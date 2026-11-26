"""
Web Search & Reader Engine (Zero-Key Resilient Architecture)
-----------------------------------------------------------
1. DuckDuckGo Search: ddgs primary with static HTML/Lite fallback
2. DDG Redirect Unwrapping: Decodes `//duckduckgo.com/l/?uddg=` trackers
3. Jina Reader: r.jina.ai on-demand page extraction with graceful degradation
"""

import os
import asyncio
import re
import html
import json
import time
import weakref
import urllib.parse
import ipaddress
from collections import OrderedDict
import httpx
from typing import List, Dict, Optional, Any, Tuple
from bs4 import BeautifulSoup
from utils.url_safety import is_safe_url, is_safe_url_async, create_safe_client, SSRFSecurityError
from services.link_resolver import _read_bounded_text

# 全域共用非同步 HTTP 連線池
_http_client: Optional[httpx.AsyncClient] = None

# 擬真瀏覽器 User-Agent (防禦 DDG HTML 驗證碼阻擋)
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# 合規識別 User-Agent (一般外部網站直連，避免 Wikipedia 403 並支援 Markdown for Agents)
DIRECT_FETCH_USER_AGENT = "TabijiTravelPWA/1.0 (https://www.tabijiapp.com; contact@tabijiapp.com)"

# SSRF 私有 IP 阻擋清單
PRIVATE_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def get_search_client() -> httpx.AsyncClient:
    """取得或初始化全域非同步 HTTP 連線（回應後自動清空 Cookie 防跨站污染）"""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        client_holder: List[Optional[httpx.AsyncClient]] = [None]

        async def _clear_response_cookies(response: httpx.Response) -> None:
            client_ref = client_holder[0]
            if client_ref is not None and not client_ref.is_closed:
                client_ref.cookies.clear()

        created = create_safe_client(
            timeout=httpx.Timeout(4.5, connect=2.0),
            headers={
                "User-Agent": BROWSER_USER_AGENT,
                "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7",
            },
            follow_redirects=True,
            event_hooks={"response": [_clear_response_cookies]},
        )
        client_holder[0] = created
        _http_client = created
    return _http_client


async def close_search_client() -> None:
    """關閉全域 HTTP 連線池"""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


def unwrap_ddg_redirect(href: str) -> str:
    """
    解析 DuckDuckGo 搜尋結果中的重定向封裝：
    //duckduckgo.com/l/?uddg=<encoded_target>&rut=...
    若為重定向則解碼出真實 URL，否則返回原 href。
    """
    if not href:
        return ""
    try:
        norm_href = f"https:{href}" if href.startswith("//") else href
        parsed = urllib.parse.urlparse(norm_href)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            qs = urllib.parse.parse_qs(parsed.query)
            target = qs.get("uddg")
            if target and target[0]:
                return target[0]
    except Exception:
        pass
    return href


def is_safe_external_url(url: str) -> bool:
    """SSRF 防禦：檢查是否為合法的外部 HTTP/HTTPS 公共網址 (委託 is_safe_url)"""
    return is_safe_url(url)


# Cloudflare 邊緣檢索執行器配置 (Tier 2)
CF_WORKER_SEARCH_URL = os.environ.get("CF_WORKER_SEARCH_URL", "https://tabidachi-search-proxy.ryanpig228.workers.dev").strip()
CF_PROXY_SECRET = os.environ.get("CF_PROXY_SECRET", "").strip()

# 6 小時記憶體 LRU 搜尋結果快取 (128 筆，不依賴 *.workers.dev 無效之 caches.default)
_WEB_SEARCH_CACHE_MAX_SIZE = 128
_WEB_SEARCH_CACHE_TTL_SEC = 6 * 3600.0
_WEB_SEARCH_CACHE: "OrderedDict[str, Tuple[float, List[Dict[str, str]]]]" = OrderedDict()

# 時效性查詢詞正則（命中時禁止降級為靜態維基百科，杜絕以過期/無關條目毒化上下文）
_TEMPORAL_SEARCH_RE = re.compile(
    r"(?:營業時間|開放時間|休館|公休|票價|門票|價錢|價格|費用|預約|訂位|購票|最新|今天|明天|今年|公告|停駛|暫停|活動|祭典|櫻花|楓葉|天氣|匯率|"
    r"\b(?:ticket|tickets|price|prices|hours|opening|open|close|closed|reservation|booking|schedule|status|news|event|forecast|2025|2026|2027|2028)\b)",
    re.IGNORECASE,
)
_WIKI_LATIN_STOPWORDS = frozenset({
    "the", "for", "and", "in", "of", "to", "a", "an", "is", "are", "at", "on", "with",
    "how", "what", "when", "where", "who", "why", "from", "by", "about", "info", "guide",
})


def _has_temporal_search_keyword(query: str) -> bool:
    return bool(_TEMPORAL_SEARCH_RE.search(query or ""))


def _is_relevant_wiki_title(query: str, title: str) -> bool:
    q_norm = re.sub(r"site:\S+", "", query or "", flags=re.IGNORECASE).strip().lower()
    t_norm = re.sub(r"\s*\([^)]*\)\s*", "", title or "").strip().lower()
    if not q_norm or not t_norm:
        return False
    if len(t_norm) >= 2 and (q_norm in t_norm or t_norm in q_norm):
        return True

    q_clean = _TEMPORAL_SEARCH_RE.sub(" ", q_norm)
    tokens = set()
    for w in re.findall(r"[a-z0-9]{2,}", q_clean):
        if w not in _WIKI_LATIN_STOPWORDS:
            tokens.add(w)
    for run in re.findall(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]+", q_clean):
        if len(run) <= 2:
            tokens.add(run)
        else:
            for i in range(len(run) - 1):
                tokens.add(run[i : i + 2])
    if not tokens:
        return False
    hits = sum(1 for tok in tokens if tok in t_norm)
    return (hits / len(tokens)) >= 0.5


def _web_search_cache_get(cache_key: str) -> Optional[List[Dict[str, str]]]:
    entry = _WEB_SEARCH_CACHE.get(cache_key)
    if entry is None:
        return None
    expires_at, payload = entry
    if time.monotonic() >= expires_at:
        _WEB_SEARCH_CACHE.pop(cache_key, None)
        return None
    _WEB_SEARCH_CACHE.move_to_end(cache_key)
    return [dict(item) for item in payload]


