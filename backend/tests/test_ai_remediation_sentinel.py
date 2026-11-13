# -*- coding: utf-8 -*-
"""
AI Systemic Remediation Sentinel Suite
======================================
Comprehensive regression tests covering:
1. Gemini 3.x / Gemma 4 ThinkingConfig, AFC disable, and Gemma 4 31B blind spot
2. Thought-only empty output rejection across call_extraction / call_with_fallback / call_verifier
3. Transient 5xx single retry & 400 config_unsupported in-place self-healing
4. Schema contract alignment (PARSE_MD, PLANNING, EXTRACTION, MEMORY_EXTRACT) & parse_receipt backfill
5. DAY_REVIEW 0 tools + refuses empty DB write
6. SSE stream_chat_generator: Stage 2 CHAT tool unloading, single SEARCH prefetch, event: reset, empty-stream 503 error
7. Agents fallback 401 fail-fast & empty guard
8. IntentRouter / SmartSearch per-model call_timeout_scope fallback
9. Geocode service _gemma_parse_address / None-safe guards & Limiter dual header keys
10. /api/ai/test-key 401/429/503/400 status discrimination & POI/Main HTTP exception mapping
"""

import asyncio
import base64
import hashlib
import io
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors
from google.genai import types
from PIL import Image
from starlette.requests import Request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main as backend_main
from main import app
from routers import agents as agents_router
from services import geocode_service, model_manager
from utils.deps import get_gemini_key, get_supabase, get_verified_user
from utils.limiter import get_rate_limit_key


client = TestClient(app)


def _make_api_error(code: int, message: str) -> genai_errors.APIError:
    return genai_errors.APIError(code, {"error": {"message": message}})


def _make_thought_only_response(thought_text: str = "Thinking deeply...", finish_reason: str = "MAX_TOKENS"):
    part = types.Part(thought=True, text=thought_text)
    cand = types.Candidate(content=types.Content(role="model", parts=[part]), finish_reason=finish_reason)
    return types.GenerateContentResponse(candidates=[cand])


def _make_text_response(visible_text: str):
    part = types.Part.from_text(text=visible_text)
    cand = types.Candidate(content=types.Content(role="model", parts=[part]), finish_reason="STOP")
    return types.GenerateContentResponse(candidates=[cand])


