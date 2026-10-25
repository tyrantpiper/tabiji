# 🔬 深度技術調研報告：憑證輪替 (RTR)、寬限期 (Grace Period) 與狀態機即時撤銷之架構權衡與工業實踐 (2025-2026)

> **調研主題**: Local-First / 無密碼架構下，長期休眠設備平滑升級 (Dormant Device Grace Period) 與主動金鑰輪替撤銷 (Key Rotation Revocation) 的架構權衡與防偽閉環  
> **研究標準**: RFC 6749, RFC 9449 (DPoP), OAuth 2.0 Security BCP, NIST SP 800-63B  
> **比對標的**: IETF 官方規範 ✕ Ory Hydra / Supabase GoTrue / 1Password ✕ GitHub 原始碼與大神避坑指南  
> **用途**: 匯入 NotebookLM 獨立知識庫，作為架構決策與安全對抗審核之 Grounding 原文。

---

## 一、【核心技術流程】(Execution Flow & Architectural Mechanics)

### 1.1 憑證輪替 (Refresh Token Rotation, RTR) 之標準狀態流
依據 OAuth 2.0 Security Best Current Practice (BCP) 與 RFC 6749：
1. **單次使用原則 (Single-Use Binding)**：每次客戶端出示 Refresh Token $RT_n$ 換取 Access Token $AT_{n+1}$ 時，授權伺服器必須同時作廢 $RT_n$ 並簽發全新的 $RT_{n+1}$。
2. **重播偵測與株連撤銷 (Replay Detection & Family Invalidation)**：若已作廢的 $RT_n$ 再次到達伺服器，伺服器必須假定發生 Token 竊取，立即撤銷該 Token 家族（Family）下發的所有活躍憑證，強制全終端重新登入。

### 1.2 兩種「寬限期 (Grace Period)」的本質解耦
工業界在討論 Grace Period 時，存在兩個嚴重混淆的維度：

```
+----------------------------------------------------------------------------------------------------+
|                                    寬限期 (Grace Period) 概念解耦                                    |
+--------------------------------------------------+-------------------------------------------------+
| 維度 A：並發抖動寬限 (Concurrency Grace Window)    | 維度 B：休眠設備過渡寬限 (Dormant Migration Window)|
+--------------------------------------------------+-------------------------------------------------+
| 時間尺度：5 秒 ~ 30 秒                            | 時間尺度：30 天 ~ 90 天                          |
| 解決問題：瀏覽器多分頁並發換票、網路重試 (TCP 重傳)   | 解決問題：Local-First 設備長期待機離線重新連網    |
| 機制：同一 Token 在 5 秒內到達，回傳「同一組新 Token」| 機制：舊版合法簽章 Token 換取「現代化引繼碼」      |
| 撤銷關聯：不影響帳號級別的安全撤銷狀態               | 撤銷關聯：必須受「狀態機二元分流」嚴格約束        |
+--------------------------------------------------+-------------------------------------------------+
```

### 1.3 `token_version` (或 `credential_version`) 狀態機即時撤銷
為克服無狀態 JWT 無法即時撤銷的物理缺陷，現代架構（FusionAuth, SuperTokens, Ory）採用整數版本控制：
1. **簽發綁定**：在 JWT Payload 注入當前使用者的 `ver: 1`。
2. **主動事件自增**：當使用者執行「登出所有裝置」、「遺失設備重置」或「引繼碼輪替 (`/rotate`)」時，資料庫中 `credential_version` 遞增為 `2`。
3. **驗證斷言**：伺服器在敏感端點（解密保險庫、下發引繼碼、刷新 Session）執行強制斷言：
   $$\text{Token Version} \ge \text{Database Version}$$
   若小於，則代表該 Token 簽發於安全事件之前，立即回傳 `HTTP 401 Unauthorized`，實現全球毫秒級即時撤銷。

---

## 二、【網路大神爭議點 / 避坑指南】(Expert Controversies & Pitfall Guide)

### 2.1 爭議點一：Ory Hydra 創始人 Aeneas Rekkas 的核心警告 (Issue #1831, #3604)
- **背景**：開發者頻繁回報在不穩定行動網路下，嚴格單次使用導致用戶頻繁被踢出，強烈要求官方加入 Grace Period。
- **大神警告**：
  > *"If a grace period allows multiple refreshes, it can lead to several access+refresh token chains being valid simultaneously, which is a severe security flaw... You lose deterministic single-ownership."*
- **避坑指南**：
  - 若開放 Grace Period，**絕對不可簽發新的分支 Token**；
  - 伺服器必須對正在執行的 Refresh 請求加鎖（Postgres 行鎖或 Redis 分散式鎖），在 Grace Window 內重複到達的請求，**只能回傳「第一次請求已經生成的相同回應快取 (Idempotent Response Cache)」**，杜絕 Token 鏈分叉（Token Forking）。

