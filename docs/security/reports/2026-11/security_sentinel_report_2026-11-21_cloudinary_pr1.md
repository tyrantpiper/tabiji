# Security Sentinel Report — PR 1: Cloudinary Signing Zero-Downtime Cloud Run Migration (2026-11-21)

## 1. Executive Summary
- **Audit Scope**: PR 1 Security Convergence (Scheme A: Cloud Run authenticated `POST /api/sign-cloudinary` in `backend/routers/cloudinary.py` (283 lines), 2-tier CWE-290-hardened rate limiting with `60/minute` per-user case-normalized `uid` SlowAPI limit and `240/minute` pre-auth `OrderedDict` LRU rightmost-GFE `X-Forwarded-For` `getlist()` IP limiter, RFC 9110 §8.6 strict `Content-Length` + 4096-byte chunked streaming body cutoff, `public_id` overwrite protection restricted to `ryan_travel/streetview` + `^mly_[0-9A-Za-z_-]{1,64}\Z`, atomic `{ signature, apiKey, cloudName }` response with `Cache-Control: no-store`, 6 frontend callers migrated to `cloudinaryApi.signUpload`, Cloudflare Edge Shield passthrough removal, and Next.js `/api/sign-cloudinary` route + Vercel `CLOUDINARY_API_SECRET` removal).
- **Zero-Downtime Rollout Topology**:
  - **CP 1–CP 2**: Cloud Run `antigravity-backend` revision `antigravity-backend-00207-wcz` (100% traffic) with GCP Secret Manager `cloudinary-api-secret:2` + rotated `CLOUDINARY_API_KEY=686667511485883`; Supabase Edge Function secrets aligned & live-verified.
  - **CP 3–CP 10 (Stage A)**: Frontend callers + RTL sentinel tests deployed to Vercel Production (`dpl_2HMTihHjrx1G22K6LWW9e2ubqT1z`, commit `8219ec4`) while keeping legacy Vercel `/api/sign-cloudinary` temporarily alive for zero 404s.
  - **CP 11 (Stage B)**: Cloudflare Edge Shield (`tabijiapp-edge-shield`, version `e89aecbf-4315-4ab5-a394-51afc8b90037`) cut over to Cloud Run; live unauthenticated `POST` returns `401` and authenticated `POST` returns `200` with rotated `apiKey=686667511485883`, `cloudName=dnpcnwrcu`, `Cache-Control: no-store`.
  - **CP 12 (Stage C)**: Legacy `frontend/app/api/sign-cloudinary/route.ts` removed, tests & Security Sentinel ledger migrated, Vercel `CLOUDINARY_API_SECRET` purged across all environments, and 4-domain penetration verification executed (`tabijiapp.com`, `www.tabijiapp.com`, `travel-pwa-five.vercel.app`, Cloud Run).
- **Security Sentinel Runner (`runner.py --mode adaptive --timeout 120`, full un-truncated slices)**:
  - **Total Validated**: `5`
  - **Confirmed**: `0`
  - **Dismissed**: `5`
  - **Inconclusive**: `0`
  - **Harness² Conservation Identity**: `0 + 5 + 0 == 5 == len(findings)` (`PASS`)
- **Mantis Block G Split Verification (`backend/tests/test_cloudinary_sign_sentinel.py`, 830 lines)**:
  - `pytest -v -k "benign"`: **5 passed** (`EXIT 0`)
  - `pytest -v -k "not benign"`: **12 passed** (`EXIT 0`, including `OrderedDict` LRU eviction/window expiry and RFC 9110 §8.6 `Content-Length` smuggling + chunked stream cutoff)
  - Full backend regression (`pytest -q`): **743 passed, 5 skipped** (`EXIT 0`; HEAD baseline `726 passed, 5 skipped`)
- **Frontend Verification**:
  - `npx tsc --noEmit`: **0 errors** (`EXIT 0`)
  - `npm run lint`: **0 errors, 0 warnings** (`EXIT 0`)
  - `npx vitest run`: **120 files / 1132 passed, 4 skipped** (`EXIT 0`; includes 4 jsdom RTL component interaction tests in `cloudinary-upload-components-sentinel.test.tsx` + migrated `F9`/`F14`/`F15`)
  - Production default Turbopack `npx next build`: **EXIT 0** (`/api/sign-cloudinary` absent, `/api/cloudinary-test` preserved)
- **Cloudflare Edge Shield**: `npx -y wrangler deploy --dry-run` (`EXIT 0`, `10.73 KiB / gzip: 3.41 KiB`) + live `wrangler deploy` (`e89aecbf-4315-4ab5-a394-51afc8b90037`).
- **Security Coverage Ledger**: `413 -> 418` targets (`+5` remediated, `0` legacy IDs altered/removed), verified by `scripts/validate_security_ledger.py` (`EXIT 0`) and `tests/test_root_hygiene_sentinel.py` (`EXIT 0`).

## 2. Attack Surface Coverage Matrix

