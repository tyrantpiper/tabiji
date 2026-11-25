# 領域知識庫：後端高併發、資料庫與健康架構 (backend_concurrency)

> **所屬領域**: FastAPI, Python 3.11+, Cloudflare D1, Supabase (PostgreSQL), Uvicorn, LinkResolver

## 🏛️ 架構決策 (Decisions)
- **多端點協作私密隔離、信用卡五不變量歸屬防奪權、私密景點 BOLA 與孤兒系統行程 GDPR 契約 (AD-251)**: GET /api/trips、/itinerary/latest 與 /api/trips/{trip_id} 必共用統一 _is_trip_creator（查 user_trips_view 時強制 allow_legacy_user_id=False，因該視圖 user_id 為查詢者自身 ID）、_filter_private_day_items 與 _filter_private_cards（脫敏非本人 creator_id 為 mem_*）。PATCH /day-data 與 /info 必保留資料庫中他方隱藏私密項、嚴格綁定 JWT user_id、將非布林 is_private/is_public 一律歸一為 false、同批 credit_cards ID 去重並對碰撞隱藏私卡 ID 重新配號，且嚴禁非建立者奪取或將公開卡私密化。私密 itinerary_items 之建立/修改/刪除/重排/匯入全面實施房主限定 403，前端 ActivityEditModal 對協作者隱藏私密開關。GDPR DELETE /api/user/{uid}/data 除使用者自建行程外，亦須回收已無其他 trip_members 之獨居 created_by='SYSTEM' 範例行程及其 Cloudinary photo_url。

- **Zero-Redis Pure Postgres 原子 RPC、HTTP/1.1 執行緒安全 Supabase 連線池與前端 Info/Card 離線回滾契約 (AD-253)**: Cloud Run 多實例併發寫入 `itineraries.content` JSONB（涵蓋 `day-data`、`info`、`location`、`import-to-trip`、`POST/DELETE ai-review` 共 6 大寫手）改以 3 支 `SECURITY DEFINER`、`SET search_path TO 'public', 'pg_temp'`、僅授權 `service_role` 之 Postgres 17 RPC (`patch_trip_day_data_atomic`、`patch_trip_info_atomic`、`merge_trip_import_content_atomic`) 透過 `FOR NO KEY UPDATE`（不阻塞子表外鍵 `FOR KEY SHARE`）＋交易局部 `lock_timeout=3000ms`／`statement_timeout=8000ms`＋頂層 `v_content || jsonb_build_object(...)`（杜絕 2 層 `jsonb_set_lax` 於 `{}`/`NULL` 靜默丟失與 `STRICT` `jsonb_set` 清空）單交易原子完成，並強制 SQL/Python 雙端嚴格布林正規化（`is_public`/`is_private` 僅認真布林 `true`，寫入端將非布林一律歸一為 `false` 防毒卡無限複製與幽靈私密項）、`v_seen_ids` 防同批重複卡 ID、匯入端拒絕非陣列覆寫既有私密陣列，並同步 `DROP FUNCTION IF EXISTS public.update_trip_credit_cards(UUID, JSONB)` 及為 `webhook_cleanup_cloudinary` 補上 `itineraries` `UPDATE` `cover_image` 單欄 no-op 守衛（對齊線上 `cleanup-cloudinary` v8）。後端透過 `create_threadsafe_supabase_client()` 以 `httpx.Client(http2=False)` 建立執行緒安全 HTTP/1.1 連線池（規避 `httpcore 1.0.9 HTTP2Connection` 無鎖 `_h2_state` `StreamIDTooLowError`）並預熱 `.postgrest`、關閉於 Lifespan shutdown；路由經 `UUID_V4_REGEX.fullmatch` 預檢（防 `22P02` 變 500）、`NonCallableMock` 偵測、`ENABLE_ATOMIC_TRIP_RPC` 熔斷開關、`await run_in_threadpool`、`55P03`/`40P01` 單次短退避重試→`409` 與 `PGRST202` 安全降級，且 `/info` 500 脫敏。前端 `tripsApi.updateInfo` 全面改走 `offlineFetch`（JWT + 401 換票 + `Idempotency-Key` + 離線/Lie-Fi 佇列），`tools-view.tsx` 改呼 `tripsApi.updateInfo`（失敗必回滾且不誤清 `localStorage`、離線略過 `tripMutate()`、提交後隔離 SWR 重抓錯誤、無行程私卡落盤本地），`sync-hooks.ts` 線上分支補齊 JWT 與 401 單次重試，`info-view.tsx` 以 `lastSyncedTripRef` 防止離線存檔結束編輯時被舊 `activeTripData` 反寫覆蓋、以 `(activeTripId, hotelIdx)` 作用域化 `preserveInnerDraftRef` 與 `isSavingInnerRef` 防連點及跨行程草稿外洩，失敗回滾 `hotels` 並完整保留 `tempHotel` 草稿。

- **Full-List Top-K 六維重排、Pass 1a/1b 全詞地標閘門與安全 Fusion 契約 (AD-245)**: GeocodeSearchRequest.limit 預設 None (上游抓 25 筆，limit=1 時 upstream_limit>=15)，strict=False 嚴禁硬刪跨國候選，全量經 rerank_top_k 重排。LANDMARKS_DB 必拆 Pass 1a (主鍵/顯示名精確優先) -> Pass 1b (別名)，全距離強制 _is_exact_landmark_match 且排除連鎖品牌，HOMONYM_GUARD_KEYS 採精確裸詞比對且僅 lat is None 或 >80km 禁秒回；軟 coord_country 不得阻斷無歧義全球地標，禁止 chinese_display 覆寫分店名；BRANDS_DB 限 JP 且 Step 2a/2b 剝除 _BRAND_GENERIC_TAIL_TOKENS。cjk_text_similarity 採短子集折減 (<0.80) + 保序子序列含雙字 Bigram (>=0.85) + Bigram 召回保護；跨語系保底限 not in variant_scripts (0.65)；分源 _batch_rank (0.45..0.15) 對齊 Photon/Nominatim 權威尺度；區分料理詞與城市/次區/地標前綴空間錨點 (次區半衰期 5km)；括號/時間前綴直達清洗並於低分 (<0.55) 單次降級；smart_search Fusion 禁灌東京預設座標、採 cuisine 軟過濾且不二次重排 base_list。

