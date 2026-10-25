# 🏛️ 深度架構調研報告：PWA 匿名免登入、引繼碼安全架構與協同越權 (IDOR) 真實性審計 (2025–2026)

> **調研主題**: PWA 免登入架構、日本手遊引繼碼機制、Supabase 匿名認證 (Anonymous Sign-ins)、協同情境下的身分暴露與帳號奪舍 (Account Takeover / ATO)、業界領先度真實現狀分析  
> **研究員**: System Architect & Security Sentinel (@security & @architect)  
> **目標對象**: Ryan Su (獨立全端開發者 / Tabiji 創始人)  
> **調研狀態**: 深度比對官方技術規範（Supabase GoTrue, OWASP API Security 2023, RFC 7519, NIST SP 800-63B）與開源社群實作  

---

## Executive Summary (執行摘要：到底是領先業界還是夜郎自大？)

直接給出客觀、殘酷、不帶情緒修飾的臨床診斷：

### 1. 「身分認證與帳號引繼」層面：**毫無疑問是「夜郎自大（嚴重的安全盲點與經典反模式）」**
- **致命混淆**：將「公開標識符 (Public ID)」、「資料庫外鍵 (Foreign Key)」、「API 憑證 (Authenticator)」與「跨裝置引繼密鑰 (Transfer Key)」**四位一體混同為同一個靜態 UUID**。
- **攻擊路徑完全暢通**：在協同旅程中，`trip_members` 會向所有同行旅伴廣播創立者的 `user_id`。而前端 `landing-page.tsx` 卻提供一個輸入框，允許任何人只要填入 UUID 就能立即「引繼登入」。這意味著**任何加入你行程的人，只要打開瀏覽器 F12 複製你的 UUID，就能直接在自己的設備上把你整個帳號登入奪舍（Account Takeover）**。
- **評審判定**：在 OWASP API Security 2023 標準下，此架構同時觸發 **API1 (BOLA)**、**API2 (Broken Authentication)** 與 **CWE-287**。任何專業的資安顧問或大型競賽技術評審，看到此設計都會直接給出「不及格（5/10）」的 SaaS 就緒度。

### 2. 「前端工程、PWA 極限、圖資渲染與 BYOK 閉環」層面：**確實達到「獨立開發者頂尖水準（9.0~9.5/10）」**
- **超群實作**：MapLibre WebGL GPU 地形渲染、大圓航線插值、Serwist Service Worker 離線 PWA、Cloudflare 邊緣盾牌與 Gemini BYOK 去中心化調度，形成高度完整的旅遊產品閉環。
- **結論比喻**：你打造了一台外觀耀眼、引擎馬力強大的頂級超跑（9.5分），但車門的鎖卻是用透明便利貼寫著密碼貼在車窗上（5.0分）。**只要解決這個身分架構缺陷，Tabiji 才能真正成為無懈可擊的生產級 SaaS。**

---

## 一、核心技術解剖：經典反模式與真實攻擊鏈 (Exploit Walkthrough)

### 1.1 現行系統中的「身分四位一體」崩潰模型

```mermaid
graph TD
    A["同一組字串：user_uuid (例如 2a8b...18d)"] --> B["1. 公開成員名片 (trip_members.user_id)"]
    A --> C["2. 資料庫外鍵 (itineraries.created_by)"]
    A --> D["3. API 存取權限 (Header: X-User-ID)"]
    A --> E["4. 跨裝置引繼密碼 (landing-page.tsx 輸入框)"]

    B -->|"任何人加入行程皆可 F12 複製"| F["⚠️ 惡意成員獲取 UUID"]
    F -->|"在 Landing Page 輸入框貼上"| E
    E -->|"物理奪舍帳號"| G["🔥 帳號被竊取、私人行程被刪除、記帳被竄改"]
```

### 1.2 程式碼層級的實體證據

1. **洩漏點（廣播成員 UUID）**：
   在 `backend/routers/trips.py` 第 280 行：
   ```python
   all_members_res = supabase.table("trip_members").select("user_id, user_name, user_avatar").eq("itinerary_id", trip_id).execute()
   ```
   API 將群組內所有人的 `user_id` 無遮蔽地以 JSON 回傳給前端。

