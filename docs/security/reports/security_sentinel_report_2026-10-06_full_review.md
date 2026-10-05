# 🛡️ Security Sentinel 深度對抗審核報告 (24 個變更檔案全局審查)

> **稽核日期**: 2026-10-06  
> **審核模式**: 物理多進程子代理人對抗證偽 (`agy.exe -p --sandbox` via `runner.py`)  
> **被審目標**: Git Source Control 當前所有 24 個變動與未追蹤檔案  
> **審核原則**: 無罪推定直至實證成立 (Presumption of Innocence until Empirically Proven) / 建造者與審查者絕對物理隔離  

---

## 📊 1. 執行總結 (Executive Summary)

| 指標 | 數值 | 說明 |
| :--- | :---: | :--- |
| **變更檔案總數** | **24** | 包含 6 個 Modified、18 個 Untracked |
| **資安與邊界假說** | **7** | 涵蓋 Prompt 注入、ReDoS、型別污染、XSS、滾動鎖定洩漏、競爭條件 |
| **已證實防禦盲區 (CONFIRMED)** | **1** | `frontend/lib/itinerary-metrics.ts`（非陣列資料引發 `TypeError: d0 is not iterable` 崩潰） |
| **證偽無風險 (DISMISSED)** | **6** | 具備完備防禦或 React JSX Entity Encoding，杜絕注入與洩漏 |
| **密鑰與機密硬編碼** | **0** | 全站無任何 API Key、JWT Token、密碼外洩 |
| **靜態驗證狀態** | **PASS** | TypeScript 0 錯誤、ESLint 0 錯誤、Vitest 37 套件 289 項測試 100% 通過 |

---

## 🗺️ 2. 24 個檔案分類與信任邊界對照表 (Attack Surface Coverage Matrix)

### A. 後端服務層 (Backend Service Layer)
| 檔案路徑 | 信任邊界 | 審核結果 | 判定理由 |
| :--- | :--- | :---: | :--- |
| `backend/routers/ai.py` | `public_to_llm` | **SECURE** | 系統提示詞具備明確角色規範，設有 `<user_query>` 隔離圍欄與【安全守則】，嚴禁探查提示詞。 |

### B. 前端核心邏輯與計算 (Client Business Logic)
| 檔案路徑 | 信任邊界 | 審核結果 | 判定理由 |
| :--- | :--- | :---: | :--- |
| `frontend/lib/itinerary-metrics.ts` | `client_compute` | ⚠️ **PENDING_PATCH** | **已證實漏洞**：當 `store[0]` 或 `store[1]` 為非陣列時，展開運算子 `[...d0, ...d1]` 會拋出致命的 `TypeError: d0 is not iterable`。需加入 `Array.isArray()` 前置防禦。 |

### C. 前端 UI 組件與視圖 (Client UI & Presentation)
| 檔案路徑 | 信任邊界 | 審核結果 | 判定理由 |
| :--- | :--- | :---: | :--- |
| `frontend/components/itinerary/WeatherPanel.tsx` | `browser_render` | **SECURE** | 溫差分母具備 `Math.max(1, maxTemp - minTemp)` 零除防禦；文字經 JSX 自動轉義，無 XSS 風險。 |
| `frontend/components/itinerary/IOSBottomSheet.tsx` | `dom_and_gestures` | **SECURE** | `useEffect` 精確記錄並還原原始 `body.style.overflow`，組件 unmount 或快速切換時保證釋放。 |
| `frontend/components/itinerary/ItineraryDashboardHub.tsx` | `browser_render` | **SECURE** | 分數為 null/NaN 時安全降級為骨架/預設值，SVG 圓環與卡片排版無溢位崩潰。 |
| `frontend/components/itinerary/EditableDailyAIReview.tsx` | `browser_render` | **SECURE** | `formatReview` 使用原生 JSX `<p>` 標籤渲染，無 `dangerouslySetInnerHTML`，安全免疫 Stored XSS。 |
| `frontend/components/itinerary/EditableDailyTips.tsx` | `browser_render` | **SECURE** | `displaySection` 為純展示過濾，不影響 `onUpdate` 提交資料之完整性。 |
| `frontend/components/views/itinerary-view.tsx` | `browser_state` | **SECURE** | 天數切換時立即重設底抽狀態，資料同步取自 Zustand focusedDay，無非同步競爭污染。 |

### D. 前端測試套件 (Test Suites - 3 檔)
- `frontend/__tests__/itinerary-dashboard-layout.test.tsx` (PASS / 無機密洩漏)
- `frontend/__tests__/itinerary-dashboard-metrics.test.ts` (PASS / In-Memory 隔離)
- `frontend/__tests__/weather-panel-ios.test.tsx` (PASS / 無外部網路連線)

