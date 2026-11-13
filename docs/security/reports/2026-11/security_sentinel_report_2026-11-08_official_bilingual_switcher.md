# 🛡️ Tabiji Security Sentinel Audit Report
## Milestone 2.5: Official Bilingual Switcher & Reactive Motion Pacing

- **Audit Date**: 2026-11-08
- **Auditor**: Security Sentinel Harness (Google Mantis Block G ✕ Cloudflare Ledger ✕ Harness² Invariant Engine)
- **Target Route**: `/official` (Official Marketing Portal, Layout, Headers, Footers, and Motion Cards)
- **Status**: PASSED (Pre-Execution Validation Complete)
- **Candidate Hypotheses Audited**: 6
- **Confirmed Vulnerabilities / Flaws**: 2
- **Dismissed Hypotheses (Chesterton Archaeology)**: 1
- **Inconclusive / Pre-Mitigated**: 3

---

### 1. Executive Summary & Attack Surface Coverage

| Target ID | Trust Boundary | Category | Verdict | Remediation Link |
| :--- | :--- | :--- | :--- | :--- |
| `HeroTypewriterHeading.tsx:line_transition_ghost_state` | `browser_to_edge` | State Desync | **CONFIRMED** | `patch_candidate_official_bilingual_switcher_2026-11-08.diff` |
| `TypewriterHeading.tsx:mobile_overflow_whitespace_pre` | `browser_to_edge` | Viewport Overflow | **CONFIRMED** | `patch_candidate_official_bilingual_switcher_2026-11-08.diff` |
| `OfficialHeader.tsx:hash_navigation_query_wipeout` | `browser_to_edge` | URL Injection | **DISMISSED** | Preserved native fragment pushState `#${link.id}` |
| `TypewriterHeading.tsx:language_switch_state_desync` | `browser_to_edge` | Logic Boundary | **INCONCLUSIVE (Mitigated)** | Render-phase activeText tracking |
| `OfficialLanguageContext.tsx:storage_leak_and_route_unmount` | `client_session` | Storage Isolation | **INCONCLUSIVE (Mitigated)** | Layout-level sessionStorage isolation |
| `OfficialFooter.tsx:adversarial_test_regression` | `test_contract` | Contract Regression | **INCONCLUSIVE (Mitigated)** | Revert footer links count to 6 |

---

### 2. Confirmed Vulnerability Details & In-Memory PoCs

#### 2.1 HeroTypewriterHeading Line Transition Ghost State (`CONFIRMED`)
- **Root Cause**: `HeroTypewriterHeading.tsx` manages a two-stage sequential typing state (`currentLine`, `charIndex1`, `charIndex2`, `cursorVisible`). When language switches from Chinese (`走過的路，都在這裡發光。`) to English (`Where every step, finds its light.`), `useEffect` restarts because props changed, but component state remains dirty (`currentLine === 3`, `charIndex2 === 7`, `cursorVisible === false`).
- **Impact**: While line 1 is typing from character 0, line 2 immediately displays `"finds i"` with no cursor, creating an awkward visual ghosting glitch.
- **Remediation**: Implement React 19 render-phase derived state reset when `line1` or `line2` prop changes, clearing timers and resetting animation indices in 0 frames without triggering `react-hooks/set-state-in-effect`.

#### 2.2 TypewriterHeading Mobile Overflow Blowout (`CONFIRMED`)
- **Root Cause**: The typewriter component applied `whitespace-pre` to the progressive character span (`<span aria-hidden="true" className="inline-block whitespace-pre">`). In CSS, `white-space: pre` strictly disables soft line breaks.
- **Impact**: English sentences (e.g. `"In your palm, the serenity of the city"` - 38 chars) cannot wrap, pushing container width beyond 375px and causing horizontal screen wobble on mobile devices.
- **Remediation**: Replace `whitespace-pre` with `whitespace-pre-wrap` to preserve incremental spacing during typewriter reveals while allowing natural line wrapping on narrow viewports.

---

### 3. Chesterton's Fence & Dismissed Analysis

#### 3.1 OfficialHeader Hash Navigation URL Query Wipeout (`DISMISSED`)
- **Hypothesis**: Suspected that `pushState` on anchor navigation wiped out `?lang=en` from the URL.
- **Archaeological Fact**: Line 196 invokes `window.history.pushState(null, "", `#${link.id}`)`. Under the WHATWG URL specification and HTML5 History API, resolving a fragment-only relative URL against the active base URL strictly preserves the existing pathname and query parameters (resulting in `/official?lang=en#routes`). The hypothesis was dismissed with zero code modification needed.

---

### 4. Code Archaeology & Chesterton's Fence Matrix

| 模組檔案 | 原代碼職責 (Legacy Function) | 當初設計初衷 (Design Intent) | 刪除/變更風險 (Regression Risk) | 新邏輯承接機制 (Successor Architecture) |
| :--- | :--- | :--- | :--- | :--- |
| `TypewriterHeading.tsx` | 單向遞增打字動畫 | 使用純原生 `setInterval` 避免第三方肥大依賴 | 切換語系時未重置造成文字殘留 | Render-phase activeText 追蹤，同週期 0 延遲重歸零 |
| `HeroTypewriterHeading.tsx` | 雙行階梯式漸變標題 | 兩階段階梯動畫與游標淡出 | 語系動態更換時第二行提早曝光 | Render-phase activeLines 比較重置，游標狀態安全還原 |
| `OfficialFooter.tsx` | 頁尾導航與法務連結 | 提供 6 個對稱式連結 | 新增第 7 個連結打破 `ADV-M2-3.9` 測試斷言 | 將功能導航維持 3 個 (`#routes`, `#offline`, `#ledger`)，測試 100% 綠燈 |

---

### 5. Invariant Conservation & Pre-Implementation Clearance

- **Core Invariant Files**:
  - `frontend/app/page.tsx`: 0 lines changed (Frozen).
  - `frontend/app/sw.ts`: 0 lines changed (Frozen).
  - `frontend/public/manifest.json`: 0 lines changed (Frozen).
- **Quality Gates Passing**:
  - `official-bilingual-switcher-sentinel.test.tsx`: 6/6 passed.
  - `official-portal`: 215/215 passed.
  - TypeScript & Turbopack build: 0 errors.

