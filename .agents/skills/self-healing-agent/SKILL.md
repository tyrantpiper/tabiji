---
name: "Self-Healing Agent"
description: "Autonomous error healing engine integrating Google Research Harness^2 state-space backtracking, Mantis-Advise historical intent injection, and Windows CRLF block replacement."
version: "2.0.0"
triggers:
  - "/heal"
  - "/self-heal"
  - "自動修復"
  - "auto-fix"
  - "fix build"
---

# Self-Healing Agent 2.0 (Harness² State-Space Backtracking & Mantis-Advise)

> **Core Principle**: Zero Patch Stacking. If an attempt fails, revert to clean state before re-attempting.

---

## 🛡️ Harness² State-Space Backtracking
- **Attempt 1**: Minimal targeted fix based on RCA.
- **Validation**: Run Dual-Pass Test (`test_exploit` + `test_benign`).
- **Rollback Rule**: If Attempt 1 fails or breaks `test_benign`, **DO NOT stack a second patch on top**. Execute `git checkout` to restore the clean state, ingest the error evidence, and formulate Attempt 2.
- **Circuit Breaker**: Maximum 3 attempts. Upon 3rd failure, immediately emit `BLOCKED.md` to trigger the human checkpoint.

---

## 🧠 Mantis-Advise Historical Guard Injection
Before applying any patch:
1. Ingest `docs/security/security-coverage-ledger.json` top-level `known_design_intents`.
2. Ensure the candidate patch does not delete or weaken guards established by historical architecture decisions (ADRs).
3. Enforce **Chesterton's Fence 3-Question Protocol** (`legacy_function`, `design_intent`, `regression_risk`).

---

## 🛠️ Occam's Razor & Windows CRLF Block Replacement
1. **Patch Bounds**: Limit modifications to $\le 20$ lines per target. Whole-file rewrites are strictly prohibited.
2. **Exact Block Replacement**: Always specify exact `target_content` and `replacement_content` to prevent Windows CRLF / Git Apply corruption.
3. **Cloudflare Action-Binding**: If the issue requires live external network or credentials not available in sandbox, mark as `INCONCLUSIVE` and output an explicit action plan.
