# 📅 Daily Report - 2026-11-27 (五雲全棧體檢加固、Search Proxy v2.1 全語系合併、Deep Research v2 與 Antigravity 沙盒聯網重構)

> **時間範圍**: `2026-11-26 22:38 ~ 2026-11-27 20:22` (UTC+8)
> **納入 Commits (`d8cfd3b..15df4ec`, 共 12 Commits, 全數已部署五雲線上驗收)**:
> - **Wave 1–3 五雲安全與可靠性全面加固（2 Commits）**:
>   - `4895b5b` (`2026-11-26 22:38`): `fix(security,five-cloud): harden push RLS, notify HMAC, search/POI/route pipelines, async offload, and edge security headers (Waves 1-3)` (`53 files, +5,798/-1,745`)
>   - `3b150d4` (`2026-11-26 23:12`): `fix(five-cloud,audit): fix DDG ad-snippet shift, zh-TW POI disambiguation, deep-research SSE wiring, CSP origins, and expenses async offload` (`12 files, +566/-87`)
> - **Tracks A–D 聯網搜尋、960px 高清 POI Lightbox、跨海路線守衛與邊界限流（3 Commits）**:
>   - `5a8ad3a` (`2026-11-27 02:07`): `fix(search,poi,route,backend): revive zero-key AI search, 960px POI Lightbox Option A, cross-ocean route guard & backend hardening (Tracks A-D)` (`14 files, +1,202/-113`)
>   - `b1341f1` (`2026-11-27 02:41`): `fix(search,poi,route,security): eliminate CF Promise.all HOL blocking, harden Wikimedia raster/lang* guards, Lightbox ESC/safe-area, and IP-only public rate limits` (`11 files, +480/-69`)
>   - `aa7cac4` (`2026-11-27 03:27`): `fix(search,poi,route,ui): fix JP locale/stopwords & forum spam, Wikidata P18 raster guard, Tier2 cancel log, Lightbox landscape safe-area/focus, and stale MultiDay routes` (`9 files, +345/-34`)
> - **Search Proxy v2.1 雙源有界寬限合併與全語系 Unicode 安全網（2 Commits）**:
>   - `a5c5531` (`2026-11-27 12:59`): `feat(search-proxy): add Option A DDG+RSS dual-source merge and full-locale Unicode safety net` (`2 files, +837/-52`)
>   - `81902d3` (`2026-11-27 13:16`): `fix(search-proxy): harden Latin combining-mark folding, subtitle/syndication dedup, XML entity bounds, and merge contract` (`2 files, +151/-18`)
> - **Deep Research v2 引文管線與跨棧解析基建（2 Commits）**:
>   - `c56f6b1` (`2026-11-27 14:41`): `feat(deep-research): integrate direct Google News RSS + parallel web search and align SourceCitation UI` (`11 files, +2,312/-63`)
>   - `0cf88b8` (`2026-11-27 15:00`): `fix(deep-research): harden timeout budget headroom, travel acronyms, XML/URL safety, and SourceCitation guards` (`7 files, +349/-46`)
> - **Antigravity 遠端沙盒主聯網、零 `GoogleSearch()` 429、503 零延遲自動輪替與全量 RCA 修復（3 Commits）**:
>   - `1715282` (`2026-11-27 18:59`): `fix(deep-research,chat): restore Antigravity SSE primary sandbox, remove free-tier GoogleSearch 429, fast 503 rotation, locale guard, and factual search tool unloading` (`12 files, +1,575/-256`)
>   - `57ed0c7` (`2026-11-27 19:58`): `fix(deep-research,chat): harden AnyIO cancel shield, linear markdown/ReDoS sanitizer, source extraction, pricing marker strip, factual search regex, and EN taxonomy guard` (`6 files, +653/-73`)
>   - `15df4ec` (`2026-11-27 20:22`): `fix(deep-research,chat): fix Antigravity source title corruption, paren URLs, cited priority, step error/running-poll DNS, late-create cancel, marker variants, EN dest localization, and SSE reader abort` (`6 files, +439/-67`)
> - **總增量 (`git diff d8cfd3b..15df4ec --shortstat`)**: **`69 files changed, 14,080 insertions(+), 1,996 deletions(-)`**
>
> **全棧 Quality Gate 與五雲線上實測結果 (`15df4ec`)**:
> - Security Ledger (`scripts/validate_security_ledger.py`): **`464 targets` (`224 remediated, 53 verified/unresolved, 187 dismissed/safe`)** (`EXIT 0`)
> - Neural Seam Invariant Harness (`scripts/neural_seam_harness.py`): **`10/10 seams Intact`** (`EXIT 0`)
> - Backend Pytest: **`975 passed, 5 skipped, 0 failed`**（基線 `924` ➔ **`975`**, `+51` 新增測試, `EXIT 0`）
> - Frontend TypeScript (`tsc --noEmit`) & ESLint (`npm run lint`): **`0 errors, 0 warnings`** (`EXIT 0`)
> - Frontend Vitest: **`139 files, 1,282 passed, 4 skipped`**（基線 `136 / 1,257` ➔ **`139 / 1,282`**, `+3 files / +25 tests`, `EXIT 0`）
> - Next.js Production Build (`NODE_ENV=production npx next build`): **`11/11` routes PASS** (`EXIT 0`)
> - **五雲線上實測**:
>   - **Google Cloud Run (`antigravity-backend-00248-g5q`)**: 100% 流量、18 組環境變數/機密完整保留、`ENV=production`、`/health` 200、`/docs` 404、`severity>=ERROR` 0 筆。
>   - **Vercel (`dpl_3R9GMuxNwtr8NoXsHDQt7oVMLWgR`, `15df4ec`)**: `READY / PROMOTED`、`aliasError: null`、雙網域安全標頭與 `CSP-Report-Only` 上線。
>   - **Cloudflare Workers**: `tabidachi-search-proxy` (`7e93e7f8`)、`tabijiapp-edge-shield` (`8c2c3bc9`)、`cloudinary-proxy`、`tabijiapp-poi-service` 全數 ACTIVE。
>   - **Supabase (`oudnkmigfueuyvxqpqwn`)**: Migration `20261126_harden_push_rls_and_notify_hmac.sql` 已套用、`notify-event` 與 `notify-countdown` v10 ACTIVE、`cron.job #1` 驗證通過。
>   - **線上 API & Chrome DevTools MCP (`https://www.tabijiapp.com`)**: Antigravity SSE 直通 `42.34s`（`sources_count=5`、`tokyodisneyresort.jp`、`has_file_workspace=False`、`has_602410=False`）；180s 逾時降級 503 零重試輪替 `3.9s` 完成且 0 `GoogleSearch` 429；`locale="en"` 清水寺 `12.14s` 純英文回答票價與營業時間（`tools_count=0`）；Chrome 瀏覽器 `32/32` 請求 `200/204`、0 console errors、0 CSP 違規、0 破圖、`EN ↔ 繁中` 與亮/暗模式新聞徽章計算樣式驗收通過。

