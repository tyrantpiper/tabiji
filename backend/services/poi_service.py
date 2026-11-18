"""
POI 服務層 - 整合 OSM Overpass + OpenTripMap API
提供附近設施搜索功能，並優化 AI Token 消耗
"""

import os
import httpx
import asyncio
import re
from typing import List, Dict, Optional, Any, Tuple
from math import radians, cos, sin, sqrt, atan2
from urllib.parse import quote
from datetime import datetime
import time
import logging
from utils.url_safety import is_safe_url

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

# 🆕 Phase 1 Concurrency Control
WIKI_SEMAPHORE = asyncio.Semaphore(50)

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
            "User-Agent": "RyanTravelApp/1.2 (contact@example.com)",
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


# ==================== Wikipedia API ====================

from utils.url_safety import is_safe_url

async def get_wikipedia_summary(name: str, lang: str = "zh", client: httpx.AsyncClient = None, is_retry: bool = False, lat: float = None, lng: float = None) -> tuple[str, str]:
    """
    從 Wikipedia 獲取景點簡介 (200 字以內，共享 Client 與 Semaphore)
    """
    # 🛡️ SSRF Protection: Validate language whitelist
    allowed_langs = {"en", "zh", "ja", "ko", "fr", "de", "es", "it", "ru", "pt"}
    if lang not in allowed_langs:
        print(f"[POI] Blocked potential SSRF attempt with invalid Wikipedia lang: {lang}")
        return "", ""

    start_time = time.time()
    try:
        headers = {
            "User-Agent": "RyanTravelApp/1.2 (contact@example.com)",
            "Accept": "application/json"
        }

        # 📍 優先權加固 (Phase 6.10)：十倍視野優化，確保密集景區地標不遺漏
        if lat is not None and lng is not None and not is_retry:
            geo_url = f"https://{lang}.wikipedia.org/w/api.php?action=query&list=geosearch&gscoord={lat}|{lng}&gsradius=1000&gslimit=10&format=json"
            if is_safe_url(geo_url): # 🛡️ 安全防護不中斷
                try:
                    if client:
                        geo_resp = await client.get(geo_url, headers=headers)
                    else:
                        async with httpx.AsyncClient(timeout=5.0) as temp_client:
                            geo_resp = await temp_client.get(geo_url, headers=headers)
                            
                    if geo_resp.status_code == 200:
                        geo_data = geo_resp.json()
                        geosearch_results = geo_data.get("query", {}).get("geosearch", [])
                        if geosearch_results:
                            # 🎯 智慧選擇：從附近條目中找名字最契合的 (擴大檢索深度至 10)
                            best_title = geosearch_results[0]["title"]
                            
                            # 第一輪：嘗試全字包含 (掃描前 10 項)
                            found_exact = False
                            for entry in geosearch_results[:10]:
                                t = entry["title"]
                                if name in t or t in name:
                                    best_title = t
                                    found_exact = True
                                    break
                            
                            # 第二輪：智慧分詞比對 (處理中正廟 -> 中正紀念堂, 自由廣場 -> 自由廣場 (台北))
                            if not found_exact:
                                # 🧠 智慧分詞：生成所有可能的 2 字片段 (N-grams) 提高命中率
                                search_fragments = [name[i:i+2] for i in range(len(name)-1)]
                                # 同時保留原始 split 部份 (針對英文關鍵字)
                                search_fragments.extend([p for p in name.split() if len(p) >= 2])
                                
                                # 擴大比對深度至前 10 名
                                for entry in geosearch_results[:10]:
                                    entry_t = entry["title"]
                                    if any(frag in entry_t for frag in search_fragments):
                                        best_title = entry_t
                                        break
                                
                                # 如果地理搜尋找到了精確條目，直接跳轉
                                print(f"📍 [Wiki Geosearch] Found best nearby match: {best_title}")
                                return await get_wikipedia_summary(best_title, lang=lang, client=client, is_retry=True, lat=lat, lng=lng)
                except Exception as e:
                    print(f"⚠️ [Wiki Geosearch] Priority check failed: {e}")

        # Wikipedia REST API 規範：空格應轉為下底線 _
        clean_name = name.strip().replace(' ', '_')
        url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(clean_name)}"
        if not is_safe_url(url):
            return "", ""
        
        async with WIKI_SEMAPHORE:
            if client:
                response = await client.get(url, headers=headers, follow_redirects=True)
            else:
                async with httpx.AsyncClient(timeout=10.0) as temp_client:
                    response = await temp_client.get(url, headers=headers, follow_redirects=True)
            
            latency = time.time() - start_time
            latency_metric, _ = _get_poi_metrics()
            latency_metric.labels(source="wikipedia").observe(latency)
                    
            if response.status_code == 200:
                _, requests_metric = _get_poi_metrics()
                requests_metric.labels(source="wikipedia", status="success").inc()
                data = response.json()
                extract = data.get("extract", "")
                image_url = data.get("thumbnail", {}).get("source", "") # 🆕 Phase 5.3.2: Extract image
                
                final_extract = extract[:200] if len(extract) > 200 else extract
                return final_extract, image_url
            else:
                _, requests_metric = _get_poi_metrics()
                requests_metric.labels(source="wikipedia", status="error").inc()
                
                # 🆕 智慧搜尋保底：當直接查無結果 (404) 時
                if response.status_code == 404 and not is_retry:
                    # 備案：關鍵字搜尋 (OpenSearch)
                    search_url = f"https://{lang}.wikipedia.org/w/api.php?action=opensearch&search={quote(name)}&limit=1&format=json"
                    try:
                        if client:
                            search_resp = await client.get(search_url, headers=headers)
                        else:
                            async with httpx.AsyncClient(timeout=5.0) as temp_client:
                                search_resp = await temp_client.get(search_url, headers=headers)
                                
                        if search_resp.status_code == 200:
                            search_data = search_resp.json()
                            if len(search_data) > 1 and search_data[1]:
                                best_title = search_data[1][0]
                                return await get_wikipedia_summary(best_title, lang=lang, client=client, is_retry=True, lat=lat, lng=lng)
                    except Exception as search_err:
                        print(f"⚠️ [Wiki Search] Fallback search failed for '{name}': {search_err}")
    except Exception as e:
        _, requests_metric = _get_poi_metrics()
        requests_metric.labels(source="wikipedia", status="exception").inc()
        print(f"Wikipedia API error ({lang}): {e}")
    
    # 語言 fallback: zh → ja → en
    fallback_order = {"zh": "ja", "ja": "en"}
    if lang in fallback_order:
        return await get_wikipedia_summary(name, fallback_order[lang], client=client, lat=lat, lng=lng)
    
    return "", "" # 🆕 Phase 5.3.2: Return tuple


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
            "User-Agent": "RyanTravelApp/1.2 (contact@example.com)"
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
    
    # 並行查詢三個來源 (每項 3s Timeout 防護)
    try:
        tasks = [
            asyncio.wait_for(get_wikidata_labels(wikidata_id, client=client), 6.0) if wikidata_id else asyncio.sleep(0),
            asyncio.wait_for(get_wikipedia_summary(name, lang=wiki_lang, client=client, lat=lat, lng=lng), 6.0),
            asyncio.wait_for(search_wikivoyage(name, lang=wiki_lang, client=client), 6.0)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 1. 處理 Wikidata 結果
        wikidata_result = None
        res0 = results[0]
        if isinstance(res0, asyncio.TimeoutError):
            poi["warnings"].append("WIKIDATA_TIMEOUT")
            if poi["status"] == "SUCCESS": poi["status"] = "PARTIAL_SUCCESS"
        elif isinstance(res0, Exception):
            poi["warnings"].append("WIKIDATA_ERROR")
            if poi["status"] == "SUCCESS": poi["status"] = "PARTIAL_SUCCESS"
        else:
            wikidata_result = res0
            
        # 2. 處理 Wikipedia 結果 (三步 Fallback 流程)
        wikipedia_result = ""
        wikipedia_image = "" # 🆕 Phase 5.3.2
        res1 = results[1]
        
        # 定義：內部抓取函式 (方便 fallback 時重用)
        async def fetch_wiki(title_to_fetch: str):
            if not title_to_fetch: return "", ""
            return await get_wikipedia_summary(title_to_fetch, lang=wiki_lang, client=client, lat=lat, lng=lng)

        if isinstance(res1, asyncio.TimeoutError):
            poi["warnings"].append("WIKIPEDIA_TIMEOUT")
            if poi["status"] == "SUCCESS": poi["status"] = "PARTIAL_SUCCESS"
        elif isinstance(res1, Exception):
            # 初始抓取異常，稍後嘗試 Sitelink Fallback
            pass
        else:
            # Unpack the tuple
            if isinstance(res1, tuple):
                wikipedia_result, wikipedia_image = res1
            else:
                wikipedia_result = res1 or ""

        # --- Fallback Step 2 & 3: Wikidata Sitelink ---
        if not wikipedia_result and wikidata_result:
            sitelinks = wikidata_result.get("sitelinks", {})
            
            # Step 2: 優先核心語系 (依請求語系切換優先序)
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
            
            # Step 3: 全球保底 (Phase 5.2: 抓取第一個可用語系)
            if not best_title and sitelinks:
                # 排除一些非百科的 Meta 連結
                valid_wikis = [k for k in sitelinks.keys() if k.endswith("wiki") and not k.startswith("commons")]
                if valid_wikis:
                    wiki_key = valid_wikis[0]
                    best_title = sitelinks[wiki_key]
                    target_lang = wiki_key.replace("wiki", "")
                    print(f"🌍 [Global Fallback] Using {target_lang} Wikipedia: {best_title}")

            if best_title:
                try:
                    # 使用 2s timeout 進行二次抓取
                    res_fallback = await asyncio.wait_for(get_wikipedia_summary(best_title, lang=target_lang, client=client, lat=lat, lng=lng), 2.0)
                    if isinstance(res_fallback, tuple):
                        wikipedia_result, wikipedia_image = res_fallback
                        if wikipedia_result and not target_lang.startswith(wiki_lang):
                            used_fallback_lang = target_lang
                            poi["resolved_language"] = target_lang
                    else:
                        wikipedia_result = res_fallback
                except:
                    # 二次抓取失敗不中斷流程
                    pass

        # 最終 Wikipedia 狀態判定與 Warning 固定
        if not wikipedia_result:
            if isinstance(res1, asyncio.TimeoutError):
                # 已經有 TIMEOUT warning 了
                pass
            else:
                # 查無結果 (Page Not Found)
                poi["warnings"].append("WIKIPEDIA_NOT_FOUND")
            
            if poi["status"] == "SUCCESS": poi["status"] = "PARTIAL_SUCCESS"
        else:
            # 有結果，但如果是空字串 (理論上 fetch_wiki 不會回傳空但保險起見)
            if not wikipedia_result.strip():
                poi["warnings"].append("WIKIPEDIA_EMPTY")
            
        # 3. 處理 WikiVoyage 結果
        wikivoyage_result = None
        res2 = results[2]
        if isinstance(res2, asyncio.TimeoutError):
            poi["warnings"].append("WIKIVOYAGE_TIMEOUT")
        elif isinstance(res2, Exception):
            poi["warnings"].append("WIKIVOYAGE_ERROR")
        else:
            wikivoyage_result = res2
        
        if wikidata_result:
            # 🆕 Phase 5.1.3: Wikidata Image Fallback
            if not poi.get("image_url") and wikidata_result.get("wikidata_image"):
                # 將 Commons 檔名轉為基本連結 (後續由 Proxy 處理)
                img_name = wikidata_result["wikidata_image"].replace(" ", "_")
                poi["image_url"] = f"https://commons.wikimedia.org/wiki/Special:FilePath/{img_name}?width=500"

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

