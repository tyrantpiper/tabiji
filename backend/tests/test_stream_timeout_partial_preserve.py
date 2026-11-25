import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import main as backend_main
from services import model_manager


def _make_text_chunk(text: str):
    chunk = MagicMock(spec=["text", "thought", "candidates"])
    chunk.text = text
    chunk.thought = None
    chunk.candidates = []
    return chunk


class _TimedChunkStream:
    """Async iterator emitting (delay_sec, chunk_or_exc) items."""

    def __init__(self, steps):
        self._steps = list(steps)

    def __aiter__(self):
        self._idx = 0
        return self

    async def __anext__(self):
        if self._idx >= len(self._steps):
            raise StopAsyncIteration
        delay, item = self._steps[self._idx]
        self._idx += 1
        if delay > 0:
            await asyncio.sleep(delay)
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.mark.asyncio
async def test_active_stream_survives_past_first_output_timeout_while_chunks_keep_flowing():
    """Once visible output begins flowing, stream must NOT be decapitated at initial stream_timeout (e.g. 45s)."""
    # stream_timeout=0.12s, idle_timeout=0.20s, total_cap=0.60s:
    # chunks arrive every 0.06s over ~0.24s (> 0.12s initial timeout) -> MUST complete cleanly with event: done!
    stream = _TimedChunkStream([
        (0.02, _make_text_chunk("大阪梅田這家超人氣燒肉店「焼肉エイト」位於茶屋町大樓三樓，")),
        (0.06, _make_text_chunk("提供中文手機點餐介面，價格親民且座位寬敞非常適合多人旅遊聚餐。")),
        (0.06, _make_text_chunk("建議避開尖峰晚餐時段或提前預約，整體 CP 值極高！")),
        (0.06, _make_text_chunk("另外步行五分鐘即可到達梅田藍天大廈看夜景。")),
    ])

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(return_value=stream)

    with patch.object(backend_main.genai, "Client", return_value=mock_client), \
         patch.object(backend_main, "classify_chat_intent", AsyncMock(return_value=("CHAT", []))), \
         patch.object(backend_main, "build_effective_routing", return_value=["gemini-3.6-flash", "gemini-3.1-flash-lite"]), \
         patch.object(backend_main, "_get_call_timeout", return_value=0.12), \
         patch.object(backend_main, "_STREAM_IDLE_CHUNK_TIMEOUT", 0.20), \
         patch.object(backend_main, "_STREAM_ACTIVE_TOTAL_CAP", 0.60):
        events = []
        async for ev in backend_main.stream_chat_generator(
            api_key="AIzaSyStreamActiveSurvives1234567890",
            history=[],
            message="介紹一下大阪梅田燒肉",
            raw_user_message="介紹一下大阪梅田燒肉",
            locale="zh-TW",
        ):
            events.append(ev)

    joined = "".join(events)
    assert "event: reset" not in joined
    assert "event: error" not in joined
    assert "event: done" in joined
    assert mock_client.aio.models.generate_content_stream.await_count == 1
    done_line = [ev for ev in events if ev.startswith("event: done")][0]
    done_payload = json.loads(done_line.split("data:", 1)[1].strip())
    assert "梅田藍天大廈" in done_payload["raw_parts"][0]["text"]


@pytest.mark.asyncio
async def test_substantial_partial_output_preserved_without_reset_on_midstream_idle_timeout():
    """When >= _STREAM_PRESERVE_PARTIAL_MIN_CHARS are already shown, mid-stream stall must preserve text (no event: reset, no fallback cascade)."""
    long_prefix = (
        "大阪梅田茶屋町三樓的「焼肉エイト」是當地高人氣的平價和牛燒肉吃到飽餐廳，"
        "提供繁體中文手機點餐系統，肉質穩定且客席座位寬敞，無論兩人旅遊或家庭多人同行都非常適合。"
        "除了招牌黑毛和牛之外，店內還提供多款醃漬橫膈膜、牛舌、豬五花、冷麵與甜點可以無限加點，"
        "午餐與平日晚餐時段 CP 值特別突出，建議提前預約或在開店前十到十五分鐘現場排隊入場，飯後還可步行順遊梅田藍天大廈。"
    )
    assert len(long_prefix) >= 175  # ensures >= 140 chars already emitted past 30-char sanitizer window

    # Emits long_prefix immediately, then stalls past idle timeout (0.08s)
    stream = _TimedChunkStream([
        (0.01, _make_text_chunk(long_prefix)),
        (0.25, _make_text_chunk("這段不會在逾時前到達")),
    ])

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = AsyncMock(return_value=stream)

    with patch.object(backend_main.genai, "Client", return_value=mock_client), \
         patch.object(backend_main, "classify_chat_intent", AsyncMock(return_value=("CHAT", []))), \
         patch.object(backend_main, "build_effective_routing", return_value=["gemini-3.6-flash", "gemini-3.1-flash-lite", "gemma-4-31b-it"]), \
         patch.object(backend_main, "_get_call_timeout", return_value=0.10), \
         patch.object(backend_main, "_STREAM_IDLE_CHUNK_TIMEOUT", 0.08), \
         patch.object(backend_main, "_STREAM_ACTIVE_TOTAL_CAP", 1.0):
        events = []
        async for ev in backend_main.stream_chat_generator(
            api_key="AIzaSyStreamPartialPreserve123456789",
            history=[],
            message="介紹這篇燒肉貼文",
            raw_user_message="介紹這篇燒肉貼文",
            locale="zh-TW",
        ):
            events.append(ev)

    joined = "".join(events)
    assert "event: reset" not in joined
    assert "event: error" in joined
    assert '"partial_preserved": true' in joined
    assert '"code": 504' in joined
    # Must NOT fall back to 2nd/3rd models after preserving substantial partial text
    assert mock_client.aio.models.generate_content_stream.await_count == 1
    # Emitted text includes flushed tail from sanitizer too
    text_chunks = [
        json.loads(ev.split("data:", 1)[1].strip())["text"]
        for ev in events
        if ev.startswith("event: text")
    ]
    assert "".join(text_chunks) == long_prefix