def _dummy_jpeg_data_url() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color=(255, 255, 255)).save(buf, format="JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.fixture(autouse=True)
def _reset_ai_state():
    model_manager.__reset_client_cache_for_testing()
    model_manager._CIRCUIT_STATE.clear()
    agents_router.__reset_fallback_tasks_for_testing()
    yield
    model_manager.__reset_client_cache_for_testing()
    model_manager._CIRCUIT_STATE.clear()
    agents_router.__reset_fallback_tasks_for_testing()


# ==============================================================================
# 1. Thinking Config, Gemma 4 Compatibility & AFC Disable
# ==============================================================================

def test_generation_configs_and_gemma_thinking_sanitization():
    # PLANNING: 32768 + MEDIUM + AFC disabled
    plan_cfg = model_manager.get_generation_config("PLANNING")
    assert plan_cfg.max_output_tokens == 32768
    assert plan_cfg.automatic_function_calling is not None
    assert plan_cfg.automatic_function_calling.disable is True
    assert plan_cfg.thinking_config is not None
    assert plan_cfg.thinking_config.thinking_level == types.ThinkingLevel.MEDIUM
    assert plan_cfg.thinking_config.thinking_budget is None
    assert plan_cfg.thinking_config.include_thoughts is False

    # PARSE_MD: 32768 + LOW + JSON
    md_cfg = model_manager.get_generation_config("PARSE_MD")
    assert md_cfg.max_output_tokens == 32768
    assert md_cfg.response_mime_type == "application/json"
    assert md_cfg.thinking_config.thinking_level == types.ThinkingLevel.LOW

    # POI_ENRICH (JSON, 1024) vs POI_RECOMMEND (prose, 1024)
    enrich_cfg = model_manager.get_generation_config("POI_ENRICH")
    rec_cfg = model_manager.get_generation_config("POI_RECOMMEND")
    assert enrich_cfg.max_output_tokens == 1024
    assert enrich_cfg.response_mime_type == "application/json"
    assert rec_cfg.max_output_tokens == 1024
    assert rec_cfg.response_mime_type is None

    # DAY_REVIEW: 0 tools
    review_cfg = model_manager.get_generation_config("DAY_REVIEW")
    assert not review_cfg.tools
    assert review_cfg.max_output_tokens == 8192

    # Gemma 4 31B blind spot: None thinking_config MUST become MINIMAL + include_thoughts=False
    bare_cfg = types.GenerateContentConfig(max_output_tokens=512)
    sanitized_31b = model_manager.sanitize_config_for_model(bare_cfg, "gemma-4-31b-it", intent_type="GEOCODE")
    assert sanitized_31b.thinking_config is not None
    assert sanitized_31b.thinking_config.thinking_level == types.ThinkingLevel.MINIMAL
    assert sanitized_31b.thinking_config.include_thoughts is False
    assert sanitized_31b.automatic_function_calling.disable is True

    # Gemma 4 31B maps MEDIUM -> MINIMAL
    sanitized_31b_med = model_manager.sanitize_config_for_model(plan_cfg, "gemma-4-31b-it", intent_type="PLANNING")
    assert sanitized_31b_med.thinking_config.thinking_level == types.ThinkingLevel.MINIMAL

    # Gemma 4 26B matches live API thinking=True (minimal/high) and maps MEDIUM -> MINIMAL
    sanitized_26b_med = model_manager.sanitize_config_for_model(plan_cfg, "gemma-4-26b-a4b-it", intent_type="PLANNING")
    assert sanitized_26b_med.thinking_config is not None
    assert sanitized_26b_med.thinking_config.thinking_level == types.ThinkingLevel.MINIMAL
    assert sanitized_26b_med.thinking_config.include_thoughts is False

    # Gemini 2.5 Flash disables default -1 dynamic thinking via thinking_budget=0 when suppressed
    extract_cfg = model_manager.get_generation_config("EXTRACTION")
    sanitized_25_extract = model_manager.sanitize_config_for_model(extract_cfg, "gemini-2.5-flash", intent_type="EXTRACTION")
    assert sanitized_25_extract.thinking_config is not None
    assert sanitized_25_extract.thinking_config.thinking_budget == 0
    assert sanitized_25_extract.thinking_config.include_thoughts is False
    assert getattr(sanitized_25_extract.thinking_config, "thinking_level", None) is None

    # Non-thinking model clears thinking_config to None
    s_g3 = model_manager.sanitize_config_for_model(plan_cfg, "gemma-3-27b-it", intent_type="PLANNING")
    assert s_g3.thinking_config is None

    # Gemini 3.x strips stale thinking_budget
    legacy_cfg = types.GenerateContentConfig(
        max_output_tokens=1024,
        thinking_config=types.ThinkingConfig(thinking_budget=256),
    )
    sanitized_g3 = model_manager.sanitize_config_for_model(legacy_cfg, "gemini-3.5-flash-lite", intent_type="INTENT_PARSE")
    assert sanitized_g3.thinking_config is not None
    assert sanitized_g3.thinking_config.thinking_budget is None
    assert sanitized_g3.thinking_config.thinking_level == types.ThinkingLevel.MINIMAL


def test_tool_required_routing_excludes_toolless_models():
    routing = model_manager.build_effective_routing("ITINERARY", ["gemini-3-flash-preview", "gemini-3.6-flash"])
    assert "gemini-3.6-flash" in routing
    assert "gemini-3-flash-preview" not in routing


# ==============================================================================
# 2. Thought-Only Empty Rejection & 5xx/400 Self-Heal Retries
# ==============================================================================

@pytest.mark.asyncio
async def test_call_extraction_rejects_thought_only_empty_on_prose_intent():
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(side_effect=[
        _make_thought_only_response(),
        _make_text_response("Concise trip recap"),
    ])

    with patch.object(model_manager, "get_cached_client", return_value=mock_client):
        res = await model_manager.call_extraction(
            "AIzaSyTestEmptyExtraction1234567890",
            "Summarize chat",
            intent_type="SUMMARIZE",
            routing_strategy=["gemini-3.5-flash-lite", "gemini-3.6-flash"],
        )

    assert res == "Concise trip recap"
    assert mock_client.aio.models.generate_content.await_count == 2


@pytest.mark.asyncio
async def test_call_with_fallback_rejects_thought_only_empty_response():
    chat_empty = MagicMock()
    chat_empty.send_message = AsyncMock(return_value=_make_thought_only_response())
    chat_ok = MagicMock()
    chat_ok.send_message = AsyncMock(return_value=_make_text_response("Try Senso-ji in the morning!"))

    mock_client = MagicMock()
    mock_client.aio.chats.create = MagicMock(side_effect=[chat_empty, chat_ok])

    with patch.object(model_manager, "get_cached_client", return_value=mock_client):
        res = await model_manager.call_with_fallback(
            api_key="AIzaSyTestEmptyChat1234567890123",
            history=[],
            message="What should I do in Tokyo?",
            intent_type="CHAT",
            routing_strategy=["gemini-3.5-flash-lite", "gemini-3.6-flash"],
        )

    assert res["text"] == "Try Senso-ji in the morning!"
    assert res["model_used"] == "gemini-3.6-flash"


@pytest.mark.asyncio
async def test_call_verifier_rejects_empty_and_retries_transient_503():
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(side_effect=[
        _make_api_error(503, "503 Service Unavailable"),
        _make_thought_only_response(),
        _make_text_response("Verified OK"),
    ])

    with patch.object(model_manager, "get_cached_client", return_value=mock_client), \
         patch.object(model_manager.asyncio, "sleep", AsyncMock()):
        res = await model_manager.call_verifier(
            "AIzaSyTestVerifierRetry" + "0" * 18,
            poi_data={"name": "Ichiran Ramen", "address": "Shinjuku"},
            query="Ichiran Shinjuku",
            routing_strategy=["gemini-3.5-flash-lite", "gemini-3.6-flash"],
        )

    assert res["verified_data"] == "Verified OK"
    assert mock_client.aio.models.generate_content.await_count == 3
    assert mock_client.aio.models.generate_content.await_args_list[-1].kwargs["model"] == "gemini-3.6-flash"


@pytest.mark.asyncio
async def test_call_extraction_transient_503_retry_and_400_config_self_heal():
    assert model_manager.classify_api_error(_make_api_error(400, "Invalid thinking_level parameter")) == "config_unsupported"

    captured_configs = []

    async def fake_generate_content(*, model, contents, config):
        captured_configs.append(config)
        if len(captured_configs) == 1:
            raise _make_api_error(400, "thinking_level is not supported for this model")
        if len(captured_configs) == 2:
            raise _make_api_error(503, "503 Overloaded")
        return _make_text_response('{"intent": "search"}')

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = fake_generate_content

    with patch.object(model_manager, "get_cached_client", return_value=mock_client), \
         patch.object(model_manager.asyncio, "sleep", AsyncMock()):
        out = await model_manager.call_extraction(
            "AIzaSyTestSelfHeal400_1234567890",
            "Find ramen",
            intent_type="INTENT_PARSE",
            routing_strategy=["gemini-3.5-flash-lite"],
        )

    assert json.loads(out)["intent"] == "search"
    assert len(captured_configs) == 3
    assert captured_configs[0].thinking_config is not None
    assert captured_configs[1].thinking_config is None
    assert captured_configs[2].thinking_config is None


# ==============================================================================
# 3. Schema Contracts, parse-receipt & day-review Guards
# ==============================================================================

def test_json_schemas_include_required_domain_fields():
    planning = model_manager.build_json_schema_for_intent("PLANNING")
    assert "destination" in planning["properties"]
    assert "currency" in planning["properties"]
    note_props = planning["properties"]["day_metadata"]["items"]["properties"]["notes"]["items"]["properties"]
    for key in ("icon", "title", "item", "content"):
        assert key in note_props

    parse_md = model_manager.build_json_schema_for_intent("PARSE_MD")
    for key in ("title", "destination", "start_date", "end_date", "items", "day_metadata", "ai_review"):
        assert key in parse_md["properties"]

    extraction = model_manager.build_json_schema_for_intent("EXTRACTION")
    for key in ("expense_date", "date", "notes", "diagnostics"):
        assert key in extraction["properties"]


def test_parse_receipt_backfills_expense_date_and_maps_auth_errors():
    headers = {"X-Gemini-API-Key": "AIzaSyParseReceiptTestKey" + "1" * 16}
    payload = {"image": _dummy_jpeg_data_url(), "locale": "zh"}

    ai_json = json.dumps({
        "title": "Lawson Tokyo",
        "date": "2026-11-11",
        "currency": "JPY",
        "total_amount": 680.0,
        "subtotal_amount": 680.0,
        "items": [{"original_name": "Onigiri", "translated_name": "飯糰", "amount": 680.0}],
        "notes": "Morning snack",
        "diagnostics": {"status": "warning", "message": "Receipt slightly blurred"},
    })

    with patch("routers.ai.call_extraction", new_callable=AsyncMock, return_value=ai_json):
        res = client.post("/api/ai/parse-receipt", json=payload, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["expense_date"] == "2026-11-11"
    assert body["notes"] == "Morning snack"
    assert body["currency"] == "JPY"
    assert body["diagnostics"]["status"] == "warning"
    assert "blurred" in body["diagnostics"]["message"]

    headers_auth = {"X-Gemini-API-Key": "AIzaSyParseReceiptTestKey" + "2" * 16}
    with patch("routers.ai.call_extraction", new_callable=AsyncMock, side_effect=model_manager.NonRetryableAuthError("bad key")):
        res_401 = client.post("/api/ai/parse-receipt", json=payload, headers=headers_auth)
    assert res_401.status_code == 401

    headers_503 = {"X-Gemini-API-Key": "AIzaSyParseReceiptTestKey" + "3" * 16}
    with patch("routers.ai.call_extraction", new_callable=AsyncMock, side_effect=model_manager.AllModelsFailedError("down")):
        res_503 = client.post("/api/ai/parse-receipt", json=payload, headers=headers_503)
    assert res_503.status_code == 503


def test_day_review_blocks_empty_response_before_db_write():
    mock_sb = MagicMock()
    itinerary_exec = MagicMock(data=[{"created_by": "owner-1", "title": "Hokkaido Trip", "start_date": "2026-11-10"}])
    items_exec = MagicMock(data=[{
        "place_name": "Sapporo Station",
        "category": "transport",
        "start_time": "09:00",
        "time_slot": "09:00",
        "notes": None,
    }])
    notes_exec = MagicMock(data=[])
    members_exec = MagicMock(data=[])

    def table_side_effect(name: str):
        tbl = MagicMock()
        tbl.select.return_value = tbl
        tbl.eq.return_value = tbl
        tbl.order.return_value = tbl
        tbl.update.return_value = tbl
        if name == "itineraries":
            tbl.execute.return_value = itinerary_exec
        elif name == "itinerary_items":
            tbl.execute.return_value = items_exec
        elif name == "trip_members":
            tbl.execute.return_value = members_exec
        else:
            tbl.execute.return_value = notes_exec
        return tbl

    mock_sb.table.side_effect = table_side_effect
    update_tracker = MagicMock()
    mock_sb._update_tracker = update_tracker

    orig_table = mock_sb.table.side_effect

    def tracked_table(name: str):
        tbl = orig_table(name)
        if name == "trip_day_notes":
            tbl.update.side_effect = update_tracker
        return tbl

    mock_sb.table.side_effect = tracked_table

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: "owner-1"
    app.dependency_overrides[get_gemini_key] = lambda: "AIzaSyDayReviewEmptyGuard1234567"
    try:
        with patch("routers.ai.call_extraction", new_callable=AsyncMock, return_value="   "):
            res = client.post("/api/ai/trips/trip-1/days/1/ai-review?locale=zh")
        assert res.status_code == 503
        assert update_tracker.call_count == 0
    finally:
        app.dependency_overrides.pop(get_supabase, None)
        app.dependency_overrides.pop(get_verified_user, None)
        app.dependency_overrides.pop(get_gemini_key, None)


# ==============================================================================
# 4. Streaming Chat: Stage 2 CHAT Unload, Single Search Prefetch, Reset & Error
# ==============================================================================

class _ChunkStream:
    def __init__(self, items):
        self._items = items

    def __aiter__(self):
        self._it = iter(self._items)
        return self

    async def __anext__(self):
        try:
            item = next(self._it)
        except StopIteration:
            raise StopAsyncIteration
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.mark.asyncio
async def test_stream_chat_long_plain_chat_unloads_tools():
    captured_configs = []

    async def fake_stream(*, model, contents, config):
        captured_configs.append(config)
        return _ChunkStream([_make_text_response("Of course! I can share general travel tips.")])

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = fake_stream

    long_chat = "I really enjoy slow mornings when I travel around East Asia and just want to chat casually today."
    with patch.object(backend_main.genai, "Client", return_value=mock_client), \
         patch.object(backend_main, "classify_chat_intent", AsyncMock(return_value=("CHAT", []))):
        events = []
        async for ev in backend_main.stream_chat_generator(
            api_key="AIzaSyStreamChatUnload1234567890",
            history=[],
            message=long_chat,
            raw_user_message=long_chat,
            locale="en",
        ):
            events.append(ev)

    assert len(captured_configs) == 1
    assert captured_configs[0].tools is None
    assert "Of course! I can share general travel tips." in "".join(events)


@pytest.mark.asyncio
async def test_stream_chat_search_prefetches_once_and_emits_reset_on_midstream_fallback():
    stream_calls = 0

    async def fake_stream(*, model, contents, config):
        nonlocal stream_calls
        stream_calls += 1
        if stream_calls == 1:
            return _ChunkStream([
                _make_text_response("Here is a long partial Tokyo recommendation text that exceeds the 30-char lookahead window... "),
                _make_api_error(503, "503 stream dropped mid-turn"),
            ])
        return _ChunkStream([
            _make_text_response("Recommended ramen spot in Shinjuku[1]."),
        ])

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = fake_stream
    mock_search = AsyncMock(return_value=[
        {"title": "Shinjuku Ramen Guide", "url": "https://tabelog.com/tokyo/ramen", "snippet": "Open 11:00-22:00"},
    ])

    with patch.object(backend_main.genai, "Client", return_value=mock_client), \
         patch.object(backend_main, "classify_chat_intent", AsyncMock(return_value=("SEARCH", model_manager.ALL_CHAT_TOOLS))), \
         patch.object(backend_main, "execute_web_search", mock_search), \
         patch.object(backend_main, "build_effective_routing", return_value=["gemini-3.5-flash-lite", "gemini-3.6-flash"]):
        events = []
        async for ev in backend_main.stream_chat_generator(
            api_key="AIzaSyStreamResetMidstream12345",
            history=[],
            message="Search best ramen in Shinjuku",
            raw_user_message="Search best ramen in Shinjuku",
            locale="en",
        ):
            events.append(ev)

    joined = "".join(events)
    assert mock_search.await_count == 1
    assert "event: reset" in joined
    assert "event: done" in joined
    done_line = [blk for blk in events if blk.startswith("event: done")][0]
    done_payload = json.loads(done_line.split("data:", 1)[1].strip())
    assert done_payload["raw_parts"][0]["text"] == "Recommended ramen spot in Shinjuku[1]."
    assert "Here is a long partial Tokyo" not in done_payload["raw_parts"][0]["text"]


@pytest.mark.asyncio
async def test_stream_chat_thought_only_all_models_emits_503_error_not_canned_greeting():
    async def fake_stream(*, model, contents, config):
        return _ChunkStream([_make_thought_only_response()])

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = fake_stream

    with patch.object(backend_main.genai, "Client", return_value=mock_client), \
         patch.object(backend_main, "classify_chat_intent", AsyncMock(return_value=("CHAT", []))), \
         patch.object(backend_main, "build_effective_routing", return_value=["gemini-3.5-flash-lite", "gemini-3.6-flash"]):
        events = []
        async for ev in backend_main.stream_chat_generator(
            api_key="AIzaSyStreamEmptyAll5031234567",
            history=[],
            message="Tell me something",
            raw_user_message="Tell me something",
            locale="zh",
        ):
            events.append(ev)

    joined = "".join(events)
    assert "收到！有什麼我可以幫忙的嗎？" not in joined
    assert "event: error" in joined
    assert '"code": 503' in joined


# ==============================================================================
# 5. Agents Fallback, Intent/SmartSearch Per-Model Timeout, Geocode, Limiter, TestKey & POI
# ==============================================================================

@pytest.mark.asyncio
async def test_agents_fallback_401_fails_fast_and_empty_falls_back():
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(side_effect=_make_api_error(401, "API_KEY_INVALID"))

    with patch("routers.agents.genai.Client", return_value=mock_client):
        await agents_router._execute_flash_fallback_task("fallback_401", "Compare flights", "AIzaSyBadKey", locale="en")

    assert agents_router._FALLBACK_TASKS["fallback_401"]["status"] == "failed"
    assert agents_router._FALLBACK_TASKS["fallback_401"]["code"] == 401
    assert mock_client.aio.models.generate_content.await_count == 1

    mock_client_empty = MagicMock()
    mock_client_empty.aio.models.generate_content = AsyncMock(side_effect=[
        _make_thought_only_response(),
        _make_text_response("# Fallback Research Report"),
    ])

    with patch("routers.agents.genai.Client", return_value=mock_client_empty), \
         patch("routers.agents.build_effective_routing", return_value=["gemini-3.7-flash", "gemini-3.6-flash"]):
        await agents_router._execute_flash_fallback_task("fallback_empty", "Plan Hokkaido", "AIzaSyGoodKey", locale="en")

    assert agents_router._FALLBACK_TASKS["fallback_empty"]["status"] == "completed"
    assert "Fallback Research Report" in agents_router._FALLBACK_TASKS["fallback_empty"]["output_text"]


@pytest.mark.asyncio
async def test_intent_router_and_smart_search_per_model_timeout_slides_to_fallback():
    from services.intent_router import _workhorse_classify
    from services.smart_search_service import parse_intent

    call_idx = 0

    async def slow_then_fast(*, model, contents, config):
        nonlocal call_idx
        call_idx += 1
        if call_idx % 2 == 1:
            await asyncio.sleep(2.5)
            return _make_text_response("{}")
        return _make_text_response('{"intent": "itinerary", "intent_type": "nearby", "category": "restaurant"}')

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = slow_then_fast

    with patch.object(model_manager, "get_cached_client", return_value=mock_client), \
         patch.object(model_manager, "build_effective_routing", return_value=["gemini-3.5-flash-lite", "gemini-3.6-flash"]):
        intent = await _workhorse_classify("幫我想想明天東京要去哪", api_key="AIzaSyIntentTimeoutTest123456")
        assert intent == "ITINERARY"

        parsed = await parse_intent("AIzaSySmartTimeoutTest1234567", "nearby ramen", region="Tokyo", locale="en")
        assert parsed["category"] == "restaurant"


@pytest.mark.asyncio
async def test_geocode_ai_helpers_handle_none_and_empty_safely():
    with patch.object(geocode_service, "call_extraction_server", new_callable=AsyncMock, return_value=None):
        assert await geocode_service._gemma_parse_address("Tokyo Station", user_key="AIzaSyGeo" + "0" * 31) == {}
        assert await geocode_service.detect_country_from_trip_title("Tokyo 5 Days", api_key="AIzaSyGeo" + "0" * 31) is None
        assert await geocode_service.detect_country_from_query("Senso-ji", api_key="AIzaSyGeo" + "0" * 31) is None
        assert await geocode_service.translate_place_name("淺草寺", "JP", api_key="AIzaSyGeo" + "0" * 31) == ["淺草寺"]

    with patch.object(geocode_service, "reverse_geocode_with_photon", new_callable=AsyncMock, return_value={"name": "Tokyo", "address": "Chiyoda"}), \
         patch.object(geocode_service, "call_extraction_server", new_callable=AsyncMock, return_value=None):
        rev = await geocode_service.reverse_geocode_with_ai_enhancement(35.68, 139.76, api_key="AIzaSyGeo" + "0" * 31)
        assert rev["name"] == "Tokyo"


def test_limiter_accepts_both_gemini_key_headers():
    key = "AIzaSyDualHeaderRateLimit123456"
    expected = "key:" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    req_std = Request({"type": "http", "headers": [(b"x-gemini-api-key", key.encode("utf-8"))]})
    req_alt = Request({"type": "http", "headers": [(b"x-gemini-key", key.encode("utf-8"))]})
    assert get_rate_limit_key(req_std) == expected
    assert get_rate_limit_key(req_alt) == expected


def test_ai_test_key_status_codes_and_400_self_heal():
    mock_client = MagicMock()

    mock_client.aio.models.generate_content = AsyncMock(side_effect=_make_api_error(401, "API key not valid"))
    with patch("main.genai.Client", return_value=mock_client):
        r401 = client.post("/api/ai/test-key", headers={"X-Gemini-API-Key": "AIzaSyTestKey401_" + "1" * 24})
    assert r401.status_code == 401

    mock_client.aio.models.generate_content = AsyncMock(side_effect=_make_api_error(429, "Resource exhausted"))
    with patch("main.genai.Client", return_value=mock_client):
        r429 = client.post("/api/ai/test-key", headers={"X-Gemini-API-Key": "AIzaSyTestKey429_" + "2" * 24})
    assert r429.status_code == 429

    mock_client.aio.models.generate_content = AsyncMock(side_effect=_make_api_error(503, "Service Unavailable"))
    with patch("main.genai.Client", return_value=mock_client):
        r503 = client.post("/api/ai/test-key", headers={"X-Gemini-API-Key": "AIzaSyTestKey503_" + "3" * 24})
    assert r503.status_code == 503

    mock_client.aio.models.generate_content = AsyncMock(side_effect=[
        _make_api_error(400, "thinking_level not supported"),
        _make_text_response("pong"),
    ])
    with patch("main.genai.Client", return_value=mock_client):
        r200 = client.post("/api/ai/test-key", headers={"X-Gemini-API-Key": "AIzaSyTestKey400_" + "4" * 24})
    assert r200.status_code == 200
    assert r200.json()["status"] == "ok"


def test_poi_recommend_uses_prose_intent_and_maps_errors():
    payload = {
        "api_key": "AIzaSyPoiRecommendTestKey" + "5" * 16,
        "pois": [{"name": "Ichiran", "category": "restaurant", "lat": 35.6, "lng": 139.7}],
        "user_query": "best ramen",
        "locale": "en",
    }
    with patch("services.model_manager.call_extraction", new_callable=AsyncMock, return_value="Ichiran is great for solo diners.") as mock_ext:
        ok = client.post("/api/poi/recommend", json=payload)
    assert ok.status_code == 200
    assert mock_ext.call_args.kwargs["intent_type"] == "POI_RECOMMEND"

    with patch("services.model_manager.call_extraction", new_callable=AsyncMock, return_value="   "):
        empty_res = client.post("/api/poi/recommend", json=payload)
    assert empty_res.status_code == 503

    with patch("services.model_manager.call_extraction", new_callable=AsyncMock, side_effect=model_manager.NonRetryableAuthError("bad key")):
        auth_res = client.post("/api/poi/recommend", json=payload)
    assert auth_res.status_code == 401


@pytest.mark.asyncio
async def test_stream_chat_lazy_anext_400_self_heal_and_503_retry():
    captured_400_configs = []

    async def fake_stream_400(*, model, contents, config):
        captured_400_configs.append(config)
        if len(captured_400_configs) == 1:
            return _ChunkStream([_make_api_error(400, "thinking_level is not supported")])
        return _ChunkStream([_make_text_response("Healed lazy stream response.")])

    mock_client_400 = MagicMock()
    mock_client_400.aio.models.generate_content_stream = fake_stream_400

    with patch.object(backend_main.genai, "Client", return_value=mock_client_400), \
         patch.object(backend_main, "classify_chat_intent", AsyncMock(return_value=("CHAT", []))), \
         patch.object(backend_main, "build_effective_routing", return_value=["gemini-3.5-flash-lite", "gemini-3.6-flash"]):
        events = []
        async for ev in backend_main.stream_chat_generator(
            api_key="AIzaSyStreamLazy400Heal12345678",
            history=[],
            message="Hello lazy 400",
            raw_user_message="Hello lazy 400",
            locale="en",
        ):
            events.append(ev)

    joined_400 = "".join(events)
    assert len(captured_400_configs) == 2
    assert captured_400_configs[0].thinking_config is not None
    assert captured_400_configs[1].thinking_config is None
    assert "Healed lazy stream response." in joined_400
    assert "event: done" in joined_400

    stream_503_calls = 0

    async def fake_stream_503(*, model, contents, config):
        nonlocal stream_503_calls
        stream_503_calls += 1
        if stream_503_calls == 1:
            return _ChunkStream([_make_api_error(503, "Service Unavailable")])
        return _ChunkStream([_make_text_response("Recovered after lazy 503 retry.")])

    mock_client_503 = MagicMock()
    mock_client_503.aio.models.generate_content_stream = fake_stream_503

    with patch.object(backend_main.genai, "Client", return_value=mock_client_503), \
         patch.object(backend_main, "classify_chat_intent", AsyncMock(return_value=("CHAT", []))), \
         patch.object(backend_main, "build_effective_routing", return_value=["gemini-3.5-flash-lite"]), \
         patch("main.asyncio.sleep", new_callable=AsyncMock):
        events_503 = []
        async for ev in backend_main.stream_chat_generator(
            api_key="AIzaSyStreamLazy503Retry1234567",
            history=[],
            message="Hello lazy 503",
            raw_user_message="Hello lazy 503",
            locale="en",
        ):
            events_503.append(ev)

    assert stream_503_calls == 2
    assert "Recovered after lazy 503 retry." in "".join(events_503)


@pytest.mark.asyncio
async def test_stream_chat_non_config_400_bad_request_fails_fast():
    called_models = []

    async def fake_stream_bad(*, model, contents, config):
        called_models.append(model)
        return _ChunkStream([_make_api_error(400, "Invalid image attachment encoding")])

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = fake_stream_bad

    with patch.object(backend_main.genai, "Client", return_value=mock_client), \
         patch.object(backend_main, "classify_chat_intent", AsyncMock(return_value=("CHAT", []))), \
         patch.object(backend_main, "build_effective_routing", return_value=["gemini-3.5-flash-lite", "gemini-3.6-flash"]):
        events = []
        async for ev in backend_main.stream_chat_generator(
            api_key="AIzaSyStreamBadReq400_12345678",
            history=[],
            message="Hello bad attachment",
            raw_user_message="Hello bad attachment",
            locale="en",
        ):
            events.append(ev)

    joined = "".join(events)
    assert called_models == ["gemini-3.5-flash-lite"]
    assert "event: error" in joined
    assert '"code": 400' in joined


def test_api_chat_function_calls_with_empty_text_synthesizes_non_empty_response():
    mock_result = {
        "text": "",
        "raw_parts": [
            {"functionCall": {"name": "add_expense", "args": {"title": "Ichiran Ramen", "amount": 1200, "currency": "JPY"}}}
        ],
        "model_used": "gemini-3.5-flash-lite",
        "grounding_metadata": None,
    }
    had_supa = hasattr(app.state, "supabase")
    orig_supa = getattr(app.state, "supabase", None)
    if had_supa:
        delattr(app.state, "supabase")
    app.dependency_overrides[get_verified_user] = lambda: "test-user-1"
    app.dependency_overrides[get_gemini_key] = lambda: "AIzaSyChatEmptyFCTest1234567890"
    try:
        with patch.object(backend_main, "classify_chat_intent", AsyncMock(return_value=("EXPENSE", model_manager.ALL_CHAT_TOOLS))), \
             patch.object(backend_main, "call_with_fallback", AsyncMock(return_value=mock_result)):
            res = client.post(
                "/api/chat",
                json={"message": "Record 1200 JPY ramen", "history": [], "locale": "en"},
                headers={"X-Gemini-API-Key": "AIzaSyChatEmptyFCTest1234567890"},
            )
    finally:
        app.dependency_overrides.pop(get_verified_user, None)
        app.dependency_overrides.pop(get_gemini_key, None)
        if had_supa:
            app.state.supabase = orig_supa

    assert res.status_code == 200
    body = res.json()
    assert body["response"].strip() != ""
    assert "Ichiran Ramen" in body["response"]


@pytest.mark.asyncio
async def test_workhorse_classify_survives_slow_503_retry_and_falls_back():
    from services.intent_router import _workhorse_classify

    async def slow_503_then_fast(*, model, contents, config):
        if model == "gemini-3.5-flash-lite":
            await asyncio.sleep(0.55)
            raise _make_api_error(503, "Primary overloaded")
        await asyncio.sleep(0.05)
        return _make_text_response('{"intent": "itinerary"}')

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = slow_503_then_fast

    with patch.object(model_manager, "get_cached_client", return_value=mock_client), \
         patch.object(model_manager, "build_effective_routing", return_value=["gemini-3.5-flash-lite", "gemini-3.6-flash"]):
        intent = await _workhorse_classify("幫我把清水寺排進明天行程", api_key="AIzaSyWorkhorse503Slow123456")

    assert intent == "ITINERARY"


@pytest.mark.asyncio
async def test_call_verifier_raises_all_models_failed_and_sanitize_guards_unlisted_models():
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(side_effect=_make_api_error(503, "All busy"))

    with patch.object(model_manager, "get_cached_client", return_value=mock_client), \
         patch.object(model_manager, "build_effective_routing", return_value=["gemini-3.5-flash-lite", "gemini-3.6-flash"]), \
         patch("services.model_manager.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(model_manager.AllModelsFailedError) as exc_info:
            await model_manager.call_verifier("AIzaSyVerifierFail503_12345678", {"place_name": "Kiyomizu-dera"}, "open hours")
    assert len(exc_info.value.attempts) == 2

    cfg_high_budget = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="high", thinking_budget=2048),
    )
    sanitized_g3_high = model_manager.sanitize_config_for_model(cfg_high_budget, "gemini-3.9-flash", "GEOCODE")
    assert sanitized_g3_high.thinking_config is not None
    assert sanitized_g3_high.thinking_config.thinking_budget is None
    assert str(sanitized_g3_high.thinking_config.thinking_level).lower().endswith("minimal")

    cfg_low_budget = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="low", thinking_budget=2048),
    )
    sanitized_g3_low = model_manager.sanitize_config_for_model(cfg_low_budget, "gemini-3.9-flash", "GEOCODE")
    assert sanitized_g3_low.thinking_config is not None
    assert sanitized_g3_low.thinking_config.thinking_budget is None
    assert str(sanitized_g3_low.thinking_config.thinking_level).lower().endswith("low")

    cfg_3 = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="low"),
    )
    sanitized_25 = model_manager.sanitize_config_for_model(cfg_3, "gemini-2.5-pro", "EXTRACTION")
    assert sanitized_25.thinking_config is not None
    assert sanitized_25.thinking_config.thinking_level is None
    assert sanitized_25.thinking_config.thinking_budget == 0


@pytest.mark.asyncio
async def test_detect_country_uses_module_mock_and_geocode_search_accepts_api_key_header():
    with patch.object(geocode_service, "call_extraction_server", new_callable=AsyncMock, return_value="JP.") as mock_ext:
        code = await geocode_service.detect_country_from_trip_title("Hokkaido 5 Days", api_key="AIzaSyGeoModuleMock123456")
    assert code == "JP"
    assert mock_ext.await_count == 1

    captured_keys = []

    async def fake_smart_geo(query, limit, trip_title, user_key, *args, **kwargs):
        captured_keys.append(user_key)
        return []

    from routers import geocode as geocode_router
    with patch.object(geocode_router, "smart_geocode_logic", side_effect=fake_smart_geo):
        res = client.post(
            "/api/geocode/search",
            json={"query": "Tokyo Station", "limit": 5, "locale": "en"},
            headers={"X-Gemini-API-Key": "AIzaSyAltGeoHeader123456789012"},
        )
    assert res.status_code == 200
    assert captured_keys == ["AIzaSyAltGeoHeader123456789012"]