- **公用 Photon 反直覺參數校正、Event-Loop 分桶 Nominatim 鎖與港澳 SAR 邊界契約 (AD-244)**: Photon location_bias_scale 代表全球重要度權重 ((1 - scale) 為距離權重)，必須依整數 params['zoom'] (0..18) 反轉設定為 z>=14->0.2、z>10->0.4、z<=10->0.7；嚴禁同 q 空白拼接雙變體 (Operator.And 歸零) 或硬過濾 osm_tag。Nominatim 1 req/s 全域鎖必須以 weakref.WeakKeyDictionary 依 asyncio.get_running_loop() 分桶並導出 __reset_geocode_state_for_testing()，LLM 地址解析須置於鎖外。GEOCODE 自 INTENTS_ALLOW_GEMMA_LAST_RESORT 移除並設 0.9s 超時 + fast_fail + 1.8s 外層上限；無 Key 跨語系走 0ms 微字典 -> 1.2s Wikipedia langlinks (去括號)；HK/MO (_OSM_SAR_CODES) 以 COUNTRY_BOUNDS ±0.05° bbox 取代無效 countrycode=hk/mo；extent 一律正規化為 RFC 7946 [minLon, minLat, maxLon, maxLat] 並跨源回填 importance/admin_level/display_name。

- **長條收據前後端位元級一致縮放、原子直傳與 AI 實體圖片消毒契約 (AD-240)**: 前後端對 aspect > 2.0 長條收據與長截圖共用 s = min(1, 1200/short, 4096/long, sqrt(5_000_000/(W*H)))，後端 ai.py 採 int(orig_w * s + 0.5) + img.resize(..., LANCZOS) 對齊 JS Math.round()，且於模組頂層設 Image.MAX_IMAGE_PIXELS = 50_000_000。ExpenseDialog 須以 localReceipt: { url, dataUrl } 同源綁定並以 editItem.id 鍵值化初始化，於上傳 200 時直傳 body.image 並保留 receiptUrl 回退。/api/chat、/api/ai/parse-md 與 /api/ai/parse-receipt 必須強制 MIME 白名單、validate=True Base64、reject_unidentified=True 實體解碼／PDF %PDF- 驗簽，且 /api/chat 外層必先 except HTTPException: raise 杜絕吞掉 400。

- **Cloudinary 簽章端點雙層限流、嚴格白名單與原子輪換契約 (AD-238)**: POST /api/sign-cloudinary 僅存於 Cloud Run (backend/routers/cloudinary.py)，嚴禁於 Vercel 保存 CLOUDINARY_API_SECRET。必須經 _bind_verified_user_for_sign 先執行前置 OrderedDict LRU 右端 GFE X-Forwarded-For IP 限流 (240/min, 遍歷 getlist('x-forwarded-for') 且 IPv6 .lower()，429 帶 Retry-After 與 Cache-Control: no-store)，再執行 Depends(get_verified_user) 寫入 request.state.verified_user_id，供 SlowAPI @limiter.limit('60/minute') 以 uid:{uid.lower()} 分桶。強制 RFC 9110 §8.6 Content-Length + 4096B 串流截斷、無前導零非布林 timestamp (±600s)、public_id 僅限 ryan_travel/streetview 且匹配 ^mly_[0-9A-Za-z_-]{1,64}\Z、錯誤訊息禁用 gemini/api key/金鑰 關鍵字，並回傳原子 { signature, apiKey, cloudName } (Cache-Control: no-store)。

- **膠囊二階段正數位移、無 Key Wiki 保底與單索引街景引用計數契約 (AD-232, AD-233)**: 對具 (itinerary_id, day_number) 唯一鍵之時光膠囊平移天數，必須經 Postgres 原子 RPC (+10000 臨時偏移再寫目標值) 且限定 day_number > 0 保護 Day 0。webhook_cleanup_cloudinary 必須於單一表達式索引 idx_itinerary_items_mly_ref_id 下執行 to_jsonb(OLD) #- '{preview_metadata,mapillary_thumb}' 跨表引用計數（嚴禁 LIKE '%...' Seq Scan）。/api/poi/ai-enrich 無 API Key 時回傳 200 PARTIAL_SUCCESS（禁用快取寫入），且 agents Fallback 表須經 RLS + SHA-256 key_hash + conftest.py 測試隔離。

