# 領域知識庫：狀態持久化、SWR 快取與自癒 (state_cache)

> **所屬領域**: SWR v2, Zustand v5, 自癒狀態機, 深層連結 (Deep Link), 路由跳轉

## 🏛️ 架構決策 (Decisions)
- **模組單例可測性與狀態隔離重置法則 (Module Throttle Singleton Reset Invariance)**: 凡在組件外部宣告之模組層級單例狀態（如 globalLastRefreshTimestamp），必須顯式導出 __reset...ForTesting() 介面，並於單元測試 beforeEach/afterEach 中強制調用，徹底杜絕跨測試狀態洩漏與 Flaky Tests。

- **雙重核驗型別化自癒架構 (Double-Checked Silent Self-Healing)**: 404 自癒嚴禁憑單次 HTTP 404 就清除快取。必須透過行程總清單二次核驗證實死透後，才在 300ms 內靜默導正至最新行程。
- **SWR 404 立即熔斷機制 (Zero-Retry 404 Guard)**: 在 onErrorRetry 中強制判定 error.status === 404 立即終止重試，消除冷啟動請求風暴。
- **型別化 HTTP 錯誤傳遞**: Fetcher 遇到 !r.ok 必須主動拋出標準 HttpError(status, detail)，防止 404 誤入合法快取。
- **本地快取雙清原則 (Dual-Storage Coherence)**: Zustand persist 與 legacy storage 自癒清理時，以 store action 為單一真實來源並同步清理 legacy 鍵。
- **暫時性目標參數脫敏 (Ephemeral Target Parameter Cleanup)**: 定位完成後立即以 window.history.replaceState 拔除 expense_id，達成單次消費即銷毀。
- **深層天數意圖優先原則**: 外部明確意圖 (Deep Link URL / Intent Store) > 內部預設落地值 (Day 1)，推播可直達 Day 0 封面卡片。
- **虛擬化清單篩選器穿透機制**: 長清單尋址時自動歸零前置篩選器，調用 virtuosoRef.current.scrollToIndex 尋址。
- **全域通知連動重新整理與標頭瘦身**: 徹底移除所有 ZenRenew 按鈕。通知鈴鐺展開時 2000ms 節流廣播 tabidachi-trigger-refresh；模組單例戳記必須匯出 __resetGlobalRefreshTimestampForTesting。
- **全域景點口袋庫 (Global POI Pocket & D1 Topology)**: 抽屜、全螢幕清單與口袋地圖結合 Cloudflare D1 微服務與 Next.js 代理，支援 SSRF 防護與跨應用互通。
- **記憶體動態類別收割與零註冊表解耦法則 (Dynamic In-Memory Category Harvesting)**: 自訂分類嚴禁在後端建立 category 表與 CRUD 端點。類別自包含於 POI 的 custom:<emoji>:<name>:<colorHex> 字串中；UI 篩選器透過純函數 extractCategoriesFromPois 在記憶體中動態收割並依據 name 複合主鍵收斂，實現零伺服器負擔、離線天生相容與無 POI 時自動消退。

## 🛡️ 踩坑記錄 (Failed Paths)
- **FP-004 (SWR 快取鍵錯位)**: 使用 new Date().toISOString() 在 UTC+8 深夜產生前一天日期。所有日期快取鍵一律採用 new Date().toLocaleDateString('en-CA')。
- **FP-005 (非同步狀態機解耦)**: Open-Meteo 等長耗時請求嚴禁寫入組件局部 state，必須由獨立模組寫入 Zustand store 並以 in-flight Promise 池去重。
- **FP-006 (骨架屏死鎖)**: 依賴遠端資料的骨架屏必須內建 4 秒硬逾時定時器，連線中斷自動退回暫無資料並支援手動重試。
- **FP-048 (React Compiler Purity)**: 在組件本體呼叫 Date.now() 觸發 react-hooks/purity 報警。時間相依的副作用抽成模組層級純函式。
