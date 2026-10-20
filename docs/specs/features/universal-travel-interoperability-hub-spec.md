# Tabidachi 跨生態通用相容樞紐規格書 (Universal Travel Interoperability Hub Spec)
**規格書識別碼**: `SPEC-FEAT-INTEROP-HUB-2026-10-17`  
**遵循標準**: `/Idea to Spec` 標準規格書架構  
**當前狀態**: `PROPOSED` (待人類決策確認)  
**核心哲學**: 「相容性大於封閉功能；成為使用者既有數位生活（Google Maps, Apple Calendar, Notion, Booking, Excel）的無縫超級樞紐（Hub & Bridge），而非封閉花園（Walled Garden）。」

---

## 一、 問題陳述與核心價值 (Problem Statement & Core Value)

### 1.1 使用者痛點 (User Problem)
*   **多工具分散痛點**：現代旅客不可能只使用單一 App。他們在 **Google Maps** 標註星號、在 **Gmail/Outlook** 收到訂房訂票信、在 **Apple/Google Calendar** 管理個人時間、在 **Notion/Obsidian** 記錄旅遊心得、在 **Excel/Sheets** 與旅伴算帳。
*   **競品孤島詛咒**：
    *   **Wanderlog / TripIt**：試圖鎖定使用者資料，匯出日曆與離線地圖往往需要收取高昂訂閱費 ($40–$49/年)。
    *   **開源 TREK**：功能極齊全，但依賴重型 Docker + PostgreSQL 自架，大眾旅客門檻極高。
*   **Tabidachi 解法**：作為 **純前端 Local-First PWA**，不重造輪子（不試圖取代 Google Maps 即時導航或 Notion 富文本協作），而是透過**開放協議與極致相容管道**，讓數據自由流入與流出，實現零摩擦的工作流銜接。

### 1.2 成功衡量指標 (Success Metrics)
1.  **外部生態匯入成功率**：Google Maps 景點分享連結 / 清單 / KML 解析成功率 $\ge 98\%$。
2.  **日曆同步零摩擦**：點擊「加入日曆」後，可在 1 秒內透過 Web Share 或 `.ics` 下載完成 Apple / Google Calendar 注入。
3.  **零伺服器邊際成本**：全鏈路匯入、匯出與格式轉換 100% 在前端瀏覽器（或 Cloudflare 無狀態 Worker）完成，不增加 Cloud Run 或資料庫負擔。

---

## 二、 使用者旅程與核心流程 (User Journey & Core Flows)

```mermaid
graph TD
    subgraph 外部輸入生態 (Input Streams)
        A1[Google Maps 景點/清單連結] -->|Web Share Target / 剪貼簿| B[Tabidachi 樞紐解析器]
        A2[Booking / 機票確認信] -->|貼入內文 / EML / 轉寄| B
        A3[KML / KMZ / GPX 檔案] -->|拖曳上傳| B
    end

    subgraph Tabidachi 核心 (Local-First Core)
        B --> C[IndexedDB SWR 本機狀態]
        C --> D[MapLibre WebGL 軌跡地圖]
        C --> E[時間軸與記帳儀表板]
    end

    subgraph 外部輸出與喚醒 (Output & Hand-off)
        E -->|URL Schemes| F1[一鍵喚醒 Apple Maps / Google Maps 即時導航]
        E -->|RFC 5545 .ics| F2[系統級日曆推播 (Apple/Google/Outlook)]
        E -->|Markdown / 富文本| F3[一鍵貼入 Notion / Obsidian 筆記]
        E -->|CSV / SheetJS| F4[匯出 Excel / Google Sheets 拆帳表格]
        E -->|Model Context Protocol| F5[提供 Claude / Cursor 讀寫行程 (MCP)]
    end
```

---

## 三、 四大相容協議架構與資料模型 (Architecture & Data Model)

### 3.1 地圖生態相容 (Map Interoperability)
*   **輸入 (Ingress)**：
    *   **Google Maps Share URL**：`https://maps.app.goo.gl/...` 或 `https://www.google.com/maps/place/...`。前端透過無狀態正規化器解析出經緯度與名稱。
    *   **KML / KMZ / GPX**：純前端使用 `@tmcw/togeojson` 解析為標準 `GeoJSON FeatureCollection`。
*   **輸出 (Egress & Hand-off)**：
    *   **Apple Maps 原生導航喚醒**：`maps://?daddr={lat},{lng}&q={encodeURIComponent(title)}`
    *   **Google Maps 原生導航喚醒**：`https://www.google.com/maps/dir/?api=1&destination={lat},{lng}`
    *   **日本在地乘換案內**：支援快速帶入 Navitime / Yahoo! 乘換案內站點參數。

