# Security Sentinel Adversarial Audit Report: Notification-Bound Refresh & Header Decluttering

> **Audit Date**: 2026-10-21  
> **Auditor**: `@security` (Security Sentinel Engine v2.0.0 via `agy.exe --sandbox`)  
> **Status**: Verified & Hardened (Ready for Human Gate Handover)  
> **Target Commits/Branch**: `main`  
> **Primary Surfaces Audited**:
> - `frontend/components/notifications/notification-bell.tsx`
> - `frontend/components/views/itinerary-view.tsx`
> - `frontend/components/itinerary/ItineraryHeader.tsx`
> - `frontend/components/itinerary/TabijiHomeDashboard.tsx`
> - `frontend/components/views/tools-view.tsx`
> - `frontend/components/views/info-view.tsx`

---

## 1. Executive Summary

| Total Targets Audited | Confirmed | Dismissed | Inconclusive | Hardening Patches Formulated |
| :---: | :---: | :---: | :---: | :---: |
| 4 | 0 | 3 | 1 | 4 (Complete Patch Set) |

All 4 adversarial hypotheses have been thoroughly investigated through physical sandboxed validation and in-memory unit PoC testing ([frontend/__tests__/notification-bound-refresh-sentinel.test.tsx](file:///d:/Project/tabiji/travel-pwa/frontend/__tests__/notification-bound-refresh-sentinel.test.tsx), 4/4 passing).

---

## 2. Adversarial Hypothesis Findings & In-Memory Proofs

### Target 1: `frontend/components/notifications/notification-bell.tsx:dos_flood_unauthenticated_refresh`
- **Vector**: `dos_flood_unauthenticated_refresh`
- **Hypothesis**: Rapid clicking on notification bell could flood backend Supabase notification queries and trigger broadcast cascades.
- **Physical Sandbox Verdict**: `DISMISSED`
- **Technical Analysis**:
  - `fetchNotifications` issues read-only SELECT queries with limit(30), which do not write to PostgreSQL WAL and cannot trigger Realtime broadcast cascades.
  - Queries are asynchronous (non-blocking).
  - Regardless, our candidate patch incorporates a strict **2000ms client-side debounce throttle** (`lastRefreshRef.current`), eliminating any possibility of UI/network thread congestion. Verified in PoC 1.

### Target 2: `frontend/components/notifications/notification-bell.tsx:animation_state_stagnation`
- **Vector**: `animation_state_stagnation`
- **Hypothesis**: Bell ringing animation state could remain true, preventing subsequent animation triggers.
- **Physical Sandbox Verdict**: `DISMISSED` (Not present in existing code; hardened in candidate patch).
- **Hardening Guard**:
  - In candidate patch, Framer Motion `<motion.div>` uses `onAnimationComplete={() => setIsRinging(false)}`.
  - Closing the notification panel is guarded by `if (nextOpen)`, guaranteeing that collapse actions are completely silent and never trigger refresh or animation. Verified in PoC 2 & PoC 3.

### Target 3: `frontend/components/itinerary/ItineraryHeader.tsx:interface_regression_on_refresh`
- **Vector**: `broken_access_control_or_interface_regression`
- **Hypothesis**: Removing `ZenRenew` might break `ItineraryHeaderProps.onRefresh`, breaking `TripMembersSheet.onMemberKicked`.
- **Physical Sandbox Verdict**: `DISMISSED`
- **Hardening Guard**:
  - Candidate patch retains `onRefresh?: () => Promise<void>` in `ItineraryHeaderProps` and forwards it cleanly to `<TripMembersSheet onMemberKicked={onRefresh} />`. Only the JSX `<ZenRenew ... />` button is unmounted.

### Target 4: `frontend/components/views/itinerary-view.tsx:unhandled_rejection_in_global_refresh`
- **Vector**: `unhandled_rejection_in_global_refresh`
- **Hypothesis**: Network dropouts or 500 errors during global refresh could cause unhandled promise rejections.
- **Physical Sandbox Verdict**: Hardened via `Promise.allSettled`.
- **Hardening Guard**:
  - Candidate patch wraps all global refresh handlers with `Promise.allSettled` and a `try...catch` block with graceful console warnings, ensuring 0 uncaught rejections bubble up to React error boundaries. Verified in PoC 4.

---

## 3. Sandboxed Unit Test Results (Vitest)
```text
RUN  v4.1.11 D:/Project/tabiji/travel-pwa/frontend
✓ __tests__/notification-bound-refresh-sentinel.test.tsx (4 tests) 5ms
  - PoC 1: 2000ms throttle defense blocks rapid clicking request flooding (PASSED)
  - PoC 2: Panel collapse action silence defense prevents redundant sync on close (PASSED)
  - PoC 3: Animation state reset prevents stagnation across click cycles (PASSED)
  - PoC 4: Error shielding with Promise.allSettled suppresses unhandled rejections (PASSED)

Test Files  1 passed (1)
     Tests  4 passed (4)
```

---

## 4. Human Gate Handover
- Candidate Patch: [patch_candidate_notification_refresh_2026-10-21.diff](file:///d:/Project/tabiji/travel-pwa/docs/security/patch_candidate_notification_refresh_2026-10-21.diff)
- Ready for Human Confirmation to apply.
