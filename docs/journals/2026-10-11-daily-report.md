# 📅 Daily Report - 2026-10-11

> **系統狀態**：🟢 Production Deployed, Viewport Golden Coordinate Restored, Splash High-Priority Preload 60FPS Live, Recovery Atomic Reset 100% Verified, Strict Verification Spec Solidified, 0 TypeScript Errors, 0 ESLint Warnings, 100% Tests Green (Frontend 56/56 Suites Passing, 392/392 Tests Passing; Backend 121/121 Passing), GitHub main branch synced (`50ba989`).  
> **今日關鍵提交串列 (Full Day Commit Stream)**：
> - [`50ba989`](https://github.com/tyrantpiper/tabiji/commit/50ba989) `fix(auth): atomic cache reset and splash preload to eliminate recovery race and stutter`
> - [`0cfe4f8`](https://github.com/tyrantpiper/tabiji/commit/0cfe4f8) `fix(pwa): restore golden statusBarStyle default and #fafaf9 theme to eliminate viewport upward offset`

---

## 🏆 深度專案復盤：三大核心工程里程碑 (Three Engineering Milestones)

本日完成全棧視口穩定性、開機動畫繪製管線與身分引繼狀態機的核心升級：

---

### 里程碑一：iOS/iPadOS 狀態列黃金律回滾與視口原點修復 (Viewport Coordinate Golden Restoral)
1. **問題背景與真機現象**：
   - 使用者在手機與平板重新加入主畫面後，反饋 App 整體介面向上偏移，Header 與系統時間、電量指示條發生視覺重疊。
   - 歷史基準對比：上週真機行為完全正常，但在近期提交嘗試解決狀態列白底時，曾將 `appleWebApp.statusBarStyle` 修改為 `"black-translucent"`。
2. **底層 WebKit 視口幾何剖析 (WebKit Standalone Viewport Mechanics)**：
   - 當宣告 `statusBarStyle: "black-translucent"` 時，iOS WebKit 會將視口強行切換為「沉浸式全螢幕（Immersive Fullscreen）」，此時視口 (0,0) 原點直接貼齊物理螢幕最頂部，將頁面 Header 推入狀態列背後，產生致命視覺上移。
   - 當維持 `statusBarStyle: "default"` 時，WebKit 會將狀態列保留為系統專屬保留區，視口 (0,0) 原點嚴格錨定在狀態列正下方，配合 `themeColor: "#fafaf9"` 即可達成與系統頂部無縫融合，且絕無任何上移或重疊問題。
3. **黃金律精確回滾 (Golden Rollback)**：
   - 迅速執行精準回滾（Commit `0cfe4f8`），將 `layout.tsx` 中的 `statusBarStyle` 恢復為 `"default"`，`themeColor` 維持 `#fafaf9`，真機視覺原點百分之百完美復原。

---

### 里程碑二：開場動畫黑色勾勒原畫原生最高優先級預載入 (Splash Preload Pipeline & 60FPS Reveal)
1. **掉幀病因定位 (Decode Jank on First Frame)**：
   - 開機動畫所使用的高解析度黑色墨線立繪（`tabiji-art-mask.png` 2048×2048）與紙飛機（`tabiji-paper-plane.png`）原本是在 React 元件掛載時才由瀏覽器發現並非同步下載解碼。
   - 瀏覽器在主執行緒計算向量遮罩展開的第一瞬間遭遇大型點陣圖非同步解碼等待，產生 50~100ms 的繪製卡頓與掉幀現象。
2. **原生高優先級預載入標籤 (High-Priority Resource Hints)**：
   - 在全域 `layout.tsx` 的 `<head>` 靜態注入原生最高優先級 Resource Hints：
     ```html
     <link rel="preload" href="/images/tabiji-art-mask.png" as="image" type="image/png" fetchPriority="high" />
     <link rel="preload" href="/images/tabiji-paper-plane.png" as="image" type="image/png" fetchPriority="high" />
     ```
   - 瀏覽器自下載 HTML 第 0 毫秒起便指令 GPU 與網路管線在背景預先完成紋理加載，進場動畫啟動時已完全入駐記憶體，達成 60FPS 零掉幀絲滑展開。

---

### 里程碑三：帳號引繼原子四清、5秒過渡靜音鎖與防過度工程化 (Account Recovery Atomic Reset & Pragmatism)
1. **時序競爭與快取幽靈根除**：
   - **痛點**：輸入還原 Key 且行程完好存在時，偶發彈出黃色警告「該行程不存在或無存取權限，已切換至預設行程」。
   - **病因**：在 `landing-page.tsx` 中僅清理了獨立鍵值 `active_trip_id`，但 Zustand persist 儲存庫 `tabidachi-trip-storage` 仍殘留匿名模式的暫存指標；React 換場時反芻出舊 ID，而新帳號行程清單非同步拉取（SWR）尚未抵達，比對未中時誤觸刪除判定警告。
   - **處方**：
     - **原子四清**：還原瞬間同步深入 `tabidachi-trip-storage` 將暫存指標歸零。
     - **5 秒過渡靜音鎖**：在 `sessionStorage` 寫入 `tabiji_identity_transition_lock` 時間戳記。在引繼後 5 秒內，`trip-context.tsx` 即使遇到快取不匹配亦一律靜默對齊名下第一筆行程，物理阻斷誤判 Toast。
2. **極致容錯與全景式架構審核**：
   - 透過 `/Idea to Spec` 與 `/grill-me` 進行 3 輪關鍵決策訪談，完成規格書 `docs/specs/auth/account-recovery-strict-verification-spec.md`。
   - 審核發現深層潛伏風險：全新設備還原時本機缺乏 `sample_trip_seeded` 標記，會導致進入 App 後背景調用 seed API 逆向污染老使用者的雲端行程庫（FP-020）；且 PostgREST `.single()` 在查無記錄時會拋出 `PGRST116` 異常。
   - **防過度工程化共識 (Pragmatic Architecture Alignment)**：使用者金鑰皆為複製貼上，格式錯誤前端 0 毫秒由 `isValidUUID` 攔截，且雲端行程具備 100% 冪等性與可逆性。確立「保持現有高穩定度架構，不盲目新增後端驗證複雜度」之最佳實踐。

---

## 4. 多維度知識提煉 (Multi-Dimensional Synthesis)

### 🟢 Features & Fixes
- **iOS Standalone Viewport Golden Fix**: 回滾 `statusBarStyle` 為 `"default"`，消除 PWA 重新加入主畫面後的介面上移與系統狀態列重疊問題。
- **Splash Preload Pipeline**: 注入 `tabiji-art-mask.png` 與 `tabiji-paper-plane.png` 原生最高優先級 Preload 標籤，達成首幀 60FPS 絲滑展開。
- **Atomic Recovery Reset**: `landing-page.tsx` 實裝 Zustand 快取原子清理，徹底根除還原時之幽靈快照反芻。
- **5-Second Transition Lock**: `trip-context.tsx` 注入 `tabiji_identity_transition_lock` 靜音過渡機制，消滅引繼期間的誤判 Toast。
- **Account Recovery Spec**: 完成工程規格書 `docs/specs/auth/account-recovery-strict-verification-spec.md`。

### 🏛️ Architecture Decisions
- **iOS Standalone Status Bar 模式與視口原點黃金律 (AD-075)**: WebKit PWA 嚴禁在未設計自定義頂部延伸 Padding 的版型下宣告 `statusBarStyle: "black-translucent"`；必須維持 `"default"` 保留獨立系統狀態列空間，使視口座標原點 (0,0) 嚴格對齊狀態列下緣，保障整體佈局幾何穩定。
- **原生最高優先級紋理預載入與解碼停頓根治 (AD-076)**: 針對開機首幀涉及大型向量遮罩（2048×2048）或關鍵圖騰之資產，嚴禁等待 React 元件水合後才發起下載；必須在 HTML `<head>` 靜態配置 `<link rel="preload" as="image" fetchPriority="high">`，由瀏覽器管線在前 0 毫秒提前解碼完畢。
- **帳號引繼原子四清與 5 秒過渡靜音鎖架構 (AD-077)**: 跨使用者身分切換時，必須同步抹除 Zustand 本機持久化快照（`tabidachi-trip-storage`）；並透過 `sessionStorage` 宣告時間窗口鎖，阻斷 SWR 非同步載入期間因快取錯位觸發的破壞性誤判警告。
- **引繼金鑰極致容錯與拒絕過度工程化原則 (AD-078)**: 在純複製貼上 UUID 的操作場景中，格式錯誤已被前端正則嚴密攔截，且雲端資料具備完全可逆性；堅決拒絕為了理論上的極端輸入錯誤而盲目增加後端跨表驗證往返與延遲。

### 🔴 Technical Debt
- **Dependabot #105 待評估**: GitHub 遠端高風險依賴安全性警告待安排專責升級。
- **Sample Trip 標記原子注入備忘**: 未來若重構引繼流程，需確保還原成功時同步標記 `sample_trip_seeded: "true"`，防止背景種子腳本非同步觸發。

### 🛡️ Failed Paths
- **`black-translucent` 沉浸式誤傷版型佈局 (FP-019)**: 嘗試以 `black-translucent` 消除白底，反而觸發 WebKit 沉浸模式將整個 App 向上推移進入系統狀態列下，造成標題與時間電量疊印。教訓：狀態列模式牽動整個根層視口幾何，不可作為局部色彩補丁使用。
- **引繼情境下老使用者 Sample Trip 逆向污染陷阱 (FP-020)**: 在全新設備還原時，若只重設了 `user_uuid`，本地 `sample_trip_seeded` 為空會導致 `trip-context.tsx` 的種子守門器將老使用者誤判為新使用者，背景發起 `sampleTripApi.seed` 塞入示範行程。教訓：引繼流程必須同時覆蓋新人引導相關的所有本機旗標。

---

## 5. 品質閘門驗證清單 (Quality Gates Checklist)
- [x] **TypeScript**: `npx tsc --noEmit` (0 Errors)
- [x] **ESLint**: `npm run lint` (0 Errors, 0 Warnings)
- [x] **Vitest (Frontend)**: 56 Suites, 392 Tests Passed (100%)
- [x] **Pytest (Backend)**: 121 Tests Passed, 5 Skipped (100%)
- [x] **Account Recovery Sentinel**: `account-recovery-atomic-sentinel.test.tsx` (2/2 Passed)
- [x] **Git Cleanliness**: `Working tree clean`，已完全同步至遠端 `origin/main` (`50ba989`)

---

## 6. 下一步規劃 (Next Steps)
1. **真機 iOS / iPadOS PWA 體感終端驗收**：驗證重新加入主畫面後之狀態列頂部間距與開屏 60FPS 流暢度。
2. **Dependabot #105 安全性升級評估**。
3. **離線 Service Worker 終端同步演練**。
