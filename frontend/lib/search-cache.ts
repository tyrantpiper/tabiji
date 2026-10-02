import { get, set, del } from "idb-keyval"

const SEARCH_CACHE_PREFIX = "tabidachi_search_cache_"
const DEFAULT_TTL_MS = 2 * 60 * 60 * 1000 // 預設 2 小時有效期限 (景點與營業時間時效)

export interface SearchCacheItem {
    query: string
    sources: Array<{ title: string; uri: string }>
    summary?: string
    timestamp: number
    ttlMs: number
}

// 🧠 L1 記憶體微秒級快取 (0ms RAM Cache)
const l1SearchCache = new Map<string, SearchCacheItem>()

/**
 * 正規化搜尋詞，消除標點與多餘空格，提高快取命中率
 */
export function normalizeSearchKey(query: string): string {
    if (!query) return ""
    return query
        .trim()
        .toLowerCase()
        .replace(/[？?！!。，,、\s]+/g, " ")
        .trim()
}

/**
 * 檢查環境是否支援 Storage
 */
function isBrowserStorageAvailable(): boolean {
    return typeof window !== "undefined" && typeof indexedDB !== "undefined"
}

/**
 * 讀取本機搜尋快取 (先查 L1 RAM -> 再查 L2 IndexedDB)
 */
export async function getSearchCache(query: string): Promise<SearchCacheItem | null> {
    const key = normalizeSearchKey(query)
    if (!key) return null

    // 1. L1 記憶體快查
    const memCached = l1SearchCache.get(key)
    if (memCached) {
        if (Date.now() - memCached.timestamp < memCached.ttlMs) {
            return memCached
        }
        l1SearchCache.delete(key)
    }

    // 2. L2 IndexedDB 非同步持久化讀取
    if (!isBrowserStorageAvailable()) return null

    try {
        const idbKey = SEARCH_CACHE_PREFIX + key
        const idbCached = await get<SearchCacheItem>(idbKey)
        if (idbCached) {
            if (Date.now() - idbCached.timestamp < idbCached.ttlMs) {
                // 反向預熱回 L1 記憶體
                l1SearchCache.set(key, idbCached)
                return idbCached
            }
            // 已過期，背景靜默清理
            await del(idbKey)
        }
    } catch (err) {
        console.warn("[SearchCache] L2 read warning:", err)
    }

    return null
}

/**
 * 寫入本機搜尋快取 (雙寫 L1 RAM + L2 IndexedDB)
 */
export async function setSearchCache(
    query: string,
    sources: Array<{ title: string; uri: string }>,
    summary?: string,
    ttlMs: number = DEFAULT_TTL_MS
): Promise<void> {
    const key = normalizeSearchKey(query)
    if (!key || (!sources.length && !summary)) return

    const item: SearchCacheItem = {
        query: key,
        sources,
        summary,
        timestamp: Date.now(),
        ttlMs
    }

    // 1. 寫入 L1 RAM
    l1SearchCache.set(key, item)

    // 2. 寫入 L2 IndexedDB
    if (isBrowserStorageAvailable()) {
        try {
            await set(SEARCH_CACHE_PREFIX + key, item)
        } catch (err) {
            console.warn("[SearchCache] L2 write warning:", err)
        }
    }
}

/**
 * 清理指定搜尋詞或全部快取 (測試或重置用)
 */
export async function clearSearchCache(query?: string): Promise<void> {
    if (query) {
        const key = normalizeSearchKey(query)
        l1SearchCache.delete(key)
        if (isBrowserStorageAvailable()) {
            try {
                await del(SEARCH_CACHE_PREFIX + key)
            } catch {
                // Ignore
            }
        }
    } else {
        l1SearchCache.clear()
    }
}
