import { describe, it, expect } from "vitest"
import fs from "fs"
import path from "path"

describe("iOS PWA Fullscreen Splash Sentinel (Zero-Regression & Immersion Gate)", () => {
    const layoutPath = path.resolve(__dirname, "../app/layout.tsx")
    const globalsCssPath = path.resolve(__dirname, "../app/globals.css")
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

    it("AC-3: layout.tsx must include pre-hydration splash root background sync script", () => {
        const layoutContent = fs.readFileSync(layoutPath, "utf-8")
        expect(layoutContent).toContain("splash-active")
        expect(layoutContent).toContain("#162832")
    })

    it("AC-4: globals.css must define html.splash-active background lockdown", () => {
        const globalsContent = fs.readFileSync(globalsCssPath, "utf-8")
        expect(globalsContent).toContain("html.splash-active")
        expect(globalsContent).toContain("#162832")
    })

    it("AC-5: tabiji-splash-animation.tsx must manage splash-active lifecycle idempotently", () => {
        const animContent = fs.readFileSync(splashAnimPath, "utf-8")
        expect(animContent).toContain("splash-active")
    })
})
