# -*- coding: utf-8 -*-
"""
Regression & Edge-Case Verification Suite for Tracks A–D:
- Track A: No duplicate local_q search, global_q fallback budget, 5.0s QueryRewrite timeout (without reordering ai_config),
           Tier2 observability logs, skip Tier3 DDG in prod CF-edge mode, [Citations] raw/cleaned/final log.
- Track B: _pick_hd_wiki_image 960px raster upgrade + SVG/TIFF/DjVu guard, Wikidata ?width=960,
           bounded LRU POI_ENRICH_CACHE (max 500 entries).
- Track C: Per-engine independent throttle locks in routers/route.py (OSRM vs Valhalla non-blocking).
- Track D: memory_service & deps run_in_threadpool offload, max_keepalive_connections=40,
           poi_resolve_link placelist error sanitization, @limiter.limit on /api/route, /api/poi/enrich, /api/poi/nearby.
"""

import ast
import asyncio
import json
import sys
import time
from collections import OrderedDict
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

import main as backend_main
from routers import poi as poi_router
from routers import route as route_router
from services import destination_taxonomy, memory_service, poi_service, web_search_engine
from utils import ai_config, deps
from utils.limiter import limiter

DUMMY_KEY = "AIzaSy" + "T" * 34


class _MockAsyncStream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __aiter__(self):
        self._it = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


@pytest.fixture(autouse=True)
def _clean_singletons():
    web_search_engine.__reset_web_search_cache_for_testing()
    poi_router.__resetPoiEnrichCacheForTesting()
    route_router.__reset_route_state_for_testing()
    limiter._storage.reset()
    yield
    web_search_engine.__reset_web_search_cache_for_testing()
    poi_router.__resetPoiEnrichCacheForTesting()
    route_router.__reset_route_state_for_testing()
    limiter._storage.reset()


# ============================================================================
# Track A: AI Web Search Revival
# ============================================================================


@pytest.mark.asyncio
async def test_track_a_main_does_not_repeat_identical_local_q_and_runs_global_q(capsys):
    """When search_query == local_q fails, main.py must NOT re-query local_q and must immediately run global_q."""
    called_queries = []

    async def fake_web_search(query, site_filter=None, max_results=3, region=None):
        called_queries.append((query, region))
        if "Tokyo Station" in query:
            return [
                {
                    "title": "Tokyo Station 2026 Travel Guide",
                    "url": "https://www.japan-guide.com/e/e3037.html",
                    "snippet": "Tokyo Station shops, ramen street, and itinerary recommendations for 2026.",
                }
            ]
        return []

    chunk = MagicMock(spec=["text", "thought", "candidates"])
    chunk.text = "推薦前往 Tokyo Station 2026 Travel Guide 介紹的東京車站一番街與拉麵街。"
    chunk.thought = None
    chunk.candidates = []

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(return_value=_MockAsyncStream([chunk]))

    lite_result = {
        "should_search": True,
        "destination": "東京",
        "local_query": "東京車站 2026 行程推薦",
        "global_query": "Tokyo Station 2026 travel guide",
        "search_query": "東京車站 2026 行程推薦",  # identical to local_query!
        "metadata": {
            "destination_code": "JP",
            "matched_destination": "東京",
            "local_region": "jp-jp",
            "global_region": "us-en",
            "clean_query": "東京車站 2026 行程推薦",
        },
        "source": "gemini-3.5-flash-lite",
    }

    with patch("main.genai.Client", return_value=mock_client), \
         patch("main.classify_chat_intent_with_meta", AsyncMock(return_value=("SEARCH", ["tool"], {"needs_query_rewrite": True}))), \
         patch("main.extract_search_queries_with_lite", AsyncMock(return_value=lite_result)), \
         patch("main.execute_web_search", side_effect=fake_web_search):
        events = [
            ev async for ev in backend_main.stream_chat_generator(
                api_key=DUMMY_KEY,
                history=[],
                message="東京車站 2026 行程推薦",
                raw_user_message="東京車站 2026 行程推薦",
                locale="zh",
            )
        ]

    queries_only = [q for q, _ in called_queries]
    assert queries_only == ["東京車站 2026 行程推薦", "Tokyo Station 2026 travel guide"], (
        f"Expected primary local_q once then global_q fallback (no duplicate local_q), got: {queries_only}"
    )

    out = capsys.readouterr().out
    assert "[Citations] raw=1 cleaned=1 final=" in out
    assert any("event: done" in e for e in events)


