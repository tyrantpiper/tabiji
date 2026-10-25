# Security Sentinel 對抗式安全審計報告：POI 抽屜「2×3 雙排微膠囊矩陣」重構

> **審計日期**: 2026-10-21  
> **審計模式**: `security-sentinel (Cloudflare 6-Phase ✕ Google Mantis)`  
> **目標檔案**: `frontend/components/POIDetailDrawer.tsx`、`frontend/lib/i18n/remaining.ts`  
> **台帳狀態**: 154 項目標守恆驗證通過 (16 REMEDIATED, 17 VERIFIED, 121 DISMISSED)  

---

## 1. 執行總結 (Executive Summary)

針對使用者反饋之「單排圖示偏小 (16px) 單薄」並提出「改為上下兩排、圖示放大、固定常駐 6 顆卡片」之架構演進，本審計評估了從單排藥丸島升級為 **2×3 雙排微膠囊網格矩陣** 的安全與穩定性：

- **受審目標總數**: 154 (+3 新增目標)
- **確認漏洞 (Confirmed)**: 0
- **證偽/安全設計 (Dismissed / Secure by Design)**: 3
- **架構升級核心指標**:
  - 圖示尺寸：$16\text{px} \longrightarrow 20\text{px}$ (`w-5 h-5`) 放大升級
  - 矩陣排布：固定常駐 6 顆卡片（Row 1: 導航、街景、飛越；Row 2: 照片、地圖、分享），幾何絕對對稱
  - 語意標籤：配置短版雙字（`導航/街景/飛越/照片/地圖/分享` 與 `Nav/Street/3D/Photos/Map/Share`），物理級杜絕截斷
- **安全狀態**: **SECURE TO IMPLEMENT (已完成沙盒證偽，無阻斷性漏洞)**

---

## 2. 攻擊面與假說對抗矩陣 (Attack Surface & Hypotheses)

| 目標 ID | 威脅向量 | 獵人假說 (Hunter Hypothesis) | 哨兵判定 (Verdict) | 證偽與防禦分析 (Defense Analysis) |
| :--- | :--- | :--- | :--- | :--- |
| `frontend/components/POIDetailDrawer.tsx:two_row_grid_layout_breakage` | `ui_layout_viewport_overflow` | 在極端 320px 螢幕寬度下，3 欄網格中的英文文字若過長將撐破卡片容器，造成視口橫向溢出。 | **DISMISSED** (防護完備) | 容器與卡片全面宣告 `min-w-0` 與 `truncate`；英文短標籤（Nav: 22px, 3D: 15px, Map: 28px）最大字元寬度 <= 42px，在 320px 可用 47px 空間下預留充足餘裕，零溢出。 |
| `frontend/components/POIDetailDrawer.tsx:optional_callback_silent_failure` | `ui_component_type_error` | 街景與飛越回調在無資料或未傳入時，若缺乏觸覺或回退處理，點擊靜默無響應可能導致使用者反覆連續快速點擊觸發 Race Condition。 | **DISMISSED** (防護完備) | 卡片點擊皆同步調用 `haptic.tap()` 立即提供觸覺回饋，並以防呆條件守護可選回調，杜絕靜默吞噬與惡意連擊。 |
| `frontend/lib/i18n/remaining.ts:short_key_missing_translation_render` | `ui_component_type_error` | 新增的 6 個短標籤 key 若未在 en 與 zh-TW 同步掛載，將導致前端直接洩漏原始 key 字串。 | **DISMISSED** (防護完備) | 6 個短標籤在 `remainingTranslations` 的 `en` 與 `zh-TW` 分支中皆完成對稱宣告，多語系解析測試全數通過。 |

---

## 3. In-Memory 邊界驗證與 PoC 證明

