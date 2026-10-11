# 🛡️ Security Sentinel 深度安全與對抗審計報告：全球化行程範本與地理幣別閉環

> **審計日期**: 2026-10-11  
> **審計模式**: `sentinel-agy-adversarial` ✕ In-Memory Pytest & Vitest Sandbox PoC  
> **遵循憲法**: L0 憲法安全第一、人類主權（唯讀審查、零私自改碼）、Maker-Checker 嚴格隔離  
> **受審目標**:
> 1. `backend/services/geocode_service.py:LOCATION_KEYWORDS` (歐美關鍵字缺漏引發之法幣誤判為 TWD 與地理錨點漂移)
> 2. `frontend/components/itinerary/AiImportTripWizard.tsx:TEMPLATE_PILLS` (天數虛標截斷、地域偏狹與 i18n 語系穿透漏洞)

---

## 1. 執行總結 (Executive Summary)

| 指標 | 數值 | 說明 |
| :--- | :--- | :--- |
| **受審目標總數** | 2 項 | 後端確定性國家/幣別推斷引擎、前端 AI 匯入範本快選矩陣 |
| **實證缺陷 (Confirmed Defect)** | 2 項 | 1. 巴黎/紐約行程因關鍵字缺漏誤判為新台幣 (TWD) 並喪失地理邊界錨點；2. 前端 5 日範本僅提供 2~3 日導致行程截斷 |
| **證偽無虞 (Dismissed)** | 0 項 | 兩項假設皆經由獨立 `agy.exe --sandbox` 子代理人證實存在 |
| **沙盒實體驗證狀態** | **100% VERIFIED** | In-Memory Pytest (`test_sentinel_global_templates.py`) 1/1 PASS，Vitest (`ai-import-templates-sentinel.test.ts`) 1/1 PASS |

---

## 2. 沙盒對抗證偽與實體量測 (Sandbox Empirical Proofs)

### 2.1 [CONFIRMED] 後端歐美行程幣別誤判為新台幣與地理編碼錨點漂移
* **對抗假設**:
  在使用者匯入巴黎或紐約行程時，`backend/services/geocode_service.py` 中的 `LOCATION_KEYWORDS` 僅定義了東亞/東南亞（`JP`, `KR`, `TW`, `TH`, `VN`, `SG`, `HK`），缺少 `FR`（法國/巴黎）與 `US`（美國/紐約）。`detect_country_from_keywords` 返回 `None`，使 `infer_currency_from_destination` 強制跌入預設回退值 `TWD`（新台幣），且使 `dest_country` 變成 `None` 喪失地理邊界過濾。
* **沙盒 In-Memory PoC 實證 (`backend/tests/test_sentinel_global_templates.py`)**:
  - **復現結果**:
    - `has_fr`: `False` (證實 FR 未收錄)
    - `has_us`: `False` (證實 US 未收錄)
    - `Paris -> Country`: `None`，`Currency`: `TWD`（**實證重大業務漏洞：歐洲行程全數以新台幣計價**）
    - `NYC -> Country`: `None`，`Currency`: `TWD`（**實證重大業務漏洞：美洲行程全數以新台幣計價**）
  - **安全影響**:
    - 嚴重破壞使用者記帳、匯率換算及預算統計功能。
    - 景點（如「聖母院」）在缺少 `country=FR` 錨點下，可能被錯誤編碼至加拿大蒙特婁或美洲景點。

---

### 2.2 [CONFIRMED] 前端範本天數虛標截斷與缺乏全球化/i18n 支援
* **對抗假設**:
  `frontend/components/itinerary/AiImportTripWizard.tsx` 中 `TEMPLATE_PILLS` 標籤載明 5 日、3 日、4 日，但其 Markdown 內文分別僅包含 3 日、2 日、2 日內容。傳送給後端解析後，前後端均以 items 之 `maxDay` 計算天數，導致 5 日行程硬生生被縮減為 3 日；且範本全部為日本城市，標題與提示訊息均寫死為繁體中文，切換為英文介面時產生嚴重的國際化斷裂。
* **沙盒 In-Memory PoC 實證 (`frontend/__tests__/ai-import-templates-sentinel.test.ts`)**:
  - **復現結果**:
    - `hasTokyoDay4`: `false` (證實 Day 4 缺失)
    - `hasTokyoDay5`: `false` (證實 Day 5 缺失)
    - `hasParis`: `false` (證實缺乏歐洲代表)
    - `hasNewYork`: `false` (證實缺乏美洲代表)

