# 📅 Daily Report - 2026-11-21 (登入頁雙語膠囊切換器、Web Storage 容錯安全網與 `@mcp:chrome` 全端驗收)

> **時間範圍**: `2026-11-21 00:42 ~ 02:10` (UTC+8)
> **當日納入 Commit**:
> - [`2f0d727`](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/landing-page.tsx): `feat(auth,i18n): add landing bilingual switcher and storage safety-net guards` — **`11 files changed, 2095 insertions(+), 54 deletions(-)`**（另有本篇日報與 `.agents/domains/*.md` 領域記憶結晶隨續接 `docs(journal,memory)` Commit 一併提交）。
> **全棧 Quality Gate 實測結果**:
> - Root Hygiene & Teamwork Scratch Gates: `OFFENDERS=0`, `TRACKED_TEAMWORK=''`, `TEAMWORK_IGNORE_RC=0`
> - Neural Seam Invariant Harness (`scripts/neural_seam_harness.py`): **`10/10` Intact** (`0` Sequelae, `SEAM_RC=0`)
> - Frontend TypeScript (`npx tsc --noEmit`): **`0 errors`** (`TSC_RC=0`)
> - Frontend ESLint (`npm run lint`): **`0 errors, 0 warnings`** (`LINT_RC=0`)
> - Frontend Vitest (`npx vitest run`): **`119 files, 1127 passed | 4 skipped (1131)`**（`VITEST_RC=0`；本次相關 7 個檔案 **`53/53 passed, 0 skipped`**）
> - Frontend Production Build (`npx next build`): Next.js 16.4.5 Turbopack **`Compiled in 267ms`**, TypeScript `2.6s`, **`13/13` routes** (`BUILD_RC=0`)
> - Backend Pytest (`pytest`): **`726 passed, 5 skipped in 103.20s`** (`PYTEST_RC=0`)
> - Security Ledger (`scripts/validate_security_ledger.py`): **`413 targets` (`185 remediated, 53 verified/unresolved, 175 dismissed/safe`)** (`LEDGER_RC=0`)
> - Security Sentinel (`runner.py --mode fast` 5 切片平行驗證): **`5/5 DISMISSED`** (`0 confirmed, 0 inconclusive`, `RUNNER_RC=0`)

---

## 1. 工程與檔案異動清單（2026-11-21）

- **核心功能與容錯實作**:
  - [frontend/lib/LanguageContext.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/lib/LanguageContext.tsx) (`+50 / -23`): 匯出 `Language` 型別；新增 `isValidLanguage()` 執行期白名單並維持 `setLang` 空依賴 `useCallback` 穩定性；抽出 `persistLanguageStorage()` 將 `localStorage.setItem` 與 `document.cookie` 分離為雙獨立 `try/catch` 區塊，並補齊掛載讀取 `try/catch`；抽出共用 `translateTemplate()`（`Object.prototype.hasOwnProperty.call` 防原型鍵查詢＋`split/join` 防 `$&` 展開，同步支援 SSR fallback `params`）。
  - [frontend/components/auth/landing-language-switcher.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/auth/landing-language-switcher.tsx) (`+90` 新增): 純展示型雙段切換膠囊（`繁中 | EN`），具備 `isolate` + `z-0` 膠囊 + `relative z-10` 文字、`Boolean(useReducedMotion())` 降級、WCAG AA 明暗對比、`focus-visible:ring-offset-2`（對應白／深石板底色）、`min-h-11 min-w-11`（≥44px）、`touch-manipulation`、`select-none` 與三重 `disabled` 防護。
  - [frontend/components/views/landing-page.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/landing-page.tsx) (`+64 / -24`): 右上角掛載安全區定位膠囊（`safe-area + 0.75rem`）；移除衝突的 `py-8 sm:py-12`，改以跨斷點一致的 `pt-[calc(max(env(safe-area-inset-top,0px),0px)+4rem)] pb-24 sm:pb-12`；將掛載 `useEffect` 內 `sessionStorage.setItem("pending_deep_link")` 與 `localStorage.getItem` 包入 `try/catch` 防禦 `SecurityError`；新增受 `isLoggingInRef`/`isRecoveringRef` 保護的 `handleLanguageChange`；補齊 `ChunkErrorBoundary`、引繼碼 placeholder、還原流程 Toast（含 `Error('').message` 空字串兜底）與頁尾標語雙語化。
  - [frontend/lib/i18n/remaining.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/i18n/remaining.ts) (`+28 / -0`) 與 [frontend/lib/translations.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/translations.ts) (`+28 / -0`): 雙字典 `en`/`zh` 對稱補齊 14 組 `landing_*` 鍵，雙語 `landing_recovery_placeholder` 皆嚴格保留 `tbj_rec_xxxxxxxx_` 契約。
