# 🛡️ Security Sentinel 對抗式沙盒審計報告 (Touch-Slop Gesture Disambiguation)

> **審計日期**: 2026-10-07  
> **審計模式**: `sentinel-agy-adversarial` (物理沙盒隔離驗證)  
> **受審目標**: `frontend/components/timeline-card.tsx:dropdown_trigger` (三點編輯選單觸發器)  
> **安全台帳狀態**: 29/29 SECURE  
> **沙盒測試結果**: 5/5 PASSED (`frontend/__tests__/timeline-touch-slop.test.tsx`)  
> **型別驗證**: `tsc --noEmit` 0 錯誤  

---

## 1. 執行摘要 (Executive Summary)

本輪審計針對行動端垂直滾動行程卡牌時，手指壓在三點編輯按鈕 (`DropdownMenuTrigger`) 處向下滑動導致選單誤彈出中斷滑動之互動缺陷進行全景式沙盒驗證。
- **物理隔離審核者結論**：獨立 `runner.py` 子代理人從純安全角度評估，確認 `touch-manipulation` 屬於標準防禦，選單開閉為非破壞性狀態切換；但從互動體驗與誤觸防禦角度，Radix 原生 `onPointerDown` 在觸控下第 0 毫秒開啟選單確實存在手勢搶佔事實。
- **沙盒 PoC 證偽與校準**：在隔離測試中成功重現並化解了「桌面端滑鼠點擊閃退 (Toggle Thrashing)」與「滑動釋放後點擊冒泡至外層卡片觸發地圖跳轉」之重大邊際缺陷。
- **補丁就緒**：候選補丁與 5 項單元測試在沙盒環境已 100% 驗證通過，零降級，待人類確認後即可進行主代碼套用。

---

## 2. 威脅矩陣與沙盒驗證結果 (Attack Surface Matrix)

| 檢驗維度 | 潛在威脅 / 缺陷假說 | 沙盒證偽與驗證結果 | 最終防禦策略 |
| :--- | :--- | :--- | :--- |
| **手勢搶佔與滑動中斷** | 垂直滑動時 `pointerdown` 第 0 毫秒開啟選單，凍結列表滾動 | **已於沙盒完全阻斷** (TC-1: 位移 > 8px 選單 100% 保持關閉) | 觸控下 `preventDefault()` 阻止 Radix 原生秒開 |
| **桌面端閃退矛盾** | 受控 `open` 搭配手動 `onClick` 導致滑鼠點擊瞬間閃開秒關 | **已於沙盒完全化解** (TC-3: 滑鼠點擊放行給 Radix 原生開閉) | 嚴格依據 `pointerType` 進行觸控與滑鼠雙態分流 |
| **卡片地圖跳轉穿透** | 滑動結束時瀏覽器派發 `click`，冒泡至卡片引發地圖跳轉 | **已於沙盒完全切斷** (TC-4: 外層卡片點擊監聽器 0 觸發) | 三點按鈕 `onClick` 無條件執行 `e.stopPropagation()` |
| **橫向滑動誤觸發** | 使用者左右橫滑時誤觸發三點按鈕展開 | **已於沙盒完全阻斷** (TC-5: 水平位移 > 8px 同樣判定為滑動) | 動態計算 X 與 Y 雙軸向位移向量 |

---

## 3. 沙盒 In-Memory 測試數據

執行命令：`npx vitest run __tests__/timeline-touch-slop.test.tsx`
```text
✓ __tests__/timeline-touch-slop.test.tsx (5 tests) 196ms
  ✓ TC-1 (滑動情境): 手指垂直位移超過 8px 時，選單 100% 保持關閉
  ✓ TC-2 (輕點情境): 手指微動小於 8px (Tap) 時，選單正常展開
  ✓ TC-3 (桌面情境): 滑鼠左鍵點擊時，選單正常展開
  ✓ TC-4 (防止點擊穿透外層卡片): 滑動三點按鈕時，外層卡片 onClick 100% 不會被觸發
  ✓ TC-5 (橫向滑動情境): 手指水平位移超過 8px 時，同樣判定為滑動並阻斷選單

Test Files  1 passed (1)
Tests       5 passed (5)
```

---

## 4. 候選補丁 (Candidate Patch)

- 候選補丁檔案：[`docs/security/history/patches/patch_candidate_touch_slop.diff`](file:///d:/Project/Tabidachi/travel-pwa/docs/security/history/patches/patch_candidate_touch_slop.diff)
- 安全台帳更新：[`docs/security/security-coverage-ledger.json`](file:///d:/Project/Tabidachi/travel-pwa/docs/security/security-coverage-ledger.json)
