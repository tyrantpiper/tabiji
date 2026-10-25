# 🔬 Tabidachi 前瞻技術調研與架構深潛庫 (Research Repository)

> **定位守則 (Master Doctrine)**:  
> 本目錄專門收錄專案在引進重大第三方技術、邊緣架構與外部 API 整合前的**先導技術調研（Pre-Implementation Research）**與**底層真實考證（Ground Truth Deep Dive）**。  
> 堅決拒絕「官方宣稱」與「社群傳聞」，堅持以官方開源代碼庫、網路封包實測與 NotebookLM 知識庫多方交叉比對，作為規格制定前之單一真實來源。

---

## 🗂️ 8 大領域分類拓撲 (Domain Topology)

```text
docs/research/
├── cloud_backend/        # ☁️ 雲端身分、邊緣防護、Worker 代理與資料庫連線
├── map_geo/              # 🗺️ 向量地圖、DEM 3D 地形、空間拓撲與模擬遙測
├── ios_ui/               # 📱 iOS 原生體驗、手勢防競態、液態玻璃與微動效
├── offline_pwa/          # 📶 離線秒開、Service Worker 穿透、IndexedDB 與 IPC
├── devops_security/      # 🛡️ 零信任身分安全、依賴治理、Token 輪轉與 IDOR 稽核
├── ai_intent/            # 🧠 AI 雙階意圖路由、動態工具門控與 Grounding
├── medical/              # 💊 跨國醫療、慢病時差生理劑量與開源醫學 API
└── business_strategy/    # 💼 商業變現、補助核銷、聯盟行銷歸因與商標智財
```

---

## 📋 領域調研矩陣總表 (Full Research Matrix)

