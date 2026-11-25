"""
Security Sentinel In-Memory PoC & Regression Suite — Revised 9/10 Plan B + Vercel-Grade CSP
===========================================================================================
Covers Mantis Block G Benign Controls (test_benign_*) and Red->Green Exploit PoCs (test_sentinel_poc_*):
1. Step 1: Linear-time ReDoS immunity (_PAREN_REMARK_RE, _STATION_STRIP_RE, clean_conversational_query)
           + Pydantic max_length bounds (GeocodeSearchRequest <= 4096, ChatRequest <= 50000)
           + smart_geocode_logic [:500] entry truncation.
2. Step 2: Removal of 410 Gone ArcGIS static-map token leak in link_resolver.py (preserving geocode_service.py)
           + httpx / httpx2 logger WARNING level suppression in main.py.
3. Step 3: Dedicated 4-thread DNS bulkhead & is_safe_url_async timeout isolation (url_safety.py),
           bounded streaming in fetch_og_metadata / fetch_opengraph_metadata / safe_download_image /
           smart_redirect_tracer / poi_resolve_link, strict shortlink hostname validation,
           iOS share string GAS Rescue ordering, SlowAPI signature on /api/poi/resolve-link.
4. Step 4: Hardened /api/poi/media-proxy (strict upload.wikimedia.org host, SVG/SVGZ 415,
           PNG-thumb-of-SVG allowed, 10 MB Content-Length 413 & chunked cap, 400/502/504 mapping,
           guaranteed aclose(), SlowAPI rate limiting, Vercel-grade sandbox CSP preserved by
           main.py middleware setdefault).
"""

import asyncio
import inspect
import logging
import socket
import time
from typing import Any, Callable, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from models.base import ChatRequest, GeocodeSearchRequest
from services import destination_taxonomy, geocode_service, link_resolver, web_search_engine
from utils import url_safety
from utils.limiter import limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter_state():
    """Keep SlowAPI enabled so signature/limit bugs are surfaced, while resetting storage per test."""
    prev_enabled = limiter.enabled
    limiter.enabled = True
    try:
        if hasattr(limiter, "_storage") and hasattr(limiter._storage, "reset"):
            limiter._storage.reset()
        yield
    finally:
        if hasattr(limiter, "_storage") and hasattr(limiter._storage, "reset"):
            limiter._storage.reset()
        limiter.enabled = prev_enabled


def _make_transport_client_factory(handler: Callable[[httpx.Request], httpx.Response], record_aclose: Optional[List[bool]] = None):
    """Build a real httpx.AsyncClient factory backed by MockTransport (preserves real streaming & ResponseNotRead)."""
    real_async_client = httpx.AsyncClient

    class _TrackedAsyncClient(real_async_client):
        async def aclose(self) -> None:
            if record_aclose is not None:
                record_aclose.append(True)
            await super().aclose()

    def _factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return _TrackedAsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return _factory


# ============================================================================
# Mantis Block G: Benign Control Tests (Must pass BEFORE and AFTER patch)
# ============================================================================


def test_benign_geocode_and_chat_normal_lengths_and_text_helpers():
    """Normal queries (including 2,400-char legacy adversarial test) and normal text cleaning must stay intact."""
    req_geo = GeocodeSearchRequest(query="ramen " * 400, limit=10)
    assert len(req_geo.query) == 2400

    req_chat = ChatRequest(message="幫我安排東京三天兩夜美食行程")
    assert "東京" in req_chat.message

    assert geocode_service._extract_clean_place_query("淺草寺 (雷門拍照)") == "淺草寺"
    assert geocode_service._extract_clean_place_query("10:00 築地市場（海鮮早餐）") == "築地市場"

    candidates = [
        {"name": "Tokyo Station", "lat": 35.6812, "lng": 139.7671, "type": "station", "osm_key": "railway"},
        {"name": "Tokyo", "lat": 35.6762, "lng": 139.6503, "type": "city", "osm_key": "place"},
    ]
    ranked = geocode_service.rerank_top_k(candidates, "Tokyo   Central   Station", limit=5)
    assert len(ranked) == 2

    cleaned_q = destination_taxonomy.clean_conversational_query("請問東京推薦拉麵嗎？")
    assert "東京" in cleaned_q
    assert not cleaned_q.endswith("嗎")
    assert not cleaned_q.endswith("？")


def test_benign_geocode_service_preserves_arcgis_server_fallback():
    """Removing client-side ArcGIS static map URL must NOT remove server-side geocode_service ARCGIS_API_KEY."""
    assert hasattr(geocode_service, "ARCGIS_API_KEY")
    src = inspect.getsource(geocode_service)
    assert "ARCGIS_API_KEY" in src


def test_benign_url_safety_basic_allow_and_block():
    """Core url_safety allow/block behavior remains intact."""
    assert url_safety.is_safe_url("https://en.wikipedia.org/wiki/Tokyo") is True
    assert url_safety.is_safe_url("http://127.0.0.1/secret") is False
    assert url_safety.is_safe_url("http://169.254.169.254/latest/meta-data/") is False


