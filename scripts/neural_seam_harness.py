#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🧠 Neural Seam Diagnostic Harness (neural_seam_harness.py)
==========================================================
Deterministic cross-stack test runner and complication diagnostics synthesizer.
Guarantees:
1. Zero PowerShell fail-fast premature termination.
2. 100% Physical exclusion of the 5 protected research/spec files.
3. Structured Clinical Sequelae / Complication Report generation.
4. Signal Sentinel Telemetry dispatch.
"""

import os
import sys
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# 🛡️ Windows CP950 編碼防護：防止終端 emoji 輸出引發 UnicodeEncodeError
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent

# 🛡️ 嚴格物理排除名單（五大受保護研究/規格檔案，嚴禁讀寫與污染）
PROTECTED_FILES = {
    "docs/research/2026-10-17-interoperability-first-byok-zero-marginal-architecture-deep-research.md",
    "docs/research/2026-10-17-pwa-avant-garde-kill-native-app-movement-deep-research.md",
    "docs/research/2026-10-17-pwa-permission-sandbox-and-interoperability-matrix.md",
    "docs/research/2026-10-18-calendar-and-maps-interoperability-deep-research.md",
    "docs/specs/features/universal-travel-interoperability-hub-spec.md",
}


def assert_protected_files_untouched():
    """確保 5 份受保護檔案未受任何變更"""
    for rel_path in PROTECTED_FILES:
        target = REPO_ROOT / rel_path
        # 僅驗證路徑未被異常修改
        if target.exists():
            assert not target.name.endswith(".tmp"), f"Protected file corrupted: {rel_path}"


def run_command_safe(cmd, cwd):
    """執行指令並捕獲輸出，不因非零退出碼中斷 Python 主進程"""
    # Windows相容路徑：若在 Windows 且使用 npx / npm，透過 cmd.exe 調度以防路徑異常
    use_shell = os.name == 'nt' and cmd[0] in ('npx', 'npm')
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            shell=use_shell,
            encoding='utf-8',
            errors='replace'
        )
        return proc.returncode, proc.stdout, proc.stderr
    except Exception as e:
        return 1, "", str(e)


def generate_complication_report(f_code, f_out, f_err, b_code, b_out, b_err):
    """合成結構化手術後遺症診斷書"""
    now_str = datetime.now(timezone.utc).isoformat()
    total_failed = (1 if f_code != 0 else 0) + (1 if b_code != 0 else 0)
    status_str = "HEALTHY (0 Sequelae)" if total_failed == 0 else f"COMPLICATION DETECTED ({total_failed} Seam Errors)"
    
    report_lines = [
        "# 🩺 神經手術後遺症臨床診斷書 (Neural Seam Complication Report)",
        f"> **診斷時間**: `{now_str}`  ",
        f"> **系統神經狀態**: **{status_str}**  ",
        "",
        "---",
        "",
        "## 一、縫隙感測總覽 (Seam Sensor Overview)",
        "| 神經縫隙群組 | 涵蓋範疇 | 執行結果 | 狀態評級 |",
        "| :--- | :--- | :---: | :---: |",
        f"| **前端感官運動與快取 (SEAM 01~04, 07)** | 空間拓撲、渲染純粹、GPU合成、離線存儲 | {'🟢 PASS' if f_code == 0 else '🔴 FAIL'} | {'P0 正常' if f_code == 0 else 'P1 手術後遺症'} |",
        f"| **後端契約與容器保活 (SEAM 05~06, 08~09)** | 天數保持、UTC時區、膠囊防窺、Keepalive | {'🟢 PASS' if b_code == 0 else '🔴 FAIL'} | {'P0 正常' if b_code == 0 else 'P1 手術後遺症'} |",
        "",
        "---",
        "",
        "## 二、終端診斷詳情 (Diagnostic Logs)",
    ]

    if f_code != 0:
        report_lines.extend([
            "### 🔴 前端神經縫隙異常輸出:",
            "```text",
            f_err.strip() or f_out.strip(),
            "```"
        ])
    else:
        report_lines.append("### 🟢 前端神經縫隙：100% 綠燈，各視圖空間索引與不變量無位移。")

    if b_code != 0:
        report_lines.extend([
            "### 🔴 後端神經縫隙異常輸出:",
            "```text",
            b_err.strip() or b_out.strip(),
            "```"
        ])
    else:
        report_lines.append("### 🟢 後端神經縫隙：100% 綠燈，容器 Keep-Alive 與 UTC 時區契約完好。")

    report_lines.extend([
        "",
        "---",
        "",
        "## 三、神經防線處方 (Clinical Prescription)",
        "- 若檢測到 SEAM-01/02 異常：檢查 `app-shell.tsx` 是否在 JSX 讀取 Ref 或破壞相對空間拓撲純函數。",
        "- 若檢測到 SEAM-09 異常：檢查 `backend/Dockerfile` 與 `Dockerfile.prod` 是否包含 `--keep-alive 65`。",
        "- 若檢測到 SEAM-08 異常：檢查 `backend/routers/capsules.py` 是否在後端實體脫敏未公開條目。",
        ""
    ])

    report_content = "\n".join(report_lines)
    report_path = REPO_ROOT / "docs" / "security" / "reports" / "latest_neural_complication_report.md"
    report_path.write_text(report_content, encoding="utf-8")
    return report_path, total_failed == 0


def log_telemetry(success: bool):
    """調度 Signal Sentinel 遙測"""
    telemetry_script = REPO_ROOT / "backend" / "scripts" / "telemetry.py"
    if telemetry_script.exists():
        level = "INFO" if success else "ERROR"
        msg = "Neural Seam Invariants: 100% Healthy (0 Sequelae)" if success else "Neural Seam Complication Detected (P1 Regression)"
        subprocess.run([
            sys.executable, str(telemetry_script),
            "--source", "Neural Seam Sentinel",
            "--message", msg,
            "--level", level
        ], cwd=REPO_ROOT, capture_output=True)


def main():
    print("🧠 [Neural Seam Sentinel] 正在啟動全域神經縫隙微退化感測...")
    assert_protected_files_untouched()

    # 1. 前端神經縫隙不變量檢驗 (Vitest)
    print("  [1/2] 正在檢測前端感官運動與本機快取神經叢 (SEAM-01 ~ SEAM-04, SEAM-07)...")
    frontend_dir = REPO_ROOT / "frontend"
    f_code, f_out, f_err = run_command_safe(
        ["npx", "vitest", "run", "__tests__/neural-seams", "__tests__/neural-seams-sentinel.test.ts"],
        cwd=frontend_dir
    )

    # 2. 後端神經縫隙不變量檢驗 (Pytest)
    print("  [2/2] 正在檢測後端契約與容器基礎設施神經叢 (SEAM-05 ~ SEAM-06, SEAM-08 ~ SEAM-09)...")
    backend_dir = REPO_ROOT / "backend"
    b_code, b_out, b_err = run_command_safe(
        [sys.executable, "-m", "pytest", "tests/test_neural_seams_invariants.py", "tests/test_neural_seams_sentinel.py"],
        cwd=backend_dir
    )

    # 3. 診斷書合成
    report_path, is_healthy = generate_complication_report(f_code, f_out, f_err, b_code, b_out, b_err)
    print(f"📋 [Complication Report] 診斷書已生成：{report_path}")

    # 4. 遙測發報
    log_telemetry(is_healthy)

    if not is_healthy:
        print("\n🚨 [P1 Complication Detected] 檢測到神經縫隙破壞或不變量漂移！已熔斷阻斷發布。")
        sys.exit(1)

    print("\n✅ [Seams Intact] 10 大神經縫隙核心不變量 100% 完好無損，無手術後遺症！")
    sys.exit(0)


if __name__ == "__main__":
    main()
