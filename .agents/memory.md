## [Decisions]

### 1. 圖形、地圖與 WebGL 架構 (Graphics, MapLibre & WebGL)
- **MapLibre 宣告式圖層拓撲優先原則 (Declarative Layer Precedence)**: 在 React 宣告式渲染中，JSX 必須依物理由底至頂排列（底圖衛星/向量 ➔ 中間彩帶軌跡 ➔ 頂層自訂 Marker Pin）。禁止在前面圖層宣告 `beforeId` 指向尚未宣告的後續同級圖層，避免引發 `Cannot add layer before non-existing layer` 致命白屏；`beforeId` 僅能參照底圖 Base Style 內已預載的圖層。
- **CSP Web Worker 同源靜態管線標準化 (MapLibre CSP Worker Pipeline)**: 堅決不放寬 CSP 安全標頭（不用 `unsafe-eval` 或動態 blob）。透過 `frontend/scripts/copy-maplibre-worker.mjs` 與 npm `prebuild` hook，自動將 `maplibre-gl-csp-worker.js` 同步至 `public/` 目錄，組件宣告 `maplibregl.workerUrl = '/maplibre-gl-csp-worker.js'` 同源派發。
- **WebGL Canvas 與浮動手勢雙向硬體隔離 (Hardware Composite Decoupling)**: 拖曳節點若直接以 CSS `right/bottom` 修改座標，會觸發 Blink/WebKit 主執行緒 Layout Reflow，迫使 GPU 重新繪製整張大尺寸 WebGL Canvas 導致掉幀至 20fps。規範：地圖容器使用 `transform-gpu will-change-transform` 固定為獨立合成層，拖曳節點宣告 `transform-gpu` 並動態切換 `willChange: isDragging ? "right, bottom" : "auto"`，達成 60fps 絲滑拖曳。
- **景點抽屜容器內錨定原則 (Container-Anchored Sheet Decoupling)**: 在全景或總覽地圖中，景點抽屜必須支援 `isInternal={true}` 模式，將容器限制在地圖內部（`absolute bottom-0`）而非視窗層級（`fixed inset-0`），防止抽屜破壞全域導航列與 Header。
- **大圓航線球面線性插值 (Great-Circle Slerp Interpolation)**: 跨天或長途城際移動軌跡禁止在平面上直連線條。透過 `geo-multi-day.ts` 純函數庫進行球面幾何插值，依天數動態映射高對比飽和色彩池（Day 1~5: Emerald, Blue, Violet, Pink, Amber）。
- **雙套件依賴強耦合原子升級鎖 (Coupled Dependency Atomic Lock)**: `react-map-gl` 與 `maplibre-gl` 存在深層私有 API（內部 transform 實例）綁定，嚴禁獨立升級單一套件。未來升級必須視為「原子包 (Atomic Pair)」同步評估與實機雙重核驗。
- **務實穩定勝於盲目追新原則 (Pragmatic Stabilization over Chasing SemVer Major)**: 在核心商業邏輯未受阻且維持 0 安全漏洞前提下，不為了追求版本號承擔生態斷層與 WebGL1 淘汰的代價。
- **本地真機活體驗收守門 (Local Native Probing Gate)**: Node.js / JSDOM 單元測試無法模擬真實 WebGL Context。凡涉及圖形渲染、地圖底圖與事件循環的核心變更，必須在本地真機瀏覽器確認無誤後方可提交。
- **Liquid Glass 物理材質純 CSS + GPU 合成層準則 (CSS Inset Specular over Heavy WebGL Shader)**: 堅決反對社群中盲目引入全屏 WebGL/WebGPU Shader（如 liquidGL）為按鈕製作液態玻璃效果的「反模式」。在已有 MapLibre 畫布的情況下，雙 WebGL Context 會引發 iOS Safari Context Loss 崩潰。規範一律使用純 CSS `backdrop-blur`、`saturate`、`shadow-[inset_...]` 搭配 `transform-gpu will-change-transform`，0ms JS 執行緒開銷，穩健交付 60~120fps。
- **MapLibre 相機排程原子化原則 (Atomic Camera Transition Invariance)**: 連續呼叫 `easeTo` 與 `fitBounds` 會引發相機動畫排程競爭，後者會直接掐斷前者。若需在縮放視角的同時歸零角度，必須在 `fitBounds` 的 options 中顯式注入 `bearing: 0, pitch: 0`，使相機邊界縮放與方位重置在同一底層矩陣運算中原子化完成。
- **多日總覽地圖 2D 平面 Mercator 預設守則 (Overview Map 2D Planar Default Invariance)**: 行程總覽（MultiDayMasterMap）涵蓋多天城際甚至跨國大尺度邊界，其預設投影必須維持 2D Mercator 平面（`isGlobe = false`）。在大尺度下若預設開啟 3D Globe，拖曳手勢會從線性平移退化為球面弧線旋轉（Spherical Rotation），導致視角傾斜、旋轉拉扯與手感降級。3D 地球儀必須作為選擇性增強功能，僅在使用者點擊 🌐 按鈕時按需動態開啟。
- **MapLibre Globe 投影球面射線穿透奇異點與反向滑動陷阱 (Globe Projection Raycast Antipodal Singularity & Opposite Slip)**: 實證 MapLibre GL JS 官方已知底層缺陷（Issue #8349: *Map occasionally slips to opposite direction when dragging*）。在 3D Globe 投影下，觸控拖曳靠近地平線外圍（Horizon Limb）或中低縮放層級時，引擎射線反投影（Raycasting Unproject）會穿透至球體背面或切線法向量點積轉負（$\vec{N} \cdot \vec{V} < 0$），導致角速度位移被乘以 $-1$，產生「地圖朝手指反方向滑動」之反常現象；該反向速度會被 dragPan 慣性動量緩衝區記錄，手放開後持續反向滑行，直至使用者放大（Zoom In）攤平曲率、或四元數旋轉矩陣重新約束歸一化後才平息。架構方針：單日行程地圖（DayMap）亦應對齊遵循 2D Mercator 平面優先原則，避免預設強制 Globe 導致觸控跟手性破壞。
- **MapLibre 3D 地形拖曳高程凍結與放手微幅吸附現象 (3D Terrain Elevation Freeze & Gesture Re-clamping Snap)**: 實證 MapLibre GL JS 官方核心 PR #8471 與 Issue #8539（*Camera Jumps / Bobbing over Terrain*）。在 3D DEM 地形啟用時，引擎為確保拖曳時維持 60 FPS，手勢移動中會將相機高程「暫時凍結（Elevation Freeze）」；而在手指放開（moveend / pan release）瞬間解除凍結，強制精算新中心點的地表高度並執行 centerClampedToGround（貼地高度吸附）。在大比例尺（高縮放）的山地或陡峭斜坡，相機中心高程差（$\Delta Z$）可能在數十米內劇烈變動，經透視矩陣投影為螢幕 XY 平面的微幅跳動（Bobbing / Snap）；加上 dragPan 慣性殘留，造成放手後地圖稍微抽動一下的視覺感。業界解法方針：在 3D 模式下可選擇性配置 dragPan.enable({ inertia: false }) 或平滑化 setCenterClampedToGround(false) 消除放手突變。
- **地圖控制膠囊單一真理與呼吸降敏架構 (MapControlCapsule Single Source of Truth & Idle Dimming)**: `day-map.tsx` 與 `MultiDayMasterMap.tsx` 消除重複控制鈕與樣式代碼，抽取共用元件 `MapControlCapsule.tsx`。繼承 Tabidachi 核心設計 DNA——對齊 Ryan AI 聊天懸浮球的 `isIdle` 呼吸降敏機制：靜止 3 秒無操作自動以平滑動畫降低至 25% 晶透幽靈態（`opacity-25 scale-95`），避開東北方景點視野遮蔽；地圖拖曳、游標懸停或手指觸控瞬間點亮至 100% 飽和高亮態，完美兼顧視覺沉浸度與操作可發現性。
- **離散手勢排程優於每幀高頻監聽原則 (Discrete Lifecycle over 60fps Frame Thrashing)**: 偵測地圖運動時嚴禁直接在 MapLibre `onMove`（每秒 60~120 次）中綁定 React 狀態，防止高頻 Re-render 與 WebGL 掉幀。架構上一律使用離散生命週期事件——`onMoveStart` 進入平移態、`onMoveEnd` 結束平移態。拖曳過程中 React 觸發次數降為 0，實現完全無負擔的流暢滑動。

### 2. 狀態持久化、SWR 快取與自癒機制 (State, SWR, Routing & Self-Healing)
- **雙重核驗型別化自癒架構 (Double-Checked Silent Self-Healing)**: 分散式快取自癒嚴禁僅憑單次 HTTP 404 就草率清除快取（避免網路抖動導致正常行程被誤判跳轉）。必須透過「行程總清單存活二次核驗（List Double-Check）」證實死透後，才在 300ms 內完全靜默導正至最新有效行程。
- **SWR 404 立即熔斷機制 (Zero-Retry 404 Guard)**: HTTP 404 屬於明確的客戶端資源不存在，在 SWR `onErrorRetry` 中強制判定 `error.status === 404` 立即終止重試，將無效請求次數由 19 次嚴格降為 0，消除伺服器冷啟動風暴。
- **型別化 HTTP 錯誤傳遞 (Typed HttpError Propagation)**: 原生 fetch 遇 4xx/5xx 不會 reject Promise，底層 Fetcher 必須主動檢查 `!r.ok` 並拋出標準 `HttpError(status, detail)`，防止上層快取引擎將 404 誤當作合法資料寫入快取而使自癒啞火。
- **本地快取雙清原則 (Dual-Storage Coherence)**: 同時使用 Zustand `persist`（`trip-storage`）與舊版 Storage（`active_trip_id`）時，自癒清理必須以 Zustand store action 為單一真實來源並同步清理 legacy 鍵，杜絕重新整理後狀態還原。
- **暫時性目標參數脫敏與防震盪機制 (Ephemeral Target Parameter Cleanup)**: 在完成定位調度後，立即調用 `window.history.replaceState` 將 `expense_id` 從網址列拔除，達成「單次消費即銷毀」的冪等性保護，防止使用者 F5 重新整理時反覆重播定位動畫。
- **深層天數意圖優先於預設天數之階層判定 (Day-Zero Overview Precedence)**: 確立「外部明確意圖（Deep Link URL / Intent Store） > 內部預設落地值（Day 1）」的優先順序模型，成功解鎖推播直達 `day=0` 行程封面總覽卡片。
- **虛擬化清單篩選器穿透機制 (Filter Penetration on Deep Link)**: 虛擬化長清單（React Virtuoso）尋址時，消費端必須具備「前置篩選器自動歸零」的穿透權威，隨後調用虛擬列表內部控制代碼 `virtuosoRef.current.scrollToIndex` 達成 100% 精準尋址，嚴禁調用 DOM 原生選擇器。
- **表現層截斷與資料層無損分離 (Presentation Layer Truncation Separation)**: 資料傳輸與儲存層保持 100% 原始語義完整性，字數截斷完全由前端 CSS (`line-clamp-2`, `truncate`) 控制。
- **天數物理可見性雙向防衛 (Physical Visibility Defense)**: 前端天數分頁以 `Math.max(日期天數, 資料庫景點天數)` 渲染，後端 `save_itinerary` 與 `ai.py` 強制以 `max_day` 動態展延 `end_date`，防止日期字串截斷 UI 顯示。
- **長耗時外部網路請求全域狀態機解耦與 In-Flight 去重 (Decoupled Global Write & Deduplication)**: 在頻繁重繪架構下，非同步長耗時請求（如 Open-Meteo API）嚴禁寫入組件局部 state 或依賴 `isMounted` 閉包；必須由獨立模組寫入全域狀態機（Zustand store），並維護 In-Flight Promise 池避免相同座標重複請求。組件僅在渲染階段以響應式 selector 讀取，杜絕組件因父層 SWR 抖動卸載後誤殺回傳資料。
- **本地時區安全日期鍵規範 (Local Timezone Date Safety)**: 使用 `new Date().toISOString().split("T")[0]` 在 UTC+8 深夜 00:00~08:00 會回傳前一天的 UTC 日期造成快取鍵與本地行程錯位。前端所有快取鍵與日期排程統一採用 `new Date().toLocaleDateString('en-CA')` 對齊客戶端本地時區。
- **骨架屏硬逾時優雅降級 (Hard-Timeout Skeleton Fallback)**: 依賴非同步遠端資料的骨架屏（如 `DailyWeatherStrip`），嚴禁無限期 pulse 閃爍。必須內建 4 秒硬逾時定時器，連線中斷或逾時自動切換至「暫無氣象資料 · 重試」狀態並支援手動重新整理。

