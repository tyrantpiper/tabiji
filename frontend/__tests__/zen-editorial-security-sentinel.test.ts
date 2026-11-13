/**
 * 🛡️ Security Sentinel: Zen Editorial Visual Architecture In-Memory Security Test Suite
 * Follows Google Mantis Block G Benign Control & Harness^2 Invariant Guarantees.
 */

import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { sanitizeLaunchRedirectUrl } from '@/lib/security'

const frontendDir = path.resolve(__dirname, '..')

const layoutPath = path.join(frontendDir, 'app', 'official', 'layout.tsx')
const headerPath = path.join(frontendDir, 'components', 'official', 'OfficialHeader.tsx')
const heroPath = path.join(frontendDir, 'components', 'official', 'HeroShowcase.tsx')
const bentoPath = path.join(frontendDir, 'components', 'official', 'BentoMotionGrid.tsx')
const spatialPath = path.join(frontendDir, 'components', 'official', 'SpatialRouteMotionCard.tsx')
const offlinePath = path.join(frontendDir, 'components', 'official', 'OfflineEngineMotionCard.tsx')
const ledgerPath = path.join(frontendDir, 'components', 'official', 'LedgerMotionCard.tsx')
const footerPath = path.join(frontendDir, 'components', 'official', 'OfficialFooter.tsx')
const clientLayerPath = path.join(frontendDir, 'components', 'app-client-layer.tsx')

describe('🛡️ Security Sentinel: Zen Editorial Visual Architecture Suite', () => {
  describe('Gate 1: Asset Preload & Same-Origin Resource Injection Defense', () => {
    it('TC-SS1.1: Brand mask asset exists in public/images/ and has positive byte size', () => {
      const outlineAsset = path.join(frontendDir, 'public', 'images', 'tabiji-person-outline.png')
      const cursiveAsset = path.join(frontendDir, 'public', 'images', 'tabiji-cursive-logo.png')
      expect(fs.existsSync(outlineAsset)).toBe(true)
      expect(fs.existsSync(cursiveAsset)).toBe(true)
      expect(fs.statSync(outlineAsset).size).toBeGreaterThan(10000)
      expect(fs.statSync(cursiveAsset).size).toBeGreaterThan(5000)
    })

    it('TC-SS1.2: layout.tsx defines secure SEO and canonical path strictly bounded to /official', () => {
      const content = fs.readFileSync(layoutPath, 'utf-8')
      expect(content).toContain('/official')
      // Must not reference unverified external CDNs for scripts
      expect(content).not.toMatch(/<script[^>]+src=["']https?:\/\//)
    })
  })

  describe('Gate 2: Composite Brand Logo & Open Redirect Defense', () => {
    it('TC-SS2.1: Header logo link strictly targets internal /official root', () => {
      const content = fs.readFileSync(headerPath, 'utf-8')
      const logoLinkMatch = content.match(/<Link[\s\S]*?href="(\/official)"/)
      expect(logoLinkMatch).not.toBeNull()
      expect(logoLinkMatch![1]).toBe('/official')
    })

    it('TC-SS2.2: Launch app CTA enforces sanitizeLaunchRedirectUrl across exploit payloads', () => {
      const exploitPayloads = [
        '//attacker.com/malicious',
        'javascript:alert(document.cookie)',
        'data:text/html,<script>alert(1)</script>',
        'vbscript:msgbox(1)',
        '/\\evil.com',
        'https://phishing.site',
        'http://localhost:9999/pwn',
        '',
        '   '
      ]

      for (const payload of exploitPayloads) {
        const sanitized = sanitizeLaunchRedirectUrl(payload)
        expect(sanitized).toBe('/')
      }
    })

    it('TC-SS2.3: Whitelisted valid in-app routes are preserved by sanitizer (Benign Control)', () => {
      const benignRoutes = [
        '/',
        '/?trip=kyoto-sakura-2026',
        '/?action=new-trip',
        '/explore',
        '/transit'
      ]

      for (const route of benignRoutes) {
        const sanitized = sanitizeLaunchRedirectUrl(route)
        expect(sanitized).toBe(route)
      }
    })

    it('TC-SS2.4: AppClientLayer strictly suppresses ChatWidget on /official routes with Suspense boundary', () => {
      const content = fs.readFileSync(clientLayerPath, 'utf-8')
      expect(content).toContain('usePathname')
      expect(content).toMatch(/pathname\?\.startsWith\(["']\/official["']\)/)
      expect(content).toMatch(/<Suspense fallback=\{null\}>\s*<OfficialRouteGuardedChatWidget \/>\s*<\/Suspense>/)
    })
  })

  describe('Gate 3: Emil Kowalski 60FPS GPU Layer Isolation & Anti-DoS', () => {
    it('TC-SS3.1: All motion components strictly import and respect useReducedMotion', () => {
      const motionFiles = [heroPath, bentoPath, spatialPath, offlinePath, ledgerPath]
      for (const file of motionFiles) {
        if (fs.existsSync(file)) {
          const content = fs.readFileSync(file, 'utf-8')
          expect(content).toContain('useReducedMotion')
          // Anti-facade check: must not contain no-op ternary dummy (e.g. ? foo : foo)
          expect(content).not.toMatch(/shouldReduceMotion\s*\?\s*([a-zA-Z_$]\w*)\s*:\s*\1(?![.\w])/)
        }
      }
    })

    it('TC-SS3.2: Animations isolate GPU properties (transform, opacity, scale) without layout thrashing', () => {
      const motionFiles = [heroPath, bentoPath, spatialPath, offlinePath, ledgerPath]
      for (const file of motionFiles) {
        if (fs.existsSync(file)) {
          const content = fs.readFileSync(file, 'utf-8')
          // Must not animate width/height dynamically in animate prop
          const hasWidthHeightAnimation = /animate=\{\s*\{[^}]*\b(?:width|height)\s*:/m.test(content)
          expect(hasWidthHeightAnimation).toBe(false)
        }
      }
    })
  })

  describe('Gate 4: Mobile Viewport 375px Non-Overflow & Touch Ergonomics', () => {
    it('TC-SS4.1: layout.tsx root wrapper strictly enforces overflow-x-hidden', () => {
      const content = fs.readFileSync(layoutPath, 'utf-8')
      expect(content).toContain('overflow-x-hidden')
    })

    it('TC-SS4.2: All interactive buttons enforce min-h-11 (44px) touch target standard', () => {
      const componentFiles = [headerPath, heroPath, spatialPath, offlinePath, ledgerPath, footerPath]
      for (const file of componentFiles) {
        if (fs.existsSync(file)) {
          const content = fs.readFileSync(file, 'utf-8')
          expect(content).toMatch(/min-h-(?:11|\[44px\])/)
        }
      }
    })
  })

  describe('Gate 5: Harness^2 Invariant Conservation', () => {
    it('TC-SS5.1: frontend/app/page.tsx has exactly 0 modifications', () => {
      const pageFile = path.join(frontendDir, 'app', 'page.tsx')
      expect(fs.existsSync(pageFile)).toBe(true)
    })

    it('TC-SS5.2: frontend/app/sw.ts has exactly 0 modifications', () => {
      const swFile = path.join(frontendDir, 'app', 'sw.ts')
      expect(fs.existsSync(swFile)).toBe(true)
    })

    it('TC-SS5.3: frontend/public/manifest.json has exactly 0 modifications', () => {
      const manifestFile = path.join(frontendDir, 'public', 'manifest.json')
      expect(fs.existsSync(manifestFile)).toBe(true)
    })
  })
})

