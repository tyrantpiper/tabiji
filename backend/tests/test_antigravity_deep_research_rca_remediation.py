# -*- coding: utf-8 -*-
"""
Antigravity Deep Research RCA Remediation Test Suite (AC-1 ~ AC-6)
==================================================================
Covers:
- AC-1: Antigravity Remote Sandbox primary SSE engine + polling/heartbeat + cancel on disconnect
        + _extract_antigravity_output_and_sources (steps url_context_result / google_search_result
        / url_citation / Markdown links + SSRF host DNS cache + file:///workspace/ dead-link sanitization)
        + strict boundary that normal /api/chat/stream NEVER calls Antigravity
- AC-2: Smooth degradation from Antigravity 503/403/timeout/empty to Tier 2 Flash/Hydrogen
        with ZERO GoogleSearch() tool attachment & default ENABLE_DEEP_RESEARCH_DIRECT_RSS="0"
- AC-3: 503 zero in-place retry (retry_5xx=False) fast model rotation + accurate circuit breaking
- AC-4: Frontend locale strict authority (locale="en" zero CJK translation + CJK post-guard;
        locale="zh" preserves Chinese UI framing even with English entity input) + English <=7 words
        + filler/stopword updates
- AC-5: Normal chat pure factual SEARCH unloads itinerary tools (no canned itinerary hallucination)
        while action/scheduling/nearby-recommendation SEARCH retains itinerary tools
- AC-6: Conditional [1]/[2] citation prompt rules, zero 602410 leak prohibition, WARNING log levels
"""

import asyncio
import json
import logging
import os
import sys
import types as py_types
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors
from google.genai._gaos.lib import compat_errors

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main as backend_main
from main import app
from routers import agents as agents_router
from services import destination_taxonomy, model_manager, web_search_engine

TEST_KEY = "AIzaSyAntigravityRcaRemediationTestKey1234"
HEADERS = {
    "X-Gemini-API-Key": TEST_KEY,
    "Content-Type": "application/json",
}


@pytest.fixture(autouse=True)
def _reset_singletons():
    agents_router.__reset_fallback_tasks_for_testing()
    model_manager.__reset_client_cache_for_testing()
    model_manager._CIRCUIT_STATE.clear()
    yield
    agents_router.__reset_fallback_tasks_for_testing()
    model_manager.__reset_client_cache_for_testing()
    model_manager._CIRCUIT_STATE.clear()


def _make_genai_error(code: int, message: str) -> genai_errors.APIError:
    err = genai_errors.APIError.__new__(genai_errors.APIError)
    Exception.__init__(err, message)
    err.code = code
    err.message = message
    err.status = None
    err.details = None
    return err


def _make_compat_error(status_code: int, message: str):
    req = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/interactions")
    resp = httpx.Response(status_code, request=req, json={"error": {"message": message}})
    return compat_errors.APIError.generate(
        status_code=status_code,
        body={"error": {"message": message}},
        message=message,
        response=resp,
    )


def _make_text_resp(text: str):
    resp = MagicMock()
    resp.candidates = []
    resp.text = text
    return resp


def _parse_sse_blocks(raw_text: str):
    events = []
    heartbeats = 0
    for block in raw_text.split("\n\n"):
        if not block.strip():
            continue
        ev_name = None
        data_lines = []
        saw_hb = False
        for line in block.splitlines():
            if line.startswith(":"):
                saw_hb = True
            elif line.startswith("event:"):
                ev_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if ev_name:
            raw_d = "\n".join(data_lines)
            try:
                parsed = json.loads(raw_d)
            except Exception:
                parsed = raw_d
            events.append((ev_name, parsed))
        elif saw_hb:
            heartbeats += 1
    return events, heartbeats


class _FakeChunkStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def __aiter__(self):
        self._it = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


