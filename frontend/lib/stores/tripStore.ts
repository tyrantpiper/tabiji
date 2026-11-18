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

/**
 * 🔧 FIX: Sync initialize userId from localStorage without generating unregistered orphan UUIDs
 * Unauthenticated visitors stay null until explicit login/recovery in LandingPage.
 */
const getInitialUserId = (): string | null => {
    if (typeof window !== 'undefined') {
        const raw = localStorage.getItem('user_uuid')
        if (!raw) return null
        const trimmed = raw.trim()
        if (!trimmed || trimmed === 'null' || trimmed === 'undefined') return null
        return trimmed
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
            setActiveTripId: (id) => set({ activeTripId: id }),
            setUserId: (id) => set({ userId: id }),
            setActiveTripTitle: (title) => set({ activeTripTitle: title }),
            setFocusedDay: (day) => set({ focusedDay: day }),
            setTargetExpenseId: (id) => set({ targetExpenseId: id }),

            // Initialize from legacy localStorage (for migration & resilience)
            initializeFromStorage: () => {
                if (typeof window !== 'undefined') {
                    // 🛡️ Identity Calibration: Ensure the primary user_uuid is used as the SSO
                    const legacyId = localStorage.getItem('user_uuid')
                    const { userId } = useTripStore.getState()

                    if (legacyId && userId !== legacyId) {
                        console.log('🏗️ [Calibration] Restoring primary identity from localStorage:', legacyId)
                        set({ userId: legacyId })
                    }

                    const activeTripId = localStorage.getItem('active_trip_id')
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
            // 🔧 FIX: Custom merge to prevent sync-initialized userId from being overwritten
            merge: (persistedState, currentState) => {
                const persisted = persistedState as Partial<TripState>
                return {
                    ...currentState,
                    ...persisted,
                    // If persisted userId is empty, use sync-initialized value
                    userId: persisted?.userId || currentState.userId
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
