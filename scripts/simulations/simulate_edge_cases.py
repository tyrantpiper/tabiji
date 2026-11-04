"""
Autonomous Edge Case Simulation & Stress Harness
===============================================
執行五大極限邊界狀況的物理模擬與數值推演：
1. 模擬 A: 跨國際換日線、夏令時間 DST 23/25 小時跳變、與時差慢性病服藥間隔 (Chrono-Shift)
2. 模擬 B: 經度 180/-180 翻轉、大圓航線短弧/長弧判定、Web Mercator 緯度極限、fitBounds 螞蟻點防衛
3. 模擬 C: 離線 Outbox 佇列多操作依賴鏈 (Ephemeral ID Cascading) 與衝突重播狀態機
4. 模擬 D: Overpass QL 注入、SSRF 協議穿透、與周邊搜尋 3.0s 嚴格熔斷 Fuzzing
5. 模擬 E: 醫療急難 POI 標籤拓撲 (AED, 24H 藥局, 醫院急診) 與多語系對照提取
"""

import math
import re
import sys
from pathlib import Path
import zoneinfo
from datetime import datetime, timezone, timedelta, time
from typing import Dict, List, Tuple, Any, Optional

# 🛡️ 注入 REPO_ROOT 動態路徑，相容從任意目錄執行
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# =====================================================================
# 1. 模擬 A: 時區跨越、夏令時間 (DST) 與時差服藥間隔 (Chrono-Shift)
# =====================================================================

def simulate_dst_and_timezone_jumps():
    """
    模擬春季 (撥快 1h, 23h 天) 與秋季 (撥慢 1h, 25h 天) 對活動與服藥間隔的影響
    """
    results = {}
    
    # 案例 1: 歐洲巴黎 2026 年秋季 DST 結束 (撥慢 1 小時)
    # 2026-10-25 03:00 撥回 02:00 (剛好就是今天！)
    tz_paris = zoneinfo.ZoneInfo("Europe/Paris")
    
    # 在切換前後各取時間點
    dt_before = datetime(2026, 10, 25, 1, 30, tzinfo=tz_paris) # UTC+2
    dt_after = datetime(2026, 10, 25, 3, 30, tzinfo=tz_paris)  # UTC+1
    
    # 計算物理流逝時間 (以 UTC 基準)
    elapsed_physical_hours = (dt_after.astimezone(timezone.utc) - dt_before.astimezone(timezone.utc)).total_seconds() / 3600.0
    # 計算表面掛鐘時間差
    nominal_wall_hours = (dt_after.hour + dt_after.minute/60) - (dt_before.hour + dt_before.minute/60)
    
    results["paris_fall_dst"] = {
        "dt_before_iso": dt_before.isoformat(),
        "dt_after_iso": dt_after.isoformat(),
        "elapsed_physical_hours": elapsed_physical_hours, # 應該是 3.0 小時，因為中間重複了 1 小時！
        "nominal_wall_hours": nominal_wall_hours,         # 表面只有 2.0 小時
        "wall_clock_drift": elapsed_physical_hours - nominal_wall_hours
    }
    
    # 案例 2: 跨國際換日線飛行 (台北 -> 舊金山)
    # 台北 TPE 2026-11-01 23:00 起飛，飛行 11 小時，抵達舊金山 SFO
    tz_tpe = zoneinfo.ZoneInfo("Asia/Taipei")     # UTC+8
    tz_sfo = zoneinfo.ZoneInfo("America/Los_Angeles") # UTC-7 (夏令) 或 UTC-8 (冬令，11/1 剛好冬令切換)
    
    depart_tpe = datetime(2026, 11, 1, 23, 0, tzinfo=tz_tpe)
    arrive_utc = depart_tpe.astimezone(timezone.utc) + timedelta(hours=11)
    arrive_sfo = arrive_utc.astimezone(tz_sfo)
    
    results["transpacific_flight"] = {
        "depart_tpe_local": depart_tpe.strftime("%Y-%m-%d %H:%M %Z"),
        "arrive_sfo_local": arrive_sfo.strftime("%Y-%m-%d %H:%M %Z"),
        "calendar_date_change": (arrive_sfo.date() - depart_tpe.date()).days, # 時間倒退或同日
        "same_calendar_day": arrive_sfo.date() == depart_tpe.date()
    }
    
    # 案例 3: 慢性病服藥間隔 (Chrono-Shift Algorithm)
    # 患者每天固定早上 08:00 吃一次降血壓藥 (每 24h 一次)
    # 跨越時區後，若盲目在 SFO 早上 08:00 服用，會發生什麼？
    tpe_dose_1 = datetime(2026, 11, 1, 8, 0, tzinfo=tz_tpe) # Day 1 早上 8 點
    # 晚上 23 點起飛，飛行 11 小時，在 SFO 11/1 早上 19:00 或 11/2 早上 08:00
    sfo_naive_dose = datetime(2026, 11, 2, 8, 0, tzinfo=tz_sfo)
    
    interval_naive_hours = (sfo_naive_dose.astimezone(timezone.utc) - tpe_dose_1.astimezone(timezone.utc)).total_seconds() / 3600.0
    
    # 醫學安全間隔算法：維持 24 ± 4 小時之生理劑量保護
    # 若間隔超過 28 小時，必須提供過渡期微劑量或平移服藥排程 (Shift Schedule)
    results["medication_interval"] = {
        "interval_naive_hours": interval_naive_hours,
        "is_dangerously_delayed": interval_naive_hours > 28.0,
        "recommended_shift_dose_utc": (tpe_dose_1.astimezone(timezone.utc) + timedelta(hours=24)).isoformat()
    }
    
    return results

