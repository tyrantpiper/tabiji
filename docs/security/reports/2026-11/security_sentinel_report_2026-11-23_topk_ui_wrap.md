# Security Sentinel Audit Report — Top-K Geocoding Overhaul & Mobile UI Wrapping Hardening

- **Date**: `2026-11-23`
- **Audit Mode**: `sentinel-agy-adversarial` (`runner.py --mode adaptive --timeout 120`, Round 1: 10 targets in isolated Git Worktree sandbox; Round 2: 6 delta/new targets after adversarial remediation)
- **Candidates**: `docs/security/history/candidates/candidates_topk_ui_wrap_2026-11-23.json`, `docs/security/history/candidates/candidates_topk_ui_wrap_r2_2026-11-23.json`
- **Findings**: `docs/security/history/findings/findings_topk_ui_wrap_2026-11-23.json` (10/10 DISMISSED), `docs/security/history/findings/findings_topk_ui_wrap_r2_2026-11-23.json` (6/6 DISMISSED)
- **Ledger Conservation**: `439 / 439` targets (`201` remediated, `53` verified/unresolved, `185` dismissed/safe; all `428` historical IDs preserved; `validate_security_ledger.py` EXIT `0`)

---

## 1. Executive Summary

| Metric | Round 1 | Round 2 (Delta + New) | Total Unique |
| :--- | :---: | :---: | :---: |
| Total Targets Validated | **10** | **6** | **11** |
| Initially Confirmed & Remediated (`CONFIRMED -> REMEDIATED -> DISMISSED`) | **1** | **0** | **1** |
| Remaining Confirmed Defects (`CONFIRMED`) | **0** | **0** | **0** |
| Final Dismissed / Verified Safe (`DISMISSED`) | **10** | **6** | **11** |
| Inconclusive (`INCONCLUSIVE`) | **0** | **0** | **0** |
| Harness² Conservation Identity | `0 + 10 + 0 == 10` PASS | `0 + 6 + 0 == 6` PASS | **PASS** |

> **Adversarial Review Remediation Resolved & Re-Validated in Sandbox**:
> 1. **`backend/services/geocode_service.py:topk_instant_return_and_single_pass_fallback`** (`CONFIRMED` on retry run -> remediated in sandbox -> re-verified `DISMISSED`): When a `LANDMARKS_DB` hit was blocked by `HOMONYM_GUARD_KEYS` (`lat is None or lng is None or dist_km > 80.0`) or invalidated via `not is_exact_lm` / `is_chain_brand` / `not country_matches`, `search_terms` retained polluted landmark aliases (and `landmark_data` remained populated on `not is_exact_lm` / `not country_matches`). Remediated by resetting `search_terms = [clean_query]`, `landmark_data = None`, and `display_name = None` on all invalidation paths, adding a dedicated Pytest PoC assertion in `backend/tests/test_topk_and_safety_net_sentinel.py`, and re-running `runner.py --mode adaptive` until verified `DISMISSED`.

---

## 2. Attack Surface Coverage Matrix

| # | Target ID | Trust Boundary | Final Verdict | Verification Evidence |
| :-: | :--- | :--- | :-: | :--- |
| 1 | `backend/services/geocode_service.py:topk_landmark_exact_gate_and_homonym` | `public_to_internal` | `DISMISSED` | Pytest `test_topk_and_safety_net_sentinel.py` + `test_geocode_search_overhaul_sentinel.py` + `test_mcp_affiliate_geo_sentinel.py` + Sentinel adaptive |
| 2 | `backend/services/geocode_service.py:topk_cjk_similarity_and_rerank` | `public_to_internal` | `DISMISSED` | Pytest `test_topk_and_safety_net_sentinel.py` (AC-PBT-1, bigram recall, cross-script monotonicity, per-source `_batch_rank`, temple vs transit weights) + Sentinel adaptive |
| 3 | `backend/services/geocode_service.py:topk_paren_fallback_and_city_anchor` | `public_to_internal` | `DISMISSED` | Pytest `test_topk_and_safety_net_sentinel.py` (ReDoS-bounded regex, `math.isfinite` bounds, zero Tokyo default) + Sentinel adaptive |
| 4 | `backend/services/geocode_service.py:topk_instant_return_and_single_pass_fallback` | `public_to_internal` | `REMEDIATED -> DISMISSED` | Caught by Sentinel adaptive (`search_terms` & `landmark_data` leak on invalidation); patched in sandbox + Pytest PoC + re-verified `DISMISSED` |
| 5 | `backend/routers/geocode.py:topk_fusion_anchor_dedup_and_limit` | `public_to_internal` | `DISMISSED` | Pytest `test_topk_and_safety_net_sentinel.py` + `test_smart_fusion_search.py` (zero Tokyo fallback, `<50m` same-name dedup without 2nd rerank, positive `limit` slice) + Sentinel adaptive |
| 6 | `backend/services/smart_search_service.py:topk_overpass_soft_filter` | `public_to_internal` | `DISMISSED` | Pytest `test_topk_and_safety_net_sentinel.py` (None/non-string field coercion, empty fallback to raw Overpass POIs) + Sentinel adaptive |
| 7 | `cloudflare/edge-shield/worker.js:topk_edge_cache_key_and_header_sanitization` | `browser_to_edge` | `DISMISSED` | `wrangler deploy --dry-run` + Sentinel adaptive (strips `Content-Length`/`Content-Encoding`, isolates macro zoom `<=10`, bypasses Gemini key & ArcGIS, whitelists cached headers) |
| 8 | `frontend/lib/location-utils.ts:topk_clean_query_regex_and_osm_dedup` | `browser_to_edge` | `DISMISSED` | Vitest `ui-wrapping-and-activity-modal-sentinel.test.tsx` (bounded regex, local `new RegExp` avoiding shared `lastIndex`, finite coord check, `(normOsmType, osm_id)` + 50m dedup) + Sentinel adaptive |
| 9 | `frontend/components/itinerary/ActivityEditModal.tsx:topk_modal_race_guard_and_paren_desc` | `browser_to_edge` | `DISMISSED` | Vitest `ui-wrapping-and-activity-modal-sentinel.test.tsx` (strict `[isOpen, editItem?.id]` cleanup, `AbortController`/`requestSeqRef`/`activeItemIdRef` guards, omits `limit`, preserves paren remark only into blank `desc`) + Sentinel adaptive |
| 10 | `frontend/components/views/itinerary-view.tsx:topk_save_bias_and_abort_timeout` | `browser_to_edge` | `DISMISSED` | Vitest + `tsc --noEmit` + Sentinel adaptive (`calculateBiasLocation(day)`, `3500ms` `AbortController` cleared in `finally`, non-blocking save) |
| 11 | `frontend/components/itinerary/LocationEditDialog.tsx:topk_location_dialog_day_switch_race_guard` | `browser_to_edge` | `DISMISSED` | Vitest (`ui-wrapping-and-activity-modal-sentinel.test.tsx`) + real Chromium 320px reopen test + Sentinel R2 adaptive (`[isOpen, day]` cleanup aborts in-flight search, increments `requestSeqRef`, clears stale results) |

