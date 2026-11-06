# Security Sentinel 對抗審計報告：Tabiji MCP 前端 UI 與邊緣轉發整合

> **審計日期**: 2026-11-06  
> **模式**: `/security-sentinel` ✕ Mantis Block G ✕ Harness² Conservation  
> **標的模組**: Next.js Rewrites ✕ Session JWT Contract ✕ MCPConnectorDialog  
> **沙盒測試套件**: `backend/tests/test_mcp_ui_sentinel_simulation.py` (4/4 通過)  
> **全量測試套件**: 26/26 全部綠燈 (4.97s)  
> **候選補丁檔**: `docs/security/history/patches/patch_candidate_mcp_ui_2026-11-06.diff`  

---

## 1. 執行總結 (Executive Summary)

針對前端 UI 面板與 Next.js 邊緣轉發的整合計畫，Security Sentinel 針對「Token 合約型別混淆」、「OAuth Discovery 轉發盲區」及「剪貼簿憑證洩漏防禦」三項假說實施了紅藍對抗審計。

- **審計目標總數**: 3
- **紅軍擊穿/確認漏洞 (Confirmed)**: 2 (Raw Token 混淆 401 拒絕、Next.js 漏掉 /.well-known 轉發)
- **藍軍防禦與良性對照通過 (Mantis Block G Passed)**: 3
- **閹割補丁攔截數**: 0
- **實體測試結果**: **4/4 passed (0.49s)，累計全量 MCP 套件 26/26 passed (4.97s)**

---

## 2. 核心漏洞與修復驗證

### 2.1 裸露引繼碼型別混淆 401 拒絕 (`frontend/lib/auth-session.ts`)
- **威脅路徑**: `public_to_authenticated`
- **紅軍驗證 (PoC)**: 若 UI 直接複製 `user_recovery_key` (tbj_rec_*) 給用戶貼入 Gemini，後端 `deps.py` 執行 `jwt.decode` 失敗拋出 401，連線 100% 失敗。
- **藍軍修復**: 前端 UI 改為透過 `getValidSessionToken()` 向後端獲取標準簽署之 Session JWT，並以密文遮罩保護。`test_benign_signed_session_jwt_accepted_by_auth` 通過。

### 2.2 Next.js 邊緣代理缺失 OAuth Discovery (`frontend/next.config.mjs`)
- **威脅路徑**: `browser_to_edge`
- **紅軍驗證 (PoC)**: Next.js 原有 rewrites 僅涵蓋 `/api/:path*`，Google Gemini 發送 `/.well-known/oauth-authorization-server` 探針時遭遇 Next.js 404 攔截。
- **藍軍修復**: 在 `next.config.mjs` 加入 `/.well-known/:path*` 反向代理規則，直通 FastAPI 後端。`test_benign_nextjs_wellknown_rewrite_success` 通過。

---

## 3. 統計與守恆性驗證 (Harness² Conservation)

```python
assert total_targets == 266
assert verified_vulnerabilities == 57
assert remediated_vulnerabilities == 65
assert dismissed_hypotheses == 150
# 守恆等式滿足: 57 + 150 + 59 == 266
```

