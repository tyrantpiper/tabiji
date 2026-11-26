"""
POI 服務層 - 整合 OSM Overpass + OpenTripMap API
提供附近設施搜索功能，並優化 AI Token 消耗
"""

import os
import httpx
import asyncio
import re
import unicodedata
from typing import List, Dict, Optional, Any, Tuple
from math import radians, cos, sin, sqrt, atan2
from urllib.parse import quote, urlparse, urlunparse, unquote
from datetime import datetime
import time
import logging
from utils.url_safety import is_safe_url

TABIJI_USER_AGENT = "TabijiTravelPWA/1.0 (https://www.tabijiapp.com; contact@tabijiapp.com)"

_SAFE_RASTER_EXTS = (".jpg", ".jpeg", ".png", ".webp")
_WIKI_THUMB_WIDTH_RE = re.compile(r"(/thumb/.+/(?:lossy-page\d+-|page\d+-)?)(\d+)px-([^/?#]+)$")


def _pick_hd_wiki_image(data: Optional[Dict[str, Any]], target_width: int = 960) -> str:
    """Select a high-res Wikimedia raster image up to `target_width` (960px standard).

    1. Only return `originalimage.source` directly when its extension is a safe raster
       (`.jpg`/`.jpeg`/`.png`/`.webp`) and `331 <= width <= target_width` (blocks SVG 415
       and TIFF/DjVu broken images).
    2. Otherwise, if `thumbnail.source` exists (and is not raw `.svg`/`.svgz`), upgrade
       `/<N>px-` to `/<target_width>px-` when `<N> < target_width`.
    """
    if not isinstance(data, dict):
        return ""

    orig = data.get("originalimage")
    if isinstance(orig, dict):
        orig_src = str(orig.get("source") or "").strip()
        orig_w = orig.get("width")
        if (
            orig_src
            and isinstance(orig_w, (int, float))
            and not isinstance(orig_w, bool)
            and 331 <= orig_w <= target_width
        ):
            decoded_orig_path = unquote(unquote(urlparse(orig_src).path)).rstrip("/").lower()
            if decoded_orig_path.endswith(_SAFE_RASTER_EXTS):
                return orig_src

    thumb = data.get("thumbnail")
    thumb_src = str(thumb.get("source") or "").strip() if isinstance(thumb, dict) else ""
    if not thumb_src:
        return ""

    parsed = urlparse(thumb_src)
    decoded_thumb_path = unquote(unquote(parsed.path)).rstrip("/").lower()
    if decoded_thumb_path.endswith((".svg", ".svgz")):
        return ""

    m = _WIKI_THUMB_WIDTH_RE.search(parsed.path)
    if m:
        cur_w = int(m.group(2))
        if cur_w < target_width:
            new_path = f"{parsed.path[:m.start()]}{m.group(1)}{target_width}px-{m.group(3)}"
            return urlunparse((parsed.scheme, parsed.netloc, new_path, parsed.params, parsed.query, parsed.fragment))
    return thumb_src

logger = logging.getLogger("poi-service")

# 🛡️ [Security Sentinel Guard] Overpass QL Injection & Character Sanitizer
def sanitize_overpass_keyword(keyword: str) -> str:
    """Strip dangerous Overpass QL characters (quotes, semicolons, brackets) to prevent QL injection."""
    if not keyword:
        return ""
    sanitized = re.sub(r'[\";\[\]\(\)\{\}\<\>]', '', str(keyword))
    sanitized = sanitized.replace('\n', '').replace('\r', '')
    return sanitized.strip()[:64]

# 🆕 Phase 1 Observability (Lazy Loading to prevent Windows import deadlock)
_POI_METRICS = {"latency": None, "requests": None}

def _get_poi_metrics():
    """Lazy initialization of Prometheus metrics with ModuleNotFoundError resilience"""
    try:
        from prometheus_client import Counter, Histogram
        if _POI_METRICS["latency"] is None:
            _POI_METRICS["latency"] = Histogram(
                "poi_enrichment_latency_seconds",
                "Latency of individual source enrichment in seconds",
                ["source"],
                buckets=[0.1, 0.5, 1.0, 2.0, 2.5, 3.0, 5.0, 10.0]
            )
        if _POI_METRICS["requests"] is None:
            _POI_METRICS["requests"] = Counter(
                "poi_enrichment_requests_total",
                "Total number of enrichment requests per source and status",
                ["source", "status"]
            )
        return _POI_METRICS["latency"], _POI_METRICS["requests"]
    except (ImportError, ModuleNotFoundError):
        # 🛡️ Resilience logic: Return a Mock object that accepts .labels().observe() and .labels().inc()
        class MockMetric:
            def labels(self, *args, **kwargs): return self
            def observe(self, *args, **kwargs): pass
            def inc(self, *args, **kwargs): pass
        return MockMetric(), MockMetric()

# 🆕 Phase 1 Concurrency Control (壓低至 8 防 Wikimedia 429)
WIKI_SEMAPHORE = asyncio.Semaphore(8)

# Overpass API endpoint
OVERPASS_API = "https://overpass-api.de/api/interpreter"

# OpenTripMap API (免費無限制)
OPENTRIPMAP_API = "https://api.opentripmap.com/0.1/en/places"

# Photon Reverse & Nominatim Spatial Fallback Endpoints
PHOTON_REVERSE_API = "https://photon.komoot.io/reverse"
NOMINATIM_SEARCH_API = "https://nominatim.openstreetmap.org/search"

# 🛡️ 5 分鐘空間結果記憶體快取 (TTL = 300s, max 256 entries)
NEARBY_POI_CACHE_TTL_SEC = 300.0
NEARBY_POI_CACHE_MAX_ENTRIES = 256
NEARBY_POI_CACHE: Dict[Tuple[float, float, str, int], Tuple[float, List[Dict]]] = {}


def __resetNearbyPoiCacheForTesting() -> None:
    """Explicit test reset hook for module-level nearby POI cache."""
    NEARBY_POI_CACHE.clear()


# POI 類別映射: 前端類別 -> Overpass 查詢標籤
CATEGORY_OVERPASS_MAP = {
    "department_store": 'nwr["shop"="department_store"]',
    "restaurant": 'nwr["amenity"="restaurant"]',
    "convenience": 'nwr["shop"="convenience"]',
    "supermarket": 'nwr["shop"="supermarket"]',
    "pharmacy": 'nwr["amenity"="pharmacy"]',
    "popular": 'nwr["tourism"~"attraction|museum|viewpoint|gallery|theme_park"]'  # 景點直接由 Overpass 高速支援
}

# POI 類別映射: 前端類別 -> Photon /reverse Elasticsearch OSM tag filter
CATEGORY_PHOTON_QUERY_FILTER = {
    "department_store": "osm_value:department_store OR osm_value:mall OR osm_value:shopping_centre",
    "restaurant": "osm_value:restaurant OR osm_value:fast_food OR osm_value:food_court OR osm_value:cafe",
    "convenience": "osm_value:convenience",
    "supermarket": "osm_value:supermarket OR osm_value:grocery",
    "pharmacy": "osm_value:pharmacy OR osm_value:chemist",
    "popular": "osm_value:attraction OR osm_value:museum OR osm_value:viewpoint OR osm_value:gallery OR osm_value:theme_park OR osm_value:monument OR osm_value:castle OR osm_value:ruins",
}

# POI 類別映射: 前端類別 -> Nominatim Tag 查詢兜底
CATEGORY_NOMINATIM_TAG_MAP = {
    "department_store": "[shop=department_store]",
    "restaurant": "[amenity=restaurant]",
    "convenience": "[shop=convenience]",
    "supermarket": "[shop=supermarket]",
    "pharmacy": "[amenity=pharmacy]",
    "popular": "[tourism=attraction]",
}

# POI 類別映射: 前端類別 -> OpenTripMap kinds
CATEGORY_OPENTRIPMAP_MAP = {
    "department_store": "malls",
    "restaurant": "foods",
    "convenience": "shops",
    "supermarket": "shops",
    "pharmacy": "drugstores",  # OpenTripMap 用 drugstores
    "popular": "interesting_places"
}

# 位置相關關鍵字 (用於偵測 POI 查詢)
LOCATION_KEYWORDS = [
    "附近", "周邊", "nearby", "around", "near",
    "哪裡有", "哪裏有", "哪邊有", "where",
    "推薦", "recommend", "suggest",
    "最近的", "closest", "nearest"
]

# 類別關鍵字映射 (用戶語言 -> POI 類別)
CATEGORY_KEYWORDS = {
    "pharmacy": ["藥局", "藥妝", "藥店", "pharmacy", "drugstore", "松本清", "大國"],
    "restaurant": ["餐廳", "美食", "吃飯", "restaurant", "food", "吃的", "好吃"],
    "convenience": ["超商", "便利商店", "便利店", "7-11", "全家", "羅森", "lawson", "便利"],
    "supermarket": ["超市", "超級市場", "supermarket", "grocery"],
    "department_store": ["百貨", "百貨公司", "mall", "shopping"],
    "popular": ["景點", "熱門", "觀光", "attraction", "tourist", "sightseeing"]
}


