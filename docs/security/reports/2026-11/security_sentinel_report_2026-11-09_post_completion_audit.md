# 🛡️ Security Sentinel 全系統完工後對抗審核報告 (Post-Completion Audit 2026-11-09)

> **審核日期**: 2026-11-09  
> **基準提交 (`HEAD`)**: `44f107f`（鏡像未提交變更與未追蹤檔案共 `297` 項進入隔離沙盒 `.worktrees/sentinel-48b4fd77`）  
> **稽核模式**: Cloudflare 6-Phase Ledger ✕ Google Mantis Block G ✕ Harness² Invariant Conservation  
> **總目標數**: `348`（本次新增 `24` 項：確認漏洞 `21` 項待人類核准套用，合理設計排除 `3` 項；台帳計數 `77 verified + 104 remediated + 167 dismissed = 348`）  
> **上線與合併判定**: **NO, NEEDS FIX / BLOCK & REFACTOR**（沙盒 18 檔補丁已通過 100% 雙端全量回歸驗證，依 L0 人類主權原則凍結實作，待人類核准 [`implementation_plan.md`](file:///C:/Users/Ryan%20su/.gemini/antigravity/brain/5dbe8200-1879-4852-be56-160d7e6f93f3/implementation_plan.md) 後方可寫入實體原始碼）

---

## 1. 執行摘要 (Executive Summary)

針對本機工作區（Source Control 含未追蹤檔案共 295+ 項變更）進行全鏈路端到端（E2E）、極端邊際條件（Edge Cases）、React 19 Compiler 純度與資安深度驗收後，判定現行實作尚存在 BOLA 越權讀取/觸發、`HTTPException` 403/404 遭外層吞併轉拋 HTTP 500、全域例外堆疊外洩、`itineraries.content` JSONB 並發 Read-Modify-Write 覆寫競態、部分建立無補償回滾（Quota 幽靈佔用）、Lie-Fi 斷線突變遺失與缺少 `Idempotency-Key` 等問題，**阻斷直接發布（BLOCK & REFACTOR）**。

本階段嚴格遵循 L0 人類主權與物理隔離規範，未修改任何線上原始碼與設定檔，僅在臨時 Git worktree 沙盒內完成「Red 對抗實證 ➔ 18 檔外科手術式補丁（`+1028 / -572`） ➔ Green 全量雙端回歸驗證」：
* **Red 階段**：良性控制 `be_benign` (`3 passed, 13 deselected`, `RC=0`) 與 `fe_benign` (`2 passed | 7 skipped`, `RC=0`) 全數通過；紅軍 PoC `be_poc` (`13 failed, 3 passed`, `RC=1`) 與 `fe_poc` (`RC=1`) 精準擊穿現行缺陷。
* **Green 階段 (6/6 Zero-Failure)**：`be_poc` (`16 passed`, `RC=0`)、`pytest` (`491 passed, 5 skipped`, `RC=0`)、`fe_poc` (`9 passed`, `RC=0`)、`tsc --noEmit` (`RC=0`)、`eslint .` (`RC=0`)、`vitest run` (`102 files / 950 passed`, `RC=0`)。
* **Artifact 輸出**：
  * 候選清單：[`candidates_post_completion_audit_2026-11-09.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/candidates/candidates_post_completion_audit_2026-11-09.json)
  * 沙盒差異補丁：[`patch_candidate_post_completion_audit_2026-11-09.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_post_completion_audit_2026-11-09.diff)
  * AST/Block 考古替換紀錄：[`block_replacements_post_completion_audit_2026-11-09.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/candidates/block_replacements_post_completion_audit_2026-11-09.json)
  * 沙盒遙測紀錄：[`sandbox_telemetry_2026-11-09.json`](file:///C:/Users/Ryan%20su/.gemini/antigravity/brain/5dbe8200-1879-4852-be56-160d7e6f93f3/scratch/sandbox_telemetry_2026-11-09.json)

---

## 2. 24 項審核標的清單與判定台帳 (Audit Ledger Breakdown)

### 2.1 確認漏洞並已完成沙盒補丁驗證 (`VULNERABLE_CONFIRMED`, 21 項)

| Target ID | 嚴重度 | 風險向量與實證現象 | 沙盒修復機制 (待人類核准套用) |
| :--- | :---: | :--- | :--- |
| `backend/routers/trips.py:get_trip_expenses_bola` | Critical | 未檢查 [`check_trip_access`](file:///d:/Project/tabiji/travel-pwa/backend/routers/expenses.py#L46) 且缺 `except HTTPException: raise` | 查詢前強制驗證成員權限並正確傳遞 `403` |
| `backend/routers/ai.py:generate_day_review_bola_lock_locale` | Critical | 端點無 [`get_verified_user`](file:///d:/Project/tabiji/travel-pwa/backend/utils/deps.py#L97) 認證、無成員檢核、RMW 無鎖、無英文 prompt | 加上 JWT + 成員授權、[`trip_lock`](file:///C:/Users/Ryan%20su/.gemini/antigravity/brain/5dbe8200-1879-4852-be56-160d7e6f93f3/scratch/run_post_audit_sandbox.py#L197) 序列化與 `?locale=en` 雙語支持 |
| `backend/routers/trips.py:update_item_404_masking_and_single` | High | `.single()` 與缺少 `except HTTPException: raise` 將 `404` 掩蓋為 `500` | 改用 `_first_row` 安全萃取並傳遞 `403`/`404` |
| `backend/routers/trips.py:reorder_items_empty_and_batch` | High | `items=[]` 觸發 `UnboundLocalError`，重複 ID 造成偽 `404`，缺分段 `.in_()` | 預初始化 `results = []`、`dict.fromkeys` 去重、`_chunked(..., 50)` |
| `backend/routers/trips.py:create_manual_trip_count_and_compensation` | High | 配額 `403` 被吞併為 `500`；`trip_members` 失敗遺留孤兒主表；無冪等鍵 | 補償刪除 `itineraries`、導入 [`idempotency.py`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_post_completion_audit_2026-11-09.diff#L64)、修正 `isinstance(raw_count, int)` |
| `backend/routers/trips.py:save_itinerary_compensation_and_tz` | High | 細項寫入失敗遺留主表與成員列、使用 naive `datetime.now()`、無冪等鍵 | 反向清理 3 張表、`datetime.now(timezone.utc)`、`Idempotency-Key` |
| `backend/routers/trips.py:trip_content_rmw_concurrency_lock` | High | `update_day_data`/`location`/`info` 並發讀取寫入互相覆寫、`location` 未驗權先查存在性 | 先驗成員後取得 per-trip async `trip_lock` 序列化 RMW |
| `backend/routers/trips.py:day_management_lock_batch_and_404` | High | `delete_day`/`add_day` 缺 `trip_lock`、`N+1` 逐筆更新、`403/404/400` 遭掩蓋為 `500` | `trip_lock` + 依目標日分組並採 `CHUNK_SIZE=50` 批次 `.in_()` |
| `backend/routers/trips.py:update_trip_dates_lock_and_batch` | High | 畸形日期觸發 `datetime.strptime` `500`、缺鎖、`on_shorten` 觸發 `N+1` | `try/except ValueError` 回 `400`、`_safe_single_data`、`trip_lock` + 批次 `.in_()` |
| `backend/routers/expenses.py:update_expense_404_masking_and_sanitization` | High | `except Exception` 攔截 `404` 轉成 `500` 且外洩 `str(e)` | 補上 `except HTTPException: raise` 並脫敏 `500` 回應訊息 |
| `backend/routers/expenses.py:add_expense_idempotency_and_error_guard` | Medium | 重送建帳會重複記帳；`500` 回傳直接曝露 `str(e)` | BOLA 驗證後檢查 `Idempotency-Key` 快取並脫敏 `500` 訊息 |
| `backend/routers/ai.py:parse_markdown_b64_json_and_locale` | High | `b64decode` 未設 `validate=True`、LLM 非法 JSON 報 `500`、缺 `locale` 指令 | `validate=True` + 尺寸檢查回 `400`、JSON 解析失敗回 `422`、英文指令注入 |
| `backend/main.py:global_exception_traceback_disclosure` | High | [`global_exception_handler`](file:///d:/Project/tabiji/travel-pwa/backend/main.py#L170-L187) 直接將 `str(exc)`、`error_type`、`path`、`traceback` 回傳 HTTP 500 | HTTP 僅回 `{"detail": "An internal server error occurred."}`，完整堆疊留存伺服器日誌 |
| `backend/main.py:stream_chat_world_time_and_poi_guards` | High | 重複呼叫 `get_world_time` 引發 `UnboundLocalError`、`fetch_jina_reader`/搜尋/POI 無超時與硬編中文 | 改為 `Dict` 快取、`asyncio.wait_for` (`4s/6s/8s`)、雙語 `query_world_time` 與 thinking 事件 |
| `backend/services/model_manager.py:client_cache_unbounded_and_timeout` | High | [`_client_cache`](file:///d:/Project/tabiji/travel-pwa/backend/services/model_manager.py#L422) 無上限增長、非同步 LLM 呼叫缺 `asyncio.wait_for` 超時保護 | 改用 `OrderedDict` LRU 上限 32 並導出 `__reset_client_cache_for_testing`、`MODEL_CALL_TIMEOUT=45.0` |
| `frontend/components/official/HeroTypewriterHeading.tsx:render_phase_setstate_compiler_violation` | Medium | Render 階段呼叫 `setActiveLines` 違反 React 19 Compiler 純度規則 | 外層以 `key` 重置內層 [`HeroTypewriterHeadingContent`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_post_completion_audit_2026-11-09.diff#L1689) |
| `frontend/components/official/TypewriterHeading.tsx:render_phase_setstate_and_ref_access` | Medium | Render 階段 `setActiveText` 與 `prevTextRef` 存取違反 React Compiler（附帶運動卡片英文標籤微補齊） | 外層以 `key` 重置 [`TypewriterHeadingContent`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_post_completion_audit_2026-11-09.diff#L1728)，補齊 `OfflineEngineMotionCard` / `LedgerMotionCard` 雙語 |
| `frontend/components/itinerary/AiImportTripWizard.tsx:locale_forwarding_and_hook_deps` | Medium | [`useEffect`](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/AiImportTripWizard.tsx#L255-L277) 關閉 `exhaustive-deps` 造成閉包陳舊，且未傳 `locale` 至 `aiApi.parseMarkdown` | 提昇 `useCallback(handleFileSelected)`、傳遞 `locale: lang` 並雙語化貼上/拖曳介面 |
| `frontend/components/itinerary/EditableDailyAIReview.tsx:locale_forwarding_and_loading_text` | Medium | 未傳 `lang` 至 `generateAIReview`、樂觀狀態未綁定 `tripId-day`、載入按鈕硬編中文 | 傳遞 `lang`、建立 `scopeKey` 隔離狀態、雙語化 `AI is reviewing...` |
| `frontend/components/itinerary/TripCoverMenu.tsx:missing_dialog_description_a11y` | Low | Lightbox [`DialogContent`](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/TripCoverMenu.tsx#L253-L256) 缺少 `DialogDescription` | 於 `VisuallyHidden` 內補齊雙語 `<DialogDescription>` |
| `frontend/lib/api.ts:liefi_network_fallback_and_idempotency` | High | [`offlineFetch`](file:///d:/Project/tabiji/travel-pwa/frontend/lib/api.ts#L981-L1018) 僅判斷 `!navigator.onLine` 導致 Lie-Fi 網路中斷掉包，且未自動注入 `Idempotency-Key` | 普通物件正規化注入 `Idempotency-Key`、捕獲非 `AbortError` 網路失敗入隊，並導出 `__resetSyncProcessingForTesting` |

### 2.2 Chesterton's Fence 故意設計排除清單 (`DISMISSED`, 3 項)

| Target ID | 原職責與設計意圖 | 排除理由 |
| :--- | :--- | :--- |
| [`backend/routers/app.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/app.py#L13-L44) (`donation_progress_single_and_naive_tz`) | 公開進度查詢採 `try/except` 容錯回傳預設 `{current: 0, goal: 2000, month}` | 既已安全降級無 500 或敏感資訊外洩風險，避免非必要更動 |
| [`frontend/lib/OfficialLanguageContext.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/lib/OfficialLanguageContext.tsx#L34-L96) (`sync_external_store_and_query_override`) | 使用 `sessionStorage` 保留跨頁面語系選擇，並監聽 `popstate` 同步回預設中文路由 | 官網多頁切換器有意設計行為，已受官網整合測試保護 |
| [`frontend/app/official/terms/page.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/app/official/terms/page.tsx#L89-L99) (`english_legal_rendering_omission`) | 靜態 RSC 法條頁第 3 條明定準據法為中華民國法律且仲裁準據語言為繁體中文 | 具法律拘束力語言一致性要求與靜態 Metadata 邊界 |

---

## 3. Sandbox 雙端全量遙測與 Diff 統計

### 3.1 沙盒全流程執行結果 (`sandbox_telemetry_2026-11-09.json`)
* **Baseline**：`pytest` `RC=0` (`475 passed, 5 skipped in 43.17s`) ｜ `tsc --noEmit` `RC=0` ｜ `eslint .` `RC=0` ｜ `vitest run` `RC=0` (`101 files / 941 passed in 10.44s`)
* **Red Stage (Mantis Block G)**：
  * `backend_benign`: `RC=0` (`3 passed, 13 deselected in 1.74s`)
  * `backend_poc`: `RC=1` (`13 failed, 3 passed in 2.62s`)
  * `frontend_benign`: `RC=0` (`2 passed | 7 skipped in 1.20s`)
  * `frontend_poc`: `RC=1` (`exploit_6`, `exploit_7` 紅燈失敗)
* **Green Stage (全通過 `RC=0`)**：
  * `backend_poc`: `RC=0` (`16 passed in 2.16s`)
  * `backend_full_pytest`: `RC=0` (`491 passed, 5 skipped in 34.27s`)
  * `frontend_poc`: `RC=0` (`9 passed in 1.18s`)
  * `tsc --noEmit`: `RC=0` (`0 errors`)
  * `eslint .`: `RC=0` (`0 errors, 0 warnings`)
  * `vitest run`: `RC=0` (`102 files / 950 passed in 10.48s`)

### 3.2 實體治理門禁驗證
* [`scripts/validate_security_ledger.py`](file:///d:/Project/tabiji/travel-pwa/scripts/validate_security_ledger.py)：`Verified 348 targets (104 remediated, 77 verified/unresolved, 167 dismissed/safe).` (`RC=0`)
* [`test_root_hygiene_sentinel.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_root_hygiene_sentinel.py)：`6 passed in 0.02s` (`RC=0`)
* [`root-hygiene-sentinel.test.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/root-hygiene-sentinel.test.ts)：`4 passed (1 file)` (`RC=0`)

### 3.3 沙盒補丁 18 檔行數變動統計 (`+1028 / -572`)
* 新增 `backend/utils/concurrency.py`: `+59 / -0`
* 新增 `backend/utils/idempotency.py`: `+58 / -0`
* `backend/models/base.py`: `+1 / -0`
* `backend/routers/expenses.py`: `+13 / -3`
* `backend/services/model_manager.py`: `+35 / -14`
* `backend/services/temporal_service.py`: `+16 / -5`
* `backend/main.py`: `+68 / -20`
* `backend/routers/ai.py`: `+105 / -29`
* `backend/routers/trips.py`: `+527 / -416`
* `frontend/components/official/HeroTypewriterHeading.tsx`: `+10 / -11`
* `frontend/components/official/TypewriterHeading.tsx`: `+10 / -16`
* `frontend/components/official/OfflineEngineMotionCard.tsx`: `+12 / -8`
* `frontend/components/official/LedgerMotionCard.tsx`: `+1 / -1`
* `frontend/components/itinerary/AiImportTripWizard.tsx`: `+30 / -30`
* `frontend/components/itinerary/EditableDailyAIReview.tsx`: `+14 / -8`
* `frontend/components/itinerary/TripCoverMenu.tsx`: `+5 / -2`
* `frontend/lib/api.ts`: `+60 / -9`
* `frontend/lib/sync-hooks.ts`: `+4 / -0`

---

## 4. 被刪除內容審查 (Deletion Audit)

| 被刪除／替換程式碼 | 原職責 | 承接機制與不變量守恆 |
| :--- | :--- | :--- |
| `global_exception_handler` 中 `error_type`/`path`/`traceback` 與 `str(exc)` | 回傳 HTTP 500 偵錯細節 | 完整 `traceback` 保留於伺服器端 `print(...)` 日誌；HTTP 回應僅輸出靜態安全字樣 `{"detail": "An internal server error occurred."}` |
| `generate_day_review` 無認證簽名與 `except Exception` 直接報 500 | 接受無憑證呼叫生成 AI 審核 | 改由 [`get_verified_user`](file:///d:/Project/tabiji/travel-pwa/backend/utils/deps.py#L97) + 行程擁有者/成員授權守門，`HTTPException` 直接透傳 |
| `ai.py:parse_markdown` 函式內重複區域變數 `import base64` 與 `from google.genai import types` | 在函式內延遲匯入模組（造成遮蔽風險） | 由模組頂層既有 `base64` 與 `google.genai.types` 匯入承接 |
| `HeroTypewriterHeading`、`TypewriterHeading` 內 `activeLines`/`activeText`/`prevTextRef` 渲染期 `setState` | prop 變更時於 render 階段重設打字機進度 | 外層包覆組件改以 `key`（`${line1}::${line2}` / `${as}::${text}`）徹底卸載重建內層 Content 組件 |
| `EditableDailyAIReview` 無作用域之 `optimisticReview` 狀態 | 本地樂觀更新當日 AI 審核文字 | 改為 `{ key: "${tripId}-${day}", value }` 綁定作用域狀態，防止切日/切行程殘影 |
| `AiImportTripWizard` 內 `// eslint-disable-next-line react-hooks/exhaustive-deps` | 壓制 `useEffect` 對 `handleFileSelected` 的相依警告 | `handleFileSelected` 提昇為 `useCallback` 並納入 `[handleFileSelected, haptic, zh]` |
| `trips.py` 高風險 `.single()`、`update_trip_location` 查表順序、`N+1` 逐筆迴圈、`datetime.now()` 與未分區 `in_()` | 單列讀取、天數位移與縮短截斷 | `_first_row()` / `_safe_single_data()` 防 `PGRST116`；成員權限先驗；`_chunked(..., 50)` 分批 `.in_()`；`datetime.now(timezone.utc)` |
| `expenses.py` / `trips.py` 原生 `detail=str(e)` 500 例外字樣 | 向前端暴露未過濾例外訊息 | 全數改為穩定中文化安全錯誤字串並確保 `except HTTPException: raise` 先行 |
| `model_manager.py` 無界字典 `_client_cache: Dict[str, genai.Client]` | 依 BYOK Key 快取 SDK 實例 | 改為 `OrderedDict` LRU（上限 32）+ `asyncio.wait_for(..., timeout=45.0)` |

---

## 5. `Chesterton's Fence` 設計初衷與歷史 Corner Case 溯源（Code Archaeology）

依提交歷史、領域知識庫（[`.agents/domains/`](file:///d:/Project/tabiji/travel-pwa/.agents/domains/backend_concurrency.md)）、測試合約與原始註解對全數受檢群集進行法醫學溯源後，確認原始實作大多為解決過去真實痛點而生，僅因後續機能擴張、並發寫入與 React 19 編譯器規範演化才暴露副作用：

| 群集／檔案 | 原始設計意圖與解決的歷史 Corner Case | 為何在現況演變為風險（與不變量衝突點） | 沙盒補丁如何兼顧原意與修復 |
| :--- | :--- | :--- | :--- |
| [`backend/main.py`](file:///d:/Project/tabiji/travel-pwa/backend/main.py#L170-L187) (`global_exception_handler`) | `3e019b3` (2026-07-24) 為方便單人開發者在手機／Vercel 前端直接排查 500 例外而回傳 `error_type`、`path`、`traceback`（已確認前端無任何程式碼解析此等欄位） | CWE-209 直接將內部檔案路徑、模組結構與 DB 訊息暴露給任意呼叫端 | 伺服器 `print(...)` 完整堆疊保留不變；HTTP 回應收斂為靜態字串 `An internal server error occurred.` |
| [`backend/main.py`](file:///d:/Project/tabiji/travel-pwa/backend/main.py#L1325-L1430) (`stream_chat_generator`) | `7f5f680`（AD-182~187）實作雙軌 Grounding：`fetched_urls` 跳過重複精讀降延遲、`batch_tool_responses` 防止 Gemini 400 Dangling Tool、`150ms` 錯峰防 DDG 429、`10s` ping 繞過代理超時 | `executed_world_time` 使用 `set()` 記錄城市卻未快取結果，同一輪若重複呼叫 `get_world_time` 會因跳過賦值引發 `time_data` `UnboundLocalError`；外部爬取/POI 無超時且思維鏈硬編中文 | `executed_world_time` 改為 `Dict[str, Any]` 快取查詢結果；替 `fetch_jina_reader`、`execute_resilient_nearby_search`、`execute_web_search` 加上 `4s/6s/8s` `asyncio.wait_for`；[`query_world_time`](file:///d:/Project/tabiji/travel-pwa/backend/services/temporal_service.py#L418-L473) 與 SSE 思維訊息雙語化 |
| [`backend/routers/ai.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py#L892-L1018) (`generate_day_review` vs `clear_day_review`) | `1da65f4` (2025-12-30) 初版原本有 `except HTTPException: raise`；`47624e6` (2026-03-18) 全面重構端點對齊與 `.single()` 時不慎漏掉 `HTTPException` 透傳與 `get_verified_user`（反觀相鄰 [`clear_day_review`](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py#L980-L1017) 保留完整 JWT + BOLA + 透傳，受 [`test_p0_auth_sentinel.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_p0_auth_sentinel.py#L415-L442) 保護）；[`parse_markdown`](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py#L269-L520) 沿用 fast-lite 路由防 Next.js 30s ECONNRESET | 無 JWT/成員驗證即可匿名消耗他人行程 `day_ai_reviews` 配額並寫入任意 `trip_id` JSONB；`b64decode` 未啟 `validate=True`；`JSONDecodeError` 噴 500；未支援 `?locale=en` | 補齊 [`get_verified_user`](file:///d:/Project/tabiji/travel-pwa/backend/utils/deps.py#L97)、創立者/成員授權、[`trip_lock`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_post_completion_audit_2026-11-09.diff#L52) 序列化與英文評鑑 rubric；`parse_markdown` 改回 `400/422` 語意狀態碼並支援 `body.locale` |
| [`backend/services/model_manager.py`](file:///d:/Project/tabiji/travel-pwa/backend/services/model_manager.py#L422-L442) (`_client_cache` 與超時) | `21e107d` (2026-03-07) 原採 5 分鐘 TTL 快取；`b535a24` (2026-03-15, `v21 核心`) 改為無界 `Dict` 搭配 `close_all_cached_clients()` 在 `lifespan` 統一關閉非同步連線池，重用 BYOK HTTPS/TLS 連線 | 長期運行下大量 BYOK Key 會令 `_client_cache` 無上限增長；單一模型 TCP/TLS 僵死無 `asyncio.wait_for` 保護，無法快速觸發 fallback | 改用 `OrderedDict` LRU 上限 32 並提供 `__reset_client_cache_for_testing()`；於 [`call_with_fallback`](file:///d:/Project/tabiji/travel-pwa/backend/services/model_manager.py#L867)、[`call_verifier`](file:///d:/Project/tabiji/travel-pwa/backend/services/model_manager.py#L937)、[`call_extraction`](file:///d:/Project/tabiji/travel-pwa/backend/services/model_manager.py#L989) 加上 `MODEL_CALL_TIMEOUT = 45.0`（詳見第 6 節調參說明） |
| [`backend/routers/trips.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/trips.py#L2135-L2208) (`get_trip_expenses`) | `b535a24` 為相容前端 `API.TRIPS` 路徑建立，後續補入 `mem_*` 雜湊遮罩以符合公開層成員脫敏，但未同步移植 [`check_trip_access`](file:///d:/Project/tabiji/travel-pwa/backend/routers/expenses.py#L84) | 任意已登入使用者只要猜中/取得 `trip_id` UUID 即可讀取他團全部 `is_public=True` 公帳明細（Critical BOLA） | 入口強制呼叫 [`check_trip_access`](file:///d:/Project/tabiji/travel-pwa/backend/routers/expenses.py#L84) 並補 `except HTTPException: raise` 與 500 脫敏 |
| [`backend/routers/trips.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/trips.py#L534-L2020) (寫入、`content` RMW、天數位移、`reorder_items`、`update_item`) | PostgREST REST API 缺乏跨表分散式交易；[`save_itinerary`](file:///d:/Project/tabiji/travel-pwa/backend/routers/trips.py#L974-L982) 失敗時逐筆寫入定位故障項目；[`update_day_data`](file:///d:/Project/tabiji/travel-pwa/backend/routers/trips.py#L1230-L1250) 採 `select("*")` 執行 Legacy Merge-on-Write；[`delete_day`](file:///d:/Project/tabiji/travel-pwa/backend/routers/trips.py#L1889-L1960) / [`add_day`](file:///d:/Project/tabiji/travel-pwa/backend/routers/trips.py#L1973-L2120) 內建 `Ghostbuster`（避免 `"10" < "2"` 字串排序殘留幽靈鍵）、`Scorched Earth Clean` 與 `Identity Wash`；[`update_trip_dates`](file:///d:/Project/tabiji/travel-pwa/backend/routers/trips.py#L1441-L1544) 實作 `Zero-Shift` 防護並受 [`test_trip_dates_shift.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_trip_dates_shift.py) `.single()` mock 鏈測試保護；[`update_item`](file:///d:/Project/tabiji/travel-pwa/backend/routers/trips.py#L1689-L1833) 先讀 `itinerary_items` 快照以支援 `Visual Synergy` 與 `Sticky Pin Prevention` | 多表失敗遺留主表配額佔用；無鎖讀寫 `content` 並發覆寫遺失；`reorder_items` 遇到 `items=[]` 拋 `UnboundLocalError` 或因重複 ID 誤判 404；`.single()` 與缺失 `except HTTPException: raise` 將 404/403 掩蓋為 500；`N+1` 逐筆迴圈撞 PostgREST URI 長度或逾時 | 保留全部 `Lazy Migration`、`Ghostbuster`、`Scorched Earth`、`Identity Wash`、`Zero-Shift` 與 `Visual Synergy`；導入補償刪除、[`trip_lock`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_post_completion_audit_2026-11-09.diff#L52)、[`idempotency.py`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_post_completion_audit_2026-11-09.diff#L64)、`_chunked(..., 50)`、`_first_row()` 及相容 `.single()` Mock 的 [`_safe_single_data()`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_post_completion_audit_2026-11-09.diff#L748) |
| [`backend/routers/expenses.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/expenses.py#L28-L302) (`sanitize_payer`, `add_expense`, `update_expense`) | [`sanitize_payer`](file:///d:/Project/tabiji/travel-pwa/backend/routers/expenses.py#L28) 防止訪客 UUID 觸發 PostgreSQL `23503` 外鍵違規；`calculate_total_fallback` 調和細目與總額誤差 | 重複離線重送欠缺 `Idempotency-Key` 造成重複記帳；[`update_expense`](file:///d:/Project/tabiji/travel-pwa/backend/routers/expenses.py#L485-L532) 因缺 `HTTPException` 透傳把 404 變成 500 並洩漏 `str(e)` | 保留全部 `sanitize_payer` / 精算邏輯；成員驗權後接入 `Idempotency-Key` 快取與 `404`/脫敏防衛 |
| [`frontend/components/official/HeroTypewriterHeading.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/official/HeroTypewriterHeading.tsx#L38-L45) & [`TypewriterHeading.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/official/TypewriterHeading.tsx#L41-L53) | 受 [`official-bilingual-switcher-sentinel.test.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/official-bilingual-switcher-sentinel.test.tsx#L77-L113)（Gate 2）契約驅動：工程師刻意採用渲染期 `setState`（「adjusting state when a prop changes」）避免在 `useEffect` `setState` 觸發 React 19 `react-hooks/set-state-in-effect` 與 1-frame 舊語言閃爍，並用 `hasStartedRef` 防止同文字滾動重繪重複打字 | 在 React 19 Compiler 下於 render 期間直接呼叫 `setState` 並讀寫 `prevTextRef.current` 仍屬非純函數寫法 | 外層包裝組件以穩定 `key`（`${line1}::${line2}` / `${as}::${text}`）重置內層 Content；文字不變時滾動狀態不流失，語系切換時自動潔淨重掛並完整通過 `SENTINEL-2.1~2.4` 與 `SENTINEL-6.4` |
| [`frontend/components/itinerary/AiImportTripWizard.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/AiImportTripWizard.tsx#L255-L460), [`EditableDailyAIReview.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/EditableDailyAIReview.tsx#L42-L166), [`TripCoverMenu.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/TripCoverMenu.tsx#L251-L260) | 剪貼簿直接貼上圖片、產出報告後立刻透過 `optimisticReview` 渲染避免等待 SWR revalidation 閃白、`VisuallyHidden` 隱藏 Lightbox 標題以維持無邊框視覺 | 壓制 `exhaustive-deps` 埋下閉包風險、`optimisticReview` 未綁定 `tripId-day` 在快速切換天數時可能殘留他日報告、`locale` 未下傳且截圖/Loading 文案與 Radix `DialogDescription` 缺漏 | 提昇 `useCallback` 解除 lint 壓制；`scopeKey` 隔離樂觀狀態；雙語與 `VisuallyHidden` a11y 補齊 |
| [`frontend/lib/api.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/lib/api.ts#L981-L1018) (`offlineFetch`) | `f25f942` (2026-01-16) 刻意僅攔截 `!navigator.onLine` 的突變請求（避免輪詢 GET 污染佇列），且維持 plain object headers 以滿足 IndexedDB 序列化與 [`api.test.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/api.test.ts#L44-L53) 的 `expect.objectContaining` 斷言；[`next.config.mjs`](file:///d:/Project/tabiji/travel-pwa/frontend/next.config.mjs) 直接將 `/api/*` 代理至後端 | 行動端「在線假死（Lie-Fi）」時 `navigator.onLine === true` 但 `fetch` 拋出網路錯誤，突變直接丟失；離線重播重複發送缺少 `Idempotency-Key` | 新增 `normalizePlainHeaders()`（不轉 `Headers` 實例，100% 相容 `api.test.ts` 與 IndexedDB）並注入 UUID `Idempotency-Key`；僅捕獲非 `AbortError` 的網路錯誤自動入隊，HTTP 4xx/5xx 行為維持原樣 |

---

## 6. 沙盒補丁與歷史意圖之取捨提醒（Pre-Apply Engineering Nuances）

> [!WARNING]
> **實作前關鍵設計權衡（已反映於審核結論，待人類拍板）**：
> 1. **`model_manager.py` 的 `MODEL_CALL_TIMEOUT = 45.0` 與 `PLANNING` 長時思考衝突風險**：[`generate_trip_core`](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py#L522-L605) 使用 `intent_type="PLANNING"`（`ThinkingConfig(thinking_level="high")`、`max_output_tokens=16384`），而 [`generate_trip_stream`](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py#L696-L758) 之所以實作 `10s Keep-Alive` 心跳正是為了**重置 Cloudflare 100s Idle 計時器**以容納長天數深度生成（可能耗時 45s～90s）。統一 45.0s 超時雖能快速切斷僵死模型觸發 fallback，但在高複雜度 7 日以上 `PLANNING` 請求可能過早中斷並連環耗盡整條備援鏈。
> 2. **`_client_cache` LRU 淘汰與連線回收**：當超過 `MAX_CLIENT_CACHE_SIZE = 32` 把手時，同步函式 [`get_cached_client`](file:///d:/Project/tabiji/travel-pwa/backend/services/model_manager.py#L425-L431) 執行 `_client_cache.popitem(last=False)` 無法直接 `await c.aio.aclose()`（該回收僅於關閉階段的 `close_all_cached_clients()` 執行）。對多數同時少於 32 組活躍 BYOK Key 的場景無影響，若極端高併發替換大量 Key，可於非同步呼叫點補上退役佇列排程關閉。
> 3. **`trips.py` `_safe_single_data` 之測試相容設計**：[`update_trip_dates`](file:///d:/Project/tabiji/travel-pwa/backend/routers/trips.py#L1441) 刻意保留 `.single()` 並以外層 [`_safe_single_data()`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_post_completion_audit_2026-11-09.diff#L748) 攔截 `PGRST116`（零列錯誤轉 `None -> 404`），藉此與 [`test_trip_dates_shift.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_trip_dates_shift.py#L39) 原有的 `.single().execute` Mock 鏈維持 100% 向下相容。


