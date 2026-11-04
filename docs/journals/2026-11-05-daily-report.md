# 📅 Daily Report - 2026-11-05 (Security Sentinel v2.3.0 Zero-Bloat Native Assimilation, GitWorktreePool Physical Isolation, Chesterton's Fence Code Archaeology & Autonomous Edge Simulations Convergence)

> **系統狀態**：🟢 Production Ready & Security Sentinel v2.3.0 Hardened, 0 TypeScript Errors (`tsc --noEmit`), 0 ESLint Warnings, 100% Tests Green (Backend & Sentinel Pytest: 34/34 Passed; Root Hygiene Sentinel: 4/4 Passed; Neural Seam Sentinel: 10/10 Seams Intact), Security Ledger 246 Targets (49 Remediated, 51 Verified, 146 Dismissed, 100% 數學守恆 + `known_design_intents` 歷史決策防線).
> **今日關鍵研發範疇 (Core Focus)**：
> - 🛡️ **Security Sentinel v2.3.0 三大頂尖開源神作零臃腫原生內化 (Zero-Bloat Native Assimilation: Google Mantis ✕ Cloudflare Security Audit Skill ✕ Google Research Harness², SPEC-AGY-002 v1.3.0, AD-196)**：深度拆解 `google/mantis`、`cloudflare/security-audit-skill` 與 `google-research/harness2` 核心原始碼，剔除不相容 Windows 之 POSIX `mktemp/fstat` 與高耗能 `4k` Rollout，將四大精華內化至 [`scripts/lib/adversarial_team.py`](file:///d:/Project/tabiji/travel-pwa/scripts/lib/adversarial_team.py) 與 [`.agents/skills/security-sentinel/scripts/runner.py`](file:///d:/Project/tabiji/travel-pwa/.agents/skills/security-sentinel/scripts/runner.py)：(1) **Mantis Block G 良性對照防閹割 (`test_benign*`)**；(2) **Mantis-Advise 歷史設計意圖自動注入 (`load_historical_design_intents`)**；(3) **Cloudflare Blocker & Action-Binding (`validation_blocker` / `validation_plan`)**；(4) **Harness² 台帳計數守恆斷言 (`assert_findings_conservation`)**。
> - 🔬 **雙向沙盒預演與物理對抗隔離池 (GitWorktreePool & Dual-Tier Red-vs-Blue Subagents, SPEC-AGY-002, AD-197)**：建構 [`scripts/lib/worktree_pool.py`](file:///d:/Project/tabiji/travel-pwa/scripts/lib/worktree_pool.py) 與雙層紅藍對抗機制（Tier 1 CLI Batch + Tier 2 Native Subagents `sentinel-attacker` vs `sentinel-defender`），支援開工前沙盒預演（Phase 0 Pre-Execution Worktree Spiking）與完工後先紅後綠實體驗證，跑完即刻以 `git worktree remove --force` 物理蒸發，主工作區零中繼垃圾檔殘留。
> - 🏛️ **切斯特頓圍欄三問與刪除代碼逐行考古入憲 (Chesterton's Fence 3-Question Code Archaeology & Panoramic Pre-Execution Audit, AD-198)**：於 Sentinel L0 憲法第 5 條與 [`concise-planning/SKILL.md`](file:///d:/Project/tabiji/travel-pwa/.agents/skills/concise-planning/SKILL.md) 固化「功能反推 (`legacy_function`)、設計初衷 (`design_intent`)、刪除風險 (`regression_risk`)」與「全景預先審核 (The Missing 1 Point Gate)」，完成 Source Control 全部變動檔案對比 `HEAD` (`3df81d73`) 共 48 行刪除代碼之 100% 逐行無省略考古審查。
> - 🧠 **AI 混合意圖路由抗注入加固與串流雙軌檢索閉環 (Hybrid Intent Router Hardening & E2E Lifecycle Closure, AD-199)**：修復 [`backend/services/intent_router.py`](file:///d:/Project/tabiji/travel-pwa/backend/services/intent_router.py) 長系統脈絡（>500 字）截斷 `<user_input_{salt}>` 與零寬/Bidi 隱形字元繞過漏洞；將 [`backend/main.py`](file:///d:/Project/tabiji/travel-pwa/backend/main.py) 雙軌目的地識別 `generate_dual_queries` 前移至 First-Pass 前初始化；補齊 [`backend/routers/expenses.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/expenses.py) 建立者 UUID 回退、[`ExpensePreviewCard.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/chat/ExpensePreviewCard.tsx) 連點冪等守衛與 [`chat-widget.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/chat-widget.tsx) 地圖停靠 DOM 保活。
> - 🌐 **跨會話極限邊界模擬與架構規格大合流 (Autonomous Edge Simulations & Multi-Persona Architecture Convergence, AD-200, Resolves DEBT-015)**：將並行會話之 6 大極限邊界模擬測試（[`backend/tests/test_autonomous_edge_simulations.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_autonomous_edge_simulations.py)、[`scripts/simulations/`](file:///d:/Project/tabiji/travel-pwa/scripts/simulations/simulate_edge_cases.py)）與 4 份架構規格書、5 份深度調研文獻完整驗證並收斂至主分支。

---

## 🏆 深度專案復盤：五大工程與架構里程碑 (Five Core Milestones)

---

### 里程碑一：Security Sentinel v2.3.0 三大開源神作零臃腫原生內化 (AD-196)

1. **為什麼不直接照搬外部開源腳本？**：
   - `google/mantis` 依賴 Linux `mktemp -d` 與 `cp -r` 全量複製專案目錄，在 Windows 面對含 `node_modules` 與 `.venv` 的 Next.js + FastAPI 專案會瞬間卡死 I/O；
   - `cloudflare/security-audit-skill` 之 `stream-exec.cjs` 依賴 POSIX `fstat(0)` 與 Node.js CJS 包裝，與本專案純 Python `safe_subprocess.py` 重疊；
   - `google-research/harness2` 之 `recursion.py` 採用 `4k` 指數級樹狀展開，單次審計將耗盡數十萬 Token。
2. **四大核心機制純 Python 原生內化**：
   - **Mantis Block G 良性對照防閹割 (`_split_poc_test_names` + Dual-Pass Pytest)**：
     - 於 [`scripts/lib/adversarial_team.py`](file:///d:/Project/tabiji/travel-pwa/scripts/lib/adversarial_team.py#L89-L101) 自動解析 PoC 腳本中之攻擊測試與良性對照測試 (`test_benign*`)。
     - **紅燈階段 (Red Check)**：先以 `pytest -k "not benign"` 確認攻擊測試真正觸發 `AssertionError` (`returncode == 1`)，防止攻擊測試通過但良性測試寫錯導致的「假紅燈 (False Red Confirmation)」。
     - **綠燈階段 (Green Check)**：套用 `block_replacement` 後全量執行攻擊與良性測試；若補丁透過直接 `return 0` 或 `return None` 閹割正常業務功能，良性對照測試即刻失敗，自動阻斷補丁 (`benign_control_passed = False`) 並還原原始檔案位元組。
   - **Mantis-Advise 歷史設計意圖自動注入 (`load_historical_design_intents`)**：
     - 於 [`runner.py`](file:///d:/Project/tabiji/travel-pwa/.agents/skills/security-sentinel/scripts/runner.py#L114-L149) 自動讀取 [`docs/security/security-coverage-ledger.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/security-coverage-ledger.json) 頂層 `known_design_intents` 與歷史 `DISMISSED` 紀錄，防禦性注入 Validator Prompt，避免藍軍重複爭論已確認之架構設計（如 `expenses.py` SSOT 動態聚合、`chat-widget.tsx` 行程切換重置對話、`main.py` 二階段工具卸載）。
   - **Cloudflare Blocker & Action-Binding (`validation_blocker` & `validation_plan`)**：
     - 強制規範涉及外部部署環境或無法於單機記憶體證偽之假說必須標記為 `INCONCLUSIVE`，並輸出明確之阻斷前提 (`validation_blocker`) 與後續驗證計畫 (`validation_plan`)。
   - **Harness² 台帳計數守恆斷言 (`assert_findings_conservation`)**：
     - 於 `runner.py` 輸出前強制檢驗 `confirmed_count + dismissed_count + inconclusive_count == total_validated == len(findings)`，任何狀態漂移立即觸發 `AssertionError`。

---

### 里程碑二：GitWorktreePool 雙向沙盒預演與無痕物理蒸發 (AD-197)

1. **解決跨會話碰撞與中繼垃圾檔氾濫**：
   - 過去每次執行資安審計或 PoC 測試，需在主目錄落地 `candidates_*.json`、`patch_candidate_*.diff` 或臨時 `test_*_poc.py`，導致 VS Code Source Control 頻繁出現大量中繼檔案。
2. **Worktree 隔離池與 In-Memory 閉環**：
   - [`scripts/lib/worktree_pool.py`](file:///d:/Project/tabiji/travel-pwa/scripts/lib/worktree_pool.py) 透過 `_GIT_WORKTREE_LOCK` (`asyncio.Lock`) 調度 `git worktree add --detach .worktrees/sentinel-<uuid> HEAD`，並將主工作區未提交之 dirty 檔案鏡像同步至沙盒（雙向執行 `Path.is_relative_to()` 阻斷 CWE-22 同綴兄弟目錄穿越）。
   - 所有臨時 PoC (`test_sentinel_poc_<uuid>.py`) 與補丁套用皆於 `.worktrees/` 內透過記憶體字典直傳驗證；結束後於 `finally` 區塊執行 3 次指數退避 `git worktree remove --force` 物理銷毀（若遇 Windows 句柄佔用則寫入 `.pending_prune` 自癒佇列），主工作區維持 **0 中繼檔污染**。
   - 支援 **Phase 0 開工前沙盒預演 (Pre-Execution Worktree Spiking)**：在動手修改生產環境代碼前，先於獨立 Worktree 完成原型植入與 34 項全量測試驗證，達成開工前 10/10 確定性。

---

### 里程碑三：切斯特頓圍欄三問入憲與 Git HEAD 48 行刪除代碼逐行考古 (AD-198)

1. **切斯特頓圍欄三問 (Chesterton's Fence Protocol)**：
   - 任何提議刪除或修改既有邏輯之審查與補丁，必須強制回答三問並寫入 `code_archaeology` 欄位：
     1. **功能反推 (`legacy_function`)**：被刪除代碼在舊系統扮演什麼具體功能？
     2. **設計初衷 (`design_intent`)**：當初工程師為何這樣設計？解決了什麼業務痛點或 Corner Case？
     3. **刪除風險 (`regression_risk`)**：刪除後是否破壞未明寫的隱藏依賴？新代碼如何 100% 承接？
2. **Source Control 變動檔案刪除考古與 CRLF 假性刪除根除**：
   - 排查並修復 Windows 下因腳本寫入 `LF` 或 `open(..., newline='\r\n')` 疊加 `\r\n` 產生尾部 `\r\r\n`（導致 Git 判定為 `w/-text` 二進位檔而停用 `autocrlf`，引發 3,000+ 行假性整檔刪除）之陷阱。
   - 完成 12 個 Modified 檔案對比 `HEAD` (`3df81d73`) 共 **48 行真實刪除代碼**之逐行無省略考古核對，證明 100% 皆由強化後之新邏輯完整承接，零功能降級。

---

### 里程碑四：AI 混合意圖路由抗注入加固與前後端 E2E 閉環 (AD-199)

1. **`backend/services/intent_router.py` 兩大P1資安漏洞修復**：
   - **漏洞 1（長脈絡先截斷後提取標籤）**：舊版 `_fast_path_classify` 先執行 `message.strip()[:500]` 再搜尋 `<user_input_{salt}>`；當系統注入之行程與記憶脈絡超過 500 字時，真實使用者輸入被完全切掉，且脈絡中之「預算/花費」字眼會誤觸 `EXPENSE` 意圖。修復後由 `_extract_clean_user_text` 先跨越 `SYSTEM_BOUNDARY_END_RE` 提取同名 `outer_salt` 標籤並校驗 `_is_valid_outer_trailing` 後綴白名單，最後才執行 500 字元截斷。
   - **漏洞 2（零寬與 Bidi 控制字元繞過正則）**：新增 `INVISIBLE_CHARS_RE` 全面剝除 `\u200b-\u200f`、`\u202a-\u202e`、`\u2060-\u206f`、`\ufeff` 及 ASCII 控制字元，同步應用於 `main.py:detect_admin_hijack_attempt`（結合 `NFKC` 正規化）。
2. **`backend/main.py`、`expenses.py`、`chat-widget.tsx` 與 `ExpensePreviewCard.tsx` 閉環修復**：
   - 將 `main.py` 串流 `SEARCH` 分支之 `generate_dual_queries` 前移至 First-Pass `try` 區塊前（`L1240-L1245`），根除 First-Pass 呼叫 `search_nearby_places` 時讀取 `dest_name` 之 `UnboundLocalError` 並讓 `trip_city` 獲得真實目的地名稱。
   - `expenses.py:L254` 補齊 `"created_by": request.created_by or user_id`，防止 AI 記帳卡寫入 `created_by = NULL` 導致使用者無法刪除該筆消費。
   - `ExpensePreviewCard.tsx:L59` 新增 `if (isAdding || isAdded) return` 同步冪等守衛，阻斷連點重複扣款。
   - `chat-widget.tsx:L881-L926` 將 `isDocked` 三元條件渲染改為並存渲染並以 `hidden pointer-events-none` 隱藏主對話框，避免開啟地圖抽屜時卸載聊天元件導致 SSE 串流斷線。

---

### 里程碑五：極限邊界自主模擬與多形態架構規格大合流 (AD-200, Resolves DEBT-015)

1. **6 大極限邊界模擬 (`backend/tests/test_autonomous_edge_simulations.py`) 100% 通過**：
   - **TC-1 & TC-2**：夏令時間 (DST) 跳躍與跨太平洋航班時區偏移 (`scripts/simulations/simulate_edge_cases.py`)；
   - **TC-3**：跨國際換日線 (Antimeridian $\pm 180^\circ$) 航線插值與 `[0, 360]` 連續域最小包絡框 (`calculate_antimeridian_bbox`，空陣列安全防護)；
   - **TC-4**：離線 Outbox 臨時 ID 級聯替換（依長度降冪排序 + `(?![0-9A-Za-z_-])` 邊界正則，防 `temp_1` 誤改 `temp_10`）；
   - **TC-5**：資安 Fuzzing 與 SQL/Prompt Injection 免疫驗證；
   - **TC-6**：離線緊急醫療哨兵 (`scripts/simulations/simulate_emergency_medical.py`)，以 `_match_emergency_keyword` 拉丁字母邊界正則防止 `"er"` 誤判 `"Uber"` / `"Burger"`，並支援中/英/日三語急救卡生成。
2. **單一源多形態規格 (`single-origin-multi-persona-spec.md`) 隱私強化**：
   - 切換離開 `'medical'` 模式時自動將 `isMedicalUnlocked` 鎖回 `false`，並於 Zustand `persist` 以 `partialize` 排除 `isMedicalUnlocked` 落盤，嚴格落實醫療隱私零持久化。

---

## 🏛️ 架構決策紀錄 (Architecture Decision Records)

- **AD-196 (Zero-Bloat Native Assimilation of Mantis, Cloudflare & Harness² - SPEC-AGY-002 v1.3.0)**:
  - **Context**: 評估 `google/mantis`、`cloudflare/security-audit-skill` 與 `google-research/harness2` 三大倉庫時，若直接引入其 Linux Shell / Node CJS / `4k` Rollout 腳本，將導致 Windows I/O 卡死、雙語執行緒重複與 Token 暴增。
  - **Decision**: 採取「零臃腫原生內化」策略，以純 Python 於 `adversarial_team.py` 與 `runner.py` 實作 Mantis Block G 良性對照防閹割、Mantis-Advise 歷史意圖載入、Cloudflare Blocker 欄位契約與 Harness² 台帳計數守恆斷言。
  - **Trade-offs**: 需維護自研 `_split_poc_test_names` 與雙階段 `pytest -k` 篩選邏輯，但換取 0 外部依賴、100% Windows 相容與毫秒級執行效能。
- **AD-197 (Bi-Directional GitWorktreePool & Dual-Tier Native Subagent Confrontation)**:
  - **Context**: 傳統資安審查在主工作區產生大量中繼檔，且缺乏開工前沙盒預演能力；同時 Antigravity IDE v2.6.0 開放原生 `define_subagent` / `invoke_subagent` 非同步子代理協同。
  - **Decision**: 建立 `GitWorktreePool` (`.worktrees/sentinel-<uuid>`) 搭配雙層對抗架構（Tier 1 CLI `runner.py` 批次快篩 + Tier 2 IDE 原生 `sentinel-attacker` vs `sentinel-defender` 紅藍對抗），並將子代理定義固化於 `.agents/agents/` 與 `~/.gemini/config/agents/`；跑完即刻物理銷毀 Worktree。
  - **Trade-offs**: 首次建立 Worktree 需約 0.8~1.5 秒 Git Checkout I/O，透過 `_GIT_WORKTREE_LOCK` 與僅針對 High/Critical 或開工前 Spiking 啟用，達成速度與隔離性的最佳平衡。
- **AD-198 (Chesterton's Fence 3-Question Code Archaeology & Panoramic Pre-Execution Gate)**:
  - **Context**: AI 審查或重構時容易將系統刻意設計（如 SSOT 動態計算總金額、切換行程重置 AI 對話、二階段卸載搜尋工具）誤判為 Bug 或在重構中暗中刪除防禦邏輯。
  - **Decision**: 將「切斯特頓圍欄三問 (`legacy_function`, `design_intent`, `regression_risk`)」寫入 Sentinel L0 憲法第 5 條與 JSON Schema，並於 `concise-planning` 加入三維度全景預先審核（邏輯一致性、遺漏邊界、The Missing 1 Point 10/10 評分閘口）。
  - **Trade-offs**: 每次刪除或行為變更皆須產出結構化考古證據，增加審查嚴謹度成本，但徹底杜絕靜默功能退化（Silent Regression）。
- **AD-199 (Tag-First Extraction & Invisible Character Sanitization in Hybrid Intent Router)**:
  - **Context**: 當聊天訊息附帶超過 500 字元的系統行程脈絡時，先切片再抓 `<user_input_{salt}>` 會導致使用者真實輸入遺失；且零寬字元 (`\u200b`) 與 Bidi 控制碼可拆散關鍵字繞過正則快篩與管理員守衛。
  - **Decision**: 統一由 `_extract_clean_user_text` 先執行 `INVISIBLE_CHARS_RE` 清洗、跨越 `SYSTEM_BOUNDARY_END_RE` 匹配同名 `outer_salt` 閉合標籤與 `_is_valid_outer_trailing` 後綴白名單，最後才截斷至 500 字元。
  - **Trade-offs**: 正則提取需掃描原始字串尋找標籤邊界，但透過單次編譯正則將耗時控制在 `<0.2ms`。
- **AD-200 (Cross-Session Autonomous Edge Simulations & Multi-Persona Spec Convergence)**:
  - **Context**: 並行會話產出之跨換日線空間幾何、離線多主 Outbox ID 收斂、離線急救醫療哨兵與單一源多形態規格（原 `DEBT-015`）需經嚴格除錯與考古審查後方可合流。
  - **Decision**: 修復換日線 `[0, 360]` 連續域包絡框、Outbox `tempId` 降冪邊界替換、急救關鍵字拉丁字母邊界正則與醫療解鎖狀態 `partialize` 排除落盤，並通過全量自動化測試後正式併入主分支。
  - **Trade-offs**: 無，全面清償跨會話未合流技術債。

---

## 🔴 技術債務追蹤 (Technical Debt)

- **DEBT-015**: `[RESOLVED in HEAD]` 並行會話位於 `docs/specs/architecture/` 之 3 份極限架構規格（反子午線空間引擎、離線醫療哨兵、離線多主聚合收件匣）及對應模擬測試套件已完成邊界修復、切斯特頓圍欄考古與 34/34 Pytest 驗證，正式合流至主分支。

---

## 🛡️ 今日踩坑與失敗路徑紀錄 (Failed Paths)

- **FP-33: `Path.startswith` 前綴比對引發 CWE-22 同綴兄弟目錄穿越漏洞**
  - **Symptom**: 在 `worktree_pool.py` 與 `adversarial_team.py` 中使用 `str(dst).startswith(str(wt_path.resolve()))` 校驗路徑時，若傳入 `../sentinel-1234_evil/pwn.py`，因其字串前綴與 `sentinel-1234` 相同而繞過檢查，允許覆寫隔離池外之兄弟目錄檔案。
  - **Lesson**: Python 路徑邊界防禦嚴禁使用字串 `.startswith()`；必須一律使用 `Path.resolve().is_relative_to(root.resolve())`，並同時對 `src` 與 `dst` 進行雙向邊界驗證。
- **FP-34: PoC 同時包含攻擊測試與良性測試時，良性測試寫錯引發「假紅燈 (False Red Confirmation)」**
  - **Symptom**: 導入 Mantis Block G 良性對照時，若直接全量執行 `poc_script`，當目標代碼原本安全（攻擊測試通過 `returncode == 0`），但良性測試本身斷言寫錯失敗（`returncode == 1`），會被誤判為漏洞擊穿 (`RED_CONFIRMED`)。
  - **Lesson**: 物理沙盒紅燈驗證必須先透過 `_split_poc_test_names` 拆分測試函數，紅燈階段強制執行 `pytest -k "not benign"` 僅驗證攻擊測試本身是否擊穿防禦。
- **FP-35: Detached Worktree 未鏡像 Untracked 依賴檔案導致沙盒內 `FileNotFoundError`**
  - **Symptom**: `git worktree add --detach HEAD` 僅簽出已提交至 Git Index 之檔案；當主工作區新增尚未 commit 之模組（如 `.agents/.../safe_subprocess.py` 或新測試檔）時，沙盒內測試因找不到檔案而失敗。
  - **Lesson**: 在 Dirty Working Tree 執行 Pre-Execution Worktree Spiking 時，必須將相關聯之未追蹤 (`??`) 與已修改 (`M`) 檔案一併列入 `GitWorktreePool.acquire(mirror_files=[...])` 進行跨工作區鏡像。
- **FP-36: Windows 下 Python `open(..., newline='\r\n')` 搭配 `f.write('\r\n')` 產生 `\r\r\n` 導致 Git 誤判為 Binary (`w/-text`)**
  - **Symptom**: 在 Windows 使用 `open(path, 'w', newline='\r\n')` 寫入 JSON 並於結尾呼叫 `f.write('\r\n')` 時，Python 會將字串中的 `\n` 再次轉為 `\r\n`，產生 `\r\r\n`（孤立 `\r`）。Git 因此將該檔案標記為 `w/-text`（非純文字），停用 `core.autocrlf`，導致 `git diff` 將整份 3,100 行檔案全部標示為紅字刪除。
  - **Lesson**: Windows 下欲精確控制 `CRLF` 行尾，應統一以 `raw.replace(b'\r\r\n', b'\r\n').replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')` 二進位寫入 (`write_bytes`)，並以 `git ls-files --eol` 確認為 `w/crlf`。

---

## 🎯 明日核心衝刺目標 (Next Steps)

1. **自動化雲端 CI/CD 遙測驗收**：監控本次 32 個檔案推送至 `main` 後 GitHub Actions 全棧測試管線之執行表現。
2. **Service Worker 離線地圖瓦片快取實裝**：落地 Esri World Imagery / OSM 瓦片 LRU 快取機制（50MB 配額上限）。
3. **跨國時區與醫療哨兵前端 UI 對接**：將已驗證之 `simulate_emergency_medical.py` 與 `single-origin-multi-persona-spec.md` 對接至前端醫療模式面板。

---

## 🧬 Machine-Executable Invariant Rules
```json
[
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-DEVOPS-025",
    "title": "Mantis Block G Benign Control & Dual-Stage Pytest Disambiguation (AD-196)",
    "content": "When verifying security PoCs and patches in GitWorktreePool, exploit tests and benign control tests (test_benign*) must be split via _split_poc_test_names. Red verification must run pytest -k 'not benign' to prevent broken benign assertions from triggering False Red Confirmation; Green verification must pass both exploit and benign tests, automatically rejecting and rolling back any lobotomized patch that breaks benign functionality."
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-DEVOPS-026",
    "title": "Mantis-Advise Historical Design Intent Pre-Ingestion & Harness2 Conservation (AD-196)",
    "content": "Security Sentinel runner.py must automatically load known_design_intents and historical DISMISSED targets from docs/security/security-coverage-ledger.json into validator prompts to prevent relitigating intentional architecture (e.g. SSOT dynamic expense aggregation, trip-switch chat reset, 2nd-pass tool unloading), and must enforce assert_findings_conservation (confirmed + dismissed + inconclusive == total_validated == len(findings)) before output."
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-DEVOPS-027",
    "title": "Chesterton's Fence 3-Question Code Archaeology & Bidirectional Path.is_relative_to Guard (AD-197, AD-198)",
    "content": "Every finding or patch deleting or altering existing code must populate code_archaeology (legacy_function, design_intent, regression_risk). All worktree file mirroring and block replacements must validate both source and destination paths using Path.resolve().is_relative_to(root.resolve()), strictly forbidding string .startswith() to prevent CWE-22 sibling prefix traversal."
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BACKEND-019",
    "title": "Tag-First Extraction & Invisible Character Stripping Before Length Truncation (AD-199)",
    "content": "In hybrid intent routing and admin hijack guardrails, user input wrapped in <user_input_{salt}> must first strip zero-width/Bidi control characters (INVISIBLE_CHARS_RE), advance past SYSTEM_BOUNDARY_END_RE, and extract content matching the exact closing outer_salt tag with trailing whitelist validation BEFORE applying 500-character ReDoS truncation."
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-063",
    "title": "Windows Python newline='\\r\\n' Double Carriage Return (\\r\\r\\n) Binary Classification Trap (FP-36)",
    "content": "Passing newline='\\r\\n' to open() while writing '\\r\\n' translates '\\n' into '\\r\\n', producing '\\r\\r\\n' (lone CR). Git classifies files containing lone CR as w/-text (binary), disabling core.autocrlf and causing git diff to flag the entire file as deleted. Always normalize CRLF via raw bytes: raw.replace(b'\\r\\r\\n', b'\\r\\n').replace(b'\\r\\n', b'\\n').replace(b'\\n', b'\\r\\n')."
  },
  {
    "domain": "devops_security",
    "type": "TECHNICAL_DEBT_RESOLUTION",
    "id": "DEBT-015",
    "title": "Cross-Session Autonomous Edge Simulations & Architecture Specs Convergence",
    "content": "Resolved and converged 3 architecture specs (antimeridian spatial engine, offline emergency medical sentinel, offline outbox multi-master convergence) and 6 autonomous edge simulation tests into main.",
    "status": "RESOLVED"
  }
]
```