def test_benign_media_proxy_valid_wikimedia_png_and_svg_png_thumbnail():
    """Valid Wikimedia PNG and PNG-rendered thumbnail of an SVG must stream 200 cleanly."""
    from main import app

    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

    def _handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "image/png", "Content-Length": str(len(png_bytes))}, content=png_bytes)

    factory = _make_transport_client_factory(_handler)
    thumb_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Flag.svg/320px-Flag.svg.png"

    with patch("routers.poi.httpx.AsyncClient", side_effect=factory), \
         patch("utils.url_safety.httpx.AsyncClient", side_effect=factory):
        client = TestClient(app)
        resp = client.get("/api/poi/media-proxy", params={"url": thumb_url})

    assert resp.status_code == 200
    assert resp.content == png_bytes
    assert resp.headers["content-type"].startswith("image/png")


# ============================================================================
# Step 1 PoCs: Linear-time ReDoS Immunity & Input Length Bounds
# ============================================================================


def test_sentinel_poc_model_input_length_bounds():
    """Step 1: GeocodeSearchRequest.query <= 4096 and ChatRequest.message <= 50000."""
    # Exact boundary must pass
    assert len(GeocodeSearchRequest(query="a" * 4096).query) == 4096
    assert len(ChatRequest(message="a" * 50000).message) == 50000

    # Over-limit must fail Pydantic validation
    with pytest.raises(ValidationError):
        GeocodeSearchRequest(query="a" * 4097)

    with pytest.raises(ValidationError):
        ChatRequest(message="a" * 50001)


@pytest.mark.asyncio
async def test_sentinel_poc_smart_geocode_logic_truncates_direct_query():
    """Step 1: smart_geocode_logic slices clean_query to [:500] at entry."""
    captured_queries: List[str] = []

    class _StopAfterCapture(Exception):
        pass

    def _spy_anchor(q: str):
        captured_queries.append(q)
        raise _StopAfterCapture()

    with patch.object(geocode_service, "_detect_explicit_city_anchor", side_effect=_spy_anchor):
        with pytest.raises(_StopAfterCapture):
            await geocode_service.smart_geocode_logic("Tokyo " * 300, allow_overpass=False)

    assert captured_queries, "Expected smart_geocode_logic to invoke _detect_explicit_city_anchor"
    assert len(captured_queries[0]) <= 500


def test_sentinel_poc_redos_linear_time_bounds():
    """Step 1: All three backend regex hotspots must execute in strictly linear time (< 50ms on 60k adversarial inputs)."""
    # 1. _PAREN_REMARK_RE (leading \s* caused quadratic backtracking on long internal whitespace without paren)
    payload_paren = "A" + " " * 60000 + "X"
    t0 = time.perf_counter()
    assert geocode_service._extract_clean_place_query(payload_paren) == "A X"
    dt_paren = time.perf_counter() - t0
    assert dt_paren < 0.05, f"_PAREN_REMARK_RE quadratic ReDoS detected: {dt_paren:.4f}s"
    assert not geocode_service._PAREN_REMARK_RE.pattern.startswith(r"\s*")

    # 2. _STATION_STRIP_RE (\s+ before alternation anchored at $ caused quadratic backtracking)
    payload_station = " " * 60000 + "central" + " " * 100 + "X"
    t1 = time.perf_counter()
    geocode_service._STATION_STRIP_RE.sub("", payload_station)
    dt_station = time.perf_counter() - t1
    assert dt_station < 0.05, f"_STATION_STRIP_RE quadratic ReDoS detected: {dt_station:.4f}s"
    assert r"\s+" not in geocode_service._STATION_STRIP_RE.pattern

    # 3. clean_conversational_query (trailing [...]+$ caused quadratic backtracking on repeated punctuation)
    payload_conv = "?" * 60000 + "X"
    t2 = time.perf_counter()
    destination_taxonomy.clean_conversational_query(payload_conv)
    dt_conv = time.perf_counter() - t2
    assert dt_conv < 0.05, f"clean_conversational_query quadratic ReDoS detected: {dt_conv:.4f}s"

    payload_conv2 = "嗎" * 60000 + "X"
    t3 = time.perf_counter()
    destination_taxonomy.clean_conversational_query(payload_conv2)
    dt_conv2 = time.perf_counter() - t3
    assert dt_conv2 < 0.05, f"clean_conversational_query (CJK) quadratic ReDoS detected: {dt_conv2:.4f}s"


# ============================================================================
# Step 2 PoCs: ArcGIS Static-Map Leak Removal & HTTP Client Log Suppression
# ============================================================================


