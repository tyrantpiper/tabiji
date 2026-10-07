# 📐 Tabidachi 系統架構規格全景地圖 (System Specification Matrix)

> **定位守則 (Master Doctrine)**:  
> 本目錄採用 **Domain-Driven (領域驅動)** 組織架構，收錄 Tabidachi 旅遊 PWA 全棧各業務與技術核心的工程規格書（Mini Design Docs）。  
> 任何跨越單一檔案或涉及核心邏輯重構之功能，均須依據 `/Idea to Spec` 規範於此落地規格，經審查核准後方可實作。

---

## 🗂️ 領域分類拓撲 (Domain Topology)

```
docs/specs/
├── README.md                                 # [總中樞] 本全景導航矩陣與架構地圖
├── ai/                                       # 🧠 AI 智能助手、人物態、時間感知與工具呼叫
├── search/                                   # 🔍 搜尋引擎、區域詞庫、邊緣代理與 Grounding
├── offline-pwa/                              # 📶 離線優先秒開、Service Worker 與 Web Push
├── ui-motion/                                # ✨ UI 介面、液態玻璃材質與微動效呼吸
├── business/                                 # 💼 商業記帳、交通比價與聯盟行銷跳轉
├── infra/                                    # 🛠️ 基礎設施、Git 規範與架構演進 Backlog
└── archive/                                  # 📦 歷史過期或已被取代之規格
```

---

## 📋 規格矩陣總表 (Full Specification Matrix)

### 1. 🧠 AI 智能與意圖模組 (`ai/`)

| 規格檔案 | 現行狀態 | 核心業務與架構摘要 | 主要對應代碼位置 |
| :--- | :---: | :--- | :--- |
| [**`ai-model-strategy-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/ai/ai-model-strategy-spec.md) | 🟢 Active | Gemini 2.5 Flash / Flash Lite 雙模動態切換、意圖路由與 Token 成本優化。 | `backend/services/intent_router.py`<br>`backend/services/model_manager.py` |
| [**`ryan-ai-companion-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/ai/ryan-ai-companion-spec.md) | 🟢 Active | 打造專業醫學背景＋全端旅遊助理 Ryan 之專屬人物態、語氣規範與陪伴心智。 | `backend/services/model_manager.py`<br>`frontend/components/chat-widget.tsx` |
| [**`realtime-temporal-awareness-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/ai/realtime-temporal-awareness-spec.md) | 🟢 Active | 端側時間解析、相對時差天數計算、行程生命週期狀態機 (`PLANNING`~`POST_TRIP`)。 | `backend/services/temporal_service.py`<br>`backend/main.py` |
| [**`parallel-tooling-and-temporal-constants-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/ai/parallel-tooling-and-temporal-constants-spec.md) | 🟢 Active | 後端伺服端工具 (`get_world_time`) 與客戶端業務工具分離、時間常數統一。 | `backend/main.py`<br>`backend/services/model_manager.py` |
| [**`sse-streaming-keepalive-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/ai/sse-streaming-keepalive-spec.md) | 🟢 Active | Cloudflare 100s 超時防衛、SSE 串流 10s 心跳保活與跨 Chunk 累加器。 | `backend/routers/ai.py`<br>`cloudflare/edge-shield/worker.js` |

---

### 2. 🔍 搜尋與邊緣運算 (`search/`)

| 規格檔案 | 現行狀態 | 核心業務與架構摘要 | 主要對應代碼位置 |
| :--- | :---: | :--- | :--- |
| [**`ddgs-multi-engine-and-query-slimming-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/search/ddgs-multi-engine-and-query-slimming-spec.md) | 🟢 Active | DDGS 8 引擎並發非同步檢索、排除百科動漫洗版、Tier 1 5.2s 黃金超時校準。 | `backend/services/web_search_engine.py` |
| [**`global-local-search-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/search/global-local-search-spec.md) | 🟢 Active | 4-Tier 容錯搜尋管線、AC-2 雜訊過濾黑名單、AC-4 嚴格 1對1 引文剪裁對齊演算法。 | `backend/services/web_search_engine.py`<br>`frontend/components/chat/SourceCitation.tsx` |
| [**`global-search-taxonomy-and-region-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/search/global-search-taxonomy-and-region-spec.md) | 🟢 Active | 全球 9 大區域詞庫大瘦身（拔除破壞性 `OR` 運算符）、動態雙軌 Region 分流。 | `backend/services/destination_taxonomy.py` |
| [**`cloudflare-edge-and-wrangler-master-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/search/cloudflare-edge-and-wrangler-master-spec.md) | 🟢 Active | Cloudflare 邊緣檢索執行器（雙通道競速、DDG Lite 快速熔斷、Wikipedia 全文）。 | `cloudflare/search-proxy/worker.js`<br>`cloudflare/search-proxy/wrangler.jsonc` |
| [**`multi-factor-top-k-rerank-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/search/multi-factor-top-k-rerank-spec.md) | 🟢 Active | 多元加權 Top-K 重排演算法（50% 字義 + 30% 有理空間衰減 + 10% 權威度 + 10% 國境加成）。 | `backend/services/geocode_service.py` |

