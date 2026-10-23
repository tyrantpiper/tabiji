# 🧬 雙重快取的醫源性病變與協同錯覺：一次關於狀態主權的深度冷血反思

> **記錄日期**: 2026-10-23  
> **筆記屬性**: 工程心智後設認知（Metacognition）與架構病理學解剖  
> **視角**: 醫學訓練背景的獨立開發者。直面今日「新增項目反覆消失」、「Service Worker 舊快取毒丸」與「跨模組協同斷裂」背後的技術盲區與系統代價。

---

## 一、醫源性病變：當「效能優化」成了資料抹煞的毒丸

臨床上有個詞叫「醫源性疾病（Iatrogenic Disease）」——醫生為了治療病人的某個症狀開了強效藥，藥物副作用卻破壞了病人的內壓平衡，引發了更致命的器官衰竭。

今日在 Tabiji 爆發的「重點事項新增後瞬間可見、數秒後卻莫名蒸發」Bug，就是教科書級別的醫源性病變。

```mermaid
flowchart TD
    subgraph 醫源性快取互踩迴圈
        A[使用者新增重點提醒] -->|0ms| B[SWR 記憶體樂觀更新: 畫面出現]
        B -->|非同步發送| C[FastAPI 後端: 成功落盤 PostgreSQL]
        C -->|觸發| D[SWR 背景發起 Revalidate GET 請求]
        D -->|攔截| E[Service Worker: 命中 7 天 trips-api-cache]
        E -->|回灌舊磁碟快照| F[SWR 狀態遭 7 天前舊資料覆寫: 項目瞬間蒸發！]
    end
```

### 1. 自作聰明的雙重快取架構

幾週前為了讓 PWA 在斷網或冷啟動時達到「零白屏秒開」，我在 Serwist Service Worker 裡給 `/api/trips/` 加上了 `StaleWhileRevalidate` 策略，並配置了 7 天的磁碟快取（`trips-api-cache`）。

當時的我自以為完成了極致的效能優化，但實質上犯了架構設計的大忌：**違背單一真相源（Single Source of Truth），在同一條資料鏈路上架設了兩個缺乏原子性協調的快取層**。

- **層級一（應用層）**：SWR 負責管理前端記憶體快取與樂觀更新（Optimistic UI）。
- **層級二（傳輸層）**：Service Worker 在底層攔截 HTTP 流量，自作主張地從 CacheStorage 回灌舊資料。

### 2. 病理惡化機制

當使用者點擊新增時，SWR 在記憶體裡率先把新項目畫出來（樂觀更新）；隨後 SWR 向後端發起背景驗證。結果這個 GET 請求根本沒摸到伺服器，直接被 Service Worker 攔腰截斷，把 7 天前的舊磁碟快照吐給了 SWR。

SWR 信任了這個回應，用舊資料洗掉了剛才的樂觀更新——**使用者親眼看著自己剛敲進去的文字被系統活生生吃掉**。

### 3. 解剖後的醒悟

快取不是越多越好。快取層級每增加一層，系統狀態的排列組合與競態邊界就呈指數級暴增。

- **決策落盤**：動態業務實體（`/api/trips/`）必須嚴格隔離在 Service Worker 的 `NetworkOnly` 規則外。
- **快取主權**：快顯責任 100% 收攏至應用層 SWR 與具備版本時間戳記的本機儲存（L0 LocalStorage / L1 IndexedDB）。寧可沒有 SW 磁碟快取，也絕不容許傳輸層擅自向應用層灌入過期狀態。

---

## 二、協同錯覺：對 Supabase Realtime 與 CDC 的盲目迷信

很多全端開發者（包括過去的我）在讀完宣傳文案後，往往對 WebSocket、Supabase Realtime 與變更數據擷取（CDC, Change Data Capture）產生一種不切實際的浪漫幻想：「只要掛上 `postgres_changes`，我的 App 就瞬間具備 Figma 級別的多人即時協同了。」

今天一連串殘酷的物理排查，徹底擊碎了這個幻想。

```mermaid
flowchart LR
    subgraph 協同幻想與殘酷現實
        R1[幻想: CDC 自動同步一切] -.->|現實 1: 欄位拼錯| F1[expenses 表外鍵為 itinerary_id 而非 trip_id<br/>Supabase 靜默裝死，0 報錯但 0 觸發]
        R1 -.->|現實 2: 資安旁路穿透| F2[postgres_changes 直推 Raw Row<br/>繞過後端 FastAPI 脫敏與 BOLA，機密洩漏]
        R1 -.->|現實 3: 快取鍵型別失配| F3[useExpenses 註冊 Tuple 鍵 [url, uid]<br/>字串 mutate() 打在空氣上，靜默無效]
    end
```

### 1. 靜默失聯的痛苦（Silent Failures）

我在前端監聽 `expenses` 表的異動，監聽條件寫了 `filter: trip_id=eq.${tripId}`。結果同伴在另一台手機記了帳，這邊的畫面紋風不動。
排查了半天才發現，資料庫裡費用表的外鍵欄位根本叫 `itinerary_id`，不叫 `trip_id`。
**Supabase 的 CDC 面對不存在的欄位名稱時，不會拋出錯誤，甚至不會在 Console 印出一行 Warning**。它只是安靜地坐在那裡，吞掉所有推播。這種「無聲的失敗」是系統工程中最昂貴的除錯黑洞。

### 2. 資安後門的警鐘

當真正抓到 CDC 推播的封包時，我背脊發涼：`postgres_changes` 預設是把資料庫那一行原始資料（Raw Row Payload）原封不動地透過 WebSocket 廣播到連線客戶端。
這意味著：

