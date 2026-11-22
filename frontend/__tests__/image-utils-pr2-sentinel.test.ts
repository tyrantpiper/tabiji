/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
    IMAGE_PRESETS,
    MAX_CANVAS_PIXELS,
    __resetImageUtilsForTesting,
    computeTargetDimensions,
    compressImage,
    hasJpegExifMetadata,
    isImageFile,
    readImageFileAsDataUrl,
} from '@/lib/image-utils'

function makeJpegBytes(opts: { app1?: boolean; app13?: boolean; fakeExifInScan?: boolean }): Uint8Array<ArrayBuffer> {
    const chunks: number[] = [0xff, 0xd8] // SOI
    if (opts.app1) {
        // APP1 segment: FF E1 <len=8> "Exif\0\0"
        chunks.push(0xff, 0xe1, 0x00, 0x08, 0x45, 0x78, 0x69, 0x66, 0x00, 0x00)
    }
    if (opts.app13) {
        // APP13 segment: FF ED <len=6> "IPTC"
        chunks.push(0xff, 0xed, 0x00, 0x06, 0x49, 0x50, 0x54, 0x43)
    }
    // DQT segment: FF DB <len=4> 00 01
    chunks.push(0xff, 0xdb, 0x00, 0x04, 0x00, 0x01)
    // SOS marker: FF DA <len=4> 00 01
    chunks.push(0xff, 0xda, 0x00, 0x04, 0x00, 0x01)
    if (opts.fakeExifInScan) {
        // Compressed scan bytes containing FF E1 must NOT be mistaken for APP1 header
        chunks.push(0xff, 0xe1, 0x00, 0x08, 0x11, 0x22)
    }
    chunks.push(0xff, 0xd9) // EOI
    const buf = new ArrayBuffer(chunks.length)
    const arr = new Uint8Array(buf)
    arr.set(chunks)
    return arr
}

