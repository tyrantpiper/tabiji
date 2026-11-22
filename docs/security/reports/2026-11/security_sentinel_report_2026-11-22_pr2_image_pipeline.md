# Security Sentinel Audit Report — PR 2 Full-Stack Image Pipeline & Edge Proxy Hardening

- **Date**: `2026-11-22`
- **Audit Mode**: `sentinel-agy-adversarial` (`runner.py --mode adaptive --timeout 120`, isolated Git Worktree sandbox from `main @ 38396de`)
- **Candidates**: `docs/security/history/candidates/candidates_pr2_image_pipeline_2026-11-22.json`
- **Findings**: `docs/security/history/findings/findings_pr2_image_pipeline_2026-11-22.json`
- **Ledger Conservation**: `428 / 428` targets (`200` remediated, `53` verified/unresolved, `175` dismissed/safe; all `418` historical IDs preserved; `validate_security_ledger.py` EXIT `0`)

---

## 1. Executive Summary

| Metric | Count |
| :--- | :---: |
| Total Targets Validated | **10** |
| Confirmed Defects (`CONFIRMED`) | **0** |
| Dismissed / Verified Safe (`DISMISSED`) | **10** |
| Inconclusive (`INCONCLUSIVE`) | **0** |
| Harness² Conservation Identity (`0 + 10 + 0 == 10`) | **PASS** |

> **Adversarial Review Remediations Resolved & Re-Validated in Sandbox**:
> 1. **`frontend/lib/image-utils.ts`**: Hardened `hasJpegExifMetadata` to fail closed on truncated headers, stuffed `0xFF 0x00`, non-JPEG headers, and >64KB ICC profiles; added upfront 2D Canvas capability check (`hasCanvas2dSupport()`) eliminating real jsdom 8s deadlocks when `URL.createObjectURL` exists; added cancellation signals in `enqueueSerialTask` + `decodeImageSource` guaranteeing `maxActiveCanvases <= 1` even when a timed-out task wakes late; added `readImageFileAsDataUrl` normalizing empty-MIME `.heic`/`.heif` to `data:image/heic;base64,...` / `data:image/heif;base64,...`.
> 2. **End-to-End HEIC & Multimodal Input Alignment (`chat-widget.tsx`, `AiImportTripWizard.tsx`, `backend/routers/ai.py` `/api/ai/parse-md`)**: Replaced non-atomic compression state locks with `useRef` locks awaiting `readImageFileAsDataUrl`, preventing `data:application/octet-stream` 400 rejections on `/api/chat`; hardened `/api/ai/parse-md` with explicit image MIME allowlist, pre/post-decode base64 size bounds, and `process_and_optimize_image_sync` off-event-loop optimization (including `pillow-heif` conversion).
> 3. **Upload Lifecycle & Cross-Item Isolation (`ExpenseDialog`, `ImageUpload`, `MultiImageUpload`)**: Replaced boolean `formInitializedRef` with `initializedKeyRef` keyed by `editItem.id` so switching `editItem` while `open=true` resets `receiptUrl` and clears `localReceipt`; added unmount XHR abort + `isMountedRef` suppression + `xhr.onabort` cleanup across `ImageUpload` and `MultiImageUpload`.
> 4. **Edge Proxy (`cloudflare/cloudinary-proxy/worker.js`)**: Blocked upstream `image/svg*` responses (`415` + `Content-Security-Policy: sandbox` + `no-store`, never cached) to prevent Stored SVG XSS; implemented RFC quality-aware `prefersAvif` respecting `image/avif;q=0` with canonical upstream `Accept`; stripped `access-control-expose-headers` & `server-timing`; wrapped upstream `fetch` in `try/catch` returning `502 no-store`.

---

## 2. Attack Surface Coverage Matrix

