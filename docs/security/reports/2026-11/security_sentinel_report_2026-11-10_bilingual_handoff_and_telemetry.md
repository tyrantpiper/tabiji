# 🛡️ Security Sentinel 沙盒對抗審查報告：全系統雙語切換連動與 Chrome Telemetry 修復 (2026-11-10)

> **稽核日期**: 2026-11-10  
> **基準提交**: `44f107f`（疊加 Post-Completion Audit V2 既有本地變更；沙盒基底 `43857d1`）  
> **稽核模式**: `/security-sentinel` 6-Phase Pipeline ✕沙盒 Worktree 實體隔離 (`sentinel-23a02618`) ✕ Google Mantis Block G ✕ Harness²守恆  
> **審查判定**: **`12 / 12` `CONFIRMED_PENDING_DEV`**（`0 dismissed`, `0 inconclusive`，取代先前超時之 `mode: "fast"` 殘缺紀錄）  
> **台帳守恆驗證**: `365` Targets (`130 remediated + 68 verified/pending_dev + 167 dismissed/safe = 365`, `scripts/validate_security_ledger.py RC=0`)  
> **L0 人類主權狀態**: **WAITING FOR HUMAN APPROVAL (`Proceed`)** — **Live 工作區 `backend/` 與 `frontend/` 目前維持 0 修改**。

---

## 1. 執行摘要 (Executive Summary)

