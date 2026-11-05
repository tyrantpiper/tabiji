"""
Unit Tests for SPEC-AGY-002 Attacker vs Defender Duel Orchestrator (test_sentinel_duel_orchestrator.py)
Validates the integrated 4-phase Red-vs-Blue confrontation protocol with Mantis Block G Benign Control.
"""

import sys
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.lib.safe_subprocess import ProcessResult
from scripts.lib.adversarial_team import (
    DEFAULT_CODE_ARCHAEOLOGY,
    classify_pytest_outcome,
    normalize_code_archaeology,
    _split_poc_test_names,
    orchestrate_adversarial_duel,
)


def test_split_poc_test_names():
    poc_code = """
def test_exploit_injection():
    assert False

def test_benign_control_valid_input():
    assert True
"""
    exploit, benign = _split_poc_test_names(poc_code)
    assert exploit == ["test_exploit_injection"]
    assert benign == ["test_benign_control_valid_input"]


@pytest.mark.asyncio
async def test_duel_attacker_dismissed_early(tmp_path: Path):
    """Phase 1: 若紅軍判定防禦已具備 (DISMISSED)，對抗立即終止，不浪費 Worktree 資源"""
    attacker_subagent = AsyncMock(return_value={
        "target_id": "test_target",
        "verdict": "DISMISSED",
        "reasoning": "Existing regex already filters invisible characters.",
        "poc_script": None,
    })

    result = await orchestrate_adversarial_duel(
        wt_path=tmp_path,
        target={"id": "test_target", "file_path": "backend/sample.py"},
        attacker_fn=attacker_subagent,
    )

    assert result["verdict"] == "DISMISSED"
    assert "Existing regex already filters" in result["reasoning"]
    assert result["worktree_verified"] is False


@pytest.mark.asyncio
async def test_duel_poc_fails_to_break_defense(tmp_path: Path):
    """Phase 2: 紅軍產出 PoC，但在 Worktree 內運行 exit code 為 0 (未擊穿)，判定 DISMISSED"""
    attacker_subagent = AsyncMock(return_value={
        "target_id": "test_target",
        "verdict": "CONFIRMED",
        "reasoning": "Hypothesized bypass.",
        "poc_script": "def test_exploit(): assert True",
    })

    with patch("scripts.lib.adversarial_team.execute_worktree_pytest") as mock_exec:
        # Exit code 0 means defense held!
        mock_exec.return_value = ProcessResult(returncode=0, stdout="passed", stderr="")

        result = await orchestrate_adversarial_duel(
            wt_path=tmp_path,
            target={"id": "test_target", "file_path": "backend/sample.py"},
            attacker_fn=attacker_subagent,
        )

        assert result["verdict"] == "DISMISSED"
        assert "defense already holds" in result["reasoning"].lower()


@pytest.mark.asyncio
async def test_duel_defender_archaeology_dismissal(tmp_path: Path):
    """Phase 3: 紅軍 PoC 造成 exit code 1 (紅燈)，但藍軍提出切斯特頓三問舉證為刻意設計，判定 DISMISSED"""
    attacker_subagent = AsyncMock(return_value={
        "target_id": "test_target",
        "verdict": "CONFIRMED",
        "poc_script": "def test_exploit(): assert False\ndef test_benign(): assert True",
    })

    defender_subagent = AsyncMock(return_value={
        "target_id": "test_target",
        "verdict": "DISMISSED",
        "reasoning": "This is intentional SSOT split calculation to avoid DB desync.",
        "code_archaeology": {
            "legacy_function": "Optimistic in-memory sort ordering.",
            "design_intent": "Eliminates premature DB race conditions.",
            "regression_risk": "Removing this causes card bounce-back glitch.",
        }
    })

    with patch("scripts.lib.adversarial_team.execute_worktree_pytest") as mock_exec:
        # First execution (Red exploit check): returncode 1 (exploit triggered)
        # Second execution (Benign check): returncode 0 (benign passes)
        mock_exec.side_effect = [
            ProcessResult(returncode=1, stdout="AssertionError", stderr=""),
            ProcessResult(returncode=0, stdout="passed", stderr=""),
        ]

        result = await orchestrate_adversarial_duel(
            wt_path=tmp_path,
            target={"id": "test_target", "file_path": "backend/sample.py"},
            attacker_fn=attacker_subagent,
            defender_fn=defender_subagent,
        )

        assert result["verdict"] == "DISMISSED"
        assert result["code_archaeology"]["design_intent"] == "Eliminates premature DB race conditions."