- 私人隱藏花費直接被推給了非擁有者。
- 建立者的原生 UUID、內部審計欄位未經任何脫敏（Sanitization）直接裸奔。
- 後端精心設計的 BOLA（物件授權）防禦牆，被前端一條看似無害的 Realtime Channel 繞得乾乾淨淨。

### 3. 破除迷思的架構重塑

這促使我做出了今日最重要的架構決策（AD-156）：**CDC 絕不可作為業務數據的傳輸載體**。

- WebSocket 推播只能充當**「無載荷的失效觸發訊號（Zero-Payload Invalidation Trigger）」**。
- 客戶端收到訊號後，必須規規矩矩地走標準 HTTP 管道向 FastAPI 閘道發起 `GET`。所有的鑑權、脫敏、隱私過濾，一律在後端嚴格收口。

---

## 三、微觀生命週期裡的魔鬼：過期閉包與幽靈隊列

宏觀架構定得再漂亮，如果對底層 JavaScript 的事件迴圈（Event Loop）、React 渲染週期與記憶體生命週期缺乏敬畏，系統依然會在微觀處分崩離析。

### 1. React 異步狀態更新的閉包陷阱

在資訊頁面（`InfoView`）的飯店編輯邏輯中，原先的程式碼長這樣：

```typescript
// ❌ 致命的閉包過期代碼
newHotels[currentHotelIdx] = tempHotel;
setHotels(newHotels); // 觸發非同步排程更新
setInnerEditing(false);
handleSave(); // 👈 這裡讀取的 hotels 依然是「上一幀渲染」的過期舊狀態！
```

當使用者修改了飯店名稱並點擊儲存，下方的 `handleSave()` 從當前函式閉包裡抓取 `hotels`。但此時 React 根本還沒完成重新渲染（Re-render），結果打到後端的居然是尚未修改的舊飯店資料！

- **修復**：徹底放棄對閉包 state 的盲目依賴，將 `handleSave` 重構為支援顯式引數傳遞：`handleSave(overrideHotels)`。資料流從此具備絕對的確定性。

### 2. 離開房間後的幽靈便條紙（Queue Leak）

在實作 `RealtimeChannelCoordinator` 時，為了防止使用者在網路不穩時遺失廣播，我設計了一個離線待發信箱（`queueMap`）。
然而，當元件卸載（Unmount）調用 `detach(tripId)` 時，我清理了連線狀態與頻道，**卻把 `queueMap` 遺忘在單例記憶體裡**。
這導致了一個隱蔽的幽靈現象：

> 使用者在行程 A 離線時隨手打了幾個字（產生廣播事件排入佇列）；隨後他切換去看行程 B；過了半小時，他又切回行程 A。連線建立的瞬間，系統翻出半小時前那封過期的便條紙，強行推播給旅伴——旅伴的手機畫面莫名跳動，剛改好的內容甚至被這封「幽靈信件」衝擊。

一行看似不起眼的修正：

```typescript
public detach(tripId: string) {
    this.channelMap.delete(tripId);
    this.statusMap.delete(tripId);
    this.queueMap.delete(tripId); // 🧹 離開房間，便條紙當場碎紙銷毀
}
```

**讓物件生命週期與網路會話生命週期完全對齊**。沒有這行代碼，任何高可用保證都只是空中樓閣。

---

## 四、工程心智的自我批判：我們是否過度防禦了？

回顧今天一整天的排查歷程：
為了根除這幾個問題，我調用了 Chrome DevTools MCP 做即時物理遙測、在後端寫了 2 套 Python In-Memory PoC、更新了 18 個檔案、在日誌中寫下了 4 個架構決策與 4 個踩坑紀錄，甚至寫了腳本自動把規則注入到大腦領域庫中。

這時候，一個冷酷的聲音必須跳出來質問自己：

> **「你是在做扎實的軟體工程，還是在把簡單問題複雜化，以此滿足某種控制狂般的技術儀式感？」**

經過冷靜解剖，我的答案是：

1. **問題的本質是複雜的**：
   前端離線快取（Service Worker + IndexedDB + LocalStorage）與多人即時廣播（WebSocket + SWR）交織在一起時，本質上就是一個分散式系統（Distributed System）。在分散式環境下，「資料何時過期」、「誰是真相源」、「斷線重連如何補償」，每一項都是經典的並發難題，容不得半點僥倖。如果不用這種手術刀式的精度去拆解，系統只會在日後無休止地隨機崩潰。
2. **防禦體系的確有膨脹的風險**：
   我必須時刻自我警惕：工具與測試矩陣是手段，不是目的。寫了 240 個單元測試與 204 個資安條目，如果最後拖垮了迭代速度，那就是本末倒置。
   **奧坎剃刀（Occam's Razor）永遠是最後的懸崖勒馬繩**——「如無必要，勿增實體」。當我們發現 Service Worker 磁碟快取與 SWR 衝突時，最乾淨的做法不是再去寫一套複雜的跨層快取協調演算法，而是**果斷砍掉 Service Worker 的動態快取**，把責任還給單一模組。

---

## 五、結語：在確定性中前行

今天的經歷再次印證了臨床醫學教給我的底層思維：

- **尊重生理機轉**：不要試圖對抗瀏覽器的生命週期與非同步事件迴圈。
- **拒絕貼布式治療**：看見問題不要只加一個 `setTimeout` 或多包一層 `try-catch`，必須把資料流的來龍去脈從根部摸清楚。
- **不信任口頭承諾**：瀏覽器的快照、網路的 Status Code、測試套件的綠燈，才是真實世界的唯一度量衡。

760 筆 Commit 之後，代碼庫漸漸褪去了浮躁的拼貼感，正在長出屬於它自己的骨骼與神經。而身為開發者的我，依然在敬畏與清醒中，持續校準著自己的坐標。
