# 🛡️ Security Sentinel 對抗式沙盒審計報告 (時光膠囊當地時區錨定與防篡改軟解鎖)

> **審計日期**: 2026-10-23  
> **審計模式**: `sentinel-agy-adversarial` (Cloudflare 6-Phase Ledger ✕ Google Mantis Patch ✕ agy.exe CLI 物理隔離沙盒)  
> **執法標準**: L0 人類主權憲法 (只回報，交由人類決策；未經核准不碰原始碼)  
> **驗證狀態**: 3 個目標平行審查完成 (2 個 Confirmed, 1 個 Dismissed/Hardened, In-Memory PoC 4/4 PASSED)

---

## 執行摘要 (Executive Summary)

| 審計目標 | 信任邊界 | 攻擊/缺陷向量 | Sentinel 裁決 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| [`backend/routers/capsules.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/capsules.py)<br/>`hardcoded_timezone_drift` | `authenticated_to_internal` | 硬編碼東京時區引發非日本行程最高 17 小時漂移 (`temporal_and_timezone_desync`) | **CONFIRMED** | 🚨 待修復 |
| [`backend/routers/capsules.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/capsules.py)<br/>`early_unlock_premature_trigger` | `authenticated_to_internal` | 提前解鎖缺乏「最後一天」邊界守衛導致旅途前期偷跑 (`access_control_and_time_lock_bypass`) | **CONFIRMED** | 🚨 待修復 |
| [`backend/routers/capsules.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/capsules.py)<br/>`post_unveil_tampering_overwrite` | `authenticated_to_internal` | 提前破印後看過他人心得偷改自己內容 (`integrity_and_tampering`) | **CONFIRMED (待防衛)** | 🚨 待修復 |

---

## 漏洞深度實證與 In-Memory PoC

### 🚨 SEC-CAPSULE-02: `compute_trip_end_utc` 寫死東京時區引發全球行程嚴重漂移 (CONFIRMED)
- **攻擊/缺陷場景**：
  若使用者建立前往**紐約（America/New_York，EDT UTC-4）**的行程，後端原程式碼硬編碼 `14:59:59 UTC`（東京當晚 23:59:59）。在紐約當地時間，這僅相當於最後一天**上午 10:59:59 AM**！
  行程在白天上午 11 點就被誤判為「旅程已結束」，時間鎖提前 13 小時硬凍結，嚴重破壞正常填寫。
- **In-Memory PoC 驗證實證 ([test_capsules_temporal_tamper_sentinel_poc.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_capsules_temporal_tamper_sentinel_poc.py#L90-L125))**：
  ```bash
  pytest backend/tests/test_capsules_temporal_tamper_sentinel_poc.py -v -k "test_tc1"
  # 結果：PASSED (實證硬編碼產生 13.0 小時致命漂移，接入 infer_destination_timezone + safe_get_zoneinfo 後 0 誤差)
  ```

### 🚨 SEC-CAPSULE-03: `unlock_trip_capsules_early` 缺乏最後一天邊界防線 (CONFIRMED)
- **攻擊/缺陷場景**：
  任何旅伴在 Day 1 或 Day 2 即可發起呼叫提前解鎖，缺乏時間邊界防衛，導致旅程才剛開始秘密盲盒就被破印。
- **In-Memory PoC 驗證實證 ([test_capsules_temporal_tamper_sentinel_poc.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_capsules_temporal_tamper_sentinel_poc.py#L128-L150))**：
  ```bash
  pytest backend/tests/test_capsules_temporal_tamper_sentinel_poc.py -v -k "test_tc2"
  # 結果：PASSED (實證 Day 1 觸發遭 HTTP 400 攔截；最後一天 20:30 本地時間成功放行)
  ```

### 🚨 SEC-CAPSULE-04: 防篡改軟解鎖守衛 (Anti-Tampering Soft Unlock)
- **防禦目標**：
  解鎖後若開放補填，必須杜絕「看過別人真心話後修改自己已揭曉內容」之道德風險。
- **In-Memory PoC 驗證實證 ([test_capsules_temporal_tamper_sentinel_poc.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_capsules_temporal_tamper_sentinel_poc.py#L153-L198))**：
  ```bash
  pytest backend/tests/test_capsules_temporal_tamper_sentinel_poc.py -v -k "test_tc3"
  # 結果：PASSED (Alice 嘗試修改已揭曉條目遭 403 阻斷；Bob 補填全新條目 200 通過並立即揭曉)
  ```

---

## 候選補丁與精確區塊替換 (Mantis Candidate Patch)
已產出於 [`docs/security/history/patch_candidate_capsules_temporal_tamper_2026-10-23.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patch_candidate_capsules_temporal_tamper_2026-10-23.diff)。

### 區塊替換要點 ([`backend/routers/capsules.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/capsules.py))
1. 匯入 `infer_destination_timezone` 與 `safe_get_zoneinfo`。
2. 以 `compute_trip_local_bounds(trip)` 取代寫死東京的 `compute_trip_end_utc`。
3. `unlock_trip_capsules_early` 加入 `now_utc < last_day_start_utc` 攔截（400）。
4. `submit_trip_capsule` 加入防篡改驗證：若 `is_capsule_unlocked` 且已存在條目，拋出 403 阻斷篡改；未填者放行補填。

---

## 人類閘門移交 (Human Gate Handover)
依據 L0 憲法，全套對抗審計已在沙盒完成，In-Memory PoC 全數通過，本報告與補丁僅供審查。
等待 Ryan 確認批准後，方可由 `@dev` 執行實體程式碼變更與 `@qa` 測試驗收。