def detect_poi_query(message: str) -> Optional[Dict]:
    """
    偵測訊息是否為 POI 相關查詢
    
    Args:
        message: 用戶訊息
    
    Returns:
        如果是 POI 查詢，回傳 {"is_poi_query": True, "category": "pharmacy"}
        否則回傳 None
    """
    message_lower = message.lower()
    
    # 檢查是否包含位置關鍵字
    has_location_keyword = any(kw in message_lower for kw in LOCATION_KEYWORDS)
    
    if not has_location_keyword:
        return None
    
    # 偵測類別
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in message_lower:
                return {
                    "is_poi_query": True,
                    "category": category,
                    "matched_keyword": kw
                }
    
    # 有位置關鍵字但無明確類別，預設搜索熱門景點
    return {
        "is_poi_query": True,
        "category": "popular",
        "matched_keyword": None
    }


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """計算兩點間的 Haversine 距離（公尺）"""
    R = 6371000  # 地球半徑（公尺）
    
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    
    a = sin(delta_lat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return R * c


async def search_overpass(
    lat: float,
    lng: float,
    category: str,
    radius: int = 1000,
    timeout: float = 10.0
) -> List[Dict]:
    """
    透過 OSM Overpass API 搜索附近 POI
    
    Args:
        lat: 中心點緯度
        lng: 中心點經度
        category: POI 類別 (pharmacy, restaurant, etc.)
        radius: 搜索半徑（公尺）
        timeout: Overpass QL 與 HTTP 逾時（秒，預設 10.0）
    
    Returns:
        POI 列表
    """
    overpass_tag = CATEGORY_OVERPASS_MAP.get(category)
    if not overpass_tag:
        return []
    
    ql_timeout = max(1, int(round(timeout)))
    # Overpass QL 查詢語法
    query = f"""
    [out:json][timeout:{ql_timeout}];
    (
      {overpass_tag}(around:{radius},{lat},{lng});
    );
    out center 25 qt;
    """
    
    # [SAFETY] SSRF Protection
    if not is_safe_url(OVERPASS_API):
        logger.warning(f"Blocked unsafe Overpass request: {OVERPASS_API}")
        return []

    headers = {
        "User-Agent": "TabidachiTravelApp/1.0 (contact@tabidachi.app)",
        "Accept": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                OVERPASS_API,
                data={"data": query},
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
            
            pois = []
            for element in data.get("elements", []):
                # 取得座標（node 直接有，way/relation 用 center）
                poi_lat = element.get("lat") or element.get("center", {}).get("lat")
                poi_lng = element.get("lon") or element.get("center", {}).get("lon")
                
                if not poi_lat or not poi_lng:
                    continue
                
                tags = element.get("tags", {})
                name = tags.get("name") or tags.get("name:en") or tags.get("name:ja") or "Unknown"
                
                # 計算距離
                distance = round(haversine_distance(lat, lng, poi_lat, poi_lng))
                
                pois.append({
                    "id": f"osm_{element.get('id')}",
                    "name": name,
                    "category": category,
                    "lat": poi_lat,
                    "lng": poi_lng,
                    "distance": distance,
                    "address": tags.get("addr:full") or tags.get("addr:street", ""),
                    "phone": tags.get("phone", ""),
                    "website": tags.get("website", ""),
                    "opening_hours": tags.get("opening_hours", ""),
                    "cuisine": tags.get("cuisine", ""),
                    "wikidata_id": tags.get("wikidata", ""),
                    "source": "osm"
                })
            
            # 按距離排序
            pois.sort(key=lambda x: x["distance"])
            return pois[:20]  # 最多回傳 20 個
            
    except Exception as e:
        print(f"Overpass API error: {e}")
        return []


async def search_opentripmap(
    lat: float,
    lng: float,
    category: str,
    radius: int = 1000,
    api_key: str = ""
) -> List[Dict]:
    """
    透過 OpenTripMap API 搜索附近旅遊景點
    
    Args:
        lat: 中心點緯度
        lng: 中心點經度
        category: POI 類別
        radius: 搜索半徑（公尺）
        api_key: OpenTripMap API Key (免費申請)
    
    Returns:
        POI 列表（含評分）
    """
    kind = CATEGORY_OPENTRIPMAP_MAP.get(category, "interesting_places")
    
    # 🛡️ 2026 防護：OpenTripMap 現行規範強制要求 API Key，無 Key 立即短路返回以杜絕 401 慢阻斷
    effective_key = api_key or os.getenv("OPENTRIPMAP_API_KEY", "")
    if not effective_key:
        return []

    url = f"{OPENTRIPMAP_API}/radius"
    params = {
        "radius": radius,
        "lon": lng,
        "lat": lat,
        "kinds": kind,
        "format": "json",
        "limit": 20,
        "apikey": effective_key
    }
    
    # [SAFETY] SSRF Protection
    if not is_safe_url(url):
        logger.warning(f"Blocked unsafe OpenTripMap request: {url}")
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            
            # OpenTripMap 可能回傳空或錯誤
            if response.status_code != 200:
                print(f"OpenTripMap error: {response.status_code}")
                return []
            
            data = response.json()
            if not isinstance(data, list):
                return []
            
            pois = []
            for item in data:
                poi_lat = item.get("point", {}).get("lat")
                poi_lng = item.get("point", {}).get("lon")
                
                if not poi_lat or not poi_lng:
                    continue
                
                distance = round(haversine_distance(lat, lng, poi_lat, poi_lng))
                
                pois.append({
                    "id": f"otm_{item.get('xid')}",
                    "name": item.get("name") or "Unknown",
                    "category": category,
                    "lat": poi_lat,
                    "lng": poi_lng,
                    "distance": distance,
                    "rating": item.get("rate", 0),  # 1-10 評分
                    "wikidata_id": item.get("wikidata", ""),
                    "source": "opentripmap"
                })
            
            pois.sort(key=lambda x: x["distance"])
            return pois
            
    except Exception as e:
        print(f"OpenTripMap API error: {e}")
        return []


def _select_wiki_lang_for_coords(lat: float, lng: float) -> str:
    """Select regional Wikipedia edition from coordinates for richer local landmarks."""
    if 21.5 <= lat <= 25.5 and 119.5 <= lng <= 122.5:
        return "zh"
    if 24.0 <= lat <= 45.6 and 122.9 <= lng <= 154.0:
        return "ja"
    if 18.0 <= lat <= 53.6 and 73.5 <= lng <= 135.1:
        return "zh"
    return "en"


async def _query_photon_reverse_once(
    client: httpx.AsyncClient,
    lat: float,
    lng: float,
    category: str,
    radius_km: float,
    query_filter: str,
) -> List[Dict]:
    params = {
        "lat": lat,
        "lon": lng,
        "radius": radius_km,
        "limit": 25,
        "distance_sort": "true",
        "query_string_filter": query_filter,
    }
    resp = await client.get(PHOTON_REVERSE_API, params=params)
    if resp.status_code != 200:
        return []
    data = resp.json()
    pois: List[Dict] = []
    for idx, feat in enumerate(data.get("features", [])):
        props = feat.get("properties") or {}
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        name = (props.get("name") or "").strip()
        if not name or len(coords) < 2:
            continue
        poi_lng, poi_lat = coords[0], coords[1]
        if poi_lat is None or poi_lng is None:
            continue
        street = props.get("street") or ""
        housenumber = props.get("housenumber") or ""
        district = props.get("district") or props.get("city") or ""
        addr_parts = [p for p in (district, f"{street} {housenumber}".strip()) if p]
        osm_id = props.get("osm_id") or f"r{idx}_{round(float(poi_lat), 5)}_{round(float(poi_lng), 5)}"
        pois.append({
            "id": f"photon_{osm_id}",
            "name": name,
            "category": category,
            "lat": float(poi_lat),
            "lng": float(poi_lng),
            "distance": round(haversine_distance(lat, lng, float(poi_lat), float(poi_lng))),
            "address": ", ".join(addr_parts),
            "phone": "",
            "website": "",
            "opening_hours": "",
            "wikidata_id": "",
            "source": "photon_reverse",
        })
    pois.sort(key=lambda x: x["distance"])
    return pois


async def _search_photon_reverse_nearby(
    lat: float,
    lng: float,
    category: str,
    radius: int = 1000,
    timeout: float = 3.5,
) -> List[Dict]:
    """Tier 1 resilient spatial fallback via Photon /reverse + structured OSM tag filters."""
    query_filter = CATEGORY_PHOTON_QUERY_FILTER.get(category)
    if not query_filter or not is_safe_url(PHOTON_REVERSE_API):
        return []

    initial_radius_km = max(1.5, min(round(radius / 1000.0, 2), 10.0))
    headers = {"User-Agent": os.getenv("APP_USER_AGENT", "TabidachiTravelApp/2.0 (contact@tabidachi.app)")}
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            pois = await _query_photon_reverse_once(client, lat, lng, category, initial_radius_km, query_filter)
            if len(pois) < 2 and initial_radius_km <= 2.0:
                expanded = await _query_photon_reverse_once(client, lat, lng, category, 6.0, query_filter)
                if len(expanded) > len(pois):
                    pois = expanded
            return pois[:20]
    except Exception as e:
        logger.debug(f"[NearbySearch] Photon reverse error: {e}")
        return []


async def _search_wikipedia_geosearch_nearby(
    lat: float,
    lng: float,
    category: str,
    radius: int = 1000,
    timeout: float = 3.0,
) -> List[Dict]:
    """Tier 2 landmark discovery via Wikipedia Geosearch API."""
    lang = _select_wiki_lang_for_coords(lat, lng)
    wiki_url = f"https://{lang}.wikipedia.org/w/api.php"
    if not is_safe_url(wiki_url):
        return []

    gsradius = min(max(int(radius * 2), 2000), 10000)
    params = {
        "action": "query",
        "list": "geosearch",
        "gscoord": f"{lat}|{lng}",
        "gsradius": gsradius,
        "gslimit": 20,
        "format": "json",
    }
    headers = {"User-Agent": os.getenv("APP_USER_AGENT", "TabidachiTravelApp/2.0 (contact@tabidachi.app)")}
    try:
        async with WIKI_SEMAPHORE:
            async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
                resp = await client.get(wiki_url, params=params)
                if resp.status_code != 200:
                    return []
                data = resp.json()
        pois: List[Dict] = []
        for item in ((data.get("query") or {}).get("geosearch") or []):
            title = (item.get("title") or "").strip()
            p_lat = item.get("lat")
            p_lng = item.get("lon")
            if not title or p_lat is None or p_lng is None:
                continue
            dist = round(haversine_distance(lat, lng, float(p_lat), float(p_lng)))
            pois.append({
                "id": f"wiki_{lang}_{item.get('pageid')}",
                "name": title,
                "category": category,
                "lat": float(p_lat),
                "lng": float(p_lng),
                "distance": dist,
                "address": "",
                "phone": "",
                "website": f"https://{lang}.wikipedia.org/?curid={item.get('pageid')}" if item.get("pageid") else "",
                "opening_hours": "",
                "wikidata_id": "",
                "source": "wikipedia",
            })
        pois.sort(key=lambda x: x["distance"])
        return pois[:20]
    except Exception as e:
        logger.debug(f"[NearbySearch] Wikipedia geosearch error: {e}")
        return []


async def _search_nominatim_nearby(
    lat: float,
    lng: float,
    category: str,
    radius: int = 1000,
    timeout: float = 3.0,
) -> List[Dict]:
    """Tier 3 single-shot bounded Nominatim fallback (never looped/retried to respect 1 req/s policy)."""
    osm_tag = CATEGORY_NOMINATIM_TAG_MAP.get(category)
    if not osm_tag or not is_safe_url(NOMINATIM_SEARCH_API):
        return []

    delta_lat = max(radius, 1500) / 111320.0
    cos_lat = max(abs(cos(radians(lat))), 0.2)
    delta_lng = delta_lat / cos_lat
    viewbox = f"{lng - delta_lng:.6f},{lat + delta_lat:.6f},{lng + delta_lng:.6f},{lat - delta_lat:.6f}"
    params = {
        "q": osm_tag,
        "format": "jsonv2",
        "viewbox": viewbox,
        "bounded": 1,
        "limit": 20,
    }
    headers = {"User-Agent": os.getenv("APP_USER_AGENT", "TabidachiTravelApp/2.0 (contact@tabidachi.app)")}
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            resp = await client.get(NOMINATIM_SEARCH_API, params=params)
            if resp.status_code != 200:
                return []
            items = resp.json()
        if not isinstance(items, list):
            return []
        pois: List[Dict] = []
        for item in items:
            raw_name = (item.get("name") or (item.get("display_name") or "").split(",")[0]).strip()
            p_lat = item.get("lat")
            p_lng = item.get("lon")
            if not raw_name or p_lat is None or p_lng is None:
                continue
            f_lat, f_lng = float(p_lat), float(p_lng)
            pois.append({
                "id": f"nom_{item.get('osm_id', round(f_lat, 5))}",
                "name": raw_name,
                "category": category,
                "lat": f_lat,
                "lng": f_lng,
                "distance": round(haversine_distance(lat, lng, f_lat, f_lng)),
                "address": item.get("display_name", ""),
                "phone": "",
                "website": "",
                "opening_hours": "",
                "wikidata_id": "",
                "source": "nominatim",
            })
        pois.sort(key=lambda x: x["distance"])
        return pois[:20]
    except Exception as e:
        logger.debug(f"[NearbySearch] Nominatim fallback error: {e}")
        return []


def _merge_and_dedupe_pois(batches: List[List[Dict]]) -> List[Dict]:
    """Merge prioritized POI batches while preserving the highest-priority source and deduplicating overlaps."""
    merged: List[Dict] = []
    seen_wikidata: set[str] = set()
    seen_names: set[str] = set()

    for batch in batches:
        for poi in batch or []:
            if not isinstance(poi, dict):
                continue
            p_lat = poi.get("lat")
            p_lng = poi.get("lng")
            if p_lat is None or p_lng is None:
                continue
            w_id = (poi.get("wikidata_id") or "").strip()
            name_norm = (poi.get("name") or "").strip().lower()
            if w_id and w_id in seen_wikidata:
                continue
            if name_norm and name_norm in seen_names:
                continue
            is_spatial_dup = False
            if name_norm:
                prefix = name_norm[:4]
                for existing in merged:
                    ex_name = (existing.get("name") or "").strip().lower()
                    if ex_name and (ex_name.startswith(prefix) or name_norm.startswith(ex_name[:4])):
                        if haversine_distance(float(p_lat), float(p_lng), float(existing["lat"]), float(existing["lng"])) < 35:
                            is_spatial_dup = True
                            break
            if is_spatial_dup:
                continue
            if w_id:
                seen_wikidata.add(w_id)
            if name_norm:
                seen_names.add(name_norm)
            merged.append(poi)

    merged.sort(key=lambda x: x.get("distance", 0))
    return merged[:20]


async def search_nearby_fallback(
    lat: float,
    lng: float,
    category: str,
    radius: int = 1000,
    timeout: float = 3.5,
) -> List[Dict]:
    """Multi-tier spatial fallback: Photon /reverse -> Wikipedia Geosearch -> single-shot Nominatim."""
    if category == "popular":
        photon_res, wiki_res = await asyncio.gather(
            _search_photon_reverse_nearby(lat, lng, category, radius, timeout=timeout),
            _search_wikipedia_geosearch_nearby(lat, lng, category, radius, timeout=min(timeout, 3.0)),
            return_exceptions=True,
        )
        p_list = photon_res if isinstance(photon_res, list) else []
        w_list = wiki_res if isinstance(wiki_res, list) else []
        combined = _merge_and_dedupe_pois([p_list, w_list])
        if combined:
            return combined
        return await _search_nominatim_nearby(lat, lng, category, radius, timeout=min(timeout, 3.0))

    photon_list = await _search_photon_reverse_nearby(lat, lng, category, radius, timeout=timeout)
    if photon_list:
        return photon_list

    nom_list = await _search_nominatim_nearby(lat, lng, category, radius, timeout=min(timeout, 3.0))
    if nom_list:
        return nom_list

    return await _search_wikipedia_geosearch_nearby(lat, lng, category, radius, timeout=min(timeout, 2.5))


async def search_poi_combined(
    lat: float,
    lng: float,
    category: str,
    radius: int = 1000,
    opentripmap_key: str = "",
    timeout: float = 10.0
) -> List[Dict]:
    """
    整合多個來源並行避險搜索 POI，合併去重與 5 分鐘空間快取

    優先採用 Overpass（標籤與座標最精確），OpenTripMap 補充評分；
    同時並行啟動 Photon /reverse + Wiki Geosearch 空間備援，消除單點 502/逾時空回傳。
    """
    cache_key = (round(float(lat), 3), round(float(lng), 3), str(category), int(radius))
    now_ts = time.monotonic()
    cached_entry = NEARBY_POI_CACHE.get(cache_key)
    if cached_entry is not None:
        cached_at, cached_pois = cached_entry
        if now_ts - cached_at < NEARBY_POI_CACHE_TTL_SEC:
            return [dict(item) for item in cached_pois]
        NEARBY_POI_CACHE.pop(cache_key, None)

    overpass_timeout = min(float(timeout), 2.5)
    fallback_timeout = min(max(float(timeout), 3.0), 4.0)

    # 並行啟動主源與備援，確保總延遲 <= max(2.5s, 備援 ~1s) 而非串列累加
    overpass_task = search_overpass(lat, lng, category, radius, timeout=overpass_timeout)
    opentripmap_task = search_opentripmap(lat, lng, category, radius, opentripmap_key)
    fallback_task = search_nearby_fallback(lat, lng, category, radius, timeout=fallback_timeout)

    overpass_results, opentripmap_results, fallback_results = await asyncio.gather(
        overpass_task,
        opentripmap_task,
        fallback_task,
        return_exceptions=True
    )

    # 處理異常
    overpass_results = overpass_results if isinstance(overpass_results, list) else []
    opentripmap_results = opentripmap_results if isinstance(opentripmap_results, list) else []
    fallback_results = fallback_results if isinstance(fallback_results, list) else []

    # 建立 Wikidata ID 對照表（用於合併評分）
    wikidata_ratings = {}
    for poi in opentripmap_results:
        if poi.get("wikidata_id"):
            wikidata_ratings[poi["wikidata_id"]] = poi.get("rating", 0)

    # 為 Overpass 結果補充評分
    for poi in overpass_results:
        if poi.get("wikidata_id") and poi["wikidata_id"] in wikidata_ratings:
            poi["rating"] = wikidata_ratings[poi["wikidata_id"]]

    combined = _merge_and_dedupe_pois([overpass_results, opentripmap_results, fallback_results])

    if combined:
        if len(NEARBY_POI_CACHE) >= NEARBY_POI_CACHE_MAX_ENTRIES:
            oldest_key = next(iter(NEARBY_POI_CACHE))
            NEARBY_POI_CACHE.pop(oldest_key, None)
        NEARBY_POI_CACHE[cache_key] = (now_ts, [dict(item) for item in combined])

    return combined


def format_pois_for_ai(pois: List[Dict], max_items: int = 5, locale: str = "zh") -> str:
    """
    將 POI 列表格式化為精簡文字，供 AI 處理
    
    這是 Token 優化的關鍵！
    原始 JSON 可能 5KB，格式化後只有 ~500 bytes
    """
    is_en = bool(locale and str(locale).strip().lower().startswith("en"))
    empty_msg = "No nearby places found." if is_en else "附近沒有找到相關地點。"
    default_name = "Unknown Place" if is_en else "未知地點"
    if not pois or not isinstance(pois, list):
        return empty_msg
    
    lines = []
    for i, poi in enumerate(pois[:max_items], 1):
        if not isinstance(poi, dict):
            continue
        name = poi.get("name") or poi.get("place_name") or default_name
        
        # 🛡️ 距離安全防禦：整數化輸出，無距離則優雅省略，杜絕 KeyError
        dist = poi.get("distance")
        dist_str = ""
        if dist is not None:
            try:
                dist_str = f" ({int(round(float(dist)))}m)"
            except (ValueError, TypeError):
                dist_str = f" ({dist}m)"
                
        rating_str = f"⭐{poi.get('rating')}" if poi.get('rating') else ""
        hours_str = f" | {poi.get('opening_hours')}" if poi.get('opening_hours') else ""
        
        line = f"{i}. {name}{dist_str} {rating_str}{hours_str}".strip()
        lines.append(line)
    
    return "\n".join(lines) if lines else empty_msg


def get_ai_prompt_for_recommendation(
    pois_text: str,
    user_query: str,
    user_preferences: Optional[Dict] = None,
    locale: str = "zh"
) -> str:
    """
    生成給 Gemini 的精簡 prompt
    
    設計原則：
    - System prompt 固定、精簡
    - POI 資料已預處理
    - 用戶問題直接帶入
    """
    is_en = bool(locale and str(locale).strip().lower().startswith("en"))
    if is_en:
        preferences_str = ""
        if user_preferences:
            prefs = []
            if user_preferences.get("prefer_rating"):
                prefs.append("prefers high ratings")
            if user_preferences.get("prefer_distance"):
                prefs.append("prefers closer distance")
            if user_preferences.get("prefer_price"):
                prefs.append("budget-conscious")
            if prefs:
                preferences_str = f"\nUser preferences: {', '.join(prefs)}"

        return f"""You are a professional travel assistant. Answer the user's question based on the nearby places below.

Nearby Places:
{pois_text}
{preferences_str}

User Query: {user_query}

Provide a concise recommendation in natural English (under 80 words) explaining why."""

    preferences_str = ""
    if user_preferences:
        prefs = []
        if user_preferences.get("prefer_rating"):
            prefs.append("重視評分")
        if user_preferences.get("prefer_distance"):
            prefs.append("重視距離")
        if user_preferences.get("prefer_price"):
            prefs.append("重視價格")
        if prefs:
            preferences_str = f"\n用戶偏好：{', '.join(prefs)}"
    
    return f"""你是專業旅遊助手。根據以下附近地點資訊回答問題。

地點列表：
{pois_text}
{preferences_str}

用戶問題：{user_query}

請給出簡潔推薦（100字內），說明原因。"""


# ==================== WikiVoyage API ====================

WIKIVOYAGE_API = "https://en.wikivoyage.org/w/api.php"


async def search_wikivoyage(place_name: str, lang: str = "en", client: httpx.AsyncClient = None) -> Optional[Dict]:
    """
    透過 WikiVoyage MediaWiki API 搜索景點描述 (經由共享 Client 與 Semaphore)
    """
    # 🛡️ SSRF Protection: Validate language whitelist
    allowed_langs = {"en", "zh", "ja", "ko", "fr", "de", "es", "it", "ru", "pt"}
    if lang not in allowed_langs:
        print(f"[POI] Blocked potential SSRF attempt with invalid lang: {lang}")
        return None

    api_url = f"https://{lang}.wikivoyage.org/w/api.php"
    
    params = {
        "action": "query",
        "prop": "extracts",
        "exintro": "true",       # 只取摘要
        "explaintext": "true",   # 純文字 (非 HTML)
        "titles": place_name,
        "format": "json",
        "formatversion": "2"
    }
    
    start_time = time.time()
    try:
        headers = {
            "User-Agent": TABIJI_USER_AGENT,
            "Accept": "application/json"
        }
        
        async with WIKI_SEMAPHORE:
            # 🛡️ Anti-SSRF Guard
            if not is_safe_url(api_url):
                return None

            if client:
                response = await client.get(api_url, params=params, headers=headers, follow_redirects=True)
            else:
                async with httpx.AsyncClient(timeout=10.0) as temp_client:
                    response = await temp_client.get(api_url, params=params, headers=headers, follow_redirects=True)
            
            latency = time.time() - start_time
            latency_metric, _ = _get_poi_metrics()
            latency_metric.labels(source="wikivoyage").observe(latency)
            
            if response.status_code != 200:
                _, requests_metric = _get_poi_metrics()
                requests_metric.labels(source="wikivoyage", status="error").inc()
                print(f"WikiVoyage API error: {response.status_code}")
                return None
            
            _, requests_metric = _get_poi_metrics()
            requests_metric.labels(source="wikivoyage", status="success").inc()
            
            data = response.json()
            pages = data.get("query", {}).get("pages", [])
            
            if not pages:
                return None
            
            page = pages[0]
            if page.get("missing"):
                return None
            
            title = page.get("title", place_name)
            extract = page.get("extract", "")
            
            if len(extract) > 500:
                extract = extract[:500] + "..."
            
            return {
                "title": title,
                "description": extract,
                "url": f"https://{lang}.wikivoyage.org/wiki/{title.replace(' ', '_')}"
            }
            
    except Exception as e:
        print(f"WikiVoyage API error: {e}")
        return None


async def enrich_poi_with_wikivoyage(poi: Dict, lang: str = "en", client: httpx.AsyncClient = None) -> Dict:
    """
    用 WikiVoyage 資料豐富 POI 資訊 (共享 Client)
    """
    if not poi.get("name"):
        return poi
    
    wiki_data = await search_wikivoyage(poi["name"], lang, client=client)
    
    if wiki_data:
        poi["wikivoyage_description"] = wiki_data.get("description", "")
        poi["wikivoyage_url"] = wiki_data.get("url", "")
    
    return poi


# ==================== Wikipedia API (Multi-Signal Weighted Top-K) ====================

_CJK_ORTHO_MAP = str.maketrans({
    "鐵": "鉄", "铁": "鉄",
    "臺": "台",
    "廣": "広", "广": "広",
    "驛": "駅", "駅": "駅", "驿": "駅",
    "澀": "渋", "涩": "渋",
    "淺": "浅",
    "廳": "庁", "厅": "庁",
    "國": "国",
    "園": "園", "园": "園",
    "館": "館", "馆": "館",
    "廟": "廟", "庙": "廟",
    "樓": "楼",
    "橋": "橋", "桥": "橋",
    "島": "島", "岛": "島",
    "灣": "湾", "湾": "湾",
    "會": "会", "会": "会",
    "萬": "万",
    "龍": "竜", "龙": "竜",
    "櫻": "桜", "樱": "桜",
    "濱": "浜", "滨": "浜",
    "東": "东",
    "嵐": "岚",
    "閣": "阁",
    "銀": "银",
    "築": "筑",
    "關": "关",
    "橫": "横",
    "見": "见",
    "沖": "冲",
    "繩": "绳",
    "鳥": "鸟",
    "熱": "热",
    "長": "长",
    "華": "华",
    "陽": "阳",
    "雲": "云",
    "門": "门",
    "電": "电",
    "車": "车",
    "場": "场",
    "區": "区",
    "縣": "县",
    "鎮": "镇",
    "鄉": "乡",
    "寶": "宝",
    "聖": "圣",
    "溫": "温",
    "線": "线",
    "學": "学",
    "樂": "乐",
    "藝": "艺",
    "術": "术",
    "歷": "历",
    "觀": "观",
    "紀": "纪",
    "開": "开",
    "運": "运",
    "動": "动",
    "樹": "树",
    "風": "风",
    "飛": "飞",
    "機": "机",
    "雙": "双",
    "魚": "鱼",
    "麵": "面",
    "飯": "饭",
    "燒": "烧",
    "湯": "汤",
    "藥": "药",
    "妝": "妆",
    "書": "书",
    "紅": "红",
    "藍": "蓝",
    "綠": "绿",
    "黃": "黄",
    "黑": "黒",
    "馬": "马",
    "鶴": "鹤",
    "貓": "猫",
    "龜": "龟",
    "蓮": "莲",
    "蘭": "兰",
    "葉": "叶",
    "頭": "头",
    "頂": "顶",
    "嶺": "岭",
    "峽": "峡",
    "瀧": "滝",
    "澤": "沢",
    "邊": "边",
    "護": "护",
    "賀": "贺",
    "鴨": "鸭",
    "舊": "旧",
    "點": "点",
    "宮": "宫",
    "莊": "庄",
})

_DINING_OR_SHOP_TYPES = frozenset({
    "restaurant", "cafe", "bar", "pub", "fast_food", "food", "bakery",
    "shop", "supermarket", "convenience", "mall", "store", "izakaya", "ramen",
    "department_store", "pharmacy", "dining", "shopping",
})

_ADMIN_AREA_RE = re.compile(
    r"(?:行政區|行政区|特別區|特别区|町丁|丁目|地名|地區|地区|街道|自治體|自治体|"
    r"(?:^|[\s、，,])(?:區|区|市|町|村|郡|縣|县|府|都|車站|駅)$|"
    r"\b(?:neighborhood|neighbourhood|district|ward|municipality|town|locality|suburb|prefecture|city in|place in|station|quarter|borough)\b)",
    re.IGNORECASE,
)

_NON_PLACE_EVENT_RE = re.compile(
    r"(?:放火事件|縱火事件|纵火事件|事件|火災|火灾|事故|大屠殺|大屠杀|戰役|战役|戰爭|战争|空難|空难|"
    r"電影|电影|小說|小说|專輯|专辑|歌曲|單曲|单曲|電視劇|电视剧|動畫|动画|漫畫|漫画|"
    r"\b(?:arson|incident|massacre|battle|disaster|film|movie|novel|album|song|anime|manga|tv series)\b)",
    re.IGNORECASE,
)


def _poi_haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2.0) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2.0) ** 2
    return r * 2.0 * atan2(sqrt(a), sqrt(max(0.0, 1.0 - a)))


