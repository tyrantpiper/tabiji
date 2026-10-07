# 📐 時間軸第二輪整合工程規格書 (Timeline Phase 2 Specification)
> **涵蓋範疇**: 區塊 3（左滑刪除與 5 秒 Undo）、區塊 4（交通銜接膠囊與 Mini 覆寫面板）、區塊 5（全面底抽式 Inset Grouped 編輯表單）  
> **狀態**: 已完成訪談並確立共識 (Spec Approved)  
> **日期**: 2026-10-07  

---

## 1. Problem Statement & Core Value (問題陳述與核心價值)

### 1.1 使用者痛點 (User Pain Points)
1. **刪除手感突兀與不可逆焦慮 (區塊 3)**:
   - 現有左滑手勢雖已露出紅色垃圾桶按鈕，但點擊後直接觸發瀏覽器原生 `window.confirm()` 彈窗，打斷操作節奏；且一旦確認即不可復原，缺乏現代 iOS/Android 的優雅容錯防護。
   - > 💡 *架構演進 (AD-055)*: 經由使用者驗證，卡片橫滑與垂直滾動存在手勢衝突，區塊 3 已於 [fullwidth-card-top-pill-spec.md](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/ui-motion/fullwidth-card-top-pill-spec.md) 正式演進為「右上角三點選單觸發 + 5 秒 Undo 延遲安全撤銷」。
2. **行程景點間缺乏連續性感知 (區塊 4)**:
   - 行程卡片之間只有一條垂直細線，使用者無法直觀得知從前一個景點（例如台北 101）移動到下一個景點（例如鼎泰豐）需要步行多久或搭乘什麼交通工具，亦無法一鍵開啟雙點起訖導航。
3. **編輯表單過於厚重且格式不統一 (區塊 5)**:
   - 現有的 `ActivityEditModal` 為傳統居中浮動 Dialog，在手機端與 PWA 模式下無法享有 iOS 原生 Bottom Sheet 的流暢上下滑動手感，且多項設定（POI 搜尋、地址解析、多圖上傳）缺乏清晰的 Inset Grouped 分組。

### 1.2 成功衡量指標 (Success Metrics)
- **手勢與容錯率**: 左滑刪除 0 秒延遲平滑折疊，5 秒內提供 100% 成功的無損「復原 (Undo)」按鈕。
- **導航效率提升**: 80% 以上具備座標的相鄰景點自動顯示距離與時間，點擊即可直達 Google Maps 雙點路線。
- **操作一致性**: 編輯表單全面底抽化，滾動流暢度達 60fps，關閉與開啟過渡時間 < 300ms。

---

## 2. User Journey & Core Flow (使用者旅程與操作流程)

```mermaid
flowchart TD
    subgraph S3["區塊 3: 左滑刪除與 Undo"]
        A[使用者在卡片上向左滑動] --> B[露出紅色垃圾桶按鈕]
        B --> C[點擊刪除按鈕]
        C --> D[卡片樂觀折疊移除<br/>畫面平滑過渡]
        D --> E[下方彈出 5 秒 Toast<br/>含『復原 (Undo)』按鈕]
        E -- 使用者在 5 秒內點擊復原 --> F[卡片無縫還原回原位<br/>取消遠端刪除請求]
        E -- 5 秒倒數結束 / 切換頁面 --> G[靜默觸發 itemsApi.delete 永久刪除]
    end

    subgraph S4["區塊 4: 交通銜接膠囊與 Mini 覆寫面板"]
        H[前後相鄰卡片均具備座標] --> I[渲染交通銜接膠囊<br/>如: 🚶 15 min · 1.2 km]
        I --> J{使用者點擊行為}
        J -- 點擊膠囊本體 --> K[展開 Mini Popover / 底抽小面板]
        K --> L[切換交通方式: 🚶 步行 / 🚇 大眾 / 🚗 開車]
        K --> M[手動覆寫預估時間 / 備註班次]
        K --> N[點擊『在地圖查看路線』]
        N --> O[開啟 Google Maps 雙點路徑規劃<br/>origin=A & destination=B]
    end

    subgraph S5["區塊 5: 全面底抽式 Inset Grouped 編輯表單"]
        P[點擊卡片選單『編輯全部』或新增行程] --> Q[90vh iOS Bottom Sheet 彈出]
        Q --> R[Group 1: 基本資訊<br/>時間、名稱、6大分類網格、私密]
        Q --> S[Group 2: 地點與導航<br/>國家地區、POI 搜尋、地址解析、座標]
        Q --> T[Group 3: 媒體與官網<br/>多圖滑軌、官網解析、費用、備忘]
        Q --> U[頂部滑動或導航欄儲存/關閉]
    end
```

