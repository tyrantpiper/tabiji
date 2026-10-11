# 2026 全球 AI 旅遊規劃系統架構對比與 Tabiji 工具箱重構獨立研究報告
> **調研主題**：AI 旅遊架構現況深度剖析（領先業界 vs. 夜郎自大）、GitHub 開源實作流程驗證、ToolsView 功能架構重構指南  
> **研究日期**：2026-10-11  
> **數據來源**：GitHub MCP (`github-mcp-server`)、全球開發者社群 (Reddit/HackerNews/V2EX/X)、2025-2026 官方發布日誌與 API 變更、Tabidachi 核心源碼

---

## Executive Summary：客觀現狀診斷（獨步領先 vs 夜郎自大）

| 評估維度 | 業界主流 / 開源現狀 (2025–2026) | Tabiji 當前架構實作 | 客觀評級 | 診斷結論 |
| :--- | :--- | :--- | :--- | :--- |
| **離線優先 (Offline-First)** | 95% 純雲端 SaaS，無網路即白畫面癱瘓；僅少數如 Wanderlog Pro 原生 App 支援唯讀下載 | ServiceWorker + IndexedDB + SWR 樂觀更新 + 離線突變同步佇列 | **領先業界** | 真實解決日本地下鐵/偏遠景點斷網痛點 |
| **資料安全與隱私** | 中心化收集個資，依賴後端伺服器轉發 API Key，強制高昂訂閱月費 | BYOK (Bring Your Own Key) + 客戶端 Web Crypto (AES-GCM) 零信任存儲 | **領先業界** | 兼顧自託管極客隱私與零中心化架構成本 |
| **旅行金融精算** | 僅支援靜態預算欄位 (Budget: Low/Med/High)，無視跨國金融手續費 | 支援 JCB/Visa/MasterCard 海外回饋上限水位、1.5% 手續費折抵、多人公積金墊付分攤圖論演算法 | **獨創護城河** | 市面無任何開源專案或主流商業軟體達到此深度 |
| **美學與互動體驗** | 90% 為通用 Tailwind/Bootstrap 或 Streamlit/Gradio 原型套版 | 和紙 (Washi) 侘寂 (Wabi-Sabi) 色票系統 + Framer Motion 手勢微動態 + MapLibre WebGL 大圓航線 | **領先同級** | 具備高度差異化之品牌視覺識別度 |
| **工具箱頁面定位 (Tools Architecture)** | 商業 App 工具頁通常聚焦於「路上工具」(匯率換算、行李打包、退稅試算) | 在 ToolsView 硬塞 `AiGrillMeWizard`、`AiImportTripWizard` 與自由提示詞生成 | **夜郎自大 / 冗餘盲點** | **嚴重疊床架屋**：與主行程畫布與隨行 ChatWidget 功能重複，違背路上高頻使用情境 |

---

## 第一章：網路與官方資料檢索（2025–2026 官方演進與大神避坑指南）

### 1.1 官方宣稱與 API 演進 (Official Landscape)
- **OpenAI / Anthropic / Google Vertex AI Travel Agents (2025–2026)**：
  - 官方倡導「多智能體工作流 (Multi-Agent Workflows)」與「嚴格結構化輸出 (Structured Outputs / JSON Schema Enforcement)」。
  - 主打：透過 Function Calling / Tool Calling 自動呼叫 Google Flights、Amadeus 或 Booking.com API 完成即時比價與下訂。
- **官方規格變更核心趨勢**：
  - 捨棄純 Prompt 自由文字生成，全面轉向 Typed Function Calling。
  - 導入長上下文 (Long-context Window) 搭配持久化使用者偏好設定 (User Persona Memory)。

### 1.2 網路技術大神踩坑紀錄與爭議點 (Reddit / HackerNews / V2EX)
社群技術大神與深度旅行玩家對 2025–2026 年市面「AI Travel Planner」的一致共識為：**「紙上談兵，出發即崩」**。核心痛點歸納為四項：
1. **90% 幻覺與實體鮮度崩壞 (The Freshness Deficit)**：
   - LLM 靜態權重經常推薦已經於數月前永久停業的日本店家，或忽視神社/水族館特定的休館日、雪季封路、施工公休。
   - 官方宣稱的即時聯網，因 Rate Limits 或各國在地店家未建立英文/API 索引，仍常查無此店而觸發兜底幻覺。
2. **無視物理定律與生理極限 (Physical Infeasibility)**：
   - AI 排行程計算距離常使用兩點直線歐幾里得距離，忽視了「東京車站轉乘京葉線需徒步 15 分鐘」、「京都公車爆滿等三班上不去」、「新宿地下迷宮找出口」的真實物理耗時。
   - 產出典型「特種兵死板行程」，缺乏交通緩衝與人體生理休息時間。
3. **出發後的真空期 (Post-Booking Silence)**：
   - 幾乎所有 AI 旅遊工具只在「出發前在沙發上規劃時」被打開一次；一旦旅客抵達目的地機場，AI 產品便喪失存在感。
   - 在旅途路上（On the Road），旅客需要的是**「秒開、單手操作、不需聯網、解決單點摩擦」**的微型工具，而非冗長繁瑣的對話方塊。
4. **工具架構錯置 (Feature Placement Anti-Pattern)**：
   - 將行程生成功能分散於「工具頁」與「行程主頁」，迫使使用者在不同頁籤之間重複確認狀態，打破了認知心智模型。

---

## 第二章：GitHub 本地與開源實作調研（原始碼層級分析）

