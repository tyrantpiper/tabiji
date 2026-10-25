# 領域知識庫：iOS 原生體驗、微動效與 UI 元件 (ios_ui)

> **所屬領域**: Tailwind CSS v4, Radix UI Primitives, Framer Motion, WebKit 防衛, 手勢互動

## 🏛️ 架構決策 (Decisions)
- **Mobile Viewport Mini-Bar Auto-Dock**: On mobile screens (< 768px), floating chat dialogs must support docking into a <= 60px mini-bar to preserve underlying map interaction without losing conversation state.

- **5000ms Dismiss Cooldown for Reauth Modal**: When user clicks 'Dismiss (Stay Offline)' in SessionReauthModal, dismissReauthPrompt must set a 5000ms cooldown timestamp to prevent rapid background SWR requests from reopening the modal immediately.

- **UX 機能融合與雙軌自癒備援法則 (AD-151)**: 極簡行動端 UI 應避免突兀的孤立重整控制項。在即時長連線（增量廣播）與快照拉取（全量權威）的雙軌架構中，手動重整應無痕依附於使用者既有高頻操作（如點擊通知鈴鐺、下拉手勢），兼顧介面極致留白美感與 100% 狀態自癒備援。

- **UX 機能融合與雙軌自癒備援法則 (INV-UI-024 / Dual-Purpose UI)**: 極簡行動端 UI 應避免突兀的孤立重整控制項。在即時長連線（增量廣播）與快照拉取（全量權威）的雙軌架構中，手動重整應無痕依附於使用者既有高頻操作（如點擊通知鈴鐺、下拉手勢），兼顧介面極致留白美感與 100% 狀態自癒備援。

- **POI 抽屜 2×3 微膠囊雙排矩陣與極限寬度防護法則 (Two-Row Grid Matrix & Viewport Clamping Invariance)**: 底抽二級快捷操作列採用 2 排 × 3 列網格矩陣 (grid grid-cols-3 gap-1.5 sm:gap-2) 常駐 6 顆微卡片；圖示規格統一為 20px (w-5 h-5)，文字標籤嚴格使用精簡雙字短詞 (繁中雙字 / 英文 <=6 字母)；容器與卡片全面配置 min-w-0 與 truncate，並宣告 touch-manipulation 與 onPointerDown stopPropagation，保證 iPhone SE 320px 螢幕下字串零截斷且手勢互不干擾。

- **抽屜一體化毛玻璃純圖示藥丸島法則 (Segmented Frosted Glass Icon Capsule Invariance)**: 抽屜第一屏快捷工具列必須採用單一毛玻璃圓角膠囊底座 (rounded-2xl max-w-sm mx-auto h-12 backdrop-blur-md)，內部按鈕採用純圖示一字排開零滾動，嚴禁在固定窄卡片內堆疊文字導致 truncate 截斷；每個純圖示按鈕必須配備 localized title 與 aria-label，容器宣告 touch-manipulation 防止 WebKit 300ms 點擊延遲。

- **動態圖標工具列等寬流體拓撲架構 (Fluid Auto-Cols-Fr Grid & Icon Stack Architecture)**: 底抽次要功能工具列必須採用 grid grid-flow-col auto-cols-fr gap-2 w-full 與縱向 Icon 微堆疊排列，子項一律約束 min-w-0 truncate，徹底消滅橫向撐破容器寬度之物理缺陷。

- **底抽滾動容器四重軸向硬鎖定法則 (Fourfold Axis-Lock & Touch-Pan-Y Invariance)**: 底抽內部所有可滾動容器必須顯式宣告 overflow-y-auto overflow-x-hidden touch-pan-y overscroll-x-none overscroll-y-contain 並掛載 style={{ touchAction: 'pan-y' }}，徹底在瀏覽器底層阻斷斜向滑動引發之水平晃動。

- **底抽 Flexbox 現代流體佈局法則 (Flexbox Fluid Bottom Sheet Layout)**: 底抽主面板設置固定或百分比高度時，內部滾動內容區嚴禁使用寫死的 max-h-60 等高度計算，必須統一宣告為 flex-1 min-h-0 overflow-y-auto，將高度動態排版主權歸還給外層 Flex 容器，徹底根除雙重滾動條缺陷。

