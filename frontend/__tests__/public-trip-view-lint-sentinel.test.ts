import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

describe('🛡️ Bug Hunter: PublicTripView Tailwind v4 Canonical Class Audit', () => {
    const viewPath = path.resolve(__dirname, '..', 'app', 'share', '[shareCode]', 'PublicTripView.tsx')
    const content = fs.readFileSync(viewPath, 'utf-8')

    it('TC-1: bg-gradient-to-br MUST be modernized to Tailwind v4 canonical bg-linear-to-br', () => {
        expect(content).not.toMatch(/bg-gradient-to-br/)
        expect(content).toMatch(/bg-linear-to-br/)
    })

    it('TC-2: flex-shrink-0 MUST use Tailwind canonical shorthand shrink-0', () => {
        expect(content).not.toMatch(/flex-shrink-0/)
        expect(content).toMatch(/shrink-0/)
    })
})