def _web_search_cache_set(cache_key: str, results: List[Dict[str, str]]) -> None:
    if not results:
        return
    _WEB_SEARCH_CACHE[cache_key] = (time.monotonic() + _WEB_SEARCH_CACHE_TTL_SEC, [dict(item) for item in results])
    _WEB_SEARCH_CACHE.move_to_end(cache_key)
    while len(_WEB_SEARCH_CACHE) > _WEB_SEARCH_CACHE_MAX_SIZE:
        _WEB_SEARCH_CACHE.popitem(last=False)


async def _search_cloudflare_edge(query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """
    第 2 層保險：Cloudflare 邊緣檢索器 (Anycast IP 洗白)
    由全球 300+ 邊緣節點直接抓取並回傳結構化 JSON，零機房 IP 封鎖風險。
    """
    cf_url = (os.environ.get("CF_WORKER_SEARCH_URL") or CF_WORKER_SEARCH_URL or "").strip()
    cf_secret = (os.environ.get("CF_PROXY_SECRET") or CF_PROXY_SECRET or "").strip()
    if not cf_url or "REDACTED" in cf_url:
        return []
    client = get_search_client()
    headers = {"x-tabidachi-key": cf_secret} if cf_secret else {}
    try:
        resp = await client.get(
            f"{cf_url.rstrip('/')}/search",
            params={"q": query, "limit": max_results},
            headers=headers,
            timeout=4.5
        )
        if resp.status_code == 200:
            data = resp.json()
            raw_list = data.get("results", [])
            results = []
            for r in raw_list:
                u = r.get("url")
                if u and await is_safe_url_async(u):
                    results.append({
                        "title": r.get("title", ""),
                        "snippet": r.get("snippet", ""),
                        "url": u
                    })
            if results:
                return results
    except Exception as e:
        print(f"⚠️ [SearchEngine] Tier 2 Cloudflare 邊緣檢索異常: {e}")
    return []


async def _search_wikipedia_fallback(query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """
    第 4 層保險：Wikipedia 官方 OpenSearch API 兜底 (零 IP 封鎖、免 Key)
    僅允許非時效性查詢且必須通過標題相關性門檻，嚴防雜訊毒化上下文。
    """
    if _has_temporal_search_keyword(query):
        return []
    client = get_search_client()
    wiki_url = "https://zh.wikipedia.org/w/api.php"
    params = {
        "action": "opensearch",
        "search": query,
        "limit": max_results,
        "namespace": "0",
        "format": "json"
    }
    headers = {
        "User-Agent": DIRECT_FETCH_USER_AGENT,
        "Accept": "application/json"
    }
    try:
        resp = await client.get(wiki_url, params=params, headers=headers, timeout=2.8)
        if resp.status_code == 200:
            data = resp.json()
            titles = data[1] if len(data) > 1 else []
            snippets = data[2] if len(data) > 2 else []
            urls = data[3] if len(data) > 3 else []
            results = []
            for t, s, u in zip(titles, snippets, urls):
                if not t or not _is_relevant_wiki_title(query, t):
                    continue
                if u and await is_safe_url_async(u):
                    results.append({
                        "title": f"{t} (維基百科)",
                        "snippet": s or f"關於 {t} 的開放百科條目詳細資訊",
                        "url": u
                    })
            if results:
                return results
    except Exception as e:
        print(f"⚠️ [SearchEngine] Tier 4 Wikipedia API 備援失敗: {e}")
    return []


async def _search_ddg_html_fallback(query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """
    第 3 層保險：DuckDuckGo 靜態 Lite / HTML 端點
    純表單 POST，無需執行 JavaScript、不產生 VQD Token。
    """
    client = get_search_client()
    # 優先嘗試 lite.duckduckgo.com/lite/
    try:
        resp = await client.post(
            "https://lite.duckduckgo.com/lite/",
            data={"q": query},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            results: List[Dict[str, str]] = []
            links = soup.find_all("a", class_="result-link")
            snippets = soup.find_all("td", class_="result-snippet")
            for idx, link_tag in enumerate(links[:max_results]):
                raw_href = link_tag.get("href", "")
                real_url = unwrap_ddg_redirect(raw_href)
                snippet_text = snippets[idx].get_text(strip=True) if idx < len(snippets) else ""
                if real_url and await is_safe_url_async(real_url):
                    results.append({
                        "title": link_tag.get_text(strip=True),
                        "snippet": snippet_text,
                        "url": real_url
                    })
            if results:
                return results
    except Exception as e:
        print(f"⚠️ [SearchEngine] DDG Lite 靜態端點異常: {e}")

    # 次級嘗試 html.duckduckgo.com/html/
    try:
        resp = await client.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for item in soup.find_all("div", class_="result")[:max_results]:
                title_tag = item.find("a", class_="result__a")
                snippet_tag = item.find("a", class_="result__snippet")
                if title_tag and title_tag.get("href"):
                    real_url = unwrap_ddg_redirect(title_tag["href"])
                    if real_url and await is_safe_url_async(real_url):
                        results.append({
                            "title": title_tag.get_text(strip=True),
                            "snippet": snippet_tag.get_text(strip=True) if snippet_tag else "",
                            "url": real_url
                        })
            return results
    except Exception as e:
        print(f"⚠️ [SearchEngine] DDG HTML 備援端點亦失敗: {e}")

    return []


def _sync_ddgs_call(final_query: str, region: str, max_results: int) -> List[Dict[str, str]]:
    """以獨立同步執行緒調用 ddgs Dux 8 引擎全併發，排除百科避免動漫雜訊"""
    from ddgs import DDGS
    DDGS.threads = 8  # 🚀 解鎖執行緒池上限，允許所有引擎同時併發
    # 剔除 wikipedia、grokipedia 與已停用之 google 後端，優先調度有效網路搜尋引擎
    search_backends = "yahoo,duckduckgo,startpage,brave,mojeek"
    with DDGS(timeout=4) as ddgs:
        raw_res = list(ddgs.text(final_query, backend=search_backends, region=region, max_results=max_results))
        results: List[Dict[str, str]] = []
        for r in raw_res:
            real_url = unwrap_ddg_redirect(r.get("href", ""))
            if real_url and is_safe_external_url(real_url):
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": real_url
                })
        return results


async def execute_web_search(
    query: str,
    site_filter: Optional[str] = None,
    max_results: int = 3,
    region: Optional[str] = None
) -> List[Dict[str, str]]:
    """
    四級抗脆弱零成本非同步搜尋主入口
    - Tier 1: 本地 Dux 多引擎非同步執行緒 (解決 Event Loop 阻塞)
    - Tier 2: Cloudflare 邊緣檢索器 (Anycast IP 洗白，抗雲端機房 403)
    - Tier 3: DuckDuckGo 靜態 HTML / Lite 端點
    - Tier 4: Wikipedia 官方 OpenSearch API 兜底 (零封鎖、免 Key)
    """
    trimmed = query.strip()
    if not trimmed:
        return []

    final_query = f"{trimmed} site:{site_filter}" if site_filter else trimmed
    
    # 🚀 動態 Region 自適應回退：堅決不使用 wt-wt，中文優先 tw-tzh，英文 us-en
    if not region:
        is_japanese = any("\u3040" <= c <= "\u30ff" for c in trimmed)
        is_cjk = any("\u4e00" <= c <= "\u9fff" for c in trimmed)
        resolved_region = "jp-jp" if is_japanese else ("tw-tzh" if is_cjk else "us-en")
    else:
        resolved_region = region

    # 0. [Cache] 6 小時記憶體 LRU 快取 (128 筆)
    cache_key = f"{final_query.lower()}|{resolved_region}|{max_results}"
    cached = _web_search_cache_get(cache_key)
    if cached is not None:
        return cached

    cf_url = (os.environ.get("CF_WORKER_SEARCH_URL") or CF_WORKER_SEARCH_URL or "").strip()
    cf_secret = (os.environ.get("CF_PROXY_SECRET") or CF_PROXY_SECRET or "").strip()
    prefer_cf_edge = bool(cf_url and "REDACTED" not in cf_url and cf_secret)

    # 1. 當已配置 CF_WORKER_SEARCH_URL 與 CF_PROXY_SECRET 時，優先直走 Cloudflare Edge (避免在 Cloud Run 先燒 5.2s + 8 執行緒)
    if prefer_cf_edge:
        cf_results = await _search_cloudflare_edge(final_query, max_results=max_results)
        if cf_results:
            _web_search_cache_set(cache_key, cf_results)
            return cf_results

    # 2. [Tier 1] 本地 Dux 多引擎 (非同步線程；生產直連 CF 模式未命中時不再空耗 5.2s)
    is_prod_env = os.environ.get("ENV") == "production" or os.environ.get("NODE_ENV") == "production"
    if not (prefer_cf_edge and is_prod_env):
        try:
            results = await asyncio.wait_for(
                asyncio.to_thread(_sync_ddgs_call, final_query, resolved_region, max_results),
                timeout=3.5 if prefer_cf_edge else 5.2
            )
            if results:
                _web_search_cache_set(cache_key, results)
                return results
        except Exception as e:
            print(f"⚠️ [SearchEngine] Tier 1 本地查詢未命中 ({e})，切換至備援檢索...")

    # 3. [Tier 2] Cloudflare 邊緣檢索執行器 (未於優先直走階段觸發時)
    if not prefer_cf_edge:
        cf_results = await _search_cloudflare_edge(final_query, max_results=max_results)
        if cf_results:
            _web_search_cache_set(cache_key, cf_results)
            return cf_results

    # 4. [Tier 3] 靜態 Lite / HTML 端點
    html_results = await _search_ddg_html_fallback(final_query, max_results=max_results)
    if html_results:
        _web_search_cache_set(cache_key, html_results)
        return html_results

    # 5. [Tier 4] Wikipedia 官方開放 API 兜底 (含時效詞禁走與標題相關性門檻)
    if not _has_temporal_search_keyword(trimmed):
        print("⚠️ [SearchEngine] 搜尋引擎受阻，啟用 Tier 4 Wikipedia 官方 API 條件兜底...")
        wiki_results = await _search_wikipedia_fallback(trimmed, max_results=max_results)
        if wiki_results:
            _web_search_cache_set(cache_key, wiki_results)
            return wiki_results

    return []


# 社群媒體網址模式 (IG / Threads / FB / TikTok / X / Twitter，涵蓋行動版與短網址；嚴格錨定開頭防查詢參數偽冒)
SOCIAL_MEDIA_PATTERN = re.compile(
    r"^\s*https?://(?:"
    r"(?:www\.|m\.)?instagram\.com|"
    r"(?:www\.)?instagr\.am|"
    r"(?:www\.)?ig\.me|"
    r"(?:www\.)?threads\.(?:net|com)|"
    r"(?:www\.|m\.|mbasic\.)?facebook\.com|"
    r"(?:www\.)?fb\.watch|"
    r"(?:www\.|m\.|vm\.|vt\.)?tiktok\.com|"
    r"(?:www\.|mobile\.)?twitter\.com|"
    r"(?:www\.)?x\.com"
    r")(?::\d+)?(?:/|\?|#|$)",
    re.IGNORECASE,
)

# 社群登入牆特徵（避免機房 IP 遇到 HTTP 200 登入牆被誤判為有效貼文內文）
_SOCIAL_LOGIN_WALL_TITLES = frozenset({
    "登入 • instagram",
    "login • instagram",
    "log in • instagram",
    "log into facebook",
    "登入 facebook",
})
_SOCIAL_LOGIN_WALL_PHRASES = (
    "登入 • instagram",
    "login • instagram",
    "log in • instagram",
    "歡迎回到 instagram",
    "welcome back to instagram",
    "create an account or log in to instagram",
    "建立帳號或登入 instagram",
    "log in to see photos and videos",
    "sign up to see photos and videos",
    "log into facebook to start sharing",
    "登入即可查看",
)

# Tier 0: LRU 成功快取與 Event-Loop 分桶 Singleflight 去重 (FP-113)
_URL_CACHE_MAX_SIZE = 128
_SOCIAL_CACHE_TTL_SEC = 3600.0
_GENERAL_CACHE_TTL_SEC = 1800.0
_URL_READER_CACHE: "OrderedDict[str, Tuple[float, Dict[str, Any]]]" = OrderedDict()
_URL_INFLIGHT_BY_LOOP: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Dict[str, List[Any]]]" = (
    weakref.WeakKeyDictionary()
)
_CACHE_TRACKING_PARAMS = frozenset({"igsh", "igshid", "stkn", "fbclid", "gclid", "si", "g_st"})

