import { describe, it, expect } from "vitest"
import fs from "fs"
import path from "path"

describe("iOS PWA Fullscreen Splash Sentinel (Zero-Regression & Immersion Gate)", () => {
    const layoutPath = path.resolve(__dirname, "../app/layout.tsx")
    const splashAnimPath = path.resolve(__dirname, "../components/ui/splash/tabiji-splash-animation.tsx")

    it("AC-1: layout.tsx must statically include apple-mobile-web-app-capable meta tag in <head>", () => {
        const layoutContent = fs.readFileSync(layoutPath, "utf-8")
        // iOS WebKit requires exact <meta name="apple-mobile-web-app-capable" content="yes" />
        expect(layoutContent).toContain('<meta name="apple-mobile-web-app-capable" content="yes"')
    })

    it("AC-2: layout.tsx must include black-translucent status bar and cover viewportFit", () => {
        const layoutContent = fs.readFileSync(layoutPath, "utf-8")
        expect(layoutContent).toContain('statusBarStyle: "black-translucent"')
        expect(layoutContent).toContain('viewportFit: "cover"')
    })

    it("AC-3: layout.tsx must include pre-hydration static root background style lock", () => {
        const layoutContent = fs.readFileSync(layoutPath, "utf-8")
        // Microsecond 0 root styling to prevent #FFFFFF flash
        expect(layoutContent).toContain("#F6F5EE")
        expect(layoutContent).toContain("#121A18")
    })

    it("AC-4: tabiji-splash-animation.tsx must remain pure without global DOM class mutation (Zero-Regression Gate)", () => {
        const animContent = fs.readFileSync(splashAnimPath, "utf-8")
        // Must NOT manipulate global documentElement classes to prevent React 19 timer cleanup regressions
        expect(animContent).not.toContain("classList.add")
        expect(animContent).not.toContain("classList.remove")
    })

    it("AC-5: tabiji-splash-animation.tsx must maintain full-screen overlay geometry", () => {
        const animContent = fs.readFileSync(splashAnimPath, "utf-8")
        expect(animContent).toContain("fixed inset-0")
        expect(animContent).toContain("99999")
    })
})
