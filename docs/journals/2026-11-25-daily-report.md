# 📅 Daily Report - 2026-11-25 (統一 AI 輸入列、精算器 Bento、5 分頁智慧看板、多人協作隱私、Zero-Redis Postgres 17 原子併發、Auth PoP 封窗、6 帳測試池與原子暱稱建帳)

> **時間範圍**: `2026-11-23 20:02 ~ 2026-11-25 18:30` (UTC+8)
> **納入 Commits (`781918e..HEAD`, 8 個程式碼 Commits ＋ 日報固化 `0b04e24`/`dcf2628`)**:
> - **第一階段（`781918e..57855c0`, 5 Commits, `44 files changed, 17,119 insertions(+), 1,722 deletions(-)`）**:
>   - `8322671` (`2026-11-23 20:02:07`): `feat(agents): isolate pwa-idea-to-spec skill in workspace` (`4 files, +129/-2`)
>   - `6a4af9f` (`2026-11-24 22:48:14`): `feat(ui,dashboard): unify chat composer, tax bento, and daily smart dashboard` (`23 files, +10,521/-1,478`)
>   - `7d9b996` (`2026-11-25 00:09:51`): `fix(collab,privacy,gdpr): enforce privacy isolation, safe merge & wrap` (`9 files, +1,143/-137`)
>   - `ff6909a` (`2026-11-25 00:57:05`): `fix(privacy,collab): block card creator forgery/hijack and private item BOLA` (`7 files, +368/-55`)
>   - `57855c0` (`2026-11-25 12:20:18`): `feat(concurrency,auth): add Postgres atomic content RPCs and fix card JWT/info rollback` (`17 files, +5,043/-135`)
>   - `0b04e24` (`2026-11-25 12:51:02`): `docs(journal,memory): add Nov 25 daily report and consolidate UI, collab privacy, and atomic RPC invariants` (`7 files, +161/-2`)
> - **第二階段（`0b04e24..HEAD`, 含 `eb12c76` 及經歷史清洗後之單步原子暱稱建帳／前端清洗補強／日報固化提交）**:
>   - `eb12c76` (`2026-11-25 16:23:33`): `fix(auth,ops): enforce PoP reauth guard and add test pool manager` (`9 files, +3,641/-60`)
>   - 原子暱稱建帳、過期 `Traveler` 清理、前端統一清洗與安全哨兵加固提交（`fix(auth,ops,security): add atomic nickname bootstrap, save sanitization, and stale traveler purge`, `12 files`）：抽離純模組 `frontend/lib/nickname-utils.ts` 統一 `LandingPage.handleLogin` 與 `ProfileView.handleSaveProfile` 清洗規則，補齊 `ProfileView` 四重競態鎖與全倉 SHA-256 哨兵掃描，並獲站長核准自 `main` 公開 Git 歷史徹底清除原 `e387233` 測試檔誤入之 3 筆未升級 Legacy 用戶明文 UUID。
>   - 本日報與全對話紀錄資產固化提交（`docs(journal,memory): finalize Nov 25 report, Chrome E2E pass, and FP-128`, `6 files`）。
> **全棧 Quality Gate 實測結果（最新基線）**:
> - Neural Seam Invariant Harness (`scripts/neural_seam_harness.py`): **`10/10` Intact** (`0` Sequelae, `EXIT 0`)
> - Security Ledger (`scripts/validate_security_ledger.py`): **`454 targets` (`214 remediated, 53 verified/unresolved, 187 dismissed/safe`)**（`439 -> 444 -> 454`, `+15 targets`, `0` 歷史 ID 遺失, `EXIT 0`）
> - Security Sentinel (`runner.py --mode fast` 物理隔離 `agy.exe --sandbox` ✕ Worktree Spiking Red→Green PoC ✕ Mantis Block G):
>   - 2026-11-24 當日智慧看板 5 分頁審查：**`5/5 DISMISSED`**（[`security_sentinel_report_2026-11-24_daily_dashboard_cards.md`](file:///d:/Project/tabiji/travel-pwa/docs/security/reports/2026-11/security_sentinel_report_2026-11-24_daily_dashboard_cards.md)）
>   - 2026-11-25 Pure Postgres 原子 RPC 與前端 P0 審查：**`10/10 DISMISSED`**（[`security_sentinel_report_2026-11-25_atomic_trip_content_rpc.md`](file:///d:/Project/tabiji/travel-pwa/docs/security/reports/2026-11/security_sentinel_report_2026-11-25_atomic_trip_content_rpc.md)）
> - Backend Pytest (`pytest -q`): **`831 passed, 5 skipped, 0 failed`**（基線 `785` ➔ 午間 `803` ➔ `eb12c76` `823` ➔ **`831`**, `+46` 新增測試, `EXIT 0`）
> - Frontend TypeScript (`npx tsc --noEmit`) & ESLint (`npm run lint`): **`0 errors, 0 warnings`** (`EXIT 0`)
> - Frontend Vitest (`npx vitest run`): **`134 files, 1,247 passed | 4 skipped (1,251)`**（基線 `127 files / 1,168` ➔ 午間 `131 / 1,224` ➔ `eb12c76` `132 / 1,226` ➔ `e387233` `134 / 1,245` ➔ 本輪補強 **`134 / 1,247`**, `+7 files / +79 tests`, `EXIT 0`）
> - Frontend Production Build (`npx next build`, Turbopack): **`11/11` static pages** (`EXIT 0`)
> - Live Postgres 17.6 Migration & Transaction Verification: `20261125_atomic_trip_content_rpcs.sql` 已直上正式 Supabase Postgres 17.6，`BEGIN; ... ROLLBACK;` 實測 **`18/18` 斷言全綠**（涵蓋空 `{}` 行程、非布林毒卡、重複卡 ID、日期保護、外鍵共存 `FOR NO KEY UPDATE`、`cover_image` 單欄 no-op 觸發器守衛）。
> - Live 5-Cloud Production & `@mcp:chrome` E2E:
>   - **`57855c0`（午間）**: Cloud Run `antigravity-backend-00219-ppk` 12 條真併發 **`12/12 HTTP 200`**；Vercel `dpl_zZeziLgntN6ZSTSuN4RHPiBBTb3y` 實機 Chrome 驗收信用卡 `PATCH /info` `200` 持久化；15 次純 `content` 更新 `cleanup-cloudinary` 觸發 **`0`** 次。
>   - **`eb12c76`（午後）**: 實機 `@mcp:chrome` 4 組隔離流程（裸 UUID `401` 彈窗、貼 `tbj_rec_*` `200` 復原、Legacy 靜默升級、90 天過期 PoP JWT 自動恢復＋對抗探針 `401`）100% 通過；線上 `https://www.tabijiapp.com/api/auth/session` 實測裸 `OWNER` UUID + `expected_user_id` 已回 **`HTTP 401` (`leaked_key=False`)**、新簽發 `OWNER` `tbj_rec_*` 回 **`HTTP 200`**；線上 Supabase 精準清理 `29` 測試帳＋`99` 筆 `>7d` 爬蟲/稽核 `Traveler` 殭屍（`public.users`: **`250` → `221` → `122`**）並補回 `3` 位老用戶真名（`Chungshi`、`William`、`海獺`），3 份脫敏備份均受 `.gitignore` 保護且零敏感鍵外洩。
>   - **原子暱稱建帳與安全補強（傍晚）**: 實探 Vercel Production (`READY`) 與 Cloud Run `antigravity-backend-00222-sfc`（`200 healthy`, `database: connected`）皆已上線最新版；完成 `@mcp:chrome` 4 組隔離終驗（A. 新用戶 `\u200b`/`null` 攔截 0 API 呼叫＋`"　測試　🇹🇼👨‍💻　"` 原子建帳與 `PUT /api/users/me` 清洗 100% 一致、B. `ProfileView` 封鎖 `"Traveler"`/`"null"`/`"undefined"` 覆蓋與 1,200ms 慢速 `GET` 競態防線、C. 現代 `tbj_rec_*` 換票省略 `name` 零 401 風暴、D. `https://www.tabijiapp.com` 唯讀終驗 0 console error／0 自動建帳／`public.users` 維持 `122` 筆零髒資料）；並經站長核准自 `main` 公開 Git 歷史徹底改寫清除原 `e387233` 誤入之 3 筆 Legacy 明文 UUID（實查三者均仍為 `is_upgraded=False` 未遭動用）。

---

## 1. 工程與檔案異動清單（2026-11-23 晚 ~ 2026-11-25 傍晚）

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
- **Auth PoP 安全封窗與 6 帳雙軌固定測試池治理（`eb12c76`, 9 檔）**:
  - [backend/routers/auth.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/auth.py) (`+9/-14`)、[test_prod_auth_cutover_sentinel.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_prod_auth_cutover_sentinel.py) (`+46/-11`): 移除 `has_matching_anchor` 免 Bearer JWT 旁路，對已升級帳號前置 `if not is_authenticated: raise 401` 並恢復 `db_ver > 1 and token_ver < db_ver` 撤銷閘門；完整保留未升級 Legacy 初次靜默升級與 90 天 PoP JWT 自癒。
  - [scripts/manage_test_accounts.py](file:///d:/Project/tabiji/travel-pwa/scripts/manage_test_accounts.py) (`+2,068`)、[test_users.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/fixtures/test_users.py) (`+88/-8`)、[test-fixtures.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/constants/test-fixtures.ts) (`+64/-2`)、[test_manage_test_accounts.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_manage_test_accounts.py) (`+1,150`)、[test_test_user_pool_sentinel.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_test_user_pool_sentinel.py) (`+129/-25`)、[test-fixtures.test.ts](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/test-fixtures.test.ts) (`+85`)、[.agents/domains/devops_security.md](file:///d:/Project/tabiji/travel-pwa/.agents/domains/devops_security.md): 建立三模式維運工具（`--audit`/`--purge`/`--upgrade-pool`），同步前後端 6 帳雙軌常數（`RYAN_TEST` 環境變數注入＋合成 RFC 4122 v4 預設值 `00000000-0000-4000-8000-000000000006`，零明文個人 UUID 外洩）。
  - **線上 Supabase 精準清理與升級實績**：清理 `29` 測試帳、`52` 行程、`344` 景點、`1` 記帳、`45` 成員、`150` 通知、`2` 孤兒推播、`1` Cloudinary 資產（備份 `test_accounts_backup_20261125_082411.json`，`176,972 B`，零敏感鍵洩漏）；經線上正式 API 升級 `00001/00002/00004/00005` 並原子寫入受 `.gitignore` 隔離之 `.env.test-pool.local`（`00003 VIEWER` 硬鎖純 Legacy、`RYAN_TEST` 原密鑰不動）。
- **單步原子暱稱建帳、個人頁防 `Traveler` 覆蓋鎖與過期 `Traveler` 殭屍清理（`e387233`, 10 檔）**:
  - [backend/routers/auth.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/auth.py) (`+107/-4`)、[test_auth_atomic_nickname_bootstrap.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_auth_atomic_nickname_bootstrap.py) (`+453`): `SessionRequest` 支援可選 `name`（`max_length=256`）搭配 `sanitize_bootstrap_name`（剝除控制／零寬／Bidi 字元、`\s+` 全形空白折疊、Grapheme 邊界安全 64 碼點截斷、前後雙重佔位符過濾），僅套用於新建帳號與孤兒 UUID 補登，絕不覆寫既有老用戶。
  - [frontend/lib/nickname-utils.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/nickname-utils.ts)（本輪抽離純模組）、[frontend/lib/auth-session.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/auth-session.ts)、[landing-page.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/landing-page.tsx)、[profile-view.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/profile-view.tsx)、[auth-session-atomic-nickname.test.ts](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/auth-session-atomic-nickname.test.ts)、[landing-page-orphan-and-dual-storage.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/landing-page-orphan-and-dual-storage.test.tsx)、[profile-nickname-overwrite-guard.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/profile-nickname-overwrite-guard.test.tsx)、[test_test_user_pool_sentinel.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_test_user_pool_sentinel.py): 跨端同步 Unicode/Grapheme 清洗並透過純模組 `nickname-utils.ts` 統一 `LandingPage.handleLogin` 與 `ProfileView.handleSaveProfile` 輸入清洗（杜絕 `usersApi.updateProfile` 反覆蓋原子清洗暱稱與放行 `\u200b`/`null`/`undefined`）；`ProfileView` 封鎖後端 `"Traveler"`／佔位符覆蓋本機真名並補齊四重非同步競態防線；移除 `e387233` 測試檔誤入之 3 筆線上未升級 Legacy 用戶明文 UUID 並升級全倉 SHA-256 哨兵掃描。
  - [scripts/manage_test_accounts.py](file:///d:/Project/tabiji/travel-pwa/scripts/manage_test_accounts.py) (`+512/-5`)、[test_manage_test_accounts.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_manage_test_accounts.py) (`+339`): 擴充 `--purge-stale-travelers`（預設 7 天冷卻＋`SAMPLE_TRIP_PLACE_NAMES` 二階段範例景點核驗）；線上補回 `3` 位老用戶真名（`Chungshi`、`William`、`海獺`，備份 `restore_legacy_user_names_20261125_091357.json`）並精準清除 `99` 位超過 7 天爬蟲／稽核 `Traveler` 殭屍與 `67` 份未改動範例行程（備份 `stale_travelers_backup_20261125_091433.json`），線上總用戶由 `221` 淨化至 **`122`**（真實外部主動註冊用戶 **`107`** 位、核心有效用戶 **`58`** 位、真實轉化率 **`54.2%`**）。

---

## 2. 本日實戰事件、架構決策與經驗沉澱

### 🟢 Features & Fixes
- **三大高頻介面和紙視覺與行動端人體工學大統一**：AI 聊天輸入列、外幣免稅精算器、5 分頁當日智慧看板全部對齊 320px 零溢位、深淺雙色、高對比與 WAI-ARIA 鍵盤／觸控體驗。
- **線上雙帳號紅隊實測 7 連殺封堵協作隱私與資料遺失**：透過真實 `https://www.tabijiapp.com` 房主 A ✕ 旅伴 B 互測與對抗攻擊，接連揪出並根治「同伴存檔抹除私密項」「WebSocket 明文廣播私密 UUID」「信用卡歸屬偽造／奪權／偷轉私卡」「私密景點 BOLA 強制公開／刪除」「GDPR 殘留孤兒系統行程」等線上真實缺陷。
- **Zero-Redis Pure Postgres 17 原子化並根治線上信用卡 401 靜默丟失**：對標 Supabase／Vercel／Cloudflare 業界實踐，以零新增基礎設施成本解決 Cloud Run 多實例 JSONB 併發覆蓋（12 條真併發 12/12 `200` 零遺失），同步抓出並根除線上 `tools-view.tsx` 信用卡寫入 100% `401` 靜默清空的 P0 缺陷與 `cleanup-cloudinary` 無效觸發雜訊。
- **Auth PoP 輪替繞過 P0 封窗與 6 帳雙軌固定測試池落地（`eb12c76`）**：於 `/boost` 變更安全網稽核中提前攔截 `auth.py` `has_matching_anchor` 繞過 `credential_version > 1` 撤銷之 Critical 漏洞與公開倉庫個人 UUID 外洩風險；移除旁路後經 `@mcp:chrome` 4 組隔離流程與線上 Cloud Run `401` 實探雙重驗收，並將線上 6 帳固定池統一納管於 `scripts/manage_test_accounts.py` 與受 `.gitignore` 隔離的 `.env.test-pool.local`。
- **Cloud Run 日誌法醫學溯源 `Traveler` 真相、原子暱稱建帳與線上用戶表徹底淨化（`e387233`）**：自 205 筆線上 `/api/auth/session` 日誌證實 107 筆零行程 `Traveler` 全數源自 11/18 前 Googlebot 爬蟲、歷次稽核腳本漏刪、孤兒 UUID 復活與兩段式改名斷裂；補回 `Chungshi`/`William`/`海獺` 真名、清零 99 筆 `>7d` 爬蟲殭屍（`250 -> 221 -> 122`），並落地單步原子暱稱建帳與個人頁防覆蓋鎖。
- **開發環境雜訊與 Antigravity IDE v2.8.0 存檔衝突死循環精準鑑識（零誤改）**：根治每次送出訊息彈出 `Error: File Modified Since` 死循環（定位至 `agy` `onChatSent() -> flushDirtyNonReviewedDocuments()` 撞上 2 個殘留 Hot-Exit 舊分頁，避免誤點 `Overwrite` 寫回未脫敏資安報告）；另確認 `com.chrome.devtools.json 404`、`reactStrictMode` 雙次自癒 `401` 與 `.worktrees/review-sandbox` 659 筆假紅字皆非程式碼問題。

### 🏛️ Architecture Decisions
- **AD-249（ChatComposer 雙區卡片、精算器 320px Bento、5 欄純圖示底抽膠囊與三層 Escape/z-index 隔離契約）**：統一 AI 輸入列為雙區卡片＋`+` Radix Popover（Auto-Dock 關閉、全螢幕隱藏 `#tour-ai-bot`、壓縮世代鎖、深度研究 `/cancel` + `AbortSignal` 隔離）；精算器升級 320px 2 層 Bento＋寬容數字解析 (`parseCostAmount`)＋門檻 `Math.min(99, ...)`＋0% VAT 隱藏進度條；`IOSBottomSheet` 採 `grid-cols-5` 純圖示膠囊與 `z-115`（介於 `#tour-ai-bot` `z-110` 與 `SessionReauthModal` `z-165`），並落實 Popover → 內嵌表單 → 外層底抽三層 `Escape` 隔離與 `Intl.Segmenter` 字素擷取。
- **AD-250（零外洩後落盤即時廣播、本地私密保留合併、防抖計數守恆與 Day 0/1 清單同步契約）**：`broadcastTripEvent` 嚴格置於後端落盤成功後且經 `stripPrivateForBroadcast()` 淨化；接收端採 `mergeIncomingWithLocalPrivate(allowOwnerlessIncoming=false)` 保護本端私密項；父層以 `useMemo` 穩定陣列參照並對 Day 1 樂觀歸零 `day_checklists[0]`；500ms 勾選防抖以 `hasPendingDebounceRef` 守恆計數、`committedItemsRef` 基準回滾，所有立即寫入前先 `cancelPendingDebounce()`。
- **AD-251（多端點協作私密隔離、信用卡五不變量歸屬防奪權、私密景點 BOLA 與孤兒系統行程 GDPR 契約）**：三支查詢端點共用 `_is_trip_creator(allow_legacy_user_id=False)`、`_filter_private_day_items` 與 `_filter_private_cards`（`mem_*` 脫敏）；`PATCH /day-data` 與 `/info` 保留他方私密項、綁定 JWT `user_id`、強制布林正規化並捍衛信用卡歸屬五不變量；私密 `itinerary_items` 全 CRUD/重排/匯入限房主並隱藏協作者介面切換鈕；GDPR 同步回收獨居 `SYSTEM` 孤兒行程。
- **AD-253（Zero-Redis Pure Postgres 原子 RPC、HTTP/1.1 執行緒安全 Supabase 連線池與前端 Info/Card 離線回滾契約）**：*(已隨 `57855c0` 預先固化於 `.agents/domains/backend_concurrency.md`，本日報統一編號為 `AD-253` 消除與 `map_webgl.md` `AD-246` 之撞號)*。以 3 支 `service_role` 專屬 Postgres 17 `FOR NO KEY UPDATE` RPC ＋ `httpx.Client(http2=False)` 連線池 ＋ `tripsApi.updateInfo` (`offlineFetch`) ＋ `info-view.tsx` 顯式快照回滾與 `lastSyncedTripRef` 達成端到端零競態、零靜默丟失。
- **AD-254（固定 6 帳雙軌測試池、零線上一次性帳號污染與過期 `Traveler` 清理契約）**：*(統一 `eb12c76` 原寫入 `.agents/domains/devops_security.md` 之 `AD-249` 為 `AD-254`，消除與 `ios_ui.md` `AD-249` 之撞號)*。嚴禁線上建立一次性測試／稽核帳號，統一複用固定 6 帳雙軌池（環境變數注入 RFC 4122 v4 `RYAN_TEST` 專測 D1 POI/UI、`00001/00002/00004/00005` 現代 `tbj_rec_*`、`00003` 硬鎖純 Legacy 且嚴禁對線上實打靜默升級—升級測試限 Pytest Mock）；公開程式碼僅留合成 v4 預設值與 SHA-256 雜湊硬保護清單（嚴禁嵌入任何真實個人或外部 Legacy 用戶明文 UUID）；所有巡檢／清理／過期 `Traveler` 回收（`min_age_days >= 1` 預設 7 天＋`SAMPLE_TRIP_PLACE_NAMES` 二階段核驗）／線上升級均經 `scripts/manage_test_accounts.py`（預設 Dry-Run、分頁讀表、空 `SYSTEM` 行程 1h 冷卻＋精確大寫比對、聯合固定點收斂、Cloudinary Step-1 前置 Preflight＋顯式 `ok`/`not found` 驗收、脫敏備份鎖定 `docs/migrations/backups/`、行級 25 列 Trigger 節流、Cloud Run `/api/health/deep` 暖機＋嚴驗 `upgraded=True`、`.env.test-pool.tmp.local` ＋裸 `git check-ignore -q --` 守門、`PARTIAL_UPGRADE_DESYNC` 回查）。
- **AD-255（單步原子暱稱建帳、跨端 Unicode/Grapheme 邊界清洗與已升級帳號強制 PoP 閘門契約）**：`POST /api/auth/session` 對已升級帳號前置 `if not is_authenticated: raise 401` 徹底封堵 `expected_user_id` 免 JWT 旁路（保留未升級 Legacy 靜默升級與 90 天 PoP JWT 自癒；無狀態 0.05ms 業務 API 於輪替後隨裝置重載或背景 `GET /api/auth/credential` `token_ver < db_ver` 即刻撤銷）；同步支援可選 `name`（`max_length=256`）僅於新建帳號與孤兒 UUID 補登原子寫入、絕不覆寫既有老用戶；前後端對稱剝除控制／零寬／Bidi 字元、`\s+` 折疊 Unicode 空白、Grapheme 邊界安全 64 碼點截斷，且於截斷前後雙重封殺佔位名（`traveler`/`new traveler`/`unknown traveler`/`legacy traveler`/`null`/`undefined`）。
- **AD-256（個人頁 `Traveler` 佔位名防覆蓋鎖、四重非同步競態防線與登入孤兒 UUID 自癒重試契約）**：純模組 `frontend/lib/nickname-utils.ts` 統一供應 `normalizeUserInputNickname`/`sanitizeEffectiveNickname`（避免 `vi.mock('@/lib/auth-session')` 癱瘓 UI 清洗）；`LandingPage.handleLogin` 與 `ProfileView.handleSaveProfile` 皆先清洗輸入（拒收純隱形字元與字面 `"null"`/`"undefined"`，避免 `usersApi.updateProfile` 反覆蓋原子清洗暱稱）；`LandingPage` 於 `!uuid || !hasCachedToken` 單步帶入真名並支援孤兒自癒重試且保留 `updateProfile` 過渡保底；`ProfileView` 禁止後端 `"Traveler"`／佔位名覆蓋本機有效真名，並以 `isMountedRef`、`profileReqSeqRef`、`isEditingRef` 與 `user_uuid` 核對封堵四重競態與跨帳號回滾污染。

### 🔴 Technical Debt
- **DEBT-E387233-GITHUB-CACHE-PURGE-01（Follow-up — 公開歷史已清除，可選 GitHub 快取清理）**：原 `e387233` 誤入之 3 位線上未升級 Legacy 老用戶（`1fbdb6a6` `Chungshi`、`3e227762` `William`、`22a719a2` `海獺`）明文 UUID 已於站長核准後自 `main` 公開 Git 歷史徹底改寫清除並 `--force-with-lease` 覆寫遠端（實查三者皆仍為 `is_upgraded=False` 未遭動用）；因 GitHub 網頁仍可能短暫快取斷鏈 commit SHA，若需徹底抹除遠端孤兒物件可向 GitHub Support 提交快取清除申請。
- **DEBT-AUTH-MAIN-ROTATE-V5-01（Optional — 安全強化建議）**：`eb12c76` 已於 Cloud Run 封閉 11/19–11/25 期間的 `has_matching_anchor` 窗口，建議站長擇機於 App 內對主帳執行一次 `/api/auth/rotate`（`v4 -> v5`）使窗口期間所有潛在複製品徹底失效（其他裝置於下次同步／重開即強制原地貼新引繼碼恢復，不遺失離線資料）。
- **DEBT-LEGACY-CREATOR-NAME-SNAPSHOT-01（Low — 歷史反正規化欄位）**：3 位老用戶（`Chungshi`、`William`、`海獺`）之 `public.users.name` 與 `trip_members` 已確認為真名，歷史行程表舊副本欄位 `itineraries.creator_name` 未做回溯改寫（不影響登入、個人頁與行程名單顯示）。
- **DEBT-LEGACY-ORPHAN-NOTIFS-01（Low — 歷史唯讀列管）**：線上尚留存 `292` 筆歷史已刪帳號遺留之孤兒 `notifications` 與 `3` 筆 `2025-12-18` `created_by IS NULL` 歷史行程，目前刻意不碰並由 `manage_test_accounts.py --audit` 持續列管。
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
- **FP-123（Antigravity IDE v2.8+ `flushDirtyNonReviewedDocuments()` 過期 Hot-Exit 分頁存檔衝突死循環陷阱）**：IDE v2.8.0 起每次送出聊天訊息都會呼叫 `onChatSent() -> flushDirtyNonReviewedDocuments()` 強制存檔工作區所有 `isDirty` 分頁（含隱藏 5–7 天前的 Hot-Exit 舊緩衝區），引發每次發訊必跳 `Error: File Modified Since`。嚴禁點擊 `Overwrite`（可能蓋回舊版並帶回已脫敏之 `apiSecretFirst4` 等敏感片段），必須先驗 `git status`/`git diff` 確認磁碟已為最新版，再於 IDE 執行 `File: Revert File` 並定期清掉殭屍工作樹分頁。
- **FP-124（`has_matching_anchor` 客戶端 `expected_user_id` 免 JWT 旁路架空 `credential_version > 1` 輪替撤銷陷阱）**：`36b07bb2` 為了搶救舊網域殘留分頁曾以 `body.expected_user_id == clean_uid` 免 Bearer JWT 解密雲端保險庫，結果省略 `Authorization` 標頭即可讓 `is_authenticated = False` 直接跳過 `db_ver > 1 and token_ver < db_ver` 輪替檢查，單憑公開倉庫歷史 UUID 即可奪取最新 `tbj_rec_*`。絕不可信任客戶端 JSON 欄位作為身分證明；已升級帳號必須前置 `if not is_authenticated: raise 401`，且公開倉庫嚴禁硬寫個人手測 UUID。
- **FP-125（維運清理腳本多重暗坑：`.env.*.local.tmp` 繞過忽略、PostgREST 千列截斷、Trigger 風暴、Cloudinary 吞錯與時區偏移）**：實證 `.gitignore` 規則 `.env.*.local` 不忽略 `.env.test-pool.local.tmp`（`exit=1`），`docs/security/*.json` 具反轉規則，暫存檔必留 `.local` 後綴（`.env.test-pool.tmp.local`）、備份鎖定 `docs/migrations/backups/` 並經裸 `git check-ignore -q --`（禁 `-v`/`--no-index`）驗證；PostgREST 預設 1,000 列上限必分頁 `.range()`；混雜非 UUID 查 UUID 欄必先 `uuid_only()` 防 `22P02`；`public.users` 無 Cloudinary Trigger 且 `destroy_cloudinary_assets()` 會將 `401`/`not found` 靜默回 `0`，必於 Step 1 刪庫前執行 Cloudinary Preflight 並顯式斷言 `status == 200 and result in {"ok", "not found"}`；`AFTER DELETE FOR EACH ROW` 必採行級 25 列／0.3s 節流；空 `SYSTEM` 行程必設 `>= 1h` 冷卻（防 `seed-sample` 競態）且嚴格比對大寫 `"SYSTEM"`（護 `created_by IS NULL`）；跨表清理採聯合固定點迴圈核對 `created_by` 與 `user_id`；`--upgrade-pool` 必先 `/api/health/deep` 暖機（Cloud Run `--min-instances 0`）、驗證 `upgraded is True`（防 `auth.py` 200 假成功）並於 `httpx.TransportError` 回查 `PARTIAL_UPGRADE_DESYNC`；Python naive `datetime` 於 UTC+8 呼叫 `.astimezone(timezone.utc)` 會偏移 8 小時，須改用 `.replace(tzinfo=timezone.utc)`。
- **FP-126（兩段式改名斷裂、歷史爬蟲空打建帳與孤兒 UUID 靜默復活硬寫 `"Traveler"` 污染真實用戶主檔陷阱）**：Cloud Run 日誌實證 107 筆零行程 `Traveler` 全來自 11/18 前爬蟲空打 `/api/auth/session {}`、稽核腳本漏刪、孤兒復活與兩段式改名失敗（並使 3 位老用戶主檔停在 `Traveler`，開個人頁反被覆蓋）。必須於首次建帳與孤兒補登原子寫入初始暱稱、杜絕稽核亂建一次性帳號，並於清理過期 `Traveler` 時強制 `min_age_days >= 7` ＋二階段範例景點核驗保護剛復活真實裝置（如 `24b0b81a`）。
- **FP-127（暱稱清洗僅折疊 ASCII 空白、截斷後漏檢 `"null"`、撕裂 Emoji Grapheme、二次 `updateProfile` 反覆蓋與 `ProfileView` 競態陷阱）**：僅壓縮 ASCII 空格會漏放 `"New\u3000Traveler"`／NBSP；截斷後漏檢佔位名會讓 `'null' + 'e' + '\u0301'*61` 截成 `'null'`；原始 64 索引截斷會撕裂 `👨‍💻` ZWJ 與 `🇹🇼` 國旗組合；若僅在 `POST /api/auth/session` 清洗而讓 `LandingPage.handleLogin`／`ProfileView.handleSaveProfile` 裸用 `.trim()` 寫入 `localStorage` 與 `usersApi.updateProfile`，20ms 後即反覆蓋原子清洗暱稱並放行 `\u200b`/`null`/`undefined`；`ProfileView` 傳值布林 `isMounted` 且缺 `profileReqSeqRef`/`isEditingRef`/UUID 核對亦會引發慢速覆蓋競態。
- **FP-128（公開倉庫單元測試誤入真實未升級 Legacy 用戶 UUID 與單一 UUID `git grep` 盲點陷阱）**：`e387233` 曾誤將 3 位線上真實外部未升級 Legacy 用戶的完整 36 碼 UUID 寫入 `frontend/__tests__/profile-nickname-overwrite-guard.test.tsx`，而推送前僅執行 `git grep -i "ace30a0d"` 未跨庫比對，導致公開 Git 暴露實質等效密碼之 Legacy 憑證。單元測試一律僅能使用純合成 UUID（如 `aaaa1111-...`），且 `test_test_user_pool_sentinel.py` 必須以 SHA-256 雜湊清單全倉掃描 `backend/tests/`、`frontend/__tests__/`、`scripts/`、`.agents/domains/` 與 `docs/journals/`。

### 🎯 Next Steps
- **可選資安收尾**：原 `e387233` 已自 `main` 歷史徹底清除並覆寫遠端；若需連帶移除 GitHub 網頁孤兒 commit 快取，可至 GitHub Support 提出 cached view 清除申請。
- `@mcp:chrome` 4 組隔離終驗與 `e387233` 歷史清除均已全數完成，本聊天室所有可固化資產均已 100% 沉澱至程式碼、單元測試、`docs/journals/2026-11-25-daily-report.md`、`.agents/memory.md` 與 `.agents/domains/*.md`，**可安全歸檔／刪除此聊天室**。
- 後續維護依優先序可安排：站長擇機於 App 內將主帳輪替 `v4 -> v5`、`fetchLatestRecoveryKey()` single-flight 去重、清理本機 `.worktrees/` 殘留目錄、GitHub Dependabot 2 項 moderate 依賴評估。

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
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-DEVOPS-TEST-POOL-POP-01",
    "title": "固定 6 帳雙軌測試池、零線上一次性帳號污染與過期 Traveler 清理契約 (AD-254)",
    "content": "嚴禁於線上環境任意建立一次性 Test / QA_Audit / SentinelTest 或匿名 POST /api/auth/session {} 測試帳號；凡需實測一律複用固定 6 帳雙軌測試池（D1 POI 與全棧手測走環境變數注入之 RFC 4122 v4 RYAN_TEST、協作/膠囊/BOLA 走 00001/00002/00004/00005 現代 tbj_rec_*、Legacy 相容專測走硬鎖純 UUID 之 00003 VIEWER 且嚴禁對線上 00003 實打靜默升級—靜默升級測試僅限 Pytest Mock）。公開程式碼僅使用合成 v4 預設值 00000000-0000-4000-8000-000000000006 與 SHA-256 雜湊硬保護清單，嚴禁嵌入任何真實個人或外部 Legacy 用戶明文 UUID；日常巡檢、核准清理、歷史過期 Traveler 殭屍回收（--purge-stale-travelers，強制 min_age_days >= 1 預設 7 天保護剛復活真實裝置、零互動/通知核驗、且以 SAMPLE_TRIP_PLACE_NAMES 二階段核驗範例行程未被改動）與測試池升級一律透過 scripts/manage_test_accounts.py（預設 Dry-Run、強制分頁、空 SYSTEM 行程 1h 冷卻與嚴格大寫比對、聯合固定點收斂、Step-1 前置 Cloudinary Preflight 與顯式 ok/not found 驗收、脫敏備份鎖定 docs/migrations/backups/、行級 25 列 Trigger 節流、/api/health/deep 暖機與嚴驗 upgraded=True、.env.test-pool.tmp.local 留 .local 後綴搭配裸 git check-ignore -q -- 與 PARTIAL_UPGRADE_DESYNC 偵測）。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BACKEND-ATOMIC-NICKNAME-POP-01",
    "title": "單步原子暱稱建帳、跨端 Unicode/Grapheme 邊界清洗與已升級帳號強制 PoP 閘門契約 (AD-255)",
    "content": "POST /api/auth/session 對已升級帳號（recovery_key_id IS NOT NULL）必須前置 if not is_authenticated: raise 401，再執行 db_ver > 1 and token_ver < db_ver 撤銷閘門，嚴禁憑客戶端 expected_user_id 免 Bearer JWT 解密保險庫（保留未升級 Legacy 初次靜默升級與 90 天內合法 PoP JWT 自癒；因一般業務 API 採 0.05ms 純記憶體無狀態驗簽，輪替撤銷由他端重載或背景 GET /api/auth/credential token_ver < db_ver 即時執行）。SessionRequest 支援可選 name (max_length=256)，僅於新建使用者與孤兒 UUID 靜默補登時經 sanitize_bootstrap_name() 單步原子寫入，絕不覆寫既有已存在用戶主檔；前後端（auth.py 與 nickname-utils.ts/auth-session.ts）必對稱剝除 ASCII 控制與 Unicode 零寬/Bidi 格式碼點、以 \\s+ 折疊全形/NBSP 空白、以 Grapheme Cluster 邊界（Python _truncate_grapheme_safe 護 ZWJ/國旗對/結合符、TS Intl.Segmenter）安全截斷至 64 碼點，且於截斷前後雙重封殺佔位名（traveler/new traveler/unknown traveler/legacy traveler/null/undefined）。"
  },
  {
    "domain": "state_cache",
    "type": "INVARIANT_RULE",
    "id": "INV-STATE-PROFILE-GUARD-RACE-01",
    "title": "個人頁 Traveler 佔位名防覆蓋鎖、四重非同步競態防線與登入孤兒 UUID 自癒重試契約 (AD-256)",
    "content": "純模組 frontend/lib/nickname-utils.ts 獨立提供 normalizeUserInputNickname / sanitizeEffectiveNickname（auth-session.ts 再匯出），避免測試 vi.mock('@/lib/auth-session') 關閉 UI 清洗。LandingPage handleLogin 與 ProfileView handleSaveProfile 皆須先經 normalizeUserInputNickname 清洗（拒收純隱形字元與字面 null/undefined，確保 ensureValidSession、localStorage.user_nickname 與 usersApi.updateProfile 寫入一致，絕不讓 updateProfile 反覆蓋原子清洗暱稱）；LandingPage 於 (!uuid || !hasCachedToken) && navigator.onLine 單步帶入真名（modern tbj_rec_* 換票省略 name），若既有孤兒 UUID 遭訪客自癒清除則立即補發全新建帳並保留 updateProfile 跨雲過渡保底。ProfileView 嚴禁後端預設佔位名（Traveler 等）或無效字面值覆蓋本機有效真名，並以 isMountedRef、profileReqSeqRef（每次拉取與存檔遞增作廢舊請求）、isEditingRef 與 localStorage.getItem('user_uuid') === userId 四重防線封堵競態與跨帳號回滾污染。"
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-123",
    "title": "Antigravity IDE v2.8+ flushDirtyNonReviewedDocuments 過期 Hot-Exit 分頁存檔衝突陷阱 (FP-123)",
    "content": "Antigravity IDE v2.8.0 起每次送出聊天訊息都會經 onDidSendChatMessage -> onChatSent() -> flushDirtyNonReviewedDocuments() 強制存檔工作區所有 isDirty 分頁（即使隱藏於背景且由 Hot-Exit Backups 留存多日），導致每次發訊必跳 Error: File Modified Since。嚴禁點擊 Overwrite（會將舊草稿蓋回較新 commit 並可能帶回未脫敏資安片段如 apiSecretFirst4）；必先以 git status/git diff 驗證磁碟已最新，再於 IDE 對衝突分頁執行 File: Revert File 並定期清理殭屍 worktree 分頁。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-124",
    "title": "has_matching_anchor 客戶端 expected_user_id 免 JWT 旁路架空輪替撤銷陷阱 (FP-124)",
    "content": "commit 36b07bb2 曾為搶救舊網域殘留分頁於 POST /api/auth/session 加入 has_matching_anchor (body.expected_user_id == clean_uid)，導致攻擊者省略 Authorization 標頭令 is_authenticated=False 時直接跳過 if is_authenticated and db_ver > 1 and token_ver < db_ver 撤銷閘門，單憑公開倉庫 UUID 即可解密雲端 AES-GCM 保險庫取得最新輪替 tbj_rec_*。絕不可把客戶端可偽造 JSON 欄位當作身分證明；已升級帳號必須前置 if not is_authenticated: raise 401，且公開倉庫零明文個人測試 UUID。"
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-125",
    "title": "維運清理腳本多重暗坑：.env.*.local.tmp 繞過忽略、PostgREST 千列截斷、Trigger 風暴、Cloudinary 吞錯與時區偏移 (FP-125)",
    "content": "實測 .gitignore 規則 .env.*.local 不忽略 .env.test-pool.local.tmp (exit=1) 且 docs/security/*.json 具反轉規則，暫存檔必採 .env.test-pool.tmp.local、備份鎖定 docs/migrations/backups/ 並經裸 git check-ignore -q --（禁 -v/--no-index）驗證；PostgREST 預設 1,000 列上限必分頁 .range()；混雜非 UUID 查 UUID 欄必先 uuid_only() 防 22P02；public.users 無 Cloudinary Delete Trigger 且 destroy_cloudinary_assets() 會將 401/not found 皆回傳 0，必於 Step 1 刪庫前執行 Cloudinary Preflight 並顯式斷言 status==200 且 result in {'ok','not found'}；AFTER DELETE FOR EACH ROW Webhook 必採行級 25 列/0.3s 節流；空 SYSTEM 行程必加 >=1h 冷卻（防 seed-sample 競態）且嚴格比對大寫 'SYSTEM'（護 created_by IS NULL）；跨表清理必採聯合固定點迴圈並同時查 created_by 與 user_id；--upgrade-pool 必先 /api/health/deep 暖機（Cloud Run --min-instances 0）、斷言 upgraded is True（防 auth.py 200 假成功）並於 httpx.TransportError 回查 PARTIAL_UPGRADE_DESYNC；Python naive datetime 於 UTC+8 呼叫 .astimezone(timezone.utc) 會偏移 8 小時，須改用 .replace(tzinfo=timezone.utc)。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-126",
    "title": "兩段式改名斷裂、歷史爬蟲空打建帳與孤兒 UUID 靜默復活硬寫 Traveler 污染陷阱 (FP-126)",
    "content": "Cloud Run 205 筆線上日誌法醫學證實 107 筆零行程 Traveler 全源自 11/18 前爬蟲 (Googlebot/Dataprovider) 空打 POST /api/auth/session {}、稽核腳本漏刪匿名帳、孤兒 UUID 靜默復活硬寫 'Traveler'（如 iOS 用戶 24b0b81a）與登入兩段式改名失敗（並使 Chungshi/William/海獺 等老用戶主檔停在 Traveler）。必須於首次建帳與孤兒補登原子帶入暱稱、禁止稽核建立一次性帳號，且清理過期 Traveler 必設 min_age_days >= 7 與二階段範例景點比對保護剛復活真實裝置。"
  },
  {
    "domain": "state_cache",
    "type": "FAILED_PATH",
    "id": "FP-127",
    "title": "暱稱清洗僅折疊 ASCII 空白、截斷後漏檢 null、撕裂 Emoji Grapheme、二次 updateProfile 反覆蓋與 ProfileView 競態陷阱 (FP-127)",
    "content": "前後端暱稱清洗若僅壓縮 ASCII 空格 ( {2,}) 會漏放全形空白/NBSP ('New\\u3000Traveler')，未在 64 碼點截斷後重驗佔位名會讓 'null'+'e'+'\\u0301'*61 截成 'null'，未剝除零寬/Bidi 碼點會放行隱形字串，原始切片會撕裂 ZWJ Emoji 與國旗對；若僅在 POST /api/auth/session 清洗而 LandingPage.handleLogin 與 ProfileView.handleSaveProfile 裸用 .trim()，20ms 後即以未清洗字串透過 localStorage 與 usersApi.updateProfile 反覆蓋 DB 並放行 '\\u200b'/'null'/'undefined'，須抽離純模組 nickname-utils.ts 統一清洗；另 ProfileView 須以 isMountedRef/profileReqSeqRef/isEditingRef 與 user_uuid 核對封堵慢速舊回應覆蓋與跨帳號回滾競態。"
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-128",
    "title": "公開倉庫單元測試誤入真實未升級 Legacy 用戶 UUID 與單一 UUID grep 盲點陷阱 (FP-128)",
    "content": "commit e387233 曾將 3 位線上真實外部未升級 Legacy 用戶（recovery_key_id IS NULL，UUID 即免 JWT 登入升級憑證）之完整 36 碼明文 UUID 寫入公開倉庫 frontend/__tests__/profile-nickname-overwrite-guard.test.tsx，推送前僅跑 git grep -i 'ace30a0d' 未偵測其他真實用戶。單元測試與文件嚴禁引用任何真實線上用戶完整 UUID，一律使用純合成 UUID（如 aaaa1111-...）；並須於 test_test_user_pool_sentinel.py 以 SHA-256 雜湊清單全倉掃描 backend/tests/、frontend/__tests__/、scripts/、.agents/domains/ 與 docs/journals/ 阻斷回歸。"
  }
]
```
