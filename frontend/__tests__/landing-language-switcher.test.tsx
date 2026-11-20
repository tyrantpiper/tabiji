/**
 * @vitest-environment jsdom
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act, renderHook } from '@testing-library/react'
import fs from 'node:fs'
import path from 'node:path'

const mockState = vi.hoisted(() => ({
  pathname: '/',
  searchParams: new URLSearchParams(),
  shouldThrowAppShell: false,
}))

vi.mock('next/navigation', () => ({
  usePathname: () => mockState.pathname,
  useSearchParams: () => mockState.searchParams,
}))

vi.mock('next/dynamic', () => ({
  default: () => {
    const MockAppShell = () => {
      if (mockState.shouldThrowAppShell) {
        throw new Error('ChunkLoadError: Loading chunk failed')
      }
      return <div data-testid="mock-app-shell">AppShell</div>
    }
    MockAppShell.displayName = 'MockAppShell'
    return MockAppShell
  },
}))

vi.mock('@/components/onboarding/WelcomeWizard', () => ({
  WelcomeWizard: ({ onComplete }: { onComplete: () => void }) => (
    <button onClick={onComplete}>Complete Wizard</button>
  ),
}))

vi.mock('@/lib/stores/onboardingStore', () => ({
  useOnboardingStore: () => ({ isCompleted: true }),
}))

vi.mock('sonner', () => ({
  toast: {
    warning: vi.fn(),
    error: vi.fn(),
    loading: vi.fn(() => 'toast-loading-id'),
    dismiss: vi.fn(),
    success: vi.fn(),
  },
}))

vi.mock('@/lib/auth-session', () => ({
  ensureValidSession: vi.fn().mockResolvedValue(null),
  restoreAccountWithKey: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  usersApi: {
    updateProfile: vi.fn().mockResolvedValue({}),
    getProfile: vi.fn().mockResolvedValue({ name: 'Alice', avatar_url: '' }),
  },
}))

import { LandingLanguageSwitcher } from '@/components/auth/landing-language-switcher'
import { LandingPage } from '@/components/views/landing-page'
import { LanguageProvider, useLanguage, type TranslationKey } from '@/lib/LanguageContext'
import { remainingTranslations } from '@/lib/i18n/remaining'
import { translations as legacyTranslations } from '@/lib/translations'
import { toast } from 'sonner'
import { restoreAccountWithKey } from '@/lib/auth-session'
import { usersApi } from '@/lib/api'

const LANDING_NEW_KEYS = [
  'landing_lang_switcher_aria',
  'landing_lang_zh',
  'landing_lang_en',
  'landing_lang_switch_to_zh',
  'landing_lang_switch_to_en',
  'landing_recovery_placeholder',
  'landing_verifying_identity',
  'landing_welcome_back',
  'landing_recovered_offline',
  'landing_verify_failed',
  'landing_footer_tagline',
  'landing_offline_loading_title',
  'landing_offline_loading_desc',
  'landing_offline_retry',
] as const

describe('LandingLanguageSwitcher & LandingPage Bilingual Safety Net', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    document.cookie = 'app_language=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
    window.history.replaceState(null, '', '/')
    mockState.pathname = '/'
    mockState.searchParams = new URLSearchParams()
    mockState.shouldThrowAppShell = false
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  describe('1. Pure Presentational LandingLanguageSwitcher Contract', () => {
    const defaultLabels = {
      groupAria: '語系切換',
      zhLabel: '繁中',
      enLabel: 'EN',
      switchToZhAria: '切換為繁體中文',
      switchToEnAria: '切換為英文',
    }

    it('renders accessible group, 44px touch targets, contrast & isolation tokens, and toggles cleanly', () => {
      const onChange = vi.fn()
      const { rerender } = render(
        <LandingLanguageSwitcher lang="zh" onChange={onChange} labels={defaultLabels} />
      )

      const group = screen.getByRole('group', { name: '語系切換' })
      expect(group).toHaveClass('isolate', 'select-none', 'touch-manipulation')

      const zhBtn = screen.getByRole('button', { name: '切換為繁體中文' })
      const enBtn = screen.getByRole('button', { name: '切換為英文' })

      expect(zhBtn).toHaveAttribute('type', 'button')
      expect(zhBtn).toHaveAttribute('aria-pressed', 'true')
      expect(enBtn).toHaveAttribute('type', 'button')
      expect(enBtn).toHaveAttribute('aria-pressed', 'false')

      for (const btn of [zhBtn, enBtn]) {
        expect(btn.className).toContain('min-h-11')
        expect(btn.className).toContain('min-w-11')
        expect(btn.className).toContain('whitespace-nowrap')
        expect(btn.className).toContain('shrink-0')
        expect(btn.className).toContain('touch-manipulation')
        expect(btn.className).toContain('select-none')
        expect(btn.className).toContain('focus-visible:ring-2')
        expect(btn.className).toContain('focus-visible:ring-offset-2')
        expect(btn.className).toContain('focus-visible:ring-offset-white')
        expect(btn.className).toContain('dark:focus-visible:ring-offset-slate-800')
      }

      fireEvent.click(enBtn)
      expect(onChange).toHaveBeenCalledWith('en')

      rerender(<LandingLanguageSwitcher lang="en" onChange={onChange} labels={defaultLabels} />)
      expect(zhBtn).toHaveAttribute('aria-pressed', 'false')
      expect(enBtn).toHaveAttribute('aria-pressed', 'true')

      fireEvent.click(zhBtn)
      expect(onChange).toHaveBeenCalledWith('zh')
    })

    it('enforces disabled styling and suppresses clicks when disabled', () => {
      const onChange = vi.fn()
      render(
        <LandingLanguageSwitcher lang="zh" onChange={onChange} disabled={true} labels={defaultLabels} />
      )

      const zhBtn = screen.getByRole('button', { name: '切換為繁體中文' })
      const enBtn = screen.getByRole('button', { name: '切換為英文' })

      expect(zhBtn).toBeDisabled()
      expect(enBtn).toBeDisabled()
      expect(enBtn.className).toContain('disabled:opacity-50')
      expect(enBtn.className).toContain('disabled:pointer-events-none')
      expect(enBtn.className).toContain('disabled:cursor-not-allowed')

      fireEvent.click(enBtn)
      fireEvent.click(zhBtn)
      expect(onChange).not.toHaveBeenCalled()
    })

    it('supports prefers-reduced-motion cleanly and drops layoutId when reduced', () => {
      const switcherSrc = fs.readFileSync(
        path.resolve(__dirname, '../components/auth/landing-language-switcher.tsx'),
        'utf-8'
      )
      expect(switcherSrc).toContain('useReducedMotion')
      expect(switcherSrc).toContain('layoutId={shouldReduceMotion ? undefined : "landing-lang-pill"}')

      const origMatchMedia = window.matchMedia
      Object.defineProperty(window, 'matchMedia', {
        configurable: true,
        value: vi.fn().mockImplementation((query: string) => ({
          matches: query === '(prefers-reduced-motion: reduce)',
          media: query,
          onchange: null,
          addListener: vi.fn(),
          removeListener: vi.fn(),
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        })),
      })

      try {
        render(
          <LandingLanguageSwitcher lang="en" onChange={vi.fn()} labels={defaultLabels} />
        )
        const enBtn = screen.getByRole('button', { name: '切換為英文' })
        expect(enBtn).toHaveAttribute('aria-pressed', 'true')
        expect(enBtn.querySelector('.z-0')).not.toBeNull()
      } finally {
        Object.defineProperty(window, 'matchMedia', {
          configurable: true,
          value: origMatchMedia,
        })
      }
    })
  })

  describe('2. LanguageContext Storage, Runtime Validation & Interpolation Safety Net', () => {
    it('isolates localStorage QuotaExceededError from document.cookie sync and vice versa', () => {
      const { result } = renderHook(() => useLanguage(), {
        wrapper: LanguageProvider,
      })

      const setItemSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
        throw new DOMException('QuotaExceededError')
      })

      act(() => {
        result.current.setLang('en')
      })

      expect(result.current.lang).toBe('en')
      expect(document.cookie).toContain('app_language=en')
      setItemSpy.mockRestore()

      const cookieSpy = vi.spyOn(document, 'cookie', 'set').mockImplementation(() => {
        throw new Error('Cookie write blocked')
      })

      act(() => {
        result.current.setLang('zh')
      })

      expect(result.current.lang).toBe('zh')
      expect(localStorage.getItem('app_language')).toBe('zh')
      cookieSpy.mockRestore()
    })

    it('survives localStorage.getItem SecurityError during mount and rejects invalid runtime language values', () => {
      vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
        throw new DOMException('SecurityError')
      })

      const { result } = renderHook(() => useLanguage(), {
        wrapper: LanguageProvider,
      })

      expect(result.current.lang).toBe('zh')

      act(() => {
        result.current.setLang('fr' as unknown as 'en' | 'zh')
        result.current.setLang('__proto__' as unknown as 'en' | 'zh')
      })
      expect(result.current.lang).toBe('zh')
    })

    it('prevents $& replacement expansion, prototype key lookup, and supports fallback params outside Provider', () => {
      const { result } = renderHook(() => useLanguage(), {
        wrapper: LanguageProvider,
      })

      act(() => {
        result.current.setLang('en')
      })

      expect(result.current.t('landing_welcome_back', { name: 'Alice$&$$$1' })).toBe(
        'Welcome back, Alice$&$$$1!'
      )
      expect(result.current.t('toString' as TranslationKey)).toBe('toString')
      expect(result.current.t('constructor' as TranslationKey)).toBe('constructor')

      const { result: fallbackResult } = renderHook(() => useLanguage())
      expect(fallbackResult.current.t('landing_welcome_back', { name: '旅人' })).toBe(
        '歡迎回來，旅人！'
      )
    })

    it('preserves /official storage isolation and ?lang= URL handoff cleanup', async () => {
      mockState.pathname = '/official'
      mockState.searchParams = new URLSearchParams('lang=en')
      window.history.replaceState(null, '', '/official?lang=en')

      const Probe = () => {
        const { lang } = useLanguage()
        return <div data-testid="handoff-lang">{lang}</div>
      }

      const { rerender } = render(
        <LanguageProvider>
          <Probe />
        </LanguageProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('handoff-lang').textContent).toBe('zh')
      })
      expect(localStorage.getItem('app_language')).toBeNull()

      mockState.pathname = '/'
      mockState.searchParams = new URLSearchParams('trip=t1&lang=en')
      window.history.replaceState(null, '', '/?trip=t1&lang=en#day1')

      rerender(
        <LanguageProvider>
          <Probe />
        </LanguageProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('handoff-lang').textContent).toBe('en')
      })
      expect(localStorage.getItem('app_language')).toBe('en')
      expect(window.location.search).toBe('?trip=t1')
      expect(window.location.hash).toBe('#day1')
    })
  })

  describe('3. LandingPage End-to-End Bilingual Switching, Layout & Recovery Flows', () => {
    it('places switcher in top-right safe-area wrapper and removes conflicting py-8 sm:py-12 from main', async () => {
      const { container } = render(
        <LanguageProvider>
          <LandingPage />
        </LanguageProvider>
      )

      const group = await screen.findByRole('group', { name: '語系切換' })
      const wrapper = group.parentElement
      expect(wrapper?.className).toContain('top-[calc(max(env(safe-area-inset-top,0px),0px)+0.75rem)]')
      expect(wrapper?.className).toContain('right-4')
      expect(wrapper?.className).toContain('z-20')

      const main = container.querySelector('main')
      expect(main?.className).toContain('pt-[calc(max(env(safe-area-inset-top,0px),0px)+4rem)]')
      expect(main?.className).toContain('pb-24')
      expect(main?.className).toContain('sm:pb-12')
      expect(main?.className).not.toContain('py-8')
    })

    it('survives Storage SecurityError during LandingPage mount with deep-link query intact', async () => {
      window.history.replaceState(null, '', '/?trip=t1')
      vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
        throw new DOMException('SecurityError', 'SecurityError')
      })
      vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
        throw new DOMException('SecurityError', 'SecurityError')
      })

      render(
        <LanguageProvider>
          <LandingPage />
        </LanguageProvider>
      )

      expect(await screen.findByRole('group', { name: '語系切換' })).toBeInTheDocument()
      expect(screen.getByText('旅路 ｜ 旅行提案')).toBeInTheDocument()
    })

    it('switches copy live across main form, recovery panel, and footer without losing typed input', async () => {
      render(
        <LanguageProvider>
          <LandingPage />
        </LanguageProvider>
      )

      const nicknameInput = (await screen.findByPlaceholderText('例如：小明')) as HTMLInputElement
      fireEvent.change(nicknameInput, { target: { value: 'Ryan' } })
      expect(screen.getByText('旅路 ｜ 旅行提案')).toBeInTheDocument()
      expect(screen.getByText('您的智慧旅途夥伴')).toBeInTheDocument()

      // Switch to EN on main form
      fireEvent.click(screen.getByRole('button', { name: '切換為英文' }))

      expect(await screen.findByText('Tabiji | Travel Planner')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('E.g. Ryan')).toHaveValue('Ryan')
      expect(screen.getByText('Your Smart Travel Companion')).toBeInTheDocument()
      expect(localStorage.getItem('app_language')).toBe('en')
      expect(document.cookie).toContain('app_language=en')

      // Open recovery panel in EN mode
      fireEvent.click(screen.getByRole('button', { name: /Use Recovery Key/ }))
      expect(screen.getByText('Account Recovery')).toBeInTheDocument()
      const recInput = screen.getByPlaceholderText('tbj_rec_xxxxxxxx_... or UUID') as HTMLInputElement
      fireEvent.change(recInput, { target: { value: 'tbj_rec_12345678' } })

      // Switch back to ZH inside recovery panel without losing typed code
      fireEvent.click(screen.getByRole('button', { name: 'Switch to Traditional Chinese' }))
      expect(await screen.findByText('帳號還原')).toBeInTheDocument()
      expect(screen.getByPlaceholderText('tbj_rec_xxxxxxxx_... 或 UUID')).toHaveValue('tbj_rec_12345678')
      expect(screen.getByText('您的智慧旅途夥伴')).toBeInTheDocument()
      expect(localStorage.getItem('app_language')).toBe('zh')
    })

    it('emits localized loading/success/error/offline recovery toasts in EN and handles empty Error message fallback', async () => {
      localStorage.setItem('app_language', 'en')

      const validKey = 'tbj_rec_12345678_1234567890abcdef1234567890abcdef'
      vi.mocked(restoreAccountWithKey).mockRejectedValueOnce(new Error(''))

      render(
        <LanguageProvider>
          <LandingPage />
        </LanguageProvider>
      )

      const useRecoveryBtn = await screen.findByRole('button', { name: /Use Recovery Key/ })
      vi.useFakeTimers()
      fireEvent.click(useRecoveryBtn)

      const recInput = screen.getByPlaceholderText('tbj_rec_xxxxxxxx_... or UUID')
      const recoverBtn = screen.getByRole('button', { name: 'Recover' })
      fireEvent.change(recInput, { target: { value: validKey } })
      fireEvent.click(recoverBtn)

      expect(toast.loading).toHaveBeenCalledWith('Verifying identity...')

      await act(async () => {
        await Promise.resolve()
        await Promise.resolve()
      })
      expect(toast.error).toHaveBeenCalledWith('Failed to verify recovery key')

      // Online recovery success in EN
      vi.mocked(restoreAccountWithKey).mockResolvedValueOnce({
        accessToken: 'jwt-en',
        userId: '33333333-3333-4333-8333-333333333333',
        isNew: false,
      })
      vi.mocked(usersApi.getProfile).mockResolvedValueOnce({ name: 'Bob', avatar_url: '' } as never)

      fireEvent.click(recoverBtn)
      await act(async () => {
        await Promise.resolve()
        await Promise.resolve()
      })
      expect(toast.success).toHaveBeenCalledWith('Welcome back, Bob!')
    })

    it('emits localized offline recovery toast in EN', async () => {
      localStorage.setItem('app_language', 'en')
      Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
      vi.mocked(restoreAccountWithKey).mockRejectedValueOnce(new Error('Offline'))

      render(
        <LanguageProvider>
          <LandingPage />
        </LanguageProvider>
      )

      fireEvent.click(await screen.findByRole('button', { name: /Use Recovery Key/ }))
      fireEvent.change(screen.getByPlaceholderText('tbj_rec_xxxxxxxx_... or UUID'), {
        target: { value: 'tbj_rec_12345678_1234567890abcdef1234567890abcdef' },
      })
      fireEvent.click(screen.getByRole('button', { name: 'Recover' }))

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith('Account recovered (Offline Mode)')
      })
    })

    it('renders localized ChunkErrorBoundary fallback in EN when AppShell chunk fails', async () => {
      localStorage.setItem('app_language', 'en')
      localStorage.setItem('user_nickname', 'Ryan')
      localStorage.setItem('user_uuid', '44444444-4444-4444-8444-444444444444')
      mockState.shouldThrowAppShell = true

      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

      try {
        render(
          <LanguageProvider>
            <LandingPage />
          </LanguageProvider>
        )

        expect(await screen.findByText('Loading Offline')).toBeInTheDocument()
        expect(
          screen.getByText('Loading core modules from local offline cache. Please check device cache or retry.')
        ).toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument()
      } finally {
        warnSpy.mockRestore()
        errorSpy.mockRestore()
      }
    })
  })

  describe('4. i18n Symmetric Key Parity & Recovery Placeholder Sentinel', () => {
    it('defines all 14 landing_* keys symmetrically in remaining.ts and translations.ts with tbj_rec_xxxxxxxx_ preserved', () => {
      for (const key of LANDING_NEW_KEYS) {
        expect(remainingTranslations.en[key]).toBeTruthy()
        expect(remainingTranslations.zh[key]).toBeTruthy()
        expect(legacyTranslations.en[key]).toBeTruthy()
        expect(legacyTranslations.zh[key]).toBeTruthy()
      }

      expect(remainingTranslations.en.landing_recovery_placeholder).toContain('tbj_rec_xxxxxxxx_')
      expect(remainingTranslations.zh.landing_recovery_placeholder).toContain('tbj_rec_xxxxxxxx_')
      expect(legacyTranslations.en.landing_recovery_placeholder).toContain('tbj_rec_xxxxxxxx_')
      expect(legacyTranslations.zh.landing_recovery_placeholder).toContain('tbj_rec_xxxxxxxx_')
    })
  })
})
