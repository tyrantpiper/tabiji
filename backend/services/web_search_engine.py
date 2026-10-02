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
import urllib.parse
import ipaddress
import httpx
from typing import List, Dict, Optional, Any
from bs4 import BeautifulSoup

# 全域共用非同步 HTTP 連線池
_http_client: Optional[httpx.AsyncClient] = None

# 擬真瀏覽器 User-Agent (防禦 DDG HTML 驗證碼阻擋)
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# SSRF 私有 IP 阻擋清單
PRIVATE_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def get_search_client() -> httpx.AsyncClient:
    """取得或初始化全域非同步 HTTP 連線"""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(4.5, connect=2.0),
            headers={
                "User-Agent": BROWSER_USER_AGENT,
                "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7",
            },
            follow_redirects=True,
        )
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
    """SSRF 防禦：檢查是否為合法的外部 HTTP/HTTPS 公共網址"""
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return False
    try:
        hostname = urllib.parse.urlparse(url).hostname
        if not hostname:
            return False
        if hostname.lower() in PRIVATE_HOSTS:
            return False
        # 檢查是否為私有 IP
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
        except ValueError:
            pass  # 一般域名通過
        return True
    except Exception:
        return False


# Cloudflare 邊緣檢索執行器配置 (Tier 2)
CF_WORKER_SEARCH_URL = os.environ.get("CF_WORKER_SEARCH_URL", "https://tabidachi-search-proxy.ryanpig228.workers.dev")
CF_PROXY_SECRET = os.environ.get("CF_PROXY_SECRET", "")


