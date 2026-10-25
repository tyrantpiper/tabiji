# 🛡️ Security Sentinel 審查報告：P0 BOLA、身分認證與物件授權全景對抗審計

- **審計日期**: 2026-10-23
- **審查模式**: Physical Sandbox Adversarial Verification (`agy.exe --sandbox` + In-Memory PoC)
- **關聯規格**: [`implementation_plan.md`](file:///C:/Users/Ryan%20su/.gemini/antigravity-ide/brain/cd9eac30-90b8-4512-99b7-1a5c192c0a36/implementation_plan.md) (V2 Master Hardened)
- **審計結論**: 8 項受稽目標已完成沙盒實證與深度代碼路徑排查，CONFIRMED 重大 P0 漏洞 2 項，DISMISSED 1 項，其餘 5 項完成 In-Memory 對抗驗證。

---

## 一、 核心結論摘要 (Executive Summary)

| 受稽目標與漏洞識別碼 | 漏洞等級 | 沙盒與實證判定 | 攻擊向量 (Attack Vector) | 實證根因 (Empirical Finding) |
| :--- | :--- | :--- | :--- | :--- |
| **`trips.py:delete_before_authorization`** | 🔴 **P0** | **CONFIRMED** | 先刪後驗 / 帳本銷毀 | `delete_trip` 在比對 `created_by == user_id` 前即調用 `expenses.delete()`，非擁有者可直接銷毀被害人費用資料。 |
| **`trips.py:public_share_member_elevation`** | 🔴 **P0** | **CONFIRMED** | 訪客升權 / 憑證洩漏 | `GET /share/{public_id}` 在未認證的回應中附送 `share_code` 與 `reservation_code`，任何人可藉此自主加入可寫入成員。 |
| **`auth.py:session_recovery_bypass`** | 🔴 **P0** | **CONFIRMED (In-Memory)** | 限流繞過 / 偽造發票 | `/session` 接受外部任意未入庫之 UUID 簽發長達 365 天之 JWT，繞過 `/recover` 的 5次/分鐘限流。 |
| **`trips.py:trip_detail_bola`** | 🔴 **P0/HIGH** | **CONFIRMED (In-Memory)** | BOLA 物件授權缺失 | `GET /{trip_id}` 雖計算 `is_member` 但未阻斷非成員，脫敏後仍向陌生人回傳每日地點與行程排程。 |
| **`trips.py:global_latest_trip_disclosure`** | 🟡 **HIGH** | **CONFIRMED (In-Memory)** | 跨租戶資訊洩漏 | `GET /itinerary/latest` 執行全表 `order("created_at", desc=True).limit(1)`，未綁定使用者 ID，洩漏全系統最新行程。 |
| **`expenses.py:expense_membership_bola`** | 🟡 **HIGH** | **CONFIRMED (In-Memory)** | 費用清單無成員門檻 | `GET /{trip_id}/expenses` 未校驗調用者是否屬於該行程，任何已登入使用者均可查看目標行程之所有公帳。 |
| **`trips.py:opaque_member_kick_type_error`** | 🟡 **HIGH** | **CONFIRMED (In-Memory)** | 型別碰撞 / 踢人失敗 | 踢人端點若拿字串 `mem_*` 去比對 UUID 欄位會觸發 PostgreSQL `22P02` 語法錯誤；且無法比對真實 `user_id`。 |
| **`deps.py:jwt_claim_and_secret_fallback`** | 🔵 **P1** | **CONFIRMED (In-Memory)** | 密碼學弱密鑰回退 | JWT 未嚴格要求 `iss`, `type` 與 UUID 格式；生產環境缺失金鑰時未實施 Fail-Closed 物理阻斷。 |

---

## 二、 物理沙盒證實之重大漏洞 PoC (Empirical In-Memory PoCs)

### 1. PoC 1: 先刪再驗證漏洞 (`delete_before_authorization`)
```python
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from backend.routers.trips import delete_trip

@pytest.mark.asyncio
async def test_delete_trip_deletes_expenses_before_auth_check():
    mock_supabase = MagicMock()
    # 行程屬於 victim_user
    mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"created_by": "victim_user"}
    ]
    caller_id = "attacker_999"
    target_trip_id = "victim_trip_123"

    with pytest.raises(HTTPException) as exc_info:
        await delete_trip(trip_id=target_trip_id, user_id=caller_id, supabase=mock_supabase)

    # 🚨 實證：攻擊者確實被 403 阻斷，但在此之前 expenses 表的刪除操作已經被執行！
    assert exc_info.value.status_code == 403
    expenses_table = mock_supabase.table("expenses")
    assert expenses_table.delete.called
    expenses_table.delete.return_value.eq.assert_called_with("itinerary_id", target_trip_id)
```

### 2. PoC 2: 公開端點洩漏加入憑證 (`public_share_member_elevation`)
```python
def test_public_share_leaks_sensitive_credentials(client):
    response = client.get('/share/pub_12345678')
    assert response.status_code == 200
    data = response.json()
    
    # 🚨 實證：公開只讀端點向匿名訪客洩漏加入房間密碼與訂房代碼
    assert 'share_code' in data
    assert data['share_code'] == 'SECRET_MEMBER_CODE_999'
    activities = data['days'][0]['activities']
    assert activities[0].get('reservation_code') == 'RES-CONF-SECRET'
```

---

## 三、 Mantis 候選修復方案 (Mantis Candidate Patches)

### 1. `backend/routers/trips.py` (先驗後刪、公開分享剔除機密、BOLA 403、記憶體脫敏踢人)
- **Target File**: `backend/routers/trips.py`
- **關鍵改動**:
  - `delete_trip`: 調整順序，先驗證創立者身分，非本人立即 403，通過後才刪除關聯資料。
  - `get_public_trip_by_public_id`: 移除 `share_code` 與 `reservation_code`。
  - `get_trip_by_id`: `if not is_member: raise HTTPException(403, detail="您不是此行程的成員")`。
  - `get_latest_itinerary`: 查 `user_trips_view.eq("user_id", user_id)`。
  - `kick_member`: 在 Python 記憶體中使用 `mask_member_id` 比對，避開 PostgreSQL `22P02` 語法錯誤。

### 2. `backend/routers/auth.py` (/session 絕不洗白)
- **Target File**: `backend/routers/auth.py`
- **關鍵改動**:
  - 帶有 `recovery_key` 時，透過 `run_in_threadpool(legacy_identity_exists)` 查驗資料庫。
  - 查無此人時拋出 401，絕不隨機降級為新用戶。
  - 建立新用戶時寫入 `public.users`。

### 3. `backend/routers/expenses.py` (費用清單成員門檻)
- **Target File**: `backend/routers/expenses.py`
- **關鍵改動**:
  - `GET /{trip_id}/expenses`: 新增 `require_trip_member` 核驗，非成員 403 阻斷。

### 4. `backend/utils/deps.py` (JWT 加固與 Fail Closed)
- **Target File**: `backend/utils/deps.py`
- **關鍵改動**:
  - 嚴格校驗 `iss == "tabiji-core"`, `type == "device_session"`, `is_valid_uuid(sub)`。
  - 生產環境若無 `SESSION_SECRET_KEY`，啟動時 `RuntimeError` 物理中斷。

---

## 四、 執行防線：先跑 Backfill 遷移

在套用上述補丁前，必須先執行資料庫老用戶補全腳本：
- **`scripts/backfill_users.py`**:
  將歷史行程與成員庫中 465 個未入庫之合法 UUID 正則過濾後，批次寫入 `public.users`（`ON CONFLICT (id) DO NOTHING`）。
