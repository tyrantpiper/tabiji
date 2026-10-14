# Feature Specification: 旅伴時光膠囊輸入彈窗體驗精進 (Polaroid Capsule Modal Refinement)

> **建立日期**: 2026-10-14  
> **關聯版本**: Tabidachi v2.5 / PWA  
> **驅動指令**: `/Idea to Spec` `/grill-me`

---

## 1. Problem Statement & Core Value (問題陳述與核心價值)

在使用者真機體驗「旅伴時光膠囊（Trip Time Capsule）」拍立得輸入彈窗時，發現四項關鍵體驗與視覺痛點：
1. **雙重打叉 (Duplicate Close Buttons)**：彈窗右上角同時出現外層 Radix UI 預設關閉鈕與自訂深藍 Header 關閉鈕，視覺重疊突兀。
2. **拍立得相框視覺佔比過高**：原 280px (`max-w-70`) 尺寸佔滿直式手機畫面，造成下方心情與真心話輸入框被大幅擠壓。
3. **底部操作列滾動截斷 (Bottom Bar Truncation)**：內外雙層滾動條高度競爭，造成「取消」與「封存進時光膠囊」按鈕被推擠至視窗下緣外，使用者需手動費力滑動甚至難以點擊。
4. **心情維度不足 (Limited Mood Expression)**：原僅 6 種 Emoji，無法涵蓋旅人多元豐富的心境（如爆笑、崩潰、狂拍、爆買等），缺乏個性化表達能力。

---

## 2. Architecture & UI Refinements (架構與使用者體驗重構)

### 2.1 雙重關閉按鈕隔離機制 (Single Close Button Isolation)
- **架構改動**: 在 `DialogContent` 顯式聲明 `showCloseButton={false}`。
- **效果**: 阻斷 Radix UI `DialogPrimitive.Close` 在 `top-4 right-4` 的預設注入，僅保留深色 Header 內唯一的整合式關閉按鈕，消除重疊。

### 2.2 拍立得尺寸重定標與上傳管線 (Polaroid Sizing & Pipeline)
- **視覺尺寸**: 由 `max-w-70` (280px) 收斂至 `max-w-56` (224px)，搭配 `p-2.5 pb-4`。垂直高度節省約 60px，顯著釋放首屏可視空間。
- **檔案傳輸標準**: 維持 `max 8MB`。維持前端 Canvas 自動等比縮放至 2048px/85% JPEG 壓縮機制，實際網路傳輸約 600KB~1.2MB，由 Cloudinary 直傳簽名路由快速上傳。

### 2.3 視窗高度收斂與常駐吸底操作列 (Sticky Bottom Bar)
- **容器重構**:
  - `DialogContent`: `flex flex-col max-h-[88vh] sm:max-h-[85vh] overflow-hidden`
  - 頂部 Header: `shrink-0`
  - 中間內容區: `flex-1 overflow-y-auto overscroll-contain p-4 sm:p-5 space-y-4`
  - 底部操作工具列: `shrink-0 sticky bottom-0 bg-slate-950/95 backdrop-blur border-t border-slate-800/80 p-3.5 sm:p-4 z-10`
- **效果**: 操作工具列永遠牢靠釘在螢幕底部可見，中間內容自由滾動，杜絕截斷。

### 2.4 心情表達擴充系統 (12 種情境 + 自選 Emoji)
- **12 款精選雙排網格 (6x2)**:
  1. `🥳 嗨翻` (Excited)
  2. `🤩 驚艷` (Amazed)
  3. `🍜 吃貨` (Foodie)
  4. `😴 累趴` (Exhausted)
  5. `🤯 震撼` (Mindblown)
  6. `✨ 溫馨` (Cherished)
  7. `🤣 爆笑` (Hilarious)
  8. `😭 崩潰` (Meltdown)
  9. `☕ 愜意` (Chill)
  10. `💸 爆買` (Broke)
  11. `📸 狂拍` (Photogenic)
  12. `🍺 微醺` (Tipsy)
- **自選表情引擎**:
  - 提供「➕ 自選 Emoji」展開式輸入條，支援輸入法貼上任何客製化 Emoji（如 ⛩️, 🍣, 💖），即時同步至拍立得卡片手寫標籤。

---

## 3. Acceptance Criteria (驗收標準清單)

- [x] **AC-1 (單一關閉鈕)**: 打開時光膠囊輸入彈窗，右上角僅呈現 1 個 X 關閉按鈕，無雙重重疊。
- [x] **AC-2 (尺寸緊湊度)**: 拍立得照片外框寬度為 224px，文字框與按鈕在常見手機視窗（390px 寬、667px+ 高）皆能自然呈現。
- [x] **AC-3 (操作列常駐吸底)**: 下滑內容至最底端時，「取消」與「封存進時光膠囊」按鈕保持在彈窗最下方，完全無被截斷或溢出視窗。
- [x] **AC-4 (心情多樣性)**: 呈現 12 款精選 Emoji 雙排網格；點擊「➕ 自選 Emoji」可成功輸入並套用任意表情至拍立得底片標籤。
- [x] **AC-5 (靜態與測試守門)**: `tsc --noEmit`、`eslint` 與 `vitest` 全量 100% 綠燈通過。