@pytest.mark.asyncio
async def test_sentinel_poc_arcgis_static_map_token_leak_removed(monkeypatch):
    """Step 2: link_resolver must never generate dead static-maps-api.arcgis.com URLs containing ARCGIS_API_KEY."""
    monkeypatch.setenv("ARCGIS_API_KEY", "SUPER_SECRET_ARCGIS_TOKEN_XYZ")

    with patch.object(link_resolver, "fetch_og_metadata", new_callable=AsyncMock, return_value={"title": "Tokyo Tower", "image": None, "description": None, "site_name": None}), \
         patch("services.geocode_service.reverse_geocode_with_photon", new_callable=AsyncMock, return_value=None):
        res = await link_resolver.resolve_google_maps_link(
            "https://www.google.com/maps/place/Tokyo+Tower/@35.6585805,139.7454329,17z"
        )

    img = res.get("metadata", {}).get("image") or ""
    assert "static-maps-api.arcgis.com" not in img
    assert "SUPER_SECRET_ARCGIS_TOKEN_XYZ" not in img


def test_sentinel_poc_httpx_and_httpx2_loggers_suppressed_to_warning():
    """Step 2: main.py must silence httpx and httpx2 INFO request logs that can leak query tokens."""
    import main  # noqa: F401

    assert logging.getLogger("httpx").level >= logging.WARNING
    assert logging.getLogger("httpx2").level >= logging.WARNING


# ============================================================================
# Step 3 PoCs: DNS Bulkhead, Bounded Streaming, Shortlink Hostname, ai.py, poi.py
# ============================================================================


@pytest.mark.asyncio
async def test_sentinel_poc_dns_bulkhead_isolation_and_timeout():
    """Step 3A: is_safe_url_async runs in dedicated 4-thread bulkhead, times out cleanly, and doesn't block event loop."""
    assert hasattr(url_safety, "_DNS_SAFETY_EXECUTOR")
    assert hasattr(url_safety, "is_safe_url_async")
    assert getattr(url_safety._DNS_SAFETY_EXECUTOR, "_max_workers", None) == 4

    def _stalling_getaddrinfo(*args, **kwargs):
        time.sleep(0.8)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    loop_ticks = 0

    async def _ticker():
        nonlocal loop_ticks
        for _ in range(5):
            await asyncio.sleep(0.02)
            loop_ticks += 1

    with patch("utils.url_safety.socket.getaddrinfo", side_effect=_stalling_getaddrinfo):
        t0 = time.perf_counter()
        safe_res, _ = await asyncio.gather(
            url_safety.is_safe_url_async("https://slow-dns.example.invalid/test", timeout=0.15),
            _ticker(),
        )
        elapsed = time.perf_counter() - t0

    assert safe_res is False, "Timed-out DNS check must fail closed (False)"
    assert elapsed < 0.55, f"DNS bulkhead failed to enforce timeout promptly: {elapsed:.3f}s"
    assert loop_ticks == 5, "Event loop must stay responsive during stalling DNS resolution"


@pytest.mark.asyncio
async def test_sentinel_poc_shortlink_strict_hostname_and_ios_share_gas_rescue():
    """Step 3C: Strict _is_google_shortlink rejects spoofed hosts while iOS share strings preserve GAS Rescue."""
    assert hasattr(link_resolver, "_is_google_shortlink")
    assert link_resolver._is_google_shortlink("https://maps.app.goo.gl/Test123") is True
    assert link_resolver._is_google_shortlink("https://goo.gl/maps/Test123") is True
    assert link_resolver._is_google_shortlink("https://www.goo.gl/maps/Test123") is True
    assert link_resolver._is_google_shortlink("https://evil.com/?r=maps.app.goo.gl") is False
    assert link_resolver._is_google_shortlink("https://maps.app.goo.gl.evil.com/abc") is False
    assert link_resolver._is_google_shortlink("javascript://maps.app.goo.gl/%0aalert(1)") is False

    # 1. Spoofed host must NOT trigger SmartTracer or GAS Rescue
    mock_tracer = MagicMock()
    mock_tracer.trace_full_chain_smart = AsyncMock(return_value={"final_url": "https://evil.com/?r=maps.app.goo.gl"})
    mock_gas = AsyncMock(return_value=None)

    with patch.object(link_resolver, "get_smart_tracer", return_value=mock_tracer), \
         patch.object(link_resolver, "resolve_via_gas", mock_gas), \
         patch.object(link_resolver, "fetch_og_metadata", new_callable=AsyncMock, return_value={"title": None, "image": None, "description": None, "site_name": None}):
        await link_resolver.resolve_google_maps_link("https://evil.com/?r=maps.app.goo.gl")

    mock_tracer.trace_full_chain_smart.assert_not_awaited()
    mock_gas.assert_not_awaited()

    # 2. iOS share string with surrounding text & trailing punctuation MUST extract clean URL BEFORE assigning original_input_url
    #    so GAS Rescue still receives the clean shortlink with g_st=ic when local tracer finds no coords!
    ios_share = "老新台菜\nhttps://maps.app.goo.gl/TestIOS123?g_st=ic。"
    mock_tracer2 = MagicMock()
    mock_tracer2.trace_full_chain_smart = AsyncMock(return_value={"final_url": "https://maps.app.goo.gl/TestIOS123"})
    mock_gas2 = AsyncMock(return_value={
        "lat": 22.6429,
        "lng": 120.2971,
        "title": "老新台菜",
        "titleReliable": True,
        "longUrl": "https://www.google.com/maps/place/LaoXin/@22.6429,120.2971,17z",
        "method": "gas_rescue",
    })

    with patch.object(link_resolver, "get_smart_tracer", return_value=mock_tracer2), \
         patch.object(link_resolver, "resolve_via_gas", mock_gas2), \
         patch.object(link_resolver, "is_safe_url_async", new_callable=AsyncMock, return_value=True), \
         patch.object(link_resolver, "fetch_og_metadata", new_callable=AsyncMock, return_value={"title": "老新台菜", "image": None, "description": None, "site_name": None}), \
         patch("services.geocode_service.reverse_geocode_with_photon", new_callable=AsyncMock, return_value=None):
        res = await link_resolver.resolve_google_maps_link(ios_share)

    # SmartTracer gets g_st-stripped clean URL
    mock_tracer2.trace_full_chain_smart.assert_awaited_once_with("https://maps.app.goo.gl/TestIOS123")
    # GAS Rescue gets clean original URL (with g_st=ic preserved, no Japanese/CJK prefix, no trailing '。')
    mock_gas2.assert_awaited_once_with("https://maps.app.goo.gl/TestIOS123?g_st=ic")
    assert res["lat"] == pytest.approx(22.6429, abs=1e-4)


