# Cloudflare 帳戶 API 權杖 (Account API Token) 與 CLI (`wrangler` / `cf`) 實戰指南 (2026)

> **前言**: 本文依據 Cloudflare 官方文件 (`developers.cloudflare.com`)、`cloudflare/workers-sdk` 開源代碼庫、2026 年最新統一 CLI (`cf`) 與 Model Context Protocol (MCP) Server 規範整理。針對使用者畫面中正在建立的「帳戶 API 權杖」，提供最權威的權限選擇、避坑指南與 CLI / MCP 落地用法。

---

## 一、 核心概念辨析：帳戶 API 權杖 (Account API Token) vs 使用者 API 權杖 (User API Token)

在 Cloudflare 2025–2026 的 RBAC 權限體系升級中，主要劃分為兩大權杖類型：

| 權杖類型 | 建立路徑 | 作用範圍與生命週期 | 最佳適用場景 |
| :--- | :--- | :--- | :--- |
| **帳戶 API 權杖 (Account API Token)**<br>*(即使用者目前畫面所在之處)* | `管理帳戶 > 帳戶 API 權杖` | **綁定於特定 Account (組織/帳戶)**。<br>權杖歸屬於該帳戶本身，不受單一成員離職或個人 Profile 變更影響。 | **CI/CD 自動化、生產環境容器 (Cloud Run)、無人值守 Agent、團隊協作** |
| **使用者 API 權杖 (User API Token)** | `我的設定檔 > API 權杖` | 綁定於特定使用者個人。<br>可跨多個不同的帳戶授權，但若個人密碼重置或離職，權杖將隨之失效。 | 個人本機開發、跨多組織管理 |

---

## 二、 畫面操作精準指引：該點選哪一個？

檢視使用者畫面上之 6 大範本卡片：

### 推薦選擇：直接點擊【`Edit Cloudflare Workers`】(11 個權限)

#### 為什麼選擇 `Edit Cloudflare Workers`？
此範本是 Cloudflare 官方為 `wrangler` CLI、GitHub Actions CI/CD 與 Workers 生態所預設打造的「最小必要權限 (Least Privilege)」標準範本。它包含：
1. **Workers Scripts**: `Edit` (允許上傳、部署與版本發布)
2. **Workers KV Storage**: `Edit` (允許存取與管理 KV 快取)
3. **Workers D1 / Database**: `Edit` (允許資料庫操作)
4. **Workers Routes**: `Edit` (允許自訂域名與路由綁定)
5. **Workers Tail / Logs**: `Read` (允許串流讀取運行日誌)

> [!IMPORTANT]
> **若同時需要支援 Cloudflare MCP Server (`https://mcp.cloudflare.com/mcp`)：**
> 依據 `cloudflare/mcp` 官方規範，若使用「Account API Token」連線，必須額外具備 **`Account Resources : Read` (帳戶資源 : 讀取)** 權限，否則 MCP Server 無法自動辨識您的 `account_id`。
> **操作方式**：點擊 `Edit Cloudflare Workers` 後，在下方的權限列表中檢查或點選「新增權限」➔ 選擇 `Account` ➔ `Account Settings` / `Account Resources` ➔ 賦予 `Read` 權限。

#### 其他選項為何不推薦？
- ❌ **`Full account and zone access`**: 權限過度氾濫 (Overprivileged)，若 Token 意外洩漏或 Agent 產生幻覺，可能導致整站 DNS 或計費資料遭竄改。
- ❌ **`Read all resources`**: 僅有唯讀權限，`wrangler deploy` 無法發布代碼。
- ❌ **`從頭開始 Custom`**: 適合進階客製化，但在已有標準 Workers 範本時自行挑選容易漏選（例如漏選 KV 或 Routes）。

---

## 三、 CLI 工具 (`wrangler` vs `cf`) 落地使用指南

### 1. `wrangler` CLI (專注於 Workers / Pages 的成熟工具)
取得 Token 後，**完全無需進行瀏覽器互動式登入 (`wrangler login`)**，直接透過環境變數注入：

#### Windows PowerShell 環境配置
```powershell
# 1. 設置環境變數
$env:CLOUDFLARE_API_TOKEN="您的_Account_API_Token"
$env:CLOUDFLARE_ACCOUNT_ID="您的_32位元_Account_ID"

# 2. 驗證連線與權限
npx wrangler whoami
```
若輸出 `Getting User settings... ✨ Successfully logged in with an Account API Token`，即代表授權成功。

#### 核心生產指令
```powershell
# 本地 Miniflare V8 沙盒測試 (零延遲、不消耗雲端額度)
npx wrangler dev

# 寫入邊緣密鑰 (例如 Tabidachi 防盜刷 Secret)
npx wrangler secret put PROXY_SECRET

# 一鍵發布至全球 300+ 邊緣節點
npx wrangler deploy
```

---

### 2. `cf` CLI (2026 全新統一全功能 Cloudflare CLI - Beta)
Cloudflare 於 2026 年推出了涵蓋全 API (2,900+ 操作) 的統一指令列工具 `cf`：
```powershell
# 1. 安裝或免安裝執行
npx cf whoami

# 2. 檢視線上 Workers
npx cf workers list

# 3. 專案遷移 (從 wrangler.jsonc / toml 遷移至 cloudflare.config.ts)
npx cf migrate
```

---

## 四、 Cloudflare 官方 MCP Server 接入配置

在 Antigravity / Claude Desktop / Agent 設定檔中：
```json
{
  "mcpServers": {
    "cloudflare": {
      "type": "http",
      "url": "https://mcp.cloudflare.com/mcp",
      "headers": {
        "Authorization": "Bearer 您的_Account_API_Token"
      }
    }
  }
}
```
* **保持 Code Mode 預設**: 嚴禁在 URL 後加上 `?codemode=false`（避免灌入 244,000+ tokens 導致上下文爆炸）。
* **無 IP 限制要求**: 請確保建立 Token 時未勾選「Client IP Address Filtering」（MCP Server 雲端不支援特定 IP 篩選）。

---

## 五、 Tabidachi 專案整合效益

在 Tabidachi PWA 架構中，配置此 Token 後：
1. **Tier 2 邊緣代理自動化**: Agent 可直接透過 `npx wrangler deploy` 發布 `tabidachi-search-proxy`。
2. **GCP Cloud Run 洗白**: 在 Cloud Run 注入 `DDGS_PROXY=https://<worker-domain>.workers.dev`，徹底終結 DuckDuckGo 在資料中心 IP 的 403 阻斷。
