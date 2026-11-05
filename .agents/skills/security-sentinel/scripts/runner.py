#!/usr/bin/env python3
"""
Security Sentinel Harness Runner (runner.py)
Orchestrates independent agy.exe CLI subagents in read-only mode
for zero-prompt-contamination adversarial validation.
"""

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

def find_repo_root() -> Path:
    """自動自適應解析目標倉庫根目錄：
    1. 優先由當前工作目錄 Path.cwd() 向上查找包含 .git 或 .agents 的專案根目錄
    2. 若腳本位於專案內 (.agents/skills/...) 則解析其上層目錄
    3. 兜底回退至 Path.cwd()
    """
    cwd = Path.cwd().resolve()
    for p in [cwd] + list(cwd.parents):
        if (p / ".git").exists() or (p / ".agents").exists():
            return p
    script_path = Path(__file__).resolve()
    if len(script_path.parents) >= 5 and script_path.parents[3].name == ".agents":
        return script_path.parents[4]
    return cwd


# Self-resolving sys.path to locate scripts.lib.safe_subprocess and local lib across arbitrary CWDs
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = find_repo_root()
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))


def assert_security_path_hygiene(file_path: Optional[str], param_name: str, repo_root: Path = _REPO_ROOT) -> None:
    """🛡️ 根目錄衛生強制防呆：禁止任何中繼檔案落在專案根目錄"""
    if not file_path:
        return

    # 1. 裸檔名檢查（無目錄前綴，如 candidates.json 或 ./candidates.json）
    given_parent = Path(file_path).parent
    is_bare = str(given_parent) in ("", ".") or not given_parent.name

    # 2. 根目錄解析檢查（無論由何處解析，父目錄不得為 repo_root）
    resolved_path = Path(file_path).resolve()
    norm_parent = os.path.normcase(str(resolved_path.parent))
    norm_root = os.path.normcase(str(repo_root))

    # 3. 相對於 repo_root 的解析檢查
    root_resolved_path = (repo_root / file_path).resolve()
    norm_root_resolved_parent = os.path.normcase(str(root_resolved_path.parent))

    if is_bare or norm_parent == norm_root or norm_root_resolved_parent == norm_root:
        sys.stderr.write(
            f"\n🚨 [Root Hygiene Violation] 參數 '{param_name}' 路徑 ({file_path}) 嚴禁直接置於專案根目錄！\n"
            f"👉 請依規範存放於 docs/security/ 目錄（例如: docs/security/candidates_<topic>_<date>.json）。\n\n"
        )
        sys.exit(1)

run_streaming_process = None
try:
    import importlib
    _safe_subproc = importlib.import_module("scripts.lib.safe_subprocess")
    run_streaming_process = getattr(_safe_subproc, "run_streaming_process", None)
except Exception:
    run_streaming_process = None

VALIDATOR_SYSTEM_PROMPT = """
You are an objective Software Quality and Defensive Architecture Reviewer.
Your mission is to evaluate whether a proposed code robustness or security issue actually exists in the provided code snippet.

Rules:
1. Do NOT execute any external tools, bash commands, or subagents. Rely SOLELY on static inspection of the provided code snippet.
2. Presumption of Correctness: Assume the code handles requirements properly unless you can point to an exact unhandled condition or defect.
3. In-Memory Mock Testing: If an issue is confirmed, formulate an in-memory test (e.g. pytest unit test with mock or FastAPI TestClient). Never assume live servers.
4. Chesterton's Fence & Code Archaeology: If proposing to delete or modify existing logic, analyze what function it fulfilled, why it was designed that way, and regression risks. Provide "code_archaeology" object.
5. Marginal Capability & Self-Impact (Mantis): If the issue only affects the current execution context or requires pre-existing root/privileged arbitrary file write, cap severity to Low or mark DISMISSED as defense-in-depth unless it escalates privilege.
6. Blocker & Action-Binding (Cloudflare): If the hypothesis cannot be confirmed without external deployment infrastructure or live network access, do NOT speculate. Mark "verdict": "INCONCLUSIVE", specify "validation_blocker" explaining the missing prerequisite, and supply a concrete "validation_plan".

Output MUST be strictly valid JSON matching this schema:
{
  "target_id": "<target_id>",
  "verdict": "CONFIRMED" | "DISMISSED" | "INCONCLUSIVE",
  "reasoning": "<concise technical explanation of why the code is safe or why it has an unhandled flaw>",
  "validation_blocker": "<explanation of missing external dependency if INCONCLUSIVE, else null>",
  "validation_plan": "<concrete steps to verify once blocker is resolved if INCONCLUSIVE, else null>",
  "poc_type": "pytest_in_memory" | "unit_test" | "none",
  "poc_script": "<python pytest test code or null>",
  "code_archaeology": {
    "legacy_function": "<purpose of original code or null>",
    "design_intent": "<why it was designed this way or null>",
    "regression_risk": "<what could break if changed or null>"
  },
  "remediation_hint": "<suggested code modification or null>",
  "block_replacement": {
    "target_content": "<exact original lines to replace if CONFIRMED, else null>",
    "replacement_content": "<remediated lines if CONFIRMED, else null>"
  }
}
"""