@pytest.mark.asyncio
async def test_first_output_timeout_still_fails_fast_and_falls_back():
    """If model stalls BEFORE emitting any visible output, initial stream_timeout must still fail fast and switch to fallback."""
    call_count = 0

    async def _fake_stream(*, model, contents, config):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _TimedChunkStream([
                (0.25, _make_text_chunk("too late")),
            ])
        return _TimedChunkStream([
            (0.01, _make_text_chunk("已切換備援模型順利完成回覆！")),
        ])

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = _fake_stream

    with patch.object(backend_main.genai, "Client", return_value=mock_client), \
         patch.object(backend_main, "classify_chat_intent", AsyncMock(return_value=("CHAT", []))), \
         patch.object(backend_main, "build_effective_routing", return_value=["gemini-3.6-flash", "gemini-3.1-flash-lite"]), \
         patch.object(backend_main, "_get_call_timeout", return_value=0.08), \
         patch.object(backend_main, "_STREAM_IDLE_CHUNK_TIMEOUT", 0.20), \
         patch.object(backend_main, "_STREAM_ACTIVE_TOTAL_CAP", 1.0):
        events = []
        async for ev in backend_main.stream_chat_generator(
            api_key="AIzaSyStreamTTFTFallback12345678901",
            history=[],
            message="推薦京都咖啡廳",
            raw_user_message="推薦京都咖啡廳",
            locale="zh-TW",
        ):
            events.append(ev)

    joined = "".join(events)
    assert call_count == 2
    assert "event: reset" not in joined  # nothing emitted before TTFT timeout
    assert "event: done" in joined
    done_line = [ev for ev in events if ev.startswith("event: done")][0]
    done_payload = json.loads(done_line.split("data:", 1)[1].strip())
    assert "已切換備援模型順利完成回覆" in done_payload["raw_parts"][0]["text"]


@pytest.mark.asyncio
async def test_short_partial_output_on_midstream_timeout_still_resets_and_falls_back():
    """When emitted text is short (< _STREAM_PRESERVE_PARTIAL_MIN_CHARS), mid-stream timeout still resets and tries fallback."""
    call_count = 0

    async def _fake_stream(*, model, contents, config):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _TimedChunkStream([
                (0.01, _make_text_chunk("這是一段超過三十字前瞻緩衝但還不到一百四十字的簡短開頭文字，剛好模擬剛吐一點字就斷線的情況。")),
                (0.25, _make_text_chunk("never arrives")),
            ])
        return _TimedChunkStream([
            (0.01, _make_text_chunk("備援模型完整重答：推薦您前往清水寺與二年坂散步。")),
        ])

    mock_client = MagicMock()
    mock_client.aio.models.generate_content_stream = _fake_stream

    with patch.object(backend_main.genai, "Client", return_value=mock_client), \
         patch.object(backend_main, "classify_chat_intent", AsyncMock(return_value=("CHAT", []))), \
         patch.object(backend_main, "build_effective_routing", return_value=["gemini-3.6-flash", "gemini-3.1-flash-lite"]), \
         patch.object(backend_main, "_get_call_timeout", return_value=0.10), \
         patch.object(backend_main, "_STREAM_IDLE_CHUNK_TIMEOUT", 0.08), \
         patch.object(backend_main, "_STREAM_ACTIVE_TOTAL_CAP", 1.0):
        events = []
        async for ev in backend_main.stream_chat_generator(
            api_key="AIzaSyStreamShortReset1234567890123",
            history=[],
            message="推薦京都散步路線",
            raw_user_message="推薦京都散步路線",
            locale="zh-TW",
        ):
            events.append(ev)

    joined = "".join(events)
    assert call_count == 2
    assert "event: reset" in joined
    assert "event: done" in joined
    done_line = [ev for ev in events if ev.startswith("event: done")][0]
    done_payload = json.loads(done_line.split("data:", 1)[1].strip())
    assert "清水寺與二年坂" in done_payload["raw_parts"][0]["text"]
    assert "簡短開頭文字" not in done_payload["raw_parts"][0]["text"]
