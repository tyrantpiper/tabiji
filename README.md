<p align="center">
  <img src="docs/screenshots/showcase/weather-itinerary.png" width="180" alt="Trip Master Overview & 5-Day Weather" />
  <img src="docs/screenshots/showcase/timeline-cards.png" width="180" alt="Timeline Spots & Continuous Calendar" />
  <img src="docs/screenshots/showcase/route-map.png" width="180" alt="Fullscreen Map & Multi-mode Route" />
  <img src="docs/screenshots/showcase/ai-chat.png" width="180" alt="AI Assistant & Batch POI Pickers" />
  <img src="docs/screenshots/showcase/expense-tracker.png" width="180" alt="Expense Tracker & Deep Link Highlight" />
</p>

<h1 align="center">Tabiji 旅路</h1>

<p align="center">
  <strong>Next-Generation Generative AI Travel Orchestrator</strong><br/>
  <strong>新一代生成式 AI 旅遊編排助手</strong>
</p>

<p align="center">
  <i>"Beyond Planning. Intelligent Journey Orchestration."</i><br/>
  <i>「超越規劃，開啟智慧旅程編排新境界。」</i>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Next.js-16.3-black?logo=next.js" />
  <img src="https://img.shields.io/badge/React-19.2-61DAFB?logo=react" />
  <img src="https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript" />
  <img src="https://img.shields.io/badge/Tailwind_CSS-v4.1-38B2AC?logo=tailwind-css" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi" />
  <img src="https://img.shields.io/badge/Gemini_3.7_Flash_&_Gemma-4285F4?logo=google" />
  <img src="https://img.shields.io/badge/Cloudflare-Edge_Shield-F38020?logo=cloudflare" />
  <img src="https://img.shields.io/badge/PWA-Installable-5A0FC8?logo=pwa" />
  <img src="https://img.shields.io/badge/License-PolyForm_Noncommercial_1.0.0-blue" />
</p>

<p align="center">
  <a href="https://tabijiapp.com/">🌐 Live Demo (tabijiapp.com)</a> •
  <a href="https://travel-pwa-five.vercel.app/">⚡ Vercel Mirror</a> •
  <a href="#-getting-started--快速開始">🚀 Getting Started</a> •
  <a href="#-features--功能特色">✨ Features</a> •
  <a href="#-tech-stack--技術棧">🏗️ Tech Stack</a> •
  <a href="docs/specs/README.md">📐 Architecture Specs</a> •
  <a href="#-judging-guide--評審導覽">🏆 Judging Guide</a>
</p>

---

| 🚀 創新亮點 | 💡 技術實作 | 🏆 評審價值 |
| :--- | :--- | :--- |
| **Same-Origin Edge Shield** | Cloudflare Anycast 邊緣反代 + GFE 標頭重寫 + 虛擬 GET 快取 | **企業級資安與零延遲**：完全隱匿 Cloud Run 原始網址，消除 CORS Preflight 150ms 延遲，熱門搜尋邊緣 0ms 直出。 |
| **3D DEM Terrain & Pitch Engine** | Mapterhorn Terrarium 高程解碼 + 30° 傾角運鏡動態掛載 | **極致視覺與效能平衡**：支援 1.2 倍真實地表起伏，平視自動卸載維持 60 FPS 絲滑手感，杜絕 GPU 顯存洩漏。 |
| **OSRM 3-Tier Resilient Routing** | Layer 1 記憶體 LRU 快取 (1.6ms) + 連線池 + Haversine 直線保底 | **永不中斷路網**：徹底除役付費 ArcGIS，重複查詢加速 200 倍，遇離島偏遠無路網自動優雅降級，後端永不拋 500。 |
| **Multi-Factor Top-K Geocoding** | 50% 字義 + 30% 有理衰減 $\frac{1}{1 + \text{dist}/150}$ + 權威度 + 國境加成 | **開源地理消歧義**：破解開源 Geocoder CJK 斷詞痛點，出發地機場與同名景點兼得，BBOX 換日線防禦。 |
| **Supabase Two-Pillar Keep-Alive** | Lifespan 獨立循環 ✕ 外部 UptimeRobot `/api/health/deep` 探針 | **零成本永久保活**：穿透 PostgREST 實體 SQL 查詢徹底破解 7 天休眠，搭配 60s 純記憶體防抖鎖杜絕連線池死鎖。 |
| **Agentic Deep Linking** | 全鏈路推播深層調度 + Virtuoso 穿透重置 + 3.5s 光暈尋址 | **零迷航落地**：推播點擊精準直達特定記帳項目或總覽儀表板，打破傳統 Web Push 跳轉首頁痛點。 |
| **Zero-Regression Rigor** | 雙重核驗 404 靜默自癒 + 370 項全維度自動化測試守門 | **軍規級品質保障**：後端 pytest 112/112 + 前端 vitest 258/258 全綠，防禦型架構守護專案無感自癒。 |

