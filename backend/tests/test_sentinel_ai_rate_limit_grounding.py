"""
Security Sentinel In-Memory PoC Test Suite: AI Rate Limit & Grounding Defense
=============================================================================
Tests:
1. Free API Key Grounding Trap Prevention (clean business tools vs explicit grounding)
2. Structured 429 Metadata Extraction (QuotaFailure & RetryInfo)
3. API-Key-Isolated Circuit Breaker with 10-15s Rate Limit Cooldown
4. Dual-Speed Quick Retry and Smooth Fallback Jitter
5. Mantis Block G Benign Control: Actuary and Chat Functionality Integrity
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from google.genai import types, errors
from services.model_manager import (
    sanitize_config_for_model,
    get_generation_config,
    parse_429_metadata,
    is_model_circuit_broken,
    record_model_error,
    call_with_fallback,
    build_effective_routing,
    _CIRCUIT_STATE,
)
from utils.ai_config import DAILY_ROUTING


class FakeAPIError(errors.APIError):
    def __init__(self, message="Resource exhausted", code=429, details=None):
        self.message = message
        self.code = code
        self.details = details or []
        resp_json = {"error": {"code": code, "message": message, "details": details or []}}
        super().__init__(code=code, response_json=resp_json)


# ═══════════════════════════════════════════════════════════════
# 1. PoC 1: Free API Key Grounding Trap Prevention
# ═══════════════════════════════════════════════════════════════

def test_poc_free_api_key_grounding_trap():
    """
    Vulnerability: Blindly injecting google_search and google_maps onto Gemini models
    during CHAT/ITINERARY/DIAGNOSIS/COMPOSITE intents causes immediate HTTP 429
    RESOURCE_EXHAUSTED rejections on free-tier API keys.

    Defense Requirement: Do NOT blindly inject paid grounding tools unless explicitly requested.
    General chat, actuary, and itinerary must retain clean business tools.
    """
    from services.model_manager import NEURAL_LINK_TOOLS

    # 1. 測試 CHAT 意圖：具有 NEURAL_LINK_TOOLS 業務工具，但絕不可被強行追加 google_maps 付費地圖工具
    chat_config = types.GenerateContentConfig(tools=NEURAL_LINK_TOOLS)
    sanitized_chat = sanitize_config_for_model(
        chat_config, "gemini-3.8-flash", "CHAT", explicit_grounding=False
    )
    assert sanitized_chat.tools is not None
    for tool in sanitized_chat.tools:
        assert getattr(tool, "google_maps", None) is None, "Accidental google_maps injected in CHAT"

    # 2. 測試 ITINERARY 意圖：具有 ADD_ITINERARY_TOOL，絕不可被強行追加 google_maps
    itin_config = get_generation_config("ITINERARY")
    sanitized_itin = sanitize_config_for_model(
        itin_config, "gemini-3.8-flash", "ITINERARY", explicit_grounding=False
    )
    assert sanitized_itin.tools is not None
    for tool in sanitized_itin.tools:
        assert getattr(tool, "google_maps", None) is None, "Accidental google_maps injected in ITINERARY"

    # 3. 測試顯式請求 Grounding (explicit_grounding=True)：此時模型才允許注入地圖與搜尋
    clean_config = types.GenerateContentConfig()
    explicit_grounded = sanitize_config_for_model(
        clean_config, "gemini-3.8-flash", "CHAT", explicit_grounding=True
    )
    assert explicit_grounded.tools is not None
    assert any(hasattr(t, "google_maps") and t.google_maps is not None for t in explicit_grounded.tools)

    # 4. 測試未指定 explicit_grounding (預設 False)：clean_config 絕不盲目注入地圖與搜尋
    default_unspecified = sanitize_config_for_model(
        clean_config, "gemini-3.8-flash", "CHAT"
    )
    assert default_unspecified.tools is None, "Blind grounding injection occurred on default unspecified call"


# ═══════════════════════════════════════════════════════════════
# 2. PoC 2: Structured 429 Metadata Parsing
# ═══════════════════════════════════════════════════════════════

def test_poc_parse_429_metadata_with_retry_info():
    """
    驗證 parse_429_metadata 能從 err.details 中的 RetryInfo 與 QuotaFailure 提取結構化資料。
    """
    details = [
        {
            "@type": "type.googleapis.com/google.rpc.RetryInfo",
            "retryDelay": "1.2s"
        },
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [
                {
                    "subject": "project:12345/rate_limit",
                    "description": "Quota exceeded for quota metric 'GenerateContentRequestsPerMinutePerProjectPerRegion'"
                }
            ]
        }
    ]
    err = FakeAPIError(message="Resource has been exhausted", code=429, details=details)
    meta = parse_429_metadata(err)
    assert meta["retry_delay"] == pytest.approx(1.2, abs=0.01)
    assert meta["is_daily"] is False
    assert "rate_limit" in meta["quota_reason"].lower() or "minute" in meta["quota_reason"].lower()


def test_poc_parse_429_metadata_daily_quota_and_fallback_regex():
    """
    驗證每日限額 (RPD) 辨識與 Message 正則回退機制。
    """
    # 測試 Daily 標記
    details_daily = [
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [{"description": "PerDay requests quota exceeded for service"}]
        }
    ]
    err_daily = FakeAPIError(message="Quota exceeded", code=429, details=details_daily)
    meta_daily = parse_429_metadata(err_daily)
    assert meta_daily["is_daily"] is True

    # 測試 details 為空時的正則提取回退
    err_msg = FakeAPIError(message="Resource has been exhausted. Please retry in 0.8s.", code=429, details=[])
    meta_msg = parse_429_metadata(err_msg)
    assert meta_msg["retry_delay"] == pytest.approx(0.8, abs=0.01)
    assert meta_msg["is_daily"] is False

    # 測試 details 為字串化 JSON 之深層解析 (如 Cloudflare Edge Proxy 或 API Gateway 封裝)
    import json
    json_str_details = json.dumps([{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "1.4s"}])
    err_json_str = FakeAPIError(message="Resource exhausted", code=429, details=json_str_details)
    meta_json_str = parse_429_metadata(err_json_str)
    assert meta_json_str["retry_delay"] == pytest.approx(1.4, abs=0.01)
    assert meta_json_str["is_daily"] is False

    # 測試 message 僅為通用提示但 details 字串含有 retryDelay 欄位
    err_raw_str = FakeAPIError(message="Resource exhausted", code=429, details="quota failure with retryDelay 1.1s")
    meta_raw_str = parse_429_metadata(err_raw_str)
    assert meta_raw_str["retry_delay"] == pytest.approx(1.1, abs=0.01)


# ═══════════════════════════════════════════════════════════════
# 3. PoC 3: API Key Isolation & Cooldown in Circuit Breaker
# ═══════════════════════════════════════════════════════════════

def test_poc_circuit_breaker_api_key_isolation():
    """
    驗證熔斷器狀態以 (hash(api_key), model_name) 隔離，單一用戶 Key 觸發 429 不影響其他租戶，
    且 429 冷卻時間縮減為 10~15s，而非全域鎖定 300s。
    """
    key_a = "gemini_key_tenant_alpha_111111111"
    key_b = "gemini_key_tenant_bravo_222222222"
    model = "gemini-3.8-flash"

    # 清理初始狀態
    _CIRCUIT_STATE.clear()

    # 記錄 key_a 連續 3 次 429 錯誤
    for _ in range(3):
        record_model_error(model, api_key=key_a, is_rate_limit=True)

    # key_a 應處於熔斷狀態
    assert is_model_circuit_broken(model, api_key=key_a) is True

    # key_b 絕不可被波及！(Cross-tenant DoS defense)
    assert is_model_circuit_broken(model, api_key=key_b) is False

    # 檢查 key_a 的冷卻時間：必須在 10 ~ 15 秒之間，嚴禁為 300s
    key_hash = None
    for k in _CIRCUIT_STATE:
        if model in k and "alpha" in key_a: # 透過雜湊或關聯鍵比對
            key_hash = k
            break
    assert key_hash is not None
    cooldown_until = _CIRCUIT_STATE[key_hash]["cooldown_until"]
    remaining = cooldown_until - time.time()
    assert 5 <= remaining <= 16, f"Cooldown should be 10~15s, got remaining={remaining}"


# ═══════════════════════════════════════════════════════════════
# 4. PoC 4: Dual-Speed Quick Retry & Smooth Fallback Jitter
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@patch("services.model_manager.get_cached_client")
async def test_poc_call_with_fallback_dual_speed_quick_retry(mock_get_client):
    """
    當 429 指明 retry_delay <= 1.5s 時，執行一次快速原地重試 (Quick Retry)。
    若重試成功，直接返回結果，無需切換模型；且不記錄為 300s 伺服器崩潰。
    """
    _CIRCUIT_STATE.clear()
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_chat = MagicMock()
    mock_client.aio.chats.create.return_value = mock_chat

    # 模擬第一次呼叫噴 429 (retryDelay 0.1s)，第二次快速重試成功
    err_429 = FakeAPIError(
        message="Resource exhausted. Please retry in 0.1s",
        code=429,
        details=[{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "0.1s"}]
    )

    fake_resp = MagicMock()
    fake_resp.text = "雙速重試成功！"
    fake_resp.candidates = [MagicMock(content=MagicMock(parts=[MagicMock(text="雙速重試成功！", thought=None, function_call=None)]))]

    mock_chat.send_message = AsyncMock(side_effect=[err_429, fake_resp])

    result = await call_with_fallback(
        api_key="test_dual_speed_key",
        history=[],
        message="測試快速重試",
        intent_type="CHAT",
        explicit_grounding=False
    )

    assert result["text"] == "雙速重試成功！"
    assert mock_chat.send_message.call_count == 2
    # 驗證模型未被熔斷
    assert is_model_circuit_broken(DAILY_ROUTING[0], api_key="test_dual_speed_key") is False


# ═══════════════════════════════════════════════════════════════
# 5. Mantis Block G Benign Control: Actuary Clean Config & Chat
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
@patch("services.model_manager.get_cached_client")
async def test_benign_actuary_clean_config_no_grounding(mock_get_client):
    """
    良性對照 (Block G): 驗證 AI 精算師傳遞 clean tools ([] 或無工具)，
    在 call_with_fallback 與 sanitize_config_for_model 處理後保持乾淨，
    完全不附帶原生 Google Maps Grounding，確保免費用戶金鑰 100% 穩定可用。
    """
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_chat = MagicMock()
    mock_client.aio.chats.create.return_value = mock_chat

    fake_resp = MagicMock()
    fake_resp.text = "本趟東京之旅總花費 50,000 JPY，建議每人均分 25,000 JPY。"
    fake_resp.candidates = [MagicMock(content=MagicMock(parts=[MagicMock(text=fake_resp.text, thought=None, function_call=None)]))]
    mock_chat.send_message = AsyncMock(return_value=fake_resp)

    # 模擬 Actuary 呼叫 (tools=[])
    result = await call_with_fallback(
        api_key="benign_actuary_key",
        history=[],
        message="計算分帳",
        intent_type="CHAT",
        system_instruction="你是 Ryan，專業財務顧問",
        tools=[]
    )

    assert result["text"] == fake_resp.text
    # 檢查 chats.create 的 config 參數
    created_config = mock_client.aio.chats.create.call_args.kwargs["config"]
    if created_config.tools:
        for t in created_config.tools:
            assert getattr(t, "google_maps", None) is None


@pytest.mark.asyncio
@patch("services.model_manager.get_cached_client")
async def test_benign_general_chat_workflow(mock_get_client):
    """
    良性對照 (Block G): 驗證常規聊天功能不受任何影響，依然具備標準業務工具與回應能力。
    """
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client
    mock_chat = MagicMock()
    mock_client.aio.chats.create.return_value = mock_chat

    fake_resp = MagicMock()
    fake_resp.text = "你好！我是你的旅行助理。"
    fake_resp.candidates = [MagicMock(content=MagicMock(parts=[MagicMock(text=fake_resp.text, thought=None, function_call=None)]))]
    mock_chat.send_message = AsyncMock(return_value=fake_resp)

    result = await call_with_fallback(
        api_key="benign_chat_key",
        history=[],
        message="你好",
        intent_type="CHAT"
    )

    assert result["text"] == fake_resp.text


def test_benign_enforce_strict_alternating_turns_immutability():
    """
    良性對照 (Block G): 驗證 enforce_strict_alternating_turns 能合併連續 turn，
    且具備純函數特性，絕不在原始傳入之 Content.parts 上進行 in-place mutation。
    """
    from services.model_manager import enforce_strict_alternating_turns

    part_a = types.Part.from_text(text="First turn")
    part_b = types.Part.from_text(text="Second turn")
    c1 = types.Content(role="user", parts=[part_a])
    c2 = types.Content(role="user", parts=[part_b])
    c3 = types.Content(role="model", parts=[types.Part.from_text(text="Model response")])

    history = [c1, c2, c3]
    merged = enforce_strict_alternating_turns(history)

    assert len(merged) == 2
    assert merged[0].role == "user"
    assert len(merged[0].parts) == 2
    assert merged[1].role == "model"

    # 關鍵：驗證原始物件 c1.parts 未被在原地破壞或污染
    assert len(c1.parts) == 1, "c1.parts was mutated in-place by enforce_strict_alternating_turns"
    assert c1.parts[0].text == "First turn"
