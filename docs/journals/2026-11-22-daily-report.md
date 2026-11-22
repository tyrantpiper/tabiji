# 📅 Daily Report - 2026-11-22 (PR 1 五雲零停機 Cloudinary 簽章收斂＋金鑰輪換，與 PR 2 前端分級圖片壓縮、收據直傳、孤兒後門拆除及 Proxy 加固)

> **時間範圍**: `2026-11-21 18:29 ~ 2026-11-22 14:30` (UTC+8)
> **當日納入 Commit (`1d58cb5..e00b536`, 5 Commits, `36 files changed, 8274 insertions(+), 659 deletions(-)`)**:
> - `8219ec4`: `feat(security): migrate cloudinary upload signing to authenticated cloud run backend (stage 1)`
> - `1650dc0`: `refactor(security): cut over edge shield and remove legacy vercel cloudinary signing route`
> - `38396de`: `test(security): freeze wall clock in cloudinary timestamp skew sentinel test`
> - `212d867`: `feat(media,security): add tiered client compression, receipt direct-pass, and harden cloudinary proxy`
> - `e00b536`: `fix(media,security): tighten vercel preview allowlist, reject spoofed images in AI routes, and normalize raster data-url mimes`
> **全棧 Quality Gate 實測結果**:
> - Neural Seam Invariant Harness (`scripts/neural_seam_harness.py`): **`10/10` Intact** (`0` Sequelae, `EXIT 0`)
> - Security Ledger (`scripts/validate_security_ledger.py`): **`428 targets` (`200 remediated, 53 verified/unresolved, 175 dismissed/safe`)**（`413 -> 418 -> 428`, `0` 歷史 ID 遺失, `EXIT 0`）
> - Security Sentinel (`runner.py --mode adaptive --timeout 120`): PR 1 **`5/5 DISMISSED`** (`0` confirmed / `0` inconclusive) + PR 2 **`10/10 DISMISSED`** (`0` confirmed / `0` inconclusive)
> - Backend Pytest (`pytest -q`): **`752 passed, 5 skipped, 0 failed`**（基線 `726` ➔ `+26` 新增測試, `EXIT 0`）
> - Frontend TypeScript (`npx tsc --noEmit`) & ESLint (`npm run lint`): **`0 errors, 0 warnings`** (`EXIT 0`)
> - Frontend Vitest (`npx vitest run`): **`124 files, 1,156 passed | 4 skipped (1,160)`**（基線 `119 files / 1,127` ➔ `+5 files / +29 tests`, `EXIT 0`）
> - Frontend Production Build (`npx next build`, Turbopack): **`11/11` static pages**（確認 `/api/sign-cloudinary` 與 `/api/parse-receipt` 已自路由表移除, `EXIT 0`）
> - Live 5-Cloud & `@mcp:chrome` E2E: Cloud Run (`antigravity-backend-00211-tjj`), Vercel (`dpl_HmNnfCKYviY6tRVa3Hgryo8VmDWi`), Cloudflare (`tabijiapp-edge-shield` `e89aecbf` & `cloudinary-proxy` `f06bc6fe`), Supabase (`cleanup-cloudinary` v7 撤銷舊 Key 後實測 `200`), Cloudinary（新 Key `686667511485883` `200` / 舊 Root Key `996197457174111` `401 disabled api_key`）, Chrome 實機 `nextImageRequests=[]`, `brokenImgCount=0`, Canvas WebP 上傳 `200` 並清理完成。

---

## 1. 工程與檔案異動清單（2026-11-22）

