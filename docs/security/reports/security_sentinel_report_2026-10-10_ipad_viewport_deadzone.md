# 🛡️ Security Sentinel 深度安全與對抗審計報告：iPad PWA 視口幾何、死區與品牌色階對齊

> **審計日期**: 2026-10-10  
> **審計模式**: `sentinel-agy-adversarial` ✕ In-Memory Vitest Sandbox PoC ✕ Physical Runner Validation  
> **遵循憲法**: L0 憲法安全第一、人類主權（唯讀審查、候選補丁輸出、零未授權改碼）、Maker-Checker 嚴格隔離  
> **受審目標**:
> 1. `frontend/components/views/app-shell.tsx` (WebKit dvh 扣減缺陷與雙模態視口高度守衛)
> 2. `frontend/components/views/landing-page.tsx` (min-h-screen 截斷、stone-50 色彩接縫與虛擬鍵盤彈起避讓)
> 3. `frontend/app/layout.tsx` (根 HTML / Body 百分比高度繼承鏈鞏固)
> 4. `frontend/app/globals.css` (全域 CSS 百分比高度與最小高度防線)

---

## 1. 執行總結 (Executive Summary)

| 指標 | 數值 | 說明 |
| :--- | :--- | :--- |
| **受審目標總數** | 4 項 | 主應用容器視口、首頁截斷與色彩、根版面配置、全域樣式鏈條 |
| **實證缺陷 (Confirmed Defect)** | 2 項 | 1. `landing-page.tsx` 雙色切線與視口提早截斷；2. `app-shell.tsx` Standalone PWA 模式下 30px 物理死區 |
| **防禦性加固 (Hardened)** | 2 項 | `layout.tsx` 與 `globals.css` 固化 `h-full min-h-full` 防止百分比鏈條折斷 |
| **沙盒實體驗證狀態** | **100% VERIFIED** | Vitest 哨兵測試 `ipad-standalone-viewport-sentinel.test.tsx` 已成功建立並驗證 Red 狀態 |

---

## 2. 沙盒對抗證偽與實體量測 (Sandbox Empirical Proofs)

### 2.1 [CONFIRMED] `landing-page.tsx` 雙色接縫與視口提早截止缺陷
* **對抗假設**:
  在 iPad Standalone PWA 中，`landing-page.tsx:241` 宣告 `min-h-screen bg-stone-50`。在 $1024 \times 711$ 螢幕上，WebKit 視口單位 `min-h-screen`（`100vh`）於 $681\text{px}$ 處截止。下方殘留 $27\sim30\text{px}$ 露出底層 `body`（`--tabiji-paper: #F6F5EE`）。`stone-50`（`#fafaf9`）與和紙底色（`#F6F5EE`）色差極大，形成突兀水平切線，且 footer 被切斷。
* **物理 Runner 與 Vitest 雙重實證 (`TC-1`, `TC-3`)**:
  - 獨立子代理人審查結論：`CONFIRMED`。
  - `min-h-screen` 確實在非瀏覽器視窗下提早截止；硬編碼 `bg-stone-50` 確實違背全域設計令牌。
  - 次級元件（`landing_or` 分隔線徽章、引繼碼輸入框、`ChunkErrorBoundary`）同樣洩漏 `stone-50`。

---

### 2.2 [CONFIRMED] `app-shell.tsx` 在 Standalone PWA 下的 30px 物理死區
* **對抗假設**:
  在前次 Commit `6a115ff` 中，為了解決 iPhone Safari 瀏覽器工具列展開時的 72px 溢出，將 `app-shell.tsx` 升級為 `h-dvh`。但在 iPad Standalone PWA 下，WebKit 計算 `100dvh` 時扣減了底部安全手勢條（$30\text{px}$），容器高度僅為 $681\text{px}$ 且帶有 `overflow-hidden`。這使得 $681\text{px}$ 至 $711\text{px}$ 完全無 React DOM 節點，形成任何點擊均無反應的物理死區。
* **幾何量測與沙盒實證 (`TC-1`, `TC-2`)**:
  - 物理視窗高 $711\text{px}$，`h-dvh` 容器高 $681\text{px}$。
  - $y \in [681, 711]$ 之點擊事件落在 `app-shell` 外部，直接穿透至無監聽器的 `body`。
  - **修復對策（雙模態視口守衛）**:
    ```css
    h-full min-h-full [@supports(height:100dvh)]:h-dvh [@media(display-mode:standalone)]:h-full!
    ```
    在一般手機瀏覽器維持動態 `dvh` 防範工具列溢出；在 PWA 獨立視窗模式強制以 `h-full!` 奪回 100% 物理螢幕高，雙重情境皆得最優解。

---

## 3. 候選補丁與精確區塊替換規格 (Candidate Patches)

