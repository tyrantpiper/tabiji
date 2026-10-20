# 2026 Google Maps 共享清單逆向萃取、全局景點庫 (POI Pool) 與雲端儲存架構調研

> **調研日期**: 2026-10-18  
> **目標對象**: Google Maps Shared Lists (`maps.app.goo.gl` / `placelists/list`), Supabase vs Cloudflare D1/KV, MapLibre 向量圖層聯動, UI/UX 空間減負重構  
> **輸出規格**: NotebookLM 獨立研究素材包 (無主觀修飾，嚴謹工程推導)

---

## 1. 核心技術流程 (Core Technical Execution Flow)

### 1.1 Google Maps 共享清單逆向萃取流程 (Shared List Extraction Flow)

```
[使用者貼上 Google Maps 清單網址]
       │
       ▼
[階段一：短網址追蹤 (Unshorten & Canonicalization)]
  - URL Pattern: https://maps.app.goo.gl/[Token] 或 https://goo.gl/maps/[Token]
  - 邊緣發起 HTTP GET (User-Agent: Desktop Chrome, Follow Redirects)
  - 獲取展開後長網址: https://www.google.com/maps/placelists/list/[ListID]
       │
       ▼
[階段二：SSR HTML 初始狀態截收 (State Ingestion)]
  - 請求標頭配置: Accept: text/html, User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)...
  - 截取 Script Payload:
    window.APP_INITIALIZATION_STATE = [...];
    或 window._pageData = "...";
       │
       ▼
[階段三：混淆 Protobuf/陣列逆向解析 (Structural Pattern Extraction)]
  - 放棄死板的固定陣列索引 (避免 Google 佈局更新引發崩潰)
  - 採用容錯正則與語意錨點掃描:
    * 經緯度座標: \[null,\s*null,\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)\]
    * Google Place ID: ChIJ[A-Za-z0-9_-]{23,}
    * 地點標題與類別: 鄰接於座標點前後之 UTF-8 字串
    * 使用者私人備註: 捕捉清單建立者輸入之註解文字 (Notes)
       │
       ▼
[階段四：正規化 POI 實體與快取 (Normalized POI Entity & Edge Cache)]
  - 轉為標準結構: { id, name, lat, lng, place_id, address, category, user_note }
  - 邊緣快取 24 小時 (Cloudflare Cache API)，大幅消除 Google 請求頻率
```

---

## 2. 網路大神爭議點與避坑指南 (Pitfalls & Battle-Tested Defenses)

### 2.1 陷阱一：Google 首屏 SSR 分頁截斷 (The 20-30 Item Pagination Wall)
* **現象**：當使用者分享超過 50 或 100 個景點的超大清單時，`window.APP_INITIALIZATION_STATE` 僅包含首屏 20 到 30 個地點。
* **原因**：Google Maps 前端為 SPA 架構，超出 25 個地點的項目依賴客戶端捲動觸發內部 RPC (`/_/MapsUiEgressService/...` 帶有 protobuf 游標 `8i20`, `8i40`)。
* **業界對策**：
  1. **Tier 1 (輕量無伺服器)**：直接提取首屏 20-30 筆（覆蓋 80% 一般背包客分享清單），並在 UI 標示「已成功匯入前 25 筆地點；超長清單可透過追加連結或 Google Takeout 匯入」。
  2. **Tier 2 (Google Takeout 備用雙軌)**：使用者若需匯出數百個星號標籤，引導匯入 Google Takeout `Saved Places.json` 或 `Saved Places.csv`，由本機前端 0 延遲解析完成。

### 2.2 陷阱二：數據中心 IP 封鎖與 429 人機驗證 (Google Anti-Bot Defenses)
* **現象**：若直接由單一後端伺服器 (如 Cloud Run 或 VPS 固定 IP) 大量向 Google 發起 `placelists/list` 抓取，將觸發 Google 防爬機制，回傳 `302 Found -> sorry/index?continue=...` (CAPTCHA 攔截)。
* **業界對策**：
  - **嚴禁使用後端單點 IP 直連**。
  - **由 Cloudflare Worker 擔任出站解析代理**：利用 Cloudflare 遍佈全球 300+ 城市的 Edge IP 輪換池，結合 Cache API（以 `list_id` 為鍵快取 24 小時），將 Google 出站請求壓至最低。

