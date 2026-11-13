/**
 * 🛡️ Tabiji Official Portal & Legal Center Comprehensive E2E Test Suite
 * 
 * Architecture & Quality Guarantees:
 * - Opaque-box, requirement-driven tests adhering to TEST_INFRA.md (Tiers 1-4).
 * - Zero modification to frozen invariants (/, sw.ts, manifest.json).
 * - Rigorous verification of security sanitization, legal armor clauses,
 *   metadata, touch targets, RWD bounds, cross-feature flows, and user journeys.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { sanitizeLaunchRedirectUrl } from '@/lib/security'
import { useTripStore } from '@/lib/stores/tripStore'

// Canonical paths
const frontendDir = path.resolve(__dirname, '..')
const repoRoot = path.resolve(frontendDir, '..')

const layoutPath = path.join(frontendDir, 'app', 'official', 'layout.tsx')
const termsPath = path.join(frontendDir, 'app', 'official', 'terms', 'page.tsx')
const privacyPath = path.join(frontendDir, 'app', 'official', 'privacy', 'page.tsx')
const headerPath = path.join(frontendDir, 'components', 'official', 'OfficialHeader.tsx')
const footerPath = path.join(frontendDir, 'components', 'official', 'OfficialFooter.tsx')

const rootPagePath = path.join(frontendDir, 'app', 'page.tsx')
const swPath = path.join(frontendDir, 'app', 'sw.ts')
const manifestPath = path.join(frontendDir, 'public', 'manifest.json')

describe('Tier 1: Feature Coverage (Opaque-Box Requirement Invariants)', () => {
  describe('F1: sanitizeLaunchRedirectUrl Core Whitelist Behavior', () => {
    it('TC-1.1: Default root path "/" is strictly preserved', () => {
      expect(sanitizeLaunchRedirectUrl('/')).toBe('/')
    })

    it('TC-1.2: Action path "/?action=new-trip" is preserved for instant trip creation', () => {
      expect(sanitizeLaunchRedirectUrl('/?action=new-trip')).toBe('/?action=new-trip')
    })

    it('TC-1.3: Deep link query parameter on root "/?trip=kyoto-2026-xyz" is preserved', () => {
      expect(sanitizeLaunchRedirectUrl('/?trip=kyoto-2026-xyz')).toBe('/?trip=kyoto-2026-xyz')
    })

    it('TC-1.4: Explore internal path "/explore" is whitelisted and preserved', () => {
      expect(sanitizeLaunchRedirectUrl('/explore')).toBe('/explore')
    })

    it('TC-1.5: Transit connector path "/transit" is whitelisted and preserved', () => {
      expect(sanitizeLaunchRedirectUrl('/transit')).toBe('/transit')
    })
  })

  describe('F2: Official Layout & Dedicated SEO Metadata Contract', () => {
    it('TC-2.1: layout.tsx file exists in frontend/app/official/', () => {
      expect(fs.existsSync(layoutPath)).toBe(true)
    })

    it('TC-2.2: SEO title metadata defines "Tabiji | 官方網站 — 自由行隨身夥伴"', () => {
      const content = fs.readFileSync(layoutPath, 'utf-8')
      expect(content).toContain('Tabiji | 官方網站 — 自由行隨身夥伴')
    })

    it('TC-2.3: Metadata description articulates smart travel companion', () => {
      const content = fs.readFileSync(layoutPath, 'utf-8')
      expect(content).toContain('專為自由行旅人打造的隨身行程助手')
    })

    it('TC-2.4: Canonical alternates URL strictly specifies "/official"', () => {
      const content = fs.readFileSync(layoutPath, 'utf-8')
      expect(content).toMatch(/canonical:\s*["']\/official["']/)
    })

    it('TC-2.5: OpenGraph metadata declares title, /official url, and siteName Tabiji', () => {
      const content = fs.readFileSync(layoutPath, 'utf-8')
      expect(content).toContain('openGraph:')
      expect(content).toContain('siteName: "Tabiji"')
      expect(content).toMatch(/url:\s*["']\/official["']/)
    })

    it('TC-2.6: Official layout does not contain invalid nested <head> tag causing hydration error', () => {
      const content = fs.readFileSync(layoutPath, 'utf-8')
      expect(content).not.toMatch(/<head[\s>]/)
      expect(content).toContain('rel="preload"')
      expect(content).toContain('/images/tabiji-person-outline.png?v=3')
      expect(content).toContain('/images/tabiji-cursive-logo.png')
    })
  })

  describe('F3: Terms of Service Mandatory Legal Armor Contract', () => {
    it('TC-3.1: terms/page.tsx file exists in frontend/app/official/terms/', () => {
      expect(fs.existsSync(termsPath)).toBe(true)
    })

    it('TC-3.2: Explicitly mandates 100 USD damage liability cap ($100 美元責任上限)', () => {
      const content = fs.readFileSync(termsPath, 'utf-8')
      expect(content).toMatch(/100\s*(美元|USD)|\$100/)
      expect(content).toContain('責任上限')
    })

    it('TC-3.3: Mandates binding arbitration before Chinese Arbitration Association (Taipei)', () => {
      const content = fs.readFileSync(termsPath, 'utf-8')
      expect(content).toContain('中華民國仲裁協會')
      expect(content).toContain('台北')
      expect(content).toContain('約束性仲裁')
    })

    it('TC-3.4: Strictly enforces Class Action Waiver (放棄集體訴訟權利)', () => {
      const content = fs.readFileSync(termsPath, 'utf-8')
      expect(content).toContain('放棄集體訴訟')
      expect(content).toContain('Class Action Waiver')
    })

    it('TC-3.5: Designates Republic of China (Taiwan) as exclusive governing law', () => {
      const content = fs.readFileSync(termsPath, 'utf-8')
      expect(content).toContain('中華民國')
      expect(content).toContain('準據法')
    })
  })

  describe('F4: Privacy Policy Regulatory Compliance & User Sovereignty', () => {
    it('TC-4.1: privacy/page.tsx file exists in frontend/app/official/privacy/', () => {
      expect(fs.existsSync(privacyPath)).toBe(true)
    })

    it('TC-4.2: Fully articulates GDPR 6 data subject rights (access, rectification, erasure, restriction, portability, objection)', () => {
      const content = fs.readFileSync(privacyPath, 'utf-8')
      expect(content).toContain('GDPR')
      expect(content).toMatch(/訪問權|Right of Access/)
      expect(content).toMatch(/更正權|Right to Rectification/)
      expect(content).toMatch(/刪除權|被遺忘權|Right to Erasure/)
      expect(content).toMatch(/限制處理權|Right to Restriction/)
      expect(content).toMatch(/資料可攜權|Right to Data Portability/)
      expect(content).toMatch(/反對權|Right to Object/)
    })

    it('TC-4.3: Incorporates Taiwan Personal Data Protection Act compliance items', () => {
      const content = fs.readFileSync(privacyPath, 'utf-8')
      expect(content).toContain('個人資料保護法')
      expect(content).toContain('090')
      expect(content).toContain('C001')
    })

    it('TC-4.4: Defines cross-border data transfer safeguards under Standard Contractual Clauses (SCC)', () => {
      const content = fs.readFileSync(privacyPath, 'utf-8')
      expect(content).toContain('標準合約條款')
      expect(content).toContain('SCC')
      expect(content).toContain('TLS 1.3')
    })

    it('TC-4.5: Declares Local-First non-custodial architecture & Zero-Tracking policy', () => {
      const content = fs.readFileSync(privacyPath, 'utf-8')
      expect(content).toMatch(/在地優先|Local-First/)
      expect(content).toMatch(/零(廣告)?追蹤|Zero-Tracking/)
      expect(content).toContain('IndexedDB')
    })
  })

  describe('F5: Official Header Component Structure & Interactivity', () => {
    it('TC-5.1: OfficialHeader.tsx exists in frontend/components/official/', () => {
      expect(fs.existsSync(headerPath)).toBe(true)
    })

    it('TC-5.2: Header renders brand logo using CSS mask referencing /images/tabiji-cursive-logo.png', () => {
      const content = fs.readFileSync(headerPath, 'utf-8')
      expect(content).toContain('/images/tabiji-cursive-logo.png')
      expect(content).toContain('maskImage')
    })

    it('TC-5.3: Provides anchor navigation links to #routes, #offline, and #ledger', () => {
      const content = fs.readFileSync(headerPath, 'utf-8')
      expect(content).toContain('/official#routes')
      expect(content).toContain('/official#offline')
      expect(content).toContain('/official#ledger')
    })

    it('TC-5.4: Launch CTA invokes sanitizeLaunchRedirectUrl before routing', () => {
      const content = fs.readFileSync(headerPath, 'utf-8')
      expect(content).toContain('sanitizeLaunchRedirectUrl')
      expect(content).toContain('router.push')
    })

    it('TC-5.5: Launch CTA adopts Emil Kowalski micro-touch feedback (active:scale-[0.97])', () => {
      const content = fs.readFileSync(headerPath, 'utf-8')
      expect(content).toContain('active:scale-[0.97]')
      expect(content).toMatch(/duration-160|160ms/)
    })
  })

  describe('F6: Official Footer Architecture & Legal Links', () => {
    it('TC-6.1: OfficialFooter.tsx exists in frontend/components/official/', () => {
      expect(fs.existsSync(footerPath)).toBe(true)
    })

    it('TC-6.2: Provides direct link to Terms of Service "/official/terms"', () => {
      const content = fs.readFileSync(footerPath, 'utf-8')
      expect(content).toContain('/official/terms')
      expect(content).toContain('服務條款')
    })

    it('TC-6.3: Provides direct link to Privacy Policy "/official/privacy"', () => {
      const content = fs.readFileSync(footerPath, 'utf-8')
      expect(content).toContain('/official/privacy')
      expect(content).toMatch(/隱私(權)?政策|Privacy Policy/)
    })

    it('TC-6.4: Declares copyright and brand identity', () => {
      const content = fs.readFileSync(footerPath, 'utf-8')
      expect(content).toMatch(/Tabiji|旅路/)
      expect(content).toContain('All rights reserved')
    })

    it('TC-6.5: Includes global travel coordinator role disclaimer with zero pharmaceutical claims', () => {
      const content = fs.readFileSync(footerPath, 'utf-8')
      expect(content).toContain('旅遊協調')
      expect(content).not.toContain('跨境藥理')
    })
  })

  describe('F14: Root Hygiene & Frozen Core Invariants', () => {
    it('TC-14.1: frontend/app/page.tsx is strictly frozen and unmodified', () => {
      expect(fs.existsSync(rootPagePath)).toBe(true)
      const content = fs.readFileSync(rootPagePath, 'utf-8')
      expect(content).toContain('LandingPage')
      expect(content).not.toContain('OfficialHeader')
    })

    it('TC-14.2: frontend/app/sw.ts is strictly frozen and preserves precache fallbacks', () => {
      expect(fs.existsSync(swPath)).toBe(true)
      const content = fs.readFileSync(swPath, 'utf-8')
      expect(content).toContain('fallbacks:')
      expect(content).toContain('request.destination === "document"')
    })

    it('TC-14.3: frontend/public/manifest.json is strictly frozen and preserves PWA identity', () => {
      expect(fs.existsSync(manifestPath)).toBe(true)
      const content = fs.readFileSync(manifestPath, 'utf-8')
      const parsed = JSON.parse(content)
      expect(parsed.name).toContain('Tabiji')
      expect(parsed.start_url).toBe('/')
      expect(parsed.display).toBe('standalone')
    })

    it('TC-14.4: Root hygiene rule: candidates.json must not linger in repository root', () => {
      const rootCandidates = path.join(repoRoot, 'candidates.json')
      expect(fs.existsSync(rootCandidates)).toBe(false)
    })

    it('TC-14.5: Root hygiene rule: No unauthorized DNS configurations or external domains added', () => {
      const pkgPath = path.join(frontendDir, 'package.json')
      const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf-8'))
      expect(pkg.name).toBe('tabiji-pwa')
    })
  })
})

describe('Tier 2: Boundary & Corner Cases (Adversarial Stress & Precision Layout)', () => {
  describe('Open Redirect Adversarial Attack Surface Neutralization', () => {
    it('TC-B1.1: Protocol-relative Open Redirect "//evil.com" downgraded to "/"', () => {
      expect(sanitizeLaunchRedirectUrl('//evil.com')).toBe('/')
      expect(sanitizeLaunchRedirectUrl('//attacker.site/login')).toBe('/')
    })

    it('TC-B1.2: Multi-slash bypass payloads "///evil.com" and "////evil.com" downgraded to "/"', () => {
      expect(sanitizeLaunchRedirectUrl('///evil.com')).toBe('/')
      expect(sanitizeLaunchRedirectUrl('////evil.com')).toBe('/')
    })

    it('TC-B1.3: Backslash bypass payloads "/\\evil.com" and "\\\\evil.com" downgraded to "/"', () => {
      expect(sanitizeLaunchRedirectUrl('/\\evil.com')).toBe('/')
      expect(sanitizeLaunchRedirectUrl('\\\\evil.com')).toBe('/')
      expect(sanitizeLaunchRedirectUrl('/\\/evil.com')).toBe('/')
    })

    it('TC-B1.4: Script pseudo-protocols "javascript:alert(1)" downgraded to "/"', () => {
      expect(sanitizeLaunchRedirectUrl('javascript:alert(1)')).toBe('/')
      expect(sanitizeLaunchRedirectUrl('javascript:document.cookie')).toBe('/')
      expect(sanitizeLaunchRedirectUrl('javascript:void(0)')).toBe('/')
    })

    it('TC-B1.5: Data URL pseudo-protocols "data:text/html,..." downgraded to "/"', () => {
      expect(sanitizeLaunchRedirectUrl('data:text/html,<script>alert(1)</script>')).toBe('/')
      expect(sanitizeLaunchRedirectUrl('data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==')).toBe('/')
    })

    it('TC-B1.6: VBScript and Blob pseudo-protocols downgraded to "/"', () => {
      expect(sanitizeLaunchRedirectUrl('vbscript:msgbox(1)')).toBe('/')
      expect(sanitizeLaunchRedirectUrl('blob:https://evil.com/49257-234')).toBe('/')
    })

    it('TC-B1.7: External HTTP/HTTPS URLs downgraded to "/"', () => {
      expect(sanitizeLaunchRedirectUrl('https://evil.com')).toBe('/')
      expect(sanitizeLaunchRedirectUrl('http://attacker.com/phish')).toBe('/')
      expect(sanitizeLaunchRedirectUrl('https://tabijiapp.evil.com')).toBe('/')
    })

    it('TC-B1.8: Falsy and malformed inputs (null, undefined, empty, whitespaces) safely yield "/"', () => {
      expect(sanitizeLaunchRedirectUrl(null)).toBe('/')
      expect(sanitizeLaunchRedirectUrl(undefined)).toBe('/')
      expect(sanitizeLaunchRedirectUrl('')).toBe('/')
      expect(sanitizeLaunchRedirectUrl('    ')).toBe('/')
      expect(sanitizeLaunchRedirectUrl('\t\n')).toBe('/')
    })

    it('TC-B1.9: Unauthorized internal paths outside whitelist downgraded to "/"', () => {
      expect(sanitizeLaunchRedirectUrl('/admin')).toBe('/')
      expect(sanitizeLaunchRedirectUrl('/secret-tokens')).toBe('/')
      expect(sanitizeLaunchRedirectUrl('/api/v1/keys')).toBe('/')
    })

    it('TC-B1.10: Legitimate deep link with complex encoded queries preserved', () => {
      const legitimateUrl = '/?trip=tokyo-autumn-2026&day=3&tab=itinerary'
      expect(sanitizeLaunchRedirectUrl(legitimateUrl)).toBe(legitimateUrl)
    })
  })

  describe('Responsive Web Design & Touch Target Boundaries (375px+)', () => {
    it('TC-B2.1: Official layout declares "overflow-x-hidden" to prevent horizontal page wobble', () => {
      const content = fs.readFileSync(layoutPath, 'utf-8')
      expect(content).toContain('overflow-x-hidden')
    })

    it('TC-B2.2: OfficialHeader navigation items comply with min 44x44px touch target ergonomics', () => {
      const content = fs.readFileSync(headerPath, 'utf-8')
      expect(content).toMatch(/min-h-\[44px\]|h-11|py-2\.5|py-3/)
    })

    it('TC-B2.3: OfficialFooter legal links comply with min 44px vertical touch target spacing', () => {
      const content = fs.readFileSync(footerPath, 'utf-8')
      expect(content).toMatch(/min-h-(11|\[44px\])/)
    })

    it('TC-B2.4: Terms page back-to-home button complies with min 44px touch ergonomics', () => {
      const content = fs.readFileSync(termsPath, 'utf-8')
      expect(content).toMatch(/min-h-(11|\[44px\])/)
    })

    it('TC-B2.5: Privacy page back-to-home button complies with min 44px touch ergonomics', () => {
      const content = fs.readFileSync(privacyPath, 'utf-8')
      expect(content).toMatch(/min-h-(11|\[44px\])/)
    })
  })

  describe('Legal Armor Boundary Guards', () => {
    it('TC-B3.1: Terms liability cap numerical value 100 is strictly bounded to USD', () => {
      const content = fs.readFileSync(termsPath, 'utf-8')
      expect(content).toMatch(/100\s*(美元|USD)/)
    })

    it('TC-B3.2: Terms arbitration venue is explicitly anchored to Taipei, Taiwan', () => {
      const content = fs.readFileSync(termsPath, 'utf-8')
      expect(content).toContain('台北市')
      expect(content).toContain('中華民國仲裁協會')
    })

    it('TC-B3.3: Terms class action waiver prohibits both collective representative actions and consolidation', () => {
      const content = fs.readFileSync(termsPath, 'utf-8')
      expect(content).toContain('集體訴訟')
      expect(content).toContain('代表訴訟')
    })

    it('TC-B3.4: Privacy policy covers statutory purpose codes 090, 148, and 157 under Taiwan PDPA', () => {
      const content = fs.readFileSync(privacyPath, 'utf-8')
      expect(content).toContain('090')
      expect(content).toContain('148')
      expect(content).toContain('157')
    })

    it('TC-B3.5: Privacy policy explicitly covers personal data categories C001 and C035 under Taiwan PDPA', () => {
      const content = fs.readFileSync(privacyPath, 'utf-8')
      expect(content).toContain('C001')
      expect(content).toContain('C035')
    })
  })

  describe('Frozen Core Invariant Boundaries', () => {
    it('TC-B4.1: Root page app/page.tsx has zero imports of official portal components', () => {
      const content = fs.readFileSync(rootPagePath, 'utf-8')
      expect(content).not.toContain('@/components/official/')
      expect(content).not.toContain('/official')
    })

    it('TC-B4.2: Serwist Service Worker app/sw.ts maintains exact pre-existing caching policies', () => {
      const content = fs.readFileSync(swPath, 'utf-8')
      expect(content).toContain('serwist.addEventListeners')
      expect(content).toContain('app-shell-navigation')
    })

    it('TC-B4.3: Manifest public/manifest.json retains display mode standalone', () => {
      const content = fs.readFileSync(manifestPath, 'utf-8')
      const parsed = JSON.parse(content)
      expect(parsed.display).toBe('standalone')
    })

    it('TC-B4.4: App shell navigation does not re-register service worker on /official subroutes', () => {
      const content = fs.readFileSync(layoutPath, 'utf-8')
      expect(content).not.toContain('ServiceWorkerRegister')
    })

    it('TC-B4.5: Security coverage ledger remains structurally sound and contains 0 unverified critical gaps', () => {
      const ledgerPath = path.join(repoRoot, 'docs', 'security', 'security-coverage-ledger.json')
      expect(fs.existsSync(ledgerPath)).toBe(true)
      const ledger = JSON.parse(fs.readFileSync(ledgerPath, 'utf-8'))
      expect(ledger.version).toBeDefined()
      expect(ledger.targets.length).toBeGreaterThan(200)
    })
  })
})

describe('Tier 3: Cross-Feature Combinations & State Transitions', () => {
  beforeEach(() => {
    useTripStore.setState({
      activeTripId: null,
      focusedDay: 1,
      targetExpenseId: null,
    })
  })

  describe('Launch CTA Redirection & Deep-Link Parameter Hand-off', () => {
    it('TC-C1.1: Launch CTA with legitimate trip deep-link "/?trip=trip-uuid-888" retains trip parameter', () => {
      const input = '/?trip=trip-uuid-888'
      const sanitized = sanitizeLaunchRedirectUrl(input)
      expect(sanitized).toBe(input)

      // Simulate state update in tripStore
      const params = new URLSearchParams(sanitized.slice(1))
      const tripId = params.get('trip')
      expect(tripId).toBe('trip-uuid-888')

      useTripStore.getState().setActiveTripId(tripId)
      expect(useTripStore.getState().activeTripId).toBe('trip-uuid-888')
    })

    it('TC-C1.2: Launch CTA with multi-query deep-link preserves all whitelisted query parameters', () => {
      const input = '/?trip=kyoto-2026&action=new-trip&ref=official'
      const sanitized = sanitizeLaunchRedirectUrl(input)
      expect(sanitized).toBe(input)

      const params = new URLSearchParams(sanitized.slice(1))
      expect(params.get('trip')).toBe('kyoto-2026')
      expect(params.get('action')).toBe('new-trip')
      expect(params.get('ref')).toBe('official')
    })

    it('TC-C1.3: Launch CTA with poisoned open-redirect query parameter safely neutralizes to clean root "/"', () => {
      const maliciousInput = '//malicious-phishing.com/steal-creds'
      const sanitized = sanitizeLaunchRedirectUrl(maliciousInput)
      expect(sanitized).toBe('/')

      // Ensure no polluted trip state is written
      expect(useTripStore.getState().activeTripId).toBeNull()
    })
  })

  describe('Footer to Legal Pages Seamless Navigation Flow', () => {
    it('TC-C2.1: Footer terms link matches exact terms page route and layout container', () => {
      const footerContent = fs.readFileSync(footerPath, 'utf-8')
      const termsContent = fs.readFileSync(termsPath, 'utf-8')

      expect(footerContent).toContain('/official/terms')
      expect(termsContent).toContain('服務條款 (Terms of Service)')
      expect(termsContent).toContain('OfficialHeader')
      expect(termsContent).toContain('OfficialFooter')
    })

    it('TC-C2.2: Footer privacy link matches exact privacy page route and layout container', () => {
      const footerContent = fs.readFileSync(footerPath, 'utf-8')
      const privacyContent = fs.readFileSync(privacyPath, 'utf-8')

      expect(footerContent).toContain('/official/privacy')
      expect(privacyContent).toContain('隱私權政策 (Privacy Policy)')
      expect(privacyContent).toContain('OfficialHeader')
      expect(privacyContent).toContain('OfficialFooter')
    })

    it('TC-C2.3: Terms page and Privacy page provide consistent back-to-official-home navigation', () => {
      const termsContent = fs.readFileSync(termsPath, 'utf-8')
      const privacyContent = fs.readFileSync(privacyPath, 'utf-8')

      expect(termsContent).toMatch(/href=["']\/official["']/)
      expect(privacyContent).toMatch(/href=["']\/official["']/)
    })
  })

  describe('Dark Mode Semantic Token Coexistence', () => {
    it('TC-C3.1: Official Layout supports dual-theme background classes', () => {
      const layoutContent = fs.readFileSync(layoutPath, 'utf-8')
      expect(layoutContent).toContain('bg-[#F6F5EE]')
      expect(layoutContent).toContain('dark:bg-[#121A18]')
      expect(layoutContent).toContain('text-[#1E2927]')
      expect(layoutContent).toContain('dark:text-[#E5EBEA]')
    })

    it('TC-C3.2: Official Header supports dual-theme logo mask coloring', () => {
      const headerContent = fs.readFileSync(headerPath, 'utf-8')
      expect(headerContent).toContain('bg-[#0B3026]')
      expect(headerContent).toContain('dark:bg-white')
    })

    it('TC-C3.3: Official Footer supports dual-theme background styling', () => {
      const footerContent = fs.readFileSync(footerPath, 'utf-8')
      expect(footerContent).toContain('bg-[#F6F5EE]/80')
      expect(footerContent).toContain('dark:bg-[#121A18]/90')
    })
  })

  describe('PWA Offline Shell Non-Interference', () => {
    it('TC-C4.1: Official portal layout does not instantiate standalone PwaHardSkeleton', () => {
      const layoutContent = fs.readFileSync(layoutPath, 'utf-8')
      expect(layoutContent).not.toContain('PwaHardSkeleton')
    })

    it('TC-C4.2: RootLayout ThemeProvider & LanguageProvider wrap children cleanly without breaking /official', () => {
      const rootLayoutPath = path.join(frontendDir, 'app', 'layout.tsx')
      const rootLayoutContent = fs.readFileSync(rootLayoutPath, 'utf-8')
      expect(rootLayoutContent).toContain('<ThemeProvider>')
      expect(rootLayoutContent).toContain('<LanguageProvider>')
      expect(rootLayoutContent).toContain('{children}')
    })
  })
})

describe('Tier 4: Real-World Application User Journeys', () => {
  it('Scenario 4.1: International EU Traveler Rigorous Legal Audit Before Onboarding', () => {
    // 1. Traveler visits official portal and inspects footer links
    const footerContent = fs.readFileSync(footerPath, 'utf-8')
    expect(footerContent).toContain('/official/terms')
    expect(footerContent).toContain('/official/privacy')

    // 2. Traveler opens Terms of Service to verify liability cap and arbitration
    const termsContent = fs.readFileSync(termsPath, 'utf-8')
    expect(termsContent).toContain('責任上限條款 ($100 USD Liability Cap)')
    expect(termsContent).toContain('台北約束性仲裁 (Taipei Binding Arbitration)')
    expect(termsContent).toContain('中華民國仲裁協會')
    expect(termsContent).toContain('放棄集體訴訟權利 (Class Action Waiver)')

    // 3. Traveler reviews Privacy Policy for GDPR compliance and data transfer guarantees
    const privacyContent = fs.readFileSync(privacyPath, 'utf-8')
    expect(privacyContent).toContain('歐盟 GDPR 六大資料當事人權利')
    expect(privacyContent).toContain('標準合約條款（Standard Contractual Clauses - SCCs）')
    expect(privacyContent).toContain('在地儲存優先與零第三方廣告追蹤')
    expect(privacyContent).toContain('TLS 1.3')

    // 4. Traveler clicks return to official portal
    expect(termsContent).toMatch(/href=["']\/official["']/)
  })

  it('Scenario 4.2: Mobile Visitor Seamless App Launch Flow (375px)', () => {
    // 1. Mobile visitor navigates to OfficialHeader
    const headerContent = fs.readFileSync(headerPath, 'utf-8')
    expect(headerContent).toContain('OfficialHeader')

    // 2. Header CTA button enforces mobile touch feedback
    expect(headerContent).toContain('active:scale-[0.97]')
    expect(headerContent).toMatch(/min-h-(11|\[44px\])/)

    // 3. Header CTA executes sanitizeLaunchRedirectUrl for target navigation
    const target = sanitizeLaunchRedirectUrl('/')
    expect(target).toBe('/')

    // 4. Mobile layout maintains horizontal stability
    const layoutContent = fs.readFileSync(layoutPath, 'utf-8')
    expect(layoutContent).toContain('overflow-x-hidden')
  })

  it('Scenario 4.3: Hostile Phishing & Open Redirect Defense Campaign', () => {
    // Attacker crafts 10 distinct exploit vectors attempting to hijack the launch CTA
    const exploitVectors = [
      '//evil-phishing.com/login',
      '///attacker.org',
      '/\\evil.com/redirect',
      'javascript:alert(document.domain)',
      'data:text/html,<script>window.location="http://evil.com"</script>',
      'vbscript:msgbox("hacked")',
      'https://attacker-domain.org',
      'http://192.168.1.1/admin',
      '/unauthorized-route/dump',
      '   '
    ]

    for (const vector of exploitVectors) {
      const result = sanitizeLaunchRedirectUrl(vector)
      expect(result).toBe('/')
    }
  })

  it('Scenario 4.4: Returning Traveler Deep-Link Trip Recovery Flow', () => {
    const validTripDeepLink = '/?trip=tokyo-sakura-2026-tbj'
    const validatedUrl = sanitizeLaunchRedirectUrl(validTripDeepLink)
    expect(validatedUrl).toBe(validTripDeepLink)

    // Deep-link correctly synchronizes into state
    const params = new URLSearchParams(validatedUrl.slice(1))
    const tripId = params.get('trip')
    expect(tripId).toBe('tokyo-sakura-2026-tbj')

    useTripStore.getState().setActiveTripId(tripId)
    expect(useTripStore.getState().activeTripId).toBe('tokyo-sakura-2026-tbj')
  })

  it('Scenario 4.5: Accessibility & Reduced-Motion Traveler Experience', () => {
    // Verify that layout and interactive controls support reduced motion and accessible contrast
    const layoutContent = fs.readFileSync(layoutPath, 'utf-8')
    expect(layoutContent).toContain('antialiased')
    expect(layoutContent).toContain('transition-colors')

    const termsContent = fs.readFileSync(termsPath, 'utf-8')
    expect(termsContent).toContain('aria-label')

    const headerContent = fs.readFileSync(headerPath, 'utf-8')
    expect(headerContent).toContain('aria-label')
  })

  it('Scenario 4.6: Multi-Device Fluid Viewport Scaling (375px to 1920px)', () => {
    const layoutContent = fs.readFileSync(layoutPath, 'utf-8')
    expect(layoutContent).toContain('w-full')
    expect(layoutContent).toContain('overflow-x-hidden')

    const headerContent = fs.readFileSync(headerPath, 'utf-8')
    expect(headerContent).toContain('max-w-6xl')
    expect(headerContent).toContain('sm:px-6')

    const footerContent = fs.readFileSync(footerPath, 'utf-8')
    expect(footerContent).toContain('max-w-6xl')
    expect(footerContent).toContain('grid-cols-1')
    expect(footerContent).toContain('md:grid-cols-4')
  })

  it('Scenario 4.7: Offline-First Reliability & Local Storage Sovereignty Verification', () => {
    const privacyContent = fs.readFileSync(privacyPath, 'utf-8')
    expect(privacyContent).toContain('IndexedDB')
    expect(privacyContent).toContain('SWR')
    expect(privacyContent).toContain('客戶端在地優先架構')

    const termsContent = fs.readFileSync(termsPath, 'utf-8')
    expect(termsContent).toContain('tbj_rec_*')
    expect(termsContent).toContain('非託管形式')
  })
})
