# DDGS 8 大引擎全併發解鎖與查詢詞瘦身規格書 (Mini Design Doc)

## 1. Problem Statement & Root Cause (問題陳述與根本原因)

### 1.1 根本死因解剖
1. **DDGS 內核併發截斷與 Wikipedia 優先陷阱**：
   - `ddgs` 9.16.0 的 `ENGINES` 註冊表內建 8 大引擎：`['wikipedia', 'grokipedia', 'duckduckgo', 'startpage', 'google', 'mojeek', 'yahoo', 'brave']`。
   - `ddgs._search_sync` 計算執行緒數量為：`max_workers = min(len_unique_providers, ceil(max_results / 10) + 1)`。當請求 `max_results=3` 時，`max_workers` 被算出為 **2**。
   - 這導致搜尋時**只會執行前 2 個引擎（Wikipedia 與 Grokipedia，兩者皆為百科全書）**。後方的 Yahoo、DuckDuckGo、Startpage、Google 等真實網路搜尋引擎**完全沒有被執行**。
   - 此外，`wait(..., return_when="FIRST_EXCEPTION")` 在維基百科觸發 DNS 異常時立即中斷整個檢索。
2. **First-Pass 3.0s 逾時引發連鎖崩潰**：
   - 台灣至 Google US Gemini API 延遲在尖峰時段達 3.2~3.8s，`timeout=3.0` 觸發 `asyncio.TimeoutError`（錯誤字串為空 `()`）。
3. **Dual-Track 關鍵字膨脹（過度重寫）**：
   - First-Pass 逾時後，退回 `generate_dual_queries`，將原始問句與整串 `OR 食べログ OR じゃらん OR 観光協会 OR おすすめ OR 穴場` 硬接成 50 字長句，搜尋引擎對此類布林長句回傳 0 結果，被迫跌落至維基百科。
   - 維基百科 OpenSearch 只能根據「京都」兩字模糊匹配，導致結果全被動漫條目（角色列表、登場人物等）佔據。

---

## 2. Architecture & Solution Strategy (架構與解法)

```
[User Message] ➔ "幫我查詢京都現在的天氣與推薦的賞楓名所"
       │
       ▼
[First-Pass Gemini 3.1 Flash-Lite] (放寬 timeout 至 4.5s)
  ├── 成功 ➔ 提煉精準短詞: ["京都 賞楓 景點", "京都 天氣"]
  └── 逾時/失敗 ➔ [Dual-Track Query Slimming] (去除長布林，精簡為: "京都 賞楓 推薦", "京都 天氣")
       │
       ▼
[Tier 1: DDGS 8 引擎全併發解鎖]
  ├── DDGS.threads = 8 (打開封閉上限)
  ├── backend = "yahoo,duckduckgo,startpage,brave,mojeek,google" (剔除百科，只讓真實搜尋引擎併發)
  └── region = "wt-wt" (全球標準，無 tzh.wikipedia.org DNS 隱患)
       │
       ▼
[搜尋結果: 1.2s 命中 mimigo.tw / vivianexplore.tw / followtotravel.com 頂級旅遊網誌]
```

---

## 3. Detailed Component Changes (組件變更細節)

### 3.1 `backend/services/web_search_engine.py`
1. 設定全域 `DDGS.threads = 8`。
2. 在 `_sync_ddgs_call` 中顯式傳入 `backend="yahoo,duckduckgo,startpage,brave,mojeek,google"`。
3. 地區固定使用 `"wt-wt"`（因已排除維基引擎，徹底免除 `tzh.wikipedia.org` DNS 錯誤）。
4. 捕獲例外並確保個別引擎失敗不阻礙已取得之結果。

### 3.2 `backend/services/destination_taxonomy.py`
1. 重構 `generate_dual_queries`：
   - 廢除直接拼接 `食べログ OR じゃらん...` 等長布林運算元。
   - 針對日本、台灣、全球目的地，採用簡練的旅遊語意後綴（例如「`{clean_text} 推薦`」、「`{clean_text} 攻略`」）。
   - 保障查詢字串長度在 20 字以內，符合搜尋引擎最佳檢索長度。

### 3.3 `backend/main.py`
1. 將 First-Pass `asyncio.wait_for` 逾時從 `3.0s` 調整為 `4.5s`，給予國際網路往返充足餘裕。
2. 保持對多工具併發與 Grounding 注入的原有保護。

---

## 4. Acceptance Criteria (驗收標準清單)

- [ ] AC-1: `_sync_ddgs_call` 執行時能調用 Yahoo、DuckDuckGo、Startpage、Google 等實體搜尋引擎，不被 `max_workers=2` 截斷在百科。
- [ ] AC-2: 搜尋「京都賞楓」時，回傳之結果為旅遊推薦文章（如 mimigo、vivianexplore 等），無動漫或百科角色列表。
- [ ] AC-3: `generate_dual_queries` 生成之搜尋詞長度小於 25 字元，且不包含 `OR` 串聯布林語法。
- [ ] AC-4: First-Pass 逾時時間為 4.5 秒，後端單元測試與端對端驗證 100% 通過。
