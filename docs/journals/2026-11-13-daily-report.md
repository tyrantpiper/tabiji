# 📅 Daily Report - 2026-11-13 (Multi-Model Resilience, Service Worker Routing Isolation, Official Portal Bilingual Launch, Teamwork Scratch Defense & 11-07~11-13 Historical Asset Consolidation)

> **系統狀態**：🟢 Production Ready & Security Sentinel v2.5.0 Hardened, 0 TypeScript Errors (`tsc --noEmit`), 0 ESLint Warnings, 100% Tests Green (Frontend Vitest: 109/109 Files, 1051/1051 Tests Passed, 4 Skipped; Backend Pytest: 648 Collected, 643 Passed, 5 Skipped, 0 Errors; Root Hygiene Sentinel: Clean; Teamwork Scratch Gate: Clean; Neural Seams Invariants: 10/10 Intact), Security Ledger 377 Targets (156 Remediated, 54 Verified, 167 Dismissed, 100% 數學守恆 + 歷史決策防線).
> **本次工程交付範疇 (11-09 ~ 11-13 Core Focus)**：
> - 🤖 **多模型路由強固與 SDK 異常映射 (Multi-Model Routing & SDK Compat, Commit 2b96441)**：深度修復 Google GenAI 2.16.0 Interactions SDK 異常處理，雙重攔截 `compat_errors.APIStatusError` 與 `genai_errors.APIError`；Gemini 3.8 / Gemma `thought_signature` 400 精準處置；思考長度（Thinking Budget）適配矩陣；免費金鑰原生 Grounding 429 隔離（不計入全域熔斷池）；非同步客戶端依 Event Loop 分桶與優雅關閉。
> - 🌐 **後端地理、POI、行程與智慧搜尋翻修 (Backend Geo, POI, Trips & Smart Search, Commit 3709b28)**：全面加固行程成員存取控制（`check_trip_access`）、單列查詢安全（替代 `.single()` 為 `_first_row`）、資料庫同步呼叫線程池化（`run_in_threadpool`）、分類快路徑正則多語系碰撞隔離、POI 搜尋與暫態地理服務健全化。
> - 🛡️ **前端 AI 金鑰哨兵、聊天視窗與 SSE 解析器 (Frontend AI Key Sentinel & SSE Parser, Commit 4a3ea5f)**：修復開發者模式哨兵字串比對順序（防 ASCII 過濾污染出站標頭）；重構聊天視窗與 `ActuaryDialogCard` 錯誤展示與保底機制；補齊 SSE 前端解析器對流式思考標籤與 tool 事件之相容性。
> - 🎌 **官方網站雙語展示總站與微動效 (Official Portal, Bilingual Switcher & Motion, Commit 4863d07)**：同源子路由 `/official` 獨立入口；官方與 PWA 雙語切換無縫銜接（`OfficialLanguageContext`）；打字機標題 a11y 雙層 DOM 與視口觸發；真機儀表板（Authentic Device Theater）與空間航線動態卡片。
> - 📱 **Service Worker 路由隔離與離線儲存 (PWA SW Routing Isolation & IDB Storage, Commit 1bc8637)**：修復無尾斜線 `/api/trips` 快取穿透缺陷（所有 `/api/*` 一律強制 NetworkOnly）；清理 Serwist 歷史殘留快取；推播導引安全淨化（防止反斜線與控制字元跳轉）；IndexedDB 離線寫入單一權威化。
> - 🎨 **介面設計收斂與隱私強化 (UI Polish & Privacy Hardening, Commit 4697c56)**：個人檔案贊助與公益進度 Fail-Closed 且徹底去法幣金額化；底欄導航、日曆排程與地圖元件排版微調；多語系切換全棧一致性同步。
> - 🔒 **多代理人協作暫存區版控隔離 (Teamwork Scratch Gate, Commit 0dd8371, AD-151)**：`.agents/teamwork/` 臨時協作目錄納入 `.gitignore` 與 `/push` 守門檢驗，杜絕跨代理暫存雜訊污染版控。
> - 📚 **資安覆蓋台帳與歷史防禦歷程固化 (Sentinel Ledger & History Reports, Commit 940037b)**：更新 `security-coverage-ledger.json` 至 377 個標的，固化 11-08 至 11-11 的候選修補 diff 與 sentinel 審計報告。