### 1. ☁️ 雲端身分與邊緣架構 (`cloud_backend/`)
| 調研檔案 | 核心主題與技術真相 |
| :--- | :--- |
| [**`2026-10-17-cloudflare-origin-rules-vs-worker-cloud-run-deep-research.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/cloud_backend/2026-10-17-cloudflare-origin-rules-vs-worker-cloud-run-deep-research.md) | Origin Rules 免費版限制 vs Worker 邊緣覆寫 Host 標頭與 Cloud Run 整合實證。 |
| [**`2026-10-17-cloudflare-zone-free-tier-advanced-features-deep-research.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/cloud_backend/2026-10-17-cloudflare-zone-free-tier-advanced-features-deep-research.md) | 免費方案進階功能上限、WAF 規則配額與 SSL/TLS 最佳實踐。 |
| [**`2026-10-17-supabase-supavisor-6543-vs-cloud-run-deep-research.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/cloud_backend/2026-10-17-supabase-supavisor-6543-vs-cloud-run-deep-research.md) | Supabase Supavisor 連線池 6543 埠無伺服器併發瓶頸與 Transaction 模式。 |
| [**`2026-cloudflare-account-api-token-guide.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/cloud_backend/2026-cloudflare-account-api-token-guide.md) | Account API Token 與 User Token 權限邊界、CI/CD 與無人值守 Agent 安全授權。 |
| [**`2026-cloudflare-domain-proxy-cloudrun-vercel-truth.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/cloud_backend/2026-cloudflare-domain-proxy-cloudrun-vercel-truth.md) | 橘雲代理下 Vercel SSL 證書驗證與 Cloud Run 轉發真實封包行為。 |
| [**`2026-cloudflare-edge-shield-and-traffic-flattening-research.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/cloud_backend/2026-cloudflare-edge-shield-and-traffic-flattening-research.md) | 邊緣流量吸震技術、Google Cloud Run 直連 404 根因與 Host Override 解決方案。 |
| [**`2026-cloudflare-mcp-and-wrangler-guide.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/cloud_backend/2026-cloudflare-mcp-and-wrangler-guide.md) | Code Mode 模式以 1,100 tokens 掌控 2,594 個端點的技術底層與 Stdio 參數配置。 |
| [**`2026-custom-domain-cloud-shield-truth-and-pitfalls.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/cloud_backend/2026-custom-domain-cloud-shield-truth-and-pitfalls.md) | 買網域真實防禦架構、Vercel 每 90 天 ACME 續簽死鎖與橘雲合體技。 |
| [**`2026-zero-cost-edge-worker-shield-vs-custom-domain.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/cloud_backend/2026-zero-cost-edge-worker-shield-vs-custom-domain.md) | Workers KV 邊緣吸震、CORS 0ms 短路、日行 10 萬次上限邊界防衛。 |

---

#### 2. 🗺️ 地圖、地理與空間運算 (`map_geo/`)
| 調研檔案 | 核心主題與技術真相 |
| :--- | :--- |
| [**`2026-10-18-google-maps-shared-list-and-poi-pool-architecture.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/map_geo/2026-10-18-google-maps-shared-list-and-poi-pool-architecture.md) | Google Maps 清單分享解析架構、零成本 POI 緩存池拓撲。 |
| [**`2026-10-19-google-maps-shared-list-and-poi-pool-industry-reality-check.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/map_geo/2026-10-19-google-maps-shared-list-and-poi-pool-industry-reality-check.md) | 逆向工程業界現狀評估、反爬蟲防禦機制與多來源降級策略。 |
| [**`2026-10-21-google-maps-internal-rpc-cloudflare-proxy-tos-reality-check.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/map_geo/2026-10-21-google-maps-internal-rpc-cloudflare-proxy-tos-reality-check.md) | Google 內部 RPC 通訊協定、ToS 合規邊界與 Cloudflare 轉發隔離。 |
| [**`2026-10-24-maplibre-3d-dem-mapterhorn-tile-404-and-overzoom-deep-research.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/map_geo/2026-10-24-maplibre-3d-dem-mapterhorn-tile-404-and-overzoom-deep-research.md) | MapLibre 3D DEM 圖磚 404 根因、Mapterhorn Overzoom 演算法與 CSP 防護。 |
| [**`opencv_frame_telemetry.json`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/map_geo/opencv_frame_telemetry.json) | 地圖幀率、視窗切換與 GPU 合成遙測數據紀錄。 |

---

### 3. 📱 iOS 體驗、手勢與動效 (`ios_ui/`)
| 調研檔案 | 核心主題與技術真相 |
| :--- | :--- |
| [**`2026-10-21-pwa-pull-to-refresh-and-gesture-competition-master-research.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/ios_ui/2026-10-21-pwa-pull-to-refresh-and-gesture-competition-master-research.md) | PWA 下拉更新與水平滑動手勢競爭仲裁、WebKit 物理彈性阻斷技術。 |
| [**`ios-modal-sheet-physics-architecture-2026.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/ios_ui/ios-modal-sheet-physics-architecture-2026.md) | iOS 原生彈簧物理底抽 (Modal Sheet) 阻尼係數與中斷手勢解法。 |
| [**`mobile-touch-scroll-gesture-disambiguation-2026.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/ios_ui/mobile-touch-scroll-gesture-disambiguation-2026.md) | 移動端捲動、長按與拖曳歧義判定演算法。 |
| [**`tabiji-dynamic-gradient-aurora-bloom-research-2026.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/ios_ui/tabiji-dynamic-gradient-aurora-bloom-research-2026.md) | 極光呼吸光暈與 OKLCH 色域動態擴散演算法。 |
| [**`tabiji-home-dashboard-architecture-bento-motion-research-2026.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/ios_ui/tabiji-home-dashboard-architecture-bento-motion-research-2026.md) | Bento Grid 卡片佈局、微動效時序與多功能看板動態整合。 |

---

