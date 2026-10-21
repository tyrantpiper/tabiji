# 📅 Daily Report - 2026-10-22 (Supabase 2026-10-30 Breaking Change Defense, Explicit DAC Grant Invariance & Sentinel Static AST Hardening)

> **系統狀態**：🟢 Production Ready & Remote Synchronized, 0 TypeScript Errors, 0 ESLint Warnings, 100% Tests Green (Seams 10/10 Intact, Pytest 2/2 Sentinel Passed), Supabase Live Production Migration Executed (`REDACTED_SUPABASE_REF`).  
> **今日關鍵研發範疇 (Core Focus)**：
> - 🛡️ **Supabase 2026-10-30 破壞性變更防線**：建立顯式 DAC 授權遷移 [`supabase/migrations/20261022_data_api_explicit_grants.sql`](file:///d:/Project/tabiji/travel-pwa/supabase/migrations/20261022_data_api_explicit_grants.sql)，線上生產庫執行成功。
> - 🔒 **AI 個人偏好表 RLS 補強與型別歸一化**：修復 `user_preferences` 未啟用 RLS 漏洞，落實 `auth.uid()::text = user_id::text` 雙向字串轉型防線（AD-143, FP-061）。
> - 🤖 **CI 靜態授權哨兵與正則容錯加固**：建立 [`backend/tests/test_supabase_grants_sentinel.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_supabase_grants_sentinel.py)，並經 Security Sentinel 獨立沙盒對抗證偽，完成多行與角色排列容錯升級（FP-062）。
> - 📊 **資安台帳數學守恆升級**：`security-coverage-ledger.json` 擴充至 163 目標（21 處已修復，17 處列管驗證，125 處已證偽排除）。

---

## 🏆 深度專案復盤：三大工程與資安里程碑 (Three Core Milestones)

---

### 里程碑一：防禦 Supabase 2026-10-30 關閉 Public Schema 自動授權之破壞性變更 (Explicit DAC Grants)

1. **背景與官方架構變革**：
   - Supabase 官方公告於 2026 年 10 月 30 日起，既有專案在 `public` schema 建立的新資料表，系統將不再自動授予 Data API（PostgREST / GraphQL / supabase-js）的存取權限。
   - 在 PostgreSQL 核心權限模型中，**資料表層級自主存取控制（DAC / `GRANT`）優先於列級安全性（RLS）被評估**。若未顯式賦予 `GRANT`，PostgREST 會在進入 RLS 評估之前直接拋出 `42501 permission denied`，導致本地重置（`supabase db reset`）、預覽分支（Preview Branches）及未來新環境全面癱瘓。
2. **遷移設計與前向兼容實施**：
   - 遵從遷移不可變原則，不篡改歷史遷移檔以防雲端雜湊漂移，建立前向遷移 [`supabase/migrations/20261022_data_api_explicit_grants.sql`](file:///d:/Project/tabiji/travel-pwa/supabase/migrations/20261022_data_api_explicit_grants.sql)。
   - 透過 `DO $$ ... DECLARE ... FOREACH tbl IN ARRAY tables` 動態安全迭代，針對全站 12 張核心業務表（`app_settings`, `expenses`, `itineraries`, `itinerary_items`, `medicines`, `notifications`, `profiles`, `push_subscriptions`, `trip_capsule_entries`, `trip_members`, `user_preferences`, `users`）依最小權限原則派發權限：
     - `anon`: `GRANT SELECT`
     - `authenticated`: `GRANT SELECT, INSERT, UPDATE, DELETE`
     - `service_role`: `GRANT ALL PRIVILEGES`
   - 同步為多日行程聚合視圖 `user_trips_view` 補齊 `GRANT SELECT`，並為所有序列（`ALL SEQUENCES IN SCHEMA public`）授予 `USAGE, SELECT`，保證自增 ID 與寫入管線暢通。
   - **實時線上驗收**：已透過 Supabase 管理端點在線上正式專案 `REDACTED_SUPABASE_REF` 執行完畢，零中斷驗證通過。

---

### 里程碑二：修復 `user_preferences` 歷史 RLS 缺失與型別運算子陷阱 (AD-143 & FP-061)

1. **漏洞挖掘與安全防護**：
   - 在審計歷史資料庫定義時，發現 [`backend/migrations/20260120_user_preferences.sql`](file:///d:/Project/tabiji/travel-pwa/backend/migrations/20260120_user_preferences.sql) 建立之使用者 AI 偏好記憶表缺少 `ENABLE ROW LEVEL SECURITY`。
   - 若開放 Data API 存取，匿名用戶可直接透過 PostgREST 讀取全體使用者的旅遊習慣、飲食限制與無障礙偏好。
   - 在新遷移中強制執行 `ALTER TABLE public.user_preferences ENABLE ROW LEVEL SECURITY;`，並建立個人唯讀與管理策略。
2. **PostgreSQL RLS 型別比對運算子陷阱 (FP-061)**：
   - 本地遷移定義 `user_id` 為 `TEXT`，而線上生產環境 Supabase 之 `user_id` 為 `UUID`。
   - 若策略撰寫為 `auth.uid()::text = user_id`，PostgreSQL 解析器在面對 UUID 欄位時會拋出 `ERROR 42883: operator does not exist: text = uuid` 致命錯誤阻斷執行。
   - 解決方案：策略統一宣告為 `auth.uid()::text = user_id::text`，實施雙向純字串歸一化，達到 100% 跨環境型別自洽。

---

### 里程碑三：CI 靜態哨兵建立與正則 AST 語意加固 (Sentinel Static AST Hardening)

1. **自動化守門測試 [`backend/tests/test_supabase_grants_sentinel.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_supabase_grants_sentinel.py)**：
   - 為了將 10/30 規範固化為團隊工程紀律，新增靜態掃描測試，在 CI 階段遍歷 `supabase/migrations/` 與 `backend/migrations/`。
   - 任何自 `20261022` 起新建之資料表與視圖，若未在同一檔案內包含顯式 `GRANT` 與 `ENABLE ROW LEVEL SECURITY`，測試立即亮紅燈阻斷提交。
2. **Security Sentinel 對抗式沙盒審查與雙重缺陷加固 (FP-062)**：
   - 啟動 Security Sentinel 調度獨立背景子代理人（`agy.exe --sandbox`）發動對抗審查，沙盒實證原始正則存在兩項假陽性誤判風險：
     1. **多行截斷缺陷**：原始正則 `GRANT\s+.*ON` 缺少 `re.DOTALL`，面對標準多行 SQL 排版（`GRANT ... \n ON ... \n TO ...`）時截斷匹配。
     2. **角色順序拘束缺陷**：`TO\s+(?:authenticated|service_role)` 寫死緊接角色，面對 Supabase 官方推薦之 `TO anon, authenticated;` 排版直接誤判。
     3. **RLS 修飾詞拘束**：`ALTER TABLE` 缺少 `(?:IF\s+EXISTS\s+)?(?:ONLY\s+)?`，無法識別防禦性 SQL。
   - 加固方案：升級為 `GRANT\s+[\s\S]*?ON\s+(?:TABLE\s+)?(?:public\.)?{table}\s+TO\s+[^;]*(?:authenticated|service_role)`，並於單元測試中雙向覆蓋正向防禦語法與反向漏洞阻斷。

---

## 🏛️ 架構決策記錄 (Architecture Decisions)

- **AD-143: Supabase PostgREST 顯式 DAC 授權與 RLS 雙軌防衛法則 (Explicit DAC Grant Invariance & RLS Type Normalization)**:
  - *Context*: Supabase 於 2026-10-30 關閉 Public Schema 預設 DAC 授權，且雲端生產庫與本地環境存在 `user_id` (UUID vs TEXT) 型別歧異。
  - *Decision*: 所有新表與視圖必須在建立檔案內顯式派發 `GRANT` 至 `anon, authenticated, service_role`，並強制宣告 `ENABLE ROW LEVEL SECURITY`；RLS 策略中的身份驗證必須雙向轉型為純文字比對（`auth.uid()::text = user_id::text`）。
  - *Trade-off*: 每次撰寫 Migration 需多寫 3~5 行 SQL，但徹底解除了 10/30 後環境重建 API 報警（42501）與跨環境型別崩潰（42883）的根本風險。

---

## 🛡️ 踩坑記錄與經驗結晶 (Failed Paths)

- **FP-061 (PostgreSQL RLS 型別比對運算子遺漏陷阱)**:
  - *Symptom*: 在 Supabase RLS 策略中撰寫 `auth.uid()::text = user_id` 時，若資料表欄位為 `UUID`，PostgreSQL 報錯 `ERROR: 42883 (operator does not exist: text = uuid)`。
  - *Lesson*: Postgres 不會自動跨型別隱式轉換 `text` 與 `uuid`。修復準則：所有 RLS 等號兩端必須雙向轉型 `auth.uid()::text = user_id::text`。
- **FP-062 (CI 靜態正則缺 `re.DOTALL` 與角色排列硬編碼誤報陷阱)**:
  - *Symptom*: CI 靜態掃描測試使用 `.*` 且寫死 `TO (authenticated|service_role)`，導致合法的多行 SQL 與 `TO anon, authenticated;` 被判為未授權，CI 假陽性阻斷。
  - *Lesson*: 靜態代碼分析器正則必須使用 `[\s\S]*?` 穿透跨行換行符，並以 `[^;]*` 支援逗號分隔的任意角色排列順序。

---

## 🎯 明日核心衝刺目標 (Next Steps)

1. **多端推播導航雙軌協議驗證**：持續追蹤 Service Worker 背景推播到達率與喚醒流程。
2. **邊緣 D1 口袋庫離線同步壓力驗證**：壓測 5,000+ POI 口袋庫在弱網環境下與 Supabase 行程資料夾之關聯穩定度。
3. **全棧生產環境持續監控**：確保 10/30 Supabase 雲端政策正式切換當天 0 異常。

---

## 🧬 Machine-Executable Invariant Rules
```json
[
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BACKEND-031",
    "title": "Supabase PostgREST 顯式 DAC 授權與 RLS 雙軌防衛法則 (AD-143)",
    "content": "PostgreSQL 中 DAC 權限 (GRANT) 優先於 RLS。Supabase 2026-10-30 關閉 public 預設 ACL 後，所有新建或重構表格必須在同一 Migration 內顯式向 anon, authenticated, service_role 派發 DAC 存取權，否則 PostgREST 在 DAC 檢查階段即阻斷連線 (42501)；同時，跨型別 RLS 比較必須實施雙向純字串正規化 (auth.uid()::text = user_id::text)，防止 operator does not exist: text = uuid 型別崩潰。"
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-DEVOPS-032",
    "title": "靜態 AST/正則哨兵多行與修飾詞容錯法則 (Sentinel Multiline & Regex Tolerance Invariance)",
    "content": "CI/CD 靜態安全分析器比對 SQL DDL 時，嚴禁使用單行 .* 與硬編碼角色鄰接。必須統一採用 [\\s\\S]*? 穿透多行排版，以 [^;]* 容納逗號分隔的角色任意排列，並對 ALTER TABLE 注入 (?:IF\\s+EXISTS\\s+)?(?:ONLY\\s+)? 修飾詞容錯，杜絕 CI 假陽性 (False Positive) 阻斷正常交付管線。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-061",
    "title": "PostgreSQL RLS 型別比對運算子遺漏陷阱",
    "content": "在 Supabase RLS Policy 中撰寫 auth.uid()::text = user_id 時，若 user_id 為 UUID 型別，PostgreSQL 會報 operator does not exist: text = uuid (42883) 阻斷 Migration。修復準則：一律採用 auth.uid()::text = user_id::text 進行雙邊字串歸一化比對。"
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-062",
    "title": "CI 靜態正則缺 re.DOTALL 與角色排列硬編碼誤報陷阱",
    "content": "CI 靜態掃描測試使用 .* 且寫死 TO (authenticated|service_role)，導致合法的多行 SQL 與 TO anon, authenticated; 被判為未授權，CI 假陽性阻斷。修復準則：靜態代碼分析器正則必須使用 [\\s\\S]*? 穿透跨行換行符，並以 [^;]* 支援逗號分隔的任意角色排列順序。"
  }
]
```
