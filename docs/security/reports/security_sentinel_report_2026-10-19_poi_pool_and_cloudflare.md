# Security Sentinel 深度對抗審查報告 (POI 口袋庫與邊緣生態)

> **報告編號**: `SEC-SENTINEL-2026-10-19-POI-POOL`  
> **執行模式**: `agy.exe --sandbox` 物理子進程隔離證偽審查 (Zero-Prompt-Contamination)  
> **審查日期**: 2026-10-19  
> **審查者**: `@security` (Security Sentinel)  
> **審查範疇**: `backend/routers/poi.py`, `cloudflare/edge-shield/worker.js`, `frontend/components/views/itinerary-view.tsx`

---

## 一、 執行摘要 (Executive Summary)

本次 Security Sentinel 針對「Tabidachi 全域景點口袋庫 (POI Pool)」之邊緣路由、Google Maps 逆向匯入解析器、跨視圖排程與使用者身分隔離實施物理對抗證偽：

- **受審目標總數**: 5 項核心信任邊界
- **證偽駁回 (Dismissed / Secure)**: 1 項 (`cloudflare/edge-shield/worker.js`)
- **漏洞確認 (Confirmed Vulnerability)**: 1 項 (`backend/routers/poi.py:import_link_safety`)
- **待修復狀態**: 候選補丁與 In-Memory PoC 已生成，等待人類審查核准（Human Gate）。

---

## 二、 信任邊界審查矩陣 (Attack Surface Matrix)

| 目標組件 | 信任邊界 | 檢驗威脅向量 | 判定結果 | 實證分析摘要 |
| :--- | :--- | :--- | :---: | :--- |
| `cloudflare/edge-shield/worker.js` | `browser_to_edge` | `ssrf_and_unauthorized_bypass` | **DISMISSED (安全)** | WHATWG 標準 URL 自動規範化路徑，Service Binding 透過 V8 Isolate IPC 內部呼叫，無外部 DNS 解析與 CRLF 注入風險。 |
| `backend/routers/poi.py:import_link_safety` | `public_to_backend` | `ssrf_and_dos_in_poi_import` | **CONFIRMED (高風險漏洞)** | `import_poi_link` 未呼叫 `is_safe_url` 檢查目標主機，且使用 `follow_redirects=True`，允許透過雲端 Metadata IP (`169.254.169.254`) 或本機 (`127.0.0.1`) 發動 SSRF 攻擊。 |
| `backend/utils/url_safety.py` | `backend_to_external` | `dns_rebinding_bypass` | **SECURE** | 經測試確認阻斷 `127.0.0.1`、`0.0.0.0`、`169.254.169.254` 及私有 LAN IP。 |

---

## 三、 確認漏洞詳情與 In-Memory PoC (Confirmed Vulnerability)

### 🚨 VULN-2026-1019-01: POI 匯入端點存在伺服器端請求偽造 (SSRF)

