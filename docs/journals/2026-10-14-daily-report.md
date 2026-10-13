# 📅 Daily Report - 2026-10-14 (Universal Trip Cover Pipeline, Reschedule Zero-Shift Engine & Dashboard Bento Polish)

> **系統狀態**：🟢 Production Deployed & Synced (`043b538`), 0 TypeScript Errors, 0 ESLint Warnings, 100% Tests Green (Frontend 68/68 Suites Passing, 455/455 Tests Passing; Backend 143/143 Tests Passing, 5 skipped), Working Tree Clean, GitHub main branch synced.  
> **今日關鍵提交串列 (Full Day Commit Stream)**：
> - [`043b538`](https://github.com/tyrantpiper/tabiji/commit/043b538) `feat(itinerary): decouple date shift dominoes, enhance day lifecycle & align dashboard bento UI` (2026-10-14 02:42:21 +0800)
> - [`2734f12`](https://github.com/tyrantpiper/tabiji/commit/2734f12) `feat(trip): unify destination cover pipeline and streamline global inspiration pills` (2026-10-14 00:22:40 +0800)

---

## 🏆 深度專案復盤：七大工程與架構里程碑 (Seven Core Milestones)

本日完成 Tabidachi 行程封面視覺一致性閉環、日曆改期活動擠壓缺陷徹底根除、天數生命週期架構移轉、資訊儀表板 CRO 視覺動線重構、天氣卡牌去雜訊與地理搜尋對齊，以及全棧自動化測試防禦固化：

---

### 里程碑一：全端行程封面統一自動解析管線 (Universal Trip Cover Pipeline)
1. **業務挑戰與感官痛點根因**：
   - 使用者反映「首頁卡片與行程清單顯示深色灰底漸層色塊，但點進行程齒輪設定卻看得到預設風景照片，感官上呈現隨機性」。
   - 代碼根因：`TripSettingsView.tsx` 早已內建 `trip.cover_image || resolveDestinationCover(trip.title)` 動態保底；但首頁儀表板（`TabijiHomeDashboard.tsx`）、總覽清單（`TripList.tsx`）與公開分享頁面（`PublicTripView.tsx`）僅以 `{trip.cover_image ? <Image /> : <無圖色塊>}` 判斷；歷史或空值行程資料庫中為 `NULL`，導致清單為空色塊、進設定齒輪卻生出圖片。
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
   - 原手動建立行程之靈感快選膠囊共有 5 個，數量過多且全數集中於東亞區域。
   - 經 `/Idea to Spec` 與規格重構，精簡為 **3 個跨洲全球代表性都會**：
     - 🇯🇵 **東京** (亞洲代表 / Tokyo 5-Day Explorer)
     - 🇫🇷 **巴黎** (歐洲代表 / Paris 5-Day Cultural Stroll)
     - 🇺🇸 **紐約** (美洲代表 / NYC 5-Day Urban Discovery)
   - 統一為經典 5 日行程，支援中英雙語 (`i18n`) 動態切換標籤與預設行程名稱。
2. **本地時區安全日期運算標準 (`addDaysToLocalYMD`)**：
   - 徹底淘汰 `new Date().toISOString().split('T')[0]`。因在 UTC-5 或跨日時區邊界，UTC 時間會導致跨日滑移。
   - 封裝本地時區安全純函數 `addDaysToLocalYMD(startDate, 4)`，透過 `[year, month, day]` 本地構造進行純數學運算，保證在跨月（10/31 ➔ 11/04）、跨年（12/29 ➔ 01/02）與閏年（2028-02-27 ➔ 2028-03-02）情境下天數恆等於 5 天。

---

### 里程碑三：日曆改期骨牌位移算法根除 ✕ 零位移天數保持引擎 (Zero-Shift Duration Engine)
1. **致命 Bug 根因與物理沙盒對抗證偽**：
   - 使用者反饋「原 3 天行程改為另一個 3 天行程時，所有活動全被擠壓至第 1 天，筆記銷毀」。
   - **代碼病灶**：舊代碼在 `trips.py` 計算 `start_shift = (old_start - new_start).days`。當延後出發（`start_shift < 0`）時，第一階段將 `day_number <= shift_abs` 暫時更名為 `shift_abs + 1`；緊接的第二階段 `day_number > shift_abs` 又重新抓取這批剛更名的活動並強制減去 `shift_abs`，直接將所有活動二次輾壓變成 `day_number = 1`，並由 `del` 清空每日筆記！
2. **零位移天數保持架構重構**：
   - 徹底移除 119 行舊骨牌平移算法。
   - 確立「行程活動核心資產是天數序號（Day 1~N），而非公曆物理日期」：
     - **天數相等時**：活動 100% 原位保留、零位移寫入。
     - **天數增加時**：原活動原位不動，末尾追加空白天。
     - **天數縮短時**：僅對 `day_number > new_days` 的超出天數執行合併（merge）或刪除（delete）。
   - 補齊 `created_by` 擁有者權限檢查與 `start_date > end_date` HTTP 400 攔截。
3. **測試固化**：新增 `backend/tests/test_trip_dates_shift.py`（5 項單元測試 100% 通過）。

---

### 里程碑四：前端 0ms 樂觀響應 ✕ 夾角遮蔽破除 ✕ 快照回滾防禦
1. **0ms 樂觀注入與多層快取同步**：
   - 在 [`frontend/components/views/itinerary-view.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/views/itinerary-view.tsx) 引入 `reloadTripDetail(optimisticTrip, false)` 與 `saveTripSnapshot`，改期後立即反映，告別手動跳出頁面刷新。
2. **`maxDayFromItems` 夾角陷阱破除**：
   - `totalDays` 計算函數為 `Math.max(daysFromDates, maxDayFromItems)`。在縮短天數時，若未同步裁剪 `optimisticTrip.days` 陣列，`maxDayFromItems` 會維持舊天數而抵消縮短效果。本次實作在客戶端預先執行 `optimisticDays` 修剪/合併，並將 `focusedDay` 安全夾止至新天數上限。
3. **雙向快照硬核回滾防禦**：
   - 呼叫 API 前深拷貝 `backupTrip = { ...currentTrip }`；若遭遇網路異常或 5xx 錯誤，於 `catch` 區塊立即執行 `reloadTripDetail(backupTrip, false)` 並還原 IndexedDB，確保前端絕不脫鉤。

---

### 里程碑五：天數結構管理全域遷移 ✕ 行程設定二級確認對話框
1. **視覺痛點根治**：
   - 原頂部日期膠囊下方懸掛的紅色「刪除這一天」按鈕破壞垂直對稱且極易誤觸。
   - 徹底自 `ItineraryHeader.tsx` 移除該懸掛按鈕，恢復水平日期膠囊等高與 iOS 玻璃擬態。
2. **管理專區建立**：
   - 於 [`frontend/components/itinerary/TripSettingsView.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/itinerary/TripSettingsView.tsx) 開闢「天數結構管理 (Day Structure Management)」分組。
   - 條列所有天數、日期標籤、活動計數；提供安全刪除操作，在 `totalDays <= 1` 自動禁用，並附帶不可逆二級安全確認對話框。
3. **測試固化**：新增 `frontend/__tests__/calendar-date-shift-instant-sync.test.tsx`（3/3 通過）。

---

### 里程碑六：行程看板 Bento Grid 佈局調換 ✕ 抽屜分頁標籤順序對齊
1. **CRO 視覺動線與重要性調換**：
   - 依照使用者需求與單手操作熱區分析，將高頻操作的「✅ 行前清單」移至右欄上方（Row 1, Col 2），將「💰 預估花費」移至右欄下方（Row 2, Col 2）。
   - 保留微型進度條、完成徽章、多幣別標籤與粗體數額，兩側卡片等高（`min-h-20.5`）。
2. **心智模型 100% 同構**：
   - [`frontend/components/itinerary/IOSBottomSheet.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/itinerary/IOSBottomSheet.tsx) 分頁標籤順序同步調整為：`[AI 審核] ➜ [重點提醒] ➜ [行前清單] ➜ [交通票券] ➜ [預估花費]`。
3. **測試固化**：於 `itinerary-dashboard-layout.test.tsx` 補強 2x2 Grid 卡片順序與 Sheet Tabs 嚴格排列斷言（4/4 通過）。

---

### 里程碑七：天氣卡牌頂部去雜訊 ✕ 國家地點搜尋雙層對齊
1. **極簡視覺還原**：
   - 於 [`frontend/components/itinerary/WeatherPanel.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/itinerary/WeatherPanel.tsx) 移除左上角 GPS 經緯度微標籤（`25.10, 121.55`），還原純淨的 `📍 [地點名稱] ✏️`。
2. **地點搜尋模組標準化對齊**：
   - 重構 [`frontend/components/itinerary/LocationEditDialog.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/itinerary/LocationEditDialog.tsx)，對齊 `ActivityEditModal` 規格：
     - 第一層：雙欄微型篩選條（國家 Datalist 支援台、日、韓、泰等手打搜尋或自選 + 地區動態下拉選單）。
     - 第二層：全寬地點名稱輸入框 + 藍色搜尋按鈕。
     - 移除多餘的 `p-2` 內縮外框，統一 `h-10`、`rounded-xl` 與一致背景，達成像素級垂直邊界對齊。
     - 消除 i18n 重複放大鏡圖標。
3. **測試固化**：新增 `frontend/__tests__/location-edit-dialog-search.test.tsx`（2/2 通過）。

---

## 🏛️ 架構決策紀錄 (Architecture Decisions Added)

### 決策 28：全端行程封面統一自動解析與髒資料防禦架構 (Universal Trip Cover Resolver)
- **單一真理與三層防禦模型**：自訂封面優先 ➔ 惡意偽字串過濾 ➔ 標題/目的地別名確定性推導 ➔ 預設封面托底。後端寫入期與前端讀取期雙重閉環。

### 決策 29：全球代表性靈感快選與本地時區安全日期運算標準 (Global Inspiration Pills & Timezone Safety)
- **全球三大都會模型 (Tokyo, Paris, NYC)**：精簡靈感膠囊至 5 日經典範本。嚴禁使用 `toISOString()`，全面採用本地時區解構純函數 `addDaysToLocalYMD`，杜絕跨日時差滑移。

### 決策 30：日曆改期天數序號絕對保持律 (Zero-Shift Duration Preservation Engine)
- **天數序號解耦**：改期時 Day 1~N 序號 100% 原位保留。廢除骨牌平移算法，天數相等或增加時 0 次破壞性寫入；天數縮短時由使用者指定合併或刪除，兼備建立者權限攔截。

### 決策 31：SWR 樂觀更新之 days 陣列預修剪與快照回滾防衛 (Optimistic Pruning & Rollback Invariance)
- **雙向快照防禦**：縮短行程時前端樂觀構建預先修剪 `days` 陣列並夾止 `focusedDay`，破除 `maxDayFromItems` 夾角遮蔽；呼叫前深拷貝快照，網路中斷時 0ms 硬核回滾。

### 決策 32：天數結構管理收攏至行程設定視圖 (Trip Settings Day Structure Governance)
- **操作空間分離**：頂部導航膠囊專注於檢視切換，破壞性天數刪除全數收攏至 `TripSettingsView`，搭配單日行程禁用與不可逆二級確認對話框。

### 決策 33：行程看板 2x2 Bento 資訊層級對調與 Tabs 心智模型對齊 (Bento Grid CRO & Tabs Parity)
- **視覺動線對齊**：右上角配置高頻之「行前清單」，右下角配置「預估花費」；底層抽屜標籤同步同構對齊。

### 決策 34：天氣卡牌極簡去雜訊與地理搜尋雙層對齊 (Weather Location & Datalist Search Alignment)
- **極簡與雙層規範**：卡牌左上角隱藏經緯度；對話框搜尋模組對齊行程卡牌（國家 Datalist 手打 + 地區動態下拉 + 全寬搜尋），消除 `p-2` 內縮框達成像素級垂直對齊。

---

## 🛡️ 今日避坑指南 (Failed Paths & Hard Lessons)

1. **出發日位移 `start_shift < 0` 骨牌平移雙重輾壓陷阱 (FP-028)**：
   - *現象*：改期延後出發時，活動先更名為 `shift_abs + 1`，緊接著下一階段查詢大於 `shift_abs` 又再度扣除，直接將所有天數活動全部碾壓成 Day 1，並刪除每日筆記。
   - *教訓*：改期絕不可做骨牌式位移算術，必須直接解耦出發日與天數序號。
2. **前端 `maxDayFromItems` 夾角遮蔽天數縮短樂觀更新陷阱 (FP-029)**：
   - *現象*：縮短天數樂觀更新時，若僅修改起訖日期而未同步裁剪 `optimisticTrip.days` 陣列，`maxDayFromItems` 仍返回舊總天數，導致頂部天數膠囊在 0ms 樂觀期間無法即刻縮短。
   - *教訓*：前端樂觀構建時必須對資料載體執行深層同步修剪。
3. **外層包裹容器 `p-2` 造成次級篩選條與搜尋框邊界錯位陷阱 (FP-030)**：
   - *現象*：為第一層篩選條添加帶 `p-2` 的卡片外框背景，而第二層搜尋框為裸組件，導致第一層內部輸入框左右各縮進 8px，與第二層搜尋框在視覺上產生嚴重的邊界鋸齒與未對齊感。
   - *教訓*：同組件內部輸入元素應統一寬度維度與圓角規格，避免局部嵌套單獨 padding 容器。
4. **i18n 字串前綴圖標重複包裝陷阱 (FP-031)**：
   - *現象*：`t('loc_search')` 字典內已定義 `"🔍 搜尋地點"`，JSX 外層又手動添加 `<span>🔍</span>`，導致介面出現雙重放大鏡 `🔍 🔍`。
   - *教訓*：使用 i18n 標籤前需確認翻譯文本是否已自帶 Emoji 圖標，杜絕重複圖標包裝。

---

## 🔴 技術債與後續待辦 (Technical Debt & Next Steps)

1. **投資盡職調查報告後續追蹤**：
   - 本地未追蹤之 [`docs/research/investment_due_diligence_linkincubator_analysis_2026.md`](file:///d:/Project/Tabidachi/travel-pwa/docs/research/investment_due_diligence_linkincubator_analysis_2026.md) 待融資推演會議前進一步研擬。
2. **端到端 E2E 視覺回歸基線更新**：
   - 在下一次重大發布前，透過 `/verify-e2e` Playwright 重新捕獲改期與 Bento 調整後的最新全域視圖截圖。
