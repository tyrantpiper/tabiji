# 🛡️ Security Sentinel 對抗式資安審查報告：認證與授權端點沙盒證偽 (2026-10-22)

> **審查模式**: Sentinel Physical Adversarial Subagent Inspection & In-Memory Test Validation  
> **資安稽核員**: @security (Security Sentinel)  
> **受審檔案**:
> - `backend/routers/gdpr.py` (Trust Boundary: `authenticated_to_internal`)
> - `backend/routers/trips.py` (Trust Boundary: `authenticated_to_internal`)
> - `backend/routers/ai.py` (Trust Boundary: `authenticated_to_internal`)
> **候選假說清單**: `docs/security/candidates_post_auth_endpoints_2026-10-22.json`  
> **沙盒判定清單**: `docs/security/findings_post_auth_endpoints_2026-10-22.json`  
> **驗證狀態**: 4 項假說 **全數證偽/防禦成立 (4/4 DISMISSED / PROVEN SECURE)**

---

## 執行摘要 (Executive Summary)

針對 Tabiji 後端 4 個高敏感端點（GDPR 資料刪除、行程合併匯入、行程自建儲存、AI 審核報告刪除）進行獨立沙盒子代理人對抗審查與記憶體級單元驗證 (`backend/tests/test_p0_auth_sentinel.py`)。
審查結果：**4 項安全威脅假說全數證偽（4/4 DISMISSED）**，端點均已實體具備強制性 JWT 依賴驗證、物件級擁有權比對（BOLA 防禦）以及防身分替換約束。

| 假說 ID | 攻擊向量 | 嚴重等級 | 審查判定 | 物理沙盒審查結論 |
| :--- | :--- | :--- | :--- | :--- |
| `backend/routers/gdpr.py:delete_user_data_unauthenticated_bola` | BOLA / 越權刪除帳戶資料 | **High** | 🛡️ **DISMISSED** | 強制 `caller_user_id: Depends(get_verified_user)` 且 `caller_user_id == user_id`，非本人操作即刻 403 阻斷。 |
| `backend/routers/trips.py:import_to_trip_unauthenticated_injection` | BOLA / 未授權資料篡改注入 | **High** | 🛡️ **DISMISSED** | 綁定 `user_id: Depends(get_verified_user)`，嚴格核實行程創立者或成員關係，非成員操作即刻 403 阻斷。 |
| `backend/routers/trips.py:save_itinerary_identity_substitution` | 請求體身分替換攻擊 (Identity Spoofing) | **High** | 🛡️ **DISMISSED** | 配額檢查、主行程 `created_by`、用戶存在性校驗與成員綁定，100% 取自 verified JWT，忽視請求體偽造。 |
| `backend/routers/ai.py:clear_day_review_unauthenticated_deletion` | BOLA / 任意調用者清除審核報告 | **Medium** | 🛡️ **DISMISSED** | 綁定 `user_id: Depends(get_verified_user)`，且嚴格核對建立者或成員清單，無成員權限即刻 403 阻斷。 |

---

## 物理沙盒證偽剖析 (Empirical Defense Verification)

### 1. `DELETE /api/user/{user_id}/data` (GDPR 資料刪除)
- **代碼位置**: `backend/routers/gdpr.py:14-31`
- **防禦機制**:
  ```python
  @router.delete("/user/{user_id}/data")
  async def delete_user_data(
      user_id: str, 
      caller_user_id: str = Depends(get_verified_user),
      supabase=Depends(get_supabase)
  ):
      if caller_user_id != user_id:
          raise HTTPException(status_code=403, detail="只能刪除自己的資料")
  ```
- **Sentinel 判定**: 證實未帶 Token 者在 FastAPI 依賴注入階段即拋出 401 Unauthorized；帶有有效 Token 但欲刪除他人資料者即刻拋出 403 Forbidden，BOLA 漏洞被徹底消除。

### 2. `POST /api/trips/import-to-trip` (匯入到現有行程)
- **代碼位置**: `backend/routers/trips.py:941-971`
- **防禦機制**:
  ```python
  @router.post("/import-to-trip")
  async def import_to_trip(
      request: ImportToTripRequest, 
      user_id: str = Depends(get_verified_user),
      supabase=Depends(get_supabase)
  ):
      ...
      created_by = str(existing_trip.get("created_by") or "")
      if created_by != user_id:
          mem_res = supabase.table("trip_members").select("id").eq("itinerary_id", request.trip_id).eq("user_id", user_id).execute()
          if not mem_res.data:
              raise HTTPException(status_code=403, detail="只有行程成員或創建者可以匯入內容")
  ```
- **Sentinel 判定**: 成功驗證雙層防禦（建立者匹配與協同成員查詢），任何外部非法調用者均無法對非所屬行程進行內容合併與細項注入。

### 3. `POST /api/trips/save-itinerary` (儲存行程與配額限制)
- **代碼位置**: `backend/routers/trips.py:785-886`
- **防禦機制**:
  - 用戶行程數量限制配額以 Token 解析之 `user_id` 為查詢基準 (`.eq("created_by", user_id)`)。
  - `trip_data["created_by"] = user_id`，強制覆蓋 client 傳入之任意 payload。
  - `member_data["user_id"] = user_id`，確保行程初始所有權不可篡改。
- **Sentinel 判定**: 證實客戶端在 JSON Body 中偽造 `user_id` 或 `creator_name` 完全無法替換真實創立者，身分替換攻擊無效。

### 4. `DELETE /api/ai/trips/{trip_id}/days/{day}/ai-review` (清除 AI 審核報告)
- **代碼位置**: `backend/routers/ai.py:858-882`
- **防禦機制**:
  - 強制依賴 `user_id: str = Depends(get_verified_user)`。
  - 檢驗 `trip.created_by == user_id`，若不匹配則進一步檢查 `trip_members`，皆不符時拋出 403 Forbidden。
- **Sentinel 判定**: 審核報告刪除邏輯具備嚴格的物件級權限控制，任何匿名或非授權成員調用均被拒絕。

---

## 迴歸驗證與測試關卡 (Quality & Regression Gates)

- **後端專項測試 (`backend/tests/test_p0_auth_sentinel.py`)**: 15/15 測試用例全數通過（涵蓋未帶 Token 401、跨帳號 BOLA 403、身分覆寫驗證）。
- **後端全量測試 (`pytest tests/`)**: **215 passed, 5 skipped, 0 failed** (16.99s)。
- **前端全量測試 (`vitest run`)**: **82 test files, 544 passed** (100% green)。
- **靜態型別與 Lint 檢查**:
  - TypeScript: `npx tsc --noEmit` -> **0 errors**
  - ESLint: `npm run lint` -> **0 errors, 0 warnings**
- **安全帳本校驗 (`validate_security_ledger.py`)**: 175 項受稽目標格式全數通過驗證。
