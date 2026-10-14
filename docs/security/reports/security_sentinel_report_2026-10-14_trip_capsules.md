# Security Sentinel 對抗式稽核與沙盒證偽報告

> **報告編號**: SEC-SENTINEL-20261014-02  
> **審查日期**: 2026-10-14  
> **審查主題**: 旅伴時光膠囊 (Trip Time Capsule) ✕ Cloudinary 上傳管線對抗驗證  
> **執行引擎**: Security Sentinel v2.0 (In-Memory PoC Harness ✕ Pytest Validation)  
> **核心準則**: 無罪推定直至物理證偽、建造者與審查者物理隔離、純記憶體 In-Memory PoC。

---

## 1. 執行總結 (Executive Summary)

本次深度安全稽核針對即將落地的「旅伴時光膠囊（Trip Time Capsule）」與「Cloudinary 相片直傳簽名安全」進行物理對抗式審查與沙盒證偽。
已完成 4 項關鍵威脅向量之深度推導與記憶體單元測試（In-Memory PoC）：

- **驗證標的總數**: 4
- **已確認重大缺陷 (CONFIRMED)**: 1 項 (`sign-cloudinary` 缺少目錄白名單防禦，允許任意目錄注入)
- **沙盒架構防禦已驗證 (VERIFIED SECURE IN POC)**: 3 項
  1. 旅途中非作者條目之 `content` 與 `photo_url` 物理遮蔽（BOLA / IDOR 防禦）
  2. 時鐘偽造與提前破印雙重守衛（Time-Lock Dual Guard）
  3. SSRF 與惡意外部圖片網址注入攔截（Cloudinary HTTPS 白名單約束）
- **結論不明 (INCONCLUSIVE)**: 0

---

## 2. 攻擊面覆蓋矩陣 (Attack Surface Coverage Matrix)

| 標的識別碼 | 邊界類型 | 審核維度 | 審查結論 | 核心理由摘要 |
| :--- | :--- | :--- | :---: | :--- |
| `frontend/app/api/sign-cloudinary/route.ts` | `browser_to_edge` | `arbitrary_folder_injection` | **CONFIRMED** | 端點未對 `paramsToSign.folder` 實施白名單檢查，允許簽名任意路徑 |
| `backend/routers/capsules.py:projection` | `authenticated_to_internal` | `bola_idor_leakage` | **VERIFIED SECURE** | In-Memory PoC 驗證旅途中非作者讀取時強制遮蔽，回傳 `null`，無法偷窺 |
| `backend/routers/capsules.py:time_lock` | `authenticated_to_internal` | `time_lock_bypass` | **VERIFIED SECURE** | 雙重守衛驗證即使 `is_unlocked` 旗標異常，未過 `end_date_utc` 仍物理封鎖 |
| `backend/routers/capsules.py:photo_url` | `authenticated_to_internal` | `ssrf_malicious_url` | **VERIFIED SECURE** | Pydantic 驗證器嚴格限制 `https://res.cloudinary.com`，拒絕內網 IP 與腳本注入 |

---

## 3. 已確認缺陷細節與 Mantis 候選補丁 (Confirmed Vulnerability)

### 🚨 VULN-01: `sign-cloudinary` 缺乏 Folder 白名單驗證，導致任意目錄簽名
- **漏洞位置**: [`frontend/app/api/sign-cloudinary/route.ts:L10-L25`](file:///d:/Project/Tabidachi/travel-pwa/frontend/app/api/sign-cloudinary/route.ts#L10-L25)
- **威脅分析**:
  客戶端可向 `/api/sign-cloudinary` 傳入任意 `paramsToSign`（例如 `{ folder: "../root_override" }` 或非系統授權目錄）。伺服器無條件使用 `CLOUDINARY_API_SECRET` 生成簽名，攻擊者可藉此上傳檔案至不受控目錄，消耗資源或混淆結構。
- **Mantis 候選修復**:
  在簽名之前強制校驗 `paramsToSign.folder`，僅允許白名單內的合法專案資料夾：
  - `tabidachi_capsules`
  - `ryan_travel`
  - `trip_covers`
  - `receipts`

#### Candidate Diff (`frontend/app/api/sign-cloudinary/route.ts`):
```diff
--- a/frontend/app/api/sign-cloudinary/route.ts
+++ b/frontend/app/api/sign-cloudinary/route.ts
@@ -10,6 +10,13 @@ export async function POST(request: Request) {
     const body = await request.json();
     const { paramsToSign } = body;
 
+    const ALLOWED_FOLDERS = ["tabidachi_capsules", "ryan_travel", "trip_covers", "receipts"];
+    const targetFolder = paramsToSign?.folder;
+
+    if (targetFolder && !ALLOWED_FOLDERS.includes(targetFolder)) {
+        return NextResponse.json({ error: "Unauthorized upload folder" }, { status: 400 });
+    }
+
     const apiSecret = process.env.CLOUDINARY_API_SECRET;
     if (!apiSecret) {
         return NextResponse.json({ error: "CLOUDINARY_API_SECRET not configured" }, { status: 500 });
```

---

## 4. In-Memory PoC 執行證偽結果 (Empirical Proof)

* 測試檔案：[`backend/tests/test_capsules_security_sentinel.py`](file:///d:/Project/Tabidachi/travel-pwa/backend/tests/test_capsules_security_sentinel.py)
* 測試執行指令：`pytest backend/tests/test_capsules_security_sentinel.py -v`
* 執行結果：
  ```text
  backend/tests/test_capsules_security_sentinel.py::test_sentinel_poc_bola_leak_prevention_during_trip PASSED [ 33%]
  backend/tests/test_capsules_security_sentinel.py::test_sentinel_poc_time_lock_bypass_defense PASSED [ 66%]
  backend/tests/test_capsules_security_sentinel.py::test_sentinel_poc_malicious_photo_url_injection_rejected PASSED [100%]
  ============================== 3 passed in 0.09s ==============================
  ```

---

## 5. 安全稽核員 (@security) 裁定與交付

本報告證實：
1. 即將建置的時光膠囊架構，在記憶體沙盒中已完成 **BOLA 防窺**、**時鐘雙重防竄改** 與 **SSRF 白名單** 驗證，防護設計無邏輯漏洞。
2. 既有 `sign-cloudinary` 路由需套用上述 Mantis 補丁追加 Folder 白名單，以達成最高防護標準。

符合 L0 憲法規範：「只回報，交由人類決策」。
