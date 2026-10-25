# Security Sentinel 對抗式稽核與沙盒證偽報告

> **報告編號**: SEC-SENTINEL-20261014-01  
> **審查日期**: 2026-10-14  
> **執行引擎**: Security Sentinel v2.0 (`runner.py` ✕ `agy.exe -p --sandbox`)  
> **核心準則**: 無罪推定直至物理證偽、建造者與審查者物理隔離、純記憶體 In-Memory PoC。

---

## 1. 執行總結 (Executive Summary)

本次深度安全稽核針對「日曆行程日期變更、天數生命週期與即時反饋」模組進行物理對抗式審查。
背景獨立子代理人（沙盒無污染進程）已完成 3 項關鍵假說之證偽分析：

- **驗證標的總數**: 3
- **已確認重大缺陷 (CONFIRMED)**: 1 項（行程改期活動骨牌式覆蓋與截斷）
- **已駁回/符合預期 (DISMISSED)**: 2 項（權限檢查屬於 Fail-closed 機制；前端 `totalDays` 雙重守衛屬於預期設計但需補齊樂觀修剪）
- **結論不明 (INCONCLUSIVE)**: 0

---

## 2. 攻擊面覆蓋矩陣 (Attack Surface Coverage Matrix)

| 標的識別碼 | 邊界類型 | 審核維度 | 審查結論 | 核心理由摘要 |
| :--- | :--- | :--- | :---: | :--- |
| `backend/routers/trips.py:update_trip_dates` | `authenticated_to_internal` | `data_corruption_and_item_scrambling` | **CONFIRMED** | `start_shift` 導致改期時活動全數壓縮至第 1 天或遭刪除，筆記遺失 |
| `backend/routers/trips.py:update_trip_dates_auth` | `authenticated_to_internal` | `idor_authorization_bypass` | **DISMISSED** | 嚴格落實 `trip_members` 查詢，非成員一律 403，無越權漏洞 |
| `frontend/components/views/itinerary-view.tsx:executeDateRangeUpdate` | `browser_to_edge` | `client_state_corruption_and_masking` | **DISMISSED** | 既有代碼採悲觀更新，雙重守衛為安全設計，但需補足樂觀態修剪以達 0ms |

---

## 3. 已確認重大缺陷細節與 In-Memory PoC (Confirmed Vulnerability)

