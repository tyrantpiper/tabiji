/**
 * 🛡️ undo-delete-manager.ts - 具備生命週期安全與 Flush 防禦的待刪除隊列管理器
 * 
 * 核心安全特性:
 * 1. 5000ms 樂觀延遲刪除窗口
 * 2. 隨時可調用的 undoDelete(id) 取消刪除
 * 3. 元件卸載 (Unmount) 或切換分頁時的 flushAll() 強制落庫，杜絕幽靈資料
 * 4. 併發多項目獨立計時器追蹤
 */

export interface PendingDeleteItem<T> {
    id: string
    item: T
    timerId: ReturnType<typeof setTimeout>
    createdAt: number
}

export class UndoDeleteManager<T = unknown> {
    private pendingMap = new Map<string, PendingDeleteItem<T>>()
    private deleteFn: (id: string) => Promise<unknown>
    private delayMs: number

    constructor(
        deleteFn: (id: string) => Promise<unknown>,
        delayMs: number = 5000
    ) {
        this.deleteFn = deleteFn
        this.delayMs = delayMs
    }

    /**
     * 📥 排程刪除項目
     * @param id 項目唯一識別碼
     * @param item 項目原始資料 (供 Undo 復原使用)
     * @param onCommitted 真正觸發遠端刪除後的回調
     */
    scheduleDelete(id: string, item: T, onCommitted?: (id: string) => void): void {
        // 若該項目已在待刪除佇列，先清除舊計時器
        if (this.pendingMap.has(id)) {
            clearTimeout(this.pendingMap.get(id)!.timerId)
        }

        const timerId = setTimeout(async () => {
            this.pendingMap.delete(id)
            try {
                await this.deleteFn(id)
                onCommitted?.(id)
            } catch (err) {
                console.error(`[UndoDeleteManager] Failed to delete ${id}:`, err)
            }
        }, this.delayMs)

        this.pendingMap.set(id, {
            id,
            item,
            timerId,
            createdAt: Date.now()
        })
    }

    /**
     * ↩️ 復原 (Undo) 指定項目
     * @returns 原始項目資料，若不存在則回傳 null
     */
    undoDelete(id: string): T | null {
        const pending = this.pendingMap.get(id)
        if (!pending) return null

        clearTimeout(pending.timerId)
        this.pendingMap.delete(id)
        return pending.item
    }

    /**
     * 🚨 強制沖刷 (Flush): 立即終止所有倒數計時，同步呼叫遠端刪除
     * 適用於切換天數分頁、離開頁面或關閉瀏覽器時
     */
    async flushAll(): Promise<void> {
        const items = Array.from(this.pendingMap.values())
        this.pendingMap.clear()

        for (const pending of items) {
            clearTimeout(pending.timerId)
            try {
                await this.deleteFn(pending.id)
            } catch (err) {
                console.error(`[UndoDeleteManager] Flush error for ${pending.id}:`, err)
            }
        }
    }

    /**
     * 🔍 檢查特定項目是否處於待刪除狀態
     */
    isPending(id: string): boolean {
        return this.pendingMap.has(id)
    }

    /**
     * 📊 取得當前隊列大小
     */
    get size(): number {
        return this.pendingMap.size
    }
}