@pytest.mark.asyncio
async def test_track_a_query_rewrite_preserves_routing_order_and_5s_budget_rescues_second_model():
    """User Quote 1: QUERY_REWRITE_ROUTING order stays intact; 5.0s total budget gives model 2 time after model 1 times out."""
    assert ai_config.QUERY_REWRITE_ROUTING[0] == "gemini-3.1-flash-lite"
    assert ai_config.QUERY_REWRITE_ROUTING[1] == "gemini-3.5-flash-lite"

    seen_models = []
    captured_timeouts = []

    async def fake_gen(*, model, contents, config):
        seen_models.append(model)
        if model == "gemini-3.1-flash-lite":
            raise asyncio.TimeoutError()
        resp = MagicMock()
        resp.candidates = []
        resp.text = json.dumps({
            "should_search": True,
            "destination": "東京",
            "local_query": "淺草寺 營業時間 2026",
            "global_query": "Senso-ji Temple opening hours 2026",
        })
        return resp

    orig_wait_for = asyncio.wait_for

    async def spy_wait_for(aw, timeout):
        captured_timeouts.append(timeout)
        return await orig_wait_for(aw, timeout=timeout)

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = fake_gen

    with patch("services.destination_taxonomy.asyncio.wait_for", side_effect=spy_wait_for):
        res = await destination_taxonomy.extract_search_queries_with_lite(
            user_msg="淺草寺 營業時間",
            history=[],
            trip_destination="東京 5 天",
            locale="zh",
            api_key=DUMMY_KEY,
            genai_client=mock_client,
        )

    assert seen_models == ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]
    assert res["source"] == "gemini-3.5-flash-lite"
    assert res["local_query"] == "淺草寺 營業時間 2026"
    assert 5.0 in captured_timeouts, f"Outer timeout must be 5.0s, saw: {captured_timeouts}"
    assert 2.5 in captured_timeouts, f"Single-model timeout must remain 2.5s, saw: {captured_timeouts}"


@pytest.mark.asyncio
async def test_track_a_tier2_observability_log_and_prod_skips_tier3_ddg(monkeypatch, capsys):
    """Tier 2 emits structured status/source/count/elapsed_ms log; prod CF-edge mode skips Tier 3 DDG HTML."""
    monkeypatch.setenv("CF_WORKER_SEARCH_URL", "https://search-proxy.example.com")
    monkeypatch.setenv("CF_PROXY_SECRET", "unit-test-secret")
    monkeypatch.setenv("ENV", "production")

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"results": [], "source": "none"}

    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=fake_resp)

    tier3_mock = AsyncMock(side_effect=AssertionError("Tier 3 DDG HTML must be skipped in prod when CF Edge already ran"))
    tier4_mock = AsyncMock(return_value=[])

    with patch.object(web_search_engine, "get_search_client", return_value=fake_client), \
         patch.object(web_search_engine, "_search_ddg_html_fallback", tier3_mock), \
         patch.object(web_search_engine, "_search_wikipedia_fallback", tier4_mock):
        res = await web_search_engine.execute_web_search("淺草寺 營業時間 2026", region="jp-jp")

    assert res == []
    tier3_mock.assert_not_called()
    out = capsys.readouterr().out
    assert "[SearchEngine] Tier2 status=200 source=none count=0 elapsed_ms=" in out


# ============================================================================
# Track B: 960px Safe Raster Image Picker & Bounded POI_ENRICH_CACHE
# ============================================================================