### 3. iOS 原生體驗、微動效與 UI 元件架構 (iOS Ergonomics, Motion & Decoupled UI)
- **WebKit 匿名文字節點隔離與 Flex 寬度守護 (Text-Node Isolation Architecture)**: 在 Flex 容器中，裸露文字搭配 `truncate` 會在 WebKit 引擎下產生匿名文字方塊（Anonymous Block Box），在 390px 窄螢幕下壓縮同級 `shrink-0` 標籤。架構上確立動態文本必須封裝於獨立 `<span className="truncate">` 節點中，與同級元素形成明確 DOM 邊界。
- **iOS 原生雙擊鑽取心智模型 (Tap-to-Focus, Tap-again-to-Drilldown)**: 在空間極度受限的行動裝置地圖頂部，杜絕塞入臃腫跳轉按鈕。初次點擊切換天數聚焦軌跡並浮現箭頭（`🟢 Day 1 ➔`），再次點擊已選中項觸發平滑滾動（Smooth Scroll）直達卡片。
- **解耦按鈕 DOM 架構 (Decoupled Button DOM Architecture)**: HTML5 嚴禁 `<button>` 嵌套 `<button>`。卡片容器內部點擊進入與操作列按鈕（PDF、退出、刪除）在 DOM 層級完全解耦為同級 Sibling 節點。
- **無狀態銷毀的視圖動畫架構 (Zero-Remount View Animation Architecture)**: `<motion.div>` 使用靜態標識搭配屬性動畫驅動位移，四大主頁面常駐且永不銷毀，達成 0 重複 API 請求與 100% 滾動位置記憶。
- **iOS Swift 全域雙向滑動轉場與觸控防衛 (Direction-Aware Spring Transitions & Touch Guards)**: `app-shell.tsx` 導入方向感知索引與彈簧滑入 (`x: ±28px`)；全域注入 `select-none` 消除長按選取文字問題，底部導航搭配 `haptic.selection()` 原生震動與 `active:scale-95` 反饋。
- **連續多月份滾動日曆區間選擇器 (Continuous Multi-Month Calendar)**: 採用連續縱向雙向滾動日曆 (`CalendarRangeSheet`) 搭配 Sticky 月份標題與快速跳轉，取代零散前後加減天數按鈕；在 Day 0 建立 `TripMasterOverview` 儀表板。
- **合成點擊與拖曳手勢競態防衛 (Drag-Release Synthetic Click Race-Condition Guard)**: 透過 `hasMovedRef` 追蹤位移並於 `handleDragEnd` 中設置 80ms 延遲釋放閥，徹底杜絕拖曳完放開手指誤開面板的手勢衝突。
- **輸入法組合態攔截與自適應高度防線 (IME Composition Guard & Auto-Growing Textarea)**: 中文（注音/倉頡/拼音）與日文選字時，輸入框全面升級為自適應高度 `<textarea>`（`min-h-9 max-h-32`），並在 `onKeyDown` 嚴格掛載 `if (e.nativeEvent.isComposing) return`，防止提前觸發發送。
- **高密度對話組件原地微創升級原則 (In-Place Surgical Modernization over Premature Component Splitting)**: 對於承載 12+ 項複雜閉包的高密度邏輯組件（如 `chat-widget.tsx`、`ExpenseDialog.tsx`），堅決抵制盲目拆檔，改以原地微創升級保持閉包穩定，取得最高穩定度與安全 ROI。
- **導覽列原生 CSS 暗黑適配優先於 React State (Native CSS Dark Token over Runtime Hydration)**: 核心 UI 控制項（如常駐 Bottom Nav）的指示器背景與邊框，嚴禁在客戶端尚未 Hydration 前依賴 React `isDark` state 進行 inline style 賦值。必須以 Tailwind CSS 原生 `dark:` 類別接管，確保 SSR 渲染至客戶端繪製期間零延遲、無色彩跳動。
- **Touch-Safe 指針偽類隔離防禦 (Pointer-Type Touch-Safe Hover Invariance)**: 行動裝置觸控螢幕會將按鈕點擊判定為 `:hover` 黏滯（Sticky Hover），導致無法自動退回幽靈態。架構上指針事件必須以 `e.pointerType === "mouse"` 隔離，使 Hover 續命邏輯僅對真實滑鼠生效，觸控設備純由 Touch 與 Map Move 離散狀態機接管。
- **跨層彈窗 Radix Portal 物理隔離原則 (Radix Portal Container Escape)**: 在全景地圖或深度巢狀容器中喚醒天數選擇器等跨天彈窗（DaySelectDialog），必須透過 Radix UI Dialog Portal 將 DOM 節點直接掛載至 `document.body`，杜絕地圖容器外層 `overflow-hidden isolate` 引發的彈窗裁切與層級穿透問題。
- **Zero-FOUC 前置同步腳本原則 (Zero-FOUC Pre-Hydration Scripting)**: 全域字體縮放與外觀偏好若完全依賴 React `useEffect` 在客戶端讀取 `localStorage`，使用者在開啟頁面的前數百毫秒必然會看到標準字體瞬間放大或跳動（Flash of Unstyled Content）。架構規範必須在 HTML `<head>` 注入原生微型同步腳本，首幀直接設定 `:root { --font-scale: ... }`，阻斷首次渲染前的樣式漂移，保障原生應用級別的視覺平穩度。
- **動作感應式聚光燈取代被動打勾清單原則 (Action-Gated Walkthrough over Passive Checklist)**: 被動打勾卡片（`TaskCard`）佔用 Profile 空間且點擊率極低，無法引導使用者建立深層心智模型。全面升級為全域懸掛、點擊可穿透、帶領使用者走完真實業務流程（開 AI 設定 ➔ 點 Ryan 助理 ➔ 建行程 ➔ 開範例行程 ➔ 切工具箱）的沈浸式聚光燈導引。
- **速度收斂穩定追蹤優於瞬態採樣原則 (Velocity-Settled Convergence over Premature Snapshot)**: 當路由或視圖切換伴隨 Framer Motion 進場動畫（如 `x: -20% -> 0`）時，若在切換瞬間僅執行一次 `getBoundingClientRect()`，會捕捉到位移途中的座標，導致導引外框偏位（如偏左 42px）。引導定位嚴禁單次採樣，必須啟用 RAF 速度收斂演算法：設定 180ms 最小觀察窗，且必須連續 4 幀在 X 與 Y 軸的位移差均小於 0.5px，才判定目標已完全靜止並鎖定座標；同時設置 600ms 算力熔斷計時器防止無效耗電。
- **破壞性動作隔離與專屬動作白名單原則 (Destructive Action Defense & Tour White-listing)**: 為完整框選卡片容器而提升導引 ID 時，卡片內通常包含刪除按鈕等高危操作。若聚光燈點擊穿透僅執行 `container.querySelector("button")`，將有極高機率誤點擊右上角的刪除按鈕。規範在主要業務按鈕上顯式宣告 `data-tour-action="primary"` 作為最高優先級目標；穿透點擊轉發引擎嚴格過濾排除帶有 `.bg-red-500`、`variant="destructive"` 之元素，杜絕新手誤刪資料。
- **視圖切換雙重 RAF 佈局重排等待原則 (Double-RAF Layout Reflow Invariance)**: 在具有過渡動畫的容器（`AnimatePresence mode="wait"`）中返回上一層視圖時，第 1 幀 DOM 剛被掛載，瀏覽器尚未完成 CSS 計算與佈局重排（Layout/Reflow），此時容器 `scrollHeight` 尚未展開，立即調用 `scrollTo` 會被截斷至 0。必須採用雙重 `requestAnimationFrame`：第 1 幀等待舊視圖卸載與新節點掛載，第 2 幀等待瀏覽器重排完畢後再執行 `scrollTo({ top: targetPos, behavior: 'instant' })`，並搭配 `active` 旗標與清理函式消除競態條件。

### 4. 離線架構與 PWA 快取 (Offline, Service Worker & PWA)
- **Service Worker 構建路徑絕對化標準 (Hermetic Build-Time Path Resolution)**: 工具腳本中的靜態資產掃描嚴禁依賴非確定性的 `process.cwd()`。必須以模組目錄 `import.meta.url` 為錨點解析絕對路徑，確保無論從專案根目錄或子模組呼叫皆具備相同的產出確定性。
- **站在既有巨人肩膀上的輕量化離線原則 (Shoulder-of-Giants Offline Architecture)**: 拒絕盲目引入 PowerSync 或 RxDB 等肥大客戶端複寫引擎，完全立足於專案既有的 `serwist`、`idb-keyval` 與 `SWRConfig provider` 官方標準模式，以最小代碼增量完成離線優先秒開閉環。
- **動脈與靜脈讀寫分流架構 (Arterial/Venous Read-Write Decoupling)**: 在 Service Worker 層將 GET 查詢（SWR 快取）與 POST/PUT/PATCH/DELETE 突變（BackgroundSync 離線重試）物理隔離，杜絕突變請求被快取誤吞或 GET 查詢誤進背景佇列。
- **PWA 帶參冷啟動導航防線 (Ignore-Search Navigation Pipeline)**: 手機 Standalone PWA 啟動或推播跳轉常帶有 `/?source=pwa` 或查詢參數。Service Worker `app-shell-navigation` 必須宣告 `matchOptions: { ignoreSearch: true }`，且導航逾時緊縮至 2s，確保離網冷啟動 100% 命中 App Shell 快取，防止字串嚴格比對失敗拋出瀏覽器小恐龍。
- **行程上下文離線防自我抹殺雙守衛 (Offline Trip Non-Destructive Invariance)**: SWR 在斷網或 API 異常時回傳的空陣列不可作為「使用者無行程」之業務假設；`trip-context.tsx` 強制守衛 `isDefinitelyOnline && !isError`，只有確實在線且無錯誤時才允許清空當前行程，斷網狀態死守本機現存 ID 與 localStorage。
- **SWR ES6 Proxy 防抖硬碟持久化 (L2 IndexedDB Auto-Persistence)**: 透過 `createPersistedCacheMap()` 以 ES6 Proxy 攔截 SWR 成功寫入操作，1500ms 防抖自動序列化持久化至 IndexedDB `tabidachi_swr_persisted_cache`，冷啟動重啟秒出。
- **既有 Client 喚醒與內部事件廣播 (Smart Tab Focus & Push Navigation)**: 推播點擊由暴力 `client.navigate()` 重載升級為 `client.focus()` 喚醒分頁，並透過 `client.postMessage({ type: "TABIDACHI_PUSH_NAVIGATE", url })` 內部廣播，由 `useDeepLinkRouter` 實現無刷新平滑切換，保留當前滾動位置與編輯狀態。
- **以體驗為先解鎖圖片快取容量 (Experience-First Media Cache Unlocking)**: 外部景點圖片上限擴充至 300 張（約 30MB），保障出國離線重度使用體驗，並透過 Cloudflare Worker 反向代理注入 `Access-Control-Allow-Origin: *`，防止 Safari 7~10MB Opaque 填充配額爆炸。
- **離線快取真因釐清與過度工程化及時熔斷 (Over-engineering Circuit Breaker)**: 開發模式 (npm run dev) 預設阻斷 Service Worker 註冊以保護 HMR 免受污染，測試 PWA 離線能力應走標準生產預覽流程 (npm run build && npm start)，嚴禁盲目跨層在 RootLayout 注入 raw HTML/CSS inline splash 等破壞 Next.js 架構純潔性的補丁。
- **Precache 動靜態資產解耦原則 (Precache Dynamic Chunk Decoupling)**: 現代全端 SSR/ISR 框架（Next.js）的動態 Chunks 每次構建皆帶隨機 Hash。**嚴禁將動態 JS Chunks 放入 Service Worker 的 install Precache 清單**。Precache 僅保留 `public/` 穩固資產與根 App Shell `/`；動態 JS/CSS Chunks 100% 交給 `runtimeCaching` 的 `CacheFirst`，在瀏覽器首次請求真實 URL 時動態緩存。
- **Service Worker 絕不向瀏覽器舉白旗 (Zero-Response.error Invariance)**: 在 Navigation Fallback 策略中，`handlerDidError` 絕對禁止回傳 `Response.error()`。必須提供內聯 Zero-JS 物理 HTML/CSS 骨架，根絕 WebKit 彈出原生斷網報錯。
- **WebKit Service Worker 註冊快取隔離 (`updateViaCache: "none"`)**: 所有現代 PWA 註冊必須顯式指定 `{ updateViaCache: "none" }`，切斷瀏覽器內部 HTTP 緩存對 `sw.js` 檔案的干擾，確保版本迭代即時生效。
- **Web 標準黃金組合 vs 外部重型引擎 (Web Standards Golden Path over Heavy Sync Engines)**: 在 Local-First 選型中，堅決拒絕引入高侵入性的 WASM SQLite（如 PowerSync / ElectricSQL，需重構 80% 後端）或純文字 CRDT（如 Yjs，破壞強關聯關聯型結構）；堅定以「Serwist SW + SWR/Zustand + IndexedDB + Client-Generated UUIDv4」打造專屬旅遊場景的輕量化頂級架構，成熟度已達 85%，後續循序引進 `fractional-indexing` 補齊最後一哩路。
- **Service Worker Ready 永不裸奔原則 (Service Worker Ready Hard-Timeout Invariance)**: `navigator.serviceWorker.ready` 嚴禁直接無防護 `await`（在未就緒環境下為永不 reject 的 pending Promise）。必須封裝 `getReadyServiceWorker(timeoutMs = 5000)` 搭配 `Promise.race` 與動態按需註冊，逾時安全回退並由 `finally { setIsLoading(false) }` 釋放按鈕狀態，根除介面無限轉圈死鎖。
- **客戶端自訂 Fetch Wrapper 授權傳遞標準 (Dynamic Auth Header Injection over Supabase Client Tampering)**: 在匿名或自訂 ID（`user_uuid`）場景下寫入啟用 RLS 的 Supabase 資料表（如 `push_subscriptions`），不破壞 Client 純潔性亦不放寬 RLS 安全標準；改在 `createClient` 建立時透過 `global.fetch` 動態注入 `x-user-id` 標頭，達成安全透明且無副作用的認證傳遞。
- **明確退出意圖優先於實體訂閱存在 (Explicit Opt-Out State over Blind Rehydration)**: 解決瀏覽器底層實體訂閱與應用層偏好不同步問題。引入 `localStorage.setItem("push_opt_out", "true")`，在狀態還原時若偵測到 opt-out 標記，即便瀏覽器底層仍回傳訂閱，前端強制視為已退訂，杜絕重新整理時的流氓重開。
- **權限封鎖情境下的同理心引導原則 (Actionable Guidance over Dead-end Disabled UI)**: 系統權限被拒（`Notification.permission === 'denied'`）絕不可直接將開關設為 `disabled` 讓使用者陷入死胡同。應保持按鈕可點擊並彈出圖文引導對話框，教學網址列解鎖步驟，賦予使用者自我修復能力。

### 5. 後端高併發、資料庫與健康架構 (Backend Concurrency, Supabase & Health Probes)
- **純記憶體存活探針與獨立保活解耦架構 (Zero-Blocking Health & Keep-Alive Decoupling)**: `/health` 端點堅持 0ms 純記憶體計算（單一職責原則），完全不觸發任何外部網路 I/O 或資料庫查詢；Supabase 7 天防休眠保活由 Lifespan 獨立非同步背景定時循環（每 6 小時一次）靜默守護，達成極限並發安全與 100% 外部監控免疫。
- **三層健康檢查分流機制 (Tri-Tier Health Probe Hierarchy)**: `/health` 作為 Liveness Probe 提供 0ms 純記憶體快速探針；`/health/deep` 作為 Readiness/Diagnostics Probe 提供帶 2.5s 硬熔斷的非同步 Supabase 深度檢查。
- **後端時間處理時區原子一致性 (Timezone-Aware Atomicity)**: 伺服器啟動時間與每次請求計算必須同步採用 `timezone.utc`，杜絕因 naive/aware 混用導致的 TypeError 致命崩潰。
- **AI 座標直出 + 動態 Fallback 雙層保障 (Inline Coordinates with Dynamic Fallback)**: AI 生成行程時直接輸出經緯度座標（精度小數點後 4 位），後端 `_safe_geocode`（Semaphore 10 + 2.5s 硬熔斷）僅對座標缺失或為 0 的景點進行補查，省去 80%+ 外部 API 網路延遲。
- **母體區域繼承原則 (Mother Region Inheritance)**: 行程景點地理編碼以母體目的地中心點為 Proximity Bias，國碼獨立解析注入，解決 Photon 不含 `country` 欄位導致 `dest_country` 永遠為 `None` 的 P0 隱患。
- **原子日期平移與雙向位移保護 (Atomic Date Range Shift & Protection)**: 後端 `PATCH /api/trips/{trip_id}/dates` 端點，出發日提前採逆序迭代，延後採正序迭代，行程縮短提供 `merge` 與 `delete` 雙重保護。

