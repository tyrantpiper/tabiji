---
name: "Bug Hunter"
description: "Master-level root cause analysis and active fault localization engine integrating Anthropic 3-tier hierarchical localization, backward call-graph tracing, and GitWorktreePool dual-mode sandboxing."
version: "2.0.0"
triggers:
  - "/bug-hunter"
  - "/hunt"
  - "除錯"
  - "debug"
  - "rca"
  - "根因分析"
---

# Bug Hunter 2.0: Active Fault Localization & Anti-Hallucination Engine

> **Core Tenet**: Presumption of Innocence until Empirically Proven. Absolute Maker-Checker Isolation via In-Memory PoC and GitWorktreePool.

---

## 🏛️ L0 Constitution & Principles
1. **The Single Hypothesis Law**: Before executing any command or editing any file, formulate exactly ONE testable hypothesis. No parallel guessing.
2. **Anthropic Hierarchical Localization**: Narrow fault scope progressively: `Repository -> File -> Function/Block -> Line Range (<= 20 lines)`.
3. **Dual-Mode Adaptive Sandboxing**:
   - **Mode A (In-Memory Trace)**: For pure logic / unit functions, perform static backward call-graph tracing via `ast_grep_search` and pure mocks (<10s, zero disk overhead).
   - **Mode B (Physical Worktree Spiking)**: For cross-module, database, or SSE stream defects, dispatch `GitWorktreePool.acquire()` into an ephemeral `.worktrees/sentinel-<uuid>` sandbox.
4. **Hugging Face Code-as-Action**: Synthesize reproducible Python/TypeScript test code directly; avoid brittle nested JSON tool-calling schemas.
5. **Perplexity Citation Grounding**: Every claim in the diagnosis report MUST cite precise `file:///path#Lxx-Lyy` evidence.

---

## 🔄 5-Phase Diagnostic Pipeline

### Phase 1: Symptom & Memory Grounding
1. Ingest `.agents/memory.md` and relevant `.agents/domains/*.md` to check if a similar bug or edge condition was previously solved.
2. Formulate the single testable hypothesis and identify the failure contract.

### Phase 2: Anthropic Backward Call-Graph Tracing
1. Locate the error stack trace entry point (`throw`, `AssertionError`, or unhandled rejection).
2. Trace backward through callers using `ast_grep_search`:
   - What caller provided the invalid argument?
   - Did any middleware strip authentication or mutate state?
   - Is there a temporal race condition or missing guard?

### Phase 3: Dual-Mode Reproduction Contract
1. Synthesize a minimal reproduction script adhering to **Google Mantis Block G**:
   - `test_exploit`: Triggers the failure (`returncode == 1`, valid red).
   - `test_benign`: Verifies legitimate existing functionality remains unharmed (`returncode == 0`).
2. Execute the reproduction in Mode A (memory) or Mode B (Worktree).

### Phase 4: Root Cause Formalization
Output the formal Root Cause Analysis (RCA) with:
- **Faulty File & Line Range**: `file:///path#Lxx-Lyy`
- **Root Mechanism**: Why the failure occurred.
- **Chesterton's Fence Context**: Why the code was originally written that way.

### Phase 5: Handoff to Self-Healing / TDD
Hand off the verified failing contract and benign control to `tdd-orchestrator` and `self-healing-agent` for minimal remediation.
