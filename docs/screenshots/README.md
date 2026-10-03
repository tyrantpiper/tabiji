# 📸 Tabidachi 視覺資產中心與截圖清冊 (Screenshots & Visual Assets)

> **定位守則 (Master Doctrine)**:  
> 本目錄為 Tabidachi 專案所有截圖與視覺二進位資產的**單一真實來源 (Single Source of Truth)**。  
> 嚴格實施「宣傳展示 (Showcase)」與「實機驗收 (Verification)」物理分流，杜絕測試證據截圖散落於報告或代碼目錄中。

---

## 🗂️ 資產分類結構

```
docs/screenshots/
├── README.md                                 # [總中樞] 本視覺資產清冊與引用規範
├── showcase/                                 # 🌟 產品核心功能宣傳展示圖 (用於 README.md Banner)
│   ├── ai-chat.png                           # Ryan AI 旅遊伴侶與批次景點選取器
│   ├── expense-tracker.png                   # 多法幣記帳、即時匯率換算與深度定位高亮
│   ├── route-map.png                         # 全螢幕 MapLibre 向量地圖、大圓航線與多運具切換
│   ├── timeline-cards.png                    # 行程時間軸景點卡片、多月份連續滾動日曆
│   └── weather-itinerary.png                 # 行程封面總覽、Linvill 氣溫曲線與 5 天氣象條
└── verification/                             # 🔍 E2E 自動化測試、Playwright 截圖與 QA 實機物理證據
    ├── aviasales_deep_link_verified.png      # 航班深層連結跳轉驗證截圖
    ├── aviasales_search_success_verified.png # 航班查詢成功狀態驗證截圖
    ├── flight_comparison_accordion_verified.png # 機票比價手風琴折疊卡片驗證
    ├── italy_flight_search_verified.png      # 義大利長途跨國航線查詢驗證
    ├── offline-itinerary-screen-proof.png    # 實機離線行程渲染物理證據
    └── offline-swipe-reopen-proof.png       # 實機離線滑掉重開零白屏物理證據
```

---

## 🌟 1. 產品核心展示圖清冊 (`showcase/`)

專供根目錄 `README.md` 與 `frontend/README.md` 首頁橫幅展示使用（建議尺寸寬度 180px~390px Retina 2x）：

| 檔案名稱 | 展示功能名稱 | 視覺特點與展示亮點 | 引用位置 |
| :--- | :--- | :--- | :--- |
| **`weather-itinerary.png`** | 行程總覽與五天天氣 | 展示封面大卡片、多日氣象條動態預報與 Linvill 日夜溫差折線。 | `README.md` (Banner)<br>`frontend/README.md` |
| **`timeline-cards.png`** | 時間軸景點與日曆 | 展示每日行程時間軸、景點狀態標籤與連續縱向滾動月份日曆。 | `README.md` (Banner)<br>`frontend/README.md` |
| **`route-map.png`** | 全景地圖與移動軌跡 | 展示 MapLibre WebGL 衛星/向量切換、大圓航線插值彩帶與地圖呼吸膠囊。 | `README.md` (Banner)<br>`frontend/README.md` |
| **`ai-chat.png`** | Ryan AI 智慧助理 | 展示 iOS 液態玻璃懸浮圓球、對話面板、即時在地 Grounding 來源徽章。 | `README.md` (Banner)<br>`frontend/README.md` |
| **`expense-tracker.png`** | 記帳與匯率轉換 | 展示 110+ 主權法幣切換、本地多層 SVG 國旗、記帳明細與圖表。 | `README.md` (Banner)<br>`frontend/README.md` |

---

## 🔍 2. 實機測試物理證據清冊 (`verification/`)

供自動化整合測試斷言與架構排查報告鏈接之用：

| 檔案名稱 | 測試/驗證主題 | 關聯測試檔案 / 腳本 | 關聯排查報告 |
| :--- | :--- | :--- | :--- |
| **`offline-swipe-reopen-proof.png`** | iOS Standalone PWA 離線滑掉重開零白屏驗證 | `frontend/__tests__/offline-pwa-integrity.test.ts` (TC-7)<br>`frontend/scripts/verify-offline-swipe-reopen.mjs` | [offline-refresh-white-screen-deep-dive.md](file:///d:/Project/Tabidachi/travel-pwa/docs/reports/offline-refresh-white-screen-deep-dive.md) |
| **`offline-itinerary-screen-proof.png`** | 斷網狀態下載入快取離線景點與底部導航驗證 | `frontend/scripts/verify-offline-itinerary-screen.mjs` | [offline-refresh-white-screen-deep-dive.md](file:///d:/Project/Tabidachi/travel-pwa/docs/reports/offline-refresh-white-screen-deep-dive.md) |
| **`aviasales_deep_link_verified.png`** | OTA 航班直連帶參聯盟行銷跳轉驗證 | 航班比價 E2E 測試 | [flight-pricing-and-airport-spec.md](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/business/flight-pricing-and-airport-spec.md) |
| **`aviasales_search_success_verified.png`**| 即時機票搜尋 API 成功解析與渲染驗證 | 航班比價 E2E 測試 | [flight-pricing-and-airport-spec.md](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/business/flight-pricing-and-airport-spec.md) |
| **`flight_comparison_accordion_verified.png`** | 航班卡片手風琴互動展開與同城短路驗證 | `flight-price-comparison.test.tsx` | [flight-pricing-and-airport-spec.md](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/business/flight-pricing-and-airport-spec.md) |
| **`italy_flight_search_verified.png`** | 跨洲際長途機票查詢與貨幣換算驗證 | 航班比價 E2E 測試 | [flight-pricing-and-airport-spec.md](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/business/flight-pricing-and-airport-spec.md) |

---

## 📌 截圖資產管理規範

1. **禁止直接放置於 `screenshots/` 根目錄**：任何新截圖必須明確歸入 `showcase/`（宣傳圖）或 `verification/`（測試證據）。
2. **截圖腳本防護義務**：Playwright 或 Puppeteer 自動化截圖腳本必須在調用 `page.screenshot({ path })` 前宣告：
   ```javascript
   const dir = path.dirname(screenshotPath);
   if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
   ```
3. **測試斷言路徑**：凡依賴實體截圖存在的 Vitest / Jest 單元測試，路徑一律錨定至 `docs/screenshots/verification/`。
