#!/usr/bin/env python3
"""
scripts/validate_security_ledger.py
===================================
Zero-dependency deterministic validator for docs/security/security-coverage-ledger.json
Inspired by Cloudflare Security Audit's validate-coverage-ledger.cjs.

Enforces:
1. Strict schema compliance (all entries MUST have 'id', NO legacy 'target_id').
2. Mathematical conservation invariants:
   total_targets == audited_targets == (verified + remediated + dismissed)
3. Target ID uniqueness across the entire ledger.
4. Allowed status lifecycle states:
   - Vulnerable cluster: VULNERABLE_CONFIRMED, VULNERABLE, PENDING_PATCH, CONFIRMED_PENDING_DEV
   - Remediated cluster: REMEDIATED
   - Dismissed cluster:  DISMISSED, SECURE, VERIFIED_SAFE, VERIFIED_BY_POC
5. Exact parity between statistical counters and enumerated array items.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, Tuple

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / "docs" / "security" / "security-coverage-ledger.json"

VULNERABLE_STATUSES = {
    "VULNERABLE_CONFIRMED",
    "VULNERABLE",
    "PENDING_PATCH",
    "CONFIRMED_PENDING_DEV",
}

REMEDIATED_STATUSES = {
    "REMEDIATED",
}

DISMISSED_STATUSES = {
    "DISMISSED",
    "SECURE",
    "VERIFIED_SAFE",
    "VERIFIED_BY_POC",
}

ALLOWED_STATUSES = VULNERABLE_STATUSES | REMEDIATED_STATUSES | DISMISSED_STATUSES


def validate_ledger_dict(data: Dict[str, Any]) -> Tuple[bool, str]:
    """Pure deterministic assertion function over ledger JSON data."""
    if not isinstance(data, dict):
        return False, "Ledger root must be a JSON object"

    stats = data.get("statistics")
    if not isinstance(stats, dict):
        return False, "Ledger missing 'statistics' object"

    for field in ("total_targets", "audited_targets", "verified_vulnerabilities", "remediated_vulnerabilities", "dismissed_hypotheses"):
        if field not in stats or not isinstance(stats[field], int):
            return False, f"Statistics field '{field}' must be an integer"

    total = stats["total_targets"]
    audited = stats["audited_targets"]
    verified = stats["verified_vulnerabilities"]
    remediated = stats["remediated_vulnerabilities"]
    dismissed = stats["dismissed_hypotheses"]

    # Mathematical conservation checks
    if total != audited:
        return False, f"Conservation violation: total_targets ({total}) != audited_targets ({audited})"

    if total != (verified + remediated + dismissed):
        return False, (
            f"Conservation violation: total_targets ({total}) != sum of states "
            f"(verified: {verified} + remediated: {remediated} + dismissed: {dismissed} = {verified + remediated + dismissed})"
        )

    targets = data.get("targets")
    if not isinstance(targets, list):
        return False, "Ledger missing 'targets' list"

    if len(targets) != total:
        return False, f"Item count mismatch: len(targets) ({len(targets)}) != total_targets ({total})"

    seen_ids = set()
    counted_verified = 0
    counted_remediated = 0
    counted_dismissed = 0

    for idx, target in enumerate(targets):
        if not isinstance(target, dict):
            return False, f"Target at index {idx} is not a JSON object"

        # Anti-polymorphic key guard
        if "target_id" in target:
            return False, f"Legacy 'target_id' detected at index {idx} ({target['target_id']}). Standardize to 'id'!"

        tid = target.get("id")
        if not tid or not isinstance(tid, str) or not tid.strip():
            return False, f"Target at index {idx} lacks valid non-empty 'id'"

        if tid in seen_ids:
            return False, f"Duplicate target id detected: '{tid}' at index {idx}"
        seen_ids.add(tid)

        status = target.get("status")
        if status not in ALLOWED_STATUSES:
            return False, f"Target '{tid}' has invalid status: '{status}'. Allowed: {ALLOWED_STATUSES}"

        if status in VULNERABLE_STATUSES:
            counted_verified += 1
        elif status in REMEDIATED_STATUSES:
            counted_remediated += 1
        elif status in DISMISSED_STATUSES:
            counted_dismissed += 1

    if counted_verified != verified:
        return False, f"Count parity mismatch for verified: counted {counted_verified} vs stats {verified}"

    if counted_remediated != remediated:
        return False, f"Count parity mismatch for remediated: counted {counted_remediated} vs stats {remediated}"

    if counted_dismissed != dismissed:
        return False, f"Count parity mismatch for dismissed: counted {counted_dismissed} vs stats {dismissed}"

    return True, f"Verified {total} targets ({remediated} remediated, {verified} verified/unresolved, {dismissed} dismissed/safe)."


def validate_ledger_file(file_path: Path = LEDGER_PATH) -> Tuple[bool, str]:
    if not file_path.exists():
        return False, f"Ledger file not found at {file_path}"
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return validate_ledger_dict(data)
    except Exception as e:
        return False, f"JSON parsing error: {e}"


def main() -> int:
    success, message = validate_ledger_file()
    if success:
        print(f"🟢 [LEDGER GUARD] {message}")
        return 0
    else:
        sys.stderr.write(f"🚨 [LEDGER GUARD ERROR] {message}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
