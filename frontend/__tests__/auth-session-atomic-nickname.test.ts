/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
    isDefaultPlaceholderNickname,
    normalizeUserInputNickname,
    sanitizeEffectiveNickname,
    ensureValidSession,
    resetAndStartFreshSession,
    __resetExchangeFailedForTesting,
} from '@/lib/auth-session'

function createMockJwt(payload: Record<string, unknown>): string {
    const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url')
    const body = Buffer.from(JSON.stringify(payload)).toString('base64url')
    return `${header}.${body}.mock-sig`
}

describe('Auth Session Atomic Nickname Bootstrap & Placeholder Guard', () => {
    let mockStorage: Record<string, string> = {}
    const originalFetch = globalThis.fetch

    beforeEach(() => {
        __resetExchangeFailedForTesting()
        mockStorage = {}
        vi.stubGlobal('localStorage', {
            getItem: vi.fn((k: string) => (k in mockStorage ? mockStorage[k] : null)),
            setItem: vi.fn((k: string, v: string) => { mockStorage[k] = String(v) }),
            removeItem: vi.fn((k: string) => { delete mockStorage[k] }),
            clear: vi.fn(() => { mockStorage = {} }),
        })
        Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
        process.env.TEST_AUTH_EXCHANGE = 'true'
    })

    afterEach(() => {
        delete process.env.TEST_AUTH_EXCHANGE
        globalThis.fetch = originalFetch
        vi.restoreAllMocks()
        vi.unstubAllGlobals()
    })

    it('identifies default placeholder nicknames while allowing real names containing Traveler', () => {
        for (const bad of [
            null,
            undefined,
            '',
            '   \t\r\n  ',
            '\x00\x07\x1f',
            'Traveler',
            'traveler',
            '  TRAVELER  ',
            'New Traveler',
            'Unknown Traveler',
            'Legacy Traveler',
            'null',
            'undefined',
            '\u200b',
            '\ufeff',
            '\u200b\u200c\ufeff',
            '\u200d',
            '\u200d\ufe0f',
            'Traveler\u200b',
            'New\u3000Traveler',
            'New\u00a0Traveler',
        ]) {
            expect(isDefaultPlaceholderNickname(bad)).toBe(true)
            expect(sanitizeEffectiveNickname(bad)).toBeUndefined()
        }

        // Post-truncation placeholder guard when grapheme-safe clamp trims a long trailing cluster
        expect(sanitizeEffectiveNickname('null' + 'e' + '\u0301'.repeat(61))).toBeUndefined()
        expect(sanitizeEffectiveNickname('undefined' + 'e' + '\u0301'.repeat(61))).toBeUndefined()
        // Unicode fullwidth whitespace is collapsed cleanly before truncation
        expect(sanitizeEffectiveNickname('null' + '\u3000'.repeat(60) + 'x')).toBe('null x')

        expect(isDefaultPlaceholderNickname('海獺')).toBe(false)
        expect(sanitizeEffectiveNickname('  海獺  ')).toBe('海獺')
        expect(sanitizeEffectiveNickname('\u202eAlice\u200b')).toBe('Alice')
        expect(sanitizeEffectiveNickname('Alice\r\n\t\x00Bob')).toBe('Alice Bob')
        expect(sanitizeEffectiveNickname('海獺 🦦👨‍💻')).toBe('海獺 🦦👨‍💻')
        expect(isDefaultPlaceholderNickname('Tokyo Traveler')).toBe(false)
        expect(sanitizeEffectiveNickname('Tokyo Traveler')).toBe('Tokyo Traveler')

        // Grapheme-safe truncation: never splits surrogate pairs, ZWJ emojis, flags, or combining marks
        const longEmojiName = '🦦'.repeat(70)
        expect(sanitizeEffectiveNickname(longEmojiName)).toBe('🦦'.repeat(64))
        expect(sanitizeEffectiveNickname('A'.repeat(62) + '👨‍💻')).toBe('A'.repeat(62))
        expect(sanitizeEffectiveNickname('A'.repeat(62) + '👨‍👩‍👧‍👦')).toBe('A'.repeat(62))
        expect(sanitizeEffectiveNickname('A'.repeat(63) + '🇹🇼')).toBe('A'.repeat(63))
        expect(sanitizeEffectiveNickname('A'.repeat(63) + 'e\u0301')).toBe('A'.repeat(63))
        expect(sanitizeEffectiveNickname('e' + '\u0301'.repeat(70))).toBeUndefined()

        // normalizeUserInputNickname blocks invisible & literal null/undefined while keeping consistent sanitization
        expect(normalizeUserInputNickname('\u200b')).toBeUndefined()
        expect(normalizeUserInputNickname('null')).toBeUndefined()
        expect(normalizeUserInputNickname('undefined')).toBeUndefined()
        expect(normalizeUserInputNickname('null' + 'e' + '\u0301'.repeat(61))).toBeUndefined()
        expect(normalizeUserInputNickname('\u202e\u3000測試\u3000🇹🇼👨‍💻\u3000')).toBe('測試 🇹🇼👨‍💻')
        expect(normalizeUserInputNickname('A'.repeat(62) + '👨‍💻' + 'extra')).toBe('A'.repeat(62))
        expect(normalizeUserInputNickname('Traveler')).toBe('Traveler')
    })

    it('ensureValidSession sends explicit initialName in POST /api/auth/session for brand-new users', async () => {
        const uid = '11111111-1111-4111-8111-111111111111'
        const jwt = createMockJwt({ sub: uid, exp: Math.floor(Date.now() / 1000) + 3600 })
        let capturedBody: Record<string, unknown> = {}

        globalThis.fetch = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
            capturedBody = JSON.parse(String(init?.body || '{}'))
            return new Response(
                JSON.stringify({
                    access_token: jwt,
                    user_id: uid,
                    recovery_key: 'tbj_rec_12345678_0123456789abcdef0123456789abcdef',
                    is_new: true,
                }),
                { status: 200, headers: { 'Content-Type': 'application/json' } }
            )
        }) as unknown as typeof fetch

        const tok = await ensureValidSession(false, { initialName: '  小明  ' })
        expect(tok).toBe(jwt)
        expect(capturedBody.name).toBe('小明')
        expect(capturedBody.recovery_key).toBeUndefined()
    })

    it('ensureValidSession does not fall back to stale localStorage nickname when initialName is explicitly a placeholder', async () => {
        mockStorage['user_nickname'] = 'StaleLocalName'
        const uid = '22222222-2222-4222-8222-222222222222'
        const jwt = createMockJwt({ sub: uid, exp: Math.floor(Date.now() / 1000) + 3600 })
        let capturedBody: Record<string, unknown> = {}

        globalThis.fetch = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
            capturedBody = JSON.parse(String(init?.body || '{}'))
            return new Response(
                JSON.stringify({ access_token: jwt, user_id: uid, is_new: true }),
                { status: 200, headers: { 'Content-Type': 'application/json' } }
            )
        }) as unknown as typeof fetch

        await ensureValidSession(false, { initialName: 'Traveler' })
        expect('name' in capturedBody).toBe(false)
    })

    it('ensureValidSession sends local user_nickname during orphan UUID bootstrap and omits default placeholders', async () => {
        const orphanUid = '33333333-3333-4333-8333-333333333333'
        const jwt = createMockJwt({ sub: orphanUid, exp: Math.floor(Date.now() / 1000) + 3600 })
        mockStorage['user_uuid'] = orphanUid
        mockStorage['user_nickname'] = '海獺'

        let capturedBody: Record<string, unknown> = {}
        globalThis.fetch = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
            capturedBody = JSON.parse(String(init?.body || '{}'))
            return new Response(
                JSON.stringify({
                    access_token: jwt,
                    user_id: orphanUid,
                    recovery_key: 'tbj_rec_deadbeef_0123456789abcdef0123456789abcdef',
                    upgraded: true,
                    is_new: false,
                }),
                { status: 200, headers: { 'Content-Type': 'application/json' } }
            )
        }) as unknown as typeof fetch

        const tok = await ensureValidSession()
        expect(tok).toBe(jwt)
        expect(capturedBody).toEqual({
            recovery_key: orphanUid,
            expected_user_id: orphanUid,
            name: '海獺',
        })

        // Now verify placeholder local nickname is omitted
        __resetExchangeFailedForTesting()
        delete mockStorage['tabiji_session_token']
        delete mockStorage['tabiji_pop_token']
        delete mockStorage['user_recovery_key']
        mockStorage['user_nickname'] = 'Traveler'

        await ensureValidSession()
        expect('name' in capturedBody).toBe(false)
    })

    it('resetAndStartFreshSession includes valid local nickname and omits placeholder nickname', async () => {
        const uid1 = '44444444-4444-4444-8444-444444444444'
        const jwt1 = createMockJwt({ sub: uid1, exp: Math.floor(Date.now() / 1000) + 3600 })
        mockStorage['user_nickname'] = 'Chungshi'

        let capturedBody: Record<string, unknown> = {}
        globalThis.fetch = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
            capturedBody = JSON.parse(String(init?.body || '{}'))
            return new Response(
                JSON.stringify({ access_token: jwt1, user_id: uid1, is_new: true }),
                { status: 200, headers: { 'Content-Type': 'application/json' } }
            )
        }) as unknown as typeof fetch

        const info = await resetAndStartFreshSession()
        expect(info?.userId).toBe(uid1)
        expect(capturedBody).toEqual({ name: 'Chungshi' })

        // Placeholder local nickname -> sends {}
        mockStorage['user_nickname'] = 'New Traveler'
        await resetAndStartFreshSession()
        expect(capturedBody).toEqual({})
    })

    it('ensureValidSession omits name when refreshing an existing modern tbj_rec_* key', async () => {
        const uid = '55555555-5555-4555-8555-555555555555'
        const modernKey = 'tbj_rec_abcdef12_0123456789abcdef0123456789abcdef'
        const jwt = createMockJwt({ sub: uid, exp: Math.floor(Date.now() / 1000) + 3600 })
        mockStorage['user_uuid'] = uid
        mockStorage['user_recovery_key'] = modernKey
        mockStorage['user_nickname'] = '海獺'

        let capturedBody: Record<string, unknown> = {}
        globalThis.fetch = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
            capturedBody = JSON.parse(String(init?.body || '{}'))
            return new Response(
                JSON.stringify({ access_token: jwt, user_id: uid, recovery_key: modernKey, is_new: false }),
                { status: 200, headers: { 'Content-Type': 'application/json' } }
            )
        }) as unknown as typeof fetch

        const tok = await ensureValidSession(true)
        expect(tok).toBe(jwt)
        expect(capturedBody).toEqual({
            recovery_key: modernKey,
            expected_user_id: uid,
        })
        expect('name' in capturedBody).toBe(false)
    })
})
