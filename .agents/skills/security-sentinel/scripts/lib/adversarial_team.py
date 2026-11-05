#!/usr/bin/env python3
"""
Single Source of Truth Re-export for Adversarial Team Engine (scripts.lib.adversarial_team)
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.lib.adversarial_team import (
    DEFAULT_CODE_ARCHAEOLOGY,
    TEAMWORK_ATTACKER_PROMPT,
    TEAMWORK_DEFENDER_PROMPT,
    apply_block_replacement_in_worktree,
    classify_pytest_outcome,
    execute_worktree_pytest,
    normalize_code_archaeology,
    verify_candidate_in_worktree,
    orchestrate_adversarial_duel,
    extract_json_payload,
)

__all__ = [
    "DEFAULT_CODE_ARCHAEOLOGY",
    "normalize_code_archaeology",
    "TEAMWORK_ATTACKER_PROMPT",
    "TEAMWORK_DEFENDER_PROMPT",
    "classify_pytest_outcome",
    "execute_worktree_pytest",
    "apply_block_replacement_in_worktree",
    "verify_candidate_in_worktree",
    "orchestrate_adversarial_duel",
    "extract_json_payload",
]