def _normalize_poi_title(text: str) -> str:
    if not text:
        return ""
    stripped = re.sub(r"\s*[\(（][^\)）]*[\)）]\s*", " ", str(text))
    nfkd = unicodedata.normalize("NFKD", stripped)
    no_marks = "".join(ch for ch in nfkd if unicodedata.category(ch) != "Mn")
    canon = no_marks.translate(_CJK_ORTHO_MAP).lower()
    return re.sub(r"[^a-z0-9\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]+", "", canon)


def _compute_name_similarity(query: str, candidate_title: str) -> float:
    q = _normalize_poi_title(query)
    t = _normalize_poi_title(candidate_title)
    if not q or not t:
        return 0.0
    if q == t:
        return 1.0

    min_len = min(len(q), len(t))
    max_len = max(len(q), len(t))
    len_ratio = min_len / max_len

    # Containment with length-ratio weighting (blocks short "東京" matching "東京塔攝影棚")
    if q in t or t in q:
        if min_len >= 3:
            return 0.25 + 0.75 * len_ratio
        return len_ratio

    def _bigrams(s: str) -> set:
        if len(s) < 2:
            return {s}
        return {s[i : i + 2] for i in range(len(s) - 1)}

    q_bi = _bigrams(q)
    t_bi = _bigrams(t)
    overlap = len(q_bi & t_bi)
    if overlap == 0:
        return 0.0
    dice = (2.0 * overlap) / (len(q_bi) + len(t_bi))
    return min(1.0, dice * (0.65 + 0.35 * len_ratio))


