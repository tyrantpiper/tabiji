# 2026 次世代雙螺旋工程規格引擎與蘇格拉底式攝取架構深度調研 (SPEC-AGY-003)

- **文檔 ID**: `DOSSIER-AI-INTENT-2026-11-06`
- **架構標籤**: `spec-driven-development`, `dag-agent-loop`, `socratic-elenchus`, `living-executable-spec`, `harness2`
- **最後更新**: 2026-11-06
- **狀態**: `RATIFIED_IN_PRODUCTION` (v2.1.0 已實裝入庫)

---

## Executive Summary (執行摘要)

在 2026 年生成式 AI 輔助軟體工程（AI-Assisted Software Engineering）的實踐中，「憑感覺寫程式（Vibe Coding）」已被證實為導致程式庫架構熵增、AI Bloat（無用抽象層）與大規模技術債的根本毒瘤。
本調研統整 Google、Anthropic、Perplexity、Cloudflare、Vercel、Supabase 與 GitHub 頂尖社群之最佳實踐，為 Tabidachi Agent 系統確立了**「宏觀確定性 DAG ✕ 微觀有界自適應 Agent Loop」**的終局架構，並將 `/Idea to Spec` 與 `/grill-me` 升級為**次世代雙螺旋工程規格引擎 (Dual-Track Spec DAG Engine 2.1)**。

---

## 一、 根本哲學與認知起源 (Philosophical Foundations)

### 1. 概念心智模型對齊 (Brooks 哲學)
引用 Frederick P. Brooks《The Design of Design》核心命題：每個新功能背後都是一棵複雜的決策樹。
傳統開發失敗率高達 80% 的原因在於**人機波長失調（Misalignment）**。
- `/grill-me` 的本質不是做計畫，而是透過無情的追問（Relentless Questioning）達到人機共享的心智模型（Shared Mental Model）。
- **Facts vs Decisions 原則**：
  - **事實 (Facts)**：可由本地程式碼（Codebase）、資料庫 Schema 或設定檔查證者，Agent 必須自行探勘，嚴禁發問浪費人類注意力。
  - **決策 (Decisions)**：涉及業務取捨、非目標與邊界策略者，才向人類提問，並強制附帶 `(Recommended)` 最佳解以消除決策疲勞。

### 2. 精細度分流與拋棄式沙盒 (Fidelity Matching & Sandbox Protocol)
- **低精細度問題 (Low-Fidelity)**：如 API 路由、資料型別、RLS 策略，直接在對話中以文字敲定。
- **高精細度問題 (High-Fidelity)**：如 UI 畫面感受、手勢物理彈性、微動畫反饋，嚴禁在文字中進行無效的自然語言爭辯。
- **處方**：即刻分流至 `<conversation_dir>/scratch/proto/` 產出拋棄式雛形（Throwaway Code），驗證後回填決策並清除臨時檔案，嚴格遵守目錄穿越防護 (`is_relative_to`)。

### 3. 智商區間效應與工件狀態交換 (Smart Zone vs Dumb Zone)
- LLM 對話脈絡累積超過 100K Tokens 時，推理能力會出現非線性的劇烈衰減，進入「愚蠢區（Dumb Zone）」，此時生成的規格充滿表面合理的假代碼。
- **Momento / Ralph Loop 原則**：節點與節點之間**嚴禁傳遞原始對話歷史（Raw Chat History）**。上一節點的產出必須固化為確定性 Markdown/JSON 工件，下游客戶端永遠在乾淨的 **Fresh Context Window** 中啟動。

---

## 二、 臨床診療指引模型：宏觀 DAG ✕ 微觀 Agent Loop

```
           [宏觀 Deterministic DAG: 拓撲保證、狀態檢查點、硬性門禁]
                                      │
  Node 1 (Intent) ──► Node 2 [Grounding Loop] ──► Node 3 [Grill Loop] ──► Node 4 [Red-Team] ──► Gate 5 (Human) ──► Node 6 (Tracer Bullets)
                                 │  ▲                    │  ▲                    │  ▲
                                 └──┘                    └──┘                    └──┘
                              (微觀 Bounded Stochastic Loops: 具備步數上限與物理反壓熔斷)
```

以臨床醫學的 **ACLS（進階心臟救命術）** 做類比：
1. **宏觀確定性 DAG**：嚴格的處置指引流程（如心律辨識 ➔ 可電擊 vs 不可電擊 ➔ 給藥）。其拓撲結構不可隨意篡改，確保系統防線不漂移。
2. **微觀有界 Agent Loop**：特定節點內的「CPR 2 分鐘循環」。在該局部節點內，Agent 擁有高度自主探索權，可高頻自我調整，但受限於最大迭代次數（Iteration Cap）與確定性退出條件（物理測試通過或人類簽核）。

