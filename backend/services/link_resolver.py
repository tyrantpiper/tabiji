import httpx
import asyncio
import re
import os
import json
import random
import time as _time
from urllib.parse import unquote, unquote_plus
import urllib.parse  # Keep original for other uses if any
from bs4 import BeautifulSoup
from typing import Dict, Any
from datetime import datetime

from utils.url_safety import is_safe_url, is_safe_url_async, create_safe_client, SSRFSecurityError

# 🆕 v35.26: Anti-Acidosis Protocol - Smart Redirect Tracer
from utils.smart_redirect_tracer import get_smart_tracer
from utils.molecular_parser import get_molecular_parser

_GOOGLE_SHORTLINK_HOSTS = frozenset({"goo.gl", "www.goo.gl", "maps.app.goo.gl"})
_MAX_HTML_BYTES = 2 * 1024 * 1024  # 2 MB cap for HTML/OG scraping


def _is_google_shortlink(url: str) -> bool:
    """Strict hostname check for Google Maps shortlinks (blocks substring spoofing such as evil.com/?r=goo.gl)."""
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception:
        return False
    if parsed.scheme.lower() not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    return host in _GOOGLE_SHORTLINK_HOSTS


def _strip_tracking_params(url: str) -> str:
    """Strip g_st / si / utm_* tracking params cleanly without corrupting remaining query delimiters."""
    try:
        parts = urllib.parse.urlsplit(url)
        if not parts.query:
            return url.rstrip("?&")
        filtered = [
            (k, v)
            for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in ("g_st", "si") and not k.lower().startswith("utm_")
        ]
        new_query = urllib.parse.urlencode(filtered, doseq=True)
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
    except Exception:
        return url


async def _read_bounded_text(resp: httpx.Response, max_bytes: int = _MAX_HTML_BYTES) -> str:
    """Read at most `max_bytes` from a streaming httpx.Response and decode safely with LookupError fallback."""
    buf = bytearray()
    async for chunk in resp.aiter_bytes(chunk_size=65536):
        if not chunk:
            continue
        remaining = max_bytes - len(buf)
        if remaining <= 0:
            break
        if len(chunk) > remaining:
            buf.extend(chunk[:remaining])
            break
        buf.extend(chunk)
        if len(buf) >= max_bytes:
            break
    encoding = resp.encoding or "utf-8"
    try:
        return bytes(buf).decode(encoding, errors="replace")
    except LookupError:
        return bytes(buf).decode("utf-8", errors="replace")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🛰️ GAS Two-Shot Rescue Gateway (Failure-Only Fallback)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_GAS_RESOLVE_DEAD_CACHE: Dict[str, float] = {}


def __reset_link_resolver_caches_for_testing() -> None:
    """顯式重置 GAS 解析冷宮快取，供單元測試隔離狀態。"""
    _GAS_RESOLVE_DEAD_CACHE.clear()


def _mask_gas_url_id(gas_url: str) -> str:
    """日誌脫敏：僅輸出 GAS 部署 ID 結尾 4 碼，嚴禁印出完整 GAS 網址。"""
    try:
        path = urllib.parse.urlsplit(gas_url or "").path.rstrip("/")
        parts = [p for p in path.split("/") if p]
        if parts and parts[-1] in ("exec", "dev") and len(parts) >= 2:
            token = parts[-2]
        elif parts:
            token = parts[-1]
        else:
            token = ""
        return f"***{token[-4:]}" if len(token) >= 4 else "***"
    except Exception:
        return "***"


async def resolve_via_gas(short_url: str) -> Dict[str, Any] | None:
    """
    🛰️ GAS Rescue: 只在所有本地引擎失敗後才啟動。
    利用 GAS 的 google-apps-script User-Agent 繞過 Google 機器人偵測，
    取得本地 httpx 無法拿到的座標與地名。
    
    Two-Shot 策略：
      Shot 1: followRedirects=false → 攔截 Location Header 取座標
      Shot 2: followRedirects=true  → 抓 HTML <title> 取地名
    
    Returns:
        成功: {"lat": float, "lng": float, "title": str|None, ...}
        失敗: None
    """
    urls_str = os.getenv("GAS_RESOLVE_LINK_URLS", "").strip()
    if not urls_str:
        return None
    
    urls = [u.strip() for u in urls_str.split(",") if u.strip()]
    if not urls:
        return None
    
    random.shuffle(urls)  # Load balancing
    now = _time.time()
    
    for gas_url in urls:
        # Dead URL cache (12h penalty)
        if gas_url in _GAS_RESOLVE_DEAD_CACHE and (now - _GAS_RESOLVE_DEAD_CACHE[gas_url] < 43200):
            continue
        
        try:
            # GAS Web Apps return 302 redirects → must follow them
            # 🛡️ 2026 Emergency: Disable SSL verify only in development for internal GAS rescue gateway
            should_verify_ssl = os.getenv("ENVIRONMENT") != "development"
            async with create_safe_client(follow_redirects=True, timeout=15.0, verify=should_verify_ssl) as client:
                res = await client.get(gas_url, params={"url": short_url})
            res.raise_for_status()
            data = res.json()
            
            if data and data.get("success") and data.get("lat"):
                print(f"[GAS Rescue] OK ({data['lat']}, {data['lng']}) title={data.get('title')}")
                return {
                    "lat": float(data["lat"]),
                    "lng": float(data["lng"]),
                    "title": data.get("title"),
                    "titleReliable": data.get("titleReliable", False),
                    "longUrl": data.get("longUrl", short_url),
                    "method": "gas_rescue"
                }
            elif data and "quota" in str(data.get("error", "")).lower():
                print(f"[GAS Rescue] Endpoint {_mask_gas_url_id(gas_url)} quota exceeded. Banning URL for 12 hours.")
                _GAS_RESOLVE_DEAD_CACHE[gas_url] = now
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response is not None else None
            tag = _mask_gas_url_id(gas_url)
            if status_code in (404, 410):
                _GAS_RESOLVE_DEAD_CACHE[gas_url] = now
                print(f"[GAS Rescue] Endpoint {tag} returned HTTP {status_code}. Banning URL for 12 hours.")
            else:
                print(f"[GAS Rescue] Endpoint {tag} returned HTTP {status_code}.")
            continue
        except Exception as e:
            print(f"[GAS Rescue] Request failed ({_mask_gas_url_id(gas_url)}): {type(e).__name__}")
            continue
    
    return None


