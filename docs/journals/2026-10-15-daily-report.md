# 📅 Daily Report - 2026-10-15 (Trip Time Capsule, BOLA Defense, Portal Unveiling Ceremony & Tabiji Push Dual-Track Compatibility)

> **系統狀態**：🟢 Production Deployed & Synced (`9ba8073`), 0 TypeScript Errors, 0 ESLint Warnings, 100% Tests Green (Frontend 72/72 Suites Passing, 475/475 Tests Passing; Backend 157/157 Tests Passing, 5 skipped), Working Tree Clean, GitHub main branch synced.  
> **今日關鍵提交串列 (Full Day Commit Stream)**：
> - [`9ba8073`](https://github.com/tyrantpiper/tabiji/commit/9ba8073) `feat(capsule): implement trip time capsule with BOLA defense and portal unveiling ceremony` (2026-10-15 00:05:48 +0800)
> - 連帶整合對話跨度：`@[conversation:"Tabidachi Availability Locations"]` (`3534bbd5-c8fc-486e-a52f-be32e93a0969`) 與時光膠囊破印盛典驗收對話 (`2257e53d-f5ee-40f7-8594-51dbd48fcd6e`)

---

## 🏆 深度專案復盤：六大工程與架構里程碑 (Six Core Milestones)

本次研發循環跨越對外品牌遷移與多旅伴時光膠囊系統，完成了資料庫 Row-level 唯一性鎖定、後端 BOLA 防窺脫敏、React 19 Portal 頂層隔離、動態視窗高度自適應、React Compiler Cascading Render 根除，以及 Windows 原生滾動條跨平台洗滌：

---

### 里程碑一：對外分享元資料與 Supabase Web Push 品牌對齊 ✕ 雙軌相容層 (Tabiji Push Rebranding & Dual-Track Compatibility)
*(源自對話 `3534bbd5-c8fc-486e-a52f-be32e93a0969`)*

1. **業務挑戰與老用戶離線斷裂痛點**：
   - 專案由 `Tabidachi` 全面重構並定案為品牌 **`Tabiji 旅路`**。然而，對外公開分享行程頁面（`PublicTripView.tsx`）、社群分享卡片（`ShareButton.tsx`）與 HTML Title 仍遺留舊商標。
   - 若直接暴力替換 Service Worker 內部通訊協議（將 `TABIDACHI_PUSH_NAVIGATE` 硬改為 `TABIJI_PUSH_NAVIGATE`），已將 PWA 加入手機主畫面但尚未重啟 Service Worker 的數百名老用戶，在收到雲端推播並點擊通知時，底層路由解析器將無法識別舊事件代碼，引發「點擊推播無法自動跳轉行程」之嚴重體驗斷裂。
2. **雙軌相容性跳轉架構 (Dual-Track Push Routing)**：
   - 於 [`frontend/lib/hooks/useDeepLinkRouter.ts`](file:///d:/Project/Tabidachi/travel-pwa/frontend/lib/hooks/useDeepLinkRouter.ts) 實裝雙軌事件監聽：
     ```typescript
     const isPushNavigate =
       (event.data?.type === "TABIJI_PUSH_NAVIGATE" || event.data?.type === "TABIDACHI_PUSH_NAVIGATE") &&
       event.data?.url;
     ```
   - Service Worker 新版事件派發升級為 `TABIJI_PUSH_NAVIGATE`，推播標題預設保底為 `Tabiji 旅路`；廣播維護腳本 [`scripts/broadcast.ps1`](file:///d:/Project/Tabidachi/travel-pwa/scripts/broadcast.ps1) 控制台日誌同步規格化，達成新舊版本完全平滑無感銜接。

---

### 里程碑二：旅伴時光膠囊資料庫架構 ✕ BOLA 伺服端實體防窺脫敏 (Time Capsule Schema & BOLA Redaction Engine)
1. **業務場景與防窺心智模型**：
   - 旅伴在旅行中每天各自寫下當日真心話與上傳照片（如拍立得）。在行程尚未結束前，為了保持神秘感與驚喜度，旅伴彼此**絕對不可提前偷看**對方寫了什麼；只有本人能查看自己的日記，並看到其他旅伴是否已打勾提交。
   - 當整趟旅程結束（或破印時間抵達）時，系統才進行全體公開解鎖（Unveil），共同回顧旅行點滴。
2. **資料庫層級唯一性與並發死鎖防禦**：
   - 在 [`supabase/migrations/20261014_trip_capsules.sql`](file:///d:/Project/Tabidachi/travel-pwa/supabase/migrations/20261014_trip_capsules.sql) 建立 `trip_capsule_entries` 資料表，並注入複合唯一鍵約束：
     `CONSTRAINT uq_trip_capsule_user_day UNIQUE (trip_id, day_number, author_id)`。
   - 寫入時採用 PostgreSQL 原生 `ON CONFLICT (trip_id, day_number, author_id) DO UPDATE`。摒棄傳統「先 SELECT 是否存在，再 INSERT 或 UPDATE」的兩階段反模式，在行級取得 `RowExclusiveLock`，徹底根治死鎖（Deadlock-Free），且具備完全的冪等性（Idempotency）。
3. **後端 BOLA (Broken Object Level Authorization) 防窺實體脫敏**：
   - 傳統前端若僅在 UI 蓋上「霧面馬賽克遮罩」，駭客或同伴只要打開瀏覽器 DevTools Network Payload 就能提前截獲真實文字與圖片。
   - 在 [`backend/routers/capsules.py`](file:///d:/Project/Tabidachi/travel-pwa/backend/routers/capsules.py) 建立嚴密的伺服端分流管線：
     - 行程未結束期間：非本人之記錄，後端直接在資料序列化時將 `mood_emoji`、`content`、`photo_url` 實體重設為 `None`，僅傳遞 `author_name` 與 `created_at` 作為進度統計；即便抓取 raw JSON 亦為空，從根本物理阻斷 BOLA 漏洞。
     - 破印時間抵達：全量解鎖真實資料。解鎖後修改 POST 端點立即凍結，回傳 `HTTP 403 Forbidden`，防止回憶被惡意篡改。

---

### 里程碑三：伺服端實名化雙軌 Profile 批次解析 (Server-Side Real-Name Profile Hydration)
1. **N+1 查詢崩潰隱患**：
   - 時光膠囊條目僅存儲 `author_id: UUID`。若在遍歷 entries 時逐筆調用資料庫獲取使用者名稱與頭像，在 16 天行程且 4 位旅伴的情況下將引發高達 64 次重複 SQL 查詢，嚴重拖慢 API 響應時間。
2. **O(1) 記憶體映射與雙軌批次融合**：
   - 後端首先聚合所有獨立作者 UUID：`author_uuids = list(set(...))`。
   - **第 1 軌 (Global Users Profile)**：透過 `supabase.table("users").in_("id", author_uuids)` 一次性檢索全域註冊名稱與頭像。
   - **第 2 軌 (Trip Members Nickname Overlay)**：透過 `supabase.table("trip_members").eq("itinerary_id", trip_id)` 檢索行程專屬暱稱與自訂頭像，覆寫覆蓋為成員最真實的稱呼。
   - 經由 O(1) Memory Map 高速拼接，資料庫查詢次數恆等於 2 次，消滅 N+1 查詢。

---

### 里程碑四：React Portal 頂層隔離 ✕ 動態視窗高度防截斷大師級重構 (Portal Isolation & Viewport-Safe Budget)
1. **四大導覽列穿透與卡片截斷雙重缺陷**：
   - 破印盛典彈窗原先掛載於 `itinerary-view.tsx` 的 `<motion.div>` 內部。由於 Framer Motion 的 `transform` 動畫屬性會強制在瀏覽器中產生新的 **Stacking Context (堆疊上下文)**，導致內部宣告 `z-[120]` 仍然被囚禁在父容器內，被外部 AppShell 的常駐 `BottomNav` (`z-100`) 實體穿透遮蔽。
   - 同時，中央拍立得卡片採用固定比例高寬，在 667px (iPhone SE) 窄屏設備上直接硬撐，將底部的多旅伴切換 Pills、切換箭頭與引導提示推擠出視窗底部（截斷超過 61px）。
2. **大師級工程解決方案**：
   - **React Portal 根節點物理隔離**：使用 `createPortal(..., document.body)`，將破印盛典直接掛載至 HTML `<body>`，徹底擺脫 Framer Motion 的 Stacking Context 囚禁，以純粹的 `z-120` 100% 覆蓋四大常駐導覽列與頂部 AI 懸浮球。
   - **動態視窗高度單位 (100dvh)**：採用 `h-dvh max-h-dvh` 消除行動端 Safari / Chrome 網址列伸縮時的跳動。
   - **40vh 垂直預算防截斷約束**：卡片限制為 `max-h-[40vh]` 雙向縮放；中央容器宣告 `min-h-0 overflow-y-auto overscroll-contain`，並配置 Body Scroll Lock (`overflow: hidden`) 與鍵盤 `Escape` 安全退出，保證從小螢幕到桌面端截斷率嚴格歸零。

---

### 里程碑五：React 19 `useSyncExternalStore` 客戶端水合 ✕ 零 Cascading Render 重構
1. **React Compiler 嚴苛規範報錯**：
   - 原先組件採用經典的客戶端掛載判斷：
     ```tsx
     const [mounted, setMounted] = useState(false)
     useEffect(() => { setMounted(true) }, [])
     ```
   - React 19 與 React Compiler 嚴禁在 `useEffect` 中同步執行 `setState`，因為這會在首幀後立即觸發二次串聯渲染（Cascading Renders），引發效能抖動與 ESLint `react-hooks/set-state-in-effect` 致命報錯。
2. **標準外部 Store 訂閱架構**：
   - 引入 React 18/19 官方推薦之 `useSyncExternalStore`：
     ```tsx
     const emptySubscribe = () => () => {}
     const getClientSnapshot = () => true
     const getServerSnapshot = () => false

     export function CapsuleUnveilingCeremony(...) {
         // 🛡️ SSR 安全守衛 (使用 useSyncExternalStore 確保無 cascading render 且客戶端安全執行 createPortal)
         const isClient = useSyncExternalStore(emptySubscribe, getClientSnapshot, getServerSnapshot)
         if (!isClient) return null
         ...
     }
     ```
   - SSR 渲染時快照精確回傳 `false`，客戶端水合瞬間精確回傳 `true`，**0 次額外重新渲染**，徹底消滅 Cascading Render 錯誤，並通過 React Compiler 嚴苛編譯。

---

### 里程碑六：Windows 原生捲軸洗滌 ✕ 全域 `.scrollbar-none` 跨平台標準化
1. **Windows 原生白色上下箭頭按鈕驚魂**：
   - 中央卡片容器為了防截斷配置了 `overflow-y-auto`。在 Windows 系統下的 Chrome / Edge 瀏覽器中，當卡片高度稍微有些微溢出時，Windows 會強制渲染出原生非浮動滾動條。
   - 由於容器高度被嚴格壓縮，原生滾動條滑塊沒有滑動空間，導致頂部的「向上微調按鈕 `▲`」與底部的「向下微調按鈕 `▼`」直接縮合成一個白色底、灰色箭頭的突兀長方塊，破壞暗色深松星夜美學。
2. **跨平台樣式重設與注入**：
   - 發現全專案雖然散佈 `scrollbar-none` class，但在 `globals.css` 中從未宣告其實體樣式。
   - 於 [`frontend/app/globals.css`](file:///d:/Project/Tabidachi/travel-pwa/frontend/app/globals.css#L341-L356) 注入標準跨平台規範：
     ```css
     @utility scrollbar-none {
       scrollbar-width: none;
       -ms-overflow-style: none;
       &::-webkit-scrollbar {
         display: none;
       }
     }
     .scrollbar-none {
       scrollbar-width: none;
       -ms-overflow-style: none;
     }
     .scrollbar-none::-webkit-scrollbar {
       display: none;
     }
     ```
   - 徹底根除 Windows Chrome/Edge 原生白底箭頭，維持極致沉浸之深松和紙氛圍。

---

## 🏛️ 架構決策紀錄 (Architecture Decisions)

- **AD-104: 旅伴時光膠囊複合唯一約束與行排他鎖 UPSERT (Compound Unique Key & Deadlock-Free UPSERT)**:
  時光膠囊資料表建立 `CONSTRAINT uq_trip_capsule_user_day UNIQUE (trip_id, day_number, author_id)`。寫入操作一律採用原生 PostgREST `upsert(..., on_conflict="trip_id,day_number,author_id")`，在 PostgreSQL 內部獲取 `RowExclusiveLock`，達成單次操作原子性、零死鎖與完全冪等性。
- **AD-105: 伺服端實體脫敏取代純表現層模糊遮罩 (Server-Side BOLA Redaction over Client-Side Blur)**:
  時光膠囊在行程進行期間，非本人條目由 FastAPI 後端直接將 `mood_emoji`、`content`、`photo_url` 設為 `None`，只回傳完成狀態。堅決杜絕僅靠前端 CSS `blur` 的偽防窺，自根源物理阻斷 BOLA 漏洞。
- **AD-106: 雙軌相容推播訊息路由協議 (Dual-Track Push Navigation Protocol)**:
  品牌更名時，PWA Service Worker 通訊協議嚴禁單方面硬升級。`useDeepLinkRouter` 同時相容 `TABIJI_PUSH_NAVIGATE` 與 `TABIDACHI_PUSH_NAVIGATE` 雙重事件，保障已安裝桌面 PWA 離線老用戶零斷裂。
- **AD-107: React Portal 頂層逃逸與動態視窗高度安全預算 (React Portal Root Escape & 40vh Budget)**:
  全屏回顧或破印彈窗一律透過 `createPortal(..., document.body)` 逃離 Framer Motion 的 Stacking Context 囚禁；視窗高度鎖定 `h-dvh max-h-dvh`，中央卡片預算壓制於 `max-h-[40vh]` 搭配 `overflow-y-auto`，確保 667px (iPhone SE) 設備底部旅伴 Pills 與控制列 100% 不截斷。
- **AD-108: `useSyncExternalStore` 客戶端渲染守衛原則 (Hydration Guard via useSyncExternalStore over useEffect)**:
  需要判斷客戶端掛載以渲染 Portal 的情境，全面廢止 `useEffect + setState` 模式，改採 React 官方標準 `useSyncExternalStore(emptySubscribe, () => true, () => false)`，達成 0 次二次渲染，全面通過 React 19 與 React Compiler 純粹性檢查。
- **AD-109: 跨平台滾動條重設單一來源原則 (Cross-Platform Invisible Scrollbar Invariance)**:
  在暗色沉浸式彈窗中，任何標註 `scrollbar-none` 的可滾動容器必須在全域 `globals.css` 具備 `scrollbar-width: none` 與 `::-webkit-scrollbar { display: none }` 雙重定義，杜絕 Windows 原生白色 Stepper 箭頭破功露餡。

---

## 🛡️ 失敗路徑與踩坑教訓 (Failed Paths & Debugging Lessons)

- **FP-031: Framer Motion Stacking Context 囚禁彈窗層級陷阱**:
  在 `itinerary-view.tsx` 內部直接渲染全屏 Overlay，儘管配置了 `z-[120]`，但因外層 `<motion.div>` 具備 `transform` 動畫屬性，建立了新的 Stacking Context，導致彈窗永遠被外層 `BottomNav` (`z-100`) 遮蔽。教訓：全屏 Modal 必須透過 `createPortal` 脫離一切父層 Transform 容器直掛 `document.body`。
- **FP-032: 固定比例卡片擠壓底部按鈕截斷陷阱**:
  初版拍立得卡片採用固定 `w-72 aspect-[3/4.2]`（高度約 403px），加上 Header (72px)、天數橫條 (44px) 與 Footer (44px)，在 iPhone SE (667px) 上直接超出視窗 61px，導致旅伴切換箭頭被推入虛無。教訓：卡片必須設置 `max-h-[40vh]` 自適應收縮，且外層容器必須為 `min-h-0 flex-1 overflow-y-auto` 保底。
- **FP-033: `useEffect` 同步 `setMounted(true)` 引發 Cascading Render 報錯陷阱**:
  為防止 SSR 渲染 Portal 拋出 `document is not defined`，在組件內撰寫 `useEffect(() => setMounted(true), [])`，遭 React Compiler 判定為觸發 cascading render 違反純粹性。教訓：判斷客戶端環境應採用 `useSyncExternalStore`。
- **FP-034: Tailwind v4 未定義 `@utility scrollbar-none` 導致 Windows 原生滾動條暴露陷阱**:
  誤以為 Tailwind 內建 `scrollbar-none`，在 macOS 上因系統預設隱藏捲軸而未察覺，在 Windows Chrome/Edge 上卡片高度稍有溢出即浮現白底灰色 `▲ / ▼` 原生按鈕。教訓：跨平台捲軸隱藏必須在全域 CSS 明確宣告標準 `@utility scrollbar-none`。

---

## 🔴 技術債務與待辦清單 (Technical Debt & Next Steps)

1. **時光膠囊實機推播通知聯動**:
   - 目前已具備破印盛典介面與 API，下一階段可於雲端排程器（Cloudflare Cron 或 Supabase Webhook）於行程結束當天自動發送「📭 旅伴時光膠囊破印盛典已開啟」推播通知。
2. **離線 IndexedDB 暫存未送出之時光膠囊**:
   - 若旅伴在飛機上或深山無網路環境撰寫真心話，目前依賴即時 POST。未來可引入 `BackgroundSync` 或草稿 IndexedDB 本地存檔，待連線後自動上傳。
3. **拍立得卡片匯出相片圖檔 (Canvas Snapshot)**:
   - 支援將翻轉後的拍立得真心話卡片透過 `html-to-image` 匯出為高畫質 PNG，供旅伴儲存至手機相簿或分享至 Instagram Stories。

---

## 📊 驗收指標摘要 (Acceptance Metrics)

```powershell
# 1. 靜態型別與語意校驗
npx tsc --noEmit                -> Exit Code: 0 (0 errors)
npm run lint                    -> Exit Code: 0 (0 errors, 0 warnings)

# 2. 自動化測試覆蓋
Frontend Vitest Suite           -> 72 passed / 72 files (475/475 tests passed)
Backend Pytest Suite            -> 157 passed / 157 tests (5 skipped, 0 failed)

# 3. 生產打包構建
next build (Turbopack)          -> Compiled successfully in 2.1s, TS 7.6s, 10/10 Static Pages

# 4. Git 歷史與分支狀態
Git Commit                      -> 9ba8073 (48 files changed, 4066 insertions, 107 deletions)
Remote Status                   -> Synced to origin/main, Working tree clean
```
