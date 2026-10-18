# 📅 Daily Report - 2026-10-18 (Dock Direction-Aware Motion & Neural Seam Invariant Defense System)

> **系統狀態**：🟢 Production Ready & Synced (`f08d2bc`), 0 TypeScript Errors, 0 ESLint Warnings, 100% Tests Green (Frontend 74 test suites / 490 tests passing; Backend 167 tests passing), Working Tree Clean, GitHub main branch synced.  
> **今日關鍵提交串列 (Full Day Commit Stream)**：
> - [`1c2f36f`](https://github.com/tyrantpiper/tabiji/commit/1c2f36f) `feat(ui,motion): implement direction-aware dock transitions and spatial parity` (2026-10-18 14:14:49 +0800)
> - [`25c7e0b`](https://github.com/tyrantpiper/tabiji/commit/25c7e0b) `docs(daily-report,memory): consolidate 2026-10-18 daily report and append section 32 decisions` (2026-10-18 14:23:04 +0800)
> - [`883858b`](https://github.com/tyrantpiper/tabiji/commit/883858b) `feat(testing,arch): implement neural seam topology matrix and tri-layer complication defense` (2026-10-18 16:54:22 +0800)
> - [`f08d2bc`](https://github.com/tyrantpiper/tabiji/commit/f08d2bc) `docs(memory): consolidate section 33 neural seam decisions and container keepalive invariants` (2026-10-18 16:55:04 +0800)

---

## 🏆 深度專案復盤：八大工程與架構里程碑 (Eight Core Milestones)

今日研發循環完成了兩大史詩級架構攻堅：
1. **空間感知導航拓撲與 React 19 純粹渲染重構**（根治底欄逆向切換同向滑動反直覺問題）。
2. **全域神經縫隙拓撲矩陣 ✕ 三層手術後遺症微退化感測體系**（落實「程式碼無錯誤不代表無退化，如同手術有後遺症」的臨床級全棧架構防衛網）。

---

### 里程碑一：Dock 事件斷鏈修復 ✕ 純函數相對空間拓撲重構 (Spatial Index Topology & Decoupled Bypass Fix)

1. **使用者痛點與真因溯源**：
   - 使用者在四大 Dock 間切換時：從左向右切換（0 ➔ 1）自右向左滑入；**從右向左切換（3 ➔ 2 或 1 ➔ 0）仍然自右向左滑入**，嚴重違背空間直覺。
   - 深度代碼審查確認兩大根因：
     1. **事件斷鏈**：[`app-shell.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/app-shell.tsx) 第 273 行傳入 `<BottomNav onTabChange={setActiveView} />`，直接繞過頂層的 `handleTabChange`，導致 `direction` 狀態自初始值 `+1` 起從未動態更新。
     2. **座標殘留**：即使更新 `direction`，在既有 `<motion.div animate={{ x: direction * 28 }}>` 模型下，非作用中視圖在上一次切換中已被推至 `+28px`；當使用者由右向左切換時，目標視圖從殘留的 `+28px` 動畫至 `0px`，依然呈現右至左滑動。
2. **大師級相對空間拓撲方案 (`frontend/lib/spatial-tab-topology.ts`)**：
   - 徹底拔除易變的歷史 `direction` 狀態，升級為純函數空間拓撲計算：
     $$\Delta X = \begin{cases} 0 & \text{if } \text{target} = \text{active} \lor \text{intent} = \text{'instant'} \lor \text{isReducedMotion} \\ +28\text{px} & \text{if } \text{targetIdx} > \text{currentIdx} \\ -28\text{px} & \text{if } \text{targetIdx} < \text{currentIdx} \end{cases}$$
   - **數學自洽性**：當使用者在 `profile` (3) 點擊 `itinerary` (0) 時，`0 < 3` 靜態停靠座標為 `-28px`，動畫自 `-28px` 平滑進入 `0px`，確定性實現由左向右滑入。

---

### 里程碑二：未預熱組件首度掛載動態補償 ✕ 轉場意圖原子化防死鎖 (Cold Mount Initial Injection & Intent Scoping)

1. **Preheat 競態與掛載動態斷崖**：
   - `app-shell.tsx` 透過 `shouldPreheat` 實施 2000ms 延遲背景預熱。若直接在外層宣告 `initial={false}`，當使用者在 App 冷啟動前 2 秒內快速點擊 Dock 時，目標視圖為生命週期首次掛載（First Mount），Framer Motion 會強制抑制進場彈簧動畫，導致頁面瞬間以 0ms 彈出（Pop-in）。
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
   - 初步重構中使用 `const prevTabRef = useRef(activeView)` 並在 JSX `<motion.div initial={{ x: calculateTabOffset(..., prevTabRef.current, ...) }}>` 中讀取 `prevTabRef.current`，觸發 React Compiler 4 項 `react-hooks/refs` 違規編譯報錯。
2. **升級至純量響應式狀態**：
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
   - 透過 `agy.exe -p --sandbox` 調度 4 組獨立子代理人進行物理對抗審查，確認 BottomNav 繞過處理器、冷啟動動態閹割與意圖死鎖三大漏洞實證成立。
2. **In-Memory PoC 沙盒測試套件 (`frontend/__tests__/dock-transition-sentinel.test.ts`)**：
   - 撰寫 4 項核心單元驗證，Vitest 實測 4/4 綠燈（耗時 592ms，零外部網路依賴）。
   - 審計報告落地至 [`docs/security/reports/security_sentinel_report_2026-10-18_dock_transitions.md`](file:///d:/Project/tabiji/travel-pwa/docs/security/reports/security_sentinel_report_2026-10-18_dock_transitions.md)。

---

### 里程碑五：全域神經縫隙解剖大冊 ✕ 6 大神經叢全覆蓋 (Neural Seam Topology Matrix Specification)

1. **全專案目錄檔案解剖清冊**：
   - 系統性盤點全專案每一資料夾與關鍵檔案，產出大師級規格書：[`docs/specs/core-architecture/neural-seam-topology-matrix.md`](file:///d:/Project/tabiji/travel-pwa/docs/specs/core-architecture/neural-seam-topology-matrix.md)。
   - 確立 6 大神經叢架構：
     1. **感官與運動神經叢 (Sensory & Motion)**: `frontend/components/views/`, `bottom-nav.tsx`, `spatial-tab-topology.ts`
     2. **本機存儲與快取神經叢 (Storage & Cache)**: `idb-storage.ts`, `tripStore.ts`, `sw.ts`
     3. **地理運算與畫布神經叢 (Geospatial & Canvas)**: `day-map.tsx`, `MapControlCapsule.tsx`, `geo-multi-day.ts`
     4. **智能推理與即時串流神經叢 (AI & Stream)**: `chat-widget.tsx`, `sse-parser.ts`, `backend/routers/ai.py`
     5. **業務精算與生命週期神經叢 (Business Logic)**: `GlobalTaxActuary.tsx`, `trips.py`, `capsules.py`
     6. **邊緣網關與基礎設施神經叢 (Infra & Edge)**: `edge-shield/worker.js`, `main.py`, `Dockerfile`
2. **規格中樞註冊**：
   - 更新 [`docs/specs/README.md`](file:///d:/Project/tabiji/travel-pwa/docs/specs/README.md)，建立 `0. 🏛️ 核心架構與神經拓撲 (core-architecture/)` 導航矩陣。

---

### 里程碑六：三層神經微退化感測套件 ✕ 10 大手術脆弱縫隙不變量實裝 (Tri-Layer Invariant Sensors)

1. **前端神經不變量測試套件 (`frontend/__tests__/neural-seams/seam-invariants.test.ts`)**：
   - 覆蓋 SEAM-01 (導航拓撲)、SEAM-02 (渲染純粹)、SEAM-03 (快照持久)、SEAM-04 (GPU 隔離)、SEAM-07 (數學精算 Zero-Eval AST)。
   - 實測：11/11 測試全部綠燈（耗時 643ms）。
2. **後端神經不變量測試套件 (`backend/tests/test_neural_seams_invariants.py`)**：
   - 覆蓋 SEAM-05 (改期天數序號保持)、SEAM-06 (伺服器 UTC 時區原子性)、SEAM-08 (膠囊 BOLA 伺服端實體脫敏)、SEAM-09 (容器 Keep-Alive 階層防線)。
   - 實測：4/4 測試全部綠燈（耗時 0.05s）。
3. **即時臨床診斷書輸出**：
   - 自動生成 [`docs/security/reports/latest_neural_complication_report.md`](file:///d:/Project/tabiji/travel-pwa/docs/security/reports/latest_neural_complication_report.md)，輸出「HEALTHY (0 Sequelae)」，提供即時臨床後遺症處方。

---

### 里程碑七：基礎設施 Gunicorn/Uvicorn 65s Keep-Alive 容器漏洞封堵 (Container Keep-Alive Hardening)

1. **對抗審查捕獲漏洞 (Sentinel Finding)**：
   - Security Sentinel 發現：雖然 `backend/main.py` 已配置 65s，但生產環境 [`backend/Dockerfile`](file:///d:/Project/tabiji/travel-pwa/backend/Dockerfile) 使用 Gunicorn 未帶 `--keep-alive` 參數，退回 2 秒預設值，高併發下會提早斷開 TCP 連線誘發反向代理拋出 `ECONNRESET`。
2. **實體熱修復與雙容器對齊**：
   - `backend/Dockerfile`: 注入 `--keep-alive 65`。
   - `backend/Dockerfile.prod`: 注入 `--timeout-keep-alive 65`。
   - 透過 `backend/tests/test_neural_seams_sentinel.py` 2/2 通過驗證。
   - 安全總帳本 [`docs/security/security-coverage-ledger.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/security-coverage-ledger.json) 擴充至 93 項目標（100% 覆蓋）。

---

### 里程碑八：確定性測試調度器 ✕ Windows CP950 防護與工作流深度串接

1. **確定性測試調度器 (`scripts/neural_seam_harness.py`)**：
   - 解決 Windows PowerShell `$LASTEXITCODE` 遇失敗提前殺死進程導致診斷書無法合成的痛點。
   - 在記憶體中安全接管 Vitest 與 Pytest，無論成功失敗均保證產出結構化臨床診斷書。
   - 內建 Windows CP950 `reconfigure(encoding='utf-8')` 防護，杜絕 Emoji 引發 `UnicodeEncodeError`。
   - 內建 5 份受保護研究檔案（`docs/research/*`）物理排除防線。
2. **工作流全面集成**：
   - [`.agents/workflows/test.md`](file:///d:/Project/tabiji/travel-pwa/.agents/workflows/test.md): 支援 `Mode 4: /test --seam`。
   - [`.agents/workflows/push.md`](file:///d:/Project/tabiji/travel-pwa/.agents/workflows/push.md): Quality Gate 前置注入 `Step 0.5 神經微退化守門員`。

---

## 🏛️ 架構決策與模式提煉 (Architectural Synthesis)

### 1. 🏛️ Architecture Decisions (架構決策)
- **相對空間索引拓撲純函數原則 (AD-115)**：切換分頁的進場與停靠方位，嚴禁依賴易變狀態紀錄的 `direction`（`1 | -1`）。規範全面升級為無狀態純函數 `calculateTabOffset(targetTab, currentActiveTab, intent, isReducedMotion)`，由物理索引差值即時映射，達成 100% 空間幾何自洽。
- **轉場意圖原子化分流與原生分頁規範對齊 (AD-116)**：手動點擊 Dock 派發 `intent: 'dock'`（`±28px` 彈簧動效）；外部 Deep Link、推播跳轉、首屏冷啟動水合派發 `intent: 'instant'`（`x: 0` 瞬移）。轉場意圖在每次調度時以 Action 引數原子化傳遞，嚴禁作為持久易死鎖的單向 React 布林狀態。
- **React 19 / React Compiler 渲染純函數規範 (AD-117)**：嚴禁在 JSX 屬性計算中直接讀取 `useRef.current`。所有決定 JSX 渲染輸出與 Initial 動畫座標的變量，必須升級為正規的 React State（`prevTab`），並在 `handleTabChange` 中透過函式型狀態更新原子配對。
- **動態 Initial 座標注入消除冷啟動未預熱瞬跳 (AD-118)**：宣告動態 `initial={{ opacity: 0.7, x: calculateTabOffset(...) }}`，使無論組件是否已延遲預熱，首次登場皆精準自 `±28px` 滑入。
- **全域神經縫隙拓撲矩陣架構 (AD-119)**：確立全棧 6 大神經叢解剖全景，將跨模組脆弱介面規格化為 10 大手術縫隙（Surgical Seams）。任何功能異動皆必須通過對應縫隙之核心不變量（Invariant Contracts）微感測，杜絕「0 編譯錯誤但存在隱性功能退化」的偽陽性盲區。
- **雙容器 Keep-Alive 逆向覆蓋防線 (AD-120)**：反向代理（Next.js/Cloudflare 60s 逾時）環境下，後端容器啟動必須嚴格維持 $T_{\text{upstream}} > T_{\text{proxy}}$。在生產環境 `backend/Dockerfile`（Gunicorn `--keep-alive 65`）與 `Dockerfile.prod`（Uvicorn `--timeout-keep-alive 65`）顯式鎖定 65s，徹底消除 Gunicorn 預設 2 秒導致之 Socket Hang Up / `ECONNRESET`。
- **跨棧確定性神經調度器與無損診斷管線 (AD-121)**：在 Windows PowerShell 環境下，透過獨立 Python 調度器 (`scripts/neural_seam_harness.py`) 在記憶體中安全接管測試進程，確保在檢測到 P0/P1 手術後遺症時完整合成「手術後遺症臨床診斷書」，隨後再發起 Exit Code 1 熔斷，兼顧確定性守門與臨床可診斷性。

### 2. 🛡️ Failed Paths (踩過的坑與失敗路徑)
- **BottomNav 直接傳遞 `setActiveView` 繞過協調器斷鏈陷阱 (FP-039)**：底層導航控制元件直接修改狀態，徹底繞過方向計算與歷史記錄，導致 `direction` 永久凍結在初始值 `+1`。教訓：導航事件回呼必須精確綁定至包含業務與拓撲計算的統一協調器。
- **Framer Motion 舊座標殘留導致逆向切換同向滑動陷阱 (FP-040)**：在非作用中視圖上宣告 `animate={{ x: direction * 28 }}` 導致殘留位移，逆向切換時依舊自 `+28px` 動畫至 `0px`。教訓：不能依賴全域單一 `direction`，必須以相對空間拓撲純函數決定各分頁的獨立絕對位置。
- **React 19 JSX 內讀取 Ref 觸發 `react-hooks/refs` 致命編譯報錯 (FP-041)**：在組件內維護 `prevTabRef = useRef(activeView)` 並在 JSX 中讀取，觸發 React Compiler 純粹性報錯。教訓：所有參與 JSX 計算的變數必須是 React State 或 Props。
- **Gunicorn 預設 Keep-Alive 倒掛陷阱 (FP-042)**：以為在 `main.py` 宣告 `timeout_keep_alive=65` 便解決了連線問題，忽略了生產環境 Dockerfile 使用 Gunicorn，其預設 `--keep-alive 2` 會覆蓋 Uvicorn 設定，造成雲端連線 2 秒中斷。教訓：基礎設施參數必須在最外層進程管理器的 CMD 顯式宣告。
- **Windows CP950 終端 Emoji 編碼中斷陷阱 (FP-043)**：在 Windows 繁體中文終端下執行測試調度腳本時，直接輸出 Unicode Emoji（如 🧠）會拋出 `UnicodeEncodeError` 導致調度腳本崩潰。教訓：CLI 調度腳本必須在開頭強制注入 `sys.stdout/stderr.reconfigure(encoding='utf-8')`。

### 3. 🔴 Technical Debt (技術債與後續追蹤)
- **四大主視圖雙向交叉滑動 (Cross-Slide Entrance & Exit)**：目前為了堅守 Zero-Remount 與 WebGL 地圖極致省電，退場視圖採用立即 `hidden` 凍結渲染；未來若硬體效能充裕，可評估微幅放寬 200ms 的退場動畫（Cross-Fade Slide Out）。

---

## 🔮 下一步計畫 (Next Steps)

1. **Universal Travel Interoperability Hub 落地**：
   - 推進 RFC 5545 iCalendar (`.ics`) 本地零依賴匯出（Apple Calendar / Google Calendar / Outlook）。
   - 推進大圓航線軌跡 GeoJSON 匯出與深層外部地圖喚起 (Apple Maps / Google Maps URL Scheme)。
2. **真機 E2E 效能與 Core Web Vitals 遙測 (`/verify-e2e`)**：
   - 在真機 Standalone PWA 模式下持續監測高頻滑動下的 120Hz ProMotion 幀率與觸控防震穩定性。