def test_track_b_pick_hd_wiki_image_raster_guard_and_960px_upgrade():
    # 1. Safe raster originalimage within [331, 960] -> direct originalimage
    assert poi_service._pick_hd_wiki_image({
        "originalimage": {
            "source": "https://upload.wikimedia.org/wikipedia/commons/a/a1/Shiba_Park.jpg",
            "width": 800,
            "height": 600,
        },
        "thumbnail": {
            "source": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/Shiba_Park.jpg/330px-Shiba_Park.jpg",
            "width": 330,
        },
    }) == "https://upload.wikimedia.org/wikipedia/commons/a/a1/Shiba_Park.jpg"

    # 2. Oversized 4K originalimage (>960) -> upgrade thumbnail 330px -> 960px
    assert poi_service._pick_hd_wiki_image({
        "originalimage": {
            "source": "https://upload.wikimedia.org/wikipedia/commons/a/a1/Tokyo_Tower.jpg",
            "width": 4032,
            "height": 3024,
        },
        "thumbnail": {
            "source": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/Tokyo_Tower.jpg/330px-Tokyo_Tower.jpg",
            "width": 330,
        },
    }) == "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/Tokyo_Tower.jpg/960px-Tokyo_Tower.jpg"

    # 3. SVG originalimage (even width=512) MUST be rejected -> safe PNG thumbnail upgraded to 960px
    assert poi_service._pick_hd_wiki_image({
        "originalimage": {
            "source": "https://upload.wikimedia.org/wikipedia/commons/a/a1/Emblem.svg",
            "width": 512,
        },
        "thumbnail": {
            "source": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/Emblem.svg/330px-Emblem.svg.png",
            "width": 330,
        },
    }) == "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/Emblem.svg/960px-Emblem.svg.png"

    # 4. TIFF / DjVu originalimage MUST be rejected -> safe JPEG thumbnail upgraded to 960px
    assert poi_service._pick_hd_wiki_image({
        "originalimage": {
            "source": "https://upload.wikimedia.org/wikipedia/commons/b/b2/Old_Map.tif",
            "width": 720,
        },
        "thumbnail": {
            "source": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b2/Old_Map.tif/lossy-page1-330px-Old_Map.tif.jpg",
            "width": 330,
        },
    }) == "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b2/Old_Map.tif/lossy-page1-960px-Old_Map.tif.jpg"

    # 5. Encoded SVG thumbnail MUST be blocked completely
    assert poi_service._pick_hd_wiki_image({
        "thumbnail": {
            "source": "https://upload.wikimedia.org/wikipedia/commons/a/a1/Icon.%73vg",
            "width": 330,
        }
    }) == ""

    # 6. Already >= 960px thumbnail is NOT downgraded
    assert poi_service._pick_hd_wiki_image({
        "thumbnail": {
            "source": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/HiRes.webp/1280px-HiRes.webp",
            "width": 1280,
        }
    }) == "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/HiRes.webp/1280px-HiRes.webp"

    # 7. Boundary / empty inputs
    assert poi_service._pick_hd_wiki_image(None) == ""
    assert poi_service._pick_hd_wiki_image({}) == ""
    assert poi_service._pick_hd_wiki_image({"originalimage": {"source": "https://x/a.jpg", "width": True}}) == ""


@pytest.mark.asyncio
async def test_track_b_wikidata_fallback_uses_960px_width():
    """Wikidata P18 fallback URL must request ?width=960 instead of ?width=500."""
    with patch.object(poi_service, "get_wikidata_labels", AsyncMock(return_value={
        "labels": {"zh-TW": "芝公園", "en-US": "Shiba Park"},
        "sitelinks": {},
        "wikidata_image": "Shiba Park & Tokyo Tower.jpg",
    })), \
         patch.object(poi_service, "get_wikipedia_summary", AsyncMock(return_value=("", ""))), \
         patch.object(poi_service, "search_wikivoyage", AsyncMock(return_value=None)):
        enriched = await poi_service.enrich_poi_complete({"name": "芝公園", "wikidata_id": "Q1074284"}, lang="zh")

    assert enriched["image_url"].endswith("?width=960")
    assert "?width=500" not in enriched["image_url"]


