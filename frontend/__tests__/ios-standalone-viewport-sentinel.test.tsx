import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

describe('iOS/iPadOS Standalone Viewport & Animation Completion Sentinel Tests', () => {
    const appShellPath = path.resolve(__dirname, '../components/views/app-shell.tsx')
    const layoutPath = path.resolve(__dirname, '../app/layout.tsx')
    const splashPath = path.resolve(__dirname, '../components/ui/splash/tabiji-splash-animation.tsx')
    const homeDashboardPath = path.resolve(__dirname, '../components/itinerary/TabijiHomeDashboard.tsx')

    it('TC-1: Guard against WebKit 100dvh truncation defect in app-shell root container', () => {
        const content = fs.readFileSync(appShellPath, 'utf-8')
        // Must NOT use h-dvh for root container (causes 64px deadzone in iOS standalone WebClips)
        expect(content).not.toMatch(/<div className="h-dvh /)
        // Must strictly use h-screen to fill 100% physical viewport
        expect(content).toMatch(/<div className="h-screen bg-background flex flex-col overflow-hidden">/)
    })

    it('TC-2: Guard top floating controls against dynamic island / status bar collision', () => {
        const content = fs.readFileSync(appShellPath, 'utf-8')
        // AIStatusButton and Notification controls must include env(safe-area-inset-top)
        expect(content).toContain('top-[calc(max(env(safe-area-inset-top,0px),0px)+0.5rem)]')
    })

    it('TC-3: Guard TabijiHomeDashboard header against tablet status bar overlap', () => {
        const content = fs.readFileSync(homeDashboardPath, 'utf-8')
        // Header must incorporate safe-area-inset-top dynamically for both mobile and tablet breakpoints
        expect(content).toContain('pt-[calc(max(env(safe-area-inset-top,0px),0px)+3.5rem)]')
        expect(content).toContain('sm:pt-[calc(max(env(safe-area-inset-top,0px),0px)+2.5rem)]')
    })

    it('TC-4: Guarantee Apple PWA standalone meta tags in layout.tsx head', () => {
        const content = fs.readFileSync(layoutPath, 'utf-8')
        expect(content).toContain('<meta name="apple-mobile-web-app-capable" content="yes" />')
        expect(content).toContain('<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />')
    })

    it('TC-5: Guarantee splash animation lifecycle covers full airplane trajectory (>= 2400ms)', () => {
        const content = fs.readFileSync(splashPath, 'utf-8')
        // Timer must be at least 2400ms to allow 2.0s airplane flight + graceful golden aurora fade
        expect(content).toMatch(/setTimeout\(\(\)\s*=>\s*\{\s*onComplete\?\.?\(\)\s*\}, 2400\)/)
    })
})
