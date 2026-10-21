# 🛡️ Security Sentinel 對抗式安全審計報告 (Sentinel 正則解析器加固)

> **審計日期**: `2026-10-21T16:15:00Z`  
> **審計模式**: `sentinel-agy-adversarial` (物理隔離沙盒調度 `agy.exe --sandbox`)  
> **關聯組件**: `backend/tests/test_supabase_grants_sentinel.py`

---

## 1. 執行總結 (Executive Summary)

針對 CI 靜態哨兵 `test_supabase_grants_sentinel.py` 中的正則解析器語法容錯度，Security Sentinel 發動 2 組物理隔離沙盒驗證子代理人進行對抗證偽審查：

- **受審目標總數**: 2
- **確認缺陷 (CONFIRMED)**: 2
- **證偽假說 (DISMISSED)**: 0
- **無法定論 (INCONCLUSIVE)**: 0

---

## 2. 脆弱點覆蓋矩陣 (Attack Surface Matrix)

| 目標檔案 / 識別碼 | 信任邊界 | 審計維度 | 裁決 (Verdict) | 證據與技術摘要 |
| :--- | :---: | :---: | :---: | :--- |
| `backend/tests/test_supabase_grants_sentinel.py:multiline_and_role_order_false_positive` | `internal_developer_tooling` | CI 誤報拒絕服務 | 🔴 **CONFIRMED** | `grant_pattern` 缺少 `re.DOTALL` 且硬編碼角色名稱緊接 `TO`，導致標準多行 SQL 或官方推薦之 `TO anon, authenticated;` 誤判為未授權，阻斷正常 CI 建置。 |
| `backend/tests/test_supabase_grants_sentinel.py:rls_pattern_syntax_rigidity` | `internal_developer_tooling` | 語法過度拘束 / 靜態漏判 | 🔴 **CONFIRMED** | `rls_pattern` 缺少 `IF EXISTS` 與 `ONLY` 容錯，當遷移採用防禦性 SQL 語法時無法識別，引發誤報。 |

---

## 3. 確認缺陷詳情與 In-Memory PoC 存證

### 缺陷 1: 缺少換行穿透與角色順序拘束引發 CI 誤報
- **嚴重等級**: P2 (Medium - CI 假陽性阻斷)
- **成因**: 正則 `GRANT\s+.*ON\s+...` 在遇到多行 SQL 時因 `.*` 無法跨行匹配而中斷；且 `TO\s+(?:authenticated|service_role)` 無法匹配 `TO anon, authenticated`。
- **In-Memory PoC 存證**:
  ```python
  import re
  import pytest

  def test_sentinel_false_positives_on_valid_sql():
      table = "user_profiles"
      rigid_grant_pattern = re.compile(
          rf"GRANT\s+.*ON\s+(?:TABLE\s+)?(?:public\.)?{table}\s+TO\s+(?:authenticated|service_role)",
          re.IGNORECASE
      )
      
      # 1. 官方多角色授權寫法 (anon 在前)
      multi_role_sql = f"GRANT SELECT, INSERT ON TABLE public.{table} TO anon, authenticated;"
      assert rigid_grant_pattern.search(multi_role_sql) is None, "False positive: 官方推薦寫法遭誤判"

      # 2. 多行標準排版 SQL
      multiline_sql = f"""GRANT SELECT,
          INSERT, UPDATE
      ON TABLE public.{table}
      TO authenticated;"""
      assert rigid_grant_pattern.search(multiline_sql) is None, "False positive: 多行語法遭誤判"
  ```

### 缺陷 2: RLS 語法缺少修飾詞容錯
- **嚴重等級**: P2 (Medium - 語法拘束誤報)
- **成因**: `ALTER\s+TABLE\s+(?:public\.)?{table}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY` 未能匹配 `IF EXISTS` 或 `ONLY`。
- **In-Memory PoC 存證**:
  ```python
  import re

  def test_rls_pattern_rejects_valid_defensive_syntax():
      table = "secure_records"
      valid_variants = [
          f"ALTER TABLE IF EXISTS public.{table} ENABLE ROW LEVEL SECURITY;",
          f"ALTER TABLE ONLY public.{table} ENABLE ROW LEVEL SECURITY;",
          f"ALTER TABLE IF EXISTS ONLY public.{table} ENABLE ROW LEVEL SECURITY;",
      ]
      rigid_rls_pattern = re.compile(
          rf"ALTER\s+TABLE\s+(?:public\.)?{table}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
          re.IGNORECASE
      )
      for sql in valid_variants:
          assert rigid_rls_pattern.search(sql) is None, f"Expected rigid regex to fail on: {sql}"
  ```

---

## 4. 候選補丁與精確替換指令 (Mantis Candidate Fixes)

- **補丁檔案**: [`docs/security/patch_candidate_sentinel_regex_2026-10-22.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/patch_candidate_sentinel_regex_2026-10-22.diff)
- **精確代碼區塊替換規格**:
  - **目標檔案**: `backend/tests/test_supabase_grants_sentinel.py`
  - **原始代碼 (Line 42-50)**:
    ```python
                    grant_pattern = re.compile(
                        rf"GRANT\s+.*ON\s+(?:TABLE\s+)?(?:public\.)?{table}\s+TO\s+(?:authenticated|service_role)",
                        re.IGNORECASE
                    )
                    rls_pattern = re.compile(
                        rf"ALTER\s+TABLE\s+(?:public\.)?{table}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
                        re.IGNORECASE
                    )
    ```
  - **替換為 (Hardened)**:
    ```python
                    grant_pattern = re.compile(
                        rf"GRANT\s+[\s\S]*?ON\s+(?:TABLE\s+)?(?:public\.)?{table}\s+TO\s+[^;]*(?:authenticated|service_role)",
                        re.IGNORECASE
                    )
                    rls_pattern = re.compile(
                        rf"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?(?:public\.)?{table}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
                        re.IGNORECASE
                    )
    ```
  - **視圖匹配 (Line 61-64)** 替換為:
    ```python
                    view_grant_pattern = re.compile(
                        rf"GRANT\s+[\s\S]*?SELECT\s+[\s\S]*?ON\s+(?:VIEW\s+)?(?:public\.)?{view}\s+TO\s+[^;]*(?:authenticated|service_role)",
                        re.IGNORECASE
                    )
    ```

---

## 5. 人類主權閘門 (Human Gate Handover)

依據 L0 憲法規範，Security Sentinel 僅產出漏洞驗證報告、In-Memory PoC 與候選補丁，**嚴禁在未獲人類主管授權前逕自套用修改**。
目前測試檔保持未加固狀態，隨時等待人類工程師（Ryan）指示實作或套用補丁。
