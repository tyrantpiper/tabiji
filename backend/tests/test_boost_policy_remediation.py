# -*- coding: utf-8 -*-
"""
Regression test suite for /boost live AQ. probing & 2026 Google Gemini/Agents remediation.
"""

import asyncio
import inspect
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors
from google.genai import types
from google.genai._gaos.lib import compat_errors

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routers import agents as agents_router
from routers import ai as ai_router
from services import model_manager
from utils import ai_config


AQ_TEST_KEY = "AQ.Ab8RN6BoostRegressionTestKey12345678901234567890"


def _make_compat_status_error(status_code: int, message: str = "compat api error"):
    req = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/interactions")
    resp = httpx.Response(status_code, request=req, json={"error": {"message": message}})
    return compat_errors.APIError.generate(
        status_code=status_code,
        body={"error": {"message": message}},
        message=message,
        response=resp,
    )


def _make_genai_api_error(code: int, message: str) -> genai_errors.APIError:
    err = genai_errors.APIError.__new__(genai_errors.APIError)
    Exception.__init__(err, message)
    err.code = code
    err.message = message
    err.status = None
    err.details = None
    return err


def _make_thought_only_response():
    part = types.Part(text="hidden chain of thought", thought=True)
    content = types.Content(role="model", parts=[part])
    cand = types.Candidate(content=content, finish_reason="STOP")
    return types.GenerateContentResponse(candidates=[cand])


@pytest.fixture(autouse=True)
def _clean_singletons():
    agents_router.__reset_fallback_tasks_for_testing()
    model_manager.__reset_client_cache_for_testing()
    model_manager._CIRCUIT_STATE.clear()
    yield
    agents_router.__reset_fallback_tasks_for_testing()
    model_manager.__reset_client_cache_for_testing()
    model_manager._CIRCUIT_STATE.clear()


def _build_agents_test_app() -> TestClient:
    app = FastAPI()
    app.include_router(agents_router.router)
    return TestClient(app)


# ==============================================================================
# 1. agents.py — compat_errors.APIStatusError handling & antigravity-preview-09-2026
# ==============================================================================


@pytest.mark.parametrize("status_code", [401, 403])
def test_agents_research_compat_auth_errors_return_401_not_200_fallback(status_code: int):
    compat_err = _make_compat_status_error(status_code, "API key invalid")
    assert not isinstance(compat_err, genai_errors.APIError)

    mock_client = MagicMock()
    mock_client.interactions.create.side_effect = compat_err

    client = _build_agents_test_app()
    with patch("routers.agents.genai.Client", return_value=mock_client):
        resp = client.post(
            "/api/agents/research",
            json={"prompt": "Tokyo 5-day autumn itinerary", "language": "en"},
            headers={"X-Gemini-API-Key": AQ_TEST_KEY},
        )

    assert resp.status_code == 401
    assert agents_router._FALLBACK_TASKS == {}


