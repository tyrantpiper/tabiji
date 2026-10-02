"""
Unit tests for Temporal Service & Temporal Awareness in Tabidachi
"""

import pytest
from datetime import datetime, time
import zoneinfo

from services.temporal_service import (
    safe_get_zoneinfo,
    infer_destination_timezone,
    parse_time_slot,
    calculate_temporal_itinerary_context,
    format_temporal_header,
    query_world_time,
)


def test_safe_get_zoneinfo():
    """驗證時區安全解析與非法降級"""
    tz1 = safe_get_zoneinfo("Asia/Tokyo")
    assert str(tz1) == "Asia/Tokyo"

    # 非法時區不拋異常，安全降級為預設時區
    tz2 = safe_get_zoneinfo("Invalid/Random_Zone_123")
    assert str(tz2) == "Asia/Taipei"

    # None 或空字串安全回退
    tz3 = safe_get_zoneinfo(None, fallback="UTC")
    assert str(tz3) == "UTC"


def test_infer_destination_timezone():
    """驗證目的地時區智能推斷"""
    # 1. 標題包含日本東京
    itinerary_jp = {"title": "東京賞櫻五日遊", "destination": "東京"}
    assert infer_destination_timezone(itinerary_jp) == "Asia/Tokyo"

    # 2. 包含法國巴黎
    itinerary_fr = {"title": "歐洲蜜月", "dest_country": "法國", "dest_city": "巴黎"}
    assert infer_destination_timezone(itinerary_fr) == "Europe/Paris"

    # 3. 包含英國倫敦
    itinerary_uk = {"title": "倫敦大英博物館漫步", "destination": "London"}
    assert infer_destination_timezone(itinerary_uk) == "Europe/London"

    # 4. 無匹配時安全回退至使用者時區
    itinerary_unknown = {"title": "未知外星旅行", "destination": "Mars"}
    assert infer_destination_timezone(itinerary_unknown, client_tz_str="Asia/Taipei") == "Asia/Taipei"


def test_parse_time_slot():
    """驗證活動時間字串解析與容錯"""
    # 單一時間點
    t_start, t_end = parse_time_slot("09:30")
    assert t_start == time(9, 30)
    assert t_end is None

    # 區間時間點
    t_start, t_end = parse_time_slot("14:00~16:30")
    assert t_start == time(14, 0)
    assert t_end == time(16, 30)

    # 帶文字說明容錯
    t_start, t_end = parse_time_slot("18:30 (預約拉麵)")
    assert t_start == time(18, 30)
    assert t_end is None

    # 無時間格式或模糊字串
    t_start, t_end = parse_time_slot("下午彈性安排")
    assert t_start is None
    assert t_end is None


def test_calculate_temporal_context_lifecycle_stages():
    """驗證行程全週期生命週期判定 (BEFORE / IN_TRIP / AFTER)"""
    mock_itinerary = {
        "title": "京都楓葉季",
        "destination": "京都",
        "start_date": "2026-10-10",
        "end_date": "2026-10-15",
        "total_days": 6,
        "days": [
            {"day_number": 1, "items": [{"place": "清水寺", "time": "09:00"}]},
            {"day_number": 2, "items": [{"place": "金閣寺", "time": "10:00"}]}
        ]
    }

    # 1. 出發前倒數 (2026-10-02 -> 出發 10-10，倒數 8 天)
    ctx_before = calculate_temporal_itinerary_context(
        mock_itinerary,
        client_time_iso="2026-10-02T19:30:00+08:00",
        client_tz_str="Asia/Taipei"
    )
    assert ctx_before["lifecycle_stage"] == "BEFORE_TRIP"
    assert "距離出發還有 8 天" in ctx_before["lifecycle_desc"]

    # 2. 旅行進行中 (2026-10-11 -> 第 2 天)
    ctx_in = calculate_temporal_itinerary_context(
        mock_itinerary,
        client_time_iso="2026-10-11T12:00:00+09:00",
        client_tz_str="Asia/Tokyo"
    )
    assert ctx_in["lifecycle_stage"] == "IN_TRIP"
    assert ctx_in["current_day_number"] == 2
    assert "第 2 天" in ctx_in["lifecycle_desc"]

    # 3. 旅行結束回顧 (2026-10-18 -> 已過期 3 天)
    ctx_after = calculate_temporal_itinerary_context(
        mock_itinerary,
        client_time_iso="2026-10-18T10:00:00+08:00",
        client_tz_str="Asia/Taipei"
    )
    assert ctx_after["lifecycle_stage"] == "AFTER_TRIP"
    assert "已結束 3 天" in ctx_after["lifecycle_desc"]


