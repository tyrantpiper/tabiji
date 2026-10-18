# 📅 Daily Report - 2026-10-18 (Dock Direction-Aware Transitions, Spatial Index Topology, React 19 Pure Render & Native Parity Intent)

> **系統狀態**：🟢 Production Ready & Synced (`1c2f36f`), 0 TypeScript Errors, 0 ESLint Warnings, 100% Tests Green (Frontend 74 test suites / 490 tests passing; Backend 161 tests passing), Working Tree Clean, GitHub main branch synced.  
> **今日關鍵提交串列 (Full Day Commit Stream)**：
> - [`1c2f36f`](https://github.com/tyrantpiper/tabiji/commit/1c2f36f) `feat(ui,motion): implement direction-aware dock transitions and spatial parity` (2026-10-18 14:14:49 +0800)

---

## 🏆 深度專案復盤：四大工程與動態轉場里程碑 (Four Core Milestones)

本次研發循環全面針對底部 Dock（`BottomNav`）切換四大核心視圖（行程 0 ➔ 資訊 1 ➔ 工具 2 ➔ 個人 3）時的「逆向切換仍然右至左滑入」反直覺痛點展開深入偵錯、對抗性安全審計與架構級重構：

---

### 里程碑一：Dock 事件斷鏈修復 ✕ 純函數相對空間拓撲重構 (Spatial Index Topology & Decoupled Bypass Fix)

1. **使用者痛點與真因溯源**：
   - 使用者在四大 Dock 間切換時：
     - 從左向右切換（如 0 ➔ 1）：頁面自右向左滑入（符合視覺預期）。
     - 從右向左切換（如 3 ➔ 2 或 1 ➔ 0）：**頁面仍然自右向左滑入**，嚴重違背空間直覺。
   - 深度代碼審查確認兩大根因：
     1. **事件斷鏈**：[`app-shell.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/app-shell.tsx) 第 273 行傳入 `<BottomNav onTabChange={setActiveView} />`，直接繞過頂層的 `handleTabChange`，導致 `direction` 狀態自初始值 `+1` 起從未動態更新。
     2. **座標殘留**：即使更新 `direction`，在既有 `<motion.div animate={{ x: direction * 28 }}>` 模型下，非作用中視圖在上一次切換中已被推至 `+28px`；當使用者由右向左切換時，目標視圖從殘留的 `+28px` 動畫至 `0px`，依然呈現右至左滑動。
2. **大師級相對空間拓撲方案 (`frontend/lib/spatial-tab-topology.ts`)**：
   - 徹底拔除易變的歷史 `direction` 狀態，升級為純函數空間拓撲計算：
     $$\Delta X = \begin{cases} 0 & \text{if } \text{target} = \text{active} \lor \text{intent} = \text{'instant'} \lor \text{isReducedMotion} \\ +28\text{px} & \text{if } \text{targetIdx} > \text{currentIdx} \\ -28\text{px} & \text{if } \text{targetIdx} < \text{currentIdx} \end{cases}$$
   - **數學自洽性**：當使用者在 `profile` (3) 點擊 `itinerary` (0) 時，`0 < 3` 靜態停靠座標為 `-28px`，動畫自 `-28px` 平滑進入 `0px`，**確定性實現由左向右滑入**，徹底消除歷史方向漂移。

---

### 里程碑二：未預熱組件首度掛載動態補償 ✕ 轉場意圖原子化防死鎖 (Cold Mount Initial Injection & Intent Scoping)

1. **Preheat 競態與掛載動態斷崖**：
   - `app-shell.tsx` 透過 `shouldPreheat` 實施 2000ms 延遲背景預熱。
   - 若直接在外層宣告 `initial={false}`，當使用者在 App 冷啟動前 2 秒內快速點擊 Dock 時，目標視圖為生命週期首次掛載（First Mount），Framer Motion 會強制抑制進場彈簧動畫，導致頁面瞬間以 0ms 彈出（Pop-in）。
2. **動態 Initial 座標注入方案**：
   - 在各視圖外層宣告：
     `initial={{ opacity: 0.7, x: calculateTabOffset(tab, prevTab, transitionIntent, !!isReducedMotion) }}`
   - 未預熱時初次掛載瞬間，組件即精確依據來源與目標相對方位取得起始位移，確保冷啟動手動點擊依然具備 100% 絲滑進場動效。
3. **意圖原子化分流 (Native Parity Intent)**：
   - 手動點擊 Dock：明確宣告 `intent: 'dock'`（`±28px` 彈簧微滑入）。
   - 外部 Deep Link / 推播通知 / 冷啟動首屏：明確宣告 `intent: 'instant'`（`x: 0` 瞬移），避免非預期的視差跳動，且單次派發不殘留狀態，杜絕「外部跳轉後手動點擊無法滑動」的死鎖缺陷。

---

### 里程碑三：React 19 與 React Compiler 渲染純函數規範重構 (React 19 Pure Render Invariance)

1. **編譯器違規警報診斷 (`react-hooks/refs`)**：
   - 在初步重構中，為避免額外重繪使用了 `const prevTabRef = useRef(activeView)`，並直接在 JSX `<motion.div initial={{ x: calculateTabOffset(..., prevTabRef.current, ...) }}>` 中讀取 `prevTabRef.current`。
   - React 19 與 React Compiler（Babel Plugin React Compiler）嚴格約束組件評估（Render Phase）的純函數性，檢測到 Render 期間讀取 Ref，拋出 4 項 `react-hooks/refs` 違規錯誤。
2. **微創升級至純量響應式狀態**：
   - 拔除 `useRef`，升級為正規的 React State `prevTab`。
   - 在 `handleTabChange` 中以函數型狀態更新完成原子化配對：
     ```tsx
     const handleTabChange = useCallback((nextTab: string, intent: TabTransitionIntent = "dock") => {
         setActiveView((current) => {
             if (nextTab === current) return current
             setPrevTab(current)
             setTransitionIntent(intent)
             return nextTab
         })
     }, [])
     ```
   - 徹底符合 React 19 渲染純函數規範，ESLint 檢查 0 錯誤、0 警告。

---

### 里程碑四：Security Sentinel 對抗式物理沙盒驗證 ✕ In-Memory PoC 4/4 綠燈

1. **多輪對抗驗證 (`runner.py`)**：
   - 透過 `agy.exe -p --sandbox` 調度 4 組獨立子代理人進行物理對抗審查：
     - 證實 1：`BottomNav` 第 273 行直接傳遞 `setActiveView` 確實繞過方向狀態機（Confirmed）。
     - 證實 2：`initial={false}` 在冷啟動前 2 秒未預熱點擊時會閹割進場動態（Confirmed）。
     - 證實 3：未區隔單次轉場意圖會引發狀態閂鎖死鎖（Confirmed）。
     - 排除 1：`tabidachi-tab-changed` 自訂事件受 `if (isActive)` 分流阻斷，無重入迴圈風險（Dismissed）。
2. **In-Memory PoC 沙盒測試套件 (`frontend/__tests__/dock-transition-sentinel.test.ts`)**：
   - 撰寫 4 項核心單元驗證（斷鏈證偽、幾何拓撲、意圖死鎖防衛、Reduced Motion 減敏），Vitest 實測 4/4 綠燈（耗時 592ms，零外部網路依賴）。
   - 審計報告落地至 [`docs/security/reports/security_sentinel_report_2026-10-18_dock_transitions.md`](file:///d:/Project/tabiji/travel-pwa/docs/security/reports/security_sentinel_report_2026-10-18_dock_transitions.md)，總帳本原子化更新至 [`docs/security/security-coverage-ledger.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/security-coverage-ledger.json)。

---

## 🏛️ 架構決策與模式提煉 (Architectural Synthesis)

### 1. 🏛️ Architecture Decisions (架構決策)
- **相對空間索引拓撲純函數原則 (AD-115)**：切換分頁的進場與停靠方位，嚴禁依賴易變狀態（mutable historical state）紀錄的 `direction`（`1 | -1`）。規範全面升級為無狀態純函數 `calculateTabOffset(targetTab, currentActiveTab, intent, isReducedMotion)`，由物理索引差值 `targetIdx > currentIdx ? +28px : -28px` 即時映射。任何分頁的待命位置由當前作用中分頁絕對鎖定，達成 100% 空間幾何自洽與零歷史狀態漂移。
- **轉場意圖原子化分流與原生分頁規範對齊 (AD-116)**：嚴格區隔使用者主動行為與系統程式調度。手動點擊 Dock 導航列派發 `intent: 'dock'`，執行 `±28px` 彈簧微動效；外部 Deep Link、推播跳轉、首屏冷啟動水合與內部事件派發 `intent: 'instant'`，強制作業為 `x: 0` 瞬移，避免非預期的視差干擾。轉場意圖在每次調度時以 Action 引數原子化傳遞，嚴禁將 `isInstant` 作為持久易死鎖的單向 React 布林狀態，守護狀態機冪等性。
- **React 19 / React Compiler 渲染純函數規範 (AD-117)**：React 19 與 React Compiler（Babel Plugin React Compiler）嚴格約束組件評估（Render Phase）的純函數性。嚴禁在 JSX 屬性計算中直接讀取 `useRef.current`（如 `calculateTabOffset(..., prevTabRef.current, ...)`)，否則會觸發 `react-hooks/refs` 違規編譯報錯。所有決定 JSX 渲染輸出與 Initial 動畫座標的變量，必須升級為正規的 React State（`prevTab`），並在 `handleTabChange` 中透過函式型狀態更新（`setActiveView((current) => { setPrevTab(current); return nextTab })`）完成原子化配對。
- **動態 Initial 座標注入消除冷啟動未預熱瞬跳 (AD-118)**：當非核心視圖依賴 `shouldPreheat` 延遲預熱時，若外層 `<motion.div>` 盲目宣告 `initial={false}`，冷啟動前 2 秒內使用者的初次點擊將因生命週期首度掛載而直接跳過進場動畫，產生 0ms 突兀瞬彈（Pop-in）。架構規範必須宣告動態 `initial={{ opacity: 0.7, x: calculateTabOffset(...) }}`，使無論組件是否已預熱，首次登場皆精準自 `±28px` 滑入。