---

## 3. Architecture & Data Model (架構與資料模型)

### 3.1 交通銜接模組 (`transit-connector.ts`)
```typescript
export interface TransitSegment {
    origin: { lat: number; lng: number; name?: string };
    destination: { lat: number; lng: number; name?: string };
    distanceKm: number;
    estimatedMinutes: number;
    recommendedMode: 'walking' | 'transit' | 'driving';
    googleMapsUrl: string;
}

// 演算法: Haversine 球面大圓幾何計算
// 閾值: < 1.5 km 預設 walking (時速 4.8 km/h); >= 1.5 km 預設 transit/driving (推估 25 km/h + 5 min 等候)
```

### 3.2 交通自訂資料擴充 (`Activity` 型別相容)
```typescript
export interface Activity {
    // ... 現有欄位 100% 保留
    transit_override?: {
        mode?: 'walking' | 'transit' | 'driving' | 'bicycling';
        duration_minutes?: number;
        custom_note?: string; // 例: "搭乘新幹線希望號 5 號車廂"
    };
}
```

### 3.3 刪除 Undo 狀態機 (`UndoQueueState`)
- **隊列結構**: `{ id: string; activity: Activity; day: number; timerId: NodeJS.Timeout }`
- **樂觀移除**: 立即從 React state 濾除，但延遲 5000ms 執行 `itemsApi.delete`。
- **復原觸發**: 清除計時器，將 `activity` 插回原陣列索引，播放 Haptic success 反饋。

---

## 4. Edge Cases & Boundary Conditions (邊界條件與異常處理)

1. **無座標或非實體景點**:
   - 若前/後卡片為 Header 或無經緯度座標，交通膠囊自動隱藏，維持純直線連接。
2. **超長距離跨城移動**:
   - 若相鄰景點距離超過 50km（如台北 ➔ 高雄），自動推薦高鐵/火車模式，時速依城際鐵路權重推估，並提供提示「城際移動」。
3. **Undo 期間的使用者跳轉**:
   - 若使用者在 5 秒倒數期間切換「Day 分頁」或點擊「返回主頁」，系統應立即 flush 執行永久刪除，防止 state 遺失造成幽靈資料。
4. **iOS 虛擬鍵盤彈起防破版**:
   - 在編輯表單聚焦文字輸入框時，底抽必須啟用 `visualViewport` 自動上推，多圖滑軌自動收折為緊湊膠囊高度（`h-18`）。

---

## 5. Acceptance Criteria (驗收標準清單)

- [ ] **AC-1 (左滑手勢)**: 在非 Header 卡片向左滑動能平滑露出紅色刪除按鈕，手勢結束若未達閾值自動彈回原位。
- [ ] **AC-2 (樂觀刪除與 Undo)**: 點擊刪除按鈕後不彈出原生 `confirm`，卡片立即折疊消失，並在畫面底部彈出 Sonner Toast 包含「復原」按鈕。
- [ ] **AC-3 (成功復原)**: 在 5 秒內點擊「復原」，卡片立即在原本位置重新顯現，且不向伺服器發送刪除請求。
- [ ] **AC-4 (永久刪除)**: 5 秒未點擊「復原」後，背景靜默呼叫 API 完成永久刪除。
- [ ] **AC-5 (交通膠囊自適應)**: 相鄰兩實體景點若均有座標，中間垂直線段處自動渲染膠囊，正確顯示步行或車程時間與距離。
- [ ] **AC-6 (雙點導航 URL)**: 點擊導航開啟之 Google Maps 連結，正確帶入前點座標為 `origin`、後點座標為 `destination`。
- [ ] **AC-7 (交通 Mini 覆寫面板)**: 點擊膠囊能呼叫 Mini 面板，允許自訂模式（步行/大眾/開車）及備註，並儲存至行程資料。
- [ ] **AC-8 (底抽編輯表單 Inset Grouped)**: `ActivityEditModal` 改為 90vh Bottom Sheet，內部採用分組區塊，所有原有的 POI 搜尋、地址解析、多圖上傳功能正常運作無遺漏。
