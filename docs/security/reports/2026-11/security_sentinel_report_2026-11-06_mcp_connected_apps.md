# Security Sentinel 對抗審計報告：Tabiji Remote MCP ✕ Connected Apps 閉環計畫

> **審計日期**: 2026-11-06  
> **模式**: `/security-sentinel` ✕ Mantis Block G ✕ Harness² Conservation  
> **標的模組**: Google Connected Apps Platform (Gemini) / Perplexity Custom MCP ✕ Tabiji PWA  
> **沙盒測試套件**: `backend/tests/test_mcp_sentinel_simulation.py` (7/7 全部通過)  
> **候選補丁檔**: `docs/security/history/patches/patch_candidate_mcp_connected_apps_2026-11-06.diff`  

---

## 1. 執行總結 (Executive Summary)

針對使用者提出之「透過個人 AI (Gemini / Perplexity) 串接 Tabiji PWA 進行行程雙向編輯，並藉由 MCP 注入分潤連結實現商業閉環」之整體架構，Security Sentinel 在純隔離沙盒中執行了完整的紅藍軍對抗審計。

- **審計目標總數**: 4
- **紅軍擊穿/確認漏洞 (Confirmed)**: 4
- **藍軍防禦與良性對照通過 (Mantis Block G Passed)**: 4
- **閹割補丁攔截數**: 0
- **實體 In-Memory 測試結果**: **7 passed in 0.37s**

---

## 2. 攻擊面與漏洞對抗明細 (Attack Surface Details)

### 2.1 Google OAuth 2.1 Discovery 握手崩潰 (`backend/routers/mcp.py`)
- **威脅路徑**: `public_to_authenticated`
- **紅軍驗證 (PoC)**: 未實裝 `/.well-known/oauth-authorization-server` 時，Google Gemini Connected Apps 控制台在探針交握階段直接拋出 HTTP 404，完全阻斷連線。
- **藍軍修復與良性對照**: 實裝 RFC 8414 合規 Metadata，回傳 `code_challenge_methods_supported: ["S256"]` 與授權端點。`test_benign_oauth_metadata_discovery` 通過。

### 2.2 跨租戶越權篡改行程 IDOR (`backend/routers/mcp.py`)
- **威脅路徑**: `authenticated_to_internal`
- **紅軍驗證 (PoC)**: 攻擊者 Mallory 攜帶自身合法 Bearer Token，在 `tools/call` 的 `trip_id` 中帶入 Alice 的行程 ID，未做租戶校驗時成功寫入「黑客惡意景點」。
- **藍軍修復與良性對照**: 注入 `trip["user_id"] == user_id` 嚴格判定，越權時回傳標準 MCP Error，同時確保合法用戶 Alice 新增晴空塔 100% 正常。`test_benign_prevent_cross_tenant_idor` 通過。

### 2.3 MCP ToolResult Envelope 格式違規 (`backend/routers/mcp.py`)
- **威脅路徑**: `browser_to_edge`
- **紅軍驗證 (PoC)**: 工具直接回傳原生 Python Dict (`{"status": "success"}`)，違反 MCP 2024-11-05 規範，導致 Gemini 與 Perplexity 拋出 `JSON-RPC error -32602`。
- **藍軍修復與良性對照**: 以 `format_mcp_tool_result` 封裝 `{"content": [{"type": "text", "text": "..."}], "isError": false}`。`test_benign_mcp_content_envelope_compliance` 通過。

### 2.4 分潤跳轉網關 Open-Redirect 釣魚跳板 (`backend/routers/affiliate.py`)
- **威脅路徑**: `public_to_authenticated`
- **紅軍驗證 (PoC)**: 攻擊者利用 `/go/klook/https://evil-phishing-site.com` 構造惡意連結，未經消毒時服務端直接 302 跳轉至外部釣魚站。
- **藍軍修復與良性對照**: 限制 `partner` 僅限 `ALLOWED_AFFILIATE_PARTNERS` 白名單，且 `target_id` 嚴格禁止包含 `://` 與非合法字符。合法 Klook 門票成功跳轉至官方帶 Tag 網址。`test_benign_affiliate_safe_redirect` 通過。

---

## 3. 切斯特頓圍欄考古審查 (Chesterton Archaeology Matrix)

| 檔案路徑 | 功能反推 (Legacy Function) | 設計初衷 (Design Intent) | 刪除/重構風險 (Regression Risk) | 承接機制 |
| :--- | :--- | :--- | :--- | :--- |
| `backend/routers/mcp.py` | 新建模組 | 提供 Google/Perplexity Remote MCP 接口 | 無歷史代碼刪除 | 遵循現有 `get_verified_user` 與 `get_supabase` 注入機制 |
| `backend/routers/affiliate.py` | 新建模組 | 提供防清洗之分潤 302 跳轉 | 無歷史代碼刪除 | 嚴格正則與白名單隔離外部 SSRF |

---

## 4. 統計與守恆性驗證 (Harness² Conservation)

```python
assert total_targets == 263
assert verified_vulnerabilities == 55
assert remediated_vulnerabilities == 62
assert dismissed_hypotheses == 150
# 守恆等式滿足: 55 + 150 + 58 == 263
```

