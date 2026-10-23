# 🛡️ Security Sentinel 對抗式沙盒審查報告 (2026-10-24)

> **稽核主題**: Local-First 原地重認證 (In-Place Re-auth Modal) 與出站隊列凍結 (Outbox Freeze)  
> **稽核模式**: `/security-sentinel` (Mode B: Vitest In-Memory Sandbox ✕ Cloudflare Ledger ✕ Google Mantis)  
> **審查判定**: **3 / 3 假說確認 (CONFIRMED)**，已透過物理單元測試完成漏洞重現與修復閉環驗證。

---

## 一、Executive Summary (審核總覽)

| 項目 | 數據 / 結果 | 備註 |
| :--- | :--- | :--- |
| **總稽核標的** | 3 個假說標的 | 涵蓋出站隊列數據遺失、原地換票防污染與事件防抖 |
| **確認漏洞數 (CONFIRMED)** | 3 件 | 1 件高危 (隊列 401 自動丟棄)、1 件高危 (破壞性登出)、1 件中危 (事件風暴) |
| **沙盒單元測試** | **6 / 6 PASSED (100%)** | 於 `frontend/__tests__/in-place-reauth-resilience.test.ts` 驗證 |
| **執行耗時** | **718ms** | 物理測試零外部依賴、純記憶體隔離執行 |

---

## 二、確認漏洞與沙盒 PoC 證偽矩陣

### 1. [CONFIRMED] 離線出站隊列 401 自動丟棄 (SyncQueue Outbox Eviction)
- **攻擊路徑**: `browser_to_edge` -> `frontend/lib/sync-hooks.ts:133-136`
- **漏洞根因**: `useBackgroundSync` 在重播請求遭遇 401 脫節時，將 401 視為普通失敗，累計重試達 3 次（`MAX_RETRIES`）後執行 `SyncQueue.dequeue(req.id)`，將使用者離線新增的行程與記帳**永久自 IndexedDB 剔除抹滅**。
- **沙盒證偽結果**:
  - `TC-1: Unpatched sync queue evicts items after 3x 401 retries`: **PASSED** (成功重現未修復版本下，離線修改在 3 次 401 後被永久丟棄，隊列清空)。
  - `TC-2: Freezing sync queue on 401 halts replay and preserves all mutations`: **PASSED** (驗證修復：在收到 401 瞬間啟動 `SyncEngineControl.pause()`，中斷重播，隊列完整保留，重試次數不消耗)。

### 2. [CONFIRMED] 原地重認證與「帳號錯套」資料污染 (Wrong User Hazard)
- **攻擊路徑**: `browser_to_edge` -> `frontend/lib/auth-session.ts:reanchorSessionWithKey`
- **漏洞根因**: 傳統 401 粗暴執行 `localStorage.clear()` 導致本地離線資料毀滅；而若缺乏嚴格的身分斷言，使用者誤輸入不同帳號的引繼碼會導致本地 IndexedDB 數據被他人身分覆蓋污染。
- **沙盒證偽結果**:
  - `TC-3: Re-anchoring strictly rejects Wrong User key`: **PASSED** (成功防禦：輸入異身分引繼碼時拋出 `Identity mismatch` 異常，本機行程與 UUID 零篡改)。
  - `TC-4: Legitimate Re-anchoring updates credentials in-place`: **PASSED** (驗證修復：合法金鑰原地更新通行證與引繼碼，本地離線資料庫毫髮無傷)。
  - `TC-6: Case-Insensitive UUID tolerance`: **PASSED** (容錯驗證：iOS WebKit 大寫 UUID 與 Postgres 小寫 UUID 正常相容)。

### 3. [CONFIRMED] 多併發 401 引發的事件轟炸 (Event Flood Thrashing)
- **攻擊路徑**: `browser_to_edge` -> `frontend/components/auth/session-reauth-modal.tsx`
- **漏洞根因**: 多個 SWR Hook 同時收到 401 時，連續發射 `tabiji:session_reauth_required`，引發 React Modal 重複掛載震盪。
- **沙盒證偽結果**:
  - `TC-5: Multiple concurrent 401s trigger only 1 reauth event broadcast`: **PASSED** (驗證修復：3 秒防抖門禁將 10 次併發 401 收攏為單次廣播)。

---

## 三、工件清冊與帳本更新 (Artifacts & Ledger)

1. **候選假說清單**: [candidates_reauth_and_outbox_freeze_2026-10-24.json](file:///d:/Project/tabiji/travel-pwa/docs/security/candidates_reauth_and_outbox_freeze_2026-10-24.json)
2. **驗證判定記錄**: [findings_reauth_and_outbox_freeze_2026-10-24.json](file:///d:/Project/tabiji/travel-pwa/docs/security/findings_reauth_and_outbox_freeze_2026-10-24.json) (3/3 CONFIRMED)
3. **Mantis 候選補丁**: [patch_candidate_reauth_and_outbox_freeze_2026-10-24.diff](file:///d:/Project/tabiji/travel-pwa/docs/security/patch_candidate_reauth_and_outbox_freeze_2026-10-24.diff)
4. **沙盒單元測試套件**: [frontend/__tests__/in-place-reauth-resilience.test.ts](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/in-place-reauth-resilience.test.ts) (6/6 通過)
5. **安全覆蓋總帳本**: 已原子更新 [security-coverage-ledger.json](file:///d:/Project/tabiji/travel-pwa/docs/security/security-coverage-ledger.json)。

---

## 四、Human Gate (人類主權門禁)

本稽核員**嚴格遵守唯讀與沙盒證偽原則，尚未更動任何正式生產程式碼**。  
所有測試均已在隔離沙盒中 100% 驗證通過。  
請確認是否核准進入代碼落地階段？
