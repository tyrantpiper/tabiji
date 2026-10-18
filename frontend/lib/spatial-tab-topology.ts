/**
 * 🧭 Tab Spatial Index Topology & Motion Mathematics
 * ====================================================
 * Pure functional spatial calculation for Dock tab transitions.
 * Eliminates mutable historical direction state drift and ensures
 * 100% deterministic spatial parallax matching physical user intuition.
 */

export const TAB_INDICES: Record<string, number> = {
    itinerary: 0,
    info: 1,
    tools: 2,
    profile: 3,
}

export const MOTION_CONFIG = {
    offsetPx: 28, // iOS Swift inspired subtle translation (±28px)
    spring: {
        type: "spring" as const,
        stiffness: 420,
        damping: 32,
    },
}

export type TabTransitionIntent = "dock" | "instant"

/**
 * Calculates deterministic X-axis offset for view transitions
 * @param targetTab The tab whose offset is being computed
 * @param currentActiveTab The currently active tab in the shell
 * @param intent 'dock' (spring slide) or 'instant' (contextual jump: deep link, cold boot)
 * @param isReducedMotion User accessibility preference
 * @returns Spatial offset in pixels (0, +28, or -28)
 */
export function calculateTabOffset(
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