describe('🛡️ PR 2 Image Utils Sentinel (Geometry, EXIF, Safari WebP Fallback, Serial Queue, VRAM)', () => {
    const origCreateImageBitmap = globalThis.createImageBitmap
    const origCreateObjectURL = URL.createObjectURL
    const origRevokeObjectURL = URL.revokeObjectURL
    const origCreateElement = document.createElement.bind(document)

    beforeEach(() => {
        __resetImageUtilsForTesting()
        vi.restoreAllMocks()
    })

    afterEach(() => {
        globalThis.createImageBitmap = origCreateImageBitmap
        URL.createObjectURL = origCreateObjectURL
        URL.revokeObjectURL = origRevokeObjectURL
        vi.restoreAllMocks()
        __resetImageUtilsForTesting()
    })

    it('AC-1 & AC-2: computeTargetDimensions enforces dual-axis bounds, 16MP Safari cap, no upscale, and backend-identical long-receipt math', () => {
        // Standard 4:3 downscale matching backend test_cloud_run_hardening_sentinel.py
        expect(computeTargetDimensions(4000, 3000, 2048, 2048, true)).toEqual({ width: 2048, height: 1536 })
        // Non-square box constraint: both axes strictly respected
        expect(computeTargetDimensions(1000, 1000, 800, 400, false)).toEqual({ width: 400, height: 400 })
        expect(computeTargetDimensions(2000, 1000, 1200, 500, false)).toEqual({ width: 1000, height: 500 })
        // Never upscales small images
        expect(computeTargetDimensions(300, 200, 1600, 1600, false)).toEqual({ width: 300, height: 200 })
        // iOS Safari 16.7MP limit: 8192x8192 (67MP) capped <= 16_000_000
        const capped = computeTargetDimensions(8192, 8192, 8192, 8192, false)
        expect(capped.width * capped.height).toBeLessThanOrEqual(MAX_CANVAS_PIXELS)
        expect(capped).toEqual({ width: 4000, height: 4000 })

        // Long receipts / LINE screenshots (aspect > 2.0, preserveShortEdge = true)
        expect(computeTargetDimensions(1200, 4800, 2048, 2048, true)).toEqual({ width: 1024, height: 4096 })
        expect(computeTargetDimensions(1000, 5000, 2048, 2048, true)).toEqual({ width: 819, height: 4096 })
        expect(computeTargetDimensions(2000, 6000, 2048, 2048, true)).toEqual({ width: 1200, height: 3600 })
        expect(computeTargetDimensions(1000, 3000, 2048, 2048, true)).toEqual({ width: 1000, height: 3000 })
    })

    it('isImageFile accepts empty-MIME .heic/.heif, standard images, SVG (F15), and rejects non-images', () => {
        expect(isImageFile(new File(['heic'], 'IMG_0001.HEIC', { type: '' }))).toBe(true)
        expect(isImageFile(new File(['heif'], 'photo.heif', { type: 'application/octet-stream' }))).toBe(true)
        expect(isImageFile(new File(['svg'], 'polaroid.svg', { type: 'image/svg+xml' }))).toBe(true)
        expect(isImageFile(new File(['jpg'], 'pic.jpg', { type: 'image/jpeg' }))).toBe(true)
        expect(isImageFile(new File(['pdf'], 'doc.pdf', { type: 'application/pdf' }))).toBe(false)
        expect(isImageFile(new File(['txt'], 'notes.txt', { type: 'text/plain' }))).toBe(false)
        expect(isImageFile(new File(['bin'], 'payload.exe', { type: '' }))).toBe(false)
    })

    it('hasJpegExifMetadata detects APP1 (0xFFE1) & APP13 (0xFFED), ignores 0xFFE1 bytes inside SOS scan payload, and fails closed on truncated/malformed headers', async () => {
        const withApp1 = new File([makeJpegBytes({ app1: true })], 'gps.jpg', { type: 'image/jpeg' })
        const withApp13 = new File([makeJpegBytes({ app13: true })], 'iptc.jpg', { type: 'image/jpeg' })
        const cleanWithScanBytes = new File([makeJpegBytes({ fakeExifInScan: true })], 'clean.jpg', { type: 'image/jpeg' })
        const truncatedBeforeSos = new File([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46])], 'trunc.jpg', { type: 'image/jpeg' })
        const stuffedZeroBeforeSos = new File([new Uint8Array([0xff, 0xd8, 0xff, 0x00, 0xff, 0xda, 0xff, 0xd9])], 'bad00.jpg', { type: 'image/jpeg' })
        const nonJpegHeader = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], 'fake.jpg', { type: 'image/jpeg' })

        expect(await hasJpegExifMetadata(withApp1)).toBe(true)
        expect(await hasJpegExifMetadata(withApp13)).toBe(true)
        expect(await hasJpegExifMetadata(cleanWithScanBytes)).toBe(false)
        expect(await hasJpegExifMetadata(truncatedBeforeSos)).toBe(true)
        expect(await hasJpegExifMetadata(stuffedZeroBeforeSos)).toBe(true)
        expect(await hasJpegExifMetadata(nonJpegHeader)).toBe(true)
    })

    it('Fails open without deadlocking in bare jsdom when createImageBitmap & URL.createObjectURL are unavailable, and skips SVG / small GIF', async () => {
        globalThis.createImageBitmap = undefined as unknown as typeof createImageBitmap
        URL.createObjectURL = undefined as unknown as typeof URL.createObjectURL

        const jpg = new File([new Uint8Array(500)], 'photo.jpg', { type: 'image/jpeg' })
        const svg = new File(['<svg/>'], 'icon.svg', { type: 'image/svg+xml' })
        const smallGif = new File([new Uint8Array(1024)], 'anim.gif', { type: 'image/gif' })

        expect(await compressImage(jpg, 'cover')).toBe(jpg)
        expect(await compressImage(svg, 'capsule')).toBe(svg)
        expect(await compressImage(smallGif, 'spot')).toBe(smallGif)
        expect(IMAGE_PRESETS.avatar.maxWidth).toBe(512)
        expect(IMAGE_PRESETS.receipt.preserveShortEdge).toBe(true)
    })

    it('AC-3: Safari silent WebP->PNG fallback downgrades to white-bg JPEG (.jpg), cleans VRAM (bitmap.close + 0x0 canvas), and fills #ffffff before drawImage', async () => {
        const ops: string[] = []
        const closeSpy = vi.fn()
        const createdCanvases: Array<{ width: number; height: number }> = []

        globalThis.createImageBitmap = vi.fn(async () => ({
            width: 3000,
            height: 2000,
            close: closeSpy,
        })) as unknown as typeof createImageBitmap

        vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
            if (tagName.toLowerCase() !== 'canvas') {
                return origCreateElement(tagName)
            }
            const mockCanvas = {
                width: 0,
                height: 0,
                getContext: () => ({
                    fillStyle: '',
                    imageSmoothingEnabled: false,
                    imageSmoothingQuality: 'low',
                    fillRect: function (this: { fillStyle: string }) {
                        ops.push(`fillRect:${this.fillStyle}`)
                    },
                    drawImage: () => {
                        ops.push('drawImage')
                    },
                }),
                toBlob: (cb: (b: Blob | null) => void, mime?: string) => {
                    if (mime === 'image/webp') {
                        // Simulate iOS Safari silently returning oversized image/png
                        cb(new Blob([new Uint8Array(9000)], { type: 'image/png' }))
                        return
                    }
                    cb(new Blob([new Uint8Array(1200)], { type: 'image/jpeg' }))
                },
            }
            createdCanvases.push(mockCanvas)
            return mockCanvas as unknown as HTMLCanvasElement
        }) as typeof document.createElement)

        const input = new File([new Uint8Array(5000)], 'transparent-receipt.png', { type: 'image/png' })
        const out = await compressImage(input, 'receipt')

        expect(out).toBeInstanceOf(File)
        expect((out as File).type).toBe('image/jpeg')
        expect((out as File).name).toBe('transparent-receipt.jpg')
        expect(closeSpy).toHaveBeenCalledTimes(1)
        // White fill MUST occur before drawImage
        const drawIdx = ops.indexOf('drawImage')
        const whiteFillIdx = ops.lastIndexOf('fillRect:#ffffff', drawIdx)
        expect(whiteFillIdx).toBeGreaterThanOrEqual(0)
        expect(whiteFillIdx).toBeLessThan(drawIdx)
        // All canvases zeroed out for iOS Safari VRAM release
        for (const c of createdCanvases) {
            expect(c.width).toBe(0)
            expect(c.height).toBe(0)
        }
    })

    it('AC-4: EXIF JPEG never falls back to GPS-leaking original when re-encoded is larger, while clean EXIF-free JPEG preserves original to avoid bloat', async () => {
        globalThis.createImageBitmap = vi.fn(async () => ({
            width: 800,
            height: 600,
            close: vi.fn(),
        })) as unknown as typeof createImageBitmap

        const qualitySeen: number[] = []
        vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
            if (tagName.toLowerCase() !== 'canvas') {
                return origCreateElement(tagName)
            }
            const mockCanvas = {
                width: 0,
                height: 0,
                getContext: () => ({
                    fillStyle: '',
                    imageSmoothingEnabled: false,
                    imageSmoothingQuality: 'low',
                    fillRect: vi.fn(),
                    drawImage: vi.fn(),
                }),
                toBlob: (cb: (b: Blob | null) => void, mime?: string, q?: number) => {
                    if (mockCanvas.width === 1 && mockCanvas.height === 1) {
                        cb(new Blob([new Uint8Array(10)], { type: 'image/webp' }))
                        return
                    }
                    qualitySeen.push(q ?? 0)
                    // Make output deliberately larger than tiny test input to trigger bloat/EXIF branch
                    const size = (q ?? 0.85) < 0.8 ? 400 : 600
                    cb(new Blob([new Uint8Array(size)], { type: mime || 'image/webp' }))
                },
            }
            return mockCanvas as unknown as HTMLCanvasElement
        }) as typeof document.createElement)

        // 1. EXIF JPEG -> MUST NOT return original, retries lower quality, strips EXIF into .webp
        const exifJpeg = new File([makeJpegBytes({ app1: true })], 'iphone-gps.jpg', { type: 'image/jpeg' })
        const stripped = await compressImage(exifJpeg, 'spot')
        expect(stripped).not.toBe(exifJpeg)
        expect((stripped as File).name).toBe('iphone-gps.webp')
        expect((stripped as File).type).toBe('image/webp')
        expect(qualitySeen).toContain(0.72)

        // 2. Clean JPEG without EXIF (same dimensions, output bigger) -> preserves original file
        const cleanJpeg = new File([makeJpegBytes({ fakeExifInScan: true })], 'clean.jpg', { type: 'image/jpeg' })
        const preserved = await compressImage(cleanJpeg, 'spot')
        expect(preserved).toBe(cleanJpeg)
    })

    it('AC-3 Serial Queue & Timeout Recovery: 3 concurrent compressions strictly serialize (max active = 1) and a hung task times out without deadlocking subsequent tasks', async () => {
        __resetImageUtilsForTesting({ taskTimeoutMs: 40 })

        let active = 0
        let maxActive = 0

        globalThis.createImageBitmap = vi.fn(async () => {
            active += 1
            maxActive = Math.max(maxActive, active)
            await new Promise((r) => setTimeout(r, 10))
            active -= 1
            return { width: 400, height: 300, close: vi.fn() }
        }) as unknown as typeof createImageBitmap

        vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
            if (tagName.toLowerCase() !== 'canvas') {
                return origCreateElement(tagName)
            }
            return {
                width: 0,
                height: 0,
                getContext: () => ({
                    fillStyle: '',
                    imageSmoothingEnabled: false,
                    imageSmoothingQuality: 'low',
                    fillRect: vi.fn(),
                    drawImage: vi.fn(),
                }),
                toBlob: (cb: (b: Blob | null) => void, mime?: string) => {
                    cb(new Blob([new Uint8Array(50)], { type: mime || 'image/webp' }))
                },
            } as unknown as HTMLCanvasElement
        }) as typeof document.createElement)

        // Part 1: 3 concurrent normal compressions MUST never exceed 1 active Canvas
        const f1 = new File([new Uint8Array(200)], 'a.png', { type: 'image/png' })
        const f2 = new File([new Uint8Array(200)], 'b.png', { type: 'image/png' })
        const f3 = new File([new Uint8Array(200)], 'c.png', { type: 'image/png' })

        const [r1, r2, r3] = await Promise.all([
            compressImage(f1, 'avatar'),
            compressImage(f2, 'avatar'),
            compressImage(f3, 'avatar'),
        ])

        expect(maxActive).toBe(1)
        expect((r1 as File).name).toBe('a.webp')
        expect((r2 as File).name).toBe('b.webp')
        expect((r3 as File).name).toBe('c.webp')

        // Part 2: Hung task times out cleanly to original file and unblocks queued next task
        let hangOnce = true
        globalThis.createImageBitmap = vi.fn(async () => {
            if (hangOnce) {
                hangOnce = false
                await new Promise(() => {})
            }
            return { width: 400, height: 300, close: vi.fn() }
        }) as unknown as typeof createImageBitmap

        const hungFile = new File([new Uint8Array(200)], 'hung.png', { type: 'image/png' })
        const nextFile = new File([new Uint8Array(200)], 'after-hung.png', { type: 'image/png' })
        const [hungRes, nextRes] = await Promise.all([
            compressImage(hungFile, 'avatar'),
            compressImage(nextFile, 'avatar'),
        ])
        expect(hungRes).toBe(hungFile)
        expect((nextRes as File).name).toBe('after-hung.webp')
    })

    it('Fails open in 0ms in real jsdom EVEN when URL.createObjectURL exists (no 8s deadlock when 2D canvas is unavailable)', async () => {
        // Real Node20/jsdom has typeof URL.createObjectURL === 'function' while canvas.getContext('2d') === null
        globalThis.createImageBitmap = undefined as unknown as typeof createImageBitmap
        const jpg = new File([new Uint8Array(500)], 'jsdom-photo.jpg', { type: 'image/jpeg' })
        const start = Date.now()
        const out = await compressImage(jpg, 'receipt')
        expect(out).toBe(jpg)
        expect(Date.now() - start).toBeLessThan(500)
    })

    it('Late-waking timed-out task NEVER allocates a concurrent second Canvas (strict maxActiveCanvases <= 1)', async () => {
        __resetImageUtilsForTesting({ taskTimeoutMs: 30 })
        let activeCanvases = 0
        let maxActiveCanvases = 0
        let callIdx = 0

        globalThis.createImageBitmap = vi.fn(async () => {
            callIdx += 1
            if (callIdx === 1) {
                // Resolves AFTER 30ms timeout while task 2 is inside toBlob
                await new Promise((r) => setTimeout(r, 55))
            }
            return { width: 400, height: 300, close: vi.fn() }
        }) as unknown as typeof createImageBitmap

        vi.spyOn(document, 'createElement').mockImplementation(((tag: string) => {
            if (tag.toLowerCase() !== 'canvas') return origCreateElement(tag)
            const c = {
                _w: 0,
                get width() { return this._w },
                set width(v: number) {
                    if (v > 1 && this._w <= 1) {
                        activeCanvases += 1
                        maxActiveCanvases = Math.max(maxActiveCanvases, activeCanvases)
                    } else if (v === 0 && this._w > 1) {
                        activeCanvases -= 1
                    }
                    this._w = v
                },
                height: 0,
                getContext: () => ({ fillStyle: '', imageSmoothingEnabled: true, imageSmoothingQuality: 'high', fillRect: vi.fn(), drawImage: vi.fn() }),
                toBlob: (cb: (b: Blob | null) => void, mime?: string) => {
                    if (c.width === 1) {
                        cb(new Blob([new Uint8Array(4)], { type: 'image/webp' }))
                        return
                    }
                    setTimeout(() => cb(new Blob([new Uint8Array(50)], { type: mime || 'image/webp' })), 40)
                },
            }
            return c as unknown as HTMLCanvasElement
        }) as typeof document.createElement)

        const f1 = new File([new Uint8Array(100)], 'slow.png', { type: 'image/png' })
        const f2 = new File([new Uint8Array(100)], 'next.png', { type: 'image/png' })
        await Promise.all([compressImage(f1, 'avatar'), compressImage(f2, 'avatar')])
        await new Promise((r) => setTimeout(r, 80))
        expect(maxActiveCanvases).toBeLessThanOrEqual(1)
    })

    it('Runtime Safari WebP->PNG fallback fires even when 1x1 probe reported WebP support, flips cache, and outputs .jpg', async () => {
        const mimesRequestedOnMainCanvas: string[] = []
        globalThis.createImageBitmap = vi.fn(async () => ({
            width: 800,
            height: 600,
            close: vi.fn(),
        })) as unknown as typeof createImageBitmap

        vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
            if (tagName.toLowerCase() !== 'canvas') return origCreateElement(tagName)
            const mockCanvas = {
                width: 0,
                height: 0,
                getContext: () => ({
                    fillStyle: '',
                    imageSmoothingEnabled: true,
                    imageSmoothingQuality: 'high',
                    fillRect: vi.fn(),
                    drawImage: vi.fn(),
                }),
                toBlob: (cb: (b: Blob | null) => void, mime?: string) => {
                    if (mockCanvas.width === 1 && mockCanvas.height === 1) {
                        // 1x1 probe claims WebP is supported
                        cb(new Blob([new Uint8Array(10)], { type: 'image/webp' }))
                        return
                    }
                    mimesRequestedOnMainCanvas.push(mime || '')
                    if (mime === 'image/webp') {
                        // Main canvas silently degrades to oversized PNG on Safari
                        cb(new Blob([new Uint8Array(9000)], { type: 'image/png' }))
                        return
                    }
                    cb(new Blob([new Uint8Array(800)], { type: 'image/jpeg' }))
                },
            }
            return mockCanvas as unknown as HTMLCanvasElement
        }) as typeof document.createElement)

        const first = await compressImage(new File([new Uint8Array(4000)], 'first.png', { type: 'image/png' }), 'spot')
        expect((first as File).type).toBe('image/jpeg')
        expect((first as File).name).toBe('first.jpg')
        expect(mimesRequestedOnMainCanvas).toEqual(['image/webp', 'image/jpeg'])

        // Second call MUST skip image/webp directly because cachedWebpSupport flipped to false
        mimesRequestedOnMainCanvas.length = 0
        const second = await compressImage(new File([new Uint8Array(4000)], 'second.png', { type: 'image/png' }), 'spot')
        expect((second as File).type).toBe('image/jpeg')
        expect(mimesRequestedOnMainCanvas).toEqual(['image/jpeg'])
    })

    it('hasJpegExifMetadata fails closed on >64KB ICC Profile before EXIF and readImageFileAsDataUrl normalizes empty-MIME HEIC/HEIF', async () => {
        // Large JPEG with 70KB APP2 ICC Profile before APP1 (exceeds 64KB slice) -> must fail closed (true)
        const bigHeader = new Uint8Array(72000)
        bigHeader[0] = 0xff
        bigHeader[1] = 0xd8
        // APP2 (0xFFE2) with 65500-byte segment, followed by APP2 #2 pushing APP1 past 64KB
        bigHeader[2] = 0xff
        bigHeader[3] = 0xe2
        bigHeader[4] = 0xff
        bigHeader[5] = 0xdc
        const hugeIccJpeg = new File([bigHeader], 'display-p3.jpg', { type: 'image/jpeg' })
        expect(await hasJpegExifMetadata(hugeIccJpeg)).toBe(true)

        // readImageFileAsDataUrl normalizes empty/octet-stream MIME for HEIC/HEIF AND standard raster extensions
        const heic = new File([new Uint8Array([0, 0, 0, 24, 0x66, 0x74, 0x79, 0x70])], 'IMG_0001.HEIC', { type: '' })
        const heif = new File([new Uint8Array([0, 0, 0, 24, 0x66, 0x74, 0x79, 0x70])], 'IMG_0002.heif', { type: 'application/octet-stream' })
        const jpgOctet = new File([makeJpegBytes({ fakeExifInScan: true })], 'clean.JPG', { type: 'application/octet-stream' })
        const pngEmpty = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], 'shot.png', { type: '' })
        const webpOctet = new File([new Uint8Array([82, 73, 70, 70])], 'shot.webp', { type: 'application/octet-stream' })
        const gifEmpty = new File([new Uint8Array([71, 73, 70, 56])], 'anim.gif', { type: '' })
        const unknownBin = new File([new Uint8Array([1, 2, 3])], 'payload.bin', { type: 'application/octet-stream' })

        expect(await readImageFileAsDataUrl(heic)).toMatch(/^data:image\/heic;base64,/)
        expect(await readImageFileAsDataUrl(heif)).toMatch(/^data:image\/heif;base64,/)
        expect(await readImageFileAsDataUrl(jpgOctet)).toMatch(/^data:image\/jpeg;base64,/)
        expect(await readImageFileAsDataUrl(pngEmpty)).toMatch(/^data:image\/png;base64,/)
        expect(await readImageFileAsDataUrl(webpOctet)).toMatch(/^data:image\/webp;base64,/)
        expect(await readImageFileAsDataUrl(gifEmpty)).toMatch(/^data:image\/gif;base64,/)
        expect(await readImageFileAsDataUrl(unknownBin)).toMatch(/^data:application\/octet-stream;base64,/)
    })
})