- **測試與資安工件**:
  - [frontend/__tests__/landing-language-switcher.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/landing-language-switcher.test.tsx) (`+514` 新增, `14 tests`): 覆蓋無障礙、減弱動態、`QuotaExceededError`／`SecurityError` 雙儲存隔離、`$ &`／原型鍵防護、`LandingPage` 掛載 `SecurityError` 降級、輸入保留切換、EN Toast／空錯誤訊息／`ChunkErrorBoundary` 與雙字典對稱守門。
  - [frontend/__tests__/landing-page-loading-lock.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/landing-page-loading-lock.test.tsx) (`+22 / -2`): 補齊登入／還原鎖定期間切換器禁用斷言，並同步還原成功 Toast 雙語斷言。
  - [security_sentinel_report_2026-11-21_landing_bilingual.md](file:///d:/Project/tabiji/travel-pwa/docs/security/reports/2026-11/security_sentinel_report_2026-11-21_landing_bilingual.md)、[candidates_landing_bilingual_2026-11-21.json](file:///d:/Project/tabiji/travel-pwa/docs/security/history/candidates/candidates_landing_bilingual_2026-11-21.json)、[patch_candidate_landing_bilingual_2026-11-21.diff](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_landing_bilingual_2026-11-21.diff)、[security-coverage-ledger.json](file:///d:/Project/tabiji/travel-pwa/docs/security/security-coverage-ledger.json)（`408 -> 413` targets）。

---

## 2. 本日實戰事件、架構決策與經驗沉澱

### 🟢 Features & Fixes
- **登入頁雙語入口與 100% 雙語閉環**：完成需求訪談（`/Idea to Spec` + `/grill-me`）後，針對先後兩輪隔離 Worktree 沙盒 Red→Green 發現之容錯／無障礙缺陷逐一加固，並於生產編譯伺服器（`npx next start -p 3010`）以 `@mcp:chrome` 完成桌面、iPhone SE (`375×667`)、極窄屏 (`320×568` @ `130%` fontScale)、橫屏 (`667×375`)、暗黑模式、`prefers-reduced-motion`、重整持久化與 `/official?lang=en ➔ /` 接力全流程實測，主登入頁 `/` **0 React Hydration 錯誤**、**0 版面重疊**（`overlap: false`）。

### 🏛️ Architecture Decisions
- **AD-235（登入頁浮動雙語膠囊安全區淨空與聚焦外環對比契約）**：右上角膠囊（`top: safe-area + 0.75rem`, `min-h-11` + `p-0.5 border`）底緣達 `safe-area + 3.875rem`，`<main>` 必須在所有斷點維持 `pt-[calc(max(env(safe-area-inset-top,0px),0px)+4rem)]`（不可在 `sm:` 降回 `py-12`）；實心選取態膠囊須以 `isolate` + `z-0` + `relative z-10` 防沉底，並強制宣告 `focus-visible:ring-offset-2`（配對明暗背景色）維持 WCAG 2.4.7/2.4.11 聚焦可視性。
- **AD-236（雙語 Context 雙獨立 Storage 容錯與安全插值模板契約）**：`persistLanguageStorage` 將 `localStorage` 與 `document.cookie` 拆為雙獨立 `try/catch`（避免配額滿載連帶阻斷 Cookie），`setLang` 實施執行期白名單且保留 `useCallback([], [])` 穩定性；`translateTemplate` 透過 `hasOwnProperty` 與 `split/join` 消滅原型鍵洩漏與 `$&` 樣板展開，且對 Provider 與 SSR fallback 共用同一邏輯。
- **AD-237（前端 Worktree 沙盒降級構建與雙層 i18n/Sentinel 切片守則）**：因 `adversarial_team.py` 僅支援 Python `pytest`，前端目標在沙盒 Worktree（`frontend/node_modules` NTFS Junction）改以 Vitest Red→Green PoC ＋ `npx next build --webpack` 驗證，回 Live 後補跑預設 Turbopack `next build` 與 `--start_line`/`--end_line` 切片之 `runner.py --mode fast`。

### 🔴 Technical Debt
- **DEBT-STORAGE-ROOT-01（Open — 本次範圍外觀察）**：在 Safari 極端完全封鎖 `Storage.prototype` 的情境下，根佈局 [app/layout.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/app/layout.tsx#L111) 上層掛載的 [trip-context.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/lib/trip-context.tsx#L49) 與 [ThemeContext.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/lib/ThemeContext.tsx#L79) 於掛載讀取 `localStorage.getItem` 時仍未包入 `try/catch`。本次範圍內之 `LanguageContext` 與 `LandingPage` 本身已完成對等 `SecurityError` 防護。
- **DEBT-OFFICIAL-HYDRATION-01（Open — 既有上游觀察）**：`@mcp:chrome` 實測既有 `/official?lang=en` 路由時，上游 [OfficialLanguageContext.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/lib/OfficialLanguageContext.tsx#L63-L65) 因 SSR/CSR 首幀同步讀取 `?lang=en` 仍存在既有 React Hydration `#418` 錯誤；`/` 與 `/?lang=en` 為 `0` Hydration 錯誤。
- **DEBT-IOS-NOTCH-DEVICE-01（Open — 實體裝置視覺覆核）**：桌面 Chrome `env(safe-area-inset-top)` 恆為 `0px`，實體 iPhone 動態島 WebClip 模式（~`59px`）之視覺間距尚待實體機或 iOS Simulator 確認。

### 🛡️ Failed Paths
- **FP-105（僅護 Context 漏護 LandingPage 掛載期 Web Storage 導致受限環境整頁崩潰陷阱）**：第一輪實作僅為 `LanguageContext.tsx` 加上 `localStorage` `try/catch` 並只以 `renderHook(() => useLanguage())` 驗證，卻忽略 [landing-page.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/landing-page.tsx#L175-L189) 掛載 `useEffect` 仍裸呼叫 `sessionStorage.setItem("pending_deep_link")` 與 `localStorage.getItem`，導致在 Safari 隱私瀏覽／受限 iframe 下直接拋出未捕獲 `SecurityError` 整頁崩潰。往後凡涉及 Web Storage 容錯防線，必須於所有入口元件對稱落地並直接掛載完整頁元件執行 Red→Green 驗證。

### 🎯 Next Steps
- 由人類審視 Source Control 變動與執行分組 Commit / Push 至遠端，並於實機 iPhone Safari / WebClip 模式順手目視確認動態島下膠囊頂距；後續可另排程替 `TripProvider` / `ThemeProvider` 補齊根層 `Storage` `SecurityError` 防護與處理 `/official?lang=en` Hydration `#418`。

---

## 🧬 Machine-Executable Invariant Rules

```json
[
  {
    "domain": "ios_ui",
    "type": "INVARIANT_RULE",
    "id": "INV-UI-LANDING-CAPSULE-SAFEAREA-01",
    "title": "登入頁頂端浮動雙語膠囊安全區淨空與實心選取態聚焦外環契約 (AD-235)",
    "content": "登入頁右上角 absolute 語系膠囊 (top: safe-area + 0.75rem, min-h-11 + p-0.5 border) 底緣達 safe-area + 3.875rem。<main> 必須在所有斷點維持 pt-[calc(max(env(safe-area-inset-top,0px),0px)+4rem)]（嚴禁在 sm: 降級為 sm:pt-12 或保留 py-8 sm:py-12 衝突樣式），確保 667x375 橫屏與 320x568 130% 字級下 zero overlap。膠囊內部須採 isolate + z-0 motion.span + relative z-10 文字、Boolean(useReducedMotion()) 正規化，且實心選取態按鈕必須宣告 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-slate-800 維持鍵盤聚焦可視對比。"
  },
  {
    "domain": "state_cache",
    "type": "INVARIANT_RULE",
    "id": "INV-STATE-LANG-STORAGE-TEMPLATE-01",
    "title": "雙語儲存雙獨立容錯、執行期白名單與安全模板插值契約 (AD-236)",
    "content": "LanguageContext.tsx 必須將 localStorage.setItem 與 document.cookie 分離為兩個獨立 try/catch 區塊（QuotaExceededError 不可阻斷 Cookie 同步），並於掛載讀取與 LandingPage 掛載 useEffect 全面包裹 try/catch；setLang 必須執行 isValidLanguage() 校驗同時保持 useCallback([], []) 穩定性。共用 translateTemplate() 必須以 Object.prototype.hasOwnProperty.call(dict, key) 阻擋原型鍵查詢，並以 split/join 替代動態 RegExp.replace 消除 $& 展開缺陷且支援 SSR fallback params。"
  },
  {
    "domain": "state_cache",
    "type": "FAILED_PATH",
    "id": "FP-105",
    "title": "僅護 Context 漏護 LandingPage 掛載期 Web Storage 導致受限環境整頁崩潰陷阱 (FP-105)",
    "content": "僅在 LanguageContext 補齊 localStorage try/catch 並只用 renderHook(() => useLanguage()) 測試會誤以為具備 Safari 隱私瀏覽／受限 iframe 防護；實測掛載 <LandingPage />（特別是 URL 含 ?trip= 時）會在掛載 useEffect 裸呼叫 sessionStorage.setItem / localStorage.getItem 處拋出未捕獲 DOMException('SecurityError') 導致整頁崩潰。Web Storage 防護必須於入口元件對稱落地並以整頁元件渲染驗證。"
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-DEVOPS-FRONTEND-WORKTREE-SENTINEL-01",
    "title": "前端 Worktree 沙盒建置降級與雙層 i18n/Sentinel 契約對齊守則 (AD-237)",
    "content": "Security Sentinel adversarial_team.py (--mode duel) 僅內建 pytest 而不支援 Vitest；前端變更於隔離 Git Worktree（frontend/node_modules NTFS Junction）須手動執行 Vitest Red->Green PoC + npx next build --webpack（Turbopack 不相容指向根目錄外之 NTFS Junction），套用 Live 後再補跑預設 Turbopack npx next build 與 --start_line/--end_line 切片之 runner.py --mode fast。同時須守衛 remaining.ts 與 legacy translations.ts 雙語對稱，並於 landing_recovery_placeholder 保留 tbj_rec_xxxxxxxx_ 相容現有正則測試。"
  }
]
```
