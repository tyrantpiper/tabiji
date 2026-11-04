#!/usr/bin/env python3
"""
Tiered Adversarial Team Validation Engine (adversarial_team.py)
---------------------------------------------------------------
Implements SPEC-AGY-002:
1. Attacker vs Defender 2-round Disprove-by-Default circuit breaker with Chesterton's Fence archaeology.
2. Mantis Block G Benign Control: prevents lobotomized patches by verifying benign tests pass before and after patch.
3. Strict pytest exit code disambiguation:
   - returncode == 1 -> RED_CONFIRMED (AssertionError: vulnerability proven)
   - returncode == 0 -> GREEN_SAFE (Defense held or remediation verified)
   - returncode >= 2 or < 0 -> INVALID_POC (ImportError / SyntaxError / Timeout)
4. Physical Red-Green verification inside an isolated GitWorktreePool directory.
"""

import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .safe_subprocess import ProcessResult, run_streaming_process

DEFAULT_CODE_ARCHAEOLOGY: Dict[str, Optional[str]] = {
    "legacy_function": None,
    "design_intent": None,
    "regression_risk": None,
}


def normalize_code_archaeology(raw_arch: Any) -> Dict[str, Optional[str]]:
    """
    Ensure code_archaeology dict conforms strictly to the 3 Chesterton questions schema:
    1. legacy_function: What capability does the code fulfill?
    2. design_intent: Why was it designed this way / corner case it solves?
    3. regression_risk: What breaks if deleted / how replacement preserves it?
    """
    if not isinstance(raw_arch, dict):
        return dict(DEFAULT_CODE_ARCHAEOLOGY)
    return {
        "legacy_function": (
            raw_arch.get("legacy_function")
            if isinstance(raw_arch.get("legacy_function"), str)
            else None
        ),
        "design_intent": (
            raw_arch.get("design_intent")
            if isinstance(raw_arch.get("design_intent"), str)
            else None
        ),
        "regression_risk": (
            raw_arch.get("regression_risk")
            if isinstance(raw_arch.get("regression_risk"), str)
            else None
        ),
    }


def _split_poc_test_names(poc_code: str) -> Tuple[List[str], List[str]]:
    """
    Extract test function names and split into:
    - exploit_tests: functions without 'benign' in their name
    - benign_tests: functions with 'benign' in their name (Mantis Block G Benign Control)
    """
    if not isinstance(poc_code, str):
        return [], []
    all_tests = re.findall(r"^\s*(?:async\s+)?def\s+(test_[A-Za-z0-9_]+)", poc_code, re.M)
    exploit_tests = [t for t in all_tests if "benign" not in t.lower()]
    benign_tests = [t for t in all_tests if "benign" in t.lower()]
    return exploit_tests, benign_tests


TEAMWORK_ATTACKER_PROMPT = """
You are Sentinel-Attacker (Red Team) in a strictly isolated Git Worktree.
Your mission is to evaluate the target file and construct a self-contained, deterministic Python `pytest` test function (`def test_sentinel_poc(): ...`) that empirically proves the hypothesized flaw via an `AssertionError`.

Strict Rules:
1. Do NOT use network calls or external servers.
2. Import modules relative to `backend/` (e.g., `from services.intent_router import _fast_path_classify`).
3. If the code already defends against the hypothesis or is an intentional design pattern, set `"verdict": "DISMISSED"`.
4. If vulnerable, provide `"poc_script"` (valid python pytest code) and `"block_replacement"` (`{"target_content": "...", "replacement_content": "..."}`) to remediate it.
5. If proposing block replacement that deletes or alters lines, provide `"code_archaeology"` fulfilling Chesterton's Fence protocol.
6. (Mantis Block G): When possible, include a companion `def test_benign_control():` in `poc_script` verifying normal expected inputs continue to work properly.

Output strictly valid JSON:
{
  "target_id": "<target_id>",
  "verdict": "CONFIRMED" | "DISMISSED",
  "reasoning": "<concise technical explanation>",
  "poc_type": "pytest_in_memory" | "none",
  "poc_script": "<complete python test code or null>",
  "code_archaeology": {
    "legacy_function": "<purpose of original lines or null>",
    "design_intent": "<design intent or null>",
    "regression_risk": "<hidden dependency or null>"
  },
  "block_replacement": {
    "target_content": "<exact original lines or null>",
    "replacement_content": "<remediated lines or null>"
  }
}
"""