| Target ID | Trust Boundary | Vector Checked | Sentinel Verdict | Test Evidence |
| --- | --- | --- | --- | --- |
| `backend/routers/cloudinary.py:auth_and_rate_limit_order` | `public_to_authenticated` | `rate_limit_key_isolation_and_auth_ordering` | `DISMISSED` (post-fix) | `test_cloudinary_sign_sentinel.py` (pre-auth multi-header rightmost-XFF `OrderedDict` LRU IP limit `240/min` + `Retry-After`/`no-store`, single `jwt.decode`, case-normalized `uid` SlowAPI `60/min` limit, `get_verified_user` override) |
| `backend/routers/cloudinary.py:param_folder_timestamp_public_id_guard` | `authenticated_to_internal` | `parameter_validation_and_public_id_overwrite_scope` | `DISMISSED` (post-fix) | `test_cloudinary_sign_sentinel.py` (RFC 9110 §8.6 strict `Content-Length` + 4096B chunked body cap, benign folders, streetview `public_id` scope, `±600s` skew, leading-zero/bool/float/Unicode/newline guards, CRLF secret trimming, BYOK keyword absence) |
| `frontend/lib/api.ts:cloudinary_sign_upload_client_boundary` | `browser_to_edge` | `client_auth_propagation_and_response_validation` | `DISMISSED` (post-fix) | Vitest `F9` (`API.SIGN_CLOUDINARY`, Bearer JWT, 401 refresh + 1-time retry, `extractError` for `detail`/`error`, safe non-JSON 200 & whitespace trimming) |
| `cloudflare/edge-shield/worker.js:sign_cloudinary_edge_forwarding` | `browser_to_edge` | `edge_routing_header_and_body_forwarding` | `DISMISSED` (post-fix) | Vitest `F14` (URL/POST/Authorization/Host/redirect/duplex/body/`no-store`) + live `wrangler deploy` (`e89aecbf-4315-4ab5-a394-51afc8b90037`) + 4-domain penetration verification |
| `frontend/components/ui/multi-image-upload.tsx:upload_error_and_progress_cleanup` | `browser_to_edge` | `error_handling_and_state_reset_hygiene` | `DISMISSED` (post-fix) | Vitest `F15` + `cloudinary-upload-components-sentinel.test.tsx` (4/4 RTL component tests across `ImageUpload`, `MultiImageUpload`, `TripCoverMenu`, `TripSettingsView`) |

## 3. Chesterton's Fence Code Archaeology Matrix (All Deletions & Behavioral Changes)

| File | Legacy Function | Design Intent | Regression Risk & 100% Handoff |
| --- | --- | --- | --- |
| `frontend/app/api/sign-cloudinary/route.ts` (deleted, `-70` lines) | Unauthenticated Next.js API route signing Cloudinary upload params using Vercel `CLOUDINARY_API_SECRET`. | Co-located signing with frontend before authenticated Cloud Run + Edge Shield architecture matured. | **Risk**: 404 on uploads if removed prematurely. **Handoff**: `backend/routers/cloudinary.py` serves authenticated `POST /api/sign-cloudinary` on Cloud Run; `worker.js` routes `www.tabijiapp.com`/`tabijiapp.com` and `next.config.mjs` fallback rewrite routes `.vercel.app` & localhost to backend. |
| `cloudflare/edge-shield/worker.js` (`-6/+2` lines) | Passed `/api/sign-cloudinary*` straight to Vercel origin instead of Cloud Run. | Prevented Cloud Run 404 prior to backend endpoint rollout. | **Risk**: 404 if deployed before Cloud Run. **Handoff**: Under Scheme A deployment order (Cloud Run first, then Frontend Stage A, then Edge Shield Stage B, then Vercel cleanup Stage C), Section 3 forwards `POST /api/sign-cloudinary` to Cloud Run preserving `Authorization`, body (`duplex: 'half'`), `Host` rewrite, and `redirect: 'manual'`. |
| 6 frontend callers (`image-upload.tsx`, `multi-image-upload.tsx`, `TripCoverMenu.tsx`, `TripSettingsView.tsx`, `capsule-upload.ts`, `mapillary.ts`) | Direct unauthenticated `fetch("/api/sign-cloudinary")` with pre-flight static `NEXT_PUBLIC_CLOUDINARY_*` check. | Simple same-origin call prior to JWT requirement and key rotation. | **Risk**: Auth failure (401) or key mismatch during rotation if callers omit JWT or ignore rotated `apiKey`. **Handoff**: All 6 callers invoke `cloudinaryApi.signUpload`, prefer server-returned `apiKey`/`cloudName` with `NEXT_PUBLIC_*` fallback, and preserve all compression/XHR/toast/haptic/a11y logic (`multi-image-upload.tsx` also gains `!res.ok` rejection + `setProgress(0)` + `fileInputRef` reset; `image-upload.tsx` resets `e.target.value` so failed uploads can retry the same file; `TripCoverMenu.tsx` preserves `DialogDescription`). |
| `frontend/next.config.mjs` (`-1/+1` comment line) | Comment citing local App Router priority for `/api/sign-cloudinary`. | Documented `fallback` rewrites ordering. | **Risk**: None (comment-only update; `/api/:path*` fallback rewrite rule unchanged). |
| `frontend/__tests__/prod-auth-and-edge-resilience.test.ts` (F9 & F14 migrated, F15 added) | Tested deleted Next.js `/api/sign-cloudinary/route.ts` directly. | Validated signing folder/param/timestamp checks when logic lived in Next.js. | **Risk**: Coverage drop on signing validation. **Handoff**: Full server-side assertions + new auth/rate-limit/skew/`public_id`/LRU/RFC 9110 `Content-Length`/body-cap checks live in `backend/tests/test_cloudinary_sign_sentinel.py` (17/17 passing); F9/F14/F15 + `cloudinary-upload-components-sentinel.test.tsx` cover client JWT+401 retry, Edge Shield Cloud Run forwarding, and all 6 frontend callers. |

## 4. Deliverables & Verification Handover
- **Candidates**: `docs/security/history/candidates/candidates_cloudinary_pr1_2026-11-21.json`
- **Code-Only Candidate Patch**: `docs/security/history/patches/patch_candidate_cloudinary_pr1_2026-11-21.diff`
- **Coverage Ledger**: `docs/security/security-coverage-ledger.json` (`418` targets, `validate_security_ledger.py` EXIT 0)
- **CP 13 Gate**: Legacy Cloudinary Root Key `996197457174111` intentionally retained active pending human confirmation after final Chrome E2E verification.
