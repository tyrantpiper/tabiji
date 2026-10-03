# 📅 Daily Report - 2026-10-03

> **系統狀態**：🟢 Production Stable, Custom Domain `tabijiapp.com` Live, Zero-Cost Same-Origin Edge Shield Deployed on Cloudflare Anycast, Google Front End (GFE) 404 Routed via Dynamic Host Rewrite, Cloudflare Image Proxy Multi-Origin Whitelisted with CORS Injection, Dual-Active PWA Storage Preserved, 0 TypeScript Errors, 0 ESLint Warnings, 100% Tests Green (Backend 95/95, Frontend 257/257, Total 352/352 Tests Passing)  
> **今日關鍵提交串列 (Full Day Commit Stream)**：
> - [`2acf235`](https://github.com/tyrantpiper/travel-pwa/commit/2acf235) `fix(infra): allow custom domain in cloudinary proxy and inject cors headers`
> - [`3f5abc5`](https://github.com/tyrantpiper/travel-pwa/commit/3f5abc50c8e3e4a29aefb20ccefcbbec6fbfca26) `docs(daily-report): record custom domain and same-origin edge shield memory`
> - [`ea26adc`](https://github.com/tyrantpiper/travel-pwa/commit/ea26adc8843e4169b435151ca8ed844b6f65747a) `chore(infra): add tabijiapp-edge-shield worker configuration`
> - [`7da4795`](https://github.com/tyrantpiper/travel-pwa/commit/7da4795c9803569dfcacf3cfdb11d32434da933b) `feat(infra): implement same-origin edge shield and register tabijiapp.com`
> - [`f4b496d`](https://github.com/tyrantpiper/travel-pwa/commit/f4b496d96aedb081ce00a725c83c1269155022d0) `docs(hierarchy): standardize reports, research, and screenshots with asset isolation and master navigation`
> - [`a764b87`](https://github.com/tyrantpiper/travel-pwa/commit/a764b871ec9f805c4f881a71a3d5e245a11f36cf) `docs(specs): organize specs into domain-driven structure and establish navigation matrix`
> - [`4dc9ed9`](https://github.com/tyrantpiper/travel-pwa/commit/4dc9ed9ce76200c27936d6dc0c3273478e1dc017) `docs(skill): upgrade cloudflare-wrangler with modular references and mcp ecosystem standards`

---

## 🏆 深度專案復盤：獨立頂級網域上線、零成本同源邊緣防護罩、GFE 動態路由重寫與 PWA 本地沙箱無損雙軌共存

本日 Tabidachi 完成了從「測試網址展示品」正式蛻變為「主權獨立頂級品牌商用 PWA」的關鍵基礎設施飛躍：

1. **上半場（工程體系與文件資產規範化）**：
   - 升級 `cloudflare-wrangler` 技能手冊，建立包含邊緣模式、MCP 生態與排錯指引的模組化參照文件。
   - 將全站 20+ 份規格文件重組為領域驅動（DDD）的 6 大模組架構（`ai`, `business`, `core-architecture`, `infra`, `search`, `ui-motion`），並建立頂層導航矩陣 `docs/specs/README.md`。
   - 實現展示截圖（Showcase）與自動化驗收截圖（Verification）的物理分流與標準化資產隔離。

2. **下半場（自訂網域 `tabijiapp.com` 與零成本同源邊緣防護罩）**：
   - 在 Cloudflare 註冊主權獨立頂級網域 `tabijiapp.com`，配置 CNAME 代理至 Vercel Edge，啟用 Full (strict) SSL 與全球 Anycast 防護。
   - 徹底消滅前端客戶端直連暴露 Google Cloud Run 網址的歷史隱患，實作全站同源化 API 調度與多態 `getApiHost()`。
   - 攻克 Google Cloud Run 多租戶路由器 GFE（Google Front End）拒絕非 `*.run.app` 主機名稱導致的 404 退件死穴；繞過 Cloudflare 需每月 2,000 美元企業版方可解鎖 Origin Rules Host Rewrite 的付費牆，利用免費 Cloudflare Worker（`tabijiapp-edge-shield`）在邊緣節點動態重寫 `Host` 標頭為真實 Cloud Run 服務網址，達成 0 成本完美轉發。
   - 精準實裝 Vercel 本地 API 旁路白名單（`/api/sign-cloudinary`, `/api/parse-receipt` 直通 Vercel Edge，其餘 `/api/*` 直達 Cloud Run）。
   - 深入洞察 W3C Storage Origin 沙箱邊界，果斷否決暴力 308 重定向，保留舊網域 `travel-pwa-five.vercel.app` 獨立存活，100% 捍衛已安裝在手機桌面使用者的 IndexedDB / localStorage 本機資料。

3. **夜間加固（雙網域全功能對齊與 Cloudflare 圖片代理全源穿透）**：
   - 深度排查新網域 `www.tabijiapp.com` 點擊「抓取街景」後卡片破圖消失之 Bug。
   - 快速定位根因為 Cloudflare Worker `cloudinary-proxy` 之 Referer 防盜鏈白名單僅允許舊站 `travel-pwa-five.vercel.app` 與 localhost，發出 403 阻斷引發前端 `<Image onError>` 隱藏卡片相片。
   - 升級 Worker 邏輯：動態支援主網域 `tabijiapp.com`、`www.tabijiapp.com`、舊站與本地開發，放行 PWA Standalone 模式（無 Referer/Origin），並注入 `Access-Control-Allow-Origin: *` 防禦 PDF / Canvas 匯出污染。
   - 遵循 Bug Hunter 規範進行 Red-Green TDD 迴圈，並以 Chrome DevTools MCP 實機驗收，消除全部 403 報錯，新舊網域十維度功能完全對齊。

全系統通過 352 項自動化測試（後端 Pytest 95/95 通過，前端 Vitest 257/257 通過），TypeScript 與 ESLint 保持 0 錯誤底線，線上端到端即時撥測全部綠燈。

---

### 1. 同源邊緣防護罩全鏈路流量調度拓撲

```mermaid
flowchart TD
    subgraph Users ["使用者與終端設備"]
        Browser["瀏覽器 / 手機 PWA 客戶端"]
        LegacyPWA["已安裝在桌面的舊版 PWA<br/>(origin: travel-pwa-five.vercel.app)"]
    end

    subgraph CF_DNS ["Cloudflare Anycast 邊緣網路 (tabijiapp.com)"]
        CF_DDoS["L3/L4 DDoS 防護 & Anycast DNS"]
        WorkerRoute{"URL 路徑判定"}
    end

    subgraph Cloudflare_Worker ["邊緣防護罩 Worker (tabijiapp-edge-shield)"]
        PathCheck{"路徑是否在白名單?<br/>/api/sign-cloudinary<br/>/api/parse-receipt"}
        Rewriter["動態 Host 標頭覆寫<br/>Host: antigravity-backend-...run.app<br/>X-Forwarded-Host: www.tabijiapp.com<br/>X-Edge-Shield: Active"]
        StreamForward["SSE / 串流透傳 (無緩衝)"]
    end

    subgraph Vercel_Platform ["Vercel Edge Platform (Frontend PWA)"]
        ApexRedirect["tabijiapp.com -> 308 -> www.tabijiapp.com"]
        VercelSSR["Next.js 16 App Router (SSR / ISR)"]
        VercelAPI["Vercel Serverless Functions<br/>(Cloudinary 簽名 / 收據 OCR)"]
        LegacyVercel["舊版網址 travel-pwa-five.vercel.app<br/>(保持運作，本地儲存不丟失)"]
    end

    subgraph Google_Cloud ["Google Cloud Platform (Backend)"]
        GFE["Google Front End (GFE 負載均衡路由器)<br/>核驗 Host 標頭名牌"]
        CloudRun["FastAPI 3.12+ (antigravity-backend)<br/>CORS & TrustedHost 白名單"]
        Supabase["Supabase DB & Realtime"]
    end

    %% Flow connections
    Browser -->|HTTPS 請求| CF_DDoS
    CF_DDoS --> WorkerRoute

    WorkerRoute -->|非 /api/* (網頁、靜態資產、PWA Shell)| ApexRedirect
    ApexRedirect --> VercelSSR

    WorkerRoute -->|符合 /api/* 路由觸發器| PathCheck
    PathCheck -->|是 (Vercel 本地專屬)| VercelAPI
    PathCheck -->|否 (一般業務 API / SSE)| Rewriter

    Rewriter --> StreamForward
    StreamForward -->|轉發至 Cloud Run 網址| GFE
    GFE -->|名牌比對通過| CloudRun
    CloudRun --> Supabase

    LegacyPWA -->|直連舊網域| LegacyVercel
    LegacyVercel -.->|伺服端轉發 (INTERNAL_BACKEND_URL)| GFE
```

---

## 🟢 1. Features & Fixes (今日全量交付價值)

### 1. 主權獨立頂級網域正式啟用 (`tabijiapp.com` / `www.tabijiapp.com`)
- **DNS 與 CDN 架構配置**：
  - 於 Cloudflare 註冊管理 `tabijiapp.com`，配置 CNAME 代理至 `cname.vercel-dns.com`。
  - 全域啟用 Cloudflare Full (strict) 雙向加密、Always Use HTTPS、Brotli 高壓縮與 HTTP/3。
  - 在 Vercel 生產環境綁定 `tabijiapp.com` 與 `www.tabijiapp.com`，建立 Apex 至 WWW 的規範化 308 永久轉址。

### 2. 客戶端同源化重構與多態 API 路由 (`frontend/lib/api.ts`, 全站 8+ 元件)
- **拔除後端真實網址洩漏隱患**：
  - 徹底移除客戶端程式碼中直接拼接 `process.env.NEXT_PUBLIC_API_URL` 的裸露寫法，切斷惡意爬蟲或攻擊者直取 Google Cloud Run 網址的攻擊面。
- **抽象多態 `getApiHost()` 與防禦性斜線清洗**：
  - 客戶端瀏覽器環境一律返回空字串 `""`，發起同源相對路徑請求（`/api/...`），由邊緣防護罩自動路由。
  - 伺服端 Node.js / RSC 環境優先讀取 `INTERNAL_BACKEND_URL`，回退讀取 `NEXT_PUBLIC_API_URL`。
  - 實作防禦性正則清洗（`url.replace(/\/+$/, '')`），徹底消除雙斜線（`//api/...`）或路徑截斷缺陷。
  - 同步重構並驗證全站 8 大核心模組：`chat-widget.tsx`, `day-map.tsx`, `MultiDayMasterMap.tsx`, `ledger-client.tsx`, `profile-view.tsx`, `tools-view.tsx`, `hooks.ts`, `app/api/parse-receipt/route.ts`。

### 3. Cloudflare Worker 邊緣防護罩實裝與部署 (`cloudflare/edge-shield/worker.js`)
- **GFE 虛擬主機名稱動態重寫**：
  - 解決 Google Cloud Run 多租戶路由器 GFE（Google Front End）依賴 `Host: *.run.app` 導致自訂網域拋出 404 退件的物理限制。
  - 在邊緣請求中動態抽換 `Host` 標頭為 `antigravity-backend-589255638719.us-central1.run.app`，並安全注入 `X-Forwarded-Host: www.tabijiapp.com`。
- **Vercel 本地專屬路由旁路白名單**：
  - 針對 `/api/sign-cloudinary`（Cloudinary 上傳簽名）與 `/api/parse-receipt`（Vercel Serverless 收據解析），自動判定並直連 Vercel 源站，不驚動 Google Cloud Run。
- **SSE 串流原生透傳與遙測注入**：
  - SSE 事件串流（`/api/chat/stream`）採取零緩衝即時傳輸，維持大模型打字機流暢體驗。
  - 對直連 Cloud Run 請求強制排除 GET/HEAD 的空 Request Body，防止引發 `TypeError: Request with GET/HEAD method cannot have body`。
  - 注入 `X-Edge-Shield: Cloudflare-Worker-Active` 標頭，提供全鏈路追蹤能力。
  - 透過 Wrangler CLI 成功部署生產 Worker `tabijiapp-edge-shield` 並配置 Route 觸發器。

### 4. 後端 CORS 與信任主機白名單雙重加固 (`backend/main.py`)
- 在 `CORSMiddleware` 的 `ALLOWED_ORIGINS` 中新增：
  - `https://tabijiapp.com`
  - `https://www.tabijiapp.com`
- 在 `TrustedHostMiddleware` 的 `ALLOWED_HOSTS` 中同步新增：
  - `tabijiapp.com`
  - `www.tabijiapp.com`
- 兼顧邊緣防護罩與可能直連情境下的 HTTP Host Header 投毒攻擊防禦。

### 5. 舊版 PWA 雙軌並存與本地存儲沙箱保護
- 依據 W3C 規範，PWA 的 IndexedDB、Cache Storage 與 LocalStorage 嚴格受 Origin（通訊協定 + 網域 + 埠號）沙箱隔離。
- 若對舊網域 `travel-pwa-five.vercel.app` 實施強制 308 重定向，已安裝在手機桌面的老使用者將因 Origin 變更而遺失本機離線行程。
- 確立「新使用者全量採用新品牌網域，老使用者雙軌存活」原則，舊網域繼續提供服務並透過伺服端同源代理呼叫後端，達成 0 損失過渡。

### 6. 規格文件與架構研究資產全面拓撲化 (`docs/`)
- 產出 4 篇重量級雲原生網路架構深度研究報告：
  - `docs/research/cloudflare-domain-proxy-cloudrun-vercel-truth.md`
  - `docs/research/zero-cost-edge-shield-and-traffic-flattening-research.md`
  - `docs/research/google-cloud-run-custom-domain-cloud-shield-truth-and-pitfalls.md`
  - `docs/research/zero-cost-edge-worker-shield-vs-custom-domain.md`
- 產出 2 篇標準實裝與維運 SOP 規範：
  - `docs/specs/infra/same-origin-edge-shield-architecture-spec.md`
  - `docs/specs/infra/tabijiapp-cloudflare-setup-sop-spec.md`
- 規格文件全面歸檔至以領域驅動（DDD）為核心的 6 大維度，建立完整矩陣導航。

### 7. Cloudflare 圖片邊緣代理全源放行與 CORS 標頭注入 (`cloudinary-proxy`)
- 升級 Cloudflare Worker `cloudinary-proxy`，白名單從寫死單一 Vercel 網域擴展為動態陣列：`tabijiapp.com`、`www.tabijiapp.com`、`travel-pwa-five.vercel.app`、`localhost`、`127.0.0.1` 與任意 `*.vercel.app`。
- 支援手機 PWA Standalone 與防追蹤嚴格隱私模式（空 Referer / 空 Origin 自動安全放行）。
- 全面注入 `Access-Control-Allow-Origin: *`、`Access-Control-Allow-Methods: GET, HEAD, OPTIONS` 以及 204 OPTIONS Preflight 預檢處理，杜絕 `html2canvas` 匯出 PDF 時 Canvas Tainted 跨域污染。
- 專案根目錄納入版本控制：新增 `cloudflare/cloudinary-proxy/worker.js` 與 `wrangler.jsonc`。

---

## 🏛️ 2. Architecture Decisions (架構決策紀錄)

1. **同源邊緣防護罩取代客戶端跨域暴露原則 (Same-Origin Edge Shield over Client-Exposed Cloud Run)**:
   - *決策理由*：在前端 JS 檔案中暴露後端真實 `run.app` 網址會引發直接攻擊風險與複雜的跨域 Preflight 負擔。架構上確立客戶端瀏覽器一律發送同源 `/api/...` 請求，在 Cloudflare Anycast 邊緣由 Worker 辨識並無縫轉發，外部攻擊者無法直接探測真實後端位址。
2. **GFE 虛擬主機名牌動態覆寫原則 (GFE Virtual Host Dynamic Rewrite over $2,000/mo Cloudflare Enterprise Origin Rules)**:
   - *決策理由*：Google Cloud Run 門口的 GFE 路由器依賴 HTTP `Host` 標頭辨識目標容器服務。若未改寫 Host，自訂網域名牌會被 GFE 直接以 404 退件。Cloudflare 官方的 Origin Rules (Host Header Override) 被鎖在每月 2,000 美元的 Enterprise 方案中；架構決策利用免費的 Cloudflare Worker 在 `fetch()` 時動態重寫 `headers.set("Host", cloudRunHost)`，實現零成本完美的 Anycast 邊緣轉發。
3. **Vercel 本地路由邊緣旁路白名單原則 (Vercel Native Route Edge Bypass Whitelist)**:
   - *決策理由*：專案架構中存在部分原生運行於 Vercel 的輕量 Serverless API（如 `/api/sign-cloudinary` 與 `/api/parse-receipt`）。若無差別將全量 `/api/*` 轉往 Google Cloud Run，會引發 Cloud Run 404 報錯。Worker 必須建立精準的白名單規則，遇到特定路由直接直通 Vercel 原生源站。
4. **PWA 本地資料沙箱雙軌共存原則 (Dual-Active PWA Storage Preservation over Forced Redirect)**:
   - *決策理由*：瀏覽器 Local-First 存儲（IndexedDB / Cache Storage）受限於同源策略（Same-Origin Policy）。若在新域名上線時對舊域名執行 308 永久轉址，已將 App 加入手機桌面的老使用者在開啟時會被強制重定向至新域名，導致歷史自訂行程無法讀取。決策確立舊域名保持運作，維持雙軌共存與資料安全。
5. **多態 API Host 衍生與尾部斜線防禦架構 (Polymorphic API Host Derivation & Defensive Slash Sanitization)**:
   - *決策理由*：環境變數可能由不同維運人員配置帶有尾部斜線（例如 `https://api.com/`）或不帶斜線。直接拼接 `${apiHost}/api/xxx` 會產生非標準的雙斜線（`//api/xxx`），在部分反向代理下會被解析為通訊協定相對路徑而引發致命錯誤。架構規範：`getApiHost()` 一律經由正則清洗尾部斜線，確保路徑拼接絕對冪等。
6. **規格文件領域驅動拓撲化原則 (Domain-Driven Specification Hierarchy over Flat Spec Dumping)**:
   - *決策理由*：隨著專案快速擴展，平鋪於單一目錄下的規格檔案已超過 20 份，難以維護與檢索。全面重構為 6 大領域目錄（AI, 商業, 核心架構, 基礎設施, 搜尋, UI動效），並建立帶狀態徽章與對應代碼連結的 README 總覽矩陣。
7. **多網域圖片邊緣代理全源放行與 CORS 注入標準 (Multi-Origin Media Proxy & CORS Injection)**:
   - *決策理由*：反向代理 Worker 在實施防盜鏈檢查時，嚴禁單一寫死舊版 Vercel 網域。在新主域名啟用後，必須動態支援多來源比對，並兼容手機 PWA 獨立視窗下不帶 Referer 的情境；同時必須為所有圖片響應注入 `Access-Control-Allow-Origin: *`，防止 Canvas Tainted 污染破壞 PDF 行程表匯出功能。

---

## 🔴 3. Technical Debt (技術債與待辦事項)

1. **Cloudflare Worker 代理金鑰強制校驗 (`x-tabidachi-key`)**：
   - 目前 Worker 向 Cloud Run 轉發請求時尚未強制要求雙向 Secret 金鑰驗證。未來若遭遇惡意流量掃描，可於 Worker 與 Cloud Run 同步配置預共享金鑰（Pre-Shared Secret）進行標頭校驗阻斷。
2. **Supabase 身份驗證回調網址更新（待帳號體系啟動時排程）**：
   - 目前 Tabidachi 全面採用訪客匿名認證（`user_uuid` 本地儲存於 IndexedDB），無需 OAuth 流程。後續若開發第三方社群帳號登入功能，需將 `https://www.tabijiapp.com/auth/callback` 加入 Supabase Redirect URLs 白名單。
3. **前端搜尋 L1 RAM 快取容量上限與 LRU 驅逐**：
   - `frontend/lib/search-cache.ts` 目前未設 `MAX_L1_ITEMS` 上限，長期會話存在微量記憶體洩漏風險，後續可規劃導入 LRU 淘汰機制。
4. **離線照片二進位本機暫存隊列 (Offline Photo Blob Persistence)**：
   - 目前離線隊列對 `FormData`（如現場收據拍照上傳）採取跳過並彈出 Toast 提示的保守策略。未來需支援將照片轉為 IndexedDB Blob 本機排程隊列，待連網時自動重播二進位上傳。
5. **iOS Safari 斷網重連主動重播隊列 (BackgroundSync Safari Fallback)**：
   - iOS Safari 原生不支援 W3C Background Sync API，目前依賴 Service Worker 被動重啟。後續可評估在 `SyncManager` 前端組件中監聽 `window.addEventListener('online')` 作為主動觸發保險。

---

## 🛡️ 4. Failed Paths (踩坑與排除記錄)

1. **直連 Cloud Run 觸發 Google Front End (GFE) 404 陷阱 (`GFE Host Header Mismatch 404 Trap`)**：
   - *現象*：在 Cloudflare 設定 CNAME 直接指向 Cloud Run 網址，瀏覽器請求 `https://tabijiapp.com/api/health` 瞬間返回 Google 原生 404 錯誤頁面，FastAPI 後端無任何存取日誌。
   - *根因*：Google Cloud Run 的 GFE 多租戶負載均衡器依賴 HTTP `Host` 標頭識別目標服務容器。當請求的 Host 為 `tabijiapp.com` 時，GFE 查無此租戶直接予以退件。
   - *修復*：部署 Cloudflare Worker，在轉發前將 `request.headers` 的 `Host` 覆寫為 `antigravity-backend-589255638719.us-central1.run.app`，成功通過 GFE 路由。
2. **Cloudflare 免費版嘗試使用 Origin Rules 覆寫 Host 遭 $2,000/月 付費牆攔截 (`Cloudflare Origin Rules Enterprise Paywall Trap`)**：
   - *現象*：試圖在 Cloudflare 控制台 Rules > Origin Rules 中配置「Host Header Rewrite」規則將標頭改寫為 Cloud Run 網址，系統提示需要 Enterprise 方案才能啟用該欄位。
   - *根因*：Cloudflare 將進階標頭覆寫作為企業方案的收費功能，Free 與 Pro 方案無法直接使用 UI 規則覆寫 Host 標頭。
   - *修復*：捨棄靜態規則，改寫極簡 Cloudflare Worker（`fetch(url, { headers })`），以完全合規且零成本的邊緣無伺服器代碼解鎖 Host 覆寫。
3. **Cloudflare Worker 轉發 GET/HEAD 帶 body 觸發 TypeError 陷阱 (`Worker GET/HEAD Body TypeError Trap`)**：
   - *現象*：在邊緣轉發器中若無條件執行 `fetch(backendUrl, { method: request.method, body: request.body })`，當客戶端發起 GET 或 HEAD 請求時，V8 執行緒丟出 `TypeError: Request with GET/HEAD method cannot have body`。
   - *根因*：Fetch API 規範強制規定 GET 與 HEAD 請求的 `body` 屬性必須為 `null` 或 `undefined`。
   - *修復*：在 Worker 中嚴格過濾：`const body = (request.method !== "GET" && request.method !== "HEAD") ? request.body : undefined;`，徹底根絕運行時異常。
4. **暴力 308 重定向舊網域導致已安裝 PWA 本地資料歸零陷阱 (`Forced Domain Redirect PWA Storage Wipe Trap`)**：
   - *現象*：討論是否在 Vercel 將舊網域 `travel-pwa-five.vercel.app` 設置 308 轉址至新主網域。
   - *根因*：瀏覽器 Local-First 存儲機制以 Origin 作為唯一隔離邊界。轉址會迫使現有桌面快捷方式載入新域名，導致老使用者的 IndexedDB 與 LocalStorage 離線行程數據被隔離在舊 Origin 之下無法讀取，產生「更新後行程全沒了」的災難性用戶體驗。
   - *修復*：否決全域強制 308 重定向，保留舊網域作為副存活節點，透過伺服端同源代理維持其全功能運作。
5. **Vercel "Proxy Detected" 黃色警報引發的偽性焦慮陷阱 (`Vercel Proxy Detected False Panic Trap`)**：
   - *現象*：當 Cloudflare 開啟橘色雲朵（Proxied）後，Vercel 網域管理介面彈出黃色警告標籤 `"Proxy Detected: Some features may not work as expected"`。
   - *根因*：Vercel 的日常提醒提示其無法直接取得終端客戶端原始 IP，但 Vercel 底層已全面支援 `Verified Proxy Lite`，只要 Cloudflare 傳遞標準 `CF-Connecting-IP` 標頭，所有 CDN 快取與 SSR 功能完全正常運作。
   - *修復*：確認 Vercel Bot Protection 保持為預設或 Challenge 模式（不設為暴力 Deny），解除偽性焦慮並實測快取命中率與轉址速度。
6. **Cloudflare Worker 圖片防盜鏈寫死單一網域引發新網域破圖陷阱 (`Hardcoded Proxy Referer Whitelist 403 Trap`)**：
   - *現象*：使用者在新網域 `www.tabijiapp.com` 點擊「抓取街景」後，雖然跳出成功提示，但行程卡片相片破圖並瞬間隱藏；瀏覽器控制台爆發 13 次 `403 Forbidden`。
   - *根因*：`cloudinary-proxy` 邊緣 Worker 的防盜鏈白名單僅檢查 `travel-pwa-five.vercel.app` 與 `localhost`，將帶有 `Referer: https://www.tabijiapp.com/` 的請求全部以 403 阻斷。前端 `<Image onError>` 捕捉到錯誤後將卡片隱藏。
   - *修復*：擴充 Worker 白名單為多網域正則比對，相容 PWA Standalone 模式，實測雙網域加載成功率 100%。
7. **跨網域圖片缺乏 CORS 標頭引發 Canvas Tainted 污染與 PDF 匯出阻斷陷阱 (`Missing Proxy CORS Canvas Tainted Trap`)**：
   - *現象*：在進行行程 PDF 匯出時，`html2canvas` 在繪製 Cloudflare Worker 代理的圖片時偶發 `SecurityError: The operation is insecure`。
   - *根因*：`cloudinary-proxy` 原先僅回傳圖片串流，未顯式注入 `Access-Control-Allow-Origin: *`，導致瀏覽器 Canvas 在匯出時被標記為 Tainted（受污染）而拒絕輸出二進位資料。
   - *修復*：Worker 在回傳快取命中或遠端抓取的圖片時，一律透過 `cachedResponse.headers.set('Access-Control-Allow-Origin', '*')` 注入標頭，並支援 OPTIONS 204 Preflight。

---

## 🎯 Next Steps

1. **生產流量監控**：持續觀察 Cloudflare Analytics 與 Google Cloud Run Metrics，確認 `tabijiapp.com` 流量分佈、邊緣快取命中率與轉發延遲。
2. **PWA 安裝體驗驗證**：在 iOS Safari 與 Android Chrome 上透過新網域安裝 PWA，驗證 App 橫幅、離線冷啟動以及圖標完整性。
3. **推進技術債修復**：排程為 `search-cache.ts` 補齊 LRU 容量上限驅逐邏輯，持續優化行動端效能。

---

## 🎯 Next Steps

1. **生產流量監控**：持續觀察 Cloudflare Analytics 與 Google Cloud Run Metrics，確認 `tabijiapp.com` 流量分佈、邊緣快取命中率與轉發延遲。
2. **PWA 安裝體驗驗證**：在 iOS Safari 與 Android Chrome 上透過新網域安裝 PWA，驗證 App 橫幅、離線冷啟動以及圖標完整性。
3. **推進技術債修復**：排程為 `search-cache.ts` 補齊 LRU 容量上限驅逐邏輯，持續優化行動端效能。
