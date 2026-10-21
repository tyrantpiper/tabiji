# 實作計畫：零成本 Google Maps 短網址解析、店名門牌解耦與偽座標覆寫根治 (Zero-Cost POI Resolver Implementation Plan)

## 🎯 核心目標
徹底修復手機版 Google Maps 短網址解析時，因美中機房引發的 Nebraska 偽座標漂移、標題混雜門牌郵遞區號，以及後續景點連環覆寫舊景點三大缺陷。完全在**零成本、不使用 Google 付費官方 API**原則下完成。

---

## 🛡️ 沙盒驗證前置狀態 (Pre-flight Sandbox Status)
- [x] In-Memory 沙盒 PoC 套件已建立：[`backend/tests/test_poi_zero_cost_resolver_sentinel.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_poi_zero_cost_resolver_sentinel.py)
- [x] 5 項對抗證偽沙盒測試 **100% 通過 (5/5 passed in 0.15s)**。
- [x] 後端全量測試 **180/180 全數通過，0 迴歸**。
- [x] 資安審計報告已歸檔：[`docs/security/reports/security_sentinel_report_2026-10-21_poi_zero_cost_resolver.md`](file:///d:/Project/tabiji/travel-pwa/docs/security/reports/security_sentinel_report_2026-10-21_poi_zero_cost_resolver.md)。
- [x] 資安帳本更新完畢：[`docs/security/security-coverage-ledger.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/security-coverage-ledger.json) (131 targets)。

---

## 📋 實施步驟明細 (Implementation Steps)

### Step 1: 後端解析器注入 Place RPC、地址分離器與偽座標熔斷
- **檔案**：[`backend/services/link_resolver.py`](file:///d:/Project/tabiji/travel-pwa/backend/services/link_resolver.py)
- **實作內容**：
  1. 實作 `split_taiwan_address_and_poi(raw_text)`，將 `807高雄市三民區十美里漢口街103號君腿庫飯` 拆解為門牌 `高雄市三民區漢口街103號` 與純店名 `君腿庫飯`。
  2. 實作 `fetch_place_from_google_rpc(cid_hex)`，自 URL 的 `ftid` 提取十六進位 CID，直接發起公開 Google Maps Web 端點請求（0成本、免金鑰），以遞歸正則匹配 `ChIJ...` place_id 與物理座標 `(lat, lng)`。
  3. 在 `fetch_og_metadata` 封殺純 `?q=` 網址的 staticmap center，並過濾 `zoom <= 10` 的國家級概覽中心，徹底免疫美中 Nebraska 座標。
  4. 在 `resolve_google_maps_link` 結尾串聯：若有 `ftid` 優先走 Place RPC；若無則走地址分離器並進行台灣定向地理編碼。

### Step 2: Cloudflare D1 寫入避免覆寫不同來源景點
- **檔案**：[`cloudflare/poi-service/worker.js`](file:///d:/Project/tabiji/travel-pwa/cloudflare/poi-service/worker.js)
- **實作內容**：
  1. 修改 `batchInsertPois` 的 `ON CONFLICT(user_id, lat, lng)` 語句，加入 `source_url` 保護子句，防止不同景點因偶發同座標被覆寫。
  2. 執行 `wrangler deploy` 部署至 Cloudflare 邊緣微服務。

### Step 3: 前端 SWR 快取更新升級
- **檔案**：[`frontend/lib/hooks/usePoiPool.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/lib/hooks/usePoiPool.ts)
- **實作內容**：
  1. 將 SWR mutate 的比對條件提升為 `item.id === c.id || (item.source_url && item.source_url === c.source_url)`。
  2. 杜絕前端因座標接近誤將新景點覆寫既有景點卡片。

### Step 4: 重啟本機 Python 守護進程並執行端到端實測
- 重啟 `python main.py`（PID 刷新，載入全新邏輯）。
- 本地測試兩大短網址解析：
  1. `https://maps.app.goo.gl/mmMsQpYNpLcE5GhE9?g_st=ic`（君腿庫飯）
  2. `https://maps.app.goo.gl/rHZYzoimiNDH39ua9?g_st=ic`（世外桃源土雞城）
- 驗證兩者座標各自獨立、店名純淨、地址精確，連續匯入不互相覆寫。

### Step 5: 全棧 Quality Gate 驗收
- Root Hygiene 檢驗。
- 前端 `npx tsc --noEmit` (0 錯誤)。
- 前端 `npm run lint` (0 警告)。
- 前端 `npx vitest run` (521/521 通過)。
- 後端 `pytest backend/tests` (185/185 通過)。
