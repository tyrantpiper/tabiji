# 🔗 聯盟行銷多網域歸因、防禦性渠道架構與出款審核 (Payout Audit) SOP

> **文件狀態**: 正式發布 (Production Spec)  
> **建立日期**: 2026 年 10 月 17 日  
> **適用平台**: Travelpayouts (Klook 4110, KKday 9074, Airalo 8310, Agoda), Direct Klook Affiliate, Direct KKday Partner  
> **核心目標**: 換網域零斷流、免重申請、雙渠道並存保護測試環境、防禦人工請款稽核 (Payout Audit) 卡單  

---

## 1. 聯盟行銷底層歸因原理：為什麼換網域不需要重新申請？

當專案從初期的測試網址（如 Vercel 預設子網域或舊網域）遷移至正式自訂網域 `https://tabijiapp.com` 時，許多創辦人會恐慌是否需要「砍掉重練全部重新向廠商申請審核」。

答案是：**絕對不需要！底層追蹤完全不會中斷。**

### 1.1 歸因核心：認「Marker Token / Affiliate ID」，不認來源網址
* 查看前端代碼庫中的 `frontend/lib/affiliate-config.ts`，所有票券、eSIM 與住宿的導購連結本質上是透過 Travelpayouts 或原廠的短鏈跳轉：
  ```text
  https://tp.media/r?marker=[你的MarkerID]&p=[廠商ID]&url=[目標商品頁面]
  ```
* **生命週期機制**：
  1. 使用者在 `tabijiapp.com` 點擊連結。
  2. 瀏覽器跳轉至合作夥伴（Klook / KKday / Airalo）伺服器。
  3. 廠商伺服器**立即將含有你 Marker ID 的追蹤 Cookie 寫入使用者的瀏覽器本地儲存中**（有效期限普遍長達 30 天～90 天）。
  4. 使用者在 Cookie 有效期內完成下單結帳，廠商結帳系統直接以該 Cookie 作為依據，將佣金計入你的收款帳號。
* **結論**：點擊跳轉當下，分潤判定完全取決於 URL 內的 Marker 參數與目標端 Cookie，**完全不會因為發射端網域名稱改變而失效**。

---

## 2. 雙渠道並存架構（Two-Channel Architecture）的戰略價值

雖然技術上點擊立刻有效，但**必須在後台執行「雙渠道並存（Two-Channel Architecture）」備案**。

```
                               ┌────────────────────────────────┐
                               │     創辦人聯盟行銷核心錢包     │
                               │   (Travelpayouts / Klook ID)   │
                               └───────────────┬────────────────┘
                                               │
               ┌───────────────────────────────┴───────────────────────────────┐
               ▼                                                               ▼
┌───────────────────────────────┐                               ┌───────────────────────────────┐
│     Channel 1: 正式生產站     │                               │     Channel 2: 內部測試站     │
│   (Official Production PWA)   │                               │       (Dev / Staging)         │
│   URL: https://tabijiapp.com  │                               │   URL: https://*.vercel.app   │
│   功能: 真實旅客流量與分潤出款 │                               │   功能: 整合測試、CI 驗證、無污染 │
└───────────────────────────────┘                               └───────────────────────────────┘
```

### 為什麼「兩個都留」比「直接改掉」更好？
1. **防禦請款稽核（Payout Audit）卡單**：
   * 當佣金累積達到平台撥款門檻（如 50 美元或 100 美元），平台的法務與風控團隊在發放第一筆電匯前，會人工抽查流量來源 Referer。
   * 若後台已完整登記 `https://tabijiapp.com`，系統可秒速驗證通過，避免「流量來源不明」被要求凍結帳戶補件說明。
2. **舊網址 301 轉址流量不漏單**：
   * 過去分享在社群、競賽文件或早鳥用戶瀏覽器書籤中的舊網址，即便被轉址，依然屬於授權白名單內。
3. **隔離開發與測試環境（Staging Protection）**：
   * 本地開發或 Staging 環境測試點擊時，後台風控不會將其判定為爬蟲或假流量攻擊。

---

## 3. 各大平台後台操作 SOP

### 3.1 Travelpayouts 後台操作（耗時約 2 分鐘）
1. 登入 **Travelpayouts Dashboard**。
2. 進入 **Projects**（專案 / 渠道管理）。
3. **保留舊專案**：將原本舊網址的 Project 名稱備註為 `Tabiji (Legacy / Staging)`。
4. **點擊「Add Project」新增正式專案**：
   * **Project Name**: `Tabiji Official Production`
   * **Website URL**: `https://tabijiapp.com`
   * **Type**: `Content Website / Mobile Application (PWA)`
   * **Target Audience**: East Asia, Japan Free Independent Travelers (FIT)
5. 儲存送出即可（通常不需人工重審，即時生效）。

### 3.2 直簽型平台（Direct Klook / KKday Partner）
* 登入後台 ➔ 點選 `Account Settings` ➔ `Traffic Channels / Media Assets` ➔ 點選 `Add Media / Website`。
* 輸入 `https://tabijiapp.com`，分類選擇 Travel Tech / Mobile PWA，即刻完成確權。

---

## 4. 前端工程與環境變數防禦清單

在生產環境部署前，檢查代碼庫確認以下兩點：
1. **環境變數完整性**：
   * 檢查 Vercel / Cloudflare 的 Production Environment Variables，確保 `NEXT_PUBLIC_TP_MARKER` 已正確設置。
2. **動態路徑檢核**：
   * 確保 `frontend/lib/affiliate-config.ts` 與所有 Deep Research 卡片中的轉址函式一律讀取環境變數，無寫死任何舊測試網域名稱。