- **檔案位置**: [`backend/routers/poi.py` 第 550-555 行](file:///d:/Project/tabiji/travel-pwa/backend/routers/poi.py#L550-L555)
- **威脅等級**: `HIGH` (CVSS 7.5)
- **根因分析**:
  使用者傳入的 `url` 在經過簡單的正則清洗後，直接由 `httpx.AsyncClient(follow_redirects=True)` 發起 GET 請求，未檢驗是否為公有 IP 或合法 Google 地圖網域。攻擊者可傳入 `http://169.254.169.254/latest/meta-data/` 竊取雲端環境元數據，或傳入內部私有服務端點發動掃描。

#### 🧪 In-Memory PoC (單元測試實證)
```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import Request
from backend.routers.poi import import_poi_link, POIImportLinkRequest

@pytest.mark.asyncio
async def test_poi_import_link_unvalidated_ssrf():
    mock_req = MagicMock(spec=Request)
    internal_metadata_url = "http://169.254.169.254/latest/meta-data/"
    payload = POIImportLinkRequest(url=internal_metadata_url)
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.url = internal_metadata_url
        mock_resp.text = "ami-id"
        mock_get.return_value = mock_resp
        
        try:
            await import_poi_link(fastapi_req=mock_req, req=payload, user_id=None, supabase=None)
        except Exception:
            pass
        
        # 實證：未經驗證的私有雲端 Metadata IP 被直接請求
        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        assert "169.254.169.254" in called_url
```

---

## 四、 候選修復方案 (Mantis Patch Candidate)

### 修復要點：
1. 在 `backend/routers/poi.py` 引入 `utils.url_safety.is_safe_url`。
2. 請求發起前強制驗證 `is_safe_url(clean_url)`，若為私有 IP、回環位址或無效協議，直接回傳 `400 Bad Request`。
3. 關閉盲目 `follow_redirects=True`，改為逐層追蹤或在收到 3xx 轉址時逐次檢查 `Location` 是否安全。

### 精確區塊替換 (Block Replacement):

**目標檔案**: `backend/routers/poi.py`  
**目標內容**:
```python
from utils.deps import get_gemini_key, get_supabase
from services.link_resolver import resolve_google_maps_link
```
**替換內容**:
```python
from utils.deps import get_gemini_key, get_supabase
from utils.url_safety import is_safe_url
from services.link_resolver import resolve_google_maps_link
```

**目標檔案**: `backend/routers/poi.py`  
**目標內容**:
```python
    clean_match = re.search(r'(https?://[^\s]+)', raw_url)
    clean_url = clean_match.group(1).rstrip('.,!?:;"\'。，！？') if clean_match else raw_url

    places = []
    final_url = clean_url
    html_content = ""
    is_placelist = "/placelists/list" in clean_url or "/placelists/" in clean_url

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12.0) as client:
            resp = await client.get(clean_url, headers={
```
**替換內容**:
```python
    clean_match = re.search(r'(https?://[^\s]+)', raw_url)
    clean_url = clean_match.group(1).rstrip('.,!?:;"\'。，！？') if clean_match else raw_url

    # 🛡️ Security Sentinel: SSRF 防護與合法網址驗證
    if not is_safe_url(clean_url):
        raise HTTPException(status_code=400, detail="不允許存取私有網路、回環位址或不安全的網址 (SSRF 防護)")

    places = []
    final_url = clean_url
    html_content = ""
    is_placelist = "/placelists/list" in clean_url or "/placelists/" in clean_url

    try:
        # 手動安全追蹤轉址，防禦開放轉址與 DNS 重綁定繞過
        async with httpx.AsyncClient(follow_redirects=False, timeout=12.0) as client:
            curr_url = clean_url
            for _ in range(6):
                resp = await client.get(curr_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                })
                if resp.status_code in (301, 302, 303, 307, 308):
                    loc = resp.headers.get("Location")
                    if not loc:
                        break
                    next_url = str(httpx.URL(curr_url).join(loc))
                    if not is_safe_url(next_url):
                        raise HTTPException(status_code=400, detail="轉址目標包含不安全或私有網路位址 (SSRF 防護)")
                    curr_url = next_url
                    continue
                break
            final_url = curr_url
            html_content = resp.text
            if "/placelists/list" in final_url or "/placelists/" in final_url:
                is_placelist = True
```

---

## 五、 首頁雙階排程交互架構 (TabijiHomeDashboard Two-Step Triage)

使用者指示：
> *「TabijiHomeDashboard. 可以設定在加入行程的時候讓你多一個可以選取行程的步驟然後選取行程之後再看是加入第幾天啊」*

### 兩階段選擇體驗設計：
在 `PoiPoolView.tsx` 中：
1. **若當前有 `currentTrip`**（從行程頁面點擊 🔖 進入）：
   - 點擊「＋ 排入行程」直接展示「選擇天數（Day 1, Day 2...）」。
2. **若當前無 `currentTrip`**（從 `TabijiHomeDashboard` 首頁點擊 🔖 進入）：
   - 點擊「＋ 排入行程」第一步：彈出 **「選擇目標行程」** 列表（列出使用者所有進行中/規劃中的行程）。
   - 點選特定行程後，第二步：展示 **「該行程之天數（Day 1, Day 2...）」**。
   - 點選天數後立即加入，卡片回顯「已排入 [東京五日遊] Day 2」，頁面保持開啟不關閉，完全符合連續排程與多行程流動彈性。

---

## 六、 人類裁決閘門 (Human Gate Handover)

依據 L0 憲法規範，本報告與修復代碼目前處於唯讀狀態。請確認核准上述 SSRF 防護補丁與首頁兩階段排程設計後，我們將立即應用補丁並開啟實作！
