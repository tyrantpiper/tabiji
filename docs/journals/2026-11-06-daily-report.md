# 📅 Daily Report - 2026-11-06 (Unauthenticated Visitor Toast False Alarm Suppression, Unified CLI Red-vs-Blue Adversarial Duel Automation, Mantis Block G & Chesterton Archaeology Dual-Lock Convergence)

> **系統狀態**：🟢 Production Ready & Security Sentinel v2.4.0 Hardened, 0 TypeScript Errors (`tsc --noEmit`), 0 ESLint Warnings, 100% Tests Green (Frontend Vitest: 88/88 Files, 589/589 Tests Passed; Backend Pytest: 27/27 Passed; Root Hygiene Sentinel: 6/6 Passed), Security Ledger 252 Targets (54 Remediated, 51 Verified, 147 Dismissed, 100% 數學守恆 + `known_design_intents` 歷史決策防線).
> **今日關鍵研發範疇 (Core Focus)**：
> - 🛡️ **未登入訪客首頁虛警 Toast 根因修復與事件源標籤過濾閉環 (Unauthenticated Visitor Toast False Alarm Suppression & Event Source Tagging, AD-201, SPEC-AUTH-003)**：徹底排查未登入訪客首次進入網站首頁 (`/`) 即彈出「✨ 帳號引繼碼已自其他裝置同步更新」之惡性誤報。根本原因在於 `AppClientLayer` 掛載無差別監聽 `tabiji:recovery_key_updated`，而 `auth-session.ts` 內 `initSessionLifecycleListener()` 在未登入訪客無憑證時自動換票引發廣播。透過重構事件承載契約，全域事件標註四種來源 (`initial_bootstrap`、`session_exchange`、`remote_sync`、`local_reanchor`)，並於 `AppClientLayer` 建立 `if (!isUserLoggedIn()) return;` 與 `if (customEvent.detail?.source !== "remote_sync") return;` 雙層防衛，訪客不再受到虛警打擾且避免多餘背景請求。
> - ⚔️ **紅藍軍對抗全自動工作流原生整合至 Sentinel CLI (`runner.py --mode duel`, SPEC-AGY-002 v1.4.0, AD-202)**：響應架構演進方案一，深度融合 Red Team (`sentinel-attacker`) 與 Blue Team (`sentinel-defender`)，於 [`scripts/lib/adversarial_team.py`](file:///d:/Project/tabiji/travel-pwa/scripts/lib/adversarial_team.py) 實作 `orchestrate_adversarial_duel` 四階段全自動對抗協調器，並為 [`.agents/skills/security-sentinel/scripts/runner.py`](file:///d:/Project/tabiji/travel-pwa/.agents/skills/security-sentinel/scripts/runner.py) 擴充 `--mode {adaptive,duel,fast}` 命令列參數，自動調度 `GitWorktreePool` 沙盒執行「攻擊 PoC 擊穿 (`exit 1`) ➔ 藍軍切斯特頓考古抗辯 (`DISMISSED`) ➔ 補丁合成 ➔ Mantis Block G 良性對照綠燈驗證 (`exit 0`)」全自動化閉環。
> - 🔬 **Mantis Block G 良性對照與切斯特頓圍欄考古雙重閉環 (Mantis Block G Benign Control & Chesterton's Fence Archaeology, AD-203)**：全方位落實先紅後綠與防閹割補丁驗證，編寫 [`frontend/__tests__/unauth-visitor-toast-sentinel-poc.test.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/unauth-visitor-toast-sentinel-poc.test.ts)（5/5 通過，驗證訪客遮罩與合法跨裝置同步不受閹割）及 [`backend/tests/test_sentinel_duel_orchestrator.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_sentinel_duel_orchestrator.py)（7/7 通過，涵蓋早退、未擊穿、藍軍考古駁回、實體綠燈轉化與 runner 模式調度）。
> - 📊 **資安覆蓋台帳擴展至 252 項目標與數學守恆 100% 達成 (Ledger Guard Identity Assertion, SPEC-AGY-002)**：新增 3 項針對對抗編排器、CLI 模式開關與治理規範之候選假說審計，完成補丁落地與切斯特頓考古舉證，台帳維持 54 Remediated + 51 Verified + 147 Dismissed = 252 Total Targets 的絕對數學守恆。

---

## 🏆 深度專案復盤：四大核心工程里程碑 (Four Core Milestones)

---

### 里程碑一：未登入訪客首頁虛警 Toast 根因修復與事件源標籤過濾閉環 (AD-201, SPEC-AUTH-003)

1. **問題現象與根因溯源**：
   - 使用者反映：未登入使用者只要進入網站首頁 (`/`)，畫面上方就會彈出 Sonner 輕量通知：「✨ 帳號引繼碼已自其他裝置同步更新」。
   - **深層根因 (Root Cause)**：
     - [`frontend/components/app-client-layer.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/app-client-layer.tsx) 掛載了對自訂事件 `tabiji:recovery_key_updated` 的全域監聽器，原本的處理函式無條件直接彈出 Toast，並未校驗使用者當前是否為已登入狀態，亦未檢查該事件是由本機初始化還是異地遠端廣播所觸發。
     - 與此同時，[`frontend/lib/auth-session.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/lib/auth-session.ts) 的 `initSessionLifecycleListener()` 在初次掛載 (`handleReconnectOrResume()`) 時，若檢查到 `!getCachedToken()`，會自動觸發 `ensureValidSession()`。
     - `ensureValidSession()` 向後端發起 `/api/auth/session` 請求為訪客簽發臨時訪客憑證時，因獲得了新引繼碼，遂派發了 `tabiji:recovery_key_updated`。
     - 兩者疊加，導致每位無憑證訪客造訪首頁時，皆會觸發「已自其他裝置同步更新」的嚇人誤報。
2. **切斯特頓圍欄考古與承接機制 (Chesterton's Fence Handover)**：
   - **功能反推 (`legacy_function`)**：該 Toast 之所以存在，是為了消滅「跨裝置憑證輪替黑洞」。當使用者在裝置 A 輪替引繼碼，Supabase Realtime 向裝置 B 廣播 `CREDENTIAL_ROTATED`，裝置 B 之 `fetchLatestRecoveryKey()` 需即時通知使用者金鑰已更新，避免使用者誤抄過期金鑰。
   - **設計初衷 (`design_intent`)**：提供無縫的跨裝置狀態透明度。
   - **精準修正方案**：
     - **語意化事件來源標記 (`detail.source`)**：為 `tabiji:recovery_key_updated` 事件注入來源標籤：
       - `initial_bootstrap` / `session_exchange`：本機訪客或首次會話交換。
       - `remote_sync`：真正由 Supabase Realtime 觸發之跨裝置雲端校準。
       - `local_reanchor`：本機手動輸入引繼碼熱重錨。
     - **雙重守衛**：在 `AppClientLayer` 中強制加入：
       ```typescript
       if (!isUserLoggedIn()) return;
       if (customEvent.detail?.source !== "remote_sync") return;
       ```
     - **訪客換票節流**：在 `auth-session.ts` 的 `handleReconnectOrResume` 開頭加入 `if (!isUserLoggedIn()) return;`，阻斷未登入訪客造訪首頁時無意義向後端換取訪客憑證之效能浪費。

---

### 里程碑二：紅藍軍對抗全自動工作流原生整合至 Sentinel CLI (`runner.py --mode duel`, AD-202)

1. **三權分立的架構痛點**：
   - 過去架構中，`sentinel-attacker`（紅軍）負責建構攻擊 PoC，`sentinel-defender`（藍軍）負責切斯特頓圍欄考古抗辯，但兩者僅能透過 IDE 交談動態 `define_subagent` 手動調度，與批次命令列工具 `runner.py` 處於脫節狀態。
2. **方案一落地：四階段自動化對抗協調器 (`orchestrate_adversarial_duel`)**：
   - 於 [`scripts/lib/adversarial_team.py`](file:///d:/Project/tabiji/travel-pwa/scripts/lib/adversarial_team.py) 實作 `orchestrate_adversarial_duel`：
     - **Phase 1 (紅軍假說評估)**：自動讀取目標程式碼與歷史意圖，調用紅軍建構獨立 `pytest` PoC；若紅軍自主判定現有代碼已具備防禦，即刻以 `verdict: "DISMISSED"` 提前結束，節約 Worktree 資源。
     - **Phase 2 (Worktree 實體紅燈擊穿)**：在隔離沙盒中執行 `pytest -k "not benign"`，要求嚴格 `exit code == 1`（證明確有漏洞擊穿）。若傳回 `exit code == 0`，代表防禦依然穩固，依「無罪推定」判定 `DISMISSED`。
     - **Phase 3 (藍軍切斯特頓考古審查)**：紅燈成立時，調動藍軍進行切斯特頓三問考古。若藍軍舉證為刻意系統設計（如 SSOT 分拆計算、狀態重置），判定 `DISMISSED` 駁回誤判。
     - **Phase 4 (補丁合成與 Mantis Block G 綠燈檢驗)**：套用 `block_replacement`，執行全量測試，要求攻擊與良性對照測試雙過 (`exit code == 0` 且 `benign_control_passed == True`)，正式輸出 `CONFIRMED` 候選修復。
3. **CLI 三模態擴充 (`runner.py --mode {adaptive,duel,fast}`)**：
   - `--mode duel`：全自動對抗模式，每個候選目標自動分配 `GitWorktreePool` 沙盒執行完整 4 階段對抗。
   - `--mode adaptive`（預設）：自適應模式，維持批次平行靜態快篩，僅對 `high`/`critical` 目標自動啟用 Worktree 實體驗證。
   - `--mode fast`：純靜態極速審查模式，跳過 Worktree 建立與實體 pytest 執行。

---

### 里程碑三：Mantis Block G 良性對照與切斯特頓圍欄考古雙重閉環 (AD-203)

1. **訪客 Toast 假說的先紅後綠與防閹割實證**：
   - 於 [`frontend/__tests__/unauth-visitor-toast-sentinel-poc.test.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/unauth-visitor-toast-sentinel-poc.test.ts) 建立 5 大測試案例：
     - **TC-1 (漏洞復現)**：未登入訪客接收事件，在舊邏輯下 100% 觸發誤報 Toast（紅燈證明）。
     - **TC-2 (Mantis Block G 良性對照)**：合法登入用戶接收 `remote_sync` 事件，必須依然觸發 Toast，保證修復未閹割既有功能。
     - **TC-3 (運算子優先級漏洞)**：孤兒金鑰邊界狀態測試。
     - **TC-4 & TC-5 (防禦驗證)**：修復後之 `AppClientLayer` 與 `initSessionLifecycleListener` 徹底靜默訪客誤報。
2. **對抗協調器 7 大單元測試覆蓋**：
   - 於 [`backend/tests/test_sentinel_duel_orchestrator.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_sentinel_duel_orchestrator.py) 驗證紅軍早退、防禦未擊穿、藍軍考古駁回、實體紅轉綠、以及 `runner.py` 在 `duel` 與 `fast` 模式下的行為一致性，測試耗時僅 0.07s，達成 100% 綠燈。

---

### 里程碑四：資安覆蓋台帳擴展至 252 項目標與數學守恆 100% 達成 (SPEC-AGY-002)

1. **新入帳目標與驗證結論**：
   - `scripts/lib/adversarial_team.py:missing_attacker_defender_duel_orchestrator` ➔ `REMEDIATED`（完成 4 階段對抗編排器實作）。
   - `.agents/skills/security-sentinel/scripts/runner.py:unintegrated_mode_switch_and_duel_dispatch` ➔ `REMEDIATED`（完成 `--mode duel` CLI 調度與 Worktree 接軌）。
   - `.agents/skills/security-sentinel/SKILL.md:fragmented_subagent_and_runner_documentation` ➔ `DISMISSED`（藍軍切斯特頓考古證實 Tier 1 CLI 自動化與 Tier 2 IDE 交談式協同為互補分層架構，非規格漂移）。
2. **台帳守恆性校驗**：
   - 執行 `python scripts/validate_security_ledger.py`：
   - `total_targets`: 252
   - `remediated_vulnerabilities`: 54
   - `verified_vulnerabilities`: 51
   - `dismissed_hypotheses`: 147
   - 數學恆等式：$54 + 51 + 147 = 252$ 完全閉環。

---

## 🏛️ 架構決策紀錄 (Architecture Decision Records)

- **AD-201 (Event Source Tagging & Dual-Guard Toast Suppression - SPEC-AUTH-003)**:
  - **Context**: `AppClientLayer` 無差別監聽 `tabiji:recovery_key_updated`，未登入訪客造訪首頁時觸發 `ensureValidSession()` 產生金鑰更新事件，誤彈出跨裝置同步 Toast。
  - **Decision**: 擴充 `tabiji:recovery_key_updated` 之 `detail.source` 欄位契約 (`initial_bootstrap`, `session_exchange`, `remote_sync`, `local_reanchor`)；`AppClientLayer` 實施 `!isUserLoggedIn()` 與 `detail.source !== "remote_sync"` 雙重過濾；`initSessionLifecycleListener` 在未登入時跳過首頁自動換票。
  - **Trade-offs**: 稍微增加事件資料負載，但徹底根除首頁誤報，並減少未登入訪客對後端換票端點的無效請求。
- **AD-202 (Unified Dual-Core CLI Adversarial Automation via `runner.py --mode duel` - SPEC-AGY-002 v1.4.0)**:
  - **Context**: 紅軍 (`sentinel-attacker`) 與藍軍 (`sentinel-defender`) 原先散落在 IDE交談子代理人中，缺乏與 CLI 批次審查工具之程式碼整合，開發者難以一鍵啟動自動化紅藍軍實體沙盒對抗。
  - **Decision**: 採納方案一，於 `scripts/lib/adversarial_team.py` 封裝 `orchestrate_adversarial_duel`，並為 `runner.py` 增設 `--mode {adaptive,duel,fast}` 參數，將 GitWorktreePool、PoC 紅燈擊穿、切斯特頓考古抗辯、Mantis Block G 補丁合成與良性對照檢驗無縫串接。
  - **Trade-offs**: 執行 `--mode duel` 時因需建立實體 Git Worktree 與執行兩輪 pytest，耗時約 2~4 秒，但換取 100% 先紅後綠之極致真實性與零 prompt 污染。
- **AD-203 (Mantis Block G Benign Control Invariant for Auth Toast Remediations)**:
  - **Context**: 修復未登入訪客 Toast 時，若修復手段為粗暴刪除監聽器或全面禁止 Toast，將破壞合法多裝置使用者在雲端金鑰輪替時的知情權（閹割補丁）。
  - **Decision**: 嚴格遵守 Mantis Block G，在測試與補丁中設立良性對照組（`TC-2`），確認合法登入用戶接收 `remote_sync` 時仍能正常顯示 Toast，守護既有業務能力。
  - **Trade-offs**: 必須在測試套件中維護雙重狀態 Mock，但確保代碼品質達到零降級（Zero-Regression）。

---

## 🛡️ 失敗路徑與經驗教訓 (Failed Paths & Hard Lessons)

- **FP-012 (Windows PowerShell `-p` 參數與 Flag 擺放順序陷阱)**:
  - **Symptom**: 在 `runner.py` 呼叫 `agy.exe` 時，若將 `-p` 放在前面且後方接 `--sandbox`（如 `agy.exe -p <prompt> --sandbox`），PowerShell 會將 `--sandbox` 誤判定為 `-p` 的參數值，拋出 `Error: -p took "--sandbox" as its prompt`。
  - **Resolution**: 在命令列陣列中一律採用 `f"-p={cli_prompt}"` 格式，並將 `--sandbox`、`--disable-slash-commands`、`--output-format json` 等標誌固定前置。
- **FP-013 (`agy.exe` 子代理人預設 Token 上限與 Thinking 截斷陷阱)**:
  - **Symptom**: 在批次審查時若將超過 60,000 字元的全量檔案直傳給 `agy.exe`，模型產生的思考權杖 (Thinking Tokens, 約 580+) 會耗盡 CLI 預設輸出額度，導致 JSON 回應被截斷為空字串，產生 `INCONCLUSIVE`。
  - **Resolution**: 審計目標必須指定 `start_line` 與 `end_line` 精確局部切片，將上下文限制在 40~100 行核心區塊，徹底消除 Token 耗盡截斷問題。
- **FP-014 (`isUserLoggedIn()` 跨測試依賴隱藏邊界 - 孤兒金鑰陷阱)**:
  - **Symptom**: 最初嘗試將 `isUserLoggedIn()` 簡化為嚴格要求 `user_nickname && user_uuid`，導致 `auth-session-resilience.test.ts` 的 TC-10 與 TC-11 失敗。
  - **Resolution**: 原來 TC-10/TC-11 刻意設計了「僅有 `user_recovery_key` 但缺乏 `user_nickname`」的極端情況，期望在 401 時觸發 `SessionReauthModal` 原地重錨，而非直接靜默清空會話。修復時必須區分 `handleReconnectOrResume`（僅服務具備完整身分之活躍用戶）與 `isUserLoggedIn` 本身的型別容錯定義。

---

## 🧬 Machine-Executable Invariant Rules

```json
[
  {
    "domain": "state_cache",
    "type": "INVARIANT_RULE",
    "id": "INV-AUTH-005",
    "title": "Unauthenticated Visitor Session Lifecycle & Recovery Toast Isolation",
    "content": "In frontend/components/app-client-layer.tsx and frontend/lib/auth-session.ts, unauthenticated visitors accessing '/' MUST NOT trigger toast notifications for '✨ 帳號引繼碼已自其他裝置同步更新' or automatically call ensureValidSession() on mount/reconnect. All tabiji:recovery_key_updated custom events MUST carry a detail.source tag ('initial_bootstrap', 'session_exchange', 'remote_sync', 'local_reanchor'). AppClientLayer MUST filter strictly with 'if (!isUserLoggedIn()) return;' and 'if (customEvent.detail?.source !== \"remote_sync\") return;'."
  },
  {
    "domain": "state_cache",
    "type": "INVARIANT_RULE",
    "id": "INV-AUTH-006",
    "title": "isUserLoggedIn() Operator Precedence & In-Place Reauth Boundary",
    "content": "In frontend/lib/auth-session.ts, isUserLoggedIn() MUST maintain backward compatibility for orphan recovery keys (where user_recovery_key exists without nickname) so that 401 triggers in-place re-auth modal (auth-session-resilience TC-10/TC-11). Do NOT conflate visitor mount suppression with isUserLoggedIn definition."
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-SENTINEL-002",
    "title": "Unified Dual-Core CLI Adversarial Duel Integration (--mode duel)",
    "content": "Security Sentinel CLI (runner.py) supports --mode {adaptive,duel,fast}. In --mode duel, runner.py dynamically acquires an isolated GitWorktreePool and executes orchestrate_adversarial_duel across 4 phases: (1) Attacker pytest PoC generation; (2) Physical Red Check with pytest -k 'not benign' (exit code 1); (3) Defender Chesterton's Fence archaeology evaluation (DISMISSED if proven intentional design); (4) Block replacement patch synthesis with Mantis Block G Benign Control green check (exit code 0)."
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-012",
    "title": "agy.exe CLI Flag Precedence with -p Option under Windows PowerShell",
    "content": "When invoking agy.exe CLI via subprocess under Windows PowerShell, placing -p before other flags (e.g., agy.exe -p <prompt> --sandbox) causes agy.exe to interpret '--sandbox' as the prompt string itself. Always format prompt as -p=<cli_prompt> and place flags (--sandbox, --disable-slash-commands, --output-format json) upfront."
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-013",
    "title": "Large File Prompt Token Exhaustion in Sentinel Validator Subagent",
    "content": "Passing entire 60k character source files to agy.exe subagent in batch runner runs exhausts the default output token limit on chain-of-thought thinking tokens (e.g. 586 thinking tokens / 622 total tokens), leaving insufficient tokens for JSON emission. Always constrain target inspection with start_line and end_line targeted code snippets."
  }
]
```

