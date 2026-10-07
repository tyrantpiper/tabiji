# 📱 2026 行動端觸控滾動與按鈕手勢消歧義架構研究 (Mobile Touch-Scroll vs Menu Trigger Disambiguation)

> **研究主題**: 解決手機端垂直滾動行程卡牌時，誤觸三點編輯按鈕 (`DropdownMenuTrigger`) 導致選單意外彈出中斷滑動之缺陷。  
> **目標架構**: 比照 iOS UIKit / SwiftUI 原生級 `delaysContentTouches` 與 Touch Slop 手勢競爭機制，在 Next.js 16 + React 19 + Radix UI 現代架構中實現絲滑滾動體驗。  
> **研究日期**: 2026-10-07  
> **狀態**: COMPLETED (已匯入 NotebookLM 進行獨立驗證)

---

## 一、 問題陳述與根本成因定位 (Root Cause Analysis)

### 1.1 使用者體驗痛點
在手機端（PWA / iOS WebKit / Android Chrome）瀏覽垂直排列的行程卡牌清單時，使用者的拇指習慣於卡片右側滑動。當手指正好按在卡片右上角的三點編輯按鈕群（`DropdownMenuTrigger`）並向下滑動滾動時：
1. **意外開打選單**：手指剛碰觸按鈕的瞬間，編輯行程的下拉選單（包含「編輯此活動」、「刪除」）突然彈出。
2. **滾動手勢被強制打斷**：選單打開後立即搶佔焦點與滾動鎖定，卡牌列表瞬間停滯，使用者體驗極度挫折。

### 1.2 根本機制剖析：Radix UI 為什麼在滑動時會誤觸？
翻閱 `@radix-ui/react-menu` 與 `@radix-ui/react-dropdown-menu` 的原始碼（以及核心原始碼 GitHub Issue #1912 / #2418）：

```tsx
// 摘錄自 @radix-ui/react-menu/src/Menu.tsx
const MenuTrigger = React.forwardRef<HTMLButtonElement, MenuTriggerProps>((props, forwardedRef) => {
  return (
    <Primitive.button
      type="button"
      onPointerDown={composeEventHandlers(props.onPointerDown, (event) => {
        // 🚨 致命缺陷所在：只要是左鍵或觸控按下，立即在此毫秒打開選單！
        if (event.button === 0 && event.ctrlKey === false) {
          context.onOpenToggle();
          // 如果原本是關閉狀態，還執行了 preventDefault()
          if (!context.open) event.preventDefault();
        }
      })}
    />
  );
});
```

在行動裝置瀏覽器上，使用者觸控螢幕並滑動的事件時間軸如下：
```text
1. [t = 0ms]   手指碰觸螢幕 (Touch Down)
               ├── 瀏覽器派發 pointerdown 事件 (button = 0, pointerType = 'touch')
               └── Radix UI 監聽 onPointerDown 立即呼叫 context.onOpenToggle()！
                   🚨【選單已在此瞬間被強制開啟！】
2. [t = 20ms]  瀏覽器派發 touchstart 事件
3. [t = 40ms]  手指位移 5px (使用者真正意圖：開始向下滑動)
               └── 瀏覽器本應識別為 Pan / Scroll 手勢，
                   但此時 Radix 已打開選單並接管 DismissableLayer，滾動直接遭劫持中斷！
```

---

## 二、 iOS Swift / UIKit 原生架構對照 (The iOS Native Benchmark)

### 2.1 UIKit `UIScrollView` 的手勢競爭判定
在 iOS 原生開發中，`UIScrollView` 是如何完美解決這個問題的？
UIKit 設計了兩組關鍵屬性：
1. **`delaysContentTouches = true`（預設開啟）**：
   - 當使用者的手指觸碰在 scrollView 內的子元件（例如 `UIButton`）時，`UIScrollView` **不會立即將事件派發給按鈕**。
   - 它會啟動一個長度約 **150ms** 的消歧義等待窗口（Touch Slop Window）。
   - **分支 A（判定為滑動）**：如果在 150ms 內，手指移動超過了系統閾值（通常為 8~10 points），`UIScrollView` 立即判定為 Pan Gesture（滾動手勢），滾動開始，子按鈕完全收不到點擊事件！
   - **分支 B（判定為點擊）**：如果 150ms 內手指沒有顯著移動且快速抬起（Touch Up），才判定為 Tap，派發按鈕的點擊動作。
