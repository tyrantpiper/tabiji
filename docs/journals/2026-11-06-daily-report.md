# 📅 Daily Report - 2026-11-06 (Unauthenticated Visitor Toast Suppression, Unified CLI Duel Automation, Dual-Track Spec DAG Engine, Deep Geocoding Pipeline & Subdomain SSRF Hardening)

> **系統狀態**：🟢 Production Ready & Security Sentinel v2.5.0 Hardened, 0 TypeScript Errors (`tsc --noEmit`), 0 ESLint Warnings, 100% Tests Green (Frontend Vitest: 88/88 Files, 589/589 Tests Passed; Backend Pytest: 357 Collected, 352 Passed, 5 Skipped, 0 Warnings; Root Hygiene Sentinel: Clean), Security Ledger 259 Targets (58 Remediated, 51 Verified, 150 Dismissed, 100% 數學守恆 + `known_design_intents` 歷史決策防線).
> **今日關鍵研發範疇 (Core Focus)**：
> - 🛡️ **未登入訪客首頁虛警 Toast 根因修復與事件源標籤過濾閉環 (Unauthenticated Visitor Toast False Alarm Suppression & Event Source Tagging, AD-201, SPEC-AUTH-003)**：徹底排查未登入訪客首次進入網站首頁 (`/`) 即彈出「✨ 帳號引繼碼已自其他裝置同步更新」之惡性誤報。透過重構事件承載契約，標註四種來源並於 `AppClientLayer` 與 `auth-session.ts` 建立雙層防衛，訪客不再受到虛警打擾。
> - ⚔️ **紅藍軍對抗全自動工作流原生整合至 Sentinel CLI (`runner.py --mode duel`, SPEC-AGY-002 v1.4.0, AD-202)**：深度融合 Red Team 與 Blue Team，於 [`scripts/lib/adversarial_team.py`](file:///d:/Project/tabiji/travel-pwa/scripts/lib/adversarial_team.py) 實作 `orchestrate_adversarial_duel` 四階段全自動協調器，並為 `runner.py` 擴充 `--mode {adaptive,duel,fast}` 命令列參數，自動調度 `GitWorktreePool` 執行實體沙盒對抗閉環。
> - 🧬 **次世代雙螺旋工程規格引擎 (Dual-Track Spec DAG Engine, AD-204, SPEC-AGY-003)**：融合 Google (Non-Goals/Alternatives Matrix)、Anthropic (階梯式蘇格拉底探針)、Perplexity (外部情報雷達)、Cloudflare/Supabase (RLS 安全矩陣與 50ms 邊緣故障模型) 與 GitHub MADR 規範。重構 `/Idea to Spec` 與 `/grill-me`，建立「宏觀確定性 DAG ✕ 微觀隨機自適應 Agent Loop」架構，以 Fast-Track（保留 1 輪速成優勢）與 Deep-DAG（5 節點防衛管線）雙軌並存，徹底摧毀 Vibe Coding 崩塌與 100K Token Dumb Zone 智商衰竭。
> - 🧹 **後端 Pytest 測試警訊清零與加密/Mock 規範合規 (AD-205, SPEC-DEF-002)**：全面根治 `backend/tests/` 內殘留之 4 項 Pytest 警訊。將 `test_phase4_sync_deadlock_poc.py` 的偽造 HS256 金鑰提升至 39 位元組，嚴格合規 RFC 7518 Section 3.2（$\ge 32$ bytes）；重構 `test_poi_lifespan.py`，廢除 `with mocker.patch(...)` 雙重上下文語法，改採 `mock_labels.return_value = ...` 重新賦值，使測試輸出達成純淨零警告。
> - 🧭 **筆記文字匯入深層空間定位管線（Deep Geocoding Pipeline for Markdown Note Import, AD-206, SPEC-GEO-004）**：全鏈路重構 `/api/ai/parse-md` 端點，補齊以往遺漏的經緯度自動檢索能力。整合 `MolecularParser` 零成本 URL 直解、自癒型母體空間偏置推算、Semaphore(10) + 2.5s 逾時並發保護、動作噪音過濾與確定性貨幣推斷。經真實 Chrome DevTools MCP 與 Supabase 落盤遙測，經緯度覆蓋率達 **90.5%**（19/21 筆精準取得），MapLibre WebGL 正確渲染 69.2 km 路線與 15h 24m 交通耗時。
> - ⚡ **模型路由快速降級策略消除 Next.js Dev API Proxy 503/ECONNRESET 逾時（AD-207）**：針對 Google 雲端模型擁塞引發之代理逾時（socket hang up），顯式指定 `routing_strategy=["gemini-3.1-flash-lite", ...]` 優先調用 0.9s 極速模型，將筆記結構解析縮減至 1~2s 內完成。
> - 🛡️ **次級網域偽造 SSRF 邊界加固與 Security Sentinel 6 階段完整閉環 (AD-208, SPEC-AGY-002 v1.5.0)**：發掘正則表達式缺失結尾錨點（`maps.app.goo.gl.attacker.com` 繞過），升級為 `(?:/|\?|$)` 封死漏洞；擴展資安台帳至 259 項目標（58 Remediated + 51 Verified + 150 Dismissed），維持絕對數學守恆。
> 
> ---
> 
> ## 🏆 深度專案復盤：七大核心工程里程碑 (Seven Core Milestones)

---

### 里程碑一：未登入訪客首頁虛警 Toast 根因修復與事件源標籤過濾閉環 (AD-201, SPEC-AUTH-003)

1. **問題現象與根因溯源**：
   - 使用者反映：未登入使用者只要進入網站首頁 (`/`)，畫面上方就會彈出 Sonner 輕量通知：「✨ 帳號引繼碼已自其他裝置同步更新」。
   - **深層根因 (Root Cause)**：
     - [`frontend/components/app-client-layer.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/components/app-client-layer.tsx) 掛載了對自訂事件 `tabiji:recovery_key_updated` 的全域監聽器，原本的處理函式無條件直接彈出 Toast，並未校驗使用者當前是否為已登入狀態，亦未檢查該事件是由本機初始化還是異地遠端廣播所觸發。
     - 與此同時，[`frontend/lib/auth-session.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/lib/auth-session.ts) 的 `initSessionLifecycleListener()` 在初次掛載 (`handleReconnectOrResume()`) 時，若檢查到 `!getCachedToken()`，會自動觸發 `ensureValidSession()`。
     - `ensureValidSession()` 向後端發起 `/api/auth/session` 請求為訪客簽發臨時訪客憑證時，因獲得了新引繼碼，遂派發了 `tabiji:recovery_key_updated`。
     - 兩者疊加，導致每位無憑證訪客造訪首頁時，皆會觸發「已自其他裝置同步更新」的嚇人誤報。
2. **切斯特頓圍欄考古與承接機制 (Chesterton's Fence Handover)**：
   - **功能反推 (`legacy_function`)**：該 Toast 之所以存在，是為了消滅「跨裝置憑證輪替黑洞」。當使用者在裝置 A 輪替引繼碼，Supabase Realtime 向裝置 B 廣播 `CREDENTIAL_ROTATED`，裝置 B 之 `fetchLatestRecoveryKey()` 需即時通知使用者金鑰已更新，避免使用者誤抄過期金鑰。
   - **設計初衷 (`design_intent`)**：提供無縫的跨裝置狀態透明度。
   - **精準修正方案**：
     - **語意化事件來源標記 (`detail.source`)**：為 `tabiji:recovery_key_updated` 事件注入來源標籤：
       - `initial_bootstrap` / `session_exchange`：本機訪客或首次會話交換。
       - `remote_sync`：真正由 Supabase Realtime 觸發之跨裝置雲端校準。
       - `local_reanchor`：本機手動輸入引繼碼熱重錨。
     - **雙重守衛**：在 `AppClientLayer` 中強制加入：
       ```typescript
       if (!isUserLoggedIn()) return;
       if (customEvent.detail?.source !== "remote_sync") return;
       ```
     - **訪客換票節流**：在 `auth-session.ts` 的 `handleReconnectOrResume` 開頭加入 `if (!isUserLoggedIn()) return;`，阻斷未登入訪客造訪首頁時無意義向後端換取訪客憑證之效能浪費。

---

### 里程碑二：紅藍軍對抗全自動工作流原生整合至 Sentinel CLI (`runner.py --mode duel`, AD-202)

1. **三權分立的架構痛點**：
   - 過去架構中，`sentinel-attacker`（紅軍）負責建構攻擊 PoC，`sentinel-defender`（藍軍）負責切斯特頓圍欄考古抗辯，但兩者僅能透過 IDE 交談動態 `define_subagent` 手動調度，與批次命令列工具 `runner.py` 處於脫節狀態。
2. **方案一落地：四階段自動化對抗協調器 (`orchestrate_adversarial_duel`)**：
   - 於 [`scripts/lib/adversarial_team.py`](file:///d:/Project/tabiji/travel-pwa/scripts/lib/adversarial_team.py) 實作 `orchestrate_adversarial_duel`：
     - **Phase 1 (紅軍假說評估)**：自動讀取目標程式碼與歷史意圖，調用紅軍建構獨立 `pytest` PoC；若紅軍自主判定現有代碼已具備防禦，即刻以 `verdict: "DISMISSED"` 提前結束，節約 Worktree 資源。
     - **Phase 2 (Worktree 實體紅燈擊穿)**：在隔離沙盒中執行 `pytest -k "not benign"`，要求嚴格 `exit code == 1`（證明確有漏洞擊穿）。若傳回 `exit code == 0`，代表防禦依然穩固，依「無罪推定」判定 `DISMISSED`。
     - **Phase 3 (藍軍切斯特頓考古審查)**：紅燈成立時，調動藍軍進行切斯特頓三問考古。若藍軍舉證為刻意系統設計（如 SSOT 分拆計算、狀態重置），判定 `DISMISSED` 駁回誤判。
     - **Phase 4 (補丁合成與 Mantis Block G 綠燈檢驗)**：套用 `block_replacement`，執行全量測試，要求攻擊與良性對照測試雙過 (`exit code == 0` 且 `benign_control_passed == True`)，正式輸出 `CONFIRMED` 候選修復。
3. **CLI 三模態擴充 (`runner.py --mode {adaptive,duel,fast}`)**：
   - `--mode duel`：全自動對抗模式，每個候選目標自動分配 `GitWorktreePool` 沙盒執行完整 4 階段對抗。
   - `--mode adaptive`（預設）：自適應模式，維持批次平行靜態快篩，僅對 `high`/`critical` 目標自動啟用 Worktree 實體驗證。
   - `--mode fast`：純靜態極速審查模式，跳過 Worktree 建立與實體 pytest 執行。

---

### 里程碑三：Mantis Block G 良性對照與切斯特頓圍欄考古雙重閉環 (AD-203)

1. **訪客 Toast 假說的先紅後綠與防閹割實證**：
   - 於 [`frontend/__tests__/unauth-visitor-toast-sentinel-poc.test.ts`](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/unauth-visitor-toast-sentinel-poc.test.ts) 建立 5 大測試案例：
     - **TC-1 (漏洞復現)**：未登入訪客接收事件，在舊邏輯下 100% 觸發誤報 Toast（紅燈證明）。
     - **TC-2 (Mantis Block G 良性對照)**：合法登入用戶接收 `remote_sync` 事件，必須依然觸發 Toast，保證修復未閹割既有功能。
     - **TC-3 (運算子優先級漏洞)**：孤兒金鑰邊界狀態測試。
     - **TC-4 & TC-5 (防禦驗證)**：修復後之 `AppClientLayer` 與 `initSessionLifecycleListener` 徹底靜默訪客誤報。
2. **對抗協調器 7 大單元測試覆蓋**：
   - 於 [`backend/tests/test_sentinel_duel_orchestrator.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_sentinel_duel_orchestrator.py) 驗證紅軍早退、防禦未擊穿、藍軍考古駁回、實體紅轉綠、以及 `runner.py` 在 `duel` 與 `fast` 模式下的行為一致性，測試耗時僅 0.07s，達成 100% 綠燈。

---

### 里程碑四：資安覆蓋台帳擴展至 252 項目標與數學守恆 100% 達成 (SPEC-AGY-002)

1. **新入帳目標與驗證結論**：
   - `scripts/lib/adversarial_team.py:missing_attacker_defender_duel_orchestrator` ➔ `REMEDIATED`（完成 4 階段對抗編排器實作）。
   - `.agents/skills/security-sentinel/scripts/runner.py:unintegrated_mode_switch_and_duel_dispatch` ➔ `REMEDIATED`（完成 `--mode duel` CLI 調度與 Worktree 接軌）。
   - `.agents/skills/security-sentinel/SKILL.md:fragmented_subagent_and_runner_documentation` ➔ `DISMISSED`（藍軍切斯特頓考古證實 Tier 1 CLI 自動化與 Tier 2 IDE 交談式協同為互補分層架構，非規格漂移）。
2. **台帳守恆性校驗**：
   - 執行 `python scripts/validate_security_ledger.py`：
   - `total_targets`: 255
   - `remediated_vulnerabilities`: 54
   - `verified_vulnerabilities`: 51
   - `dismissed_hypotheses`: 150
   - 數學恆等式：$54 + 51 + 150 = 255$ 完全閉環。

---

### 里程碑五：次世代雙螺旋工程規格引擎 (Dual-Track Spec DAG Engine, AD-204, SPEC-AGY-003)

1. **核心動機與全球頂尖巨頭範式融合**：
   - 針對 `/Idea to Spec` 與 `/grill-me` 進行地毯式架構重構，汲取 Google (Non-Goals、Alternatives Considered 權衡矩陣)、Anthropic (階梯式蘇格拉底探針 L1 ➔ L2 ➔ L3)、Perplexity (外部情報接地)、Cloudflare/Supabase (RLS 安全矩陣與 50ms 邊緣故障模型)、Vercel (RSC 邊界拓撲) 與 GitHub MADR 規範。
2. **宏觀 DAG ✕ 微觀 Agent Loop 臨床診療指引模型**：
   - 採用臨床 ACLS（進階心臟救命術）處置樹類比：宏觀骨架由確定性 DAG 掌管拓撲推進與硬性門禁，微觀節點嵌入有界的 Agent 自適應循環（如 CPR 2 分鐘循環），並透過「Facts vs Decisions」原則（代碼庫查得到的絕不發問）大幅縮減無謂對話。
3. **雙軌執行模式 (Fast-Track vs Deep-DAG)**：
   - **Fast-Track**：保留原本單輪速成的輕量規格體驗，零摩擦生成 5 段式規格。
   - **Deep-DAG**：啟動 5 節點深度防衛管線，整合外部 5 秒熔斷器、短路逃生艙、抛棄式 UI 沙盒實驗（`<conversation_dir>/scratch/proto/` 嚴防目錄穿越），以及簽核前的自動化紅軍合約審查。
4. **實裝與本機配置升級**：
   - 成功更新本機全域技能 [`C:\Users\Ryan su\.gemini\config\skills\idea-to-spec\SKILL.md`](file:///C:/Users/Ryan%20su/.gemini/config/skills/idea-to-spec/SKILL.md) 至 v2.1.0。

---

### 里程碑六：後端 Pytest 測試警訊清零與加密/Mock 規範合規 (AD-205, SPEC-DEF-002)

1. **RFC 7518 HS256 金鑰長度安全閾值修復**：
   - 在 [`backend/tests/test_phase4_sync_deadlock_poc.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_phase4_sync_deadlock_poc.py) L200 與 L231 中，將模擬攻擊者偽造 Token 的金鑰由 22/11 位元組提升至 39 位元組（`attacker_forged_secret_key_32bytes_long!` 與 `fake_secret_key_minimum_32_bytes_long!`），完全合規 RFC 7518 Section 3.2 對 HMAC-SHA256 的 32 位元組下限，徹底清零 `InsecureKeyLengthWarning`。
2. **pytest-mock 生命週期語法除垢**：
   - 在 [`backend/tests/test_poi_lifespan.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_poi_lifespan.py) L131/L141 中，移除 `with mocker.patch(...)` 雙重上下文語法，改採 `mock_labels.return_value = ...` 重新賦值，使 pytest 框架乾淨接管 mock 恢復，徹底清零 `PytestMockWarning`。
3. **測試輸出純淨度**：
   - 14 項測試收集：11 passed, 3 skipped, **0 warnings**（警告完全歸零）。

---

### 里程碑七：筆記文字匯入深層空間定位管線（Deep Geocoding Pipeline for Markdown Note Import, AD-206, SPEC-GEO-004）

1. **問題現象與使用者直覺印證**：
   - 使用者提問：「為什麼 AI 生成行程 (`/generate-trip`) 經緯度準確率極高，但筆記文字匯入 (`/parse-md`) 解析後完全不抓取各自的經緯度？」
   - **實證分析**：
     - AI 生成行程之所以精準，是因為具備標準名詞收斂、提示詞初階座標注入、母體中心點偏置 (`bias_lat`, `bias_lng`) 以及後端 `_safe_geocode` (Semaphore + Timeout) 批次補齊。
     - 過去筆記匯入端點僅執行純文字擷取，完全未對接 Geocoding 管線或 `MolecularParser`，回傳座標全數為 `null`，造成地圖標記無法渲染且路線里程為 0。
2. **端點內聚架構實作**：
   - 在 [`backend/routers/ai.py`](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py) 實作深層定位管線：
     - **Step 1 (MolecularParser 零成本 URL 直解)**：利用正規表達式與 CID 向量，直接自 Google Maps URL 秒解精準座標，完全不發送網路請求。
     - **Step 2 (自癒型動態空間偏置推算)**：若筆記標題為「5天4夜自由行」等泛稱，自動將首個已解出座標之項目晉升為母體中心點（Self-Bootstrapping Anchor），解決全域空間漂移。
     - **Step 3 (並發檢索與短網址救援)**：以 `asyncio.Semaphore(10)` 與單項 2.5s 超時熔斷防護，過濾「集合/搭乘/休息/退稅」等動作噪音，專注查詢實體景點。
     - **Step 4 (確定性幣別與日期注入)**：根據目的地推斷 ISO 貨幣代碼。
3. **實體遙測與驗收**：
   - 經 Chrome DevTools MCP 與 Supabase DB 遙測（行程 `3747ac9a-2672-4a0d-bba7-719af754f2ad`）：21 項景點中 19 筆獲得精準座標（**90.5% 覆蓋率**），MapLibre WebGL 渲染全圖釘、里程 69.2 km、交通耗時 15h 24m。

---

### 里程碑八：模型路由快速降級策略消除 Next.js Dev API Proxy 503/ECONNRESET 逾時（AD-207）

1. **問題現象**：
   - 長文或多日筆記送出解析時，Next.js API proxy 偶發出現 500 `socket hang up` (ECONNRESET)。
2. **根因剖析**：
   - Google 雲端 `gemini-3.8-flash` 偶發遭遇 503 伺服器端過載，後端模型管理器在多層級退避時耗時超過 30 秒，觸發 Next.js dev server proxy 連線中斷。
3. **修復措施**：
   - 於 `call_extraction` 顯式注入優先快速路由 `routing_strategy=["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.8-flash"]`。
   - 由 0.9 秒極速回傳之 `gemini-3.1-flash-lite` 作為第一道防線，消除長文逾時中斷風險。

---

### 里程碑九：Security Sentinel 對抗審查與次級網域偽造 SSRF 邊界加固（AD-208, SPEC-AGY-002 v1.5.0）

1. **對抗審核與實體沙盒刺探**：
   - 建立候選假說與實體沙盒測試 [`backend/tests/test_parse_md_geocoding_sentinel_poc.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_parse_md_geocoding_sentinel_poc.py) (4/4 passed in 2.54s)。
   - 驗證 SSRF 拒絕、型別混淆防禦 (`_safe_float`)、自癒動態錨點、並發 Semaphore 與 2.5s 逾時熔斷。
2. **深層次級網域偽造漏洞發掘與即刻加固**：
   - 原始正則 `r'^https?://(maps\.app\.goo\.gl|...)'` 缺失主機名結尾邊界，允許 `https://maps.app.goo.gl.attacker.com` 繞過白名單。
   - 立即追加 `(?:/|\?|$)` 邊界錨點，並於測試案例中加入對抗測資驗證封堵。
3. **台帳守恆與審核報告**：
   - 資安覆蓋台帳更新至 259 項目標（58 Remediated + 51 Verified + 150 Dismissed），`validate_security_ledger.py` 綠燈守恆。
   - 產出審查報告 [`docs/security/reports/2026-11/security_sentinel_report_2026-11-06_parse_md_geocoding.md`](file:///d:/Project/tabiji/travel-pwa/docs/security/reports/2026-11/security_sentinel_report_2026-11-06_parse_md_geocoding.md)。

---

## 🏛️ 架構決策紀錄 (Architecture Decision Records)

- **AD-201 (Event Source Tagging & Dual-Guard Toast Suppression - SPEC-AUTH-003)**:
  - **Context**: `AppClientLayer` 無差別監聽 `tabiji:recovery_key_updated`，未登入訪客造訪首頁時觸發 `ensureValidSession()` 產生金鑰更新事件，誤彈出跨裝置同步 Toast。
  - **Decision**: 擴充 `tabiji:recovery_key_updated` 之 `detail.source` 欄位契約 (`initial_bootstrap`, `session_exchange`, `remote_sync`, `local_reanchor`)；`AppClientLayer` 實施 `!isUserLoggedIn()` 與 `detail.source !== "remote_sync"` 雙重過濾；`initSessionLifecycleListener` 在未登入時跳過首頁自動換票。
  - **Trade-offs**: 稍微增加事件資料負載，但徹底根除首頁誤報，並減少未登入訪客對後端換票端點的無效請求。
- **AD-202 (Unified Dual-Core CLI Adversarial Automation via `runner.py --mode duel` - SPEC-AGY-002 v1.4.0)**:
  - **Context**: 紅軍 (`sentinel-attacker`) 與藍軍 (`sentinel-defender`) 原先散落在 IDE交談子代理人中，缺乏與 CLI 批次審查工具之程式碼整合，開發者難以一鍵啟動自動化紅藍軍實體沙盒對抗。
  - **Decision**: 採納方案一，於 `scripts/lib/adversarial_team.py` 封裝 `orchestrate_adversarial_duel`，並為 `runner.py` 增設 `--mode {adaptive,duel,fast}` 參數，將 GitWorktreePool、PoC 紅燈擊穿、切斯特頓考古抗辯、Mantis Block G 補丁合成與良性對照檢驗無縫串接。
  - **Trade-offs**: 執行 `--mode duel` 時因需建立實體 Git Worktree 與執行兩輪 pytest，耗時約 2~4 秒，但換取 100% 先紅後綠之極致真實性與零 prompt 污染。
- **AD-203 (Mantis Block G Benign Control Invariant for Auth Toast Remediations)**:
  - **Context**: 修復未登入訪客 Toast 時，若修復手段為粗暴刪除監聽器或全面禁止 Toast，將破壞合法多裝置使用者在雲端金鑰輪替時的知情權（閹割補丁）。
  - **Decision**: 嚴格遵守 Mantis Block G，在測試與補丁中設立良性對照組（`TC-2`），確認合法登入用戶接收 `remote_sync` 時仍能正常顯示 Toast，守護既有業務能力。
  - **Trade-offs**: 必須在測試套件中維護雙重狀態 Mock，但確保代碼品質達到零降級（Zero-Regression）。
- **AD-204 (Dual-Track Spec DAG Engine & Socratic Ingestion Architecture - SPEC-AGY-003)**:
  - **Context**: 舊版 `idea-to-spec` 與 `/grill-me` 為線性對話，缺乏 DAG 剪枝容易引發決策疲勞；同時長對話超過 100K Token 進入 Dumb Zone 智商衰減，且文字爭論高精細度 UI 動效效率極低。
  - **Decision**: 建立確定性 DAG 骨架並在局部嵌入 Agent Loop；嚴格實施階梯質詢（L1 ➔ L2 ➔ L3）；遇高精細度 UI 即刻分流至拋棄式沙盒實驗；以 Fast-Track 保留單輪速成，以 Deep-DAG 承接大型架構設計；紅軍自動稽核移至人類簽核之前以杜絕簽核後漂移。
  - **Trade-offs**: 深度模式對話前置思考密度較高，但消除 90% 下游返工與架構腐敗。
- **AD-205 (Pytest Mock Lifecycle & Cryptographic Key Length Hygiene - SPEC-DEF-002)**:
  - **Context**: 後端測試執行時出現 4 項警告（PyJWT 密鑰過短警告與 pytest-mock 雙重上下文退出警告），影響 CI 乾淨度。
  - **Decision**: 密鑰生成強制遵守 RFC 7518（長度 $\ge 32$ 位元組）；全面統一使用 pytest-mock 標準模式管理 mock 生命週期，禁止在 fixture 上疊加 `with` 語法。
  - **Trade-offs**: 稍微增加測試字串長度，但換取完全零警告的乾淨測試環境。
- **AD-206 (Deep Geocoding Pipeline & Self-Bootstrapping Proximity Bias for Markdown Import - SPEC-GEO-004)**:
  - **Context**: 過去 `/api/ai/parse-md` 僅擷取文字，無經緯度座標，導致匯入之行程地圖無法渲染、路線無距離。前端多次非同步補查架構脆弱且引發大量競態。
  - **Decision**: 採用端點內聚架構，於後端依序串接：(1) MolecularParser 零成本 URL 直解；(2) 動態空間偏置（若標題泛稱則自動從首個已解出座標自癒晉升為母體中心點）；(3) `asyncio.Semaphore(10)` 與 2.5s 逾時熔斷之並發檢索；(4) 動作噪音過濾；(5) 確定性貨幣與日期推斷。
  - **Trade-offs**: 後端解析耗時微幅增加（+0.5~1.5s），但前端獲得完整的結構化資料，完全消除二階段異步補查之競態與覆蓋黑洞。
- **AD-207 (Fast-Lite Fallback Strategy for High-Latency Note Extraction)**:
  - **Context**: 預設調用 `gemini-3.8-flash` 偶發遇到 Google 雲端 503 超時與退避，耗時 > 30s 導致 Next.js Dev API Proxy 觸發 `socket hang up` (ECONNRESET)。
  - **Decision**: 在 `parse_markdown` 中顯式傳入 `routing_strategy=["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.8-flash"]`，優先由 0.9s 回傳之極速模型處理長文擷取。
  - **Trade-offs**: 稍微限制單次輸出的極度長文複雜度，但徹底杜絕 Proxy 500 連線崩潰。
- **AD-208 (Subdomain Boundary Hardening on URL Whitelist)**:
  - **Context**: 檢查 Google Maps 網址之正則表達式缺失主機邊界錨點，允許 `https://maps.app.goo.gl.attacker.com` 繞過白名單發起外部請求。
  - **Decision**: 在正規表達式主機結尾強制追加 `(?:/|\?|$)`，並將此測資固化於 Sentinel 對抗測試套件中。
  - **Trade-offs**: 無。零成本提升 SSRF 防禦邊界。

---

## 🛡️ 失敗路徑與經驗教訓 (Failed Paths & Hard Lessons)

- **FP-012 (Windows PowerShell `-p` 參數與 Flag 擺放順序陷阱)**:
  - **Symptom**: 在 `runner.py` 呼叫 `agy.exe` 時，若將 `-p` 放在前面且後方接 `--sandbox`（如 `agy.exe -p <prompt> --sandbox`），PowerShell 會將 `--sandbox` 誤判定為 `-p` 的參數值，拋出 `Error: -p took "--sandbox" as its prompt`。
  - **Resolution**: 在命令列陣列中一律採用 `f"-p={cli_prompt}"` 格式，並將 `--sandbox`、`--disable-slash-commands`、`--output-format json` 等標誌固定前置。
- **FP-013 (`agy.exe` 子代理人預設 Token 上限與 Thinking 截斷陷阱)**:
  - **Symptom**: 在批次審查時若將超過 60,000 字元的全量檔案直傳給 `agy.exe`，模型產生的思考權杖 (Thinking Tokens, 約 580+) 會耗盡 CLI 預設輸出額度，導致 JSON 回應被截斷為空字串，產生 `INCONCLUSIVE`。
  - **Resolution**: 審計目標必須指定 `start_line` 與 `end_line` 精確局部切片，將上下文限制在 40~100 行核心區塊，徹底消除 Token 耗盡截斷問題。
- **FP-014 (`isUserLoggedIn()` 跨測試依賴隱藏邊界 - 孤兒金鑰陷阱)**:
  - **Symptom**: 最初嘗試將 `isUserLoggedIn()` 簡化為嚴格要求 `user_nickname && user_uuid`，導致 `auth-session-resilience.test.ts` 的 TC-10 與 TC-11 失敗。
  - **Resolution**: 原來 TC-10/TC-11 刻意設計了「僅有 `user_recovery_key` 但缺乏 `user_nickname`」的極端情況，期望在 401 時觸發 `SessionReauthModal` 原地重錨，而非直接靜默清空會話。修復時必須區分 `handleReconnectOrResume`（僅服務具備完整身分之活躍用戶）與 `isUserLoggedIn` 本身的型別容錯定義。
- **FP-015 (Gate Sequence Inversion Trap in Multi-Stage Agent Pipelines)**:
  - **Symptom**: 在設計自動化規格流水線時，若將「人類簽核門禁」置於「紅軍自動合約修補」之前，一旦紅軍自動套用 Patch 修補漏洞，最終交付實作的規格將未經人類審批，架空 L0 人類主權。
  - **Resolution**: 紅軍修補與合約自檢必須在內部完全收斂（Green），人類簽核永遠是交付實作前的最後一棒（Final Gate）。
- **FP-016 (Pytest-mock Context Manager Double-Exit Warning Trap)**:
  - **Symptom**: 在 pytest 測試函式中使用 `with mocker.patch(...)` 會觸發 `PytestMockWarning`，因為 `mocker` fixture 已經在函式層級自動託管了生命週期。
  - **Resolution**: 移除 `with` 語法，跨情境直接透過 `mock_obj.return_value = ...` 重新指定模擬值。
- **FP-017 (Next.js Dev Proxy Socket Hang Up under Gemini 3.8 Multi-Tier Backoff)**:
  - **Symptom**: 前端調用 `/api/ai/parse-md` 偶發出現 500 ECONNRESET，排查發現後端因 Google 雲端 503 重試超過 30 秒，觸發前端 Next.js http-proxy 逾時中斷。
  - **Resolution**: 顯式指定極速模型路由策略 `routing_strategy=["gemini-3.1-flash-lite", ...]`，0.9 秒回傳排除逾時。
- **FP-018 (Subdomain Spoofing in Unanchored Domain Regex Whitelist)**:
  - **Symptom**: 正則表達式 `r'^https?://(maps\.app\.goo\.gl|...)'` 允許 `maps.app.goo.gl.attacker.com` 匹配成功，產生 SSRF 穿透盲區。
  - **Resolution**: 必須在主機名稱結尾嚴格錨定 `(?:/|\?|$)`。
- **FP-019 (Action Noise False Geocoding Query Overhead)**:
  - **Symptom**: 行程筆記中的「集合/搭乘/休息/退稅」等動作項目被送往地理編碼，造成無效網路開銷與錯誤座標。
  - **Resolution**: 建立 `ACTION_NOISE_KEYWORDS` 過濾機制，阻斷動作項目發起地理查詢。

---

## 🧬 Machine-Executable Invariant Rules

```json
[
  {
    "domain": "state_cache",
    "type": "INVARIANT_RULE",
    "id": "INV-AUTH-005",
    "title": "Unauthenticated Visitor Session Lifecycle & Recovery Toast Isolation",
    "content": "In frontend/components/app-client-layer.tsx and frontend/lib/auth-session.ts, unauthenticated visitors accessing '/' MUST NOT trigger toast notifications for '✨ 帳號引繼碼已自其他裝置同步更新' or automatically call ensureValidSession() on mount/reconnect. All tabiji:recovery_key_updated custom events MUST carry a detail.source tag ('initial_bootstrap', 'session_exchange', 'remote_sync', 'local_reanchor'). AppClientLayer MUST filter strictly with 'if (!isUserLoggedIn()) return;' and 'if (customEvent.detail?.source !== \"remote_sync\") return;'."
  },
  {
    "domain": "state_cache",
    "type": "INVARIANT_RULE",
    "id": "INV-AUTH-006",
    "title": "isUserLoggedIn() Operator Precedence & In-Place Reauth Boundary",
    "content": "In frontend/lib/auth-session.ts, isUserLoggedIn() MUST maintain backward compatibility for orphan recovery keys (where user_recovery_key exists without nickname) so that 401 triggers in-place re-auth modal (auth-session-resilience TC-10/TC-11). Do NOT conflate visitor mount suppression with isUserLoggedIn definition."
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-SENTINEL-002",
    "title": "Unified Dual-Core CLI Adversarial Duel Integration (--mode duel)",
    "content": "Security Sentinel CLI (runner.py) supports --mode {adaptive,duel,fast}. In --mode duel, runner.py dynamically acquires an isolated GitWorktreePool and executes orchestrate_adversarial_duel across 4 phases: (1) Attacker pytest PoC generation; (2) Physical Red Check with pytest -k 'not benign' (exit code 1); (3) Defender Chesterton's Fence archaeology evaluation (DISMISSED if proven intentional design); (4) Block replacement patch synthesis with Mantis Block G Benign Control green check (exit code 0)."
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-012",
    "title": "agy.exe CLI Flag Precedence with -p Option under Windows PowerShell",
    "content": "When invoking agy.exe CLI via subprocess under Windows PowerShell, placing -p before other flags (e.g., agy.exe -p <prompt> --sandbox) causes agy.exe to interpret '--sandbox' as the prompt string itself. Always format prompt as -p=<cli_prompt> and place flags (--sandbox, --disable-slash-commands, --output-format json) upfront."
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-013",
    "title": "Large File Prompt Token Exhaustion in Sentinel Validator Subagent",
    "content": "Passing entire 60k character source files to agy.exe subagent in batch runner runs exhausts the default output token limit on chain-of-thought thinking tokens (e.g. 586 thinking tokens / 622 total tokens), leaving insufficient tokens for JSON emission. Always constrain target inspection with start_line and end_line targeted code snippets."
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-AGY-001",
    "title": "Dual-Track Spec DAG Engine & Approval Gate Precedence",
    "content": "In idea-to-spec skill, specification generation supports Fast-Track (single-turn) and Deep-DAG (5-node pipeline). In Deep-DAG, automated adversarial red-team audit and property-based test invariant assertions MUST occur strictly BEFORE Gate 5 Human Approval Gate, guaranteeing that human confirmation is the sole irreversible handover boundary to @dev."
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-DEV-001",
    "title": "RFC 7518 HMAC-SHA256 Minimum Key Length Threshold",
    "content": "All HMAC-SHA256 (HS256) secrets in tests and production code MUST be at least 32 bytes (256 bits) long to comply with RFC 7518 Section 3.2 and eliminate PyJWT InsecureKeyLengthWarning."
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-DEV-002",
    "title": "pytest-mock Fixture Lifecycle Hygiene",
    "content": "Mocks created via pytest-mock fixture (mocker.patch) MUST NOT be wrapped in 'with' context manager statements. Use direct assignment and modify 'mock.return_value' across test branches."
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-015",
    "title": "Gate Sequence Inversion Trap in Multi-Stage Agent Pipelines",
    "content": "Placing human approval gates before automated adversarial patch refinement leads to post-approval specification drift where unapproved automated changes reach developers. Automated contract and security verification must strictly precede the human approval gate."
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-016",
    "title": "Pytest-mock Context Manager Double-Exit Warning Trap",
    "content": "Wrapping mocker.patch() in a 'with' block triggers PytestMockWarning due to redundant context exit calls. Manage test branching via return_value mutation instead of context managers."
  },
  {
    "domain": "map_webgl",
    "type": "INVARIANT_RULE",
    "id": "INV-GEO-001",
    "title": "Self-Bootstrapping Spatial Proximity Bias for Markdown Import",
    "content": "In parse_markdown (/api/ai/parse-md), when trip title is generic (e.g. '5天4夜自由行'), proximity bias MUST dynamically bootstrap (bias_lat, bias_lng) from the first successfully resolved item coordinate to anchor subsequent geocoding queries and eliminate global coordinate drift."
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-SEC-002",
    "title": "Strict Hostname Boundary Regex for Whitelisted Redirect URLs",
    "content": "When whitelisting external redirect or maps URLs via regular expressions, the hostname expression MUST end with an explicit boundary anchor '(?:/|\\?|$)' to prevent subdomain spoofing bypasses such as 'https://maps.app.goo.gl.attacker.com'."
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-AI-001",
    "title": "Fast-Lite Fallback Strategy for High-Latency Note Extraction",
    "content": "In note extraction endpoints, routing_strategy MUST prioritize 'gemini-3.1-flash-lite' before 'gemini-3.5-flash-lite' and 'gemini-3.8-flash' to prevent Next.js dev server proxy from encountering 500 ECONNRESET (socket hang up) during upstream model retry backoffs."
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-017",
    "title": "Next.js Dev Proxy Socket Hang Up under Gemini 3.8 Multi-Tier Backoff",
    "content": "When calling Gemini 3.8 Flash for long markdown extraction, upstream 503 errors trigger exponential backoff exceeding 30s, causing Next.js dev proxy to drop connections with ECONNRESET. Use gemini-3.1-flash-lite (0.9s response) as the primary extraction model."
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-018",
    "title": "Subdomain Spoofing in Unanchored Domain Regex Whitelist",
    "content": "Writing regex like '^https?://(maps\\.app\\.goo\\.gl|...)' allows attackers to construct 'maps.app.goo.gl.attacker.com' and bypass SSRF domain whitelisting. Always append '(?:/|\\?|$)'."
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-019",
    "title": "Action Noise False Geocoding Query Overhead",
    "content": "Submitting activity notes like '集合/搭乘/休息/退稅' to geocoding services causes rate limit exhaustion and erroneous coordinates. Filter out items matching ACTION_NOISE_KEYWORDS before geocoding."
  }
]
```

