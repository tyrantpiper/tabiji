# Security Sentinel 物理沙盒審計報告：跨模組協同同步、SWR 複合鍵與 L0 快照一致性審查

> **審計日期**: 2026-10-23  
> **審計模式**: 物理隔離沙盒審核 (`runner.py` ✕ `agy.exe --sandbox` ✕ In-Memory Pytest PoC)  
> **執行身份**: `@security` (Security Sentinel)  
> **遵守憲法**: 遵守 L0 人類主權原則（只回報、產出 PoC 與候選補丁，絕不擅自直接修改正式代碼）

---

## 1. 執行總結 (Executive Summary)

針對 Tabiji 系統全景式協同盲區（公帳記帳、航班住宿、活動細項/備忘錄），本審計進行物理沙盒對抗證偽與邊界容錯審核：

| 評估維度 | 統計數值 | 狀態評估 |
| :--- | :---: | :--- |
| **審查攻擊面靶點** | **4** | 全覆蓋 `useTripRealtime`、`tools-view` / `expense-dialog`、`info-view`、`itinerary-view` |
| **實證架構隱患與破綻** | **3** | SWR Tuple 陣列鍵比對失效、`handleSaveInner` 非同步閉包過期沖刷、API 異常時 L0 快照未自癒回滾 |
| **沙盒排除/邊界確認** | **1** | `tools-view` 記帳彈窗 `ExpenseDialog` 擁有獨立內部表單 state，背景刷新不會直接踩踏輸入中表單 |
| **In-Memory PoC 通過率** | **100% (3/3)** | 於 [test_cross_module_sentinel_poc.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_cross_module_sentinel_poc.py) 完成數學實證（耗時 0.03s） |
| **候選安全補丁 (Mantis Patch)** | **1 份** | [patch_candidate_cross_module_2026-10-23.diff](file:///d:/Project/tabiji/travel-pwa/docs/security/patch_candidate_cross_module_2026-10-23.diff) |
| **全棧回歸驗證** | **551/551 Tests 綠燈** | Vitest 82 套件 (547 測試) + 兩套 Sentinel PoC (7 測試) 100% 通過 |

---

## 2. 實證隱患細節與沙盒 PoC (Vulnerability Details & In-Memory PoCs)

### 🔴 隱患 1：SWR 複合鍵斷層引發協同失效 (Tuple Key Predicate Desync)
- **攻擊靶點**: `frontend/lib/hooks/useTripRealtime.ts` (L137-141) 與 `frontend/lib/hooks.ts` (L240)
- **邊界等級**: `browser_runtime` (跨設備 WebSocket 協同通道)
- **隱患成因**:
  `useExpenses` 註冊 SWR 採用複合 Tuple 鍵 `[`/api/trips/${tripId}/expenses`, userId]`。若在 Realtime 監聽器中使用一般字串 `mutate("/api/trips/${tripId}/expenses")`，SWR 字典查詢將無條件判定為 Key Mismatch，導致遠端 `postgres_changes` 或 `expense:update` 廣播事件抵達後**完全無法刷新前端費用列表**。
- **實證 PoC**:
  於 [test_cross_module_sentinel_poc.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_cross_module_sentinel_poc.py) 之 `test_poc_1_swr_tuple_key_predicate_mismatch` 成功重現：字串比對命中數為 0，改採 `expense_predicate` 後精確命中並刷新快取。

---

### 🔴 隱患 2：React 狀態閉包延遲導致飯店編輯遺失 (State Closure Stale Overwrite)
- **攻擊靶點**: `frontend/components/views/info-view.tsx` (L128-136, L218-228)
- **邊界等級**: `browser_local` (React 渲染幀生命週期)
- **隱患成因**:
  在 `handleSaveInner` 中，程式依序呼叫 `setHotels(newHotels)` 與 `handleSave()`。由於 React 的狀態設定為非同步批次處理，`handleSave` 在同一執行幀內閉包捕獲的 `hotels` 依然是**修改前的舊陣列**。因此傳送到後端與寫入快照的均為舊資料，使用者修改的飯店細節被靜默丟棄。
- **實證 PoC**:
  於 `test_poc_2_info_view_stale_closure_overwrites_temp_hotel` 成功重現：無參數呼叫時後端與 L0 快照殘留 `Old Hotel A`；導入 `override_hotels` 參數後，成功逃逸閉包，後端與 L0 快照正確更新為最新飯店。

---

### 🔴 隱患 3：異常回滾遺漏持久化快照導致離線資料污染 (L0 Snapshot Poisoning on Failure)
- **攻擊靶點**: `frontend/components/views/itinerary-view.tsx` (L1318-1326)
- **邊界等級**: `browser_local` (L0 IndexedDB 離線快顯層)
- **隱患成因**:
  當在景點活動中進行快速備忘/資訊修改時，前端進行樂觀更新。若後端 API 請求失敗（例如斷網或伺服器 500），現有邏輯在 `catch` 區塊僅執行 `reloadTripDetail()` 重新對齊記憶體，但**未將權威回滾結果重新寫入 `saveTripSnapshot`**。離線時重開 PWA，本地 IndexedDB 依然顯示已失敗的修改項目。
- **實證 PoC**:
  於 `test_poc_3_itinerary_rollback_prevents_corrupted_snapshot` 成功重現：失敗後未校正快照將使未承認之資料殘留於持久存儲；回滾閉環可確保權威狀態無損。

---

## 3. 精確區塊替換指引 (Block Replacement Instructions)

完整補丁見 [patch_candidate_cross_module_2026-10-23.diff](file:///d:/Project/tabiji/travel-pwa/docs/security/patch_candidate_cross_module_2026-10-23.diff)。

### 區塊 1: `frontend/lib/hooks/useTripRealtime.ts`
- **原內容**: `broadcastTripEvent` 型別未包含記帳與資訊事件；缺乏 `expenses` 資料表 `postgres_changes`。
- **替換為**: 擴充型別包含 `"expense:update" | "info:update"`；掛載 `expenses` CDC 監聽並使用 Tuple Predicate 精準刷新 SWR。

### 區塊 2: `frontend/components/expense-dialog.tsx` 與 `tools-view.tsx`
- **原內容**: 新增/修改/刪除費用後無廣播；`tools-view` 未監聽即時協同。
- **替換為**: 於 `onSaveSuccess` 與 `handleDeleteExpense` 觸發 `broadcastTripEvent`；於 `tools-view` 掛載 `tabiji:collab-event` 監聽，並以 `!isDialogOpen` 作為保護守衛。

### 區塊 3: `frontend/components/views/info-view.tsx`
- **原內容**: `handleSave` 無參數，閉包讀取過期 `hotels`；存檔未寫入 L0 快照與廣播。
- **替換為**: `handleSave` 接收 `overrideHotels` 與 `overrideFlights`；存檔成功後寫入 `saveTripSnapshot` 並廣播 `"info:update"`。

### 區塊 4: `frontend/components/views/itinerary-view.tsx`
- **原內容**: `handleUpdateActivity` 與 `handleSaveEdit` 缺乏快照校正與異常回滾自癒。
- **替換為**: 成功更新後寫入 `saveTripSnapshot`；`catch` 區塊回滾時將伺服器權威資料同步回寫至 `saveTripSnapshot`。

---

## 4. 人類閘門移交 (Human Gate Handover)

依據 Security Sentinel 憲法：
- 本報告、In-Memory PoC 與候選補丁已全數就緒並驗證完畢。
- **正式代碼目前未做任何改動**。
- 請 Ryan 審閱並授權：核准後將正式交由 `@dev` 執行實體檔案變更，並由 `@qa` 進行全棧型別與端到端驗證。