def _score_wiki_candidate(
    query: str,
    cand_title: str,
    *,
    poi_lat: Optional[float] = None,
    poi_lng: Optional[float] = None,
    cand_lat: Optional[float] = None,
    cand_lng: Optional[float] = None,
    poi_qid: Optional[str] = None,
    cand_qid: Optional[str] = None,
    poi_type: Optional[str] = None,
    cand_description: Optional[str] = None,
) -> Tuple[float, float, bool]:
    """
    Multi-signal weighted Top-K candidate scorer.
    Returns (score, name_similarity, qid_matched).
    """
    qid_match = bool(
        poi_qid and cand_qid and str(poi_qid).strip().upper() == str(cand_qid).strip().upper()
    )
    name_sim = _compute_name_similarity(query, cand_title)

    has_coords = (
        poi_lat is not None
        and poi_lng is not None
        and cand_lat is not None
        and cand_lng is not None
    )
    if has_coords:
        dist_km = _poi_haversine_km(float(poi_lat), float(poi_lng), float(cand_lat), float(cand_lng))
        if dist_km > 5.0 and not qid_match:
            return float("-inf"), name_sim, False
        dist_score = 40.0 * max(0.0, 1.0 - dist_km / 5.0)
        name_score = 60.0 * name_sim
        score = (100.0 if qid_match else 0.0) + name_score + dist_score
    else:
        # Proportional normalization when coordinates are absent so exact/strong matches pass >= 55
        name_score = 100.0 * name_sim
        score = (100.0 if qid_match else 0.0) + name_score

    norm_type = (poi_type or "").strip().lower()
    desc_and_title = f"{cand_title or ''} {cand_description or ''}"
    if norm_type in _DINING_OR_SHOP_TYPES and not qid_match and name_sim < 0.85:
        if _ADMIN_AREA_RE.search(desc_and_title):
            score -= 40.0

    # Penalize historical events / arson / media articles (e.g. 金閣寺 -> 金閣寺放火事件)
    # unless the user explicitly searched for an event/media title.
    if not qid_match and not _NON_PLACE_EVENT_RE.search(query or "") and _NON_PLACE_EVENT_RE.search(desc_and_title):
        score -= 45.0

    return score, name_sim, qid_match