# Instagram 短碼與分享短網址正則（嚴格線性 O(n)）
_IG_HOSTS = frozenset({
    "instagram.com",
    "www.instagram.com",
    "m.instagram.com",
    "instagr.am",
    "www.instagr.am",
    "ig.me",
    "www.ig.me",
})
_IG_RESERVED_SEGMENTS = frozenset({"share", "explore", "accounts", "stories", "direct", "p", "reel", "reels", "tv"})
_IG_SHORTCODE_PATH_RE = re.compile(
    r"^/(?:([A-Za-z0-9_.]{1,64})/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]{5,64})(?:/|$)"
)
_IG_SHARE_PATH_RE = re.compile(
    r"^/share/(?:(?:reel|p|tv)/)?([A-Za-z0-9_-]{5,64})(?:/|$)"
)


def __reset_web_search_cache_for_testing() -> None:
    """顯式重置 Tier 0 URL 快取、6h 搜尋快取與 Singleflight 狀態，供 pytest 徹底隔離跨測試狀態。"""
    _URL_READER_CACHE.clear()
    _WEB_SEARCH_CACHE.clear()
    for bucket in list(_URL_INFLIGHT_BY_LOOP.values()):
        for entry in list(bucket.values()):
            task = entry[0] if entry else None
            if task is not None and not task.done():
                try:
                    task.cancel()
                except Exception:
                    pass
        bucket.clear()
    _URL_INFLIGHT_BY_LOOP.clear()