---

## 🏆 深度專案復盤：11-09 ~ 11-13 六大工程里程碑

---

### 里程碑一：多模型智能分流、思考配置適配與 Interactions SDK 健全化 (Commit `2b96441`, `4a3ea5f`)

1. **Google GenAI 2.16.0 SDK 異常捕捉雙軌化**：
   - `google-genai==2.16.0` 的 `client.interactions.*` 丟出 `google.genai._gaos.lib.compat_errors.APIStatusError`（屬性為 `status_code`），而非 `genai_errors.APIError`（屬性為 `code`）。舊版僅攔截 `genai_errors.APIError` 導致 400/401/404/429 逃逸並退化為 `500 Internal Server Error`。
   - 於 `backend/routers/agents.py` 定義 `_INTERACTION_API_ERRORS = (genai_errors.APIError, _compat_errors.APIError)`，並透過兼容提取器抹平狀態碼差異。
2. **免費金鑰原生 Grounding 429 熔斷隔離**：
   - Gemini 免費層若附加 `GoogleSearch()` 或原生 Maps 工具，工具調用額度極低（短突發即 429）。此類錯誤屬於工具附加額度耗盡，非模型運算核心崩潰。
   - 嚴格隔離工具層 429，禁止寫入 `record_model_error`，避免核心旗艦模型被誤鎖 300 秒。
3. **Thinking Budget 矩陣跨模型映射**：
   - Gemini 2.5 系列關閉/低思考使用整數型 `thinking_budget=0`。
   - Gemini 3.8 系列採用枚舉型 `ThinkingLevel.LOW / MEDIUM / HIGH`。
   - Gemma 4 系列採用 `minimal / high` 宣告，且其思考耗時較長（30~50s），不適合放入 <2s 意圖分類路徑。
4. **開發者模式哨兵比對與 ASCII 過濾順序**：
   - 前端金鑰診斷中，開發者模式哨兵字串 `"(開發者模式)"` 比對必須在 ASCII 特殊字元過濾之前執行。舊順序導致中文括弧被剔除後退化為 `"()"`，外洩至 HTTP Header。

---

### 里程碑二：Service Worker 路由隔離、API 快取收斂與推播導引安全 (Commit `1bc8637`)

1. **無尾斜線 API 快取逃逸漏洞修補**：
   - 舊版 `sw.ts` 僅宣告排除 `/api/trips/`。前端 hooks（`useTrips`）請求 `/api/trips`（無尾斜線），被 `@serwist/next` 的預設規則判定為普通 API，落入 `apis` 暫存桶快取 24 小時。
   - 由於 `CacheStorage` 僅以 URL 作為索引鍵而不區分 HTTP Authorization Header，在共用裝置切換使用者或網路離線時，會錯誤吐出前一位使用者的行程資料。
   - 全面收斂為 `url.pathname.startsWith("/api")` 一律強制作為 `NetworkOnly`，離線資料由 IndexedDB 與 SyncQueue 完全接管。
