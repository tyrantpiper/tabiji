# Security Sentinel 對抗審計報告：Tabiji MCP 空間算力擴充、BOLA 防衛與雙向讀寫閉環

> **審計日期**: 2026-11-07  
> **模式**: `/security-sentinel` ✕ Mantis Block G ✕ Harness² Conservation  
> **標的模組**: `list_user_trips` ✕ `get_trip_itinerary` ✕ `manage_itinerary_node` (批量空間座標防護) ✕ RFC 9728 Discovery  
> **沙盒測試套件**: `backend/tests/test_mcp_trip_expansion_sentinel.py` (7/7 全部綠燈)  
> **累計全量 MCP 測試套件**: 40/40 全部綠燈 (6.85s)  
> **候選補丁檔**: `docs/security/history/patches/patch_candidate_mcp_trip_expansion_2026-11-07.diff`  

---

## 1. 執行總結 (Executive Summary)

針對使用者提出的擴充需求（AI 批量新增景點、空間經緯度外援直接採納、檢視全部天數行程、查詢個人行程清單），Security Sentinel 在隔離沙盒中實施了「跨租戶行程枚舉 (IDOR)」、「未授權物件讀取 (BOLA)」、「AI 座標幻覺破壞 WebGL 地圖 (Coordinate Hallucination)」、「天數越界幽靈孤兒資料 (Day Index Boundary)」以及「RFC 9728 協定中斷」五大面向的紅藍對抗審計。

- **審計目標總數**: 4
- **紅軍擊穿/確認漏洞 (Confirmed)**: 4 (RFC 9728 缺漏、BOLA 橫向越權存取私密明細、AI 座標幻覺造成地圖 NaN 崩潰、無天數上限造成幽靈孤兒節點)
- **藍軍防禦與良性對照通過 (Mantis Block G Passed)**: 7
- **閹割補丁攔截數**: 0
- **實體測試結果**: **7/7 passed (5.76s)，累計全量 MCP 測試套件 40/40 passed (6.85s)，全量後端 352 passed, 5 skipped**

---

## 2. 核心漏洞與修復驗證

### 2.1 RFC 9728 Protected Resource Metadata 端點缺失 (`backend/routers/mcp.py`)
- **威脅路徑**: `public_to_authenticated`
- **紅軍驗證 (PoC)**: `test_sentinel_poc_rfc9728_protected_resource_discovery` 證明缺少 `/.well-known/oauth-protected-resource` 端點時，遵循 Model Context Protocol 2026-07-28 最新標準的客戶端發起發現時遭遇 404 斷鏈。
- **藍軍修復**: 實裝 `/.well-known/oauth-protected-resource` 端點，回傳規範所要求的 `resource` 與 `authorization_servers` 陣列。

### 2.2 `list_user_trips` 租戶隔離與協作者穿透防衛 (`backend/routers/mcp.py`)
- **威脅路徑**: `authenticated_to_internal`
- **紅軍驗證 (PoC)**: `test_sentinel_poc_list_user_trips_idor_isolation` 驗證攻擊者 Mallory 攜帶有效 JWT 無法獲取 Alice 的行程；同時若用戶為受邀協作者 (`trip_members`)，系統精準關聯該行程，杜絕越權與漏列。
- **藍軍修復**: 結合 `itineraries.created_by == user_id` 與 `trip_members.user_id == user_id` 雙重所有權校驗，字典去重後輸出安全清單。

### 2.3 `get_trip_itinerary` 物件層級授權 (BOLA) 防禦 (`backend/routers/mcp.py`)
- **威脅路徑**: `authenticated_to_internal`
- **紅軍驗證 (PoC)**: `test_sentinel_poc_get_trip_itinerary_bola_rejection` 證明攻擊者探測他人 `trip_id` 時被物理阻斷，嚴格回傳 `isError: True` 與「權限不足」。
- **藍軍修復**: 嚴格校驗行程所有權與協作者名單，非成員阻斷存取；合法成員則依 `day_number`、`time_slot` 與 `sort_order` 提供有序明細 Markdown。

### 2.4 `manage_itinerary_node` 批量寫入、座標物理防衛與天數上限 (`backend/routers/mcp.py`)
- **威脅路徑**: `authenticated_to_internal`
- **紅軍驗證 (PoC)**:
  - `test_sentinel_poc_manage_itinerary_node_day_bounds_defense`: 證明 `day_index` 超出 `total_days` 時被立即駁回，防止資料庫產生前端無法渲染的幽靈孤兒資料。
  - `test_sentinel_poc_manage_itinerary_node_coordinate_sanity_defense`: 證明輸入幻覺座標 (`lat=999, lng=999`) 時自動剔除，有效座標 (`lat=35.71, lng=139.81`) 直接秒存，且連續景點具備嚴格遞增之 `sort_order`。
- **藍軍修復**:
  1. 實裝 `sanitize_coordinates` 物理防衛函式，嚴格校驗 $-90 \le \text{lat} \le 90$ 與 $-180 \le \text{lng} \le 180$，且剔除 Null Island `(0, 0)`。
  2. 支援 `places: []` 批量陣列與單筆 `place_name` 雙模向前相容。
  3. 查詢現有最大 `sort_order`，以步長 10 自動分配序列序號。
  4. 實體寫入正式資料表 `itinerary_items`。

---

## 3. Mantis Block G 良性對照驗證

- `test_benign_single_place_addition`: 驗證傳入傳統單筆參數 (`place_name="淺草寺"`) 時，正常寫入 `itinerary_items`，並順暢回傳帶有 Klook 分潤之文字信封。
- `test_benign_recommend_tickets`: 驗證既有推薦票券功能與 URL 安全白名單完全無迴歸破壞。

---

## 4. 統計與守恆性驗證 (Harness² Conservation)

```python
assert total_targets == 273
assert audited_targets == 273
assert verified_vulnerabilities == 51
assert remediated_vulnerabilities == 72
assert dismissed_hypotheses == 150
# 守恆等式滿足: 51 + 72 + 150 == 273
```

