"""
Route Router (Wave 3.1 Multi-Engine Resilient Edition)
------------------------------------------------------
Handles route calculation endpoints with:
- Per-event-loop Singleflight deduplication & 1 req/s upstream pacing (WeakKeyDictionary)
- 429 60s circuit breaker per engine + 4.5s per-engine timeout
- Fallback chain: FOSSGIS OSRM -> FOSSGIS Valhalla (Polyline6 1e-6) -> Optional ORS -> Haversine straight-line
- Zero 600s cache poisoning for straight-line fallbacks (15s short debounce only)
"""

import asyncio
import math
import os
import time
import weakref
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException, Request

from models.base import RouteStop, RouteRequest
from utils.limiter import limiter

router = APIRouter(prefix="/api", tags=["route"])

TABIJI_ROUTE_USER_AGENT = "TabijiTravelPWA/1.0 (https://www.tabijiapp.com; contact@tabijiapp.com)"
_ENGINE_TIMEOUT_SEC = 4.5
_CIRCUIT_BREAKER_SEC = 60.0
_THROTTLE_INTERVAL_SEC = 1.0
_STRAIGHT_DEBOUNCE_TTL_SEC = 15.0

# ═══════════════════════════════════════════════════════════════
# ⚡ HTTPX 全域共享連線池 (HTTP Keep-Alive & Connection Pooling)
# ═══════════════════════════════════════════════════════════════
_ROUTE_CLIENT: Optional[httpx.AsyncClient] = None


def get_route_client() -> httpx.AsyncClient:
    """延遲安全獲取全域 HTTPX 連線池，杜絕每次請求重複 TCP/TLS 握手延遲"""
    global _ROUTE_CLIENT
    if _ROUTE_CLIENT is None or _ROUTE_CLIENT.is_closed:
        _ROUTE_CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(_ENGINE_TIMEOUT_SEC, connect=2.5),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=15),
            headers={
                "User-Agent": TABIJI_ROUTE_USER_AGENT,
                "Accept": "application/json",
            },
        )
    return _ROUTE_CLIENT


# ═══════════════════════════════════════════════════════════════
# 🧠 Layer 1: 動線記憶體快取 (LRU Cache, 600s 僅存真實路網；15s 短防抖存直線)
# ═══════════════════════════════════════════════════════════════
class RouteLRUCache:
    def __init__(self, maxsize: int = 500, ttl_sec: float = 600.0):
        self.maxsize = maxsize
        self.ttl_sec = ttl_sec
        self._cache: OrderedDict = OrderedDict()

    def get(self, key: str) -> Optional[dict]:
        if key in self._cache:
            data, exp = self._cache[key]
            if time.time() < exp:
                self._cache.move_to_end(key)
                return data
            else:
                del self._cache[key]
        return None

    def set(self, key: str, value: dict, ttl_sec: Optional[float] = None):
        if key in self._cache:
            self._cache.move_to_end(key)
        effective_ttl = self.ttl_sec if ttl_sec is None else ttl_sec
        self._cache[key] = (value, time.time() + effective_ttl)
        if len(self._cache) > self.maxsize:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()


_ROUTE_CACHE = RouteLRUCache(maxsize=500, ttl_sec=600.0)
_STRAIGHT_DEBOUNCE_CACHE = RouteLRUCache(maxsize=256, ttl_sec=_STRAIGHT_DEBOUNCE_TTL_SEC)

# 429 60 秒引擎熔斷表
_ENGINE_CIRCUIT_OPEN_UNTIL: Dict[str, float] = {}

# Event-Loop 分桶 Singleflight 與 per-engine 1 req/s 獨立節流鎖 (FP-113 防跨迴圈崩潰；OSRM 與 Valhalla 互不阻塞)
_INFLIGHT_BY_LOOP: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Dict[str, asyncio.Future]]" = (
    weakref.WeakKeyDictionary()
)
_THROTTLE_BY_LOOP: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Dict[str, Tuple[asyncio.Lock, List[float]]]]" = (
    weakref.WeakKeyDictionary()
)


def __reset_route_state_for_testing() -> None:
    """顯式重置路線快取、熔斷器、Singleflight 與節流狀態，供 pytest 徹底隔離跨測試狀態。"""
    _ROUTE_CACHE.clear()
    _STRAIGHT_DEBOUNCE_CACHE.clear()
    _ENGINE_CIRCUIT_OPEN_UNTIL.clear()
    for bucket in list(_INFLIGHT_BY_LOOP.values()):
        bucket.clear()
    _INFLIGHT_BY_LOOP.clear()
    for engine_bucket in list(_THROTTLE_BY_LOOP.values()):
        engine_bucket.clear()
    _THROTTLE_BY_LOOP.clear()