---

## ✨ Features / 功能特色

### 🤖 AI Travel Assistant / AI 旅遊助手
- **Neural-Link Extraction Pipeline** — 100% 格式對齊的精準資料提取，Agentic 能力的核心 / 結構化抽取引擎
- **Batch POI Recommendations** — 批次景點勾選推薦卡片 (`BatchPOIPreviewCard`)，一次將多個景點加入行程
- **Interactive UI Pickers** — 原生時鐘日曆選取器與對話流 Markdown 格式化渲染 / 豐富對話卡片
- **Multi-tier AI Routing** — Gemini 3.7 Flash 思考推論 + Gemma 4/3 多層級救援路由 / 多模型動態切換
- **Hyper-Contextual Injection** — 即時機票報價與 Sliding Window Context 脈絡注入 / 滑動視窗上下文管理
- **Itinerary Health Check** — AI reviews your daily plan and suggests improvements / AI 行程健檢
- **Smart Itinerary Editing** — 在對話中透過 Function Calling 智慧刪除或調整景點
- **Memory Engine** — Auto-summarizes long conversations to maintain context / 記憶壓縮引擎
- **BYOK (Bring Your Own Key)** — Your API key, your privacy / 自帶金鑰，隱私至上

### 🗺️ Interactive Maps / 互動地圖
- **Mapterhorn 3D DEM Terrain & Dynamic Pitch** — 開源全球 3D 地形高程（Terrarium 512px 解碼），相機傾角 $\ge 30^\circ$ 自動拉起 1.2 倍真實地貌，$\le 15^\circ$ 自動卸載歸零守護 60 FPS
- **OSRM 3-Tier Resilient Routing Engine** — Layer 1 記憶體 LRU 快取（1.6ms 瞬回，快 200 倍）、Layer 2 HTTPX 全域連線池、Layer 3 Haversine 大圓航線直線保底（遇無路網優雅降級灰色虛線，100% 零崩潰）
- **Multi-Factor Top-K Geocoding Reranker** — 多元加權重排演算法（50% CJK 字義 + 30% 有理空間衰減 + 10% 權威重要度 + 10% 目標國加分），換日線 BBOX 拓撲防禦
- **3D Cinematic Tour Engine & VisionOS HUD** — 60° 俯衝大圓航線低空巡航導覽、景點 360° 自動盤旋與 Apple VisionOS 曜黑晶透懸浮面板
- **Mapillary Global Street View** — 整合式 360 度真實街景沉浸式探索，隨時預覽實體地標外觀
- **MapLibre GL & CSP Pipeline** — Web Worker 同源靜態管線，符合最嚴格 CSP 安全防護標準
- **3D Buildings & Satellite View** — 支援 3D 建築視圖、Esri 高清衛星空拍圖與 OpenFreeMap 向量街道切換
- **Edge POST-to-GET Virtual Cache** — Cloudflare Anycast 邊緣快取適配，熱門地理搜尋 0ms 跨洲直出
- **L1 Local Instant Search** — Offline-capable MiniSearch for stations & landmarks / 本地即時搜尋（離線可用）
- **L2 5-Source POI Fusion Engine** — OSM, OpenTripMap, WikiVoyage, Wikipedia, Wikidata 聚合 / 五源 POI 聚合引擎
- **Fullscreen Map** with cross-platform long-press and red-pin precision / 全螢幕地圖與長按選址互動

