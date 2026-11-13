# Security Sentinel 對抗審查報告：PWA AI 雙語管線與語言漂移防禦

> **審計編號**: `SEC-2026-11-09-PWA-AI-BILINGUAL-PIPELINE`  
> **執行模式**: Security Sentinel (Cloudflare 6-Phase Ledger ✕ Google Mantis Block G ✕ Harness² Conservation)  
> **審查日期**: 2026-11-09  
> **審查對象**: PWA AI 全管線雙語一致性 (Traditional Chinese ⇄ English)  
> **審查結論**: **5 項漏洞全數實體證實 (Red Exploit Exit Code 1) 並完成非侵入性補丁修復 (Green Exit Code 0)**，良性控制 (Benign Control) 100% 通過，全庫品質門檻零回歸。

---

## 執行摘要 (Executive Summary)

針對使用者提出的「PWA 內 AI 輸出是否有全面英文對照？切換至英文時是否全顯示英文？英文詢問能否正確調用工具？」等問題，Security Sentinel 啟動全流程對抗驗證與考古審核。

| 指標 | 數值 | 說明 |
| :--- | :--- | :--- |
| **候選假說目標** | 5 | 覆蓋 Schema、意圖路由、System Prompt、1-shot 吸引子、前端參數傳遞 |
| **實體 Red 擊穿數** | 5 (100%) | `test_pwa_ai_bilingual_sentinel_poc.py` (Exit Code 1) 確鑿證實 |
| **Mantis Block G 良性對照** | 4 (100% 通過) | 保證繁體中文既有使用者行為零降級、零破壞 |
| **修復後 Green 驗證** | 9/9 PASSED | 攻擊測資與良性測資 100% 雙雙通過 (Exit Code 0) |
| **靜態驗證 (TypeScript / Lint)** | 0 錯誤 | `tsc --noEmit` 通過，`eslint` 通過 |
| **核心不變式 (Invariants)** | 0 diff | `page.tsx`, `sw.ts`, `manifest.json` 保持物理凍結 |

---

## 攻擊面審計矩陣 (Attack Surface Matrix)

```
[前端 PWA Client]
       │
       ├── ChatWidget.tsx / TripDialogs.tsx (傳入 locale: "en")
       ▼
[Edge / Proxy 邊界]
       │
       ├── SSE Streaming (/api/chat/stream, /api/generate-trip/stream)
       ├── Synchronous API (/api/chat, /api/generate-trip)
       ▼
[後端 FastAPI 服務層]
       │
       ├── 1. Pydantic Schema: ChatRequest, SimplePromptRequest (新增 locale 欄位)
       ├── 2. 意圖路由: DIAGNOSIS_KEYWORDS (新增英文診斷詞庫)
       ├── 3. 輸入清理: extract_search_query (消除英文多餘搜尋前綴)
       ├── 4. 安全守衛: detect_admin_hijack_attempt (輸出在地化英文守衛回應)
       ├── 5. 提示詞工程: build_chat_system_instruction (動態注入英文人設與 POI 命名規則)
       └── 6. 注意力定錨: dummy_history (動態切換英文 1-shot，消除中文注意力吸引子)
```

---

## 切斯特頓圍欄三問考古 (Chesterton's Fence Archaeology)

凡涉及刪除或變更既有硬編碼行為，一律執行三問考古確認設計初衷：

| 目標位置 | 功能反推 (Legacy Function) | 設計初衷 (Design Intent) | 刪除風險與承接機制 (Regression Risk & Handover) |
| :--- | :--- | :--- | :--- |
| `backend/main.py` lines 915 & 1848 `dummy_history` | 注入單樣本定錨 (`"你好！請依照你的系統人設來協助我。"`) | 解決早期 Gemini 模型在上下文重設時的打招呼死循環與簡體中文漂移。 | 若直接移除會引發打招呼死循環；**承接機制**：依 `locale` 動態注入英文版 1-shot 定錨，同時維持破除死循環效果。 |
| `backend/routers/ai.py` line 576 `語言：全繁體中文。` | 強制 AI 行程輸出繁體中文 | 防止海外景點混合簡體或日語夾雜造成台灣使用者困惑。 | 若直接刪除會造成輸出語系不受控；**承接機制**：改為動態變數 `lang_directive`，英文環境下要求標準英文與羅馬拼音，中文環境維持既有全繁體中文。 |
| `backend/services/model_manager.py` line 453 `DIAGNOSIS_KEYWORDS` | 行程診斷快速分流比對 | 0 Token 快速攔截行程檢視問題並轉發專用診斷 Prompt。 | 原僅支援中文導致英文按鈕失效；**承接機制**：非破壞性擴充英文關鍵字清單，中文部分保持 100% 原狀。 |

---

## 實體驗證證據 (Physical Telemetry Evidence)

### 1. In-Memory PoC Red State (實體擊穿)
```
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_benign_diagnosis_intent_zh PASSED
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_exploit_diagnosis_intent_en_bypass FAILED
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_benign_admin_guardrail_zh PASSED
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_exploit_admin_guardrail_en_leakage FAILED
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_benign_search_query_zh PASSED
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_exploit_search_query_en_prefix_remains FAILED
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_benign_chat_request_default PASSED
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_exploit_chat_request_locale_contract FAILED
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_exploit_simple_prompt_request_locale_contract FAILED
=== 5 failed, 4 passed in 1.66s ===
```

### 2. In-Memory PoC Green State (補丁修復後)
```
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_benign_diagnosis_intent_zh PASSED
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_exploit_diagnosis_intent_en_bypass PASSED
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_benign_admin_guardrail_zh PASSED
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_exploit_admin_guardrail_en_leakage PASSED
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_benign_search_query_zh PASSED
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_exploit_search_query_en_prefix_remains PASSED
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_benign_chat_request_default PASSED
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_exploit_chat_request_locale_contract PASSED
backend\tests\test_pwa_ai_bilingual_sentinel_poc.py::TestPWAAIBilingualSentinel::test_exploit_simple_prompt_request_locale_contract PASSED
=== 9 passed in 1.41s ===
```

### 3. 全局回歸測試與靜態門檻
- **前端官方入口測試**: 234/234 PASSED
- **前端對抗測試**: 184/184 PASSED
- **TypeScript 型別檢查**: `tsc --noEmit` 0 errors
- **ESLint 靜態分析**: `eslint` 0 errors
- **Security Coverage Ledger 確定性守恆**: 321 targets, 100% 數學守恆通過

---

## 交付文件清單 (Artifacts Inventory)
1. **補丁候選檔**: `docs/security/history/patches/patch_candidate_pwa_ai_bilingual_pipeline_2026-11-09.diff`
2. **CRLF 韌性區塊替換表**: `docs/security/history/candidates/block_replacements_pwa_ai_bilingual_pipeline_2026-11-09.json`
3. **實體 PoC 測試檔**: `backend/tests/test_pwa_ai_bilingual_sentinel_poc.py`
4. **安全帳本原子更新**: `docs/security/security-coverage-ledger.json` (321 targets, 0 status leakage)