async def _search_cloudflare_edge(query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """
    第 2 層保險：Cloudflare 邊緣檢索器 (Anycast IP 洗白)
    由全球 300+ 邊緣節點直接抓取並回傳結構化 JSON，零機房 IP 封鎖風險。
    """
    if not CF_WORKER_SEARCH_URL:
        return []
    client = get_search_client()
    headers = {"x-tabidachi-key": CF_PROXY_SECRET} if CF_PROXY_SECRET else {}
    try:
        resp = await client.get(
            f"{CF_WORKER_SEARCH_URL.rstrip('/')}/search",
            params={"q": query, "limit": max_results},
            headers=headers,
            timeout=3.2
        )
        if resp.status_code == 200:
            data = resp.json()
            raw_list = data.get("results", [])
            results = []
            for r in raw_list:
                u = r.get("url")
                if u and is_safe_external_url(u):
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
    """
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
        "User-Agent": "TabidachiTravelPWA/1.0 (https://tabidachi.app; dev@tabidachi.app)",
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
                if u and is_safe_external_url(u):
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
                if real_url and is_safe_external_url(real_url):
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
                    if real_url and is_safe_external_url(real_url):
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
    # 剔除 wikipedia 與 grokipedia 百科引擎，優先調度真實網路搜尋引擎
    search_backends = "yahoo,duckduckgo,startpage,brave,mojeek,google"
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

    # 1. [Tier 1] 本地 Dux 多引擎 (非同步線程，限時 5.2 秒覆蓋正常多引擎開銷)
    try:
        results = await asyncio.wait_for(
            asyncio.to_thread(_sync_ddgs_call, final_query, resolved_region, max_results),
            timeout=5.2
        )
        if results:
            return results
    except Exception as e:
        print(f"⚠️ [SearchEngine] Tier 1 本地查詢未命中 ({e})，切換至 Tier 2 Cloudflare 邊緣...")

    # 2. [Tier 2] Cloudflare 邊緣檢索執行器 (Anycast IP 洗白)
    cf_results = await _search_cloudflare_edge(final_query, max_results=max_results)
    if cf_results:
        return cf_results

    # 3. [Tier 3] 靜態 Lite / HTML 端點
    html_results = await _search_ddg_html_fallback(final_query, max_results=max_results)
    if html_results:
        return html_results

    # 4. [Tier 4] Wikipedia 官方開放 API 硬事實兜底
    print("⚠️ [SearchEngine] 搜尋引擎全面受阻，啟用 Tier 4 Wikipedia 官方 API 兜底...")
    wiki_results = await _search_wikipedia_fallback(trimmed, max_results=max_results)
    if wiki_results:
        return wiki_results

    return []


# 社群媒體網址模式 (IG / Threads / FB / TikTok / X / Twitter)
SOCIAL_MEDIA_PATTERN = re.compile(
    r"https?://(?:www\.)?(instagram\.com|threads\.net|facebook\.com|fb\.watch|tiktok\.com|twitter\.com|x\.com)/",
    re.IGNORECASE,
)


async def fetch_opengraph_metadata(url: str) -> Optional[Dict[str, str]]:
    """
    使用社群爬蟲 User-Agent (facebookexternalhit / Googlebot) 直接抽取 OpenGraph Metadata
    專門防禦社群媒體 (IG/Threads/FB) 登入牆與 Jina Reader 403 阻擋
    """
    headers = {
        "User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7",
    }
    client = get_search_client()
    try:
        resp = await client.get(url, headers=headers, timeout=4.0)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")

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
        print(f"⚠️ [SearchEngine] OpenGraph 抓取失敗: {e}")
    return None


async def fetch_jina_reader(
    url: str,
    wait_for_selector: Optional[str] = None,
    target_selector: Optional[str] = None
) -> Dict[str, Any]:
    """
    呼叫 Jina Reader (https://r.jina.ai/{url}) 進行深度網頁精讀
    - 免 Key 支援 (20 RPM)
    - 智慧社群分流：若為 IG/Threads/FB 等社群平台，優先採用 OpenGraph 專用爬蟲秒解貼文
    - 遇到 401 (ASN 信譽阻斷) 或連線逾時，自動優雅回退至 OpenGraph 或搜尋摘要，不崩潰
    """
    real_url = unwrap_ddg_redirect(url)
    if not is_safe_external_url(real_url):
        return {
            "status": "error",
            "error_code": "INVALID_URL",
            "message": "不支援或不安全的網址協議",
            "markdown": ""
        }

    # 1. 社群媒體網址優先路徑 (IG / Threads / FB 防爬牆極強，OpenGraph 直取最穩)
    if SOCIAL_MEDIA_PATTERN.search(real_url):
        og_data = await fetch_opengraph_metadata(real_url)
        if og_data and og_data.get("markdown"):
            return {
                "status": "success",
                "url": real_url,
                "markdown": og_data["markdown"]
            }

    # 2. 標準 Jina Reader 路徑
    client = get_search_client()
    jina_endpoint = f"https://r.jina.ai/{real_url}"

    headers = {
        "Accept": "text/markdown",
        "X-Respond-With": "markdown",
        "X-Timeout": "4000",
        "X-Token-Budget": "2500",
    }
    if wait_for_selector:
        headers["X-Wait-For-Selector"] = wait_for_selector
    if target_selector:
        headers["X-Target-Selector"] = target_selector

    try:
        resp = await client.get(jina_endpoint, headers=headers)
        if resp.status_code == 200:
            md_content = resp.text.strip()
            if md_content:
                return {
                    "status": "success",
                    "url": real_url,
                    "markdown": md_content[:3500]  # 後端上限防護
                }
            return {
                "status": "error",
                "error_code": "EMPTY_CONTENT",
                "message": "網頁無可讀取之正文內容",
                "markdown": ""
            }
        elif resp.status_code in [401, 403]:
            # Jina 免費節點 ASN 聲譽風控或目標網站反爬 -> 嘗試 OpenGraph 回退
            print(f"⚠️ [SearchEngine] Jina Reader HTTP {resp.status_code}，嘗試 OpenGraph 備援...")
            og_fallback = await fetch_opengraph_metadata(real_url)
            if og_fallback and og_fallback.get("markdown"):
                return {
                    "status": "success",
                    "url": real_url,
                    "markdown": og_fallback["markdown"]
                }
            return {
                "status": "error",
                "error_code": "READER_UNAVAILABLE",
                "message": "該網頁受防爬保護或連線受限，已為您自動採用搜尋摘要進行分析",
                "markdown": ""
            }
        else:
            og_fallback = await fetch_opengraph_metadata(real_url)
            if og_fallback and og_fallback.get("markdown"):
                return {
                    "status": "success",
                    "url": real_url,
                    "markdown": og_fallback["markdown"]
                }
            return {
                "status": "error",
                "error_code": f"HTTP_{resp.status_code}",
                "message": f"網頁讀取服務回應異常代碼 {resp.status_code}",
                "markdown": ""
            }
    except httpx.TimeoutException:
        print("⏱️ [SearchEngine] Jina Reader 讀取逾時 (>4.0s)，嘗試 OpenGraph 備援...")
        og_fallback = await fetch_opengraph_metadata(real_url)
        if og_fallback and og_fallback.get("markdown"):
            return {
                "status": "success",
                "url": real_url,
                "markdown": og_fallback["markdown"]
            }
        return {
            "status": "error",
            "error_code": "TIMEOUT",
            "message": "網頁回應過慢，已為您自動採用搜尋摘要進行分析",
            "markdown": ""
        }
    except Exception as e:
        print(f"⚠️ [SearchEngine] Jina Reader 讀取異常: {e}，嘗試 OpenGraph 備援...")
        og_fallback = await fetch_opengraph_metadata(real_url)
        if og_fallback and og_fallback.get("markdown"):
            return {
                "status": "success",
                "url": real_url,
                "markdown": og_fallback["markdown"]
            }
        return {
            "status": "error",
            "error_code": "NETWORK_ERROR",
            "message": "網路連線異常，已為您自動採用搜尋摘要進行分析",
            "markdown": ""
        }
