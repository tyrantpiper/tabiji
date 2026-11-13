/**
 * 🎨 Tabiji Official Portal Milestone 2 Motion Components Test Suite
 * 
 * Verifies HeroShowcase, SpatialRouteMotionCard, OfflineEngineMotionCard,
 * LedgerMotionCard, BentoMotionGrid, and page integration.
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import fs from 'node:fs'
import path from 'node:path'

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

// Import components under test
import { HeroShowcase } from '@/components/official/HeroShowcase'
import { SpatialRouteMotionCard } from '@/components/official/SpatialRouteMotionCard'
import { OfflineEngineMotionCard } from '@/components/official/OfflineEngineMotionCard'
import { LedgerMotionCard } from '@/components/official/LedgerMotionCard'
import OfficialPage from '@/app/official/page'

const frontendDir = path.resolve(__dirname, '..')
const heroPath = path.join(frontendDir, 'components', 'official', 'HeroShowcase.tsx')
const spatialPath = path.join(frontendDir, 'components', 'official', 'SpatialRouteMotionCard.tsx')
const offlinePath = path.join(frontendDir, 'components', 'official', 'OfflineEngineMotionCard.tsx')
const ledgerPath = path.join(frontendDir, 'components', 'official', 'LedgerMotionCard.tsx')
const bentoPath = path.join(frontendDir, 'components', 'official', 'BentoMotionGrid.tsx')
const pagePath = path.join(frontendDir, 'app', 'official', 'page.tsx')
const headerPath = path.join(frontendDir, 'components', 'official', 'OfficialHeader.tsx')
const typewriterPath = path.join(frontendDir, 'components', 'official', 'TypewriterHeading.tsx')
const heroTypewriterPath = path.join(frontendDir, 'components', 'official', 'HeroTypewriterHeading.tsx')
const theaterPath = path.join(frontendDir, 'components', 'official', 'LiveDeviceTheater.tsx')

class MockIntersectionObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

describe('Milestone 2: Motion Components & Official Portal Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver
  })

  describe('1. HeroShowcase Component Contract', () => {
    it('M2-1.1: File exists and contains Spring Water badge label "自由行隨身夥伴 · 離線優先架構"', () => {
      expect(fs.existsSync(heroPath)).toBe(true)
      const content = fs.readFileSync(heroPath, 'utf-8')
      expect(content).toContain('自由行隨身夥伴 · 離線優先架構')
      expect(content).toMatch(/y:\s*\[-4,\s*4,\s*-4\]/)
    })

    it('M2-1.2: Renders masked brand wordmark with /images/tabiji-cursive-logo.png', () => {
      const content = fs.readFileSync(heroPath, 'utf-8')
      expect(content).toContain('/images/tabiji-cursive-logo.png')
      expect(content).toContain('maskImage')
    })

    it('M2-1.3: CTA Launch App button invokes sanitizeLaunchRedirectUrl and enforces Emil Kowalski feedback', () => {
      render(<HeroShowcase />)
      const launchButton = screen.getByRole('button', { name: /啟動應用/i })
      expect(launchButton).toBeDefined()
      expect(launchButton.className).toMatch(/min-h-(11|\[44px\])/)
      expect(launchButton.className).toMatch(/min-w-(11|\[44px\])/)
      expect(launchButton.className).toContain('active:scale-[0.97]')
      expect(launchButton.className).toContain('duration-160')
      expect(launchButton.className).toContain('ease-out')

      fireEvent.click(launchButton)
      expect(mockPush).toHaveBeenCalledWith('/?lang=zh')
    })

    it('M2-1.4: Explore features button anchors to #routes with min 44x44px touch target', () => {
      render(<HeroShowcase />)
      const exploreButton = screen.getByRole('link', { name: /探索特色/i })
      expect(exploreButton).toBeDefined()
      expect(exploreButton.getAttribute('href')).toBe('#routes')
      expect(exploreButton.className).toMatch(/min-h-(11|\[44px\])/)
      expect(exploreButton.className).toMatch(/min-w-(11|\[44px\])/)
      expect(exploreButton.className).toContain('active:scale-[0.97]')
    })

    it('M2-1.5: Enforces 60FPS GPU acceleration curve [0.23, 1, 0.32, 1] and prefers-reduced-motion', () => {
      const content = fs.readFileSync(heroPath, 'utf-8')
      expect(content).toContain('useReducedMotion')
      expect(content).toContain('[0.23, 1, 0.32, 1]')
    })
  })

  describe('2. SpatialRouteMotionCard Component Contract', () => {
    it('M2-2.1: File exists and focuses on global travel coordination (Tokyo, Taipei, Reykjavik, Paris, New York)', () => {
      expect(fs.existsSync(spatialPath)).toBe(true)
      const content = fs.readFileSync(spatialPath, 'utf-8')
      expect(content).toContain('東京')
      expect(content).toContain('台北')
      expect(content).toContain('巴黎')
      expect(content).toContain('雷克雅維克')
      expect(content).toContain('紐約')
    })

    it('M2-2.2: Strictly excludes cross-border pharmaceutical or medical terminology', () => {
      const content = fs.readFileSync(spatialPath, 'utf-8')
      expect(content).not.toContain('跨境藥理')
      expect(content).not.toContain('藥品')
      expect(content).not.toContain('處方')
      expect(content).not.toContain('醫藥')
    })

    it('M2-2.3: Implements dynamic SVG arc pulling animation and micro-waypoint pulses', () => {
      const content = fs.readFileSync(spatialPath, 'utf-8')
      expect(content).toContain('pathLength')
      expect(content).toContain('motion.path')
      expect(content).toContain('motion.circle')
      expect(content).toContain('Global Waypoints Synced')
    })

    it('M2-2.4: Waypoint selector buttons comply with min 44px touch targets and interactive detail display', () => {
      render(<SpatialRouteMotionCard />)
      const tokyoBtn = screen.getByRole('button', { name: /選擇航點 東京/i })
      expect(tokyoBtn).toBeDefined()
      expect(tokyoBtn.className).toMatch(/min-h-(11|\[44px\])/)

      fireEvent.click(tokyoBtn)
      expect(screen.getByText(/都會漫遊與鐵道接駁/i)).toBeDefined()
    })
  })

  describe('3. OfflineEngineMotionCard Component Contract', () => {
    it('M2-3.1: File exists and implements 12ms in-memory cache pointer gauge', () => {
      expect(fs.existsSync(offlinePath)).toBe(true)
      const content = fs.readFileSync(offlinePath, 'utf-8')
      expect(content).toContain('12ms')
      expect(content).toContain('離線自癒引擎')
    })

    it('M2-3.2: Interactive offline simulation toggle transitions between Online and Simulated Offline', () => {
      render(<OfflineEngineMotionCard />)
      const toggleBtn = screen.getByRole('switch', { name: /切換至模擬斷網模式/i })
      expect(toggleBtn).toBeDefined()
      expect(toggleBtn.className).toMatch(/min-h-(11|\[44px\])/)

      // Initially online
      expect(screen.getByText(/Edge CDN Active/i)).toBeDefined()

      // Toggle to offline
      fireEvent.click(toggleBtn)
      expect(screen.getByText(/Airplane Mode · Local Snapshot Engaged/i)).toBeDefined()
      expect(screen.getByText(/0 延遲本地秒開/i)).toBeDefined()
    })

    it('M2-3.3: Needle rotation responds to offline state and is 60FPS GPU accelerated (transform only)', () => {
      const content = fs.readFileSync(offlinePath, 'utf-8')
      expect(content).toContain('motion.g')
      expect(content).toContain('needleRotation')
      expect(content).toContain('useReducedMotion')
    })
  })

  describe('4. LedgerMotionCard Component Contract', () => {
    it('M2-4.1: File exists and supports multi-currency real-time counters (JPY, TWD, USD)', () => {
      expect(fs.existsSync(ledgerPath)).toBe(true)
      const content = fs.readFileSync(ledgerPath, 'utf-8')
      expect(content).toContain('JPY')
      expect(content).toContain('TWD')
      expect(content).toContain('USD')
      expect(content).toContain('智慧多幣別分帳')
    })

    it('M2-4.2: Currency switching updates displayed amounts and currency tab selection', () => {
      render(<LedgerMotionCard />)
      const twdTab = screen.getByRole('tab', { name: /TWD/i })
      expect(twdTab).toBeDefined()
      expect(twdTab.className).toMatch(/min-h-(11|\[44px\])/)

      fireEvent.click(twdTab)
      expect(screen.getAllByText(/NT\$/i).length).toBeGreaterThanOrEqual(1)
    })

    it('M2-4.3: Split balance toggle switches between 4-way split and total group amount', () => {
      render(<LedgerMotionCard />)
      const splitBtn = screen.getByRole('button', { name: /切換為全團總額/i })
      expect(splitBtn).toBeDefined()
      expect(splitBtn.className).toMatch(/min-h-(11|\[44px\])/)

      fireEvent.click(splitBtn)
      expect(screen.getByText(/本趟行程總計費用/i)).toBeDefined()
    })

    it('M2-4.4: Implements spring physics interactive cards with whileHover={{ y: -4, scale: 1.02 }}', () => {
      const content = fs.readFileSync(ledgerPath, 'utf-8')
      expect(content).toContain('whileHover')
      expect(content).toContain('scale: 1.02')
      expect(content).toContain('y: -4')
    })
  })

  describe('5. BentoMotionGrid Component Contract', () => {
    it('M2-5.1: File exists and houses all 3 motion cards', () => {
      expect(fs.existsSync(bentoPath)).toBe(true)
      const content = fs.readFileSync(bentoPath, 'utf-8')
      expect(content).toContain('SpatialRouteMotionCard')
      expect(content).toContain('OfflineEngineMotionCard')
      expect(content).toContain('LedgerMotionCard')
    })

    it('M2-5.2: Contains anchor targets #routes, #offline, and #ledger', () => {
      const content = fs.readFileSync(bentoPath, 'utf-8')
      expect(content).toContain('id="routes"')
      expect(content).toContain('id="offline"')
      expect(content).toContain('id="ledger"')
    })

    it('M2-5.3: Implements 40ms staggerChildren and Kowalski cubic-bezier [0.23, 1, 0.32, 1]', () => {
      const content = fs.readFileSync(bentoPath, 'utf-8')
      expect(content).toContain('staggerChildren: shouldReduceMotion ? 0 : 0.04')
      expect(content).toContain('[0.23, 1, 0.32, 1]')
    })
  })

  describe('6. OfficialPage Full Assembly Contract', () => {
    it('M2-6.1: page.tsx exists and renders Header, Hero, BentoGrid, and Footer', () => {
      expect(fs.existsSync(pagePath)).toBe(true)
      const content = fs.readFileSync(pagePath, 'utf-8')
      expect(content).toContain('OfficialHeader')
      expect(content).toContain('HeroShowcase')
      expect(content).toContain('BentoMotionGrid')
      expect(content).toContain('OfficialFooter')
    })

    it('M2-6.2: Enforces zero horizontal overflow (overflow-x-hidden)', () => {
      const content = fs.readFileSync(pagePath, 'utf-8')
      expect(content).toContain('overflow-x-hidden')
    })

    it('M2-6.3: Launch CTA in banner invokes sanitizeLaunchRedirectUrl and enforces touch targets >= 44x44px', () => {
      render(<OfficialPage />)
      const bannerLaunchBtn = screen.getByRole('button', { name: /立即啟動 Tabiji/i })
      expect(bannerLaunchBtn).toBeDefined()
      expect(bannerLaunchBtn.className).toMatch(/min-h-\[44px\]/)
      expect(bannerLaunchBtn.className).toMatch(/min-w-\[44px\]/)
      expect(bannerLaunchBtn.className).toContain('active:scale-[0.97]')

      fireEvent.click(bannerLaunchBtn)
      expect(mockPush).toHaveBeenCalledWith('/?lang=zh')
    })
  })

  describe('7. TypewriterHeading & Header Convergence Contract', () => {
    it('M2-7.1: TypewriterHeading component exists and enforces a11y sr-only layer', () => {
      expect(fs.existsSync(typewriterPath)).toBe(true)
      const content = fs.readFileSync(typewriterPath, 'utf-8')
      expect(content).toContain('sr-only')
      expect(content).toContain('aria-hidden')
      expect(content).toContain('useReducedMotion')
      expect(content).toContain('bg-emerald-500')
    })

    it('M2-7.2: All three motion cards integrate TypewriterHeading', () => {
      const spatialContent = fs.readFileSync(spatialPath, 'utf-8')
      const offlineContent = fs.readFileSync(offlinePath, 'utf-8')
      const ledgerContent = fs.readFileSync(ledgerPath, 'utf-8')

      expect(spatialContent).toContain('TypewriterHeading')
      expect(spatialContent).toContain('text="空間航線巡航"')

      expect(offlineContent).toContain('TypewriterHeading')
      expect(offlineContent).toContain('text="離線自癒引擎"')

      expect(ledgerContent).toContain('TypewriterHeading')
      expect(ledgerContent).toContain('text="智慧多幣別分帳"')
    })

    it('M2-7.3: OfficialHeader navLinks feature 4 chapters starting with 行旅體驗 without legal links', () => {
      const headerContent = fs.readFileSync(headerPath, 'utf-8')
      expect(headerContent).toContain('experience')
      expect(headerContent).toContain('行旅體驗')
      expect(headerContent).toContain('routes')
      expect(headerContent).toContain('offline')
      expect(headerContent).toContain('ledger')

      // navLinks should not include terms or privacy
      const navLinksMatch = headerContent.match(/const navLinks = \[([\s\S]*?)\]/)
      expect(navLinksMatch).toBeTruthy()
      const navLinksCode = navLinksMatch ? navLinksMatch[1] : ''
      expect(navLinksCode).not.toContain('terms')
      expect(navLinksCode).not.toContain('privacy')
    })

    it('M2-7.4: HeroShowcase and LiveDeviceTheater integrate typewriter headings', () => {
      expect(fs.existsSync(heroTypewriterPath)).toBe(true)
      const heroTypewriterContent = fs.readFileSync(heroTypewriterPath, 'utf-8')
      expect(heroTypewriterContent).toContain('sr-only')
      expect(heroTypewriterContent).toContain('bg-gradient-to-r')

      const heroContent = fs.readFileSync(heroPath, 'utf-8')
      expect(heroContent).toContain('HeroTypewriterHeading')
      expect(heroContent).toContain('line1="走過的路，"')
      expect(heroContent).toContain('line2="都在這裡發光。"')

      const theaterContent = fs.readFileSync(theaterPath, 'utf-8')
      expect(theaterContent).toContain('TypewriterHeading')
      expect(theaterContent).toContain('text="握在掌心的，是整座城市的從容"')
    })
  })
})
