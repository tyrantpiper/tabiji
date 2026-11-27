# 領域知識庫：圖形、地圖與 WebGL (map_webgl)

> **所屬領域**: MapLibre GL JS, WebGL Canvas, 3D Globe, 大圓航線, 手勢隔離, CSP Worker

## 🏛️ 架構決策 (Decisions)
- **全天總覽路線跨海守衛、FOSSGIS Valhalla Polyline6 備援與 14 天邊緣快取契約 (AD-267)**: route.py 採合規 UA + WeakKeyDictionary Singleflight + 429 熔斷 + 分引擎獨立節流鎖（OSRM 與 Valhalla 互不互卡 1s），導入免 Key FOSSGIS Valhalla（Polyline6 1e-6 精度）備援，嚴禁將 straight-line 降級結果寫入 600s 快取，並於 edge-shield 啟用 /api/route SHA-256 14 天邊緣快取（僅快取真實道路結果）。MultiDayMasterMap.tsx 必套用跨海/超長途站點守衛、優先載入 selectedDay、單日超時 15s、過濾 lng===0、將 Ref 更新移入 useEffect 並於行程變更時清除陳舊 roadRoutesByDay。

- **跨區確認座標保真（WYSIWYS）、外國/跨城自洽驗證與弱子字串拒寫契約 (AD-261)**: CreateItemRequest 支援 preserve_coords: bool = False，當前端 POIPreviewCard / BatchPOIPreviewCard 已視覺呈現有效座標或 ActivityEditModal 屬手動/搜尋/地圖解析座標時帶 preserve_coords=true，跳過單筆鎖國覆寫（但對無外國自洽線索之 HOMONYM_GUARD_KEYS 撞名地標仍強制自癒）。verify_and_heal_itinerary_coords 必納入 notes 與 address 並執行 is_self_consistent_foreign_place(..., allowed_countries)（攔截文字提母體國家卻帶外國座標之矛盾分店、排除裝飾性「の」與「大阪燒/廣島燒」料理尾詞）、is_self_consistent_explicit_city_place(...)（保護同國跨城明確城市景點，同時維持無城市線索單點幻覺攔截）與 _is_weak_out_of_country_match（於剝除空白前切分拉丁 token，拒絕短子字串誤撞覆寫有效原座標）。

- **地圖搜尋真實視口偏置、競態序列鎖、L1 AND 精確過濾與 L2-1 宏觀分流契約 (AD-246)**: 前端所有地圖與表單搜尋入口一律省略 limit (嚴禁傳 limit: null) 與硬 bbox，lat/lng 直取 mapRef.getCenter()；必配 AbortController + 單調 requestSeqRef + selectedQuery state + INCOMPLETE_ZHUYIN_RE 早退 (不阻斷 Android Gboard 英文 isComposing)；L2 回應以 [...rawResults] 為主、去重後 localMapped 附尾，去重統一採 (normOsmType, osm_id) + 同名 <50m。useLocalGeocode.ts 強制 combineWith: 'AND'、空白/CJK 邊界 bigramTokenize 與同步 10 個日文新字體。點擊結果採 L2-1 智慧分流：isMacroGeoResult(r) 時僅在 isUsableMacroExtent (0.002° <= span <= 45° 擋跨洋領地) 通過才 fitBounds(..., { bearing: 0, pitch: 0 })，否則質心 flyTo 且不開啟 POIDetailDrawer；僅具體 POI 插紅針開抽屜。

- **地圖搜尋 L1 本地結果保底與多供應商競速 POI 備援契約 (AD-229)**: DayMap 與 FullscreenMapModal 在觸發 L2 雲端 debounce 請求當下及 catch 失敗回退時，必須保留並回寫本地秒回清單 localMapped，嚴禁執行 setResults([]) 洗白已有結果。後端 /api/poi/nearby 禁止單依賴 Overpass，必須以主供應商短時限並行 Photon / Wikipedia / Nominatim 競速保底。

