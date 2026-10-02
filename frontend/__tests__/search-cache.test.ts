import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import {
    normalizeSearchKey,
    getSearchCache,
    setSearchCache,
    clearSearchCache,
    type SearchCacheItem
} from '@/lib/search-cache'

// Mock in-memory idb-keyval store
const mockIdbStore = new Map<string, SearchCacheItem>()

vi.mock('idb-keyval', () => ({
    get: vi.fn(async (key: string) => mockIdbStore.get(key)),
    set: vi.fn(async (key: string, val: SearchCacheItem) => {
        mockIdbStore.set(key, val)
    }),
    del: vi.fn(async (key: string) => {
        mockIdbStore.delete(key)
    })
}))

beforeAll(() => {
    // @ts-expect-error Mock indexedDB for test runner
    globalThis.indexedDB = {}
})

beforeEach(async () => {
    mockIdbStore.clear()
    await clearSearchCache()
})

describe('Client-Side Search Cache Engine', () => {
    it('TC-1: normalizeSearchKey strips whitespace and punctuation', () => {
        expect(normalizeSearchKey('  晴空塔 幾點開門？？ ')).toBe('晴空塔 幾點開門')
        expect(normalizeSearchKey('東京鐵塔！門票多少？')).toBe('東京鐵塔 門票多少')
        expect(normalizeSearchKey('')).toBe('')
    })

    it('TC-2: Sets and retrieves cache from L1 and L2', async () => {
        const sources = [{ title: '晴空塔官網', uri: 'https://tokyo-skytree.jp' }]
        await setSearchCache('晴空塔營業時間', sources, '每日 10:00 - 21:00 營業')

        const cached = await getSearchCache('晴空塔營業時間？')
        expect(cached).not.toBeNull()
        expect(cached?.query).toBe('晴空塔營業時間')
        expect(cached?.sources[0].uri).toBe('https://tokyo-skytree.jp')
        expect(cached?.summary).toContain('10:00 - 21:00')
    })

    it('TC-3: Returns null and evicts when TTL expired', async () => {
        const sources = [{ title: '測試', uri: 'https://example.com' }]
        // Set with 50ms TTL
        await setSearchCache('快到期查詢', sources, '內容', 50)

        // Immediately available
        const fresh = await getSearchCache('快到期查詢')
        expect(fresh).not.toBeNull()

        // Wait 60ms for expiry
        await new Promise((resolve) => setTimeout(resolve, 60))

        const expired = await getSearchCache('快到期查詢')
        expect(expired).toBeNull()
    })

    it('TC-4: Gracefully handles empty query or non-existent key', async () => {
        expect(await getSearchCache('')).toBeNull()
        expect(await getSearchCache('從未搜尋過的內容')).toBeNull()
    })

    it('TC-5: Clears specific query from cache', async () => {
        await setSearchCache('Q1', [{ title: 'T1', uri: 'U1' }])
        await setSearchCache('Q2', [{ title: 'T2', uri: 'U2' }])

        await clearSearchCache('Q1')
        expect(await getSearchCache('Q1')).toBeNull()
        expect(await getSearchCache('Q2')).not.toBeNull()
    })
})
