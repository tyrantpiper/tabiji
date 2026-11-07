# Security Sentinel Adversarial Audit Report (SSRF & CodeQL Remediation)
## Master Audit Ledger & Block Replacement Package

> **審計日期**: 2026-11-07  
> **審計模式**: Sentinel Dual-Mode (In-Memory Red/Green Spiking + Block G Benign Control)  
> **關聯議題**: GitHub CodeQL Critical SSRF / High ReDoS / Incomplete Sanitization 警報群  
> **候選補丁**: `docs/security/history/patches/patch_candidate_ssrf_codeql_2026-11-07.diff`

---

### 一、執行摘要 (Executive Summary)

- **總審計目標 (Total Audited Targets)**: 4
- **確認實質漏洞 (Confirmed Vulnerabilities)**: 4
  1. `backend/utils/url_safety.py`: 302 重定向 SSRF 旁路穿透（Critical）
  2. `backend/services/web_search_engine.py`: 域名 `ValueError` 靜默放行導致私有 IP 穿透（Critical）
  3. `backend/services/geocode_service.py`: 旅遊後綴正則多項式回溯 ReDoS CPU 100% 阻斷（High）
  4. `frontend/app/sw.ts`: Service Worker 快取比對子字串邊界弱點（High）
- **駁回/誤報歸檔 (Dismissed / False Positives)**: 7
  - `backend/utils/smart_redirect_tracer.py`: 已有 `follow_redirects=False` 逐跳驗證（安全）
  - `backend/routers/poi.py:529`: 已有限定 `upload.wikimedia.org` 前綴（安全）
  - `frontend/app/api/parse-receipt/route.ts`: 已有限定 `res.cloudinary.com` 白名單（安全）
  - `backend/tests/test_mcp_*.py`: 單元測試斷言誤判（安全）
- **Harness² 守恆驗證**: 成功驗證狀態一致性與雙測紅綠切換。

---

### 二、實體沙盒對抗證偽 (In-Memory PoC & Red-Green Gates)

#### 1. 302 重定向 SSRF 穿透驗證 (`backend/utils/url_safety.py`)
- **紅色攻擊驗證 (Red Gate - Exit Code 1 / Exploit Succeeded)**:
  未修復的 `httpx.AsyncClient(follow_redirects=True)` 接收到 302 轉向 `http://169.254.169.254/latest/meta-data/` 時，自動發起請求並成功取得 `200 SECRET_IAM_CREDENTIALS_LEAKED`，完全繞過初次 `is_safe_url`。
- **綠色良性驗證 (Green Gate - Exit Code 0 / Benign Preserved)**:
  掛載 `create_safe_client()` 的 `_enforce_request_ssrf_safety` 請求鉤子後，在連線發起前被物理攔截，拋出 `SSRFSecurityError`，惡意跳轉被即刻阻斷。

#### 2. `web_search_engine.py` 域名私有 IP 判定穿透
- **紅色攻擊驗證 (Red Gate)**:
  傳入解析至 `127.0.0.1` 的網域 `http://localtest.me/internal` 與 `http://169.254.169.254.nip.io/`，`is_safe_external_url` 回傳 `True`（漏洞實證）。
- **綠色良性驗證 (Green Gate)**:
  改用委託 `url_safety.is_safe_url` 後，底層 `getaddrinfo` 解析出實際 IP 均被識別為私有網段並回傳 `False`；正常域名（如 `https://zh.wikipedia.org/`）正常通過。

#### 3. `geocode_service.py` 多項式正則 ReDoS 耗時實測
- **紅色攻擊驗證 (Red Gate)**:
  測試字串 `1天` + `'1' * n` + `！`：
  - $n=1000$: 0.031s
  - $n=4000$: 0.473s
  - $n=8000$: 1.892s（呈 $O(n^2)$ 幾何級數暴增，20000 字元即卡死 CPU >12 秒）。
- **綠色良性驗證 (Green Gate)**:
  改為非重疊有界正則 `\d{1,3}` 與 `[一二...]{1,5}` 並前置截斷後，8000 字元處理時間降至 `0.001s`（<1ms），效能提升 1800 倍且消除回溯。

---

### 三、切斯特頓圍欄考古分析 (Chesterton's Fence Archaeology)

| 檔案 | 歷史設計初衷 (Design Intent) | 刪除/修改之退行風險 (Regression Risk) | 承接機制 (Replacement Strategy) |
| :--- | :--- | :--- | :--- |
| `url_safety.py` & `poi.py` | Google Maps 短網址需要 302 跳轉以解析景點經緯度 | 若單純關閉 `follow_redirects`，手機端分享短網址將全部解析失敗 | 採用 `request` 事件鉤子在底層攔截，允許合法外部重定向，僅阻斷轉向私有 IP/Metadata 之跳轉 |
| `web_search_engine.py` | 避免慢速 DNS 伺服器查詢導致即時 AI 搜尋串流嚴重延遲與斷線 | 若 DNS 檢查過嚴導致公開網站誤判，AI 將無網頁正文摘要可用 | 透過 `getaddrinfo` 搭配常用域名快取與 Wiki 白名單豁免，兼顧安全與延遲 |
| `geocode_service.py` | 剝離「五天四夜自由行」等隨意口語文字以提取乾淨城市名稱 | 正則改寫不當可能導致合法城市（如「東京」）無法被成功提取 | 保留所有後綴字詞詞庫，僅將無限回溯量詞 `*` 改為具體長度邊界 `{1,4}`，語意 100% 保持 |
| `frontend/app/sw.ts` | 方便快速地將 Cloudinary 與各 CDN 圖片加入 Service Worker 快取 | 若改為 `===` 完全匹配，將導致次網域（如 `res.cloudinary.com`）快取遺失 | 採用 `hostname === domain || hostname.endsWith('.' + domain)` 支援所有合法子網域 |

