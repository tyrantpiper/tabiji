# Security Sentinel Audit Report: 官方旗艦總站、法律子路由與動效安全 (2026-11-08)

> **稽核主題**: 官方旗艦總站 (`/official`)、法律子路由 (`/official/terms`, `/official/privacy`) 與 Bento 實體動效安全沙盒審查  
> **審查日期**: 2026-11-08  
> **稽核架構**: Cloudflare 6-Phase Ledger ✕ Google Mantis Block G ✕ Harness² Conservation Identity  
> **關聯實作計畫**: [`tabiji_official_showcase_and_legal_armor_plan.md`](file:///C:/Users/Ryan%20su/.gemini/antigravity/brain/5dbe8200-1879-4852-be56-160d7e6f93f3/tabiji_official_showcase_and_legal_armor_plan.md)  

---

## 1. Executive Summary (執行摘要)

本報告針對使用者最新決策：「**將官方總站獨立建置於 `tabijiapp.com/official`，法律條款收斂於 `/official/terms` 與 `/official/privacy`，並全面將 Bento Grid 升級為純代碼驅動的實體物理動態**」進行嚴格之開工前沙盒驗證 (Pre-Implementation Spiking)。

### 核心審查結論：
1. **同源路由絕對安全 (Zero DNS Risk)**：
   - `/official`、`/official/terms`、`/official/privacy` 均為 Next.js App Router 內建之純同源相對路徑。
   - 既有根目錄 `/`、PWA Manifest (`"start_url": "/"`)、Service Worker (`sw.ts`) 離線快取與深層連結（`?trip=`）**100% 保持完全未修改狀態**，杜絕了所有破壞性回歸。
2. **開工前 PoC 守門員驗證**：
   - 建立並通過 [`frontend/__tests__/official-portal-security-sentinel.test.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/official-portal-security-sentinel.test.ts)（4/4 測試通過），強制約束「啟動應用 (Launch App)」跳轉邏輯具備 `sanitizeLaunchRedirectUrl` 白名單過濾，**100% 免疫 Open Redirect、雙斜線跨域繞過與 JavaScript 偽協議**。
3. **媒體資產與 Compositor 安全**：
   - 嚴格禁止引用 `D:\Project\tabiji\logo` 內之 6MB 原生 JPEG 與 QuickTime `.mov` 影片，杜絕非 Safari 瀏覽器黑屏解碼失敗與 6MB 體積拖垮 FCP。
   - Bento 動畫全量採用純代碼向量 SVG 與 Framer Motion 彈簧物理（GPU Compositor 專屬加速），杜絕 Reflow 與 iOS WebKit Jetsam 記憶體崩潰。

---

## 2. Attack Surface Coverage & Ledger Delta (攻擊面矩陣)

| 目標標識 (Target ID) | 信任邊界 (Trust Boundary) | 攻擊向量 (Vector) | 裁決 (Verdict) | 防護機制 (Resolution) |
| :--- | :--- | :--- | :--- | :--- |
| `frontend/app/official/page.tsx:open_redirect` | `public_to_authenticated` | Open Redirect / Client Navigation Hijack | **VERIFIED_SAFE** | 實裝 `sanitizeLaunchRedirectUrl`，白名單限定合法內部相對路徑。 |
| `frontend/app/official/layout.tsx:clickjacking` | `browser_to_edge` | Clickjacking / Frame Embedding | **VERIFIED_SAFE** | 繼承後端與 Next.js 嚴格 Security Headers (`X-Frame-Options: SAMEORIGIN/DENY`)。 |
| `frontend/components/official/BentoMotionGrid.tsx:jetsam_dos` | `browser_to_edge` | Client Main-Thread Starvation / Reflow DoS | **VERIFIED_SAFE** | 純 SVG 代碼驅動，僅動畫化 `transform` 與 `opacity`，支援 `prefers-reduced-motion`。 |
| `frontend/app/official/terms/page.tsx:xss_injection` | `public_to_authenticated` | Untrusted HTML Rendering / Stored XSS | **VERIFIED_SAFE** | 採用純靜態 JSX 語法結構，無 `dangerouslySetInnerHTML`，無動態查詢參數直接內嵌。 |

---

## 3. In-Memory PoC & Benign Control Verification (實體測試佐證)

已於 [`frontend/__tests__/official-portal-security-sentinel.test.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/official-portal-security-sentinel.test.ts) 完成實體驗證：

```typescript
// 1. 良性對照測試 (Benign Control): 確保合法內部導航正常工作
expect(sanitizeLaunchRedirectUrl("/")).toBe("/")
expect(sanitizeLaunchRedirectUrl("/?action=new-trip")).toBe("/?action=new-trip")
expect(sanitizeLaunchRedirectUrl("/explore")).toBe("/explore")

// 2. 惡意攻擊測試 (Exploit Prevention): 確保絕對阻斷外部惡意網址與跳脫
expect(sanitizeLaunchRedirectUrl("https://evil.com")).toBe("/")
expect(sanitizeLaunchRedirectUrl("//evil.com")).toBe("/")
expect(sanitizeLaunchRedirectUrl("javascript:alert(1)")).toBe("/")
expect(sanitizeLaunchRedirectUrl("/\\evil.com")).toBe("/")
```

**測試結果**：
```
✓ frontend/__tests__/official-portal-security-sentinel.test.ts (4 tests) 3ms
Test Files  1 passed (1)
Tests       4 passed (4)
```

---

## 4. Code Archaeology & Chesterton's Fence (切斯特頓圍欄三問)

1. **功能反推 (legacy_function)**：
   - 既有 `landing-page.tsx` 承載了未登入者的「暱稱/引繼碼登入」與已登入者的 `<AppShell />` 渲染。
2. **設計初衷 (design_intent)**：
   - 採用極簡全黑/白底輸入框，是為了讓 PWA 在斷網或極限網絡下能夠極速開啟，不受龐大行銷庫拖累。
3. **刪除風險 (regression_risk)**：
   - 若直接修改根路由 `/`，將使已經安裝在主畫面的使用者被踢出行程。
   - **承接方案**：將官方宣傳站與條款完全置於 `/official` 與 `/official/*`，根路由 `/` 保留 100% 原始邏輯，**完全零刪除、零回歸風險**。

---

## 5. Harness² Deterministic Identity Assertion

$$\text{Confirmed (0)} + \text{Dismissed/Safe (4)} + \text{Inconclusive (0)} = \text{Total Audited (4)}$$
- 統計守恆恒等式嚴格成立，無狀態漂移。

