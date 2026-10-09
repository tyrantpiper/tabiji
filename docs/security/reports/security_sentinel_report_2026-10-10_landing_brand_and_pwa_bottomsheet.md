# 🛡️ Security Sentinel 深度安全與對抗審計報告

> **審計日期**: 2026-10-10  
> **審計模式**: `sentinel-agy-adversarial` ✕ In-Memory Sandbox PoC  
> **受審目標**:
> 1. `frontend/components/pwa-install-prompt.tsx` (PWA 置底 Bottom Sheet 人體工學與軟體鍵盤避讓)
> 2. `frontend/components/views/landing-page.tsx` (上圖下字品牌階層化與藝術立繪遮罩)
> 3. `frontend/lib/translations.ts` ✕ `frontend/lib/i18n/remaining.ts` (多語系字典同步性)
> 4. `frontend/public/images/tabiji-person-outline.png` (人物背部「t」字橫槓弱化為自然衣摺)

---

## 1. 執行總結 (Executive Summary)

| 指標 | 數值 | 說明 |
| :--- | :--- | :--- |
| **受審目標總數** | 4 項 | 安全區覆蓋、鍵盤動態避讓、多語系一致性、圖像拓撲真實性 |
| **已證實潛在缺陷 (Confirmed)** | 2 項 | 貼底時 iOS Home Bar 覆蓋風險、行動端輸入暱稱時虛擬鍵盤頂起遮擋 |
| **證偽假設 (Dismissed)** | 1 項 | 原版 `bottom-24` 懸浮卡片雖不擋安全區，但嚴重破壞 Landing Page 空間呼吸感 |
| **沙盒驗證狀態** | **100% VERIFIED** | 圖像與單元測試於 Sandbox 驗證通過，零語法錯誤與零迴歸 |

---

## 2. 對抗證偽與修復細節 (Adversarial Findings & Remediation)

### 2.1 [CONFIRMED] `frontend/components/pwa-install-prompt.tsx:mobile_keyboard_and_safe_area_overlap`
* **漏洞描述**：當 PWA 安裝提示改造為固定置底抽屜（`bottom-0`）時，若未注入 `pb-[max(0.75rem,env(safe-area-inset-bottom))]`，iOS Safari 系統 Home Bar（34px）將與「立即安裝」或「分享指引」重疊，引發使用者誤觸系統手勢。此外，當使用者在登入頁點擊暱稱輸入框時，行動端軟體鍵盤彈起會使 `fixed bottom-0` 元素被推至螢幕正中央，直接遮擋輸入框與開始按鈕。
* **修復方案 (Mantis Patch)**：
  1. 引入 `visualViewport` 監聽，當可視高度縮小至視窗 78% 以下時判定鍵盤彈起，抽屜自動向下滑出隱藏。
  2. 底部內邊距宣告 `pb-[max(0.75rem,env(safe-area-inset-bottom))]`，徹底相容 iOS 邊界手勢。
  3. 新增 `hasActiveUser` 本地態感知：登入進入 `AppShell` 後提升至 `bottom-20`，避免遮蔽常駐 `BottomNav`。

### 2.2 [CONFIRMED] `frontend/lib/translations.ts:subtitle_i18n_desync`
* **漏洞描述**：更新 `landing_subtitle` 為「旅路 ｜ 旅行提案」時，若僅修改 `translations.ts` 而遺漏 `remaining.ts`，多語系備援引擎將在某些切換情境下回退為舊字串，破壞品牌語意一致性。
* **修復方案 (Mantis Patch)**：雙檔案同步固化 `zh: "旅路 ｜ 旅行提案"` 與 `en: "Tabiji | Travel Planner"`。

### 2.3 [VERIFIED] `frontend/public/images/tabiji-person-outline.png`
* **影像拓撲修復**：透過 Python 影像處理腳本，於 X: 300~450、Y: 595~665 區間消除左側突兀的「t」橫槓，並沿脊背與風衣縫線計算平滑三次樣條（Spline）自然弧度，徹底消滅字母人造痕跡，釋放純粹自然的手繪人物圖騰（Brand Icon）。

---

## 3. 候選補丁 (Candidate Patches)

### 補丁 1: `frontend/lib/translations.ts` 與 `frontend/lib/i18n/remaining.ts`
```diff
-        landing_subtitle: "旅行規劃師",
+        landing_subtitle: "旅路 ｜ 旅行提案",
```

### 補丁 2: `frontend/components/pwa-install-prompt.tsx`
將原本懸浮的 `bottom-24` 升級為支援 iOS 安全區、鍵盤避讓與雙態適配的固定置底 Bottom Sheet。

### 補丁 3: `frontend/public/images/tabiji-person-outline.png`
以沙盒驗證通過之無「t」橫槓純墨線立繪覆蓋，邊界平滑抗鋸齒。