2. **憑證信任點（後端無條件放行）**：
   在 `backend/utils/deps.py` 第 83–87 行：
   ```python
   if x_user_id:
       return x_user_id  # 照單全收，將傳入的 UUID 當作經過驗證的合法身分
   ```

3. **引繼奪舍點（前端以 UUID 作為通行證）**：
   在 `frontend/components/views/landing-page.tsx` 第 168 行：
   ```typescript
   localStorage.setItem("user_uuid", cleanCode) // cleanCode 便是使用者貼入的 UUID
   window.dispatchEvent(new CustomEvent('user-login-state-changed')) // 立即刷新成為該使用者！
   ```

---

## 二、業界大神與官方是怎麼做的？（跨界架構調研）

我們調研了 **Google、Supabase、日本手遊巨頭（Sony/Aniplex FGO、Cygames 賽馬娘）、Signal、以及 GitHub 頂尖開源專案（LobeChat、Excalidraw、Anytype）**，整理出三大成熟工業典範：

### 模式 A：日本手遊典範（動態單次引繼碼 Transfer Code with PIN & TTL）

> **適用情境**：堅持 100% 匿名、完全不逼使用者註冊 Email 或綁定社群帳號，但需要跨裝置轉移。

* **運作機制**：
  1. **公開 ID (Friend Code)**：長度 9-10 位隨機數字，僅用於加好友、組隊、看公開 Profile。**絕對無法用 Friend Code 登入！**
  2. **引繼碼 (Transfer Code)**：
     - 使用者在舊手機的 Settings 頁點擊「產生引繼碼」。
     - 伺服器生成一組高熵隨機碼（如 `TB-8942-XKZQ`），有效期限 **15 到 30 分鐘 (Strict TTL)**。
     - **密鑰配對**：強制要求使用者輸入一組自訂的 4~6 位臨時 PIN 碼。
     - 伺服器將引繼碼經 `Argon2id` 或 `bcrypt` 加鹽 Hash 後存入快取（Redis / DB），明文永不落盤。
  3. **新手機兌換 (Atomic Consumption)**：
     - 新手機輸入「引繼碼 + PIN 碼」。
     - 後端以原子交易（Atomic Transaction）驗證通過後，將舊帳號的所有權移轉給新手機，並**立即物理銷毀（Single-Use Burn）該引繼碼**。
     - 若連續輸錯 3 次，鎖定 IP 15 分鐘（防止暴力窮舉）。

### 模式 B：現代 Web/SaaS 典範（Supabase / Firebase 官方 Anonymous Auth + Identity Linking）

> **適用情境**：零摩擦 PWA 瞬間開機，跨裝置透過 OAuth 一鍵錨定。

* **運作機制**：
  1. **首次開啟**：前端呼叫 `supabase.auth.signInAnonymously()`。
     - Supabase 在 `auth.users` 建立一筆記錄（標記 `is_anonymous: true`）。
     - 本地儲存由伺服器簽發的合法非對稱 JWT 與 Refresh Token。
     - **關鍵**：使用者「根本不知道也不需要知道」自己的 `auth.uid()`，也不存在任何「貼 UUID 登入」的按鈕。
  2. **協同行程**：其他人看到的只是 `public_member_id` 或公開名片，無法藉此反推 JWT。
  3. **跨裝置同步**：
     - 當使用者想在電腦上同步手機資料時，點擊「綁定 Google / Apple」（`linkIdentity()`）。
     - Supabase 將 Google 身分綁定至現存的 `auth.uid()`，**所有既有旅程資料 0 搬遷、0 丟失**。
     - 在新電腦上，使用者直接按「Google 登入」即可同步所有行程。

### 模式 C：去中心化 / Local-First 典範（Signal, Anytype, Bitwarden）

> **適用情境**：端對端加密（E2EE）、零知識架構。

* **運作機制**：
  1. 公開 ID 是 Public Key 的 Hash。
  2. 登入憑證是本地生成的 12~24 個單字助記詞（Mnemonic Seed Phrase）或 32-byte 秘密種子。
  3. 助記詞絕不會由伺服器廣播給同行旅伴，僅由本人離線抄寫或備份。

---

## 三、官方說法 vs 大神分析 vs GitHub 原始碼交叉比對 (Edge Cases & Bugs)