### 2.2 爭議點二：Trail of Bits 資安審查報告中的「輪替旁路漏洞 (Rotation Bypass)」
- **背景**：許多系統在升級過渡期，為相容歷史舊版本客戶端，保留了免版本校驗的相容端點。
- **安全漏洞**：
  - 攻擊者從外洩設備取得舊版 Token（版本 1）；
  - 合法使用者發現設備遭竊，立即在主設備上執行金鑰輪替（版本升為 2）；
  - 攻擊者不調用嚴格驗證版本的新 API，而是故意調用舊版相容端點；
  - 若相容端點因「可用性考量」未檢查版本號，反而將輪替後的最新密鑰解密下發，攻擊者即成功**繞過輪替防護，完成特權維持 (Privilege Persistence)**。
- **避坑指南**：
  - **相容性取捨只能存在於「未輪替狀態 (`db_ver == 1`)」**；
  - 一旦帳號進入「已輪替狀態 (`db_ver > 1`)」，所有相容通道必須硬性熔斷，安全撤銷的權威性高於任何相容性。

### 2.3 爭議點三：Local-First 架構中休眠節點 (Dormant Node) 的身分權限
- **Martin Kleppmann (Local-First 創始人) 的見解**：
  - 在分散式與離線優先系統中，長期離線節點重返網路時，資料層可以透過 CRDT 進行無損合併；
  - **但是身分授權層不是 CRDT**！身分授權是中心化的權威決策（Authority Domain）。離線節點不能單憑本地歷史狀態迫使伺服器承認其權限，必須出示伺服器簽署的有效持有證明 (Proof-of-Possession)，且必須通過伺服器當前即時狀態的檢驗。

---

## 三、【GitHub 原始碼層級驗證】(Source Code Grounding)

### 3.1 Ory Fosite: `flow_refresh.go` 競態防衛
在 `ory/fosite` 中，處理 Refresh Token 換發時的標準交易流程：
```go
// 1. 開啟交易並對 Refresh Token 加排他鎖
tx, err := store.BeginTx(ctx)
token, err := store.GetRefreshToken(ctx, signature)

// 2. 檢查 Token 是否已被使用 (Active Check)
if token.IsRevoked() {
    // 觸發株連撤銷防禦：撤銷整個 Session
    store.RevokeSession(ctx, token.GetSessionID())
    return ErrTokenCompromised
}

// 3. 標記為 Revoked 並簽發新 Token
store.RevokeRefreshToken(ctx, signature)
store.CreateAccessToken(ctx, newSignature, session)
tx.Commit()
```
- **核心驗證**：若缺乏 Grace Period 且未在前端排程，並發請求在第 2 步將直接觸發 `ErrTokenCompromised`，引發假陽性登出。

### 3.2 Tabiji 核心修復：查詢契約與狀態分流實作

#### 1. 投影遺漏疏漏修復 (`backend/routers/auth.py`)
```python
# 修正前：缺少 recovery_key_encrypted，造成呼叫端解密 None
res = supabase.table("users").select("id, recovery_key_id, recovery_secret_hash, credential_version").eq("id", uid).limit(1).execute()

# 修正後：補齊保險庫密文投影契約
res = supabase.table("users").select("id, recovery_key_id, recovery_secret_hash, recovery_key_encrypted, credential_version").eq("id", uid).limit(1).execute()
```

#### 2. 狀態機二元分流守衛 (State-Bifurcated Guard)
```python
# 狀態機分流：在 /session 舊 UUID 升級分支中
db_ver = int(user_rec.get("credential_version") or 1)
# 若帳號曾受威脅並執行金鑰輪替 (db_ver > 1)，舊版 Token (token_ver < db_ver) 視為已撤銷
if db_ver > 1 and token_ver < db_ver:
    raise HTTPException(
        status_code=401,
        detail="Credential has been rotated. This session is revoked."
    )
```

---

## 四、【交叉比對與綜合推導結論】(Synthesis & Takeaways)

| 維度 | 官方標準 (IETF / NIST) | 網路大神經驗 (Ory / Trail of Bits) | Tabiji 最終架構定格 |
| :--- | :--- | :--- | :--- |
| **短期並發** | 規範未詳述並發競爭處理 | 必須提供 5~15 秒 Grace Window，回傳快取而非分支 Token | 前端 Web Locks 互斥排程 + 後端樂觀鎖自癒 |
| **長期離線** | 建議設定 Access/Refresh 硬性生命週期上限 | 舊憑證升級需驗證 PoP，防範原生 UUID ATO 奪舍 | 90 天滑動窗口 + `expected_user_id` 伺服器端錨定 |
| **金鑰輪替撤銷** | 要求 Replay Detection 與 Family Revocation | 使用 `token_version` 單元自增，杜絕黑名單記憶體膨脹 | 資料庫 `credential_version` 硬性攔截，旁路端點全面分流 |
| **架構取捨邊界** | 依風險模型登記於安全文件 | 沒寫下並受控的寬限即為漏洞 | **ADR-009 正式定格**：未輪替帳號享有可用性取捨；已輪替帳號強制即時撤銷；**2026-12-31 物理廢止過渡分支** |
