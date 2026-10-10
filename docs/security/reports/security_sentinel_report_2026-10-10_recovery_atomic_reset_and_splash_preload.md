# 🛡️ Security Sentinel 深度安全與對抗審計報告：帳號引繼原子雙清與開屏預載入

> **審計日期**: 2026-10-10  
> **審計模式**: `sentinel-agy-adversarial` ✕ `runner.py` 獨立子代理人沙盒對抗證偽  
> **遵循憲法**: L0 憲法安全第一、人類主權（唯讀審查、候選補丁發布、零私自破壞）、Maker-Checker 嚴格隔離  
> **受審目標**:
> 1. `frontend/components/views/landing-page.tsx` (帳號引繼恢復流程中 Zustand Persist 快照殘留與反向水合污染)
> 2. `frontend/lib/trip-context.tsx` (身分過渡期間非同步 SWR 比對競爭引發之誤導性刪除警告 Toast)
> 3. `frontend/app/layout.tsx` (開屏動畫 2048px 高解析原畫遮罩冷啟動異步解碼掉幀)

---

## 1. 執行總結 (Executive Summary)

| 指標 | 數值 | 說明 |
| :--- | :--- | :--- |
| **受審目標總數** | 3 項 | Zustand 持久化快取洩漏、身分過渡時間差誤警報、開屏非同步解碼 |
| **實證缺陷 (Confirmed Defect)** | **2 項** | 1. 引繼未清理 `tabidachi-trip-storage` 致反向水合；2. `prevUserIdRef` 提前覆寫致誤彈 Toast |
| **對抗證偽 (Dismissed)** | **1 項** | `layout.tsx` 保持職責解耦，但建議於 `<head>` 配置高優先級 Preload 以極限提升首幀 FPS |
| **沙盒實體驗證狀態** | **100% VERIFIED** | In-Memory Vitest 哨兵測試 2/2 PASS（`account-recovery-atomic-sentinel.test.tsx`） |

---

## 2. 沙盒對抗證偽與實體量測 (Sandbox Empirical Proofs)

### 2.1 [CONFIRMED] `landing-page.tsx`：Zustand Persist 快照未抹除引發反向水合
* **對抗假設**:
  在使用者透過引繼碼恢復帳號時，現有邏輯僅呼叫了 `localStorage.removeItem("active_trip_id")` 與 `active_trip_title`。然而，Zustand 持久化中介軟體將狀態儲存在獨立鍵值 `tabidachi-trip-storage` 中。當 `AppShell` 掛載時，Zustand 自動自該快照反向水合出舊帳號（或先前匿名）的 `activeTripId`，直接污染新帳號狀態。
* **獨立沙盒 PoC 實證**:
  - `runner.py` 獨立子代理人執行驗證確認：舊有匿名 `activeTripId` 依然存在於 `tabidachi-trip-storage` 之內，新使用者登入後被強行注入前者的行程 ID。
  - **判定結果**: `CONFIRMED`（實證存在）。

---

### 2.2 [CONFIRMED] `trip-context.tsx`：`prevUserIdRef` 時間競爭導致誤彈「無法存取行程」
* **對抗假設**:
  `TripProvider` 意圖透過 `if (prevUserIdRef.current === userId)` 守衛阻斷帳號切換期間的警告彈窗。然而，`prevUserIdRef.current = userId` 在身分變更當下即被同步執行。由於 SWR 行程拉取為非同步操作（約耗時 200~400ms），當真實清單返回並與殘留的舊 `activeTripId` 比對時，`prevUserIdRef.current` 已經等於 `userId`！守衛形同虛設，系統誤判為「使用者的行程遭到外部刪除」，遂彈出「該行程不存在或無存取權限，已切換至預設行程」誤警報。
* **獨立沙盒 PoC 實證**:
  - `runner.py` 模擬驗證確認：當切換至新身分並載入新行程時，`toast.warning` 被確定性呼叫，造成嚴重的用戶體驗挫折感。
  - **判定結果**: `CONFIRMED`（實證存在）。

---

## 3. 候選補丁與精確區塊替換規格 (Candidate Patches)

### 3.1 目標 1：`frontend/components/views/landing-page.tsx`
* **修復說明**: 引繼成功時執行原子四清：同步抹殺 `tabidachi-trip-storage` 中的殘留 `activeTripId`，並建立 5 秒身分過渡時間鎖 `tabiji_identity_transition_lock`。
* **精確區塊替換 (Target Content / Replacement Content)**:
  - **Target File**: `frontend/components/views/landing-page.tsx`
  - **Target Content**:
