import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import worker, { isOriginAllowed, parseProxyPath, prefersAvif, resolveCloudName } from '../../cloudflare/cloudinary-proxy/worker.js'

describe('🛡️ PR 2 Cloudflare cloudinary-proxy Worker Hardening Sentinel', () => {
    const origFetch = globalThis.fetch
    const origCaches = (globalThis as unknown as { caches?: unknown }).caches

    let cacheStore: Map<string, Response>
    let cacheMatchSpy: ReturnType<typeof vi.fn>
    let cachePutSpy: ReturnType<typeof vi.fn>
    let fetchSpy: ReturnType<typeof vi.fn>

    beforeEach(() => {
        cacheStore = new Map()
        cacheMatchSpy = vi.fn(async (req: Request) => {
            const hit = cacheStore.get(req.url)
            return hit ? hit.clone() : undefined
        })
        cachePutSpy = vi.fn(async (req: Request, res: Response) => {
            cacheStore.set(req.url, res.clone())
        })
        ;(globalThis as unknown as { caches: unknown }).caches = {
            default: {
                match: cacheMatchSpy,
                put: cachePutSpy,
            },
        }
        fetchSpy = vi.fn()
        globalThis.fetch = fetchSpy as unknown as typeof fetch
    })

    afterEach(() => {
        globalThis.fetch = origFetch
        ;(globalThis as unknown as { caches?: unknown }).caches = origCaches
        vi.restoreAllMocks()
    })

    it('resolveCloudName eliminates REDACTED placeholder and falls back to dnpcnwrcu', () => {
        expect(resolveCloudName(undefined)).toBe('dnpcnwrcu')
        expect(resolveCloudName({ CLOUDINARY_CLOUD_NAME: 'REDACTED_CLOUDINARY_CLOUD' })).toBe('dnpcnwrcu')
        expect(resolveCloudName({ CLOUDINARY_CLOUD_NAME: 'custom_cloud_prod' })).toBe('custom_cloud_prod')
    })

    it('isOriginAllowed enforces strict new URL() hostname matching while preserving iOS Standalone PWA empty headers', () => {
        // Malicious spoofing blocked (including arbitrary third-party travel-pwa-*.vercel.app projects)
        expect(isOriginAllowed('https://tabijiapp.com.evil.com/page', '')).toBe(false)
        expect(isOriginAllowed('', 'https://evil-tabijiapp.com')).toBe(false)
        expect(isOriginAllowed('https://attacker.vercel.app/', '')).toBe(false)
        expect(isOriginAllowed('https://travel-pwa-evil.vercel.app/', '')).toBe(false)
        expect(isOriginAllowed('', 'https://evil-tyrantpipers-projects.vercel.app')).toBe(false)
        expect(isOriginAllowed('https://www.tabijiapp.com/', 'https://evil.com')).toBe(false)
        expect(isOriginAllowed('not-a-valid-url', '')).toBe(false)
        expect(isOriginAllowed('javascript:alert(1)', '')).toBe(false)

        // Benign controls allowed (including actual tyrantpipers-projects Vercel deployment/preview URLs)
        expect(isOriginAllowed('', '')).toBe(true) // iOS Standalone PWA
        expect(isOriginAllowed('https://www.tabijiapp.com/trips/123', '')).toBe(true)
        expect(isOriginAllowed('https://tabijiapp.com/', '')).toBe(true)
        expect(isOriginAllowed('', 'https://travel-pwa-five.vercel.app')).toBe(true)
        expect(isOriginAllowed('https://travel-na6m8zk52-tyrantpipers-projects.vercel.app/', '')).toBe(true)
        expect(isOriginAllowed('https://travel-pwa-git-feat-tyrantpipers-projects.vercel.app/trip/1', '')).toBe(true)
        expect(isOriginAllowed('http://localhost:3000/', '')).toBe(true)
    })

    it('parseProxyPath blocks transform injection, traversal, encoded dots, missing width, and non-whitelisted widths', () => {
        expect(parseProxyPath('/').ok).toBe(false)
        expect(parseProxyPath('/v1/ryan_travel/a.jpg').ok).toBe(false)
        expect(parseProxyPath('/w_999/v1/ryan_travel/a.jpg')).toMatchObject({ ok: false, status: 403 })
        expect(parseProxyPath('/w_320/e_blur:100/v1/a.jpg').ok).toBe(false)
        expect(parseProxyPath('/w_320/v1/../e_blur:100/a.jpg').ok).toBe(false)
        expect(parseProxyPath('/w_320/v1/%2e%2e/a.jpg').ok).toBe(false)
        expect(parseProxyPath('/w_320/v1/a,b/photo.jpg').ok).toBe(false)
        expect(parseProxyPath('/w_320/v1//photo.jpg').ok).toBe(false)

        // Benign valid path
        expect(parseProxyPath('/w_640/v1792785423/ryan_travel/streetview/mly_947387631644042.jpg')).toEqual({
            ok: true,
            width: '640',
            assetPath: 'v1792785423/ryan_travel/streetview/mly_947387631644042.jpg',
        })
    })

    it('rejects POST/DELETE with 405 no-store and rejects evil Referer / transform injection without calling Cloudinary', async () => {
        const ctx = { waitUntil: vi.fn((p: Promise<unknown>) => p) }

        const postRes = await worker.fetch(
            new Request('https://cloudinary-proxy.ryanpig228.workers.dev/w_320/v1/a.jpg', { method: 'POST' }),
            {},
            ctx
        )
        expect(postRes.status).toBe(405)
        expect(postRes.headers.get('Cache-Control')).toBe('no-store')

        const evilRefRes = await worker.fetch(
            new Request('https://cloudinary-proxy.ryanpig228.workers.dev/w_320/v1/a.jpg', {
                headers: { Referer: 'https://tabijiapp.com.evil.com/' },
            }),
            {},
            ctx
        )
        expect(evilRefRes.status).toBe(403)
        expect(evilRefRes.headers.get('Cache-Control')).toBe('no-store')

        const blurRes = await worker.fetch(
            new Request('https://cloudinary-proxy.ryanpig228.workers.dev/w_320/e_blur:100/v1/a.jpg', {
                headers: { Referer: 'https://www.tabijiapp.com/' },
            }),
            {},
            ctx
        )
        expect(blurRes.status).toBe(400)
        expect(blurRes.headers.get('Cache-Control')).toBe('no-store')

        expect(fetchSpy).not.toHaveBeenCalled()
        expect(cachePutSpy).not.toHaveBeenCalled()
    })

    it('strips upstream poison headers, isolates AVIF vs WebP cache keys, injects c_limit, and NEVER caches 404 or non-image or HEAD responses', async () => {
        const waitPromises: Promise<unknown>[] = []
        const ctx = { waitUntil: vi.fn((p: Promise<unknown>) => waitPromises.push(p)) }

        // 1. Benign 200 WebP response with poisonous upstream headers -> stripped & cached with ?fmt=f_webp
        fetchSpy.mockResolvedValueOnce(
            new Response(new Uint8Array([1, 2, 3]), {
                status: 200,
                headers: {
                    'Content-Type': 'image/webp',
                    'CDN-Cache-Control': 'no-store, s-maxage=0',
                    'Cloudflare-CDN-Cache-Control': 'no-store',
                    Vary: 'Save-Data',
                    'Set-Cookie': 'session=leak',
                    'x-cld-error': 'should-be-stripped',
                },
            })
        )

        const webpRes = await worker.fetch(
            new Request('https://cloudinary-proxy.ryanpig228.workers.dev/w_320/v1792785423/ryan_travel/spot.jpg', {
                headers: { Accept: 'image/webp,*/*', Referer: 'https://www.tabijiapp.com/' },
            }),
            {},
            ctx
        )
        await Promise.all(waitPromises)

        expect(webpRes.status).toBe(200)
        expect(fetchSpy).toHaveBeenCalledWith(
            'https://res.cloudinary.com/dnpcnwrcu/image/upload/w_320,c_limit,f_webp,q_auto/v1792785423/ryan_travel/spot.jpg',
            expect.objectContaining({ method: 'GET' })
        )
        expect(webpRes.headers.get('Cache-Control')).toContain('immutable')
        expect(webpRes.headers.get('Access-Control-Allow-Origin')).toBe('*')
        expect(webpRes.headers.get('CDN-Cache-Control')).toBeNull()
        expect(webpRes.headers.get('Cloudflare-CDN-Cache-Control')).toBeNull()
        expect(webpRes.headers.get('Vary')).toBeNull()
        expect(webpRes.headers.get('Set-Cookie')).toBeNull()
        expect(webpRes.headers.get('x-cld-error')).toBeNull()
        expect(cachePutSpy).toHaveBeenCalledTimes(1)
        expect((cachePutSpy.mock.calls[0][0] as Request).url).toContain('?fmt=f_webp')

        // 2. AVIF request for same URL MUST NOT hit WebP cache entry (cache key isolated!)
        fetchSpy.mockResolvedValueOnce(
            new Response(new Uint8Array([4, 5, 6]), {
                status: 200,
                headers: { 'Content-Type': 'image/avif' },
            })
        )
        const avifRes = await worker.fetch(
            new Request('https://cloudinary-proxy.ryanpig228.workers.dev/w_320/v1792785423/ryan_travel/spot.jpg', {
                headers: { Accept: 'image/avif,image/webp,*/*' },
            }),
            {},
            ctx
        )
        await Promise.all(waitPromises)
        expect(avifRes.headers.get('Content-Type')).toBe('image/avif')
        expect(fetchSpy).toHaveBeenCalledTimes(2)
        expect(fetchSpy.mock.calls[1][0]).toContain('w_320,c_limit,f_avif,q_auto')
        expect((cachePutSpy.mock.calls[1][0] as Request).url).toContain('?fmt=f_avif')

        // 3. Upstream 404 MUST return Cache-Control: no-store, strip x-cld-error, and NEVER call cache.put
        cachePutSpy.mockClear()
        fetchSpy.mockResolvedValueOnce(
            new Response('Not Found', {
                status: 404,
                headers: { 'Content-Type': 'application/octet-stream', 'x-cld-error': 'Resource not found' },
            })
        )
        const notFoundRes = await worker.fetch(
            new Request('https://cloudinary-proxy.ryanpig228.workers.dev/w_320/v1/missing.jpg'),
            {},
            ctx
        )
        expect(notFoundRes.status).toBe(404)
        expect(notFoundRes.headers.get('Cache-Control')).toBe('no-store')
        expect(notFoundRes.headers.get('x-cld-error')).toBeNull()
        expect(cachePutSpy).not.toHaveBeenCalled()

        // 4. HEAD 200 MUST NOT call cache.put
        fetchSpy.mockResolvedValueOnce(
            new Response(null, { status: 200, headers: { 'Content-Type': 'image/webp' } })
        )
        const headRes = await worker.fetch(
            new Request('https://cloudinary-proxy.ryanpig228.workers.dev/w_320/v1/head_check.jpg', { method: 'HEAD' }),
            {},
            ctx
        )
        expect(headRes.status).toBe(200)
        expect(cachePutSpy).not.toHaveBeenCalled()
    })

    it('blocks upstream image/svg+xml (415 sandbox no-store, never cached), respects image/avif;q=0, strips expose/server-timing headers, and returns 502 no-store on network error', async () => {
        const ctx = { waitUntil: vi.fn((p: Promise<unknown>) => p) }

        // 1. prefersAvif respects q=0
        expect(prefersAvif('image/avif,image/webp,*/*')).toBe(true)
        expect(prefersAvif('image/avif;q=0, image/webp')).toBe(false)
        expect(prefersAvif('image/avif; q=0.0, image/webp')).toBe(false)

        // 2. Upstream 200 image/svg+xml & 200 text/html MUST be blocked with 415 sandbox no-store and NEVER cached
        fetchSpy.mockResolvedValueOnce(
            new Response('<svg onload="alert(1)"/>', {
                status: 200,
                headers: { 'Content-Type': 'image/svg+xml; charset=utf-8' },
            })
        )
        const svgRes = await worker.fetch(
            new Request('https://cloudinary-proxy.ryanpig228.workers.dev/w_320/v1/tabidachi_capsules/x.svg'),
            {},
            ctx
        )
        expect(svgRes.status).toBe(415)
        expect(svgRes.headers.get('Cache-Control')).toBe('no-store')
        expect(svgRes.headers.get('Content-Security-Policy')).toBe('sandbox')
        expect(cachePutSpy).not.toHaveBeenCalled()

        fetchSpy.mockResolvedValueOnce(
            new Response('<html><script>alert(1)</script></html>', {
                status: 200,
                headers: { 'Content-Type': 'text/html; charset=utf-8' },
            })
        )
        const htmlRes = await worker.fetch(
            new Request('https://cloudinary-proxy.ryanpig228.workers.dev/w_320/v1/tabidachi_capsules/x.jpg'),
            {},
            ctx
        )
        expect(htmlRes.status).toBe(415)
        expect(htmlRes.headers.get('Cache-Control')).toBe('no-store')
        expect(htmlRes.headers.get('Content-Security-Policy')).toBe('sandbox')
        expect(cachePutSpy).not.toHaveBeenCalled()

        // 3. Accept: image/avif;q=0, image/webp selects f_webp, sends canonical Accept, and strips expose/server-timing headers
        fetchSpy.mockResolvedValueOnce(
            new Response(new Uint8Array([9, 8, 7]), {
                status: 200,
                headers: {
                    'Content-Type': 'image/webp',
                    'Access-Control-Expose-Headers': 'X-Cld-Error,Server-Timing,Vary',
                    'Server-Timing': 'fastly;dur=10',
                },
            })
        )
        const q0Res = await worker.fetch(
            new Request('https://cloudinary-proxy.ryanpig228.workers.dev/w_640/v1/q0_check.jpg', {
                headers: { Accept: 'image/avif;q=0, image/webp' },
            }),
            {},
            ctx
        )
        expect(q0Res.status).toBe(200)
        expect(fetchSpy.mock.calls[2][0]).toContain('w_640,c_limit,f_webp,q_auto')
        expect((fetchSpy.mock.calls[2][1] as RequestInit).headers).toEqual({ Accept: 'image/webp,*/*' })
        expect(q0Res.headers.get('Access-Control-Expose-Headers')).toBeNull()
        expect(q0Res.headers.get('Server-Timing')).toBeNull()

        // 4. Upstream fetch network error returns 502 no-store cleanly
        fetchSpy.mockRejectedValueOnce(new TypeError('upstream unreachable'))
        const errRes = await worker.fetch(
            new Request('https://cloudinary-proxy.ryanpig228.workers.dev/w_320/v1/network_err.jpg'),
            {},
            ctx
        )
        expect(errRes.status).toBe(502)
        expect(errRes.headers.get('Cache-Control')).toBe('no-store')
    })
})
