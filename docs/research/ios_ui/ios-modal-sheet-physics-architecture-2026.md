# iOS 原生質感模態抽屜 (Modal Sheet) 物理動力學與 Web/PWA 架構研究報告 (2025–2026)

> **研究主題**: Web / Next.js PWA 達成 iOS 原生級 Sheet 模態互動之物理參數、手勢生命週期與工程防坑矩陣  
> **研究目標**: 交叉驗證 Apple HIG 規範、網路技術大神 (Emil Kowalski / Rauno Freiberg) 動效哲學、GitHub 開源實作 (Vaul / Framer Motion / Radix) 與 iOS Safari / PWA 實機踩坑邊界。  
> **交付物**: NotebookLM 獨立研究知識庫素材包 (Knowledge Base Dossier)。

---

## 壹、核心技術流程 (Core Technical Execution Flow)

### 1.1 iOS 原生 Sheet 拓撲架構與視覺層級 (Visual Hierarchy)

在 iOS 16–18 原生系統中，`UISheetPresentationController` 確立了現代行動端彈窗的黃金標準：
1. **背景縮放 (Background Card Scale-Down / Inset)**：
   - 當 Sheet 自底部滑入時，底層的主頁面容器（Wrapper）以頂部或螢幕中心為原點縮放至約 `0.93 ~ 0.95` (`scale((window.innerWidth - 26) / window.innerWidth)`)。
   - 底層容器同時獲得圓角 (`border-radius: 12px ~ 16px`)，並由頂部下移 `calc(env(safe-area-inset-top) + 14px)`。
   - 遮罩層 (`Overlay`) 覆蓋 `rgba(0, 0, 0, 0.4 ~ 0.5)` 並搭配微弱高斯模糊 (`backdrop-blur: 4px ~ 8px`)。
2. **抽屜本體 (Sheet Container)**：
   - 頂部外緣圓角：`rounded-t-[20px] ~ rounded-t-[28px]`。
   - 頂部膠囊抓手 (Grabber Handle)：居中放置 `width: 36px ~ 48px`, `height: 4px ~ 5px`, 圓角 `rounded-full`，色彩為低對比灰色 (`bg-slate-300/80` / `dark:bg-slate-600/80`)，並具備微弱內陰影。
   - 液態玻璃邊緣高光：頂部邊框配置 `shadow-[inset_0_1px_0.5px_rgba(255,255,255,0.2)]`。
3. **安全區沉浸適配 (Safe Area Inset)**：
   - 底部必須墊高 `env(safe-area-inset-bottom)`，確保 Home Bar（橫條手勢區）不遮擋任何按鈕或操作文字。
   - 高度計算嚴格鎖定動態視口高度 `dvh`（如 `max-h-[85dvh]`），切斷傳統 `vh` 在 iOS Safari 網址列縮放時引發的跳動。

### 1.2 物理動力學曲線 (Spring Physics & Motion Parameters)

```
[使用者手勢 Touch Move] ──▶ 橡皮筋阻尼計算 (Rubber Band Resistance)
                                  │
[手指放開 Touch End]   ──▶ 速度 (Velocity) 與位移 (Offset) 雙重閾值判斷
                                  ├── 超過閾值 ──▶ 順勢飛出關閉 (Dismiss Spring)
                                  └── 未超閾值 ──▶ 彈簧回吸復位 (Snapback Spring)
```

1. **曲線配置之爭：Spring vs Cubic Bezier**：
   - **Apple 官方標準流體貝茲曲線**：`cubic-bezier(0.32, 0.72, 0, 1)`，標準持續時間 `0.5s`（500ms）。
   - **Framer Motion 物理彈簧配置**：
     ```typescript
     transition: {
       type: "spring",
       stiffness: 350,   // 剛性：提供清脆明快的起步反應
       damping: 28,      // 阻尼：迅速吸收多餘振盪，杜絕視覺晃動
       mass: 0.85        // 質量：略輕於 1.0，營造極致輕盈跟手感
     }
     ```
   - **Apple 簡化彈簧對齊模式**：`{ type: "spring", duration: 0.5, bounce: 0.15 }`。

2. **手勢關閉判定閾值 (Dismissal Gates)**：
   - **位移閾值 (Displacement Gate)**：當向下拉動距離超過抽屜總高度的 `25% ~ 30%`（或向下位移 `> 120px ~ 150px`）。
   - **速度閾值 (Velocity Gate)**：向下拖曳釋放速度 `velocity.y > 0.4 ~ 0.5 px/ms`（約 400px/s），即使位移僅 30px，仍判定為有意識的「甩動關閉 (Flick to dismiss)」。

---

## 貳、GitHub 原始碼層級驗證 (GitHub Open Source Implementation Audit)

### 2.1 Emil Kowalski `vaul` 核心常數與架構 (`src/constants.ts` & `src/use-scale-background.ts`)

透過 GitHub MCP 對 `emilkowalski/vaul`（commit `3e97aac`）的源碼級審查：

```typescript
// 1. 動畫與門檻常數 (src/constants.ts)
export const TRANSITIONS = {
  DURATION: 0.5,
  EASE: [0.32, 0.72, 0, 1], // 官方認證之 Apple 流體曲線
};
export const VELOCITY_THRESHOLD = 0.4;
export const CLOSE_THRESHOLD = 0.25;
export const WINDOW_TOP_OFFSET = 26;
export const BORDER_RADIUS = 8;

// 2. 背景卡片縮放演算法 (src/use-scale-background.ts)
function getScale() {
  return (window.innerWidth - WINDOW_TOP_OFFSET) / window.innerWidth;
}
// 運算結果：在 390px 寬度的 iPhone 15 上，Scale 為 (390 - 26) / 390 ≈ 0.9333
// 搭配位移：translate3d(0, calc(env(safe-area-inset-top) + 14px), 0)
```

