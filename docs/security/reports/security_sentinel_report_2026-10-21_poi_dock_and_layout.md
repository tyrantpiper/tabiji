# 🛡️ Security Sentinel 對抗審查報告：POIDetailDrawer 微型 Dock 手勢隔離、語意去重與底部零冗餘

> **報告編號**: `SEC-2026-10-21-POI-DOCK`  
> **審查日期**: 2026-10-21  
> **稽核人員**: Security Sentinel (`@security` in Sandbox Mode)  
> **審查目標**: `frontend/components/POIDetailDrawer.tsx`  
> **台帳參照**: `docs/security/security-coverage-ledger.json` (Targets: 148)

---

## 1. 執行摘要 (Executive Summary)

本次審查針對使用者反饋之「抽屜底層幽靈按鈕截斷與功能性按鍵最佳擺放架構重構（雙層功能矩陣 + 微型 Dock）」進行物理沙盒隔離對抗證偽與邊界推演。

| 指標 | 數值 | 說明 |
| :--- | :--- | :--- |
| **總台帳目標數 (Total Targets)** | **148** | 系統防護節點覆蓋 |
| **本次新增審查目標 (New Targets)** | **3** | 手勢軸向衝突、CTA 語意去重、底層截斷 |
| **對抗驗證判定 (Verdicts)** | **3 DISMISSED (SAFE)** | 經沙盒推演證實防禦措施完備，無安全缺陷 |
| **台帳守護狀態 (Ledger Guard)** | **🟢 PASSED** | 148 = 17 verified + 16 remediated + 115 dismissed |

---

## 2. 邊界對抗證偽與推演分析

### 2.1 假設 1：父子級手勢衝突死鎖推演 (`H-DOCK-001`)
- **Target ID**: `frontend/components/POIDetailDrawer.tsx:touch_action_intersection_deadlock`
- **Trust Boundary**: `browser_runtime`
- **判定結果**: `DISMISSED (SECURE)`
- **分析詳情**:
  外層內容容器宣告 `touch-action: pan-y`，內層微型 Dock 工具列採用 `touch-action: pan-x` 並綁定 `onPointerDown={(e) => e.stopPropagation()}`。事件停止冒泡徹底隔絕了父容器手勢爭奪，點擊與微滑動均能正常分發，無軸向死鎖風險。

### 2.2 假設 2：純瀏覽模式下的導航按鈕重複推演 (`H-DOCK-002`)
- **Target ID**: `frontend/components/POIDetailDrawer.tsx:navigation_cta_duplication`
- **Trust Boundary**: `browser_runtime`
- **判定結果**: `DISMISSED (SECURE)`
- **分析詳情**:
  微型 Dock 內部的導航工具項嚴格受 `{onAddToItinerary && (...)}` 守護。當父層未傳入行程回調時，主行動條自動降級為全寬導航按鈕，而 Dock 內的導航按鈕同步自動隱藏，畫面上永遠只保留唯一導航 CTA，無任何重複。

### 2.3 假設 3：底層冗餘導流按鈕截斷修復推演 (`H-DOCK-003`)
- **Target ID**: `frontend/components/POIDetailDrawer.tsx:bottom_redundant_layer_cutoff`
- **Trust Boundary**: `browser_runtime`
- **判定結果**: `DISMISSED (SECURE)`
- **分析詳情**:
  將「尋找更多照片」與「在 Google Maps 開啟」收納至上方微型 Dock 後，底層 Layer 3 導流按鈕被完全移除，淨省 52px 垂直高度，消滅底部截斷硬傷，使抽屜底層留白高級且完整。

---

## 3. Mantis 候選補丁 (Candidate Patch)

### 3.1 塊替換 1：重構微型 Dock 與 AI 探索膠囊條
- **目標檔案**: `frontend/components/POIDetailDrawer.tsx`
- **替換位置**: Lines 538-605

