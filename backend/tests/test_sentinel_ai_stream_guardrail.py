"""
Security Sentinel In-Memory PoC & Benign Control Tests
Topic: AI Streaming Guardrails, Intent Routing & Capability Stripping
Date: 2026-11-10
"""

import pytest
import asyncio
import json
import re
from unittest.mock import MagicMock, AsyncMock

from services.intent_router import _fast_path_classify, GREETING_PATTERN, PRAISE_PATTERN
from services.model_manager import MODEL_CAPS
from services.stream_sanitizer import StreamLookaheadSanitizer


# ═══════════════════════════════════════════════════════════════
# 1. Intent Router: Praise & Gratitude Fast-Path Tests
# ═══════════════════════════════════════════════════════════════

def test_benign_standard_greetings():
    """Mantis Block G Benign Control: 標準問候語必須持續命中 CHAT (0ms)"""
    benign_greetings = ["你好", "早安", "hello", "hi", "嗨！", "謝謝~", "午安", "晚安"]
    for text in benign_greetings:
        assert _fast_path_classify(text) == "CHAT", f"Benign greeting '{text}' should route to CHAT"


def test_poc_praise_and_gratitude_misroute():
    """
    Sentinel PoC: 證明「你很棒」、「太強了」等日常讚美穿透 Fast-Path (回傳 None)，
    導致後續落入 Stage 2 逾時並誤判為 SEARCH，發動無效搜尋。
    修復後必須 100% 命中 Fast-Path 回傳 'CHAT'。
    """
    praise_samples = [
        "你很棒",
        "太強了",
        "好厲害",
        "太讚了",
        "good job",
        "awesome",
        "great job",
        "你太棒了吧",
        "真厲害！",
        "辛苦了",
        "辛苦啦",
        "辛苦您了",
        "謝謝你唷",
        "好棒唷",
        "太神啦",
        "非常感謝！",
        "Thank you",
        "thank you so much!",
        "You are awesome",
        "you're great",
    ]
    failed_samples = []
    for text in praise_samples:
        verdict = _fast_path_classify(text)
        if verdict != "CHAT":
            failed_samples.append((text, verdict))
    
    assert len(failed_samples) == 0, f"Praise samples misrouted (returned {failed_samples}): expected 'CHAT'"


def test_benign_negative_controls_not_misrouted_as_chat():
    """Mantis Block G Benign Control: 具體旅遊探索、搜尋或移除指令絕不被誤判為 CHAT"""
    negatives = [
        "曼谷有什麼好吃的",
        "推薦好吃的拉麵",
        "幫我查一下天氣",
        "把淺草寺移除",
        "幫我規劃京都3天行程"
    ]
    for text in negatives:
        verdict = _fast_path_classify(text)
        assert verdict != "CHAT", f"Non-chat query '{text}' incorrectly classified as CHAT"


# ═══════════════════════════════════════════════════════════════
# 2. Streaming Buffer: JSON & Thought Interception Simulation
# ═══════════════════════════════════════════════════════════════

async def simulate_streaming_sanitizer(chunks):
    """
    調用正式 StreamLookaheadSanitizer 進行滑動前瞻與中段 JSON 截獲測試
    """
    sanitizer = StreamLookaheadSanitizer(window_size=30)
    emitted_texts = []
    for c in chunks:
        emitted_texts.extend(sanitizer.feed(c))
    tail, parsed_json = sanitizer.flush()
    emitted_texts.extend(tail)
    emitted_fcs = [parsed_json] if parsed_json else []
    return "".join(emitted_texts), emitted_fcs


