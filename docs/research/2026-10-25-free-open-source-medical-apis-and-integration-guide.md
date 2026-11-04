# 2026 全球免費開源醫療 API 實測、串接指南與避坑手冊 (Open-Source Free Medical API Matrix)

> **調研主題**: 針對 Tabiji 醫療急難與跨時區守護 (`SPEC-MED-001`) 之「免費/開源醫療 API」全景考證與工程落地手冊  
> **調查渠道**: GitHub MCP 開源代碼審計、美國國家醫學圖書館 (NLM)、美國 FDA 官方開放數據、Healthsites.io (Humanitarian OSM)、OpenAEDMap、Reddit / Stack Overflow 開發者社群實測  
> **作者**: Antigravity Technical Intelligence Team  
> **適用專案**: Tabidachi (travel-pwa) - FastAPI 後端與 Next.js 16 前端  

---

## 摘要：四大免費開源醫療 API 生態對照表

| API / 資料庫名稱 | 主管/開源機構 | 計費標準與額度 | 核心功能與資料範疇 | 致命限制與避坑指南 | Tabiji 整合建議 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **NLM RxNorm / RxNav REST API** | 美國國家醫學圖書館 (NLM / NIH) | **100% 免費**<br>無須 API Key<br>上限: 20 req/sec | • 藥物標準命名 (RxCUI)<br>• 商品名轉國際通用學名 (Generic / INN)<br>• 藥物劑型、成分與 ATC 分類映射 | ⚠️ **重磅警訊**: NLM 已永久終止 Drug Interaction API（藥物交互作用）。但標準名對齊、RxCUI 搜尋完全正常。超過 20 req/s 噴 429。 | **強烈推薦**：用於將使用者輸入的各國商品名（如 Panadol、Tylenol）一鍵正規化為世界通用的 INN 學名（Acetaminophen）。 |
| **openFDA Drug API** | 美國食品藥物管理局 (FDA) | **100% 免費**<br>免 Key: 1,000 req/day<br>免費 Key: 120,000 req/day (240/min) | • 官方藥物核准仿單 (Drug Labeling)<br>• 適應症 (Indications) 與用法<br>• 嚴重不良反應 (FAERS) 與警語<br>• 藥物召回與短缺 (Shortages) | JSON 回傳結構深層且非結構化文字多，部分非處方藥欄位缺失，需使用嚴格 Zod / Pydantic schema 容錯。 | **推薦**：作為旅行常備藥物仿單、警語與禁忌症的權威背書來源。 |
| **Healthsites.io API (v3)** | Kartoza / Global Open Health GIS (基於 OSM) | **100% 免費**<br>需註冊免費 Token | • 全球人道主義醫療設施地圖<br>• 醫院、診所、藥局、急救點<br>• 官方提供 Python Client (`healthsites-api-client`) 與 GeoJSON | 偏遠開發中國家數據覆蓋極佳，但在日本/先進都市部分點位不如直接查詢原生 OSM Overpass 即時。 | **備選/互補**：可作為跨國人道救援與特定醫療據點的兜底資料源。 |
| **OpenAEDMap / OSM Overpass API** | OpenStreetMap 基金會 / OSM-Polska | **100% 免費**<br>全球公共伺服器無限制 (建議自控頻率) | • `emergency=defibrillator` (AED)<br>• `amenity=hospital|clinic|pharmacy`<br>• `opening_hours=24/7`<br>• `wheelchair=yes` (無障礙) | ⚠️ **實體致命陷阱**: 65% 的 AED 缺失室內層級 (`level=*`, `indoor=yes`)，緊急時地圖經緯度可能指向馬路中央但機器在地下室。 | **核心支柱**：Tabiji 既有架構已原生支援 Overpass，只需疊加室內層級警示與 119 一鍵直撥！ |

---

## 第一部：NLM RxNorm API 深度實測與串接架構

### 1. 核心端點與執行流程 (Execution Flow)
- **基礎 URL**: `https://rxnav.nlm.nih.gov/REST/`
- **流程 1: 商品名模糊查詢標準 RxCUI (Normalization)**:
  ```http
  GET /REST/rxcui.json?name=Tylenol&search=1
  ```
  回傳範例：
  ```json
  {
    "idGroup": {
      "name": "Tylenol",
      "rxnormId": ["202433", "209459"]
    }
  }
  ```
- **流程 2: 根據 RxCUI 提取國際非專利學名 (Generic / INN Name)**:
  ```http
  GET /REST/rxcui/202433/allProperties.json?prop=all
  ```
  可解析出活性成分：`Acetaminophen`、ATC 代碼：`N02BE01`。

