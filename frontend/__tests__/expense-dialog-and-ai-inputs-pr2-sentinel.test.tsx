/**
 * @vitest-environment jsdom
 */
import fs from 'fs'
import path from 'path'
import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, fireEvent, waitFor, act } from '@testing-library/react'
import { toast } from 'sonner'

vi.mock('sonner', () => ({
    toast: {
        success: vi.fn(),
        error: vi.fn(),
        warning: vi.fn(),
        info: vi.fn(),
    },
}))

vi.mock('@/lib/image-utils', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@/lib/image-utils')>()
    return {
        ...actual,
        compressImage: vi.fn(async (file: File) =>
            new File([new Uint8Array([82, 73, 70, 70])], file.name.replace(/\.[a-z0-9]+$/i, '.webp'), {
                type: 'image/webp',
            })
        ),
    }
})

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

vi.mock('@/lib/currency', () => ({
    getExchangeRate: vi.fn(async () => 0.22),
    getAllSupportedCurrencies: vi.fn(async () => []),
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

import { ImageUpload } from '@/components/ui/image-upload'
import { ExpenseDialog } from '@/components/expense-dialog'
import { AiImportTripWizard } from '@/components/itinerary/AiImportTripWizard'
import { uploadCapsulePhotoToCloudinary } from '@/lib/capsule-upload'
import { aiApi, cloudinaryApi } from '@/lib/api'
import { compressImage } from '@/lib/image-utils'

describe('🛡️ PR 2 ExpenseDialog Direct-Pass Receipt & Upload Hardening Sentinel', () => {
    const origXhr = globalThis.XMLHttpRequest

    beforeEach(() => {
        vi.clearAllMocks()
        localStorage.clear()
        localStorage.setItem('user_uuid', '3f7abf22-b447-4281-b240-584549c79943')
    })

    afterEach(() => {
        globalThis.XMLHttpRequest = origXhr
        vi.restoreAllMocks()
    })

    it('AC-5: Newly uploaded receipt normalizes .heic->.jpg, passes compressed local dataUrl directly to aiApi.parseReceipt, ignores failed re-upload, and clears cache on close', async () => {
        vi.spyOn(cloudinaryApi, 'signUpload').mockResolvedValue({
            signature: 'receipt_sig_ok',
            apiKey: '111122223333444',
            cloudName: 'dnpcnwrcu',
        })
        const parseReceiptSpy = vi.spyOn(aiApi, 'parseReceipt').mockResolvedValue({
            title: 'Lawson',
            total_amount: 680,
            currency: 'JPY',
        })

        let xhrMode: 'heic_ok' | 'bad_json' | 'http_500' = 'heic_ok'
        const uploadedFilenames: string[] = []
        class MockXHR {
            status = 200
            responseText = ''
            upload: { onprogress?: (e: { lengthComputable: boolean; loaded: number; total: number }) => void } = {}
            onload?: () => void
            onerror?: () => void
            open() {}
            send(body: FormData) {
                const f = body.get('file') as File | null
                if (f) uploadedFilenames.push(f.name)
                if (xhrMode === 'heic_ok') {
                    this.status = 200
                    this.responseText = JSON.stringify({
                        secure_url: 'https://res.cloudinary.com/dnpcnwrcu/image/upload/v1/ryan_travel/receipts/r1.HEIC',
                    })
                } else if (xhrMode === 'bad_json') {
                    this.status = 200
                    this.responseText = '<html>Gateway error</html>'
                } else {
                    this.status = 500
                    this.responseText = 'Internal error'
                }
                this.onload?.()
            }
        }
        globalThis.XMLHttpRequest = MockXHR as unknown as typeof XMLHttpRequest

        const { baseElement, rerender } = render(
            <ExpenseDialog
                open={true}
                onOpenChange={vi.fn()}
                editItem={null}
                activeTripId="trip-1"
                activeTrip={{ id: 'trip-1', title: 'Tokyo', start_date: '2026-11-10', end_date: '2026-11-15' }}
                selectedCurrency="JPY"
                onSaveSuccess={vi.fn()}
            />
        )

        const fileInput = baseElement.querySelector('input[type="file"]') as HTMLInputElement
        expect(fileInput).toBeTruthy()
        const receiptFile = new File(['raw-receipt'], 'receipt_01.HEIC', { type: '' })
        fireEvent.change(fileInput, { target: { files: [receiptFile] } })

        await waitFor(() => {
            expect(toast.success).toHaveBeenCalledWith('img_upload_success')
        })
        expect(compressImage).toHaveBeenCalledWith(receiptFile, 'receipt')
        expect(uploadedFilenames[0]).toBe('receipt_01.webp')

        // Click AI Parse -> MUST pass both normalized .jpg URL AND precomputed dataUrl!
        const aiBtn = Array.from(baseElement.querySelectorAll('button')).find((b) =>
            b.textContent?.includes('exp_ai_parse')
        ) as HTMLButtonElement
        expect(aiBtn).toBeTruthy()
        expect(aiBtn.disabled).toBe(false)
        fireEvent.click(aiBtn)

        await waitFor(() => {
            expect(parseReceiptSpy).toHaveBeenCalledTimes(1)
        })
        const [calledUrl, calledDirectImage, calledLang] = parseReceiptSpy.mock.calls[0]
        expect(calledUrl).toBe('https://res.cloudinary.com/dnpcnwrcu/image/upload/v1/ryan_travel/receipts/r1.jpg')
        expect(calledDirectImage).toMatch(/^data:image\/webp;base64,/)
        expect(calledLang).toBe('zh')

        // Malformed JSON XHR failure MUST NOT corrupt existing receiptUrl or localReceipt
        xhrMode = 'bad_json'
        fireEvent.change(fileInput, { target: { files: [new File(['bad'], 'bad.jpg', { type: 'image/jpeg' })] } })
        await waitFor(() => {
            expect(toast.error).toHaveBeenCalledWith('img_upload_failed')
        })

        // Re-click AI Parse -> still sends original r1.jpg and its matching dataUrl
        parseReceiptSpy.mockClear()
        fireEvent.click(aiBtn)
        await waitFor(() => {
            expect(parseReceiptSpy).toHaveBeenCalledTimes(1)
        })
        expect(parseReceiptSpy.mock.calls[0][0]).toBe(
            'https://res.cloudinary.com/dnpcnwrcu/image/upload/v1/ryan_travel/receipts/r1.jpg'
        )
        expect(parseReceiptSpy.mock.calls[0][1]).toMatch(/^data:image\/webp;base64,/)

        // Close and reopen with an existing expense -> localReceipt MUST be cleared (directImage = undefined)
        rerender(
            <ExpenseDialog
                open={false}
                onOpenChange={vi.fn()}
                editItem={null}
                activeTripId="trip-1"
                activeTrip={{ id: 'trip-1', title: 'Tokyo', start_date: '2026-11-10', end_date: '2026-11-15' }}
                selectedCurrency="JPY"
                onSaveSuccess={vi.fn()}
            />
        )
        rerender(
            <ExpenseDialog
                open={true}
                onOpenChange={vi.fn()}
                editItem={{
                    id: 'exp-existing',
                    title: 'Existing Ramen',
                    amount: 1200,
                    is_public: true,
                    image_url: 'https://res.cloudinary.com/dnpcnwrcu/image/upload/v1/ryan_travel/receipts/old.jpg',
                }}
                activeTripId="trip-1"
                activeTrip={{ id: 'trip-1', title: 'Tokyo', start_date: '2026-11-10', end_date: '2026-11-15' }}
                selectedCurrency="JPY"
                onSaveSuccess={vi.fn()}
            />
        )

        parseReceiptSpy.mockClear()
        const aiBtnExisting = Array.from(baseElement.querySelectorAll('button')).find((b) =>
            b.textContent?.includes('exp_ai_parse')
        ) as HTMLButtonElement
        fireEvent.click(aiBtnExisting)

        await waitFor(() => {
            expect(parseReceiptSpy).toHaveBeenCalledTimes(1)
        })
        expect(parseReceiptSpy.mock.calls[0]).toEqual([
            'https://res.cloudinary.com/dnpcnwrcu/image/upload/v1/ryan_travel/receipts/old.jpg',
            undefined,
            'zh',
        ])
    })

    it('AC-6 & Thumbnail Parity: TripSettingsView, TripDialogs external <Image> have unoptimized, TimelineCardOverlay uses getOptimizedImageUrl(..., 320), MultiImageUpload uses f_auto', () => {
        const settingsSrc = fs.readFileSync(
            path.resolve(__dirname, '../components/itinerary/TripSettingsView.tsx'),
            'utf8'
        )
        expect(settingsSrc).toMatch(/<Image[\s\S]*?src=\{displayCover\}[\s\S]*?unoptimized/)

        const dialogsSrc = fs.readFileSync(
            path.resolve(__dirname, '../components/itinerary/TripDialogs.tsx'),
            'utf8'
        )
        expect(dialogsSrc).toMatch(/<Image[\s\S]*?src=\{aiCoverImage \|\| resolveDestinationCover\(aiResult\.title\)\}[\s\S]*?unoptimized/)
        expect(dialogsSrc).toMatch(/<Image[\s\S]*?src=\{importCoverImage \|\| resolveDestinationCover\(importResult\.title\)\}[\s\S]*?unoptimized/)

        const overlaySrc = fs.readFileSync(
            path.resolve(__dirname, '../components/itinerary/TimelineCardOverlay.tsx'),
            'utf8'
        )
        expect(overlaySrc).toContain('getOptimizedImageUrl(activity.image_urls?.[0] || activity.image_url, 320)')

        const multiSrc = fs.readFileSync(
            path.resolve(__dirname, '../components/ui/multi-image-upload.tsx'),
            'utf8'
        )
        expect(multiSrc).toContain("isTrustedUrl(url, 'cloudinary.com')")
        expect(multiSrc).toContain('/upload/w_200,h_200,c_fill,f_auto,q_auto/')
    })

    it('Capsule upload relaxes raw limit to 25MB, compresses with capsule preset, enforces post-compression 8MB gate, and normalizes .heic->.jpg', async () => {
        vi.spyOn(cloudinaryApi, 'signUpload').mockResolvedValue({
            signature: 'cap_sig_ok',
            apiKey: '111122223333444',
            cloudName: 'dnpcnwrcu',
        })

        class MockXHR {
            status = 200
            responseText = JSON.stringify({
                secure_url: 'https://res.cloudinary.com/dnpcnwrcu/image/upload/v1/tabidachi_capsules/c1.heic',
            })
            upload: { onprogress?: (e: { lengthComputable: boolean; loaded: number; total: number }) => void } = {}
            onload?: () => void
            onerror?: () => void
            open() {}
            send() {
                this.onload?.()
            }
        }
        globalThis.XMLHttpRequest = MockXHR as unknown as typeof XMLHttpRequest

        // 1. > 25MB raw rejected before compression
        const tooBigRaw = new File(['x'], 'huge.jpg', { type: 'image/jpeg' })
        Object.defineProperty(tooBigRaw, 'size', { value: 26 * 1024 * 1024 })
        await expect(uploadCapsulePhotoToCloudinary(tooBigRaw)).rejects.toThrow('25MB')

        // 2. 12MB raw empty-MIME .HEIC -> compresses to tiny webp -> passes 8MB post-gate and normalizes .heic->.jpg
        const rawHeic12MB = new File(['heic-raw'], 'snap.HEIC', { type: '' })
        Object.defineProperty(rawHeic12MB, 'size', { value: 12 * 1024 * 1024 })
        const outUrl = await uploadCapsulePhotoToCloudinary(rawHeic12MB)
        expect(compressImage).toHaveBeenCalledWith(rawHeic12MB, 'capsule')
        expect(outUrl).toBe('https://res.cloudinary.com/dnpcnwrcu/image/upload/v1/tabidachi_capsules/c1.jpg')

        // 3. Post-compression > 8MB rejected cleanly
        const stillHugeCompressed = new File(['still-big'], 'still.jpg', { type: 'image/jpeg' })
        Object.defineProperty(stillHugeCompressed, 'size', { value: 9 * 1024 * 1024 })
        vi.mocked(compressImage).mockResolvedValueOnce(stillHugeCompressed)
        const normalRaw = new File(['raw'], 'raw.jpg', { type: 'image/jpeg' })
        await expect(uploadCapsulePhotoToCloudinary(normalRaw)).rejects.toThrow('8MB')
    })

    it('AiImportTripWizard compresses with ai_input preset, clears input value, and shows HEIC fallback UI on img onError', async () => {
        const { container, getByText } = render(
            <AiImportTripWizard userId="u-1" onComplete={vi.fn()} />
        )
        const input = container.querySelector('input[type="file"]') as HTMLInputElement
        const heicFile = new File(['heic'], 'itinerary.HEIC', { type: '' })

        fireEvent.change(input, { target: { files: [heicFile] } })

        await waitFor(() => {
            expect(compressImage).toHaveBeenCalledWith(heicFile, 'ai_input')
        })
        expect(input.value).toBe('')

        const previewImg = await waitFor(() => {
            const img = container.querySelector('img[alt="Preview"]')
            expect(img).toBeTruthy()
            return img as HTMLImageElement
        })
        fireEvent.error(previewImg)

        await waitFor(() => {
            expect(getByText('HEIC')).toBeTruthy()
        })
    })

    it('ExpenseDialog switching editItem directly while open=true resets receiptUrl & clears localReceipt, and ImageUpload unmount/abort guards prevent stale state mutations', async () => {
        vi.spyOn(cloudinaryApi, 'signUpload').mockResolvedValue({
            signature: 'switch_sig',
            apiKey: '111122223333444',
            cloudName: 'dnpcnwrcu',
        })
        const parseReceiptSpy = vi.spyOn(aiApi, 'parseReceipt').mockResolvedValue({
            title: 'Sushi',
            total_amount: 3000,
            currency: 'JPY',
        })

        class InstantXHR {
            status = 200
            responseText = JSON.stringify({
                secure_url: 'https://res.cloudinary.com/dnpcnwrcu/image/upload/v1/ryan_travel/receipts/r1.jpg',
            })
            upload = {}
            onload?: () => void
            onerror?: () => void
            onabort?: () => void
            abort = vi.fn()
            open() {}
            send() {
                this.onload?.()
            }
        }
        globalThis.XMLHttpRequest = InstantXHR as unknown as typeof XMLHttpRequest

        const { baseElement, rerender } = render(
            <ExpenseDialog
                open={true}
                onOpenChange={vi.fn()}
                editItem={null}
                activeTripId="trip-1"
                activeTrip={{ id: 'trip-1', title: 'Tokyo', start_date: '2026-11-10', end_date: '2026-11-15' }}
                selectedCurrency="JPY"
                onSaveSuccess={vi.fn()}
            />
        )

        const input = baseElement.querySelector('input[type="file"]') as HTMLInputElement
        fireEvent.change(input, { target: { files: [new File(['r1'], 'r1.jpg', { type: 'image/jpeg' })] } })
        await waitFor(() => expect(toast.success).toHaveBeenCalledWith('img_upload_success'))

        // Switch editItem directly while open stays true
        rerender(
            <ExpenseDialog
                open={true}
                onOpenChange={vi.fn()}
                editItem={{
                    id: 'exp-switched-2',
                    title: 'Sushi',
                    amount: 3000,
                    is_public: true,
                    image_url: 'https://res.cloudinary.com/dnpcnwrcu/image/upload/v1/ryan_travel/receipts/old-exp2.jpg',
                }}
                activeTripId="trip-1"
                activeTrip={{ id: 'trip-1', title: 'Tokyo', start_date: '2026-11-10', end_date: '2026-11-15' }}
                selectedCurrency="JPY"
                onSaveSuccess={vi.fn()}
            />
        )

        const aiBtn = Array.from(baseElement.querySelectorAll('button')).find((b) =>
            b.textContent?.includes('exp_ai_parse')
        ) as HTMLButtonElement
        fireEvent.click(aiBtn)
        await waitFor(() => expect(parseReceiptSpy).toHaveBeenCalledTimes(1))
        expect(parseReceiptSpy.mock.calls[0]).toEqual([
            'https://res.cloudinary.com/dnpcnwrcu/image/upload/v1/ryan_travel/receipts/old-exp2.jpg',
            undefined,
            'zh',
        ])

        // ImageUpload unmount aborts in-flight XHR and suppresses stale callbacks; onabort unlocks re-entrancy
        const sentXhrs: Array<{ onload?: () => void; onabort?: () => void; abort: ReturnType<typeof vi.fn> }> = []
        class DeferredXHR {
            status = 200
            responseText = JSON.stringify({
                secure_url: 'https://res.cloudinary.com/dnpcnwrcu/image/upload/v1/stale.jpg',
            })
            upload = {}
            onload?: () => void
            onerror?: () => void
            onabort?: () => void
            abort = vi.fn(() => {
                this.onabort?.()
            })
            open() {}
            send() {
                sentXhrs.push(this)
            }
        }
        globalThis.XMLHttpRequest = DeferredXHR as unknown as typeof XMLHttpRequest

        const onChange = vi.fn()
        const onSuccess = vi.fn()
        const mounted = render(<ImageUpload onChange={onChange} onUploadSuccess={onSuccess} folder="ryan_travel/receipts/u1" />)
        const upInput = mounted.container.querySelector('input[type="file"]') as HTMLInputElement
        fireEvent.change(upInput, { target: { files: [new File(['a'], 'a.jpg', { type: 'image/jpeg' })] } })
        await waitFor(() => expect(sentXhrs).toHaveLength(1))

        // Trigger onabort while mounted -> unlocks for next upload
        act(() => {
            sentXhrs[0].onabort?.()
        })
        fireEvent.change(upInput, { target: { files: [new File(['b'], 'b.jpg', { type: 'image/jpeg' })] } })
        await waitFor(() => expect(sentXhrs).toHaveLength(2))

        // Unmount while XHR in flight -> aborts and ignores late onload
        const xhrBeforeUnmount = sentXhrs[1]
        mounted.unmount()
        expect(xhrBeforeUnmount.abort).toHaveBeenCalledTimes(1)
        act(() => {
            xhrBeforeUnmount.onload?.()
        })
        expect(onChange).not.toHaveBeenCalled()
        expect(onSuccess).not.toHaveBeenCalled()
    })

    it('AiImportTripWizard normalizes empty-MIME undecodable HEIC to data:image/heic (not application/octet-stream)', async () => {
        const heicFile = new File([new Uint8Array([0, 0, 0, 24, 0x66, 0x74, 0x79, 0x70])], 'IMG_0001.HEIC', { type: '' })
        // Simulate non-Safari browser where compressImage fails open returning raw empty-MIME HEIC
        vi.mocked(compressImage).mockResolvedValueOnce(heicFile)

        const { container } = render(<AiImportTripWizard userId="u-1" onComplete={vi.fn()} />)
        const input = container.querySelector('input[type="file"]') as HTMLInputElement
        fireEvent.change(input, { target: { files: [heicFile] } })

        const previewImg = await waitFor(() => {
            const img = container.querySelector('img[alt="Preview"]') as HTMLImageElement | null
            expect(img).toBeTruthy()
            return img!
        })
        expect(previewImg.src).toMatch(/^data:image\/heic;base64,/)
    })
})
