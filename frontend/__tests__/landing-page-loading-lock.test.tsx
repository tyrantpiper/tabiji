import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'

const mockState = vi.hoisted(() => ({
  isOnboardingComplete: true,
}))

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}))

vi.mock('next/dynamic', () => ({
  default: () => {
    const MockAppShell = () => <div data-testid="mock-app-shell">AppShell</div>
    MockAppShell.displayName = 'MockAppShell'
    return MockAppShell
  },
}))

vi.mock('@/components/onboarding/WelcomeWizard', () => ({
  WelcomeWizard: ({ onComplete }: { onComplete: () => void }) => (
    <div data-testid="mock-welcome-wizard">
      <button onClick={onComplete}>Complete Wizard</button>
    </div>
  ),
}))

vi.mock('@/lib/stores/onboardingStore', () => ({
  useOnboardingStore: () => ({
    isCompleted: mockState.isOnboardingComplete,
  }),
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
  ensureValidSession: vi.fn(),
  restoreAccountWithKey: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  usersApi: {
    updateProfile: vi.fn(),
    getProfile: vi.fn(),
  },
}))

import { LandingPage } from '@/components/views/landing-page'
import { LanguageProvider } from '@/lib/LanguageContext'
import { toast } from 'sonner'
import { ensureValidSession, restoreAccountWithKey } from '@/lib/auth-session'
import { usersApi } from '@/lib/api'

function createDeferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function renderLanding(lang: 'zh' | 'en' = 'zh') {
  if (lang === 'en') {
    localStorage.setItem('app_language', 'en')
  } else {
    localStorage.removeItem('app_language')
  }
  return render(
    <LanguageProvider>
      <LandingPage />
    </LanguageProvider>
  )
}

