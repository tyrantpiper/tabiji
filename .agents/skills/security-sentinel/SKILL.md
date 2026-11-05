---
name: "security-sentinel"
description: "Master-level adversarial security auditor integrating Cloudflare 6-Phase Ledger, Google Mantis Patch synthesis (Block G Benign Control), and Harness^2 Conservation Identity with agy CLI physical multi-agent isolation."
version: "2.3.0"
triggers:
  - "/sentinel"
  - "/security-audit --deep"
  - "/security-audit --sentinel"
  - "深度安全審計"
  - "對抗審查"
  - "安全稽核"
---

# Security Sentinel (Cloudflare ✕ Google Mantis ✕ Harness² ✕ agy CLI)

> **Core Tenet**: Presumption of Innocence until Empirically Proven. Absolute Maker-Checker Isolation via Background `agy.exe` Subagents, Mantis Block G Benign Control, and Harness² Deterministic Conservation.

---

## 🏛️ L0 Constitution & Human Gate
1. **Human Sovereignty**: `@security` (Sentinel) ONLY inspects, proves, and proposes. **NEVER modify codebase files directly.**
2. **Physical Context Separation**: The Validator agent MUST be executed in an independent, clean OS process via `runner.py` dispatching `agy.exe -p --sandbox` (Zero Prompt Contamination).
3. **In-Memory PoC Standard**: All exploits MUST be demonstrated via in-memory unit tests (`pytest` with `FastAPI TestClient` or pure function assertions). **NEVER rely on live servers or external network requests.**
4. **Windows Path & Line-Ending Defense**: All diffs MUST be accompanied by exact block replacement instructions (`target_content` / `replacement_content`) to prevent Windows CRLF / Git Apply corruption.
5. **Chesterton's Fence & Code Archaeology (切斯特頓圍欄三問)**: Any finding or patch proposing code deletion or behavior change MUST pass the three-question archaeology protocol:
   - **功能反推 (legacy_function)**: 這些被刪除或質疑的代碼，在現有系統中具體扮演了什麼功能？
   - **設計初衷 (design_intent)**: 當初工程師為什麼要這樣設計？解決了什麼業務痛點或極端情況 (Corner Case)？
   - **刪除風險 (regression_risk)**: 刪除或重構後，是否會破壞未明寫但現有系統依賴的隱藏機制？新邏輯如何 100% 承接？
   嚴禁將刻意跨層解耦、單一資料源 (SSOT) 拆分計算、或對話狀態切換清理等系統架構設計誤判為漏洞。

---

## 🔄 6-Phase Sentinel Pipeline

### Phase 0: Pre-Execution Worktree Spiking (開工前沙盒驗證 / 假說預演)
Sentinel 不僅在程式碼完工後執行防禦審查，**更能在開工前進行沙盒驗證 (Pre-Implementation Spiking)**：
- 當面對架構重構、邊界條件不明確、或高風險邏輯調整時，在不污染主工作區的前提下：
  1. 調用 `GitWorktreePool` 快速建立獨立沙盒 worktree。
  2. 鏡像目標檔案並編寫 in-memory 測試驗證假說或極端情況（紅燈證明）。
  3. 驗證原型補丁能順利轉綠且無迴歸破壞後，再輸出至執行計畫，做到開工前 100% 確定性。

### Phase 1: Reconnaissance & Ledger Delta (Mantis-Advise)
- Read `docs/security/security-coverage-ledger.json` to load existing attack surface state.
- **Mantis-Advise Intent Ingestion**: Automatically extract `known_design_intents` and previous `DISMISSED` targets into the validator context. Pre-verified deliberate architectural patterns (such as SSOT calculations, trip switch chat resets, and 2nd-pass tool unloading) are shielded from redundant scrutiny.
- Identify new or modified files via `git status` or `git diff HEAD~1`.
- Categorize targets by Trust Boundaries:
  - `public_to_authenticated` (e.g. Login, JWT verification)
  - `authenticated_to_internal` (e.g. FastAPI services, Supabase RLS)
  - `browser_to_edge` (e.g. Next.js API proxies, Cloudflare Workers)

### Phase 2: Hunter Hypothesis Generation
- Analyze the target code for subtle vulnerabilities:
  - **Logic & Access Control**: IDOR, Role Escalation, RLS policy bypass, Token leakage.
  - **Edge & Proxies**: SSRF, Request smuggling, Header injection, Unchecked CORS.
  - **Input Sanitization**: ReDoS, Deserialization, Prompt Injection in AI routers.
- Output candidate hypotheses to `docs/security/history/candidates/candidates_<topic>_<YYYY-MM-DD>.json`:
  ```json
  [
    {
      "id": "backend/services/intent_router.py",
      "file_path": "backend/services/intent_router.py",
      "attack_vector": "prompt_injection",
      "hypothesis": "Sanitizer fails on zero-width space characters, allowing prompt override."
    }
  ]
  ```

### Phase 3: Dual-Mode Physical Validator Confrontation (`runner.py --mode duel` ✕ Native Subagents)
- **Gate A: Blue Team 考古證偽 (Chesterton Archaeology Gate)**:
  藍軍防禦者 (`sentinel-defender`) 必須對紅軍假說進行切斯特頓圍欄三問驗證。若代碼為故意設計（如 SSOT 分拆單一來源計算、行程切換狀態重刷、二階段工具卸載），藍軍即刻出具考古反推證據，以 `verdict: "DISMISSED"` 駁回誤判，避免過度修正。
