# 🛡️ Security Sentinel V2 全系統修復驗收報告 (Post-Completion Audit V2 Live Applied 2026-11-10)

> **驗收日期**: 2026-11-10  
> **基準提交 (`HEAD`)**: `44f107f`  
> **稽核模式**: Cloudflare 6-Phase Ledger ✕ Google Mantis Block G ✕ Harness² Invariant Conservation  
> **台帳守恆結果**: `353` Targets (`130 remediated + 56 verified/unresolved + 167 dismissed/safe = 353`, `RC=0`)  
> **實體套用判定**: **APPLIED & VERIFIED (ALL 6 LIVE GATES GREEN)**

---

## 1. Live 套用與核心修正摘要

依 [`implementation_plan.md`](file:///C:/Users/Ryan%20su/.gemini/antigravity/brain/5dbe8200-1879-4852-be56-160d7e6f93f3/implementation_plan.md) 與 [`block_replacements_post_completion_audit_2026-11-10.json`](file:///d:/Project/tabiji/travel-pwa/docs/security/history/candidates/block_replacements_post_completion_audit_2026-11-10.json) 將 20 個生產檔案（74 個替換區塊，`+1235 / -625` 補丁行數）與 3 個永久回歸測試檔套用至實體工作區：

1. **V1 全數 21 項確認漏洞修復 (`REMEDIATED`)**：包含 `trips.py` BOLA 存取檢查與統一 `_rollback_created_trip()` 補償刪除、`trip_lock` 讀寫序列化與 `_chunked(..., 50)` `.in_()` 批次化、`expenses.py` `Idempotency-Key` 與 404/500 脫敏、`ai.py` `generate_day_review` JWT/BOLA 與 `parse_markdown` `400/422` 驗證、`main.py` 500 堆疊脫敏與雙語超時防護、`HeroTypewriterHeading` / `TypewriterHeading` React 19 Compiler `key` 隔離、`AiImportTripWizard` / `EditableDailyAIReview` / `TripCoverMenu` a11y 與雙語化、`offlineFetch` Lie-Fi 與 `Idempotency-Key`。
2. **V2 再審核 5 項新增升級 (`REMEDIATED`)**：
   - `backend/routers/app.py:donation_progress_zero_fiat_fail_closed`：伺服端計算百分比與 UTC 跨月歸零，JSON 完全剔除 `current` / `goal`，缺列回 `{available: false}`，DB 異常回 `HTTP 503` + `Cache-Control: no-store`。
   - `backend/services/model_manager.py:dual_track_timeout_and_deferred_eviction`：`PLANNING_SSE=120s` (ContextVar `call_timeout_scope`)、`PLANNING=90s`、預設 `45s`；`asyncio.TimeoutError` 不呼叫 `record_model_error()` 直接切換備援；LRU 淘汰（上限 32）改為 `RETIRED_CLIENT_CLOSE_DELAY=150s` 延遲 `aclose()`。
   - `backend/routers/ai.py:generate_trip_sse_timeout_scope`：`generate_trip_core` 具備 `progress_queue` 時啟用 `call_timeout_scope("PLANNING_SSE")`，保留 10 秒心跳與 5 參數 `call_extraction` 簽名相容。
   - `frontend/lib/api.ts:donation_progress_offline_and_no_store`：新增 `DonationProgressResponse`，離線短路 `{available: false}` 與 `cache: "no-store"`。
   - `frontend/components/views/profile-view.tsx:donation_fail_closed_and_zero_fiat`：改存 `donationPercentage: number | null`，當月已關閉跳過 API 請求，`HTTP 503` / 離線 / `{available: false}` 一律 `setShowDonation(false)` 整張隱藏。

---

## 2. Live 品質關卡實測結果

- `python -m pytest tests/test_post_audit_sentinel_poc.py -v` ➔ `26 passed in 3.10s` (`RC=0`)
- `python -m pytest tests/test_root_hygiene_sentinel.py -v` ➔ `6 passed` (`RC=0`)
- `python -m pytest -q` ➔ `501 passed, 5 skipped in 63.21s` (`RC=0`)
- `npx tsc --noEmit` ➔ `0 errors` (`RC=0`)
- `npx eslint .` ➔ `0 errors, 0 warnings` (`RC=0`)
- `npx vitest run` ➔ `103 passed (103)` / `955 passed (955)` (`RC=0`)
- `npx next build` ➔ `RC=0` (Turbopack + React Compiler + Cache Components / PPR)
- `python scripts/validate_security_ledger.py` ➔ `Verified 353 targets (130 remediated, 56 verified/unresolved, 167 dismissed/safe).` (`RC=0`)

## 3. 複審補充修正（Independent Skepticism Review Fixes）

1. `backend/main.py`：`lifespan()` 關閉階段納入 `await close_all_cached_clients()` 與 `keepalive_task` 取消等待，回收 Active / 150s 延遲淘汰中之 `genai.Client`。
2. `backend/routers/ai.py`：`clear_day_review` 補齊 `trip_lock(trip_id)`、`dict(...)` 淺拷貝、重讀防 clobber 與 500 錯誤脫敏；`parse_markdown` 支援 `awaitable` 之 `dependency_overrides`。
3. `backend/routers/trips.py`：`import_to_trip` 於外部 Geocoding 完成後取得 `trip_lock(request.trip_id)` 重讀最新 `itineraries`/`itinerary_items` 執行序列化合併與 500 脫敏；`leave_trip` 以 `_safe_single_data` 處理 `PGRST116` 並脫敏 500。
4. `frontend/components/views/profile-view.tsx`：新增 `online`/`offline`/`refresh-active-view` 監聽、`donationReqSeqRef` 序號防競態與離線瞬間歸零清空，防止 `AppShell` 背景預載之快取百分比於斷線後外洩或復線卡死隱藏。

---

## 4. 新增永久回歸測試檔

- [`backend/tests/test_post_audit_sentinel_poc.py`](file:///d:/Project/tabiji/travel-pwa/backend/tests/test_post_audit_sentinel_poc.py)
- [`frontend/__tests__/post-audit-remediation-sentinel.test.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/post-audit-remediation-sentinel.test.tsx)
- [`frontend/__tests__/donation-fail-closed-sentinel.test.tsx`](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/donation-fail-closed-sentinel.test.tsx)