def test_agents_research_uses_antigravity_09_2026_and_falls_back_on_compat_404():
    compat_404 = _make_compat_status_error(404, "Agent not found")
    mock_client = MagicMock()
    mock_client.interactions.create.side_effect = compat_404

    client = _build_agents_test_app()
    with patch("routers.agents.genai.Client", return_value=mock_client), \
         patch("routers.agents._execute_flash_fallback_task", AsyncMock()):
        resp = client.post(
            "/api/agents/research",
            json={"prompt": "Kyoto hidden gems", "language": "zh"},
            headers={"X-Gemini-API-Key": AQ_TEST_KEY},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["engine"] == "gemini-3.7-flash-fallback"
    assert "Gemini 3.8 Flash" in data["message"]
    create_kwargs = mock_client.interactions.create.call_args.kwargs
    assert create_kwargs["agent"] == "antigravity-preview-09-2026"


@pytest.mark.parametrize(
    "upstream_status,expected_http",
    [
        (400, 400),
        (401, 401),
        (403, 401),
        (404, 404),
        (429, 429),
        (500, 503),
    ],
)
def test_agents_poll_and_cancel_map_compat_api_status_errors_cleanly(
    upstream_status: int, expected_http: int
):
    compat_err = _make_compat_status_error(upstream_status, f"upstream {upstream_status}")
    mock_client = MagicMock()
    mock_client.interactions.get.side_effect = compat_err
    mock_client.interactions.cancel.side_effect = compat_err

    client = _build_agents_test_app()
    with patch("routers.agents.genai.Client", return_value=mock_client):
        poll_resp = client.get(
            "/api/agents/interactions/int_nonexistent_123",
            headers={"X-Gemini-API-Key": AQ_TEST_KEY},
        )
        cancel_resp = client.post(
            "/api/agents/interactions/int_nonexistent_123/cancel",
            headers={"X-Gemini-API-Key": AQ_TEST_KEY},
        )

    assert poll_resp.status_code == expected_http
    assert cancel_resp.status_code == expected_http


def test_agents_poll_and_cancel_compat_bad_request_400_returns_400_not_503():
    compat_400 = _make_compat_status_error(400, "Invalid interaction name")
    assert isinstance(compat_400, compat_errors.APIStatusError)

    mock_client = MagicMock()
    mock_client.interactions.get.side_effect = compat_400
    mock_client.interactions.cancel.side_effect = compat_400

    client = _build_agents_test_app()
    with patch("routers.agents.genai.Client", return_value=mock_client):
        poll_resp = client.get(
            "/api/agents/interactions/fake_nonexistent_id_123",
            headers={"X-Gemini-API-Key": AQ_TEST_KEY},
        )
        cancel_resp = client.post(
            "/api/agents/interactions/fake_nonexistent_id_123/cancel",
            headers={"X-Gemini-API-Key": AQ_TEST_KEY},
        )

    assert poll_resp.status_code == 400
    assert poll_resp.json()["detail"] == "無效的任務請求: Invalid interaction name"
    assert cancel_resp.status_code == 400
    assert cancel_resp.json()["detail"] == "無效的取消請求: Invalid interaction name"

    # Auth failure reported as HTTP 400 (e.g. API key not valid) must still map to 401
    compat_400_auth = _make_compat_status_error(400, "API key not valid. Please pass a valid API key.")
    mock_client.interactions.get.side_effect = compat_400_auth
    mock_client.interactions.cancel.side_effect = compat_400_auth
    with patch("routers.agents.genai.Client", return_value=mock_client):
        auth_poll_resp = client.get(
            "/api/agents/interactions/fake_nonexistent_id_123",
            headers={"X-Gemini-API-Key": AQ_TEST_KEY},
        )
        auth_cancel_resp = client.post(
            "/api/agents/interactions/fake_nonexistent_id_123/cancel",
            headers={"X-Gemini-API-Key": AQ_TEST_KEY},
        )

    assert auth_poll_resp.status_code == 401
    assert auth_cancel_resp.status_code == 401

    # Standard genai_errors.APIError with code=400 also maps to 400
    genai_400 = _make_genai_api_error(400, "Malformed interaction resource name")
    mock_client.interactions.get.side_effect = genai_400
    mock_client.interactions.cancel.side_effect = genai_400
    with patch("routers.agents.genai.Client", return_value=mock_client):
        genai_poll_resp = client.get(
            "/api/agents/interactions/fake_nonexistent_id_123",
            headers={"X-Gemini-API-Key": AQ_TEST_KEY},
        )
        genai_cancel_resp = client.post(
            "/api/agents/interactions/fake_nonexistent_id_123/cancel",
            headers={"X-Gemini-API-Key": AQ_TEST_KEY},
        )

    assert genai_poll_resp.status_code == 400
    assert genai_poll_resp.json()["detail"] == "無效的任務請求: Malformed interaction resource name"
    assert genai_cancel_resp.status_code == 400
    assert genai_cancel_resp.json()["detail"] == "無效的取消請求: Malformed interaction resource name"


@pytest.mark.asyncio
async def test_agents_flash_fallback_google_search_429_does_not_pollute_global_circuit():
    rate_limit_err = _make_genai_api_error(429, "RESOURCE_EXHAUSTED: Search grounding quota exceeded")
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(side_effect=rate_limit_err)

    candidates = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]
    # Run multiple fallback attempts (exceeding ERROR_THRESHOLD=3)
    with patch("routers.agents.genai.Client", return_value=mock_client), \
         patch("routers.agents.build_effective_routing", return_value=candidates):
        for i in range(4):
            await agents_router._execute_flash_fallback_task(
                f"fallback_429_{i}",
                "Live Tokyo weather & cherry blossom forecast",
                AQ_TEST_KEY,
                locale="en",
            )

    for model_name in candidates:
        assert model_manager.is_model_circuit_broken(model_name, api_key=AQ_TEST_KEY) is False

    # Normal non-grounding CHAT routing for the same AQ. key must remain completely unaffected
    chat_routing = model_manager.build_effective_routing("CHAT", api_key=AQ_TEST_KEY)
    for model_name in candidates:
        assert model_name in chat_routing


