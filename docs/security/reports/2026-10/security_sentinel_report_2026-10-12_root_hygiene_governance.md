# 🛡️ Security Sentinel 對抗審計報告：專案根目錄衛生防護與路徑防呆治理

> **審計日期**: 2026-10-12  
> **審計模式**: `sentinel-adversarial-sandbox` (物理沙盒證偽審查)  
> **關聯議題**: `candidates.json` 根目錄殘留治理與全域路徑防呆機制  
> **狀態**: `CONFIRMED_VULNERABILITIES` (等待人類核准應用補丁)  

---

## 1. Executive Summary (審計摘要)

| 指標 | 數值 | 說明 |
| :--- | :--- | :--- |
| **總受審目標 (Total Targets)** | 3 | `runner.py`, `push.md`, `SKILL.md` |
| **確認漏洞 (Confirmed)** | 3 | 根目錄路徑污染、Windows 磁碟代號比較失效、發布守門員缺失 |
| **證偽排除 (Dismissed)** | 0 | - |
| **沙盒單元測試 (PoC Tests)** | 5/5 通過 | `backend/tests/test_root_hygiene_sentinel.py` |
| **全棧回歸狀態 (Regression)** | 100% 綠燈 | 433 vitest + 5 pytest 全部 PASS |

---

## 2. Attack Surface Coverage Matrix (攻擊面矩陣)

| 目標組件 | 信任邊界 | 檢驗威脅向量 | 判定結果 | 實證位置 |
| :--- | :--- | :--- | :--- | :--- |
| `.agents/skills/security-sentinel/scripts/runner.py` | `developer_to_filesystem` | `filesystem_namespace_pollution` | **CONFIRMED** | `backend/tests/test_root_hygiene_sentinel.py::test_runner_blocks_bare_filename_in_root` |
| `.agents/skills/security-sentinel/scripts/runner.py` | `developer_to_filesystem` | `path_comparison_bypass_on_windows` | **CONFIRMED** | `backend/tests/test_root_hygiene_sentinel.py::test_runner_normalizes_drive_casing` |
| `.agents/workflows/push.md` | `git_stage_to_remote` | `workflow_quality_gate_omission` | **CONFIRMED** | `backend/tests/test_root_hygiene_sentinel.py::test_push_gate_whitelist_filtering` |

---

## 3. Confirmed Vulnerability Details & In-Memory PoCs

### 3.1 漏洞 1: `runner.py` 缺乏根目錄阻斷防呆 (Path Namespace Pollution)
- **問題描述**: `runner.py` 解析 `--candidates` 與 `--output` 時，未比對其解析後的父目錄是否為專案根目錄。當輸入 `candidates.json` 或 `findings.json` 時，直接於專案根目錄產生或讀取檔案，導致殘留孤兒中繼檔。
- **PoC 實證結果**:
  ```
  backend/tests/test_root_hygiene_sentinel.py::test_runner_blocks_bare_filename_in_root PASSED [20%]
  backend/tests/test_root_hygiene_sentinel.py::test_runner_blocks_absolute_root_path PASSED [40%]
  ```

### 3.2 漏洞 2: Windows 磁碟代號大小寫比較盲區 (Case Normalization Bypass)
- **問題描述**: Windows 檔案系統具備大小寫不敏感特性（Case-Insensitive），若路徑比較未經 `os.path.normcase` 處理，`d:\...` 與 `D:\...` 在物件比對時判定為不相等，造成根目錄防呆繞過。
- **PoC 實證結果**:
  ```
  backend/tests/test_root_hygiene_sentinel.py::test_runner_normalizes_drive_casing PASSED [60%]
  ```

### 3.3 漏洞 3: `/push` 發布管線缺乏根目錄衛生審核
- **問題描述**: 現有 `/push` 工作流僅驗證 TypeScript、ESLint、Vitest、Pytest，未掃描專案根目錄是否存在非設定檔類型的中繼產物（如未被追蹤或被 `.gitignore` 隱藏之 `.json`, `.diff`, `.tmp`）。
- **PoC 實證結果**:
  ```
  backend/tests/test_root_hygiene_sentinel.py::test_push_gate_whitelist_filtering PASSED [100%]
  ```

---

## 4. Mantis Patch & Block Replacement Candidate (候選補丁)

