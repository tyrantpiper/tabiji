import asyncio
import json
import pytest

from services.stream_sanitizer import StreamLookaheadSanitizer


def run_sanitizer(chunks):
    """Helper to run StreamLookaheadSanitizer across a sequence of string chunks."""
    sanitizer = StreamLookaheadSanitizer(window_size=30)
    emitted = []
    for c in chunks:
        emitted.extend(sanitizer.feed(c))
    tail, parsed_json = sanitizer.flush()
    emitted.extend(tail)
    return "".join(emitted), parsed_json


def test_normal_text_with_brackets():
    chunks = ["前往參觀 (10:00 - 12:00) ", "門票標記為 {免費入場}。", "祝你玩得開心！"]
    text, json_res = run_sanitizer(chunks)
    assert text == "前往參觀 (10:00 - 12:00) 門票標記為 {免費入場}。祝你玩得開心！"
    assert json_res is None


def test_split_thought_tags():
    chunks = ["你好！", "<thought>Thinking about Bangkok", " places</thought>曼谷是個很棒的城市！"]
    text, json_res = run_sanitizer(chunks)
    assert text == "你好！曼谷是個很棒的城市！"
    assert "<thought>" not in text
    assert json_res is None


def test_split_json_items_across_chunks():
    chunks = [
        "這是推薦的景點：\n",
        "{\n  ",
        '"items": [\n    {\n      "day": 1,\n      "place_name": "班嘉奇蒂公園"\n    }\n  ]\n}'
    ]
    text, fc = run_sanitizer(chunks)
    assert text.strip() == "這是推薦的景點："
    assert fc is not None
    assert fc["items"][0]["place_name"] == "班嘉奇蒂公園"


def test_stream_lookahead_sanitizer_preserves_trailing_text_after_json():
    """
    CRITICAL INVARIANT: 確保 JSON 區塊之後的所有結尾說明文字 100% 被保留，
    絕對不因 in_json 狀態未閉合而丟失結尾語！
    """
    chunks = [
        "這是我為您推薦的景點：\n",
        "```json\n{\n  ",
        '"items": [\n    {\n      "day": 1,\n      "place_name": "淺草寺",\n      "category": "attraction"\n    }\n  ]\n}\n```\n',
        "淺草寺是東京最古老的寺廟，周邊的仲見世商店街有很多美食！祝你有個愉快的旅程！"
    ]
    text, fc = run_sanitizer(chunks)
    assert "這是我為您推薦的景點：" in text
    assert "淺草寺是東京最古老的寺廟，周邊的仲見世商店街有很多美食！祝你有個愉快的旅程！" in text
    assert "```json" not in text
    assert '{"items":' not in text
    assert fc is not None
    assert fc["items"][0]["place_name"] == "淺草寺"


def test_multiple_flat_json_with_interstitial_text():
    """
    AC-Parallel-2: 支援多個單層扁平 JSON 物件 (Gemma 4 平行工具輸出) 及其間隔文字，
    自動合併為標準 items 清單，且保留所有段落文字。
    """
    chunks = [
        "曼谷熱門景點推薦：\n",
        '{"day": 1, "place_name": "臥佛寺", "category": "temple"}\n',
        "另外還有這個必去：\n",
        '{"day": 1, "place_name": "大皇宮", "category": "palace"}\n',
        "這兩個景點相距很近，可以安排在同一天前往喔！"
    ]
    text, fc = run_sanitizer(chunks)
    assert "曼谷熱門景點推薦：" in text
    assert "另外還有這個必去：" in text
    assert "這兩個景點相距很近，可以安排在同一天前往喔！" in text
    assert fc is not None
    assert len(fc["items"]) == 2
    assert fc["items"][0]["place_name"] == "臥佛寺"
    assert fc["items"][1]["place_name"] == "大皇宮"


def test_stream_lookahead_sanitizer_split_closing_thought():
    chunks = [
        "你好！",
        "<thought>Thinking step 1...",
        " step 2</th",
        "ought>祝你有美好的一天！"
    ]
    text, fc = run_sanitizer(chunks)
    assert text == "你好！祝你有美好的一天！"
    assert fc is None
