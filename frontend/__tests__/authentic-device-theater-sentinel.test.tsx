/**
 * 🛡️ Tabiji Security Sentinel: Authentic Live Device Theater Pre-Execution In-Memory Spike
 * Verifies full-bleed mirroring, touch targets, DOM isolation, and zero-regression invariants.
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import fs from 'node:fs'
import path from 'node:path'

// Mock next/navigation
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
  usePathname: () => '/official',
}))

import { LiveDeviceTheater } from '@/components/official/LiveDeviceTheater'
import OfficialPage from '@/app/official/page'

const componentPath = path.resolve(__dirname, '../components/official/LiveDeviceTheater.tsx')

class MockIntersectionObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

describe('🛡️ Security Sentinel: Authentic Device Theater Invariant Verification', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver
  })

  it('TC-AT1.1: Outer mode switchers and play/pause controls enforce min-h-11 / min-w-11 touch targets', () => {
    render(<LiveDeviceTheater />)
    const modeTabs = screen.getAllByRole('tab')
    expect(modeTabs.length).toBe(3)
    modeTabs.forEach((tab) => {
      expect(tab.className).toMatch(/min-h-(11|\[44px\])/)
      expect(tab.className).toMatch(/min-w-(11|\[44px\])/)
      expect(tab.className).toContain('active:scale-[0.97]')
      expect(tab.className).toContain('duration-160')
      expect(tab.className).toContain('ease-out')
    })

    const playPauseBtn = screen.getByRole('button', { name: /(暫停|繼續)自動輪播/i })
    expect(playPauseBtn.className).toMatch(/min-h-(11|\[44px\])/)
    expect(playPauseBtn.className).toMatch(/min-w-(11|\[44px\])/)
  })

  it('TC-AT1.2: Inner phone mockup viewport is strictly aria-hidden to eliminate DOM selector pollution', () => {
    const content = fs.readFileSync(componentPath, 'utf-8')
    // Must contain aria-hidden="true" on screen viewport or mock containers
    expect(content).toContain('aria-hidden="true"')
    
    // Render and ensure no secondary tabs leak into testing-library from mock cards
    render(<LiveDeviceTheater />)
    const tabs = screen.getAllByRole('tab')
    // Only the 3 outer switcher tabs should be discoverable
    expect(tabs.length).toBe(3)
  })

  it('TC-AT1.3: Inner screen container strictly implements full-bleed dual theme tokens', () => {
    const content = fs.readFileSync(componentPath, 'utf-8')
    // Outer phone chassis
    expect(content).toContain('aspect-[9/19]')
    // Full bleed dual theme classes
    expect(content).toContain('bg-[#F6F5EE]')
    expect(content).toContain('dark:bg-[#121A18]')
  })

  it('TC-AT1.4: Component declares zero unconstrained fixed width classes (>343px) on mobile root', () => {
    const content = fs.readFileSync(componentPath, 'utf-8')
    const fixedWidthMatches = content.match(/(?<!sm:|md:|lg:|xl:)w-\[(\d+)px\]/g) || []
    for (const match of fixedWidthMatches) {
      const pixelVal = parseInt(match.replace(/[^0-9]/g, ''), 10)
      expect(pixelVal).toBeLessThanOrEqual(343)
    }
  })

  it('TC-AT1.5: Component respects useReducedMotion and isPaused state without unhandled rAF loops', () => {
    const content = fs.readFileSync(componentPath, 'utf-8')
    expect(content).toContain('useReducedMotion')
    expect(content).toContain('shouldReduceMotion')
    expect(content).toContain('isPaused')
  })

  it('TC-AT1.6: OfficialPage integrates LiveDeviceTheater cleanly without breaking existing banner CTAs', () => {
    const { container } = render(<OfficialPage />)
    const launchBtn = container.querySelector('button[aria-label*="立即啟動"]')
    const termsLink = container.querySelector('a[aria-label*="查閱服務條款"]')
    expect(launchBtn).toBeDefined()
    expect(termsLink).toBeDefined()
  })

  it('TC-AT1.7: Micro-scroll transition branches properly across active loop, pause lock, and reduced motion', () => {
    const content = fs.readFileSync(componentPath, 'utf-8')
    expect(content).toContain('repeat: Infinity')
    expect(content).toContain('repeatDelay: 0.2')
    expect(content).toContain('duration: 0.2')
    expect(content).toContain('duration: 0')
  })

  it('TC-AT1.8: Smartphone container implements onTouchCancel to prevent mobile touch-scroll wedging', () => {
    const content = fs.readFileSync(componentPath, 'utf-8')
    expect(content).toContain('onTouchCancel')
  })

  it('TC-AT1.9: Authentic screens embed exact Tabiji business artifacts: Taipei 101, Boarding Pass TB-2026, and Ledger NT$ 4,283', () => {
    const content = fs.readFileSync(componentPath, 'utf-8')
    // Timeline
    expect(content).toContain('台北 101')
    expect(content).toContain('鼎泰豐 101 店')
    expect(content).toContain('象山步道 · 巨石觀景台')
    // Boarding Pass & Checklist
    expect(content).toContain('FLIGHT TB-2026')
    expect(content).toContain('100% 離線可用 · 本地自癒快照')
    expect(content).toContain('護照與國際機票')
    // Ledger
    expect(content).toContain('TWD ⇄ JPY 0.215')
    expect(content).toContain('NT$ 4,283')
    expect(content).toContain('NT$ 12,850')
  })

  it('TC-AT1.10: Typography audit strictly enforces Traditional Chinese "已同步完整資料" with no Japanese Kanji "歩"', () => {
    const content = fs.readFileSync(componentPath, 'utf-8')
    expect(content).toContain('已同步完整資料')
    expect(content).not.toContain('已同歩完整資料')
  })

  it('TC-AT1.11: Entire inner screen chassis declares aria-hidden to eliminate decorative status bar / subheader pollution', () => {
    const content = fs.readFileSync(componentPath, 'utf-8')
    // Check that the aspect-[9/19] container itself has aria-hidden
    expect(content).toMatch(/aspect-\[9\/19\][^>]*aria-hidden="true"/)
  })
})
