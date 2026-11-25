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
from urllib.parse import urlparse, unquote

from fastapi import APIRouter, Depends, HTTPException, Request, Header, Query
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
from utils.limiter import limiter
from utils.url_safety import is_safe_url, is_safe_url_async, create_safe_client, SSRFSecurityError
from services.link_resolver import (
    resolve_google_maps_link,
    resolve_google_maps_placelist,
    _is_google_shortlink,
)
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
from services.model_manager import (
    call_extraction,
    NonRetryableAuthError,
    NonRetryableRequestError,
    AllModelsFailedError,
    map_ai_exception_to_http_status,
)
from utils.poi_utils import generate_v2_cache_key

router = APIRouter(prefix="/api", tags=["poi"])

# 🆕 Phase 2 Cache (Process-level with v2 versioning)
POI_ENRICH_CACHE: Dict[str, Dict] = {}


def __resetPoiEnrichCacheForTesting() -> None:
    """重置 POI_ENRICH_CACHE 測試輔助函數（原地 clear，維持模組引用契約）。"""
    POI_ENRICH_CACHE.clear()


class PoiResolveLinkRequest(BaseModel):
    url: str


@router.post("/poi/resolve-link")
@limiter.limit("30/minute")
async def poi_resolve_link(request: Request, body: PoiResolveLinkRequest):
    """
    🔗 全局 POI 網址解析端點 (Universal Link-to-Pin Engine)
    支援：
    1. Google Maps 單一景點網址（短網址、長網址、搜尋網址）
    2. Google Maps 共享清單 (Placelists / Saved Lists)
    回傳洗滌後的乾淨繁中地名、門牌地址、座標與備註陣列。
    """
    raw_url = (body.url or "").strip()
    if not raw_url:
        raise HTTPException(status_code=400, detail="Missing url parameter")
        
    # 預防前端未處理直接送出包含雜質的整段文字
    url_match = re.search(r'(https?://[^\s]+)', raw_url)
    clean_url = url_match.group(1).rstrip('.,!?:;"\'。，！？') if url_match else raw_url

    # 🛡️ SSRF 防護守門 (non-blocking DNS bulkhead)
    if not await is_safe_url_async(clean_url):
        raise HTTPException(status_code=400, detail="Disallowed target URL (SSRF Blocked)")

    is_placelist = "/placelists/list" in clean_url or "/placelists/" in clean_url or "!11m2!2s" in clean_url
    
    # 針對短網址判斷是否可能重定向為清單 (嚴格主機名檢查 + 串流不緩衝 body)
    if not is_placelist and _is_google_shortlink(clean_url):
        try:
            # 🛡️ 對齊下游清單 RPC 超時閾值 (12.0s)，防範行動網路下過早放棄造成誤導流至單點 POI
            async with create_safe_client(follow_redirects=True, timeout=12.0) as client:
                async with client.stream("GET", clean_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                }) as head_resp:
                    final_traced_url = str(head_resp.url)
                if "/placelists/list" in final_traced_url or "/placelists/" in final_traced_url or "!11m2!2s" in final_traced_url:
                    is_placelist = True
                    clean_url = final_traced_url
        except SSRFSecurityError:
            raise HTTPException(status_code=400, detail="Disallowed target URL (SSRF Blocked)")
        except Exception as e:
            print(f"[poi_resolve_link] Head redirect trace error: {e}")

    # A. 共享清單解析 (Placelist)
    if is_placelist:
        res = await resolve_google_maps_placelist(clean_url)
        if not res.get("success") or not res.get("items"):
            error_detail = res.get("error") or "無法從該清單提取地點，請確認清單設為公開或有分享權限"
            raise HTTPException(status_code=422, detail=error_detail)
        return {
            "success": True,
            "mode": "placelist",
            "title": res.get("title", "Google 地圖清單"),
            "count": len(res["items"]),
            "items": res["items"]
        }

    # B. 單一景點解析 (Single POI)
    single_res = await resolve_google_maps_link(clean_url)
    if not single_res.get("lat") or not single_res.get("lng"):
        raise HTTPException(status_code=422, detail="無法從該網址提取有效經緯度座標")

    title = single_res.get("metadata", {}).get("title") or single_res.get("query") or "已儲存地點"
    address = single_res.get("address")
    image_url = single_res.get("metadata", {}).get("image")

    item = {
        "title": title,
        "address": address,
        "lat": single_res["lat"],
        "lng": single_res["lng"],
        "category": "attraction",
        "user_notes": None,
        "source_url": clean_url,
        "image_url": image_url
    }

    return {
        "success": True,
        "mode": "single",
        "title": title,
        "count": 1,
        "items": [item]
    }


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
        locale = request.locale or "zh"
        is_en = bool(str(locale).strip().lower().startswith("en"))

        # 🆕 Step 3: 快取檢查 (v2 versioned + locale partitioned)
        cache_key = generate_v2_cache_key(
            name=request.name,
            lat=request.lat,
            lng=request.lng,
            poi_id=request.poi_id,
            wikidata_id=request.wikidata_id,
            locale=locale,
        )
        
        if cache_key in POI_ENRICH_CACHE:
            print(f"⚡ [Cache Hit] {cache_key}")
            return POI_ENRICH_CACHE[cache_key]

        api_key = (request.api_key or "").strip()
        has_api_key = bool(api_key)

        print(f"🔍 [POI Enrich] 開始抓取與摘要: {request.name} (Wiki + {'AI' if has_api_key else 'Wiki-Only Fallback'}, locale={locale})...")

        if has_api_key:
            lang_label = "English summary" if is_en else "Traditional Chinese summary"
            prompt = f"""
You are a travel guide assistant. Search the web for reviews and vibes for:
- Name: {request.name}
- Type: {request.type}
- Location: {request.lat}, {request.lng}

Output in this EXACT JSON format ({lang_label}):
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
        else:
            ai_task = asyncio.sleep(0, result=None)

        wiki_task = enrich_poi_complete({
            "name": request.name,
            "wikidata_id": request.wikidata_id or "",
            "lat": request.lat,
            "lng": request.lng
        }, getattr(fastapi_req.app.state, "client", None), lang="en" if is_en else "zh")

        ai_result, wiki_result = await asyncio.gather(ai_task, wiki_task, return_exceptions=True)

        # 1. 處理 AI 摘要結果
        ai_data = {}
        ai_warning: Optional[str] = None
        if not has_api_key:
            ai_warning = "NO_API_KEY"
        elif isinstance(ai_result, NonRetryableAuthError):
            raise ai_result
        elif isinstance(ai_result, Exception):
            print(f"⚠️ [POI Enrich] AI 調用失敗 ({request.name}): {type(ai_result).__name__}: {ai_result}")
            ai_warning = "AI_UNAVAILABLE"
        elif isinstance(ai_result, str) and ai_result.strip():
            json_match = re.search(r'\{[\s\S]*\}', ai_result)
            if json_match:
                try:
                    ai_data = json.loads(json_match.group())
                except Exception as je:
                    print(f"⚠️ [POI Enrich] AI JSON 解析失敗 ({request.name}): {je} | snippet={ai_result[:160]!r}")
                    ai_data = {"summary": ai_result.strip()[:200]}
            else:
                ai_data = {"summary": ai_result.strip()[:200]}
        else:
            print(f"⚠️ [POI Enrich] AI 回傳空內容 ({request.name})")
            ai_warning = "AI_EMPTY_OUTPUT"

        # 2. 處理 Wiki 結果
        if isinstance(wiki_result, Exception):
            wiki_result = {
                "status": "PARTIAL_SUCCESS",
                "warnings": ["WIKI_SYSTEM_ERROR"],
                "cultural_desc": None,
                "travel_tips": None
            }

        # 🆕 Phase 5.2: AI Translation Fallback (雙語對齊 — 僅在持有有效 API Key 時執行)
        resolved_lang = wiki_result.get("resolved_language", "zh-TW")
        cultural_desc = wiki_result.get("cultural_desc")

        if has_api_key and is_en:
            if cultural_desc and not str(resolved_lang).lower().startswith("en"):
                print(f"🌐 [AI Translate] Translating {resolved_lang} to en...")
                translation_prompt = f"Translate the following Wikipedia description into natural, fluent English with a professional travel guide tone:\n\n{cultural_desc}"
                try:
                    translated = await call_extraction(
                        api_key=api_key,
                        prompt=translation_prompt,
                        intent_type="SUMMARIZE"
                    )
                    if translated and translated.strip():
                        wiki_result["cultural_desc"] = translated.strip()
                        wiki_result["resolved_language"] = f"en (translated from {resolved_lang})"
                except Exception as te:
                    print(f"⚠️ Translation failed: {te}")
        elif has_api_key:
            if cultural_desc and resolved_lang != "zh-TW" and not str(resolved_lang).startswith("zh"):
                print(f"🌐 [AI Translate] Translating {resolved_lang} to zh-TW...")
                translation_prompt = f"請將以下維基百科描述翻譯為繁體中文（zh-TW），保持旅遊指南的專業語氣：\n\n{cultural_desc}"
                try:
                    translated = await call_extraction(
                        api_key=api_key,
                        prompt=translation_prompt,
                        intent_type="SUMMARIZE"  # Use SUMMARIZE for simple translation tasks to avoid schema overhead
                    )
                    if translated and translated.strip():
                        wiki_result["cultural_desc"] = translated.strip()
                        wiki_result["resolved_language"] = f"zh-TW (translated from {resolved_lang})"
                except Exception as te:
                    print(f"⚠️ Translation failed: {te}")

        # 3. 數據合流與保底鏈 (Summary Fallback Chain)
        default_summary = f"{request.name} is a notable local point of interest." if is_en else f"{request.name} 是位於當地的地點。"
        final_summary = ai_data.get("summary") or wiki_result.get("cultural_desc") or default_summary

        # 4. 狀態判定
        ai_success = bool(ai_data.get("summary"))
        wiki_status = wiki_result.get("status", "FAILED")

        final_status = "SUCCESS"
        if not ai_success or wiki_status != "SUCCESS":
            final_status = "PARTIAL_SUCCESS"
        if not ai_success and wiki_status == "FAILED":
            final_status = "FAILED"

        merged_warnings = list(wiki_result.get("warnings") or [])
        if ai_warning and ai_warning not in merged_warnings:
            merged_warnings.append(ai_warning)

        result_payload = {
            "summary": final_summary,
            "must_try": ai_data.get("must_try") or [],
            "rating": ai_data.get("rating") or 0,
            "business_status": ai_data.get("business_status") or "UNKNOWN",
            "cultural_desc": wiki_result.get("cultural_desc"),
            "travel_tips": wiki_result.get("travel_tips"),
            "resolved_language": wiki_result.get("resolved_language") or ("en" if is_en else "zh-TW"),
            "image_url": wiki_result.get("image_url"), # 🆕 Phase 5.4: Expose image
            "status": final_status,
            "warnings": merged_warnings,
            "official_url": wiki_result.get("official_url"),
            "ai_key_missing": not has_api_key,
        }

        # 🆕 Step 3: 快取存儲 (僅在完全成功 SUCCESS 且有 Key 時存儲，不快取缺 Key 或 PARTIAL 狀態)
        if final_status == "SUCCESS" and has_api_key:
            POI_ENRICH_CACHE[cache_key] = result_payload
            
        print(f"✅ [POI Enrich] 完成: {request.name} (Status: {final_status})")
        return result_payload
        
    except HTTPException:
        raise
    except (NonRetryableAuthError, NonRetryableRequestError, AllModelsFailedError) as e:
        is_en_err = bool(request.locale and str(request.locale).strip().lower().startswith("en"))
        status_code, _, detail = map_ai_exception_to_http_status(e, is_en=is_en_err)
        raise HTTPException(status_code=status_code, detail=detail)
    except Exception as e:
        print(f"🔥 AI POI 整合失敗：{e}")
        raise HTTPException(
            status_code=500,
            detail="AI enrichment temporarily unavailable" if request.locale and str(request.locale).strip().lower().startswith("en") else "AI 增強失敗，請稍後重試"
        )


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
        
        enriched = await enrich_poi_complete(
            poi,
            getattr(fastapi_req.app.state, "client", None),
            lang="en" if str(body.locale or "zh").strip().lower().startswith("en") else "zh",
        )
        formatted = format_enriched_poi_for_ai(enriched, locale=body.locale or "zh")
        
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
        pois = await search_poi_combined(lat, lng, category, radius, timeout=2.5)
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
    locale = request.locale or "zh"
    is_en = bool(str(locale).strip().lower().startswith("en"))
    if not request.pois:
        return {
            "recommendation": (
                "No nearby places found. Please try another category or expand the search radius."
                if is_en
                else "附近沒有找到相關地點，請嘗試其他類別或擴大搜索範圍。"
            )
        }
    
    if not request.api_key:
        raise HTTPException(status_code=400, detail="API key required")
    
    try:
        # Step 1: 格式化 POI 為精簡文字
        pois_text = format_pois_for_ai(request.pois, max_items=5, locale=locale)
        print(f"🤖 [POI Recommend] 正在為 {len(request.pois)} 個地點進行 AI 推薦評估...")
        
        # Step 2: 生成精簡 prompt
        prompt = get_ai_prompt_for_recommendation(
            pois_text,
            request.user_query,
            request.user_preferences,
            locale=locale,
        )
        
        # 🆕 v5.0: 使用 call_extraction 獲得 3 層降級保護
        from services.model_manager import call_extraction
        from utils.ai_config import DAILY_ROUTING
        
        recommendation_text = await call_extraction(
            request.api_key, prompt,
            intent_type="POI_RECOMMEND",
            routing_strategy=DAILY_ROUTING,
        )
        if not recommendation_text or not recommendation_text.strip():
            raise HTTPException(
                status_code=503,
                detail="AI recommendation returned empty response" if is_en else "AI 推薦回傳空白內容，請稍後重試",
            )
        
        print(f"✅ [POI Recommend] AI 推薦完成")
        return {
            "recommendation": recommendation_text.strip(),
            "pois_count": len(request.pois),
            "token_optimized": True
        }
        
    except HTTPException:
        raise
    except (NonRetryableAuthError, NonRetryableRequestError, AllModelsFailedError) as e:
        status_code, _, detail = map_ai_exception_to_http_status(e, is_en=is_en)
        raise HTTPException(status_code=status_code, detail=detail)
    except Exception as e:
        print(f"🔥 POI Recommend Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/poi/categories")
async def get_poi_categories(locale: str = Query("zh")):
    """📋 取得支援的 POI 類別列表"""
    is_en = bool(str(locale or "zh").strip().lower().startswith("en"))
    if is_en:
        return {
            "categories": [
                {"id": "department_store", "name": "Department Store", "icon": "🏬"},
                {"id": "restaurant", "name": "Restaurants & Dining", "icon": "🍽️"},
                {"id": "convenience", "name": "Convenience Store", "icon": "🏪"},
                {"id": "supermarket", "name": "Supermarket", "icon": "🛒"},
                {"id": "pharmacy", "name": "Pharmacy & Drugstore", "icon": "💊"},
                {"id": "popular", "name": "Popular Attractions", "icon": "🔥"}
            ]
        }
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
            max_results=request.max_results,
            locale=request.locale or "zh"
        )
        
        return result
        
    except HTTPException:
        raise
    except (NonRetryableAuthError, NonRetryableRequestError, AllModelsFailedError) as e:
        is_en_ss = bool(request.locale and str(request.locale).strip().lower().startswith("en"))
        status_code, _, detail = map_ai_exception_to_http_status(e, is_en=is_en_ss)
        raise HTTPException(status_code=status_code, detail=detail)
    except Exception as e:
        print(f"🔥 Smart Search Error: {e}")
        raise HTTPException(status_code=500, detail=f"Smart search failed: {str(e)}")

# ═══════════════════════════════════════════════════════════════════════════════
# Media Proxy (Phase 5.4)
# ═══════════════════════════════════════════════════════════════════════════════

_MEDIA_PROXY_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_MEDIA_PROXY_CSP = "script-src 'none'; frame-src 'none'; sandbox;"


@router.get("/poi/media-proxy")
@limiter.limit("30/minute")
async def media_proxy(request: Request, url: str):
    """
    🖼️ 媒體代理端點 - 解決維基百科圖片的 CORS 與 Referrer 限制
    防禦：嚴格 upload.wikimedia.org 主機白名單、阻斷 SVG/SVGZ 與非圖片 MIME、
    10 MB Content-Length 預檢與串流上限、Vercel Next.js 級別 sandbox CSP。
    """
    raw_url = (url or "").strip()
    if not raw_url or any(ord(ch) < 32 or ord(ch) == 127 for ch in raw_url):
        raise HTTPException(status_code=400, detail="Invalid media source")
    try:
        parsed = urlparse(raw_url)
        port = parsed.port
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid media source")
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != "upload.wikimedia.org"
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or not parsed.path.startswith("/")
    ):
        raise HTTPException(status_code=400, detail="Invalid media source")

    # 阻斷直連 .svg / .svgz（含百分比編碼如 .%73vg、%2esvg 及尾端斜線；保留 PNG 渲染縮圖如 .../320px-Flag.svg.png）
    decoded_path = unquote(unquote(parsed.path)).rstrip("/").lower()
    if decoded_path.endswith((".svg", ".svgz")):
        raise HTTPException(status_code=415, detail="Unsupported media type: SVG is not allowed")

    headers = {
        "User-Agent": "RyanTravelApp/1.2 (https://www.tabijiapp.com)",
        "Referer": "https://www.wikipedia.org/",
    }
    timeout = httpx.Timeout(10.0, connect=5.0, read=15.0, write=5.0, pool=5.0)
    client = create_safe_client(follow_redirects=False, timeout=timeout)
    upstream_resp: Optional[httpx.Response] = None
    async def _cleanup_upstream() -> None:
        try:
            if upstream_resp is not None:
                await upstream_resp.aclose()
        finally:
            await client.aclose()

    try:
        req = client.build_request("GET", raw_url, headers=headers)
        upstream_resp = await client.send(req, stream=True)

        if upstream_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Upstream media unavailable")

        raw_ct = upstream_resp.headers.get("Content-Type", "")
        media_type = raw_ct.split(";", 1)[0].strip().lower()
        if not media_type.startswith("image/") or "svg" in media_type or "xml" in media_type:
            raise HTTPException(status_code=415, detail="Unsupported upstream media type")

        raw_cl = upstream_resp.headers.get("Content-Length")
        if raw_cl:
            try:
                if int(raw_cl.strip()) > _MEDIA_PROXY_MAX_BYTES:
                    raise HTTPException(status_code=413, detail="Upstream media exceeds size limit")
            except ValueError:
                pass
    except HTTPException:
        await _cleanup_upstream()
        raise
    except SSRFSecurityError:
        await _cleanup_upstream()
        raise HTTPException(status_code=400, detail="Invalid media source")
    except httpx.TimeoutException:
        await _cleanup_upstream()
        raise HTTPException(status_code=504, detail="Upstream media timeout")
    except httpx.HTTPError:
        await _cleanup_upstream()
        raise HTTPException(status_code=502, detail="Upstream media fetch failed")
    except Exception:
        await _cleanup_upstream()
        raise HTTPException(status_code=502, detail="Upstream media proxy error")
    except BaseException:
        await _cleanup_upstream()
        raise

    async def stream_image():
        total = 0
        try:
            async for chunk in upstream_resp.aiter_bytes(chunk_size=65536):
                if not chunk:
                    continue
                remaining = _MEDIA_PROXY_MAX_BYTES - total
                if remaining <= 0:
                    break
                if len(chunk) > remaining:
                    yield chunk[:remaining]
                    break
                total += len(chunk)
                yield chunk
        finally:
            await _cleanup_upstream()

    return StreamingResponse(
        stream_image(),
        media_type=media_type,
        headers={
            "Content-Security-Policy": _MEDIA_PROXY_CSP,
            "X-Content-Type-Options": "nosniff",
        },
    )


