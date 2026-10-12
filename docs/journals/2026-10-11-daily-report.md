# 📅 Daily Report - 2026-10-11 (Master Full-Day Consolidation)

> **系統狀態**：🟢 Production Deployed & Verified, Global Tax Actuary Live, Double-Card Split Strategy Operational, Globalized 5-Day Import Templates Live (Tokyo/Paris/NYC), In-Memory Tally Tape Verified, Cross-Module AI Import Linked, 0 TypeScript Errors, 0 ESLint Warnings, 100% Tests Green (Frontend 57/57 Suites Passing, 406/406 Tests Passing; Backend 122/122 Passing), GitHub main branch synced (`14cfcd3`).  
> **今日關鍵提交串列 (Full Day Commit Stream)**：
> - [`14cfcd3`](https://github.com/tyrantpiper/tabiji/commit/14cfcd3) `feat(itinerary): globalize import templates and enforce 5-day currency alignment` (20:07:10 +0800)
> - [`4ca4819`](https://github.com/tyrantpiper/tabiji/commit/4ca4819) `feat(tools): add global tax actuary and smart credit card split strategy` (16:50:18 +0800)
> - [`50ba989`](https://github.com/tyrantpiper/tabiji/commit/50ba989) `fix(auth): atomic cache reset and splash preload to eliminate recovery race and stutter`
> - [`0cfe4f8`](https://github.com/tyrantpiper/tabiji/commit/0cfe4f8) `fix(pwa): restore golden statusBarStyle default and #fafaf9 theme to eliminate viewport upward offset`

---

## 🏆 深度專案復盤：六大核心工程里程碑 (Six Engineering Milestones)

本日完成全端視口穩定性、開機繪製管線、身分引繼防線、全球化多國 5 日行程範本與地理貨幣自動對齊，以及工具箱全新「全球免稅精算器 ✕ 雙卡拆單神策 ✕ 購物計算機」的全面交付：

---

### 里程碑一：iOS/iPadOS 狀態列黃金律回滾與視口原點修復 (Viewport Coordinate Golden Restoral)
1. **問題背景與真機現象**：
   - 使用者在手機與平板重新加入主畫面後，App 整體介面向上偏移，Header 與系統時間、電量指示條發生視覺重疊。
2. **底層 WebKit 視口幾何剖析 (WebKit Standalone Viewport Mechanics)**：
   - 當宣告 `statusBarStyle: "black-translucent"` 時，iOS WebKit 會將視口強行切換為「沉浸式全螢幕（Immersive Fullscreen）」，視口 (0,0) 原點直接貼齊物理螢幕最頂部，將頁面 Header 推入狀態列背後，產生致命視覺上移。
   - 當維持 `statusBarStyle: "default"` 時，WebKit 會將狀態列保留為系統專屬保留區，視口 (0,0) 原點嚴格錨定在狀態列正下方，配合 `themeColor: "#fafaf9"` 即可達成與系統頂部無縫融合，且絕無任何上移或重疊問題。
3. **黃金律精確回滾 (Golden Rollback)**：
   - 迅速執行精準回滾（Commit `0cfe4f8`），將 `layout.tsx` 中的 `statusBarStyle` 恢復為 `"default"`，`themeColor` 維持 `#fafaf9`，真機視覺原點百分之百完美復原。

---

### 里程碑二：開場動畫黑色勾勒原畫原生最高優先級預載入 (Splash Preload Pipeline & 60FPS Reveal)
1. **掉幀病因定位 (Decode Jank on First Frame)**：
   - 開機動畫所使用的高解析度黑色墨線立繪（`tabiji-art-mask.png` 2048×2048）與紙飛機（`tabiji-paper-plane.png`）原本是在 React 元件掛載時才由瀏覽器發現並非同步下載解碼，產生 50~100ms 的繪製卡頓。
2. **原生高優先級預載入標籤 (High-Priority Resource Hints)**：
   - 在全域 `layout.tsx` 的 `<head>` 靜態注入原生最高優先級 Resource Hints：
     ```html
     <link rel="preload" href="/images/tabiji-art-mask.png" as="image" type="image/png" fetchPriority="high" />
     <link rel="preload" href="/images/tabiji-paper-plane.png" as="image" type="image/png" fetchPriority="high" />
     ```
   - 瀏覽器自下載 HTML 第 0 毫秒起便指令 GPU 與網路管線在背景預先完成紋理加載，進場動畫啟動時已完全入駐記憶體，達成 60FPS 零掉幀絲滑展開。

---

### 里程碑三：帳號引繼原子四清、5秒過渡靜音鎖與防過度工程化 (Account Recovery Atomic Reset & Pragmatism)
1. **時序競爭與快取幽靈根除**：
   - **痛點**：輸入還原 Key 且行程完好存在時，偶發彈出黃色警告「該行程不存在或無存取權限，已切換至預設行程」。
   - **病因**：在 `landing-page.tsx` 中僅清理了獨立鍵值 `active_trip_id`，但 Zustand persist 儲存庫 `tabidachi-trip-storage` 仍殘留匿名模式的暫存指標；React 換場時反芻出舊 ID，而新帳號行程清單非同步拉取（SWR）尚未抵達，比對未中時誤觸刪除判定警告。
   - **處方**：
     - **原子四清**：還原瞬間同步深入 `tabidachi-trip-storage` 將暫存指標歸零。
     - **5 秒過渡靜音鎖**：在 `sessionStorage` 寫入 `tabiji_identity_transition_lock` 時間戳記。在引繼後 5 秒內，`trip-context.tsx` 即使遇到快取不匹配亦一律靜默對齊名下第一筆行程，物理阻斷誤判 Toast。
2. **極致容錯與全景式架構審核**：
   - 透過 `/Idea to Spec` 與 `/grill-me` 進行關鍵決策訪談，完成規格書 `docs/specs/auth/account-recovery-strict-verification-spec.md`。確立「保持現有高穩定度架構，不盲目新增後端驗證複雜度」之最佳實踐。

---

### 里程碑四：全球免稅精算器 ✕ 購物大鍵盤紙帶 ✕ 雙卡拆單神策 (Global Tax Actuary & Split Strategy)
1. **業務痛點破局**：
   - 原工具箱之 AI 標籤與行程視圖重複且功能受限，同時舊版精算器存在三大硬傷：日文硬編碼 `(税込)`、冷門國家無法選擇/自訂、缺乏連續四則運算大鍵盤與海外信用卡極限折抵建議。
2. **核心架構落地**：
   - **全球 18 國免稅規則與在地化動態標籤**：新增瑞士 (CHF 8.1%)、冰島 (ISK 24%)、挪威 (NOK 25%)、越南 (VND 10%) 等全球法規；依目的國自動呈現地道標籤（日本 `税込/税抜`、歐盟 `TTC/HT`、韓國 `과세/未稅`），並內建搜尋對話框與自訂國家/稅率/門檻表單。
   - **日本 2026/11/01 機場退稅改制時序守衛 (Temporal Guard)**：純函數 `resolveEffectiveTaxRule` 自動比對當前時間，在改制日後自動自適應切換為機場退稅（5% 手續費），提前防禦旅客時序斷層。
   - **零 eval 四則運算 AST 評估器 ✕ 暫存記帳紙帶 (Tally Tape)**：實作 AST 兩階段詞法解析求值器（乘除優先、懸空符號修補如 `"1500+"` -> 1500、除以零防禦返回 null）。支援「記入紙帶」動態累加清單，免稅門檻即時反饋進度條，且純由 React in-memory 狀態管理，關閉或刷新頁面自動洗掉，乾淨無痕。
   - **信用卡海外 1.5% 淨利差精算 ✕ 雙卡拆單神策**：
     - 上限正規化：將現金回饋上限換算為最大可刷額度 $MaxSpend = Limit / (Rate\%)$。
     - 雙卡最佳拆單：若消費超出頂格卡上限，主動試算「卡 A 刷至滿額上限 NT$X + 卡 B 接力無上限刷剩餘 NT$Y」的拆單組合技。
     - 摩擦力守衛：次卡消費需 $\ge 100$ TWD 且拆單額外利差需 $\ge 30$ TWD 才主動推薦拆單，兼顧省錢與收銀台操作體驗。
     - 一鍵轉入行程記帳：直接銜接既有 `ExpenseDialog` 寫入後端。

---

### 里程碑五：跨模組無縫打通 ✕ 幽靈快取與重複 Key 系統性除錯 (Event Mesh & Systematic Debugging)
1. **AI 旅伴直通行程匯入器 (ChatWidget ➔ AppShell ➔ TripDialogs)**：
   - AI 對話中產生結構化行程時，卡片提供「傳送至行程匯入器」按鈕，發送 `CustomEvent("ai-import-itinerary")` 與 `CustomEvent("navigate-to-trips")`。
   - 修復 `app-shell.tsx` 中 `handleNavigateToTrips` 誤設為非存在標籤 `"trips"` 導致全分頁隱藏的 Bug，精準導向 `"itinerary"`。
   - `TripDialogs.tsx` 掛載事件監聽器，透過 `tryParseItinerary` 驗收 JSON 並開啟 `CreateTripModal`，徹底打通全鏈路閉環。
2. **Turbopack 幽靈 Service Worker 快取與重複 Key 根除**：
   - 深入剖析開發模式下 Turbopack 拋出 `TripList.tsx module factory is not available` 的根本原因：生產環境遺留的 Service Worker 透過 `CacheFirst` 吐出包含舊版依賴的 JS Chunk。確立硬性重新整理（Ctrl+Shift+R）與 DevTools 取消註冊之排查 SOP。
   - 抓出 `defaultTaxRules.ts` 中重複註冊的越南條目 (`countryCode: "VN"`)，完成資料層合併，並在 `GlobalTaxActuary.tsx` 導入 `Map` 鍵值去重防線，消滅 React 重複 Key 警告。

---

### 里程碑六：全球化示範行程範本匯入 ✕ 5日多幣別對齊 ✕ 地理編碼關鍵字防線 (Global Import Templates & 5-Day Currency Alignment)
1. **業務痛點與多國擴展需求**：
   - 原 `AiImportTripWizard.tsx` 僅內建短天數單一範本，且範本文字多限於亞洲單一貨幣情境。使用者需要快速體驗歐洲與北美跨洲際長程規劃，同時測試貨幣對齊（EUR, USD）與 5 整天完整景點排程。
2. **核心架構升級**：
   - **亞洲、歐洲、美洲三大經典 5 日範本落地**：
     - 🇯🇵 東京 5 天深度慢活（Tokyo, JPY）
     - 🇫🇷 巴黎 5 天藝文漫步（Paris, EUR）
     - 🇺🇸 紐約 5 天都會探險（New York City, USD）
   - **雙語國際化對齊 (Bilingual i18n Guard)**：完整支援繁體中文 (`zh-TW`) 與英文 (`en`) 範本名稱、描述、佔位符與動態提示，杜絕硬編碼字串。
   - **地理編碼歐美母體關鍵字防線 (Geocode Mother Region Keywords Expansion)**：
     - 在後端 `backend/services/geocode_service.py` 擴充 `LOCATION_KEYWORDS`，新增法國 (`FR`: `paris`, `france`, `lyon`, `marseille`, `versailles`, `eiffel`) 與美國 (`US`: `new york`, `nyc`, `manhattan`, `brooklyn`, `united states`, `usa`) 關鍵字。
     - 確保匯入巴黎與紐約行程時，`detect_country_from_keywords` 能精準識別國家代碼與對應主權貨幣（EUR / USD），消滅開源 Photon 地理編碼缺漏 `country` 欄位造成的空間錯位。
   - **Security Sentinel 雙端記憶體沙盒測試守門**：
     - 前端 `ai-import-templates-sentinel.test.ts` 驗證三大範本 5 日結構完整性、景點天數連續性與經緯度格式。
     - 後端 `test_sentinel_global_templates.py` 驗證地理編碼關鍵字解析、貨幣推斷與空間邊界。

---

## 4. 多維度知識提煉 (Multi-Dimensional Synthesis)

### 🟢 Features & Fixes
- **Globalized 5-Day Import Templates**: `AiImportTripWizard.tsx` 內建東京、巴黎、紐約三大跨洲 5 整天完整範本，支援雙語 i18n 切換。
- **Geocode Country & Currency Auto-Inference**: 後端地理編碼關鍵字擴充 FR 與 US，精準對應 EUR 與 USD 主權法幣。
- **GlobalTaxActuary 落地**: 工具箱全新掛載全球免稅精算器，支援 18 國法規、自訂國別、匯率原地編輯與一鍵轉入記帳。
- **In-Memory Calculator & Tally Tape**: 大鍵盤四則運算、算式紙帶清單與門檻進度條，無痕記憶體管理。
- **Smart Double-Card Split Strategy**: 1.5% 海外手續費折抵、上限正規化與雙卡接力拆單神策，帶有 30 元利差摩擦力防護。
- **Cross-Module Itinerary Import Event Mesh**: ChatWidget 對話結果一鍵無縫直通 TripDialogs 行程匯入精靈。
- **AppShell Navigation Fix**: 修復 `handleNavigateToTrips` 導向正確的 `"itinerary"` 分頁，消滅全屏隱藏隱患。
- **React Duplicate Key Elimination**: 合併 `defaultTaxRules.ts` 中的重複越南條目，並在元件層實裝 `Map` 去重防線。
- **iOS Standalone Viewport Golden Fix**: 回滾 `statusBarStyle` 為 `"default"`，消除 PWA 狀態列重疊上移問題。
- **Splash Preload Pipeline**: 注入原生 Preload 標籤，達成首幀 60FPS 絲滑展開。
- **Atomic Recovery Reset**: `landing-page.tsx` 實裝 Zustand 快取原子清理與 5 秒過渡靜音鎖。

### 🏛️ Architecture Decisions
- **全球示範範本 5 日完整閉環與雙語國際化對齊 (AD-083)**: 範本必須提供滿 5 天、每天至少 3 個具備正確經緯度的真實景點結構，並嚴格透過 `locale` 分流雙語字串，保障示範資料隨選即用。
- **地理編碼關鍵字歐美擴充與貨幣自動推斷防線 (AD-084)**: 針對 Photon 不帶 `country` 欄位的缺陷，後端必須持續維護並擴充 `LOCATION_KEYWORDS` 字典，使全球主流目的地（法、美、日、台等）能自動推導 ISO 國碼與正確記帳法定貨幣。
- **Zero-Eval 四則運算 AST 詞法解析求值器 (AD-079)**: 購物計算機嚴禁使用 `eval()` 或 `new Function()`。透過 Tokenizer 採兩階段掃描（先乘除後加減），支援懸空符號修補與除以零安全防禦，杜絕 XSS。
- **信用卡現金回饋上限正規化與最大可刷額度推導 (AD-080)**: 台灣信用卡回饋上限為回饋金上限，引擎必須以 $MaxSpend = Limit / (Rate\%)$ 換算最大可刷額度，並精確扣除 1.5% 手續費結算真實淨利差。
- **雙卡最佳拆單神策與收銀台摩擦力防衛 (AD-081)**: 超出頂級神卡上限時，以費率最高滿額卡 A 搭配次佳無上限卡 B；次卡 $\ge 100$ TWD 且額外利差 $\ge 30$ TWD 才主動輸出拆單神策，避免瑣碎操作。
- **跨視圖行程研究結構化直通匯入架構 (AD-082)**: 透過雙向 CustomEvent 事件總線直通 `app-shell.tsx`，由 `TripDialogs.tsx` 安全解析喚醒建立模態框，達成對話至建程零摩擦閉環。
- **iOS Standalone Status Bar 模式與視口原點黃金律 (AD-075)**: WebKit PWA 必須維持 `"default"` 保留獨立系統狀態列空間，使視口座標原點 (0,0) 嚴格對齊狀態列下緣，保障整體佈局幾何穩定。
- **原生最高優先級紋理預載入與解碼停頓根治 (AD-076)**: 針對開機首幀涉及大型向量遮罩之資產，必須在 HTML `<head>` 靜態配置 `<link rel="preload" as="image" fetchPriority="high">`，保證進場動畫 60FPS 絲滑展開。
- **帳號引繼原子四清與 5 秒過渡靜音鎖架構 (AD-077)**: 跨使用者身分切換時同步抹除 Zustand 本機持久化快照，並透過 `sessionStorage` 宣告 5 秒時間窗口鎖，阻斷 SWR 載入期間的誤判警告。

### 🔴 Technical Debt
- **Dependabot #105 待評估**: GitHub 遠端高風險依賴安全性警告待安排專責升級。
- **Dev-Mode Service Worker 自動註銷補丁**: 當前仍依賴開發者在終端遇到舊快取時手動 Hard Refresh；未來可考慮在 `service-worker-register.tsx` 於 dev 模式掛載自動 unregister 與 clear caches。

### 🛡️ Failed Paths
- **Turbopack 開發模式 Service Worker 快取劫持陷阱 (FP-021)**: 在執行過 PWA 生產預覽後回到 `npm run dev`，瀏覽器殘留的 Service Worker 其 `CacheFirst` 會持續吐出快取中的歷史 JS Chunks（如引用已棄用之 `TripList.tsx`），引發 `Module factory is not available` 白屏報錯。教訓：開發環境切換須執行硬性重新整理（Ctrl+Shift+R）或於 DevTools Unregister Service Worker。
- **種子規則國碼重複與 React List Key 碰撞陷阱 (FP-022)**: 在擴充多國免稅規則時，未檢查頂部既有清單而重複追加 `countryCode: "VN"`，導致清單遍歷時產生重複的 `key="VN"` 觸發 React 警告。處方：資料層物理合併去重，表現層元件透過 `new Map()` 進行確定性動態去重，達成雙重免疫。
- **`black-translucent` 沉浸式誤傷版型佈局 (FP-019)**: 嘗試以 `black-translucent` 消除白底，反而觸發 WebKit 沉浸模式將整個 App 向上推移進入系統狀態列下，造成標題與時間電量疊印。教訓：狀態列模式牽動整個根層視口幾何，不可作為局部色彩補丁使用。
- **引繼情境下老使用者 Sample Trip 逆向污染陷阱 (FP-020)**: 在全新設備還原時，若只重設了 `user_uuid`，本地 `sample_trip_seeded` 為空會導致種子守門器將老使用者誤判為新使用者塞入示範行程。教訓：引繼流程必須同時覆蓋新人引導相關的所有本機旗標。

---

## 5. 品質閘門驗證清單 (Quality Gates Checklist)
- [x] **TypeScript**: `npx tsc --noEmit` (0 Errors)
- [x] **ESLint**: `npm run lint` (0 Errors, 0 Warnings)
- [x] **Vitest (Frontend)**: 57 Suites, 406 Tests Passed (100% Green, 含 13 項沙盒精算器測試 + 1 項 AI 範本沙盒測試)
- [x] **Pytest (Backend)**: 122 Tests Passed, 5 Skipped (100% Green, 含 全球地理關鍵字沙盒測試)
- [x] **Account Recovery Sentinel**: `account-recovery-atomic-sentinel.test.tsx` (2/2 Passed)
- [x] **Actuary Engine Sandbox**: `actuary-engine-sandbox.test.ts` (13/13 Passed)
- [x] **Global Template Sentinel**: `ai-import-templates-sentinel.test.ts` (1/1 Passed) & `test_sentinel_global_templates.py` (2/2 Passed)
- [x] **Git Cleanliness**: `Working tree clean`，已完全同步至遠端 `origin/main` (`14cfcd3`)

---

## 6. 下一步規劃 (Next Steps)
1. **行程設定面板 (Trip Settings View) 專屬獨立視圖實作**：將行程封面管理、行程基本資料與危險操作收攏於獨立設定視圖，支援平滑滑入滑出動效。
2. **目的地封面照片自動解析管線 (Destination Cover Photo Pipeline)**：建程時依據目的地關鍵字自動匹配優質高解析度封面，提供 0 成本高美感首頁視覺。
3. **雙卡拆單實戰微調**：依據使用者實際反饋，持續擴充常用海外高回饋神卡（如永豐幣倍、聯邦幸福 M 卡、國泰 CUBE 等）的標籤備忘。
4. **Dependabot #105 安全性依賴升級評估**。

