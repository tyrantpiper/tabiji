# Tabiji 重命名、商標衝突、GitHub 遷移與 PWA 快取工程深度研究報告 (2026)

## 摘要 (Executive Summary)
本研究針對專案自 `Tabidachi` (travel-pwa) 遷移至 `Tabiji` (tabijiapp.com) 之四大核心面向進行多維度調研與交叉驗證：
1. **商標與商用競爭風險**：發現 iOS App Store 已存在高度重疊之商用競品《Tabiji - Plan trips with ease》，構成極大之商標與上架衝突。
2. **GitHub 倉庫重命名與 CI/CD 遷移**：釐清 GitHub 轉址邊界條件、Vercel Git 斷連風險、Actions 依賴陷阱。
3. **PWA 重命名與圖示快取防禦**：解析 W3C Manifest `id` 身份綁定機制、Android WebAPK 24-48 小時延遲、iOS Web Clip 無法自動更新之物理限制。
4. **代碼庫內部相容性斷層**：指出 IndexedDB 快取前綴遷移可能導致的離線資料抹除風險。

---

## 一、商標與商用現況調查 (Trademark & Commercial Conflict Analysis)

### 1. 現存商業競品深度調研 (Market Landscape)
經全球應用商店與開源生態檢索，"Tabiji" (日文「旅路」，意為旅程/旅途) 已存在多個活躍的同名專案與商業產品：

| 實體 / 產品 | 平台 / 類別 | 開發者 / 公司 | 核心功能特徵 | 與本專案衝突程度 |
| :--- | :--- | :--- | :--- | :--- |
| **Tabiji - Plan trips with ease** | iOS App Store (商業上架) | Yu Itakura / Emanate (emanate.jp) | 行程管理、機票飯店整理、分帳匯率、**內建 AI 助手 Sora**、訂閱制收費 | 🔴 **極高 (100% 業務與功能撞車)** |
| **Tabiji - 旅路 \| 都道府県・国の記録** | Google Play Store | Masataka Kagiyama | 都道府縣與國家旅行足跡打卡、地圖紀錄、評分 | 🟡 **中度 (同屬旅遊類別但功能不同)** |
| **Kaiwa-Jun/tabiji** | GitHub (開源) | Kaiwa-Jun | 「旅行プランニングアプリ」(旅行規劃 Web App) | 🟡 **中度 (開源代碼庫同名)** |
| **Tabiji Trails** | 旅遊服務 (Web) | 商業旅行社 | 私人定製旅行路線與在地響導 | 🟢 **低度 (實體旅行社服務)** |
| **TABI-JI** | 零售 / 電商 (tabiji.co.jp) | TABI-JI Co. | 日本奈良傳統分趾鞋 (Tabi shoes) 知名品牌 | 🟢 **低度 (尼斯分類第 25 類鞋類)** |

### 2. 商標法理分析 (尼斯分類第 9、39、42 類)
- **第 9 類 (Class 009)**：可下載之行動應用程式、電腦軟體、AI 運算程式。
- **第 39 類 (Class 039)**：旅行安排、旅遊交通預訂、導航路線指引。
- **第 42 類 (Class 042)**：SaaS 雲端平台、地圖路網雲端託管、軟體即服務。
- **描述性詞彙抗辯 (Descriptiveness in Trademark Law)**：
  - 依據日本商標法第 3 條第 1 項第 3 款，純名詞「旅路 (Tabiji)」若純粹表示旅行路程，在審查實務上常被視為欠缺顯著性 (Lack of Distinctiveness)；但若作為應用程式品牌，並配合特定字型商標 (Logo/Stylized Mark) 或衍生詞，即可能被核准註冊。
- **在先商用權 (Prior Commercial Use) 與不正競爭法**：
  - 由於 Emanate / Yu Itakura 之《Tabiji》已在 iOS App Store 營運並提供訂閱服務，其在「AI 旅遊行程規劃軟體」領域已具備在先使用事實 (Common Law Trademark / 不正競爭防止法保護)。
  - 若直接使用純英文「Tabiji」並同在旅遊 AI 領域發布，將有極高機率觸發 **商標侵權警告信 (Cease & Desist)** 或面臨 **Apple App Store 爭議投訴導致下架**。
- **網域所有權迷思 (Domain Ownership vs Trademark Rights)**：
  - 買下 `tabijiapp.com` **完全不等同於** 取得「Tabiji」之商標權。
  - 在 ICANN 統一網域名稱爭議解決政策 (UDRP) 下，若品牌名稱與已具備知名度之商用標誌衝突且在相同領域提供競爭服務，網域甚至存在被主張惡意混淆之抗辯風險。