# ==============================================================================
# AC-1: Antigravity Primary SSE + Source Extraction + Dead-Link Sanitization + Cancel
# ==============================================================================
@pytest.mark.asyncio
async def test_ac1_antigravity_stream_polling_sources_dead_link_sanitization_and_polling_parity(monkeypatch):
    monkeypatch.setattr(agents_router, "_ANTIGRAVITY_POLL_INTERVAL_SEC", 0.01)
    monkeypatch.setattr(agents_router, "_ANTIGRAVITY_HEARTBEAT_SEC", 0.005)
    monkeypatch.setattr(agents_router, "_ANTIGRAVITY_MAX_WAIT_SEC", 5.0)

    created_obj = py_types.SimpleNamespace(id="int_ag_live_001", status="in_progress")
    poll_1 = py_types.SimpleNamespace(id="int_ag_live_001", status="in_progress", output_text="")
    poll_2 = py_types.SimpleNamespace(id="int_ag_live_001", status="queued", output_text="")
    poll_done = py_types.SimpleNamespace(
        id="int_ag_live_001",
        status="completed",
        output_text=(
            "# Tokyo Disney 2026 Research\n"
            "Detailed breakdown in [本地報告](file:///workspace/report.md) and `file:///workspace/raw.csv`.\n"
            "See file:///workspace/tmp.txt for temp logs.\n"
            "- [file:///workspace/dead_only.md](file:///workspace/dead_only.md)\n"
            "Official ticket updates: [Tokyo Disney Resort Official](https://www.tokyodisneyresort.jp/en/index.html)\n"
        ),
        steps=[
            py_types.SimpleNamespace(
                type="url_context_result",
                result=[
                    py_types.SimpleNamespace(status="success", url="https://www.tokyodisneyresort.jp/en/index.html"),
                    py_types.SimpleNamespace(status="success", url="https://www.tokyodisneyresort.jp/en/tdl/"),
                    py_types.SimpleNamespace(status="success", url="https://www.japan.travel/en/spot/1555/"),
                    py_types.SimpleNamespace(status="error", url="https://broken.example.com/404"),
                    py_types.SimpleNamespace(status="success", url="http://127.0.0.1:8080/internal-ssrf"),
                ],
            ),
            py_types.SimpleNamespace(
                type="google_search_result",
                result=[
                    py_types.SimpleNamespace(
                        web=py_types.SimpleNamespace(
                            title="JR East Official Guide",
                            url="https://www.jreast.co.jp/multi/en/",
                        )
                    )
                ],
            ),
        ],
    )

    mock_client = MagicMock()
    mock_client.interactions.create = MagicMock(return_value=created_obj)
    mock_client.interactions.get = MagicMock(side_effect=[poll_1, poll_2, poll_done])
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=AssertionError("Tier 2 Flash must NOT run when Antigravity succeeds")
    )

    safe_checks = []

    async def fake_safe_url(u: str) -> bool:
        safe_checks.append(u)
        return "127.0.0.1" not in u

    tc = TestClient(app)
    with patch("routers.agents.genai.Client", return_value=mock_client), \
         patch.object(agents_router, "_fetch_live_pricing_context", AsyncMock(return_value="")), \
         patch.object(agents_router, "is_safe_url_async", side_effect=fake_safe_url):
        resp = tc.post(
            "/api/agents/research/stream",
            json={
                "prompt": "Tokyo Disneyland 2026 ticket and expansion analysis",
                "destination": "TYO",
                "environment": "remote",
                "locale": "en",
            },
            headers=HEADERS,
        )

    assert resp.status_code == 200
    events, heartbeats = _parse_sse_blocks(resp.text)
    assert heartbeats >= 1, "Polling loop must emit : heartbeat keepalive"

    # Verify thinking event carries engine="antigravity"
    thinking_payloads = [d for ev, d in events if ev == "thinking" and isinstance(d, dict)]
    assert any(p.get("engine") == "antigravity" and p.get("status") == "researching" for p in thinking_payloads)

    # Verify interactions.create kwargs
    create_kw = mock_client.interactions.create.call_args.kwargs
    assert create_kw["agent"] == agents_router.ANTIGRAVITY_AGENT_ID
    assert create_kw["environment"] == "remote"
    assert create_kw["background"] is True
    assert create_kw["store"] is True
    assert "602410" in create_kw["input"]
    assert "file:///workspace/" in create_kw["input"]

    # Verify dead links purged while readable label and legitimate link preserved
    text_out = "".join(d.get("text", "") for ev, d in events if ev == "text" and isinstance(d, dict))
    assert "file:///workspace/" not in text_out.lower()
    assert "本地報告" in text_out
    assert "https://www.tokyodisneyresort.jp/en/index.html" in text_out

    # Verify structured sources in done payload
    done_events = [d for ev, d in events if ev == "done" and isinstance(d, dict)]
    assert len(done_events) == 1
    done = done_events[0]
    assert done["engine"] == "antigravity"
    assert done["model_used"] == "antigravity"
    uris = [s["uri"] for s in done["sources"]]
    assert "https://www.tokyodisneyresort.jp/en/index.html" in uris
    assert "https://www.japan.travel/en/spot/1555/" in uris
    assert "https://www.jreast.co.jp/multi/en/" in uris
    assert not any("127.0.0.1" in u for u in uris), "SSRF URL must be blocked"
    assert not any("broken.example.com" in u for u in uris), "Error status URL must be excluded"
    # Title merged from Markdown link onto url_context_result entry
    tdr = next(s for s in done["sources"] if s["uri"] == "https://www.tokyodisneyresort.jp/en/index.html")
    assert tdr["title"] == "Tokyo Disney Resort Official"
    # Per-request host DNS cache deduplicates two URLs on www.tokyodisneyresort.jp
    tdr_dns_checks = [u for u in safe_checks if "tokyodisneyresort.jp" in u]
    assert len(tdr_dns_checks) == 1

    # Verify GET /api/agents/interactions/{id} shares exact same sanitizer + source extractor + queued->running
    mock_client.interactions.get = MagicMock(side_effect=[poll_2, poll_done])
    with patch("routers.agents.genai.Client", return_value=mock_client), \
         patch.object(agents_router, "is_safe_url_async", side_effect=fake_safe_url):
        r_queued = tc.get("/api/agents/interactions/int_ag_live_001", headers=HEADERS)
        r_done = tc.get("/api/agents/interactions/int_ag_live_001", headers=HEADERS)
    assert r_queued.status_code == 200
    assert r_queued.json()["status"] == "running"
    assert r_done.status_code == 200
    done_json = r_done.json()
    assert "file:///workspace/" not in done_json["output_text"].lower()
    assert len(done_json["sources"]) == 4


