# 📅 Daily Report - 2026-11-28 (五雲 103 筆資安告警終審、34 筆 CodeQL 全清零、RFC 1123/線性正則加固與 `gh` 閉環清理)

> **時間範圍**: `2026-11-27 21:32 ~ 2026-11-28 00:47` (UTC+8)
> **納入 Commits (`00dba09..be7194e`, 共 4 Commits, 全數通過 CI / CodeQL / 五雲線上實測)**:
> - `83d938f` (`2026-11-27 22:36`): `fix(security): remediate all 34 CodeQL Bucket A+B alerts and harden public IP rate limits`
> - `e770176` (`2026-11-27 23:04`): `fix(security): close residual ReDoS, OAuth redirect/state, URL fast-path, and regional taxonomy gaps`
> - `9ccacac` (`2026-11-27 23:11`): `test(security): set synthetic SESSION_SECRET_KEY for prod OAuth test on CI runners`
> - `be7194e` (`2026-11-27 23:42`): `fix(security): harden DNS hostname/scheme validation, O(N) envelope parsing, and title newline stripping`
> - **總增量 (`git diff 00dba09..be7194e --shortstat`)**: **`23 files changed, 1,731 insertions(+), 252 deletions(-)`**
>
> **全棧 Quality Gate、五雲上線與 GitHub Security 即時狀態 (`be7194e`)**:
> - **GitHub Actions (`be7194e`)**: `CI` ✅ (`3m39s`)、`Deploy Backend to Cloud Run` ✅ (`1m54s`)、`CodeQL` ✅ (`1m22s`)
> - **GitHub Security (`gh` 即時複查)**:
>   - **Code Scanning (CodeQL)**: **`0` Open**（原有 100 筆 ➔ **34 筆實修自動 `Fixed`** ＋ **66 筆依實證理由 `Dismissed`**；0 新增告警、0 隱藏 Low/Note）
>   - **Secret Scanning**: **`0` Open**（`#3`, `#4`, `#5` 均確認為 `backend/tests/` 假字串，依 `used_in_tests` 結案）
>   - **Dependabot**: **`2` Open**（`#121 minimatch`、`#120 glob`，純 Build/Lint 期 0 線上風險，依站長決策保留併入後續套件批次升級）
> - **自動化測試與守門**:
>   - Backend Pytest: **`1,000 passed, 5 skipped, 0 failed`**（基線 `975` ➔ **`1,000`**, `+25` 雙面單測, `EXIT 0`）
>   - Frontend: `tsc --noEmit` (`0`)、`npm run lint` (`0`)、`vitest run` **`139 檔 / 1,283 passed, 4 skipped`**、`NODE_ENV=production npx next build` (`11/11` PASS)
>   - Security Ledger (`scripts/validate_security_ledger.py`): **`476 targets` (`236 remediated, 53 verified/unresolved, 187 dismissed/safe`)** (`EXIT 0`)
>   - Neural Seam Harness (`scripts/neural_seam_harness.py`): **`10/10 seams Intact`** (`EXIT 0`)
> - **五雲線上實測**:
>   - **Cloud Run (`antigravity-backend-00252-485`)**: 18 組 env/secrets 完整保留、近 30 分鐘 `severity>=ERROR` `0` 筆；`/.well-known/oauth-authorization-server` 鎖定 `https://www.tabijiapp.com`、`.tabijiapp.com`/`..claude.ai`/`-sub.tabijiapp.com`/`evil.vercel.app` 全回 `400`、合法 `claude.ai`/`oauth-redirect.googleusercontent.com` 放行、`/api/poi/enrich` `200`、513 字超長輸入 `422`。
>   - **Vercel (`dpl_8txiccvW4MNaa8ZXgVSQ7uzMBRYJ`, `be7194e`)**: `READY / production`。
>   - **Cloudflare Workers**: `tabidachi-search-proxy` 手動 `wrangler deploy` 上線 Version `ba8fbe7e-9655-4f13-b3ac-d9dc060e7fbe`（100% 流量、未授權 `401`）。
>   - **Chrome DevTools MCP (`https://www.tabijiapp.com/`)**: `32/32` 請求 `200/204`、0 初始 Console 錯誤、0 CSP 違規、0 破圖、`overflowX=false`。

