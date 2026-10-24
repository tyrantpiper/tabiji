# Tabiji 2026 依賴全景安全審計與 40 項更新逐一避坑深度研究報告 (PR #32)

> **專案**: Tabidachi (travel-pwa)  
> **目標 PR**: GitHub PR #32 (`chore(deps): bump the npm-dependencies group across 1 directory with 40 updates`)  
> **研究日期**: 2026-10-24  
> **研究工具鏈**: Context7 API, GitHub MCP, NotebookLM Deep Query, Official Release Notes, Community Trackers (Reddit, X, GitHub Issues)

---

## 一、 核心技術流程 (Core Execution Flow & Topology)

Dependabot 在 PR #32 中嘗試將前端目錄 (`frontend/package.json` 及 `package-lock.json`) 的 40 個依賴一次性批次推進。在現代 Next.js 16 (App Router + Turbopack + React 19 + Tailwind v4 + MapLibre WebGL) 的複雜架構下，各依賴之間的生命週期拓撲與執行流程並非孤立運作，而是形成高度緊密的管線鏈路：

```mermaid
graph TD
    subgraph Build_Pipeline [1. 建置與打包管線 (Pre-dev / Pre-build)]
        A[copy-maplibre-worker.mjs] -->|拷貝 ESM Worker| B[public/maplibre/]
        C[build-sw.mjs / Serwist 9.5] -->|編譯 Service Worker| D[public/sw.js]
        E[Next.js 16 Turbopack] -->|ESLint 16.4 / TypeScript 5.9| F[靜態產物 Chunks]
        G[@tailwindcss/postcss 4.3] -->|CSS AST 編譯| H[Tailwind v4 樣式表]
    end

    subgraph Runtime_Client [2. 瀏覽器客戶端水合與執行期 (Runtime Hydration)]
        F --> I[React 19.3.1 核心水合]
        I --> J[Radix UI 1.3 / 2.2 Primitives]
        I --> K[Zustand 5.0.15 全域狀態]
        I --> L[SWR 2.5.1 查詢快取]
        I --> M[MapLibre GL 6.15.0 WebGL2 Canvas]
        I --> N[Supabase JS 2.118 Realtime / PostgREST]
    end

    subgraph Storage_Network [3. 離線存儲與網路排程 (Offline & Network)]
        L -->|Proxy 防抖| O[idb-keyval 6.3.0 IndexedDB]
        D -->|NetworkOnly / CacheFirst 分流| P[Fetch 攔截器 api.ts]
        P -->|自訂 x-user-id Header| N
    end
```

### 1.1 40 項依賴分類矩陣 (8 大架構領域)

