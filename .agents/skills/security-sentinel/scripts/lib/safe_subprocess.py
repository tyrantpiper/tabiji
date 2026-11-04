#!/usr/bin/env python3
"""
Single Source of Truth Re-export for Safe Subprocess IPC (scripts.lib.safe_subprocess)
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.lib.safe_subprocess import ProcessResult, run_streaming_process

__all__ = ["ProcessResult", "run_streaming_process"]