### 6. CI/CD、工程化守門與自動化 (DevOps, Quality Gates & Tooling)
- **PowerShell 確定性熔斷守門架構 (Fail-Fast PowerShell Execution Harness)**: 在 Windows 環境下，嚴禁依賴非熔斷的 `;` 或無效的 `&&` 串接指令。所有工作流與守門腳本必須明確宣告 `$LASTEXITCODE` 檢查（`if ($LASTEXITCODE -ne 0) { exit 1 }`），確保任何一級（TypeScript、ESLint、Vitest、Pytest）失敗時能立即物理中斷，杜絕偽綠燈提交。
- **雙模 AST/正則防禦架構 (Dual-Mode AST/Regex Audit Pipeline)**: 對於 JSX 樹狀結構複雜的樣式反模式（如 Flex Truncate 匿名區塊、Virtuoso 直接 DOM 操作），放棄過度工程化的單一 AST 比對，採 AST 節點鎖定搭配正則約束，兼顧精確度與零偽陽性。
- **三重活體驗收防線 (Tri-Layer Verification Protocol)**: 底層依賴與編譯鏈更新時，驗收絕不能僅停留在靜態型別層（tsc），必須串聯 npm audit、vitest 與 next build 進行真實驗收。
- **overrides 原地安全合併原則 (In-Place Override Merging)**: 在既有 package.json 配置依賴覆蓋時，嚴禁盲目新增重複鍵，必須採增量原地合併以保留既有修復，杜絕 JSON 語法解析錯誤。
- **基礎設施宣告權威性原則 (Infra-as-Code Authority)**: 雲端資源參數（如 Cloud Run `--timeout 600s`）必須在 `.github/workflows/deploy-backend.yml` 宣告，杜絕 Console 手動設定被 CI/CD 無預警洗回。
- **Tiered Memory 架構與神經重組 (Auto Dream & AI Recombination)**: 大腦記憶維護採用分層神經壓縮模式，以原生 Antigravity CLI 驅動，新舊日誌無縫融合並保留歷史脈絡與技術債。
- **手冊即事實單一來源原則 (Documentation Truthfulness over Aspirational Copy)**: 軟體系統說明手冊必須 1-to-1 忠實映射代碼庫實作，堅決杜絕早期規劃的「願景型功能（Aspirational Features）」或工程術語；未實作機制絕不寫入手冊，所有操作路徑必須完全符合當前介面。
- **3D 巡航空間避讓與人體工學 (Dynamic Spatial Evacuation over Static Overlap)**: 3D 動態低空巡航啟動時，右上角常駐地圖控制項透過 CSS Transition 宣告式動態淡出與禁用指標事件（`pointer-events-none`），退出後平滑恢復，解決相機視角干擾與按鈕物理碰撞。
- **ISO 4217 法定貨幣白名單與國旗安全回退標準 (Strict ISO 4217 Fiat & Flag Fallback Standard)**: 在記帳中間層建立 110+ 種官方主權法幣白名單切斷非主流代幣雜訊，並維護 `CURRENCY_TO_COUNTRY_CODE` 確定性映射與本地多層 SVG 回退，徹底根除 Flag CDN 404 破圖。
- **去中心化 Git 身分投影與官方 ID 隱私信箱標準 (Decoupled Git Identity & ID-Pinned Privacy Standard)**: Git Commit 協議僅傳遞純文字 Name 與 Email，無中心化 GitHub ID 欄位。GitHub 將 Email 視為身分與貢獻熱力圖的對帳代幣，誤填範例信箱（如 `example.com`）會引發第三方帳號碰撞冒領。專案與全域環境一律強制固化採用 GitHub 官方 ID 隱私信箱格式（`223093762+tyrantpiper@users.noreply.github.com`），達成真實私人信箱 100% 隱蔽與貢獻度 100% 唯一綁定。
- **不可逆獨立封裝備份與租約前置獲取原則 (Hermetic Bundle Backup & Fetch-Before-Lease Invariance)**: 執行歷史重構（`git-filter-repo`）時，因工具預設會遍歷重寫所有 local refs 並移除 origin，備份防禦必須封裝為完全獨立於倉庫外的單一二進位檔案（`.bundle`）並經由 verify 檢驗；重新掛載 remote 後必須先 `git fetch origin main` 同步遠端基準指針，方可安全執行 `--force-with-lease` 覆蓋。

### 7. 零成本搜尋、Cloudflare 邊緣代理與 RAG Grounding 架構 (Zero-Cost Search, Edge Anycast Proxy & Grounding)
- **邊緣檢索執行器取代傳統 Forward Proxy (Edge Search Runner over TCP CONNECT)**: `ddgs` 依賴的 `primp` 需要標準 HTTP CONNECT TCP 隧道代理，標準 Serverless/Worker 無法透明代理 raw TCP。架構決策將 Worker 升級為「邊緣檢索執行器（Edge Search Runner）」，由全球 Anycast 節點聚合檢索並回傳乾淨 JSON，後端以輕量 HTTPX 呼叫，零機房 ASN 阻擋風險。
- **雙通道並行競速與超時阻斷 (Parallel Dual-Channel with Strict AbortSignal)**: DuckDuckGo Lite 對資料中心節點實施 Tarpit（慢速阻斷延遲）。Worker 採用 `Promise.all([fetchDDG(), fetchWiki()])` 同時發起 Wikipedia 全文搜尋與 DDG Lite，並將 DDG 鎖死在 1.5s 快速中斷，保證全鏈路 1.1s 內完成結算。
- **維基百科全文檢索優於前綴補全 (Full-Text Search over Prefix OpenSearch)**: Wikipedia OpenSearch API 為前綴比對，查詢「京都清水寺」時因條目名為「清水寺」回傳空陣列；全面切換至 `action=query&list=search` 全文語意搜尋，達成 100% 條目命中。
- **搜尋態工具物理卸載防衛 (Physical Tool Unloading in Search Intent)**: LLM 在看到價格數字時極易將詢價誤判為記帳。在 Intent Router 中將 `add_expense` 物理卸載，從根本杜絕幻覺彈窗。
- **懸空工具調用對稱合成防衛 (Dangling Tool Calls Auto-Synthesis)**: 若對話歷史中模型上一輪輸出了 `function_call`，但使用者下一輪直接發話而未包含 `function_response`，會觸發 Gemini 400 Bad Request 狀態機崩潰。在建構歷史時自動合成對稱的虛擬 `functionResponse`（`client_handled`），徹底免疫協議報錯。
- **AC-4 嚴格 1對1 引文剪裁對齊原則 (Strict 1-to-1 Citation Pruner)**: 對 LLM 串流產出的文本正則萃取實際標註的 `[1]`, `[2]` 錨點，僅保留被提及的 Sources 並賦予對應索引，未引用的候選來源一律物理剪除，杜絕引用標籤與內文脫節。

### 8. 全球詞庫瘦身、動態 Region 分流、時間感知狀態機與實證安全架構 (Taxonomy, Dynamic Regions, Temporal & Empirical Security)
- **動態雙軌 Region 分流與搜尋詞庫瘦身原則 (Dynamic Region Resolution & Taxonomy Slimming over Overloaded OR Queries)**: DuckDuckGo 等現代語意搜尋引擎對布林運算符 `OR` 支援極度脆弱，長句串接 `PTT OR Dcard OR Tabelog` 會導致 DDG 將整個查詢判定為過度限制而回傳 0 筆結果。架構決策徹底移除 `OR`，精煉為自然語言主題詞，並實作動態雙軌分流：在地軌根據目標地動態映射本地 Region（如 `jp-jp`、`tw-tzh` 等，未命中回傳 `None` 讓 DDGS 自動適配），全球軌鎖定 `us-en` 查詢 Reddit 國際視角，徹底拔除引發 DNS 崩潰的 `wt-wt` 寫死代碼。
- **邊界感知與長度降序時區推斷原則 (Boundary-Aware Longest-Match Timezone Inference)**: 在由關鍵字推斷目的地時區時，短關鍵字（如 `th` 代表泰國曼谷、`la` 代表寮國）以純字串包含 `if kw in text` 比對時，會無差別劫持包含該字母組合的所有英文單詞（例如 "South New York"、"Perth" 命中 `th`，"Island"、"Los Angeles" 命中 `la`）。架構規範：針對 ASCII/拉丁單詞強制加上正則邊界 `\b{kw}\b`，CJK 語系維持包含比對，並在初始化時將所有關鍵字按字串長度由長至短排序（`SORTED_TIMEZONE_MAP`），長詞優先匹配，徹底根治子字串劫持。
- **DDGS 8 引擎並發檢索與 5.2s 黃金超時校準 (Multi-Engine Concurrency & 5.2s Timeout Calibration)**: DDGS 擴充至 8 個真實搜尋引擎並發檢索，涵蓋多元資訊來源，並自適應排除 Wikipedia 條目（由 Cloudflare Edge 獨立處理）。將 Tier 1 超時時間從 2.8s 放寬至 5.2s（實測 8 引擎並發平均耗時 3.5s~4.14s，5.2s 杜絕了偽逾時跌入備援層）。
- **伺服端與客戶端工具分離防禦 (Server-Side vs Client-Side Tool Decoupling)**: 部分工具（如 `get_world_time`, `search_web`）需在後端伺服器立即執行以獲取上下文回填模型，而業務工具（如 `add_expense`, `view_itinerary`）必須傳遞給前端客戶端觸發 UI 動作。後端在接收到模型的 tool calls 時，建立分離分流機制：伺服端工具由後端直接執行並遞迴送回模型繼續推理，客戶端工具則安全保留於 SSE 事件傳遞給前端，杜絕狀態混淆。
- **即時端側時間感知與行程生命週期狀態機 (Real-Time Temporal Awareness & Lifecycle State Machine)**: 前端請求標頭動態注入 `client_time`（ISO 8601 當前時間）與 `client_timezone`。後端建立 `TemporalService`，提供端側時間解析、相對時差天數與小時計算，以及行程生命週期狀態機（`PLANNING`, `PRE_TRIP`, `IN_TRIP_ACTIVE`, `POST_TRIP`），並落實神經時間夾擊（System Instruction + Prompt Header）即時注入。
- **實證導向的安全稽核與零功能降級原則 (Pragmatic Empirical Security Audit over Blind Warning Suppression)**: 靜態程式碼分析工具（如 CodeQL）依據通用啟發式規則生成告警，常將安全的業務邏輯（如 URL 域名包含檢查以決定徽章 Emoji、固定 API 前綴的 query 傳參）誤判為安全漏洞。架構決策堅持「實證先於合規」：在沒有真實安全風險或可利用攻擊向量的前提下，嚴禁盲目重構核心模組，守護系統零功能降級與絕對穩定度。

### 9. 頂級自訂網域、同源邊緣防護罩與 GFE 動態名牌路由架構 (Custom Domain, Edge Shield & GFE Host Routing)
- **同源邊緣防護罩取代客戶端跨域暴露原則 (Same-Origin Edge Shield over Client-Exposed Cloud Run)**: 在前端客戶端暴露後端真實服務網址（`process.env.NEXT_PUBLIC_API_URL` 直通 Google Cloud Run）會引發後端被直接探測與複雜 Preflight 開銷。架構確立客戶端一律向同源 `/api/...` 發起相對請求，由 Cloudflare Anycast 邊緣節點上的 Worker 依路徑安全識別並轉發，阻斷外部直接探測後端真實 IP / 服務網址。
- **GFE 虛擬主機名牌動態覆寫原則 (GFE Virtual Host Dynamic Rewrite over $2,000/mo Cloudflare Enterprise Origin Rules)**: Google Cloud Run 的 GFE 多租戶負載均衡器強制依賴 HTTP `Host` 標頭識別目標容器；非 `*.run.app` 之自訂網域 Host 會被 GFE 直接以 404 退件。Cloudflare 官方 Origin Rules 的 Host 覆寫被鎖定在每月 2,000 美元企業版付費牆；架構決策透過免費 Cloudflare Worker 在 `fetch()` 階段動態覆寫 `Host: antigravity-backend-*.run.app`，實現 0 成本 Anycast 邊緣轉發。
- **Vercel 本地路由邊緣旁路白名單原則 (Vercel Native Route Edge Bypass Whitelist)**: 專案內原生運行於 Vercel 的輕量 Serverless API（如 `/api/sign-cloudinary` 與 `/api/parse-receipt`），若被全量無差別轉發至 Google Cloud Run 會引發後端 404 報錯。Worker 必須建立精確白名單，遇 Vercel 本地專屬路由直接直連 Vercel 源站，不驚動 Google Cloud Run。
- **PWA 本地資料沙箱雙軌共存原則 (Dual-Active PWA Storage Preservation over Forced Redirect)**: 瀏覽器 Local-First 存儲（IndexedDB / Cache Storage）受限於同源策略（Same-Origin Policy）。在新網域上線時若對舊網域（`travel-pwa-five.vercel.app`）實施強制 308 重定向，已安裝於手機桌面的老使用者將因 Origin 變更而遺失本機歷史行程。確立舊網域保持運作並透過伺服端同源代理呼叫後端，維持雙軌共存與資料安全。
- **多態 API Host 衍生與尾部斜線防禦架構 (Polymorphic API Host Derivation & Defensive Slash Sanitization)**: 前端 `getApiHost()` 在客戶端瀏覽器環境回傳空字串 `""`，伺服端優先回退 `INTERNAL_BACKEND_URL` / `NEXT_PUBLIC_API_URL`；所有網址必須經過正則清除尾部斜線（`replace(/\/+$/, '')`），杜絕反向代理下雙斜線（`//api/...`）解析失誤。
- **規格文件領域驅動拓撲化原則 (Domain-Driven Specification Hierarchy over Flat Spec Dumping)**: 規格文件全量依領域驅動（DDD）劃分為 6 大目錄（`ai`, `business`, `core-architecture`, `infra`, `search`, `ui-motion`），並建立頂層導航矩陣 `docs/specs/README.md`，杜絕平鋪檔案過多造成的維護退化。
- **多網域圖片邊緣代理全源放行與 CORS 注入標準 (Multi-Origin Media Proxy & CORS Injection)**: 邊緣反向代理 Worker（如 `cloudinary-proxy`）在實施防盜鏈檢查時，嚴禁單一寫死舊版 Vercel 網域。必須動態支援主網域 `tabijiapp.com`、`www.tabijiapp.com`、舊站與本地開發環境，並相容手機 Standalone PWA 無 Referer 模式；同時強制注入 `Access-Control-Allow-Origin: *`，防止 Canvas Tainted 污染破壞 PDF 行程匯出。