def _sanitize_url_for_log(url: str) -> str:
    """日誌脫敏：僅輸出協議、主機名與有限路徑，嚴禁輸出 query/token/stkn。"""
    try:
        parts = urllib.parse.urlsplit(url or "")
        host = parts.hostname or "unknown"
        path = (parts.path or "")[:64]
        return f"{parts.scheme}://{host}{path}" if parts.scheme else host
    except Exception:
        return "unknown"


def _normalize_reader_cache_key(
    url: str,
    wait_for_selector: Optional[str] = None,
    target_selector: Optional[str] = None,
) -> str:
    """正規化 URL 作為 Tier 0 快取與 Singleflight 鍵值（剝除追蹤參數與 fragment）。"""
    try:
        parts = urllib.parse.urlsplit((url or "").strip())
        scheme = parts.scheme.lower()
        netloc = parts.netloc.lower()
        path = parts.path or "/"
        if SOCIAL_MEDIA_PATTERN.search(url or "") and path != "/":
            path = path.rstrip("/")
        filtered_qs = [
            (k, v)
            for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in _CACHE_TRACKING_PARAMS and not k.lower().startswith("utm_")
        ]
        norm_query = urllib.parse.urlencode(filtered_qs, doseq=True)
        base = urllib.parse.urlunsplit((scheme, netloc, path, norm_query, ""))
    except Exception:
        base = (url or "").strip()
    return f"{base}|w={wait_for_selector or ''}|t={target_selector or ''}"


def _reader_cache_get(cache_key: str) -> Optional[Dict[str, Any]]:
    entry = _URL_READER_CACHE.get(cache_key)
    if entry is None:
        return None
    expires_at, payload = entry
    if time.monotonic() >= expires_at:
        _URL_READER_CACHE.pop(cache_key, None)
        return None
    _URL_READER_CACHE.move_to_end(cache_key)
    return dict(payload)


def _reader_cache_set(cache_key: str, payload: Dict[str, Any], is_social: bool) -> None:
    if payload.get("status") != "success" or not (payload.get("markdown") or "").strip():
        return
    ttl = _SOCIAL_CACHE_TTL_SEC if is_social else _GENERAL_CACHE_TTL_SEC
    _URL_READER_CACHE[cache_key] = (time.monotonic() + ttl, dict(payload))
    _URL_READER_CACHE.move_to_end(cache_key)
    while len(_URL_READER_CACHE) > _URL_CACHE_MAX_SIZE:
        _URL_READER_CACHE.popitem(last=False)


def _extract_markdown_title(md_content: str) -> str:
    """自 Jina Reader 或原生 Markdown 前段抽出乾淨標題。"""
    if not md_content:
        return ""
    for raw_line in md_content.splitlines()[:12]:
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("title:"):
            candidate = line[6:].strip()
            if candidate:
                return candidate[:200]
        if line.startswith("#"):
            candidate = line.lstrip("#").strip()
            if candidate:
                return candidate[:200]
    return ""


def _is_instagram_url(url: str) -> bool:
    try:
        host = (urllib.parse.urlsplit((url or "").strip()).hostname or "").lower().rstrip(".")
        return host in _IG_HOSTS
    except Exception:
        return False


def _is_instagram_share_url(url: str) -> bool:
    try:
        parts = urllib.parse.urlsplit((url or "").strip())
        host = (parts.hostname or "").lower().rstrip(".")
        if host not in _IG_HOSTS:
            return False
        return bool(_IG_SHARE_PATH_RE.match(parts.path or "")) or host in ("ig.me", "www.ig.me")
    except Exception:
        return False


def _extract_instagram_shortcode(url: str) -> Optional[str]:
    """從 Instagram 貼文/Reel/TV 網址線性提取 shortcode（排除 /share/ 路徑）。"""
    try:
        parts = urllib.parse.urlsplit((url or "").strip())
        host = (parts.hostname or "").lower().rstrip(".")
        if host not in _IG_HOSTS:
            return None
        path = parts.path or ""
        if _IG_SHARE_PATH_RE.match(path):
            return None
        match = _IG_SHORTCODE_PATH_RE.match(path)
        if not match:
            return None
        prefix_user, shortcode = match.group(1), match.group(2)
        if prefix_user and prefix_user.lower() in _IG_RESERVED_SEGMENTS:
            return None
        return shortcode
    except Exception:
        return None


def _extract_instagram_shortcode_from_redirect(url: str) -> Optional[str]:
    """自 IG 重導向目標提取 shortcode（同時相容 Meta 機房 IP 跳轉 /accounts/login/?next=...）。"""
    direct = _extract_instagram_shortcode(url)
    if direct:
        return direct
    try:
        parts = urllib.parse.urlsplit((url or "").strip())
        host = (parts.hostname or "").lower().rstrip(".")
        if host not in _IG_HOSTS:
            return None
        if parts.path.startswith("/accounts/login"):
            next_vals = urllib.parse.parse_qs(parts.query).get("next") or []
            for next_val in next_vals:
                candidate = urllib.parse.urljoin("https://www.instagram.com/", next_val)
                code = _extract_instagram_shortcode(candidate)
                if code:
                    return code
    except Exception:
        return None
    return None