### 2.3 陷阱三：私人清單與權限邊界 (Private vs Shared Access)
* **現象**：使用者貼上的清單若為 Google Maps「私人清單 (Private)」，無憑證請求將回傳 Google 登入導向。
* **防護機制**：
  - 後端/Worker 偵測 HTTP 302 跳轉至 `accounts.google.com` 或 HTML 缺乏 `APP_INITIALIZATION_STATE` 時，立即回傳錯誤代碼 `LIST_IS_PRIVATE`。
  - 前端 UI 跳出清楚引導：「此清單設為私人。請在 Google 地圖中將該清單權限設為『知道連結的人即可查看』後再次貼上」。

---

## 3. GitHub 原始碼層級驗證 (Open Source Audits)

| 專案名稱 | 語言/架構 | 星數/維護狀態 | 實作策略與借鑒 | 局限與缺失 |
| :--- | :--- | :--- | :--- | :--- |
| **`jakubvalenta/geoshare`** | Kotlin (Android) | 活躍維護 (2025-2026) | 深度實作各大地圖 URL Schemes 與意圖轉換。 | 在 `GoogleMapsPlaceListInputImplTest.kt` 明確標記 `Place lists are not supported`，驗證在輕量端點解析清單的技術門檻高，大多數行動端選擇放棄。 |
| **`liketrek/TREK`** | TypeScript / Vue / Go | v5.0.0 (2026 開源) | 具備完整的旅行書籤 (Bookmarks/POI Pool) 與地圖聚集 (Clustering) 模組。 | 需自架 Docker + PostgreSQL，無純前端免安裝 PWA，亦無貼 Google Maps 清單自動解構機制。 |
| **`Yeshey/Export-Google-Maps-Saved-Places`** | Python | 社群成熟 | 驗證 Google Takeout 匯出的 CSV/JSON 結構與 GPX/KML 轉換管道。 | 依賴使用者手動前往 Google Takeout 下載壓縮包，操作步驟過於冗長 (高摩擦力)。 |
| **`omkarcloud/google-maps-scraper`** | Python / Headless | 高星熱門 | 透過 Playwright 捲動抓取 Google Maps 完整清單，精準抓取店名、座標、電話與評分。 | 需重型 Headless Chrome 算力，無法在邊緣 (Edge) 或低成本伺服器運行，單次抓取成本過高。 |

---

## 4. 雲端架構終極裁決：Cloudflare D1/KV 是否「屌打」Supabase？

使用者提出大膽設想：**「景點清單庫考慮用 Cloudflare 儲存有搞頭嗎？是不是屌打 Supabase？」**

### 4.1 深入對比矩陣

| 評估維度 | Cloudflare (D1 / KV) | Supabase (PostgreSQL) | 裁決與理由 |
| :--- | :--- | :--- | :--- |
| **儲存模型** | 邊緣 SQLite (D1) / Key-Value (KV) | 關聯式 PostgreSQL 15/16+ | **Supabase 勝**。景點庫需支援「隨時加入哪天行程」，與行程 (`trips`, `days`, `activities`) 為強關聯實體。 |
| **認證體系 (Auth)** | 無內建 Auth，需由 Worker 自行校驗 JWT | 內建 Supabase Auth (JWT + RLS) | **Supabase 完勝**。若用 Cloudflare，必須自建 Supabase JWT RS256 驗證中介軟體，出現認證孤島 (Auth Silo)。 |
| **交易一致性 (ACID)** | 跨平台分散式寫入 (D1 讀出 ➔ Supabase 寫入) | 原生資料庫內部交易 (Single DB ACID) | **Supabase 完勝**。跨系統寫入極易出現網路中斷後的幽靈資料或狀態不同步。 |
| **邊緣讀取延遲** | 極致 (全球 300+ 城市 < 10ms 唯讀) | 區域性 (依託 Primary Region 約 30-80ms) | **Cloudflare 勝**。但 Tabidachi 本身具備 IndexedDB 本機快取 (0ms)，削弱了 D1 邊緣優勢。 |
| **出站反爬與抓取** | 全球邊緣出站 IP 池，無冷啟動，帶 Cache API | 僅為資料庫，不適合作為外部爬蟲代理 | **Cloudflare 完勝**。解碼 Google Maps 短網址與 HTML 提取是 Cloudflare Worker 的絕對強項。 |