---

## 1. 工程與檔案異動總覽

- **ReDoS 根治、輸入長度上限與純 IP 限流**:
  - [backend/services/intent_router.py](file:///d:/Project/tabiji/travel-pwa/backend/services/intent_router.py)、[backend/services/poi_service.py](file:///d:/Project/tabiji/travel-pwa/backend/services/poi_service.py)、[backend/services/flight_pricing_service.py](file:///d:/Project/tabiji/travel-pwa/backend/services/flight_pricing_service.py)、[backend/services/link_resolver.py](file:///d:/Project/tabiji/travel-pwa/backend/services/link_resolver.py)、[backend/services/geocode_service.py](file:///d:/Project/tabiji/travel-pwa/backend/services/geocode_service.py)、[backend/utils/poi_utils.py](file:///d:/Project/tabiji/travel-pwa/backend/utils/poi_utils.py)、[backend/models/base.py](file:///d:/Project/tabiji/travel-pwa/backend/models/base.py)、[backend/routers/poi.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/poi.py)、[backend/routers/geocode.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/geocode.py)。
- **OAuth / Discovery 主機防投毒、URL 安全快車道、SSE 脫敏與 CI 唯讀**:
  - [backend/routers/mcp.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/mcp.py)、[backend/utils/url_safety.py](file:///d:/Project/tabiji/travel-pwa/backend/utils/url_safety.py)、[backend/main.py](file:///d:/Project/tabiji/travel-pwa/backend/main.py)、[.github/workflows/ci.yml](file:///d:/Project/tabiji/travel-pwa/.github/workflows/ci.yml)。
- **跨端精確主機名閘道與 Cloudflare 單趟 XML 實體解碼**:
  - [backend/services/destination_taxonomy.py](file:///d:/Project/tabiji/travel-pwa/backend/services/destination_taxonomy.py)、[backend/services/web_search_engine.py](file:///d:/Project/tabiji/travel-pwa/backend/services/web_search_engine.py)、[backend/routers/agents.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/agents.py)、[frontend/lib/utils.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/utils.ts)、[cloudflare/search-proxy/worker.js](file:///d:/Project/tabiji/travel-pwa/cloudflare/search-proxy/worker.js)。
- **Mantis Block G 雙面單測與安全台帳**:
  - [backend/tests/test_codeql_34_remediation_sentinel.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_codeql_34_remediation_sentinel.py)（`+921`）、[docs/security/security-coverage-ledger.json](file:///d:/Project/tabiji/travel-pwa/docs/security/security-coverage-ledger.json)（`476 targets`）、[frontend/__tests__/cloudinary-proxy-and-preferences-sentinel.test.ts](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/cloudinary-proxy-and-preferences-sentinel.test.ts) 等。

---

## 2. 本日實戰事件、架構決策與經驗沉澱

### 🟢 Features & Fixes
- **五雲 103 筆資安告警全量實證終審**：透過 14 張截圖搭配 Cloud Run 線上組態實查（證實 `ingress=all` 且已設 `TP_API_TOKEN`），嚴格區分 `14` 必修（Bucket A）＋ `24` 低風險／建置期（Bucket B）＋ `65` 實證安全（Bucket C）＝ `103` 數學守恆，拒絕盲目關閉真實漏洞。
- **34 筆 CodeQL 一次清零＋深層 7 項邊界加固（`83d938f..be7194e`）**：在首次修復後再經對抗覆檢揪出 7 項殘留邊界（前導點 DNS 標籤 `.tabijiapp.com`、Authority 空白／前導零埠號、同鹽內嵌閉合標籤洩漏、尾端換行回歸、來源分類器與 DDG 拆包協定閘道），一次收斂至 CodeQL **`34/34 Fixed`、`0` 新增告警**。
- **導入本機 `gh` CLI 並完成 69 筆確定性清盤**：安裝 `gh` v2.106.0 直查線上 Actions / CodeQL / Secret Scanning / Dependabot，確認 0 隱藏 Low/Note，並依實證理由完成 66 筆 CodeQL ＋ 3 筆測試假金鑰關閉（達成 `CodeQL = 0`、`Secret Scanning = 0`），保留 2 筆建置期 Dependabot 待日後批次升級。

### 🏛️ Architecture Decisions
- **AD-269（單核容器線性 $O(N)$ 正則、有界輸入上限與公開代理純 IP 限流契約）**：鑑於 Cloud Run 採 `--workers 1 --timeout 0`，任何主事件迴圈同步 `re` 回溯皆會凍結全部 40 條併發連線且無法由 `asyncio.wait_for` 中斷。全面線性化 10 處正則（`intent_router.py` 前綴限縮 `bounded_raw[:256]` + 首詞保留連字號 + 單趟 `last_close_by_salt` 達嚴格 $O(N)$；`poi_service.py`、`flight_pricing_service.py`、`link_resolver.py` 抽出 `_strip_google_maps_title_suffix()` 先 `.strip()[:500]`、`geocode_service.py` L771 & L774 同步加 `(?<!\d)`、`poi_utils.py` 互斥字元類）；公開輸入補上 `max_length=512`（景點名／地址）與 `2048`（連結）；公開代理端點（`/api/poi/ai-enrich`, `/api/poi/resolve-link`, `/api/poi/media-proxy`, `/api/geocode/*`）全面改採寬鬆家庭配額之純 IP `get_public_ip_rate_limit_key`，一般聊天 `/api/chat/stream` 維持各自 API Key 配額不互卡同 Wi-Fi 家人。
- **AD-270（RFC 1035/1123 嚴格主機驗證、OAuth/Discovery 零投毒、SSE 脫敏與 CI 唯讀權限契約）**：`mcp.py` 拔除萬用 `vercel.app` 與 `googleusercontent.com`，精確鎖定 `travel-pwa-five.vercel.app`、專案預覽正則、`oauth-redirect.googleusercontent.com`、`oauth-redirect-sandbox.googleusercontent.com` 與既有 AI 平台白名單，並全面套用 RFC 1035/1123 DNS 標籤正則（`<=253`、拒前導點／雙點／連字號首尾／`username`/`password`/`\`/控制字元／前導零埠號／生產 `testserver`）；`get_public_base_url` 嚴驗 host 與 `proto in {"http", "https"}` 且未知 Host 一律回退 `"https://www.tabijiapp.com"`；`url_safety.py` 抽離共用 `_validate_and_parse_host()` 守衛快車道與 DNS 路徑；`main.py` SSE `event: error`（L2329/L2364）與 `/api/ai/test-key` 全面回傳中英安全常數（保留 401 `API_KEY_INVALID` 與伺服端 `logger.warning`）；`.github/workflows/ci.yml` 頂層宣告 `permissions: contents: read`。
- **AD-271（全站精確主機名與 HTTP(S) 協定閘道暨 Cloudflare 單趟 XML 實體解碼契約）**：消除全站 17 處生產 URL 子字串比對——`destination_taxonomy.py` 以 `_is_valid_dns_host()` + `_host_matches()` + `_is_google_maps_url()` 鎖定 `http/https` 並修復 L836 死碼讓 Google Maps 來源徽章生效；`web_search_engine.py` `unwrap_ddg_redirect()` 強制外層與目標皆為 `http/https` + RFC 1123 精確 `duckduckgo.com`；`agents.py` Wikipedia 標題萃取補 `_VALID_WIKI_HOST_RE` 與 `http/https`；`frontend/lib/utils.ts` `getOptimizedImageUrl()` 以 `new URL()` 嚴驗 `https:` + `res.cloudinary.com` 且無帳密／非預設埠；`cloudflare/search-proxy/worker.js` `decodeXmlEntities()` 改為線性 CDATA 剝離＋單趟查表替換（含過濾 Surrogate `0xd800..0xdfff`）並手動 `wrangler deploy`。
- **AD-272（GitHub CLI `gh` 確定性資安閉環與告警分流治理準則）**：透過本機 `gh` CLI 直查 Actions / CodeQL / Secret Scanning / Dependabot 取代人工截圖盲區；建立「真缺陷優先實修（CodeQL 自動轉 `Fixed`）➔ Mantis Block G 雙面單測驗證 ➔ 經實證零風險項按標準理由（`false positive`/`won't fix`/`used in tests`）精準關閉 ➔ 建置期 Dependabot 併入有控制之套件批次升級」之確定性治理閉環。

### 🔴 Technical Debt
- **DEBT-DEPENDABOT-BUILD-UPGRADE-01（Low — 建置／Lint 期 2 筆 Dependabot 留待批次升級）**：`frontend/package-lock.json` 尚留 Dependabot `#121`（`minimatch < 11.0.1`）與 `#120`（`glob <= 14.0.1`），僅存在於 `@serwist/*`（Build）與 `typescript-eslint`（Lint），0 線上執行期風險；後續進行前端套件批次升級時，精準同步升級 `@serwist/* -> 9.6.0` 與 `typescript-eslint -> 8.74.0`（切勿無腦跑 `npm audit fix` 以免誤將 `tailwindcss` 由 `4.3.5` 降為 `4.3.4`）。
- **DEBT-SECURITY-KEY-ROTATION-01（Action Required — 手動撤銷臨時測試金鑰）**：請至 Google AI Studio 撤銷先前線上實測曾貼入對話視窗之臨時 Gemini 測試金鑰。

### 🛡️ Failed Paths
- **FP-142（單核 Cloud Run 下同步 `re` 回溯不受 `asyncio.wait_for` 中斷與迴圈放大陷阱）**：在 `--workers 1 --timeout 0` 容器內，同步 C 層 `re.sub` 回溯無法被 `asyncio.wait_for(1.5)` 中斷；`poi_service.py` Geosearch `ggslimit=10` 會將單筆 ReDoS 放大 10× 至 ~34s，`flight_pricing_service.py` 對 `orig`/`dest` 放大 2×，`geocode_service.py` L771/L774 在持有全域 `_get_nominatim_lock()` 時阻塞全站地理編碼；`intent_router.py` 逐鹽 `find()` 在 1,100 組異鹽退化為 $O(N^2)$ 且漏處理同鹽內嵌閉合標籤。修補時必檢查同檔重複正則（如 L771 & L774）並為所有公開入口加上 `max_length`。
- **FP-143（僅驗 `^[a-z0-9.-]+$` 漏檢 RFC 1123 DNS 標籤、Authority 空白與 `X-Forwarded-Host` userinfo 繞過陷阱）**：僅檢查 `^[a-z0-9.-]+$` 搭 `endswith(".tabijiapp.com")` 會放行 `.tabijiapp.com`、`..claude.ai`、`-sub.tabijiapp.com`；`url_safety.py` 僅濾控制字元卻未攔截 Authority 空白、空埠冒號與前導零埠號（`:000443`）會使快車道誤放畸形網址；`mcp.py` 僅拆 `:` 前段驗白名單會在 `ingress=all` Cloud Run 遭 `www.tabijiapp.com:443@evil.com` 繞過。所有主機白名單一律須過嚴格 RFC 1035/1123 標籤正則與 `http/https` 協定檢查。
- **FP-144（單元測試寫入 39 碼 `AIzaSy...` 假金鑰觸發 Secret Scanning 與 CI 缺 `SESSION_SECRET_KEY` 陷阱）**：在 `backend/tests/` 撰寫符合 Google API Key 格式的 39 碼假字串（如 `AIzaSyFamilyMember...`）會立即觸發 GitHub Secret Scanning（`#4`, `#5`）；另生產模式 OAuth 單測若未透過 `monkeypatch` 注入測試用 `SESSION_SECRET_KEY`，本機通過但 GitHub Actions CI 會因無環境變數失敗（`9ccacac` 修正）。
- **FP-145（無腦 `npm audit fix` 意外降版 Tailwind 與單鏈升級無法消滅 `minimatch` 陷阱）**：`npm audit --json` 實證 `minimatch` (`#121`) 同時掛在 `@serwist/*` 與 `eslint-config-next -> typescript-eslint` 兩條鏈（單升 `@serwist/*` 無法清零），且盲跑 `npm audit fix` 會把 `tailwindcss` 從 `4.3.5` 降為 `4.3.4`。升級傳遞依賴前必先跑 `--dry-run` 檢視完整變動樹並採精準指定套件升級。

### 🎯 Next Steps
- **立即可辦**：至 Google AI Studio 撤銷先前線上實測使用的臨時 Gemini 測試金鑰。
- **後續套件升級波次**：待其他前端套件一併升級時，精準同步升級 `@serwist/*` 與 `typescript-eslint` 自動清零剩餘 2 筆建置期 Dependabot 提醒（`#121`, `#120`）。
- **本聊天室可安全歸檔／刪除**：自 `d8cfd3b` 至 `be7194e` 橫跨兩日全部 **17 筆 Commits**（`4895b5b`–`15df4ec` 12 筆＋`00dba09` 日報＋`83d938f`–`be7194e` 4 筆資安加固）均已上線五雲驗收，全對話所有架構決策（`AD-262`–`AD-272`）與踩坑經驗（`FP-135`–`FP-145`）已 100% 固化至兩份日報（`2026-11-27` & `2026-11-28`）與 `.agents/` 分層記憶庫。

---

## 🧬 Machine-Executable Invariant Rules

```json
[
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BACKEND-LINEAR-REGEX-IP-LIMIT-01",
    "title": "單核容器線性 O(N) 正則、有界輸入上限與公開代理純 IP 限流契約 (AD-269)",
    "content": "Cloud Run 採單核單 worker（--workers 1 --timeout 0），主事件迴圈任何同步 Python re 回溯皆會凍結全容器 40 條併發連線且無法被 asyncio.wait_for 中斷。所有公開路徑正則（intent_router.py、poi_service.py、flight_pricing_service.py、link_resolver.py、geocode_service.py L771/L774、poi_utils.py）必採非重疊線性寫法：intent_router.py 限縮系統前綴檢查於 bounded_raw[:256]、首詞保留連字號並以單趟 last_close_by_salt 達嚴格 O(N)；link_resolver.py _strip_google_maps_title_suffix 先 .strip()[:500] 再去尾綴；公開請求模型必設 max_length（景點名/地址 512、連結 2048）；公開代理端點（/api/poi/ai-enrich、/api/poi/resolve-link、/api/poi/media-proxy、/api/geocode/*）全面改用寬鬆家庭配額之純 IP get_public_ip_rate_limit_key，/api/chat/stream 維持各自 API Key 配額不互卡同 Wi-Fi 家人。"
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-SEC-RFC1123-OAUTH-SSE-CI-01",
    "title": "RFC 1035/1123 嚴格主機驗證、OAuth/Discovery 零投毒、SSE 脫敏與 CI 唯讀權限契約 (AD-270)",
    "content": "mcp.py TRUSTED_REDIRECT_DOMAINS 嚴禁萬用 vercel.app 與 googleusercontent.com，必精確鎖定 travel-pwa-five.vercel.app、專案預覽正則 ^travel-[a-z0-9-]+-tyrantpipers-projects\\.vercel\\.app$、oauth-redirect.googleusercontent.com、oauth-redirect-sandbox.googleusercontent.com 與既有 AI 平台白名單；所有主機名驗證必符合 RFC 1035/1123 標籤語法（<=253、禁前導點/雙點/首尾連字號/username/password/反斜線/控制字元/前導零埠號/生產 testserver）。get_public_base_url 嚴驗 host 與 forwarded_proto in {'http','https'}（非本機強制 https），未知 Host 回退常數 https://www.tabijiapp.com。url_safety.py 以共用 _validate_and_parse_host() 攔截 Authority 空白與畸形埠號；main.py SSE event: error (L2329/L2364) 與 /api/ai/test-key 一律吐安全常數（保留 401 API_KEY_INVALID 與伺服端 logger.warning）；.github/workflows/ci.yml 頂層必宣告 permissions: contents: read。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BACKEND-EXACT-HOST-SINGLEPASS-XML-01",
    "title": "全站精確主機名與 HTTP(S) 協定閘道暨 Cloudflare 單趟 XML 實體解碼契約 (AD-271)",
    "content": "生產程式碼嚴禁以裸 URL 子字串（'domain' in url/netloc）判定來源或代理分流：destination_taxonomy.py 統一以 _is_valid_dns_host() + _host_matches() + _is_google_maps_url() 鎖定 http/https 並確保 Google Maps 徽章正常生效；web_search_engine.py unwrap_ddg_redirect() 強制外層與解碼目標皆為 http/https 與 RFC 1123 精確 duckduckgo.com；agents.py Wikipedia 標題萃取補 _VALID_WIKI_HOST_RE 與 http/https；frontend/lib/utils.ts getOptimizedImageUrl() 以 new URL() 嚴驗 https: + res.cloudinary.com 且無帳密/非預設埠；cloudflare/search-proxy/worker.js decodeXmlEntities() 採線性 CDATA 剝離 + 單趟查表替換（過濾 Surrogate 0xd800..0xdfff），杜絕 &amp;lt; 雙重解碼吃字。"
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-SEC-GH-CLI-CLOSED-LOOP-01",
    "title": "GitHub CLI (gh) 確定性資安閉環與告警分流治理準則 (AD-272)",
    "content": "查核 GitHub Actions / CodeQL / Secret Scanning / Dependabot 優先透過本機 gh CLI 直連 API 以消除截圖盲區與 Low/Note 遺漏。所有告警必須採四段閉環：(1) 真實缺陷實修並驗證 CodeQL 自動轉 Fixed；(2) 以 Mantis Block G 雙面單測確保零功能退化；(3) 僅對實證安全或純測試檔項目依精確理由（false positive / won't fix / used in tests）附實證說明關閉；(4) 建置期 Dependabot 須先 npm audit fix --dry-run 審核依賴樹，避免降版相依套件，並同步更新 security-coverage-ledger.json 維持數學守恆。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-142",
    "title": "單核 Cloud Run 同步 re 回溯不受 asyncio.wait_for 中斷與多倍迴圈放大陷阱 (FP-142)",
    "content": "在 --workers 1 --timeout 0 容器中，同步 C 層 re.sub 回溯無法由 asyncio.wait_for(1.5) 中斷；poi_service.py Geosearch ggslimit=10 會將單筆 ReDoS 放大 10 倍至 ~34s，flight_pricing_service.py 對 orig/dest 放大 2 倍，geocode_service.py L771 與 L774 在持有全域 _get_nominatim_lock() 時鎖死全站地理編碼；intent_router.py 逐鹽 find() 遇 1,100 組異鹽退化為 O(N^2) 且漏處理同鹽內嵌閉合標籤。修補時必檢同檔重複正則並補齊入口 max_length。"
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-143",
    "title": "僅驗 ^[a-z0-9.-]+$ 漏檢 RFC 1123 DNS 標籤、Authority 空白與 X-Forwarded-Host userinfo 繞過陷阱 (FP-143)",
    "content": "僅以 ^[a-z0-9.-]+$ 搭 endswith('.tabijiapp.com') 會放行 .tabijiapp.com、..claude.ai、-sub.tabijiapp.com；url_safety.py 若只濾控制字元未攔截 Authority 空白、空埠冒號與前導零埠號（:000443）會使快車道誤放畸形 URL；mcp.py 僅拆冒號前段驗白名單會在 ingress=all Cloud Run 遭 X-Forwarded-Host: www.tabijiapp.com:443@evil.com 繞過。所有主機白名單必過嚴格 RFC 1035/1123 標籤語法與 http/https 協定檢核。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-144",
    "title": "測試檔寫入 39 碼 AIzaSy 假金鑰觸發 Secret Scanning 與 CI 缺 SESSION_SECRET_KEY 陷阱 (FP-144)",
    "content": "於單元測試檔寫入 39 碼 AIzaSy... 字串（如 AIzaSyFamilyMember...）會立刻觸發 GitHub Secret Scanning 告警；另生產模式 OAuth 測試若未在 fixture 以 monkeypatch 獨立注入測試用 SESSION_SECRET_KEY，本機通過但 GitHub Actions CI 會因環境未設該機密而失敗。"
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-145",
    "title": "無腦 npm audit fix 意外降版 Tailwind 與單鏈升級無法消滅 minimatch 陷阱 (FP-145)",
    "content": "npm audit --json 實證 minimatch 同時掛在 @serwist/* 與 eslint-config-next -> typescript-eslint 兩條相依樹（僅升級 @serwist/* 無法消滅 Dependabot #121）；且無腦執行 npm audit fix 雖可修兩鏈，卻會連帶將 tailwindcss 從 4.3.5 降回 4.3.4。升級傳遞依賴前必先 --dry-run 核對完整變更樹並採精準指定套件升級。"
  }
]
```