# Regex for coordinates in URLs
# Pattern A: @lat,lng
RE_COORD_A = re.compile(r'@(-?\d+\.\d+),(-?\d+\.\d+)')
# Pattern B: !3dlat!4dlng (Protobuf style)
RE_COORD_B = re.compile(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)')
# Pattern C: search?q=... or ?query=...
RE_QUERY = re.compile(r'[?&](?:q|query|place_name)=([^&]+)')
# Pattern D: /place/NAME/... or /search/NAME/... (Modern Google Maps Path Style)
RE_PLACE_PATH = re.compile(r'/place/([^/@]+)')
RE_SEARCH_PATH = re.compile(r'/search/([^/?&]+)')
# Pattern F: staticmap?center=lat,lng (Metadata extraction)
RE_STATICMAP = re.compile(r'center=(-?\d+\.\d+)(?:%2C|,)(-?\d+\.\d+)')

def extract_address_from_description(desc: str) -> str | None:
    """從 Google Maps 的 og:description 提取真實門牌 (例如: '老新台菜 · 807台灣高雄市三民區九如二路227號')"""
    if not desc or not isinstance(desc, str):
        return None
    # 匹配包含郵遞區號或市/區/路/街/號的片段
    match = re.search(r'·\s*([0-9\u4e00-\u9fa5]+(?:市|縣|區|鄉|鎮)[^\s·]+[路街巷弄號樓][^\s·]*)', desc)
    if match:
        return match.group(1).strip()
    parts = [p.strip() for p in desc.split('·')]
    for p in parts[1:]:
        if any(k in p for k in ["市", "縣", "區", "鄉", "鎮", "路", "街", "號"]):
            return p
    return None

ADDRESS_POI_PATTERN = re.compile(
    r'^(\d{3,5})?'
    r'([台臺]灣)?'
    r'([台臺]北市|[台臺]中市|基隆市|[台臺]南市|高雄市|新北市|桃園市|新竹市|嘉義市|[^\s區縣市]+[縣市])'
    r'([^\s區鄉鎮市]+[區鄉鎮市])?'
    r'([^\s里村]+[里村])?'
    r'([^\s號樓]+(?:路|街|大道|巷|弄)[^\s號樓]*\d+號(?:之\d+)?(?:[^\s號樓]*樓)?)'
    r'(.*)$'
)

def split_taiwan_address_and_poi(raw_text: str) -> tuple[str | None, str | None]:
    """將混雜字串純粹分離為 (純門牌地址, 純景點名稱)"""
    if not raw_text or not isinstance(raw_text, str):
        return None, None
    clean_text = raw_text.strip()
    m = ADDRESS_POI_PATTERN.search(clean_text)
    if not m:
        return None, clean_text
    zip_code, country, city, dist, village, road_no, poi_name = m.groups()
    full_address = f"{city}{dist or ''}{road_no}"
    clean_poi_name = (poi_name or '').strip()
    if not clean_poi_name:
        return full_address, clean_text
    return full_address, clean_poi_name

def parse_google_place_rpc_payload(rpc_text: str) -> dict | None:
    """解析 Google Maps Web preview/place RPC 回傳的結構化資料包 (含邊界與變異容錯防禦)"""
    if not rpc_text or not isinstance(rpc_text, str):
        return None
    try:
        clean_json = re.sub(r"^\)]\}'\s*", "", rpc_text).strip()
        data = json.loads(clean_json)
        if not isinstance(data, list) or len(data) <= 6 or not isinstance(data[6], list):
            return None
        d6 = data[6]
        pure_name = d6[11] if len(d6) > 11 and isinstance(d6[11], str) else None
        
        lat = None
        lng = None
        if len(d6) > 9 and isinstance(d6[9], list) and len(d6[9]) > 3:
            lat = d6[9][2]
            lng = d6[9][3]
            
        if lat is None or lng is None:
            return None
            
        address = None
        if len(d6) > 39 and isinstance(d6[39], str):
            address = d6[39]
        elif len(d6) > 2 and isinstance(d6[2], list) and len(d6[2]) > 0 and isinstance(d6[2][0], str):
            address = d6[2][0]
            
        place_id = None
        def find_place_id(obj):
            nonlocal place_id
            if place_id:
                return
            if isinstance(obj, list):
                for item in obj:
                    find_place_id(item)
            elif isinstance(obj, str):
                if re.match(r'^ChIJ[A-Za-z0-9_-]{20,}$', obj):
                    place_id = obj
        find_place_id(d6)
        
        return {
            "lat": float(lat),
            "lng": float(lng),
            "title": pure_name,
            "address": address,
            "place_id": place_id
        }
    except Exception:
        return None


