import React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import fs from 'node:fs'
import path from 'node:path'

vi.mock('@/lib/hooks/usePushNotifications', () => ({
  usePushNotifications: () => ({
    permissionState: 'unsupported',
    isSubscribed: false,
    subscribe: async () => false,
    unsubscribe: async () => false,
    isSupported: false,
    isLoading: false,
  }),
}))

vi.mock('next/image', () => ({
  default: () => null,
}))

import * as authSession from '@/lib/auth-session'
import { ThemeProvider } from '@/lib/ThemeContext'
import { translations } from '@/lib/i18n'
import { ProfileView } from '@/components/views/profile-view'
import { appApi } from '@/lib/api'

const frontendDir = path.resolve(__dirname, '..')
const originalFetch = global.fetch

class MockResizeObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

function renderProfileView() {
  return render(
    <ThemeProvider>
      <ProfileView />
    </ThemeProvider>
  )
}

describe('Security Sentinel Donation Fail-Closed & Privacy Suite', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    global.fetch = originalFetch
    localStorage.clear()
    vi.spyOn(authSession, 'fetchLatestRecoveryKey').mockResolvedValue(null)
    window.ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
  })

  afterEach(() => {
    global.fetch = originalFetch
  })

  it('benign_control: ProfileView renders core profile header both before and after donation hardening', async () => {
    vi.spyOn(appApi, 'getDonationProgress').mockResolvedValue({
      available: true,
      percentage: 40,
      current: 800,
      goal: 2000,
      month: new Date().toISOString().slice(0, 7),
    } as never)

    renderProfileView()
    expect(screen.getByText(translations.zh.rank_explorer)).toBeDefined()
    await waitFor(() => {
      expect(screen.getByText('40%')).toBeDefined()
    })
  })

  it('exploit_8: appApi.getDonationProgress short-circuits offline and sends cache: no-store', async () => {
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    const mockFetch = vi.fn()
    global.fetch = mockFetch

    const offlineRes = await appApi.getDonationProgress()
    expect(offlineRes).toEqual({ available: false })
    expect(mockFetch).not.toHaveBeenCalled()

    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ available: true, percentage: 25, month: '2026-11' }),
    })
    const onlineRes = await appApi.getDonationProgress()
    expect(onlineRes).toEqual({ available: true, percentage: 25, month: '2026-11' })
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/app/donation-progress'),
      expect.objectContaining({ cache: 'no-store' })
    )
  })

  it('exploit_9: ProfileView hides donation card on DB/HTTP 503 error or available:false and never renders fake 0%', async () => {
    const profileSrc = fs.readFileSync(path.join(frontendDir, 'components/views/profile-view.tsx'), 'utf-8')
    expect(profileSrc).not.toContain('useState({ current: 0, goal: 2000 })')

    // Case A: API throws (HTTP 503 / network drop) -> wait for load settle, card MUST hide completely
    const errSpy = vi.spyOn(appApi, 'getDonationProgress').mockRejectedValue(new Error('HTTP 503'))
    const first = renderProfileView()
    await waitFor(() => {
      expect(errSpy).toHaveBeenCalledTimes(1)
      expect(first.container.querySelector('.animate-pulse')).toBeNull()
    })
    expect(screen.queryByText(translations.zh.profile_donation_monitor)).toBeNull()
    expect(screen.queryByText('0%')).toBeNull()
    first.unmount()
    errSpy.mockRestore()

    // Case B: backend returns { available: false } -> wait for load settle, card MUST hide completely
    const unavailSpy = vi.spyOn(appApi, 'getDonationProgress').mockResolvedValue({ available: false })
    const second = renderProfileView()
    await waitFor(() => {
      expect(unavailSpy).toHaveBeenCalledTimes(1)
      expect(second.container.querySelector('.animate-pulse')).toBeNull()
    })
    expect(screen.queryByText(translations.zh.profile_donation_monitor)).toBeNull()
    expect(screen.queryByText('0%')).toBeNull()
    second.unmount()
    unavailSpy.mockRestore()

    // Case C: dismissedMonth matches current UTC month -> no API request and card hidden immediately
    localStorage.setItem('donation_dismissed', new Date().toISOString().slice(0, 7))
    const spyDismissed = vi.spyOn(appApi, 'getDonationProgress').mockResolvedValue({ available: true, percentage: 50 })
    const third = renderProfileView()
    await waitFor(() => {
      expect(third.container.querySelector('.animate-pulse')).toBeNull()
      expect(screen.queryByText(translations.zh.profile_donation_monitor)).toBeNull()
    })
    expect(spyDismissed).not.toHaveBeenCalled()
    third.unmount()
  })

  it('exploit_10: ProfileView clears cached donation percentage immediately on offline transition and recovers online', async () => {
    const month = new Date().toISOString().slice(0, 7)
    const getSpy = vi.spyOn(appApi, 'getDonationProgress').mockResolvedValueOnce({
      available: true,
      percentage: 40,
      month,
    })

    const view = renderProfileView()
    await waitFor(() => {
      expect(screen.getByText('40%')).toBeDefined()
    })

    // Simulate going offline while ProfileView stays mounted in AppShell tab cache
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    act(() => {
      window.dispatchEvent(new Event('offline'))
    })

    await waitFor(() => {
      expect(screen.queryByText('40%')).toBeNull()
      expect(screen.queryByText(translations.zh.profile_donation_monitor)).toBeNull()
      expect(screen.queryByText('0%')).toBeNull()
    })

    // Simulate coming back online and refreshing without page reload
    getSpy.mockResolvedValueOnce({
      available: true,
      percentage: 55,
      month,
    })
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    await act(async () => {
      window.dispatchEvent(new Event('online'))
    })

    await waitFor(() => {
      expect(screen.getByText('55%')).toBeDefined()
    })
    view.unmount()
  })

  it('exploit_11: offline mount recovers on online event and stale async online resolve cannot leak while offline', async () => {
    const month = new Date().toISOString().slice(0, 7)

    // Part A: Initial mount offline stays hidden with zero API calls, then recovers when online event fires
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    let resolveDelayed!: (val: { available: boolean; percentage: number; month: string }) => void
    const getSpy = vi.spyOn(appApi, 'getDonationProgress')

    const view = renderProfileView()
    await waitFor(() => {
      expect(view.container.querySelector('.animate-pulse')).toBeNull()
      expect(screen.queryByText(translations.zh.profile_donation_monitor)).toBeNull()
    })
    expect(getSpy).not.toHaveBeenCalled()

    // Now simulate online recovery with a slow in-flight response, then abort offline mid-flight
    getSpy.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveDelayed = resolve
        })
    )
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    act(() => {
      window.dispatchEvent(new Event('online'))
    })
    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledTimes(1)
    })

    Object.defineProperty(navigator, 'onLine', { configurable: true, value: false })
    await act(async () => {
      window.dispatchEvent(new Event('offline'))
      resolveDelayed({ available: true, percentage: 88, month })
    })

    await waitFor(() => {
      expect(view.container.querySelector('.animate-pulse')).toBeNull()
      expect(screen.queryByText('88%')).toBeNull()
      expect(screen.queryByText(translations.zh.profile_donation_monitor)).toBeNull()
    })

    // Finally online again recovers cleanly
    getSpy.mockResolvedValueOnce({ available: true, percentage: 62, month })
    Object.defineProperty(navigator, 'onLine', { configurable: true, value: true })
    await act(async () => {
      window.dispatchEvent(new Event('online'))
    })
    await waitFor(() => {
      expect(screen.getByText('62%')).toBeDefined()
    })
    view.unmount()
  })
})
