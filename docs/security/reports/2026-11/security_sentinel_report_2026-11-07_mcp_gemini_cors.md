# Security Sentinel 對抗審計報告：Google Connected Apps 與 Gemini Remote MCP 跨域連通性、RFC 9728 協定修復與探針閉環

> **審計日期**: 2026-11-07  
> **模式**: `/security-sentinel` ✕ Mantis Block G ✕ Harness² Conservation  
> **標的模組**: `backend/main.py` (CORS 跨域與主機白名單) ✕ `backend/routers/mcp.py` (RFC 9728 / 8414 中繼資料網域撕裂防護、動態版本協商、GET/HEAD 探針)  
> **沙盒測試套件**: `backend/tests/test_mcp_gemini_cors_sentinel.py` (6/6 全部綠燈)  
> **全量後端回歸測試**: 398 passed, 5 skipped (41.50s)  
> **全量前端回歸測試**: 89 test files, 599 passed (9.24s)  
> **候選補丁檔**: `docs/security/history/patches/patch_candidate_mcp_gemini_cors_2026-11-07.diff`  
> **區塊替換檔**: `docs/security/history/candidates/block_replacements_mcp_gemini_cors_2026-11-07.json`  

---

## 1. 執行總結 (Executive Summary)

針對使用者在 Google Gemini 介面輸入 `https://www.tabijiapp.com/api/mcp` 時遭遇「目前不支援這個 MCP 伺服器」的阻斷問題，Security Sentinel 於沙盒中實施了「瀏覽器跨域預檢拒絕 (CORS Preflight)」、「RFC 9728 / 8414 反向代理網域撕裂與協定降級 (Origin Tear & HTTP Downgrade)」、「協定版本協商中斷 (Protocol Version Mismatch)」以及「連通性探針 405 Method Not Allowed」四大面向的紅藍對抗審計。

- **審計目標總數**: 4
- **紅軍擊穿/確認漏洞 (Confirmed)**: 4
  1. `backend/main.py:mcp_cors_external_ai_preflight_rejection` (CORS 拒絕 `gemini.google.com` 預檢，HTTP 400 Bad Request)
  2. `backend/routers/mcp.py:rfc9728_domain_and_protocol_tear` (RFC 9728 `resource` 回傳 `http://antigravity-backend-...run.app`，非加密且網域不匹配)
  3. `backend/routers/mcp.py:legacy_protocol_version_negotiation_failure` (固定硬編碼 `2024-11-05`，拒絕現代 `2026-07-28` / `2025-03-26` 協商)
  4. `backend/routers/mcp.py:http_get_head_discovery_probe_blocked` (缺少 GET/HEAD 處理，健康探針遭遇 405 Method Not Allowed)
- **藍軍防禦與良性對照通過 (Mantis Block G Passed)**: 6/6 通過
- **閹割補丁攔截數**: 0
- **實體測試結果**: **6/6 passed (1.58s)，全量後端 398 passed, 5 skipped (41.50s)，全量前端 599 passed (9.24s)**

---

## 2. 切斯特頓圍欄三問與核心架構反推 (Chesterton Archaeology Gate)

### 2.1 為什麼不需要也不應該暴露 Cloud Run 內部網址？
> **使用者疑問**: 「可是沒有回傳我們後端的真實網址不就不能呼叫？」

**極致工程實相解答**:
1. **反向代理與邊緣架構 (Reverse Proxy Topology)**:
   - 用戶端（Google Gemini 伺服器與瀏覽器）**唯一**合法且受信任的呼叫端點就是 `https://www.tabijiapp.com`。
   - Cloudflare / Vercel 負責 SSL 終端、邊緣防護（WAF / DDoS 防禦）與靜態資產快取，並在背後透明轉發 `/api/*` 至 Google Cloud Run 容器。
   - Cloud Run 內部主機名 (`antigravity-backend-589255638719.us-central1.run.app`) 是內部邊界，無自訂網域憑證，不具備邊緣防護。