2. **推播跳轉安全性淨化（CWE-20）**：
   - 網域白名單嚴格限制為精確匹配或後綴比對（`host === d || host.endsWith('.' + d)`），杜絕 `hostname.includes('cloudinary.com')` 放行 `evil-cloudinary.com` 之偽造漏洞。
   - 推播 Payload 中的導航連結強制過濾反斜線 `\`、ASCII 控制字元與跨源跳轉，不合規者強制回退至 `/`。

---

### 里程碑三：官方網站展示總站、雙語無縫交接與無障礙打字機動效 (Commit `4863d07`)

1. **同源子路徑架構決策（AD-OFFICIAL-ROUTE）**：
   - 官方網站採同源子路徑 `tabijiapp.com/official` 部署，免除次級網域 DNS、Cloudflare 路由與 SSL 憑證異動風險，保護 PWA 現有主畫面安裝權限。
   - 於 PWA 安裝橫幅與即時聊天懸浮鈕實作路徑隔離，官方展示頁面不渲染應用內專屬浮層。
2. **雙語無縫導航與狀態接力**：
   - 實作 `OfficialLanguageContext`，官方頁面語言切換（`zh-TW` / `en`）支援 URL 參數、Cookie 與 LocalStorage 記憶。
   - 點擊「Launch App」按鈕時攜帶 `?lang=en` 參數，PWA 根路由在首屏啟動階段無縫承接語系偏好。
3. **打字機文字無障礙與 React 19 編譯器相容**：
   - 打字機動態標題使用 `sr-only` 保留完整無障礙語意標籤，動態動畫層標註 `aria-hidden="true"`。
   - 外層 key 隔離內層 state 狀態，徹底解決 React Compiler 在渲染期因 ref 狀態變更引發的水合警告。

---

### 里程碑四：行程存取授權、單列查詢強化與非同步線程池化 (Commit `3709b28`)

1. **行程子資源垂直越權（BOLA）防守**：
   - 所有行程關聯子資源（天數、地點、花費、AI 評論）端點強制經過 `check_trip_access` 檢查，確保僅房間合法成員可存取。
2. **單列查詢 `.single()` 崩潰預防**：
   - 將易引發資料庫未命中例外的裸 `.single()` 呼叫重構為 `_first_row` 安全查詢，在無資料或旅伴已刪除情況下回傳乾淨的 404/403，不再被伺服器吞沒為 500。
3. **非同步路由內同步 SDK 線程池隔離**：
   - FastAPI async 路由呼叫同步 Supabase SDK 時全面以 `run_in_threadpool` 包裹，防止阻塞 Uvicorn 主事件循環。

---

### 里程碑五：多代理人協作工作區版控隔離防線（AD-151, Commit `0dd8371`）

1. **協作暫存檔案實體隔離**：
   - 多代理人協同運作產生的臨時暫存檔與探針（`.agents/teamwork/`）在 `.gitignore` 顯式排除。
   - 在 `/push` Quality Gate 增設 `Teamwork Scratch Gate`，以 `git ls-files .agents/teamwork` 進行強制物理阻斷，確保協同碎片絕不污染 Git 版控歷史。

---

### 里程碑六：資安覆蓋台帳數學守恆校準 (Commit `940037b`)

1. **安全台帳狀態空間守恆**：
   - 依據 Google Research Harness² 狀態空間約束，資安覆蓋台帳總標的擴充至 377 項：
     - `remediated_vulnerabilities`: 156
     - `verified_vulnerabilities`: 54
     - `dismissed_hypotheses`: 167
     - 總計：$156 + 54 + 167 = 377$（100% 數學守恆無漂移，`validate_security_ledger.py` 驗證退出碼 0）。

---

## 🏛️ 架構決策紀錄 (Architecture Decisions)

- **AD-151 (Multi-Agent Teamwork Scratch Isolation)**:
  - *Context*: 多代理人背景協同會在 `.agents/teamwork/` 產生大量溝通 JSON 與探針檔案。
  - *Decision*: 於 `.gitignore` 加入 `/.agents/teamwork/`，並在 `scripts/neural_seam_harness.py` 與 `/push` 流程中注入硬性斷言，只要索引中存在 teamwork 檔案立即中斷發布。
  - *Trade-off*: 開發者若需手動查看代理人交接日誌需直接瀏覽該本機目錄，不進入遠端倉庫。
- **AD-OFFICIAL-ROUTE (Official Portal Subpath Deployment)**:
  - *Context*: 官方形象入口需要與 PWA 共享主網域，且不可破壞已有使用者的 PWA 離線快取與 Manifest。
  - *Decision*: 採用同源子路徑 `/official` 部署，透過 `sw.ts` 路由守衛與 Suspense 包裹客戶端元件，完成與應用本體的樣式與邏輯隔離。
- **AD-AI-LAYERED-INTENT (Two-Stage Intent Classification)**:
  - *Context*: 單一模型分類在高並發或網路延遲下易超時，超時若降級 SEARCH 會引發不必要的外部搜尋風暴。
  - *Decision*: 第一階段以本地純正規表示式（0ms）過濾讚美、問候與明確行程動作；第二階段模型分類若遇超時，中性降級為 CHAT/AUTO，絕對不強制調用工具。

---

## 🛡️ 踩坑記錄 (Failed Paths - 11-07 ~ 11-13)

- **FP-SW-BGSYNC-01**: Serwist `bgSyncPlugin` 路由漏傳 HTTP method 預設僅監聽 GET，線上命中率為 0 且與本機 SyncQueue 邊界重疊。離線重試佇列必須維持單一權威源。
- **FP-DEVOPS-FREEZE-01**: 單元測試中斷言 `git diff HEAD === ""` 作為凍結守門，會阻斷合法安全修復並卡死發布管線。凍結核心應寫為行為契約測試。
- **FP-UI-SCROLLSPY-01**: 點擊錨點平滑捲動與 `IntersectionObserver` 判定互斥振盪（0.8s 內 3 次跳動）。點擊時應設置互斥鎖暫停 Observer 回寫約 900ms。
- **FP-UI-SVGORIGIN-01**: SVG 旋轉中心使用像素值（`100px`）在不同 DPI 下縮放偏移。應使用 `transformBox: 'view-box'` 配合百分比或 viewBox 座標。
- **FP-STATE-HEAD-01**: 子路由 layout 宣告 `<head>` 導致 React 19 水合崩潰。子路由資源預載應使用 `<Image priority>` 或 route metadata。
- **FP-BE-INTENT-01**: 意圖分類 1.8s 硬逾時無腦降級 SEARCH + mode=ANY，逼迫模型呼叫工具輸出空文字，引發前端 28px 空白幽靈氣泡與對話中斷。
- **FP-BE-GEMMA-01**: Gemma 4 深度思考延遲（30~50s）被誤診為模型未開放或端點崩潰。高時效路徑不應選用該模型，且工具呼叫應扁平化。
- **FP-BE-429-01**: RPD 配額未滿卻頻繁 429 源於短突發超限與免費金鑰之付費 Grounding 工具耗盡。移除初次雙重呼叫並停用免費金鑰的原生 Grounding。
- **FP-BE-THOUGHT-SIG-400**: Gemini 3.8 / Gemma 的 `thought_signature` 400 錯誤被粗暴判定為配置不支援導致不當降級。應針對錯誤詳情進行精準模式比對。

---

## 🔴 技術債狀況 (Technical Debt Status)

- **[RESOLVED in 2b96441] DEBT-BE-SILENT-JSON-01**: 模型 200 OK 但 JSON 解析失敗時缺乏診斷日誌，已於 `backend/services/model_manager.py` 補齊模型名稱、意圖與長度追蹤。
- **DEBT-SW-PRECACHE-SYNC**: `frontend/public/sw.js` 包含編譯時注入的 git revision，每次 HEAD 變更重跑 `build-sw.mjs` 會產生微幅版本雜訊，需評估是否在 CI 階段統一生產並排除於日常源碼追蹤。

---

## 🎯 Next Steps

1. 待使用者授權後執行 `git push origin main` 將 8 組提交同步至 GitHub 遠端。
2. 評估將 `C:\Users\Ryan su\.gemini\antigravity\brain\5dbe8200-1879-4852-be56-160d7e6f93f3` 內的 22 份 spec 與架構圖手動備份至專案 `docs/specs/` 後清理對話。
3. 持續監控 Gemini 3.8 Flash 生產環境調用穩定度與配額消耗比。

---

## 🧬 Machine-Executable Invariant Rules

```json
[
  {
    "domain": "offline_pwa",
    "type": "INVARIANT_RULE",
    "id": "INV-SW-02",
    "title": "SW 排除規則須涵蓋無尾斜線 API 路徑；所有 /api/* 一律 NetworkOnly",
    "content": "CacheStorage 只依據 URL 匹配而不檢查 Header。若 SW 僅排除帶尾斜線的 /api/trips/，而前端發起 /api/trips，會導致共用裝置在切換帳號或離線時吐出前一位使用者的快取資料。所有 /api/* 必須一律設為 NetworkOnly，離線寫入與本機持久化完全委任 IndexedDB 與 SyncQueue。"
  },
  {
    "domain": "offline_pwa",
    "type": "FAILED_PATH",
    "id": "FP-SW-BGSYNC-01",
    "title": "Serwist BackgroundSync 路由漏傳 method 導致死路由與雙重排隊",
    "content": "在 Serwist 中註冊 BackgroundSync 插件若未顯式傳入 HTTP method，預設僅攔截 GET 請求，導致線上命中率 0% 且與前端本機 SyncQueue 邊界重疊。離線重試佇列必須保持單一權威源，嚴禁未經測試掛載空泛 SW BackgroundSync。"
  },
  {
    "domain": "offline_pwa",
    "type": "INVARIANT_RULE",
    "id": "INV-SW-03",
    "title": "SW 網域白名單精確比對與推播導引安全淨化",
    "content": "網域白名單比對嚴禁使用 .hostname.includes()，必須採用 host === domain || host.endsWith('.' + domain) 以防禦次級域名偽造（CWE-20）。Web Push 導引連結必須封鎖反斜線、ASCII 控制字元與跨源跳轉，非安全路徑強制 fallback 至 /。"
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-DEVOPS-FREEZE-01",
    "title": "以 git diff HEAD === '' 當凍結不變量會阻斷合法安全修補並卡死 CI 閘門",
    "content": "凍結核心（Frozen Core）應撰寫為行為契約測試（驗證離線/資安不變量），而非在單元測試中硬性斷言 git diff HEAD -- file === ''。後者會導致任何合法的上游依賴修補或預編譯直接判定為測試失敗，並造成提交循環死鎖。"
  },
  {
    "domain": "ios_ui",
    "type": "FAILED_PATH",
    "id": "FP-UI-SCROLLSPY-01",
    "title": "ScrollSpy 高亮標記與平滑捲動互斥競態（Flapping Race）",
    "content": "點擊導航錨點觸發平滑捲動時，途中被 IntersectionObserver 觸發回彈判定，導致 0.8s 內產生多次振盪閃爍。應在點擊時以 isManualScrollingRef 互斥鎖暫停 Observer 回調寫入 state 約 900ms，捲動抵達後再解除鎖定。"
  },
  {
    "domain": "ios_ui",
    "type": "FAILED_PATH",
    "id": "FP-UI-SVGORIGIN-01",
    "title": "SVG 羅盤指針 transform-origin 使用像素單位導致響應式縮放位移刺穿卡片",
    "content": "在 SVG 向量動效中，transform-origin: 100px 在不同螢幕 DPI 縮放時會被視為絕對像素偏移。旋轉中心必須使用 transformBox: 'view-box' 配合百分比或 viewBox 原生座標，外層容器必須添加 overflow-hidden。"
  },
  {
    "domain": "state_cache",
    "type": "FAILED_PATH",
    "id": "FP-STATE-HEAD-01",
    "title": "子路由 layout 宣告 head 導致 React 19 與 Next.js 16 渲染層水合錯誤",
    "content": "在 Next.js App Router 架構下，只有根路由 app/layout.tsx 允許渲染 html, body, head。子路由（如 app/official/layout.tsx）若重複宣告 head，會觸發 In HTML, head cannot be a child of body 水合失敗。資源預載應透過 Image priority 或 route metadata 宣告。"
  },
  {
    "domain": "offline_pwa",
    "type": "INVARIANT_RULE",
    "id": "INV-UI-ROUTEISO-01",
    "title": "官方展示頁（/official/*）隔離 PWA 安裝提示與即時聊天助手",
    "content": "官方入口頁面採同源子路徑部署時，必須依 usePathname() 嚴格隔離 PWA 安裝橫幅與即時聊天懸浮鈕，兼顧渲染層與 Effect 層雙重防守。Next.js 16 下使用 usePathname() 的客戶端元件外層必須以 Suspense fallback={null} 包裹以確保靜態編譯合規。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BE-TIMEOUT-01",
    "title": "SSE 心跳僅保連線存活，底層模型呼叫需獨立 wait_for 且逾時不計全域熔斷",
    "content": "SSE 傳輸層 10s keep-alive 僅維持 HTTP 連線，google-genai SDK 預設 timeout=None 會在 upstream 異常時永久阻塞。模型呼叫必須以 asyncio.wait_for 設置端點逾時（無心跳 90s、SSE 120s）。逾時僅切換至下一備援模型，絕不可呼叫 record_model_error 誤鎖健康旗艦模型。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-BE-INTENT-01",
    "title": "意圖分類 1.8s 硬逾時無腦降級 SEARCH + mode=ANY 導致 28px 空白幽靈氣泡與對話中斷",
    "content": "分類逾時若強制降級為 SEARCH 意圖且以 ToolConfig(mode=ANY) 強制模型呼叫工具，會使讚美/問候語句輸出空文字，引發前端 28px 空白氣泡，下一輪遺失 model 訊息而觸發 Gemini 400 INVALID_ARGUMENT。分類逾時必須中性 fallback 為 CHAT/AUTO，並引入本地 Regex 0ms 短路判斷。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-BE-GEMMA-01",
    "title": "Gemma 4 深度思考延遲被誤診為模型未開放或端點崩潰",
    "content": "Gemma 4 系列模型因原生思考延遲達 30~50s，若置於 <2s 之快速分類端點會被逾時中斷。不可在未經真實探測下誤診為模型未開放。Gemma 4 不適合高時效分類路徑；呼叫時工具宣告應採用 Depth=1 扁平化結構以避免 400 schema 衝突，純文字模式關閉自動函數呼叫。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BE-STREAM-SANITIZER-01",
    "title": "串流生成必須經由 Lookahead 滑動窗過濾裸 JSON 協定與內部思考標籤",
    "content": "模型輸出尾端偶發之 { items: [...] } 函數呼叫與 thought/thinking 思考標籤若直接以 event: text 推送會外洩系統提示詞。必須由 StreamLookaheadSanitizer 30 字元滑動窗進行前瞻緩衝，使用 json.JSONDecoder().raw_decode 識別閉合 JSON 並轉為 event: tool 推送。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-BE-429-01",
    "title": "RPD 配額未滿卻頻繁遭遇 429 速率限制之四層成因與退避治理",
    "content": "429 觸發多源於短突發速率（RPM/TPM）或免費金鑰之付費 Grounding 工具耗盡，非每日總請求數（RPD）耗盡。移除 SEARCH 意圖之 First-Pass 雙重呼叫可降低 60% 瞬間突發；免費金鑰停用 Google 原生 Grounding；SlowAPI 改用金鑰雜湊分桶避免本機 127.0.0.1 誤限流；暫態 429 不計入 300s 熔斷池。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BE-LOCALE-01",
    "title": "多語系全棧切換契約：UI locale 必傳且 Prompt 注入與分類快路徑全面聯動",
    "content": "使用者語言由前端介面 locale 明確決定，禁止由後端輸入隨意猜測。所有 AI 端點必須傳入 locale；SYSTEM_PROMPT、搜尋字串注入與行程評估 Prompt 依 locale 動態渲染；分類快路徑正則必須避免英文關鍵字（如 check）誤觸發繁體中文搜尋模板。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BE-AUTHZ-01",
    "title": "行程資源存取授權、單列查詢安全、同步 SDK 線程隔離與對外錯誤遮蔽基線",
    "content": "所有行程子資源端點必須驗證房間成員權限（check_trip_access）；資料庫查詢禁止使用裸 .single()，應採用 _first_row 並安全回傳 404/403；async FastAPI 路由呼叫同步 Supabase SDK 必須使用 run_in_threadpool；全域例外處理器嚴禁對外回傳 traceback。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BE-PRIVACY-DONATION-01",
    "title": "公益進度查詢 Fail-Closed 原則與個人隱私去法幣化",
    "content": "贊助與公益進度 API 僅回傳百分比與狀態 {available, percentage, month}，絕對禁止包含任何法幣金額欄位以避免使用者誤解。後端拋錯或未啟用時前端自動隱藏且不發起重複請求，骨架屏依實際內容縮小避免 CLS。"
  },
  {
    "domain": "backend_concurrency",
    "type": "TECHNICAL_DEBT_RESOLUTION",
    "id": "DEBT-BE-SILENT-JSON-01",
    "title": "模型 200 OK 提取但 JSON 解析失敗之診斷追蹤與日誌補齊",
    "content": "後端 call_extraction 捕捉 json.JSONDecodeError 時，必須顯式記錄模型名稱、意圖、長度與文字頭尾預覽，禁止靜默吞沒異常直接退避，確保高延遲重試具備可觀測性。",
    "status": "RESOLVED",
    "commit": "2b96441"
  },
  {
    "domain": "ios_ui",
    "type": "INVARIANT_RULE",
    "id": "INV-UI-TYPEWRITER-01",
    "title": "打字機動畫標題雙層 DOM 無障礙設計與 React Compiler 渲染隔離",
    "content": "打字機文字元件必須包含 sr-only 完整可讀文字與 aria-hidden 動態層以維護 a11y；外層 key 隔離內層 state 避免 React 19 / React Compiler 於渲染階段觸發狀態循環更新；支援 prefers-reduced-motion 降級為靜態文字。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BE-COMPAT-ERRORS-01",
    "title": "Google GenAI Interactions SDK 異常捕獲須相容 compat_errors.APIStatusError",
    "content": "google-genai==2.16.0 的 client.interactions.* 呼叫拋出的是 google.genai._gaos.lib.compat_errors.APIStatusError（屬性為 status_code），而非 genai_errors.APIError（屬性為 code）。後端異常攔截必須使用雙重元組 (genai_errors.APIError, _compat_errors.APIError)，並透過相容取值器提取 HTTP 狀態碼，避免 400/401/404/429 被誤判為 500。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BE-FREE-GROUNDING-429",
    "title": "免費金鑰 GoogleSearch 原生工具 429 嚴禁計入全域模型熔斷池",
    "content": "Gemini 免費層呼叫原生 GoogleSearch() 產生的 429 屬於工具附加額度耗盡，非模型運算核心離線。此類錯誤絕不可傳遞至 record_model_error，避免將核心 Gemini 旗艦模型錯誤封鎖 300 秒。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BE-AI-CLIENT-CACHE-LOOP",
    "title": "AI 異步客戶端快取需依 Event Loop 實例分桶並於 Shutdown 統一釋放",
    "content": "在測試環境或動態任務中，多個測試案例可能運行於不同的 asyncio 事件循環。全域 AI 客戶端快取必須以 id(asyncio.get_running_loop()) 作為快取分桶鍵，並在 FastAPI lifespan 關閉時遍歷關閉所有連線池，杜絕 Event loop is closed 殭屍連線警告。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-BE-THOUGHT-SIG-400",
    "title": "Gemini 3.8 與 Gemma 系列 thought_signature 400 錯誤避免誤判為配置不支援",
    "content": "當 Gemini 3.8 或後續模型回傳 thought_signature 相關 400 INVALID_ARGUMENT 時，系統不可武斷將其歸類為 config_unsupported 觸發全域降級。應針對錯誤詳情進行精確模式比對，並在降級時優先剝離思考簽名配置進行原模型重試。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BE-THINKING-BUDGET-MATRIX",
    "title": "各主流模型思考配置（Thinking Budget）相容性矩陣契約",
    "content": "思考模式配置存在嚴格的模型版本差異：Gemini 2.5 系列關閉/低思考使用數值型 thinking_budget=0；Gemini 3.8 系列採用枚舉型 ThinkingLevel.LOW / MEDIUM / HIGH；Gemma 4 系列採用 minimal / high 宣告。跨模型傳遞配置前必須經過適配矩陣轉換，嚴禁混用。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BE-INTERACTIONS-REMOTE",
    "title": "Antigravity Preview Agent 互動建立必須顯式指定 remote 環境",
    "content": "在調用 antigravity-preview-09-2026 的 interactions.create 時，請求參數必須顯式包含 environment=\"remote\"；傳入不存在或已過期的 interaction_id 探針時後端必須回傳 400，並精準映射至 404/401/429 狀態碼。"
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-SEC-SENTINEL-ASCII-ORDER",
    "title": "開發者模式哨兵字串比對必須在 ASCII 特殊字元過濾之前執行",
    "content": "在 API 金鑰診斷與請求標頭處理管線中，開發者模式哨兵字串比對（如 '(開發者模式)'）必須在非 ASCII 或控制字元過濾之前進行。若順序倒置，中文中括號被過濾器剔除後會退化為殘留字串 '()'，進而外洩至出站 HTTP 標頭造成資料污染。"
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-DEVOPS-TEAMWORK-SCRATCH",
    "title": "多代理人暫存工作區（.agents/teamwork/）版控雙重隔離防線（AD-151）",
    "content": "多代理人協同運作產生的臨時暫存檔與溝通日誌（.agents/teamwork/）必須在 .gitignore 嚴格宣告忽略，並於 /push Quality Gate 的 Teamwork Scratch Gate 進行物理探針檢查（git ls-files .agents/teamwork），嚴禁任何協作暫存碎片進入 Git 版控歷史。"
  }
]
```
