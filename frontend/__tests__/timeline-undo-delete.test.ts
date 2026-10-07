import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { UndoDeleteManager } from '@/lib/undo-delete-manager'

describe('UndoDeleteManager - Lifecycle, Concurrency & Security Sentinel Tests', () => {
    let mockCalls: string[]
    let mockDeleteApi: (id: string) => Promise<unknown>

    beforeEach(() => {
        vi.useFakeTimers()
        mockCalls = []
        mockDeleteApi = vi.fn(async (id: string) => {
            mockCalls.push(id)
            return true
        })
    })

    afterEach(() => {
        vi.restoreAllMocks()
    })

    it('does not invoke delete API immediately upon scheduling', () => {
        const manager = new UndoDeleteManager(mockDeleteApi, 5000)
        manager.scheduleDelete('act-1', { title: 'Taipei 101' })

        expect(mockCalls).toEqual([])
        expect(manager.isPending('act-1')).toBe(true)
        expect(manager.size).toBe(1)
    })

    it('successfully undos delete before timeout and prevents API call', () => {
        const manager = new UndoDeleteManager(mockDeleteApi, 5000)
        manager.scheduleDelete('act-1', { title: 'Taipei 101' })

        // 經過 2 秒後點擊 Undo
        vi.advanceTimersByTime(2000)
        const restored = manager.undoDelete('act-1')

        expect(restored).toEqual({ title: 'Taipei 101' })
        expect(manager.isPending('act-1')).toBe(false)
        expect(manager.size).toBe(0)

        // 經過剩餘的 3 秒 (總共 5 秒)
        vi.advanceTimersByTime(3000)
        expect(mockCalls).toEqual([])
    })

    it('automatically invokes delete API after 5000ms delay if not undone', async () => {
        const manager = new UndoDeleteManager(mockDeleteApi, 5000)
        manager.scheduleDelete('act-1', { title: 'Taipei 101' })

        // 前進 4999ms: 尚未觸發
        vi.advanceTimersByTime(4999)
        expect(mockCalls).toEqual([])

        // 前進至 5000ms: 觸發刪除
        vi.advanceTimersByTime(1)
        await Promise.resolve() // 等待 Promise microtask

        expect(mockCalls).toEqual(['act-1'])
        expect(manager.isPending('act-1')).toBe(false)
    })

    it('flushes all pending deletions synchronously upon unmount / page change', async () => {
        const manager = new UndoDeleteManager(mockDeleteApi, 5000)
        manager.scheduleDelete('act-1', { title: 'Item 1' })
        manager.scheduleDelete('act-2', { title: 'Item 2' })
        manager.scheduleDelete('act-3', { title: 'Item 3' })

        expect(manager.size).toBe(3)
        expect(mockCalls).toEqual([])

        // 模擬使用者快速切換天數分頁，觸發 flushAll
        await manager.flushAll()

        expect(mockCalls).toEqual(['act-1', 'act-2', 'act-3'])
        expect(manager.size).toBe(0)

        // 後續即使時間推進，也不會重複呼叫
        vi.advanceTimersByTime(6000)
        expect(mockCalls).toEqual(['act-1', 'act-2', 'act-3'])
    })

    it('handles idempotent scheduling and overwrites previous timer safely', () => {
        const manager = new UndoDeleteManager(mockDeleteApi, 5000)
        manager.scheduleDelete('act-1', { title: 'V1' })

        vi.advanceTimersByTime(3000)
        // 重新排程同一 ID
        manager.scheduleDelete('act-1', { title: 'V2' })

        // 再過 3000ms (距首次排程 6 秒，但距二次排程僅 3 秒) -> 應尚未刪除
        vi.advanceTimersByTime(3000)
        expect(mockCalls).toEqual([])

        // 再過 2000ms -> 觸發二次排程的刪除
        vi.advanceTimersByTime(2000)
        expect(mockCalls).toEqual(['act-1'])
    })

    it('ensures deduplicated insertion pattern prevents duplicate items in optimistic array', () => {
        const initialActivities = [
            { id: 'act-1', place: 'Taipei 101' },
            { id: 'act-2', place: 'Din Tai Fung' }
        ]
        const restoredItem = { id: 'act-1', place: 'Taipei 101' }

        // 模擬先 filter 再 append 的防禦邏輯
        const cleanList = initialActivities.filter((a) => a.id !== restoredItem.id)
        const updatedList = [...cleanList, restoredItem]

        expect(updatedList.filter((a) => a.id === 'act-1').length).toBe(1)
        expect(updatedList.length).toBe(2)
    })
})
