# 🛡️ Security Sentinel 對抗式審查報告 (2026-10-07)

> **審查模式**: Physical Multi-Agent Sandboxed Audit (`runner.py` via `agy.exe -p`)  
> **核心標的**: `frontend/components/itinerary/ActivityEditModal.tsx`  
> **審查範圍**: 狀態並發競態 (Race Conditions)、Stale Closure 覆寫、Re-render 震盪、URL 偽協議注入  
> **Ledger 狀態**: `docs/security/security-coverage-ledger.json` 已原子更新 (Target 18/18)

---

## 一、審查摘要 (Executive Summary)

| 指標 | 數值 | 說明 |
| :--- | :--- | :--- |
| **總測試假說 (Hypotheses Evaluated)** | 3 | 針對表單異步解析、狀態突變防抖、輸入協議安全性 |
| **證實漏洞 (Confirmed Vulnerabilities)** | 1 | 異步地址/網址解析陳舊閉包資料覆寫漏洞 (Stale Closure Data Clobbering) |
| **排除假說 (Dismissed)** | 1 | `isManualCoords` 旗標狀態鎖定機制已有效防範無限重繪 |
| **防禦狀態 (Overall Status)** | `PENDING_PATCH` | 需於 Inset Grouped 重構實作中掛載 Mantis 防禦補丁 |

---

## 二、證實漏洞詳情 (Confirmed Vulnerability: SEC-ACT-001)

### 2.1 漏洞機理分析
- **目標組件**: `frontend/components/itinerary/ActivityEditModal.tsx`
- **弱點位置**: `handleResolveAddress` 與 `handleResolveLink`
- **機理說明**:
  在發起非同步地理編碼或 Google Maps 短網址解析時，函式內部直接捕獲了當下元件的 `editItem` 閉包快照。當使用者在網路請求尚在飛行中（Inflight）時：
  1. 繼續在表單輸入名稱 (`place`)、筆記 (`desc`) 或費用 (`cost`)；或
  2. 快速切換編輯項目 (`editItem` 由外部變更為不同 ID 的活動)；
  
  一旦網路請求返回，`setEditItem({ ...editItem, ... })` 會將已過期的舊快照直接展開覆蓋，**導致使用者最新輸入的文字被瞬間洗掉**，或將舊活動的座標誤寫入新活動中。

### 2.2 獨立沙盒證偽驗證 (In-Memory PoC)
沙盒驗證代理人生成的 In-Memory 測試腳本如下：

```python
import asyncio
import pytest

class MockActivityEditModal:
    def __init__(self, edit_item=None):
        self.edit_item = edit_item
        self.is_resolving_address = False

    async def handle_resolve_address(self, geocode_api_resolve):
        if not self.edit_item or not self.edit_item.get("address"):
            return
        # Stale closure over current edit_item snapshot
        captured_item = dict(self.edit_item)
        self.is_resolving_address = True
        try:
            data = await geocode_api_resolve(captured_item["address"])
            if data.get("success") and data.get("lat") and data.get("lng"):
                current_place = captured_item.get("place", "").strip()
                new_place = current_place if current_place else (data.get("name") or data.get("address") or "")
                # Overwrites active item with stale captured_item
                self.edit_item = {
                    **captured_item,
                    "lat": data["lat"],
                    "lng": data["lng"],
                    "place": new_place,
                    "isManualCoords": True
                }
        finally:
            self.is_resolving_address = False

@pytest.mark.asyncio
async def test_stale_closure_race_condition_overwrites_item():
    modal = MockActivityEditModal(edit_item={"id": "item-1", "address": "Tokyo Tower", "place": "Tokyo Tower", "notes": "Original"})

    async def mock_delayed_resolve(address):
        await asyncio.sleep(0.05)
        return {"success": True, "lat": 35.6586, "lng": 139.7454, "name": "Tokyo Tower"}

    # Trigger async resolution on item-1
    task = asyncio.create_task(modal.handle_resolve_address(mock_delayed_resolve))

    # User switches to item-2 while resolution is inflight
    await asyncio.sleep(0.01)
    modal.edit_item = {"id": "item-2", "address": "Shibuya Sky", "place": "Shibuya Sky", "notes": "Switched item"}

    await task

    # Demonstrates defect: item-2 is overwritten by stale item-1 state
    assert modal.edit_item["id"] == "item-1", "Defect confirmed: stale closure clobbered switched item"
```

---

## 三、Mantis 防禦補丁設計 (Mantis Candidate Patch)

為徹底根除此並發競態，必須採用 **雙重 Ref 防衛機制 (Dual Ref Guard)**：
1. **`activeItemIdRef`**: 追蹤當前啟用的活動 ID，解析完成後比對若 ID 不符則直接中斷提交。
2. **`editItemRef`**: 即時同步最新 `editItem` 物件指標，確保狀態展開時使用最新的使用者輸入，絕不洗掉已編輯欄位。

```tsx
// 🛡️ Mantis 防禦機制
const editItemRef = useRef(editItem)
editItemRef.current = editItem
const activeItemIdRef = useRef<string | undefined>(editItem?.id)

useEffect(() => {
    activeItemIdRef.current = editItem?.id
}, [editItem?.id])

// 在 handleResolveAddress 與 handleResolveLink 中：
const targetId = editItem.id
const data = await geocodeApi.resolveAddress(...)

// 守門檢查：若已切換項目或 Modal 已關閉，靜默放棄
if (activeItemIdRef.current !== targetId) return

const latest = editItemRef.current || editItem
setEditItem({
    ...latest,
    lat: data.lat,
    lng: data.lng,
    place: latest.place?.trim() ? latest.place : (data.name || data.address || ""),
    isManualCoords: true
})
```

---

## 四、安全門禁總結 (Handover Status)

- **審查結論**: 漏洞已精確定位並形成可實作之防禦修復方案。
- **下一階段**: 交付全端工程師 (`@dev`) 在執行 iOS Inset Grouped 重構時同步掛載此防禦補丁，並由品質工程師 (`@qa`) 執行靜態驗證與回歸測試。