### 10. 資安審查、Google Mantis ✕ Cloudflare Sentinel 與 CLI 子代理人調度架構 (Security Sentinel & Subagents)
- **`agy` CLI 本地背景子代理人調度原則 (agy CLI Headless Subagent Dispatch Invariance)**: 在本機未配置 Docker 容器環境下，嚴禁依賴外部動態沙箱。全面利用 Antigravity 原生 CLI `agy.exe -p --sandbox` 作為背景子代理人調度引擎，在獨立 OS 行程中以乾淨上下文執行對抗證偽（Validator Critic），實現零歷史記憶污染（Zero Prompt Contamination）與嚴格的 Maker-Checker 物理隔離。
- **審查判定三元狀態機與零假陰性防禦 (Tri-State Verdict & Zero False-Negative Guarantee)**: 資安審查判定嚴格採用三態——`CONFIRMED`（實證漏洞）、`DISMISSED`（明確安全）、`INCONCLUSIVE`（未決）。任何因 CLI 未輸出結構化 JSON、進程逾時或模型被 safety filter 攔截之情境，一律強制標記為 `INCONCLUSIVE` 供人工介入，絕對禁止因解析失敗而預設判定為安全，杜絕靜默漏報。
- **L0 憲法 Human-Gated 補丁與雙軌修復規範 (RFC Diff & Exact Block Replacement Protocol)**: `@security`（Sentinel）角色嚴守「只回報，不私自改碼」憲法，產出漏洞報告時必須成對提供 RFC Unified Diff 與精確區塊替換指南（`target_content` / `replacement_content`）。既解決 Windows CRLF 破壞 `git apply` 的格式痛點，又確保修復動作必須經由人類明確授權後，由 `@dev` 實作並經由 `@qa` 驗證。
- **離線記憶體中單元 PoC 規範 (In-Memory Mock PoC over Live HTTP Requests)**: 漏洞驗證 PoC 嚴格禁止依賴本機運行中的 HTTP 伺服器或外部網路（不產出裸 `curl` 指令）。後端強制使用 `pytest` 搭配 `FastAPI TestClient`，前端使用純函式單元斷言，保證在完全斷網與本機伺服器離線時 100% 離線可重現。

### 11. 次世代 Agent 演化、開源地理拓撲與提示詞防護裝甲 (Next-Gen Agent, Hybrid Geocoding & Prompt Shield)
- **Sovereign Agentic Loops (SAL) 與 ReAct 意圖控制平面架構 (Sovereign Agentic Loops & Intent Control Plane)**: 解決 AI 助理從「單向文本預測生成器」向「真實世界感知—決策—行動閉環」演進時的額度失控與幻覺問題。確立在模型輸出 Tool Calls 與實際底層執行之間，必須建立後端控制平面 (Control Plane)：實施預算配額閥門 (Budget Gate)、參數型別嚴格白名單與防抖動機制；交替產生 Thought 與 Action，當外部 API 顯示景點休館或天候不佳時，由 Agent 主動發起修正，達成自癒閉環。
- **開源地理編碼雙引擎分流拓撲 (Photon OpenSearch Typo-Tolerance vs Nominatim 5.0 Precision Hierarchy)**: 針對開源地理資訊難以媲美 Google Maps 商業模糊搜尋的痛點，確立「前台即時輸入 vs 後端精確定位」雙軌分流：前台採用 95GB 輕量 Photon (OpenSearch) 提供極速 Autocomplete 與 Typo-Tolerance（容錯拼字模糊比對）；後端深層批次計算則掛載 Nominatim 5.0 (Python 重寫)，提取建築物微觀 Entrance 座標；複雜自然語言查詢（如「東京車站附近的壽司」）由 Gemini Query Parser 提煉結構化關鍵字後再行檢索。
- **母體區域繼承與國碼獨立解析防線 (Mother Region Proximity Bias & Explicit Country Code Resolution)**: 行程批次地理編碼中，單一景點常有簡稱或重名（如「朝市」、「水族館」）。確立必須提取母體目的地（如「北海道」）並藉由 `detect_country_from_keywords` 獨立確定 ISO 國碼（`dest_country`），解決開源 Geocoder 結果字典不含 `country` 欄位引發的國碼穿透失效；母體中心點座標僅作為 Proximity Bias 排序加權，嚴禁作為 Hard Lock 過濾器，兼顧周邊優先與跨國彈性。
- **神經三明治與動態隨機鹽漬標籤防禦 (Dynamic Salted Tags & Neural Sandwich Defense)**: 針對 LLM Agent 工具呼叫遭受提示詞注入（Prompt Injection）與標籤欺騙（Tag Spoofing）的防護標準化。每次 API 請求動態生成 8 碼隨機字串（`user_input_{salt}`）封裝使用者輸入；系統指令透過原生 `system_instruction` 通道傳遞直達神經中樞；並於提示詞序列的最末端強制附加 `[SYSTEM_SHIELD]` 神經三明治提醒（Reminder Defense），利用注意力機制在上下文最後一刻壓制越獄指令。

---

## [Failed Paths]

### 1. 圖形與地圖渲染踩坑
- **MapLibre v6 內部相機屬性移除 (`Unbound Transform Trap`)**: MapLibre v6 移除了 `map.transform`，而 `react-map-gl@8.1.0` 在 `transformToViewState` 中強依賴此屬性，造成執行時拋出 `TypeError: Cannot read properties of undefined (reading 'center')` 致命白屏。教訓：涉及包裝層（Wrapper Lib）的底層核心函式庫 Major 升級，不能只看 TypeScript 定義，必須深入檢查包裝層是否已對內部重構提供完整適配。
- **動態 Blob Worker 遭 CSP 攔截 (`Worker Blob CSP Trap`)**: 直接在客戶端使用 `new Worker(URL.createObjectURL(blob))`，在嚴格 CSP 標頭下遭瀏覽器拋出 `Refused to create a worker from 'blob:...'` 阻擋。教訓：第三方函式庫 Web Worker 必須走同源靜態檔案管道（`copy-maplibre-worker.mjs`）派發。
- **未宣告圖層指定 beforeId 引發崩潰 (`Premature beforeId Reference Trap`)**: 在 JSX 中宣告底層衛星影像時指定 `beforeId="day-trajectories-layer"`，但該圖層在 JSX 代碼中寫在衛星之後，MapLibre 依序解析引發 `Cannot add layer before non-existing layer` 致命錯誤。教訓：React-map-gl 圖層宣告應善用自然 JSX 階層排列，切忌跨越宣告順序參考不存在的圖層 ID。
- **拖曳手勢誘發 WebGL Canvas 重排掉幀 (`Unisolated WebGL Reflow Trap`)**: 拖曳以 `right/bottom` 定位的浮動圓球，未開啟硬體加速時會誘發主執行緒重新計算佈局並重繪大型地圖 WebGL Canvas，導致拖曳掉幀至 20fps。教訓：包含 WebGL 地圖的複雜視圖中，浮動動態節點必須明確宣告 `transform-gpu` 與動態 `will-change`，建立獨立 GPU 合成層。
- **JSDOM / SSR 建置通過帶來的偽陽性安全感 (`WebGL Canvas Testing Blind Spot`)**: `tsc --noEmit` 與 `vitest` 在 Node.js / JSDOM 環境下無法模擬真實 WebGL 上下文與 Canvas 交互，誤導做出「升級通過」的斷言。教訓：WebGL 與 Canvas 相關改動必須以瀏覽器真實繪製為唯一驗收標準。
- **MapLibre 動畫排程競爭陷阱 (`Camera Animation Preemption Trap`)**: 在羅盤點擊處理器中先調用 `targetMap.easeTo({ bearing: 0, pitch: 0, duration: 400 })`，接著同步調用 `targetMap.fitBounds(...)`。使用者在旋轉地圖後點擊羅盤，地圖僅縮放了邊界，相機角度依然保持歪斜。原因在於 MapLibre 相機是單一狀態機排程，後續的 `fitBounds` 立即掐斷了先前的 `easeTo` 動畫且預設維持原有視角。教訓：複合相機運動必須整合在單一呼叫（`fitBounds(bounds, { bearing: 0, pitch: 0, ... })`）原子執行。
- **雙 WebGL 上下文引發 Safari 崩潰 (`Dual WebGL Context Safari Crash Trap`)**: 探討使用 WebGL 片段著色器為 UI 按鈕繪製次表面折射效果，但在 iOS 測試機上偶發白屏，終端出現 `WebGL: CONTEXT_LOST_WEBGL` 警告。原因在於頁面中已運行大型 MapLibre WebGL 地圖畫布，在 DOM 上額外掛載小型 WebGL Context 容易突破 iOS Safari 嚴格的 GPU 記憶體與 Context 總數配額。教訓：PWA 的 UI 控制項嚴禁使用額外 WebGL Context，一律採用純 CSS 濾鏡與 Inset 陰影模擬光學折射。
- **手勢基準點清理遺漏導致跨手勢座標殘留 (`Stale Touch Pos Reference Trap`)**: 長按防手震手勢機在平移開始（`onMoveStart`）未清理 `touchStartPosRef.current = null`，導致從邊界脫離後舊座標污染新長按判斷。教訓：所有手勢狀態機在進入平移生命週期時，必須原子化重置觸控基準參考點。

### 2. 狀態持久化、快取與自癒踩坑
- **原生 fetch 吞沒 404 引發 SWR 假成功 (`Raw Fetch 404 Swallowing Trap`)**: 在 fetcher 中直接使用 `fetch().then(r => r.json())` 未檢查 `r.ok`。後端回傳 404 時 Promise 依然正常 resolve，SWR 將 `{ detail: "Trip not found" }` 判定為成功資料寫入快取，導致 `error` 永遠為 `undefined`，SWR 的 `onErrorRetry` 與自癒完全啞火。教訓：所有底層 Fetcher 必須嚴格檢驗 `!r.ok` 並主動拋出標準 `HttpError`。
- **未經二次核驗草率清除快取 (`Unverified 404 Eviction Trap`)**: 僅憑一次 GET 404 就直接清除本地快取並切換行程，在行動網路偶發抖動或 CDN 節點異常時，使用者正在看的合法行程會被誤切換。教訓：自癒機制必須搭配「清單總表二次核驗（List Double-Check）」，確認清單中也查無此人時才允許執行破壞性清除。
- **Zustand 與 legacy localStorage 雙重持久化漂移 (`Dual Persistence Drift Trap`)**: 僅透過 `localStorage.removeItem('active_trip_id')` 清理快取，忽略了 Zustand 的 `persist` 中介軟體仍將舊 ID 儲存在 `trip-storage`，重新整理後死 ID 再次復發。教訓：具備多重持久化機制時，必須以 Zustand store action 為單一真實來源並同步清理 legacy 鍵。
- **傳統 DOM scrollIntoView 在虛擬化清單下的無效陷阱 (`Virtual List Null DOM Trap`)**: 嘗試使用 `document.getElementById('expense-' + id)?.scrollIntoView()` 尋找目標項目。在項目數量超過可視區域時，Virtuoso 尚未將其渲染至 DOM 樹中，`document.getElementById` 必為 `null`。教訓：虛擬化滾動引擎必須使用虛擬庫提供的 Ref Handle（`virtuosoRef.current.scrollToIndex`）進行索引計算與滾動。
- **行程切換無腦重置天數抹除外部深層意圖 (`Blind Day-1 Overwrite Trap`)**: 在 `itinerary-view.tsx` 中監聽 `[activeTripId]` 並直接調用 `setDay(1)`，導致推播傳入的 `day=0` 總覽參數被瞬間覆寫回第一天。教訓：在多狀態驅動視圖中，狀態重置必須檢查當前全域 Store 是否已有高優先順序的顯式指定值。
- **父層 SWR 抖動引發 isMounted 誤殺非同步回傳 (`isMounted Weather Drop Trap`)**: 總覽天氣卡片在 `useEffect` 中發起耗時 1 秒的 Open-Meteo 請求。首次點入時父層 SWR revalidate 觸發 `setDailyLocs`，引發 Effect cleanup（`isMounted = false`），導致氣象回傳時被 `if (!isMounted) return` 丟棄，卡在骨架屏。教訓：長耗時資料抓取應委託全域 Store，回寫全域狀態而非組件局部 state。
- **Zustand 非同步 IDB 靜態取值未響應 (`Zustand Async IDB Silent Trap`)**: `weatherStore` 使用非同步 `idbStorage`，若組件僅呼叫靜態 getter，IndexedDB 完成 rehydrate 後組件無法感知。教訓：組件頂層必須以 `useWeatherStore((s) => s.fiveDayCache)` 響應式訂閱。

