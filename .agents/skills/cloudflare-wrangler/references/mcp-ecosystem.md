# 🌐 Cloudflare MCP 生態體系與調度全指南

> **本文件定位**：延遲載入參考手冊 (On-Demand Reference)。當 Agent 需要調度 Cloudflare MCP 服務、評估 Token 開銷或配置本機/遠端連接時查閱。  
> **官方權威來源**：
> - [`cloudflare/mcp`](https://github.com/cloudflare/mcp) — 官方 Code Mode 伺服器 (`mcp.cloudflare.com`)
> - [`cloudflare/mcp-server-cloudflare`](https://github.com/cloudflare/mcp-server-cloudflare) — 官方領域特定伺服器與本地 Stdio 伺服器

---

## 1. Cloudflare MCP 三大架構型態

Cloudflare 官方在 2025~2026 年形成了三大 MCP 體系，其 Token 開銷與適用場景如下表：

| 體系名稱 | 實現庫 / 端點 | 工具數 | Token 成本 (上下文佔比) | 最佳使用場景 |
| :--- | :--- | :---: | :---: | :--- |
| **Code Mode 遠端** | `https://mcp.cloudflare.com/mcp` | **3** (`docs`, `search`, `execute`) | **~1,100** tokens (0.5%) | **跨產品未知端點探索**、廣泛 API 調用、全域資源排查 |
| **本機 Stdio 伺服器** | `@cloudflare/mcp-server-cloudflare` | **89** (依產品分組 typed tools) | **已掛載 IDE** (本地進程) | **專案日常資源操作**（D1 查詢、KV 讀寫、R2 物件、Worker 部署） |
| **領域特定遠端** | `https://<domain>.mcp.cloudflare.com/mcp` | 專屬領域 typed tools | 中等 (依各服務而定) | **深入單一專屬功能**（如 `docs` 文檔、`browser` 渲染、`observability` 日誌） |

---

## 2. 官方 Code Mode 伺服器 (`mcp.cloudflare.com/mcp`) 深入指南

### 2.1 核心機制 (Dynamic Worker Loader)
Cloudflare OpenAPI 規格超過 **2,000,000 tokens**，若以傳統 MCP 逐一宣告 2,594 個工具，即使最小化 schema 也高達 **244,047 tokens**（直接爆掉標準 200k 上下文）。  
Code Mode 將 OpenAPI 完整規格留存在 Cloudflare 邊緣伺服器端，由 Agent 撰寫 JavaScript 代碼在獨立沙盒 Worker 中執行比對與 API 調用，僅回傳運算結果，達成 **1,100 tokens 掌控 2,500+ 端點**。

### 2.2 三大核心工具語法

#### ① `docs`: 檢索 Cloudflare 官方開發者文檔
```javascript
docs({
  query: "workers KV get with metadata"
})
```

#### ② `search`: 在邊緣沙盒中以 JavaScript 比對 `spec.paths`
```javascript
search({
  code: `async () => {
    const results = [];
    for (const [path, methods] of Object.entries(spec.paths)) {
      for (const [method, op] of Object.entries(methods)) {
        if (op.tags?.some(t => t.toLowerCase() === 'workers')) {
          results.push({
            method: method.toUpperCase(),
            path,
            summary: op.summary
          });
        }
      }
    }
    return results;
  }`
});
```

#### ③ `execute`: 在邊緣發起認證 API 請求
```javascript
// 方式 A: User Token (必須傳入 account_id)
execute({
  code: `async () => {
    const response = await cloudflare.request({
      method: "GET",
      path: \`/accounts/\${accountId}/workers/scripts\`
    });
    return response.result;
  }`,
  account_id: "your-account-id"
});

// 方式 B: Account Token (account_id 自動由伺服器端識別)
execute({
  code: `async () => {
    const response = await cloudflare.request({
      method: "GET",
      path: \`/accounts/\${accountId}/workers/scripts\`
    });
    return response.result;
  }`
});
```

### 2.3 GraphQL Analytics 呼叫標準
針對分析類統計資料，透過 `execute` 呼叫 `/client/v4/graphql`：
```javascript
execute({
  code: `async () => {
    const response = await cloudflare.request({
      method: "POST",
      path: "/client/v4/graphql",
      body: {
        query: \`query {
          viewer {
            zones(filter: { zoneTag: "your-zone-id" }) {
              httpRequests1dGroups(limit: 7, orderBy: [date_ASC]) {
                dimensions { date }
                sum { requests bytes cachedBytes }
              }
            }
          }
        }\`,
        variables: {}
      }
    });
    return response.result;
  }`,
  account_id: "your-account-id"
});
```

### 2.4 安全與熔斷守則
- 🚨 **嚴禁無故附加 `?codemode=false`**：此參數會強行將 2,594 個端點全部展開為獨立工具，立即灌入 244,000+ tokens，造成上下文崩潰。
- 💡 **結果截斷機制 (`?truncateToolResult`)**：預設伺服器會將回傳結果限制在 ~6,000 tokens 並保持有效 JSON。若 Agent 內部具備後處理過濾器且需要完整資料，可附加 `?truncateToolResult=false`，但必須自負記憶體消耗。

---

## 3. 官方 15 大領域特定遠端 MCP 端點總表

由 [`cloudflare/mcp-server-cloudflare`](https://github.com/cloudflare/mcp-server-cloudflare) 維護，統一採用 Streamable HTTP 協定（基於 `/mcp`，舊版 `/sse` 會返回 410 Gone）：

| 服務名稱 | 遠端 MCP URL | 核心能力 |
| :--- | :--- | :--- |
| **Documentation** | `https://docs.mcp.cloudflare.com/mcp` | 官方產品最新文檔與架構指南 |
| **Workers Bindings**| `https://bindings.mcp.cloudflare.com/mcp` | Workers 儲存、AI 與運算 Primitive 綁定 |
| **Workers Builds**  | `https://builds.mcp.cloudflare.com/mcp` | 檢視與管理 Cloudflare Workers Builds |
| **Observability**   | `https://observability.mcp.cloudflare.com/mcp` | 查詢應用程式即時日誌與分佈式遙測 |
| **Containers**      | `https://containers.mcp.cloudflare.com/mcp` | 啟動邊緣沙盒容器開發環境 |
| **Browser Run**     | `https://browser.mcp.cloudflare.com/mcp` | 邊緣無頭瀏覽器爬取、轉 Markdown 與截圖 |
| **Logpush**         | `https://logs.mcp.cloudflare.com/mcp` | Logpush 作業健康狀態與日誌推送摘要 |
| **AI Gateway**      | `https://ai-gateway.mcp.cloudflare.com/mcp` | 搜尋 AI Gateway 日誌、Prompt 與回應延遲 |
| **AutoRAG**         | `https://autorag.mcp.cloudflare.com/mcp` | 查詢帳戶 AutoRAG 向量知識庫實例 |
| **DNS Analytics**   | `https://dns-analytics.mcp.cloudflare.com/mcp` | DNS 解析效能優化與異常排查 |
| **DEX (體驗監控)**  | `https://dex.mcp.cloudflare.com/mcp` | 企業關鍵應用程式網路體驗分析 |
| **CASB**            | `https://casb.mcp.cloudflare.com/mcp` | SaaS 應用程式安全配置偏差掃描 |
| **Radar**           | `https://radar.mcp.cloudflare.com/mcp` | 全球網際網路流量趨勢與威脅洞察 |
| **Cloudflare Blog** | `https://blog.mcp.cloudflare.com/mcp` | 搜尋與閱讀 Cloudflare 官方部落格技術文章 |
| **Demo Day**        | `https://demo-day.mcp.cloudflare.com/mcp` | 最小化 Cloudflare MCP 伺服器示範 |

---

## 4. 本機 Stdio MCP 伺服器 (`@cloudflare/mcp-server-cloudflare`) 規格

### 4.1 核心參數不變性 (Parameter Invariance)
在 IDE 或全域配置 `mcp_config.json` 時，必須遵循嚴格的啟動參數格式：

```json
{
  "mcpServers": {
    "cloudflare": {
      "command": "npx",
      "args": [
        "-y",
        "@cloudflare/mcp-server-cloudflare",
        "run",
        "<YOUR_ACCOUNT_ID>"
      ],
      "env": {
        "CLOUDFLARE_API_TOKEN": "<YOUR_API_TOKEN>"
      }
    }
  }
}
```

> ⚠️ **高危陷阱警告**：
> 1. 若漏掉 `"run"` 指令，npx 啟動時會拋出 `Error: Unknown command: undefined. Expected 'init' or 'run'` 並引發 EOF 斷線。
> 2. 若僅填 `["run"]` 未在指令後方傳入 `<YOUR_ACCOUNT_ID>`，套件內部 `dist/index.js` 會將 `config.accountId` 覆寫為 `undefined`，進而退回尋找 `~/.wrangler/config/default.toml` 拋出檔案不存在例外。因此指令末端必須顯式帶入 Account ID！

### 4.2 本地 Stdio 常用高頻工具速查
已在 IDE 註冊之 89 項工具中，最核心的 6 大維度：
- **Workers 部署與管理**: `worker_list`, `worker_get`, `worker_put`, `worker_deploy`, `worker_delete`
- **D1 關聯式 SQL**: `d1_list_databases`, `d1_create_database`, `d1_query`
- **KV 鍵值儲存**: `kv_list`, `kv_get`, `kv_put`, `kv_delete`
- **R2 物件儲存**: `r2_list_buckets`, `r2_create_bucket`, `r2_get_object`, `r2_put_object`
- **Workers AI 推理**: `ai_list_models`, `ai_inference`, `ai_text_generation`, `ai_embeddings`
- **網路與 DNS**: `zones_list`, `zones_get`, `domain_list`, `route_list`
