import { describe, it, expect } from 'vitest'
import {
    calculateHaversineDistance,
    estimateTransitTime,
    generateGoogleMapsDirUrl,
    computeTransitSegment,
    isValidCoordinate
} from '@/lib/transit-connector'

describe('Transit Connector - Core & Security Sentinel Tests', () => {
    // 台北 101: 25.033964, 121.564468
    const TAIPEI_101 = { lat: 25.033964, lng: 121.564468, name: 'Taipei 101' }
    // 象山步道口: 25.027419, 121.574676 (~1.27 km 直線距離)
    const XIANGSHAN = { lat: 25.027419, lng: 121.574676, name: 'Xiangshan Trail' }

    describe('Haversine Distance & Accuracy', () => {
        it('calculates realistic distance between Taipei 101 and Xiangshan', () => {
            const distance = calculateHaversineDistance(
                TAIPEI_101.lat,
                TAIPEI_101.lng,
                XIANGSHAN.lat,
                XIANGSHAN.lng
            )
            expect(distance).toBeGreaterThan(1.0)
            expect(distance).toBeLessThan(1.6)
            expect(distance).toBeCloseTo(1.28, 1)
        })

        it('returns 0 for identical coordinates', () => {
            const distance = calculateHaversineDistance(
                TAIPEI_101.lat,
                TAIPEI_101.lng,
                TAIPEI_101.lat,
                TAIPEI_101.lng
            )
            expect(distance).toBe(0)
        })
    })

    describe('Adversarial Coordinate Validation & NaN Defense', () => {
        it('rejects null, undefined, NaN, and Infinity coordinates safely', () => {
            expect(isValidCoordinate(NaN, 121.5)).toBe(false)
            expect(isValidCoordinate(25.0, Infinity)).toBe(false)
            expect(isValidCoordinate(null, null)).toBe(false)
            expect(isValidCoordinate(undefined, 121.5)).toBe(false)
            expect(isValidCoordinate(95.0, 121.5)).toBe(false) // 緯度越界
            expect(isValidCoordinate(25.0, 190.0)).toBe(false) // 經度越界
            expect(isValidCoordinate(0, 0)).toBe(false) // 原點 (0, 0)
        })

        it('prevents NaN propagation in distance calculation', () => {
            const distance = calculateHaversineDistance(NaN as unknown as number, 121.5, 25.0, 121.6)
            expect(distance).toBe(0)
            expect(Number.isNaN(distance)).toBe(false)
        })

        it('returns null safely when computeTransitSegment receives invalid coordinates', () => {
            const result = computeTransitSegment(
                { lat: NaN as unknown as number, lng: 121.5 },
                XIANGSHAN
            )
            expect(result).toBeNull()
        })
    })

    describe('Adaptive Transit Time Estimation', () => {
        it('recommends walking for short distance < 1.5 km', () => {
            const result = estimateTransitTime(1.2)
            expect(result.recommendedMode).toBe('walking')
            expect(result.minutes).toBe(15) // 1.2 * 12.5 = 15
            expect(result.isIntercity).toBe(false)
        })

        it('recommends transit for city trips >= 1.5 km', () => {
            const result = estimateTransitTime(5.0)
            expect(result.recommendedMode).toBe('transit')
            expect(result.minutes).toBeGreaterThan(15)
            expect(result.isIntercity).toBe(false)
        })

        it('flags intercity travel for distance >= 50 km', () => {
            const result = estimateTransitTime(150.0)
            expect(result.recommendedMode).toBe('transit')
            expect(result.isIntercity).toBe(true)
        })

        it('respects manual override mode', () => {
            const result = estimateTransitTime(1.2, 'driving')
            expect(result.recommendedMode).toBe('driving')
            expect(result.minutes).toBe(5) // 1.2 * 2 + 3 = 5.4 -> 5
        })
    })

    describe('Google Maps Direction URL Security (RFC 3986)', () => {
        it('generates secure HTTPS Google Maps universal URL with origin & destination', () => {
            const urlString = generateGoogleMapsDirUrl(TAIPEI_101, XIANGSHAN, 'walking')
            const url = new URL(urlString)

            expect(url.protocol).toBe('https:')
            expect(url.hostname).toBe('www.google.com')
            expect(url.pathname).toBe('/maps/dir/')
            expect(url.searchParams.get('api')).toBe('1')
            expect(url.searchParams.get('origin')).toContain('25.033964,121.564468')
            expect(url.searchParams.get('destination')).toContain('25.027419,121.574676')
            expect(url.searchParams.get('travelmode')).toBe('walking')
        })

        it('falls back to safe base URL when coordinates are invalid', () => {
            const fallback = generateGoogleMapsDirUrl(
                { lat: NaN as unknown as number, lng: 121.5 },
                XIANGSHAN
            )
            expect(fallback).toBe('https://www.google.com/maps')
        })
    })

    describe('Transit Mode Placeholders & Anti-clipping Tests', () => {
        it('ensures concise placeholders to prevent truncation on mobile screens', async () => {
            const { TRANSIT_MODE_PLACEHOLDERS } = await import('@/components/itinerary/TransitSegmentConnector')
            const modes = ['transit', 'driving', 'walking', 'bicycling'] as const
            for (const mode of modes) {
                const item = TRANSIT_MODE_PLACEHOLDERS[mode]
                expect(item).toBeDefined()
                expect(item.zh.length).toBeLessThanOrEqual(15) // 防止在小輸入框被截斷
                expect(item.en.length).toBeLessThanOrEqual(28)
            }
        })
    })
})