補丁已生成於: [`docs/security/history/patches/patch_candidate_root_hygiene_governance.diff`](file:///d:/Project/Tabidachi/travel-pwa/docs/security/history/patches/patch_candidate_root_hygiene_governance.diff)

### 區塊替換明細 (Exact Block Replacements)

#### [替換區塊 1] `.agents/skills/security-sentinel/scripts/runner.py`
- **目標範圍**: Lines 16–22
- **原有代碼**:
  ```python
  # Self-resolving sys.path to locate scripts.lib.safe_subprocess across arbitrary CWDs
  _SCRIPT_DIR = Path(__file__).resolve().parent
  _REPO_ROOT = _SCRIPT_DIR.parents[3]  # .agents/skills/security-sentinel/scripts -> repo root
  if str(_REPO_ROOT) not in sys.path:
      sys.path.insert(0, str(_REPO_ROOT))
  ```
- **替換為**:
  ```python
  # Self-resolving sys.path to locate scripts.lib.safe_subprocess across arbitrary CWDs
  _SCRIPT_DIR = Path(__file__).resolve().parent
  _REPO_ROOT = Path(__file__).resolve().parents[4]  # .agents/skills/security-sentinel/scripts/runner.py -> repo root
  if str(_REPO_ROOT) not in sys.path:
      sys.path.insert(0, str(_REPO_ROOT))

  def assert_security_path_hygiene(file_path: Optional[str], param_name: str, repo_root: Path = _REPO_ROOT) -> None:
      """🛡️ 根目錄衛生強制防呆：禁止任何中繼檔案落在專案根目錄"""
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
  ```

#### [替換區塊 2] `.agents/skills/security-sentinel/scripts/runner.py`
- **目標範圍**: Lines 239–243
- **原有代碼**:
  ```python
      workspace_root = Path(__file__).resolve().parents[4]

      candidates = []
  ```
- **替換為**:
  ```python
      workspace_root = _REPO_ROOT

      if args.candidates:
          assert_security_path_hygiene(args.candidates, "--candidates", repo_root=workspace_root)
      if args.output:
          assert_security_path_hygiene(args.output, "--output", repo_root=workspace_root)

      candidates = []
  ```

#### [替換區塊 3] `.agents/skills/security-sentinel/SKILL.md`
- **目標範圍**: Phase 2 與 Phase 3 指令範例
- **原有代碼**:
  ```markdown
  - Output candidate hypotheses to `candidates.json`:
  ...
  python .agents/skills/security-sentinel/scripts/runner.py --candidates candidates.json --output docs/security/findings.json --timeout 120
  ```
- **替換為**:
  ```markdown
  - Output candidate hypotheses to `docs/security/candidates_<topic>_<YYYY-MM-DD>.json`:
  ...
  python .agents/skills/security-sentinel/scripts/runner.py --candidates docs/security/candidates_{topic}_{date}.json --output docs/security/findings_{topic}.json --timeout 120
  ```

#### [替換區塊 4] `.agents/workflows/push.md`
- **目標範圍**: Line 16
- **插入代碼**:
  ```powershell
  # 0. 專案根目錄衛生檢查 (Root Hygiene Gate)
  $whitelist = @("package.json", "package-lock.json", "tsconfig.json", "components.json", "NOTICE.md", "README.md", "next.config.ts")
  $offenders = Get-ChildItem -Path . -File | Where-Object { 
      ($_.Extension -match '^\.(diff|tmp|bak|log)$') -or 
      ($_.Extension -eq '.json' -and $whitelist -notcontains $_.Name)
  }
  if ($offenders) {
      Write-Error "🚨 [Root Hygiene Gate] 偵測到專案根目錄存在未歸位檔案: $($offenders.Name -join ', ')。請歸位後再執行 push！"
      exit 1
  }
  ```

#### [實體檔案遷移指令]
```powershell
Move-Item -Path "candidates.json" -Destination "docs/security/candidates_expense_toggle_icon_harmony.json" -Force
git add "docs/security/candidates_expense_toggle_icon_harmony.json"
```

---

## 5. Human Gate Handover (交付決定)

依據 L0 憲法規範，本稽核報告與候選補丁已完成沙盒證偽。所有原始碼檔案在人類授權前保持不變。
請確認是否核准套用補丁與執行檔案歸位作業。
