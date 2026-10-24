# 領域知識庫：後端高併發、資料庫與健康架構 (backend_concurrency)

> **所屬領域**: FastAPI, Python 3.11+, Cloudflare D1, Supabase (PostgreSQL), Uvicorn, LinkResolver

## 🏛️ 架構決策 (Decisions)
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
