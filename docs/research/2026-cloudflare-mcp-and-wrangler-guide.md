# Cloudflare 官方 MCP Server 與 Wrangler CLI 雙軌架構深度研究報告 (2026)

> **目標**: 剖析 Cloudflare 官方 Model Context Protocol (MCP) Server (`https://mcp.cloudflare.com/mcp`) 與 Wrangler CLI 在 AI Agent 開發體系中的實際運作機制、原始碼邏輯、工程陷阱與雙軌協同最佳實踐。
> **適用場景**: Tabidachi 邊緣檢索代理部署、Cloudflare Worker 治理、無伺服器架構零成本穿透。

---

## 一、 核心技術流程 (Core Technical Execution Flow)

Cloudflare 在 2026 年建立了以 **Model Context Protocol (MCP)** 為核心的邊緣 AI 代理架構。針對 Cloudflare 全球 API 龐大的 2,594 個 Endpoints，官方採用了創新的 **Code Mode** 模式，與本機端 **Wrangler CLI** 形成互補的雙軌協同體系。

### 1. Cloudflare MCP Server 架構與「Code Mode」運作流

```
[AI Agent / LLM Context]
         │
         ├── 1. search({ code: "find worker endpoints" })
         │      │
         │      ▼
         │   [Cloudflare MCP Server (https://mcp.cloudflare.com/mcp)]
         │      │  (動態在隔離 V8 Worker 中執行搜尋代碼)
         │      ▼
         │   [檢索 2,594 個 OpenAPI Schema 定義]
         │      │
         │◄─────┴── 返回過濾後的精確 API 路徑 (~200 tokens)
         │
         ├── 2. execute({ code: "cloudflare.request(...)" })
         │      │
         │      ▼
         │   [Cloudflare API Gateway] ── (驗證 API Token / OAuth)
         │      │
         │◄─────┴── 返回 API 執行結果 (預設自動截斷保護在 ~6,000 tokens)
```

#### Token 消耗對比矩陣 (Why Code Mode Matters)
| 整合方式 | 工具數量 (Tools) | Token 消耗 | 佔 200K 上下文比例 |
| :--- | :--- | :--- | :--- |
| 原始 OpenAPI Spec 注入 Prompt | 0 | ~2,000,000 | 977% (直接爆表) |
| 原生 MCP (完整 Schema 暴露) | 2,594 | 1,170,523 | 585% (無法運行) |
| 原生 MCP (最小必要參數模式) | 2,594 | 244,047 | 122% (超過單次上下文) |
| **Cloudflare Code Mode (現行預設)** | **3** (`docs`, `search`, `execute`) | **~1,100** | **0.5% (極致輕量)** |

#### 核心三工具職責：
1. `docs`: 直接語意檢索 Cloudflare 官方最新開發者文件。
2. `search`: Agent 撰寫一段 JavaScript 程式碼，在遠端隔離記憶體中查詢 `spec.paths`，定位精確的 API 路徑與參數規格。
3. `execute`: Agent 撰寫呼叫 `cloudflare.request({ method, path, body })` 的 JavaScript 代碼，由 MCP Server 代理向 Cloudflare 核心 API 發起呼叫。

---

### 2. Wrangler CLI 本地工程管線

相較於 MCP Server 的「遠端宣告與感知」，Wrangler CLI（v3/v4）是 AI Agent 進行「本地代碼建構、虛擬沙盒模擬與確定性發布」的實體工具。

```
[Agent 本地產生 Worker 代碼 (worker.js)]
         │
         ▼
[Wrangler 本地驗證] ── `npx wrangler types` (產生 TS 型別契約)
         │
         ▼
[Miniflare V8 本地沙盒] ── `npx wrangler dev --test-scheduled` (本機單元測試)
         │
         ▼
[全域發布與密鑰注入] ── `npx wrangler secret put DDGS_SECRET` + `npx wrangler deploy`
```

---

### 3. MCP Server 與 Wrangler CLI 雙軌協作矩陣

