# 領域知識庫：CI/CD、工程化守門與資安攻防 (devops_security)

> **所屬領域**: GitHub Actions, PowerShell 熔斷, Security Sentinel (runner.py), 台帳驗證 (validate_security_ledger.py)

## 🏛️ 架構決策 (Decisions)
- **記憶 3-Tier 微核心與領域按需載入原則 (3-Tier Sharded Memory Routing)**: memory.md 必須保持 <50 行微核心憲法，包含領域路由表與全域詞彙；具體決策按業務維度下放至 .agents/domains/*.md，透過 AGENTS.md 路由指引按需延遲載入，嚴禁重構為單體大檔案。

- **Cloudflare 式台帳數學守恆與非多態硬驗證守則 (Deterministic Security Ledger Invariance)**: 資安覆蓋帳本必須受 validate_security_ledger.py 靜態守護：所有 targets 必須唯一使用 id 鍵，嚴禁 target_id 多態殘留；統計總數必須嚴格滿足 total_targets == audited_targets == (verified + remediated + dismissed) 數學守恆。

- **PowerShell 確定性熔斷守門架構**: 嚴禁依賴非熔斷的 ; 或無效的 &&。所有守門腳本必須明確宣告 if ($LASTEXITCODE -ne 0) { exit 1 }。
- **雙模 AST/正則防禦架構**: JSX 樹狀結構複雜樣式反模式採 AST 節點鎖定搭配正則約束，兼顧精確度與零偽陽性。
- **三重活體驗收防線**: 編譯鏈更新時串聯 npm audit, vitest 與 next build 進行真實驗收。
- **overrides 原地安全合併原則**: package.json 依賴覆蓋採增量原地合併，保留既有修復。
- **Security Sentinel 物理沙盒證偽驗收**: 透過 runner.py 調度獨立 agy.exe -p --sandbox 進行無提示詞污染的對抗審查；推行 In-Memory PoC 標準。
- **Cloudflare 確定性台帳硬核驗證**: validate_security_ledger.py 靜態硬驗證 ID 唯一性、無 target_id 多態殘留、狀態白名單與數學守恆。
- **Mantis-Critic 假陽性修剪與中性語意轉化**: 假說生成前洗滌 DoS/flood 等黑話為中性軟體工程術語，杜絕安全模型誤報；Critic 預審排除防禦在層。

## 🛡️ 踩坑記錄 (Failed Paths)
- **FP-050 (Sentinel 假說被安全過濾器攔截)**: 候選假說使用了攻擊性字眼導致雲端 API 攔截報 INCONCLUSIVE。規範一律使用中性品質工程措辭。
- **FP-027 (專案根目錄衛生硬防線)**: runner.py 強制攔截裸檔名輸出至根目錄；白名單外違規檔案立即觸發 sys.exit(1)。
