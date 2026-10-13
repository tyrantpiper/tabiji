# 📋 規格說明書：行程資訊看板「行前清單」與「預估花費」卡片位置調換 (Spec)

> **文件狀態**: `DRAFT / APPROVED BY INTERVIEW`  
> **建立時間**: 2026-10-14  
> **關聯組件**: `ItineraryDashboardHub.tsx`, `IOSBottomSheet.tsx`  
> **設計規範**: iOS Bento Grid, iOS Segmented Control Tabs, Tailwind CSS v4  

---

### 1. Problem Statement & Core Value (問題陳述與核心價值)

#### 1.1 使用者痛點 (User Problem)
- 原先的行程資訊看板 2x2 Bento Grid 中，右欄上方為「預估花費」、下方為「行前清單」。
- 使用者在行程準備與每日出行時，對於「行前清單 (Checklist)」的檢視與操作頻率高於「預估花費 (Cost Summary)」。將行前清單置於下方，操作動線較低且在單手拇指熱區與視線掃描時權重不足。
- 使用者希望將右欄上下的「行前清單」與「預估花費」位置互換，讓每日行動資訊（重點提醒 ✕ 行前清單）集中在第 1 列（Row 1），財務與票據資訊（交通票券 ✕ 預估花費）集中在第 2 列（Row 2）。

#### 1.2 成功指標 (Success Metrics)
- **視覺一致性**: 2x2 Grid 右側上下卡片精準互換，卡片等高（`min-h-20.5`），進度條與金額顯示無破版。
- **心智模型同步**: `IOSBottomSheet` 分頁標籤列順序同步為 `[AI 審核] [重點提醒] [行前清單] [交通票券] [預估花費]`，點擊儀表板卡片直接啟動對應分頁且順序直覺。
- **測試覆蓋與零降級**: 靜態檢查（`tsc` 0 錯誤、`eslint` 0 錯誤），現有與新增的單元測試 100% 綠燈。

---

### 2. User Journey & Visual Layout (使用者旅程與操作佈局)

#### 2.1 2x2 Bento Grid Before / After 佈局矩陣

```
【修改前 (Before)】
┌───────────────────────────┬───────────────────────────┐
│ [Row 1, Col 1] 💡 每日重點提醒 │ [Row 1, Col 2] 💰 預估花費  │
├───────────────────────────┼───────────────────────────┤
│ [Row 2, Col 1] 🎫 交通票券   │ [Row 2, Col 2] ✅ 行前清單  │
└───────────────────────────┴───────────────────────────┘

【修改後 (After)】
┌───────────────────────────┬───────────────────────────┐
│ [Row 1, Col 1] 💡 每日重點提醒 │ [Row 1, Col 2] ✅ 行前清單  │
├───────────────────────────┼───────────────────────────┤
│ [Row 2, Col 1] 🎫 交通票券   │ [Row 2, Col 2] 💰 預估花費  │
└───────────────────────────┴───────────────────────────┘
```

#### 2.2 IOSBottomSheet 分頁順序變更
- **Before**: `["ai_review", "tips", "costs", "tickets", "checklist"]`
- **After**: `["ai_review", "tips", "checklist", "tickets", "costs"]`

---

### 3. Architecture & Code Changes (架構與變更細節)

#### 3.1 `frontend/components/itinerary/ItineraryDashboardHub.tsx`
- 將原本的「卡片 2: 💰 預估花費」代碼區塊與「卡片 4: ✅ 行前清單」代碼區塊對調順序。
- 保持各卡片既有的 `whileTap`、`cn(...)` 視覺樣式、圖標與色彩體系（行前清單使用 Indigo，預估花費使用 Emerald）。
- 保持卡片點擊事件 `handleCardClick("checklist")` 與 `handleCardClick("costs")` 邏輯不變。

#### 3.2 `frontend/components/itinerary/IOSBottomSheet.tsx`
- 調整 `tabs` 常數陣列宣告順序：
  ```typescript
  const tabs: Array<{ id: DashboardSectionTab; label: string; icon: React.ComponentType<{ className?: string }> }> = [
    { id: "ai_review", label: zh ? "AI 審核" : "AI Review", icon: Sparkles },
    { id: "tips", label: zh ? "重點提醒" : "Tips", icon: AlertCircle },
    { id: "checklist", label: zh ? "行前清單" : "Checklist", icon: CheckSquare },
    { id: "tickets", label: zh ? "交通票券" : "Tickets", icon: Ticket },
    { id: "costs", label: zh ? "預估花費" : "Costs", icon: Wallet },
  ]
  ```

#### 3.3 測試更新 `frontend/__tests__/itinerary-dashboard-layout.test.tsx`
- 更新測試對 `tabs` 排列順序或渲染驗證的斷言，確保 DOM 節點順序與標籤順序完全一致。

---

### 4. Edge Cases & Boundary Conditions (邊界條件與異常處理)

| 邊界狀況 | 預期行為 | 防禦機制 |
| :--- | :--- | :--- |
| **清單項目全完成 (100%)** | 右上角徽章顯示綠色「完成」，微型進度條為 100% | 既有 `checklistProgress.completed === total` 條件渲染保持不變 |
| **清單無項目 (0/0)** | 徽章顯示 `0/0`，進度條 0%，不報錯 | 保持 `checklistPercentage` 零除防禦 (`total > 0 ? ... : 0`) |
| **多幣別預估花費** | 右下角預估花費徽章顯示「多幣別」標籤，金額不破行 | 既有 `truncate` 與 `tabular-nums` 樣式保護 |
| **iOS / PWA 觸控切換** | 點擊任一卡片開啟 Sheet，滑動切換至正確 Tab | Sheet 傳入 `activeTab` 保持受控屬性 |

---

### 5. Acceptance Criteria (驗收標準清單)

- [ ] **AC-1**: 儀表板第 1 列右側 (右上) 為「行前清單」，顯示圖標、進度標籤、進度條。
- [ ] **AC-2**: 儀表板第 2 列右側 (右下) 為「預估花費」，顯示圖標、金額與幣別。
- [ ] **AC-3**: 點擊「行前清單」開啟 `IOSBottomSheet`，預設選中並聚焦於 `checklist` Tab。
- [ ] **AC-4**: 點擊「預估花費」開啟 `IOSBottomSheet`，預設選中並聚焦於 `costs` Tab。
- [ ] **AC-5**: `IOSBottomSheet` 分頁控制列自左至右順序為：AI 審核 -> 重點提醒 -> 行前清單 -> 交通票券 -> 預估花費。
- [ ] **AC-6**: 執行 `npx tsc --noEmit` 0 型別錯誤；`npm run lint` 0 警告與錯誤；Vitest 測試套件全數通過。
