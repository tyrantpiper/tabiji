# 📅 Daily Report - 2026-11-25 (統一 AI 輸入列、精算器 Bento、5 分頁智慧看板、多人協作零外洩隱私防線與 Zero-Redis Pure Postgres 17 原子併發架構)

> **時間範圍**: `2026-11-23 20:02 ~ 2026-11-25 12:35` (UTC+8)
> **納入 Commits (`781918e..57855c0`, 5 Commits, `44 files changed, 17,119 insertions(+), 1,722 deletions(-)`)**:
> - `8322671` (`2026-11-23 20:02:07`): `feat(agents): isolate pwa-idea-to-spec skill in workspace` (`4 files, +129/-2`)
> - `6a4af9f` (`2026-11-24 22:48:14`): `feat(ui,dashboard): unify chat composer, tax bento, and daily smart dashboard` (`23 files, +10,521/-1,478`)
> - `7d9b996` (`2026-11-25 00:09:51`): `fix(collab,privacy,gdpr): enforce privacy isolation, safe merge & wrap` (`9 files, +1,143/-137`)
> - `ff6909a` (`2026-11-25 00:57:05`): `fix(privacy,collab): block card creator forgery/hijack and private item BOLA` (`7 files, +368/-55`)
> - `57855c0` (`2026-11-25 12:20:18`): `feat(concurrency,auth): add Postgres atomic content RPCs and fix card JWT/info rollback` (`17 files, +5,043/-135`)
> **全棧 Quality Gate 實測結果**:
> - Neural Seam Invariant Harness (`scripts/neural_seam_harness.py`): **`10/10` Intact** (`0` Sequelae, `EXIT 0`)
> - Security Ledger (`scripts/validate_security_ledger.py`): **`454 targets` (`214 remediated, 53 verified/unresolved, 187 dismissed/safe`)**（`439 -> 444 -> 454`, `+15 targets`, `0` 歷史 ID 遺失, `EXIT 0`）
> - Security Sentinel (`runner.py --mode fast` 物理隔離 `agy.exe --sandbox` ✕ Worktree Spiking Red→Green PoC ✕ Mantis Block G):
>   - 2026-11-24 當日智慧看板 5 分頁審查：**`5/5 DISMISSED`**（[`security_sentinel_report_2026-11-24_daily_dashboard_cards.md`](file:///d:/Project/tabiji/travel-pwa/docs/security/reports/2026-11/security_sentinel_report_2026-11-24_daily_dashboard_cards.md)）
>   - 2026-11-25 Pure Postgres 原子 RPC 與前端 P0 審查：**`10/10 DISMISSED`**（[`security_sentinel_report_2026-11-25_atomic_trip_content_rpc.md`](file:///d:/Project/tabiji/travel-pwa/docs/security/reports/2026-11/security_sentinel_report_2026-11-25_atomic_trip_content_rpc.md)）
> - Backend Pytest (`pytest -q`): **`803 passed, 5 skipped, 0 failed`**（基線 `785` ➔ `+18` 新增測試含協作隱私／GDPR 與 11 項原子 RPC 哨兵, `EXIT 0`）
> - Frontend TypeScript (`npx tsc --noEmit`) & ESLint (`npm run lint`): **`0 errors, 0 warnings`** (`EXIT 0`)
> - Frontend Vitest (`npx vitest run`): **`131 files, 1,224 passed | 4 skipped (1,228)`**（基線 `127 files / 1,168` ➔ `+4 files / +56 tests`, `EXIT 0`）
> - Frontend Production Build (`npx next build`, Turbopack 16.4.5): **`11/11` static pages** (`EXIT 0`)
> - Live Postgres 17.6 Migration & Transaction Verification: `20261125_atomic_trip_content_rpcs.sql` 已直上正式 Supabase Postgres 17.6，`BEGIN; ... ROLLBACK;` 實測 **`18/18` 斷言全綠**（涵蓋空 `{}` 行程、非布林毒卡、重複卡 ID、日期保護、外鍵共存 `FOR NO KEY UPDATE`、`cover_image` 單欄 no-op 觸發器守衛）。
> - Live 5-Cloud Production & `@mcp:chrome` E2E (`57855c0` @ `https://www.tabijiapp.com`):
>   - **Cloud Run**: `antigravity-backend-00219-ppk`（100% 流量），12 條真併發 burst 寫入 **`12/12 HTTP 200`** 零 `StreamIDTooLowError`、零丟失。
>   - **Vercel**: `dpl_zZeziLgntN6ZSTSuN4RHPiBBTb3y`（`READY / PROMOTED`），實機 Chrome 獨立分頁驗證信用卡新增 `PATCH /api/trips/{id}/info` `hasAuth: true` `200` 並持久化入庫。
>   - **Supabase / Cloudinary / Cloudflare**: 15 次純 `content` 更新期間 `cleanup-cloudinary` 呼叫次數 **`0`**（Edge Function 雜訊完全歸零）；測試帳號經 GDPR 清理確認 `rem_users=0, rem_trips=0, rem_members=0`，`404/401` 零殘留。

---

## 1. 工程與檔案異動清單（2026-11-23 晚 ~ 2026-11-25 午）

- **Workspace Agent 技能隔離（`8322671`）**:
  - [.agents/skills/pwa-idea-to-spec/SKILL.md](file:///d:/Project/tabiji/travel-pwa/.agents/skills/pwa-idea-to-spec/SKILL.md) (`+126`)、[.gitignore](file:///d:/Project/tabiji/travel-pwa/.gitignore) (`+1`)、[.agents/domains/devops_security.md](file:///d:/Project/tabiji/travel-pwa/.agents/domains/devops_security.md): 將 Tabidachi PWA 專屬 2.1.0 Dual-Track Spec Engine 獨立納管於專案版控。
- **前端高階 UI 重塑與安全網加固（`6a4af9f`, 23 檔）**:
  - **統一 AI 輸入列**：[ChatComposer.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/chat/ChatComposer.tsx) (`+645`)、[chat-widget.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/chat-widget.tsx) (`+235/-206`)、[chat.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/i18n/chat.ts) (`+50`)、[chat-composer.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/chat-composer.test.tsx) (`+866`)。雙層和紙白／深翠黑統一卡片、`+` 旋轉 Radix Popover 三合一選單（上傳圖片／拍照即問／深度研究切換）、移除 `#E56E25` 橘色偏、行動端 Auto-Dock 自動收合 Popover、全螢幕展開隱藏 `#tour-ai-bot`、深度研究 `/cancel` ＋ `AbortSignal` 同步與失敗防穿透 `streamChat`、圖片壓縮世代鎖。
  - **精算器行動端 Bento ✕ 5 欄純圖示底抽膠囊**：[GlobalTaxActuary.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/tools/GlobalTaxActuary.tsx) (`+460/-259`)、[IOSBottomSheet.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/IOSBottomSheet.tsx) (`+142/-36`)、[session-reauth-modal.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/auth/session-reauth-modal.tsx) (`+2/-1`)、[global-tax-actuary-layout.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/global-tax-actuary-layout.test.tsx) (`+285`)、[itinerary-dashboard-layout.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/itinerary-dashboard-layout.test.tsx) (`+126/-10`)。320px 2 層信用卡 Bento、免稅門檻 `Math.min(99, ...)` 防 `未達門檻 (100%)` 矛盾、0% VAT 隱藏進度條、44px 計算機按鍵、`grid-cols-5` 零文字純圖示膠囊、`z-115` 蓋過待機 AI 圓球 (`z-110`) 且遜於 `SessionReauthModal` (`z-165`)。
  - **5 分頁當日智慧看板大統一與指標解析**：[EditableDailyTips.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/EditableDailyTips.tsx)、[EditableDailyChecklist.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/EditableDailyChecklist.tsx)、[EditableDailyAIReview.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/EditableDailyAIReview.tsx)、[itinerary-metrics.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/itinerary-metrics.ts) (`parseCostAmount`)、[itinerary-view.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/itinerary-view.tsx)、[daily-dashboard-cards.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/daily-dashboard-cards.test.tsx) (`+1,277`)、[itinerary-dashboard-metrics.test.ts](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/itinerary-dashboard-metrics.test.ts) (`+145`)。和紙統一視覺系統、三層 `Escape` 隔離、`Intl.Segmenter` 首字素圖示器、`CurrencyPillSelector` 純橫向捲動與自訂幣別保留、`hasPendingDebounceRef` ＋ `cancelPendingDebounce()` 防抖守恆、同級 `<button>` 解耦、全路徑 `useRef` 單幀互斥鎖與行程預設幣別內外同步。
- **線上五雲紅隊實測捕獲之協作隱私、BOLA、GDPR 與 Tailwind v4 修正（`7d9b996` & `ff6909a`）**:
  - [backend/routers/trips.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/trips.py)、[backend/routers/gdpr.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/gdpr.py)、[test_collab_privacy_and_gdpr_sentinel.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_collab_privacy_and_gdpr_sentinel.py) (`+649`): 統一三支查詢端點（`GET /api/trips`、`/itinerary/latest`、`/{id}`）私密過濾與 `mem_*` 脫敏；修補 `PATCH /day-data` 與 `PATCH /info` 保留他方隱藏私密項與信用卡五不變量歸屬防奪權／防偷轉私卡／隱藏 ID 碰撞重鑄；封堵私密 `itinerary_items` 強制公開／竄改／刪除／重排 BOLA；GDPR 回收孤兒 `created_by="SYSTEM"` 範例行程與 Cloudinary `photo_url`。
  - [useTripRealtime.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/hooks/useTripRealtime.ts)、[ActivityEditModal.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/ActivityEditModal.tsx)、[itinerary-view.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/itinerary-view.tsx)、[EditableDailyChecklist.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/EditableDailyChecklist.tsx)、[EditableDailyTips.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/EditableDailyTips.tsx)、[EditableDailyAIReview.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/EditableDailyAIReview.tsx): 落盤後才發送並以 `stripPrivateForBroadcast()` 淨化 WebSocket、接收端 `mergeIncomingWithLocalPrivate(allowOwnerlessIncoming=false)`、`useMemo` 穩定陣列參照、Day 1 樂觀歸零 `day_checklists[0]`、協作者隱藏私密景點切換鈕、全面以 Tailwind v4 原生 `wrap-anywhere` 取代 `wrap-break-word [overflow-wrap:anywhere]`。
- **Zero-Redis Pure Postgres 17 原子併發 RPC 與前端 P0 信用卡／飯店回滾修復（`57855c0`, 17 檔）**:
  - [20261125_atomic_trip_content_rpcs.sql](file:///d:/Project/tabiji/travel-pwa/supabase/migrations/20261125_atomic_trip_content_rpcs.sql) (`+875`): 建立 `patch_trip_day_data_atomic`、`patch_trip_info_atomic`、`merge_trip_import_content_atomic`（`FOR NO KEY UPDATE` ＋ `lock_timeout=3000ms`／`statement_timeout=8000ms` ＋頂層 `|| jsonb_build_object(...)`），移除舊 `public.update_trip_credit_cards`，並為 `webhook_cleanup_cloudinary` 補上 `cover_image` 單欄 no-op 守衛。
  - [backend/utils/deps.py](file:///d:/Project/tabiji/travel-pwa/backend/utils/deps.py)、[backend/main.py](file:///d:/Project/tabiji/travel-pwa/backend/main.py)、[backend/routers/trips.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/trips.py)、[backend/routers/ai.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py)、[test_atomic_trip_content_rpc_sentinel.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_atomic_trip_content_rpc_sentinel.py) (`+1,074`): 導入 `create_threadsafe_supabase_client()`（`httpx.Client(http2=False)` ＋ `.postgrest` 預熱）、`UUID_V4_REGEX.fullmatch`、`NonCallableMock` 守衛、`ENABLE_ATOMIC_TRIP_RPC` 熔斷開關、`run_in_threadpool`、`55P03/40P01 -> 409` 與 `PGRST202` 安全降級、`/info` 500 脫敏。
  - [api.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/api.ts)、[sync-hooks.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/sync-hooks.ts)、[tools-view.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/tools-view.tsx)、[info-view.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/info-view.tsx)、[trip-info-cards-atomic-sentinel.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/trip-info-cards-atomic-sentinel.test.tsx) (`+570`): `tripsApi.updateInfo` 全面走 `offlineFetch`（JWT + 401 換票 + `Idempotency-Key` + 離線佇列）；根治線上 `tools-view.tsx` 信用卡寫入 100% 401 靜默蒸發；補齊 `sync-hooks.ts` 線上分支 JWT 與 401 重試；修正 `info-view.tsx` `handleSaveInner` 失敗回滾保留 `tempHotel` 草稿與 `lastSyncedTripRef` 防離線存檔反寫覆蓋。

---

## 2. 本日實戰事件、架構決策與經驗沉澱

### 🟢 Features & Fixes
- **三大高頻介面和紙視覺與行動端人體工學大統一**：AI 聊天輸入列、外幣免稅精算器、5 分頁當日智慧看板全部對齊 320px 零溢位、深淺雙色、高對比與 WAI-ARIA 鍵盤／觸控體驗。
- **線上雙帳號紅隊實測 7 連殺封堵協作隱私與資料遺失**：透過真實 `https://www.tabijiapp.com` 房主 A ✕ 旅伴 B 互測與對抗攻擊，接連揪出並根治「同伴存檔抹除私密項」「WebSocket 明文廣播私密 UUID」「信用卡歸屬偽造／奪權／偷轉私卡」「私密景點 BOLA 強制公開／刪除」「GDPR 殘留孤兒系統行程」等線上真實缺陷。
- **Zero-Redis Pure Postgres 17 原子化並根治線上信用卡 401 靜默丟失**：對標 Supabase／Vercel／Cloudflare 業界實踐，以零新增基礎設施成本解決 Cloud Run 多實例 JSONB 併發覆蓋（12 條真併發 12/12 `200` 零遺失），同步抓出並根除線上 `tools-view.tsx` 信用卡寫入 100% `401` 靜默清空的 P0 缺陷與 `cleanup-cloudinary` 無效觸發雜訊。
- **開發環境雜訊精準鑑識（無需改碼）**：確認本機 `GET /.well-known/appspecific/com.chrome.devtools.json 404` 為 Chrome 135+ DevTools 工作區探測經 `next.config.mjs` 代理所致；瞬間雙次 `GET /api/auth/credential 401` 後自癒為本機舊 token 過期觸發 `reactStrictMode` 雙掛載並自動清退換票（屬自癒正常行為）；659 筆短暫 VS Code Problems 確認全數源自已註銷但磁碟尚留存之 `.worktrees/review-sandbox` 殘留目錄。

### 🏛️ Architecture Decisions
- **AD-249（ChatComposer 雙區卡片、精算器 320px Bento、5 欄純圖示底抽膠囊與三層 Escape/z-index 隔離契約）**：統一 AI 輸入列為雙區卡片＋`+` Radix Popover（Auto-Dock 關閉、全螢幕隱藏 `#tour-ai-bot`、壓縮世代鎖、深度研究 `/cancel` + `AbortSignal` 隔離）；精算器升級 320px 2 層 Bento＋寬容數字解析 (`parseCostAmount`)＋門檻 `Math.min(99, ...)`＋0% VAT 隱藏進度條；`IOSBottomSheet` 採 `grid-cols-5` 純圖示膠囊與 `z-115`（介於 `#tour-ai-bot` `z-110` 與 `SessionReauthModal` `z-165`），並落實 Popover → 內嵌表單 → 外層底抽三層 `Escape` 隔離與 `Intl.Segmenter` 字素擷取。
- **AD-250（零外洩後落盤即時廣播、本地私密保留合併、防抖計數守恆與 Day 0/1 清單同步契約）**：`broadcastTripEvent` 嚴格置於後端落盤成功後且經 `stripPrivateForBroadcast()` 淨化；接收端採 `mergeIncomingWithLocalPrivate(allowOwnerlessIncoming=false)` 保護本端私密項；父層以 `useMemo` 穩定陣列參照並對 Day 1 樂觀歸零 `day_checklists[0]`；500ms 勾選防抖以 `hasPendingDebounceRef` 守恆計數、`committedItemsRef` 基準回滾，所有立即寫入前先 `cancelPendingDebounce()`。
- **AD-251（多端點協作私密隔離、信用卡五不變量歸屬防奪權、私密景點 BOLA 與孤兒系統行程 GDPR 契約）**：三支查詢端點共用 `_is_trip_creator(allow_legacy_user_id=False)`、`_filter_private_day_items` 與 `_filter_private_cards`（`mem_*` 脫敏）；`PATCH /day-data` 與 `/info` 保留他方私密項、綁定 JWT `user_id`、強制布林正規化並捍衛信用卡歸屬五不變量；私密 `itinerary_items` 全 CRUD/重排/匯入限房主並隱藏協作者介面切換鈕；GDPR 同步回收獨居 `SYSTEM` 孤兒行程。
- **AD-253（Zero-Redis Pure Postgres 原子 RPC、HTTP/1.1 執行緒安全 Supabase 連線池與前端 Info/Card 離線回滾契約）**：*(已隨 `57855c0` 預先固化於 `.agents/domains/backend_concurrency.md`，本日報統一編號為 `AD-253` 消除與 `map_webgl.md` `AD-246` 之撞號)*。以 3 支 `service_role` 專屬 Postgres 17 `FOR NO KEY UPDATE` RPC ＋ `httpx.Client(http2=False)` 連線池 ＋ `tripsApi.updateInfo` (`offlineFetch`) ＋ `info-view.tsx` 顯式快照回滾與 `lastSyncedTripRef` 達成端到端零競態、零靜默丟失。

### 🔴 Technical Debt
- **DEBT-AUTH-CREDENTIAL-DEDUP-01（Low — 本機微觀測）**：`fetchLatestRecoveryKey()` 目前無 single-flight Promise 去重，於開發模式 `reactStrictMode` 雙掛載且 token 剛失效時會瞬間連打 2 次 `GET /api/auth/credential`（皆安全自癒，無功能影響）；後續可補上模組級進行中 Promise 去重。
- **DEBT-ATOMIC-PHASE2-TIER3-01（Low — 低頻跨表寫入）**：Tier 3 跨表操作（行程建立／刪除／成員調整）與其餘路由少數 `detail=str(e)` 尚未納入原子 RPC／統一脫敏；屬低頻寫入，視後續規模演進評估。
- **DEBT-CLOUDINARY-HOTEL-CLEANUP-01（Low — 既有 Edge Function 邊界）**：線上 `cleanup-cloudinary` v8 僅比對 `itineraries.cover_image` 而未掃描 `content->'hotel_info'` 圖片（本次 trigger guard 刻意對齊線上 v8 不破壞既有行為）；若未來實作飯店圖片自動回收，須先升級 Edge Function 再同步更新 trigger 條件。
- **DEBT-WORKTREE-DIR-CLEANUP-01（Chore — 本機磁碟衛生）**：`.worktrees/review-sandbox` 與 `.worktrees/sentinel-581fb847` 已自 `git worktree list` 註銷且被 `.gitignore` 忽略，但實體目錄仍殘留於磁碟；建議刪除並於 `.vscode/settings.json` 排除 `.worktrees/**` 徹底根絕 VS Code 掃描雜訊。
- **DEBT-DEPENDABOT-2MOD-01（Low — 既有依賴）**：GitHub Dependabot 仍有 2 項既有 moderate 告警（與本次無關），及實機 iPhone Safari `<input capture="environment">`／軟鍵盤慣性目視覆驗待有實機時順帶抽檢。

### 🛡️ Failed Paths
- **FP-118（Tailwind CSS v4 `wrap-break-word` 壓過 `[overflow-wrap:anywhere]` 級聯反轉陷阱）**：在 `tailwindcss@4.3.5` 中，`@layer utilities` 產出順序將 `.\[overflow-wrap\:anywhere\]` 排在 `.wrap-break-word` 之前，且 `tailwind-merge` 不會合併任意屬性，導致兩者並寫時反被 `break-word` 蓋回並冒出 18 個 IDE `cssConflict` 警告；必須單獨使用 Tailwind v4 原生 **`wrap-anywhere`**。
- **FP-119（Radix `onEscapeKeyDown` 原生事件簽名誤判與 `scrollIntoView` 垂直跳頁陷阱）**：`@radix-ui/react-dismissable-layer` 傳給 `onEscapeKeyDown` 的是原生 `KeyboardEvent` 而非 `CustomEvent`（讀 `e.detail?.originalEvent` 恆為 `undefined` 會使 IME 防誤關失效）；在長 `IOSBottomSheet` 內呼叫 `el.scrollIntoView({ inline: "nearest" })` 會連帶把父層垂直捲到最底（`scrollTop > 2000px`），橫向膠囊必須以 `getBoundingClientRect()` 直接計算並設定 `container.scrollLeft`。
- **FP-120（SWR v2 `dequal` 參照穩定性導致失敗不回滾與 `useEffect([..., isEditing])` 覆蓋離線編輯陷阱）**：突變失敗時伺服器資料未變，SWR v2 `dequal` 維持同一個 `activeTripData` 物件參照，導致 `useEffect([activeTripData])` 根本不會重跑，單靠 `reloadTripDetail()` 無法回滾樂觀 UI；反過來將 `isEditing`/`innerEditing` 放進 `useEffect` 若未比對 `lastSyncedTripRef`，離線存檔退出編輯態時會被舊快取反寫覆蓋；且 200 寫入後之 `reloadTripDetail()`/`tripMutate()` 必須 `.catch(() => {})` 隔離重抓抖動。
- **FP-121（`httpcore 1.0.9` HTTP/2 無鎖多執行緒崩潰、Postgres 17 雙層 `jsonb_set_lax` 丟失與 `useOfflineMutation` 漏帶 JWT 陷阱）**：`supabase-py 2.31.0` 預設 `httpx.Client(http2=True)` 底層 `httpcore 1.0.9 HTTP2Connection._h2_state` 無鎖，在 `run_in_threadpool` 多執行緒壓測下 12/12 爆 `StreamIDTooLowError`；Postgres 17 `jsonb_set_lax('{}'::jsonb, ARRAY['day_notes','1'], val, true)` 會靜默回傳 `'{}'` 丟失新行程寫入，而 `jsonb_set(..., NULL::jsonb, ...)` 為 `STRICT` 會把整個 `content` 抹為 `NULL`；前端 `sync-hooks.ts` 線上分支裸 `fetch()` 繞過 JWT 包裝造成線上信用卡寫入 100% `401` 靜默丟失。
- **FP-122（靜態假設偏離線上五雲實況與 `MagicMock` `hasattr(rpc)` 偽路徑陷阱）**：僅憑靜態碼與本地 migration 曾兩度誤判線上現況（線上 `public.update_trip_credit_cards` 實則已有 `auth.uid()` 守衛；線上 `cleanup-cloudinary` v8 僅查 `cover_image` 不查 `hotel_info`），印證實作前必先直查五雲現況；另後端新增 `.rpc()` 快路徑時因 `hasattr(MagicMock(), "rpc")` 恆為 `True`，必須以 `isinstance(supabase, NonCallableMock)` ＋ `ENABLE_ATOMIC_TRIP_RPC` 熔斷開關雙重隔離。

### 🎯 Next Steps
- 提交並推送本日報與 Auto Dream 2.0 固化之 `.agents/` 記憶更新；確認無遺留後可安全清理本機 `.worktrees/review-sandbox`、`sentinel-581fb847` 並歸檔／刪除此聊天室。
- 後續維護依優先序可安排：`fetchLatestRecoveryKey()` single-flight 去重、GitHub Dependabot 2 項 moderate 依賴評估、以及有實機時抽檢 iOS Safari 相機／軟鍵盤體感。

---

## 🧬 Machine-Executable Invariant Rules

```json
[
  {
    "domain": "ios_ui",
    "type": "INVARIANT_RULE",
    "id": "INV-IOS-COMPOSER-BENTO-DASHBOARD-01",
    "title": "ChatComposer 統一雙區卡片、精算器 320px Bento、5 欄純圖示底抽膠囊與三層 Escape/z-index 隔離契約 (AD-249)",
    "content": "ChatComposer 採統一雙區和紙白/深翠黑卡片與左下角 + 旋轉 Radix Popover（上傳圖片/拍照即問/深度研究），行動端 Auto-Dock 必同步關閉 Popover、全螢幕對話開啟必隱藏 #tour-ai-bot、壓縮必配世代鎖、深度研究停止須同步 /cancel 與 AbortSignal 且啟動失敗不得穿透 streamChat。GlobalTaxActuary 採 320px 2 層信用卡 Bento、滿寬 grid-cols-2 標價膠囊、44px 計算機鍵、寬容文字數值輸入 (type='text' inputMode='decimal' + parseCostAmount)、免稅門檻 Math.min(99, ...) 防 100% 矛盾並於 0% VAT 隱藏進度條。IOSBottomSheet 頁籤列採 grid-cols-5 純圖示零文字膠囊，層級鎖定 z-115（高於 #tour-ai-bot z-110、低於 SessionReauthModal z-165），並落實 Popover -> 內嵌表單 -> 外層底抽 (!e.defaultPrevented) 三層 Escape 隔離；當日智慧看板 5 分頁卡片統一和紙底座、同級 <button> 解耦、全路徑 useRef 單幀互斥鎖、Intl.Segmenter 首字素擷取、CurrencyPillSelector 保留既非預載幣別且與外層同步行程預設幣別。"
  },
  {
    "domain": "state_cache",
    "type": "INVARIANT_RULE",
    "id": "INV-STATE-ZERO-LEAK-BROADCAST-MERGE-01",
    "title": "零外洩後落盤即時廣播、本地私密保留合併、防抖計數守恆與 Day 0/1 清單同步契約 (AD-250)",
    "content": "協同端點 broadcastTripEvent 必須在 await tripsApi.updateDayData(...) 後端落盤成功後才發送，且 payload 必經 stripPrivateForBroadcast() 淨化，嚴禁將 is_private: true 條目或原始 private_owner_id UUID 送上 Supabase Realtime WebSocket。接收端 (useTripRealtime.ts, EditableDailyChecklist.tsx, EditableDailyTips.tsx) 必以 mergeIncomingWithLocalPrivate(..., allowOwnerlessIncoming=false) 將外部公開廣播與本端私密項合併，防止同伴更新洗掉本機私密項；itinerary-view.tsx 須以 useMemo 穩定每日陣列參照並對 500 錯誤去重單一 Toast；Day 1 清單樂觀寫入須同步歸零 day_checklists[0] = [] 對齊後端 Day 0 合併清理；500ms 勾選防抖必以 hasPendingDebounceRef 每視窗僅累加一次 pendingUpdatesCount、失敗回滾至 committedItemsRef，且所有立即變更 (add/remove/privacy/saveEdit) 前須先執行 cancelPendingDebounce() 杜絕過期計時器復活已刪項目。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BACKEND-COLLAB-PRIVACY-BOLA-GDPR-01",
    "title": "多端點協作私密隔離、信用卡五不變量歸屬防奪權、私密景點 BOLA 與孤兒系統行程 GDPR 契約 (AD-251)",
    "content": "GET /api/trips、/itinerary/latest 與 /api/trips/{trip_id} 必共用統一 _is_trip_creator（查 user_trips_view 時強制 allow_legacy_user_id=False，因該視圖 user_id 為查詢者自身 ID）、_filter_private_day_items 與 _filter_private_cards（脫敏非本人 creator_id 為 mem_*）。PATCH /day-data 與 /info 必保留資料庫中他方隱藏私密項、嚴格綁定 JWT user_id、將非布林 is_private/is_public 一律歸一為 false、同批 credit_cards ID 去重並對碰撞隱藏私卡 ID 重新配號，且嚴禁非建立者奪取或將公開卡私密化。私密 itinerary_items 之建立/修改/刪除/重排/匯入全面實施房主限定 403，前端 ActivityEditModal 對協作者隱藏私密開關。GDPR DELETE /api/user/{uid}/data 除使用者自建行程外，亦須回收已無其他 trip_members 之獨居 created_by='SYSTEM' 範例行程及其 Cloudinary photo_url。"
  },
  {
    "domain": "ios_ui",
    "type": "FAILED_PATH",
    "id": "FP-118",
    "title": "Tailwind CSS v4 wrap-break-word 壓過 [overflow-wrap:anywhere] 級聯反轉陷阱 (FP-118)",
    "content": "在 tailwindcss@4.3.5 中，編譯後 @layer utilities 會將 .\\[overflow-wrap\\:anywhere\\] 輸出在 .wrap-break-word 之前，且 tailwind-merge 不合併任意 CSS 屬性，導致同時宣告 wrap-break-word [overflow-wrap:anywhere] 時反被 break-word 靜默覆寫並引發 IDE cssConflict 警告。需要無空白長字串任意處折行時一律單獨使用 Tailwind v4 原生 canonical 類別 wrap-anywhere。"
  },
  {
    "domain": "ios_ui",
    "type": "FAILED_PATH",
    "id": "FP-119",
    "title": "Radix onEscapeKeyDown 原生事件簽名誤判與 scrollIntoView 垂直跳頁陷阱 (FP-119)",
    "content": "@radix-ui/react-dismissable-layer 傳入 onEscapeKeyDown 的參數為原生 KeyboardEvent（不同於 onPointerDownOutside 的 CustomEvent），讀取 e.detail?.originalEvent 恆為 undefined，會導致 IME isComposing 防誤關失效；須直接判斷 e.isComposing。另在長高度 IOSBottomSheet 內對橫向膠囊呼叫 el.scrollIntoView({ inline: 'nearest' }) 會連帶將父層垂直捲動至底部 (scrollTop > 2000px)，必須以 getBoundingClientRect() 僅調整橫向容器 container.scrollLeft。"
  },
  {
    "domain": "state_cache",
    "type": "FAILED_PATH",
    "id": "FP-120",
    "title": "SWR v2 dequal 參照穩定性導致失敗不回滾與 useEffect([..., isEditing]) 覆蓋離線編輯陷阱 (FP-120)",
    "content": "前端突變失敗 (401/409/500) 時伺服器資料未變，SWR v2 dequal 會保留同一份 activeTripData 物件參照，導致 useEffect([activeTripData]) 永不重跑，單靠 reloadTripDetail() 無法回滾樂觀狀態；寫入處理器必須快照前態並顯式回滾，同時將 200 成功後之 reloadTripDetail()/tripMutate() 加上 .catch(() => {}) 避免重抓抖動觸發假回滾。反之若將 isEditing/innerEditing 放入 useEffect 而未以 lastSyncedTripRef 追蹤 (tripId, activeTripData)，離線排隊存檔後退出編輯態時會被舊快取反寫覆蓋樂觀編輯。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-121",
    "title": "httpcore 1.0.9 HTTP/2 無鎖崩潰、Postgres 17 雙層 jsonb_set_lax 丟失與 useOfflineMutation 漏 JWT 陷阱 (FP-121)",
    "content": "supabase-py 2.31.0 預設 httpx.Client(http2=True) 底層 httpcore 1.0.9 HTTP2Connection 無鎖修改 _h2_state，於 run_in_threadpool 多執行緒併發下 12/12 爆 StreamIDTooLowError/KeyError，必改以 ClientOptions(httpx_client=httpx.Client(http2=False)) 並於主執行緒預熱 .postgrest。Postgres 17 jsonb_set_lax('{}'::jsonb, ARRAY['day_notes','1'], val, true) 靜默回傳 '{}' 丟失空行程寫入，且 jsonb_set(..., NULL::jsonb, ...) 具 STRICT 特性會將整欄 content 抹為 NULL，必須先驗 jsonb_typeof(...)='object' 並改採頂層 v_content || jsonb_build_object(...)。前端 sync-hooks.ts 線上分支裸 fetch() 繞過 JWT 包裝造成線上信用卡編輯 100% 401 靜默蒸發，必須統一經 offlineFetch (tripsApi.updateInfo) 或於線上分支補齊 JWT 與 401 單次重試。"
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-122",
    "title": "靜態假設偏離線上五雲實況與 MagicMock hasattr(rpc) 偽路徑測試崩壞陷阱 (FP-122)",
    "content": "未直查線上五雲實況而單憑本地 migration 與靜態碼推論曾兩度誤判（線上 public.update_trip_credit_cards 實則具 auth.uid() 守衛、線上 cleanup-cloudinary v8 僅掃 itineraries.cover_image 不掃 hotel_info），架構審核前必須直連線上五雲取證。另後端新增 .rpc() 快路徑搭配舊 Python 降級時，因 hasattr(MagicMock(), 'rpc') 恆為 True，必須以 isinstance(supabase, NonCallableMock) 搭配 ENABLE_ATOMIC_TRIP_RPC 熔斷開關雙重護衛，確保既有 mock 測試與秒級回退均安全運作。"
  }
]
```
