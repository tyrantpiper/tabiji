/**
 * @vitest-environment jsdom
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, act } from '@testing-library/react'

interface MockChannelRecord {
    name: string
    on: ReturnType<typeof vi.fn>
    subscribe: ReturnType<typeof vi.fn>
    broadcastHandlers: Record<string, () => void>
}

const {
    createdChannels,
    mockChannel,
    mockRemoveChannel,
    mockGetSupabaseClient,
    mockFetchLatestRecoveryKey,
    mockInitSessionLifecycleListener,
} = vi.hoisted(() => {
    const createdChannels: MockChannelRecord[] = []
    const mockChannel = vi.fn((name: string) => {
        const broadcastHandlers: Record<string, () => void> = {}
        const rec: MockChannelRecord = {
            name,
            broadcastHandlers,
            on: vi.fn((_type: string, filter: { event?: string }, cb: () => void) => {
                if (filter?.event) {
                    broadcastHandlers[filter.event] = cb
                }
                return rec
            }),
            subscribe: vi.fn(() => rec),
        }
        createdChannels.push(rec)
        return rec
    })
    const mockRemoveChannel = vi.fn()
    const mockClient = {
        channel: mockChannel,
        removeChannel: mockRemoveChannel,
    }
    return {
        createdChannels,
        mockChannel,
        mockRemoveChannel,
        mockGetSupabaseClient: vi.fn(() => mockClient),
        mockFetchLatestRecoveryKey: vi.fn().mockResolvedValue(null),
        mockInitSessionLifecycleListener: vi.fn(() => vi.fn()),
    }
})

vi.mock('next/navigation', () => ({
    usePathname: () => '/',
}))

vi.mock('next/dynamic', () => ({
    default: () => {
        const MockChat = () => null
        MockChat.displayName = 'MockChat'
        return MockChat
    },
}))

vi.mock('@/components/auth/session-reauth-modal', () => ({
    SessionReauthModal: () => null,
}))

vi.mock('@/lib/LanguageContext', () => ({
    useLanguage: () => ({ lang: 'zh', setLanguage: vi.fn() }),
}))

vi.mock('sonner', () => ({
    toast: { info: vi.fn(), error: vi.fn(), warning: vi.fn(), success: vi.fn() },
}))

vi.mock('@/lib/supabase', () => ({
    getSupabaseClient: mockGetSupabaseClient,
}))

vi.mock('@/lib/auth-session', () => ({
    initSessionLifecycleListener: mockInitSessionLifecycleListener,
    fetchLatestRecoveryKey: mockFetchLatestRecoveryKey,
    isUserLoggedIn: vi.fn(() => Boolean(localStorage.getItem('user_nickname') && localStorage.getItem('user_uuid'))),
}))

import { AppClientLayer } from '@/components/app-client-layer'

describe('AppClientLayer Realtime Channel Dynamic Bind & Rebind', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        createdChannels.length = 0
        localStorage.clear()
    })

    afterEach(() => {
        localStorage.clear()
    })

    it('binds dynamically on post-mount login, skips redundant rebind for same UUID, rebinds cleanly on recovery without leaking, and unmounts cleanly', () => {
        const { unmount } = render(<AppClientLayer />)

        // 1. Unauthenticated mount: zero Supabase channel subscriptions
        expect(mockGetSupabaseClient).not.toHaveBeenCalled()
        expect(mockChannel).not.toHaveBeenCalled()

        // 2. Sentinel strings "null" / "undefined" and temporary offline tbj_rec_* placeholders must not leak into Realtime channels
        localStorage.setItem('user_uuid', 'null')
        act(() => {
            window.dispatchEvent(new CustomEvent('user-login-state-changed'))
        })
        expect(mockChannel).not.toHaveBeenCalled()

        localStorage.setItem('user_uuid', 'tbj_rec_12345678_1234567890abcdef1234567890abcdef')
        act(() => {
            window.dispatchEvent(new CustomEvent('user-login-state-changed'))
        })
        expect(mockChannel).not.toHaveBeenCalled()

        // 3. Login sets user_uuid and dispatches user-login-state-changed -> binds user-sync:${uuidA}
        const uuidA = '11111111-1111-4111-8111-111111111111'
        localStorage.setItem('user_uuid', uuidA)
        act(() => {
            window.dispatchEvent(new CustomEvent('user-login-state-changed'))
        })

        expect(mockChannel).toHaveBeenCalledTimes(1)
        expect(mockChannel).toHaveBeenLastCalledWith(`user-sync:${uuidA}`)
        expect(createdChannels[0].subscribe).toHaveBeenCalledTimes(1)
        expect(mockRemoveChannel).not.toHaveBeenCalled()

        // Broadcast handler works on the dynamically bound channel
        createdChannels[0].broadcastHandlers['CREDENTIAL_ROTATED']?.()
        expect(mockFetchLatestRecoveryKey).toHaveBeenCalledTimes(1)

        // 4. Redundant user-login-state-changed with same UUID (e.g. WelcomeWizard completion) does not churn channel
        act(() => {
            window.dispatchEvent(new CustomEvent('user-login-state-changed'))
        })
        expect(mockChannel).toHaveBeenCalledTimes(1)
        expect(mockRemoveChannel).not.toHaveBeenCalled()

        // 5. Account recovery switches user_uuid -> cleans up old channelA BEFORE/when binding channelB
        const uuidB = '22222222-2222-4222-8222-222222222222'
        localStorage.setItem('user_uuid', uuidB)
        act(() => {
            window.dispatchEvent(new CustomEvent('user-login-state-changed'))
        })

        expect(mockRemoveChannel).toHaveBeenCalledTimes(1)
        expect(mockRemoveChannel).toHaveBeenNthCalledWith(1, createdChannels[0])
        expect(mockChannel).toHaveBeenCalledTimes(2)
        expect(mockChannel).toHaveBeenLastCalledWith(`user-sync:${uuidB}`)
        expect(createdChannels[1].subscribe).toHaveBeenCalledTimes(1)

        // 6. Clearing identity removes active channel and binds nothing new
        localStorage.removeItem('user_uuid')
        act(() => {
            window.dispatchEvent(new CustomEvent('user-login-state-changed'))
        })
        expect(mockRemoveChannel).toHaveBeenCalledTimes(2)
        expect(mockRemoveChannel).toHaveBeenNthCalledWith(2, createdChannels[1])
        expect(mockChannel).toHaveBeenCalledTimes(2)

        // 7. Re-login after clear binds channelC and unmount cleans it up with zero leaks
        const uuidC = '33333333-3333-4333-8333-333333333333'
        localStorage.setItem('user_uuid', uuidC)
        act(() => {
            window.dispatchEvent(new CustomEvent('user-login-state-changed'))
        })
        expect(mockChannel).toHaveBeenCalledTimes(3)
        expect(mockChannel).toHaveBeenLastCalledWith(`user-sync:${uuidC}`)

        unmount()
        expect(mockRemoveChannel).toHaveBeenCalledTimes(3)
        expect(mockRemoveChannel).toHaveBeenNthCalledWith(3, createdChannels[2])

        // Post-unmount dispatch must not re-subscribe
        localStorage.setItem('user_uuid', '44444444-4444-4444-8444-444444444444')
        act(() => {
            window.dispatchEvent(new CustomEvent('user-login-state-changed'))
        })
        expect(mockChannel).toHaveBeenCalledTimes(3)
    })

    it('subscribes immediately on mount when user_uuid already exists and reacts to storage changes', () => {
        const uuidMount = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        localStorage.setItem('user_uuid', uuidMount)

        const { unmount } = render(<AppClientLayer />)

        expect(mockChannel).toHaveBeenCalledTimes(1)
        expect(mockChannel).toHaveBeenLastCalledWith(`user-sync:${uuidMount}`)

        // Cross-tab storage update switches channel cleanly
        const uuidCrossTab = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
        localStorage.setItem('user_uuid', uuidCrossTab)
        act(() => {
            window.dispatchEvent(new StorageEvent('storage', { key: 'user_uuid', newValue: uuidCrossTab }))
        })

        expect(mockRemoveChannel).toHaveBeenCalledTimes(1)
        expect(mockRemoveChannel).toHaveBeenCalledWith(createdChannels[0])
        expect(mockChannel).toHaveBeenCalledTimes(2)
        expect(mockChannel).toHaveBeenLastCalledWith(`user-sync:${uuidCrossTab}`)

        unmount()
        expect(mockRemoveChannel).toHaveBeenCalledTimes(2)
        expect(mockRemoveChannel).toHaveBeenNthCalledWith(2, createdChannels[1])
    })
})