### 3. 命名防禦策略與架構建議
1. **方案 A (複合品牌定位 - 推薦)**：使用 `Tabiji App` 或 `Tabiji AI` 或 `Tabiji 旅路` 作為對外品牌名稱，避免單獨使用泛用詞 "Tabiji"。在 App Store 與 SEO 上可標記為「Tabiji - Generative Travel OS」。
2. **方案 B (雙軌並行架構)**：代碼底層、內部架構、GitHub 倉庫或微服務保留代號（或遷移至 `tabiji-app`），前端對外呈現註冊網域 `tabijiapp.com`，既解決撞名又保護現有工程穩定性。
3. **方案 C (維持原名或微調)**：`Tabidachi` (旅立ち，象徵出發/啟程) 具備較高的獨特性且無 App Store 直系競品衝突；`tabijiapp.com` 可作為簡短入口或官網轉址。

---

## 二、GitHub 倉庫重命名技術全流程 (GitHub Repo Renaming Execution Flow)

### 1. GitHub 官方轉址行為與邊際條件 (2025-2026 Docs)
當將 GitHub 倉庫從 `tyrantpiper/travel-pwa` 重命名為 `tyrantpiper/tabiji` 時：
- **自動轉址範圍**：
  - Web 網址 (`https://github.com/tyrantpiper/travel-pwa` ➔ `.../tabiji`)
  - Issues、PRs、Wiki、Stars、Watchers、Discussions
  - Git 操作：`git clone`, `git fetch`, `git push` 會透過 HTTP 301 / Git Smart HTTP 協議轉址。
- **三大破壞性陷阱 (Critical Edge Cases)**：
  1. **GitHub Actions 依賴中斷 (No Action Redirects)**：若該倉庫發布過 Reusable Action 且被其他工作流以 `uses: tyrantpiper/travel-pwa@...` 調用，GitHub **不會** 轉址，工作流將直接拋出 `repository not found` 崩潰。
  2. **名稱回收/重用陷阱 (Name Hijacking / Overwrite)**：若未來在此 GitHub 帳號下重新創建了名為 `travel-pwa` 的新倉庫，所有對舊倉庫的轉址將在該瞬間**物理失效**。
  3. **套件與容器註冊表 (Packages / GHCR.io)**：Docker/OCI 鏡像若以 `ghcr.io/tyrantpiper/travel-pwa` 命名，不會隨倉庫改名自動同步 Tag，舊鏡像拉取可能受阻。

### 2. CI/CD 與第三方雲端生態影響矩陣
| 整合服務 | 影響評估 | 處置SOP |
| :--- | :--- | :--- |
| **Vercel** | ⚠️ Webhook 可能脫鉤 | 雖然 Vercel 使用不可變 Project ID，但 GitHub 倉庫改名後常導致自動 PR/Commit Webhook 失效。需至 Project Settings ➔ Git 重新驗證連線。 |
| **GitHub Actions** | ⚠️ 環境變數變更 | `GITHUB_REPOSITORY` 系統變數將從 `tyrantpiper/travel-pwa` 變為 `tyrantpiper/tabiji`。工作流內若有硬編碼需檢查。 |
| **Cloud Run (GCP)** | 🟢 無直接衝擊 | 部署腳本使用的是 GCP SA Key 與 Cloud Run 服務名稱 (`antigravity-backend`)，與 GitHub 倉庫名無耦合。 |
| **Supabase** | 🟢 無衝擊 | 使用 Project Ref (`oudnkmigfueuyvxqpqwn`)，與 Git 倉庫名稱解耦。 |
| **Cloudflare Worker** | 🟡 命名規範相依 | 搜尋代理 Worker 目前為 `tabidachi-search-proxy`，可持續運行，但建議在後續階段同步更名。 |

### 3. 本地 Git 處置流程
```bash
# 1. 於 GitHub 網頁 Settings > General > Repository Name 修改為 tabiji
# 2. 本地終端機更新 Remote URL
git remote set-url origin https://github.com/tyrantpiper/tabiji.git
# 3. 驗證連線
git remote -v
git fetch origin
```

---

## 三、PWA 重命名、Icon 替換與快取工程 (PWA Rebranding & Cache Buster)

### 1. W3C Manifest `id` 機制與升級陷阱
- 依據 W3C Web App Manifest 規範，`id` 欄位是瀏覽器識別 PWA 身份的全球唯一錨點。
- 本專案目前 `frontend/public/manifest.json` 中宣告為：
  ```json
  {
    "id": "/",
    "name": "Tabidachi - 旅立ち",
    "short_name": "Tabidachi"
  }
  ```
- **核心設計決策**：
  - **嚴禁變更 `id`**！若將 `id` 改為 `"/tabiji"`，Android Chrome / Edge 等瀏覽器會判定其為「全新獨立 App」，現有安裝用戶不僅無法收到更名更新，還會在手機上產生兩個並存的孤島圖示。
  - **保持 `id: "/"`**，僅修改 `name: "Tabiji - 旅路"` 與 `short_name: "Tabiji"`，Android WebAPK 才能就地覆蓋升級。

