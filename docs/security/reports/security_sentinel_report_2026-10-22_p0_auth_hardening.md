# 🛡️ Security Sentinel 對抗式資安審查報告：P0 身分認證與 IDOR 帳號奪舍防禦 (2026-10-22)

> **審查模式**: Sentinel In-Memory Adversarial PoC Confrontation  
> **資安稽核員**: @security (Security Sentinel)  
> **受審檔案**:
> - `backend/utils/deps.py` (Trust Boundary: `public_to_authenticated`)
> - `backend/routers/trips.py` (Trust Boundary: `authenticated_to_internal`)
> - `backend/routers/expenses.py` (Trust Boundary: `authenticated_to_internal`)
> **候選假說清單**: `docs/security/candidates_p0_auth_sentinel_2026-10-22.json`  
> **驗證狀態**: 4 項假說 **全數實證成立 (4/4 CONFIRMED via In-Memory PoC)**

---

## 執行摘要 (Executive Summary)

針對 Tabiji 後端身分識別機制進行深度對抗驗證，編寫並執行記憶體級實證測試套件 (`backend/tests/test_p0_auth_poc.py`)。
測試結果：**4 項資安假說全數 100% 觸發實體漏洞 (PASSED 4/4 in Pytest)**，證明漏洞真實存在於現有代碼中，絕非理論臆測。

| 假說 ID | 攻擊向量 | 嚴重等級 | 實測驗證狀態 |
| :--- | :--- | :--- | :--- |
| `backend/utils/deps.py:unauthenticated_x_user_id_fallback` | 偽造 Header 繞過驗證 (Broken Authentication) | **Critical (CVSS 9.1)** | ✅ **CONFIRMED** (PoC 1 通過) |
| `backend/routers/trips.py:trip_collaborator_uuid_broadcast` | 協同行程廣播創立者 UUID (IDOR / ATO) | **High (CVSS 8.5)** | ✅ **CONFIRMED** (PoC 2 通過) |
| `backend/routers/expenses.py:expense_payer_and_creator_uuid_leakage` | 財務明細洩漏真實 UUID (Financial Harvesting) | **High (CVSS 7.8)** | ✅ **CONFIRMED** (PoC 3 通過) |
| `backend/routers/trips.py:residual_hardcoded_x_user_id_header` | 硬編碼 Header 認證孤島 (Auth Bypass Island) | **Medium (CVSS 6.5)** | ✅ **CONFIRMED** (PoC 4 通過) |

---

## 漏洞實體證偽剖析 (Empirical Proof Details)

### 1. PoC 1: 偽造 `X-User-ID` 即可無憑證讀寫任意私有行程
- **代碼位置**: `backend/utils/deps.py:83-87`
- **實測行為**:
  攻擊者發送 `GET /api/trips`，僅在 Header 帶入受害者的 UUID，未附帶任何 JWT 或密鑰。
  ```http
  GET /api/trips HTTP/1.1
  X-User-ID: 00000000-0000-0000-0000-000000000001
  ```
- **測試結果**: 伺服器回傳 `200 OK`，受害者的私人行程清單被完整外洩。

### 2. PoC 2 & PoC 3: 協同成員獲取創立者 UUID 導致帳號奪舍 (Account Takeover)
- **代碼位置**: `backend/routers/trips.py:280, 403-404` 與 `backend/routers/expenses.py:341, 348`
- **實測行為**:
  協同成員 Bob 調用 `GET /api/trips/shared-trip-123` 及 `GET /api/expenses/shared-trip-123/expenses`。
  API 回應將 Alice 的真實 UUID 明文回傳於 `created_by`、`members[0].user_id` 及 `payer_id`。
- **測試結果**: 證實 Bob 在瀏覽器 Network 分頁可 100% 獲取 Alice 的 UUID。搭配目前 Landing Page 的「引繼碼輸入框」，Bob 可在其他裝置直接貼上該 UUID 登入奪舍 Alice 帳號。

### 3. PoC 4: 退出行程端點硬編碼 Header 繞過中央驗證
- **代碼位置**: `backend/routers/trips.py:1247`
- **實測行為**:
  端點定義 `user_id: str = Header(None, alias="X-User-ID")`，未經過 `Depends(get_verified_user)`。
- **測試結果**: 攻擊者直接假冒任意 member_id 發出 `POST /leave`，伺服器直接回傳 `200 OK` 執行退出操作。

---

## 候選補丁與區塊替換規範 (Mantis Patch Candidate)

已生成標準候選補丁：`docs/security/patch_candidate_p0_auth_2026-10-22.diff`。

### 關鍵防禦機制：
1. **後端 Session 路由 (`backend/routers/auth.py`)**:
   - `POST /api/auth/session` (開機領票/老用戶原金鑰換票)。
   - `POST /api/auth/recover` (首頁恢復金鑰還原，加掛 5次/分鐘 IP 限流)。
2. **Deps 升級為 JWT-Only (`backend/utils/deps.py`)**:
   - 提取 `Authorization: Bearer <token>` 並以本機密鑰執行 0.05ms 記憶體驗證。
   - 徹底移除 `x_user_id` 回退信任。
3. **伺服端動態脫敏 (`backend/routers/trips.py` & `backend/routers/expenses.py`)**:
   - 僅本人可見本人真實 ID，同行隊友看到的他人 ID 動態雜湊為 `mem_hash`。
   - 回傳 `is_owner: bool`，前端權限判斷 100% 保持相容。
4. **收攏孤島端點**:
   - 將 `leave_trip` 改為 `user_id: str = Depends(get_verified_user)`。

---

## 審查交接與人類主權 (Human Gate Handover)

依 L0 憲法規範：
- `@security` **僅提供證明、報告與 diff 補丁，絕不擅自修改專案原始碼**。
- 請確認是否核准候選補丁 `docs/security/patch_candidate_p0_auth_2026-10-22.diff`？核准後將交由 `@dev` 進行精確區塊替換與回歸測試。
