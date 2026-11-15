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
  }
]
```
