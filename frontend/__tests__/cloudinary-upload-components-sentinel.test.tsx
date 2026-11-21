/**
 * @vitest-environment jsdom
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/react'
import { toast } from 'sonner'

vi.mock('sonner', () => ({
    toast: {
        success: vi.fn(),
        error: vi.fn(),
        info: vi.fn(),
    },
}))

vi.mock('@/lib/image-utils', () => ({
    compressImage: vi.fn(async (file: File) => file),
}))

vi.mock('@/lib/hooks', () => ({
    useHaptic: () => ({
        tap: vi.fn(),
        selection: vi.fn(),
        success: vi.fn(),
        error: vi.fn(),
    }),
}))

vi.mock('@/lib/hooks/useTripRealtime', () => ({
    broadcastTripEvent: vi.fn(async () => {}),
}))

vi.mock('@/lib/LanguageContext', () => ({
    useLanguage: () => ({
        lang: 'zh',
        t: (key: string) => key,
    }),
}))

vi.mock('next/image', () => ({
    default: ({
        alt = '',
        fill: _fill,
        unoptimized: _unoptimized,
        priority: _priority,
        ...props
    }: React.ComponentProps<'img'> & { fill?: boolean; unoptimized?: boolean; priority?: boolean }) => {
        void _fill
        void _unoptimized
        void _priority
        // eslint-disable-next-line @next/next/no-img-element
        return <img alt={alt} {...props} />
    },
}))

vi.mock('framer-motion', () => ({
    motion: {
        div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
    },
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

import { ImageUpload } from '@/components/ui/image-upload'
import { MultiImageUpload } from '@/components/ui/multi-image-upload'
import { TripCoverMenu } from '@/components/itinerary/TripCoverMenu'
import { TripSettingsView } from '@/components/itinerary/TripSettingsView'
import { tripsApi } from '@/lib/api'
import { __resetExchangeFailedForTesting } from '@/lib/auth-session'
import type { Trip } from '@/lib/itinerary-types'

function createMockJwt(payload: Record<string, unknown>): string {
    const enc = (obj: Record<string, unknown>) =>
        btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
    return `${enc({ alg: 'HS256', typ: 'JWT' })}.${enc(payload)}.mock_sig`
}

const TEST_UID = '3f7abf22-b447-4281-b240-584549c79943'

const SAMPLE_TRIP: Trip = {
    id: 'trip-upload-test',
    title: '京都賞楓之旅',
    start_date: '2026-11-10',
    end_date: '2026-11-14',
    created_by: TEST_UID,
    days: [{ day: 1, activities: [] }],
}

describe('🛡️ Cloudinary PR 1 React Upload Components Interaction Sentinel', () => {
    const origFetch = globalThis.fetch
    const origXhr = globalThis.XMLHttpRequest
    const origTestAuth = process.env.TEST_AUTH_EXCHANGE

    beforeEach(() => {
        vi.clearAllMocks()
        __resetExchangeFailedForTesting()
        localStorage.clear()
        process.env.TEST_AUTH_EXCHANGE = 'true'
        vi.stubEnv('NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME', 'stale_env_cloud')
        vi.stubEnv('NEXT_PUBLIC_CLOUDINARY_API_KEY', '999999999999999')

        const futureExp = Math.floor(Date.now() / 1000) + 3600
        localStorage.setItem('user_uuid', TEST_UID)
        localStorage.setItem('user_nickname', 'Ryan')
        localStorage.setItem('user_recovery_key', 'tbj_rec_deadbeef_0123456789abcdef0123456789abcdef')
        localStorage.setItem('tabiji_session_token', createMockJwt({ sub: TEST_UID, exp: futureExp }))
    })

    afterEach(() => {
        globalThis.fetch = origFetch
        globalThis.XMLHttpRequest = origXhr
        process.env.TEST_AUTH_EXCHANGE = origTestAuth
        vi.unstubAllEnvs()
        vi.restoreAllMocks()
    })

    it('C1 (ImageUpload): retries once on 401 refresh, uploads with atomic rotated server credentials, and resets loading/progress on 429 failure', async () => {
        const freshJwt = createMockJwt({ sub: TEST_UID, exp: Math.floor(Date.now() / 1000) + 7200 })
        let signCalls = 0
        const authSeen: Array<string | null> = []

        globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
            const url = typeof input === 'string' ? input : input.toString()
            if (url.includes('/api/auth/session')) {
                return new Response(JSON.stringify({ access_token: freshJwt, user_id: TEST_UID }), {
                    status: 200,
                    headers: { 'Content-Type': 'application/json' },
                })
            }
            if (url.includes('/api/sign-cloudinary')) {
                signCalls += 1
                authSeen.push(new Headers(init?.headers).get('Authorization'))
                if (signCalls === 1) {
                    return new Response(JSON.stringify({ detail: 'Invalid or expired token' }), {
                        status: 401,
                        headers: { 'Content-Type': 'application/json' },
                    })
                }
                return new Response(
                    JSON.stringify({
                        signature: 'img_upload_sig_v2',
                        apiKey: '111122223333444',
                        cloudName: 'rotated_prod_cloud',
                    }),
                    { status: 200, headers: { 'Content-Type': 'application/json' } }
                )
            }
            return new Response('{}', { status: 404 })
        }) as unknown as typeof fetch

        const xhrLog: Array<{ url: string; apiKey: string; signature: string; folder: string }> = []
        class MockXHR {
            status = 200
            responseText = JSON.stringify({
                secure_url: 'https://res.cloudinary.com/rotated_prod_cloud/image/upload/v1/ryan_travel/receipts/r1.jpg',
            })
            upload: { onprogress?: (e: { lengthComputable: boolean; loaded: number; total: number }) => void } = {}
            onload?: () => void
            onerror?: () => void
            private targetUrl = ''
            open(_method: string, url: string) {
                this.targetUrl = url
            }
            send(body: FormData) {
                xhrLog.push({
                    url: this.targetUrl,
                    apiKey: String(body.get('api_key') || ''),
                    signature: String(body.get('signature') || ''),
                    folder: String(body.get('folder') || ''),
                })
                this.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 })
                this.onload?.()
            }
        }
        globalThis.XMLHttpRequest = MockXHR as unknown as typeof XMLHttpRequest

        const onChange = vi.fn()
        const { container } = render(<ImageUpload onChange={onChange} folder="ryan_travel/receipts/user1" />)
        const input = container.querySelector('input[type="file"]') as HTMLInputElement
        const file = new File(['img-bytes'], 'receipt.jpg', { type: 'image/jpeg' })

        fireEvent.change(input, { target: { files: [file] } })

        await waitFor(() => {
            expect(onChange).toHaveBeenCalledWith(
                'https://res.cloudinary.com/rotated_prod_cloud/image/upload/v1/ryan_travel/receipts/r1.jpg'
            )
        })
        expect(signCalls).toBe(2)
        expect(authSeen[1]).toBe(`Bearer ${freshJwt}`)
        expect(xhrLog).toEqual([
            {
                url: 'https://api.cloudinary.com/v1_1/rotated_prod_cloud/image/upload',
                apiKey: '111122223333444',
                signature: 'img_upload_sig_v2',
                folder: 'ryan_travel/receipts/user1',
            },
        ])
        expect(input.value).toBe('')

        // Error path: 429 signing error must not call XHR and must reset loading/progress cleanly
        xhrLog.length = 0
        globalThis.fetch = vi.fn(async () =>
            new Response(JSON.stringify({ detail: 'Too many upload signing requests. Please try again shortly.' }), {
                status: 429,
                headers: { 'Content-Type': 'application/json' },
            })
        ) as unknown as typeof fetch

        fireEvent.change(input, { target: { files: [file] } })

        await waitFor(() => {
            expect(toast.error).toHaveBeenCalled()
        })
        expect(xhrLog).toHaveLength(0)
        expect(container.textContent).not.toContain('%')
    })

    it('C2 (MultiImageUpload): rejects non-OK signing responses without sending XHR and resets loading/progress, while happy path uses rotated credentials', async () => {
        const xhrLog: Array<{ url: string; apiKey: string; signature: string }> = []
        class MockXHR {
            status = 200
            responseText = JSON.stringify({
                secure_url: 'https://res.cloudinary.com/rotated_spots_cloud/image/upload/v1/ryan_travel/spots/s1.jpg',
            })
            upload: { onprogress?: (e: { lengthComputable: boolean; loaded: number; total: number }) => void } = {}
            onload?: () => void
            onerror?: () => void
            private targetUrl = ''
            open(_method: string, url: string) {
                this.targetUrl = url
            }
            send(body: FormData) {
                xhrLog.push({
                    url: this.targetUrl,
                    apiKey: String(body.get('api_key') || ''),
                    signature: String(body.get('signature') || ''),
                })
                this.onload?.()
            }
        }
        globalThis.XMLHttpRequest = MockXHR as unknown as typeof XMLHttpRequest

        // 1. Error path first: 500 sign error must abort before XHR and re-enable upload button
        globalThis.fetch = vi.fn(async () =>
            new Response(JSON.stringify({ detail: 'Upload signing service is not configured' }), {
                status: 500,
                headers: { 'Content-Type': 'application/json' },
            })
        ) as unknown as typeof fetch

        const onChange = vi.fn()
        const { container } = render(<MultiImageUpload values={[]} onChange={onChange} folder="ryan_travel/spots" />)
        const input = container.querySelector('input[type="file"]') as HTMLInputElement
        const file = new File(['spot-bytes'], 'spot.jpg', { type: 'image/jpeg' })

        fireEvent.change(input, { target: { files: [file] } })

        await waitFor(() => {
            expect(toast.error).toHaveBeenCalledWith('img_upload_error')
        })
        expect(xhrLog).toHaveLength(0)
        const addButton = container.querySelector('button[type="button"]') as HTMLButtonElement
        expect(addButton.disabled).toBe(false)
        expect(container.textContent).not.toContain('%')

        // 2. Benign happy path with rotated server credentials
        let seenAuth: string | null = null
        globalThis.fetch = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
            seenAuth = new Headers(init?.headers).get('Authorization')
            return new Response(
                JSON.stringify({
                    signature: 'multi_sig_v2',
                    apiKey: '111122223333444',
                    cloudName: 'rotated_spots_cloud',
                }),
                { status: 200, headers: { 'Content-Type': 'application/json' } }
            )
        }) as unknown as typeof fetch

        fireEvent.change(input, { target: { files: [file] } })

        await waitFor(() => {
            expect(onChange).toHaveBeenCalledWith([
                'https://res.cloudinary.com/rotated_spots_cloud/image/upload/v1/ryan_travel/spots/s1.jpg',
            ])
        })
        expect(seenAuth).toContain('Bearer ')
        expect(xhrLog).toEqual([
            {
                url: 'https://api.cloudinary.com/v1_1/rotated_spots_cloud/image/upload',
                apiKey: '111122223333444',
                signature: 'multi_sig_v2',
            },
        ])
    })

    it('C3 (TripCoverMenu): uses rotated server credentials on happy path and recovers loading state on 429 signing failure', async () => {
        const updateCoverSpy = vi.spyOn(tripsApi, 'updateCover').mockResolvedValue({ status: 'ok' } as never)
        const onUpdate = vi.fn()
        const uploadRequests: Array<{ url: string; apiKey: string; folder: string }> = []

        globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
            const url = typeof input === 'string' ? input : input.toString()
            if (url.includes('/api/sign-cloudinary')) {
                expect(new Headers(init?.headers).get('Authorization')).toContain('Bearer ')
                return new Response(
                    JSON.stringify({
                        signature: 'cover_menu_sig',
                        apiKey: '111122223333444',
                        cloudName: 'rotated_cover_cloud',
                    }),
                    { status: 200, headers: { 'Content-Type': 'application/json' } }
                )
            }
            const fd = init?.body as FormData
            uploadRequests.push({
                url,
                apiKey: String(fd.get('api_key') || ''),
                folder: String(fd.get('folder') || ''),
            })
            return new Response(
                JSON.stringify({
                    secure_url: 'https://res.cloudinary.com/rotated_cover_cloud/image/upload/v1/ryan_travel/covers/c1.jpg',
                }),
                { status: 200, headers: { 'Content-Type': 'application/json' } }
            )
        }) as unknown as typeof fetch

        const { container } = render(
            <TripCoverMenu
                tripId={SAMPLE_TRIP.id}
                tripTitle={SAMPLE_TRIP.title}
                userId={TEST_UID}
                onUpdate={onUpdate}
            />
        )
        const input = container.querySelector('input[type="file"]') as HTMLInputElement
        const file = new File(['cover-bytes'], 'cover.jpg', { type: 'image/jpeg' })

        fireEvent.change(input, { target: { files: [file] } })

        await waitFor(() => {
            expect(updateCoverSpy).toHaveBeenCalledWith(
                SAMPLE_TRIP.id,
                'https://res.cloudinary.com/rotated_cover_cloud/image/upload/v1/ryan_travel/covers/c1.jpg',
                TEST_UID
            )
        })
        expect(onUpdate).toHaveBeenCalledTimes(1)
        expect(uploadRequests).toEqual([
            {
                url: 'https://api.cloudinary.com/v1_1/rotated_cover_cloud/image/upload',
                apiKey: '111122223333444',
                folder: 'ryan_travel/covers',
            },
        ])

        // Error path: 429 signing failure must not upload to Cloudinary and must reset loading
        uploadRequests.length = 0
        globalThis.fetch = vi.fn(async () =>
            new Response(JSON.stringify({ error: 'Rate limit exceeded: 60 per 1 minute' }), {
                status: 429,
                headers: { 'Content-Type': 'application/json' },
            })
        ) as unknown as typeof fetch

        fireEvent.change(input, { target: { files: [file] } })

        await waitFor(() => {
            expect(toast.error).toHaveBeenCalled()
        })
        expect(uploadRequests).toHaveLength(0)
        const triggerBtn = container.querySelector('button[aria-label]') as HTMLButtonElement
        expect(triggerBtn.disabled).toBe(false)
    })

    it('C4 (TripSettingsView): uses rotated server credentials on cover upload and recovers cleanly on 400 signing failure', async () => {
        const updateCoverSpy = vi.spyOn(tripsApi, 'updateCover').mockResolvedValue({ status: 'ok' } as never)
        const onTripUpdated = vi.fn()
        const uploadRequests: Array<{ url: string; apiKey: string }> = []

        globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
            const url = typeof input === 'string' ? input : input.toString()
            if (url.includes('/api/sign-cloudinary')) {
                expect(new Headers(init?.headers).get('Authorization')).toContain('Bearer ')
                return new Response(
                    JSON.stringify({
                        signature: 'settings_cover_sig',
                        apiKey: '111122223333444',
                        cloudName: 'rotated_settings_cloud',
                    }),
                    { status: 200, headers: { 'Content-Type': 'application/json' } }
                )
            }
            const fd = init?.body as FormData
            uploadRequests.push({
                url,
                apiKey: String(fd.get('api_key') || ''),
            })
            return new Response(
                JSON.stringify({
                    secure_url: 'https://res.cloudinary.com/rotated_settings_cloud/image/upload/v1/ryan_travel/covers/s1.jpg',
                }),
                { status: 200, headers: { 'Content-Type': 'application/json' } }
            )
        }) as unknown as typeof fetch

        const { container } = render(
            <TripSettingsView
                currentTrip={SAMPLE_TRIP}
                userId={TEST_UID}
                totalDays={1}
                onBack={vi.fn()}
                onTripUpdated={onTripUpdated}
            />
        )
        const input = container.querySelector('input[type="file"]') as HTMLInputElement
        const file = new File(['settings-cover'], 'settings.jpg', { type: 'image/jpeg' })

        fireEvent.change(input, { target: { files: [file] } })

        await waitFor(() => {
            expect(updateCoverSpy).toHaveBeenCalledWith(
                SAMPLE_TRIP.id,
                'https://res.cloudinary.com/rotated_settings_cloud/image/upload/v1/ryan_travel/covers/s1.jpg',
                TEST_UID
            )
        })
        expect(uploadRequests).toEqual([
            {
                url: 'https://api.cloudinary.com/v1_1/rotated_settings_cloud/image/upload',
                apiKey: '111122223333444',
            },
        ])

        // Error path: 400 signing failure must not call Cloudinary and must fire error toast
        uploadRequests.length = 0
        globalThis.fetch = vi.fn(async () =>
            new Response(JSON.stringify({ detail: 'Invalid or expired timestamp' }), {
                status: 400,
                headers: { 'Content-Type': 'application/json' },
            })
        ) as unknown as typeof fetch

        fireEvent.change(input, { target: { files: [file] } })

        await waitFor(() => {
            expect(toast.error).toHaveBeenCalled()
        })
        expect(uploadRequests).toHaveLength(0)
    })
})
