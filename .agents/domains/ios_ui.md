# 領域知識庫：iOS 原生體驗、微動效與 UI 元件 (ios_ui)

> **所屬領域**: Tailwind CSS v4, Radix UI Primitives, Framer Motion, WebKit 防衛, 手勢互動

## 🏛️ 架構決策 (Decisions)
- **長地名自動換行與跨元件 0px 水平溢位四層防線契約 (AD-247)**: dialog.tsx DialogContent 必宣告 grid-cols-1 阻斷隱式 auto 軌道膨脹；scroll-area.tsx Viewport 必宣告 overflow-x-hidden [&>div]:!block [&>div]:!min-w-0 破除 Radix display: table 水平撐寬。所有地點搜尋結果與行程卡片 (ActivityEditModal, LocationEditDialog, POISearch, TimelineCard, TimelineCardOverlay, InfoView, DayMap, FullscreenMapModal, POIDetailDrawer 展開態) 滾動容器必套用四重軸鎖，button 必加 min-w-0 max-w-full overflow-hidden，地名與地址撤除 truncate 改用 min-w-0 flex-1 wrap-break-word [word-break:break-word] whitespace-normal，包裹長文字之 <Button> 必覆寫 whitespace-normal；ActivityEditModal 清理鎖定 [isOpen, editItem?.id]、LocationEditDialog 鎖定 [isOpen, day]，並以 extractCleanPlaceQuery 保留括號備註至空白 desc。

- **前端零依賴分級壓縮、iOS 16.7MP 防護、白底合成與空 MIME/HEIC 契約 (AD-239)**: frontend/lib/image-utils.ts 集中定義 IMAGE_PRESETS (avatar 512 / spot 1600 / cover 1920 / document 2048 / receipt 2048+shortEdge / capsule 1600 / ai_input 1600+shortEdge) 並支援字串 preset 參數。必須實作 hasCanvas2dSupport() 0ms jsdom 預檢、帶 SerialTaskSignal 取消訊號與 8s 逾時之單併發佇列及 __resetImageUtilsForTesting()；優先 createImageBitmap(file)（禁傳 resizeWidth/resizeHeight 避開 Safari EXIF 旋轉倒置）；以 1x1 WebP 探針＋輸出 blob.type 雙驗防 Safari 靜默輸出 PNG；ctx.drawImage 前無條件填 #ffffff 防 bg-black/95 預覽透明黑字隱形；硬鎖 outW*outH <= 16_000_000 並於 finally 釋放 bitmap 與 canvas.width=0；僅對不透明 JPEG 切片前 64KB 檢查 APP1/APP13 EXIF；readImageFileAsDataUrl() 須依副檔名補齊空 MIME/octet-stream 標籤，所有 Cloudinary 上傳器將 .heic/.heif 回傳 URL 正規化為 .jpg 且卸載必 abort XHR。

- **登入頁頂端浮動雙語膠囊安全區淨空與實心選取態聚焦外環契約 (AD-235)**: 登入頁右上角 absolute 語系膠囊 (top: safe-area + 0.75rem, min-h-11 + p-0.5 border) 底緣達 safe-area + 3.875rem。<main> 必須在所有斷點維持 pt-[calc(max(env(safe-area-inset-top,0px),0px)+4rem)]（嚴禁在 sm: 降級為 sm:pt-12 或保留 py-8 sm:py-12 衝突樣式），確保 667x375 橫屏與 320x568 130% 字級下 zero overlap。膠囊內部須採 isolate + z-0 motion.span + relative z-10 文字、Boolean(useReducedMotion()) 正規化，且實心選取態按鈕必須宣告 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-slate-800 維持鍵盤聚焦可視對比。

- **非同步表單雙軌互斥鎖、IME 組字守衛與卸載安全轉場法則**: 凡涉及非同步身分建立或遠端請求之登陸/還原表單，送出前須先通過空白與格式校驗，再同步鎖定 useRef（阻斷單幀連點重入）與 useState（鎖定輸入框、主按鈕與切換鈕 disabled/aria-busy/select-none）；輸入框 Enter 送出必須掛載 !e.nativeEvent.isComposing；document.startViewTransition 必須檢查 typeof === 'function'；且非同步完成與延遲換場計時器必須受 isMountedRef 與 unmount cleanup 保護，異常時於 catch 解鎖並以 toast.error 呈現，嚴禁對 onClick 外拋 unhandled rejection。

- **打字機動畫標題雙層 DOM 無障礙設計與 React Compiler 渲染隔離**: 打字機文字元件必須包含 sr-only 完整可讀文字與 aria-hidden 動態層以維護 a11y；外層 key 隔離內層 state 避免 React 19 / React Compiler 於渲染階段觸發狀態循環更新；支援 prefers-reduced-motion 降級為靜態文字。

