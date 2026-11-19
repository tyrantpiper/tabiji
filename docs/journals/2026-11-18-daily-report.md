# 📅 Daily Report - 2026-11-18 (孤兒 UUID 自癒、三總管密鑰獨立、Supabase `sb_*` 無痛切換與雙網域稽核)

> **時間範圍**: `2026-11-18 00:00 ~ 23:59` (UTC+8)
> **當日納入 Commit**:
> - [`8e63b56`](file:///d:/Project/tabiji/travel-pwa/backend/routers/auth.py) (`2026-11-18T20:30:20+08:00`): `fix(auth,edge,ai): heal orphan uuid sessions, support supabase sb_ keys, and harden ai pipeline` — **`39 files changed, 4303 insertions(+), 276 deletions(-)`**（含 `2026-11-17` Stage 1 AI 變更 + Auth/Edge/`sb_*` 切換）
> - [`bdf1d8a`](file:///d:/Project/tabiji/travel-pwa/frontend/lib/auth-session.ts) (`2026-11-18T20:54:19+08:00`): `fix(auth): guard concurrent 401 token cleanup in fetchLatestRecoveryKey` — **`2 files changed, 45 insertions(+), 2 deletions(-)`**
> **資安報告與品質驗證**:
> - 當日線上五端實證稽核報告：[security_sentinel_report_2026-11-18_prod_auth_edge_audit.md](file:///d:/Project/tabiji/travel-pwa/docs/security/reports/2026-11/security_sentinel_report_2026-11-18_prod_auth_edge_audit.md) 與補丁 [`patch_candidate_prod_auth_edge_audit_2026-11-18.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_prod_auth_edge_audit_2026-11-18.diff)（留置次日零點 `be7a32c` 部署）
> - `validate_security_ledger.py`: `402 targets (175 remediated, 53 verified/unresolved, 174 dismissed/safe)`；後端 Pytest `705 ➔ 709 passed, 5 skipped`；前端 Vitest `115 files / 1082 ➔ 116 files / 1098 passed, 4 skipped`

---

## 1. 工程與檔案異動清單（2026-11-18）

- **認證自癒與 `sb_*` 新制相容（`8e63b56`, `bdf1d8a`）**:
  - [backend/routers/auth.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/auth.py): 對不存在於 `users`/`trip_members`/`itineraries` 之合法孤兒 UUIDv4 實作就地註冊並簽發首組 `tbj_rec_*`（含併發 PK 衝突回查防護）。
  - [backend/utils/deps.py](file:///d:/Project/tabiji/travel-pwa/backend/utils/deps.py)、[backend/main.py](file:///d:/Project/tabiji/travel-pwa/backend/main.py)、[backend/routers/users.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/users.py): 新增 `build_supabase_rest_headers()`，辨識 `sb_*` 金鑰並僅掛載 `apikey` 標頭（省略 `Authorization: Bearer`）；`get_verified_user()` 對 `iss == "tabiji-core"` 直接短路拒絕。
  - [supabase/functions/notify-broadcast/index.ts](file:///d:/Project/tabiji/travel-pwa/supabase/functions/notify-broadcast/index.ts)（納入 Git 版控 `v5`）、[notify-countdown/index.ts](file:///d:/Project/tabiji/travel-pwa/supabase/functions/notify-countdown/index.ts)、[notify-event/index.ts](file:///d:/Project/tabiji/travel-pwa/supabase/functions/notify-event/index.ts)、[cleanup-cloudinary/index.ts](file:///d:/Project/tabiji/travel-pwa/supabase/functions/cleanup-cloudinary/index.ts): 全面支援 `SUPABASE_SECRET_KEYS` / `sb_secret_` 與 `apikey` 標頭驗證。
  - [frontend/lib/stores/tripStore.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/stores/tripStore.ts): 移除模組載入期偷跑產生未註冊 UUID 與呼叫 `ensureValidSession()` 之副作用。
  - [frontend/components/views/landing-page.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/landing-page.tsx): 延後寫入 `user_nickname` 至取得有效 `uuid` 之後，並透過 `clearPersistedTripSelection()` 雙清兩個持久化行程鍵與過濾 `"null"` / `"undefined"`。
  - [frontend/components/app-client-layer.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/app-client-layer.tsx): 新增 `readActiveUserUuid()`、`syncUserChannel()`，動態監聽 `user-login-state-changed` 與 `storage` 綁定/清理 `user-sync:${uuid}`。
  - [frontend/lib/auth-session.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/auth-session.ts): 新增 `ensureValidSession(forceRefresh)` 備份 `tabiji_pop_token` 再重發、於 `fetchLatestRecoveryKey`（`bdf1d8a`）加入 Compare-And-Swap 檢查（`localStorage.getItem(TOKEN_KEY) === token`），防堵遲到 `401` 誤刪剛刷新之新 JWT。
  - 測試覆蓋：[test_orphan_uuid_and_key_rotation_safety_net.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_orphan_uuid_and_key_rotation_safety_net.py)、[orphan-uuid-and-key-rotation-safety-net.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/orphan-uuid-and-key-rotation-safety-net.test.tsx)、[auth-session-resilience.test.ts](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/auth-session-resilience.test.ts)、[supabase-edge-functions-secret-keys.test.ts](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/supabase-edge-functions-secret-keys.test.ts)、[landing-page-orphan-and-dual-storage.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/landing-page-orphan-and-dual-storage.test.tsx)、[app-client-layer-realtime-sync.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/app-client-layer-realtime-sync.test.tsx)、[trip-store-and-supabase-init.test.ts](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/trip-store-and-supabase-init.test.ts)。

---

## 2. 本日實戰事件、雲端切換與晚間稽核結果

### 🟢 Features & Fixes
- **即時捕捉線上 `iPhone OS 18_7` 卡死案例**：調閱 Cloud Run 日誌定位特定裝置連續 8 次於冷啟動撞上 `POST /api/auth/session -> 401`（過去 14 天累計 `50` 筆同型失敗），並一舉修正孤兒 UUID 建檔與前端註冊時序顛倒漏洞。
- **零停機三總管密鑰獨立與 `sb_*` 切換上線 (`antigravity-backend-00199-d2w`, `dpl_2C15MAiueeD645pAxuLAdzPcoqdV`)**：
  - 固定 `VAULT_MASTER_KEY` (`vault-master-key:2`)、`RECOVERY_PEPPER` (`recovery-pepper:latest`)、輪替全新 `SESSION_SECRET_KEY` 上 Cloud Run 與 Cloudflare `tabijiapp-edge-shield`；Vercel 與後端切換為 `sb_publishable_` / `sb_secret_`。
  - 查核 Supabase `pg_cron` (`trip-countdown-daily`) 與資料庫觸發器無寫死舊 JWT，且確認線上 Legacy `anon` key 已處於 `"disabled": true`、`GET /api/health/deep` 雙網域均為 `200 healthy`。

### 🏛️ Architecture Decisions
- **AD-226（三層身分契約對齊與孤兒 UUID 無感就地自癒）**：確立 `user_uuid`（資料庫外鍵唯一身分）、`tbj_rec_*`（可輪替之再登錄密鑰）、`tabiji_session_token`（30 天 JWT 階段憑證）三層定義；僅當 UUID 確切存在於 DB 且經輪替卻未提供持有證明時才要求原機驗證，未建檔之合法孤兒 UUID 直接現場建檔並核發首把 `tbj_rec_*`。
- **AD-227（雙網域稽核駁回提案與安全替代方案 — 已納入次日 `be7a32c`）**：在夜間稽核中明確駁回「僅憑同源 `expected_user_id` 即免驗證替已升級帳號解密保險庫」的危險草案（避免依可枚舉 UUID 造成 ATO 與繞過 ADR-009）；改採對 `auth.py` `/session` 與 `get_verified_session_with_grace` 引入可選 `LEGACY_SESSION_SECRET_KEY` 與 `LEGACY_VAULT_MASTER_KEY` 過渡解密（一般業務端點 `deps.get_verified_user` 維持只認新密鑰以迫使前端自動升級）。

### 🔴 Technical Debt
- **DEBT-CLOUD-SECRET-CUTOVER-01 `[RESOLVED in 8e63b56]`**：已完成三把系統母鑰自 `SUPABASE_KEY` 解耦及 Vercel/Cloud Run/Edge Functions `sb_*` 切換；後續雙網域細部防線與 Edge BOLA 修補已生成補丁於 [security_sentinel_report_2026-11-18_prod_auth_edge_audit.md](file:///d:/Project/tabiji/travel-pwa/docs/security/reports/2026-11/security_sentinel_report_2026-11-18_prod_auth_edge_audit.md)，排入 `2026-11-19 00:51` 部署。
- **DEBT-LEGACY-SECRET-SUNSET-01（Open）**：(1) GCP Secret Manager `LEGACY_SESSION_SECRET_KEY`（`legacy-session-secret-key:2` 含 `H1_raw`/`H1_strip`/`H1_norm`/`H2_raw`）與 `supabase-key:1` 於 90 天寬限期滿（`2027-02-16` 後）併後續部署順手清理；(2) 至 Supabase Dashboard 確認 Legacy `service_role` 已停用（MCP API 未回傳此欄位）；(3) 資料庫 `vault.secrets` 中 `2026-04-25` 建立之舊 `service_role_key` 紀錄可於確認無舊函式相依後移除。

### 🛡️ Failed Paths
- **FP-095（模組載入期自生未註冊 UUID + 註冊順序顛倒造成孤兒帳號鎖死陷阱）**：`tripStore.ts` 在載入期自造 UUID 塞入 `localStorage` 並隨即觸發 `ensureValidSession()`，且 `landing-page.tsx` 先寫入 `user_nickname` 再呼叫註冊，導致網路慢或未註冊完成的瀏覽器被 `isUserLoggedIn()` 判為已登入，隨即被 `/api/auth/session` 拒絕 `401` 陷入無解重認證彈窗迴圈。
- **FP-096（GCP Secret Manager 舊版金鑰含尾端 CRLF / 空白致保險庫多版本派生分裂陷阱）**：實際切換實庫 Vault 時僅 `110/120` 筆直接解密成功，餘 `10/120` 筆因過去 `supabase-key:1` 寫入時夾帶尾端 `\r\n`／空白且舊 `deps.py` 未做 `.strip()` 而由不同位元組版本派生。須於記憶體比對 `tbj_rec_*` HMAC 後將全數 `120/120` 筆正規化重封裝為單一基準金鑰並留存候選衍生雜湊於 `LEGACY_SESSION_SECRET_KEY`。
- **FP-097（`fetchLatestRecoveryKey` 遲到 `401` 回應盲刪已刷新 JWT 之競態陷阱 — Commit `bdf1d8a`）**：頁面啟動同時發送 `/api/trips` 與 `/api/auth/credential`；前者先獲 401 並換回新 Token 寫入 `localStorage`，後者持舊 Token 遲到回傳 401 時未核對 `localStorage.getItem(TOKEN_KEY) === token` 即無條件清空 `TOKEN_KEY`，瞬間抹除剛換好的新憑證。
- **FP-098（SWR `15s` 輪詢大於 `10s / 5s` 授權冷卻窗 + Edge Masking 掩蓋 `/api/cloudinary-test` 暴露陷阱）**：夜間對 `travel-pwa-five.vercel.app` 雙網域實測發現：(1) 前端 `lastExchangeFailedAt < 10000ms` 與 `lastDismissedAt < 5000ms` 小於 SWR 15 秒輪詢，形成無限 401 與彈窗復發；(2) `www.tabijiapp.com` 因 Edge Shield 轉發 Cloud Run 回 `404` 掩蓋了 `travel-pwa-five.vercel.app/api/cloudinary-test` 直接回 `200` 洩漏密鑰資訊的事實；(3) `tabijiapp-poi-service.workers.dev` 公網可憑偽造 `X-User-ID` 繞過 Edge Shield 直接讀取真實 D1 資料，且 `edge-shield` 貪婪正則於 `www` 攔截誤殺 `GET /api/poi/categories` 與 `/nearby`。

### 🎯 Next Steps
- 立即複審並部署 [patch_candidate_prod_auth_edge_audit_2026-11-18.diff](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_prod_auth_edge_audit_2026-11-18.diff) 至 Cloudflare、Cloud Run 與 Vercel，並於實機複測雙網域同步與周邊 POI 搜尋。

---

## 🧬 Machine-Executable Invariant Rules

```json
[
  {
    "domain": "state_cache",
    "type": "FAILED_PATH",
    "id": "FP-095",
    "title": "模組載入期自生未註冊 UUID 與提前寫入 user_nickname 引發 401 鎖死陷阱 (FP-095)",
    "content": "tripStore.ts 嚴禁在模組 import 期生成本地 UUID 寫入 localStorage 並隨即呼叫 ensureValidSession()；LandingPage handleLogin 嚴禁在後端註冊完成前先行寫入 user_nickname 並必須過濾 'null'/'undefined' 字串。否則未入庫的孤兒 UUID 會使 isUserLoggedIn() 回傳 true，開機即吃 /api/auth/session 401 陷入無解的引繼碼重驗證死結。"
  },
  {
    "domain": "state_cache",
    "type": "FAILED_PATH",
    "id": "FP-097",
    "title": "fetchLatestRecoveryKey 遲到 401 盲刪剛刷新 Session JWT 之競態陷阱 (FP-097)",
    "content": "並發請求中若其他路徑已透過 ensureValidSession(true) 換發並寫入新 tabiji_session_token，較慢返回之背景 /api/auth/credential 401 回應在清除或搬移 TOKEN_KEY 前必須嚴格執行 Compare-And-Swap Check (if (localStorage.getItem(TOKEN_KEY) === token))，禁止無條件刪除已更新之最新憑證。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BE-SB-SECRET-HEADER-01",
    "title": "Supabase sb_* 非 JWT 金鑰標頭分離與禁止轉發瀏覽器 UA 法則 (AD-227)",
    "content": "Supabase sb_publishable_* 與 sb_secret_* 非 JWT 格式，所有直連 PostgREST (/rest/v1/*) 與 Edge Functions 之 HTTP 請求必須透過 build_supabase_rest_headers() 僅置入 apikey 標頭並嚴禁放入 Authorization: Bearer（Authorization 僅保留給使用者 JWT）；且後端不得對 Supabase API Gateway 轉發使用者瀏覽器 User-Agent，避免觸發 Gateway 401 封鎖。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-096",
    "title": "Secret Manager 尾端換行空白導致派生主密鑰分裂與 Vault 解密失敗陷阱 (FP-096)",
    "content": "以未經 .strip() 的原始密鑰位元組作為 PBKDF2/SHA-256 派生輸入時，GCP Secret Manager 版本若含尾端換行 (\\r\\n) 或空白會分裂產生多個 H1/H2 衍生金鑰版本（實測曾致 10/120 保險庫密文解不開）。密鑰派生與遷移驗證必須顯式考量 raw/strip 候選並原地統一重封裝單一乾淨主鑰。"
  }
]
```
