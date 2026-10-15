# 📅 Daily Report - 2026-10-16 (FlightCard High-Font-Scale Adaptive Layout, WebKit Pill Shield & Sentinel Adversarial Verification)

> **系統狀態**：🟢 Production Deployed & Synced (`5de076d`), 0 TypeScript Errors, 0 ESLint Warnings, 100% Tests Green (Frontend 25/25 Tests Passing across active suites, 11 new Sentinel tests; Backend 157/157 Tests Passing, 5 skipped), Working Tree Clean, GitHub main branch synced.  
> **今日關鍵提交串列 (Full Day Commit Stream)**：
> - [`5de076d`](https://github.com/tyrantpiper/tabiji/commit/5de076d) `fix(info): adaptive layout tuning for flight card under high font scale` (2026-10-16 03:37:01 +0800)
> - [`aa9f4b4`](https://github.com/tyrantpiper/tabiji/commit/aa9f4b4) `docs(memory): document microsecond computation time-slicing anti-pattern in failed paths` (2026-10-16 01:42:32 +0800)

---

## 🏆 深度專案復盤：四大工程與架構里程碑 (Four Core Milestones)

本次研發循環針對使用者在個人設定中啟用「清晰 (120%)」與「醒目 (130%)」文字放大時，機票資訊卡片 (`FlightCard.tsx`) 產生的版面擠壓與文字刺穿問題，完成了全鏈路自適應幾何調諧、WebKit 匿名文字節點保護、Security Sentinel 物理沙盒證偽審查，以及 E2E 資料庫生命週期 ACID 驗證：

---

### 里程碑一：航班卡片高字級 (120%~130%) 自適應幾何重構 ✕ 寬度防刺穿 (Fluid Scaling & Anti-Collision Architecture)

1. **業務挑戰與排版撞軌痛點**：
   - 使用者在設定中將字級放大至 120%~130% 時，前端首幀透過原生腳本向根節點注入 `document.documentElement.style.fontSize = 130%`。由於 Tailwind CSS 大量依賴 `rem` 單位，文字尺寸、內邊距 (`padding`)、間距 (`gap`) 與固定寬度均等比膨脹 30%。
   - 頂部日期列原採用 `grid-cols-[1fr_auto_1fr]`，中央裝飾線為固定 `w-12 sm:w-20 px-4`（在 130% 下膨脹至 >100px）。未設定日期文字「尚未設定日期」（6 個中文字）在 `text-lg` (膨脹至 ~23.4px) 且帶有 `whitespace-nowrap overflow-visible` 的情況下，左右兩側文字直接向中央溢出刺穿，與中央藍色圓點及虛線重疊碰撞。
   - 級距倒掛異常：手機端原硬編碼為 `text-lg`，平板端反而為 `sm:text-base`，導致最狹窄的手機螢幕上文字反而比大螢幕更大。
   - 機場代碼 `text-4xl`、飛行線軌道 `w-16` 與右側抵達時間 `00:00` 爭搶寬度，右側時鐘圖示貼邊。
   - 卡片手機端內距原為 `p-8`，膨脹至 83.2px，將 375px/390px 窄螢幕內容壓縮至僅剩 266px。
2. **大師級自適應幾何解決方案**：
   - **外邊距空間釋放**：上半部由 `p-8 pt-10` 調諧為 `p-5 sm:p-8 pt-6 sm:pt-10`，下半部改為 `p-5 sm:p-8 space-y-6 sm:space-y-8`，為內容即刻釋放 24px+ 橫向寬度。
   - **平滑字級階梯與防溢**：日期字級修正為平滑遞增 `text-sm sm:text-base md:text-lg font-black`，消除級距倒掛；移除 `overflow-visible`，全面宣告 `truncate min-w-0`，未設定時啟用精簡字串「未設定」(`no_date_short`)。
   - **確定性響應軌道**：中央裝飾線改為確定性響應軌道 `w-8 sm:w-14`，消除 Grid cell 誤用 `flex-1` 無效的陷阱。
   - **機場與飛行軌道**：機場代碼微調為 `text-3xl sm:text-5xl md:text-6xl font-black`，飛行軌道調整為 `w-12 sm:w-20`，右側時間欄補齊 `pr-0.5 sm:pr-1` 安全呼吸邊距。

---

### 里程碑二：WebKit 匿名文字節點隔離 ✕ 指示膠囊 `shrink-0` 硬體防衛 (WebKit Text-Node Isolation & Pill Shrink Guard)

1. **WebKit 匿名盒壓縮同級標籤缺陷**：
   - 忠實落實專案記憶 [`memory.md#Decision-35`](file:///d:/Project/Tabidachi/travel-pwa/.agents/memory.md)。在 Flex 容器中，裸露文字搭配 `truncate` 會在 WebKit 引擎下產生匿名文字方塊（Anonymous Block Box），在 390px 窄螢幕下壓縮同級標籤。
   - 在航空公司列 [`FlightCard.tsx:299-303`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/views/info/FlightCard.tsx#L299-L303)，若僅對文字套用 `truncate` 而未對左側膠囊標記加上 `shrink-0`，在 130% 字級與 390px WebKit（iOS Safari）環境下，文字溢出計算會直接將藍色膠囊寬度壓扁至 0px。
2. **防禦架構與輸入框本質寬度控制**：
   - 航空公司列將文字封裝於獨立 `<span className="truncate">`，並在左側藍色膠囊標籤顯式宣告 `shrink-0`（`<span className="w-1.5 h-5 sm:h-6 bg-blue-500 rounded-full shrink-0" />`），徹底杜絕壓扁瑕疵。
   - 編輯態 `<input type="date">` 注入 `min-w-0 w-full`，抵禦 iOS Safari 原生日期選擇器 Shadow DOM 最小本質寬度（約 120px~130px）撐破 `1fr` 格線的隱患。
   - 檢視態與編輯態輸入框同步宣告 `text-3xl sm:text-5xl md:text-6xl h-10 sm:h-14`，徹底消除模式切換時的 CLS 佈局跳動。

---

### 里程碑三：Security Sentinel 物理沙盒審查 ✕ TDD Red-Green 閉環 (Adversarial Sentinel Sandbox & TDD Loop)

1. **Maker-Checker 物理子代理人隔離審查**：
   - 遵守 L0 憲法，調用 `runner.py` 調度 3 組獨立背景 OS 進程（`agy.exe --sandbox`）對剪貼簿 API、陣列狀態變異、高字級呈現 DoS 進行證偽審查。
   - 審查結果判定：3/3 全數 DISMISSED（確認無 DOM XSS、無原型鏈污染，排版擠壓判定為 CSS 響應式極限邊界而非安全漏洞）。
   - 原子化更新資安台帳 [`docs/security/security-coverage-ledger.json`](file:///d:/Project/Tabidachi/travel-pwa/docs/security/security-coverage-ledger.json) 與產出報告 [`docs/security/reports/security_sentinel_report_2026-10-16_flight_card_adaptive.md`](file:///d:/Project/Tabidachi/travel-pwa/docs/security/reports/security_sentinel_report_2026-10-16_flight_card_adaptive.md)。
2. **TDD 嚴格紅綠循環**：
   - 建立專屬自動化測試 [`frontend/__tests__/flight-card-adaptive-layout.test.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/__tests__/flight-card-adaptive-layout.test.tsx)。
   - **Red 階段**：現行代碼執行測試確認精準失敗（`9 failed | 2 passed`），成功捕捉到 9 項佈局缺陷與倒掛異常。
   - **Green 階段**：實作完成後測試由 Red 轉為 100% Green（`11 passed (11)`），數學幾何證明在 375px 手機與 130% 字級下留有 66.1px 充足安全淨空。

---

### 里程碑四：全鏈路 E2E 與 ACID 交易隔離驗收 (E2E Lifecycle & PostgreSQL Row-Level Lock)

1. **完整生命週期全鏈路跑通**：
   - 前端 UI 受控變更：[`FlightCard.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/views/info/FlightCard.tsx) 觸發 `onChange`，由 [`info-view.tsx:185-191`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/views/info-view.tsx#L185-L191) 進行不可變陣列變更。
   - 傳輸層標準化 PATCH：[`frontend/lib/api.ts:482-493`](file:///d:/Project/Tabidachi/travel-pwa/frontend/lib/api.ts#L482-L493) 攜帶 `X-User-ID` 標頭調用同源端點 `/api/trips/${tripId}/info`。
   - 後端 Pydantic 契約守門：[`backend/models/base.py:400-405`](file:///d:/Project/Tabidachi/travel-pwa/backend/models/base.py#L400-L405) 之 `UpdateInfoRequest` 宣告強型別。
   - 身分驗證與資料庫持久化：[`backend/routers/trips.py:1275-1334`](file:///d:/Project/Tabidachi/travel-pwa/backend/routers/trips.py#L1275-L1334) 驗證 `trip_members` 後執行單次原子化 SQL 更新。
2. **ACID 與並發安全**：
   - 單一行更新 (`UPDATE itineraries WHERE id = :id`) 在 PostgreSQL 中直接獲取該 Row 的排他鎖，不涉及跨資料表多重資源循環申請，物理上完全不可能發生死鎖 (Deadlock Impossible)。
   - `PATCH /api/trips/{trip_id}/info` 操作本質為狀態置換，重複發送相同的 `flight_info` 酬載 $N$ 次保持嚴格等價（$f(f(x)) = f(x)$），具備 100% 冪等性。

---

## 🏛️ 架構決策與模式提煉 (Architectural Synthesis)

### 1. 🏛️ Architecture Decisions (架構決策)
- **CSS Grid auto 軌道之確定性響應寬度原則 (Deterministic Grid Auto Tracks)**: 在 `grid-cols-[1fr_auto_1fr]` 中，`auto` 欄位禁止宣告無效的 `flex-1`，必須以明確的響應式幾何尺度（如 `w-8 sm:w-14`）接管，留出精準的兩側空間。
- **擬物化機票卡流式微創調諧準則 (Fluid Micro-Tuning over Layout Stack Degradation)**: 在卡片式擬物佈局中，維持橫向對稱比重優於輕易退化為垂直堆疊；透過外距收縮（`p-5 sm:p-8`）、字級階梯修正與截斷保護，兼顧登機證美感與超大字級可存取性。
- **編輯與檢視態字級原子一致性 (Edit/View State Typographic Symmetry)**: 檢視態與編輯態輸入框必須使用相同的字級階梯（`text-3xl sm:text-5xl md:text-6xl`）與 `h-10 sm:h-14`，根除模式切換時的 CLS 佈局跳動。

### 2. 🛡️ Failed Paths (踩坑與排除路徑)
- **CSS Grid auto 欄位子節點誤用 `flex-1` 反模式**: 試圖在 CSS Grid 的 `auto` 欄位子節點使用 `flex-1` 實現自動彈性收縮。CSS Grid 規範中 `flex-1` 僅在 `display: flex` 父容器內生效，在 Grid `auto` 軌道中是無效宣告，無法阻止 140px 文字與中央裝飾線擠壓。
- **Framer Motion 內使用 window.innerWidth 視窗偵測動效位移**: 試圖在 Framer Motion `animate={{ x: ... }}` 中使用 `window.innerWidth` 動態決定飛機位移。這會引發 SSR 水合首幀與客戶端不匹配的 Hydration Mismatch 警告，必須使用靜態幾何標稱位移 `x: [-18, 18]`。

### 3. 🔴 Technical Debt (技術債務追蹤)
- **多語系 `no_date_short` 擴充**: 目前僅補齊 `zh-TW`（未設定）與 `en`（Not set）。未來若擴展日語支援，需在日文字典檔補齊對應精簡詞條。

---

## 🎯 明日與後續行動綱領 (Next Steps)
1. **持續觀測**: 於真實行動設備觀察大字級下的整體使用者閱讀與操作回饋。
2. **卡片拓撲巡檢**: 依循本次驗證模式，巡檢住宿資訊（`HotelCard`）在 130% 字級下的橫向空間餘裕。
