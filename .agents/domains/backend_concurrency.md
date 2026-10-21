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
- **Google Maps Place RPC 零成本精確解析**: 自 URL ftid 提取十進位 CID 直連 Web 端點，0 成本獲取真實門牌、座標與 ChIJ... place_id (Commit 3979450)。
- **台灣門牌與店家名稱決定性分離器**: ADDRESS_POI_PATTERN 嚴格邊界正則精準分離門牌地址與景點名稱。
- **Nebraska 美中偽座標熔斷機制**: 封殺純 ?q= 網址 staticmap center，過濾 zoom <= 10 國家級概覽中心，免疫座標漂移。

## 🛡️ 踩坑記錄 (Failed Paths)
- **FP-051 (Uvicorn 靜態進程重載陷阱)**: main.py 為了防止 Windows CLOSE_WAIT 關閉了 reload=True。新增 FastAPI 端點後必須手動重啟 Python 進程。
- **FP-052 (Edge Shield 白名單遺漏)**: 前端直通 D1 的新端點必須同步在 POI_POOL_ENDPOINTS 白名單登記並 wrangler deploy。
- **FP-053 (D1 SQLite UPSERT 遺漏門牌欄位)**: batchInsertPois 的 ON CONFLICT DO UPDATE SET 曾漏掉 address，資料層新增欄位必須同步檢查 UPSERT 子句。
- **FP-054 (Cloudflare Worker 硬編碼白名單)**: validCategories 寫死陣列曾阻斷自訂類別，已升級 isValidCategory 放行 custom: 協定。
