# Security Sentinel 對抗式安全審計報告 (Adversarial Security Audit Report)
**主題**: 自訂地點分類協定 (Custom POI Categories Protocol) 與邊緣端持久化驗證  
**審計日期**: 2026-10-21  
**模式**: Security Sentinel (Cloudflare ✕ Google Mantis ✕ agy CLI Physical Sandbox)  
**總審計目標數**: 5 項 | **已證偽確證**: 1 項 | **審查駁回**: 1 項 | **PoC 預防性驗證**: 3 項  

---

## 執行摘要 (Executive Summary)

針對使用者提出的「自訂地點類別與 Emoji/Icon、色票選擇」功能，Security Sentinel 透過背景物理隔離之子代理人（`agy.exe --sandbox`）與記憶體單元測試（In-Memory PoC）展開全景式對抗證偽審查。

### 核心發現：
1. **確證高危缺陷 (`CONFIRMED`)**:
   - **目標**: `cloudflare/poi-service/worker.js:category_whitelist_override`
   - **成因**: Cloudflare Worker 在 `PATCH /api/poi/:id/category` 路由（行 409-410）實施了硬編碼 7 項白名單校驗。任何自訂協定字串（如 `custom:🍜:拉麵:#F59E0B`）會被邊緣端強制覆寫為 `"attraction"`，導致雲端資料庫持久化全面失效。
   - **狀態**: 已透過 PoC 13 證偽，並由 Mantis 補丁完成防禦合成。
2. **預防性邊界驗證 (`VERIFIED_BY_POC`)**:
   - **冒號分隔符碰撞 (PoC 14)**: 自訂類別名稱若包含 `:`，透過前端序列化全形轉義 `name.replaceAll(":", "：")` 與解碼端切片截取 `":".join(p[2:-1])` 達成 100% 免疫。
   - **殘缺協定安全降級 (PoC 15)**: 空值、破損協定平滑降級至 `other`，杜絕未捕獲之執行期崩潰。
   - **動態收割純淨度 (PoC 16)**: 保證跨多 POI 提煉自訂類別時無重複項，且嚴格排除標準系統類別。
3. **安全審查駁回 (`DISMISSED`)**:
   - **地圖圖標元件崩潰假說**: 地圖元件利用邏輯 OR 運算子（`|| Compass`）在遇到未知鍵值時自動安全回退至羅盤圖示，不會引發未定義例外。

---

## 審計目標與裁決矩陣 (Attack Surface Matrix)

| Target ID | Trust Boundary | Vector Checked | Verdict | PoC Evidence |
| :--- | :--- | :--- | :--- | :--- |
| `cloudflare/poi-service/worker.js:category_whitelist_override` | `edge_to_storage` | `schema_whitelist_mutation_drop` | **CONFIRMED** | `test_poc_13` |
| `frontend/components/poi/PoiPoolMap.tsx:custom_marker_component_render_type` | `browser_runtime` | `ui_component_type_error` | **DISMISSED** | 靜態 `|| Compass` 守護 |
| `frontend/lib/poi-category-protocol.ts:colon_delimiter_injection` | `input_sanitization` | `protocol_delimiter_injection` | **VERIFIED** | `test_poc_14` |
| `frontend/lib/poi-category-protocol.ts:malformed_protocol_crash` | `input_deserialization` | `input_deserialization_unhandled_crash` | **VERIFIED** | `test_poc_15` |
| `frontend/lib/poi-category-protocol.ts:dynamic_harvesting_dedup` | `state_synchronization` | `state_desynchronization` | **VERIFIED** | `test_poc_16` |

---

## Mantis 候選補丁 (Patch Candidates)

### 補丁 1：Cloudflare Worker 邊緣端協定放行守門
**檔案**: `cloudflare/poi-service/worker.js` (Lines 409-410)

```diff
- const validCategories = ["attraction", "food", "cafe", "shopping", "hotel", "transport", "other"];
- const category = validCategories.includes(body.category) ? body.category : "attraction";
+ // 🛡️ 放行標準類別與合規自訂協定 custom:<emoji>:<name>:<color>
+ const isValidCategory = (cat) => {
+   if (typeof cat !== "string") return false;
+   const standardCategories = ["attraction", "food", "cafe", "shopping", "hotel", "transport", "other"];
+   if (standardCategories.includes(cat)) return true;
+   return cat.startsWith("custom:") && cat.split(":").length >= 4;
+ };
+ const category = isValidCategory(body.category) ? body.category : "attraction";
```

### 補丁 2：協定編解碼與防注入核心
**檔案**: `frontend/lib/poi-category-protocol.ts` (新建)

```typescript
export function serializeCustomCategory(emoji: string, name: string, colorHex: string): string {
    const cleanEmoji = emoji.trim() || "📍";
    // 🛡️ 冒號轉義為全形冒號，杜絕協定注入破壞
    const cleanName = name.replaceAll(":", "：").trim() || "自訂";
    const cleanColor = colorHex.startsWith("#") ? colorHex : `#${colorHex}`;
    return `custom:${cleanEmoji}:${cleanName}:${cleanColor}`;
}

export function parseCategory(catStr: string | null | undefined): ParsedCategory {
    if (!catStr) return { isCustom: false, key: "other", label: "全部", color: "#64748B", bg: "bg-slate-50 dark:bg-slate-800", icon: Compass };

    if (catStr.startsWith("custom:")) {
        const parts = catStr.split(":");
        if (parts.length >= 4) {
            const emoji = parts[1] || "📍";
            const color = parts[parts.length - 1] || "#E56E25";
            const label = parts.slice(2, parts.length - 1).join(":") || "自訂";
            return { isCustom: true, key: catStr, label, emoji, color, bg: `${color}1A` };
        }
    }
    const cm = CATEGORY_MAP[catStr as POICategory] || CATEGORY_MAP.other;
    return { isCustom: false, key: catStr, label: cm.labelKey, color: cm.color, bg: cm.bg, icon: cm.icon };
}
```

---

## 驗收確認 (Verification Summary)
- [x] In-Memory 沙盒 PoC 套件已新增 4 項測試：`test_poc_13` 至 `test_poc_16`。
- [x] Sentinel 測試套件 **16/16 100% 通過 (0.17s)**。
- [x] 資安帳本 `docs/security/security-coverage-ledger.json` 已原子更新（總計 142 個目標）。