@pytest.mark.asyncio
async def test_sentinel_poc_bounded_html_streaming_and_no_response_not_read():
    """Step 3C & 3D: _read_bounded_text enforces 2MB cap + invalid charset fallback; fetch_og_metadata & fetch_opengraph_metadata stream safely without ResponseNotRead."""
    assert hasattr(link_resolver, "_read_bounded_text")

    # 1. 5MB chunked stream with invalid charset must stop at <= 2MB and decode without LookupError
    chunks_yielded = 0

    class _GiantStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal chunks_yielded
            for _ in range(80):  # 80 * 64KB = 5MB
                chunks_yielded += 1
                yield b"A" * 65536

    def _giant_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=bogus-invalid-encoding"},
            stream=_GiantStream(),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(_giant_handler)) as client:
        async with client.stream("GET", "https://example.com/huge") as resp:
            text = await link_resolver._read_bounded_text(resp, max_bytes=2 * 1024 * 1024)

    assert len(text) == 2 * 1024 * 1024
    assert chunks_yielded <= 33, f"Stream was not cut off early at 2MB: yielded {chunks_yielded} chunks"

    # 2. fetch_og_metadata on Google Maps HTML (triggers Deep Scraper path) must NOT hit httpx.ResponseNotRead
    gmaps_html = (
        '<html><head><meta property="og:title" content="Test Place" /></head>'
        '<body><script>var img = "https://lh3.googleusercontent.com/p/AF1QipTestPhoto123=w400-h300";</script></body></html>'
    ).encode("utf-8")

    class _OneShotStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield gmaps_html

    def _gmaps_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "text/html; charset=utf-8"}, stream=_OneShotStream())

    factory = _make_transport_client_factory(_gmaps_handler)
    with patch("utils.url_safety.is_safe_url", return_value=True), \
         patch("utils.url_safety.httpx.AsyncClient", side_effect=factory):
        meta = await link_resolver.fetch_og_metadata("https://www.google.com/maps/place/Test")

    assert meta["title"] == "Test Place"
    assert meta["image"] == "https://lh3.googleusercontent.com/p/AF1QipTestPhoto123=w1000-h800-k-no"

    # 3. fetch_opengraph_metadata in web_search_engine must cap streamed body at <= 2MB
    og_chunks = 0

    class _OgHugeStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal og_chunks
            og_chunks += 1
            yield b'<html><head><meta property="og:title" content="Bounded Title" /></head><body>'
            for _ in range(80):
                og_chunks += 1
                yield b"B" * 65536

    def _og_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "text/html; charset=utf-8"}, stream=_OgHugeStream())

    async with httpx.AsyncClient(transport=httpx.MockTransport(_og_handler)) as og_client:
        with patch.object(web_search_engine, "get_search_client", return_value=og_client):
            og_res = await web_search_engine.fetch_opengraph_metadata("https://example.com/post")

    assert og_res is not None
    assert og_res["title"] == "Bounded Title"
    assert og_chunks <= 35, f"fetch_opengraph_metadata did not bound stream to 2MB: yielded {og_chunks} chunks"