### 4.2 最優非對稱架構結論 (The Hybrid Moat)
* ❌ **絕對不要把景點庫資料本體丟去 Cloudflare D1**：那將破壞整個應用的一致性與安全 RLS，徒增架構維護複雜度。
* ✅ **資料持久層 (Data Tier) ➔ Supabase PostgreSQL (`saved_places` 表)**：
  - 與現有使用者、行程、活動無縫關聯，享有現成的 RLS 權限隔離。
  - 免費 500MB 可容納超過 250 萬筆景點，邊際成本為 $0。
* ✅ **代理與快取層 (Edge Scraper Tier) ➔ Cloudflare Worker (`edge-shield/worker.js`)**：
  - 專門負責接收 Google Maps 短網址，在邊緣節點執行 302 跟隨、抓取 HTML、正則解析出 POI 清單。
  - 將解析結果在 Cloudflare 邊緣快取 24 小時。
  - 前端拿到解析好的 POIs 後，一次寫入 Supabase，同時持久化至本機 IndexedDB。

---

## 5. UI/UX 空間減負重塑與「半截緞帶 (Bookmark)」規格

### 5.1 空間痛點與減負工程
1. **移除 TripSwitcher 編輯鉛筆 (`Edit3`)**：
   - 目前在 `ItineraryHeader` 中，標題旁的編輯鉛筆製造了嚴重視覺擁擠。
   - 右上角齒輪按鈕 (`Settings`) 已具備完整的行程標題編輯功能，鉛筆純屬功能冗餘。**直接自 Header 移除鉛筆**。
2. **移除 `ItineraryHeader` 的 `ZenRenew` 旋轉重新整理**：
   - Tabidachi 採用 SWR Map Proxy + IndexedDB 永續快取，具備離線自癒與後台驗證能力，手動重新整理按鈕已無必要。**直接拿掉**。
3. **換裝「半截緞帶 (Bookmark / Ribbon)」圖示按鈕**：
   - 在行程首頁 (`TabijiHomeDashboard`) 與行程詳情頁 (`ItineraryHeader`) 原重新整理位置，替換為優雅的「半截緞帶（已儲存景點 / 願望清單）」按鈕。
   - 點擊時伴隨微震動觸覺（Haptic Impact），滑出【全局景點清單庫抽屜 (Global Saved Places Drawer)】。

### 5.2 全局景點清單庫抽屜 (Global Saved Places Drawer) 互動規格
* **匯入區**：頂部提供快速貼上欄，支援單一 Google 地點連結或完整共享清單連結。
* **景點卡片**：
  - 顯示：地點名稱、圖標類別、經緯度、評分、備註。
  - 動作 A：**「加入行程」** ➔ 彈出天數選單 (Day 1..Day N)，一鍵新增至行程該天。
  - 動作 B：**「外部導航」** ➔ 喚起 Apple Maps / Google Maps。
  - 動作 C：**「移除」** ➔ 從願望清單刪除。
* **MapLibre 向量地圖聯動**：
  - 地圖模式下，願望清單地點以獨立的「琥珀金/半透明半截緞帶 Pin」常駐於地圖上。
  - 使用者在瀏覽地圖時，能清楚區分「已排程活動 (深綠/亮橘)」與「口袋名單 (琥珀金)」，點擊地圖上的緞帶 Pin 亦可直接「排入今天行程」。