@pytest.mark.asyncio
async def test_agents_flash_fallback_non_429_server_error_still_records_circuit():
    err_503 = _make_genai_api_error(503, "Service Unavailable")
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(side_effect=err_503)

    with patch("routers.agents.genai.Client", return_value=mock_client), \
         patch("routers.agents.build_effective_routing", return_value=["gemini-3.6-flash"]), \
         patch("services.model_manager.asyncio.sleep", AsyncMock()):
        for i in range(model_manager.ERROR_THRESHOLD):
            await agents_router._execute_flash_fallback_task(
                f"fallback_503_{i}", "Research train pass", AQ_TEST_KEY, locale="en"
            )

    assert model_manager.is_model_circuit_broken("gemini-3.6-flash", api_key=AQ_TEST_KEY) is True


# ==============================================================================
# 2. model_manager.py — Thinking capabilities, error classification, loop cache, empty outputs
# ==============================================================================


def test_gemini_25_flash_thinking_budget_zero_when_suppressed_and_preserves_explicit_budget():
    assert model_manager.MODEL_CAPS["gemini-2.5-flash"].supports_thinking is True

    # Suppressed intents must emit thinking_budget=0 (disabling default dynamic -1)
    for intent in ("EXTRACTION", "VERIFY", "GEOCODE", "SUMMARIZE", "PARSE_MD"):
        base_cfg = model_manager.get_generation_config(intent)
        safe = model_manager.sanitize_config_for_model(base_cfg, "gemini-2.5-flash", intent)
        assert safe.thinking_config is not None
        assert safe.thinking_config.thinking_budget == 0
        assert safe.thinking_config.include_thoughts is False
        assert getattr(safe.thinking_config, "thinking_level", None) is None

    # Even bare config without thinking_config gets thinking_budget=0 when suppressed
    bare = types.GenerateContentConfig(max_output_tokens=256)
    safe_bare = model_manager.sanitize_config_for_model(bare, "gemini-2.5-flash", "GEOCODE")
    assert safe_bare.thinking_config is not None
    assert safe_bare.thinking_config.thinking_budget == 0

    # PLANNING strips Gemini-3 thinking_level (budget=None -> None, dynamic thinking allowed)
    plan_cfg = model_manager.get_generation_config("PLANNING")
    safe_plan = model_manager.sanitize_config_for_model(plan_cfg, "gemini-2.5-flash", "PLANNING")
    assert safe_plan.thinking_config is None


def test_gemini_38_flash_thinking_levels_map_minimal_to_low():
    caps = model_manager.MODEL_CAPS["gemini-3.8-flash"]
    assert caps.supported_thinking_levels == ("low", "medium", "high")

    extract_cfg = model_manager.get_generation_config("EXTRACTION")
    safe_extract = model_manager.sanitize_config_for_model(extract_cfg, "gemini-3.8-flash", "EXTRACTION")
    assert safe_extract.thinking_config is not None
    assert safe_extract.thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert safe_extract.thinking_config.include_thoughts is False
    assert safe_extract.thinking_config.thinking_budget is None

    plan_cfg = model_manager.get_generation_config("PLANNING")
    safe_plan = model_manager.sanitize_config_for_model(plan_cfg, "gemini-3.8-flash", "PLANNING")
    assert safe_plan.thinking_config is not None
    assert safe_plan.thinking_config.thinking_level == types.ThinkingLevel.MEDIUM