---

## 3. 候選補丁與精確區塊替換規格 (Candidate Patches)

### 3.1 目標 1：`backend/services/geocode_service.py`
* **說明**: 在 `LOCATION_KEYWORDS` 補足法國 (`FR`) 與美國 (`US`) 常用中英文關鍵字，使歐美行程能精準推斷法定貨幣 (`EUR` / `USD`) 並鎖定空間邊界。
* **RFC Diff**:
```diff
--- a/backend/services/geocode_service.py
+++ b/backend/services/geocode_service.py
@@ -1078,3 +1078,17 @@
         "迪士尼", "disney", "海洋公園", "ocean park", "大嶼山", "lantau",
     ],
+    "FR": [
+        "巴黎", "paris", "法國", "france", "尼斯", "nice", "里昂", "lyon",
+        "馬賽", "marseille", "波爾多", "bordeaux", "羅浮宮", "louvre",
+        "艾菲爾", "eiffel", "凡爾賽", "versailles", "聖母院", "notre dame",
+        "奧賽", "orsay", "蒙馬特", "montmartre",
+    ],
+    "US": [
+        "紐約", "new york", "nyc", "美國", "usa", "洛杉磯", "los angeles",
+        "舊金山", "san francisco", "西雅圖", "seattle", "芝加哥", "chicago",
+        "曼哈頓", "manhattan", "布魯克林", "brooklyn", "時代廣場", "times square",
+        "中央公園", "central park", "大都會", "metropolitan", "自由女神", "statue of liberty",
+    ],
 }
```
* **精確區塊替換**:
  - **Target File**: `backend/services/geocode_service.py`
  - **Target Content**:
```python
        "迪士尼", "disney", "海洋公園", "ocean park", "大嶼山", "lantau",
    ],
}
```
  - **Replacement Content**:
```python
        "迪士尼", "disney", "海洋公園", "ocean park", "大嶼山", "lantau",
    ],
    "FR": [
        "巴黎", "paris", "法國", "france", "尼斯", "nice", "里昂", "lyon",
        "馬賽", "marseille", "波爾多", "bordeaux", "羅浮宮", "louvre",
        "艾菲爾", "eiffel", "凡爾賽", "versailles", "聖母院", "notre dame",
        "奧賽", "orsay", "蒙馬特", "montmartre",
    ],
    "US": [
        "紐約", "new york", "nyc", "美國", "usa", "洛杉磯", "los angeles",
        "舊金山", "san francisco", "西雅圖", "seattle", "芝加哥", "chicago",
        "曼哈頓", "manhattan", "布魯克林", "brooklyn", "時代廣場", "times square",
        "中央公園", "central park", "大都會", "metropolitan", "自由女神", "statue of liberty",
    ],
}
```

---