### 3. iOS 原生與 UI 元件踩坑
- **Flex 容器未封裝文字直用 truncate 引發擠壓 (`WebKit Anonymous Flex Truncation Trap`)**: 在 Header 直接使用 `className="flex items-center min-w-0 truncate"` 包覆文字與 `<Badge>`，在 WebKit/iOS 渲染引擎下裸文字包入 Anonymous Block，計算寬度時強制將同級 `shrink-0` 徽章壓縮或推出可視範圍。教訓：Flex 容器內的文本溢出截斷，務必單獨由子 `<span className="truncate">` 承擔。
- **推倒式拆檔引發的閉包斷裂與 SWR 快取丟失 (`Premature Component Decomposition Trap`)**: 曾嘗試將 `chat-widget.tsx` 暴力解耦拆分至 3 個獨立組件，導致 `useDynamicPolling`、`prevTripIdRef` 雙清閉包、`textareaRef` 焦點控制以及多個自癒狀態遺失，引發大量測試報錯與死循環震盪。教訓：在缺乏完整抽象層保護前，高耦合高密度邏輯組件應優先採原地微創增強，嚴禁過度工程化的推倒重來。
- **Framer Motion 動態 Key 引發元件重新掛載與重複請求 (`Dynamic Key Remount Trap`)**: 在 `app-shell.tsx` 中為四大視圖外層加上 `key={`view-${activeView}`}` 時，導致換頁時 React 銷毀重新掛載引發 API 重複發送。教訓：常駐型主頁面切換動效嚴禁使用動態 `key`，應使用靜態標識搭配屬性動畫。
- **React 19 在 useEffect 內同步 setState 觸發 cascading renders (`React 19 Cascading Renders Trap`)**: 在 `DailyWeatherStrip` 的 `useEffect` 內若同步呼叫 `setIsTimedOut(false)`，會被 React Compiler 判定為串聯重新渲染引發 Linter 報錯。教訓：改用衍生狀態 `const showTimeoutFallback = isTimedOut && !hasData && !isLoading`，`useEffect` 僅負責逾時定時器生命週期。
- **試圖在 React RootLayout 內嵌 Raw HTML 假裝原生 Splash (`Inline Splash Over-Engineering Trap`)**: 在 Next.js App Router 體系下硬塞 90 行 inline `<style>`、`id="pwa-native-splash"` 與原生 DOM 操作腳本，破壞現代架構純潔性，忽視了真實 PWA 在安裝後會由 OS (iOS/Android) 依據 `manifest.json` 自動渲染原生啟動畫面的基本事實。
- **React State 延遲導致 Hydration FOUC 閃爍 (`Hydration Dark Mode FOUC Trap`)**: 在 `bottom-nav.tsx` 的指示器使用 `style={{ backgroundColor: isDark ? "rgba(...)" : "rgba(...)" }}`，深色模式重新整理頁面時，指示器在第 1 幀短暫顯示為淺色底塊。原因在於 `ThemeContext` 初始 state 為 `isDark = false`，需待客戶端掛載後透過 `useEffect` 讀取 `localStorage`。此時 HTML 標籤早已由 SSR 帶有 `class="dark"`，但 inline style 的 React state 尚未更新。教訓：常駐型核心元件的暗黑適配必須由 CSS `dark:` 變體承擔，堅決不讓未就緒的 React state 決定首屏關鍵樣式。
- **React Compiler Effect 同步 setState 串聯渲染報警 (`React Compiler Cascading Renders Trap`)**: 在 `useEffect` 內部同步調用 `setIsIdle(false)`，觸發 React Compiler 針對 Effect 內部同步 setState 導致 cascading renders 的嚴格攔截。教訓：初始狀態直接設定 `isIdle = false`，運動與懸停狀態改採派生計算（`isVisibleAwake = !isIdle || isMapMoving || isHovered`），搭配非同步微任務（`setTimeout(..., 0)`）重置計時器，杜絕同步渲染瀑布。
- **行動端 Safari/Chrome Sticky Hover 黏滯陷阱 (`Sticky Hover Retention Trap`)**: 在觸控螢幕上直接套用 Tailwind `hover:opacity-100`，手指點擊按鈕後，行動瀏覽器強制將元素維持在 `:hover` 偽類，導致計時結束仍無法回到 25% 幽靈態。教訓：在 `onPointerEnter` / `onPointerLeave` 中嚴格檢驗 `if (e.pointerType === "mouse")`，切斷觸控設備對 Hover 的非預期黏滯。
- **CSS 動畫進場位移導致的聚光燈 42px 偏位殘影 (`Animation Transience Snapshot Trap`)**: 點擊進入步驟 3 時，行程列表伴隨 Framer Motion 的滑入過渡。聚光燈因過早讀取 `getBoundingClientRect()`，鎖定在移動中的暫態座標，導致高亮框相對於卡片永久向左偏移 42px。教訓：放棄單次採樣與固定延遲 `setTimeout`，實作 180ms 最小時間窗 + 連續 4 幀位移 `< 0.5px` 的速度收斂引擎，只有當座標連續 4 幀完全不變時才解鎖高亮框。
- **提升容器 ID 誘發的刪除按鈕誤觸陷阱 (`Destructive Button Accidental Click Trap`)**: 為使步驟 4 完整框選卡片，將 ID 綁至 `<Card>`。使用者點擊高亮孔洞時，原生穿透轉發預設點擊第一個 `button`，直接觸發了卡片右上角的紅色垃圾桶刪除按鈕。教訓：在橫幅按鈕新增 `data-tour-action="primary"`，並在穿透邏輯中硬性過濾排除包含 `.bg-red-500` / `variant='destructive'` 的元素。
- **子視圖返回時單次 scrollTo 被截斷歸零陷阱 (`Premature Single-RAF Scroll Truncation Trap`)**: 從使用說明返回 Profile 主頁面時，若直接在 `useEffect` 或單次 RAF 中執行 `container.scrollTo({ top: pos })`，由於 DOM 容器的內部高度尚未完成重排，瀏覽器自動將捲動值截斷為 0，造成每次返回都跳回頁首。教訓：升級為雙重 RAF 排程，確保在瀏覽器 Reflow 完全結束後的下一幀才執行捲動定位。

### 4. 離線架構與 PWA 踩坑
- **Service Worker 嚴格路徑比對導致帶參冷啟動白屏 (`Strict Navigation URL Mismatch Trap`)**: PWA 從桌面圖示啟動時常攜帶 `?source=pwa`，若 Service Worker 宣告 `navigateFallback` 未開啟 `ignoreSearch: true`，比對失敗直接由瀏覽器發起真實網路請求，在斷網情境下拋出小恐龍死白屏。教訓：離線 App Shell 導航快取必須宣告 `matchOptions: { ignoreSearch: true }`。
- **斷網時誤信 SWR 空清單抹殺本機行程 (`Offline Empty-Array Wipe Trap`)**: 斷網冷啟動時 SWR 請求 `/api/trips` 失敗回退為空陣列，`trip-context.tsx` 誤判使用者無行程而調用 `setActiveTripId(null)` 並清空 localStorage，使整個 App 癱瘓。教訓：斷網時 SWR 狀態不可信，必須嚴格捍衛本機快取與 activeTripId。
- **直接將未過濾的 SWR 快取 Map 序列化至 IndexedDB (`DataCloneError Trap`)**: SWR 內部的 `cacheMap` 包含未決的 Promise、變異調度器與閉包函式，若未經過濾直接對其執行 IndexedDB `set()` 會觸發瀏覽器 `DataCloneError: could not clone` 致命崩潰。教訓：SWR 持久化必須將資料層（Data Snapshot）與排程/Promise 狀態解耦，由 `idb-storage.ts` 定向寫入純乾淨的 JSON 快照。
- **盲目 npm audit fix --force 引發的破壞性降級 (`Serwist Destructive Downgrade Trap`)**: `npm audit fix --force` 試圖將 `@serwist/turbopack` 降級至骨董版本 9.5.2 破壞 Next.js 16 打包。教訓：間接依賴漏洞治理應優先採用 npm 原生 overrides 原地鎖定，杜絕向後降級。
- **Precache 動態 Chunk 導致 Service Worker 物理銷毀 (`Precache 404 Poison Pill Trap`)**: 本地編譯生成帶 Hash 的 `sw.js`（含 56 個本地 chunk hash），推送到 Vercel 後雲端 Hash 改變。手機安裝 SW 時請求本地 Hash 回傳 404，觸發 W3C 規範直接銷毀 SW，導致手機完全無 SW 服務。教訓：Precache 清單必須永遠保持 100% 命中率，脆弱的動態編譯產物絕不可放入 Precache。
- **WebKit 頑固 HTTP 快取阻礙 SW 更新 (`WebKit sw.js Cache Retention Trap`)**: 未設定 `updateViaCache: "none"`，iOS 常常連續數天使用舊的 Service Worker 檔案，導致新部署的修正無法觸達使用者。教訓：`navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" })` 是 iOS PWA 的標配。
- **`navigator.serviceWorker.ready` 永久掛死陷阱 (`SW Ready Infinite Hang Trap`)**: `navigator.serviceWorker.ready` 規格為永不 reject 的 Promise。在未註冊或 Safari 無痕模式下調用會永久卡在 pending 狀態，導致後續代碼與 finally 區塊無法執行，介面轉圈永久鎖死。教訓：所有 `serviceWorker.ready` 調用必須搭配 `Promise.race` 與 5 秒硬逾時定時器。
- **Supabase RLS 政策引發的靜默拒絕陷阱 (`Silent RLS Rejection Trap`)**: 啟用 RLS 的資料表（如 `push_subscriptions`）在匿名客戶端寫入時遭 PostgreSQL 阻擋，Supabase 不拋例外僅回傳空成功或 403。前端若無嚴格 error 判定會產生偽成功幻覺。教訓：全局注入 fetch wrapper 攜帶 `x-user-id`，並嚴格判定 `if (error) return false`。
- **Service Worker 重新整理時的流氓重開陷阱 (`Aggressive Push Re-subscription Trap`)**: 使用者退訂時若瀏覽器後台撤銷稍慢，頁面重新整理初始化會再次查詢到現存 subscription 並誤將狀態設為已開啟。教訓：引入 `localStorage.setItem("push_opt_out", "true")` 作為主動退出意志憑證，初始化時強制維持關閉。
- **權限遭阻擋時將按鈕設為 Disabled 的死胡同陷阱 (`Disabled State Dead-end Trap`)**: 在 `Notification.permission === 'denied'` 時直接設置 `disabled`，剝奪使用者自救路徑。教訓：移除 disabled，改以點擊彈出引導彈窗，教學至瀏覽器網址列手動解鎖。

### 5. 後端高併發、資料庫與健康探針踩坑
- **多線程背景調用非 Thread-Safe 的 Supabase Client (`Supabase Client Deadlock`)**: 在 `/health` 每次請求中透過 `asyncio.to_thread` 調用 `supabase.Client`，當 UptimeRobot 多節點併發打入時觸發 `httpcore` 連線池內部死鎖 (Deadlock)，導致全域線程池耗盡、請求掛起 30s 並由 GFE 拋出 500。教訓：禁止在多線程中調用非 Thread-Safe 的同步 SDK，應使用原生非同步 `httpx.AsyncClient` 或將保活與請求完全解耦。
- **健康檢查端點攜帶副作用 (`Health Check Side-Effects Trap`)**: 將資料庫保活或連線預熱強行掛在健康檢查端點上，一旦外部網路波動或連線鎖爭搶，健康檢查連帶失敗導致整台伺服器被誤判死亡。教訓：健康檢查必須保持 Idempotent 與無副作用。
- **後端時間處理時區不一致性 (`Timezone Mismatch Trap`)**: 伺服器啟動時間與請求時間混用 naive/aware，引發 `TypeError: can't subtract offset-naive and offset-aware datetimes`。教訓：全域時間運算統一強制帶有 `timezone.utc` 標籤。
- **Photon 回傳結構盲區 (`Photon Missing Country Trap`)**: 錯誤假設 Photon/Nominatim 的回傳結果包含 `country` 欄位，導致 `dest_country` 永遠為 `None`。教訓：取用欄位前必須直接檢驗 API 回傳原始結構。
- **OSM Nominatim 併發限速衝突 (`Nominatim Concurrency Limit Trap`)**: OpenStreetMap Nominatim 官方限速 1 req/s，AI 批次 5 並發查詢觸發 429 或 ReadTimeout。第三方免費用量受限服務必須有前置命中跳過條件。

### 6. CI/CD、工程化守門踩坑
- **PowerShell 分號串接導致錯誤吞噬與假性放行 (`PowerShell Unhalted Chain Trap`)**: 在 Windows PowerShell 中使用 `cmd1; cmd2; cmd3` 串接指令時，即使 `cmd1` 噴錯，PowerShell 依然會繼續執行後續指令；使用 `&&` 則直接報錯 `The token '&&' is not a valid statement separator`。教訓：Windows 終端工作流必須顯式包裝 `if ($LASTEXITCODE -ne 0) { exit 1 }` 實施嚴格熔斷。
- **粗糙 AST Pattern 比對引發的偽陽性爆發 (`AST Pattern Overmatching Trap`)**: 企圖以單一寬鬆 AST Pattern 比對包含特定 CSS 類別的動態文字標籤，若未指定確切約束，會把全站所有 JSX 文字節點全部誤判。教訓：語法審核必須採約束性 AST 規則（Constraints & Regex）。
- **JSON 重複鍵盲區 (`Duplicate Key Trap`)**: 在已有 overrides 的 package.json 粗暴追加新區塊產生重複鍵語法錯誤。教訓：工程修改前必須嚴格確認既有代碼結構，堅持原地增量合併。
- **GFE 逾時引發的偽性 CORS 誤診 (`GFE 60s Timeout False CORS Trap`)**: 連線在到達 FastAPI Middleware Stack 前被 Google Front End 依據 60s 逾時強制斷開回傳不帶 CORS Headers 的 504 頁面。修改程式碼層 CORS Middleware 無效，根因在於基礎設施層逾時配置。
- **佔位範例信箱引發第三方帳號碰撞 (`Placeholder Email Collision Trap`)**: 誤用 `ryan@example.com`，被 GitHub 索引到同名外國開發者 `ryan-winkler`，導致 Vercel 的 `Created` 欄位展示陌生人頭像與名字。教訓：任何開發環境嚴禁使用 `example.com` 作為本機 Git Config，必須在全域 `~/.gitconfig` 預先固化正統帳號。
- **缺乏全域 Git 配置導致多專案身分漂移 (`Missing Global Gitconfig Trap`)**: 本機未曾建立 `~/.gitconfig`，導致不同專案各自為政且易殘留佔位信箱。教訓：開發機初次裝機或初始化環境時，第一優先級任務必須是全域宣告 `git config --global user.name` 與 `user.email`。
- **未考慮 git-filter-repo 重寫全域 Ref 的本地備份污染 (`Ref-Rewriting Self-Pollution Trap`)**: 在重寫前於本地同儲存庫建立備份分支，但 `git-filter-repo` 預設行為會重寫倉庫內的所有 local refs，導致備份分支一同被改寫。教訓：不可逆備份必須封裝為完全獨立於倉庫目錄外的單一二進位檔案（`.bundle`）。
- **未 Fetch 追蹤分支即調用 --force-with-lease 的租約斷裂 (`Un-anchored Lease Push Trap`)**: `git-filter-repo` 重構後會自動移除 `origin` remote，未執行 `fetch` 便直接 push 導致 lease 檢查崩潰。教訓：安全租約覆蓋前，必須強制以 `git fetch origin main` 同步遠端基準點。
- **純文檔提交無路徑過濾引發 GitHub Actions Runner 枯竭逾時 (`Doc-Commit CI Runner Starvation Trap`)**: 在未配置 `paths-ignore` 與 `concurrency` 的情況下，僅推送每日報告或 memory.md（純 markdown）仍無差別觸發包含 CodeQL、Frontend 與 Backend 的 6 個雲端 Job。在美國下班/台灣清晨等全球提交尖峰時段，短時間內連續推送迅速打滿 GitHub-hosted Runner 免費併發配額，導致 Runner 分配超時被 GitHub 強制取消（`The job was not acquired by Runner of type hosted even after multiple attempts`），產生看似前端測試掛掉的假陽性報警。教訓：CI 工作流必須嚴格配置 `paths-ignore` 排除純文檔與設定檔，並在頂層配置 `concurrency: cancel-in-progress: true`，杜絕佇列堆疊與算力浪費。