| 維度 | Cloudflare MCP Server (`https://mcp.cloudflare.com/mcp`) | Wrangler CLI (`npx wrangler`) |
| :--- | :--- | :--- |
| **運行位置** | 雲端託管 / 遠端 Edge Worker | 開發機 / 容器本地 Terminal |
| **主要定位** | **指揮官與感知神經** (動態查資源、狀態審計、即時配置) | **工匠與執行手臂** (代碼打包、本地模擬、版本化發布) |
| **Token 開銷** | 極小 (~1,100 tokens 覆蓋全域 2,500+ API) | 零 Token (走本機 CLI 指令標準輸出) |
| **適用時機** | 查詢即時 DNS、列出線上 Worker 運行狀態、讀取 D1/KV 資料 | 建立專案骨架、編譯 TypeScript、本機除錯、CI/CD 部署 |
| **安全邊界** | 依賴 Bearer Token 或 OAuth 權限範圍 | 依賴本地 `CLOUDFLARE_API_TOKEN` 與 `CLOUDFLARE_ACCOUNT_ID` |

---

## 二、 網路技術大神爭議點與踩坑指南 (Ground Truth & Field Reports)

### 爭議點 1：「把 MCP 連上 Agent 就能自動管理一切？」
* **真相與陷阱**：
  * **陷阱 A (權限漂移與抹除風險)**：若直接給予 Agent 具有 `Administrator` 權限的 API Token，當 Agent 出現幻覺執行 `execute()` 時，可能意外觸發 `DELETE /zones/{id}` 或清除生產環境的 KV Namespace。
  * **避坑解法**：遵循「最小權限原則 (Least Privilege)」。為 Agent 頒發專屬 Token，僅開放 **Workers Scripts: Edit**、**D1: Edit**、**Account Analytics: Read**。
  * **陷阱 B (Client IP 限制失效)**：Cloudflare 官方明確標註：**「目前 MCP Server 不支援開啟了『Client IP Filtering』的 API Token」**。若在 Cloudflare 後台限制了 Token 的連線 IP，MCP Server 連線時會回傳 401 認證失敗。

### 爭議點 2：「關閉 Code Mode (`?codemode=false`) 是否更直觀？」
* **技術真相**：
  * 社群中有部分開發者為了讓 Agent 介面顯示如 `create_worker`、`list_dns_records` 等具體名稱工具，在 URL 後加上 `?codemode=false`。
  * **致命後果**：一旦加上 `?codemode=false`，MCP Server 會一次性向 Agent 註冊 **2,594 個獨立工具**，光是工具的 JSON Schema 定義就瞬間灌入 **244,000+ tokens**。這會直接吃滿 Claude 3.5 / Gemini 1.5 的 Context Window，導致對話延遲暴增、推論費用劇增甚至直接拒絕服務。
  * **避坑結論**：**絕對強制保留 Code Mode 預設狀態**。

### 爭議點 3：「2026 年 `workerd` 沙盒逃逸與安全修復」
* **底層漏洞考證**：
  * 2026 年中資安研究員曾揭露在特定版本的 `workerd` (Cloudflare Worker 本地與雲端執行期) 存在記憶體越界與沙盒逃逸隱患。
  * **現狀**：官方託管的 `https://mcp.cloudflare.com/mcp` 已在雲端即時熱修復；若開發者在自建環境運行自託管 MCP，必須確保 `workerd` 版本高於 `v1.20260619.1`。

### 爭議點 4：「Stateless HTTP vs 傳統 SSE 連線斷線」
* **協定演進**：
  * 2026 年 MCP 規格已全面支援 Stateless HTTP POST 傳輸，取代容易因反向代理超時而中斷的長連線 SSE (Server-Sent Events)。
  * 若使用舊版 MCP Client 嘗試以舊式 SSE 握手，可能遇到 OAuth Token 無法持久化而反覆要求登入的問題。

---

## 三、 GitHub 原始碼層級驗證 (Source-Level Audits)

### 1. `cloudflare/mcp` 官方核心結構解析

