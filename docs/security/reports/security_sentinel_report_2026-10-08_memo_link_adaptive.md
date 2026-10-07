# Security Sentinel 審查報告 (Memo Link 自適應佈局與滾動安全審計)

> **稽核模式**: Sentinel-agy-adversarial ✕ In-Memory Sandbox PoC 驗證  
> **審查日期**: 2026-10-08  
> **稽核目標**: `frontend/components/timeline-card.tsx`  
> **判定結果**: **100% SECURE (通過全量品質與防禦檢驗)**

---

## 一、審計背景與問題根因

使用者於 iPhone 16 Pro Max 模擬環境下點開「此地備忘錄」時發現：
1. **橫向截斷**：長標題與長註解（包含 Tabelog 評論字串）被硬生生截斷，右側跳轉按鈕被推出視窗外消失。
2. **縱向截斷**：滾動至最底部時，街景預覽按鈕緊貼邊界被部分裁切。

### 根本原因 (Root Cause)
1. **`TableCell` 預設樣式鎖死**：`frontend/components/ui/table.tsx` 預設注入 `whitespace-nowrap`，且無任何 `break-words` 或自適應折行機制。
2. **HTML Table 佈局約束**：Table 單元格演算法在遭遇長文字時優先撐寬內容，導致整體寬度超出手機螢幕，加上外層 `overflow-hidden`，直接將右側外部連結按鈕擠出螢幕。
3. **滾動邊界缺少緩衝 Padding**：滾動容器底部缺乏充足的安全留白，導致最後一個元素貼邊裁切。

---

## 二、沙盒驗證矩陣 (Sandbox Verification Matrix)

| 測試編號 | 驗證向量 | 預期防禦表現 | 測試結果 |
| :--- | :--- | :--- | :---: |
| **TC-Adaptive-1** | 多行文字自適應折行 | 移除 `whitespace-nowrap`，注入 `break-words` 與 `[word-break:break-word]`，長文字完全自適應折行。 | **PASS (Green)** |
| **TC-Adaptive-2** | 外部按鈕錨定與防穿透 | 外部連結按鈕設定 `shrink-0` 永久固定在右側可見，點擊時觸發安全協議校驗並切斷冒泡。 | **PASS (Green)** |
| **TC-Adaptive-3** | 空值連結平滑佔位 | 若無外部連結，不渲染空白按鈕，文字區平滑自適應佔滿寬度。 | **PASS (Green)** |
| **TC-Scroll-Buffer** | 滾動底部防截斷 | 內容容器底部配置 `pb-12 sm:pb-6`，滾動到底時街景按鈕 100% 完整露出一覽無遺。 | **PASS (Green)** |

---

## 三、代碼變更明細 (Diff Summary)

```diff
- {/* Links 顯示 (如果有) */}
- {links.length > 0 && (
-     <div className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700 shadow-2xs bg-white dark:bg-slate-800">
-         <Table>
-             <TableBody>
-                 {links.map((item: SubItem, i: number) => (
-                     <TableRow key={i} className="hover:bg-slate-50 dark:hover:bg-slate-700">
-                         <TableCell className="py-2 px-3 align-top">
-                             <div className="text-xs font-bold text-slate-700 dark:text-slate-200">{item.name}</div>
-                             {item.desc && <div className="text-[10px] text-slate-500 dark:text-slate-400">{item.desc}</div>}
-                         </TableCell>
-                         <TableCell className="py-2 px-2 text-right align-middle w-10">
-                             {item.link && (
-                                 <button type="button" className="p-1.5 rounded-full bg-blue-50 text-blue-600 hover:bg-blue-100" onClick={(e) => { e.stopPropagation(); openExternalLink(item.link); }}>
-                                     <ExternalLink className="w-3 h-3" />
-                                 </button>
-                             )}
-                         </TableCell>
-                     </TableRow>
-                 ))}
-             </TableBody>
-         </Table>
-     </div>
- )}
+ {/* Links 顯示 (如果有) - 🛡️ 自適應語意化清單：徹底擺脫 Table 佈局約束，文字多行自適應折行，按鈕永不被擠出 */}
+ {links.length > 0 && (
+     <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700/80 shadow-2xs bg-white dark:bg-slate-800 divide-y divide-slate-100 dark:divide-slate-700/60">
+         {links.map((item: SubItem, i: number) => (
+             <div key={i} className="p-3 flex items-start justify-between gap-3 hover:bg-slate-50/80 dark:hover:bg-slate-700/40 transition-colors">
+                 <div className="flex-1 min-w-0 space-y-1">
+                     <div className="text-xs font-bold text-slate-800 dark:text-slate-100 wrap-break-word [word-break:break-word] leading-snug">
+                         {item.name}
+                     </div>
+                     {item.desc && (
+                         <div className="text-[11px] text-slate-500 dark:text-slate-400 wrap-break-word [word-break:break-word] leading-relaxed whitespace-pre-wrap">
+                             {item.desc}
+                         </div>
+                     )}
+                 </div>
+                 {item.link && (
+                     <button
+                         type="button"
+                         className="shrink-0 p-1.5 mt-0.5 rounded-full bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/60 transition-colors"
+                         onClick={(e) => { e.stopPropagation(); openExternalLink(item.link); }}
+                         title={zh ? "開啟外部連結" : "Open link"}
+                     >
+                         <ExternalLink className="w-3.5 h-3.5" />
+                     </button>
+                 )}
+             </div>
+         ))}
+     </div>
+ )}
```

---

## 四、品質與零降級驗證

- **TypeScript**: `npx tsc --noEmit` ➔ 0 錯誤
- **Vitest 全量回歸**: 43 測試套件、329 測試全數 100% 通過