### 7. 文件審核、UI 狀態與國際化踩坑
- **依據手冊修詞卻未查證功能存在的盲目覆寫陷阱 (`Blind Rephrasing without Implementation Verification`)**: 在最佳化使用者使用手冊或介面文字時，直接根據既有文案進行文字美化或擴寫，卻未同步審查核心程式碼與元件功能清單（例如文案描述了「智能克隆前一天資料到新天數」、「手動發送測試推播」，實際上系統根本未實作該 API/按鈕），導致手冊給出空頭支票誤導使用者。教訓：任何文案修正必須以真實程式碼實作作為單一事實來源（Single Source of Truth），無對應實作者應果斷自手冊中剔除或先行實作。
- **國旗圖示盲目直連外部 CDN 導致 404 報錯陷阱 (`Flag CDN 404 Direct Dependency Trap`)**: 採用靜態 CDN 圖片作為法幣對應國旗時，因 ISO 4217 代碼（如 EUR 歐元、XAU 黃金）無法直接 1:1 對應 ISO 3166-1 國旗代碼，造成大量 404 資源載入失敗與控制台報警。教訓：法幣選單應以標準 ISO 4217 代碼為主鍵，圖示應支援本地靜態回退或純符號降級，杜絕單點外部網路依賴。

### 8. 聯盟行銷與即時比價踩坑
- **12Go Asia 誤用 Travelpayouts 舊 Program ID 產生 404 斷點 (`12Go Promo Not Found Trap`)**: 將 Travelpayouts 舊版 Program ID 1024 誤作為 `tp.media/r` 的 promo tool ID 呼叫，導致所有交通跳轉拋出 HTTP 404 promo not found。教訓：加盟夥伴跳轉格式必須對齊各平台官方最新深層連結規範，不假設通用短鏈結構，優先使用官方直連帶參。

### 9. 邊緣檢索、Cloudflare 代理與測試隔離踩坑
- **R2 S3 HMAC 憑證混淆陷阱 (`R2 S3 Token Mismatch Trap`)**: 初次為 Cloudflare 設定金鑰時生成了 R2 API Token（包含 Access Key ID, Secret Access Key 與 S3 Endpoint），嘗試用於 Wrangler CLI 與 Cloudflare MCP 拋出認證失敗。根因在於 R2 憑證僅能用於 S3 相容端點，Wrangler CLI 與 REST MCP Server 必須使用 REST API Token。教訓：Cloudflare 生態圈工具鏈身分認證必須明確區分 S3 HMAC 憑證與以 `cfat_` 開頭之 Account REST API Token。
- **DuckDuckGo Tarpit 慢阻斷延遲陷阱 (`DuckDuckGo Tarpit Timeout Trap`)**: 後端 Python 呼叫 Cloudflare Worker 代理時偶發 10 秒 `httpx.ReadTimeout` 報警。根因在於 Worker 內部的 `fetch(DDG Lite)` 未設置超時時間，遭遇 DuckDuckGo 對資料中心 IP 實施的 Tarpit 慢連線阻斷時 hold 住連線。教訓：邊緣代理所有外部發起請求必須強制宣告 `signal: AbortSignal.timeout(1500)`，搭配與 Wikipedia 全文 API 雙通道並行競速，根絕單點連線掛死。
- **未 Mock Tier 2 邊緣檢索導致 CI 假性失敗 (`Unmocked Tier-2 CI False Negative Trap`)**: GitHub Actions CI 在 `test_execute_web_search_fallback_on_ddgs_error` 拋出 AssertionError。根因在於該測試原意為驗證 Tier 3 降級，但在測試案例中漏掉了對 Tier 2（Cloudflare Worker）的 Mock；當 Worker 成功上線後，CI 環境直接連網取回了真實維基百科結果，導致流程直接在 Tier 2 返回而未觸發 Tier 3。教訓：多級 Fallback 管線的單元測試必須對上游所有 Tier 進行完整的獨立 Mock 隔離，防止真實網路呼叫穿透污染測試斷言。
- **Cloudflare MCP 本機 Stdio 參數覆寫與指令缺失陷阱 (`Cloudflare MCP Missing Command & Undefined Account ID Trap`)**: 在 `mcp_config.json` 啟動 `@cloudflare/mcp-server-cloudflare` 時若僅配置套件名稱，啟動時會拋出 `Error: Unknown command: undefined. Expected 'init' or 'run'` 並導致 MCP client EOF 關閉；若僅追加 `run` 指令，套件內部 `dist/index.js` 的 `config.accountId = accountId` 會無條件將已從環境變數載入的 `config.accountId` 覆寫為 `undefined`，進而退回尋找 `~/.wrangler/config/default.toml` 拋出檔案不存在錯誤。教訓：配置本機 `@cloudflare/mcp-server-cloudflare` 時，`args` 必須完整顯式宣告 `["-y", "@cloudflare/mcp-server-cloudflare", "run", "<account_id>"]`，使 API Token 與 Account ID 同步到位，跳過 OAuth 檔案依賴並正常初始化 89 個 Cloudflare API 工具。

### 10. 搜尋詞庫語意、DNS 區域、時間狀態機與靜態掃描踩坑
- **DuckDuckGo 查詢堆疊 `OR` 運算符導致 0 搜尋結果 (`DDG Overloaded OR Query Trap`)**: 後端搜尋在地社群評價時，查詢傳入 `"PTT OR Dcard OR Tabelog 清水寺"`，DDGS 本地搜尋與 DDG Lite 均傳回空陣列。根因在於 DuckDuckGo 語意搜尋將大寫 `OR` 作為布林分組時，對多重複合長句容錯度極低，直接將整串查詢判定為嚴格比對失敗。教訓：詞庫大瘦身，拔除所有 `OR`，精煉為乾淨的主題導向查詢，召回率由 0% 飆升至 100%。
- **寫死 `wt-wt` 區域代碼導致 DDGS DNS 伺服器崩潰 (`wt-wt Region DNS Failure Trap`)**: 呼叫 DDGS 檢索時偶發 `RethinkDNS / DDGS Server Error`。根因在於過去代碼將 `region="wt-wt"` 硬編碼傳入，而 DuckDuckGo API 部分後端節點不識別 `wt-wt`，導致連線被重置或解析失敗。教訓：移除 `wt-wt`，實作 `resolve_destination_regions`：在地軌傳入真實國家代碼（如 `jp-jp`），全球軌傳入 `us-en`，其餘預設傳入 `None` 讓 DDGS 自動選擇最優端點。
- **DDGS Tier 1 逾時過短引發偽逾時跌入備援 (`Premature 2.8s Timeout Trap`)**: 本地開發環境中，DDGS 搜尋偶發跳過 Tier 1 直接進入 Tier 2 或 Tier 4。根因在於 DDGS 擴展至 8 個真實搜尋引擎並發檢索後，底層聚合平均耗時為 3.5s ~ 4.2s。原設定的 2.8s 超時時間過於嚴苛，導致正常連線被誤殺。教訓：將 Tier 1 超時放寬至 5.2s 黃金閥值，既能保證並發結果完整返回，又能杜絕慢請求卡死線程池。
- **短關鍵字時區推斷引發子字串碰撞劫持 (`Short-Keyword Substring Collision Trap`)**: 使用者詢問 "South New York" 的行程時，系統誤將目的地推斷為泰國（曼谷時區 UTC+7）；詢問 "Perth" 亦被誤判為泰國。根因在於 `DESTINATION_TIMEZONE_MAP` 包含 `"th": "Asia/Bangkok"`，使用 `if kw in text` 時，"South" 內部的 "th" 觸發子字串命中。教訓：實作雙態匹配：拉丁單詞強制要求正則單詞邊界 `\b{kw}\b`，CJK 維持字串包含，並將字典按關鍵字長度由長至短降序排序（`SORTED_TIMEZONE_MAP`）。
- **盲目為迎合靜態掃描（CodeQL）而重構核心正則的功能破壞風險 (`Over-zealous Security Refactor Trap`)**: 在面對 CodeQL 提出的 26 項告警時，若貿然對 `sanitize_dangling_tool_calls` 或網域判定進行大刀闊斧的重構，極易引入正則回溯異常或破壞現有 352 項全綠測試。根因在於靜態分析器無法理解旅遊提問的短字數業務上下文，其警報多為理論極限情境。教訓：堅持臨床實證分析，透過真實字串長度與耗時測試（0.000005s）證明無危害性，堅守零功能降級原則。

### 11. 自訂網域、Cloudflare 邊緣防護罩、GFE 路由與 PWA 沙箱踩坑
- **直連 Cloud Run 觸發 Google Front End (GFE) 404 陷阱 (`GFE Host Header Mismatch 404 Trap`)**: 在 Cloudflare 設定 CNAME 直接指向 Cloud Run 網址，瀏覽器請求 `https://tabijiapp.com/api/health` 瞬間返回 Google 原生 404 錯誤頁面，FastAPI 後端無任何存取日誌。根因：Google Cloud Run 的 GFE 多租戶負載均衡器依賴 HTTP `Host` 標頭識別目標服務容器。當請求的 Host 為 `tabijiapp.com` 時，GFE 查無此租戶直接予以退件。教訓：在轉發請求至 Cloud Run 時必須動態覆寫 `Host` 標頭為真實 `*.run.app` 網址。
- **Cloudflare 免費版嘗試使用 Origin Rules 覆寫 Host 遭 $2,000/月 付費牆攔截 (`Cloudflare Origin Rules Enterprise Paywall Trap`)**: 試圖在 Cloudflare 控制台 Rules > Origin Rules 中配置「Host Header Rewrite」規則將標頭改寫為 Cloud Run 網址，系統提示需要 Enterprise 方案才能啟用該欄位。教訓：Cloudflare 將進階標頭覆寫作為企業方案的收費功能，Free 方案應使用極簡 Cloudflare Worker 以邊緣無伺服器代碼解鎖 Host 覆寫。
- **Cloudflare Worker 轉發 GET/HEAD 帶 body 觸發 TypeError 陷阱 (`Worker GET/HEAD Body TypeError Trap`)**: 在邊緣轉發器中若無條件執行 `fetch(backendUrl, { method: request.method, body: request.body })`，當客戶端發起 GET 或 HEAD 請求時，V8 執行緒拋出 `TypeError: Request with GET/HEAD method cannot have body`。教訓：Fetch API 強制規定 GET/HEAD 的 `body` 必須為 `undefined`，轉發時必須嚴格排查請求方法。
- **暴力 308 重定向舊網域導致已安裝 PWA 本地資料歸零陷阱 (`Forced Domain Redirect PWA Storage Wipe Trap`)**: 討論是否在 Vercel 將舊網域 `travel-pwa-five.vercel.app` 設置 308 轉址至新主網域。根因：瀏覽器 Local-First 存儲機制以 Origin 作為唯一隔離邊界。轉址會迫使現有桌面快捷方式載入新域名，導致老使用者的 IndexedDB 與 LocalStorage 離線行程數據被隔離在舊 Origin 之下無法讀取。教訓：不可強制 308 重定向，應保留舊網域作為副存活節點，透過伺服端同源代理維持其全功能運作。
- **Vercel "Proxy Detected" 黃色警報引發的偽性焦慮陷阱 (`Vercel Proxy Detected False Panic Trap`)**: 當 Cloudflare 開啟橘色雲朵（Proxied）後，Vercel 網域管理介面彈出黃色警告標籤 `"Proxy Detected: Some features may not work as expected"`。根因：Vercel 提示無法直接取得終端客戶端原始 IP，但 Vercel 底層已全面支援 `Verified Proxy Lite`，只要 Cloudflare 傳遞標準 `CF-Connecting-IP` 標頭，所有 CDN 快取與 SSR 功能完全正常運作。教訓：確認 Vercel Bot Protection 不設為暴力 Deny，解除偽性焦慮並實測快取命中率與轉址速度。