### 3.2 行事曆生態相容 (Calendar Interoperability)
*   **標準協議**：RFC 5545 (`iCalendar` / `.ics`)。
*   **核心組件**：前端純 JS 產出器 `generateIcsFeed(itinerary: Itinerary): string`。
*   **邊界特性**：
    *   **多時區處理**：跨國移動（例如台灣 UTC+8 至日本 UTC+9）自動宣告 `VTIMEZONE`，確保系統日曆在正確當地時間響鈴。
    *   **地理座標注入**：包含 `GEO:lat;lng` 與 `LOCATION:名稱`，使 Apple/Google Calendar 自動顯示微型地圖與出發提醒（Time to Leave）。

### 3.3 訂票與憑證相容 (Booking & Voucher Ingress)
*   **標準結構**：相容 Schema.org `LodgingReservation` 與 `FlightReservation` JSON-LD。
*   **輸入方式**：
    1.  **剪貼簿快速貼入**：使用者複製訂房通知信（Booking.com, Agoda, 航空公司），前端透過輕量正規化邏輯（或呼叫使用者 BYOK Gemini）提取日期、地址、訂單編號。
    2.  **Email Worker 轉寄**：利用官方網域 `receipt@tabijiapp.com` 接收轉寄郵件，無狀態解析後回傳結構化 JSON。

### 3.4 筆記與表格生態相容 (Productivity Egress)
*   **Notion / Obsidian 相容**：
    *   提供「一鍵複製為 Markdown 行程」：
        ```markdown
        ### Day 1: 2026-10-20 東京探索
        - [ ] **09:00 - 10:30** [淺草寺](https://maps.google.com/?q=35.7147,139.7966) (參拜雷門)
        - [ ] **11:00 - 12:30** [晴空塔](https://maps.google.com/?q=35.7100,139.8107) (觀景台門票已預約)
        ```
*   **Excel / Google Sheets 相容**：
    *   提供「匯出分帳 CSV」：包含 `Date`, `Category`, `Description`, `Currency`, `Amount`, `JPY_Equivalent`, `Paid_By`, `Split_Between` 等標準欄位。

---

## 四、 邊界條件與異常防護 (Edge Cases & Boundaries)

| 邊界維度 | 潛在異常場景 | 防禦機制與優雅降級 |
| :--- | :--- | :--- |
| **短網址轉址** | Google Maps `maps.app.goo.gl` 短網址受 CORS 限制，前端無法直接 `fetch` | 透過 Cloudflare Worker 輕量無狀態轉發（僅追蹤 HTTP 302 Location Header 解出長網址，耗費 0 CPU）。 |
| **時區夏令時間 (DST)** | 跨時區旅程在行事曆中發生 1 小時位移 | `.ics` 嚴格使用標準 IANA 時區識別碼（如 `Asia/Tokyo`）配合 `DTSTART;TZID=...`，禁止直接混用無時區的 Local Time。 |
| **大檔案 KML/GPX** | 使用者匯入 50MB 超大型健行航跡檔導致記憶體崩潰 | 前端 Web Worker 解析並實施座標抽稀（Douglas-Peucker 演算法），將點數壓至 2,000 點以內再交由 MapLibre 渲染。 |
| **PWA 喚醒限制** | 行動端 Safari 未安裝 Google Maps 時點擊 `google.navigation:` 會報錯 | 一律使用標準 HTTPS 萬用鏈結（Universal Links / App Links），未安裝 App 時自動平滑降級至行動網頁版。 |

---

## 五、 驗收標準清單 (Acceptance Criteria)

- [ ] **AC-1 (地圖導航手勢喚醒)**：在景點詳細卡片點擊「導航」，iOS 自動喚醒 Apple Maps / Google Maps 並精確定位至該景點座標。
- [ ] **AC-2 (行事曆一鍵注入)**：在行程總覽點擊「匯出至行事曆」，系統生成合規 `.ics` 檔案，透過 Web Share API 直接呼叫 iOS/Android 系統日曆完成訂閱。
- [ ] **AC-3 (Notion 剪貼相容)**：點擊「複製 Markdown」，貼入 Notion 或 Obsidian 時能完美呈現為核取方塊、時間標籤與地圖超連結。
- [ ] **AC-4 (費用表 CSV 匯出)**：記帳模組點擊「匯出 CSV」，輸出之檔案可直接被 Microsoft Excel 與 Google Sheets 正確解析日幣與中文字元（帶 UTF-8 BOM）。
- [ ] **AC-5 (零新增後端負擔)**：所有上述 4 項功能運行時，Cloud Run 後端零請求，100% 由瀏覽器端點與本機計算完成。
