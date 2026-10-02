---
name: "Cloudflare Edge & Wrangler Master"
description: "Master guide for Cloudflare MCP Server (Code Mode) and Wrangler CLI. Orchestrates edge workers, Miniflare local testing, zero-cost reverse proxies, and remote Cloudflare API operations."
version: "1.0.0"
triggers:
  - "cloudflare"
  - "wrangler"
  - "edge proxy"
  - "workers"
  - "cf"
---

# Cloudflare Edge & Wrangler Master Skill

## 1. 核心定位與雙軌體系
- **遠端感知神經 (Cloudflare MCP Server)**: `https://mcp.cloudflare.com/mcp` (Code Mode: `docs`, `search`, `execute`)，僅佔 ~1,100 tokens 即可操作全域 2,594 個 API。
- **本地執行手臂 (Wrangler CLI)**: `npx wrangler`，走本地命令列（零 Token 開銷），負責代碼編譯、Miniflare 本地 V8 模擬測試與確定性部署。
- **本機 Stdio 伺服器 (@cloudflare/mcp-server-cloudflare)**: 若在 `mcp_config.json` 採用 stdio 啟動，`args` 必須明確傳入 `["-y", "@cloudflare/mcp-server-cloudflare", "run", "<account-id>"]`。若漏傳 `run` 會引發 `Unknown command: undefined`；若僅傳 `run` 未帶 `account_id`，套件內部會將 `config.accountId` 覆寫為 `undefined` 並退回尋找 `default.toml` 拋出檔案不存在例外。

## 2. Wrangler CLI 本地常用指令速查

```bash
# 檢查目前身分與帳戶
npx wrangler whoami

# 產生 TypeScript 綁定型別
npx wrangler types

# 啟動本地 Miniflare 沙盒除錯 (零網路延遲測試)
npx wrangler dev --port 8787

# 設置安全 Secret (防爬反代密鑰)
echo "secret_value" | npx wrangler secret put PROXY_SECRET

# 部署至 Cloudflare 全球 300+ 邊緣節點
npx wrangler deploy
```

## 3. Cloudflare MCP Server (Code Mode) 呼叫標準

當連接至 `https://mcp.cloudflare.com/mcp` 時，**嚴禁開啟 `?codemode=false`**（會灌入 244,000+ tokens 導致 Context 爆滿）。
應使用 Code Mode 標準三步法：

1. **搜尋端點**:
   ```javascript
   search({
     code: `async () => {
       const res = [];
       for (const [p, ops] of Object.entries(spec.paths)) {
         if (p.includes("workers/scripts")) res.push({ path: p, ops: Object.keys(ops) });
       }
       return res;
     }`
   })
   ```
2. **執行請求**:
   ```javascript
   execute({
     code: `async () => {
       const res = await cloudflare.request({
         method: "GET",
         path: \`/accounts/\${accountId}/workers/scripts\`
       });
       return res.result;
     }`
   })
   ```

## 4. Tabidachi 搜尋邊緣代理規範 (Tier 2)
- 代理腳本路徑: `cloudflare/search-proxy/worker.js`
- 目的: 將 GCP Cloud Run 的機房 IP 請求洗白為 Cloudflare 全球 Anycast 邊緣 IP，攻破 DuckDuckGo 403 阻斷。
- 部署後需在 Cloud Run 環境變數注入: `DDGS_PROXY=https://<worker-subdomain>.workers.dev`