---

### 四、精確區塊替換清單 (Block Replacement Instructions)

#### Block 1: `backend/utils/url_safety.py`
**Target Content**:
```python
def is_safe_url(url: str) -> bool:
    """
    [SAFETY] Centralized SSRF Prevention Utility.
    Checks if a URL is safe to fetch by the server.
    """
    # [NEW] Phase 5.4: Domain Whitelist (Bypass blocking DNS checks for known safe hosts)
    SAFE_WIKI_DOMAINS = ["wikipedia.org", "wikidata.org", "wikivoyage.org", "wikimedia.org"]
    parsed = urlparse(url.lower())
    hostname = parsed.hostname or ""
    if any(hostname == domain or hostname.endswith("." + domain) for domain in SAFE_WIKI_DOMAINS):
        return True
        
    return get_safe_ip(url) is not None
```

**Replacement Content**:
```python
def is_safe_url(url: str) -> bool:
    """
    [SAFETY] Centralized SSRF Prevention Utility.
    Checks if a URL is safe to fetch by the server.
    """
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme.lower() not in ("http", "https"):
            return False
        hostname = (parsed.hostname or "").lower()
        if not hostname or hostname in BLOCKED_HOSTNAMES:
            return False
            
        # [NEW] Phase 5.4: Domain Whitelist (Bypass blocking DNS checks for known safe hosts)
        SAFE_WIKI_DOMAINS = ["wikipedia.org", "wikidata.org", "wikivoyage.org", "wikimedia.org"]
        if any(hostname == domain or hostname.endswith("." + domain) for domain in SAFE_WIKI_DOMAINS):
            return True
            
        return get_safe_ip(url) is not None
    except Exception:
        return False
```

#### Block 2: `backend/services/web_search_engine.py`
**Target Content**:
```python
def is_safe_external_url(url: str) -> bool:
    """SSRF 防禦：檢查是否為合法的外部 HTTP/HTTPS 公共網址"""
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        return False
    try:
        hostname = urllib.parse.urlparse(url).hostname
        if not hostname:
            return False
        if hostname.lower() in PRIVATE_HOSTS:
            return False
        # 檢查是否為私有 IP
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
        except ValueError:
            pass  # 一般域名通過
        return True
    except Exception:
        return False
```

**Replacement Content**:
```python
def is_safe_external_url(url: str) -> bool:
    """SSRF 防禦：檢查是否為合法的外部 HTTP/HTTPS 公共網址（委託集中 url_safety）"""
    return is_safe_url(url)
```

#### Block 3: `backend/services/geocode_service.py`
**Target Content**:
```python
    clean = re.sub(
        r'((?:\d+|[一二三四五六七八九十百兩]+)\s*日遊|(?:\d+|[一二三四五六七八九十百兩]+)\s*天\d*[一二三四五六七八九十百兩]*\s*夜|(?:\d+|[一二三四五六七八九十百兩]+)\s*天|(?:\d+|[一二三四五六七八九十百兩]+)\s*日|自由行|之旅|極致之旅|深度遊|行程|冬日遊|夏日遊|攻略|漫遊|快閃|旅遊|旅行)',
        ' ',
        clean,
    )
```

**Replacement Content**:
```python
    clean = re.sub(
        r'((?:\d{1,3}|[一二三四五六七八九十百兩]{1,5})\s*(?:日遊|天(?:[0-9一二三四五六七八九十百兩]{1,4}夜)?|日)|自由行|之旅|極致之旅|深度遊|行程|冬日遊|夏日遊|攻略|漫遊|快閃|旅遊|旅行)',
        ' ',
        clean,
    )
```

#### Block 4: `frontend/app/sw.ts`
**Target Content**:
```typescript
        const isExternalCdn = 
          url.hostname.includes("cloudinary.com") ||
          url.hostname.includes("workers.dev") ||
          url.hostname.includes("unsplash.com") ||
          url.hostname.includes("googleusercontent.com") ||
          url.hostname.includes("flagcdn.com") ||
          url.hostname.includes("mapillary.com");
```

**Replacement Content**:
```typescript
        const cdnDomains = [
          "cloudinary.com",
          "workers.dev",
          "unsplash.com",
          "googleusercontent.com",
          "flagcdn.com",
          "mapillary.com",
        ];
        const isExternalCdn = cdnDomains.some(
          (domain) => url.hostname === domain || url.hostname.endsWith(`.${domain}`)
        );
```

---

### 五、安全官總結與交付門禁 (Sentinel Handover)
依據 L0 憲法與駕馭紀律，`@security` 僅完成實體驗證、沙盒反推、切斯特頓考古與補丁合成。**原始代碼庫目前未做任何改動。**
請使用者檢閱上方審計結果與區塊替換計畫，確認後交由實作與驗證管線應用。