async def _resolve_instagram_share_url(url: str, timeout: float = 2.0) -> Optional[str]:
    """透過逐跳零 Body 有界串流追蹤 IG /share/ 轉址取得真實 shortcode（全程受 SSRF 保護，命中即停）。"""
    if not await is_safe_url_async(url):
        return None
    client = get_search_client()
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7",
    }
    cur_url = url
    max_hops = 5
    try:
        for _ in range(max_hops):
            if not await is_safe_url_async(cur_url):
                return None
            try:
                stream_ctx = client.stream(
                    "GET", cur_url, headers=headers, timeout=timeout, follow_redirects=False
                )
            except TypeError:
                stream_ctx = client.stream("GET", cur_url, headers=headers, timeout=timeout)
            if asyncio.iscoroutine(stream_ctx):
                stream_ctx.close()
                return None
            next_loc: Optional[str] = None
            async with stream_ctx as resp:
                # 優先檢查 resp.history 與 resp.url（相容自訂 mock 已自動跟隨轉址之情境）
                for hist_resp in getattr(resp, "history", None) or []:
                    hist_headers = getattr(hist_resp, "headers", None)
                    hist_loc = hist_headers.get("location") if hist_headers else None
                    if hist_loc:
                        cand = urllib.parse.urljoin(str(getattr(hist_resp, "url", cur_url) or cur_url), hist_loc)
                        code = _extract_instagram_shortcode_from_redirect(cand)
                        if code:
                            return code
                resp_url = str(getattr(resp, "url", "") or "")
                code = _extract_instagram_shortcode_from_redirect(resp_url)
                if code:
                    return code
                resp_headers = getattr(resp, "headers", None)
                loc = resp_headers.get("location") if resp_headers else None
                if loc:
                    next_loc = urllib.parse.urljoin(resp_url or cur_url, loc)

            if not next_loc:
                return None
            if not await is_safe_url_async(next_loc):
                print(f"🛡️ [SearchEngine] IG Share 重導向目標命中 SSRF 攔截: {_sanitize_url_for_log(url)}")
                return None
            code = _extract_instagram_shortcode_from_redirect(next_loc)
            if code:
                return code
            if next_loc == cur_url:
                return None
            cur_url = next_loc
        return None
    except SSRFSecurityError:
        print(f"🛡️ [SearchEngine] IG Share 重導向命中 SSRF 攔截: {_sanitize_url_for_log(url)}")
        return None
    except Exception as e:
        print(f"⚠️ [SearchEngine] IG Share 轉址展開失敗 ({_sanitize_url_for_log(url)}): {type(e).__name__}")
        return None


def _extract_caption_from_media_obj(media_obj: Dict[str, Any]) -> Tuple[str, str, Optional[str]]:
    """自 Instagram shortcode_media 物件抽取 username、caption 與封面圖。"""
    username = ""
    owner = media_obj.get("owner")
    if isinstance(owner, dict):
        username = str(owner.get("username") or "").strip()

    caption = ""
    caption_edge = media_obj.get("edge_media_to_caption")
    if isinstance(caption_edge, dict):
        edges = caption_edge.get("edges")
        if isinstance(edges, list) and edges:
            first_node = edges[0].get("node") if isinstance(edges[0], dict) else None
            if isinstance(first_node, dict):
                caption = str(first_node.get("text") or "").strip()

    image_url = media_obj.get("display_url") or media_obj.get("thumbnail_src")
    if isinstance(image_url, str):
        image_url = html.unescape(image_url.strip()) or None
    else:
        image_url = None

    return username, caption, image_url


def _extract_shortcode_media_from_json_str(
    raw: str,
    decoder: json.JSONDecoder,
) -> Tuple[str, str, Optional[str]]:
    """自純 JSON 片段中線性掃描 `"shortcode_media"`（跳過 null/非物件，最多掃描 8 次）。"""
    key_token = '"shortcode_media"'
    pos = 0
    for _ in range(8):
        idx = raw.find(key_token, pos)
        if idx == -1:
            break
        pos = idx + len(key_token)
        # 跳過冒號前後空白，確認後接 '{'（避免 "shortcode_media": null 跳到不相干的物件）
        scan = pos
        n = len(raw)
        while scan < n and raw[scan] in " \t\r\n":
            scan += 1
        if scan >= n or raw[scan] != ":":
            continue
        scan += 1
        while scan < n and raw[scan] in " \t\r\n":
            scan += 1
        if scan >= n or raw[scan] != "{":
            continue
        try:
            media_obj, _ = decoder.raw_decode(raw, scan)
            if isinstance(media_obj, dict):
                u, cap, img = _extract_caption_from_media_obj(media_obj)
                if cap or img:
                    return u, cap, img
        except Exception:
            continue
    return "", "", None


def _decode_enclosing_json_string(
    text: str,
    marker_idx: int,
    decoder: json.JSONDecoder,
) -> Optional[str]:
    """自 marker_idx 往前有界線性尋找包裹之未轉義雙引號，以 JSONDecoder 解碼該字串。"""
    search_floor = max(0, marker_idx - 200_000)
    pos = marker_idx - 1
    while pos >= search_floor:
        if text[pos] == '"':
            bs = 0
            while pos - 1 - bs >= 0 and text[pos - 1 - bs] == "\\":
                bs += 1
            if bs % 2 == 0:
                try:
                    decoded, _ = decoder.raw_decode(text, pos)
                    if isinstance(decoded, str):
                        return decoded
                except Exception:
                    return None
                return None
        pos -= 1
    return None


def _extract_ig_shortcode_media_from_scripts(soup: BeautifulSoup) -> Tuple[str, str, Optional[str]]:
    """當 Embed DOM 缺漏內文時，以線性 JSONDecoder 從 <script> 萃取 shortcode_media（零 ReDoS，支援單層與雙層轉義）。"""
    decoder = json.JSONDecoder()
    for script in soup.find_all("script"):
        text = script.string or script.get_text() or ""
        if "shortcode_media" not in text:
            continue

        # 1. 直接 JSON 物件："shortcode_media":{...}
        u, cap, img = _extract_shortcode_media_from_json_str(text, decoder)
        if cap or img:
            return u, cap, img

        # 2. 轉義 JSON 字串（Instagram TimeSliceImpl / contextJSON，同時支援單層 \" 與雙層 \\\" 轉義）
        marker_token = "shortcode_media"
        esc_pos = 0
        for _ in range(5):
            esc_idx = text.find(marker_token, esc_pos)
            if esc_idx == -1:
                break
            esc_pos = esc_idx + len(marker_token)
            decoded_str = _decode_enclosing_json_string(text, esc_idx, decoder)
            if not decoded_str:
                continue
            u, cap, img = _extract_shortcode_media_from_json_str(decoded_str, decoder)
            if cap or img:
                return u, cap, img
            # 雙層轉義 contextJSON（例如外層為 ServerJS JSON 字串，內層再嵌 contextJSON 字串）
            nested_idx = decoded_str.find(marker_token)
            if nested_idx != -1:
                nested_str = _decode_enclosing_json_string(decoded_str, nested_idx, decoder)
                if nested_str:
                    u, cap, img = _extract_shortcode_media_from_json_str(nested_str, decoder)
                    if cap or img:
                        return u, cap, img

    return "", "", None


