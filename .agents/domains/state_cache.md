# 領域知識庫：狀態持久化、SWR 快取與自癒 (state_cache)

> **所屬領域**: SWR v2, Zustand v5, 自癒狀態機, 深層連結 (Deep Link), 路由跳轉

## 🏛️ 架構決策 (Decisions)
- **零外洩後落盤即時廣播、本地私密保留合併、防抖計數守恆與 Day 0/1 清單同步契約 (AD-250)**: 協同端點 broadcastTripEvent 必須在 await tripsApi.updateDayData(...) 後端落盤成功後才發送，且 payload 必經 stripPrivateForBroadcast() 淨化，嚴禁將 is_private: true 條目或原始 private_owner_id UUID 送上 Supabase Realtime WebSocket。接收端 (useTripRealtime.ts, EditableDailyChecklist.tsx, EditableDailyTips.tsx) 必以 mergeIncomingWithLocalPrivate(..., allowOwnerlessIncoming=false) 將外部公開廣播與本端私密項合併，防止同伴更新洗掉本機私密項；itinerary-view.tsx 須以 useMemo 穩定每日陣列參照並對 500 錯誤去重單一 Toast；Day 1 清單樂觀寫入須同步歸零 day_checklists[0] = [] 對齊後端 Day 0 合併清理；500ms 勾選防抖必以 hasPendingDebounceRef 每視窗僅累加一次 pendingUpdatesCount、失敗回滾至 committedItemsRef，且所有立即變更 (add/remove/privacy/saveEdit) 前須先執行 cancelPendingDebounce() 杜絕過期計時器復活已刪項目。

- **雙語儲存雙獨立容錯、執行期白名單與安全模板插值契約 (AD-236)**: LanguageContext.tsx 必須將 localStorage.setItem 與 document.cookie 分離為兩個獨立 try/catch 區塊（QuotaExceededError 不可阻斷 Cookie 同步），並於掛載讀取與 LandingPage 掛載 useEffect 全面包裹 try/catch；setLang 必須執行 isValidLanguage() 校驗同時保持 useCallback([], []) 穩定性。共用 translateTemplate() 必須以 Object.prototype.hasOwnProperty.call(dict, key) 阻擋原型鍵查詢，並以 split/join 替代動態 RegExp.replace 消除 $& 展開缺陷且支援 SSR fallback params。

- **認證失敗指紋鎖與永久彈窗靜默取代短時間冷卻法 (AD-228)**: 當 SWR refreshInterval (15s) 大於冷卻時間時，10s/5s 時間冷卻會演變為無限 401 風暴。ensureValidSession 必須改採 JSON 防碰撞憑證指紋鎖 (lastFailedExchangeFingerprint)：相同憑證指紋於本頁內永久阻斷重試，憑證一更新立即解鎖；dismissReauthPrompt 以 isReauthDismissedInMemory 在當前頁面維持離線靜默（僅保留 lastRestoredAt < 5000ms 吸收恢復前在途請求）；useExpenses/useTripCapsules/usePoiPool 一律停試 401/403/404。

- **TripDialogs Daily Locations Clearing on Existing Trip Merge**: In TripDialogs.tsx, when merging AI/Markdown parsed results into an existing trip (saveTarget === 'existing'), tripsApi.importToTrip must pass daily_locations: {} to prevent stale destination anchors from a prior parse from poisoning the target existing trip's spatial anchor.

- **isUserLoggedIn() Operator Precedence & In-Place Reauth Boundary**: In frontend/lib/auth-session.ts, isUserLoggedIn() MUST maintain backward compatibility for orphan recovery keys (where user_recovery_key exists without nickname) so that 401 triggers in-place re-auth modal (auth-session-resilience TC-10/TC-11). Do NOT conflate visitor mount suppression with isUserLoggedIn definition.

- **Unauthenticated Visitor Session Lifecycle & Recovery Toast Isolation**: In frontend/components/app-client-layer.tsx and frontend/lib/auth-session.ts, unauthenticated visitors accessing '/' MUST NOT trigger toast notifications for '✨ 帳號引繼碼已自其他裝置同步更新' or automatically call ensureValidSession() on mount/reconnect. All tabiji:recovery_key_updated custom events MUST carry a detail.source tag ('initial_bootstrap', 'session_exchange', 'remote_sync', 'local_reanchor'). AppClientLayer MUST filter strictly with 'if (!isUserLoggedIn()) return;' and 'if (customEvent.detail?.source !== "remote_sync") return;'.

- **Temporal Lifecycle Non-Inhibition Invariant**: Temporal service lifecycle status (BEFORE_TRIP, IN_TRIP, AFTER_TRIP) must never inhibit mutation tool calling. The prompt must explicitly state that users have full simulation and planning permissions regardless of dates.

- **Unauthenticated Visitor Reauth Suppression & Identity Self-Healing**: triggerReauthPrompt and SessionReauthModal must strictly verify isUserLoggedIn() (checking user_nickname && user_uuid || user_recovery_key) before broadcasting or opening. In ensureValidSession, 401 for unauthenticated visitors purges orphan UUIDs and resets lastFailedExchangeFingerprint = null, unlocking login. LandingPage handleLogin must implement dual-track bootstrap (online: ensureValidSession server registration, offline: generateUUID fallback).

- **Non-Blocking Preferences Graceful Degradation & Debounced Revalidation Loop**: usersApi.getPreferences must catch 401/403/404 and network errors, gracefully returning empty array [] without throwing unhandled exceptions to console. ProfileView must listen to 'tabiji:recovery_key_updated' with a 300ms debounce to auto-revalidate preferences and profile data upon in-place re-anchoring.