def _is_wiki_candidate_admitted(score: float, name_sim: float, qid_match: bool) -> bool:
    return score >= 55.0 and (qid_match or name_sim >= 0.35)


async def _fetch_wiki_page_summary(
    title: str,
    lang: str,
    headers: Dict[str, str],
    client: Optional[httpx.AsyncClient] = None,
) -> Optional[Dict[str, Any]]:
    clean_name = title.strip().replace(" ", "_")
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(clean_name, safe='')}"
    if not is_safe_url(url):
        return None
    start_time = time.time()
    async with WIKI_SEMAPHORE:
        if client:
            response = await client.get(url, headers=headers, follow_redirects=True)
        else:
            async with httpx.AsyncClient(timeout=10.0) as temp_client:
                response = await temp_client.get(url, headers=headers, follow_redirects=True)
        latency = time.time() - start_time
        latency_metric, requests_metric = _get_poi_metrics()
        latency_metric.labels(source="wikipedia").observe(latency)
        if response.status_code == 200:
            requests_metric.labels(source="wikipedia", status="success").inc()
            return response.json()
        requests_metric.labels(source="wikipedia", status="error").inc()
        return None


async def get_wikipedia_summary(
    name: str,
    lang: str = "zh",
    client: httpx.AsyncClient = None,
    is_retry: bool = False,
    lat: float = None,
    lng: float = None,
    wikidata_id: Optional[str] = None,
    poi_type: Optional[str] = None,
) -> tuple[str, str]:
    """
    從 Wikipedia 獲取景點簡介 (200 字以內，多維權重 Top-K 消歧，共享 Client 與 Semaphore)
    """
    # 🛡️ SSRF Protection: Validate language whitelist
    allowed_langs = {"en", "zh", "ja", "ko", "fr", "de", "es", "it", "ru", "pt"}
    if lang not in allowed_langs:
        print(f"[POI] Blocked potential SSRF attempt with invalid Wikipedia lang: {lang}")
        return "", ""

    headers = {
        "User-Agent": TABIJI_USER_AGENT,
        "Accept": "application/json",
    }
    if lang == "zh":
        headers["Accept-Language"] = "zh-TW,zh-Hant;q=0.9,zh;q=0.8"

    variant_q = "&variant=zh-tw" if lang == "zh" else ""

    try:
        # Direct Sitelink / Top-1 Fetch Mode (is_retry=True): bypass geosearch directly
        if is_retry:
            data = await _fetch_wiki_page_summary(name, lang, headers, client=client)
            if data and data.get("type") != "disambiguation":
                extract = data.get("extract", "") or ""
                image_url = _pick_hd_wiki_image(data)
                if extract:
                    return (extract[:200] if len(extract) > 200 else extract), image_url
            return "", ""

        # Step 1: Direct Title Summary Lookup FIRST (with multi-signal distance/name/type validation)
        direct_data = await _fetch_wiki_page_summary(name, lang, headers, client=client)
        if direct_data and direct_data.get("type") == "disambiguation" and lat is not None and lng is not None:
            # Step 1.5: Resolve disambiguation page (e.g., 金閣寺 -> 鹿苑寺) via batched outgoing links + coordinates
            links_url = (
                f"https://{lang}.wikipedia.org/w/api.php"
                f"?action=query&titles={quote(name.strip(), safe='')}&generator=links&gpllimit=50&gplnamespace=0"
                f"&prop=coordinates|pageprops|description&redirects=1{variant_q}&format=json&formatversion=2"
            )
            if is_safe_url(links_url):
                try:
                    async with WIKI_SEMAPHORE:
                        if client:
                            links_resp = await client.get(links_url, headers=headers)
                        else:
                            async with httpx.AsyncClient(timeout=5.0) as temp_client:
                                links_resp = await temp_client.get(links_url, headers=headers)
                    if links_resp.status_code == 200:
                        link_pages = (links_resp.json().get("query") or {}).get("pages") or []
                        best_disambig_title: Optional[str] = None
                        best_disambig_dist = 1.51  # strict 1.5km geographic disambiguation match
                        norm_type = (poi_type or "").strip().lower()
                        for lp in link_pages:
                            if not isinstance(lp, dict) or lp.get("missing"):
                                continue
                            lt = str(lp.get("title") or "").strip()
                            ld = str(lp.get("description") or "")
                            coords_list = lp.get("coordinates") or []
                            if not lt or not coords_list:
                                continue
                            fc = coords_list[0] if isinstance(coords_list, list) else {}
                            c_lat, c_lng = fc.get("lat"), fc.get("lon")
                            if c_lat is None or c_lng is None:
                                continue
                            if not _NON_PLACE_EVENT_RE.search(name) and _NON_PLACE_EVENT_RE.search(f"{lt} {ld}"):
                                continue
                            if norm_type in _DINING_OR_SHOP_TYPES and _ADMIN_AREA_RE.search(f"{lt} {ld}"):
                                continue
                            d_km = _poi_haversine_km(float(lat), float(lng), float(c_lat), float(c_lng))
                            if d_km < best_disambig_dist:
                                best_disambig_dist = d_km
                                best_disambig_title = lt
                        if best_disambig_title:
                            print(f"📍 [Wiki Disambig] Resolved '{name}' -> '{best_disambig_title}' ({best_disambig_dist:.2f} km)")
                            res_disambig = await get_wikipedia_summary(
                                best_disambig_title,
                                lang=lang,
                                client=client,
                                is_retry=True,
                                lat=None,
                                lng=None,
                                wikidata_id=wikidata_id,
                                poi_type=poi_type,
                            )
                            if res_disambig[0]:
                                return res_disambig
                except Exception as disambig_err:
                    print(f"⚠️ [Wiki Disambig] Failed for '{name}': {disambig_err}")

        if direct_data and direct_data.get("type") != "disambiguation":
            raw_display = re.sub(r"<[^>]+>", "", str(direct_data.get("displaytitle") or "")).strip()
            cand_title = raw_display or direct_data.get("title") or name
            cand_coords = direct_data.get("coordinates") or {}
            cand_lat = cand_coords.get("lat")
            cand_lng = cand_coords.get("lon")
            cand_qid = direct_data.get("wikibase_item")
            cand_desc = direct_data.get("description") or ""
            score, name_sim, qid_match = _score_wiki_candidate(
                name,
                cand_title,
                poi_lat=lat,
                poi_lng=lng,
                cand_lat=cand_lat,
                cand_lng=cand_lng,
                poi_qid=wikidata_id,
                cand_qid=cand_qid,
                poi_type=poi_type,
                cand_description=cand_desc,
            )
            if _is_wiki_candidate_admitted(score, name_sim, qid_match):
                extract = direct_data.get("extract", "") or ""
                image_url = _pick_hd_wiki_image(direct_data)
                if extract:
                    return (extract[:200] if len(extract) > 200 else extract), image_url

        # Step 2: Single Batched Geosearch (generator=geosearch&prop=coordinates|pageprops|description)
        # Scores all candidates in-memory and makes at most ONE page/summary call for the winning Top-1.
        if lat is not None and lng is not None:
            geo_url = (
                f"https://{lang}.wikipedia.org/w/api.php"
                f"?action=query&generator=geosearch&ggscoord={lat}|{lng}&ggsradius=1000&ggslimit=10"
                f"&prop=coordinates|pageprops|description{variant_q}&format=json&formatversion=2"
            )
            if is_safe_url(geo_url):
                try:
                    async with WIKI_SEMAPHORE:
                        if client:
                            geo_resp = await client.get(geo_url, headers=headers)
                        else:
                            async with httpx.AsyncClient(timeout=5.0) as temp_client:
                                geo_resp = await temp_client.get(geo_url, headers=headers)

                    if geo_resp.status_code == 200:
                        geo_data = geo_resp.json()
                        pages = geo_data.get("query", {}).get("pages", []) or []
                        best_title: Optional[str] = None
                        best_score = float("-inf")
                        for page in pages:
                            if not isinstance(page, dict) or page.get("missing"):
                                continue
                            cand_title = str(page.get("title") or "").strip()
                            if not cand_title:
                                continue
                            coords_list = page.get("coordinates") or []
                            first_coord = coords_list[0] if isinstance(coords_list, list) and coords_list else {}
                            cand_lat = first_coord.get("lat")
                            cand_lng = first_coord.get("lon")
                            cand_qid = (page.get("pageprops") or {}).get("wikibase_item")
                            cand_desc = page.get("description") or ""
                            score, name_sim, qid_match = _score_wiki_candidate(
                                name,
                                cand_title,
                                poi_lat=lat,
                                poi_lng=lng,
                                cand_lat=cand_lat,
                                cand_lng=cand_lng,
                                poi_qid=wikidata_id,
                                cand_qid=cand_qid,
                                poi_type=poi_type,
                                cand_description=cand_desc,
                            )
                            if _is_wiki_candidate_admitted(score, name_sim, qid_match) and score > best_score:
                                best_score = score
                                best_title = cand_title

                        if best_title:
                            print(f"📍 [Wiki Top-K Geosearch] Winning Top-1: {best_title} (score={best_score:.1f})")
                            res_top1 = await get_wikipedia_summary(
                                best_title,
                                lang=lang,
                                client=client,
                                is_retry=True,
                                lat=None,
                                lng=None,
                                wikidata_id=wikidata_id,
                                poi_type=poi_type,
                            )
                            if res_top1[0]:
                                return res_top1
                except Exception as e:
                    print(f"⚠️ [Wiki Geosearch] Batched Top-K lookup failed: {e}")

        # Step 3: Strict OpenSearch Fallback (limit=6 so regional parentheticals like 嵐山 (京都市) are not truncated)
        search_url = f"https://{lang}.wikipedia.org/w/api.php?action=opensearch&search={quote(name, safe='')}&limit=6{variant_q}&format=json"
        if is_safe_url(search_url):
            try:
                async with WIKI_SEMAPHORE:
                    if client:
                        search_resp = await client.get(search_url, headers=headers)
                    else:
                        async with httpx.AsyncClient(timeout=5.0) as temp_client:
                            search_resp = await temp_client.get(search_url, headers=headers)

                if search_resp.status_code == 200:
                    search_data = search_resp.json()
                    cand_titles = search_data[1] if len(search_data) > 1 and isinstance(search_data[1], list) else []
                    for cand_title in cand_titles[:6]:
                        if _compute_name_similarity(name, cand_title) < 0.6:
                            continue
                        os_data = await _fetch_wiki_page_summary(cand_title, lang, headers, client=client)
                        if not os_data or os_data.get("type") == "disambiguation":
                            continue
                        os_coords = os_data.get("coordinates") or {}
                        raw_os_disp = re.sub(r"<[^>]+>", "", str(os_data.get("displaytitle") or "")).strip()
                        score, name_sim, qid_match = _score_wiki_candidate(
                            name,
                            raw_os_disp or os_data.get("title") or cand_title,
                            poi_lat=lat,
                            poi_lng=lng,
                            cand_lat=os_coords.get("lat"),
                            cand_lng=os_coords.get("lon"),
                            poi_qid=wikidata_id,
                            cand_qid=os_data.get("wikibase_item"),
                            poi_type=poi_type,
                            cand_description=os_data.get("description") or "",
                        )
                        if _is_wiki_candidate_admitted(score, name_sim, qid_match):
                            extract = os_data.get("extract", "") or ""
                            image_url = _pick_hd_wiki_image(os_data)
                            if extract:
                                return (extract[:200] if len(extract) > 200 else extract), image_url
            except Exception as search_err:
                print(f"⚠️ [Wiki Search] Fallback search failed for '{name}': {search_err}")
    except Exception as e:
        _, requests_metric = _get_poi_metrics()
        requests_metric.labels(source="wikipedia", status="exception").inc()
        print(f"Wikipedia API error ({lang}): {e}")

    # Step 4: Language fallback: zh -> ja -> en
    fallback_order = {"zh": "ja", "ja": "en"}
    if lang in fallback_order:
        return await get_wikipedia_summary(
            name,
            fallback_order[lang],
            client=client,
            lat=lat,
            lng=lng,
            wikidata_id=wikidata_id,
            poi_type=poi_type,
        )

    return "", ""


