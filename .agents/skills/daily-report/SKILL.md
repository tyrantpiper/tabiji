---
name: Daily Report
description: Generates a master-level daily report using deterministic data gathering and tiered memory consolidation.
---

# Daily Report 2.0 Workflow (/daily-report)

> **架構守則 (Master-Level Doctrine)**: 
> 真正的 Master 級別報告絕對不是「流水帳」，而是「文件即程式碼 (Documentation-as-Code)」。
> 本工作流融合 **Cloudflare 確定性台帳**、**Google Mantis 顧問庫** 與 **Google Research Harness² 經驗反射器**，落實「雙軌輸出」與「大腦分層閉環」。

---

## 1. 確定性資料採集 (Hard Data Ingestion)
**禁止憑空想像。Agent 必須嚴格執行以下指令獲取真實數據：**
1. **Git 增量與攻擊面捕捉**: 執行 `git log --since="1am" --oneline` 與 `git diff HEAD~1 --stat`。
2. **資安台帳確定性核對**: 執行 `python scripts/validate_security_ledger.py`，確認 `security-coverage-ledger.json` 保持數學守恆。
3. **終端與會話日誌掃描**: 檢查今日對話中的踩坑紀錄 (Failed Paths) 與架構決策 (AD)。
4. **全棧 Quality Gate 驗證**: 確認 TypeScript (`tsc --noEmit`)、ESLint、Vitest 與 Pytest 全數綠燈。

---

## 2. 雙軌多維度知識提煉 (Dual-Track Synthesis)

### 軌道 A：人類高密度工程敘事 (Human-Readable Journal)
以資深架構師 (@architect) 視角分類：
- 🟢 **Features & Fixes**: 今日實際交付的架構與業務價值。
- 🏛️ **Architecture Decisions**: 今日做出的架構級決策（標註 AD 序號、Context、Decision 與 Trade-offs）。
- 🔴 **Technical Debt**: 今日留下的技術債與待辦清單（若已有 Commit 解決，顯式標註 `[RESOLVED in <commit>]`）。
- 🛡️ **Failed Paths**: 今日踩過的坑與失敗的嘗試（標註 FP 序號、Symptom 與 Lesson）。
- 🎯 **Next Steps**: 明日核心衝刺目標。

### 軌道 B：機器可執行不變量區塊 (Machine-Executable Invariant Rules)
**在報告末端固定輸出標準 JSON 區塊，供 Auto Dream 2.0 經驗反射器 0ms 確定性分流至 6 大領域庫：**
```markdown
## 🧬 Machine-Executable Invariant Rules
```json
[
  {
    "domain": "map_webgl" | "state_cache" | "ios_ui" | "offline_pwa" | "backend_concurrency" | "devops_security",
    "type": "INVARIANT_RULE" | "FAILED_PATH" | "TECHNICAL_DEBT_RESOLUTION",
    "id": "INV-..." | "FP-..." | "DEBT-...",
    "title": "Rule title",
    "content": "Specific actionable rule description",
    "status": "RESOLVED" // 僅用於 TECHNICAL_DEBT_RESOLUTION
  }
]
```
```

---

## 3. 持久化日誌存檔 (Immutable Journaling)
1. 將完整雙軌報告存檔至：`docs/journals/YYYY-MM-DD-daily-report.md`。

---

## 4. 潛意識記憶分流與確定性 GC (Neural Memory Consolidation)
1. 執行 Auto Dream 2.0 注入指令：
   ```bash
   python scripts/auto_dream.py --inject-report docs/journals/YYYY-MM-DD-daily-report.md
   ```
2. Auto Dream 2.0 將自動解析 `Machine-Executable Invariant Rules`，將不變量分流路由至 `.agents/domains/*.md`，並抹除已標記 `[RESOLVED]` 的過期技術債。
3. 向使用者回報：日誌存檔完畢、資安台帳驗證通過、大腦領域庫已確定性進化。
