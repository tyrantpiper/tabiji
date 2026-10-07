import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, fireEvent, act, renderHook } from "@testing-library/react"
import React from "react"
import { useIdleBreathing } from "@/lib/hooks/useIdleBreathing"
import { FloatingMapCapsule } from "@/components/itinerary/FloatingMapCapsule"
import { ItineraryHeader } from "@/components/itinerary/ItineraryHeader"

// Mock LanguageContext & Haptic
vi.mock("@/lib/LanguageContext", () => ({
    useLanguage: () => ({ lang: "zh", t: (k: string) => k })
}))

vi.mock("@/lib/hooks", () => ({
    useHaptic: () => ({
        selection: vi.fn(),
        impact: vi.fn(),
        success: vi.fn(),
        error: vi.fn(),
        warning: vi.fn()
    })
}))

vi.mock("@/components/trip-switcher", () => ({
    TripSwitcher: () => <div data-testid="trip-switcher" />
}))

vi.mock("@/components/itinerary/ShareButton", () => ({
    ShareButton: () => <div data-testid="share-button" />
}))

vi.mock("@/components/itinerary/TripMembersSheet", () => ({
    TripMembersSheet: () => <div data-testid="trip-members-sheet" />
}))

vi.mock("@/components/ui/zen-renew", () => ({
    ZenRenew: () => <div data-testid="zen-renew" />
}))

describe("🌬️ useIdleBreathing Hook", () => {
    beforeEach(() => {
        vi.useFakeTimers()
    })

    afterEach(() => {
        vi.useRealTimers()
    })

    it("starts in awake state (isDimmed: false) and dims after 2500ms", () => {
        const dummyScroller = document.createElement("div")
        const { result } = renderHook(() => useIdleBreathing(dummyScroller, { idleTimeoutMs: 2500, enabled: true }))

        expect(result.current.isDimmed).toBe(false)

        act(() => {
            vi.advanceTimersByTime(2500)
        })

        expect(result.current.isDimmed).toBe(true)
    })

    it("does not dim when enabled is false", () => {
        const dummyScroller = document.createElement("div")
        const { result } = renderHook(() => useIdleBreathing(dummyScroller, { idleTimeoutMs: 2500, enabled: false }))

        expect(result.current.isDimmed).toBe(false)

        act(() => {
            vi.advanceTimersByTime(5000)
        })

        expect(result.current.isDimmed).toBe(false)
    })

    it("wakes up immediately when scrollerEl emits scroll event", () => {
        const dummyScroller = document.createElement("div")
        const { result } = renderHook(() => useIdleBreathing(dummyScroller, { idleTimeoutMs: 2500, enabled: true }))

        act(() => {
            vi.advanceTimersByTime(2500)
        })
        expect(result.current.isDimmed).toBe(true)

        act(() => {
            dummyScroller.dispatchEvent(new Event("scroll"))
        })

        expect(result.current.isDimmed).toBe(false)

        act(() => {
            vi.advanceTimersByTime(2500)
        })
        expect(result.current.isDimmed).toBe(true)
    })

    it("stays awake during mouse interaction and dims 2500ms after leave", () => {
        const dummyScroller = document.createElement("div")
        const { result } = renderHook(() => useIdleBreathing(dummyScroller, { idleTimeoutMs: 2500, enabled: true }))

        act(() => {
            vi.advanceTimersByTime(2500)
        })
        expect(result.current.isDimmed).toBe(true)

        // Mouse enters
        act(() => {
            result.current.handlers.onPointerEnter({ pointerType: "mouse" } as React.PointerEvent)
        })
        expect(result.current.isDimmed).toBe(false)

        // Still awake while mouse inside even after 3s
        act(() => {
            vi.advanceTimersByTime(3000)
        })
        expect(result.current.isDimmed).toBe(false)

        // Mouse leaves
        act(() => {
            result.current.handlers.onPointerLeave({ pointerType: "mouse" } as React.PointerEvent)
        })
        expect(result.current.isDimmed).toBe(false)

        // Dims 2.5s after leave
        act(() => {
            vi.advanceTimersByTime(2500)
        })
        expect(result.current.isDimmed).toBe(true)
    })
})

describe("🗺️ FloatingMapCapsule Idle Breathing", () => {
    beforeEach(() => {
        vi.useFakeTimers()
    })

    afterEach(() => {
        vi.useRealTimers()
    })

    it("dims to opacity-20 after 2.5s idle when visible", () => {
        // Create mock DOM for scroller and map
        const scroller = document.createElement("div")
        scroller.scrollTop = 300
        const mapEl = document.createElement("div")
        mapEl.id = "day-route-map-container"
        document.body.appendChild(mapEl)

        const { container } = render(
            <FloatingMapCapsule scrollerEl={scroller} activityCount={3} />
        )

        // Advance animation frame for initial scroll check
        act(() => {
            vi.advanceTimersByTime(50)
        })

        const button = container.querySelector("button")
        expect(button).toBeTruthy()
        expect(button?.className).toContain("opacity-100")

        // Wait 2500ms idle
        act(() => {
            vi.advanceTimersByTime(2500)
        })

        expect(button?.className).toContain("opacity-20")

        // Touch wakes it up
        if (button) {
            fireEvent.touchStart(button)
        }
        expect(button?.className).toContain("opacity-100")

        document.body.removeChild(mapEl)
    })
})

describe("🗓️ ItineraryHeader Sticky Idle Breathing", () => {
    beforeEach(() => {
        vi.useFakeTimers()
    })

    afterEach(() => {
        vi.useRealTimers()
    })

    const headerProps = {
        dayNumbers: [1, 2, 3],
        day: 1,
        setDay: vi.fn(),
        onBack: vi.fn(),
        onDeleteDay: vi.fn(),
        getDateInfo: () => ({ date: "10/10", week: "Sat" }),
        userId: "test-user",
        onRefresh: vi.fn(async () => {}),
        shouldShowDateSkeleton: false
    }

    it("stays opacity-100 at top of page (scrollTop <= 120)", () => {
        const scroller = document.createElement("div")
        scroller.scrollTop = 50

        const { container } = render(
            <ItineraryHeader {...headerProps} scrollerEl={scroller} />
        )

        act(() => {
            vi.advanceTimersByTime(3000)
        })

        const stickyBar = container.querySelector(".sticky")
        expect(stickyBar?.className).toContain("opacity-100")
        expect(stickyBar?.className).not.toContain("opacity-20")
    })

    it("dims to opacity-20 when sticky (scrollTop > 120) after 2.5s idle", () => {
        const scroller = document.createElement("div")
        scroller.scrollTop = 200

        const { container } = render(
            <ItineraryHeader {...headerProps} scrollerEl={scroller} />
        )

        // Advance RAF
        act(() => {
            vi.advanceTimersByTime(50)
        })

        const stickyBar = container.querySelector(".sticky")
        expect(stickyBar?.className).toContain("opacity-100")

        // Idle 2500ms in sticky state
        act(() => {
            vi.advanceTimersByTime(2500)
        })

        expect(stickyBar?.className).toContain("opacity-20")

        // Scroll back to top -> instantly wakes to opacity-100
        act(() => {
            scroller.scrollTop = 0
            scroller.dispatchEvent(new Event("scroll"))
            vi.advanceTimersByTime(50)
        })

        expect(stickyBar?.className).toContain("opacity-100")
    })
})