- **Multi-Action Input Right Padding Minimum Scale**: Form inputs housing 3 or more absolute right action buttons (e.g. Refresh, Eye Toggle, Copy) MUST enforce at least pr-44 (11rem / 176px) to guarantee zero character overlap with button icons.

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
- **Sheet/Dialog/ScrollArea/Button 四重水平撐破與 MiniSearch 單字元 OR 假陽性陷阱 (FP-115)**: ActivityEditModal 僅設 overflow-y-auto + truncate、dialog.tsx grid 缺 grid-cols-1、scroll-area.tsx Radix 注入 display: table 及 button.tsx 預設 whitespace-nowrap 共同造成 320px 整頁左右滑動；useLocalGeocode 預設 combineWith: 'OR' 搭配單字元分詞造成搜芬蘭出一蘭拉麵、搜台中出海雲台區、搜 Starbucks 出 Mystays。

- **iOS Safari WebP 靜默 PNG、空 MIME HEIC 破圖與 Node 20 jsdom 8 秒死鎖陷阱 (FP-108)**: 現代 iOS Safari 呼叫 canvas.toBlob('image/webp') 會靜默退回 2-6MB PNG；Windows/Android 選取 .heic 或部分 .jpg 時 file.type 為空字串，致 FileReader 輸出 application/octet-stream 遭後端 400 或傳上 Cloudinary 回 .heic URL 在 Chrome 100% 破圖；Node 20+ jsdom 具 URL.createObjectURL 但無 2D Canvas 實作會使未預檢之壓縮佇列卡死至 8s 逾時。必須以 1x1 探針＋blob.type 驗證、hasCanvas2dSupport() 預檢、SerialTaskSignal 取消訊號與 .heic->.jpg URL 正規化全面防禦。

- **Radix ScrollArea 僅設 max-h 無固定 height 導致捲動截斷與 JSX 數值 0 渲染陷阱 (FP-100, FP-103)**: Radix UI ScrollArea 在外層僅設 max-h-[...] 而無明確固定 height 時，內層 Viewport height:100% 會退化成 auto，導致無捲動軸且超出部分被外層 overflow-hidden 截斷（實測 20 筆僅剩 4 筆）。動態高度上限清單應改用原生 div 配合 max-h-[...] 與四重軸向鎖定。另 JSX 條件渲染評分數值嚴禁寫 {rating && ...}（0 會印出字元 '0'），須顯式判別 (rating ?? 0) > 0。

- **Button SVG 預設 size-4 覆寫與 disabled 指標穿透文字反白陷阱**: button.tsx 宣告 [&_svg:not([class*='size-'])]:size-4（權重 0,2,1），會將僅設定 w-5 h-5 的 Loader2 圖示縮小至 16px，必須顯式傳入 size-5 才能保持 20px；此外 button/input 之 disabled:pointer-events-none 會使鎖定期間的觸控長按穿透至父層容器，必須同步於送出前執行 clearActiveSelection() 收合選區並 blur()，且在鎖定狀態對表單外層容器掛載未分層 .select-none（!important）覆蓋 input 預設 user-select: text。

- **SVG 羅盤指針 transform-origin 使用像素單位導致響應式縮放位移刺穿卡片**: 在 SVG 向量動效中，transform-origin: 100px 在不同螢幕 DPI 縮放時會被視為絕對像素偏移。旋轉中心必須使用 transformBox: 'view-box' 配合百分比或 viewBox 原生座標，外層容器必須添加 overflow-hidden。

- **ScrollSpy 高亮標記與平滑捲動互斥競態（Flapping Race）**: 點擊導航錨點觸發平滑捲動時，途中被 IntersectionObserver 觸發回彈判定，導致 0.8s 內產生多次振盪閃爍。應在點擊時以 isManualScrollingRef 互斥鎖暫停 Observer 回調寫入 state 約 900ms，捲動抵達後再解除鎖定。

- **FP-047 (Hook TDZ 順序)**: useEffect 依賴陣列在 render 當下求值，effect 必須放在它引用的所有 useState 宣告之後，否則 ReferenceError 白屏。
- **FP-049 (布林動畫卡住)**: 550ms 內快速開關開時，布林值仍為 true 導致重設無效。改用遞增序號 key={ringCount}。
- **FP-055 (React 19 連鎖渲染)**: CustomCategoryModal 內若使用 useEffect 監聽 isOpen 重設觸發 react-hooks/set-state-in-effect。改由父層 key={id || 'closed'} 自動重置。
- **FP-056 (Tailwind v4 工具類別)**: stroke-[3] 任意值被 Linter 告警，改用標準語意 stroke-3。
