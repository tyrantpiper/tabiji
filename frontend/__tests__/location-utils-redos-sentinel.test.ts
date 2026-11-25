import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { extractCleanPlaceQuery, extractPlaceParentheticalNote } from '@/lib/location-utils'

describe('Security Sentinel — location-utils PAREN_REMARK_GLOBAL_RE ReDoS Defense', () => {
    it('Benign Control: extracts clean place query and parenthetical remarks accurately', () => {
        expect(extractCleanPlaceQuery('淺草寺 (雷門拍照)')).toBe('淺草寺')
        expect(extractCleanPlaceQuery('10:00 築地市場（海鮮早餐）')).toBe('築地市場')
        expect(extractCleanPlaceQuery('晴空塔【夜景】')).toBe('晴空塔')
        expect(extractPlaceParentheticalNote('淺草寺 (雷門拍照)（下午茶）')).toBe('雷門拍照 / 下午茶')
    })

    it('Red->Green PoC: removes leading \\s* and runs in strictly linear time on 60k internal whitespace payload', () => {
        const src = readFileSync(path.resolve(__dirname, '../lib/location-utils.ts'), 'utf-8')
        expect(src).not.toMatch(/PAREN_REMARK_GLOBAL_RE\s*=\s*\/\\s\*/)

        const adversarial = 'A' + ' '.repeat(60000) + 'X'
        const t0 = performance.now()
        const cleaned = extractCleanPlaceQuery(adversarial)
        const note = extractPlaceParentheticalNote(adversarial)
        const elapsedMs = performance.now() - t0

        expect(cleaned).toBe('A X')
        expect(note).toBe('')
        expect(elapsedMs).toBeLessThan(50)
    })
})
