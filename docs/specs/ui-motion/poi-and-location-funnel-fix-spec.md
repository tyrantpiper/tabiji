# 規格書：周邊探索修復、全球自由國家篩選與 iOS 時間膠囊 (POI Search, Global Country Filter & iOS Time Capsule Spec)

> **目標**: 徹底修復周邊 POI 搜尋 406 錯誤、落實真正的全球自由國家篩選（拒絕擺設），並將時間選擇器重構為 iOS 緊湊時間膠囊與快捷時段標籤。

---

## 1. 核心問題與根因剖析 (Root Cause Analysis)

### 1.1 周邊探索搜不到 (POI Search Failure)
- **現象**: 點擊周邊探索類別按鈕（美食、超商、熱門等），永遠回傳 `{"count": 0, "pois": []}`。
- **根因**: `backend/services/poi_service.py` 呼叫 `overpass-api.de` 時缺少 `User-Agent` 與 `Accept` headers，Overpass 公共伺服器拒絕未帶身分的 Python httpx client，回傳 `406 Not Acceptable`；OpenTripMap 則因缺少 API Key 回傳 `401`，造成 POI 結果完全歸零。
- **解決方案**:
  1. `search_overpass` 注入標準 `User-Agent: TabidachiTravelApp/1.0 (contact@tabidachi.app)` 與 `Accept: application/json`。
  2. 建立多節點 Overpass 鏡像備援鏈。
  3. 修正 `search_poi_combined` 合併邏輯，不再因缺少 `wikidata_id` 誤殺 POI。

### 1.2 國家篩選被地標庫穿透 (Country Filter Bypass)
- **現象**: 即使在國家選擇台灣 (TW)，搜尋「新宿」仍然回傳日本新宿。
- **根因**: `backend/services/geocode_service.py` 中的 `smart_geocode_logic` 在 `translate_famous_landmark` 命中地標時，直接執行 `INSTANT RETURN`，**未比對使用者的 `api_country_lock`**。
- **解決方案**:
  1. 後端：在 `smart_geocode_logic` 的 `INSTANT RETURN` 處嚴格校驗：若 `api_country_lock` 存在且與地標國別不一致，強制跳過 instant return，進入真實的鎖定國別搜尋。
  2. 前端：改為「即時自由輸入框 (附帶自動推薦清單)」，使用者可自由手打輸入世界上任何國家（冰島、瑞士、紐西蘭、埃及等），亦可點擊下拉推薦快速帶入。

### 1.3 時間選擇器排版空曠與美化 (iOS Time Capsule)
- **現象**: `justify-between` 導致左側「時間」與右側細長時間輸入框分居兩極端，中間死白空曠，視覺粗糙。
- **解決方案**:
  1. 改為左靠緊湊結構：展示「🕒 出發時間」與高質感磨砂時間輸入膠囊。
  2. 內嵌快捷時段標籤：提供「早 09:00」、「午 12:00」、「傍 18:00」、「夜 21:00」快速膠囊，一鍵切換。

---

## 2. 驗收標準 (Acceptance Criteria)

- **AC-1 (POI 搜尋正常運作)**: 在地圖座標點（如 35.6895, 139.6917）點擊美食/超商/熱門等類別，API 必須成功回傳真實 POI 清單，前端卡片正常展示。
- **AC-2 (全球自由國家篩選)**: 國家篩選框支援自由鍵入任意國家（如「冰島」、「瑞士」），且若在國家輸入「台灣」時搜尋「新宿」，系統不得回傳日本新宿，必須遵循國家鎖定。
- **AC-3 (iOS 時間膠囊美化)**: 時間欄位不再極端兩端對齊，呈現緊湊精緻膠囊，並包含快捷時段按鈕。
- **AC-4 (品質關卡)**: `npx tsc --noEmit` 零錯誤，`npm run lint` 零錯誤，全套單元測試 100% 通過。