---

## 1. 工程與檔案異動總覽

- **Supabase 資料庫與 Edge Functions**:
  - [20261126_harden_push_rls_and_notify_hmac.sql](file:///d:/Project/tabiji/travel-pwa/supabase/migrations/20261126_harden_push_rls_and_notify_hmac.sql)、[notify-event/index.ts](file:///d:/Project/tabiji/travel-pwa/supabase/functions/notify-event/index.ts)、[notify-countdown/index.ts](file:///d:/Project/tabiji/travel-pwa/supabase/functions/notify-countdown/index.ts)：封死 `public.push_subscriptions` Default-Deny、上線獨立 `notify_webhook_secret` Vault HMAC-SHA256、移除 `webhook_cleanup_cloudinary()` 舊 `ELSE` 明文 Bearer 回退並補 `ryan_travel/spots` 跨列 GIN 引用計數保護。
- **Cloudflare Edge Workers**:
  - [cloudflare/search-proxy/worker.js](file:///d:/Project/tabiji/travel-pwa/cloudflare/search-proxy/worker.js)：Fail-Closed 雙標頭 `SHA-256` + `timingSafeEqual` 密碼鎖、移除無條件維基毒化、DDG 嚴格 `200`-only（拒 `202` CAPTCHA）+ 廣告列修復 + 非 200 `body.cancel()`、選項 A DDG+RSS 短寬限窗合併（600ms/1800ms）、全語系 Latin-only NFD Unicode 匹配與線性雙層去重。
  - [cloudflare/edge-shield/worker.js](file:///d:/Project/tabiji/travel-pwa/cloudflare/edge-shield/worker.js)：新增 `/api/route` 14 天 SHA-256 虛擬快取（拒存 `straight-line`）與 `/api/poi/media-proxy` 7 天邊緣快取、脫敏 502 `err.message`、修補 `Number(null)` 邊界。
- **Cloud Run 後端 (`backend/`)**:
  - [backend/routers/agents.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/agents.py) & [backend/services/model_manager.py](file:///d:/Project/tabiji/travel-pwa/backend/services/model_manager.py)：深度研究 SSE 恢復 Antigravity 遠端沙盒為主聯網引擎（12s `: heartbeat`、2.5s 輪詢、`anyio.CancelScope(shield=True)` + `create_lock` 原子取消）、共用 `_extract_antigravity_output_and_sources`（清 `file:///workspace/` 與 `602410`、三層優先序來源萃取、4 併發 Host DNS 僅於 `completed` 執行）、Tier 2 徹底移除 `GoogleSearch()` 並啟用 `retry_5xx=False` 零空等 503 即刻輪替。
  - [backend/main.py](file:///d:/Project/tabiji/travel-pwa/backend/main.py)、[backend/services/destination_taxonomy.py](file:///d:/Project/tabiji/travel-pwa/backend/services/destination_taxonomy.py)、[backend/services/web_search_engine.py](file:///d:/Project/tabiji/travel-pwa/backend/services/web_search_engine.py)、[backend/services/flight_pricing_service.py](file:///d:/Project/tabiji/travel-pwa/backend/services/flight_pricing_service.py)：`locale` 權威查詢提煉、純事實 `SEARCH` 卸載行程工具、跨棧 21/21 對齊 Unicode 與線性 XML 解析（GCP 直連 RSS 預設關閉 `ENABLE_DEEP_RESEARCH_DIRECT_RSS="0"`）、共用機票比價與 IATA 反查（保護 `USJ`/`KTX`/`TDL`/`MRT`/`ANA`/`USA`）、`local_q` 去重。
  - [backend/services/poi_service.py](file:///d:/Project/tabiji/travel-pwa/backend/services/poi_service.py)、[backend/routers/poi.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/poi.py)、[backend/routers/route.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/route.py)、[backend/utils/deps.py](file:///d:/Project/tabiji/travel-pwa/backend/utils/deps.py)、全站 40+ 路由與測試：多訊號 Top-K POI 消歧、Wikimedia 11 階 960px 點陣守門與 2-hop SSRF 安全轉址、FOSSGIS Valhalla Polyline6 免 Key 備援與分引擎節流、`ENV=production` 關閉文件端點、清除 33 處 `detail=str(e)`、純 IP 公開限流與 `run_in_threadpool` 全站卸載。
- **Vercel 前端 (`frontend/`)**:
  - [frontend/next.config.mjs](file:///d:/Project/tabiji/travel-pwa/frontend/next.config.mjs)、[frontend/lib/sse-parser.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/sse-parser.ts)、[frontend/components/chat-widget.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/chat-widget.tsx)、[frontend/components/chat/DeepResearchCard.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/chat/DeepResearchCard.tsx)、[frontend/components/chat/SourceCitation.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/chat/SourceCitation.tsx)、[frontend/components/POIDetailDrawer.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/POIDetailDrawer.tsx)、[frontend/components/itinerary/MultiDayMasterMap.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/MultiDayMasterMap.tsx)、[frontend/components/ledger-client.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/ledger-client.tsx)、[frontend/app/splash-preview/page.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/app/splash-preview/page.tsx) 等。

---

## 2. 本日實戰事件、架構決策與經驗沉澱

### 🟢 Features & Fixes
- **五雲全面體檢與 P0 資安零缺口止血（`4895b5b` / `3b150d4`）**：完成 Google Cloud Run、Cloudflare、Vercel、Supabase、Cloudinary 五雲全棧唯讀實證與八大廠最佳實踐對照；關閉 `push_subscriptions` `anon` 偽造 `x-user-id` 漏洞與 `notify-event`/`notify-countdown` 公網裸奔，補齊 Cloud Run `ENV=production` 與 Vercel 安全標頭，清零 33 處 `detail=str(e)` 與 40+ 阻塞事件迴圈路由。
- **景點高清體驗與跨海路線升級（`5a8ad3a` / `b1341f1` / `aa7cac4`）**：POI 消歧修正「東京鐵塔→攝影棚／清水寺→地主神社／金閣寺→放火事件」等誤配；圖片升級 Wikimedia 官方 `960px` 點陣寬度並以方案 A 無裁切 Lightbox 取代 `h-40` 暴力裁切；全天路線補上跨海守衛、FOSSGIS Valhalla Polyline6 免 Key 備援與 Edge 14 天快取。
- **深度研究恢復 Antigravity 遠端沙盒主聯網＋503 極速輪替（`a5c5531` → `15df4ec`）**：經 `wrangler tail` × Cloud Run 雙雲遙測實證機房直連免費搜尋遭反爬封鎖後，將深度研究 SSE 升級為 Antigravity 遠端沙盒主力（42s 回傳 5 筆官網實證來源、0 死鏈、0 追蹤碼外洩），Tier 2 移除免費金鑰必 429 之 `GoogleSearch()` 並改為 503 零原地休眠即刻輪替；同步修好 `locale="en"` 語系主導權與一般聊天純事實查詢誤觸行程罐頭語（C2 Bug）。

### 🏛️ Architecture Decisions
- **AD-262（五雲安全邊界預設拒絕、Vault HMAC 推播閉環與 IP-Only 公開限流契約）**：全前端 0 處直連 PostgREST 之資料表（`public.push_subscriptions`）採 `REVOKE ALL FROM PUBLIC, anon, authenticated` Default-Deny 並刪除偽造標頭 RLS 與前端死碼；推播 Edge Functions (`notify-event`/`notify-countdown`) 以獨立 `notify_webhook_secret` 實作 Vault HMAC-SHA256 + 300s 防重放，拔除 `webhook_cleanup_cloudinary()` 殘留 `ELSE` 明文回退並對 `ryan_travel/spots` 補跨列 GIN 引用保護。Cloud Run 強制 `ENV=production`（`deps.py` 先驗 `is_prod` 再判 `supabase_key`，生產關閉 `/docs`/`/redoc`/`/openapi.json`）；公開代理端點一律採純 IP `get_public_ip_rate_limit_key` 防偽造 `X-Gemini-API-Key` 繞過限流；`search-proxy` 採 Fail-Closed `SHA-256` + `timingSafeEqual`；Vercel `next.config.mjs` 採靜態 `async headers()` + `CSP-Report-Only`（PPR 下禁用 Nonce CSP，`worker-src 'self'` 配合同源 MapLibre Worker）。
- **AD-263（Antigravity 遠端沙盒深度研究主聯網、零 `GoogleSearch()` 降級與 `503` 零延遲自動輪替契約）**：僅深度研究 `/api/agents/research/stream`（嚴格隔離一般聊天 `/api/chat/stream`）優先啟用 Antigravity 遠端沙盒（`antigravity-preview-09-2026`, `background=True, store=True`），在 SSE 內以 12s `: heartbeat` 保活 + 2.5s 輪詢（180s 上限）規避 Cloud Run `cpu-throttling` 凍結，取消時以 `anyio.CancelScope(shield=True)` + `create_lock` 原子取消遠端任務止血 Token；透過共用 `_extract_antigravity_output_and_sources` 清除 `file:///workspace/` 死鏈與 `602410` 各變體標記，僅於 `status=="completed"` 以三層優先序（編號參考 → 正文引用 → 步驟 `url_context_result`/`google_maps_result` 剔除 `is_error=True`/`paywall`）採線性成對括號掃描與 4 併發 Host DNS 萃取來源（空 `budget_exceeded`/`incomplete` 映射為 `failed`）。Tier 2 降級鏈移除免費金鑰必 429 之 `GoogleSearch()`（`explicit_grounding=False`），以 `_execute_with_transient_retry(..., retry_5xx=False)` 零空等即刻 `record_model_error()` 輪替；預設 `ENABLE_DEEP_RESEARCH_DIRECT_RSS="0"`；無來源禁要求 `[1]`/`[2]`。
- **AD-264（UI 語系絕對主導權、純事實 `SEARCH` 工具卸載與共用機票/執行緒池契約）**：`extract_search_queries_with_lite` 嚴守前端介面 `locale` 主導權（`en` 強制英文 + 防誤產 CJK 雙重守衛 + `_localize_taxonomy_dest`；`zh` 遇英文詞仍依繁中判定）；`/api/chat/stream` 與 `/api/chat` 於純事實 `SEARCH`（無加入／排程／附近／推薦意圖）卸載 `[ADD_ITINERARY_DECL, REMOVE_ITINERARY_DECL]` 與 Place Card 提示詞標頭防誤觸罐頭語；機票比價抽離 `flight_pricing_service.py`（具 IATA 反查與 `_NON_IATA_TRAVEL_ACRONYMS` 白名單）並於 SSE 送出 `event: start` **之後**限時 `<=1.5s` 注入以保護 10s TTFB；`getLeanItinerary.ts` 保留 `flight_info`；40+ 同步 DB 路由全數卸載且連線池 `max_keepalive_connections=40`。
- **AD-265（Search Proxy v2.1 雙源有界寬限合併、跨棧 Unicode 對齊與線性 XML/去重契約）**：`search-proxy` 採 DDG（嚴格 `200`-only，非 200 必 `body.cancel()`）與 RSS 並行起跑，DDG 先達時給予有界寬限窗 `min(600ms, max(0, 1800ms - elapsed))`（`Symbol("grace_timeout")` 區分逾時與空回）合併輸出 `ddg+google_news_rss`（DDG `<=limit` + RSS `<=2` 不重複）；JS 與 Python 維護 21/21 對齊之全語系 `normalizeForMatch`（全串 NFC，僅 Latin 區塊 NFD 折疊 `i\u0307`/`đð`/`ø`/`ł`/`ı`/`ßẞ`/`æ`/`œ`，保留韓文與日文濁音 NFC；支援 `ko/KR`、`th/TH`、兩階 `vi/VN` 搭配 `kanaCount===0` 與論壇雜訊剔除）；XML/CDATA 採 ASCII 1-to-1 `_ASCII_LOWER_TRANS` 線性掃描拒收 XXE 並免疫 Turkish `İ` 偏移；出版商後綴採線性 `lastIndexOf` + 雙層 `fp`/`rawFp` 去重。
- **AD-266（POI 多訊號 Top-K 消歧、Wikimedia 11 階 960px 點陣守門與 2-Hop SSRF 代理契約）**：`poi_service.py` 採「Wikidata QID `sitelinks`（`lat=None, lng=None` 繞過 Geosearch）➔ 多語系標題查詢（含 `zh-tw`、歷史事件降權、≤5km 檢核）➔ 多訊號 Top-K 嚴格名稱 Geosearch」與 `POI_ENRICH_CACHE(500)`；`_pick_hd_wiki_image` 升級至官方 `960px` 且嚴格不超過 `originalimage.width`，以白名單點陣副檔名與 `lang*`/`page*` 正則攔截 `.svg`/`.tif`/`.djvu`/`.pdf`/`.ogv`/`.webm`；`/api/poi/media-proxy` 擴增白名單並實作手動 2-hop `urljoin` + `is_safe_url_async` 安全轉址 + 7 天邊緣快取。
- **AD-267（全天總覽路線跨海守衛、FOSSGIS Valhalla Polyline6 備援與 14 天邊緣快取契約）**：`route.py` 實作 `WeakKeyDictionary` Singleflight + 429 熔斷 + 分引擎獨立節流鎖 + 免 Key FOSSGIS Valhalla（Polyline6 `1e-6`）備援，禁存 `straight-line` 入 600s 快取，搭配 `edge-shield` 14 天 SHA-256 邊緣快取；`MultiDayMasterMap.tsx` 補跨海守衛、`selectedDay` 優先、15s 逾時、過濾 `lng === 0`、Ref 更新移入 `useEffect` 並清除陳舊 `roadRoutesByDay`。
- **AD-268（POI 方案 A 無裁切 Lightbox 隔離與 Deep Research 引文防禦契約）**：`POIDetailDrawer.tsx` 採方案 A（`max-w-2xl mx-auto` + 檔位自適應高度 + 極淡模糊底圖 + `object-contain` 零裁切 + Portal Lightbox），落實與 `FullscreenMapModal` 的 ESC 鍵隔離、焦點復原與 iPhone 橫向 `sm:` 安全區 `44×44` 觸控熱區；`DeepResearchCard` + `<SourceCitation />` 強制 `Array.isArray`/`typeof`/`/^https?:\/\//i` 防禦與 Tailwind v4 靜態亮/暗類別，`sse-parser.ts` 落實 EOF flush、`onThinking(status, engine?)` 即時顯示「深度沙盒」與中止時 `reader.cancel()`。

### 🔴 Technical Debt
- **DEBT-PUSH-RLS-01 / DEBT-FLIGHT-PRICING-01 / DEBT-SEARCH-PROXY-SECRET-01** (`[RESOLVED in 4895b5b]`): 已於本批 Waves 1–3 全面清償並通過五雲線上驗收。
- **DEBT-CHAT-503-ROTATION-UNIFY-01（Low — 一般聊天與抽取端 503 輪替一致性）**：目前 `retry_5xx=False` 零空等輪替優先套用於深度研究（`agents.py`）；`/api/chat/stream` 與 `call_extraction` 仍保留預設 `retry_5xx=True`（單次 503 原地休眠 0.35s–1.4s 再重試一次）。後續可依尖峰期體感決定是否統一改為零重試即刻輪替。
- **DEBT-CLOUD-LOGGING-JSON-01（Low — Cloud Logging 結構化分級）**：關鍵告警已由 `print()` 升級為 `logger.warning`，惟 Python 預設 stderr 純文字輸出在 GCP Cloud Logging 仍歸類為 `DEFAULT`；若未來需直接以 `severity=WARNING` 建告警，可加掛精簡 JSON `logging.Formatter`。
- **DEBT-TAVILY-KEY-OPTIONAL-01（Low — 一般聊天免卡商用搜尋備援）**：`tabidachi-search-proxy` 已內建 Tavily/Firecrawl 選配插槽；因目前深度研究已由 Antigravity 沙盒主力接管、一般聊天維持免 Key，待有需求時再決定是否補上免信用卡 Tavily 1,000 次/月免費金鑰。
- **DEBT-FAMILY-TRIP-404-IMAGES-01（Low — 兩趟真實家族行程 30 張歷史 Cloudinary 404 圖片）**：依人類主權原則維持原狀不動（東京家族之旅 23 張、大阪家族之旅 7 張），後續由站長決定手動補圖或執行批次清除空網址。
- **DEBT-SECURITY-KEY-ROTATION-01（Action Required — 手動撤銷臨時測試金鑰）**：站長應於 Google AI Studio 撤銷本次線上實測曾貼入對話視窗之臨時 Gemini 測試金鑰。

### 🛡️ Failed Paths
- **FP-135（雲端機房 ASN 遭零成本搜尋引擎主動反爬降級陷阱）**：經 `wrangler tail` × Cloud Run ±20ms 時間對齊實證：`news.google.com/rss/search` 在 GCP `us-central1`（0/16 全掛 >3.2s）與 Cloudflare `ORD`（2/13 秒拒 + 11/13 掛 >2.8s）均遭機房 ASN 主動反爬降級（住宅 IP 僅 300ms 回 60 筆）；`bing.com/search?format=rss` 遭影毒化；DDG Lite 連續請求必回 `HTTP 202` CAPTCHA。教訓：機房封鎖無法靠拉長 timeout 解決，深度研究主聯網必走 Antigravity 遠端沙盒（或商用 API），GCP 直連 RSS 預設關閉免白等 3.2s。
- **FP-136（免費金鑰 `GoogleSearch()` 429 雙重陷阱、內層 `503` 靜默吞錯繞過熔斷器與 `running` 輪詢期誤跑 DNS）**：免費金鑰在深度研究降級路徑呼叫 `GoogleSearch()` 必吃 429；內層 429 剝離重試若用 `except Exception: pass` 吞掉續發 `503` 並沿用舊外層 `err_code==429` 跳過 `record_model_error()`，加上預設 `retry_5xx=True` 重打同模型，會導致單次請求拖到 34–80s。此外 `GET /api/agents/interactions/{id}` 若在 `status=="running"` 輪詢就執行來源萃取/DNS，或將無內容的 `budget_exceeded`/`incomplete` 視為 `completed`，會浪費 DNS 並回傳空報告。
- **FP-137（Python `re` 缺 `\p{}`、XML/Markdown 正則 ReDoS、Turkish `İ` 索引偏移與純事實 `SEARCH` 誤掛工具陷阱）**：Python `re` 不支援 `\p{}`，非線性 `<item>`/`<![CDATA[` 或巢狀括號正則於 60KB 畸形輸入引發 2.8s $O(N^2)$ ReDoS，`str.lower()` 遇土耳其字 `İ` (`U+0130`) 展開為 2 字元導致索引偏移 +1（須改 ASCII 1-to-1 轉換表線性掃描）；裸 `[A-Z]{3}` 去機場碼會誤殺 `USJ`/`KTX`/`TDL`/`MRT`/`ANA`/`USA`；`locale="en"` 共用中文範例會把英文問句翻成中文；一般聊天純事實 `SEARCH` 掛載行程增刪工具會使模型輸出空白誤觸罐頭推薦語（C2 Bug）。
- **FP-138（Cloudflare Worker `Promise.all` 隊頭阻塞、DDG 廣告列錯位、無門檻維基毒化與全串 NFD 毀壞韓日文陷阱）**：`worker.js` 以 `if (resp.ok)` 將 DDG `202` CAPTCHA 誤判成功、正則硬求屬性順序、未濾廣告列導致標題/摘要 off-by-N 錯位、未對非 200 回應呼叫 `body.cancel()`、用 `Promise.all` 等滿慢速 RSS 造成隊頭阻塞、無條件雙打維基造成 `Shibuya Sky -> BLACKPINK` 上下文毒化；若對整串無差別 `.normalize("NFD")` 會拆散韓文音節與日文濁音 `が`（必須先 NFC 且僅對 Latin 區塊 NFD）。
- **FP-139（Wikimedia 非標準縮圖寬度 / 過度放大 / `.svg` 415 破圖、Geosearch 誤配與 `local_q` 重複重打陷阱）**：請求非標準寬度（如 `200px`）或將小原圖放大超過 `originalimage.width` 會觸發 Wikimedia 404/502；未過濾 `originalimage` / Wikidata P18 的 `.svg`/`.tif`/`.djvu` 會引發 `media-proxy` 415 或前端破圖；`poi_service.py` 先走 Geosearch + 2 字 n-gram + `geosearch_results[0]` 預設值會將「東京鐵塔」配成「東京塔攝影棚」、「清水寺」配成「地主神社」；`main.py` 補搜未判 `local_q != search_query` 會重複重打已失敗關鍵字並餓死 `global_q`。
- **FP-140（五雲邊界誤配、`ENV` 缺失令守衛成死碼、偽造 API Key 繞過限流、跨測試滲漏與 Cloud Logging 分級陷阱）**：Cloud Run 未設 `ENV=production` 使 `deps.py` 與 `auth.py` 生產 Fail-Closed 守衛變死碼；公開代理限流鍵若採 `X-Gemini-API-Key`，攻擊者換隨機字串即可無限繞過；`webhook_cleanup_cloudinary()` 僅對 `mly_*` 做引用計數卻漏保 `ryan_travel/spots` 有誤刪風險；`conftest.py` 單旗標隔離在只 mock RSS 時會漏放真 DDG 請求（須逐葉隔離）；Python 純文字 `logging` 於 Cloud Logging 落入 `DEFAULT` 層級。
- **FP-141（前端 `"undefined"` 字串穿透路由、SSE 遺漏 EOF flush / `reader.cancel()` 與 Tailwind v4 動態類別消失陷阱）**：JS 中 `"undefined"` 為 truthy，缺 `isValidUuid(id)` 導致 2 秒連打 16 筆 `/api/trips/undefined/*` 炸 500；`chat-widget.tsx` 讀不存在的 `tripDetail.items?.length` 令深度研究景點數恆為 0 並錯傳中文標題當 IATA；`sse-parser.ts` 缺 EOF flush 與中止 `reader.cancel()` 會漏收尾事件或洩漏連線；Tailwind v4 須完整靜態寫出 `border-sky-500/30 dark:border-sky-500/20` 否則編譯期裁除。

### 🎯 Next Steps
- **立即可辦（安全衛生）**：至 Google AI Studio 撤銷本次線上測試曾使用之臨時 Gemini 測試金鑰。
- **可選後續優化（不急）**：
  1. 評估是否將 `/api/chat/stream` 與 `call_extraction` 同步切為 `retry_5xx=False` 零空等 503 輪替。
  2. 若需要一般聊天也擁有穩定免費即時聯網，可隨時於 `tabidachi-search-proxy` 注入免信用卡 `TAVILY_API_KEY`（1,000 次/月，現成插槽 0 改碼即生效）。
  3. 評估是否於後端掛載精簡 JSON `logging.Formatter`（對應 Cloud Logging `severity=WARNING`）及決定兩趟真實家族行程 30 張歷史 Cloudinary 404 圖片之處置方式。
- **本聊天室可安全歸檔／刪除**：自 `d8cfd3b` 至 `15df4ec` 共 12 筆 Commits 已全數上線五雲驗收，完整架構決策（`AD-262`～`AD-268`）與踩坑記錄（`FP-135`～`FP-141`）已 100% 固化至本報告與 `.agents/` 分層記憶庫。

---

## 🧬 Machine-Executable Invariant Rules

```json
[
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-SEC-FIVE-CLOUD-DEFAULT-DENY-01",
    "title": "五雲安全邊界預設拒絕、Vault HMAC 推播閉環與 IP-Only 公開限流契約 (AD-262)",
    "content": "全前端 0 處直連 PostgREST 之資料表（如 public.push_subscriptions）一律採 REVOKE ALL FROM PUBLIC, anon, authenticated Default-Deny 並刪除可偽造 x-user-id 標頭之 RLS 與前端死碼；Supabase 推播 Edge Functions（notify-event、notify-countdown）必以獨立 notify_webhook_secret 實作 Vault HMAC-SHA256 + 300s 防重放，拔除 webhook_cleanup_cloudinary() 殘留 ELSE 明文 Bearer 回退並對 ryan_travel/spots 補齊跨列 GIN 引用計數保護。Cloud Run 強制 ENV=production（deps.py 先驗 is_prod 再判 supabase_key，生產關閉 /docs、/redoc、/openapi.json）且禁止任何 detail=str(e) 外洩；高流量公開代理（/api/route、/api/poi/enrich、/api/poi/nearby）必用純 IP get_public_ip_rate_limit_key 杜絕偽造 X-Gemini-API-Key 繞過；search-proxy 採 Fail-Closed 雙標頭 SHA-256 + timingSafeEqual；Vercel next.config.mjs 採靜態 async headers() + CSP-Report-Only（PPR 下嚴禁 Nonce CSP，worker-src 'self' 配合 MapLibre 同源靜態 Worker，/splash-preview 生產回 notFound()）。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BACKEND-ANTIGRAVITY-SSE-FAST503-01",
    "title": "Antigravity 遠端沙盒深度研究主聯網、零 GoogleSearch 降級與 503 零延遲自動輪替契約 (AD-263)",
    "content": "僅深度研究 /api/agents/research/stream（嚴格隔離一般聊天 /api/chat/stream）優先啟動 Antigravity 遠端沙盒（antigravity-preview-09-2026, background=True, store=True），於 SSE 連線內每 12s 送 : heartbeat 保活並每 2.5s 輪詢（上限 180s）避免 Cloud Run cpu-throttling 凍結，取消時必以 anyio.CancelScope(shield=True) + create_lock 原子取消遠端任務（含建立中競態）止血 Token。SSE 與 GET /api/agents/interactions/{id} 共用 _extract_antigravity_output_and_sources：清 file:///workspace/ 死鏈與 602410 各變體追蹤碼、僅於 status=='completed' 依三層優先序（編號參考 -> 正文引用 -> 步驟 url_context_result/google_maps_result 剔除 is_error=True/paywall）採線性成對括號掃描與 4 併發 Host DNS 驗證（空 budget_exceeded/incomplete 映射為 failed）。Tier 2 降級鏈徹底移除免費金鑰必 429 之 GoogleSearch()（explicit_grounding=False），並傳 retry_5xx=False 給 _execute_with_transient_retry 實現 503 零休眠即刻 record_model_error() 輪替；預設 ENABLE_DEEP_RESEARCH_DIRECT_RSS='0'；無來源嚴禁要求模型輸出 [1]/[2]；關鍵告警一律走 logger.warning。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BACKEND-LOCALE-FACTUAL-TOOLS-01",
    "title": "UI 語系絕對主導權、純事實 SEARCH 工具卸載與共用機票/執行緒池契約 (AD-264)",
    "content": "extract_search_queries_with_lite 嚴格依前端介面 locale 分支提示詞：locale='en' 強制全英文查詢 + 原問句無 CJK 卻誤產 CJK 雙重後置守衛 + _localize_taxonomy_dest 翻譯；locale='zh' 即便輸入英文實體名仍維持繁中判定。/api/chat/stream 與 /api/chat 在 detected_intent=='SEARCH' 且 _should_retain_search_itinerary_tools 判為純事實問答（無加入/排程/附近/推薦意圖）時，必卸載 [ADD_ITINERARY_DECL, REMOVE_ITINERARY_DECL] 與 Place Card 提示詞標頭防誤觸罐頭語。機票比價共用 flight_pricing_service.py（含 resolve_iata_to_display_city 與 _NON_IATA_TRAVEL_ACRONYMS 保護 USJ/KTX/TDL/MRT/ANA/USA），於 /api/chat/stream 送出 event: start 之後限時 <=1.5s 注入以保護 10s TTFB；getLeanItinerary.ts 保留 flight_info；全後端同步 DB 路由全數卸載為 def 或 run_in_threadpool 且 max_keepalive_connections=40。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-SEARCH-DUAL-MERGE-UNICODE-01",
    "title": "Search Proxy v2.1 雙源有界寬限合併、跨棧 Unicode 對齊與線性 XML/去重契約 (AD-265)",
    "content": "cloudflare/search-proxy 棄用 Promise.all 隊頭阻塞與無條件維基毒化：DDG 嚴格 status===200（拒絕 202 CAPTCHA）且對所有非 200 回應呼叫 body.cancel()；DDG 與 RSS 並行起跑，DDG 先達時給予 RSS 有界寬限窗 min(600ms, max(0, 1800ms - elapsed))（以 Symbol('grace_timeout') 區分逾時與空陣列，超時即 abort）合併為 ddg+google_news_rss（DDG <=limit + RSS <=2 不重複）；維基退為最後關卡且封鎖時效詞並強制詞彙重疊門檻。worker.js 與 web_search_engine.py 維持 21/21 對齊之全語系 normalizeForMatch（全串 NFC，僅對 Latin 區塊 NFD 折疊 i\\u0307/đð/ø/ł/ı/ßẞ/æ/œ，嚴保韓文音節與日文濁音 NFC；支援 ko/KR、th/TH、兩階 vi/VN 搭 kanaCount===0 與論壇詞剔除）；XML/CDATA 採 ASCII 1-to-1 _ASCII_LOWER_TRANS 線性掃描拒收 XXE 並免疫 Turkish İ 偏移；出版商後綴採線性 lastIndexOf + 雙層 fp/rawFp 去重。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-POI-DISAMBIGUATION-960PX-PROXY-01",
    "title": "POI 多訊號 Top-K 消歧、Wikimedia 11 階 960px 點陣守門與 2-Hop SSRF 代理契約 (AD-266)",
    "content": "poi_service.py 嚴禁使用 2 字暴力 n-gram 與 geosearch_results[0] 預設值，必須採 Wikidata QID sitelinks（帶 lat=None, lng=None 繞過 Geosearch）-> 多語系標題查詢（含 zh-tw 變體、歷史事件降權、<=5km 座標檢核）-> 多訊號加權 Top-K 嚴格名稱 Geosearch，搭配有界 POI_ENRICH_CACHE(500) 與合規 UA TabijiTravelPWA/1.0。_pick_hd_wiki_image 升級縮圖至 Wikimedia 官方 11 階標準寬度 960px 且嚴格不超過 originalimage.width，以白名單點陣副檔名（.jpg/.jpeg/.png/.webp）與 lang*/page* 縮圖正則攔截 .svg/.tif/.djvu/.pdf/.ogv/.webm（含 Wikidata P18）；/api/poi/media-proxy 白名單涵蓋 {upload, thumb, commons}.wikimedia.org 並實作手動 2-hop urljoin + is_safe_url_async 轉址驗證與 7 天邊緣快取。"
  },
  {
    "domain": "map_webgl",
    "type": "INVARIANT_RULE",
    "id": "INV-MAP-MULTIDAY-VALHALLA-GUARD-01",
    "title": "全天總覽路線跨海守衛、FOSSGIS Valhalla Polyline6 備援與 14 天邊緣快取契約 (AD-267)",
    "content": "route.py 採合規 UA + WeakKeyDictionary Singleflight + 429 熔斷 + 分引擎獨立節流鎖（OSRM 與 Valhalla 互不互卡 1s），導入免 Key FOSSGIS Valhalla（Polyline6 1e-6 精度）備援，嚴禁將 straight-line 降級結果寫入 600s 快取，並於 edge-shield 啟用 /api/route SHA-256 14 天邊緣快取（僅快取真實道路結果）。MultiDayMasterMap.tsx 必套用跨海/超長途站點守衛、優先載入 selectedDay、單日超時 15s、過濾 lng===0、將 Ref 更新移入 useEffect 並於行程變更時清除陳舊 roadRoutesByDay。"
  },
  {
    "domain": "ios_ui",
    "type": "INVARIANT_RULE",
    "id": "INV-UI-POI-LIGHTBOX-CITATION-01",
    "title": "POI 方案 A 無裁切 Lightbox 隔離與 Deep Research 引文卡片防禦契約 (AD-268)",
    "content": "POIDetailDrawer.tsx 採用方案 A（max-w-2xl mx-auto + 檔位自適應高度 + 極淡模糊底圖 + 前景 object-contain 零裁切 + Portal Lightbox），必落實與 FullscreenMapModal 的 ESC 鍵事件隔離、關閉後焦點復原與 iPhone 橫向 sm: 安全區 44x44 觸控熱區。DeepResearchCard 整合 <SourceCitation /> 必強制 Array.isArray/typeof/^https?:\\/\\//i 驗證與 Tailwind v4 靜態編譯亮/暗色類別（border-sky-500/30 dark:border-sky-500/20）；sse-parser.ts 必落實 EOF flush、sanitizeGroundingSources、onThinking(status, engine?) 即時切換深度沙盒徽章與中止時 reader.cancel()。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-135",
    "title": "雲端機房 ASN 遭零成本搜尋引擎主動反爬降級陷阱 (FP-135)",
    "content": "經 wrangler tail 與 Cloud Run ±20ms 對齊實證：news.google.com/rss/search 在 GCP us-central1（0/16 掛 >3.2s）與 Cloudflare ORD（2/13 秒拒 + 11/13 掛 >2.8s）均遭機房 ASN 反爬降級（住宅 IP 300ms 回 60 筆）；bing.com/search?format=rss 遭影毒化；DDG Lite 連續查詢必回 HTTP 202 CAPTCHA。機房封鎖無法靠拉長超時修復，深度研究聯網應交由 Antigravity 遠端沙盒（或商用 API），GCP 直連 RSS 預設關閉免白等 3.2s。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-136",
    "title": "免費金鑰 GoogleSearch 429、內層 503 靜默吞錯繞過熔斷器與 running 輪詢誤跑 DNS 陷阱 (FP-136)",
    "content": "免費 BYOK 金鑰在深度研究降級路徑送 GoogleSearch() 必吃 429；內層 429 剝離重試若將續發 503 吞入 except Exception: pass 並沿用舊外層 err_code==429 跳過 record_model_error()，加上預設 retry_5xx=True 原地重打，會造成 34-80s 卡頓。另 GET /api/agents/interactions/{id} 若在 status=='running' 輪詢期執行來源萃取/DNS，或將無內容 budget_exceeded/incomplete 視為 completed，會浪費 DNS 並吐空白報告。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-137",
    "title": "Python re 缺 \\p{}、XML/Markdown ReDoS、Turkish İ 偏移與純事實 SEARCH 誤掛工具陷阱 (FP-137)",
    "content": "Python 標準 re 不支援 \\p{}，非線性 <item>/<![CDATA[ 或巢狀括號正則於 60KB 惡意輸入引發 2.8s O(N^2) ReDoS，str.lower() 遇土耳其字 İ (U+0130) 展開為 2 字元會使索引偏移 +1（必改 ASCII 1-to-1 轉換表線性掃描）；裸 [A-Z]{3} 去機場碼會誤殺 USJ/KTX/TDL/MRT/ANA/USA；locale='en' 共用中文範例會將英文問句誤譯中文；一般聊天純事實 SEARCH 掛載行程增刪工具會令模型空白輸出誤觸罐頭推薦語（C2 Bug）。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-138",
    "title": "Cloudflare Worker Promise.all 隊頭阻塞、DDG 廣告列錯位、維基毒化與全串 NFD 毀壞韓日文陷阱 (FP-138)",
    "content": "worker.js 以 if (resp.ok) 將 DDG HTTP 202 CAPTCHA 誤判成功、正則硬求屬性順序、未濾廣告列致標題/摘要 off-by-N 錯位、非 200 未呼叫 body.cancel()、用 Promise.all 等滿慢速 RSS 造成隊頭阻塞、無條件雙打維基導致 Shibuya Sky -> BLACKPINK 毒化；全串無差別 .normalize('NFD') 會拆散韓文音節與日文濁音 が（必先 NFC 且僅對 Latin 區塊 NFD）。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-139",
    "title": "Wikimedia 非標準縮圖寬度/過度放大/.svg 415 破圖、Geosearch 誤配與 local_q 重複重打陷阱 (FP-139)",
    "content": "向 Wikimedia 請求非標準寬度（如 200px）或放大超過 originalimage.width 會觸發 404/502；未過濾 originalimage 與 Wikidata P18 之 .svg/.tif/.djvu 會引發 media-proxy 415 或前端破圖；poi_service.py 先打 Geosearch + 2 字 n-gram + geosearch_results[0] 預設值會將東京鐵塔配成東京塔攝影棚、清水寺配成地主神社；main.py 補搜未檢查 local_q != search_query 會重打失敗關鍵字並餓死 global_q。"
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-140",
    "title": "ENV 缺失令生產守衛成死碼、偽造 API Key 繞過公開限流、測試單旗標滲漏與 Cloud Logging 分級陷阱 (FP-140)",
    "content": "Cloud Run 未設 ENV=production 使 deps.py 與 auth.py Fail-Closed 守衛變死碼；公開代理限流若採 X-Gemini-API-Key 為鍵，攻擊者換隨機字串即可繞過；webhook_cleanup_cloudinary() 漏保共用 ryan_travel/spots 具誤刪風險；conftest.py 單旗標測試隔離在僅 mock RSS 時漏放真 DDG 請求（須逐葉隔離）；Python 純文字 logging 於 Cloud Logging 落入 DEFAULT 層級。"
  },
  {
    "domain": "state_cache",
    "type": "FAILED_PATH",
    "id": "FP-141",
    "title": "前端 'undefined' 字串穿透路由、SSE 缺 EOF flush/reader.cancel 與 Tailwind v4 動態類別消失陷阱 (FP-141)",
    "content": "JS 中 'undefined' 為 truthy，前端缺 isValidUuid(id) 致 2 秒連打 16 筆 /api/trips/undefined/* 炸 500；chat-widget.tsx 誤讀不存在之 tripDetail.items?.length 致深度研究景點數恆為 0 並錯傳中文標題當 IATA；sse-parser.ts 缺 EOF flush 與中止 reader.cancel() 會漏末事件或洩漏連線；Tailwind v4 若未靜態完整寫出亮/暗色類別（如 border-sky-500/30 dark:border-sky-500/20）將遭編譯期裁除。"
  }
]
```
