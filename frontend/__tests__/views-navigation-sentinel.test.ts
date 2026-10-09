import { describe, it, expect, vi } from "vitest"
import { openExternalLink } from "../lib/utils"

describe("🛡️ Security Sentinel: Views Navigation & Link Protocol Isolation", () => {
    it("strictly blocks malicious URI schemes from openExternalLink", () => {
        const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {})
        const openSpy = vi.spyOn(window, "open").mockImplementation(() => null)

        const maliciousUrls = [
            "javascript:alert(document.cookie)",
            "JAVASCRIPT:alert(1)",
            "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
            "vbscript:msgbox(1)",
            "file:///etc/passwd",
            "blob:http://malicious.com/uuid",
            "about:blank",
            "chrome://settings"
        ]

        maliciousUrls.forEach((url) => {
            openExternalLink(url)
            expect(openSpy).not.toHaveBeenCalled()
            expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining("[Security] Blocked unsafe external link protocol"))
            warnSpy.mockClear()
        })

        warnSpy.mockRestore()
        openSpy.mockRestore()
    })

    it("safely permits legitimate whitelist protocols", () => {
        const openSpy = vi.spyOn(window, "open").mockImplementation(() => null)

        const safeUrls = [
            "https://maps.google.com/?q=Tokyo",
            "http://example.com/hotel",
            "tel:+81312345678",
            "mailto:traveler@example.com",
            "maps://?q=Tokyo"
        ]

        safeUrls.forEach((url) => {
            openExternalLink(url)
            expect(openSpy).toHaveBeenCalledWith(url, "_blank", "noopener,noreferrer")
            openSpy.mockClear()
        })

        openSpy.mockRestore()
    })

    it("validates WCAG 2.1 AA/AAA contrast ratios for Tabiji Unified Palette", () => {
        // Luminance calculation helper per WCAG 2.1 specifications
        function getRelativeLuminance(r: number, g: number, b: number): number {
            const [rs, gs, bs] = [r, g, b].map(c => {
                const s = c / 255
                return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
            })
            return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs
        }

        function getContrastRatio(rgb1: [number, number, number], rgb2: [number, number, number]): number {
            const lum1 = getRelativeLuminance(...rgb1)
            const lum2 = getRelativeLuminance(...rgb2)
            const brightest = Math.max(lum1, lum2)
            const darkest = Math.min(lum1, lum2)
            return (brightest + 0.05) / (darkest + 0.05)
        }

        // Tabiji Color definitions
        // #F6F5EE = [246, 245, 238] (Warm Paper)
        // #1E2927 = [30, 41, 39] (Jade Charcoal text)
        // #121A18 = [18, 26, 24] (Midnight Dark bg)
        // #E5EBEA = [229, 235, 234] (Dark Mode main text)

        const lightPaperBg: [number, number, number] = [246, 245, 238]
        const lightMainText: [number, number, number] = [30, 41, 39]
        const darkMidnightBg: [number, number, number] = [18, 26, 24]
        const darkMainText: [number, number, number] = [229, 235, 234]

        const lightContrast = getContrastRatio(lightPaperBg, lightMainText)
        const darkContrast = getContrastRatio(darkMidnightBg, darkMainText)

        // WCAG AAA requires >= 7.0 for normal text
        expect(lightContrast).toBeGreaterThanOrEqual(7.0)
        expect(darkContrast).toBeGreaterThanOrEqual(7.0)
    })
})