@pytest.mark.asyncio
async def test_sentinel_poc_safe_download_image_hardening():
    """Step 3B: safe_download_image rejects localhost/127.0.0.1, enforces 20MB streaming cap, strips charset, preserves HTTPException/SSRFSecurityError."""
    from routers import ai as ai_router

    # 1. Localhost / 127.0.0.1 bypass MUST be removed (HTTP 400)
    for forbidden in ("http://localhost/secret.png", "http://127.0.0.1/secret.png", "http://127.0.0.1:8008/health"):
        with pytest.raises(HTTPException) as exc_info:
            await ai_router.safe_download_image(forbidden)
        assert exc_info.value.status_code == 400

    # 2. Valid image with '; charset=binary' normalizes Content-Type cleanly
    def _ok_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "image/jpeg; charset=binary"},
            content=b"\xff\xd8\xff\xe0" + b"\x00" * 32,
        )

    with patch("routers.ai.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
         patch("utils.url_safety.is_safe_url", return_value=True), \
         patch("utils.url_safety.httpx.AsyncClient", side_effect=_make_transport_client_factory(_ok_handler)):
        data, ct = await ai_router.safe_download_image("https://cdn.example.com/receipt.jpg")
    assert ct == "image/jpeg"
    assert data.startswith(b"\xff\xd8\xff\xe0")

    # 3. Streaming > 20MB without Content-Length stops early and raises clean HTTP 400 (not wrapped as "Failed to fetch image: 400: ...")
    chunks_sent = 0

    class _Over20MBStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal chunks_sent
            for _ in range(40):  # 40 * 1MB = 40MB
                chunks_sent += 1
                yield b"\x00" * (1024 * 1024)

    def _huge_img_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "image/png"}, stream=_Over20MBStream())

    with patch("routers.ai.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
         patch("utils.url_safety.is_safe_url", return_value=True), \
         patch("utils.url_safety.httpx.AsyncClient", side_effect=_make_transport_client_factory(_huge_img_handler)):
        with pytest.raises(HTTPException) as exc_big:
            await ai_router.safe_download_image("https://cdn.example.com/huge.png")

    assert exc_big.value.status_code == 400
    assert "Image too large" in exc_big.value.detail
    assert not exc_big.value.detail.startswith("Failed to fetch image:")
    assert chunks_sent <= 22, f"safe_download_image buffered too many chunks: {chunks_sent}"

    # 4. SSRFSecurityError raised inside transport hook maps cleanly to HTTP 400
    with patch("routers.ai.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
         patch("utils.url_safety.is_safe_url", return_value=False):
        with pytest.raises(HTTPException) as exc_ssrf:
            await ai_router.safe_download_image("https://rebinding.example.com/img.png")
    assert exc_ssrf.value.status_code == 400
    assert "Forbidden" in exc_ssrf.value.detail


def test_sentinel_poc_poi_resolve_link_slowapi_signature_and_stream():
    """Step 3E: /api/poi/resolve-link enforces SlowAPI rate-limiting with valid (request: Request, body: PoiResolveLinkRequest) signature & streams redirects."""
    from main import app
    from routers import poi as poi_router

    sig = inspect.signature(poi_router.poi_resolve_link)
    params = list(sig.parameters.keys())
    assert params[:2] == ["request", "body"], f"SlowAPI requires (request: Request, body: ...), got {params}"

    client = TestClient(app)

    # 1. SSRF URL blocked with 400
    r_ssrf = client.post("/api/poi/resolve-link", json={"url": "http://127.0.0.1:8008/api/trips"})
    assert r_ssrf.status_code == 400

    # 2. Valid shortlink traces via stream without buffering body and routes cleanly
    stream_used = False
    body_read_chunks = 0

    class _RedirectBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal body_read_chunks
            body_read_chunks += 1
            yield b"HUGE_BODY_SHOULD_NOT_BE_READ" * 1000

    def _shortlink_handler(req: httpx.Request) -> httpx.Response:
        nonlocal stream_used
        stream_used = True
        return httpx.Response(200, stream=_RedirectBody())

    with patch("routers.poi.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
         patch("utils.url_safety.is_safe_url", return_value=True), \
         patch("utils.url_safety.httpx.AsyncClient", side_effect=_make_transport_client_factory(_shortlink_handler)), \
         patch("routers.poi.resolve_google_maps_link", new_callable=AsyncMock, return_value={
             "lat": 35.6585,
             "lng": 139.7454,
             "address": "Tokyo",
             "query": "Tokyo Tower",
             "metadata": {"title": "Tokyo Tower", "image": None},
         }):
        r_ok = client.post("/api/poi/resolve-link", json={"url": "https://maps.app.goo.gl/TestShort1"})

    assert r_ok.status_code == 200
    assert r_ok.json()["success"] is True
    assert stream_used is True
    assert body_read_chunks == 0, "Shortlink redirect trace must NOT buffer response body!"


# ============================================================================
# Step 4 PoCs: /api/poi/media-proxy Hardening & Middleware CSP Preservation
# ============================================================================


def test_sentinel_poc_media_proxy_hardening_and_vercel_csp():
    """Step 4: media-proxy validates host, rejects SVG/SVGZ (415), caps 10MB (413 + chunk cap), maps 502/504, closes clients, and preserves Vercel-grade CSP through middleware."""
    from main import app
    from routers import poi as poi_router

    sig = inspect.signature(poi_router.media_proxy)
    assert "request" in sig.parameters, "media_proxy must accept request: Request for SlowAPI"

    client = TestClient(app)

    # 1. Hostname spoofing / downgrade / userinfo -> 400
    for bad_url in (
        "https://upload.wikimedia.org.evil.com/a.jpg",
        "https://upload.wikimedia.org@evil.com/a.jpg",
        "http://upload.wikimedia.org/wikipedia/commons/a.jpg",
        "https://upload.wikimedia.org:8443/wikipedia/commons/a.jpg",
    ):
        r = client.get("/api/poi/media-proxy", params={"url": bad_url})
        assert r.status_code == 400, f"Expected 400 for {bad_url}, got {r.status_code}"

    # 2. SVG / SVGZ paths rejected BEFORE upstream fetch -> 415
    for svg_url in (
        "https://upload.wikimedia.org/wikipedia/commons/a/ab/Xss.svg",
        "https://upload.wikimedia.org/wikipedia/commons/a/ab/Xss.SVG?download=1",
        "https://upload.wikimedia.org/wikipedia/commons/a/ab/Xss.svgz",
    ):
        r = client.get("/api/poi/media-proxy", params={"url": svg_url})
        assert r.status_code == 415, f"Expected 415 for {svg_url}, got {r.status_code}"

    # 3. Valid PNG preserves Vercel-grade CSP (NOT overwritten by main.py middleware!) and closes client
    closed_ok: List[bool] = []
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x01" * 32

    def _ok_png(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "image/png", "Content-Length": str(len(png_bytes))}, content=png_bytes)

    with patch("utils.url_safety.httpx.AsyncClient", side_effect=_make_transport_client_factory(_ok_png, closed_ok)):
        r_ok = client.get(
            "/api/poi/media-proxy",
            params={"url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Valid.png"},
        )
    assert r_ok.status_code == 200
    assert r_ok.headers["content-security-policy"] == "script-src 'none'; frame-src 'none'; sandbox;"
    assert r_ok.headers["x-content-type-options"] == "nosniff"
    assert len(closed_ok) >= 1, "media_proxy must always close httpx.AsyncClient"

    # Global default CSP must STILL apply to normal endpoints via setdefault
    r_health = client.get("/health")
    assert r_health.status_code == 200
    assert "default-src 'self'" in r_health.headers.get("content-security-policy", "")

    # 4. Upstream returns image/svg+xml on .png URL -> 415 + aclose()
    closed_svg: List[bool] = []

    def _svg_ct(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "image/svg+xml"}, content=b"<svg/>")

    with patch("utils.url_safety.httpx.AsyncClient", side_effect=_make_transport_client_factory(_svg_ct, closed_svg)):
        r_svg = client.get(
            "/api/poi/media-proxy",
            params={"url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Fake.png"},
        )
    assert r_svg.status_code == 415
    assert len(closed_svg) >= 1

    # 5. Upstream Content-Length > 10MB -> 413 + aclose()
    closed_413: List[bool] = []

    def _cl_over(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "image/jpeg", "Content-Length": str(10 * 1024 * 1024 + 1)},
            content=b"\xff\xd8",
        )

    with patch("utils.url_safety.httpx.AsyncClient", side_effect=_make_transport_client_factory(_cl_over, closed_413)):
        r_413 = client.get(
            "/api/poi/media-proxy",
            params={"url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Huge.jpg"},
        )
    assert r_413.status_code == 413
    assert len(closed_413) >= 1

    # 6. Chunked > 10MB without Content-Length is capped at <= 10MB + aclose()
    closed_chunk: List[bool] = []

    class _Over10MBStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(15):  # 15MB
                yield b"\x00" * (1024 * 1024)

    def _chunk_over(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "image/jpeg"}, stream=_Over10MBStream())

    with patch("utils.url_safety.httpx.AsyncClient", side_effect=_make_transport_client_factory(_chunk_over, closed_chunk)):
        r_chunk = client.get(
            "/api/poi/media-proxy",
            params={"url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/ChunkedHuge.jpg"},
        )
    assert r_chunk.status_code == 200
    assert len(r_chunk.content) <= 10 * 1024 * 1024
    assert len(closed_chunk) >= 1

    # 7. Upstream non-200 -> 502 + aclose(), Timeout -> 504 + aclose()
    closed_502: List[bool] = []

    def _upstream_404(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"Not Found")

    with patch("utils.url_safety.httpx.AsyncClient", side_effect=_make_transport_client_factory(_upstream_404, closed_502)):
        r_502 = client.get(
            "/api/poi/media-proxy",
            params={"url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Missing.jpg"},
        )
    assert r_502.status_code == 502
    assert len(closed_502) >= 1

    closed_504: List[bool] = []

    def _upstream_timeout(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("upstream stalled")

    with patch("utils.url_safety.httpx.AsyncClient", side_effect=_make_transport_client_factory(_upstream_timeout, closed_504)):
        r_504 = client.get(
            "/api/poi/media-proxy",
            params={"url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Slow.jpg"},
        )
    assert r_504.status_code == 504
    assert len(closed_504) >= 1


# ============================================================================
# Round 2 Adversarial Review PoCs (6 Confirmed Edge-Case Bugs + SlowAPI 429)
# ============================================================================


def test_sentinel_poc_r2_media_proxy_malformed_url_encoded_svg_and_xsvg():
    """R2 Bug #1 & #2: Malformed ports/IPv6/control chars return 400 (never 500/502); encoded .svg/.svgz rejected pre-flight 415; image/x-svg+xml rejected 415."""
    from main import app

    client = TestClient(app, raise_server_exceptions=False)

    # 1. Malformed URLs (invalid port, out-of-range port, malformed IPv6, CRLF control chars) -> 400
    for bad_url in (
        "https://upload.wikimedia.org:abc/a.png",
        "https://upload.wikimedia.org:99999/a.png",
        "https://[invalid/a.png",
        "https://upload.wikimedia.org/wikipedia/commons/a.png\r\nX-Inject: 1",
    ):
        r = client.get("/api/poi/media-proxy", params={"url": bad_url})
        assert r.status_code == 400, f"Expected 400 for {bad_url!r}, got {r.status_code}"

    # 2. Percent-encoded .svg / .svgz / trailing slash MUST be blocked pre-flight (415, ZERO upstream hits)
    upstream_hits: List[str] = []

    def _xsvg_handler(req: httpx.Request) -> httpx.Response:
        upstream_hits.append(str(req.url))
        return httpx.Response(200, headers={"Content-Type": "image/x-svg+xml"}, content=b"<svg/>")

    with patch("utils.url_safety.httpx.AsyncClient", side_effect=_make_transport_client_factory(_xsvg_handler)):
        for enc_svg in (
            "https://upload.wikimedia.org/wikipedia/commons/a/ab/Xss.%73vg",
            "https://upload.wikimedia.org/wikipedia/commons/a/ab/Xss%2esvg",
            "https://upload.wikimedia.org/wikipedia/commons/a/ab/Xss%252esvg",
            "https://upload.wikimedia.org/wikipedia/commons/a/ab/Xss.svg/",
            "https://upload.wikimedia.org/wikipedia/commons/a/ab/Xss.%73vgz",
        ):
            r_enc = client.get("/api/poi/media-proxy", params={"url": enc_svg})
            assert r_enc.status_code == 415, f"Expected pre-flight 415 for {enc_svg}, got {r_enc.status_code}"
        assert upstream_hits == [], f"Encoded SVG bypassed pre-flight and hit upstream: {upstream_hits}"

        # 3. Non-canonical SVG/XML upstream MIME (image/x-svg+xml) on a .png URL -> 415
        r_xsvg = client.get(
            "/api/poi/media-proxy",
            params={"url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Fake.png"},
        )
        assert r_xsvg.status_code == 415


@pytest.mark.asyncio
async def test_sentinel_poc_r2_media_proxy_cancelled_error_closes_upstream():
    """R2 Bug #3: asyncio.CancelledError during client.send() or mid-stream disconnect ALWAYS closes client and response."""
    from starlette.requests import Request
    from routers import poi as poi_router

    real_cls = httpx.AsyncClient
    closed_on_send_cancel: List[bool] = []

    class _CancelSendClient(real_cls):
        async def send(self, request, *args, **kwargs):
            raise asyncio.CancelledError()

        async def aclose(self):
            closed_on_send_cancel.append(True)
            await super().aclose()

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/poi/media-proxy",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "query_string": b"",
    }
    with patch("routers.poi.create_safe_client", side_effect=lambda **kw: _CancelSendClient(**kw)):
        with pytest.raises(asyncio.CancelledError):
            await poi_router.media_proxy(
                Request(scope),
                url="https://upload.wikimedia.org/wikipedia/commons/a/ab/Valid.png",
            )
    assert len(closed_on_send_cancel) >= 1, "Client leaked on asyncio.CancelledError during send()"