### 3.2 目標 2：`frontend/components/itinerary/AiImportTripWizard.tsx`
* **說明**: 替換為亞洲（東京 5 日）、歐洲（巴黎 5 日）、美洲（紐約 5 日）完整天數範本，並支援中/英雙語自適應切換與多語系 Toast 提示。
* **RFC Diff**:
```diff
--- a/frontend/components/itinerary/AiImportTripWizard.tsx
+++ b/frontend/components/itinerary/AiImportTripWizard.tsx
@@ -29,58 +29,190 @@
-// 經典範本快選
-const TEMPLATE_PILLS = [
-    {
-        label: "🇯🇵 東京 5 日自由行",
-        content: `# 東京 5 日遊行程表
-## Day 1 (10/01)
-...
-## Day 3 (10/03)
-...`
-    },
-    ...
-]
+// 經典範本快選 (亞洲、歐洲、美洲 各一，完整 5 日行程)
+const TEMPLATE_PILLS_ZH = [
+    {
+        label: "🇯🇵 東京 5 日自由行",
+        content: `# 東京 5 日自由行行程表
+## Day 1 (10/01)
+- 10:30 抵達 成田機場 (搭乘 Skyliner 前往市區)
+- 13:00 淺草寺 (參拜與雷門拍照)
+- 15:30 晴空塔 (展望台眺望與逛街)
+- 18:30 淺草今半 (壽喜燒百年名店晚餐)
+- 20:30 隅田川水岸步道散步
+
+## Day 2 (10/02)
+- 09:00 築地場外市場 (生魚片丼飯早餐)
+- 11:30 銀座商圈 (GINZA SIX 與文房具伊東屋)
+- 15:00 皇居外苑與二重橋
+- 18:00 六本木之丘 (森大樓 52F 觀景台看東京鐵塔夜景)
+- 20:30 六本木 一蘭拉麵
+
+## Day 3 (10/03)
+- 09:30 明治神宮 (森林散步參拜)
+- 11:30 原宿竹下通與表參道 (咖啡廳跑店)
+- 15:00 澀谷 SHIBUYA SKY (夕陽展望台)
+- 18:30 澀谷十字路口與居酒屋街
+
+## Day 4 (10/04)
+- 09:30 上野恩賜公園 (阿美橫町漫步採買)
+- 12:30 秋葉原電器街 (動漫文化巡禮與女僕咖啡)
+- 15:30 東京車站丸之內 (百年紅磚車站建築美學)
+- 18:30 銀座篝拉麵 (極上雞白湯拉麵晚餐)
+
+## Day 5 (10/05)
+- 10:00 台場海濱公園 (自由女神像與彩虹大橋眺望)
+- 12:30 teamLab Planets (沉浸式光影藝術體感)
+- 15:30 羽田機場 (市區退稅採買與搭機返程)`
+    },
+    {
+        label: "🇫🇷 巴黎 5 日藝文浪漫",
+        content: `# 巴黎 5 日藝文浪漫行程表
+## Day 1 (05/10)
+- 10:00 抵達 戴高樂機場 (搭乘 RER B 線前往巴黎市區)
+- 14:00 艾菲爾鐵塔 (戰神廣場漫步與鐵塔合影)
+- 17:00 塞納河遊船 (Bateaux Parisiens 傍晚遊船體驗)
+- 19:30 夏樂宮 (觀賞鐵塔夜間整點閃燈秀)
+
+## Day 2 (05/11)
+- 09:00 羅浮宮博物館 (蒙娜麗莎與勝利女神經典巡禮)
+- 13:00 杜樂麗花園 (露天綠椅漫步休閒)
+- 15:00 協和廣場與香榭麗舍大道
+- 18:00 巴黎凱旋門 (登頂俯瞰十二道放射大道日落)
+- 20:00 香榭麗舍法式小酒館晚餐
+
+## Day 3 (05/12)
+- 09:30 奧賽美術館 (印象派梵谷與莫內名作賞析)
+- 13:00 巴黎聖母院與西堤島漫步
+- 15:30 莎士比亞書店 (塞納河畔左岸藝文書香)
+- 18:00 拉丁區雙叟咖啡館 (享受經典左岸露天咖啡)
+
+## Day 4 (05/13)
+- 09:00 凡爾賽宮 (鏡廳與宏偉皇家法式花園半日遊)
+- 14:30 瑪黑區 (歷史街區選物店與孚日廣場散策)
+- 18:30 巴士底市集周邊經典油封鴨晚餐
+
+## Day 5 (05/14)
+- 09:30 蒙馬特高地與聖心堂 (俯瞰巴黎全景)
+- 11:30 蒙馬特愛牆 (浪漫打卡與畫家村漫步)
+- 14:00 老佛爺百貨奧斯曼旗艦店 (彩繪玻璃圓頂採買伴手禮)
+- 17:30 前往 戴高樂機場 (辦理退稅手續與搭機回程)`
+    },
+    {
+        label: "🇺🇸 紐約 5 日都會經典",
+        content: `# 紐約 5 日都會經典行程表
+## Day 1 (09/18)
+- 11:00 抵達 甘迺迪國際機場 (搭乘 AirTrain 前往曼哈頓)
+- 14:30 時代廣場 (百老匯街景與璀璨廣告看板)
+- 17:30 洛克斐勒中心 (巨石陣觀景台 Top of the Rock 日落夜景)
+- 20:00 Junior's Restaurant (經典紐約起司蛋糕與美式晚餐)
+
+## Day 2 (09/19)
+- 09:00 中央公園 (畢士大噴泉與林蔭大道晨間散步)
+- 11:30 大都會藝術博物館 (The Met 世界級藝術殿堂)
+- 15:30 第五大道 (奢華商圈與聖派翠克大教堂)
+- 18:30 帝國大廈 (經典地標 86 樓露天觀景台夜景)
+
+## Day 3 (09/20)
+- 09:00 砲台公園搭乘渡輪 (參觀自由女神像與埃利斯島)
+- 12:30 華爾街 (紐約證券交易所與華爾街銅牛拍照)
+- 14:30 911 國家紀念博物館與世貿中心轉運站
+- 17:30 雀兒喜市場 (龍蝦堡晚餐與文創市集)
+
+## Day 4 (09/21)
+- 09:30 高線公園 The High Line (空中鐵道花園漫步)
+- 11:30 哈德遜園區 The Vessel 與 Edge 觀景台
+- 14:30 蘇活區 SoHo (鑄鐵建築群與潮流品牌選品)
+- 17:30 布魯克林大橋 (黃昏徒步橫跨東河賞曼哈頓天際線)
+- 19:30 DUMBO 曼哈頓大橋網美街角拍照與 Grimaldi's Pizza
+
+## Day 5 (09/22)
+- 09:30 紐約現代藝術博物館 MoMA (星夜與現代藝術精華)
+- 12:30 中央車站 Grand Central Terminal (百年天花板星空)
+- 14:30 布萊恩公園與紐約公共圖書館
+- 17:00 前往 甘迺迪國際機場 (搭機返程)`
+    }
+]
+
+const TEMPLATE_PILLS_EN = [
+    {
+        label: "🇯🇵 Tokyo 5-Day Highlights",
+        content: `# Tokyo 5-Day Highlights Itinerary
+## Day 1 (10/01)
+- 10:30 Arrive at Narita Airport (Take Skyliner to downtown)
+- 13:00 Senso-ji Temple (Asakusa gate and historic walking)
+- 15:30 Tokyo Skytree (Observation deck and shopping)
+- 18:30 Asakusa Imahan (Traditional Sukiyaki Dinner)
+- 20:30 Sumida River Waterfront Stroll
+
+## Day 2 (10/02)
+- 09:00 Tsukiji Outer Market (Fresh sashimi bowl breakfast)
+- 11:30 Ginza Shopping District (GINZA SIX and Itoya)
+- 15:00 Imperial Palace East Gardens and Nijubashi Bridge
+- 18:00 Roppongi Hills (Mori Tower 52F Tokyo Tower night view)
+- 20:30 Roppongi Ichiran Ramen
+
+## Day 3 (10/03)
+- 09:30 Meiji Shrine (Forested shrine morning walk)
+- 11:30 Harajuku Takeshita Street and Omotesando Cafes
+- 15:00 Shibuya SHIBUYA SKY (Sunset observation deck)
+- 18:30 Shibuya Crossing and Nonbei Yokocho Izakaya
+
+## Day 4 (10/04)
+- 09:30 Ueno Onshi Park and Ameyoko Market
+- 12:30 Akihabara Electric Town (Anime culture and tech)
+- 15:30 Tokyo Station Marunouchi Brick Architecture
+- 18:30 Ginza Kagari Ramen (Tori Paitan Ramen)
+
+## Day 5 (10/05)
+- 10:00 Odaiba Seaside Park (Statue of Liberty and Rainbow Bridge)
+- 12:30 teamLab Planets (Immersive digital art experience)
+- 15:30 Haneda Airport Departure`
+    },
+    {
+        label: "🇫🇷 Paris 5-Day Cultural Romance",
+        content: `# Paris 5-Day Cultural Romance Itinerary
+## Day 1 (05/10)
+- 10:00 Arrive at CDG Airport (Take RER B to Paris center)
+- 14:00 Eiffel Tower (Champ de Mars walk and iconic photography)
+- 17:00 Seine River Cruise (Bateaux Parisiens sunset cruise)
+- 19:30 Trocadero Square (Eiffel Tower evening sparkle show)
+
+## Day 2 (05/11)
+- 09:00 Louvre Museum (Mona Lisa and Venus de Milo tour)
+- 13:00 Tuileries Garden (Relaxing park walk)
+- 15:00 Place de la Concorde and Champs-Elysees Avenue
+- 18:00 Arc de Triomphe (Rooftop sunset panoramic view)
+- 20:00 Classic French Bistro Dinner on Champs-Elysees
+
+## Day 3 (05/12)
+- 09:30 Musee d'Orsay (Impressionist masterpieces of Van Gogh and Monet)
+- 13:00 Notre-Dame Cathedral and Ile de la Cite
+- 15:30 Shakespeare and Company Bookstore (Left Bank literary walk)
+- 18:00 Cafe de Flore or Les Deux Magots (Historic Left Bank coffee)
+
+## Day 4 (05/13)
+- 09:00 Palace of Versailles (Hall of Mirrors and royal gardens)
+- 14:30 Le Marais District (Historic boutiques and Place des Vosges)
+- 18:30 Bastille neighborhood duck confit dinner
+
+## Day 5 (05/14)
+- 09:30 Montmartre and Sacre-Coeur Basilica
+- 11:30 Wall of Love (Square Jehan Rictus romance stroll)
+- 14:00 Galeries Lafayette Haussmann (Art Nouveau stained-glass dome)
+- 17:30 Transfer to CDG Airport for Departure`
+    },
+    {
+        label: "🇺🇸 NYC 5-Day Urban Explorer",
+        content: `# NYC 5-Day Urban Explorer Itinerary
+## Day 1 (09/18)
+- 11:00 Arrive at JFK Airport (AirTrain to Manhattan)
+- 14:30 Times Square (Broadway neon lights and vibrant atmosphere)
+- 17:30 Rockefeller Center (Top of the Rock sunset observation deck)
+- 20:00 Junior's Restaurant (Classic NY cheesecake and dinner)
+
+## Day 2 (09/19)
+- 09:00 Central Park (Bethesda Terrace and The Mall morning walk)
+- 11:30 The Metropolitan Museum of Art (The Met world-class exhibits)
+- 15:30 Fifth Avenue (Shopping and St. Patrick's Cathedral)
+- 18:30 Empire State Building (86th floor open-air observatory night view)
+
+## Day 3 (09/20)
+- 09:00 Battery Park Ferry (Statue of Liberty and Ellis Island)
+- 12:30 Wall Street (New York Stock Exchange and Charging Bull)
+- 14:30 9/11 Memorial and Oculus Transportation Hub
+- 17:30 Chelsea Market (Lobster roll dinner and artisan market)
+
+## Day 4 (09/21)
+- 09:30 The High Line (Elevated linear park walk)
+- 11:30 Hudson Yards (The Vessel and Edge observation deck)
+- 14:30 SoHo Cast Iron District (Design boutiques and cafe break)
+- 17:30 Brooklyn Bridge (Golden hour walk towards DUMBO)
+- 19:30 DUMBO Manhattan Bridge photo spot and Grimaldi's Pizza
+
+## Day 5 (09/22)
+- 09:30 Museum of Modern Art (MoMA Starry Night and modern art)
+- 12:30 Grand Central Terminal (Historic celestial ceiling)
+- 14:30 Bryant Park and New York Public Library
+- 17:00 Transfer to JFK Airport for Departure`
+    }
+]
```
```diff
@@ -163,5 +295,5 @@
     const handleApplyTemplate = (content: string) => {
         haptic.selection()
         setImportText(content)
-        toast.info("已填入範本，點擊下方按鈕開始解析！")
+        toast.info(zh ? "已填入範本，點擊下方按鈕開始解析！" : "Template loaded! Click below to start parsing.")
     }
```
```diff
@@ -213,9 +345,9 @@
             {/* 💡 經典範本快選膠囊 */}
             <div className="space-y-1.5">
                 <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-slate-400">
                     <span className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-bold">
                         <Sparkles className="w-3.5 h-3.5" />
-                        <span>範本快選體驗</span>
+                        <span>{zh ? "範本快選體驗" : "Quick Template Experience"}</span>
                     </span>
-                    <span className="text-[11px] text-slate-400">點擊一鍵帶入</span>
+                    <span className="text-[11px] text-slate-400">{zh ? "點擊一鍵帶入" : "Click to apply"}</span>
                 </div>
                 <div className="flex flex-wrap gap-1.5">
-                    {TEMPLATE_PILLS.map((tmpl, i) => (
+                    {(zh ? TEMPLATE_PILLS_ZH : TEMPLATE_PILLS_EN).map((tmpl, i) => (
```

---

## 4. 人類主權閘門 (Human Gate Handover)
依據 L0 憲法規範，本審計報告已完成對抗驗證與 In-Memory 實體證偽。候選補丁已就緒，請人類審查員（Ryan）檢視確認後，指示交由 `@dev` 執行應用，並交由 `@qa` 進行全域品質檢查（`tsc --noEmit` & Vitest & Playwright）。