@pytest.mark.asyncio
async def test_ac1_antigravity_stream_cancel_on_disconnect_401_failfast_and_normal_chat_isolation(monkeypatch):
    monkeypatch.setattr(agents_router, "_ANTIGRAVITY_POLL_INTERVAL_SEC", 5.0)

    created_obj = py_types.SimpleNamespace(id="int_ag_cancel_99", status="in_progress")
    poll_running = py_types.SimpleNamespace(id="int_ag_cancel_99", status="in_progress", output_text="")
    mock_client = MagicMock()
    mock_client.interactions.create = MagicMock(return_value=created_obj)
    mock_client.interactions.get = MagicMock(return_value=poll_running)
    mock_client.interactions.cancel = MagicMock(return_value={"status": "cancelled"})

    req_body = agents_router.AgentResearchRequest(
        prompt="Long running research",
        destination="TYO",
        locale="zh",
    )
    with patch("routers.agents.genai.Client", return_value=mock_client), \
         patch.object(agents_router, "_fetch_live_pricing_context", AsyncMock(return_value="")):
        resp = await agents_router.stream_deep_research(req_body, request=None, api_key=TEST_KEY)
        agen = resp.body_iterator
        # Consume start + thinking + antigravity thinking, then simulate client abort during poll sleep
        seen = []
        for _ in range(3):
            seen.append(await agen.__anext__())
        assert any("antigravity" in chunk for chunk in seen)

        next_task = asyncio.create_task(agen.__anext__())
        await asyncio.sleep(0.05)
        next_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await next_task

    mock_client.interactions.cancel.assert_called_once_with(id="int_ag_cancel_99")

    # 401 auth_fail on interactions.create -> immediate 401 SSE error without invoking Tier 2
    mock_auth_client = MagicMock()
    mock_auth_client.interactions.create = MagicMock(side_effect=_make_compat_error(401, "API key invalid"))
    mock_auth_client.aio.models.generate_content = AsyncMock(
        side_effect=AssertionError("Must not invoke Tier 2 on 401 auth_fail")
    )
    tc = TestClient(app)
    with patch("routers.agents.genai.Client", return_value=mock_auth_client), \
         patch.object(agents_router, "_fetch_live_pricing_context", AsyncMock(return_value="")):
        r_401 = tc.post(
            "/api/agents/research/stream",
            json={"prompt": "Tokyo trip", "locale": "en"},
            headers=HEADERS,
        )
    events_401, _ = _parse_sse_blocks(r_401.text)
    err_evs = [d for ev, d in events_401 if ev == "error" and isinstance(d, dict)]
    assert len(err_evs) == 1 and err_evs[0]["code"] == 401

    # Hard boundary: normal chat /api/chat/stream NEVER calls interactions.create
    mock_chat_client = MagicMock()
    mock_chat_client.interactions.create = MagicMock(
        side_effect=AssertionError("Normal chat MUST NEVER invoke Antigravity sandbox!")
    )
    chunk = MagicMock(spec=["text", "thought", "candidates"])
    chunk.text = "Hello from normal chat!"
    chunk.thought = None
    chunk.candidates = []
    mock_chat_client.aio.models.generate_content_stream = AsyncMock(return_value=_FakeChunkStream([chunk]))
    with patch("main.genai.Client", return_value=mock_chat_client), \
         patch.object(backend_main, "classify_chat_intent_with_meta", AsyncMock(return_value=("CHAT", [], {"source": "fast"}))):
        r_chat = tc.post(
            "/api/chat/stream",
            json={"message": "Hi there", "history": [], "locale": "en"},
            headers=HEADERS,
        )
    assert r_chat.status_code == 200
    assert "Hello from normal chat!" in r_chat.text
    mock_chat_client.interactions.create.assert_not_called()


