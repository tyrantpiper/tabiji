# 實施計畫：全域通知連動重新整理與標頭極致瘦身 (Notification-Bound Refresh & Decluttering)

> **計畫日期**: 2026-10-21  
> **關聯規格**: [notification-bound-refresh-spec.md](file:///d:/Project/tabiji/travel-pwa/docs/specs/features/notification-bound-refresh-spec.md)  
> **決策紀錄**: 經 `/Idea to Spec` 與 `/grill-me` 訪談確定，採全站資料統一步調，將重新整理連動至右上角通知鈴鐺，並徹底自所有頁面移除 `ZenRenew` 按鈕。

---

## 提案使用者審核 (Proposed Changes for User Approval)

### 1. `frontend/components/notifications/notification-bell.tsx`
- **新增鈴鐺微動搖擺動畫 (`isRinging`)**:
  使用 Framer Motion 對 Bell 圖示綁定 `animate={{ rotate: isRinging ? [0, -14, 14, -10, 10, -5, 5, 0] : 0 }}`，動畫時長 0.55 秒。
- **點擊連動觸發與防抖節流**:
  點擊展開鈴鐺時：
  1. 觸發震動反饋 `haptic.selection()`。
  2. 啟動 `isRinging` 微動動畫。
  3. 執行 `fetchNotifications()` 讀取最新通知。
  4. 經 2000ms 節流判斷後，廣播 `tabidachi-trigger-refresh` 全域自訂事件。

### 2. 全域接收端連動 (`itinerary-view.tsx`, `tools-view.tsx`, `info-view.tsx`)
- **`itinerary-view.tsx`**:
  - 掛載 `window.addEventListener('tabidachi-trigger-refresh', ...)`。
  - 當處於行程頁面 (`activeTripId` 存在) 時，執行 `Promise.allSettled([reloadTripDetail(), reloadCapsules()])`。
  - 當處於旅程列表時，執行 `reloadTrips()`。
- **`tools-view.tsx`**:
  - 掛載 `window.addEventListener('tabidachi-trigger-refresh', ...)`，更新即時匯率、費用清單與行程資料。
- **`info-view.tsx`**:
  - 掛載 `window.addEventListener('tabidachi-trigger-refresh', ...)`，呼叫 `handleRefresh()` 重新取得機票、住宿憑證與行李清單。

### 3. 標頭極致瘦身 (移除 `ZenRenew`)
- **`frontend/components/itinerary/ItineraryHeader.tsx`**:
  - 移除 `<ZenRenew ... />` 與相關未使用的 import，釋放 44px 寬度，徹底根除行動端標頭 5 顆按鈕擁擠問題。
- **`frontend/components/itinerary/TabijiHomeDashboard.tsx`**:
  - 移除 `<ZenRenew ... />` 與相關未使用的 import，僅保留景點口袋清單書籤按鈕。
- **`frontend/components/views/tools-view.tsx`**:
  - 移除標頭區域的 `<ZenRenew ... />`。
- **`frontend/components/views/info-view.tsx`**:
  - 移除標頭區域的 `<ZenRenew ... />`。

### 4. 自動化對抗測試 (`frontend/__tests__/notification-bound-refresh-sentinel.test.tsx`)
- 驗證點擊 `NotificationBell` 發送 `tabidachi-trigger-refresh`。
- 驗證 2 秒內連續點擊之防抖節流機制。
- 驗證 `ItineraryHeader`、`TabijiHomeDashboard`、`ToolsView`、`InfoView` 均不再出現 `ZenRenew`。

---

## 驗證流程 (Verification Plan)

### 靜態品質守門 (Static Quality Gates)
1. `npx tsc --noEmit`: 確保 0 型別錯誤。
2. `npm test`: 確保既有 78 份測試套件全數通過，無任何降級。

### 人工與實機驗收點
1. 進入首頁與行程頁面，標頭整齊清爽，無擁擠排版。
2. 點擊右上角鈴鐺，鈴鐺優雅搖擺，通知面板展開，背後行程、工具箱、資訊資料無感靜默重新同步。
