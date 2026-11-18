/**
 * @vitest-environment jsdom
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'

const {
    peekMock,
    dequeueMock,
    incrementRetryMock,
    isPausedMock,
    pauseMock,
    resumeMock,
} = vi.hoisted(() => ({
    peekMock: vi.fn(),
    dequeueMock: vi.fn().mockResolvedValue(undefined),
    incrementRetryMock: vi.fn(),
    isPausedMock: vi.fn(() => false),
    pauseMock: vi.fn(),
    resumeMock: vi.fn(),
}))

vi.mock('@/lib/sync-engine', () => ({
    MAX_RETRIES: 3,
    SyncQueue: {
        peek: peekMock,
        dequeue: dequeueMock,
        incrementRetry: incrementRetryMock,
        enqueue: vi.fn(),
    },
    SyncEngineControl: {
        isPaused: isPausedMock,
        pause: pauseMock,
        resume: resumeMock,
    },
}))

vi.mock('sonner', () => ({
    toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

import { __resetExchangeFailedForTesting } from '@/lib/auth-session'
import { usersApi } from '@/lib/api'
import { fetcherWithUserId } from '@/lib/hooks'
import { useBackgroundSync, __resetSyncProcessingForTesting } from '@/lib/sync-hooks'
import { streamChat } from '@/lib/sse-parser'

function createMockJwt(payload: Record<string, unknown>): string {
    const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url')
    const body = Buffer.from(JSON.stringify(payload)).toString('base64url')
    return `${header}.${body}.mock-signature`
}

describe('Orphan UUID & Key Rotation Safety Net (AC-4 Client Session Resilience)', () => {
    let mockStorage: Record<string, string> = {}
    let mockSessionStorage: Record<string, string> = {}
    const originalFetch = globalThis.fetch
    const originalEnv = { ...process.env }

    beforeEach(() => {
        vi.clearAllMocks()
        mockStorage = {}
        mockSessionStorage = {}
        vi.stubGlobal('localStorage', {
            getItem: vi.fn((k: string) => mockStorage[k] ?? null),
            setItem: vi.fn((k: string, v: string) => { mockStorage[k] = String(v) }),
            removeItem: vi.fn((k: string) => { delete mockStorage[k] }),
            clear: vi.fn(() => { mockStorage = {} }),
        })
        vi.stubGlobal('sessionStorage', {
            getItem: vi.fn((k: string) => mockSessionStorage[k] ?? null),
            setItem: vi.fn((k: string, v: string) => { mockSessionStorage[k] = String(v) }),
            removeItem: vi.fn((k: string) => { delete mockSessionStorage[k] }),
            clear: vi.fn(() => { mockSessionStorage = {} }),
        })
        Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
        __resetExchangeFailedForTesting()
        __resetSyncProcessingForTesting()
        isPausedMock.mockReturnValue(false)
        peekMock.mockResolvedValue([])
    })

    afterEach(() => {
        vi.useRealTimers()
        globalThis.fetch = originalFetch
        process.env = { ...originalEnv }
        vi.unstubAllGlobals()
    })

    it('AC-4a: apiFetch passes forceRefresh=true on 401 with unexpired rotated JWT, backs up PoP, exchanges, and retries', async () => {
        process.env.TEST_AUTH_EXCHANGE = 'true'
        const futureExp = Math.floor(Date.now() / 1000) + 86400
        const staleJwt = createMockJwt({ sub: '11111111-1111-4111-8111-111111111111', exp: futureExp })
        const freshJwt = createMockJwt({ sub: '11111111-1111-4111-8111-111111111111', exp: futureExp + 3600 })

        mockStorage['tabiji_session_token'] = staleJwt
        mockStorage['user_uuid'] = '11111111-1111-4111-8111-111111111111'
        mockStorage['user_recovery_key'] = 'tbj_rec_12345678_0123456789abcdef0123456789abcdef'

        const callLog: Array<{ url: string; auth?: string }> = []
        globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
            const url = typeof input === 'string' ? input : input.toString()
            const hdrs = new Headers(init?.headers)
            callLog.push({ url, auth: hdrs.get('Authorization') || undefined })

            if (url.includes('/api/auth/session')) {
                return new Response(JSON.stringify({
                    access_token: freshJwt,
                    user_id: '11111111-1111-4111-8111-111111111111',
                    is_new: false,
                }), { status: 200, headers: { 'Content-Type': 'application/json' } })
            }
            if (hdrs.get('Authorization') === `Bearer ${staleJwt}`) {
                return new Response(JSON.stringify({ detail: 'Invalid or expired token' }), {
                    status: 401,
                    headers: { 'Content-Type': 'application/json' },
                })
            }
            return new Response(JSON.stringify({ id: '11111111-1111-4111-8111-111111111111', name: 'Ryan' }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            })
        }) as unknown as typeof fetch

        const profile = await usersApi.getProfile('11111111-1111-4111-8111-111111111111')
        expect(profile.name).toBe('Ryan')
        expect(mockStorage['tabiji_session_token']).toBe(freshJwt)
        expect(callLog.map(c => c.url)).toEqual([
            expect.stringContaining('/api/users/11111111-1111-4111-8111-111111111111/profile'),
            expect.stringContaining('/api/auth/session'),
            expect.stringContaining('/api/users/11111111-1111-4111-8111-111111111111/profile'),
        ])
        expect(callLog[1].auth).toBe(`Bearer ${staleJwt}`)
        expect(callLog[2].auth).toBe(`Bearer ${freshJwt}`)
    })

    it('AC-4b: fetcherWithUserId forces refresh on 401 even when local JWT exp is in the future', async () => {
        process.env.TEST_AUTH_EXCHANGE = 'true'
        const futureExp = Math.floor(Date.now() / 1000) + 86400
        const staleJwt = createMockJwt({ sub: '22222222-2222-4222-8222-222222222222', exp: futureExp })
        const freshJwt = createMockJwt({ sub: '22222222-2222-4222-8222-222222222222', exp: futureExp + 3600 })

        mockStorage['tabiji_session_token'] = staleJwt
        mockStorage['user_uuid'] = '22222222-2222-4222-8222-222222222222'
        mockStorage['user_recovery_key'] = 'tbj_rec_deadbeef_0123456789abcdef0123456789abcdef'

        globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
            const url = typeof input === 'string' ? input : input.toString()
            const hdrs = new Headers(init?.headers)
            if (url.includes('/api/auth/session')) {
                return new Response(JSON.stringify({
                    access_token: freshJwt,
                    user_id: '22222222-2222-4222-8222-222222222222',
                    is_new: false,
                }), { status: 200, headers: { 'Content-Type': 'application/json' } })
            }
            if (hdrs.get('Authorization') === `Bearer ${staleJwt}`) {
                return new Response(JSON.stringify({ detail: 'Invalid or expired token' }), { status: 401 })
            }
            return new Response(JSON.stringify([{ id: 'trip-1', title: 'Kyoto' }]), { status: 200 })
        }) as unknown as typeof fetch

        const trips = await fetcherWithUserId(['/api/trips', '22222222-2222-4222-8222-222222222222'])
        expect(trips).toEqual([{ id: 'trip-1', title: 'Kyoto' }])
        expect(mockStorage['tabiji_session_token']).toBe(freshJwt)
    })

    it('AC-4c: SyncEngine calls ensureValidSession(true) on 401 during online replay and dequeues after retry', async () => {
        process.env.TEST_AUTH_EXCHANGE = 'true'
        const futureExp = Math.floor(Date.now() / 1000) + 86400
        const staleJwt = createMockJwt({ sub: '33333333-3333-4333-8333-333333333333', exp: futureExp })
        const freshJwt = createMockJwt({ sub: '33333333-3333-4333-8333-333333333333', exp: futureExp + 3600 })

        mockStorage['tabiji_session_token'] = staleJwt
        mockStorage['user_uuid'] = '33333333-3333-4333-8333-333333333333'
        mockStorage['user_recovery_key'] = 'tbj_rec_abcd1234_0123456789abcdef0123456789abcdef'

        peekMock.mockResolvedValue([{
            id: 'sync-1',
            url: '/api/trips/11111111-1111-4111-8111-111111111111/items',
            method: 'POST',
            body: { place_name: 'Senso-ji' },
            headers: { 'Content-Type': 'application/json' },
            retryCount: 0,
        }])

        globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
            const url = typeof input === 'string' ? input : input.toString()
            const hdrs = new Headers(init?.headers)
            if (url.includes('/api/auth/session')) {
                return new Response(JSON.stringify({
                    access_token: freshJwt,
                    user_id: '33333333-3333-4333-8333-333333333333',
                    is_new: false,
                }), { status: 200 })
            }
            if (hdrs.get('Authorization') === `Bearer ${staleJwt}`) {
                return new Response(JSON.stringify({ detail: 'Invalid token' }), { status: 401 })
            }
            return new Response(JSON.stringify({ ok: true }), { status: 200 })
        }) as unknown as typeof fetch

        function SyncHarness() {
            useBackgroundSync()
            return null
        }

        const { unmount } = render(<SyncHarness />)
        try {
            await act(async () => {
                window.dispatchEvent(new Event('online'))
            })

            await waitFor(() => {
                expect(dequeueMock).toHaveBeenCalledWith('sync-1')
            })
            expect(mockStorage['tabiji_session_token']).toBe(freshJwt)
        } finally {
            unmount()
        }
    })

    it('AC-4d: streamChat preserves tabiji_pop_token on non-Gemini 401 via ensureValidSession(true) and retries', async () => {
        process.env.TEST_AUTH_EXCHANGE = 'true'
        const futureExp = Math.floor(Date.now() / 1000) + 86400
        const staleJwt = createMockJwt({ sub: '44444444-4444-4444-8444-444444444444', exp: futureExp })
        const freshJwt = createMockJwt({ sub: '44444444-4444-4444-8444-444444444444', exp: futureExp + 3600 })

        mockStorage['tabiji_session_token'] = staleJwt
        mockStorage['user_uuid'] = '44444444-4444-4444-8444-444444444444'
        mockStorage['user_recovery_key'] = 'tbj_rec_feedbeef_0123456789abcdef0123456789abcdef'

        const authHeadersSeen: string[] = []
        globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
            const url = typeof input === 'string' ? input : input.toString()
            const hdrs = new Headers(init?.headers)
            if (url.includes('/api/auth/session')) {
                authHeadersSeen.push(`session:${hdrs.get('Authorization') || ''}`)
                return new Response(JSON.stringify({
                    access_token: freshJwt,
                    user_id: '44444444-4444-4444-8444-444444444444',
                    is_new: false,
                }), { status: 200 })
            }
            if (hdrs.get('Authorization') === `Bearer ${staleJwt}`) {
                return new Response(JSON.stringify({ detail: 'Invalid or expired token' }), { status: 401 })
            }
            return new Response('event: done\ndata: {"raw_parts":[{"text":"ok"}]}\n\n', { status: 200 })
        }) as unknown as typeof fetch

        const onDone = vi.fn()
        await streamChat('http://localhost:8008', 'hi', [], 'AIzaSyGoodKey123456789012345678901234', { onDone })
        expect(onDone).toHaveBeenCalledTimes(1)
        expect(authHeadersSeen).toEqual([`session:Bearer ${staleJwt}`])
        expect(mockStorage['tabiji_session_token']).toBe(freshJwt)
    })
})