本次依據已審核之 [`implementation_plan.md`](file:///C:/Users/Ryan%20su/.gemini/antigravity/brain/5dbe8200-1879-4852-be56-160d7e6f93f3/implementation_plan.md) v2，於實體隔離工作樹 `.worktrees/sentinel-23a02618` 完成全計畫實作、紅軍 Red ➔ Green 對抗證成、Mantis Block G 良性對照驗證，以及全棧靜態/單元/建置關卡檢驗，並已安全匯出補丁與 `204` 組逐塊替換規格（Live 檔案 in-memory Round-Trip 100% 無損校驗通過）後潔淨拆除工作樹。

### 沙盒全棧門禁與結構守衛實測結果

| 驗證關卡 (Sandbox `sentinel-23a02618`) | 實測數據 / 結果 | 備註與邊界誠實揭露 |
| :--- | :--- | :--- |
| Backend Targeted Suite (`pytest`) | **`48 passed, 3 skipped in 5.07s`** (`RC=0`) | 涵蓋 [`test_intent_router.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_intent_router.py) (`14/14`)、新增 `test_bilingual_e2e_remediation_sentinel.py` (`32/32`) 與 [`test_poi_lifespan.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_poi_lifespan.py) (`2 passed, 3 skipped`；該 3 項 skip 為上游既有 `@pytest.mark.skip`，原因為 Prometheus metrics / timeout 尚未實作) |
| Backend Full Suite (`python -m pytest -q`) | **`533 passed, 5 skipped in 47.95s`** (`RC=0`) | 於最終 [`intent_router.py`](file:///d:/Project/tabiji/travel-pwa/backend/services/intent_router.py) 修補後完整重跑通過 |
| Backend Syntax (`python -m compileall -q`) | **`RC=0`** | 全後端模組編譯零錯誤 |
| Frontend TypeScript (`npx tsc --noEmit`) | **`0 errors`** (`RC=0`) | `frontend/` 修改後零型別錯誤 |
| Frontend ESLint (`npx eslint .`) | **`0 errors`** (`RC=0`) | 零 linting 違規（含 React Compiler 與 Tailwind v4 規則） |
| Frontend Unit & Sentinel (`npx vitest run`) | **`104 files / 968 tests passed`** (`RC=0`) | 含新增 `portal-lang-handoff-and-actuary-sentinel.test.tsx` (`9/9 passed`) |
| Frontend Typegen & Build | `npx next typegen` **`RC=0`**；`npx next build --webpack` **`RC=0`** | 21.0s 編譯完成 13 條路由；預設 Turbopack 因工作樹 `frontend/node_modules` 為指向主目錄之 NTFS Junction 超出 `turbopack.root` 而無法於 worktree 執行，待 `Proceed` 套用 Live 後於 Phase 6 重測預設 Turbopack Build ＋ `@mcp:chrome` 實機雙語 E2E |
| Frozen Core (`SENTINEL-4.1`) | **`0` diff lines** | [`page.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/app/page.tsx)、[`sw.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/app/sw.ts)、[`manifest.json`](file:///d:/Project/tabiji/travel-pwa/frontend/public/manifest.json)、[`pwa-install-prompt.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/pwa-install-prompt.tsx) 完全未觸碰 |
| Portal Isolation (`SENTINEL-1.1 / 3.1`) | **`0` JS `localStorage.` calls；`6` 文字 `<Link>`** | [`OfficialFooter.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/official/OfficialFooter.tsx) 保持剛好 6 個文字 `<Link>`（品牌連結另計）；[`ActuaryDialogCard.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/ActuaryDialogCard.tsx) 保留 `sm:max-w-150`、`shrink-0`、`wrap-break-word` |
| i18n EN/ZH 鍵值對齊 | **8 模組共 `1,009` 鍵 + 官網字典零缺鍵** | 主系統 `frontend/lib/i18n/*.ts` (`1,009` 鍵) 與 `official-translations.ts` 100% 雙語對齊；已棄用遺留檔 `frontend/lib/translations.ts`（僅測試引用）亦同步修補 `actuary_welcome` |
| Ledger & Findings Conservation | **`365` targets (`RC=0`), `12/12 CONFIRMED`** | [`validate_security_ledger.py`](file:///d:/Project/tabiji/travel-pwa/scripts/validate_security_ledger.py) 通過 |

---

## 2. 攻擊面覆蓋矩陣 (Attack Surface Coverage Matrix)

| 目標識別碼 (`id`) | 信任邊界 (`trust_boundary`) | 核心問題與驗證結論 (`CONFIRMED_PENDING_DEV`) |
| :--- | :--- | :--- |
| `backend/routers/geocode.py:smart_fusion_results_keyerror_and_coords_guard` | `authenticated_to_internal` | 讀取 `smart_search` 新版 `"results"`（相容 `"recommendations"`）、空 `highlights`/`reason`/無效座標防護，Task B 包裝於 `_timed_smart_search(timeout=8.0)` 防止拖垮 Task A。 |
| `backend/services/smart_search_service.py:overpass_cascading_timeout_and_locale_drift` | `authenticated_to_internal` | 解除 4 圈 10s 串行 Overpass 阻塞；改為 `parse_intent` (`2.5s`)＋`geocode_place` (`2.5s`)＋單次 Overpass (`<=3.0s`)＋Photon 即時降級 (`<=3.0s`) 與雙語預設文案。 |
| `backend/services/poi_service.py:overpass_hardcoded_timeout_parameterization` | `authenticated_to_internal` | `search_overpass` 與 `search_poi_combined` 新增可選 `timeout: float = 10.0` 參數，動態寫入 `[timeout:{ql_timeout}]` 與 `httpx.AsyncClient(timeout=timeout)`。 |
| `backend/utils/poi_utils.py:poi_cache_key_cross_locale_poisoning` | `authenticated_to_internal` | `generate_v2_cache_key(..., locale="zh")` 將 key 隔離為 `poi:v2:{zh\|en}:*`，阻絕中英文跨語系快取中毒。 |
| `backend/routers/poi.py:poi_enrich_locale_isolation_and_test_reset` | `authenticated_to_internal` | `ai_enrich_poi`、`enrich_poi`、`ai_recommend_poi`、`get_poi_categories`、`ai_smart_search` 全數消費 `locale`；新增 `__resetPoiEnrichCacheForTesting()`；英文維基翻譯對齊與 500 脫敏。 |
| `backend/services/intent_router.py:diagnosis_intent_fastpath_shadowing` | `public_to_authenticated` | 抽離 `\bcheck\b` 至 Step 5 `detect_diagnosis_intent` 之後（Step 6 接住 `"Check weather..."`），並對齊 `main.py` 英文系統信封正則邊界。 |
| `backend/services/model_manager.py:interactive_flash_lite_routing_desync` | `authenticated_to_internal` | 全互動意圖歸入 `DAILY_ROUTING`、`HEAVY_ROUTING` 由 `gemini-3.1-flash-lite` / `3.5-flash-lite` 領銜；協調更新 [`test_model_manager.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_model_manager.py)。 |
| `backend/routers/ai.py:actuary_empty_ledger_guardrail_calibration` | `authenticated_to_internal` | 空帳本 (`expenses=[]`) 雙語友善引導＋`</user_query>` XML 邊界跳脫＋保留 `[SECURITY_VIOLATION]` 阻斷＋CWE-209 安全 500 訊息。 |
| `backend/main.py:stream_chat_diagnosis_prompt_and_locale_leakage` | `authenticated_to_internal` | 補齊 `chat_stream` 上游與 `stream_chat_generator` 雙語 `get_diagnosis_prompt()`、英文地標/時間/分類/Agents 透傳、`app.state.client` 空值防護。 |
| `frontend/lib/LanguageContext.tsx:portal_soft_nav_freeze_ppr_suspense_and_storage_isolation` | `browser_to_edge` | `<Suspense>` 包覆 `LanguageUrlHandoffObserver`，僅於非 `/official*` 路徑吸收 `?lang=` 並以 `replaceState` 清洗，並以 `isReady` 取代拆離 Context 之 `if (!mounted)` 返回。 |
| `frontend/components/official/OfficialHeader.tsx:launch_app_lang_open_redirect_and_handoff` | `browser_to_edge` | Header / Hero / Page / Footer 統一以字面安全路徑 `/?lang=en` / `/?lang=zh` 經由 `sanitizeLaunchRedirectUrl` 啟動 PWA，嚴守官網零 `localStorage`。 |
| `frontend/components/POIDetailDrawer.tsx:stale_bilingual_state_and_locale_param` | `browser_to_edge` | 解構 `{ t, lang }`、語系切換重置 `aiData`、重命名遮蔽變數 `resolvedLang`、修正 `POIPreviewCard` (`cancelled` 競態) 與 6 處地圖搜尋 `locale` 透傳。 |

---

## 3. 沙盒深度審查額外查獲與即時修復項目

在沙盒對照 41 個變更檔逐行 Diff 時，另行捕獲並於沙盒修復、納入補丁與永久測試之兩項潛在故障：

1. **`enrich_poi_complete(..., lang=...)` 與英文地標擷取參數失配（[`main.py`](file:///d:/Project/tabiji/travel-pwa/backend/main.py) ✕ [`poi_service.py`](file:///d:/Project/tabiji/travel-pwa/backend/services/poi_service.py) ✕ [`poi.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/poi.py)）**：
   - `chat_stream` 呼叫 `enrich_poi_complete(poi, client=..., lang=...)` 時，原 [`poi_service.py`](file:///d:/Project/tabiji/travel-pwa/backend/services/poi_service.py) 簽名尚未接收 `lang` 參數（原會拋出 `TypeError` 被 `try/except` 靜默吞掉），且英文地標正則會連同前導動詞誤抓 `"Tell me about Senso-ji Temple"`、且測試環境未走 lifespan 時 `request.app.state.client` 會拋 `AttributeError`。
   - **修復與測試**：補齊 `enrich_poi_complete(..., lang="zh")`、`enwiki/jawiki/zhwiki` Sitelinks 與雙語 `display_name` 優先序、縮緊 `en_pattern` negative lookahead，以及 `getattr(..., "client", None)` 防護；並以第 32 條測試 `test_red_enrich_poi_complete_and_chat_stream_landmark_accept_lang_en` 在沙盒實測通過。
2. **英文系統信封提取與 `main.py` 實際模板對齊（[`intent_router.py`](file:///d:/Project/tabiji/travel-pwa/backend/services/intent_router.py)）**：
   - 比對發現 [`intent_router.py`](file:///d:/Project/tabiji/travel-pwa/backend/services/intent_router.py) 之 `SYSTEM_PREFIX_ANCHOR_RE`、`SYSTEM_BOUNDARY_END_RE`、`SYSTEM_ALLOWED_SUFFIX_RE` 先前使用假設字首（如 `User is asking about`、`User's original question:`），與 `main.py` 實際組裝之 `The user is asking about "..."`、`Original question:`、`Answer the user's question based on`、`[Live External Webpage Content (Source: `、`User Request:`、`[System Notice: ...]`、`📍 **Nearby ` 不完全吻合。
   - **修復與測試**：將三條信封正則精準對齊 `main.py` 全數中英文實際模板，並以英文地標／外部網頁預載信封夾帶偽造標籤 PoC 驗證（`test_intent_router.py` 14/14 ＋ Sentinel 32/32 全數通過）。

---

## 4. Chesterton's Fence 切斯特頓圍欄三問考古矩陣

| 模組與位置 | 功能反推 (`legacy_function`) | 設計初衷 (`design_intent`) | 刪除/修改風險與承接機制 (`regression_risk`) |
| :--- | :--- | :--- | :--- |
| [`intent_router.py`](file:///d:/Project/tabiji/travel-pwa/backend/services/intent_router.py) `_fast_path_classify` | Step 4 攔截搜尋動詞於 Step 5 診斷之前 | 防止中文「查這家好不好吃」因「好不好」誤入行程健檢 | 僅將英文 `\bcheck\b` 下移至 Step 6（位於 `detect_diagnosis_intent` 之後），中文搜尋詞與 `"Check weather in Kyoto tomorrow"` 仍 100% 進 `SEARCH`。 |
| [`geocode.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/geocode.py) Fusion Merge | 將 `smart_search` 推薦轉為地圖置頂 POI | 搜餐廳／拉麵時優先於城市行政區顯示具體店家與理由 | 相容 `"results"` 與舊版 `"recommendations"`，補齊無座標過濾與安全字串預設，Task B 逾時 8s 只降級本身不丟棄 Task A。 |
| [`smart_search_service.py`](file:///d:/Project/tabiji/travel-pwa/backend/services/smart_search_service.py) `get_poi_candidates` | 經地理編碼後查詢真實 OSM POI | 防胡謅：只回傳真實存在地點；曾用 4 半徑迴圈換召回率 | 改以單次 2000m `3.0s` Overpass ＋ 即時 `3.0s` Photon Fallback 承接召回率，徹底解除 40s 阻塞導致 Next.js Proxy 500。 |
| [`routers/ai.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py) `actuary_chat` | 限制模型僅依帳本 JSON 回覆與 XML 界線隔離 | 防止虛構消費金額與指令越權洩漏系統提示 | 以 `[EMPTY LEDGER POLICY]`／`【空帳本友善原則】` 區分「無帳本問候引導」與「提示詞注入 `[SECURITY_VIOLATION]`」，並跳脫 `</user_query>` 與脫敏 HTTP 500。 |
| [`LanguageContext.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/lib/LanguageContext.tsx) `LanguageProvider` | 掛載後同步 `localStorage['app_language']` 與 cookie | `if (!mounted)` 原為防止 SSR/CSR 水合文字不一致 | 改提供 `isReady: mounted` 維持 Context 連線不斷裂，並以 `<Suspense>` 包裹 `LanguageUrlHandoffObserver` 守住 `!pathname.startsWith('/official')` 與 PPR 邊界。 |
| [`OfficialHeader.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/official/OfficialHeader.tsx) Launch App | 引導官網訪客進入核心 PWA `/` | 維持 `/official` 與 `/` 儲存與 SEO 隔離 (`SENTINEL-1.1`) | 僅以 compile-time 字面值 `'/?lang=en'` / `'/?lang=zh'` 傳入 `sanitizeLaunchRedirectUrl`，零動態輸入故零 Open Redirect 風險。 |

---

## 5. 被刪除或替換內容審查清單 (Deletion Audit)

| 檔案與位置 | 刪除／替換內容 | 原職責 | 承接與強化機制 |
| :--- | :--- | :--- | :--- |
| [`frontend/lib/LanguageContext.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/lib/LanguageContext.tsx) | 移除 `if (!mounted) { return <>{children}</> }` 早退分支 | 防止首次 Render 讀取 client 語系造成 hydration mismatch | 改於 `LanguageContextType` 暴露 `isReady: mounted` 並讓子元件（如 `ActuaryDialogCard`、`POIPreviewCard`）依 `isReady` 延後自動請求；預設 `'zh'` 首屏水合完全一致。 |
| [`frontend/components/POIDetailDrawer.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/POIDetailDrawer.tsx) | 區域變數 `const lang = aiData.resolved_language.toLowerCase()` 更名為 `resolvedLang` | 解析維基條目語系以補充 Google Images 地名提示 | 避免遮蔽從 `useLanguage()` 解構的外層 UI `lang`，Google Images 地名提示功能 100% 等價保留。 |
| [`frontend/lib/i18n/expense.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/lib/i18n/expense.ts) 與遺留 [`translations.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/lib/translations.ts) | 替換 `en.actuary_welcome` 誤植字面 `"Loading expenses..."` | 作為 AI 精算師首次開啟對話之預設歡迎分析提示 | 改為 `"Please analyze our trip group expenses."`，消除精算師一打開就對 AI 送出「Loading expenses...」的假狀態觸發。 |
| [`backend/services/smart_search_service.py`](file:///d:/Project/tabiji/travel-pwa/backend/services/smart_search_service.py) | 刪除 `[1000, 2000, 3000, 5000]` 四圈串行 `search_poi_combined` 迴圈 | Overpass 無資料時逐步放大搜尋半徑 | 由「`2.5s` `geocode_place` ＋ `2000m` `3.0s` 限時 Overpass ＋ `3.0s` `_photon_fallback_candidates`」承接並超越原覆蓋範圍，最差總耗時降自 40s 至 <= 8s。 |
| [`backend/services/intent_router.py`](file:///d:/Project/tabiji/travel-pwa/backend/services/intent_router.py) | 將 `\bcheck\b` 自 Step 4 `strong_search_action` 移出並新增 Step 6 兜底 | 捕捉英文 `"Check weather..."` 主動聯網查詢 | 讓位於 Step 5 的 `detect_diagnosis_intent` 先辨識 `"Check if my itinerary makes sense?"` ➔ `DIAGNOSIS`，Step 6 緊接捕獲所有剩餘 `\bcheck\b` 查詢 ➔ `SEARCH`。 |
| [`backend/utils/ai_config.py`](file:///d:/Project/tabiji/travel-pwa/backend/utils/ai_config.py) & [`model_manager.py`](file:///d:/Project/tabiji/travel-pwa/backend/services/model_manager.py) | 調整 `HEAVY_ROUTING` 前置排序並將互動意圖統一併入 `DAILY_ROUTING`；移除硬寫 `WORKHORSE` 註解舊型號標示 | 定義各意圖 AI 模型備援順序 | 維持完整 `3.8/3.7/3.6` 與 Gemma MoE 救援鏈於備援序列，同步對齊 [`test_model_manager.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_model_manager.py) 斷言契約。 |
| [`backend/routers/geocode.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/geocode.py) | 移除單一 `smart_results["recommendations"]` 與未防護 `rec['reason']` / `highlights[0]` 索引 | 將 Smart Search 輸出轉為地圖 Fusion Pin | 擴充雙格式陣列偵測 (`results` 優先，`recommendations` 向後相容) ＋ `lat`/`lng` 空值跳過 ＋ `address`/`distance` 優雅回退。 |
| [`backend/routers/ai.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py) | 移除 `detail=str(e)` 原始例外字串直接暴露與單一剛性中文安全守則 | 回傳除錯錯誤訊息與限制帳本幻覺 | 保留 `print(f"🔥 ...")` 後端紀錄，對外僅回傳雙語安全訊息，空帳本可友善引導而不誤觸 `[SECURITY_VIOLATION]`。 |

---

## 6. Deliverables 檔案索引與 Phase 6 人類簽核關卡

* **候選統一補丁 (`.diff`)**：[`patch_candidate_bilingual_handoff_and_telemetry_2026-11-10.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_bilingual_handoff_and_telemetry_2026-11-10.diff)（`41` 檔、`237,928` bytes、UTF-8 無 BOM）
* **逐塊精準替換映射 (`204` Blocks, 已對 Live 完成 In-Memory 100% 無損校驗)**：[`block_replacements_bilingual_handoff_and_telemetry_2026-11-10.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/candidates/block_replacements_bilingual_handoff_and_telemetry_2026-11-10.json)
* **Harness² 對抗驗證結果**：[`findings_bilingual_handoff_2026-11-10.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/findings/findings_bilingual_handoff_2026-11-10.json)（`12/12 CONFIRMED`, `0 DISMISSED`, `0 INCONCLUSIVE`）
* **全系統安全覆蓋台帳**：[`security-coverage-ledger.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/security-coverage-ledger.json)（`365` Targets 守恆通過）
* **執行計畫依據**：[`implementation_plan.md`](file:///C:/Users/Ryan%20su/.gemini/antigravity/brain/5dbe8200-1879-4852-be56-160d7e6f93f3/implementation_plan.md)

> **下一步（L0 人類簽核）**：請回覆 **`Proceed`** 核准將上述已於沙盒完全驗證之 41 檔補丁套用至 Live 工作區，並於 Live 環境執行 **預設 Turbopack `next build`＋ 全量 `pytest` / `vitest` / `tsc` / `eslint` ＋ 啟動前後端執行 Chrome DevTools `@mcp:chrome` 雙語實機 E2E Telemetry 實測**（隨後將台帳 12 項升級為 `REMEDIATED`）。

