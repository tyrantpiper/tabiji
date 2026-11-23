# 📅 Daily Report - 2026-11-23 (全棧地圖搜尋、跨語系 Top-K 智慧排序重構、行動端 320px 長地名換行零溢位與五雲零毒快取發佈)

> **時間範圍**: `2026-11-22 22:53 ~ 2026-11-23 18:45` (UTC+8)
> **當日納入 Commits (`fc34403..d8ccb8f`, 2 Commits, `33 files changed, 6818 insertions(+), 842 deletions(-)`)**:
> - `6ba9997` (`17:11:42`): `feat(geocode,ui,edge): overhaul Top-K search accuracy, mobile wrapping, and edge cache v2.1` (`33 files changed, 6557 insertions(+), 827 deletions(-)`)
> - `d8ccb8f` (`17:51:10`): `fix(geocode,edge): fix live landmark key priority, cross-country lookup, theme-park homonyms, brand tail strip, and bump edge cache v2.2` (`3 files changed, 338 insertions(+), 92 deletions(-)`)
> **全棧 Quality Gate 實測結果**:
> - Neural Seam Invariant Harness (`scripts/neural_seam_harness.py`): **`10/10` Intact** (`0` Sequelae, `EXIT 0`)
> - Security Ledger (`scripts/validate_security_ledger.py`): **`439 targets` (`201 remediated, 53 verified/unresolved, 185 dismissed/safe`)**（`428 -> 439`, `0` 歷史 ID 遺失, `EXIT 0`）
> - Security Sentinel (`runner.py --mode adaptive --timeout 120`): Round 1 **`10/10 DISMISSED`**（1 項 `CONFIRMED -> REMEDIATED -> DISMISSED`）+ Round 2 **`6/6 DISMISSED`**（淨 `11/11` 唯一目標安全, `0` confirmed / `0` inconclusive）
> - Backend Pytest (`pytest -q`): **`785 passed, 5 skipped, 0 failed`**（基線 `752` ➔ `+33` 新增測試, `EXIT 0`）
> - Frontend TypeScript (`npx tsc --noEmit`) & ESLint (`npm run lint`): **`0 errors, 0 warnings`** (`EXIT 0`)
> - Frontend Vitest (`npx vitest run`): **`127 files, 1,168 passed | 4 skipped (1,172)`**（基線 `124 files / 1,156` ➔ `+3 files / +12 tests`, `EXIT 0`）
> - Frontend Production Build (`npx next build`, Turbopack 16.4.5): **`11/11` static pages** (`EXIT 0`)
> - Cloudflare Edge Shield Dry-Run & Deploy: `Total Upload: 12.08 KiB / gzip: 3.77 KiB`，實上線 Version `cbffc9bf-6379-4ba2-a148-a776d45419f5` (`v=2.2`, 100% 流量)
> - Live 5-Cloud & `@mcp:chrome` E2E (`d8ccb8f`): Cloud Run (`antigravity-backend-00216-vdp`, `/api/health` & `/api/health/deep` `200`, `database.status: connected`), Vercel (`dpl_6EgvP1uzV9YBHBPcyMAgn3BisXuF`, `www.tabijiapp.com` & `travel-pwa-five.vercel.app` `/sw.js` 皆含 `d8ccb8f`), Cloudflare (`v=2.2` `MISS -> HIT` `148–166ms` + 動態白名單 CORS 反射 + `zoom=5/15` 隔離), Supabase (`ACTIVE_HEALTHY`, 4 Edge Functions `ACTIVE`), Cloudinary (`cloudinary-proxy` AVIF/WebP `200 immutable` / 非法請求 `403/400`), Chrome 320px 實測 7 大元件 `scrollWidth == clientWidth` (`0px` 溢位) 且 Console `0` errors。

---

## 1. 工程與檔案異動清單（2026-11-23）