TEAMWORK_DEFENDER_PROMPT = """
You are Sentinel-Defender (Blue Team) in an isolated, read-only environment.
Your mission is to defend the codebase against false-positive vulnerability reports by executing the Chesterton's Fence & Code Archaeology Protocol:

1. Legacy Function: What exact business capability or architectural boundary does the flagged code fulfill?
2. Design Intent: Why was it implemented this way? (e.g. Single-Source-of-Truth calculation split, deliberate context reset, 2nd-pass tool unloading)
3. Regression Risk: If deleted or modified, what hidden dependency or corner-case protection will break?

Output strictly valid JSON:
{
  "target_id": "<target_id>",
  "verdict": "CONFIRMED" | "DISMISSED",
  "reasoning": "<concise technical explanation>",
  "code_archaeology": {
    "legacy_function": "<purpose of the code in current system>",
    "design_intent": "<why it was designed this way / corner case it handles>",
    "regression_risk": "<hidden dependency or why deleting it breaks the system>"
  }
}
"""


def classify_pytest_outcome(res: ProcessResult) -> str:
    """
    Strictly distinguish pytest exit codes:
    - 0: All tests passed (GREEN_SAFE)
    - 1: Tests were collected and run but some failed assertions (RED_CONFIRMED)
    - >=2 or <0: Interrupted, internal error, usage/import error, or no tests collected (INVALID_POC)
    """
    if res.timed_out or res.returncode < 0:
        return "INVALID_POC"
    if res.returncode == 0:
        return "GREEN_SAFE"
    if res.returncode == 1:
        return "RED_CONFIRMED"
    return "INVALID_POC"


async def execute_worktree_pytest(
    wt_path: Path,
    poc_code: str,
    timeout_seconds: float = 30.0,
    k_expr: Optional[str] = None,
) -> ProcessResult:
    """
    Write temporary PoC test into <wt_path>/backend/tests/, execute pytest with
    PYTHONPATH=<wt_path>/backend, optional -k filter, and guarantee file deletion on exit.
    """
    wt_resolved = wt_path.resolve()
    backend_dir = (wt_resolved / "backend").resolve()
    tests_dir = backend_dir / "tests" if backend_dir.exists() else wt_resolved
    run_cwd = backend_dir if backend_dir.exists() else wt_resolved

    tests_dir.mkdir(parents=True, exist_ok=True)
    poc_file = tests_dir / f"_sentinel_poc_{uuid.uuid4().hex[:8]}.py"
    poc_file.write_text(poc_code, encoding="utf-8")

    python_path_entries = [str(run_cwd)]
    if str(wt_resolved) not in python_path_entries:
        python_path_entries.append(str(wt_resolved))
    python_path = os.pathsep.join(python_path_entries)

    cmd = [sys.executable, "-m", "pytest", str(poc_file), "-q", "--tb=short"]
    if k_expr:
        cmd.extend(["-k", k_expr])

    try:
        return await run_streaming_process(
            cmd=cmd,
            cwd=run_cwd,
            env={"PYTHONPATH": python_path},
            timeout_seconds=timeout_seconds,
        )
    finally:
        poc_file.unlink(missing_ok=True)


def apply_block_replacement_in_worktree(
    wt_path: Path,
    rel_file: str,
    target_content: str,
    replacement_content: str,
) -> bool:
    """
    Apply CRLF-resilient block replacement to a target file inside the isolated worktree.
    """
    if not target_content or replacement_content is None:
        return False

    wt_resolved = wt_path.resolve()
    target_path = (wt_resolved / rel_file).resolve()
    if not target_path.is_relative_to(wt_resolved) or not target_path.is_file():
        return False

    raw_text = target_path.read_text(encoding="utf-8", errors="replace")
    if target_content in raw_text:
        updated = raw_text.replace(target_content, replacement_content, 1)
        target_path.write_text(updated, encoding="utf-8")
        return True

    # Fallback: normalize CRLF -> LF for comparison
    norm_raw = raw_text.replace("\r\n", "\n")
    norm_target = target_content.replace("\r\n", "\n")
    norm_replacement = replacement_content.replace("\r\n", "\n")
    if norm_target in norm_raw:
        updated = norm_raw.replace(norm_target, norm_replacement, 1)
        target_path.write_text(updated, encoding="utf-8")
        return True

    return False


