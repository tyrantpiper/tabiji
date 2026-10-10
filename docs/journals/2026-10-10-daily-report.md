# 📅 Daily Report - 2026-10-10

> **系統狀態**：🟢 Production Deployed, Tabiji Brand Sovereignty Established, PolyForm Noncommercial 1.0.0 Relicense Completed, Visual Assets Proprietary Under All Rights Reserved, Fullstack Rebranding Zero-Regression Passed, docs/security Domain Taxonomy Established (50+ History Artifacts Archived), 5-Tier Repository Topology Whitepaper Live, Stray Caches Purged, 0 TypeScript Errors, 0 ESLint Warnings, 100% Tests Green (Frontend 54/54 Suites Passing, 385/385 Tests Passing; Backend 121/121 Passing), GitHub main branch synced (`d83a838`).  
> **今日關鍵提交串列 (Full Day Commit Stream)**：
> - [`d83a838`](https://github.com/tyrantpiper/tabiji/commit/d83a838) `docs(infra): establish repository topology whitepaper, upgrade context conventions, and purge stray caches`
> - [`7192098`](https://github.com/tyrantpiper/tabiji/commit/7192098) `refactor(docs,security): restructure docs/security into domain taxonomy with history archives and README`
> - [`f4b778f`](https://github.com/tyrantpiper/tabiji/commit/f4b778f) `feat(branding,dx): rebrand to Tabiji and harden fullstack gitignore`
> - [`cf5a98e`](https://github.com/tyrantpiper/tabiji/commit/cf5a98e) `feat(legal): relicense to PolyForm Noncommercial 1.0.0 and establish split asset protection`
> - [`6a115ff`](https://github.com/tyrantpiper/tabiji/commit/6a115ff) `fix(auth,ui): resolve recovery false toast and floating map capsule viewport truncation`
> - [`7d6788e`](https://github.com/tyrantpiper/tabiji/commit/7d6788e) `feat(landing): upgrade brand icon to backpack traveler and dock pwa install sheet`

---

## 🏆 深度專案復盤：八大核心工程里程碑 (Eight Engineering Milestones)

本日完成自專案創立以來最具變革意義的全棧升級：從早晨的「揹包旅人」圖騰重塑與置底 PWA 抽屜，延伸至下午的「智財開源轉授權、全鏈路品牌純淨化、docs/security 領域拓撲重構，以及 14 大目錄白皮書與本機暫存治理」四大架構里程碑：

---

### 里程碑一：品牌圖騰「揹包旅人 (Backpack Traveler)」高解析原畫昇華與雙主題自適應遮罩
1. **問題背景與藝術重塑**：
   - 舊版人物立繪原為單純回眸披風剪影，缺少具象「整理行囊、踏上旅途」的符號感，且後背歷史痕跡曾殘留字標重疊。
   - 升級為全新原畫（`backpack.jpeg`）：揹著經典雙肩旅行後背包的回眸青年，具備掀蓋皮帶釦、前置口袋、側身立體隔層與自然肩帶弧度，完美詮釋 Tabiji（旅路）「智慧隨行、即刻出發」的品牌靈魂。
2. **影像拓撲淨化與遮罩管線 (Image Processing Pipeline)**：
   - 透過 Python PIL 直方圖分析，自暗色棋盤格背景（RGB 20~35）中徹底剝離背景（亮度 $\le 46$ 設為純透明，46~130 平滑抗鋸齒過渡），產出 1630 × 2546 高解析度純透明 RGBA 圖像於 `frontend/public/images/tabiji-person-outline.png`。
   - 物理裁切消除 Y: 0~50 處的螢幕截圖殘留字元，四個邊緣角落 100% 純透明零溢出（右上與右下邊角 0 活躍像素，Alpha 通道達 87.24% 純透明）。
3. **CSS 原生與 Tailwind 雙重防禦 (Defensive Dual-Layer Styling)**：
   - 長寬比適配為 `aspect-1630/2546`，並在行內樣式顯式宣告 `style={{ aspectRatio: '1630 / 2546' }}`，形成 Tailwind 類別 + 原生 CSSOM 雙層硬保險，杜絕任何 JIT 比例解析風險。
   - 遮罩路徑升級為 `?v=3`，強制穿透 Service Worker 與瀏覽器硬體快取。

---

### 里程碑二：登入頁「上圖下字」純粹識別架構與人體工學首屏黃金比例
1. **視覺層次解耦 (Visual Hierarchy Decoupling)**：
   - **Brand Icon (上方立繪)**：純粹藝術人物圖騰，高度限制在 `h-48 sm:h-56 md:h-60 max-h-[28vh]`。
   - **Wordmark (中央字標)**：專注品牌識別，優雅呈現原畫手寫草寫體 `tabiji` 字標與紙飛機。
   - **Subtitle (下方副標)**：多語系字典同步固化為「旅路 ｜ 旅行提案」(`zh`) / `Tabiji | Travel Planner` (`en`)。
2. **極限小螢幕 (iPhone SE 667px) 首屏防禦**：
   - 幾何量測計算證明：立繪高度上限 186.7px，圖騰 + 字標 + 表單總高約 390px，在 667px 螢幕下保留 $>200\text{px}$ 呼吸緩衝區，暱稱輸入框穩居首屏視覺與操作黃金點。

---

### 里程碑三：PWA 安裝導引固定置底抽屜 (Docked Bottom Sheet) 與軟體鍵盤避讓
1. **人體工學固定置底**：
   - 重構為貼底非強制抽屜（`bottom-0`），頂部配置 32px 圓角拖曳把手指示條（Drag Handle Indicator）。
   - **iOS Safe-Area 守護**：宣告 `pb-[max(0.75rem,env(safe-area-inset-bottom))]`，消除系統 Home Bar 誤觸。
2. **虛擬鍵盤動態避讓**：
   - 監聽 `visualViewport`，當可視高度縮減至 78% 以下時判定軟體鍵盤彈起，抽屜自動向下滑出隱藏，保證輸入暱稱時零遮蔽。
   - 登入進入 AppShell 後自動調整為 `bottom-20`，避免遮蔽常駐 `BottomNav`。

---

### 里程碑四：全鏈路對抗審查與雙哨兵回歸守門 (Sentinel Suites & Hardcore Audit)
1. **Security Sentinel 6-Phase 對抗審計**：
   - 針對新資產棋盤格漏光、CSS 比例解析回退、行動端鍵盤頂起遮擋等假設進行實體驗證。
   - 涵蓋率擴展至 56 個目標，產出完整審計報告與 candidate JSONs。
2. **雙哨兵自動化測試套件**：
   - `landing-brand-hierarchy-sentinel.test.tsx` (5 tests)：驗證多語系一致性、鍵盤動態偵測比率、Safe-Area 類別合成與首屏人體工學。
   - `splash-zero-strobe-sentinel.test.tsx` (3 tests)：守門開機動畫零頻閃、無白屏骨架屏退場。

---

### 里程碑五：品牌智財保護與開源轉授權 (PolyForm Noncommercial 1.0.0 ✕ All Rights Reserved 資產拆分)
1. **開源授權與商業邊界法律深潛**：
   - 深入調研證明：Creative Commons 官方明確反對將 CC BY-NC 4.0 用於軟體程式碼；AGPLv3 符合 OSI 開源定義第 6 條，允許任意商業運營（僅需揭露修改代碼），無法阻擋競爭對手商業營利。
   - 決策採納 **PolyForm Noncommercial License 1.0.0**：白紙黑字禁止商業使用，且法律關係黑白分明，訴訟成本最低。
2. **三向分案權益拆分架構**：
   - **原始碼授權**: `LICENSE` 採用官方標準 canonical 原文，保留 SPDX `PolyForm-Noncommercial-1.0.0`，確保 GitHub Licensee 辨識 100% 精確。
   - **歷史版本邊界**: 建立 `NOTICE.md`，以 Git Tag `v1.0.0-mit-final` (Commit: `6a115ff`) 為界，此前版本永久保留 MIT License。
   - **視覺資產保護**: 建立 `frontend/public/LICENSE-ASSETS.md`，宣告「揹包旅人立繪、手繪草寫字標、開屏原畫、3D紙飛機、App Icon」全域專有版權（All Rights Reserved）。
   - **商標指引**: 建立 `TRADEMARK.md`，規範 Fork 衍生版本必須 100% 抽換並移除 Tabiji 原廠圖資。
3. **TIPO 階梯式商標佈局戰略 (Phased Brand Moat)**：
   - 確立文字「Tabiji 旅路」與圖樣「揹包旅人立繪/Icon」採獨立分案申請，避免因複合商標遭駁回。
   - 梯隊部署：Phase 1 即刻申請第 09 類軟體/App、42 類 SaaS/PWA 與 39 類旅行安排（零三年不使用廢止風險）；後續隨出貨憑證推進實體周邊與動態商標。

---

### 里程碑六：雙份 README 與使用者介面全鏈路品牌純淨化 (Tabidachi ➔ Tabiji 旅路 零降級遷移)
1. **文檔一致性**：
   - 根目錄 `README.md` 與 `frontend/README.md` 頂部主標題統一升級為 `<h1 align="center">Tabiji 旅路</h1>`，引言段落首字同步更正。
2. **使用者可見介面文字純淨化**：
   - `UsageGuideContent.tsx`: 「Tabidachi 全功能操作手冊」→「Tabiji 全功能操作手冊」；離線說明文字同步更替。
   - `UsageGuideDialog.tsx`: 「了解如何使用 Tabidachi 的所有功能」→「Tabiji」。
   - `profile-view.tsx`: iOS 推播指引「往下滑找到「Tabidachi」或「Safari」」→「Tabiji」。
   - `onboarding.ts`: 新手導覽說明文案全面更新為 Tabiji。
3. **抗脆弱與雙向相容保證**：
   - 保留內部通訊事件名稱（`tabidachi-focus-map-activity`）與持久化快取前綴（`tabiji_` / `tabidachi_` 雙向回退相容），老使用者離線資料零丟失。
   - `account_settings_flow.spec.ts`: 斷言升級為鏈式 `.or()` 容錯語法，確保 CI/CD 與本地測試零退化。

---

### 里程碑七：docs/security 領域拓撲分流重構與 50+ 歷史產物歸檔 (Domain Taxonomy & History Archival)
1. **根目錄雜訊淨化**：
   - 原 `docs/security/` 扁平堆疊 55 個檔案，將 24 個 `candidates_*.json`、29 個 `findings_*.json` 與 1 個 `patch_*.diff` 透過 `git mv` 領域分流歸檔至 `history/` 子目錄 (`candidates/`, `findings/`, `patches/`)。
   - 根層僅保留權威台帳 `security-coverage-ledger.json` 與歷次 Markdown 報告 `reports/` 原生路徑零破壞。
2. **治理文檔與鏈結修復**：
   - 新建 `docs/security/README.md`，定義台帳維護規範、Sentinel 執行 SOP 與目錄治理標準。
   - 修復歷史報告補丁死鏈，將 `security_sentinel_report_2026-10-07_touch_slop.md` 引用對齊新路徑。
   - 升級 `.gitignore` 雙星遞迴白名單 `!docs/security/**/*.json` 與 `!docs/security/history/**/*.diff`。

---

### 里程碑八：Tabiji 全棧 5 大領域工程目錄拓撲白皮書與本機暫存治理 (Repository Topology & Stray Cache Purge)
1. **5 大領域層次嚴格界定**：
   - 劃分「應用服務 (`frontend`, `backend`, `cloudflare`, `supabase`)」、「維運自動化 (`scripts`, `.github`)」、「架構規範 (`docs`)」、「Agent 大腦 (`.agents`, `.vscode`)」與「版本控制/暫存 (`.git`, `scratch`)」。
   - 核心應用目錄嚴格維持一級目錄拓撲，保障 Vercel (Root) 與 Cloud Run (Dockerfile.prod) 部署零配置破壞。
2. **本機孤立暫存物理清除**：
   - 透過 PowerShell 絕對路徑強制錨定，物理清除孤立無效目錄 `.agent/`、測試快取 `.pytest_cache/` 與根目錄遺留之 `.vite` 快取 `node_modules/`（嚴格保護 `frontend/node_modules/`）。
   - 在 `.gitignore` 補強 `.agent/` 與 `.pytest_cache/` 全域阻斷。
3. **規範升級與矩陣登記**：
   - 產出全棧工程目錄拓撲白皮書 `docs/specs/infra/repository-topology-spec.md`。
   - 升級 `CONTEXT.md` 領域模型標題為 Tabiji 規範。
   - 於 `docs/specs/README.md` 登錄新規格書，達成規格體系 100% 閉環。

---

## 4. 多維度知識提煉 (Multi-Dimensional Synthesis)

### 🟢 Features & Fixes
- **Legal Relicensing**: 全面建立 PolyForm Noncommercial 1.0.0 與 All Rights Reserved 資產拆分架構。
- **Brand Pure-play**: README 雙份文件與 UI 使用手冊、離線說明、推播指引、新手導覽全面統一為 Tabiji。
- **Security Taxonomy**: `docs/security/` 50+ 歷史 JSON 歸檔至 `history/`，建立 `docs/security/README.md`。
- **Topology Whitepaper**: 產出 5 大領域工程拓撲白皮書 `repository-topology-spec.md`，升級 `CONTEXT.md`。
- **Stray Cache Purge**: 物理清除根層 `.agent/`、`.pytest_cache/` 與 `node_modules/`，補強 `.gitignore`。
- **Brand Icon Upgrade**: 部署 1630×2546 高解析度雙肩「揹包旅人」純線條遮罩立繪。
- **PWA Bottom Sheet**: 將安裝導引升級為固定置底抽屜，支援安全區、鍵盤避讓與雙態位移。

### 🏛️ Architecture Decisions
- **代碼與美術資產雙軌拆分**: 軟體原始碼受 PolyForm 保護，視覺圖資受 All Rights Reserved 保護，兼顧開源社群檢視與商業防禦。
- **版本回溯 Git Tag 錨定**: 透過 `v1.0.0-mit-final` 固化歷史邊界，未來版本全數納入防商用授權，徹底消除追溯性法律爭議。
- **核心應用目錄路徑不動原則**: 拒絕盲目物理合併為 `apps/`，維持 `frontend/`、`backend/` 一級結構，保護雲端部署流水線。
- **Git ignore 雙星遞迴白名單**: 採用 `!docs/security/**/*.json` 確保 `history/` 子目錄受到版本追蹤，同時由 `docs/security/findings_*.json` 防護運行時暫存污染。

### 🔴 Technical Debt
- **Dependabot 待處理**: GitHub 遠端回報 1 項高風險依賴安全性警告（Dependabot #105），待專責工作流評估升級。
- **Cloud Run 容器服務名稱更名評估**: 目前 README 與部署命令保留 `tabidachi-backend` 以與 GCP 既有服務對齊，後續可評估是否平滑過渡為 `tabiji-backend`。

### 🛡️ Failed Paths
- **直覺裁切誤判**: 初次測試裁切邊界時，誤將人物捲髮頂部當成截圖雜訊；經單行直方圖掃描證實捲髮自 Y: 57 展開，重新校準達成 100% 保真裁切。
- **`git mv` 批次執行中斷**: 針對包含未追蹤檔案的檔案群若直接執行萬用字元 `git mv`，會因未追蹤檔案觸發 `fatal: not under version control` 中斷；改為兩段式安全腳本（Tracked 執行 `git mv`，Untracked 執行 `Move-Item`）達成零中斷平滑遷移。
- **.gitignore 單星深度盲點**: `!docs/security/*.json` 無法跨越目錄斜槓，移入 `history/` 後一度被全域 `*.json` 忽略；升級為 `!docs/security/**/*.json` 徹底根治。

---

## 5. 品質閘門驗證清單 (Quality Gates Checklist)
- [x] **TypeScript**: `npx tsc --noEmit` (0 Errors)
- [x] **ESLint**: `npm run lint` (0 Errors, 0 Warnings)
- [x] **Vitest (Frontend)**: 54 Suites, 385 Tests Passed (100%)
- [x] **Pytest (Backend)**: 121 Tests Passed, 5 Skipped (100%)
- [x] **Security Sentinel**: 3 輪對抗沙盒審計全數 DISMISSED / SECURE (台帳 targets 擴增至 59 項)
- [x] **Chrome DevTools MCP**: 4 Viewport/Theme permutations verified via live screenshots

---

## 6. 下一步規劃 (Next Steps)
1. **Dependabot 漏洞評估**: 檢視 Dependabot #105 依賴警告並進行安全性升級。
2. **PWA 離線推播與背景同步實機演練**: 驗證 Service Worker 在深層飛行模式下的景點備份寫入。
3. **TIPO 商標申請文件初稿準備**: 依據八大類階梯式佈局整理第 09 類與 42 類商標樣張。
