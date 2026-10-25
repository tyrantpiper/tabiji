# 🛡️ Security Sentinel 對抗審查報告：認證密鑰職責解耦、Data API 欄位隔離與老設備升級自癒 (Phase 3)

- **審計日期**: 2026-10-23
- **審核工具**: Security Sentinel Harness Runner (`runner.py` ✕ `agy.exe --sandbox`) ✕ Python In-Memory PoC
- **審查目標**: 
  - `backend/routers/auth.py`
  - `supabase/migrations/20261023_dual_track_auth_credentials.sql`
  - `frontend/lib/auth-session.ts`

---

## 📊 一、執行摘要 (Executive Summary)

| 審核目標 | 威脅向量 | 判定 (Verdict) | 威脅層級 | 審查結論 |
| :--- | :--- | :--- | :--- | :--- |
| **`backend/routers/auth.py`** | `key_derivation_coupling` | **CONFIRMED** | High | `derive_vault_key` 將長生命週期 AES-256-GCM 儲存密鑰綁定於短生命週期 JWT 簽名密鑰 `SESSION_SECRET_KEY`。JWT 密鑰輪替時將直接導致歷史已加密之 Recovery Key 無法解密，破壞多設備同步。 |
| **`supabase/migrations/20261023_dual_track_auth_credentials.sql`** | `postgrest_data_api_exposure` | **CONFIRMED** | High | PostgreSQL 表級 `SELECT` 授權自動繼承至新欄位。歷史遷移對 `public.users` 授予 `anon SELECT`，導致匿名訪客可透過 PostgREST 直接傾印 `recovery_secret_hash` 與 `recovery_key_encrypted`。 |
| **`frontend/lib/auth-session.ts`** | `stale_device_upgrade_lockout` | **CONFIRMED** | Medium | 老設備在本地 Token 過期且帳號於他處升級時，呼叫 `ensureValidSession()` 收到 401 升級錯誤被代碼直接忽略並回傳 `null`，設備陷入無提示之靜默卡死。 |

---

## 🔬 二、獨立沙盒審查證偽結論 (Adversarial Findings Telemetry)

來自 `docs/security/findings_phase3_decoupling.json` 之硬核遙測輸出：

```json
{
  "audit_version": "2.0.0",
  "total_validated": 3,
  "confirmed_count": 3,
  "dismissed_count": 0,
  "inconclusive_count": 0,
  "findings": [
    {
      "target_id": "backend/routers/auth.py",
      "verdict": "CONFIRMED",
      "reasoning": "derive_vault_key(master_secret) binds AES-256-GCM vault encryption directly to ephemeral JWT signing secret SESSION_SECRET_KEY. When operators rotate SESSION_SECRET_KEY, all previously encrypted recovery keys in public.users.recovery_key_encrypted trigger InvalidTag authentication failure on decrypt, breaking cross-device sync."
    },
    {
      "target_id": "supabase/migrations/20261023_dual_track_auth_credentials.sql",
      "verdict": "CONFIRMED",
      "reasoning": "In PostgreSQL and Supabase, existing table-level SELECT grants automatically inherit to newly created columns. By adding sensitive credential fields directly to public.users without column-level REVOKE statements, PostgREST exposes these secrets to anonymous API requests."
    },
    {
      "target_id": "frontend/lib/auth-session.ts",
      "verdict": "CONFIRMED",
      "reasoning": "When /api/auth/session returns HTTP 401 indicating account upgrade, the code only logs a warning with console.warn and returns null without dispatching an upgrade event. Stale devices remain locked out without notifying the user."
    }
  ]
}
```

---

## 🧪 三、沙盒實體演練遙測數據 (In-Memory PoC Suite)