def test_track_b_poi_enrich_cache_is_bounded_lru_500():
    assert isinstance(poi_router.POI_ENRICH_CACHE, OrderedDict)
    assert poi_router._POI_ENRICH_CACHE_MAX_SIZE == 500

    for i in range(510):
        poi_router._poi_enrich_cache_set(f"key_{i}", {"idx": i})

    assert len(poi_router.POI_ENRICH_CACHE) == 500
    assert "key_0" not in poi_router.POI_ENRICH_CACHE
    assert "key_9" not in poi_router.POI_ENRICH_CACHE
    assert "key_10" in poi_router.POI_ENRICH_CACHE
    assert "key_509" in poi_router.POI_ENRICH_CACHE

    # Access key_10 to promote to MRU, then insert one more -> key_11 evicted, key_10 retained
    assert poi_router._poi_enrich_cache_get("key_10") == {"idx": 10}
    poi_router._poi_enrich_cache_set("key_510", {"idx": 510})
    assert "key_10" in poi_router.POI_ENRICH_CACHE
    assert "key_11" not in poi_router.POI_ENRICH_CACHE


# ============================================================================
# Track C: Per-Engine Independent Route Throttle Locks
# ============================================================================


@pytest.mark.asyncio
async def test_track_c_route_per_engine_throttle_locks_are_independent():
    """OSRM pacing must NEVER block Valhalla fallback for 1s, while same-engine calls remain paced."""
    sleep_calls = []

    async def fake_sleep(sec):
        sleep_calls.append(sec)

    with patch.object(route_router.asyncio, "sleep", side_effect=fake_sleep):
        # 1. OSRM runs first, then Valhalla immediately -> ZERO sleep!
        await route_router._pace_upstream_request("osrm-fossgis")
        await route_router._pace_upstream_request("valhalla-fossgis")
        assert sleep_calls == [], f"Valhalla must not be blocked by OSRM lock, slept: {sleep_calls}"

        # 2. Second immediate OSRM call -> DOES trigger pacing sleep
        await route_router._pace_upstream_request("osrm-fossgis")
        assert len(sleep_calls) == 1 and 0 < sleep_calls[0] <= route_router._THROTTLE_INTERVAL_SEC


# ============================================================================
# Track D: Threadpool Offload, Keepalive=40, Error Sanitization & Rate Limits
# ============================================================================


@pytest.mark.asyncio
async def test_track_d_memory_service_and_deps_threadpool_and_keepalive():
    # 1. AST invariant: zero direct blocking .execute() inside async methods of memory_service.py
    mem_src = (REPO_ROOT / "backend" / "services" / "memory_service.py").read_text(encoding="utf-8")
    tree = ast.parse(mem_src)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            def visit(n):
                if isinstance(n, (ast.FunctionDef, ast.Lambda)):
                    return
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "execute":
                    violations.append(f"{node.name}:{n.lineno}")
                for c in ast.iter_child_nodes(n):
                    visit(c)
            for stmt in node.body:
                visit(stmt)
    assert violations == [], f"Found blocking .execute() in async memory_service methods: {violations}"

    # 2. Runtime check: MemoryService uses run_in_threadpool for both get & upsert
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"category": "diet", "preference": "不吃牛肉"}]
    )
    tp_calls = []
    orig_tp = memory_service.run_in_threadpool

    async def spy_tp(fn, *args, **kwargs):
        tp_calls.append(fn)
        return await orig_tp(fn, *args, **kwargs)

    with patch.object(memory_service, "run_in_threadpool", side_effect=spy_tp):
        ctx = await memory_service.MemoryService.get_preferences_context("u-1", mock_sb)
    assert "不吃牛肉" in ctx
    assert len(tp_calls) == 1

    # 3. deps.create_threadsafe_supabase_client uses max_keepalive_connections=40
    captured_limits = {}

    def fake_httpx_client(*args, **kwargs):
        captured_limits["limits"] = kwargs.get("limits")
        c = MagicMock()
        c.close = MagicMock()
        return c

    with patch.object(deps.httpx, "Client", side_effect=fake_httpx_client), \
         patch.object(deps, "create_client", return_value=MagicMock(postgrest=MagicMock())):
        deps.create_threadsafe_supabase_client("https://example.supabase.co", "sb_secret_test")
    assert captured_limits["limits"].max_keepalive_connections == 40

    # 4. deps.get_verified_user offloads supabase.auth.get_user via run_in_threadpool
    mock_auth_sb = MagicMock()
    mock_auth_sb.auth.get_user.return_value = MagicMock(
        user=MagicMock(id="11111111-1111-4111-8111-111111111111")
    )
    deps_tp_calls = []
    orig_deps_tp = deps.run_in_threadpool

    async def spy_deps_tp(fn, *args, **kwargs):
        deps_tp_calls.append(fn)
        return await orig_deps_tp(fn, *args, **kwargs)

    with patch.object(deps, "get_supabase", return_value=mock_auth_sb), \
         patch.object(deps, "run_in_threadpool", side_effect=spy_deps_tp):
        uid = await deps.get_verified_user(auth_header="Bearer external-oauth-token")
    assert uid == "11111111-1111-4111-8111-111111111111"
    assert len(deps_tp_calls) == 1


