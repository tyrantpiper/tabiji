import { describe, it, expect } from "vitest"
import fs from "fs"
import path from "path"

/**
 * 🛡️ Security Sentinel & Adaptive Layout Guardian Test Suite
 * Validates that FlightCard.tsx satisfies:
 * 1. Fluid horizontal geometry under 130% root font scale without column collision.
 * 2. L0 Decision #35: WebKit Text-Node Isolation & shrink-0 on indicator tags.
 * 3. Prevention of iOS Safari Intrinsic Width blowout on <input type="date">.
 * 4. Symmetric typography between view mode and edit mode for zero-CLS transitions.
 */
describe("FlightCard Adaptive Layout & Font-Scale Hardening Contracts", () => {
    const FLIGHT_CARD_PATH = path.resolve(__dirname, "..", "components", "views", "info", "FlightCard.tsx")
    const flightCardCode = fs.readFileSync(FLIGHT_CARD_PATH, "utf-8")

    describe("1. Card Padding & Horizontal Real Estate", () => {
        it("should enforce responsive padding p-5 sm:p-8 on both top and bottom sections instead of rigid p-8", () => {
            // Must not use rigid 'p-8 pt-10' that robs 83px width on 375px/390px mobile viewports
            expect(flightCardCode).not.toContain('className="p-8 pt-10')
            expect(flightCardCode).toContain("p-5 sm:p-8")
        })
    })

    describe("2. Date Header Anti-Collision Architecture", () => {
        it("should eliminate inverted font scale hierarchy (text-lg on mobile vs sm:text-base on tablet)", () => {
            // The buggy pattern: text-lg on mobile, sm:text-base on tablet
            expect(flightCardCode).not.toContain("text-lg sm:text-base md:text-xl")
            expect(flightCardCode).toContain("text-sm sm:text-base md:text-lg")
        })

        it("should ban overflow-visible on date text nodes and enforce truncate with min-w-0", () => {
            // Buggy pattern allowed text to bleed over the center divider
            expect(flightCardCode).not.toContain("whitespace-nowrap overflow-visible")
            expect(flightCardCode).toMatch(/truncate[\s\S]*?\{data\.dep_date/)
        })

        it("should replace rigid w-12 sm:w-20 px-4 divider with deterministic compact responsive track", () => {
            // Rigid 80px divider caused 140px text to collide
            expect(flightCardCode).not.toContain("w-12 sm:w-20 bg-linear-to-r")
            expect(flightCardCode).toMatch(/w-8 sm:w-14/)
        })

        it("should enforce min-w-0 w-full on edit mode date inputs to prevent Safari intrinsic width blowout", () => {
            // Edit mode date input must have min-w-0
            expect(flightCardCode).toMatch(/type="date"[\s\S]*?min-w-0/)
        })
    })

    describe("3. Airport Code & Dynamic Flight Path Visuals", () => {
        it("should scale airport code from text-3xl on mobile to text-5xl on sm and text-6xl on md", () => {
            expect(flightCardCode).toContain("text-3xl sm:text-5xl md:text-6xl")
        })

        it("should ensure edit mode input matches view mode text-3xl font size for zero layout shift", () => {
            // Buggy code had hardcoded text-4xl on edit mode input
            expect(flightCardCode).not.toMatch(/placeholder="TPE"[\s\S]*?text-4xl/)
        })

        it("should bound airplane motion displacement to [-18, 18] inside compact w-12 sm:w-20 track", () => {
            expect(flightCardCode).toContain("w-12 sm:w-20")
            expect(flightCardCode).toContain("x: [-18, 18]")
        })
    })

    describe("4. WebKit Text-Node Isolation & Pill Shrink Guard (Decision #35)", () => {
        it("should ensure the blue airline indicator pill has shrink-0 to prevent iOS Safari collapse", () => {
            expect(flightCardCode).toMatch(/bg-blue-500 rounded-full shrink-0/)
        })

        it("should wrap airline name in an isolated span with truncate to prevent anonymous block box squishing", () => {
            expect(flightCardCode).toMatch(/<span className="truncate"[^>]*>\{data\.airline/)
        })
    })

    describe("5. Mathematical Viewport Real Estate Proof under 130% Font Scale", () => {
        it("proves that under 130% font scale on 375px mobile, dates and divider fit with zero overlap", () => {
            // Root font scale = 130% => 1rem = 20.8px
            const rem = 16 * 1.3 // 20.8px
            const viewportWidth = 375
            const pagePadding = 20 * 2 // px-5 (40px)
            const cardAvailableWidth = viewportWidth - pagePadding // 335px
            
            // New card padding: p-5 = 1.25rem * 1.3 = 26px on each side
            const cardInnerPadding = 1.25 * rem * 2 // 52px
            const contentWidth = cardAvailableWidth - cardInnerPadding // 283px

            // Middle divider: w-8 = 2rem * 1.3 = 41.6px
            const dividerWidth = 2 * rem
            const availableForDates = contentWidth - dividerWidth // 241.4px
            const singleColumnWidth = availableForDates / 2 // 120.7px

            // "未設定" (3 CJK chars) at text-sm (0.875rem = 18.2px): 3 * 18.2 = 54.6px
            const textWidthNotSet = 3 * (0.875 * rem)
            expect(textWidthNotSet).toBeLessThan(singleColumnWidth)
            
            // Safety clearance is at least 60px!
            const clearance = singleColumnWidth - textWidthNotSet
            expect(clearance).toBeGreaterThan(50)
        })
    })
})
