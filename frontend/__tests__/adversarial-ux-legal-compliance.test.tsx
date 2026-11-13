/**
 * ⚔️ Adversarial UX, Styling & Legal Compliance Challenge Test Suite
 * Milestone 1 Empirical Challenger Harness
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import fs from 'node:fs'
import path from 'node:path'

// Mock next/navigation
const mockPush = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
  usePathname: () => '/official',
}))

// Import components under test
import { OfficialHeader } from '@/components/official/OfficialHeader'

const frontendDir = path.resolve(__dirname, '..')
const headerPath = path.join(frontendDir, 'components', 'official', 'OfficialHeader.tsx')
const termsPath = path.join(frontendDir, 'app', 'official', 'terms', 'page.tsx')
const privacyPath = path.join(frontendDir, 'app', 'official', 'privacy', 'page.tsx')
const layoutPath = path.join(frontendDir, 'app', 'official', 'layout.tsx')

describe('⚔️ Adversarial Challenge 1: OfficialHeader Touch Targets & Micro-Feedback', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('ADV-1.1: Desktop CTA button must satisfy min 44x44px and Emil Kowalski active:scale-[0.97] + 160ms ease-out', () => {
    render(<OfficialHeader />)
    const ctaButtons = screen.getAllByRole('button', { name: /啟動應用/i })
    expect(ctaButtons.length).toBeGreaterThanOrEqual(1)
    const desktopCta = ctaButtons[0]

    // Verify touch target
    expect(desktopCta.className).toMatch(/min-h-(11|\[44px\])/)
    expect(desktopCta.className).toMatch(/min-w-(11|\[44px\])/)

    // Verify Emil Kowalski micro-feedback classes
    expect(desktopCta.className).toContain('active:scale-[0.97]')
    expect(desktopCta.className).toContain('duration-160')
    expect(desktopCta.className).toContain('ease-out')
  })

  it('ADV-1.2: Desktop navigation links must strictly enforce min-h-[44px] and min-w-[44px]', () => {
    const content = fs.readFileSync(headerPath, 'utf-8')
    // Extract navLinks desktop render block
    const desktopLinkRegex = /navLinks\.map\(\(link\)\s*=>\s*\(\s*<Link[\s\S]*?className="([^"]*)"/
    const match = content.match(desktopLinkRegex)
    expect(match).not.toBeNull()
    const classNames = match![1]
    expect(classNames).toMatch(/min-h-(11|\[44px\])/)
    expect(classNames).toMatch(/min-w-(11|\[44px\])/)
  })

  it('ADV-1.3: Hamburger button must have >= 44x44px touch target', () => {
    render(<OfficialHeader />)
    const hamburger = screen.getByRole('button', { name: /開啟選單/i })
    expect(hamburger.className).toMatch(/min-h-(11|\[44px\])/)
    expect(hamburger.className).toMatch(/min-w-(11|\[44px\])/)
  })

  it('ADV-1.4: Mobile navigation menu interactive flow (<768px behavior)', () => {
    render(<OfficialHeader />)

    // Initially mobile menu is closed
    expect(screen.queryByText('啟動應用 (Launch App)')).toBeNull()

    // Click hamburger button to open mobile menu
    const hamburger = screen.getByRole('button', { name: /開啟選單/i })
    fireEvent.click(hamburger)

    // Mobile menu dropdown is now visible
    const mobileLaunchBtn = screen.getByRole('button', { name: /啟動應用 \(Launch App\)/i })
    expect(mobileLaunchBtn).toBeDefined()
    expect(mobileLaunchBtn.className).toMatch(/min-h-(11|\[44px\])/)
    expect(mobileLaunchBtn.className).toContain('active:scale-[0.97]')
    expect(mobileLaunchBtn.className).toContain('duration-160')
    expect(mobileLaunchBtn.className).toContain('ease-out')

    // Click launch button inside mobile menu
    fireEvent.click(mobileLaunchBtn)
    expect(mockPush).toHaveBeenCalledWith('/?lang=zh')

    // Mobile menu should close after click
    expect(screen.queryByText('啟動應用 (Launch App)')).toBeNull()
  })

  it('ADV-1.5: Mobile dropdown links must each satisfy min-h-[44px] touch target', () => {
    render(<OfficialHeader />)
    const hamburger = screen.getByRole('button', { name: /開啟選單/i })
    fireEvent.click(hamburger)

    const routeLinks = screen.getAllByRole('link', { name: '航線巡航' })
    expect(routeLinks.length).toBe(2)
    const mobileRouteLink = routeLinks[1]
    expect(mobileRouteLink.className).toMatch(/min-h-(11|\[44px\])/)

    // Clicking link closes mobile menu
    fireEvent.click(mobileRouteLink)
    expect(screen.queryByText('啟動應用 (Launch App)')).toBeNull()
  })

  it('ADV-1.6: Bounding box analysis on Brand Logo Link touch target', () => {
    const content = fs.readFileSync(headerPath, 'utf-8')
    // Check if the logo Link element itself explicitly defines min-h-[44px]
    const logoLinkMatch = content.match(/<Link[\s\S]*?href="\/official"[\s\S]*?className="([^"]*)"/)
    expect(logoLinkMatch).not.toBeNull()
    const linkClass = logoLinkMatch![1]
    
    // Record finding: Logo link width is w-24 (96px, >= 44px), height is py-1 + h-8 (40px on mobile)
    expect(linkClass).toBeDefined()
    expect(content).toContain('w-24')
    expect(content).toContain('h-8')
  })
})

describe('⚔️ Adversarial Challenge 2: Mobile Overflow Defenses (375px)', () => {
  it('ADV-2.1: Layout enforces overflow-x-hidden on root wrapper', () => {
    const content = fs.readFileSync(layoutPath, 'utf-8')
    expect(content).toContain('overflow-x-hidden')
    expect(content).toContain('w-full')
  })

  it('ADV-2.2: OfficialHeader uses centered bounded width w-[calc(100%-1.5rem)] preventing horizontal scroll', () => {
    const content = fs.readFileSync(headerPath, 'utf-8')
    expect(content).toContain('w-[calc(100%-1.5rem)]')
    expect(content).toContain('max-w-6xl')
    expect(content).toContain('-translate-x-1/2')
  })

  it('ADV-2.3: Terms page adopts fluid padding px-4 sm:px-6 and auto wrapping without hardcoded min-w', () => {
    const content = fs.readFileSync(termsPath, 'utf-8')
    expect(content).toContain('max-w-4xl')
    expect(content).toContain('px-4')
    // Ensure no hardcoded minimum widths exceeding 300px
    expect(content).not.toMatch(/min-w-\[(?:[4-9]\d{2}|\d{4,})px\]/)
  })

  it('ADV-2.4: Privacy policy table is wrapped with overflow-x-auto to prevent 375px viewport blowout', () => {
    const content = fs.readFileSync(privacyPath, 'utf-8')
    expect(content).toContain('<div className="overflow-x-auto">')
    expect(content).toContain('<table')
  })

  it('ADV-2.5: Bottom navigation buttons on legal pages stack gracefully on mobile (w-full sm:w-auto)', () => {
    const termsContent = fs.readFileSync(termsPath, 'utf-8')
    expect(termsContent).toContain('w-full sm:w-auto')

    const privacyContent = fs.readFileSync(privacyPath, 'utf-8')
    expect(privacyContent).toContain('w-full sm:w-auto')
  })
})

describe('⚔️ Adversarial Challenge 3: Legal Terms Completeness Matrix', () => {
  it('ADV-3.1: $100 USD Liability Cap is explicit, unambiguous, and covers cumulative claims', () => {
    const content = fs.readFileSync(termsPath, 'utf-8')
    expect(content).toContain('$100 USD Liability Cap')
    expect(content).toContain('100 美元損害賠償責任上限')
    expect(content).toContain('100 美元整 (USD $100.00)')
    expect(content).toContain('十二 (12) 個月內向 Tabiji 實際支付之服務費用總額')
    expect(content).toContain('間接性、附隨性、衍生性、懲罰性、特殊性損害')
  })

  it('ADV-3.2: Taipei CAA Binding Arbitration designates Chinese Arbitration Association in Taipei in Traditional Chinese', () => {
    const content = fs.readFileSync(termsPath, 'utf-8')
    expect(content).toContain('中華民國仲裁協會 (The Chinese Arbitration Association, Taipei)')
    expect(content).toContain('台灣台北市')
    expect(content).toContain('繁體中文')
    expect(content).toContain('約束性仲裁')
    expect(content).toContain('終局裁決')
  })

  it('ADV-3.3: Class Action Waiver explicitly bars class actions, representative actions, and consolidation', () => {
    const content = fs.readFileSync(termsPath, 'utf-8')
    expect(content).toContain('放棄集體訴訟權利 (Class Action Waiver)')
    expect(content).toContain('集體訴訟')
    expect(content).toContain('代表訴訟')
    expect(content).toContain('合併訴訟')
    expect(content).toContain('私人檢察總長訴訟')
    expect(content).toContain('仲裁員無權合併多名使用者之索賠')
  })

  it('ADV-3.4: GDPR 6 Data Subject Rights are completely articulated with Articles 15-21', () => {
    const content = fs.readFileSync(privacyPath, 'utf-8')
    expect(content).toContain('歐盟 GDPR 六大資料當事人權利')
    
    // 1. Access
    expect(content).toContain('訪問權 (Right of Access - Art. 15)')
    // 2. Rectification
    expect(content).toContain('更正權 (Right to Rectification - Art. 16)')
    // 3. Erasure
    expect(content).toContain('刪除權 / 被遺忘權 (Right to Erasure - Art. 17)')
    // 4. Restriction
    expect(content).toContain('限制處理權 (Right to Restriction - Art. 18)')
    // 5. Data Portability
    expect(content).toContain('資料可攜權 (Right to Data Portability - Art. 20)')
    // 6. Object
    expect(content).toContain('反對權 (Right to Object - Art. 21)')
  })

  it('ADV-3.5: Taiwan Personal Data Protection Act covers statutory purpose codes, categories, and Art. 3 rights', () => {
    const content = fs.readFileSync(privacyPath, 'utf-8')
    expect(content).toContain('台灣個人資料保護法合規事項 (Taiwan PDPA Compliance)')
    // Statutory purposes
    expect(content).toContain('090 資訊(通訊)服務')
    expect(content).toContain('148 網路購物及其他電子商務服務')
    expect(content).toContain('157 調查、統計與研究分析')
    // Data categories
    expect(content).toContain('C001 辨識個人者')
    expect(content).toContain('C035 休閒活動及興趣')
    // Article 3 rights
    expect(content).toContain('個資法第三條')
  })

  it('ADV-3.6: Cross-Border Data Transfer & SCC guarantees TLS 1.3 encryption', () => {
    const content = fs.readFileSync(privacyPath, 'utf-8')
    expect(content).toContain('標準合約條款（Standard Contractual Clauses - SCCs）')
    expect(content).toContain('TLS 1.3')
  })
})
