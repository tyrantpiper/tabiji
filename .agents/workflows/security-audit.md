---
name: "security-audit"
description: "Dual-mode security gateway: fast dependency/secret scanning and deep adversarial sentinel auditing."
triggers:
  - "/security-audit"
  - "/sentinel"
  - "/security-audit --deep"
  - "/security-audit --sentinel"
  - "安全"
  - "security"
  - "漏洞"
  - "深度安全審計"
  - "升級依賴"
  - "dep upgrade"
---

# Security Gateway & Dependency Upgrade Workflow (/security-audit)

> **Principle**: Report, Don't Blindly Fix. Fast Gates on Commit, Deep Adversarial Sentinel on Demand.

---

## 🚦 Mode Dispatcher

When invoked, inspect CLI flags or trigger intent:
- **Mode A: Quick Static & Secret Audit (Default)**: Runs when invoked without flags or with `--quick`. Completes within 30 seconds.
- **Mode B: Deep Adversarial Sentinel Audit**: Runs when invoked with `--deep`, `--sentinel`, or `/sentinel`. Dispatches `security-sentinel` with background `agy.exe` subagents.

---

## Mode A: Quick Static & Dependency Audit (Default)

### Step 1: Dependency & Secret Scanning (tools-hub Powered)
1. **Dependency Audit**:
   ```bash
   cd frontend; npm audit --production; cd ..
   ```
2. **Verified Secret Leak Detection (`trufflehog_scan`)**:
   - 執行活體憑證掃描，排除 `node_modules` 與暫存區，精準捕捉已驗證之高危洩漏：
     `trufflehog_scan(path="frontend/app", only_verified=true)`
     `trufflehog_scan(path="backend", only_verified=true)`
     `trufflehog_scan(path="docs", only_verified=true)`
   - 檢查 `.env*` 檔案皆已包含於 `.gitignore`。
3. **AST Sensitive Call Audit (`ast_grep_search`)**:
   - 掃描是否有硬編碼密鑰或非法的危險代碼執行：
     `ast_grep_search(lang="typescript", path="frontend", pattern="process.env.SUPABASE_SERVICE_ROLE_KEY")`
     `ast_grep_search(lang="python", path="backend", pattern="eval($$$ARGS)")`
4. **API & CORS Hardening**:
   - Verify `backend/main.py` CORS does not allow `["*"]` in production.
   - Verify rate-limiting (`@limiter`) covers sensitive endpoints.

### Step 2: Safe Dependency Upgrade Protocol
When dependency vulnerabilities or outdated packages are identified:
1. **Outdated Scan & Categorization**:
   ```bash
   cd frontend; npm outdated --json; cd ..
   ```
   - 🟢 **Security & Patch Updates** ($X.Y.Z \to X.Y.Z+1$): Eligible for immediate upgrade.
   - 🟡 **Minor Updates** ($X.Y \to X.Y+1$): Require verification of non-breaking changes.
   - 🔴 **Major Updates** ($X \to X+1$): Require dedicated implementation plan.
2. **Upgrade Safety Valves**:
   - Backup `package-lock.json` before upgrade.
   - Run `npx tsc --noEmit` in `frontend` and `pytest backend/tests/` immediately after upgrade.
   - Generate rollback command if build breaks.

### Step 3: Quick Audit Report
- Generate summary of vulnerabilities, secret scan status, and package upgrade recommendations.

---

## Mode B: Deep Adversarial Sentinel Audit (`--deep` / `--sentinel` / `/sentinel`)

Dispatches the composite `security-sentinel` skill:

1. **Reconnaissance**: Read `docs/security/security-coverage-ledger.json` and map unverified trust boundaries.
2. **Hunter Hypothesis Generation**: Generate candidate exploit vectors (IDOR, RLS Bypass, SSRF, Deserialization).
3. **Physical Validator Confrontation**:
   - Run the Python harness runner to launch background `agy.exe` subagents in `--sandbox` mode:
     ```bash
     python .agents/skills/security-sentinel/scripts/runner.py --candidates candidates.json --output docs/security/findings.json --timeout 120
     ```
4. **Mantis Patch & In-Memory PoC Synthesis**:
   - For confirmed vulnerabilities, generate in-memory `pytest` reproduction tests and candidate patches with exact block replacement instructions.
5. **Ledger Atomic Update & Reporting**:
   - Update `docs/security/security-coverage-ledger.json`.
   - Produce `docs/security/reports/security_sentinel_report_{YYYY-MM-DD}.md`.
6. **Human Gate**:
   - Present findings to human developer. Await authorization before delegating to `@dev` for fixes and `@qa` for regression testing.

---

## [NEURAL] Neural Linkage
Execute telemetry signal upon completion:
```bash
python backend/scripts/telemetry.py --source "Security Audit" --message "Security audit completed" --level "INFO"
```
