# 📅 Daily Report - 2026-10-14 (Universal Trip Cover Pipeline, Global Inspiration Pills & Security Sentinel Sandbox)

> **系統狀態**：🟢 Production Deployed & Synced (`2734f12`), 0 TypeScript Errors, 0 ESLint Warnings, 100% Tests Green (Frontend 67/67 Suites Passing, 451/451 Tests Passing; Backend 138/138 Tests Passing, 5 skipped), Working Tree Clean, GitHub main branch synced.  
> **今日關鍵提交串列 (Full Day Commit Stream)**：
> - [`2734f12`](https://github.com/tyrantpiper/tabiji/commit/2734f12) `feat(trip): unify destination cover pipeline and streamline global inspiration pills` (2026-10-14 00:22:40 +0800)

---

## 🏆 深度專案復盤：四大工程與架構里程碑 (Four Core Milestones)

本日完成 Tabidachi 行程封面視覺一致性閉環、建立行程體驗現代化精簡，以及 Security Sentinel 物理沙盒對抗證偽審核，交付極具質感的全端確定性體驗：

---

### 里程碑一：全端行程封面統一自動解析管線 (Universal Trip Cover Pipeline)
1. **業務挑戰與感官痛點根因**：
   - 使用者反映「首頁卡片與行程清單顯示深色灰底漸層色塊，但點進行程齒輪設定卻看得到預設風景照片，感官上呈現隨機性」。
   - **代碼根因**：
     - `TripSettingsView.tsx` 早已內建 `trip.cover_image || resolveDestinationCover(trip.title)` 動態保底。
     - 但首頁儀表板（`TabijiHomeDashboard.tsx`）、總覽清單（`TripList.tsx`）與公開分享頁面（`PublicTripView.tsx`）僅以 `{trip.cover_image ? <Image /> : <無圖色塊>}` 判斷；歷史或空值行程資料庫中為 `NULL`，導致清單為空色塊、進設定齒輪卻生出圖片。
2. **全端統一解析助手 (`getTripCoverUrl`)**：
   - 於 [`frontend/lib/destination-covers.ts`](file:///d:/Project/Tabidachi/travel-pwa/frontend/lib/destination-covers.ts) 建立並匯出全域統一解析器：
     1. **自訂封面優先**：若使用者手動上傳相片，以使用者明確意志為第一優先。
     2. **惡意字串與髒資料防禦**：嚴格過濾排除資料庫遺留字串化偽值 `"null"`、`"undefined"` 及全空白字串。
     3. **確定性動態保底**：空值時 100% 動態調用 `resolveDestinationCover(title, destination)`，無匹配時以 `DEFAULT_COVER_IMAGE` 托底。
3. **後端寫入期保底補齊**：
   - 在 [`backend/routers/trips.py`](file:///d:/Project/Tabidachi/travel-pwa/backend/routers/trips.py) 的 `create_manual_trip` (L538) 同步補齊後端保底：
     `clean_cover = request.cover_image.strip() if (request.cover_image and request.cover_image.strip()) else resolve_destination_cover_url(request.title)`
   - 確保寫入資料庫當下即為有效風景圖片 URL，達成寫入期與讀取期雙重閉環。

---

### 里程碑二：手動建立行程之全球代表性靈感快選精簡 (Global Inspiration Pills)
1. **認知負荷減輕與版面重構**：
   - 原手動建立行程之靈感快選膠囊共有 5 個（東京、京都、沖繩、北海道、香港），數量過多且全數集中於東亞區域。
   - 經 `/Idea to Spec` 與規格重構，精簡為 **3 個跨洲全球代表性都會**：
     - 🇯🇵 **東京** (亞洲代表 / Tokyo 5-Day Explorer)
     - 🇫🇷 **巴黎** (歐洲代表 / Paris 5-Day Cultural Stroll)
     - 🇺🇸 **紐約** (美洲代表 / NYC 5-Day Urban Discovery)
   - 統一為經典 5 日行程，支援中英雙語 (`i18n`) 動態切換標籤與預設行程名稱。
2. **本地時區安全日期運算標準 (`addDaysToLocalYMD`)**：
   - 徹底淘汰 `new Date().toISOString().split('T')[0]`。因在 UTC-5 或跨日時區邊界，UTC 時間會導致跨日滑移。
   - 封裝本地時區安全純函數 `addDaysToLocalYMD(startDate, 4)`，透過 `[year, month, day]` 本地構造進行純數學運算，保證在跨月（10/31 ➔ 11/04）、跨年（12/29 ➔ 01/02）與閏年（2028-02-27 ➔ 2028-03-02）情境下天數恆等於 5 天。

---

### 里程碑三：Security Sentinel 物理沙盒對抗證偽審核 (Adversarial Security Audit)
1. **物理隔離與沙盒壓測**：
   - 建立候選攻擊假設帳本 [`docs/security/candidates_cover_pills_harmony_2026-10-13.json`](file:///d:/Project/Tabidachi/travel-pwa/docs/security/candidates_cover_pills_harmony_2026-10-13.json)。
   - 更新專案攻擊面帳本 [`docs/security/security-coverage-ledger.json`](file:///d:/Project/Tabidachi/travel-pwa/docs/security/security-coverage-ledger.json)（審計目標自 73 擴充至 75 項）。
   - 產出正式安全審計報告 [`docs/security/security_sentinel_report_2026-10-13_cover_pills.md`](file:///d:/Project/Tabidachi/travel-pwa/docs/security/security_sentinel_report_2026-10-13_cover_pills.md)。
2. **關鍵對抗證偽成果：駁回「點擊標題清空封面」構想**：
   - Sentinel 沙盒對抗審查精準駁回了原本「點選靈感膠囊時強制重設 `coverImage = ""`」之構想。
   - *證偽分析*：若使用者已手動上傳精心挑選的照片，因嘗試點擊膠囊更換標題建議而遭靜默清空自訂照片，屬於破壞性資料遺失（Destructive Data Loss）。嚴格確立「自訂照片永遠優先於標題自動推導」之不變量。
3. **雙端自動化測試套件固化**：
   - 前端 Vitest 沙盒：[`frontend/__tests__/cover-pills-sentinel.test.ts`](file:///d:/Project/Tabidachi/travel-pwa/frontend/__tests__/cover-pills-sentinel.test.ts) (12/12 通過)
   - 後端 Pytest 沙盒：[`backend/tests/test_cover_pills_sentinel.py`](file:///d:/Project/Tabidachi/travel-pwa/backend/tests/test_cover_pills_sentinel.py) (3/3 通過)

---

### 里程碑四：Bug Hunter 閉環 ✕ Tailwind CSS v4 語法現代化
1. **IDE Migration Lint Warnings 根治**：
   - 偵測到 [`frontend/app/share/[shareCode]/PublicTripView.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/app/share/[shareCode]/PublicTripView.tsx) 存在兩處 Tailwind v4 警告：
     - `bg-gradient-to-br` 遷移至現代原生 CSS 命名 `bg-linear-to-br`。
     - `flex-shrink-0` 遷移至現代簡寫 `shrink-0`。
2. **TDD Red-Green 驗證**：
   - 建立守門測試 [`frontend/__tests__/public-trip-view-lint-sentinel.test.ts`](file:///d:/Project/Tabidachi/travel-pwa/frontend/__tests__/public-trip-view-lint-sentinel.test.ts)。
   - 實踐 Red（2 項失敗）➔ Green（2 項通過）標準迴圈，將全量測試套件推升至 67 Suites、451 Tests 100% 綠燈。

---

## 🏛️ 架構決策紀錄 (Architecture Decisions Added)

### 決策 28：全端行程封面統一自動解析與髒資料防禦架構 (Universal Trip Cover Resolver)
- **單一真理與三層防禦模型 (Three-Tier Cover Precedence)**：行程封面展示徹底摒棄局部組件 ad-hoc 判斷，統一套用 `getTripCoverUrl(coverImage, title, destination)`：
  1. *第 1 層 (Explicit User Will)*：使用者自訂上傳封面絕對優先。
  2. *第 2 層 (Sanitization Defense)*：過濾並攔截資料庫或外部傳入之 `"null"`、`"undefined"`、全空白偽字串，防止壞字串穿透至 `<Image src>`。
  3. *第 3 層 (Deterministic Dynamic Resolution)*：無圖或壞字串時，由標題與目的地別名即時映射高畫質代表風景照片；全未匹配時由 `DEFAULT_COVER_IMAGE` 托底。
- **寫入期與讀取期雙重閉環 (Write-Read Dual Invariance)**：後端手動建立行程路由（`create_manual_trip`）在存入資料庫前直接執行 `resolve_destination_cover_url(title)` 寫入實體圖片，前端讀取層亦全面以 `getTripCoverUrl` 渲染，根絕歷史 NULL 行程引起的顯示不一致。

### 決策 29：全球代表性靈感快選與本地時區安全日期運算標準 (Global Inspiration Pills & Timezone Safety)
- **全球三大代表都會模型 (Tri-Continental Paradigm: Tokyo, Paris, NYC)**：手動建立行程靈感膠囊精簡為東京（亞洲）、巴黎（歐洲）、紐約（美洲），統一為經典 5 日行程，支援 `i18n` 雙語。
- **本地時區安全純函數原則 (Local Timezone Date Safety)**：計算預設結束日期時嚴禁使用 `new Date().toISOString().split('T')[0]`。全面採用基於本地年/月/日解構與構造之 `addDaysToLocalYMD` 純函數，確保在任何時區、跨月跨年與閏年環境下，結束日期天數恆等於 5 天。

---

## 🛡️ 今日避坑指南 (Failed Paths & Hard Lessons)

1. **點擊靈感膠囊強制重設自訂封面之破壞性陷阱**：
   - *現象*：初版構想認為「切換靈感城市膠囊時應同步將 `coverImage` 重設為空字串，以讓新標題自動對應封面」。
   - *教訓*：Security Sentinel 對抗審查指出，若使用者已手動上傳自訂照片，點擊建議膠囊會非預期抹除使用者已上傳的照片。修復方案：自訂照片始終保持最高優先級，切換標題時絕不破壞既有已上傳之 `coverImage`。
2. **`toISOString()` 之時區跨日滑移陷阱**：
   - *現象*：在 UTC 西半球時區（如紐約 UTC-5），使用 `toISOString()` 轉字串會因 UTC 時間提前或延後產生日期回退 1 天的錯位。
   - *教訓*：日期運算與格式化必須完全立足於客戶端本地時區解析，透過 `addDaysToLocalYMD` 純數學運算杜絕時差滑移。
3. **Tailwind CSS v4 漸變與伸縮類別警告**：
   - *現象*：`bg-gradient-to-*` 與 `flex-shrink-*` 雖具相容性但會觸發 IDE 與 linter 的 migration 警告。
   - *教訓*：及時升級為 Tailwind v4 現代化標準類別（`bg-linear-*`, `shrink-0`），維持 0 warnings 代碼整潔度。

---

## 🔴 技術債與後續待辦 (Technical Debt & Next Steps)

1. **行程卡片直接父容器高度檢驗**：
   - 觀察在極端 CSS 佈局首幀下，Next.js `<Image fill />` 是否偶發拋出高度 0 警告，後續可評估移除卡片內多餘的一層 `relative w-full h-full` 包覆。
2. **DialogContent a11y 標籤微調**：
   - 針對未包含 `<DialogDescription>` 的對話框補齊 `aria-describedby={undefined}`，徹底消除開發環境 console 提醒。
3. **投資盡職調查報告後續追蹤**：
   - 本地未追蹤之 [`docs/research/investment_due_diligence_linkincubator_analysis_2026.md`](file:///d:/Project/Tabidachi/travel-pwa/docs/research/investment_due_diligence_linkincubator_analysis_2026.md) 待專案融資會議時進一步整理。