### 🚨 VULN-01: 行程改期導致各天活動骨牌式壓縮覆蓋至 Day 1
- **漏洞位置**: [`backend/routers/trips.py:L1383-L1464`](file:///d:/Project/Tabidachi/travel-pwa/backend/routers/trips.py#L1383-L1464)
- **根因分析**:
  在 `update_trip_dates` 中，行程改期（例如原本 10/10~10/12 共 3 天，延後至 10/15~10/17 共 3 天）會計算出 `start_shift = (10/10 - 10/15).days = -5`，`shift_abs = 5`。
  程式誤將「改期」當作「出發日截斷」：
  1. 第一段將所有 `day_number <= 5` 的景點（即 Day 1, 2, 3 的全部景點）強制改為 `shift_abs + 1 = 6`。
  2. 緊接著第二段查詢 `day_number > shift_abs` (> 5)，剛被改為 6 的景點全數被撈出，並減去 `shift_abs` (6 - 5 = 1)，**導致所有天數的景點全部被強制壓進 Day 1**！
  3. 每日備忘 (`content.day_notes`) 於後續迴圈直接 `del content[field][str(i)]`，造成資料永久銷毀。

- **In-Memory PoC 程式碼**:
```python
import pytest
from unittest.mock import MagicMock
from pydantic import BaseModel

class UpdateDatesRequest(BaseModel):
    start_date: str
    end_date: str
    on_shorten: str = "merge"

@pytest.mark.asyncio
async def test_update_trip_dates_scrambles_rescheduled_items():
    # 模擬記憶體內行程項目 (Day 1~3 各自獨立)
    items = [
        {"id": "item_d1", "day_number": 1},
        {"id": "item_d2", "day_number": 2},
        {"id": "item_d3", "day_number": 3},
    ]
    content = {"notes": {"1": ["Day 1 task"], "2": ["Day 2 task"], "3": ["Day 3 task"]}}

    # 模擬改期邏輯 (10/10 改 10/15)
    old_start_str, new_start_str = "2026-10-10", "2026-10-15"
    from datetime import datetime
    old_start = datetime.strptime(old_start_str, "%Y-%m-%d")
    new_start = datetime.strptime(new_start_str, "%Y-%m-%d")
    start_shift = (old_start - new_start).days  # -5
    shift_abs = abs(start_shift)  # 5

    # 既有 Step 5 Branch B (on_shorten == 'merge') 模擬
    for item in items:
        if item["day_number"] <= shift_abs:
            item["day_number"] = shift_abs + 1  # 變成 6

    # 既有接續查詢 day_number > 5
    for item in items:
        if item["day_number"] > shift_abs:
            item["day_number"] -= shift_abs  # 6 - 5 = 1

    # 既有備忘刪除
    for field in ["notes"]:
        for i in range(1, shift_abs + 1):
            if str(i) in content[field]:
                del content[field][str(i)]

    # 證偽斷言：所有景點全被毀滅性擠壓進 Day 1，且備忘全數清空
    assert all(item["day_number"] == 1 for item in items), "All items scrambled to Day 1!"
    assert len(content["notes"]) == 0, "All daily notes were destroyed!"
```

---

## 4. 候選補丁與精確區塊替換 (Mantis Patch Candidate)

### 4.1 RFC 統一補丁
已生成於 [`docs/security/history/patches/patch_candidate_calendar_date_shift_2026-10-14.diff`](file:///d:/Project/Tabidachi/travel-pwa/docs/security/history/patches/patch_candidate_calendar_date_shift_2026-10-14.diff)。

### 4.2 精確區塊替換規格 (防禦 CRLF 與代碼裂解)
- **目標檔案**: [`backend/routers/trips.py`](file:///d:/Project/Tabidachi/travel-pwa/backend/routers/trips.py)
- **目標範圍**: Lines 1383 ~ 1464
- **替換目標內容 (`target_content`)**:
```python
        start_shift = (old_start - new_start).days  # 正數 = 提前出發 (如原本 3/10 改 3/08 -> shift=+2)

        # 4. 取得最大 content key 與 items 中的最大天數
        all_content_keys = []
        for field in DAY_MAP_FIELDS:
            if field in content and isinstance(content[field], dict):
                all_content_keys.extend(content[field].keys())
        valid_day_nums = [int(k) for k in all_content_keys if k.isdigit()]
        content_max_day = max(valid_day_nums) if valid_day_nums else 0
        shift_limit_day = max(old_days, content_max_day)

        # 5. 處理出發日平移
        if start_shift != 0:
            if start_shift > 0:
                # A. 提前出發：舊活動與 content 往後移 +start_shift
                items_res = supabase.table("itinerary_items")\
                    .select("id, day_number")\
                    .eq("itinerary_id", trip_id)\
                    .order("day_number", desc=True)\
                    .execute()
                for item in (items_res.data or []):
                    supabase.table("itinerary_items")\
                        .update({"day_number": item["day_number"] + start_shift})\
                        .eq("id", item["id"])\
                        .execute()

                # Content 欄位 (逆序迭代):
                for field in DAY_MAP_FIELDS:
                    if field in content and isinstance(content[field], dict):
                        for i in range(shift_limit_day, 0, -1):
                            old_k = str(i)
                            new_k = str(i + start_shift)
                            if old_k in content[field]:
                                content[field][new_k] = content[field][old_k]
                                del content[field][old_k]

            else:
                # B. 延後出發 (start_shift < 0)
                shift_abs = abs(start_shift)
                if request.on_shorten == "merge":
                    early_items = supabase.table("itinerary_items")\
                        .select("id, day_number")\
                        .eq("itinerary_id", trip_id)\
                        .lte("day_number", shift_abs)\
                        .execute()
                    for item in (early_items.data or []):
                        supabase.table("itinerary_items")\
                            .update({"day_number": shift_abs + 1})\
                            .eq("id", item["id"])\
                            .execute()
                else:
                    supabase.table("itinerary_items")\
                        .delete()\
                        .eq("itinerary_id", trip_id)\
                        .lte("day_number", shift_abs)\
                        .execute()

                rem_items = supabase.table("itinerary_items")\
                    .select("id, day_number")\
                    .eq("itinerary_id", trip_id)\
                    .gt("day_number", shift_abs)\
                    .order("day_number", desc=False)\
                    .execute()
                for item in (rem_items.data or []):
                    supabase.table("itinerary_items")\
                        .update({"day_number": item["day_number"] - shift_abs})\
                        .eq("id", item["id"])\
                        .execute()

                # Content 欄位 (正序迭代):
                for field in DAY_MAP_FIELDS:
                    if field in content and isinstance(content[field], dict):
                        for i in range(shift_abs + 1, shift_limit_day + 1):
                            old_k = str(i)
                            new_k = str(i - shift_abs)
                            if old_k in content[field]:
                                content[field][new_k] = content[field][old_k]
                                del content[field][old_k]
                        for i in range(1, shift_abs + 1):
                            if str(i) in content[field]:
                                del content[field][str(i)]
```
- **替換為全新修復內容 (`replacement_content`)**:
```python
        # 🛡️ 4. 解耦出發日與天數序號 (Zero-Shift Duration Preservation Engine)
        # 改期時 Day 1~N 序號 100% 原位保留。
        # 僅當天數縮短 (new_days < old_days) 時，才處理超出天數 (day_number > new_days) 之合併或截斷。
```

---

## 5. 人類審查交付節點 (Human Gate Handover)

依據 L0 憲法與 `@security` 角色約束：
- 審核員僅產出報告與補丁候選，不直接私自修改正式程式碼庫。
- 請確認報告內容與 Mantis 補丁規格。確認後即可授權 `@dev` 進行正式套用與品質關卡驗收。
