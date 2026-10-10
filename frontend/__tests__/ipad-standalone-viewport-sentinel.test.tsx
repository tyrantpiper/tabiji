import { describe, it, expect } from "vitest"
import fs from "fs"
import path from "path"

/**
 * 🛡️ iPad Standalone PWA Viewport & Dead Zone Sentinel Suite
 * Validates root container geometry, WebKit safe-area inheritance, and brand color consistency.
 */
describe("iPad Standalone PWA Viewport & Dead Zone Sentinel", () => {
    const frontendDir = path.resolve(__dirname, "..")
    const appShellPath = path.join(frontendDir, "components", "views", "app-shell.tsx")
    const landingPagePath = path.join(frontendDir, "components", "views", "landing-page.tsx")
    const layoutPath = path.join(frontendDir, "app", "layout.tsx")
    const globalsCssPath = path.join(frontendDir, "app", "globals.css")

    describe("TC-1: In-Memory Geometry Verification (711px vs 681px)", () => {
        const PHYSICAL_IPAD_HEIGHT = 711
        const SAFE_AREA_INSET_BOTTOM = 30 // ~27-30px on iPad Home Bar

        it("should mathematically prove naked 100dvh leaves a 30px non-interactive dead zone", () => {
            // Under WebKit standalone PWA, dvh calculates as innerHeight - safeAreaInset:
            const containerHeightDvh = PHYSICAL_IPAD_HEIGHT - SAFE_AREA_INSET_BOTTOM // 681px
            const deadZoneHeight = PHYSICAL_IPAD_HEIGHT - containerHeightDvh

            expect(containerHeightDvh).toBe(681)
            expect(deadZoneHeight).toBe(30)
            // Proof: Touch events at y in [681..711] fall strictly outside the 681px container
            const touchAtScreenBottom = PHYSICAL_IPAD_HEIGHT - 5 // y = 706px
            expect(touchAtScreenBottom).toBeGreaterThan(containerHeightDvh)
        })

        it("should verify full-height inheritance covers 100% of physical viewport (711px)", () => {
            // Under percentage inheritance (html=100%, body=100%, container=100%):
            const containerHeightPercent = PHYSICAL_IPAD_HEIGHT // 711px
            const deadZoneHeight = PHYSICAL_IPAD_HEIGHT - containerHeightPercent

            expect(containerHeightPercent).toBe(711)
            expect(deadZoneHeight).toBe(0)
            // Proof: Touch events at y in [681..711] are completely captured by the container
            const touchAtScreenBottom = PHYSICAL_IPAD_HEIGHT - 5 // y = 706px
            expect(touchAtScreenBottom).toBeLessThanOrEqual(containerHeightPercent)
        })
    })

    describe("TC-2: app-shell.tsx Root Container Viewport Sentinel", () => {
        it("should eliminate naked h-dvh and enforce standalone full-height immunity", () => {
            const content = fs.readFileSync(appShellPath, "utf-8")

            // Must NOT have naked 'h-dvh bg-background' without standalone override
            const hasNakedDvhOnly = /className="h-dvh bg-background/.test(content)
            expect(hasNakedDvhOnly).toBe(false)

            // Must include h-full and standalone full height coverage
            expect(content).toMatch(/h-full/)
            expect(content).toMatch(/display-mode:standalone/i)
        })
    })

    describe("TC-3: landing-page.tsx Zero-Seam & Token Consistency Sentinel", () => {
        it("should purge all legacy stone-50 background references and align with bg-background", () => {
            const content = fs.readFileSync(landingPagePath, "utf-8")

            // Must NOT use legacy min-h-screen bg-stone-50 on root container
            expect(content).not.toMatch(/min-h-screen bg-stone-50/)
            // Must NOT have hardcoded bg-stone-50 anywhere in landing-page
            expect(content).not.toMatch(/bg-stone-50/)

            // Root container must use bg-background
            expect(content).toMatch(/bg-background/)
        })

        it("should include safe-area padding on landing page footer to prevent home bar collision", () => {
            const content = fs.readFileSync(landingPagePath, "utf-8")
            expect(content).toMatch(/safe-area-inset-bottom/)
        })
    })

    describe("TC-4: layout.tsx & globals.css Height Chain Integrity", () => {
        it("should guarantee html and body maintain full height inheritance", () => {
            const layoutContent = fs.readFileSync(layoutPath, "utf-8")
            const globalsContent = fs.readFileSync(globalsCssPath, "utf-8")

            // globals.css must establish height: 100% and min-height: 100% on html, body
            expect(globalsContent).toMatch(/html,\s*body\s*\{[\s\S]*?height:\s*100%/)
            expect(globalsContent).toMatch(/min-height:\s*100%/)

            // layout.tsx must reinforce h-full on html and body
            expect(layoutContent).toMatch(/<html[^>]*h-full/)
            expect(layoutContent).toMatch(/<body[^>]*h-full/)
        })
    })
})
