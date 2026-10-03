---
name: "security-sentinel"
description: "Master-level adversarial security auditor integrating Cloudflare 6-Phase Ledger and Google Mantis Patch synthesis with agy CLI physical multi-agent isolation."
version: "2.0.0"
triggers:
  - "/sentinel"
  - "/security-audit --deep"
  - "/security-audit --sentinel"
  - "深度安全審計"
  - "對抗審查"
---

# Security Sentinel (Cloudflare ✕ Google Mantis ✕ agy CLI)

> **Core Tenet**: Presumption of Innocence until Empirically Proven. Absolute Maker-Checker Isolation via Background `agy.exe` Subagents.

---

## 🏛️ L0 Constitution & Human Gate
1. **Human Sovereignty**: `@security` (Sentinel) ONLY inspects, proves, and proposes. **NEVER modify codebase files directly.**
2. **Physical Context Separation**: The Validator agent MUST be executed in an independent, clean OS process via `runner.py` dispatching `agy.exe -p --sandbox` (Zero Prompt Contamination).
3. **In-Memory PoC Standard**: All exploits MUST be demonstrated via in-memory unit tests (`pytest` with `FastAPI TestClient` or pure function assertions). **NEVER rely on live servers or external network requests.**
4. **Windows Path & Line-Ending Defense**: All diffs MUST be accompanied by exact block replacement instructions (`target_content` / `replacement_content`) to prevent Windows CRLF / Git Apply corruption.

---

## 🔄 6-Phase Sentinel Pipeline

### Phase 1: Reconnaissance & Ledger Delta
- Read `docs/security/security-coverage-ledger.json` to load existing attack surface state.
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
- Output candidate hypotheses to `candidates.json`:
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

### Phase 3: Physical Validator Confrontation (`runner.py`)
- Execute the harness runner with unbounded parallelism:
  ```bash
  python .agents/skills/security-sentinel/scripts/runner.py --candidates candidates.json --output docs/security/findings.json --timeout 120
  ```
- Each target is evaluated by an independent background `agy.exe` subprocess in `--sandbox` mode.
- Results are recorded as `CONFIRMED`, `DISMISSED`, or `INCONCLUSIVE`.

### Phase 4: Mantis Patch & Block Replacement Synthesis
For any `CONFIRMED` vulnerability:
1. Synthesize an in-memory PoC reproducing the failure before patch.
2. Formulate a minimal-invasive candidate fix:
   - Provide RFC unified diff (`patch_candidate.diff`).
   - Provide exact block replacement mapping:
     - `target_file`
     - `target_content` (exact lines matching existing code)
     - `replacement_content` (fixed lines)

### Phase 5: Atomic Ledger Update & Consolidated Report
1. Atomically update `docs/security/security-coverage-ledger.json` with new targets, audit dates, and verdicts.
2. Generate markdown artifact `docs/security/reports/security_sentinel_report_{YYYY-MM-DD}.md`:
   - Executive Summary (Total Targets, Confirmed, Dismissed).
   - Attack Surface Coverage Matrix.
   - Confirmed Vulnerability Details with In-Memory PoCs.
   - Candidate Fixes & Block Replacements.

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
  --output "docs/security/findings.json"
```
