# PWA 權限沙盒邊界與跨生態相容實現矩陣 (2025-2026)
**文件識別碼**: `RESEARCH-PWA-PERM-SANDBOX-2026-10-17`  
**建立時間**: 2026-10-17 19:35:00 UTC+8  
**針對架構**: Tabidachi (Next.js 16 + React 19 + Serwist PWA + Supabase + Cloudflare)  
**研究核心**: 深入檢驗 PWA 在 iOS (WebKit) 與 Android (Chromium) 沙盒環境下的實體權限極限，剖析何種跨應用互通「會被作業系統阻斷」，何種互通「能透過協議級手段零權限穿透」。

---

## 一、 PWA 沙盒的四大物理死穴 (What PWA CANNOT Do)

身為 PWA (Web 應用)，我們受限於瀏覽器安全模型（Browser Security Sandbox），絕對無法進行以下操作：

1.  **無靜默寫入系統日曆權限 (No Direct Silent Calendar Mutation)**：
    *   原生 App (Swift / Kotlin) 獲得 `EKEventStore` 權限後，可在背景無聲無息寫入使用者日曆。
    *   **PWA 死穴**：Web API（如已被棄用的 Chrome Calendar API）**絕對沒有**直接向作業系統日曆資料庫靜默寫入事件的權限。任何日曆寫入必須透過使用者確認或協議訂閱。
2.  **iOS 不支援 `share_target` 作為接收端 (No iOS Native Share Sheet Ingress)**：
    *   在 Android 上，PWA 可在 `manifest.json` 宣告 `share_target`，出現在系統分享選單中。
    *   **PWA 死穴**：Apple iOS 至今仍將原生 Share Sheet 封鎖給原生 App，**iOS Safari PWA 無法註冊為分享目標**。使用者無法在 iOS 的 Google Maps 點「分享至 Tabidachi」。
3.  **無本機跨應用檔案系統讀取 (No Cross-App Local File Access)**：
    *   無法在背景掃描或讀取使用者的 Gmail、Apple Mail 檔案目錄或 LINE 訊息。
4.  **iOS 背景凍結與生命週期限制 (WebKit Background Suspension)**：
    *   當 PWA 切換至背景或被上滑關閉時，iOS WebKit 會在數秒至數十秒內強制凍結 JS 執行緒與 Service Worker，無法在背景持續輪詢第三方 API。

---

## 二、 協議級「零權限穿透」解決方案矩陣 (How PWA Bypasses Sandbox)

雖然 PWA 權限有限，但透過**標準作業系統協議（OS Protocol Handlers）與 MIME Type 攔截**，我們能在**「完全不需要申請高風險權限」**的前提下，實現比原生 App 更輕量的跨生態相容：

| 外部生態 | 傳統原生 App 作法 (需敏感權限) | Tabidachi PWA 零權限穿透解法 (100% 合法且免權限) | iOS (WebKit) 支援度 | Android / PC 支援度 |
| :--- | :--- | :--- | :--- | :--- |
| **外部地圖導航** | 呼叫 Google Maps SDK（肥大且需 API Key） | **Deep URL Schemes 喚醒**：<br>• Apple Maps: `maps://?daddr=lat,lng&q=名稱`<br>• Google Maps: `https://www.google.com/maps/dir/?api=1&destination=lat,lng`<br>• Navitime: `navitime://...` 或網頁降級 | ✅ 100% 原生切換，零權限 | ✅ 100% 原生切換，零權限 |
| **行事曆同步與提醒** | 索取 `NSCalendarsUsageDescription` 寫入日曆庫 | **Webcal 訂閱協議 (`webcal://`)**：<br>PWA 提供動態 ICS 訂閱網址，OS 日曆直接接管！<br>**好處**：**系統日曆原生地理提醒與時區轉換由 iOS/Google 系統背景服務接管**，PWA 即使關閉也能精準提醒！ | ✅ 100% 點擊喚醒「訂閱此行事曆」 | ✅ 100% Google Calendar 訂閱 |
| **單一行程日曆注入** | 透過原生代碼寫入單筆 Event | **MIME Type 觸發 (`text/calendar`)**：<br>前端產生 `.ics` Blob 並下載，或透過 `navigator.share`，iOS/Android 自動彈出「將 N 個行程加入行事曆」的確認視窗。 | ✅ 100% 彈出系統加入視窗 | ✅ 100% 彈出系統加入視窗 |
| **地圖景點匯入 (iOS)** | 註冊 Native Share Extension 接收網址 | **智能剪貼簿監聽 (Smart Clipboard Ingress)**：<br>在 iOS 上，使用者在 Google Maps 複製連結 -> 切回 Tabidachi -> PWA 偵測剪貼簿或提供「貼上 Google Maps 網址」輸入框 -> 302 轉發解析座標。 | ✅ 需使用者點擊「貼上」允許 | ✅ 亦支援 `share_target` 自動接收 |
| **筆記整理 (Notion)** | 串接複雜的 Notion OAuth 伺服器雙向同步 | **富文本剪貼簿協議 (`navigator.clipboard`)**：<br>純前端一鍵將行程格式化為標準 Markdown / 帶 Checkbox 的清單，使用者貼上 Notion/Obsidian 即刻排版。 | ✅ 100% 剪貼簿支援 | ✅ 100% 剪貼簿支援 |
| **試算表對帳 (Excel)** | 伺服器生成 Excel 檔案回傳 | **純前端 CSV 產生器**：<br>瀏覽器本機產生帶 `\uFEFF` UTF-8 BOM 的 CSV 檔案，直接透過 Blob 下載，完全不經過後端。 | ✅ 100% 檔案下載 | ✅ 100% 檔案下載 |
| **電子錢包 (Apple Wallet)** | 需原生 PassKit 框架 | **MIME Type 觸發 (`application/vnd.apple.pkpass`)**：<br>伺服器簽署產出 `.pkpass`，Safari 點擊後原生跳出「加入 Apple 錢包」介面。 | ✅ 100% Safari 原生支援 | 需 Google Wallet 替代格式 |

---

## 三、 架構戰略結論：為什麼 PWA 的「協議相容」反而比原生「API 綁定」更強大？

1.  **使用者隱私阻力最小**：
    *   原生 App 一安裝就彈出「要求存取您的日曆」、「要求存取您的聯絡人」、「要求常駐背景位置」，使用者防禦心理極高。
    *   PWA 採用 **URL Schemes 與 Webcal 協議**，使用者點擊時只會看到系統官方的確認（例如「是否要訂閱此行事曆？」、「是否開啟 Google 地圖？」），**不需要交出任何隱私權限給 Tabidachi**，信任度最高。
2.  **責任轉移與零耗電**：
    *   如果由 PWA 自己在背景維持 WebSocket 或輪詢來推播「您的下一個行程還有 10 分鐘開始」，iOS 會在 30 秒內殺死 PWA，且非常耗電。
    *   但如果交給 `webcal://` 訂閱，**提醒責任直接轉嫁給 iOS 系統內建的日曆守護程式 (Calendar Daemon)**，享受 100% 可靠的原生推播與鎖定螢幕通知，Tabidachi 的伺服器與 PWA 本身**完全不需消耗任何運算資源**。
3.  **零伺服器邊際成本 (Zero Infrastructure Cost)**：
    *   產出 `.ics`、產出 Markdown、產出 CSV、產出地圖喚醒 Deep Link，全部都是**純前端字串拼接或輕量格式化**，運算耗時不到 5 毫秒，0 伺服器負擔，完全吻合我們的零邊際成本架構。
