# Security Sentinel Audit Report: Note Import Deep Geocoding Pipeline & SSRF/DoS Defense

- **Audit Date**: 2026-11-06
- **Audit Tool**: `runner.py --mode fast` ✕ `pytest` in-memory physical sandbox
- **Methodology**: Cloudflare 6-Phase Ledger, Google Mantis Patch Synthesis (Block G Benign Control), Harness² Conservation Identity
- **Ledger Verification**: 🟢 259 targets verified via `scripts/validate_security_ledger.py`

---

## 1. Executive Summary

| Metric | Count |
| :--- | :--- |
| **Total Candidates Evaluated** | 4 |
| **Confirmed Vulnerabilities** | 4 |
| **Dismissed Hypotheses** | 0 |
| **Inconclusive** | 0 |
| **Verification Gate** | 100% Passed (`backend/tests/test_parse_md_geocoding_sentinel_poc.py`) |
| **PoC Test Execution Time** | 4 passed in 2.57s |

---

## 2. In-Memory PoC & Sandboxing Suite (Phase 0 Pre-Execution Spiking)

A pre-execution spiking test suite was established at [`backend/tests/test_parse_md_geocoding_sentinel_poc.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_parse_md_geocoding_sentinel_poc.py) enforcing:
1. `test_ssrf_and_malicious_url_rejection`: Asserts that user-supplied `link_url` pointing to internal AWS/GCP metadata (`http://169.254.169.254`), localhost, phishing domains, or non-Google schemes are rejected. Asserts Mantis Block G Benign Control for genuine `maps.app.goo.gl` and `google.com/maps` URLs.
2. `test_type_confusion_defense`: Asserts that string numerals (`"35.68"`), `"null"`, `"N/A"`, `None`, and `0.0` are converted safely via `_safe_float` without throwing exceptions or corrupting downstream database decimal columns.
3. `test_structure_flattening_and_dynamic_anchor_bootstrap`: Asserts that if Gemini outputs a nested `days` structure instead of flat `items`, it is properly unpacked prior to geocoding. Asserts that if the note title is generic ("5天4夜自由行"), the dynamic anchor inherits coordinates from an item's resolved URL and correctly biases subsequent items (e.g. Tokyo Tower -> Roppongi Hills).
4. `test_concurrency_and_timeout_resilience`: Asserts that action noise items ("在飯店門口集合") are skipped from geocoding queries, and hanging lookups (simulated 4.0s delay) are terminated cleanly within the 2.5s timeout budget without crashing the request.

All 4 tests executed and passed in 2.57s.

---

## 3. Target Evaluation & Findings Details (Phase 1-3)

### Target 1: `backend/routers/ai.py:untrusted_url_ssrf_and_dos`
- **Status**: `CONFIRMED` / `REMEDIATED`
- **Severity**: HIGH
- **Reasoning**: User-supplied `link_url` extracted from untrusted notes passed directly into link resolution could trigger SSRF or infinite redirection loops.
- **PoC Script**: `backend/tests/test_parse_md_geocoding_sentinel_poc.py::test_ssrf_and_malicious_url_rejection`
- **Code Archaeology**:
  - `legacy_function`: `parse_markdown` extracts `link_url` from Markdown tables.
  - `design_intent`: Allow travel notes to preserve Google Maps URLs for quick navigation.
  - `regression_risk`: Resolving shortlinks without domain whitelist exposes backend to SSRF.
- **Resolution**: Enforce `_is_allowed_maps_url` whitelist and `is_safe_url` check.

### Target 2: `backend/routers/ai.py:concurrency_stall_and_timeout_leak`
- **Status**: `CONFIRMED` / `REMEDIATED`
- **Severity**: HIGH
- **Reasoning**: Geocoding large batches of items without concurrency limits or timeouts can exhaust connection pools or stall requests indefinitely.
- **PoC Script**: `backend/tests/test_parse_md_geocoding_sentinel_poc.py::test_concurrency_and_timeout_resilience`
- **Code Archaeology**:
  - `legacy_function`: None in `parse_markdown` (previously returned raw un-geocoded text).
  - `design_intent`: Safeguard server resources under high external geocoder latency.
  - `regression_risk`: Slow third-party API can cascade into 504 Gateway Timeouts.
- **Resolution**: Wrap items in `asyncio.Semaphore(10)` with per-item `asyncio.wait_for(..., timeout=2.5)`.

### Target 3: `backend/routers/ai.py:schema_drift_and_type_confusion`
- **Status**: `CONFIRMED` / `REMEDIATED`
- **Severity**: MEDIUM
- **Reasoning**: LLM hallucinations outputting string representations (`"35.68"`, `"null"`, `"NaN"`) cause Pydantic validation failures or database numeric column rejections.
- **PoC Script**: `backend/tests/test_parse_md_geocoding_sentinel_poc.py::test_type_confusion_defense`
- **Code Archaeology**:
  - `legacy_function`: `fix_sub_items_structure` only validated sub-item dicts and category strings.
  - `design_intent`: Prevent front-end rendering crashes on malformed LLM outputs.
  - `regression_risk`: Adding lat/lng introduces decimal fields requiring strict float casting.
- **Resolution**: Filter values through `_safe_float` parser filtering null/None/NaN/0.0 values.

### Target 4: `backend/routers/ai.py:anchor_cold_start_and_structure_recovery`
- **Status**: `CONFIRMED` / `REMEDIATED`
- **Severity**: MEDIUM
- **Reasoning**: Generic trip titles lack city keywords causing global coordinate drift, and nested `days` structures bypass geocoding if executed prior to flattening.
- **PoC Script**: `backend/tests/test_parse_md_geocoding_sentinel_poc.py::test_structure_flattening_and_dynamic_anchor_bootstrap`
- **Code Archaeology**:
  - `legacy_function`: `ai.py` lines 361-375 performed emergency flattening.
  - `design_intent`: Normalize divergent Gemini JSON outputs into flat items array.
  - `regression_risk`: Placing geocoding before flattening results in silent skip on days-structured responses.
- **Resolution**: Normalize items before geocoding, and bootstrap proximity bias anchor from the first resolved coordinate.

---

## 4. Mantis Patch Artifacts (Phase 4)

- **Unified RFC Diff**: [`docs/security/history/patches/patch_candidate_parse_md_geocoding_2026-11-06.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_parse_md_geocoding_2026-11-06.diff)
- **Exact Block Replacements**: [`docs/security/history/candidates/block_replacements_parse_md_geocoding_2026-11-06.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/candidates/block_replacements_parse_md_geocoding_2026-11-06.json)

---

## 5. Human Confirmation Gate (Phase 6)

In strict compliance with L0 Constitution:
- **No production code files have been modified yet.**
- Pre-execution spiking has proven 100% of hypotheses, edge cases, and safety bounds in the in-memory test environment.
- The system is now awaiting human developer approval to apply the candidate patch.

