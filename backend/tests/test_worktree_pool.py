"""
Unit & Integration Tests for SPEC-AGY-002 Worktree Pool & Adversarial Team Engine
"""

import sys
from pathlib import Path
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.lib.safe_subprocess import ProcessResult
from scripts.lib.adversarial_team import (
    classify_pytest_outcome,
    apply_block_replacement_in_worktree,
    verify_candidate_in_worktree,
)
from scripts.lib.worktree_pool import GitWorktreePool


def test_classify_pytest_outcome_strict_exit_codes():
    """驗證僅 returncode == 1 為 RED_CONFIRMED；0 為 GREEN_SAFE；>=2 或超時為 INVALID_POC"""
    assert classify_pytest_outcome(ProcessResult(returncode=0, stdout="", stderr="")) == "GREEN_SAFE"
    assert classify_pytest_outcome(ProcessResult(returncode=1, stdout="AssertionError", stderr="")) == "RED_CONFIRMED"
    # ModuleNotFoundError / UsageError (exit code 4) 絕不可誤判為 RED_CONFIRMED
    assert classify_pytest_outcome(ProcessResult(returncode=4, stdout="", stderr="ImportError")) == "INVALID_POC"
    assert classify_pytest_outcome(ProcessResult(returncode=2, stdout="", stderr="SyntaxError")) == "INVALID_POC"
    assert classify_pytest_outcome(ProcessResult(returncode=-1, stdout="", stderr="Timed out", timed_out=True)) == "INVALID_POC"


def test_apply_block_replacement_in_worktree_crlf_resilient(tmp_path: Path):
    """驗證在 CRLF 換行符環境下仍能精準套用 LF 修復區塊，且阻擋路徑穿越"""
    target_file = tmp_path / "backend" / "sample.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_bytes(b"def check(x):\r\n    return x\r\n")

    ok = apply_block_replacement_in_worktree(
        wt_path=tmp_path,
        rel_file="backend/sample.py",
        target_content="def check(x):\n    return x",
        replacement_content="def check(x):\n    return x.strip()",
    )
    assert ok is True
    assert "return x.strip()" in target_file.read_text(encoding="utf-8")

    # 路徑穿越與 CWE-22 同綴兄弟目錄碰撞防禦測試
    traversal = apply_block_replacement_in_worktree(
        wt_path=tmp_path,
        rel_file="../outside.py",
        target_content="a",
        replacement_content="b",
    )
    assert traversal is False

    wt_sub = tmp_path / "sentinel-1234"
    wt_sibling = tmp_path / "sentinel-1234_evil"
    wt_sub.mkdir(exist_ok=True)
    wt_sibling.mkdir(exist_ok=True)
    evil_file = wt_sibling / "pwn.py"
    evil_file.write_text("old_val", encoding="utf-8")
    sibling_collision = apply_block_replacement_in_worktree(
        wt_path=wt_sub,
        rel_file="../sentinel-1234_evil/pwn.py",
        target_content="old_val",
        replacement_content="hacked",
    )
    assert sibling_collision is False
    assert evil_file.read_text(encoding="utf-8") == "old_val"


