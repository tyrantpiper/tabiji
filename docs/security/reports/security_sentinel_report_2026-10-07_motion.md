# 🛡️ Security Sentinel 物理沙盒審計報告 (Motion & Sticky Architecture)

> **稽核模式**: `agy.exe -p --sandbox` 獨立子代理人審查 (Zero Prompt Contamination)  
> **稽核日期**: 2026-10-07  
> **驗證狀態**: 全數沙盒覆核完成 (All Targets Audited & Cleared)  

---

## 1. 執行總結 (Executive Summary)

針對即將實施的「方向 B (Sticky Blur 智慧吸頂)」與「方向 C (卡片 ➔ 地圖 Click-to-Focus 與浮動預覽膠囊)」，Security Sentinel 啟動背景獨立進程進行預防性對抗審計。

* **受審目標總數**: 4
* **已確認高危漏洞**: 0
* **證偽/安全狀態 (Dismissed / Secure)**: 3
* **前置防禦邊界標註 (Inconclusive / Pre-emptive Guard)**: 1
* **結論**: 前置架構安全無漏洞，已具備進入安全實作階段之必要防護準則。

---

## 2. 審查明細矩陣 (Findings Ledger)

| 目標組件 | 審查向量 (Vector) | 沙盒裁決 | 技術分析與防護結論 |
| :--- | :--- | :--- | :--- |
| `frontend/components/itinerary/ItineraryHeader.tsx` | `css_sticky_dom_trapping` | **DISMISSED (SECURE)** | 現行代碼未在受限容器內硬寫 sticky。審計確認實作時須將天數吸頂列獨立於滾動容器第一層，避免父層邊界截斷。 |
| `frontend/components/views/itinerary-view.tsx` | `event_injection_and_null_coordinates` | **DISMISSED (SECURE)** | 現行代碼無全域未過濾事件。實裝之事件管道將嚴格落實 `parseFloat` 與 `isNaN` 防禦，杜絕坐標污染。 |
| `frontend/components/day-map.tsx` | `webgl_context_unready_race` | **DEFENSIVE GUARD** | 標註相機調用競態防禦點：實作時必須前置防禦 `if (!mapRef.current \|\| !mapLoaded) return`。 |
| `frontend/components/timeline-card.tsx` | `gesture_propagation_collision` | **DISMISSED (SECURE)** | 按鈕選單已具備 `onPointerDown={(e) => e.stopPropagation()}` 與 `onClick` 雙重隔離，卡片點擊聚焦不影響 DnD 與選單。 |

---

## 3. 實作安全邊界規範 (Pre-Implementation Guardrails)

為確保實作達成 100% 零降級與零崩潰，`@dev` 必須遵守以下 3 大防禦規範：

1. **坐標過濾三道防線 (Coordinate Triple-Check)**:
   ```typescript
   const lat = typeof rawLat === 'string' ? parseFloat(rawLat) : rawLat;
   const lng = typeof rawLng === 'string' ? parseFloat(rawLng) : rawLng;
   if (!lat || !lng || isNaN(lat) || isNaN(lng)) return;
   ```
2. **地圖實例生命週期防護 (Map Lifecycle Guard)**:
   呼叫 `flyTo` 前必須確認 MapLibre 引擎已完成首幀渲染：
   ```typescript
   if (!mapRef.current || !mapLoaded) return;
   ```
3. **滾動隔離 (Scroll Isolation)**:
   平滑滾動必須限定於 `scrollerEl` 局部容器，禁止引發全域 `window.scrollTo` 導致 iOS Safari 導航欄抖動。