def test_gemma_4_26b_thinking_support_and_latency_timeout_guard():
    caps = model_manager.MODEL_CAPS["gemma-4-26b-a4b-it"]
    assert caps.supports_thinking is True
    assert caps.supported_thinking_levels == ("minimal", "high")
    assert caps.allow_extraction_fallback is False

    # Bare / CHAT / PLANNING / EXTRACTION must force MINIMAL + include_thoughts=False
    for intent in ("CHAT", "PLANNING", "EXTRACTION"):
        cfg = types.GenerateContentConfig() if intent == "CHAT" else model_manager.get_generation_config(intent)
        safe = model_manager.sanitize_config_for_model(cfg, "gemma-4-26b-a4b-it", intent)
        assert safe.thinking_config is not None
        assert safe.thinking_config.thinking_level == types.ThinkingLevel.MINIMAL
        assert safe.thinking_config.include_thoughts is False

    # Latency guard: Gemma 4 is capped at GEMMA_CALL_TIMEOUT even on PLANNING / SSE
    assert model_manager._get_call_timeout("PLANNING", model_name="gemma-4-26b-a4b-it") == model_manager.GEMMA_CALL_TIMEOUT
    assert model_manager._get_call_timeout("PLANNING", model_name="gemini-3.8-flash") == model_manager.PLANNING_CALL_TIMEOUT
    with model_manager.call_timeout_scope("PLANNING_SSE"):
        assert model_manager._get_call_timeout("PLANNING", model_name="gemma-4-26b-a4b-it") == model_manager.GEMMA_CALL_TIMEOUT
        assert model_manager._get_call_timeout("PLANNING", model_name="gemini-3.8-flash") == model_manager.PLANNING_SSE_TIMEOUT


def test_classify_api_error_thought_signature_400_is_bad_request_and_fail_fast():
    sig_err = _make_genai_api_error(
        400,
        "Function call is missing a thought_signature in functionCall parts. This is required for tools to work correctly.",
    )
    assert model_manager.classify_api_error(sig_err) == "bad_request"

    # Real unsupported parameter errors still trigger config_unsupported
    schema_err = _make_genai_api_error(400, "Tool use with response mime type: 'application/json' is unsupported")
    assert model_manager.classify_api_error(schema_err) == "config_unsupported"

    # compat_errors status_code classification
    assert model_manager.classify_api_error(_make_compat_status_error(401, "Unauthorized")) == "auth_fail"
    assert model_manager.classify_api_error(_make_compat_status_error(429, "Too many requests")) == "retryable"


@pytest.mark.asyncio
async def test_call_with_fallback_does_not_retry_missing_thought_signature_400():
    sig_err = _make_genai_api_error(
        400,
        "Function call is missing a thought_signature in functionCall parts. This is required for tools to work correctly.",
    )
    mock_chat = MagicMock()
    mock_chat.send_message = AsyncMock(side_effect=sig_err)
    mock_client = MagicMock()
    mock_client.aio.chats.create.return_value = mock_chat

    with patch.object(model_manager, "get_cached_client", return_value=mock_client), \
         patch.object(model_manager, "build_effective_routing", return_value=["gemini-3.5-flash-lite"]):
        with pytest.raises(model_manager.NonRetryableRequestError):
            await model_manager.call_with_fallback(
                api_key=AQ_TEST_KEY,
                history=[],
                message="Use tool",
                intent_type="CHAT",
            )

    # Must fail fast on first attempt rather than retrying degraded config
    assert mock_chat.send_message.await_count == 1


