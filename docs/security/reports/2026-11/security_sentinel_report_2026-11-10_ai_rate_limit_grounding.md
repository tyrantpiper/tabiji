# 🛡️ Security Sentinel 對抗安全審查報告
**主題**: AI 模型 429 速率限制崩潰、免費金鑰 Grounding 陷阱與多租戶熔斷隔離審查 (AI Rate Limit, Grounding Trap & Circuit Breaker Isolation)  
**日期**: 2026-11-10  
**稽核者**: Security Sentinel (Cloudflare ✕ Google Mantis ✕ Harness² ✕ agy CLI)  
**狀態**: REMEDIATED & VERIFIED (零降級驗證全數通過)

---

## 1. 執行總結 (Executive Summary)

- **審查目標總數**: 4
- **實體擊穿與修復確認 (CONFIRMED & REMEDIATED)**: 4
- **切斯特頓圍欄駁回 (DISMISSED)**: 0
- **良性對照 (Mantis Block G Benign Control)**: 100% 通過（確保常規聊天、精算師對話、行程產生與向後相容單元測試全數正常）
- **Harness² 守恆率**: 100% 嚴格守恆 (`373 = 56 verified + 150 remediated + 167 dismissed == len(targets)`)
- **回歸測試結果**: 592 passed, 0 failed, 5 skipped (72.19s)

---

## 2. 漏洞實體證偽與 In-Memory PoC

### Target 1: `backend/services/model_manager.py:free_api_key_grounding_trap`
- **攻擊向量**: `quota_exhaustion_and_resource_denial`
- **危害層級**: **CRITICAL** (免費金鑰呼叫旗艦模型即刻遭受 HTTP 429 RESOURCE_EXHAUSTED 拒絕)
- **實體證明 (PoC)**:
  - 測試檔案: `backend/tests/test_sentinel_ai_rate_limit_grounding.py::test_poc_free_api_key_grounding_trap`
  - 根因分析: 舊版本 `sanitize_config_for_model` 只要模型具備 `supports_grounding=True` 且意圖為 `CHAT`, `DIAGNOSIS`, `ITINERARY`, `COMPOSITE`，便強制追加 `types.Tool(google_search=..., google_maps=...)`。免費用戶金鑰欠缺 Google Maps 原生付費配額，導致正常對話與分帳一律崩潰。
  - 修復機制: 導入 `explicit_grounding` 守護，常規業務意圖全面使用乾淨業務工具，絕不盲目注入原生付費地圖。

### Target 2: `backend/services/model_manager.py:subsecond_thundering_fallback`
- **攻擊向量**: `cascading_rate_limit_collapse`
- **危害層級**: **HIGH** (0ms 級聯重試觸發 Google Cloud 專案層級突發限流器，瞬時擊落所有備援模型)
- **實體證明 (PoC)**:
  - 測試檔案: `backend/tests/test_sentinel_ai_rate_limit_grounding.py::test_poc_call_with_fallback_dual_speed_quick_retry`
  - 根因分析: `call_with_fallback` 在遭遇 429 時立即以 0ms 延遲切換至下一個模型，毫秒內連續發起 5~6 次 API 請求，直接耗盡 GCP 專案的瞬時突發限額（Sub-second Burst Limiter）。
  - 修復機制: 實施雙速重試（Dual-Speed Retry）與平滑降級抖動（Smooth Fallback Jitter）。若 `retry_delay <= 1.5s` 執行單次原地等待重試；若切換備援模型，引入 0.15s + random jitter 平滑間隔。

### Target 3: `backend/services/model_manager.py:global_circuit_breaker_pollution`
- **攻擊向量**: `cross_tenant_denial_of_service`
- **危害層級**: **HIGH** (跨租戶阻斷服務：單一用戶的 429 觸發全域 300s 熔斷，鎖死其他無辜用戶的健康金鑰)
- **實體證明 (PoC)**:
  - 測試檔案: `backend/tests/test_sentinel_ai_rate_limit_grounding.py::test_poc_circuit_breaker_api_key_isolation`
  - 根因分析: 全域變數 `_CIRCUIT_STATE` 僅以 `model_name` 為 Key，任何用戶連續觸發 3 次錯誤便全域鎖定 300s；且將短暫的 429 速率限制等同於伺服器 500 崩潰。
  - 修復機制: 熔斷鍵改以 `(hash(api_key), model_name)` 進行多租戶物理隔離；同時將 429 的冷卻時間縮減為 10~15s（預設 12s），杜絕 cross-tenant DoS。