async def fetch_instagram_embed(url: str, timeout: float = 2.0) -> Optional[Dict[str, Any]]:
    """
    Tier 1.5 (InstaFix 同款): 抓取 Instagram `/p/{shortcode}/embed/captioned/` 輕量頁面。
    - 支援 /p/, /reel/, /reels/, /tv/, /{user}/(p|reel|reels|tv)/ 與 /share/(reel|p|tv)/ 轉址展開
    - 嚴格 2MB 有界串流與登入牆過濾
    """
    if not _is_instagram_url(url):
        return None
    if not await is_safe_url_async(url):
        return None

    shortcode = _extract_instagram_shortcode(url)
    if not shortcode and _is_instagram_share_url(url):
        shortcode = await _resolve_instagram_share_url(url, timeout=timeout)
    if not shortcode:
        return None

    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7",
    }
    client = get_search_client()
    try:
        stream_ctx = client.stream("GET", embed_url, headers=headers, timeout=timeout)
        if asyncio.iscoroutine(stream_ctx):
            stream_ctx.close()
            return None
        async with stream_ctx as resp:
            if resp.status_code != 200:
                return None
            html_text = await _read_bounded_text(resp, max_bytes=2 * 1024 * 1024)

        soup = BeautifulSoup(html_text, "html.parser")
        page_title = soup.title.get_text(strip=True) if soup.title else ""

        username = ""
        username_el = soup.select_one(".UsernameText") or soup.select_one(".CaptionUsername")
        if username_el:
            username = html.unescape(username_el.get_text(strip=True))

        caption_text = ""
        caption_el = soup.select_one(".Caption")
        if caption_el is not None:
            for noisy in caption_el.select(".CaptionComments, .CaptionUsername"):
                noisy.decompose()
            for br in caption_el.find_all("br"):
                br.replace_with("\n")
            raw_caption = html.unescape(caption_el.get_text())
            lines = [line.strip() for line in raw_caption.replace("\r\n", "\n").split("\n")]
            caption_text = "\n".join(line for line in lines if line).strip()

        image_url: Optional[str] = None
        img_el = soup.select_one(".EmbeddedMediaImage")
        if img_el and img_el.get("src"):
            image_url = html.unescape(str(img_el.get("src")).strip())
        if not image_url:
            video_el = soup.select_one(".EmbeddedMediaVideo")
            if video_el:
                raw_vid_img = video_el.get("poster") or video_el.get("src")
                if raw_vid_img:
                    image_url = html.unescape(str(raw_vid_img).strip())
        # 若 DOM 缺漏內文或媒體，自 <script> shortcode_media 補全
        if not caption_text or not image_url:
            s_user, s_caption, s_image = _extract_ig_shortcode_media_from_scripts(soup)
            if not username and s_user:
                username = s_user
            if not caption_text and s_caption:
                caption_text = html.unescape(s_caption).strip()
            if not image_url and s_image:
                image_url = s_image

        # 統一對 DOM 與 <script> 來源之 image_url 實施協議正規化與 http(s) 白名單檢查
        if image_url and image_url.startswith("//"):
            image_url = "https:" + image_url
        if image_url and not image_url.startswith(("http://", "https://")):
            image_url = None

        if not caption_text and not image_url:
            return None

        title_text = ""
        if username and caption_text:
            first_line = caption_text.splitlines()[0].strip()[:80]
            title_text = f"@{username}: {first_line}" if first_line else f"@{username} on Instagram"
        elif caption_text:
            title_text = caption_text.splitlines()[0].strip()[:80]
        elif username:
            title_text = f"@{username} on Instagram"

        # 嚴格把關社群登入牆（無 caption 時以去標籤可見文字檢查，避免被大段 <head> 樣式擠出前 600 字）
        login_check_text = caption_text if caption_text else soup.get_text(" ", strip=True)[:1200]
        if _is_social_login_wall(
            url,
            title=title_text or page_title,
            description=caption_text,
            markdown=login_check_text,
        ):
            print("⚠️ [SearchEngine] IG Embed 命中社群登入牆，捨棄無效內容")
            return None

        markdown = ""
        if caption_text:
            parts = []
            if title_text:
                parts.append(f"# {title_text}")
            parts.append("**來源平台**: Instagram")
            if username:
                parts.append(f"**作者**: @{username}")
            parts.append(f"### 貼文內文 / 摘要資訊\n{caption_text}")
            markdown = "\n\n".join(parts)[:3500]

        return {
            "title": title_text,
            "username": username,
            "description": caption_text,
            "image": image_url,
            "markdown": markdown,
        }
    except SSRFSecurityError:
        print(f"🛡️ [SearchEngine] IG Embed 命中 SSRF 攔截: {_sanitize_url_for_log(url)}")
    except Exception as e:
        print(f"⚠️ [SearchEngine] IG Embed 抓取失敗 ({_sanitize_url_for_log(url)}): {type(e).__name__}")
    return None


def _is_social_login_wall(
    url: str,
    title: str = "",
    description: str = "",
    markdown: str = "",
) -> bool:
    """判定社群網址是否回傳了通用登入牆頁面而非真實貼文內容"""
    if not SOCIAL_MEDIA_PATTERN.search(url or ""):
        return False

    norm_title = title.strip().lower()
    norm_desc = description.strip().lower()
    if norm_title in _SOCIAL_LOGIN_WALL_TITLES:
        return True
    if norm_title == "instagram" and not norm_desc:
        return True

    combined = f"{norm_title}\n{norm_desc}\n{markdown[:1200].strip().lower()}"
    return any(phrase in combined for phrase in _SOCIAL_LOGIN_WALL_PHRASES)