@pytest.mark.asyncio
async def test_duel_full_red_to_green_confirmed(tmp_path: Path):
    """Phase 4: 紅軍擊穿 (exit 1) -> 藍軍確認為真漏洞 -> 套用補丁後實體綠燈 (exit 0) -> 判定 CONFIRMED"""
    target_file = tmp_path / "backend" / "sample.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("def sanitize(x): return x", encoding="utf-8")

    attacker_subagent = AsyncMock(return_value={
        "target_id": "test_target",
        "verdict": "CONFIRMED",
        "poc_script": "def test_exploit(): assert False\ndef test_benign(): assert True",
        "block_replacement": {
            "target_content": "def sanitize(x): return x",
            "replacement_content": "def sanitize(x): return x.strip()"
        }
    })

    defender_subagent = AsyncMock(return_value={
        "target_id": "test_target",
        "verdict": "CONFIRMED",
        "reasoning": "No existing guard covers whitespace injection.",
        "code_archaeology": {
            "legacy_function": "Input sanitizer.",
            "design_intent": "Raw string passthrough.",
            "regression_risk": "None.",
        }
    })

    with patch("scripts.lib.adversarial_team.execute_worktree_pytest") as mock_exec:
        mock_exec.side_effect = [
            # 1. Red check: exploit fails (1)
            ProcessResult(returncode=1, stdout="AssertionError", stderr=""),
            # 2. Benign baseline: benign passes (0)
            ProcessResult(returncode=0, stdout="passed", stderr=""),
            # 3. Green check post-patch: both exploit and benign pass (0)
            ProcessResult(returncode=0, stdout="2 passed", stderr=""),
        ]

        result = await orchestrate_adversarial_duel(
            wt_path=tmp_path,
            target={"id": "test_target", "file_path": "backend/sample.py"},
            attacker_fn=attacker_subagent,
            defender_fn=defender_subagent,
        )

        assert result["verdict"] == "CONFIRMED"
        assert result["patch_test_passed"] is True
        assert result["benign_control_passed"] is True
        assert result["mode"] == "duel_worktree"


@pytest.mark.asyncio
async def test_runner_mode_duel_dispatches_orchestrator(tmp_path: Path):
    """驗證 runner.py 在 mode='duel' 時會自動調度 orchestrate_adversarial_duel"""
    from importlib.machinery import SourceFileLoader
    runner_path = _REPO_ROOT / ".agents" / "skills" / "security-sentinel" / "scripts" / "runner.py"
    runner_mod = SourceFileLoader("runner_mod", str(runner_path)).load_module()

    target_file = tmp_path / "backend" / "test_target.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("def test(): pass\n", encoding="utf-8")

    duel_return = {
        "target_id": "test_target",
        "verdict": "CONFIRMED",
        "reasoning": "Confirmed via duel mock.",
        "poc_type": "pytest_in_memory",
        "poc_script": "def test(): assert False",
        "code_archaeology": {"legacy_function": None, "design_intent": None, "regression_risk": None},
        "mode": "duel_worktree",
    }

    with patch("scripts.lib.worktree_pool.GitWorktreePool.acquire", new_callable=AsyncMock) as mock_acq, \
         patch("scripts.lib.worktree_pool.GitWorktreePool.release", new_callable=AsyncMock) as mock_rel, \
         patch("scripts.lib.adversarial_team.orchestrate_adversarial_duel", new_callable=AsyncMock) as mock_duel:

        mock_acq.return_value = tmp_path
        mock_duel.return_value = duel_return

        res = await runner_mod.run_single_validator(
            target={"id": "test_target", "file_path": "backend/test_target.py"},
            workspace_root=tmp_path,
            mode="duel",
        )

        assert res["verdict"] == "CONFIRMED"
        assert res["mode"] == "duel_worktree"
        mock_acq.assert_awaited_once()
        mock_duel.assert_awaited_once()
        mock_rel.assert_awaited_once_with(tmp_path)


@pytest.mark.asyncio
async def test_runner_mode_fast_skips_worktree(tmp_path: Path):
    """驗證 runner.py 在 mode='fast' 時跳過 worktree 驗證，直接依賴靜態檢查"""
    from importlib.machinery import SourceFileLoader
    runner_path = _REPO_ROOT / ".agents" / "skills" / "security-sentinel" / "scripts" / "runner.py"
    runner_mod = SourceFileLoader("runner_mod", str(runner_path)).load_module()

    target_file = tmp_path / "backend" / "test_target.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("def test(): pass\n", encoding="utf-8")

    with patch("scripts.lib.worktree_pool.GitWorktreePool.acquire", new_callable=AsyncMock) as mock_acq, \
         patch.object(runner_mod, "run_streaming_process", new_callable=AsyncMock) as mock_stream:

        # Mock static check returning CONFIRMED
        mock_stream.return_value = ProcessResult(
            returncode=0,
            stdout='{"target_id": "test_target", "verdict": "CONFIRMED", "reasoning": "Static find"}',
            stderr="",
        )

        res = await runner_mod.run_single_validator(
            target={"id": "test_target", "file_path": "backend/test_target.py", "severity": "critical"},
            workspace_root=tmp_path,
            mode="fast",
        )

        assert res["verdict"] == "CONFIRMED"
        # Even with severity=critical, mode="fast" must NOT acquire worktree
        mock_acq.assert_not_called()
