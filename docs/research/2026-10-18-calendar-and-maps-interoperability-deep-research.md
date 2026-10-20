# Tabidachi 跨生態互通深度調研：協議級行事曆雙軌匯出與地圖生態雙向閉環
**文件識別碼**: `RESEARCH-INTEROP-CAL-MAP-2026-10-18`  
**建立時間**: 2026-10-18 03:05:00 UTC+8  
**調研目標**: 深度剖析 Option 1（RFC 5545 .ics 純前端產生 + Cloudflare/FastAPI webcal:// 動態訂閱）與 Option 2（iOS 智能剪貼簿 onFocus 探測 + 景點卡片 Deep URL Schemes 原生導航喚醒）的底層技術細節、邊界陷阱與代碼級落地架構。

---

## 一、 Tabidachi 全面架構全景梳理 (Comprehensive Architectural Anatomy)

在導入任何跨服務相容性功能前，必須嚴格對齊專案現存的六大技術維度：

```
┌────────────────────────────────────────────────────────────────────────┐
│                   Cloudflare Edge Zone (tabijiapp.com)                  │
│  - Tiered Cache (靜態資源 & 圖片 100% 命中)                                │
│  - Origin Rules (/api/* 無 Worker 消耗直通 Cloud Run)                  │
│  - Email Routing (contact@tabijiapp.com 轉發)                          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTPS (443)
       ┌────────────────────────────┴────────────────────────────┐
       ▼                                                         ▼
┌──────────────────────────────┐              ┌──────────────────────────────┐
│   Next.js 16 PWA (Client)    │              │  FastAPI (Google Cloud Run)  │
│ - Turbopack + React 19       │              │ - Python 3.11+ / Pydantic v2 │
│ - Serwist Service Worker     │              │ - BYOK 守衛 (deps.py)        │
│   (NetworkFirst 導航硬骨架)   │              │ - geocode.py (resolve-link)  │
│ - IdbSwrProvider (ES6 Proxy) │              │ - trips.py (CRUD + jsonb)    │
│ - MapLibre WebGL (OpenFree)  │              │ - GAS Serverless Pool        │
│ - SyncQueue (IndexedDB 隊列) │              │ - Concurrency: 40/實例 (0縮容)│
└──────────────────────────────┘              └──────────────────────────────┘
```

1.  **前端本地優先與離線管線**：
    *   **快取與持久化**：`IdbSwrProvider` 利用 ES6 `Proxy` 攔截 SWR 寫入，1000ms 防抖持久化至 IndexedDB（`tabiji_swr_persisted_cache`），並在首幀以 0ms 記憶體同步還原；掛載時自動執行 `navigator.storage.persist()` 守護 Safari 儲存空間。
    *   **離線突變**：`SyncQueue` (`frontend/lib/sync-engine.ts`) 管理 `offline-sync-queue`，結合 `useSyncStatusStore` 驅動樂觀 UI 狀態標籤（`SyncStatusBadge`）。
    *   **Service Worker 防護**：`frontend/app/sw.ts` 使用 Serwist，宣告 `cleanResponse` 淨化 WebKit 重定向毒丸；針對導航請求提供 2 秒 `NetworkFirst` 逾時備援，失敗時吐出內嵌 Zero-JS 物理硬骨架，絕不向 WebKit 回傳 `Response.error()`。
2.  **地圖與圖資引擎現狀**：
    *   `DayMap.tsx` 與 `MultiDayMasterMap.tsx` 預設維持 2D Mercator 平面（避免 3D Globe 射線穿透奇異點），使用 `geo-multi-day.ts` 球面大圓 Slerp 插值繪製彩帶軌跡；宣告式圖層拓撲嚴格避免非法 `beforeId`；容器使用 `transform-gpu will-change-transform` 雙向隔離主線程重排。
    *   本地內建 `brands.json` + `RapidFuzz`，日本連鎖品牌地名微秒級離線匹配。
3.  **既有連結解析管線 (Link Resolution Pipeline)**：
    *   `backend/routers/geocode.py` 的 `/resolve-link`：已支援過濾 iPhone 分享字串中的非 URL 雜訊（店名、地址等），追蹤 Google Maps 短網址 302 重定向解出經緯度，並具備 Tier 3 `geocode_place` 語義補查；同時支援官網/社群媒體首圖爬取。
    *   `frontend/components/itinerary/ActivityEditModal.tsx`：已接入 `geocodeApi.resolveLink`，並實作 `- Google Maps`、`| Google 地圖` 標題清洗邏輯。
