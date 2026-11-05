# Security Sentinel 對抗審計報告：未登入訪客金鑰同步誤報與生命週期防護 (2026-11-05)

> **審計模式**: `sentinel-agy-adversarial` ✕ `In-Memory PoC Mantis Block G` ✕ `Harness² Conservation`
> **時間戳記**: 2026-11-05T21:52:00Z
> **目標範圍**: `frontend/components/app-client-layer.tsx`, `frontend/lib/auth-session.ts`
> **稽核人員**: Security Sentinel (`@security`)

---

## Executive Summary (執行總結)

- **Total Targets Audited (審計標的數)**: 3
- **Confirmed Vulnerabilities (確認漏洞)**: 3
- **Dismissed Hypotheses (證偽假說)**: 0
- **Inconclusive (未決項目)**: 0
- **Mantis Block G Benign Control**: 通過 (`benign_control_passed == True`)
- **Vitest In-Memory PoC**: 5 / 5 passed (100%)

---

## 🎯 Attack Surface Coverage Matrix (攻擊面覆蓋矩陣)

| Target ID | Trust Boundary | Category | Verdict | PoC Type |
| :--- | :--- | :--- | :--- | :--- |
| `frontend/components/app-client-layer.tsx:unauthenticated_visitor_synced_toast_leak` | `browser_to_edge` | `unauthenticated_visitor_false_alarm` | **CONFIRMED** | `vitest_in_memory` (TC-1, TC-2, TC-4) |
| `frontend/lib/auth-session.ts:unauthenticated_visitor_background_exchange_waste` | `browser_to_edge` | `unnecessary_guest_session_exchange` | **CONFIRMED** | `pytest_in_memory` & `vitest_in_memory` (TC-5) |
| `frontend/lib/auth-session.ts:is_user_logged_in_operator_precedence_flaw` | `browser_to_edge` | `broken_access_control_identity_assertion` | **CONFIRMED** | `pytest_in_memory` & `vitest_in_memory` (TC-3) |

---

## 🔬 Confirmed Vulnerability Details & In-Memory PoCs

### 1. `AppClientLayer` 未登入訪客金鑰同步誤報 (`unauthenticated_visitor_synced_toast_leak`)
- **位置**: `frontend/components/app-client-layer.tsx:45-49`
- **成因**: 全域事件監聽器 `window.addEventListener("tabiji:recovery_key_updated", handleKeyUpdated)` 無條件彈出 Toast，未驗證 `isUserLoggedIn()` 亦未核驗事件來源 `detail.source === "remote_sync"`。
- **後果**: 未登入訪客首次載入首頁時，開機換票產生之新引繼碼立即觸發事件，畫面上彈出恐慌性提示「✨ 帳號引繼碼已自其他裝置同步更新」。

### 2. 未登入訪客首頁被動換票造成幽靈開戶與資源浪費 (`unauthenticated_visitor_background_exchange_waste`)
- **位置**: `frontend/lib/auth-session.ts:135-145`
- **成因**: `initSessionLifecycleListener()` 在連線恢復或元件掛載時，只要 `!getCachedToken()` 為真即呼叫 `ensureValidSession()`。
- **後果**: 任何路過首頁的未登入訪客均向後端發起 `POST /api/auth/session`，在 Supabase `users` 資料表無端開立匿名 `Traveler` 帳號並於本地儲存 Token，污染本地狀態與伺服器資料庫。

### 3. `isUserLoggedIn()` 布林運算子優先級邏輯缺陷 (`is_user_logged_in_operator_precedence_flaw`)
- **位置**: `frontend/lib/auth-session.ts:36-45`
- **成因**: `hasNicknameAndId || hasModernRecoveryKey` 展開為 `(hasNickname && hasLegacyId) || hasModernRecoveryKey`。當本地殘留 `user_recovery_key` 但無 `user_nickname` 時回傳 `true`。
- **後果**: 破壞未登入訪客防護閘門，導致未登入者或不完整身分繞過 `SessionReauthModal` 與 `triggerReauthPrompt` 守衛。

---

## 🛡️ Mantis Block G Benign Control (良性對照防閹割)

在 `frontend/__tests__/unauth-visitor-toast-sentinel-poc.test.ts` 中驗證：
1. **`test_exploit` (TC-1, TC-3)**: 實證未修復代碼在訪客情境下必然觸發誤報 Toast，且孤兒引繼碼會被誤判為已登入。
2. **`test_benign` (TC-2)**: 實證已登入合法使用者在收到真正的 `remote_sync` 廣播時，**依然 100% 正常收到 Toast**（杜絕為了解決誤報而直接移除 Toast 的閹割行為）。
3. **`test_remediation` (TC-4, TC-5)**: 實證套用補丁後，未登入者、日常換票、原地重錨定均保持靜默，生命週期監聽器絕不對訪客發起無效換票。

---

## 🏛️ 切斯特頓圍欄三問 (Chesterton's Fence Archaeology)

| 檔案與行數 | 原有功能 (legacy_function) | 設計初衷 (design_intent) | 刪除/修改風險 (regression_risk) | 新邏輯承接機制 (remediation_intents) |
| :--- | :--- | :--- | :--- | :--- |
| `frontend/components/app-client-layer.tsx:45-49` | 監聽金鑰更新並顯示通知 | 讓用戶在任意頁面得知引繼碼已被其他裝置輪替 (Commit `364c927`) | 若盲目刪除 Toast，多裝置跨端輪替即時性將喪失 | 新增 `isUserLoggedIn()` 與 `source === "remote_sync"` 雙重前置守門，僅保留真正的遠端更新通知 |
| `frontend/lib/auth-session.ts:135-145` | 在連線或回到前台時自動換票 | 避免返回用戶因 Token 過期而遭遇 API 401 斷線 | 若停用換票，已登入用戶過期後將無法自癒 | 新增 `if (!isUserLoggedIn()) return;`，已登入用戶持續保有自動換票自癒能力 |
| `frontend/lib/auth-session.ts:36-45` | 檢查本地是否具有有效身分 | 兼顧舊版 UUID 與新版 `tbj_rec_*` 憑證 | 若檢查過嚴可能導致合法用戶被判定為訪客 | 修正為 `nickname && (hasLegacyId || hasModernRecoveryKey)`，合法用戶兩者兼備，100% 正常判定 |

---

## 📦 補丁與物理替換區塊 (Patches & Block Replacements)

- **Unified Diff**: `docs/security/history/patches/patch_candidate_visitor_toast_suppression_2026-11-05.diff`
- **Block Replacement**: `docs/security/history/candidates/block_replacements_visitor_toast_suppression_2026-11-05.json`

