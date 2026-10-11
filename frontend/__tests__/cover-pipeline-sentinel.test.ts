import { describe, it, expect } from 'vitest'

import {
    PRE_CURATED_COVERS,
    DEFAULT_COVER_IMAGE,
    resolveDestinationCover
} from '@/lib/destination-covers'

describe('🧭 Cover Pipeline Sentinel In-Memory Tests', () => {
    it('should correctly match Asian destinations (Tokyo, Kyoto, Taipei, Osaka)', () => {
        expect(resolveDestinationCover('東京 5 日自由行')).toBe(PRE_CURATED_COVERS.tokyo)
        expect(resolveDestinationCover('Kyoto Temple Walk')).toBe(PRE_CURATED_COVERS.kyoto)
        expect(resolveDestinationCover('台北美食之旅')).toBe(PRE_CURATED_COVERS.taipei)
        expect(resolveDestinationCover('大阪環球影城')).toBe(PRE_CURATED_COVERS.osaka)
    })

    it('should correctly match European & American destinations (Paris, NYC, London)', () => {
        expect(resolveDestinationCover('巴黎 5 日藝文浪漫')).toBe(PRE_CURATED_COVERS.paris)
        expect(resolveDestinationCover('Paris Cultural Romance')).toBe(PRE_CURATED_COVERS.paris)
        expect(resolveDestinationCover('紐約 5 日都會經典')).toBe(PRE_CURATED_COVERS.newyork)
        expect(resolveDestinationCover('New York Explorer')).toBe(PRE_CURATED_COVERS.newyork)
        expect(resolveDestinationCover('London Royal Tour')).toBe(PRE_CURATED_COVERS.london)
    })

    it('should fallback to default aesthetic cover when destination is unknown', () => {
        expect(resolveDestinationCover('神祕冒險 2026')).toBe(DEFAULT_COVER_IMAGE)
        expect(resolveDestinationCover('')).toBe(DEFAULT_COVER_IMAGE)
    })

    it('should defend against malicious script injection or HTML tags in title', () => {
        const maliciousTitle = '<script>alert(1)</script> 東京之旅'
        const cover = resolveDestinationCover(maliciousTitle)
        expect(cover).toBe(PRE_CURATED_COVERS.tokyo)
        expect(cover).not.toContain('<script>')
    })
})
