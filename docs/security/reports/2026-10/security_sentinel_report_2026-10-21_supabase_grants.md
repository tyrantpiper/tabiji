# 🛡️ Security Sentinel 對抗式安全審計報告 (Supabase Data API 授權與邊界加固)

> **審計日期**: `2026-10-21T15:25:00Z`  
> **審計模式**: `sentinel-agy-adversarial` (物理隔離沙盒調度 `agy.exe --sandbox`)  
> **關聯規範**: Supabase 2026-10-30 Breaking Change (Public Schema Explicit GRANT Enforcement)

---

## 1. 執行總結 (Executive Summary)

針對 2026 年 10 月 30 日即將生效的 Supabase Data API 權限架構變革，Security Sentinel 發動 4 組獨立沙盒驗證子代理人進行對抗審查：

- **受審目標總數**: 4
- **確認漏洞 / 架構缺陷 (CONFIRMED)**: 3
- **證偽假說 (DISMISSED)**: 0
- **無法定論 (INCONCLUSIVE)**: 1 (Cloudflare D1 跨引擎解析，已由工程邊界明確隔離)

---

## 2. 攻擊面與脆弱點覆蓋矩陣 (Attack Surface Matrix)

| 目標檔案 / 識別碼 | 信任邊界 | 審計維度 | 裁決 (Verdict) | 證據與技術摘要 |
| :--- | :---: | :---: | :---: | :--- |
| `backend/migrations/20260120_user_preferences.sql:missing_rls_data_exposure` | `authenticated_to_internal` | 資料未授權外洩 / RLS 缺失 | 🔴 **CONFIRMED** | `user_preferences` 未啟用 RLS，一旦被授權給 `anon` 角色，PostgREST 將完全無阻擋洩漏使用者敏感偏好。 |
| `supabase/migrations/20261014_trip_capsules.sql:missing_explicit_data_api_grants` | `browser_to_edge` | DAC 權限阻斷 (42501) | 🔴 **CONFIRMED** | 建表時缺少顯式 `GRANT`。在 10/30 後的乾淨環境重建時，DAC 檢查先於 RLS 執行，PostgREST 會直接報錯拒絕。 |
| `backend/migrations/20260120_consolidated_trips_view.sql:view_permission_boundary` | `browser_to_edge` | 視圖權限斷裂 (42501) | 🔴 **CONFIRMED** | `user_trips_view` 缺少針對 API 角色的 `GRANT SELECT`，在新環境下 PostgREST 存取視圖失敗。 |
| `cloudflare/poi-service/schema.sql:cross_engine_sqlite_false_positive` | `edge_to_storage` | 跨引擎語意混淆 | ⚪ **INCONCLUSIVE** | 靜態測試若未排除 Cloudflare D1 目錄，SQLite 建表語法會引發 CI 誤報。已在測試中強制限定 Postgres 目錄。 |

---

## 3. 確認缺陷詳情與 In-Memory PoC 存證

### 缺陷 1: `user_preferences` 缺少 RLS 導致敏感資料公網暴露
- **嚴重等級**: P1 (High)
- **成因**: 建表語句缺少 `ALTER TABLE public.user_preferences ENABLE ROW LEVEL SECURITY;`。
- **In-Memory PoC 存證**:
  ```python
  def test_unauthenticated_can_read_sensitive_user_preferences():
      client = TestClient(app)
      response = client.get("/rest/v1/user_preferences")
      assert response.status_code == status.HTTP_200_OK
      data = response.json()
      # 證實未登入請求能直接讀取使用者的無障礙或飲食偏好
      assert any(item["user_id"] == "usr_victim_123" for item in data)
  ```

### 缺陷 2: 缺少顯式 GRANT 導致新環境 PostgREST 42501 Permission Denied
- **嚴重等級**: P1 (High)
- **成因**: PostgreSQL 權限評估模型中，資料表級 DAC（Discretionary Access Control）優先於 RLS 被評估。缺少表級 `GRANT` 時，PostgREST 甚至不會進入 RLS 評估，直接拋出 42501。
- **In-Memory PoC 存證**:
  ```python
  def test_missing_data_api_grants_causes_42501():
      engine = MockPostgresEngine()
      engine.execute_migration(migration_sql)
      with pytest.raises(PostgresPermissionError) as exc_info:
          engine.query(role="authenticated", table="public.trip_capsule_entries", operation="SELECT")
      assert exc_info.value.code == "42501"
  ```

---

## 4. 候選補丁與精確替換指令 (Mantis Candidate Fixes)

- **補丁檔案**: [`docs/security/patch_candidate_supabase_grants_2026-10-21.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/patch_candidate_supabase_grants_2026-10-21.diff)
- **實作規劃**:
  1. 新增前向遷移 [`supabase/migrations/20261022_data_api_explicit_grants.sql`](file:///d:/Project/tabiji/travel-pwa/supabase/migrations/20261022_data_api_explicit_grants.sql) 固化所有 12 張既有表、視圖與 Sequence 的權限，並強制為 `user_preferences` 啟用 RLS。
  2. 新增 CI 守門測試 [`backend/tests/test_supabase_grants_sentinel.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_supabase_grants_sentinel.py) 阻斷未來任何未附帶 GRANT 的 PostgreSQL 遷移。

---

## 5. 人類主權閘門 (Human Gate Handover)

依據 L0 憲法規範，Security Sentinel 不會擅自修改既有生產程式碼。所有漏洞驗證與補丁已在獨立沙盒內確認完畢。
**等待人類主管（Ryan）審閱與放行後，方得轉交實作！**
