"""
Smart Search Service - 防胡謅版
================================

設計原則：
1. 只用 1 次 AI 調用（Intent 解析）
2. 不生成推薦理由（最易胡謅）
3. 只返回 POI 真實資料
4. 無結果時明確說「找不到」
"""

import asyncio
import json
import os
import re
from typing import List, Dict, Optional, Tuple
from math import radians, cos, sin, sqrt, atan2

import httpx
from google import genai
from google.genai import types

from services.model_manager import call_extraction, call_timeout_scope
from utils.ai_config import DAILY_ROUTING
from services.poi_service import search_poi_combined
from services.geocode_service import geocode_place


# --- Intent 解析 Prompt ---

INTENT_PARSE_PROMPT = """
你是一個旅遊搜尋意圖分析器。分析用戶的搜尋查詢，提取結構化意圖。

用戶查詢：「{query}」
當前位置參考：{region}

請分析並輸出 JSON（不要 markdown）：
{{
    "intent_type": "recommendation|nearby|specific",
    "category": "restaurant|shopping|attraction|convenience|pharmacy|null",
    "food_type": "ramen|sushi|cafe|curry|izakaya|null",
    "location": "提取的地點名或 null",
    "keywords": ["關鍵詞1", "關鍵詞2"]
}}

意圖類型：
- recommendation: 推薦類（好吃的、值得去的）
- nearby: 附近類（附近有什麼、周邊）
- specific: 精確搜尋（具體店名）

範例：
- 「新宿好吃的拉麵」→ {{"intent_type":"recommendation","category":"restaurant","food_type":"ramen","location":"新宿",...}}
- 「附近便利商店」→ {{"intent_type":"nearby","category":"convenience","location":null,...}}
"""

INTENT_PARSE_PROMPT_EN = """
You are a travel search intent analyzer. Analyze the user's search query and extract structured intent.

User Query: "{query}"
Region Reference: {region}

Output PURE JSON ONLY (no markdown):
{{
    "intent_type": "recommendation|nearby|specific",
    "category": "restaurant|shopping|attraction|convenience|pharmacy|null",
    "food_type": "ramen|sushi|cafe|curry|izakaya|null",
    "location": "Extracted place/area name or null",
    "keywords": ["keyword1", "keyword2"]
}}

Intent types:
- recommendation: looking for good/best/recommended places
- nearby: looking for places nearby or around a location
- specific: searching a specific venue name
"""


# --- 輔助函數 ---

