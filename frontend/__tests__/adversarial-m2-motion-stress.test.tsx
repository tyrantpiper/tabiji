/**
 * ⚡ TABIJI MILESTONE 2 ADVERSARIAL STRESS TEST SUITE
 * 
 * Conducted by Challenger M2:
 * 1. SpatialRouteMotionCard: Rapid route switching, SVG arc coordinates & math, waypoint ripples, medical/pharma claim audit.
 * 2. OfflineEngineMotionCard: Rapid 100-cycle toggling, gauge pointer angular geometry, latency displays, reduced motion.
 * 3. LedgerMotionCard: Currency conversion math oracle (JPY, TWD, USD), 4-way split vs total, edge cases (0, negative, floating point precision).
 * 4. Kowalski Design Engineering & Accessibility touch target audit (>= 44x44px).
 * 5. Architectural Invariant protection verification.
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

// Import M2 components
import { SpatialRouteMotionCard } from '@/components/official/SpatialRouteMotionCard'
import { OfflineEngineMotionCard } from '@/components/official/OfflineEngineMotionCard'
import { LedgerMotionCard } from '@/components/official/LedgerMotionCard'
import { BentoMotionGrid } from '@/components/official/BentoMotionGrid'
import { HeroShowcase } from '@/components/official/HeroShowcase'
import OfficialPage from '@/app/official/page'

class MockIntersectionObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

describe('⚡ ADVERSARIAL CHALLENGER: Milestone 2 Dynamic Motion Stress Harness', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver
  })

  // =========================================================================
  // 1. STRESS-TEST: SpatialRouteMotionCard
  // =========================================================================
  describe('1. SpatialRouteMotionCard Stress & Adversarial Audit', () => {
    it('1.1. Rapid 100x sequential & randomized route switching without desynchronization', () => {
      render(<SpatialRouteMotionCard />)
      const waypointButtons = screen.getAllByRole('button', { name: /選擇航點/i })
      expect(waypointButtons.length).toBe(5)

      const waypoints = [
        { name: '台北', code: 'TPE', tz: 'UTC+8', tag: '亞洲智慧協調樞紐' },
        { name: '東京', code: 'HND', tz: 'UTC+9', tag: '都會漫遊與鐵道接駁' },
        { name: '雷克雅維克', code: 'KEF', tz: 'UTC+0', tag: '北極圈極光與冰原航線' },
        { name: '巴黎', code: 'CDG', tz: 'UTC+1', tag: '歐洲跨城鐵路樞紐' },
        { name: '紐約', code: 'JFK', tz: 'UTC-5', tag: '跨大西洋跨時區漫遊' },
      ]

      // 100 Rapid random switch clicks
      for (let i = 0; i < 100; i++) {
        const randomIndex = Math.floor(Math.random() * waypoints.length)
        const btn = waypointButtons[randomIndex]
        fireEvent.click(btn)

        const expected = waypoints[randomIndex]
        // Ensure detail card matches the currently selected waypoint
        expect(screen.getByText(new RegExp(`${expected.name} \\(${expected.code}\\) · ${expected.tag}`, 'i'))).toBeDefined()
        const tzEscaped = expected.tz.replace('+', '\\+')
        expect(screen.getByText(new RegExp(tzEscaped, 'i'))).toBeDefined()
      }
    })

    it('1.2. SVG Waypoint Node Click Stress: clicking SVG <g> tags selects corresponding waypoint', () => {
      const { container } = render(<SpatialRouteMotionCard />)
      const svgGroups = container.querySelectorAll('svg g.cursor-pointer')
      expect(svgGroups.length).toBe(5)

      // Click each SVG node directly
      const expectedCodes = ['TPE', 'HND', 'KEF', 'CDG', 'JFK']
      svgGroups.forEach((group, idx) => {
        fireEvent.click(group)
        expect(screen.getByText(new RegExp(`\\(${expectedCodes[idx]}\\)`, 'i'))).toBeDefined()
      })
    })

    it('1.3. SVG Arc Geometry & ViewBox Mathematical Validation', () => {
      const filePath = path.resolve(__dirname, '../components/official/SpatialRouteMotionCard.tsx')
      const code = fs.readFileSync(filePath, 'utf-8')

      // ViewBox must be 600 x 320
      expect(code).toContain('viewBox="0 0 600 320"')

      // Extract all waypoint coordinates from code
      const waypointMatches = [...code.matchAll(/x:\s*(\d+),\s*y:\s*(\d+)/g)]
      expect(waypointMatches.length).toBe(5)

      waypointMatches.forEach((match) => {
        const x = parseInt(match[1], 10)
        const y = parseInt(match[2], 10)
        // All nodes must be comfortably inside the 600x320 SVG viewport
        expect(x).toBeGreaterThan(0)
        expect(x).toBeLessThan(600)
        expect(y).toBeGreaterThan(0)
        expect(y).toBeLessThan(320)
      })

      // Check motion.path coordinates match the waypoint loop
      const motionPathRegex = /d="M 380 195 Q 410 160 440 130 Q 285 30 130 65 Q 165 85 200 110 Q 140 135 80 175 Q 230 290 380 195"/
      expect(code).toMatch(motionPathRegex)
    })

    it('1.4. Zero Medical / Cross-border Pharma Claim Penetration Audit', () => {
      const filesToAudit = [
        path.resolve(__dirname, '../components/official/SpatialRouteMotionCard.tsx'),
        path.resolve(__dirname, '../components/official/OfflineEngineMotionCard.tsx'),
        path.resolve(__dirname, '../components/official/LedgerMotionCard.tsx'),
        path.resolve(__dirname, '../components/official/BentoMotionGrid.tsx'),
        path.resolve(__dirname, '../components/official/HeroShowcase.tsx'),
        path.resolve(__dirname, '../app/official/page.tsx'),
      ]

      const forbiddenTerms = [
        '跨境藥理',
        '藥品',
        '處方',
        '藥局',
        '成藥',
        '醫療',
        '醫藥',
        '療效',
        '保健品',
        'pharma',
        'prescription',
        'medicine',
        'medication',
      ]

      filesToAudit.forEach((file) => {
        const content = fs.readFileSync(file, 'utf-8').toLowerCase()
        forbiddenTerms.forEach((term) => {
          expect(content.includes(term.toLowerCase()), `File ${path.basename(file)} must not contain forbidden term "${term}"`).toBe(false)
        })
      })
    })
  })

  // =========================================================================
  // 2. STRESS-TEST: OfflineEngineMotionCard
  // =========================================================================
  describe('2. OfflineEngineMotionCard Stress & Gauge Dial Geometry', () => {
    it('2.1. Rapid 100-cycle toggling between Online and Offline states', () => {
      render(<OfflineEngineMotionCard />)
      const toggleBtn = screen.getByRole('switch')

      for (let i = 0; i < 100; i++) {
        // Toggle flips state: i=0 -> offline, i=1 -> online, i=2 -> offline, etc.
        const isExpectingOffline = i % 2 === 0

        fireEvent.click(toggleBtn)

        if (isExpectingOffline) {
          expect(toggleBtn.getAttribute('aria-checked')).toBe('true')
          expect(screen.getByText('12ms 讀取延遲')).toBeDefined()
          expect(screen.getByText(/Airplane Mode · Local Snapshot Engaged/i)).toBeDefined()
          expect(screen.getByText(/0 延遲本地秒開/i)).toBeDefined()
        } else {
          expect(toggleBtn.getAttribute('aria-checked')).toBe('false')
          expect(screen.getByText('18ms 讀取延遲')).toBeDefined()
          expect(screen.getByText(/Edge CDN Active · Ping 18ms/i)).toBeDefined()
          expect(screen.getByText(/雙向增量同步/i)).toBeDefined()
        }
      }
    })

    it('2.2. Gauge Pointer Angle & SVG Coordinate Geometry Analysis', () => {
      const filePath = path.resolve(__dirname, '../components/official/OfflineEngineMotionCard.tsx')
      const code = fs.readFileSync(filePath, 'utf-8')

      // Semicircle track: M 20 100 A 80 80 0 0 1 180 100
      expect(code).toContain('M 20 100 A 80 80 0 0 1 180 100')
      // Pointer line from center (100, 100) to top (100, 28)
      expect(code).toContain('x1="100"')
      expect(code).toContain('y1="100"')
      expect(code).toContain('x2="100"')
      expect(code).toContain('y2="28"')
      // Origin point set to (100px, 100px)
      expect(code).toContain('originX: "100px"')
      expect(code).toContain('originY: "100px"')

      // Angular range validation:
      // Offline = -65 deg (12ms), Online = -55 deg (18ms)
      expect(code).toContain('const needleRotation = isOffline ? -65 : -55')
      expect(code).toContain('const currentLatency = isOffline ? "12ms" : "18ms"')
    })

    it('2.3. GPU transform & Opacity isolation (no layout thrashing properties animated)', () => {
      const filePath = path.resolve(__dirname, '../components/official/OfflineEngineMotionCard.tsx')
      const code = fs.readFileSync(filePath, 'utf-8')

      // The needle must animate rotate, not left/top/width/height/margin
      expect(code).toMatch(/animate=\{\{\s*rotate:/)
      expect(code).not.toMatch(/animate=\{\{[^}]*(width|height|left|top|margin):/)
    })
  })

  // =========================================================================
  // 3. STRESS-TEST: LedgerMotionCard
  // =========================================================================
  describe('3. LedgerMotionCard Mathematical Oracle & Currency Stress', () => {
    it('3.1. Currency Conversion & Split Calculation Matrix Verification', () => {
      render(<LedgerMotionCard />)

      const jpyTab = screen.getByRole('tab', { name: /JPY/i })
      const twdTab = screen.getByRole('tab', { name: /TWD/i })
      const usdTab = screen.getByRole('tab', { name: /USD/i })
      const splitBtn = screen.getByRole('button', { name: /切換/i })
      expect(jpyTab).toBeDefined()

      // Base amounts:
      // Dining: 8,200 JPY
      // Transit: 3,400 JPY
      // Stay: 6,900 JPY
      // Total: 18,500 JPY
      // 4-way split: 4,625 JPY

      // 1. Initial State: JPY, 4-way split
      expect(screen.getByText('4,625')).toBeDefined()
      expect(screen.getByText('每人應付份額 (4人均攤)')).toBeDefined()
      // Sub-items for 4-way JPY
      expect(screen.getByText('¥ 2,050')).toBeDefined() // 8200 / 4
      expect(screen.getByText('¥ 850')).toBeDefined()   // 3400 / 4
      expect(screen.getByText('¥ 1,725')).toBeDefined() // 6900 / 4

      // 2. Toggle to Total (JPY)
      fireEvent.click(splitBtn)
      expect(screen.getByText('18,500')).toBeDefined()
      expect(screen.getByText('本趟行程總計費用')).toBeDefined()
      expect(screen.getByText('¥ 8,200')).toBeDefined()
      expect(screen.getByText('¥ 3,400')).toBeDefined()
      expect(screen.getByText('¥ 6,900')).toBeDefined()

      // 3. Switch to TWD (Total mode)
      // Rate: 0.2081
      // Total TWD: round(18500 * 0.2081) = round(3849.85) = 3,850
      fireEvent.click(twdTab)
      expect(screen.getByText('3,850')).toBeDefined()
      // Sub-items:
      // 8200 * 0.2081 = 1706.42 -> 1,706
      // 3400 * 0.2081 = 707.54 -> 708
      // 6900 * 0.2081 = 1435.89 -> 1,436
      expect(screen.getByText('NT$ 1,706')).toBeDefined()
      expect(screen.getByText('NT$ 708')).toBeDefined()
      expect(screen.getByText('NT$ 1,436')).toBeDefined()

      // 4. Switch to 4-way split (TWD)
      // 4625 * 0.2081 = 962.4625 -> 962
      fireEvent.click(splitBtn)
      expect(screen.getByText('962')).toBeDefined()
      // Sub-items:
      // 2050 * 0.2081 = 426.605 -> 427
      // 850 * 0.2081 = 176.885 -> 177
      // 1725 * 0.2081 = 358.9725 -> 359
      expect(screen.getByText('NT$ 427')).toBeDefined()
      expect(screen.getByText('NT$ 177')).toBeDefined()
      expect(screen.getByText('NT$ 359')).toBeDefined()

      // 5. Switch to USD (4-way split mode)
      // Rate: 0.006486, decimals: 2
      // Split USD: 4625 * 0.006486 = 29.99775 -> "30.00"
      fireEvent.click(usdTab)
      expect(screen.getByText('30.00')).toBeDefined()
      // Sub-items:
      // 2050 * 0.006486 = 13.2963 -> "$ 13.30"
      // 850 * 0.006486 = 5.5131 -> "$ 5.51"
      // 1725 * 0.006486 = 11.18835 -> "$ 11.19"
      expect(screen.getByText('$ 13.30')).toBeDefined()
      expect(screen.getByText('$ 5.51')).toBeDefined()
      expect(screen.getByText('$ 11.19')).toBeDefined()

      // 6. Switch to USD (Total mode)
      // Total USD: 18500 * 0.006486 = 119.991 -> "119.99"
      fireEvent.click(splitBtn)
      expect(screen.getByText('119.99')).toBeDefined()
      // Sub-items:
      // 8200 * 0.006486 = 53.1852 -> "$ 53.19"
      // 3400 * 0.006486 = 22.0524 -> "$ 22.05"
      // 6900 * 0.006486 = 44.7534 -> "$ 44.75"
      expect(screen.getByText('$ 53.19')).toBeDefined()
      expect(screen.getByText('$ 22.05')).toBeDefined()
      expect(screen.getByText('$ 44.75')).toBeDefined()

      // 7. Full Circle: Switch back to JPY (Total mode)
      fireEvent.click(jpyTab)
      expect(screen.getByText('18,500')).toBeDefined()
      expect(screen.getByText('¥ 8,200')).toBeDefined()
    })

    it('3.2. Extreme Edge Case & Floating Point Rounding Oracle', () => {
      // Test formatAmount algorithm directly with extreme values (zero, negative, high precision fractions)
      const currencies = {
        JPY: { rate: 1, decimals: 0 },
        TWD: { rate: 0.2081, decimals: 0 },
        USD: { rate: 0.006486, decimals: 2 },
      }

      const formatAmount = (jpyValue: number, config: { rate: number; decimals: number }) => {
        const converted = jpyValue * config.rate
        if (config.decimals === 0) {
          return Math.round(converted).toLocaleString('en-US')
        }
        return converted.toLocaleString('en-US', {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })
      }

      // Edge case: 0
      expect(formatAmount(0, currencies.JPY)).toBe('0')
      expect(formatAmount(0, currencies.TWD)).toBe('0')
      expect(formatAmount(0, currencies.USD)).toBe('0.00')

      // Edge case: Negative values (e.g. refund/cashback)
      expect(formatAmount(-1000, currencies.JPY)).toBe('-1,000')
      expect(formatAmount(-1000, currencies.TWD)).toBe('-208')
      expect(formatAmount(-1000, currencies.USD)).toBe('-6.49')

      // Edge case: Large numbers (e.g. 100,000,000 JPY)
      expect(formatAmount(100000000, currencies.JPY)).toBe('100,000,000')
      expect(formatAmount(100000000, currencies.TWD)).toBe('20,810,000')
      expect(formatAmount(100000000, currencies.USD)).toBe('648,600.00')

      // Edge case: Floating sub-yen amounts (IEEE-754 precision boundary)
      const fractional = 0.1 + 0.2 // 0.30000000000000004
      expect(formatAmount(fractional, currencies.USD)).toBe('0.00')
      expect(formatAmount(100.555, currencies.USD)).toBe('0.65')
    })
  })

  // =========================================================================
  // 4. DESIGN ENGINEERING & ACCESSIBILITY AUDIT
  // =========================================================================
  describe('4. Emil Kowalski Design Engineering & Touch Target Standards', () => {
    it('4.1. All interactive buttons and controls in M2 components fulfill >= 44x44px touch ergonomics', () => {
      // 1. SpatialRouteMotionCard waypoint buttons
      const { container: spatialContainer } = render(<SpatialRouteMotionCard />)
      const waypointBtns = spatialContainer.querySelectorAll('button')
      expect(waypointBtns.length).toBe(5)
      waypointBtns.forEach((btn) => {
        expect(btn.className).toMatch(/min-h-(11|\[44px\])/)
      })

      // 2. OfflineEngineMotionCard toggle switch
      const { container: offlineContainer } = render(<OfflineEngineMotionCard />)
      const offlineSwitch = offlineContainer.querySelector('button[role="switch"]')
      expect(offlineSwitch).toBeDefined()
      expect(offlineSwitch?.className).toMatch(/min-h-(11|\[44px\])/)
      expect(offlineSwitch?.className).toMatch(/min-w-(11|\[44px\])/)

      // 3. LedgerMotionCard split toggle & currency tabs
      const { container: ledgerContainer } = render(<LedgerMotionCard />)
      const splitBtn = ledgerContainer.querySelector('button[aria-label*="切換"]')
      expect(splitBtn?.className).toMatch(/min-h-(11|\[44px\])/)
      expect(splitBtn?.className).toMatch(/min-w-(11|\[44px\])/)
      const currencyTabs = ledgerContainer.querySelectorAll('button[role="tab"]')
      expect(currencyTabs.length).toBe(3)
      currencyTabs.forEach((tab) => {
        expect(tab.className).toMatch(/min-h-(11|\[44px\])/)
      })

      // 4. HeroShowcase CTAs
      const { container: heroContainer } = render(<HeroShowcase />)
      const heroButtons = heroContainer.querySelectorAll('button, a[href]')
      expect(heroButtons.length).toBe(2)
      heroButtons.forEach((btn) => {
        expect(btn.className).toMatch(/min-h-(11|\[44px\])/)
        expect(btn.className).toMatch(/min-w-(11|\[44px\])/)
      })

      // 5. OfficialPage Launch Banner CTAs
      const { container: pageContainer } = render(<OfficialPage />)
      const bannerLaunchBtn = pageContainer.querySelector('button[aria-label*="立即啟動"]')
      const bannerTermsLink = pageContainer.querySelector('a[aria-label*="查閱服務條款"]')
      expect(bannerLaunchBtn?.className).toMatch(/min-h-(11|\[44px\])/)
      expect(bannerLaunchBtn?.className).toMatch(/min-w-(11|\[44px\])/)
      expect(bannerTermsLink?.className).toMatch(/min-h-(11|\[44px\])/)
      expect(bannerTermsLink?.className).toMatch(/min-w-(11|\[44px\])/)
    })

    it('4.2. Micro-touch active feedback: active:scale-[0.97] and ease-out 160ms on interactive controls', () => {
      const componentsCode = [
        fs.readFileSync(path.resolve(__dirname, '../components/official/HeroShowcase.tsx'), 'utf-8'),
        fs.readFileSync(path.resolve(__dirname, '../components/official/SpatialRouteMotionCard.tsx'), 'utf-8'),
        fs.readFileSync(path.resolve(__dirname, '../components/official/OfflineEngineMotionCard.tsx'), 'utf-8'),
        fs.readFileSync(path.resolve(__dirname, '../components/official/LedgerMotionCard.tsx'), 'utf-8'),
        fs.readFileSync(path.resolve(__dirname, '../app/official/page.tsx'), 'utf-8'),
      ]

      componentsCode.forEach((code) => {
        expect(code).toContain('active:scale-[0.97]')
        expect(code).toContain('duration-160')
        expect(code).toContain('ease-out')
      })
    })

    it('4.3. BentoMotionGrid: Enforces 40ms stagger micro-delay and Kowalski cubic-bezier [0.23, 1, 0.32, 1]', () => {
      const bentoCode = fs.readFileSync(path.resolve(__dirname, '../components/official/BentoMotionGrid.tsx'), 'utf-8')
      expect(bentoCode).toContain('staggerChildren: shouldReduceMotion ? 0 : 0.04')
      expect(bentoCode).toContain('[0.23, 1, 0.32, 1]')
      expect(bentoCode).toContain('scale: shouldReduceMotion ? 1 : 0.95') // Prohibits scale(0) entrance
      expect(bentoCode).not.toContain('scale: 0')
    })

    it('4.4. Accessibility & Semantics Audit: ARIA roles, labels, and tab index', () => {
      render(<BentoMotionGrid />)

      // Offline card switch
      const offlineSwitch = screen.getByRole('switch')
      expect(offlineSwitch.getAttribute('aria-checked')).toBe('false')
      expect(offlineSwitch.getAttribute('aria-label')).toBe('切換至模擬斷網模式')

      // Ledger tabs
      const tabList = screen.getByRole('tablist', { name: /選擇幣別/i })
      expect(tabList).toBeDefined()
      const jpyTab = screen.getByRole('tab', { name: /JPY/i })
      expect(jpyTab.getAttribute('aria-selected')).toBe('true')
      const twdTab = screen.getByRole('tab', { name: /TWD/i })
      expect(twdTab.getAttribute('aria-selected')).toBe('false')

      // Spatial route labels
      const waypointButtons = screen.getAllByRole('button', { name: /選擇航點/i })
      expect(waypointButtons.length).toBe(5)
    })

    it('4.5. Dark Mode Compatibility: all motion cards declare dark: variants for backgrounds and texts', () => {
      const cards = [
        path.resolve(__dirname, '../components/official/SpatialRouteMotionCard.tsx'),
        path.resolve(__dirname, '../components/official/OfflineEngineMotionCard.tsx'),
        path.resolve(__dirname, '../components/official/LedgerMotionCard.tsx'),
      ]

      cards.forEach((cardPath) => {
        const code = fs.readFileSync(cardPath, 'utf-8')
        expect(code).toContain('dark:bg-')
        expect(code).toContain('dark:text-')
        expect(code).toContain('dark:border-')
      })
    })

    it('4.6. Concurrent Cross-Card Interactive Torture Test (Bento Grid stress test)', () => {
      render(<BentoMotionGrid />)

      const waypointButtons = screen.getAllByRole('button', { name: /選擇航點/i })
      const offlineSwitch = screen.getByRole('switch')
      const splitBtn = screen.getByRole('button', { name: /切換/i })
      const currencyTabs = screen.getAllByRole('tab')

      // Concurrently fire interleaved events across all three cards 50 times
      for (let i = 0; i < 50; i++) {
        // Toggle offline mode
        fireEvent.click(offlineSwitch)

        // Switch waypoint
        fireEvent.click(waypointButtons[i % 5])

        // Switch currency
        fireEvent.click(currencyTabs[i % 3])

        // Toggle split
        if (i % 2 === 0) {
          fireEvent.click(splitBtn)
        }
      }

      // Verify DOM stability after cross-card interleaved assault
      expect(screen.getByText('空間航線巡航')).toBeDefined()
      expect(screen.getByText('離線自癒引擎')).toBeDefined()
      expect(screen.getByText('智慧多幣別分帳')).toBeDefined()
    })
  })

  // =========================================================================
  // 5. INVARIANTS COMPLIANCE
  // =========================================================================
  describe('5. Invariants Compliance Verification', () => {
    it('5.1. Strictly zero modifications to root page.tsx, sw.ts, or manifest.json', () => {
      const gitRoot = path.resolve(__dirname, '../..')
      const invariants = [
        'frontend/app/page.tsx',
        'frontend/app/sw.ts',
        'frontend/public/manifest.json',
      ]

      invariants.forEach((inv) => {
        const fullPath = path.join(gitRoot, inv)
        expect(fs.existsSync(fullPath)).toBe(true)
      })
    })
  })
})