async def fetch_opengraph_metadata(url: str, timeout: float = 2.2) -> Optional[Dict[str, str]]:
    """
    Tier 1:
    - 社群網域採用 facebookexternalhit/1.1 抽取 OpenGraph Metadata 並嚴格過濾登入牆
    - 一般外部網站採合規識別 UA 並帶 Accept: text/markdown, text/html;q=0.9, */*;q=0.8，
      若目標站支援 Cloudflare Markdown for Agents (Content-Type: text/markdown) 則直通回傳乾淨 Markdown
    """
    is_social = bool(SOCIAL_MEDIA_PATTERN.search(url or ""))
    if is_social:
        headers = {
            "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7",
        }
    else:
        headers = {
            "User-Agent": DIRECT_FETCH_USER_AGENT,
            "Accept": "text/markdown, text/html;q=0.9, */*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7",
        }

    client = get_search_client()
    try:
        stream_ctx = client.stream("GET", url, headers=headers, timeout=timeout)
        if asyncio.iscoroutine(stream_ctx):
            stream_ctx.close()
            return None
        async with stream_ctx as resp:
            if resp.status_code != 200:
                return None
            resp_headers = getattr(resp, "headers", None)
            content_type = (resp_headers.get("content-type", "") if resp_headers else "").lower()
            media_type = content_type.split(";")[0].strip()
            # 拒絕下載二進位媒體/PDF 等非文字內容，避免浪費頻寬並阻塞 Event Loop
            if media_type and media_type not in (
                "text/markdown",
                "text/x-markdown",
                "text/html",
                "application/xhtml+xml",
                "text/plain",
            ):
                return None
            raw_text = await _read_bounded_text(resp, max_bytes=2 * 1024 * 1024)

        # Cloudflare Markdown for Agents / Anthropic 原生 Markdown 直通路徑
        if media_type in ("text/markdown", "text/x-markdown"):
            md_text = raw_text.strip()
            if not md_text:
                return None
            md_title = _extract_markdown_title(md_text)
            if _is_social_login_wall(url, title=md_title, markdown=md_text):
                print("⚠️ [SearchEngine] 原生 Markdown 回應命中社群登入牆，捨棄無效內容")
                return None
            return {
                "title": md_title,
                "description": "",
                "markdown": md_text[:3500],
                "content_type": "text/markdown",
            }

        # OpenGraph meta 與 <title> 僅存於 <head>，先切出 head 區段避免在 Event Loop 同步剖析數 MB <body>
        head_end = raw_text.lower().find("</head>")
        parse_slice = raw_text[: head_end + 7] if head_end != -1 else raw_text[:262144]
        soup = BeautifulSoup(parse_slice, "html.parser")

        def _get_meta(prop_names: List[str]) -> str:
            for name in prop_names:
                tag = soup.find("meta", property=name) or soup.find("meta", attrs={"name": name})
                if tag and tag.get("content"):
                    return tag["content"].strip()
            return ""

        title = _get_meta(["og:title", "twitter:title"])
        if not title and soup.title:
            title = soup.title.get_text(strip=True)

        description = _get_meta(["og:description", "twitter:description", "description"])
        site_name = _get_meta(["og:site_name"])

        if title or description:
            clean_title = html.unescape(title) if title else ""
            clean_desc = html.unescape(description) if description else ""
            if _is_social_login_wall(url, title=clean_title, description=clean_desc):
                print("⚠️ [SearchEngine] OpenGraph 命中社群登入牆，捨棄無效登入頁摘要")
                return None

            parts = []
            if clean_title:
                parts.append(f"# {clean_title}")
            if site_name:
                parts.append(f"**來源平台**: {site_name}")
            if clean_desc:
                parts.append(f"### 貼文內文 / 摘要資訊\n{clean_desc}")

            return {
                "title": clean_title,
                "description": clean_desc,
                "markdown": "\n\n".join(parts)[:3500],
            }
    except Exception as e:
        print(f"⚠️ [SearchEngine] OpenGraph 抓取失敗 ({_sanitize_url_for_log(url)}): {type(e).__name__}")
    return None


