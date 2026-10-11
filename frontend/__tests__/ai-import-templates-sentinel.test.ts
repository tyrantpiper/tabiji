import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

describe('AI Import Template Consistency & Globalization Sentinel (Patched)', () => {
    const wizardPath = path.resolve(__dirname, '../components/itinerary/AiImportTripWizard.tsx')
    const content = fs.readFileSync(wizardPath, 'utf-8')

    it('[VERIFIED PATCH] ensures 3 global continents (Asia, Europe, Americas) with exactly 5 complete days', () => {
        // 1. 驗證三大洲代表範本存在 (中文版)
        expect(content.includes('🇯🇵 東京 5 日自由行')).toBe(true)
        expect(content.includes('🇫🇷 巴黎 5 日藝文浪漫')).toBe(true)
        expect(content.includes('🇺🇸 紐約 5 日都會經典')).toBe(true)

        // 2. 驗證三大洲代表範本存在 (英文版)
        expect(content.includes('🇯🇵 Tokyo 5-Day Highlights')).toBe(true)
        expect(content.includes('🇫🇷 Paris 5-Day Cultural Romance')).toBe(true)
        expect(content.includes('🇺🇸 NYC 5-Day Urban Explorer')).toBe(true)

        // 3. 驗證東京行程完整包含 Day 1 ~ Day 5
        expect(content.includes('## Day 1 (10/01)')).toBe(true)
        expect(content.includes('## Day 2 (10/02)')).toBe(true)
        expect(content.includes('## Day 3 (10/03)')).toBe(true)
        expect(content.includes('## Day 4 (10/04)')).toBe(true)
        expect(content.includes('## Day 5 (10/05)')).toBe(true)

        // 4. 驗證巴黎行程完整包含 Day 1 ~ Day 5
        expect(content.includes('## Day 1 (05/10)')).toBe(true)
        expect(content.includes('## Day 2 (05/11)')).toBe(true)
        expect(content.includes('## Day 3 (05/12)')).toBe(true)
        expect(content.includes('## Day 4 (05/13)')).toBe(true)
        expect(content.includes('## Day 5 (05/14)')).toBe(true)

        // 5. 驗證紐約行程完整包含 Day 1 ~ Day 5
        expect(content.includes('## Day 1 (09/18)')).toBe(true)
        expect(content.includes('## Day 2 (09/19)')).toBe(true)
        expect(content.includes('## Day 3 (09/20)')).toBe(true)
        expect(content.includes('## Day 4 (09/21)')).toBe(true)
        expect(content.includes('## Day 5 (09/22)')).toBe(true)

        // 6. 驗證多語系響應式切換
        expect(content.includes('const templatePills = zh ? TEMPLATE_PILLS_ZH : TEMPLATE_PILLS_EN')).toBe(true)
        expect(content.includes('Template loaded! Click below to start parsing.')).toBe(true)
    })
})