### 4. 📶 離線 PWA 與本地端架構 (`offline_pwa/`)
| 調研檔案 | 核心主題與技術真相 |
| :--- | :--- |
| [**`2026-10-17-pwa-avant-garde-kill-native-app-movement-deep-research.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/offline_pwa/2026-10-17-pwa-avant-garde-kill-native-app-movement-deep-research.md) | PWA 秒開對比原生 App 效能優勢、Serwist 快取與 Standalone 視窗模式。 |
| [**`2026-10-17-pwa-permission-sandbox-and-interoperability-matrix.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/offline_pwa/2026-10-17-pwa-permission-sandbox-and-interoperability-matrix.md) | 瀏覽器權限沙盒邊界、Web Share API、地理位置與跨平台相容性矩陣。 |
| [**`2026-10-16-full-stack-i18n-architecture-research.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/offline_pwa/2026-10-16-full-stack-i18n-architecture-research.md) | 全棧多語系架構、零延遲語系切換與 SWR 離線字典整合。 |
| [**`2026-10-18-calendar-and-maps-interoperability-deep-research.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/offline_pwa/2026-10-18-calendar-and-maps-interoperability-deep-research.md) | iCalendar (.ics) 標準格式雙向同步、本機日曆與地圖深層連結對接。 |
| [**`2026-10-17-interoperability-first-byok-zero-marginal-architecture-deep-research.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/offline_pwa/2026-10-17-interoperability-first-byok-zero-marginal-architecture-deep-research.md) | BYOK (自帶金鑰) 零邊際成本架構、本機 IndexedDB 安全性與端側解密。 |
| [**`windows-cli-winerror-206-ipc-architecture-2026.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/offline_pwa/windows-cli-winerror-206-ipc-architecture-2026.md) | Windows CLI WinError 206 檔案名過長破防原理、IPC 安全跨進程通訊。 |

---

### 5. 🛡️ 資安防護、身分驗證與依賴治理 (`devops_security/`)
| 調研檔案 | 核心主題與技術真相 |
| :--- | :--- |
| [**`2026-10-22-pwa-anonymous-auth-transfer-code-and-idor-reality-check.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/devops_security/2026-10-22-pwa-anonymous-auth-transfer-code-and-idor-reality-check.md) | 匿名使用者憑證安全遷移、移轉碼時效防撞與 IDOR 越權防禦實證。 |
| [**`2026-10-24-dependabot-pr32-40-dependencies-audit-and-breakage-prevention.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/devops_security/2026-10-24-dependabot-pr32-40-dependencies-audit-and-breakage-prevention.md) | Dependabot 自動升級 PR 32~40 依賴審核、破壞性變更熔斷防線。 |
| [**`2026-10-24-token-rotation-grace-period-and-revocation-deep-research.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/devops_security/2026-10-24-token-rotation-grace-period-and-revocation-deep-research.md) | JWT Token 輪轉過渡期容錯、吊銷黑名單與並發並行請求競態防禦。 |
| [**`2026-10-17-production-architecture-vulnerability-and-competitive-audit.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/devops_security/2026-10-17-production-architecture-vulnerability-and-competitive-audit.md) | 生產架構脆弱性評估、競品安全策略審計與開源防線部署。 |

---

### 6. 🧠 AI 意圖、檢索與智能調度 (`ai_intent/`)
| 調研檔案 | 核心主題與技術真相 |
| :--- | :--- |
| [**`2026-rag-grounding-research-report.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/ai_intent/2026-rag-grounding-research-report.md) | 雙軌在地與全球情報 Grounding、AC-4 嚴格 1對1 引文剪裁對齊演算法。 |
| [**`two-stage-intent-routing-and-dynamic-tool-gating.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/ai_intent/two-stage-intent-routing-and-dynamic-tool-gating.md) | 兩階段意圖路由、動態工具門控與 Token 消耗縮減機制。 |

---