### 12. 資安審計、agy CLI 與 Windows 子行程編碼踩坑
- **動態 Curl 離線連線拒絕陷阱 (`Offline Live Server Curl Failure Trap`)**: 在最初設計 PoC 時以 `curl -X GET https://.../api/user/123` 作為範例。實地審查時發現本地開發伺服器（Port 8000）處於離線狀態是常態，依賴真實 HTTP 請求會引發 `Connection Refused` 異常阻斷流程；且 Windows PowerShell 下 `curl` 為 `Invoke-WebRequest` 別名，轉義引號極易引發語法錯誤。教訓：PoC 必須全面規格化為基於 `pytest` + `TestClient` 的記憶體內單元測試。
- **Headless 模式工具自動拒絕卡死陷阱 (`Headless Tool-Deny Hang Trap`)**: `agy.exe -p` 在無 `--dangerously-skip-permissions` 時調用工具會被 auto-denied 並輸出診斷訊息；但在 print 模式下若直接放權執行命令又易卡在子行程等待。教訓：由 Python Harness 直接讀取檔案文字並將代碼片段（前 10,000 字元）內嵌於 Prompt 中，要求子代理人純靜態評估，無需調用任何外部工具。
- **Windows CP950 終端解碼崩潰陷阱 (`Windows CP950 Decode Error Trap`)**: 在 Windows 繁體中文環境下使用 `subprocess.run(capture_output=True, text=True)` 接收 `agy` 的輸出時，由於 `agy` 包含 UTF-8 特殊符號（如 Unicode 破折號 `0xe2`），Python 嘗試以預設 `cp950` 解碼導致拋出 `UnicodeDecodeError: 'cp950' codec can't decode byte`。教訓：子進程通訊一律接收原始 bytes，在 Python 端顯式以 `decode('utf-8', errors='replace')` 解碼，並注入 `PYTHONIOENCODING=utf-8` 環境變數。

---

## [Technical Debt]

- **多天總覽 POI Pin 碰撞聚合 (Clustering)**: 當多天行程累積超過 20+ 密集景點時，地圖 Pin 存在重疊遮蔽，待規劃導入 MapLibre 原生向量聚合圓圈或 Zoom Level 動態展延機制。
- **MapLibre 實例與記憶體生命週期監控 (WebGL Context Lifecycle)**: 切換視圖頻繁時需持續監測 WebGL 上下文釋放情況，確保地圖卸載時完整執行 `map.remove()`，杜絕行動端 Safari 報錯 `Too many active WebGL contexts`。
- **離線照片二進位暫存隊列 (Offline Photo Blob Persistence)**: 目前離線隊列對 `FormData`（如現場收據拍照上傳）採取跳過並彈出 Toast 提示的保守策略。未來需支援將照片轉為 IndexedDB Blob 本機排程隊列，待連網時自動重播二進位上傳。
- **氣象 API 伺服器端邊緣快取 (Open-Meteo Edge Cache)**: 目前客戶端直連 Open-Meteo。未來使用者量增長時，應在 FastAPI 後端透過 Redis 實作城市級反向代理快取，減少對第三方服務的依賴。
- **Dependabot #83 安全依賴修復**: Default branch 存在 1 個 Moderate severity 安全漏洞（Dependabot #83），需排程安全升級。
- **Radix DialogContent a11y 補充**: 部分彈窗缺少 `aria-describedby` 或 `Description` 產生 Accessibility Warning，需補齊 `<DialogDescription>`。
- **FastAPI ORJSONResponse 遷移評估**: FastAPI 新版本提出 `FastAPIDeprecationWarning: ORJSONResponse is deprecated`，後續可評估直接交由 Pydantic response_model 序列化。
- **BackgroundSync iOS Safari 降級機制強化**: iOS Safari 原生不支援 W3C Background Sync API，目前依賴 Service Worker 被動重啟。後續可評估在 `SyncManager` 前端組件中監聽 `window.addEventListener('online')` 作為主動觸發保險。
- **離線記帳本機暫存與背景重播隊列 (Offline Mutation Queue)**: 目前記帳頁面新增支出若處於斷網狀態，尚未整合 IndexedDB Background Sync 隊列自動重播。
- **活動多連結陣列化擴充 (Activity Dynamic Links Array)**: 行程活動項目目前支援單一外部連結，手冊中已標註預留多連結與訂位憑證結構，未來可將 `activity.link` 擴展為 link 物件陣列。
- **地圖控制膠囊插槽擴充性 (MapControlCapsule Action Slot Extensibility)**: 未來若地圖需引進即時路況或等高線圖層，可在 MapControlCapsule 設計 children 插槽或動態 items 配置，保持控制膠囊可插拔彈性。
- **前端搜尋 L1 RAM 快取容量上限與 LRU 驅逐 (Search L1 Cache Bound & Eviction)**: `frontend/lib/search-cache.ts` 目前未設 `MAX_L1_ITEMS` 上限，長期會話存在微量記憶體洩漏風險，後續可規劃導入 LRU 淘汰機制。
- **Cloudflare Worker 代理 Secret 金鑰強制校驗 (Cloudflare Worker Key Enforcement)**: 目前 Worker 的 `x-tabidachi-key` 為非強制校驗。未來若流量增長或面臨濫用風險，可於 Worker 環境變數配置 Secret 並於後端 Cloud Run 同步注入。
- **CodeQL 靜態告警漸進式收斂 (CodeQL Gradual Convergence)**: 後續可在不破壞既有架構前提下，為 `poi_service.py` 加上類型別名或獨立驗證器顯式告知靜態分析器 `api_url` 屬安全常數，並對 URL 判斷改採標準 `urllib.parse` 解析主機名，逐步消除靜態分析噪音。
- **Supabase 身份驗證回調網址更新（待帳號體系啟動時排程）**: 目前 Tabidachi 全面採用訪客匿名認證（`user_uuid` 本地儲存於 IndexedDB），無需 OAuth 流程。後續若開發第三方社群帳號登入功能，需將 `https://www.tabijiapp.com/auth/callback` 加入 Supabase Redirect URLs 白名單。
- **真實世界時空感知與公休核實能力 (Real-World Spatiotemporal & Opening Hours Verification)**: 目前 AI 行程生成為單向結構化 JSON 直出，缺乏公休日閉館與跨區瞬移的感知能力。未來已規劃導入「後置非同步行程體檢器 (Real-World Itinerary Inspector Pipeline)」，以純數學 Haversine 計算位移時間，並結合 OSM opening_hours 輕量探針，在 UI 呈現警示膠囊與替代方案，兼顧 0ms 體感延遲與 100% 真實世界感知。

---

## [Vocabulary]

### 1. 圖形與地圖領域
- **Declarative Layer Precedence**: 宣告式圖層順序優先，利用 JSX 物理順序定義 MapLibre 圖層層次而非無效跨層 beforeId。
- **MapLibre CSP Worker Pipeline**: MapLibre 內容安全策略 Worker 建置管線，將 Web Worker 同源靜態化之架構方案。
- **Hardware Composite Decoupling**: 雙向硬體合成層解耦，透過 GPU 合成層隔離浮動節點拖曳與底層 WebGL 重繪。
- **Container-Anchored Sheet Decoupling**: 容器錨定抽屜解耦，將抽屜限制於地圖容器內部避免竄出覆蓋全站 Header。
- **Great-Circle Slerp Interpolation**: 大圓航線球面線性插值，在 2D/3D 平面上以球面幾何學平滑渲染長途跨城軌跡。
- **Coupled Dependency Atomic Lock**: 雙套件依賴強耦合原子升級鎖，將具有深層內部 API 依賴的跨函式庫綁定為單一原子升級單元。
- **Local Native Probing Gate**: 本地真機活體驗收守門，要求涉及圖形渲染與原生 Web API 的重大變更必須通過本機瀏覽器實地驗收。
- **MapControlCapsule Idle Dimming**: 地圖控制膠囊呼吸降敏，無手勢操作時 3 秒自動平滑降至 25% 晶透幽靈態，觸碰/拖曳瞬間點亮。
- **Discrete Camera Lifecycle Scheduling**: 離散相機生命週期排程，使用 `onMoveStart`/`onMoveEnd` 取代 60fps `onMove` 狀態綁定，徹底消除地圖拖曳掉幀。
- **Pointer-Type Touch-Safe Hover**: 指針型態觸控安全懸停防禦，透過 `e.pointerType === "mouse"` 根除行動端 Sticky Hover 黏滯。
- **Radix Portal Container Escape**: Radix Portal 容器逃逸，將彈窗掛載至 document.body 杜絕地圖容器 overflow:hidden 裁切。

### 2. 狀態持久化與自癒領域
- **Double-Checked Silent Self-Healing**: 雙重核驗完全靜默自癒，結合 SWR 404 立即熔斷與清單二度核驗，達成 <300ms 無感導正與零誤判防禦。
- **Zero-Retry 404 Guard**: SWR 404 立即熔斷守衛，遇到客戶端資源不存在時重試次數強制歸零，杜絕伺服器冷啟動風暴。
- **Dual-Storage Coherence**: 雙重持久化存儲一致性，跨 Zustand 與 localStorage 雙清以防幽靈 ID 還原。
- **Typed HttpError Propagation**: 型別化 HTTP 錯誤傳遞，強制底層 Fetcher 檢驗 !r.ok 並向外拋出狀態碼。
- **Filter Penetration on Deep Link**: 深度連結篩選器穿透機制，在尋址前自動重置 UI 篩選器以避免目標被遮蔽。
- **Day-Zero Overview Precedence**: 零天總覽優先順序，外部深度連結指定天數優先於預設第 1 天的狀態調度原則。
- **Ephemeral Target Parameter Cleanup**: 暫時性目標參數脫敏，消費完成後立即自 URL 抹除參數以達冪等性。
- **Decoupled Global Write**: 請求生命週期全域解耦寫入，將外部 API 請求由組件局部 state 升級為全域 Store 寫入，避免組件卸載誤殺回傳資料。
- **In-Flight Request Deduplication**: 飛航中請求池去重，以座標/參數為 Key 快取進行中的 Promise，避免多卡片並發重複發送相同請求。
- **Local Timezone Date Safety**: 本地時區安全日期，採用 `toLocaleDateString('en-CA')` 杜絕 UTC 跨日時區漂移。
- **Hard-Timeout Skeleton Fallback**: 骨架屏硬逾時優雅降級，定時終止 pulse 動效並展示友善重試介面。

### 3. iOS 原生體驗與 UI 元件領域
- **Text-Node Isolation Architecture**: 文本節點隔離架構，Flex 容器內將文字單獨封裝於子 span 避免 WebKit 匿名文字區塊破壞同級排版。
- **Tap-to-Focus, Tap-again-to-Drilldown**: iOS 鑽取心智模型，首次點擊聚焦軌跡，再次點擊深入平滑滾動至詳情卡片。
- **Decoupled Button DOM Architecture**: 解耦按鈕 DOM 架構，避免按鈕巢狀包覆造成 HTML5 規格衝突。
- **Zero-Remount View Animation Architecture**: 無狀態銷毀的視圖動畫架構，靜態標識搭配 animate 屬性驅動位移，確保 0 重複 API 請求與生命週期穩定。
- **Direction-Aware Spring Transition**: 方向感知彈簧滑入轉場，依據 Tab 索引動態計算方向並驅動 iOS 原生彈簧滑入動畫。
- **Continuous Multi-Month Calendar**: iOS Swift 風格連續縱向多月份滾動日曆區間選擇器。
- **IME Composition Guard**: 輸入法組合態守衛，在 onKeyDown 檢查 isComposing 防止 CJK 選字誤觸送出。

### 4. 離線架構與 PWA 領域
- **Shoulder-of-Giants Offline Architecture**: 站在既有巨人肩膀上的輕量化離線架構，立足既有 Serwist、idb-keyval 與 SWR 快取規範，達成零冗餘體積的離線優先秒開。
- **Arterial/Venous Read-Write Decoupling**: 動脈與靜脈讀寫分流架構，將 GET 離線讀取與 POST/PUT/PATCH/DELETE 突變寫入在 Service Worker 層物理分離。
- **Ignore-Search Navigation Pipeline**: 忽略查詢參數的離線導航管線，透過 `matchOptions: { ignoreSearch: true }` 保障帶參啟動 PWA 100% 命中 App Shell。
- **Offline Trip Non-Destructive Invariance**: 離線行程不可抹除性，在網路中斷或 API 報錯時守護本地行程資料與選定狀態。
- **Smart Tab Focus & Push Navigation**: 智慧分頁聚焦與無刷新推播導航，喚醒既有 Client 並透過 postMessage 內部事件平滑切換視圖。
- **Hydration-Safe App Shell Fallback**: 水合安全 App Shell 導航降級，導航快取精確排除 _rsc 與 /api/ 以維護 React 19 RSC 水合安全。

### 5. 後端高併發與健康探針領域
- **Zero-Blocking Health Probe**: 零阻塞健康探針，僅依據伺服器內存狀態秒回 200 OK，杜絕外部依賴污染。
- **Isolated Keep-Alive Task**: 隔離保活任務，在 Lifespan 背景獨立循環運行的資料庫保活定時器。
- **Timezone-Aware Atomicity**: 時區原子一致性，全域時間運算統一強制帶有時區標籤以防 TypeError。
- **Inline Coordinates with Dynamic Fallback**: AI 直出座標伴隨動態補漏，兼顧極速生成與邊緣景點高可用性的坐標解析架構。
- **Mother Region Inheritance**: 母體區域繼承，以行程整體目的地中心點作為所有子景點 Proximity Bias 錨點的空間收斂架構。
- **Atomic Date Range Shift**: 原子日期平移，出發日與結束日平移時同步將所有子項目天數逆序/正序移動並保障截斷資料。

### 6. CI/CD 與工程化守門領域
- **Fail-Fast PowerShell Execution Harness**: 確定性熔斷 PowerShell 執行架構，透過 `$LASTEXITCODE` 即刻中止失敗連鎖。
- **Dual-Mode AST/Regex Audit Pipeline**: 雙模 AST/正則審核管線，結合語法樹與模式約束消除誤報。
- **Tri-Layer Verification Protocol**: 三重活體驗收協議，結合靜態安全、單元邏輯與真實生產打包的三重驗收標準。
- **In-Place Override Merging**: 原地覆蓋合併，在既有 package.json overrides 區塊增量注入而不破壞既有補丁。
- **Infra-as-Code Authority**: 基礎設施程式碼權威，雲端執行時配置以 CI/CD Workflow 定義為唯一真實來源。
- **AI Recombination**: 大腦記憶壓縮重組模式，使新舊日誌無縫融合並保留歷史脈絡與技術債。
- **Decoupled Git Identity**: 去中心化 Git 身分解耦架構，正視 Git Commit 僅傳遞純文字 Name/Email，而無 GitHub ID 概念之底層特性。
- **ID-Pinned Noreply Standard**: 官方 ID 錨定隱私信箱標準，以 `ID+username@users.noreply.github.com` 同時達成個資隱蔽與身分防偽。
- **Hermetic Bundle Backup**: 封閉獨立打包備份，利用 Git Bundle 獨立封裝全量 DAG 規避歷史重構時的全域 Ref 污染。
- **Fetch-Before-Lease**: 租約前置同步原則，在 force-with-lease 前強制獲取遠端追蹤指針避免租約斷裂。
- **Turbopack 雙實例衝突與編譯 Worker 熔斷守則 (Turbopack Multi-Instance Port Collision & Worker Proliferation)**: 開發模式下若重複執行 `npm run dev`，新實例會調度多執行緒 Turbopack Rust/Node 編譯集群狂暴掃描全站 AST 與依賴，與既有進程在 Port 3000 發生競態搶佔，衍生高達 8~10 個 `node.exe` 子處理程序並發引發 CPU 瞬間暴衝 50%+。規範：嚴格維持單一 Dev Server 進程；重啟前必須執行進程樹清查（如 `taskkill /F /IM node.exe /T` 或檢測 `Get-NetTCPConnection`），杜絕幽靈 Worker 殘留。

