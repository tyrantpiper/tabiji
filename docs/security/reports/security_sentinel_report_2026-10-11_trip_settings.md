# 🛡️ Security Sentinel 對抗安全審查報告 (Trip Settings Sub-View & Permissions)

> **審查日期**: 2026-10-11 21:42:00 (UTC+8)  
> **稽核者**: `@security` (Security Sentinel Engine v2.0)  
> **模式**: 純記憶體沙盒對抗證偽 (In-Memory Sandbox Mock PoC)  
> **涵蓋邊界**: `authenticated_to_internal`, `browser_to_edge`, `client_side_state_isolation`

---

## 1. 執行總結 (Executive Summary)

針對使用者提出的全新「全屏行程設定頁面（`TripSettingsView`）」與「頂部全寬導航列（`ItineraryHeader` ⚙️）」架構，執行端到端對抗審核與沙盒證偽：
- **受測目標數**: 4 項攻擊假說
- **實證安全 (DISMISSED)**: 4 項（均由純記憶體單元測試完成反向證偽）
- **確認漏洞 (CONFIRMED)**: 0 項
- **整體安全等級**: **SECURE (PASSED)**

---

## 2. 攻擊面與假說對抗驗證矩陣 (Attack Surface Matrix)

| 測試編號 | 受測端點 / 模組 | 攻擊向量 | 假說內容 | 沙盒證偽證據 | 判定結果 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SEC-SET-01** | `DELETE /api/trips/{trip_id}` | IDOR 越權刪除 | 非建立者或任意攻擊者可能刪除他人的旅遊行程 | `test_trip_settings_sentinel.py:test_sentinel_delete_trip_idor_non_creator_blocked` 驗證後端比對 `created_by != user_id` 回傳 **403 Forbidden** | **DISMISSED (SECURE)** |
| **SEC-SET-02** | `POST /api/trips/{trip_id}/leave` | 孤兒資源狀態污染 | 行程建立者若退出行程，將使行程失去擁有者形成孤兒資料 | `test_trip_settings_sentinel.py:test_sentinel_owner_cannot_leave_must_delete` 驗證後端阻斷建立者退出，回傳 **400 Bad Request** 要求其走刪除流程 | **DISMISSED (SECURE)** |
| **SEC-SET-03** | `PATCH /api/trips/{trip_id}/title` | 越權篡改 | 非成員惡意修改行程標題 | `test_trip_settings_sentinel.py:test_sentinel_update_title_non_member_blocked` 驗證後端查詢 `trip_members`，非成員回傳 **403 Forbidden** | **DISMISSED (SECURE)** |
| **SEC-SET-04** | `TripSettingsView.tsx` | XSS / 偽協議注入 | 封面 URL 參數可能傳入 `javascript:` 或惡意 HTML 注入燈箱 | `trip-settings-sentinel.test.ts:TC-1` 驗證前端正規化切斷偽協議，強制限定 `https?://` 安全通訊協定 | **DISMISSED (SECURE)** |

---

## 3. 實作前防禦加固規範 (Defense Invariants)

1. **Popstate 記憶體洩漏防禦**: `useEffect` 註冊 `window.addEventListener('popstate')` 時，必須在 return cleanup 函式中精確解綁，防止快速切換子頁面時閉包堆疊。
2. **標題前後空白清洗**: 在送出 `updateTitle` 前，強制以 `rawTitle.trim()` 驗證；若長度為 0 則不發起網路請求，防止覆蓋為空標題。
3. **首頁快取雙向連動**: 設定頁完成封面或標題變更後，同步調用 `reloadTripDetail()` 與 `reloadTrips()`，保證首頁卡片與設定頁狀態無時差同步。
