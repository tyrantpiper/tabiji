/**
 * ⚔️ Tabiji Milestone 2: Adversarial RWD & Responsiveness Challenge Test Suite
 * 
 * Verifies:
 * 1. Zero horizontal overflow (overflow-x-hidden & overflow-hidden containment)
 * 2. Strict minimum 44x44px touch target ergonomics across all interactive elements
 * 3. Emil Kowalski active micro-feedback tokens (active:scale-[0.97] + 160ms ease-out)
 * 4. Invariant files (frontend/app/page.tsx, sw.ts, manifest.json) 100% untouched
 * 5. Viewport responsiveness matrix (375px Mobile -> 1920px Desktop)
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import fs from 'node:fs'
import path from 'node:path'
import { execSync } from 'node:child_process'

// Mock next/navigation
const mockPush = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
  usePathname: () => '/official',
}))

// Import components
import OfficialPage from '@/app/official/page'
import { HeroShowcase } from '@/components/official/HeroShowcase'
import { SpatialRouteMotionCard } from '@/components/official/SpatialRouteMotionCard'
import { OfflineEngineMotionCard } from '@/components/official/OfflineEngineMotionCard'
import { LedgerMotionCard } from '@/components/official/LedgerMotionCard'
import { OfficialHeader } from '@/components/official/OfficialHeader'

const frontendDir = path.resolve(__dirname, '..')
const repoRoot = path.resolve(frontendDir, '..')

class MockIntersectionObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

describe('⚔️ Tabiji Milestone 2 Adversarial Challenge: RWD & Responsiveness Harness', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver
  })

  // =========================================================================
  // Challenge 1: Physical File Invariants (Untouched & Frozen)
  // =========================================================================
  describe('Challenge 1: Invariant Files Physical Integrity', () => {
    it('ADV-M2-1.1: frontend/app/page.tsx has zero git modifications', () => {
      const status = execSync('git status --porcelain frontend/app/page.tsx', {
        cwd: repoRoot,
        encoding: 'utf-8',
      }).trim()
      expect(status).toBe('')
    })

    it('ADV-M2-1.2: frontend/app/sw.ts enforces Security Sentinel API isolation, fallback shell & zero dead bgSync', () => {
      const swContent = fs.readFileSync(path.join(frontendDir, 'app', 'sw.ts'), 'utf-8')
      expect(swContent).toContain('isSensitiveOrDynamicApiRequest')
      expect(swContent).toContain('isExternalCdnImageRequest')
      expect(swContent).toContain('sanitizePushLink')
      expect(swContent).toContain('app-shell-navigation')
      expect(swContent).toContain('fallbacks:')
      expect(swContent).not.toContain('BackgroundSyncPlugin')
    })

    it('ADV-M2-1.3: frontend/public/manifest.json has zero git modifications', () => {
      const status = execSync('git status --porcelain frontend/public/manifest.json', {
        cwd: repoRoot,
        encoding: 'utf-8',
      }).trim()
      expect(status).toBe('')
    })

    it('ADV-M2-1.4: git diff against HEAD shows zero changes in portal/manifest invariant files', () => {
      const diff = execSync(
        'git diff HEAD -- frontend/app/page.tsx frontend/public/manifest.json',
        { cwd: repoRoot, encoding: 'utf-8' }
      ).trim()
      expect(diff).toBe('')
    })
  })

  // =========================================================================
  // Challenge 2: Zero Horizontal Page Overflow & Scrollbar Wobble Prevention
  // =========================================================================
  describe('Challenge 2: Zero Horizontal Page Wobble & Overflow Containment', () => {
    it('ADV-M2-2.1: Root wrapper of official/page.tsx strictly enforces overflow-x-hidden and w-full', () => {
      const pageFile = path.join(frontendDir, 'app', 'official', 'page.tsx')
      const content = fs.readFileSync(pageFile, 'utf-8')
      expect(content).toContain('overflow-x-hidden')
      expect(content).toContain('w-full')
      expect(content).toContain('min-h-screen')
    })

    it('ADV-M2-2.2: HeroShowcase section explicitly enforces overflow-hidden to clip blur glows on mobile', () => {
      const heroFile = path.join(frontendDir, 'components', 'official', 'HeroShowcase.tsx')
      const content = fs.readFileSync(heroFile, 'utf-8')
      // Outer section must contain overflow-hidden
      expect(content).toMatch(/<section[^>]*overflow-hidden[^>]*>/)
    })

    it('ADV-M2-2.3: BentoMotionGrid container explicitly enforces overflow-hidden', () => {
      const bentoFile = path.join(frontendDir, 'components', 'official', 'BentoMotionGrid.tsx')
      const content = fs.readFileSync(bentoFile, 'utf-8')
      expect(content).toMatch(/<section[^>]*overflow-hidden[^>]*>/)
    })

    it('ADV-M2-2.4: SpatialRouteMotionCard container strictly enforces overflow-hidden', () => {
      const spatialFile = path.join(frontendDir, 'components', 'official', 'SpatialRouteMotionCard.tsx')
      const content = fs.readFileSync(spatialFile, 'utf-8')
      expect(content).toContain('overflow-hidden')
      expect(content).toMatch(/aspect-(?:\[600\/320\]|\[15\/8\]|15\/8)/)
    })

    it('ADV-M2-2.5: OfflineEngineMotionCard container strictly enforces overflow-hidden and gauge constraint', () => {
      const offlineFile = path.join(frontendDir, 'components', 'official', 'OfflineEngineMotionCard.tsx')
      const content = fs.readFileSync(offlineFile, 'utf-8')
      expect(content).toContain('overflow-hidden')
      expect(content).toContain('max-w-[280px]')
    })

    it('ADV-M2-2.6: LedgerMotionCard container strictly enforces overflow-hidden and responsive flex layout', () => {
      const ledgerFile = path.join(frontendDir, 'components', 'official', 'LedgerMotionCard.tsx')
      const content = fs.readFileSync(ledgerFile, 'utf-8')
      expect(content).toContain('overflow-hidden')
      expect(content).toContain('flex-1')
    })

    it('ADV-M2-2.7: Launch CTA Banner in page.tsx encloses decorative elements within overflow-hidden', () => {
      const pageFile = path.join(frontendDir, 'app', 'official', 'page.tsx')
      const content = fs.readFileSync(pageFile, 'utf-8')
      // Banner container
      expect(content).toMatch(/rounded-3xl[^>]*overflow-hidden[^>]*flex flex-col md:flex-row/)
    })

    it('ADV-M2-2.8: OfficialHeader uses safe viewport calculation w-[calc(100%-1.5rem)] preventing screen-edge collision', () => {
      const headerFile = path.join(frontendDir, 'components', 'official', 'OfficialHeader.tsx')
      const content = fs.readFileSync(headerFile, 'utf-8')
      expect(content).toContain('w-[calc(100%-1.5rem)]')
    })

    it('ADV-M2-2.9: No Milestone 2 component contains unconstrained fixed-width classes (>320px) that cause 375px mobile overflow', () => {
      const m2Files = [
        path.join(frontendDir, 'app', 'official', 'page.tsx'),
        path.join(frontendDir, 'components', 'official', 'HeroShowcase.tsx'),
        path.join(frontendDir, 'components', 'official', 'SpatialRouteMotionCard.tsx'),
        path.join(frontendDir, 'components', 'official', 'OfflineEngineMotionCard.tsx'),
        path.join(frontendDir, 'components', 'official', 'LedgerMotionCard.tsx'),
        path.join(frontendDir, 'components', 'official', 'BentoMotionGrid.tsx'),
      ]

      for (const file of m2Files) {
        const content = fs.readFileSync(file, 'utf-8')
        // Look for fixed pixel widths like w-[400px], w-[500px] without sm:, md:, lg: prefixes
        const fixedWidthMatches = content.match(/(?<!sm:|md:|lg:|xl:)w-\[(\d+)px\]/g) || []
        for (const match of fixedWidthMatches) {
          const pixelVal = parseInt(match.replace(/[^0-9]/g, ''), 10)
          // Any unconstrained fixed width on mobile root must not exceed 343px (375px - 32px padding)
          // unless contained within an absolute or overflow-hidden wrapper (e.g. ambient glow w-[340px])
          expect(pixelVal).toBeLessThanOrEqual(343)
        }
      }
    })
  })

  // =========================================================================
  // Challenge 3: Strict Minimum 44x44px Touch Target Standard
  // =========================================================================
  describe('Challenge 3: Touch Target Ergonomics (Minimum 44x44px)', () => {
    it('ADV-M2-3.1: HeroShowcase primary CTA satisfies min-h-[44px] and min-w-[44px]', () => {
      render(<HeroShowcase />)
      const btn = screen.getByRole('button', { name: /啟動應用/i })
      expect(btn.className).toMatch(/min-h-(11|\[44px\])/)
      expect(btn.className).toMatch(/min-w-(11|\[44px\])/)
    })

    it('ADV-M2-3.2: HeroShowcase secondary anchor satisfies min-h-[44px] and min-w-[44px]', () => {
      render(<HeroShowcase />)
      const link = screen.getByRole('link', { name: /探索特色/i })
      expect(link.className).toMatch(/min-h-(11|\[44px\])/)
      expect(link.className).toMatch(/min-w-(11|\[44px\])/)
    })

    it('ADV-M2-3.3: SpatialRouteMotionCard waypoint selector buttons satisfy min-h-[44px]', () => {
      render(<SpatialRouteMotionCard />)
      const waypoints = ['台北', '東京', '雷克雅維克', '巴黎', '紐約']
      for (const name of waypoints) {
        const btn = screen.getByRole('button', { name: new RegExp(`選擇航點 ${name}`, 'i') })
        expect(btn).toBeDefined()
        expect(btn.className).toMatch(/min-h-(11|\[44px\])/)
      }
    })

    it('ADV-M2-3.4: OfflineEngineMotionCard simulation toggle satisfies min-h-[44px] and min-w-[44px]', () => {
      render(<OfflineEngineMotionCard />)
      const toggle = screen.getByRole('switch')
      expect(toggle.className).toMatch(/min-h-(11|\[44px\])/)
      expect(toggle.className).toMatch(/min-w-(11|\[44px\])/)
    })

    it('ADV-M2-3.5: LedgerMotionCard split calculation toggle satisfies min-h-[44px] and min-w-[44px]', () => {
      render(<LedgerMotionCard />)
      const splitBtn = screen.getByRole('button', { name: /切換為全團總額/i })
      expect(splitBtn.className).toMatch(/min-h-(11|\[44px\])/)
      expect(splitBtn.className).toMatch(/min-w-(11|\[44px\])/)
    })

    it('ADV-M2-3.6: LedgerMotionCard currency switcher tabs (JPY, TWD, USD) satisfy min-h-[44px]', () => {
      render(<LedgerMotionCard />)
      const tabs = ['JPY', 'TWD', 'USD']
      for (const tab of tabs) {
        const tabEl = screen.getByRole('tab', { name: new RegExp(tab, 'i') })
        expect(tabEl.className).toMatch(/min-h-(11|\[44px\])/)
      }
    })

    it('ADV-M2-3.7: OfficialPage Launch CTA Banner buttons satisfy min-h-[44px] and min-w-[44px]', () => {
      render(<OfficialPage />)
      const launchBtn = screen.getByRole('button', { name: /立即啟動 Tabiji/i })
      expect(launchBtn.className).toMatch(/min-h-(11|\[44px\])/)
      expect(launchBtn.className).toMatch(/min-w-(11|\[44px\])/)

      const termsLink = screen.getByRole('link', { name: /查閱服務條款/i })
      expect(termsLink.className).toMatch(/min-h-(11|\[44px\])/)
      expect(termsLink.className).toMatch(/min-w-(11|\[44px\])/)
    })

    it('ADV-M2-3.8: OfficialHeader interactive buttons satisfy min-h-[44px] and min-w-[44px]', () => {
      render(<OfficialHeader />)
      const ctaBtn = screen.getByRole('button', { name: /啟動應用/i })
      expect(ctaBtn.className).toMatch(/min-h-(11|\[44px\])/)
      expect(ctaBtn.className).toMatch(/min-w-(11|\[44px\])/)

      const menuBtn = screen.getByRole('button', { name: /開啟選單/i })
      expect(menuBtn.className).toMatch(/min-h-(11|\[44px\])/)
      expect(menuBtn.className).toMatch(/min-w-(11|\[44px\])/)
    })

    it('ADV-M2-3.9: OfficialFooter navigation and legal links satisfy min-h-[44px]', () => {
      const footerFile = path.join(frontendDir, 'components', 'official', 'OfficialFooter.tsx')
      const content = fs.readFileSync(footerFile, 'utf-8')
      const linkMatches = content.match(/<Link[\s\S]*?className="([^"]*)"/g) || []
      // Skip the brand logo link (href="/official")
      const textLinks = linkMatches.filter((m) => !m.includes('href="/official"'))
      expect(textLinks.length).toBe(6)
      for (const link of textLinks) {
        expect(link).toMatch(/min-h-(11|\[44px\])/)
      }
    })
  })

  // =========================================================================
  // Challenge 4: Emil Kowalski Active Micro-Feedback Tokens
  // =========================================================================
  describe('Challenge 4: Emil Kowalski Active Feedback Tokens Across All CTA Buttons', () => {
    it('ADV-M2-4.1: HeroShowcase Primary CTA enforces active:scale-[0.97] + 160ms ease-out', () => {
      render(<HeroShowcase />)
      const btn = screen.getByRole('button', { name: /啟動應用/i })
      expect(btn.className).toContain('active:scale-[0.97]')
      expect(btn.className).toContain('duration-160')
      expect(btn.className).toContain('ease-out')
    })

    it('ADV-M2-4.2: HeroShowcase Secondary CTA enforces active:scale-[0.97] + 160ms ease-out', () => {
      render(<HeroShowcase />)
      const link = screen.getByRole('link', { name: /探索特色/i })
      expect(link.className).toContain('active:scale-[0.97]')
      expect(link.className).toContain('duration-160')
      expect(link.className).toContain('ease-out')
    })

    it('ADV-M2-4.3: OfficialPage Banner Launch CTA enforces active:scale-[0.97] + 160ms ease-out', () => {
      render(<OfficialPage />)
      const btn = screen.getByRole('button', { name: /立即啟動 Tabiji/i })
      expect(btn.className).toContain('active:scale-[0.97]')
      expect(btn.className).toContain('duration-160')
      expect(btn.className).toContain('ease-out')
    })

    it('ADV-M2-4.4: OfficialPage Banner Terms Link enforces active:scale-[0.97] + 160ms ease-out', () => {
      render(<OfficialPage />)
      const link = screen.getByRole('link', { name: /查閱服務條款/i })
      expect(link.className).toContain('active:scale-[0.97]')
      expect(link.className).toContain('duration-160')
      expect(link.className).toContain('ease-out')
    })

    it('ADV-M2-4.5: SpatialRouteMotionCard waypoint buttons enforce active:scale-[0.97] + 160ms ease-out', () => {
      render(<SpatialRouteMotionCard />)
      const btn = screen.getByRole('button', { name: /選擇航點 東京/i })
      expect(btn.className).toContain('active:scale-[0.97]')
      expect(btn.className).toContain('duration-160')
      expect(btn.className).toContain('ease-out')
    })

    it('ADV-M2-4.6: OfflineEngineMotionCard simulation toggle enforces active:scale-[0.97] + 160ms ease-out', () => {
      render(<OfflineEngineMotionCard />)
      const toggle = screen.getByRole('switch')
      expect(toggle.className).toContain('active:scale-[0.97]')
      expect(toggle.className).toContain('duration-160')
      expect(toggle.className).toContain('ease-out')
    })

    it('ADV-M2-4.7: LedgerMotionCard split toggle & currency tabs enforce active:scale-[0.97] + 160ms ease-out', () => {
      render(<LedgerMotionCard />)
      const splitBtn = screen.getByRole('button', { name: /切換為全團總額/i })
      expect(splitBtn.className).toContain('active:scale-[0.97]')
      expect(splitBtn.className).toContain('duration-160')
      expect(splitBtn.className).toContain('ease-out')

      const jpyTab = screen.getByRole('tab', { name: /JPY/i })
      expect(jpyTab.className).toContain('active:scale-[0.97]')
      expect(jpyTab.className).toContain('duration-160')
      expect(jpyTab.className).toContain('ease-out')
    })

    it('ADV-M2-4.8: OfficialHeader Launch CTA enforces active:scale-[0.97] + 160ms ease-out', () => {
      render(<OfficialHeader />)
      const headerBtn = screen.getByRole('button', { name: /啟動應用/i })
      expect(headerBtn.className).toContain('active:scale-[0.97]')
      expect(headerBtn.className).toContain('duration-160')
      expect(headerBtn.className).toContain('ease-out')
    })
  })

  // =========================================================================
  // Challenge 5: Viewport Responsiveness Matrix (375px Mobile -> 1920px Desktop)
  // =========================================================================
  describe('Challenge 5: Responsive Web Design Breakpoint Architecture', () => {
    it('ADV-M2-5.1: BentoMotionGrid scales from 1 col on mobile to 3 cols on desktop (grid-cols-1 lg:grid-cols-3)', () => {
      const bentoFile = path.join(frontendDir, 'components', 'official', 'BentoMotionGrid.tsx')
      const content = fs.readFileSync(bentoFile, 'utf-8')
      expect(content).toContain('grid-cols-1')
      expect(content).toContain('lg:grid-cols-3')
    })

    it('ADV-M2-5.2: Architecture highlights scale responsively (grid-cols-1 md:grid-cols-2 lg:grid-cols-4)', () => {
      const pageFile = path.join(frontendDir, 'app', 'official', 'page.tsx')
      const content = fs.readFileSync(pageFile, 'utf-8')
      expect(content).toContain('grid-cols-1')
      expect(content).toContain('md:grid-cols-2')
      expect(content).toContain('lg:grid-cols-4')
    })

    it('ADV-M2-5.3: OfficialFooter scales from 1 col on mobile to 4 cols on desktop (grid-cols-1 md:grid-cols-4)', () => {
      const footerFile = path.join(frontendDir, 'components', 'official', 'OfficialFooter.tsx')
      const content = fs.readFileSync(footerFile, 'utf-8')
      expect(content).toContain('grid-cols-1')
      expect(content).toContain('md:grid-cols-4')
    })

    it('ADV-M2-5.4: Launch CTA banner switches from vertical on mobile to horizontal on desktop (flex-col md:flex-row)', () => {
      const pageFile = path.join(frontendDir, 'app', 'official', 'page.tsx')
      const content = fs.readFileSync(pageFile, 'utf-8')
      expect(content).toContain('flex flex-col md:flex-row')
    })

    it('ADV-M2-5.5: Max-width constraints (max-w-5xl, max-w-6xl, max-w-7xl) prevent distortion on 1920px Full HD monitors', () => {
      const pageFile = path.join(frontendDir, 'app', 'official', 'page.tsx')
      const content = fs.readFileSync(pageFile, 'utf-8')
      expect(content).toContain('max-w-7xl')
      expect(content).toContain('max-w-5xl')

      const headerFile = path.join(frontendDir, 'components', 'official', 'OfficialHeader.tsx')
      expect(fs.readFileSync(headerFile, 'utf-8')).toContain('max-w-6xl')

      const footerFile = path.join(frontendDir, 'components', 'official', 'OfficialFooter.tsx')
      expect(fs.readFileSync(footerFile, 'utf-8')).toContain('max-w-6xl')
    })

    it('ADV-M2-5.6: Mobile hamburger menu toggle responds to user click with accessible ARIA attributes', () => {
      render(<OfficialHeader />)
      const menuBtn = screen.getByRole('button', { name: /開啟選單/i })
      expect(menuBtn.getAttribute('aria-expanded')).toBe('false')

      // Open menu
      fireEvent.click(menuBtn)
      const closeBtn = screen.getByRole('button', { name: /關閉選單/i })
      expect(closeBtn.getAttribute('aria-expanded')).toBe('true')
      expect(screen.getByRole('button', { name: /啟動應用 \(Launch App\)/i })).toBeDefined()

      // Close menu
      fireEvent.click(closeBtn)
      const reopenedBtn = screen.getByRole('button', { name: /開啟選單/i })
      expect(reopenedBtn.getAttribute('aria-expanded')).toBe('false')
    })

    it('ADV-M2-5.7: Typography uses fluid responsive breakpoints to prevent mobile wrapping blowout', () => {
      const heroFile = path.join(frontendDir, 'components', 'official', 'HeroShowcase.tsx')
      const heroContent = fs.readFileSync(heroFile, 'utf-8')
      expect(heroContent).toContain('text-3xl sm:text-5xl md:text-6xl')
      expect(heroContent).toContain('break-words')

      const pageFile = path.join(frontendDir, 'app', 'official', 'page.tsx')
      const pageContent = fs.readFileSync(pageFile, 'utf-8')
      expect(pageContent).toContain('text-2xl sm:text-4xl')
    })

    it('ADV-M2-5.8: Mobile-first full-width stacking on Launch Banner buttons (w-full sm:w-auto)', () => {
      const pageFile = path.join(frontendDir, 'app', 'official', 'page.tsx')
      const pageContent = fs.readFileSync(pageFile, 'utf-8')
      expect(pageContent).toContain('w-full sm:w-auto')
    })

    it('ADV-M2-5.9: Long content truncation and overflow guards in Ledger subcards (truncate)', () => {
      const ledgerFile = path.join(frontendDir, 'components', 'official', 'LedgerMotionCard.tsx')
      const ledgerContent = fs.readFileSync(ledgerFile, 'utf-8')
      expect(ledgerContent).toContain('truncate')
      expect(ledgerContent).toContain('min-w-0')
    })

    it('ADV-M2-5.10: SpatialRouteMotionCard SVG coordinate boundaries are within 600x320 viewBox', () => {
      const spatialFile = path.join(frontendDir, 'components', 'official', 'SpatialRouteMotionCard.tsx')
      const content = fs.readFileSync(spatialFile, 'utf-8')
      expect(content).toContain('viewBox="0 0 600 320"')

      // Verify all waypoint coordinates (x, y) fit within [0, 600] and [0, 320]
      const coordMatches = content.matchAll(/x:\s*(\d+),\s*y:\s*(\d+)/g)
      let count = 0
      for (const m of coordMatches) {
        count++
        const x = parseInt(m[1], 10)
        const y = parseInt(m[2], 10)
        expect(x).toBeGreaterThanOrEqual(0)
        expect(x).toBeLessThanOrEqual(600)
        expect(y).toBeGreaterThanOrEqual(0)
        expect(y).toBeLessThanOrEqual(320)
      }
      expect(count).toBe(5)
    })
  })
})