- **後端地理編碼、跨語系翻譯、Top-K 排序與 Search Fusion（6 檔核心程式 + 2 支哨兵測試）**:
  - [backend/services/model_manager.py](file:///d:/Project/tabiji/travel-pwa/backend/services/model_manager.py) (`+13/-9`): 自 `INTENTS_ALLOW_GEMMA_LAST_RESORT` 移除 `"GEOCODE"`（保留呼叫端顯式 `routing_strategy`）；新增 `GEOCODE_CALL_TIMEOUT = 0.9`、`Extraction:{intent_type}` tag 與 `fast_fail`（跳過 429/5xx 退避），根除單筆注音查詢卡死 `38.08s`。
  - [backend/models/base.py](file:///d:/Project/tabiji/travel-pwa/backend/models/base.py) (`+2/-2`) & [backend/routers/geocode.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/geocode.py) (`+50/-9`): `GeocodeSearchRequest.limit` 改為 `Optional[int] = None`（預設全量智慧排序呈現，顯式正數仍受尊重）；移除硬編碼東京預設座標 `(35.6895, 139.6917)` 改由 `resolve_fusion_anchor_coords` 解析；Fusion 結果改以同名 `<50m` 去重合併、不對 `base_list` 二次呼叫 `rerank_top_k`。
  - [backend/services/poi_service.py](file:///d:/Project/tabiji/travel-pwa/backend/services/poi_service.py) (`+1`) & [backend/services/smart_search_service.py](file:///d:/Project/tabiji/travel-pwa/backend/services/smart_search_service.py) (`+67/-2`): 輸出 OSM `cuisine` 標籤並以軟過濾（空集退回原清單）避免誤殺純日文拉麵店。
  - [backend/services/geocode_service.py](file:///d:/Project/tabiji/travel-pwa/backend/services/geocode_service.py) (`+2853/-425`):
    - 修正 Photon `location_bias_scale` 反轉（`z>=14: 0.2, z>10: 0.4, z<=10: 0.7`）、顯式傳送整數 `params["zoom"]` (`0..18`)、移除雙變體空白拼接與硬 `osm_tag`、15 秒斷路器、RFC 7946 `extent` 正規化、`_OSM_SAR_CODES` (`HK`/`MO`) 邊界框轉換、跨源 `importance`/`admin_level`/`display_name` 回填；
    - 建立 `WeakKeyDictionary` Event-Loop 分桶 Nominatim `1 req/s` 鎖（`_gemma_parse_address` 移出鎖外並共用限流器）與空間感知 Nominatim 短路；
    - 解鎖 122+ 國座標優先翻譯（最近城市錨點優先 → 最小面積矩形、0ms 通用設施微字典 → 1.8s Flash-Lite → 1.2s Wikipedia `langlinks` 去括號備援）；
    - 重構 `LANDMARKS_DB` 為 Pass 1a（主鍵/顯示名精確優先）→ Pass 1b（別名），全距離精確閘門＋排除 46 筆連鎖品牌＋精確裸詞 `HOMONYM_GUARD_KEYS`＋解除軟座標對 290+ 無歧義全球地標誤封＋迪士尼／環球影城移出日本專屬表；`BRANDS_DB` 限 `JP` 且 Step 2a/2b 剝除 `_BRAND_GENERIC_TAIL_TOKENS`（`ラーメン`/`ドラッグストア`）；
    - 修正 `cjk_text_similarity`（短子集折減 + 保序子序列含雙字 Bigram + Bigram 召回保護）、跨語系 `not in variant_scripts` 保底 `0.65`、分源 `_batch_rank` (`0.45..0.15`)、`_LANDMARK_QUERY_MARKERS` 補 `"寺/廟/神社"`、`wants_theme_park`、`wants_hotel`、料理詞 vs 城市／次區／地標前綴空間錨點切換、括號／時間前綴直達清洗與低分單次降級、`strict=False` 不硬刪跨國候選、`limit=1` 時 `upstream_limit >= 15`。
  - 新增測試：[test_geocode_search_overhaul_sentinel.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_geocode_search_overhaul_sentinel.py) (`+951`)、[test_topk_and_safety_net_sentinel.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_topk_and_safety_net_sentinel.py) (`+634`)。
- **Cloudflare Edge Shield Worker（1 檔）**:
  - [cloudflare/edge-shield/worker.js](file:///d:/Project/tabiji/travel-pwa/cloudflare/edge-shield/worker.js) (`+43/-10`): 快取命名空間升版至 **`v=2.2`** + `zb=macro` (`round(zoom) <= 10`)；POST 轉發刪除 `Content-Length` 與 `Content-Encoding`；快取排除 `arcgis` 遵循 Esri ToS；新增 `GEOCODE_ALLOWED_ORIGINS` 白名單，於快取 `HIT` 動態反射 CORS 標頭（不汙染共享快取）。
- **前端搜尋體驗、底層防水平溢位與自動換行（16 檔元件/工具 + 3 支哨兵測試）**:
  - [dialog.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/ui/dialog.tsx) (`grid-cols-1`)、[scroll-area.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/ui/scroll-area.tsx) (`overflow-x-hidden [&>div]:!block [&>div]:!min-w-0`)、[schemas.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/schemas.ts)（補 `osm_id`/`osm_type`/`display_name`/`city`/`country`/`state`/`importance`/`source`）、[itinerary-types.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/itinerary-types.ts)（補 `osm_type`/`extent`）、[location-utils.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/location-utils.ts)（`isMacroGeoResult`、`isUsableMacroExtent` 45° 跨洋守衛、`extractCleanPlaceQuery`、統一去重函式）、[useLocalGeocode.ts](file:///d:/Project/tabiji/travel-pwa/frontend/hooks/useLocalGeocode.ts)（`combineWith: 'AND'`、空白/CJK 邊界 `bigramTokenize`、補 10 個日文新字體、修 `brandCount`）。
  - [day-map.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/day-map.tsx)、[FullscreenMapModal.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/FullscreenMapModal.tsx)、[ActivityEditModal.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/ActivityEditModal.tsx)、[LocationEditDialog.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/LocationEditDialog.tsx)、[info-view.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/info-view.tsx)、[itinerary-view.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/itinerary-view.tsx)、[poi-search.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/poi-search.tsx)、[timeline-card.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/timeline-card.tsx)、[TimelineCardOverlay.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/TimelineCardOverlay.tsx)、[POIDetailDrawer.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/POIDetailDrawer.tsx)：全數移除人為 `limit` 與硬 `bbox`、補齊競態/注音/IME 守衛、L2-1 宏觀 `fitBounds(bearing:0,pitch:0)` 不開抽屜分流、四重軸鎖與多行折行（`wrap-break-word whitespace-normal`）、括號備註保留至空白 `desc`、`itinerary-view` 存檔 `3500ms` 熔斷＋偏置座標。
  - 新增測試：[geocode-search-overhaul-sentinel.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/geocode-search-overhaul-sentinel.test.tsx) (`+292`)、[map-search-component-sentinel.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/map-search-component-sentinel.test.tsx) (`+438`)、[ui-wrapping-and-activity-modal-sentinel.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/ui-wrapping-and-activity-modal-sentinel.test.tsx) (`+400`)，與 `docs/security/` 4 檔。

---

## 2. 本日實戰事件、架構決策與經驗沉澱

### 🟢 Features & Fixes
- **免費圖資 0 元全棧地理搜尋徹底根治**：線上實測 38 組跨國／在地／品牌／括號／同音對抗查詢（含首次上線後二次對抗破獲之迪士尼／環球影城／晴空塔／關西機場／嵐山／景福宮／一蘭／松本清 7 類線上真實缺陷），全面轉正並將 `淺草寺 (雷門拍照)` 與 `晴空塔（夜景拍照）` 延遲由 `5–15s` 壓降至 **`224–232ms`**。
- **行動端 320px 零水平溢位與長地名自動換行**：根除 `ActivityEditModal`、`LocationEditDialog`、`POISearch`、`TimelineCard`、`DayMap`、`POIDetailDrawer`、`InfoView` 長地名截斷與頁面左右滑動，Chrome 320px 實測全數 `scrollWidth == clientWidth`。
- **官方搜尋引擎架構對標完成**：釐清本系統「50% 查詢期聯邦元搜尋補償 + 20% 連自架 Photon 亦缺之 CJK 正字法橋接 + 30% 連 Google Maps API 亦無之旅遊行程垂直智慧」之工程邊界，並實測確認 GraphHopper 日/台/韓多語系 `.jsonl.zst` 總計僅 `876.4 MB`（為未來付費成長期自建選項建立精確基線）。

### 🏛️ Architecture Decisions
- **AD-244（公用 Photon 反直覺參數校正、Event-Loop 分桶 Nominatim 鎖與港澳 SAR 邊界契約）**：校正 Photon `location_bias_scale` 反轉語意（街景 `>=14` 用 `0.2`、宏觀 `<=10` 用 `0.7`）與整數 `zoom`；以 `WeakKeyDictionary` 依 Event Loop 分桶 Nominatim `1 req/s` 鎖；`GEOCODE` 移出 Gemma 並鎖 `0.9s` + `fast_fail`；`HK`/`MO` 以 `COUNTRY_BOUNDS ± 0.05°` 邊界框繞過 OSM 國碼黑洞；跨源統一 RFC 7946 `extent` 與 `importance` 回填。
- **AD-245（Full-List Top-K 六維重排、Pass 1a/1b 精確地標閘門、CJK 正字法橋接與安全 Fusion 契約）**：預設 `limit=None` 全量智慧重排（`strict=False` 不硬刪跨國結果，`limit=1` 時 `upstream_limit >= 15`）；`LANDMARKS_DB` 拆分為「主鍵/顯示名精確優先 → 別名」並排除 46 筆連鎖品牌，軟性 `coord_country` 不阻斷無歧義全球地標；`BRANDS_DB` 限 `JP` 且 Step 2a/2b 剝除 OSM 泛用尾詞；`cjk_text_similarity` 採短子集折減＋保序子序列＋Bigram 保護；料理詞與城市/次區/地標前綴雙軌消歧義；括號/時間前綴直達清洗並於低分單次降級；Fusion 禁灌東京預設座標且不二次重排 `base_list`。
- **AD-246（地圖搜尋真實視口偏置、競態序列鎖、L1 AND 過濾與 L2-1 宏觀點擊分流契約）**：全前端入口省略 `limit`（不傳 `null`）與硬 `bbox`，直取真實地圖中心；以 `AbortController` + `requestSeqRef` + `selectedQuery` state + `INCOMPLETE_ZHUYIN_RE` 早退防競態與注音閃現；`useLocalGeocode.ts` 採 `combineWith: 'AND'`＋邊界分詞；宏觀行政區點擊經 `isUsableMacroExtent`（`<= 45°` 防跨洋海外領地飛往幾內亞灣）決定 `fitBounds(bearing:0,pitch:0)` 或質心 `flyTo`，且不自動開啟 `POIDetailDrawer`。
- **AD-247（長地名自動換行與跨元件 0px 水平溢位四層防線契約）**：底層 `dialog.tsx` 鎖 `grid-cols-1`、`scroll-area.tsx` 鎖 `[&>div]:!block [&>div]:!min-w-0`；所有搜尋清單與卡片容器套用四重軸鎖、`min-w-0` 與 `wrap-break-word whitespace-normal`；長字 `<Button>` 顯式覆寫 `whitespace-normal`；`ActivityEditModal` 與 `LocationEditDialog` 分別鎖定 `[isOpen, editItem?.id]` 與 `[isOpen, day]` 清理，並保留括號備註至空白 `desc`。
- **AD-248（Edge Shield Geocode `v=2.2` 動態白名單 CORS、ArcGIS 法遵隔離與五雲零毒快取發布順序契約）**：POST 轉發刪除 `Content-Length`/`Content-Encoding`，寫入快取排除 `arcgis` 且僅用純淨標頭，快取 `HIT` 依 `GEOCODE_ALLOWED_ORIGINS` 動態反射 CORS；凡變更 Geocode 契約之發布，強制嚴守 **`Cloud Run 部署驗收 ➔ 手動 wrangler deploy 升版快取命名空間 ➔ Git Push 觸發 Vercel`**。

### 🔴 Technical Debt
- **DEBT-GEOCODE-TAIPEI-CIVIC-01（Open — 極低頻邊界）**：Photon 瞬時 503/429 熔斷退回 Nominatim 查 `臺北市政府` 時，OSM `operator=臺北市政府` 標籤會誤配 `政大附中 (school)`（本次高併發壓測已使精確座標 `(25.033, 121.565)` 退回結果快取進 `v=2.2`）；後續版更可在 `wants_civic` 僅中 `school` 時補查 `"市政府"` / `"Taipei City Hall"` 並升版快取。
- **DEBT-CLOUDFLARE-SW-TTL-01（Open — 維運排查）**：實測 `www.tabijiapp.com/sw.js` 被 Cloudflare 施加 `max-age=14400`（4 小時），而 `.vercel.app/sw.js` 為 `max-age=0`；待檢視 Cloudflare Zone Browser Cache TTL / Cache Rules 加速 PWA 熱更新。
- **DEBT-SUPABASE-ADVISORS-01（Open — 既有非本次引入）**：Supabase Security Advisors 提醒 `public.pg_net` 位於 `public` schema、3 支既有 `SECURITY DEFINER` RPC 可由 `anon`/`authenticated` 呼叫、及 GitHub Dependabot 2 項 moderate 依賴；另留存實體 iPhone Safari 320px 軟鍵盤慣性目視覆驗。
- **DEBT-CHAT-SECRET-ROTATION-01（Action Required — 本對話清理安全提醒）**：本聊天室早期紀錄（`2026-11-18` step 825）曾貼過明文 `sb_secret_*` 金鑰；本日報推送後應**立即刪除此聊天室**以清除本機對話明文殘留（若需最高潔癖可擇期輪換該 Supabase Secret Key）。

### 🛡️ Failed Paths
- **FP-112（公用 Photon 無 `zh` 語言包之漢字 Edit-Distance 跨海誤配、旋鈕反轉與跨洋 `fitBounds` 陷阱）**：公用 `photon.komoot.io` 僅支援 `default/en/de/fr`，裸查 `東京車站` 因 Lucene `Fuzziness(AUTO)` 改 1 字誤中屏東 `東海車站`、裸查 `慕尼黑`/`首爾` 被台灣餐廳劫持；`location_bias_scale=0.9` 實為 90% 全球重要度而非距離，致台北搜 `Starbucks` 飛往美日；對跨洋海外領地國家（法國 `350.7°`、美國 `360°`、紐西蘭 `358.4°`）直呼 `fitBounds` 會將鏡頭拉至非洲幾內亞灣 `zoom: 0`。
- **FP-113（模組級 `asyncio.Lock` 跨 Loop 崩潰、`model_manager` 死條件與 `LANDMARKS_DB` 單輪別名劫持陷阱）**：裸用模組級 `asyncio.Lock()` 在 `pytest-asyncio` 多事件迴圈拋 `bound to a different event loop`；`call_extraction` 寫死 `tag="Extraction"` 且 `_get_call_timeout("GEOCODE")=45s` 使 `fast_fail` 成死碼；`LANDMARKS_DB` 單輪依長度比對主鍵與別名使 `嵐山→虹夕諾雅`、`景福宮→光化門站`，`LOCATION_KEYWORDS["JP"]` 混入迪士尼／環球影城害 `巴黎迪士尼→芭堤雅夜市`、`環球影城→高雄 YouBike`。
- **FP-114（CJK `token_set_ratio` 子集滿分、`0.45→0.72` 非單調斷崖與 `routers/geocode.py` 二次 `rerank_top_k` 反轉陷阱）**：CJK 拆單字 `token_set_ratio` 使顛倒字 `台中→中台禪寺` 與短子集 `大阪燒→大阪` 拿 `1.0`；`<0.45→0.72` 跨語系保底令不相關店反殺部分匹配店；外層 `routers/geocode.py` 無翻譯變體二次呼叫 `rerank_top_k` 會破壞跨語系分數並反轉既有 `smart_fusion` 順序。
- **FP-115（`Sheet`/`Dialog`/`ScrollArea`/`Button` 四重隱形水平撐破與 `MiniSearch` 單字元 `OR` 污染陷阱）**：`ActivityEditModal` 僅設 `overflow-y-auto` + `truncate`、`dialog.tsx` 缺 `grid-cols-1`、`scroll-area.tsx` Radix 注入 `display: table`、`button.tsx` 繼承 `whitespace-nowrap` 共同造成 320px 整頁左右滑動；`useLocalGeocode` 預設 `combineWith: 'OR'` 致搜 `芬蘭→一蘭拉麵`、`台中→海雲台區` 假陽性。
- **FP-116（Cloudflare Edge Cache `HIT` 漏反射 CORS 跨站停擺與五雲發布競態 7 天毒快取陷阱）**：`cache.put` 淨化標頭後若 `HIT` 未依白名單動態反射 `Access-Control-Allow-Origin` 會使 `.vercel.app` 跨站請求全數 CORS 失敗；`.github/workflows` 無 Cloudflare 自動部署，若先推 `main` 讓 Vercel 搶跑 Cloud Run 3–5 分鐘，會將舊後端回應毒化寫入邊緣 7 天快取。
- **FP-117（括號備註僅於 0 筆觸發降級導致 11 秒逾時與垃圾結果短路陷阱）**：帶括號／時間前綴之活動標題（如 `淺草寺 (雷門拍照)`、`晴空塔（夜景拍照）`）若等到尾端 0 筆才降級，會空燒 5–11 秒觸發存檔 `3500ms` 逾時或吃下低分垃圾結果（如西安 `晴空之阁`），必須於前置優先清洗直查無歧義地標，並在 Speculative 0 筆或 Top-1 相似度 `< 0.55` 時單次降級。

### 🎯 Next Steps
- 提交並推送本日報與 Auto Dream 2.0 注入後之 `.agents/` 記憶檔案；完成後即可**安全刪除本聊天室**（清除早期明文 `sb_secret_*` 對話殘留）。
- 後續維運清單：排查 Cloudflare `/sw.js` `max-age=14400` 規則、補齊 `wants_civic` 僅中 `school` 時之 Nominatim 補查、以及實機 iPhone Safari 驗收 320px 軟鍵盤捲動與 48MP HEIC。

---

## 🧬 Machine-Executable Invariant Rules

```json
[
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BACKEND-PHOTON-GEOCODE-01",
    "title": "公用 Photon 反直覺參數校正、Event-Loop 分桶 Nominatim 鎖與港澳 SAR 邊界契約 (AD-244)",
    "content": "Photon location_bias_scale 代表全球重要度權重 ((1 - scale) 為距離權重)，必須依整數 params['zoom'] (0..18) 反轉設定為 z>=14->0.2、z>10->0.4、z<=10->0.7；嚴禁同 q 空白拼接雙變體 (Operator.And 歸零) 或硬過濾 osm_tag。Nominatim 1 req/s 全域鎖必須以 weakref.WeakKeyDictionary 依 asyncio.get_running_loop() 分桶並導出 __reset_geocode_state_for_testing()，LLM 地址解析須置於鎖外。GEOCODE 自 INTENTS_ALLOW_GEMMA_LAST_RESORT 移除並設 0.9s 超時 + fast_fail + 1.8s 外層上限；無 Key 跨語系走 0ms 微字典 -> 1.2s Wikipedia langlinks (去括號)；HK/MO (_OSM_SAR_CODES) 以 COUNTRY_BOUNDS ±0.05° bbox 取代無效 countrycode=hk/mo；extent 一律正規化為 RFC 7946 [minLon, minLat, maxLon, maxLat] 並跨源回填 importance/admin_level/display_name。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BACKEND-TOPK-RANKING-01",
    "title": "Full-List Top-K 六維重排、Pass 1a/1b 全詞地標閘門與安全 Fusion 契約 (AD-245)",
    "content": "GeocodeSearchRequest.limit 預設 None (上游抓 25 筆，limit=1 時 upstream_limit>=15)，strict=False 嚴禁硬刪跨國候選，全量經 rerank_top_k 重排。LANDMARKS_DB 必拆 Pass 1a (主鍵/顯示名精確優先) -> Pass 1b (別名)，全距離強制 _is_exact_landmark_match 且排除連鎖品牌，HOMONYM_GUARD_KEYS 採精確裸詞比對且僅 lat is None 或 >80km 禁秒回；軟 coord_country 不得阻斷無歧義全球地標，禁止 chinese_display 覆寫分店名；BRANDS_DB 限 JP 且 Step 2a/2b 剝除 _BRAND_GENERIC_TAIL_TOKENS。cjk_text_similarity 採短子集折減 (<0.80) + 保序子序列含雙字 Bigram (>=0.85) + Bigram 召回保護；跨語系保底限 not in variant_scripts (0.65)；分源 _batch_rank (0.45..0.15) 對齊 Photon/Nominatim 權威尺度；區分料理詞與城市/次區/地標前綴空間錨點 (次區半衰期 5km)；括號/時間前綴直達清洗並於低分 (<0.55) 單次降級；smart_search Fusion 禁灌東京預設座標、採 cuisine 軟過濾且不二次重排 base_list。"
  },
  {
    "domain": "map_webgl",
    "type": "INVARIANT_RULE",
    "id": "INV-MAP-SEARCH-UX-01",
    "title": "地圖搜尋真實視口偏置、競態序列鎖、L1 AND 精確過濾與 L2-1 宏觀分流契約 (AD-246)",
    "content": "前端所有地圖與表單搜尋入口一律省略 limit (嚴禁傳 limit: null) 與硬 bbox，lat/lng 直取 mapRef.getCenter()；必配 AbortController + 單調 requestSeqRef + selectedQuery state + INCOMPLETE_ZHUYIN_RE 早退 (不阻斷 Android Gboard 英文 isComposing)；L2 回應以 [...rawResults] 為主、去重後 localMapped 附尾，去重統一採 (normOsmType, osm_id) + 同名 <50m。useLocalGeocode.ts 強制 combineWith: 'AND'、空白/CJK 邊界 bigramTokenize 與同步 10 個日文新字體。點擊結果採 L2-1 智慧分流：isMacroGeoResult(r) 時僅在 isUsableMacroExtent (0.002° <= span <= 45° 擋跨洋領地) 通過才 fitBounds(..., { bearing: 0, pitch: 0 })，否則質心 flyTo 且不開啟 POIDetailDrawer；僅具體 POI 插紅針開抽屜。"
  },
  {
    "domain": "ios_ui",
    "type": "INVARIANT_RULE",
    "id": "INV-IOS-LONG-NAME-WRAP-01",
    "title": "長地名自動換行與跨元件 0px 水平溢位四層防線契約 (AD-247)",
    "content": "dialog.tsx DialogContent 必宣告 grid-cols-1 阻斷隱式 auto 軌道膨脹；scroll-area.tsx Viewport 必宣告 overflow-x-hidden [&>div]:!block [&>div]:!min-w-0 破除 Radix display: table 水平撐寬。所有地點搜尋結果與行程卡片 (ActivityEditModal, LocationEditDialog, POISearch, TimelineCard, TimelineCardOverlay, InfoView, DayMap, FullscreenMapModal, POIDetailDrawer 展開態) 滾動容器必套用四重軸鎖，button 必加 min-w-0 max-w-full overflow-hidden，地名與地址撤除 truncate 改用 min-w-0 flex-1 wrap-break-word [word-break:break-word] whitespace-normal，包裹長文字之 <Button> 必覆寫 whitespace-normal；ActivityEditModal 清理鎖定 [isOpen, editItem?.id]、LocationEditDialog 鎖定 [isOpen, day]，並以 extractCleanPlaceQuery 保留括號備註至空白 desc。"
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-DEVOPS-EDGE-GEOCODE-ROLLOUT-01",
    "title": "Edge Shield Geocode 動態白名單 CORS、ArcGIS 隔離與五雲有序發布契約 (AD-248)",
    "content": "cloudflare/edge-shield/worker.js 轉發 POST 前必刪 Content-Length 與 Content-Encoding；寫入 7 天快取必用純淨 Headers 並排除 source === 'arcgis' (Esri ToS)；快取鍵以 round(zoom) <= 10 (zb=macro) 隔離宏觀視口；快取 HIT 必依 GEOCODE_ALLOWED_ORIGINS 白名單動態反射 Access-Control-Allow-Origin、Access-Control-Allow-Credentials: true、Vary: Origin 與 X-Content-Type-Options: nosniff (嚴禁寫入共享快取)。因 Vercel (~1m) 快於 Cloud Run (3-5m)、Worker 無自動 CI 且 www /sw.js 具 4 小時快取，凡變更 Geocode 契約之發布必嚴守 Cloud Run 部署驗收 -> 手動 wrangler deploy 升版快取命名空間 -> Git Push 觸發 Vercel。"
  },
  {
    "domain": "map_webgl",
    "type": "FAILED_PATH",
    "id": "FP-112",
    "title": "公用 Photon 漢字 Edit-Distance 跨海誤配、scale 反轉與跨洋 fitBounds 幾內亞灣陷阱 (FP-112)",
    "content": "公用 photon.komoot.io 未啟用 zh 語言包，裸查「東京車站」會因 Lucene Fuzziness(AUTO) 改 1 字誤中屏東「東海車站」，裸查「慕尼黑/首爾」遭台灣同名餐廳劫持；location_bias_scale=0.9 實為 90% 全球重要度權重導致台北搜 Starbucks 飛去美日；法國 (350.7°)/美國 (360°)/紐西蘭 (358.4°) 含海外領地之 extent 直接呼叫 MapLibre fitBounds 會使鏡頭退至非洲幾內亞灣 zoom:0，必須經 isUsableMacroExtent (<=45°) 過濾後退回本土質心 flyTo。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-113",
    "title": "裸用模組級 asyncio.Lock 跨迴圈崩潰、model_manager 死條件與地標單輪別名劫持陷阱 (FP-113)",
    "content": "模組頂層裸建 asyncio.Lock() 在 pytest-asyncio 多迴圈必拋 bound to a different event loop；call_extraction 寫死 tag='Extraction' 且 GEOCODE 預設 45s 使 fast_fail 曾為死條件；LANDMARKS_DB 單輪依長度同時比對主鍵與別名導致嵐山->虹夕諾雅、景福宮->光化門站，且 LOCATION_KEYWORDS['JP'] 混入迪士尼/環球影城害巴黎迪士尼->泰國芭堤雅夜市、環球影城->高雄 YouBike。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-114",
    "title": "CJK token_set_ratio 子集滿分、0.45->0.72 非單調斷崖與 Fusion 二次重排反轉陷阱 (FP-114)",
    "content": "CJK 拆單字直用 fuzz.token_set_ratio 會使顛倒詞 (台中 vs 中台禪寺) 與短殘片 (大阪燒 vs 大阪) 拿滿分 1.0；跨語系保底寫 if fuzz < 0.45: max(..., 0.72) 會造成不及格雜訊反殺部分匹配結果；外層 routers/geocode.py 在無翻譯變體下對已排好之 base_list 二次呼叫 rerank_top_k 會破壞跨語系名次並反轉既有 smart_fusion 順序。"
  },
  {
    "domain": "ios_ui",
    "type": "FAILED_PATH",
    "id": "FP-115",
    "title": "Sheet/Dialog/ScrollArea/Button 四重水平撐破與 MiniSearch 單字元 OR 假陽性陷阱 (FP-115)",
    "content": "ActivityEditModal 僅設 overflow-y-auto + truncate、dialog.tsx grid 缺 grid-cols-1、scroll-area.tsx Radix 注入 display: table 及 button.tsx 預設 whitespace-nowrap 共同造成 320px 整頁左右滑動；useLocalGeocode 預設 combineWith: 'OR' 搭配單字元分詞造成搜芬蘭出一蘭拉麵、搜台中出海雲台區、搜 Starbucks 出 Mystays。"
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-116",
    "title": "Edge Cache HIT 淨化標頭漏反射 CORS 停擺與五雲發布競態 7 天毒快取陷阱 (FP-116)",
    "content": "Cloudflare Worker cache.put 淨化為純 Content-Type + Cache-Control 後，若 cache HIT 未依白名單動態反射 Access-Control-Allow-Origin，將導致 .vercel.app 跨網域快取命中全面 CORS 失敗 7 天；且因 Vercel 快於 Cloud Run 且無 Worker 自動 CI，直接 push main 會使新前端打舊後端並把錯誤結果毒化寫入舊版邊緣快取。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-117",
    "title": "括號備註僅於 0 筆觸發降級導致 11 秒逾時與低分垃圾短路陷阱 (FP-117)",
    "content": "行程卡片含時間前綴與全/半形括號備註 (如 晴空塔（夜景拍照）、淺草寺 (雷門拍照)) 若等到尾端 0 筆才降級，會空燒 5-11 秒觸發存檔 3500ms 逾時或被低分垃圾結果 (如西安晴空之阁) 短路。必須前置清洗直查無歧義地標 (0.2s 秒回)，並於 Speculative Photon 0 筆或 Top-1 相似度 < 0.55 時單次降級重查。"
  }
]
```
