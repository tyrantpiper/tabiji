# 🧠 全域神經縫隙拓撲與不變量全景大冊 (Neural Seam Topology & Invariant Matrix)

> **版本**: `1.0.0` (Canonical Spec)  
> **狀態**: `APPROVED & RATIFIED`  
> **領域**: `core-architecture`  
> **臨床架構守則**: 程式碼編譯成功與單元測試綠燈（0 Error）不等於沒有退化。猶如外科手術，主病灶切除成功後，遠端組織可能因神經牽拉、缺血痙攣或電解質失衡而產生隱性「手術後遺症 (Surgical Sequelae)」。本文件確立 Tabiji 全棧 6 大神經叢、所有目錄檔案之神經相依關係，以及跨模組縫隙（Surgical Seams）的核心不變量防衛標準。

---

## 一、系統六大神經叢解剖總圖 (The Six Major Neural Plexuses)

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Tabiji 全域六大神經叢架構                        │
└────────────────────────────────────────────────────────────────────────┘
  [1. 感官與運動神經叢 Sensory-Motion]    [2. 本機存儲與快取神經叢 Storage-Cache]
  • frontend/components/views/           • frontend/lib/idb-storage.ts
  • frontend/components/layout/          • frontend/lib/stores/*.ts
  • frontend/lib/spatial-tab-topology.ts • frontend/lib/idb-swr-provider.tsx
  • frontend/components/bottom-nav.tsx   • public/sw.js (Service Worker)
                │                               │
                ▼                               ▼
  [3. 地理運算與畫布神經叢 Geo-Canvas]     [4. 智能推理與即時串流神經叢 AI-Stream]
  • frontend/components/day-map.tsx      • frontend/components/chat-widget.tsx
  • MapControlCapsule.tsx                • frontend/lib/sse-parser.ts
  • frontend/lib/geo-multi-day.ts        • backend/routers/ai.py & agents.py
  • MapLibre GL JS WebGL Canvas          • backend/services/model_manager.py
                │                               │
                ▼                               ▼
  [5. 業務精算與生命週期神經叢 Business]    [6. 邊緣網關與基礎設施神經叢 Infra-Edge]
  • GlobalTaxActuary.tsx                 • cloudflare/edge-shield/worker.js
  • frontend/lib/currency.ts             • backend/main.py (FastAPI Lifespan)
  • backend/routers/trips.py             • backend/Dockerfile (Gunicorn Keep-Alive)
  • backend/routers/capsules.py          • Supabase PostgreSQL Migrations / RLS
```

---

## 二、目錄與檔案神經解剖清冊 (Comprehensive Anatomical Inventory)

### 1. 感官與運動神經叢 (Sensory & Motion Plexus)
- **`frontend/components/views/app-shell.tsx`**: 全站頂層視圖宿主。
  - *神經輸入*: `BottomNav` 點擊、深層網址參數、推播 `navigate` 自訂事件。
  - *神經輸出*: `activeView` 狀態分流、`calculateTabOffset` 動態位移、視圖背景預熱。
  - *脆弱縫隙 (Seam)*: 視圖切換事件若繞過協調器直接調用 `setActiveView`，會凍結空間方向；在 JSX 中直接讀取 `useRef.current` 會觸發 React 19 編譯報警。
- **`frontend/lib/spatial-tab-topology.ts`**: 純函數相對空間拓撲引擎。
  - *輸入*: `targetTab`, `currentActiveTab`, `transitionIntent`, `isReducedMotion`。
  - *輸出*: 確定性數值位移（`0 | 28 | -28` px）。
  - *脆弱縫隙 (Seam)*: 非法字串若未經 `?? 0` 箝位會引發 `NaN` 座標漂移。
- **`frontend/components/bottom-nav.tsx`**: 觸覺回饋底部導航。
  - *輸入*: 點擊手勢、目前作用中分頁。
  - *輸出*: `haptic.selection()`、`onTabChange`。
  - *脆弱縫隙 (Seam)*: 控制項邊框與背景依賴 React runtime hydration 會引發首屏色彩跳動 (FOUC)。
- **`frontend/components/layout/` & `frontend/components/ui/`**: 擬物化按鈕與彈窗組件。
  - *脆弱縫隙 (Seam)*: 卡片內部按鈕若嵌套 `<button>` 會引發 DOM 違法與事件冒泡失控。

---

### 2. 本機存儲與快取神經叢 (Storage & Cache Plexus)
- **`frontend/lib/idb-storage.ts`**: 本地離線儲存引擎（三級容錯：記憶體 ➔ IDB ➔ LocalStorage）。
  - *神經輸入*: Zustand `persist` 序列化、SWR 資料快照。
  - *神經輸出*: 客戶端開機狀態還原、離線查詢。
  - *脆弱縫隙 (Seam)*: 序列化包含未決 Promise 會引發 `DataCloneError`；未加載版本號會引發綱要錯位。
- **`frontend/lib/stores/tripStore.ts`**: 行程全域狀態真理。
  - *輸入*: SWR 異步資料、使用者的樂觀天數裁剪與切換。
  - *輸出*: `activeTripId`, `activeTripTitle` 響應式訂閱。
  - *脆弱縫隙 (Seam)*: 跨帳號引繼時若未清空 Zustand 持久化快照，會造成舊行程逆向污染新帳號。
- **`frontend/lib/stores/weatherStore.ts`**: 氣象非同步多天快取。
  - *輸入*: Open-Meteo 經緯度五日預報。
  - *輸出*: `fiveDayCache` 字典。
  - *脆弱縫隙 (Seam)*: 元件若在 `useEffect` 中直接 setState 外部資料，會在父層 re-render 時被清理閉包誤殺。
- **`public/sw.js` & `frontend/app/sw.ts`**: PWA 離線 Service Worker。
  - *脆弱縫隙 (Seam)*: 動態編譯 Chunks 若放入 Precache，雲端部署更新 Hash 後會引發 404 毒丸摧毀 SW。

---

### 3. 地理運算與畫布神經叢 (Geospatial & Canvas Plexus)
- **`frontend/components/day-map.tsx` & `MultiDayMasterMap.tsx`**: MapLibre GL JS WebGL 畫布視圖。
  - *神經輸入*: 經緯度座標池、相機角度 (pitch, bearing)、大圓航線插值。
  - *神經輸出*: WebGL Canvas 渲染、`MapControlCapsule` 互動。
  - *脆弱縫隙 (Seam)*: 浮動手勢節點若直接以 `right/bottom` 定位，會引發 Layout Reflow 迫使 GPU 重繪畫布造成掉幀；宣告 `beforeId` 指向未預載圖層會引發致命白屏。
- **`frontend/components/MapControlCapsule.tsx`**: 呼吸降敏地圖控制膠囊。
  - *脆弱縫隙 (Seam)*: 觸控螢幕會黏滯 `:hover` 偽類，指針事件必須以 `pointerType === 'mouse'` 隔離。
- **`frontend/lib/geo-multi-day.ts`**: 球面幾何大圓航線插值演算法。
  - *輸出*: Day 1~5 高對比飽和色彩航線 GeoJSON。
- **`frontend/scripts/copy-maplibre-worker.mjs`**: 同源 CSP 靜態 Worker 管線。
  - *保證*: 嚴格同源派發，禁止 `blob:` 遭到嚴格 CSP 標頭攔截。

---

### 4. 智能推理與即時串流神經叢 (AI & Stream Plexus)
- **`frontend/components/chat-widget.tsx`**: AI 旅伴高密度對話視圖。
  - *神經輸入*: 使用者語音/文字、SSE 串流分塊。
  - *神經輸出*: 結構化 Tool Calls、行程建議匯入事件 (`ai-import-itinerary`)。
  - *脆弱縫隙 (Seam)*: 輸入法 IME 組合態若未在 `onKeyDown` 攔截，會提前觸發發送；暴力拆檔會遺失閉包自癒狀態。
- **`frontend/lib/sse-parser.ts`**: 健壯的 Server-Sent Events 解析器。
  - *防線*: 支援換行與黏包處理、Thought Signature 解析、Function Calling 雙格式提取。
- **`backend/routers/ai.py` & `backend/services/model_manager.py`**: 後端模型路由與神經防護。
  - *神經輸出*: Gemini 3.1 Flash-Lite / 2.5 雙軌調度、多模態收據辨識。
  - *脆弱縫隙 (Seam)*: 提示詞未加隨機鹽漬標籤與 `[SYSTEM_SHIELD]` 三明治提醒，易遭惡意注入越獄。
- **`backend/services/intent_router.py`**: 旅伴意圖前置分流平面。
  - *職責*: 預算閥門、搜尋工具白名單、旅遊領域意圖分類。

---

### 5. 業務精算與生命週期神經叢 (Business Logic Plexus)
- **`frontend/components/tools/GlobalTaxActuary.tsx`**: 全球免稅精算與雙卡拆單神策。
  - *防線*: Zero-Eval AST 詞法解析器，杜絕 `eval()` 注入；台灣信用卡 1.5% 手續費與封頂計算。
- **`backend/routers/trips.py`**: 行程核心增刪改查與改期引擎。
  - *脆弱縫隙 (Seam)*: 改期若做骨牌式位移算術，會將所有活動擠壓至 Day 1；必須採「天數序號絕對保持律」。
- **`backend/routers/capsules.py`**: 旅伴時光膠囊。
  - *脆弱縫隙 (Seam)*: 非本人未公開膠囊僅靠前端 CSS blur 遮罩會引發 BOLA 漏洞；必須在伺服端直接實體脫敏。
- **`backend/routers/expenses.py`**: 行程記帳與分帳路由。
  - *防線*: 支援多法幣實時匯率轉換與離線冪等性。

---

### 6. 邊緣網關與基礎設施神經叢 (Infra & Edge Plexus)
- **`cloudflare/edge-shield/worker.js`**: 邊緣反向代理與標頭覆寫。
  - *職責*: 動態覆寫 `Host: antigravity-backend-*.run.app` 解鎖 Google Cloud Run GFE 404 限制；注入 5 大安全標頭。
- **`backend/main.py`**: FastAPI 應用程式中樞與 Lifespan。
  - *神經防線*: `/health` 端點純記憶體計算（0ms）；Supabase 保活獨立非同步循環；Uvicorn `timeout_keep_alive=65`。
- **`backend/Dockerfile` & `backend/Dockerfile.prod`**: 容器化生產規格。
  - *防線*: Gunicorn 與 Uvicorn 強制注入 `--keep-alive 65`，逆向覆蓋反向代理層 60 秒視窗。
- **`supabase/migrations/`**: PostgreSQL 資料庫與 RLS 安全策略。
  - *防線*: 資料表複合唯一約束（`uq_trip_capsule_user_day`）、RowExclusiveLock 原子 UPSERT。

---

## 三、十大手術脆弱縫隙與核心不變量矩陣 (Ten Critical Surgical Seams)

| 縫隙編號 (Seam ID) | 跨模組牽涉路徑 | 手術後遺症 (Surgical Sequelae) | 核心不變量檢驗標準 (Invariant Contract) |
|:---|:---|:---|:---|
| **SEAM-01: 導航拓撲** | `app-shell.tsx` ⇄ `spatial-tab-topology.ts` | 點擊切換時頁面逆向滑動、冷啟動無動畫 | **[AD-115/118]** 動態 initial 座標確定性滑入，任意合法與非法輸入均無 `NaN`。 |
| **SEAM-02: 渲染純粹** | `components/views/*.tsx` ⇄ React 19 Compiler | 渲染階段讀取 Ref、串聯更新造成介面卡頓 | **[AD-117]** 嚴格遵守純函數規範，Render Phase 零 Ref 存取，0 Linter 警告。 |
| **SEAM-03: 快照持久** | `tripStore.ts` ⇄ `idb-storage.ts` ⇄ SWR | 切換視圖或斷網時誤刪本機草稿與行程 | **[AD-077]** 視圖切換前後快照守恆；SWR 404 嚴禁無核驗清空本機快取。 |
| **SEAM-04: 地圖隔離** | `day-map.tsx` ⇄ WebGL Canvas ⇄ GPU 合成 | 拖曳手勢造成地圖掉幀至 20fps、上下文洩漏 | **[AD-071]** 浮動元素強制隔離 GPU 合成層；全站 Canvas 節點卸載時完全釋放。 |
| **SEAM-05: 日期改期** | `trips.py` ⇄ `CalendarRangeSheet.tsx` | 改期導致活動被骨牌位移雙重覆寫 | **[AD-099]** 天數序號 Day 1~N 絕對保持，縮短時由使用者指定合併或刪除。 |
| **SEAM-06: 時區安全** | `frontend/lib/timezone.ts` ⇄ `backend/main.py` | UTC+8 西半球跨日運算回退、naive/aware 崩潰 | **[AD-098]** 本地日期構造純函數運算；後端伺服器全域時間標註 `timezone.utc`。 |
| **SEAM-07: 精算安全** | `GlobalTaxActuary.tsx` ⇄ `tax-rules/` | 計算機輸入運算式誘發 XSS 或執行注入 | **[AD-079]** 雙階段 Zero-Eval AST 詞法求值，除以零安全降級，無 `eval()`。 |
| **SEAM-08: 膠囊防窺** | `capsules.py` ⇄ `CapsuleUnveilingCeremony.tsx` | 破印前非本人資料在前端遭到審查穿透 (BOLA) | **[AD-105]** 後端實體脫敏，未破印前內容強制為 `None`，不依賴 CSS blur。 |
| **SEAM-09: 邊緣保活** | `backend/Dockerfile` ⇄ Gunicorn ⇄ Uvicorn | Keepalive 階層倒掛引發客戶端 `ECONNRESET` | **[AD-110]** 容器啟動參數強制宣告 `--keep-alive 65`，覆蓋代理端 60 秒視窗。 |
| **SEAM-10: 離線防毒** | `idb-storage.ts` ⇄ LocalStorage ⇄ SWR Provider | 損壞快照造成冷啟動白屏、Prototype 污染 | **[AD-081]** 原生結構化克隆隔離，解析錯誤安全回退 `null`，嚴格版本比對。 |

---

## 四、神經守門整合規範 (Workflow Integration)

1. **本地手動調度**:
   ```bash
   python scripts/neural_seam_harness.py
   ```
2. **統一大門整合 (`/test --seam`)**:
   在執行 `/test --seam` 時，僅針對這 10 大縫隙執行高敏微感測，於 1 秒內輸出「手術後遺症診斷書」。
3. **發布守門 (`/push`)**:
   在 Step 0 根目錄衛生之後，強制執行 `neural_seam_harness.py`；檢測到任何 P0/P1 手術後遺症時，立即物理熔斷阻斷推送。
