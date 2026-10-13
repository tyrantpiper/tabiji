import { describe, it, expect } from 'vitest'
import { 
    getTripCoverUrl, 
    resolveDestinationCover, 
    PRE_CURATED_COVERS, 
    DEFAULT_COVER_IMAGE 
} from '@/lib/destination-covers'

import { 
    addDaysToLocalYMD, 
    GLOBAL_INSPIRATION_PILLS 
} from '@/components/itinerary/TripDialogs'

describe('Security Sentinel: Cover Pipeline & Inspiration Pills Sandbox', () => {
    describe('[Vector 1: Falsy String Injection Defense]', () => {
        it('should correctly prioritize clean custom cover image', () => {
            const custom = 'https://images.unsplash.com/photo-custom?w=800'
            expect(getTripCoverUrl(custom, '東京 5 日自由行')).toBe(custom)
        })

        it('should fallback to destination cover on null, undefined or empty string', () => {
            expect(getTripCoverUrl(null, '東京 5 日自由行')).toBe(PRE_CURATED_COVERS.tokyo)
            expect(getTripCoverUrl(undefined, '巴黎 5 日藝文慢步')).toBe(PRE_CURATED_COVERS.paris)
            expect(getTripCoverUrl('', '紐約 5 日都會探索')).toBe(PRE_CURATED_COVERS.newyork)
        })

        it('should strictly reject malicious falsy strings: "null", "undefined", and whitespace', () => {
            // 🛡️ 防禦資料庫遺留字串 "null"
            expect(getTripCoverUrl('null', '東京 5 日自由行')).toBe(PRE_CURATED_COVERS.tokyo)
            // 🛡️ 防禦資料庫遺留字串 "undefined"
            expect(getTripCoverUrl('undefined', '巴黎 5 日藝文慢步')).toBe(PRE_CURATED_COVERS.paris)
            // 🛡️ 防禦全空白字串
            expect(getTripCoverUrl('    ', '紐約 5 日都會探索')).toBe(PRE_CURATED_COVERS.newyork)
        })

        it('should fallback to DEFAULT_COVER_IMAGE if title has no matching destination alias', () => {
            expect(getTripCoverUrl(null, '秘密冒險 2026')).toBe(DEFAULT_COVER_IMAGE)
            expect(getTripCoverUrl(undefined, '')).toBe(DEFAULT_COVER_IMAGE)
        })
    })

    describe('[Vector 2: Local Timezone Safe Date Calculation]', () => {
        it('should accurately calculate 5 days in normal month without UTC shift', () => {
            // 起始日 2026-10-15，加 4 天 = 2026-10-19 (總天數 5 天)
            expect(addDaysToLocalYMD('2026-10-15', 4)).toBe('2026-10-19')
        })

        it('should handle month rollover seamlessly (October 31st)', () => {
            // 10/31, 11/01, 11/02, 11/03, 11/04 -> 5 天
            expect(addDaysToLocalYMD('2026-10-31', 4)).toBe('2026-11-04')
        })

        it('should handle year rollover seamlessly (December 29th)', () => {
            // 12/29, 12/30, 12/31, 01/01, 01/02 -> 5 天
            expect(addDaysToLocalYMD('2026-12-29', 4)).toBe('2027-01-02')
        })

        it('should handle leap year February 29th seamlessly (2028-02-27)', () => {
            // 2028 為閏年，2/27, 2/28, 2/29, 03/01, 03/02 -> 5 天
            expect(addDaysToLocalYMD('2028-02-27', 4)).toBe('2028-03-02')
        })

        it('should safely return original string on malformed inputs', () => {
            expect(addDaysToLocalYMD('invalid-date', 4)).toBe('invalid-date')
            expect(addDaysToLocalYMD('', 4)).toBe('')
        })
    })

    describe('[Vector 3: Inspiration Pills Invariance]', () => {
        it('should have exactly 3 global items representing Asia, Europe, and Americas', () => {
            expect(GLOBAL_INSPIRATION_PILLS).toHaveLength(3)
            const ids = GLOBAL_INSPIRATION_PILLS.map(p => p.id)
            expect(ids).toEqual(['tokyo', 'paris', 'nyc'])
        })

        it('should enforce exactly 5 days for all 3 pills', () => {
            GLOBAL_INSPIRATION_PILLS.forEach(p => {
                expect(p.days).toBe(5)
            })
        })

        it('should resolve destination covers for all 3 pills titles', () => {
            GLOBAL_INSPIRATION_PILLS.forEach(p => {
                // 繁體中文標題解析
                const coverZh = resolveDestinationCover(p.titleZh)
                expect(coverZh).toBe(PRE_CURATED_COVERS[p.id === 'nyc' ? 'newyork' : p.id])
                
                // 英文標題解析
                const coverEn = resolveDestinationCover(p.titleEn)
                expect(coverEn).toBe(PRE_CURATED_COVERS[p.id === 'nyc' ? 'newyork' : p.id])
            })
        })
    })
})