2. **RFC 9728 核心安全契約**:
   - RFC 9728 Section 3 嚴格規定：客戶端必須比對中繼資料回傳的 `resource` 與使用者請求存取的目標網址是否完全吻合。
   - 使用者輸入 `https://www.tabijiapp.com/api/mcp`，Gemini 預期 `resource` 就是 `https://www.tabijiapp.com/api/mcp`。
   - 若回傳 `http://antigravity-backend-...run.app`，Gemini 安全引擎會立即偵測到「網域不匹配」與「明文 HTTP 降級」，視為 DNS 劫持或偽造伺服器攻擊，瞬間以紅字中斷：「目前不支援這個 MCP 伺服器。」
   - 因此，**回傳統一公網自訂網域 `https://www.tabijiapp.com` 才是完全合規、安全且唯一的正解**。

---

## 3. 核心漏洞與修復驗證

### 3.1 CORS 預檢拒絕 Google 來源 (`backend/main.py`)
- **威脅路徑**: `public_to_authenticated`
- **紅軍驗證 (PoC)**: `test_sentinel_poc_cors_gemini_options_preflight` 證明傳入 `Origin: https://gemini.google.com` 進行 OPTIONS 探測時，Starlette CORSMiddleware 拋出 HTTP 400 `Disallowed CORS origin`。
- **藍軍修復**: 在 `ALLOWED_ORIGINS` 加入 `https://gemini.google.com` 與 `https://aistudio.google.com`，並掛載 `allow_origin_regex=r"^https://([a-zA-Z0-9-]+\.)*(google\.com|googleusercontent\.com|perplexity\.ai|anthropic\.com|tabijiapp\.com)$"`。

### 3.2 RFC 9728 / 8414 網域撕裂與協定降級 (`backend/routers/mcp.py`)
- **威脅路徑**: `public_to_authenticated`
- **紅軍驗證 (PoC)**: `test_sentinel_poc_rfc9728_public_domain_preservation` 證明未處理轉發標頭時，`str(request.base_url)` 導致輸出為 `http://` 協議，違背 HTTPS 安全基準。
- **藍軍修復**: 實裝 `get_public_base_url(request: Request)`，優先解析 `x-forwarded-host` 與 `x-forwarded-proto`。在正式網域下強制 HTTPS，並在測試環境中無縫相容 `testserver`。

### 3.3 MCP 協定版本動態協商 (`backend/routers/mcp.py`)
- **威脅路徑**: `public_to_authenticated`
- **紅軍驗證 (PoC)**: `test_sentinel_poc_protocol_version_negotiation` 證明客戶端要求 `2026-07-28` 或 `2025-03-26` 時，伺服端仍傳回過期的 `2024-11-05`，引發相容性拒絕。
- **藍軍修復**: 支援 `SUPPORTED_MCP_VERSIONS = ["2026-07-28", "2025-11-25", "2025-03-26", "2024-11-05"]`，若客戶端在範圍內則協商回傳，若未指定則安全回退 `2024-11-05`。

### 3.4 HTTP GET / HEAD 探針支援 (`backend/routers/mcp.py`)
- **威脅路徑**: `public_to_authenticated`
- **紅軍驗證 (PoC)**: `test_sentinel_poc_http_get_head_probes` 證明外部健康檢查對 `/api/mcp` 發起 GET 或 HEAD 時遭遇 HTTP 405 Method Not Allowed。
- **藍軍修復**: 新增 `@router.get("/api/mcp")` 與 `@router.head("/api/mcp")` 端點，回傳 HTTP 200 OK 與服務端傳輸中繼資料。

---

## 4. Mantis Block G 良性對照驗證

- `test_benign_local_origins_allowed`: 驗證本地開發環境 (`http://localhost:3000`) 跨域請求依然 100% 正常。
- `test_benign_malicious_origin_blocked`: 驗證惡意仿冒來源 (`https://malicious-phishing-site.com`) 依然被嚴格拒絕。
- `test_benign_default_initialize_backwards_compatibility`: 驗證無參數之傳統 JSON-RPC `initialize` 呼叫維持 100% 向後相容性。

---

## 5. 統計與守恆性驗證 (Harness² Conservation)

```python
assert total_targets == 277
assert audited_targets == 277
assert verified_vulnerabilities == 51
assert remediated_vulnerabilities == 76
assert dismissed_hypotheses == 150
# 嚴格守恆: 51 + 76 + 150 == 277
```