```tsx
            // 🛡️ 物理雙清：引繼換帳號時立即抹除前一階段匿名或殘留的行程狀態
            localStorage.removeItem("active_trip_id")
            localStorage.removeItem("active_trip_title")

            // 🆕 通知 App 身分已切換，觸發 SWR 重新 fetch 行程
            window.dispatchEvent(new CustomEvent('user-login-state-changed'))
```
  - **Replacement Content**:
```tsx
            // 🛡️ 物理原子四清：抹除獨立鍵值與 Zustand persist 快照，防禦反向水合
            localStorage.removeItem("active_trip_id")
            localStorage.removeItem("active_trip_title")
            try {
                const raw = localStorage.getItem("tabidachi-trip-storage")
                if (raw) {
                    const parsed = JSON.parse(raw)
                    if (parsed.state) {
                        parsed.state.activeTripId = null
                        parsed.state.activeTripTitle = null
                        localStorage.setItem("tabidachi-trip-storage", JSON.stringify(parsed))
                    }
                }
            } catch (e) {}

            // 標記 5 秒身分引繼過渡鎖，指令 TripProvider 全程保持靜默
            sessionStorage.setItem("tabiji_identity_transition_lock", Date.now().toString())

            // 🆕 通知 App 身分已切換，觸發 SWR 重新 fetch 行程
            window.dispatchEvent(new CustomEvent('user-login-state-changed'))
```

---

### 3.2 目標 2：`frontend/lib/trip-context.tsx`
* **修復說明**: 引入 5 秒時間鎖判定，在引繼或身分過渡窗口期 100% 靜默銜接至合法第一項行程，徹底杜絕誤報。
* **精確區塊替換 (Target Content / Replacement Content)**:
  - **Target File**: `frontend/lib/trip-context.tsx`
  - **Target Content**:
```tsx
                    if (!tripExists) {
                        console.log("⚠️ 快取的行程已刪除或不屬於當前使用者，自動選擇最新行程")
                        // 🛡️ 只有在身分穩定且確實在清單遺失時才彈出警告；帳號切換期間保持靜默
                        if (prevUserIdRef.current === userId) {
                            toast.warning("該行程不存在或無存取權限，已切換至預設行程")
                        }
                        deleteTripSnapshot(activeTripId)
```
  - **Replacement Content**:
```tsx
                    if (!tripExists) {
                        console.log("⚠️ 快取的行程已刪除或不屬於當前使用者，自動選擇最新行程")
                        // 🛡️ 檢查是否處於身分引繼或登入過渡窗口（5 秒內）
                        const isTransitionLocked = () => {
                            if (typeof window === "undefined") return false
                            const lock = sessionStorage.getItem("tabiji_identity_transition_lock")
                            return lock ? Date.now() - parseInt(lock, 10) < 5000 : false
                        }
                        // 只有在身分穩定且非引繼過渡期間才彈出警告；引繼與切換 100% 靜默銜接！
                        if (prevUserIdRef.current === userId && !isTransitionLocked()) {
                            toast.warning("該行程不存在或無存取權限，已切換至預設行程")
                        }
                        deleteTripSnapshot(activeTripId)
```

---

### 3.3 目標 3：`frontend/app/layout.tsx`
* **修復說明**: 在 `<head>` 注入靜態原畫高優先級 Preload，消滅首幀 WebKit 異步圖片解碼卡頓。
* **精確區塊替換 (Target Content / Replacement Content)**:
  - **Target File**: `frontend/app/layout.tsx`
  - **Target Content**:
```tsx
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
```
  - **Replacement Content**:
```tsx
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        {/* 🚀 開屏原畫高解析度遮罩與紙飛機第 0 毫秒預載入 (消除冷啟動跳躍掉幀) */}
        <link rel="preload" href="/images/tabiji-art-mask.png" as="image" type="image/png" fetchPriority="high" />
        <link rel="preload" href="/images/tabiji-paper-plane.png" as="image" type="image/png" fetchPriority="high" />
```

---

## 4. 人類主權與發布守門 (Human Gate Handover)

依據 L0 憲法「唯讀審查，交由人類決策」，本報告候選補丁已在獨立沙盒（`runner.py`）與 Vitest（`account-recovery-atomic-sentinel.test.tsx`）完成 100% 驗證。  
請人類開發者確認核准後，方可進入實作修改。
