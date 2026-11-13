/**
 * Challenger 2 Adversarial Frontend & Handoff Verification Test Suite
 * Stress-tests OfficialHeader launch app link, LanguageContext SSR/PPR Suspense boundaries,
 * and localStorage / cookie isolation between official portal and main app.
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { renderToString } from 'react-dom/server'
import { sanitizeLaunchRedirectUrl } from '../lib/security'
import { OfficialHeader } from '../components/official/OfficialHeader'
import { OfficialLanguageProvider } from '../lib/OfficialLanguageContext'
import { LanguageProvider, useLanguage } from '../lib/LanguageContext'

// Navigation mocks
let mockPathname = '/official'
let mockSearchParams = new URLSearchParams('')
const mockPush = vi.fn()
const mockReplace = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
  usePathname: () => mockPathname,
  useSearchParams: () => mockSearchParams,
}))

// IntersectionObserver mock for OfficialHeader scrollspy
class MockIntersectionObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

describe('Challenger 2: Adversarial Frontend Verification', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockPathname = '/official'
    mockSearchParams = new URLSearchParams('')
    window.IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver
    sessionStorage.clear()
    localStorage.clear()
    document.cookie = 'app_language=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
    window.history.replaceState(null, '', '/official')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // =========================================================================
  // 1. Stress-test OfficialHeader.tsx Launch App link & Open-Redirect Immunity
  // =========================================================================
  describe('1. OfficialHeader Launch App Link & Open-Redirect Immunity', () => {
    const maliciousLangPayloads = [
      '//evil.com',
      '///evil.com',
      'https://evil.com',
      'http://attacker.org',
      'javascript:alert(document.cookie)',
      'javascript:void(0)',
      'data:text/html,<script>alert(1)</script>',
      'vbscript:alert(1)',
      '/\\evil.com',
      '\\evil.com',
      '..%2f..%2fevil',
      '%00',
      'fr',
      'de',
      'es',
      'ja',
    ]

    for (const payload of maliciousLangPayloads) {
      it(`blocks malformed/protocol lang parameter in portal: "${payload}" -> falls back safely to "/?lang=zh"`, () => {
        window.history.replaceState(null, '', `/official?lang=${encodeURIComponent(payload)}`)
        mockPathname = '/official'
        mockSearchParams = new URLSearchParams(`lang=${encodeURIComponent(payload)}`)

        render(
          <OfficialLanguageProvider>
            <OfficialHeader />
          </OfficialLanguageProvider>
        )

        // Find the Launch App CTA button in header
        const launchBtn = screen.getByRole('button', { name: /啟動應用|Launch App/i })
        fireEvent.click(launchBtn)

        // Must NOT redirect to external protocol or malicious target
        expect(mockPush).toHaveBeenCalledWith('/?lang=zh')
        expect(mockPush).not.toHaveBeenCalledWith(expect.stringContaining('evil'))
        expect(mockPush).not.toHaveBeenCalledWith(expect.stringContaining('javascript:'))
      })
    }

    it('blocks open-redirect attempts with returnTo=//evil.com on /official: OfficialHeader ignores returnTo and navigates to /?lang=zh', () => {
      window.history.replaceState(null, '', '/official?returnTo=//evil.com')
      mockPathname = '/official'
      mockSearchParams = new URLSearchParams('returnTo=//evil.com')

      render(
        <OfficialLanguageProvider>
          <OfficialHeader />
        </OfficialLanguageProvider>
      )

      const launchBtn = screen.getByRole('button', { name: /啟動應用|Launch App/i })
      fireEvent.click(launchBtn)

      expect(mockPush).toHaveBeenCalledWith('/?lang=zh')
      expect(mockPush).not.toHaveBeenCalledWith(expect.stringContaining('evil'))
    })

    it('blocks open-redirect attempts with returnTo=https://evil.com and lang=en: navigates strictly to /?lang=en without returnTo', () => {
      window.history.replaceState(null, '', '/official?lang=en&returnTo=https://evil.com')
      mockPathname = '/official'
      mockSearchParams = new URLSearchParams('lang=en&returnTo=https://evil.com')

      render(
        <OfficialLanguageProvider>
          <OfficialHeader />
        </OfficialLanguageProvider>
      )

      const launchBtn = screen.getByRole('button', { name: /Launch App/i })
      fireEvent.click(launchBtn)

      expect(mockPush).toHaveBeenCalledWith('/?lang=en')
      expect(mockPush).not.toHaveBeenCalledWith(expect.stringContaining('evil'))
    })

    it('blocks open-redirect attempts with returnTo=javascript:alert(1) on /official: navigates strictly to /?lang=zh', () => {
      window.history.replaceState(null, '', '/official?returnTo=javascript:alert(1)')
      mockPathname = '/official'
      mockSearchParams = new URLSearchParams('returnTo=javascript:alert(1)')

      render(
        <OfficialLanguageProvider>
          <OfficialHeader />
        </OfficialLanguageProvider>
      )

      const launchBtn = screen.getByRole('button', { name: /啟動應用|Launch App/i })
      fireEvent.click(launchBtn)

      expect(mockPush).toHaveBeenCalledWith('/?lang=zh')
      expect(mockPush).not.toHaveBeenCalledWith(expect.stringContaining('javascript:'))
    })

    it('handles legitimate EN language in portal: navigates strictly to "/?lang=en"', () => {
      window.history.replaceState(null, '', '/official?lang=en')
      mockPathname = '/official'
      mockSearchParams = new URLSearchParams('lang=en')

      render(
        <OfficialLanguageProvider>
          <OfficialHeader />
        </OfficialLanguageProvider>
      )

      const launchBtn = screen.getByRole('button', { name: /Launch App/i })
      fireEvent.click(launchBtn)

      expect(mockPush).toHaveBeenCalledWith('/?lang=en')
    })

    it('handles mobile menu Launch App button click safely', () => {
      window.history.replaceState(null, '', '/official?lang=en')
      mockPathname = '/official'
      mockSearchParams = new URLSearchParams('lang=en')

      render(
        <OfficialLanguageProvider>
          <OfficialHeader />
        </OfficialLanguageProvider>
      )

      // Open mobile menu via hamburger button
      const menuBtn = screen.getByRole('button', { name: /Open Menu/i })
      fireEvent.click(menuBtn)

      // Both desktop and mobile Launch buttons are now present
      const launchBtns = screen.getAllByRole('button', { name: /Launch App/i })
      expect(launchBtns.length).toBeGreaterThanOrEqual(2)

      // Click the mobile launch button (last one in DOM)
      const mobileLaunchBtn = launchBtns[launchBtns.length - 1]
      fireEvent.click(mobileLaunchBtn)

      expect(mockPush).toHaveBeenCalledWith('/?lang=en')
    })

    describe('Adversarial fuzzing of sanitizeLaunchRedirectUrl', () => {
      const openRedirectVectors = [
        '//attacker.com',
        '///attacker.com',
        '////attacker.com',
        'https://evil.com/phish',
        'http://evil.com',
        'ftp://evil.com',
        'javascript:alert(1)',
        'JavaScript:alert(1)',
        'data:text/html;base64,PHNjcmlwdD4=',
        'vbscript:msgbox("test")',
        'file:///etc/passwd',
        '/\\evil.com',
        '\\evil.com',
        '\\\\evil.com',
        '/evil.com',
        '/attacker',
        '/admin/secret',
        '/login',
        '/?returnTo=https://evil.com',
        '/?returnTo=http://evil.com',
        '/?returnTo=javascript:alert(1)',
        '/?next=https://evil.com',
        '/?url=http://attacker.com',
        '/?param=foo:bar',
        '/?param=foo\\bar',
        '/%2f/evil.com',
        '/\0/evil.com',
        '/\r\n/evil.com',
      ]

      for (const vector of openRedirectVectors) {
        it(`strictly blocks vector: ${JSON.stringify(vector)} -> returns "/"`, () => {
          const result = sanitizeLaunchRedirectUrl(vector)
          expect(result).toBe('/')
        })
      }

      it('preserves valid internal paths and query strings', () => {
        expect(sanitizeLaunchRedirectUrl('/')).toBe('/')
        expect(sanitizeLaunchRedirectUrl('/?lang=en')).toBe('/?lang=en')
        expect(sanitizeLaunchRedirectUrl('/?lang=zh')).toBe('/?lang=zh')
        expect(sanitizeLaunchRedirectUrl('/?action=new-trip')).toBe('/?action=new-trip')
        expect(sanitizeLaunchRedirectUrl('/?action=new-trip&ref=official')).toBe('/?action=new-trip&ref=official')
        expect(sanitizeLaunchRedirectUrl('/explore')).toBe('/explore')
        expect(sanitizeLaunchRedirectUrl('/explore?region=kansai')).toBe('/explore?region=kansai')
        expect(sanitizeLaunchRedirectUrl('/transit')).toBe('/transit')
        expect(sanitizeLaunchRedirectUrl('/transit?from=HND&to=NRT')).toBe('/transit?from=HND&to=NRT')
      })
    })
  })

  // =========================================================================
  // 2. Stress-test LanguageContext SSR / PPR Suspense Boundary Compliance
  // =========================================================================
  describe('2. LanguageContext SSR / PPR Suspense Compliance', () => {
    it('renders cleanly in SSR without throwing unhandled Suspense / useSearchParams bailout', () => {
      // In SSR, window is undefined or mounted is false initially
      const TestConsumer = () => {
        const { lang, isReady } = useLanguage()
        return (
          <div data-testid="ssr-out">
            <span id="lang-val">{lang}</span>
            <span id="ready-val">{String(isReady)}</span>
          </div>
        )
      }

      // renderToString executes synchronously representing SSR
      let ssrHtml = ''
      expect(() => {
        ssrHtml = renderToString(
          <LanguageProvider>
            <TestConsumer />
          </LanguageProvider>
        )
      }).not.toThrow()

      expect(ssrHtml).toContain('id="lang-val">zh<')
      expect(ssrHtml).toContain('id="ready-val">false<')
    })

    it('encloses LanguageUrlHandoffObserver inside <Suspense> when mounted on client', async () => {
      const TestConsumer = () => {
        const { lang, isReady } = useLanguage()
        return (
          <div data-testid="client-out">
            <span id="lang-client">{lang}</span>
            <span id="ready-client">{String(isReady)}</span>
          </div>
        )
      }

      const { container } = render(
        <LanguageProvider>
          <TestConsumer />
        </LanguageProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('client-out')).toBeDefined()
        expect(screen.getByText('true')).toBeDefined()
      })

      // Ensure no dangling error in DOM
      expect(container.innerHTML).not.toContain('bailout')
    })
  })

  // =========================================================================
  // 3. Verify localStorage and Cookie Isolation Between Portal & Main App
  // =========================================================================
  describe('3. localStorage & Cookie State Isolation', () => {
    it('Scenario 1: Viewing /official with ?lang=en NEVER writes to localStorage or document.cookie', async () => {
      mockPathname = '/official'
      mockSearchParams = new URLSearchParams('lang=en')
      window.history.replaceState(null, '', '/official?lang=en')

      const Probe = () => {
        const { lang } = useLanguage()
        return <div data-testid="main-app-lang">{lang}</div>
      }

      render(
        <LanguageProvider>
          <Probe />
        </LanguageProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('main-app-lang')).toBeDefined()
      })

      // Strict Isolation Invariant: /official MUST NEVER write to app_language
      expect(localStorage.getItem('app_language')).toBeNull()
      expect(document.cookie).not.toContain('app_language=en')
    })

    it('Scenario 2: Toggling language inside OfficialLanguageProvider does not pollute localStorage or cookie', () => {
      mockPathname = '/official'
      mockSearchParams = new URLSearchParams('')
      window.history.replaceState(null, '', '/official')

      const Harness = () => {
        return (
          <OfficialLanguageProvider>
            <OfficialHeader />
          </OfficialLanguageProvider>
        )
      }

      render(<Harness />)

      // Switch to EN via toggle button
      const enToggle = screen.getByRole('button', { name: /Switch to English/i })
      fireEvent.click(enToggle)

      // Official portal uses sessionStorage, NOT localStorage or cookie
      expect(sessionStorage.getItem('tabiji_official_portal_lang')).toBe('en')
      expect(localStorage.getItem('app_language')).toBeNull()
      expect(document.cookie).not.toContain('app_language')
    })

    it('Scenario 3: Returning from /official without Launch App preserves prior app_language', async () => {
      // Prior state: user chose 'zh' in main app
      localStorage.setItem('app_language', 'zh')
      document.cookie = 'app_language=zh; path=/'

      // User visits /official?lang=en
      mockPathname = '/official'
      mockSearchParams = new URLSearchParams('lang=en')
      window.history.replaceState(null, '', '/official?lang=en')

      const Probe = () => {
        const { lang } = useLanguage()
        return <div data-testid="preserved-lang">{lang}</div>
      }

      const { rerender } = render(
        <LanguageProvider>
          <Probe />
        </LanguageProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('preserved-lang').textContent).toBe('zh')
      })
      expect(localStorage.getItem('app_language')).toBe('zh')

      // User navigates back to / (without ?lang= param)
      mockPathname = '/'
      mockSearchParams = new URLSearchParams('')
      window.history.replaceState(null, '', '/')

      rerender(
        <LanguageProvider>
          <Probe />
        </LanguageProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('preserved-lang').textContent).toBe('zh')
      })
      // Stored language was preserved, never overwritten
      expect(localStorage.getItem('app_language')).toBe('zh')
    })

    it('Scenario 4: Explicit Launch App handoff (?lang=en on /) adopts language, writes storage/cookie, and strips query param', async () => {
      mockPathname = '/'
      mockSearchParams = new URLSearchParams('lang=en&tab=itinerary')
      window.history.replaceState(null, '', '/?lang=en&tab=itinerary')

      const Probe = () => {
        const { lang } = useLanguage()
        return <div data-testid="adopted-lang">{lang}</div>
      }

      render(
        <LanguageProvider>
          <Probe />
        </LanguageProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('adopted-lang').textContent).toBe('en')
      })

      // Explicit handoff accepted:
      expect(localStorage.getItem('app_language')).toBe('en')
      expect(document.cookie).toContain('app_language=en')

      // Query param ?lang=en stripped, but other params preserved
      expect(window.location.search).toBe('?tab=itinerary')
    })

    it('Scenario 5: Malformed language parameter on / (?lang=attacker) is safely rejected', async () => {
      mockPathname = '/'
      mockSearchParams = new URLSearchParams('lang=attacker_lang_xyz')
      window.history.replaceState(null, '', '/?lang=attacker_lang_xyz')

      const Probe = () => {
        const { lang } = useLanguage()
        return <div data-testid="rejected-lang">{lang}</div>
      }

      render(
        <LanguageProvider>
          <Probe />
        </LanguageProvider>
      )

      await waitFor(() => {
        // Must remain default 'zh', not 'attacker_lang_xyz'
        expect(screen.getByTestId('rejected-lang').textContent).toBe('zh')
      })

      // localStorage must NOT contain attacker language
      expect(localStorage.getItem('app_language')).toBeNull()
    })
  })
})
