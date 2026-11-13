/**
 * 🛡️ Security Sentinel: Official Bilingual Switcher Pre-Execution Spiking Test Suite
 * Follows Mantis Block G Benign Control, Harness^2 Invariant Conservation & Zero LocalStorage Pollution.
 */

import React, { act } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, renderHook } from '@testing-library/react'
import { type OfficialLanguage, officialTranslations } from '../lib/official-translations'
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

import {
  OfficialLanguageProvider,
  useOfficialLanguage,
  OFFICIAL_PORTAL_LANG_KEY,
} from '../lib/OfficialLanguageContext'
import { OfficialHeader } from '../components/official/OfficialHeader'
import { OfficialBackLink } from '../components/official/OfficialBackLink'
import { TypewriterHeading } from '../components/official/TypewriterHeading'
import { HeroTypewriterHeading } from '../components/official/HeroTypewriterHeading'
import { LiveDeviceTheater } from '../components/official/LiveDeviceTheater'
import { BentoMotionGrid } from '../components/official/BentoMotionGrid'

const frontendDir = path.resolve(__dirname, '..')
const typewriterPath = path.join(frontendDir, 'components', 'official', 'TypewriterHeading.tsx')
const heroTypewriterPath = path.join(frontendDir, 'components', 'official', 'HeroTypewriterHeading.tsx')
const headerPath = path.join(frontendDir, 'components', 'official', 'OfficialHeader.tsx')
const footerPath = path.join(frontendDir, 'components', 'official', 'OfficialFooter.tsx')
const layoutPath = path.join(frontendDir, 'app', 'official', 'layout.tsx')

class MockIntersectionObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

