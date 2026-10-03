# tabijiapp.com 零缺陷生產級部署 SOP 規格書 (v2 Hardened)

> **網域目標**: `tabijiapp.com` / `www.tabijiapp.com`  
> **舊站保障**: `travel-pwa-five.vercel.app`（100% 獨立可用且不中斷）  
> **後端目標**: Google Cloud Run (`antigravity-backend-589255638719.us-central1.run.app`)  
> **審核認證**: 零降級 (Zero Regression)、無 V8 TypeError、無 GFE 404、無重定向迴圈。

---

## 完整執行流程（全 6 階段）

### 階段 0：後端雲端部署（啟動 GCP 網域白名單）
> 目的：讓運行於 GCP Cloud Run 的 FastAPI 實例即時認可 `tabijiapp.com`，防範 CORS 攔截。

1. 本機已在 [`backend/main.py`](file:///d:/Project/Tabidachi/travel-pwa/backend/main.py) 將 `https://tabijiapp.com` 加入白名單。
2. 執行 Git Commit 與 Push 至 `main` 分支：
   - GitHub Actions (`deploy-backend.yml`) 將自動構建並發布新版至 Cloud Run。

---

### 階段 1：保障原本網站 100% 存活（Vercel 環境變數）
> 目的：使舊網址 `travel-pwa-five.vercel.app` 呼叫同源 `/api/*` 時，Vercel 內部精準轉發至 Cloud Run，避免本地 127.0.0.1 崩潰。

1. 登入 [Vercel 控制台](https://vercel.com/) ➔ 進入 `travel-pwa` 專案。
2. 點選 **Settings** ➔ **Environment Variables**。
3. 新增變數：
   - **Key**: `INTERNAL_BACKEND_URL`
   - **Value**: `https://antigravity-backend-589255638719.us-central1.run.app`
   - **Environment**: 勾選 Production, Preview, Development。
4. 點選 **Save** 儲存。

---

### 階段 2：Vercel 網域綁定與平滑驗證（零競爭過渡）
> 目的：避免 Cloudflare 橘色雲朵阻礙 Vercel 的 CNAME 所有權探針。

1. 進入 [Cloudflare Dashboard](https://dash.cloudflare.com/) ➔ 點選 `tabijiapp.com` ➔ 左側選單 **DNS** ➔ **Records**：
   - 新增 1：`CNAME` | 名稱 `@` | 目標 `cname.vercel-dns.com` | **灰色雲朵 (DNS Only)**
   - 新增 2：`CNAME` | 名稱 `www` | 目標 `cname.vercel-dns.com` | **灰色雲朵 (DNS Only)**
2. 前往 [Vercel 專案設定](https://vercel.com/) ➔ **Settings** ➔ **Domains**：
   - 新增 `tabijiapp.com`。
   - 新增 `www.tabijiapp.com`（選擇 Recommended / Redirect to `tabijiapp.com`）。
   - 看到狀態顯示 **Valid Configuration (綠色打勾)**。
3. 回到 Cloudflare DNS 控制台：
   - 將上述 2 筆 CNAME 紀錄切換為 **橘色雲朵 (Proxied)**。

---

### 階段 3：Cloudflare SSL/TLS 安全配置（防重定向迴圈）
> 目的：杜絕 Flexible 模式引發的 HTTP/HTTPS 無限重定向迴圈 (`ERR_TOO_MANY_REDIRECTS`)。

1. 在 Cloudflare 左側選單點選 **SSL/TLS** ➔ **Overview**：
   - 加密模式選擇：**Full (Strict) (嚴格)**。
2. 進入 **SSL/TLS** ➔ **Edge Certificates**：
   - 將 **Always Use HTTPS** 切換為 **開 (On)**。
   - 將 **Automatic HTTPS Rewrites** 切換為 **開 (On)**。

---

### 階段 4：部署 Hardened 邊緣防護罩 Worker（解鎖 Cloud Run 404 與 GET 容錯）
> 目的：在邊緣攔截 `/api/*` 改寫 Host 標頭，放行 Vercel 本地 API，並防禦 GET/HEAD 攜帶 body 拋出的 V8 TypeError。

1. 進入 Cloudflare 左側選單 **Compute (Workers & Pages)** ➔ 點擊 **Create application** ➔ **Create Worker**。
2. 名稱填寫：`tabijiapp-edge-shield` ➔ 點擊 **Deploy**。
3. 點擊 **Edit code**，貼入以下生產等級代碼並點選 **Deploy**：

```javascript
/**
 * Tabidachi 邊緣同源防護罩 (Edge Shield - Hardened v2)
 * 解決 GET/HEAD TypeError、支援 Gemini 流式串流、放行 Vercel 本地 API
 */
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const pathname = url.pathname;

    // 1. 放行 Vercel 本地處理的 API（如 Cloudinary 收據簽章與本地路由）
    if (pathname.startsWith('/api/sign-cloudinary') || pathname.startsWith('/api/parse-receipt')) {
      return fetch(request);
    }

    // 2. 目標 Google Cloud Run 實例
    const TARGET_HOST = 'antigravity-backend-589255638719.us-central1.run.app';
    const backendUrl = new URL(url.pathname + url.search, `https://${TARGET_HOST}`);

    // 3. 標頭重寫（規避 GFE 404）
    const newHeaders = new Headers(request.headers);
    newHeaders.set('Host', TARGET_HOST);
    newHeaders.set('X-Forwarded-Host', url.hostname);
    newHeaders.set('X-Forwarded-Proto', url.protocol.replace(':', ''));

    // 🛡️ 極致容錯：GET 與 HEAD 嚴禁攜帶 body，避免 V8 TypeError
    const isBodyAllowed = !['GET', 'HEAD'].includes(request.method.toUpperCase());

    const initOptions = {
      method: request.method,
      headers: newHeaders,
      redirect: 'follow',
      body: isBodyAllowed ? request.body : undefined,
    };

    // 若有 body 則啟用串流雙工模式
    if (isBodyAllowed && request.body) {
      initOptions.duplex = 'half';
    }

    try {
      const response = await fetch(backendUrl.toString(), initOptions);
      
      const responseHeaders = new Headers(response.headers);
      responseHeaders.set('X-Edge-Shield', 'Cloudflare-Worker-Active');

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
    } catch (err) {
      return new Response(JSON.stringify({
        error: "Backend Edge Proxy Error",
        detail: err.message
      }), {
        status: 502,
        headers: { "Content-Type": "application/json" }
      });
    }
  }
};
```

4. 綁定自訂路由：進入該 Worker 的 **Settings** ➔ **Domains & Routes** ➔ **Add route**：
   - 路由 1：`tabijiapp.com/api*`，區域選擇 `tabijiapp.com`
   - 路由 2：`www.tabijiapp.com/api*`，區域選擇 `tabijiapp.com`

---

### 階段 5：Supabase 認證白名單配置（OAuth 登入不失效）
> 目的：確保 Google 第三方登入與 Email 驗證在 `tabijiapp.com` 上順利回跳。

1. 登入 [Supabase Dashboard](https://supabase.com/dashboard) ➔ 專案 `oudnkmigfueuyvxqpqwn`。
2. 點選 **Authentication** ➔ **URL Configuration** ➔ **Redirect URLs** ➔ **Add URL**：
   - `https://tabijiapp.com/**`
   - `https://tabijiapp.com/auth/callback`
   - `https://www.tabijiapp.com/**`
   - `https://www.tabijiapp.com/auth/callback`
3. 點選 **Save** 儲存。

---

## 驗收清單 (Verification Checklist)

- [ ] **舊站獨立運作**：訪問 `https://travel-pwa-five.vercel.app`，所有 API 正常響應。
- [ ] **新站 SSL 安全鎖**：訪問 `https://tabijiapp.com`，顯示 Cloudflare 安全綠色鎖頭。
- [ ] **Cloud Run 穿透正常**：訪問 `https://tabijiapp.com/api/health` 回傳 JSON，帶有 `X-Edge-Shield: Cloudflare-Worker-Active`。
- [ ] **AI 串流打字**：測試行程生成或聊天助手，文字流暢逐字輸出無緩衝。
- [ ] **Cloudinary 收據辨識**：上傳圖片簽章不報 404。
- [ ] **Supabase 登入**：Google 帳號登入成功回跳至主頁。