@pytest.mark.asyncio
async def test_sentinel_poc_r2_dns_bulkhead_fast_path_under_saturation():
    """R2 Bug #4: Saturating all 4 DNS threads MUST NOT stall or fail-closed SAFE_WIKI_DOMAINS, BLOCKED_HOSTNAMES, or IP literals."""
    def _hanging_dns(*args, **kwargs):
        time.sleep(0.5)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    with patch("utils.url_safety.socket.getaddrinfo", side_effect=_hanging_dns):
        slow_tasks = [
            asyncio.create_task(url_safety.is_safe_url_async(f"https://stall-{i}.example.invalid/", timeout=0.35))
            for i in range(4)
        ]
        await asyncio.sleep(0.05)  # All 4 bulkhead workers now occupied in getaddrinfo

        t0 = time.perf_counter()
        wiki_safe = await url_safety.is_safe_url_async("https://upload.wikimedia.org/wikipedia/commons/a.png", timeout=0.1)
        blocked_safe = await url_safety.is_safe_url_async("http://127.0.0.1/secret", timeout=0.1)
        meta_safe = await url_safety.is_safe_url_async("http://metadata.google.internal/", timeout=0.1)
        pub_ip_safe = await url_safety.is_safe_url_async("https://93.184.216.34/img.png", timeout=0.1)
        elapsed = time.perf_counter() - t0

        await asyncio.gather(*slow_tasks)

    assert wiki_safe is True, "SAFE_WIKI_DOMAINS must fast-path inline when DNS bulkhead is saturated"
    assert blocked_safe is False
    assert meta_safe is False
    assert pub_ip_safe is True
    assert elapsed < 0.05, f"Pure-CPU fast-path stalled behind saturated DNS bulkhead: {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_sentinel_poc_r2_gst_first_param_preserves_query_delimiter():
    """R2 Bug #5: Stripping g_st when it is the FIRST query parameter must preserve '?' for remaining parameters."""
    captured_traced: List[str] = []

    class _SpyTracer:
        async def trace_full_chain_smart(self, u: str):
            captured_traced.append(u)
            return {"final_url": u}

    mock_gas = AsyncMock(return_value=None)
    with patch.object(link_resolver, "get_smart_tracer", return_value=_SpyTracer()), \
         patch.object(link_resolver, "is_safe_url_async", new_callable=AsyncMock, return_value=True), \
         patch.object(link_resolver, "resolve_via_gas", mock_gas), \
         patch.object(link_resolver, "fetch_og_metadata", new_callable=AsyncMock, return_value={"title": None, "image": None, "description": None, "site_name": None}):
        await link_resolver.resolve_google_maps_link("https://maps.app.goo.gl/Test123?g_st=ic&hl=zh-TW&utm_source=ios")

    assert captured_traced == ["https://maps.app.goo.gl/Test123?hl=zh-TW"]
    mock_gas.assert_awaited_once_with("https://maps.app.goo.gl/Test123?g_st=ic&hl=zh-TW&utm_source=ios")


