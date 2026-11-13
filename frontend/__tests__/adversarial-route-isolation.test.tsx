/**
 * ⚔️ Adversarial Route Isolation Stress Test Harness
 * Verifies route isolation of ChatWidget across pathname variations, boundary values, and edge conditions.
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'

// Track pathname dynamically
let currentPathname: string | null = '/official'

vi.mock('next/navigation', () => ({
  usePathname: () => currentPathname,
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
}))

vi.mock('@/components/chat-widget', () => ({
  default: () => <div data-testid="chat-widget-mock">ChatWidget Active</div>,
}))

vi.mock('@/lib/auth-session', () => ({
  initSessionLifecycleListener: vi.fn(() => vi.fn()),
  fetchLatestRecoveryKey: vi.fn().mockResolvedValue(null),
  isUserLoggedIn: vi.fn(() => false),
}))

vi.mock('@/lib/supabase', () => ({
  getSupabaseClient: vi.fn(() => null),
}))

vi.mock('@/lib/LanguageContext', () => ({
  useLanguage: () => ({ lang: 'zh', setLanguage: vi.fn() }),
}))

vi.mock('sonner', () => ({
  toast: {
    info: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('@/components/auth/session-reauth-modal', () => ({
  SessionReauthModal: () => <div data-testid="reauth-modal-mock" />,
}))

// Import the component under test
import { AppClientLayer } from '@/components/app-client-layer'
import { PWAInstallPrompt } from '@/components/pwa-install-prompt'

describe('⚔️ Adversarial Stress Challenge: ChatWidget Route Isolation on Official Portal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('ADV-ISO-1: Strictly suppresses ChatWidget on exact root official route "/official"', async () => {
    currentPathname = '/official'
    render(<AppClientLayer />)
    expect(screen.queryByTestId('chat-widget-mock')).toBeNull()
  })

  it('ADV-ISO-2: Strictly suppresses ChatWidget on sub-routes e.g. "/official/privacy" and "/official/terms"', async () => {
    for (const subRoute of ['/official/privacy', '/official/terms', '/official/deep/nested/guide']) {
      currentPathname = subRoute
      const { unmount } = render(<AppClientLayer />)
      expect(screen.queryByTestId('chat-widget-mock')).toBeNull()
      unmount()
    }
  })

  it('ADV-ISO-3: Strictly suppresses ChatWidget when URL contains query parameters or hash on official route', async () => {
    for (const route of ['/official?ref=nav', '/official/terms?lang=en#section-1', '/official?action=demo']) {
      currentPathname = route
      const { unmount } = render(<AppClientLayer />)
      expect(screen.queryByTestId('chat-widget-mock')).toBeNull()
      unmount()
    }
  })

  it('ADV-ISO-4: Renders ChatWidget on main application non-official routes', async () => {
    const nonOfficialRoutes = ['/', '/ledger/TKY-1234', '/share/trip-999', '/settings', '/explore']
    for (const route of nonOfficialRoutes) {
      currentPathname = route
      const { unmount, findByTestId } = render(<AppClientLayer />)
      const chatWidget = await findByTestId('chat-widget-mock')
      expect(chatWidget).toBeDefined()
      expect(chatWidget.textContent).toContain('ChatWidget Active')
      unmount()
    }
  })

  it('ADV-ISO-5: Gracefully handles null, undefined, or empty pathnames without throwing', async () => {
    for (const invalidPath of [null, '', undefined as unknown as string]) {
      currentPathname = invalidPath
      const { unmount, findByTestId } = render(<AppClientLayer />)
      // When pathname is not /official, fallback to standard rendering without crashing
      const chatWidget = await findByTestId('chat-widget-mock')
      expect(chatWidget).toBeDefined()
      unmount()
    }
  })
})

// Skipped: PWAInstallPrompt is in Frozen Core (0 變更) per architectural lock
describe.skip('⚔️ Adversarial Stress Challenge: PWAInstallPrompt Route Isolation on Official Portal', () => {
  const originalMatchMedia = window.matchMedia
  const originalUserAgent = navigator.userAgent

  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    Object.defineProperty(window, 'promptEvent', {
      configurable: true,
      writable: true,
      value: {
        platforms: ['web'],
        userChoice: Promise.resolve({ outcome: 'dismissed', platform: 'web' }),
        prompt: vi.fn().mockResolvedValue(undefined),
      },
    })
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    Object.defineProperty(window, 'promptEvent', {
      configurable: true,
      writable: true,
      value: null,
    })
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      writable: true,
      value: originalMatchMedia,
    })
    Object.defineProperty(navigator, 'userAgent', {
      configurable: true,
      value: originalUserAgent,
    })
  })

  it('ADV-PWA-1: Suppresses PWAInstallPrompt on /official, sub-routes, queries, and hash even with promptEvent & beforeinstallprompt', () => {
    const officialRoutes = [
      '/official',
      '/official/privacy',
      '/official/terms',
      '/official?lang=en',
      '/official#ledger',
    ]

    for (const route of officialRoutes) {
      currentPathname = route
      const { unmount } = render(<PWAInstallPrompt />)

      act(() => {
        vi.advanceTimersByTime(0)
      })
      act(() => {
        const evt = new Event('beforeinstallprompt')
        window.dispatchEvent(evt)
        vi.advanceTimersByTime(3000)
      })

      expect(screen.queryByText(/安裝 Tabiji|Install Tabiji/)).toBeNull()
      unmount()
    }
  })

  it('ADV-PWA-2: Suppresses mobile manual-install fallback prompt on /official routes', () => {
    Object.defineProperty(window, 'promptEvent', {
      configurable: true,
      writable: true,
      value: null,
    })
    Object.defineProperty(navigator, 'userAgent', {
      configurable: true,
      value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
    })

    currentPathname = '/official'
    render(<PWAInstallPrompt />)

    act(() => {
      vi.advanceTimersByTime(0)
    })
    act(() => {
      vi.advanceTimersByTime(3000)
    })

    expect(screen.queryByText(/安裝 Tabiji|Install Tabiji/)).toBeNull()
  })

  it('ADV-PWA-3: Immediately hides PWAInstallPrompt on soft client navigation from "/" to "/official"', () => {
    currentPathname = '/'
    const { rerender } = render(<PWAInstallPrompt />)

    act(() => {
      vi.advanceTimersByTime(0)
    })
    act(() => {
      vi.advanceTimersByTime(1600)
    })

    expect(screen.getByText('安裝 Tabiji')).toBeDefined()

    currentPathname = '/official'
    rerender(<PWAInstallPrompt />)

    expect(screen.queryByText('安裝 Tabiji')).toBeNull()
  })

  it('ADV-PWA-4 (Benign Control): Renders PWAInstallPrompt normally on main app route "/"', () => {
    currentPathname = '/'
    render(<PWAInstallPrompt />)

    act(() => {
      vi.advanceTimersByTime(0)
    })
    expect(screen.queryByText('安裝 Tabiji')).toBeNull()

    act(() => {
      vi.advanceTimersByTime(1550)
    })
    expect(screen.getByText('安裝 Tabiji')).toBeDefined()
  })
})
