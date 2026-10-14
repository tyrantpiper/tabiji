# 實作計畫：Tabiji UI 分享元資料與 Supabase 推播系統品牌遷移 (Implementation Plan)

## 📌 任務背景
依據 `/Idea to Spec` 與 `/grill-me` 訪談結果，將外部行程分享頁面 (PublicTripView)、社群分享標題 (ShareButton)、以及 Supabase Web Push 推播通知體系（Service Worker 預設標題、postMessage 通訊、廣播維護腳本）全面升級對齊為 **`Tabiji 旅路`**，並建立雙軌相容層防止已安裝 PWA 老用戶斷裂。

規格書參照：[`tabiji-ui-metadata-and-push-rebranding-spec.md`](file:///d:/Project/Tabidachi/travel-pwa/docs/specs/branding/tabiji-ui-metadata-and-push-rebranding-spec.md)

---

## 🎯 變更清單與執行步驟

### Phase 1: UI 對外分享與元資料更新
1. **[`frontend/app/share/[shareCode]/PublicTripView.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/app/share/[shareCode]/PublicTripView.tsx)**:
   - 將頁尾 `<p>由 Tabidachi 旅立ち 提供技術支援</p>` 替換為 `<p>由 Tabiji 旅路 提供技術支援</p>`。
2. **[`frontend/app/share/[shareCode]/page.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/app/share/[shareCode]/page.tsx)**:
   - 將 `title: '行程不存在 | Tabidachi 旅立ち'` 替換為 `title: '行程不存在 | Tabiji 旅路'`。
   - 將 `title: `${trip.title} | Tabidachi 旅立ち`` 替換為 `title: `${trip.title} | Tabiji 旅路``。
3. **[`frontend/components/itinerary/ShareButton.tsx`](file:///d:/Project/Tabidachi/travel-pwa/frontend/components/itinerary/ShareButton.tsx)**:
   - 將 `title: `${tripTitle} | Tabidachi`` 替換為 `title: `${tripTitle} | Tabiji 旅路``。

### Phase 2: Supabase 推播與 Service Worker 雙軌相容升級
4. **[`frontend/app/sw.ts`](file:///d:/Project/Tabidachi/travel-pwa/frontend/app/sw.ts)**:
   - BackgroundSyncPlugin 標籤改為 `"tabiji-offline-mutations"`。
   - 推播 fallback 標題設為 `data.title || "Tabiji 旅路"`。
   - 點擊通知跳轉派發訊息升級為 `client.postMessage({ type: "TABIJI_PUSH_NAVIGATE", url: link })`。
5. **[`frontend/lib/hooks/useDeepLinkRouter.ts`](file:///d:/Project/Tabidachi/travel-pwa/frontend/lib/hooks/useDeepLinkRouter.ts)**:
   - 擴充推播跳轉判定為**雙軌相容**：
     ```typescript
     const isPushNavigate =
       (event.data?.type === "TABIJI_PUSH_NAVIGATE" || event.data?.type === "TABIDACHI_PUSH_NAVIGATE") &&
       event.data?.url;
     ```
6. **[`frontend/lib/hooks/usePushNotifications.ts`](file:///d:/Project/Tabidachi/travel-pwa/frontend/lib/hooks/usePushNotifications.ts)**:
   - 派發事件升級為 `"tabiji-push-status-change"`。
   - 同時監聽新舊事件以達平滑過渡。
7. **[`scripts/broadcast.ps1`](file:///d:/Project/Tabidachi/travel-pwa/scripts/broadcast.ps1)**:
   - 更新標題與控制台日誌輸出為 `Tabiji 旅路`。

### Phase 3: 自動化測試與型別守門驗證
8. **更新與擴充單元測試**:
   - [`frontend/__tests__/push-notifications.test.ts`](file:///d:/Project/Tabidachi/travel-pwa/frontend/__tests__/push-notifications.test.ts)
   - [`frontend/__tests__/deep-link-router.test.ts`](file:///d:/Project/Tabidachi/travel-pwa/frontend/__tests__/deep-link-router.test.ts)
9. **品質守門**:
   - 執行 `npx tsc --noEmit`
   - 執行 `npm run test`

---

## ⚠️ 風險評估與回滾策略
- **風險**: 舊版已安裝 PWA 在離線或未重啟前，點擊通知無法喚醒路由。
- **緩解**: Phase 2 第 5 點採用雙軌條件 `(type === 'TABIJI_PUSH_NAVIGATE' || type === 'TABIDACHI_PUSH_NAVIGATE')`，經單元測試驗證，新舊客戶端完全零斷裂。