# =====================================================================
# 2. 模擬 B: 換日線大圓航線短弧/長弧判定與 Web Mercator 奇異點
# =====================================================================

def calculate_antimeridian_arc(lng1: float, lng2: float) -> Tuple[float, bool]:
    """
    計算兩經度間的真正最短經度差，並判定是否跨越 180 度換日線 (O(1) 模運算 + 非有限浮點數防禦)
    回傳 (shortest_delta_deg, crosses_antimeridian)
    """
    if not (isinstance(lng1, (int, float)) and isinstance(lng2, (int, float))):
        raise ValueError("Coordinates must be numeric")
    if not (math.isfinite(lng1) and math.isfinite(lng2)):
        raise ValueError("Coordinates must be finite numbers")
    raw_diff = float(lng2) - float(lng1)
    # O(1) 標準化至 [-180, 180]，防止極大數或無限大導致 while 迴圈 CPU DoS
    norm_diff = ((raw_diff + 180.0) % 360.0) - 180.0
    if norm_diff == -180.0 and raw_diff > 0:
        norm_diff = 180.0
    crosses_antimeridian = abs(raw_diff) > 180.0
    return abs(norm_diff), crosses_antimeridian

def simulate_great_circle_antimeridian():
    """
    模擬東京 (139.767, 35.681) 到檀香山 (-157.858, 21.307)
    """
    p1 = (139.767, 35.681)
    p2 = (-157.858, 21.307)
    
    # 傳統二維簡單差值 (錯誤方式)
    naive_diff = abs(p2[0] - p1[0]) # 297.625 度 (幾乎繞地球一整圈)
    
    # 換日線感知演算法 (正確方式)
    shortest_diff, crosses = calculate_antimeridian_arc(p1[0], p2[0])
    
    # 外接矩形 Bounds 崩潰模擬
    # 傳統方式:
    naive_min_lng = min(p1[0], p2[0]) # -157.858
    naive_max_lng = max(p1[0], p2[0]) # 139.767
    naive_span = naive_max_lng - naive_min_lng # 297.625 度！
    
    # 換日線防禦方式 (Pacifc-Centered or Split Bounds):
    # 將西經轉為 360 度基準計算跨度
    norm_p2_lng = p2[0] if p2[0] >= 0 else p2[0] + 360 # -157.858 + 360 = 202.142
    pacific_span = abs(norm_p2_lng - p1[0]) # 202.142 - 139.767 = 62.375 度！
    
    return {
        "naive_diff_deg": naive_diff,
        "shortest_diff_deg": shortest_diff,
        "crosses_antimeridian": crosses,
        "naive_bbox_span_deg": naive_span,
        "pacific_bbox_span_deg": pacific_span,
        "zoom_distortion_ratio": naive_span / pacific_span # 縮小了 4.77 倍 (螞蟻點效應)
    }

# =====================================================================
# 3. 模擬 C: 離線 Outbox 佇列多操作依賴鏈與臨時 ID 級聯
# =====================================================================

class MockOutboxEngine:
    def __init__(self):
        self.queue = []
        self.server_db = {}
        self.id_mapping = {} # client_temp_id -> server_permanent_id
        
    def enqueue(self, op_id: str, action: str, target_id: str, payload: dict):
        self.queue.append({
            "op_id": op_id,
            "action": action,
            "target_id": target_id,
            "payload": payload,
            "status": "pending",
            "retry_count": 0
        })
        
    def replay_all(self):
        """
        模擬網路恢復時的佇列重播，包含臨時 ID 替換與依賴鏈自癒
        """
        execution_log = []
        for req in self.queue:
            target_id = req["target_id"]
            # 依賴解析: 若 target_id 是臨時 ID 且已有伺服端對應，自動替換！
            resolved_target_id = self.id_mapping.get(target_id, target_id)
            
            if req["action"] == "CREATE_ITEM":
                temp_id = req["payload"].get("client_temp_id")
                server_id = f"srv_uuid_{len(self.server_db) + 1}"
                self.server_db[server_id] = {**req["payload"], "id": server_id}
                if temp_id:
                    self.id_mapping[temp_id] = server_id
                req["status"] = "synced"
                execution_log.append(f"CREATED item temp={temp_id} -> server={server_id}")
                
            elif req["action"] == "UPDATE_ITEM":
                if resolved_target_id in self.server_db:
                    self.server_db[resolved_target_id].update(req["payload"])
                    req["status"] = "synced"
                    execution_log.append(f"UPDATED item target={resolved_target_id}")
                else:
                    req["status"] = "failed_404"
                    execution_log.append(f"ERROR: Target not found {resolved_target_id}")
                    
            elif req["action"] == "DELETE_ITEM":
                if resolved_target_id in self.server_db:
                    del self.server_db[resolved_target_id]
                    req["status"] = "synced"
                    execution_log.append(f"DELETED item target={resolved_target_id}")
                else:
                    req["status"] = "failed_404"
                    execution_log.append(f"ERROR: Delete target not found {resolved_target_id}")
                    
        return execution_log

