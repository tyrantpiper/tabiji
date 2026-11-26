import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'

const {
    mockStreamChat,
    mockToastError,
    mockToastInfo,
    mockToastSuccess,
    mockGetCachedToken,
    mockEnsureValidSession,
    mockWasTransientFailure,
} = vi.hoisted(() => ({
    mockStreamChat: vi.fn(),
    mockToastError: vi.fn(),
    mockToastInfo: vi.fn(),
    mockToastSuccess: vi.fn(),
    mockGetCachedToken: vi.fn(() => 'mock-session-jwt'),
    mockEnsureValidSession: vi.fn().mockResolvedValue('mock-session-jwt'),
    mockWasTransientFailure: vi.fn(() => false),
}))

vi.mock('@/lib/sse-parser', async () => {
    const actual = await vi.importActual<typeof import('@/lib/sse-parser')>('@/lib/sse-parser')
    return {
        ...actual,
        streamChat: (...args: unknown[]) => mockStreamChat(...args),
    }
})

vi.mock('@/lib/trip-context', () => ({
    useTripContext: () => ({
        activeTrip: { id: 'trip-1', title: 'Tokyo 5 Days' },
        activeTripId: 'trip-1',
        userId: 'user-1',
    }),
}))

vi.mock('@/lib/stores/tripStore', () => ({
    useFocusedDay: () => 1,
}))

vi.mock('@/lib/hooks', () => ({
    useTripDetail: () => ({
        trip: { id: 'trip-1', title: 'Tokyo 5 Days', items: [] },
    }),
}))

vi.mock('@/lib/polling-manager', () => ({
    useDynamicPolling: () => 0,
}))

vi.mock('@/lib/security', () => ({
    getSecureApiKey: () => 'AIzaSyMockChatWidgetTestKey123456',
}))

vi.mock('@/lib/stores/weatherStore', () => ({
    useWeatherStore: () => ({
        getWeatherData: () => null,
    }),
}))

vi.mock('@/lib/search-cache', () => ({
    setSearchCache: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@/lib/auth-session', () => ({
    getCachedToken: mockGetCachedToken,
    ensureValidSession: mockEnsureValidSession,
    wasLastAuthExchangeTransientFailure: mockWasTransientFailure,
}))

vi.mock('sonner', () => ({
    toast: {
        error: (...args: unknown[]) => mockToastError(...args),
        info: (...args: unknown[]) => mockToastInfo(...args),
        success: (...args: unknown[]) => mockToastSuccess(...args),
    },
}))

import ChatWidget from '@/components/chat-widget'
import { ActuaryDialogCard } from '@/components/ActuaryDialogCard'
import { LanguageProvider } from '@/lib/LanguageContext'
import { ensureValidSession } from '@/lib/auth-session'

