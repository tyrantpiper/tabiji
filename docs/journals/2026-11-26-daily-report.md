# 📅 Daily Report - 2026-11-26 (4 層零成本 IG/網頁萃取漏斗、SSE 兩階段閒置超時與半成品保留、跨區座標保真與 4 層地圖導航網址分流)

> **時間範圍**: `2026-11-25 22:30 ~ 2026-11-26 03:20` (UTC+8)
> **納入 Commits (`89140b3..working-tree`)**:
> - **已推送並上線 Cloud Run（`89140b3..7b6c0ef`, 2 Commits）**:
>   - `63b5bc1` (`2026-11-26 01:09:21`): `fix(search,backend): upgrade 4-tier IG/web extraction funnel, GAS 404 dead-cache, and hot-path threadpool offloading` (`11 files changed, 2,318 insertions(+), 208 deletions(-)`) — Cloud Run `antigravity-backend-00226-qn8` 實機驗收通過。
>   - `7b6c0ef` (`2026-11-26 01:39:18`): `fix(stream): use two-phase idle timeout and preserve substantial partial output on mid-stream stall` (`2 files changed, 276 insertions(+), 8 deletions(-)`) — Cloud Run `antigravity-backend-00227-ggn` 實機驗收通過。
> - **待推送整理完成（Working Tree on `7b6c0ef`, 已清除 `sw.js`/`sw.js.map` 建置雜訊與根目錄 `semantic_fallback_audit.log`）**:
>   - 跨區確認座標保真（WYSIWYS）＋ 4 層地圖專用導航網址分流（`15 files`: `13 modified + 2 new test files`, `+2,214 / -103`）。
> **全棧 Quality Gate 實測結果**:
> - Root Hygiene Gate & Teamwork Scratch Gate: **PASS** (`0` 根目錄違規檔、`.agents/teamwork/` 已忽略、`sw.js`/`sw.js.map` 雜訊已還原)
> - Neural Seam Invariant Harness (`scripts/neural_seam_harness.py`): **`10/10` Intact** (`0` Sequelae, `EXIT 0`)
> - Security Ledger (`scripts/validate_security_ledger.py`): **`464 targets` (`224 remediated, 53 verified/unresolved, 187 dismissed/safe`)** (`EXIT 0`)
> - Backend Pytest (`pytest -q`): **`924 passed, 5 skipped, 0 failed`**（基線 `852` ➔ `63b5bc1` `872` ➔ `7b6c0ef` `878` ➔ **`924`**, `+72` 新增測試, `EXIT 0`）
> - Frontend TypeScript (`npx tsc --noEmit`) & ESLint (`npm run lint`): **`0 errors, 0 warnings`** (`EXIT 0`)
> - Frontend Vitest (`npx vitest run`): **`136 files, 1,257 passed | 4 skipped (1,261)`**（基線 `135 / 1,249` ➔ **`136 / 1,257`**, `+1 file / +8 tests`, `EXIT 0`）
> - Live Cloud Run Production Verification (`00226-qn8` / `00227-ggn`): IG Reel 冷抓 `1.71s` / 熱快取 `0.27s`、晴空塔冷抓 `2.10s` / 熱快取 `0.25s`、`/api/geocode/resolve-link` (`type=media`) `200 (0.79s, has_login_wall=False, has_img=True)`、GAS `***JZ0C` 404 首呼熔斷（後續跳過 0 次原始網址洩漏）、Top-5 熱讀取端點全 `200`、`HTTP_409=0`、`INFO:httpx=0`、Supabase `public.users=122`（0 污染）。

---

## 1. 工程與檔案異動清單

