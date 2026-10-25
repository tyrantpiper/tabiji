# 🛡️ Security Sentinel Audit Report: Knowledge Extraction & Spatial Topology Hardening

> **Report ID**: `SEC-SENTINEL-2026-10-21-TOPOLOGY-KNOWLEDGE`  
> **Audit Framework**: Cloudflare 6-Phase Ledger ✕ Google Mantis Patch Synthesis ✕ agy CLI Sandbox  
> **Timestamp**: 2026-10-21T14:20:00Z  
> **Auditor**: Security Sentinel Subagent (`@security`)  
> **Verdict**: 3 DISMISSED HYPOTHESES (Option A: Closed-Set Call Site Invariance)  

---

## 1. Executive Summary

| Metric | Value |
| :--- | :--- |
| **Total Candidates Audited** | 3 |
| **Confirmed Vulnerabilities** | 0 (Human Gate selected Option A: Closed-Set Invariance) |
| **Dismissed Hypotheses** | 3 (`spatial-tab-topology.ts`, `link_resolver.py`, `poi-category-protocol.ts`) |
| **Ledger Conservation Status** | 🟢 Verified 157 Targets (16 Remediated, 17 Verified, 124 Dismissed) |
| **Maker-Checker Isolation** | 100% Physical Execution via `runner.py` with `agy.exe -p --sandbox` |

---

## 2. Attack Surface Coverage & Empirical Findings

### 2.1 [DISMISSED] `frontend/lib/spatial-tab-topology.ts:unregistered_tab_direction_inversion`
* **Trust Boundary**: `browser_runtime`
* **Vectors Checked**: `unregistered_tab_direction_inversion`, `spatial_parity_asymmetry`
* **Status**: `DISMISSED` (Option A: Human Gate Decision)
* **Empirical Analysis**:
  * 原始實作使用空值合併運算子：`const targetIdx = TAB_INDICES[targetTab] ?? 0` 與 `const currentIdx = TAB_INDICES[currentActiveTab] ?? 0`。
  * 當未註冊分頁（如 modal、未列入常駐導航的深層頁面）與 `itinerary` (Index 0) 進行轉場時，`targetTab !== currentActiveTab` 通過前置檢查，但 `targetIdx` 與 `currentIdx` 皆為 0。
  * `targetIdx > currentIdx` (`0 > 0`) 評估為 `false`，導致函數在雙向轉場時皆回傳 `-MOTION_CONFIG.offsetPx` (-28px)。
  * **破壞空間反對稱性公理**：數學上空間視差必須滿足 $\text{offset}(A \to B) = -\text{offset}(B \to A)$。雙向恆為 -28px 導致反向位移或非預期晃動。

```python
# In-Memory Sentinel Validation PoC (Empirically Proven)
def calculate_tab_offset(target_tab: str, current_active_tab: str, intent: str = "dock", is_reduced_motion: bool = False) -> int:
    tab_indices = {"itinerary": 0, "info": 1, "tools": 2, "profile": 3}
    offset_px = 28
    if is_reduced_motion or intent == "instant" or target_tab == current_active_tab:
        return 0
    target_idx = tab_indices.get(target_tab, 0)
    current_idx = tab_indices.get(current_active_tab, 0)
    return offset_px if target_idx > current_idx else -offset_px

def test_unregistered_tab_direction_inversion():
    forward = calculate_tab_offset(target_tab="unknown", current_active_tab="itinerary")
    backward = calculate_tab_offset(target_tab="itinerary", current_active_tab="unknown")
    assert forward == -28
    assert backward == -28  # 🚨 Flaw: both directions return -28px!
    assert forward != -backward
```

---

### 2.2 [DISMISSED] `backend/services/link_resolver.py:rpc_xssi_non_json_html_resilience`
* **Trust Boundary**: `edge_to_upstream`
* **Hypothesis**: Google Maps RPC 回傳 HTML 429 或驗證碼挑戰頁面時，正則脫殼後 `json.loads` 會引發未處理例外。
* **Sentinel 審核結論**: `DISMISSED`。`parse_google_place_rpc_payload`（L140-184）全體包覆於頂層 `try...except Exception:` 區塊中，遇 HTML 字串拋出之 `JSONDecodeError` 會被靜默攔截並安全回傳 `None`，符合契約守則。

---

### 2.3 [DISMISSED] `frontend/lib/poi-category-protocol.ts:category_harvesting_display_name_collision`
* **Trust Boundary**: `state_synchronization`
* **Hypothesis**: 收割自訂分類時純以協定字串去重，同名不同色會造成篩選按鈕重複。
* **Sentinel 審核結論**: `DISMISSED`。自訂類別必須以完整協定字串（`custom:<emoji>:<name>:<colorHex>`）作為 Key。若依標籤收斂，將導致不同 Emoji 或顏色的分類丟失，進而破壞 POI 篩選閉環。UI 標籤已配備顏色圓點與 Emoji 進行視覺消歧義。

---

## 3. Mantis Patch Candidate (候選修正方案)

### 3.1 `frontend/lib/spatial-tab-topology.ts`
嚴格校驗分頁是否登記於 `TAB_INDICES`；任一分頁未登記或兩者索引相同時，恆定回傳 `0`（原地切換，不產生偽位移）：

```diff
--- a/frontend/lib/spatial-tab-topology.ts
+++ b/frontend/lib/spatial-tab-topology.ts
@@ -40,9 +40,15 @@ export function calculateTabOffset(
     intent: TabTransitionIntent = "dock",
     isReducedMotion: boolean = false
 ): number {
-    if (isReducedMotion || intent === "instant" || targetTab === currentActiveTab) {
+    if (
+        isReducedMotion ||
+        intent === "instant" ||
+        targetTab === currentActiveTab ||
+        !(targetTab in TAB_INDICES) ||
+        !(currentActiveTab in TAB_INDICES)
+    ) {
         return 0
     }
-    const targetIdx = TAB_INDICES[targetTab] ?? 0
-    const currentIdx = TAB_INDICES[currentActiveTab] ?? 0
+    const targetIdx = TAB_INDICES[targetTab]
+    const currentIdx = TAB_INDICES[currentActiveTab]
     return targetIdx > currentIdx ? MOTION_CONFIG.offsetPx : -MOTION_CONFIG.offsetPx
 }
```

---

## 4. 領域記憶庫固化方案 (Auto Dream 2.0 Invariants)

在人類審核同意後，執行以下變更：
1. **垃圾回收 (GC)**：清理 [backend_concurrency.md:L18](file:///d:/Project/tabiji/travel-pwa/.agents/domains/backend_concurrency.md#L18) 之重複條目。
2. **寫入領域知識庫**：
   * `backend_concurrency.md` ➔ 寫入「兩階段意圖路由法則」、「Google Maps Web RPC 脫殼與 XSSI 容錯防護法則」、「邊緣 D1 與核心 Supabase 異構雙庫權責劃分法則」。
   * `ios_ui.md` ➔ 寫入「純函數空間索引拓撲與零漂移視差法則」（包含未登記分頁歸零安全防衛）。
   * `state_cache.md` ➔ 寫入「記憶體動態類別收割與零註冊表解耦法則」。

---

## 5. Human Gate Handover
* 根據 L0 憲法第一條「人類主權原則」，`@security` 已在物理沙盒完成全部證偽與驗收。
* 請檢閱上述 findings 與 candidate patch，確認無誤後即可下達實作指令交由 `@dev` 執行。
