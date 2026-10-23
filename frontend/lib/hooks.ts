import useSWR from "swr"
import { useState, useEffect, useCallback, useMemo, useRef } from "react"
import { travelDataApi, API_HOST } from './api'
import { getTripSnapshotSync, saveTripSnapshot, preloadTripSnapshot, getTripsListSnapshotSync, preloadTripsListSnapshot, saveTripsListSnapshot, getTripCapsuleSnapshotSync, saveTripCapsuleSnapshot } from './idb-storage'
import type { Trip, CapsuleProgressSummary } from './itinerary-types'


import { toast } from "sonner"

export class HttpError extends Error {
    constructor(public status: number, message: string, public data?: unknown) {
        super(message)
        this.name = "HttpError"
    }
}

import { getCachedToken, ensureValidSession } from './auth-session'

export const fetcherWithUserId = async ([url, uid]: [string, string]) => {
    let token = getCachedToken()
    if (!token && typeof window !== "undefined") {
        token = await ensureValidSession().catch(() => null)
    }
    const headers: Record<string, string> = { "X-User-ID": uid }
    if (token) {
        headers["Authorization"] = `Bearer ${token}`
    }
    const activeFetch = typeof globalThis !== "undefined" && globalThis.fetch ? globalThis.fetch : (typeof window !== "undefined" ? window.fetch : fetch)
    
    let r: Response
    try {
        r = await activeFetch(API_HOST + url, { headers, cache: "no-store" })
    } catch (err) {
        console.warn("[Fetcher] Network degradation or offline:", (err as Error)?.message || err)
        throw new HttpError(0, (err as Error)?.message || "Network error", { offline: true })
    }

    // 🛡️ 401 憑證自癒重試機制 (Self-Healing 1-Time Re-exchange & Retry)
    if (r.status === 401 && typeof window !== "undefined") {
        console.warn("⚠️ [Fetcher] Received 401 Unauthorized. Purging stale token and attempting 1-time re-exchange...")
        localStorage.removeItem("tabiji_session_token")
        const freshToken = await ensureValidSession().catch(() => null)
        if (freshToken) {
            const retryHeaders = { ...headers, "Authorization": `Bearer ${freshToken}` }
            try {
                r = await activeFetch(API_HOST + url, { headers: retryHeaders, cache: "no-store" })
            } catch (retryErr) {
                throw new HttpError(0, (retryErr as Error)?.message || "Network error", { offline: true })
            }
        }
    }

    if (!r.ok) {
        const errorBody = await r.json().catch(() => ({}))
        if (r.status !== 404 && r.status !== 401 && r.status !== 403) {
            toast.error("伺服器連線失敗，請稍後再試 (Server connection failed)")
        }
        throw new HttpError(r.status, errorBody?.detail || `HTTP ${r.status}`, errorBody)
    }
    return r.json()
}

export function useTrips(userId: string | null) {
    const [idbTrips, setIdbTrips] = useState<Trip[] | null>(() => getTripsListSnapshotSync<Trip[]>(userId))

    useEffect(() => {
        if (userId && !idbTrips) {
            preloadTripsListSnapshot<Trip[]>(userId).then((data) => {
                if (data && Array.isArray(data) && data.length > 0) {
                    setIdbTrips(data)
                }
            })
        }
    }, [userId, idbTrips])

    const initialSnapshot = useMemo(() => getTripsListSnapshotSync<Trip[]>(userId) || idbTrips, [userId, idbTrips])
    const { data, error, mutate } = useSWR<Trip[]>(
        userId ? ["/api/trips", userId] : null,
        fetcherWithUserId,
        {
            fallbackData: initialSnapshot || undefined,
            onErrorRetry: (err) => {
                // 🛡️ 401 / 403 / 404 徹底禁止無效重試，保護伺服器與防震盪
                if (err instanceof HttpError && (err.status === 401 || err.status === 403 || err.status === 404)) return
            },
            onSuccess: (freshData) => {
                if (userId && freshData) {
                    saveTripsListSnapshot(userId, freshData)
                }
            }
        }
    )
    const effectiveTrips = Array.isArray(data) ? data : (Array.isArray(initialSnapshot) ? initialSnapshot : [])
    return {
        trips: effectiveTrips,
        isLoading: !error && !data && !initialSnapshot,
        isError: !!error,
        mutate
    }
}