### 2. 跨平台 PWA 更新物理週期 (Platform Divergence)
- **Android (WebAPK Pipeline)**：
  - Chrome 在每次 PWA 啟動與網路閒置時，會向伺服器比對 `manifest.json`。
  - 一旦檢測到 `name` 或 `icons` 變更，Chrome 將請求 Google WebAPK 伺服器重新打包簽名 APK。
  - 此過程具備 **24 至 48 小時延遲**，且必須在用戶**關閉所有背景實例**後才會在下一次啟動時無感套用。
- **iOS Safari (Web Clip Limitation)**：
  - **iOS Safari 不會自動更新已安裝在主畫面上的 Web Clip 圖示與名稱**。
  - 蘋果 iOS 系統在用戶點擊「加入主畫面 (Add to Home Screen)」時，將圖示與 `<meta name="apple-mobile-web-app-title">` 寫入 Springboard 靜態快照。
  - **避坑結論**：對於 iOS 已安裝用戶，純伺服器端更新無法改變其主畫面圖示；必須透過應用程式內部 Banner 提示用戶「應用程式已升級為 Tabiji，請刪除舊捷徑並重新加到主畫面」。

### 3. Serwist (Service Worker) 精準快取破壞架構
- 專案使用 `@serwist/turbopack` 透過 `frontend/scripts/build-sw.mjs` 自動編譯 `sw.js`。
- 其編譯邏輯採用 `globPatterns: ["public/**/*"]`，會對 `public/icon.png` 提取內容 Hash。
- **快取防護關鍵**：
  1. 替換 `frontend/public/icon.png` 後，必須觸發 `npm run predev` 或 `npm run build`，確保 `public/sw.js` 內的 `revision` hash 刷新。
  2. 瀏覽器端 `frontend/app/layout.tsx` 中的 `<link rel="apple-touch-icon">` 應加入版本查詢字串（如 `/icon.png?v=2`），以擊破 Safari 對 Apple Touch Icon 的侵略性 HTTP 快取。

---

## 四、代碼庫內部相容性審查 (Internal Codebase Audit)

經全域檢索，專案內部包含以下深度耦合項目，需採漸進式相容策略：

1. **IndexedDB 本地離線存儲前綴 (破壞性風險 🔴)**：
   - `frontend/lib/idb-storage.ts`: `tabidachi_trip_snapshot_`, `tabidachi_trips_list_`
   - `frontend/lib/idb-swr-provider.tsx`: `tabidachi_swr_persisted_cache`
   - **破壞性推導**：若立即將 Key Prefix 改為 `tabiji_`，現有使用者儲存在瀏覽器本機的全部行程草稿、離線快照將瞬間變成「不可見」（如同被清空）。
   - **避坑解法**：必須實作「相容讀取器 (Fallback Reader)」：讀取時先查 `tabiji_`，若為空則回退讀取 `tabidachi_`，並於寫入時進行平滑遷移。
2. **自定義 DOM 廣播事件**：
   - `tabidachi-deep-link`, `tabidachi-push-status-change`, `tabidachi-focus-map-activity`
   - 事件名稱僅限前端內部解耦通訊，可排定於第二階段批次安全重構。
3. **加解密混淆字串**：
   - `frontend/lib/security.ts`: `tabidachi:${data}:secure`
   - 包含正則檢查 `/^tabidachi:(.*):secure$/`，若直接修改將導致既有本地混淆資料無法解碼。

---

## 五、三方交叉驗證與邊際效應對照表 (Triangulation Matrix)

| 檢驗向度 | 官方文件承諾 | 技術大神/社群實測反饋 | 本專案代碼層級驗證結果 |
| :--- | :--- | :--- | :--- |
| **GitHub 轉址** | 所有 Git 操作與 Web 請求 100% 自動無感重定向 | 若重用舊倉庫名稱或 Actions 調用，轉址立刻失效且報 404 | 本倉庫無外部發布之 Reusable Action，但需防範未來誤建 `travel-pwa` 舊名倉庫。 |
| **Vercel 連線** | 自動偵測 GitHub 變更，不中斷服務 | 大量開發者回報改名後 Webhook 遺失，不再觸發 Preview Build | 需手動於 Vercel Dashboard 重新確認 Git Repository 連接。 |
| **PWA 圖示更新** | Manifest 修改後客戶端自動下載新圖示 | iOS 完全不更新主畫面；Android 需 24-48 小時；Serwist 舊快取若未清理會呈現舊圖 | 需利用 `build-sw.mjs` 自動重算 Revision Hash，並在 iOS 端依賴使用者重新加入主畫面。 |
| **商標與名稱** | 自由註冊網域與公開代碼庫 | 同名商業旅遊 App 已在 App Store 佔據位置，單一詞彙 "Tabiji" 具高度法律風險 | 建議以 "Tabiji App" 作為對外品牌名稱，對內保留工程代號或分層遷移。 |
