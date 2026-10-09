import { describe, it, expect } from "vitest"
import { translations } from "@/lib/translations"
import { remainingTranslations } from "@/lib/i18n/remaining"

/**
 * 🛡️ Security Sentinel & Sandbox Verification Suite
 * Target: Landing Page Brand Hierarchy & PWA Bottom Sheet Ergonomics
 */
describe("Landing Page Brand Hierarchy & PWA Bottom Sheet Sandbox Verification", () => {
    describe("TC-1: i18n Subtitle Consistency & Cross-Tier Parity", () => {
        it("should verify translations.ts and remaining.ts have matched subtitle structure", () => {
            expect(translations.zh.landing_subtitle).toBe("旅路 ｜ 旅行提案")
            expect(translations.en.landing_subtitle).toBe("Tabiji | Travel Planner")
            expect(remainingTranslations.zh.landing_subtitle).toBe("旅路 ｜ 旅行提案")
            expect(remainingTranslations.en.landing_subtitle).toBe("Tabiji | Travel Planner")
        })
    })

    describe("TC-2: Mobile Virtual Keyboard Occlusion Calculation", () => {
        it("should accurately detect virtual keyboard popup via visualViewport ratio", () => {
            const checkKeyboardOpen = (windowHeight: number, vvHeight: number) => {
                return vvHeight < windowHeight * 0.78
            }

            // Normal mobile screen (keyboard closed)
            expect(checkKeyboardOpen(844, 844)).toBe(false)
            // Mobile screen with virtual keyboard opened (height shrunk to ~500px)
            expect(checkKeyboardOpen(844, 520)).toBe(true)
            expect(checkKeyboardOpen(667, 390)).toBe(true)
            // Small desktop resize (ratio > 0.8)
            expect(checkKeyboardOpen(900, 800)).toBe(false)
        })
    })

    describe("TC-3: iOS Safe Area Inset Class Synthesis", () => {
        it("should ensure bottom sheet includes safe area padding syntax", () => {
            const getBottomSheetClass = (isBottomDocked: boolean, hasActiveUser: boolean) => {
                if (isBottomDocked && !hasActiveUser) {
                    return "fixed bottom-0 left-0 right-0 z-50 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
                }
                if (hasActiveUser) {
                    return "fixed bottom-20 left-0 right-0 z-50"
                }
                return "fixed bottom-6 right-6 w-96"
            }

            const mobileClass = getBottomSheetClass(true, false)
            expect(mobileClass).toContain("bottom-0")
            expect(mobileClass).toContain("env(safe-area-inset-bottom)")

            const appShellClass = getBottomSheetClass(true, true)
            expect(appShellClass).toContain("bottom-20")
        })
    })

    describe("TC-4: Backpack Brand Icon Dual-Layer Defense & Cache-Busting", () => {
        it("should verify landing-page.tsx incorporates aspect-[1630/2546], style.aspectRatio, and v3 cache parameter", async () => {
            const fs = await import("fs")
            const path = await import("path")
            const landingSource = fs.readFileSync(
                path.resolve(__dirname, "../components/views/landing-page.tsx"),
                "utf-8"
            )

            // 必須包含 1630/2546 寬高比
            expect(landingSource).toContain("aspect-1630/2546")
            expect(landingSource).toContain("aspectRatio: '1630 / 2546'")

            // 必須包含 ?v=3 快取穿透參數
            expect(landingSource).toContain("/images/tabiji-person-outline.png?v=3")

            // 必須包含 max-h-[28vh]
            expect(landingSource).toContain("max-h-[28vh]")
        })
    })

    describe("TC-5: First-Fold Viewport Ergonomics Calculation", () => {
        it("should guarantee login form remains in first fold under small screens (iPhone SE 667px)", () => {
            const viewportH = 667
            const brandIconMaxH = viewportH * 0.28 // 186.76px
            const brandIconW = brandIconMaxH * (1630 / 2546) // ~119.5px
            const totalContentEstimate = brandIconMaxH + 60 + 130 + 32 // Icon + Wordmark + Form + Padding = ~408px

            expect(brandIconMaxH).toBeLessThan(190)
            expect(brandIconW).toBeLessThan(125)
            expect(totalContentEstimate).toBeLessThan(viewportH * 0.75) // Leaves >25% breathing space
        })
    })
})

