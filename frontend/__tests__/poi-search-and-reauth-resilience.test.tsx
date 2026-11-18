import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { SWRConfig } from 'swr'

const {
    mockReanchorSessionWithKey,
    mockResetAndStartFreshSession,
    mockDismissReauthPrompt,
    mockIsUserLoggedIn,
    mockPoiNearby,
    mockPoiRecommend,
    mockSyncPeek,
} = vi.hoisted(() => ({
    mockReanchorSessionWithKey: vi.fn(),
    mockResetAndStartFreshSession: vi.fn(),
    mockDismissReauthPrompt: vi.fn(),
    mockIsUserLoggedIn: vi.fn(() => true),
    mockPoiNearby: vi.fn(),
    mockPoiRecommend: vi.fn(),
    mockSyncPeek: vi.fn().mockResolvedValue([]),
}))

vi.mock('@/lib/auth-session', async () => {
    const actual = await vi.importActual<typeof import('@/lib/auth-session')>('@/lib/auth-session')
    return {
        ...actual,
        reanchorSessionWithKey: (...args: unknown[]) => mockReanchorSessionWithKey(...args),
        resetAndStartFreshSession: (...args: unknown[]) => mockResetAndStartFreshSession(...args),
        dismissReauthPrompt: (...args: unknown[]) => mockDismissReauthPrompt(...args),
        isUserLoggedIn: () => mockIsUserLoggedIn(),
    }
})

vi.mock('@/lib/api', async () => {
    const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
    return {
        ...actual,
        poiApi: {
            ...actual.poiApi,
            nearby: (...args: unknown[]) => mockPoiNearby(...args),
            recommend: (...args: unknown[]) => mockPoiRecommend(...args),
        },
    }
})

vi.mock('@/lib/sync-engine', () => ({
    MAX_RETRIES: 3,
    SyncQueue: {
        peek: (...args: unknown[]) => mockSyncPeek(...args),
        enqueue: vi.fn(),
        dequeue: vi.fn(),
    },
    SyncEngineControl: {
        isPaused: () => false,
        pause: vi.fn(),
        resume: vi.fn(),
    },
}))

vi.mock('sonner', () => ({
    toast: {
        success: vi.fn(),
        error: vi.fn(),
        info: vi.fn(),
        loading: vi.fn(),
    },
}))

import { SessionReauthModal, formatReauthReason } from '@/components/auth/session-reauth-modal'
import { POISearch } from '@/components/poi-search'
import { LanguageProvider } from '@/lib/LanguageContext'
import { useExpenses, useTripCapsules, useTripDetail, __resetTripDetailMutateMapForTesting } from '@/lib/hooks'
import { useBackgroundSync, __resetSyncProcessingForTesting } from '@/lib/sync-hooks'

