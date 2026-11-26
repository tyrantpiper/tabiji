/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const { createClientMock } = vi.hoisted(() => ({
    createClientMock: vi.fn(() => ({ channel: vi.fn() })),
}))

vi.mock('@supabase/supabase-js', () => ({
    createClient: createClientMock,
}))

import { getSupabaseClient } from '@/lib/supabase'

describe('TripStore Empty Init (AC-3) & Supabase Publishable Key Selection', () => {
    let mockStorage: Record<string, string> = {}
    const originalFetch = globalThis.fetch
    const originalEnv = { ...process.env }

    beforeEach(() => {
        vi.clearAllMocks()
        mockStorage = {}
        vi.stubGlobal('localStorage', {
            getItem: vi.fn((k: string) => mockStorage[k] ?? null),
            setItem: vi.fn((k: string, v: string) => { mockStorage[k] = String(v) }),
            removeItem: vi.fn((k: string) => { delete mockStorage[k] }),
            clear: vi.fn(() => { mockStorage = {} }),
        })
        delete (globalThis as { supabaseClient?: unknown }).supabaseClient
    })

    afterEach(() => {
        globalThis.fetch = originalFetch
        process.env = { ...originalEnv }
        delete (globalThis as { supabaseClient?: unknown }).supabaseClient
        vi.unstubAllGlobals()
    })

    it('AC-3: useTripStore initializes with userId=null and triggers zero /api/auth/session calls on empty localStorage', async () => {
        const fetchSpy = vi.fn()
        globalThis.fetch = fetchSpy as unknown as typeof fetch

        const { useTripStore } = await import('@/lib/stores/tripStore')

        expect(useTripStore.getState().userId).toBeNull()
        expect(mockStorage['user_uuid']).toBeUndefined()
        expect(fetchSpy).not.toHaveBeenCalled()
    })

    it('getSupabaseClient prefers NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY and falls back to NEXT_PUBLIC_SUPABASE_ANON_KEY', async () => {
        process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
        process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY = 'sb_publishable_test_key_1'
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'eyJ_legacy_anon_key'

        getSupabaseClient()
        expect(createClientMock).toHaveBeenLastCalledWith(
            'https://example.supabase.co',
            'sb_publishable_test_key_1',
        )

        // Reset global singleton and verify fallback when NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY is unset
        delete (globalThis as { supabaseClient?: unknown }).supabaseClient
        delete process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY

        getSupabaseClient()
        expect(createClientMock).toHaveBeenLastCalledWith(
            'https://example.supabase.co',
            'eyJ_legacy_anon_key',
        )

        // Verify no legacy unauthenticated x-user-id custom fetch wrapper is attached
        const lastCall = createClientMock.mock.calls.at(-1) as unknown[]
        expect(lastCall).toHaveLength(2)
    })
})
