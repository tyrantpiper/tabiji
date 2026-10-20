"""
POI Router
----------
Handles Point of Interest related endpoints including:
- AI-powered enrichment
- Wikipedia/WikiVoyage integration
- Nearby search
- AI recommendations
"""

import json
import re
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import StreamingResponse
import httpx
import uuid
import time
from typing import List, Optional, Any, Dict
from pydantic import BaseModel
from google import genai
from google.genai import types

from models.base import POIAIEnrichRequest, POIEnrichRequest, POIRecommendRequest, SmartSearchRequest
from utils.deps import get_gemini_key, get_supabase
from utils.url_safety import is_safe_url
from services.link_resolver import resolve_google_maps_link
from services.geocode_service import smart_geocode_logic, reverse_geocode_with_photon
from utils.ai_config import LITE_MODEL, DAILY_ROUTING
from services.poi_service import (
    enrich_poi_complete,
    format_enriched_poi_for_ai,
    search_poi_combined,
    format_pois_for_ai,
    get_ai_prompt_for_recommendation,
    search_wikivoyage
)
from services.smart_search_service import smart_search
from services.model_manager import call_extraction
from utils.poi_utils import generate_v2_cache_key

router = APIRouter(prefix="/api", tags=["poi"])

# 🆕 Phase 2 Cache (Process-level with v2 versioning)
POI_ENRICH_CACHE: Dict[str, Dict] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# POI AI Enrichment
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/poi/ai-enrich")
async def ai_enrich_poi(fastapi_req: Request, request: POIAIEnrichRequest):
    """
    🤖 整合型 POI 增強端點 - 同時取得 AI 摘要與 Wikipedia/WikiVoyage 資訊
    
    具備背景並行抓取、三級保底鏈防護與 v2 版本化快取。
    """
    try:
        # 🆕 Step 3: 快取檢查 (v2 versioned)
        cache_key = generate_v2_cache_key(
            name=request.name,
            lat=request.lat,
            lng=request.lng,
            poi_id=request.poi_id,
            wikidata_id=request.wikidata_id
        )
        
        if cache_key in POI_ENRICH_CACHE:
            print(f"⚡ [Cache Hit] {cache_key}")
            return POI_ENRICH_CACHE[cache_key]

        api_key = request.api_key
        if not api_key:
            raise HTTPException(status_code=400, detail="需要 API Key")
        
        print(f"🔍 [POI Enrich] 開始抓取與摘要: {request.name} (Wiki + AI)...")
        
        prompt = f"""
You are a travel guide assistant. Search the web for reviews and vibes for:
- Name: {request.name}
- Type: {request.type}
- Location: {request.lat}, {request.lng}

Output in this EXACT JSON format (Traditional Chinese summary):
{{
    "summary": "1-2 sentence vibe check",
    "must_try": ["Item 1", "Item 2"],
    "rating": 4.5,
    "business_status": "OPERATIONAL"
}}
"""
        # 🚀 並行執行 AI 摘要與 Wiki 豐富 (使用 DAILY_ROUTING 進行極速低延遲解析)
        ai_task = call_extraction(
            api_key,
            prompt,
            intent_type="POI_ENRICH",
            routing_strategy=DAILY_ROUTING
        )
        wiki_task = enrich_poi_complete({
            "name": request.name,
            "wikidata_id": request.wikidata_id or "",
            "lat": request.lat,
            "lng": request.lng
        }, fastapi_req.app.state.client)
        
        ai_result, wiki_result = await asyncio.gather(ai_task, wiki_task, return_exceptions=True)
        
        # 1. 處理 AI 摘要結果
        ai_data = {}
        if not isinstance(ai_result, Exception):
            json_match = re.search(r'\{[\s\S]*\}', ai_result)
            if json_match:
                try:
                    ai_data = json.loads(json_match.group())
                except:
                    ai_data = {"summary": ai_result[:200]}
            else:
                ai_data = {"summary": str(ai_result)[:200]}
        
        # 2. 處理 Wiki 結果
        if isinstance(wiki_result, Exception):
            wiki_result = {
                "status": "PARTIAL_SUCCESS",
                "warnings": ["WIKI_SYSTEM_ERROR"],
                "cultural_desc": None,
                "travel_tips": None
            }
        
        # 🆕 Phase 5.2: AI Translation Fallback
        resolved_lang = wiki_result.get("resolved_language", "zh-TW")
        cultural_desc = wiki_result.get("cultural_desc")
        
        if cultural_desc and resolved_lang != "zh-TW" and not str(resolved_lang).startswith("zh"):
            print(f"🌐 [AI Translate] Translating {resolved_lang} to zh-TW...")
            translation_prompt = f"請將以下維基百科描述翻譯為繁體中文（zh-TW），保持旅遊指南的專業語氣：\n\n{cultural_desc}"
            try:
                translated = await call_extraction(
                    api_key=api_key,
                    prompt=translation_prompt,
                    intent_type="SUMMARIZE"  # Use SUMMARIZE for simple translation tasks to avoid schema overhead
                )
                if translated:
                    wiki_result["cultural_desc"] = translated
                    wiki_result["resolved_language"] = f"zh-TW (translated from {resolved_lang})"
            except Exception as te:
                print(f"⚠️ Translation failed: {te}")

        # 3. 數據合流與保底鏈 (Summary Fallback Chain)
        final_summary = ai_data.get("summary") or wiki_result.get("cultural_desc") or f"{request.name} 是位於當地的地點。"
        
        # 4. 狀態判定
        ai_success = bool(ai_data.get("summary"))
        wiki_status = wiki_result.get("status", "FAILED")
        
        final_status = "SUCCESS"
        if not ai_success or wiki_status != "SUCCESS":
            final_status = "PARTIAL_SUCCESS"
        if not ai_success and wiki_status == "FAILED":
            final_status = "FAILED"
            
        result_payload = {
            "summary": final_summary,
            "must_try": ai_data.get("must_try") or [],
            "rating": ai_data.get("rating") or 0,
            "business_status": ai_data.get("business_status") or "UNKNOWN",
            "cultural_desc": wiki_result.get("cultural_desc"),
            "travel_tips": wiki_result.get("travel_tips"),
            "resolved_language": wiki_result.get("resolved_language") or "zh-TW",
            "image_url": wiki_result.get("image_url"), # 🆕 Phase 5.4: Expose image
            "status": final_status,
            "warnings": (wiki_result.get("warnings") or []),
            "official_url": wiki_result.get("official_url")
        }

        # 🆕 Step 3: 快取存儲 (僅在完全成功 SUCCESS 時存儲，不快取帶有警告的 PARTIAL 狀態)
        if final_status == "SUCCESS":
            POI_ENRICH_CACHE[cache_key] = result_payload
            
        print(f"✅ [POI Enrich] 完成: {request.name} (Status: {final_status})")
        return result_payload
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"🔥 AI POI 整合失敗：{e}")
        raise HTTPException(status_code=500, detail=f"AI 增強失敗: {str(e)}")