4.  **既有導航按鈕限制**：
    *   `frontend/components/timeline-card.tsx` 的 `openGoogleMap`（第 133 行）：目前僅簡單拼接 `https://www.google.com/maps/search/?api=1&query=...`，尚未利用已解析的 `lat/lng` 進行精準路況導航，未適配 iOS Apple Maps 原生喚醒，亦未整合日本在地 Navitime。

---

## 二、 Option 1 深度研究：協議級行事曆雙軌匯出 (.ics + webcal://)

### 2.1 RFC 5545 (iCalendar) 標準代碼級規範
要讓生成的日曆被 Apple Calendar、Google Calendar、Outlook 與 iOS 系統無摩擦解析，必須嚴格遵守以下 RFC 5545 底層規則：

1.  **行尾換行與折行 (Line Folding)**：
    *   每一行必須以 CRLF (`\r\n`) 結尾。
    *   單行位元組長度不得超過 75 octets。超過時必須在下一行首位補一個空格（`\r\n `）進行 Line Folding。
2.  **時區宣告 (VTIMEZONE)**：
    *   日本旅遊場景一律宣告 `Asia/Tokyo`（UTC+9）。
    *   明確輸出 `DTSTART;TZID=Asia/Tokyo:20261020T090000`，嚴禁使用未帶時區的浮動時間，避免跨時區旅客在出發前日曆時間錯位 1 小時。
3.  **地理座標注入 (GEO)**：
    *   格式：`GEO:35.714700;139.796600`。
    *   **iOS 核心效益**：iOS 日曆偵測到 `GEO` 欄位後，會在事件詳細頁自動渲染微型地圖，並根據使用者當前 GPS 位置主動觸發**「該出發了 (Time to Leave)」原生系統推播**！
4.  **原生系統鬧鐘提醒 (VALARM)**：
    *   每個景點事件注入：
        ```text
        BEGIN:VALARM
        TRIGGER:-PT30M
        ACTION:DISPLAY
        DESCRIPTION:Reminder: 該前往下一個景點了
        END:VALARM
        ```
    *   抵達景點前 30 分鐘，手機由系統底層自動響鈴與跳出鎖定螢幕通知。

### 2.2 雙軌架構對比：單次 .ics 匯出 vs 動態 webcal:// 訂閱

| 維度 | 軌道 A：純前端 RFC 5545 .ics 檔案生成 | 軌道 B：動態 Webcal 訂閱 (`webcal://`) |
| :--- | :--- | :--- |
| **運作原理** | 瀏覽器本機純 JS 格式化字串，產出 `Blob` | 後端 (FastAPI/Next.js) 提供無狀態 GET 端點吐出即時 `.ics` |
| **網路依賴** | 100% 離線可用，0 伺服器請求 | 需網路連線由日曆伺服器定時拉取更新 |
| **同步能力** | 單次快照（若行程修改，日曆不自動更新） | **即時動態同步**（Tabidachi 改行程，系統日曆自動跟著改） |
| **使用者操作** | 下載檔案 ➔ 系統彈出「全部加入」確認 | 點擊一次 `webcal://...` ➔ 系統彈出「是否訂閱」 |
| **隱私與安全** | 資料 100% 留在本機，零洩漏風險 | 需行程具備公開 ID 或簽名 Token 防止他人猜測 |

### 2.3 雙軌融合最佳實踐
Tabidachi 應提供「雙軌合一」介面：
*   **預設「加入日曆」按鈕**：
    *   點擊時彈出簡潔的 iOS Action Sheet：
        1.  `📥 下載單次日曆檔 (.ics)`：立即觸發本機 Blob 下載或 Web Share。
        2.  `🔄 訂閱自動同步日曆 (webcal://)`：一鍵喚醒系統日曆訂閱面板，日後排程變更自動同步。

---

## 三、 Option 2 深度研究：Google Maps 雙向互通增強

