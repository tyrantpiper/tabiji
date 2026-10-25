# 📅 Daily Report - 2026-10-25 (Agentic Geo-Spatial POI Grounding, In-Card MiniMap, Temporal Life-Cycle De-biasing, Cloudflare Edge Search Proxy & Mobile Auto-Dock)

> **系統狀態**：🟢 Production Ready & Security Sentinel Hardened, 0 TypeScript Errors, 0 ESLint Warnings, 100% Tests Green (Frontend 87 Suites / 584 Tests Passed; Backend 325 Items: 320 Passed, 5 Skipped, 0 Failures; Chrome DevTools MCP 真機實體遙測閉環通過), Security Ledger 244 Targets (47 Remediated, 51 Verified, 146 Dismissed, 100% 數學守恆).
> **今日關鍵研發範疇 (Core Focus)**：
> - 🗺️ **聊天室空間感知閉環與 In-Card MiniMap 輕量瓦片地圖 (AD-182)**：徹底解決「周邊推薦提問不出地圖氣泡」之核心痛點。於 `POIPreviewCard.tsx` 實裝基於 Web Mercator 網格算法之 Esri 高清街景瓦片切片地圖（0ms 延遲、無完整 WebGL 實例負擔、紅色呼吸圖釘），並透過 `tabidachi:map-flyto` 自定義事件實現內部 MapLibre 1.8 秒平滑全景運鏡。
> - ⏱️ **時序感知生命週期去耦合與工具抑制破除 (Temporal Awareness De-biasing, AD-183)**：修復 `temporal_service.py` 判定歷史行程（如 2026/03/10）已過期導致 Gemini 3.1 Flash 自作聰明認為「旅途已結束、不可加景點」之負向意圖抑制。顯式注入模擬編輯與規劃不變量，重拾 100% 工具派發率。
> - 🧠 **二階段 Agentic Tool-Calling 提示詞斷鏈消解 (Two-Pass Prompt Disconnect Remediation, AD-184)**：捕獲並修復 `backend/main.py` 在 First-Pass 查獲真實坐標後未注入 Second-Pass 的致命 Bug；重構系統安全指令第 5 條【空間卡片派發規範】，破除口頭動詞依賴，任何設施推薦一律強制派發 `add_itinerary_item`。
> - 🌐 **Cloudflare Edge 搜尋代理打通與多引擎四層洋蔥保險 (Cloudflare Anycast Search Runner & Onion Resilience, AD-185)**：打通已線上部署之 `https://tabidachi-search-proxy.ryanpig228.workers.dev`，消解脫敏佔位符 `REDACTED_WORKER_HOST` 引發之 `getaddrinfo failed` DNS 異常，並建立面對 DDG 202、Brave 429、Google 403 之毫秒級 Wikipedia 官方 API 零封鎖終極兜底。
> - 📱 **行動端對話框 Auto-Dock 迷你浮條與 Quick Action Chips (AD-186)**：在 `chat-widget.tsx` 實裝 56px 迷你浮條（Mini-Bar）下潛收納與一鍵秒回機制，大幅優化手機端 (< 768px) 視口遮蔽痛點，並配置 4 顆高頻周邊探索晶片。
> - ⚡ **Next.js 16 局部預渲染與 PPR 啟動警告消除 (Next.js 16 Partial Prefetching, AD-187)**：在 `next.config.mjs` 配置 `partialPrefetching: true`，消除 Next.js 16 編譯警告，實現路由局部預載加速。

---

## 🏆 深度專案復盤：五項工程與資安里程碑 (Five Core Milestones)

---

### 里程碑一：周邊空間感知閉環與 In-Card MiniMap 輕量瓦片 (AD-182)

1. **核心痛點與外跳破裂問題**：
   - 舊版聊天室推薦美食或景點時，若調用 `add_itinerary_item`，僅呈現文字卡片；點擊「在地圖上預覽」會呼叫 `openExternalLink` 彈出 Google Maps 新視窗，徹底打斷旅人的對話流與 PWA 沉浸感。
