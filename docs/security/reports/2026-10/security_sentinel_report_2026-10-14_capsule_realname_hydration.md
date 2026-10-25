# Security Sentinel 對抗安全審計報告 (2026-10-14)

> **審計主題**: 時光膠囊實名水合、UUID 強型別約束、資料庫實體完整性與併發競爭防禦  
> **稽核代理人**: `@security` (Security Sentinel 2.0 - Physical Subagent Sandbox)  
> **審計模式**: 物理進程沙盒隔離 (`runner.py`) + 記憶體內對抗證偽 PoC (`pytest`)  
> **目標範疇**:
> - `backend/routers/capsules.py`
> - `supabase/migrations/20261014_trip_capsules.sql`
> - `frontend/components/views/landing-page.tsx`
> - `frontend/components/itinerary/CapsuleUnveilingCeremony.tsx`

---

## 一、審計總結與防禦態勢 (Executive Summary)

| 審計目標 | 信任邊界 | 對抗假說維度 | 實證結果 | 防禦狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **`backend/routers/capsules.py:realname_hydration`** | `authenticated_to_internal` | 批量水合引發全域用戶輪廓探測 (IDOR) | **DISMISSED** | 🛡️ SECURE (水合受限於行程成員) |
| **`backend/routers/capsules.py:time_lock_race`** | `authenticated_to_internal` | 解鎖瞬間併發寫入繞過時間鎖 (TOCTOU) | **VERIFIED & DEFENDED** | 🛡️ SECURE (資料庫與 API 雙重時間阻斷) |
| **`supabase/migrations/20261014_trip_capsules.sql`** | `authenticated_to_internal` | 髒資料直接轉型 UUID 導致 DDL 崩潰 | **CONFIRMED** | ⚠️ MITIGATED (已給出先清洗後約束 SQL) |
| **`frontend/components/views/landing-page.tsx`** | `public_to_authenticated` | 登入註冊異步延遲引發外鍵阻斷競爭 | **DISMISSED** | 🛡️ SECURE (已證實為 await 阻塞式流轉) |

---

## 二、對抗驗證與 In-Memory PoC 結果

所有 5 項對抗性測試均於隔離環境通過：

```
tests/test_capsules_security_sentinel.py::test_sentinel_poc_bola_leak_prevention_during_trip PASSED [ 20%]
tests/test_capsules_security_sentinel.py::test_sentinel_poc_time_lock_bypass_defense PASSED [ 40%]
tests/test_capsules_security_sentinel.py::test_sentinel_poc_malicious_photo_url_injection_rejected PASSED [ 60%]
tests/test_capsules_security_sentinel.py::test_sentinel_poc_author_id_must_be_valid_uuid PASSED [ 80%]
tests/test_capsules_security_sentinel.py::test_sentinel_poc_realname_hydration_isolation PASSED [100%]
============================== 5 passed in 0.10s ==============================
```

---

## 三、Google Mantis 候選修復補丁 (Candidate Patches)

> 遵守 L0 憲法「只回報，交由人類決策並授權應用」。

### 補丁 1：資料庫安全清洗與實名外鍵重建 (`supabase/migrations/20261014_trip_capsules.sql`)

```sql
-- 1. 清理非 UUID 格式之既有測試記錄
DELETE FROM public.trip_capsule_entries 
WHERE author_id NOT SIMILAR TO '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';

-- 2. 升級為 UUID 強型別
ALTER TABLE public.trip_capsule_entries 
ALTER COLUMN author_id TYPE UUID USING author_id::uuid;

-- 3. 建立正規實名外鍵約束 (指向 public.users)
ALTER TABLE public.trip_capsule_entries 
DROP CONSTRAINT IF EXISTS fk_capsule_author_user;

ALTER TABLE public.trip_capsule_entries 
ADD CONSTRAINT fk_capsule_author_user 
FOREIGN KEY (author_id) REFERENCES public.users(id) ON DELETE CASCADE;
```

### 補丁 2：後端 O(1) 批量實名水合器 (`backend/routers/capsules.py`)

在 `get_trip_capsules` 中，一次性收集所有 `author_id` 執行批次查詢，並加上 `author_avatar` 欄位支援：

```python
# 批次水合旅伴實名與頭像，徹底消除 N+1 查詢
author_uuids = list(set([str(e["author_id"]) for e in raw_entries]))
user_profile_map: Dict[str, Dict[str, Any]] = {}

if author_uuids:
    # 優先從 public.users 提取全域 profile
    u_res = supabase.table("users").select("id, name, avatar_url").in_("id", author_uuids).execute()
    if u_res.data:
        for u in u_res.data:
            user_profile_map[str(u["id"])] = {
                "name": u.get("name") or "Traveler",
                "avatar_url": u.get("avatar_url")
            }

    # 次級提取 trip_members 自訂頭像與名稱補充
    m_res = supabase.table("trip_members").select("user_id, user_name, user_avatar")\
        .eq("itinerary_id", trip_id).in_("user_id", author_uuids).execute()
    if m_res.data:
        for m in m_res.data:
            uid = str(m.get("user_id"))
            if uid in user_profile_map:
                if m.get("user_name"): user_profile_map[uid]["name"] = m["user_name"]
                if m.get("user_avatar"): user_profile_map[uid]["avatar_url"] = m["user_avatar"]
```
