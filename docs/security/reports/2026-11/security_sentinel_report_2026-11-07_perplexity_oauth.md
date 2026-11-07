# Security Sentinel 對抗審計報告：Perplexity / Claude / ChatGPT OAuth 2.1 雙模式連通性、Cloud Run 跨實例無狀態換票與欄位自癒閉環

> **審計日期**: 2026-11-07  
> **模式**: `/security-sentinel` ✕ Phase 0 `GitWorktreePool` 物理沙盒預演 ✕ Mantis Block G ✕ Harness² Conservation  
> **標的模組**: `backend/routers/mcp.py` ✕ `backend/main.py` ✕ `frontend/components/ai/mcp-connector-dialog.tsx`  
> **物理沙盒路徑**: `.worktrees/sentinel-397ba29c` (已驗證並安全釋放，主工作區零污染)  
> **沙盒測試套件**: `backend/tests/test_mcp_perplexity_oauth_sentinel.py` (補丁前 5/5 擊穿紅燈 `exit code 1` ➔ 補丁後 8/8 全數綠燈 `exit code 0`)  
> **沙盒 MCP 回歸測試**: 55/55 passed (4.98s)  
> **沙盒前端測試與型別檢查**: Vitest `10/10 passed` (2.53s) ✕ `tsc --noEmit` (`Exit Code: 0`)  
> **候選補丁檔**: `docs/security/history/patches/patch_candidate_perplexity_oauth_2026-11-07.diff`  
> **區塊替換檔**: `docs/security/history/candidates/block_replacements_perplexity_oauth_2026-11-07.json`  

---

## 1. 執行總結 (Executive Summary)

針對使用者在 Perplexity 連接 Tabiji MCP 時，於「OAuth 模式」遭遇 `{"detail":"Invalid redirect_uri: untrusted domain"}` 阻斷，以及全鏈路架構審計所揭露之 5 項深層缺陷，Security Sentinel 在不修改主工作區檔案的前提下，於獨立 `GitWorktreePool` 沙盒完成紅藍軍實彈對抗與補丁驗證：

- **審計目標總數**: 5
- **紅軍擊穿/確認漏洞 (Confirmed)**: 5 (`Pre-Patch Exit Code: 1`)
  1. `backend/routers/mcp.py:perplexity_and_ai_redirect_uri_allowlist_and_https_enforcement` (`is_trusted_redirect_uri` 漏列 `perplexity.ai`、`claude.ai`、`chatgpt.com`，且未阻斷外部網域 `http://` 明文降級)
  2. `backend/routers/mcp.py:oauth_code_cross_instance_state_loss_and_replay_defense` (Cloud Run `max-instances 10` 多實例下，`OAUTH_CODES` 單機記憶體不共享導致跨實例換票 400 失敗)
  3. `backend/routers/mcp.py:oauth_client_id_validation_and_jwt_self_healing` (`oauth_authorize` 未校驗 `client_id` 是否為合法 UUID，亦未在使用者誤填 JWT 時自癒提取 `sub`)
  4. `backend/routers/mcp.py:oauth_token_basic_auth_and_refresh_grant_contradiction` (`oauth_metadata` 宣告支援 `refresh_token`，但 `oauth_token` 拒絕 `refresh_token` 且未解析 RFC 6749 `Authorization: Basic` 標頭)
  5. `backend/main.py:cors_claude_and_chatgpt_origin_preflight` (`allow_origin_regex` 漏列 `claude.ai`、`claude.com`、`chatgpt.com`、`openai.com`)
- **藍軍防禦與良性對照通過 (Mantis Block G Passed)**: 3/3 良性對照 + 5/5 攻擊修復 = **8/8 通過 (`Post-Patch Exit Code: 0`)**
- **統計守恆驗證 (Harness² Conservation)**: `confirmed(5) + dismissed(0) + inconclusive(0) == total_validated(5)`

---

## 2. 切斯特頓圍欄三問與刪除審查 (Chesterton Archaeology & Deletion Audit)

| 變更位置 | 舊邏輯職責 (`legacy_function`) | 設計初衷 (`design_intent`) | 刪除風險與 100% 承接機制 (`regression_risk` & Handover) |
|---|---|---|---|
| `mcp.py:is_trusted_redirect_uri` | 逐一以 `if` 判斷 `google.com`、`googleusercontent.com`、`tabijiapp.com`、`vercel.app`、`localhost`，並允許 `http` 或 `https`。 | 為 Google Gemini Connected Apps 提供首版 Open Redirect 防護。 | **風險**：原本允許外部網域使用明文 `http://`。**承接**：改為 `TRUSTED_REDIRECT_DOMAINS` 元組，完整保留原有全部網域並新增 `perplexity.ai`、`claude.ai`、`claude.com`、`anthropic.com`、`chatgpt.com`、`openai.com`；僅對 `localhost`/`127.0.0.1`/`testserver` 允許 `http`，外部網域一律強制 `https`。 |
| `mcp.py:oauth_authorize` & `oauth_token` (`OAUTH_CODES`) | 產生隨機 `tbj_code_<hex>` 存入單機記憶體 `OAUTH_CODES`，換票時 `OAUTH_CODES.pop(code, None)`。 | 單實例下之 5 分鐘一次性授權碼交換。 | **風險**：既有單元測試 (`test_mcp_real_router.py:665`) 會直接修改 `OAUTH_CODES[code]["expires_at"]` 測試過期。**承接**：完整保留 `OAUTH_CODES` 字典作為第一優先查表（100% 相容既有測試），同時將 `auth_code` 升級為 `tbj_code_<signed_jwt>` 作為跨實例無狀態回退，並以 `CONSUMED_OAUTH_CODES` 阻絕重放攻擊。 |
| `mcp-connector-dialog.tsx:429` | 顯示「在 Headers 加入：Authorization: Bearer <連線憑證>」。 | 引導使用者在 Perplexity 傳入 Bearer Token。 | **風險**：Perplexity UI 無自訂 Headers 欄位。**承接**：更新為同時說明 Perplexity 進階設定中的「API 金鑰 (API Key)」與「OAuth」雙模式填法。 |

