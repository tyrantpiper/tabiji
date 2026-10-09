import { describe, it, expect } from 'vitest'
import { generateGreatCircle } from '@/lib/geo-multi-day'

describe('Security Sentinel: Great Circle Coordinate Robustness Guard', () => {
    it('TC-1: handles standard Tokyo-to-Kyoto route safely without NaN', () => {
        const tokyo: [number, number] = [139.6917, 35.6895]
        const kyoto: [number, number] = [135.7681, 35.0116]
        const arc = generateGreatCircle(tokyo, kyoto, 25)

        expect(arc.length).toBe(26)
        arc.forEach(([lng, lat]) => {
            expect(Number.isFinite(lng)).toBe(true)
            expect(Number.isFinite(lat)).toBe(true)
        })
    })

    it('TC-2: handles identical start and end coordinates gracefully', () => {
        const point: [number, number] = [139.6917, 35.6895]
        const arc = generateGreatCircle(point, point, 25)
        expect(arc).toEqual([point, point])
    })

    it('TC-3: handles NaN or malformed input coordinates defensively', () => {
        const nanPoint: [number, number] = [NaN, 35.6895]
        const validPoint: [number, number] = [135.7681, 35.0116]
        const arc = generateGreatCircle(nanPoint, validPoint, 25)
        expect(arc.length).toBe(2)
    })
})