def load_historical_design_intents(repo_root: Path, rel_file: str) -> str:
    """
    Extract known design intents and previously DISMISSED hypotheses for target file
    from docs/security/security-coverage-ledger.json (Mantis-Advise pattern).
    """
    norm_file = rel_file.replace("\\", "/")
    ledger_path = repo_root / "docs" / "security" / "security-coverage-ledger.json"
    if not ledger_path.is_file():
        return ""

    try:
        data = json.loads(ledger_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return ""

    matched_intents = []
    # 1. Check top-level known_design_intents dict
    known_dict = data.get("known_design_intents", {})
    if isinstance(known_dict, dict):
        for pattern, desc in known_dict.items():
            if pattern in norm_file:
                matched_intents.append(f"- [Known Architectural Intent]: {desc}")

    # 2. Check previous DISMISSED targets matching file
    for t in data.get("targets", []):
        if not isinstance(t, dict):
            continue
        t_id = str(t.get("id", ""))
        t_status = str(t.get("status", "")).upper()
        if norm_file in t_id and t_status == "DISMISSED":
            details = t.get("validator_details") or t.get("resolution") or "Intentional design"
            matched_intents.append(f"- [Historical DISMISSED Defense]: ({t_id}) {details}")

    if not matched_intents:
        return ""
    return "\n[Known Intentional Architecture & Past Verified Dismissals]:\n" + "\n".join(matched_intents[:4]) + "\n"


def assert_findings_conservation(output_data: Dict[str, Any]) -> None:
    """
    Deterministic identity assertion (Harness^2 ledger.py):
    confirmed_count + dismissed_count + inconclusive_count == total_validated == len(findings)
    """
    total = int(output_data.get("total_validated", 0))
    c = int(output_data.get("confirmed_count", 0))
    d = int(output_data.get("dismissed_count", 0))
    i = int(output_data.get("inconclusive_count", 0))
    findings = output_data.get("findings", [])

    if len(findings) != total:
        raise AssertionError(f"Ledger length mismatch: len(findings)={len(findings)} != total_validated={total}")
    if (c + d + i) != total:
        raise AssertionError(
            f"Ledger conservation failure: confirmed({c}) + dismissed({d}) + inconclusive({i}) = {c+d+i} != total({total})"
        )


def extract_json_payload(raw_output: str) -> Optional[Dict[str, Any]]:
    """Extract JSON object from stdout, ignoring any leading/trailing CLI banners."""
    if not raw_output or not raw_output.strip():
        return None
    try:
        data = json.loads(raw_output.strip())
        if isinstance(data, dict):
            if "response" in data and isinstance(data["response"], str):
                inner = extract_json_payload(data["response"])
                if inner:
                    return inner
            if "verdict" in data:
                return data
    except json.JSONDecodeError:
        pass

    # Scan with JSONDecoder.raw_decode to accurately parse nested JSON even when CLI banners contain braces
    decoder = json.JSONDecoder()
    fallback_dict: Optional[Dict[str, Any]] = None
    for idx, ch in enumerate(raw_output):
        if ch == "{":
            try:
                cand, _ = decoder.raw_decode(raw_output[idx:])
                if isinstance(cand, dict):
                    if "verdict" in cand:
                        return cand
                    if fallback_dict is None:
                        fallback_dict = cand
            except json.JSONDecodeError:
                continue

    return fallback_dict


async def run_single_validator(
    target: Dict[str, Any],
    timeout_seconds: int = 45,
    workspace_root: Optional[Path] = None,
    mode: str = "adaptive",
) -> Dict[str, Any]:
    """Execute a single validator subagent or adversarial duel."""
    target_id = target.get("id", "unknown")
    file_path = target.get("file_path", target_id)
    hypothesis = target.get("hypothesis", "")
    attack_vector = target.get("attack_vector", "general")

    normalized_file = (
        Path(file_path).as_posix()
        if not os.path.isabs(file_path)
        else Path(file_path).as_posix()
    )

    full_path = (workspace_root / file_path) if workspace_root and not os.path.isabs(file_path) else Path(file_path)

    if not full_path.exists():
        return {
            "target_id": target_id,
            "verdict": "INCONCLUSIVE",
            "reasoning": f"Target file does not exist: {normalized_file}",
            "poc_type": "none",
            "poc_script": None,
            "remediation_hint": None,
        }

    target_cwd = workspace_root if workspace_root else Path.cwd()

    if mode == "duel":
        try:
            try:
                from scripts.lib.worktree_pool import GitWorktreePool
                from scripts.lib.adversarial_team import orchestrate_adversarial_duel
            except ImportError:
                from lib.worktree_pool import GitWorktreePool
                from lib.adversarial_team import orchestrate_adversarial_duel

            pool = GitWorktreePool(target_cwd)
            wt_path = await pool.acquire(mirror_files=[normalized_file])
            try:
                return await orchestrate_adversarial_duel(
                    wt_path=wt_path,
                    target=target,
                    timeout_seconds=min(timeout_seconds, 45),
                )
            finally:
                await pool.release(wt_path)
        except Exception as duel_exc:
            return {
                "target_id": target_id,
                "verdict": "INCONCLUSIVE",
                "reasoning": f"Adversarial duel failed: {duel_exc}",
                "validation_blocker": str(duel_exc),
                "validation_plan": "Check git worktree setup and retry.",
                "poc_type": "none",
                "poc_script": None,
                "code_archaeology": {
                    "legacy_function": None,
                    "design_intent": None,
                    "regression_risk": None,
                },
                "remediation_hint": None,
                "worktree_verified": False,
                "mode": "duel_worktree",
            }

    code_snippet = ""
    try:
        if target.get("code_snippet"):
            code_snippet = str(target["code_snippet"])[:60000]
        elif target.get("start_line") and target.get("end_line"):
            lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
            s_line = max(0, int(target["start_line"]) - 1)
            e_line = min(len(lines), int(target["end_line"]))
            code_snippet = "\n".join(lines[s_line:e_line])
        else:
            code_snippet = full_path.read_text(encoding="utf-8", errors="replace")[:60000]
    except Exception as e:
        code_snippet = f"# Error reading file: {e}"

    target_cwd = workspace_root if workspace_root else Path.cwd()
    historical_intents = load_historical_design_intents(target_cwd, normalized_file)

    prompt = (
        f"{VALIDATOR_SYSTEM_PROMPT}\n\n"
        f"--- TARGET METADATA ---\n"
        f"Target ID: {target_id}\n"
        f"File: {normalized_file}\n"
        f"Audit Category: {attack_vector}\n"
        f"Quality Check: {hypothesis}\n\n"
        f"{historical_intents}"
        f"--- CODE TO REVIEW (DO NOT USE TOOLS, REVIEW TEXT DIRECTLY) ---\n"
        f"```\n{code_snippet}\n```\n\n"
        f"Analyze the code above and return ONLY the JSON result object."
    )

    use_stdin = len(prompt) > 24000
    cli_prompt = (
        "Read the target metadata and code snippet from standard input (stdin) and return ONLY the JSON result object."
        if use_stdin
        else prompt
    )
    stdin_payload = prompt if use_stdin else None

    # Pass prompt via -p flag with --sandbox, --disable-slash-commands and json output format
    cmd = [
        "agy.exe",
        "--sandbox",
        "--disable-slash-commands",
        "--print-timeout",
        f"{timeout_seconds}s",
        "--output-format",
        "json",
        f"-p={cli_prompt}",
    ]

    try:
        if run_streaming_process:
            res = await run_streaming_process(
                cmd=cmd,
                payload=stdin_payload,
                timeout_seconds=float(timeout_seconds + 5),
                cwd=target_cwd,
            )
            raw_stdout = res.stdout
            if res.timed_out:
                return {
                    "target_id": target_id,
                    "verdict": "INCONCLUSIVE",
                    "reasoning": f"Validation timed out after {timeout_seconds}s.",
                    "validation_blocker": f"Process execution exceeded timeout threshold ({timeout_seconds}s).",
                    "validation_plan": "Rerun with higher --timeout or verify in worktree sandbox directly.",
                    "poc_type": "none",
                    "poc_script": None,
                    "code_archaeology": {
                        "legacy_function": None,
                        "design_intent": None,
                        "regression_risk": None,
                    },
                    "remediation_hint": None,
                }
        else:
            # Inline fallback if safe_subprocess module cannot be imported
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE if stdin_payload is not None else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(target_cwd),
            )
            stdout_bytes, _ = await asyncio.wait_for(
                proc.communicate(input=stdin_payload.encode("utf-8") if stdin_payload is not None else None),
                timeout=float(timeout_seconds + 5),
            )
            raw_stdout = stdout_bytes.decode("utf-8", errors="replace")

        parsed = extract_json_payload(raw_stdout)
        if parsed and isinstance(parsed, dict) and "verdict" in parsed:
            parsed["target_id"] = target_id
            if "validation_blocker" not in parsed:
                parsed["validation_blocker"] = None
            if "validation_plan" not in parsed:
                parsed["validation_plan"] = None
            if "code_archaeology" not in parsed or not isinstance(parsed["code_archaeology"], dict):
                parsed["code_archaeology"] = {
                    "legacy_function": None,
                    "design_intent": None,
                    "regression_risk": None,
                }
            needs_worktree = (
                mode != "fast"
                and (
                    str(target.get("severity", "")).lower() in ("high", "critical")
                    or bool(target.get("escalate_teamwork"))
                )
            )
            if needs_worktree and parsed.get("verdict") == "CONFIRMED":
                try:
                    try:
                        from scripts.lib.worktree_pool import GitWorktreePool
                        from scripts.lib.adversarial_team import verify_candidate_in_worktree
                    except ImportError:
                        from lib.worktree_pool import GitWorktreePool
                        from lib.adversarial_team import verify_candidate_in_worktree

                    pool = GitWorktreePool(target_cwd)
                    wt_path = await pool.acquire(mirror_files=[normalized_file])
                    try:
                        parsed = await verify_candidate_in_worktree(
                            wt_path=wt_path,
                            target=target,
                            candidate_result=parsed,
                            timeout_seconds=min(timeout_seconds, 30),
                        )
                    finally:
                        await pool.release(wt_path)
                except ImportError as imp_exc:
                    parsed["worktree_verified"] = False
                    parsed["worktree_skipped_reason"] = f"worktree_pool_not_available: {imp_exc}"
                except Exception as wt_exc:
                    parsed["verdict"] = "INCONCLUSIVE"
                    parsed["worktree_verified"] = False
                    parsed["worktree_error"] = str(wt_exc)
            return parsed

        return {
            "target_id": target_id,
            "verdict": "INCONCLUSIVE",
            "reasoning": f"Validator subagent did not produce a structured verdict. Raw output: {raw_stdout[:250]}",
            "validation_blocker": "Validator subagent did not output valid JSON verdict structure.",
            "validation_plan": "Inspect raw stdout and retry validation.",
            "poc_type": "none",
            "poc_script": None,
            "code_archaeology": {
                "legacy_function": None,
                "design_intent": None,
                "regression_risk": None,
            },
            "remediation_hint": None,
        }
    except asyncio.TimeoutError:
        return {
            "target_id": target_id,
            "verdict": "INCONCLUSIVE",
            "reasoning": f"Validation timed out after {timeout_seconds}s.",
            "validation_blocker": f"TimeoutError occurred after {timeout_seconds}s.",
            "validation_plan": "Increase timeout and re-execute.",
            "poc_type": "none",
            "poc_script": None,
            "code_archaeology": {
                "legacy_function": None,
                "design_intent": None,
                "regression_risk": None,
            },
            "remediation_hint": None,
        }
    except Exception as exc:
        return {
            "target_id": target_id,
            "verdict": "INCONCLUSIVE",
            "reasoning": f"Subagent execution failed: {str(exc)}",
            "validation_blocker": f"Exception raised: {str(exc)}",
            "validation_plan": "Check environment and dependencies.",
            "poc_type": "none",
            "poc_script": None,
            "code_archaeology": {
                "legacy_function": None,
                "design_intent": None,
                "regression_risk": None,
            },
            "remediation_hint": None,
        }


