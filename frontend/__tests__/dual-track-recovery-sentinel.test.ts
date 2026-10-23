import { describe, it, expect } from 'vitest'

// Core format regexes for dual-track recovery
const UUID_RELAXED_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const TBJ_REC_REGEX = /^tbj_rec_[0-9a-f]{8}_[0-9a-f]{32}$/i

function isValidRecoveryKey(key: string | null | undefined): boolean {
    if (!key || typeof key !== 'string') return false
    const clean = key.trim()
    return UUID_RELAXED_REGEX.test(clean) || TBJ_REC_REGEX.test(clean)
}

describe('Dual-Track Recovery Input Validation Sandbox Tests', () => {
    it('TC-1: Accepts modern tbj_rec_* recovery key from user screenshot', () => {
        // Exact prefix & format from Ryan's screenshot
        const modernKey = 'tbj_rec_4ce43480_72b32646f2911f5a549a37e192f15a67'
        expect(isValidRecoveryKey(modernKey)).toBe(true)
    })

    it('TC-2: Accepts modern tbj_rec_* with whitespace or mixed casing', () => {
        const paddedKey = '   tbj_rec_4CE43480_72B32646F2911F5A549A37E192F15A67 \n'
        expect(isValidRecoveryKey(paddedKey)).toBe(true)
    })

    it('TC-3: Accepts legacy UUID v4', () => {
        const legacyUuid = 'ee7e3ae2-870f-4b60-bd81-6937576c855f'
        expect(isValidRecoveryKey(legacyUuid)).toBe(true)
    })

    it('TC-4: Rejects malformed or truncated recovery keys', () => {
        expect(isValidRecoveryKey(null)).toBe(false)
        expect(isValidRecoveryKey('')).toBe(false)
        expect(isValidRecoveryKey('tbj_rec_')).toBe(false)
        expect(isValidRecoveryKey('tbj_rec_4ce43480')).toBe(false)
        expect(isValidRecoveryKey('tbj_rec_4ce43480_short')).toBe(false)
        expect(isValidRecoveryKey('tbj_rec_invalid_hex_characters_here_123456789012')).toBe(false)
        expect(isValidRecoveryKey('random-string-not-uuid')).toBe(false)
    })
})