### Target 4: `backend/services/model_manager.py:unstructured_429_metadata_blindness`
- **攻擊向量**: `fault_classification_failure`
- **危害層級**: **MEDIUM** (錯誤診斷失明，無法區分單日配額耗盡與暫態限流)
- **實體證明 (PoC)**:
  - 測試檔案: `backend/tests/test_sentinel_ai_rate_limit_grounding.py::test_poc_parse_429_metadata_with_retry_info` 與 `test_poc_parse_429_metadata_daily_quota_and_fallback_regex`
  - 根因分析: 系統僅靠字串比對，忽略 `err.details` 內 Google RPC 的 `QuotaFailure` 與 `RetryInfo` (`retryDelay`)。
  - 修復機制: 實作結構化解析器 `parse_429_metadata`，精確解析微秒/秒級 `retry_delay`、`is_daily` 與 `quota_reason`。

---

## 3. 切斯特頓圍欄考古矩陣 (Code Archaeology Matrix)

| 修改目標 | 被替換之舊代碼 (Legacy Code) | 舊設計初衷 (Original Design Intent) | 刪除/重構風險 (Regression Risk) | 100% 承接機制 (Mitigation Contract) |
| :--- | :--- | :--- | :--- | :--- |
| **`sanitize_config_for_model`** | `elif caps.family == "gemini" and caps.supports_grounding and intent_type in ["CHAT", ...]: safe.tools.append(Tool(google_maps=...))` | 2026 年初企圖讓聊天與行程規劃自動具備 Google Maps 景點地圖卡片引用能力。 | 免費金鑰因無 Google Maps 原生付費權限直接引發 HTTP 429，導致所有常規對話癱瘓。 | 引入 `explicit_grounding: bool = False` 參數。常規對話、精算師與串流全面預設使用乾淨業務工具，絕不盲目注入原生付費地圖；只有在顯式要求 `explicit_grounding=True` 時才掛載 Grounding。 |
| **`_CIRCUIT_STATE`** | `_CIRCUIT_STATE = {} # {model_name: ...}` | 集中式模型健康狀態監控，當模型宕機時保護系統不重複發送請求。 | 欠缺金鑰隔離，A 用戶超額導致 B 用戶的健康金鑰被連帶封鎖 300 秒。 | 改為 `(hash(api_key), model_name)` 複合隔離鍵，無 key 時回退 `global:{model_name}` 同步相容舊有單元測試。 |
| **`call_with_fallback` 429 處理** | 429 發生時與 500 一同呼叫 `record_model_error` 並以 0ms 切換下一模型 | 盡快尋求可用備援模型回應使用者。 | 毫秒級暴衝使 Google Cloud 專案整體限流器熔斷，全部備援模型連續陣亡。 | 導入雙速重試（Dual-Speed Retry，`retry_delay <= 1.5s` 原地單次快重試）與 0.15s 平滑抖動（Smooth Fallback Jitter），大幅降低級聯崩潰率。 |
| **`/api/ai/actuary`** | 未顯式傳入 `tools`，預設走 `CHAT` 意圖 | 簡化端點呼叫代碼。 | 繼承 CHAT 配置可能被污染注入地圖或外部工具。 | 顯式指定 `tools=[]` 與 `explicit_grounding=False`，精算師專注於確定性財務數學運算。 |

---

## 4. 候選補丁與精確區塊替換 (Block Replacement Mapping)

候選補丁已儲存至：
- `docs/security/history/patches/patch_candidate_ai_rate_limit_grounding_2026-11-10.diff`
- `docs/security/history/candidates/block_replacements_ai_rate_limit_grounding_2026-11-10.json`

---

## 5. 驗證記錄 (Verification Summary)

- **靜態型別與建置檢查**:
  - `powershell -Command "cd frontend; npx tsc --noEmit"`: **0 errors**
  - `npm --prefix frontend run build`: **Compiled successfully in 1051ms**
- **後端單元測試與安全 PoC**:
  - `pytest backend/tests/test_sentinel_ai_rate_limit_grounding.py`: **8 passed**
  - `pytest backend/tests/test_model_manager.py`: **18 passed**
  - 全套回歸測試: **592 passed, 0 failed, 5 skipped**
- **凍結核心驗證 (Frozen Core Zero Diff)**:
  - `frontend/app/page.tsx`: **0 diff**
  - `frontend/app/sw.ts`: **0 diff**
  - `frontend/public/manifest.json`: **0 diff**
  - `frontend/components/pwa-install-prompt.tsx`: **0 diff**
