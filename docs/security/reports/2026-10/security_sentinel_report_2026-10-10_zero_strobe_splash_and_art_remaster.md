# 🛡️ Security Sentinel 深度安全與對抗審計報告

> **審計日期**: 2026-10-10  
> **審計模式**: `sentinel-agy-adversarial` ✕ In-Memory Sandbox PoC  
> **受審範圍**: 開屏零頻閃防線 (`splash-screen.tsx`, `tabiji-splash-animation.tsx`)、未水合骨架屏 (`landing-page.tsx:AppShellSkeleton`)、品牌人物純墨線立繪與草寫 Logo 重構 (`tabiji-cursive-logo.png`, `tabiji-person-outline.png`)

---

## 1. 執行總結 (Executive Summary)

| 指標 | 數值 | 說明 |
| :--- | :--- | :--- |
| **受審目標總數** | 3 項 | 開屏生命週期協同、未水合骨架白光頻閃、立繪小螢幕排版 |
| **已證實潛在缺陷 (Confirmed)** | 1 項 | `SplashScreen` 於 `useEffect` 同步調用 `__dismissHardSkeleton()` 導致 1~2 幀未水合空窗 |
| **證偽假設 (Dismissed)** | 1 項 | 人物立繪尺寸在合理視窗高度下不會造成輸入框破版 |
| **修復驗證狀態** | **100% SECURE** | 3 項單元測試全綠，全棧 52 套件 374 項測試 100% 通過 |

---

## 2. 對抗證偽與修復細節 (Adversarial Findings & Remediation)

### 2.1 [CONFIRMED] `frontend/components/ui/splash-screen.tsx:premature_dismissal_gap`
* **漏洞描述**：`SplashScreen` 在首幀 `isStandalone` 預設為 `false`，首次 render 返回 `null`。在 `useEffect` 中過早同步調用 `window.__dismissHardSkeleton()`，使 `#pwa-hard-skeleton` 在 `<TabijiSplashAnimation>` 真正被瀏覽器 Paint 到螢幕前提早 1~2 幀被強制設為 `display: none`，導致底層未水合 DOM 短暫裸露。
* **In-Memory PoC 驗證**：已於 `splash-zero-strobe-sentinel.test.tsx:SENTINEL-1` 捕捉到同步過早調用行為。
* **修復方案 (Mantis Patch)**：
  - `SplashScreen` 僅在 `hasShown || !standalone`（確定不播放動畫）時立即釋放硬骨架。
  - 當需要播放開屏動畫時，硬骨架銷毀延後至 `<TabijiSplashAnimation>` 的內部 `useEffect`（實體 DOM 掛載完成時）才安全調用，達成 0ms 無縫銜接。

### 2.2 [REMEDIATED] `frontend/components/views/landing-page.tsx:unmounted_skeleton_fouc`
* **漏洞描述**：`LandingPage` 在未水合階段（`!mounted`）渲染的 `<AppShellSkeleton />` 包含了高亮度白色 Header（`bg-white/50`）、灰色卡片（`bg-stone-200`）與白色導航，與深色背景 `#162832` 產生強烈頻閃。
* **修復方案 (Mantis Patch)**：
  - 將 `AppShellSkeleton` 改造為純粹的環境過渡底層：`<div className="min-h-screen bg-[#162832] dark:bg-[#162832] [@media(display-mode:standalone)]:bg-[#162832] flex flex-col" />`。
  - 完全保持 `TC-5` 契約，同時徹底消除所有刺眼白光元素。

### 2.3 [ENHANCED] 登入頁面品牌人物立繪與草寫 Logo 英文
* **草寫 Logo 清洗**：使用像素遮罩演算法剔除「t」字左側的大衣斷頭殘留雜線（Y: 0~11, 157~169, 305~314），修復平滑手寫筆鋒，並與右上角紙飛機完美融合。
* **人物立繪放大無框**：移除橘/藍水墨背景圓角方形卡片，改為雙主題自適應之純墨線立繪（淺色 `#0f172a`，深色 `#f8fafc`），高度放大至 `h-44 sm:h-52 md:h-56 max-h-[26vh]`，居中對稱，兼具大氣感與小螢幕防破版安全保護。

---

## 3. 全鏈路驗收門禁結果 (Verification Gates)

```
✓ TypeScript Typecheck (tsc --noEmit): 0 errors
✓ ESLint Analysis (eslint .): 0 errors, 0 warnings
✓ Vitest Full Suite: 52 test files passed, 374 tests passed (100% Green)
✓ Git Diff Regression: Zero unwanted logic regression
```
