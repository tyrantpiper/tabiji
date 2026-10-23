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