### 2.2 GitHub 實證缺陷與尚未解決的開源暗坑

在 GitHub Issues 檢索中發現，直接引入 `vaul` 在特定行動端情境存在重大隱患：

| Issue 編號 | 現象描述 | 底層根本成因 (Root Cause) |
|:---|:---|:---|
| **Issue #505** | `Drawer is unusable on a standalone installed PWA` | 在 iOS PWA standalone 模式下，頁面在視窗中段開啟 Drawer 時，`body-scroll-lock` 強制重設 `window.scrollTo(0, 0)`，導致使用者點擊抽屜任何區域立即觸發誤判關閉。 |
| **Issue #455** | `iOS: Overflowing elements flash on drawer close` | 抽屜關閉動畫進行時，內部 overflow-y: auto 節點與外層硬體加速圖層產生閃爍 (Flickering)。 |
| **Issue #269** | `Add support for iOS PWA app bar` | PWA 全螢幕狀態下，若未配置 `black-translucent` 與動態 status-bar 色彩，頂部會出現突兀白條或背景穿透。 |

---

## 參、網路大神爭議點與避坑指南 (Expert Insights & Pitfalls)

### 3.1 爭議點一：CSS Transform 是否應用於 `document.body`？
- **爭議焦點**：Vaul 預設透過 DOM Manipulator 對 `[data-vaul-drawer-wrapper]` 實施 `scale(...)`。若開發者未正確包裹 wrapper，Vaul 會直接對 `body` 上樣式。
- **大神實證**：對 `document.body` 或整個視圖套用 `scale()` 會導致 WebKit 重新計算所有 `position: fixed` 子節點的包含區塊 (Containing Block)，導致全域懸浮元件（如 Bottom Navigation、Float Action Button）位置瞬間跳動甚至失真。
- **最佳實踐**：**拒絕全域強制 Scale**。對於單一業務彈窗（如此地備忘錄），應聚焦於「彈窗本體進場彈簧動效 (`y: 100% ➔ 0`)」與「毛玻璃遮罩柔和過渡 (`backdrop-blur + bg-black/40`)」，切斷對全站 DOM 架構的侵入性修改。

### 3.2 爭議點二：巢狀滾動 (Nested Scroll) 與手勢劫持 (Gesture Hijack)
- **踩坑現象**：備忘錄內容過長時，使用者在彈窗內向上滾動時無事，但在向下滑動閱讀上方筆記時，手指滑動常被外層 Drag 手勢提前攔截，導致使用者「想看上面的備忘文字，彈窗卻直接被滑掉關閉」。
- **避坑機制**：
  1. **手勢區隔離 (Grab-Handle Delegation)**：僅允許頂部 Grabber 區域（或頂部 Header）觸發 Drag 關閉手勢；內部內容區宣告 `touch-action: pan-y`，並由原生滾動接管。
  2. **滾動頂部感應 (ScrollTop Sensor)**：若要支援全屏下滑關閉，必須在 `onPointerDown` 時檢查內部滾動容器的 `scrollTop === 0`，只有當已經置頂時才解鎖 Drag 下拉阻尼。

### 3.3 爭議點三：iOS Safari 100vh 截斷陷阱與軟鍵盤防禦
- **踩坑現象**：在 iOS Safari 中使用 `100vh` 會將導航列與底部工具列空間算入，造成底部被截斷 60~80px（此即使用者回報的截斷真因之一）。
- **避坑機制**：
  1. 使用 CSS `dvh`（動態視口高度）取代 `vh`。
  2. 底部填充注入 `pb-[calc(1.5rem+env(safe-area-inset-bottom))]`。
  3. 輸入法彈出時，`visualViewport.height` 縮小，彈窗應自動以 `max-h-[85dvh]` 或 `flex flex-col` 彈性收縮，嚴禁寫死絕對像素高度。

---

## 肆、Tabidachi「此地備忘錄」iOS 升級工程落地方案

結合專案架構（Next.js 16 + React 19 + Framer Motion 12 + Tailwind CSS v4），推薦落地規格：

1. **容器型態 (Responsive Morphology)**：
   - **行動端 (Mobile)**：無縫升級為 iOS 原生質感 Bottom Sheet（底部抽屜）。
     - 頂部居中 iOS Grabber 膠囊 (`w-10 h-1 rounded-full bg-slate-300 dark:bg-slate-600`)。
     - 圓角：`rounded-t-[24px]`。
     - 動畫：Framer Motion Spring `{ type: "spring", damping: 28, stiffness: 350, mass: 0.85 }`。
     - 進出場位移：`initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }}`。
     - 手勢：支援 Grabber 下拉拖曳關閉 (`drag="y" dragConstraints={{ top: 0 }} dragElastic={{ top: 0, bottom: 0.2 }}`)。
   - **桌面端 (Desktop, `sm:`)**：優雅保持置中微卡片彈窗（Centered Modal）。
     - 動畫：微幅放大進入 (`initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}`)。
2. **滾動與高度守護**：
   - 外層結構採用 `flex flex-col max-h-[85dvh] sm:max-h-[80vh]`。
   - Header 與 Grabber 標記 `shrink-0`，永不被擠壓。
   - 內容區 `flex-1 min-h-0 overflow-y-auto overscroll-contain`，滾動順暢且不反彈擊穿主頁面。
   - 徹底移除底部 English 按鈕（Close / Google Maps），釋放寶貴縱向空間。
3. **觸控震動 (Haptic Feedback)**：
   - 抽屜開啟與關閉時調用 `haptic.selection()`，營造逼真的 iOS Taptic Engine 物理打擊感。
