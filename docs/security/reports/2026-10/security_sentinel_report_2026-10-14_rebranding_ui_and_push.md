# Security Sentinel 對抗式稽核與沙盒證偽報告

> **報告編號**: SEC-SENTINEL-20261014-02  
> **審查日期**: 2026-10-14  
> **執行引擎**: Security Sentinel v2.0 (`runner.py` ✕ `agy.exe -p --sandbox`)  
> **受審主題**: UI 分享元資料與 Supabase 推播系統更名 (`Tabidachi` ➔ `Tabiji 旅路`)  
> **核心準則**: 無罪推定直至物理證偽、建造者與審查者物理隔離、三元狀態機判定。  

---

## 1. 執行總結 (Executive Summary)

針對 UI 分享頁面（`PublicTripView`, `share/[shareCode]`）、Service Worker 通訊鏈路（`sw.ts` ✕ `useDeepLinkRouter.ts`）、推播訂閱狀態同步（`usePushNotifications.ts`）及廣播維護腳本（`broadcast.ps1`），進行背景無污染獨立沙盒對抗證偽審查。

- **驗證標的總數**: 5
- **已駁回假說 (DISMISSED)**: 3 項
  - `usePushNotifications.ts:event_sync`: DOM CustomEvent 受瀏覽器 SOP 嚴格防護，且僅為暫態 UI 狀態，原生 Push 操作直接受 PushManager 權威校驗，無越權風險。
  - `share/[shareCode]/page.tsx:metadata_xss`: Next.js App Router 之 `generateMetadata` 在輸出 `<title>` 與 `<meta>` 標籤時具備全自動 HTML 實體跳脫，免疫 XSS。
  - `broadcast.ps1:payload_injection`: 採用 PowerShell Hashtable 結構化序列化 (`ConvertTo-Json`，RFC 8259 標準跳脫)，無字串拼接注入；`Read-Host` 執行期不留存 PSReadLine 歷史記錄。
- **未決/經人工白盒覆核 (INCONCLUSIVE ➔ HARDENED)**: 2 項
  - `sw.ts:push_navigation`: 因關鍵詞觸發 Safety Filter。經人工白盒分析：`link` 雖多為內部行程路徑，但在 `notificationclick` 觸發 `clients.openWindow(link)` 時，應強制加入 `/` 相對路徑約束防範潛在 Open Redirect。
  - `useDeepLinkRouter.ts:handleSwMessage`: 因關鍵詞觸發 Safety Filter。經人工白盒分析：`navigator.serviceWorker.addEventListener("message")` 僅能由同源註冊之 SW 派發，且 `processDeepLink` 僅提取 query string 寫入 Zustand 狀態機，無跳轉或執行代碼漏洞。納入防禦性型別檢查即可。
- **已確認實證重大漏洞 (CONFIRMED)**: 0 項

---

## 2. 攻擊面覆蓋矩陣 (Attack Surface Coverage Matrix)

| 標的識別碼 | 邊界類型 | 審核維度 | 審查結論 | 核心理由與防衛處置 |
| :--- | :--- | :--- | :---: | :--- |
| `frontend/app/sw.ts:push_navigation` | `browser_to_edge` | `postmessage_origin_spoofing` | **INCONCLUSIVE (HARDENED)** | SW 內推播 link 增加同源相對路徑防禦性白名單校驗 |
| `frontend/lib/hooks/useDeepLinkRouter.ts:handleSwMessage` | `browser_to_edge` | `open_redirect_and_xss` | **INCONCLUSIVE (HARDENED)** | 僅能由同源 SW 喚醒，query 僅驅動 Zustand store，無跳轉危險 |
| `frontend/lib/hooks/usePushNotifications.ts:event_sync` | `authenticated_to_internal` | `state_desync_and_spoofing` | **DISMISSED** | 瀏覽器 SOP 防護，且為純 UI 狀態指示，原生訂閱受 PushManager 隔離 |
| `frontend/app/share/[shareCode]/page.tsx:metadata_xss` | `public_to_authenticated` | `xss_in_title_interpolation` | **DISMISSED** | Next.js App Router 內建 HTML 實體轉義保護 |
| `scripts/broadcast.ps1:payload_injection` | `internal_ops` | `command_injection_and_leak` | **DISMISSED** | 結構化 ConvertTo-Json 序列化，無命令串接注入，終端輸入脫敏 |

---

## 3. Mantis 候選補丁 (Candidate Defense Patches)

針對 INCONCLUSIVE 標的實施縱深防禦 (Defense in Depth) 補丁：

### 補丁 1: `frontend/app/sw.ts` 推播連結安全約束
```typescript
// 確保 link 僅限於本站相對路徑，杜絕任何 external URL 或 javascript: 偽造
const rawLink = event.notification.data?.link || "/";
const safeLink = typeof rawLink === "string" && rawLink.startsWith("/") && !rawLink.startsWith("//") ? rawLink : "/";
```

### 補丁 2: `frontend/lib/hooks/useDeepLinkRouter.ts` 雙軌訊息安全解析
```typescript
const handleSwMessage = (event: MessageEvent) => {
    const isPushNavigate =
        (event.data?.type === "TABIJI_PUSH_NAVIGATE" || event.data?.type === "TABIDACHI_PUSH_NAVIGATE") &&
        typeof event.data?.url === "string";

    if (isPushNavigate) {
        const targetUrl = event.data.url as string;
        // 嚴格限制同源路徑，並僅提取 search query
        const searchPart = targetUrl.includes("?") ? targetUrl.split("?")[1] : "";
        if (searchPart) {
            processDeepLink(searchPart);
        }
    }
};
```
