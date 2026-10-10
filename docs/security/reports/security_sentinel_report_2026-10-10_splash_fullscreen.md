# Security Sentinel Adversarial Audit Report

- **Date**: 2026-10-10
- **Auditor Mode**: Security Sentinel (Dual-Channel Isolation via `runner.py` & `agy.exe -p --sandbox`)
- **Target Component**: iOS PWA Fullscreen Splash Overlap & Root Background Lifecycle Lock
- **Verdict Summary**: 3 Target Hypotheses Evaluated | 0 Confirmed Vulnerabilities | 3 Dismissed (Safe) | 1 In-Memory Sentinel Test Built (RED)

---

## 1. Executive Summary

本次審查針對用戶回報之「iOS PWA 開屏動畫頂部 56px 安全區呈現白色區塊（#F6F5EE）」之架構修復方案進行對抗審查。
核心風險評估聚焦於：
1. `frontend/app/layout.tsx` 中新增的 `<meta>` 標籤與 pre-hydration 背景同步腳本是否引發 XSS、Prototype Pollution 或 DOM Clobbering。
2. `frontend/components/ui/splash/tabiji-splash-animation.tsx` 在操作 `document.documentElement.classList` 時，是否可能因組件異常卸載造成根節點永久深色鎖定（UI Blindness）。
3. `frontend/app/globals.css` 中的 `!important` 樣式覆蓋是否會意外阻斷 Modal Dialog、Radix Portal 或 Toast 通知。

經過背景獨立 `agy.exe` 沙盒驗證子代理人（`runner.py`）之靜態對抗證偽與程式碼推理：
**3 項安全與穩定性假說均被判定為 `DISMISSED`（安全無虞）。修復方案設計具備高度防禦性與冪等性。**

---

## 2. Attack Surface Coverage Matrix

| Target ID | Trust Boundary | Vector Checked | Verdict | Sandbox Evidence |
| :--- | :--- | :--- | :--- | :--- |
| `frontend/app/layout.tsx` | `browser_to_edge` | `xss_and_injection` | **DISMISSED** | 腳本僅讀取固定鍵值，比對嚴格白名單，且僅賦值於 style/classList，不涉及 `eval` 或動態 HTML 拼接。 |
| `frontend/components/ui/splash/tabiji-splash-animation.tsx` | `browser_ui` | `dom_state_lock_and_leakage` | **DISMISSED** | 生命週期 cleanup 函式與 `onComplete` 採雙重重置（`classList.remove` 與 `style.backgroundColor = ""`），完全冪等。 |
| `frontend/app/globals.css` | `browser_ui` | `css_injection_and_ui_blocking` | **DISMISSED** | 樣式僅作用於 `html.splash-active` 與 `body` 背景色，不修改 `z-index` 或 `pointer-events`，不影響任何 Portal 與浮層。 |

---

## 3. In-Memory Sentinel Test (PoC Verification)

專屬驗收測試已建置於：`frontend/__tests__/ios-pwa-splash-fullscreen-sentinel.test.tsx`。
- **AC-1**: 驗證 `layout.tsx` 靜態輸出 `<meta name="apple-mobile-web-app-capable" content="yes" />`。
- **AC-2**: 驗證 `viewportFit: "cover"` 與 `statusBarStyle: "black-translucent"` 存在。
- **AC-3**: 驗證 pre-hydration 腳本包含開屏根層夜幕底色保護。
- **AC-4**: 驗證 `globals.css` 包含 `html.splash-active` 根層色彩鎖定。
- **AC-5**: 驗證 `tabiji-splash-animation.tsx` 正確納入生命週期雙向釋放。

**目前測試狀態**: **RED (4 failed, 1 passed)**，符合嚴格 TDD 先行準則。

---

## 4. Candidate Fixes & Exact Block Replacements (Human Gate Handover)

依據 L0 憲法，`@security` 僅產出候選補丁與區塊替換指南，嚴禁私自修改業務代碼：