export function useTripDetail(
    tripId: string | null, 
    userId?: string | null, 
    refreshInterval: number = 0,
    onTripNotFound?: (invalidId: string) => void
) {
    // 🔧 FIX: Include userId in cache key to ensure refetch when userId changes
    // And only make the request when we have a valid userId to prevent unauthenticated fetches
    // 🧠 2026 Normalization: userId is critical for privacy-aware caching
    const swrKey = (tripId && userId) ? [`/api/trips/${tripId}`, userId] : null

    // ⚡ 0ms L1 記憶體微秒級快顯 (首幀 0 骨架屏)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const initialSnapshot = useMemo(() => getTripSnapshotSync<any>(tripId), [tripId])

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { data, error, mutate, isValidating } = useSWR<any>(
        swrKey,
        fetcherWithUserId,
        {
            fallbackData: initialSnapshot || undefined,
            revalidateOnFocus: false,
            revalidateOnMount: true,
            refreshInterval, // 🆕 Hyper-Heuristics Injection
            dedupingInterval: 2000, // Prevent spam
            onSuccess: (freshData) => {
                // ⚡ 雲端獲取最新資料後，同步更新 L1 記憶體與 L2 IndexedDB
                if (tripId && freshData) {
                    saveTripSnapshot(tripId, freshData)
                }
            },
            onErrorRetry: (err) => {
                // 🛡️ 401 未授權 / 403 BOLA 阻斷 / 404 資源不存在，徹底禁止無效重試
                if (err instanceof HttpError && (err.status === 401 || err.status === 403 || err.status === 404)) return
            },
            onError: (err) => {
                if (err instanceof HttpError && err.status === 404 && tripId && onTripNotFound) {
                    onTripNotFound(tripId)
                }
            }
        }
    )

    // 🚀 非同步自 L2 (IndexedDB) 預熱快取至 L1 記憶體
    useEffect(() => {
        if (tripId) {
            preloadTripSnapshot(tripId).then(cached => {
                // 若當前無資料且 L2 預熱出資料，立即觸發一次局部 revalidate 注入
                if (cached && !data && mutate) {
                    mutate(cached, false)
                }
            })
        }
    }, [tripId, data, mutate])

    // 🔧 FIX: 當 userId 從 Zustand hydration 準備好後，保底刷新 (帶 2 秒去重時間閘門)
    const lastMutateTimeRef = useRef(0)
    useEffect(() => {
        if (userId && tripId && mutate) {
            const now = Date.now()
            if (now - lastMutateTimeRef.current > 2000) {
                lastMutateTimeRef.current = now
                mutate()
            }
        }
    }, [userId, tripId, mutate])

    return {
        trip: data,
        isLoading: !error && !data,
        isValidating,  // 🆕 Indicates SWR is fetching fresh data (even with cache)
        isError: error,
        mutate
    }
}

/**
 * 🔍 SWR Hook: Real-time lowest flight price (Phase 2A)
 * Only triggers when both origin and destination IATA codes are available.
 */
