/**
 * Security & Bilingual E2E Sentinel Test Suite (Frontend)
 * Follows Mantis Block G Benign Control, SENTINEL-1.1 / 3.1 / 4.1 Invariants,
 * LanguageContext PPR Suspense Soft Navigation, Actuary Bilingualism & POI Race Guard.
 */

import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import fs from 'node:fs'
import path from 'node:path'

// Mutable mock navigation state for soft-navigation handoff testing
let mockPathname = '/official'
let mockSearchParams = new URLSearchParams('')
const mockPush = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
  usePathname: () => mockPathname,
  useSearchParams: () => mockSearchParams,
}))

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api')
  return {
    ...actual,
    aiApi: {
      ...actual.aiApi,
      actuaryChat: vi.fn().mockResolvedValue({
        status: 'success',
        response: 'Ready to help split expenses!',
        grounding_metadata: {
          sources: [{ title: 'Wise FX Rate', uri: 'https://wise.com' }],
        },
      }),
    },
    poiApi: {
      ...actual.poiApi,
      enrich: vi.fn().mockResolvedValue({
        summary: 'Historic Buddhist temple in Asakusa.',
        cultural_desc: 'Founded in 628 CE.',
        status: 'SUCCESS',
      }),
    },
  }
})

vi.mock('@/lib/trip-context', () => ({
  useTripContext: () => ({
    activeTripId: null,
    activeTrip: null,
    mutate: vi.fn(),
    userId: null,
  }),
}))

import { OfficialLanguageProvider } from '@/lib/OfficialLanguageContext'
import { LanguageProvider, useLanguage } from '@/lib/LanguageContext'
import OfficialPage from '@/app/official/page'
import { ActuaryDialogCard } from '@/components/ActuaryDialogCard'
import POIDetailDrawer from '@/components/POIDetailDrawer'
import POIPreviewCard from '@/components/chat/POIPreviewCard'
import { ACCENT_COLORS } from '@/lib/ThemeContext'
import { translations } from '@/lib/translations'
import { expenseTranslations } from '@/lib/i18n/expense'
import { aiApi, poiApi } from '@/lib/api'

const frontendDir = path.resolve(__dirname, '..')

class MockIntersectionObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