def _is_engine_circuit_open(engine: str) -> bool:
    until = _ENGINE_CIRCUIT_OPEN_UNTIL.get(engine, 0.0)
    if until <= 0.0:
        return False
    if time.monotonic() >= until:
        _ENGINE_CIRCUIT_OPEN_UNTIL.pop(engine, None)
        return False
    return True


def _trip_engine_circuit(engine: str, duration_sec: float = _CIRCUIT_BREAKER_SEC) -> None:
    _ENGINE_CIRCUIT_OPEN_UNTIL[engine] = time.monotonic() + duration_sec


async def _pace_upstream_request(engine: str = "default") -> None:
    """1 req/s per-event-loop, per-engine upstream pacing guard for FOSSGIS compliance."""
    loop = asyncio.get_running_loop()
    engine_map = _THROTTLE_BY_LOOP.get(loop)
    if engine_map is None:
        engine_map = {}
        _THROTTLE_BY_LOOP[loop] = engine_map
    state = engine_map.get(engine)
    if state is None:
        state = (asyncio.Lock(), [0.0])
        engine_map[engine] = state
    lock, last_ts_box = state
    async with lock:
        now = time.monotonic()
        elapsed = now - last_ts_box[0]
        if last_ts_box[0] > 0.0 and elapsed < _THROTTLE_INTERVAL_SEC:
            await asyncio.sleep(_THROTTLE_INTERVAL_SEC - elapsed)
        last_ts_box[0] = time.monotonic()


def decode_polyline6(encoded: str, precision: int = 6) -> List[List[float]]:
    """
    Pure-Python Google/Valhalla Encoded Polyline decoder (precision=6 -> 1e-6).
    Returns GeoJSON [lng, lat] coordinate pairs.
    """
    if not encoded:
        return []
    factor = 10.0 ** precision
    coords: List[List[float]] = []
    index = 0
    length = len(encoded)
    lat = 0
    lng = 0

    while index < length:
        shift = 0
        result = 0
        while index < length:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat

        shift = 0
        result = 0
        while index < length:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng

        coords.append([round(lng / factor, 6), round(lat / factor, 6)])

    return coords


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """計算兩點之間的大圓幾何距離 (Haversine Formula)"""
    r = 6371.0  # 地球半徑 (km)
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return r * c


def create_straight_fallback(stops: List[RouteStop], mode: str) -> dict:
    """🛡️ 終極保底：Haversine 直線動線幾何 (保證前端地圖永不 500 報錯)"""
    total_km = 0.0
    for i in range(len(stops) - 1):
        total_km += haversine_distance_km(stops[i].lat, stops[i].lng, stops[i + 1].lat, stops[i + 1].lng)

    speed_map = {
        "walk": 4.5,
        "bike": 15.0,
        "bicycle": 15.0,
        "drive": 40.0,
        "transit": 30.0,
    }
    avg_speed = speed_map.get(mode, 40.0)
    duration_min = max(1, round((total_km / avg_speed) * 60))

    return {
        "source": "straight-line",
        "route": {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "LineString",
                "coordinates": [[s.lng, s.lat] for s in stops],
            },
        },
        "distance": f"{round(total_km, 1)} km (直線估計)",
        "duration": f"{duration_min} 分鐘 (估計)" if duration_min < 60 else f"{duration_min // 60}h {duration_min % 60}m",
    }


def _format_route_response(source: str, geometry: dict, distance_km: float, duration_min: int) -> dict:
    dist_rounded = round(distance_km, 1)
    dur_rounded = max(1, round(duration_min))
    return {
        "source": source,
        "route": {
            "type": "Feature",
            "properties": {},
            "geometry": geometry,
        },
        "distance": f"{dist_rounded} km",
        "duration": f"{dur_rounded} 分鐘" if dur_rounded < 60 else f"{dur_rounded // 60}h {dur_rounded % 60}m",
    }


