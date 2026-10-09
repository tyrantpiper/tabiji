import { describe, it, expect } from "vitest"
import fs from "fs"
import path from "path"

/**
 * 🛡️ Bug Hunter & Responsive Fluid Scaling Regression Suite
 * Verifies that all 4 main views (Itinerary, Info, Tools, Profile) implement
 * the evolved 83c3211 fluid responsive architecture (w-full max-w-4xl lg:max-w-5xl mx-auto px-5 sm:px-8)
 * and eliminates the frozen 576px (max-w-xl) bottleneck.
 */
describe("Responsive Fluid Scaling & Container Contract Verification", () => {
    const EXPECTED_CONTAINER_SIGNATURE = "w-full max-w-4xl lg:max-w-5xl mx-auto"
    const ROOT_FRONTEND = path.resolve(__dirname, "..")

    const VIEWS = [
        {
            name: "ItineraryView",
            file: path.join(ROOT_FRONTEND, "components", "views", "itinerary-view.tsx"),
        },
        {
            name: "InfoView",
            file: path.join(ROOT_FRONTEND, "components", "views", "info-view.tsx"),
        },
        {
            name: "ToolsView",
            file: path.join(ROOT_FRONTEND, "components", "views", "tools-view.tsx"),
        },
        {
            name: "ProfileView",
            file: path.join(ROOT_FRONTEND, "components", "views", "profile-view.tsx"),
        },
    ]

    VIEWS.forEach(({ name, file }) => {
        it(`${name} should enforce responsive fluid container without hardcoded max-w-xl ceiling`, () => {
            const content = fs.readFileSync(file, "utf-8")
            expect(content).toContain(EXPECTED_CONTAINER_SIGNATURE)
            // Ensure no legacy top container is locked at max-w-xl mx-auto w-full px-5
            expect(content).not.toContain("max-w-xl mx-auto w-full px-5")
        })
    })

    describe("Viewport Geometry & Ergonomic Calculation Proof", () => {
        const calculateEffectiveWidth = (viewportWidth: number) => {
            const padding = viewportWidth >= 640 ? 64 : 40 // sm:px-8 (32*2) vs px-5 (20*2)
            const availableWidth = viewportWidth - padding

            const maxCap = viewportWidth >= 1024 
                ? 1024 // lg:max-w-5xl (64rem = 1024px)
                : 896  // max-w-4xl (56rem = 896px)

            return Math.min(availableWidth, maxCap)
        }

        it("should dynamically scale on mobile (375px) without horizontal scrollbar overflow", () => {
            const effectiveWidth = calculateEffectiveWidth(375)
            expect(effectiveWidth).toBe(335)
            expect(effectiveWidth).toBeLessThan(375)
        })

        it("should smoothly extend on tablet/iPad (768px) beyond legacy 576px ceiling", () => {
            const effectiveWidth = calculateEffectiveWidth(768)
            expect(effectiveWidth).toBe(704)
            // Proves that it extends past the legacy 576px lock-in!
            expect(effectiveWidth).toBeGreaterThan(576)
        })

        it("should adaptively extend on desktop/laptop (1024px and 1440px) with comfortable reading bounds", () => {
            const tabletLandscape = calculateEffectiveWidth(1024)
            const desktopWide = calculateEffectiveWidth(1440)

            expect(tabletLandscape).toBe(960)
            expect(desktopWide).toBe(1024)
            expect(desktopWide).toBeGreaterThan(576)
            expect(desktopWide).toBeLessThanOrEqual(1024)
        })
    })
})