### 2. 🛡️ Failed Paths (踩過的坑與失敗路徑)
- **BottomNav 直接傳遞 `setActiveView` 繞過協調器斷鏈陷阱 (FP-039)**：在 `app-shell.tsx` 中定義了 `handleTabChange`，但傳入 `<BottomNav onTabChange={setActiveView} />`。使用者點擊導航欄直接修改視圖狀態，徹底繞過方向計算與歷史記錄，導致 `direction` 永久凍結在初始值 `+1`。教訓：底層導航控制元件的事件回呼必須精確綁定至包含業務與拓撲計算的統一協調器。
- **Framer Motion 舊座標殘留導致逆向切換同向滑動陷阱 (FP-040)**：在非作用中視圖上宣告 `animate={{ x: direction * 28 }}`，當分頁從 0 切換至 1 時，所有非作用中分頁被推至 `+28px`。當使用者由 1 切換回 0 時，雖然 `direction` 變為 `-1`，但 Tab 0 在 DOM 上的當前位移仍停在 `+28px`，Framer Motion 從 `+28px` 動畫至 `0px`，依然呈現右至左滑動。教訓：不能依賴全域單一 `direction` 控制所有分頁，必須以相對空間拓撲純函數決定各分頁的獨立絕對位置。
- **React 19 JSX 內讀取 Ref 觸發 `react-hooks/refs` 致命編譯報錯 (FP-041)**：為了避免額外狀態更新，在組件內維護 `prevTabRef = useRef(activeView)` 並在 `<motion.div initial={{ x: calculateTabOffset(..., prevTabRef.current, ...) }}>` 中傳入。React Compiler 檢測到 Render 期間讀取 Ref，判定為可能引發不可預測渲染的非純操作並報錯。教訓：所有參與 JSX 結構與屬性計算的變數，必須是 React State 或 Props，不可走 Ref 旁路。

### 3. 🔴 Technical Debt (技術債與後續追蹤)
- **四大主視圖雙向交叉滑動 (Cross-Slide Entrance & Exit)**：目前為了堅守 Zero-Remount 與 WebGL 地圖極致省電，退場視圖採用立即 `hidden` 凍結渲染；未來若硬體效能充裕，可評估微幅放寬 200ms 的退場動畫（Cross-Fade Slide Out），在不銷毀組件前提下達成更極致的電影級連續感。

---

## 🔮 下一步計畫 (Next Steps)
1. 持續推進 Universal Travel Interoperability Hub（多平台行事曆 ICS/Google Calendar 與航線匯出規格）。
2. 在真機 Standalone PWA 模式下持續監測高頻滑動下的 120Hz ProMotion 幀率與觸控防震穩定性。
