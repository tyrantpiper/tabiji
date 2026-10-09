import { get, set, del } from "idb-keyval"

const SNAPSHOT_KEY_PREFIX = "tabiji_trip_snapshot_"
const LEGACY_SNAPSHOT_KEY_PREFIX = "tabidachi_trip_snapshot_"
const SNAPSHOT_SCHEMA_VERSION = 1

const L0_SYNC_TRIP_PREFIX = "tabiji_l0_sync_trip_"
const LEGACY_L0_SYNC_TRIP_PREFIX = "tabidachi_l0_sync_trip_"

interface SnapshotPayload<T = unknown> {
    data: T
    timestamp: number
    version: number
}

// 🧠 Layer 1: 記憶體微秒級同步快取 (RAM Cache)，供 SWR 首幀 0ms 零骨架屏直出
const l1SnapshotCache = new Map<string, SnapshotPayload>()

/**
 * 檢查是否處於安全且支援 IndexedDB 的瀏覽器環境
 */
function isBrowserWithStorage(): boolean {
    return typeof window !== "undefined" && typeof indexedDB !== "undefined"
}

/**
 * ⚡ 0ms 同步讀取 L1 記憶體快照與 L0 LocalStorage 鏡像
 * 徹底解決「App 被向上刷掉殺死進程後，L1 RAM 歸零、L2 IndexedDB 尚未建立非同步連線」的離線冷啟動白屏空窗！
 * 支援 tabiji_ 與 tabidachi_ 雙前綴回退，保障老使用者資料零丟失並自動無縫升級
 */
export function getTripSnapshotSync<T = unknown>(tripId: string | null | undefined): T | null {
    if (!tripId) return null
    // 1. 先查 L1 RAM 記憶體
    const cached = l1SnapshotCache.get(tripId)
    if (cached && cached.version === SNAPSHOT_SCHEMA_VERSION) {
        return cached.data as T
    }

    // 2. ⚡ L0 硬核保底：冷啟動時自 localStorage 同步讀取 (先查新 key，若無則回退查詢舊 key)
    if (typeof window !== "undefined") {
        try {
            let raw = localStorage.getItem(L0_SYNC_TRIP_PREFIX + tripId)
            let isLegacy = false
            if (!raw) {
                raw = localStorage.getItem(LEGACY_L0_SYNC_TRIP_PREFIX + tripId)
                if (raw) isLegacy = true
            }

            if (raw) {
                const parsed = JSON.parse(raw) as T
                // 反向預熱回 L1 記憶體
                l1SnapshotCache.set(tripId, {
                    data: parsed,
                    timestamp: Date.now(),
                    version: SNAPSHOT_SCHEMA_VERSION,
                })
                // 若讀取自舊 key，自動升級遷移至新 key 並清理舊 key
                if (isLegacy) {
                    try {
                        localStorage.setItem(L0_SYNC_TRIP_PREFIX + tripId, raw)
                        localStorage.removeItem(LEGACY_L0_SYNC_TRIP_PREFIX + tripId)
                    } catch {}
                }
                return parsed
            }
        } catch {
            // 忽略 JSON 解析異常
        }
    }

    return null
}

/**
 * 非同步預熱：自 L2 (IndexedDB) 載入快照至 L1 (記憶體)
 * 支援雙前綴回退 (tabiji_ -> tabidachi_)
 */
export async function preloadTripSnapshot<T = unknown>(tripId: string | null | undefined): Promise<T | null> {
    if (!tripId) return null

    // 若 L1 或 L0 命中則直接返回
    const memoryHit = getTripSnapshotSync<T>(tripId)
    if (memoryHit) return memoryHit

    if (!isBrowserWithStorage()) return null

    try {
        let stored = await get<SnapshotPayload<T>>(SNAPSHOT_KEY_PREFIX + tripId)
        let isLegacy = false
        if (!stored) {
            stored = await get<SnapshotPayload<T>>(LEGACY_SNAPSHOT_KEY_PREFIX + tripId)
            if (stored) isLegacy = true
        }

        if (stored && stored.version === SNAPSHOT_SCHEMA_VERSION && stored.data) {
            l1SnapshotCache.set(tripId, stored)
            // 同步鏡像至 L0
            if (typeof window !== "undefined") {
                try {
                    localStorage.setItem(L0_SYNC_TRIP_PREFIX + tripId, JSON.stringify(stored.data))
                    localStorage.removeItem(LEGACY_L0_SYNC_TRIP_PREFIX + tripId)
                } catch {}
            }
            // 若為 legacy，升級寫入新 key 並清理舊 key
            if (isLegacy) {
                set(SNAPSHOT_KEY_PREFIX + tripId, stored).catch(() => {})
                del(LEGACY_SNAPSHOT_KEY_PREFIX + tripId).catch(() => {})
            }
            return stored.data
        }
        return null
    } catch (err) {
        console.warn("[Storage] L2 IndexedDB read warning (safely ignored):", err)
        return null
    }
}

