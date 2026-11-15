# 2026-11-16 每日開發與資安硬化報告 (Daily Report)

> **涵蓋區間**: `2026-11-14 ~ 2026-11-16` (UTC+8)
> **基準 HEAD**: `bcefb3f34887518512cd56c0187d8f4fbf40f675` (`docs(journal): add 2026-11-13 daily report and consolidate domain memories`)
> **目標分支**: `main`

---

## 1. 工程硬數據摘要 (Verified Hard Metrics)

- **核心程式碼變動 (`git diff HEAD` 4 個已追蹤檔案)**:
  - `backend/routers/gdpr.py` (`119` 行): `+58 / -14`
  - `backend/routers/users.py` (`489` 行): `+238 / -5`
  - `frontend/components/views/profile-view.tsx` (`1815` 行): `+17 / -2`
  - `frontend/lib/auth-session.ts` (`540` 行): `+43 / -3`
  - 合計：**`4 files changed, 356 insertions(+), 24 deletions(-)`**
- **新增 Supabase 線上對齊檔案 (3 個未追蹤核心檔案)**:
  - `supabase/functions/cleanup-cloudinary/index.ts` (`645` 行)
  - `supabase/migrations/20261115_harden_users_grants_triggers_and_orphan_system_cleanup.sql` (`65` 行，對應線上 migration `20261115124422`)
  - `supabase/migrations/20261115_webhook_cleanup_cloudinary_vault_hmac.sql` (`157` 行，對應線上 migration `20261115135303`)
- **自動化護欄報告更新**:
  - `docs/security/reports/latest_neural_complication_report.md` (`10/10` invariants intact, exit `0`)
- **資安覆蓋帳本 (`validate_security_ledger.py`)**:
  - `377` targets: `156` remediated, `54` verified/unresolved, `167` dismissed/safe (exit `0`)

---

## 2. 本週期核心成果與線上遙測 (Live Production Verification)

### A. 全端真實拓撲對齊與過度工程回滾
- 將先前依純靜態假設產出之 70+ 過度工程變動與臨時報告全數歸零，嚴格收斂至與線上 5 端架構真實對齊的 **7 個核心變動/新增檔案**（`4` 個前後端檔案 + `3` 個 Supabase Edge/SQL 檔案）。
- 完成線上 5 端實測對齊：
  - **Vercel**: 生產部署 `dpl_3MWgn39DdRFjW5MTnEB5H92Z9DpT`（`READY` / `PROMOTED`，Commit `bcefb3f3`）。
  - **Cloudflare Workers & D1**: `cloudinary-proxy`、`tabidachi-search-proxy`、`tabijiapp-edge-shield`、`tabijiapp-poi-service` 與 D1 `tabidachi-poi-db`（確認預設 Python `urllib` User-Agent 回傳 `1010` 為 WAF 正常攔截）。
  - **Google Cloud Run**: `https://antigravity-backend-589255638719.us-central1.run.app`（`1.2.9-hardened`，DB 連線正常；針對 `/api/cloudinary-test` 等無效/歷史探針之 `HTTP 404` 日誌已確認為無對應路由的預期回應）。
  - **Supabase (`oudnkmigfueuyvxqpqwn`)**: 線上資料量 `221` users、`252` trips、`1,739` notifications；在 `153` 筆含成員行程中，孤兒 `SYSTEM` 行程已降至 `0`。

### B. 認證 PoP 寬限期保留與快取清除完整性
- **問題根因**: 前端 `getCachedToken()` 若在過期瞬間直接清除 `tabiji_session_token`，會導致 `ensureValidSession()`、`rotateAccountRecoveryKey()` 與 `fetchLatestRecoveryKey()` 無法帶入舊 JWT 觸發後端 `auth.py` 的 90 天寬限期 PoP 驗證。
- **修正落點**:
  - [auth-session.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/auth-session.ts): 清除過期 `tabiji_session_token` 前將語法有效之舊 JWT 備份至 `tabiji_pop_token`，並僅於明確登出、重設或 visitor 401 時一併清空。
  - [profile-view.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/profile-view.tsx): `handleClearCache()` 完整保留 `user_uuid`、`user_recovery_key`、`tabiji_session_token`、`tabiji_pop_token`、`user_nickname`、`user_avatar` 6 項憑證與個人資料鍵值。

