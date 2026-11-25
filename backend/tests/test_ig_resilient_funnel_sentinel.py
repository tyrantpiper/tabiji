import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main as main_module
from main import app, _clean_detected_url, _has_searchable_text_beyond_urls
from routers import expenses as expenses_router
from routers import trips as trips_router
from routers import users as users_router
from services import geocode_service, link_resolver, web_search_engine
from services.intent_router import _extract_clean_user_text
from utils.url_safety import SSRFSecurityError, create_safe_client


def _make_mock_transport_client(handler, *, follow_redirects: bool = True, clear_cookies: bool = False):
    """Build an httpx.AsyncClient backed by MockTransport (optionally with cookie-clearing hook)."""
    holder = [None]

    async def _clear_cookies(resp: httpx.Response) -> None:
        c = holder[0]
        if c is not None and not c.is_closed:
            c.cookies.clear()

    hooks = {"response": [_clear_cookies]} if clear_cookies else None
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=follow_redirects,
        event_hooks=hooks,
    )
    holder[0] = client
    return client


# ═══════════════════════════════════════════════════════════════════════════════
# AC-1: Jina Reader Header Contract, 2MB Bounded Streaming, Title & Cookie Isolation
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_jina_headers_contract_bounded_streaming_and_title():
    captured_headers = {}
    chunks_yielded = 0

    class _LargeJinaStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal chunks_yielded
            chunks_yielded += 1
            yield (
                "Title: 大阪梅田超人氣燒肉 焼肉エイト\n\n"
                "URL Source: https://www.tokyo-skytree.jp/long-page\n\n"
                "Markdown Content:\n# 焼肉エイト\n大阪梅田茶屋町超值和牛吃到飽。\n"
            ).encode("utf-8")
            for _ in range(80):  # ~5MB total -> must stop at <=2MB
                chunks_yielded += 1
                yield b"X" * 65536

    def _handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "r.jina.ai":
            captured_headers.update({k.lower(): v for k, v in req.headers.items()})
            return httpx.Response(
                200,
                headers={"Content-Type": "text/markdown; charset=utf-8"},
                stream=_LargeJinaStream(),
            )
        return httpx.Response(404, text="not found")

    async with _make_mock_transport_client(_handler) as client:
        with patch("services.web_search_engine.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
             patch("services.web_search_engine.get_search_client", return_value=client):
            res = await web_search_engine.fetch_jina_reader("https://www.tokyo-skytree.jp/long-page")

    assert res["status"] == "success"
    assert res["title"] == "大阪梅田超人氣燒肉 焼肉エイト"
    assert "焼肉エイト" in res["markdown"]
    assert len(res["markdown"]) <= 3500
    assert chunks_yielded <= 35, f"Jina stream was not bounded at 2MB: yielded {chunks_yielded} chunks"

    # Strict Jina crawler-options.ts header contract
    assert "x-token-budget" not in captured_headers
    assert captured_headers.get("accept") == "text/markdown"
    assert captured_headers.get("x-respond-with") == "markdown"
    assert captured_headers.get("x-timeout") == "8"
    assert captured_headers.get("x-max-tokens") == "3500"
    assert captured_headers.get("x-retain-images") == "alt"
    assert captured_headers.get("x-retain-media") == "none"
    assert captured_headers.get("x-retain-links") == "text"


@pytest.mark.asyncio
async def test_search_client_clears_cookies_across_requests():
    seen_cookies = []

    def _handler(req: httpx.Request) -> httpx.Response:
        seen_cookies.append((req.url.host, req.headers.get("cookie")))
        if req.url.host == "www.instagram.com":
            return httpx.Response(200, headers={"Set-Cookie": "csrftoken=meta_secret; Path=/"}, text="ok")
        return httpx.Response(200, text="ok")

    orig_create = web_search_engine.create_safe_client

    def _patched_create_safe_client(**kwargs):
        kwargs["transport"] = httpx.MockTransport(_handler)
        return orig_create(**kwargs)

    await web_search_engine.close_search_client()
    try:
        with patch("utils.url_safety.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
             patch("services.web_search_engine.create_safe_client", side_effect=_patched_create_safe_client):
            client = web_search_engine.get_search_client()
            await client.get("https://www.instagram.com/reel/ABC12345/")
            assert len(client.cookies) == 0
            await client.get("https://www.instagram.com/reel/XYZ98765/")
            await client.get("https://example.com/page")
    finally:
        await web_search_engine.close_search_client()

    assert seen_cookies == [
        ("www.instagram.com", None),
        ("www.instagram.com", None),
        ("example.com", None),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# AC-2: IG Tier 1.5 Embed DOM + Script Fallback, /share/ Redirect & SSRF Guard
# ═══════════════════════════════════════════════════════════════════════════════


def test_instagram_shortcode_extraction_variants():
    assert web_search_engine._extract_instagram_shortcode("https://www.instagram.com/reel/DX8x6XOtEqI/") == "DX8x6XOtEqI"
    assert web_search_engine._extract_instagram_shortcode("https://m.instagram.com/reels/DX8x6XOtEqI/?igsh=1") == "DX8x6XOtEqI"
    assert web_search_engine._extract_instagram_shortcode("https://instagram.com/p/AbC_123-xyz") == "AbC_123-xyz"
    assert web_search_engine._extract_instagram_shortcode("https://instagr.am/tv/TVcode12345/") == "TVcode12345"
    assert web_search_engine._extract_instagram_shortcode("https://www.instagram.com/osaka.foodie/reel/DX8x6XOtEqI/") == "DX8x6XOtEqI"
    # /share/reel/... must NOT be mistaken for username="share"
    assert web_search_engine._extract_instagram_shortcode("https://www.instagram.com/share/reel/BAc1234567/") is None
    assert web_search_engine._is_instagram_share_url("https://www.instagram.com/share/reel/BAc1234567/") is True


@pytest.mark.asyncio
async def test_instagram_embed_dom_caption_and_br_newlines_and_script_fallback():
    ig_url = "https://www.instagram.com/reel/DX8x6XOtEqI/?igsh=abc"
    login_og_html = (
        "<html><head><title>登入 • Instagram</title>"
        '<meta property="og:description" content="建立帳號或登入 Instagram" /></head></html>'
    )
    embed_dom_html = (
        "<html><body>"
        '<div class="Header"><span class="UsernameText">osaka_foodie</span></div>'
        '<img class="EmbeddedMediaImage" src="https://scontent.cdninstagram.com/v/cover.jpg?a=1&amp;b=2" />'
        '<div class="Caption">'
        '<a class="CaptionUsername">osaka_foodie</a>'
        "🇯🇵大阪梅田必吃燒肉<br/>｜焼肉エイト 梅田茶屋町店｜<br>黑毛和牛吃到飽 ¥2980 起"
        '<div class="CaptionComments"><a class="CaptionCommentsExpand">View all 88 comments</a></div>'
        "</div></body></html>"
    )

    called_urls = []

    def _handler(req: httpx.Request) -> httpx.Response:
        called_urls.append(str(req.url))
        if "/embed/captioned/" in req.url.path:
            return httpx.Response(200, headers={"Content-Type": "text/html; charset=utf-8"}, text=embed_dom_html)
        return httpx.Response(200, headers={"Content-Type": "text/html; charset=utf-8"}, text=login_og_html)

    async with _make_mock_transport_client(_handler) as client:
        with patch("services.web_search_engine.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
             patch("services.web_search_engine.get_search_client", return_value=client):
            res = await web_search_engine.fetch_jina_reader(ig_url)

    assert res["status"] == "success"
    assert "osaka_foodie" in res["title"]
    assert "🇯🇵大阪梅田必吃燒肉\n｜焼肉エイト 梅田茶屋町店｜\n黑毛和牛吃到飽 ¥2980 起" in res["markdown"]
    assert "View all 88 comments" not in res["markdown"]
    # Jina should NOT have been called since Tier 1.5 succeeded
    assert not any("r.jina.ai" in u for u in called_urls)
    assert any("/p/DX8x6XOtEqI/embed/captioned/" in u for u in called_urls)

    # Script fallback: DOM lacks .Caption, payload inside escaped TimeSliceImpl script string
    inner_payload = json.dumps({
        "gql_data": {
            "shortcode_media": {
                "owner": {"username": "kyoto_cafe"},
                "display_url": "https://scontent.cdninstagram.com/v/matcha.jpg",
                "edge_media_to_caption": {
                    "edges": [{"node": {"text": "京都宇治抹茶名店\n中村藤吉本店"}}]
                },
            }
        }
    })
    escaped_js_literal = json.dumps(inner_payload)
    embed_script_html = (
        f"<html><body><script>window.__additionalDataLoaded('extra', JSON.parse({escaped_js_literal}));</script></body></html>"
    )

    def _script_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "text/html; charset=utf-8"}, text=embed_script_html)

    async with _make_mock_transport_client(_script_handler) as client2:
        with patch("services.web_search_engine.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
             patch("services.web_search_engine.get_search_client", return_value=client2):
            embed_res = await web_search_engine.fetch_instagram_embed("https://www.instagram.com/p/ScriptCode99/")

    assert embed_res is not None
    assert embed_res["username"] == "kyoto_cafe"
    assert "中村藤吉本店" in embed_res["description"]
    assert embed_res["image"] == "https://scontent.cdninstagram.com/v/matcha.jpg"


@pytest.mark.asyncio
async def test_instagram_share_reel_redirect_expansion_and_ssrf_block():
    share_url = "https://www.instagram.com/share/reel/BAcShareToken99/"
    embed_html = (
        "<html><body>"
        '<span class="UsernameText">tokyo_ramen</span>'
        '<div class="Caption">東京新宿拉麵推薦：麵屋武藏</div>'
        "</body></html>"
    )

    def _ok_redirect_handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.startswith("/share/reel/"):
            return httpx.Response(302, headers={"Location": "https://www.instagram.com/reel/ExpandedCode77/"})
        if req.url.path == "/reel/ExpandedCode77/":
            return httpx.Response(200, text="<html><title>ok</title></html>")
        if req.url.path == "/p/ExpandedCode77/embed/captioned/":
            return httpx.Response(200, text=embed_html)
        return httpx.Response(404)

    async with _make_mock_transport_client(_ok_redirect_handler) as client:
        with patch("services.web_search_engine.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
             patch("services.web_search_engine.get_search_client", return_value=client):
            res = await web_search_engine.fetch_instagram_embed(share_url)

    assert res is not None
    assert "麵屋武藏" in res["markdown"]

    # SSRF redirect guard: /share/reel/ redirects to GCP metadata IP 169.254.169.254 -> MUST BE BLOCKED
    ssrf_target_hit = False

    def _ssrf_redirect_handler(req: httpx.Request) -> httpx.Response:
        nonlocal ssrf_target_hit
        if req.url.host == "169.254.169.254":
            ssrf_target_hit = True
            return httpx.Response(200, text="SECRET_GCP_TOKEN")
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})

    async with create_safe_client(
        follow_redirects=True,
        transport=httpx.MockTransport(_ssrf_redirect_handler),
    ) as safe_client:
        with patch("utils.url_safety.get_safe_ip", return_value="157.240.1.174"), \
             patch("services.web_search_engine.get_search_client", return_value=safe_client):
            ssrf_res = await web_search_engine.fetch_instagram_embed(share_url)

    assert ssrf_res is None
    assert ssrf_target_hit is False


def test_expanded_social_domains_and_login_wall_phrases():
    for u in (
        "https://m.instagram.com/reel/ABC12345/",
        "https://instagr.am/p/ABC12345/",
        "https://ig.me/p/ABC12345/",
        "https://www.threads.com/@user/post/123",
        "https://m.facebook.com/story.php?id=1",
        "https://mbasic.facebook.com/story.php?id=1",
        "https://vm.tiktok.com/ZM12345/",
        "https://vt.tiktok.com/ZS12345/",
        "https://mobile.twitter.com/user/status/123",
    ):
        assert web_search_engine.SOCIAL_MEDIA_PATTERN.search(u), f"Should match social URL: {u}"

    assert not web_search_engine.SOCIAL_MEDIA_PATTERN.search("https://instagram.com.evil.com/reel/ABC/")
    assert not web_search_engine.SOCIAL_MEDIA_PATTERN.search("https://example.com/instagram.com")

    ig_url = "https://m.instagram.com/reel/ABC12345/"
    assert web_search_engine._is_social_login_wall(ig_url, markdown="建立帳號或登入 Instagram 以繼續") is True
    assert web_search_engine._is_social_login_wall(ig_url, markdown="Log in to see photos and videos from friends.") is True
    assert web_search_engine._is_social_login_wall(ig_url, markdown="Sign up to see photos and videos from friends.") is True


# ═══════════════════════════════════════════════════════════════════════════════
# AC-3: Cloudflare / Anthropic Accept: text/markdown Direct Passthrough
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_accept_text_markdown_direct_passthrough_skips_jina():
    seen_requests = []

    def _handler(req: httpx.Request) -> httpx.Response:
        seen_requests.append((str(req.url), req.headers.get("accept", ""), req.headers.get("user-agent", "")))
        return httpx.Response(
            200,
            headers={"Content-Type": "text/markdown; charset=utf-8"},
            text="# Cloudflare Edge Guide\n\nServed natively as clean Markdown.",
        )

    async with _make_mock_transport_client(_handler) as client:
        with patch("services.web_search_engine.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
             patch("services.web_search_engine.get_search_client", return_value=client):
            res = await web_search_engine.fetch_jina_reader("https://developers.cloudflare.com/agents/")

    assert res["status"] == "success"
    assert res["title"] == "Cloudflare Edge Guide"
    assert "Served natively as clean Markdown." in res["markdown"]
    assert len(seen_requests) == 1
    url, accept, ua = seen_requests[0]
    assert url == "https://developers.cloudflare.com/agents/"
    assert "text/markdown" in accept
    assert "facebookexternalhit" not in ua.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# AC-4: Tier 0 LRU Cache, Failure Non-Caching, Singleflight & Cross-Loop Isolation
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tier0_cache_hit_failure_not_cached_and_singleflight_dedup():
    call_count = 0

    def _handler(req: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            headers={"Content-Type": "text/markdown"},
            text="# Cached Guide\n\nContent from upstream.",
        )

    async with _make_mock_transport_client(_handler) as client:
        with patch("services.web_search_engine.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
             patch("services.web_search_engine.get_search_client", return_value=client):
            r1 = await web_search_engine.fetch_jina_reader("https://example.com/guide?utm_source=ig")
            r2 = await web_search_engine.fetch_jina_reader("https://example.com/guide?utm_medium=share")

    assert r1["status"] == "success"
    assert r2["status"] == "success"
    assert call_count == 1  # Tracking params stripped -> same cache key, 1 upstream call

    # Errors MUST NOT be cached
    web_search_engine.__reset_web_search_cache_for_testing()
    fail_calls = 0

    def _fail_then_ok(req: httpx.Request) -> httpx.Response:
        nonlocal fail_calls
        fail_calls += 1
        if fail_calls <= 2:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(200, headers={"Content-Type": "text/markdown"}, text="# Recovered\n\nOK")

    async with _make_mock_transport_client(_fail_then_ok) as client_fail:
        with patch("services.web_search_engine.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
             patch("services.web_search_engine.get_search_client", return_value=client_fail):
            err_res = await web_search_engine.fetch_jina_reader("https://example.com/flaky")
            ok_res = await web_search_engine.fetch_jina_reader("https://example.com/flaky")

    assert err_res["status"] == "error"
    assert ok_res["status"] == "success"

    # Singleflight: 5 concurrent callers -> 1 upstream call
    web_search_engine.__reset_web_search_cache_for_testing()
    sf_calls = 0

    async def _slow_uncached(real_url, **kwargs):
        nonlocal sf_calls
        sf_calls += 1
        await asyncio.sleep(0.05)
        payload = {"status": "success", "url": real_url, "title": "SF", "markdown": "# SF\nBody"}
        web_search_engine._reader_cache_set(kwargs["cache_key"], payload, is_social=False)
        return payload

    with patch("services.web_search_engine.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
         patch("services.web_search_engine._fetch_jina_reader_uncached", side_effect=_slow_uncached):
        results = await asyncio.gather(
            *[web_search_engine.fetch_jina_reader("https://example.com/concurrent") for _ in range(5)]
        )

    assert sf_calls == 1
    assert all(r["status"] == "success" and r["title"] == "SF" for r in results)

    # Singleflight partial cancellation: waiter 1 times out, waiter 2 still receives result from same single upstream call
    web_search_engine.__reset_web_search_cache_for_testing()
    cancel_sf_calls = 0

    async def _slow_cancel_uncached(real_url, **kwargs):
        nonlocal cancel_sf_calls
        cancel_sf_calls += 1
        await asyncio.sleep(0.08)
        payload = {"status": "success", "url": real_url, "title": "Survived", "markdown": "# Survived\nBody"}
        web_search_engine._reader_cache_set(kwargs["cache_key"], payload, is_social=False)
        return payload

    with patch("services.web_search_engine.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
         patch("services.web_search_engine._fetch_jina_reader_uncached", side_effect=_slow_cancel_uncached):
        t1 = asyncio.create_task(asyncio.wait_for(web_search_engine.fetch_jina_reader("https://example.com/cancel-sf"), timeout=0.02))
        t2 = asyncio.create_task(web_search_engine.fetch_jina_reader("https://example.com/cancel-sf"))
        with pytest.raises(asyncio.TimeoutError):
            await t1
        r_survived = await t2

    assert cancel_sf_calls == 1
    assert r_survived["status"] == "success" and r_survived["title"] == "Survived"

    # LRU eviction at >128 entries and TTL expiry
    web_search_engine.__reset_web_search_cache_for_testing()
    for i in range(135):
        web_search_engine._reader_cache_set(
            f"https://example.com/item-{i}|w=|t=",
            {"status": "success", "url": f"https://example.com/item-{i}", "title": f"T{i}", "markdown": f"# T{i}"},
            is_social=False,
        )
    assert len(web_search_engine._URL_READER_CACHE) == 128
    assert web_search_engine._reader_cache_get("https://example.com/item-0|w=|t=") is None
    assert web_search_engine._reader_cache_get("https://example.com/item-134|w=|t=") is not None

    # General HTML site: direct fetch stashes OG -> Jina 403 -> returns prefetched OG with 0 duplicate origin requests
    web_search_engine.__reset_web_search_cache_for_testing()
    origin_hits = 0
    jina_hits = 0

    def _html_fallback_handler(req: httpx.Request) -> httpx.Response:
        nonlocal origin_hits, jina_hits
        if req.url.host == "r.jina.ai":
            jina_hits += 1
            return httpx.Response(403, text="Blocked")
        origin_hits += 1
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            text='<html><head><meta property="og:title" content="Origin OG" /><meta property="og:description" content="Saved from prefetched OG" /></head></html>',
        )

    async with _make_mock_transport_client(_html_fallback_handler) as html_client:
        with patch("services.web_search_engine.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
             patch("services.web_search_engine.get_search_client", return_value=html_client):
            fb_res = await web_search_engine.fetch_jina_reader("https://example.com/html-site")

    assert fb_res["status"] == "success"
    assert fb_res["title"] == "Origin OG"
    assert "Saved from prefetched OG" in fb_res["markdown"]
    assert origin_hits == 1
    assert jina_hits == 1


def test_singleflight_cross_event_loop_isolation():
    """FP-113: Separate event loops must not raise 'bound to a different event loop'."""
    web_search_engine.__reset_web_search_cache_for_testing()

    async def _run_once(url: str):
        async def _fake(real_url, **kwargs):
            await asyncio.sleep(0.01)
            return {"status": "success", "url": real_url, "title": "Loop", "markdown": "# Loop\nOK"}

        with patch("services.web_search_engine.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
             patch("services.web_search_engine._fetch_jina_reader_uncached", side_effect=_fake):
            return await web_search_engine.fetch_jina_reader(url)

    loop1 = asyncio.new_event_loop()
    try:
        r1 = loop1.run_until_complete(_run_once("https://example.com/loop-1"))
    finally:
        loop1.close()

    loop2 = asyncio.new_event_loop()
    try:
        r2 = loop2.run_until_complete(_run_once("https://example.com/loop-2"))
    finally:
        loop2.close()

    assert r1["status"] == "success"
    assert r2["status"] == "success"


# ═══════════════════════════════════════════════════════════════════════════════
# AC-5: CJK Punctuation Stripping, Honest Failure Guidance & Search Fallback
# ═══════════════════════════════════════════════════════════════════════════════


def test_url_cleaning_and_searchable_remainder_helpers():
    assert _clean_detected_url("https://www.instagram.com/reel/PRIVATE/！") == "https://www.instagram.com/reel/PRIVATE/"
    assert _clean_detected_url("https://www.instagram.com/reel/PRIVATE/）。") == "https://www.instagram.com/reel/PRIVATE/"
    assert _clean_detected_url("www.tokyo-skytree.jp/hours！") == "https://www.tokyo-skytree.jp/hours"

    u = "https://www.instagram.com/reel/PRIVATE/！"
    assert _has_searchable_text_beyond_urls(f"幫我看 {u}", [u]) is False
    assert _has_searchable_text_beyond_urls(u, [u]) is False
    assert _has_searchable_text_beyond_urls(f"Please check this link {u}", [u]) is False
    assert _has_searchable_text_beyond_urls(f"幫我查大阪燒肉 焼肉エイト {u}", [u]) is True


def _parse_sse(raw_text: str):
    events = []
    ev_name = None
    for line in raw_text.splitlines():
        if line.startswith("event:"):
            ev_name = line[6:].strip()
        elif line.startswith("data:") and ev_name:
            try:
                events.append((ev_name, json.loads(line[5:].strip())))
            except Exception:
                events.append((ev_name, line[5:].strip()))
            ev_name = None
    return events


class _SingleChunkStream:
    def __init__(self, text: str):
        self._text = text

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        chunk = MagicMock(spec=["text", "thought", "candidates"])
        chunk.text = self._text
        chunk.thought = None
        chunk.candidates = []
        yield chunk


def test_stream_chat_strips_cjk_punct_and_injects_bilingual_failure_guidance():
    client = TestClient(app)
    headers = {"X-Gemini-API-Key": "AIzaSy" + "B" * 34}

    # 1. zh-TW: bare/filler message + failed IG URL with trailing "！"
    mock_genai_zh = MagicMock()
    mock_genai_zh.aio.models.generate_content_stream = AsyncMock(
        return_value=_SingleChunkStream("目前無法直接讀取此 Instagram 貼文，歡迎直接上傳截圖或貼上內文！")
    )

    with patch("main.genai.Client", return_value=mock_genai_zh), \
         patch("main.fetch_jina_reader", new_callable=AsyncMock) as mock_reader, \
         patch("main.execute_web_search", new_callable=AsyncMock) as mock_search:
        mock_reader.return_value = {
            "status": "error",
            "error_code": "LOGIN_WALL",
            "message": "登入牆阻擋",
            "markdown": "",
        }
        resp = client.post(
            "/api/chat/stream",
            json={"message": "幫我看 https://www.instagram.com/reel/PRIVATE/！", "history": [], "locale": "zh-TW"},
            headers=headers,
        )

    assert resp.status_code == 200
    # Trailing "！" must be stripped before calling fetch_jina_reader
    mock_reader.assert_awaited_once_with("https://www.instagram.com/reel/PRIVATE/")
    # Filler-only message with failed URL should NOT fire garbage web search
    mock_search.assert_not_awaited()

    stream_contents = mock_genai_zh.aio.models.generate_content_stream.call_args.kwargs["contents"]
    injected_prompt = stream_contents[-1].parts[0].text
    assert "[系統即時解析外部網頁資訊 (來源: https://www.instagram.com/reel/PRIVATE/)]" in injected_prompt
    assert "截圖" in injected_prompt
    assert "文字" in injected_prompt
    # Verify intent_router anti-spoofing boundary recognizes our injected envelope cleanly
    wrapped_for_router = f"{injected_prompt.split('使用者需求：')[0]}使用者需求：<user_input_s1>幫我看</user_input_s1>"
    assert _extract_clean_user_text(wrapped_for_router) == "幫我看"

    events = _parse_sse(resp.text)
    done_ev = [d for ev, d in events if ev == "done"]
    assert len(done_ev) == 1
    assert done_ev[0].get("sources", []) == []

    # 2. English locale + real keywords alongside failed URL -> injects English guidance AND triggers web search backup
    mock_genai_en = MagicMock()
    mock_genai_en.aio.models.generate_content_stream = AsyncMock(
        return_value=_SingleChunkStream("I couldn't open the IG link directly, please paste a screenshot.")
    )

    with patch("main.genai.Client", return_value=mock_genai_en), \
         patch("main.fetch_jina_reader", new_callable=AsyncMock, side_effect=asyncio.TimeoutError()), \
         patch("main.execute_web_search", new_callable=AsyncMock, return_value=[]) as mock_search_en, \
         patch("main.extract_search_queries_with_lite", new_callable=AsyncMock, return_value={"source": "deterministic_fallback"}):
        resp_en = client.post(
            "/api/chat/stream",
            json={
                "message": "Osaka Yakiniku Eight https://www.instagram.com/reel/PRIVATE/!",
                "history": [],
                "locale": "en",
            },
            headers=headers,
        )

    assert resp_en.status_code == 200
    assert mock_search_en.await_count >= 1
    en_prompt = mock_genai_en.aio.models.generate_content_stream.call_args.kwargs["contents"][-1].parts[0].text
    assert "[Live External Webpage Content (Source: https://www.instagram.com/reel/PRIVATE/)]" in en_prompt
    assert "screenshot" in en_prompt.lower()
    assert "TIMEOUT" in en_prompt


# ═══════════════════════════════════════════════════════════════════════════════
# AC-6: link_resolver.fetch_og_metadata Social Login-Wall Filter + Embed Rescue
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_link_resolver_fetch_og_metadata_filters_login_wall_and_rescues_via_embed():
    ig_url = "https://www.instagram.com/reel/DX8x6XOtEqI/"
    seen_ua = []
    login_html = (
        "<html><head><title>登入 • Instagram</title>"
        '<meta property="og:title" content="登入 • Instagram" />'
        '<meta property="og:description" content="歡迎回到 Instagram" />'
        '<meta property="og:image" content="https://static.cdninstagram.com/rsrc.php/login-logo.png" />'
        "</head></html>"
    )

    def _handler(req: httpx.Request) -> httpx.Response:
        seen_ua.append(req.headers.get("user-agent", ""))
        return httpx.Response(200, headers={"Content-Type": "text/html; charset=utf-8"}, text=login_html)

    def _client_factory(**kwargs):
        return _make_mock_transport_client(_handler)

    mock_embed = AsyncMock(return_value={
        "title": "@osaka_foodie: 大阪梅田燒肉 焼肉エイト",
        "username": "osaka_foodie",
        "description": "大阪梅田超值燒肉吃到飽",
        "image": "https://scontent.cdninstagram.com/v/real_cover.jpg",
        "markdown": "# @osaka_foodie",
    })

    with patch("services.link_resolver.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
         patch("services.link_resolver.create_safe_client", side_effect=_client_factory), \
         patch("services.web_search_engine.fetch_instagram_embed", mock_embed):
        meta = await link_resolver.fetch_og_metadata(ig_url)

    assert seen_ua and "facebookexternalhit/1.1" in seen_ua[0]
    assert meta["title"] == "@osaka_foodie: 大阪梅田燒肉 焼肉エイト"
    assert meta["description"] == "大阪梅田超值燒肉吃到飽"
    assert meta["image"] == "https://scontent.cdninstagram.com/v/real_cover.jpg"
    assert meta["site_name"] == "Instagram"

    # When Embed ALSO returns None (private account), polluted "登入 • Instagram" MUST NOT leak
    with patch("services.link_resolver.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
         patch("services.link_resolver.create_safe_client", side_effect=_client_factory), \
         patch("services.web_search_engine.fetch_instagram_embed", AsyncMock(return_value=None)):
        meta_private = await link_resolver.fetch_og_metadata(ig_url)

    assert meta_private["title"] is None
    assert meta_private["description"] is None
    assert meta_private["image"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# AC-7: GAS 404/410 12h Dead Cache & Sanitized Logging (No Full GAS URL Leakage)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_gas_resolve_and_geocode_404_410_dead_cache_and_log_sanitization(monkeypatch, capsys):
    dead_resolve_url = "https://script.google.com/macros/s/AKfycbSECRET_DEAD_SLOT_9991/exec"
    live_resolve_url = "https://script.google.com/macros/s/AKfycbSECRET_LIVE_SLOT_8882/exec"
    monkeypatch.setenv("GAS_RESOLVE_LINK_URLS", f"{dead_resolve_url},{live_resolve_url}")
    monkeypatch.setattr(link_resolver.random, "shuffle", lambda lst: None)

    resolve_hits = {dead_resolve_url: 0, live_resolve_url: 0}

    def _resolve_handler(req: httpx.Request) -> httpx.Response:
        base = f"{req.url.scheme}://{req.url.host}{req.url.path}"
        resolve_hits[base] = resolve_hits.get(base, 0) + 1
        if base == dead_resolve_url:
            return httpx.Response(404, text="Not Found", request=req)
        return httpx.Response(
            200,
            json={"success": True, "lat": 34.7024, "lng": 135.4959, "title": "Osaka Station", "titleReliable": True},
            request=req,
        )

    with patch("services.link_resolver.create_safe_client", side_effect=lambda **kw: _make_mock_transport_client(_resolve_handler)):
        r1 = await link_resolver.resolve_via_gas("https://maps.app.goo.gl/Test1")
        r2 = await link_resolver.resolve_via_gas("https://maps.app.goo.gl/Test2")

    assert r1 is not None and r1["lat"] == pytest.approx(34.7024)
    assert r2 is not None and r2["lat"] == pytest.approx(34.7024)
    assert resolve_hits[dead_resolve_url] == 1  # Banned on first 404, skipped on second call!
    assert resolve_hits[live_resolve_url] == 2
    assert dead_resolve_url in link_resolver._GAS_RESOLVE_DEAD_CACHE

    # Same for geocode_service.geocode_with_gas (testing HTTP 410 Gone)
    geocode_service.__reset_geocode_runtime_state_for_testing()
    dead_geo_url = "https://script.google.com/macros/s/AKfycbSECRET_GEO_DEAD_7773/exec"
    live_geo_url = "https://script.google.com/macros/s/AKfycbSECRET_GEO_LIVE_6664/exec"
    monkeypatch.setenv("GAS_GEOCODE_URLS", f"{dead_geo_url},{live_geo_url}")
    monkeypatch.setattr(geocode_service.random, "shuffle", lambda lst: None)

    geo_hits = {dead_geo_url: 0, live_geo_url: 0}

    def _geo_handler(req: httpx.Request) -> httpx.Response:
        base = f"{req.url.scheme}://{req.url.host}{req.url.path}"
        geo_hits[base] = geo_hits.get(base, 0) + 1
        if base == dead_geo_url:
            return httpx.Response(410, text="Gone", request=req)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "geometry": {"location": {"lat": 35.7100, "lng": 139.8107}},
                        "formatted_address": "Tokyo Skytree, Tokyo, Japan",
                    }
                ]
            },
            request=req,
        )

    real_async_client = httpx.AsyncClient
    with patch(
        "services.geocode_service.httpx.AsyncClient",
        side_effect=lambda **kw: real_async_client(transport=httpx.MockTransport(_geo_handler), follow_redirects=True),
    ):
        g1 = await geocode_service.geocode_with_gas("Tokyo Skytree")
        g2 = await geocode_service.geocode_with_gas("Tokyo Skytree")

    assert g1 is not None and g1["lat"] == pytest.approx(35.7100)
    assert g2 is not None and g2["lat"] == pytest.approx(35.7100)
    assert geo_hits[dead_geo_url] == 1  # Banned on first 410, skipped on second call!
    assert geo_hits[live_geo_url] == 2
    assert dead_geo_url in geocode_service._DEAD_URL_CACHE

    out = capsys.readouterr().out
    # Full GAS URLs & secret deployment prefixes MUST NEVER appear in logs
    assert "AKfycbSECRET_DEAD_SLOT" not in out
    assert "AKfycbSECRET_GEO_DEAD" not in out
    assert "script.google.com/macros/s/" not in out
    assert "***9991" in out
    assert "***7773" in out


# ═══════════════════════════════════════════════════════════════════════════════
# AC-8: Hot Read Routers Offloaded via run_in_threadpool (Zero Event-Loop Freeze)
# ═══════════════════════════════════════════════════════════════════════════════


def _build_slow_supabase_mock(table_payloads, sleep_sec: float = 0.12):
    """Build a mock Supabase client whose .execute() blocks synchronously for sleep_sec."""
    class _SlowQuery:
        def __init__(self, table_name: str):
            self._table = table_name

        def select(self, *args, **kwargs):
            return self

        def eq(self, *args, **kwargs):
            return self

        def in_(self, *args, **kwargs):
            return self

        def order(self, *args, **kwargs):
            return self

        def limit(self, *args, **kwargs):
            return self

        def update(self, *args, **kwargs):
            return self

        def execute(self):
            time.sleep(sleep_sec)
            resp = MagicMock()
            val = table_payloads.get(self._table, [])
            if isinstance(val, Exception):
                raise val
            resp.data = val
            return resp

    supa = MagicMock()
    supa.table.side_effect = lambda name: _SlowQuery(name)
    return supa


async def _assert_non_blocking(coro):
    """Run coro concurrently with a 15ms heartbeat; if event loop freezes, heartbeat ticks == 0."""
    ticks = 0
    done = False

    async def _heartbeat():
        nonlocal ticks
        while not done:
            await asyncio.sleep(0.015)
            ticks += 1

    hb = asyncio.create_task(_heartbeat())
    try:
        result = await coro
    finally:
        done = True
        await hb

    assert ticks >= 3, f"Event loop was blocked by synchronous DB call (only {ticks} heartbeat ticks)"
    return result


@pytest.mark.asyncio
async def test_hot_read_endpoints_do_not_block_event_loop():
    uid = "11111111-1111-4111-8111-111111111111"
    trip_id = "22222222-2222-4222-8222-222222222222"

    # 1. GET /api/trips/share/{public_id}
    supa_pub = _build_slow_supabase_mock({
        "itineraries": [{"id": trip_id, "title": "Osaka", "start_date": "2026-11-01", "public_id": "pub_abcd1234", "content": {}}],
        "itinerary_items": [],
    })
    pub_res = await _assert_non_blocking(
        trips_router.get_public_trip_by_public_id("pub_abcd1234", supabase=supa_pub)
    )
    assert pub_res["id"] == trip_id

    # 2. GET /api/trips
    supa_list = _build_slow_supabase_mock({
        "user_trips_view": [{"id": trip_id, "title": "Osaka", "created_by": uid, "user_id": uid, "content": {}}],
    })
    list_res = await _assert_non_blocking(trips_router.get_trips(user_id=uid, supabase=supa_list))
    assert len(list_res) == 1 and list_res[0]["id"] == trip_id

    # 3. GET /api/trips/{trip_id} (member success + non-member BOLA 403 passthrough)
    supa_detail = _build_slow_supabase_mock({
        "itineraries": [{"id": trip_id, "title": "Osaka", "start_date": "2026-11-01", "public_id": "pub_abcd1234", "created_by": uid, "content": {}}],
        "trip_members": [{"id": "m1", "user_id": uid, "user_name": "Ryan", "user_avatar": None}],
        "itinerary_items": [],
    })
    detail_res = await _assert_non_blocking(
        trips_router.get_trip_by_id(trip_id, user_id=uid, supabase=supa_detail)
    )
    assert detail_res["id"] == trip_id and detail_res["is_owner"] is True

    with pytest.raises(HTTPException) as exc_403:
        await trips_router.get_trip_by_id(trip_id, user_id="99999999-9999-4999-8999-999999999999", supabase=supa_detail)
    assert exc_403.value.status_code == 403

    # 4. GET /api/expenses/{trip_id}/expenses
    supa_exp = _build_slow_supabase_mock({
        "itineraries": [{"id": trip_id, "created_by": uid}],
        "trip_members": [],
        "expenses": [{
            "id": "e1",
            "itinerary_id": trip_id,
            "title": "Ramen",
            "amount": 1200.0,
            "currency": "JPY",
            "is_public": True,
            "created_by": uid,
            "created_at": "2026-11-01T10:00:00Z",
        }],
    })
    exp_res = await _assert_non_blocking(
        expenses_router.get_expenses(trip_id, user_id=uid, supabase=supa_exp)
    )
    assert len(exp_res) == 1 and exp_res[0]["title"] == "Ramen"

    # 5. GET /api/users/{user_id}/profile
    supa_user = _build_slow_supabase_mock({
        "users": [{"id": uid, "name": "Ryan", "avatar_url": None, "email": "r@example.com"}],
    })
    user_res = await _assert_non_blocking(users_router.get_user_profile(uid, supabase=supa_user))
    assert user_res["name"] == "Ryan"


# ═══════════════════════════════════════════════════════════════════════════════
# AC-9: Deprecated ddgs 'google' backend removed
# ═══════════════════════════════════════════════════════════════════════════════


def test_sync_ddgs_call_excludes_deprecated_google_backend():
    mock_ddgs = MagicMock()
    mock_ddgs.text.return_value = []
    mock_ddgs.__enter__.return_value = mock_ddgs
    mock_ddgs.__exit__.return_value = None

    with patch("ddgs.DDGS", return_value=mock_ddgs):
        web_search_engine._sync_ddgs_call("東京晴空塔", "tw-tzh", 3)

    backend_val = mock_ddgs.text.call_args.kwargs.get("backend", "")
    engines = [e.strip() for e in backend_val.split(",") if e.strip()]
    assert engines == ["yahoo", "duckduckgo", "startpage", "brave", "mojeek"]
    assert "google" not in engines


# ═══════════════════════════════════════════════════════════════════════════════
# Adversarial Maker-Checker Hardening Regression Guards
# ═══════════════════════════════════════════════════════════════════════════════


def test_social_media_pattern_blocks_query_and_path_spoofing():
    """SOCIAL_MEDIA_PATTERN must be start-anchored so third-party URLs embedding social links cannot spoof is_social."""
    assert not web_search_engine.SOCIAL_MEDIA_PATTERN.search(
        "https://evil.example/?redirect=https://www.instagram.com/reel/ABC12345/"
    )
    assert not web_search_engine.SOCIAL_MEDIA_PATTERN.search(
        "https://web.archive.org/web/20260101/https://x.com/user/status/123"
    )
    assert web_search_engine.SOCIAL_MEDIA_PATTERN.search("https://www.instagram.com:443/reel/ABC12345/")
    assert web_search_engine.SOCIAL_MEDIA_PATTERN.search("https://www.instagram.com#top")


@pytest.mark.asyncio
async def test_instagram_share_universal_multihop_and_login_next_redirect():
    """/share/{token} (universal), multi-hop relative redirects, and datacenter /accounts/login/?next=... must resolve."""
    assert web_search_engine._is_instagram_share_url("https://www.instagram.com/share/BAc1234567/") is True

    # 1. Datacenter redirect straight to /accounts/login/?next=...
    login_redirect_hits = []

    def _login_next_handler(req: httpx.Request) -> httpx.Response:
        login_redirect_hits.append(req.url.path)
        if req.url.path.startswith("/share/"):
            return httpx.Response(
                302,
                headers={
                    "Location": "https://www.instagram.com/accounts/login/?next=https%3A%2F%2Fwww.instagram.com%2Freel%2FDX8x6XOtEqI%2F"
                },
            )
        return httpx.Response(200, text="<html><title>Login</title></html>")

    async with _make_mock_transport_client(_login_next_handler, follow_redirects=True) as c1:
        with patch("services.web_search_engine.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
             patch("services.web_search_engine.get_search_client", return_value=c1):
            code1 = await web_search_engine._resolve_instagram_share_url("https://www.instagram.com/share/BAc1234567/")

    assert code1 == "DX8x6XOtEqI"
    assert login_redirect_hits == ["/share/BAc1234567/"]  # Stopped immediately on Hop 1 Location without hitting /accounts/login

    # 2. Multi-hop relative redirect -> final reel Location (stops before fetching /reel/)
    multihop_hits = []

    def _multihop_handler(req: httpx.Request) -> httpx.Response:
        multihop_hits.append(req.url.path)
        if req.url.path == "/share/TOK99999/":
            return httpx.Response(302, headers={"Location": "/share/_u/TOK99999/"})
        if req.url.path == "/share/_u/TOK99999/":
            return httpx.Response(302, headers={"Location": "https://www.instagram.com/reel/MultiHop77/"})
        return httpx.Response(200, text="should not be fetched")

    async with _make_mock_transport_client(_multihop_handler, follow_redirects=True) as c2:
        with patch("services.web_search_engine.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
             patch("services.web_search_engine.get_search_client", return_value=c2):
            code2 = await web_search_engine._resolve_instagram_share_url("https://www.instagram.com/share/TOK99999/")

    assert code2 == "MultiHop77"
    assert multihop_hits == ["/share/TOK99999/", "/share/_u/TOK99999/"]


@pytest.mark.asyncio
async def test_instagram_embed_script_hardening_null_double_escape_scheme_and_buried_login_wall():
    """Script extractor handles null-before-real & double-escaped contextJSON; rejects non-HTTP image schemes & buried login walls."""
    from bs4 import BeautifulSoup

    # 1. "shortcode_media": null followed by real object + whitespace around colon
    null_then_real_html = (
        '<html><body><script>var a={"shortcode_media": null, "other": {"x": 1}}; '
        'var b={"shortcode_media" : {"owner":{"username":"namba_food"},'
        '"display_url":"https://scontent.cdninstagram.com/v/ok.jpg",'
        '"edge_media_to_caption":{"edges":[{"node":{"text":"難波燒肉名店"}}]}}};</script></body></html>'
    )
    u, cap, img = web_search_engine._extract_ig_shortcode_media_from_scripts(BeautifulSoup(null_then_real_html, "html.parser"))
    assert u == "namba_food"
    assert cap == "難波燒肉名店"
    assert img == "https://scontent.cdninstagram.com/v/ok.jpg"

    # 2. Double-escaped contextJSON inside ServerJS payload
    inner_gql = json.dumps({
        "gql_data": {
            "shortcode_media": {
                "owner": {"username": "shibuya_coffee"},
                "display_url": "https://scontent.cdninstagram.com/v/coffee.jpg",
                "edge_media_to_caption": {"edges": [{"node": {"text": "渋谷手沖咖啡"}}]},
            }
        }
    })
    outer_ctx = json.dumps({"contextJSON": inner_gql})
    double_escaped_html = f"<html><body><script>ServerJS.handle([{json.dumps(outer_ctx)}]);</script></body></html>"
    u2, cap2, img2 = web_search_engine._extract_ig_shortcode_media_from_scripts(
        BeautifulSoup(double_escaped_html, "html.parser")
    )
    assert u2 == "shibuya_coffee"
    assert cap2 == "渋谷手沖咖啡"
    assert img2 == "https://scontent.cdninstagram.com/v/coffee.jpg"

    # 3. Non-HTTP(S) scheme in script display_url MUST be rejected (sanitized to None)
    bad_scheme_html = (
        '<html><body><script>var d={"shortcode_media":{"owner":{"username":"u"},'
        '"display_url":"ftp://evil.example/pic.jpg",'
        '"edge_media_to_caption":{"edges":[{"node":{"text":"合法內文"}}]}}};</script></body></html>'
    )
    async with _make_mock_transport_client(lambda r: httpx.Response(200, text=bad_scheme_html)) as c3:
        with patch("services.web_search_engine.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
             patch("services.web_search_engine.get_search_client", return_value=c3):
            res3 = await web_search_engine.fetch_instagram_embed("https://www.instagram.com/p/Code12345/")
    assert res3 is not None
    assert res3["image"] is None
    assert "合法內文" in res3["description"]

    # 4. Login wall buried past 600 bytes of <head> markup MUST still be blocked when .Caption is empty
    buried_login_html = (
        "<html><head><title>Instagram Embed</title>"
        f"<style>{'a' * 1500}</style></head>"
        '<body><img class="EmbeddedMediaImage" src="https://static.cdninstagram.com/logo.png"/>'
        "<p>Log in to see photos and videos from friends.</p></body></html>"
    )
    async with _make_mock_transport_client(lambda r: httpx.Response(200, text=buried_login_html)) as c4:
        with patch("services.web_search_engine.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
             patch("services.web_search_engine.get_search_client", return_value=c4):
            res4 = await web_search_engine.fetch_instagram_embed("https://www.instagram.com/p/Code12345/")
    assert res4 is None


@pytest.mark.asyncio
async def test_fetch_opengraph_skips_binary_content_types_without_reading_body():
    """Binary Content-Types (PDF/image) must abort immediately before streaming 2MB into memory."""
    body_read = False

    class _BinaryStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal body_read
            body_read = True
            yield b"%PDF-1.7 binary payload"

    def _pdf_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "application/pdf"}, stream=_BinaryStream())

    async with _make_mock_transport_client(_pdf_handler) as client:
        with patch("services.web_search_engine.get_search_client", return_value=client):
            res = await web_search_engine.fetch_opengraph_metadata("https://example.com/guide.pdf")

    assert res is None
    assert body_read is False


def test_url_detection_preserves_balanced_parens_and_splits_cjk_punctuation():
    """Balanced Wikipedia parens survive, enclosing parens strip cleanly, CJK punctuation terminates URL capture, and multi-word fillers do not trigger search."""
    # Balanced parens preserved; outer enclosing parens stripped
    assert _clean_detected_url("https://en.wikipedia.org/wiki/Tokyo_(disambiguation)") == (
        "https://en.wikipedia.org/wiki/Tokyo_(disambiguation)"
    )
    assert _clean_detected_url("https://en.wikipedia.org/wiki/Tokyo_(disambiguation)).") == (
        "https://en.wikipedia.org/wiki/Tokyo_(disambiguation)"
    )

    # CJK fullwidth punctuation stops URL detection before following Chinese text
    msg_comma = "看這個https://www.instagram.com/reel/DX8x6XOtEqI/，好想去"
    detected_comma = [main_module._clean_detected_url(u) for u in main_module._URL_DETECT_RE.findall(msg_comma)]
    assert detected_comma == ["https://www.instagram.com/reel/DX8x6XOtEqI/"]

    msg_paren = "https://www.tokyo-skytree.jp/（晴空塔官網）"
    detected_paren = [main_module._clean_detected_url(u) for u in main_module._URL_DETECT_RE.findall(msg_paren)]
    assert detected_paren == ["https://www.tokyo-skytree.jp/"]

    # Multi-word conversational fillers must NOT trigger irrelevant web search
    u = "https://www.instagram.com/reel/PRIVATE/"
    for filler_msg in (
        f"請幫我看這篇貼文 {u}",
        f"幫我看這個連結 {u}",
        f"可以幫我看一下嗎 {u}",
        f"這是什麼 {u}",
        f"Can you check this link {u}",
        f"What is this {u}",
    ):
        assert _has_searchable_text_beyond_urls(filler_msg, [u]) is False, f"Should be filler: {filler_msg}"

    assert _has_searchable_text_beyond_urls(f"請問大阪梅田燒肉開到幾點 {u}", [u]) is True


def test_stream_chat_mixed_dual_url_one_success_one_failure_and_sanitized_error_log(capsys):
    """When 1 URL succeeds and 1 URL fails with query token exception, sources keep only succeeded URL, prompt has both, and secret token never leaks to stdout."""
    client = TestClient(app)
    headers = {"X-Gemini-API-Key": "AIzaSy" + "C" * 34}
    ok_url = "https://www.tokyo-skytree.jp/"
    fail_url = "https://www.instagram.com/reel/FAIL123/?stkn=TOPSECRET_QUERY_TOKEN"

    async def _fake_reader(url: str):
        if url == ok_url:
            return {
                "status": "success",
                "url": ok_url,
                "title": "Tokyo Skytree",
                "markdown": "# Tokyo Skytree\nOpen 10:00 - 21:00",
            }
        raise RuntimeError(f"upstream failed for {fail_url}")

    mock_genai = MagicMock()
    mock_genai.aio.models.generate_content_stream = AsyncMock(
        return_value=_SingleChunkStream("晴空塔營業時間為 10:00-21:00；另 IG 連結無法直接讀取，歡迎提供截圖。")
    )

    with patch("main.genai.Client", return_value=mock_genai), \
         patch("main.fetch_jina_reader", side_effect=_fake_reader), \
         patch("main.execute_web_search", new_callable=AsyncMock) as mock_search:
        resp = client.post(
            "/api/chat/stream",
            json={"message": f"幫我看 {ok_url} 跟 {fail_url}！", "history": [], "locale": "zh-TW"},
            headers=headers,
        )

    assert resp.status_code == 200
    mock_search.assert_not_awaited()
    injected = mock_genai.aio.models.generate_content_stream.call_args.kwargs["contents"][-1].parts[0].text
    assert "Tokyo Skytree" in injected
    assert "無法讀取該連結" in injected
    events = _parse_sse(resp.text)
    done_ev = [d for ev, d in events if ev == "done"]
    assert len(done_ev) == 1
    assert [s["uri"] for s in done_ev[0].get("sources", [])] == [ok_url]

    out = capsys.readouterr().out
    assert "TOPSECRET_QUERY_TOKEN" not in out


@pytest.mark.asyncio
async def test_link_resolver_ssrf_error_aborts_without_ig_embed_rescue():
    """SSRFSecurityError during redirect must abort fetch_og_metadata immediately without calling fetch_instagram_embed."""
    embed_mock = AsyncMock(return_value={"title": "should not run", "image": "https://img", "description": "d"})

    class _SsrfFailClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def stream(self, *args, **kwargs):
            raise SSRFSecurityError("blocked intranet redirect")

    with patch("services.link_resolver.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
         patch("services.link_resolver.create_safe_client", return_value=_SsrfFailClient()), \
         patch("services.web_search_engine.fetch_instagram_embed", embed_mock):
        meta = await link_resolver.fetch_og_metadata("https://www.instagram.com/reel/DX8x6XOtEqI/")

    assert embed_mock.await_count == 0
    assert meta["title"] is None
    assert meta["image"] is None
