# 📅 Daily Report - 2026-10-13 (Commercialization Milestone, TIPO Dual-Mark Filing & Paris Convention Moat)

> **系統狀態**：🟢 Production Deployed & Synced, TIPO Trademark Phase 1 Filed (`Tabiji 旅路` + Color App Icon), Paris Convention 6-Month Priority Clock Active (`2026-10-13` ~ `2027-04-13`), 0 TypeScript Errors, 0 ESLint Warnings, 100% Tests Green (Frontend 65/65 Suites Passing, 437/437 Tests Passing; Backend 135/135 Tests Passing), Working Tree 100% Clean, GitHub main branch synced (`12dfb47`).  
> **今日關鍵提交串列 (Full Day Commit Stream)**：
> - [`12dfb47`](https://github.com/tyrantpiper/tabiji/commit/12dfb47) `docs(trademark): archive TIPO filing docket and commercialization moat` (2026-10-13 02:18:00 +0800)

---

## 🏆 深度專案復盤：四大商業化與工程里程碑 (Four Core Milestones)

本日完成 Tabiji 從「代碼開源與產品交付」邁向「商業化實體法律確權」的最重要里程碑。成功於經濟部智慧財產局（TIPO）完成核心雙案送件，搶下法定在先申請日並啟動跨國優先權時鐘：

---

### 里程碑一：TIPO e 網通雙案並行送件 ✕ 數位軟體核心三類別全量覆蓋
1. **業務挑戰與戰略佈局**：
   - Tabiji 專案已在線上穩定運行（tabijiapp.com），並於 GitHub 具備廣泛代碼開源曝光，面臨「品牌名稱被惡意搶註」與「App Store / Google Play 圖示與視覺外觀遭到競品抄襲擦邊」之高風險。
   - 經 `/Idea to Spec` 與 `/grill-me` 深度梳理，確立拒絕單一薄弱防禦，採「互補性雙案並行架構」：
     - **第一案（主品牌文字商標）**：`Tabiji 旅路`，採用中英複合純文字標樣，以墨色申請取得最廣排他權。
     - **第二案（彩色 App Icon 圖形商標）**：旭日回眸旅人 t 字路標樣，直接鎖定手機桌面圖示與商店第一門面。
2. **尼斯分類 12 版標準商品詞清冊（零補正設計）**：
   - 嚴格指定三大核心類別（每類 5~7 項，完全在 20 項免加徵規費門檻內）：
     - **第 09 類（電腦軟體/App）**：`電腦軟體（可下載）`、`行動電話用應用軟體（可下載）`、`旅行行程規劃用電腦程式`、`具備人工智慧功能之旅遊路線規劃軟體`、`電子地圖資料庫軟體`、`電子憑證管理軟體`、`全球衛星定位系統（GPS）接收軟體`。
     - **第 42 類（SaaS 雲端平台）**：`軟體即服務（SaaS）`、`雲端運算服務`、`行程生成人工智慧演算法之雲端託管服務`、`電腦軟體設計、維護與線上諮詢`、`提供線上不可下載之旅遊行程資料庫檢索平台`。
     - **第 39 類（旅遊行程導航）**：`旅遊行程安排服務`、`旅遊導航路線規劃服務`、`旅客運輸之路線導引資訊提供`、`代訂機票、火車票及交通工具租賃服務`、`透過網際網路提供之即時旅遊交通資訊`。
   - **規費最優化**：每類享有電子送件折抵 NT$ 600 優惠，2 案 × 3 類 × NT$ 2,400 = **NT$ 14,400**，成功完成線上繳納並取得收文文號。

---

### 里程碑二：鎖定台灣法定在先申請日 ✕ 巴黎公約 6 個月國際優先權時鐘
1. **法定時戳固化 (Filing Date Anchor)**：
   - 創辦人 Ryan Su 以本國自然人名義於 **2026-10-13** 正式完成電子送件與繳費，依法取得當日作為「在先申請日」。
   - 在先申請原則下，自今日起任何第三方提出相同或近似之軟體/行程申請，智財局將予以全數駁回。日後公司設立完成，得直接以受讓人身分無縫辦理商標移轉。
2. **巴黎公約國際優先權時鐘 (Paris Convention Priority Window)**：
   - 依據《保護工業產權巴黎公約》第 4 條，自台灣申請日起算 6 個月內：
   - **優先權有效期間**：**`2026-10-13` 至 `2027-04-13`**。
   - **戰略主動權**：若專案於半年內進軍日本市場（向特許廳 JPO）或美國市場（向 USPTO）送件，得依法主張以 2026-10-13 為海外申請日，徹底杜絕跨國搶註。

---

### 里程碑三：破解 TIPO 電子送件三大行政謎團與標樣轉化管線
1. **行政謎團破譯 (TIPO Operational Mechanics)**：
   - **謎團一：手寫簽名圖檔之法律定位**：手寫簽名圖檔並非 PKI 加密私鑰，但在 TIPO 新版系統中屬於「留存簽章（印鑑卡數位化）」；會員註冊時上傳手寫簽名，送件時系統在後端比對同一檔案影像特徵，達成免讀卡機、免申辦硬體憑證之合法線上送件。
   - **謎團二：電子收據清單寄送地址疑慮**：系統顯示之「寄送地址」為郵局臨櫃劃撥或退信時之備用防呆；線上信用卡繳費者 100% 由「電子收據寄送信箱」以 Email 發送法律效力 PDF，不會寄發紙本收據。
   - **謎團三：實體信件到底會寄什麼**：4~6 個月審查核准後，燙金正本之實體《商標註冊證》將以郵局掛號信寄達通訊地址。
2. **TIPO 300 DPI 墨色圖樣轉換管線**：
   - 針對原始深色背景/白線向量圖（若直接上傳白底系統會導致筆畫隱形或限縮為特殊底色），建立 Python Pillow 轉換管線：
   - 產出白底黑線標準圖檔 [`docs/legal/trademark/tipo_assets/dossier_03_person_device_mark.png`](file:///d:/Project/Tabidachi/travel-pwa/docs/legal/trademark/tipo_assets/dossier_03_person_device_mark.png) 與 [`dossier_app_icon_color.png`](file:///d:/Project/Tabidachi/travel-pwa/docs/legal/trademark/tipo_assets/dossier_app_icon_color.png)，兼顧色彩純淨度與法律保護最大化。

---

### 里程碑四：法律資產 Git 存證閉環 ✕ 全棧品質守門零降級
1. **不可篡改法律資產存證 (Immutable Legal Ledger)**：
   - 全套商標卷宗、著作權原創底稿鏈路存證、三幕開屏動態商標 6 格時間戳分解圖（0.0s~1.8s）與 300 DPI 送件資產全量收納於 `docs/legal/trademark/`，並在 Commit [`12dfb47`](https://github.com/tyrantpiper/tabiji/commit/12dfb47) 固化上鏈。
2. **全量品質守門驗證 (Quality Gates Invariance)**：
   - 前端 TypeScript `npx tsc --noEmit` 保持 0 錯誤。
   - 前端 Vitest：65 個測試套件、**437 個測試全數綠燈**。
   - 後端 Pytest：27 個測試模組、**135 個測試全數綠燈**。
   - 根目錄保持絕對整潔（Zero-Root-Pollution），工作樹純淨度 100%。

---

## 🏛️ 架構決策紀錄 (Architecture Decisions Added)

### 決策 12：商業化確權、商標護城河與巴黎公約國際優先權架構
- **雙案互補性確權架構 (Complementary Dual-Mark Moat: Word + App Icon)**：在數位軟體與 PWA 領域，單純文字無法壟斷手機桌面第一眼之視覺門面，而單純圖形無法阻擋競品以同音/文字擦邊。架構上確立 Phase 1「純文字墨色標樣（Tabiji 旅路）＋ 彩色具象圖形（旭日旅人 t 字路 App Icon）」雙案並行，分別涵蓋尼斯分類第 09 類（電腦軟體/App）、第 42 類（SaaS 雲端平台）與第 39 類（旅遊行程導航）。文字案取得全色系最廣排他權，彩色圖形案直接鎖定 App Store 與手機桌面侵權檢舉之絕對防禦。
- **法定在先申請日鎖定與巴黎公約 6 個月時鐘 (Filing Date Anchor & Paris Convention Priority Clock)**：創辦人以本國自然人名義於 2026-10-13 正式完成經濟部智慧財產局（TIPO）電子送件並繳費，鎖定台灣法定在先申請日。此動作正式啟動《保護工業產權巴黎公約》第 4 條之 6 個月國際優先權期間（至 2027-04-13 止），日後拓展日本專利商標局（JPO）或美國（USPTO）時，得依法主張以台灣送件日為其國際申請日。
- **標準商品詞零補正與手寫留存簽章機制 (Standard Taxonomy Zero-Office-Action & Signature Anchor)**：全量採用 TIPO 官方公告之標準尼斯分類詞彙（每類 5~7 項，杜絕超額加徵與人工補正公文）。電子送件採系統留存手寫簽名影像檔驗證身分，正式商標註冊證與公文將以實體掛號郵寄至通訊地址，電子規費收據則無紙化直接寄送 Email。

---

## 🛡️ 今日避坑指南 (Failed Paths & Hard Lessons)

1. **手寫簽名圖檔與電子簽章私鑰之混淆陷阱**：
   - *現象*：初期誤以為手寫簽名圖檔可直接作為《電子簽章法》的 PKI 非對稱加密公私鑰憑證使用。
   - *教訓*：手寫簽名為視覺點陣圖，無法透過加密演算法計算檔案 Hash。TIPO 系統實務上是透過「會員中心留存印鑑」與「線上送件比對同一影像」提供替代途徑；若欲接收加密電子公文，未來仍需以自然人憑證或軟體憑證（`.pfx`）升級。
2. **商標圖樣透明底與深色底之審查陷阱**：
   - *現象*：原始 App 標樣為暗色模式或透明底白線，若直接上傳 TIPO 系統，在預設白底預覽中線條將完全隱形，或被審查官誤判為「以特定深色作為商標背景的一部分」，大幅限縮商標保護範圍。
   - *教訓*：商標申請之墨色保護一律採用「白底黑線（RGB 0,0,0 on 255,255,255）」高解析度 300 DPI 圖樣，方能取得最完整、不限背景色彩之全光譜排他權。

---

## 🔴 技術債與後續待辦 (Technical Debt & Next Steps)

1. **Phase 1 案件官方文號追蹤**：
   - 待收取 TIPO 電子收據與公文收文文號後，將 9 碼申請案號登記回 [`docs/legal/trademark/trademark_filing_dossier.md`](file:///d:/Project/Tabidachi/travel-pwa/docs/legal/trademark/trademark_filing_dossier.md)。
2. **巴黎公約優先權日曆標記**：
   - 關注 2027 年 4 月 13 日國際優先權截止日，於 2027 年 Q1 評估日本市場迴響與 JPO 送件規劃。
3. **Phase 2 旗艦周邊儲備（6~12 個月）**：
   - 配合實體背包樣品、手帳印製或募資計畫，推進第 18 類（後背包/旅行箱）、第 16 類（手帳/印刷地圖）及案卷 4（三幕開屏動態商標）送件。
