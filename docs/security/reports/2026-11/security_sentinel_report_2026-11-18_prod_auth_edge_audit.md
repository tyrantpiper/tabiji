# 🛡️ Security Sentinel 對抗式稽核與五大線上環境實證報告 (2026-11-18)

> **Audit Mode**: Live 5-Stack Grounding + `runner.py` (`--mode duel` & `--mode adaptive`) + `GitWorktreePool` Sandbox + Mantis Block G
> **Ledger Totals**: `402` targets (`175` remediated, `53` verified/unresolved, `174` dismissed/safe)
> **Unified Patch**: [`docs/security/history/patches/patch_candidate_prod_auth_edge_audit_2026-11-18.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_prod_auth_edge_audit_2026-11-18.diff)

---

## 1. 五大線上真實部署環境實證結果 (Live Production Telemetry)

| 服務層 | 線上實測目標 | 實證證據 (2026-11-18) | 對真實使用者之影響結論 |
|---|---|---|---|
| **Cloud Run** | `antigravity-backend` (`us-central1`, rev `00199-d2w`) | `/api/health/deep` 回傳 `200 healthy (1.2.9-hardened)`；秘密 `SUPABASE_KEY` (`latest`), `VAULT_MASTER_KEY` (`2`), `RECOVERY_PEPPER`, `SESSION_SECRET_KEY` 已掛載；**未掛載 `LEGACY_SESSION_SECRET_KEY`**。截至 `2026-11-18T14:04:03Z` 仍見 `3f7abf22-...` 於 `travel-pwa-five.vercel.app` 連續觸發 `/api/auth/session` 與 `/api/trips*` `401`。 | **活躍缺陷**：(1) 未掛載輪替過渡金鑰且缺乏多密鑰驗簽支援；(2) `travel-pwa-five.vercel.app` 舊分頁缺 `tbj_rec_*` 觸發 15 秒 SWR `401` 輪詢風暴與 5 秒後彈窗復發。 |
| **Vercel** | `www.tabijiapp.com` & `travel-pwa-five.vercel.app` (`dpl_2C15MAiueeD645pAxuLAdzPcoqdV`, `bdf1d8a`) | 雙網域提供完全一致之 immutable chunks (`117-6l6l-we00.js`, `sb_publishable_...`) 與 `sw.js` (`48586` bytes)。**新發現**：`GET https://travel-pwa-five.vercel.app/api/cloudinary-test` 回傳 **`200`** 並外洩 `apiSecretLength: 27`, `apiSecretFirst4: "[REDACTED]"`, `apiSecretLast4: "[REDACTED]"` 及簽章產生器（`www.tabijiapp.com` 因 Edge Shield 導流至 Cloud Run 而回傳 `404`）。 | **高危實證缺陷**：`app/api/cloudinary-test/route.ts` 於 Vercel 原生網域暴露測試簽章與部分機密資訊；`R6 (sw.js 舊版)` 則為**誤報**（Vercel prebuild 已自動執行 `build-sw.mjs`）。 |
| **Supabase** | `oudnkmigfueuyvxqpqwn` | `public.users`: `234` 筆（`120` 升級、`114` legacy、`1` 已輪替 `3f7abf22-...`, `credential_version=4`）。4 支 Edge Functions (`cleanup-cloudinary`, `notify-event`, `notify-countdown`, `notify-broadcast`) 皆為 `ACTIVE` 並相容 `sb_secret_`。 | **已安全**：Secret Key 切換完整正常。 |
| **Cloudinary** | `dnpcnwrcu` / `cloudinary-proxy` | `POST /api/sign-cloudinary` 雙網域皆回傳 `200`（即使省略 `folder` 參數亦簽章成功）；`cloudinary-proxy` `OPTIONS -> 204`、`/w_999/test.jpg -> 403`。 | **已修補待部署**：強制 `ALLOWED_FOLDERS` 必填白名單與 `ALLOWED_PARAM_KEYS` 嚴格校驗（配合修復 `/api/cloudinary-test` 生產環境 fail-closed `404`）。 |
| **Cloudflare** | `tabijiapp-edge-shield` & `tabijiapp-poi-service` | `wrangler secret list` 與 `2026-11-18T12:31:04Z Secret Change` 證實 `edge-shield` 已設定 `SESSION_SECRET`（偽造 JWT 實測皆回傳 `401`）。**兩項嚴重實證發現**：(1) `tabijiapp-poi-service` 開啟了 `workers.dev` (`https://tabijiapp-poi-service.ryanpig228.workers.dev/api/poi/all`)，僅憑偽造 `X-User-ID` 即回傳 **`HTTP 200`** 實際 D1 資料，**完全繞過 `tabijiapp-edge-shield` 驗證**；(2) **Round 3 複驗實測新發現**：`GET https://www.tabijiapp.com/api/poi/categories` 與 `/api/poi/nearby?...` 亦被 `edge-shield` 貪婪正則 `/^\/api\/poi\/[^/]+.../` + `'GET'` 誤攔轉入 `POI_SERVICE` 而回傳 **`401`/`404`**（Cloud Run 實為 `200`）。 | **重大 BOLA 繞過 + 邊緣路由誤攔截**：於 `poi-service/wrangler.jsonc` 明設 `workers_dev: false` / `preview_urls: false`、於 `poi-service/worker.js` 阻斷 `.workers.dev` 與未驗簽 `atob()`；於 `edge-shield/worker.js` 明確排除 `BACKEND_POI_ENDPOINTS` 且僅對 `PATCH/DELETE/OPTIONS` 路由動態 D1 `:id`、並補齊 `UUID_V4_REGEX` 與 `Authorization` 剝除。 |

---

## 2. 對先前提案 (`implementation_plan.md` / `step 1080`) 之駁斥與架構裁決

先前計畫曾提議「若 `expected_user_id == clean_uid` 且請求來自已升級帳號，免 Bearer PoP 憑證直接解密雲端保險庫 (`recovery_key_encrypted`) 並簽發新 JWT」。此提議已於本次審查中**明確駁斥與拒絕實作**：
1. `user_uuid` (`clean_uid`) 於 URL、行程建立者 (`itineraries.created_by`)、成員清單及歷史 `X-User-ID` 標頭中均屬可枚舉/非機密識別碼。
2. 實測線上 `POST /api/auth/session` 攜帶 `{"recovery_key": "3f7abf22-...", "expected_user_id": "3f7abf22-..."}` 兩網域皆正確拒絕 `401`，若按原計畫放行將直接構成 **Critical Account Takeover (ATO)** 與 **ADR-009 輪替撤銷防線失效**。
3. **正確替代實作**：保持 Proof-of-Possession 與 `db_ver > 1 and token_ver < db_ver` 硬阻斷，於 `backend/routers/auth.py` 僅在 `POST /api/auth/session` PoP 橋接與 `get_verified_session_with_grace` 支援可選 `LEGACY_SESSION_SECRET_KEY` / `PREVIOUS_SESSION_SECRET_KEY` 與 `LEGACY_VAULT_MASTER_KEY` 過渡解密，並讓一般業務端點 `deps.get_verified_user` 維持僅認現用密鑰以強制靜默換發最新憑證。

---

## 3. Chesterton's Fence Code Archaeology Matrix

| 目標檔案與防衛機制 | Legacy Function / 原職責 | Design Intent / 設計意圖 | Regression Risk / 移除風險與承接機制 |
|---|---|---|---|
| `backend/routers/auth.py` (`create_or_exchange_session`, `get_verified_session_with_grace`) | 僅使用單一 `SESSION_SECRET_KEY` 驗簽 PoP 與 90 天寬限 Token | 強制單一信任根與 ADR-009 版本號撤銷檢查 | 若直接改用無憑證 `expected_user_id` 比對將導致 ATO；改採 `decode_device_session_jwt()` 依序驗 `current` 與設定檔 `LEGACY_SESSION_SECRET_KEY`，並完整保留 `db_ver > 1` 撤銷閘門 |
| `frontend/lib/auth-session.ts` (`lastFailedExchangeFingerprint`, `isReauthDismissedInMemory`, `backedUpValidToken`) | 10 秒換票失敗冷卻、5 秒彈窗關閉防震盪與 `forceRefresh` 暫態回補 | 避免連發換票、誤關即復發與離線/5xx 丟失有效憑證 | 原 15s SWR > 10s 冷卻仍觸發風暴，且殘留 `< 10s` 全域冷卻條件在跨分頁憑證指紋更新時誤鎖新憑證並於 `forceRefresh` 丟失 `backedUpValidToken`；現改為純指紋鎖定（指紋不變於本頁永久阻斷、指紋變更秒級解鎖）、JSON 防碰撞指紋序列化、`isReauthDismissedInMemory`、`wasLastAuthExchangeTransientFailure()` 與 `postFetchFingerprint` 非 401 暫態回補承接 |
| `frontend/lib/api.ts` (`!urlStr.includes("/api/poi/")`) & `app/api/poi/[...path]/route.ts` | 原跳過 `/api/poi/*` 401 攔截且代理吞沒 `401`/`catch` 回傳 `200 []` | 防止跨源/離線誤殺主會話 | 代理吞沒 `401` 導致靜默換票失效且 `usePoiPool` 以 `[]` 覆寫本地 IndexedDB；現於代理層如實透傳 `401`/`502`，於 `apiFetch` 放行 `/api/poi/*` 1 次靜默換票並隔離其失敗不誤刪主會話 |
| `frontend/app/api/cloudinary-test/route.ts` & `app/api/sign-cloudinary/route.ts` | 開發除錯端點與未強制必填 `folder` 之簽章代理 | 開發驗證 `api_sign_request` 與上傳路徑隔離 | `cloudinary-test` 於生產環境 fail-closed `404` 並移除密鑰前後綴外洩；`sign-cloudinary` 強制 `ALLOWED_FOLDERS`、`ALLOWED_PARAM_KEYS`、正整數 `timestamp` 與 `public_id` 正規防禦 |
| `cloudflare/edge-shield/*` & `cloudflare/poi-service/*` | 邊緣 JWT 閘道與 D1 POI 微服務 | Service Binding 內部隔離 | `edge-shield` 與 `poi-service` 均設 `workers_dev: false` / `preview_urls: false`、補齊 else `Authorization` 剝除與嚴格 `typeof payload.exp !== "number" || !Number.isFinite(payload.exp)` 檢查；`poi-service` 硬拒 `.workers.dev` (`403`) 與未驗簽 `atob()` |

---

## 4. 沙盒、全棧測試與 Chrome MCP 端到端實證摘要

- **Security Sentinel CLI (`runner.py`) & 帳本守恆**:
  - `mode=duel`: 第一批 8 項因 Windows nested `agy.exe --sandbox` 逾時回傳 `INCONCLUSIVE`。
  - `mode=adaptive`: 第一批 8 項取得 `6 CONFIRMED / 2 DISMISSED / 0 INCONCLUSIVE`；第二批 `poi-service/wrangler.jsonc` 取得 `CONFIRMED`；補測修補後增量候選 [`candidates_review_delta_2026-11-18.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/candidates/candidates_review_delta_2026-11-18.json) 取得 `5/5 DISMISSED / 0 INCONCLUSIVE` ([`findings_review_delta_2026-11-18.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/findings/findings_review_delta_2026-11-18.json))；第二輪針對 `auth-session.ts` 10s 指紋解鎖補測 [`candidates_auth_fingerprint_unlock_2026-11-18.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/candidates/candidates_auth_fingerprint_unlock_2026-11-18.json) 取得 `1/1 DISMISSED / 0 INCONCLUSIVE` ([`findings_auth_fingerprint_unlock_2026-11-18.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/findings/findings_auth_fingerprint_unlock_2026-11-18.json))；第三輪對併發 `inFlightSession` 競態、`edge-shield` 後端 POI 誤攔、`/api/poi` 子路徑邊界及 `sign-cloudinary` 整數時間戳/分隔符防禦執行 [`candidates_round3_review_2026-11-18.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/candidates/candidates_round3_review_2026-11-18.json) 取得 `4/4 DISMISSED / 0 INCONCLUSIVE` ([`findings_round3_review_2026-11-18.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/findings/findings_round3_review_2026-11-18.json))。
  - `python scripts/validate_security_ledger.py`: `Verified 402 targets (175 remediated, 53 verified/unresolved, 174 dismissed/safe)`。
  - 統一補丁可逆性：`git apply --check --reverse docs/security/history/patches/patch_candidate_prod_auth_edge_audit_2026-11-18.diff` (`exit 0`)。