async def route_with_osrm(stops: List[RouteStop], mode: str) -> dict:
    """Engine 1: FOSSGIS OSRM (專用步行/單車/車道子網域，嚴禁使用僅支援車道之 project-osrm.org)"""
    if _is_engine_circuit_open("osrm-fossgis"):
        raise RuntimeError("OSRM circuit breaker open")

    coords = ";".join([f"{s.lng},{s.lat}" for s in stops])
    if mode == "walk":
        server = "https://routing.openstreetmap.de/routed-foot"
        profile = "foot"
    elif mode in ("bike", "bicycle"):
        server = "https://routing.openstreetmap.de/routed-bike"
        profile = "bicycle"
    else:
        server = "https://routing.openstreetmap.de/routed-car"
        profile = "driving"

    url = f"{server}/route/v1/{profile}/{coords}"
    client = get_route_client()
    await _pace_upstream_request("osrm-fossgis")

    res = await client.get(
        url,
        params={
            "overview": "full",
            "geometries": "geojson",
            "steps": "false",
        },
        timeout=_ENGINE_TIMEOUT_SEC,
    )

    if res.status_code == 429:
        _trip_engine_circuit("osrm-fossgis")
        raise RuntimeError("OSRM HTTP 429 rate limited")
    if res.status_code != 200:
        raise RuntimeError(f"OSRM HTTP {res.status_code}")

    data = res.json()
    code = data.get("code")
    if code != "Ok":
        raise RuntimeError(f"OSRM API code: {code}")

    routes = data.get("routes") or []
    if not routes:
        raise RuntimeError("OSRM returned no routes")

    route = routes[0]
    return _format_route_response(
        "osrm-fossgis",
        route["geometry"],
        route["distance"] / 1000.0,
        route["duration"] / 60.0,
    )


async def route_with_valhalla(stops: List[RouteStop], mode: str) -> dict:
    """Engine 2 (Zero-Key Fallback): FOSSGIS Valhalla (valhalla1.openstreetmap.de) with Polyline6 (1e-6) decoding"""
    if _is_engine_circuit_open("valhalla-fossgis"):
        raise RuntimeError("Valhalla circuit breaker open")

    if mode == "walk":
        costing = "pedestrian"
    elif mode in ("bike", "bicycle"):
        costing = "bicycle"
    else:
        costing = "auto"

    payload = {
        "locations": [{"lat": s.lat, "lon": s.lng} for s in stops],
        "costing": costing,
        "units": "kilometers",
        "directions_options": {"narrative": False},
    }
    client = get_route_client()
    await _pace_upstream_request("valhalla-fossgis")

    res = await client.post(
        "https://valhalla1.openstreetmap.de/route",
        json=payload,
        headers={
            "User-Agent": TABIJI_ROUTE_USER_AGENT,
            "X-Client-Id": "tabijiapp.com",
            "Accept": "application/json",
        },
        timeout=_ENGINE_TIMEOUT_SEC,
    )

    if res.status_code == 429:
        _trip_engine_circuit("valhalla-fossgis")
        raise RuntimeError("Valhalla HTTP 429 rate limited")
    if res.status_code != 200:
        raise RuntimeError(f"Valhalla HTTP {res.status_code}")

    data = res.json()
    trip = data.get("trip") or {}
    legs = trip.get("legs") or []
    if not legs:
        raise RuntimeError("Valhalla returned no legs")

    combined_coords: List[List[float]] = []
    for leg in legs:
        shape = leg.get("shape") or ""
        leg_coords = decode_polyline6(shape, precision=6)
        if not leg_coords:
            continue
        if combined_coords and combined_coords[-1] == leg_coords[0]:
            combined_coords.extend(leg_coords[1:])
        else:
            combined_coords.extend(leg_coords)

    if len(combined_coords) < 2:
        raise RuntimeError("Valhalla decoded empty geometry")

    summary = trip.get("summary") or {}
    distance_km = float(summary.get("length", 0.0))
    duration_min = float(summary.get("time", 0.0)) / 60.0

    return _format_route_response(
        "valhalla-fossgis",
        {"type": "LineString", "coordinates": combined_coords},
        distance_km,
        duration_min,
    )


