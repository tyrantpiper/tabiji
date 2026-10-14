import { describe, it, expect } from "vitest"
import type { TripCapsuleEntry } from "@/lib/itinerary-types"

/**
 * 🛡️ Security Sentinel & Sandbox Verification Suite
 * Target 1: Trip Capsule Days Disconnect (totalDays fallback bug)
 * Target 2: Stale Index Out of Bounds in Multi-Traveler Carousel
 * Target 3: Multi-Traveler Pill Navigation & State Highlight
 * Target 4: Initial Day Clamp & Boundary Resilience
 */
describe("Trip Capsule Unveiling Days & Multi-Traveler Sentinel Suite", () => {
    // ──────── Mock Helpers & Algorithm Emulators ────────
    const calculateTripTotalDays = (
        startDate?: string,
        endDate?: string,
        daysArray?: { day: number }[]
    ): number => {
        let daysFromDates = 1
        if (startDate && endDate) {
            const [sy, sm, sd] = startDate.split("T")[0].split("-").map(Number)
            const [ey, em, ed] = endDate.split("T")[0].split("-").map(Number)
            const start = new Date(sy, sm - 1, sd)
            const end = new Date(ey, em - 1, ed)
            if (!isNaN(start.getTime()) && !isNaN(end.getTime())) {
                daysFromDates = Math.max(1, Math.round((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1)
            }
        }
        const maxDayFromItems =
            Array.isArray(daysArray) && daysArray.length > 0
                ? Math.max(...daysArray.map((d) => d.day || 1))
                : 1
        return Math.max(daysFromDates, maxDayFromItems)
    }

    const clampTravelerIndex = (currentIndex: number, listLength: number): number => {
        if (listLength <= 0) return 0
        return Math.min(Math.max(0, currentIndex), listLength - 1)
    }

    const clampInitialDay = (initialDay: number, totalDays: number): number => {
        if (initialDay < 1) return 1
        if (initialDay > totalDays) return totalDays
        return initialDay
    }

    describe("TC-1: In-Memory PoC - Days Disconnect Between Itinerary Calendar and Capsule Unveiling", () => {
        it("VULNERABILITY PROOF: Using currentTrip.days.length truncates empty/sparse 16-day trip to 1 day", () => {
            // A 16-day trip (2026-10-10 to 2026-10-25)
            // But only Day 1 has activities (days.length === 1)
            const mockTrip = {
                id: "00000000-0000-0000-0000-000000000010",
                title: "[Test] 雙人時光膠囊測試之旅 🌸",
                start_date: "2026-10-10",
                end_date: "2026-10-25",
                days: [{ day: 1, activities: [] }] // Only 1 day has activity record
            }

            // Vulnerable calculation in itinerary-view.tsx:L1984:
            // totalDays={currentTrip?.days?.length || currentTrip?.total_days || 1}
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const vulnerableTotalDays = mockTrip.days?.length || (mockTrip as any).total_days || 1

            // Generates Day buttons for the unveiling ceremony
            const renderedDays = Array.from({ length: vulnerableTotalDays }, (_, i) => i + 1)

            // Demonstrates the defect: Even though it's a 16-day trip, only Day 1 is accessible!
            expect(vulnerableTotalDays).toBe(1)
            expect(renderedDays).toEqual([1])
            expect(renderedDays.includes(2)).toBe(false)
            expect(renderedDays.includes(16)).toBe(false)
        })

        it("REMEDIATION PROOF: Using date-derived totalDays preserves the complete 16-day span", () => {
            const mockTrip = {
                id: "00000000-0000-0000-0000-000000000010",
                title: "[Test] 雙人時光膠囊測試之旅 🌸",
                start_date: "2026-10-10",
                end_date: "2026-10-25",
                days: [{ day: 1, activities: [] }]
            }

            // Fixed calculation: Use calculated totalDays
            const fixedTotalDays = calculateTripTotalDays(mockTrip.start_date, mockTrip.end_date, mockTrip.days)
            const renderedDays = Array.from({ length: fixedTotalDays }, (_, i) => i + 1)

            expect(fixedTotalDays).toBe(16)
            expect(renderedDays).toHaveLength(16)
            expect(renderedDays[0]).toBe(1)
            expect(renderedDays[15]).toBe(16)
        })
    })

    describe("TC-2: In-Memory PoC - Stale Index Out-of-Bounds in Multi-Traveler Carousel", () => {
        const mockEntries: TripCapsuleEntry[] = [
            // Day 1 has 3 travelers
            {
                id: "entry-d1-1",
                trip_id: "trip-1",
                day_number: 1,
                author_id: "user-1",
                author_name: "Owner",
                mood_emoji: "🥳",
                content: "Owner Note D1",
                is_sealed: false
            },
            {
                id: "entry-d1-2",
                trip_id: "trip-1",
                day_number: 1,
                author_id: "user-2",
                author_name: "Editor",
                mood_emoji: "🤩",
                content: "Editor Note D1",
                is_sealed: false
            },
            {
                id: "entry-d1-3",
                trip_id: "trip-1",
                day_number: 1,
                author_id: "user-3",
                author_name: "Viewer",
                mood_emoji: "✨",
                content: "Viewer Note D1",
                is_sealed: false
            },
            // Day 2 has only 1 traveler
            {
                id: "entry-d2-1",
                trip_id: "trip-1",
                day_number: 2,
                author_id: "user-1",
                author_name: "Owner",
                mood_emoji: "☕",
                content: "Owner Note D2",
                is_sealed: false
            }
        ]

        it("VULNERABILITY PROOF: Unclamped index when switching from 3-person day to 1-person day returns undefined entry", () => {
            // User was on Day 1, viewing 3rd traveler (index = 2)
            const currentTravelerIdx = 2
            const day2Entries = mockEntries.filter((e) => e.day_number === 2)

            // Vulnerable access without clamp:
            const rawEntry = day2Entries[currentTravelerIdx]

            // Causes UI to treat Day 2 as having no entries (empty state false positive!)
            expect(day2Entries).toHaveLength(1)
            expect(rawEntry).toBeUndefined()
        })

        it("REMEDIATION PROOF: Clamped safeTravelerIdx gracefully falls back to existing traveler", () => {
            const currentTravelerIdx = 2
            const day2Entries = mockEntries.filter((e) => e.day_number === 2)

            // Clamped access:
            const safeIdx = clampTravelerIndex(currentTravelerIdx, day2Entries.length)
            const safeEntry = day2Entries[safeIdx]

            expect(safeIdx).toBe(0)
            expect(safeEntry).toBeDefined()
            expect(safeEntry?.author_name).toBe("Owner")
            expect(safeEntry?.mood_emoji).toBe("☕")
        })
    })

    describe("TC-3: Multi-Traveler Navigation Pills Verification", () => {
        it("Generates correct traveler pills with active selection highlighting", () => {
            const day1Entries = [
                { id: "e1", author_name: "Owner", mood_emoji: "🥳" },
                { id: "e2", author_name: "Editor", mood_emoji: "🤩" },
                { id: "e3", author_name: "Aimee", mood_emoji: "🍜" }
            ]

            const selectedIdx = 1

            const pills = day1Entries.map((e, idx) => ({
                id: e.id,
                label: `${e.mood_emoji} ${e.author_name}`,
                isActive: idx === selectedIdx
            }))

            expect(pills).toHaveLength(3)
            expect(pills[0].isActive).toBe(false)
            expect(pills[1].isActive).toBe(true)
            expect(pills[1].label).toBe("🤩 Editor")
            expect(pills[2].isActive).toBe(false)
        })
    })

    describe("TC-4: Initial Day Clamp & Boundary Resilience", () => {
        it("Clamps negative or out-of-range initialDay safely within 1..totalDays", () => {
            const totalDays = 5

            expect(clampInitialDay(3, totalDays)).toBe(3)
            expect(clampInitialDay(0, totalDays)).toBe(1)
            expect(clampInitialDay(-5, totalDays)).toBe(1)
            expect(clampInitialDay(10, totalDays)).toBe(5)
            expect(clampInitialDay(999, totalDays)).toBe(5)
        })
    })
})
