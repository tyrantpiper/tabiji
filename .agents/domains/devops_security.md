# 領域知識庫：CI/CD、工程化守門與資安攻防 (devops_security)

> **所屬領域**: GitHub Actions, PowerShell 熔斷, Security Sentinel (runner.py), 台帳驗證 (validate_security_ledger.py)

## 🏛️ 架構決策 (Decisions)
- **Commercial Cloud Compliance and Deployment Guard**: Any production build utilizing commercial affiliate redirect or monetization tokens must operate on Vercel Pro or Cloudflare Pages to prevent 503 DEPLOYMENT_PAUSED fair-use suspension.

- **Counter Due-Diligence Tri-Gate Defense**: All unsolicited inbound investment/incubation inquiries must satisfy corporate email domain, bilateral NDA, and 100% legal tender cash affirmation before sharing proprietary architecture or schemas.

- **Redacted Host Short-Circuit Guard**: Any proxy URL configuration using REDACTED placeholders must short-circuit gracefully to fallback mechanisms without triggering getaddrinfo DNS network exceptions.

- **Dependabot Group Scope Restricted to Minor & Patch Updates**: Dependabot groups must specify 'update-types: ["minor", "patch"]' to strictly isolate breaking major upgrades into standalone PRs, preventing monolithic group PRs from breaking the entire test and compilation pipeline.

- **Pinned Transitive Package Alignment in Dependabot & npm Overrides**: When direct dependencies strictly pin internal sub-packages (e.g. vitest strictly pinning @vitest/mocker), Dependabot single-package transitive updates fail with exit code 1. Root dependencies must be bumped in unison with npm overrides incrementally merged to guarantee 0 vulnerabilities and 0 container resolution crashes.

- **Constant Error String for Identity Oracle Suppression**: All recovery key verification failures (format invalid, non-existent key, hash mismatch, expected_user_id mismatch) across backend and frontend must output the identical uniform constant string: '引繼碼驗證失敗，無法在此設備恢復同步。請確認引繼碼是否正確。' Never reveal 'belongs to another account'.

- **Proof-of-Possession Migration Invariant**: In dual-track migration, legacy identifiers must not be accepted unauthenticated nor rejected unconditionally. The server must verify proof of possession of a server-signed session token before decrypting upgraded credentials.

- **PostgREST Anon Column-Level Least Privilege Invariant**: Sensitive credential columns in public tables must never be exposed to the anon role. Table-level SELECT must be revoked and replaced with explicit column-level grants.

- **Resting Data Vault Key Decoupling Invariant**: The master key used for resting data AES-256-GCM encryption must be decoupled from the ephemeral JWT signing secret (SESSION_SECRET_KEY) to ensure secret rotation never invalidates stored recovery keys.

- **Cloud Run CI/CD Workflow Secret Decoupling Invariant**: GitHub Actions deployment workflows must never pass sensitive environment variables via --set-env-vars. Secrets must reside exclusively within cloud platform secret managers or container service configurations.

- **Dual-Track Credential & Permanent Identity Decoupling Invariant**: User UUID must remain an internal-only foreign key anchor and never serve as an authentication credential. Authentication must use dedicated high-entropy recovery keys (tbj_rec_*), stored strictly as salted hashes in the database.

- **CI 工作目錄隔離與測試跨根路徑解析法則 (CI CWD Isolation & Cross-Root Import Invariance)**: 當測試檔案（如 `backend/tests/`）需要引用專案根目錄的腳本（如 `scripts/`）時，嚴禁假定執行環境當前工作目錄為專案根目錄（因為 CI 通常會執行 `cd backend && pytest`）。測試檔頭必須顯式注入動態路徑 `REPO_ROOT = Path(__file__).resolve().parent.parent.parent; sys.path.insert(0, str(REPO_ROOT))`，且 `backend/pytest.ini` 必須設定 `pythonpath = . ..`，徹底杜絕 CI 中的 `ModuleNotFoundError`。

- **1Password 式私鑰存儲與動態傳輸身分解耦法則 (Storage Identity vs Transmission Identity Invariance)**: 在關聯式資料庫中，使用者 UUID 作為跨表外鍵（Foreign Key）具有物理不可變性，嚴禁為了「時效性」在資料庫層級輪換 Primary Key（會引發災難級資料庫改寫）；正確典範是將資料庫 UUID 定義為 1Password 私密引繼碼（永久存於客戶端 LocalStorage），傳輸層疊加 30 天密碼學 JWT，協同端點伺服端單向脫敏為 `mem_sha256(uid + trip_id)[:10]`，徹底達成「存儲層永固、傳輸層時效、公開層脫敏」。