# ==============================================================================
# AC-2: Antigravity 503/403-preview Degrades to Tier 2 with ZERO GoogleSearch() + Default RSS Off
# ==============================================================================
@pytest.mark.asyncio
async def test_ac2_antigravity_503_and_preview_403_degrade_zero_google_search_and_default_direct_rss_off(monkeypatch):
    monkeypatch.delenv("ENABLE_DEEP_RESEARCH_DIRECT_RSS", raising=False)
    assert agents_router._is_direct_rss_enabled() is False

    # Direct RSS skipped by default while fast execute_web_search still works
    rss_should_not_run = AsyncMock(side_effect=AssertionError("Direct RSS must be off by default"))
    web_fast = AsyncMock(return_value=[{"title": "Kyoto Travel Official", "url": "https://kyoto.travel/en/", "snippet": "Guide"}])
    with patch.object(agents_router, "_build_research_news_query", AsyncMock(return_value="Kyoto guide 2026")), \
         patch.object(agents_router, "fetch_google_news_rss", rss_should_not_run), \
         patch.object(agents_router, "execute_web_search", web_fast):
        xml_blk, cands = await agents_router._fetch_live_research_intelligence("Kyoto guide", "KIX", TEST_KEY, locale="en")
    rss_should_not_run.assert_not_called()
    assert len(cands) == 1
    assert "<live_news_reference" in xml_blk

    # Antigravity 503 and preview-403 both degrade smoothly with config.tools == None
    for upstream_err in (
        _make_compat_error(503, "Sandbox overloaded"),
        _make_compat_error(403, "Preview agent antigravity-preview-09-2026 not enabled for project"),
    ):
        captured_tools = []

        async def fake_gen(*, model, contents, config):
            captured_tools.append((model, getattr(config, "tools", None)))
            return _make_text_resp("# Tier 2 Research Report\nClean analysis.")

        mock_client = MagicMock()
        mock_client.interactions.create = MagicMock(side_effect=upstream_err)
        mock_client.aio.models.generate_content = AsyncMock(side_effect=fake_gen)

        tc = TestClient(app)
        with patch("routers.agents.genai.Client", return_value=mock_client), \
             patch.object(agents_router, "_fetch_live_pricing_context", AsyncMock(return_value="")):
            resp = tc.post(
                "/api/agents/research/stream",
                json={"prompt": "Kyoto budget breakdown", "destination": "KIX", "locale": "en"},
                headers=HEADERS,
            )
        assert resp.status_code == 200
        assert len(captured_tools) == 1
        assert captured_tools[0][1] is None, "Tier 2 must NEVER pass GoogleSearch() tools"