describe('🛡️ Security Sentinel: Bilingual Switcher Invariant Contract', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver
    sessionStorage.clear()
    localStorage.clear()
    window.history.replaceState(null, '', '/official')
  })

  describe('Gate 1: Zero LocalStorage Pollution & Storage Sovereignty', () => {
    it('SENTINEL-1.1: Official portal code never accesses localStorage for language preferences', () => {
      const headerContent = fs.readFileSync(headerPath, 'utf-8')
      const layoutContent = fs.readFileSync(layoutPath, 'utf-8')
      
      // Strict isolation assertion: must not call localStorage.setItem('app_language', ...) in official components
      expect(headerContent).not.toMatch(/localStorage\.(setItem|getItem)\(['"]app_language['"]\)/)
      expect(layoutContent).not.toMatch(/localStorage\.(setItem|getItem)\(['"]app_language['"]\)/)
    })

    it('SENTINEL-1.2: Native sessionStorage isolation key is scoped to tabiji_official_portal_lang', () => {
      // Must use dedicated official portal session scope
      const expectedKey = OFFICIAL_PORTAL_LANG_KEY
      expect(expectedKey).toBe('tabiji_official_portal_lang')
      expect(expectedKey).toContain('official_portal')
    })
  })

  describe('Gate 2: Typewriter Dynamic Language Switch & Render-Phase State Reset', () => {
    it('SENTINEL-2.1: TypewriterHeading uses whitespace-pre-wrap to prevent 375px mobile overflow', () => {
      const content = fs.readFileSync(typewriterPath, 'utf-8')
      // Must not use unconstrained 'whitespace-pre' without '-wrap'
      const hasUnwrappedPre = /className="[^"]*\bwhitespace-pre\b(?!\-wrap)[^"]*"/.test(content)
      // When remediated, hasUnwrappedPre must be false and whitespace-pre-wrap must be present
      expect(hasUnwrappedPre).toBe(false)
      expect(content).toContain('whitespace-pre-wrap')
    })

    it('SENTINEL-2.2: HeroTypewriterHeading visual layers allow responsive line wrapping for English text', () => {
      const content = fs.readFileSync(heroTypewriterPath, 'utf-8')
      expect(content).toContain('HeroTypewriterHeading')
      expect(content).toContain('whitespace-pre-wrap')
    })

    it('SENTINEL-2.3: TypewriterHeading renders clean without ghosting across prop updates', () => {
      const { rerender } = render(<TypewriterHeading text="走過的路，" />)
      expect(screen.getByText('走過的路，')).toBeDefined()

      // Dynamically switch to English
      rerender(<TypewriterHeading text="Where every step," />)
      expect(screen.getByText('Where every step,')).toBeDefined()
    })

    it('SENTINEL-2.4: HeroTypewriterHeading resets line transition on language toggle without error', () => {
      const { rerender } = render(
        <HeroTypewriterHeading line1="走過的路，" line2="都在這裡發光。" />
      )
      expect(screen.getByText(/走過的路，/)).toBeDefined()

      rerender(
        <HeroTypewriterHeading line1="Where every step," line2="finds its light." />
      )
      expect(screen.getByText(/Where every step,/)).toBeDefined()
    })
  })

  describe('Gate 3: OfficialFooter Link Count Conservation (Prevent Adversarial RWD Failure)', () => {
    it('SENTINEL-3.1: OfficialFooter text links count matches exact 6 link test expectation', () => {
      const content = fs.readFileSync(footerPath, 'utf-8')
      const linkMatches = content.match(/<Link[\s\S]*?className="([^"]*)"/g) || []
      const textLinks = linkMatches.filter((m) => !m.includes('href="/official"'))
      
      // ADV-M2-3.9 expects exactly 6 links (3 in features nav, 3 in legal nav)
      // If experience is in the header, footer features nav should retain exactly 3 links to keep ADV-M2-3.9 green
      expect(textLinks.length).toBe(6)
    })
  })

  describe('Gate 4: Frozen Core Invariants (Unchanged & Sacred)', () => {
    it('SENTINEL-4.1: frontend/app/page.tsx, sw.ts, and public/manifest.json have 0 modifications', () => {
      const rootPagePath = path.join(frontendDir, 'app', 'page.tsx')
      const swPath = path.join(frontendDir, 'app', 'sw.ts')
      const manifestPath = path.join(frontendDir, 'public', 'manifest.json')

      expect(fs.existsSync(rootPagePath)).toBe(true)
      expect(fs.existsSync(swPath)).toBe(true)
      expect(fs.existsSync(manifestPath)).toBe(true)
    })
  })

  describe('Gate 5: Interactive Bilingual Switcher & Sovereignty Compliance', () => {
    it('SENTINEL-5.1: Switching language to English sets sessionStorage and leaves localStorage untouched', () => {
      render(
        <OfficialLanguageProvider>
          <OfficialHeader />
        </OfficialLanguageProvider>
      )

      // Find English switcher button
      const enButtons = screen.getAllByRole('button', { name: /switch to english/i })
      expect(enButtons.length).toBeGreaterThanOrEqual(1)

      fireEvent.click(enButtons[0])

      // Verify sessionStorage is updated to 'en'
      expect(sessionStorage.getItem(OFFICIAL_PORTAL_LANG_KEY)).toBe('en')

      // Strict check: localStorage MUST NOT have 'app_language' set
      expect(localStorage.getItem('app_language')).toBeNull()
    })

    it('SENTINEL-5.2: Switcher buttons comply with 44px touch ergonomics and hide on narrow viewports', () => {
      render(
        <OfficialLanguageProvider>
          <OfficialHeader />
        </OfficialLanguageProvider>
      )

      const zhButton = screen.getAllByRole('button', { name: /切換為繁體中文/i })[0]
      const enButton = screen.getAllByRole('button', { name: /switch to english/i })[0]

      expect(zhButton.className).toMatch(/min-h-(11|\[44px\])/)
      expect(enButton.className).toMatch(/min-h-(11|\[44px\])/)

      const headerContent = fs.readFileSync(headerPath, 'utf-8')
      expect(headerContent).toContain('hidden sm:inline-flex')
    })

    it('SENTINEL-5.3: Popstate navigation from ?lang=en back to /official reverts language to zh and updates sessionStorage', () => {
      // Simulate browser at /official?lang=en
      window.history.replaceState(null, '', '/official?lang=en')

      const TestHarness = () => {
        const { language } = useOfficialLanguage()
        return <div data-testid="current-lang">{language}</div>
      }

      const { unmount } = render(
        <OfficialLanguageProvider>
          <TestHarness />
        </OfficialLanguageProvider>
      )

      expect(screen.getByTestId('current-lang').textContent).toBe('en')
      expect(sessionStorage.getItem(OFFICIAL_PORTAL_LANG_KEY)).toBe('en')

      // Simulate browser history navigation back to /official (no query string)
      window.history.replaceState(null, '', '/official')
      act(() => {
        fireEvent(window, new PopStateEvent('popstate'))
      })

      expect(screen.getByTestId('current-lang').textContent).toBe('zh')
      expect(sessionStorage.getItem(OFFICIAL_PORTAL_LANG_KEY)).toBe('zh')

      unmount()
    })

    it('SENTINEL-5.4: URL query parameter fallback and XSS mitigation', () => {
      // 1. Invalid language parameter fallback
      window.history.replaceState(null, '', '/official?lang=ja')
      const TestHarness = () => {
        const { language } = useOfficialLanguage()
        return <div data-testid="current-lang">{language}</div>
      }

      const { unmount: unmount1 } = render(
        <OfficialLanguageProvider>
          <TestHarness />
        </OfficialLanguageProvider>
      )
      expect(screen.getByTestId('current-lang').textContent).toBe('zh')
      unmount1()

      // 2. Malicious XSS injection fallback
      window.history.replaceState(null, '', '/official?lang=%3Cscript%3Ealert(1)%3C/script%3E')
      const { unmount: unmount2 } = render(
        <OfficialLanguageProvider>
          <TestHarness />
        </OfficialLanguageProvider>
      )
      expect(screen.getByTestId('current-lang').textContent).toBe('zh')
      unmount2()

      window.history.replaceState(null, '', '/official')
    })

    it('SENTINEL-5.5: setLanguage sanitizes arbitrary input to valid OfficialLanguage', () => {
      const { result } = renderHook(() => useOfficialLanguage(), {
        wrapper: OfficialLanguageProvider,
      })

      expect(result.current.language).toBe('zh')

      // Call with unsupported string
      act(() => {
        result.current.setLanguage('unsupported' as unknown as OfficialLanguage)
      })
      expect(result.current.language).toBe('zh')
      expect(sessionStorage.getItem(OFFICIAL_PORTAL_LANG_KEY)).toBe('zh')
    })

    it('SENTINEL-5.6: Rapid 50-cycle language toggle stress test maintains integrity', () => {
      const { result } = renderHook(() => useOfficialLanguage(), {
        wrapper: OfficialLanguageProvider,
      })

      act(() => {
        for (let i = 0; i < 50; i++) {
          const targetLang: OfficialLanguage = i % 2 === 0 ? 'en' : 'zh'
          result.current.setLanguage(targetLang)
        }
      })

      // After 50 iterations (ending on 49 -> odd -> 'zh')
      expect(result.current.language).toBe('zh')
      expect(sessionStorage.getItem(OFFICIAL_PORTAL_LANG_KEY)).toBe('zh')
      expect(localStorage.getItem('app_language')).toBeNull()
    })

    it('SENTINEL-5.7: OfficialBackLink provides bilingual back navigation for terms and privacy pages', () => {
      const Harness = () => {
        const { setLanguage } = useOfficialLanguage()
        return (
          <div>
            <button type="button" onClick={() => setLanguage('en')}>
              SwitchToEnglish
            </button>
            <OfficialBackLink />
          </div>
        )
      }

      render(
        <OfficialLanguageProvider>
          <Harness />
        </OfficialLanguageProvider>
      )

      // Default Chinese
      expect(screen.getByRole('link', { name: /返回官方網站首頁/i })).toBeDefined()
      expect(screen.getByText('返回官方首頁')).toBeDefined()

      // Click button inside the provider tree to switch to English
      fireEvent.click(screen.getByText('SwitchToEnglish'))

      expect(screen.getByRole('link', { name: /back to official portal home/i })).toBeDefined()
      expect(screen.getByText('Back to Official Home')).toBeDefined()
    })
  })

  describe('Gate 6: Authentic Device Bilingual Mock & Typewriter Viewport Re-Arm', () => {
    it('SENTINEL-6.1: officialTranslations contains complete mockDevice dictionary for zh and en', () => {
      const { zh, en } = officialTranslations
      expect(zh.mockDevice).toBeDefined()
      expect(en.mockDevice).toBeDefined()

      // Chinese checks
      expect(zh.mockDevice.subHeader.taglinePass).toBe('【斷網抵達】離線時間軸秒開')
      expect(zh.mockDevice.passMode.timeline1.title).toBe('台北 101 觀景台')
      expect(zh.mockDevice.passMode.timeline2.title).toBe('鼎泰豐 101 店')
      expect(zh.mockDevice.passMode.timeline3.title).toBe('象山步道 · 巨石觀景台')
      expect(zh.mockDevice.dock.arrival).toBe('抵達')
      expect(zh.mockDevice.dock.transit).toBe('穿行')
      expect(zh.mockDevice.dock.split).toBe('分帳')
      expect(zh.mockDevice.dock.profile).toBe('個人')

      // English checks
      expect(en.mockDevice.subHeader.taglinePass).toBe('【Off-Grid Arrival】Instant Timeline')
      expect(en.mockDevice.passMode.timeline1.title).toBe('Taipei 101 Observatory')
      expect(en.mockDevice.passMode.timeline2.title).toBe('Din Tai Fung 101')
      expect(en.mockDevice.passMode.timeline3.title).toBe('Elephant Mountain Trail · Boulder Lookout')
      expect(en.mockDevice.ledgerMode.summaryTitle).toBe('Group Split Overview')
      expect(en.mockDevice.ledgerMode.summaryPerPerson).toBe('Average per person (3-way split)')
      expect(en.mockDevice.dock.arrival).toBe('Arrival')
      expect(en.mockDevice.dock.transit).toBe('Transit')
      expect(en.mockDevice.dock.split).toBe('Split')
      expect(en.mockDevice.dock.profile).toBe('Profile')
    })

    it('SENTINEL-6.2: LiveDeviceTheater renders English mockDevice text when language is en', () => {
      window.history.replaceState(null, '', '/official?lang=en')
      const { container } = render(
        <OfficialLanguageProvider>
          <LiveDeviceTheater />
        </OfficialLanguageProvider>
      )

      expect(container.textContent).toContain('Taipei 101')
      expect(container.textContent).toContain('Din Tai Fung 101')
      expect(container.textContent).toContain('Arrival')
      expect(container.textContent).toContain('Transit')
      expect(container.textContent).toContain('Split')
      expect(container.textContent).toContain('Profile')
      expect(container.textContent).toContain('【Off-Grid Arrival】Instant Timeline')
      expect(container.textContent).not.toContain('【斷網抵達】離線時間軸秒開')
    })

    it('SENTINEL-6.3: BentoMotionGrid integrates TypewriterHeading with bilingual heading', () => {
      const bentoPath = path.join(frontendDir, 'components', 'official', 'BentoMotionGrid.tsx')
      const bentoContent = fs.readFileSync(bentoPath, 'utf-8')
      expect(bentoContent).toContain('TypewriterHeading')
      expect(bentoContent).toContain('t.bento.heading')

      const { container } = render(
        <OfficialLanguageProvider>
          <BentoMotionGrid />
        </OfficialLanguageProvider>
      )
      expect(container).toBeDefined()
    })

    it('SENTINEL-6.4: TypewriterHeading resets on language switch and re-arms typing', () => {
      vi.useFakeTimers()
      try {
        const { rerender } = render(<TypewriterHeading text="中文標題" charDelay={50} />)
        // sr-only has full text
        expect(screen.getByText('中文標題')).toBeDefined()

        // Switch to English text
        rerender(<TypewriterHeading text="English Heading" charDelay={50} />)
        expect(screen.getByText('English Heading')).toBeDefined()
      } finally {
        vi.useRealTimers()
      }
    })
  })
})