2. **`canCancelContentTouches = true`（預設開啟）**：
   - 即使子按鈕已經進入追蹤狀態（Highlight），一旦手指移動距離突破滾動閾值，`UIScrollView` 有權隨時中途對按鈕發送 `touchesCancelled`，將控制權徹底搶回給滾動引擎。

---

## 三、 網路大神技術爭議與四大避坑指南 (Expert Controversies & Pitfalls)

### 避坑點 1：單純使用 `onPointerDown={(e) => e.preventDefault()}` 的副作用
- **爭議分析**：在社群中最常被提及的解法是把 `DropdownMenuTrigger` 的 `onPointerDown` 加上 `e.preventDefault()`。
- **踩坑紀錄**：在特定 Android 裝置或舊版 iOS WebKit 中，若在 `pointerdown` 直接呼叫 `preventDefault()`，瀏覽器會取消後續所有滑鼠合成事件，導致原生的 `click` 事件根本不會被派發，造成**按鈕在行動端徹底變成死按鈕（Dead Button，點擊完全無反應）**！

### 避坑點 2：單純依賴 CSS `touch-action: pan-y` 或 `touch-manipulation`
- **爭議分析**：部分開發者試圖在 Trigger 按鈕加上 `className="touch-manipulation touch-pan-y"` 來解決問題。
- **踩坑紀錄**：`touch-action` 僅是通知瀏覽器合成器（Compositor Thread）是否允許該區域平移或雙擊縮放，**它無法阻止 JavaScript 主執行緒派發 `pointerdown` 事件**！Radix 的 JS 監聽器依然會在第一時間觸發。

### 避坑點 3：使用 `onClick` 取代 `onPointerDown` 的無障礙退化風險
- **爭議分析**：若全面改用 `onClick` 觸發選單，會丟失桌面端用戶使用滑鼠右鍵點擊或觸控板即時呼叫的流暢感，且會干擾鍵盤焦點管理（Space / Enter）。
- **正確做法**：必須**區分輸入設備類型 (`pointerType`)**：
  - 滑鼠 / 觸控筆 (`pointerType === 'mouse' | 'pen'`)：保留 Radix 原生快速響應。
  - 手指觸控 (`pointerType === 'touch'`)：切換為 Touch-Slop 消歧義模式。

---

## 四、 GitHub 開源實作層級驗證 (GitHub Codebase Verification)

### 4.1 Radix UI Issue #1912 與 #2418 核心進展
- 在 `radix-ui/primitives` Issue #1912 中，社群累積了 40+ 點贊，核心討論集中在：Radix 團隊因優先考量鍵盤導航 (WAI-ARIA) 與跨平台統一性，拒絕在核心中強加預設的滾動延遲。
- 官方給出的指引是：需要客製觸控手勢的場景，由消費者在 Trigger 處進行事件轉發控制（Controlled `open` state 或自定義手勢過濾）。

### 4.2 Adobe React Aria (`useMenuTrigger`) 的借鏡
Adobe 的 React Aria 在 `usePress` 中內建了 **10px 的移動閾值（Touch Slop Threshold）** 與 **cancelOnScroll** 機制：
- 只要手指移動超過閾值，內部狀態機立即遷移為 `isPressed = false` 並忽略後續 trigger。

---

## 五、 Tabidachi 專案落地之最佳架構解法：Touch-Slop 守衛 (The Touch-Slop Guard Pattern)

為了在 Next.js 16 + React 19 + Radix UI 中達到 100% 媲美 iOS Swift 原生絲滑體驗，我們設計出 **`Touch-Slop Gesture Disambiguation Pattern`**：

### 5.1 核心架構演算法
1. **輸入設備識別**：
   - 當 `event.pointerType !== 'touch'` 時：直接放行，保持桌面端最高響應度。