### E. 資安覆蓋帳本與報告 (Security Ledger & Artifacts - 8 檔)
- `docs/security/security-coverage-ledger.json` (格式合規)
- `docs/security/candidates-full-review.json` (候選清單)
- `docs/security/findings-full-review.json` (物理子代理人執行紀錄)
- 其他既有歷史 candidates / findings 檔案 (經 TruffleHog / 正則檢驗無 Token 洩漏)

### F. 架構設計與規格文件 (Architecture Specs - 5 檔)
- `docs/specs/ai/llm-itinerary-rubric-scoring-research.md`
- `docs/specs/ai/llm-itinerary-rubric-scoring-spec.md`
- `docs/specs/ui-motion/ios-expandable-itinerary-sections-research.md`
- `docs/specs/ui-motion/ios-expandable-itinerary-sections-spec.md`
- `docs/specs/ui-motion/ios-weather-bento-grid-architecture-spec.md`

---

## 🎯 3. 證實漏洞細節與 In-Memory 證偽證明 (Confirmed Vulnerability)

### 📌 目標: `frontend/lib/itinerary-metrics.ts`
- **弱點類型**: 邊界防禦缺失引發未捕獲例外 (Uncaught TypeError / Denial of Service)
- **觸發條件**:
  當行程資料快取、LocalStorage 或後端 API 回傳畸形/舊版本結構（例如 `dayChecklists: { "0": { "notes": "..." } }` 或非 Array 物件）時：
  程式執行到第 246-249 行：
  ```ts
  const d0 = store[0] || store["0"] || []
  const d1 = store[1] || store["1"] || []
  const map = new Map<string, ChecklistItem>()
  ;[...d0, ...d1].forEach(...) // 💥 拋出 TypeError: d0 is not iterable，頁面直接白屏！
  ```
- **In-Memory PoC 複現**:
  ```ts
  const malformedData = { "0": { items: [] } };
  // 執行 calculateChecklistProgress(malformedData, 1)
  // 結果: Uncaught TypeError: d0 is not iterable
  ```

---

## 🛠️ 4. 候選補丁 (Candidate Patch) 與 Block Replacement

依據 L0 憲法：「**@security 僅提出候選補丁，不得擅自修改程式碼，必須經由人類核准。**」

### A. RFC Unified Diff (`patch_candidate.diff`)
```diff
--- a/frontend/lib/itinerary-metrics.ts
+++ b/frontend/lib/itinerary-metrics.ts
@@ -204,7 +204,7 @@ export function calculateDayCostsSummary(
 
     if (!isNaN(rawAmount) && rawAmount > 0) {
-      const curr = (c.currency || defaultCurrency).toUpperCase()
+      const curr = String(c.currency || defaultCurrency).trim().toUpperCase()
       totalsByCurrency[curr] = (totalsByCurrency[curr] || 0) + rawAmount
     }
   }
@@ -244,8 +244,12 @@ export function calculateChecklistProgress(
 
   if (day === 1) {
-    const d0 = store[0] || store["0"] || []
-    const d1 = store[1] || store["1"] || []
+    const raw0 = store[0] !== undefined ? store[0] : store["0"]
+    const raw1 = store[1] !== undefined ? store[1] : store["1"]
+    const d0 = Array.isArray(raw0) ? raw0 : []
+    const d1 = Array.isArray(raw1) ? raw1 : []
     const map = new Map<string, ChecklistItem>()
     ;[...d0, ...d1].forEach((item) => {
```

### B. Exact Block Replacement Mapping
- **Target File**: `d:\Project\Tabidachi\travel-pwa\frontend\lib\itinerary-metrics.ts`
- **Target Content 1** (Line 204-207):
```ts
    if (!isNaN(rawAmount) && rawAmount > 0) {
      const curr = (c.currency || defaultCurrency).toUpperCase()
      totalsByCurrency[curr] = (totalsByCurrency[curr] || 0) + rawAmount
    }
```
- **Replacement Content 1**:
```ts
    if (!isNaN(rawAmount) && rawAmount > 0) {
      const curr = String(c.currency || defaultCurrency).trim().toUpperCase()
      totalsByCurrency[curr] = (totalsByCurrency[curr] || 0) + rawAmount
    }
```

- **Target Content 2** (Line 245-248):
```ts
  if (day === 1) {
    const d0 = store[0] || store["0"] || []
    const d1 = store[1] || store["1"] || []
    const map = new Map<string, ChecklistItem>()
```
- **Replacement Content 2**:
```ts
  if (day === 1) {
    const raw0 = store[0] !== undefined ? store[0] : store["0"]
    const raw1 = store[1] !== undefined ? store[1] : store["1"]
    const d0 = Array.isArray(raw0) ? raw0 : []
    const d1 = Array.isArray(raw1) ? raw1 : []
    const map = new Map<string, ChecklistItem>()
```