- **Tier 1 (CLI Dual-Core Adversarial Automation — v2.4.0+)**:
  支援三種執行模式 (`--mode {adaptive,duel,fast}`)：
  1. **`--mode duel` (紅藍軍對抗全自動工作流)**：
     為每個假說自動分配隔離的 `GitWorktreePool`，依序執行四階段對抗：
     - *Phase 1*: 紅軍產出 PoC 測試 (`test_sentinel_poc`) 與良性對照 (`test_benign_*`)。
     - *Phase 2*: 實體 Worktree 紅燈檢驗 (執行 `pytest -k "not benign"`，要求嚴格 `exit code == 1` 擊穿)。
     - *Phase 3*: 藍軍切斯特頓圍欄考古審查，舉證刻意架構者駁回 (`DISMISSED`)。
     - *Phase 4*: 補丁合成與 Mantis Block G 良性對照綠燈驗證 (要求雙測全過 `exit code == 0`)。
     ```bash
     python .agents/skills/security-sentinel/scripts/runner.py --candidates docs/security/history/candidates/candidates_{topic}_{date}.json --mode duel --output docs/security/history/findings/findings_{topic}.json --timeout 120
     ```
  2. **`--mode adaptive` (自適應模式，預設)**：
     靜態審查所有候選目標，僅對 `high`/`critical` 或 `escalate_teamwork` 目標自動啟用 Worktree 實體紅綠驗證。
  3. **`--mode fast` (快速審查模式)**：
     純靜態驗證，跳過 Worktree 建立與實體 pytest 執行。
- **Tier 2 (IDE Native Red-vs-Blue Subagent Confrontation — 對話式互動)**:
  在 IDE 交談環境中，亦可手動透過 `define_subagent` 與 `invoke_subagent` 動態調度 `sentinel-attacker` 與 `sentinel-defender` 進行人機協同審核。
- Results are recorded as `CONFIRMED`, `DISMISSED`, or `INCONCLUSIVE` (enforcing strict `pytest` `exit code == 1` for Red confirmation).
- **Cloudflare Action-Binding Blockers**: If an external dependency blocks immediate confirmation, the verdict MUST be `INCONCLUSIVE` with explicit `validation_blocker` and `validation_plan`.
- **Mantis Marginal Capability Defense**: Issues confined strictly to self-impact or requiring impossible preconditions are capped to Low or `DISMISSED`.

### Phase 4: Mantis Patch & Block Replacement Synthesis (Block G Benign Control)
For any `CONFIRMED` vulnerability:
1. Synthesize an in-memory PoC reproducing the failure before patch.
2. **Mantis Block G Benign Control (良性對照防閹割)**:
   - PoC 必須包含 `test_benign*` 測試以驗證正常輸入。
   - 補丁套用後，必須同時通過攻擊測試與良性對照測試 (`benign_control_passed == True`)。
   - 任何藉由直接返回 `None`、`0` 或關閉功能來消除攻擊的「閹割補丁」一律自動阻斷並復原原始代碼。
3. Formulate a minimal-invasive candidate fix:
   - Provide RFC unified diff (`docs/security/history/patches/patch_candidate_{topic}_{YYYY-MM-DD}.diff`).
   - Provide exact block replacement mapping:
     - `target_file`
     - `target_content` (exact lines matching existing code)
     - `replacement_content` (fixed lines)
4. **Gate B: 補丁刪除逐行承接與 The Missing 1 Point 自檢**:
   - 凡涉及程式碼刪除，必須輸出完整考古矩陣 (`code_archaeology`: `legacy_function`, `design_intent`, `regression_risk`)，並說明替換邏輯如何 100% 承接舊邏輯職責。
   - 執行三維度自檢（邏輯一致性、遺漏邊界、評分與關鍵補足），確保補丁達 10/10 完美閉環。

### Phase 5: Atomic Ledger Update & Consolidated Report (Harness² Conservation)
1. **Harness² Deterministic Identity Assertion**:
   - `assert_findings_conservation`: 嚴格檢驗 `confirmed_count + dismissed_count + inconclusive_count == total_validated == len(findings)`。任何狀態漂移或統計脫節立即硬中斷。
2. Atomically update `docs/security/security-coverage-ledger.json` with new targets, audit dates, verdicts, `report_ref` (pointing to `docs/security/reports/{YYYY-MM}/...`), and `resolution` (pointing to `docs/security/history/patches/...`).
3. Generate markdown artifact in monthly archive `docs/security/reports/{YYYY-MM}/security_sentinel_report_{YYYY-MM-DD}_{topic}.md`:
   - Executive Summary (Total Targets, Confirmed, Dismissed).
   - Attack Surface Coverage Matrix.
   - Confirmed Vulnerability Details with In-Memory PoCs.
   - Candidate Fixes & Block Replacements.
   - Code Archaeology Matrix for all modifications/deletions.

### Phase 6: Human Gate Handover
- Present report to human developer (Ryan).
- Wait for human approval before passing the task to `@dev` for application and `@qa` for static type checking (`tsc`) and regression testing.

---

## ⚡ Quick Direct Auditing Example
To audit a single suspect file immediately:
```bash
python .agents/skills/security-sentinel/scripts/runner.py \
  --target-file "backend/services/intent_router.py" \
  --vector "prompt_injection" \
  --hypothesis "Sanitizer allows bypassing system instructions via unicode control characters" \
  --output "docs/security/history/findings/findings.json"
```