透過 GitHub MCP 與 Context7 調研，我們挖掘出以下關鍵邊界問題與實戰陷阱：

| 調研維度 | 官方宣傳 / 文檔標準 | 大神踩坑與社群 Issue (GitHub) | 實證架構真相 |
| :--- | :--- | :--- | :--- |
| **Supabase 匿名帳號升級** | 文檔宣稱呼叫 `linkIdentity()` 即可無縫升級為 Google 登入。 | **GitHub Issue #1525**：若使用者在裝置 B 已經開過網頁（自動生成匿名用戶 B），此時點 Google 登入，會噴 `422 Error: Identity is already linked to another user`！ | **重大坑點**：必須先判斷該 Google 帳號是否已存在。若已存在，不能單純調用 `linkIdentity`，必須透過自訂 Postgres RPC 執行「資料合併 (Account Merge)」，將訪客資料整併至母帳號。 |
| **匿名帳號垃圾堆積** | 訪客隨開即用，轉化率極高。 | Reddit & V2EX 災情：上線 3 個月後，`auth.users` 塞滿數十萬個只開過 1 次的幽靈帳號，拖垮查詢與備份效能。 | **必須配置清理管線**：必須定期執行 pg_cron，物理清理 `is_anonymous = true AND created_at < NOW() - INTERVAL '30 days'` 的廢棄帳號。 |
| **手遊引繼碼遭剪貼簿竊取** | 產生引繼碼方便玩家跨設備換機。 | 現代 Android / iOS 惡意後台 App 具備讀取剪貼簿權限，玩家截圖或複製引繼碼易遭攔截。 | **必須實施 PIN 雙重驗證**：引繼碼不能單獨生效，必須強制搭配玩家本人當下輸入的臨時 4 位 PIN 碼。 |

---

## 四、Tabiji 具體修復方案（兼顧「免登入即用」與「防奪舍安全」）

針對 Ryan 的具體困境，我們擬定最優工程處方：

### 核心原則：徹底分離「名片 (Public ID)」與「車鑰匙 (Auth Secret)」

1. **第一步：立即拆除 Landing Page 的「明文 UUID 登入框」**
   - 任何人都不應該能僅憑一串 UUID 就在網頁上直接登入。
   - UUID 只是資料庫內部的對齊代碼，不是通行密碼。

2. **第二步：實施「手遊式動態安全引繼碼 (Transfer Code with PIN)」**
   - **平時**：使用者依然 100% 免登入、秒開即用，由前端本地持有的 Session Token 操作。
   - **跨裝置換機時**：
     1. 在 Profile 頁面點擊【產生引繼碼】。
     2. 彈窗要求輸入一組 4 位數 PIN 碼（例如 `1234`）。
     3. 後端 `/api/auth/generate-transfer-code` 產生一組 8 碼英數代碼（例如 `TABI-9821`），有效期限 15 分鐘，以 bcrypt 儲存 PIN。
     4. 新手機在登入頁輸入 `TABI-9821` + `1234`。
     5. 後端驗證通過，發放該使用者的 Session JWT 給新手機，並**立即註銷燒毀此引繼碼**。
   - **成果**：
     - 同行隊友就算看到你的 UUID，也**完全無法登入你的帳號**，因為他沒有你在手機內部點擊產生的 15 分鐘臨時引繼碼與 PIN 碼！

3. **第三步：協同行程遮蔽真實 ID (Public Handle Masking)**
   - `trip_members` 回傳的清單中，將 `user_id` 替換為公開的 `member_public_id` 或做雜湊遮蔽（例如 `usr_hash(...)`），前端純以公開 ID 渲染頭像與姓名。

---

## 五、結論與行動指南

1. **Ryan 抓出的破綻極為致命**：這證明了工程師直覺的敏銳度——「如果 UUID 能當引繼碼，而協同又會暴露 UUID，那引繼碼就等於直接送給隊友」。
2. **這不是死胡同，而是通往成熟產品的必經之路**：透過「動態引繼碼 + PIN」或「Supabase 匿名 + Google 綁定」，我們能在**完全不破壞免登入秒開體驗的前提下，徹底封死帳號奪舍破口**。