官方開源倉庫 [cloudflare/mcp](https://github.com/cloudflare/mcp) 的關鍵機制：
* **Code Mode Dynamic Runner**：
  伺服器內部整合了動態 Worker 載入器（Dynamic Worker Loader）。當 Agent 呼叫 `execute()` 時，伺服器並非使用 Node.js 的 `eval()`，而是將代碼注入一個拋棄式的輕量 `workerd` 隔離環境中執行，確保隔離性。
* **輸出截斷保護機制 (`truncateToolResult`)**：
  預設將每個工具的回傳結果嚴格限制在 **~6,000 tokens** 內，並保持 JSON 結構完整（長字串截斷、陣列保留前項），防止大容量 API Response 撐爆 Agent 記憶體。

### 2. Tabidachi 專案落地：Cloudflare Edge 檢索代理 (`worker.js`)

利用 Wrangler 與 Cloudflare Worker 免費方案（每天 100,000 次），為 Tabidachi 的 GCP Cloud Run 提供無阻斷的搜尋邊緣轉發：

```javascript
/**
 * Tabidachi 零成本搜尋轉發代理 (Cloudflare Worker)
 * 作用：將 Cloud Run 的機房 IP 請求，轉換為 Cloudflare 全球 Anycast 邊緣 IP
 */
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // 簡易安全金鑰驗證 (防範未授權盜用配額)
    const authHeader = request.headers.get("x-tabidachi-key");
    if (env.PROXY_SECRET && authHeader !== env.PROXY_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    // 提取目標網址：/proxy?url=https%3A%2F%2Flite.duckduckgo.com%2Flite%2F
    const targetUrl = url.searchParams.get("url");
    if (!targetUrl) {
      return new Response("Missing target url parameter", { status: 400 });
    }

    // 複製原始請求標頭，抹除 Cloud Run 專屬特徵
    const newHeaders = new Headers(request.headers);
    newHeaders.delete("x-tabidachi-key");
    newHeaders.delete("host");
    newHeaders.set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36");

    const init = {
      method: request.method,
      headers: newHeaders,
      body: request.method !== "GET" && request.method !== "HEAD" ? await request.arrayBuffer() : null,
      redirect: "follow",
    };

    try {
      const response = await fetch(targetUrl, init);
      const modifiedResponse = new Response(response.body, response);
      // 支援前端跨域除錯
      modifiedResponse.headers.set("Access-Control-Allow-Origin", "*");
      return modifiedResponse;
    } catch (err) {
      return new Response(JSON.stringify({ error: err.message }), {
        status: 502,
        headers: { "Content-Type": "application/json" }
      });
    }
  }
};
```

#### Wrangler 快速部署指令 (CI/CD / Agent 本地執行)
```bash
# 1. 建立輕量 worker 目錄與設定
npx wrangler init tabidachi-search-proxy --yes

# 2. 設置防盜刷密鑰 (可選)
echo "my_super_secret_key" | npx wrangler secret put PROXY_SECRET

# 3. 發布至全球邊緣網絡 (秒級完成)
npx wrangler deploy
```

---

## 四、 總結：AI Agent 最佳工具協同指南

1. **雲端架構治理與審計**：使用 **Cloudflare MCP Server (`https://mcp.cloudflare.com/mcp`)**，維持 Code Mode，Agent 僅需 ~1,100 tokens 即可即時監控 Cloudflare 帳戶下的 Workers、DNS 與 Analytics。
2. **邊緣代碼構建與發布**：使用 **Wrangler CLI** 本地指令 (`npx wrangler deploy`)，由 Agent 撰寫代碼、本地透過 Miniflare 測試後確定性發布。
3. **Tabidachi 生產運行**：在 Cloud Run 環境變數中掛載 Worker 代理位址（例如 `DDGS_PROXY=https://tabidachi-proxy.yourname.workers.dev`），零成本攻破資料中心 IP 封鎖，完美實現 Tier 1 ➔ Tier 2 ➔ Tier 4 的高可用性閉環。
