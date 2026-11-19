# 🪞 雙層遮蔽效應與五雲密鑰分離：一次跨越三日的全棧病理剖析 (`2026-11-17 ~ 2026-11-19`)

> **臨床類比**: 就像病人同時服用兩種藥物卻出現交叉掩蓋症狀——外層藥物壓住了發燒，反而讓底下細菌性肺炎一路隱匿惡化；直到停用外層干擾或抽絲剝繭對齊「真實五端現場」，深層病因與安全邊界才會浮現。

---

## 一、雙層缺陷遮蔽效應（Two-Layer Bug Masking & Edge Masking）

1. **周邊 POI 搜尋的雙月盲區 (`2026-10-21` + `2026-10-25` ➔ `2026-11-19`)**:
   - 第一層：`2026-10-21` (`ba37b92`) Cloudflare `edge-shield` 用寬鬆正則攔截所有 `GET /api/poi/*` 轉進只有 D1 口袋庫的 `poi-service`，導致主網域 `www.tabijiapp.com` 長期回傳 `401` / `404`。
   - 第二層：`2026-10-25` (`7f5f680`) 後端直連清單頁的 `search_poi_combined` 在跳過需 Key 的 OpenTripMap 後退化為僅靠 Overpass 單點供應；反觀舊網域因代理路徑差異沒撞上第一層，讓開發者產生「有時候還好好的」錯覺。
   - **教訓**: 單靠一個網域沒報錯或修掉第一層攔截，並不代表下層健壯；高風險外部依賴（Overpass）必須以多供應商競速（Photon / Wikipedia / Nominatim）消除單點故障。
2. **Edge Shield Masking 遮蔽原生 Vercel 暴露 (`/api/cloudinary-test`)**:
   - `www.tabijiapp.com/api/cloudinary-test` 經 Edge Shield 轉發後端回傳 `404`，看似安全；但直打原生網域 `travel-pwa-five.vercel.app/api/cloudinary-test` 卻直接吐出 `HTTP 200` 與部分密鑰資訊。
   - **教訓**: 雙網域或任何設有邊緣反向代理的架構，安全探測必須對**所有入口網域**（自訂網域、`*.vercel.app`、`*.workers.dev`、`*.run.app`）個別穿透驗證。

---

## 二、靜默失效的共用模式（RLS 收緊與冷卻窗口反噬）

1. **匿名前端碰上 `auth.uid()` RLS `...v2`（靜默歸零）**:
   - 當系統以自建 JWT 取代 Supabase Auth 登入，前端拿著公開 `Publishable Key`（`auth.uid() = NULL`）面對綁定 `{authenticated}` 的 RLS 時，PostgREST 不報 `401`，而是靜默回 `[]`；`postgres_changes` 也不報錯，而是靜默丟棄推播——致使通知中心自 `2026-09-20` 起全員已讀歸 `0`，活動增刪改停止即時同步而其他已接廣播的模組卻仍正常。
   - **黃金解方**: 以不透明 `Broadcast` 訊號（REST 端嚴禁手動補上 `realtime:` 前綴，交給 SDK 自己補）做 10–50ms 敲門，搭配經 JWT 驗簽的 FastAPI `service_role` 端點拉取最新狀態。
2. **SWR 輪詢週期＞冷卻時間的醫源性風暴**:
   - `lastExchangeFailedAt < 10000ms` 與 `lastDismissedAt < 5000ms` 初衷是防抖，卻小於 SWR `refreshInterval: 15000ms`，導致永久性 `401` 每 15 秒反覆觸發換票與彈窗；改採**JSON 憑證指紋鎖（`lastFailedExchangeFingerprint`）＋頁面記憶體靜默標記（`isReauthDismissedInMemory`）＋ CAS 刪票檢查**後徹底收斂。

---

## 三、三總管密鑰分離與長期營運日曆（對話刪除前固化清單）

1. **識別、再登錄與門票的三層權責**：
   - **`user_uuid`**：資料庫永不變更之跨表外鍵身分識別碼；遇到未入庫之合法孤兒 UUID 應就地註冊並發放首組引繼碼，避免鎖死使用者。
   - **`tbj_rec_*` + `RECOVERY_PEPPER` + `VAULT_MASTER_KEY`**：用戶端亂數引繼碼與雙向保險庫／單向雜湊驗證（嚴禁與短期 `SESSION_SECRET_KEY` 或 `SUPABASE_KEY` 耦合派生；Secret Manager 金鑰派生注意 `.strip()`／尾端 CRLF 分裂）。
   - **`sb_publishable_` / `sb_secret_`**: 非 JWT 格式，手寫 REST/Edge 請求一律只放 `apikey`、禁用 `Authorization: Bearer`，且嚴禁轉發瀏覽器 `User-Agent`。
2. **跨日保留與後續待辦行事曆 (Actionable Debt Ledger)**：
   - **2027-02-16 後（90 天寬限期屆滿）**：於下一次部署 Cloud Run 時順手移除 `LEGACY_SESSION_SECRET_KEY`（`legacy-session-secret-key:1/:2`）與 `supabase-key:1`，並至 Supabase Dashboard 複核 Legacy `service_role` 與 `vault.secrets` 中 `2026-04-25` `service_role_key` 舊紀錄已停用清理（`DEBT-LEGACY-SECRET-SUNSET-01`）。
   - **`push_subscriptions` `anon` RLS 收回 (`DEBT-PUSH-RLS-01`)**：待線上 `/api/push/subscribe` 穩定運行後移除舊表 `anon` 直寫政策。
   - **Travelpayouts 兩條即時機票管線重連 (`DEBT-FLIGHT-PRICING-01`)**：目前僅以 `^[A-Z]{3}$` 阻斷無效 400 請求；`DeepResearch` 需串接 `airport-mapping.ts` / `travel_data.py`，`/api/chat/stream` 需接回 `_build_price_context()`。
   - **4 項僅有單元測試覆蓋之線上實機待驗情境**：雙瀏覽器 `T2` Broadcast 即時同步、瀏覽器 Web Push 系統彈窗送達、多成員已結束行程 `Day 0` 膠囊實機揭曉、以及 [notify-event/index.ts](file:///d:/Project/tabiji/travel-pwa/supabase/functions/notify-event/index.ts) Sentinel CLI 複驗。