describe('ChatWidget & ActuaryDialogCard Remediation RTL Tests', () => {
    const originalFetch = global.fetch

    beforeEach(() => {
        vi.clearAllMocks()
        mockGetCachedToken.mockReturnValue('mock-session-jwt')
        mockEnsureValidSession.mockResolvedValue('mock-session-jwt')
        mockWasTransientFailure.mockReturnValue(false)
        localStorage.setItem('user_uuid', 'user-1')
        localStorage.setItem('user_nickname', 'Ryan')
        Element.prototype.scrollIntoView = vi.fn()
        global.ResizeObserver = class {
            observe = vi.fn()
            unobserve = vi.fn()
            disconnect = vi.fn()
        } as unknown as typeof ResizeObserver
    })

    afterEach(() => {
        global.fetch = originalFetch
        vi.useRealTimers()
        localStorage.clear()
    })

    function renderOpenChatWidget() {
        const view = render(
            <LanguageProvider>
                <ChatWidget />
            </LanguageProvider>
        )
        const toggleBtn = screen.getByRole('button', { name: /Ryan AI/i })
        fireEvent.click(toggleBtn)
        return view
    }

    it('onReset clears partial text and cards from failed primary before fallback output', async () => {
        mockStreamChat.mockImplementationOnce(async (_url, _msg, _hist, _key, handlers) => {
            handlers.onStart?.()
            handlers.onText?.('Broken partial primary text ')
            handlers.onTool?.({ name: 'add_itinerary_item', args: { day: 1, place_name: 'Wrong Primary Place' } })
            handlers.onReset?.({ reason: 'fallback', model: 'gemini-3.5-flash-lite' })
            handlers.onText?.('Clean fallback response from Gemma 4.')
            handlers.onDone?.({
                model_used: 'gemma-4-31b-it',
                raw_parts: [{ text: 'Clean fallback response from Gemma 4.' }],
                sources: [],
            })
        })

        renderOpenChatWidget()

        const textarea = screen.getByRole('textbox')
        fireEvent.change(textarea, { target: { value: 'Recommend Tokyo spots' } })
        fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })

        await waitFor(() => {
            expect(screen.getByText(/Clean fallback response from Gemma 4\./)).toBeInTheDocument()
        })
        expect(screen.queryByText(/Broken partial primary text/)).not.toBeInTheDocument()
        expect(screen.queryByText(/Wrong Primary Place/)).not.toBeInTheDocument()
    })

    it('empty onDone renders explicit error without canned greeting or duplicate /api/chat call', async () => {
        const mockFetch = vi.fn()
        global.fetch = mockFetch as unknown as typeof fetch

        mockStreamChat.mockImplementationOnce(async (_url, _msg, _hist, _key, handlers) => {
            handlers.onStart?.()
            handlers.onDone?.({
                model_used: 'gemini-3.5-flash-lite',
                raw_parts: [],
                sources: [],
            })
        })

        renderOpenChatWidget()

        const textarea = screen.getByRole('textbox')
        fireEvent.change(textarea, { target: { value: 'Test empty done' } })
        fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })

        await waitFor(() => {
            expect(mockToastError).toHaveBeenCalled()
            expect(screen.getByText(/AI 回應為空，請重試|AI returned an empty response/)).toBeInTheDocument()
        })
        expect(screen.queryByText(/收到！有什麼我可以幫忙的嗎？/)).not.toBeInTheDocument()
        expect(screen.queryByText(/I'm here to help!/)).not.toBeInTheDocument()
        expect(mockFetch).not.toHaveBeenCalled()
    })

    it('Deep Research stops polling immediately on 404 and clears active interval on unmount', async () => {
        vi.useFakeTimers({ shouldAdvanceTime: true })

        let pollHits = 0
        global.fetch = vi.fn(async (input: RequestInfo | URL) => {
            const url = String(input)
            if (url.endsWith('/api/agents/research/stream')) {
                return new Response(null, { status: 404 })
            }
            if (url.endsWith('/api/agents/research')) {
                return new Response(
                    JSON.stringify({ interaction_id: 'res_404_1', engine: 'fallback' }),
                    { status: 200, headers: { 'Content-Type': 'application/json' } }
                )
            }
            if (url.includes('/api/agents/interactions/res_404_1')) {
                pollHits += 1
                return new Response(
                    JSON.stringify({ detail: 'Research task not found' }),
                    { status: 404, headers: { 'Content-Type': 'application/json' } }
                )
            }
            return new Response('{}', { status: 200 })
        }) as unknown as typeof fetch

        const view1 = renderOpenChatWidget()
        const textarea1 = screen.getByRole('textbox')
        fireEvent.change(textarea1, { target: { value: '/research Sapporo winter rail pass' } })
        fireEvent.keyDown(textarea1, { key: 'Enter', shiftKey: false })

        await act(async () => {
            await vi.advanceTimersByTimeAsync(2200)
        })
        expect(pollHits).toBe(1)
        expect(mockToastError).toHaveBeenCalledWith('Research task not found')

        await act(async () => {
            await vi.advanceTimersByTimeAsync(6000)
        })
        // 404 must clear interval immediately — no further polls after first 404
        expect(pollHits).toBe(1)
        view1.unmount()

        // Second check: running task unmounts cleanly with zero stray polling timers
        let unmountPollHits = 0
        let startedCount = 0
        global.fetch = vi.fn(async (input: RequestInfo | URL) => {
            const url = String(input)
            if (url.endsWith('/api/agents/research/stream')) {
                return new Response(null, { status: 404 })
            }
            if (url.endsWith('/api/agents/research')) {
                startedCount += 1
                return new Response(
                    JSON.stringify({ interaction_id: 'res_unmount_1', engine: 'fallback' }),
                    { status: 200, headers: { 'Content-Type': 'application/json' } }
                )
            }
            unmountPollHits += 1
            return new Response(
                JSON.stringify({ status: 'running' }),
                { status: 200, headers: { 'Content-Type': 'application/json' } }
            )
        }) as unknown as typeof fetch

        const view2 = renderOpenChatWidget()
        const textarea2 = screen.getByRole('textbox')
        fireEvent.change(textarea2, { target: { value: '/research Hakodate trams' } })
        fireEvent.keyDown(textarea2, { key: 'Enter', shiftKey: false })

        // Immediately unmount while POST /api/agents/research is resolving (tests async post-unmount timer leak guard)
        await waitFor(() => expect(startedCount).toBe(1))
        view2.unmount()

        await act(async () => {
            await vi.advanceTimersByTimeAsync(6500)
        })
        expect(unmountPollHits).toBe(0)

        // Third check: already-active polling interval stops cleanly upon unmount
        let activeIntervalPollHits = 0
        global.fetch = vi.fn(async (input: RequestInfo | URL) => {
            const url = String(input)
            if (url.endsWith('/api/agents/research/stream')) {
                return new Response(null, { status: 404 })
            }
            if (url.endsWith('/api/agents/research')) {
                return new Response(
                    JSON.stringify({ interaction_id: 'res_unmount_active', engine: 'fallback' }),
                    { status: 200, headers: { 'Content-Type': 'application/json' } }
                )
            }
            activeIntervalPollHits += 1
            return new Response(
                JSON.stringify({ status: 'running' }),
                { status: 200, headers: { 'Content-Type': 'application/json' } }
            )
        }) as unknown as typeof fetch

        const view3 = renderOpenChatWidget()
        const textarea3 = screen.getByRole('textbox')
        fireEvent.change(textarea3, { target: { value: '/research Furano lavender route' } })
        fireEvent.keyDown(textarea3, { key: 'Enter', shiftKey: false })

        await act(async () => {
            await vi.advanceTimersByTimeAsync(2200)
        })
        expect(activeIntervalPollHits).toBe(1)

        view3.unmount()

        await act(async () => {
            await vi.advanceTimersByTimeAsync(6500)
        })
        expect(activeIntervalPollHits).toBe(1)
    })

    it('ActuaryDialogCard renders backend FastAPI detail instead of swallowed success or generic message', async () => {
        global.fetch = vi.fn().mockResolvedValueOnce(
            new Response(
                JSON.stringify({ detail: 'Gemini API Key 無效或已過期，請更新金鑰' }),
                { status: 401, headers: { 'Content-Type': 'application/json' } }
            )
        ) as unknown as typeof fetch

        render(
            <LanguageProvider>
                <ActuaryDialogCard
                    open={true}
                    onOpenChange={vi.fn()}
                    expenses={[]}
                    members={[
                        { user_id: 'u1', user_name: 'Ryan' },
                        { user_id: 'u2', user_name: 'Alex' },
                    ]}
                />
            </LanguageProvider>
        )

        await waitFor(() => {
            expect(screen.getByText(/Gemini API Key 無效或已過期，請更新金鑰/)).toBeInTheDocument()
        })
    })

    it('fallback /api/chat calls ensureValidSession(true) on non-Gemini 401, retries with fresh token, and skips refresh on Gemini 401', async () => {
        localStorage.setItem('tabiji_session_token', 'mock-session-jwt')
        mockStreamChat.mockRejectedValueOnce(new Error('stream unavailable'))
        vi.mocked(ensureValidSession).mockResolvedValueOnce('fresh-rotated-jwt')

        const chatAuthHeaders: Array<string | null> = []
        global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
            const url = String(input)
            const hdrs = new Headers(init?.headers)
            if (url.endsWith('/api/chat')) {
                const auth = hdrs.get('Authorization')
                chatAuthHeaders.push(auth)
                if (auth === 'Bearer mock-session-jwt') {
                    return new Response(
                        JSON.stringify({ detail: 'Invalid or expired token' }),
                        { status: 401, headers: { 'Content-Type': 'application/json' } }
                    )
                }
                return new Response(
                    JSON.stringify({
                        response: 'Recovered via forceRefresh fallback',
                        raw_parts: [{ text: 'Recovered via forceRefresh fallback' }],
                    }),
                    { status: 200, headers: { 'Content-Type': 'application/json' } }
                )
            }
            return new Response('{}', { status: 200 })
        }) as unknown as typeof fetch

        const view1 = renderOpenChatWidget()
        const textarea1 = screen.getByRole('textbox')
        fireEvent.change(textarea1, { target: { value: 'Fallback retry test' } })
        fireEvent.keyDown(textarea1, { key: 'Enter', shiftKey: false })

        await waitFor(() => {
            expect(screen.getByText(/Recovered via forceRefresh fallback/)).toBeInTheDocument()
        })
        expect(ensureValidSession).toHaveBeenCalledWith(true)
        expect(chatAuthHeaders).toEqual(['Bearer mock-session-jwt', 'Bearer fresh-rotated-jwt'])
        view1.unmount()

        // Case B: Gemini API Key 401 in fallback must NOT call ensureValidSession(true) or clear tabiji_session_token
        vi.clearAllMocks()
        localStorage.setItem('tabiji_session_token', 'mock-session-jwt')
        mockStreamChat.mockRejectedValueOnce(new Error('stream unavailable'))
        global.fetch = vi.fn(async () => new Response(
            JSON.stringify({ detail: 'Your Google Gemini API Key is invalid' }),
            { status: 401, headers: { 'Content-Type': 'application/json' } }
        )) as unknown as typeof fetch

        const view2 = renderOpenChatWidget()
        const textarea2 = screen.getByRole('textbox')
        fireEvent.change(textarea2, { target: { value: 'Fallback gemini 401 test' } })
        fireEvent.keyDown(textarea2, { key: 'Enter', shiftKey: false })

        await waitFor(() => {
            expect(screen.getByText(/連線中斷|Connection lost/)).toBeInTheDocument()
        })
        expect(ensureValidSession).not.toHaveBeenCalled()
        expect(localStorage.getItem('tabiji_session_token')).toBe('mock-session-jwt')
        view2.unmount()
    })

    it('background /api/chat/summarize boots missing JWT, retries once on non-Gemini 401, and leaves token intact on Gemini 401', async () => {
        // 1. Cold boot token missing -> calls ensureValidSession(), then hits non-Gemini 401 -> calls ensureValidSession(true) and succeeds
        mockGetCachedToken.mockReturnValue(null as unknown as string)
        mockEnsureValidSession
            .mockResolvedValueOnce('initial-jwt')
            .mockResolvedValueOnce('fresh-summary-jwt')
        mockWasTransientFailure.mockReturnValue(false)
        localStorage.setItem('tabiji_session_token', 'initial-jwt')

        mockStreamChat.mockImplementation(async (_url, msg, _hist, _key, handlers) => {
            handlers.onStart?.()
            handlers.onText?.(`Reply to ${msg}`)
            handlers.onDone?.({
                model_used: 'gemini-3.5-flash-lite',
                raw_parts: [{ text: `Reply to ${msg}` }],
                sources: [],
            })
        })

        const summarizeAuthHeaders: Array<string | null> = []
        global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
            const url = String(input)
            const auth = new Headers(init?.headers).get('Authorization')
            if (url.endsWith('/api/chat/summarize')) {
                summarizeAuthHeaders.push(auth)
                if (auth === 'Bearer initial-jwt') {
                    return new Response(JSON.stringify({ detail: 'Invalid or expired token' }), { status: 401 })
                }
                return new Response(JSON.stringify({ summary: 'Tokyo itinerary memory summary' }), { status: 200 })
            }
            return new Response('{}', { status: 200 })
        }) as unknown as typeof fetch

        const view1 = renderOpenChatWidget()
        const textarea1 = screen.getByRole('textbox')
        // 1 greeting + 10 rounds * 2 = 21 messages; on 10th send messages.length is 19, wait -> 11th send has messages.length === 21 (>= PREHEAT_THRESHOLD 20)
        for (let i = 1; i <= 11; i++) {
            fireEvent.change(textarea1, { target: { value: `Turn ${i}` } })
            fireEvent.keyDown(textarea1, { key: 'Enter', shiftKey: false })
            await waitFor(() => {
                expect(screen.getByText(`Reply to Turn ${i}`)).toBeInTheDocument()
            })
        }

        await waitFor(() => {
            expect(summarizeAuthHeaders).toEqual(['Bearer initial-jwt', 'Bearer fresh-summary-jwt'])
        })
        expect(mockEnsureValidSession).toHaveBeenCalledWith()
        expect(mockEnsureValidSession).toHaveBeenCalledWith(true)
        await waitFor(() => {
            expect(mockToastSuccess).toHaveBeenCalled()
        })
        view1.unmount()

        // 2. Gemini API Key 401 on /api/chat/summarize MUST NOT refresh session or wipe tabiji_session_token
        vi.clearAllMocks()
        mockGetCachedToken.mockReturnValue('valid-session-jwt')
        localStorage.setItem('tabiji_session_token', 'valid-session-jwt')
        const geminiAuthHeaders: Array<string | null> = []
        global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
            const url = String(input)
            if (url.endsWith('/api/chat/summarize')) {
                geminiAuthHeaders.push(new Headers(init?.headers).get('Authorization'))
                return new Response(JSON.stringify({ detail: 'Your Google Gemini API Key is invalid' }), { status: 401 })
            }
            return new Response('{}', { status: 200 })
        }) as unknown as typeof fetch

        const view2 = renderOpenChatWidget()
        const textarea2 = screen.getByRole('textbox')
        for (let i = 1; i <= 11; i++) {
            fireEvent.change(textarea2, { target: { value: `GeminiTurn ${i}` } })
            fireEvent.keyDown(textarea2, { key: 'Enter', shiftKey: false })
            await waitFor(() => {
                expect(screen.getByText(`Reply to GeminiTurn ${i}`)).toBeInTheDocument()
            })
        }
        await waitFor(() => {
            expect(geminiAuthHeaders).toEqual(['Bearer valid-session-jwt'])
        })
        expect(mockEnsureValidSession).not.toHaveBeenCalled()
        expect(localStorage.getItem('tabiji_session_token')).toBe('valid-session-jwt')
        view2.unmount()
    })
})