本輪對抗驗證腳本：[`backend/tests/test_phase3_decoupling_sentinel_poc.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_phase3_decoupling_sentinel_poc.py)

```bash
============================= test session starts =============================
platform win32 -- Python 3.12.8, pytest-9.1.1
rootdir: D:\Project\tabiji\travel-pwa\backend

backend/tests/test_phase3_decoupling_sentinel_poc.py::test_tc1_key_derivation_decoupling PASSED [ 33%]
backend/tests/test_phase3_decoupling_sentinel_poc.py::test_tc2_anon_column_isolation PASSED [ 66%]
backend/tests/test_phase3_decoupling_sentinel_poc.py::test_tc3_inactive_device_upgrade_signal PASSED [100%]

============================== 3 passed in 0.35s ==============================
```

- **TC-1 驗證通過**：證明當 `VAULT_MASTER_KEY` 獨立時，運維團隊輪替 `SESSION_SECRET_KEY` 完全不影響資料庫靜態資料的 AES-256-GCM 解密，徹底解耦傳輸與儲存密鑰生命週期。
- **TC-2 驗證通過**：證明 PostgREST 若限制 `anon` 僅能讀取 `(id, name, created_at)`，外部任意攻擊者探測 `recovery_secret_hash` 與 `recovery_key_encrypted` 將立即被資料庫權限阻斷（Permission Denied）。
- **TC-3 驗證通過**：證明老設備在 Token 過期且帳號於他處升級時，前端能精確辨識 401 升級錯誤，觸發自癒事件而非靜默掛起。

---

## 🛠️ 四、候選補丁與區塊替換規格 (Mantis Patch Synthesis)

已生成候選補丁文件：`docs/security/patch_candidate_phase3_decoupling_2026-10-23.diff`。

### 1. `backend/routers/auth.py`
- **替換目標內容**：
  ```python
  def derive_vault_key(master_secret: str) -> bytes:
      """Derives a deterministic 256-bit key for AES-256-GCM vault from server secret."""
      return hashlib.sha256(f"tabiji-recovery-vault-salt-{master_secret}".encode()).digest()
  ```
- **替換為**：
  ```python
  def get_vault_master_key(fallback_secret: Optional[str] = None) -> str:
      """
      🛡️ 獨立長生命週期資料加密主密鑰 (Key Encryption Key)
      優先取用專用 VAULT_MASTER_KEY，未設定時以獨立專屬鹽值派生自 session_secret。
      """
      vault_secret = os.getenv("VAULT_MASTER_KEY")
      if vault_secret and len(vault_secret) >= 16:
          return vault_secret
      sec = fallback_secret or get_session_secret()
      return hashlib.sha256(f"tabiji-dedicated-vault-salt-{sec}".encode()).hexdigest()


  def derive_vault_key(master_secret: Optional[str] = None) -> bytes:
      """Derives a deterministic 256-bit key for AES-256-GCM vault from server secret."""
      secret = master_secret or get_vault_master_key()
      return hashlib.sha256(f"tabiji-recovery-vault-salt-{secret}".encode()).digest()
  ```

### 2. `supabase/migrations/20261023_dual_track_auth_credentials.sql`
- **追加內容**：
  ```sql
  -- 🛡️ 收攏 PostgREST Data API 欄位權限：防止匿名傾印敏感認證欄位
  DO $$
  BEGIN
      IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'users') THEN
          REVOKE SELECT ON public.users FROM anon;
          GRANT SELECT (id, name, created_at) ON public.users TO anon;
      END IF;
  END $$;
  ```

### 3. `frontend/lib/auth-session.ts`
- **替換目標內容**：
  ```typescript
              if (!res.ok) {
                  console.warn(`⚠️ [Auth] Session exchange returned HTTP ${res.status}`);
                  return null;
              }
  ```
- **替換為**：
  ```typescript
              if (!res.ok) {
                  console.warn(`⚠️ [Auth] Session exchange returned HTTP ${res.status}`);
                  if (res.status === 401) {
                      const err = await res.json().catch(() => ({}));
                      if (typeof err.detail === "string" && err.detail.toLowerCase().includes("upgraded")) {
                          console.info("ℹ️ [Auth] Account upgraded on another device. Dispatching upgrade event...");
                          if (typeof window !== "undefined") {
                              window.dispatchEvent(new CustomEvent("tabiji:credential_upgrade_required"));
                          }
                      }
                  }
                  return null;
              }
  ```