@pytest.mark.asyncio
async def test_streaming_sanitizer_catches_mid_text_json():
    """驗證中段出現的 JSON 協定被完美截獲，正文對話無任何代碼外洩，並成功轉化為結構化調用"""
    raw_chunks = [
        "班嘉奇蒂公園 (Benjakitti Park) 的時間已經很近囉！\n",
        "那裡真的很適合下午去走走，空中步道也是絕佳攝影點。\n",
        "{\n  ",
        '"items": [\n    {\n      "day": 1,\n      "place_name": "班嘉奇蒂公園",\n',
        '      "category": "park",\n      "desc": "曼谷城市綠洲",\n',
        '      "lat": 13.7276,\n      "lng": 100.5562\n    }\n  ]\n}',
    ]
    visible_text, extracted_fcs = await simulate_streaming_sanitizer(raw_chunks)

    # 1. 正文絕對不能包含任何 JSON 語法
    assert '{"items":' not in visible_text
    assert '"place_name"' not in visible_text
    assert "班嘉奇蒂公園 (Benjakitti Park) 的時間已經很近囉！" in visible_text

    # 2. 結構化資料必須被成功提取
    assert len(extracted_fcs) == 1
    assert extracted_fcs[0]["items"][0]["place_name"] == "班嘉奇蒂公園"


@pytest.mark.asyncio
async def test_streaming_sanitizer_catches_split_thought_tags():
    """驗證跨 Chunk 撕裂的 <thought> 標籤能被完整消除，不外洩思考過程"""
    raw_chunks = [
        "你好！",
        "<thought>User is asking about travel in Bangkok.",
        " I will recommend some spots.</thought>曼谷是個很棒的城市！"
    ]
    visible_text, _ = await simulate_streaming_sanitizer(raw_chunks)

    assert "<thought>" not in visible_text
    assert "</thought>" not in visible_text
    assert "User is asking about travel" not in visible_text
    assert "你好！" in visible_text
    assert "曼谷是個很棒的城市！" in visible_text


# ═══════════════════════════════════════════════════════════════
# 3. Model Capability: Gemma 4 Capability Stripping
# ═══════════════════════════════════════════════════════════════

def test_gemma_capability_stripping_logic():
    """
    驗證 Gemma 模型能力配置與工具安全剝離規則：
    當模型屬於 gemma 家族且執行純文本/分類任務時，必須強制 tools=None
    """
    from services.model_manager import sanitize_config_for_model, get_generation_config
    from google.genai import types

    for model_name in ["gemma-4-31b-it", "gemma-4-26b-a4b-it", "gemma-3-27b-it"]:
        caps = MODEL_CAPS.get(model_name)
        assert caps is not None
        assert caps.family == "gemma"
        
        # 驗證在執行純文字/分類任務時，必須剝離 tools 與抑制思考
        base_cfg = types.GenerateContentConfig(
            temperature=0.7,
            tools=[types.Tool(function_declarations=[])]
        )
        safe_cfg = sanitize_config_for_model(base_cfg, model_name, "INTENT_PARSE")
        assert safe_cfg.tools is None
        if caps.supports_thinking:
            # Gemma 4 31B supports thinking; omitting thinking_config enables default reasoning,
            # so sanitizer must explicitly suppress thinking via MINIMAL + include_thoughts=False.
            assert safe_cfg.thinking_config is not None
            assert safe_cfg.thinking_config.thinking_level == types.ThinkingLevel.MINIMAL
            assert safe_cfg.thinking_config.include_thoughts is False
        else:
            assert safe_cfg.thinking_config is None