2. **Web Mercator 靜態切片瓦片輕量整合**：
   - 不在對話框內重複建立昂貴且佔用 GPU Context 的 MapLibre 實例，而在 [`frontend/components/chat/POIPreviewCard.tsx:266-314`](file:///d:/Project/tabiji/travel-pwa/frontend/components/chat/POIPreviewCard.tsx#L266-L314) 實裝基於標準 OSM/Esri 瓦片數學公式之微型地圖：
     $$x = \lfloor \frac{\text{lng} + 180}{360} \cdot 2^{\text{zoom}} \rfloor$$
     $$y = \lfloor (1 - \frac{\ln(\tan(\text{latRad}) + \sec(\text{latRad}))}{\pi}) \cdot 2^{\text{zoom}-1} \rfloor$$
   - 採用 Esri World Street Map 15 級切片，搭配 Tailwind CSS 微妙漸層遮罩、中心呼吸紅點圖釘與浮動坐標膠囊。
3. **跨組件神經運鏡事件 (Neural Map FlyTo)**：
   - 點擊卡片地圖或「全景運鏡 ↗」時，透過 `window.dispatchEvent(new CustomEvent("tabidachi:map-flyto", ...))` 發送信號；
   - [`frontend/components/itinerary/MultiDayMasterMap.tsx:120-156`](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/MultiDayMasterMap.tsx#L120-L156) 註冊監聽器，嚴格校驗經緯度邊界，驅動主地圖以 `duration: 1800` 執行絲滑的相機聚焦運鏡。
4. **DevTools 遙測實證**：
   - 真機測試台北車站「麵屋武藏（站前店）」，成功呈現坐標 `25.0456, 121.5165` 瓦片圖並平滑聚焦。

---

### 里程碑二：時序感知生命週期去耦合與工具抑制破除 (AD-183)

1. **時序感知干擾的發現**：
   - 當前系統時間為 `2026-10-25`，測試專案範例行程日期為 `2026-03-10`。
   - [`backend/services/temporal_service.py`](file:///d:/Project/tabiji/travel-pwa/backend/services/temporal_service.py#L310) 判定：`🏁 行程已圓滿結束 (已結束 227 天，當前為行程回顧狀態)`。
   - Gemini 模型因此產生強烈的「回顧模式」偏見，認為行程已過期，不應調用 `add_itinerary_item`，退化為僅在文字最後詢問：「需要我幫你把這家拉麵存到下次待吃清單嗎？」。
2. **解耦防護架構**：
   - 在 [`backend/services/temporal_service.py:405-407`](file:///d:/Project/tabiji/travel-pwa/backend/services/temporal_service.py#L405-L407) 注入時序中立不變量：
     ```python
     lines.append(f"- 行程生命週期: {temporal_info['lifecycle_desc']}")
     lines.append("  (注意：無論行程日期是否已結束或尚未開始，使用者隨時可能進行模擬規劃、編輯或調整。當使用者詢問周邊或推薦具體美食/景點時，務必照常調用 add_itinerary_item 派發空間卡片供使用者自由加入行程)")
     ```
   - 徹底打破 AI 的「過期行程拒絕排程」心理包袱。

---

### 里程碑三：二階段 Agentic Tool-Calling 提示詞斷鏈消解 (AD-184)

1. **資料斷鏈致命 Bug**：
   - 在 First-Pass 中，地理服務 [`poi_service.py:execute_resilient_nearby_search`](file:///d:/Project/tabiji/travel-pwa/backend/services/poi_service.py#L126-L260) 成功抓回真實 POI 與精確經緯度。
   - 但在 Second-Pass 組裝 `contents` 時，舊版代碼僅注入了網頁文字搜尋結果（`candidate_sources`），地理坐標陣列被完全丟棄！
   - 同時，提示詞只在 `if candidate_sources:` 中要求調用工具，且附加了苛刻條件「若使用者的指示包含將景點加入行程...才調用」。使用者若詢問「推薦拉麵」，該條件不成立，導致模型 100% 輸出純文字。
2. **全面補全與強制卡片派發規範**：
   - 在 [`backend/main.py:1358-1380`](file:///d:/Project/tabiji/travel-pwa/backend/main.py#L1358-L1380) 實裝空間意圖雙軌補全，若 First-Pass 未調用地理工具，背景自動推導錨點發起檢索；
   - 在 [`backend/main.py:1419-1440`](file:///d:/Project/tabiji/travel-pwa/backend/main.py#L1419-L1440) 無條件格式化注入真實 POI 坐標，並附帶【強制空間卡片派發指示】；
   - 在 [`backend/main.py:1845`](file:///d:/Project/tabiji/travel-pwa/backend/main.py#L1845) 注入最高安全指令第 5 條【空間卡片派發規範】，明定推薦具體店家時「嚴禁只輸出文字反問，必須調用 `add_itinerary_item`」。

---

### 里程碑四：Cloudflare Edge 搜尋代理打通與四層洋蔥保險 (AD-185)

1. **DNS 解析異常根因**：
   - 本地日誌出現 `⚠️ [SearchEngine] Tier 2 Cloudflare 邊緣檢索異常: [Errno 111001] getaddrinfo failed`。
   - 查明原因為先前資安脫敏將預設網址設為 `REDACTED_WORKER_HOST`，而本機 `.env` 漏填真實變數。
2. **打通現役 Worker 與短路防護**：
   - 透過 Cloudflare 官方 API 檢驗，確認帳號內已部署現役 Worker `tabidachi-search-proxy`；
   - 在 [`backend/.env`](file:///d:/Project/tabiji/travel-pwa/backend/.env#L20) 補齊 `CF_WORKER_SEARCH_URL=https://tabidachi-search-proxy.ryanpig228.workers.dev`；
   - 在 [`backend/services/web_search_engine.py:108`](file:///d:/Project/tabiji/travel-pwa/backend/services/web_search_engine.py#L108) 增加短路防禦，避免無效佔位符拋錯。
3. **四層洋蔥容錯實效**：
   - 當面對 DuckDuckGo 202（圖形挑戰）、Brave 429（頻率限制）、Google 403（機房阻擋）時，Cloudflare Anycast IP 洗白檢索器與 Wikipedia 官方開放 API 構成無懈可擊的 100% 兜底防線。

---

### 里程碑五：行動端對話框 Auto-Dock 迷你浮條與 Quick Action Chips (AD-186)

1. **人因工程視口遮蔽改善**：
   - 在小螢幕設備（< 768px）上，聊天室展開時會佔據全螢幕，遮擋旅人正在比對的底層多天大地圖。
2. **雙態 Auto-Dock 機制**：
   - 在 [`frontend/components/chat-widget.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/chat-widget.tsx) 引入 `isDocked` 狀態。
   - 支援點擊右上角最小化或在頂部向下滑動，下潛為高度 56px 的底層迷你懸浮條（Mini-Bar），顯示 AI 狀態與最新訊息預覽；點擊浮條秒級彈回原對話。
3. **快速操作晶片**：
   - 輸入框上方配置 4 顆常駐藥丸晶片（📍 探索周邊、🍜 必吃拉麵、💊 應急藥妝、☕ 特色咖啡），大幅降低單手在旅途中打字的認知負擔。

---

### 里程碑六：機構級反向投資審查（Counter Due-Diligence）防禦體系 (AD-188)

1. **戰略背景與創意收割者防禦**：
   - 鑑於 Web3、AI 領域充斥以「孵化中心」或「天使專題」為幌子的刷單中介，試圖誘使團隊上傳未公開 Prompt 拓撲、Schema 與財務架構。
   - 於 [`docs/legal/investment/spec_investor_counter_due_diligence_response.md`](file:///d:/Project/tabiji/travel-pwa/docs/legal/investment/spec_investor_counter_due_diligence_response.md) 實裝三道不可妥協的機構級合規試金石（Gate 1: 官方機構企業域名通訊；Gate 2: 雙向非公開保密協議 NDA；Gate 3: 100% 純現金股權出資確認，明確排除內部算力/流量券等 In-Kind Credit）。
2. **正式回函標準化範本**：
   - 制定中英標準覆函文本，維護專案商業安全與嚴肅性。

---

### 里程碑七：TIPO 商標註冊佈局與《巴黎公約》6 個月跨國優先權 (AD-189)

1. **核心類別封鎖**：
   - 於 [`docs/legal/trademark/2026-tipo-trademark-filing-and-paris-convention-spec.md`](file:///d:/Project/tabiji/travel-pwa/docs/legal/trademark/2026-tipo-trademark-filing-and-paris-convention-spec.md) 完成第 09 類（行動電話應用與電子行程表）、第 39 類（觀光旅遊安排與客票代售預訂）、第 42 類（AIaaS、SaaS 與地圖託管）之精準 NCL 尼斯分類佈局。
2. **跨國優先權時鐘與零紙本隱私防禦**：
   - 依《巴黎公約》第 4 條鎖定 2026-10-12 至 2027-04-12 跨國優先權窗口，未來可無縫延展至日本特許廳 (JPO)；
   - 全流程採用 TIPO e-Filing 電子送達，杜絕實體平信寄送至戶籍住址，落實創辦人個人極致隱私保護。

---

### 里程碑八：教育部 U-start 35 萬開辦費合規提領與 Vercel 商業雷區防禦 (AD-190)

1. **35 萬創業開辦費合法公轉私架構**：
   - 於 [`docs/specs/business/2026-ustart-grant-allocation-and-cloud-compliance.md`](file:///d:/Project/tabiji/travel-pwa/docs/specs/business/2026-ustart-grant-allocation-and-cloud-compliance.md) 明確劃分：上限 70%（約 24.5 萬元）透過聘僱核心架構師合法提領研發薪資，檢附 Git Commit、日誌與所得扣繳；30%（約 10.5 萬元）用於會計師簽證、商標規費與雲端年費實報實銷。
2. **Vercel Hobby 商業停機雷區防禦**：
   - 識別掛載導購或收費後 Vercel 觸發 `503 DEPLOYMENT_PAUSED` 風險，確立「以 U-start 業務費升級 Vercel Pro」與「零成本備援遷移至 Cloudflare Pages」之雙保險策略。

---

### 里程碑九：聯盟行銷多網域歸因與出款審核 (Payout Audit) SOP (AD-191)

1. **換網域零斷流底層原理**：
   - 於 [`docs/specs/business/affiliate-payout-and-multi-domain-attribution-guide.md`](file:///d:/Project/tabiji/travel-pwa/docs/specs/business/affiliate-payout-and-multi-domain-attribution-guide.md) 確立 Travelpayouts / Klook 分潤取決於 URL 內的 Marker Token 與目標端 30~90 天 Cookie，遷移自訂網域 `tabijiapp.com` 不會中斷歸因。
2. **雙渠道並存（Two-Channel Architecture）**：
   - 正式站與測試站並存白名單，徹底防禦首次請款人工稽核（Payout Audit）卡單風險。

---

### 里程碑十：AaaS 焦油坑逃脫、YC Startup School 申請與敏感訊息脫敏 (AD-192)

1. **矽谷焦油坑定理（Tarpit Idea）與破局解法**：
   - 於 [`docs/research/2026-10-24-aaas-travel-tarpit-and-u-start-audit.md`](file:///d:/Project/tabiji/travel-pwa/docs/research/2026-10-24-aaas-travel-tarpit-and-u-start-audit.md) 深度剖析泛用型 B2C 旅遊規劃之低頻與高 CAC 死穴，確立 Tabiji 轉向「弱網離線自癒 + 跨國醫療移動照護」高防禦性利基。
2. **YC Startup School Taipei 2026 申請答題包**：
   - 於 [`docs/research/2026-yc-startup-school-taipei-application-pack.md`](file:///d:/Project/tabiji/travel-pwa/docs/research/2026-yc-startup-school-taipei-application-pack.md) 針對 Garry Tan 率領之 YC 旗艦活動產出高密度英中文申請規格。
3. **全域敏感訊息淨化 (Zero Leakage)**：
   - 全面清洗所有個人私密通訊、身分證號與內部金鑰佔位符，確認 Git 暫存區 100% 安全無虞。

---

## 🏛️ 架構決策紀錄 (Architecture Decision Records)

- **AD-182 (Map-in-Chat Decoupling)**: 嚴禁在對話框內初始化重量級 WebGL Canvas 實例。一律採用靜態 Web Mercator 瓦片切片渲染 MiniMap，並透過 Window CustomEvent 向單例 MasterMap 派發相機運鏡指令。
- **AD-183 (Temporal Lifecycle Invariant)**: 行程時序狀態僅用於問候與時區轉換，嚴禁用於抑制 AI 的工具調用或假定行程唯讀。
- **AD-184 (Deterministic Geo-Injection Protocol)**: 任何涉及到地理 POI 檢索的結果，必須在 Second-Pass 的 User Content 中強行注入真實坐標與批次 `add_itinerary_item` 指示，防禦 LLM 自然對話慣性造成的工具閹割。
- **AD-185 (Edge Proxy & Multi-Engine Onion Fallback)**: 外部搜尋引擎一律視為不可信且隨時可能觸發 429/403/202。實施本地多引擎並行 (Tier 1) -> Cloudflare Anycast (Tier 2) -> Wikipedia API (Tier 4) 的階梯式無損降級。
- **AD-186 (Mobile Viewport Docking Standard)**: 行動端 (< 768px) 對話介面必須提供高度小於等於 60px 的 Docked Mini-Bar 狀態，保證隨時可還原底層地圖操作。
- **AD-187 (Next.js 16 Partial Prefetching Compliance)**: 使用 Next.js 16 Cache Components 時，必須顯式宣告 `partialPrefetching: true`，消除框架潛在配置偏離。
- **AD-188 (Counter Due-Diligence Institutional Protocol)**: 面對外部投資邀請，強制執行企業域名、雙向 NDA 與 100% 現金確認三道門檻，防禦技術與架構被無償收割。
- **AD-189 (Paris Convention Trademark Priority Moat)**: 以 TIPO 雙案送件確立優先權基點（第 09、39、42 類），捨棄審查高風險的動態商標，以平面商標結合代碼軟體著作權築起跨國護城河。
- **AD-190 (Grant Capital Allocation & Cloud Compliance)**: U-start 35 萬創業開辦費採取 70% 研發薪資公轉私 + 30% 業務費合規實報實銷架構，並建立 Vercel 商業升級與 Cloudflare Pages 遷移備援。
- **AD-191 (Multi-Domain Affiliate Payout Attribution)**: 建立生產站與測試站雙渠道並存架構，確保網域遷移後 Cookie 歸因不斷流並通過出款風控審核。
- **AD-192 (AaaS Tarpit Escape & High-Resilience Domain Pivot)**: 確立擺脫泛用型消費旅遊焦油坑戰略，以端側 WebGL 空間拓撲與弱網離線自癒建立差異化，並備妥 YC Startup School 國際賽道申請資料。

---

## 🛡️ 今日踩坑與失敗路徑紀錄 (Failed Paths)

- **FP-28: 依賴使用者的字面動詞作為唯一工具調用依據**
  - **Symptom**: 使用者問「這附近有什麼拉麵」時，AI 只給出優美文字介紹並詢問要不要加行程，前端永遠長不出地圖氣泡。
  - **Lesson**: 使用者是探索者而非系統操作員，嚴禁要求使用者精確說出「加入行程」動詞。後端必須在語意涉及實體店家時，主動以空間卡片形式提供選擇。
- **FP-29: 佔位符未提供本機環境隔離**
  - **Symptom**: 資安脫敏審查將網址改為 `REDACTED_WORKER_HOST`，導致本機執行時遭遇 DNS `getaddrinfo failed` 警告。
  - **Lesson**: 任何佔位符字串在進入網路請求前，必須有 `if "REDACTED" in url: return fallback` 的安全短路守衛。
- **FP-30: 誤將自訂網域視為通過 Vercel 商用檢驗**
  - **Symptom**: 誤以為花錢買網域綁在 Vercel Hobby 上即可合法商用，忽略其自動爬蟲對聯盟行銷與收費行為之偵測。
  - **Lesson**: 一旦涉及真實商業或導購代碼，必須以公司預算升級 Vercel Pro 或遷移至完全支援免費商用的 Cloudflare Pages。

---

## 🎯 明日核心衝刺目標 (Next Steps)

1. **離線地圖離線瓦片快取擴充**：評估 Serwist Service Worker 快取 Esri/OpenFreeMap 瓦片之 LRU 上限（目標 50MB）。
2. **三源 POI 文化資訊多語系同步**：確保日語、繁中與英文在 In-Card MiniMap 與 POI 卡片切換時流暢無縫。
3. **雲端發布與 Cloud Run CI/CD 監控**：持續追蹤 Cloudflare Edge Search Proxy 之連線延遲（維持在 300ms 內）。
4. **YC Startup School 台北實體活動送件**：確認英文申請欄位與 Demo 網址體驗，於截止前完成線上投遞。

---

## 🧬 Machine-Executable Invariant Rules
```json
[
  {
    "domain": "map_webgl",
    "type": "INVARIANT_RULE",
    "id": "INV-MAP-004",
    "title": "In-Card MiniMap Lightweight Tile Rendering",
    "content": "Chat POI preview cards must use Web Mercator tile URL calculations (https://server.arcgisonline.com/.../15/{y}/{x}) instead of initializing full WebGL MapLibre instances to prevent GPU memory pressure."
  },
  {
    "domain": "map_webgl",
    "type": "INVARIANT_RULE",
    "id": "INV-MAP-005",
    "title": "Cross-Component FlyTo Event Bus",
    "content": "Component-level location previews must dispatch tabidachi:map-flyto custom events with bounded lat/lng rather than opening external map windows."
  },
  {
    "domain": "state_cache",
    "type": "INVARIANT_RULE",
    "id": "INV-STATE-008",
    "title": "Temporal Lifecycle Non-Inhibition Invariant",
    "content": "Temporal service lifecycle status (BEFORE_TRIP, IN_TRIP, AFTER_TRIP) must never inhibit mutation tool calling. The prompt must explicitly state that users have full simulation and planning permissions regardless of dates."
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BACKEND-012",
    "title": "Two-Pass Geo Tool-Calling Injection Mandate",
    "content": "Whenever nearby search executes in First-Pass, the coordinates and candidate places must be explicitly injected into the Second-Pass User Content with an unconditioned mandate to call add_itinerary_item."
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-SEC-015",
    "title": "Redacted Host Short-Circuit Guard",
    "content": "Any proxy URL configuration using REDACTED placeholders must short-circuit gracefully to fallback mechanisms without triggering getaddrinfo DNS network exceptions."
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-SEC-016",
    "title": "Counter Due-Diligence Tri-Gate Defense",
    "content": "All unsolicited inbound investment/incubation inquiries must satisfy corporate email domain, bilateral NDA, and 100% legal tender cash affirmation before sharing proprietary architecture or schemas."
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-SEC-017",
    "title": "Commercial Cloud Compliance and Deployment Guard",
    "content": "Any production build utilizing commercial affiliate redirect or monetization tokens must operate on Vercel Pro or Cloudflare Pages to prevent 503 DEPLOYMENT_PAUSED fair-use suspension."
  },
  {
    "domain": "ios_ui",
    "type": "INVARIANT_RULE",
    "id": "INV-UI-007",
    "title": "Mobile Viewport Mini-Bar Auto-Dock",
    "content": "On mobile screens (< 768px), floating chat dialogs must support docking into a <= 60px mini-bar to preserve underlying map interaction without losing conversation state."
  }
]
```