### 3.1 外部流入：iOS 智能剪貼簿 (Smart Clipboard) + Android `share_target`
在 PWA 架構下，受限於 Apple 對 WebKit 的封鎖，iOS PWA 無法註冊至原生 Share Sheet。但我們可以透過前沿黑魔法實現無感 Ingress：

```
[使用者在 Google Maps 複製景點連結]
             │
             ▼
[切回 Tabidachi PWA (觸發 window.onfocus)]
             │
             ▼
[useSmartClipboardIngress Hook 檢測剪貼簿內容]
             │ 包含 maps.app.goo.gl 或 google.com/maps?
      ┌──────┴──────┐
      ▼ YES         ▼ NO
[頂部滑出優雅膠囊浮窗]   [靜默無動作]
"📍 偵測到地圖連結：淺草寺 [加入行程] [✕]"
             │ 點擊加入
             ▼
[調用既有 geocodeApi.resolveLink]
             │ 解析 lat, lng, title
             ▼
[自動開啟 ActivityEditModal 帶入數據]
```

*   **避坑指南**：
    *   **權限授權處理**：瀏覽器調用 `navigator.clipboard.readText()` 時若無使用者手勢，Safari 可能會拋出 `NotAllowedError`。架構上必須安全包裹 `try/catch`，若受阻則降級為在頂部常駐「📋 貼上地圖連結」微型按鈕，使用者點擊時才執行讀取。
    *   **防重複干擾**：維護 `lastCheckedUrl` 與 `dismissedUrls` 記憶體集合，使用者按過關閉或已加入過的網址，同一個 Session 內不再重複彈出。

### 3.2 外部喚醒：景點卡片 `openMapNavigation` 複合式原生喚醒
目前 `TimelineCard.tsx` 的導航按鈕過於單一。升級方案如下：

1.  **智慧平台分流**：
    *   **iOS 裝置**：
        *   首選 Apple Maps 原生導航：`maps://?daddr=${lat},${lng}&q=${encodeURIComponent(place)}`
        *   次選 Google Maps App：`comgooglemaps://?daddr=${lat},${lng}&directionsmode=walking`
        *   保底 Web：`https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`
    *   **Android 裝置**：
        *   原生 Intent：`geo:${lat},${lng}?q=${lat},${lng}(${encodeURIComponent(place)})`
        *   Google Maps：`https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`
2.  **日本在地交通擴充 (Navitime / Yahoo Japan)**：
    *   若活動分類為 `transport` 或地點名稱包含「站 / 駅 / 空港 / station」，彈出選單額外提供：
        *   `🚆 乘換案內 (Navitime/Yahoo!路線情報)` 快速查詢。
    *   提供 `📋 複製地址與座標` 便於貼入 Uber 或計程車 App。

---

## 四、 架構落地方案與代碼模組規劃 (Execution Blueprint)

### 模組 1：純前端 RFC 5545 日曆生成器 (`frontend/lib/calendar-generator.ts`)
*   **職責**：將 `Trip` 資料模型純函數式轉換為合規 RFC 5545 格式字串。
*   **核心函數**：
    *   `export function generateTripIcs(trip: Trip): string`
    *   `export function downloadIcsFile(trip: Trip): void`
    *   `export async function shareIcsFile(trip: Trip): Promise<boolean>`

### 模組 2：後端/邊緣 Webcal 訂閱路由
*   **端點**：`GET /api/trips/{trip_id}/calendar.ics`
*   **安全防護**：利用既有的 `public_id` 或簽署 Hash 存取，不公開內部私有 UUID；回傳 Header 設置：
    *   `Content-Type: text/calendar; charset=utf-8`
    *   `Cache-Control: public, max-age=60, s-maxage=300` (由 Cloudflare Tiered Cache 邊緣快取保護，0 伺服器壓力)。

### 模組 3：智能剪貼簿地圖注入 Hook (`frontend/lib/hooks/useSmartClipboardIngress.ts`)
*   **職責**：監聽 `window.onfocus`，正則探測剪貼簿中的 Google Maps 連結，以無感浮動膠囊引導使用者一鍵解析並注入行程。

### 模組 4：多地圖導航適配器 (`frontend/lib/map-navigation.ts`)
*   **職責**：封裝 Apple Maps, Google Maps, Navitime 的 Deep URL Schemes，提供給 `TimelineCard.tsx` 與景點詳細頁一鍵呼叫。
