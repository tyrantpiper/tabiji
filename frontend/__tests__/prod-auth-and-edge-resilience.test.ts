import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

function createMockJwt(payload: Record<string, unknown>): string {
    const b64url = (obj: Record<string, unknown>) =>
        Buffer.from(JSON.stringify(obj)).toString('base64url')
    return `${b64url({ alg: 'HS256', typ: 'JWT' })}.${b64url(payload)}.sig`
}

async function signRealHs256Jwt(payload: Record<string, unknown>, secret: string): Promise<string> {
    const b64url = (input: Uint8Array | string) => {
        const buf = typeof input === 'string' ? Buffer.from(input, 'utf8') : Buffer.from(input)
        return buf.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '')
    }
    const header = b64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
    const body = b64url(JSON.stringify(payload))
    const enc = new TextEncoder()
    const key = await crypto.subtle.importKey(
        'raw',
        enc.encode(secret),
        { name: 'HMAC', hash: 'SHA-256' },
        false,
        ['sign']
    )
    const sig = await crypto.subtle.sign('HMAC', key, enc.encode(`${header}.${body}`))
    return `${header}.${body}.${b64url(new Uint8Array(sig))}`
}

function loadWorkerModule(relPath: string): { fetch: (req: Request, env: Record<string, unknown>, ctx: unknown) => Promise<Response> } {
    const fullPath = path.resolve(__dirname, '..', '..', relPath)
    const raw = fs.readFileSync(fullPath, 'utf8')
    const transformed = raw.replace(/export default\s*\{/, 'module.exports = {')
    const mod: { exports: { fetch?: (req: Request, env: Record<string, unknown>, ctx: unknown) => Promise<Response> } } = { exports: {} }
    const sandbox = {
        module: mod,
        exports: mod.exports,
        Request,
        Response,
        Headers,
        URL,
        crypto,
        TextEncoder,
        Uint8Array,
        atob,
        btoa,
        console,
        fetch: (...args: Parameters<typeof globalThis.fetch>) => globalThis.fetch(...args),
    }
    vm.runInNewContext(transformed, sandbox, { filename: fullPath })
    if (!mod.exports.fetch) {
        throw new Error(`Worker ${relPath} did not export default.fetch`)
    }
    return mod.exports as { fetch: (req: Request, env: Record<string, unknown>, ctx: unknown) => Promise<Response> }
}

describe('🛡️ Production Auth Storm, POI Isolation, Cloudinary Gate & Edge Worker Hardening', () => {
    let mockStorage: Record<string, string> = {}
    const originalFetch = globalThis.fetch
    const originalEnv = { ...process.env }

    beforeEach(() => {
        mockStorage = {}
        vi.stubGlobal('localStorage', {
            getItem: (key: string) => (key in mockStorage ? mockStorage[key] : null),
            setItem: (key: string, val: string) => { mockStorage[key] = String(val) },
            removeItem: (key: string) => { delete mockStorage[key] },
            clear: () => { mockStorage = {} },
            key: (i: number) => Object.keys(mockStorage)[i] || null,
            get length() { return Object.keys(mockStorage).length },
        })
        Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    })

    afterEach(() => {
        vi.useRealTimers()
        vi.restoreAllMocks()
        globalThis.fetch = originalFetch
        process.env = { ...originalEnv }
        vi.unstubAllGlobals()
    })

    it('F1: Suppresses SWR >15s polling 401 storms on unchanged failed credentials, while allowing retry after 5xx', async () => {
        vi.useFakeTimers()
        vi.setSystemTime(new Date('2026-11-18T14:00:00Z'))
        const { ensureValidSession, __resetExchangeFailedForTesting } = await import('@/lib/auth-session')
        __resetExchangeFailedForTesting()
        process.env.TEST_AUTH_EXCHANGE = 'true'

        const uid = '3f7abf22-b447-4281-b240-584549c79943'
        mockStorage['user_uuid'] = uid
        mockStorage['user_nickname'] = 'Ryan'

        // Transient 503 must NOT permanently latch
        const fetchMock = vi.fn()
            .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Service Unavailable' }), { status: 503 }))
            .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Account already upgraded. Please use your modern recovery key (tbj_rec_*).' }), { status: 401 }))
        globalThis.fetch = fetchMock as unknown as typeof fetch

        expect(await ensureValidSession()).toBeNull()
        expect(fetchMock).toHaveBeenCalledTimes(1)

        // Second attempt after transient 503 proceeds and hits 401
        expect(await ensureValidSession()).toBeNull()
        expect(fetchMock).toHaveBeenCalledTimes(2)

        // Advance past old 10s cooldown & SWR 15s cycle -> unchanged credential fingerprint MUST remain latched (0 extra calls)
        vi.advanceTimersByTime(25_000)
        expect(await ensureValidSession()).toBeNull()
        expect(await ensureValidSession(true)).toBeNull()
        vi.advanceTimersByTime(60_000)
        expect(await ensureValidSession()).toBeNull()
        expect(fetchMock).toHaveBeenCalledTimes(2)
    })

    it('F2: In-memory dismissReauthPrompt silences modal across >5s / >30s SWR cycles until explicit reanchor/reset', async () => {
        vi.useFakeTimers()
        vi.setSystemTime(new Date('2026-11-18T14:00:00Z'))
        const {
            triggerReauthPrompt,
            dismissReauthPrompt,
            reanchorSessionWithKey,
            __resetExchangeFailedForTesting,
        } = await import('@/lib/auth-session')
        __resetExchangeFailedForTesting()

        mockStorage['user_uuid'] = '3f7abf22-b447-4281-b240-584549c79943'
        mockStorage['user_nickname'] = 'Ryan'

        const received: Array<string | undefined> = []
        const listener = (e: Event) => {
            received.push((e as CustomEvent<{ reason?: string }>).detail?.reason)
        }
        window.addEventListener('tabiji:session_reauth_required', listener)
        try {
            triggerReauthPrompt('Account already upgraded.')
            expect(received).toHaveLength(1)

            dismissReauthPrompt()
            vi.advanceTimersByTime(6_000)
            triggerReauthPrompt('static overwrite should stay silenced')
            vi.advanceTimersByTime(45_000)
            triggerReauthPrompt('still dismissed in memory')
            expect(received).toHaveLength(1)

            // Re-anchoring clears in-memory dismissal + failure latches
            const freshJwt = createMockJwt({ sub: mockStorage['user_uuid'], exp: Math.floor(Date.now() / 1000) + 3600 })
            globalThis.fetch = vi.fn().mockResolvedValueOnce(
                new Response(JSON.stringify({ access_token: freshJwt, user_id: mockStorage['user_uuid'] }), { status: 200 })
            ) as unknown as typeof fetch

            const validKey = 'tbj_rec_12345678_0123456789abcdef0123456789abcdef'
            await reanchorSessionWithKey(validKey)
            vi.advanceTimersByTime(6_000)
            triggerReauthPrompt('Post-reanchor future genuine prompt')
            expect(received).toHaveLength(2)
        } finally {
            window.removeEventListener('tabiji:session_reauth_required', listener)
        }
    })

    it('F3: Preserves server 401 error detail and transmits expected_user_id in ensureValidSession', async () => {
        const { __resetExchangeFailedForTesting, getLastAuthExchangeError } = await import('@/lib/auth-session')
        const { fetcherWithUserId } = await import('@/lib/hooks')
        __resetExchangeFailedForTesting()
        process.env.TEST_AUTH_EXCHANGE = 'true'

        const uid = '3f7abf22-b447-4281-b240-584549c79943'
        const serverDetail = 'Credential has been rotated. This session is revoked.'
        const staleJwt = createMockJwt({ sub: uid, exp: Math.floor(Date.now() / 1000) + 3600 })
        mockStorage['user_uuid'] = uid
        mockStorage['user_nickname'] = 'Ryan'
        mockStorage['tabiji_session_token'] = staleJwt

        let capturedBody: Record<string, unknown> = {}
        globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
            const url = typeof input === 'string' ? input : input.toString()
            if (url.includes('/api/auth/session')) {
                capturedBody = JSON.parse(String(init?.body || '{}'))
                return new Response(JSON.stringify({ detail: serverDetail }), { status: 401 })
            }
            return new Response(JSON.stringify({ detail: 'Invalid token' }), { status: 401 })
        }) as unknown as typeof fetch

        const reasons: Array<string | undefined> = []
        const listener = (e: Event) => reasons.push((e as CustomEvent<{ reason?: string }>).detail?.reason)
        window.addEventListener('tabiji:session_reauth_required', listener)
        try {
            await expect(fetcherWithUserId(['/api/trips', uid])).rejects.toThrow()
            expect(capturedBody.expected_user_id).toBe(uid)
            expect(getLastAuthExchangeError()).toBe(serverDetail)
            expect(reasons).toEqual([serverDetail])
        } finally {
            window.removeEventListener('tabiji:session_reauth_required', listener)
        }
    })

    it('F4: apiFetch retries /api/poi/* once on 401 when session refreshes, but isolates session token & modal on POI refresh failure', async () => {
        const { __resetExchangeFailedForTesting } = await import('@/lib/auth-session')
        const { poiApi } = await import('@/lib/api')
        __resetExchangeFailedForTesting()
        process.env.TEST_AUTH_EXCHANGE = 'true'

        const uid = '3f7abf22-b447-4281-b240-584549c79943'
        const futureExp = Math.floor(Date.now() / 1000) + 3600
        const staleJwt = createMockJwt({ sub: uid, exp: futureExp })
        const freshJwt = createMockJwt({ sub: uid, exp: futureExp + 3600 })
        mockStorage['user_uuid'] = uid
        mockStorage['user_nickname'] = 'Ryan'
        mockStorage['user_recovery_key'] = 'tbj_rec_deadbeef_0123456789abcdef0123456789abcdef'
        mockStorage['tabiji_session_token'] = staleJwt

        // Case 1: /api/poi/nearby gets 401 -> refreshes token -> retries once and succeeds!
        globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
            const url = typeof input === 'string' ? input : input.toString()
            const auth = new Headers(init?.headers).get('Authorization')
            if (url.includes('/api/auth/session')) {
                return new Response(JSON.stringify({ access_token: freshJwt, user_id: uid }), { status: 200 })
            }
            if (auth === `Bearer ${staleJwt}`) {
                return new Response(JSON.stringify({ error: 'UNAUTHORIZED' }), { status: 401 })
            }
            return new Response(JSON.stringify({ results: [{ id: 'poi_1' }] }), { status: 200 })
        }) as unknown as typeof fetch

        const nearby = await poiApi.nearby(35.68, 139.76, 'food', uid)
        expect(nearby.results).toHaveLength(1)
        expect(mockStorage['tabiji_session_token']).toBe(freshJwt)

        // Case 2: If session refresh fails (503) or remote D1 Edge Shield still returns 401 after refresh,
        // /api/poi/* MUST preserve tabiji_session_token and MUST NOT pop SessionReauthModal!
        __resetExchangeFailedForTesting()
        let modalTriggered = false
        const listener = () => { modalTriggered = true }
        window.addEventListener('tabiji:session_reauth_required', listener)
        try {
            globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
                const url = typeof input === 'string' ? input : input.toString()
                if (url.includes('/api/auth/session')) {
                    return new Response(JSON.stringify({ detail: 'Transient unavailable' }), { status: 503 })
                }
                return new Response(JSON.stringify({ error: 'UNAUTHORIZED' }), { status: 401 })
            }) as unknown as typeof fetch
            await expect(poiApi.nearby(35.68, 139.76, 'food', uid)).rejects.toThrow()
            expect(modalTriggered).toBe(false)
            expect(mockStorage['tabiji_session_token']).toBe(freshJwt)

            // Also verify remote 401 after local 200 refresh does not purge token or pop modal
            const freshJwt2 = createMockJwt({ sub: uid, exp: futureExp + 7200 })
            globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
                const url = typeof input === 'string' ? input : input.toString()
                if (url.includes('/api/auth/session')) {
                    return new Response(JSON.stringify({ access_token: freshJwt2, user_id: uid }), { status: 200 })
                }
                return new Response(JSON.stringify({ error: 'UNAUTHORIZED' }), { status: 401 })
            }) as unknown as typeof fetch
            await expect(poiApi.nearby(35.68, 139.76, 'food', uid)).rejects.toThrow()
            expect(modalTriggered).toBe(false)
            expect(mockStorage['tabiji_session_token']).toBe(freshJwt2)
        } finally {
            window.removeEventListener('tabiji:session_reauth_required', listener)
        }
    })

    it('F5: /api/cloudinary-test strictly fails closed with 404 in production and leaks zero secret prefix/suffix', async () => {
        vi.stubEnv('NODE_ENV', 'production')
        vi.stubEnv('CLOUDINARY_API_SECRET', 'super_secret_should_never_leak_1234')
        vi.stubEnv('NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME', 'demo')
        vi.stubEnv('NEXT_PUBLIC_CLOUDINARY_API_KEY', '9961000000')
        vi.stubEnv('ENABLE_CLOUDINARY_TEST_ROUTE', '')

        const { GET } = await import('@/app/api/cloudinary-test/route')
        const res = await GET()
        expect(res.status).toBe(404)
        const text = await res.text()
        expect(text).not.toContain('apiSecretFirst4')
        expect(text).not.toContain('supe')
        expect(text).not.toContain('1234')

        // Benign local dev diagnostic when explicitly enabled in non-prod
        vi.stubEnv('NODE_ENV', 'development')
        vi.stubEnv('ENABLE_CLOUDINARY_TEST_ROUTE', 'true')
        const devRes = await GET()
        expect(devRes.status).toBe(200)
        const devJson = await devRes.json()
        expect(devJson.apiSecretConfigured).toBe(true)
        expect(devJson.apiSecretFirst4).toBeUndefined()
        expect(devJson.apiSecretLast4).toBeUndefined()
        expect(devJson.apiSecretLength).toBeUndefined()
    })

    it('F6: Cloudflare Edge Shield & POI Service reject workers.dev bypass, strip fallback Authorization, and verify real HS256 JWTs', async () => {
        const edgeShield = loadWorkerModule('cloudflare/edge-shield/worker.js')
        const poiService = loadWorkerModule('cloudflare/poi-service/worker.js')

        // 0. Check wrangler.jsonc disables workers_dev and preview_urls
        const wranglerRaw = fs.readFileSync(path.resolve(__dirname, '../../cloudflare/poi-service/wrangler.jsonc'), 'utf8')
        const wranglerJson = JSON.parse(wranglerRaw)
        expect(wranglerJson.workers_dev).toBe(false)
        expect(wranglerJson.preview_urls).toBe(false)

        // 1. Direct workers.dev ingress to poi-service MUST return 403
        const directRes = await poiService.fetch(
            new Request('https://tabijiapp-poi-service.ryanpig228.workers.dev/api/poi/all', {
                headers: { 'X-User-ID': '3f7abf22-b447-4281-b240-584549c79943' },
            }),
            { DB: { prepare: () => ({ bind: () => ({ all: async () => ({ results: [{ id: 'secret' }] }) }) }) } },
            {}
        )
        expect(directRes.status).toBe(403)

        // 2. Unverified base64 JWT without X-User-ID or SESSION_SECRET MUST fail 401
        const spoofedJwt = createMockJwt({ sub: '3f7abf22-b447-4281-b240-584549c79943' })
        const unverifiedJwtRes = await poiService.fetch(
            new Request('https://www.tabijiapp.com/api/poi/all', {
                headers: { Authorization: `Bearer ${spoofedJwt}` },
            }),
            { DB: { prepare: () => ({ bind: () => ({ all: async () => ({ results: [] }) }) }) } },
            {}
        )
        expect(unverifiedJwtRes.status).toBe(401)

        // 3. Edge Shield fallback (SESSION_SECRET unset) strips BOTH X-User-ID and Authorization
        let forwardedHeaders: Headers | null = null
        await edgeShield.fetch(
            new Request('https://www.tabijiapp.com/api/poi/all', {
                headers: {
                    'X-User-ID': '3f7abf22-b447-4281-b240-584549c79943',
                    Authorization: `Bearer ${spoofedJwt}`,
                },
            }),
            {
                POI_SERVICE: {
                    fetch: async (req: Request) => {
                        forwardedHeaders = req.headers
                        return await poiService.fetch(
                            req,
                            { DB: { prepare: () => ({ bind: () => ({ all: async () => ({ results: [] }) }) }) } },
                            {}
                        )
                    },
                },
            },
            {}
        )
        expect(forwardedHeaders).not.toBeNull()
        expect(forwardedHeaders!.has('X-User-ID')).toBe(false)
        expect(forwardedHeaders!.has('Authorization')).toBe(false)

        // 4. Signed HS256 JWT through Edge Shield + Service Binding POI Service -> 200 for legitimate user
        const secret = 'cloudflare-edge-shield-prod-secret-2026'
        const validUid = '3f7abf22-b447-4281-b240-584549c79943'
        const signedJwt = await signRealHs256Jwt(
            { sub: validUid, iss: 'tabiji-core', exp: Math.floor(Date.now() / 1000) + 3600 },
            secret
        )
        const okRes = await edgeShield.fetch(
            new Request('https://www.tabijiapp.com/api/poi/all', {
                headers: {
                    Authorization: `Bearer ${signedJwt}`,
                    'X-User-ID': 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', // attempt spoofing
                },
            }),
            {
                SESSION_SECRET: secret,
                POI_SERVICE: {
                    fetch: async (req: Request) => {
                        expect(req.headers.get('X-User-ID')).toBe(validUid)
                        return await poiService.fetch(
                            req,
                            {
                                DB: {
                                    prepare: () => ({
                                        bind: (qUid: string) => {
                                            expect(qUid).toBe(validUid)
                                            return { all: async () => ({ results: [{ id: 'poi_1', user_id: validUid }] }) }
                                        },
                                    }),
                                },
                            },
                            {}
                        )
                    },
                },
            },
            {}
        )
        expect(okRes.status).toBe(200)
        expect(await okRes.json()).toEqual([{ id: 'poi_1', user_id: validUid }])

        // 5. exp: 0 or missing exp MUST be rejected with 401 by both Edge Shield & POI Service
        const zeroExpJwt = await signRealHs256Jwt({ sub: validUid, iss: 'tabiji-core', exp: 0 }, secret)
        const zeroExpShieldRes = await edgeShield.fetch(
            new Request('https://www.tabijiapp.com/api/poi/all', {
                headers: { Authorization: `Bearer ${zeroExpJwt}` },
            }),
            {
                SESSION_SECRET: secret,
                POI_SERVICE: { fetch: async () => new Response('[]', { status: 200 }) },
            },
            {}
        )
        expect(zeroExpShieldRes.status).toBe(401)

        const zeroExpPoiRes = await poiService.fetch(
            new Request('https://www.tabijiapp.com/api/poi/all', {
                headers: { Authorization: `Bearer ${zeroExpJwt}` },
            }),
            {
                SESSION_SECRET: secret,
                DB: { prepare: () => ({ bind: () => ({ all: async () => ({ results: [] }) }) }) },
            },
            {}
        )
        expect(zeroExpPoiRes.status).toBe(401)
    })

    it('F7: Transient 503/offline during ensureValidSession(true) preserves backedUpValidToken across fetcherWithUserId, apiFetch, and streamChat without false modal', async () => {
        const { __resetExchangeFailedForTesting, wasLastAuthExchangeTransientFailure } = await import('@/lib/auth-session')
        const { fetcherWithUserId } = await import('@/lib/hooks')
        const { usersApi } = await import('@/lib/api')
        const { streamChat } = await import('@/lib/sse-parser')
        __resetExchangeFailedForTesting()
        process.env.TEST_AUTH_EXCHANGE = 'true'

        const uid = '3f7abf22-b447-4281-b240-584549c79943'
        const validJwt = createMockJwt({ sub: uid, exp: Math.floor(Date.now() / 1000) + 3600 })
        mockStorage['user_uuid'] = uid
        mockStorage['user_nickname'] = 'Ryan'
        mockStorage['user_recovery_key'] = 'tbj_rec_deadbeef_0123456789abcdef0123456789abcdef'
        mockStorage['tabiji_session_token'] = validJwt

        let reauthEvents = 0
        const listener = () => { reauthEvents += 1 }
        window.addEventListener('tabiji:session_reauth_required', listener)
        try {
            globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
                const url = typeof input === 'string' ? input : input.toString()
                if (url.includes('/api/auth/session')) {
                    return new Response(JSON.stringify({ detail: 'Service Unavailable' }), { status: 503 })
                }
                return new Response(JSON.stringify({ detail: 'Transient backend edge mismatch' }), { status: 401 })
            }) as unknown as typeof fetch

            await expect(fetcherWithUserId(['/api/trips', uid])).rejects.toThrow()
            expect(wasLastAuthExchangeTransientFailure()).toBe(true)
            expect(mockStorage['tabiji_session_token']).toBe(validJwt)
            expect(reauthEvents).toBe(0)

            await expect(usersApi.getProfile(uid)).rejects.toThrow()
            expect(wasLastAuthExchangeTransientFailure()).toBe(true)
            expect(mockStorage['tabiji_session_token']).toBe(validJwt)
            expect(reauthEvents).toBe(0)

            await expect(streamChat('http://127.0.0.1:8008', 'hi', [], 'AIzaSyGoodKey123456789012345678901234', {})).rejects.toThrow()
            expect(wasLastAuthExchangeTransientFailure()).toBe(true)
            expect(mockStorage['tabiji_session_token']).toBe(validJwt)
            expect(reauthEvents).toBe(0)
        } finally {
            window.removeEventListener('tabiji:session_reauth_required', listener)
        }
    })

    it('F8: Next.js /api/poi/[...path] passes through upstream 401 on GET /api/poi/all instead of swallowing to [] and poisoning IDB cache', async () => {
        const { NextRequest } = await import('next/server')
        const { GET } = await import('@/app/api/poi/[...path]/route')

        globalThis.fetch = vi.fn().mockResolvedValueOnce(
            new Response(JSON.stringify({ error: 'UNAUTHORIZED' }), {
                status: 401,
                headers: { 'Content-Type': 'application/json' },
            })
        ) as unknown as typeof fetch

        const req = new NextRequest('https://travel-pwa-five.vercel.app/api/poi/all', {
            method: 'GET',
            headers: { Authorization: 'Bearer stale-jwt' },
        })
        const res = await GET(req, { params: Promise.resolve({ path: ['all'] }) })
        expect(res.status).toBe(401)
    })

    it('F9: /api/sign-cloudinary enforces mandatory folder whitelist, path traversal guard, and parameter allowlist', async () => {
        vi.stubEnv('CLOUDINARY_API_SECRET', 'cloudinary_test_secret_1234567890abcdef')
        const { POST } = await import('@/app/api/sign-cloudinary/route')

        const postSign = (body: unknown) =>
            POST(new Request('https://travel-pwa-five.vercel.app/api/sign-cloudinary', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            }))

        // Missing folder -> 400
        expect((await postSign({ paramsToSign: { timestamp: 1700000000 } })).status).toBe(400)
        // Path traversal -> 400
        expect((await postSign({ paramsToSign: { timestamp: 1700000000, folder: 'ryan_travel/../evil' } })).status).toBe(400)
        // Disallowed folder -> 400
        expect((await postSign({ paramsToSign: { timestamp: 1700000000, folder: 'attacker_bucket' } })).status).toBe(400)
        // Extra unauthorized parameter (overwrite) -> 400
        expect((await postSign({ paramsToSign: { timestamp: 1700000000, folder: 'ryan_travel/covers', overwrite: true } })).status).toBe(400)

        // Legitimate folders + optional public_id -> 200
        const ok1 = await postSign({ paramsToSign: { timestamp: 1700000000, folder: 'tabidachi_capsules' } })
        expect(ok1.status).toBe(200)
        expect((await ok1.json()).signature).toBeTruthy()

        const ok2 = await postSign({ paramsToSign: { timestamp: 1700000000, folder: 'ryan_travel/streetview', public_id: 'mly_12345' } })
        expect(ok2.status).toBe(200)
        expect((await ok2.json()).signature).toBeTruthy()
    })

    it('F10: Stale concurrent ensureValidSession 401 resolving after reanchorSessionWithKey does not overwrite restored state', async () => {
        const {
            ensureValidSession,
            reanchorSessionWithKey,
            getLastAuthExchangeError,
            wasLastAuthExchangeTransientFailure,
            __resetExchangeFailedForTesting,
        } = await import('@/lib/auth-session')
        __resetExchangeFailedForTesting()
        process.env.TEST_AUTH_EXCHANGE = 'true'

        const uid = '3f7abf22-b447-4281-b240-584549c79943'
        mockStorage['user_uuid'] = uid
        mockStorage['user_nickname'] = 'Ryan'

        let resolveStaleFetch!: (res: Response) => void
        const staleFetchPromise = new Promise<Response>((resolve) => {
            resolveStaleFetch = resolve
        })
        const freshJwt = createMockJwt({ sub: uid, exp: Math.floor(Date.now() / 1000) + 3600 })
        const validNewKey = 'tbj_rec_12345678_0123456789abcdef0123456789abcdef'

        globalThis.fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
            const url = typeof input === 'string' ? input : input.toString()
            const parsedBody = JSON.parse(String(init?.body || '{}'))
            if (url.includes('/api/auth/session') && parsedBody.recovery_key === validNewKey) {
                return Promise.resolve(new Response(JSON.stringify({ access_token: freshJwt, user_id: uid }), { status: 200 }))
            }
            return staleFetchPromise
        }) as unknown as typeof fetch

        const pendingStale = ensureValidSession()
        await reanchorSessionWithKey(validNewKey)

        // Now stale in-flight exchange resolves with 401 -> MUST NOT overwrite new token or set error latches!
        resolveStaleFetch(new Response(JSON.stringify({ detail: 'Account already upgraded.' }), { status: 401 }))
        const staleResult = await pendingStale
        expect(staleResult).toBe(freshJwt)
        expect(mockStorage['tabiji_session_token']).toBe(freshJwt)
        expect(getLastAuthExchangeError()).toBeNull()
        expect(wasLastAuthExchangeTransientFailure()).toBe(false)
    })

    it('F11: Suppresses unchanged failed credential within <10s, but unlocks immediately and preserves backedUpValidToken when fingerprint changes within <10s', async () => {
        vi.useFakeTimers()
        vi.setSystemTime(new Date('2026-11-18T15:00:00Z'))
        const {
            ensureValidSession,
            wasLastAuthExchangeTransientFailure,
            __resetExchangeFailedForTesting,
        } = await import('@/lib/auth-session')
        const { fetcherWithUserId } = await import('@/lib/hooks')
        __resetExchangeFailedForTesting()
        process.env.TEST_AUTH_EXCHANGE = 'true'

        const uid = '3f7abf22-b447-4281-b240-584549c79943'
        const oldKey = 'tbj_rec_11111111_0123456789abcdef0123456789abcdef'
        const newKey = 'tbj_rec_22222222_fedcba9876543210fedcba9876543210'
        const futureExp = Math.floor(Date.now() / 1000) + 3600
        const crossTabValidJwt = createMockJwt({ sub: uid, exp: futureExp })
        const freshJwt2 = createMockJwt({ sub: uid, exp: futureExp + 3600 })

        mockStorage['user_uuid'] = uid
        mockStorage['user_nickname'] = 'Ryan'
        mockStorage['user_recovery_key'] = oldKey

        let reauthEvents = 0
        const listener = () => { reauthEvents += 1 }
        window.addEventListener('tabiji:session_reauth_required', listener)
        try {
            // 1. Initial 401 failure latches oldKey fingerprint at t=0
            const initialFetch = vi.fn().mockResolvedValueOnce(
                new Response(JSON.stringify({ detail: '引繼碼驗證失敗，無法在此設備恢復同步。請確認引繼碼是否正確。' }), { status: 401 })
            )
            globalThis.fetch = initialFetch as unknown as typeof fetch

            expect(await ensureValidSession()).toBeNull()
            expect(initialFetch).toHaveBeenCalledTimes(1)
            expect(reauthEvents).toBe(1)

            // 2. Within <10s (t = +2000ms), unchanged credential remains suppressed (0 extra fetch calls)
            vi.advanceTimersByTime(2_000)
            const unchangedFetch = vi.fn()
            globalThis.fetch = unchangedFetch as unknown as typeof fetch
            expect(await ensureValidSession()).toBeNull()
            expect(await ensureValidSession(true)).toBeNull()
            expect(unchangedFetch).not.toHaveBeenCalled()

            // 3. Still within <10s (t = +3000ms), cross-tab localStorage sync updates recovery key & valid token!
            // An older in-flight API call gets 401 and invokes fetcherWithUserId -> ensureValidSession(true)
            // while /api/auth/session transiently returns 503.
            vi.advanceTimersByTime(1_000)
            mockStorage['user_recovery_key'] = newKey
            mockStorage['tabiji_session_token'] = crossTabValidJwt

            let sessionCallsOn503 = 0
            globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
                const url = typeof input === 'string' ? input : input.toString()
                if (url.includes('/api/auth/session')) {
                    sessionCallsOn503 += 1
                    const body = JSON.parse(String(init?.body || '{}'))
                    expect(body.recovery_key).toBe(newKey)
                    expect(new Headers(init?.headers).get('Authorization')).toBe(`Bearer ${crossTabValidJwt}`)
                    return new Response(JSON.stringify({ detail: 'Service Unavailable' }), { status: 503 })
                }
                return new Response(JSON.stringify({ detail: 'Stale request 401' }), { status: 401 })
            }) as unknown as typeof fetch

            await expect(fetcherWithUserId(['/api/trips', uid])).rejects.toThrow()
            // MUST NOT be blocked by old 10s cooldown: session exchange MUST execute immediately
            expect(sessionCallsOn503).toBe(1)
            // MUST restore backedUpValidToken and mark transient failure so token isn't dropped & modal isn't popped
            expect(wasLastAuthExchangeTransientFailure()).toBe(true)
            expect(mockStorage['tabiji_session_token']).toBe(crossTabValidJwt)
            expect(reauthEvents).toBe(1)

            // 4. Still within <10s (t = +4000ms), backend recovers and returns 200 -> silent upgrade succeeds
            vi.advanceTimersByTime(1_000)
            globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
                const url = typeof input === 'string' ? input : input.toString()
                const auth = new Headers(init?.headers).get('Authorization')
                if (url.includes('/api/auth/session')) {
                    return new Response(JSON.stringify({ access_token: freshJwt2, user_id: uid, recovery_key: newKey }), { status: 200 })
                }
                if (auth === `Bearer ${crossTabValidJwt}`) {
                    return new Response(JSON.stringify({ detail: 'Needs fresh token' }), { status: 401 })
                }
                return new Response(JSON.stringify([{ id: 'trip-ok' }]), { status: 200 })
            }) as unknown as typeof fetch

            const trips = await fetcherWithUserId(['/api/trips', uid])
            expect(trips).toEqual([{ id: 'trip-ok' }])
            expect(mockStorage['tabiji_session_token']).toBe(freshJwt2)
            expect(reauthEvents).toBe(1)

            // 5. Mid-flight key change (without token written yet) during transient 503 preserves backedUpValidToken
            let resolve503!: (res: Response) => void
            const pending503 = new Promise<Response>((resolve) => { resolve503 = resolve })
            globalThis.fetch = vi.fn(() => pending503) as unknown as typeof fetch
            const validJwtBeforeRace = freshJwt2
            mockStorage['tabiji_session_token'] = validJwtBeforeRace
            const refreshPromise = ensureValidSession(true)
            mockStorage['user_recovery_key'] = 'tbj_rec_33333333_0123456789abcdef0123456789abcdef'
            resolve503(new Response(JSON.stringify({ detail: 'Transient 503' }), { status: 503 }))
            await refreshPromise
            expect(wasLastAuthExchangeTransientFailure()).toBe(true)
            expect(mockStorage['tabiji_session_token']).toBe(validJwtBeforeRace)
        } finally {
            window.removeEventListener('tabiji:session_reauth_required', listener)
        }
    })

    it('F12: Edge Shield passes backend POI routes (/categories, /nearby, /media-proxy) through to Cloud Run instead of hijacking to POI_SERVICE', async () => {
        const edgeShield = loadWorkerModule('cloudflare/edge-shield/worker.js')
        const secret = 'cloudflare-edge-shield-prod-secret-2026'
        let poiServiceCalls = 0
        const backendUrls: string[] = []

        globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
            const url = typeof input === 'string' ? input : input.toString()
            backendUrls.push(url)
            return new Response(JSON.stringify({ upstream: 'cloud-run', url }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            })
        }) as unknown as typeof fetch

        const env = {
            SESSION_SECRET: secret,
            POI_SERVICE: {
                fetch: async (req: Request) => {
                    poiServiceCalls += 1
                    return new Response(JSON.stringify({ ok: true, path: new URL(req.url).pathname }), { status: 200 })
                },
            },
        }

        // 1. Backend GET POI endpoints MUST go to Cloud Run without POI JWT gate
        for (const pathUrl of [
            'https://www.tabijiapp.com/api/poi/categories',
            'https://www.tabijiapp.com/api/poi/nearby?lat=35.6812&lng=139.7671&category=restaurant',
            'https://www.tabijiapp.com/api/poi/media-proxy?url=https%3A%2F%2Fexample.com%2Fa.jpg',
        ]) {
            const res = await edgeShield.fetch(new Request(pathUrl, { method: 'GET' }), env, {})
            expect(res.status).toBe(200)
        }
        expect(poiServiceCalls).toBe(0)
        expect(backendUrls).toHaveLength(3)

        // 2. D1 POI pool PATCH / DELETE routes still route to POI_SERVICE with valid HS256 JWT
        const validUid = '3f7abf22-b447-4281-b240-584549c79943'
        const validJwt = await signRealHs256Jwt({ sub: validUid, iss: 'tabiji-core', exp: Math.floor(Date.now() / 1000) + 3600 }, secret)
        const patchRes = await edgeShield.fetch(
            new Request('https://www.tabijiapp.com/api/poi/poi_123/category', {
                method: 'PATCH',
                headers: { Authorization: `Bearer ${validJwt}` },
                body: JSON.stringify({ category: 'food' }),
            }),
            env,
            {}
        )
        expect(patchRes.status).toBe(200)
        expect(poiServiceCalls).toBe(1)

        // 3. Signed JWT with non-UUID sub is rejected 401 by Edge Shield
        const nonUuidJwt = await signRealHs256Jwt({ sub: 'not-a-uuid', iss: 'tabiji-core', exp: Math.floor(Date.now() / 1000) + 3600 }, secret)
        const badSubRes = await edgeShield.fetch(
            new Request('https://www.tabijiapp.com/api/poi/all', {
                headers: { Authorization: `Bearer ${nonUuidJwt}` },
            }),
            env,
            {}
        )
        expect(badSubRes.status).toBe(401)
    })

    it('F13: Concurrent stale ensureValidSession(false) + credential rotation/reanchor + ensureValidSession(true) does not wipe new token or skip new exchange', async () => {
        const {
            ensureValidSession,
            reanchorSessionWithKey,
            wasLastAuthExchangeTransientFailure,
            __resetExchangeFailedForTesting,
        } = await import('@/lib/auth-session')
        const { fetcherWithUserId } = await import('@/lib/hooks')
        __resetExchangeFailedForTesting()
        process.env.TEST_AUTH_EXCHANGE = 'true'

        const uid = '3f7abf22-b447-4281-b240-584549c79943'
        const newKey = 'tbj_rec_44444444_0123456789abcdef0123456789abcdef'
        const futureExp = Math.floor(Date.now() / 1000) + 3600
        const reanchoredJwt = createMockJwt({ sub: uid, exp: futureExp })
        const refreshedJwt = createMockJwt({ sub: uid, exp: futureExp + 7200 })

        mockStorage['user_uuid'] = uid
        mockStorage['user_nickname'] = 'Ryan'

        let resolveStale!: (res: Response) => void
        const stalePending = new Promise<Response>((resolve) => { resolveStale = resolve })
        let reanchorCalls = 0
        let modalTriggered = 0
        const listener = () => { modalTriggered += 1 }
        window.addEventListener('tabiji:session_reauth_required', listener)
        try {
            globalThis.fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
                const url = typeof input === 'string' ? input : input.toString()
                const body = JSON.parse(String(init?.body || '{}'))
                if (url.includes('/api/auth/session') && body.recovery_key === newKey) {
                    reanchorCalls += 1
                    if (reanchorCalls === 1) {
                        return Promise.resolve(new Response(JSON.stringify({ access_token: reanchoredJwt, user_id: uid }), { status: 200 }))
                    }
                    // Subsequent forceRefresh from old 401 hits transient 503
                    return Promise.resolve(new Response(JSON.stringify({ detail: 'Transient 503' }), { status: 503 }))
                }
                if (url.includes('/api/auth/session')) {
                    return stalePending
                }
                return Promise.resolve(new Response(JSON.stringify({ detail: 'Old request 401' }), { status: 401 }))
            }) as unknown as typeof fetch

            // 1. Stale exchange (fingerprint A, no key) starts and remains in flight
            const stalePromise = ensureValidSession()
            // 2. User re-anchors with newKey -> writes reanchoredJwt (fingerprint B)
            await reanchorSessionWithKey(newKey)
            expect(mockStorage['tabiji_session_token']).toBe(reanchoredJwt)

            // 3. Before stalePromise finishes, an old 401 triggers ensureValidSession(true) while /api/auth/session transiently returns 503
            const refreshDuringRace = await ensureValidSession(true)
            expect(refreshDuringRace).toBeNull()
            // MUST have attempted exchange for newKey (not joined stale A), MUST preserve reanchoredJwt, MUST mark transient failure!
            expect(reanchorCalls).toBe(2)
            expect(wasLastAuthExchangeTransientFailure()).toBe(true)
            expect(mockStorage['tabiji_session_token']).toBe(reanchoredJwt)

            // 4. Calling getCachedToken fast-path ensureValidSession() MUST NOT clobber lastExchangeTransientFailure!
            expect(await ensureValidSession()).toBe(reanchoredJwt)
            expect(wasLastAuthExchangeTransientFailure()).toBe(true)

            // 5. Now stalePromise settles with 401 -> MUST NOT wipe reanchoredJwt or pop modal!
            resolveStale(new Response(JSON.stringify({ detail: 'Stale upgraded error' }), { status: 401 }))
            await stalePromise
            expect(mockStorage['tabiji_session_token']).toBe(reanchoredJwt)
            expect(modalTriggered).toBe(0)

            // 6. Mid-flight key update without TOKEN_KEY while stale B is in flight: new call with key C MUST exchange C!
            __resetExchangeFailedForTesting()
            delete mockStorage['tabiji_session_token']
            delete mockStorage['tabiji_pop_token']
            mockStorage['user_recovery_key'] = newKey

            let resolveFirst!: (res: Response) => void
            const firstPending = new Promise<Response>((resolve) => { resolveFirst = resolve })
            const thirdKey = 'tbj_rec_55555555_abcdef0123456789abcdef0123456789'
            let sawThirdKey = false

            globalThis.fetch = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
                const url = typeof input === 'string' ? input : input.toString()
                const body = JSON.parse(String(init?.body || '{}'))
                if (url.includes('/api/auth/session') && body.recovery_key === thirdKey) {
                    sawThirdKey = true
                    return Promise.resolve(new Response(JSON.stringify({ access_token: refreshedJwt, user_id: uid, recovery_key: thirdKey }), { status: 200 }))
                }
                if (url.includes('/api/auth/session')) {
                    return firstPending
                }
                return Promise.resolve(new Response(JSON.stringify([{ id: 'trip-race-ok' }]), { status: 200 }))
            }) as unknown as typeof fetch

            const p1 = ensureValidSession()
            mockStorage['user_recovery_key'] = thirdKey
            const resTrips = await fetcherWithUserId(['/api/trips', uid])
            expect(sawThirdKey).toBe(true)
            expect(resTrips).toEqual([{ id: 'trip-race-ok' }])
            expect(mockStorage['tabiji_session_token']).toBe(refreshedJwt)
            resolveFirst(new Response(JSON.stringify({ detail: 'Stale key error' }), { status: 401 }))
            await p1
            expect(mockStorage['tabiji_session_token']).toBe(refreshedJwt)
            expect(modalTriggered).toBe(0)

            // 7. reanchorSessionWithKey ignores offline tbj_rec_* placeholder in user_uuid
            mockStorage['user_uuid'] = thirdKey
            globalThis.fetch = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
                const body = JSON.parse(String(init?.body || '{}'))
                expect(body.expected_user_id).toBeUndefined()
                return Promise.resolve(new Response(JSON.stringify({ access_token: refreshedJwt, user_id: uid }), { status: 200 }))
            }) as unknown as typeof fetch
            await expect(reanchorSessionWithKey(thirdKey)).resolves.toBe(refreshedJwt)
            expect(mockStorage['user_uuid']).toBe(uid)
        } finally {
            window.removeEventListener('tabiji:session_reauth_required', listener)
        }
    })

    it('F14: /api/sign-cloudinary rejects boolean/float timestamps and delimiter-smuggled folders while allowing valid receipt subpaths', async () => {
        vi.stubEnv('CLOUDINARY_API_SECRET', 'cloudinary_test_secret_1234567890abcdef')
        const { POST } = await import('@/app/api/sign-cloudinary/route')

        const postSign = (body: unknown) =>
            POST(new Request('https://travel-pwa-five.vercel.app/api/sign-cloudinary', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            }))

        expect((await postSign({ paramsToSign: { timestamp: true, folder: 'ryan_travel/covers' } })).status).toBe(400)
        expect((await postSign({ paramsToSign: { timestamp: 1700000000.5, folder: 'ryan_travel/covers' } })).status).toBe(400)
        expect((await postSign({ paramsToSign: { timestamp: 1700000000, folder: 'ryan_travel/covers&overwrite=true' } })).status).toBe(400)
        expect((await postSign({ paramsToSign: { timestamp: 1700000000, folder: 'ryan_travel/covers?x=1' } })).status).toBe(400)

        const okReceipt = await postSign({
            paramsToSign: { timestamp: 1700000000, folder: 'ryan_travel/receipts/3f7abf22-b447-4281-b240-584549c79943' },
        })
        expect(okReceipt.status).toBe(200)
        expect((await okReceipt.json()).signature).toBeTruthy()
    })
})