describe('Cross-Origin Reauth Restoration, SWR 401 Guards & Resilient POISearch', () => {
    const originalFetch = globalThis.fetch

    beforeEach(() => {
        vi.clearAllMocks()
        __resetTripDetailMutateMapForTesting()
        __resetSyncProcessingForTesting()
        mockIsUserLoggedIn.mockReturnValue(true)
        localStorage.setItem('user_uuid', '3f7abf22-b447-4281-b240-584549c79943')
        localStorage.setItem('user_nickname', 'Ryan')
        localStorage.setItem('tabidachi_lang', 'zh')
        Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    })

    afterEach(() => {
        globalThis.fetch = originalFetch
        localStorage.clear()
        vi.restoreAllMocks()
    })

    it('SessionReauthModal localizes upgrade/rotation reasons and triggers SWR revalidation + refresh on restore', async () => {
        const localizedUpgrade = formatReauthReason('Account already upgraded. Please use your modern recovery key (tbj_rec_*).', true)
        expect(localizedUpgrade).toContain('tabijiapp.com')
        expect(localizedUpgrade).toContain('vercel.app')
        expect(localizedUpgrade).toContain('tbj_rec_*')

        const validKey = 'tbj_rec_12345678_0123456789abcdef0123456789abcdef'
        mockReanchorSessionWithKey.mockResolvedValueOnce('fresh-jwt-token')

        let refreshEvents = 0
        const onRefresh = () => { refreshEvents += 1 }
        window.addEventListener('tabidachi-trigger-refresh', onRefresh)

        let expensesFetchCount = 0
        const TestHarness = () => {
            useExpenses('trip-123', '3f7abf22-b447-4281-b240-584549c79943')
            return <SessionReauthModal />
        }

        globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
            const url = String(input)
            if (url.includes('/expenses')) {
                expensesFetchCount += 1
                if (expensesFetchCount === 1) {
                    return new Response(JSON.stringify({ detail: 'Unauthorized' }), { status: 401 })
                }
                return new Response(JSON.stringify([]), { status: 200 })
            }
            return new Response('{}', { status: 200 })
        }) as unknown as typeof fetch

        try {
            render(
                <SWRConfig value={{ provider: () => new Map() }}>
                    <LanguageProvider>
                        <TestHarness />
                    </LanguageProvider>
                </SWRConfig>
            )

            await waitFor(() => expect(expensesFetchCount).toBe(1))

            act(() => {
                window.dispatchEvent(new CustomEvent('tabiji:session_reauth_required', {
                    detail: { reason: 'Account already upgraded. Please use your modern recovery key (tbj_rec_*).' }
                }))
            })

            expect(await screen.findByText(/瀏覽器跨網域儲存空間互相獨立/)).toBeInTheDocument()

            const input = screen.getByPlaceholderText('tbj_rec_xxxxxxxx_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx')
            fireEvent.change(input, { target: { value: validKey } })
            const submitBtn = screen.getByRole('button', { name: /恢復連線與同步/ })
            fireEvent.click(submitBtn)

            await waitFor(() => {
                expect(mockReanchorSessionWithKey).toHaveBeenCalledWith(validKey)
                expect(refreshEvents).toBeGreaterThanOrEqual(1)
                expect(expensesFetchCount).toBe(2)
            })
        } finally {
            window.removeEventListener('tabidachi-trigger-refresh', onRefresh)
        }
    })

    it('POISearch displays empty state, recovers via retry on error, and discards stale out-of-order responses', async () => {
        // 1. Empty state check
        mockPoiNearby.mockResolvedValueOnce({ count: 0, pois: [] })

        render(
            <LanguageProvider>
                <POISearch centerLat={25.0551} centerLng={121.5083} />
            </LanguageProvider>
        )

        const deptBtn = screen.getByRole('button', { name: /百貨/ })
        fireEvent.click(deptBtn)

        expect(await screen.findByText(/附近暫無此類別地點/)).toBeInTheDocument()

        // 2. Error + retry check
        mockPoiNearby.mockRejectedValueOnce(new Error('Upstream error'))
        mockPoiNearby.mockResolvedValueOnce({
            count: 1,
            pois: [{ id: 'p_1', name: 'Dihua Cafe', category: 'restaurant', lat: 25.056, lng: 121.509, distance: 110 }],
        })

        const foodBtn = screen.getByRole('button', { name: /美食/ })
        fireEvent.click(foodBtn)

        expect(await screen.findByText(/周邊景點載入失敗/)).toBeInTheDocument()
        const retryBtn = screen.getByRole('button', { name: /重試/ })
        fireEvent.click(retryBtn)

        expect(await screen.findByText('Dihua Cafe')).toBeInTheDocument()

        // 3. Stale out-of-order response guard when switching categories quickly
        let resolveSlowStore!: (val: unknown) => void
        const slowStorePromise = new Promise((resolve) => {
            resolveSlowStore = resolve
        })
        mockPoiNearby.mockReturnValueOnce(slowStorePromise)
        mockPoiNearby.mockResolvedValueOnce({
            count: 1,
            pois: [{ id: 'p_fast', name: 'Fast Pharmacy', category: 'pharmacy', lat: 25.055, lng: 121.508, distance: 50 }],
        })

        fireEvent.click(screen.getByRole('button', { name: /超商/ }))
        fireEvent.click(screen.getByRole('button', { name: /藥妝/ }))

        expect(await screen.findByText('Fast Pharmacy')).toBeInTheDocument()

        await act(async () => {
            resolveSlowStore({
                count: 1,
                pois: [{ id: 'p_slow', name: 'Stale Slow Store', category: 'convenience', lat: 25.055, lng: 121.508, distance: 90 }],
            })
        })

        expect(screen.queryByText('Stale Slow Store')).not.toBeInTheDocument()
        expect(screen.getByText('Fast Pharmacy')).toBeInTheDocument()
    })

    it('useExpenses and useTripCapsules stop retrying on 401 and useTripDetail deduplicates multi-mount requests', async () => {
        vi.useFakeTimers({ shouldAdvanceTime: true })
        let expensesHits = 0
        let capsulesHits = 0
        let tripDetailHits = 0

        globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
            const url = String(input)
            if (url.includes('/expenses')) {
                expensesHits += 1
                return new Response(JSON.stringify({ detail: 'Unauthorized' }), { status: 401 })
            }
            if (url.includes('/capsules')) {
                capsulesHits += 1
                return new Response(JSON.stringify({ detail: 'Unauthorized' }), { status: 401 })
            }
            if (url.includes('/api/trips/trip-dup')) {
                tripDetailHits += 1
                return new Response(JSON.stringify({ id: 'trip-dup', title: 'Taipei', items: [] }), { status: 200 })
            }
            return new Response('{}', { status: 200 })
        }) as unknown as typeof fetch

        const MultiSubscriber = () => {
            useExpenses('trip-dup', '3f7abf22-b447-4281-b240-584549c79943')
            useTripCapsules('trip-dup', '3f7abf22-b447-4281-b240-584549c79943')
            useTripDetail('trip-dup', '3f7abf22-b447-4281-b240-584549c79943')
            useTripDetail('trip-dup', '3f7abf22-b447-4281-b240-584549c79943')
            useTripDetail('trip-dup', '3f7abf22-b447-4281-b240-584549c79943')
            useTripDetail('trip-dup', '3f7abf22-b447-4281-b240-584549c79943')
            return <div>mounted</div>
        }

        try {
            render(
                <SWRConfig value={{ provider: () => new Map() }}>
                    <MultiSubscriber />
                </SWRConfig>
            )

            await waitFor(() => {
                expect(expensesHits).toBe(1)
                expect(capsulesHits).toBe(1)
            })

            await act(async () => {
                await vi.advanceTimersByTimeAsync(15_000)
            })

            // Zero background 401 retry storms for expenses/capsules and deduplicated trip detail fetches
            expect(expensesHits).toBe(1)
            expect(capsulesHits).toBe(1)
            expect(tripDetailHits).toBeLessThanOrEqual(2)
        } finally {
            vi.useRealTimers()
        }
    })

    it('useBackgroundSync immediately replays outbox on tabiji:session_restored event', async () => {
        const SyncProbe = () => {
            useBackgroundSync()
            return null
        }

        render(<SyncProbe />)
        expect(mockSyncPeek).not.toHaveBeenCalled()

        act(() => {
            window.dispatchEvent(new CustomEvent('tabiji:session_restored'))
        })

        await waitFor(() => {
            expect(mockSyncPeek).toHaveBeenCalledTimes(1)
        })
    })
})