### 📅 Trip & Booking Management / 行程與訂房管理
- **Trip Master Overview (Day 0)** — 全景行程總覽封面卡片、關鍵天數概覽與統計儀表板
- **DailyWeatherStrip (5-Day Weather)** — 橫向動態氣象預報帶，即時監控氣溫與晴雨降水機率
- **Smart Currency & Country Inference** — 依目的地名稱智慧推算國碼與預設法定貨幣（如日本 ➔ JPY）
- **Continuous Multi-Month Calendar** — iOS Swift 風格連續縱向多月份雙向滾動日曆區間選擇器
- **Affiliate Booking Center** — 內建 21+ 旅遊平台 (Agoda 等) 註冊與智慧推薦 / 全域導購中心
- **Drag & Drop Reorder** — Powered by dnd-kit / 拖拉排序
- **Multi-segment Flight Tracking** — 支援多航段與獨立去回程新增 / 智能航班管理
- **Multi-trip Switcher** — Manage multiple trips with real-time collaboration / 多行程切換 + 即時協作
- **Daily Checklist & AI Tips** — Pack lists, tickets, and curated destination guides / 每日清單與智慧旅遊指南
- **ISR Public Sharing** — Share itineraries via link (no login required) / 公開分享（免登入）

### 💰 Expense Tracker & Deep Linking / 記帳工具與深層連結
- **Agentic Deep Linking Engine** — 點擊推播直達指定記帳項目，虛擬列表穿透尋址與 3.5 秒翠綠發光定位
- **110+ Official Sovereign Fiat Currencies** — 支援全球 110+ 種官方 ISO 4217 法定貨幣白名單，純淨過濾加密貨幣
- **Real-time Exchange Rates** — Auto-convert to your home currency / 即時匯率換算
- **Category Analytics** — Interactive pie charts and daily/total views / 分類統計與圓餅圖表
- **Receipt Photo Upload & AI Parse** — Cloudinary 整合收據存證與 AI 圖片自動拆分 (Subtotal, Tax, Tip)
- **Shared & Private Ledgers** — Split expenses with travel buddies / 公帳私帳分離

### 🔐 Privacy & Security / 隱私安全
- **BYOK Model** — AI keys stored locally, never on server / 金鑰僅存本地
- **GDPR Compliance** — Data export & deletion via API / GDPR 資料匯出/刪除
- **Anonymous Recovery Keys** — No email or phone required / 匿名恢復金鑰
- **Rate Limiting** — SlowAPI protection / 速率限制保護

### 📱 PWA & UX
- **Installable PWA** — Works on iOS, Android, and Desktop / 可安裝到主畫面
- **Real-time Push Notifications** — 實時推播、倒數提醒與共同編輯廣播 / PWA 推播引擎
- **Offline-First Instant Boot** — 本地 L1 快取 + L2 IndexedDB 存儲與 Serwist 離線引擎，無網路依然秒開並自動背景樂觀同步
- **Integrated Navigation Hub** — 懸浮藥丸式 (Floating pill) 底部導覽列與雙擊刷新 / 整合式導航中樞
- **Dark Mode** — System-aware theme switching / 深色模式
- **Bilingual** — Traditional Chinese & English / 繁體中文 + 英文
- **Haptic Feedback** — Native-like touch responses / 全系統觸覺回饋
- **PDF Export** — Generate printable itinerary PDFs / PDF 匯出

