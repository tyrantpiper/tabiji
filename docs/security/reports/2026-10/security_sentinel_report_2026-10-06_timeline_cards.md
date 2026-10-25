# 🛡️ Security Sentinel 對抗安全審計報告：時間軸卡片與互動模組 (Timeline Cards)

> **審查日期**: 2026-10-06  
> **稽核模式**: Sentinel Physical Adversarial Sandbox (`runner.py` ✕ `agy.exe -p --sandbox`)  
> **目標範圍**: `frontend/components/timeline-card.tsx`, `frontend/components/itinerary/SortableTimelineCard.tsx`, `frontend/lib/utils.ts`  
> **基準 Commit**: `4d9a84e09cd6b346adcf654830961c083edc26f6`  

---

## 📊 一、執行摘要 (Executive Summary)

- **總審查標的**: 3 項假說
- **實質安全隱患 (Confirmed)**: 1 項 (`openExternalLink` 偽協議 DOM-XSS / 惡意重定向)
- **前置手勢防護 (Defensive Hardening)**: 2 項 (dnd-kit Pointer 冒泡劫持、表格與滑動刪除手勢競爭)
- **審查結論**: **CONDITIONAL PASS (附帶候選安全加固補丁)**

---

## 🔍 二、漏洞與弱點深度分析

### 1. [CONFIRMED] `openExternalLink` 偽協議執行 (Client-Side DOM-XSS)
- **檔案**: `frontend/lib/utils.ts#L26-L47`
- **攻擊向量**: Client-side XSS / Open Redirect via `javascript:` or `data:` URL
- **漏洞根因**:
  在 `openExternalLink(url)` 中，直接將未經驗證的外部字串傳遞給 `window.open(url, '_blank')` 或在 iOS PWA 下指派給 `a.href = url` 並觸發 `a.click()`。若行程資料或分享來源包含惡意連結（如 `javascript:/*...*/`），點擊卡片正面附屬表格或地圖按鈕將直接觸發任意腳本執行。
- **In-Memory 概念驗證 (PoC)**:
  ```typescript
  // In-Memory Test Case
  const maliciousUrl = "javascript:alert(document.cookie)";
  // 當前代碼行為:
  // a.href = maliciousUrl; a.click(); => 觸發腳本執行！
  ```

### 2. [DEFENSIVE HARDENING] dnd-kit Pointer 感測器冒泡干擾
- **檔案**: `frontend/components/timeline-card.tsx`
- **弱點**: 卡片內部的縮圖點擊、附屬表格點擊與底部按鈕列若僅監聽 `onClick`，其 `pointerdown` 事件仍會冒泡至外層 `@dnd-kit` 的 `useSortable` 監聽器，導致使用者在行動端輕觸縮圖或點擊外鏈時，被誤判為長按拖曳排序。
- **防禦手段**: 在可互動元素容器上綁定 `onPointerDown={(e) => e.stopPropagation()}`。

### 3. [DEFENSIVE HARDENING] 表格橫向滾動與向左滑動刪除手勢衝突
- **檔案**: `frontend/components/timeline-card.tsx` 附屬表格區塊
- **弱點**: 當使用者在包含多欄位的外鏈表格橫向滑動查看時，若外層卡片掛載向左滑動刪除手勢，會引發瀏覽器原生滾動與手勢庫競爭。
- **防禦手段**: 表格容器加上 `touch-pan-x` 與 `onPointerDown={(e) => e.stopPropagation()}`，實現手勢物理隔離。

---

## 🛠️ 三、候選加固補丁 (Candidate Patch)

### 補丁 1: `frontend/lib/utils.ts` 安全協議校驗
```diff
--- a/frontend/lib/utils.ts
+++ b/frontend/lib/utils.ts
@@ -26,6 +26,13 @@ export function formatCurrency(
 export function openExternalLink(url?: string | null) {
     if (!url) return;
+    
+    const trimmed = url.trim();
+    // 🛡️ Sentinel Defense: 僅允許安全的外部協議，阻斷 javascript: / data: / vbscript:
+    if (!/^(https?|maps|geo|tel|mailto):/i.test(trimmed)) {
+        console.warn(`[Security] Blocked unsafe external link protocol: ${trimmed}`);
+        return;
+    }
     
     const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || 
                   (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
```

### 補丁 2: `frontend/components/timeline-card.tsx` 互動元素手勢隔離
- 在右側 72px 縮圖、附屬表格容器及底部按鈕區加入 `onPointerDown={(e) => e.stopPropagation()}` 與 `touch-pan-x`。

---

## 🏛️ 四、L0 憲法審查守門 (Human Gate Handover)
遵照 L0 憲法規範：「@security 僅產出報告與候選補丁，由人類決定修復方案」。此報告已交付，等待 Ryan 核准後方可進入實作。
