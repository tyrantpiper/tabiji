"""
Subprocess IPC Large-Payload Safety Unit Tests (test_safe_subprocess.py)
Validates:
1. TC-1: 70KB payload streaming via stdin (bypassing CreateProcessW 32,767 limit / WinError 206)
2. TC-2: Bidirectional 130KB buffer stress test (zero deadlock guarantee)
3. TC-3: BrokenPipeError resilience when child terminates prematurely
4. TC-4: CJK, Unicode, Quotations and Emoji UTF-8 lossless transmission
5. TC-5: Timeout handling and process tree teardown
6. TC-6: File-based fallback with WinError 32 sharing violation defense
"""

import sys
from pathlib import Path
from typing import List
import pytest

# Ensure project root is in sys.path across arbitrary test runners
_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.lib.safe_subprocess import (
    ProcessResult,
    run_file_fallback,
    run_streaming_process,
)


@pytest.mark.asyncio
async def test_streaming_process_70kb_payload_bypasses_winerror_206():
    """TC-1: Verify 70,000 characters payload stream works without WinError 206."""
    huge_data = "A" * 70000
    py_code = "import sys; data = sys.stdin.read(); print(f'LEN:{len(data)}')"
    cmd = [sys.executable, "-c", py_code]

    res = await run_streaming_process(cmd=cmd, payload=huge_data, timeout_seconds=10.0)
    assert res.returncode == 0
    assert not res.timed_out
    assert "LEN:70000" in res.stdout.strip()


@pytest.mark.asyncio
async def test_streaming_process_bidirectional_130kb_buffer_deadlock_free():
    """TC-2: Both parent and child transfer >65KB simultaneously. Must not deadlock."""
    huge_data = "B" * 65536
    # Child reads 64KB stdin and writes 64KB stdout and 100 bytes stderr
    py_code = (
        "import sys\n"
        "input_len = len(sys.stdin.read())\n"
        "sys.stdout.write('C' * 65536)\n"
        "sys.stderr.write(f'STDIN_READ:{input_len}')\n"
    )
    cmd = [sys.executable, "-c", py_code]

    res = await run_streaming_process(cmd=cmd, payload=huge_data, timeout_seconds=10.0)
    assert res.returncode == 0
    assert not res.timed_out
    assert len(res.stdout) == 65536
    assert "STDIN_READ:65536" in res.stderr


@pytest.mark.asyncio
async def test_streaming_process_broken_pipe_resilience():
    """TC-3: Child exits immediately without reading stdin. Must handle BrokenPipeError gracefully."""
    huge_data = "X" * 70000
    # Child exits with code 42 immediately
    py_code = "import sys; sys.exit(42)"
    cmd = [sys.executable, "-c", py_code]

    res = await run_streaming_process(cmd=cmd, payload=huge_data, timeout_seconds=5.0)
    assert res.returncode == 42
    assert not res.timed_out


@pytest.mark.asyncio
async def test_streaming_process_cjk_emoji_quote_lossless():
    """TC-4: Verify CJK, Japanese, Quotations and Emoji UTF-8 roundtrip integrity."""
    complex_text = (
        "【測試開始】\n"
        "繁體中文：行程時間軸與備忘錄\n"
        "日本語：とうきょうと 新宿・渋谷 散策\n"
        "引號與轉義：\"quoted\" 'single' \\backslash /slash \n"
        "Emoji 符號：📱 🗺️ 🚀 ☁️ ✈️ 🏨\n"
        "【測試結束】"
    )
    py_code = "import sys; sys.stdout.write(sys.stdin.read())"
    cmd = [sys.executable, "-c", py_code]

    res = await run_streaming_process(cmd=cmd, payload=complex_text, timeout_seconds=5.0)
    assert res.returncode == 0
    assert not res.timed_out
    # Windows TextIOWrapper on child stdout translates \n to \r\n by default.
    # Verify content roundtrip integrity with universal newlines.
    assert res.stdout.replace("\r\n", "\n") == complex_text.replace("\r\n", "\n")


@pytest.mark.asyncio
async def test_streaming_process_timeout_and_teardown():
    """TC-5: Verify timeout triggers ProcessResult.timed_out and terminates process."""
    py_code = "import time; time.sleep(10)"
    cmd = [sys.executable, "-c", py_code]

    res = await run_streaming_process(cmd=cmd, payload=None, timeout_seconds=0.5)
    assert res.timed_out is True
    assert res.returncode == -1
    assert "timed out" in res.stderr


@pytest.mark.asyncio
async def test_file_fallback_safe_cleanup_no_winerror_32():
    """TC-6: Verify temp file fallback works and temp file is safely unlinked without sharing violation."""
    sample_text = "TEMPORARY_PAYLOAD_CONTENT_FOR_FALLBACK"
    captured_temp_path = None

    def make_cmd(temp_path: Path) -> List[str]:
        nonlocal captured_temp_path
        captured_temp_path = temp_path
        # Child reads the file and prints its length
        py_code = f"from pathlib import Path; print('FILE_LEN:' + str(len(Path(r'{temp_path}').read_text(encoding='utf-8'))))"
        return [sys.executable, "-c", py_code]

    res = await run_file_fallback(cmd_factory=make_cmd, payload=sample_text, timeout_seconds=5.0)
    assert res.returncode == 0
    assert not res.timed_out
    assert f"FILE_LEN:{len(sample_text)}" in res.stdout
    assert captured_temp_path is not None
    # Verify file is deleted cleanly
    assert not captured_temp_path.exists()
