# 🛡️ Security Sentinel 沙盒對抗審查報告：登錄頁雙語切換與安全網加固 (2026-11-21)

> **稽核基準**: `2dec84e` (`main`)
> **稽核模式**: Pre-Execution Worktree Spiking (`.worktrees/review-sandbox`) ✕ Red→Green PoC ✕ Mantis Block G ✕ `runner.py --mode fast` (sliced) ✕ Playwright Chromium 實機遙測 ✕ Harness² Ledger 守恆
> **審查判定**: **`5 / 5` `DISMISSED` (Verified Safe Post-Patch)**（`0 confirmed`, `0 inconclusive`，單次 5 切片平行驗證全通過）
> **台帳守恆驗證**: `413` Targets (`53` verified/unresolved + `185` remediated + `175` dismissed/safe = `413`, `scripts/validate_security_ledger.py RC=0`)

---

## 1. 執行摘要與沙盒實證 (Executive Summary)

1. **沙盒 Red→Green PoC 驗證**：
   - **第一輪沙盒驗證（`LanguageContext` 與雙語切換核心）**：驗證 `localStorage.setItem` (`QuotaExceededError`) 與 `document.cookie` 雙軌獨立 `try/catch`、掛載 `SecurityError` 防護、`setLang` 執行期語系檢查、`translateTemplate` `$&`/原型鍵防護與安全區佈局。
   - **第二輪對抗審查與沙盒 Red→Green PoC（`.worktrees/review-sandbox`）**：
     * **Pre-Patch Red Check (`RED_RC=1`, `2 failed | 1 skipped`; Benign Control `BENIGN_RC=0`, `1 passed`)**：實證 `LandingPage` 掛載 `useEffect` 裸呼叫 `sessionStorage.setItem` / `localStorage.getItem` 在儲存受限環境會拋出未捕獲 `SecurityError`（導致頁面白屏／錯誤頁），且 `LandingLanguageSwitcher` 啟用態按鈕缺乏 `focus-visible:ring-offset-2` 導致深／淺色實心膠囊之鍵盤聚焦環與背景融為一體。
     * **Post-Patch Green Check (`POC_GREEN_RC=0`, `3/3 passed`)**：補上 `try/catch` 掛載防護與 `focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-slate-800` 後全數轉綠並併入永久測試套件。
2. **沙盒全棧門禁 (`.worktrees/review-sandbox`)**：
   - `npx tsc --noEmit`: **`0 errors`** (`RC=0`)
   - `npm run lint`: **`0 errors, 0 warnings`** (`RC=0`)
   - `npx vitest run`: **`119 files / 1127 passed, 4 skipped`** (`RC=0`)
   - `npx next build --webpack`: **`RC=0`** (13/13 路由編譯通過)
3. **Security Sentinel CLI (`runner.py --mode fast`)**：
   - 5 切片單輪平行驗證：**`5 / 5 DISMISSED`** (`0 confirmed`, `0 inconclusive`, `RC=0`)。

---

## 2. 切斯特頓圍欄三問考古與刪除審查 (Code Archaeology & Deletion Audit)

| 變更檔案與位置 | 刪除／替換內容 | 設計初衷 (`design_intent`) | 承接與回歸保護 (`regression_risk`) |
|---|---|---|---|
| `frontend/lib/LanguageContext.tsx` | 單一 `setLang` 裸呼叫與 `new RegExp(...).replace` | 簡化語系切換與 `{name}` 參數插值，並以 `useCallback(..., [])` 穩定 `LanguageUrlHandoffObserver` | 拆分為獨立 `localStorage` / `document.cookie` `try/catch`（保留空依賴 `useCallback` 穩定性）、新增 `isValidLanguage` 執行期守護，並以 `hasOwnProperty` + `split/join` 消除原型鍵與 `$&` 展開風險，同步補齊 SSR fallback `params` 支援。 |
| `frontend/components/auth/landing-language-switcher.tsx` | 新增純展示膠囊與聚焦外環補償 | 提供無狀態受控雙語膠囊並兼顧鍵盤導航辨識度 | 補齊 `focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-slate-800`，避免聚焦環與實心背景色重合。 |
| `frontend/components/views/landing-page.tsx` (`useEffect`) | 裸 `sessionStorage.setItem` / `localStorage.getItem` | 於掛載期暫存 `?trip=` 深層連結並自動恢復已登入工作階段 | 外層包覆 `try/catch`，於 `SecurityError`（Safari 隱私模式／沙盒 iframe）下安全降級為訪客登入態。 |
| `frontend/components/views/landing-page.tsx` (`ChunkErrorBoundary`) | 寫死繁中離線重試文案 | Dynamic `AppShell` 載入失敗時無條件顯示友善提示，不依賴外層 Provider 狀態 | 改為可選 `title` / `description` / `retryLabel` props 並保留原始繁中預設值，呼叫端傳入 `t(...)` 兼顧雙語化與獨立調用安全性。 |
| `frontend/components/views/landing-page.tsx` (`<main>`) | `py-8 sm:py-12` 與 `pb-24 sm:pb-12` 衝突樣式 | 在大小螢幕提供置中留白並避開手機底部 | 改為跨斷點一致的 `pt-[calc(max(env(safe-area-inset-top,0px),0px)+4rem)] pb-24 sm:pb-12`，確保 `<main>` 頂距永大於右上角膠囊底緣 (`safe-area + 3.875rem`) 而不重疊。 |
| `frontend/components/views/landing-page.tsx` (`handleRecover`) | 寫死英文 Toast 與未判空 `e.message` | 提供快速登入驗證回饋 | 全面改用 `landing_verifying_identity` / `landing_welcome_back` / `landing_recovered_offline` / `landing_verify_failed`，並補上 `e instanceof Error && e.message` 空字串兜底。 |
| `frontend/lib/i18n/remaining.ts` & `translations.ts` | 新增 14 組 `landing_*` 鍵 | 維持主表與遺留表雙語對稱與 `tbj_rec_xxxxxxxx_` 測試契約 | 雙檔案 `en`/`zh` 100% 對齊，`landing_recovery_placeholder` 雙語皆保留 `tbj_rec_xxxxxxxx_`。 |

---

## 3. Deliverables 索引

- **候選清單**: [`candidates_landing_bilingual_2026-11-21.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/candidates/candidates_landing_bilingual_2026-11-21.json)
- **Sentinel 結果**: [`findings_landing_bilingual_2026-11-21.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/findings/findings_landing_bilingual_2026-11-21.json)
- **統一補丁**: [`patch_candidate_landing_bilingual_2026-11-21.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_landing_bilingual_2026-11-21.diff)
- **覆蓋台帳**: [`security-coverage-ledger.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/security-coverage-ledger.json)