- **Zero-Dictionary Dynamic Segment Naming & Action Noise Disambiguation**: Corridor segment naming follows a 4-tier zero-dictionary hierarchy: known_city_anchors -> GLOBAL_CITY_ANCHORS -> LANDMARKS_DB -> POI token co-occurrence analysis, generating clean 'A -> B' labels for unindexed global routes (e.g. Lima -> Cusco). Transit bridge items without coordinates automatically anchor to origin segment center, while action noise items (check-in, rest) with out-of-country coordinates are purged.

- **Transit Corridor K-Partitioning & Cluster Support Guard**: On transit corridor days (e.g. Shinkansen 500km, island flight 260km), verify_and_heal_itinerary_coords must partition items into K chronological segments using spatial jump detection (>80km). Jumps only split if supported by Invariant 1 (explicit transit splitter category/keyword, local cluster density MinPts >= 2, or known city hit), preventing single-point AI coordinate hallucinations from bypassing outlier defense. Subclusters compute independent medians and output additive type: 'transit_corridor' and segments: [].

- **Self-Bootstrapping Spatial Proximity Bias for Markdown Import**: In parse_markdown (/api/ai/parse-md), when trip title is generic (e.g. '5天4夜自由行'), proximity bias MUST dynamically bootstrap (bias_lat, bias_lng) from the first successfully resolved item coordinate to anchor subsequent geocoding queries and eliminate global coordinate drift.

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
- **單筆新增景點無條件鎖國自癒覆寫有效跨區座標與短子字串模糊撞名陷阱 (FP-133)**: POST /api/trips/items 未傳 notes/address 且無座標確認旗標，在台北行程加入大阪「北海 -HOKKAI- お初天神店」(34.7024, 135.5002) 時遭 verify_and_heal_itinerary_coords 以 country='TW', strict=True 鎖國重搜，Photon 僅憑「北海」二字模糊撞到台灣新北 (25.0395, 121.4247) 並靜默覆寫原座標。必須同時落實 preserve_coords 保真、外國/跨城文字座標自洽檢核與低相關度短子字串拒寫防線。

- **公用 Photon 漢字 Edit-Distance 跨海誤配、scale 反轉與跨洋 fitBounds 幾內亞灣陷阱 (FP-112)**: 公用 photon.komoot.io 未啟用 zh 語言包，裸查「東京車站」會因 Lucene Fuzziness(AUTO) 改 1 字誤中屏東「東海車站」，裸查「慕尼黑/首爾」遭台灣同名餐廳劫持；location_bias_scale=0.9 實為 90% 全球重要度權重導致台北搜 Starbucks 飛去美日；法國 (350.7°)/美國 (360°)/紐西蘭 (358.4°) 含海外領地之 extent 直接呼叫 MapLibre fitBounds 會使鏡頭退至非洲幾內亞灣 zoom:0，必須經 isUsableMacroExtent (<=45°) 過濾後退回本土質心 flyTo。

- **MapLibre 3D DEM Pitch 404 Cascade from TileJSON Null Maxzoom**: Symptom: Tilting map camera pitch >= 30 deg floods console with GET tiles.mapterhorn.com/{z}/{x}/{y}.webp 404 (Not Found). Cause: TileJSON maxzoom is null, defaulting to 22, while GLO-30 data only exists up to z12. Lesson: Always explicitly specify maxzoom: 12 on raster-dem sources.

- **FP-001 (圖形與地圖渲染)**: 雙 WebGL Context (Liquid Glass + MapLibre) 導致 iOS Safari 拋出 WebGL Context Lost 崩潰。改以純 CSS backdrop-blur 交付。
- **FP-002 (MapLibre 相機排程競爭)**: 連續呼叫 easeTo 與 fitBounds 導致後者掐斷前者。必須在 fitBounds options 顯式注入 bearing: 0, pitch: 0。
- **FP-003 (離散生命週期)**: 禁止在 onMove 中綁定 React state，改以 onMoveStart / onMoveEnd 接管。