async def verify_candidate_in_worktree(
    wt_path: Path,
    target: Dict[str, Any],
    candidate_result: Dict[str, Any],
    timeout_seconds: int = 30,
) -> Dict[str, Any]:
    """
    Given a candidate verdict and PoC script, run the physical Red-Green cycle inside wt_path.
    Enforces Mantis Block G Benign Control and Disprove-by-Default circuit breaker.
    """
    target_id = target.get("id", "unknown")
    rel_file = target.get("file_path", target_id)
    poc_script = candidate_result.get("poc_script")
    code_archaeology = normalize_code_archaeology(candidate_result.get("code_archaeology"))

    if candidate_result.get("verdict") != "CONFIRMED":
        candidate_result["code_archaeology"] = code_archaeology
        candidate_result["worktree_verified"] = True
        candidate_result["patch_test_passed"] = False
        candidate_result["benign_control_passed"] = None
        return candidate_result

    if not isinstance(poc_script, str) or not poc_script.strip():
        return {
            "target_id": target_id,
            "verdict": "DISMISSED",
            "reasoning": "[Disprove-by-Default Circuit Breaker] CONFIRMED verdict lacked an executable pytest poc_script.",
            "worktree_verified": True,
            "poc_type": "none",
            "poc_script": None,
            "code_archaeology": code_archaeology,
            "remediation_hint": None,
            "patch_test_passed": False,
            "benign_control_passed": None,
        }

    exploit_tests, benign_tests = _split_poc_test_names(poc_script)
    has_separate_benign = bool(exploit_tests and benign_tests)

    # Phase 1: Physical Red Check
    # If separate benign tests exist, run exploit tests with -k "not benign" to prevent
    # a broken benign test from causing a false red confirmation.
    red_k = "not benign" if has_separate_benign else None
    red_res = await execute_worktree_pytest(wt_path, poc_script, timeout_seconds=float(timeout_seconds), k_expr=red_k)
    red_status = classify_pytest_outcome(red_res)

    if red_status == "GREEN_SAFE":
        return {
            "target_id": target_id,
            "verdict": "DISMISSED",
            "reasoning": (
                f"[Worktree Physical Defense Proof] Proposed PoC passed with exit code 0 "
                f"(defense already holds). Original claim disproved."
            ),
            "worktree_verified": True,
            "poc_type": "none",
            "poc_script": None,
            "code_archaeology": code_archaeology,
            "remediation_hint": None,
            "patch_test_passed": False,
            "benign_control_passed": None,
        }

    if red_status == "INVALID_POC":
        return {
            "target_id": target_id,
            "verdict": "DISMISSED",
            "reasoning": (
                f"[Disprove-by-Default Circuit Breaker] Attacker PoC failed to execute cleanly "
                f"(exit code {red_res.returncode}, expected 1 for AssertionError). "
                f"Output: {(red_res.stdout or red_res.stderr)[:240]}"
            ),
            "worktree_verified": True,
            "poc_type": "none",
            "poc_script": None,
            "code_archaeology": code_archaeology,
            "remediation_hint": None,
            "patch_test_passed": False,
            "benign_control_passed": None,
        }

    # Mantis Block G: Check unpatched benign baseline if separate benign tests exist
    unpatched_benign_valid = True
    if has_separate_benign:
        benign_base_res = await execute_worktree_pytest(
            wt_path, poc_script, timeout_seconds=float(timeout_seconds), k_expr="benign"
        )
        if classify_pytest_outcome(benign_base_res) != "GREEN_SAFE":
            unpatched_benign_valid = False

    # red_status == "RED_CONFIRMED": Vulnerability empirically proven!
    candidate_result["code_archaeology"] = code_archaeology
    candidate_result["worktree_verified"] = True
    candidate_result["patch_test_passed"] = False
    candidate_result["benign_control_passed"] = None

    # Phase 2: Optional Physical Green Check if block_replacement is provided
    raw_block_rep = candidate_result.get("block_replacement")
    block_rep = raw_block_rep if isinstance(raw_block_rep, dict) else {}
    t_content = block_rep.get("target_content")
    r_content = block_rep.get("replacement_content")
    if t_content and r_content is not None:
        wt_resolved = wt_path.resolve()
        target_path = (wt_resolved / rel_file).resolve()
        original_bytes = (
            target_path.read_bytes()
            if target_path.is_relative_to(wt_resolved) and target_path.is_file()
            else None
        )
        applied = apply_block_replacement_in_worktree(wt_path, rel_file, t_content, r_content)
        if applied:
            # Run all tests (both exploit and benign) against the patched file
            green_res = await execute_worktree_pytest(wt_path, poc_script, timeout_seconds=float(timeout_seconds))
            if classify_pytest_outcome(green_res) == "GREEN_SAFE":
                candidate_result["patch_test_passed"] = True
                if has_separate_benign and unpatched_benign_valid:
                    candidate_result["benign_control_passed"] = True
            else:
                # Patch failed: either exploit still triggers or benign control was broken (lobotomized patch)
                candidate_result["patch_test_passed"] = False
                if has_separate_benign and unpatched_benign_valid:
                    candidate_result["benign_control_passed"] = False
                if original_bytes is not None:
                    target_path.write_bytes(original_bytes)

    return candidate_result
