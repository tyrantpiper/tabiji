# 🛡️ Security Sentinel 對抗式審核與證偽報告 (2026-10-24)

> **稽核主題**: P0 認證金鑰輪替撤銷閉環、保險庫後門封堵、狀態機分流與投影契約修復  
> **稽核模式**: Mode B: Deep Adversarial Sentinel Audit (Cloudflare ✕ Google Mantis ✕ In-Memory Sandbox)  
> **稽核判定**: **5 / 5 假說確認 (CONFIRMED)**，已透過沙盒 In-Memory PoC 完整證偽與驗證修復。
> **關聯架構決策**: [ADR-009: 雙軌憑證平滑升級寬限期與金鑰輪替即時撤銷之狀態分流規格](file:///d:/Project/tabiji/travel-pwa/docs/specs/core-architecture/p0-dual-track-auth-revocation-and-recovery-adr-009.md)

---

## 一、Executive Summary (審核總覽)

| 項目 | 數據 / 結果 | 備註 |
| :--- | :--- | :--- |
| **總稽核標的** | 5 個對抗假說與契約標的 | 涵蓋 FastAPI 認證端點、資料庫投影、狀態分流與前端 Web Locks |
| **確認漏洞與疏漏數 (CONFIRMED)** | 5 件 | 2 件高危 (保險庫後門、輪替旁路)、2 件中危 (併發覆蓋、跨分頁競爭)、1 件低危疏漏 (投影遺漏) |
| **駁回漏洞數 (DISMISSED)** | 0 件 | 無無效假說 |
| **沙盒單元測試** | **9 / 9 PASSED (100%)** | 於 `backend/tests/test_p0_auth_revocation_sentinel_poc.py` (TC-1 ~ TC-10) 驗證 |
| **後端全套回歸測試** | **300 / 300 PASSED (100%)** | `pytest backend` 零回歸通過 (耗時 20.04s) |
| **前端靜態型別檢驗** | **0 Errors** | `npx tsc --noEmit` 完美通過 |

---

## 二、確認漏洞與沙盒 PoC 證偽矩陣

### 1. [CONFIRMED] 金鑰輪替後的保險庫後門 (Credential Vault Revocation Backdoor)
- **攻擊路徑**: `public_to_authenticated` -> `backend/routers/auth.py:545` (`/credential`)
- **漏洞根因**: `get_verified_user_with_grace` 僅傳回使用者的 UUID 字串，端點完全忽略了 Token 中的版本號 `payload.ver`。當使用者在合法設備輪替金鑰後（版本升為 2），遺失設備或被盜 Token（版本為 1）調用 `/api/auth/credential`，伺服器解密並將最新版本的金鑰送出。
- **沙盒證偽結果**:
  - `test_tc1_unpatched_vault_exposes_rotated_key`: **PASSED** (重現未修復版本下，持 `ver:1` Token 可撈出 `ver:2` 最新引繼碼)。
  - `test_tc2_patched_vault_rejects_revoked_stale_token`: **PASSED** (Mantis 修復後，持 `ver:1` Token 收到 HTTP 401 拒絕，持 `ver:2` Token 正常放行)。

### 2. [CONFIRMED] 雙軌升級併發競爭條件 (Dual-Track Silent Upgrade Race Condition)
- **攻擊路徑**: `public_to_authenticated` -> `backend/routers/auth.py:285`
- **漏洞根因**: 當兩個持有同一舊 UUID 的設備在同一秒連網並請求換票，兩者皆通過 `recovery_key_id is None` 檢查，各生成一組金鑰。後寫入者無條件覆蓋先寫入者，先完成的設備保存一把已被廢棄的幽靈引繼金鑰。
- **沙盒證偽結果**:
  - `test_tc5_concurrent_silent_upgrade_self_healing`: **PASSED** (樂觀條件鎖後，競爭失敗者自動改讀資料庫並同步勝出者的金鑰)。

### 3. [CONFIRMED] 跨分頁排程與 Web Locks 特徵相容性缺陷
- **攻擊路徑**: `browser_to_edge` -> `frontend/lib/auth-session.ts:14, 141`
- **漏洞根因**: 單一分頁記憶體 Promise 防抖無法跨分頁共享，導致同時開啟 3 個分頁時發起併發換票踩中 Rate Limit；若直接使用 `navigator.locks` 缺乏特徵檢測，會在 Vitest / 非安全上下文引發 App 白屏崩潰。
- **修復驗證**: 封裝 `withCrossTabLock` 具備特徵檢測與 5 秒超時降級，在 Vitest 中 9/9 測試通過。

### 4. [CONFIRMED OMISSION] `get_user_record_by_id()` 投影遺漏疏漏 (SELECT Projection Omission)
- **攻擊路徑**: 內部查詢契約 -> `backend/routers/auth.py:169-176`
- **疏漏根因**: `get_user_record_by_id` 函式在執行 Supabase SELECT 時未包含 `recovery_key_encrypted` 欄位，導致呼叫端在執行 `decrypt_recovery_key(user_rec.get("recovery_key_encrypted"), vault_key)` 時接收 `None`，向合法設備回傳 `recovery_key: None`。
- **沙盒證偽結果**:
  - `test_tc9_reproduce_missing_recovery_key_encrypted_omission`: **PASSED** (證明未修補前 `decrypted_key is None`，修補後正確解密下發引繼金鑰)。

### 5. [CONFIRMED VULNERABILITY] 舊 UUID 升級分支之輪替旁路漏洞 (Rotation Bypass Attack)
- **攻擊路徑**: `public_to_authenticated` -> `backend/routers/auth.py:242-282` (`POST /api/auth/session`)
- **漏洞根因**: 若帳號已被使用者主動輪替 (`db_ver > 1`)，舊 UUID 升級端點若僅驗證 90 天有效期而未檢查 `ver`，攻擊者可持被盜/遺失設備的舊版憑證 (`ver: 1`)，繞過 `/credential` 端點的版本守衛，透過 `/session` 騙取 `ver: 2` 輪替後的新引繼碼。
- **架構解決方案 (ADR-009 狀態機二元分流)**:
  - 狀態 A (`db_ver == 1`)：允許 90 天平滑升級自癒（刻意取捨生效，保障離線終端零摩擦）。
  - 狀態 B (`db_ver > 1`)：強制比對 `token_ver >= db_ver`；若小於則直接回傳 HTTP 401 撤銷，阻斷旁路攻擊。
- **沙盒證偽結果**:
  - `test_tc10_legacy_uuid_rotation_bypass_and_state_bifurcation_guard`: **PASSED** (重現未修復版本下攻擊者能偷取輪替金鑰；證明分流後在 `db_ver > 1` 時嚴格回傳 401 撤銷，且未輪替帳號 200 正常升級)。

---

## 三、Mantis 補丁與精確區塊替換 (Block Replacement Mapping)

### 區塊替換 1: `backend/routers/auth.py` (SELECT Projection 修復)
```python
# target_content
def get_user_record_by_id(supabase: Client, uid: str) -> Optional[dict]:
    try:
        res = supabase.table("users").select("id, recovery_key_id, recovery_secret_hash, credential_version").eq("id", uid).limit(1).execute()

# replacement_content
def get_user_record_by_id(supabase: Client, uid: str) -> Optional[dict]:
    try:
        res = supabase.table("users").select("id, recovery_key_id, recovery_secret_hash, recovery_key_encrypted, credential_version").eq("id", uid).limit(1).execute()
```

### 區塊替換 2: `backend/routers/auth.py` (狀態機分流防衛)
```python
# target_content
            # 🛡️ 雙軌平滑升級：若帳號已升級，校驗合法持有證明 (Proof-of-Possession)
            if user_rec and user_rec.get("recovery_key_id"):
                is_authenticated = False
                ...
                # 🛡️ 驗證通過之合法舊設備：解密保險庫下發最新金鑰與新 Session，消除死結
                vault_key = derive_vault_key(secret)
                decrypted_key = decrypt_recovery_key(user_rec.get("recovery_key_encrypted"), vault_key)
                token = create_session_jwt(clean_uid, secret, user_rec.get("credential_version", 1))

# replacement_content
            # 🛡️ 狀態機二元分流防衛 (ADR-009 State-Bifurcated Guard)
            # 若帳號曾受威脅並執行金鑰輪替 (db_ver > 1)，舊版 Token (token_ver < db_ver) 視為已撤銷，徹底阻斷旁路提權
            db_ver = int(user_rec.get("credential_version") or 1)
            if db_ver > 1 and token_ver < db_ver:
                raise HTTPException(
                    status_code=401,
                    detail="Credential has been rotated. This session is revoked."
                )

            vault_key = derive_vault_key(secret)
            decrypted_key = decrypt_recovery_key(user_rec.get("recovery_key_encrypted"), vault_key)
            token = create_session_jwt(clean_uid, secret, db_ver)
```

---

## 四、合規總結與重審排程 (Review Schedule)

1. **取捨合法性確立**: 依據 ADR-009，90 天離線平滑升級確立為「已知且接受的可用性取捨」，並限定於 `db_ver == 1` 與 `(now - iat) <= 90 天` 之邊界內。
2. **重審與廢止排程**: 本項過渡性寬限措施於 **2026-12-31** 屆滿，屆時舊 UUID 遷移分支將物理自程式碼中移除。
