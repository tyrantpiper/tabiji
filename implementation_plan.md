# POI 統一網址解析引擎與多地點共享清單萃取實施計畫

## 1. 任務背景與根因回顧
- **痛點**：使用者在 POI 口袋庫貼入 Google Maps 連結時，地名顯示為未解碼的 `%E8%80%81%E6%96%B0%E5%8F%B0%E8%8F%9C+(%E4%B9%9D%E5%A6%82...`，且門牌地址為空；此外無法批次匯入 Google 共享清單（Placelists）。
- **根因**：先前在 Cloudflare Worker 手刻了簡陋正則解析器，割裂了後端成熟的 `link_resolver.py`，既缺少 DNA 地名解碼，也沒有 Photon 地址反查與清單 RPC。
- **決策共識（來自 /grill-me）**：
  1. 回歸後端 `link_resolver.py` 作為全站「單一解析之源」。
  2. 後端擴展調研確證的 `entitylist/getlist` 內部 RPC，一口氣解析清單內 N 個地點（含標題、門牌地址、座標、備註）。
  3. 單點自動結合 Photon 逆向門牌地址反查，確保有像「幸福花園」一般的完整地址。
  4. 解析後由前端發送標準實體陣列至 Cloudflare D1 批次持久化。
  5. 純後端保證清洗，歷史髒資料由使用者在 UI 直接手動刪除。

---

## 2. 預計變更檔案清單

| 檔案路徑 | 變更性質 | 核心職責 |
| :--- | :--- | :--- |
| `backend/services/link_resolver.py` | 邏輯擴展 | 實作 `entitylist/getlist` RPC 共享清單萃取；單點解析自動附加 Photon 結構化門牌地址反查；地名嚴格 unquote 清洗。 |
| `backend/routers/poi.py` | 端點新增 | 新增 `POST /api/poi/resolve-link`，統一對接單點與清單解析，回傳標準化 POI 實體陣列。 |
| `frontend/app/api/poi/[...path]/route.ts` | 路由分流 | 將 `resolve-link` 轉發至 FastAPI 後端；將 CRUD 與 `batch-save` 轉發至 Cloudflare D1。 |
| `cloudflare/poi-service/worker.js` | 端點支援 | 確保 `POST /api/poi/batch-save` 能無縫接收後端傳來的標準陣列並原子寫入 D1。 |
| `frontend/lib/api.ts` | API 封裝 | 更新 `poiPoolApi.importLink`：先呼叫 `resolve-link` 解析，再將標準 items 寫入 D1。 |
| `frontend/lib/hooks/usePoiPool.ts` | 狀態更新 | 支援單點或多地點匯入後的即時 SWR mutate 與 IndexedDB 灌水，顯示精確成功筆數 toast。 |
| `backend/tests/test_poi_universal_resolver.py` | 測試守門 | 新增單元測試：驗證老新台菜短網址單點解析、地名乾淨度、地址存在性與 Placelist 解析。 |

---

## 3. 實施步驟

### 階段一：後端核心引擎擴展 (`backend/services/link_resolver.py`)
1. 實作 `resolve_google_maps_placelist(url)`：
   - 跟隨 302 重定向截獲清單 Token（匹配 `(?:!11m2!2s|/placelists/list/)([A-Za-z0-9_-]{16,})`）。
   - 調用 Google 內部 RPC `https://www.google.com/maps/preview/entitylist/getlist?pb=!1m4!1s{list_id}!2e1!3m1!1e1!2e2!3e2!4i2000`。
   - 脫除前綴 `)]}'\n`，提取 `item[2]` (title)、`item[1][4]` (address)、`item[1][5]` (lat, lng)、`item[3]` (user_notes)。
2. 在 `resolve_google_maps_link(url)` 單點解析流程中：
   - 取得座標後，呼叫 `reverse_geocode_with_photon(lat, lng)` 自動填補 `address`。
   - 地名透過 `urllib.parse.unquote_plus` 徹底解碼，並剔除 ` - Google 地圖` 等後綴。

### 階段二：後端端點與分流配置
1. 在 `backend/routers/poi.py` 實作 `POST /api/poi/resolve-link`：
   - 自動判斷輸入網址是 Placelist 還是 Single POI。
   - 統一包裝回傳結構：`{ success: true, count: len(items), items: [...] }`。
2. 在 `frontend/app/api/poi/[...path]/route.ts`：
   - 確保 `resolve-link` 導向後端 FastAPI，其餘導向 Cloudflare D1。

### 階段三：Cloudflare Worker 與前端管線串接
1. 在 `cloudflare/poi-service/worker.js`：
   - 確保 `POST /api/poi/batch-save`：接收 `{ items: [...] }`，直接使用 D1 `env.DB.batch()` 寫入，回傳插入結果。
2. 在 `frontend/lib/api.ts`：
   - 更新 `poiPoolApi.importLink(url, userId)`：先調用 `/api/poi/resolve-link` 解析，再調用 `/api/poi/batch-save` 存入 D1。
3. 在 `frontend/lib/hooks/usePoiPool.ts`：
   - 匯入成功後，將回傳的所有新項目原子推入 SWR 快取與 IndexedDB。

### 階段四：自動化驗證與守門
1. 執行 `pytest backend/tests`：確保既有 171 測試全數通過，並新增 `test_poi_universal_resolver.py`。
2. 執行 `npx tsc --noEmit`：確保前端型別 0 錯誤。
3. 執行 `npm test`：確保既有 79 份前端測試套件 100% 通過。
4. 真機/終端驗證：測試老新台菜短網址 `https://maps.app.goo.gl/mXQjEKhJSDfJkWi17`，驗證標題為「老新台菜 (九如創始店)」，地址為真實街道門牌。