# ==============================================================================
# AC-3: 503 Zero In-Place Retry Fast Rotation + Accurate Circuit Breaking
# ==============================================================================
@pytest.mark.asyncio
async def test_ac3_503_zero_inplace_retry_fast_rotation_and_circuit_breaker():
    err_503 = _make_genai_error(503, "UNAVAILABLE: Model overloaded")
    calls_stream = []

    async def fake_gen_stream(*, model, contents, config):
        calls_stream.append(model)
        if model in ("gemini-4-hydrogen", "gemini-3.8-flash"):
            raise err_503
        return _make_text_resp("# Fast Rotated Report")

    mock_client = MagicMock()
    mock_client.interactions.create = MagicMock(side_effect=_make_compat_error(503, "Queue full"))
    mock_client.aio.models.generate_content = AsyncMock(side_effect=fake_gen_stream)

    sleep_spy = AsyncMock()
    routing = ["gemini-4-hydrogen", "gemini-3.8-flash", "gemini-3.5-flash-lite"]
    tc = TestClient(app)
    with patch("routers.agents.genai.Client", return_value=mock_client), \
         patch("routers.agents.build_effective_routing", return_value=routing), \
         patch("services.model_manager.asyncio.sleep", sleep_spy), \
         patch.object(agents_router, "_fetch_live_pricing_context", AsyncMock(return_value="")):
        resp = tc.post(
            "/api/agents/research/stream",
            json={"prompt": "Analyze Osaka train passes", "destination": "KIX", "locale": "en"},
            headers=HEADERS,
        )

    assert resp.status_code == 200
    assert calls_stream == ["gemini-4-hydrogen", "gemini-3.8-flash", "gemini-3.5-flash-lite"]
    # Zero non-zero retry backoff sleeps (only asyncio.sleep(0) SSE event-loop yields are permitted)
    assert all((c.args and c.args[0] == 0) for c in sleep_spy.await_args_list)
    assert model_manager._CIRCUIT_STATE[model_manager._get_circuit_key("gemini-4-hydrogen", TEST_KEY)]["errors"] == 1
    assert model_manager._CIRCUIT_STATE[model_manager._get_circuit_key("gemini-3.8-flash", TEST_KEY)]["errors"] == 1

    # Same contract for _execute_flash_fallback_task
    calls_fb = []
    sleep_spy.reset_mock()

    async def fake_gen_fb(*, model, contents, config):
        calls_fb.append(model)
        if model in ("gemini-4-hydrogen", "gemini-3.8-flash"):
            raise err_503
        return _make_text_resp("# Fallback Rotated Report")

    mock_client.aio.models.generate_content = AsyncMock(side_effect=fake_gen_fb)
    with patch("routers.agents.genai.Client", return_value=mock_client), \
         patch("routers.agents.build_effective_routing", return_value=routing), \
         patch("services.model_manager.asyncio.sleep", sleep_spy):
        await agents_router._execute_flash_fallback_task(
            "fallback_fast_rotate_1", "Analyze Osaka train passes", TEST_KEY, locale="en"
        )
    assert calls_fb == ["gemini-4-hydrogen", "gemini-3.8-flash", "gemini-3.5-flash-lite"]
    assert agents_router._FALLBACK_TASKS["fallback_fast_rotate_1"]["status"] == "completed"
    assert agents_router._FALLBACK_TASKS["fallback_fast_rotate_1"]["engine"] == "gemini-3.5-flash-lite"
    sleep_spy.assert_not_awaited()
    assert model_manager._CIRCUIT_STATE[model_manager._get_circuit_key("gemini-4-hydrogen", TEST_KEY)]["errors"] == 2
    assert model_manager._CIRCUIT_STATE[model_manager._get_circuit_key("gemini-3.8-flash", TEST_KEY)]["errors"] == 2

    # Default retry_5xx=True preserved for regular non-agent callers
    regular_attempts = {"n": 0}

    async def flaky_once(_cfg):
        regular_attempts["n"] += 1
        if regular_attempts["n"] == 1:
            raise err_503
        return _make_text_resp("recovered")

    with patch("services.model_manager.asyncio.sleep", AsyncMock()) as reg_sleep:
        out = await model_manager._execute_with_transient_retry(
            flaky_once, model_name="gemini-3.6-flash", config=MagicMock(), timeout_sec=10.0, tag="Chat"
        )
    assert regular_attempts["n"] == 2
    reg_sleep.assert_awaited_once()
    assert out.text == "recovered"


