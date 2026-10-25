# 🛡️ Security Sentinel 對抗式稽核與沙盒驗證報告

> **審查日期**：2026-10-24  
> **稽核模式**：Physical Sandboxed Subagent (`runner.py`) ✕ In-Memory PoC Verification  
> **審查主題**：首頁訪客重認證彈窗阻斷、孤兒 UUID 自噬陷阱與訪客雙軌安全啟動  
> **涉及邊界**：`browser_to_edge` / `public_to_authenticated`  
> **角色權限**：`@security` (Sentinel) —— 僅檢驗、實證與擬定候選補丁，絕不直接修改專案原始碼。  

---

## 一、執行摘要 (Executive Summary)

針對使用者回報「全新訪客或初次造訪者開啟網站根目錄時，被彈出的『需要原地驗證最新引繼碼』阻斷」之嚴重體驗與架構瑕疵，本審計調度獨立沙盒子代理人（Physical Subagent）並配合 In-Memory 記憶體單元測試，完成實證與攻擊向量防堵。

| 總審查標的 | 實證確認漏洞 (CONFIRMED) | 證偽排除假警報 (DISMISSED) | 程式碼片段限制 (INCONCLUSIVE) |
| :---: | :---: | :---: | :---: |
| **3** | **1** | **1** | **1** (已由 In-Memory PoC 實證補足) |

---

## 二、漏洞實證與攻防矩陣 (Vulnerability Details & PoC)

### 標的 1: `frontend/components/views/landing-page.tsx:client_unregistered_uuid_injection`
- **判定結果**: **CONFIRMED (實證漏洞存在)**
- **沙盒驗證器證詞 (`runner.py` task-457)**:
  > *"In `LandingPage.handleLogin()`, a new client-side UUID is generated via `generateUUID()` and immediately written to `localStorage` ('user_uuid') prior to any backend validation or database registration. The subsequent call to `usersApi.updateProfile(uuid, { name: nickname })` assumes an existing record and is wrapped in a try/catch block that silently suppresses failures as non-blocking. Consequently, the user is transitioned to `isLoggedIn = true` with an unregistered orphan UUID in `localStorage`. On page refresh, `useEffect` rehydrates this stored ID; when session verification (`ensureValidSession()`) attempts to validate this unregistered UUID against backend database (`legacy_identity_exists`), the lookup fails with HTTP 401, resulting in an unrecoverable `SessionReauthModal` trap."*
- **實體成因**: 前端私自生成之孤兒 UUID 未經後端發牌與 Supabase 登記，次頁刷新即淪為無效憑證，引發 401 連環警報。

### 標的 2: `frontend/lib/auth-session.ts:unauthenticated_visitor_reauth_dos`
- **判定結果**: **CONFIRMED via In-Memory PoC (記憶體實證確診)**
- **實證 PoC (`frontend/__tests__/reauth-gate-and-guest-bootstrap.test.ts`)**:
  - `TC-1`: 證明未修復前，未登入訪客持有孤兒 UUID 遭遇 401 時，`triggerReauthPrompt()` 無差別向全域 DOM 廣播 `tabiji:session_reauth_required`，阻斷首頁流程（5/5 通過）。
  - `TC-2`: 證明修復後的 `isUserLoggedIn()` 根部硬閘門能在訪客狀態下 100% 物理阻斷彈窗廣播。
  - `TC-4`: 證明修復後的 `ensureValidSession()` 在訪客遭遇 401 時，會主動清除本地失效的孤兒 UUID 並立即解開 `lastExchangeFailedAt = 0` 的 10 秒冷卻鎖死。

### 標的 3: `frontend/components/views/landing-page.tsx:offline_onboarding_regression`
- **判定結果**: **DISMISSED (證偽/保護需求)**
- **沙盒驗證器證詞**:
  > *"Static inspection of `handleLogin()` shows that it does not invoke or depend on `ensureValidSession()`. For a first-time offline user, `handleLogin()` generates a client-side UUID via `generateUUID()`, writes it with the nickname to `localStorage`, and wraps profile sync in a non-blocking try/catch block. The transition executes unconditionally, preserving Tabiji's offline-first architecture."*
- **關鍵結論**: 嚴禁粗暴刪除客戶端 UUID 生成能力；必須保留離線首登的本機安全降級路徑，嚴格維護 Tabiji L0 離線優先憲法。

---

## 三、Google Mantis 候選補丁與精確區塊替換 (Candidate Fix)

候選補丁已完成 RFC diff 與 Windows 衛生無歧義替換清單生成：
- **Diff 檔案**：[docs/security/patch_candidate_reauth_gate_and_guest_bootstrap_2026-10-24.diff](file:///d:/Project/tabiji/travel-pwa/docs/security/patch_candidate_reauth_gate_and_guest_bootstrap_2026-10-24.diff)
- **替換清單**：[docs/security/block_replacements_reauth_gate_and_guest_bootstrap_2026-10-24.json](file:///d:/Project/tabiji/travel-pwa/docs/security/block_replacements_reauth_gate_and_guest_bootstrap_2026-10-24.json)

### 1. 核心檔案 1: `frontend/lib/auth-session.ts`
- **變更點 A**: 新增 `isUserLoggedIn()` 狀態機檢驗函式，並在 `triggerReauthPrompt()` 根部實施未登入者硬阻斷。
- **變更點 B**: 在 `ensureValidSession()` 的 401 分支中加入身分二元分流：已登入者觸發重認證；未登入訪客則靜默清除本機失效殘留、解開 10 秒限流鎖死。

### 2. 核心檔案 2: `frontend/components/auth/session-reauth-modal.tsx`
- **變更點**: 在事件監聽器回調首行加入登入態硬邊界守衛，未登入狀態下收到事件直接 return 靜默抑制。

### 3. 核心檔案 3: `frontend/components/views/landing-page.tsx`
- **變更點**: 在 `handleLogin()` 中實施雙軌安全登入——在線時由 `ensureValidSession()` 向伺服器正規領牌與寫入 Supabase；離線時平滑降級為本機 `generateUUID()`，兼顧後端身分真理源與斷網首登體驗。

---

## 四、安全台帳同步 (Ledger Delta)

`docs/security/security-coverage-ledger.json` 已完成原子更新：
- 審查標的總數提升至 **238** 項。
- 新增項目：`frontend/lib/auth-session.ts:reauth_gate_and_guest_bootstrap` (`CONFIRMED_PENDING_DEV`)。
- 關聯 PoC 套件：`frontend/__tests__/reauth-gate-and-guest-bootstrap.test.ts` (5/5 Passed)。

---

## 五、人類主權交接 (Human Gate Handover)

依據 L0 憲法規範，`@security` 已完成對抗證偽、記憶體 PoC 實證與最小侵入性候選補丁配製。**未經使用者明確核准前，嚴禁擅自修改專案正式程式碼**。
