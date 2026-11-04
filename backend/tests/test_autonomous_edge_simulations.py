"""
test_autonomous_edge_simulations.py
===================================
自動化測試：五大邊際情況模擬與生理/空間不變量守護
1. TC-1: 歐洲 DST 夏令時間切換 (25小時日) 與掛鐘時間漂移防衛
2. TC-2: 跨國際換日線長途航程 (台北->舊金山) 飛行時間與日曆錯位驗證
3. TC-3: 換日線大圓航線短弧演算法與 Bounding Box 螞蟻點防衛 (4.77x 縮小修正)
4. TC-4: 離線 Outbox 佇列多操作依賴鏈 (Ephemeral ID Cascading) 與衝突重播自癒
5. TC-5: Overpass QL 注入防衛與惡意邊界字符清洗
6. TC-6: 醫療急難 (AED, 24H 藥局, 急救) 空間感知與多語系對照卡聚合
"""

import sys
from pathlib import Path
import zoneinfo
from datetime import datetime, timezone, timedelta
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.simulations.simulate_edge_cases import (
    simulate_dst_and_timezone_jumps,
    simulate_great_circle_antimeridian,
    simulate_offline_outbox_cascade,
    simulate_security_fuzzing,
    calculate_antimeridian_arc
)
from scripts.simulations.simulate_emergency_medical import (
    detect_emergency_intent,
    format_emergency_response_card
)

def test_tc1_dst_and_timezone_jumps():
    """TC-1: 驗證巴黎秋季夏令時間切換時物理時間 (3h) 與表面掛鐘時間 (2h) 之 1h 漂移"""
    res = simulate_dst_and_timezone_jumps()
    paris = res["paris_fall_dst"]
    assert paris["elapsed_physical_hours"] == 3.0
    assert paris["nominal_wall_hours"] == 2.0
    assert paris["wall_clock_drift"] == 1.0

def test_tc2_transpacific_flight_and_chrono_shift():
    """TC-2: 驗證跨太平洋航班 (TPE->SFO) 表面日曆時間倒退與慢病服藥間隔過度延遲 (40h)"""
    res = simulate_dst_and_timezone_jumps()
    flight = res["transpacific_flight"]
    assert flight["same_calendar_day"] is True
    assert flight["calendar_date_change"] == 0
    
    med = res["medication_interval"]
    assert med["interval_naive_hours"] == 40.0
    assert med["is_dangerously_delayed"] is True
    # 驗證生理排程建議在 UTC 基準 24 小時整提供過渡劑量
    assert med["recommended_shift_dose_utc"] == "2026-11-02T00:00:00+00:00"

def test_tc3_antimeridian_arc_and_bbox_ant_point_defense():
    """TC-3: 換日線短弧經度差 (62.375°) vs 傳統未防禦經度差 (297.625°)，消除 4.77x 螞蟻點失真"""
    res = simulate_great_circle_antimeridian()
    assert round(res["shortest_diff_deg"], 3) == 62.375
    assert round(res["naive_diff_deg"], 3) == 297.625
    assert res["crosses_antimeridian"] is True
    assert res["zoom_distortion_ratio"] > 4.5
    
    # 單元驗證 calculate_antimeridian_arc
    delta_deg, crosses = calculate_antimeridian_arc(179.0, -179.0)
    assert delta_deg == 2.0
    assert crosses is True

def test_tc4_offline_outbox_ephemeral_id_cascade():
    """TC-4: 離線 Outbox 連續操作之臨時 ID (client_temp_999) 級聯映射與 100% 成功重播"""
    res = simulate_offline_outbox_cascade()
    assert res["all_synced"] is True
    assert "client_temp_999" in res["id_mapping"]
    srv_id = res["id_mapping"]["client_temp_999"]
    assert srv_id in res["final_server_db"]
    # 驗證備註成功更新至該伺服器正式 ID 記錄中
    assert res["final_server_db"][srv_id]["notes"] == "記得提早排隊"

def test_tc5_security_fuzzing_and_ql_injection_immunity():
    """TC-5: Overpass QL 注入與長字串 Fuzzing 免疫"""
    fuzzing = simulate_security_fuzzing()
    for item in fuzzing:
        assert item["is_safe"] is True
        assert item["sanitized_length"] <= 64

def test_tc6_emergency_medical_and_multilingual_card():
    """TC-6: 醫療急難 (AED, 醫院急診, 24H 藥局) 意圖精準識別與中日英卡片輸出"""
    # 1. AED 意圖
    res_aed = detect_emergency_intent("老人家胸痛呼吸困難，快找最近的AED！")
    assert res_aed["is_emergency"] is True
    assert res_aed["matched_poi_category"] == "aed"
    assert res_aed["overpass_filter"] == 'nwr["emergency"="defibrillator"]'
    
    # 2. 醫院急診意圖與多語系卡片
    res_er = detect_emergency_intent("小孩發高燒抽搐，需要立刻送急診醫院")
    assert res_er["is_emergency"] is True
    assert res_er["matched_poi_category"] == "hospital"
    card = format_emergency_response_card(res_er, "淺草寺")
    assert card["active"] is True
    assert "119" in card["action_banner"] or "醫療" in card["action_banner"] or "醫院" in card["action_banner"] or "診所" in card["action_banner"]
    assert "ja" in card["multilingual_card"]
    
    # 3. 正常非急難查詢 (無副作用)
    res_normal = detect_emergency_intent("附近有好吃的鰻魚飯嗎？")
    assert res_normal["is_emergency"] is False
    assert res_normal["matched_poi_category"] is None

    # 4. 防止拉丁短詞 'er' / 'aed' 子字串誤判 (如 Uber, Burger, Dinner, Supermarket)
    res_uber = detect_emergency_intent("幫我叫 Uber 去吃 Burger 晚餐，順便逛 Supermarket")
    assert res_uber["is_emergency"] is False
    assert res_uber["matched_poi_category"] is None
    res_real_er = detect_emergency_intent("Need an ER or emergency room right now!")
    assert res_real_er["is_emergency"] is True
    assert res_real_er["matched_poi_category"] == "hospital"

    # 6. 驗證日文臨床症狀與純症狀預設醫療設施映射
    res_ja = detect_emergency_intent("胸の痛み")
    assert res_ja["is_emergency"] is True
    assert res_ja["matched_poi_category"] == "hospital"
    assert res_ja["overpass_filter"] == 'nwr["amenity"="hospital"]'

    res_en_sym = detect_emergency_intent("I have severe chest pain")
    assert res_en_sym["is_emergency"] is True
    assert res_en_sym["matched_poi_category"] == "hospital"
    assert res_en_sym["overpass_filter"] == 'nwr["amenity"="hospital"]'

    # 5. 驗證 calculate_antimeridian_arc O(1) 極大數與非有限浮點數防禦
    with pytest.raises(ValueError):
        calculate_antimeridian_arc(139.0, float("inf"))
    with pytest.raises(ValueError):
        calculate_antimeridian_arc(float("nan"), -157.0)

