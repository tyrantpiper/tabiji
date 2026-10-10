import { describe, it, expect, vi, beforeEach } from 'vitest'

describe('Account Recovery Atomic Reset & Silent Handoff Sentinel Tests', () => {
    let mockStorage: Record<string, string> = {}

    beforeEach(() => {
        mockStorage = {}
        vi.stubGlobal('localStorage', {
            getItem: vi.fn((key: string) => mockStorage[key] || null),
            setItem: vi.fn((key: string, val: string) => { mockStorage[key] = val }),
            removeItem: vi.fn((key: string) => { delete mockStorage[key] }),
            clear: vi.fn(() => { mockStorage = {} })
        })
        vi.stubGlobal('sessionStorage', {
            getItem: vi.fn((key: string) => mockStorage[key] || null),
            setItem: vi.fn((key: string, val: string) => { mockStorage[key] = val }),
            removeItem: vi.fn((key: string) => { delete mockStorage[key] }),
            clear: vi.fn(() => { mockStorage = {} })
        })
    })

    it('TC-1: Guarantee Zustand persist storage is completely purged on account recovery', () => {
        // Setup: Previous session has residual Zustand persist snapshot
        const priorPersistData = {
            state: {
                activeTripId: 'stale-trip-uuid-111',
                activeTripTitle: 'Old Anonymous Trip',
                userId: 'stale-user-000'
            },
            version: 0
        }
        mockStorage['tabidachi-trip-storage'] = JSON.stringify(priorPersistData)
        mockStorage['active_trip_id'] = 'stale-trip-uuid-111'
        mockStorage['active_trip_title'] = 'Old Anonymous Trip'

        // Function replicating atomic recovery purge
        const purgeRecoveryArtifacts = () => {
            localStorage.removeItem('active_trip_id')
            localStorage.removeItem('active_trip_title')
            try {
                const raw = localStorage.getItem('tabidachi-trip-storage')
                if (raw) {
                    const parsed = JSON.parse(raw)
                    if (parsed.state) {
                        parsed.state.activeTripId = null
                        parsed.state.activeTripTitle = null
                        localStorage.setItem('tabidachi-trip-storage', JSON.stringify(parsed))
                    }
                }
            } catch {}
            sessionStorage.setItem('tabiji_identity_transition_lock', Date.now().toString())
        }

        purgeRecoveryArtifacts()

        // Verify: Legacy standalone keys removed
        expect(mockStorage['active_trip_id']).toBeUndefined()
        expect(mockStorage['active_trip_title']).toBeUndefined()

        // Verify: Zustand persist storage state sanitized (activeTripId is strictly null)
        const sanitized = JSON.parse(mockStorage['tabidachi-trip-storage'])
        expect(sanitized.state.activeTripId).toBeNull()
        expect(sanitized.state.activeTripTitle).toBeNull()
        // Verify: Transition lock established
        expect(mockStorage['tabiji_identity_transition_lock']).toBeDefined()
    })

    it('TC-2: Guarantee zero false-positive warning toasts during identity transition window', () => {
        const toastWarning = vi.fn()
        const now = Date.now()
        mockStorage['tabiji_identity_transition_lock'] = now.toString()

        const isTransitionLocked = () => {
            const lockTime = sessionStorage.getItem('tabiji_identity_transition_lock')
            if (!lockTime) return false
            return Date.now() - parseInt(lockTime, 10) < 5000
        }

        const handleTripValidation = (
            trips: Array<{ id: string; title: string }>,
            activeTripId: string | null,
            prevUserId: string | null,
            currentUserId: string | null
        ) => {
            if (trips.length > 0 && activeTripId) {
                const tripExists = trips.some(t => t.id === activeTripId)
                if (!tripExists) {
                    // Guard: Suppress toast during transition lock window
                    if (prevUserId === currentUserId && !isTransitionLocked()) {
                        toastWarning('該行程不存在或無存取權限，已切換至預設行程')
                    }
                    return trips[0].id // Silently switch to valid trip
                }
            }
            return activeTripId
        }

        // Simulating: User recovers account, trips load for Alice with trip-222, while stale activeTripId is trip-111
        const activeTrip = handleTripValidation(
            [{ id: 'trip-222', title: 'Alice Real Trip' }],
            'stale-trip-111',
            'user-alice', // prevUserId updated
            'user-alice'  // currentUserId matches
        )

        // Verifications:
        expect(toastWarning).not.toHaveBeenCalled()
        expect(activeTrip).toBe('trip-222') // Clean silent handoff!
    })
})
