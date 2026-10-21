# 規格說明書：POI 景點抽屜「2×3 對稱微膠囊雙排矩陣 (Two-Row Grid Matrix)」重構

> **狀態**: APPROVED (使用者共同設計收斂)  
> **建立日期**: 2026-10-21  
> **目標檔案**: `frontend/components/POIDetailDrawer.tsx`  
> **測試檔案**: `frontend/__tests__/poi-detail-drawer-physics-sentinel.test.tsx`  

---

## 1. Problem Statement & User Request (問題陳述與需求背景)

- **使用者回饋**: 
  1. 單排 6 顆純圖示在手機橫向長條中顯得圖示偏小（16px）、單薄且略顯空洞。
  2. 使用者直覺提議：「如果把它變上下兩排呢，這樣也可以圖示大一點」。
  3. 「我們點進去就會自己顯示此地沒有啦，所以不用特別拿掉」——確立維持固定 2 排 × 3 列（共 6 顆完整卡片），版面幾何絕對對稱與穩定。
- **核心價值**:
  1. **圖示尺寸大升級**: 圖示從 `w-4 h-4` (16px) 升級為 `w-5 h-5` (20px)，視覺張力與識別度顯著提升。
  2. **圖示 + 雙字清晰標籤**: 每排 3 顆寬裕空間，讓圖示右側能放置精簡雙字標籤（「導航」、「街景」、「飛越」 / 「照片」、「地圖」、「分享」），徹底告別生硬截斷。
  3. **統一高級毛玻璃中性底**: 所有卡片採用統一的高級柔和灰白底色，圖示維持專屬微色彩點綴，既冷靜一致又具備清晰視覺層級。

---

## 2. 佈局架構與排布順序 (2×3 Matrix Topology)

### 2.1 排布矩陣
```
┌──────────────┬──────────────┬──────────────┐
│  🧭 導航     │  📷 街景     │  ✈️ 飛越     │  <-- Row 1: 空間沉浸與抵達
├──────────────┼──────────────┼──────────────┤
│  🖼️ 照片     │  📍 地圖     │  🔗 分享     │  <-- Row 2: 情報檢索與外部
└──────────────┴──────────────┴──────────────┘
```

### 2.2 容器與卡片 Token 矩陣
- **外層容器**:
  ```tsx
  <div 
      className="grid grid-cols-3 gap-2 w-full touch-manipulation"
      onPointerDown={(e) => e.stopPropagation()}
  >
  ```
- **單一卡片樣式**:
  ```tsx
  className="flex items-center justify-center gap-1.5 py-2 px-2.5 h-11 rounded-xl bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100 dark:hover:bg-slate-700/60 border border-slate-200/50 dark:border-slate-700/50 transition-all active:scale-95 cursor-pointer"
  ```
- **各項規格一覽**:
  | 順序 | 標籤 (Label) | 圖示 (Icon) | 圖示色彩 | 交互行為 | a11y 標籤 (title & aria-label) |
  | :--- | :--- | :--- | :--- | :--- | :--- |
  | 1 | `導航` | `Navigation` (w-5 h-5) | `text-indigo-500` | `handleNavigate()` | `t('tc_navigate')` |
  | 2 | `街景` | `Camera` (w-5 h-5) | `text-emerald-500` | `onOpenStreetView?.(poi.lat, poi.lng)` | `t('mapillary_streetview')` |
  | 3 | `飛越` | `Plane` (w-5 h-5) | `text-purple-500` | `onFlyover?.(poi.lat, poi.lng)` | `t('flyover_poi')` |
  | 4 | `照片` | `ImageIcon` (w-5 h-5) | `text-amber-500` | `handleViewPhotos()` | `t('poi_more_photos')` |
  | 5 | `地圖` | `MapPin` (w-5 h-5) | `text-blue-500` | `openExternalLink(...)` | `t('poi_open_gmaps')` |
  | 6 | `分享` | `Share2` (w-5 h-5) | `text-slate-500 dark:text-slate-400` | `handleShare()` | `t('share')` |

---

## 3. i18n 多語系精簡標籤策略

在 `frontend/lib/i18n/remaining.ts` 中新增短標籤對照：
- `poi_dock_nav`: `zh-TW`: "導航", `en`: "Nav"
- `poi_dock_street`: `zh-TW`: "街景", `en`: "Street"
- `poi_dock_fly`: `zh-TW`: "飛越", `en`: "Flyover"
- `poi_dock_photo`: `zh-TW`: "照片", `en`: "Photos"
- `poi_dock_map`: `zh-TW`: "地圖", `en`: "Map"
- `poi_dock_share`: `zh-TW`: "分享", `en`: "Share"

---

## 4. 驗收標準 (Acceptance Criteria)

- [ ] **AC-1**: 抽屜快捷列轉為 2 排 × 3 列網格佈局，固定常駐 6 大功能卡片，版面幾何完全對稱。
- [ ] **AC-2**: 圖示尺寸放大為 20px (`w-5 h-5`)，視覺焦點清晰。
- [ ] **AC-3**: 採用雙字短標籤，在任何手機螢幕下字串零截斷（無 `...` 縮略符）。
- [ ] **AC-4**: 統一柔和中性底色，圖示維持專屬微色彩點綴。
- [ ] **AC-5**: 保留 `touch-manipulation` 與 `onPointerDown stopPropagation`，切斷手勢競爭。
- [ ] **AC-6**: 全棧測試（前端 81 檔 538 測試、後端 pytest 198 測試）100% 通過。