def test_get_cached_client_isolates_across_closed_and_distinct_event_loops():
    created_clients = []

    def _make_mock_client(api_key: str):
        c = MagicMock()
        c.api_key = api_key
        c.aio.aclose = AsyncMock()
        created_clients.append(c)
        return c

    with patch.object(model_manager.genai, "Client", side_effect=_make_mock_client):
        async def _use_once():
            c1 = model_manager.get_cached_client(AQ_TEST_KEY)
            c2 = model_manager.get_cached_client(AQ_TEST_KEY)
            assert c1 is c2
            return c1

        first = asyncio.run(_use_once())
        # Second asyncio.run spins up a fresh loop after the first loop closed
        second = asyncio.run(_use_once())
        assert second is not first
        assert AQ_TEST_KEY in model_manager._client_cache

        # Concurrent distinct unclosed loops also remain isolated AND retain per-loop reuse + full close cleanup
        loop_a = asyncio.new_event_loop()
        loop_b = asyncio.new_event_loop()
        try:
            async def _get_in_loop():
                return model_manager.get_cached_client("loop-isolation-key")

            ca = loop_a.run_until_complete(_get_in_loop())
            cb = loop_b.run_until_complete(_get_in_loop())
            assert cb is not ca

            # Switching back to loop_a must reuse ca instead of dropping/leaking it
            ca_reused = loop_a.run_until_complete(_get_in_loop())
            assert ca_reused is ca

            # Shutting down closes BOTH open-loop clients with zero leak
            loop_a.run_until_complete(model_manager.close_all_cached_clients())
            ca.aio.aclose.assert_awaited_once()
            cb.aio.aclose.assert_awaited_once()
        finally:
            loop_a.close()
            loop_b.close()

    model_manager.__reset_client_cache_for_testing()
    assert len(model_manager._client_cache) == 0
    assert len(model_manager._client_loop_refs) == 0


@pytest.mark.asyncio
async def test_empty_output_records_circuit_consistently_across_entry_points():
    thought_only = _make_thought_only_response()
    target_model = "gemini-3.5-flash-lite"

    # 1. call_with_fallback
    mock_chat = MagicMock()
    mock_chat.send_message = AsyncMock(return_value=thought_only)
    mock_client = MagicMock()
    mock_client.aio.chats.create.return_value = mock_chat
    mock_client.aio.models.generate_content = AsyncMock(return_value=thought_only)

    with patch.object(model_manager, "get_cached_client", return_value=mock_client), \
         patch.object(model_manager, "build_effective_routing", return_value=[target_model]):
        for _ in range(model_manager.ERROR_THRESHOLD):
            with pytest.raises(model_manager.AllModelsFailedError):
                await model_manager.call_with_fallback(
                    api_key="key-empty-chat", history=[], message="hi", intent_type="CHAT"
                )
    assert model_manager.is_model_circuit_broken(target_model, api_key="key-empty-chat") is True
    assert model_manager.is_model_circuit_broken(target_model, api_key="unrelated-key") is False

    # 2. call_verifier
    with patch.object(model_manager, "get_cached_client", return_value=mock_client), \
         patch.object(model_manager, "build_effective_routing", return_value=[target_model]):
        for _ in range(model_manager.ERROR_THRESHOLD):
            with pytest.raises(model_manager.AllModelsFailedError):
                await model_manager.call_verifier(
                    api_key="key-empty-verify", poi_data={"place_name": "Kiyomizu"}, query="hours"
                )
    assert model_manager.is_model_circuit_broken(target_model, api_key="key-empty-verify") is True

    # 3. call_extraction
    with patch.object(model_manager, "get_cached_client", return_value=mock_client), \
         patch.object(model_manager, "build_effective_routing", return_value=[target_model]):
        for _ in range(model_manager.ERROR_THRESHOLD):
            with pytest.raises(model_manager.AllModelsFailedError):
                await model_manager.call_extraction(
                    api_key="key-empty-extract", prompt="extract", intent_type="EXTRACTION"
                )
    assert model_manager.is_model_circuit_broken(target_model, api_key="key-empty-extract") is True


# ==============================================================================
# 3. ai_config.py & ai.py — Deduplicated routing & PLANNING thinking alignment
# ==============================================================================


