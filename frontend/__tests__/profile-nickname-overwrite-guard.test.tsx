/**
 * @vitest-environment jsdom
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'

vi.mock('framer-motion', () => ({
    motion: {
        div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
    },
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock('next/image', () => ({
    default: ({ alt }: { alt?: string }) => <span data-testid="mock-next-image" aria-label={alt || ''} />,
}))

vi.mock('sonner', () => ({
    toast: {
        success: vi.fn(),
        error: vi.fn(),
        warning: vi.fn(),
    },
}))

vi.mock('@/lib/auth-session', async () => {
    const actual = await vi.importActual<typeof import('@/lib/auth-session')>('@/lib/auth-session')
    return {
        ...actual,
        fetchLatestRecoveryKey: vi.fn().mockResolvedValue(null),
        rotateAccountRecoveryKey: vi.fn(),
    }
})

vi.mock('@/lib/ThemeContext', async () => {
    const actual = await vi.importActual<typeof import('@/lib/ThemeContext')>('@/lib/ThemeContext')
    return {
        ...actual,
        useTheme: () => ({
            isDark: false,
            toggleDark: vi.fn(),
            accentColor: 'default',
            setAccentColor: vi.fn(),
            currentTheme: actual.ACCENT_COLORS.default,
            fontScale: 100 as const,
            setFontScale: vi.fn(),
        }),
    }
})

vi.mock('@/lib/hooks', () => ({
    useHaptic: () => ({ selection: vi.fn(), impact: vi.fn(), notification: vi.fn() }),
}))

vi.mock('@/lib/hooks/usePushNotifications', () => ({
    usePushNotifications: () => ({
        permissionState: 'default',
        isSubscribed: false,
        subscribe: vi.fn(),
        unsubscribe: vi.fn(),
        isSupported: false,
        isLoading: false,
    }),
}))

vi.mock('@/lib/supabase', () => ({
    getSupabaseClient: () => null,
}))

vi.mock('@/lib/security', () => ({
    getSecureApiKey: () => null,
}))

vi.mock('@/lib/sync-engine', () => ({
    SyncEngineControl: { resume: vi.fn(), pause: vi.fn() },
}))

vi.mock('@/components/ui/image-upload', () => ({
    ImageUpload: ({ icon }: { icon?: React.ReactNode }) => <div>{icon}</div>,
}))

vi.mock('@/components/ui/zoomable-image', () => ({
    ZoomableImage: () => null,
}))

vi.mock('@/components/UsageGuideDialog', () => ({
    UsageGuideDialog: () => null,
}))

vi.mock('@/components/UsageGuideContent', () => ({
    UsageGuideContent: () => null,
}))

vi.mock('@/components/ai/ai-key-dialog', () => ({
    AIKeyDialog: () => null,
}))

vi.mock('@/components/ai/mcp-connector-dialog', () => ({
    MCPConnectorDialog: () => null,
}))

vi.mock('@/lib/api', () => ({
    usersApi: {
        getProfile: vi.fn(),
        getPreferences: vi.fn(),
        updateProfile: vi.fn(),
        deletePreference: vi.fn(),
        deleteUserData: vi.fn(),
    },
    appApi: {
        getDonationProgress: vi.fn(),
    },
}))

import { ProfileView } from '@/components/views/profile-view'
import { LanguageProvider } from '@/lib/LanguageContext'
import { usersApi, appApi } from '@/lib/api'

describe('ProfileView Local Real Nickname Overwrite Guard', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        localStorage.clear()
        Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
        vi.mocked(usersApi.getPreferences).mockResolvedValue([])
        vi.mocked(appApi.getDonationProgress).mockResolvedValue({ available: false } as never)
    })

    afterEach(() => {
        vi.restoreAllMocks()
    })

    it.each(['Traveler', 'New Traveler', 'Unknown Traveler', 'Legacy Traveler'])(
        'does NOT overwrite valid local nickname with backend placeholder %s',
        async (placeholderName) => {
            const uid = 'aaaa1111-1111-4111-8111-111111111111'
            localStorage.setItem('user_uuid', uid)
            localStorage.setItem('user_nickname', 'Alice')

            vi.mocked(usersApi.getProfile).mockResolvedValueOnce({
                id: uid,
                name: placeholderName,
                avatar_url: null,
            })

            const view = render(
                <LanguageProvider>
                    <ProfileView />
                </LanguageProvider>
            )

            await waitFor(() => {
                expect(usersApi.getProfile).toHaveBeenCalledWith(uid)
            })

            // Let microtasks flush and verify BOTH UI and localStorage stay protected
            await waitFor(() => {
                expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Alice')
            })
            expect(localStorage.getItem('user_nickname')).toBe('Alice')
            view.unmount()
        }
    )

    it('DOES sync non-placeholder server name (e.g. multi-device rename) to UI and localStorage', async () => {
        const uid = 'bbbb2222-2222-4222-8222-222222222222'
        localStorage.setItem('user_uuid', uid)
        localStorage.setItem('user_nickname', 'OldName')

        vi.mocked(usersApi.getProfile).mockResolvedValueOnce({
            id: uid,
            name: 'Bob',
            avatar_url: null,
        })

        const view = render(
            <LanguageProvider>
                <ProfileView />
            </LanguageProvider>
        )

        await waitFor(() => {
            expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Bob')
        })
        expect(localStorage.getItem('user_nickname')).toBe('Bob')
        view.unmount()
    })

    it('allows backend Traveler when localStorage has no real nickname', async () => {
        const uid = 'cccc3333-3333-4333-8333-333333333333'
        localStorage.setItem('user_uuid', uid)

        vi.mocked(usersApi.getProfile).mockResolvedValueOnce({
            id: uid,
            name: 'Traveler',
            avatar_url: null,
        })

        const view = render(
            <LanguageProvider>
                <ProfileView />
            </LanguageProvider>
        )

        await waitFor(() => {
            expect(usersApi.getProfile).toHaveBeenCalledWith(uid)
        })
        expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Traveler')
        expect(localStorage.getItem('user_nickname')).toBe('Traveler')
        view.unmount()
    })

    it('still syncs avatar_url while blocking backend Traveler placeholder from overwriting local real name', async () => {
        const uid = 'aaaa1111-1111-4111-8111-111111111111'
        localStorage.setItem('user_uuid', uid)
        localStorage.setItem('user_nickname', '海獺')

        vi.mocked(usersApi.getProfile).mockResolvedValueOnce({
            id: uid,
            name: 'Traveler',
            avatar_url: 'https://example.com/otter.png',
        })

        const view = render(
            <LanguageProvider>
                <ProfileView />
            </LanguageProvider>
        )

        await waitFor(() => {
            expect(localStorage.getItem('user_avatar')).toBe('https://example.com/otter.png')
        })
        expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('海獺')
        expect(localStorage.getItem('user_nickname')).toBe('海獺')
        view.unmount()
    })

    it('blocks backend Unicode/invisible-padded placeholder from overwriting local real name AND blocks literal null/undefined/invisible when local is empty', async () => {
        const uid = 'aaaa1111-1111-4111-8111-111111111111'
        localStorage.setItem('user_uuid', uid)
        localStorage.setItem('user_nickname', '海獺')

        vi.mocked(usersApi.getProfile).mockResolvedValueOnce({
            id: uid,
            name: 'New\u3000Traveler\u200b',
            avatar_url: null,
        })

        const view1 = render(
            <LanguageProvider>
                <ProfileView />
            </LanguageProvider>
        )
        await waitFor(() => {
            expect(usersApi.getProfile).toHaveBeenCalledTimes(1)
        })
        expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('海獺')
        expect(localStorage.getItem('user_nickname')).toBe('海獺')
        view1.unmount()

        // Empty localStorage + literal 'undefined' / invisible '\u200b' from backend -> NEVER persist
        localStorage.clear()
        localStorage.setItem('user_uuid', uid)
        vi.mocked(usersApi.getProfile).mockResolvedValueOnce({
            id: uid,
            name: 'undefined',
            avatar_url: null,
        })

        const view2 = render(
            <LanguageProvider>
                <ProfileView />
            </LanguageProvider>
        )
        await waitFor(() => {
            expect(usersApi.getProfile).toHaveBeenCalledTimes(2)
        })
        expect(localStorage.getItem('user_nickname')).toBeNull()
        expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Traveler')
        view2.unmount()
    })

    it('does NOT clobber active unsaved edit draft when slow getProfile resolves during isEditing, and Cancel restores saved nickname', async () => {
        const uid = 'bbbb2222-2222-4222-8222-222222222222'
        localStorage.setItem('user_uuid', uid)
        localStorage.setItem('user_nickname', 'OldName')

        let resolveProfile!: (val: { id: string; name: string; avatar_url: null }) => void
        vi.mocked(usersApi.getProfile).mockImplementationOnce(
            () => new Promise((res) => { resolveProfile = res })
        )

        const view = render(
            <LanguageProvider>
                <ProfileView />
            </LanguageProvider>
        )

        // Enter edit mode and type a draft BEFORE slow getProfile resolves
        const editBtn = await screen.findByTitle('編輯個人檔案')
        fireEvent.click(editBtn)
        const input = screen.getByPlaceholderText('Enter nickname')
        fireEvent.change(input, { target: { value: 'Ryan Draft' } })

        await act(async () => {
            resolveProfile({ id: uid, name: 'RemoteStaleName', avatar_url: null })
            await Promise.resolve()
        })

        // Unsaved draft remains intact while editing; localStorage NOT overwritten
        expect(screen.getByPlaceholderText('Enter nickname')).toHaveValue('Ryan Draft')
        expect(localStorage.getItem('user_nickname')).toBe('OldName')

        // Clicking Cancel restores the saved local nickname cleanly
        fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
        expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('OldName')
        view.unmount()
    })

    it('discards stale in-flight getProfile that resolves AFTER handleSaveProfile succeeds', async () => {
        const uid = 'bbbb2222-2222-4222-8222-222222222222'
        localStorage.setItem('user_uuid', uid)
        localStorage.setItem('user_nickname', 'OldName')

        let resolveSlowGet!: (val: { id: string; name: string; avatar_url: null }) => void
        vi.mocked(usersApi.getProfile).mockImplementationOnce(
            () => new Promise((res) => { resolveSlowGet = res })
        )
        vi.mocked(usersApi.updateProfile).mockResolvedValueOnce({ status: 'success' })

        const view = render(
            <LanguageProvider>
                <ProfileView />
            </LanguageProvider>
        )

        const editBtn = await screen.findByTitle('編輯個人檔案')
        fireEvent.click(editBtn)
        fireEvent.change(screen.getByPlaceholderText('Enter nickname'), { target: { value: '  Bob  ' } })
        fireEvent.click(screen.getByRole('button', { name: /Save/ }))

        await waitFor(() => {
            expect(usersApi.updateProfile).toHaveBeenCalledWith(uid, { name: 'Bob' })
        })
        expect(localStorage.getItem('user_nickname')).toBe('Bob')

        // Now the stale initial GET finally resolves with 'OldName' -> MUST be ignored!
        await act(async () => {
            resolveSlowGet({ id: uid, name: 'OldName', avatar_url: null })
            await Promise.resolve()
        })

        expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Bob')
        expect(localStorage.getItem('user_nickname')).toBe('Bob')
        view.unmount()
    })

    it('handleSaveProfile rejects invisible-only & literal null/undefined inputs and sanitizes fullwidth/Bidi/over-length emoji names', async () => {
        const uid = 'dddd4444-4444-4444-8444-444444444444'
        localStorage.setItem('user_uuid', uid)
        localStorage.setItem('user_nickname', 'OriginalName')
        vi.mocked(usersApi.getProfile).mockResolvedValueOnce({ id: uid, name: 'OriginalName', avatar_url: null })
        vi.mocked(usersApi.updateProfile).mockResolvedValue({ status: 'success' })

        const view = render(
            <LanguageProvider>
                <ProfileView />
            </LanguageProvider>
        )

        const editBtn = await screen.findByTitle('編輯個人檔案')
        fireEvent.click(editBtn)

        for (const bad of ['\u200b', '\ufeff\u200d\ufe0f', 'null', '  undefined  ']) {
            fireEvent.change(screen.getByPlaceholderText('Enter nickname'), { target: { value: bad } })
            fireEvent.click(screen.getByRole('button', { name: /Save/ }))
            expect(usersApi.updateProfile).not.toHaveBeenCalled()
            expect(localStorage.getItem('user_nickname')).toBe('OriginalName')
        }

        // Valid Unicode input with internal fullwidth space, Bidi override, and >64 grapheme boundary
        const messy = '\u202e\u3000測試\u3000🇹🇼👨‍💻\u200b\u3000'
        fireEvent.change(screen.getByPlaceholderText('Enter nickname'), { target: { value: messy } })
        fireEvent.click(screen.getByRole('button', { name: /Save/ }))

        await waitFor(() => {
            expect(usersApi.updateProfile).toHaveBeenCalledWith(uid, { name: '測試 🇹🇼👨‍💻' })
        })
        expect(localStorage.getItem('user_nickname')).toBe('測試 🇹🇼👨‍💻')
        expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('測試 🇹🇼👨‍💻')
        view.unmount()
    })

    it('ignores late getProfile resolution after unmount or account switch (no stale localStorage write)', async () => {
        const uidA = '11111111-1111-4111-8111-111111111111'
        const uidB = '22222222-2222-4222-8222-222222222222'
        localStorage.setItem('user_uuid', uidA)
        localStorage.setItem('user_nickname', 'Alice')

        let resolveFirst!: (val: { id: string; name: string; avatar_url: null }) => void
        vi.mocked(usersApi.getProfile).mockImplementationOnce(
            () => new Promise((res) => { resolveFirst = res })
        )

        const view = render(
            <LanguageProvider>
                <ProfileView />
            </LanguageProvider>
        )
        await waitFor(() => {
            expect(usersApi.getProfile).toHaveBeenCalledWith(uidA)
        })

        // Unmount BEFORE getProfile resolves, then resolve -> localStorage stays untouched
        view.unmount()
        await act(async () => {
            resolveFirst({ id: uidA, name: 'StaleUnmountedName', avatar_url: null })
            await Promise.resolve()
        })
        expect(localStorage.getItem('user_nickname')).toBe('Alice')

        // Cross-account switch while mounted: user_uuid changed from uidA -> uidB before uidA resolves
        let resolveSwitch!: (val: { id: string; name: string; avatar_url: null }) => void
        vi.mocked(usersApi.getProfile).mockImplementationOnce(
            () => new Promise((res) => { resolveSwitch = res })
        )
        const view2 = render(
            <LanguageProvider>
                <ProfileView />
            </LanguageProvider>
        )
        await waitFor(() => {
            expect(usersApi.getProfile).toHaveBeenCalledTimes(2)
        })
        localStorage.setItem('user_uuid', uidB)
        localStorage.setItem('user_nickname', 'Bob')

        await act(async () => {
            resolveSwitch({ id: uidA, name: 'WrongAccountName', avatar_url: null })
            await Promise.resolve()
        })
        expect(localStorage.getItem('user_nickname')).toBe('Bob')
        view2.unmount()
    })
})