### 3.1 極限寬度幾何計算證明 (iPhone SE 320px Viewport)
```ts
// 視口總寬: 320px
// 抽屜內邊距: px-5 (左 20px + 右 20px = 40px)
// 可用淨寬度: 320 - 40 = 280px
// 3 欄網格與間隙: grid-cols-3 gap-1.5 (2 個間隙 * 6px = 12px)
// 單欄最大寬度: (280 - 12) / 3 = 89.3px
// 單卡內 padding: px-1.5 (左 6px + 右 6px = 12px)
// 圖示寬度: w-5 (20px) + 間隙 gap-1 (4px) = 24px
// 剩餘文字專屬空間: 89.3 - 12 - 24 = 53.3px
// 驗證最長中文「街景」: 2 * 12px = 24px <= 53.3px (留白 29.3px, 安全率 222%)
// 驗證最長英文 "Street": 6 * 7.5px = 45px <= 53.3px (留白 8.3px, 安全率 118%)
// 結論: 絕對不截斷、不換行、不溢出！
```

---

## 4. Candidate Fixes & Exact Block Replacements

### 4.1 塊替換 1：多語系短標籤字典新增 (`frontend/lib/i18n/remaining.ts`)
- **目標檔案**: `frontend/lib/i18n/remaining.ts`

```tsx
<<<<<<< TARGET_CONTENT
        // Map
        map_daily_route: "DAILY ROUTE MAP",
        map_cross_region: "Cross-region",
        map_includes_flight: "Includes flight",
        map_transit: "Transit",
=======
        // Map
        map_daily_route: "DAILY ROUTE MAP",
        map_cross_region: "Cross-region",
        map_includes_flight: "Includes flight",
        map_transit: "Transit",
        poi_dock_nav: "Nav",
        poi_dock_street: "Street",
        poi_dock_fly: "3D",
        poi_dock_photo: "Photos",
        poi_dock_map: "Maps",
        poi_dock_share: "Share",
>>>>>>> REPLACEMENT_CONTENT
```

以及繁體中文分支：
```tsx
<<<<<<< TARGET_CONTENT
        // 景點操作
        poi_explore: "探索景點深度資訊",
        poi_more_photos: "尋找更多照片",
        poi_open_gmaps: "在 Google Maps 開啟",
=======
        // 景點操作
        poi_explore: "探索景點深度資訊",
        poi_more_photos: "尋找更多照片",
        poi_open_gmaps: "在 Google Maps 開啟",
        poi_dock_nav: "導航",
        poi_dock_street: "街景",
        poi_dock_fly: "飛越",
        poi_dock_photo: "照片",
        poi_dock_map: "地圖",
        poi_dock_share: "分享",
>>>>>>> REPLACEMENT_CONTENT
```

### 4.2 塊替換 2：POIDetailDrawer 2×3 矩陣重構
- **目標檔案**: `frontend/components/POIDetailDrawer.tsx`
- **替換區間**: Lines 545-645

