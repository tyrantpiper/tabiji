import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'

const mockStreamChat = vi.fn()
const mockToastError = vi.fn()
const mockToastInfo = vi.fn()
const mockToastSuccess = vi.fn()

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
    getCachedToken: () => 'mock-session-jwt',
    ensureValidSession: vi.fn().mockResolvedValue('mock-session-jwt'),
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

describe('ChatWidget & ActuaryDialogCard Remediation RTL Tests', () => {
    const originalFetch = global.fetch

    beforeEach(() => {
        vi.clearAllMocks()
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
})
