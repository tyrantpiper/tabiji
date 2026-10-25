# 領域知識庫：狀態持久化、SWR 快取與自癒 (state_cache)

> **所屬領域**: SWR v2, Zustand v5, 自癒狀態機, 深層連結 (Deep Link), 路由跳轉

## 🏛️ 架構決策 (Decisions)
- **Temporal Lifecycle Non-Inhibition Invariant**: Temporal service lifecycle status (BEFORE_TRIP, IN_TRIP, AFTER_TRIP) must never inhibit mutation tool calling. The prompt must explicitly state that users have full simulation and planning permissions regardless of dates.

- **Unauthenticated Visitor Reauth Suppression & Identity Self-Healing**: triggerReauthPrompt and SessionReauthModal must strictly verify isUserLoggedIn() (checking user_nickname && user_uuid || user_recovery_key) before broadcasting or opening. In ensureValidSession, 401 for unauthenticated visitors purges orphan UUIDs and resets lastExchangeFailedAt = 0, unlocking login. LandingPage handleLogin must implement dual-track bootstrap (online: ensureValidSession server registration, offline: generateUUID fallback).

- **Non-Blocking Preferences Graceful Degradation & Debounced Revalidation Loop**: usersApi.getPreferences must catch 401/403/404 and network errors, gracefully returning empty array [] without throwing unhandled exceptions to console. ProfileView must listen to 'tabiji:recovery_key_updated' with a 300ms debounce to auto-revalidate preferences and profile data upon in-place re-anchoring.

- **401 Self-Healing Token Retention & In-Place Modal Prompt**: In api.ts and hooks.ts, existing session tokens must be preserved across 401 as proof-of-possession for ensureValidSession exchange; upon exchange failure, token is purged and triggerReauthPrompt is fired to wake SessionReauthModal in-place without manual logout.

- **Stale Token Purge on Background Credential 401 & 10s Exchange Cooldown**: When background vault synchronization (/api/auth/credential) returns 401 Unauthorized, client must immediately purge stale TOKEN_KEY from localStorage. In ensureValidSession, a 10000ms cooldown (lastExchangeFailedAt) must be enforced upon 401 to prevent SWR storm hammering.

- **Post-Restoration Grace Window Against Modal Thrashing**: Client-side triggerReauthPrompt must enforce a 5000ms grace cooldown based on lastRestoredAt timestamp to absorb in-flight stale 401 responses fired before re-anchoring, preventing modal reopening thrashing.

- **Root Layer Realtime Subscription & Event Bus Invariant**: Account-level Realtime broadcast channels must be subscribed exclusively at the top-level client layer and communicate to deep views via DOM CustomEvents to avoid blindspots and redundant connections.

- **Opaque Invalidation Signal for Realtime WebSocket Channels**: Realtime broadcast events (e.g. CREDENTIAL_ROTATED) must never contain plaintext secrets or user tokens in their payload. Broadcasts must function strictly as opaque invalidation signals (timestamp only), forcing clients to fetch fresh state over authenticated HTTPS.

- **Realtime Channel Coordinator Detach Queue Pruning**: When unmounting a realtime channel via RealtimeChannelCoordinator.detach(tripId), queueMap for that tripId must be pruned atomically to prevent stale event replay upon rejoining the trip.

- **Predicate Invalidation for SWR Tuple Keys**: When SWR keys are declared as Tuples (e.g. ['/api/trips/...', userId]), mutations must use Predicate matching functions (key => Array.isArray(key) && key[0].startsWith(...)) and explicitly pass undefined, { revalidate: true }.

- **Service Worker Dynamic Trip API NetworkOnly Invariant**: Dynamic trip APIs (/api/trips/) must be routed as NetworkOnly in the Service Worker. Never apply StaleWhileRevalidate in the SW when SWR and IndexedDB (L0/L1) manage client-side state, preventing double-cache overwrite.

- **Strict Local-First Recovery Key Anti-Overwrite Invariant**: In client auth-session handling, if a local recovery key exists in localStorage, it must never be overwritten if a session response returns a mismatched user_id. Such occurrences must trigger an alert and throw an error to preserve account ownership.

- **雙軌協同與全量快照調和防衛法則**: 系統必須維持即時同步（增量廣播，主打多人 0ms 極速體驗）與手動/手勢重整（全量快照，主打手機休眠喚醒、丟包與競態調和）雙軌架構。手動重整應無感封裝於通知鈴鐺或下拉手勢中，兼顧介面極簡留白與 100% 狀態自癒防呆。

- **UX 機能融合與雙軌自癒備援法則 (INV-UI-024 / INV-STATE-037 / Dual-Purpose UI)**: 系統必須維持即時同步（增量廣播，主打多人 0ms 極速體驗）與手動/手勢重整（全量快照，主打手機休眠喚醒、丟包與競態調和）雙軌架構。手動重整應無感封裝於通知鈴鐺或下拉手勢中，兼顧介面極簡留白與 100% 狀態自癒防呆。

- **即時記憶體廣播鏡像與 0ms 樂觀解耦法則 (AD-149)**: 協同廣播通道必須利用 clientSessionId 物理過濾本端回環；同伴拖曳排序廣播以 orderedItemIds 在記憶體中 0ms 鏡像重排卡片以消弭 SWR 提前拉取導致的資料庫競態回彈；所有本機表單操作必須先更新 State 並立即關閉表單，背景發送請求且遇錯自動回滾；廣播接收端必須強制注入 Array.isArray(data) 邊界斷言。

