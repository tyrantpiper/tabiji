---
name: "PWA Idea to Spec"
description: "[Tabidachi PWA 專屬 2.1] Transforms conversational user requests into rigorous Travel-PWA engineering specifications (Supabase RLS, Cloudflare Edge 50ms, Double-Checked Healing, MapLibre/WebGL). Supports Fast-Track and Deep-DAG execution modes."
version: "2.1.0"
triggers:
  - "/pwa-spec"
  - "/spec"
  - "/grill-me"
  - "PWA規格化"
  - "規格化"
  - "需求梳理"
  - "設計規格"
---

# PWA Idea to Spec 2.1 (Tabidachi Dual-Track Spec Engine)

## Purpose
Bridge the gap between raw user ideas and deterministic implementation. Eliminates Vibe Coding, prevents context degradation into the "Dumb Zone", and produces an ambiguity-free, production-ready `Mini Design Doc` before any production code is written.

---

## 🔀 雙軌執行路由 (Execution Mode Routing)

在執行開始時，依據使用者指令或任務複雜度自動切換：
- **軌道 A: Fast-Track (輕量單輪模式 - 保留原始優勢)**
  - **觸發條件**: 單純 `/spec`、改動範圍限於單一檔案、或使用者明確要求快速產出草稿。
  - **核心行為**: 不進行多輪盤問，以本地程式碼為事實來源，直接合成 5 段式標準規格。
- **軌道 B: Deep-DAG (深度架構模式 - 啟動 DAG 局部循環)**
  - **觸發條件**: `/grill-me`、`/spec --deep`、或改動跨越 2 個以上微服務/架構邊界。
  - **核心行為**: 依序執行下方完整 5 節點 DAG 排程。

---

## 🧭 Phase 1: Pre-flight Grounding & External Radar (地質探勘)

Before initiating inquiries or generating specifications:
1. **Facts First (Codebase Grounding)**: Read relevant schemas, store files, and route handlers. If a fact exists in code, never ask the user.
2. **NotebookLM Retrieval**: 定向檢索歷史決策與架構踩坑經驗（嚴禁使用 `all=true`，採用標籤過濾）：
   ```json
   call_mcp_tool("notebooklm", "cross_notebook_query", {
     "tags": "tabidachi,architecture",
     "query": "<具體功能模組之歷史限制與設計邊界>"
   })
   ```
3. **External Intelligence Radar (GitHub / Context7)**:
   - 檢索目標套件最新 RFC 與已知地雷。
   - **Circuit Breaker (5 秒熔斷器)**: 若外部 MCP 工具回應延遲超過 5 秒或遭遇 Rate Limit，立即放棄外部檢索，靜默降級為「純本地 Codebase 靜態探勘」，絕不中斷 DAG 推進。

---

## 🎙️ Phase 2: Adaptive Socratic Interview (`/grill-me`)

Follow the Hierarchical Elenchus protocol:
1. **Single Question at a Time**: Ask exactly one question per turn using `ask_question`.
2. **Always Provide Recommended Answer**: State the architectural recommendation prefixed with `(Recommended)` and provide the trade-off rationale.
3. **Strict Hierarchy (階梯式分層)**:
   - **L1 (Intent & Non-Goals)**: 核心痛點、非目標（本次絕不做什麼）、衡量指標。
   - **L2 (Boundaries & Contracts)**: 資料流向、RSC 邊界、API 介面、Supabase RLS 矩陣。
   - **L3 (Failure Budgets & Edges)**: Cloudflare Worker 限制、離線自癒衝突解決、網路超時重試策略。
   *Rule: Never ask L2/L3 questions before L1 consensus is achieved.*
4. **Fidelity Matching & Sandbox Isolation**:
   - **Low-Fidelity**: 業務邏輯、資料型態 ➔ 直接於對話中敲定。
   - **High-Fidelity**: UI 視覺反饋、手勢微動效 ➔ 暫停文字辯論，於 `<conversation_dir>/scratch/proto/` 產出獨立預覽檔案，待使用者確認視覺後立即回填結論並清除臨時檔案。嚴禁目錄穿越 (`../`)。
5. **Escape Hatch (短路逃生艙)**:
   - 若使用者回覆「照推薦執行」、「直接出規格」或連續 2 題選擇推薦項，立即終止盤問循環，自動承接現有決策並將未解分支標記為 `[DEFERRED_TO_DEV]`，直接進入 Phase 3。

---

