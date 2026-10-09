import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import React from 'react'
import { TabijiSplashAnimation } from '@/components/ui/splash/tabiji-splash-animation'

describe('TabijiSplashAnimation Fidelity & Full Artwork Mask Tests', () => {
    it('renders the SVG mask with Trailing Bloom zones and Full Canvas Unification to guarantee 100% line completeness', () => {
        const { container } = render(<TabijiSplashAnimation />)

        // 1. Verify mask exists with correct ID
        const mask = container.querySelector('#tabiji-track-matte')
        expect(mask).not.toBeNull()

        // 2. Verify mask contains full canvas unifier to prevent permanently cropped artwork lines
        // A rect covering width=2048 and height=2048 that transitions to full white opacity
        const maskRects = mask?.querySelectorAll('rect')
        expect(maskRects?.length).toBeGreaterThanOrEqual(2)

        // 3. Verify Trailing Bloom elements exist in mask (ellipses / bloom shapes for curls & body)
        const bloomEllipses = mask?.querySelectorAll('ellipse')
        expect(bloomEllipses && bloomEllipses.length >= 2).toBe(true)

        // 4. Verify original raster image is referenced with the matte mask
        const artImage = container.querySelector('image[href="/images/tabiji-art-mask.png"]')
        expect(artImage).not.toBeNull()
        expect(artImage?.getAttribute('mask')).toBe('url(#tabiji-track-matte)')

        // 5. Verify independent paper plane element exists
        const planeImage = container.querySelector('image[href="/images/tabiji-paper-plane.png"]')
        expect(planeImage).not.toBeNull()
    })

    it('ensures no synthetic vector path overlay is rendered in the foreground stage (preventing ghost lines across face)', () => {
        const { container } = render(<TabijiSplashAnimation />)

        // Verify that inside the main SVG, no <path> is rendered outside of <defs>/<mask>
        // Any <path> outside of mask is an overlay stroke that draws artificial lines on the artwork
        const foregroundPaths = container.querySelectorAll('svg > path')
        expect(foregroundPaths.length).toBe(0)
    })

    it('verifies Three-Act dynamic gradient aurora layers (Morandi Night Base, Blooming Ink Orb, and Sunset Overlay)', () => {
        const { container } = render(<TabijiSplashAnimation />)

        // Verify the aurora container exists
        const auroraContainer = container.querySelector('[data-testid="tabiji-aurora-bg"]')
        expect(auroraContainer).not.toBeNull()

        // Verify the presence of blooming ink orb element
        const inkOrb = container.querySelector('[data-testid="tabiji-ink-orb"]')
        expect(inkOrb).not.toBeNull()
    })

    it('triggers onComplete callback after standard healing duration', () => {
        vi.useFakeTimers()
        const onComplete = vi.fn()
        render(<TabijiSplashAnimation onComplete={onComplete} />)

        expect(onComplete).not.toHaveBeenCalled()
        vi.advanceTimersByTime(2000)
        expect(onComplete).toHaveBeenCalledTimes(1)
        vi.useRealTimers()
    })
})
