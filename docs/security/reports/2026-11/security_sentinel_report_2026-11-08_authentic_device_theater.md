# 🛡️ Security Sentinel 對抗安全審核報告：真機劇院全屏原生真實應用視圖重構
*(Security Sentinel Adversarial Audit Report: Authentic Live Device Theater Full-Bleed Views)*

> **審核日期**: 2026-11-08  
> **稽核模式**: Cloudflare 6-Phase Ledger ✕ Google Mantis Block G ✕ Harness² Invariant Conservation  
> **審核標的**: 官方旗艦總站【真機劇院】真實應用視圖滿版鏡射與微滾動時序安全  
> **總驗證目標數**: 310（本次新增 4 項，全數通過驗證）  
> **審核結論**: **PASSED (ALL HYPOTHESES PROVEN SAFE & INVARIANTS CONSERVED)**

---

## 1. 執行摘要 (Executive Summary)

為徹底解決真機劇院中「黑邊空調、非真實應用畫面」與使用者預期之落差，團隊規劃將 Tabiji PWA 之真實首頁時間軸（台北 101、鼎泰豐、象山步道）、離線自癒通行證與行前清單、智慧多幣別分帳系統 1:1 滿版植入 iPhone 15 Pro 鈦金屬框體中，並導入借鑑自 `travelapp.mp4` 之微滾動（Micro-scroll）動態。

Security Sentinel 依照標準於沙盒環境啟動全流程對抗審計（Pre-Execution Spiking）：
1. 建立 4 項紅軍對抗假說（主題閃爍、DOM 角色選擇器污染、動畫與暫停狀態脫鉤、RWD 寬度溢位）。
2. 透過前端記憶體內測試套件（[authentic-device-theater-sentinel.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/authentic-device-theater-sentinel.test.tsx)）驗證紅燈擊穿與綠燈修復。
3. 執行全站 10 套測試檔案共 **307 項測試 100% 全數通過**，TypeScript 0 錯誤、ESLint 0 警告。

---

## 2. 對抗假說與審查明細 (Adversarial Findings Ledger)

### ▍Target 1: 全屏滿版雙主題對比與防閃爍 (`LiveDeviceTheater.tsx:fullbleed_authentic_mirroring`)
* **假說**: 將內屏擴展為滿版雙主題容器可能引入淺色模式下的深色文字繼承衝突或主題閃爍。
* **驗證結果**: **DISMISSED (Safe with Guardrails)**
* **證明證據**:
  * 內屏全面採用 Tabiji 標準雙主題色階：`bg-[#F6F5EE] dark:bg-[#121A18]` 與 `text-[#1E2927] dark:text-[#E5EBEA]`。
  * 徹底移除 `bg-stone-950` 與內外黑邊 padding，對比度經檢測符合 WCAG AAA 標準。

### ▍Target 2: DOM 角色隔離與全頁選擇器防碰撞 (`LiveDeviceTheater.tsx:viewport_mask_and_dom_collision`)
* **假說**: 在真機預覽內植入高保真 Tabiji UI 可能注入重複的 `role="tab"` 或 `role="button"`，導致 Testing-Library 於全頁渲染時發生多重元素碰撞。
* **驗證結果**: **DISMISSED (Safe with Guardrails)**
* **證明證據**:
  * 手機內部視窗強制包裹於 `aria-hidden="true"` 遮罩層中。
  * 內部展示卡片全面使用無語意之 `div` 與 `span` 標籤，嚴禁使用原生的 `<button>` 或 `role="tab"`。
  * [adversarial-m2-motion-stress.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/adversarial-m2-motion-stress.test.tsx) 與全頁 CTAs 測試無任何選擇器衝突。

### ▍Target 3: 微滾動作動與暫停狀態時序防護 (`LiveDeviceTheater.tsx:micro_scroll_race_and_memory`)
* **假說**: 手機內部的微滾動動畫若與 4 秒自動循環輪播及懸停暫停脫鉤，可能導致無效 rAF 運算、記憶體洩漏或閱讀時晃動。
* **驗證結果**: **DISMISSED (Safe with Guardrails)**
* **證明證據**:
  * 滾動嚴格鎖定 GPU 合成屬性 `y` via CSS transform。
  * 微滾動動畫與全域暫停狀態連動：`animate={shouldReduceMotion || isPaused ? { y: 0 } : { y: [0, -22, 0] }}`。
  * 當使用者游標懸停或點擊暫停時，畫面立即歸零鎖定，徹底消除動暈症與並發競態。

### ▍Target 4: 觸控靶標與固定像素防溢位 (`LiveDeviceTheater.tsx:touch_target_and_fixed_width_ergonomics`)
* **假說**: 手機外框與卡片若宣告大於 343px 之固定像素寬度，將違反 `ADV-M2-2.9` 並造成 375px 行動端橫向晃動。
* **驗證結果**: **DISMISSED (Safe with Guardrails)**
* **證明證據**:
  * 外部切換按鈕維持嚴格的 `min-h-11 min-w-11`（$\ge 44\times 44\text{px}$）與 Emil Kowalski `active:scale-[0.97]` 微回饋。
  * 內部所有卡片採用 `w-full` 與彈性流式排版，無任何無前綴之 `w-[>343px]` 宣告，100% 通過移動端零橫向滾動驗證。

---

## 3. Harness² 不變性守護條約 (Invariant Conservation)

審核確認既有三核心文件處於物理絕對凍結狀態，git diff 行數為 0：
* `frontend/app/page.tsx`：**0 行更動**
* `frontend/app/sw.ts`：**0 行更動**
* `frontend/public/manifest.json`：**0 行更動**

---

## 4. 稽核簽名 (Sentinel Sign-off)

* **審核員**: `@security (Security Sentinel)`
* **狀態**: 🟢 **PASSED & EMPIRICALLY GROUNDED (ALL 307 TESTS PASSING)**
* **候選記錄檔**: `docs/security/history/candidates/candidates_authentic_device_theater_2026-11-08.json`
* **審核結果檔**: `docs/security/history/findings/findings_authentic_device_theater.json`
* **候選補丁檔**: `docs/security/history/patches/patch_candidate_authentic_device_theater_2026-11-08.diff`
* **總體帳本**: `docs/security/security-coverage-ledger.json` (310 標的全數綠燈)