export function useFlightPrice(
    origin?: string,
    destination?: string,
    departureAt?: string
) {

    // 🛡️ 嚴格清洗日期為 YYYY-MM-DD，防禦 ISO 時間戳穿透至 Travelpayouts 導致 400/502 報警
    const cleanDate = departureAt ? departureAt.split('T')[0].replace(/\//g, '-') : undefined
    const cleanOrigin = origin?.trim().toUpperCase()
    const cleanDest = destination?.trim().toUpperCase()
    const isValidRoute = !!cleanOrigin && !!cleanDest && cleanOrigin !== cleanDest

    const key = isValidRoute
        ? `flight-price-${cleanOrigin}-${cleanDest}-${cleanDate || ''}`
        : null

    const { data, error, isLoading } = useSWR(
        key,
        async () => {
            const res = await travelDataApi.getFlightPrices({
                origin: cleanOrigin!,
                destination: cleanDest!,
                departure_at: cleanDate,
                currency: 'twd',
            })
            // 🛡️ 彈性降級 (Resilient Fallback): 若特定出發日無快取報價，自動補位抓取該航線近期最優惠價格
            if (cleanDate && (!res || !res.prices || res.prices.length === 0)) {
                try {
                    const fallbackRes = await travelDataApi.getFlightPrices({
                        origin: origin!.toUpperCase(),
                        destination: destination!.toUpperCase(),
                        currency: 'twd',
                    })
                    if (fallbackRes && fallbackRes.prices && fallbackRes.prices.length > 0) {
                        return fallbackRes
                    }
                } catch { /* non-blocking fallback */ }
            }
            return res
        },
        {
            revalidateOnFocus: false,
            dedupingInterval: 300000,   // 5 min dedup
            errorRetryCount: 1,
        }
    )

    return {
        lowestPrice: data?.lowest_price ?? null,
        prices: data?.prices ?? [],
        currency: data?.currency ?? 'TWD',
        isLoading,
        error,
    }
}

export function useExpenses(tripId: string | null, userId: string | null) {
    const { data, error, mutate } = useSWR(
        (tripId && userId) ? [`/api/trips/${tripId}/expenses`, userId] : null,
        fetcherWithUserId,
        { revalidateOnFocus: false }
    )
    return {
        expenses: data || [],
        isLoading: !error && !data,
        isError: error,
        mutate
    }
}

/**
 * Haptic feedback hook for mobile devices
 * Usage: const haptic = useHaptic(); haptic.tap();
 */
export function useHaptic() {
    const vibrate = useCallback((pattern: number | number[]) => {
        if (typeof window !== 'undefined' && 'vibrate' in navigator) {
            navigator.vibrate(pattern)
        }
    }, [])

    return useMemo(() => ({
        /** Ultra-light tick - for tabs, lists, and segmented pickers */
        selection: () => vibrate(6),
        /** Light tap - for button clicks */
        tap: () => vibrate(10),
        /** Medium feedback - for successful actions */
        success: () => vibrate([10, 50, 10]),
        /** Strong feedback - for errors or warnings */
        error: () => vibrate([50, 30, 50]),
        /** Custom pattern */
        custom: (pattern: number | number[]) => vibrate(pattern)
    }), [vibrate])
}

/**
 * Online status hook for detecting network connectivity
 * Usage: const isOnline = useOnlineStatus();
 * Returns false when user is offline, useful for showing offline notifications
 */
export function useOnlineStatus() {
    const [isOnline, setIsOnline] = useState(true)

    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect -- Sync with browser state on mount
        setIsOnline(navigator.onLine)

        const handleOnline = () => setIsOnline(true)
        const handleOffline = () => setIsOnline(false)

        window.addEventListener('online', handleOnline)
        window.addEventListener('offline', handleOffline)

        return () => {
            window.removeEventListener('online', handleOnline)
            window.removeEventListener('offline', handleOffline)
        }
    }, [])

    return isOnline
}

/**
 * Service Worker registration hook
 * Only registers in production environment
 */
export function useServiceWorker() {
    useEffect(() => {
        if (
            typeof window !== 'undefined' &&
            'serviceWorker' in navigator &&
            process.env.NODE_ENV === 'production'
        ) {
            navigator.serviceWorker
                .register('/sw.js')
                .then((registration) => {
                    console.log('SW registered:', registration.scope)
                })
                .catch((error) => {
                    console.error('SW registration failed:', error)
                })
        }
    }, [])
}

/**
  * 📮 旅伴時光膠囊專用 SWR Hook (Trip Time Capsule Hook)
  * 自動獲取進度摘要與已解鎖/自己之條目清單
  */
export function useTripCapsules(tripId: string | null | undefined, userId: string | null | undefined) {
    const { data, error, mutate, isValidating } = useSWR<CapsuleProgressSummary>(
        tripId && userId ? [`/api/trips/${tripId}/capsules`, userId] : null,
        fetcherWithUserId,
        {
            revalidateOnFocus: false,
            dedupingInterval: 10000,
            fallbackData: getTripCapsuleSnapshotSync<CapsuleProgressSummary>(tripId, userId) || undefined,
            onSuccess: (freshData) => {
                if (tripId && userId && freshData) {
                    saveTripCapsuleSnapshot(tripId, userId, freshData)
                }
            },
        }
    )

    // 🛡️ 智能解構：已解鎖時顯示所有人揭曉條目，旅程中則顯示當前使用者封存條目
    const entries = data ? (data.is_unlocked ? (data.revealed_entries || []) : (data.my_entries || [])) : []

    return {
        capsules: entries,
        summary: data || null,
        isLoading: !error && !data,
        isValidating,
        mutate,
    }
}