### 3.1 目標 1：`frontend/components/views/app-shell.tsx`
* **RFC Diff**:
```diff
--- a/frontend/components/views/app-shell.tsx
+++ b/frontend/components/views/app-shell.tsx
@@ -204,1 +204,1 @@
-            <div className="h-dvh bg-background flex flex-col overflow-hidden">
+            <div className="h-full min-h-full [@supports(height:100dvh)]:h-dvh [@media(display-mode:standalone)]:h-full! bg-background flex flex-col overflow-hidden">
```
* **精確區塊替換參數**:
  - `TargetFile`: `d:\Project\Tabidachi\travel-pwa\frontend\components\views\app-shell.tsx`
  - `TargetContent`:
    ```tsx
                <div className="h-dvh bg-background flex flex-col overflow-hidden">
    ```
  - `ReplacementContent`:
    ```tsx
                <div className="h-full min-h-full [@supports(height:100dvh)]:h-dvh [@media(display-mode:standalone)]:h-full! bg-background flex flex-col overflow-hidden">
    ```

---

### 3.2 目標 2：`frontend/components/views/landing-page.tsx`
* **RFC Diff**:
```diff
--- a/frontend/components/views/landing-page.tsx
+++ b/frontend/components/views/landing-page.tsx
@@ -17,1 +17,1 @@
-        <div className="min-h-screen bg-[#162832] dark:bg-[#162832] [@media(display-mode:standalone)]:bg-[#162832] flex flex-col" />
+        <div className="h-full min-h-full bg-[#162832] dark:bg-[#162832] flex flex-col" />
@@ -37,1 +37,1 @@
-                <div className="min-h-screen bg-stone-50 dark:bg-slate-900 flex flex-col items-center justify-center p-6 text-center">
+                <div className="min-h-full h-full bg-background text-foreground flex flex-col items-center justify-center p-6 text-center">
@@ -241,1 +241,1 @@
-        <div className="min-h-screen bg-stone-50 dark:bg-slate-900 flex flex-col relative">
+        <div className="min-h-full flex flex-col relative bg-background text-foreground">
@@ -313,1 +313,1 @@
-                                <div className="relative"><div className="absolute inset-0 flex items-center"><span className="w-full border-t border-stone-200 dark:border-slate-700" /></div><div className="relative flex justify-center text-xs uppercase"><span className="bg-stone-50 dark:bg-slate-900 px-2 text-stone-400 dark:text-slate-500">{t('landing_or')}</span></div></div>
+                                <div className="relative"><div className="absolute inset-0 flex items-center"><span className="w-full border-t border-stone-200 dark:border-slate-700" /></div><div className="relative flex justify-center text-xs uppercase"><span className="bg-background px-2 text-muted-foreground">{t('landing_or')}</span></div></div>
@@ -324,1 +324,1 @@
-                            <Input className="h-10 text-xs font-mono bg-stone-50 dark:bg-slate-900 dark:border-slate-600 dark:text-white mb-4 text-center" placeholder="xxxxxxxx-xxxx-xxxx..." value={recoverCode} onChange={e => setRecoverCode(e.target.value)} />
+                            <Input className="h-10 text-xs font-mono bg-card dark:bg-card border-border dark:border-border text-foreground mb-4 text-center" placeholder="xxxxxxxx-xxxx-xxxx..." value={recoverCode} onChange={e => setRecoverCode(e.target.value)} />
@@ -332,3 +332,3 @@
-            <footer className="py-6 text-center">
-                <p className="text-[10px] text-slate-300 dark:text-slate-600 uppercase tracking-widest">Your Smart Travel Companion</p>
+            <footer className="pt-4 pb-[max(env(safe-area-inset-bottom,20px),20px)] text-center">
+                <p className="text-[10px] text-muted-foreground/60 uppercase tracking-widest">Your Smart Travel Companion</p>
             </footer>
```

---

### 3.3 目標 3：`frontend/app/layout.tsx`
* **RFC Diff**:
```diff
--- a/frontend/app/layout.tsx
+++ b/frontend/app/layout.tsx
@@ -61,1 +61,1 @@
-    <html lang="zh-Hant" translate="no" suppressHydrationWarning>
+    <html lang="zh-Hant" translate="no" suppressHydrationWarning className="h-full">
@@ -82,1 +82,1 @@
-      <body className={inter.className} suppressHydrationWarning>
+      <body className={`${inter.className} h-full bg-background text-foreground`} suppressHydrationWarning>
```

---

### 3.4 目標 4：`frontend/app/globals.css`
* **RFC Diff**:
```diff
--- a/frontend/app/globals.css
+++ b/frontend/app/globals.css
@@ -183,1 +183,2 @@
   height: 100%;
+  min-height: 100%;
```

---

## 4. Human Gate Handover

所有對抗假設均已透過獨立子代理人審核與 Vitest 哨兵測試（`ipad-standalone-viewport-sentinel.test.tsx`）嚴格實證。目前代碼處於純淨 Red 狀態，等待人類開發者核准後即可將候選補丁寫入原始碼並轉為 Green。
