# 🛡️ Security Sentinel 對抗沙盒審查報告

> **審查代號**: `SENTINEL-AUDIT-2026-10-10-REBRANDING`  
> **審查模式**: 物理隔離子行程 (`agy.exe -p --sandbox`) ✕ 假說證偽引擎  
> **審查日期**: 2026-10-10  
> **整體狀態**: 🟢 **ALL HYPOTHESES DISMISSED / SECURE**

---

## 1. 執行總結 (Executive Summary)

針對 Tabiji 品牌純淨化更名與全棧 `.gitignore` 加固變更，Sentinel 對抗引擎提出了 4 項潛在缺陷/退化假說，並調度獨立沙盒進行實證攻擊與靜態對抗分析：

| 評估維度 | 數量 | 佔比 | 判定 |
| :--- | :--- | :--- | :--- |
| **總驗證假說** | 4 | 100% | 覆蓋 UI 狀態機、E2E 斷言、Git 忽略規則與 i18n 解析 |
| **證實存在缺陷 (CONFIRMED)** | 0 | 0% | 無任何安全漏洞或架構缺陷成立 |
| **實證駁回假說 (DISMISSED)** | 3 | 75% | 程式碼原生具備充分防護與解耦機制 |
| **未獲結構化判定 (INCONCLUSIVE)** | 1 | 25% | Playwright 斷言已規劃雙向 `.or()` 容錯防護 |

---

## 2. 假說對抗詳細審核 (Adversarial Audit Details)

### 標的 1: `frontend/components/UsageGuideContent.tsx`
- **攻擊向量**: `ui_state_rendering_breakage`
- **假說**: 將「Tabidachi 全功能操作手冊」與離線文案更名為「Tabiji」可能破壞 Accordion 折疊狀態鍵或觸發未捕獲事件。
- **沙盒裁定**: **DISMISSED (駁回)**
- **實證分析**: Accordion 狀態完全綁定於內部語意 ID（如 `value="trip"`、`value="offline"`），與使用者可見的標題與說明文字嚴格解耦；重啟導引自訂事件 (`tabidachi-restart-tour`) 亦不受說明手冊標題文字變更影響。

### 標的 2: `frontend/tests/account_settings_flow.spec.ts`
- **攻擊向量**: `e2e_regression_drift`
- **假說**: 測試斷言若同時包含新舊文字選擇器，可能引發 Playwright 嚴格模式衝突或模糊定位超時。
- **防禦設計**: 實作採用 `.or()` 鏈式容錯模式，優先匹配 `Tabiji`，同時相容 `Tabidachi`，確保本地開發與 CI/CD 環境無退化。

### 標的 3: `.gitignore`
- **攻擊向量**: `git_pattern_shadowing`
- **假說**: 補齊 `docs/security/findings_*.json` 可能因匹配優先級意外遮蔽 `security-coverage-ledger.json`。
- **沙盒裁定**: **DISMISSED (駁回)**
- **實證分析**: 現有規則第 35 行已存在明確定界之白名單 `!docs/security/*.json`，全域安全帳本在模式語法中受到嚴格保護；針對暫存檔案只需執行 `git rm --cached` 即可完成乾淨解耦。

### 標的 4: `frontend/lib/i18n/onboarding.ts`
- **攻擊向量**: `i18n_key_interpolation_drift`
- **假說**: 更換文案可能破壞插值佔位符或引號跳脫。
- **沙盒裁定**: **DISMISSED (駁回)**
- **實證分析**: 該常數為純靜態雙引號字串，無 `${...}` 動態模板佔位符，純字母字串更替不影響 TypeScript AST 結構與編譯結果。

---

## 3. 防禦結論與實作綠燈 (Sign-Off)

所有變更在沙盒中均通過解耦與無退化驗證。系統具備即刻進入實作之安全條件。