- **Supabase sb_* 非 JWT 金鑰標頭分離與禁止轉發瀏覽器 UA 法則 (AD-227)**: Supabase sb_publishable_* 與 sb_secret_* 非 JWT 格式，所有直連 PostgREST (/rest/v1/*) 與 Edge Functions 之 HTTP 請求必須透過 build_supabase_rest_headers() 僅置入 apikey 標頭並嚴禁放入 Authorization: Bearer（Authorization 僅保留給使用者 JWT）；且後端不得對 Supabase API Gateway 轉發使用者瀏覽器 User-Agent，避免觸發 Gateway 401 封鎖。

- **分層目的地推斷與動態年份檢索詞提煉契約 (AD-224)**: detect_destination() 嚴禁將查詢、對話歷史與行程標題縫合成單一字串後按字典序掃描（會使『台北出發・東京5天4夜』誤鎖 TW），必須嚴格依「當前查詢 -> 近期對話歷史 -> 行程目的地」階層優先解析；gemini-3.1-flash-lite 檢索詞提煉必須經 _sanitize_xml_boundary_text() 剝除控制字元與跳脫 XML 標籤並注入動態 {current_year}，主對話同時禁止無引註時強制復活 candidate_sources[:2]。

- **社群登入牆攔截與 OpenGraph 單次嘗試契約 (INV-BE-SOCIAL-LOGINWALL-01)**: fetch_opengraph_metadata() 與 fetch_jina_reader() 必須透過 _is_social_login_wall() 攔截社群登入牆，OpenGraph 命中時回傳 None、Jina HTTP 200 命中時回傳 error_code='LOGIN_WALL' 且維持 markdown=''，負向控制必須驗證含 Instagram 字樣之一般部落格不被誤判；同時因 main.py 對 fetch_jina_reader 設有 4.0s asyncio.wait_for 上限，Tier 1 已嘗試過 OpenGraph 之社群網址在 Tier 2 Jina 失敗時必須以 og_attempted 阻斷重複發送第二次相同 OpenGraph 請求，非社群網址保留 _og_fallback_or_error() 備援。

- **DB-to-Edge Webhook Vault HMAC 與純 Deno WebCrypto 清理雙軌契約**: 凡由 Postgres Trigger 經 pg_net 呼叫 Supabase Edge Function 之非同步清理流程，強制使用 Vault 密鑰 + HMAC-SHA256 防重放驗簽 (300s) 與純 Deno WebCrypto 簽名外部請求；禁止依賴 app.settings.* 或在 Edge Function 引入 npm:cloudinary，並須透過 net._http_response 實測 HTTP 200 回執率。

- **Antigravity Preview Agent 互動建立必須顯式指定 remote 環境**: 在調用 antigravity-preview-09-2026 的 interactions.create 時，請求參數必須顯式包含 environment="remote"；傳入不存在或已過期的 interaction_id 探針時後端必須回傳 400，並精準映射至 404/401/429 狀態碼。

- **各主流模型思考配置（Thinking Budget）相容性矩陣契約**: 思考模式配置存在嚴格的模型版本差異：Gemini 2.5 系列關閉/低思考使用數值型 thinking_budget=0；Gemini 3.8 系列採用枚舉型 ThinkingLevel.LOW / MEDIUM / HIGH；Gemma 4 系列採用 minimal / high 宣告。跨模型傳遞配置前必須經過適配矩陣轉換，嚴禁混用。

- **AI 異步客戶端快取需依 Event Loop 實例分桶並於 Shutdown 統一釋放**: 在測試環境或動態任務中，多個測試案例可能運行於不同的 asyncio 事件循環。全域 AI 客戶端快取必須以 id(asyncio.get_running_loop()) 作為快取分桶鍵，並在 FastAPI lifespan 關閉時遍歷關閉所有連線池，杜絕 Event loop is closed 殭屍連線警告。

- **免費金鑰 GoogleSearch 原生工具 429 嚴禁計入全域模型熔斷池**: Gemini 免費層呼叫原生 GoogleSearch() 產生的 429 屬於工具附加額度耗盡，非模型運算核心離線。此類錯誤絕不可傳遞至 record_model_error，避免將核心 Gemini 旗艦模型錯誤封鎖 300 秒。

- **Google GenAI Interactions SDK 異常捕獲須相容 compat_errors.APIStatusError**: google-genai==2.16.0 的 client.interactions.* 呼叫拋出的是 google.genai._gaos.lib.compat_errors.APIStatusError（屬性為 status_code），而非 genai_errors.APIError（屬性為 code）。後端異常攔截必須使用雙重元組 (genai_errors.APIError, _compat_errors.APIError)，並透過相容取值器提取 HTTP 狀態碼，避免 400/401/404/429 被誤判為 500。

- **公益進度查詢 Fail-Closed 原則與個人隱私去法幣化**: 贊助與公益進度 API 僅回傳百分比與狀態 {available, percentage, month}，絕對禁止包含任何法幣金額欄位以避免使用者誤解。後端拋錯或未啟用時前端自動隱藏且不發起重複請求，骨架屏依實際內容縮小避免 CLS。

- **行程資源存取授權、單列查詢安全、同步 SDK 線程隔離與對外錯誤遮蔽基線**: 所有行程子資源端點必須驗證房間成員權限（check_trip_access）；資料庫查詢禁止使用裸 .single()，應採用 _first_row 並安全回傳 404/403；async FastAPI 路由呼叫同步 Supabase SDK 必須使用 run_in_threadpool；全域例外處理器嚴禁對外回傳 traceback。

- **多語系全棧切換契約：UI locale 必傳且 Prompt 注入與分類快路徑全面聯動**: 使用者語言由前端介面 locale 明確決定，禁止由後端輸入隨意猜測。所有 AI 端點必須傳入 locale；SYSTEM_PROMPT、搜尋字串注入與行程評估 Prompt 依 locale 動態渲染；分類快路徑正則必須避免英文關鍵字（如 check）誤觸發繁體中文搜尋模板。

- **串流生成必須經由 Lookahead 滑動窗過濾裸 JSON 協定與內部思考標籤**: 模型輸出尾端偶發之 { items: [...] } 函數呼叫與 thought/thinking 思考標籤若直接以 event: text 推送會外洩系統提示詞。必須由 StreamLookaheadSanitizer 30 字元滑動窗進行前瞻緩衝，使用 json.JSONDecoder().raw_decode 識別閉合 JSON 並轉為 event: tool 推送。

- **SSE 心跳僅保連線存活，底層模型呼叫需獨立 wait_for 且逾時不計全域熔斷**: SSE 傳輸層 10s keep-alive 僅維持 HTTP 連線，google-genai SDK 預設 timeout=None 會在 upstream 異常時永久阻塞。模型呼叫必須以 asyncio.wait_for 設置端點逾時（無心跳 90s、SSE 120s）。逾時僅切換至下一備援模型，絕不可呼叫 record_model_error 誤鎖健康旗艦模型。

- **Single-Event-Loop ReDoS & Truncation Invariant**: Under single-process Uvicorn deployments on Google Cloud Run, synchronous regex execution on user-controlled text must enforce input truncation (e.g. raw[:800]) and bounded repetitions ({1,3}, {1,5}, [^<]{1,200}) without overlapping quantifiers. Unbounded polynomial backtracking freezes the asyncio event loop, severing active SSE client streams and inducing runaway container autoscaling.

- **Remote MCP OAuth 2.1 RFC 8414/9728 & Stateless HMAC Fallback**: OAuth 2.1 authorization server endpoints (/api/oauth/authorize & /token) must implement dual-track authorization codes: in-memory fast dict plus stateless HMAC-SHA256 token fallback to survive multi-instance Cloud Run server restarts and cross-container load balancing. CONSUMED_OAUTH_CODES replay table strictly enforces single-use token consumption.

- **AI Client CORS Preflight and Health Probe Compliance**: FastAPI CORS middleware must configure allow_origin_regex to permit browser-based preflight requests from AI clients (https://gemini.google.com, https://aistudio.google.com, https://*.perplexity.ai). Furthermore, /api/mcp must register both GET and HEAD handlers returning HTTP 200 with transport capabilities to pass external liveness probes before JSON-RPC initialization.

- **Remote MCP Reverse Proxy Base URL and RFC 9728 Invariant**: OAuth discovery endpoints (/.well-known/oauth-protected-resource and /.well-known/oauth-authorization-server) MUST dynamically resolve public base URL from x-forwarded-host and x-forwarded-proto with a strict TRUSTED_BASE_DOMAINS allowlist filter. Returning internal container origins (e.g. Cloud Run *.run.app) causes RFC 9728 Section 3 client-side identity mismatch and HTTP downgrade rejections.

- **Dual-Discovery Compliance RFC 8414 and RFC 9728**: Remote MCP servers MUST expose both /.well-known/oauth-authorization-server and /.well-known/oauth-protected-resource to satisfy discovery standards across both legacy and 2026-07-28 Model Context Protocol specifications.

- **AI Spatial Coordinate Sanity Gate**: Any latitude/longitude coordinates supplied by external AI agents MUST pass physical bounds validation (-90 <= lat <= 90, -180 <= lng <= 180, excluding 0,0) before database insertion. Invalid or missing coordinates MUST gracefully fallback to internal geocoding logic to prevent WebGL camera NaN fitBounds crashes.

- **Strict ToolResult Content Enveloping for Remote MCP**: All MCP tool handler responses dispatched to Gemini or third-party LLMs MUST be enveloped in {'content': [{'type': 'text', 'text': text_content}], 'isError': bool}. Returning raw dictionaries or primitive JSON causes client-side -32602 protocol rejections.

- **Fast-Lite Fallback Strategy for High-Latency Note Extraction**: In note extraction endpoints, routing_strategy MUST prioritize 'gemini-3.1-flash-lite' before 'gemini-3.5-flash-lite' and 'gemini-3.8-flash' to prevent Next.js dev server proxy from encountering 500 ECONNRESET (socket hang up) during upstream model retry backoffs.

- **RFC 7518 HMAC-SHA256 Minimum Key Length Threshold**: All HMAC-SHA256 (HS256) secrets in tests and production code MUST be at least 32 bytes (256 bits) long to comply with RFC 7518 Section 3.2 and eliminate PyJWT InsecureKeyLengthWarning.

- **Tag-First Extraction & Invisible Character Stripping Before Length Truncation (AD-199)**: In hybrid intent routing and admin hijack guardrails, user input wrapped in <user_input_{salt}> must first strip zero-width/Bidi control characters (INVISIBLE_CHARS_RE), advance past SYSTEM_BOUNDARY_END_RE, and extract content matching the exact closing outer_salt tag with trailing whitelist validation BEFORE applying 500-character ReDoS truncation.

- **Windows Terminal UTF-8 Reconfiguration Guard**: All standalone Python CLI utility scripts and test harnesses must include sys.stdout.reconfigure(encoding='utf-8') at initialization to prevent cp950 encoding crashes during stdout streaming on Windows platforms.

- **Two-Pass Geo Tool-Calling Injection Mandate**: Whenever nearby search executes in First-Pass, the coordinates and candidate places must be explicitly injected into the Second-Pass User Content with an unconditioned mandate to call add_itinerary_item.

- **State-Bifurcated Revocation Guard on /api/auth/rotate Endpoint**: POST /api/auth/rotate must depend on get_verified_session_with_grace. When db_ver > 1 (credential rotated), any incoming token where session.token_version < db_ver must be immediately rejected with HTTP 401 'Credential has been rotated. This session is revoked.', preventing revocation bypass attacks.

- **Projection Invariant for Encrypted Recovery Key**: get_user_record_by_id in backend/routers/auth.py must explicitly project 'recovery_key_encrypted' in Supabase select query to prevent vault decrypt returning None on legitimate upgrades.

- **State-Bifurcated Rotation Revocation Guard in Legacy UUID Path**: In /api/auth/session, when db_ver > 1 (credential rotated), any token with token_ver < db_ver MUST be rejected with HTTP 401, completely cutting off rotation bypass attacks while preserving 90-day grace upgrade for db_ver == 1.

- **Server-Side Expected User ID Assertion Before JWT Issuance**: In /api/auth/session, when expected_user_id is provided by the client, the backend must assert user['id'].strip().lower() == expected_user_id.strip().lower() BEFORE calling create_session_jwt. Mismatched identities must return 401 with zero tokens serialized in response body.

- **Dormant Device Grace Period Self-Healing Invariant**: Credential vault recovery endpoints must accept un-tampered server-signed tokens within a 90-day grace period to allow dormant devices to recover modern credentials.

- **Server-Side Credential Vault AES-256-GCM Invariant**: To support cross-device recovery key synchronization, the plaintext recovery key must be encrypted using AES-256-GCM derived via PBKDF2 from a server secret. Retrieval endpoints (/api/auth/credential) must strictly enforce caller JWT subject equality.

- **Anti-Tampering Soft Unlock for Revealed Time Capsules**: When a trip capsule is unlocked early on the final day, existing submitted entries are permanently frozen against updates (403 Forbidden) to prevent post-unveil tampering, while unsubmitted members may append their first entry until destination midnight.

- **Destination IANA Timezone Temporal Boundary Invariant**: All multi-day trip temporal boundaries (capsule locks, daily expenses, daily weather) must be evaluated against the destination IANA timezone [00:00:00, 23:59:59] converted to UTC. Never hardcode client or server local offsets.

- **Native Pydantic v2 Rust Serialization Pipeline**: Do not declare default_response_class=ORJSONResponse in FastAPI v0.115+. Rely on native pydantic-core Rust serialization to eliminate double-conversion overhead and suppress deprecation warnings.

- **Application Layer Memory Lookup for Masked Member References**: When an endpoint accepts an opaque or masked reference (e.g. mem_*), it must never query a PostgreSQL UUID column directly. Lookup must be conducted in memory against native ID and masked hash, and mutations must use the native UUID primary key.

- **Strict Authorization-Before-Deletion for Cascading Resources**: Any destructive endpoint (e.g. delete_trip) must verify caller ownership before executing ANY child table deletions (expenses, itinerary_items, trip_members). Unauthorized callers must be rejected immediately with 403 to prevent cross-tenant asset wiping.

- **批次更新跨租戶物件隔離與狀態碼穿透法則 (AD-150)**: 後端批次更新端點必須驗證傳入的所有 item_ids 隸屬於單一合法授權之行程 (len(itinerary_ids) == 1 且數量相等)，更新時一律限定 .eq('itinerary_id', tid) 杜絕跨租戶竄改；路由外層 try...except 區塊第一行必須顯式聲明 except HTTPException: raise，嚴禁通用 Exception 遮蔽業務安全狀態碼。

- **後端端點物件級授權（BOLA）與防身分替換約束法則 (AD-147)**: 所有涉及個人資料修改、刪除或行程內容注入之 API 端點，一律強制注入 Depends(get_verified_user)，嚴禁信任請求體傳入之 user_id；所有資源變更必須在資料庫層級驗證調用者為建立者 (created_by == user_id) 或行程協同成員 (trip_members 表存在)，不符者一律回傳 403 Forbidden。

- **1Password 私鑰與伺服端動態脫敏法則 (AD-144)**: 嚴禁將使用者 UUID 作為明文公開標籤（如行程成員 ID、記帳建立者 ID）直接回傳給協同者。所有日常 API 必須透過本地高速 HS256 JWT（0.05ms）完成驗證；行程與記帳端點對非本人查詢必須動態遮蔽為 mem_sha256(user_id + trip_id)[:10]，確保真金鑰永不洩漏。

- **台灣地址門牌與景點名稱決定性分離法則 (Deterministic Taiwan Address Separator)**: Google Maps 清單與公開端點獲取之文字，必須以 ADDRESS_POI_PATTERN 邊界正則決定性分離縣市區里路街號與店家名稱，嚴禁將地址前綴混入景點標題。

- **純記憶體存活探針與保活解耦**: /health 端點堅持 0ms 純記憶體計算，不觸發外部 I/O；Supabase 防休眠保活由 Lifespan 獨立背景定時循環守護。
- **三層健康檢查分流機制**: /health (Liveness, 0ms 純記憶體) vs /health/deep (Readiness, 2.5s 硬熔斷非同步檢查)。
- **後端時間處理時區原子一致性**: 啟動時間與請求計算統一採用 timezone.utc，杜絕 naive/aware 混用 TypeError 崩潰。
- **AI 座標直出 + 動態 Fallback 雙層保障**: AI 生成行程直出小數點後 4 位經緯度，_safe_geocode 僅對缺失景點補查，省去 80%+ 網路延遲。
- **母體區域繼承原則**: 行程景點地理編碼以母體目的地中心點為 Proximity Bias，國碼獨立解析注入，避免 country 欄位缺失。
- **原子日期平移與雙向位移保護**: 出發日提前採逆序迭代，延後採正序迭代，縮短行程提供 merge 與 delete 雙重保護。
- **Cloudflare D1 POI 微服務直通**: 徹底拔除後端 472 行舊版 CRUD 與 POI_POOL_STORE；全量 POI 口袋庫直通 Cloudflare D1 分散式邊緣資料庫 (Commit 8bc30e9)。
- **自包含純字串自訂類別協定**: custom:<emoji>:<name>:<colorHex> 自封裝於 category 欄位，無需 SQL migration，天然相容離線快取與動態收割。
- **冒號轉義與邊界切片防注入**: 序列化以 name.replaceAll(':', '：') 轉義，解析端採 parts.slice(2, -1).join(':')，顏色固定取末碼。
- **Google Maps Web RPC 脫殼與 XSSI 容錯防護法則 (Google Maps RPC & XSSI Stripping Invariance)**: 存取 Web 端點前必須以 re.sub(r"^\)\]\}'\s*", "", text) 脫除防跨站前綴；解析前由頂層 try-except 攔截 HTML 標頭以防 429/CAPTCHA 引發 JSONDecodeError 崩潰；自稠密陣列 d6 提取座標 (d6[9][2..3]) 與標題 (d6[11])，官方 Place ID 統一採 ^ChIJ[A-Za-z0-9_-]{20,}$ 邊界掃描萃取 (Commit 3979450)。
- **兩階段意圖路由與動態工具門控法則 (Two-Stage Intent Routing & Dynamic Tool Gating)**: 為杜絕移動端 2,180 tokens 全量工具注入造成的 2s+ KV-Cache 延遲與工具誤觸，必須採用 Stage 1 Fast-Path 正則分類器 (<1ms, 嚴格防禦 ReDoS) 與 Stage 2 動態門控：閒聊請求注入 0 工具，明確意圖僅注入單一對應 Schema，將 TTFT 壓制於 400ms 內 (PR #84)。
- **邊緣 D1 與核心 Supabase 異構雙庫權責劃分法則 (Edge-Core Polyglot Persistence Invariance)**: D1 專責承載無狀態、高頻讀取之全域個人 POI 口袋庫 (sub-10ms 邊緣直出，以 user_uuid 建立 idx_poi_user 複合索引防 5M 全表掃描計費巨坑)；Supabase 專責多日行程關聯時間軸與協作；景點加入行程時採副本分離，D1 原點永不刪除，徹底杜絕跨庫分散式事務。
- **Nebraska 美中偽座標熔斷機制**: 封殺純 ?q= 網址 staticmap center，過濾 zoom <= 10 國家級概覽中心，免疫座標漂移。
- **Supabase PostgREST 顯式 DAC 授權與 RLS 雙軌防衛法則 (AD-143)**: PostgreSQL 中 DAC 權限 (`GRANT`) 優先於 RLS。Supabase 2026-10-30 關閉 `public` 預設 ACL 後，所有新建或重構表格必須在同一 Migration 內顯式向 `anon`, `authenticated`, `service_role` 派發 DAC 存取權，否則 PostgREST 在 DAC 檢查階段即阻斷連線 (`42501`)；同時，跨型別 RLS 比較必須實施雙向純字串正規化 (`auth.uid()::text = user_id::text`)，防止 `operator does not exist: text = uuid` 型別崩潰。

## 🛡️ 踩坑記錄 (Failed Paths)
- **httpcore 1.0.9 HTTP/2 無鎖崩潰、Postgres 17 雙層 jsonb_set_lax 丟失與 useOfflineMutation 漏 JWT 陷阱 (FP-121)**: supabase-py 2.31.0 預設 httpx.Client(http2=True) 底層 httpcore 1.0.9 HTTP2Connection 無鎖修改 _h2_state，於 run_in_threadpool 多執行緒併發下 12/12 爆 StreamIDTooLowError/KeyError，必改以 ClientOptions(httpx_client=httpx.Client(http2=False)) 並於主執行緒預熱 .postgrest。Postgres 17 jsonb_set_lax('{}'::jsonb, ARRAY['day_notes','1'], val, true) 靜默回傳 '{}' 丟失空行程寫入，且 jsonb_set(..., NULL::jsonb, ...) 具 STRICT 特性會將整欄 content 抹為 NULL，必須先驗 jsonb_typeof(...)='object' 並改採頂層 v_content || jsonb_build_object(...)。前端 sync-hooks.ts 線上分支裸 fetch() 繞過 JWT 包裝造成線上信用卡編輯 100% 401 靜默蒸發，必須統一經 offlineFetch (tripsApi.updateInfo) 或於線上分支補齊 JWT 與 401 單次重試。

- **括號備註僅於 0 筆觸發降級導致 11 秒逾時與低分垃圾短路陷阱 (FP-117)**: 行程卡片含時間前綴與全/半形括號備註 (如 晴空塔（夜景拍照）、淺草寺 (雷門拍照)) 若等到尾端 0 筆才降級，會空燒 5-11 秒觸發存檔 3500ms 逾時或被低分垃圾結果 (如西安晴空之阁) 短路。必須前置清洗直查無歧義地標 (0.2s 秒回)，並於 Speculative Photon 0 筆或 Top-1 相似度 < 0.55 時單次降級重查。

- **CJK token_set_ratio 子集滿分、0.45->0.72 非單調斷崖與 Fusion 二次重排反轉陷阱 (FP-114)**: CJK 拆單字直用 fuzz.token_set_ratio 會使顛倒詞 (台中 vs 中台禪寺) 與短殘片 (大阪燒 vs 大阪) 拿滿分 1.0；跨語系保底寫 if fuzz < 0.45: max(..., 0.72) 會造成不及格雜訊反殺部分匹配結果；外層 routers/geocode.py 在無翻譯變體下對已排好之 base_list 二次呼叫 rerank_top_k 會破壞跨語系名次並反轉既有 smart_fusion 順序。

- **裸用模組級 asyncio.Lock 跨迴圈崩潰、model_manager 死條件與地標單輪別名劫持陷阱 (FP-113)**: 模組頂層裸建 asyncio.Lock() 在 pytest-asyncio 多迴圈必拋 bound to a different event loop；call_extraction 寫死 tag='Extraction' 且 GEOCODE 預設 45s 使 fast_fail 曾為死條件；LANDMARKS_DB 單輪依長度同時比對主鍵與別名導致嵐山->虹夕諾雅、景福宮->光化門站，且 LOCATION_KEYWORDS['JP'] 混入迪士尼/環球影城害巴黎迪士尼->泰國芭堤雅夜市、環球影城->高雄 YouBike。

- **ai.py 雙層 except Exception 靜默吞錯穿透 Gemini 與未凍結時鐘測試浮動陷阱 (FP-110)**: process_and_optimize_image_sync 預設 except Exception 回傳原始位元組為 image/jpeg，加上 main.py 外層 except Exception，會使偽裝成 image/jpeg 的 <svg> 繞過驗證直打 Gemini API 且跳過 parse-receipt 的 imageUrl 回退；此外時間戳偏移測試若未以 monkeypatch 凍結 cloudinary_router.time.time，跨秒邊界會令 now+601 偶發通過變 200 造成 CI 浮動。

- **SlowAPI 與 Depends 執行順序倒置及 CWE-290 多重 XFF / FIFO 驅逐繞過陷阱 (FP-106)**: FastAPI 會先執行 Depends(get_verified_user) 才進入 @limiter.limit 裝飾器，使 key_func 內未鑑權 IP fallback 成為死碼；僅用 request.headers.get('x-forwarded-for') 會被多重 XFF 標頭繞過；普通 dict 的 FIFO 驅逐會在滿表時將活躍攻擊 IP 計數歸零；UUID 大小寫未 .lower() 會拆成兩個 SlowAPI 分桶。必須以獨立前置 OrderedDict LRU 依賴 + getlist('x-forwarded-for') 逆序尾部解析 + uid.lower() 根治。

- **Secret Manager 尾端換行空白導致派生主密鑰分裂與 Vault 解密失敗陷阱 (FP-096)**: 以未經 .strip() 的原始密鑰位元組作為 PBKDF2/SHA-256 派生輸入時，GCP Secret Manager 版本若含尾端換行 (\r\n) 或空白會分裂產生多個 H1/H2 衍生金鑰版本（實測曾致 10/120 保險庫密文解不開）。密鑰派生與遷移驗證必須顯式考量 raw/strip 候選並原地統一重封裝單一乾淨主鑰。

- **google-genai 3.4+ v1 預設偏移與 Speakeasy 退避卡死陷阱 (FP-092)**: google-genai>=3.4.0 將預設 API 版本由 v1beta 變更為 v1 並切換至 httpx2。呼叫 gemini-decision-1 (client.aio.decisions.create) 必須顯式指定 api_version='v1beta' 且停用 SDK 內建 Speakeasy 4 次指數退避 (retry_config={'strategy':'none','max_retries':0})；呼叫 gemini-4-hydrogen 必須過濾 minimal 思考等級（改用 low/medium/high/xhigh）並清空 temperature/top_p/top_k/thinking_budget，且因 Free Tier 尾延遲達 12s–44s，同步路由維持 Flash-Lite 優先。

- **社群爬蟲 HTTP 200 登入牆偽陽性與無 Mock 外網測試陷阱 (FP-067)**: Instagram/Facebook 對雲端機房 IP（如 GitHub Actions Azure 或 Cloud Run）常回傳 HTTP 200 通用登入頁（登入 • Instagram / Login • Instagram / 歡迎回到 Instagram）而非 401/403。fetch_opengraph_metadata() 若未比對登入牆特徵會回傳 status='success' 污染 AI grounding_context_text；且 pytest 若直連外網社群網址將呈現本機通過、CI 紅燈。

- **Supabase Trigger 讀取 app.settings 靜默 NULL 造成 401 與套件欄位誤判**: Supabase 代管 Postgres 未預設 app.settings.service_role_key，Trigger 取值為 NULL 會引發 Webhook 連續 HTTP 401（實測曾累積 338 筆失敗）；同時 Deno Edge Runtime 無法運行含 vm2 的 npm:cloudinary，且 itineraries.public_id 為 pub_* 分享代碼而非 Cloudinary Asset ID。應改用 Vault cleanup_webhook_secret 搭配 SECURITY DEFINER + extensions.hmac(..., 'sha256') 與 verify_cleanup_webhook_signature RPC (300s 視窗)，Edge Function 使用純 Deno WebCrypto SHA-1，並以 DB 三表觸發器 (expenses/itineraries/itinerary_items) 搭配後端清理 users.avatar_url 與 trip_capsule_entries.photo_url。

- **Gemini 3.8 與 Gemma 系列 thought_signature 400 錯誤避免誤判為配置不支援**: 當 Gemini 3.8 或後續模型回傳 thought_signature 相關 400 INVALID_ARGUMENT 時，系統不可武斷將其歸類為 config_unsupported 觸發全域降級。應針對錯誤詳情進行精確模式比對，並在降級時優先剝離思考簽名配置進行原模型重試。

- **RPD 配額未滿卻頻繁遭遇 429 速率限制之四層成因與退避治理**: 429 觸發多源於短突發速率（RPM/TPM）或免費金鑰之付費 Grounding 工具耗盡，非每日總請求數（RPD）耗盡。移除 SEARCH 意圖之 First-Pass 雙重呼叫可降低 60% 瞬間突發；免費金鑰停用 Google 原生 Grounding；SlowAPI 改用金鑰雜湊分桶避免本機 127.0.0.1 誤限流；暫態 429 不計入 300s 熔斷池。

- **Gemma 4 深度思考延遲被誤診為模型未開放或端點崩潰**: Gemma 4 系列模型因原生思考延遲達 30~50s，若置於 <2s 之快速分類端點會被逾時中斷。不可在未經真實探測下誤診為模型未開放。Gemma 4 不適合高時效分類路徑；呼叫時工具宣告應採用 Depth=1 扁平化結構以避免 400 schema 衝突，純文字模式關閉自動函數呼叫。

- **意圖分類 1.8s 硬逾時無腦降級 SEARCH + mode=ANY 導致 28px 空白幽靈氣泡與對話中斷**: 分類逾時若強制降級為 SEARCH 意圖且以 ToolConfig(mode=ANY) 強制模型呼叫工具，會使讚美/問候語句輸出空文字，引發前端 28px 空白氣泡，下一輪遺失 model 訊息而觸發 Gemini 400 INVALID_ARGUMENT。分類逾時必須中性 fallback 為 CHAT/AUTO，並引入本地 Regex 0ms 短路判斷。

- **FastAPI Dependency Request Parameter Wrapping Crash**: Wrapping request parameter as Optional[Request] = None in FastAPI route dependencies causes Starlette reflection to fail with 'FastAPIError: Invalid args for response field!'. Must strictly declare request: Request = None without Optional, while declaring auth headers as Optional[str] = Header(None).

- **Action Noise False Geocoding Query Overhead**: Submitting activity notes like '集合/搭乘/休息/退稅' to geocoding services causes rate limit exhaustion and erroneous coordinates. Filter out items matching ACTION_NOISE_KEYWORDS before geocoding.

- **Next.js Dev Proxy Socket Hang Up under Gemini 3.8 Multi-Tier Backoff**: When calling Gemini 3.8 Flash for long markdown extraction, upstream 503 errors trigger exponential backoff exceeding 30s, causing Next.js dev proxy to drop connections with ECONNRESET. Use gemini-3.1-flash-lite (0.9s response) as the primary extraction model.

- **Strict Expire Lockout on Recovery Vault Trap**: Strictly enforcing 30-day token expiration on vault endpoints blocks offline or dormant devices from pulling updated credentials.

- **Post-Unveil Entry Modification Tampering Trap**: Allowing edits after early unveiling breaks trust. Existing entries must be locked upon unlock while allowing pending members to submit.

- **Hardcoded Destination Timezone Premature Freezing Trap**: Assuming Asia/Tokyo (UTC+9) for end-of-trip calculations freezes Western Hemisphere trips (e.g. EDT UTC-4) up to 13-19 hours prematurely. Always infer timezone from coordinates.

- **CDC Filter Column Name Mismatch (itinerary_id vs trip_id)**: Supabase CDC silently ignores subscriptions with non-existent column filters. Foreign key in expenses table is itinerary_id.

- **PostgreSQL 22P02 on Masked Reference SQL Query**: Passing mem_* masked strings into PostgreSQL UUID columns triggers 22P02 type mismatch. Isolate masked lookups in Python application memory.

- **FastAPI 通用 Exception 捕捉遮蔽 HTTPException 狀態碼陷阱**: 路由內部明確 raise HTTPException(status_code=400, detail='禁止跨行程批次排序')，但外層寫了 try: ... except Exception as e: return {'status': 'error'}，導致客戶端收到 500 或 200 error，前端無法辨識租戶安全拒絕。修復準則：FastAPI 路由若使用 try...except 區塊，第一行必須顯式聲明 except HTTPException: raise，確保受控的業務安全例外能原樣穿透。

- **Supabase select(count=exact) 在測試 Mock 環境回傳物件結構陷阱**: count_res = supabase.table('itineraries').select('id', count='exact').eq('created_by', user_id).execute() 在單元測試 MagicMock 中，count_res.count 回傳 MagicMock 物件而非整數，導致 int >= int 比較拋出 TypeError。修復準則：配額統計取值必須具備防禦性型別防護：raw_count = getattr(count_res, 'count', None); owned_count = raw_count if isinstance(raw_count, int) else len(count_res.data or [])。

- **歷史相容路徑之次級記帳接口未脫敏洩漏陷阱**: 雖然修復了 /api/expenses，但 backend/routers/trips.py 中保留的舊式相容接口 /{trip_id}/expenses 仍直接回傳原始 created_by 與 payer_id。修復準則：敏感憑證脫敏必須對所有路由別名與歷史跨模組端點進行全路徑拓撲掃描，杜絕次級通道洩漏。

- **PostgreSQL RLS 型別比對運算子遺漏陷阱**: 在 Supabase RLS Policy 中撰寫 auth.uid()::text = user_id 時，若 user_id 為 UUID 型別，PostgreSQL 會報 operator does not exist: text = uuid (42883) 阻斷 Migration。修復準則：一律採用 auth.uid()::text = user_id::text 進行雙邊字串歸一化比對。

- **FP-051 (Uvicorn 靜態進程重載陷阱)**: main.py 為了防止 Windows CLOSE_WAIT 關閉了 reload=True。新增 FastAPI 端點後必須手動重啟 Python 進程。
- **FP-052 (Edge Shield 白名單遺漏)**: 前端直通 D1 的新端點必須同步在 POI_POOL_ENDPOINTS 白名單登記並 wrangler deploy。
- **FP-053 (D1 SQLite UPSERT 遺漏門牌欄位)**: batchInsertPois 的 ON CONFLICT DO UPDATE SET 曾漏掉 address，資料層新增欄位必須同步檢查 UPSERT 子句。
- **FP-054 (Cloudflare Worker 硬編碼白名單)**: validCategories 寫死陣列曾阻斷自訂類別，已升級 isValidCategory 放行 custom: 協定。
- **FP-061 (PostgreSQL RLS 型別比對運算子遺漏陷阱)**: 在 Supabase RLS Policy 中撰寫 `auth.uid()::text = user_id` 時，若 `user_id` 為 `UUID` 型別，PostgreSQL 會報 `operator does not exist: text = uuid` (42883) 阻斷 Migration。修復準則：一律採用 `auth.uid()::text = user_id::text` 進行雙邊字串歸一化比對。
