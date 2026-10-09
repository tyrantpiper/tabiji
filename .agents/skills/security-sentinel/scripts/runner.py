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
_REPO_ROOT = _SCRIPT_DIR.parents[3]  # .agents/skills/security-sentinel/scripts -> repo root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from scripts.lib.safe_subprocess import run_streaming_process
except ImportError:
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
            code_snippet = full_path.read_text(encoding="utf-8", errors="replace")[:60000]
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

    # Bypass Windows CreateProcessW 32,767 limit (WinError 206) via stdin streaming
    cmd = [
        "agy.exe",
        "--print-timeout",
        f"{timeout_seconds}s",
        "--output-format",
        "json",
    ]

    target_cwd = workspace_root if workspace_root else Path.cwd()
    try:
        if run_streaming_process:
            res = await run_streaming_process(
                cmd=cmd,
                payload=prompt,
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

    workspace_root = Path(__file__).resolve().parents[4]

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