/**
 * 同步寫入 L1 記憶體、L0 LocalStorage 鏡像，並非同步持久化至 L2 IndexedDB
 */
export async function saveTripSnapshot<T = unknown>(tripId: string | null | undefined, data: T): Promise<void> {
    if (!tripId || !data) return

    const payload: SnapshotPayload<T> = {
        data,
        timestamp: Date.now(),
        version: SNAPSHOT_SCHEMA_VERSION,
    }

    // 1. 0ms 同步更新 L1 記憶體
    l1SnapshotCache.set(tripId, payload)

    // 2. ⚡ 同步鏡像至 L0 LocalStorage (防 App 滑掉進程終止後 RAM 遺失)
    if (typeof window !== "undefined") {
        try {
            localStorage.setItem(L0_SYNC_TRIP_PREFIX + tripId, JSON.stringify(data))
            localStorage.removeItem(LEGACY_L0_SYNC_TRIP_PREFIX + tripId)
        } catch {
            // LocalStorage 配額防禦
        }
    }

    // 3. 非同步持久化至 L2 IndexedDB (大容量保底)
    if (isBrowserWithStorage()) {
        try {
            await set(SNAPSHOT_KEY_PREFIX + tripId, payload)
        } catch (err) {
            console.warn("[Storage] L2 IndexedDB write warning (safely ignored):", err)
        }
    }
}

/**
 * ⚡ 五清自癒閉環：同步抹除 L0 本地儲存、L1 記憶體、L2 IndexedDB 與 L3 Service Worker CacheStorage
 * 徹底杜絕 404 幽靈行程在客戶端或離線時復活
 */
export async function deleteTripSnapshot(tripId: string | null | undefined): Promise<void> {
    if (!tripId) return

    // 1. 清除 L1 記憶體
    l1SnapshotCache.delete(tripId)

    // 2. ⚡ 清除 L0 LocalStorage (同時清除新舊 prefix)
    if (typeof window !== "undefined") {
        try {
            localStorage.removeItem(L0_SYNC_TRIP_PREFIX + tripId)
            localStorage.removeItem(LEGACY_L0_SYNC_TRIP_PREFIX + tripId)
        } catch {}
    }

    // 3. 清除 L2 IndexedDB (同時清除新舊 prefix)
    if (isBrowserWithStorage()) {
        try {
            await del(SNAPSHOT_KEY_PREFIX + tripId)
            await del(LEGACY_SNAPSHOT_KEY_PREFIX + tripId)
        } catch (err) {
            console.warn("[Storage] L2 IndexedDB delete warning (safely ignored):", err)
        }
    }

    // 4. ⚡ 清除 L3 Service Worker CacheStorage (五清閉環：抹除 trips-api-cache)
    if (typeof window !== "undefined" && "caches" in window) {
        try {
            const cache = await caches.open("trips-api-cache")
            const keys = await cache.keys()
            for (const request of keys) {
                if (request.url.includes(`/api/trips/${tripId}`)) {
                    await cache.delete(request)
                }
            }
        } catch (err) {
            console.warn("[Storage] CacheStorage delete warning (safely ignored):", err)
        }
    }
}

/**
 * 清空所有記憶體快照 (測試與全域登出專用)
 */
export function clearAllMemorySnapshots(): void {
    l1SnapshotCache.clear()
    l1TripsListCache.clear()
}

// 🧠 Layer 1: 行程清單微秒級記憶體快取 (RAM Cache)
const TRIPS_LIST_KEY_PREFIX = "tabiji_trips_list_"
const LEGACY_TRIPS_LIST_KEY_PREFIX = "tabidachi_trips_list_"

const L0_SYNC_TRIPS_LIST_PREFIX = "tabiji_l0_sync_trips_list_"
const LEGACY_L0_SYNC_TRIPS_LIST_PREFIX = "tabidachi_l0_sync_trips_list_"

const l1TripsListCache = new Map<string, SnapshotPayload>()

/**
 * ⚡ 0ms 同步讀取行程清單 L1 記憶體快照與 L0 LocalStorage 鏡像 (供 useTrips fallbackData 使用)
 * 支援雙前綴回退相容
 */