---

### 3. 📶 離線架構與 PWA (`offline-pwa/`)

| 規格檔案 | 現行狀態 | 核心業務與架構摘要 | 主要對應代碼位置 |
| :--- | :---: | :--- | :--- |
| [**`offline-first-instant-boot-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/offline-pwa/offline-first-instant-boot-spec.md) | 🟢 Active | 輕量化 Local-First 離線優先架構、Serwist SW 快取策略、L2 IndexedDB 持久化。 | `frontend/app/sw.ts`<br>`frontend/lib/idb-storage.ts` |
| [**`offline-instant-boot-hardened-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/offline-pwa/offline-instant-boot-hardened-spec.md) | 🟢 Active | 根治 iOS Standalone PWA 斷網重啟白屏、esbuild NODE_ENV 生產打包穿透防禦。 | `frontend/app/sw.ts`<br>`frontend/app/sw.js/route.ts` |
| [**`web-push-notification-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/offline-pwa/web-push-notification-spec.md) | 🟢 Active | Web Push 雙向推播架構、Service Worker 喚醒既有 Client、推播權限同理心引導。 | `frontend/hooks/use-push-notifications.ts`<br>`backend/routers/notifications.py` |

---

### 4. ✨ 前端介面與動效 (`ui-motion/`)

| 規格檔案 | 現行狀態 | 核心業務與架構摘要 | 主要對應代碼位置 |
| :--- | :---: | :--- | :--- |
| [**`fullwidth-card-top-pill-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/ui-motion/fullwidth-card-top-pill-spec.md) | 🟢 Active | 行程卡牌 100% 滿版擴展、頂部時序膠囊收攏、徹底拔除橫滑刪除誤觸。 | `frontend/components/timeline-card.tsx`<br>`frontend/components/itinerary/SortableTimelineCard.tsx` |
| [**`timeline-phase2-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/ui-motion/timeline-phase2-spec.md) | 🟢 Active | 時間軸二期架構：Transit 轉乘動態線條、5s 延遲安全撤銷刪除、卡片聚焦地圖。 | `frontend/components/itinerary/TransitSegmentConnector.tsx`<br>`frontend/lib/undo-delete-manager.ts` |
| [**`idle-breathing-opacity-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/ui-motion/idle-breathing-opacity-spec.md) | 🟢 Active | 天數導航列與地圖膠囊 2.5s 靜止呼吸微降敏 (20% dimming)、150ms 瞬態喚醒。 | `frontend/lib/hooks/useIdleBreathing.ts`<br>`frontend/components/itinerary/FloatingMapCapsule.tsx` |
| [**`ios-weather-bento-grid-architecture-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/ui-motion/ios-weather-bento-grid-architecture-spec.md) | 🟢 Active | iOS 天氣 Bento Grid、OKLCH 色溫光譜插值、24h Scrubber、ECMWF 徽章。 | `frontend/components/weather/WeatherPanel.tsx`<br>`frontend/lib/weather.ts` |
| [**`ios-expandable-itinerary-sections-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/ui-motion/ios-expandable-itinerary-sections-spec.md) | 🟢 Active | 4 合 1 每日智慧看板 (ItineraryDashboardHub) ✕ 物理彈簧底抽 (IOSBottomSheet)。 | `frontend/components/itinerary/ItineraryDashboardHub.tsx`<br>`frontend/components/ui/IOSBottomSheet.tsx` |
| [**`ios-inset-grouped-form-research.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/ui-motion/ios-inset-grouped-form-research.md) | 🟢 Active | iOS Inset Grouped 表單分組設計規範、活動編輯彈窗現代化。 | `frontend/components/itinerary/ActivityEditModal.tsx` |
| [**`memo-and-vip-refactor-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/ui-motion/memo-and-vip-refactor-spec.md) | 🟢 Active | 行程卡片在地備忘與星標 VIP 視覺階層重構、圖示與排版優雅降級。 | `frontend/components/timeline-card.tsx` |
| [**`sticky-days-and-map-focus-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/ui-motion/sticky-days-and-map-focus-spec.md) | 🟢 Active | 天數導航 Sticky Blur 玻璃吸頂與單日地圖點擊聯動聚焦 (FlyTo)。 | `frontend/components/itinerary/ItineraryHeader.tsx`<br>`frontend/components/day-map.tsx` |
| [**`location-search-funnel-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/ui-motion/location-search-funnel-spec.md) | 🟢 Active | 景點位置搜尋漏斗最佳化、防抖與錯誤提示處理。 | `frontend/components/itinerary/ActivityEditModal.tsx` |
| [**`ios-liquid-glass-chat-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/ui-motion/ios-liquid-glass-chat-spec.md) | 🟢 Active | iOS 26 液態玻璃材質、純 CSS Inset 陰影、觸控手勢 80ms 延遲釋放與無損 UI。 | `frontend/components/chat-widget.tsx`<br>`frontend/components/chat/*` |
| [**`living-motion-and-idle-dimming-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/ui-motion/living-motion-and-idle-dimming-spec.md) | 🟢 Active | 地圖控制膠囊 (MapControlCapsule) 3 秒平滑降至 25% 晶透幽靈態、防手震狀態機。 | `frontend/components/map/MapControlCapsule.tsx`<br>`frontend/components/map/day-map.tsx` |

---

### 5. 💼 旅遊業務與商業化 (`business/`)

| 規格檔案 | 現行狀態 | 核心業務與架構摘要 | 主要對應代碼位置 |
| :--- | :---: | :--- | :--- |
| [**`currency-and-multi-fiat-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/business/currency-and-multi-fiat-spec.md) | 🟢 Active | 110+ 主權法定貨幣支援、確定性 ISO 4217 映射、本地多層 SVG 國旗防破圖。 | `frontend/lib/currency.ts`<br>`frontend/components/expense/ExpenseDialog.tsx` |
| [**`flight-pricing-and-airport-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/business/flight-pricing-and-airport-spec.md) | 🟢 Active | 同城起降 0ms 記憶體短路防衛、全台與全球主要機場三字碼 IATA 解析。 | `frontend/lib/airport-mapping.ts`<br>`backend/services/flight_service.py` |
| [**`universal-affiliate-interactive-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/business/universal-affiliate-interactive-spec.md) | 🟢 Active | 12Go Asia 官方直連加盟帶參規範、分潤 Cookie 寫入、交通比價跳轉閉環。 | `frontend/lib/affiliate.ts`<br>`frontend/components/transport/TransportCard.tsx` |

---

### 6. 🛠️ 基礎設施與維運 (`infra/`)

| 規格檔案 | 現行狀態 | 核心業務與架構摘要 | 主要對應代碼位置 |
| :--- | :---: | :--- | :--- |
| [**`same-origin-edge-shield-architecture-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/infra/same-origin-edge-shield-architecture-spec.md) | 🟢 Active | 同源邊緣防護罩、隱匿 Cloud Run 網址、零 CORS Preflight 與 POST-to-GET 虛擬快取。 | `cloudflare/edge-shield/worker.js`<br>`frontend/lib/api.ts` |
| [**`tabijiapp-cloudflare-setup-sop-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/infra/tabijiapp-cloudflare-setup-sop-spec.md) | 🟢 Active | tabijiapp.com 零缺陷生產級部署 SOP、灰雲/橘雲平滑過渡與雙軌網域存活。 | Cloudflare DNS<br>Vercel 網域配置 |
| [**`supabase-keepalive-architecture-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/infra/supabase-keepalive-architecture-spec.md) | 🟢 Active | Supabase 7 天防休眠雙柱保活架構、PostgREST 實體穿透與 60s 防抖鎖。 | `backend/main.py` (Lifespan & `/health/deep`) |
| [**`git-identity-and-history-reconciliation-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/infra/git-identity-and-history-reconciliation-spec.md) | 🟢 Active | 去中心化 Git 身分防偽、官方 ID 錨定隱私信箱標準、全量 DAG Bundle 獨立備份。 | `~/.gitconfig`<br>Git Commit 規範 |
| [**`architecture-evolution-backlog-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/infra/architecture-evolution-backlog-spec.md) | 📋 Backlog | 全專案架構演進路線圖、技術債追蹤與未來大版本里程碑清單。 | 全專案架構規劃 |

---

### 7. 📦 歷史封存規格 (`archive/`)

| 規格檔案 | 封存原因 | 取代規格 / 處置說明 |
| :--- | :--- | :--- |
| [**`overview-weather-coldstart-spec.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/archive/overview-weather-coldstart-spec.md) | 舊版氣象冷啟動方案已完全被 SWR 持久化與雙層快取淘汰。 | 已由 `offline-first-instant-boot-spec.md` 取代。 |

---

## 📝 新增規格指南 (Contribution & Naming Convention)

1. **命名規範**：採用小寫字母搭配連字號，格式為 `<domain-feature>-spec.md`（例如 `ai-voice-interaction-spec.md`）。
2. **目錄歸屬**：請嚴格依據 6 大業務領域放置於對應子目錄中，禁止直接放置於 `docs/specs/` 根目錄。
3. **結構標準**：必須遵循 `/Idea to Spec` 模板，涵蓋：
   - 1. Problem Statement & Core Value (問題陳述與核心價值)
   - 2. User Journey & Core Flow (使用者旅程與操作流程)
   - 3. Architecture & Data Model (架構與資料模型)
   - 4. Edge Cases & Boundary Conditions (邊界條件與異常處理)
   - 5. Acceptance Criteria (驗收標準清單)
4. **索引同步**：新增規格完成後，必須同步更新本 `README.md` 對應領域表格與狀態標籤。
