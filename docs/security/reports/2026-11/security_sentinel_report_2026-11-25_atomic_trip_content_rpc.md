# 🛡️ Security Sentinel 沙盒對抗審查報告：Phase 1 Pure Postgres 原子 RPC 與前端 P0 Info/Card 離線回滾修復 (2026-11-25)

> **稽核基準**: `ff6909a` (`main`)
> **稽核模式**: Pre-Execution Worktree Spiking (`.worktrees/review-sandbox`) ✕ Red→Green PoC ✕ Mantis Block G ✕ `runner.py --mode fast` (10 切片平行對抗審查 `agy.exe --sandbox`) ✕ Harness² Ledger 守恆
> **審查判定**: **`10 / 10` `DISMISSED` (Verified Safe Post-Patch)**（`0 confirmed`, `0 inconclusive`, `SENTINEL_RC=0`）
> **台帳守恆驗證**: `454` Targets (`53` verified/unresolved + `214` remediated + `187` dismissed/safe = `454`, `scripts/validate_security_ledger.py RC=0`)

---

## 1. 執行摘要與沙盒實證 (Executive Summary)

1. **Pre-Execution Worktree Spiking (`.worktrees/review-sandbox`) Red→Green PoC 實證**：
   - **Mantis Block G Benign Control**：
     - 後端 `BE_BENIGN_RC=0` (`2 passed`: legacy `MagicMock()` `.table()` 相容性、一般單人寫入)。
     - 前端 `FE_BENIGN_RC=0` (`1 passed`: `tripsApi.updateInfo` 線上 Bearer JWT 正常更新)。
   - **Pre-Patch Red Check**：
     - 後端 `BE_RED_RC=1` (`8 / 8 failed`：`20261125_atomic_trip_content_rpcs.sql` 尚未建立、缺 HTTP/1.1 執行緒安全 `supabase_http_client`、無 `trip_lock` 跨實例併發遺失、非 UUID `22P02` 炸成 `500`、缺 `55P03`/`40P01` 重試與 `409`、缺 `PGRST202` 降級與 `/info` L1795 `detail=str(e)` 洩漏、缺 `run_in_threadpool` 非阻塞執行、`day < 0` 未擋)。
     - 前端 `FE_RED_RC=1` (`4 / 4 failed`：`tripsApi.updateInfo` 未走 `offlineFetch`、`useOfflineMutation` 線上分支缺 Bearer JWT 與 401 重試、`tools-view.tsx` 走 `offlineMutate` 吞錯未回滾且誤清 `localStorage` 與 `!activeTripId` 遺失私卡、`info-view.tsx` `handleSaveInner` 失敗缺回滾且 `useEffect` 沖刷草稿)。
   - **Post-Patch Green Check (Sandbox + Main Workspace + Round-2 Adversarial Fix)**:
     - 後端全倉 `pytest -q`: **`803 passed, 5 skipped`** (`FULL_PYTEST_RC=0`，含新增 `test_atomic_trip_content_rpc_sentinel.py` `11/11` 與 `test_collab_privacy_and_gdpr_sentinel.py` 走 `.rpc()` 全過)。
     - 前端靜態與全倉測試：`npx tsc --noEmit` (`0 errors`, `RC=0`)、`npm run lint` (`0 errors, 0 warnings`, `RC=0`)、`npx vitest run` (**`131/131 files, 1224 passed | 4 skipped`**, `RC=0`，含 `trip-info-cards-atomic-sentinel.test.tsx` `8/8`)。
     - 神經縫隙回歸：`python scripts/neural_seam_harness.py` (`SEAM_RC=0`, 10/10 intact)。
2. **Security Sentinel CLI (`runner.py --mode fast`)**：
   - 10 切片平行物理沙盒驗證 (`agy.exe --sandbox`)：**`10 / 10 DISMISSED`** (`0 confirmed`, `0 inconclusive`, `RC=0`)。

---

## 2. 攻擊面覆蓋矩陣 (Attack Surface Coverage Matrix)

| Target ID | Trust Boundary | Attack Vector | Pre-Patch PoC | Post-Patch Sentinel Verdict |
|---|---|---|---|---|
| `supabase/migrations/20261125_atomic_trip_content_rpcs.sql:trigger_and_day_data_atomic_rpc` | `authenticated_to_internal` | `bola_privilege_escalation_or_jsonb_corruption_or_deadlock` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |
| `supabase/migrations/20261125_atomic_trip_content_rpcs.sql:info_and_import_atomic_rpcs` | `authenticated_to_internal` | `credit_card_ownership_hijacking_or_date_shrinkage_or_dac_exposure` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |
| `backend/utils/deps.py:threadsafe_http11_supabase_pool` | `authenticated_to_internal` | `multithread_http2_race_or_connection_leak` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |
| `backend/routers/trips.py:atomic_rpc_helper_and_import_wiring` | `authenticated_to_internal` | `uuid_22p02_oracle_or_fail_open_fallback_or_event_loop_block` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |
| `backend/routers/trips.py:day_data_location_info_rpc_and_500_sanitization` | `authenticated_to_internal` | `error_information_disclosure_or_partial_clobber_or_bola` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |
| `backend/routers/ai.py:day_review_atomic_rpc_and_creator_bypass` | `authenticated_to_internal` | `bola_bypass_or_llm_inside_db_lock_or_stale_overwrite` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |
| `frontend/components/views/tools-view.tsx:credit_card_jwt_offline_and_rollback` | `browser_to_edge` | `unauthenticated_mutation_silent_data_loss_or_stale_clobber` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |
| `frontend/components/views/tools-view.tsx:credit_card_save_delete_rollback_and_local_persistence` | `browser_to_edge` | `premature_localstorage_wipe_or_missing_no_trip_persistence` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |
| `frontend/components/views/info-view.tsx:hotel_inner_edit_rollback_and_draft_preservation` | `browser_to_edge` | `optimistic_state_drift_or_draft_wipe_on_save_failure` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |
| `frontend/lib/sync-hooks.ts:offline_mutation_online_jwt_and_401_retry` | `browser_to_edge` | `missing_jwt_header_or_unhandled_401_token_expiry` | `RED_RC=1` | `DISMISSED` (`REMEDIATED`) |