# ==================== Wikidata API ====================

async def get_wikidata_labels(wikidata_id: str, client: httpx.AsyncClient = None) -> Optional[Dict]:
    """
    從 Wikidata 獲取多語言 labels 和結構化資料 (共享 Client 與 Semaphore)
    """
    if not re.match(r"^Q\d+$", wikidata_id):
        return None

    start_time = time.time()
    try:
        url = f"https://www.wikidata.org/wiki/Special:EntityData/{wikidata_id}.json"
        if not is_safe_url(url):
            return None

        headers = {
            "User-Agent": TABIJI_USER_AGENT
        }
        
        async with WIKI_SEMAPHORE:
            if client:
                response = await client.get(url, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=5.0) as temp_client:
                    response = await temp_client.get(url, headers=headers)
            
            latency = time.time() - start_time
            latency_metric, _ = _get_poi_metrics()
            latency_metric.labels(source="wikidata").observe(latency)
                    
            if response.status_code != 200:
                _, requests_metric = _get_poi_metrics()
                requests_metric.labels(source="wikidata", status="error").inc()
                print(f"⚠️ Wikidata API returned {response.status_code} for {wikidata_id}")
                return None
            
            _, requests_metric = _get_poi_metrics()
            requests_metric.labels(source="wikidata", status="success").inc()
            
            data = response.json()
            # 支援 entities 結構抓取
            entities = data.get("entities", {})
            entity = entities.get(wikidata_id, {})
            if not entity:
                # 有時返回的 key 可能不同或層級有差，做個保險
                if entities:
                    first_key = list(entities.keys())[0]
                    entity = entities[first_key]
            
            # 解析多語言 labels
            labels_raw = entity.get("labels", {})
            labels = {}
            # 支援更多 BCP 47 變體
            for lang in ["zh-tw", "zh-hant", "zh-hk", "zh", "ja", "en", "ko"]:
                if lang in labels_raw:
                    # 規範化 key
                    key = lang
                    if lang in ["zh-tw", "zh-hant"]: key = "zh-TW"
                    elif lang == "zh-hk": key = "zh-HK"
                    elif lang == "zh": key = "zh-CN"
                    elif lang == "ja": key = "ja-JP"
                    elif lang == "en": key = "en-US"
                    elif lang == "ko": key = "ko-KR"
                    
                    if key not in labels:
                        labels[key] = labels_raw[lang].get("value", "")
            
            claims = entity.get("claims", {})
            website = ""
            if "P856" in claims:
                website = claims["P856"][0].get("mainsnak", {}).get("datavalue", {}).get("value", "")
            
            opening_hours = ""
            if "P3025" in claims:
                opening_hours = claims["P3025"][0].get("mainsnak", {}).get("datavalue", {}).get("value", "")
            
            # 解析 Sitelinks (全域抓取支援 Phase 5.2 翻譯鏈)
            sitelinks_raw = entity.get("sitelinks", {})
            sitelinks = {k: v.get("title", "") for k, v in sitelinks_raw.items()}
            
            # P18: 核心高畫質圖源
            wikidata_image = ""
            if "P18" in claims:
                wikidata_image = claims["P18"][0].get("mainsnak", {}).get("datavalue", {}).get("value", "")
            
            return {
                "labels": labels,
                "sitelinks": sitelinks,
                "website": website,
                "opening_hours": opening_hours,
                "wikidata_image": wikidata_image # 🆕 Phase 5.1.1
            }
            
    except Exception as e:
        print(f"Wikidata API error: {e}")
        return None


# ==================== 三源整合 ====================

