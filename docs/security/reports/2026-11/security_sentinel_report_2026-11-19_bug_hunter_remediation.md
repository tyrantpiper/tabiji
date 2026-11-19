# 🛡️ Security Sentinel 對抗式稽核與五大線上環境修復實證報告 (2026-11-19)

> **Baseline Commit**: `1fa192e` (`main`)
> **Audit Mode**: Live 5-Cloud Grounding + `runner.py` (`--mode duel` & `--mode adaptive`) + Sandbox Pytest/Vitest + Mantis Block G
> **Ledger Totals**: `408` targets (`181` remediated, `53` verified/unresolved, `174` dismissed/safe)
> **Unified Patch**: [`docs/security/history/patches/patch_candidate_bug_hunter_2026-11-19.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_bug_hunter_2026-11-19.diff)

---

## 1. 五大線上真實部署環境實證與目標對應 (Live Baseline Findings)

| 服務層 | 線上實測證據 (`1fa192e` 部署前) | 對應修復軌 (T1–T9) |
|---|---|---|
| **Supabase** (`oudnkmigfueuyvxqpqwn`) | `public.notifications` (`1743` 筆 / `51` 已讀，最後已讀停在 `2026-09-20`) 受 `auth.uid()` RLS 阻斷；`push_subscriptions` 依賴可偽造 `x-user-id`；`itinerary_items` 缺 `address` 欄；缺 `agent_fallback_tasks` 表與 `shift_trip_capsules` RPC；`webhook_cleanup_cloudinary` 缺 Mapillary 引用計數且未掛載至 `trip_capsule_entries`。 | T1, T2, T5, T6, T7c, T8, T9 |
| **Cloudflare** (`tabijiapp-edge-shield`) | `/api/geocode/search` 快取鍵僅含 `q`、`bbox`、`country`，缺 `v=2`、`lat`/`lng`、`region`、`trip`、`locale`、`limit` 且未繞過 `X-Gemini-Key`/`X-Gemini-API-Key`。 | T3 |
| **Cloud Run** (`antigravity-backend`) | `capsules.py` 未查詢 `trip_members`；`users.py` `.single()` 0-row 例外風險；`poi.py` 無 Key 回 `400` 阻斷免費 Wiki；`agents.py` 記憶體字典跨實例遺失與缺 `key_hash` 驗證；`model_manager.py` 缺乏串流思考/文字進度回報。 | T1, T5, T6, T7, T9 |
| **Vercel** (`www.tabijiapp.com` / `travel-pwa-five.vercel.app`) | `NotificationBell`/`usePushNotifications` 直連 Supabase 遭 RLS/冷啟動失敗；`useTripRealtime` 依賴被擋之 `postgres_changes`；`day-map`/`FullscreenMapModal` L2 失敗清光 L1；`CapsuleUnveilingCeremony` 遺失 Day 0 / 狀態未重置；`share/[shareCode]` 使用 `force-cache`；`consumeTripStream` 註解吞字事件。 | T1, T2, T4, T5, T6, T7, T8, T9 |
| **Cloudinary** (`dnpcnwrcu`) | `mly_1414593269762424` (36 筆引用) 與 `mly_2831639033717822` (25 筆引用) 已呈 404，需在觸發器加上引用計數防衛並在前端補上 `TimelineCard` / `PhotoGalleryPreview` 壞圖降級。 | T8 |

---

## 2. Deletion Audit & Chesterton's Fence Code Archaeology

| 刪除 / 替換目標 | 原職責 (Legacy Function) | 設計意圖 (Design Intent) | 承接與回歸保護 (Replacement & Risk Mitigation) |
|---|---|---|---|
| `frontend/components/notifications/notification-bell.tsx` (`supabase.from("notifications")` 與 `postgres_changes`) | 前端直接透過 Supabase anon client 讀寫通知並訂閱資料表異動 | 減輕後端路由負載 | 改走 JWT 驗證的 FastAPI `/api/notifications*` (`service_role` + `get_verified_user`)，搭配不帶 PII 之 Realtime Broadcast (`user-notif:<uid>` & `user-notif:broadcast`) + `visibilitychange` + `isUserLoggedIn()`/`tbj_rec_` 守衛，並保留樂觀更新失敗回滾與全域節流單例 `dispatchGlobalRefreshThrottled`。 |
| `frontend/lib/hooks/usePushNotifications.ts` (`supabase.from("push_subscriptions")`) | 前端直接以 `localStorage` `user_uuid` 寫入推播訂閱 | 避免自建訂閱 API | 改由 FastAPI `/api/push/subscribe` (`POST`/`DELETE`) 經 JWT 驗證與嚴格 `https://` 非 loopback 端點檢查後寫入，保留 opt-out 與 Service Worker 逾時防禦。 |
| `frontend/lib/hooks/useTripRealtime.ts` (`postgres_changes` 監聽器 3 組) | 監聽 `itineraries` / `itinerary_items` / `expenses` 表異動 | 協作即時重整 | 因 anon 連線無法通過 `auth.uid()` RLS，移除無效監聽並由寫入點於 `create`、非 `skipRevalidation` `edit`、`UndoDeleteManager` delete flush 發送 `item:mutate` Broadcast 觸發協作者 SWR `revalidate: true`。 |
| `backend/routers/poi.py` (`if not api_key: raise 400`) | 強制無 API Key 時拒絕存取 `/api/poi/ai-enrich` | 節省 AI 模型呼叫 | 改為 `has_api_key` 雙軌降級：無 Key 時跳過 AI 摘要與 AI 翻譯，保留免費 Wikipedia / WikiVoyage / Wikidata 回傳 `200 PARTIAL_SUCCESS` (`ai_key_missing: true`, `NO_API_KEY`) 且嚴禁寫入 `POI_ENRICH_CACHE`。 |
| `backend/routers/users.py` (`.single()`) | 單筆查詢 `public.users` | 取回單一物件 | 改為 `.limit(1)` 並同時相容 PostgREST list 與測試單筆 dict 回傳，消除 PGRST116 例外，確保 Legacy 行程暱稱回補路徑暢通。 |
| `frontend/app/share/[shareCode]/page.tsx` (`cache: 'force-cache'`) | 永久快取公開分享行程 | 降低後端 SSR 流量 | 改為 `next: { revalidate: 60 }` 兼顧 CDN 快取與 1 分鐘內更新可見性。 |

---

## 3. Security Sentinel CLI & 全棧沙盒驗證紀錄

1. **Pre-Implementation Sentinel Runs**:
   - `--mode duel` (`candidates_2026-11-19_remediation.json`): `8/8 INCONCLUSIVE` (Windows nested `agy.exe` CLI timeout behavior).
   - `--mode adaptive` (`findings_pre_adaptive_2026-11-19.json`): `2 CONFIRMED`, `3 DISMISSED`, `3 INCONCLUSIVE` (揭示 `notification-bell` 登入事件追蹤需求與 `consumeTripStream` SSE 註解吞字事件 PoC).
2. **Post-Implementation Sentinel Runs (6/6 Verified Safe)**:
   - `findings_post_adaptive_2026-11-19.json`: `4 DISMISSED` (`poi.py`, `edge-shield/worker.js`, `api.ts`, `20261119_bug_hunter_remediation_schema.sql`), `2 INCONCLUSIVE` (關鍵字誤攔截 / 長度逾時).
   - `findings_post_retry_2026-11-19.json` & `findings_post_agents_2026-11-19.json`: 補測確認 `notifications.py` (`DISMISSED`) 與 `agents.py` (`DISMISSED`), 達成 **6/6 `DISMISSED` (`0 CONFIRMED`, `0 INCONCLUSIVE`)**.
3. **Ledger Conservation**:
   - `python scripts/validate_security_ledger.py` -> `408` targets (`181` remediated, `53` verified/unresolved, `174` dismissed/safe), `exit 0`.
4. **Full Stack Gates**:
   - Backend: `pytest -q --tb=short` -> `725 passed, 5 skipped`
   - Frontend: `npx tsc --noEmit` (`exit 0`), `npm run lint` (`exit 0`), `npx vitest run` (`118 files, 1113 passed | 4 skipped`), `npm run build` (`exit 0`)
   - Edge Shield: `npx wrangler deploy --dry-run` (`exit 0`, `10.82 KiB / gzip 3.43 KiB`)
