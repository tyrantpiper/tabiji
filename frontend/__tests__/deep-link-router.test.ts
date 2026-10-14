import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useTripStore } from '@/lib/stores/tripStore'
import { dispatchDeepLink, useDeepLinkRouter } from '@/lib/hooks/useDeepLinkRouter'

describe('Deep Link Router & Store Integration', () => {
    beforeEach(() => {
        useTripStore.setState({
            activeTripId: null,
            focusedDay: 1,
            targetExpenseId: null,
        })
    })

    it('should set and clear targetExpenseId in tripStore', () => {
        expect(useTripStore.getState().targetExpenseId).toBeNull()

        useTripStore.getState().setTargetExpenseId('exp-uuid-123')
        expect(useTripStore.getState().targetExpenseId).toBe('exp-uuid-123')

        useTripStore.getState().setTargetExpenseId(null)
        expect(useTripStore.getState().targetExpenseId).toBeNull()
    })

    it('should allow setting focusedDay to 0 for Overview', () => {
        expect(useTripStore.getState().focusedDay).toBe(1)

        useTripStore.getState().setFocusedDay(0)
        expect(useTripStore.getState().focusedDay).toBe(0)
    })

    it('should dispatch custom tabidachi-deep-link event', () => {
        let receivedDetail: unknown = null
        const handler = (e: Event) => {
            const ce = e as CustomEvent<{ link?: string }>
            receivedDetail = ce.detail
        }
        window.addEventListener('tabidachi-deep-link', handler)

        dispatchDeepLink('/?trip=trip-abc&tab=tools&expense_id=exp-xyz')

        expect(receivedDetail).toEqual({ link: '/?trip=trip-abc&tab=tools&expense_id=exp-xyz' })
        window.removeEventListener('tabidachi-deep-link', handler)
    })

    it('TC-SW: should process both TABIJI_PUSH_NAVIGATE and legacy TABIDACHI_PUSH_NAVIGATE messages smoothly', () => {
        let messageHandler: ((event: MessageEvent) => void) | null = null
        const mockServiceWorker = {
            addEventListener: vi.fn((type: string, handler: EventListener) => {
                if (type === 'message') messageHandler = handler as (event: MessageEvent) => void
            }),
            removeEventListener: vi.fn(),
        }

        const originalNavigator = window.navigator
        Object.defineProperty(window, 'navigator', {
            value: {
                ...originalNavigator,
                serviceWorker: mockServiceWorker,
            },
            writable: true,
            configurable: true,
        })

        const onTabChange = vi.fn()
        const { unmount } = renderHook(() => useDeepLinkRouter({ onTabChange }))

        expect(mockServiceWorker.addEventListener).toHaveBeenCalledWith('message', expect.any(Function))
        expect(messageHandler).not.toBeNull()

        // 1. 驗證新版 TABIJI_PUSH_NAVIGATE 協議
        act(() => {
            messageHandler?.(new MessageEvent('message', {
                data: { type: 'TABIJI_PUSH_NAVIGATE', url: '/?trip=trip-tabiji-456&day=2' }
            }))
        })
        expect(useTripStore.getState().activeTripId).toBe('trip-tabiji-456')
        expect(useTripStore.getState().focusedDay).toBe(2)

        // 2. 驗證舊版 TABIDACHI_PUSH_NAVIGATE 雙軌相容性
        act(() => {
            messageHandler?.(new MessageEvent('message', {
                data: { type: 'TABIDACHI_PUSH_NAVIGATE', url: '/?trip=trip-legacy-123&day=0' }
            }))
        })
        expect(useTripStore.getState().activeTripId).toBe('trip-legacy-123')
        expect(useTripStore.getState().focusedDay).toBe(0)

        unmount()
        Object.defineProperty(window, 'navigator', {
            value: originalNavigator,
            writable: true,
            configurable: true,
        })
    })
})