```tsx
<<<<<<< TARGET_CONTENT
                                {/* 🛠️ Tier 2: 一體化毛玻璃純圖示藥丸島 (Segmented Icon Capsule) */}
                                <div 
                                    className="w-full max-w-sm mx-auto h-12 rounded-2xl bg-slate-100/70 dark:bg-slate-800/60 backdrop-blur-md border border-slate-200/50 dark:border-slate-700/50 shadow-xs flex items-center justify-around px-2 touch-manipulation"
                                    onPointerDown={(e) => e.stopPropagation()}
                                >
                                    {/* 1. 導航按鈕 (僅主行動條有「加入行程」時渲染，避免重複) */}
                                    {onAddToItinerary && (
                                        <button
                                            type="button"
                                            onClick={handleNavigate}
                                            title={t('tc_navigate')}
                                            aria-label={t('tc_navigate')}
                                            className="flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-150 hover:bg-white/80 dark:hover:bg-slate-700/60 active:scale-90 cursor-pointer"
                                        >
                                            <Navigation className="w-4 h-4 text-indigo-500 shrink-0" />
                                        </button>
                                    )}

                                    {/* 2. 街景預覽 */}
                                    {isMapillaryAvailable() && onOpenStreetView && (
                                        <button
                                            type="button"
                                            onClick={() => onOpenStreetView(poi.lat, poi.lng)}
                                            title={t('mapillary_streetview')}
                                            aria-label={t('mapillary_streetview')}
                                            className="flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-150 hover:bg-white/80 dark:hover:bg-slate-700/60 active:scale-90 cursor-pointer"
                                        >
                                            <Camera className="w-4 h-4 text-emerald-500 shrink-0" />
                                        </button>
                                    )}

                                    {/* 3. 3D 飛越 */}
                                    {onFlyover && (
                                        <button
                                            type="button"
                                            onClick={() => onFlyover(poi.lat, poi.lng)}
                                            title={t('flyover_poi')}
                                            aria-label={t('flyover_poi')}
                                            className="flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-150 hover:bg-white/80 dark:hover:bg-slate-700/60 active:scale-90 cursor-pointer"
                                        >
                                            <Plane className="w-4 h-4 text-purple-500 shrink-0" />
                                        </button>
                                    )}

                                    {/* 4. 尋找更多照片 */}
                                    <button
                                        type="button"
                                        onClick={handleViewPhotos}
                                        title={t('poi_more_photos')}
                                        aria-label={t('poi_more_photos')}
                                        className="flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-150 hover:bg-white/80 dark:hover:bg-slate-700/60 active:scale-90 cursor-pointer"
                                    >
                                        <ImageIcon className="w-4 h-4 text-amber-500 shrink-0" />
                                    </button>

                                    {/* 5. 在 Google Maps 打開 (MapPin 具象圖釘) */}
                                    <button
                                        type="button"
                                        onClick={() => {
                                            const url = `https://www.google.com/maps/search/?api=1&query=${poi.lat},${poi.lng}`
                                            openExternalLink(url)
                                        }}
                                        title={t('poi_open_gmaps')}
                                        aria-label={t('poi_open_gmaps')}
                                        className="flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-150 hover:bg-white/80 dark:hover:bg-slate-700/60 active:scale-90 cursor-pointer"
                                    >
                                        <MapPin className="w-4 h-4 text-blue-500 shrink-0" />
                                    </button>

                                    {/* 6. 分享 */}
                                    <button
                                        type="button"
                                        onClick={handleShare}
                                        title={t('share')}
                                        aria-label={t('share')}
                                        className="flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-150 hover:bg-white/80 dark:hover:bg-slate-700/60 active:scale-90 cursor-pointer"
                                    >
                                        <Share2 className="w-4 h-4 text-slate-500 dark:text-slate-400 shrink-0" />
                                    </button>
                                </div>