2. **觸控按下階段 (`onTouchStart` / `onPointerDown`)**：
   - 阻止 Radix 在 `pointerdown` 立即呼叫 `context.onOpenToggle()`。
   - 記錄觸控起始座標 `(startX, startY)`。
   - 重設 `isScrollingRef.current = false`。
3. **觸控移動階段 (`onTouchMove`)**：
   - 若計算出的垂直位移 `|currentY - startY| > 8px` 或水平位移 `|currentX - startX| > 8px`：
   - 標記 `isScrollingRef.current = true`（判定為使用者正在滑動頁面）。
4. **觸控釋放階段 (`onClick` / `onTouchEnd`)**：
   - 若 `isScrollingRef.current === true`：**徹底忽略並阻斷選單開啟**，放行列表滾動！
   - 若 `isScrollingRef.current === false`：判定為精準點擊，安全開啟 DropdownMenu！

### 5.2 具體組件層面重構代碼模型
```tsx
const [menuOpen, setMenuOpen] = useState(false);
const touchStartPos = useRef<{ x: number; y: number } | null>(null);
const isScrollingRef = useRef(false);

const handlePointerDown = (e: React.PointerEvent) => {
  if (e.pointerType === 'touch') {
    // 阻止 Radix 內部 pointerdown 立即打開選單
    e.preventDefault();
    touchStartPos.current = { x: e.clientX, y: e.clientY };
    isScrollingRef.current = false;
  }
};

const handleTouchMove = (e: React.TouchEvent) => {
  if (!touchStartPos.current) return;
  const touch = e.touches[0];
  const deltaX = Math.abs(touch.clientX - touchStartPos.current.x);
  const deltaY = Math.abs(touch.clientY - touchStartPos.current.y);
  // 超過 8 像素即判定為 iOS 原生滾動手勢
  if (deltaX > 8 || deltaY > 8) {
    isScrollingRef.current = true;
  }
};

const handleTriggerClick = (e: React.MouseEvent) => {
  if (isScrollingRef.current) {
    // 手指滑動中：阻斷開打選單
    e.preventDefault();
    e.stopPropagation();
    return;
  }
  setMenuOpen((prev) => !prev);
};
```

### 5.3 複合層級下防禦性事件管線：無條件切斷冒泡 (Unconditional Stop Propagation)
在含有「外層卡片點擊聚焦地圖」與「內層三點選單」的複合結構中，經 NotebookLM 深度交叉推導發現一項重大隱蔽邊際效應：
- **潛在風險**：當使用者在三點按鈕上滑動時，雖然 Touch-Slop 守衛成功阻止了 Radix 選單展開，但行動端瀏覽器在手指抬起時仍可能派發 `click` 事件。
- **致命穿透**：若三點按鈕在 `isScrolling === true` 時僅做 `return` 而未調用 `e.stopPropagation()`，該 `click` 事件將向上冒泡至卡片容器的 `handleCardClick`，造成「選單雖未開，背景地圖卻意外跳轉」的次級缺陷！
- **黃金守則**：三點按鈕的 `onClick` 處理器中，**不論最終判定為「展開選單」還是「阻斷選單（滑動中）」，第一行均必須無條件執行 `e.stopPropagation()`**！

---

## 六、 結論與驗收標準 (Acceptance Criteria)

- **AC-1 (滑動零誤觸)**：在手機端手指按住三點按鈕向下滑動卡片列表時，選單 100% 不會彈出，滾動如原生 Swift 般平滑順暢。
- **AC-2 (背景地圖零穿透)**：在手機端手指按住三點按鈕向下滑動時，絕不冒泡觸發背後卡片的地圖聚焦跳轉事件。
- **AC-3 (輕點正常觸發)**：在手機端精準輕點（Tap）三點按鈕時，選單於手指抬起時瞬間展開。
- **AC-4 (桌面端與無障礙零退化)**：在電腦桌面端使用滑鼠點擊三點按鈕時，保持 Radix 原生秒開響應；鍵盤 Space/Enter 與螢幕閱讀器 VoiceOver 保持 100% 導航焦點。