| # | Target ID | Trust Boundary | Verdict | Verification Evidence |
| :-: | :--- | :--- | :-: | :--- |
| 1 | `frontend/lib/image-utils.ts:pr2_jpeg_exif_marker_walker` | `browser_to_edge` | `DISMISSED` | Vitest `image-utils-pr2-sentinel.test.ts` (APP1/APP13, SOS scan bytes, >64KB ICC, truncated/stuffed-00/non-JPEG fail-closed) + Sentinel adaptive |
| 2 | `frontend/lib/image-utils.ts:pr2_compress_image_safari_fallback_and_vram` | `browser_to_edge` | `DISMISSED` | Vitest `image-utils-pr2-sentinel.test.ts` (16MP cap, jsdom 0ms fail-open, true runtime Safari WebP→PNG→JPEG fallback, `#ffffff` fill, EXIF retry, cancellation-guarded serial queue, VRAM cleanup) + Sentinel adaptive |
| 3 | `frontend/components/ui/image-upload.tsx:pr2_direct_pass_and_reentrancy_guard` | `browser_to_edge` | `DISMISSED` | Vitest `cloudinary-upload-components-sentinel.test.tsx` C1 + `expense-dialog-and-ai-inputs-pr2-sentinel.test.tsx` (AC-5, editItem switch reset, unmount XHR abort, `onabort` unlock) + Sentinel adaptive |
| 4 | `frontend/lib/capsule-upload.ts:pr2_capsule_post_compression_gate` | `browser_to_edge` | `DISMISSED` | Vitest `prod-auth-and-edge-resilience.test.ts` F15 + `expense-dialog-and-ai-inputs-pr2-sentinel.test.tsx` + Sentinel adaptive |
| 5 | `frontend/lib/api.ts:pr2_parse_receipt_direct_client_forwarding` | `browser_to_edge` | `DISMISSED` | Vitest `ai-remediation-sentinel.test.ts` (direct `API.RECEIPT_PARSE` forwarding + orphan route deletion assertion) + Sentinel adaptive |
| 6 | `backend/routers/ai.py:pr2_receipt_dimension_and_strict_mode` | `authenticated_to_internal` | `DISMISSED` | Pytest `test_pr2_image_pipeline_sentinel.py` + `test_cloud_run_hardening_sentinel.py` + Sentinel adaptive |
| 7 | `backend/routers/ai.py:pr2_parse_md_image_validation_and_heic` | `authenticated_to_internal` | `DISMISSED` | Pytest `test_pr2_image_pipeline_sentinel.py` (SVG/octet-stream/oversized 400 + benign 3000x2000 PNG & HEIC downscale) + Sentinel adaptive |
| 8 | `backend/routers/ai.py:pr2_receipt_base64_mime_and_fallback` | `authenticated_to_internal` | `DISMISSED` | Pytest `test_pr2_image_pipeline_sentinel.py` + `test_parse_receipt_diagnostics.py` + Sentinel adaptive |
| 9 | `backend/main.py:pr2_chat_image_validation_and_http_propagation` | `authenticated_to_internal` | `DISMISSED` | Pytest `test_pr2_image_pipeline_sentinel.py` (400 propagation + benign downscale + corrupt graceful degradation) + Sentinel adaptive |
| 10 | `cloudflare/cloudinary-proxy/worker.js:pr2_edge_proxy_origin_path_and_cache_isolation` | `browser_to_edge` | `DISMISSED` | Vitest `cloudinary-proxy-worker-pr2-sentinel.test.ts` (origin/path/cache isolation, SVG 415 sandbox, `avif;q=0`, 502 network guard) + `wrangler deploy --dry-run` + Sentinel adaptive |

---

## 3. Chesterton's Fence — Deletion & Behavior Change Archaeology Matrix