---

## 三、 頂尖巨頭工程規範映射 (Industry Benchmark)

| 組織 / 框架 | 核心精髓 (Core Practice) | 在 Tabidachi Spec Engine 中的實裝維度 |
| :--- | :--- | :--- |
| **Google** | Design Doc、Critiques、Non-Goals | **模組 1 & 2**：強制定義 `Non-Goals`（非目標，防範範圍蔓延）與 `Alternatives Considered`（被否決方案與代價矩陣）。 |
| **Anthropic** | Socratic Probing、Constitutional AI | **Phase 2 階梯質詢**：L1 概念層 ➔ L2 邊界層 ➔ L3 細節層。L1 未達成共識前，嚴禁拋出 L2/L3 問題。 |
| **Perplexity** | Proactive Grounding | **Phase 1 外部情報雷達**：主動調用 GitHub / Context7 檢索目標套件最新 RFC 與 Known Issues，帶 5 秒熔斷器。 |
| **Cloudflare** | Edge-First & Distributed Failure | **模組 5**：邊緣故障模型（Worker CPU < 50ms、D1 寫入序列化瓶頸、離線自癒機制）。 |
| **Supabase** | Schema-First & RLS Matrix | **模組 4**：資料安全矩陣（角色 × CRUD 操作 × RLS 策略邏輯）。 |
| **Vercel** | RSC Composition & Observability | **模組 3**：Server Component（資料抓取島）與 Client Component（DOM/Canvas 水合島）之拓撲邊界。 |
| **GitHub 社群** | MADR & Type-Safe Living Spec | **模組 6 & 7**：有限狀態機（FSM）轉移圖，並將 Gherkin AC 升級為基於屬性的測試 (Property-Based Testing, PBT)。 |

---

## 四、 關鍵陷阱與架構免疫抗體 (Immunity Invariants)

### 1. 門禁時序倒置陷阱 (Gate Sequence Inversion - FP-015)
- **陷阱**：若將「人類簽核門禁」置於「紅軍自動合約修補」之前，一旦紅軍在審查時自動套用 Patch 修補了 RLS 或資料模型，最終交付 `@dev` 實作的規格實質上未經人類核准，架空 L0 人類主權。
- **抗體**：紅軍修補與合約自檢必須在內部完全收斂（Green），人類簽核（Gate 5）永遠是交付實作前的絕對最後一棒。

### 2. 雙軌共存保全 (Dual-Track Retention - INV-AGY-001)
- **陷阱**：重構規格引擎若過度追求嚴謹度，強制每項輕量任務都經歷數十輪盤問，會摧毀敏捷性。
- **抗體**：
  - **Fast-Track**：保留 100% 原始單輪速成體驗，無多餘盤問，直接合成 5 段式標準規格。
  - **Deep-DAG**：面對跨模組、微服務邊界變更時啟動 5 節點深度管線。

### 3. 加密與測試衛生抗體 (INV-DEV-001 & INV-DEV-002)
- **RFC 7518 HS256 下限**：HMAC-SHA256 金鑰長度不得低於 32 位元組（256 位元），測試模擬字串嚴格遵從此規則以清零 `InsecureKeyLengthWarning`。
- **pytest-mock 生命週期純淨度**：`mocker.patch` 由 fixture 自動託管，嚴禁包入 `with` 上下文管理器，防止觸發雙重退出警告。

---

## 五、 資產沉澱與遷移驗證 (Asset Grounding Matrix)

本調研衍生之所有可執行程式碼與規格已 100% 固化至本地系統，具備完整歷史可追溯性：

1. **全域技能實裝**: `C:\Users\Ryan su\.gemini\config\skills\idea-to-spec\SKILL.md` (v2.1.0)
2. **Sentinel In-Memory PoC**: `backend/tests/test_spec_dag_sentinel_poc.py` (5 項安全斷言全數綠燈)
3. **安全台帳數學守恆**: `docs/security/security-coverage-ledger.json` (255 標的無漂移)
4. **月度安全稽核報告**: `docs/security/reports/2026-11/security_sentinel_report_2026-11-06_spec_dag_engine.md`
5. **神經領域庫直通分流**: `.agents/domains/devops_security.md` & `backend_concurrency.md` (Auto Dream 注入完畢)
6. **工程日誌**: `docs/journals/2026-11-06-daily-report.md`

---
*本檔案為 Tabidachi 架構之永久不可磨滅資產。對話上下文清空後，Agent 隨時可藉由此調研檔重構完整的心智模型。*

