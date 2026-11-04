"""
Scripts library package (workspace local re-export).
"""
from .safe_subprocess import ProcessResult, run_streaming_process
from .worktree_pool import GitWorktreePool
from .adversarial_team import (
    DEFAULT_CODE_ARCHAEOLOGY,
    TEAMWORK_ATTACKER_PROMPT,
    TEAMWORK_DEFENDER_PROMPT,
    apply_block_replacement_in_worktree,
    classify_pytest_outcome,
    execute_worktree_pytest,
    normalize_code_archaeology,
    verify_candidate_in_worktree,
)

__all__ = [
    "ProcessResult",
    "run_streaming_process",
    "GitWorktreePool",
    "DEFAULT_CODE_ARCHAEOLOGY",
    "normalize_code_archaeology",
    "TEAMWORK_ATTACKER_PROMPT",
    "TEAMWORK_DEFENDER_PROMPT",
    "classify_pytest_outcome",
    "execute_worktree_pytest",
    "apply_block_replacement_in_worktree",
    "verify_candidate_in_worktree",
]