def test_gemma_polymorphic_flat_tool_depth_one():
    """
    AC-Flat-1 & AC-Parallel-2: 驗證 Gemma 單層超扁平化工具 (Depth=1)
    - 嚴格無任何深層 items 巢狀結構，徹底杜絕 Google API 500
    - Gemini 模型完整保留 items 4 層巢狀結構
    """
    from services.model_manager import (
        ADD_ITINERARY_FLAT_DECL,
        ADD_ITINERARY_DECL,
        get_tools_for_model,
        sanitize_config_for_model
    )
    from google.genai import types

    # 1. Gemma 扁平化工具檢驗 (Depth=1，無任何 items/sub_items 巢狀陣列)
    gemma_props = ADD_ITINERARY_FLAT_DECL.parameters.properties
    assert "items" not in gemma_props, "Gemma flat tool MUST NOT have nested 'items' array"
    assert "sub_items" not in gemma_props, "Gemma flat tool MUST NOT have nested 'sub_items' array"
    assert "place_name" in gemma_props
    assert "lat" in gemma_props
    assert "lng" in gemma_props

    # 2. Gemini 工具檢驗 (保留批次 4 層 items 陣列吞吐)
    gemini_props = ADD_ITINERARY_DECL.parameters.properties
    assert "items" in gemini_props, "Gemini tool must preserve batch 'items' array"

    # 3. 多型工具工廠分流檢驗
    gemma_tools = get_tools_for_model("gemma-4-31b-it", "ITINERARY")
    assert gemma_tools is not None and len(gemma_tools) == 1
    assert gemma_tools[0].function_declarations[0].name == "add_itinerary_item"
    assert "items" not in gemma_tools[0].function_declarations[0].parameters.properties

    gemini_tools = get_tools_for_model("gemini-2.5-flash", "ITINERARY")
    assert gemini_tools is not None and len(gemini_tools) == 1
    assert "items" in gemini_tools[0].function_declarations[0].parameters.properties

    # 4. 配置淨化多型自適應轉接檢驗 (將 ADD_ITINERARY_DECL 傳入 Gemma 配置，必須自動降為 FLAT)
    nested_cfg = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=[ADD_ITINERARY_DECL])]
    )
    sanitized_gemma = sanitize_config_for_model(nested_cfg, "gemma-4-31b-it", "ITINERARY")
    assert sanitized_gemma.tools is not None
    active_decl = sanitized_gemma.tools[0].function_declarations[0]
    assert "items" not in active_decl.parameters.properties



# ═══════════════════════════════════════════════════════════════
# 4. End-to-End Chat Stream Sentinel Verification
# ═══════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_chat_stream_praise_warm_response_no_search_no_leak():
    """
    AC-Praise-5 & AC-Sanitizer-4: 
    使用者發送「你很棒」至 /api/chat/stream 時：
    1. 0 次外部聯網搜尋 (execute_web_search / fetch_jina_reader 未被調用)
    2. 工具完全卸載 (tools=None)
    3. 串流純文字回覆，無任何 JSON 或思維鏈標籤外洩
    """
    from httpx import AsyncClient, ASGITransport
    from main import app
    from unittest.mock import patch, MagicMock

    transport = ASGITransport(app=app)
    headers = {
        "X-Gemini-API-Key": "AIzaSy" + "A" * 34,
        "Content-Type": "application/json"
    }
    payload = {
        "message": "你很棒",
        "history": []
    }

    class MockChunk:
        def __init__(self, text):
            self.text = text
            self.thought = None
            self.thought_signature = None
            self.function_calls = None
            self.candidates = []

    async def mock_stream_gen(*args, **kwargs):
        # 模擬模型返回帶有思維鏈與結尾自然語言的串流
        chunks = [
            MockChunk("<thought>User praised me, respond warmly.</thought>謝謝你的誇獎！"),
            MockChunk("我是你的專屬 AI 旅遊顧問 Ryan，很高興能為你的旅程提供協助！🌸")
        ]
        for c in chunks:
            yield c

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(return_value=mock_stream_gen())

    with patch("google.genai.Client", return_value=mock_client), \
         patch("services.web_search_engine.execute_web_search") as mock_search, \
         patch("services.web_search_engine.fetch_jina_reader") as mock_jina:
        
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with client.stream("POST", "/api/chat/stream", json=payload, headers=headers) as res:
                assert res.status_code == 200
                events = []
                text_parts = []
                async for line in res.aiter_lines():
                    if line.startswith("event:"):
                        events.append(line.split(":", 1)[1].strip())
                    elif line.startswith("data:") and events and events[-1] == "text":
                        data_json = json.loads(line.split(":", 1)[1].strip())
                        text_parts.append(data_json.get("text", ""))

                # 斷言 1: 0 次發起外部搜尋
                assert mock_search.call_count == 0, "Praise '你很棒' must NEVER trigger web search"
                assert mock_jina.call_count == 0, "Praise '你很棒' must NEVER trigger jina reader"

                full_reply = "".join(text_parts)
                # 斷言 2: 思維鏈標籤 100% 消除
                assert "<thought>" not in full_reply
                assert "</thought>" not in full_reply
                assert "User praised me" not in full_reply

                # 斷言 3: 正文純淨自然語言秒回
                assert "謝謝你的誇獎！" in full_reply
                assert "AI 旅遊顧問 Ryan" in full_reply
                assert "{" not in full_reply
                assert "items" not in full_reply


