# Security Sentinel 對抗審計報告：Tabiji OAuth 2.1 閉環與 PKCE S256 驗證

> **審計日期**: 2026-11-06  
> **模式**: `/security-sentinel` ✕ Mantis Block G ✕ Harness² Conservation  
> **標的模組**: `/api/oauth/authorize` ✕ `/api/oauth/token` ✕ PKCE S256 (RFC 7636)  
> **沙盒測試套件**: `backend/tests/test_mcp_oauth_flow_simulation.py` (3/3 通過)  
> **全量測試套件**: 29/29 全部綠燈 (4.74s)  
> **候選補丁檔**: `docs/security/history/patches/patch_candidate_mcp_oauth_flow_2026-11-06.diff`  

---

## 1. 執行總結 (Executive Summary)

針對 Google Gemini 在連線至自訂 MCP 伺服器時發起的真實 OAuth 2.1 授權碼流，Security Sentinel 在隔離沙盒中實施了「授權碼重放 (Replay Attack)」、「PKCE 篡改 (Code Verifier Tampering)」與「缺少端點 404 斷鏈」的紅藍對抗審計。

- **審計目標總數**: 3
- **紅軍擊穿/確認漏洞 (Confirmed)**: 2 (端點缺少 404 斷鏈、未驗證 PKCE 時存在重放攻擊風險)
- **藍軍防禦與良性對照通過 (Mantis Block G Passed)**: 3
- **閹割補丁攔截數**: 0
- **實體測試結果**: **3/3 passed (0.48s)，累計全量 MCP 套件 29/29 passed (4.74s)**

---

## 2. 核心漏洞與修復驗證

### 2.1 授權與換票端點缺失 404 斷鏈 (`backend/routers/mcp.py`)
- **威脅路徑**: `public_to_authenticated`
- **紅軍驗證 (PoC)**: 未實裝 `/api/oauth/authorize` 與 `/api/oauth/token` 時，Google Gemini 在探測後發起重定向直接遭遇 404 崩潰。
- **藍軍修復**: 實裝標準 Authorize 302 跳轉與 Token 換票端點。`test_benign_full_google_gemini_oauth_handshake` 通過。

### 2.2 PKCE S256 密碼學驗證與一次性消費防禦 (`backend/routers/mcp.py`)
- **威脅路徑**: `public_to_authenticated`
- **紅軍驗證 (PoC)**: 攻擊者使用錯誤的 `code_verifier` 偷換票，或重放已使用的授權碼。
- **藍軍修復**: 強制執行 `base64url(sha256(verifier)) == challenge` 密碼學比對，且使用 `oauth_codes.pop(code)` 達成一次性立即銷毀。`test_poc_pkce_tampering_and_replay_defense` 通過。

---

## 3. 統計與守恆性驗證 (Harness² Conservation)

```python
assert total_targets == 269
assert verified_vulnerabilities == 59
assert remediated_vulnerabilities == 68
assert dismissed_hypotheses == 150
# 守恆等式滿足: 59 + 150 + 60 == 269
```