async def fetch_place_from_google_rpc(cid_hex: str) -> dict | None:
    """透過未公開 Google Web RPC 提取精確物理座標與純地名 (0成本，非付費 API)"""
    try:
        cid_dec = int(cid_hex, 16)
        cid_url = f"https://www.google.com/maps?cid={cid_dec}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8"
        }
        async with create_safe_client(follow_redirects=True, timeout=3.5) as client:
            resp = await client.get(cid_url, headers=headers)
            if resp.status_code != 200:
                return None
            m = re.search(r'href="(/maps/preview/place\?[^"]+)"', resp.text)
            if not m:
                return None
            rpc_url = f"https://www.google.com{m.group(1).replace('&amp;', '&')}"
            rpc_resp = await client.get(rpc_url, headers=headers)
            if rpc_resp.status_code != 200:
                return None
            return parse_google_place_rpc_payload(rpc_resp.text)
    except Exception as e:
        print(f"[PlaceRPC] Extraction skipped/failed: {e}")
        return None


async def fetch_og_metadata(url: str) -> Dict[str, Any]:
    """
    Scrapes Open Graph metadata from a URL.
    對社群媒體網址（IG/Threads/FB 等）啟用 facebookexternalhit UA、登入牆過濾與 IG Embed 救援。
    """
    from services.web_search_engine import (
        SOCIAL_MEDIA_PATTERN,
        _is_social_login_wall,
        _is_instagram_url,
        fetch_instagram_embed,
    )

    metadata = {
        "title": None,
        "image": None,
        "description": None,
        "site_name": None
    }
    is_social = bool(SOCIAL_MEDIA_PATTERN.search(url or ""))
    is_ig = _is_instagram_url(url)

    async def _try_ig_embed_rescue() -> None:
        if not is_ig:
            return
        embed = await fetch_instagram_embed(url, timeout=2.0)
        if not embed:
            return
        if not metadata["title"] and embed.get("title"):
            metadata["title"] = embed["title"]
        if not metadata["description"] and embed.get("description"):
            metadata["description"] = embed["description"]
        if not metadata["image"] and embed.get("image"):
            metadata["image"] = embed["image"]
        if not metadata["site_name"]:
            metadata["site_name"] = "Instagram"

    try:
        if is_social:
            headers = {
                "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
                "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
            }
        else:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
            }
        # 🛡️ SSRF Check (non-blocking DNS bulkhead)
        if not await is_safe_url_async(url):
            print(f"[SSRF Block] Metadata fetch aborted for unsafe URL: {url}")
            return metadata

        async with create_safe_client(follow_redirects=True, timeout=5.0) as client:
            non_200 = False
            async with client.stream("GET", url, headers=headers) as resp:
                if resp.status_code != 200:
                    non_200 = True
                else:
                    html_text = await _read_bounded_text(resp)

            if non_200:
                if is_ig:
                    await _try_ig_embed_rescue()
                return metadata

            soup = BeautifulSoup(html_text, 'html.parser')
            
            # 1. 提取 OG 標籤
            og_title = soup.find("meta", property="og:title")
            og_image = soup.find("meta", property="og:image")
            og_desc = soup.find("meta", property="og:description")
            og_site = soup.find("meta", property="og:site_name")
            
            if og_title:
                metadata["title"] = og_title.get("content")
            if og_image:
                metadata["image"] = og_image.get("content")
            if og_desc:
                metadata["description"] = og_desc.get("content")
            if og_site:
                metadata["site_name"] = og_site.get("content")

            # 2. 額外標籤支援 (twitter, thumbnail, itemprop)
            if not metadata["image"]:
                for tag in ["twitter:image", "image_src", "thumbnail"]:
                    found = soup.find("meta", attrs={"name": tag}) or soup.find("link", attrs={"rel": tag})
                    if found:
                        metadata["image"] = found.get("content") or found.get("href")
                        break
            
            if not metadata["image"]:
                itemprop_image = soup.find("meta", itemprop="image")
                if itemprop_image:
                    metadata["image"] = itemprop_image.get("content")

            # 3. Engine 2 - 深度獵捕 (Deep Scraper Regex Probe)
            if not metadata["image"] and "google.com/maps" in url:
                # 搜尋埋藏在 JS 中的高畫質圖片模式 (重用已讀取之 bounded html_text，避免 ResponseNotRead)
                lh_matches = re.findall(r'https://lh\d\.googleusercontent\.com/p/[^\\"]+=w\d+-h\d+', html_text)
                if lh_matches:
                    best_match = lh_matches[0]
                    # 重寫為 1000x800 高清格式
                    metadata["image"] = re.sub(r'=w\d+-h\d+', '=w1000-h800-k-no', best_match)
                    print(f"[DeepScraper] Found photo buried in JS: {metadata['image']}")

            # 4. URL 正規化與過濾 (Protocol-relative & Generic Icon)
            if metadata["image"]:
                if metadata["image"].startswith("//"):
                    metadata["image"] = "https:" + metadata["image"]
                
                generic_icons = [
                    "maps_512dp.png", 
                    "maps_icon_60.png",
                    "place_api/icons/",
                    "play-lh.googleusercontent.com",
                    "/images/branding/product/"
                ]
                if any(icon in metadata["image"] for icon in generic_icons):
                    print(f"[Filter] Generic Google Maps logo skipped: {metadata['image']}")
                    metadata["image"] = None
                
                # 🆕 v35.94: Metadata Coordinate Extraction (Tier 2.5)
                # 🛡️ 封殺純 ?q= 網址之 staticmap 概覽中心 (消除美中 Nebraska 與城市預設中心假座標)
                is_pure_query = bool(RE_QUERY.search(url)) and not bool(re.search(r'!3d-?\d+\.\d+!4d-?\d+\.\d+', url))
                if metadata["image"] and "staticmap" in metadata["image"] and not is_pure_query:
                    zoom_m = re.search(r'zoom=(\d+)', metadata["image"])
                    zoom_val = int(zoom_m.group(1)) if zoom_m else 15
                    if zoom_val > 10:
                        sm_match = RE_STATICMAP.search(metadata["image"])
                        if sm_match:
                            metadata["lat"] = float(sm_match.group(1))
                            metadata["lng"] = float(sm_match.group(2))
                            print(f"[MetadataEngine] Found coordinates in staticmap: ({metadata['lat']}, {metadata['lng']})")
                    else:
                        print(f"[MetadataEngine] Low zoom staticmap rejected ({zoom_val} <= 10): {metadata['image']}")
                elif is_pure_query and metadata["image"] and "staticmap" in metadata["image"]:
                    print(f"[MetadataEngine] Pure-query staticmap center rejected to prevent IP context poisoning: {metadata['image'][:80]}...")

            
            # 5. 回退機制 - Title & Description
            if not metadata["title"] and soup.title:
                metadata["title"] = soup.title.string
                
            if not metadata["description"]:
                desc = soup.find("meta", attrs={"name": "description"})
                if desc:
                    metadata["description"] = desc.get("content")

            # 6. 🛡️ 社群登入牆過濾與 IG Embed 救援（避免「登入 • Instagram」污染景點參考連結卡片）
            if is_social:
                hit_login_wall = _is_social_login_wall(
                    url,
                    title=str(metadata.get("title") or ""),
                    description=str(metadata.get("description") or ""),
                )
                if hit_login_wall:
                    print("[LinkResolver] Social OG hit login wall; purging polluted preview fields.")
                    metadata["title"] = None
                    metadata["description"] = None
                    metadata["image"] = None
                if is_ig and (hit_login_wall or not metadata.get("title") or not metadata.get("image")):
                    await _try_ig_embed_rescue()

    except SSRFSecurityError:
        print("[SSRF Block] Metadata fetch blocked during redirect; skipping IG Embed rescue.")
        return metadata
    except Exception as e:
        print(f"[WARN] Metadata fetch failed for {url}: {e}")
        if is_ig and (not metadata.get("title") or not metadata.get("image")):
            try:
                await _try_ig_embed_rescue()
            except Exception:
                pass
        
    return metadata