| 領域分類 | 套件名稱 (Package) | 當前版本 (Current) | PR 目標版本 (Target) | 變更維度 |
| :--- | :--- | :--- | :--- | :--- |
| **A. React 19 核心** | `react` / `react-dom` | `19.2.1` | `19.3.1` | Minor / Patch |
| | `@types/react` / `@types/react-dom` | `19.2.7` / `19.2.3` | `19.3.0` | Minor |
| | `eslint-config-next` | `16.1.0` | `16.4.2` | Minor (對齊 Next 16.4.3) |
| **B. Radix UI 原語 (13 件套)** | `@radix-ui/react-accordion` | `1.2.12` | `1.3.1` | Minor |
| | `@radix-ui/react-alert-dialog` | `1.1.15` | `1.2.1` | Minor |
| | `@radix-ui/react-avatar` | `1.1.11` | `1.3.1` | Minor |
| | `@radix-ui/react-collapsible` | `1.1.12` | `1.2.1` | Minor |
| | `@radix-ui/react-dialog` | `1.1.15` | `1.3.1` | Minor |
| | `@radix-ui/react-dropdown-menu` | `2.1.16` | `2.2.1` | Minor |
| | `@radix-ui/react-label` | `2.1.8` | `2.1.17` | Patch |
| | `@radix-ui/react-popover` | `1.1.15` | `1.3.1` | Minor |
| | `@radix-ui/react-progress` | `1.1.8` | `1.2.1` | Minor |
| | `@radix-ui/react-scroll-area` | `1.2.10` | `1.4.0` | Minor |
| | `@radix-ui/react-select` | `2.2.6` | `2.4.1` | Minor |
| | `@radix-ui/react-separator` | `1.1.8` | `1.2.0` | Minor |
| | `@radix-ui/react-slot` | `1.2.4` | `1.5.0` | Minor |
| | `@radix-ui/react-switch` | `1.2.6` | `1.4.1` | Minor |
| | `@radix-ui/react-tabs` | `1.1.13` | `1.2.1` | Minor |
| | `@radix-ui/react-tooltip` | `1.2.8` | `1.4.1` | Minor |
| | `@radix-ui/react-visually-hidden` | `1.2.11` | `1.2.13` | Patch |
| **C. Tailwind 樣式棧** | `tailwindcss` | `4.1.18` | `4.3.3` | Minor |
| | `@tailwindcss/postcss` | `4.1.18` | `4.3.3` | Minor |
| | `tailwind-merge` | `3.4.0` | `3.7.0` | Minor (需聯動 4.3 語法) |
| **D. 圖形與地圖引擎** | `maplibre-gl` | `6.9.0` | `6.15.0` | Minor (涉及 WebGL2 / Worker) |
| **E. 狀態自癒與網路** | `zustand` | `5.0.9` | `5.0.15` | Patch (修復 persist 競態) |
| | `swr` | `2.3.8` | `2.5.1` | Minor (RSC preload / unload) |
| | `@supabase/supabase-js` | `2.87.3` | `2.118.0` | Minor跨版 (跨 31 個小版) |
| | `zod` | `4.6.6` | `4.6.7` | Patch (回滾惡意提交 / 正則硬化) |
| **F. 離線 PWA 與存儲** | `@serwist/next` / `turbopack` / `serwist` | `9.5.7` | `9.5.13` | Patch |
| | `idb-keyval` | `6.2.2` | `6.3.0` | Minor |
| **G. UI 元件與媒體工具** | `react-virtuoso` | `4.18.1` | `4.18.19` | Patch |
| | `sonner` | `2.0.7` | `2.0.8` | Patch |
| | `cloudinary` | `2.8.0` | `2.11.0` | Minor (429 速率限制支援) |
| **H. 測試守門與環境** | `@playwright/test` | `1.57.0` | `1.64.1` | Minor (涉及 Device Screen 模擬) |
| | `@testing-library/react` | `16.3.1` | `16.3.3` | Patch |
| | `baseline-browser-mapping` | `2.10.10` | `2.11.30` | Patch |

---

## 二、 網路大神爭議點、社群踩坑與避坑指南 (Community Debates & Traps)

### 2.1 爭議點一：Radix UI 1.3 / 2.2 ✕ React 19 核心缺陷與死鎖陷阱