@pytest.mark.asyncio
async def test_chat_stream_midstream_json_interception_and_trailing_text():
    """
    AC-Sanitizer-3 & AC-Sanitizer-4:
    驗證串流中段輸出之 JSON 協定被攔截轉為 event: tool，
    且 JSON 之後的結尾自然語言 100% 保留並推送至 event: text。
    """
    from httpx import AsyncClient, ASGITransport
    from main import app
    from unittest.mock import patch, MagicMock, AsyncMock

    transport = ASGITransport(app=app)
    headers = {
        "X-Gemini-API-Key": "AIzaSy" + "A" * 34,
        "Content-Type": "application/json"
    }
    payload = {
        "message": "推薦曼谷景點",
        "history": []
    }

    class MockChunk:
        def __init__(self, text):
            self.text = text
            self.thought = None
            self.thought_signature = None
            self.function_calls = None
            self.candidates = []

    async def mock_stream_gen(*args, **kwargs):
        chunks = [
            MockChunk("為您推薦曼谷必去景點：\n"),
            MockChunk("```json\n{\n  "),
            MockChunk('"items": [\n    {\n      "day": 1,\n      "place_name": "臥佛寺",\n      "category": "temple"\n    }\n  ]\n}\n```\n'),
            MockChunk("臥佛寺內有巨大的臥佛像，非常值得一訪喔！祝旅途愉快！")
        ]
        for c in chunks:
            yield c

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(return_value=mock_stream_gen())

    with patch("google.genai.Client", return_value=mock_client), \
         patch("services.web_search_engine.execute_web_search"), \
         patch("services.web_search_engine.fetch_jina_reader"):
        
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with client.stream("POST", "/api/chat/stream", json=payload, headers=headers) as res:
                assert res.status_code == 200
                events = []
                text_parts = []
                tool_calls = []
                async for line in res.aiter_lines():
                    if line.startswith("event:"):
                        events.append(line.split(":", 1)[1].strip())
                    elif line.startswith("data:") and events:
                        cur_ev = events[-1]
                        data_json = json.loads(line.split(":", 1)[1].strip())
                        if cur_ev == "text":
                            text_parts.append(data_json.get("text", ""))
                        elif cur_ev == "tool":
                            tool_calls.append(data_json.get("function_call", {}))

                full_reply = "".join(text_parts)
                # 1. 前後自然語言必須完整保留
                assert "為您推薦曼谷必去景點：" in full_reply
                assert "臥佛寺內有巨大的臥佛像，非常值得一訪喔！祝旅途愉快！" in full_reply
                # 2. 正文絕對無代碼外洩
                assert "```json" not in full_reply
                assert '{"items":' not in full_reply
                assert '"place_name"' not in full_reply
                # 3. 工具調用必須被正確發送
                assert len(tool_calls) == 1
                assert tool_calls[0]["name"] == "add_itinerary_item"
                assert tool_calls[0]["args"]["items"][0]["place_name"] == "臥佛寺"
