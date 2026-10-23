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

    it('TC-9: ensureValidSession refuses to overwrite existing user_uuid on identity mismatch', async () => {
        const { ensureValidSession } = await import('@/lib/auth-session')
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
                is_new: true
            })
        } as unknown as Response)

        const token = await ensureValidSession()
        expect(token).toBeNull()
        expect(mockStorage['user_uuid']).toBe('permanent-owner-key')
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
})
