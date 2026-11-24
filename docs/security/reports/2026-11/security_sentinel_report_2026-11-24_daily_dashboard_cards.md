# 🛡️ Security Sentinel 沙盒對抗審查報告：當日智慧看板 5 分頁大統一與安全網加固 (2026-11-24)

> **稽核基準**: `8322671` (`main`)
> **稽核模式**: Pre-Execution Worktree Spiking (`.worktrees/review-sandbox`) ✕ Red→Green PoC ✕ Mantis Block G ✕ `runner.py --mode fast` (5 切片平行對抗審查) ✕ Harness² Ledger 守恆
> **審查判定**: **`5 / 5` `DISMISSED` (Verified Safe Post-Patch)**（`0 confirmed`, `0 inconclusive`，單次 5 切片平行驗證全通過）
> **台帳守恆驗證**: `444` Targets (`53` verified/unresolved + `204` remediated + `187` dismissed/safe = `444`, `scripts/validate_security_ledger.py RC=0`)

---

## 1. 執行摘要與沙盒實證 (Executive Summary)

1. **Pre-Execution Worktree Spiking (`.worktrees/review-sandbox`) Red→Green PoC 實證**：
   - **Mantis Block G Benign Control (`BENIGN_RC=0`, `1 passed`)**：實證未套用補丁前，`EditableDailyTips`、`EditableDailyChecklist` 與 `EditableDailyAIReview` 之既有公開 Props 與核心資料渲染契約正常運作。
   - **Pre-Patch Red Check (`RED_RC=1`, `7 failed | 1 skipped`)**：
     1. **`exploit_poc_1` (`EditableDailyChecklist.tsx:L91-L120` Debounce 計數器洩漏與中間髒狀態回滾)**：使用者在 500ms 防抖視窗內快速點擊兩項清單時，`pendingUpdatesCount.current++` 於 `clearTimeout` 前無條件累加，而 `pendingUpdatesCount.current--` 僅在被取消的 `setTimeout` `finally` 中執行，造成計數器永久 `> 0` 洩漏，徹底鎖死後續外部 Props 與 `tabiji:collab-event` 即時協同同步；且 API 失敗回滾時錯誤退回至最後一次點擊前的過渡閉包狀態而非防抖前已確認基準 (`committedItemsRef.current`)。
     2. **`exploit_poc_2` (`EditableDailyChecklist.tsx:L124-L153` 缺 `catch` 未處理拒絕與單幀雙擊重複新增)**：`addItem` 僅有 `try ... finally` 而無 `catch` 區塊，當 `onUpdate` 拋出網路異常時引發 Unhandled Promise Rejection；且僅依賴非同步 React State `isUpdating` 無法攔截同幀連點快選晶片（如 `+ 護照`）造成的重複建立。
     3. **`exploit_poc_3` (`EditableDailyTips.tsx:L476, L608` & `EditableDailyChecklist.tsx:L200` 裸呼叫 `localStorage.getItem` 崩潰)**：於未傳入 `userId` 且處於 Safari 隱私瀏覽或受限 WebView 時，切換隱私直接拋出未捕獲 `DOMException: SecurityError`。
     4. **`exploit_poc_4` (`EditableDailyTips.tsx:L114-L120` `IconPicker` 自訂輸入整句溢位與 UTF-16 Surrogate Pair 風險)**：原代碼註解稱擷取首字元卻實際寫入 `val.trim()` 整句字串，導致貼上長句撐破圖示框。
     5. **`exploit_poc_5` (`EditableDailyChecklist.tsx` 500ms 防抖期間立即刪除／新增／編輯之幽靈計時器髒寫競態)**：勾選項目後 500ms 內執行立即刪除（`removeItem`）、新增（`addItemWithText`）或儲存編輯（`handleSaveEdit`）時，若未取消進行中的 `debounceRef.current`，過期計時器將於 500ms 後拿舊閉包復活已刪除項目；已透過 `cancelPendingDebounce()` 完整攔截。
     6. **`exploit_poc_6` (`EditableDailyTips.tsx` `CurrencyPillSelector` 自訂幣別點擊消失與編輯模式隱私微開關)**：既有非預載幣別（如 `GBP`）在編輯模式點擊預設幣別膠囊後不會消失，且支援於批次編輯模式 (`editingCosts` / `editingTickets`) 直接切換 `PrivacyTogglePill`。
     7. **`exploit_poc_7` (`IOSBottomSheet` 內 `IconPicker` Popover 與內嵌表單 `Escape` 隔離及全動作單幀互斥鎖)**：於 `IconPicker` Popover 或內嵌新增／編輯 `<Input>` 按下 `Escape` 僅收合當前內層介面而不誤關外層 `IOSBottomSheet`，且全數 11 支 tips 變更處理器、checklist 刪除／隱私／編輯儲存與 `EditableDailyAIReview` 生成／清除皆受同步 `useRef` 單幀互斥鎖保護。
   - **Post-Patch Green Check (`GREEN_RC=0`, `26/26 passed across 3 dashboard suites`)**：
     - 導入 `hasPendingDebounceRef` + `cancelPendingDebounce` + `committedItemsRef` 守恆防抖、`actionLockRef` / `noteLockRef` / `costLockRef` / `ticketLockRef` 全路徑單幀互斥鎖、`resolveOwnerId` `try/catch` 儲存防護、`CurrencyPillSelector` 初始與既有自訂幣別保留，以及 `extractFirstGrapheme` (`Intl.Segmenter` 字素叢集擷取 + IME `onCompositionEnd` 正規化) 後，全數轉綠通過。
