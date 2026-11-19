# 📅 Daily Report - 2026-11-19 (雙網域與邊緣防火牆加固、周邊 POI 雙層破洞根治、20 筆滾動修復及全域 Bug Hunter T1–T9 總決戰)

> **時間範圍**: `2026-11-19 00:00 ~ 23:59` (UTC+8)
> **當日納入 Commits（共 6 筆）**:
> - [`be7a32c`](file:///d:/Project/tabiji/travel-pwa/cloudflare/edge-shield/worker.js) (`00:51:27`): `fix(auth,edge,security): harden session cutover, edge routing, and cloudinary signing` — **`31 files, +3726 / -215`**
> - [`36b07bb`](file:///d:/Project/tabiji/travel-pwa/backend/services/poi_service.py) (`02:21:56`): `fix(auth,poi): enable cross-origin reauth healing and hedged nearby POI fallback` — **`11 files, +1030 / -80`**
> - [`1fa192e`](file:///d:/Project/tabiji/travel-pwa/frontend/components/poi-search.tsx) (`02:37:49`): `fix(poi): enable full 20-item native scrolling inside POISearch` — **`2 files, +27 / -5`**
> - [`6c714e2`](file:///d:/Project/tabiji/travel-pwa/supabase/migrations/20261119_bug_hunter_remediation_schema.sql) (`13:14:52`): `fix(t1-t9): harden notifications, realtime sync, capsules, wiki fallback, and AI streaming` — **`47 files, +6295 / -424`**
> - [`96d5fe2`](file:///d:/Project/tabiji/travel-pwa/supabase/migrations/20261119_bug_hunter_remediation_schema.sql) (`13:15:08`): `chore: remove temporary supabase cli version file` — **`1 file, -1`**
> - [`0445f1a`](file:///d:/Project/tabiji/travel-pwa/backend/routers/notifications.py) (`13:59:57`): `fix(t1-t9): harden broadcast topics, streaming progress, SSRF/threadpool, and realtime coverage` — **`22 files, +476 / -69`**
> *(註：`1fa192e..0445f1a` 淨變動合計為 `55 files changed, 6704 insertions(+), 427 deletions(-)`。)*
> **最終全棧系統品質關卡（於 `0445f1a` 獨立覆核完成）**:
> - Backend Pytest: `726 passed, 5 skipped in 104.58s (0:01:44)`（Exit `0`）
> - Frontend: `tsc --noEmit` (Exit `0`)、`npm run lint` (Exit `0`)、`npx vitest run` `118 files, 1113 passed | 4 skipped (1117)`（Exit `0`）
> - Security Ledger (`validate_security_ledger.py`): `408 targets (181 remediated, 53 verified/unresolved, 174 dismissed/safe)`（Exit `0`）
> - Security Sentinel (`runner.py`): 第一輪 Post 補驗達成 `6/6 DISMISSED`；`0445f1a` 覆核輪 [findings_2026-11-19_review_fixes.json](file:///d:/Project/tabiji/travel-pwa/docs/security/history/findings/findings_2026-11-19_review_fixes.json) + [review_retry.json](file:///d:/Project/tabiji/travel-pwa/docs/security/history/findings/findings_2026-11-19_review_retry.json) 共 `5 DISMISSED`、`1 INCONCLUSIVE`（[notify-event/index.ts](file:///d:/Project/tabiji/travel-pwa/supabase/functions/notify-event/index.ts) 因 `agy.exe` 90s/120s CLI 逾時未決，已以 Vitest 與直接讀碼覆蓋）。
> - **五大雲端真實部署與遙測驗證**:
>   - Vercel (`prj_1SHlNELBNWUvFlj8jK4Vxo4YFsqd`): `dpl_2QvijgGhZgPDiwCkZvZHX1PKd3k7` (`0445f1a`, `READY`/`PROMOTED`)
>   - Cloud Run (`antigravity-prod-2026`, `us-central1`): `antigravity-backend-00206-lgc`
>   - Cloudflare (`tabijiapp-edge-shield` & `tabijiapp-poi-service`): `worker_get` 驗證 `v=2` + `BYPASS` + 關閉 `workers_dev`
>   - Supabase (`oudnkmigfueuyvxqpqwn`): SQL 檢查 `addr_col=1`, `mly_index="idx_itinerary_items_mly_ref_id"`, `shift_rpc="shift_trip_capsules"`, `capsule_cleanup_triggers=2`, `rls_agent_fallback=true`, `anon_fallback_grants=0`, `fallback_rows=0`, `recent_non_system_trips=0`, `recent_notif_errors=0`；Edge Functions `notify-countdown` (v7), `notify-event` (v7), `notify-broadcast` (v6), `cleanup-cloudinary` (v6) 全數 `ACTIVE`
>   - Live HTTP & Chrome (`pageId=23`): `/api/notifications` 未登入 `401`、登入 `200`；`/api/poi/ai-enrich` 無 Key 回 `200 PARTIAL_SUCCESS` (`NO_API_KEY`)；`/api/geocode/search` `zh z12 MISS -> z16 HIT`、`en z12 MISS -> z16 HIT`、`X-Gemini-API-Key BYPASS`；首頁 `0` console error、`0` 破圖、`localStorage` 無測試金鑰殘留。

---

## 1. 三階段戰役核心交付明細（2026-11-19）

### 🟢 Stage A（`00:51 ~ 02:37`）：雙網域認證收斂、邊緣安全與周邊 POI 重生 (`be7a32c`, `36b07bb`, `1fa192e`)
1. **認證指紋鎖定與同源跨網域保險庫回填**（[auth-session.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/auth-session.ts)、[auth.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/auth.py)、[hooks.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/hooks.ts)、[usePoiPool.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/hooks/usePoiPool.ts)、[session-reauth-modal.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/auth/session-reauth-modal.tsx)）：
   - 以 JSON 防碰撞憑證指紋鎖（`lastFailedExchangeFingerprint`）與頁面記憶體級靜默標記（`isReauthDismissedInMemory`）淘汰易與 SWR 15 秒輪詢相撞的 10 秒全域冷卻；放行 `/api/poi/*` 單次靜默換票且不誤刪主會話。
   - `/api/auth/session` 對遺失 Token 之同源舊網域（`not is_authenticated` 且明確傳遞 `expected_user_id == clean_uid`）安全領回保險庫金鑰（同時嚴守 ADR-009 撤銷檢查與裸 UUID 探測拒絕）。
   - `useExpenses` / `useTripCapsules` / `usePoiPool` 補齊 `401/403/404` 停試守衛；`useTripDetail` 改用模組級 `lastTripDetailMutateMap` 去重；認證恢復後派發全域 `mutate` 與 Outbox 重送。
2. **Cloudflare Edge Shield / POI Service / Cloudinary 封口**：
   - [poi-service/wrangler.jsonc](file:///d:/Project/tabiji/travel-pwa/cloudflare/poi-service/wrangler.jsonc) 與 [edge-shield/wrangler.jsonc](file:///d:/Project/tabiji/travel-pwa/cloudflare/edge-shield/wrangler.jsonc) 明設 `workers_dev: false`、`preview_urls: false`；`poi-service` 拒接 `.workers.dev`（實測回 `404`/`403`）與無驗簽 `atob()`；`edge-shield` 排除 `BACKEND_POI_ENDPOINTS`、補齊 `UUID_V4_REGEX`、剝除 fallback `Authorization` 並檢查 `Number.isFinite(payload.exp)`。
   - [cloudinary-test/route.ts](file:///d:/Project/tabiji/travel-pwa/frontend/app/api/cloudinary-test/route.ts) 於生產環境 fail-closed `404`；[sign-cloudinary/route.ts](file:///d:/Project/tabiji/travel-pwa/frontend/app/api/sign-cloudinary/route.ts) 強制檢驗 `ALLOWED_FOLDERS`、`ALLOWED_PARAM_KEYS`、`timestamp` 與 `public_id` 路徑安全；[poi/[...path]/route.ts](file:///d:/Project/tabiji/travel-pwa/frontend/app/api/poi/%5B...path%5D/route.ts) 如實透傳 `401/502`。
3. **周邊 POI 雙層破洞貫通與 20 筆完整滾動**：
   - [poi_service.py](file:///d:/Project/tabiji/travel-pwa/backend/services/poi_service.py): 為直連的 `search_poi_combined` 建立多供應商競速並行機制（Overpass 2.5s + Photon + Wikipedia + Nominatim + 6km 延伸半徑與 5 分鐘快取）。
   - [poi-search.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/poi-search.tsx): 移除造成捲動卡死於 4 筆的 Radix `<ScrollArea max-h-[300px]>` 與 `.slice(0, 10)` 硬截斷，改以原生 `div` 四重軸鎖呈現全部 20 筆結果（Chrome 實測 `clientHeight: 300, scrollHeight: 1459` 捲動到底）。

### 🟢 Stage B（`13:14 ~ 14:25`）：全站 Bug Hunter 健檢 T1–T9 全棧修復 (`6c714e2`, `96d5fe2`, `0445f1a`)
- **T1 通知中心與推播閉環**：因 Supabase RLS 收緊 `auth.uid()` 致前端直連通知表自 `2026-09-20` 起已讀歸零，改為 FastAPI JWT 代理讀寫（[notifications.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/notifications.py) 含 `_validate_https_push_endpoint` SSRF IPv4/IPv6/內網防護與 `run_in_threadpool`）＋ [notification-bell.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/notifications/notification-bell.tsx) 未登入守衛/樂觀回滾 ＋ Edge Functions [notify-event](file:///d:/Project/tabiji/travel-pwa/supabase/functions/notify-event/index.ts) / [notify-countdown](file:///d:/Project/tabiji/travel-pwa/supabase/functions/notify-countdown/index.ts) / [notify-broadcast](file:///d:/Project/tabiji/travel-pwa/supabase/functions/notify-broadcast/index.ts) 無前綴主題 (`user-notif:<uid>`, `user-notif:broadcast`) 不透明 Broadcast 訊號（2000ms `AbortController` 隔離）。
- **T2 多人協同 Broadcast 全覆蓋**：移除 [useTripRealtime.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/hooks/useTripRealtime.ts) 被 RLS 靜默丟棄之 3 組 `postgres_changes` 監聽，於活動建立、非 `skipRevalidation` 編輯、`UndoDeleteManager` 刪除沖刷（經 `activeTripIdRef`）、設定/封蓋等全部異動點補齊 `broadcastTripEvent`。
- **T3 & T4 地圖搜尋 Edge 快取 `v=2` 與 L1 防閃爍**：[worker.js](file:///d:/Project/tabiji/travel-pwa/cloudflare/edge-shield/worker.js) Geocode 快取鍵加入 `v=2`、量化 `bbox`/2 位小數 `lat`/`lng`、`locale`、`trip`、`limit` (`1..50`)，刻意排除高噪 `zoom` 並對 `X-Gemini-Key`/`X-Gemini-API-Key` 強制 `BYPASS`；[day-map.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/day-map.tsx) 與 [FullscreenMapModal.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/FullscreenMapModal.tsx) 於 debounce 與異常處保留 `localMapped`。
- **T5 時光膠囊與原子天數平移**：保留 `Day 0` 並修正 [CapsuleUnveilingCeremony.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/CapsuleUnveilingCeremony.tsx) 天數重設，[capsules.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/capsules.py) `total_members` 計入 `trip_members ∪ {created_by}`，[trips.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/trips.py) 與 Postgres RPC `shift_trip_capsules`（`+10000` 二階段偏移）原子平移天數不碰撞唯一索引且保留 `day_number > 0`。
- **T6 Activity Schema 對齊**：新增 `itinerary_items.address` 欄位、前後端序列化及補齊 `CreateItemParams.website_link`（[schemas.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/schemas.ts)）。
- **T7 無 Key POI 免費降級與後端強固**：[poi.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/poi.py) 無 API Key 時回傳 `200 PARTIAL_SUCCESS` (`ai_key_missing: true`, `NO_API_KEY`) 且嚴禁寫入 `POI_ENRICH_CACHE`；[POIDetailDrawer.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/POIDetailDrawer.tsx) 增加 `rating > 0` 守衛防印 `"0"`；[users.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/users.py) 以 `.limit(1)` 消除 `.single()` `PGRST116`；[agents.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/agents.py) 落地 Supabase `agent_fallback_tasks`（RLS + `REVOKE ALL` + SHA-256 `key_hash` 與 `hmac.compare_digest`），並以 [conftest.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/conftest.py) 隔離測試防寫入真庫。
- **T8 街景引用計數與破圖保護**：[20261119_bug_hunter_remediation_schema.sql](file:///d:/Project/tabiji/travel-pwa/supabase/migrations/20261119_bug_hunter_remediation_schema.sql) 建立單一表達式索引 `idx_itinerary_items_mly_ref_id`，以 `to_jsonb(OLD) #- '{preview_metadata,mapillary_thumb}'` 執行跨表 (`itinerary_items` ∪ `trip_capsule_entries`) 引用計數，0 引用才清理 Cloudinary；[timeline-card.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/timeline-card.tsx) 與 [zoomable-image.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/ui/zoomable-image.tsx) 補齊 404 圖片優雅降級。
- **T9 AI 行程真串流進度、分享頁快取與住宿欄位**：[share/[shareCode]/page.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/app/share/%5BshareCode%5D/page.tsx) 改為 `revalidate: 60`；[pdf-generator.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/pdf-generator.ts) 支援 `check_in ?? checkIn`；[model_manager.py](file:///d:/Project/tabiji/travel-pwa/backend/services/model_manager.py) 與 [ai.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py) 實作 `call_extraction_stream`（含 `_is_mocked` 既有單測相容橋接），以有限線性正則偵測 `"day_number"` / 思考標籤即時推進 `15% -> 20..24% -> 25..68% -> 75% -> 90% -> complete`；[api.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/api.ts) 逐行濾除 `: ` SSE 註解避免心跳包吞沒 `event:` 區塊。

---

## 2. 架構決策、踩坑記錄與技術債盤點

### 🏛️ Architecture Decisions
- **AD-228（雙網域指紋鎖定取代全域時間冷卻 — 更新既有 `10000ms` 舊規）**：以不可碰撞 JSON 序列化憑證指紋（`lastFailedExchangeFingerprint`）+ `isReauthDismissedInMemory` 鎖定永久性 401 重試與彈窗復發，指紋一有變動即刻解鎖；保留 `lastRestoredAt < 5000ms` 僅用於吸收剛恢復瞬間之前置在途 401。
- **AD-229（Hedged Multi-Provider POI Fallback 架構）**：外部免費地圖圖資具備高不可靠性，`/api/poi/nearby` 以主供應商 2.5s budget 並行對接 Photon / Wikipedia / Nominatim，遇零結果擴大都會圈半徑並短期快取。
- **AD-230（Opaque Realtime Broadcast 全面接管失效監聽）**：Supabase JS SDK 預設為 `channel.topic` 加上 `realtime:` 前綴，因此從 Edge Function 透過 REST API 推播廣播時必須傳送**無 `realtime:` 前綴**之主題名稱（`user-notif:<uid>`）；全面以不透明 Broadcast 訊號 + JWT API 拉取替代需開放 `anon` 資料表權限之 `postgres_changes`。
- **AD-231（Edge Geocode Cache v2 降維去噪 + 個人化繞過契約）**：排除高噪 `zoom`、對 `lat`/`lng`/`bbox` 兩位小數網格量化、嚴格分離 `locale`/`trip`/`limit`，並於含使用者 Gemini API Key 標頭時同時繞過快取讀取與寫入。
- **AD-232（單一表達式索引引用計數刪除防線）**：禁止在 Postgres Trigger 使用無法命中索引之 `LIKE '%...' OR ...` 掃表，統一收斂為精確 JSON 路徑表達式索引搭配 `to_jsonb(OLD) #- ...` 等值比對。
- **AD-233（Atomic Offset Day Shifting for Unique-Constrained Capsules）**：有 `(itinerary_id, day_number)` 複合唯一約束的時光膠囊表做平移或重排前，必先執行 `+10000` 臨時正向偏移二階段更新再落目標值，且嚴格限定 `day_number > 0` 以保護 `Day 0` 總結膠囊。
- **AD-234（SSE Strategy A Streaming + Test-Seam `_is_mocked` Compatibility）**：串流改造核心函式若既有用例已直接 `patch` 舊單次介面，需顯式檢測 `_is_mocked` 維持舊測契約；SSE 前端解析器不得因單一區塊首行為 `: keep-alive` 註解即丟棄整段 `data:` 事件，必須以行級過濾註解行。

### 🔴 Technical Debt
- **FP/DEBT Resolved in `2026-11-19`**: 雙網域 401 風暴、`edge-shield`/`poi-service` 公網後門、`cloudinary-test` 暴露、周邊 POI 斷鏈與 20 筆滾動截斷、通知與即時協同 RLS 失效、街景共用誤刪與 AI 15% 卡住問題全數 `[RESOLVED in be7a32c..0445f1a]`。
- **DEBT-PUSH-RLS-01（Open）**：`T1` 已啟用經 JWT 與 SSRF 驗證之 FastAPI `/api/push/subscribe` 並保留舊版 `push_subscriptions` `anon` RLS 作零中斷過渡；待觀察線上去重與訂閱穩定後即可收回 `anon` 寫入策略。
- **DEBT-BUGHUNTER-MINOR-01（Open — Explicit Non-Goals & 4 項線上待實機雙人壓測項目）**：
  1. 本輪人類裁決暫不納入之次要瑕疵：`/api/ledger/{code}` 非 UUID 回 500、`PoiPoolMap` inline style chip 樣式、對帳分享頁底部「了解更多」空綁定、`manifest.json` `/?action=new-trip` 未處理參數。
  2. 本輪僅由單元/契約測試覆蓋、尚未於線上進行雙帳號併發實機壓測之 4 項情境：雙瀏覽器分頁 `T2` 即時同步重繪、瀏覽器 Web Push 系統彈窗與實際推播抵達、多成員已結束行程實機 `Day 0` 膠囊揭曉、[notify-event/index.ts](file:///d:/Project/tabiji/travel-pwa/supabase/functions/notify-event/index.ts) Sentinel CLI 90s 逾時復驗。

### 🛡️ Failed Paths
- **FP-099（雙層缺陷遮蔽效應 — Two-Layer Bug Masking）**：`2026-10-21` `edge-shield` 貪婪正則錯誤攔截 `www.tabijiapp.com` `/api/poi/nearby` 回 401/404，整整掩蓋了 `2026-10-25` 因跳過 OpenTripMap 後 `/api/poi/nearby` 單依賴 Overpass 且未接備援的事實；僅修復外層路由後剛好撞上 Overpass 大當機才揭出第二層單點故障。另有 **Edge Masking**：自訂網域 Worker 把原生 Vercel 路由 (`/api/cloudinary-test`) 蓋成 404，讓人誤以為原生站點也已安全關閉。
- **FP-100（Radix `<ScrollArea>` 無固定高度僅設 `max-h` 導致捲動癱瘓與硬切 10 筆陷阱）**：父容器僅宣告 `max-h-[300px]` + `overflow-hidden` 時，Radix Viewport 的 `height: 100%` 會退化成 `height: auto` 撐開卻不生捲軸，隨後被外層 `overflow-hidden` 物理截斷剩 4 張卡片；且循環同時殘留 `.slice(0, 10)`。凡限定最大高度且內容動態長短不一的列表應改用原生彈性/最大高度捲動容器配四重軸向鎖定。
- **FP-101（Supabase RLS `auth.uid()` 收緊導致無 Supabase Auth 前端與 `postgres_changes` 靜默斷流）**：前端未登入 Supabase Auth 而僅帶 `anon`/Publishable Key，RLS 升級強制檢查 `auth.uid()` 後 PostgREST 查詢不報 401 而是靜默回傳 `[]`、`postgres_changes` 靜默失收推播，造成通知 center 與未接廣播發射器之活動編修同時失效而不噴錯。
- **FP-102（Supabase REST Broadcast 主題誤加 `realtime:` 前綴陷阱）**：`@supabase/supabase-js` `channel(topic)` 底層會自動前綴 `realtime:`，若伺服器 REST Broadcast 呼叫再手動補上 `realtime:` 前綴，會導致前端監聽與後端廣播主題錯位完全收不到訊號；REST 端必須傳純淨無前綴 topic 名稱。
- **FP-103（JSX 數值 0 Falsy 渲染陷阱 & `LIKE '%...'` 觸發器全表掃描陷阱）**：`{aiData.rating && ...}` 在後端無 Key 降級回傳 `rating: 0` 時會在介面印出多餘字元 `"0"`，數值判斷必須改用 `(rating ?? 0) > 0`；SQL Trigger `EXISTS` 若混用 `LIKE '%...' OR` 會令 B-Tree 索引徹底失效。
- **FP-104（SSE `: keep-alive` 與 `event:` 同區塊導致事件整包丟失 & `conftest` 直連真庫汙染陷阱）**：前端 SSE parser 若以 `if (block.trim().startsWith(':')) continue` 檢查整個 `\n\n` 分隔區塊，會將與 `: keep-alive` 相鄰送達的真實 `data:` 事件一併拋棄；後端測試若未在 `conftest.py` 攔截 `_resolve_supabase` fallback，執行測試會將假任務列寫入線上真實 Supabase。

### 🎯 Next Steps
- 依排程於實機雙瀏覽器驗證 `T2` Broadcast 即時重繪、`Day 0` 膠囊揭曉與系統 Web Push 送達，並於 `2027-02-16` 後排程清理 GCP `LEGACY_SESSION_SECRET_KEY`。

---

## 🧬 Machine-Executable Invariant Rules

```json
[
  {
    "domain": "state_cache",
    "type": "INVARIANT_RULE",
    "id": "INV-STATE-FINGERPRINT-LOCK-01",
    "title": "認證失敗指紋鎖與永久彈窗靜默取代短時間冷卻法 (AD-228)",
    "content": "當 SWR refreshInterval (15s) 大於冷卻時間時，10s/5s 時間冷卻會演變為無限 401 風暴。ensureValidSession 必須改採 JSON 防碰撞憑證指紋鎖 (lastFailedExchangeFingerprint)：相同憑證指紋於本頁內永久阻斷重試，憑證一更新立即解鎖；dismissReauthPrompt 以 isReauthDismissedInMemory 在當前頁面維持離線靜默（僅保留 lastRestoredAt < 5000ms 吸收恢復前在途請求）；useExpenses/useTripCapsules/usePoiPool 一律停試 401/403/404。"
  },
  {
    "domain": "state_cache",
    "type": "FAILED_PATH",
    "id": "FP-102",
    "title": "Supabase RLS 靜默回空與 REST Broadcast 重複加 realtime: 前綴失聯陷阱 (FP-101, FP-102)",
    "content": "未跑 Supabase Auth 僅用 Publishable Key 時，RLS 綁定 auth.uid() 會使查詢靜默回傳 [] 且 postgres_changes 靜默丟棄事件；實作即時同步應全數改為不透明 Broadcast 訊號搭配認證後端 API 拉取。透過 Supabase Realtime REST API 發送廣播時，topic 嚴禁手動加上 'realtime:' 前綴（客戶端 SDK 已自動附加），否則雙邊主題永遠無法匹配。"
  },
  {
    "domain": "state_cache",
    "type": "FAILED_PATH",
    "id": "FP-104",
    "title": "SSE 註解心跳行誤殺整段資料區塊與 Stream Mock 契約破壞陷阱 (FP-104)",
    "content": "frontend/lib/api.ts 解析 SSE \\n\\n 區塊時，嚴禁只判斷 trimmed.startsWith(':') 就 continue 整段區塊（會把同區塊內的 event:/data: 一併吞掉），必須先以 line => !line.startsWith(':') 逐行剔除註解行。後端將核心端點重構為 call_extraction_stream 時，必須加入 _is_mocked 相容檢查，否則既有用例 mock 舊 call_extraction 將被靜默繞過。"
  },
  {
    "domain": "ios_ui",
    "type": "FAILED_PATH",
    "id": "FP-100",
    "title": "Radix ScrollArea 僅設 max-h 無固定 height 導致捲動截斷與 JSX 數值 0 渲染陷阱 (FP-100, FP-103)",
    "content": "Radix UI ScrollArea 在外層僅設 max-h-[...] 而無明確固定 height 時，內層 Viewport height:100% 會退化成 auto，導致無捲動軸且超出部分被外層 overflow-hidden 截斷（實測 20 筆僅剩 4 筆）。動態高度上限清單應改用原生 div 配合 max-h-[...] 與四重軸向鎖定。另 JSX 條件渲染評分數值嚴禁寫 {rating && ...}（0 會印出字元 '0'），須顯式判別 (rating ?? 0) > 0。"
  },
  {
    "domain": "map_webgl",
    "type": "INVARIANT_RULE",
    "id": "INV-MAP-L1-HEDGED-POI-01",
    "title": "地圖搜尋 L1 本地結果保底與多供應商競速 POI 備援契約 (AD-229)",
    "content": "DayMap 與 FullscreenMapModal 在觸發 L2 雲端 debounce 請求當下及 catch 失敗回退時，必須保留並回寫本地秒回清單 localMapped，嚴禁執行 setResults([]) 洗白已有結果。後端 /api/poi/nearby 禁止單依賴 Overpass，必須以主供應商短時限並行 Photon / Wikipedia / Nominatim 競速保底。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BE-CAPSULE-OFFSET-AND-MLY-RC-01",
    "title": "膠囊二階段正數位移、無 Key Wiki 保底與單索引街景引用計數契約 (AD-232, AD-233)",
    "content": "對具 (itinerary_id, day_number) 唯一鍵之時光膠囊平移天數，必須經 Postgres 原子 RPC (+10000 臨時偏移再寫目標值) 且限定 day_number > 0 保護 Day 0。webhook_cleanup_cloudinary 必須於單一表達式索引 idx_itinerary_items_mly_ref_id 下執行 to_jsonb(OLD) #- '{preview_metadata,mapillary_thumb}' 跨表引用計數（嚴禁 LIKE '%...' Seq Scan）。/api/poi/ai-enrich 無 API Key 時回傳 200 PARTIAL_SUCCESS（禁用快取寫入），且 agents Fallback 表須經 RLS + SHA-256 key_hash + conftest.py 測試隔離。"
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-099",
    "title": "雙層缺陷遮蔽效應與雙網域 Edge Shield 暴露假象陷阱 (FP-099)",
    "content": "主網域邊緣閘道（Edge Shield）轉發錯誤或覆寫路徑（例如 www 回傳 404 或 401）常完全掩蓋下層應用漏洞：包含原生網域 (.vercel.app) /api/cloudinary-test 回傳 200 暴露資訊、或外部圖資未接備援之單點故障，及內部 Cloudflare Service Binding Worker 未明確設置 workers_dev: false / preview_urls: false 留下的 BOLA 公網後門。安全驗證必須穿透所有對外網域（含 .vercel.app 與 *.workers.dev）逐層實測，且 Edge Geocode Cache v2 須隔離 locale/座標並繞過帶 AI Key 請求。"
  }
]
```