- **全棧品質閘門 (隔離沙盒 `.worktrees/sentinel-5251767b` & 主工作區)**:
  - Backend `pytest -q --tb=short`: `709 passed, 5 skipped` (`0 warnings`)
  - Frontend: `npx tsc --noEmit` (`exit 0`) | `npx eslint .` (`exit 0`) | `npx vitest run` (`116 files, 1098 passed, 4 skipped`) | `npm run build` (`exit 0`)
  - Wrangler `--dry-run`: `edge-shield` (`exit 0`, `9.10 KiB`), `poi-service` (`exit 0`, `15.40 KiB`)
- **Chrome DevTools MCP (`@mcp:chrome`) 端到端實測**:
  - 線上隔離驗證 (`www.tabijiapp.com` & `travel-pwa-five.vercel.app`): 訪客冷啟動 `0` 錯誤、`0` 個 `401`、`0` 彈窗，`?lang=en` 正常渲染；實測證實未部署新版前 `travel-pwa-five.vercel.app/api/cloudinary-test` 仍回傳 `200` 外洩部分密鑰、雙網域 `POST /api/sign-cloudinary` 缺 `folder` 仍回傳 `200`。
  - 本機修補生產建置 (`http://127.0.0.1:3000` + `127.0.0.1:8008`): `GET /api/cloudinary-test -> 404`、`POST /api/sign-cloudinary` 缺 `folder`/路徑穿越/非法鍵皆回 `400`、`GET /api/poi/all` 偽造憑證如實回 `401`（不再吞成 `200 []`）；已升級帳號無 `tbj_rec_*` 時僅發 `1` 次 `POST /api/auth/session [401]` 並於彈窗保留後端原錯誤訊息，點擊「稍後驗證 (保持離線)」後歷經 `18.5+` 秒 SWR/focus 重驗與 `10+` 次 `/api/* 401` 仍維持 `0` 彈窗復發與 `0` 換票風暴。

---

## 5. 上線部署待辦 (Human Gate — 需使用者明確確認後方可執行)

1. **Cloud Run (`antigravity-backend`)**: 部署最新 `backend/` 後，若需支援舊輪替期遺留 JWT (未輪替帳號)，於 Secret Manager 掛載 `LEGACY_SESSION_SECRET_KEY`（及視需要 `LEGACY_VAULT_MASTER_KEY`）。
2. **Vercel (`travel-pwa`)**: 部署最新 `frontend/`（消除 `/api/cloudinary-test` 暴露及前端 401 風暴/離線靜默/POI 重試修復）。
3. **Cloudflare (`tabijiapp-edge-shield` & `tabijiapp-poi-service`)**: 執行 `wrangler deploy` 部署 `edge-shield` 與 `poi-service`（並確認 Cloudflare Dashboard / API `tabijiapp-poi-service` 之 `workers.dev` 與 `previews_enabled` 關閉）。
