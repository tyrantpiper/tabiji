# 🛡️ Security Sentinel 對抗性沙盒審計報告

> **審計主題**: POI 景點口袋庫 D1 單一真理源收斂與記憶體黑洞根除  
> **執行模式**: `agy.exe -p --sandbox` 物理隔離子代理人 (Zero Prompt Contamination)  
> **審計日期**: 2026-10-21  
> **審計結論**: 1 項漏洞實體證偽 (CONFIRMED)、3 項邊界防禦與回歸驗證通過 (DISMISSED)

---

## 1. 執行總結 (Executive Summary)

| 目標組件 | 審查維度 | 沙盒判定 | 判定原因 |
| :--- | :--- | :---: | :--- |
| `backend/routers/poi.py:obsolete_crud_memory_leak` | 狀態持久化與記憶體洩漏 | **VULNERABLE (CONFIRMED)** | `save_user_poi` / `delete_user_poi` 以 `except: pass` 吞蔽 Supabase 404，資料沉澱於進程記憶體，容器重啟即滅。 |
| `frontend/app/api/poi/[...path]/route.ts:transparent_proxy_robustness` | 反向代理健壯性與 Header 注入 | **DISMISSED** | 現行代碼為本地 Mock，尚未實作代理；但候選補丁必須前置防禦 Host 覆寫與 GET Body 隔離。 |
| `cloudflare/edge-shield/worker.js:cors_fail_closed_boundary` | 邊緣容錯與 CORS 邊界 | **DISMISSED** | 現行邊緣代碼直接 pass-through 至後端；候選 Fail-Closed 補丁已預先補齊完整 CORS 標頭。 |
| `backend/tests/test_poi_link_security_sentinel.py:import_breakage` | 測試解耦與回歸阻斷 | **DISMISSED** | 刪除舊端點導致測試 ImportError 屬預期回歸，需在實作前完成測試目標轉移。 |

---

## 2. 證偽漏洞詳情與 In-Memory PoC

### 漏洞 ID: `backend/routers/poi.py:obsolete_crud_memory_leak`
- **威脅路徑**: `authenticated_to_internal` ➔ 假持久化與靜默資料遺失
- **根因分析**:
  後端第 491～523 行的 `save_user_poi` 與 `delete_user_poi` 嘗試對 Supabase `poi_items` 進行 upsert，但資料庫中無此表。代碼使用 bare `except Exception: pass` 吞掉例外，直接存入 Python 全域變數 `POI_POOL_STORE` 並回傳 200 OK。Cloud Run 容器一旦重啟或水平擴展，使用者的景點資料將徹底消失。
- **In-Memory PoC 驗證碼**:
```python
import pytest
from unittest.mock import MagicMock

POI_POOL_STORE = {}

async def save_user_poi(user_id: str, item: dict, supabase=None):
    if supabase:
        try:
            supabase.table("poi_items").upsert(item).execute()
        except Exception:
            pass
    current = POI_POOL_STORE.setdefault(user_id, [])
    current.insert(0, item)

@pytest.mark.asyncio
async def test_silent_data_loss_on_container_restart():
    global POI_POOL_STORE
    POI_POOL_STORE.clear()
    user_id = "user-123"
    poi_item = {"id": "poi-1", "title": "Tokyo Tower"}

    # 模擬 Supabase 報錯 (404 / 連線失敗)
    mock_supabase_failing = MagicMock()
    mock_supabase_failing.table.return_value.upsert.return_value.execute.side_effect = Exception("404 Table Not Found")

    # 寫入表面成功，實質僅存在於記憶體
    await save_user_poi(user_id, poi_item, supabase=mock_supabase_failing)
    assert POI_POOL_STORE[user_id][0]["id"] == "poi-1"

    # 模擬 Cloud Run 容器重啟
    POI_POOL_STORE.clear()

    # 資料歸零，確認發生靜默丟失
    assert user_id not in POI_POOL_STORE
```

---

## 3. 候選補丁與精準區塊替換規範 (Mantis Candidate Patches)

### 補丁 1：`backend/tests/test_poi_link_security_sentinel.py` (前置解耦)
- **目標**: 解除對即將刪除的 `routers.poi:import_poi_link` 的依賴，直接測試安全核心 [`is_safe_url`](file:///d:/Project/tabiji/travel-pwa/backend/utils/url_safety.py)。
- **區塊替換**:
```python
<<<<
@pytest.mark.asyncio
async def test_poi_import_link_ssrf_rejection():
    from unittest.mock import MagicMock
    from fastapi import Request, HTTPException
    from routers.poi import import_poi_link, POIImportLinkRequest

    mock_req = MagicMock(spec=Request)
    
    # 1. Test Loopback SSRF blocked
    payload_loopback = POIImportLinkRequest(url="http://127.0.0.1:8008/api/trips")
    with pytest.raises(HTTPException) as exc_info:
        await import_poi_link(fastapi_req=mock_req, req=payload_loopback, user_id="test-user", supabase=None)
    assert exc_info.value.status_code == 400
    assert "SSRF" in exc_info.value.detail

    # 2. Test Cloud Metadata SSRF blocked
    payload_metadata = POIImportLinkRequest(url="http://169.254.169.254/latest/meta-data/")
    with pytest.raises(HTTPException) as exc_info:
        await import_poi_link(fastapi_req=mock_req, req=payload_metadata, user_id="test-user", supabase=None)
    assert exc_info.value.status_code == 400
    assert "SSRF" in exc_info.value.detail
====
def test_poi_link_ssrf_security_guard():
    # Direct validation of SSRF defense without reliance on obsolete router
    assert not is_safe_url("http://127.0.0.1:8008/api/trips")
    assert not is_safe_url("http://169.254.169.254/latest/meta-data/")
    assert not is_safe_url("http://metadata.google.internal/computeMetadata/v1/")
>>>>
```

### 補丁 2：`backend/routers/poi.py` (根除記憶體黑洞與無效 CRUD)
- **目標**: 刪除第 480～845 行的舊 CRUD 代碼，消滅 `POI_POOL_STORE` 與無效 Supabase 呼叫。

### 補丁 3：`frontend/app/api/poi/[...path]/route.ts` (硬核級生產透明代理)
- **目標**: 替換 374 行的本地 Mock，改為具備「Host 覆寫清洗」、「GET/HEAD Body 隔離防護」、「Promise Params 異步解析」與「Query String 完好保持」的生產級反向代理。

### 補丁 4：`cloudflare/edge-shield/worker.js` (邊緣 503 CORS 閉環)
- **目標**: 移除向 Cloud Run 的無效假降級，於 D1 異常時回傳具備完整 CORS 標頭的 `503 Service Unavailable`，無縫激發前端 PWA 離線同步佇列。

---

## 4. 人類主權把關 (Human Gate Handover)

根據 L0 憲法與專案規範：
- `@security` (Sentinel) 僅負責證偽漏洞與提出防禦型補丁候選。
- **嚴禁未經人類確認擅自修改代碼**。
- 請確認是否同意依此補丁清單，由 `@dev` 進行最小侵入性精確替換並執行靜態 `tsc` 與動態 `pytest` 雙重守門。