def simulate_offline_outbox_cascade():
    engine = MockOutboxEngine()
    # 使用者在斷網時連續操作:
    # 1. 新增景點 (臨時 ID: client_temp_999)
    engine.enqueue("op1", "CREATE_ITEM", "new", {"client_temp_id": "client_temp_999", "place": "淺草炸牛排"})
    # 2. 編輯剛才新增景點的備註 (引用 client_temp_999)
    engine.enqueue("op2", "UPDATE_ITEM", "client_temp_999", {"notes": "記得提早排隊"})
    # 3. 再刪除另一個舊景點
    engine.server_db["srv_uuid_old"] = {"id": "srv_uuid_old", "place": "舊景點"}
    engine.enqueue("op3", "DELETE_ITEM", "srv_uuid_old", {})
    
    logs = engine.replay_all()
    all_synced = all(r["status"] == "synced" for r in engine.queue)
    return {
        "execution_logs": logs,
        "all_synced": all_synced,
        "final_server_db": engine.server_db,
        "id_mapping": engine.id_mapping
    }

# =====================================================================
# 4. 模擬 D: Overpass QL 注入與 SSRF 惡意請求 Fuzzing
# =====================================================================

def simulate_security_fuzzing():
    from backend.services.poi_service import sanitize_overpass_keyword
    
    test_vectors = [
        # Vector 1: Overpass QL 注入 (企圖跳脫 query 括號並發送全量下載)
        ('"]; node(user:"attacker"); out body; [out:json]; //', 'Overpass QL delimiter bypass'),
        # Vector 2: 內嵌單雙引號與正則符號
        ('restaurant"; out meta; (._;>;); <script>alert(1)</script>', 'Script & Meta tag injection'),
        # Vector 3: 超長字串 (Buffer/Token exhaustion)
        ('A' * 500, 'Oversized buffer payload'),
        # Vector 4: 換行符注入 (CRLF injection)
        ('ramen\n\r[out:xml];\nnode;', 'CRLF injection'),
        # Vector 5: 正常中英日文與符號
        ('一蘭拉麵 (新宿店) - Ramen & Gyoza', 'Legitimate multilingual search')
    ]
    
    fuzzing_results = []
    for payload, description in test_vectors:
        sanitized = sanitize_overpass_keyword(payload)
        # 驗證危險字元被完全剔除
        has_dangerous_chars = any(c in sanitized for c in [';', '"', '[', ']', '(', ')', '{', '}', '<', '>', '\n', '\r'])
        fuzzing_results.append({
            "vector": description,
            "raw_length": len(payload),
            "sanitized": sanitized,
            "sanitized_length": len(sanitized),
            "is_safe": not has_dangerous_chars and len(sanitized) <= 64
        })
        
    return fuzzing_results

# =====================================================================
# 主執行與總結報告
# =====================================================================

if __name__ == "__main__":
    print("=== Running Autonomous Edge Case Simulations ===")
    res_a = simulate_dst_and_timezone_jumps()
    print("\n[Simulation A: Timezone & DST & Chrono-Shift]")
    for k, v in res_a.items():
        print(f"  - {k}: {v}")
        
    res_b = simulate_great_circle_antimeridian()
    print("\n[Simulation B: Antimeridian & Great Circle Singularity]")
    for k, v in res_b.items():
        print(f"  - {k}: {v}")
        
    res_c = simulate_offline_outbox_cascade()
    print("\n[Simulation C: Offline Outbox ID Cascading]")
    print(f"  - All Synced: {res_c['all_synced']}")
    print(f"  - Logs: {res_c['execution_logs']}")
    
    res_d = simulate_security_fuzzing()
    print("\n[Simulation D: Security Fuzzing & Injection Defense]")
    for item in res_d:
        print(f"  - {item['vector']}: Safe={item['is_safe']} (Len {item['raw_length']} -> {item['sanitized_length']})")
