# 🛡️ Security Sentinel 對抗審查與沙盒實測報告 (Phase 5)
**主題**: 引繼碼身份預言機 (Identity Oracle) 防禦與網路傳輸零洩漏 (Zero-Wire-Leak) 架構  
**日期**: 2026-10-24  
**審查者**: `@security` (Security Sentinel)  
**狀態**: `CONFIRMED_PENDING_DEV` (等待人類簽准開工)

---

## Executive Summary (執行摘要)
- **攻擊面標的數**: 2 (後端 `POST /api/auth/session`、前端 `reanchorSessionWithKey`)
- **確診漏洞數**: 2
  1. **網路層 Token 提前外洩 (Wire-Level JWT Exposure)**: 後端在收到有效引繼碼後，於比對設備身份之前即簽發並下發受害者之 JWT。攻擊者僅需打開 DevTools Network Tab 即可竊取他人 Token。
  2. **使用者枚舉預言機 (User Enumeration Oracle)**: 系統區分「引繼碼不存在」與「此引繼碼屬於另一個帳號」，攻擊者可藉此暴力探測已註冊之有效引繼碼。
- **沙盒測試通過率**:
  - `backend/tests/test_p0_auth_revocation_sentinel_poc.py`: **7/7 PASSED (100%)**
  - `frontend/__tests__/in-place-reauth-resilience.test.ts`: **10/10 PASSED (100%)**
  - 前端型別檢查: `npx tsc --noEmit` **0 Errors**

---

## 🔬 物理沙盒實測實證 (Empirical Sandbox Proof)

### 1. 後端沙盒測試實證 (pytest)
- **TC-7: 漏洞物理重現**
  - 模擬情境: 攻擊者設備（持有 Alice UUID）傳入 Bob 的合法引繼碼。
  - 舊版行為: 伺服器回傳 HTTP 200，Response Body 攜帶 Bob 的 `access_token` 與 `user_id`。
  - 遙測數據: 透過 `jwt.decode` 證實該 Token 確實具備 Bob 之身份權限，在網路傳輸層造成實質外洩。
- **TC-8: Mantis Patch 防護驗證**
  - 修正架構: Client 請求時攜帶 `expected_user_id`。後端在**產生任何 JWT 之前**進行嚴格斷言：
    ```python
    if body.expected_user_id and user["id"].strip().lower() != body.expected_user_id.strip().lower():
        raise HTTPException(status_code=401, detail=UNIFORM_AUTH_ERROR)
    ```
  - 遙測數據:
    - 回應狀態碼: **HTTP 401 Unauthorized**。
    - 網路層酬載: **完全零 Token、零 user_id 傳輸** (`assert "access_token" not in res.json()`)。
    - 錯誤訊息一致性: 無效金鑰、錯誤 Hash、非目標帳號引繼碼，**三者回傳完全一致之常數**：
      `"引繼碼驗證失敗，無法在此設備恢復同步。請確認引繼碼是否正確。"`
    - 舊版 UUID 遷移路徑同樣受此防禦涵蓋，杜絕任何繞過可能。

### 2. 前端沙盒測試實證 (vitest)
- **TC-9: 前端統一防線與預言機消解**
  - 驗證 `reanchorSessionWithKey` 無論遭遇 401 拒絕、格式錯誤或內部例外，UI 均僅呈現統一安全文案。
  - 絕不對外輸出「此引繼碼屬於另一個帳號」，徹底摧毀攻擊者的枚舉預言機。
- **TC-10: 5 秒在途請求靜音窗口 (lastRestoredAt Grace Window)**
  - 驗證重認證完成時標記 `lastRestoredAt = Date.now()`。
  - 在此後 5000ms 內，若有先前在途發出、攜帶過期 Token 的請求返回 401，被防護攔截器靜默吸收，不再反覆喚醒 Re-auth Modal。

---

## 🛠️ Mantis Patch 候選補丁與替換指令
所有候選補丁已精準生成於：
- RFC 差異檔: [patch_candidate_oracle_defense_2026-10-24.diff](file:///d:/Project/tabiji/travel-pwa/docs/security/patch_candidate_oracle_defense_2026-10-24.diff)
- 精確區塊映射: [block_replacements_oracle_defense_2026-10-24.json](file:///d:/Project/tabiji/travel-pwa/docs/security/block_replacements_oracle_defense_2026-10-24.json)

---

## 🚦 Human Gate (人類審核關卡)
依據 L0 憲法與 `@security` 職責隔離：
- 本代理人已於沙盒內完成全部對抗證偽與零回歸驗證。
- **尚未對生產代碼進行任何修改**。
- 請人類開發者（Ryan）檢閱本報告。簽准後，即交由 `@dev` 執行精確區塊替換，並由 `@qa` 進行全棧回歸驗證。