@pytest.mark.asyncio
async def test_sentinel_poc_r2_safe_download_image_heic_mime_validation():
    """R2 Bug #6: .heic path rejects text/html and image/svg+xml (400) while still allowing application/octet-stream normalized to image/heic."""
    from routers import ai as ai_router

    for bad_ct in ("text/html", "image/svg+xml"):
        def _bad_handler(req: httpx.Request, ct: str = bad_ct) -> httpx.Response:
            return httpx.Response(200, headers={"Content-Type": ct}, content=b"<html>evil</html>")

        with patch("routers.ai.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
             patch("utils.url_safety.is_safe_url", return_value=True), \
             patch("utils.url_safety.httpx.AsyncClient", side_effect=_make_transport_client_factory(_bad_handler)):
            with pytest.raises(HTTPException) as exc:
                await ai_router.safe_download_image("https://cdn.example.com/photo.heic")
        assert exc.value.status_code == 400
        assert "Unsupported format" in exc.value.detail

    def _octet_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "application/octet-stream"}, content=b"\x00\x00\x00\x18ftypheic")

    with patch("routers.ai.is_safe_url_async", new_callable=AsyncMock, return_value=True), \
         patch("utils.url_safety.is_safe_url", return_value=True), \
         patch("utils.url_safety.httpx.AsyncClient", side_effect=_make_transport_client_factory(_octet_handler)):
        data, ct = await ai_router.safe_download_image("https://cdn.example.com/photo.heic")
    assert ct == "image/heic"
    assert len(data) > 0


def test_sentinel_poc_r2_slowapi_31st_request_returns_429():
    """R2 Rate-Limit Verification: Both /api/poi/resolve-link and /api/poi/media-proxy enforce HTTP 429 on 31st request/minute."""
    from main import app

    client = TestClient(app)

    limiter._storage.reset()
    resolve_codes = [
        client.post("/api/poi/resolve-link", json={"url": "http://127.0.0.1/blocked"}).status_code
        for _ in range(31)
    ]
    assert resolve_codes[:30] == [400] * 30
    assert resolve_codes[30] == 429

    limiter._storage.reset()
    media_codes = [
        client.get("/api/poi/media-proxy", params={"url": "https://evil.com/x.png"}).status_code
        for _ in range(31)
    ]
    assert media_codes[:30] == [400] * 30
    assert media_codes[30] == 429
