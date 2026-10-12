import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

describe('🛡️ Security Sentinel: Segmented Tabs Icon Harmony & Symmetry Audit', () => {
    const frontendDir = path.resolve(__dirname, '..')

    it('TC-1: info-view.tsx MUST alias Hotel as HotelIcon to prevent identifier collision with type Hotel', () => {
        const infoViewPath = path.join(frontendDir, 'components', 'views', 'info-view.tsx')
        const content = fs.readFileSync(infoViewPath, 'utf-8')
        
        // Check local type definition exists
        expect(content).toMatch(/type\s+Hotel\s*=\s*typeof\s+DEFAULT_HOTEL/)

        // Must import Hotel as HotelIcon from lucide-react to avoid type/value duplicate identifier collision
        expect(content).toMatch(/import\s*\{[^}]*Hotel\s+as\s+HotelIcon[^}]*\}\s*from\s*["']lucide-react["']/)
        // Must import ShoppingBag from lucide-react
        expect(content).toMatch(/import\s*\{[^}]*ShoppingBag[^}]*\}\s*from\s*["']lucide-react["']/)
    })

    it('TC-2: info-view.tsx segmented tabs MUST eliminate emoji string concatenation and adopt Lucide icons', () => {
        const infoViewPath = path.join(frontendDir, 'components', 'views', 'info-view.tsx')
        const content = fs.readFileSync(infoViewPath, 'utf-8')

        // Must not contain emoji string concatenation
        expect(content).not.toMatch(/['"]✈️\s*['"]\s*\+\s*t\(['"]flight_details['"]\)/)
        expect(content).not.toMatch(/['"]🏨\s*['"]\s*\+\s*t\(['"]accommodation['"]\)/)
        expect(content).not.toMatch(/['"]🛒\s*['"]\s*\+\s*t\(['"]booking_center['"]\)/)

        // Must render icon in button
        expect(content).toMatch(/<tab\.icon\s+className=["'][^"']*w-4\s+h-4\s+shrink-0/)
    })

    it('TC-3: tools-view.tsx segmented tabs MUST provide 3-item icon symmetry (CreditCard, Receipt, Calculator)', () => {
        const toolsViewPath = path.join(frontendDir, 'components', 'views', 'tools-view.tsx')
        const content = fs.readFileSync(toolsViewPath, 'utf-8')

        // Must define tab array with CreditCard, Receipt, and Calculator
        expect(content).toMatch(/icon:\s*CreditCard/)
        expect(content).toMatch(/icon:\s*Receipt/)
        expect(content).toMatch(/icon:\s*Calculator/)

        // Must render icon in button
        expect(content).toMatch(/<tab\.icon\s+className=["'][^"']*w-4\s+h-4\s+shrink-0/)
    })

    it('TC-4: Tab buttons MUST enforce flex layout and relative z-10 for GPU layer isolation', () => {
        const infoViewPath = path.join(frontendDir, 'components', 'views', 'info-view.tsx')
        const toolsViewPath = path.join(frontendDir, 'components', 'views', 'tools-view.tsx')
        
        const infoContent = fs.readFileSync(infoViewPath, 'utf-8')
        const toolsContent = fs.readFileSync(toolsViewPath, 'utf-8')

        // Must include flex items-center justify-center in buttons or wrapper
        expect(infoContent).toMatch(/relative\s+z-10\s+flex\s+items-center\s+justify-center\s+gap-1\.5/)
        expect(toolsContent).toMatch(/relative\s+z-10\s+flex\s+items-center\s+justify-center\s+gap-1\.5/)
    })

    it('TC-5: remaining.ts i18n dictionaries MUST NOT contain hardcoded emojis in tv_cards and tv_actuary', () => {
        const remainingPath = path.join(frontendDir, 'lib', 'i18n', 'remaining.ts')
        const content = fs.readFileSync(remainingPath, 'utf-8')

        // English dictionary
        expect(content).not.toMatch(/tv_cards:\s*["']💳/)
        expect(content).not.toMatch(/tv_actuary:\s*["']🧮/)

        // Traditional Chinese dictionary
        expect(content).not.toMatch(/tv_cards:\s*["']💳\s*卡片["']/)
        expect(content).not.toMatch(/tv_actuary:\s*["']🧮\s*精算器["']/)
        
        // Pure strings must exist
        expect(content).toMatch(/tv_cards:\s*["']Cards["']/)
        expect(content).toMatch(/tv_actuary:\s*["']Actuary["']/)
        expect(content).toMatch(/tv_cards:\s*["']卡片["']/)
        expect(content).toMatch(/tv_actuary:\s*["']精算器["']/)
    })
})
