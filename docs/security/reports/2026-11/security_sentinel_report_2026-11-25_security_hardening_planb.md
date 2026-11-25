# 🛡️ Security Sentinel 沙盒對抗審查報告：Revised 9/10 Plan B 全棧資安加固與 Vercel-Grade CSP (2026-11-25)

> **稽核基準**: `08b06df` (`main`)
> **稽核模式**: Pre-Execution Worktree Spiking (`.worktrees/sentinel-planb-sandbox`) ✕ Red→Green PoC ✕ Mantis Block G ✕ `runner.py --mode fast` (10 切片平行物理對抗審查 `agy.exe --sandbox`) ✕ Harness² Ledger 守恆
> **審查判定**: **`10 / 10` `DISMISSED` (Verified Safe Post-Patch)**（`0 confirmed`, `0 inconclusive`, `SENTINEL_RC=0`）
> **台帳守恆驗證**: `464` Targets (`53` verified/unresolved + `224` remediated + `187` dismissed/safe = `464`, `scripts/validate_security_ledger.py RC=0`)

---

## 1. 執行摘要與沙盒實證 (Executive Summary)

1. **Phase 0 Pre-Execution Worktree Spiking (`.worktrees/sentinel-planb-sandbox`) Red→Green PoC 實證**：
   - **Mantis Block G Benign Control (Pre-Patch)**：
     - 後端 `BE_BENIGN_RC=0` (`4 passed`: 2,400-char `GeocodeSearchRequest` 既有測試、`ChatRequest`、`_extract_clean_place_query`、`rerank_top_k`、`clean_conversational_query`、`geocode_service.ARCGIS_API_KEY`、`url_safety` 基本規則、Wikimedia SVG-to-PNG 縮圖代理)。
     - 前端 `FE_BENIGN_RC=0` (`1 passed`: `extractCleanPlaceQuery` / `extractPlaceParentheticalNote` 括號清洗與備註提取)。
   - **Pre-Patch Red Check (Unpatched `08b06df`)**：
     - 後端 `BE_RED_RC=1` (`11 / 11 failed`：`GeocodeSearchRequest`/`ChatRequest` 無 `max_length`、`smart_geocode_logic` 入口未截斷 (`1799 > 500`)、`_PAREN_REMARK_RE` 實測 60k 空白耗時 **`11.9838s`** 二次方 ReDoS、`_STATION_STRIP_RE` 與 `clean_conversational_query` 二次方正則、ArcGIS 退役 static-maps URL 明文洩漏 `ARCGIS_API_KEY`、`httpx`/`httpx2` INFO 日誌未壓制、缺 4-thread `_DNS_SAFETY_EXECUTOR` 與 `is_safe_url_async`、短網址子字串比對遭 `evil.com/?r=maps.app.goo.gl` 偽造且 iOS 分享字串破壞 GAS Rescue、OG 抓取未採 2 MB 串流上限、`safe_download_image` 留存 `localhost`/`127.0.0.1` 旁路且未串流限容、`poi_resolve_link` 缺 SlowAPI `request: Request` 簽名、`media_proxy` 放行 SVG / 未嚴驗主機 / 無 10 MB 上限且遭 `main.py` 中介軟體覆寫 CSP)。
     - 前端 `FE_RED_RC=1` (`1 / 1 failed`: `PAREN_REMARK_GLOBAL_RE` 含前導 `\s*` 二次方回溯)。
   - **Post-Patch Green Check (Sandbox + Main Workspace)**：
     - 沙盒全量：`pytest -q` (**`846 passed, 5 skipped`**, `SB_FULL_PYTEST_RC=0`, `-W error::RuntimeWarning` `ZERO_WARN_RC=0`)、`npx tsc --noEmit` (`0 errors`)、`npm run lint` (`0 errors, 0 warnings`)、`npx vitest run` (**`135/135 files, 1249 passed | 4 skipped`**)、`npx next build --webpack` (`RC=0`)。
     - 主工作區全量：`pytest -q` (**`846 passed, 5 skipped`**, `MAIN_PYTEST_RC=0`)、`npx tsc --noEmit` (`MAIN_TSC_RC=0`)、`npm run lint` (`MAIN_LINT_RC=0`)、`npx vitest run` (**`135/135 files, 1249 passed | 4 skipped`**, `MAIN_VITEST_RC=0`)、`npx next build` Turbopack (`MAIN_NEXT_BUILD_RC=0`)、`python scripts/neural_seam_harness.py` (`MAIN_SEAM_RC=0`, 10/10 Seams Intact)。