### C. Supabase Vault HMAC Webhook 與純 Deno WebCrypto Cloudinary 清理
- **問題根因**: Supabase 代管 Postgres 未設置 `app.settings.service_role_key`，導致舊觸發器對 `cleanup-cloudinary` 累積 `338` 筆 `HTTP 401` 錯誤；此外 Deno Edge Runtime 不相容 `npm:cloudinary` (`vm2`)，且 `itineraries.public_id` 實為 `pub_*` 分享代碼而非 Cloudinary Asset ID。
- **修正落點**:
  - [20261115_webhook_cleanup_cloudinary_vault_hmac.sql](file:///d:/Project/tabiji/travel-pwa/supabase/migrations/20261115_webhook_cleanup_cloudinary_vault_hmac.sql) 與 [cleanup-cloudinary/index.ts](file:///d:/Project/tabiji/travel-pwa/supabase/functions/cleanup-cloudinary/index.ts): 改用 Vault `cleanup_webhook_secret` 與 `SECURITY DEFINER` + `extensions.hmac(..., 'sha256')` 對 `${ts}.${payload}` 簽章，並以限定 `service_role` 的 `verify_cleanup_webhook_signature` RPC 驗證 300 秒重放視窗；Edge Function 改以純 Deno WebCrypto SHA-1 呼叫 Cloudinary Destroy API，資料庫觸發器覆蓋 `expenses`、`itineraries`、`itinerary_items` 三表，其餘 `users.avatar_url` 與 `trip_capsule_entries.photo_url` 由後端 [gdpr.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/gdpr.py) / [users.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/users.py) 接手清理。
  - **實測成效**: `net._http_response` 於修復後 3 小時視窗內已轉為 `41/41` (`100% HTTP 200`, `0` 錯誤)。

---

## 3. 技術債與後續營運注意事項 (Technical Debt & Ops Follow-up)

1. **Cloud Run Cloudinary 環境變數核對**: 使用者已確認 `CLOUDINARY_API_KEY` 與 `CLOUDINARY_API_SECRET` 存在於 Cloud Run，仍建議檢查 `CLOUDINARY_CLOUD_NAME=dnpcnwrcu`（或 `NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME`）是否已同軌設定，以利後端清理與頭像模組零落差運作。
2. **Supabase Migration 檔名與版本號對齊**: 本地新增 SQL 採用 8 碼日期前綴（`20261115_*.sql`），而線上 `schema_migrations` 為 MCP 套用產生之 14 碼版本號（`20261115124422`、`20261115135303`）。未來若改用 `supabase db push` CLI，須先對齊遠端 `schema_migrations` 或調整檔名以避免重複執行。

---

## 4. 第二階段增量交付：`LandingPage` 載入鎖定、防反白與 IME 守衛 (`e5f24c7`)

> **時間戳記**: `2026-11-16 03:14` (UTC+8)
> **對應提交**: `e5f24c7` (`feat(landing): add loading lock, spinner feedback and IME submit guard`)

### 🟢 Features & Fixes
- **變動範圍 (`4` 檔案，合計 `+856 / -72`，忽略縮排 `-w` 為 `+808 / -24`)**:
  - [landing-page.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/landing-page.tsx): `+240 / -72`（`-w`: `+192 / -24`）
  - [remaining.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/i18n/remaining.ts): `+8 / -0`（新增 `landing_preparing_journey`、`landing_login_failed`、`landing_recovering`、`landing_recover_failed` 雙語鍵）
  - [translations.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/translations.ts): `+8 / -0`（同步 4 組雙語鍵）
  - [landing-page-loading-lock.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/landing-page-loading-lock.test.tsx): `+600 / -0`（13 項鎖定、防連點、IME、卸載清理與錯誤回退測試）
- **核心行為**:
  - 保留原有 `ensureValidSession()`、`generateUUID()` 離線降級與 `usersApi.updateProfile()` 底層邏輯不變。
  - 點擊「開始旅程」或「帳號還原」於校驗通過後，立即執行 `clearActiveSelection()` 收合並清除既有的文字反白與 `blur()`，同步鎖定 `useRef` 互斥閘門與 `useState`（`isLoggingIn` / `isRecovering`）。
  - 鎖定期間對外層表單容器、`<Input>` 與 `<Button>` 全面施加 `disabled` + `aria-busy` + `select-none`，並顯示 `<Loader2 className="size-5 animate-spin shrink-0" />`（「正在準備旅程...」 / 「還原中...」）。
  - 雙輸入框補齊 `enterKeyHint="go"` 與 `!e.nativeEvent.isComposing` IME 組字防誤觸守衛，以及 `isMountedRef`、`recoverTimerRef` 卸載清理與 `typeof document.startViewTransition === 'function'` 型別降級保護。

### 🛡️ 踩坑與測試品質記錄
- **SVG 圖示尺寸覆寫**: `button.tsx` 之 `[&_svg:not([class*='size-'])]:size-4`（權重 `(0,2,1)`）會覆寫 `w-5 h-5`，改用 `size-5` 維持 `20px` 視覺量體。
- **CSS Cascade Layer 與指標穿透**: Tailwind v4 `.select-none` 依賴 `globals.css` 未分層 `.select-none`（`!important`）覆蓋 `input` 預設 `user-select: text !important`；同時將 `select-none` 掛載於載入中表單外層容器，吸收 `disabled:pointer-events-none` 的指標穿透選取風險。
- **全棧 Quality Gate 實測**: `tsc --noEmit` (0)、`eslint --max-warnings=0 .` (0)、Frontend Vitest (`110` 檔 / `1064` passed / `4` pre-existing skipped)、Backend Pytest (`643` passed / `5` skipped)、`next build` (0)、`neural_seam_harness.py` (`10/10` PASS)、`validate_security_ledger.py` (`377` targets PASS)。

### 🎯 Next Steps
- 確認提交與遠端同步指令（`git push origin main`）。
- 實機 iOS Safari 針對 2–3 秒網路延遲進行觸控長按與實體 IME 煙霧測試。

---

## 🧬 Machine-Executable Invariant Rules

```json
[
  {
    "domain": "state_cache",
    "type": "FAILED_PATH",
    "id": "FP-063",
    "title": "過期 JWT 預先清除導致 90 天寬限期 PoP 驗證失效",
    "content": "getCachedToken() 若在 ensureValidSession()、rotateAccountRecoveryKey() 或 fetchLatestRecoveryKey() 讀取前直接移除過期 tabiji_session_token，會導致後端 auth.py 90 天寬限期 PoP 驗證失敗。必須在清除前將語法有效的過期 JWT 備份至 tabiji_pop_token（僅於登出、重設或 visitor 401 時清除），且 profile-view handleClearCache() 必須完整保留 user_uuid、user_recovery_key、tabiji_session_token、tabiji_pop_token、user_nickname 與 user_avatar 六項鍵值。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-064",
    "title": "Supabase Trigger 讀取 app.settings 靜默 NULL 造成 401 與套件欄位誤判",
    "content": "Supabase 代管 Postgres 未預設 app.settings.service_role_key，Trigger 取值為 NULL 會引發 Webhook 連續 HTTP 401（實測曾累積 338 筆失敗）；同時 Deno Edge Runtime 無法運行含 vm2 的 npm:cloudinary，且 itineraries.public_id 為 pub_* 分享代碼而非 Cloudinary Asset ID。應改用 Vault cleanup_webhook_secret 搭配 SECURITY DEFINER + extensions.hmac(..., 'sha256') 與 verify_cleanup_webhook_signature RPC (300s 視窗)，Edge Function 使用純 Deno WebCrypto SHA-1，並以 DB 三表觸發器 (expenses/itineraries/itinerary_items) 搭配後端清理 users.avatar_url 與 trip_capsule_entries.photo_url。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BE-WEBHOOK-VAULT-01",
    "title": "DB-to-Edge Webhook Vault HMAC 與純 Deno WebCrypto 清理雙軌契約",
    "content": "凡由 Postgres Trigger 經 pg_net 呼叫 Supabase Edge Function 之非同步清理流程，強制使用 Vault 密鑰 + HMAC-SHA256 防重放驗簽 (300s) 與純 Deno WebCrypto 簽名外部請求；禁止依賴 app.settings.* 或在 Edge Function 引入 npm:cloudinary，並須透過 net._http_response 實測 HTTP 200 回執率。"
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-065",
    "title": "未盤點線上五端拓撲即執行全面靜態加固造成過度工程回滾",
    "content": "未先查證 Vercel 線上 Commit、Cloud Run 路由與環境變數、Cloudflare Worker WAF 規則（如 Python urllib UA 觸發 1010）及 Supabase 即時 schema_migrations / pg_net 日誌前，依靜態假設發起多輪全面修改會產生脫離真實部署環境的 70+ 過度工程檔案並被迫全數還原。另使用 Supabase CLI db push 前須確認 8 碼檔名與線上 14 碼版本號對齊。"
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-DEVOPS-LIVE-TOPOLOGY-01",
    "title": "安全稽核前必先完成線上五端真實拓撲 Grounding",
    "content": "啟動跨模組資安審計與修復前，必須優先以實測驗證 Vercel、Google Cloud Run、Cloudflare Workers/D1、Cloudinary 與 Supabase 線上現況與日誌，嚴禁僅憑離線臆測驅動跨檔案大改；Cloud Run 日誌對無效測試路徑 /api/cloudinary-test 回傳 HTTP 404 屬正常未命中行為。"
  },
  {
    "domain": "ios_ui",
    "type": "FAILED_PATH",
    "id": "FP-066",
    "title": "Button SVG 預設 size-4 覆寫與 disabled 指標穿透文字反白陷阱",
    "content": "button.tsx 宣告 [&_svg:not([class*='size-'])]:size-4（權重 0,2,1），會將僅設定 w-5 h-5 的 Loader2 圖示縮小至 16px，必須顯式傳入 size-5 才能保持 20px；此外 button/input 之 disabled:pointer-events-none 會使鎖定期間的觸控長按穿透至父層容器，必須同步於送出前執行 clearActiveSelection() 收合選區並 blur()，且在鎖定狀態對表單外層容器掛載未分層 .select-none（!important）覆蓋 input 預設 user-select: text。"
  },
  {
    "domain": "ios_ui",
    "type": "INVARIANT_RULE",
    "id": "INV-UI-LOADING-LOCK-01",
    "title": "非同步表單雙軌互斥鎖、IME 組字守衛與卸載安全轉場法則",
    "content": "凡涉及非同步身分建立或遠端請求之登陸/還原表單，送出前須先通過空白與格式校驗，再同步鎖定 useRef（阻斷單幀連點重入）與 useState（鎖定輸入框、主按鈕與切換鈕 disabled/aria-busy/select-none）；輸入框 Enter 送出必須掛載 !e.nativeEvent.isComposing；document.startViewTransition 必須檢查 typeof === 'function'；且非同步完成與延遲換場計時器必須受 isMountedRef 與 unmount cleanup 保護，異常時於 catch 解鎖並以 toast.error 呈現，嚴禁對 onClick 外拋 unhandled rejection。"
  }
]
```