- **iOS 底抽三檔位與階梯式遮罩穿透法則 (Stepped Backdrop & 3-Stage Detent Invariance)**: 地圖內部景點底抽必須支援 peek (~110px)、half (~56%)、full (~92%) 三檔位。在 peek 狀態下必須完全阻斷背景遮罩掛載，保障地圖 100% 穿透可操作；half 狀態採 20% 輕量遮罩；full 狀態採 50% 高斯模糊遮罩。

- **WebKit 匿名文字節點隔離 (Text-Node Isolation Architecture)**: Flex 容器中裸露文字搭配 truncate 會在 WebKit 下產生匿名文字方塊壓縮同級標籤。動態文本必須封裝於獨立 <span className="truncate">。
- **iOS 原生雙擊鑽取心智模型 (Tap-to-Focus, Tap-again-to-Drilldown)**: 窄屏地圖頂部初次點擊聚焦軌跡，再次點擊觸發平滑滾動直達卡片。
- **解耦按鈕 DOM 架構**: HTML5 嚴禁 <button> 嵌套 <button>。卡片點擊與操作列按鈕在 DOM 層級解耦為同級 Sibling 節點。
- **無狀態銷毀的視圖動畫架構 (Zero-Remount Architecture)**: motion.div 採靜態標識搭配屬性位移，主頁面常駐不銷毀，達成 0 重複請求與 100% 滾動記憶。
- **iOS 全域雙向滑動轉場與觸控防衛**: app-shell.tsx 導入方向感知索引與彈簧滑入 (x: ±28px)；全域注入 select-none，底部導航搭配 haptic.selection()。
- **純函數空間索引拓撲與零漂移視差法則 (Tab Spatial Index Topology & Parallax Invariance)**: 分頁滑動轉場嚴禁依賴組件歷史內部狀態。必須透過 TAB_INDICES 純量索引映射與 calculateTabOffset 純函數比對；當任一分頁非登記分頁或啟用 reduced-motion 時位移恆定歸 0，保證 100% 空間物理確定性且無方向漂移。app-shell 調用端以封閉枚舉字面量呼叫，外部深層連結以 instant 意圖早退歸零。
- **合成點擊與拖曳手勢競態防衛**: hasMovedRef 追蹤位移並在 handleDragEnd 設置 80ms 延遲釋放閥，徹底杜絕拖曳放開手指誤開面板。
- **輸入法組合態攔截 (IME Composition Guard)**: 中日文選字時在 onKeyDown 嚴格掛載 if (e.nativeEvent.isComposing) return，防止提前發送。
- **導覽列原生 CSS 暗黑適配優先**: 核心控制項背景邊框以 Tailwind dark: 類別接管，杜絕 Hydration 前色彩跳動。
- **Touch-Safe 指針偽類隔離**: 按鈕 Hover 邏輯以 e.pointerType === 'mouse' 隔離，防止觸控螢幕偽類黏滯。
- **跨層彈窗 Radix Portal 物理隔離**: 巢狀容器喚醒彈窗必須透過 Radix Dialog Portal 掛載至 document.body，防 overflow 裁切。
- **Zero-FOUC 前置同步腳本**: head 注入微型同步腳本，首幀直接設定 :root { --font-scale: ... }，阻斷字體放大閃爍。
- **Framer Motion 一次性動畫遞增 key 重播**: 鈴鐺動畫以 key={ringCount} 重播，取代布林狀態重設，消除快速連點卡死。

## 🛡️ 踩坑記錄 (Failed Paths)
- **FP-047 (Hook TDZ 順序)**: useEffect 依賴陣列在 render 當下求值，effect 必須放在它引用的所有 useState 宣告之後，否則 ReferenceError 白屏。
- **FP-049 (布林動畫卡住)**: 550ms 內快速開關開時，布林值仍為 true 導致重設無效。改用遞增序號 key={ringCount}。
- **FP-055 (React 19 連鎖渲染)**: CustomCategoryModal 內若使用 useEffect 監聽 isOpen 重設觸發 react-hooks/set-state-in-effect。改由父層 key={id || 'closed'} 自動重置。
- **FP-056 (Tailwind v4 工具類別)**: stroke-[3] 任意值被 Linter 告警，改用標準語意 stroke-3。
