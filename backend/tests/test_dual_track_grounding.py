# -*- coding: utf-8 -*-
"""
Dual-Track Grounding & Citation Alignment Integration Tests
==========================================================
Verifies:
1. Destination detection & dual query rewriting
2. AC-2 noise blacklist & domain classification
3. AC-4 anchored index citation pruning
4. End-to-end SSE stream generation with dual-perspective grounding
"""

import pytest
import sys
import os
import json
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from main import app
from services.destination_taxonomy import (
    generate_dual_queries,
    classify_and_filter_results,
    prune_and_align_citations
)

client = TestClient(app)

HEADERS = {
    "X-Gemini-API-Key": "AIzaSy" + "C" * 34,
    "Content-Type": "application/json"
}


class MockAsyncStream:
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


def test_dual_track_grounding_stream_e2e():
    """驗證雙軌搜尋 Grounding 端到端：SEARCH 意圖 -> 雙軌檢索 -> AC-2 過濾 -> 注入 Prompt -> AC-4 引文對齊"""
    
    chunk = MagicMock(spec=["text", "thought", "candidates"])
    chunk.text = "在台北，在地人推薦阜杭豆漿[1]，而國際旅客常在 Reddit 推薦鼎泰豐與饒河夜市[2]。"
    chunk.thought = None
    chunk.candidates = []

    mock_genai_client = MagicMock()
    # First-pass returns None to simulate fallback to deterministic dual-track
    mock_genai_client.aio.models.generate_content = AsyncMock(return_value=None)
    mock_genai_client.aio.models.generate_content_stream = AsyncMock(
        return_value=MockAsyncStream([chunk])
    )

    mock_search_results = [
        {"title": "阜杭豆漿 PTT 美食版熱議", "url": "https://www.ptt.cc/bbs/Food/M.123.html", "snippet": "排隊必吃的燒餅油條"},
        {"title": "Taipei food recommendations on Reddit", "url": "https://www.reddit.com/r/travel/comments/xyz", "snippet": "Din Tai Fung and Raohe Night Market are must-visits."},
        {"title": "警察專科學校第40期研討會論壇", "url": "https://police.example.com/symposium", "snippet": "研討會圓滿閉幕"}, # AC-2 雜訊
        {"title": "台北景點推薦未被引用之部落格", "url": "https://blog.example.com/not-cited", "snippet": "這篇文章沒被 LLM 引用"} # AC-4 應被修剪
    ]

    with patch("main.genai.Client", return_value=mock_genai_client), \
         patch("main.classify_chat_intent", new_callable=AsyncMock, return_value=("SEARCH", {})), \
         patch("main.execute_web_search", new_callable=AsyncMock) as mock_search:
        
        mock_search.return_value = mock_search_results

        resp = client.post(
            "/api/chat/stream",
            json={
                "message": "台北有什麼在地美食與國際旅客推薦？",
                "history": []
            },
            headers=HEADERS
        )

        assert resp.status_code == 200
        events = parse_sse_events(resp.text)

        # 1. 驗證 thinking searching 事件
        thinking_events = [data for ev, data in events if ev == "thinking"]
        assert any(isinstance(d, dict) and d.get("status") == "searching" for d in thinking_events)

        # 2. 驗證文字串流
        text_events = [data.get("text", "") for ev, data in events if ev == "text" and isinstance(data, dict)]
        combined_text = "".join(text_events)
        assert "阜杭豆漿[1]" in combined_text
        assert "饒河夜市[2]" in combined_text

        # 3. 驗證 AC-2 雜訊過濾與 AC-4 引文對齊
        done_events = [data for ev, data in events if ev == "done" and isinstance(data, dict)]
        assert len(done_events) == 1
        sources = done_events[0].get("sources", [])
        
        # 雜訊「警察」必須被物理過濾
        assert not any("警察" in s.get("title", "") for s in sources)
        
        # 內文僅引用 [1] 和 [2]，未被引用的第 4 筆來源必須被 AC-4 修剪
        assert len(sources) == 2
        assert sources[0]["citation_index"] == 1
        assert "ptt.cc" in sources[0]["uri"]
        assert sources[0]["category"] == "local_forum"
        assert sources[1]["citation_index"] == 2
        assert "reddit.com" in sources[1]["uri"]
        assert sources[1]["category"] == "global_forum"


def test_anchored_citation_index_preservation():
    """驗證錨定索引穩定性：當僅引用 [3] 時，返回的 Sources 必須保持 citation_index=3，絕不變異重整為 1"""
    candidates = [
        {"title": "來源一", "url": "https://s1.com", "snippet": "s1", "category": "official", "badge": {"text": "官方", "color": "green"}},
        {"title": "來源二", "url": "https://s2.com", "snippet": "s2", "category": "review", "badge": {"text": "老饕", "color": "orange"}},
        {"title": "來源三 (唯一被引用)", "url": "https://s3.com", "snippet": "s3", "category": "global_forum", "badge": {"text": "Reddit", "color": "amber"}}
    ]
    
    text = "根據最新國際旅人討論，這個秘境非常值得造訪[3]。"
    pruned = prune_and_align_citations(text, candidates)
    
    assert len(pruned) == 1
    assert pruned[0]["citation_index"] == 3
    assert pruned[0]["uri"] == "https://s3.com"
    assert pruned[0]["category"] == "global_forum"
