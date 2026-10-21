# 領域知識庫：後端高併發、資料庫與健康架構 (backend_concurrency)

> **所屬領域**: FastAPI, Python 3.11+, Cloudflare D1, Supabase (PostgreSQL), Uvicorn, LinkResolver

## 🏛️ 架構決策 (Decisions)
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
- **FP-051 (Uvicorn 靜態進程重載陷阱)**: main.py 為了防止 Windows CLOSE_WAIT 關閉了 reload=True。新增 FastAPI 端點後必須手動重啟 Python 進程。
- **FP-052 (Edge Shield 白名單遺漏)**: 前端直通 D1 的新端點必須同步在 POI_POOL_ENDPOINTS 白名單登記並 wrangler deploy。
- **FP-053 (D1 SQLite UPSERT 遺漏門牌欄位)**: batchInsertPois 的 ON CONFLICT DO UPDATE SET 曾漏掉 address，資料層新增欄位必須同步檢查 UPSERT 子句。
- **FP-054 (Cloudflare Worker 硬編碼白名單)**: validCategories 寫死陣列曾阻斷自訂類別，已升級 isValidCategory 放行 custom: 協定。
- **FP-061 (PostgreSQL RLS 型別比對運算子遺漏陷阱)**: 在 Supabase RLS Policy 中撰寫 `auth.uid()::text = user_id` 時，若 `user_id` 為 `UUID` 型別，PostgreSQL 會報 `operator does not exist: text = uuid` (42883) 阻斷 Migration。修復準則：一律採用 `auth.uid()::text = user_id::text` 進行雙邊字串歸一化比對。
