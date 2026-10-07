# 📅 Daily Report - 2026-10-07

> **系統狀態**：🟢 Production Hardened, Full-Width Top-Pill Timeline Deployed, Swipe Misfire Eliminated, iOS Inset Grouped Forms Active, Transit Connectors & 5s Undo Deletion Integrated, Idle Breathing (2.5s) Operational, Security Sentinel Physical Sandbox Hardened (27/27 SECURE), 0 TypeScript Errors, 0 ESLint Warnings, 100% Tests Green (Backend 112/112, Frontend 316/316, Total 428/428 Tests Passing), GitHub main branch synced.  
> **今日關鍵提交串列 (Full Day Commit Stream)**：
> - [`f73b9db`](https://github.com/tyrantpiper/travel-pwa/commit/f73b9db) `feat(itinerary): modernize timeline cards, sticky blur days, idle breathing, transit connectors and undo deletion`
> - [`a3a3f7a`](https://github.com/tyrantpiper/travel-pwa/commit/a3a3f7a) `feat(itinerary): upgrade timeline card to full-width top-pill layout and remove swipe misfire`

---

## 🏆 深度專案復盤：四大核心工程里程碑

本日 Tabidachi 在行程時間軸卡片版面架構、垂直滾動手勢純淨化、iOS 轉乘動態銜接、5 秒延遲安全撤銷刪除，以及物理隔離資安對抗上實現了重大突破：

### 里程碑一：行程卡牌 100% 滿版擴展 ✕ 頂部時序膠囊 (Top-Pill) ✕ Bento 看板像素級對齊
1. **問題背景與痛點根因**：
   - 舊版卡片採用左側獨立時間欄位（`w-14`，56px）+ 間距（`gap-4`，16px），實體佔據了 72px 水平空間。
   - 外容器留白 `px-5`（40px 邊距）與上方儀表板及天氣看板（`px-4`，32px）不一致，產生凹陷狹窄感。
   - 右側縮圖硬編碼 `mr-8`（32px）避開浮動三點按鈕，進一步壓縮中央標題與描述，在 375px 小螢幕（iPhone SE）上文字可視寬度僅剩約 126px，嚴重影響閱讀。
2. **頂部時序膠囊與滿版整合架構**：
   - **時序膠囊收攏（Top-Pill Header）**：
     - 將拖曳抓取手把（`⠿`）、高對比圓形序號徽章（`①`）、等寬字體時間（`09:00`）與分類標籤全面收編至卡片內部頂部膠囊列。
     - 三點選單按鈕（`...`）獨立錨定於頂部標頭右側，縮圖移除 `mr-8`，解鎖 +60px 以上的可視橫向空間。
   - **容器邊距等寬對齊**：
     - 外容器從 `px-5` 收斂為 `px-4 sm:px-6`，行程卡片本體設定為 `w-full`，與上方 iOS 天氣 Bento 看板及 4 合 1 概覽看板達到像素級邊緣對齊。
   - **DragOverlay 鏡像同步**：
     - `TimelineCardOverlay.tsx` 100% 鏡像對齊頂部膠囊滿版架構，拖曳移動時尺寸完全咬合，徹底消除跨組件視覺跳動與撕裂。

---

### 里程碑二：徹底拔除橫滑刪除誤觸 ✕ 5 秒安全延遲撤銷管理器 (UndoDeleteManager)
1. **痛點剖析**：
   - 行程時間軸屬於高頻率垂直滾動頁面。舊版在 `SortableTimelineCard` 中為每張卡片綁定了 `framer-motion` 的 `drag="x"`。
   - 當使用者手指在上下滑動時只要帶有微小的水平位移偏差（`offset.x < -35`），就會觸發彈簧位移並露出紅色刪除垃圾桶抽屜，頻繁造成誤觸與操作驚嚇。
2. **手術級精確重構**：
   - **移除脆弱的 `drag="x"` 手勢層**：
     - 徹底移除 `drag="x"`、`swipeOffset`、`handleDragEnd` 與底層紅色垃圾桶抽屜。卡片回歸純淨的垂直滾動與拖曳排序手勢。
     - 刪除操作完全收斂至卡片右上角標準三點選單（`...`）中。
   - **UndoDeleteManager 安全撤銷機制**：
     - 導入 5 秒延遲刪除佇列與平滑折疊動畫，點擊刪除後即刻跳出「已刪除活動 · 復原」Toast。
     - **Lifecycle FlushAll 守護**：在組件卸載、分頁切換、行程切換或主動儲存時，無條件調用 `flushAll()` 立即執行持久化突變，杜絕非同步切換期間定時器被垃圾回收導致的資料丟失。

---

### 里程碑三：TransitSegmentConnector 轉乘動態耗時 ✕ 智慧距離計算 ✕ 手動覆寫
1. **問題背景**：
   - 卡片與卡片之間缺乏視覺流動感，景點間的移動方式（步行、大眾運輸、開車）與交通耗時處於黑盒子狀態。
2. **架構落實**：
   - 實作 `TransitSegmentConnector.tsx` 與純計算模組 `transit-connector.ts`：
     - 依據前後景點座標自動計算 Haversine 距離，智慧映射最佳交通方式與預估耗時。
     - 支援使用者手動自訂與覆寫交通模式（🚶 步行、🚇 大眾運輸、🚗 開車、🚕 計程車）與時間。
     - 在連續景點卡片中央垂直貫穿連線，呈現原生 iOS 地圖風格的時序流動感。

---

### 里程碑四：Security Sentinel 實體隔離對抗審核 ✕ 27/27 SECURE 全通關
1. **物理隔離子代理人對抗證偽**：
   - 透過 `runner.py` 調度 `agy.exe -p --sandbox` 對本次重構涉及的全部核心模組進行惡意對抗審查：
     - `SortableTimelineCard.tsx`：驗證橫滑移除後，`@dnd-kit` 手把與生命週期是否有遺留懸空監聽器 ➔ **DISMISSED (安全)**。
     - `timeline-card.tsx`：驗證拖曳手把是否會冒泡觸發卡片根層點擊，造成地圖錯誤聚焦飛航 ➔ **DISMISSED (安全，具備 `data-drag-handle` 防禦)**。
     - `timeline-card.tsx`：驗證 375px 小螢幕下頂部標籤是否會水平溢位推擠按鈕 ➔ **DISMISSED (安全，Tags 已分流至標題下方)**。
     - `ItineraryTimeline.tsx`：驗證容器邊距調整是否會造成 Virtuoso 虛擬高度快取失步 ➔ **DISMISSED (安全)**。
     - `TimelineCardOverlay.tsx`：驗證拖曳浮層是否與本體版型脫節 ➔ **DISMISSED (安全，鏡像同步)**。
2. **安全帳本全綠通關**：
   - 更新 `docs/security/security-coverage-ledger.json`，審核目標擴充至 27 項全部 `SECURE`。

---

## 🏛️ 架構決策 (Architecture Decisions)

- **[AD-055] 垂直手勢優先於次級橫滑原則 (Vertical Gestures First over Secondary Swipe Gestures)**:
  - 在主要操作為高頻垂直滾動的長時間軸頁面，嚴禁為單一卡片配置無閾值門檻的橫向滑動手勢（如 `drag="x"`）；次級破壞性動作（刪除）必須收攏於標準選單並由樂觀延遲撤銷（Undo Toast）提供安全兜底。
- **[AD-056] 頂部時序膠囊收攏與單列滿版架構 (Top-Pill Consolidation & Full-Width Grid Invariance)**:
  - 卡片時間與序號由獨立左欄（佔用 72px）移入卡片內部頂部膠囊列，外層容器與上方看板統一錨定為 `px-4 sm:px-6`，解鎖 +60px 文字水平空間並達成像素級對齊。
- **[AD-057] 樂觀撤銷生命週期強制結算防線 (Optimistic Undo Lifecycle Flush Invariance)**:
  - 延遲撤銷刪除（5 秒 Pending 佇列）在組件卸載、分頁切換、行程切換或儲存時，必須無條件同步調用 `flushAll()` 立即執行持久化突變，杜絕延遲計時器在非同步切換中被垃圾回收造成刪除狀態丟失或資料幽靈復原。
- **[AD-058] 拖曳手把 DOM 事件冒泡防禦標準 (Drag Handle DOM Event Isolation Guard)**:
  - 卡片容器具備地圖跳轉點擊事件時，拖曳抓取手把必須宣告顯式 `button[type="button"]` 與 `data-drag-handle="true"`，並在卡片根層點擊攔截器中防禦性排除，徹底阻斷拖曳引發的地圖飛航誤觸。

---

## 🟢 Features & Fixes 今日交付價值

1. **行程卡片滿版與時序膠囊 (`timeline-card.tsx`, `SortableTimelineCard.tsx`, `TimelineCardOverlay.tsx`)**：
   - 卡片升級為 100% 滿版寬度，邊距與上方看板統一為 `px-4 sm:px-6`。
   - 頂部收攏整合時序膠囊（抓取手把、序號、時間、分類）。
   - 移除 `framer-motion drag="x"` 滑動誤觸，刪除操作安全收斂至三點選單。
2. **轉乘銜接動態線條 (`TransitSegmentConnector.tsx`, `transit-connector.ts`)**：
   - 自動距離計算與交通模式預估，支援手動覆寫耗時與模式。
3. **5 秒延遲安全撤銷刪除 (`undo-delete-manager.ts`)**：
   - 具備 5 秒延遲 Toast、樂觀折疊動畫與 `flushAll` 生命週期防線。
4. **天數導航吸頂與 2.5s 靜止呼吸微降敏 (`useIdleBreathing.ts`, `FloatingMapCapsule.tsx`)**：
   - 滾動靜止 2.5 秒自動 20% 微幅透明，觸控或滾動 150ms 瞬態喚醒。
5. **iOS Inset Grouped 活動編輯表單 (`ActivityEditModal.tsx`)**：
   - HIG 分組卡片風格、景點 POI 搜尋整合與深色模式支援。
6. **資安防護與全套測試通過**：
   - Security Sentinel 實體沙盒對抗證偽通關（27 項全部 SECURE）。
   - 全套測試（前端 316 個、後端 112 個，共 428 個）100% 綠燈通關，成功推送到 GitHub `main` 分支。

---

## 🔴 Technical Debt 今日登記技術債

- **[TD-027] Windows CreateProcess 命令列長度限制 (WinError 206) 防禦標準化**：
  - `runner.py` 在調度背景 `agy.exe -p` 子代理人時，若檔案全文超過 32KB（如超過 800 行之複合組件），Windows 命令列會拋出 `[WinError 206] 檔名或副檔名太長`。
  - 目前採 `start_line` / `end_line` 局部切片傳入，未來需在 `runner.py` 全域改以暫存檔案或 stdin pipe 標準化傳入，消除任何單行命令列長度溢位風險。

---

## 🛡️ Failed Paths 今日避坑指南

1. **長時間軸卡片橫滑手勢衝突陷阱**：
   - 在行動裝置快速垂直滾動時，手指自然運動軌跡具備微幅弧形水平位移（-35px），導致 `dragElastic` 頻繁被激發並彈出紅色刪除垃圾桶，嚴重破壞流暢瀏覽體驗。
   - **教訓**：高頻垂直滾動視圖中，避免在整張卡片上疊加無阻尼門檻的橫向拖曳手勢；破壞性操作回歸選單與撤銷防線。
2. **頂部標頭多標籤過度擠壓陷阱**：
   - 初版嘗試將時間、序號、分類徽章、私有標記與自訂 Tags 全部置於頂部單一行，在 iPhone SE（375px）寬度下會造成右上角三點選單被擠出螢幕或強制折行。
   - **教訓**：自訂 Tags 必須分流至標題下方，頂部僅保留時序膠囊與動作按鈕，維持版面堅固性。
3. **拖曳手把與地圖點擊聚焦事件競態**：
   - 卡片根容器綁定 `onClick` 聚焦地圖時，若拖曳手把未在事件攔截器中被顯式排除，長按手把或放開時會冒泡觸發 `flyTo`，干擾排序體驗。
   - **教訓**：手把需加上 `data-drag-handle` 屬性，並於父層 `handleCardClick` 前置攔截過濾。

---

## 🚀 Next Steps 下一步計畫

1. **實機多尺寸體驗驗收**：
   - 在真實行動裝置（iOS Safari、Android Chrome）上體驗頂部膠囊滿版卡片與轉乘線的跟手度與流暢度。
2. **國際化 (i18n) 補齊盤點**：
   - 檢查轉乘銜接線與表單新欄位在日文 (ja) 與英文 (en) 下的字串完整度。
3. **Security Sentinel runner.py pipe 化升級**：
   - 將 `runner.py` 改寫為 stdin pipe 傳遞，徹底防禦 Windows WinError 206 邊界限制。