2. **Security Sentinel CLI (`runner.py --mode fast`)**：
   - 10 切片平行物理隔離審核 (`agy.exe --sandbox`)：**`10 / 10 DISMISSED`** (`0 confirmed`, `0 inconclusive`, `SENTINEL_RC=0`)。

---

## 2. 攻擊面覆蓋矩陣 (Attack Surface Coverage Matrix)

| Target ID | Trust Boundary | Attack Vector | Pre-Patch PoC | Post-Patch Sentinel Verdict |
|---|---|---|---|---|
| `backend/models/base.py:geocode_and_chat_length_bounds` | `public_to_authenticated` | `unbounded_input_validation_and_resource_budget` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |
| `backend/services/geocode_service.py:regex_linear_time_and_entry_truncation` | `authenticated_to_internal` | `regex_backtracking_complexity_and_whitespace_normalization` | `RED_RC=1` (`11.98s`) | `DISMISSED` (`REMEDIATED`) |
| `frontend/lib/location-utils.ts:paren_remark_linear_time_regex` | `browser_to_edge` | `client_regex_complexity_and_remark_extraction` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |
| `backend/services/destination_taxonomy.py:conversational_query_rstrip_linear_time` | `authenticated_to_internal` | `trailing_punctuation_regex_complexity` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |
| `backend/main.py:http_client_log_level_and_csp_setdefault` | `browser_to_edge` | `outbound_url_token_logging_and_header_preservation` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |
| `backend/utils/url_safety.py:dedicated_dns_bulkhead_executor` | `authenticated_to_internal` | `async_dns_resolution_isolation_and_fail_closed_timeout` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |
| `backend/routers/ai.py:safe_download_image_streaming_and_ssrf_guard` | `authenticated_to_internal` | `outbound_image_fetch_validation_and_memory_cap` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |
| `backend/services/link_resolver.py:shortlink_hostname_bounded_stream_and_ios_rescue` | `public_to_authenticated` | `shortlink_hostname_matching_and_bounded_html_decoding` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |
| `backend/services/web_search_engine.py:opengraph_bounded_streaming_and_async_url_check` | `authenticated_to_internal` | `unbounded_html_response_buffering_and_async_validation` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |
| `backend/routers/poi.py:resolve_link_and_media_proxy_hardening` | `browser_to_edge` | `media_proxy_host_validation_svg_rejection_size_cap_and_csp` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |

---

## 3. 切斯特頓圍欄三問考古與刪除審查 (Code Archaeology & Deletion Audit)