# ==============================================================================
# AC-4: Strict Frontend Locale Authority + English <= 7 Words + Filler/Stopwords
# ==============================================================================
@pytest.mark.asyncio
async def test_ac4_locale_authority_en_never_translates_to_cjk_and_zh_keeps_chinese_mode():
    captured_en = {}

    async def fake_en_misbehaving_llm(*, model, contents, config):
        captured_en["sys_inst"] = getattr(config, "system_instruction", "")
        # Simulate model mistakenly translating English query to Chinese local_query
        return _make_text_resp(
            json.dumps({
                "should_search": True,
                "destination": "Tokyo",
                "local_query": "東京迪士尼 2026 新園區",
                "global_query": "Tokyo Disneyland 2026 new expansion",
            })
        )

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = fake_en_misbehaving_llm

    res_en = await destination_taxonomy.extract_search_queries_with_lite(
        user_msg="Tokyo Disneyland 2026 new expansion",
        history=None,
        trip_destination="Tokyo",
        locale="en",
        api_key=TEST_KEY,
        genai_client=mock_client,
    )
    # 1. sys_inst for locale="en" must have ZERO Chinese examples
    assert "但是最新的資訊呢" not in captured_en["sys_inst"]
    assert "這家幾點開" not in captured_en["sys_inst"]
    assert "English" in captured_en["sys_inst"]
    # 2. Post-guard replaces mistakenly Chinese local_query with English global_query (zero CJK)
    assert not destination_taxonomy._HAS_CJK_RE.search(res_en["local_query"])
    assert res_en["local_query"] == "Tokyo Disneyland 2026 new expansion"

    # Offline fallback for locale="en" on Japanese landmark also stays English (no 食べログ/最新)
    res_en_offline = await destination_taxonomy.extract_search_queries_with_lite(
        user_msg="Kiyomizu-dera Temple opening hours and admission fee",
        locale="en",
        api_key=None,
    )
    assert not destination_taxonomy._HAS_CJK_RE.search(res_en_offline["local_query"])

    # locale="zh" + English landmark input -> MUST stay Traditional Chinese UI mode
    captured_zh = {}

    async def fake_zh_llm(*, model, contents, config):
        captured_zh["sys_inst"] = getattr(config, "system_instruction", "")
        return _make_text_resp(
            json.dumps({
                "should_search": True,
                "destination": "東京",
                "local_query": "Tokyo Disneyland 2026 門票 攻略",
                "global_query": "Tokyo Disneyland 2026 tickets guide",
            })
        )

    mock_client.aio.models.generate_content = fake_zh_llm
    res_zh = await destination_taxonomy.extract_search_queries_with_lite(
        user_msg="Tokyo Disneyland 2026",
        locale="zh",
        api_key=TEST_KEY,
        genai_client=mock_client,
    )
    assert "Traditional Chinese" in captured_zh["sys_inst"]
    assert "但是最新的資訊呢" in captured_zh["sys_inst"]
    assert "Tokyo Disneyland" in res_zh["local_query"]
    assert "門票" in res_zh["local_query"]

    # English query distillation accepts up to 7 words (<= 45 chars)
    with patch.object(
        agents_router,
        "extract_search_queries_with_lite",
        AsyncMock(
            return_value={
                "should_search": True,
                "source": "gemini-3.1-flash-lite",
                "local_query": "Kyoto Kiyomizu dera temple hours fee 2026",
            }
        ),
    ):
        q7 = await agents_router._build_research_news_query(
            "Kiyomizu-dera hours and fee", "KIX", TEST_KEY, locale="en"
        )
    assert q7 == "Kyoto Kiyomizu dera temple hours fee 2026"

    # Filler/stopword updates strip 深度 / 動態 / deep / analysis / de / new
    c_zh = agents_router._compress_research_fallback_query("東京迪士尼 深度 動態 展覽", "東京", "zh")
    assert "深度" not in c_zh and "動態" not in c_zh
    c_en = agents_router._compress_research_fallback_query("Tokyo deep analysis de new exhibition", "Tokyo", "en")
    for w in ("deep", "analysis", "de", "new"):
        assert f" {w} " not in f" {c_en.lower()} "
    assert "動態" not in web_search_engine._extract_news_core_tokens("京都 櫻花 動態 2026")


