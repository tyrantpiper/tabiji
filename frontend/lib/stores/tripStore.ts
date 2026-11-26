/**
 * Trip Store - Zustand State Management
 * Manages global trip state with localStorage persistence
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface TripState {
    // State
    activeTripId: string | null
    userId: string | null
    activeTripTitle: string | null
    focusedDay: number // 🆕 2026: The day currently being viewed in the UI
    targetExpenseId: string | null // 🆕 2026: Target expense ID for deep linking & highlighting

    // Actions
    setActiveTripId: (id: string | null) => void
    setUserId: (id: string | null) => void
    setActiveTripTitle: (title: string | null) => void
    setFocusedDay: (day: number) => void // 🆕 2026
    setTargetExpenseId: (id: string | null) => void // 🆕 2026
    initializeFromStorage: () => void
}

const INVALID_ID_LITERALS = new Set(['null', 'undefined', 'nan', 'none'])

export const sanitizeStoredId = (raw: string | null | undefined): string | null => {
    if (typeof raw !== 'string') return null
    const trimmed = raw.trim()
    if (!trimmed || INVALID_ID_LITERALS.has(trimmed.toLowerCase())) return null
    return trimmed
}

/**
 * 🔧 FIX: Sync initialize userId from localStorage without generating unregistered orphan UUIDs
 * Unauthenticated visitors stay null until explicit login/recovery in LandingPage.
 */
const getInitialUserId = (): string | null => {
    if (typeof window !== 'undefined') {
        return sanitizeStoredId(localStorage.getItem('user_uuid'))
    }
    return null
}

export const useTripStore = create<TripState>()(
    persist(
        (set) => ({
            // Initial state - 🔧 userId now sync initialized
            activeTripId: null,
            userId: getInitialUserId(),
            activeTripTitle: null,
            focusedDay: 1, // Default to Day 1
            targetExpenseId: null,

            // Actions
            setActiveTripId: (id) => set({ activeTripId: sanitizeStoredId(id) }),
            setUserId: (id) => set({ userId: sanitizeStoredId(id) }),
            setActiveTripTitle: (title) => set({ activeTripTitle: title }),
            setFocusedDay: (day) => set({ focusedDay: day }),
            setTargetExpenseId: (id) => set({ targetExpenseId: id }),

            // Initialize from legacy localStorage (for migration & resilience)
            initializeFromStorage: () => {
                if (typeof window !== 'undefined') {
                    // 🛡️ Identity Calibration: Ensure the primary user_uuid is used as the SSO
                    const legacyId = sanitizeStoredId(localStorage.getItem('user_uuid'))
                    const { userId } = useTripStore.getState()

                    if (legacyId && userId !== legacyId) {
                        console.log('🏗️ [Calibration] Restoring primary identity from localStorage:', legacyId)
                        set({ userId: legacyId })
                    }

                    const activeTripId = sanitizeStoredId(localStorage.getItem('active_trip_id'))
                    const activeTripTitle = localStorage.getItem('active_trip_title')

                    set({
                        activeTripId,
                        activeTripTitle
                    })
                }
            }
        }),
        {
            name: 'trip-storage', // localStorage key
            partialize: (state) => ({
                // Only persist these fields
                activeTripId: state.activeTripId,
                activeTripTitle: state.activeTripTitle,
                userId: state.userId  // 🔧 FIX: Now also persist userId
            }),
            // 🔧 FIX: Custom merge to prevent sync-initialized userId from being overwritten and sanitize invalid literals
            merge: (persistedState, currentState) => {
                const persisted = persistedState as Partial<TripState>
                const cleanPersistedUserId = sanitizeStoredId(persisted?.userId)
                const cleanPersistedTripId = sanitizeStoredId(persisted?.activeTripId)
                return {
                    ...currentState,
                    ...persisted,
                    activeTripId: cleanPersistedTripId,
                    // If persisted userId is empty/invalid, use sync-initialized value
                    userId: cleanPersistedUserId || currentState.userId
                }
            }
        }
    )
)

/**
 * Selector hooks for performance optimization
 */
export const useActiveTripId = () => useTripStore((s) => s.activeTripId)
export const useUserId = () => useTripStore((s) => s.userId)
export const useActiveTripTitle = () => useTripStore((s) => s.activeTripTitle)
export const useFocusedDay = () => useTripStore((s) => s.focusedDay)
export const useTargetExpenseId = () => useTripStore((s) => s.targetExpenseId)
