# 領域知識庫：圖形、地圖與 WebGL (map_webgl)

> **所屬領域**: MapLibre GL JS, WebGL Canvas, 3D Globe, 大圓航線, 手勢隔離, CSP Worker

## 🏛️ 架構決策 (Decisions)
- **Cross-Component FlyTo Event Bus**: Component-level location previews must dispatch tabidachi:map-flyto custom events with bounded lat/lng rather than opening external map windows.

- **In-Card MiniMap Lightweight Tile Rendering**: Chat POI preview cards must use Web Mercator tile URL calculations (https://server.arcgisonline.com/.../15/{y}/{x}) instead of initializing full WebGL MapLibre instances to prevent GPU memory pressure.

- **Explicit maxzoom 12 Bound on Mapterhorn 3D DEM Raster Source**: Mapterhorn GLO-30 DEM elevation slices only exist up to Zoom 12 globally. TileJSON defaults to maxzoom: null which triggers MapLibre's maxzoom 22 default, causing massive 404 tile request storms when camera pitch >= 30 deg. All raster-dem sources using Mapterhorn must explicitly inject maxzoom: 12 to eliminate invalid network fetches and rely on GPU bilinear shader overzooming.

- **Pinned Lock for MapLibre GL (^6.9.0) and Lucide React (^0.473.0)**: MapLibre GL must be pinned to ^6.9.0 to prevent mat4.invert singular projection crashes in >=6.10, and Lucide React must be pinned to ^0.473.0 to prevent icon renaming breaking changes. Never blindly bulk-upgrade major dependencies in Dependabot without standalone sandboxed verification.

- **MapLibre 宣告式圖層拓撲優先原則**: JSX 必須依物理由底至頂排列。禁止 beforeId 指向未宣告同級圖層。
- **CSP Web Worker 同源靜態管線標準化**: 透過 copy-maplibre-worker.mjs 同步至 public/，宣告 maplibregl.workerUrl = '/maplibre-gl-csp-worker.js'。
- **WebGL Canvas 與浮動手勢雙向硬體隔離**: 容器使用 transform-gpu will-change-transform，拖曳節點宣告 willChange 動態切換，杜絕主執行緒 Layout Reflow。
- **景點抽屜容器內錨定原則**: isInternal={true} 模式將抽屜錨定於地圖內部 (absolute bottom-0)，不破壞全域 Header。
- **大圓航線球面線性插值 (Slerp)**: 跨天長途移動以 geo-multi-day.ts 進行球面插值，色彩池映射天數。
- **雙套件原子升級鎖**: react-map-gl 與 maplibre-gl 綁定內部 transform 實例，嚴禁獨立升級單一套件。
- **多日總覽 2D 平面 Mercator 預設守則**: 預設 isGlobe = false，杜絕球面拖曳拉扯。
- **Globe 投影射線穿透奇異點防禦**: 3D Globe 靠近地平線外圍觸發法向量點積轉負反向滑動，單日地圖同樣 2D 優先。
- **3D 地形拖曳高程凍結與貼地吸附**: DEM 地形啟用時相機暫時凍結，手放開時平滑化消除微幅跳動。
- **地圖控制膠囊呼吸降敏架構**: 靜止 3 秒進入 25% 晶透幽靈態，觸控或拖曳瞬間喚醒至 100%。

## 🛡️ 踩坑記錄 (Failed Paths)
- **MapLibre 3D DEM Pitch 404 Cascade from TileJSON Null Maxzoom**: Symptom: Tilting map camera pitch >= 30 deg floods console with GET tiles.mapterhorn.com/{z}/{x}/{y}.webp 404 (Not Found). Cause: TileJSON maxzoom is null, defaulting to 22, while GLO-30 data only exists up to z12. Lesson: Always explicitly specify maxzoom: 12 on raster-dem sources.

- **FP-001 (圖形與地圖渲染)**: 雙 WebGL Context (Liquid Glass + MapLibre) 導致 iOS Safari 拋出 WebGL Context Lost 崩潰。改以純 CSS backdrop-blur 交付。
- **FP-002 (MapLibre 相機排程競爭)**: 連續呼叫 easeTo 與 fitBounds 導致後者掐斷前者。必須在 fitBounds options 顯式注入 bearing: 0, pitch: 0。
- **FP-003 (離散生命週期)**: 禁止在 onMove 中綁定 React state，改以 onMoveStart / onMoveEnd 接管。
