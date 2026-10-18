import { describe, it, expect } from "vitest"

/**
 * 🛡️ Security Sentinel In-Memory PoC Test Suite: Dock Transitions & Spatial Topology
 * =================================================================================
 * Empirically proves:
 * PoC 1: BottomNav onTabChange bypass flaw (direction freeze vulnerability)
 * PoC 2: Relative spatial index topology guarantees deterministic direction without history pollution
 * PoC 3: Atomic transition intent prevents 'instant' mode deadlock
 * PoC 4: Accessibility reduced-motion gate defense
 */

const TAB_INDICES: Record<string, number> = {
    itinerary: 0,
    info: 1,
    tools: 2,
    profile: 3,
}

const MOTION_CONFIG = {
    offsetPx: 28,
    spring: {
        type: "spring" as const,
        stiffness: 420,
        damping: 32,
    },
}

type TabTransitionIntent = "dock" | "instant"

function calculateTabOffset(
    targetTab: string,
    currentActiveTab: string,
    intent: TabTransitionIntent = "dock",
    isReducedMotion: boolean = false
): number {
    if (isReducedMotion || intent === "instant" || targetTab === currentActiveTab) {
        return 0
    }
    const targetIdx = TAB_INDICES[targetTab] ?? 0
    const currentIdx = TAB_INDICES[currentActiveTab] ?? 0
    return targetIdx > currentIdx ? MOTION_CONFIG.offsetPx : -MOTION_CONFIG.offsetPx
}

describe("🛡️ Security Sentinel: Dock Direction-Aware Transitions", () => {
    it("PoC 1: Proves BottomNav onTabChange bypass freezes direction at initial state", () => {
        const state = {
            activeView: "itinerary",
            direction: 1,
            prevView: "itinerary",
        }

        const handleTabChange = (nextTab: string) => {
            const prevIdx = TAB_INDICES[state.prevView] ?? 0
            const nextIdx = TAB_INDICES[nextTab] ?? 0
            state.direction = nextIdx >= prevIdx ? 1 : -1
            state.prevView = nextTab
            state.activeView = nextTab
        }

        const setActiveView = (nextTab: string) => {
            state.activeView = nextTab
        }

        // 1. Move forward: itinerary (0) -> profile (3)
        handleTabChange("profile")
        expect(state.activeView).toBe("profile")
        expect(state.direction).toBe(1)
        expect(state.prevView).toBe("profile")

        // 2. DEFECT REPRODUCTION: BottomNav passes onTabChange={setActiveView}
        // Moving backward: profile (3) -> itinerary (0) via direct setActiveView
        setActiveView("itinerary")

        // Flaw: activeView changed, but direction is stuck at 1 (wrong slide direction!)
        expect(state.activeView).toBe("itinerary")
        expect(state.direction).toBe(1) // 🚨 VULNERABILITY: direction is frozen!
        expect(state.prevView).toBe("profile")

        // If proper handler were used:
        handleTabChange("itinerary")
        expect(state.direction).toBe(-1) // ✅ Correct direction
    })

    it("PoC 2: Proves Relative Spatial Topology mathematically eliminates history drift", () => {
        // Active tab is 'profile' (3). User clicks 'itinerary' (0).
        // Itinerary (0) relative to current active (3): 0 < 3 -> must be parked at -28px (left side)
        const incomingOffset = calculateTabOffset("itinerary", "profile", "dock", false)
        expect(incomingOffset).toBe(-28) // Will slide from -28 to 0 (Left-to-Right)

        // Active tab is 'itinerary' (0). User clicks 'profile' (3).
        // Profile (3) relative to current active (0): 3 > 0 -> must be parked at +28px (right side)
        const forwardOffset = calculateTabOffset("profile", "itinerary", "dock", false)
        expect(forwardOffset).toBe(28) // Will slide from +28 to 0 (Right-to-Left)

        // Active tab is 'tools' (2). User clicks 'info' (1).
        const stepBackOffset = calculateTabOffset("info", "tools", "dock", false)
        expect(stepBackOffset).toBe(-28) // Will slide from -28 to 0 (Left-to-Right)
    })

    it("PoC 3: Proves Intent-Scoped Transitions prevent 'instant' mode deadlock", () => {
        let currentIntent: TabTransitionIntent = "instant"

        // 1. Deep link sets intent to 'instant'
        const handleNavigation = (tab: string, intent: TabTransitionIntent) => {
            currentIntent = intent
            return calculateTabOffset(tab, "itinerary", currentIntent, false)
        }

        const deepLinkOffset = handleNavigation("profile", "instant")
        expect(deepLinkOffset).toBe(0) // Zero displacement for deep link

        // 2. Subsequent manual dock click sets intent to 'dock'
        const dockClickOffset = handleNavigation("tools", "dock")
        expect(dockClickOffset).toBe(28) // Properly slides in, no deadlock!
    })

    it("PoC 4: Proves reduced-motion gate unconditionally forces zero displacement", () => {
        const offsetWithReducedMotion = calculateTabOffset("profile", "itinerary", "dock", true)
        expect(offsetWithReducedMotion).toBe(0)

        const reverseOffsetWithReducedMotion = calculateTabOffset("itinerary", "profile", "dock", true)
        expect(reverseOffsetWithReducedMotion).toBe(0)
    })
})
