"""
Route Router
------------
Handles route calculation endpoints with OSRM engine and Haversine straight-line fallback.
"""

import math
import time
from collections import OrderedDict
from typing import List, Optional

import httpx
from fastapi import APIRouter, HTTPException

from models.base import RouteStop, RouteRequest

router = APIRouter(prefix="/api", tags=["route"])

# ═══════════════════════════════════════════════════════════════
# ⚡ HTTPX 全域共享連線池 (HTTP Keep-Alive & Connection Pooling)
# ═══════════════════════════════════════════════════════════════
_ROUTE_CLIENT: Optional[httpx.AsyncClient] = None


def get_route_client() -> httpx.AsyncClient:
    """延遲安全獲取全域 HTTPX 連線池，杜絕每次請求重複 TCP/TLS 握手延遲"""
    global _ROUTE_CLIENT
    if _ROUTE_CLIENT is None or _ROUTE_CLIENT.is_closed:
        _ROUTE_CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=5.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=15),
            headers={
                "User-Agent": "RyanTravelPWA/1.0 (https://github.com/ryan-travel-app)",
                "Accept": "application/json"
            }
        )
    return _ROUTE_CLIENT


# ═══════════════════════════════════════════════════════════════
# 🧠 Layer 1: 動線記憶體快取 (LRU Cache, TTL 10 分鐘)
# 嚴格守護 FOSSGIS 1 req/s 政策，短時間內重複縮放/排序 0ms 直出
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

    def set(self, key: str, value: dict):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (value, time.time() + self.ttl_sec)
        if len(self._cache) > self.maxsize:
            self._cache.popitem(last=False)


_ROUTE_CACHE = RouteLRUCache(maxsize=500, ttl_sec=600.0)


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """計算兩點之間的大圓幾何距離 (Haversine Formula)"""
    r = 6371.0  # 地球半徑 (km)
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def create_straight_fallback(stops: List[RouteStop], mode: str) -> dict:
    """🛡️ Layer 3 終極保底：Haversine 直線動線幾何 (保證前端地圖永不 500 報錯)"""
    total_km = 0.0
    for i in range(len(stops) - 1):
        total_km += haversine_distance_km(stops[i].lat, stops[i].lng, stops[i + 1].lat, stops[i + 1].lng)

    # 依模式推估旅行時長 (km/h)
    speed_map = {
        "walk": 4.5,
        "bike": 15.0,
        "bicycle": 15.0,
        "drive": 40.0,
        "transit": 30.0
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
                "coordinates": [[s.lng, s.lat] for s in stops]
            }
        },
        "distance": f"{round(total_km, 1)} km (直線估計)",
        "duration": f"{duration_min} 分鐘 (估計)" if duration_min < 60 else f"{duration_min // 60}h {duration_min % 60}m"
    }


async def route_with_osrm(stops: List[RouteStop], mode: str) -> dict:
    """使用 OSRM (FOSSGIS 伺服器) 計算真實拓撲路線"""
    coords = ";".join([f"{s.lng},{s.lat}" for s in stops])
    
    # 依據移動模式選擇專屬子網域 (FOSSGIS 規範)
    if mode == "walk":
        server = "https://routing.openstreetmap.de/routed-foot"
        profile = "foot"
    elif mode in ("bike", "bicycle"):
        server = "https://routing.openstreetmap.de/routed-bike"
        profile = "bicycle"
    else:  # drive, transit 或其他預設
        server = "https://routing.openstreetmap.de/routed-car"
        profile = "driving"
    
    url = f"{server}/route/v1/{profile}/{coords}"
    client = get_route_client()
    
    # 關鍵參數：steps=false 大幅減少 70% 傳輸體積與 JSON 解析開銷
    res = await client.get(
        url,
        params={
            "overview": "full",
            "geometries": "geojson",
            "steps": "false"
        }
    )
    
    if res.status_code != 200:
        raise Exception(f"OSRM HTTP {res.status_code}: {res.text[:120]}")
    
    data = res.json()
    code = data.get("code")
    if code != "Ok":
        raise Exception(f"OSRM API code: {code} ({data.get('message', 'No details')})")
    
    if not data.get("routes") or len(data["routes"]) == 0:
        raise Exception("OSRM returned no routes")
    
    route = data["routes"][0]
    distance_km = round(route["distance"] / 1000.0, 1)
    duration_min = round(route["duration"] / 60.0)
    
    return {
        "source": "osrm-fossgis",
        "route": {
            "type": "Feature",
            "properties": {},
            "geometry": route["geometry"]
        },
        "distance": f"{distance_km} km",
        "duration": f"{duration_min} 分鐘" if duration_min < 60 else f"{duration_min // 60}h {duration_min % 60}m"
    }


@router.post("/route")
async def calculate_route(request: RouteRequest):
    """🛣️ 路線運算端點 (OSRM 預設引擎 ✕ LRU 快取 ✕ Haversine 直線保底)"""
    if len(request.stops) < 2:
        raise HTTPException(status_code=400, detail="至少需要 2 個停靠點")
    
    # 構造快取 Key (座標精度保留 5 位小數，約 1 公尺精度)
    cache_key = f"{request.mode}:{';'.join(f'{s.lng:.5f},{s.lat:.5f}' for s in request.stops)}"
    
    # Layer 1: 記憶體快取命中 (0ms 直出)
    cached = _ROUTE_CACHE.get(cache_key)
    if cached:
        print(f"   ⚡ [Route Cache] Hit: {len(request.stops)} stops, mode={request.mode}")
        return cached

    print(f"🛣️ 計算路線 (OSRM): {len(request.stops)} 個點, 模式={request.mode}, 優化={request.optimize}")
    
    # Layer 2: OSRM 核心路網計算
    try:
        result = await route_with_osrm(request.stops, request.mode)
        _ROUTE_CACHE.set(cache_key, result)
        print(f"   ✅ OSRM 路線成功: {result['distance']}, {result['duration']}")
        return result
    except Exception as e:
        print(f"   ⚠️ OSRM 計算失敗或孤島無路網: {e}, 啟動 Haversine 直線保底")

    # Layer 3: Haversine 直線保底 (防止前端 500 報錯崩潰)
    fallback_res = create_straight_fallback(request.stops, request.mode)
    _ROUTE_CACHE.set(cache_key, fallback_res)
    return fallback_res
