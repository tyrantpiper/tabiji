import pytest
from google.genai import types
from services.intent_router import _fast_path_classify, PRAISE_PATTERN
from services.model_manager import enforce_strict_alternating_turns
from services.temporal_service import format_temporal_header

def test_praise_pattern_taiwanese_colloquial():
    """驗證台式口語短語讚美 100% 命中 Fast-Path CHAT 意圖"""
    phrases = [
        "不賴欸",
        "不錯喔",
        "真不賴",
        "很不錯",
        "可以喔",
        "水啦",
        "水喔",
        "屌喔",
        "給過",
        "行喔",
        "牛逼",
        "你很棒",
        "做得好",
        "謝謝你",
        "thx",
        "thanks a lot"
    ]
    for p in phrases:
        assert _fast_path_classify(p) == "CHAT", f"Phrase failed: {p}"

def test_enforce_strict_alternating_turns():
    """驗證交替回合守護器能徹底消除連續相同角色，防止 Gemini 400"""
    # 案例 1: 連續 user 與連續 model
    history = [
        types.Content(role="user", parts=[types.Part.from_text(text="u1")]),
        types.Content(role="user", parts=[types.Part.from_text(text="u2")]),
        types.Content(role="model", parts=[types.Part.from_text(text="m1")]),
        types.Content(role="model", parts=[types.Part.from_text(text="m2")]),
        types.Content(role="user", parts=[types.Part.from_text(text="u3")]),
    ]
    sanitized = enforce_strict_alternating_turns(history)
    assert len(sanitized) == 3
    assert sanitized[0].role == "user"
    assert len(sanitized[0].parts) == 2
    assert sanitized[1].role == "model"
    assert len(sanitized[1].parts) == 2
    assert sanitized[2].role == "user"

    # 案例 2: 以 model 開頭自動補 user 啟動
    history_model_start = [
        types.Content(role="model", parts=[types.Part.from_text(text="m0")]),
        types.Content(role="user", parts=[types.Part.from_text(text="u1")]),
    ]
    sanitized2 = enforce_strict_alternating_turns(history_model_start)
    assert len(sanitized2) == 3
    assert sanitized2[0].role == "user"
    assert sanitized2[1].role == "model"
    assert sanitized2[2].role == "user"

def test_persona_boundary_guard_in_temporal_header():
    """驗證時間感知區塊注入了擬人化隱私約束指令"""
    mock_info = {
        "client_time_str": "2026-11-10 20:00",
        "client_weekday": "週二",
        "client_tz": "Asia/Taipei",
        "dest_time_str": "2026-11-10 20:00",
        "dest_weekday": "週二",
        "dest_tz": "Asia/Taipei",
        "is_different_tz": False,
        "lifecycle_desc": "行程已於 2026/03/12 結束",
        "is_today_completed": False,
        "current_day_number": None
    }
    header_zh = format_temporal_header(mock_info, locale="zh")
    assert "最高隱私與擬人守則" in header_zh
    assert "嚴禁在對話中向使用者背誦或解釋內部系統字眼" in header_zh

    header_en = format_temporal_header(mock_info, locale="en")
    assert "Persona Privacy Guard" in header_en
    assert "NEVER reveal or recite internal system terms" in header_en


def test_generate_dynamic_accompanying_text_edge_cases():
    """驗證多態動態伴隨文字生成器之異常免疫與多工具組合"""
    from main import generate_dynamic_accompanying_text

    # 1. 畸形與 None 輸入
    assert "互動卡片" in generate_dynamic_accompanying_text(None, is_en=False)
    assert "interactive preview cards" in generate_dynamic_accompanying_text([], is_en=True) or "details below" in generate_dynamic_accompanying_text([], is_en=True)
    assert "互動卡片" in generate_dynamic_accompanying_text("not-a-list", is_en=False)  # type: ignore
    assert "互動卡片" in generate_dynamic_accompanying_text([None, "corrupt_string"], is_en=False)  # type: ignore
    assert "互動卡片" in generate_dynamic_accompanying_text([{"function_call": "not-a-dict"}], is_en=False)

    # 2. add_itinerary_item 帶有扁平字串陣列 items (LLM 常見非標準格式，杜絕 AttributeError)
    fcs_str_items = [{
        "function_call": {
            "name": "add_itinerary_item",
            "args": {"items": ["淺草寺", "東京晴空塔"]}
        }
    }]
    res_str = generate_dynamic_accompanying_text(fcs_str_items, is_en=False)
    assert "淺草寺" in res_str
    assert "東京晴空塔" in res_str

    # 3. add_expense 完整與缺省欄位
    fcs_expense = [{
        "function_call": {
            "name": "add_expense",
            "args": {"title": "一蘭拉麵", "amount": 980, "currency": "JPY"}
        }
    }]
    res_exp_zh = generate_dynamic_accompanying_text(fcs_expense, is_en=False)
    assert "一蘭拉麵 (JPY 980)" in res_exp_zh
    assert "記帳卡片" in res_exp_zh

    res_exp_en = generate_dynamic_accompanying_text(fcs_expense, is_en=True)
    assert "一蘭拉麵 (JPY 980)" in res_exp_en
    assert "expense" in res_exp_en

    # 4. remove_itinerary_item
    fcs_remove = [{
        "function_call": {
            "name": "remove_itinerary_item",
            "args": {"place_name": "舊行程點"}
        }
    }]
    res_rem = generate_dynamic_accompanying_text(fcs_remove, is_en=False)
    assert "舊行程點" in res_rem
    assert "刪除" in res_rem

    # 5. 多工具組合 (記帳 + 行程)
    fcs_multi = [
        {"function_call": {"name": "add_expense", "args": {"title": "晚餐", "amount": 1200, "currency": "TWD"}}},
        {"function_call": {"name": "add_itinerary_item", "args": {"place_name": "夜市"}}}
    ]
    res_multi = generate_dynamic_accompanying_text(fcs_multi, is_en=False)
    assert "晚餐 (TWD 1200)" in res_multi
    assert "夜市" in res_multi


def test_get_rate_limit_key_isolation_and_fallbacks():
    """驗證 SlowAPI Rate Limiter Key 函數之雜湊隔離與安全回退"""
    import hashlib
    from starlette.requests import Request
    from utils.limiter import get_rate_limit_key

    # 1. 帶有合法 X-Gemini-API-Key
    test_key = "AIzaSy_Secret_Test_Key_12345"
    expected_hash = hashlib.sha256(test_key.encode("utf-8")).hexdigest()[:16]
    req1 = Request({"type": "http", "headers": [(b"x-gemini-api-key", test_key.encode("utf-8"))]})
    assert get_rate_limit_key(req1) == f"key:{expected_hash}"

    # 2. 帶有空白/全空白金鑰 → 安全回退至 IP
    req2 = Request({"type": "http", "headers": [(b"x-gemini-api-key", b"   ")], "client": ("192.168.1.50", 8080)})
    assert get_rate_limit_key(req2) == "192.168.1.50"

    # 3. 未攜帶金鑰 → 安全回退至 IP
    req3 = Request({"type": "http", "headers": [], "client": ("10.0.0.1", 9999)})
    assert get_rate_limit_key(req3) == "10.0.0.1"


