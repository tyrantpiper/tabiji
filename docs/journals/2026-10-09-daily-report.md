# 📅 Daily Report - 2026-10-09

> **系統狀態**：🟢 Production Hardened, Zero-FOUC Splash Deployed, Tabiji Brand Identity Deployed, Wabi-Sabi Paper Design System Active, 3-Act Aurora Paper Airplane Splash Operational, Fluid Responsive Bento Scaling Active across All Views (Itinerary, Info, Tools, Profile), Dual-Prefix Backward-Compatible Storage Engine (tabiji_ ⇄ tabidachi_) Verified, PWA Home Screen Streamlined to "Tabiji", 0 TypeScript Errors, 0 ESLint Warnings, 100% Tests Green (Frontend 51/51 Suites Passing, 371/371 Tests Passing; Backend 121/121 Passing), GitHub main branch synced (`7804a03`).  
> **今日關鍵提交串列 (Full Day Commit Stream)**：
> - [`7804a03`](https://github.com/tyrantpiper/tabiji/commit/7804a03) `feat(splash): eliminate pwa cold boot skeleton flash with #162832 dark base and coordinated unmount`
> - [`5d2b114`](https://github.com/tyrantpiper/tabiji/commit/5d2b114) `chore(deps): bump source-map-js (#20)`
> - [`9055df1`](https://github.com/tyrantpiper/tabiji/commit/9055df1) `feat(pwa): streamline home screen app name from Tabiji App to Tabiji`
> - [`f4255c0`](https://github.com/tyrantpiper/tabiji/commit/f4255c0) `feat(brand): complete tabiji rebranding with responsive bento grid, paper cards, and offline sync`

---

## 🏆 深度專案復盤：七大核心工程里程碑

本日聚焦於全端品牌識別蛻變（Brand Identity Rebirth）、和紙美學設計語彙建構（Wabi-Sabi Paper Design Tokens）、三幕式極光手繪紙飛機開屏動效（Three-Act Dynamic Gradient Splash Animation）、大螢幕流式自適應縮放（Fluid Responsive Bento Scaling）、雙前綴資料無損升級引擎、首頁登入視覺規格化重塑，以及冷啟動零閃爍夜幕防線（Zero-FOUC Splash），完成了全棧架構的跨越式升級：

---

### 里程碑一：Tabiji 品牌重塑與和紙 Wabi-Sabi 色彩系統建立
1. **問題背景與品牌蛻變**：
   - 專案自初創期以暫定案名 `Tabidachi` 運行，隨著產品邁入精緻熟成階段，正式確立以日文「旅路」為語意的全新官方品牌——**Tabiji**。
   - 舊有介面色彩偏向冷硬的灰階（slate/gray），缺乏日式旅人手作筆記與溫暖畫報的沉浸氛圍。
2. **Wabi-Sabi 自然色彩代幣架構 (Design Tokens)**：
   - **紙質畫布基底**：
     - 淺色模式：沉穩溫潤的米白和紙底色 `#F6F5EE`（配合紙張纖維感卡片 `#FFFFFF` 與微米框線 `#E5E2D9`）。
     - 深色模式：深邃夜幕墨黑石板色 `#121A18`（搭配暗夜青苔綠卡片 `#182220` 與炭黑飾邊 `#253330`）。
   - **品牌靈魂雙主色**：
     - 森林深綠（Tabiji Forest）：`#0B3026`（象徵日本古道與靜謐神社參道）。
     - 夕陽暮光暖橘（Tabiji Sunset Amber）：`#E56E25`（象徵旅途黃昏與暖心燈火）。
   - **全面統一元數據**：
     - 全站 HTML Title、Apple Web App Title、OpenGraph 社交卡片與 PWA Manifest 徹底切換為 **Tabiji**。

---

### 里程碑二：三幕式動態極光手繪紙飛機開屏動畫架構
1. **痛點剖析與效能瓶頸**：
   - 舊版開屏動畫為純靜態圖片，缺乏儀式感與開場張力；且若在 2048×2048 向量畫布上直接套用高斯模糊陰影（`drop-shadow-2xl`），會在低階手機造成嚴重的 GPU 掉幀（降至 20~30 FPS）。
2. **雙通道 GPU 硬體解耦與動態光場渲染 ([`tabiji-splash-animation.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/ui/splash/tabiji-splash-animation.tsx))**：
   - **三幕式動態日落極光層 (Three-Act Aurora)**：
     - Act 1 (0.0s~0.5s)：莫蘭迪深藍綠夜幕基底（Morandi Deep Teal Base `#162832` ➔ `#254A5A`）。
     - Act 2 (0.15s~1.2s)：暖橘夕陽墨水光球（Blooming Ink Orb `#E25248` ➔ `#D46238` ➔ `#9D9065`）平滑擴散放大 1.9 倍。
     - Act 3 (0.85s~2.0s)：終態黃金比例日落漸層淡入融合，完美還原黃金時刻天色。
   - **純手繪 Track Matte 區域水墨綻放 (Trailing Bloom)**：
     - 堅決剔除前景人造貝茲向量軌跡線，杜絕穿透五官臉頰的「幽靈線」瑕疵。
     - 透過階梯式水墨光斑（Zone 1 髮絲五官 ➔ Zone Hood 連帽兜帽 ➔ Zone 2 大衣連身 ➔ Zone 3 草寫字體）自然展開，95,588 像素 100% 保真還原原畫手繪線條。
   - **獨立 3D 紙飛機物理巡航 (Fly Element)**：
     - 右側手作紙飛機於字體末端揚起，以平滑貝茲曲線展開 `[scale: 1.0 -> 1.4, rotate: -5° -> -16°]` 俯衝昇華動畫，順暢銜接進入主儀表板。

---

### 里程碑三：全視圖流式自適應縮放 (Fluid Responsive Bento Scaling)
1. **痛點剖析**：
   - 舊版介面強行鎖死於窄版手機寬度（`max-w-md`），在 iPad、折疊機或桌面寬螢幕下，兩側呈現巨大無內容的黑邊空白，無法善用現代設備之大畫布優勢。
2. **多端自適應 Bento Grid 佈局架構**：
   - **主視圖自適應擴展**：
     - [`itinerary-view.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/views/itinerary-view.tsx)、[`info-view.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/views/info-view.tsx)、[`tools-view.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/views/tools-view.tsx)、[`profile-view.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/views/profile-view.tsx) 全面鬆綁為 `w-full max-w-4xl lg:max-w-5xl mx-auto`。
   - **響應式卡片陣列**：
     - 手機端維持易於單手滑動之縱向串流卡片；平版與桌面端自動展開為雙欄/三欄 Bento Grid 佈局（如 工具箱換匯、翻譯、備忘錄卡牌網格排版）。
   - **個人檔案 (Profile) 卡片完美對齊**：
     - 統一卡片邊距、圓角（`rounded-3xl`）、陰影層次與微標籤排版，消除不同模組間高度參差與縮放時文字跑版的視覺割裂感。

---

### 里程碑四：雙前綴無損儲存遷移引擎 (Dual-Prefix Zero-Loss Migration)
1. **痛點剖析與資料遺失風險**：
   - 品牌名變更可能牽動客戶端本機快取與資料庫儲存鍵。若直接將 IndexedDB 與 localStorage 中的前綴由 `tabidachi_` 改為 `tabiji_`，現有成千上萬使用者的離線行程、自訂設定與編輯草稿將在更新後全部「蒸發」，造成災難性資料丟失。
2. **無縫雙前綴自動升級協議 ([`idb-storage.ts`](file:///d:/Project/Tabidachi/travel-pwa/frontend/lib/idb-storage.ts))**：
   - **讀取階段雙向探測與透明升級**：
     - 優先讀取新前綴 `tabiji_trip_snapshot_{id}`。
     - 若未命中，自動回退探測舊前綴 `tabidachi_trip_snapshot_{id}`；若舊資料存在，在回傳資料的同時**自動於背景升級寫入新前綴並清除舊鍵**。
   - **三層儲存（L0 / L1 / L2）全鏈路相容**：
     - 同步涵蓋 L0 LocalStorage 同步鍵、L1 記憶體快取與 L2 IndexedDB 快照。
     - 撰寫專屬自動化回歸測試套件（[`instant-boot-storage.test.ts`](file:///d:/Project/Tabidachi/travel-pwa/frontend/__tests__/instant-boot-storage.test.ts)），實證老用戶升級零資料遺失。

---

### 里程碑五：PWA 桌面命名精簡 (Tabiji App -> Tabiji)
1. **PWA 桌面圖示名稱精簡**：
   - 根據使用者體驗回饋，手機主畫面若顯示「Tabiji App」帶有冗餘軟體尾綴，顯得不夠俐落；將 `manifest.json`（`name` / `short_name`）、`layout.tsx` 與安裝引導元件全面精簡為純粹的 **`Tabiji`**。
   - Service Worker 快取外殼重新構建，離線安裝體驗更加原生自然。

---

### 里程碑六：登入頁面品牌視覺重構與引繼碼安全防禦
1. **視覺層重塑 ([`landing-page.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/views/landing-page.tsx))**：
   - 將舊有通用 `<Compass>` 圖示替換為中央專屬 **白色線條回眸人物頭像**（`tabiji-person-icon.png`），外嵌原畫夕陽漸層圓角浮雕卡片。
   - 標題升級為原畫手寫草寫體「tabiji」與飛翔紙飛機透明遮罩（`tabiji-cursive-logo.png`），藉由 CSS `mask-image` 搭配 `bg-slate-900 dark:bg-white` 達成淺色墨黑與深色夜光白之高精度主題切換。
2. **安全防線與向下游 Schema 破壞防禦**：
   - 透過 `/security-sentinel` 審查，發現舊有引繼碼僅驗證長度，惡意字串會寫入 `localStorage.setItem("user_uuid")` 並破壞後續所有 UUID 端點。
   - 於 [`security.ts`](file:///d:/Project/Tabidachi/travel-pwa/frontend/lib/security.ts) 實裝 `isValidUUID` 正則驗證器，前端輸入送出前 100% 嚴格攔截非法輸入，並新增 [`landing-page-sentinel.test.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/__tests__/landing-page-sentinel.test.tsx) 進行防護驗證。

---

### 里程碑七：PWA 冷啟動白屏骨架屏全鏈路消滅 (Zero-FOUC Splash)
1. **痛點根因剖析 (Root Cause)**：
   - 使用者透過螢幕錄影（`ScreenRecording_10-09-2026 22-17-20_1.MP4`）回報：App 啟動至開屏動畫出現前，會閃現極短暫（50~150ms）的白色骨架屏。
   - 透過 `/Bug Hunter` 與沙盒審查實證兩大真因：
     1. `manifest.json` 與 `layout.tsx` 之 `background_color` / `themeColor` 設為淺白石色 `#fafaf9`。
     2. `pwa-hard-skeleton.tsx` 在 `DOMContentLoaded`（HTML 解析完成約 20ms）就提早添加 `hydrated` 類別並隱藏；但 React 水合尚未完成，導致底層未水合的 `AppShellSkeleton` 淺色骨架條暴露出螢幕；而 `splash-screen.tsx` 在首幀因為 `isStandalone=false` 渲染 `null`。
2. **四重防禦鏈路與生命週期協同實裝**：
   - **視窗與主題基底對齊**：`manifest.json` 與 `layout.tsx` 之 `background_color` / `themeColor` 統一為 `#162832`，iOS 狀態列對齊 `black-translucent`。
   - **媒體查詢首幀夜幕**：`pwa-hard-skeleton.tsx` 透過 `@media (display-mode: standalone)` 渲染 `#162832` 漸層並徹底隱藏 `.pwa-pulse-box` 脈衝方塊。
   - **生命週期協調卸除**：移除 `DOMContentLoaded` 盲目卸除，提供 `window.__dismissHardSkeleton` 鉤子，由 `SplashScreen` 在水合掛載開屏動畫時主動調用釋放。
   - **測試守門**：撰寫專屬驗證套件 [`zero-fouc-splash.test.ts`](file:///d:/Project/Tabidachi/travel-pwa/frontend/__tests__/zero-fouc-splash.test.ts)，6 項測試全數綠燈通過。

---

## 🏛️ 架構決策 (Architecture Decisions)

- **[AD-067] Tabiji 和紙自然美學色彩與設計代幣收斂 (Wabi-Sabi Paper Canvas Invariance)**:
  - 專案色彩基調摒棄冷硬科技感灰階，採用日式和紙天然質地米白色（`#F6F5EE`）作為淺色畫布，搭配森林深綠（`#0B3026`）與暮光琥珀橘（`#E56E25`）作為品牌識別雙軸心；深色模式採用青苔石板色（`#121A18`），保障高對比可讀性同時散發紙本溫度。
- **[AD-068] 離線快取雙前綴平滑遷移協議 (Dual-Prefix Backward Compatibility Protocol)**:
  - 本地儲存鍵變更時，嚴禁採取硬切斷式更名。底層儲存引擎必須實作「讀取優先新鍵 ➔ 回退讀取舊鍵 ➔ 背景寫入新鍵並釋放舊鍵」之自癒式原子升級迴路，保障現有離線資料 100% 零丟失。
- **[AD-069] 流式響應最大寬度自適應約束 (Fluid Adaptive Bento Invariance)**:
  - 視圖容器嚴禁硬編碼行動端固定寬度（如 `max-w-md`）。外層統一採用 `max-w-4xl lg:max-w-5xl mx-auto` 流式邊界，內部組件透過 Tailwind CSS Grid (`grid-cols-1 md:grid-cols-2 lg:grid-cols-3`) 在不同視窗尺寸下彈性展開，兼顧行動端單手操作與桌面端資訊密度。
- **[AD-070] 開屏動畫 Track Matte 水墨漸次顯現原則 (Track Matte Bloom Reveal Invariance)**:
  - 在高解析手繪開屏動效中，嚴禁在前景疊加生硬之人造貝茲向量軌跡線；主體顯現必須以原畫遮罩（Track Matte）結合多階水墨光斑（Trailing Bloom）展開，GPU 背景極光與前景手繪線條採 Stacking Context 物理隔離，穩鎖 60~120 FPS。
- **[AD-071] PWA 桌面圖示與主標題純淨命名法則 (Streamlined PWA Brand Identity)**:
  - PWA 應用程式名稱在 Manifest 與系統元數據中保持簡潔單一詞彙「Tabiji」，省略「App / 應用 / 行程」等修飾後綴，符合 iOS/Android 主畫面 App 名稱極簡化人體工學。
- **[AD-072] 品牌草寫體 CSS 遮罩雙模適配原則 (CSS Mask Image Theming Invariance)**:
  - 手繪品牌標題嚴禁採用多張不同顏色的點陣圖反覆切換。應提取單一高解析度透明通道遮罩圖（`tabiji-cursive-logo.png`），藉由 CSS `mask-image: url(...)` 配合 Tailwind 語意化背景色（`bg-slate-900 dark:bg-white`），達成 0 資源冗餘且與文字渲染引擎同級的完美主題對齊。
- **[AD-073] 冷啟動零閃爍夜幕與生命週期協調防線 (Zero-FOUC Splash & Lifecycle Coordinated Guard)**:
  - PWA 獨立視窗冷啟動時，嚴禁在 `DOMContentLoaded` 就提前卸除硬骨架屏（`body.classList.add('hydrated')`），否則在 React 水合前會露出未水合 SSR 骨架條；必須將 `manifest.json` 與 `viewport.themeColor` 統一鎖定為 `#162832`，硬骨架透過 `@media (display-mode: standalone)` 呈現 `#162832` 漸層並隱藏脈衝方塊，並由 React `SplashScreen` 在水合掛載時主動調用 `window.__dismissHardSkeleton` 無縫交棒，徹底消滅白屏與骨架閃爍。

---

## 🔴 技術債 (Technical Debt)

1. **多語系檔 `remaining.ts` 領域模組化拆分**:
   - `remaining.ts` 內仍承載超過 1,300 行翻譯代碼，後續排程依 Sprint 規劃拆分為 `landing.ts`、`itinerary.ts`、`profile.ts` 獨立模組。
2. **iOS Safari WebKit 離線快取透明度追蹤**:
   - iOS 18 針對 PWA 獨立模式有更嚴格的 7 天無活動清理政策，後續需評估於每次上線時主動觸發快取保活信標。

---

## 🛡️ 踩坑記錄與失敗路徑 (Failed Paths & Pitfalls)

1. **原畫漸層直接縮放疊加人物導致「重影」陷阱**:
   - 最初嘗試將帶有人物線條的原圖直接縮放作為背景並再次貼上白線人物，導致原圖縮小後的半透明線條在底層形成微小殘影。
   - **正確解法**：使用多級 Box 模糊降採樣（32×32）與 Bicubic 重建，完美消除所有細白線條，生成乾淨無雜質的純連續極光光場底圖（`tabiji-aurora-bg.png`），再精確合成高解析度居中人物。
2. **淺色模式下白線手寫字失真對比度陷阱**:
   - 原畫手寫「tabiji」字體為白色線條，若直接以 PNG 貼於淺色米白畫布上，對比度將降至不可讀。
   - **正確解法**：提取高解析透明遮罩圖（`tabiji-cursive-logo.png`），以 CSS `mask-image` 配合 `bg-slate-900 dark:bg-white` 達成原生主題自適應，淺色墨黑、深色夜光白，零邊緣鋸齒。
3. **硬骨架屏綁定 `DOMContentLoaded` 提早卸除引發水合空窗閃屏陷阱**:
   - `pwa-hard-skeleton.tsx` 在 `DOMContentLoaded` 立即加上 `hydrated` 類別，誤以為 HTML 解析結束等同於 React 水合完畢，結果在 20ms~100ms 之間將未水合的 `AppShellSkeleton` 淺色方塊直接暴露在畫面上。
   - **正確解法**：由 React `SplashScreen` 在水合且開屏準備就緒時主動調用 `window.__dismissHardSkeleton`，達成無縫平滑交棒。
4. **`SplashScreen` 依賴 `isStandalone` 客戶端狀態導致首幀 `null` 渲染盲區**:
   - `SplashScreen` 初始 `isStandalone` 為 `false`，首幀在 SSR 與客戶端均為 `null`，直到繪製後的 `useEffect` 觸發才非同步重繪掛載動畫，導致底層畫面曝光。
   - **正確解法**：前置透過 `manifest.json` 與靜態 `#pwa-hard-skeleton` 在第 0 毫秒就鎖死 `#162832` 漸層，消除首幀空窗。

---

## 🚀 下一步計畫 (Next Steps)

1. 進行生產環境真機 PWA 安裝驗收（iOS / Android 實機加入主畫面，確認點擊圖示瞬間至開屏動畫結束全程 0 白屏、0 骨架閃爍）。
2. 多語系檔 `remaining.ts` 模組化拆分排程實施。
3. 監控線上錯誤回報與 Service Worker 離線快取命中率。