async def enrich_poi_complete(poi: Dict, client: httpx.AsyncClient = None, lang: str = "zh") -> Dict:
    """
    三源互補整合：Wikidata + Wikipedia + WikiVoyage (2026 Phase 1 Parallel)
    """
    name = poi.get("name", "")
    wikidata_id = poi.get("wikidata_id", "")
    
    if not name:
        return poi

    is_en = bool(str(lang or "zh").strip().lower().startswith("en"))
    wiki_lang = "en" if is_en else "zh"
    used_fallback_lang = None
    
    poi["warnings"] = []
    poi["status"] = "SUCCESS"
    poi["resolved_language"] = "en" if is_en else "zh-TW" # Default per requested locale
    poi["image_url"] = ""              # 🆕 Phase 5.3.1 Safety Init
    
    lat = poi.get("lat")
    lng = poi.get("lng")
    poi_type = poi.get("type") or ""
    
    # 並行與分層查詢：當具 Wikidata QID 時優先解析 Sitelinks 精準鎖定百科（is_retry=True 繞過 Geosearch）
    try:
        wikidata_result = None
        wikivoyage_result = None
        wikipedia_result = ""
        wikipedia_image = ""
        res1: Any = None

        if wikidata_id:
            wd_task = asyncio.wait_for(get_wikidata_labels(wikidata_id, client=client), 6.0)
            wv_task = asyncio.wait_for(search_wikivoyage(name, lang=wiki_lang, client=client), 6.0)
            res0, res2 = await asyncio.gather(wd_task, wv_task, return_exceptions=True)

            if isinstance(res0, asyncio.TimeoutError):
                poi["warnings"].append("WIKIDATA_TIMEOUT")
                if poi["status"] == "SUCCESS": poi["status"] = "PARTIAL_SUCCESS"
            elif isinstance(res0, Exception):
                poi["warnings"].append("WIKIDATA_ERROR")
                if poi["status"] == "SUCCESS": poi["status"] = "PARTIAL_SUCCESS"
            else:
                wikidata_result = res0

            # Priority 1: Wikidata QID Sitelink (direct page/summary with is_retry=True, never falls back into Geosearch)
            if wikidata_result:
                sitelinks = wikidata_result.get("sitelinks", {}) or {}
                priority_links = (
                    [("enwiki", "en"), ("jawiki", "ja"), ("zhwiki", "zh")]
                    if is_en
                    else [("zhwiki", "zh"), ("jawiki", "ja"), ("enwiki", "en")]
                )
                best_title = ""
                target_lang = wiki_lang
                for link_key, link_lang in priority_links:
                    if sitelinks.get(link_key):
                        best_title = sitelinks[link_key]
                        target_lang = link_lang
                        break
                if not best_title and sitelinks:
                    valid_wikis = [k for k in sitelinks.keys() if k.endswith("wiki") and not k.startswith("commons")]
                    if valid_wikis:
                        wiki_key = valid_wikis[0]
                        best_title = sitelinks[wiki_key]
                        target_lang = wiki_key.replace("wiki", "")
                        print(f"🌍 [Global Sitelink] Using {target_lang} Wikipedia: {best_title}")

                if best_title:
                    try:
                        res_sl = await asyncio.wait_for(
                            get_wikipedia_summary(
                                best_title,
                                lang=target_lang,
                                client=client,
                                is_retry=True,
                                lat=None,
                                lng=None,
                                wikidata_id=wikidata_id,
                                poi_type=poi_type,
                            ),
                            4.0,
                        )
                        if isinstance(res_sl, tuple):
                            wikipedia_result, wikipedia_image = res_sl
                        else:
                            wikipedia_result = res_sl or ""
                        if wikipedia_result and not target_lang.startswith(wiki_lang):
                            used_fallback_lang = target_lang
                            poi["resolved_language"] = target_lang
                    except asyncio.TimeoutError:
                        res1 = asyncio.TimeoutError()
                        poi["warnings"].append("WIKIPEDIA_TIMEOUT")
                        if poi["status"] == "SUCCESS": poi["status"] = "PARTIAL_SUCCESS"
                    except Exception:
                        pass

            # Fallback if QID had no usable sitelink: run Top-K get_wikipedia_summary
            if not wikipedia_result and not isinstance(res1, asyncio.TimeoutError):
                try:
                    res1 = await asyncio.wait_for(
                        get_wikipedia_summary(
                            name,
                            lang=wiki_lang,
                            client=client,
                            lat=lat,
                            lng=lng,
                            wikidata_id=wikidata_id,
                            poi_type=poi_type,
                        ),
                        6.0,
                    )
                    if isinstance(res1, tuple):
                        wikipedia_result, wikipedia_image = res1
                    else:
                        wikipedia_result = res1 or ""
                except asyncio.TimeoutError as te:
                    res1 = te
                    poi["warnings"].append("WIKIPEDIA_TIMEOUT")
                    if poi["status"] == "SUCCESS": poi["status"] = "PARTIAL_SUCCESS"
                except Exception:
                    pass
        else:
            tasks = [
                asyncio.wait_for(
                    get_wikipedia_summary(
                        name,
                        lang=wiki_lang,
                        client=client,
                        lat=lat,
                        lng=lng,
                        wikidata_id="",
                        poi_type=poi_type,
                    ),
                    6.0,
                ),
                asyncio.wait_for(search_wikivoyage(name, lang=wiki_lang, client=client), 6.0),
            ]
            res1, res2 = await asyncio.gather(*tasks, return_exceptions=True)

            if isinstance(res1, asyncio.TimeoutError):
                poi["warnings"].append("WIKIPEDIA_TIMEOUT")
                if poi["status"] == "SUCCESS": poi["status"] = "PARTIAL_SUCCESS"
            elif isinstance(res1, Exception):
                pass
            else:
                if isinstance(res1, tuple):
                    wikipedia_result, wikipedia_image = res1
                else:
                    wikipedia_result = res1 or ""

        # 最終 Wikipedia 狀態判定與 Warning 固定
        if not wikipedia_result:
            if not isinstance(res1, asyncio.TimeoutError):
                poi["warnings"].append("WIKIPEDIA_NOT_FOUND")
            if poi["status"] == "SUCCESS": poi["status"] = "PARTIAL_SUCCESS"
        else:
            if not wikipedia_result.strip():
                poi["warnings"].append("WIKIPEDIA_EMPTY")
            
        # 3. 處理 WikiVoyage 結果
        if isinstance(res2, asyncio.TimeoutError):
            poi["warnings"].append("WIKIVOYAGE_TIMEOUT")
        elif isinstance(res2, Exception):
            poi["warnings"].append("WIKIVOYAGE_ERROR")
        else:
            wikivoyage_result = res2
        
        if wikidata_result:
            # 🆕 Phase 5.1.3: Wikidata Image Fallback (URL-encode filename to protect #/& characters; 960px Wikimedia standard)
            if not poi.get("image_url") and wikidata_result.get("wikidata_image"):
                img_name = wikidata_result["wikidata_image"].replace(" ", "_")
                poi["image_url"] = f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(img_name, safe='')}?width=960"

            labels = wikidata_result.get("labels", {})
            ja_name = labels.get("ja-JP", "")
            en_name = labels.get("en-US", "")
            zh_name = labels.get("zh-TW") or labels.get("zh-HK") or labels.get("zh-CN") or ""

            if is_en:
                primary = en_name or zh_name or name
                if not used_fallback_lang:
                    poi["resolved_language"] = "en"
                secondary_parts = []
                if ja_name and ja_name != primary: secondary_parts.append(ja_name)
                if zh_name and zh_name != primary: secondary_parts.append(f"({zh_name})")
            else:
                # BCP 47 優先權
                primary = labels.get("zh-TW") or labels.get("zh-HK") or labels.get("zh-CN") or name
                if not used_fallback_lang:
                    poi["resolved_language"] = "zh-TW" # 能查到 Wikidata 預設視為繁中處理
                secondary_parts = []
                if ja_name and ja_name != primary: secondary_parts.append(ja_name)
                if en_name: secondary_parts.append(f"({en_name})")
            
            poi["display_name"] = {
                "primary": primary,
                "secondary": " ".join(secondary_parts) if secondary_parts else ""
            }
            
            if wikidata_result.get("website"):
                poi["official_url"] = wikidata_result["website"]
            if wikidata_result.get("opening_hours"):
                poi["wikidata_hours"] = wikidata_result["opening_hours"]
        else:
            if wikidata_id:
                poi["warnings"].append("WIKIDATA_NOT_FOUND")
                poi["status"] = "PARTIAL_SUCCESS"

        # Wikipedia 文化描述
        if wikipedia_result:
            poi["cultural_desc"] = wikipedia_result
            if wikipedia_image:
                poi["image_url"] = wikipedia_image # 🆕 Phase 5.3.3: Store image
        else:
            # Warning 已經在前面 Logic 分支中處理過 WIKIPEDIA_TIMEOUT/NOT_FOUND
            if poi["status"] == "SUCCESS": poi["status"] = "PARTIAL_SUCCESS"
        
        # WikiVoyage 旅遊指南
        if wikivoyage_result:
            poi["travel_tips"] = wikivoyage_result.get("description", "")
            if wikivoyage_result.get("url"):
                poi["wikivoyage_url"] = wikivoyage_result["url"]
        else:
            poi["warnings"].append("WIKIVOYAGE_EMPTY")

        # 最終失敗判定
        if poi["status"] == "SUCCESS" and not wikidata_result and not wikipedia_result and not wikivoyage_result:
            poi["status"] = "FAILED"
        
    except Exception as e:
        print(f"enrich_poi_complete error: {e}")
        poi["status"] = "FAILED"
    
    return poi


def format_enriched_poi_for_ai(poi: Dict, locale: str = "zh") -> str:
    """
    將豐富後的 POI 格式化為 AI 可讀文字
    """
    is_en = bool(locale and str(locale).strip().lower().startswith("en"))
    lines = []
    
    # 名稱 (主標題 + 副標題)
    display = poi.get("display_name", {})
    if display:
        name_line = display.get("primary", poi.get("name", ""))
        if display.get("secondary"):
            name_line += f" {display['secondary']}"
        lines.append(f"📍 {name_line}")
    else:
        lines.append(f"📍 {poi.get('name', '')}")
    
    # 文化描述
    if poi.get("cultural_desc"):
        lines.append(f"📖 {poi['cultural_desc']}")
    
    # 旅遊指南
    if poi.get("travel_tips"):
        lines.append(f"🧳 {poi['travel_tips'][:150]}...")
    
    # 官方連結
    if poi.get("official_url"):
        label = "Official Site" if is_en else "官網"
        lines.append(f"🔗 {label}: {poi['official_url']}")
    
    return "\n".join(lines)