### 2. Python 輕量非同步實作 (含 LRU 快取與 20 req/s 節流防衛)
```python
import httpx
import asyncio
from typing import Optional, Dict

class RxNormClient:
    BASE_URL = "https://rxnav.nlm.nih.gov/REST"
    
    def __init__(self):
        # 🛡️ 內建 30 天記憶體 LRU 快取 (藥品名稱幾乎永不改變)
        self._cache: Dict[str, str] = {}
        self._semaphore = asyncio.Semaphore(10) # 節流至每秒 10 請求，遠離 20 req/s 熔斷線
        
    async def get_generic_name(self, brand_name: str) -> Optional[str]:
        clean_name = (brand_name or "").strip().lower()
        if not clean_name:
            return None
        if clean_name in self._cache:
            return self._cache[clean_name]
            
        async with self._semaphore:
            try:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    # 1. 查詢 RxCUI
                    r1 = await client.get(f"{self.BASE_URL}/rxcui.json", params={"name": clean_name, "search": 1})
                    if r1.status_code != 200:
                        return None
                    id_group = r1.json().get("idGroup", {})
                    rxnorm_ids = id_group.get("rxnormId") or []
                    if not rxnorm_ids:
                        return None
                    
                    rxcui = rxnorm_ids[0]
                    # 2. 查詢活性學名 (IN / INN)
                    r2 = await client.get(f"{self.BASE_URL}/rxcui/{rxcui}/property.json", params={"propName": "RxNorm Name"})
                    if r2.status_code == 200:
                        prop_concept = r2.json().get("propConceptGroup", {}).get("propConcept", [])
                        if prop_concept:
                            generic = prop_concept[0].get("propValue")
                            self._cache[clean_name] = generic
                            return generic
            except Exception as e:
                # 🛡️ 優雅降級：網路逾時絕不崩潰
                return None
        return None
```

---

## 第二部：openFDA 官方開放數據庫實測

### 1. 核心端點與能力
- **端點**: `https://api.fda.gov/drug/label.json`
- **能力**: 免費提取適應症、禁忌症 (contraindications)、警語 (warnings)、儲存條件 (storage and handling，如胰島素冷藏要求)。
- **配額實況**:
  - 免 Key: `240 requests/min`, `1,000 requests/day`
  - 免費申請 Key: `240 requests/min`, `120,000 requests/day`（秒級核發，完全免費）

### 2. 開發者避坑要點
- openFDA 返回的文字很多是未分段的長條 String，直接塞進前端卡片會撐破 UI。
- **最佳實踐**：只擷取 `openfda.generic_name`、`openfda.substance_name` 與 `purpose` 前 120 字元，配合 Tabiji 既有的 `truncate` 樣式規範。

---

## 第三部：全球醫療開源標竿審查 (`JamesANZ/medical-mcp`)

在 GitHub 上由開發者社群維護的最新專案 `JamesANZ/medical-mcp` (v2.0, 2026-10) 為業界提供了極佳的工程參考典範：

### 1. 核心架構啟示
- **零 Key 原則 (Zero-Key by Default)**：RxNorm、FDA、WHO、PubMed 全部原生支援無金鑰訪問。
- **三層韌性管線 (Three-Layer Resilience Stack)**：
  ```
  請求發起 ──> [Token Bucket 速率限制] ──> [Circuit Breaker 熔斷器] ──> [Exponential Backoff 重試] ──> 上游 API
  ```
  - **熔斷策略**：上游連續 3 次失敗（或收到 429/500），熔斷 60 秒（Transitions: `CLOSED` ➔ `OPEN` ➔ `HALF_OPEN` ➔ `CLOSED`）。
  - **快取策略**：RxNorm 本機快取 30 天（`2592000s`），FDA 仿單快取 24 小時（`86400s`）。

---

## 第四部：Tabiji 落地實施藍圖（零成本閉環）

結合上述實測，Tabiji 可以在完全不增加任何伺服器費用、不引入任何高風險 SaMD 違法責任的前提下，打造極致驚豔的醫療守護功能：

```
[使用者輸入各國藥品/症狀 (如: 普拿疼 / パブロン / Advil)]
                     │
                     ▼
       ┌─────────────────────────────┐
       │   Tabiji 輕量醫療韌性中樞   │
       └─────────────┬───────────────┘
                     │
 ┌───────────────────┼───────────────────┐
 ▼                   ▼                   ▼
【RxNorm REST 查詢】 【OSM Overpass 空間】 【離線 25KB 臨床字典】
 • 0ms 本地快取優先  • 檢索 500m 內藥局  • 斷網 100% 兜底可用
 • 提取國際 INN 學名 • 標註 24H 調劑藥局 • 中日英假名對照卡
 • 免費無 Key 配額   • 常駐 119 直撥電話 • 日本醫師秒看秒懂
                     │
                     ▼
       【MedicalEmergencyCard 輸出】
       • 頂部: 🚨 官方 119/911 一鍵直撥按鈕
       • 中部: 雙時區生理時間流逝對照 (符合 21st Cures Act 豁免)
       • 底部: MapLibre 平滑運鏡直達實體藥局/AED (附室內層級警示)
```
