# iOS Inset Grouped 表單架構與 Mobile Safari 視口調研報告 (2025–2026)

> **研究對象**: `ActivityEditModal.tsx` 行程活動編輯介面之 iOS Inset Grouped 原生化整合  
> **調研範圍**: Apple HIG (2025–2026)、Tailwind CSS v4、Mobile Safari PWA 視口/虛擬鍵盤避坑、Vaul / Emil Kowalski 開源實作驗證  
> **關聯筆記本**: `eedb7a4a-f44a-4d2f-9c1a-2df2816f8d7e` (Tabidachi iOS Timeline Cards & Inset Form Memo Architecture 2026)

---

## 一、核心技術流程 (Core Technical Execution Flow)

### 1.1 iOS Inset Grouped 視覺拓撲與層級規範
根據 Apple Human Interface Guidelines (Forms & Lists 最新規範) 以及 iOS 18/26 設計語言，模態表單 (Sheet Modal) 的視覺結構必須嚴格遵守雙層背景系統：
- **Level 0 (System Grouped Background)**:
  - 模態抽屜本體背景為次級中性底色：`bg-[#f2f2f7] dark:bg-black`（或 Tailwind 系統中 `bg-slate-100 dark:bg-slate-950`）。
  - 邊距：內層卡片距離抽屜邊緣標準 `px-4` (16pt)。
- **Level 1 (Secondary Grouped Background / Inset Grouped Cards)**:
  - 每個邏輯區塊（Section）由獨立圓角卡片包覆：`rounded-2xl bg-white dark:bg-[#1c1c1e] shadow-xs border border-black/5 dark:border-white/10`。
  - 卡片內部行 (Cell Rows) 使用 `divide-y divide-slate-100 dark:divide-slate-800/80`，行內高度維持 44pt–48pt 觸控黃金標準。
- **Section Headers & Footers**:
  - Section Header：`text-[13px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider px-3 pb-1.5`。
  - Section Footer：`text-[12px] text-slate-400 dark:text-slate-500 px-3 pt-1.5`（提供欄位補充說明，如「私密行程僅存於本機」）。

### 1.2 `ActivityEditModal` 五大分組整合架構 (Grouped Information Architecture)
將目前平鋪直敘、長度達 3000px 的雜亂欄位收納為 5 大精準 Section：

1. **Section 1: 基礎核心 (Primary Identity)**
   - 行程名稱 (`place` 輸入框) + 快速搜尋按鈕。
   - 活動分類：Segmented Control 膠囊滑軌（🎯 景點、🍽️ 美食、🏨 住宿、🚃 交通、🛍️ 購物、🎭 活動）。
   - 出發時間：原生 Time Pill 選擇器 (`type="time"`，內縮微型標籤)。
2. **Section 2: 地點與導航 (Location & Navigation)**
   - 國家與區域快速篩選（雙欄緊湊下拉選單）。
   - 高精地址解析引擎（Address Engine）：內嵌折疊式文字框與高精 GEOCODE 按鈕。
   - 導航網址（Navigation Link）解析行。
   - 座標與 POI 次級展開列（Disclosure Row：預設折疊，點擊展開 Coordinates & Nearby POI）。
3. **Section 3: 媒體與視覺 (Media & Visuals)**
   - 橫向滑軌多圖上傳 (`MultiImageUpload`)。
   - 預覽封面清除按鈕。
4. **Section 4: 備忘與商務 (Details & Accounting)**
   - 預約代號 (Reservation Code) 與 預估花費 (Cost) 雙欄並列。
   - 備忘筆記 (`desc` / Multiline Textarea)。
   - 標籤膠囊群 (`tags` Tag Pills + 內聯新增)。
5. **Section 5: 偏好設定 (Preferences & Controls)**
   - 私密行程切換 (Private Mode)：iOS 原生 `Switch` 開關。
   - 隱藏導航切換 (No Navigation)：iOS 原生 `Switch` 開關。

---

## 二、網路大神爭議點與避坑指南 (Web Expert Controversies & Pitfalls)

### 2.1 爭議點一：iOS PWA 虛擬鍵盤與 Viewport 頂推抖動 (Emil Kowalski vs. Apple WebKit)
- **現象**:
  - 當聚焦於 Sheet 內部的 `<input>` 或 `<textarea>` 時，iOS Safari 會彈出軟鍵盤。
  - WebKit 官方將鍵盤視為 Overlay 浮層，但在 standalone PWA 模式下，WebKit 經常觸發 `window.visualViewport.resize` 與 `scroll`。
- **大神解法爭議**:
  - *派別 A (JS 動態介入派)*: 監聽 `visualViewport.onresize`，動態計算 `keyboardHeight` 並修改 Sheet 的 `height` 或 `style.bottom`。
  - *派別 B (CSS 容器隔離派)*: 堅決不使用 JS 調整 Sheet 高度。將 Sheet 固定為 `h-[90vh] max-h-[90vh] flex flex-col`，頂部 Header 與底部 Footer 使用 `shrink-0`，中間滾動區設為 `flex-1 overflow-y-auto overscroll-contain`。