export function getTripsListSnapshotSync<T = unknown>(userId: string | null | undefined): T | null {
    if (!userId) return null
    // 1. 先查 L1 RAM
    const cached = l1TripsListCache.get(userId)
    if (cached && cached.version === SNAPSHOT_SCHEMA_VERSION) {
        return cached.data as T
    }

    // 2. ⚡ L0 硬核保底：進程重開時同步自 localStorage 取得 (新舊 key 回退支援)
    if (typeof window !== "undefined") {
        try {
            let raw = localStorage.getItem(L0_SYNC_TRIPS_LIST_PREFIX + userId)
            let isLegacy = false
            if (!raw) {
                raw = localStorage.getItem(LEGACY_L0_SYNC_TRIPS_LIST_PREFIX + userId)
                if (raw) isLegacy = true
            }

            if (raw) {
                const parsed = JSON.parse(raw) as T
                l1TripsListCache.set(userId, {
                    data: parsed,
                    timestamp: Date.now(),
                    version: SNAPSHOT_SCHEMA_VERSION,
                })
                if (isLegacy) {
                    try {
                        localStorage.setItem(L0_SYNC_TRIPS_LIST_PREFIX + userId, raw)
                        localStorage.removeItem(LEGACY_L0_SYNC_TRIPS_LIST_PREFIX + userId)
                    } catch {}
                }
                return parsed
            }
        } catch {}
    }

    return null
}

/**
 * 🚀 非同步預熱行程清單：自 L2 (IndexedDB) 載入快照至 L1 (記憶體)，保障斷網冷啟動秒開
 * 支援雙前綴回退相容
 */
export async function preloadTripsListSnapshot<T = unknown>(userId: string | null | undefined): Promise<T | null> {
    if (!userId) return null

    // 若 L1 或 L0 命中則直接返回
    const memoryHit = getTripsListSnapshotSync<T>(userId)
    if (memoryHit) return memoryHit

    if (!isBrowserWithStorage()) return null

    try {
        let stored = await get<SnapshotPayload<T>>(TRIPS_LIST_KEY_PREFIX + userId)
        let isLegacy = false
        if (!stored) {
            stored = await get<SnapshotPayload<T>>(LEGACY_TRIPS_LIST_KEY_PREFIX + userId)
            if (stored) isLegacy = true
        }

        if (stored && stored.version === SNAPSHOT_SCHEMA_VERSION && stored.data) {
            l1TripsListCache.set(userId, stored)
            if (typeof window !== "undefined") {
                try {
                    localStorage.setItem(L0_SYNC_TRIPS_LIST_PREFIX + userId, JSON.stringify(stored.data))
                    localStorage.removeItem(LEGACY_L0_SYNC_TRIPS_LIST_PREFIX + userId)
                } catch {}
            }
            if (isLegacy) {
                set(TRIPS_LIST_KEY_PREFIX + userId, stored).catch(() => {})
                del(LEGACY_TRIPS_LIST_KEY_PREFIX + userId).catch(() => {})
            }
            return stored.data
        }
        return null
    } catch (err) {
        console.warn("[Storage] L2 IndexedDB trips list read warning (safely ignored):", err)
        return null
    }
}

/**
 * 同步寫入行程清單至 L1 記憶體、L0 LocalStorage，並非同步持久化至 L2 IndexedDB
 */
export async function saveTripsListSnapshot<T = unknown>(userId: string | null | undefined, data: T): Promise<void> {
    if (!userId || !data) return

    const payload: SnapshotPayload<T> = {
        data,
        timestamp: Date.now(),
        version: SNAPSHOT_SCHEMA_VERSION,
    }

    // 1. 0ms 同步更新 L1 記憶體
    l1TripsListCache.set(userId, payload)

    // 2. ⚡ 同步鏡像至 L0 LocalStorage
    if (typeof window !== "undefined") {
        try {
            localStorage.setItem(L0_SYNC_TRIPS_LIST_PREFIX + userId, JSON.stringify(data))
            localStorage.removeItem(LEGACY_L0_SYNC_TRIPS_LIST_PREFIX + userId)
        } catch {}
    }

    // 3. 非同步持久化至 L2 IndexedDB
    if (isBrowserWithStorage()) {
        try {
            await set(TRIPS_LIST_KEY_PREFIX + userId, payload)
        } catch (err) {
            console.warn("[Storage] L2 IndexedDB trips list write warning (safely ignored):", err)
        }
    }
}

