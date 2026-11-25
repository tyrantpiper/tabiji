# Tabidachi 大腦微核心記憶 (Tier 1 Micro-Core Invariants)

> **最高層級**: 全域憲法不變量 (Global Invariants) 與領域知識庫路由表。
> **載入策略**: 常駐 Prompt Prefix 高速快取。業務領域知識請依下方路由表按需延遲載入 (On-Demand)。

---

## 🏛️ [Core Invariants] 最高工程鐵律
1. **物理隔離 Maker-Checker**: 開發者 (@dev) 與審查者 (@qa) 運行於純淨獨立上下文。唯讀測試審查，禁止自我審查。
2. **零退化與全棧品質底線**: 任何變更必須維持 TypeScript 0 錯誤 (`tsc --noEmit`)、ESLint 0 錯誤/警告、測試 100% 通過。
3. **最小侵入性與 Windows 衛生**: 嚴禁整檔重寫，採精確 diff；嚴禁裸檔名落入專案根目錄；嚴格宣告 `$LASTEXITCODE` 熔斷。
4. **In-Memory PoC 與確定性守門**: 資安漏洞與架構防禦必須以記憶體單元測試實證；台帳受 `validate_security_ledger.py` 數學守恆約束。
5. **模組單例可測性法則**: 凡模組層級節流/快取狀態，必須顯式導出 `__reset...ForTesting()` 介面，杜絕跨測試狀態洩漏。

---

## 🗺️ [Domain Routing Map] 領域知識庫路由表
當任務涉及以下具體業務時，Agent **必須按需讀取** 對應的領域庫以獲取完整歷史決策與踩坑經驗：
- 🌐 **圖形、地圖、WebGL、手勢、CSP Worker** ➔ `.agents/domains/map_webgl.md`
- ⚡ **SWR、自癒、Zustand、深層連結、路由** ➔ `.agents/domains/state_cache.md`
- 🎨 **動畫、觸控、iOS 原生體驗、WebKit 防衛** ➔ `.agents/domains/ios_ui.md`
- 📱 **Service Worker、IndexedDB、快取分流、推送** ➔ `.agents/domains/offline_pwa.md`
- 🚀 **FastAPI、Cloudflare D1、Supabase、探針、時區** ➔ `.agents/domains/backend_concurrency.md`
- 🛡️ **CI/CD、PowerShell 熔斷、Sentinel 攻防、台帳** ➔ `.agents/domains/devops_security.md`

---

## 📖 [Core Vocabulary] 全域核心術語
- **Storage-Transmission Decoupling**: 存儲身分永固（資料庫外鍵不輪換）與傳輸身分時效（30 天 JWT + 單向脫敏）之分離典範。
- **CI CWD Isolation**: CI 測試目錄切換防斷線，以動態 `REPO_ROOT` 注入確保跨層引用永不失效。
- **Double-Checked Healing**: 清單二次核驗後 300ms 靜默導正，杜絕誤殺。
- **Great-Circle Slerp**: 跨天長途城際移動之球面幾何線性插值。
- **Opaque Response**: Safari 外部圖片快取配額防膨脹與 CORS 穿透。
- **Deterministic Guard**: 零依賴靜態腳本實施的不可妥協數學級品質門禁。
- **Dual-Track Credential**: 資料身分永固（UUID 內部主鍵）與存取憑證（`tbj_rec_*` 現代引繼碼）之解耦模型。
- **Opaque Realtime Signal**: WebSocket 廣播僅傳遞無狀態失效訊號（timestamp），敏感資料一律強制透過鑑權 HTTPS 拉取。
- **Transit Corridor K-Partitioning**: 跨區高鐵/離島長途移動以物理跳躍與局部密度支撐動態切分多時序空間子群，杜絕中位數坍塌誤殺。
- **Stateless Authorization Code Fallback**: OAuth 2.1 授權伺服器以記憶體字典 + HMAC-SHA256 Token 雙軌備援，杜絕 Cloud Run 多容器自動擴展時狀態遺失。
- **Credential Fingerprint Lock**: `auth-session.ts` 以 JSON 序列化憑證指紋鎖（`lastFailedExchangeFingerprint`）＋ `isReauthDismissedInMemory` 取代短時間冷卻，消滅 SWR 15s 輪詢大於 10s 冷卻觸發的無限 401 風暴。
- **Two-Layer & Edge Bug Masking**: 外層邊緣錯誤（如 Edge Shield 誤攔 `/api/poi/nearby` 或 `www` 404 遮蔽 `.vercel.app` 原生端點暴露）會長期掩蓋下層缺陷，稽核必須雙網域穿透實測。
- **Three-Master-Key Decoupling**: Cloud Run `SESSION_SECRET_KEY` (JWT 門票)、`VAULT_MASTER_KEY` (AES-GCM 保險庫)、`RECOVERY_PEPPER` (HMAC 指紋) 三權嚴格獨立於 `SUPABASE_KEY`（`sb_*` 僅置於 `apikey` 標頭）。
- **CJK Orthographic & Lexical Bridge**: 針對公用 Photon 無中文索引與日本 OSM 95% 長尾缺 `name:zh` 之結構限制，建立繁簡日新字體正規化（`澀→渋`/`車站→駅`）、品牌泛用尾詞剝除與保序 Bigram Top-K 橋接，補足自架開源引擎亦缺的東亞在地能力。
- **Five-Cloud Ordered Rollout**: 因 Vercel (~1m) 快於 Cloud Run (3–5m)、Cloudflare Worker 無自動 CI 且 `/sw.js` 具 4h 快取，涉及跨雲契約與邊緣快取之發佈必須嚴守 `Cloud Run 驗收 ➔ 手動 wrangler deploy 升版快取 ➔ Git Push 觸發 Vercel`。
- **Pure Postgres Row-Lock Atomic Merge**: 跨容器 JSONB 併發改以 Postgres `FOR NO KEY UPDATE` ＋ `lock_timeout` ＋頂層 `|| jsonb_build_object(...)` 單交易原子寫入，以零 Redis 成本根除 read-modify-write 覆蓋。
- **Post-Persist Zero-Leak Broadcast**: 協同 WebSocket 廣播必於後端落盤後發送且經 `stripPrivateForBroadcast()` 剔除私密項與原始 UUID，接收端以 `mergeIncomingWithLocalPrivate()` 保留本端私密狀態。
- **Atomic Bootstrap & Grapheme-Safe Nickname**: `POST /api/auth/session` 於建帳與孤兒補登單步帶入跨端 Unicode/Grapheme 安全清洗之初始暱稱（絕不覆寫既有老用戶），搭配 `ProfileView` `Traveler` 防覆蓋鎖與四重競態守衛，根除兩段式改名斷裂。
- **Dual-Track 6-Account Fixed Test Pool**: 線上實測一律複用 6 帳固定池（環境變數 RFC 4122 v4 `RYAN_TEST` 專測 D1 POI/UI、`00001/00002/00004/00005` 現代 `tbj_rec_*`、`00003` 硬鎖 Legacy），由 `scripts/manage_test_accounts.py` 統一巡檢、脫敏清理與線上升級。
- **Single-Worker DNS Bulkhead & Bounded Streaming**: 單進程 Cloud Run (`1 vCPU / 1Gi`) 下出站 DNS 檢查隔離於獨立 4 執行緒艙壁並對白名單走 0ms 純 CPU 快車道，外部抓取一律採 `client.stream` 有界截斷、線性 $O(n)$ 正則與 Vercel 同款 `sandbox` CSP。