### Patch 1: `frontend/app/layout.tsx`
#### Exact Target Content:
```tsx
      <head>
        <meta name="google" content="notranslate" />
        <meta name="agd-partner-manual-verification" />
        {/* 🚀 Zero-FOUC Font Scale Pre-Hydration Sync */}
```
#### Exact Replacement Content:
```tsx
      <head>
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="google" content="notranslate" />
        <meta name="agd-partner-manual-verification" />
        {/* 🚀 Zero-FOUC Splash Root Background Guard: 在開屏期間保持根層夜幕底色，杜絕 iOS 狀態列採樣白底 */}
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  var isStandalone = window.matchMedia('(display-mode: standalone)').matches || (window.navigator && window.navigator.standalone === true);
                  var hasShown = sessionStorage.getItem('tabiji_splash_shown') || sessionStorage.getItem('splash_shown');
                  if (isStandalone && !hasShown) {
                    document.documentElement.style.backgroundColor = '#162832';
                    document.documentElement.classList.add('splash-active');
                  }
                } catch (e) {}
              })();
            `
          }}
        />
        {/* 🚀 Zero-FOUC Font Scale Pre-Hydration Sync */}
```

---

### Patch 2: `frontend/app/globals.css`
#### Exact Target Content:
```css
  body {
    @apply bg-background text-foreground;
  }
```
#### Exact Replacement Content:
```css
  body {
    @apply bg-background text-foreground;
  }

  /* 🛡️ 開屏動畫期間根層色彩物理鎖定，杜絕 iOS 系統狀態列採樣 #F6F5EE 洩漏 */
  html.splash-active,
  html.splash-active body {
    background-color: #162832 !important;
  }
```

---

### Patch 3: `frontend/components/ui/splash/tabiji-splash-animation.tsx`
#### Exact Target Content:
```tsx
export function TabijiSplashAnimation({ onComplete }: TabijiSplashAnimationProps) {
    useEffect(() => {
        // 🛡️ 動畫 DOM 實體掛載就緒，安全平滑隱藏底層硬骨架
        if (typeof window !== "undefined" && typeof (window as unknown as { __dismissHardSkeleton?: () => void }).__dismissHardSkeleton === "function") {
            (window as unknown as { __dismissHardSkeleton: () => void }).__dismissHardSkeleton()
        }

        const timer = setTimeout(() => {
            onComplete?.()
        }, 2000)

        return () => clearTimeout(timer)
    }, [onComplete])
```
#### Exact Replacement Content:
```tsx
export function TabijiSplashAnimation({ onComplete }: TabijiSplashAnimationProps) {
    useEffect(() => {
        // 🛡️ 動畫 DOM 實體掛載就緒，安全平滑隱藏底層硬骨架
        if (typeof window !== "undefined" && typeof (window as unknown as { __dismissHardSkeleton?: () => void }).__dismissHardSkeleton === "function") {
            (window as unknown as { __dismissHardSkeleton: () => void }).__dismissHardSkeleton()
        }

        // 🛡️ 確保開屏播放期間根層物理鎖定為深色夜幕
        if (typeof document !== "undefined") {
            document.documentElement.classList.add("splash-active")
        }

        const timer = setTimeout(() => {
            // 動畫結束，平滑釋放根層背景給主畫面
            if (typeof document !== "undefined") {
                document.documentElement.classList.remove("splash-active")
                document.documentElement.style.backgroundColor = ""
            }
            onComplete?.()
        }, 2000)

        return () => {
            clearTimeout(timer)
            if (typeof document !== "undefined") {
                document.documentElement.classList.remove("splash-active")
                document.documentElement.style.backgroundColor = ""
            }
        }
    }, [onComplete])
```

---

## 5. Human Gate Handover Statement

所有沙盒驗證、對抗假說證偽、TDD RED 測試建置均已 100% 閉環完畢。
依據 L0 憲法規範，此階段凍結直接寫入，等待人類開發者（Ryan）核准後，方由開發者角色（`@dev`）精確套用區塊替換，並交由品質工程師（`@qa`）執行零錯誤靜態驗證！
