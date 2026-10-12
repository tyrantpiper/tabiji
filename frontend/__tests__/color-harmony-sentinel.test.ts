import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

describe('🛡️ Security Sentinel: Color Harmony & Native Icon Integrity Audit', () => {
    const frontendDir = path.resolve(__dirname, '..')

    it('TC-1: ToolsView MUST import Calculator and Coins from lucide-react (No ReferenceError)', () => {
        const toolsViewPath = path.join(frontendDir, 'components', 'views', 'tools-view.tsx')
        const content = fs.readFileSync(toolsViewPath, 'utf-8')
        
        // Match imports from lucide-react
        const lucideImportMatch = content.match(/import\s*\{([^}]+)\}\s*from\s*["']lucide-react["']/)
        expect(lucideImportMatch).not.toBeNull()
        
        const importedSymbols = lucideImportMatch![1].split(',').map(s => s.trim())
        expect(importedSymbols).toContain('Calculator')
        expect(importedSymbols).toContain('Coins')
    })

    it('TC-2: ToolsView buttons MUST eliminate 🤖 and follow Tabiji primary/secondary hierarchy', () => {
        const toolsViewPath = path.join(frontendDir, 'components', 'views', 'tools-view.tsx')
        const content = fs.readFileSync(toolsViewPath, 'utf-8')

        // Must not contain hardcoded 🤖 in actuary button
        expect(content).not.toMatch(/🤖\s*\{t\(['"]actuary_btn['"]\)/)
        
        // Primary button must use #0B3026 (Dark Forest)
        expect(content).toMatch(/bg-\[#0B3026\]/)
        
        // Secondary actuary button must use Calculator with #E56E25 (Sunrise Amber)
        expect(content).toMatch(/<Calculator[^>]*text-\[#E56E25\]/)
    })

    it('TC-3: ItineraryHeader date capsule icon MUST be dark mode adaptive (No emerald-500)', () => {
        const headerPath = path.join(frontendDir, 'components', 'itinerary', 'ItineraryHeader.tsx')
        const content = fs.readFileSync(headerPath, 'utf-8')

        // Calendar in date button must NOT be emerald-500
        expect(content).not.toMatch(/<Calendar[^>]*text-emerald-500/)
        
        // Must use #1E2927 and #E5EBEA for dark mode contrast
        expect(content).toMatch(/<Calendar[^>]*text-\[#1E2927\]\s+dark:text-\[#E5EBEA\]/)
    })

    it('TC-4: TripMasterOverview location capsule MUST eliminate green background & text', () => {
        const overviewPath = path.join(frontendDir, 'components', 'itinerary', 'TripMasterOverview.tsx')
        const content = fs.readFileSync(overviewPath, 'utf-8')

        // Location capsule must not use emerald-700 / bg-emerald-50
        expect(content).not.toMatch(/text-emerald-700\s+dark:text-emerald-300/)
        expect(content).not.toMatch(/bg-emerald-50\b/)
        
        // Must adopt subtle ink styling
        expect(content).toMatch(/text-\[#1E2927\]\s+dark:text-\[#E5EBEA\]/)
    })

    it('TC-5: i18n dictionaries MUST NOT contain hardcoded emojis in core keys', () => {
        const transPath = path.join(frontendDir, 'lib', 'translations.ts')
        const expensePath = path.join(frontendDir, 'lib', 'i18n', 'expense.ts')
        
        const transContent = fs.readFileSync(transPath, 'utf-8')
        const expenseContent = fs.readFileSync(expensePath, 'utf-8')

        // exp_split_bill must not have 🤖
        expect(transContent).not.toMatch(/exp_split_bill:\s*["']🤖/)
        expect(expenseContent).not.toMatch(/exp_split_bill:\s*["']🤖/)

        // exp_select_trip_first must not have ⚠️
        expect(transContent).not.toMatch(/exp_select_trip_first:\s*["']⚠️/)
        expect(expenseContent).not.toMatch(/exp_select_trip_first:\s*["']⚠️/)
    })

    it('TC-6: ActuaryDialogCard header MUST use native Calculator instead of 🤖', () => {
        const dialogPath = path.join(frontendDir, 'components', 'ActuaryDialogCard.tsx')
        const content = fs.readFileSync(dialogPath, 'utf-8')

        // Title must not contain 🤖
        expect(content).not.toMatch(/<DialogTitle[^>]*>\s*🤖/)
        expect(content).toMatch(/<Calculator[^>]*text-\[#E56E25\]/)
    })
})
