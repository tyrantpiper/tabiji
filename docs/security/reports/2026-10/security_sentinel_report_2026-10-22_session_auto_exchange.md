# 🛡️ Security Sentinel 對抗式資安審查報告：自動換發與身分憑證自癒彈性 (2026-10-22)

> **審查模式**: Sentinel In-Memory Adversarial PoC Confrontation  
> **資安稽核員**: @security (Security Sentinel)  
> **受審檔案**:
> - `frontend/lib/auth-session.ts` (Trust Boundary: `browser_to_edge`)
> - `frontend/lib/api.ts` (Trust Boundary: `browser_to_edge`)
> - `frontend/lib/hooks.ts` (Trust Boundary: `browser_to_edge`)
> - `frontend/components/app-client-layer.tsx` (Trust Boundary: `browser_to_edge`)
> - `backend/routers/trips.py` (Trust Boundary: `authenticated_to_internal`)
> - `backend/routers/sample_trip.py` (Trust Boundary: `authenticated_to_internal`)
> **候選假說清單**: `docs/security/candidates_session_resilience_2026-10-22.json`  
> **驗證狀態**: 5 項假說 **全數實證成立 (5/5 CONFIRMED via In-Memory PoC)**

---

## 執行摘要 (Executive Summary)

針對 Tabiji「使用者一打開就自動換發身分憑證」之生命週期以及後端身分認證覆蓋率進行全鏈路對抗審查。
審查發現：**前端冷啟動換票與逾期阻斷 (Token Expiration Deadlock) 以及後端 3 處殘留 Header 偽造破口，全數 100% 成立。**

| 假說 ID | 攻擊向量 / 故障模式 | 嚴重等級 | 實測驗證狀態 |
| :--- | :--- | :--- | :--- |
| `frontend/lib/auth-session.ts:token_expiration_deadlock` | 逾期憑證阻斷靜默換票 (Token Deadlock) | **High (CVSS 7.8)** | ✅ **CONFIRMED** |
| `frontend/lib/api.ts:boot_race_condition_unauthenticated_call` | 冷啟動競態無憑證調用 (Race Condition 401) | **High (CVSS 7.5)** | ✅ **CONFIRMED** |
| `backend/routers/trips.py:day_data_header_spoofing` | 偽造 X-User-ID 竄改天數備忘 (Auth Bypass) | **High (CVSS 8.2)** | ✅ **CONFIRMED** |
| `backend/routers/trips.py:ledger_share_header_spoofing` | 偽造 X-User-ID 生成公帳分享碼 (Auth Bypass) | **Medium (CVSS 6.5)** | ✅ **CONFIRMED** |
| `backend/routers/sample_trip.py:seed_sample_header_spoofing` | 偽造 X-User-ID 注入樣本行程 (Auth Bypass) | **Medium (CVSS 6.1)** | ✅ **CONFIRMED** |

---

## 漏洞實體證偽剖析 (Empirical Proof Details)

### 1. PoC 1: 憑證過期後，前端陷入永久 401 死鎖且無法自動換票
- **代碼位置**: `frontend/lib/auth-session.ts:25-56`
- **實測行為**:
  當用戶 `localStorage["tabiji_session_token"]` 存有已過期（或格式異常）之 JWT 時，`getCachedToken()` 僅直接取出字串，未校驗 JWT payload 的 `exp`。
  接著 `ensureValidSession()` 執行 `if (existingToken) return existingToken;`，誤以為仍有有效憑證而直接回傳。
  所有後續 API 請求均帶入已逾期之 Token，後端一律拋出 `401 Unauthorized`，客戶端因永不觸發換票而永久癱瘓。

### 2. PoC 2: 冷啟動併發請求未等待換票完成即送出
- **代碼位置**: `frontend/lib/api.ts:26-47`
- **實測行為**:
  `api.ts` 的 `fetch` 攔截器同步呼叫 `getCachedToken()`。當首次打開 App，`ensureValidSession()` 正在背景非同步換票時，`getCachedToken()` 回傳 `null`。
  `api.ts` 未 await 換票 Promise，直接以無 `Authorization` Header 發送 HTTP 請求，導致首屏所有 API 調用瞬間全軍覆沒噴 401。

### 3. PoC 3 & 4 & 5: 後端三處殘留之 `Header(None, alias="X-User-ID")` 偽造漏洞
- **代碼位置**:
  - `backend/routers/trips.py:1119` (`PATCH /{trip_id}/day-data`)
  - `backend/routers/trips.py:2096` (`PATCH /{trip_id}/ledger-share`)
  - `backend/routers/sample_trip.py:190` (`POST /trips/seed-sample`)
- **實測驗證**:
  執行 in-memory 測試：攻擊者僅發送 `X-User-ID: spoofed-id` 且無任何 Bearer JWT，三者全數回傳 `200 OK`，成功竄改天數備忘、生成公帳碼與注入範本！

---

## 候選補丁與區塊替換規範 (Mantis Patch Candidate)

已生成標準候選補丁：`docs/security/patch_candidate_session_resilience_2026-10-22.diff`。

### 關鍵修復：
1. **JWT 逾期預檢與自癒 (`frontend/lib/auth-session.ts`)**:
   - `isTokenValid(token)` 解析 JWT payload `exp`（含 60 秒 clock-skew 容錯）。
   - 若逾期自動從 localStorage 剔除，讓 `ensureValidSession()` 自動發起換票。
   - 提供 `initSessionLifecycleListener()`，在 `online` 與 `visibilitychange` 事件時自動檢查並換票。
2. **非同步請求憑證保證 (`frontend/lib/api.ts`)**:
   - `fetch` 攔截器在無 token 時主動 `await ensureValidSession().catch(() => null)`，消除冷啟動 Race Condition。
3. **頂層客戶端掛載 (`frontend/components/app-client-layer.tsx`)**:
   - 掛載 `initSessionLifecycleListener()`，保證從第 0 毫秒進入頁面即開始監護與換票。
4. **SWR 401 自癒除錯 (`frontend/lib/hooks.ts`)**:
   - 遭遇 401 時主動清空失效 Token 並觸發背景換票重試。
5. **拔除後端所有殘留 Header 偽造孤島 (`backend/routers/trips.py` & `sample_trip.py`)**:
   - 一律替換為 `user_id: str = Depends(get_verified_user)`。
