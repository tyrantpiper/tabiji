#!/usr/bin/env python3
"""
Safe Subprocess IPC Module (safe_subprocess.py)
Cross-platform resilient subprocess runner designed to:
1. Bypass Windows CreateProcessW 32,767 command-line length limits (WinError 206) via stdin streaming.
2. Prevent OS anonymous pipe buffer deadlocks (4KB-64KB) via async communicate().
3. Gracefully handle BrokenPipeError when child processes exit prematurely.
4. Defend against Windows sharing violations (WinError 32) in file-fallback mode.
5. Guarantee tree-wide process teardown on timeout via taskkill on Windows.
"""

import asyncio
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union


@dataclass
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_seconds: float = 0.0


async def run_streaming_process(
    cmd: List[str],
    payload: Optional[str] = None,
    timeout_seconds: float = 60.0,
    cwd: Optional[Union[Path, str]] = None,
    env: Optional[Dict[str, str]] = None,
) -> ProcessResult:
    """
    Execute subprocess with payload streamed via stdin to bypass CLI length constraints.
    """
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    # Enforce UTF-8 to prevent Windows CP950 console encoding crashes
    merged_env["PYTHONIOENCODING"] = "utf-8"
    merged_env["PYTHONUTF8"] = "1"

    proc = None
    timed_out = False
    loop = asyncio.get_running_loop()
    start_time = loop.time()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if payload is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
            env=merged_env,
        )

        input_bytes = payload.encode("utf-8") if payload is not None else None
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(input=input_bytes),
            timeout=timeout_seconds,
        )
        returncode = proc.returncode if proc.returncode is not None else 0

    except BrokenPipeError:
        # Child exited prematurely; safely drain remaining stdout/stderr
        stdout_bytes = b""
        stderr_bytes = b""
        if proc:
            try:
                stdout_bytes, stderr_bytes = await proc.communicate()
            except Exception:
                pass
            returncode = proc.returncode if proc.returncode is not None else 1
        else:
            returncode = 1

    except asyncio.TimeoutError:
        timed_out = True
        stdout_bytes = b""
        stderr_bytes = b"Process timed out"
        returncode = -1
        if proc:
            try:
                proc.kill()
                if sys.platform == "win32":
                    os.system(f"taskkill /F /T /PID {proc.pid} >nul 2>&1")
                await asyncio.sleep(0.1)
                await proc.wait()
            except Exception:
                pass

    duration = loop.time() - start_time
    return ProcessResult(
        returncode=returncode,
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
        timed_out=timed_out,
        duration_seconds=duration,
    )


async def run_file_fallback(
    cmd_factory: Callable[[Path], List[str]],
    payload: str,
    timeout_seconds: float = 60.0,
    cwd: Optional[Union[Path, str]] = None,
    env: Optional[Dict[str, str]] = None,
) -> ProcessResult:
    """
    Fallback mechanism for legacy tools lacking stdin stream support.
    Writes payload to a temporary file, immediately closes the handle to
    prevent Windows WinError 32 sharing violations, and securely unlinks in finally.
    """
    tf = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False)
    temp_path = Path(tf.name)
    try:
        tf.write(payload)
        tf.flush()
        tf.close()

        cmd = cmd_factory(temp_path)
        return await run_streaming_process(
            cmd=cmd,
            payload=None,
            timeout_seconds=timeout_seconds,
            cwd=cwd,
            env=env,
        )
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