@pytest.mark.asyncio
async def test_verify_candidate_red_green_and_disprove_by_default(tmp_path: Path):
    """驗證完整物理先紅後綠閉環與疑罪從無熔斷器"""
    backend_dir = tmp_path / "backend"
    services_dir = backend_dir / "services"
    tests_dir = backend_dir / "tests"
    services_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)

    vuln_file = services_dir / "dummy_sanitizer.py"
    vuln_file.write_text(
        "def clean(msg: str) -> str:\n    return msg.strip()\n",
        encoding="utf-8",
    )

    target_meta = {
        "id": "backend/services/dummy_sanitizer.py",
        "file_path": "backend/services/dummy_sanitizer.py",
        "severity": "high",
    }

    # Case 1: 真實擊穿 (Red: returncode == 1) + 補丁修復 (Green: returncode == 0)
    cand_confirmed = {
        "target_id": target_meta["id"],
        "verdict": "CONFIRMED",
        "reasoning": "Zero-width space not stripped",
        "poc_type": "pytest_in_memory",
        "poc_script": (
            "from services.dummy_sanitizer import clean\n"
            "def test_zwsp():\n"
            "    assert clean('\\u200bhello') == 'hello'\n"
        ),
        "block_replacement": {
            "target_content": "def clean(msg: str) -> str:\n    return msg.strip()",
            "replacement_content": "def clean(msg: str) -> str:\n    return msg.replace('\\u200b', '').strip()",
        },
    }

    verified = await verify_candidate_in_worktree(tmp_path, target_meta, cand_confirmed)
    assert verified["verdict"] == "CONFIRMED"
    assert verified["worktree_verified"] is True
    assert verified["patch_test_passed"] is True

    # Case 2: 語法或匯入錯誤 (Exit code != 1) -> 觸發疑罪從無自動降級為 DISMISSED
    cand_broken_import = {
        "target_id": target_meta["id"],
        "verdict": "CONFIRMED",
        "reasoning": "Broken PoC",
        "poc_type": "pytest_in_memory",
        "poc_script": "import non_existent_module_xyz\ndef test_bad(): assert False\n",
    }
    dismissed = await verify_candidate_in_worktree(tmp_path, target_meta, cand_broken_import)
    assert dismissed["verdict"] == "DISMISSED"
    assert "[Disprove-by-Default Circuit Breaker]" in dismissed["reasoning"]


@pytest.mark.asyncio
async def test_git_worktree_pool_live_acquire_mirror_and_release():
    """驗證真實 GitWorktreePool 建立隔離目錄、鏡像同步 dirty file、執行 pytest 並無痕銷毀"""
    pool = GitWorktreePool(_REPO_ROOT)
    wt_path = await pool.acquire(mirror_files=["backend/services/intent_router.py"])
    try:
        assert wt_path.exists()
        assert (wt_path / "backend" / "services" / "intent_router.py").is_file()
    finally:
        released = await pool.release(wt_path)
    assert released is True
    assert not wt_path.exists()


@pytest.mark.asyncio
async def test_verify_candidate_restores_file_when_green_patch_fails(tmp_path: Path):
    """驗證當候選補丁未能通過 Green Check 時，Worktree 內的原始檔案內容會自動還原不留髒狀態"""
    svc_dir = tmp_path / "backend" / "services"
    svc_dir.mkdir(parents=True)
    target_file = svc_dir / "dummy_restore.py"
    original_code = "def compute():\n    return 'VULNERABLE'\n"
    target_file.write_text(original_code, encoding="utf-8")

    target_meta = {
        "id": "backend/services/dummy_restore.py",
        "file_path": "backend/services/dummy_restore.py",
    }
    cand_bad_patch = {
        "target_id": target_meta["id"],
        "verdict": "CONFIRMED",
        "reasoning": "Flaw proven but patch still fails",
        "poc_type": "pytest_in_memory",
        "poc_script": "from services.dummy_restore import compute\ndef test_poc():\n    assert compute() == 'SAFE'\n",
        "block_replacement": {
            "target_content": "return 'VULNERABLE'",
            "replacement_content": "return 'STILL_BROKEN'",
        },
    }
    res = await verify_candidate_in_worktree(tmp_path, target_meta, cand_bad_patch)
    assert res["verdict"] == "CONFIRMED"
    assert res["patch_test_passed"] is False
    assert target_file.read_text(encoding="utf-8") == original_code


@pytest.mark.asyncio
async def test_worktree_pool_rejects_outside_release_and_poisoned_prune(tmp_path: Path):
    """驗證 release() 與 prune_orphans() 嚴格阻擋 .worktrees/ 外部路徑，防禦 CWE-22 任意目錄刪除"""
    pool = GitWorktreePool(tmp_path)
    outside_dir = tmp_path / "outside_precious"
    outside_dir.mkdir()
    precious_file = outside_dir / "data.txt"
    precious_file.write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError):
        await pool.release(outside_dir)
    assert precious_file.exists()

    pool.pool_dir.mkdir(parents=True, exist_ok=True)
    pool.pending_prune_file.write_text(f"{outside_dir.resolve()}\n", encoding="utf-8")
    await pool.prune_orphans()
    assert precious_file.exists()