- **401 Self-Healing Token Retention & In-Place Modal Prompt**: In api.ts and hooks.ts, existing session tokens must be preserved across 401 as proof-of-possession for ensureValidSession exchange; upon exchange failure, token is purged and triggerReauthPrompt is fired to wake SessionReauthModal in-place without manual logout.

- **Stale Token CAS Purge & Credential Fingerprint Lock (Superseded 10s Cooldown in be7a32c/bdf1d8a)**: When background vault synchronization (/api/auth/credential) returns 401 Unauthorized, client must apply Compare-And-Swap cleanup (only remove TOKEN_KEY if localStorage still holds the same rejected token). In ensureValidSession, replace fixed 10000ms timers (which clash with 15s SWR polling) with JSON fingerprint locking (lastFailedExchangeFingerprint): identical credentials stay locked until changed, while transient network/5xx errors remain retryable.

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
- **SWR v2 dequal 參照穩定性導致失敗不回滾與 useEffect([..., isEditing]) 覆蓋離線編輯陷阱 (FP-120)**: 前端突變失敗 (401/409/500) 時伺服器資料未變，SWR v2 dequal 會保留同一份 activeTripData 物件參照，導致 useEffect([activeTripData]) 永不重跑，單靠 reloadTripDetail() 無法回滾樂觀狀態；寫入處理器必須快照前態並顯式回滾，同時將 200 成功後之 reloadTripDetail()/tripMutate() 加上 .catch(() => {}) 避免重抓抖動觸發假回滾。反之若將 isEditing/innerEditing 放入 useEffect 而未以 lastSyncedTripRef 追蹤 (tripId, activeTripData)，離線排隊存檔後退出編輯態時會被舊快取反寫覆蓋樂觀編輯。

- **僅護 Context 漏護 LandingPage 掛載期 Web Storage 導致受限環境整頁崩潰陷阱 (FP-105)**: 僅在 LanguageContext 補齊 localStorage try/catch 並只用 renderHook(() => useLanguage()) 測試會誤以為具備 Safari 隱私瀏覽／受限 iframe 防護；實測掛載 <LandingPage />（特別是 URL 含 ?trip= 時）會在掛載 useEffect 裸呼叫 sessionStorage.setItem / localStorage.getItem 處拋出未捕獲 DOMException('SecurityError') 導致整頁崩潰。Web Storage 防護必須於入口元件對稱落地並以整頁元件渲染驗證。

- **SSE 註解心跳行誤殺整段資料區塊與 Stream Mock 契約破壞陷阱 (FP-104)**: frontend/lib/api.ts 解析 SSE \n\n 區塊時，嚴禁只判斷 trimmed.startsWith(':') 就 continue 整段區塊（會把同區塊內的 event:/data: 一併吞掉），必須先以 line => !line.startsWith(':') 逐行剔除註解行。後端將核心端點重構為 call_extraction_stream 時，必須加入 _is_mocked 相容檢查，否則既有用例 mock 舊 call_extraction 將被靜默繞過。

- **Supabase RLS 靜默回空與 REST Broadcast 重複加 realtime: 前綴失聯陷阱 (FP-101, FP-102)**: 未跑 Supabase Auth 僅用 Publishable Key 時，RLS 綁定 auth.uid() 會使查詢靜默回傳 [] 且 postgres_changes 靜默丟棄事件；實作即時同步應全數改為不透明 Broadcast 訊號搭配認證後端 API 拉取。透過 Supabase Realtime REST API 發送廣播時，topic 嚴禁手動加上 'realtime:' 前綴（客戶端 SDK 已自動附加），否則雙邊主題永遠無法匹配。

- **fetchLatestRecoveryKey 遲到 401 盲刪剛刷新 Session JWT 之競態陷阱 (FP-097)**: 並發請求中若其他路徑已透過 ensureValidSession(true) 換發並寫入新 tabiji_session_token，較慢返回之背景 /api/auth/credential 401 回應在清除或搬移 TOKEN_KEY 前必須嚴格執行 Compare-And-Swap Check (if (localStorage.getItem(TOKEN_KEY) === token))，禁止無條件刪除已更新之最新憑證。

- **模組載入期自生未註冊 UUID 與提前寫入 user_nickname 引發 401 鎖死陷阱 (FP-095)**: tripStore.ts 嚴禁在模組 import 期生成本地 UUID 寫入 localStorage 並隨即呼叫 ensureValidSession()；LandingPage handleLogin 嚴禁在後端註冊完成前先行寫入 user_nickname 並必須過濾 'null'/'undefined' 字串。否則未入庫的孤兒 UUID 會使 isUserLoggedIn() 回傳 true，開機即吃 /api/auth/session 401 陷入無解的引繼碼重驗證死結。

- **過期 JWT 預先清除導致 90 天寬限期 PoP 驗證失效**: getCachedToken() 若在 ensureValidSession()、rotateAccountRecoveryKey() 或 fetchLatestRecoveryKey() 讀取前直接移除過期 tabiji_session_token，會導致後端 auth.py 90 天寬限期 PoP 驗證失敗。必須在清除前將語法有效的過期 JWT 備份至 tabiji_pop_token（僅於登出、重設或 visitor 401 時清除），且 profile-view handleClearCache() 必須完整保留 user_uuid、user_recovery_key、tabiji_session_token、tabiji_pop_token、user_nickname 與 user_avatar 六項鍵值。

- **子路由 layout 宣告 head 導致 React 19 與 Next.js 16 渲染層水合錯誤**: 在 Next.js App Router 架構下，只有根路由 app/layout.tsx 允許渲染 html, body, head。子路由（如 app/official/layout.tsx）若重複宣告 head，會觸發 In HTML, head cannot be a child of body 水合失敗。資源預載應透過 Image priority 或 route metadata 宣告。

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