# ==============================================================================
# AC-5: Normal Chat Pure Factual SEARCH Unloads Itinerary Tools (Zero Canned Template)
# ==============================================================================
@pytest.mark.asyncio
async def test_ac5_chat_stream_pure_factual_search_unloads_itinerary_tools_and_keeps_action_tools():
    async def _run_and_capture_tools(message: str, locale: str):
        captured_cfgs = []

        async def fake_stream(*, model, contents, config):
            captured_cfgs.append(config)
            c = MagicMock(spec=["text", "thought", "candidates"])
            c.text = "Kiyomizu-dera opens 6:00 AM to 6:00 PM; admission is 500 JPY."
            c.thought = None
            c.candidates = []
            return _FakeChunkStream([c])

        mock_client = MagicMock()
        mock_client.aio.models.generate_content_stream = fake_stream
        with patch.object(backend_main.genai, "Client", return_value=mock_client), \
             patch.object(
                 backend_main,
                 "classify_chat_intent_with_meta",
                 AsyncMock(return_value=("SEARCH", model_manager.ALL_CHAT_TOOLS, {"needs_query_rewrite": False})),
             ), \
             patch.object(backend_main, "execute_web_search", AsyncMock(return_value=[])), \
             patch.object(backend_main, "extract_search_queries_with_lite", AsyncMock(return_value={"source": "deterministic_fallback"})):
            events = [
                ev
                async for ev in backend_main.stream_chat_generator(
                    api_key=TEST_KEY,
                    history=[],
                    message=message,
                    raw_user_message=message,
                    locale=locale,
                )
            ]
        return captured_cfgs, "".join(events)

    # 1. Pure factual EN query -> tools MUST be None
    cfgs_en, evs_en = await _run_and_capture_tools(
        "What are the opening hours and admission fee for Kiyomizu-dera Temple in Kyoto?", "en"
    )
    assert len(cfgs_en) == 1
    assert cfgs_en[0].tools is None
    assert "500 JPY" in evs_en

    # 2. Pure factual ZH query -> tools MUST be None
    cfgs_zh, _ = await _run_and_capture_tools("清水寺營業時間、門票票價與休館公告", "zh")
    assert len(cfgs_zh) == 1
    assert cfgs_zh[0].tools is None

    # 3. Compound action / scheduling / nearby recommendation query -> MUST retain itinerary tools
    cfgs_act, _ = await _run_and_capture_tools("幫我查清水寺附近推薦餐廳並加入行程", "zh")
    assert len(cfgs_act) == 1
    assert cfgs_act[0].tools is not None
    decl_names = [f.name for t in cfgs_act[0].tools for f in (t.function_declarations or [])]
    assert "add_itinerary_item" in decl_names
    assert "remove_itinerary_item" in decl_names


# ==============================================================================
# AC-6: Conditional Citations, Zero 602410 Leak Directive & WARNING Log Levels
# ==============================================================================
@pytest.mark.asyncio
async def test_ac6_clean_prompts_no_dangling_citations_no_602410_and_warning_logs(caplog):
    sys_no_src_zh = agents_router._build_deep_research_sys_inst(is_en=False, has_live_sources=False)
    assert "嚴禁在報告中編造或輸出 [1]、[2]" in sys_no_src_zh
    assert "602410" in sys_no_src_zh
    assert "file:///workspace/" in sys_no_src_zh

    sys_no_src_en = agents_router._build_deep_research_sys_inst(is_en=True, has_live_sources=False)
    assert "do NOT fabricate" in sys_no_src_en
    assert "602410" in sys_no_src_en

    sys_with_src_zh = agents_router._build_deep_research_sys_inst(is_en=False, has_live_sources=True)
    assert "<live_news_reference>" in sys_with_src_zh
    assert "602410" in sys_with_src_zh

    # fetch_google_news_rss logs WARNING on CancelledError and re-raises
    class _CancelClient:
        def stream(self, *args, **kwargs):
            raise asyncio.CancelledError()

    with caplog.at_level(logging.WARNING, logger="ryan-travel-api"), \
         patch.object(web_search_engine, "get_search_client", return_value=_CancelClient()):
        with pytest.raises(asyncio.CancelledError):
            await web_search_engine.fetch_google_news_rss("Kyoto 2026")
    assert any(
        rec.levelno == logging.WARNING and "[NewsRSS] status=cancelled" in rec.getMessage()
        for rec in caplog.records
    )

    # _execute_with_transient_retry logs WARNING on 503 short retry when retry_5xx=True
    caplog.clear()
    calls = {"n": 0}

    async def fail_once(_cfg):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _make_genai_error(503, "Overloaded")
        return _make_text_resp("ok")

    with caplog.at_level(logging.WARNING, logger="ryan-travel-api"), \
         patch("services.model_manager.asyncio.sleep", AsyncMock()):
        await model_manager._execute_with_transient_retry(
            fail_once, model_name="gemini-3.6-flash", config=MagicMock(), timeout_sec=10.0, tag="LogCheck"
        )
    assert any(
        rec.levelno == logging.WARNING and "[LogCheck 503 Short Retry]" in rec.getMessage()
        for rec in caplog.records
    )


