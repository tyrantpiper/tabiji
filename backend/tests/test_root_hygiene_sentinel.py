"""
Security Sentinel In-Memory Validator PoC:
Verifies Root Hygiene and Guardrails for runner.py and push.md
"""

import os
import sys
import pytest
from pathlib import Path

# Resolve repository root
REPO_ROOT = Path(__file__).resolve().parents[2]


def assert_security_path_hygiene(file_path: str, param_name: str, repo_root: Path = REPO_ROOT) -> None:
    """
    🛡️ 根目錄衛生強制防呆：禁止任何中繼檔案落在專案根目錄
    """
    if not file_path:
        return
    resolved_path = Path(file_path).resolve()
    norm_parent = os.path.normcase(str(resolved_path.parent))
    norm_root = os.path.normcase(str(repo_root))

    if norm_parent == norm_root:
        sys.stderr.write(
            f"\n🚨 [Root Hygiene Violation] 參數 '{param_name}' 路徑 ({file_path}) 嚴禁直接置於專案根目錄！\n"
            f"👉 請依規範存放於 docs/security/ 目錄（例如: docs/security/candidates_<topic>_<date>.json）。\n\n"
        )
        sys.exit(1)


def test_runner_blocks_bare_filename_in_root():
    """TC-1: Bare filename resolving to repo root must trigger sys.exit(1)."""
    with pytest.raises(SystemExit) as exc_info:
        assert_security_path_hygiene("candidates.json", "--candidates", REPO_ROOT)
    assert exc_info.value.code == 1


def test_runner_blocks_absolute_root_path():
    """TC-2: Absolute path resolving to repo root must trigger sys.exit(1)."""
    root_file = str(REPO_ROOT / "findings.json")
    with pytest.raises(SystemExit) as exc_info:
        assert_security_path_hygiene(root_file, "--output", REPO_ROOT)
    assert exc_info.value.code == 1


def test_runner_normalizes_drive_casing():
    """TC-3: Drive letter casing differences on Windows must be normalized and caught."""
    root_str = str(REPO_ROOT / "test_artifact.json")
    # Invert first letter (e.g. D: -> d: or d: -> D:)
    if len(root_str) > 1 and root_str[1] == ":":
        inverted_root_str = (root_str[0].lower() if root_str[0].isupper() else root_str[0].upper()) + root_str[1:]
    else:
        inverted_root_str = root_str

    with pytest.raises(SystemExit) as exc_info:
        assert_security_path_hygiene(inverted_root_str, "--candidates", REPO_ROOT)
    assert exc_info.value.code == 1


def test_runner_allows_valid_subdirectories():
    """TC-4: Legitimate subdirectories like docs/security/ must pass without exit."""
    valid_path = str(REPO_ROOT / "docs" / "security" / "candidates_valid.json")
    # Must not raise
    assert_security_path_hygiene(valid_path, "--candidates", REPO_ROOT)
    assert_security_path_hygiene(str(REPO_ROOT / "docs" / "security" / "findings.json"), "--output", REPO_ROOT)


def test_push_gate_whitelist_filtering():
    """TC-5: Emulates PowerShell Root Hygiene Gate logic to ensure whitelist accuracy."""
    whitelist = {
        "package.json", "package-lock.json", "tsconfig.json",
        "components.json", "NOTICE.md", "README.md", "next.config.ts"
    }

    test_files = [
        ("candidates.json", True),     # Offender
        ("patch_candidate.diff", True),# Offender
        ("temp.tmp", True),            # Offender
        ("error.log", True),           # Offender
        ("package.json", False),       # Whitelisted
        ("tsconfig.json", False),      # Whitelisted
        ("components.json", False),    # Whitelisted
        ("README.md", False),          # Whitelisted
    ]

    for fname, is_offender in test_files:
        ext = os.path.splitext(fname)[1].lower()
        flagged = (ext in [".diff", ".tmp", ".bak", ".log"]) or (ext == ".json" and fname not in whitelist)
        assert flagged == is_offender, f"File {fname} expected offender={is_offender}, got {flagged}"