def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """計算兩點間距離（公尺）"""
    R = 6371000
    lat1_rad, lat2_rad = radians(lat1), radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lng = radians(lng2 - lng1)
    
    a = sin(delta_lat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lng/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c


def _is_en_locale(locale: Optional[str]) -> bool:
    return bool(locale and str(locale).strip().lower().startswith("en"))


async def parse_intent(
    api_key: str,
    query: str,
    region: Optional[str] = None,
    locale: str = "zh"
) -> Dict:
    """
    使用 AI 解析用戶意圖（唯一的 AI 調用，帶 2.5s 逾時熔斷保護）
    🆕 v5.0: 使用 call_extraction 獲得 3 層降級保護
    """
    is_en = _is_en_locale(locale)
    template = INTENT_PARSE_PROMPT_EN if is_en else INTENT_PARSE_PROMPT
    prompt = template.format(
        query=query,
        region=region or ("Unknown" if is_en else "未知")
    )
    
    try:
        # 🆕 內層 per-model 1.2s + 外層 3.5s 保護，讓 Primary 卡頓或 503 時有餘裕切入 Fallback 模型
        with call_timeout_scope(1.2):
            raw_text = await asyncio.wait_for(
                call_extraction(
                    api_key, prompt,
                    intent_type="INTENT_PARSE",
                ),
                timeout=3.5,
            )
        
        if raw_text and raw_text.strip():
            json_match = re.search(r'\{[\s\S]*\}', raw_text)
            if json_match:
                result = json.loads(json_match.group())
                print(f"✅ Intent parsed: {result}")
                return result
        
    except Exception as e:
        print(f"⚠️ Intent parse failed: {e}")
    
    # Fallback: 雙語基本規則解析
    q_lower = query.lower()
    fallback_cat = None
    fallback_food = None
    if any(k in q_lower for k in ["吃", "餐", "麵", "飯", "ramen", "restaurant", "food", "eat", "sushi", "dining", "cafe", "coffee"]):
        fallback_cat = "restaurant"
        if "ramen" in q_lower or "拉麵" in q_lower:
            fallback_food = "ramen"
    elif any(k in q_lower for k in ["藥局", "藥妝", "pharmacy", "drugstore"]):
        fallback_cat = "pharmacy"
    elif any(k in q_lower for k in ["超商", "便利", "convenience"]):
        fallback_cat = "convenience"
    elif any(k in q_lower for k in ["購物", "百貨", "shopping", "mall"]):
        fallback_cat = "shopping"
    elif any(k in q_lower for k in ["景點", "temple", "shrine", "tower", "museum", "attraction"]):
        fallback_cat = "attraction"

    return {
        "intent_type": "nearby" if any(k in q_lower for k in ["附近", "周邊", "nearby", "around", "near"]) else "specific",
        "category": fallback_cat,
        "food_type": fallback_food,
        "location": None,
        "keywords": [query]
    }


async def _photon_fallback_candidates(
    search_lat: float,
    search_lng: float,
    query: str,
    poi_category: str,
    food_type: Optional[str],
    max_distance: int,
    target_coords: Optional[Tuple[float, float]],
    is_en: bool,
) -> List[Dict]:
    """當 Overpass 逾時或為空時，3.0s 內極速降級 Photon 周邊 POI 檢索。"""
    search_term = food_type or query or poi_category or "restaurant"
    default_name = "Unknown Place" if is_en else "周邊設施"
    user_agent = os.getenv("APP_USER_AGENT", "TabidachiTravelApp/2.0 (contact@tabidachi.app)")
    candidates: List[Dict] = []
    try:
        async with httpx.AsyncClient(timeout=3.0, headers={"User-Agent": user_agent}) as client:
            resp = await client.get(
                "https://photon.komoot.io/api/",
                params={"q": search_term, "lat": search_lat, "lon": search_lng, "limit": 8},
            )
            data = resp.json() if getattr(resp, "status_code", 0) == 200 else {}
            for feature in data.get("features", []) or []:
                if not isinstance(feature, dict):
                    continue
                props = feature.get("properties") or {}
                coords = (feature.get("geometry") or {}).get("coordinates") or []
                if not isinstance(coords, list) or len(coords) < 2:
                    continue
                poi_lng, poi_lat = coords[0], coords[1]
                if poi_lat is None or poi_lng is None:
                    continue
                dist = round(haversine_distance(search_lat, search_lng, poi_lat, poi_lng))
                if target_coords and dist > max_distance:
                    continue
                addr_parts = [p for p in [props.get("street"), props.get("city"), props.get("country")] if p]
                candidates.append({
                    "name": props.get("name") or props.get("street") or default_name,
                    "lat": poi_lat,
                    "lng": poi_lng,
                    "address": ", ".join(addr_parts),
                    "distance": dist,
                    "rating": None,
                    "source": "photon",
                    "wikidata_id": "",
                    "id": "",
                })
    except Exception as exc:
        print(f"⚠️ Photon fallback failed: {exc}")
    return candidates


async def get_poi_candidates(
    intent: Dict,
    lat: float,
    lng: float,
    max_distance: int = 10000,  # 10km 最大驗證距離
    locale: str = "zh"
) -> Tuple[List[Dict], Optional[Tuple[float, float]]]:
    """
    根據意圖獲取 POI 候選（純 API，無 AI；Overpass 單次 3.0s 限時＋Photon 極速降級）
    
    Returns:
        (候選列表, 目標坐標)
    """
    is_en = _is_en_locale(locale)
    intent_type = intent.get("intent_type", "specific")
    category = intent.get("category") or "restaurant"
    location = intent.get("location")
    food_type = intent.get("food_type")
    keywords = intent.get("keywords") or []
    raw_query = food_type or (keywords[0] if keywords else "") or category
    
    print(f"🔍 get_poi_candidates: type={intent_type}, category={category}, location={location}")
    
    # 確定搜尋坐標 (2.5s timeout 防護)
    search_lat, search_lng = lat, lng
    target_coords = None
    
    if location:
        try:
            geo_result = await asyncio.wait_for(geocode_place(location, lat, lng), timeout=2.5)
            if geo_result and geo_result.get("lat") is not None and geo_result.get("lng") is not None:
                search_lat = geo_result["lat"]
                search_lng = geo_result["lng"]
                target_coords = (search_lat, search_lng)
                print(f"✅ Geocoded '{location}' → ({search_lat:.4f}, {search_lng:.4f})")
        except Exception as e:
            print(f"⚠️ Geocode failed or timed out: {e}")
    
    # 類別映射
    category_map = {
        "restaurant": "restaurant",
        "shopping": "department_store",
        "convenience": "convenience",
        "pharmacy": "pharmacy",
        "attraction": "popular"
    }
    poi_category = category_map.get(category, "restaurant")
    
    # 單次限時搜尋 (<= 3.0s，杜絕舊版 4 圈 40s 阻塞 500 ECONNRESET)
    print(f"🔍 Searching POI (bounded 3.0s): category={poi_category}, radius=2000m")
    try:
        pois = await asyncio.wait_for(
            search_poi_combined(
                lat=search_lat,
                lng=search_lng,
                category=poi_category,
                radius=2000,
                timeout=3.0,
            ),
            timeout=3.5,
        )
        valid_pois = []
        for poi in pois or []:
            if not isinstance(poi, dict):
                continue
            poi_lat = poi.get("lat")
            poi_lng = poi.get("lng")
            if poi_lat is None or poi_lng is None:
                continue
            if target_coords:
                dist = haversine_distance(target_coords[0], target_coords[1], poi_lat, poi_lng)
                if dist <= max_distance:
                    poi["distance_to_target"] = round(dist)
                    valid_pois.append(poi)
            else:
                valid_pois.append(poi)
        if valid_pois:
            print(f"✅ Found {len(valid_pois)} POIs via Overpass within 3.0s")
            return valid_pois, target_coords
    except Exception as e:
        print(f"⚠️ Overpass bounded search failed/timed out, switching to Photon fallback: {e}")

    # 即時降級 Photon (<= 3.0s)
    photon_pois = await _photon_fallback_candidates(
        search_lat=search_lat,
        search_lng=search_lng,
        query=str(raw_query),
        poi_category=poi_category,
        food_type=food_type,
        max_distance=max_distance,
        target_coords=target_coords,
        is_en=is_en,
    )
    if photon_pois:
        print(f"✅ Found {len(photon_pois)} POIs via Photon fallback")
        return photon_pois, target_coords

    print("❌ No POI candidates found")
    return [], target_coords


async def smart_search(
    api_key: str,
    query: str,
    lat: float,
    lng: float,
    region: Optional[str] = None,
    trip_title: Optional[str] = None,
    max_results: int = 5,
    locale: str = "zh"
) -> Dict:
    """
    🛡️ 防胡謅版智能搜尋
    
    設計：
    - 只用 1 次 AI 調用（Intent 解析）
    - 不生成推薦理由
    - 只返回 POI 真實資料
    """
    is_en = _is_en_locale(locale)
    print(f"🧠 Smart Search: query='{query}', region='{region}', locale='{locale}'")
    
    # Step 1: AI 解析意圖（唯一的 AI 調用）
    intent = await parse_intent(api_key, query, region or trip_title, locale=locale)
    
    # Step 2: 獲取 POI 候選（純 API，無 AI）
    candidates, target_coords = await get_poi_candidates(intent, lat, lng, locale=locale)
    
    # Step 3: 構建雙語響應
    location_str = intent.get("location") or ("nearby" if is_en else "附近")
    category_str = intent.get("food_type") or intent.get("category") or ("places" if is_en else "地點")
    default_poi_name = "Unknown Place" if is_en else "周邊設施"
    understood_str = (
        f"Searching for {category_str} near {location_str}"
        if is_en
        else f"在{location_str}找{category_str}"
    )
    
    if candidates and len(candidates) > 0:
        # 成功：返回真實 POI 資料
        results = []
        for poi in candidates:
            if poi.get("lat") is None or poi.get("lng") is None:
                continue
            # 只返回真實資料，不添加任何 AI 生成的描述！
            results.append({
                "name": poi.get("name") or default_poi_name,
                "lat": poi.get("lat"),
                "lng": poi.get("lng"),
                "address": poi.get("address", ""),
                "distance": poi.get("distance"),
                "rating": poi.get("rating"),
                "source": poi.get("source", "osm"),
                "wikidata_id": poi.get("wikidata_id", ""),
                "poi_id": poi.get("id", "")
            })
            if len(results) >= max_results:
                break

        if results:
            return {
                "status": "success",
                "query_type": intent.get("intent_type", "specific"),
                "understood_intent": understood_str,
                "results": results,
                "total_found": len(candidates)
            }

    # 失敗：明確說找不到，不要胡謅！
    return {
        "status": "not_found",
        "query_type": intent.get("intent_type", "specific"),
        "understood_intent": understood_str,
        "message": (
            f"No matching {category_str} found near {location_str}"
            if is_en
            else f"在{location_str}附近找不到{category_str}相關店家"
        ),
        "suggestions": (
            [
                "Try expanding your search area",
                "Use a more specific landmark or neighborhood name",
                "Try a different category"
            ]
            if is_en
            else [
                "嘗試更大的搜尋範圍",
                "使用更具體的地名",
                "嘗試其他類別"
            ]
        )
    }