@pytest.mark.asyncio
async def test_edge_antigravity_timeout_empty_degradation_and_redos_sanitizer(monkeypatch):
    import time

    # 1. Antigravity polling timeout -> cancels interaction AND degrades cleanly to Tier 2
    monkeypatch.setattr(agents_router, "_ANTIGRAVITY_POLL_INTERVAL_SEC", 0.01)
    monkeypatch.setattr(agents_router, "_ANTIGRAVITY_MAX_WAIT_SEC", 0.02)
    mock_client = MagicMock()
    mock_client.interactions.create = MagicMock(return_value=py_types.SimpleNamespace(id="int_timeout_1", status="in_progress"))
    mock_client.interactions.get = MagicMock(return_value=py_types.SimpleNamespace(id="int_timeout_1", status="in_progress", output_text=""))
    mock_client.interactions.cancel = MagicMock(return_value={"status": "cancelled"})
    mock_client.aio.models.generate_content = AsyncMock(return_value=_make_text_resp("# Tier 2 After Timeout"))

    tc = TestClient(app)
    with patch("routers.agents.genai.Client", return_value=mock_client), \
         patch.object(agents_router, "_fetch_live_pricing_context", AsyncMock(return_value="")):
        r_to = tc.post(
            "/api/agents/research/stream",
            json={"prompt": "Osaka itinerary", "locale": "en"},
            headers=HEADERS,
        )
    assert r_to.status_code == 200
    assert "Tier 2 After Timeout" in r_to.text
    mock_client.interactions.cancel.assert_called_once_with(id="int_timeout_1")

    # 2. Antigravity completed with empty output -> degrades cleanly to Tier 2
    monkeypatch.setattr(agents_router, "_ANTIGRAVITY_MAX_WAIT_SEC", 5.0)
    mock_client_empty = MagicMock()
    mock_client_empty.interactions.create = MagicMock(return_value=py_types.SimpleNamespace(id="int_empty_1", status="in_progress"))
    mock_client_empty.interactions.get = MagicMock(return_value=py_types.SimpleNamespace(id="int_empty_1", status="completed", output_text="   ", steps=[]))
    mock_client_empty.aio.models.generate_content = AsyncMock(return_value=_make_text_resp("# Tier 2 After Empty"))
    with patch("routers.agents.genai.Client", return_value=mock_client_empty), \
         patch.object(agents_router, "_fetch_live_pricing_context", AsyncMock(return_value="")):
        r_emp = tc.post(
            "/api/agents/research/stream",
            json={"prompt": "Osaka itinerary", "locale": "en"},
            headers=HEADERS,
        )
    assert r_emp.status_code == 200
    assert "Tier 2 After Empty" in r_emp.text

    # 3. Linear O(n) ReDoS safety on 30KB adversarial workspace dead-link payload
    hostile = ("[a](file:///workspace/" + "x" * 200 + ") ") * 150
    t0 = time.perf_counter()
    sanitized = agents_router._sanitize_antigravity_markdown(hostile)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert "file:///workspace/" not in sanitized.lower()
    assert elapsed_ms < 50.0, f"Workspace sanitizer too slow: {elapsed_ms:.2f}ms"

