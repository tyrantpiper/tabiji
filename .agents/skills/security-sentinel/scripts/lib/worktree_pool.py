#!/usr/bin/env python3
"""
Single Source of Truth Re-export for GitWorktreePool (scripts.lib.worktree_pool)
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.lib.worktree_pool import GitWorktreePool, _GIT_WORKTREE_LOCK

__all__ = ["GitWorktreePool", "_GIT_WORKTREE_LOCK"]
