# 📅 Daily Report - 2026-11-17 (`gemini-decision-1` + `3.1-Flash-Lite` + `Gemini 4 Hydrogen` 與五大雲端密鑰/外洩盤點)

> **時間範圍**: `2026-11-17 00:00 ~ 23:59` (UTC+8；對應對話起點 `13:16:25+08:00`)
> **Git 提交狀態**: 本日 **0 筆獨立 Commit**（Stage 1 AI 變更保留於本機工作區並通過沙盒驗證，最終於 `2026-11-18` 隨 [`8e63b56`](file:///d:/Project/tabiji/travel-pwa/backend/services/intent_router.py) 一併提交；當日已落盤獨立資安稽核報告 [`security_sentinel_report_2026-11-17_ai_decision1_hydrogen.md`](file:///d:/Project/tabiji/travel-pwa/docs/security/reports/2026-11/security_sentinel_report_2026-11-17_ai_decision1_hydrogen.md) 與候補補丁 [`patch_candidate_ai_decision1_hydrogen_2026-11-17.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_ai_decision1_hydrogen_2026-11-17.diff)）。
> **當日驗證基準**: 後端 Pytest `696 passed, 5 skipped` (`93.64s`, `google-genai==3.4.0`)；前端 `tsc --noEmit` (0)、`eslint` (0)、Vitest `110 files / 1064 passed, 4 skipped`；`validate_security_ledger.py` `383` targets (`55 verified, 156 remediated, 172 dismissed`)；`neural_seam_harness.py` `10/10` Intact；本機 `@chrome` + 真實 Key 雙輪對話實測通過。

---

## 1. 工程與檔案異動清單（2026-11-17 實際研發範圍）

- **AI 雙階段路由與搜尋提煉（Stage 1，計 8 個核心異動/新增檔，後併入 `8e63b56`）**:
  - [backend/requirements.txt](file:///d:/Project/tabiji/travel-pwa/backend/requirements.txt): 升級 `google-genai>=3.4.0`。
  - [backend/utils/ai_config.py](file:///d:/Project/tabiji/travel-pwa/backend/utils/ai_config.py): 新增 Decision / Hydrogen 模型常數與能力定義。
  - [backend/services/intent_router.py](file:///d:/Project/tabiji/travel-pwa/backend/services/intent_router.py): 建立 Stage 1 Regex 0ms 短路 ➔ `gemini-decision-1`（`client.aio.decisions.create`，`v1beta` + `retry_config` 零退避，`1.8s / 2.2s` 截斷）混合漏斗。
  - [backend/services/destination_taxonomy.py](file:///d:/Project/tabiji/travel-pwa/backend/services/destination_taxonomy.py): 重構分層地理歸屬判斷、XML 定界跳脫、動態 `{current_year}` 查詢詞提煉與 `prune_and_align_citations`（CJK 3-gram 停用詞 + Wiki 離題攔截）。
  - [backend/services/smart_search_service.py](file:///d:/Project/tabiji/travel-pwa/backend/services/smart_search_service.py) 與 [backend/services/model_manager.py](file:///d:/Project/tabiji/travel-pwa/backend/services/model_manager.py): 加入 `gemini-4-hydrogen` 模型能力矩陣與參數淨化 (`sanitize_config_for_model`)。
  - [backend/main.py](file:///d:/Project/tabiji/travel-pwa/backend/main.py): 移除未引用時強制復活 `candidate_sources[:2]` 之回退，串接檢索詞提煉與 `@router` 雙輪脈絡測試驗證。
  - [backend/tests/test_decision1_query_rewrite_hydrogen.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_decision1_query_rewrite_hydrogen.py): 建立 `google-genai>=3.4.0`、Decision 1、XML 防注入、引用修剪與分層地名解析單元測試。
- **Security Sentinel 產出（2026-11-17 具名落盤檔案）**:
  - [security_sentinel_report_2026-11-17_ai_decision1_hydrogen.md](file:///d:/Project/tabiji/travel-pwa/docs/security/reports/2026-11/security_sentinel_report_2026-11-17_ai_decision1_hydrogen.md) (`5 DISMISSED`, `1 CONFIRMED` on `edge-shield`, `1 INCONCLUSIVE` on `poi-service`)
  - [candidates_ai_decision1_hydrogen_2026-11-17.json](file:///d:/Project/tabiji/travel-pwa/docs/security/history/candidates/candidates_ai_decision1_hydrogen_2026-11-17.json)、[patch_candidate_ai_decision1_hydrogen_2026-11-17.diff](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_ai_decision1_hydrogen_2026-11-17.diff)

---

## 2. 核心架構決策與雲端鑑識發現

### 🟢 Features & Fixes
- **AI 意圖分流與「世紀帝國II」偏題根治**：解決模糊追問（如「但是最新的資訊呢」）無脈絡全文送搜與未引註來源無條件復活 `candidate_sources[:2]` 的雙重污染；`@chrome` 雙輪實測（台北行程中追問札幌湯咖哩 + 後續追問「但是最新的資訊呢」）確認命中 `POST /v1beta/decisions 200`（336–478ms）➔ `gemini-3.1-flash-lite` 輸出含當年份關鍵字 ➔ 3 筆札幌湯咖哩精準來源。
- **Travelpayouts 深度研究無效請求止血（`agents.py`）**：為 `_fetch_live_pricing_context` 規劃並補上 `^[A-Z]{3}$` IATA 守衛，阻斷 `"3 Day Taipei Explorer"` 切前 3 碼 `"3 D"` 誤打 `api.travelpayouts.com` 回 HTTP 400。

### 🏛️ Architecture Decisions
- **AD-224（`Decision 1` + `Flash-Lite` + `Hydrogen` 三級免費優先混合漏斗）**：保留 0ms Regex 快路徑；模糊語意委由 `gemini-decision-1`（`v1beta`，停用 SDK 重試）分類與決定是否改寫；檢索詞提煉採用 `gemini-3.1-flash-lite` 並強制注入動態 `{current_year}`；`gemini-4-hydrogen` 置於旗艦備援與非同步任務，避免 Free Tier 12s–44s 延遲擊穿同步對話與規劃端點。
- **AD-225（身分識別、憑證與資料庫存取三權分離藍圖）**：盤點後決議將 Vercel `service_role` 外洩止血與 `2027` Supabase Legacy Keys 退役合併執行：導入 `sb_publishable_` / `sb_secret_`，並將 Cloud Run 三把系統母鑰（`VAULT_MASTER_KEY` 雙向 AES-GCM 保險庫、`RECOVERY_PEPPER` 單向 HMAC 指紋、`SESSION_SECRET_KEY` 短期 JWT 印章）自 `SUPABASE_KEY` 與公開程式碼公式徹底脫鉤（同步安裝 `gcloud CLI` v593.0.0 唯讀盤點 `antigravity-backend-00194-fh7`）。

### 🔴 Technical Debt
- **DEBT-FLIGHT-PRICING-01（Open）**：盤點確認兩條 Travelpayouts 即時機票管線雙重斷鏈：（1）[chat-widget.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/chat-widget.tsx) 呼叫 `/api/agents/research` 傳行程標題而非 IATA 代碼且未接 [airport-mapping.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/airport-mapping.ts) / [travel_data.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/travel_data.py)；（2）一般聊天走 `/api/chat/stream` 時未接上 [main.py](file:///d:/Project/tabiji/travel-pwa/backend/main.py) 的 `_build_price_context()`。本次僅以 `^[A-Z]{3}$` 阻斷 400 雜訊，功能重連留待後續排程。
- **DEBT-CLOUD-SECRET-CUTOVER-01（Created -> `[RESOLVED in 8e63b56 / be7a32c]`）**：線上 Vercel `NEXT_PUBLIC_SUPABASE_ANON_KEY` 實為 `service_role` JWT（與 Cloud Run `SUPABASE_KEY` SHA-256 指紋一致），且 Cloud Run 未掛載 `SESSION_SECRET_KEY` / `VAULT_MASTER_KEY` / `RECOVERY_PEPPER`，Cloudflare `edge-shield` 缺 `SESSION_SECRET` 且 `poi-service` 開放 `*.workers.dev`（於 2026-11-18 ~ 11-19 完成切換修復）。

### 🛡️ Failed Paths
- **FP-092（`google-genai>=3.4.0` 版本預設與 Speakeasy 自動重試陷阱）**：`google-genai 3.4.0` 將預設 API 版本由 `v1beta` 改為 `v1`、`httpx` 換為 `httpx2`；`gemini-decision-1` 必須明確強制 `v1beta` 且將 `retry_config` 設為 `strategy="none", max_retries=0`（否則內建 4 次退避會卡死 >20s）。`gemini-4-hydrogen` 拒收 `thinking_level='minimal'` 且須清除 `temperature`/`top_p`/`top_k`/`thinking_budget`。
- **FP-093（`destination_taxonomy` 字串縫合與字典序台灣優先偏誤陷阱）**：將「查詢 + 歷史 + 行程標題」縫合成單一字串再按字典序（`TW` 排 `JP` 前）比對，導致「台北出發・東京5天4夜」等標題永遠強鎖成 `tw-tzh`；必須採「當前查詢 ➔ 對話歷史 ➔ 行程標題」階層優先順序並於維基百科結果增加實體詞重疊檢查。
- **FP-094（Supabase Legacy JWT 前 110 字元相同誤貼與靜默派生信任鏈風險）**：Supabase 舊版 `anon`（208 字元）與 `service_role`（219 字元）前 110 個字元（Header + `iss`/`ref` Payload）100% 一致，極易誤貼 `service_role` 至 `NEXT_PUBLIC_*`；加之 Cloud Run 未設 `ENV=production` 與獨立密鑰時靜默從 `SUPABASE_KEY` 及公開程式碼公式派生總管密鑰，與公開 GitHub 組合形成跨庫連鎖推算風險。

### 🎯 Next Steps
- 完成 `SESSION_SECRET_KEY` / `VAULT_MASTER_KEY` / `RECOVERY_PEPPER` 與 `sb_publishable_` / `sb_secret_` 零停機切換計畫（`implementation_plan.md`），經安全網審查與使用者裁決切換策略（直接硬切換 + 重構前後端 401 攔截）後進入開發與上線。

---

## 🧬 Machine-Executable Invariant Rules

```json
[
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-092",
    "title": "google-genai 3.4+ v1 預設偏移與 Speakeasy 退避卡死陷阱 (FP-092)",
    "content": "google-genai>=3.4.0 將預設 API 版本由 v1beta 變更為 v1 並切換至 httpx2。呼叫 gemini-decision-1 (client.aio.decisions.create) 必須顯式指定 api_version='v1beta' 且停用 SDK 內建 Speakeasy 4 次指數退避 (retry_config={'strategy':'none','max_retries':0})；呼叫 gemini-4-hydrogen 必須過濾 minimal 思考等級（改用 low/medium/high/xhigh）並清空 temperature/top_p/top_k/thinking_budget，且因 Free Tier 尾延遲達 12s–44s，同步路由維持 Flash-Lite 優先。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BE-TAXONOMY-HIERARCHY-01",
    "title": "分層目的地推斷與動態年份檢索詞提煉契約 (AD-224)",
    "content": "detect_destination() 嚴禁將查詢、對話歷史與行程標題縫合成單一字串後按字典序掃描（會使『台北出發・東京5天4夜』誤鎖 TW），必須嚴格依「當前查詢 -> 近期對話歷史 -> 行程目的地」階層優先解析；gemini-3.1-flash-lite 檢索詞提煉必須經 _sanitize_xml_boundary_text() 剝除控制字元與跳脫 XML 標籤並注入動態 {current_year}，主對話同時禁止無引註時強制復活 candidate_sources[:2]。"
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-094",
    "title": "Supabase 舊制 JWT 前 110 碼相同誤貼與公開公式派生總管密鑰陷阱 (FP-094)",
    "content": "Supabase Legacy anon (208 chars) 與 service_role (219 chars) 前 110 個字元完全相同，人工複製極易將 service_role 誤貼入 Vercel NEXT_PUBLIC_SUPABASE_ANON_KEY 並經 Next.js 前端 JS bundle 公開暴露；若 Cloud Run 同時未設獨立 SESSION_SECRET_KEY / VAULT_MASTER_KEY / RECOVERY_PEPPER 與 ENV=production，公開倉庫內的預設字串與派生公式會使外洩的 SUPABASE_KEY 連環推算出 JWT 印章與保險庫密鑰。生產環境必須強制獨立注入三把隨機母鑰並採用 sb_publishable_/sb_secret_ 格式。"
  }
]
```
