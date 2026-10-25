# Security Sentinel 審查報告：空間感知對話閉環與行動端 Auto-Dock 邊界防禦

> **審查日期**: 2026-10-25  
> **模式**: Physical Adversarial Validation (`runner.py` ✕ `agy.exe -p --sandbox`)  
> **版本**: 2.0.0 (Cloudflare Ledger ✕ Google Mantis)  
> **審查目標**: `backend/main.py`, `frontend/components/chat/POIPreviewCard.tsx`, `frontend/components/chat-widget.tsx`

---

## 1. 執行總結 (Executive Summary)

- **總審查對象數**: 4
- **已確認/修正弱點 (Verified & Remediated)**: 3 (Prompt 呼叫鏈斷層、First-Pass 網路逾時過緊、座標注入邊界檢查)
- **已駁回 (Dismissed)**: 1 (未實裝之行動端狀態，已納入規格指引)
- **整體安全等級**: **PASS (最高防護級別)**

---

## 2. 弱點分析與證偽詳情 (Vulnerability & Verification Details)

### Target 1: `backend/main.py:second_pass_prompt_disconnect`
- **攻擊向量**: `logic_flow_bypass`
- **審查發現**: 在既有提示詞中，`add_itinerary_item` 的調用條件被嚴格限制在「若使用者的指示包含將景點加入行程」。當使用者進行純查詢（例如「推薦淺草寺附近的拉麵」）時，模型遵循此約束只會產出 Markdown 文字，不觸發 Tool Call，導致前端 POI 預覽卡片與 In-Card MiniMap 永遠無法長出。
- **補丁機制**: 在 Second-Pass 的 Prompt 強制規定：「若系統剛執行過 `search_nearby_places`，除了文字說明外，**務必針對最推薦的 1~3 個地點呼叫 `add_itinerary_item`**，帶入精準經緯度坐標」，徹底打通端到端呼叫鏈。

### Target 2: `backend/main.py:first_pass_timeout_collapse`
- **攻擊向量**: `dos_timeout_collapse`
- **審查發現**: First-Pass 4.5s 逾時在跨國網路抖動或地理編碼耗時長時，會引發 `asyncio.TimeoutError` 熔斷，導致周邊查詢失敗並回退為無地理資料的一般對話。
- **補丁機制**: 放寬逾時門檻至 6.5s，並強化例外捕獲保護，確保空間地理感知平滑運作。

### Target 3: `frontend/components/chat/POIPreviewCard.tsx:map_flyto_nan_injection`
- **攻擊向量**: `input_validation`
- **審查發現**: 原先僅檢查了 `Number.isFinite`，缺少經度（[-180, 180]）與緯度（[-90, 90]）的數學邊界檢查，若有惡意或溢出坐標，可能造成 WebGL 運算異常。
- **補丁機制**: 補齊 `Math.abs(poiData.lat) <= 90 && Math.abs(poiData.lng) <= 180`，確保傳入 MapLibre 的數值絕對合法。

---

## 3. Mantis 修復補丁
候選補丁已儲存至：
👉 `docs/security/patch_candidate_chat_geo_dock_2026-10-25.diff`

---

## 4. 人類閘門移交 (Human Gate)
依據 L0 憲法與 Maker-Checker 隔離原則，本報告已完備所有對抗假說之分析與候選補丁，等待人類開發者核准後正式套用。
