/**
 * @vitest-environment jsdom
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

const {
    mockToastError,
    mockToastInfo,
    mockToastSuccess,
    mockCompressImage,
} = vi.hoisted(() => ({
    mockToastError: vi.fn(),
    mockToastInfo: vi.fn(),
    mockToastSuccess: vi.fn(),
    mockCompressImage: vi.fn(),
}))

vi.mock('@/lib/image-utils', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@/lib/image-utils')>()
    return {
        ...actual,
        compressImage: (...args: unknown[]) => mockCompressImage(...args),
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
    wasLastAuthExchangeTransientFailure: () => false,
}))

vi.mock('sonner', () => ({
    toast: {
        error: (...args: unknown[]) => mockToastError(...args),
        info: (...args: unknown[]) => mockToastInfo(...args),
        success: (...args: unknown[]) => mockToastSuccess(...args),
    },
}))

import ChatWidget from '@/components/chat-widget'
import { LanguageProvider } from '@/lib/LanguageContext'

describe('🛡️ PR 2 ChatWidget Image Compression, HEIC Normalization & Fallback Sentinel', () => {
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
        localStorage.clear()
        vi.restoreAllMocks()
    })

    it('compresses with ai_input preset, clears input value, normalizes empty-MIME HEIC to data:image/heic, shows HEIC fallback UI on img onError, and rejects SVG', async () => {
        const heicFile = new File([new Uint8Array([0, 0, 0, 24, 0x66, 0x74, 0x79, 0x70])], 'receipt.HEIC', { type: '' })
        // Simulate non-Safari browser where HEIC cannot be decoded -> compressImage fails open returning raw empty-MIME HEIC
        mockCompressImage.mockResolvedValueOnce(heicFile)

        const { container } = render(
            <LanguageProvider>
                <ChatWidget />
            </LanguageProvider>
        )
        fireEvent.click(screen.getByRole('button', { name: /Ryan AI/i }))

        const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
        expect(fileInput).toBeTruthy()

        // 1. SVG rejected without calling compressImage
        const svgFile = new File(['<svg/>'], 'evil.svg', { type: 'image/svg+xml' })
        fireEvent.change(fileInput, { target: { files: [svgFile] } })
        expect(mockToastError).toHaveBeenCalledTimes(1)
        expect(mockCompressImage).not.toHaveBeenCalled()
        expect(fileInput.value).toBe('')

        // 2. Empty-MIME HEIC compressed with ai_input, normalized to data:image/heic;base64,..., and degrades cleanly on img onError
        fireEvent.change(fileInput, { target: { files: [heicFile] } })
        await waitFor(() => {
            expect(mockCompressImage).toHaveBeenCalledWith(heicFile, 'ai_input')
        })
        expect(fileInput.value).toBe('')

        const selectedImg = await waitFor(() => {
            const img = container.querySelector('img[alt="Selected"]') as HTMLImageElement | null
            expect(img).toBeTruthy()
            return img!
        })
        expect(selectedImg.src).toMatch(/^data:image\/heic;base64,/)

        fireEvent.error(selectedImg)
        await waitFor(() => {
            expect(screen.getByText(/HEIC 圖片已就緒|HEIC image ready/)).toBeInTheDocument()
        })
    })
})
