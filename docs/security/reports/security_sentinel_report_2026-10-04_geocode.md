# Security Sentinel Empirical Audit Report: Parallel Geocoding & Top-K Reranking

- **Audit Date**: 2026-10-04T19:24:00+08:00
- **Mode**: `/security-sentinel` In-Memory Sandbox Adversarial Validation
- **Target Components**: 
  - `backend/services/geocode_service.py`
  - `backend/routers/geocode.py`
  - `backend/models/base.py`
  - `frontend/lib/api.ts`

---

## 🔬 Executive Summary

| Test Case | Hypothesis | Sandbox Empirical Result | Verdict |
| :--- | :--- | :--- | :--- |
| **TC-1: Country Filter Zero-Out** | `filter_results_by_country(..., strict=True)` discards cross-border queries like 桃園機場 when country=JP | Returns `[]` + throws `UnicodeEncodeError: 'cp950'` on Windows console | **CONFIRMED DEFECT** |
| **TC-2: Photon Public Importance** | Photon returns raw `importance` float in GeoJSON `properties` | Photon properties contains `['osm_type', 'osm_id', 'osm_key', 'osm_value', 'type', 'name', 'country', 'countrycode', 'extra', 'extent']`. Does **NOT** expose `importance`! | **CONTRADICTION DETECTED** |
| **TC-3: CJK Tokenization & Gaussian Collapse** | Unspaced CJK with `token_set_ratio` + Gaussian 50km decay causes nearby generic POI to outrank distant exact match | 成田國際機場 (0.69) outranked 臺灣桃園國際機場 (0.43) due to CJK token splitting failure and $\exp(-800)$ distance cliff | **CONFIRMED DEFECT** |
| **TC-4: BBOX Malformed Payload** | Photon returns 400 on malformed BBOX strings | Photon returns HTTP 400: `{"bbox":[{"message":"TYPE_CONVERSION_FAILED"}]}` | **CONFIRMED RISK** |
| **TC-5: Scatter-Gather Straggler Breaker** | Parallel scatter-gather without timeouts blocks on slow upstream engines | Verified `asyncio.wait_for` + `asyncio.gather(return_exceptions=True)` isolates stragglers (5s -> 0.2s) | **CONFIRMED PASS** |

---

## 🛡️ Mantis Patch & Block Replacement Candidate

### 1. `backend/services/geocode_service.py`
- Fix `filter_results_by_country` graceful fallback when filtered result is empty.
- Add `sanitize_bbox` to prevent upstream HTTP 400.
- Implement `cjk_text_similarity` with character-spaced tokenization + substring bonus.
- Implement `proximity_decay` using rational decay $1 / (1 + d / 150)$ instead of $\exp(-0.5 \cdot (d/50)^2)$.
- Implement `rerank_top_k` multi-factor fusion.