- **PR 1：Cloudinary 簽章收斂與五雲零停機金鑰輪換（CP 1 → CP 13，19 檔）**:
  - [backend/routers/cloudinary.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/cloudinary.py) (`+283` 新增) & [backend/main.py](file:///d:/Project/tabiji/travel-pwa/backend/main.py) (`+2`): 建置鑑權 `POST /api/sign-cloudinary`（前置 LRU 右端 GFE IP `240/min`、`Depends(get_verified_user)` 單次驗簽、`uid.lower()` `60/min` SlowAPI、`±600s` 非前導零時間戳、RFC 9110 §8.6 嚴格 `Content-Length` 與 `4096B` 串流截斷、`public_id` 鎖定 `ryan_travel/streetview` + `^mly_[0-9A-Za-z_-]{1,64}\Z`、原子回傳 `{ signature, apiKey, cloudName }` 與 `Cache-Control: no-store`）。
  - [frontend/lib/api.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/api.ts) (`+39`) 與 6 處上傳入口（[image-upload.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/ui/image-upload.tsx)、[multi-image-upload.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/ui/multi-image-upload.tsx)、[TripCoverMenu.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/TripCoverMenu.tsx)、[TripSettingsView.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/TripSettingsView.tsx)、[capsule-upload.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/capsule-upload.ts)、[mapillary.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/mapillary.ts)）: 統一經 `cloudinaryApi.signUpload()` 自動注入 JWT 與 401 換票重試，優先採用回傳之原子憑證。
  - [cloudflare/edge-shield/worker.js](file:///d:/Project/tabiji/travel-pwa/cloudflare/edge-shield/worker.js) (`+2/-6`)、刪除 `frontend/app/api/sign-cloudinary/route.ts` (`-70`)、更新 [frontend/next.config.mjs](file:///d:/Project/tabiji/travel-pwa/frontend/next.config.mjs): 切換 Edge Shield 轉發 Cloud Run，四網域未鑑權一律回 `401`；自 Vercel 全環境與本機 `frontend/.env.local` 徹底移除 `CLOUDINARY_API_SECRET`，GCP Secret Manager 新增純 27 bytes v2 並鎖 `:2`，Supabase `cleanup-cloudinary` 輪換密鑰並 `unset NEXT_PUBLIC_CLOUDINARY_API_KEY`，舊 Root Key `996197457174111` 停用確認回 `401 disabled api_key`。
  - 測試與資安歸檔：[test_cloudinary_sign_sentinel.py](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_cloudinary_sign_sentinel.py) (`17 tests`, 固定時鐘消除跨秒浮動)、[cloudinary-upload-components-sentinel.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/cloudinary-upload-components-sentinel.test.tsx)、[prod-auth-and-edge-resilience.test.ts](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/prod-auth-and-edge-resilience.test.ts)（遷移 `F9`/`F14`）及 `docs/security/` 4 檔。
- **PR 2：前端分級壓縮、收據直傳、孤兒路由拆除與 Proxy 安全加固（25 檔）**:
  - [frontend/lib/image-utils.ts](file:///d:/Project/tabiji/travel-pwa/frontend/lib/image-utils.ts) (`+717/-63`): 集中式 `IMAGE_PRESETS`（支援字串鍵入參護舊 mock）、`hasCanvas2dSupport()` 0ms jsdom 預檢、`SerialTaskSignal` 8s 逾時防晚醒單併發串行佇列、`createImageBitmap` + 1×1 WebP 探針防 Safari 靜默 PNG、無條件 `#ffffff` 白底防 `bg-black/95` 透明黑字隱形、`16_000_000 px` iOS 上限與 VRAM 歸零、64KB JPEG EXIF Marker Walker、`preserveShortEdge` 長收據／LINE 長截圖幾何公式、`readImageFileAsDataUrl()` 全點陣＋HEIC 空 MIME 正規化與 `__resetImageUtilsForTesting()`。
  - 全前端 7 處上傳與 AI 附圖入口＋3 處 `<Image unoptimized>`（[TripSettingsView.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/TripSettingsView.tsx)、[TripDialogs.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/TripDialogs.tsx)）＋縮圖收斂（[TimelineCardOverlay.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/TimelineCardOverlay.tsx)、`multi-image-upload.tsx` 補 `f_auto`）＋[expense-dialog.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/expense-dialog.tsx) 原子 `localReceipt` 直傳 AI 與 `initializedKeyRef` 跨筆隔離＋[AiImportTripWizard.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/itinerary/AiImportTripWizard.tsx)／[chat-widget.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/chat-widget.tsx) 原子 `useRef` 鎖與 HEIC 預覽降級＋全上傳器 `.heic -> .jpg` URL 正規化與卸載 `xhr.abort()`。
  - 刪除未鑑權 `.vercel.app` 孤兒後門 `frontend/app/api/parse-receipt/route.ts` (`-113`) 並遷移 [ai-remediation-sentinel.test.ts](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/ai-remediation-sentinel.test.ts)。
  - [backend/routers/ai.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/ai.py) (`+190/-29`) & [backend/main.py](file:///d:/Project/tabiji/travel-pwa/backend/main.py) (`+66/-15`): 頂層 `Image.MAX_IMAGE_PIXELS`、前後端位元級一致長條縮放 (`int(orig_w * s + 0.5)` + `LANCZOS`)、`parse_receipt` Base64 降級回拉 `imageUrl`、`/api/chat` 與 `/api/ai/parse-md` 與 `/api/ai/parse-receipt` 強制 MIME 白名單＋實體圖片/PDF `%PDF-` 驗簽（`reject_unidentified=True`、`except HTTPException: raise`）。
  - [cloudflare/cloudinary-proxy/worker.js](file:///d:/Project/tabiji/travel-pwa/cloudflare/cloudinary-proxy/worker.js) (`+210/-75`): `dnpcnwrcu` fallback、`new URL()` 精確主機與 `/^travel-[a-z0-9-]+-tyrantpipers-projects\.vercel\.app$/` 白名單、嚴格路徑正則擋轉換注入、`c_limit` + RFC `prefersAvif()`、`?fmt=` 隔離快取鍵、剝除上游 7 種快取/偵錯標頭、攔截 `image/svg*` 與非圖片 200 回 `415 sandbox`、非 200 一律 `no-store`。
  - 新增 5 支前後端／Worker Sentinel 測試檔與 `docs/security/` 3 檔。

---

## 2. 本日實戰事件、架構決策與經驗沉澱

### 🟢 Features & Fixes
- **PR 1 密鑰零停機收斂（CP 1 → CP 13 閉環）**：根除原本 Cloud Run 26 碼損毀密鑰（導致 `users.py` 換頭貼與 `gdpr.py` 刪帳靜默 401）、移除 Vercel `CLOUDINARY_API_SECRET`、補齊 4 網域 JWT 簽章門禁並成功停用舊 Root Key。
- **PR 2 全鏈路媒體瘦身與邊緣防禦**：根除 8K 頭貼/收據浪費、收據雙向回拉、長收據糊字、設定頁 `/_next/image` 離線破圖、`.vercel.app/api/parse-receipt` 孤兒後門、Windows 空 MIME HEIC 破圖、偽造 SVG 穿透 Gemini 與 `cloudinary-proxy` 404 永久快取 1 年毒丸（實地於 Chrome Network 捕獲 `Nov 19` 舊毒丸對照新版 `200 OK`）。
- **業界對標知識庫留存**：於使用者 NotebookLM 帳號建立獨立研究庫 `d18929b1-77c4-48ac-b4df-bb004e015388`（19 份官方與業界來源），作為後續評估 R2 或壓縮調優之長期參考。

### 🏛️ Architecture Decisions
- **AD-238（Cloudinary 簽章收斂至 Cloud Run 鑑權端點與原子憑證輪換契約）**：`CLOUDINARY_API_SECRET` 僅存 Cloud Run 與 Supabase Edge Function；`POST /api/sign-cloudinary` 透過 `_bind_verified_user_for_sign` 依序執行前置 LRU 右端 GFE IP 限流（`240/min`）→ `Depends(get_verified_user)` → SlowAPI `uid.lower()`（`60/min`），`public_id` 嚴格限縮於 `ryan_travel/streetview` (`^mly_...`)，並以原子 `{ signature, apiKey, cloudName }`（`no-store`）支援無痛換鑰。
- **AD-239（前端零依賴分級壓縮引擎、iOS Safari 16.7MP 防護與透明白底契約）**：`image-utils.ts` 集中管理 7 組 `IMAGE_PRESETS`、單併發取消訊號佇列（`SerialTaskSignal` + `hasCanvas2dSupport()`）、`createImageBitmap` + 1×1 WebP 探針防 Safari 靜默 PNG、無條件 `#ffffff` 白底（防暗色預覽隱形）、64KB JPEG EXIF 檢查、`readImageFileAsDataUrl()` 全格式空 MIME 正規化，與上傳端 `.heic -> .jpg` URL 正規化。
- **AD-240（日本長條收據雙端位元級一致縮放與 AI 端點實體圖片消毒契約）**：前後端對 `aspect > 2.0` 共用 `s = min(1, 1200/short, 4096/long, sqrt(5_000_000/(W*H)))`（Python 用 `int(w * s + 0.5)` + `LANCZOS` 對齊 JS `Math.round`）；`ExpenseDialog` 以 `localReceipt: { url, dataUrl }` + `initializedKeyRef(editItem.id)` 直傳 AI 並保留 `receiptUrl` 回退；`/api/chat`、`/api/ai/parse-md`、`/api/ai/parse-receipt` 強制 MIME 白名單與實體解碼／`%PDF-` 驗簽。
- **AD-241（Cloudflare `cloudinary-proxy` 零快取投毒、防 SVG XSS 與精確 Vercel 預覽白名單契約）**：保留 `travel-pwa-five.vercel.app` 於精確白名單並將預覽正則鎖死於專案持有者 scope（`travel-*-tyrantpipers-projects.vercel.app`）；阻斷轉換注入、`image/svg*`／非圖片 200（`415 sandbox`）；剝除上游 `cdn-cache-control`/`vary`/`x-cld-error`/`server-timing`/`access-control-expose-headers`；僅 `GET 200 image/*` 寫入 1 年 `immutable`。
- **AD-242（跨頁共用封面 `<Image unoptimized>` 與 SWR/SW 快取一致性契約）**：首頁已加 `unoptimized` 的外部封面在 `TripSettingsView` 與 `TripDialogs` 必對稱加 `unoptimized`（共用水位、0 額外 `/_next/image` 請求、離線不破圖），並維持 `sw.ts` `trip-external-images` 採 `StaleWhileRevalidate`。
- **AD-243（五雲零停機密鑰輪換與 MCP/CLI 權限邊界實戰規範）**：Cloudinary 每上傳 1 圖固定扣 `1 tx`（`1 tx ≡ 1 MB` 頻寬損益點）；GCP Secret Manager 必寫純無換行新版本並鎖顯式版號（`:2`）；`@mcp:vercel`（8 工具）與 `@mcp:supabase`（官方架構零明文阻斷）不改密鑰，改採本機官方 CLI 授權或 Dashboard，嚴禁透過 Chrome 自動化或讀設定檔代填生產密鑰。

### 🔴 Technical Debt
- **DEBT-STORAGE-HISTORICAL-180-01（Open — 非阻斷）**：既有 180 張歷史舊收據（`454 MiB` / `0.57 credits`）仍佔儲存大宗；待用量逼近免費上限再決定批次覆寫重壓或遷移 R2。
- **DEBT-RECEIPT-OCR-AB-01（Open — 待實測）**：尚缺 10–20 張真實日本極端長條熱感紙收據 CER A/B 實測；另 `EXTRACTION_ROUTING[0]` (`gemini-3.5-flash-lite`) 標記 `supports_media_resolution=False`，若補設 `media_resolution_high` 會於主路由遭自動剝離。
- **DEBT-AUTH-SESSION-RL-01（Open — 跨模組殘留）**：[backend/routers/auth.py](file:///d:/Project/tabiji/travel-pwa/backend/routers/auth.py#L263) `POST /api/auth/session` 仍採預設 `get_rate_limit_key`（可透過輪換 `X-Gemini-API-Key` 繞過 20/min 限流），留待獨立資安 PR 收斂。
- **DEBT-IOS-PHYSICAL-MEDIA-01（Open — 實機視覺覆驗）**：實機 iPhone Safari 48MP HEIC 16.7MP 記憶體峰值與動態島頂距尚待實體機目視確認；另工作區未追蹤之 `supabase/.temp/` 切勿加入 commit，且建議於對話清理後視需求再輪換一次曾貼於對話紀錄之 Cloudinary 金鑰。

### 🛡️ Failed Paths
- **FP-106（SlowAPI 與 `Depends(get_verified_user)` 順序及 CWE-290 多重 XFF / FIFO 驅逐陷阱）**：FastAPI 先解 `Depends(get_verified_user)` 才進 `@limiter.limit`，導致 `key_func` 內 IP fallback 成死碼；單用 `headers.get("x-forwarded-for")` 忽略多標頭右端真實 IP、普通 `dict` 為 FIFO 而非 LRU 驅逐會歸零活躍攻擊者、UUID 大小寫未 `.lower()` 會拆分限流桶。
- **FP-107（GCP Secret Manager 尾端換行／`:latest` 與 Vercel `.vercel.app` 孤兒路由雙網域盲區）**：舊 v1 密鑰尾端含空白且缺字元導致線上頭貼/GDPR 刪除長期靜默 401；Cloud Run `:latest` 僅於新 Revision 解析；主網域 `www.tabijiapp.com` 受 Edge Shield 遮蔽回 404，會長期掩蓋 `travel-pwa-five.vercel.app` 上未鑑權孤兒路由（`/api/sign-cloudinary`、`/api/parse-receipt`）。
- **FP-108（iOS Safari `toBlob('image/webp')` 靜默 PNG、空 MIME `.heic` 破圖與 jsdom 8 秒死鎖）**：現代 iOS Safari 仍不支援原生 WebP Canvas 編碼並靜默吐出巨型 PNG；Windows Chrome 選取 `.heic`/`.jpg` 常給空 MIME 致 `FileReader` 產出 `octet-stream` 或上傳後回 `.heic` URL 破圖；Node 20+ jsdom 有 `URL.createObjectURL` 卻無 2D Canvas 造成 8 秒逾時死鎖，須靠 `hasCanvas2dSupport()` 與 `SerialTaskSignal` 根治。
- **FP-109（`cloudinary-proxy` 四重陷阱：workers.dev 無快取＋上游 `cdn-cache-control: no-store`＋404 一年毒丸＋預覽正則誤封）**：即使未來綁自訂域，若未剝除 Cloudinary 上游 `cdn-cache-control: no-store` 與 `Vary: Save-Data` 仍會 `BYPASS`；對 404 寫入 `immutable` 一年實證毒害真實 Chrome 磁碟快取 3 天；預覽正則漏看實際 `travel-<hash>-tyrantpipers-projects.vercel.app` 格式造成自家人 403 且放過 `travel-pwa-evil.vercel.app`。
- **FP-110（`ai.py` 雙層 `except Exception:` 靜默吞錯穿透 Gemini 與 `time.time()` 跨秒測試浮動）**：`process_and_optimize_image_sync` 預設吞掉 `UnidentifiedImageError` 與 `main.py` 外層 `except Exception` 會使偽造 `<svg>` 標為 `image/jpeg` 直打 Gemini；測試未凍結 `time.time()` 會在跨秒邊界導致 `now + 601` 偶發變 `200` 失敗。
- **FP-111（Windows 隔離 Git Worktree 殘留檔案引發 VS Code TS Server 假紅字）**：`git worktree remove` 遇編輯器鎖定殘留半刪除目錄時，TS Server 會對該舊目錄報 `No inputs were found in config file`，清除殘留暫存目錄並重啟 TS Server 即解。

### 🎯 Next Steps
- 提交並推送本日報與 `.agents/domains/*.md` 進化記憶（排除 `supabase/.temp/`）後，本聊天室即可安全歸檔刪除。
- 後續獨立排程：收斂 `POST /api/auth/session` 限流鍵（`DEBT-AUTH-SESSION-RL-01`）、實機 iPhone Safari 驗收 48MP HEIC 與動態島間距，以及視 Cloudinary 儲存成長評估歷史 180 張收據重壓或 R2 遷移。

---

## 🧬 Machine-Executable Invariant Rules

```json
[
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BACKEND-CLOUDINARY-SIGN-01",
    "title": "Cloudinary 簽章端點雙層限流、嚴格白名單與原子輪換契約 (AD-238)",
    "content": "POST /api/sign-cloudinary 僅存於 Cloud Run (backend/routers/cloudinary.py)，嚴禁於 Vercel 保存 CLOUDINARY_API_SECRET。必須經 _bind_verified_user_for_sign 先執行前置 OrderedDict LRU 右端 GFE X-Forwarded-For IP 限流 (240/min, 遍歷 getlist('x-forwarded-for') 且 IPv6 .lower()，429 帶 Retry-After 與 Cache-Control: no-store)，再執行 Depends(get_verified_user) 寫入 request.state.verified_user_id，供 SlowAPI @limiter.limit('60/minute') 以 uid:{uid.lower()} 分桶。強制 RFC 9110 §8.6 Content-Length + 4096B 串流截斷、無前導零非布林 timestamp (±600s)、public_id 僅限 ryan_travel/streetview 且匹配 ^mly_[0-9A-Za-z_-]{1,64}\\Z、錯誤訊息禁用 gemini/api key/金鑰 關鍵字，並回傳原子 { signature, apiKey, cloudName } (Cache-Control: no-store)。"
  },
  {
    "domain": "ios_ui",
    "type": "INVARIANT_RULE",
    "id": "INV-IOS-CLIENT-IMAGE-COMPRESS-01",
    "title": "前端零依賴分級壓縮、iOS 16.7MP 防護、白底合成與空 MIME/HEIC 契約 (AD-239)",
    "content": "frontend/lib/image-utils.ts 集中定義 IMAGE_PRESETS (avatar 512 / spot 1600 / cover 1920 / document 2048 / receipt 2048+shortEdge / capsule 1600 / ai_input 1600+shortEdge) 並支援字串 preset 參數。必須實作 hasCanvas2dSupport() 0ms jsdom 預檢、帶 SerialTaskSignal 取消訊號與 8s 逾時之單併發佇列及 __resetImageUtilsForTesting()；優先 createImageBitmap(file)（禁傳 resizeWidth/resizeHeight 避開 Safari EXIF 旋轉倒置）；以 1x1 WebP 探針＋輸出 blob.type 雙驗防 Safari 靜默輸出 PNG；ctx.drawImage 前無條件填 #ffffff 防 bg-black/95 預覽透明黑字隱形；硬鎖 outW*outH <= 16_000_000 並於 finally 釋放 bitmap 與 canvas.width=0；僅對不透明 JPEG 切片前 64KB 檢查 APP1/APP13 EXIF；readImageFileAsDataUrl() 須依副檔名補齊空 MIME/octet-stream 標籤，所有 Cloudinary 上傳器將 .heic/.heif 回傳 URL 正規化為 .jpg 且卸載必 abort XHR。"
  },
  {
    "domain": "backend_concurrency",
    "type": "INVARIANT_RULE",
    "id": "INV-BACKEND-RECEIPT-AI-IMAGE-01",
    "title": "長條收據前後端位元級一致縮放、原子直傳與 AI 實體圖片消毒契約 (AD-240)",
    "content": "前後端對 aspect > 2.0 長條收據與長截圖共用 s = min(1, 1200/short, 4096/long, sqrt(5_000_000/(W*H)))，後端 ai.py 採 int(orig_w * s + 0.5) + img.resize(..., LANCZOS) 對齊 JS Math.round()，且於模組頂層設 Image.MAX_IMAGE_PIXELS = 50_000_000。ExpenseDialog 須以 localReceipt: { url, dataUrl } 同源綁定並以 editItem.id 鍵值化初始化，於上傳 200 時直傳 body.image 並保留 receiptUrl 回退。/api/chat、/api/ai/parse-md 與 /api/ai/parse-receipt 必須強制 MIME 白名單、validate=True Base64、reject_unidentified=True 實體解碼／PDF %PDF- 驗簽，且 /api/chat 外層必先 except HTTPException: raise 杜絕吞掉 400。"
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-DEVOPS-CLOUDINARY-PROXY-01",
    "title": "Cloudflare cloudinary-proxy 精確預覽白名單、SVG 415 攔截與零 404 快取契約 (AD-241)",
    "content": "cloudflare/cloudinary-proxy/worker.js 必須僅允許 GET/HEAD/OPTIONS (其餘 405)、以 new URL() 精確比對 ALLOWED_EXACT_HOSTS (含 travel-pwa-five.vercel.app) 與專案持有者預覽正則 /^travel-[a-z0-9-]+-tyrantpipers-projects\\.vercel\\.app$/、嚴格路徑正則阻斷轉換參數注入並強制注入 c_limit、以 RFC prefersAvif() (尊重 q=0) 與 ?fmt= 隔離 Cache Key、剝除上游 cdn-cache-control/cloudflare-cdn-cache-control/vary/set-cookie/x-cld-error/access-control-expose-headers/server-timing、攔截 image/svg* 及非圖片 200 回 415 + CSP: sandbox + no-store，並僅對 GET 200 image/* 設 1 年 immutable 與寫入 cache.put()，非 200 一律 Cache-Control: no-store。"
  },
  {
    "domain": "offline_pwa",
    "type": "INVARIANT_RULE",
    "id": "INV-PWA-SHARED-COVER-UNOPTIMIZED-01",
    "title": "跨頁共用外部封面 <Image unoptimized> 對稱與 SW StaleWhileRevalidate 守則 (AD-242)",
    "content": "凡首頁 (TabijiHomeDashboard/TripList) 已以直連 URL + unoptimized 渲染並快取之外部封面圖，次級視圖 (TripSettingsView、TripDialogs) 必須對稱加上 unoptimized，避免產生 /_next/image?url=... 異質請求造成 Vercel 額度雙耗與離線設定頁破圖。同時 sw.ts 之 trip-external-images 應維持 StaleWhileRevalidate，禁止貿然改為 CacheFirst 以免破壞無 CORS 外部圖離線快取或觸發 Safari 7MB Opaque 配額膨脹。"
  },
  {
    "domain": "devops_security",
    "type": "INVARIANT_RULE",
    "id": "INV-DEVOPS-FIVE-CLOUD-ROTATION-01",
    "title": "五雲零停機密鑰輪換、Secret 版號鎖定與 MCP/CLI 權限邊界契約 (AD-243)",
    "content": "GCP Secret Manager 寫入憑證必須為純 UTF-8 無尾端換行並於 Cloud Run 顯式鎖定版號 (如 :2 而非不支援熱重載之 :latest)；Supabase Edge Function 輪換密鑰透過授權 CLI --env-file 寫入後立即銷毀暫存檔，撤銷舊 Key 前必實測 cleanup-cloudinary 200 並 unset 殘留舊鍵。@mcp:vercel (8 工具) 與 @mcp:supabase (官方零明文架構) 不具改刪密鑰能力，必須走本機官方 CLI 授權或 Dashboard，嚴禁以 Chrome 自動化或讀取 MCP 設定檔方式處理生產密鑰。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-106",
    "title": "SlowAPI 與 Depends 執行順序倒置及 CWE-290 多重 XFF / FIFO 驅逐繞過陷阱 (FP-106)",
    "content": "FastAPI 會先執行 Depends(get_verified_user) 才進入 @limiter.limit 裝飾器，使 key_func 內未鑑權 IP fallback 成為死碼；僅用 request.headers.get('x-forwarded-for') 會被多重 XFF 標頭繞過；普通 dict 的 FIFO 驅逐會在滿表時將活躍攻擊 IP 計數歸零；UUID 大小寫未 .lower() 會拆成兩個 SlowAPI 分桶。必須以獨立前置 OrderedDict LRU 依賴 + getlist('x-forwarded-for') 逆序尾部解析 + uid.lower() 根治。"
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-107",
    "title": "GCP Secret 尾端換行損毀與雙網域遮蔽 .vercel.app 孤兒未鑑權路由陷阱 (FP-107)",
    "content": "GCP Secret Manager v1 曾存入 26 碼殘缺且含尾端換行之密鑰導致 Cloud Run 頭貼替換與 GDPR 刪圖長期靜默 401；同時主網域 www.tabijiapp.com 經 Edge Shield 回 404 會長期遮蔽 travel-pwa-five.vercel.app 上仍存活的無認證孤兒 Next.js API Route (/api/sign-cloudinary、/api/parse-receipt)。凡資安與路由稽核必須四網域穿透實測並於刪除舊路由後驗證 .vercel.app 實測回 404。"
  },
  {
    "domain": "ios_ui",
    "type": "FAILED_PATH",
    "id": "FP-108",
    "title": "iOS Safari WebP 靜默 PNG、空 MIME HEIC 破圖與 Node 20 jsdom 8 秒死鎖陷阱 (FP-108)",
    "content": "現代 iOS Safari 呼叫 canvas.toBlob('image/webp') 會靜默退回 2-6MB PNG；Windows/Android 選取 .heic 或部分 .jpg 時 file.type 為空字串，致 FileReader 輸出 application/octet-stream 遭後端 400 或傳上 Cloudinary 回 .heic URL 在 Chrome 100% 破圖；Node 20+ jsdom 具 URL.createObjectURL 但無 2D Canvas 實作會使未預檢之壓縮佇列卡死至 8s 逾時。必須以 1x1 探針＋blob.type 驗證、hasCanvas2dSupport() 預檢、SerialTaskSignal 取消訊號與 .heic->.jpg URL 正規化全面防禦。"
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-109",
    "title": "cloudinary-proxy 四重失真：workers.dev 無快取、上游 no-store、404 一年毒丸與預覽正則寫錯 (FP-109)",
    "content": "cloudinary-proxy 除 *.workers.dev 不啟用 caches.default 外，Cloudinary 上游亦回傳優先權更高的 cdn-cache-control: no-store 與 Vary: Save-Data；對 404 寫入 max-age=31536000, immutable 實證造成真實 Chrome 磁碟快取中毒 3 天；Vercel 預覽正則若誤寫 travel-pwa-*.vercel.app 會同時 403 誤封真實部署網址 travel-<hash>-tyrantpipers-projects.vercel.app 並 200 放過外部 travel-pwa-evil.vercel.app。"
  },
  {
    "domain": "backend_concurrency",
    "type": "FAILED_PATH",
    "id": "FP-110",
    "title": "ai.py 雙層 except Exception 靜默吞錯穿透 Gemini 與未凍結時鐘測試浮動陷阱 (FP-110)",
    "content": "process_and_optimize_image_sync 預設 except Exception 回傳原始位元組為 image/jpeg，加上 main.py 外層 except Exception，會使偽裝成 image/jpeg 的 <svg> 繞過驗證直打 Gemini API 且跳過 parse-receipt 的 imageUrl 回退；此外時間戳偏移測試若未以 monkeypatch 凍結 cloudinary_router.time.time，跨秒邊界會令 now+601 偶發通過變 200 造成 CI 浮動。"
  },
  {
    "domain": "devops_security",
    "type": "FAILED_PATH",
    "id": "FP-111",
    "title": "Windows 隔離 Git Worktree 殘留目錄引發 VS Code TS Server 假紅字陷阱 (FP-111)",
    "content": "在 Windows 進行隔離 Git Worktree 沙盒測試時，若刪除 worktree 期間編輯器或 tsserver 鎖住檔案，會殘留無 .ts 檔的空殼目錄導致 VS Code Problems 顯示 No inputs were found in config file 假紅字。清理沙盒必須先以 rmdir 安全卸載 NTFS Junction，再徹底 Remove-Item 確認目錄不存在並執行 git worktree prune。"
  }
]
```