@pytest.mark.asyncio
async def test_verify_candidate_disproves_missing_poc_and_non_dict_block_rep(tmp_path: Path):
    """驗證 CONFIRMED 但缺少 poc_script 時強制降級為 DISMISSED，且非 dict 之 block_replacement 不會崩潰"""
    target = {"id": "backend/sample.py", "file_path": "backend/sample.py"}
    cand_no_poc = {
        "target_id": "backend/sample.py",
        "verdict": "CONFIRMED",
        "reasoning": "Missing PoC script",
        "poc_script": None,
    }
    res = await verify_candidate_in_worktree(tmp_path, target, cand_no_poc)
    assert res["verdict"] == "DISMISSED"
    assert "[Disprove-by-Default Circuit Breaker]" in res["reasoning"]

    cand_bad_block = {
        "target_id": "backend/sample.py",
        "verdict": "CONFIRMED",
        "reasoning": "Has Red PoC but malformed block_replacement",
        "poc_script": "def test_red():\n    assert 1 == 2\n",
        "block_replacement": "malformed-string",
    }
    res2 = await verify_candidate_in_worktree(tmp_path, target, cand_bad_block)
    assert res2["verdict"] == "CONFIRMED"
    assert res2["patch_test_passed"] is False





def test_normalize_code_archaeology_helper():
    """驗證 normalize_code_archaeology 常模防呆轉換與預設欄位防護"""
    from scripts.lib.adversarial_team import (
        DEFAULT_CODE_ARCHAEOLOGY,
        normalize_code_archaeology,
    )

    assert normalize_code_archaeology(None) == DEFAULT_CODE_ARCHAEOLOGY
    assert normalize_code_archaeology("not a dict") == DEFAULT_CODE_ARCHAEOLOGY

    partial = {"legacy_function": "Old sanitizer"}
    normalized = normalize_code_archaeology(partial)
    assert normalized["legacy_function"] == "Old sanitizer"
    assert normalized["design_intent"] is None
    assert normalized["regression_risk"] is None

    full = {
        "legacy_function": "f1",
        "design_intent": "d1",
        "regression_risk": "r1",
        "extra": "ignore",
    }
    assert normalize_code_archaeology(full) == {
        "legacy_function": "f1",
        "design_intent": "d1",
        "regression_risk": "r1",
    }


@pytest.mark.asyncio
async def test_verify_candidate_preserves_code_archaeology_across_all_branches(tmp_path: Path):
    """驗證 verify_candidate_in_worktree 在所有提早返回與降級分支均完整保留 code_archaeology 欄位"""
    target = {"id": "backend/sample.py", "file_path": "backend/sample.py"}
    arch = {
        "legacy_function": "Calculates total cost",
        "design_intent": "Single source of truth split",
        "regression_risk": "Breaks dynamic recompute",
    }

    # Branch 1: 原本即為 DISMISSED
    cand_dismissed = {
        "target_id": "backend/sample.py",
        "verdict": "DISMISSED",
        "reasoning": "Already safe",
        "code_archaeology": arch,
    }
    res1 = await verify_candidate_in_worktree(tmp_path, target, cand_dismissed)
    assert res1["code_archaeology"] == arch
    assert res1["worktree_verified"] is True

    # Branch 2: CONFIRMED 但無 poc_script
    cand_no_poc = {
        "target_id": "backend/sample.py",
        "verdict": "CONFIRMED",
        "reasoning": "No poc",
        "poc_script": None,
        "code_archaeology": arch,
    }
    res2 = await verify_candidate_in_worktree(tmp_path, target, cand_no_poc)
    assert res2["verdict"] == "DISMISSED"
    assert res2["code_archaeology"] == arch

    # Branch 3: PoC 運行為 GREEN_SAFE (Exit code 0)
    cand_green = {
        "target_id": "backend/sample.py",
        "verdict": "CONFIRMED",
        "reasoning": "Claimed flaw",
        "poc_script": "def test_green(): assert True\n",
        "code_archaeology": arch,
    }
    res3 = await verify_candidate_in_worktree(tmp_path, target, cand_green)
    assert res3["verdict"] == "DISMISSED"
    assert res3["code_archaeology"] == arch
    assert "[Worktree Physical Defense Proof]" in res3["reasoning"]

    # Branch 4: PoC 語法錯誤 (INVALID_POC)
    cand_syntax_err = {
        "target_id": "backend/sample.py",
        "verdict": "CONFIRMED",
        "reasoning": "Claimed flaw",
        "poc_script": "def test_syntax_err(:\n",
        "code_archaeology": arch,
    }
    res4 = await verify_candidate_in_worktree(tmp_path, target, cand_syntax_err)
    assert res4["verdict"] == "DISMISSED"
    assert res4["code_archaeology"] == arch