def test_track_d_poi_resolve_link_sanitizes_raw_placelist_errors():
    client = TestClient(backend_main.app)

    # Exploit: raw internal exception leaked in res["error"] MUST NOT appear in HTTP 422 response
    with patch("routers.poi.is_safe_url_async", AsyncMock(return_value=True)), \
         patch("routers.poi.resolve_google_maps_placelist", AsyncMock(return_value={
             "success": False,
             "items": [],
             "error": "httpx.ConnectError: [Errno 111] internal-proxy.corp:8080 secret_token=abc",
         })):
        r = client.post("/api/poi/resolve-link", json={"url": "https://www.google.com/maps/placelists/list/1234567890abcdef"})
    assert r.status_code == 422
    assert "internal-proxy.corp" not in r.text
    assert "secret_token" not in r.text
    assert "ConnectError" not in r.text

    # Benign control: known safe error code returns clean localized message
    with patch("routers.poi.is_safe_url_async", AsyncMock(return_value=True)), \
         patch("routers.poi.resolve_google_maps_placelist", AsyncMock(return_value={
             "success": False,
             "items": [],
             "error": "PRIVATE_OR_INVALID_LIST",
         })):
        r2 = client.post("/api/poi/resolve-link", json={"url": "https://www.google.com/maps/placelists/list/1234567890abcdef"})
    assert r2.status_code == 422
    assert "公開" in r2.json()["detail"]


def test_track_d_public_proxy_endpoints_enforce_60_per_minute_rate_limit():
    """Public /api/route, /api/poi/enrich, /api/poi/nearby must enforce 60/min @limiter.limit without signature errors."""
    client = TestClient(backend_main.app)

    # 1. /api/route
    limiter._storage.reset()
    with patch.object(route_router, "_compute_route_chain", AsyncMock(return_value=route_router.create_straight_fallback(
        [route_router.RouteStop(lat=35.6586, lng=139.7454), route_router.RouteStop(lat=35.6620, lng=139.7500)], "walk"
    ))):
        statuses = [
            client.post("/api/route", json={
                "stops": [{"lat": 35.6586, "lng": 139.7454}, {"lat": 35.6620, "lng": 139.7500}],
                "mode": "walk",
            }).status_code
            for _ in range(61)
        ]
    assert statuses[:60] == [200] * 60
    assert statuses[60] == 429

    # 2. /api/poi/enrich
    limiter._storage.reset()
    with patch("routers.poi.enrich_poi_complete", AsyncMock(return_value={"name": "Tokyo Tower", "status": "SUCCESS"})):
        statuses_enrich = [
            client.post("/api/poi/enrich", json={"name": "Tokyo Tower", "lat": 35.6586, "lng": 139.7454}).status_code
            for _ in range(61)
        ]
    assert statuses_enrich[:60] == [200] * 60
    assert statuses_enrich[60] == 429

    # 3. /api/poi/nearby
    limiter._storage.reset()
    with patch("routers.poi.search_poi_combined", AsyncMock(return_value=[])):
        statuses_nearby = [
            client.get("/api/poi/nearby", params={"lat": 35.6586, "lng": 139.7454, "category": "restaurant"}).status_code
            for _ in range(61)
        ]
    assert statuses_nearby[:60] == [200] * 60
    assert statuses_nearby[60] == 429