@router.post("/poi/enrich")
async def enrich_poi(fastapi_req: Request, body: POIEnrichRequest):
    """
    📚 三源整合 POI 端點 - Wikipedia + WikiVoyage + Wikidata
    
    Returns:
        {
            "display_name": {"primary": "金閣寺", "secondary": "金閣寺 (Kinkaku-ji)"},
            "cultural_desc": "...",
            "travel_tips": "...",
            "official_url": "..."
        }
    """
    try:
        poi = {
            "name": body.name,
            "wikidata_id": body.wikidata_id or "",
            "lat": body.lat,
            "lng": body.lng
        }
        
        enriched = await enrich_poi_complete(poi, fastapi_req.app.state.client)
        formatted = format_enriched_poi_for_ai(enriched)
        
        return {
            "success": True,
            "poi": enriched,
            "formatted": formatted
        }
        
    except Exception as e:
        print(f"🔥 POI 整合失敗：{e}")
        raise HTTPException(status_code=500, detail=f"POI 整合失敗: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════════
# POI Search
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/poi/nearby")
async def search_nearby_poi(
    lat: float,
    lng: float,
    category: str = "restaurant",
    radius: int = 1000
):
    """
    🔍 搜索附近 POI
    
    Args:
        lat: 緯度
        lng: 經度
        category: 類別 (pharmacy, restaurant, convenience, supermarket, department_store, popular)
        radius: 搜索半徑（公尺，預設 1000）
    
    Returns:
        POI 列表（含距離、評分等）
    """
    valid_categories = ["pharmacy", "restaurant", "convenience", "supermarket", "department_store", "popular"]
    if category not in valid_categories:
        raise HTTPException(status_code=400, detail=f"Invalid category. Valid: {valid_categories}")
    
    if radius < 100 or radius > 5000:
        raise HTTPException(status_code=400, detail="Radius must be between 100 and 5000 meters")
    
    try:
        pois = await search_poi_combined(lat, lng, category, radius)
        return {
            "count": len(pois),
            "radius": radius,
            "category": category,
            "pois": pois
        }
    except Exception as e:
        print(f"🔥 POI Search Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/poi/recommend")
async def ai_recommend_poi(request: POIRecommendRequest):
    """
    🤖 基於 POI 列表進行 AI 推薦
    
    Token 優化策略：
    1. POI 資料已由 /api/poi/nearby 預先查詢
    2. 只傳精簡摘要給 Gemini（~200 tokens vs ~2000 tokens）
    3. 節省 80%+ Token 消耗
    """
    if not request.pois:
        return {"recommendation": "附近沒有找到相關地點，請嘗試其他類別或擴大搜索範圍。"}
    
    if not request.api_key:
        raise HTTPException(status_code=400, detail="API key required")
    
    try:
        # Step 1: 格式化 POI 為精簡文字
        pois_text = format_pois_for_ai(request.pois, max_items=5)
        print(f"🤖 [POI Recommend] 正在為 {len(request.pois)} 個地點進行 AI 推薦評估...")
        
        # Step 2: 生成精簡 prompt
        prompt = get_ai_prompt_for_recommendation(
            pois_text,
            request.user_query,
            request.user_preferences
        )
        
        # 🆕 v5.0: 使用 call_extraction 獲得 3 層降級保護
        from services.model_manager import call_extraction
        from utils.ai_config import DAILY_ROUTING
        
        recommendation_text = await call_extraction(
            request.api_key, prompt,
            intent_type="POI_ENRICH",
            routing_strategy=DAILY_ROUTING,
        )
        
        print(f"✅ [POI Recommend] AI 推薦完成")
        return {
            "recommendation": recommendation_text,
            "pois_count": len(request.pois),
            "token_optimized": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"🔥 POI Recommend Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/poi/categories")
async def get_poi_categories():
    """📋 取得支援的 POI 類別列表"""
    return {
        "categories": [
            {"id": "department_store", "name": "百貨公司", "icon": "🏬"},
            {"id": "restaurant", "name": "美食餐廳", "icon": "🍽️"},
            {"id": "convenience", "name": "便利商店", "icon": "🏪"},
            {"id": "supermarket", "name": "超市", "icon": "🛒"},
            {"id": "pharmacy", "name": "藥局藥妝", "icon": "💊"},
            {"id": "popular", "name": "熱門景點", "icon": "🔥"}
        ]
    }


# ═══════════════════════════════════════════════════════════════════════════════
# WikiVoyage Integration
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/wikivoyage/search")
async def wikivoyage_search(place: str, lang: str = "en"):
    """
    🌍 搜索 WikiVoyage 景點描述
    
    Args:
        place: 景點名稱 (英文效果較佳)
        lang: 語言代碼 (en, ja, zh)
    
    Returns:
        WikiVoyage 頁面資訊
    """
    if not place or len(place) < 2:
        raise HTTPException(status_code=400, detail="Place name too short")
    
    result = await search_wikivoyage(place, lang)
    
    if not result:
        return {
            "found": False,
            "message": f"No WikiVoyage article found for '{place}'"
        }
    
    return {
        "found": True,
        **result
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Smart AI Search (gemma-3-27b powered)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/ai/smart-search")
async def ai_smart_search(request: SmartSearchRequest):
    """
    🧠 智能語意搜尋 - 使用 gemma-3-27b 理解用戶意圖
    
    支援查詢類型：
    - 推薦類：「好吃的拉麵」「值得去的景點」
    - 附近類：「附近有什麼」「周邊餐廳」
    - 條件類：「便宜的壽司」「24小時營業」
    
    策略：gemma-3-27b 優先（14,400 RPD），零成本
    
    Returns:
        {
            "query_type": "recommendation|nearby|specific",
            "understood_intent": "AI 理解的意圖描述",
            "recommendations": [
                {
                    "name": "地點名稱",
                    "reason": "推薦理由",
                    "highlights": ["特色1", "特色2"],
                    "lat": 35.6895,
                    "lng": 139.6917,
                    "rating": 4.5,
                    "distance": 300
                }
            ],
            "source": "gemma_poi|gemma_geocode|poi_fallback"
        }
    """
    if not request.api_key:
        raise HTTPException(status_code=400, detail="API key required")
    
    if not request.query or len(request.query) < 2:
        raise HTTPException(status_code=400, detail="Query too short")
    
    try:
        result = await smart_search(
            api_key=request.api_key,
            query=request.query,
            lat=request.lat,
            lng=request.lng,
            region=request.region,
            trip_title=request.trip_title,
            max_results=request.max_results
        )
        
        return result
        
    except Exception as e:
        print(f"🔥 Smart Search Error: {e}")
        raise HTTPException(status_code=500, detail=f"Smart search failed: {str(e)}")

# ═══════════════════════════════════════════════════════════════════════════════
# Media Proxy (Phase 5.4)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/poi/media-proxy")
async def media_proxy(url: str):
    """
    🖼️ 媒體代理端點 - 解決維基百科圖片的 CORS 與 Referrer 限制
    """
    if not url.startswith("https://upload.wikimedia.org/"):
        raise HTTPException(status_code=400, detail="Invalid media source")

    async def stream_image():
        headers = {
            "User-Agent": "RyanTravelApp/1.2 (contact@example.com)",
            "Referer": "https://www.wikipedia.org/"
        }
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code != 200:
                    return
                async for chunk in response.aiter_bytes():
                    yield chunk

    # 簡單偵測 content_type (或是預設為 image/jpeg)
    content_type = "image/jpeg"
    if url.lower().endswith(".png"): content_type = "image/png"
    elif url.lower().endswith(".svg"): content_type = "image/svg+xml"
    elif url.lower().endswith(".gif"): content_type = "image/gif"

    return StreamingResponse(stream_image(), media_type=content_type)


# ═══════════════════════════════════════════════════════════════════════════════
# POI Pool & Shared List Ingestion (Link-to-Places)
# ═══════════════════════════════════════════════════════════════════════════════

class POIImportLinkRequest(BaseModel):
    url: str

class POICreateRequest(BaseModel):
    title: str
    address: Optional[str] = None
    lat: float
    lng: float
    google_place_id: Optional[str] = None
    category: Optional[str] = "attraction"
    rating: Optional[float] = None
    user_notes: Optional[str] = None
    source_url: Optional[str] = None
    is_pinned: Optional[bool] = False
    pin_color: Optional[str] = "#E56E25"

class POIUpdateNoteRequest(BaseModel):
    note: str

class POITogglePinRequest(BaseModel):
    is_pinned: bool

class POIUpdateCategoryRequest(BaseModel):
    category: str


POI_POOL_STORE: Dict[str, List[Dict[str, Any]]] = {}

async def get_user_pois(user_id: str, supabase=None) -> List[Dict[str, Any]]:
    if supabase:
        try:
            res = supabase.table("poi_items").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
            if res.data:
                return res.data
        except Exception:
            pass
    return POI_POOL_STORE.get(user_id, [])

async def save_user_poi(user_id: str, item: Dict[str, Any], supabase=None):
    if supabase:
        try:
            supabase.table("poi_items").upsert(item).execute()
        except Exception:
            pass
    
    current = POI_POOL_STORE.setdefault(user_id, [])
    idx = next((i for i, x in enumerate(current) if x.get("id") == item.get("id")), None)
    if idx is not None:
        current[idx] = item
    else:
        current.insert(0, item)

async def delete_user_poi(user_id: str, poi_id: str, supabase=None):
    if supabase:
        try:
            supabase.table("poi_items").delete().eq("id", poi_id).eq("user_id", user_id).execute()
        except Exception:
            pass
    current = POI_POOL_STORE.get(user_id, [])
    POI_POOL_STORE[user_id] = [x for x in current if x.get("id") != poi_id]

@router.get("/poi/all")
async def get_all_pois(
    fastapi_req: Request,
    user_id: Optional[str] = Header(None, alias="X-User-ID"),
    supabase=Depends(get_supabase)
):
    uid = user_id or "guest-session"
    items = await get_user_pois(uid, supabase)
    return items

@router.post("/poi/import-link")
async def import_poi_link(
    fastapi_req: Request,
    req: POIImportLinkRequest,
    user_id: Optional[str] = Header(None, alias="X-User-ID"),
    supabase=Depends(get_supabase)
):
    uid = user_id or "guest-session"
    raw_url = req.url.strip()
    if not raw_url:
        raise HTTPException(status_code=400, detail="請提供有效的 Google 地圖連結")
    
    clean_match = re.search(r'(https?://[^\s]+)', raw_url)
    clean_url = clean_match.group(1).rstrip('.,!?:;"\'。，！？') if clean_match else raw_url

    # 🛡️ Security Sentinel: SSRF 防護與合法位址驗證
    if not is_safe_url(clean_url):
        raise HTTPException(status_code=400, detail="不允許存取私有網路、回環位址或不安全的網址 (SSRF 防護)")

    places = []
    final_url = clean_url
    html_content = ""
    is_placelist = "/placelists/list" in clean_url or "/placelists/" in clean_url

    try:
        # 手動安全追蹤轉址，防禦開放轉址至私有 IP
        async with httpx.AsyncClient(follow_redirects=False, timeout=12.0) as client:
            curr_url = clean_url
            for _ in range(6):
                resp = await client.get(curr_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                })
                if resp.status_code in (301, 302, 303, 307, 308):
                    loc = resp.headers.get("Location")
                    if not loc:
                        break
                    next_url = str(httpx.URL(curr_url).join(loc))
                    if not is_safe_url(next_url):
                        raise HTTPException(status_code=400, detail="轉址目標包含不安全或私有網路位址 (SSRF 防護)")
                    curr_url = next_url
                    continue
                final_url = curr_url
                html_content = resp.text
                if "/placelists/list" in final_url or "/placelists/" in final_url:
                    is_placelist = True
                break
    except HTTPException:
        raise
    except Exception as e:
        print(f"[POI Import] Fetch/Redirect failed: {e}")

    now_ms = int(time.time() * 1000)

    # A. 共享清單 (Placelist / Collection) 提取
    # 🕵️ 優先偵測 Google Maps 集合/清單 Token (!11m2!2s... 或 /placelists/list/...)
    list_token_match = (
        re.search(r'(?:!11m2!2s|/placelists/list/|/maps/placelists/list/)([A-Za-z0-9_-]{16,})', final_url)
        or re.search(r'(?:!11m2!2s|/placelists/list/|/maps/placelists/list/)([A-Za-z0-9_-]{16,})', clean_url)
    )

    if list_token_match:
        list_id = list_token_match.group(1)
        api_url = f"https://www.google.com/maps/preview/entitylist/getlist?authuser=0&hl=zh-TW&gl=tw&pb=!1m4!1s{list_id}!2e1!3m1!1e1!2e2!3e2!4i2000"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(api_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                })
                if resp.status_code == 200:
                    raw_text = resp.text
                    if raw_text.startswith(")]}'"):
                        raw_text = raw_text[4:].strip()
                    list_data = json.loads(raw_text)
                    raw_places = list_data[0][8] if list_data and len(list_data[0]) > 8 and list_data[0][8] else []
                    for p in raw_places:
                        try:
                            title = p[2] if len(p) > 2 and p[2] else ""
                            meta = p[1] if len(p) > 1 and p[1] else []
                            addr = meta[4] if len(meta) > 4 and meta[4] and not str(meta[4]).startswith("http") else None
                            coords = meta[5] if len(meta) > 5 and meta[5] else []
                            lat = float(coords[2]) if len(coords) > 2 and coords[2] is not None else None
                            lng = float(coords[3]) if len(coords) > 3 and coords[3] is not None else None
                            notes = p[3] if len(p) > 3 and p[3] else ""
                            if title and lat is not None and lng is not None:
                                places.append({
                                    "title": title,
                                    "lat": lat,
                                    "lng": lng,
                                    "address": addr,
                                    "user_notes": notes,
                                })
                        except Exception as parse_e:
                            print(f"[POI List Item Parse Error] {parse_e}")
                            continue
        except Exception as e:
            print(f"[POI EntityList Error] {e}")

    # 次級保底：若 entitylist 失敗但為 HTML placelist，則正則萃取
    if not places and is_placelist and html_content:
        title_matches = re.findall(r'"([^"]{2,60})",null,null,null,null,\[null,null,(-?\d+\.\d+),(-?\d+\.\d+)\]', html_content)
        if title_matches:
            for t_match in title_matches:
                t_title, t_lat, t_lng = t_match
                try:
                    lat_f = float(t_lat)
                    lng_f = float(t_lng)
                    if lat_f != 0 and lng_f != 0:
                        clean_title = t_title.encode('utf-8').decode('unicode_escape', 'ignore').replace('"', '').strip()
                        places.append({
                            "title": clean_title,
                            "lat": lat_f,
                            "lng": lng_f,
                            "address": None,
                        })
                except Exception:
                    continue
        else:
            coord_matches = re.findall(r'\[null,\s*null,\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)\]', html_content)
            seen = set()
            idx = 1
            for c_match in coord_matches:
                c_lat, c_lng = c_match
                try:
                    lat_f = float(c_lat)
                    lng_f = float(c_lng)
                    key = f"{lat_f:.4f},{lng_f:.4f}"
                    if key not in seen and lat_f != 0 and lng_f != 0:
                        seen.add(key)
                        places.append({
                            "title": f"口袋景點 #{idx}",
                            "lat": lat_f,
                            "lng": lng_f,
                            "address": None,
                        })
                        idx += 1
                except Exception:
                    continue

    # B. 單點解析提取
    if not places:
        res = await resolve_google_maps_link(clean_url)
        lat = res.get("lat")
        lng = res.get("lng")
        title = res.get("query") or res.get("title")

        if not title and html_content:
            t_match = re.search(r'<title>(.*?)</title>', html_content, re.IGNORECASE)
            if t_match:
                raw_t = t_match.group(1).split(" - Google")[0].split(" - Google 地圖")[0].strip()
                if raw_t and "Google" not in raw_t:
                    title = raw_t

        if (not lat or not lng) and title:
            try:
                geo = await smart_geocode_logic(title, limit=1)
                if geo and len(geo) > 0:
                    lat = geo[0].get("lat")
                    lng = geo[0].get("lng")
            except Exception as e:
                print(f"[POI Import] JIT Geocode fallback failed: {e}")

        if lat and lng:
            # 🛡️ 乾淨地址逆向反查：絕不儲存醜陋的 Raw URL
            clean_addr = None
            try:
                rev = await reverse_geocode_with_photon(float(lat), float(lng))
                if rev and rev.get("address") and rev.get("address") != "Unknown":
                    clean_addr = rev["address"]
            except Exception as rev_err:
                print(f"[POI Import] Reverse geocode error: {rev_err}")

            places.append({
                "title": title or "已儲存地點",
                "lat": float(lat),
                "lng": float(lng),
                "address": clean_addr,
            })

    if not places:
        raise HTTPException(status_code=400, detail="無法自此連結解析任何地點，請確認網址格式")

    saved_items = []
    for p in places:
        raw_addr = p.get("address")
        if raw_addr and (str(raw_addr).startswith("http") or "%" in str(raw_addr)):
            raw_addr = None

        poi_item = {
            "id": f"poi_{uuid.uuid4().hex[:12]}",
            "user_id": uid,
            "title": p["title"],
            "address": raw_addr or p["title"],
            "lat": p["lat"],
            "lng": p["lng"],
            "category": "attraction",
            "rating": None,
            "user_notes": p.get("user_notes") or "",
            "source_url": clean_url,
            "is_pinned": False,
            "pin_color": "#E56E25",
            "created_at": now_ms,
            "updated_at": now_ms
        }
        await save_user_poi(uid, poi_item, supabase)
        saved_items.append(poi_item)

    return {
        "success": True,
        "count": len(saved_items),
        "items": saved_items
    }

