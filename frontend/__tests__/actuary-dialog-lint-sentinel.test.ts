import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

describe('🛡️ Bug Hunter: ActuaryDialogCard Tailwind v4 Canonical Class Audit', () => {
    const cardPath = path.resolve(__dirname, '..', 'components', 'ActuaryDialogCard.tsx')
    const content = fs.readFileSync(cardPath, 'utf-8')

    it('TC-1: sm:max-w-[600px] MUST be modernized to Tailwind v4 canonical scale sm:max-w-150', () => {
        expect(content).not.toMatch(/sm:max-w-\[600px\]/)
        expect(content).toMatch(/sm:max-w-150/)
    })

    it('TC-2: flex-shrink-0 MUST use Tailwind canonical shorthand shrink-0', () => {
        expect(content).not.toMatch(/flex-shrink-0/)
        expect(content).toMatch(/shrink-0/)
    })

    it('TC-3: break-words MUST use Tailwind v4 canonical wrap-break-word', () => {
        expect(content).not.toMatch(/className=["'][^"']*break-words/)
        expect(content).toMatch(/wrap-break-word/)
    })
})