---

## 3. Chesterton's Fence — Deletion & Behavior Change Archaeology Matrix

| Removed / Altered Component | `legacy_function` (功能反推) | `design_intent` (設計初衷) | `regression_risk` & 100% Handoff (刪除風險與承接機制) |
| :--- | :--- | :--- | :--- |
| **Replaced hardcoded `35.6895, 139.6917` Tokyo fallback in `backend/routers/geocode.py` (`resolve_fusion_anchor_coords`)** | Injected Tokyo coordinates whenever `body.lat`/`body.lng` were absent before invoking `smart_search_service`. | Ensured Fusion search had a numeric `(lat, lng)` pair for Japan-centric early prototypes. | Blind Tokyo coordinates poisoned global and Taiwan/Europe searches with Tokyo POIs. Now resolved deterministically via `body.lat/lng -> city/subdistrict anchor (incl. shinjuku/新宿) -> country capital anchor`; returns `(None, None)` and skips Fusion cleanly when no spatial signal exists. All 4 existing `smart_fusion` tests pass unchanged. |
| **Removed substring landmark matching in `translate_famous_landmark` Step 1, Step 3 fuzzy on POI/food queries, and Step 4 substring Disney match** | Matched landmarks whenever a `LANDMARKS_DB` key appeared as a substring (`台南龍山寺` -> Taipei `龍山寺`, `東京迪士尼飯店` -> Disneyland, `新宿一蘭拉麵` -> Shibuya single branch). | Intended to give 0ms instant hits for common landmark nicknames and minor typos. | Caused severe landmark hijacking and branch-name overwrites across 48 `BRANDS_DB` overlaps and `jp/restaurants.json`. Replaced with full-term `_is_exact_landmark_match` + chain-brand exclusion + exact bare `HOMONYM_GUARD_KEYS` (`lat is None or lng is None or dist_km > 80.0`), while preserving `display_name` on exact `BRANDS_DB` queries (`test_geocode_search_overhaul_sentinel.py#L129-130`) and deterministic Taipei/Seoul/Lukang CI hits (`test_mcp_affiliate_geo_sentinel.py`). |
| **Removed hardcoded `limit: 5` in `ActivityEditModal.tsx` geocode search & raw `fusion_pois + base_list` concatenation in `routers/geocode.py`** | Truncated modal dropdown to 5 candidates and prepended un-deduplicated Overpass Fusion items directly before geocoding results. | Reduced dropdown height in early modal layout and elevated smart search results. | Truncation dropped legitimate branches when Top-K returned 6–10 candidates; un-deduplicated Fusion produced duplicate pins. Modal now omits `limit` (backend default `10`), and `routers/geocode.py` deduplicates merged items by `(same normalized name + <50m)` without re-running `rerank_top_k` on `base_list`, slicing only when `body.limit > 0`. |
| **Replaced single-line `truncate` on search result titles/addresses and modal/dialog chips (`ActivityEditModal`, `LocationEditDialog`, `InfoView`, `DayMap`, `FullscreenMapModal`, `TimelineCard`, `POIDetailDrawer` expanded header)** | Clipped overflowing place names with ellipsis (`truncate` / `whitespace-nowrap`) in mobile search dropdowns and modals. | Kept single-line card height compact on narrow screens. | On 320px/375px mobile screens, long Japanese/Chinese facility names (60–120 chars) became unreadable or forced Radix `DialogContent`/`ScrollArea` horizontal overflow. Replaced with `wrap-break-word [word-break:break-word] whitespace-normal min-w-0` + fourfold axis-lock (`overflow-x-hidden touch-pan-y overscroll-x-none overscroll-y-contain`), while intentionally preserving `truncate` on `POIDetailDrawer` Peek bar and 2×3 quick-action grid cells. |
