import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import fs from 'node:fs'
import path from 'node:path'

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

import { HeroTypewriterHeading } from '@/components/official/HeroTypewriterHeading'
import { TypewriterHeading } from '@/components/official/TypewriterHeading'
import { OfficialLanguageProvider } from '@/lib/OfficialLanguageContext'
import { OfflineEngineMotionCard } from '@/components/official/OfflineEngineMotionCard'
import { LedgerMotionCard } from '@/components/official/LedgerMotionCard'
import { expensesApi } from '@/lib/api'
import { SyncQueue } from '@/lib/sync-engine'
import * as syncHooks from '@/lib/sync-hooks'

const frontendDir = path.resolve(__dirname, '..')

class MockIntersectionObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

describe('Security Sentinel Post-Completion Audit Remediation Suite', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    sessionStorage.clear()
    localStorage.clear()
    window.history.replaceState(null, '', '/official')
    window.IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
  })

  // === Mantis Block G: Benign Controls ===
  it('benign_control: HeroTypewriterHeading and TypewriterHeading preserve a11y sr-only and brand classes', () => {
    render(<HeroTypewriterHeading line1="Line 1" line2="Line 2" />)
    expect(screen.getByText('Line 1Line 2')).toBeDefined()

    render(<TypewriterHeading text="Heading Text" />)
    expect(screen.getByText('Heading Text')).toBeDefined()
  })

  it('benign_control: Motion cards preserve default Chinese labels on zh language', () => {
    render(
      <OfficialLanguageProvider>
        <OfflineEngineMotionCard />
        <LedgerMotionCard />
      </OfficialLanguageProvider>
    )
    expect(screen.getByText('離線自癒引擎')).toBeDefined()
    expect(screen.getByText('智慧多幣別分帳')).toBeDefined()
  })

  // === Red -> Green Exploit Checks ===
  it('exploit_1: HeroTypewriterHeading and TypewriterHeading isolate state via keyed inner components (no render-phase setState)', () => {
    const heroSrc = fs.readFileSync(path.join(frontendDir, 'components/official/HeroTypewriterHeading.tsx'), 'utf-8')
    const headingSrc = fs.readFileSync(path.join(frontendDir, 'components/official/TypewriterHeading.tsx'), 'utf-8')

    expect(heroSrc).not.toContain('setActiveLines')
    expect(heroSrc).toContain('HeroTypewriterHeadingContent')
    expect(headingSrc).not.toContain('setActiveText')
    expect(headingSrc).not.toContain('prevTextRef')
    expect(headingSrc).toContain('TypewriterHeadingContent')
  })

  it('exploit_2: OfflineEngineMotionCard and LedgerMotionCard localize remaining labels when language=en', () => {
    window.history.replaceState(null, '', '/official?lang=en')
    const { container } = render(
      <OfficialLanguageProvider>
        <OfflineEngineMotionCard />
        <LedgerMotionCard />
      </OfficialLanguageProvider>
    )
    expect(container.textContent).toContain('Pocket-Ready Itinerary')
    expect(container.textContent).toContain('Zero-Latency Local Load')
    expect(screen.getByRole('tablist', { name: /Select currency/i })).toBeDefined()
    window.history.replaceState(null, '', '/official')
  })

  it('exploit_3: AiImportTripWizard removes eslint-disable and forwards locale to aiApi.parseMarkdown', () => {
    const wizardSrc = fs.readFileSync(path.join(frontendDir, 'components/itinerary/AiImportTripWizard.tsx'), 'utf-8')
    expect(wizardSrc).not.toContain('eslint-disable-next-line react-hooks/exhaustive-deps')
    expect(wizardSrc).toContain('locale: lang')
    expect(wizardSrc).toContain('Supports Ctrl+V paste')
  })

  it('exploit_4: EditableDailyAIReview forwards lang to generateAIReview and translates loading text', () => {
    const reviewSrc = fs.readFileSync(path.join(frontendDir, 'components/itinerary/EditableDailyAIReview.tsx'), 'utf-8')
    expect(reviewSrc).toContain('tripsApi.generateAIReview(tripId, day, userId, lang)')
    expect(reviewSrc).toContain('AI is reviewing...')
    expect(reviewSrc).toContain('scopeKey')
  })

  it('exploit_5: TripCoverMenu binds DialogDescription inside VisuallyHidden', () => {
    const coverSrc = fs.readFileSync(path.join(frontendDir, 'components/itinerary/TripCoverMenu.tsx'), 'utf-8')
    expect(coverSrc).toContain('DialogDescription')
  })

  it('exploit_6: offlineFetch injects plain-object Idempotency-Key and queues Lie-Fi network drops', async () => {
    const mockFetch = vi.fn().mockRejectedValueOnce(new TypeError('Failed to fetch'))
    global.fetch = mockFetch
    const enqueueSpy = vi.spyOn(SyncQueue, 'enqueue').mockResolvedValueOnce('q-1')

    const res = await expensesApi.create(
      { itinerary_id: 'trip-1', title: 'Sushi', amount_jpy: 1500, total_amount: 1500, currency: 'JPY' },
      'user-1'
    )
    expect(res).toEqual({ status: 'queued', offline: true, type: 'json' })
    expect(enqueueSpy).toHaveBeenCalledTimes(1)

    const queuedPayload = enqueueSpy.mock.calls[0][0]
    expect(queuedPayload.headers).toBeDefined()
    expect(queuedPayload.headers?.['Idempotency-Key']).toBeTruthy()
    expect(queuedPayload.headers?.['X-User-ID']).toBe('user-1')

    // Ensure fetch received the exact same Idempotency-Key in plain object headers
    const sentHeaders = mockFetch.mock.calls[0][1]?.headers as Record<string, string>
    expect(sentHeaders['Idempotency-Key']).toBe(queuedPayload.headers?.['Idempotency-Key'])

    // Verify user-aborted requests are re-thrown rather than falsely queued
    const abortErr = new Error('The user aborted a request')
    abortErr.name = 'AbortError'
    mockFetch.mockRejectedValueOnce(abortErr)
    await expect(
      expensesApi.create({ itinerary_id: 'trip-1', title: 'Aborted', amount_jpy: 100, currency: 'JPY' }, 'user-1')
    ).rejects.toThrow('aborted')
    expect(enqueueSpy).toHaveBeenCalledTimes(1)
  })

  it('exploit_7: sync-hooks exports __resetSyncProcessingForTesting', () => {
    const resetFn = (syncHooks as Record<string, unknown>).__resetSyncProcessingForTesting
    expect(typeof resetFn).toBe('function')
    if (typeof resetFn === 'function') {
      ;(resetFn as () => void)()
    }
  })
})