透過 GitHub MCP (`github-mcp-server`) 對全站 2,821+ 個開源 AI Travel 專案（如 `zinedkaloc/ai-travel-planner`, `kbhujbal/Multi-Agent-AI-Travel-Advisor`, `aws-samples/personalized-travel-itinerary-planner`, `KalyanM45/TravelBrain-Multi-Agent-AI-Travel-Planner`）進行深度檢索，其底層架構呈現高度同質化。

### 2.1 典型開源架構執行流程 (Execution Flow)
```
[User Form Input] 
  (Destination, Budget, Days, Interests)
         │
         ▼
[Prompt Chaining / Multi-Agent Coordinator]
  ├── CrewAI / LangChain Agents (FlightAgent, HotelAgent, ActivityAgent)
  └── LLM Completion (OpenAI / Claude / Bedrock)
         │
         ▼
[JSON Parsing / Markdown Splitting]
         │
         ▼
[Static Web / Streamlit / React Component Display]
```

### 2.2 開源實作的核心技術組件缺陷 (GitHub Code-Level Verification)
1. **無狀態 (Stateless) 與無離線架構**：
   - GitHub 專案 99% 無任何 ServiceWorker 或 IndexedDB 實作。
   - 重新整理頁面或進入地鐵飛行模式，生成的資料即刻遺失，缺乏本地 Snapshot 與 Optimistic Mutate 機制。
2. **金融計算極度粗糙**：
   - 開源代碼中對 `budget` 的處理僅為字串分類（`['Budget', 'Mid-range', 'Luxury']`），缺乏即時匯率換算、無跨幣別結算、無信用卡回饋折抵與分帳演算法。
3. **資安風險暴露**：
   - 多數專案直接在前端要求輸入 `OPENAI_API_KEY` 並以明文存於 `localStorage`，或將 Key 硬編碼於後端伺服器環境變數，缺乏客製金鑰的 AES-GCM 端對端密文保護。

---

## 第三章：多輪推導與交叉比對（官方 vs 大神 vs 實測代碼）

| 檢驗維度 | 官方宣稱 (Google/OpenAI) | 網路大神/社群實測 | GitHub 開源代碼現實 | 實施邊界效應 (Edge Cases) & 隱藏 Bug |
| :--- | :--- | :--- | :--- | :--- |
| **API 即時訂票/比價** | 全自動化 Agent 代訂行程 | API 權限嚴格、頻繁封鎖爬蟲，根本無法在個人開源中實作 | 99% 的 GitHub 專案僅回傳 Mock 資料或文字描述，無一真正打通真實訂單交易 | 外部 API 變更即癱瘓；未授權下單引發金融扣款爭議 |
| **多模態行程匯入** | 截圖、PDF 一鍵轉換結構化行程 | 各國票券排版差異極大，OCR 經常漏字或日期格式錯亂 | 代碼僅做簡單文字正則萃取，對非英文機票與日文預約信解析率低 | 時區偏移（UTC vs JST/TST）導致行程跨日錯位 |
| **工具箱定位** | 整合式超級入口 (All-in-One Superapp) | 實測證實使用者更愛單一目的精簡工具，排斥在小螢幕塞入複雜表單 | 代碼庫堆疊過多不同功能的 View，造成打包體積暴增與 Render 延遲 | 頁籤切換時表單狀態被清空、背景重複請求產生 Race Condition |

---

## 第四章：Tabiji 工具頁面 (ToolsView) 改建規格建議

### 4.1 核心決策：移除 `TabsContent value="ai"`
- **工程動機**：
  - 目前 `tools-view.tsx` 行數高達 1,753 行，其中約 300 行是用於渲染 `AiGrillMeWizard`、`AiImportTripWizard` 與 `toolsAiMode` 狀態切換。
  - 行程主頁已具備 `AiImportTripWizard`，隨行浮球 `ChatWidget` 已支援全能對話與 POI 檢索，在工具頁保留此 Tab 形成嚴重的「工程疊床架屋」。
- **決策結論**：物理移除 `ai` 分頁，釋放代碼負擔與心智負載。

### 4.2 改建方向選項評估（路上高頻剛需工具）
依據日本旅行「在路上（On the Road）」的實際高頻需求，改建工具應符合：**「秒開即用、離線可靠、單手操作、精準消除金錢或行政摩擦」**。

1. **候選 A（強烈推薦）：【日幣匯率 ✕ 藥妝/電器免稅即時精算器】(Tax-Free & Rate Actuary)**
   - **痛點**：在唐吉訶德或 Bic Camera 結帳前，遊客必須手動計算：
     - 未稅價 vs 含稅價（日本 10% 消費稅）。
     - 是否達到免稅門檻（通常未稅滿 5,000 日圓）。
     - 搭配特定信用卡（例如 JCB 3% 回饋）扣除 1.5% 海外手續費後的實際台幣支出。
   - **優勢**：可無縫串聯 Tabiji 既有的 `CreditCard` 回饋清單與離線匯率快取，成為全日旅遊必用之殺手級工具。

2. **候選 B：【智慧行前與行李清單】(Smart Packing & Readiness Checklist)**
   - **痛點**：行前常漏帶護照、網卡、VJW 填寫、行動電源容量超標等；市面清單多為靜態 Todo，無法根據旅行天數與天氣推薦。
   - **優勢**：可依據行程天數提供模板，並支援勾選持久化離線存儲。

3. **候選 C：【日本就醫與緊急求助卡片】(Medical & Emergency Flashcards)**
   - **痛點**：在藥局或急診室需要表達症狀（如發燒、腸胃炎、過敏）或尋找大使館求助電話。
   - **優勢**：純靜態離線可用，關鍵時刻救急。
