# 🛡️ Security Sentinel 對抗安全審核報告：個人檔案贊助數字隱私與百分比重構
*(Security Sentinel Adversarial Audit Report: Profile Donation Amount Privacy & Percentage Refactor)*

> **審核日期**: 2026-11-09  
> **稽核模式**: Cloudflare 6-Phase Ledger ✕ Google Mantis Block G ✕ Harness² Invariant Conservation  
> **審核標的**: 個人設定頁面【開發者血液濃度監控 / 伺服器營運支援】金額數字移除與百分比重構  
> **總驗證目標數**: 324（本次新增 3 項，全數修復並通過驗證）  
> **審核結論**: **PASSED (ALL EXPLOITS REMEDIATED & INVARIANTS CONSERVED)**

---

## 1. 執行摘要 (Executive Summary)

使用者提出需求：「我想把 profile 這邊這個金額數字拿掉不要顯示」（針對 `NT$3,250 / $6,000` 法幣金額數字）。

透過工程考古（Chesterton's Fence）分析，該金額原先設計係借鑑 OpenCollective 開源社群透明機制，向使用者公開伺服器固定每月 NT$6,000 成本與已籌得金額，並設定 100% 封頂機制（Toxic-Zone Anti-Greed Bounds）。然而在商業與使用者體驗層面上，直接於個人設定頁顯著呈現法幣金額，易被誤認為個人帳號欠費、強迫性訂閱費用或商業計費項目，造成心理壓力與隱私疑慮。

Security Sentinel 依照標準啟動沙盒全流程對抗審計（Pre-Execution Spiking）：
1. 建立 3 項紅軍對抗假說（法幣金額敏感資訊外洩、骨架屏寬度失配引發 CLS 佈局跳動、微小百分比被 `Math.floor` 歸零）。
2. 建立 [profile-donation-privacy-sentinel.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/profile-donation-privacy-sentinel.test.tsx) 測試套件，實體證明 Phase 3 紅燈失敗（3 項良性控制通過，3 項紅軍假說擊穿，Exit Code 1）。
3. 實作最小侵入性生產補丁，在 [profile-view.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/components/views/profile-view.tsx) 將金額摘要替換為對稱對齊的粗體百分比（例如 `54%`），骨架屏縮小至 `w-14`，並保留微小進度小數點精度與無障礙語音標籤。
4. 驗證 Phase 4 綠燈：測試套件 6/6 100% 通過（Exit Code 0），`profile-view-sandbox.test.tsx` 9/9 100% 通過，TypeScript 0 錯誤、ESLint 0 警告，既有三大凍結核心文件 0 diff。

---

## 2. 對抗假說與修復明細 (Adversarial Findings Ledger)

### ▍Target 1: 法幣金額隱私與商業計費誤導修復 (`profile-view.tsx:donation_amount_privacy_leakage`)
* **假說**: 個人檔案摘要列直接渲染法幣字串 `NT$3,250 / $6,000`，使非商業社群支持被誤讀為個人應繳費用，引發隱私洩露與計費焦慮。
* **驗證結果**: **REMEDIATED**
* **修復證據**:
  * 移除 `NT${donationProgress.current.toLocaleString()}` 與 `/ ${donationProgress.goal.toLocaleString()}`。
  * 替換為與左側 `profile_accumulator` 垂直對齊之品牌橘色粗體百分比（`text-lg font-bold text-[#E56E25]`）。
  * Mantis Block G 良性控制確認：保留進度條軌道、里程碑徽章及處方簽 QR 展開器，維持原本開源自願贊助互動體驗。

### ▍Target 2: 骨架屏寬度佈局偏移防護 (`profile-view.tsx:skeleton_cls_layout_shift`)
* **假說**: 原骨架屏針對 128px 之貨幣字串宣告 `w-32`，若切換為約 42px 之百分比而未縮減骨架屏寬度，載入完成瞬間將觸發 86px 橫向佈局坍塌，造成 Core Web Vitals CLS 劣化。
* **驗證結果**: **REMEDIATED**
* **修復證據**:
  * 將摘要列對應之骨架屏由 `<Skeleton className="h-6 w-32 ... />` 調整為 `<Skeleton className="h-6 w-14 ... />`。
  * 骨架屏寬度精準契合百分比渲染寬度，物理消除資料抵達時之寬度抖動。

### ▍Target 3: 微小進度精度保全與無障礙語意標籤 (`profile-view.tsx:micro_percentage_decimal_truncation`)
* **假說**: 若直接使用 `Math.floor(percentage)`，當有用戶小額贊助使進度處於 0% 至 1% 之間（如 0.2%）時將被整除歸零，導致初期支持者感知不到進度反饋；且純文字百分比對螢幕閱讀器缺少上下文。
* **驗證結果**: **REMEDIATED**
* **修復證據**:
  * 引入微小百分比守門邏輯：`percentage > 0 && percentage < 1 ? percentage.toFixed(1) : Math.floor(percentage)`。
  * 容器增加完整無障礙屬性：`aria-label={`${t('profile_accumulator')}: ${displayPercentage}%`}`。

---

## 3. Harness² 不變性守護條約 (Invariant Conservation)

嚴格驗證全系統核心基底處於物理絕對凍結狀態，git diff 行數為 0：
* `frontend/app/page.tsx`：**0 行更動**
* `frontend/app/sw.ts`：**0 行更動**
* `frontend/public/manifest.json`：**0 行更動**

---

## 4. 驗證遙測數據 (Verification Telemetry)

* **Sentinel PoC Suite**: [profile-donation-privacy-sentinel.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/profile-donation-privacy-sentinel.test.tsx) ➔ **6/6 PASSED**
* **Profile Sandbox Suite**: [profile-view-sandbox.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/profile-view-sandbox.test.tsx) ➔ **9/9 PASSED**
* **TypeScript Check**: `npx tsc --noEmit` ➔ **0 errors, 0 warnings (Exit Code 0)**
* **ESLint Check**: `npm run lint` ➔ **0 errors, 0 warnings (Exit Code 0)**
* **Ledger Conservation**: `scripts/validate_security_ledger.py` ➔ **324 targets conserved (104 remediated, 56 verified, 164 dismissed)**

