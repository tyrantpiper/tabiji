# 🔬 Tabidachi 前瞻技術調研與架構深潛庫 (Research Repository)

> **定位守則 (Master Doctrine)**:  
> 本目錄專門收錄專案在引進重大第三方技術、邊緣架構與外部 API 整合前的**先導技術調研（Pre-Implementation Research）**與**底層真實考證（Ground Truth Deep Dive）**。  
> 堅決拒絕「官方宣稱」與「社群傳聞」，堅持以官方開源代碼庫、網路封包實測與 NotebookLM 知識庫多方交叉比對，作為規格制定前之單一真實來源。

---

## 📋 技術調研矩陣總表 (Research Matrix)

| 調研文檔 | 研究領域 | 核心研究依據與來源 | 關聯規格書 | 核心技術真相與重大發現 |
| :--- | :---: | :--- | :--- | :--- |
| [**`2026-cloudflare-account-api-token-guide.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/2026-cloudflare-account-api-token-guide.md) | ☁️ 雲端身分與權限 | Cloudflare 官方文件、`workers-sdk` 開源代碼庫、2026 RBAC 體系 | 🔍 [cloudflare-edge-spec.md](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/search/cloudflare-edge-and-wrangler-master-spec.md) | 深入辨析 Account API Token 與 User API Token 之本質差異；指出無人值守 Agent 與 CI/CD 必須採用 Account API Token；釐清 R2 S3 HMAC 憑證與 REST API Token 之邊界。 |
| [**`2026-cloudflare-mcp-and-wrangler-guide.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/2026-cloudflare-mcp-and-wrangler-guide.md) | 🌐 邊緣運算與 MCP | `cloudflare/mcp`、`mcp-server-cloudflare`、Dynamic Worker Loader | 🔍 [cloudflare-edge-spec.md](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/search/cloudflare-edge-and-wrangler-master-spec.md) | 深入剖析 Code Mode 模式以 1,100 tokens 掌控 2,594 個端點的技術底層；論證 Stdio 本機啟動參數必須強制帶入 `run <account-id>` 以防止 Account ID 覆寫為 undefined。 |
| [**`2026-rag-grounding-research-report.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/2026-rag-grounding-research-report.md) | 🧠 RAG 與情報檢索 | ACL TP-RAG 論文、arXiv RAGRouter、Perplexica 源碼、NotebookLM | 🔍 [global-local-search-spec.md](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/search/global-local-search-spec.md)<br>🔍 [global-search-taxonomy-spec.md](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/search/global-search-taxonomy-and-region-spec.md) | 破解商業搜尋 API 昂貴黑盒子迷思；確立「雙軌在地與全球情報 Grounding」與「AC-4 嚴格 1對1 引文剪裁對齊演算法」，徹底杜絕模型「各說各話」與來源幻覺。 |
| [**`2026-travel-pricing-api-scraping-deep-dive.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/2026-travel-pricing-api-scraping-deep-dive.md) | 💼 交通比價與商業化 | Travelpayouts Changelog、Aviasales、GitHub `AWeirdDev/flights`、NotebookLM | 💼 [flight-pricing-spec.md](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/business/flight-pricing-and-airport-spec.md)<br>💼 [universal-affiliate-spec.md](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/business/universal-affiliate-interactive-spec.md) | 揭穿所謂「自動查價腳本」為部落格靜態 SEO 變現外掛之真相；論證現代 SPA 必須採用官方標準深層帶參直連；奠定同城起降 0ms 記憶體短路防衛原則。 |

---

## 🧠 Google NotebookLM 外部知識庫對齊

本目錄所有先導調研均於 Google NotebookLM 建立專屬深度研究筆記本進行跨文獻對齊：
- **離線秒開與 PWA 架構**: NotebookLM UUID `df7b08bd-66d2-48f0-9cac-eabeeba57869`
- **旅遊搜尋 RAG 與 Grounding**: NotebookLM UUID `b67a1904-fdc3-4c89-8e2a-3835082bf106`
- **機票即時比價與 OTA 考證**: NotebookLM UUID `13e2290f-0d80-4372-b462-9ae453337b7a`
