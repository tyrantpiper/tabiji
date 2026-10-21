# 規格說明書：POI 景點抽屜「一體化毛玻璃純圖示藥丸島 (Segmented Icon Capsule)」重構

> **狀態**: APPROVED (經過 /grill-me 深入訪談收斂共識)  
> **建立日期**: 2026-10-21  
> **關聯組件**: `frontend/components/POIDetailDrawer.tsx`  
> **相關測試**: `frontend/__tests__/poi-detail-drawer-physics-sentinel.test.tsx`  

---

## 1. Problem Statement & Core Value (問題陳述與核心價值)

- **使用者痛點**:
  1. **文字截斷醜陋 (Text Truncation)**: 在小尺寸按鈕中硬塞長文字，導致「在 Google Maps 開啟」被截斷為「在 Googl...」、「尋找更多照片」被截斷為「尋找更多...」，極度粗糙且有未完工感。
  2. **方塊割裂與雜色 (Visual Clutter)**: 每個按鈕自帶獨立的灰框/綠框/紫框與硬邊界，在抽屜中間形成割裂的小方塊堆疊，缺乏現代頂級系統的整體感。
  3. **視口佔用與滾動阻力**: 垂直堆疊高度過大，在手機半屏（50vh）展開時造成底層資訊擁擠。
- **核心價值**:
  1. **徹底消除文字截斷**: 移除文字描述，改採「純圖示 (Icon-only)」一體化毛玻璃藥丸島。
  2. **視口容納度一字排開**: 4~6 顆按鈕完美均分適配所有手機螢幕寬度（320px~430px），免水平滾動，零文字腰斬。
  3. **具象圖示與微色彩識別**: 將跳轉地圖改為 `MapPin` (圖釘)，各圖示以精緻微色彩（靛青、寶藍、琥珀橙、石墨灰、翡翠綠、紫羅蘭）識別，搭配 `title` 與 `aria-label` 實現極致 a11y。

---

## 2. Visual Architecture & Design Tokens (視覺架構與設計標記)

### 2.1 容器結構 (Segmented Capsule Island)
```html
<div 
    className="w-full h-12 rounded-2xl bg-slate-100/70 dark:bg-slate-800/60 backdrop-blur-md border border-slate-200/50 dark:border-slate-700/50 shadow-xs flex items-center justify-around px-1.5"
    onPointerDown={(e) => e.stopPropagation()}
>
    <!-- Buttons -->
</div>
```

### 2.2 按鈕清單與微色彩矩陣
| 功能名稱 | 判定條件 | 圖示 | 顏色 Class | a11y 標籤 (title & aria-label) |
| :--- | :--- | :--- | :--- | :--- |
| **導航** | `onAddToItinerary && (...)` | `Navigation` | `text-indigo-500` | `t('tc_navigate')` |
| **Google Maps** | 總是存在 | `MapPin` | `text-blue-500` | `t('poi_open_gmaps')` |
| **實景照片** | 總是存在 | `ImageIcon` | `text-amber-500` | `t('poi_more_photos')` |
| **分享** | 總是存在 | `Share2` | `text-slate-500 dark:text-slate-400` | `t('share')` |
| **街景** | `isMapillaryAvailable() && onOpenStreetView` | `Camera` | `text-emerald-500` | `t('mapillary_streetview')` |
| **3D 飛越** | `onFlyover` | `Plane` | `text-purple-500` | `t('flyover_poi')` |

### 2.3 按鈕共用微交互類別
```css
flex items-center justify-center w-10 h-10 rounded-xl 
transition-all duration-150 
hover:bg-white/80 dark:hover:bg-slate-700/60 
active:scale-90 active:bg-white dark:active:bg-slate-700 
cursor-pointer
```

---

## 3. Edge Cases & Boundary Conditions (邊界條件與異常處理)

1. **手勢搶奪 (Gesture Conflicts)**:
   - 膠囊島綁定 `onPointerDown={(e) => e.stopPropagation()}`，防止使用者按壓按鈕時觸發外層 Vaul Drawer / Framer Motion 拖曳。
2. **無障礙無文字補償 (A11y Compensation)**:
   - 每個按鈕必須具備明確且具語意的 `aria-label` 與 `title`，螢幕閱讀器與瀏覽器 hover 自然提示。
3. **寬度自適應與極窄螢幕 (Responsive Invariants)**:
   - 使用 `justify-around`，即使在 iPhone SE (320px 寬度) 下，6 顆 40px 按鈕總寬度 240px，留白間距自然均分，不擠壓、不破版。
4. **主行動條不變量**:
   - 若未傳入 `onAddToItinerary`，主底層行動條會降級為「導航」全寬按鈕，此時藥丸島中不渲染「導航」圖示，避免畫面雙導航。

---

## 4. Acceptance Criteria (驗收標準清單)

- [ ] **AC-1**: 抽屜頂部快捷操作列改為單一毛玻璃藥丸島 (`rounded-2xl`)，不再有分散獨立的雜色卡片邊框。
- [ ] **AC-2**: 移除所有按鈕文字標籤，零文字截斷（無 `...` 縮略符號）。
- [ ] **AC-3**: 地圖外部開啟按鈕採用 `MapPin` 圖示，點擊後調用 `openExternalLink`。
- [ ] **AC-4**: 每個按鈕皆具備 `title` 與 `aria-label`。
- [ ] **AC-5**: 所有測試（81 檔、538 個測試）維持 100% 通過，TypeScript 與 ESLint 0 錯誤。
