# 🛡️ Security Sentinel 對抗式審計報告 — 跨區轉場走廊與長途跨海離島空間防衛 (Transit Corridor & Cross-Island Spatial Defense)

> **審計日期**: 2026-11-07  
> **審計模式**: `sentinel-agy-adversarial` (6-Phase Physical Sandbox Worktree Duel + Mantis Block G)  
> **關聯候選補丁**: [`docs/security/history/patches/patch_candidate_transit_corridor_2026-11-07.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_transit_corridor_2026-11-07.diff)  
> **關聯區塊替換描述**: [`docs/security/history/candidates/block_replacements_transit_corridor_2026-11-07.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/candidates/block_replacements_transit_corridor_2026-11-07.json)  
> **關聯對抗測試套件**: [`backend/tests/test_transit_corridor_sentinel.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_transit_corridor_sentinel.py)

---

## 1. 執行摘要與物理沙盒實證 (Executive Summary & Physical Telemetry)

本次審計針對「單日長途高鐵跨城轉場（如東京 $\to$ 京都 500km）」與「單日跨海離島航班（如台北松山 $\to$ 澎湖馬公 260km、秘魯 Lima $\to$ Cusco 580km）」進行 6 階段物理隔離沙盒（`.worktrees/sentinel-corridor`）對抗審核，在**完全不觸碰主工作區生產代碼**的前提下，完成全套紅綠門禁與全量回歸驗證：

| 驗證階段 | 物理指令 | 實測結果 |
| :--- | :--- | :--- |
| **Phase 0: 物理沙盒隔離** | `git worktree add --detach .worktrees/sentinel-corridor HEAD` | 獨立沙盒建立並同步基線 (`SANDBOX_READY`) |
| **Phase 1-2: 候選假設提取** | 產出 `candidates_transit_corridor_2026-11-07.json` | 鎖定 4 項跨城走廊與自癒邊界漏洞 (`VULN-CORRIDOR-001` ~ `004`) |
| **Phase 3: Red Gate (未修補沙盒)** | `pytest tests/test_transit_corridor_sentinel.py -k "test_sentinel_poc"` | **`RED_GATE_EXIT_CODE=1`** (`4 failed` — 100% 物理重現誤殺與穿透) |
| **Phase 4: Green Gate (修補後沙盒)** | `pytest tests/test_transit_corridor_sentinel.py -v` | **`GREEN_GATE_EXIT_CODE=0`** (`8 passed` — 4 PoC + 4 Mantis Block G 全數通過) |
| **Phase 4: 全量後端回歸套件** | 7 大測試套件共 **81 項測試** 聯合執行 | **`81 passed in 7.4s`** (0 退化) |
| **Phase 4: 雙引擎靜態型別守門** | `npx pyright` + `pyrefly check` + `npx tsc --noEmit` | **`0 errors, 0 warnings`** |
| **Phase 5: 台帳數學守恆核驗** | `python scripts/validate_security_ledger.py` | **`294 == 55 + 89 + 150`** (`[OK] Ledger integrity verified`) |

---

## 2. 漏洞假設與紅藍對抗證偽明細 (Vulnerability Findings & Chesterton Archaeology)

### 🔴 `VULN-CORRIDOR-001`: 單日中位數坍塌與跨城/跨海離島合法景點誤殺
- **檔案與行號**: [`backend/services/geocode_service.py#L2425-L2560`](file:///d:/Project/tabiji/travel-pwa/backend/services/geocode_service.py#L2425-L2560)
- **設計初衷 (Chesterton's Fence)**：原演算法假設「一日一城（Single-City Stay Day）」，利用單日中位數過濾偏離 $>180\text{ km}$ 的離群點與 $>50\text{ km}$ 的撞名地標。
- **紅隊實證 (`test_sentinel_poc_corridor_1`)**：
  1. 在「東京 $\to$ 京都 500km 新幹線轉場日」中，未修補基線將京都「伏見稻荷大社 (`34.9671, 135.7727`)」判定為距離東京錨點 `370km > 180km` 的離群點，當 OSM 逾時時直接覆寫為東京鐵塔座標 (`35.6586, 139.7454`)。
  2. 在「台北 $\to$ 澎湖 260km 跨海航班日」中，未修補基線因澎湖未列入靜態表且「澎湖天后宮」命中 `HOMONYM_GUARD_KEYS` (`>50km`)，將澎湖天后宮強行拉回台北。
- **修復機制**：引入時序多段分割 ($K$-Partitioning)，將轉場日切分為獨立子群，各子群獨立計算中位數錨點與局部 BBox，並輸出向後相容之 `type: "transit_corridor"` 與 `segments` 陣列。

### 🔴 `VULN-CORRIDOR-002`: 無條件距離跳躍分裂導致「單點 AI 幻覺自證繞過」
- **檔案與行號**: [`backend/services/geocode_service.py#L2414-L2494`](file:///d:/Project/tabiji/travel-pwa/backend/services/geocode_service.py#L2414-L2494)
- **紅隊實證 (`test_sentinel_poc_corridor_2`)**：若單純以相鄰距離 $\Delta > 80\text{ km}$ 觸發子群分裂，當 AI 在「東京駐留日」中間幻覺塞入 1 個「一蘭拉麵（大阪道頓堀座標 `34.6687, 135.5013`）」時，該假座標會自成 1 點子群（與自身中位數距離 $0\text{ km}$），完全繞過 180km 離群守衛。
- **修復機制 (Invariant 1 — `Cluster Support Condition`)**：距離跳躍 $>80\text{ km}$ 欲成為合法走廊子群，必須滿足：(A) 顯式交通轉場節點 (`_is_transit_splitter_item`)，或 (B) 局部密度支撐 $\text{MinPts} \ge 2$（60km 內至少 2 個合法點且含非撞名點），或 (C) 命中 `known_city_anchors`。孤立單點幻覺 100% 拒絕分裂並強制導正回東京。

### 🔴 `VULN-CORRIDOR-003`: 二次校驗與遠端 MCP 新增節點之「走廊失憶症」
- **檔案與行號**: [`backend/services/geocode_service.py#L2026-L2405`](file:///d:/Project/tabiji/travel-pwa/backend/services/geocode_service.py#L2026-L2405)、[`backend/routers/mcp.py#L1126-L1290`](file:///d:/Project/tabiji/travel-pwa/backend/routers/mcp.py#L1126-L1290)
- **紅隊實證 (`test_sentinel_poc_corridor_3`)**：當 `daily_locations["1"]` 儲存為 `東京 → 京都`（頂層 `lat/lng` 為抵達地京都 `35.0116, 135.7681`）後，後續呼叫 `verify_and_heal_itinerary_coords` 或透過 MCP `manage_itinerary_node` 新增上午東京景點「築地場外市場 (`35.6655, 139.7707`)」時，未修補基線僅讀取頂層京都座標，導致上午東京景點因距離京都 `370km > 180km` 遭誤殺覆寫！
- **修復機制 (Invariant 4 — `Corridor Segment Expansion on Read`)**：在 `resolve_trip_spatial_anchor`、`verify_and_heal_itinerary_coords` 與 `mcp.py` `manage_itinerary_node` (`add`/`update`) 中完整展開 `segments` 多錨點，取與當日任一合法走廊子群之最小距離進行守衛。

### 🔴 `VULN-CORRIDOR-004`: 全球無字典走廊命名退化與 `ACTION_NOISE_KEYWORDS` 假座標放行
- **檔案與行號**: [`backend/services/geocode_service.py#L2464-L2527`](file:///d:/Project/tabiji/travel-pwa/backend/services/geocode_service.py#L2464-L2527)
- **紅隊實證 (`test_sentinel_poc_corridor_4`)**：
  1. 秘魯 `Lima -> Cusco`（580km）不在 27 城靜態字典中，未修補基線將 Cusco 景點誤殺回 Lima 且無法生成走廊名稱。
  2. 「搭乘新幹線前往京都（無座標）」因含 `"搭乘"` 被 `ACTION_NOISE_KEYWORDS` 提前攔截回傳 `None`；而「飯店 check-in 休息（夾帶巴黎假座標 `48.8566, 2.3522`）」則在未檢驗國界下直接放行巴黎座標。
- **修復機制 (Invariant 2 & Invariant 3)**：
  1. `_resolve_segment_region_name` 實作四級全球無字典動態命名（`known_city_anchors` $\to$ `GLOBAL_CITY_ANCHORS` $\to$ 子群代表景點共現詞元與 `extract_region_for_search`），自動產出 `"Lima → Cusco"`。
  2. 將交通橋接節點與純動作雜訊解耦：無座標之交通橋接節點自動錨定至出發地子群中心；夾帶越界/離群假座標之純動作雜訊強制清除為 `(None, None)`。

---

## 3. 人工審查門禁 (Phase 6 Human Gate)
- **主工作區生產代碼狀態**：未修改（100% 保持原狀，所有實作變更均封裝於 [`docs/security/history/patches/patch_candidate_transit_corridor_2026-11-07.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_transit_corridor_2026-11-07.diff)）。
- **核准指令**：請下達 `/boost` 或確認指令，即可將已通過沙盒 81 項測試與雙重型別檢查的補丁正式套用至主工作區。