| Removed / Altered Component | `legacy_function` (功能反推) | `design_intent` (設計初衷) | `regression_risk` & 100% Handoff (刪除風險與承接機制) |
| :--- | :--- | :--- | :--- |
| **Deleted `frontend/app/api/parse-receipt/route.ts` (-113 lines)** | Next.js App Router POST proxy accepting `{ imageUrl, image, mime_type, locale }`, downloading `res.cloudinary.com` images via server-side `fetch()` into unbounded `arrayBuffer()`, and forwarding to FastAPI `/api/ai/parse-receipt`. | Originally added when client-side receipt uploads could not call Cloud Run directly without CORS/proxy routing. Live telemetry confirmed `www.tabijiapp.com/api/parse-receipt` returns 404 via Edge Shield, while `travel-pwa-five.vercel.app/api/parse-receipt` remained exposed without JWT auth or `arrayBuffer()` size bounds. | **Zero production callers** (`git grep parse-receipt` verified 0 frontend usages; `frontend/lib/api.ts` already calls `API.RECEIPT_PARSE = ${API_HOST}/api/ai/parse-receipt`). `aiApi.parseReceipt` now also forwards `Accept-Language` (`en-US`/`zh-TW`) alongside `X-Gemini-API-Key`, `locale`, `image`, and `imageUrl` for 100% parity. `frontend/lib/sw-routing.ts:L66` NetworkOnly guard is retained to preserve SW security tests. `frontend/__tests__/ai-remediation-sentinel.test.ts` migrated to assert real `aiApi.parseReceipt` + absence of the deleted route. |
| **Hardened `cloudflare/cloudinary-proxy/worker.js` (replaced `.includes()` origin check, loose width regex, unisolated cache key, and unconditional 1-year caching)** | Edge Worker proxying `res.cloudinary.com` assets with basic Referer `.includes()` check, optional `/w_<width>` parsing, format negotiation (`f_avif`/`f_webp`), and `caches.default` caching. | Intended to reduce Cloudinary bandwidth/transformation credits and inject `ACAO: *` for PDF/Canvas exports while letting iOS Standalone PWA (empty Referer/Origin) load images. Live probe proved `REDACTED_CLOUDINARY_CLOUD` placeholder risk, `.includes('tabijiapp.com')` bypass via `tabijiapp.com.evil.com`, arbitrary transform injection (`/w_320/e_blur:100/v1/...`), 1-year `immutable` caching on HTTP 400/404/405 with leaked `x-cld-error`, and `CF-Cache-Status: BYPASS` caused by upstream `cdn-cache-control: no-store` + `Vary: Save-Data`. | **100% benign compatibility preserved**: empty `Referer` & `Origin` remain allowed for iOS Standalone PWA; valid `tabijiapp.com`, `www.tabijiapp.com`, `travel-pwa-five.vercel.app`, `travel-pwa-*.vercel.app`, `localhost`, and `127.0.0.1` pass strict `new URL()` hostname matching; all standard `getOptimizedImageUrl` URLs (`/w_{320\|640\|768\|1024\|1280}/v<digits>/<asset>`) match `STRICT_PROXY_PATH_RE`; `utils.ts:L75` default remains unchanged so `TC-2` passes 100%. Upstream `cdn-cache-control`, `cloudflare-cdn-cache-control`, `vary`, `set-cookie`, `x-cld-error`, `access-control-expose-headers`, and `server-timing` are stripped; `image/svg*` is blocked with `415 sandbox no-store`; `prefersAvif` respects `q=0`; upstream fetch errors return `502 no-store`; cache keys are isolated by `?fmt=f_avif\|f_webp`; only `GET 200` raster `image/*` responses receive 1-year `immutable` and `cache.put()`. |
| **Refactored `frontend/lib/image-utils.ts` (removed 8192px callers & single-axis resize)** | Client-side Canvas image resizer using `new Image()` and single-axis width/height check, returning raw `Blob` with hardcoded `image/jpeg`. | Prevented oversized camera photos from failing Cloudinary 10MB upload limits. Left transparent PNGs black-backed, suffered iOS Safari 16.7MP OOM/VRAM leaks, allowed concurrent Canvas spikes, silently fell back to bloated PNG on Safari WebP, and ignored empty-MIME `.heic` files. | **100% backward compatible**: `compressImage(file, presetNameOrOptions)` still accepts custom `{ maxWidth, maxHeight, quality, mimeType }` objects AND string preset names (`avatar`, `cover`, `spot`, `document`, `receipt`, `capsule`, `ai_input`), preserving compatibility with PR 1 component mocks (`vi.mock('@/lib/image-utils', () => ({ compressImage }))`), `image/svg+xml` (`F15`), and fail-open behavior for undecodable HEIC or bare jsdom environments (with 0ms `hasCanvas2dSupport()` short-circuit and cancellation-guarded serial queue). |