@router.post("/poi/add")
async def add_custom_poi(
    fastapi_req: Request,
    req: POICreateRequest,
    user_id: Optional[str] = Header(None, alias="X-User-ID"),
    supabase=Depends(get_supabase)
):
    uid = user_id or "guest-session"
    now_ms = int(time.time() * 1000)
    poi_item = {
        "id": f"poi_{uuid.uuid4().hex[:12]}",
        "user_id": uid,
        "title": req.title,
        "address": req.address or req.title,
        "lat": req.lat,
        "lng": req.lng,
        "google_place_id": req.google_place_id,
        "category": req.category or "attraction",
        "rating": req.rating,
        "user_notes": req.user_notes or "",
        "source_url": req.source_url,
        "is_pinned": bool(req.is_pinned),
        "pin_color": req.pin_color or "#E56E25",
        "created_at": now_ms,
        "updated_at": now_ms
    }
    await save_user_poi(uid, poi_item, supabase)
    return poi_item

@router.patch("/poi/{poi_id}/note")
async def update_poi_note(
    poi_id: str,
    req: POIUpdateNoteRequest,
    fastapi_req: Request,
    user_id: Optional[str] = Header(None, alias="X-User-ID"),
    supabase=Depends(get_supabase)
):
    uid = user_id or "guest-session"
    items = await get_user_pois(uid, supabase)
    item = next((x for x in items if x.get("id") == poi_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="找不到該景點")
    
    item["user_notes"] = req.note
    item["updated_at"] = int(time.time() * 1000)
    await save_user_poi(uid, item, supabase)
    return item

@router.patch("/poi/{poi_id}/pin")
async def toggle_poi_pin(
    poi_id: str,
    req: POITogglePinRequest,
    fastapi_req: Request,
    user_id: Optional[str] = Header(None, alias="X-User-ID"),
    supabase=Depends(get_supabase)
):
    uid = user_id or "guest-session"
    items = await get_user_pois(uid, supabase)
    item = next((x for x in items if x.get("id") == poi_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="找不到該景點")
    
    item["is_pinned"] = req.is_pinned
    item["updated_at"] = int(time.time() * 1000)
    await save_user_poi(uid, item, supabase)
    return item

@router.patch("/poi/{poi_id}/category")
async def update_poi_category(
    poi_id: str,
    req: POIUpdateCategoryRequest,
    fastapi_req: Request,
    user_id: Optional[str] = Header(None, alias="X-User-ID"),
    supabase=Depends(get_supabase)
):
    uid = user_id or "guest-session"
    items = await get_user_pois(uid, supabase)
    item = next((x for x in items if x.get("id") == poi_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="找不到該景點")
    
    item["category"] = req.category
    item["updated_at"] = int(time.time() * 1000)
    await save_user_poi(uid, item, supabase)
    return item


@router.delete("/poi/{poi_id}")
async def delete_poi(
    poi_id: str,
    fastapi_req: Request,
    user_id: Optional[str] = Header(None, alias="X-User-ID"),
    supabase=Depends(get_supabase)
):
    uid = user_id or "guest-session"
    await delete_user_poi(uid, poi_id, supabase)
    return {"success": True}
