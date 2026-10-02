# -*- coding: utf-8 -*-
"""
Stream Search ReAct Integration Test Suite
==========================================
End-to-end integration tests for:
1. Intent classification -> SEARCH
2. Server-side Tool Interception (search_web / fetch_webpage)
3. SSE thinking event streaming
4. FunctionResponse loopback into Gemini Second Pass Stream
5. Sources propagation to client
"""

import pytest
import sys
import os
import json
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

HEADERS = {
    "X-Gemini-API-Key": "AIzaSy" + "B" * 34,
    "Content-Type": "application/json"
}


class MockAsyncStream:
    """模擬 google.genai 的 aio.models.generate_content_stream 非同步迭代器"""
    def __init__(self, chunks):
        self.chunks = chunks

    def __aiter__(self):
        self._iter = iter(self.chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def parse_sse_events(sse_text: str):
    """解析 Server-Sent Events 為 [(event_name, data_dict_or_str)] 列表"""
    events = []
    current_event = None
    for line in sse_text.splitlines():
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: ") and current_event:
            raw_data = line[6:].strip()
            try:
                data = json.loads(raw_data)
            except Exception:
                data = raw_data
            events.append((current_event, data))
            current_event = None
    return events


def test_stream_search_react_full_flow():
    """驗證即時搜尋端到端：SEARCH 意圖 -> 攔截 search_web -> 發送 thinking -> 回填 functionResponse -> 串流回應"""
    
    # 1. 模擬 First Pass 回傳 function_call (search_web)
    mock_fc_candidate = MagicMock()
    mock_fc_candidate.finish_reason = "STOP"
    
    mock_part = MagicMock()
    mock_part.text = None
    mock_part.function_call = MagicMock()
    mock_part.function_call.name = "search_web"
    mock_part.function_call.args = {"query": "東京晴空塔 營業時間 門票"}
    
    mock_content = MagicMock()
    mock_content.parts = [mock_part]
    mock_fc_candidate.content = mock_content
    
    mock_first_pass = MagicMock()
    mock_first_pass.candidates = [mock_fc_candidate]
    
    mock_fc = MagicMock()
    mock_fc.name = "search_web"
    mock_fc.args = {"query": "東京晴空塔 營業時間 門票"}
    mock_first_pass.function_calls = [mock_fc]

    # 2. 模擬 Second Pass 串流回覆 (使用 spec 嚴格限制欄位，避免 MagicMock 幻覺屬性)
    chunk1 = MagicMock(spec=["text", "thought", "candidates"])
    chunk1.text = "東京晴空塔目前的營業時間為 10:00 至 21:00。"
    chunk1.thought = None
    chunk1.candidates = []
    
    chunk2 = MagicMock(spec=["text", "thought", "candidates"])
    chunk2.text = " 當日展望台門票成人約為 2,100 日圓。"
    chunk2.thought = None
    chunk2.candidates = []

    mock_search_results = [
        {
            "title": "東京晴空塔官方網站",
            "url": "https://www.tokyo-skytree.jp/",
            "snippet": "營業時間：10:00 - 21:00，最終入場 20:00。"
        }
    ]

    mock_genai_client = MagicMock()
    mock_genai_client.aio.models.generate_content = AsyncMock(return_value=mock_first_pass)
    mock_genai_client.aio.models.generate_content_stream = AsyncMock(
        return_value=MockAsyncStream([chunk1, chunk2])
    )

    with patch("main.genai.Client", return_value=mock_genai_client):
        with patch("main.execute_web_search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = mock_search_results

            resp = client.post(
                "/api/chat/stream",
                json={
                    "message": "請問晴空塔最新營業時間與票價？",
                    "history": []
                },
                headers=HEADERS
            )

            assert resp.status_code == 200
            events = parse_sse_events(resp.text)

            # 驗證 SSE 思考事件
            thinking_events = [data for ev, data in events if ev == "thinking"]
            assert any(d.get("status") == "searching" and "晴空塔" in d.get("query", "") for d in thinking_events if isinstance(d, dict))

            # 驗證 SSE 文本串流
            text_events = [data.get("text", "") for ev, data in events if ev == "text" and isinstance(data, dict)]
            combined_text = "".join(text_events)
            assert "10:00 至 21:00" in combined_text

            # 驗證 SSE 完成事件與來源
            done_events = [data for ev, data in events if ev == "done" and isinstance(data, dict)]
            assert len(done_events) == 1
            sources = done_events[0].get("sources", [])
            assert any(s.get("uri") == "https://www.tokyo-skytree.jp/" for s in sources)
            mock_search.assert_called_once()


def test_stream_chat_standard_greeting_no_search():
    """驗證純問候語：意圖為 CHAT -> 不進入搜尋工具循環 -> 直接串流回應"""
    
    chunk = MagicMock(spec=["text", "thought", "candidates"])
    chunk.text = "嗨！我是 Ryan，今天想去哪裡玩？"
    chunk.thought = None
    chunk.candidates = []

    mock_genai_client = MagicMock()
    mock_genai_client.aio.models.generate_content_stream = AsyncMock(
        return_value=MockAsyncStream([chunk])
    )

    with patch("main.genai.Client", return_value=mock_genai_client):
        with patch("main.execute_web_search", new_callable=AsyncMock) as mock_search:
            resp = client.post(
                "/api/chat/stream",
                json={
                    "message": "早安！",
                    "history": []
                },
                headers=HEADERS
            )

            assert resp.status_code == 200
            events = parse_sse_events(resp.text)

            # 驗證不觸發搜尋
            mock_search.assert_not_called()
            thinking_events = [data for ev, data in events if ev == "thinking"]
            assert not any(isinstance(d, dict) and d.get("status") == "searching" for d in thinking_events)

            text_events = [data.get("text", "") for ev, data in events if ev == "text" and isinstance(data, dict)]
            assert any("嗨！我是 Ryan" in t for t in text_events)

            done_events = [data for ev, data in events if ev == "done"]
            assert len(done_events) == 1


def test_stream_search_jina_reader_flow():
    """驗證網頁深度閱讀端到端：First Pass 發出 fetch_webpage -> 攔截 Jina Reader -> 發送 reading 思考狀態 -> 回填內文"""
    
    mock_fc_candidate = MagicMock()
    mock_fc_candidate.finish_reason = "STOP"
    
    mock_part = MagicMock()
    mock_part.text = None
    mock_part.function_call = MagicMock()
    mock_part.function_call.name = "fetch_webpage"
    mock_part.function_call.args = {"url": "https://www.tokyo-skytree.jp/hours"}
    
    mock_content = MagicMock()
    mock_content.parts = [mock_part]
    mock_fc_candidate.content = mock_content
    
    mock_first_pass = MagicMock()
    mock_first_pass.candidates = [mock_fc_candidate]
    
    mock_fc = MagicMock()
    mock_fc.name = "fetch_webpage"
    mock_fc.args = {"url": "https://www.tokyo-skytree.jp/hours"}
    mock_first_pass.function_calls = [mock_fc]

    chunk = MagicMock(spec=["text", "thought", "candidates"])
    chunk.text = "根據官網細節，晴空塔平日開放時間為 10:00。"
    chunk.thought = None
    chunk.candidates = []

    mock_reader_result = {
        "status": "success",
        "url": "https://www.tokyo-skytree.jp/hours",
        "markdown": "# 晴空塔營業時間詳細資訊\n平日 10:00-21:00，週末提早至 09:00。"
    }

    mock_genai_client = MagicMock()
    mock_genai_client.aio.models.generate_content = AsyncMock(return_value=mock_first_pass)
    mock_genai_client.aio.models.generate_content_stream = AsyncMock(
        return_value=MockAsyncStream([chunk])
    )

    with patch("main.genai.Client", return_value=mock_genai_client):
        with patch("main.fetch_jina_reader", new_callable=AsyncMock) as mock_reader:
            mock_reader.return_value = mock_reader_result

            resp = client.post(
                "/api/chat/stream",
                json={
                    "message": "查詢官網最新資訊：https://www.tokyo-skytree.jp/hours",
                    "history": []
                },
                headers=HEADERS
            )

            assert resp.status_code == 200
            events = parse_sse_events(resp.text)

            # 驗證 SSE reading 思考狀態事件
            thinking_events = [data for ev, data in events if ev == "thinking"]
            assert any(isinstance(d, dict) and d.get("status") == "reading" and "https://www.tokyo-skytree.jp/hours" in d.get("url", "") for d in thinking_events)

            # 驗證 SSE 文字串流與來源
            text_events = [data.get("text", "") for ev, data in events if ev == "text" and isinstance(data, dict)]
            combined_text = "".join(text_events)
            assert "平日開放時間" in combined_text

            done_events = [data for ev, data in events if ev == "done" and isinstance(data, dict)]
            assert len(done_events) == 1
            sources = done_events[0].get("sources", [])
            assert any(s.get("uri") == "https://www.tokyo-skytree.jp/hours" for s in sources)
            mock_reader.assert_called_once()


def test_sse_instagram_reel_with_itinerary_context():
    """
    驗證使用者開啟台北行程時發送 Instagram Reel 網址：
    1. 不受台北行程上下文污染，正確掛載 SEARCH 工具
    2. 發送 reading thinking 事件
    3. 調用 fetch_jina_reader 取得貼文資訊並成功回覆
    """
    ig_url = "https://www.instagram.com/reel/DX8x6XOtEqI/?stkn=MXZ3YWxibjJzejBtZg=="
    
    mock_part = MagicMock()
    mock_part.thought_signature = None
    mock_part.text = None
    
    mock_fc_candidate = MagicMock()
    mock_content = MagicMock()
    mock_content.parts = [mock_part]
    mock_fc_candidate.content = mock_content
    
    mock_first_pass = MagicMock()
    mock_first_pass.candidates = [mock_fc_candidate]
    
    mock_fc = MagicMock()
    mock_fc.name = "fetch_webpage"
    mock_fc.args = {"url": ig_url}
    mock_first_pass.function_calls = [mock_fc]

    chunk = MagicMock(spec=["text", "thought", "candidates"])
    chunk.text = "這段影片介紹的是位於日本大阪梅田茶屋町的「焼肉エイト」超高CP值燒肉吃到飽！"
    chunk.thought = None
    chunk.candidates = []

    mock_reader_result = {
        "status": "success",
        "url": ig_url,
        "markdown": "# 🇯🇵大阪梅田！超便宜燒肉吃到飽\n｜焼肉エイト 梅田茶屋町店｜價位¥2980起..."
    }

    mock_genai_client = MagicMock()
    mock_genai_client.aio.models.generate_content = AsyncMock(return_value=mock_first_pass)
    mock_genai_client.aio.models.generate_content_stream = AsyncMock(
        return_value=MockAsyncStream([chunk])
    )

    with patch("main.genai.Client", return_value=mock_genai_client):
        with patch("main.fetch_jina_reader", new_callable=AsyncMock) as mock_reader:
            mock_reader.return_value = mock_reader_result

            resp = client.post(
                "/api/chat/stream",
                json={
                    "message": ig_url,
                    "history": [],
                    "current_itinerary": {
                        "title": "台北 3 天 2 夜",
                        "days": [{"day": 1, "activities": [{"place": "台北車站"}]}]
                    }
                },
                headers=HEADERS
            )

            assert resp.status_code == 200
            events = parse_sse_events(resp.text)

            # 1. 驗證 thinking reading 事件
            thinking_events = [data for ev, data in events if ev == "thinking"]
            assert any(isinstance(d, dict) and d.get("status") == "reading" and ig_url in d.get("url", "") for d in thinking_events)

            # 2. 驗證文字串流
            text_events = [data.get("text", "") for ev, data in events if ev == "text" and isinstance(data, dict)]
            combined_text = "".join(text_events)
            assert "焼肉エイト" in combined_text or "大阪" in combined_text

            # 3. 驗證來源傳遞
            done_events = [data for ev, data in events if ev == "done" and isinstance(data, dict)]
            assert len(done_events) == 1
            sources = done_events[0].get("sources", [])
            assert any(s.get("uri") == ig_url for s in sources)
            mock_reader.assert_called_once()


def test_stream_itinerary_tool_calling():
    """
    驗證使用者要求加入行程時：
    1. 工具正確掛載
    2. 模型產生的 add_itinerary_item FunctionCall 能被 stream_chat_generator 完整捕獲
    3. 在 done 事件的 raw_parts 中包含 functionCall，前端可正常觸發卡片
    """
    mock_fc = MagicMock()
    mock_fc.name = "add_itinerary_item"
    mock_fc.id = "call_mock_add_123"
    mock_fc.args = {
        "day": 1,
        "place_name": "淺草寺",
        "category": "attraction",
        "desc": "東京最古老的寺廟"
    }

    chunk = MagicMock(spec=["text", "thought", "candidates", "function_calls"])
    chunk.text = "好喔！我已經幫你把淺草寺安排到第一天上午囉！"
    chunk.thought = None
    chunk.candidates = []
    chunk.function_calls = [mock_fc]

    mock_genai_client = MagicMock()
    mock_genai_client.aio.models.generate_content_stream = AsyncMock(
        return_value=MockAsyncStream([chunk])
    )

    with patch("main.genai.Client", return_value=mock_genai_client):
        resp = client.post(
            "/api/chat/stream",
            json={
                "message": "這家看起來很棒，幫我加進去",
                "history": [],
                "current_itinerary": {
                    "title": "東京 5 天 4 夜",
                    "days": [{"day": 1, "activities": []}]
                }
            },
            headers=HEADERS
        )

        assert resp.status_code == 200
        events = parse_sse_events(resp.text)

        done_events = [data for ev, data in events if ev == "done" and isinstance(data, dict)]
        assert len(done_events) == 1
        raw_parts = done_events[0].get("raw_parts", [])
        
        # 必須包含 functionCall 物件，不能只有 text
        fc_parts = [p for p in raw_parts if "functionCall" in p or "function_call" in p]
        assert len(fc_parts) > 0, f"Expected functionCall in raw_parts, got {raw_parts}"
        call_obj = fc_parts[0].get("functionCall") or fc_parts[0].get("function_call")
        assert call_obj["name"] == "add_itinerary_item"
        assert call_obj["args"]["place_name"] == "淺草寺"


def test_stream_remove_itinerary_tool_calling():
    """
    驗證使用者要求移除行程時：
    1. remove_itinerary_item 工具能被正確呼叫
    2. 在 done 事件的 raw_parts 包含該 functionCall
    """
    mock_fc = MagicMock()
    mock_fc.name = "remove_itinerary_item"
    mock_fc.id = "call_mock_remove_123"
    mock_fc.args = {
        "day": 1,
        "place_name": "晴空塔",
        "reason": "行程太趕"
    }

    chunk = MagicMock(spec=["text", "thought", "candidates", "function_calls"])
    chunk.text = "沒問題，我已經幫你把晴空塔從第一天行程中移除了！"
    chunk.thought = None
    chunk.candidates = []
    chunk.function_calls = [mock_fc]

    mock_genai_client = MagicMock()
    mock_genai_client.aio.models.generate_content_stream = AsyncMock(
        return_value=MockAsyncStream([chunk])
    )

    with patch("main.genai.Client", return_value=mock_genai_client):
        resp = client.post(
            "/api/chat/stream",
            json={
                "message": "不要去晴空塔了，幫我拿掉",
                "history": [],
                "current_itinerary": {
                    "title": "東京 5 天 4 夜",
                    "days": [{"day": 1, "activities": [{"place": "晴空塔"}]}]
                }
            },
            headers=HEADERS
        )

        assert resp.status_code == 200
        events = parse_sse_events(resp.text)

        done_events = [data for ev, data in events if ev == "done" and isinstance(data, dict)]
        assert len(done_events) == 1
        raw_parts = done_events[0].get("raw_parts", [])
        
        fc_parts = [p for p in raw_parts if "functionCall" in p or "function_call" in p]
        assert len(fc_parts) > 0, f"Expected remove functionCall, got {raw_parts}"
        call_obj = fc_parts[0].get("functionCall") or fc_parts[0].get("function_call")
        assert call_obj["name"] == "remove_itinerary_item"
        assert call_obj["args"]["place_name"] == "晴空塔"


def test_sanitize_dangling_tool_calls():
    """
    驗證歷史紀錄中的懸空 Function Call 會被自動補齊對應的 Function Response
    """
    from services.model_manager import build_chat_history
    from google.genai import types

    history = [
        {"role": "user", "displayContent": "幫我找燒肉"},
        {
            "role": "model",
            "displayContent": "推薦這家",
            "rawParts": [
                {"text": "推薦這家"},
                {"functionCall": {"name": "add_itinerary_item", "args": {"place_name": "燒肉一丁"}, "id": "call_mock_123"}}
            ]
        }
    ]

    chat_history = build_chat_history(history)
    # 原本 2 條，自動修復後應該增加第 3 條 (user role，包含 function_response)
    assert len(chat_history) == 3
    assert chat_history[0].role == "user"
    assert chat_history[1].role == "model"
    assert chat_history[2].role == "user"

    resp_part = chat_history[2].parts[0]
    assert hasattr(resp_part, 'function_response')
    assert resp_part.function_response.name == "add_itinerary_item"
    assert resp_part.function_response.response["status"] == "client_handled"
    assert resp_part.function_response.id == "call_mock_123"


def test_stream_deterministic_url_prefetching():
    """
    驗證訊息中含有 URL 時，確定性主動爬取網頁，並以對稱虛擬呼叫合法注入 contents
    """
    chunk = MagicMock(spec=["text", "thought", "candidates"])
    chunk.text = "這家是位於大阪的超人氣燒肉店！"
    chunk.thought = None
    chunk.candidates = []

    mock_genai_client = MagicMock()
    mock_genai_client.aio.models.generate_content = AsyncMock(return_value=None)
    mock_genai_client.aio.models.generate_content_stream = AsyncMock(
        return_value=MockAsyncStream([chunk])
    )

    fake_page = {
        "title": "298 心齋橋店",
        "url": "https://www.instagram.com/reel/DClDc19IyWV/",
        "markdown": "# 298 心齋橋店\n大阪平價燒肉吃到飽"
    }

    with patch("main.genai.Client", return_value=mock_genai_client), \
         patch("main.fetch_jina_reader", AsyncMock(return_value=fake_page)) as mock_reader:
        
        resp = client.post(
            "/api/chat/stream",
            json={
                "message": "幫我看這家 https://www.instagram.com/reel/DClDc19IyWV/",
                "history": [],
            },
            headers=HEADERS
        )

        assert resp.status_code == 200
        events = parse_sse_events(resp.text)

        # 1. 必須有 reading 狀態的 thinking 事件
        reading_events = [data for ev, data in events if ev == "thinking" and isinstance(data, dict) and data.get("status") == "reading"]
        assert len(reading_events) >= 1
        assert "instagram.com" in reading_events[0]["url"]

        # 2. mock_reader 必須被呼叫
        mock_reader.assert_called_once()

        # 3. 傳入 generate_content_stream 的 contents 必須包含安全的 RAG Grounding Context
        call_args = mock_genai_client.aio.models.generate_content_stream.call_args
        stream_contents = call_args.kwargs.get("contents")
        
        # 檢查 contents 結尾的 User Part 是否包含網頁資訊與標題
        user_content = stream_contents[-1]
        assert user_content.role == "user"
        user_text = user_content.parts[0].text
        assert "298 心齋橋店" in user_text
        assert "系統即時解析外部網頁資訊" in user_text