- **4 層零成本 IG/網頁萃取漏斗、GAS 404 熔斷與熱路徑卸載（`63b5bc1`, 11 檔 `+2,318/-208`）**:
  - [backend/services/web_search_engine.py](file:///d:/Project/tabiji/travel-pwa/backend/services/web_search_engine.py) (`+742/-87`): 導入 Tier 0 LRU 快取 + per-loop singleflight、Tier 1 OG + `Accept: text/markdown` 內容協商、Tier 1.5 Instagram `/p/{shortcode}/embed/captioned/` 內嵌頁與 `/share/` 5-hop SSRF 安全展開（嚴格驗內文拒絕 React CSR 空殼）、Tier 2 Jina Reader 合法標頭（`X-Timeout: 8`、`X-Max-Tokens: 3500`、`X-Retain-Images: alt`、`X-Retain-Media: none`、`X-Retain-Links: text`，移除無效 `X-Token-Budget: 2500`）與 2 MB 有界串流；移除棄用 `ddgs` `google` 後端。
  - [backend/main.py](file:///d:/Project/tabiji/travel-pwa/backend/main.py) (`+112/-10`): URL 預爬超時由 `5.0s` 調升至 `11.0s`、新增中英文全形標點尾端清洗（`。，！？）」】`），失敗時輸出中英雙語誠實降級指引。
  - [backend/services/link_resolver.py](file:///d:/Project/tabiji/travel-pwa/backend/services/link_resolver.py) (`+87/-23`)、[backend/services/geocode_service.py](file:///d:/Project/tabiji/travel-pwa/backend/services/geocode_service.py) (`+25/-8`): 社群 OG 登入牆守衛 + IG Embed 救援；`GAS_RESOLVE_LINK_URLS` / `GAS_GEOCODE_URLS` HTTP 404/410 12 小時單 URL 熔斷快取與 `***xxxx` 脫敏日誌。
  - [backend/routers/trips.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/trips.py)、[backend/routers/expenses.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/expenses.py)、[backend/routers/users.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/users.py): Top-5 高頻讀取路由同步 Supabase PostgREST 查詢改經 `run_in_threadpool` 卸載，保護單進程事件迴圈。
  - [test_ig_resilient_funnel_sentinel.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_ig_resilient_funnel_sentinel.py) (`+1,142`)、[conftest.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/conftest.py) (`+16`)、[test_instagram_and_context_poison.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_instagram_and_context_poison.py)、[test_web_search_engine.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_web_search_engine.py)。
- **SSE 串流兩階段閒置超時與實質半成品保留（`7b6c0ef`, 2 檔 `+276/-8`）**:
  - [backend/main.py](file:///d:/Project/tabiji/travel-pwa/backend/main.py) (`+55/-8`)、[test_stream_timeout_partial_preserve.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_stream_timeout_partial_preserve.py) (`+221`): 兩階段超時（TTFT = `stream_timeout`；出字後轉 `25s` Chunk 間閒置超時 + `95s` 總活動上限），已輸出 `>= 140` 字元時 flush 尾段並發送 `event: error` (`partial_preserved: true`)，杜絕 `event: reset` 洗掉使用者已讀內容。
- **跨區確認座標保真（WYSIWYS）與 4 層地圖專用導航網址分流（待推工作樹，15 檔 `+2,214/-103`）**:
  - **後端座標與連結防線**：[backend/models/base.py](file:///d:/Project/tabiji/travel-pwa/backend/models/base.py) (`+1`)、[backend/services/geocode_service.py](file:///d:/Project/tabiji/travel-pwa/backend/services/geocode_service.py) (`+243/-10`)、[backend/routers/trips.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/trips.py) (`+337/-53`)、[backend/services/model_manager.py](file:///d:/Project/tabiji/travel-pwa/backend/services/model_manager.py) (`+40/-5`)、[backend/routers/ai.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py) (`+17`)、[backend/routers/sample_trip.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/sample_trip.py) (`+5/-1`)、[test_cross_region_coords_and_nav_link_sanitization.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_cross_region_coords_and_nav_link_sanitization.py) (`+840`)。
  - **前端分流與舊資料防禦**：[frontend/lib/location-utils.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/location-utils.ts) (`+209`)、[frontend/lib/api.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/api.ts) (`+2`)、[POIPreviewCard.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/chat/POIPreviewCard.tsx) (`+47/-16`)、[BatchPOIPreviewCard.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/chat/BatchPOIPreviewCard.tsx) (`+33/-4`)、[ActivityEditModal.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/ActivityEditModal.tsx) (`+46/-8`)、[timeline-card.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/timeline-card.tsx) (`+20/-4`)、[itinerary-view.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/itinerary-view.tsx) (`+15/-2`)、[nav-link-and-poi-coords-guard.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/nav-link-and-poi-coords-guard.test.tsx) (`+359`)。

---

## 2. 本日實戰事件、架構決策與經驗沉澱

### 🟢 Features & Fixes
- **IG Reel 內容萃取從失效恢復至 ~1.7s 冷抓／0.27s 熱快取（`63b5bc1`）**：查證 Jina Reader 標頭失效、預爬超時過短、中文標點黏連、OG 登入牆與失效 GAS 404，一次升級為 4 層零成本漏斗（參考 Cloudflare `Accept: text/markdown` 與 Jina 官方規範）並同步卸載 Top-5 熱讀取端點。
- **終結 AI 串流「文字閃現後消失再重轉」（`7b6c0ef`）**：透過 Cloud Run 日誌定位 Google 503 尖峰期 `gemini-3.6-flash` 在 `45.001s` 遭硬性總時限腰斬並送出 `event: reset`，改為兩階段閒置超時與 `>= 140` 字元半成品保護。
- **根治大阪景點加入台北行程座標變新北 & IG 誤填導航網址（待推工作樹）**：透過 Cloud Run 日誌實錘 `POST /api/trips/items` 鎖國搜尋誤把「北海 -HOKKAI- お初天神店」(`34.7024, 135.5002`) 蓋成新北「北海」(`25.0395, 121.4247`)，且 AI Schema 引導將 IG 網址塞進 `link_url`；雙管齊下落地 `preserve_coords` + 跨國/跨城自洽檢核 + 4 層地圖專用導航網址分流（非地圖連結自動歸入「此地備忘錄 → 相關連結」`sub_items` 與 `website_link`），同時保護既有撞名地標防線零退化。

### 🏛️ Architecture Decisions
- **AD-259（4 層零成本 IG/網頁萃取漏斗、GAS 404 12h 熔斷與 Top-5 熱讀取 Threadpool 卸載契約）**：外部網頁抓取統一走 `Tier 0 (LRU + per-loop singleflight) -> Tier 1 (直爬 + Accept: text/markdown) -> Tier 1.5 (IG Embed 含 CSR 空殼驗證與 /share/ 5-hop SSRF 安全還原) -> Tier 2 (Jina Reader 官方標頭 + 2MB 有界串流)`；`main.py` URL 預爬放寬至 `11.0s` 並去除尾端全形標點；社群 OG 登入牆強制攔截；GAS 404/410 寫入 12h 單 URL 熔斷與脫敏日誌；Top-5 高頻讀取路由一律 `run_in_threadpool`。
- **AD-260（SSE 兩階段閒置超時與實質半成品保留契約）**：`stream_chat_generator` 將首字等待（TTFT = `stream_timeout`）與出字後活躍階段解耦（Chunk 間閒置超時 `25s`、總活動上限 `95s`）；凡已向前端輸出 `>= 140` 字元實質內容後發生中斷／超時，必須 flush 緩衝區尾段並送出 `event: error` (`partial_preserved: true`)，嚴禁發送 `event: reset` 抹除畫面。
- **AD-261（跨區確認座標保真 WYSIWYS 與 4 層地圖專用導航網址分流契約）**：`CreateItemRequest` 新增 `preserve_coords: bool = False` 供已預覽卡片與手動／搜尋／地圖解析座標保留原值（對無外國自洽線索之 `HOMONYM_GUARD_KEYS` 仍強制自癒）；`verify_and_heal_itinerary_coords` 補強 `is_self_consistent_foreign_place(..., allowed_countries)`、`is_self_consistent_explicit_city_place(...)`（排除 `の` 裝飾字與「大阪燒／廣島燒」料理詞）及 `_is_weak_out_of_country_match`（拉丁詞彙於剝除空白前切分）。導航網址 `link_url` 採 4 層白名單防線（AI Tool/JSON Schema → 前端 `isMapNavigationUrl`/`splitNavigationAndMemoLinks` → 後端 `_sanitize_item_links` 覆蓋 `create_item`/`update_item`/`save_itinerary`/`import_to_trip`/`ai.py`/`sample_trip.py` → 讀取端 `TimelineCard` 舊資料座標導航回退），非地圖安全 HTTP(S) 網址自動去重轉入 `sub_items`（此地備忘錄 → 相關連結）與 `website_link`，`PATCH` 時不復活已刪除之 `sub_items` 且不觸發無效 JIT。

### 🔴 Technical Debt
- **DEBT-COORDS-PROVENANCE-ENUM-01（Low — Big Tech 血統細化）**：目前以布林 `preserve_coords` 保護已確認座標；後續可升級為枚舉 `coord_source`（`user_manual` / `map_url` / `geocoder_pick` / `ai_preview` / `ai_raw`），讓人工手動輸入撞名地標亦具最高人類主權。
- **DEBT-MAP-WHITELIST-SSOT-01（Low — 前後端白名單單一真相）**：目前地圖導航網域白名單於 `backend/routers/trips.py` 與 `frontend/lib/location-utils.ts` 各維護一份，且為零遷移相容現有介面而雙寫 `sub_items` 與 `website_link`；後續可抽為共用 JSON 並在「此地備忘錄」提供獨立 `website_link` 呈現區。
- **DEBT-GAS-404-ENV-CLEANUP-01（Low — 環境變數清理）**：Cloud Run 環境變數中已 404 的 GAS 端點（`***JZ0C`）已由 12h 熔斷快取屏蔽零延遲影響，下次調整 Cloud Run 環境變數時可順手移除。

### 🛡️ Failed Paths
- **FP-131（Jina Reader 非官方標頭拒收、中文尾端標點黏連、IG Embed React CSR 空殼與 GAS 404 空轉陷阱）**：自訂標頭 `X-Token-Budget: 2500` 遭 Jina Reader 拒收；5s 預爬超時不足以覆蓋冷啟 IG 抽取；中文全形標點黏連 URL 末尾導致抓取失敗；Instagram `/p/{code}/embed/captioned/` 對部分 Reel 回傳 HTTP 200 542KB React CSR 空殼（`title="Instagram"` 且無 `.Caption`），必須檢查實質貼文內容才視為命中，否則立即降級至 Tier 2 Jina；另失效 GAS 404 端點未設負快取會使每次連結解析反覆重試並印出原始腳本網址。
- **FP-132（45 秒硬性串流總時限腰斬活躍輸出並發送 `event: reset` 洗畫面陷阱）**：Google API 503 波動降級至 `gemini-3.6-flash` 後，模型雖正穩定吐字，但在 `45.001s` 撞到固定總時限遭硬切並發出 `event: reset`，導致前端已顯示文字整段消失並無限轉圈；串流必須採「首字 TTFT vs 出字後 Chunk 閒置超時」兩階段設計，且達 `>= 140` 字元嚴禁 `reset`。
- **FP-133（單筆新增景點無條件鎖國自癒覆寫有效跨區座標與短子字串模糊撞名陷阱）**：`POST /api/trips/items` 未傳 `notes`/`address` 亦無座標確認旗標，導致在 `3 Day Taipei Explorer ✨` 行程加入大阪 `北海 -HOKKAI- お初天神店` (`34.7024, 135.5002`) 時遭 `country="TW", strict=True` 模糊撞到台灣新北「北海」(`25.0395, 121.4247`) 靜默覆寫；空間自癒必檢驗外國／跨城文字與座標自洽性、攔截與主行程國家矛盾之分店名稱，並拒絕低相關度子字串覆寫有效座標。
- **FP-134（AI Schema 誤導 `link_url` 混入社群網址、`website_link` 未渲染於「此地備忘錄」與建置雜訊混入版控陷阱）**：`ADD_ITINERARY_DECL` 將 `link_url` 標示為官網／參考連結導致 IG Reel 污染「導航網址」並讓卡片導航鈕誤開 IG；且介面「此地備忘錄 → 相關連結」實際讀取 `sub_items` 而非未渲染之 `website_link`，僅寫 `website_link` 會讓使用者看不到連結。另推送前必剔除 `next build` 產出之 `frontend/public/sw.js`／`sw.js.map` 雜訊與根目錄 `semantic_fallback_audit.log`。

### 🎯 Next Steps
- **推送待發 15 檔與日報記憶庫**：待站長確認後執行 commit + push，觸發 Vercel 前端與 Cloud Run 後端部署，並依 5 步手動清單於 iPad 實機驗證大阪 IG Reel 加入台北行程場景。
- **本聊天室可安全歸檔／刪除**：自 `2026-11-24` 至今（76 輪對話，涵蓋 IDE Hot-Exit 存檔衝突、Auth PoP 封窗、6 帳測試池與線上大清理、原子暱稱建帳、25 筆 CodeQL 五雲實證與 Plan B 硬化、IG 4 層萃取漏斗、SSE 兩階段超時、跨區座標保真與 4 層地圖連結分流）所有高價值架構決策與踩坑經驗皆已 100% 固化至程式碼、測試、兩份日報（`2026-11-25` & `2026-11-26`）與 `.agents/` 記憶庫，推完即可放心開新對話視窗。

---

## 🧬 Machine-Executable Invariant Rules

```json
[
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BACKEND-IG-FUNNEL-GAS-THREADPOOL-01",
    "title": "4 層零成本 IG/網頁萃取漏斗、GAS 404 12h 熔斷與 Top-5 熱讀取 Threadpool 卸載契約 (AD-259)",
    "content": "外部網頁與社群連結萃取必須走 4 層零成本漏斗：Tier 0 LRU 快取 + per-loop singleflight 去重 -> Tier 1 直爬 + Accept: text/markdown 內容協商 -> Tier 1.5 Instagram /p/{shortcode}/embed/captioned/（含 /share/ 5-hop SSRF 安全還原，且必驗證實質貼文內容以剔除 HTTP 200 542KB React CSR 空殼）-> Tier 2 Jina Reader（僅送官方標頭 X-Timeout: 8、X-Max-Tokens: 3500、X-Retain-Images: alt、X-Retain-Media: none、X-Retain-Links: text 與 2MB 有界串流，嚴禁無效 X-Token-Budget: 2500）。main.py URL 預爬超時至少 11.0s 並剝除尾端黏連全形標點；link_resolver.py 必攔截社群 OG 登入牆並走 IG Embed 救援；GAS_RESOLVE_LINK_URLS / GAS_GEOCODE_URLS 遇 HTTP 404/410 必入 12h 單 URL 熔斷快取且僅列印 ***xxxx 脫敏日誌；移除棄用 ddgs google 後端；trips.py/expenses.py/users.py Top-5 高頻讀取路由之同步 Supabase PostgREST 查詢必經 run_in_threadpool 卸載。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BACKEND-SSE-TWOPHASE-PARTIAL-01",
    "title": "SSE 串流兩階段閒置超時與實質半成品保留契約 (AD-260)",
    "content": "backend/main.py stream_chat_generator 嚴禁以單一 45s 硬性總時限腰斬已開始輸出的串流，必須採兩階段超時：Phase 1 等待首字輸出（TTFT = stream_timeout）；一旦輸出可見內容即切換至 Phase 2（Chunk 間閒置超時 25s + 總活動上限 95s）。串流中斷或超時時，只要已輸出 >= 140 字元實質內容，必須 flush 緩衝區尾段並送出 event: error（含 partial_preserved: true），嚴禁發送 event: reset 抹除畫面重跑備援鏈。"
  },
  {
    "domain": "map_webgl",
    "type": "INVARIANT_RULE",
    "id": "INV-GEO-COORDS-PROVENANCE-WYSIWYS-01",
    "title": "跨區確認座標保真（WYSIWYS）、外國/跨城自洽驗證與弱子字串拒寫契約 (AD-261)",
    "content": "CreateItemRequest 支援 preserve_coords: bool = False，當前端 POIPreviewCard / BatchPOIPreviewCard 已視覺呈現有效座標或 ActivityEditModal 屬手動/搜尋/地圖解析座標時帶 preserve_coords=true，跳過單筆鎖國覆寫（但對無外國自洽線索之 HOMONYM_GUARD_KEYS 撞名地標仍強制自癒）。verify_and_heal_itinerary_coords 必納入 notes 與 address 並執行 is_self_consistent_foreign_place(..., allowed_countries)（攔截文字提母體國家卻帶外國座標之矛盾分店、排除裝飾性「の」與「大阪燒/廣島燒」料理尾詞）、is_self_consistent_explicit_city_place(...)（保護同國跨城明確城市景點，同時維持無城市線索單點幻覺攔截）與 _is_weak_out_of_country_match（於剝除空白前切分拉丁 token，拒絕短子字串誤撞覆寫有效原座標）。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BACKEND-NAV-LINK-WHITELIST-01",
    "title": "4 層地圖專用導航網址白名單與此地備忘錄自動分流契約 (AD-261)",
    "content": "link_url（導航網址）嚴格限縮於合法地圖導航網域白名單（Google/Apple/OSM/Naver/Kakao/Yahoo JP/Bing Maps/Amap/Baidu/Waze），並落實 4 層縱深防禦：(1) model_manager.py 全數 AI Tool/JSON Schema（維持 Gemma ADD_ITINERARY_FLAT_DECL Depth=1）將 link_url 限為地圖專用並宣告 website_link；(2) 前端 location-utils.ts isMapNavigationUrl / splitNavigationAndMemoLinks 於 POIPreviewCard、BatchPOIPreviewCard 與 ActivityEditModal 選點/解析層即時分流；(3) 後端 trips.py _sanitize_item_links 作為最終寫入閘道覆蓋 create_item、update_item、save_itinerary、import_to_trip、ai.py 預覽與 sample_trip.py，將非地圖安全 HTTP(S) 網址清空 link_url 並去重寫入 sub_items（此地備忘錄 -> 相關連結）與 website_link，PATCH 時未異動 website_link 不得復活已刪 sub_items 且非地圖連結不得觸發 JIT 座標清空；(4) 讀取端 TimelineCard.openGoogleMap 遇歷史污染之非地圖 link_url 改以有效 (lat, lng) 或地名開啟 Google Maps。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-131",
    "title": "Jina Reader 非官方標頭拒收、中文尾端標點黏連、IG Embed CSR 空殼與 GAS 404 空轉陷阱 (FP-131)",
    "content": "向 Jina Reader 傳送非官方標頭 X-Token-Budget: 2500 會導致拒收；main.py 5s 預爬超時與未剝除尾端中文標點（。，！？）」】）會造成 IG/網頁抽取失敗；Instagram /p/{code}/embed/captioned/ 對部分 Reel 回傳 HTTP 200 542KB React CSR 空殼（title='Instagram' 無 .Caption），未驗實質內文即回傳會阻斷 Tier 2 Jina 接手；另失效 GAS 404 端點未加 12h 熔斷快取會反覆空耗並洩漏完整網址。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-132",
    "title": "45 秒硬性串流總時限腰斬活躍輸出並發送 event: reset 洗畫面陷阱 (FP-132)",
    "content": "Google Gemini API 503 尖峰期降級至 gemini-3.6-flash 時，模型雖持續吐字但在 45.001s 觸發固定總時限截斷並發送 event: reset，導致使用者已閱讀的文字突然蒸發並重轉。串流超時必採兩階段閒置超時（首字 TTFT vs 出字後 25s Chunk 閒置 + 95s 上限），且已輸出 >= 140 字元實質文字時嚴禁送出 event: reset。"
  },
  {
    "domain": "map_webgl",
    "type": "FAILED_PATH",
    "id": "FP-133",
    "title": "單筆新增景點無條件鎖國自癒覆寫有效跨區座標與短子字串模糊撞名陷阱 (FP-133)",
    "content": "POST /api/trips/items 未傳 notes/address 且無座標確認旗標，在台北行程加入大阪「北海 -HOKKAI- お初天神店」(34.7024, 135.5002) 時遭 verify_and_heal_itinerary_coords 以 country='TW', strict=True 鎖國重搜，Photon 僅憑「北海」二字模糊撞到台灣新北 (25.0395, 121.4247) 並靜默覆寫原座標。必須同時落實 preserve_coords 保真、外國/跨城文字座標自洽檢核與低相關度短子字串拒寫防線。"
  },
  {
    "domain": "state_cache",
    "type": "FAILED_PATH",
    "id": "FP-134",
    "title": "AI Schema 誤將非地圖網址歸入 link_url、website_link 未渲染於此地備忘錄與 sw.js 建置雜訊陷阱 (FP-134)",
    "content": "AI 工具宣告將 link_url 描述為官網或相關連結導致 IG Reel 污染導航網址，使 TimelineCard 導航鈕誤開 IG；且「此地備忘錄 -> 相關連結」實際渲染欄位為 sub_items 而非未掛載於彈窗的 website_link，若僅改存 website_link 使用者將看不到連結，必同步寫入 sub_items（去重）。另推送前必還原 next build 產出之 frontend/public/sw.js、sw.js.map 雜訊並清除根目錄 *.log 以通過 Root Hygiene Gate。"
  }
]
```