async def resolve_google_maps_link(url: str) -> Dict[str, Any]:
    """
    Follows redirects and extracts location data + visuals from Google Maps URLs.
    """
    result = {
        "lat": None,
        "lng": None,
        "address": None,
        "query": None,
        "resolved_url": url,
        "method": "none",
        "metadata": {}
    }

    # 🕵️ Step 0.5: Aggressive Text-to-URL Extraction FIRST (Defense in Depth)
    # 必須先自 iOS/Android 分享字串抽出純淨網址並剝除尾端標點，再賦值 original_input_url，
    # 確保後續嚴格主機名檢查 _is_google_shortlink(original_input_url) 不會誤擋 GAS Rescue。
    if url:
        clean_match = re.search(r'(https?://[^\s]+)', url)
        if clean_match:
            url = clean_match.group(1).rstrip('.,!?:;"\'。，！？')

    # 🆕 v35.26: Anti-Acidosis Protocol - Use SmartRedirectTracer
    original_input_url = url
    final_url = url
    result["resolved_url"] = url
    smart_tracer = get_smart_tracer()
    
    # 🛡️ Step 0: Sanitization (針對 iOS 分享連結進行淨化)
    # 目的：移除 g_st 等參數以強制 Google 回傳帶座標的 Desktop 版 URL（使用 query 解析防首參剝除破壞 '?'）
    if _is_google_shortlink(url):
        url = _strip_tracking_params(url)
    
    try:
        # Step 1: Smart Trace with precision analysis
        if _is_google_shortlink(url):
            # 🛡️ SSRF Check before tracing (non-blocking DNS bulkhead)
            if not await is_safe_url_async(url):
                print(f"[SSRF Block] SmartTrace aborted for unsafe URL: {url}")
                return result

            trace_result = await smart_tracer.trace_full_chain_smart(url)
            
            if trace_result.get('lat') and trace_result.get('lng'):
                # Use traced coords with precision guarantee
                result["lat"] = trace_result["lat"]
                result["lng"] = trace_result["lng"]
                result["method"] = f"smart_tracer+{trace_result.get('method', 'unknown')}"
                result["resolved_url"] = trace_result.get("final_url", url)
                final_url = trace_result.get("final_url", url)
                
                # 🛡️ v35.84: Capture name from tracer DNA
                if trace_result.get("place_name") and not result.get("query"):
                    result["query"] = trace_result["place_name"]
                
                print(f"[SmartTracer] OK ({result['lat']}, {result['lng']}) precision={trace_result.get('precision', 'N/A')}")
            else:
                # SmartTracer found no coords in chain, try final URL parsing
                final_url = trace_result.get("final_url", url)
                result["resolved_url"] = final_url
                
                # Use MolecularParser as fallback
                parser = get_molecular_parser()
                parsed = parser.parse_url(final_url)
                if parsed:
                    result["lat"] = parsed["lat"]
                    result["lng"] = parsed["lng"]
                    result["method"] = f"molecular+{parsed.get('method', 'unknown')}"
                    print(f"[MolecularParser] OK ({result['lat']}, {result['lng']})")
        else:
            # Non-short URL: Direct parsing with MolecularParser
            parser = get_molecular_parser()
            parsed = parser.parse_url(url)
            if parsed:
                result["lat"] = parsed["lat"]
                result["lng"] = parsed["lng"]
                result["method"] = f"molecular+{parsed.get('method', 'unknown')}"
            final_url = url
    
    except Exception as e:
        # 🛡️ Graceful fallback: Use legacy logic if new tracer fails
        print(f"[WARN] SmartTracer/MolecularParser failed, fallback to legacy: {e}")
        try:
            # 🛡️ SSRF Check (non-blocking DNS bulkhead)
            if not await is_safe_url_async(url):
                print(f"[SSRF Block] Legacy redirect aborted for unsafe URL: {url}")
                return result

            async with create_safe_client(follow_redirects=True, timeout=10.0) as client:
                async with client.stream("GET", url) as resp:
                    final_url = str(resp.url)
                    result["resolved_url"] = final_url
                    result["method"] = "legacy_redirect"
        except Exception as legacy_e:
            print(f"[WARN] Legacy fallback failed: {legacy_e}")
            return result
        
        # Legacy regex extraction
        processed_url = urllib.parse.unquote(urllib.parse.unquote(final_url)).replace('%21', '!')
        lat_match = re.search(r'!3d(-?\d+\.\d+)', processed_url)
        lng_match = re.search(r'!4d(-?\d+\.\d+)', processed_url)
        
        if lat_match and lng_match:
            result["lat"] = float(lat_match.group(1))
            result["lng"] = float(lng_match.group(1))
            result["method"] = f"{result['method']}+legacy_regex"
        else:
            match_a = RE_COORD_A.search(processed_url)
            if match_a:
                result["lat"] = float(match_a.group(1))
                result["lng"] = float(match_a.group(2))
                result["method"] = f"{result['method']}+legacy_regex_a"

    # Step 3: Extract Search Query (Tier 3 Fallback)
    match_q = RE_QUERY.search(final_url)
    if match_q:
        try:
            query = unquote_plus(match_q.group(1))
            result["query"] = query
            result["method"] = f"{result['method']}+query"
        except Exception:
            pass

    # 🕵️ Step 3.5: HTML Deep Mining (Deprecated due to IP Context Poisoning)
    # As discovered in testing, Google Maps URLs using "?q=" statically render 
    # HTML body with !2d/!3d and APP_INITIALIZATION_STATE mapped to the SERVER'S IP LOCATION.
    # SSR HTML body mining is permanently disabled to force fail-forward to RPC / geocoding.
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🆕 Step 3.6: Google Web Place RPC (Zero-Cost CID/FTID Miner)
    # 條件: (1) 沒座標 (2) URL 包含 ftid 或 cid 特徵
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if not result["lat"]:
        cid_match = re.search(r'ftid=0x[0-9a-fA-F]+:0x([0-9a-fA-F]+)', final_url) or re.search(r'cid=([0-9a-fA-F]+)', final_url)
        if not cid_match:
            cid_match = re.search(r'ftid=0x[0-9a-fA-F]+:0x([0-9a-fA-F]+)', original_input_url) or re.search(r'cid=([0-9a-fA-F]+)', original_input_url)
        
        if cid_match:
            hex_cid = cid_match.group(1)
            print(f"[PlaceRPC] Found CID {hex_cid}, probing Google Maps Web preview/place RPC...")
            rpc_res = await fetch_place_from_google_rpc(hex_cid)
            if rpc_res and rpc_res.get("lat") and rpc_res.get("lng"):
                result["lat"] = rpc_res["lat"]
                result["lng"] = rpc_res["lng"]
                result["method"] = f"{result.get('method', 'none')}+place_rpc"
                if rpc_res.get("title"):
                    result["query"] = rpc_res["title"]
                if rpc_res.get("address"):
                    result["address"] = rpc_res["address"]
                if rpc_res.get("place_id"):
                    result["place_id"] = rpc_res["place_id"]
                print(f"[PlaceRPC] Success: ({result['lat']}, {result['lng']}) title={result.get('query')}")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🆕 Step 3.7: GAS Two-Shot Rescue (Failure-Only Gateway)
    # 條件: (1) 所有本地引擎失敗 (2) 原始輸入是短網址
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    if not result["lat"] and _is_google_shortlink(original_input_url):
        try:
            gas_input = original_input_url  # 使用原始短網址呼叫 GAS 效果最好
            print(f"[GAS Rescue] Local engines failed, invoking GAS for original URL: {gas_input[:60]}...")
            
            gas_result = await resolve_via_gas(gas_input)
            
            if gas_result and gas_result.get("lat"):
                result["lat"] = gas_result["lat"]
                result["lng"] = gas_result["lng"]
                result["method"] = f"{result.get('method', 'none')}+gas_rescue"
                
                # 更新 final_url 以利後續 Metadata 取得更好結果
                if gas_result.get("longUrl") and gas_result["longUrl"] != gas_input:
                    final_url = gas_result["longUrl"]
                    result["resolved_url"] = final_url
                
                # 地名注入（僅在可靠時）
                if gas_result.get("title") and gas_result.get("titleReliable"):
                    result["query"] = gas_result["title"]
                    
                print(f"[GAS Rescue] Success: ({result['lat']}, {result['lng']})")
            else:
                print(f"[GAS Rescue] GAS could not resolve this link.")
        except Exception as gas_e:
            print(f"[GAS Rescue] Exception: {gas_e}")

    # Step 4: Fetch Metadata (Visuals + 🛰️ Metadata Rescue)
    result["metadata"] = await fetch_og_metadata(final_url)
    
    # 🛰️ Metadata Rescue (Tier 2.5)
    # 如果本地引擎和 GAS 都失敗，但 Metadata 抓到了 StaticMap 座標
    if not result["lat"] and result["metadata"].get("lat"):
        result["lat"] = result["metadata"]["lat"]
        result["lng"] = result["metadata"]["lng"]
        result["method"] = f"{result.get('method', 'none')}+metadata_rescue"
        print(f"[MetadataRescue] Recovered coordinates from staticmap: ({result['lat']}, {result['lng']})")
    
    # 🕵️ v35.84: DNA-Level Name Recovery (Full Cascade)
    # If title is generic "Google Maps" or missing, use a priority chain to recover the real name
    current_title = result["metadata"].get("title") or ""
    is_generic = not current_title or any(g in current_title.lower() for g in ["google maps", "google 地圖", "google地圖", "google マップ"])
    
    if is_generic:
        recovered_name = None
        
        # Priority 1: Query already extracted from ?q= (Line 294)
        if result.get("query"):
            recovered_name = result["query"]
            print(f"[DNA-Recovery] P1 (Query): {recovered_name}")
            
        # Priority 2: Extract from /place/ NAME /...
        if not recovered_name:
            place_match = RE_PLACE_PATH.search(final_url)
            if place_match:
                try:
                    recovered_name = unquote_plus(place_match.group(1))
                    print(f"[DNA-Recovery] P2 (Place Path): {recovered_name}")
                except: pass
                
        # Priority 3: Extract from /search/ NAME /...
        if not recovered_name:
            search_match = RE_SEARCH_PATH.search(final_url)
            if search_match:
                try:
                    recovered_name = urllib.parse.unquote(search_match.group(1)).replace("+", " ")
                    print(f"[DNA-Recovery] P3 (Search Path): {recovered_name}")
                except: pass

        if recovered_name:
            result["query"] = recovered_name
            result["metadata"]["title"] = recovered_name
            is_generic = False # Successfully recovered
            
    # 🆕 GAS Title Backfill: Only if still generic/missing
    if is_generic and result.get("query") and "gas_rescue" in result.get("method", ""):
        result["metadata"]["title"] = result["query"]
        print(f"[GAS Title] Backfill: {result['query']}")
    
    # 🛡️ [Region Guard] Safety First Protocol
    # v35.70: Categorical check to prevent IP-localized "drift" (Zero-Regression)
    if result.get("lat") and result.get("lng"):
        # Check if the coordinates are consistent with the metadata (e.g., Japan vs. others)
        metadata_text = f"{result['metadata'].get('title', '')} {result['metadata'].get('description', '')}".lower()
        
        # Japan Safety Check (Primary target region)
        is_japan_meta = any(token in metadata_text for token in ["japan", "tokyo", "osaka", "kyoto", "hokkaido", "airport", " hotel", "日本", "東京"])
        is_japan_geo = 20.0 <= result["lat"] <= 50.0 and 120.0 <= result["lng"] <= 155.0
        
        if is_japan_meta and not is_japan_geo:
            print(f"[RegionGuard] Geo-Drift detected! Meta indicates Japan but coords are at ({result['lat']}, {result['lng']}). PURGING COORDS.")
            result["lat"] = None
            result["lng"] = None
            result["method"] = f"{result.get('method', 'unknown')}+drift_purged"
        
        # Taiwan / CJK vs US Geo-Drift (e.g., Cloud Run us-central1 IP location Nebraska: 41.10567, -96.265644)
        is_us_geo = 24.0 <= result["lat"] <= 50.0 and -130.0 <= result["lng"] <= -65.0
        is_taiwan_meta = any(token in metadata_text for token in [
            "taiwan", "台灣", "臺灣", "台北", "臺北", "台中", "臺中", "台南", "臺南", "高雄", "新北", "桃園", "新竹", "苗栗", "彰化", "南投", "雲林", "嘉義", "屏東", "宜蘭", "花蓮", "台東", "臺東", "澎湖", "金門", "馬祖"
        ])
        has_cjk = bool(re.search(r'[\u4e00-\u9fff]', metadata_text))
        
        if is_us_geo and (is_taiwan_meta or has_cjk):
            print(f"[RegionGuard] US Geo-Drift detected for CJK/Taiwan POI! Coords at ({result['lat']}, {result['lng']}). PURGING COORDS.")
            result["lat"] = None
            result["lng"] = None
            result["method"] = f"{result.get('method', 'unknown')}+drift_purged"
        
    # Phase 2: The "DNA" Upgrade (Place ID / CID Extraction)
    # 使用 Side-car 方法提取正式 ID，而不干擾原本的座標邏輯
    try:
        parser = get_molecular_parser()
        ids = parser.extract_identifiers(final_url)
        if ids:
            result.update(ids)
    except Exception:
        pass
        
    # 📉 [Precision Auditor] Log failures for persistent optimization
    if not result.get("lat"):
        # Log to a persistent file for "carpet-bombing" optimization
        try:
            with open("semantic_fallback_audit.log", "a", encoding="utf-8") as audit_f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                audit_f.write(f"[{timestamp}] FAIL | URL: {final_url} | Metadata: {result.get('metadata', {}).get('title')} \n")
        except:
            pass

    # 📍 雙軌門牌地址提煉 (Description 正則優先 ➔ Photon 反查兜底)
    resolved_address = None
    if result.get("metadata", {}).get("description"):
        resolved_address = extract_address_from_description(result["metadata"]["description"])
    
    if not resolved_address and result.get("lat") and result.get("lng"):
        try:
            from services.geocode_service import reverse_geocode_with_photon
            geo = await reverse_geocode_with_photon(result["lat"], result["lng"])
            if geo and geo.get("address"):
                resolved_address = geo["address"]
        except Exception as geo_err:
            print(f"[ReverseGeocode] Photon fallback error: {geo_err}")
            
    result["address"] = resolved_address

    # 🧬 繁中地名清洗與解碼 (去除 URL 編碼與 - Google 地圖 後綴)
    raw_title = result.get("metadata", {}).get("title") or result.get("query") or ""
    if "%" in raw_title:
        try:
            raw_title = unquote_plus(raw_title)
        except Exception:
            pass
    clean_title = re.sub(r'\s*[-|]\s*Google\s*(Maps|地图|地圖|マップ|映射|map|search).*$', '', raw_title, flags=re.IGNORECASE).strip()

    # 🇹🇼 台灣地址與景點名稱分離演算法 (Zero-Cost 分離純店名與純門牌)
    extracted_addr = None
    if "·" in clean_title:
        parts = [p.strip() for p in clean_title.split("·")]
        part0 = parts[0]
        addr0, poi0 = split_taiwan_address_and_poi(part0)
        if poi0:
            clean_title = poi0
            extracted_addr = addr0
        else:
            clean_title = part0
        if not extracted_addr and len(parts) > 1:
            addr1, _ = split_taiwan_address_and_poi(parts[1])
            if addr1:
                extracted_addr = addr1
            elif any(k in parts[1] for k in ["市", "縣", "區", "路", "街", "號"]):
                extracted_addr = parts[1]
    else:
        addr, poi = split_taiwan_address_and_poi(clean_title)
        if poi:
            clean_title = poi
            extracted_addr = addr

    if extracted_addr and not result.get("address"):
        result["address"] = extracted_addr

    if clean_title:
        result["metadata"]["title"] = clean_title
        result["query"] = clean_title

    # 🧭 Tier 3 Fallback Geocoding: 若無座標但有地址或清洗後店名
    if not result.get("lat") and (result.get("address") or clean_title):
        try:
            from services.geocode_service import geocode_place
            target_query = result.get("address") or clean_title
            print(f"[LinkResolver] Fallback geocoding target: {target_query}")
            geo_res = await geocode_place(target_query)
            if geo_res and geo_res.get("lat") and geo_res.get("lng"):
                result["lat"] = geo_res["lat"]
                result["lng"] = geo_res["lng"]
                result["method"] = f"{result.get('method', 'none')}+fallback_geocode"
                print(f"[LinkResolver] Fallback geocode success: ({result['lat']}, {result['lng']})")
        except Exception as geocode_err:
            print(f"[LinkResolver] Fallback geocode error: {geocode_err}")

    return result