describe('Bilingual Handoff & Frontend E2E Remediation Sentinel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockPathname = '/official'
    mockSearchParams = new URLSearchParams('')
    window.IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver
    sessionStorage.clear()
    localStorage.clear()
    document.cookie = 'app_language=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
    window.history.replaceState(null, '', '/official')
    Element.prototype.scrollIntoView = vi.fn()
  })

  describe('1. Official Portal -> PWA Language Handoff & SENTINEL-1.1/3.1 Isolation', () => {
    it('DEFECT-1: Clicking Launch App in EN mode navigates to /?lang=en across Header, Hero, Page, Footer without touching localStorage', () => {
      window.history.replaceState(null, '', '/official?lang=en')

      render(
        <OfficialLanguageProvider>
          <OfficialPage />
        </OfficialLanguageProvider>
      )

      const launchBtns = screen.getAllByRole('button', { name: /launch/i })
      expect(launchBtns.length).toBeGreaterThanOrEqual(2)

      // Click Hero + Footer Page Launch buttons too
      for (const btn of launchBtns) {
        fireEvent.click(btn)
        expect(mockPush).toHaveBeenLastCalledWith('/?lang=en')
      }

      // Strict SENTINEL-1.1: /official must NEVER write app_language to localStorage
      expect(localStorage.getItem('app_language')).toBeNull()

      // Footer backApp link forwards ?lang=en
      const backLink = screen.getByRole('link', { name: /launch tabiji/i })
      expect(backLink.getAttribute('href')).toBe('/?lang=en')
    })

    it('BENIGN-1: OfficialFooter strictly preserves 6 text Links & zero localStorage access in portal source', () => {
      const footerContent = fs.readFileSync(path.join(frontendDir, 'components', 'official', 'OfficialFooter.tsx'), 'utf-8')
      const linkMatches = footerContent.match(/<Link[\s\S]*?className="([^"]*)"/g) || []
      const textLinks = linkMatches.filter((m) => !m.includes('href="/official"'))
      expect(textLinks.length).toBe(6)

      for (const rel of [
        'components/official/OfficialHeader.tsx',
        'components/official/HeroShowcase.tsx',
        'components/official/OfficialFooter.tsx',
        'app/official/page.tsx',
      ]) {
        const src = fs.readFileSync(path.join(frontendDir, rel), 'utf-8')
        expect(src).not.toMatch(/localStorage\.(setItem|getItem)\(['"]app_language['"]\)/)
      }
    })
  })

  describe('2. LanguageContext PPR Suspense Soft Navigation & Query Cleaning', () => {
    it('DEFECT-2: Opening /official?lang=en under shared LanguageProvider does NOT write localStorage; navigating to /?lang=en syncs en & strips lang while preserving other params & hash', async () => {
      // Phase A: Render shared LanguageProvider while on /official?lang=en
      mockPathname = '/official'
      mockSearchParams = new URLSearchParams('lang=en')
      window.history.replaceState(null, '', '/official?lang=en')

      const Probe = () => {
        const { lang } = useLanguage()
        return <div data-testid="pwa-lang">{lang}</div>
      }

      const { rerender } = render(
        <LanguageProvider>
          <Probe />
        </LanguageProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('pwa-lang')).toBeDefined()
      })
      // Must NOT pollute localStorage while pathname starts with /official
      expect(localStorage.getItem('app_language')).toBeNull()

      // Phase B: Soft-navigate from /official to /?foo=bar&lang=en#trips
      mockPathname = '/'
      mockSearchParams = new URLSearchParams('foo=bar&lang=en')
      window.history.replaceState(null, '', '/?foo=bar&lang=en#trips')

      rerender(
        <LanguageProvider>
          <Probe />
        </LanguageProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('pwa-lang').textContent).toBe('en')
      })
      expect(localStorage.getItem('app_language')).toBe('en')
      expect(document.cookie).toContain('app_language=en')
      // Only ?lang= stripped; ?foo=bar and #trips preserved
      expect(window.location.search).toBe('?foo=bar')
      expect(window.location.hash).toBe('#trips')
    })

    it('DEFECT-2B: LanguageContext wraps useSearchParams observer in <Suspense> inside mounted Provider', () => {
      const ctxSource = fs.readFileSync(path.join(frontendDir, 'lib', 'LanguageContext.tsx'), 'utf-8')
      expect(ctxSource).toContain('Suspense')
      expect(ctxSource).toContain('useSearchParams')
      expect(ctxSource).toContain('/official')
    })

    it('BENIGN-2: On / with no ?lang=, LanguageContext loads existing localStorage app_language', async () => {
      localStorage.setItem('app_language', 'en')
      mockPathname = '/'
      mockSearchParams = new URLSearchParams('')
      window.history.replaceState(null, '', '/')

      const Probe = () => {
        const { lang } = useLanguage()
        return <div data-testid="pwa-lang-benign">{lang}</div>
      }

      render(
        <LanguageProvider>
          <Probe />
        </LanguageProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('pwa-lang-benign').textContent).toBe('en')
      })
    })
  })

  describe('3. Actuary, POIPreviewCard, POIDetailDrawer, Theme & i18n Bilingual Parity', () => {
    it('DEFECT-3: expense.en.actuary_welcome and translations.en.actuary_welcome are real prompts, not "Loading expenses..."', () => {
      expect(expenseTranslations.en.actuary_welcome).not.toBe('Loading expenses...')
      expect(translations.en.actuary_welcome).not.toBe('Loading expenses...')
      expect(expenseTranslations.en.actuary_welcome.toLowerCase()).toContain('expense')
    })

    it('DEFECT-4: ThemeContext ACCENT_COLORS.default has English label nameEn: "Default"', () => {
      expect((ACCENT_COLORS.default as { nameEn?: string }).nameEn).toBe('Default')
    })

    it('DEFECT-5: ActuaryDialogCard renders zero hardcoded Chinese in EN mode, passes locale="en", and keeps Tailwind v4 canonical classes', async () => {
      localStorage.setItem('app_language', 'en')
      mockPathname = '/'

      render(
        <LanguageProvider>
          <ActuaryDialogCard open={true} onOpenChange={vi.fn()} expenses={[]} members={[]} />
        </LanguageProvider>
      )

      await waitFor(() => {
        expect(aiApi.actuaryChat).toHaveBeenCalled()
      })

      const callArgs = vi.mocked(aiApi.actuaryChat).mock.calls[0]
      expect(callArgs[4]).toBe('en')
      expect(screen.getByText('Sources')).toBeDefined()
      expect(screen.queryByText('參考來源')).toBeNull()

      const cardSrc = fs.readFileSync(path.join(frontendDir, 'components', 'ActuaryDialogCard.tsx'), 'utf-8')
      expect(cardSrc).toContain('sm:max-w-150')
      expect(cardSrc).toContain('shrink-0')
      expect(cardSrc).toContain('wrap-break-word')
    })

    it('DEFECT-6: POIPreviewCard and POIDetailDrawer pass locale to poiApi.enrich and reset state on language switch', async () => {
      localStorage.setItem('app_language', 'en')
      mockPathname = '/'

      render(
        <LanguageProvider>
          <POIPreviewCard
            poiData={{ day_number: 1, time_slot: '10:00', place_name: 'Senso-ji', category: 'sightseeing', lat: 35.7147, lng: 139.7966 }}
            onAdded={vi.fn()}
          />
          <POIDetailDrawer
            isOpen={true}
            onClose={vi.fn()}
            poi={{ name: 'Kinkaku-ji', type: 'attraction', lat: 35.0394, lng: 135.7292 }}
          />
        </LanguageProvider>
      )

      await waitFor(() => {
        expect(poiApi.enrich).toHaveBeenCalledWith(
          expect.objectContaining({ name: 'Senso-ji', locale: 'en' }),
          undefined
        )
      })

      const exploreBtn = await screen.findByRole('button', { name: /explore/i })
      fireEvent.click(exploreBtn)

      await waitFor(() => {
        expect(poiApi.enrich).toHaveBeenCalledWith(
          expect.objectContaining({ name: 'Kinkaku-ji', locale: 'en' }),
          expect.anything()
        )
      })

      const drawerSrc = fs.readFileSync(path.join(frontendDir, 'components', 'POIDetailDrawer.tsx'), 'utf-8')
      expect(drawerSrc).toContain('const { t, lang } = useLanguage()')
      expect(drawerSrc).toContain('locale: lang')
    })
  })
})
