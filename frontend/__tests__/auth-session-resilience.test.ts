import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { isTokenValid, getCachedToken, initSessionLifecycleListener } from '@/lib/auth-session'

function createMockJwt(payload: Record<string, unknown>): string {
    const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url')
    const body = Buffer.from(JSON.stringify(payload)).toString('base64url')
    return `${header}.${body}.mock-signature`
}

describe('Auth Session Resilience & Token Life-Cycle Tests', () => {
    let mockStorage: Record<string, string> = {}

    beforeEach(() => {
        mockStorage = {}
        vi.stubGlobal('localStorage', {
            getItem: vi.fn((k: string) => mockStorage[k] || null),
            setItem: vi.fn((k: string, v: string) => { mockStorage[k] = v }),
            removeItem: vi.fn((k: string) => { delete mockStorage[k] }),
            clear: vi.fn(() => { mockStorage = {} }),
        })
    })

    afterEach(() => {
        vi.restoreAllMocks()
    })

    it('TC-1: isTokenValid accepts unexpired token with future exp', () => {
        const futureExp = Math.floor(Date.now() / 1000) + 3600
        const validJwt = createMockJwt({ sub: 'user-123', exp: futureExp })
        expect(isTokenValid(validJwt)).toBe(true)
    })

    it('TC-2: isTokenValid rejects expired token', () => {
        const pastExp = Math.floor(Date.now() / 1000) - 3600
        const expiredJwt = createMockJwt({ sub: 'user-123', exp: pastExp })
        expect(isTokenValid(expiredJwt)).toBe(false)
    })

    it('TC-3: isTokenValid rejects malformed or corrupted strings', () => {
        expect(isTokenValid(null)).toBe(false)
        expect(isTokenValid('')).toBe(false)
        expect(isTokenValid('not-a-jwt')).toBe(false)
        expect(isTokenValid('part1.part2')).toBe(false)
        expect(isTokenValid('part1.invalidbase64!@#.part3')).toBe(false)
    })

    it('TC-4: getCachedToken automatically purges expired token from localStorage', () => {
        const pastExp = Math.floor(Date.now() / 1000) - 600
        const expiredJwt = createMockJwt({ sub: 'user-123', exp: pastExp })
        mockStorage['tabiji_session_token'] = expiredJwt

        const token = getCachedToken()
        expect(token).toBeNull()
        expect(mockStorage['tabiji_session_token']).toBeUndefined()
    })

    it('TC-5: getCachedToken returns valid unexpired token intact', () => {
        const futureExp = Math.floor(Date.now() / 1000) + 86400
        const validJwt = createMockJwt({ sub: 'user-123', exp: futureExp })
        mockStorage['tabiji_session_token'] = validJwt

        const token = getCachedToken()
        expect(token).toBe(validJwt)
        expect(mockStorage['tabiji_session_token']).toBe(validJwt)
    })

    it('TC-6: initSessionLifecycleListener attaches and detaches online & visibility listeners', () => {
        const addEventSpy = vi.spyOn(window, 'addEventListener')
        const removeEventSpy = vi.spyOn(window, 'removeEventListener')

        const cleanup = initSessionLifecycleListener()
        expect(addEventSpy).toHaveBeenCalledWith('online', expect.any(Function))

        cleanup()
        expect(removeEventSpy).toHaveBeenCalledWith('online', expect.any(Function))
    })

    it('TC-7: ensureValidSession sets RECOVERY_KEY when initial visitor has no stored key', async () => {
        const { ensureValidSession } = await import('@/lib/auth-session')
        process.env.TEST_AUTH_EXCHANGE = 'true'
        delete mockStorage['user_uuid']
        const futureExp = Math.floor(Date.now() / 1000) + 3600
        const freshJwt = createMockJwt({ sub: 'brand-new-user-456', exp: futureExp })

        vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
            ok: true,
            status: 200,
            json: async () => ({
                access_token: freshJwt,
                user_id: 'brand-new-user-456',
                is_new: true
            })
        } as unknown as Response)

        const token = await ensureValidSession()
        expect(token).toBe(freshJwt)
        expect(mockStorage['tabiji_session_token']).toBe(freshJwt)
        expect(mockStorage['user_uuid']).toBe('brand-new-user-456')
        delete process.env.TEST_AUTH_EXCHANGE
    })

    it('TC-8: ensureValidSession retains existing user_uuid when is_new is false', async () => {
        const { ensureValidSession } = await import('@/lib/auth-session')
        process.env.TEST_AUTH_EXCHANGE = 'true'
        mockStorage['user_uuid'] = 'existing-user-123'
        const futureExp = Math.floor(Date.now() / 1000) + 3600
        const freshJwt = createMockJwt({ sub: 'existing-user-123', exp: futureExp })

        vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
            ok: true,
            status: 200,
            json: async () => ({
                access_token: freshJwt,
                user_id: 'existing-user-123',
                is_new: false
            })
        } as unknown as Response)

        const token = await ensureValidSession()
        expect(token).toBe(freshJwt)
        expect(mockStorage['user_uuid']).toBe('existing-user-123')
        delete process.env.TEST_AUTH_EXCHANGE
    })

    it('TC-9: ensureValidSession refuses to overwrite existing user_uuid or tokens on identity mismatch', async () => {
        const { ensureValidSession, __resetExchangeFailedForTesting } = await import('@/lib/auth-session')
        __resetExchangeFailedForTesting()
        process.env.TEST_AUTH_EXCHANGE = 'true'
        mockStorage['user_uuid'] = 'permanent-owner-key'
        const futureExp = Math.floor(Date.now() / 1000) + 3600
        const freshJwt = createMockJwt({ sub: 'alien-user-789', exp: futureExp })

        vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
            ok: true,
            status: 200,
            json: async () => ({
                access_token: freshJwt,
                user_id: 'alien-user-789',
                recovery_key: 'tbj_rec_alien000_0123456789abcdef0123456789abcdef',
                is_new: true
            })
        } as unknown as Response)

        const token = await ensureValidSession()
        expect(token).toBeNull()
        expect(mockStorage['user_uuid']).toBe('permanent-owner-key')
        expect(mockStorage['tabiji_session_token']).toBeUndefined()
        expect(mockStorage['tabiji_pop_token']).toBeUndefined()
        expect(mockStorage['user_recovery_key']).toBeUndefined()
        delete process.env.TEST_AUTH_EXCHANGE
    })

    it('TC-10: ensureValidSession triggers reauth prompt on 401 when storedKey exists', async () => {
        const { ensureValidSession, __resetExchangeFailedForTesting } = await import('@/lib/auth-session')
        __resetExchangeFailedForTesting()
        process.env.TEST_AUTH_EXCHANGE = 'true'
        mockStorage['user_recovery_key'] = 'tbj_rec_deadbeef_0123456789abcdef0123456789abcdef'

        let reauthDispatched = false
        const listener = () => { reauthDispatched = true }
        window.addEventListener('tabiji:session_reauth_required', listener)

        vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
            ok: false,
            status: 401,
            json: async () => ({ detail: '引繼碼驗證失敗，無法在此設備恢復同步。請確認引繼碼是否正確。' })
        } as unknown as Response)

        const token = await ensureValidSession()
        expect(token).toBeNull()
        expect(reauthDispatched).toBe(true)

        window.removeEventListener('tabiji:session_reauth_required', listener)
        delete process.env.TEST_AUTH_EXCHANGE
    })

    it('TC-11: ensureValidSession enforces cooldown to block rapid repeat exchange hammering', async () => {
        const { ensureValidSession } = await import('@/lib/auth-session')
        process.env.TEST_AUTH_EXCHANGE = 'true'
        mockStorage['user_recovery_key'] = 'tbj_rec_deadbeef_0123456789abcdef0123456789abcdef'

        const fetchSpy = vi.spyOn(globalThis, 'fetch')
        // Cooldown is active from TC-10 (within 10s)
        const token = await ensureValidSession()
        expect(token).toBeNull()
        expect(fetchSpy).not.toHaveBeenCalled()
        delete process.env.TEST_AUTH_EXCHANGE
    })

    it('TC-12: ensureValidSession(true) backs up unexpired stale JWT to tabiji_pop_token and exchanges for fresh JWT', async () => {
        const { ensureValidSession, __resetExchangeFailedForTesting } = await import('@/lib/auth-session')
        __resetExchangeFailedForTesting()
        process.env.TEST_AUTH_EXCHANGE = 'true'

        const futureExp = Math.floor(Date.now() / 1000) + 86400
        const staleJwt = createMockJwt({ sub: 'user-rot-1', exp: futureExp })
        const freshJwt = createMockJwt({ sub: 'user-rot-1', exp: futureExp + 3600 })

        mockStorage['tabiji_session_token'] = staleJwt
        mockStorage['user_recovery_key'] = 'tbj_rec_12345678_0123456789abcdef0123456789abcdef'
        mockStorage['user_uuid'] = 'user-rot-1'

        const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
            ok: true,
            status: 200,
            json: async () => ({
                access_token: freshJwt,
                user_id: 'user-rot-1',
                is_new: false,
            })
        } as unknown as Response)

        const token = await ensureValidSession(true)
        expect(token).toBe(freshJwt)
        expect(mockStorage['tabiji_session_token']).toBe(freshJwt)
        expect(fetchSpy).toHaveBeenCalledTimes(1)

        // Verify PoP header sent during exchange contained staleJwt before refresh completed
        const [, fetchInit] = fetchSpy.mock.calls[0]
        const sentHeaders = fetchInit?.headers as Record<string, string>
        expect(sentHeaders['Authorization']).toBe(`Bearer ${staleJwt}`)
        delete process.env.TEST_AUTH_EXCHANGE
    })

    it('TC-13: ensureValidSession(true) purges non-JWT garbage without overwriting valid tabiji_pop_token', async () => {
        const { ensureValidSession, __resetExchangeFailedForTesting } = await import('@/lib/auth-session')
        __resetExchangeFailedForTesting()
        process.env.TEST_AUTH_EXCHANGE = 'true'

        const futureExp = Math.floor(Date.now() / 1000) + 86400
        const previousValidPop = createMockJwt({ sub: 'user-rot-2', exp: futureExp })
        const freshJwt = createMockJwt({ sub: 'user-rot-2', exp: futureExp + 3600 })

        mockStorage['tabiji_pop_token'] = previousValidPop
        mockStorage['tabiji_session_token'] = 'corrupted-not-a-jwt'
        mockStorage['user_uuid'] = 'user-rot-2'

        const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
            ok: true,
            status: 200,
            json: async () => ({
                access_token: freshJwt,
                user_id: 'user-rot-2',
                is_new: false,
            })
        } as unknown as Response)

        const token = await ensureValidSession(true)
        expect(token).toBe(freshJwt)
        const [, fetchInit] = fetchSpy.mock.calls[0]
        expect((fetchInit?.headers as Record<string, string>)['Authorization']).toBe(`Bearer ${previousValidPop}`)
        delete process.env.TEST_AUTH_EXCHANGE
    })

    it('TC-14: ensureValidSession reconciles offline tbj_rec_* placeholder in user_uuid to server user_id and notifies listeners', async () => {
        const { ensureValidSession, __resetExchangeFailedForTesting } = await import('@/lib/auth-session')
        __resetExchangeFailedForTesting()
        process.env.TEST_AUTH_EXCHANGE = 'true'

        const recKey = 'tbj_rec_12345678_0123456789abcdef0123456789abcdef'
        const realUuid = '77777777-7777-4777-8777-777777777777'
        const futureExp = Math.floor(Date.now() / 1000) + 86400
        const freshJwt = createMockJwt({ sub: realUuid, exp: futureExp })

        mockStorage['user_recovery_key'] = recKey
        mockStorage['user_uuid'] = recKey
        mockStorage['user_nickname'] = 'OfflineTraveler'

        let loginStateChangedFired = false
        const onStateChange = () => { loginStateChangedFired = true }
        window.addEventListener('user-login-state-changed', onStateChange)

        try {
            vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
                ok: true,
                status: 200,
                json: async () => ({
                    access_token: freshJwt,
                    user_id: realUuid,
                    recovery_key: recKey,
                    is_new: false,
                })
            } as unknown as Response)

            const token = await ensureValidSession()
            expect(token).toBe(freshJwt)
            expect(mockStorage['user_uuid']).toBe(realUuid)
            expect(mockStorage['tabiji_session_token']).toBe(freshJwt)
            expect(loginStateChangedFired).toBe(true)
        } finally {
            window.removeEventListener('user-login-state-changed', onStateChange)
            delete process.env.TEST_AUTH_EXCHANGE
        }
    })

    it('TC-15: isUserLoggedIn rejects "null" and "undefined" sentinel strings', async () => {
        const { isUserLoggedIn } = await import('@/lib/auth-session')
        mockStorage['user_nickname'] = 'Visitor'
        mockStorage['user_uuid'] = 'null'
        expect(isUserLoggedIn()).toBe(false)

        mockStorage['user_uuid'] = 'undefined'
        expect(isUserLoggedIn()).toBe(false)

        mockStorage['user_recovery_key'] = 'null'
        expect(isUserLoggedIn()).toBe(false)
    })
})
