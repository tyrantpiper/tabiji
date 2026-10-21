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

# Self-resolving sys.path to locate scripts.lib.safe_subprocess across arbitrary CWDs
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = Path(__file__).resolve().parents[4]  # .agents/skills/security-sentinel/scripts/runner.py -> repo root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


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

Output MUST be strictly valid JSON matching this schema:
{
  "target_id": "<target_id>",
  "verdict": "CONFIRMED" | "DISMISSED" | "INCONCLUSIVE",
  "reasoning": "<concise technical explanation of why the code is safe or why it has an unhandled flaw>",
  "poc_type": "pytest_in_memory" | "unit_test" | "none",
  "poc_script": "<python pytest test code or null>",
  "remediation_hint": "<suggested code modification or null>"
}
"""


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

    # Regex search for the outermost {...} containing "verdict"
    for match in re.finditer(r"\{[\s\S]*?\}", raw_output):
        try:
            cand = json.loads(match.group(0))
            if isinstance(cand, dict) and "verdict" in cand:
                return cand
        except json.JSONDecodeError:
            continue

    # Broader regex fallback
    match = re.search(r"\{[\s\S]*\}", raw_output)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


async def run_single_validator(
    target: Dict[str, Any],
    timeout_seconds: int = 45,
    workspace_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute a single agy.exe subagent with embedded code snippet."""
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

    code_snippet = ""
    try:
        if target.get("code_snippet"):
            code_snippet = target["code_snippet"]
        elif target.get("start_line") and target.get("end_line"):
            lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
            s_line = max(0, int(target["start_line"]) - 1)
            e_line = min(len(lines), int(target["end_line"]))
            code_snippet = "\n".join(lines[s_line:e_line])
        else:
            code_snippet = full_path.read_text(encoding="utf-8", errors="replace")[:6000]
    except Exception as e:
        code_snippet = f"# Error reading file: {e}"

    prompt = (
        f"{VALIDATOR_SYSTEM_PROMPT}\n\n"
        f"--- TARGET METADATA ---\n"
        f"Target ID: {target_id}\n"
        f"File: {normalized_file}\n"
        f"Audit Category: {attack_vector}\n"
        f"Quality Check: {hypothesis}\n\n"
        f"--- CODE TO REVIEW (DO NOT USE TOOLS, REVIEW TEXT DIRECTLY) ---\n"
        f"```\n{code_snippet}\n```\n\n"
        f"Analyze the code above and return ONLY the JSON result object."
    )

    # Pass prompt via -p flag with --sandbox and json output format
    cmd = [
        "agy.exe",
        "--sandbox",
        "--print-timeout",
        f"{timeout_seconds}s",
        "--output-format",
        "json",
        f"-p={prompt}",
    ]

    target_cwd = workspace_root if workspace_root else Path.cwd()
    try:
        if run_streaming_process:
            res = await run_streaming_process(
                cmd=cmd,
                payload=None,
                timeout_seconds=float(timeout_seconds + 5),
                cwd=target_cwd,
            )
            raw_stdout = res.stdout
            if res.timed_out:
                return {
                    "target_id": target_id,
                    "verdict": "INCONCLUSIVE",
                    "reasoning": f"Validation timed out after {timeout_seconds}s.",
                    "poc_type": "none",
                    "poc_script": None,
                    "remediation_hint": None,
                }
        else:
            # Inline fallback if safe_subprocess module cannot be imported
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(target_cwd),
            )
            stdout_bytes, _ = await asyncio.wait_for(
                proc.communicate(input=prompt.encode("utf-8")),
                timeout=float(timeout_seconds + 5),
            )
            raw_stdout = stdout_bytes.decode("utf-8", errors="replace")

        parsed = extract_json_payload(raw_stdout)
        if parsed and isinstance(parsed, dict) and "verdict" in parsed:
            parsed["target_id"] = target_id
            return parsed

        return {
            "target_id": target_id,
            "verdict": "INCONCLUSIVE",
            "reasoning": f"Validator subagent did not produce a structured verdict. Raw output: {raw_stdout[:250]}",
            "poc_type": "none",
            "poc_script": None,
            "remediation_hint": None,
        }
    except asyncio.TimeoutError:
        return {
            "target_id": target_id,
            "verdict": "INCONCLUSIVE",
            "reasoning": f"Validation timed out after {timeout_seconds}s.",
            "poc_type": "none",
            "poc_script": None,
            "remediation_hint": None,
        }
    except Exception as exc:
        return {
            "target_id": target_id,
            "verdict": "INCONCLUSIVE",
            "reasoning": f"Subagent execution failed: {str(exc)}",
            "poc_type": "none",
            "poc_script": None,
            "remediation_hint": None,
        }


async def run_parallel_validators(
    candidates: List[Dict[str, Any]],
    timeout_seconds: int = 45,
    workspace_root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Run all validators in parallel using unbounded concurrency."""
    tasks = [
        run_single_validator(cand, timeout_seconds, workspace_root)
        for cand in candidates
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return results


def main():
    parser = argparse.ArgumentParser(description="Security Sentinel Runner")
    parser.add_argument("--candidates", type=str, help="Path to JSON file containing candidate hypotheses")
    parser.add_argument("--target-file", type=str, help="Single target file path to audit")
    parser.add_argument("--hypothesis", type=str, help="Hypothesis for single target audit")
    parser.add_argument("--vector", type=str, default="logic_boundary", help="Audit category")
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

    print(f"[*] Security Sentinel Harness: launching {len(candidates)} validator(s) in parallel...", file=sys.stderr)
    results = asyncio.run(
        run_parallel_validators(candidates, timeout_seconds=args.timeout, workspace_root=workspace_root)
    )

    output_data = {
        "audit_version": "2.0.0",
        "total_validated": len(results),
        "confirmed_count": sum(1 for r in results if r.get("verdict") == "CONFIRMED"),
        "dismissed_count": sum(1 for r in results if r.get("verdict") == "DISMISSED"),
        "inconclusive_count": sum(1 for r in results if r.get("verdict") == "INCONCLUSIVE"),
        "findings": results,
    }

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"[+] Findings written to {out_path}", file=sys.stderr)

    print(json.dumps(output_data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
