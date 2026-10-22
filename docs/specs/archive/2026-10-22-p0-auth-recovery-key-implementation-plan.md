# 🚀 實作計畫：P0 專屬恢復金鑰與伺服端動態脫敏體系 (Implementation Plan v2)

> **目標**: 實施「1Password 專屬恢復金鑰模式」與「伺服端動態脫敏」，徹底拔除同行隊友獲取他人 UUID 奪舍帳號的破口，同時 100% 保留 Landing Page 引繼碼體驗與 PWA 秒開即用優勢。  
> **關聯規格書**: [p0-silent-session-and-cryptographic-auth-spec.md](docs/specs/core-architecture/p0-silent-session-and-cryptographic-auth-spec.md)  
> **關聯研究報告**: [2026-10-22-pwa-anonymous-auth-transfer-code-and-idor-reality-check.md](docs/research/2026-10-22-pwa-anonymous-auth-transfer-code-and-idor-reality-check.md)  
> **執行紀律**: 遵循全域 AI 協定，待使用者確認後即刻進入實作階段。

---

## 📋 變更範圍概覽 (Scope Matrix)

| 模組 | 涉及檔案 | 變更性質 | 關鍵任務 |
| :--- | :--- | :--- | :--- |
| **後端核心認證** | `backend/routers/auth.py` (新增)<br/>`backend/utils/deps.py`<br/>`backend/main.py` | 認證升級 | 1. 建立 `POST /api/auth/session` (開機領票/換票)<br/>2. 建立 `POST /api/auth/recover` (首頁恢復金鑰引繼，含 IP 限流)<br/>3. `deps.py` 改為 JWT-only，廢除 `X-User-ID` 回退 |
| **後端動態脫敏** | `backend/routers/trips.py` | 隱私隔離 | 1. 於 `get_trip_by_id` 注入 `is_owner: bool`<br/>2. 非創立者請求時將 `created_by` 脫敏為 `None` 或掩碼<br/>3. 成員清單 `members` 中他人 UUID 動態雜湊為 `mem_xxx` |
| **後端資安守門** | `backend/tests/test_auth_sentinel.py` (新增)<br/>`backend/tests/test_trip_settings_sentinel.py` | 測試升級 | 1. 撰寫偽造 X-User-ID 被 401 拒絕之測試<br/>2. 撰寫同行隊友無法看見創立者真實 UUID 之脫敏測試<br/>3. 驗證現有 112+ pytest 全綠 |
| **前端狀態與 API** | `frontend/lib/auth-session.ts` (新增)<br/>`frontend/lib/api.ts`<br/>`frontend/lib/stores/tripStore.ts` | 狀態與請求注入 | 1. 實作啟動自動換票防抖單例<br/>2. `api.ts` 自動攜帶 `Authorization: Bearer <token>`<br/>3. 支援以恢復金鑰換發 Token |
| **前端 UI 正名** | `frontend/components/views/profile-view.tsx`<br/>`frontend/components/views/landing-page.tsx` | 文案正名與體驗優化 | 1. Profile 頁正名為「🛡️ 專屬恢復金鑰 (Recovery Key / 引繼碼)」並加安全提示<br/>2. Landing Page 正名為「使用恢復金鑰還原帳號」並對接 `/recover` 端點 |
| **文案與授權定位** | `README.md`<br/>`frontend/README.md` | 合規與文案校正 | 1. BYOK 文案更正為「Zero-Retention BYOK Relay (伺服器零持久化)」<br/>2. 標明「Source-Available under PolyForm Noncommercial 1.0.0」 |

---

## 🛠️ 分階段實作步驟 (Phased Execution Steps)

### Phase 1: 後端憑證發放中心與嚴格校驗依賴
1. **建立 `backend/routers/auth.py`**:
   - `POST /api/auth/session`：支援新訪客直接領取 JWT，既有老用戶傳入 `recovery_key` 靜默換發對應 JWT。
   - `POST /api/auth/recover`：首頁還原專用，配置 SlowAPI 限流 (5 次/分鐘/IP)，成功還原回傳新 JWT。
2. **重構 `backend/utils/deps.py`**:
   - `get_verified_user` 嚴格要求 `Authorization: Bearer <token>`，本機以 `PyJWT` 毫秒級解密簽章。
   - 徹底移除 `X-User-ID` Header 信任代碼。
3. **掛載至 `backend/main.py`**:
   - 掛載 `auth.router` 到 `/api/auth`。

---

### Phase 2: 協同行程伺服端動態脫敏 (Server-Side Masking)
1. **修改 `backend/routers/trips.py` 中的 `get_trip_by_id`**:
   - 計算 `is_owner = (user_id == created_by)`。
   - 若非創立者本人造訪，回傳的 `created_by` 遮蔽為 `None`，`is_owner` 設為 `False`。
   - 成員列表 `members` 中，僅保留本人之真實 ID，他人 ID 動態雜湊為 `mem_` + sha256。
2. **更新相關行程路由權限判斷**:
   - 確保所有刪除、踢人、更新標題等高風險操作，以 `user_id == trip.created_by` 或 `trip_members` 表格為唯一權威依據。

---

### Phase 3: 後端資安 Sentinel 測試
1. **新增 `backend/tests/test_auth_sentinel.py`**:
   - 測試 1：未帶 Bearer Token 存取私有端點被 401 拒絕。
   - 測試 2：偽造他人 `X-User-ID` 存取私有端點被 401 拒絕。
   - 測試 3：同行成員 Bob 呼叫 `GET /api/trips/{id}`，回傳中完全看不見 Alice 的真實 UUID。
   - 測試 4：Alice 呼叫 `GET /api/trips/{id}`，`is_owner` 為 `True` 且可見本人 ID。
   - 測試 5：`/api/auth/recover` 超過限流次數被 429 阻斷。
2. **回歸測試**:
   - 執行 `pytest` 確保 112+ 測試全數綠燈。

---

### Phase 4: 前端憑證注入、Landing Page 引繼對接與 UI 正名
1. **建立 `frontend/lib/auth-session.ts`**:
   - 管理 Session JWT 生命週期與換票邏輯。
2. **修改 `frontend/lib/api.ts`**:
   - 所有打向後端之請求自動附加 `Authorization: Bearer <token>`。
3. **修改 `landing-page.tsx`**:
   - 引繼功能對接 `/api/auth/recover`。
4. **修改 `profile-view.tsx`**:
   - 正名為「🛡️ 專屬恢復金鑰 (Recovery Key / 引繼碼)」並加上妥善保管之安全提示。

---

### Phase 5: 文案校正與全端測試守門
1. **修正 `README.md` & `frontend/README.md`**:
   - BYOK 零持久化轉發說明 + Source-Available 定位標註。
2. **全端測試關卡**:
   - 前端：`npx tsc --noEmit`（0 錯誤）
   - 前端：`npm run lint`（0 錯誤）
   - 前端：`npm run test -- --run`（全數通過）
   - 後端：`pytest`（全數通過）
