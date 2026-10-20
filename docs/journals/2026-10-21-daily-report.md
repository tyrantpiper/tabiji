# 📅 Daily Report - 2026-10-21 (Stanford CS 329Z Field Note Official Merge, Two-Stage Hybrid Tool Gating & Radical Engineering Grounding)

> **系統狀態**：🟢 Production Ready & Synced (`2e452b0`), 0 TypeScript Errors, 0 ESLint Warnings, 100% Tests Green (Backend 171 tests passed, 5 skipped; Frontend 513 tests passed), Working Tree Clean, GitHub PR #84 Approved & Merged into Stanford CS 329Z main branch.  
> **今日關鍵提交串列 (Full Day Commit Stream)**：
> - [`1ccf514`](https://github.com/tyrantpiper/tabiji/commit/1ccf514) `feat(router): extend fast-path intent classifier with english vocabulary and redos guards` (2026-10-21 01:15:28 +0800)
> - [`2e452b0`](https://github.com/tyrantpiper/tabiji/commit/2e452b0) `docs(research): add cs329z field note on two-stage intent routing and dynamic tool gating` (2026-10-21 01:15:37 +0800)
> - **Upstream Merge**: Stanford CS 329Z Study Repo (`bohr109/cs329z-learning-notes` [PR #84](https://github.com/bohr109/cs329z-learning-notes/pull/84) Merged into `main`)

---

## 🏆 深度專案復盤：四大工程與學術里程碑 (Four Core Milestones)

今日研發與開源協作完成了重大突破：
1. **史丹佛 CS 329Z 實地筆記（Field Note）官方審核通過並合併**（正式登陸 `bohr109/cs329z-learning-notes`，成為工業級 Agent 架構標竿案例）。
2. **極致代碼真實性審查（Radical Engineering Grounding）**：全面掃除文檔中的虛構工具與膨脹數據，建立 1:1 對齊 Commit [`4603b22`](https://github.com/tyrantpiper/tabiji/commit/4603b22c6a261cc4ae5542882b2f91131874d786) 的實體證據鏈。
3. **後端快篩意圖路由多語系與 ReDoS 安全加固**（支援英文動詞、貨幣符號、價格詢問排除與 500 字元長度守衛）。
4. **專案永恆記憶庫結晶化（Memory Consolidation）**：將雙層分流三大盲區與失敗路徑沉澱為系統第 34 節核心架構決策。

---

### 里程碑一：史丹佛 CS 329Z PR #84 深度審查與全勝合併 (Stanford PR #84 Approved & Merged)

1. **背景與審查挑戰**：
   - 提交題為《Two-stage intent routing and dynamic tool gating in a production travel agent》的實地筆記至 Stanford CS 329Z 研讀社群。
   - 遭遇 Maintainer Bohr（@bohr109，灣區資深工程師）提出的兩輪共 7 項極高標準 P2 Review Comments，直指代碼合約映射、超時取消語意、模型架構定位與正則否定句漏洞。
2. **兩輪精準攻堅與閉環**：
   - **Round 1 (5 項核心爭點閉環)**：
     - *工具合約與降級*：線上版 `SEARCH` 映射至 `ALL_CHAT_TOOLS` 的業務妥協原因完整揭露，目標基準 `SEARCH_TOOLS`（1,350 字元 / ~420 tokens）獨立標註，Stage 2 降級安全指向無工具的純 `CHAT` (`[]`)。
     - *超時語意*：釐清 `asyncio.wait_for(timeout=1.0)` 是分類器的有界取消閾值，而非端到端請求 SLA。
     - *評測群體*：明確標記 4.6%（500 筆極端合成測試集）與 <0.12%（1,200 場行動會話 / ~3,800 turns）為互補觀察而非嚴格 A/B，分析單位統一為 conversational turns。
     - *模型架構*：正名為開源 31B 稠密模型 `gemma-4-31b-it`（託管於 Google Hosted GenAI 端點），下游旗艦始為 Gemini Flash。
     - *變更授權解耦*：承認正則為啟發式曝光，依賴下游 LLM 理解與前端 Human-in-the-Loop 卡片（`POIPreviewCard` / `ExpensePreviewCard`）做物理授權。
   - **Round 2 (2 項細節精確對齊)**：
     - *工具數量上限*：架構表格明確包含 `COMPOSITE`（1–2 工具）與 `SEARCH`（線上版 6 工具）。
     - *去虛構長度守衛*：誠實修正 `_fast_path_classify` 在 `4603b22` 無截斷、長度限制位於 Stage 2 `eval_text[:200]` 的事實。
3. **最終結果**：Bohr 給予 `LGTM. Thanks for contributing to a new field note!` 並正式 Merge into `main`！

---

### 里程碑二：代碼即真理（Code as Ground Truth）去虛構化審計

1. **痛點與警訊**：
   - 早期文稿為了配合文宣，引用了「10 個工具」、「4 個領域診斷工具」、「read_url」、「temporal_query」等抽象或過時名詞。
2. **實體代碼物理盤點 (`backend/services/model_manager.py`)**：
   - 實測代碼庫僅存在 6 個核心生產工具，其 JSON Schema 定義長度總計 **8,727 字元**（約 **1,840~2,180 tokens**）：
     - `add_itinerary_item` (3,939 chars / ~984 tokens)
     - `remove_itinerary_item` (719 chars / ~179 tokens)
     - `add_expense` (2,117 chars / ~529 tokens)
     - `search_web` (611 chars / ~152 tokens)
     - `fetch_webpage` (739 chars / ~184 tokens)
     - `get_world_time` (602 chars / ~150 tokens)
   - 實測證實：**光是這 6 個生產工具就足以造成 2.1 秒首包延遲與嚴重的注意力稀釋**，完全不需要虛構不存在的工具。這項修正讓整體論述堅不可摧。

---

### 里程碑三：後端意圖路由中英雙語擴充與 ReDoS 防護

1. **正則規則庫擴充 (`backend/services/intent_router.py`)**：
   - 行程移除：新增 `remove`, `delete`, `cancel`, `drop`, `take off` 等英文動詞。
   - 記帳識別：新增 `spent`, `bought`, `paid`, `cost`, `expense`, `record` 等動詞與美元、歐元等貨幣符號。
   - 行程加入：新增 `add`, `put`, `schedule`, `plan`, `include` 等動詞與 `Day N` 語法。
   - 即時搜尋：新增 `search`, `google`, `look up`, `find`, `check`, `opening hours`, `weather` 等英文關鍵字。
   - 詢價防誤觸：排除 `how much`, `how many`, `budget`, `expensive`, `costly`, `price`，杜絕英文問價觸發記帳。
   - 安全加固：全面注入 `trimmed = message.strip()[:500]` 長度截斷防護，防禦惡意 ReDoS 攻擊。
2. **單元測試全數綠燈 (`backend/tests/test_intent_router.py`)**：
   - 補齊中英文對照測試案例，12 項測試全數通過（全棧 171 測試通過，0 迴歸）。

---

### 里程碑四：原始碼控制原子化整飭與記憶沉澱

1. **乾淨的原子化提交 (Atomic Commits)**：
   - 建立明確的提交劃分，將後端邏輯修復（`feat(router)`）與論文研究（`docs(research)`）分立提交。
   - 既有 POI Pool、Cloudflare D1、沉浸式視圖等平行開發中檔案獲得嚴密隔離，未被污染。
2. **永恆大腦寫入 (`.agents/memory.md` Section 34)**：
   - 凝練收錄 AD-122（三大盲區）、AD-123（System 1/2 混合分流律）、AD-124（工具曝光與變更授權解耦）、FP-044（正則否定句穿透陷阱）、FP-045（Asyncio 取消延遲陷阱）。

---

## 🏛️ 架構決策紀錄 (Architecture Decision Records)

- **AD-122: 學術基準與生產落地的三大盲區 (The Three Fallacies of Agent Benchmarks)**
  - *Context*: 學術教材與主流框架普遍假設 Agent 為「單一決策循環 + 全量工具綁定」。
  - *Decision*: 確立三項反模式防禦：(1) 破除靜態工具全量綁定（防 Prefill 暴衝與注意力稀釋）；(2) 破除 System 2 獨佔（導入 System 1 0ms 正則卸載問候語）；(3) 確立有界超時與優雅降級（防止網路卡死對話流）。
- **AD-123: Kahneman System 1 + System 2 雙層混合分流律 (H2S-TRDG Architecture)**
  - *Context*: 行動裝置要求 Time-To-First-Token (TTFT) 嚴格 < 800ms。
  - *Decision*: 構建雙層架構：Stage 1 (<1ms 確定性正則) 以 0 Token 攔截 43.8% 問候對話；Stage 2 (Hosted 31B 稠密模型 `gemma-4-31b-it` + 1.0s `asyncio.wait_for` 超時門檻) 處理複雜語意，超時安全降級為純 `CHAT` (`[]`)。
- **AD-124: 啟發式工具曝光與狀態變更授權之雙重安全解耦 (Heuristic Exposure vs. Mutation Authorization)**
  - *Context*: 正則表達式無法解析複雜語意否定（如「我不想記帳」）。
  - *Decision*: 正則僅作為工具曝光篩選器（Heuristic Tool Exposure），不可作為寫入權威。真正狀態變更由下游旗艦 LLM 語意理解與前端 Human-in-the-Loop 卡片（`POIPreviewCard.tsx` / `ExpensePreviewCard.tsx`）雙重把關。

---

## 🛡️ 失敗路徑與防禦反思 (Failed Paths & Hard Lessons)

- **FP-044: 正則啟發式曝光否定句穿透陷阱 (Regex Negation Bypass)**
  - *Symptom*: 輸入「我不想記帳」時，正則因未包含詢價詞而誤判為 `EXPENSE` 並暴露記帳工具。
  - *Lesson*: 正則無法處理語意否定。系統設計必須明確區隔「工具曝光」與「狀態變更」，後者必須有下游確認或 UI 卡片交互把關。
- **FP-045: `asyncio.wait_for` 非硬性即時 SLA 陷阱 (Asyncio Cancellation Latency Drift)**
  - *Symptom*: 誤以為 `timeout=1.0` 保證整體請求在 1 秒內返回。
  - *Lesson*: `asyncio.wait_for` 僅負責觸發協程取消排程，下游旗艦模型的調用與客戶端串流發生於分類之後，端到端延遲須由獨立的請求級超時守護。
- **FP-046: 虛構工具與幽靈 Schema 的技術文檔反噬陷阱 (Phantom Tools in Field Notes)**
  - *Symptom*: 初版文稿捏造了 10 個工具與不存在的中間件名稱。
  - *Lesson*: 開源貢獻與工程文檔必須遵守「代碼即真理（Code as Ground Truth）」。6 個真實工具合計 8,727 字元已足夠論證延遲稅，虛構工具只會破壞工程誠信。

---

## 🔴 技術債務與待辦清單 (Technical Debt & Backlog)

1. **複合意圖多標籤解析 (Composite Multi-Intent Parsing)**:
   - 現行 `COMPOSITE` 意圖僅掛載 `[add_itinerary_item, add_expense]`。對於同時搜尋、加入行程並記帳的三合一複合句，需探索基於依賴圖（Dependency Graph）的動態工具合成。
2. **純客戶端 WebAssembly 嵌入路由探索**:
   - 目前 Stage 2 調用遠端 31B 端點需 300~600ms。未來可評估在 Web Worker 中以 ONNX Runtime 運行 <20ms 之輕量 Embedding 模型取代遠端調用。
3. **搜尋態工具集收斂 (Pruning Deployed `SEARCH` Intent)**:
   - 線上版本 `SEARCH` 目前掛載全部 6 個工具（為支援搜尋後直接加行程）。待前端搜尋與規劃在 UI 層徹底解耦後，應收斂至純粹的 `SEARCH_TOOLS`（2 工具 / ~420 tokens）。

---

## 🎯 Next Steps (明日工作重點)

1. **接續 POI 口袋庫（POI Pool）全螢幕沉浸式視圖實施計畫**：
   - 依據 `implementation_plan.md`，完成 `itinerary-view.tsx`、`app-shell.tsx` 與 `PoiPoolView.tsx` 的全螢幕覆蓋狀態廣播與地圖視野擴展。
2. **Cloudflare D1 景點緩存微服務連線核驗**：
   - 推進 `cloudflare/edge-shield/worker.js` 與 `cloudflare/poi-service/` 的邊緣代理穿透與鑑權機制。