def test_calculate_temporal_context_progress_tagging():
    """驗證當日活動進度標註與跨夜容錯"""
    mock_itinerary = {
        "title": "東京夜生活",
        "destination": "東京",
        "start_date": "2026-10-02",
        "end_date": "2026-10-02",
        "total_days": 1,
        "days": [
            {
                "day_number": 1,
                "items": [
                    {"place": "早午餐", "time": "10:00~11:30"},
                    {"place": "居酒屋", "time": "23:00~01:30"}, # 跨午夜
                    {"place": "回飯店休息", "time": "02:00"}
                ]
            }
        ]
    }

    # 時間為東京時間 23:30 (已過早午餐，居酒屋進行中，回飯店待進行)
    ctx_midnight = calculate_temporal_itinerary_context(
        mock_itinerary,
        client_time_iso="2026-10-02T22:30:00+08:00", # 台北 22:30 -> 東京 23:30
        client_tz_str="Asia/Taipei",
        focused_day=1
    )
    assert ctx_midnight["is_different_tz"] is True
    assert ctx_midnight["time_diff_hours"] == 1.0

    items_tags = {it["place"]: it["tag"] for it in ctx_midnight["items_progress"]}
    assert items_tags["早午餐"] == "[已過]"
    assert items_tags["居酒屋"] == "[📍 進行中]"
    assert items_tags["回飯店休息"] == "[待進行]"
    assert ctx_midnight["is_today_completed"] is False


def test_calculate_temporal_context_all_completed():
    """驗證當日活動全數結束時的標註"""
    mock_itinerary = {
        "title": "一日遊",
        "destination": "台北",
        "start_date": "2026-10-02",
        "end_date": "2026-10-02",
        "total_days": 1,
        "days": [
            {
                "day_number": 1,
                "items": [
                    {"place": "早餐", "time": "08:00"},
                    {"place": "午餐", "time": "12:00"}
                ]
            }
        ]
    }

    # 台北時間 18:00 (所有活動皆已過)
    ctx_done = calculate_temporal_itinerary_context(
        mock_itinerary,
        client_time_iso="2026-10-02T18:00:00+08:00",
        client_tz_str="Asia/Taipei"
    )
    assert ctx_done["is_today_completed"] is True


def test_query_world_time():
    """驗證世界時間查詢工具"""
    res_london = query_world_time("London")
    assert res_london["timezone"] == "Europe/London"
    assert "London 當前時間為" in res_london["formatted"]

    res_ny = query_world_time("New York")
    assert res_ny["timezone"] == "America/New_York"
    assert "New York 當前時間為" in res_ny["formatted"]


def test_format_temporal_header_contains_vital_info():
    """驗證產出的 Header 包含時區、時間與狀態"""
    temporal_info = {
        "client_time_str": "2026-10-02 19:30",
        "client_weekday": "週五",
        "client_tz": "Asia/Taipei",
        "dest_time_str": "2026-10-02 20:30",
        "dest_weekday": "週五",
        "dest_tz": "Asia/Tokyo",
        "time_diff_hours": 1.0,
        "is_different_tz": True,
        "lifecycle_desc": "🚀 旅行進行中 (今天是旅程第 1 天)",
        "is_today_completed": True,
        "current_day_number": 1
    }

    header = format_temporal_header(temporal_info)
    assert "【即時時間基準】" in header
    assert "Asia/Taipei" in header
    assert "Asia/Tokyo" in header
    assert "目的地時差 +1 小時" in header
    assert "【今日排定活動已全部結束】" in header