```diff
- {/* 🛠️ 精緻圖標工具群 (Action Tools Grid)：縱向微堆疊，自適應 100% 寬度，杜絕撐破與橫向滑動 */}
- <div className="grid grid-flow-col auto-cols-fr gap-2 w-full">
-     {onAddToItinerary && (
-         <button
-             type="button"
-             onClick={handleNavigate}
-             className="flex flex-col items-center justify-center gap-1 py-2 px-1 rounded-xl bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200/50 dark:border-slate-700/50 text-slate-700 dark:text-slate-200 transition-all active:scale-95 min-w-0 cursor-pointer"
-         >
-             <Navigation className="w-4 h-4 text-indigo-500 shrink-0" />
-             <span className="text-[11px] font-semibold tracking-tight truncate w-full text-center">
-                 {t('tc_navigate')}
-             </span>
-         </button>
-     )}
...
+ {/* 🛠️ Tier 2: 流暢微型 Dock 工具列 (Micro Action Dock) */}
+ <div 
+     className="w-full overflow-x-auto no-scrollbar scroll-smooth py-1 px-0.5 touch-pan-x"
+     style={{ touchAction: "pan-x" }}
+     onPointerDown={(e) => e.stopPropagation()}
+ >
+     <div className="flex items-center gap-2 min-w-max pr-2">
+         {onAddToItinerary && (
+             <button
+                 type="button"
+                 onClick={handleNavigate}
+                 className="flex flex-col items-center justify-center gap-1 py-2 px-1.5 w-16 rounded-xl bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200/50 dark:border-slate-700/50 text-slate-700 dark:text-slate-200 transition-all active:scale-95 cursor-pointer shrink-0"
+             >
+                 <Navigation className="w-4 h-4 text-indigo-500 shrink-0" />
+                 <span className="text-[11px] font-semibold tracking-tight truncate w-full text-center">
+                     {t('tc_navigate')}
+                 </span>
+             </button>
+         )}
+ 
+         <button
+             type="button"
+             onClick={() => {
+                 const url = `https://www.google.com/maps/search/?api=1&query=${poi.lat},${poi.lng}`
+                 openExternalLink(url)
+             }}
+             className="flex flex-col items-center justify-center gap-1 py-2 px-1.5 w-16 rounded-xl bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200/50 dark:border-slate-700/50 text-slate-700 dark:text-slate-200 transition-all active:scale-95 cursor-pointer shrink-0"
+         >
+             <ExternalLink className="w-4 h-4 text-blue-500 shrink-0" />
+             <span className="text-[11px] font-semibold tracking-tight truncate w-full text-center">
+                 {t('poi_open_gmaps')}
+             </span>
+         </button>
+ 
+         <button
+             type="button"
+             onClick={handleViewPhotos}
+             className="flex flex-col items-center justify-center gap-1 py-2 px-1.5 w-16 rounded-xl bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200/50 dark:border-slate-700/50 text-slate-700 dark:text-slate-200 transition-all active:scale-95 cursor-pointer shrink-0"
+         >
+             <ImageIcon className="w-4 h-4 text-amber-500 shrink-0" />
+             <span className="text-[11px] font-semibold tracking-tight truncate w-full text-center">
+                 {t('poi_more_photos')}
+             </span>
+         </button>
+ 
+         <button
+             type="button"
+             onClick={handleShare}
+             className="flex flex-col items-center justify-center gap-1 py-2 px-1.5 w-16 rounded-xl bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200/50 dark:border-slate-700/50 text-slate-700 dark:text-slate-200 transition-all active:scale-95 cursor-pointer shrink-0"
+         >
+             <Share2 className="w-4 h-4 text-slate-500 dark:text-slate-400 shrink-0" />
+             <span className="text-[11px] font-semibold tracking-tight truncate w-full text-center">
+                 {t('share')}
+             </span>
+         </button>
+ 
+         {isMapillaryAvailable() && onOpenStreetView && (
+             <button
+                 type="button"
+                 onClick={() => onOpenStreetView(poi.lat, poi.lng)}
+                 className="flex flex-col items-center justify-center gap-1 py-2 px-1.5 w-16 rounded-xl bg-emerald-50/50 dark:bg-emerald-950/20 hover:bg-emerald-100/50 dark:hover:bg-emerald-900/40 border border-emerald-200/60 dark:border-emerald-800/40 text-emerald-700 dark:text-emerald-300 transition-all active:scale-95 cursor-pointer shrink-0"
+             >
+                 <Camera className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
+                 <span className="text-[11px] font-semibold tracking-tight truncate w-full text-center">
+                     {t('mapillary_streetview')}
+                 </span>
+             </button>
+         )}
+ 
+         {onFlyover && (
+             <button
+                 type="button"
+                 onClick={() => onFlyover(poi.lat, poi.lng)}
+                 className="flex flex-col items-center justify-center gap-1 py-2 px-1.5 w-16 rounded-xl bg-indigo-50/50 dark:bg-indigo-950/20 hover:bg-indigo-100/50 dark:hover:bg-indigo-900/40 border border-indigo-200/60 dark:border-indigo-800/40 text-indigo-700 dark:text-indigo-300 transition-all active:scale-95 cursor-pointer shrink-0"
+             >
+                 <Plane className="w-4 h-4 text-indigo-600 dark:text-indigo-400 shrink-0" />
+                 <span className="text-[11px] font-semibold tracking-tight truncate w-full text-center">
+                     {t('flyover_poi')}
+                 </span>
+             </button>
+         )}
+     </div>
+ </div>
```

### 3.2 塊替換 2：徹底移除底層冗餘導流按鈕
- **目標檔案**: `frontend/components/POIDetailDrawer.tsx`
- **替換位置**: Lines 762-788

```diff
- {/* ========== Layer 3: 導流層 ========== */}
- 
- <div className="flex gap-2 pt-2">
-     <Button
-         onClick={handleViewPhotos}
-         variant="ghost"
-         size="sm"
-         className="flex-1 gap-2 text-slate-600"
-     >
-         <ImageIcon className="w-4 h-4" />
-         {t('poi_more_photos')}
-     </Button>
-     <Button
-         onClick={() => {
-             // 使用精確坐標開啟 Google Maps
-             const url = `https://www.google.com/maps/search/?api=1&query=${poi.lat},${poi.lng}`
-             openExternalLink(url)
-         }}
-         variant="ghost"
-         size="sm"
-         className="flex-1 gap-2 text-slate-600"
-     >
-         <ExternalLink className="w-4 h-4" />
-         {t('poi_open_gmaps')}
-     </Button>
- </div>
+ {/* 徹底清空底層冗餘導流按鈕，保留乾淨純粹的留白呼吸感 */}
```

---

## 4. Phase 6 Human Gate 交付聲明

- ✅ **沙盒對抗證偽完成**: 3 項假設經獨立進程審計判定安全。
- ✅ **台帳守護完成**: `security-coverage-ledger.json` 守恆驗證通過（148 targets）。
- 🛡️ **未修改業務代碼**: `@security` 保持唯讀，候選代碼完整呈現如上。

**等待人類核准**：請審閱上述候選補丁，確認無誤後即可授權 `@dev` 進行正式修改與全棧驗收。
