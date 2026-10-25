# 🛡️ Tabiji 資安治理與 Sentinel 審查全景庫 (Security & Sentinel Governance)

> **核心準則**: 無罪推定直到實證證偽 (Presumption of Innocence until Empirically Proven)  
> **隔離機制**: 調度背景 `agy.exe -p --sandbox` 獨立子行程進行物理隔離對抗驗證。

---

## 1. 目錄拓撲與資產劃分 (Directory Topology)

```text
docs/security/
├── README.md                          # 📖 本文件：資安架構指引與目錄治理規範
├── security-coverage-ledger.json      # 🛡️ 權威資安覆蓋帳本 (全站核心防禦邊界唯一事實來源)
├── reports/                           # 📑 正式 Markdown 審查報告存檔
│   ├── latest_neural_complication_report.md  # 🩺 神經診斷書（單例置頂）
│   └── 2026-10/                       # 🗓️ 依月份收納之 Sentinel 歷史報告 (90+ 份)
└── history/                           # 🗄️ 對抗審查執行產物 (合規審查存證庫)
    ├── candidates/                    # 歷次假說輸入 JSON (60+ 份)
    ├── findings/                      # 歷次物理沙盒驗證結果 JSON (40+ 份，Git 忽略)
    └── patches/                       # 歷次候選補丁 RFC diff 檔案 (20+ 份)
```

---

## 2. 核心檔案職責 (Core Artifacts)

### 1. 權威安全台帳 (`security-coverage-ledger.json`)
- **定位**: 全專案攻擊面與防禦狀態之唯一事實來源 (Single Source of Truth)。
- **記錄指標**:
  - `total_targets`: 納管防禦標的總數。
  - `audited_targets`: 已完成驗證目標數。
  - `verified_vulnerabilities`: 經實證確認之漏洞數。
  - `dismissed_hypotheses`: 經沙盒實證反駁之無效假說數。
- **維護原則**: 任何安全性架構變更或 Sentinel 審查通過後，必須原子化登錄審查時間、狀態（`SECURE` / `REMEDIATED`）、`report_ref`（指向 `reports/YYYY-MM/`）與 `resolution`（指向 `history/patches/`）。

### 2. 正式審查報告 (`reports/`)
- `latest_neural_complication_report.md`: 保持於 `reports/` 根目錄，為 `scripts/neural_seam_harness.py` 確定性相依。
- 收錄依月份歸檔之 Markdown 報告（如 `reports/YYYY-MM/security_sentinel_report_YYYY-MM-DD_*.md`）。
- 報告包含執行總結、假說對抗明細、驗證證據鏈以及通過簽核 (Sign-Off)。

### 3. 歷史存證庫 (`history/`)
- `candidates/`: 記錄 Hunter 階段產生的攻擊假說輸入檔（命名規範：`candidates_<topic>_<date>.json`）。
- `findings/`: 記錄 Validator 物理沙盒輸出的判定結構檔（命名規範：`findings_<topic>.json`）。
- `patches/`: 記錄 Mantis 補丁合成階段產生的 `patch_candidate_*.diff`。

---

## 3. Security Sentinel 執行流程 (SOP)

```mermaid
graph TD
    A[Phase 1: 讀取 security-coverage-ledger.json] --> B[Phase 2: Hunter 假說生成 history/candidates/candidates_*.json]
    B --> C["Phase 3: 調度 runner.py (輸出至 history/findings/)"]
    C --> D{驗證結果}
    D -- CONFIRMED --> E[Phase 4: Mantis 補丁合成 history/patches/patch_candidate_*.diff]
    D -- DISMISSED --> F[確認原生防禦機制充分]
    E --> G[Phase 5: 原子更新 Ledger 與產出 reports/YYYY-MM/ 報告]
    F --> G
    G --> H[Phase 6: Human Gate 審閱與核准實作]
```

### 常用審查指令
```bash
# 執行整組候選假說驗證
python .agents/skills/security-sentinel/scripts/runner.py \
  --candidates docs/security/history/candidates/candidates_<topic>_<date>.json \
  --output docs/security/history/findings/findings_<topic>.json \
  --timeout 120

# 單一檔案快速對抗檢驗
python .agents/skills/security-sentinel/scripts/runner.py \
  --target-file "backend/services/intent_router.py" \
  --vector "prompt_injection" \
  --hypothesis "Sanitizer allows bypassing system instructions via unicode control characters" \
  --output "docs/security/history/findings/findings.json"
```