### 🛡️ Architecture & DevOps / 架構與維運
- **Same-Origin Edge Shield** — 同源邊緣防護罩架構，客戶端使用相對路徑 `/api/*`，由 Cloudflare Worker 動態代理並覆寫 GFE Host，徹底隱匿後端 Cloud Run 地址
- **Supabase Two-Pillar Keep-Alive** — Lifespan 背景非同步循環 ✕ 外部 UptimeRobot `/api/health/deep` 深度探針，60s 純記憶體防抖鎖，徹底解決 7 天休眠
- **Cloudflare 100s SSE Streaming Keep-Alive** — 10s `: keep-alive` 心跳封包重置邊緣逾時讀取計時器，`Cache-Control: no-transform` 穿透邊緣緩衝
- **Double-Checked 404 Self-Healing** — 雙重核驗死行程自癒防線，網路抖動不誤判、幽靈快取 300ms 內秒級靜默自癒
- **370 Full-Dimension Automated Tests** — 後端 pytest 112 項 + 前端 vitest 258 項全綠通過，杜絕狀態死鎖與迴歸
- **Domain-Driven Spec Architecture** — 25+ 份系統架構規格書（`docs/specs/`），涵蓋 AI、搜尋、PWA、動效與基礎設施
- **Autonomous Agent Ecosystem** — `.agents` L0-L3 工作流與多角色 (@dev, @qa, @security) 自動化治理
- **Enterprise-grade Security** — MapLibre CSP Worker Pipeline、Security Sentinel 本地沙盒對抗審計與 Anti-SSRF
- **Observability** — Prometheus Metrics 與 `/api/health/deep` 雙模健康檢查 / 系統可觀測性監控

---

## 🏗️ Tech Stack / 技術棧

### Frontend

| Technology | Version | Purpose |
|-----------|---------|---------|
| Next.js | 16.3 | Framework (App Router, ISR, Turbopack) |
| React | 19.2 | UI with React Compiler |
| TypeScript | 5.9 | Type safety |
| MapLibre GL | 6.9 | Maps (3D DEM Terrain, Terrarium, Esri satellite, static CSP worker) |
| Zustand | 5.0 | State management (Single source of truth) |
| SWR | 2.3 | Data fetching & caching |
| Framer Motion | 12.x | Animations |
| dnd-kit | 6.3 | Drag and drop |
| Tailwind CSS | 4.1 | Modern styling tokens |
| Radix UI | Latest | Accessible primitives |

### Backend

| Technology | Version | Purpose |
|-----------|---------|---------|
| FastAPI | Latest | REST API framework |
| Supabase | Latest | PostgreSQL database + Realtime (7-Day Keep-Alive) |
| OSRM (FOSSGIS) | v5 API | 3-Tier Resilient Routing Engine (1.6ms LRU + Connection Pool) |
| Gemini 3.7 & Gemma | Latest | Multi-model routing, POI enrichment, itinerary synthesis |
| Prometheus Client | Latest | System observability and metrics |
| HTTPX | Latest | Async HTTP client with connection pooling & Anti-SSRF |
| SlowAPI | 0.1.9+ | Rate limiting |
| RapidFuzz | 3.6+ | Fuzzy string matching & Top-K scoring |

### Infrastructure

| Service | Purpose |
|---------|---------|
| Cloudflare Workers | Edge Shield (Host rewrite, Anycast proxy, POST-to-GET virtual cache) |
| Vercel | Frontend hosting (Edge, ISR, `tabijiapp.com` CNAME binding) |
| Google Cloud Run | Backend hosting (Docker, hidden origin) |
| Supabase | PostgreSQL Database + Auth + Realtime |
| Cloudinary | Image hosting (receipts, avatars) |

---

## 📐 Technical Architecture / 系統架構圖

```mermaid
flowchart TB
    subgraph Tier1["🌐 邊緣防護與客戶端 (Client & Edge Shield)"]
        PWA["📱 PWA 旅人端 (Next.js 16 / Serwist 離線快取)"]
        CF["⚡ Cloudflare Anycast 邊緣盾 (worker.js)<br/>• 隱匿 Cloud Run 網址 • 零 CORS 延遲 • POST-to-GET 虛擬快取"]
        PWA <-->|同源相對路徑 /api/*| CF
    end

    subgraph Tier2["⚙️ AI 編排與後端核心 (Google Cloud Run / FastAPI)"]
        Router["Smart Router & Intent Classifier"]
        TopK["Top-K Geocoding & Speculative Engine"]
        RouteLRU["OSRM 1.6ms 記憶體 LRU 路線快取"]
        KeepAlive["Supabase 雙柱保活與 60s 防抖健康鎖"]
        CF <-->|邊緣轉發 (覆寫 GFE Host)| Router
        Router --> TopK
        Router --> RouteLRU
        Router --> KeepAlive
    end

    subgraph Tier3["☁️ 雲端智慧與開源圖資服務 (Cloud Services & Map Engines)"]
        AI["🧠 Gemini 3.7 Flash / Gemma 4 (BYOK)"]
        OSRM["🚗 OSRM (FOSSGIS) 官方路網引擎"]
        DEM["🏔️ Mapterhorn 3D DEM 地形 (Terrarium)"]
        DB[("🐘 Supabase PostgreSQL (PostgREST)")]
        CDN["🖼️ Cloudinary (媒體存證)"]
        
        Router <--> AI
        RouteLRU <--> OSRM
        KeepAlive <--> DB
        PWA <--> DEM
    end
```

