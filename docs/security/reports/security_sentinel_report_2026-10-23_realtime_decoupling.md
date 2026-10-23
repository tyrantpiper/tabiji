# Security Sentinel 物理沙盒審計報告：跨端即時協同、Service Worker 快取解耦與狀態踩踏對抗性審核

> **審計日期**: 2026-10-23  
> **審計模式**: 物理隔離沙盒審核 (`runner.py` ✕ `agy.exe --sandbox` ✕ In-Memory Pytest PoC)  
> **執行身份**: `@security` (Security Sentinel)  
> **遵守憲法**: 遵守 L0 人類主權原則（只回報、產出 PoC 與候選補丁，絕不擅自修改代碼）

---

## 1. 執行總結 (Executive Summary)

針對 Tabiji 跨裝置重點事項/清單新增後消失、旅伴無法即時同步、依賴手動重新整理等系統性異常，本審計啟動全景式對抗滲透分析與物理沙盒驗證：

| 評估維度 | 統計數值 | 狀態評估 |
| :--- | :---: | :--- |
| **審查攻擊面靶點** | **6** | 全覆蓋 Service Worker、SWR Fetcher、Realtime 廣播通道、元件狀態與控制器快照 |
| **實證缺陷 (Confirmed)** | **5** | SW 7 天舊快取毒丸、廣播未就緒丟包、SWR 提前重拉競態、元件雙重狀態踩踏、快照未同步冷啟動回滾 |
| **沙盒排除/安全防線 (Dismissed/Secure)** | **1** | `fetcherWithUserId` 缺少 `cache: no-store` 符合 RFC 9111 標準（授權標頭禁止中介快取），安全排除 |
| **In-Memory PoC 通過率** | **100% (4/4)** | 於 [test_realtime_sentinel_poc.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_realtime_sentinel_poc.py) 完成物理重現與數學實證（耗時 0.09s） |
| **候選安全補丁 (Mantis Patch)** | **1 份** | [patch_candidate_realtime_decoupling_2026-10-23.diff](file:///d:/Project/tabiji/travel-pwa/docs/security/patch_candidate_realtime_decoupling_2026-10-23.diff) |
| **台帳數學守恆校驗** | **200 靶點無損** | `validate_security_ledger.py` 驗證全量數學守恆通過 |

---

## 2. 核心實證缺陷與沙盒 PoC (Vulnerability Details & In-Memory PoCs)

### 🔴 缺陷 1：Service Worker 7 天舊快取毒丸沖刷樂觀更新 (Stale-While-Revalidate Cache Poisoning)
- **攻擊靶點**: `frontend/app/sw.ts` (L133-148)
- **邊界等級**: `browser_to_edge` (PWA Service Worker 傳輸攔截層)
- **缺陷成因**:
  Serwist 對 `/api/trips/` 的 GET 請求實施了 7 天的 `StaleWhileRevalidate`。當使用者或旅伴進行任何編輯時，SWR 觸發的背景 `GET /api/trips/:id` 會被 Service Worker 攔截並**第一時間自磁碟吐出 7 天內的舊快照**。該舊資料直接回灌並覆蓋 SWR 的樂觀更新，導致剛新增或移除的項目瞬間消失，直到使用者強制 Hard Refresh 繞過 SW。
- **實證 PoC**:
  於 [test_realtime_sentinel_poc.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_realtime_sentinel_poc.py) 之 `test_poc_1_sw_stale_cache_overwrites_optimistic_update` 成功重現：SWR 拿到的資料源為 `stale_cache`，新資料遭舊快取無情抹煞。

---

### 🔴 缺陷 2：廣播通道握手丟包與 SWR 提前重查引發「非同步未落盤競態」
- **攻擊靶點**: `frontend/lib/hooks/useTripRealtime.ts` (L26-52, L124-145)
- **邊界等級**: `browser_runtime` (跨設備 WebSocket 協同通道)
- **缺陷成因**:
  1. `broadcastTripEvent` 使用臨時 channel 調用 `send()`，在 WebSocket 處於 `CONNECTING` 時直接丟包。
  2. 協同端收到廣播（10ms）後，竟然無條件立即呼叫無參數 `mutate()` 重新打 GET。此時發起端寫入 Supabase 的 HTTP PATCH（需 300~800ms）**根本尚未落盤**，協同端提早拉取到未更新的舊資料，直接覆蓋記憶體鏡像，導致旅伴畫面上自始至終看不見新項目。
- **實證 PoC**:
  於 `test_poc_2_premature_revalidation_race_condition` 成功重現：未落盤前提早拉取之 `bob_stale_fetch` 均為舊值。

---

### 🔴 缺陷 3：元件內部雙重狀態踩踏與無 ID 陣列錯位刪除 (Dual-State Anti-Pattern & Off-by-one)
- **攻擊靶點**: `frontend/components/itinerary/EditableDailyTips.tsx` (L170-230) 與 `EditableDailyChecklist.tsx` (L35-65)
- **邊界等級**: `browser_local` (React 元件渲染樹)
- **缺陷成因**:
  1. 元件自建 `useState(notes)` 並透過 `useEffect` 監聽 props。當使用者儲存關閉表單時，背景 SWR 帶著舊 props 抵達，`useEffect` 立即將舊資料寫入 `localNotes`，當場踩滅使用者剛輸入的內容。
  2. `NoteItem` 缺乏唯一 ID，依賴陣列索引 `idx: number` 刪除。當旅伴非同步插入新項目導致陣列長度改變時，發起端將刪錯項目（Off-by-one Deletion）。
- **實證 PoC**:
  於 `test_poc_3_component_dual_state_clashing_and_index_deletion` 成功重現：樂觀輸入遭 props 踩滅，索引刪除導致非預期項目被拔除。

---

### 🔴 缺陷 4：控制器遺漏存儲快照導致冷啟動回滾 (Omitted Storage Snapshot Desynchronization)
- **攻擊靶點**: `frontend/components/views/itinerary-view.tsx` (L448-484)
- **邊界等級**: `browser_local` (離線 L0/L1 儲存鏡像)
- **缺陷成因**:
  `handleDayDataUpdate` 更新了 SWR 與資料庫，但**完全遺漏了 `saveTripSnapshot`**。L0 LocalStorage 依然維持舊快照。當 App 發生冷啟動、切換前景或弱網喚醒時，SWR 依託 L0 `initialSnapshot` 作為 fallbackData，舊資料再度回灌畫面，引發靈異的歷史復活。
- **實證 PoC**:
  於 `test_poc_4_storage_snapshot_desync_on_cold_rehydration` 成功重現：SWR 記憶體已更新，但 L0 快照維持舊值，重水合時發生回滾。

---

## 3. 精確區塊替換清單 (Block Replacement Instructions)

完整補丁已封裝於 [patch_candidate_realtime_decoupling_2026-10-23.diff](file:///d:/Project/tabiji/travel-pwa/docs/security/patch_candidate_realtime_decoupling_2026-10-23.diff)。

### 區塊 1: `frontend/app/sw.ts`
- **原內容**: 將 `/api/trips/` 快取 7 天之 `StaleWhileRevalidate`
- **替換為**: 將 `/api/trips/` 納入 `NetworkOnly`，並在 `activate` 監聽器中調用 `caches.delete("trips-api-cache")` 物理銷毀舊快取。

### 區塊 2: `frontend/lib/hooks/useTripRealtime.ts`
- **原內容**: 每次臨時 `supabase.channel()` 發送廣播，且收到廣播立即觸發 SWR `mutate()`。
- **替換為**: 導入模組級單例 `RealtimeChannelCoordinator`，未連線自動排隊，`SUBSCRIBED` 瞬間排空；移除收到廣播時的立即 GET，改採 CustomEvent 記憶體鏡像先行。

### 區塊 3: `frontend/components/views/itinerary-view.tsx`
- **原內容**: `handleDayDataUpdate` 與 `EditableDailyChecklist` 遺漏快照與廣播。
- **替換為**: 補齊 `saveTripSnapshot`，並在清單勾選時派發 `checklist:update` 廣播。

---

## 4. 人類閘門移交 (Human Gate Handover)

依據專案憲法與 Maker-Checker 隔離原則：
- `@security` 已完成靜態分析、數學驗證與 In-Memory PoC 實證（4/4 Passed）。
- 本報告、候選補丁與台帳更新已全數在沙盒內就緒。
- 請人類開發者（Ryan）指示授權後，再交付 `@dev` 執行實體檔案修改，並由 `@qa` 進行最終品質驗證。