async def resolve_google_maps_placelist(url: str) -> Dict[str, Any]:
    """
    解析 Google Maps 共享清單 (Placelists / Saved Lists)。
    利用 Google 內部 RPC (preview/entitylist/getlist) 一次性萃取整批清單內的 POI 地點。
    """
    result = {
        "success": False,
        "mode": "placelist",
        "title": "Google 地圖清單",
        "count": 0,
        "items": [],
        "resolved_url": url,
        "error": None
    }
    
    clean_url = url
    if _is_google_shortlink(url):
        if not await is_safe_url_async(url):
            result["error"] = "UNSAFE_URL"
            return result
        try:
            async with create_safe_client(follow_redirects=True, timeout=12.0) as client:
                async with client.stream("GET", url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
                }) as resp:
                    clean_url = str(resp.url)
        except SSRFSecurityError:
            result["error"] = "UNSAFE_URL"
            return result
        except Exception as e:
            print(f"[Placelist] Redirect trace failed: {e}")
            clean_url = url

    # 萃取 List ID
    list_id_match = re.search(r'(?:!11m2!2s|/placelists/list/)([A-Za-z0-9_-]{16,})', clean_url)
    if not list_id_match:
        result["error"] = "CANNOT_EXTRACT_LIST_ID"
        return result
        
    list_id = list_id_match.group(1)
    rpc_url = f"https://www.google.com/maps/preview/entitylist/getlist?authuser=0&hl=zh-TW&gl=tw&pb=!1m4!1s{list_id}!2e1!3m1!1e1!2e2!3e2!4i2000"
    
    max_retries = 2
    data = None
    for attempt in range(max_retries):
        try:
            async with create_safe_client(follow_redirects=True, timeout=12.0) as client:
                resp = await client.get(rpc_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
                })
                if resp.status_code != 200:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.3)
                        continue
                    result["error"] = f"HTTP_{resp.status_code}"
                    return result
                    
                raw_text = resp.text.strip()
                if not raw_text.startswith(")]}'"):
                    if attempt < max_retries - 1:
                        print(f"[Placelist] Attempt {attempt+1}: Non-XSSI response received, retrying in 300ms...")
                        await asyncio.sleep(0.3)
                        continue
                    result["error"] = "PRIVATE_OR_INVALID_LIST"
                    return result
                    
                # 🛡️ 採用決定性正則剝除 XSSI 前綴，防止字符集剝除誤殺
                stripped = re.sub(r"^\)]\}'\s*", "", raw_text).strip()
                import json
                data = json.loads(stripped)
                break
        except Exception as net_err:
            if attempt < max_retries - 1:
                await asyncio.sleep(0.3)
                continue
            print(f"[Placelist] RPC attempt failed: {net_err}")
            result["error"] = str(net_err)
            return result

    if not data:
        result["error"] = "NO_DATA"
        return result

    try:
        # 解析清單標題
        list_title = "已儲存的地點清單"
        if len(data) > 0 and len(data[0]) > 4 and data[0][4]:
            list_title = str(data[0][4])
        result["title"] = list_title
        
        # 遍歷地點陣列 (data[0][8])
        raw_items = data[0][8] if (len(data) > 0 and len(data[0]) > 8 and isinstance(data[0][8], list)) else []
        extracted_items = []
        
        for item in raw_items:
            if not isinstance(item, list) or len(item) < 3:
                continue
            try:
                title = item[2] if len(item) > 2 and item[2] else "已儲存地點"
                title = unquote_plus(str(title)).strip()
                
                # 門牌地址 item[1][4]
                address = None
                if len(item) > 1 and isinstance(item[1], list) and len(item[1]) > 4 and item[1][4]:
                    address = str(item[1][4]).strip()
                    
                # 座標 item[1][5][2], item[1][5][3]
                lat, lng = None, None
                if len(item) > 1 and isinstance(item[1], list) and len(item[1]) > 5 and isinstance(item[1][5], list):
                    coords = item[1][5]
                    if len(coords) > 3 and coords[2] is not None and coords[3] is not None:
                        lat = float(coords[2])
                        lng = float(coords[3])
                        
                # 使用者備註 item[3]
                user_notes = None
                if len(item) > 3 and item[3]:
                    user_notes = str(item[3]).strip()
                    
                if lat is not None and lng is not None:
                    extracted_items.append({
                        "title": title,
                        "address": address,
                        "lat": lat,
                        "lng": lng,
                        "category": "attraction",
                        "user_notes": user_notes,
                        "source_url": clean_url
                    })
            except Exception as item_err:
                print(f"[Placelist] Skip corrupted item: {item_err}")
                continue
                
        result["success"] = True
        result["count"] = len(extracted_items)
        result["items"] = extracted_items
        return result
    except Exception as e:
        print(f"[Placelist] RPC parsing failed: {e}")
        result["error"] = str(e)
        return result

async def resolve_generic_link(url: str) -> Dict[str, Any]:
    """
    Resolves non-map links (IG, Official Web, FB) to get visuals.
    """
    metadata = await fetch_og_metadata(url)
    return {
        "success": True,
        "metadata": metadata,
        "resolved_url": url
    }