- **前端 401 自動換票重試遞迴熔斷法則 (AD-148)**: 全域 Fetch 攔截器與串流發起端在收到 401 觸發靜默換票與重試時，必須強制標記 _isRetry: true 並跳過認證端點本身與已消費 Request Body (input.bodyUsed)；嚴禁無限制重試，徹底杜絕 Token 刷新死循環與 Stream 耗盡崩潰。

- **前端無感 Session 自動換發與生命週期自癒法則 (AD-146)**: 前端應用必須於 AppClientLayer 掛載期預檢並靜默換發 Session JWT，並註冊 online 與 visibilitychange 生命週期監聽器於前景喚醒時提前自動刷新憑證；全域 API 代理層必須具備 401 攔截與單次透明換票重試機制，徹底消除用戶因 Token 過期產生的操作中斷。

- **前端動態代理與單例換票防抖法則 (AD-145)**: 前端包裝全域 fetch 時，嚴禁在模組載入期以 bind(window) 鎖定靜態參照，必須於執行期動態獲取 globalThis.fetch 以確保 Vitest/Node 測試相容性；同時，會話換票必須實施單例 Promise 防抖與離線 short-circuit，防止開機併發風暴。

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
- **Orphan Client UUID Inducing Reauth Modal Trap on Root Landing Page**: Symptom: First-time visitor opening root '/' was immediately confronted with an alarming '需要原地驗證最新引繼碼' modal with a 10s cooldown lock. Cause: Client-side generated UUID was persisted in localStorage without server registration, causing ensureValidSession to receive 401 and trigger triggerReauthPrompt. Lesson: Unauthenticated visitors must be strictly gated with isUserLoggedIn() and orphan UUIDs silently purged.

- **Deep-View Scoped Realtime Blindspot Trap**: Scoping realtime credential sync listeners inside specific subviews causes devices on other pages to miss critical rotation signals.

- **Realtime Broadcast Plaintext & State Poisoning Trap**: Broadcasting plaintext secrets over WebSocket channels leaks credentials and allows state poisoning. Always use opaque signals and authenticated pull.

- **React Async State Closure Stale Overwrite**: Calling save immediately after setState reads previous frame state. Pass override data directly into save handler.

- **SWR Tuple Key String Mutation Silent Failure**: Mutating a string key does not match SWR tuple keys. Use predicate matcher over cache keys.

- **Double Cache Clashing between Service Worker and SWR**: SW StaleWhileRevalidate overrides optimistic SWR updates with 7-day stale disk cache. Keep SW NetworkOnly for dynamic entities.

- **SWR 提早 Revalidate 引發資料庫非同步寫入競態與卡片回彈陷阱**: 當同伴重排卡片時，監聽端收到廣播後若立即呼叫 SWR mutate() 重新發起 GET 請求，後端 DB 若仍在執行批次 update，GET 拉取到的仍是舊的 sort_order，導致卡片剛排好又瞬間「彈回舊位置」。修復準則：即時重排必須走「記憶體鏡像先行」：廣播封包中夾帶最終的 orderedItemIds，監聽端直接在記憶體中執行本地陣列重排，待平靜期後再行背景靜默校驗。

- **協同廣播非陣列資料引發 React TypeError 白屏崩潰陷阱**: 當即時廣播頻道接收到格式異常或空物件之 tip:update 事件時，detail.data.map(...) 拋出 TypeError: detail.data.map is not a function，摧毀整棵 React 元件樹引發白屏。修復準則：任何自外部長連線（WebSocket/WebRTC/CustomEvent）接收的動態資料，在餵入 React 狀態或呼叫陣列方法前，一律強制實施 Array.isArray(data) 邊界斷言。

- **前端 401 自動重試引發 Request Body 耗盡與無限遞迴陷阱**: 在全域 Fetch 攔截器中若未檢測 input.bodyUsed，重放已消費之 Request 會拋出 TypeError: Cannot construct a Request with a Request object that has already been used；若 401 來自驗證端點本身，未設 _isRetry 標記會造成換票死循環。修復準則：401 重試必須具備雙重前置防禦：(1) _isRetry: true 單次限制標記；(2) input instanceof Request && input.bodyUsed 檢查，排除認證端點本身。

- **Vitest 模組載入期 Fetch 綁定穿透 Mock 陷阱**: 在 api.ts 頂層以 const _rawFetch = typeof window !== 'undefined' ? window.fetch.bind(window) : globalThis.fetch; 儲存引用，導致 Vitest 測試套件的 global.fetch = mockFetch 完全失效，Node 拋出 ERR_INVALID_URL。修復準則：代理函式必須在執行調用當下動態獲取 activeFetch，嚴禁在模組 import 期凍結全域參照。

- **FP-004 (SWR 快取鍵錯位)**: 使用 new Date().toISOString() 在 UTC+8 深夜產生前一天日期。所有日期快取鍵一律採用 new Date().toLocaleDateString('en-CA')。
- **FP-005 (非同步狀態機解耦)**: Open-Meteo 等長耗時請求嚴禁寫入組件局部 state，必須由獨立模組寫入 Zustand store 並以 in-flight Promise 池去重。
- **FP-006 (骨架屏死鎖)**: 依賴遠端資料的骨架屏必須內建 4 秒硬逾時定時器，連線中斷自動退回暫無資料並支援手動重試。
- **FP-048 (React Compiler Purity)**: 在組件本體呼叫 Date.now() 觸發 react-hooks/purity 報警。時間相依的副作用抽成模組層級純函式。
