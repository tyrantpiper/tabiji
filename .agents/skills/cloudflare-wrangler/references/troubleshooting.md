# 🛠️ Cloudflare Edge 與 Wrangler 實戰踩坑診斷矩陣

> **本文件定位**：延遲載入參考手冊 (On-Demand Reference)。當 Agent 或開發者遇到 Cloudflare 認證異常、MCP 啟動失敗、超時阻斷或快取膨脹等邊界問題時查閱。

---

## 1. 認證與權限陷阱

### 陷阱 1: R2 S3 HMAC 憑證混淆 (`R2 S3 Token Mismatch Trap`)
- **現象**：使用在 Cloudflare Dashboard 生成的 R2 API Token（包含 Access Key ID, Secret Access Key 與 S3 Endpoint）填入 Wrangler 或 MCP 配置，拋出認證無效或 401 Unauthorized。
- **根因**：R2 專屬憑證僅適用於 AWS S3 相容 SDK（如 boto3, @aws-sdk/client-s3）。Wrangler CLI、Cloudflare REST API 與 MCP 伺服器必須使用以 `cfat_` 開頭的 Account REST API Token。
- **解決方案**：至 [Cloudflare API Tokens](https://dash.cloudflare.com/profile/api-tokens) 使用 `Edit Cloudflare Workers` 範本生成具備 Workers、KV、D1 權限之 REST Token。

---

### 陷阱 2: 本機 Stdio MCP 啟動參數指令缺失與 Account ID 覆寫 (`Stdio Parameter Invariance Trap`)
- **現象**：
  * 情境 A: 啟動 `@cloudflare/mcp-server-cloudflare` 拋出 `Error: Unknown command: undefined. Expected 'init' or 'run'`，客戶端連線立即斷開。
  * 情境 B: 啟動參數僅帶 `["run"]`，雖然已在 `env` 設定 `CLOUDFLARE_ACCOUNT_ID`，但執行時依然報錯找不到 `~/.wrangler/config/default.toml`。
- **根因**：
  * 情境 A 漏掉了必要子命令 `"run"`。
  * 情境 B 中，套件源碼 `dist/index.js` 在解析命令列時執行了 `config.accountId = accountId`。若命令列未在 `"run"` 後方提供參數，它會無條件將環境變數載入的合法 ID 覆寫為 `undefined`，強制退回尋找本機 OAuth 登入檔。
- **解決方案**：
  在 `mcp_config.json` 中嚴格宣告四元素陣列：
  ```json
  "args": ["-y", "@cloudflare/mcp-server-cloudflare", "run", "<YOUR_ACCOUNT_ID>"]
  ```

---

## 2. 網路傳輸與逾時陷阱

### 陷阱 3: DuckDuckGo Tarpit 慢阻斷延遲 (`DuckDuckGo Tarpit Timeout Trap`)
- **現象**：後端呼叫 Cloudflare 邊緣代理時，偶發 10 秒以上 `httpx.ReadTimeout` 導致全鏈路卡死。
- **根因**：DuckDuckGo 會對部分邊緣節點實施 Tarpit（慢速涓流阻斷，每隔數秒傳遞數個字節）。若 Worker 內部的 `fetch()` 沒有掛載超時中斷，會持續等待直到 Worker 平台全域逾時。
- **解決方案**：
  所有外部 fetch 必須強制附加 `signal: AbortSignal.timeout(1500)`：
  ```javascript
  const res = await fetch("https://lite.duckduckgo.com/lite/", {
    signal: AbortSignal.timeout(1500)
  });
  ```

---

### 陷阱 4: CI/CD 單元測試未 Mock Tier 2 邊緣代理穿透 (`Unmocked Tier-2 CI False Negative`)
- **現象**：本機或 GitHub Actions 執行單元測試 `test_execute_web_search_fallback_on_ddgs_error` 拋出 `AssertionError`。
- **根因**：測試原意為驗證 Tier 3 降級，但在測試案例中漏掉了對 Tier 2（Cloudflare Worker）的 Mock；當 Worker 成功上線後，CI 環境直接連網取回了真實維基百科結果，導致流程直接在 Tier 2 返回而未觸發 Tier 3。
- **解決方案**：
  在多級 Fallback 測試中，必須以 `mocker.patch` 對上游所有 Tier 進行完整的獨立 Mock 隔離：
  ```python
  mocker.patch("services.web_search_engine._fetch_cloudflare_edge_search", return_value=[])
  ```

---

## 3. Token 與上下文陷阱

### 陷阱 5: 誤開 `?codemode=false` 灌入 244k Tokens (`Code Mode Context Blowout Trap`)
- **現象**：將 `https://mcp.cloudflare.com/mcp?codemode=false` 加入 MCP Client 後，初次發送訊息即遭遇 `Claude's response was interrupted` 或 LLM 上下文長度超限崩潰。
- **根因**：Cloudflare API 包含 2,594 個端點。關閉 Code Mode 會把所有端點以原生 MCP Tools 註冊，瞬間佔用 244,047 tokens，直接灌爆 200k context window。
- **解決方案**：
  一律採用預設 Code Mode URL：`https://mcp.cloudflare.com/mcp`（僅佔 ~1,100 tokens）。

---

## 4. 儲存與快取陷阱

### 陷阱 6: Safari Opaque Response 快取配額爆炸 (`Safari Opaque Cache Quota Explosion`)
- **現象**：在 iOS Safari PWA 快取景點圖片時，才快取了數十張照片就跳出 `QuotaExceededError`。
- **根因**：瀏覽器出於安全隔離考量，對於無 CORS 標頭的跨域請求（Opaque Response），Cache API 會為其預分配 **7MB ~ 10MB** 的虛擬填充配額（Padding）。
- **解決方案**：
  外部圖片一律透過 Cloudflare Worker 代理，在邊緣注入：
  ```javascript
  headers: {
    "Access-Control-Allow-Origin": "*",
    "Timing-Allow-Origin": "*"
  }
  ```
  使瀏覽器認定為同源或合法 CORS 資源，快取佔用還原為真實二進位大小（~50KB）。

---

### 陷阱 7: Miniflare 本地模擬綁定與 `--remote` 模式漂移 (`Miniflare Storage Emulation Trap`)
- **現象**：執行 `npx wrangler dev` 時，代碼寫入的 KV 或 D1 資料在正式環境查不到；或是本機開發時誤改了線上生產資料。
- **根因**：Wrangler 預設使用 Miniflare 在本機 `.wrangler/state/` 進行純記憶體/本地 SQLite 模擬。只有顯式加上 `--remote` 參數時才會直連 Cloudflare 雲端真實資源。
- **最佳實踐**：
  - 開發與測試一律使用預設本機模式：`npx wrangler dev`。
  - 需要排查線上真實資料時，必須明確標記：`npx wrangler dev --remote`。

---

## 5. 配置與規格陷阱

### 陷阱 8: `wrangler.jsonc` 註解與 JSON 語法相容性 (`JSONC Schema Validation`)
- **現象**：修改 `wrangler.jsonc` 時被某些外部 CI 腳本判定為「Invalid JSON」或報錯意外字元。
- **根因**：`wrangler.jsonc` 支援 JavaScript 風格註解（`//` 與 `/* */`），標準 `JSON.parse()` 無法直接解析。
- **最佳實踐**：
  - 頂部保留官方 Schema 錨點以取得 IDE 自動補全：
    ```jsonc
    {
      "$schema": "https://unpkg.com/wrangler/config-schema.json",
      "name": "my-worker"
    }
    ```
  - CI 腳本若需讀取屬性，請使用 Wrangler 專用命令（如 `npx wrangler whoami`）或專用 JSONC parser。

---

### 陷阱 9: CPU Time 限制 vs Wall Clock Time 混淆 (`Worker CPU Limit vs I/O Hang`)
- **現象**：Worker 處理大量正規表示式或大字串搜尋時拋出 `Worker exceeded CPU limit (10ms / 50ms)`。
- **根因**：免費版 Workers 限制單次請求純 CPU 運算時間為 10ms 或 50ms。等待 `fetch()` 或 `env.KV.get()` 的網路 I/O 時間屬於 Wall Clock Time（不計入 CPU 限額），但正則回溯與巨型迴圈屬於 CPU Time。
- **最佳實踐**：
  避免在 Worker 內執行 ReDoS 風險正則或繁重的二進位圖片編解碼，重型計算交由後端容器處理。

---

### 陷阱 10: 雲端環境變數未注入導致代理降級 (`Missing Environment Variable Degradation`)
- **現象**：後端部署至 Cloud Run 後，所有搜尋依然跌入 Tier 3 或 Tier 4，Tier 2 邊緣代理完全未被調用。
- **根因**：Cloud Run 的環境變數未注入 `CF_WORKER_SEARCH_URL`，導致後端判斷該變數為空而靜默跳過 Tier 2。
- **最佳實踐**：
  在 `.github/workflows/deploy-backend.yml` 宣告並傳遞 `CF_WORKER_SEARCH_URL`，實現部署管線全自動同步。