2. **沙盒與主工作區靜態品質門禁**：
   - `npx tsc --noEmit`: **`0 errors`** (`RC=0`)
   - `npm run lint`: **`0 errors, 0 warnings`** (`RC=0`)
   - `npx vitest run __tests__/daily-dashboard-cards.test.tsx __tests__/itinerary-dashboard-layout.test.tsx __tests__/post-audit-remediation-sentinel.test.tsx`: **`3 files / 26 passed`** (`RC=0`)
3. **Security Sentinel CLI (`runner.py --mode fast`)**：
   - 5 切片平行物理沙盒驗證 (`agy.exe --sandbox`)：**`5 / 5 DISMISSED`** (`0 confirmed`, `0 inconclusive`, `RC=0`)。

---

## 2. 攻擊面覆蓋矩陣 (Attack Surface Coverage Matrix)

| Target ID | Trust Boundary | Attack Vector | Pre-Patch PoC | Post-Patch Sentinel Verdict |
|---|---|---|---|---|
| `frontend/components/itinerary/EditableDailyTips.tsx:grapheme_storage_and_micro_form_selectors` | `browser_local` | `surrogate_pair_corruption_or_storage_security_error` | `RED_RC=1` (`exploit_poc_3`, `exploit_poc_4`) | `DISMISSED` (`REMEDIATED`) |
| `frontend/components/itinerary/EditableDailyTips.tsx:single_frame_lock_and_privacy_handlers` | `browser_local` | `double_tap_duplicate_mutation_or_privacy_owner_leak` | `RED_RC=1` (`exploit_poc_3`, `spec_2`) | `DISMISSED` (`REMEDIATED`) |
| `frontend/components/itinerary/EditableDailyChecklist.tsx:debounce_counter_conservation_and_add_lock` | `browser_local` | `debounce_counter_leak_or_unhandled_promise_rejection` | `RED_RC=1` (`exploit_poc_1`, `exploit_poc_2`) | `DISMISSED` (`REMEDIATED`) |
| `frontend/components/itinerary/EditableDailyChecklist.tsx:decoupled_row_buttons_and_ime_guard` | `browser_local` | `nested_interactive_buttons_or_ime_premature_submit` | `RED_RC=1` (`spec_1`, `spec_3`) | `DISMISSED` (Safe) |
| `frontend/components/itinerary/EditableDailyAIReview.tsx:sentinel_contract_and_dark_mode_contrast` | `browser_to_edge` | `cross_day_optimistic_state_bleed_or_locale_omission` | `RED_RC=1` (`spec_1`) | `DISMISSED` (Safe) |