- **奧坎剃刀與資料庫歷史測試垃圾物理清理法則 (Occam's Razor vs Premature Abstraction Invariance)**: 當資料庫發現大量重複範例資料時，應先進行法醫學溯源。若為歷史一次性爬蟲/測試累積，且範本資料已硬編碼於記憶體中，嚴禁過早抽象引入複雜的「單一範本 + Fork on Edit + 唯讀狀態機」等分散式複雜度。直接執行安全備份與分批清理，維持無狀態的記憶體生成器，達到「零代碼修改、零架構回歸」的最高工程境界。

- **Strict CHUNK_SIZE=50 for PostgREST Dynamic IN Queries**: All batch queries and deletions taking dynamic lists of UUIDs must partition requests using CHUNK_SIZE <= 50 to prevent HTTP 414 URI Too Long errors in Supabase PostgREST.

- **痛點根治的四層防禦縱深法則 (AD-151)**: 面對工程中反覆發生的環境與中繼檔案痛點（如暫存檔洩漏、未列管檔案殘留），禁止單純手動刪除；必須同時建立「規格庫正規歸檔、.gitignore 永久忽略、push.md Root Hygiene Gate 硬阻斷、test_*_sentinel.py 單元測試固化」四道縱深防線，達成物理級杜絕。

- **痛點根治的四層防禦縱深法則 (INV-DEVOPS-018 / Defense in Depth)**: 面對工程中反覆發生的環境與中繼檔案痛點（如暫存檔洩漏、未列管檔案殘留），禁止單純手動刪除；必須同時建立「規格庫正規歸檔、.gitignore 永久忽略、push.md Root Hygiene Gate 硬阻斷、test_*_sentinel.py 單元測試固化」四道縱深防線，達成物理級杜絕。

- **Windows Subprocess 命令列衛生與長度防呆法則 (Windows Subprocess Hygiene Invariance)**: 在 Windows 平台調度外部 CLI 程序 (如 agy.exe) 時，傳入命令列長度受 32,767 字元系統硬限制。Harness 傳參時必須在代碼提取端實施 [:6000] 長度防衛或強制指定 start_line 與 end_line 切片，防止 WinError 206 (檔名或副檔名太長) 崩潰。

- **靜態 AST/正則哨兵多行與修飾詞容錯法則 (Sentinel Multiline & Regex Tolerance Invariance)**: CI/CD 靜態安全分析器比對 SQL DDL 時，嚴禁使用單行 .* 與硬編碼角色鄰接。必須統一採用 [\s\S]*? 穿透多行排版，以 [^;]* 容納逗號分隔的角色任意排列，並對 ALTER TABLE 注入 (?:IF\s+EXISTS\s+)?(?:ONLY\s+)? 修飾詞容錯，杜絕 CI 假陽性 (False Positive) 阻斷正常交付管線。

- **Windows CLI 命令列長度防禦法則 (Windows CLI Character Limit Defense)**: 所有調度外部子行程 CLI（如 agy.exe）的維護腳本與 candidates 清單，必須嚴格宣告 start_line/end_line 進行片段切片，嚴禁將未經切片的大型原始檔直接嵌入 -p 參數，防止 Windows WinError 206 溢位崩潰。

- **記憶 3-Tier 微核心與領域按需載入原則 (3-Tier Sharded Memory Routing)**: memory.md 必須保持 <50 行微核心憲法，包含領域路由表與全域詞彙；具體決策按業務維度下放至 .agents/domains/*.md，透過 AGENTS.md 路由指引按需延遲載入，嚴禁重構為單體大檔案。

- **Cloudflare 式台帳數學守恆與非多態硬驗證守則 (Deterministic Security Ledger Invariance)**: 資安覆蓋帳本必須受 validate_security_ledger.py 靜態守護：所有 targets 必須唯一使用 id 鍵，嚴禁 target_id 多態殘留；統計總數必須嚴格滿足 total_targets == audited_targets == (verified + remediated + dismissed) 數學守恆。

- **PowerShell 確定性熔斷守門架構**: 嚴禁依賴非熔斷的 ; 或無效的 &&。所有守門腳本必須明確宣告 if ($LASTEXITCODE -ne 0) { exit 1 }。
- **雙模 AST/正則防禦架構**: JSX 樹狀結構複雜樣式反模式採 AST 節點鎖定搭配正則約束，兼顧精確度與零偽陽性。
- **三重活體驗收防線**: 編譯鏈更新時串聯 npm audit, vitest 與 next build 進行真實驗收。
- **overrides 原地安全合併原則**: package.json 依賴覆蓋採增量原地合併，保留既有修復。
- **Security Sentinel 物理沙盒證偽驗收**: 透過 runner.py 調度獨立 agy.exe -p --sandbox 進行無提示詞污染的對抗審查；推行 In-Memory PoC 標準。
- **Cloudflare 確定性台帳硬核驗證**: validate_security_ledger.py 靜態硬驗證 ID 唯一性、無 target_id 多態殘留、狀態白名單與數學守恆。
- **Mantis-Critic 假陽性修剪與中性語意轉化**: 假說生成前洗滌 DoS/flood 等黑話為中性軟體工程術語，杜絕安全模型誤報；Critic 預審排除防禦在層。

## 🛡️ 踩坑記錄 (Failed Paths)
- **Windows PowerShell Subprocess CLI Character Overflow Trap**: Passing entire multi-line source files into agy.exe CLI arguments exceeds Windows command buffer limits; candidates must be sliced with line numbers.

- **Blind 400 Rejection Inducing Authentication Deadlock Trap**: Strictly rejecting legacy identifiers after account upgrade prevents legitimate legacy devices from receiving sessions or accessing the vault.

- **Stale Token Silent 401 Lockout Trap**: Failing to dispatch upgrade events on 401 upgraded responses leaves clients hung without self-healing pathways.

- **PostgREST Blanket Table Grant Exposure Trap**: Adding columns to tables with pre-existing blanket anon grants silently exposes sensitive fields to public PostgREST endpoints.

- **JWT Signing Key and Storage DEK Coupling Trap**: Deriving data encryption keys directly from JWT signing secrets invalidates all encrypted database records upon secret rotation.

- **Landing Page Form Regex Desynchronization Trap**: Updating backend credential formats without updating frontend landing page form validation regex blocks users at the submission gate. Always synchronize credential formats across the entire chain.

- **CI Test Dependency Omission Trap**: Assuming dependencies are available in CI because they exist in local dev causes CI collection aborts. Always declare test dependencies in requirements-test.txt and guard optional imports.

- **Stale Test Database Flag Masking Temporal Guard Regressions**: Historical test records with pre-set boolean flags bypass temporal guard verification in production previews. Always verify and reset state before E2E telemetry.

- **Windows Console CP950 Output Encoding Trap**: Python CLI scripts on Windows PowerShell fail with UnicodeEncodeError when emitting UTF-8 emojis. Always reconfigure sys.stdout and sys.stderr with encoding='utf-8'.

- **Windows CreateProcess 命令列長度溢位陷阱 - WinError 206**: 在 Windows 平台使用 asyncio.create_subprocess_exec 傳遞包含未切片代碼字串（60,000+ 字元）之 -p={prompt} 參數給 agy.exe 時，系統拋出 [WinError 206] 檔名或副檔名太長，造成子代理人崩潰。修復準則：外部 Subprocess 調度必須對傳入的代碼片段實施精確行範圍切片或預設上限截斷（如 <= 6000 字元），防止 OS 層級命令列長度溢位。

- **CI 靜態正則缺 re.DOTALL 與角色排列硬編碼誤報陷阱**: CI 靜態掃描測試使用 .* 且寫死 TO (authenticated|service_role)，導致合法的多行 SQL 與 TO anon, authenticated; 被判為未授權，CI 假陽性阻斷。修復準則：靜態代碼分析器正則必須使用 [\s\S]*? 穿透跨行換行符，並以 [^;]* 支援逗號分隔的任意角色排列順序。

- **FP-062 (CI 靜態正則缺 re.DOTALL 與角色排列硬編碼誤報陷阱)**: CI 靜態掃描測試使用 .* 且寫死 TO (authenticated|service_role)，導致合法的多行 SQL 與 TO anon, authenticated; 被判為未授權，CI 假陽性阻斷。修復準則：靜態代碼分析器正則必須使用 [\s\S]*? 穿透跨行換行符，並以 [^;]* 支援逗號分隔的任意角色排列順序。

- **FP-050 (Sentinel 假說被安全過濾器攔截)**: 候選假說使用了攻擊性字眼導致雲端 API 攔截報 INCONCLUSIVE。規範一律使用中性品質工程措辭。
- **FP-027 (專案根目錄衛生硬防線)**: runner.py 強制攔截裸檔名輸出至根目錄；白名單外違規檔案立即觸發 sys.exit(1)。