def test_chat_request_schema_supports_temporal_fields():
    """驗證 ChatRequest 模型支援 client_time 與 client_timezone 欄位"""
    from models.base import ChatRequest

    req = ChatRequest(
        message="現在行程結束了嗎？",
        client_time="2026-10-02T19:30:00+08:00",
        client_timezone="Asia/Taipei"
    )
    assert req.client_time == "2026-10-02T19:30:00+08:00"
    assert req.client_timezone == "Asia/Taipei"


def test_format_itinerary_context_without_itinerary():
    """驗證無行程時依然正確回傳即時時間與時區 header"""
    from main import format_itinerary_context

    ctx = format_itinerary_context(
        itinerary=None,
        client_time="2026-10-02T19:30:00+08:00",
        client_timezone="Asia/Taipei"
    )
    assert "--- SYSTEM CONTEXT: TEMPORAL & ITINERARY NEURAL AWARENESS ---" in ctx
    assert "2026-10-02 19:30" in ctx
    assert "Asia/Taipei" in ctx


def test_format_itinerary_context_with_itinerary_and_tags():
    """驗證有行程時能正確注入標題、時間標籤與活動進度"""
    from main import format_itinerary_context

    mock_itinerary = {
        "title": "東京暴走團",
        "destination": "東京",
        "start_date": "2026-10-02",
        "end_date": "2026-10-04",
        "total_days": 3,
        "days": [
            {
                "day_number": 1,
                "date": "2026-10-02",
                "items": [
                    {"place": "晴空塔", "time": "10:00", "category": "sightseeing"},
                    {"place": "六本木夜景", "time": "21:00", "category": "sightseeing"}
                ]
            }
        ]
    }

    # 東京時間 20:30 (晴空塔已過，六本木待進行)
    ctx = format_itinerary_context(
        itinerary=mock_itinerary,
        focused_day=1,
        client_time="2026-10-02T19:30:00+08:00", # 台北 19:30 -> 東京 20:30
        client_timezone="Asia/Taipei"
    )
    assert "東京暴走團" in ctx
    assert "晴空塔 [已過]" in ctx
    assert "六本木夜景 [待進行]" in ctx


def test_infer_destination_timezone_long_itinerary():
    """驗證長天數行程在前 2 天為空/機場時，第 3 天以後出現的景點抽樣依然能命中時區"""
    mock_long_trip = {
        "title": "出國放鬆漫遊",  # 標題刻意不寫城市名
        "destination": "",      # 目的地為空
        "days": [
            {"day_number": 1, "items": [{"place": "機場過境酒店"}]},
            {"day_number": 2, "items": [{"place": "高速休息站"}]},
            {"day_number": 3, "items": [{"place": "羅浮宮博物館"}]}, # 法國巴黎
        ]
    }
    tz = infer_destination_timezone(mock_long_trip, client_tz_str="Asia/Taipei")
    assert tz == "Europe/Paris"


def test_substring_collision_protection():
    """驗證單詞邊界防護：避免 'th' 劫持 'South New York' 或 'la' 劫持 'Villa Relax'"""
    # 1. 'South' 含有 'th'，但不可誤判為泰國 (Asia/Bangkok)
    ny_trip = {"title": "South New York Trip"}
    assert infer_destination_timezone(ny_trip, client_tz_str="Asia/Taipei") == "America/New_York"

    # 2. 'Villa' 含有 'la'，但不可誤判為洛杉磯 (America/Los_Angeles)
    villa_trip = {"title": "Villa Relax Vacation"}
    assert infer_destination_timezone(villa_trip, client_tz_str="Asia/Taipei") == "Asia/Taipei"

    # 3. 世界時間查詢 'Perth' (伯斯) 不可誤判為曼谷
    from services.temporal_service import query_world_time
    assert query_world_time("Perth")["timezone"] == "Australia/Perth"