### 7. 文件真實性與介面工程領域
- **Documentation Reality Alignment**: 手冊與實作真實對齊原則，手冊所有操作流程與功能描述必須具備真實可運行的前端 DOM 或後端 API 支撐，禁止幽靈功能預先宣傳。
- **Dynamic Spatial Evacuation**: 動態空間避讓機制，3D 運鏡巡航時頂部 GPS/視角面板自動平滑淡出（`opacity-0 pointer-events-none`），最大化觀景視野且巡航終止時無縫復原。
- **Strict ISO 4217 Fiat Standard**: 嚴格 ISO 4217 法幣規範，記帳貨幣嚴格收斂至法定貨幣與標準三位代碼，防止非標貨幣符號破壞匯率換算精確度。

### 8. 聯盟行銷與即時比價領域
- **Official Direct Affiliate Parameterization**: 官方直連加盟帶參規範。切斷無效的第三方轉址代理（如 `tp.media/r?p=1024` 引發 404 promo not found），採用 12Go 官方標準帶參格式 `https://12go.asia/en/travel/.../?marker=${marker}`，確保 HTTP 301/200 正常重定向與分潤 Cookie 寫入。
- **Same-City Flight Zero-Delay Short-Circuit**: 同城起降零延遲短路防衛。前端 SWR hook 與後端 API 同步攔截出發地與目的地相同（`cleanOrigin === cleanDest`）之無效航班查詢，以 0ms 記憶體短路回傳免搭機狀態，消除外部 API 無效調用、超時與 502 Bad Gateway 異常。

### 9. 邊緣檢索與 Grounding 領域
- **Edge Multi-Engine Search Runner**: 邊緣多引擎檢索執行器，由 Cloudflare Anycast 邊緣節點聚合檢索並回傳乾淨 JSON，後端以輕量 HTTP 呼叫，徹底免疫雲端資料中心 IP 被 DuckDuckGo 封鎖的致命缺陷。
- **Parallel Dual-Channel Search with Strict Abort**: 嚴格超時雙通道競速檢索，以 `Promise.all` 同時調用維基百科全文 API 與 DDG Lite，並對 DDG Lite 施加 1.5s 快速中斷，根除 DuckDuckGo Tarpit 慢連線陷阱。
- **Wikipedia Full-Text Query Alignment**: 維基百科全文查詢對齊，改採 `action=query&list=search` 全文語意檢索取代前綴比對的 OpenSearch，達成複合詞條（如「京都清水寺」）100% 條目命中。
- **Dangling Tool Calls Auto-Synthesis**: 懸空工具調用對稱合成，建構對話歷史時若偵測到模型前一輪呼叫了 tool 但使用者未回傳 response，自動合成對稱的虛擬 `functionResponse`，徹底根治 Gemini 400 Bad Request 狀態機崩潰。
- **Strict 1-to-1 Citation Pruning**: 嚴格 1對1 引文剪裁對齊，正則萃取內文實際引用的標籤並對齊來源，物理剔除未引用的多餘來源，杜絕引用標籤與內文脫節。
- **Cloudflare Stdio Parameter Invariance**: Cloudflare Stdio 參數不變性，以 `run <account_id>` 完整傳遞 MCP 啟動參數，阻斷套件內部覆寫未定義變數與 OAuth 缺失造成的崩潰。

### 10. 全球詞庫、時間感知狀態機與實證安全領域
- **Dynamic Dual-Track Region Resolution**: 動態雙軌區域代碼分流，在地軌按目的地動態映射本地 Region（如 jp-jp），全球軌鎖定 us-en 搜尋 Reddit 國際評價。
- **Boundary-Aware Longest-Match Timezone Inference**: 邊界感知最長匹配時區推斷，區分拉丁字母（\b 邊界正則）與 CJK 字符，並依關鍵字長度由長至短排序匹配，杜絕短關鍵字子字串劫持。
- **Real-Time Temporal Awareness & Lifecycle State Machine**: 即時端側時間感知與行程生命週期狀態機，解析客戶端時區與時間，動態將行程劃分為 PLANNING、PRE_TRIP、IN_TRIP_ACTIVE 與 POST_TRIP 並注入即時營業與氣候語境。
- **Server-Side vs Client-Side Tool Decoupling**: 伺服端與客戶端工具分離防禦，伺服端工具（get_world_time）由後端攔截即時執行並回填模型，業務工具（add_expense）透過 SSE 傳遞給前端觸發 UI。
- **Pragmatic Empirical Security Audit**: 實證導向安全稽核，以實際攻擊向量驗證與臨床度量取代盲目消除靜態分析噪音，捍衛系統零功能降級。

### 11. 頂級網域、邊緣防護罩與路由架構領域
- **Same-Origin Edge Shield**: 同源邊緣防護罩，客戶端以相對路徑發送同源 API 請求，由 Cloudflare Anycast 邊緣節點 Worker 辨識並動態代理至真實後端，阻斷後端服務網址洩漏。
- **GFE Host Dynamic Rewrite**: GFE 虛擬主機名稱動態覆寫，在邊緣節點將 HTTP Host 標頭改寫為 Google Front End 識別之合法容器名牌，徹底解決第三方網域 404 退件問題。
- **Verified Proxy Lite**: Vercel 驗證代理精簡模式，原生相容 Cloudflare 橘色雲朵代理，透傳 CF-Connecting-IP 並維持邊緣快取與 SSR 運作。
- **Origin Storage Sandbox Partition**: 瀏覽器存儲同源沙箱隔離，IndexedDB 與 Cache Storage 嚴格以 Origin 為邊界，網域變更時維持雙軌共存以捍衛使用者離線資料。

### 12. 資安審計與子代理人調度領域
- **Physical Zero-Contamination Validation**: 物理級純淨上下文對抗證偽，利用獨立作業系統進程執行 Validator 子代理人，達成零 Prompt 歷史污染。
- **Unbounded Parallelism Harness**: 無界並行 Harness，透過 Python asyncio 同步調度多個背景子代理人同時對多端點進行證偽。
- **Tri-State Verdict & Zero False-Negative Guarantee**: 三態判定與零假陰性防線，強制將解析失敗或逾時標記為 INCONCLUSIVE 杜絕靜默漏報。
- **In-Memory Mock PoC Standard**: 離線記憶體中單元 PoC 規範，全面採用 pytest + TestClient 模擬請求，零外部伺服器依賴。
- **RFC Diff & Exact Block Replacement Protocol**: RFC 標準 Diff 與精確區塊替換雙重補丁規範，成對提供以免疫 Windows CRLF 行尾字元破損。

### 13. 邊緣串流保活與次世代並行地理編碼領域
- **10s SSE Heartbeat & Cross-Chunk Accumulator**: 邊緣 100 秒逾時 SSE 保活與跨 Chunk 累加器，每 10 秒發送 Ping 保活重置 Cloudflare 計時器，並在 EOF 刷新尾端封包。
- **Multi-Factor Top-K Fusion & Rational Distance Decay**: 地理編碼多維融合 Top-K 重排與有理空間衰減架構，以 $1 / (1 + \text{dist} / 150)$ 取代高斯斷崖，50% 文本 + 30% 空間 + 10% 權威度補償 + 10% 目標國加成。
- **Viewport Bounding Box & Antimeridian Boundary Guard**: 視窗邊界限制與換日線拓撲防禦，前端地圖動態提取 BBOX，後端嚴格校驗四坐標範圍與經緯度單調性，防範 Photon HTTP 400。
- **CJK Character-Spaced Tokenization & Graceful Fallback**: CJK 字符空格化分詞與跨國過濾優雅降級標準，解決漢字緊密分詞塌縮，且過濾為空時退回原始清單保護出發地機場。
- **Windows CP950 Unicode-Safe Logging**: Windows CP950 控制台安全日誌防衛，頂層包裝 stdout UTF-8 並以安全日誌函式防禦 Emoji 編碼崩潰。

### 14. 路線計算引擎、連線池與 3D 地形領域 (OSRM Routing Engine, Connection Pooling & 3D Terrain)
- **OSRM 3-Tier Resilient Routing Architecture**: 徹底除役不穩定且依賴 Token 的 ArcGIS Routing，全面以 OSRM (FOSSGIS) 作為預設路網引擎。架構實作三層防禦體系：Layer 1 記憶體 LRU 快取（500 筆、TTL 10m，重複縮放/拖曳 1.6ms 直出，恪守 1 req/s 公共規範）➔ Layer 2 HTTPX 全域連線池單例（Keep-Alive、max 50 連線，steps=false 減輕 70% 體積）➔ Layer 3 Haversine 大圓直線保底（遇離島無路網或逾時回傳 source: straight-line，前端降級為灰色虛線，杜絕 500 報錯與地圖崩潰）。
- **Edge POST-to-GET Virtual Cache Adapter**: 邊緣 POST-to-GET 虛擬快取適配架構。在 Cloudflare Worker 邊緣層攔截 `/api/geocode/search` POST 請求，將 BBOX 空間量化（小數點後兩位）並動態構造專屬虛擬 GET URL 作為 Cache Key，成功突破 Cloudflare Cache API 僅支援 GET 的限制，實現熱門搜尋 0ms Anycast 邊緣直出，有效保護後端算力。
- **Mapterhorn Terrarium 3D DEM & Dynamic Pitch Throttling**: Mapterhorn 開源全域 3D 地形高程與動態傾角運鏡防衛。地圖載入 DEM 圖資時必須顯式宣告 `encoding: 'terrarium'`，杜絕 MapLibre 預設 Mapbox RGB 算法造成高程膨脹 100 倍的致命白屏與形變；同時實作動態傾角監聽（pitch $\ge 30^\circ$ 自動啟用 1.2 倍真實地形、$\le 15^\circ$ 自動卸載歸零），兼具壯闊地貌與 60 FPS 絲滑體驗。

### 15. iOS 原生美學、五維量規 AI 審核與集合安全領域 (iOS Ergonomics, 5D Rubric & Collection Safety)
- **Apple HIG Weather Bento & OKLCH Spectrum Architecture**: Apple HIG 雙態天氣面板與色溫光譜架構。氣象面板採「預設緊湊 Hero 氣溫 + 24h Scrubber，點擊展開 2x2 Bento 矩陣」雙態設計；色溫條導入 OKLCH 分段線性插值（-20°C 極寒深藍至 40°C 酷暑鮮紅），兼顧無障礙高對比與平滑漸變；嚴格守衛溫差分母 `Math.max(1, maxTemp - minTemp)` 杜絕陰雨天除以零產生 NaN；並保留 Audit 5.0 特殊地點智慧提示（市場、展望台/晴空塔、高海拔 >1000m、WBGT > 28 熱中症預警）、經緯度微標籤與 ECMWF/AQI 5 階彩色徽章。
- **Itinerary Dashboard Hub & Modal Bottom Sheet Decoupling**: 每日長表單抽屜化收納原則。時間軸上方超過 1500px 的超長表單（AI 審核、花費、票券、行前清單）全面由平鋪收斂為「4 合 1 微型卡片（ItineraryDashboardHub）+ 物理彈簧底抽（IOSBottomSheet）」，顯著釋放行動端行程時間軸可視空間；底抽內建 Framer Motion 雙階檔位吸附（Half 60vh / Full 90vh）、甩動自動關閉與 Segmented Control 分頁列；並實作 Zero-Leak Body Scroll Lock，彈窗開啟時精確備份並鎖定 `document.body` 的 `overflow` 與 `touchAction`，關閉或組件卸載時百分之百還原，根除背景滾動穿透與死鎖。
- **5-Dimension Rubric Scoring & Multi-Fence Tolerance Fallback**: AI 行程審核五維量規與多圍欄容錯解析。後端 Prompt 導入 Reason-First 先論後評機制，確立「時間節奏 (Pacing)、動線順暢 (Route)、停留合理 (Duration)、體力負荷 (Fatigue)、時段契合 (Timing)」五大維度（各 0~20 分，基準起評 80 分，總分 100 分），並輸出獨立機器可讀代碼塊；前端實作三階防禦解析（結構化圍欄 ➔ 嚴格非時間字眼正則 ➔ 五維加總保底），徹底根治「20 分鐘」誤抓為 20 分與「AI 即時分析後仍顯示無分析/無分數」之重大缺陷。
- **Array Invariant Guard Before Spreading**: 集合展開前置陣列安全防衛。任何對外部傳入、LocalStorage 或快取物件進行展開運算（Spread `[...items]`）之前，必須以 `Array.isArray()` 前置確認型別（例如 `Array.isArray(raw0) ? raw0 : []`），若為非陣列物件或畸形結構強制降級為空陣列 `[]`，徹底杜絕因快取損毀或型別不符引發致命 `TypeError: d0 is not iterable` 導致整個前端頁面崩潰白屏。

### 16. CI/CD 雲端排程、路徑過濾與併發取消領域 (CI Runner Starvation & Concurrency Cancellation)
- **Doc-Commit Paths-Ignore & Concurrency Cancellation**: 文檔路徑過濾與並發取消架構。為 GitHub Actions CI 配置 `paths-ignore`（排除 `docs/**`、`.agents/**`、`README.md`、`CONTEXT.md`、`.gitignore`、`LICENSE`），阻斷純文本更新對繁重測試矩陣的無效調用；頂層啟用 `concurrency: { group: "${{ github.workflow }}-${{ github.ref }}", cancel-in-progress: true }`，新提交自動取消過時的舊任務排隊，徹底根治尖峰時段雲端 Runner 枯竭超時問題。