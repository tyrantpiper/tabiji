# 🛡️ Security Sentinel 對抗式安全審計報告 (Geo-Agentic Grounding)

> **審計時間**: 2026-10-25T01:45:00Z  
> **審計模式**: `security-sentinel` (Cloudflare 6-Phase Ledger ✕ Google Mantis ✕ agy.exe Sandbox Validator)  
> **測試套件**: `backend/tests/test_geo_agentic_sentinel_poc.py` (5/5 PASSED)  
> **實體驗證**: `docs/security/findings_geo_agentic_2026-10-25.json` (5 Targets Verified)

---

## 1. 執行摘要 (Executive Summary)

針對使用者提出的 **AI 聊天助手整合地圖與地理空間 API（Geo-Agentic Grounding）** 全景計畫，Sentinel 建立了嚴格的「有罪推定」對抗假說矩陣，透過 `runner.py` 調度 5 個獨立沙盒驗證者與 In-Memory PoC 實測：

- **受審總目標數**: 5
- **實體駁回假說 (DISMISSED)**: 4
- **防禦性加固納入規範 (CONFIRMED / REMEDIATED IN SPEC)**: 1 (Overpass QL 注入防禦)
- **整體安全等級**: **A+ (Ready for Dev Handover)**

---

## 2. 對抗式假說驗證細項 (Confrontation Ledger)

| 目標 ID | 威脅向量 | 判定結果 | 實體驗證細節與防衛分析 |
| :--- | :--- | :---: | :--- |
| `backend/services/poi_service.py:overpass_ql_injection` | Injection | **加固納入規範** | 使用者傳入含有引號、分號語法時，若直接拼入 QL 可能導致逃逸。已由 In-Memory PoC 驗證 `sanitize_overpass_keyword`，物理剔除 `";[]()<>{}` 及換行符，消除注入風險。 |
| `backend/main.py:geo_tool_ssrf_and_null_island` | SSRF & Confusion | **DISMISSED** | 實體 Validator 確認現有代碼中 `force_config` 具備嚴格的 `allowed_function_names` 白名單。未經核准的調用會進入存根回退，無法發起惡意 SSRF 網路連線。 |
| `backend/services/intent_router.py:geo_intent_bypass` | Intent Bypass | **DISMISSED** | 實體 Validator 確認正則快篩為無狀態純函數，無可變全域記憶體與 Race Condition。雙重意圖由 `ALL_CHAT_TOOLS` 涵蓋。 |
| `frontend/components/chat/POIPreviewCard.tsx:xss_link_url` | XSS Protocol | **DISMISSED** | 現有地圖跳轉硬編碼了 `https://www.google.com/maps/` 前綴與 `encodeURIComponent`，惡意 `javascript:` / `data:` URI 無法執行。 |
| `frontend/components/itinerary/MultiDayMasterMap.tsx:maplibre_nan` | WebGL Matrix Crash | **DISMISSED** | 現有座標計算已實裝 `typeof === 'number' && !isNaN()` 邊界守衛，杜絕 WebGL 奇異矩陣反轉崩潰。 |

---

## 3. In-Memory PoC 實證記錄

已由本地獨立測試套件 `backend/tests/test_geo_agentic_sentinel_poc.py` 驗證：
```bash
backend/tests/test_geo_agentic_sentinel_poc.py::test_hypothesis_1_overpass_ql_injection_resilience PASSED [ 20%]
backend/tests/test_geo_agentic_sentinel_poc.py::test_hypothesis_2_geo_tool_ssrf_and_null_island_guard PASSED [ 40%]
backend/tests/test_geo_agentic_sentinel_poc.py::test_hypothesis_3_dual_intent_conflict_resolution PASSED [ 60%]
backend/tests/test_geo_agentic_sentinel_poc.py::test_hypothesis_4_link_url_xss_protocol_defense PASSED [ 80%]
backend/tests/test_geo_agentic_sentinel_poc.py::test_hypothesis_5_maplibre_webgl_singular_matrix_guard PASSED [100%]
============================== 5 passed in 1.03s ==============================
```

---

## 4. 候選補丁與安全規格交接 (Mantis Patch)

安全防護措施已收錄於：
- [候選安全補丁 (patch_candidate_geo_agentic_2026-10-25.diff)](file:///d:/Project/tabiji/travel-pwa/docs/security/patch_candidate_geo_agentic_2026-10-25.diff)
- [實施規格計畫書 (implementation_plan.md)](file:///C:/Users/Ryan%20su/.gemini/antigravity-ide/brain/37526a61-0ed4-47b7-8ded-2401c7da4d07/implementation_plan.md)