| 變更檔案與位置 | 刪除／替換內容 | 歷史功能與設計初衷 (`legacy_function` & `design_intent`) | 刪除風險與 100% 承接機制 (`regression_risk`) |
|---|---|---|---|
| `backend/services/link_resolver.py` (原 L615-631) | 刪除 `static-maps-api.arcgis.com/...token={arcgis_key}` 靜態圖回退區塊 | 早期在 Google Maps OG 無封面圖時，透過 Esri Beta 靜態圖 API 產生預覽縮圖。 | Esri 已下線該 Beta 端點 (`410 Gone`)，且原設計將伺服器秘密 `ARCGIS_API_KEY` 直接明文回傳至前端 JSON 造成憑證外洩；刪除後 `result["metadata"]["image"]` 優雅保持 `None` 由前端既有 fallback 佔位圖承接，且 `geocode_service.py` 伺服端地理編碼 `ARCGIS_API_KEY` 100% 完整保留。 |
| `backend/routers/ai.py` (`safe_download_image` 原 L75-78) | 刪除 `if domain in ["localhost", "127.0.0.1"]: pass` 旁路，並以 `create_safe_client(follow_redirects=False)` + 20 MB 串流取代裸 `httpx.AsyncClient.get()` | 早期開發環境曾想方便抓取本機測試圖片，並直接緩衝完整回應再檢驗長度。 | 生產環境無條件放行本機迴路屬於高危 SSRF 旁路，且全量緩衝 `response.content` 易致 OOM；改為統一 `is_safe_url_async` + `create_safe_client(follow_redirects=False)` + 20 MB 分塊上限＋`; charset=...` 正規化（保留 `.heic`/`.heif` 路徑辨識）＋顯式 `except HTTPException: raise` 與 `SSRFSecurityError -> 400` 100% 安全承接。 |
| `backend/services/geocode_service.py` (`_PAREN_REMARK_RE`, `_STATION_STRIP_RE`) & `frontend/lib/location-utils.ts` (`PAREN_REMARK_GLOBAL_RE`) | 移除前導 `\s*`，改以單一空白搭配 `rerank_top_k` 前置 `re.sub(r"\s+", " ", v).strip()` | 清理括號備註與英文車站尾詞時順帶吃掉多餘空白。 | 前導 `\s*` 與未錨定前部 `\s+` 實測引發 `11.98s` 二次方回溯；前後端既有下游皆已執行 `\s+` 折疊與 `.strip()`，`rerank_top_k` 前置正規化 `norm_v` 100% 承接多空白站名剝除。 |
| `backend/services/destination_taxonomy.py` (L307, L309) | 以 `rstrip("嗎？?~～!！.")` / `rstrip("嗎呢？?~～!！.")` 取代 `[...]+$` 正則 | 去除中文問句尾端語氣詞與標點。 | `[...]+$` 在長串標點尾接非標點字元時呈 $O(N^2)$ 回溯；`str.rstrip(...)` 與原字元集語意 100% 等價且為 C 層級線性時間。 |
| `backend/services/link_resolver.py` (原 L341-366) | 調換 Step 0.5 URL 萃取至 `original_input_url` 賦值與 Step 0 `g_st` 清除之前，並以 `_is_google_shortlink` 取代 `in` 子字串比對 | 舊邏輯先存 `original_input_url` 再對含換行/空白字串做萃取，以保留原始 `g_st` 供 GAS Rescue。 | 升級為嚴格主機名 `_is_google_shortlink` 後，若未先剝除 iOS 分享前綴文字與尾端標點，會導致 `original_input_url` 解析失敗而中斷 GAS Rescue；先萃取再賦值 `original_input_url` 再清 `g_st` 同時兼顧防偽造與 iOS 分享救援 100% 承接。 |
| `backend/routers/poi.py` (`media_proxy` 原 L615-642) & `backend/main.py` (L334) | 以嚴格 `upload.wikimedia.org` 驗證、SVG/SVGZ 415 攔截、`client.send(req, stream=True)` 預檢與 10 MB 串流上限＋Vercel-grade sandbox CSP 取代舊實作；`main.py` 改用 `headers.setdefault` | 舊實作以 `startswith` 代理 Wikimedia 圖片、容許 `.svg` 且不限大小與錯誤狀態，並由全域中介軟體覆寫 CSP。 | 舊實作允許 SVG XSS、任意大檔 OOM 與 `upload.wikimedia.org` 憑證/埠口繞過；新實作完整保留 Wikimedia PNG 渲染縮圖（含 `.../320px-Flag.svg.png`）與正常 JPEG/PNG/GIF/WebP 圖片流，同時保證 `aclose()` 零連線洩漏並保留全站預設 CSP。 |

---

## 4. Deliverables 索引

- **後端回歸哨兵**: [`test_security_hardening_planb_sentinel.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_security_hardening_planb_sentinel.py)
- **前端回歸哨兵**: [`location-utils-redos-sentinel.test.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/location-utils-redos-sentinel.test.ts)
- **候選清單**: [`candidates_security_hardening_planb_2026-11-25.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/candidates/candidates_security_hardening_planb_2026-11-25.json)
- **Sentinel 結果**: [`findings_security_hardening_planb_2026-11-25.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/findings/findings_security_hardening_planb_2026-11-25.json)
- **統一補丁**: [`patch_candidate_security_hardening_planb_2026-11-25.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_security_hardening_planb_2026-11-25.diff)
- **覆蓋台帳**: [`security-coverage-ledger.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/security-coverage-ledger.json)
