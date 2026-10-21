# 規格說明書：景點口袋庫 (PoiPoolView) 導航列緊湊化與副標題解構

> **規範等級**：Feature UI Refinement Specification  
> **建立日期**：2026-10-21  
> **關聯檔案**：`frontend/components/poi/PoiPoolView.tsx`、`frontend/lib/i18n/poi.ts`

---

## 1. Problem Statement & Core Value (問題陳述與核心價值)

### 1.1 使用者痛點 (User Problem)
景點口袋庫 (`PoiPoolView`) 頂部導航列包含了一行說明文字 `poi_drawer_desc`（「儲存喜愛的地點，隨時排入行程或一鍵開啟導航」）。在行動裝置視窗中：
1. 該副標題文字佔據垂直空間，增加視覺雜訊；
2. 在口袋庫作為沉浸式視圖（Immersive View）展開時，使用者已經明確理解該視圖功能，冗長說明缺乏操作價值；
3. 與右側的雙統計徽章（總計、已釘選）在垂直對齊時產生基準線偏移，造成頂部區塊層次不夠簡練。

### 1.2 核心價值與指標 (Success Metric)
- **極致精煉 (Zen Ergonomics)**：移除副標題文字節點，將返回按鈕、標題（含書籤 Icon）與右側統計徽章整合成單一水平軸心（`items-center`）。
- **視域最大化**：節省垂直空間，為下方的智慧搜尋列（Omnibar）與景點卡片清單騰出更多顯示面積。
- **指標**：TypeScript 0 錯誤、ESLint 0 錯誤、前端 531 測試 100% 通過。

---

## 2. User Journey & UI Layout (使用者旅程與介面佈局)

### 2.1 介面變更前後對比
```text
[Before]
┌────────────────────────────────────────────────────────┐
│ [←] [🔖 景點口袋庫]                    [總計 12] [📌 3]│
│     儲存喜愛的地點，隨時排入行程或一鍵開啟導航         │
└────────────────────────────────────────────────────────┘

[After]
┌────────────────────────────────────────────────────────┐
│ [←] [🔖 景點口袋庫]                    [總計 12] [📌 3]│
└────────────────────────────────────────────────────────┘
```

### 2.2 佈局結構 (DOM Topology)
```tsx
<header className="shrink-0 px-4 sm:px-6 pt-[calc(max(env(safe-area-inset-top,0px),0px)+0.75rem)] pb-3 border-b border-black/5 dark:border-white/10 bg-white/70 dark:bg-[#182320]/70 backdrop-blur-xl flex items-center justify-between z-20">
    <div className="flex items-center gap-3">
        <button
            type="button"
            onClick={() => {
                haptic.selection()
                onBack()
            }}
            className="w-9 h-9 rounded-full flex items-center justify-center bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-[#1E2927] dark:text-[#E5EBEA] active:scale-90 transition-all cursor-pointer"
            aria-label="Back"
        >
            <ChevronLeft className="w-5 h-5 -ml-0.5" />
        </button>
        <h1 className="text-base font-bold text-[#1E2927] dark:text-[#E5EBEA] tracking-tight flex items-center gap-1.5">
            <Bookmark className="w-4 h-4 fill-amber-500/30 text-[#E56E25] dark:text-amber-400" />
            <span>{t('poi_drawer_title') || "全域景點口袋庫"}</span>
        </h1>
    </div>

    {/* 📊 統計徽章 */}
    <div className="flex items-center gap-1.5">
        ...
    </div>
</header>
```

---

## 3. Architecture & Data Model (架構與相容性)

1. **元件層 (`PoiPoolView.tsx`)**：
   - 移除包含 `{currentTrip ? currentTrip.title : (t('poi_drawer_desc') || "儲存喜愛地點，隨時排入行程")}` 的 `<p>` 標籤。
   - 扁平化包裹層，將 `<h1 ...>` 直接置於 `flex items-center gap-3` 容器內。
2. **字典層 (`poi.ts`)**：
   - 保留 `poi_drawer_desc` 於字典檔案，維持向下相容性與無破壞變更原則。

---

## 4. Edge Cases & Boundary Conditions (邊界條件與異常處理)

- **長文字標題 (Long Title Handling)**：
  若語系翻譯為長字串，`h1` 具備自然收斂能力，且右側統計徽章保持 `shrink-0`，不會造成排版破裂。
- **安全區域 (Safe Area Insets)**：
  維持 `pt-[calc(max(env(safe-area-inset-top,0px),0px)+0.75rem)] pb-3`，完美相容 iOS 動態島與瀏海屏。

---

## 5. Acceptance Criteria (驗收標準清單)

- [ ] **AC-1**: `PoiPoolView` 渲染時，不再呈現「儲存喜愛的地點，隨時排入行程或一鍵開啟導航」副標題文字。
- [ ] **AC-2**: 返回按鈕、口袋庫標題、總計徽章與已釘選徽章處於同一水平垂直置中軸線。
- [ ] **AC-3**: 靜態檢查通過：`npx tsc --noEmit` 0 錯誤。
- [ ] **AC-4**: 程式碼檢查通過：`npm run lint` 0 錯誤、0 警告。
- [ ] **AC-5**: 單元測試通過：`npx vitest run` 80 檔測試 100% Passed。