def test_isolated_safe_subprocess_reexport_importable():
    """驗證 .agents/skills/security-sentinel/scripts/lib/ 下之 safe_subprocess 可獨立匯入不報錯"""
    import importlib.util

    reexport_path = (
        _REPO_ROOT
        / ".agents"
        / "skills"
        / "security-sentinel"
        / "scripts"
        / "lib"
        / "safe_subprocess.py"
    )
    spec = importlib.util.spec_from_file_location("local_safe_subprocess", reexport_path)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "run_streaming_process")
    assert hasattr(mod, "ProcessResult")


@pytest.mark.asyncio
async def test_mantis_benign_control_blocks_lobotomized_patch(tmp_path: Path):
    """驗證 Mantis Block G: 當補丁以閹割方式修復攻擊，但破壞良性輸入時，自動阻斷並復原原始代碼"""
    from scripts.lib.adversarial_team import verify_candidate_in_worktree

    svc_dir = tmp_path / "backend" / "services"
    svc_dir.mkdir(parents=True, exist_ok=True)
    target_file = svc_dir / "calculator.py"
    original_code = (
        "def compute_total(items: list[int]) -> int:\n"
        "    if len(items) > 10: raise ValueError('overflow')\n"
        "    return sum(items)\n"
    )
    target_file.write_text(original_code, encoding="utf-8")

    target_meta = {"id": "backend/services/calculator.py", "file_path": "backend/services/calculator.py"}

    # Attacker gives both an exploit test (fails on overflow) and a benign control test
    poc_script = (
        "from services.calculator import compute_total\n"
        "def test_poc_exploit():\n"
        "    # Unpatched raises ValueError\n"
        "    assert compute_total([1]*15) == 15\n"
        "def test_benign_control():\n"
        "    # Legitimate inputs must continue to compute sum correctly\n"
        "    assert compute_total([1, 2, 3]) == 6\n"
    )

    # Lobotomized patch: returns 0 for everything (breaks benign control)
    cand_lobotomized = {
        "target_id": target_meta["id"],
        "verdict": "CONFIRMED",
        "reasoning": "Integer overflow vulnerability",
        "poc_script": poc_script,
        "block_replacement": {
            "target_content": "def compute_total(items: list[int]) -> int:\n    if len(items) > 10: raise ValueError('overflow')\n    return sum(items)",
            "replacement_content": "def compute_total(items: list[int]) -> int:\n    return 0",
        },
    }

    res = await verify_candidate_in_worktree(tmp_path, target_meta, cand_lobotomized)
    assert res["verdict"] == "CONFIRMED"
    # Block G must reject the patch because benign_control failed!
    assert res["patch_test_passed"] is False
    assert res["benign_control_passed"] is False
    # File must be restored
    assert target_file.read_text(encoding="utf-8") == original_code