- **結論與避坑決策**:
  - 採納 **派別 B**。GitHub Issue 實測證實派別 A 會在鍵盤收起時觸發 Blur Race Condition（見下文 GitHub 驗證），導致面板高度無法復原。派別 B 利用原生 WebKit 滾動隔離，最為流暢穩定。

### 2.2 爭議點二：Radix UI Dialog / Sheet 在 iOS 上的背景滾動穿透 (Scroll Bleeding)
- **避坑機制**:
  - 必須在滾動容器上加入 `overscroll-contain` 與 `-webkit-overflow-scrolling: touch`。
  - Radix Sheet 預設會鎖定 body 滾動 (`pointer-events: none` 與 `overflow: hidden`)，但在 iOS Safari 上若內部有嵌套手勢，需確保內部容器 `touch-action: pan-y`，避免水平滑動時誤觸上一頁手勢。

### 2.3 爭議點三：Input 縮放 Bug (16px Rule)
- **踩坑紀錄**:
  - iOS Safari 在點擊 `font-size < 16px` 的 input 時會自動強制放大頁面（Page Zoom），造成 Sheet 破版且無法還原。
- **鐵律規避**:
  - 所有 Inset Grouped 內部的 `<input>` 與 `<textarea>`，在行動裝置上其字體大小必須至少為 `text-base` (16px) 或使用 CSS `text-[16px] sm:text-sm`，徹底消除 iOS 強制放大 bug。

---

## 三、GitHub 原始碼層級驗證 (GitHub MCP Code Verification)

### 3.1 `emilkowalski/vaul` Issue #650 深度驗證：鍵盤關閉與 Blur 時序競態
- **Issue 標題**: `Mobile keyboard dismiss: panel height not reset when blur fires before visualViewport resize`
- **原始碼缺陷還原**:
  ```ts
  // vaul 1.1.2 內部重置邏輯
  if (isInput(focusedElement) || keyboardIsOpen.current) {
      // 依據 visualViewport 重置
  }
  ```
  當使用者點擊抽屜外側收起鍵盤時：
  1. `blur` 事件最先觸發，`document.activeElement` 立即退回 `body`。
  2. `onPointerDownOutside` 觸發，強制將 `keyboardIsOpen.current = false`。
  3. `visualViewport.resize` 最後觸發，此時上述兩條件皆為 `false`，導致抽屜高度被永久鎖定在縮小的鍵盤高度！
- **對 Tabidachi 的架構啟示**:
  - 在 `ActivityEditModal.tsx` 中，嚴禁在視窗層級手動修改 Modal 的 `style.height`。維持彈性 Flexbox + `h-[90vh]`，完全免疫此 Bug。

### 3.2 `emilkowalski/vaul` Issue #641 驗證：背景滾動穿透 (Scroll Bleed on iOS)
- **Issue 標題**: `Background Scroll Bleed When Drawer Is Open on iOS`
- **驗證結論**:
  - 當抽屜內部滾動到底部或頂部時，iOS Safari 會鏈式傳遞（Scroll Chaining）至背景時間軸。
  - **解法**: 在 `ActivityEditModal` 的內部捲動容器 `div` 明確宣告 `overscroll-contain`，並確保 `DialogContent` 遮罩層具有 `fixed inset-0` 與完整事件阻斷。

### 3.3 Radix UI Switch Primitive 驗證
- **驗證項目**: `frontend/components/ui/switch.tsx` 已經完整封裝 `@radix-ui/react-switch`。
- **優勢**:
  - 具備完整的 ARIA 無障礙屬性 (`role="switch"`, `aria-checked`)。
  - 自帶平滑過渡動畫與 Haptic 相容性，可完全取代原生 HTML `<input type="checkbox">`。

---

## 四、實作轉換矩陣 (Migration Blueprint)

| 既有區塊 | 現況問題 | iOS Inset Grouped 重構方案 |
| :--- | :--- | :--- |
| **頂部導航** | 僅有置中標題與關閉叉號，底部又重複放置「取消/儲存」按鈕 | 遵循 iOS Sheet 模式：頂部左側「取消」、中央標題、右側藍字加粗「儲存/完成」；底部可選擇移除或保留固定動作列 |
| **分類選擇** | 6 個大按鈕直接平鋪，佔據過多垂直空間 | 轉為 iOS Inset Row 內部的 **橫向滑動 Segmented Control** 或精緻網格膠囊 |
| **設定開關** | 兩個獨立的方形卡片 + 粗糙原生 Checkbox | 整合為單一 **Settings Group 卡片**，內部為兩行 Cell，右側配備 **iOS Switch** |
| **地址解析 & POI** | 綠色大卡片與虛線 POI 搜尋上下堆疊，層級破碎 | 收折入 **Location Group 卡片**：第一行為地點名稱與搜尋，第二行為地址解析，折疊列為 POI 與手動經緯度 |
| **輸入框體驗** | 部分輸入框為 `text-xs` (12px)，造成 iOS Safari 自動縮放破版 | 全面規格化為 `text-[16px] sm:text-sm`，徹底消除鍵盤縮放 bug |