---

## 3. 切斯特頓圍欄三問考古與刪除審查 (Code Archaeology & Deletion Audit)

| 變更檔案與位置 | 刪除／替換內容 | 歷史功能與設計初衷 (`legacy_function` & `design_intent`) | 刪除風險與 100% 承接機制 (`regression_risk`) |
|---|---|---|---|
| `supabase/migrations/20261125_atomic_trip_content_rpcs.sql` | `DROP FUNCTION IF EXISTS public.update_trip_credit_cards(UUID, JSONB)` | 早期繞過後端直寫 `itineraries.content->'credit_cards'` 之舊版 `SECURITY DEFINER` RPC。 | 線上授予 `authenticated` 執行權可任意覆寫他方行程私卡；由 `service_role` 專屬 `patch_trip_info_atomic`（含 5 大歸屬不變量與 `FOR NO KEY UPDATE`）100% 承接。 |
| `backend/main.py` & `backend/utils/deps.py` | 以 `create_threadsafe_supabase_client()` (`httpx.Client(http2=False)`) 取代裸 `create_client(url, key)` | 預設 `supabase-py` 建立 `http2=True` `httpx.Client` 且延遲初始化 `.postgrest`。 | 在 `run_in_threadpool` 多執行緒併發下 `httpcore 1.0.9 HTTP2Connection._h2_state` 無鎖會爆 `StreamIDTooLowError`；改為 HTTP/1.1 連線池＋主執行緒預熱 `.postgrest`＋Lifespan 顯式 `.close()` 完整承接。 |
| `backend/routers/trips.py:L1795` | 刪除 `detail=str(e)` 改為固定脫敏訊息 `"更新行程資訊失敗，請稍後重試"` | 早期除錯方便將底層例外直接透傳至前端。 | 暴露 PostgreSQL / PostgREST 內部錯誤細節；伺服器端維持 `print(f"Update Info Error: {e}")` 留存除錯日誌，對外固定脫敏。 |
| `frontend/components/views/tools-view.tsx` | 移除 `offlineMutate` / `API_HOST` 並改用 `tripsApi.updateInfo`，移除吞錯 `try/catch` 與先行清除 `localStorage` | 早期為支援離線佇列直接引用 `useOfflineMutation`，並於送出前順手清理舊版 `localStorage` 卡。 | `offlineMutate` 線上分支原漏帶 JWT 且 `saveTripInfo` 吞錯導致 401 仍顯示成功並永久清空舊卡；由 `tripsApi.updateInfo` (`offlineFetch`) 100% 承接 JWT、401 換票、`Idempotency-Key` 與離線/Lie-Fi 佇列，失敗時回滾狀態與不清空 `localStorage`，並於 `!activeTripId` 落盤本地私卡。 |
| `frontend/components/views/info-view.tsx` | 將同步 `handleSaveInner` 與無回傳 `handleSave` 升級為 `async` / `Promise<boolean>` 並加入 `preserveInnerDraftRef` | 原先為了消除 React `setState` 延遲而同步送出 `handleSave(newHotels)` 並立即關閉編輯態。 | 失敗時無回滾且 `useEffect([detailOpen, currentHotelIdx, hotels])` 會在 `hotels` 回滾時重設 `innerEditing=false` 沖刷草稿；改以 `preserveInnerDraftRef` + `setHotels(prevHotels)` + `setTempHotel(draftHotel)` + `setInnerEditing(true)` 完整承接。 |

---

## 4. Deliverables 索引

- **SQL Migration**: [`20261125_atomic_trip_content_rpcs.sql`](file:///d:/Project/tabiji/travel-pwa/supabase/migrations/20261125_atomic_trip_content_rpcs.sql)
- **後端回歸哨兵**: [`test_atomic_trip_content_rpc_sentinel.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_atomic_trip_content_rpc_sentinel.py)
- **前端回歸哨兵**: [`trip-info-cards-atomic-sentinel.test.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/trip-info-cards-atomic-sentinel.test.tsx)
- **候選清單**: [`candidates_atomic_trip_content_rpc_2026-11-25.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/candidates/candidates_atomic_trip_content_rpc_2026-11-25.json)
- **Sentinel 結果**: [`findings_atomic_trip_content_rpc_2026-11-25.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/findings/findings_atomic_trip_content_rpc_2026-11-25.json)
- **統一補丁**: [`patch_candidate_atomic_trip_content_rpc_2026-11-25.diff`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/patches/patch_candidate_atomic_trip_content_rpc_2026-11-25.diff)
- **覆蓋台帳**: [`security-coverage-ledger.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/security-coverage-ledger.json)