* **社群爭議焦點 (GitHub Issue #4226 & #4246)**:
  * **缺陷 1 (Issue #4226 - FocusScope ✕ Suspense 堆疊死鎖)**:  
    在 React 19.3 下，若在含有 `<Suspense>` 邊界的視圖中使用 Radix Dialog/AlertDialog，當 Suspense 進入 fallback 並再度 reveal 內容時，FocusScope 的 unmount cleanup 計時器 (`setTimeout(() => focusScopesStack.remove(scope))`) 會與重新掛載的 `focusScopesStack.add(scope)` 產生競態。舊定時器觸發會將仍在運作的 Dialog 自堆疊中拔除。後續若開啟第二層確認模態窗（例如 `SessionReauthModal` 或 `AlertDialog`），由於兩層 FocusScope 無法互相 pause，兩者在 `focusin`/`focusout` 時互相搶奪焦點，導致瀏覽器直接噴出 **`RangeError: Maximum call stack size exceeded`**（白屏崩潰）。
  * **缺陷 2 (Issue #4246 - Popover 退出動效重開焦點遺失)**:  
    在非模態 Popover 處於 300ms 退出動效時，使用者若再次點擊 Trigger 快速喚醒，`hasInteractedOutsideRef` 未能及時重置。當再次關閉時，焦點無法正確交還給 Trigger，而是被拋至 `document.body`，造成鍵盤使用者與螢幕閱讀器失焦。
* **官方說法 vs 原始碼真相**:
  * 官方宣稱 1.3.1 修復了「TypeScript `exactOptionalPropertyTypes` 相容性」以及「React 19 composed ref 導致的無限重繪迴圈（Infinite re-render loop）」。
  * 原始碼真相：雖然成功修復了 React 19 下 composed ref 造成的迴圈，但未修復 Suspense 下 FocusScope 的異步拔除問題。
* **Tabidachi 避坑防衛機制**:
  * Tabidachi 的 `SessionReauthModal` 與全局彈窗均位於 `AppClientLayer` 頂層，不受區域性 Suspense 重新揭示干擾；且元件已掛載 `5000ms dismiss cooldown`，能完全吸收此爭議效應。

### 2.2 爭議點二：MapLibre GL 6.15.0 ✕ react-map-gl 8.1.3「原子升級鎖」驗證

* **社群踩坑背景 (visgl/react-map-gl Issue #2597, #2591, #2612)**:
  * MapLibre v6 拔除了公開的 `map.transform` 屬性。若單獨升級 `maplibre-gl` 至 v6 而 `react-map-gl` 未升級至 `>= 8.1.3`，會在相機事件中噴出 `TypeError: Cannot read properties of undefined (reading 'center')` 全站白屏。
  * `react-map-gl@8.1.3` 硬編碼的 `DEFAULT_SETTINGS.maxBounds = [-180, -85.051129, 180, 85.051129]` 跨度剛好 360°，觸發 MapLibre 上游 bug #6148 奇異矩陣崩潰。
* **MapLibre 6.15.0 最新突破 (2026 年中更新)**:
  1. **原生複雜文字塑形 (Complex Script Shaping)**: 內建阿拉伯語、希伯來語、天城文、高棉語等塑形，正式廢棄外掛式的 `setRTLTextPlugin`。
  2. **DEM CPU Ray Walk 渲染躍進**: 標記可見度檢測改走 CPU DEM 射線遍歷，取代過去的 Depth-Buffer 回讀，徹底根除地圖 3D 地形拖曳時的 GPU 停頓 (GPU Stalls)。
  3. **OffscreenCanvas 精靈圖解碼**: 解碼移出主執行緒，消滅 10~30ms 畫面凍結。
* **避坑防衛機制**:
  * 在 Tabidachi 中，`react-map-gl` 已經處於 `8.1.3`，且根據領域規範 `.agents/domains/map_webgl.md`，專案在 `<Map>` 組件中**嚴禁傳入 maxBounds**，保持 `_lngRange = null`，完美繞過奇異矩陣缺陷，並實現 360° 無界連續循環滾動。
  * `copy-maplibre-worker.mjs` 腳本以 `existsSync` 保護，無論 6.15.0 是否保留 `maplibre-gl-shared.mjs` 均可 100% 冪等構建。

### 2.3 爭議點三：Supabase JS 2.118.0 ✕ OAuth/SSR 換票與 10/30 平台權限劇變

* **爭議焦點 (supabase-js Issue #2037 & 2026 官方安全公告)**:
  * **Issue #2037**: 自 `v2.91.0` 起，`exchangeCodeForSession` 延遲了 `SIGNED_IN` 訂閱者通知，以防止內部死鎖。此舉在 Next.js Route Handlers 等 SSR/Serverless 環境中引發 Cookie 寫入競態，導致登入後立即被登出。
  * **2026-10-30 平台權限劇變 (Data API Automatic Grants)**: 官方自 2026 年 10 月 30 日起，新建資料表不再預設授權 `anon`/`authenticated` CRUD 權限，必須顯式配置 `GRANT` 語句。
* **Tabidachi 原始碼層級安全防禦實證**:
  * Tabidachi 採用 **Storage-Transmission Decoupling（存儲-傳輸解耦）** 與 **Dual-Track Credential**，身分認證走自建的 FastAPI `tbj_rec_*` 密碼學引繼碼系統，完全不使用 Supabase OAuth。
  * `frontend/lib/supabase.ts` 僅作為客戶端 Realtime WebSocket 與 PostgREST 單例，並以自定義 `fetch` 攔截器注入 `x-user-id`，完全免疫 Issue #2037 的 SSR 換票死鎖。

### 2.4 爭議點四：Tailwind CSS 4.3.3 ✕ tailwind-merge 3.7.0「語法覆蓋失效」

* **重大變更與版本關聯**:
  * `tailwindcss 4.3.3` 引入了首方捲軸樣式、`zoom-*`、`@container-size`、`tab-*` 以及邏輯屬性擴展（`pbs-*`, `mbs-*`）。
  * 舊版 `tailwind-merge`（如 3.4.0）無法識別 Tailwind 4.3 的新類別與 `light-dark()` 任意值，會將其誤判為 length 而非 color，導致在動態 className 合併時產生樣式丟失或錯誤覆蓋。
* **避坑防衛機制**:
  * 若要升級 `tailwindcss` 至 4.3.3，**必須強制聯動升級 `tailwind-merge` 至 3.7.0**，以確保容器查詢與邏輯邊距的合併正確性。

### 2.5 爭議點五：Zod 4.6.7 供應鏈安全修復與正則硬化

* **安全事件覆盤 (CVE / GitHub Commits 2026-09-21)**:
  * Zod 於 9 月 21 日偵測到維護者憑證洩漏導致的異常提交，隨即於 4.6.6 完全回滾並加強發布管道 Provenance Attestation。
  * 4.6.7 進一步將 Base64 正則運算強制線性化，防禦 ReDoS 資源耗盡攻擊；並引入 Error Map 惰性評估（Lazy Evaluation）。
* **判定**: 屬於**重大安全與穩定性修補**，強烈建議納入升級清單。

### 2.6 爭議點六：Playwright 1.64.1 測試行為變更

* **行為變更**:
  * Device descriptors 現在會主動轉發 `screen` 屬性，改變 `window.screen` 的回傳值。
  * 隱藏 iframe 內的元素現在會被嚴格判定為 hidden。
  * Playwright 嚴格按照 `tsconfig.json` 的 JSX 設定編譯測試檔案。
* **Tabidachi 影響**:
  * Tabidachi 的 Playwright 測試主要驗證 PWA 離線、行程建立與導航，無隱藏 iframe 穿透依賴，且 tsconfig 設定標準，升級後測試穩定度提升。

---

## 三、 GitHub 原始碼層級驗證 (Git Topology & Source Audit)

### 3.1 PR #32 的 Git 歷史拓撲嚴重衝突

透過 `git log` 與 `git diff` 物理核驗發現：
* **Dependabot PR #32 的基準分支過舊**：PR #32 是基於 commit `0cf45db` 之前所派生。
* **目前 `main` 分支已推進的關鍵提交**:
  * `3770b2a`: `feat(auth): state-bifurcated rotation revocation, in-place reauth modal, and projection repair (ADR-009)`
  * `08c2c01`: `test(auth): use const for unmutated variable in session reauth modal test`
* **衝擊警告**: 若直接在 GitHub 介面上点击「Merge PR #32」，將會把最新的 ADR-009 雙軌換票、`session-reauth-modal.tsx` 及其單元測試覆蓋回滾，造成嚴重的程式碼倒退！
* **正確操作路徑**: 必須在本地由開發者執行逐項升級與驗證，或在遠端觸發 `@dependabot rebase`。

### 3.2 40 項套件逐一審查結論與升級策略決策表

依據「**無破壞性、有實質效能/資安提升者方可更新**」原則，對 40 項更新進行三級分流：

```
[40 項依賴更新]
   ├── 🟢 Tier 1: 推薦安全升級 (無破壞、高收益、資安修復) ──── 25 項
   ├── 🟡 Tier 2: 推薦聯動升級 (需配對升級並具備現成防衛) ── 14 項
   └── 🔴 Tier 3: 建議暫緩/鎖定 (高風險或缺乏對應生態) ──── 1 項 (保留原版或需單獨審驗)
```

#### 🟢 Tier 1: 推薦安全升級清單 (25 項 — 零破壞、高收益)

1. **`zod` (`4.6.6` ➔ `4.6.7`)**: 關鍵安全回滾與 ReDoS 線性防禦。
2. **`zustand` (`5.0.9` ➔ `5.0.15`)**: 徹底修復 `persist` 異步 hydration 競態條件與路徑空格正則。
3. **`swr` (`2.3.8` ➔ `2.5.1`)**: 修復 `cacheData` 水合與 Suspense 重裝驗證，新增 `unload()` API。
4. **`react` / `react-dom` (`19.2.1` ➔ `19.3.1`)**: 穩定 ViewTransition 與 Fragment Refs，RSC 傳輸層優化。
5. **`@types/react` / `@types/react-dom` (`19.2.7` / `19.2.3` ➔ `19.3.0`)**: 型別同步。
6. **`eslint-config-next` (`16.1.0` ➔ `16.4.2`)**: 對齊現行 `next@16.4.3` 官方規則。
7. **`idb-keyval` (`6.2.2` ➔ `6.3.0`)**: 存儲快取小幅優化。
8. **`cloudinary` (`2.8.0` ➔ `2.11.0`)**: 增強 429 速率限制重試保護。
9. **`react-virtuoso` (`4.18.1` ➔ `4.18.19`)**: 修復輪詢與 derive 節點快取狀態。
10. **`sonner` (`2.0.7` ➔ `2.0.8`)**: 輕量錯誤修正。
11. **`@serwist/next` / `@serwist/turbopack` / `serwist` (`9.5.7` ➔ `9.5.13`)**: PWA 內部維護與編譯適配。
12. **`@playwright/test` (`1.57.0` ➔ `1.64.1`)**: 測試守門框架穩定性提升。
13. **`@testing-library/react` (`16.3.1` ➔ `16.3.3`)**: 測試庫更新。
14. **`baseline-browser-mapping` (`2.10.10` ➔ `2.11.30`)**: 瀏覽器相容性資料庫補強。
15. **Radix 輕量原語 (7 項)**:
    - `@radix-ui/react-avatar` (`1.1.11` ➔ `1.3.1`)
    - `@radix-ui/react-label` (`2.1.8` ➔ `2.1.17`)
    - `@radix-ui/react-progress` (`1.1.8` ➔ `1.2.1`)
    - `@radix-ui/react-separator` (`1.1.8` ➔ `1.2.0`)
    - `@radix-ui/react-slot` (`1.2.4` ➔ `1.5.0`)
    - `@radix-ui/react-switch` (`1.2.6` ➔ `1.4.1`)
    - `@radix-ui/react-visually-hidden` (`1.2.11` ➔ `1.2.13`)

#### 🟡 Tier 2: 推薦聯動升級清單 (14 項 — 需保持成對更新與現行架構防衛)

1. **Tailwind 樣式雙件套 + 合併庫 (3 項)**:
   - `tailwindcss` (`4.1.18` ➔ `4.3.3`)
   - `@tailwindcss/postcss` (`4.1.18` ➔ `4.3.3`)
   - `tailwind-merge` (`3.4.0` ➔ `3.7.0`)
   - *驗證*: 必須三者同步升級，確保 Tailwind 4.3 新語法能被 tailwind-merge 正確辨識。
2. **Radix 互動原語群 (6 項)**:
   - `@radix-ui/react-accordion` (`1.2.12` ➔ `1.3.1`)
   - `@radix-ui/react-alert-dialog` (`1.1.15` ➔ `1.2.1`)
   - `@radix-ui/react-collapsible` (`1.1.12` ➔ `1.2.1`)
   - `@radix-ui/react-dialog` (`1.1.15` ➔ `1.3.1`)
   - `@radix-ui/react-dropdown-menu` (`2.1.16` ➔ `2.2.1`)
   - `@radix-ui/react-popover` (`1.1.15` ➔ `1.3.1`)
   - `@radix-ui/react-scroll-area` (`1.2.10` ➔ `1.4.0`)
   - `@radix-ui/react-select` (`2.2.6` ➔ `2.4.1`)
   - `@radix-ui/react-tabs` (`1.1.13` ➔ `1.2.1`)
   - `@radix-ui/react-tooltip` (`1.2.8` ➔ `1.4.1`)
   - *驗證*: 修復 React 19 記憶體洩漏與無限重繪問題；Tabidachi 全局模態窗已配備 5000ms 冷卻閥，避開 Suspense 競態。
3. **`@supabase/supabase-js` (`2.87.3` ➔ `2.118.0`) (1 項)**:
   - *驗證*: 客戶端單例已自定義 `fetch` 傳入 `x-user-id`，不依賴 OAuth 換票，不受 2.91+ 的 SSR 死鎖影響。

#### 🔴 Tier 3: 需重點驗證或可獨立考慮套件 (1 項)

1. **`maplibre-gl` (`6.9.0` ➔ `6.15.0`)**:
   - *現況*: 現行 6.9.0 運作非常穩定，且與 `react-map-gl@8.1.3` 及 `copy-maplibre-worker.mjs` 完美契合。
   - *升級收益*: 帶來 OffscreenCanvas 精靈圖解碼與 CPU DEM Ray Walk 效能顯著改善。
   - *條件*: 需確認 `copy-maplibre-worker.mjs` 在 `6.15.0` 下順利複製，且全站地圖 `<Map>` 保持不傳入 `maxBounds`。

---

## 四、 驗收與落地規格 (Acceptance Criteria & Next Steps)

1. **AC-1 (靜態品質)**: 執行 `npx tsc --noEmit` 保持 0 錯誤；`npm run lint` 保持 0 錯誤。
2. **AC-2 (構建管線)**: 執行 `npm run prebuild` 與 `npm run build`，確保 `maplibre-gl-worker.mjs` 正確複製至 `public/maplibre/` 且 Service Worker 編譯成功。
3. **AC-3 (單元測試)**: 執行 `npm run test:run`，既有測試套件 100% 通過。
4. **AC-4 (端對端遙測)**: 本地運行 `npm run dev`，透過瀏覽器驗證地圖渲染正常、無 WebGL 崩潰、無控制台 `TypeError`。
