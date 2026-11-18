/**
 * @vitest-environment jsdom
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'

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
        <button onClick={onComplete}>Complete</button>
    ),
}))

vi.mock('@/lib/stores/onboardingStore', () => ({
    useOnboardingStore: () => ({ isCompleted: true }),
}))

vi.mock('sonner', () => ({
    toast: {
        warning: vi.fn(),
        error: vi.fn(),
        loading: vi.fn(() => 'id'),
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

function seedTripStorage() {
    localStorage.setItem(
        'trip-storage',
        JSON.stringify({
            state: { activeTripId: 'old-trip-1', activeTripTitle: 'Old Trip 1', userId: 'old-u' },
            version: 0,
        })
    )
    localStorage.setItem(
        'tabidachi-trip-storage',
        JSON.stringify({
            state: { activeTripId: 'old-trip-2', activeTripTitle: 'Old Trip 2', userId: 'old-u' },
            version: 0,
        })
    )
}

describe('LandingPage Orphan Nickname Guard & Dual-Storage Coherency', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        localStorage.clear()
        sessionStorage.clear()
        Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
        vi.mocked(usersApi.updateProfile).mockResolvedValue({ ok: true })
        vi.mocked(usersApi.getProfile).mockResolvedValue({ name: 'Alice', avatar_url: '' })
    })

    afterEach(() => {
        vi.useRealTimers()
    })

    it('handleLogin writes user_nickname ONLY after uuid exists (zero orphan nickname on unmount)', async () => {
        const deferredSession = createDeferred<string | null>()
        vi.mocked(ensureValidSession).mockImplementationOnce(() =>
            deferredSession.promise.then((t) => {
                if (t) localStorage.setItem('user_uuid', '55555555-5555-4555-8555-555555555555')
                return t
            })
        )

        const view = render(
            <LanguageProvider>
                <LandingPage />
            </LanguageProvider>
        )

        const nickInput = await screen.findByPlaceholderText('例如：小明')
        fireEvent.change(nickInput, { target: { value: 'UnmountedUser' } })
        fireEvent.click(screen.getByRole('button', { name: /開始旅程/ }))
        expect(localStorage.getItem('user_nickname')).toBeNull()

        view.unmount()
        await act(async () => {
            deferredSession.resolve('jwt-unmounted')
        })
        expect(localStorage.getItem('user_nickname')).toBeNull()
    })

    it('handleRecover (online) clears activeTripId, activeTripTitle, and stale userId in BOTH trip-storage and tabidachi-trip-storage', async () => {
        vi.useFakeTimers()
        seedTripStorage()
        vi.mocked(restoreAccountWithKey).mockResolvedValueOnce({
            accessToken: 'jwt-ok',
            userId: '66666666-6666-4666-8666-666666666666',
            isNew: false,
        })

        const view = render(
            <LanguageProvider>
                <LandingPage />
            </LanguageProvider>
        )

        fireEvent.click(screen.getByRole('button', { name: /使用引繼碼登入/ }))
        const codeInput = screen.getByPlaceholderText(/tbj_rec_xxxxxxxx_/)
        fireEvent.change(codeInput, {
            target: { value: 'tbj_rec_12345678_1234567890abcdef1234567890abcdef' },
        })
        fireEvent.click(screen.getByRole('button', { name: '還原' }))

        await act(async () => {
            await Promise.resolve()
            await Promise.resolve()
        })

        const primary = JSON.parse(localStorage.getItem('trip-storage') || '{}')
        const legacy = JSON.parse(localStorage.getItem('tabidachi-trip-storage') || '{}')
        expect(primary.state.activeTripId).toBeNull()
        expect(primary.state.activeTripTitle).toBeNull()
        expect(primary.state.userId).toBeNull()
        expect(legacy.state.activeTripId).toBeNull()
        expect(legacy.state.activeTripTitle).toBeNull()
        expect(legacy.state.userId).toBeNull()
        view.unmount()
    })

    it('handleRecover (offline) clears activeTripId, activeTripTitle, and stale userId in BOTH trip-storage and tabidachi-trip-storage, clears prior tokens, and dispatches user-login-state-changed', async () => {
        vi.useFakeTimers()
        seedTripStorage()
        localStorage.setItem('tabiji_session_token', 'old-account-jwt')
        localStorage.setItem('tabiji_pop_token', 'old-account-pop')
        localStorage.setItem('user_recovery_key', 'tbj_rec_00000000_00000000000000000000000000000000')
        Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
        vi.mocked(restoreAccountWithKey).mockRejectedValueOnce(new Error('Offline'))

        const onLoginChanged = vi.fn()
        window.addEventListener('user-login-state-changed', onLoginChanged)

        const view = render(
            <LanguageProvider>
                <LandingPage />
            </LanguageProvider>
        )

        try {
            const recoveredCode = 'tbj_rec_12345678_1234567890abcdef1234567890abcdef'
            fireEvent.click(screen.getByRole('button', { name: /使用引繼碼登入/ }))
            const offlineCodeInput = screen.getByPlaceholderText(/tbj_rec_xxxxxxxx_/)
            fireEvent.change(offlineCodeInput, {
                target: { value: recoveredCode },
            })
            fireEvent.click(screen.getByRole('button', { name: '還原' }))

            await act(async () => {
                await Promise.resolve()
                await Promise.resolve()
            })

            const primary = JSON.parse(localStorage.getItem('trip-storage') || '{}')
            const legacy = JSON.parse(localStorage.getItem('tabidachi-trip-storage') || '{}')
            expect(primary.state.activeTripId).toBeNull()
            expect(primary.state.activeTripTitle).toBeNull()
            expect(primary.state.userId).toBeNull()
            expect(legacy.state.activeTripId).toBeNull()
            expect(legacy.state.activeTripTitle).toBeNull()
            expect(legacy.state.userId).toBeNull()
            expect(localStorage.getItem('tabiji_session_token')).toBeNull()
            expect(localStorage.getItem('tabiji_pop_token')).toBeNull()
            expect(localStorage.getItem('user_recovery_key')).toBe(recoveredCode)
            expect(localStorage.getItem('user_uuid')).toBe(recoveredCode)
            expect(onLoginChanged).toHaveBeenCalledTimes(1)
        } finally {
            window.removeEventListener('user-login-state-changed', onLoginChanged)
            view.unmount()
        }
    })

    it('handleRecover (offline) with legacy UUID removes stale user_recovery_key and dispatches user-login-state-changed', async () => {
        vi.useFakeTimers()
        localStorage.setItem('tabiji_session_token', 'old-account-jwt')
        localStorage.setItem('tabiji_pop_token', 'old-account-pop')
        localStorage.setItem('user_recovery_key', 'tbj_rec_00000000_00000000000000000000000000000000')
        Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
        vi.mocked(restoreAccountWithKey).mockRejectedValueOnce(new Error('Offline'))

        const onLoginChanged = vi.fn()
        window.addEventListener('user-login-state-changed', onLoginChanged)

        const view = render(
            <LanguageProvider>
                <LandingPage />
            </LanguageProvider>
        )

        try {
            const legacyUuid = 'AAAAAAAA-BBBB-4CCC-8DDD-EEEEEEEEEEEE'
            fireEvent.click(screen.getByRole('button', { name: /使用引繼碼登入/ }))
            const offlineCodeInput = screen.getByPlaceholderText(/tbj_rec_xxxxxxxx_/)
            fireEvent.change(offlineCodeInput, {
                target: { value: legacyUuid },
            })
            fireEvent.click(screen.getByRole('button', { name: '還原' }))

            await act(async () => {
                await Promise.resolve()
                await Promise.resolve()
            })

            expect(localStorage.getItem('user_recovery_key')).toBeNull()
            expect(localStorage.getItem('user_uuid')).toBe(legacyUuid.toLowerCase())
            expect(localStorage.getItem('tabiji_session_token')).toBeNull()
            expect(localStorage.getItem('tabiji_pop_token')).toBeNull()
            expect(onLoginChanged).toHaveBeenCalledTimes(1)
        } finally {
            window.removeEventListener('user-login-state-changed', onLoginChanged)
            view.unmount()
        }
    })
})