MAX_CONCURRENT_VALIDATORS = 4


async def run_parallel_validators(
    candidates: List[Dict[str, Any]],
    timeout_seconds: int = 45,
    workspace_root: Optional[Path] = None,
    max_concurrency: int = MAX_CONCURRENT_VALIDATORS,
    mode: str = "adaptive",
) -> List[Dict[str, Any]]:
    """Run validators in parallel with bounded Semaphore concurrency."""
    sem = asyncio.Semaphore(max(1, max_concurrency))

    async def _bounded_validate(cand: Dict[str, Any]) -> Dict[str, Any]:
        async with sem:
            return await run_single_validator(
                cand, timeout_seconds=timeout_seconds, workspace_root=workspace_root, mode=mode
            )

    tasks = [_bounded_validate(cand) for cand in candidates]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return results


def main():
    parser = argparse.ArgumentParser(description="Security Sentinel Runner")
    parser.add_argument("--candidates", type=str, help="Path to JSON file containing candidate hypotheses")
    parser.add_argument("--target-file", type=str, help="Single target file path to audit")
    parser.add_argument("--hypothesis", type=str, help="Hypothesis for single target audit")
    parser.add_argument("--vector", type=str, default="logic_boundary", help="Audit category")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["adaptive", "duel", "fast"],
        default="adaptive",
        help="Validation mode: 'adaptive' (worktree for high/critical), 'duel' (mandatory red-vs-blue duel in worktree), 'fast' (in-memory static only)",
    )
    parser.add_argument("--output", type=str, default=None, help="Path to write findings JSON output")
    parser.add_argument("--timeout", type=int, default=45, help="Per-agent timeout in seconds")
    args = parser.parse_args()

    workspace_root = _REPO_ROOT

    if args.candidates:
        assert_security_path_hygiene(args.candidates, "--candidates", repo_root=workspace_root)
    if args.output:
        assert_security_path_hygiene(args.output, "--output", repo_root=workspace_root)

    candidates = []
    if args.candidates:
        cand_path = Path(args.candidates)
        if not cand_path.is_absolute():
            cand_path = (workspace_root / cand_path).resolve()
        if cand_path.exists():
            with open(cand_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                candidates = loaded if isinstance(loaded, list) else loaded.get("candidates", [])
        else:
            print(f"Candidates file not found: {args.candidates}", file=sys.stderr)
            sys.exit(1)
    elif args.target_file and args.hypothesis:
        candidates = [
            {
                "id": args.target_file,
                "file_path": args.target_file,
                "attack_vector": args.vector,
                "hypothesis": args.hypothesis,
            }
        ]
    else:
        print("Error: Must provide either --candidates or (--target-file and --hypothesis)", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Security Sentinel Harness: launching {len(candidates)} validator(s) in parallel (mode: {args.mode})...", file=sys.stderr)
    results = asyncio.run(
        run_parallel_validators(
            candidates, timeout_seconds=args.timeout, workspace_root=workspace_root, mode=args.mode
        )
    )

    output_data = {
        "audit_version": "2.4.0",
        "mode": args.mode,
        "total_validated": len(results),
        "confirmed_count": sum(1 for r in results if r.get("verdict") == "CONFIRMED"),
        "dismissed_count": sum(1 for r in results if r.get("verdict") == "DISMISSED"),
        "inconclusive_count": sum(1 for r in results if r.get("verdict") == "INCONCLUSIVE"),
        "findings": results,
    }

    # Harness^2 Deterministic Identity Assertion
    assert_findings_conservation(output_data)

    if args.output:
        out_path = Path(args.output)
        if not out_path.is_absolute():
            out_path = (workspace_root / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"[+] Findings written to {out_path}", file=sys.stderr)

    try:
        print(json.dumps(output_data, indent=2, ensure_ascii=False))
    except UnicodeEncodeError:
        print(json.dumps(output_data, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