---

## 🚀 Getting Started / 快速開始

### Prerequisites / 前置需求

- **Node.js** 18+
- **Python** 3.11+
- **Supabase** account (free tier works / 免費方案即可)
- **Gemini API Key** ([Get one free / 免費取得](https://aistudio.google.com/apikey))

### Backend Setup / 後端設定

```bash
# 1. Navigate to backend / 進入後端目錄
cd backend

# 2. Create virtual environment / 建立虛擬環境
python -m venv .venv
.venv\Scripts\activate    # Windows
# source .venv/bin/activate  # macOS/Linux

# 3. Install dependencies / 安裝依賴
pip install -r requirements.txt

# 4. Configure environment / 設定環境變數
cp .env.example .env
# Edit .env with your values (see table below)
# 編輯 .env 填入你的設定值（見下方表格）

# 5. Start server / 啟動伺服器
uvicorn main:app --reload --port 8000
```

### Frontend Setup / 前端設定

```bash
# 1. Navigate to frontend / 進入前端目錄
cd frontend

# 2. Install dependencies / 安裝依賴
npm install

# 3. Configure environment / 設定環境變數
cp .env.local.example .env.local
# Edit .env.local with your values
# 編輯 .env.local 填入你的設定值

# 4. Start dev server / 啟動開發伺服器
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) 🎉

### Testing / 測試 (Frontend)

本專案配置了完整的自動化測試守護流程（由 `@qa` Agent 監控）。

```bash
# 1. 執行 Vitest 單元測試
npm run test

# 2. 執行 Playwright E2E 迴歸測試
npx playwright test
```

---

## 🔑 Environment Variables / 環境變數

### Backend `.env`

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | ✅ | Supabase project URL |
| `SUPABASE_ANON_KEY` | ✅ | Supabase anonymous key |
| `TP_API_TOKEN` | Optional | Travelpayouts affiliate booking integration |

> [!TIP]
> 路線計算全面由免費開源的 **OSRM (FOSSGIS)** 與內建 1.6ms LRU 快取接管，**不再需要任何 ArcGIS API Key**。

### Frontend `.env.local`

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Optional | 本地開發覆寫後端網址（生產環境由 Cloudflare 邊緣盾自動接管同源 `/api/*`，無需設定） |
| `NEXT_PUBLIC_SUPABASE_URL` | ✅ | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | ✅ | Supabase anonymous key |
| `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME` | Optional | Cloudinary cloud name (for image uploads) |

> [!NOTE]
> **Gemini API Key** is configured by each user in the app's Profile page (BYOK model).
> No server-side AI key is needed.
>
> **Gemini API Key** 由使用者在 App 的 Profile 頁面自行設定（BYOK 模式），伺服器端不需要 AI 金鑰。

---

## 🗄️ Database / 資料庫

This project uses **Supabase** (PostgreSQL) with 20+ migration files for schema management.

本專案使用 **Supabase** (PostgreSQL)，含 20+ 個 migration 檔管理資料庫結構。

```bash
# Apply migrations / 套用 migration
cd backend/migrations
# Run SQL files in order against your Supabase project
# 依序在 Supabase 專案中執行 SQL 檔案
```

---

## 🚢 Deployment / 部署

### Frontend → Vercel

```bash
# Connect your GitHub repo to Vercel
# Set environment variables in Vercel dashboard
# Automatic deployments on push to main
```

### Backend → Google Cloud Run

```bash
# Build and push Docker image / 建置並推送 Docker 映像
docker build -f Dockerfile.prod -t gcr.io/PROJECT_ID/tabidachi-backend .
docker push gcr.io/PROJECT_ID/tabidachi-backend

# Deploy / 部署
gcloud run deploy tabidachi-backend \
  --image gcr.io/PROJECT_ID/tabidachi-backend \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

---

## 📱 PWA Installation / PWA 安裝

| Platform | How to Install |
|----------|---------------|
| **iOS Safari** | Tap Share → "Add to Home Screen" / 分享 → 加入主畫面 |
| **Android Chrome** | Tap "Install App" banner or Menu → "Install" / 點擊安裝橫幅 |
| **Desktop Chrome** | Click install icon in address bar / 點擊網址列安裝圖示 |

---

## 📄 License & Intellectual Property

- **Software Code**: Licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE).
- **Historical Releases**: Releases up to Git Tag `v1.0.0-mit-final` remain under the MIT License (see [NOTICE.md](NOTICE.md)).
- **Visual & Brand Assets**: "Backpack Traveler" illustrations, splash screen artwork, and logos are proprietary under [All Rights Reserved](frontend/public/LICENSE-ASSETS.md). Please refer to [TRADEMARK.md](TRADEMARK.md) for brand usage guidelines.

---

<p align="center">
  Made with ❤️ by Ryan Su
</p>

---

## 🏆 Judging Guide / 評審導覽

如果您是競賽評審或技術審查者，我們建議您重點關注以下最能展現專案技術深度、架構韌性與創新落地的核心環節：

1. **同源邊緣盾牌與 0ms 虛擬快取 (Same-Origin Edge Shield & Virtual Cache)**：體驗 `https://tabijiapp.com/`，前端所有呼叫皆為同源相對路徑 `/api/*`，透過 Cloudflare Worker 覆寫 GFE Host 隱匿 Cloud Run 網址，徹底消除 CORS 延遲；`/api/geocode/search` 透過 POST-to-GET 虛擬適配器實現邊緣 0ms 快取直出。
2. **Mapterhorn 3D DEM 地形與 OSRM 零崩潰路網 (3D DEM & OSRM Routing Engine)**：在全景地圖中傾斜相機至 $\ge 30^\circ$，自動升起 1.2 倍真實 3D 地貌起伏；路線規劃由 OSRM 3-Tier 引擎驅動，Layer 1 記憶體 LRU 快取二次查詢僅需 1.6ms，遇偏遠或無路網自動優雅降級為 Haversine 直線虛線，達成 100% 零崩潰。
3. **AI 批次推薦與原生互動選取器 (Batch POI & Interactive UI)**：在 AI 對話中請求景點推薦，體驗 `BatchPOIPreviewCard` 勾選批次加入，以及調整時間時的原生手感日曆時鐘選取器，告別純文字 Chatbot，對話直接驅動原生 UI。
4. **全景行程總覽與 5 日動態氣象帶 (Trip Master Overview & Weather Strip)**：點擊行程頂部「ALL / 總覽」，檢視完整行程封面卡片、橫向 5 日氣溫晴雨預報帶，以及緊湊優雅的「詳情 →」跳轉按鈕，體驗多維度的資訊編排層次。
5. **全鏈路推播與深層尋址定位 (Agentic Deep Linking & Glow Highlight)**：體驗網址直接帶有深層參數（如 `?tab=tools&expense_id=...`），系統自動完成分頁切換、穿透重置長清單篩選器、調用 Virtuoso 虛擬滾動平滑定位，並附帶 3.5 秒翠綠發光定位動畫。
6. **370 項全維度測試與雙重核驗自癒 (Zero-Regression & Self-Healing)**：專案具備後端 112 項 pytest 與前端 258 項 vitest **共 370 項全量自動化測試守護**，以及 SWR 404 雙重核驗靜默自癒與 Supabase 雙柱 7 天防休眠保活，展現頂級全端工程的極致韌性。

---
