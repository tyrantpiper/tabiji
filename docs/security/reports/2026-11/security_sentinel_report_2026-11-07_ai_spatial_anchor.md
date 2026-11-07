# 🛡️ Security Sentinel 6-Phase 對抗審計報告：AI 生成前空間錨定約束與生成後非破壞性座標自癒 (`ai_pre_anchor_and_healing`)

> **審計狀態**: ✅ **6-Phase 物理隔離沙盒驗證全數通過 (`17/17` Sentinel PoCs + Block G、`98/98` 全量回歸、`0` Pyrefly/TSC/ESLint Errors)**
> **隔離環境**: `GitWorktreePool` 物理沙盒 (`.worktrees/sentinel-089c0d0b` & `.worktrees/sentinel-9f720f68`)
> **候選補丁**: [`patch_candidate_ai_spatial_anchor_2026-11-07.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_ai_spatial_anchor_2026-11-07.diff)

---

## 📊 6-Phase 物理遙測總表

| 階段 | 檢查項目 | 物理指令 / 沙盒動作 | 預期結果 | 實測結果 | 狀態 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Phase 1-2** | 攻擊面探索與 9 大威脅假設建模 (`VULN-AI-ANCHOR-001`~`004` + `BLOCK-1`~`5`) | 盤點 [`ai.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py)、[`trips.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/trips.py)、[`mcp.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/mcp.py)、[`geocode_service.py`](file:///d:/Project/tabiji/travel-pwa/backend/services/geocode_service.py)、[`TripDialogs.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/TripDialogs.tsx)、[`api.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/lib/api.ts) | 識別 4 個核心向量與 5 個審計後收斂阻斷點 | 9 個假設全數定位至行號與根因 | ✅ PASS |
| **Phase 3** | **Red Gate (修補前紅隊證偽)** | 於未修補沙盒執行 `pytest tests/test_ai_spatial_anchor_sentinel.py -k "test_sentinel_poc"` | `exit_code == 1` (紅隊 PoC 必須於修補前失敗) | `exit_code == 1` (`5 failed` 初審 + `5 failed` 複審) | ✅ PASS |
| **Phase 4.1** | **Green Gate (修補後紅隊 + Block G 良性對照)** | 套用補丁後執行 `pytest tests/test_ai_spatial_anchor_sentinel.py` | `exit_code == 0` (17 項紅隊與良性對照全過) | `exit_code == 0` (`17 passed`) | ✅ PASS |
| **Phase 4.2** | **全量 AI + MCP + Geocode 回歸測試** | 執行 11 個後端測試套件與 3 個前端 Vitest 測試套件 | `exit_code == 0` (零回歸破壞) | `exit_code == 0` (`98 passed` 後端 + `22 passed` 前端) | ✅ PASS |
| **Phase 5** | **Harness^2 守恆律與帳本同步驗證** | 檢查 `confirmed + dismissed + inconclusive == total` 並產出 `.diff` | `9 + 0 + 0 == 9` | `9 confirmed == 9 total` | ✅ PASS |
| **Phase 6** | **Human Gate & `/boost` 主工作區落地** | 套用補丁至主工作區並執行全棧靜態與動態門禁 | 0 Errors, 100% 測試通過 | 已全數通過 | ✅ PASS |

---

## 🔍 漏洞假設與沙盒實證明細 (Harness^2 Conservation: 9/9 Confirmed)

### 1. `VULN-AI-ANCHOR-001`：AI 行程生成與辨識缺乏「生成前空間錨定約束 (`<spatial_anchor_constraint>`)」
- **位置**：[`backend/routers/ai.py#L271-L343`](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py#L271-L343) (`parse_markdown`)、[`backend/routers/ai.py#L514-L579`](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py#L514-L579) (`generate_trip_core`)
- **根因**：呼叫 Gemini 前未先從使用者 Prompt、Markdown 或目標 `itinerary_id` 解析目的地空間錨點，導致 LLM 在生成同名異地景點（如「龍山寺」、「東照宮」、「日本橋」）時容易輸出錯誤國家或城市的經緯度。
- **沙盒紅隊 PoC (`test_sentinel_poc_pre_generation_spatial_constraint_injected`)**：
  - **修補前 (Red Gate)**：`FAILED` — `sys_inst` 中無 `<spatial_anchor_constraint>`，無 `ISO=TW` 與台北座標邊界約束。
  - **修補後 (Green Gate)**：`PASSED` — 呼叫 Gemini 前自動注入 `<spatial_anchor_constraint>`，明確鎖定目標區域、國碼與經緯度範圍，並支援多城市 (`東京 + 大阪`) 與純圖片 CoT 內生錨定規則。

### 2. `VULN-AI-ANCHOR-002`：生成後盲信 AI 非空座標 (`if item.get("lat") and item.get("lng"): return item`) 與漏填 `daily_locations`
- **位置**：[`backend/routers/ai.py#L449`](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py#L449)、[`backend/routers/ai.py#L617`](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py#L617)
- **根因與 Chesterton's Fence（前人設計初衷）**：
  - 原工程師寫下 `if item.get("lat") and item.get("lng"): return item` 是為了**保護外部 Photon/Nominatim 免於 30 筆併發 Rate Limit / 2.5s 超時**，並**保留微觀複合地名（如「新宿東口驚安殿堂旁一蘭拉麵」）的 AI 座標**。
  - 然而當 AI 對「龍山寺」產生首爾幻覺座標 `(37.5299, 126.9645)` 時，因非空而直接放行；且 `generate_trip_core` 與 `parse_markdown` 皆未填寫 `data["daily_locations"]`，使該筆行程日後透過 MCP 增刪景點時退化至 Tier 2/3。
- **沙盒紅隊 PoC (`test_sentinel_poc_ai_generate_hallucinated_cross_country_and_homonym_healed` & `test_sentinel_poc_parse_md_hallucinated_coords_healed_while_url_coords_preserved`)**：
  - **修補前 (Red Gate)**：`FAILED` — 台北行程中的首爾龍山寺 `(37.5299, 126.9645)` 原封不動混入回傳結果，且 `daily_locations` 為空。
  - **修補後 (Green Gate)**：`PASSED` — [`verify_and_heal_itinerary_coords`](file:///d:/Project/tabiji/travel-pwa/backend/services/geocode_service.py) 偵測到首爾座標偏離台北錨點 `> 100km`（且命中同名高風險詞），自動以台北錨點重定位為 `(25.0372, 121.4999)`，同時自動建構 `daily_locations`；而 Google Maps URL 直解的座標 (`_url_verified=True`) 與距離錨點 `<= 50km` 的正常景點則維持 **0 次外部 API 呼叫**。

### 3. `VULN-AI-ANCHOR-003`：`/api/ai/parse-md` 傳入 `itinerary_id` 時之 BOLA 越權與 `HTTPException` 吞沒漏洞
- **位置**：[`backend/routers/ai.py#L271-L275`](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py#L271-L275)、[`backend/routers/ai.py#L504-L506`](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py#L504-L506)
- **根因**：支援「匯入既有行程 (`itinerary_id`)」以取得母體行程空間錨點時，若未驗證呼叫者是否為 `created_by` 或 `trip_members`，攻擊者可探測他人私人行程錨點；此外沙盒測試更抓出 `parse_markdown` 底部的 `except Exception as e:` 原本未先 `except HTTPException: raise`，會將 `403 Forbidden` 吞沒並轉為 `500`。
- **沙盒紅隊 PoC (`test_sentinel_poc_parse_md_itinerary_id_bola_blocked`)**：
  - **修補前 (Red Gate)**：`FAILED` — 未阻擋越權 `itinerary_id`。
  - **修補後 (Green Gate)**：`PASSED` — 嚴格驗證擁有者與成員資格，非授權者精準回傳 `HTTP 403`。

### 4. `VULN-AI-ANCHOR-004`：`/save-itinerary` 與 `/import-to-trip` 寫入資料庫前缺乏最後防線空間自癒
- **位置**：[`backend/routers/trips.py#L870-L905`](file:///d:/Project/tabiji/travel-pwa/backend/routers/trips.py#L870-L905) (`save_itinerary`)、[`backend/routers/trips.py#L1090-L1125`](file:///d:/Project/tabiji/travel-pwa/backend/routers/trips.py#L1090-L1125) (`import_to_trip`)
- **沙盒紅隊 PoC (`test_sentinel_poc_save_and_import_to_trip_spatial_healing`)**：
  - **修補前 (Red Gate)**：`FAILED` — 首爾座標 `(37.5299, 126.9645)` 直接寫入台北行程的 `itinerary_items`。
  - **修補後 (Green Gate)**：`PASSED` — 寫入前自動執行 [`verify_and_heal_itinerary_coords`](file:///d:/Project/tabiji/travel-pwa/backend/services/geocode_service.py)，將偏差座標修正為台北萬華龍山寺 `(25.0372, 121.4999)` 並補齊 `daily_locations`。

### 5. 全鏈路審計後收斂修復 (`BLOCK-1` ~ `BLOCK-5`)
1. **`BLOCK-1` (`test_sentinel_poc_post_audit_1_import_and_save_daily_locations_anchor_poisoning_and_partial_drop`)**：
   - 阻斷 `import_to_trip` 將未驗證之 `request.daily_locations` 提前覆寫 `existing_content` 導致的 Tier 1 空間錨點污染，並在 `verify_and_heal_itinerary_coords` 對所有 `daily_locations` 鍵值（包含未出現於 `items` 的天數）預先執行 `_in_country_or_border` 過濾（剔除越界污染座標，同時保留 `<= 80km` 非撞名跨境順遊城市如新山/霞慕尼）；並修復 `save_itinerary` 因 `request.daily_locations or resolved_save_daily_locs` 布林短路導致部分天數 `daily_locations` 遺失與越界鍵值回寫的問題，補齊 `except HTTPException: raise`。
2. **`BLOCK-2` (`test_sentinel_poc_post_audit_2_mcp_intra_country_homonym_and_batch_insert`)**：
   - 於 [`backend/routers/mcp.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/mcp.py) 的 `manage_itinerary_node` (`add` & `update`) 同步強化同國異城撞名地標守衛 (`HOMONYM_GUARD_KEYS` 偏離 `> 50km` 強制重算，一般景點 `> 180km` 強制重算)，並於 `action == "add"` 實作批次寫入 (`insert(items_to_insert)`) 與單筆回退容錯。
3. **`BLOCK-3` (`test_sentinel_poc_post_audit_3_create_item_non_empty_hallucinated_coords_healed`)**：
   - 於 `POST /api/trips/items` (`create_item`) 對非空座標一併執行 `verify_and_heal_itinerary_coords` 4 層空間錨點校驗。
4. **`BLOCK-4` (`test_sentinel_poc_post_audit_4_oauth_authorize_state_url_encoding`)**：
   - 於 `/api/oauth/authorize` 強制對 `code` 與 `state` 執行 `urllib.parse.quote(..., safe='')`，並於 `/api/oauth/token` 入口清理過期之 `CONSUMED_OAUTH_CODES`。
5. **`BLOCK-5` (`test_sentinel_poc_post_audit_5_trip_dialogs_clears_stale_daily_locations_on_merge`)**：
   - 於 [`frontend/components/itinerary/TripDialogs.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/TripDialogs.tsx) 合併至現有行程 (`saveTarget === 'existing'`) 時傳入 `daily_locations: {}`，防止預覽階段切換目標行程後殘留舊錨點。

---

## 🧪 Mantis Block G 良性對照驗證 (Passed — 確保前人設計初衷零退化)

1. **`test_benign_multi_city_tokyo_osaka_trip_preserves_both_cities` (`PASSED`)**：
   - 「東京大阪 2 日遊」（Day 1 淺草寺、晴空塔；Day 2 道頓堀、大阪城），驗證多城市 `extract_all_regions_from_text` 與按日錨點 (`day_anchors`) 不會將 Day 2 大阪景點誤判為偏離東京而覆寫。
2. **`test_benign_osm_zero_results_non_destructive_fallback` (`PASSED`)**：
   - 當某個跨國幻覺座標觸發重查、但外部 OSM/Photon 找不到該複合小店 (`return (None, None)`) 時，系統優雅退回當日錨點中心 `(25.0330, 121.5654)`，絕不洗成 `None`（避免地圖掉針）也不保留首爾幻覺座標。
3. **`test_benign_pure_image_parse_md_cot_endogenous_anchor` (`PASSED`)**：
   - 當使用者只上傳圖片 (`markdown_text=""`) 時，呼叫 Gemini 前注入 `<spatial_anchor_constraint mode="endogenous_cot">`，且 Gemini 解析出 `title: "京都賞楓行程"` 後，生成後自癒自動由 `parsed_data["title"]` 鎖定京都錨點並修正跨國偏差座標。
4. **`test_benign_valid_in_bounds_ai_coords_zero_external_geocode_calls` (`PASSED`)**：
   - 當 AI 生成的座標皆位於目標城市 `<= 50km` 合理範圍內（且非同名高風險詞）時，外部 `smart_geocode_logic` 呼叫次數嚴格為 **`0 次`**，100% 保留原工程師「零額外延遲、零 Rate Limit 風險、保留微觀複合地名座標」的設計初衷。