## 📋 Phase 3: Industrial Mini Design Doc Schema (7 大模組)

Whenever generating the specification artifact, output the following structure into `implementation_plan.md` (stored strictly in the artifact directory, never raw in root):

### 1. 核心意圖、指標與非目標 (Problem, Metrics & Non-Goals)
- **Problem Statement**: 解決何種具體場景痛點？
- **Success Metrics (SLO)**: 可量化指標（如首屏延遲 < 1.2s、離線可用度 99.9%）。
- **⚠️ Non-Goals (非目標)**: 明確定義本次開發**絕對不涉及**的範圍。

### 2. 被否決方案與權衡矩陣 (Alternatives & Trade-offs)
| 方案選項 | 優點 | 致命缺點/代價 | 決策結果 |
| :--- | :--- | :--- | :--- |
| A. [選定方案] | 符合 Local-First 且具備離線快取 | 需處理雙向同步衝突 | **ADOPTED** |
| B. [替代方案] | 實作簡單 | 依賴即時網路，違反 PWA 離線核心憲法 | **REJECTED** |

### 3. 組件拓撲與 RSC 邊界 (Architecture & Component Topology)
- **Server Component (RSC)**: 負責無狀態資料擷取、快取控制與金鑰隔離。
- **Client Component (`'use client'`)**: 僅限於手勢操作、DOM 動畫與 WebGL/MapLibre Canvas。
- **Mermaid Sequence Diagram**: 跨端/跨服務完整呼叫序向圖。

### 4. 資料模型與安全矩陣 (Data Contract & Security Matrix)
- **Supabase DDL & RLS 矩陣**:
  | 資料表 (Table) | 角色 (Role) | 讀取 (SELECT) | 寫入 (INSERT/UPDATE) | 策略邏輯 (RLS Policy) |
  | :--- | :--- | :--- | :--- | :--- |
  | `trips` | `authenticated` | 僅本人 | 僅本人且非封存狀態 | `auth.uid() = user_id` |
- **FastAPI Pydantic / Zod Schemas**: 具體 Request/Response 強型別合約。

### 5. 邊緣與離線故障模型 (Edge & Offline Failure Budget)
- **Cloudflare Edge 限制**: CPU 執行時間（< 50ms）、Subrequest 限制與快取分流策略。
- **離線自癒機制 (Double-Checked Healing)**: 斷網重連後的衝突仲裁（LWW 或是三向合併）。

### 6. 有限狀態機 (FSM) 與狀態轉移 (State Machine & SWR)
- **狀態轉換圖**: `IDLE` ➔ `FETCHING` ➔ `MUTATING (Optimistic)` ➔ `SYNCED` / `ROLLBACK`。

### 7. 可執行驗收標準 (Executable Acceptance Criteria)
- [ ] **AC-PBT-1 (屬性守恆)**: 針對任何合法的 CJK 字元與時區偏移，序列化後的時間差恒為 0。
- [ ] **AC-Edge-2 (邊界隔離)**: 當 Supabase 斷線回傳 503 時，系統必須在 50ms 內平滑降級至 IndexedDB 快取。

---

## 🛡️ Phase 4: Pre-Approval Adversarial Review (紅軍審查循環)

在呈現給人類簽核前，規格草稿必須在內部通過以下驗證：
1. **RLS 完整性**：所有涉及的 Table 均明確標記 RLS Policy。
2. **Edge 故障預算**：無違反 Cloudflare 50ms CPU 或 D1 序列化寫入之設計。
3. **可執行 AC**：驗收標準包含至少 1 項 Property-Based Testing (屬性守恆) 與狀態機轉移清單。
*最多允許自我修正 2 次。若仍未通過，標註警告清單交由人類裁決。*

---

## 🚀 Phase 5: Human Confirmation Gate & Tracer-Bullet Handoff

1. **Approval Gate (絕對人類主權門禁)**:
   - 產出之 `implementation_plan.md` 嚴禁裸存於根目錄，必須存於工件目錄。
   - 阻斷執行，等待人類明確同意後方可進入實作。
   - **絕對守衛**：無論是 Fast-Track 或 Deep-DAG，未獲人類核准前，嚴禁呼叫 `@dev` 或直接修改程式庫。
2. **Tracer Bullets 拆解**: 拆解為貫穿「DB ➔ API ➔ UI」的垂直切片。
3. **Maker-Checker 交棒**: 交付獨立上下文之 `@dev` 實作與唯讀 `@qa` 驗證。