@pytest.mark.asyncio
async def test_mantis_benign_control_prevents_false_red_when_only_benign_fails(tmp_path: Path):
    """驗證當攻擊測試本身通過（未發現漏洞），但良性測試寫錯報錯時，不會引發假紅燈，而是疑罪從無 DISMISSED"""
    from scripts.lib.adversarial_team import verify_candidate_in_worktree

    svc_dir = tmp_path / "backend" / "services"
    svc_dir.mkdir(parents=True, exist_ok=True)
    target_file = svc_dir / "safe_svc.py"
    target_file.write_text("def ping(): return 'pong'\n", encoding="utf-8")

    target_meta = {"id": "backend/services/safe_svc.py", "file_path": "backend/services/safe_svc.py"}

    # Exploit test passes, but benign test has broken assertion
    poc_script = (
        "from services.safe_svc import ping\n"
        "def test_poc():\n"
        "    assert ping() == 'pong'\n"
        "def test_benign_broken():\n"
        "    assert ping() == 'wrong'\n"
    )

    cand = {
        "target_id": target_meta["id"],
        "verdict": "CONFIRMED",
        "reasoning": "Claimed flaw",
        "poc_script": poc_script,
    }

    res = await verify_candidate_in_worktree(tmp_path, target_meta, cand)
    # Because exploit test passed with exit code 0, it must be DISMISSED!
    assert res["verdict"] == "DISMISSED"
    assert "[Worktree Physical Defense Proof]" in res["reasoning"]


def test_mantis_advise_loads_historical_design_intents_from_ledger(tmp_path: Path):
    """驗證 load_historical_design_intents 能正確讀取 ledger 中的 known_design_intents 與 DISMISSED 歷史"""
    import json
    import importlib.util

    runner_path = _REPO_ROOT / ".agents" / "skills" / "security-sentinel" / "scripts" / "runner.py"
    spec = importlib.util.spec_from_file_location("runner_module", runner_path)
    runner_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner_mod)
    load_historical_design_intents = getattr(runner_mod, "load_historical_design_intents")

    docs_dir = tmp_path / "docs" / "security"
    docs_dir.mkdir(parents=True, exist_ok=True)
    ledger_file = docs_dir / "security-coverage-ledger.json"

    ledger_data = {
        "known_design_intents": {
            "backend/routers/expenses.py": "Single Source of Truth split calculation",
            "frontend/components/chat-widget.tsx": "Deliberate conversation reset on trip switch",
        },
        "targets": [
            {
                "id": "backend/routers/expenses.py:total_amount_split",
                "status": "DISMISSED",
                "validator_details": "Verified intentional design: dynamic recompute is SSOT."
            }
        ]
    }
    ledger_file.write_text(json.dumps(ledger_data), encoding="utf-8")

    intents = load_historical_design_intents(tmp_path, "backend/routers/expenses.py")
    assert "Single Source of Truth split calculation" in intents
    assert "Historical DISMISSED Defense" in intents


def test_harness2_findings_conservation_assertion():
    """驗證 Harness^2 守恆斷言: 嚴格檢查 confirmed + dismissed + inconclusive == total == len(findings)"""
    import importlib.util

    runner_path = _REPO_ROOT / ".agents" / "skills" / "security-sentinel" / "scripts" / "runner.py"
    spec = importlib.util.spec_from_file_location("runner_module", runner_path)
    runner_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner_mod)
    assert_findings_conservation = getattr(runner_mod, "assert_findings_conservation")

    valid_payload = {
        "total_validated": 3,
        "confirmed_count": 1,
        "dismissed_count": 1,
        "inconclusive_count": 1,
        "findings": [{"id": 1}, {"id": 2}, {"id": 3}],
    }
    # Should pass without exception
    assert_findings_conservation(valid_payload)

    # Broken count sum
    invalid_counts = dict(valid_payload, confirmed_count=2)
    try:
        assert_findings_conservation(invalid_counts)
        assert False, "Should have raised AssertionError"
    except AssertionError as e:
        assert "Ledger conservation failure" in str(e)

    # Broken findings length
    invalid_len = dict(valid_payload, findings=[{"id": 1}])
    try:
        assert_findings_conservation(invalid_len)
        assert False, "Should have raised AssertionError"
    except AssertionError as e:
        assert "Ledger length mismatch" in str(e)