async def _fetch_jina_reader_uncached(
    real_url: str,
    wait_for_selector: Optional[str] = None,
    target_selector: Optional[str] = None,
    cache_key: str = "",
) -> Dict[str, Any]:
    """四層漏斗核心執行體（Tier 1 -> Tier 1.5 -> Tier 2 Jina Reader）。"""
    is_social = bool(SOCIAL_MEDIA_PATTERN.search(real_url))
    og_attempted = False
    prefetched_og_fallback: Optional[Dict[str, Any]] = None

    def _cache_and_return(payload: Dict[str, Any]) -> Dict[str, Any]:
        if cache_key:
            _reader_cache_set(cache_key, payload, is_social=is_social)
        return payload

    async def _og_fallback_or_error(error_code: str, message: str) -> Dict[str, Any]:
        if prefetched_og_fallback and prefetched_og_fallback.get("markdown"):
            return _cache_and_return({
                "status": "success",
                "url": real_url,
                "title": prefetched_og_fallback.get("title", ""),
                "markdown": prefetched_og_fallback["markdown"],
            })
        # 避免社群 URL 已在 Tier 1 失敗／命中登入牆後重複請求兩次 OpenGraph
        if not og_attempted:
            og_fallback = await fetch_opengraph_metadata(real_url)
            if og_fallback and og_fallback.get("markdown"):
                return _cache_and_return({
                    "status": "success",
                    "url": real_url,
                    "title": og_fallback.get("title", ""),
                    "markdown": og_fallback["markdown"],
                })
        return {
            "status": "error",
            "error_code": error_code,
            "message": message,
            "markdown": "",
        }

    # 1. Tier 1 / Tier 1.5 智慧分流
    if is_social:
        og_attempted = True
        og_data = await fetch_opengraph_metadata(real_url)
        if og_data and og_data.get("markdown"):
            return _cache_and_return({
                "status": "success",
                "url": real_url,
                "title": og_data.get("title", ""),
                "markdown": og_data["markdown"],
            })

        # Tier 1.5: Instagram `/p/{shortcode}/embed/captioned/` 輕量備援
        if _is_instagram_url(real_url):
            embed_data = await fetch_instagram_embed(real_url)
            if embed_data and embed_data.get("markdown"):
                return _cache_and_return({
                    "status": "success",
                    "url": real_url,
                    "title": embed_data.get("title", ""),
                    "markdown": embed_data["markdown"],
                })
    elif not wait_for_selector and not target_selector:
        # 一般外部網站：發起 1.5s 機會型 Accept: text/markdown 探針（最壞 1.5s + Jina 8.5s = 10.0s < 11.0s 外層預算）；
        # 若回 HTML 則暫存 OG 供 Jina 失敗時零額外 I/O 備援
        og_attempted = True
        direct_data = await fetch_opengraph_metadata(real_url, timeout=1.5)
        if direct_data and direct_data.get("markdown"):
            if direct_data.get("content_type") == "text/markdown":
                return _cache_and_return({
                    "status": "success",
                    "url": real_url,
                    "title": direct_data.get("title", ""),
                    "markdown": direct_data["markdown"],
                })
            prefetched_og_fallback = direct_data

    # 2. Tier 2: Jina Reader（對齊 jina-ai/reader crawler-options.ts，移除會誤殺長頁之 X-Token-Budget）
    client = get_search_client()
    jina_endpoint = f"https://r.jina.ai/{real_url}"
    jina_timeout = httpx.Timeout(8.5, connect=3.0)

    headers = {
        "Accept": "text/markdown",
        "X-Respond-With": "markdown",
        "X-Timeout": "8",
        "X-Max-Tokens": "3500",
        "X-Retain-Images": "alt",
        "X-Retain-Media": "none",
        "X-Retain-Links": "text",
    }
    if wait_for_selector:
        headers["X-Wait-For-Selector"] = wait_for_selector
    if target_selector:
        headers["X-Target-Selector"] = target_selector

    try:
        stream_ctx = client.stream("GET", jina_endpoint, headers=headers, timeout=jina_timeout)
        if asyncio.iscoroutine(stream_ctx):
            stream_ctx.close()
            resp = await client.get(jina_endpoint, headers=headers, timeout=jina_timeout)
            status_code = resp.status_code
            raw_text = (resp.text or "") if status_code == 200 else ""
        else:
            async with stream_ctx as resp:
                status_code = resp.status_code
                raw_text = await _read_bounded_text(resp, max_bytes=2 * 1024 * 1024) if status_code == 200 else ""

        if status_code == 200:
            md_content = raw_text.strip()
            if md_content:
                md_title = _extract_markdown_title(md_content)
                if _is_social_login_wall(real_url, title=md_title, markdown=md_content):
                    return {
                        "status": "error",
                        "error_code": "LOGIN_WALL",
                        "message": "該社群貼文受登入牆保護，無法直接讀取內文，已為您自動採用搜尋摘要進行分析",
                        "markdown": "",
                    }
                return _cache_and_return({
                    "status": "success",
                    "url": real_url,
                    "title": md_title,
                    "markdown": md_content[:3500],  # 後端上限防護
                })
            return {
                "status": "error",
                "error_code": "EMPTY_CONTENT",
                "message": "網頁無可讀取之正文內容",
                "markdown": "",
            }
        elif status_code in [401, 403]:
            print(f"⚠️ [SearchEngine] Jina Reader HTTP {status_code} ({_sanitize_url_for_log(real_url)})，嘗試 OpenGraph 備援...")
            return await _og_fallback_or_error(
                "READER_UNAVAILABLE",
                "該網頁受防爬保護或連線受限，已為您自動採用搜尋摘要進行分析",
            )
        else:
            print(f"⚠️ [SearchEngine] Jina Reader HTTP {status_code} ({_sanitize_url_for_log(real_url)})")
            return await _og_fallback_or_error(
                f"HTTP_{status_code}",
                f"網頁讀取服務回應異常代碼 {status_code}",
            )
    except httpx.TimeoutException:
        print(f"⏱️ [SearchEngine] Jina Reader 讀取逾時 (>8.5s) ({_sanitize_url_for_log(real_url)})，嘗試 OpenGraph 備援...")
        return await _og_fallback_or_error(
            "TIMEOUT",
            "網頁回應過慢，已為您自動採用搜尋摘要進行分析",
        )
    except Exception as e:
        print(f"⚠️ [SearchEngine] Jina Reader 讀取異常 ({_sanitize_url_for_log(real_url)}): {type(e).__name__}，嘗試 OpenGraph 備援...")
        return await _og_fallback_or_error(
            "NETWORK_ERROR",
            "網路連線異常，已為您自動採用搜尋摘要進行分析",
        )


async def fetch_jina_reader(
    url: str,
    wait_for_selector: Optional[str] = None,
    target_selector: Optional[str] = None,
) -> Dict[str, Any]:
    """
    四層零成本網頁／社群提取漏斗：
    - Tier 0: LRU 成功快取（社群 1h / 一般 30m）+ Event-Loop 分桶 Singleflight 去重
    - Tier 1: 社群 OpenGraph 爬蟲 / 一般網站 `Accept: text/markdown` 直通
    - Tier 1.5: Instagram `/p/{shortcode}/embed/captioned/`（含 `/share/reel/` 轉址展開）
    - Tier 2: Jina Reader (`X-Timeout: 8`, `X-Max-Tokens: 3500`, 2MB 有界串流)
    """
    real_url = unwrap_ddg_redirect(url)
    if not await is_safe_url_async(real_url):
        return {
            "status": "error",
            "error_code": "INVALID_URL",
            "message": "不支援或不安全的網址協議",
            "markdown": "",
        }

    cache_key = _normalize_reader_cache_key(
        real_url,
        wait_for_selector=wait_for_selector,
        target_selector=target_selector,
    )
    cached = _reader_cache_get(cache_key)
    if cached is not None:
        cached["url"] = real_url
        return cached

    loop = asyncio.get_running_loop()
    loop_inflight = _URL_INFLIGHT_BY_LOOP.get(loop)
    if loop_inflight is None:
        loop_inflight = {}
        _URL_INFLIGHT_BY_LOOP[loop] = loop_inflight

    entry = loop_inflight.get(cache_key)
    if entry is not None and entry[1] > 0 and not entry[0].done():
        task = entry[0]
        entry[1] += 1
    else:
        task = loop.create_task(
            _fetch_jina_reader_uncached(
                real_url,
                wait_for_selector=wait_for_selector,
                target_selector=target_selector,
                cache_key=cache_key,
            )
        )
        entry = [task, 1]
        loop_inflight[cache_key] = entry

        def _cleanup_inflight(
            done_task: asyncio.Task,
            _key: str = cache_key,
            _bucket: Dict[str, List[Any]] = loop_inflight,
        ) -> None:
            current = _bucket.get(_key)
            if current is not None and current[0] is done_task:
                _bucket.pop(_key, None)
            if not done_task.cancelled():
                try:
                    done_task.exception()
                except Exception:
                    pass

        task.add_done_callback(_cleanup_inflight)

    try:
        res = await asyncio.shield(task)
    finally:
        entry[1] -= 1
        if entry[1] <= 0 and not task.done():
            task.cancel()

    if res.get("status") == "success":
        return dict(res, url=real_url)
    return dict(res)