### 7. 🔬 進行中先導調研 (In-Progress Research)
| 調研檔案 | 核心主題與技術真相 |
| :--- | :--- |
| [**`2026-10-25-autonomous-edge-case-simulations-and-spec-dossier.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/2026-10-25-autonomous-edge-case-simulations-and-spec-dossier.md) | 自主邊界情況模擬、換日線 Pacific-Centered BBox 視角崩潰實測數據卷宗。 |
| [**`2026-10-25-cross-border-medical-chronopharmacology-deep-audit.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/2026-10-25-cross-border-medical-chronopharmacology-deep-audit.md) | 跨經度飛行時間醫學 (Chronopharmacology)、半衰期動態排程與海外急症雙語救援。 |
| [**`2026-10-25-free-open-source-medical-apis-and-integration-guide.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/2026-10-25-free-open-source-medical-apis-and-integration-guide.md) | 全球免費開源急症 POI、OpenStreetMap Overpass 查詢與離線急救指引整合。 |

---

### 8. 💼 商業戰略、補助、出款與智財專利 (`business_strategy/`)
| 調研檔案 | 核心主題與技術真相 |
| :--- | :--- |
| [**`2026-10-24-aaas-travel-tarpit-and-u-start-audit.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/business_strategy/2026-10-24-aaas-travel-tarpit-and-u-start-audit.md) | AaaS 旅遊焦油坑診斷、教育部 U-start 35 萬創業開辦費提領合規法規。 |
| [**`2026-yc-startup-school-taipei-application-pack.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/business_strategy/2026-yc-startup-school-taipei-application-pack.md) | Y Combinator Startup School 申請策略、創業團隊股權治理與海外擴展論述。 |
| [**`2026-travel-pricing-api-scraping-deep-dive.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/business_strategy/2026-travel-pricing-api-scraping-deep-dive.md) | 破解交通比價爬蟲迷思、深層帶參直連與 0ms 記憶體短路防衛。 |
| [**`2026_travel_architecture_benchmark_and_tools_redesign.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/business_strategy/2026_travel_architecture_benchmark_and_tools_redesign.md) | 國際頂級旅遊工具架構基準評測、核心功能重構與痛點挖掘。 |
| [**`investment_due_diligence_linkincubator_analysis_2026.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/business_strategy/investment_due_diligence_linkincubator_analysis_2026.md) | 領投機構盡職調查反查、商業可行性與技術壁壘防禦策略。 |
| [**`tabiji-ip-protection-licensing-trademark-research-2026.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/business_strategy/tabiji-ip-protection-licensing-trademark-research-2026.md) | 智慧財產權佈局、開源授權相容性與商標侵權預防指南。 |
| [**`tabiji-rebranding-trademark-github-pwa-research-2026.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/business_strategy/tabiji-rebranding-trademark-github-pwa-research-2026.md) | 品牌重構 (Rebranding)、GitHub 專案更名與 PWA 清單跨版本遷移技術。 |
| [**`universal_global_tax_refund_and_rate_actuary_dossier_2026.md`**](file:///d:/Project/Tabidachi/travel-pwa/docs/research/business_strategy/universal_global_tax_refund_and_rate_actuary_dossier_2026.md) | 全球 110+ 國退稅費率精算矩陣、手續費扣除公式與端側離線計算。 |

---

## 🧠 Google NotebookLM 外部知識庫對齊

本目錄所有先導調研均於 Google NotebookLM 建立專屬深度研究筆記本進行跨文獻對齊：
- **Cloudflare 邊緣防護罩與 Vercel / Cloud Run 流量降壓**: NotebookLM UUID `c8678e26-6915-4810-ac3c-6da18999ea0c`
- **離線秒開與 PWA 架構**: NotebookLM UUID `df7b08bd-66d2-48f0-9cac-eabeeba57869`
- **旅遊搜尋 RAG 與 Grounding**: NotebookLM UUID `b67a1904-fdc3-4c89-8e2a-3835082bf106`
- **機票即時比價與 OTA 考證**: NotebookLM UUID `13e2290f-0d80-4372-b462-9ae453337b7a`
- **海外急救與慢病時差醫學**: NotebookLM UUID `e4d7912a-3341-4790-8801-7faecb58d91a`