def get_source_urls(poi: Dict, place_name: str, locale: str = "zh") -> list:
    """
    🆕 v3.7.1: 提取來源 URLs 用於前端引用標示
    
    Returns:
        [
            {"title": "Wikipedia: 金閣寺", "url": "https://..."},
            {"title": "WikiVoyage: 金閣寺", "url": "https://..."}
        ]
    """
    is_en = bool(locale and str(locale).strip().lower().startswith("en"))
    sources = []
    
    # Wikipedia 來源
    if poi.get("cultural_desc"):
        wiki_host = "en.wikipedia.org" if is_en else "zh.wikipedia.org"
        wiki_url = f"https://{wiki_host}/wiki/{quote(place_name)}"
        sources.append({
            "title": f"Wikipedia: {place_name}",
            "url": wiki_url
        })
    
    # WikiVoyage 來源
    if poi.get("wikivoyage_url"):
        sources.append({
            "title": f"WikiVoyage: {place_name}",
            "url": poi["wikivoyage_url"]
        })
    
    # 官方網站
    if poi.get("official_url"):
        sources.append({
            "title": "Official Website" if is_en else "官方網站",
            "url": poi["official_url"]
        })
    
    return sources


async def execute_resilient_nearby_search(
    anchor_place: str,
    category: str = "restaurant",
    keyword: str = "",
    radius_meters: int = 500,
    locale: str = "zh"
) -> List[Dict[str, Any]]:
    """
    🌐 2026 雙軌韌性周邊搜尋執行器 (執行於伺服端 First-Pass 工具調用中)
    1. 驗證 anchor_place 防禦 SSRF 與超長字串
    2. 調用 Photon 毫秒級定位真實經緯度 (杜絕 Null Island)
    3. 清洗 keyword 防禦 Overpass QL 注入
    4. 呼叫 search_poi_combined (帶 3.0s 嚴格超時熔斷)
    5. 壓縮輸出 Top 4 地點，杜絕 Token 浪費
    """
    import math
    clean_anchor = (anchor_place or "").strip()
    if not clean_anchor or len(clean_anchor) > 120:
        return []
        
    # SSRF 與協議守衛
    if re.search(r'^(https?://|ftp://|file://|//|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', clean_anchor, re.I):
        return []
    if "169.254.169.254" in clean_anchor or "metadata.google.internal" in clean_anchor:
        return []

    # 1. 座標錨定 (優先 Photon)
    lat, lng = None, None
    try:
        from services.geocode_service import geocode_with_photon
        photon_res = await geocode_with_photon(clean_anchor, limit=1)
        if photon_res and len(photon_res) > 0:
            first = photon_res[0]
            lat = first.get("lat")
            lng = first.get("lng")
    except Exception as geo_err:
        logger.warning(f"[NearbySearch] Photon anchor lookup failed for '{clean_anchor}': {geo_err}")

    if lat is None or lng is None:
        return []

    # 座標數值與 Null Island 防禦
    try:
        f_lat = float(lat)
        f_lng = float(lng)
    except (TypeError, ValueError):
        return []

    if not math.isfinite(f_lat) or not math.isfinite(f_lng):
        return []
    if not (-90.0 <= f_lat <= 90.0) or not (-180.0 <= f_lng <= 180.0):
        return []
    if abs(f_lat) < 1e-5 and abs(f_lng) < 1e-5:
        return []

    # 2. 清洗關鍵字
    clean_kw = sanitize_overpass_keyword(keyword)
    safe_radius = max(100, min(int(radius_meters), 1500))

    # 3. 雙軌查詢 (優先嘗試 search_poi_combined，單次受控逾時 2.5s / 外層 4.0s)
    raw_pois = []
    try:
        raw_pois = await asyncio.wait_for(
            search_poi_combined(f_lat, f_lng, category=category, radius=safe_radius, timeout=2.5),
            timeout=4.0
        )
    except Exception as search_err:
        logger.warning(f"[NearbySearch] search_poi_combined timeout/error: {search_err}")
        raw_pois = []

    is_en = bool(locale and str(locale).strip().lower().startswith("en"))
    # 🛡️ 關鍵極速兜底：若仍為空，立即啟動 Photon bbox 限定與距離過濾查詢
    if not raw_pois:
        try:
            # 依關鍵字與類別判斷最佳 osm_tag 與 search_term (相容台灣、日本與歐美跨國圖資，含中英關鍵字清洗)
            clean_kw = sanitize_overpass_keyword(keyword)
            osm_tag = None
            term = clean_kw or category
            term_lower = term.lower()
            
            # 智能映射 OSM Tag 與清洗通用虛詞
            if category in ["restaurant", "food"] or any(k in term_lower for k in ["拉麵", "美食", "餐廳", "小吃", "飯", "麵", "ramen", "food", "restaurant", "dining"]):
                osm_tag = "amenity:restaurant"
                term = clean_kw if clean_kw and term_lower not in ["美食", "特色美食", "必吃美食", "food", "restaurant", "dining"] else "restaurant"
            elif category == "cafe" or any(k in term_lower for k in ["咖啡", "cafe", "coffee"]):
                osm_tag = "amenity:cafe"
                term = clean_kw if clean_kw and term_lower not in ["咖啡", "cafe", "coffee"] else "cafe"
            elif category in ["attraction", "sightseeing"] or any(k in term_lower for k in ["景點", "必訪", "好玩", "參觀", "attraction", "sightseeing", "spots"]):
                osm_tag = "tourism:attraction"
                term = clean_kw if clean_kw and term_lower not in ["景點", "必訪景點", "attraction", "sightseeing", "spots"] else "attraction"
            elif category == "pharmacy" or any(k in term_lower for k in ["藥局", "藥妝", "藥店", "pharmacy", "drugstore"]):
                osm_tag = "amenity:pharmacy"
                term = clean_kw if clean_kw and term_lower not in ["藥局", "藥妝", "pharmacy", "drugstore"] else "pharmacy"
            elif category == "convenience" or any(k in term_lower for k in ["超商", "便利", "便利店", "便利商店", "convenience"]):
                osm_tag = "shop:convenience"
                term = clean_kw if clean_kw and term_lower not in ["超商", "便利店", "convenience"] else "convenience"

            user_agent = os.getenv("APP_USER_AGENT", "TabidachiTravelApp/2.0 (contact@tabidachi.app)")
            max_dist_m = max(safe_radius * 4, 6000)
            delta_lat = max_dist_m / 111320.0
            delta_lng = delta_lat / max(abs(cos(radians(f_lat))), 0.2)
            bbox_str = f"{f_lng - delta_lng:.6f},{f_lat - delta_lat:.6f},{f_lng + delta_lng:.6f},{f_lat + delta_lat:.6f}"
            params = {
                "q": term,
                "lat": f_lat,
                "lon": f_lng,
                "bbox": bbox_str,
                "limit": 6
            }
            if osm_tag:
                params["osm_tag"] = osm_tag

            default_nearby_name = "Unknown Place" if is_en else "周邊設施"
            async with httpx.AsyncClient(timeout=3.0, headers={"User-Agent": user_agent}) as client:
                photon_resp = await client.get("https://photon.komoot.io/api/", params=params)
                p_data = photon_resp.json() if photon_resp.status_code == 200 else {}
                
                # 🛡️ 容錯雙軌：若帶特定 osm_tag 查無資料，自動去除 osm_tag 重試廣域查詢
                if not p_data.get("features") and osm_tag:
                    fallback_resp = await client.get(
                        "https://photon.komoot.io/api/",
                        params={"q": clean_kw or category, "lat": f_lat, "lon": f_lng, "bbox": bbox_str, "limit": 6}
                    )
                    if fallback_resp.status_code == 200:
                        p_data = fallback_resp.json()

                for f in p_data.get("features", []):
                    props = f.get("properties", {})
                    coords = f.get("geometry", {}).get("coordinates", [])
                    if len(coords) >= 2:
                        poi_lng, poi_lat = coords[0], coords[1]
                        dist = round(haversine_distance(f_lat, f_lng, poi_lat, poi_lng))
                        if dist > max_dist_m:
                            continue
                        raw_pois.append({
                            "name": props.get("name") or props.get("street") or default_nearby_name,
                            "category": category,
                            "lat": poi_lat,
                            "lng": poi_lng,
                            "distance": dist,
                            "rating": None,
                            "source": "photon"
                        })
        except Exception as photon_err:
            logger.warning(f"[NearbySearch] Photon fallback error: {photon_err}")

    # 4. 若有特定關鍵字，進行本機模糊篩選
    filtered = []
    if clean_kw:
        for p in raw_pois:
            name = p.get("name", "")
            desc = p.get("desc", "")
            if clean_kw.lower() in name.lower() or clean_kw.lower() in desc.lower():
                filtered.append(p)
    if not filtered:
        filtered = raw_pois

    # 5. 格式壓縮輸出 Top 4 地點 (剔除多邊形與雜項頂點)
    unnamed_label = "Unnamed Place" if is_en else "未命名設施"
    compact_results = []
    for item in filtered[:4]:
        p_lat = item.get("lat")
        p_lng = item.get("lng")
        if p_lat is None or p_lng is None:
            continue
        compact_results.append({
            "name": item.get("name", unnamed_label),
            "category": item.get("category", category),
            "lat": round(float(p_lat), 6),
            "lng": round(float(p_lng), 6),
            "distance_m": int(item.get("distance", 0)),
            "rating": round(float(item["rating"]), 1) if item.get("rating") else None
        })

    return compact_results