describe('LandingPage Loading State, Anti-Double-Click & Recovery Lock', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    mockState.isOnboardingComplete = true
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
  })

  afterEach(() => {
    vi.useRealTimers()
    delete (document as unknown as { startViewTransition?: unknown }).startViewTransition
  })

  it('does not lock UI when nickname is empty or whitespace only', async () => {
    renderLanding('zh')

    const input = await screen.findByPlaceholderText('例如：小明')
    const startBtn = screen.getByRole('button', { name: /開始旅程/ })
    const useRecoveryBtn = screen.getByRole('button', { name: /使用引繼碼登入/ })

    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.click(startBtn)

    expect(toast.warning).toHaveBeenCalledWith('請輸入暱稱')
    expect(ensureValidSession).not.toHaveBeenCalled()
    expect(startBtn).not.toBeDisabled()
    expect(input).not.toBeDisabled()
    expect(useRecoveryBtn).not.toBeDisabled()
  })

  it('locks nickname input, Start Journey button (with Loader2 + status text), and recovery trigger button while login is in flight', async () => {
    const deferredSession = createDeferred<string | null>()
    const deferredProfile = createDeferred<unknown>()
    vi.mocked(ensureValidSession).mockImplementationOnce(() => {
      return deferredSession.promise.then((token) => {
        localStorage.setItem('user_uuid', '11111111-1111-4111-8111-111111111111')
        return token
      })
    })
    vi.mocked(usersApi.updateProfile).mockImplementationOnce(() => deferredProfile.promise as Promise<never>)

    renderLanding('zh')

    const input = await screen.findByPlaceholderText('例如：小明')
    fireEvent.change(input, { target: { value: '小明' } })

    const startBtn = screen.getByRole('button', { name: /開始旅程/ })
    const useRecoveryBtn = screen.getByRole('button', { name: /使用引繼碼登入/ })
    const zhSwitchBtn = screen.getByRole('button', { name: '切換為繁體中文' })
    const enSwitchBtn = screen.getByRole('button', { name: '切換為英文' })

    expect(startBtn).toHaveClass('select-none')
    expect(input).not.toHaveClass('select-none')
    expect(startBtn.closest('.max-w-xs')).not.toHaveClass('select-none')
    expect(zhSwitchBtn).not.toBeDisabled()
    expect(enSwitchBtn).not.toBeDisabled()

    // Rapid double click
    fireEvent.click(startBtn)
    fireEvent.click(startBtn)

    expect(ensureValidSession).toHaveBeenCalledTimes(1)
    expect(startBtn.closest('.max-w-xs')).toHaveClass('select-none')
    expect(input).toBeDisabled()
    expect(input).toHaveClass('select-none')
    expect(startBtn).toBeDisabled()
    expect(startBtn).toHaveAttribute('aria-busy', 'true')
    expect(startBtn).toHaveClass('select-none')
    expect(startBtn).toHaveTextContent('正在準備旅程...')
    expect(zhSwitchBtn).toBeDisabled()
    expect(enSwitchBtn).toBeDisabled()
    fireEvent.click(enSwitchBtn)
    expect(localStorage.getItem('app_language')).toBeNull()
    const spinner = startBtn.querySelector('svg.animate-spin')
    expect(spinner).not.toBeNull()
    expect(spinner).toHaveClass('size-5')

    expect(useRecoveryBtn).toBeDisabled()
    expect(useRecoveryBtn).toHaveClass('select-none')

    // Clicking disabled recovery button must not switch panels
    fireEvent.click(useRecoveryBtn)
    expect(screen.queryByText('帳號還原')).toBeNull()

    await act(async () => {
      deferredSession.resolve('mock-jwt')
    })
    await waitFor(() => {
      expect(usersApi.updateProfile).toHaveBeenCalledTimes(1)
    })

    // Still locked while updateProfile is pending
    expect(startBtn).toBeDisabled()

    await act(async () => {
      deferredProfile.resolve({ ok: true })
    })

    await waitFor(() => {
      expect(screen.getByTestId('mock-app-shell')).toBeInTheDocument()
    })
    expect(localStorage.getItem('user_nickname')).toBe('小明')
    expect(localStorage.getItem('user_uuid')).toBe('11111111-1111-4111-8111-111111111111')
  })

  it('displays English loading text when language is set to en', async () => {
    const deferredSession = createDeferred<string | null>()
    vi.mocked(ensureValidSession).mockImplementationOnce(() => deferredSession.promise)
    vi.mocked(usersApi.updateProfile).mockResolvedValueOnce({} as never)

    renderLanding('en')

    const input = await screen.findByPlaceholderText('E.g. Ryan')
    fireEvent.change(input, { target: { value: 'Ryan' } })

    const startBtn = screen.getByRole('button', { name: /Start Journey/ })
    fireEvent.click(startBtn)

    expect(startBtn).toBeDisabled()
    expect(startBtn).toHaveTextContent('Preparing journey...')
    expect(startBtn.querySelector('svg.animate-spin')).not.toBeNull()

    await act(async () => {
      deferredSession.resolve(null)
    })

    await waitFor(() => {
      expect(screen.getByTestId('mock-app-shell')).toBeInTheDocument()
    })
  })

  it('preserves offline login UUID fallback without breaking loading lock', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    mockState.isOnboardingComplete = false

    renderLanding('zh')

    const input = await screen.findByPlaceholderText('例如：小明')
    fireEvent.change(input, { target: { value: '離線旅人' } })

    const startBtn = screen.getByRole('button', { name: /開始旅程/ })
    fireEvent.click(startBtn)

    await waitFor(() => {
      expect(screen.getByTestId('mock-welcome-wizard')).toBeInTheDocument()
    })

    expect(ensureValidSession).not.toHaveBeenCalled()
    expect(usersApi.updateProfile).not.toHaveBeenCalled()
    expect(localStorage.getItem('user_nickname')).toBe('離線旅人')
    expect(localStorage.getItem('user_uuid')).toBeTruthy()
  })

  it('locks recovery input, Cancel button, and Recover button during recovery, unlocks on error, and stays locked during 800ms success handoff', async () => {
    const validRecoveryKey = 'tbj_rec_12345678_1234567890abcdef1234567890abcdef'

    renderLanding('zh')

    fireEvent.click(await screen.findByRole('button', { name: /使用引繼碼登入/ }))

    const codeInput = screen.getByPlaceholderText(/tbj_rec_xxxxxxxx_/)
    const cancelBtn = screen.getByRole('button', { name: '取消' })
    const recoverBtn = screen.getByRole('button', { name: '還原' })
    const zhSwitchBtn = screen.getByRole('button', { name: '切換為繁體中文' })
    const enSwitchBtn = screen.getByRole('button', { name: '切換為英文' })

    // Invalid format does not lock UI
    fireEvent.change(codeInput, { target: { value: 'invalid-key' } })
    fireEvent.click(recoverBtn)
    expect(toast.error).toHaveBeenCalledWith('引繼碼格式不正確')
    expect(recoverBtn).not.toBeDisabled()
    expect(cancelBtn).not.toBeDisabled()
    expect(codeInput).not.toBeDisabled()
    expect(zhSwitchBtn).not.toBeDisabled()
    expect(enSwitchBtn).not.toBeDisabled()

    // Valid format, failing request unlocks UI so user can retry or cancel
    const deferredFail = createDeferred<never>()
    vi.mocked(restoreAccountWithKey).mockImplementationOnce(() => deferredFail.promise)

    fireEvent.change(codeInput, { target: { value: validRecoveryKey } })
    fireEvent.click(recoverBtn)
    fireEvent.click(recoverBtn) // rapid double click

    expect(restoreAccountWithKey).toHaveBeenCalledTimes(1)
    expect(codeInput).toBeDisabled()
    expect(codeInput).toHaveClass('select-none')
    expect(cancelBtn).toBeDisabled()
    expect(cancelBtn).toHaveClass('select-none')
    expect(recoverBtn).toBeDisabled()
    expect(recoverBtn).toHaveAttribute('aria-busy', 'true')
    expect(recoverBtn).toHaveClass('select-none')
    expect(recoverBtn).toHaveTextContent('還原中...')
    expect(recoverBtn.querySelector('svg.animate-spin')).not.toBeNull()
    expect(zhSwitchBtn).toBeDisabled()
    expect(enSwitchBtn).toBeDisabled()
    fireEvent.click(enSwitchBtn)
    expect(localStorage.getItem('app_language')).toBeNull()

    await act(async () => {
      deferredFail.reject(new Error('Invalid recovery key'))
    })

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Invalid recovery key')
    })
    expect(codeInput).not.toBeDisabled()
    expect(cancelBtn).not.toBeDisabled()
    expect(recoverBtn).not.toBeDisabled()
    expect(recoverBtn).toHaveTextContent('還原')
    expect(zhSwitchBtn).not.toBeDisabled()
    expect(enSwitchBtn).not.toBeDisabled()

    // Valid format, succeeding request stays locked during 800ms handoff
    vi.useFakeTimers()
    const deferredSuccess = createDeferred<{ accessToken: string; userId: string; isNew: boolean }>()
    vi.mocked(restoreAccountWithKey).mockImplementationOnce(() => deferredSuccess.promise)
    vi.mocked(usersApi.getProfile).mockResolvedValueOnce({ name: 'Alice', avatar_url: '' } as never)

    fireEvent.click(recoverBtn)
    expect(recoverBtn).toBeDisabled()
    expect(cancelBtn).toBeDisabled()
    expect(enSwitchBtn).toBeDisabled()

    await act(async () => {
      deferredSuccess.resolve({
        accessToken: 'jwt-ok',
        userId: '22222222-2222-4222-8222-222222222222',
        isNew: false,
      })
      await Promise.resolve()
      await Promise.resolve()
    })

    // During 800ms handoff delay, buttons remain locked
    expect(toast.success).toHaveBeenCalledWith('歡迎回來，Alice！')
    expect(recoverBtn).toBeDisabled()
    expect(cancelBtn).toBeDisabled()
    expect(codeInput).toBeDisabled()
    expect(enSwitchBtn).toBeDisabled()
    expect(screen.queryByTestId('mock-app-shell')).toBeNull()

    await act(async () => {
      vi.advanceTimersByTime(800)
    })

    expect(screen.getByTestId('mock-app-shell')).toBeInTheDocument()
  })

  it('keeps recovery locked during offline recovery 800ms handoff and clears pending timer on unmount', async () => {
    vi.useFakeTimers()
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    vi.mocked(restoreAccountWithKey).mockRejectedValueOnce(new Error('Network unavailable'))
    const startViewTransitionMock = vi.fn((cb: () => void) => cb())
    Object.defineProperty(document, 'startViewTransition', {
      configurable: true,
      value: startViewTransitionMock,
    })

    const { unmount } = renderLanding('zh')

    fireEvent.click(screen.getByRole('button', { name: /使用引繼碼登入/ }))
    const codeInput = screen.getByPlaceholderText(/tbj_rec_xxxxxxxx_/)
    const recoverBtn = screen.getByRole('button', { name: '還原' })
    const cancelBtn = screen.getByRole('button', { name: '取消' })

    fireEvent.change(codeInput, {
      target: { value: 'tbj_rec_12345678_1234567890abcdef1234567890abcdef' },
    })
    fireEvent.click(recoverBtn)

    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(toast.success).toHaveBeenCalledWith('帳號已還原（離線模式）')
    expect(recoverBtn).toBeDisabled()
    expect(cancelBtn).toBeDisabled()
    expect(codeInput).toBeDisabled()

    unmount()
    await act(async () => {
      vi.advanceTimersByTime(1000)
    })

    expect(startViewTransitionMock).not.toHaveBeenCalled()
  })

  it('preserves document.startViewTransition flow on login without flashing back to idle state', async () => {
    const deferredSession = createDeferred<string | null>()
    vi.mocked(ensureValidSession).mockImplementationOnce(() => deferredSession.promise)
    vi.mocked(usersApi.updateProfile).mockResolvedValueOnce({} as never)

    let pendingTransitionCb: (() => void) | null = null
    const startViewTransitionMock = vi.fn((cb: () => void) => {
      pendingTransitionCb = cb
    })
    Object.defineProperty(document, 'startViewTransition', {
      configurable: true,
      value: startViewTransitionMock,
    })

    renderLanding('zh')

    const input = await screen.findByPlaceholderText('例如：小明')
    fireEvent.change(input, { target: { value: '轉場測試' } })
    const startBtn = screen.getByRole('button', { name: /開始旅程/ })
    fireEvent.click(startBtn)

    await act(async () => {
      deferredSession.resolve('mock-jwt')
      await Promise.resolve()
      await Promise.resolve()
    })

    await waitFor(() => {
      expect(startViewTransitionMock).toHaveBeenCalledTimes(1)
    })

    // While startViewTransition callback has not executed yet, button remains locked
    expect(startBtn).toBeDisabled()
    expect(startBtn).toHaveTextContent('正在準備旅程...')

    await act(async () => {
      pendingTransitionCb?.()
    })

    expect(screen.getByTestId('mock-app-shell')).toBeInTheDocument()
  })

  it('clears pre-existing text selection in nickname and recovery inputs when locking', async () => {
    const deferredSession = createDeferred<string | null>()
    vi.mocked(ensureValidSession).mockImplementationOnce(() => deferredSession.promise)
    vi.mocked(usersApi.updateProfile).mockResolvedValueOnce({} as never)

    const removeAllRangesSpy = vi.fn()
    const getSelectionSpy = vi.spyOn(window, 'getSelection').mockReturnValue({
      removeAllRanges: removeAllRangesSpy,
    } as unknown as Selection)

    renderLanding('zh')

    const input = (await screen.findByPlaceholderText('例如：小明')) as HTMLInputElement
    fireEvent.change(input, { target: { value: '小明測試' } })
    input.focus()
    input.setSelectionRange(0, 4)
    expect(input.selectionStart).toBe(0)
    expect(input.selectionEnd).toBe(4)

    fireEvent.click(screen.getByRole('button', { name: /開始旅程/ }))

    expect(input.selectionStart).toBe(input.selectionEnd)
    expect(document.activeElement).not.toBe(input)
    expect(removeAllRangesSpy).toHaveBeenCalled()

    await act(async () => {
      deferredSession.resolve(null)
    })
    getSelectionSpy.mockRestore()
  })

  it('supports Enter key submission with IME composition guard and prevents duplicate submit while locked', async () => {
    const deferredSession = createDeferred<string | null>()
    vi.mocked(ensureValidSession).mockImplementationOnce(() => deferredSession.promise)
    vi.mocked(usersApi.updateProfile).mockResolvedValueOnce({} as never)

    renderLanding('zh')

    const input = await screen.findByPlaceholderText('例如：小明')
    fireEvent.change(input, { target: { value: '小' } })

    // IME composition Enter must NOT submit
    const composingEvent = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })
    Object.defineProperty(composingEvent, 'isComposing', { value: true })
    fireEvent(input, composingEvent)
    expect(ensureValidSession).not.toHaveBeenCalled()

    // Normal Enter submits and locks
    fireEvent.keyDown(input, { key: 'Enter' })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(ensureValidSession).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: /正在準備旅程/ })).toBeDisabled()

    await act(async () => {
      deferredSession.resolve(null)
    })
    await waitFor(() => {
      expect(screen.getByTestId('mock-app-shell')).toBeInTheDocument()
    })
  })

  it('supports Enter key submission in recovery input with IME guard', async () => {
    const deferredRecover = createDeferred<{ accessToken: string; userId: string; isNew: boolean }>()
    vi.mocked(restoreAccountWithKey).mockImplementationOnce(() => deferredRecover.promise)

    renderLanding('zh')
    fireEvent.click(await screen.findByRole('button', { name: /使用引繼碼登入/ }))

    const codeInput = screen.getByPlaceholderText(/tbj_rec_xxxxxxxx_/)
    fireEvent.change(codeInput, {
      target: { value: 'tbj_rec_12345678_1234567890abcdef1234567890abcdef' },
    })

    const composingEvent = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })
    Object.defineProperty(composingEvent, 'isComposing', { value: true })
    fireEvent(codeInput, composingEvent)
    expect(restoreAccountWithKey).not.toHaveBeenCalled()

    fireEvent.keyDown(codeInput, { key: 'Enter' })
    fireEvent.keyDown(codeInput, { key: 'Enter' })
    expect(restoreAccountWithKey).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: /還原中/ })).toBeDisabled()

    await act(async () => {
      deferredRecover.reject(new Error('Invalid recovery key'))
    })
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Invalid recovery key')
    })
  })

  it('unlocks UI with toast error instead of unhandled rejection when storage throws on login or offline recovery', async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('QuotaExceededError')
    })

    try {
      renderLanding('zh')
      const input = await screen.findByPlaceholderText('例如：小明')
      fireEvent.change(input, { target: { value: '小明' } })

      const startBtn = screen.getByRole('button', { name: /開始旅程/ })
      fireEvent.click(startBtn)

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalled()
      })
      expect(startBtn).not.toBeDisabled()
      expect(input).not.toBeDisabled()

      // Fallback localized copy when thrown error has no message
      vi.mocked(toast.error).mockClear()
      setItemSpy.mockImplementation(() => {
        throw new Error('')
      })
      fireEvent.click(startBtn)
      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('無法開始旅程，請稍後再試')
      })

      // Also verify offline recovery storage throw fallback copy
      vi.mocked(toast.error).mockClear()
      Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
      vi.mocked(restoreAccountWithKey).mockRejectedValueOnce(new Error('Offline'))

      fireEvent.click(screen.getByRole('button', { name: /使用引繼碼登入/ }))
      const codeInput = screen.getByPlaceholderText(/tbj_rec_xxxxxxxx_/)
      const recoverBtn = screen.getByRole('button', { name: '還原' })
      fireEvent.change(codeInput, {
        target: { value: 'tbj_rec_12345678_1234567890abcdef1234567890abcdef' },
      })
      fireEvent.click(recoverBtn)

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith('離線還原失敗，請稍後再試')
      })
      expect(recoverBtn).not.toBeDisabled()
      expect(codeInput).not.toBeDisabled()
    } finally {
      setItemSpy.mockRestore()
    }
  })

  it('does not schedule 800ms handoff timer or call startViewTransition if unmounted while recovery is in flight', async () => {
    vi.useFakeTimers()
    const deferredRecover = createDeferred<{ accessToken: string; userId: string; isNew: boolean }>()
    vi.mocked(restoreAccountWithKey).mockImplementationOnce(() => deferredRecover.promise)
    vi.mocked(usersApi.getProfile).mockResolvedValueOnce({ name: 'Alice', avatar_url: '' } as never)

    const startViewTransitionMock = vi.fn((cb: () => void) => cb())
    Object.defineProperty(document, 'startViewTransition', {
      configurable: true,
      value: startViewTransitionMock,
    })

    const { unmount } = renderLanding('zh')
    fireEvent.click(screen.getByRole('button', { name: /使用引繼碼登入/ }))

    const codeInput = screen.getByPlaceholderText(/tbj_rec_xxxxxxxx_/)
    fireEvent.change(codeInput, {
      target: { value: 'tbj_rec_12345678_1234567890abcdef1234567890abcdef' },
    })
    fireEvent.click(screen.getByRole('button', { name: '還原' }))

    unmount()

    await act(async () => {
      deferredRecover.resolve({
        accessToken: 'jwt-ok',
        userId: '22222222-2222-4222-8222-222222222222',
        isNew: false,
      })
      await Promise.resolve()
      await Promise.resolve()
    })

    await act(async () => {
      vi.advanceTimersByTime(1000)
    })

    expect(startViewTransitionMock).not.toHaveBeenCalled()
  })

  it('falls back safely when document.startViewTransition is defined as undefined', async () => {
    vi.mocked(ensureValidSession).mockResolvedValueOnce(null)
    vi.mocked(usersApi.updateProfile).mockResolvedValueOnce({} as never)

    Object.defineProperty(document, 'startViewTransition', {
      configurable: true,
      value: undefined,
    })

    renderLanding('zh')
    const input = await screen.findByPlaceholderText('例如：小明')
    fireEvent.change(input, { target: { value: '降級測試' } })
    fireEvent.click(screen.getByRole('button', { name: /開始旅程/ }))

    await waitFor(() => {
      expect(screen.getByTestId('mock-app-shell')).toBeInTheDocument()
    })
  })
})