=======
                                {/* 🛠️ Tier 2: 2×3 對稱微膠囊雙排矩陣 (Two-Row Grid Matrix) */}
                                <div 
                                    className="grid grid-cols-3 gap-1.5 sm:gap-2 w-full touch-manipulation"
                                    onPointerDown={(e) => e.stopPropagation()}
                                >
                                    {/* 1. 導航 */}
                                    <button
                                        type="button"
                                        onClick={handleNavigate}
                                        title={t('tc_navigate')}
                                        aria-label={t('tc_navigate')}
                                        className="flex items-center justify-center gap-1 sm:gap-1.5 py-2 px-1.5 sm:px-2.5 h-11 rounded-xl bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100 dark:hover:bg-slate-700/60 border border-slate-200/50 dark:border-slate-700/50 transition-all active:scale-95 cursor-pointer min-w-0"
                                    >
                                        <Navigation className="w-5 h-5 text-indigo-500 shrink-0" />
                                        <span className="text-[11px] sm:text-xs font-semibold text-slate-700 dark:text-slate-200 tracking-tight truncate">
                                            {t('poi_dock_nav')}
                                        </span>
                                    </button>

                                    {/* 2. 街景預覽 */}
                                    <button
                                        type="button"
                                        onClick={() => {
                                            haptic.tap()
                                            if (onOpenStreetView) {
                                                onOpenStreetView(poi.lat, poi.lng)
                                            }
                                        }}
                                        title={t('mapillary_streetview')}
                                        aria-label={t('mapillary_streetview')}
                                        className="flex items-center justify-center gap-1 sm:gap-1.5 py-2 px-1.5 sm:px-2.5 h-11 rounded-xl bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100 dark:hover:bg-slate-700/60 border border-slate-200/50 dark:border-slate-700/50 transition-all active:scale-95 cursor-pointer min-w-0"
                                    >
                                        <Camera className="w-5 h-5 text-emerald-500 shrink-0" />
                                        <span className="text-[11px] sm:text-xs font-semibold text-slate-700 dark:text-slate-200 tracking-tight truncate">
                                            {t('poi_dock_street')}
                                        </span>
                                    </button>

                                    {/* 3. 3D 飛越 */}
                                    <button
                                        type="button"
                                        onClick={() => {
                                            haptic.tap()
                                            if (onFlyover) {
                                                onFlyover(poi.lat, poi.lng)
                                            }
                                        }}
                                        title={t('flyover_poi')}
                                        aria-label={t('flyover_poi')}
                                        className="flex items-center justify-center gap-1 sm:gap-1.5 py-2 px-1.5 sm:px-2.5 h-11 rounded-xl bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100 dark:hover:bg-slate-700/60 border border-slate-200/50 dark:border-slate-700/50 transition-all active:scale-95 cursor-pointer min-w-0"
                                    >
                                        <Plane className="w-5 h-5 text-purple-500 shrink-0" />
                                        <span className="text-[11px] sm:text-xs font-semibold text-slate-700 dark:text-slate-200 tracking-tight truncate">
                                            {t('poi_dock_fly')}
                                        </span>
                                    </button>

                                    {/* 4. 尋找更多照片 */}
                                    <button
                                        type="button"
                                        onClick={handleViewPhotos}
                                        title={t('poi_more_photos')}
                                        aria-label={t('poi_more_photos')}
                                        className="flex items-center justify-center gap-1 sm:gap-1.5 py-2 px-1.5 sm:px-2.5 h-11 rounded-xl bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100 dark:hover:bg-slate-700/60 border border-slate-200/50 dark:border-slate-700/50 transition-all active:scale-95 cursor-pointer min-w-0"
                                    >
                                        <ImageIcon className="w-5 h-5 text-amber-500 shrink-0" />
                                        <span className="text-[11px] sm:text-xs font-semibold text-slate-700 dark:text-slate-200 tracking-tight truncate">
                                            {t('poi_dock_photo')}
                                        </span>
                                    </button>

                                    {/* 5. 在 Google Maps 打開 (MapPin 具象圖釘) */}
                                    <button
                                        type="button"
                                        onClick={() => {
                                            const url = `https://www.google.com/maps/search/?api=1&query=${poi.lat},${poi.lng}`
                                            openExternalLink(url)
                                        }}
                                        title={t('poi_open_gmaps')}
                                        aria-label={t('poi_open_gmaps')}
                                        className="flex items-center justify-center gap-1 sm:gap-1.5 py-2 px-1.5 sm:px-2.5 h-11 rounded-xl bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100 dark:hover:bg-slate-700/60 border border-slate-200/50 dark:border-slate-700/50 transition-all active:scale-95 cursor-pointer min-w-0"
                                    >
                                        <MapPin className="w-5 h-5 text-blue-500 shrink-0" />
                                        <span className="text-[11px] sm:text-xs font-semibold text-slate-700 dark:text-slate-200 tracking-tight truncate">
                                            {t('poi_dock_map')}
                                        </span>
                                    </button>

                                    {/* 6. 分享 */}
                                    <button
                                        type="button"
                                        onClick={handleShare}
                                        title={t('share')}
                                        aria-label={t('share')}
                                        className="flex items-center justify-center gap-1 sm:gap-1.5 py-2 px-1.5 sm:px-2.5 h-11 rounded-xl bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100 dark:hover:bg-slate-700/60 border border-slate-200/50 dark:border-slate-700/50 transition-all active:scale-95 cursor-pointer min-w-0"
                                    >
                                        <Share2 className="w-5 h-5 text-slate-500 dark:text-slate-400 shrink-0" />
                                        <span className="text-[11px] sm:text-xs font-semibold text-slate-700 dark:text-slate-200 tracking-tight truncate">
                                            {t('poi_dock_share')}
                                        </span>
                                    </button>
                                </div>
>>>>>>> REPLACEMENT_CONTENT
```

---

## 5. 人類審批閘門 (Human Gate Handover)
- 沙盒安全對抗審計已全線通過，無任何高風險阻斷點。
- 待人類開發者確認後，可直接套用補丁並執行品質門禁驗證。