---

## 3. 切斯特頓圍欄三問考古與刪除審查 (Code Archaeology & Deletion Audit)

| 變更檔案與位置 | 刪除／替換內容 | 歷史功能與設計初衷 (`legacy_function` & `design_intent`) | 刪除風險與 100% 承接機制 (`regression_risk`) |
|---|---|---|---|
| `EditableDailyTips.tsx` (原 L838, L944, L1005, L1111) | 4 處原生 `<select>` 與 `w-32` 窄金額輸入容器 | 早期為在單行內同時塞入項目、幣別與金額，採用原生 `<select>` 節省實作成本並固定 `w-32` 寬度。 | 原生 `<select>` 在暗黑模式缺背景色且 `w-32` 造成大額數字嚴重截斷；由 `CurrencyPillSelector`（自動相容並附加既有非預載幣別如 `GBP`）＋滿寬 `tabular-nums` 金額欄 100% 承接。 |
| `EditableDailyTips.tsx` / `EditableDailyChecklist.tsx` / `EditableDailyAIReview.tsx` | 滿版粉蠟筆底色 (`bg-amber-50`、`from-indigo-50`、`bg-blue-50`、`bg-slate-50`)、`EditableDailyAIReview` 外層 `mx-6 mt-4`、以及所有 `Button variant="ghost"` | 在 `IOSBottomSheet` 5 分頁抽屜架構誕生前，5 個區塊為行程主頁垂直堆疊，故以整塊高彩度底色區分模組並加 `mx-6` 對齊主頁邊距。 | 進入底抽分頁後滿版粉蠟筆色與和紙品牌割裂，`mx-6` 造成雙重縮排，`variant="ghost"` 觸發 `#E56E25` 亮橘色偏；改由統一和紙白／深翠黑底座 (`bg-white/95 dark:bg-[#182320]/90`)、圓角語意圖示徽章與中性膠囊按鈕完整承接。 |
| `EditableDailyChecklist.tsx` (原 L87-L121, L299) | `toggleItem` 每次點擊無條件 `pendingUpdatesCount.current++` 與外層 `isUpdating && "pointer-events-none"` | 原意為在 500ms 防抖同步期間阻擋外部舊 Props 覆寫並防止使用者連點。 | 原寫法在 500ms 內點擊第二次即因 `clearTimeout` 永久洩漏 `pendingUpdatesCount > 0` 鎖死協同同步，且整卡 `pointer-events-none` 造成畫面閃爍；改由 `hasPendingDebounceRef` 單次計數守恆、`committedItemsRef` 基準回滾、`actionLockRef` 單幀互斥鎖與個別按鈕 `disabled` 精準承接。 |
| `EditableDailyChecklist.tsx` (原 L382-L461) | 外層 `motion.div onClick={() => toggleItem(item.id)}` 包裹內部隱私與刪除 `<button>` | 讓整列可點擊勾選，同時在右側提供隱私與刪除操作並以 `e.stopPropagation()` 隔離。 | 外層 `div` 缺乏原生鍵盤無障礙語意且依賴事件冒泡攔截；改為容器內三個同級 `<button type="button">`（主勾選按鈕＋隱私按鈕＋刪除按鈕）Sibling 解耦架構，兼顧 WAI-ARIA 無障礙與零冒泡誤觸。 |

---

## 4. Deliverables 索引

- **候選清單**: [`candidates_daily_dashboard_cards_2026-11-24.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/candidates/candidates_daily_dashboard_cards_2026-11-24.json)
- **Sentinel 結果**: [`findings_daily_dashboard_cards_2026-11-24.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/findings/findings_daily_dashboard_cards_2026-11-24.json)
- **統一補丁**: [`patch_candidate_daily_dashboard_cards_2026-11-24.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_daily_dashboard_cards_2026-11-24.diff)
- **覆蓋台帳**: [`security-coverage-ledger.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/security-coverage-ledger.json)