async def route_with_ors(stops: List[RouteStop], mode: str) -> dict:
    """Engine 3 (Optional Key Fallback): OpenRouteService (2,000 req/day free tier)"""
    ors_key = os.getenv("ORS_API_KEY", "").strip()
    if not ors_key:
        raise RuntimeError("ORS_API_KEY not configured")
    if _is_engine_circuit_open("openrouteservice"):
        raise RuntimeError("ORS circuit breaker open")

    if mode == "walk":
        profile = "foot-walking"
    elif mode in ("bike", "bicycle"):
        profile = "cycling-regular"
    else:
        profile = "driving-car"

    client = get_route_client()
    res = await client.post(
        f"https://api.openrouteservice.org/v2/directions/{profile}/geojson",
        json={"coordinates": [[s.lng, s.lat] for s in stops]},
        headers={
            "Authorization": ors_key,
            "User-Agent": TABIJI_ROUTE_USER_AGENT,
            "Accept": "application/json, application/geo+json",
        },
        timeout=_ENGINE_TIMEOUT_SEC,
    )

    if res.status_code == 429:
        _trip_engine_circuit("openrouteservice")
        raise RuntimeError("ORS HTTP 429 rate limited")
    if res.status_code != 200:
        raise RuntimeError(f"ORS HTTP {res.status_code}")

    data = res.json()
    features = data.get("features") or []
    if not features:
        raise RuntimeError("ORS returned no features")

    feat = features[0]
    geometry = feat.get("geometry") or {}
    summary = (feat.get("properties") or {}).get("summary") or {}
    distance_km = float(summary.get("distance", 0.0)) / 1000.0
    duration_min = float(summary.get("duration", 0.0)) / 60.0

    return _format_route_response("openrouteservice", geometry, distance_km, duration_min)


async def _compute_route_chain(stops: List[RouteStop], mode: str, cache_key: str) -> dict:
    """Execute multi-engine routing chain with strict cache separation for real vs straight-line results."""
    engines = [
        ("OSRM", route_with_osrm),
        ("Valhalla", route_with_valhalla),
        ("ORS", route_with_ors),
    ]
    for label, fn in engines:
        try:
            result = await fn(stops, mode)
            route_feature = result.get("route") if isinstance(result, dict) else None
            if (
                isinstance(result, dict)
                and isinstance(route_feature, dict)
                and route_feature.get("geometry")
                and result.get("source")
                and result.get("source") != "straight-line"
            ):
                _ROUTE_CACHE.set(cache_key, result)
                print(f"   ✅ {label} 路線成功: {result.get('distance')}, {result.get('duration')}")
                return result
        except Exception as e:
            if label != "ORS" or os.getenv("ORS_API_KEY", "").strip():
                print(f"   ⚠️ {label} 計算失敗 ({e})，嘗試下一引擎...")

    # Straight-line fallback: 15s short debounce ONLY (NEVER write to 600s _ROUTE_CACHE)
    fallback_res = create_straight_fallback(stops, mode)
    _STRAIGHT_DEBOUNCE_CACHE.set(cache_key, fallback_res, ttl_sec=_STRAIGHT_DEBOUNCE_TTL_SEC)
    return fallback_res


@router.post("/route")
@limiter.limit("60/minute")
async def calculate_route(request: Request, body: RouteRequest):
    """🛣️ 路線運算端點 (FOSSGIS OSRM ➔ FOSSGIS Valhalla ➔ ORS ➔ Haversine 15s 短防抖 + Singleflight)"""
    if len(body.stops) < 2:
        raise HTTPException(status_code=400, detail="至少需要 2 個停靠點")

    # 座標 4 位量化 (~11m) 對齊 Edge Shield 邊緣快取鍵
    cache_key = f"{body.mode}:{';'.join(f'{s.lng:.4f},{s.lat:.4f}' for s in body.stops)}"

    # Layer 1: 真實路網 600s 快取命中 (0ms 直出)
    cached = _ROUTE_CACHE.get(cache_key)
    if cached:
        print(f"   ⚡ [Route Cache] Hit: {len(body.stops)} stops, mode={body.mode}")
        return cached

    # Layer 1.5: 直線 15s 短防抖命中 (防全引擎暫斷期間短時雪崩，15s 後自動恢復重探)
    debounced = _STRAIGHT_DEBOUNCE_CACHE.get(cache_key)
    if debounced:
        return debounced

    # Layer 2: Per-event-loop Singleflight 去重合併併發請求
    loop = asyncio.get_running_loop()
    inflight_map = _INFLIGHT_BY_LOOP.get(loop)
    if inflight_map is None:
        inflight_map = {}
        _INFLIGHT_BY_LOOP[loop] = inflight_map

    existing_fut = inflight_map.get(cache_key)
    if existing_fut is not None:
        return await asyncio.shield(existing_fut)

    fut: asyncio.Future = loop.create_future()
    inflight_map[cache_key] = fut
    try:
        result = await _compute_route_chain(body.stops, body.mode, cache_key)
        if not fut.done():
            fut.set_result(result)
        return result
    except Exception as exc:
        if not fut.done():
            fut.set_exception(exc)
        raise
    finally:
        if inflight_map.get(cache_key) is fut:
            inflight_map.pop(cache_key, None)