def test_ai_config_routing_deduplicated_and_free_of_deprecated_aliases():
    for name, route_list in (
        ("DAILY_ROUTING", ai_config.DAILY_ROUTING),
        ("HEAVY_ROUTING", ai_config.HEAVY_ROUTING),
        ("EXTRACTION_ROUTING", ai_config.EXTRACTION_ROUTING),
    ):
        assert len(route_list) == len(set(route_list)), f"{name} contains duplicates: {route_list}"
        assert "gemini-3.5-flash" not in route_list, f"{name} still has deprecated gemini-3.5-flash"
        assert "gemini-3.7-flash" not in route_list, f"{name} still has deprecated gemini-3.7-flash"
        assert "gemini-3.6-flash" in route_list
        assert "gemini-3.8-flash" in route_list


def test_ai_router_planning_prompt_matches_medium_thinking_level():
    src = inspect.getsource(ai_router.generate_trip_core)
    assert "[Thinking: Medium]" in src
    assert "[Thinking: High]" not in src
    plan_cfg = model_manager.get_generation_config("PLANNING")
    assert plan_cfg.thinking_config.thinking_level == types.ThinkingLevel.MEDIUM


@pytest.mark.asyncio
async def test_compat_status_error_is_handled_for_429_and_401_in_model_manager():
    # Space-separated thought signature 400 also fails fast as bad_request
    assert model_manager.classify_api_error(
        _make_compat_status_error(400, "Thought signature is required for tools to work.")
    ) == "bad_request"

    # compat_errors.RateLimitError (code=None, status_code=429) triggers is_rate_limit=True cooldown (12s)
    rate_err = _make_compat_status_error(429, "Quota exceeded; please retry in 5s.")
    mock_chat = MagicMock()
    mock_chat.send_message = AsyncMock(side_effect=rate_err)
    mock_client = MagicMock()
    mock_client.aio.chats.create.return_value = mock_chat

    with patch.object(model_manager, "get_cached_client", return_value=mock_client), \
         patch.object(model_manager, "build_effective_routing", return_value=["gemini-3.6-flash"]), \
         patch("services.model_manager.asyncio.sleep", AsyncMock()):
        for _ in range(model_manager.ERROR_THRESHOLD):
            with pytest.raises(model_manager.AllModelsFailedError):
                await model_manager.call_with_fallback(
                    api_key="key-compat-429", history=[], message="hi", intent_type="CHAT"
                )
    ck = model_manager._get_circuit_key("gemini-3.6-flash", "key-compat-429")
    assert model_manager.is_model_circuit_broken("gemini-3.6-flash", api_key="key-compat-429") is True
    import time as _t
    cooldown_until = model_manager._CIRCUIT_STATE[ck]["cooldown_until"]
    assert 0 < cooldown_until - _t.time() <= model_manager.RATE_LIMIT_COOLDOWN + 1.0

    # compat_errors.AuthenticationError (401) raises NonRetryableAuthError immediately
    auth_err = _make_compat_status_error(401, "API key invalid")
    mock_chat.send_message = AsyncMock(side_effect=auth_err)
    with patch.object(model_manager, "get_cached_client", return_value=mock_client), \
         patch.object(model_manager, "build_effective_routing", return_value=["gemini-3.6-flash"]):
        with pytest.raises(model_manager.NonRetryableAuthError):
            await model_manager.call_with_fallback(
                api_key="key-compat-401", history=[], message="hi", intent_type="CHAT"
            )


@pytest.mark.asyncio
async def test_agents_flash_fallback_applies_gemma4_timeout_cap_per_candidate():
    observed_timeouts = []

    async def capture_retry(invoke_fn, model_name, config, timeout_sec, tag):
        observed_timeouts.append((model_name, timeout_sec))
        resp = MagicMock()
        resp.candidates = []
        resp.text = "Fallback itinerary output"
        return resp

    mock_client = MagicMock()
    with patch("routers.agents.genai.Client", return_value=mock_client), \
         patch("routers.agents.build_effective_routing", return_value=["gemma-4-26b-a4b-it"]), \
         patch("routers.agents._execute_with_transient_retry", side_effect=capture_retry):
        await agents_router._execute_flash_fallback_task(
            "fallback_gemma_cap", "Plan Kyoto", AQ_TEST_KEY, locale="en"
        )

    assert observed_timeouts == [("gemma-4-26b-a4b-it", model_manager.GEMMA_CALL_TIMEOUT)]
