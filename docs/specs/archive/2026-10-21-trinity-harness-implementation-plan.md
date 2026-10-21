# 實作計畫：御三家前沿架構融合 (Mantis ✕ Cloudflare ✕ Harness²) — Memory、Daily Report 與 Auto Dream 2.0 系統演進

## 🎯 目標概述
基於 `/Idea to Spec` 規格說明書與 `/grill-me` 訪談共識，落實 Google Mantis、Cloudflare Security Audit 與 Google Research Harness² 三大體系的深度融合：
1. **三層大腦記憶重構 (3-Tier Memory Architecture)**：
   - 將現有 608 行 (168KB) 的 `.agents/memory.md` 重構解耦；
   - 根目錄保留 <80 行頂層微核心憲法；
   - 6 大專業領域知識（地圖、快取、UI、PWA、後端、CI/CD）完整遷移至 `.agents/domains/*.md` 獨立領域庫。
2. **確定性台帳硬核門禁 (Deterministic Ledger Guard)**：
   - 建立零依賴純 Python 驗證器 `scripts/validate_security_ledger.py`；
   - 掛入 `backend/tests/test_root_hygiene_sentinel.py`，使每次 `pytest` 與 `/test` 必須強制通過台帳 Schema 與統計不變量校驗。
3. **Daily Report 2.0 雙軌輸出規範**：
   - 升級 `.agents/workflows/daily-report.md`，在維持人類高密度敘事的同時，引入 `🧬 Machine-Executable Invariant Rules` 機器可讀區塊與資安台帳增量檢查步驟。
4. **Auto Dream 2.0 經驗反射器與確定性 GC**：
   - 升級 `scripts/auto_dream.py`，解析結構化不變量，自動路由分流微創更新對應 `domains/*.md`；
   - 實作確定性 GC，自動清除已標記 `[RESOLVED]` 的技術債。

---

## 預計變更與新增檔案清單

| 檔案路徑 | 變更性質 | 變更說明 |
| :--- | :--- | :--- |
| `docs/specs/features/trinity-harness-architecture-evolution-spec.md` | 新增 | Master-Level 架構規格說明書（已完成）。 |
| `.agents/domains/map_webgl.md` | 新增 | 領域庫 1：圖形、MapLibre、WebGL、手勢與 CSP Worker。 |
| `.agents/domains/state_cache.md` | 新增 | 領域庫 2：SWR、自癒、Zustand、深層連結與路由。 |
| `.agents/domains/ios_ui.md` | 新增 | 領域庫 3：WebKit 匿名區塊、Framer Motion、Radix Portal 與微動效。 |
| `.agents/domains/offline_pwa.md` | 新增 | 領域庫 4：Service Worker、IndexedDB、快取分流與推送通知。 |
| `.agents/domains/backend_concurrency.md` | 新增 | 領域庫 5：FastAPI、Cloudflare D1、Supabase 與健康探針。 |
| `.agents/domains/devops_security.md` | 新增 | 領域庫 6：CI/CD、PowerShell 熔斷、Sentinel 攻防與台帳規範。 |
| `.agents/memory.md` | 重構 | 瘦身至 <80 行微核心憲法（Core Invariants, Domain Map, Core Vocabulary）。 |
| `scripts/validate_security_ledger.py` | 新增 | 零依賴 Python 腳本，確定性驗證 security-coverage-ledger.json。 |
| `backend/tests/test_root_hygiene_sentinel.py` | 修改 | 掛載台帳確定性驗證測試案例。 |
| `.agents/workflows/daily-report.md` | 修改 | 升級為 Daily Report 2.0 雙軌輸出與台帳檢查流程。 |
| `scripts/auto_dream.py` | 修改 | 升級為 Auto Dream 2.0 領域感知路由與確定性 GC。 |

---

## 實施步驟明細

### Step 1: 建立 6 大領域庫並重構 `.agents/memory.md`
- 建立 `.agents/domains/` 目錄。
- 將現有 608 行記憶按 6 大類別完整無損遷移至各個領域檔案。
- 將根目錄 `.agents/memory.md` 壓縮為嚴謹、超高密度的頂層微核心憲法（<80 行），定義全域鐵律、領域路由表與核心術語。

### Step 2: 建立確定性台帳守護器並掛入 Quality Gate
- 實作 `scripts/validate_security_ledger.py`：
  - 驗證鍵名唯一為 `id`，禁止 `target_id`。
  - 驗證狀態機合法性。
  - 驗證數學不變量：`total_targets == audited_targets == (verified + remediated + dismissed)`。
- 在 `backend/tests/test_root_hygiene_sentinel.py` 新增測試案例調用該驗證器。
- 執行 `pytest backend/tests/test_root_hygiene_sentinel.py` 驗收。

### Step 3: 升級 `.agents/workflows/daily-report.md` (Daily Report 2.0)
- 在資料採集階段增加「Git Diff 增量攻擊面檢查與 security-coverage-ledger 比對」。
- 在輸出規範中確立雙軌結構：維持人類敘事 + 新增 `🧬 Machine-Executable Invariant Rules` JSON 區塊。
- 在結尾掛載自動驅動 Auto Dream 2.0 經驗反射器指令。

### Step 4: 升級 `scripts/auto_dream.py` (Auto Dream 2.0)
- 支援解析日誌中的 `Machine-Executable Invariant Rules`。
- 實作領域感知路由邏輯（Domain Invariant Router），自動分流更新 `domains/<domain>.md`。
- 實作確定性 GC，自動掃描並標註/移除已解決的 Technical Debt。
- 保留安全超時防護與 Windows UTF-8 編碼支援。

### Step 5: 全棧 Quality Gate 與端到端整合驗收
- 執行 `python scripts/validate_security_ledger.py` 確保台帳守護通過。
- 執行 `python scripts/auto_dream.py --trigger "Integration Test"` 確保夢境引擎運作正常。
- 執行全套品質測試：
  - `npx vitest run`（前端 80 檔測試通過）
  - `pytest backend/tests`（後端 191+ 測試通過）
  - `npx tsc --noEmit` 與 `npm run lint`（前端 0 錯誤、0 警告）
