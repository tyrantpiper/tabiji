import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

describe('🛡️ Security Sentinel: Expense View Toggle & Share Ledger Icon Harmony Audit', () => {
    const frontendDir = path.resolve(__dirname, '..')

    it('TC-1: remaining.ts tv_list MUST NOT contain hardcoded clipboard emoji 📋', () => {
        const remainingPath = path.join(frontendDir, 'lib', 'i18n', 'remaining.ts')
        const content = fs.readFileSync(remainingPath, 'utf-8')

        expect(content).not.toMatch(/tv_list:\s*["']📋/)
        expect(content).toMatch(/tv_list:\s*["']List["']/)
        expect(content).toMatch(/tv_list:\s*["']列表["']/)
    })

    it('TC-2: expense.ts & translations.ts exp_shared_ledger MUST NOT contain link emoji 🔗', () => {
        const expensePath = path.join(frontendDir, 'lib', 'i18n', 'expense.ts')
        const transPath = path.join(frontendDir, 'lib', 'translations.ts')
        
        const expenseContent = fs.readFileSync(expensePath, 'utf-8')
        const transContent = fs.readFileSync(transPath, 'utf-8')

        expect(expenseContent).not.toMatch(/exp_shared_ledger:\s*["']🔗/)
        expect(transContent).not.toMatch(/exp_shared_ledger:\s*["']🔗/)

        expect(expenseContent).toMatch(/exp_shared_ledger:\s*["']Share Ledger["']/)
        expect(expenseContent).toMatch(/exp_shared_ledger:\s*["']分享公帳["']/)
        expect(transContent).toMatch(/exp_shared_ledger:\s*["']Share Ledger["']/)
        expect(transContent).toMatch(/exp_shared_ledger:\s*["']分享公帳["']/)
    })

    it('TC-3: tools-view.tsx view toggle buttons MUST use Tabiji primary #0B3026 (No generic slate-900)', () => {
        const toolsViewPath = path.join(frontendDir, 'components', 'views', 'tools-view.tsx')
        const content = fs.readFileSync(toolsViewPath, 'utf-8')

        // Target the expense toggle buttons section around line 840-860
        expect(content).not.toMatch(/expenseView\s*===\s*['"]summary['"]\s*\?\s*['"]bg-slate-900/)
        expect(content).not.toMatch(/expenseView\s*===\s*['"]daily['"]\s*\?\s*['"]bg-slate-900/)

        // Must use #0B3026 for active state
        expect(content).toMatch(/expenseView\s*===\s*['"]summary['"]\s*\?[^:]*bg-\[#0B3026\]/)
        expect(content).toMatch(/expenseView\s*===\s*['"]daily['"]\s*\?[^:]*bg-\[#0B3026\]/)
    })

    it('TC-4: tools-view.tsx share button MUST eliminate text-indigo-600 and adopt Tabiji brand palette', () => {
        const toolsViewPath = path.join(frontendDir, 'components', 'views', 'tools-view.tsx')
        const content = fs.readFileSync(toolsViewPath, 'utf-8')

        // Must not contain text-indigo-600 on share button
        expect(content).not.toMatch(/text-indigo-600\s+hover:text-indigo-700/)

        // Must adopt Tabiji #0B3026 text token with hover
        expect(content).toMatch(/text-\[#0B3026\]\s+dark:text-\[#E5EBEA\]\s+hover:bg-\[#0B3026\]\/10/)
    })

    it('TC-5: tools-view.tsx toggle and share icons MUST eliminate redundant mr-2 / mr-1.5 margins', () => {
        const toolsViewPath = path.join(frontendDir, 'components', 'views', 'tools-view.tsx')
        const content = fs.readFileSync(toolsViewPath, 'utf-8')

        // Must eliminate margin classes that conflict with Button's gap-1.5
        expect(content).not.toMatch(/<PieChart[^>]*mr-2/)
        expect(content).not.toMatch(/<List[^>]*mr-2/)
        expect(content).not.toMatch(/<Share2[^>]*mr-1\.5/)
    })
})
