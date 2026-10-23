# 🛡️ Security Sentinel 對抗式審核與證偽報告 (2026-10-24)

> **稽核主題**: P0 認證金鑰輪替撤銷閉環、保險庫後門封堵與多設備併發自癒  
> **稽核模式**: Mode B: Deep Adversarial Sentinel Audit (Cloudflare ✕ Google Mantis ✕ In-Memory Sandbox)  
> **稽核判定**: **3 / 3 假說確認 (CONFIRMED)**，已透過沙盒 In-Memory PoC 完整證偽與驗證修復。

---

## 一、Executive Summary (審核總覽)

| 項目 | 數據 / 結果 | 備註 |
| :--- | :--- | :--- |
| **總稽核標的** | 3 個假說標的 | 涵蓋 FastAPI 認證端點、資料庫樂觀鎖與前端 Web Locks |
| **確認漏洞數 (CONFIRMED)** | 3 件 | 1 件高危 (保險庫後門)、1 件中危 (併發覆蓋)、1 件中危 (跨分頁競爭) |
| **駁回漏洞數 (DISMISSED)** | 0 件 | 無無效假說 |
| **沙盒單元測試** | **4 / 4 PASSED (100%)** | 於 `backend/tests/test_p0_auth_revocation_sentinel_poc.py` 驗證 |
| **前端單元測試** | **9 / 9 PASSED (100%)** | 於 `frontend/__tests__/auth-session-resilience.test.ts` 驗證 |

---

## 二、確認漏洞與沙盒 PoC 證偽矩陣

### 1. [CONFIRMED] 金鑰輪替後的保險庫後門 (Credential Vault Revocation Backdoor)
- **攻擊路徑**: `public_to_authenticated` -> `backend/routers/auth.py:510-545`
- **漏洞根因**: `get_verified_user_with_grace` 僅傳回使用者的 UUID 字串，端點完全忽略了 Token 中的版本號 `payload.ver`。當使用者在合法設備輪替金鑰後（版本升為 2），遺失設備或被盜 Token（版本為 1）調用 `/api/auth/credential`，伺服器解密並將最新版本的金鑰送出。
- **沙盒證偽結果**:
  - `test_tc1_unpatched_vault_exposes_rotated_key`: **PASSED** (成功重現未修復版本下，持 `ver:1` Token 可成功撈出 `ver:2` 最新引繼碼)。
  - `test_tc2_patched_vault_rejects_revoked_stale_token`: **PASSED** (證明 Mantis 修復後，持 `ver:1` Token 收到 HTTP 401 拒絕，持 `ver:2` Token 正常放行)。

### 2. [CONFIRMED] 雙軌升級併發競爭條件 (Dual-Track Silent Upgrade Race Condition)
- **攻擊路徑**: `public_to_authenticated` -> `backend/routers/auth.py:270-285`
- **漏洞根因**: 當兩個持有同一舊 UUID 的設備在同一秒連網並請求換票，兩者皆通過 `recovery_key_id is None` 檢查，各生成一組金鑰。後寫入者無條件覆蓋先寫入者，先完成的設備保存一把已被廢棄的幽靈引繼金鑰。
- **沙盒證偽結果**:
  - `test_tc5_concurrent_silent_upgrade_self_healing`: **PASSED** (證明在加入樂觀條件鎖後，競爭失敗者偵測到更新列為 0，自動改讀資料庫並同步勝出者的金鑰，雙設備持有相同金鑰)。

### 3. [CONFIRMED] 跨分頁排程與 Web Locks 特徵相容性缺陷
- **攻擊路徑**: `browser_to_edge` -> `frontend/lib/auth-session.ts:14, 141`
- **漏洞根因**: 單一分頁記憶體 Promise 防抖無法跨分頁共享，導致同時開啟 3 個分頁時發起併發換票踩中 Rate Limit；若直接使用 `navigator.locks` 缺乏特徵檢測，會在 Vitest / 非安全上下文引發 App 白屏崩潰。
- **修復驗證**: 封裝 `withCrossTabLock` 具備特徵檢測與 5 秒超時降級，在 Vitest 中 9/9 測試無感通過。

---

## 三、Mantis 補丁與精確區塊替換 (Block Replacement Mapping)

### 區塊替換 1: `backend/routers/auth.py`
- **Target File**: `backend/routers/auth.py`
- **Target Lines**: 451-545
- **Patch Action**:
  1. 定義 `VerifiedSession(BaseModel)` 傳遞 `user_id` 與 `token_version`。
  2. `get_verified_user_with_grace` 改名並升級為 `get_verified_session_with_grace`。
  3. `/credential` 端點強制比對 `session.token_version < db_ver`，若小於則拋出 401。
  4. 雙軌升級加入 `.is_("recovery_key_id", "null")` 與自癒就地讀取。

### 區塊替換 2: `frontend/lib/auth-session.ts`
- **Target File**: `frontend/lib/auth-session.ts`
- **Target Lines**: 14-20
- **Patch Action**:
  加入 `withCrossTabLock` 跨分頁排程器，並將 `ensureValidSession` 換票邏輯安全包裹。

---

## 四、Human Gate (人類主權交接)

根據 L0 憲法與 `@security` 職責規範，本稽核員**嚴格遵守唯讀與證偽原則，尚未更動任何正式生產程式碼**。
目前候選補丁已在沙盒測試環境 100% 驗證通過。
請確認是否核准將此補丁應用至正式原始碼？
