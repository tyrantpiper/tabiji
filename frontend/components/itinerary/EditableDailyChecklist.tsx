"use client"

import { useState, useCallback, useRef, useMemo, useEffect } from "react"
import { motion, AnimatePresence, useReducedMotion } from "framer-motion"
import { CheckSquare, Square, Plus, X, Check, ListChecks, Eye, EyeOff, Loader2, Pencil } from "lucide-react"
import { Input } from "@/components/ui/input"
import { useHaptic } from "@/lib/hooks"
import { toast } from "sonner"
import { ChecklistItem } from "@/lib/itinerary-types"
import { mergeIncomingWithLocalPrivate } from "@/lib/hooks/useTripRealtime"
import { useLanguage } from "@/lib/LanguageContext"
import { cn } from "@/lib/utils"

interface EditableDailyChecklistProps {
    tripId: string
    day: number
    items: ChecklistItem[]
    onUpdate: (items: ChecklistItem[]) => Promise<boolean>
    readOnly?: boolean
    userId?: string
}

const QUICK_ADD_PRESETS = [
    { id: "passport", zh: "護照", en: "Passport" },
    { id: "esim", zh: "網卡 / eSIM", en: "SIM / eSIM" },
    { id: "powerbank", zh: "行動電源", en: "Power Bank" },
    { id: "adapter", zh: "萬用轉接頭", en: "Universal Adapter" },
] as const

// 🛡️ 安全讀取使用者識別碼，防禦 Safari 隱私模式 / WebView Storage SecurityError
function resolveOwnerId(userId?: string): string | undefined {
    if (userId) return userId
    try {
        if (typeof localStorage !== "undefined") {
            return localStorage.getItem("user_uuid") || undefined
        }
    } catch {
        // Ignore storage SecurityError in restricted environments
    }
    return undefined
}

// 🛡️ 安全生成 UUID，兼容非安全上下文 (LAN HTTP 測試環境)
function generateId(): string {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
        return crypto.randomUUID()
    }
    return `chk_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
}

export default function EditableDailyChecklist({
    tripId: _tripId,  // eslint-disable-line @typescript-eslint/no-unused-vars
    day,
    items,
    onUpdate,
    readOnly = false,
    userId
}: EditableDailyChecklistProps) {
    const { lang } = useLanguage()
    const zh = lang === 'zh'
    const haptic = useHaptic()
    const shouldReduceMotion = Boolean(useReducedMotion())
    const [localItems, setLocalItems] = useState<ChecklistItem[]>(items || [])

    const [isAdding, setIsAdding] = useState(false)
    const [newItemText, setNewItemText] = useState("")
    const [newItemPrivate, setNewItemPrivate] = useState(false)
    const [isUpdating, setIsUpdating] = useState(false)
    // 🆕 Per-item processing state for anti-spam
    const [processingItems, setProcessingItems] = useState<Set<string>>(new Set())
    // 🆕 編輯模式狀態
    const [isEditing, setIsEditing] = useState(false)
    const [editData, setEditData] = useState<ChecklistItem[]>([])

    // Debounce ref for toggle updates & committed baseline tracking
    const debounceRef = useRef<NodeJS.Timeout | null>(null)
    const hasPendingDebounceRef = useRef(false)
    const committedItemsRef = useRef<ChecklistItem[]>(items || [])
    const localItemsRef = useRef<ChecklistItem[]>(items || [])
    // 🛡️ Synchronous single-frame lock to prevent double-tap duplicate creation
    const actionLockRef = useRef(false)

    // 🆕 Track pending optimistic updates to prevent useEffect from overwriting
    const pendingUpdatesCount = useRef(0)

    const updateLocalItemsState = useCallback((nextItems: ChecklistItem[], markCommitted = false) => {
        localItemsRef.current = nextItems
        if (markCommitted) {
            committedItemsRef.current = nextItems
        }
        setLocalItems(nextItems)
    }, [])

    // 🔧 FIX: Sync local items when props update (async data loading)
    // 🛡️ L4 Protection: Skip sync if user is currently adding an item, editing, or mutation in-flight
    useEffect(() => {
        if (pendingUpdatesCount.current > 0 || hasPendingDebounceRef.current || isAdding || isEditing) return
        updateLocalItemsState(items || [], true)
    }, [items, isAdding, isEditing, updateLocalItemsState])

    // ⚡ 即時協同：接收廣播事件，毫秒級反映同伴勾選或修改的清單內容
    useEffect(() => {
        const handleCollab = (e: Event) => {
            const detail = (e as CustomEvent).detail
            if (detail?.event === "checklist:update" && Number(detail?.dayIndex) === Number(day)) {
                if (
                    Array.isArray(detail.items) &&
                    !isEditing &&
                    !isAdding &&
                    pendingUpdatesCount.current === 0 &&
                    !hasPendingDebounceRef.current
                ) {
                    const currentOwnerId = resolveOwnerId(userId)
                    const mergedItems = mergeIncomingWithLocalPrivate(
                        localItemsRef.current,
                        detail.items as ChecklistItem[],
                        currentOwnerId,
                        false,
                        true
                    )
                    updateLocalItemsState(mergedItems, true)
                }
            }
        }
        window.addEventListener("tabiji:collab-event", handleCollab)
        return () => window.removeEventListener("tabiji:collab-event", handleCollab)
    }, [day, userId, isEditing, isAdding, updateLocalItemsState])

    // 🆕 Cleanup: cancel debounce on unmount or before immediate mutation to prevent zombie write / counter leak
    const cancelPendingDebounce = useCallback(() => {
        if (debounceRef.current) {
            clearTimeout(debounceRef.current)
            debounceRef.current = null
        }
        if (hasPendingDebounceRef.current) {
            hasPendingDebounceRef.current = false
            pendingUpdatesCount.current = Math.max(0, pendingUpdatesCount.current - 1)
        }
    }, [])

    useEffect(() => {
        return () => {
            cancelPendingDebounce()
        }
    }, [cancelPendingDebounce])

    // 切換勾選狀態 (with leak-free debounce & committed baseline rollback)
    const toggleItem = useCallback((id: string) => {
        if (readOnly || isUpdating || actionLockRef.current) return

        haptic.tap()

        // 🛡️ Only increment pendingUpdatesCount ONCE per debounce window!
        if (!hasPendingDebounceRef.current) {
            hasPendingDebounceRef.current = true
            pendingUpdatesCount.current++
        }

        // 樂觀更新本地狀態 (基於最新 localItemsRef.current 累加多次點擊)
        const newItems = localItemsRef.current.map(item =>
            item.id === id ? { ...item, checked: !item.checked } : item
        )
        updateLocalItemsState(newItems, false)

        // 重設 Debounce API 呼叫計時器
        if (debounceRef.current) {
            clearTimeout(debounceRef.current)
        }

        debounceRef.current = setTimeout(async () => {
            debounceRef.current = null
            const baselineItems = committedItemsRef.current
            const itemsToCommit = localItemsRef.current
            setIsUpdating(true)
            try {
                const success = await onUpdate(itemsToCommit)
                if (!success) {
                    updateLocalItemsState(baselineItems, true)
                    toast.error(zh ? "更新失敗" : "Update failed")
                } else {
                    committedItemsRef.current = itemsToCommit
                }
            } catch {
                updateLocalItemsState(baselineItems, true)
                toast.error(zh ? "更新失敗" : "Update failed")
            } finally {
                setIsUpdating(false)
                if (hasPendingDebounceRef.current) {
                    hasPendingDebounceRef.current = false
                    pendingUpdatesCount.current = Math.max(0, pendingUpdatesCount.current - 1)
                }
            }
        }, 500)
    }, [onUpdate, readOnly, isUpdating, haptic, zh, updateLocalItemsState])

    // 新增項目 (支援表單輸入與空狀態快選晶片一鍵寫入，含同步互斥鎖與錯誤捕捉回滾)
    const addItemWithText = async (rawText: string, isPrivateOverride?: boolean) => {
        const trimmed = rawText.trim()
        if (!trimmed || isUpdating || actionLockRef.current || readOnly) return

        cancelPendingDebounce()
        actionLockRef.current = true
        setIsUpdating(true)
        haptic.success()
        pendingUpdatesCount.current++

        const prevItems = localItemsRef.current
        const isPrivate = isPrivateOverride ?? newItemPrivate
        const newItem: ChecklistItem = {
            id: generateId(),
            text: trimmed,
            checked: false,
            is_private: isPrivate,
            ...(isPrivate ? { private_owner_id: resolveOwnerId(userId) } : {}),
        }
        const newItems = [...prevItems, newItem]
        // ⚡ 0ms 樂觀更新
        updateLocalItemsState(newItems, false)

        try {
            const success = await onUpdate(newItems)
            if (!success) {
                updateLocalItemsState(prevItems, true)
                toast.error(zh ? "新增失敗" : "Failed to add")
            } else {
                committedItemsRef.current = newItems
                setNewItemText("")
                setNewItemPrivate(false)
                setIsAdding(false)
                toast.success(zh ? "已新增項目" : "Item added")
            }
        } catch {
            updateLocalItemsState(prevItems, true)
            toast.error(zh ? "新增失敗" : "Failed to add")
        } finally {
            setIsUpdating(false)
            actionLockRef.current = false
            pendingUpdatesCount.current = Math.max(0, pendingUpdatesCount.current - 1)
        }
    }

    const addItem = async () => {
        await addItemWithText(newItemText, newItemPrivate)
    }

    // 刪除項目
    const removeItem = async (id: string) => {
        if (readOnly || processingItems.has(id) || isUpdating || actionLockRef.current) return

        cancelPendingDebounce()
        actionLockRef.current = true
        haptic.tap()
        pendingUpdatesCount.current++
        setProcessingItems(prev => new Set(prev).add(id))
        const prevItems = localItemsRef.current
        const newItems = prevItems.filter(item => item.id !== id)
        updateLocalItemsState(newItems, false)

        setIsUpdating(true)
        try {
            const success = await onUpdate(newItems)
            if (!success) {
                updateLocalItemsState(prevItems, true)
                toast.error(zh ? "刪除失敗" : "Delete failed")
            } else {
                committedItemsRef.current = newItems
            }
        } catch {
            updateLocalItemsState(prevItems, true)
            toast.error(zh ? "刪除失敗" : "Delete failed")
        } finally {
            setIsUpdating(false)
            actionLockRef.current = false
            pendingUpdatesCount.current = Math.max(0, pendingUpdatesCount.current - 1)
            setProcessingItems(prev => {
                const next = new Set(prev)
                next.delete(id)
                return next
            })
        }
    }

    // 🆕 Toggle privacy for checklist items
    const handleTogglePrivacy = async (id: string) => {
        if (readOnly || processingItems.has(id) || isUpdating || actionLockRef.current) return

        cancelPendingDebounce()
        actionLockRef.current = true
        haptic.tap()
        pendingUpdatesCount.current++
        setProcessingItems(prev => new Set(prev).add(id))
        const prevItems = localItemsRef.current
        const ownerId = resolveOwnerId(userId)
        const newItems: ChecklistItem[] = prevItems.map(item =>
            item.id === id ? {
                ...item,
                is_private: !item.is_private,
                private_owner_id: !item.is_private ? ownerId : undefined
            } : item
        )
        updateLocalItemsState(newItems, false)

        setIsUpdating(true)
        try {
            const success = await onUpdate(newItems)
            if (!success) {
                updateLocalItemsState(prevItems, true)
                toast.error(zh ? "更新失敗" : "Update failed")
            } else {
                committedItemsRef.current = newItems
                const item = newItems.find(i => i.id === id)
                toast.success(item?.is_private ? (zh ? "已設為私人" : "Set to private") : (zh ? "已設為公開" : "Set to public"))
            }
        } catch {
            updateLocalItemsState(prevItems, true)
            toast.error(zh ? "更新失敗" : "Update failed")
        } finally {
            setIsUpdating(false)
            actionLockRef.current = false
            pendingUpdatesCount.current = Math.max(0, pendingUpdatesCount.current - 1)
            setProcessingItems(prev => {
                const next = new Set(prev)
                next.delete(id)
                return next
            })
        }
    }

    // 🆕 編輯模式
    const handleCancelAdd = useCallback(() => {
        setIsAdding(false)
        setNewItemText("")
        setNewItemPrivate(false)
    }, [])

    const handleStartEdit = () => {
        setEditData([...localItemsRef.current])
        setIsEditing(true)
        handleCancelAdd()
    }

    const handleSaveEdit = async () => {
        if (readOnly || isUpdating || actionLockRef.current) return
        if (editData.some((item) => !(item.text ?? "").trim())) {
            toast.error(zh ? "請輸入項目內容" : "Please enter text for all items")
            return
        }
        const normalizedItems = editData.map((item) => ({
            ...item,
            text: (item.text ?? "").trim(),
        }))
        cancelPendingDebounce()
        actionLockRef.current = true
        setIsUpdating(true)
        pendingUpdatesCount.current++
        try {
            if (await onUpdate(normalizedItems)) {
                updateLocalItemsState(normalizedItems, true)
                setIsEditing(false)
                setEditData([])
                toast.success(zh ? "已儲存修改" : "Changes saved")
            } else {
                toast.error(zh ? "儲存失敗" : "Save failed")
            }
        } catch {
            toast.error(zh ? "儲存失敗" : "Save failed")
        } finally {
            setIsUpdating(false)
            actionLockRef.current = false
            pendingUpdatesCount.current = Math.max(0, pendingUpdatesCount.current - 1)
        }
    }

    const handleCancelEdit = useCallback(() => {
        setIsEditing(false)
        setEditData([])
    }, [])

    // 🛡️ 攔截內嵌新增／編輯表單內的 Escape，避免冒泡至 window 關閉父層 IOSBottomSheet
    useEffect(() => {
        if (!isAdding && !isEditing) return
        const handleDocumentKeyDown = (e: KeyboardEvent) => {
            if (e.key !== "Escape" || e.isComposing || e.defaultPrevented) return
            if (
                document.querySelector(
                    '[data-slot="dialog-content"][data-state="open"], [data-slot="alert-dialog-content"][data-state="open"], [data-slot="popover-content"][data-state="open"]'
                )
            ) {
                return
            }
            e.preventDefault()
            e.stopPropagation()
            if (isEditing) {
                handleCancelEdit()
            } else if (isAdding) {
                handleCancelAdd()
            }
        }
        document.addEventListener("keydown", handleDocumentKeyDown)
        return () => document.removeEventListener("keydown", handleDocumentKeyDown)
    }, [isAdding, isEditing, handleCancelAdd, handleCancelEdit])

    const handleCardKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
        if (e.nativeEvent.isComposing || e.key !== "Escape" || e.defaultPrevented) return
        if (!isAdding && !isEditing) return
        if (
            document.querySelector(
                '[data-slot="dialog-content"][data-state="open"], [data-slot="alert-dialog-content"][data-state="open"], [data-slot="popover-content"][data-state="open"]'
            )
        ) {
            return
        }
        e.preventDefault()
        e.stopPropagation()
        if (isEditing) {
            handleCancelEdit()
        } else if (isAdding) {
            handleCancelAdd()
        }
    }

    const handleUpdateEditItem = (id: string, text: string) => {
        setEditData(prev => prev.map(item =>
            item.id === id ? { ...item, text } : item
        ))
    }

    // 計算完成進度
    const completedCount = localItems.filter(item => item.checked).length
    const totalCount = localItems.length
    const progressPercent = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0

    // 🆕 排序邏輯：1. 私人項目最優先, 2. 已勾選項目次優先, 3. 保持穩定原始順序
    const sortedItems = useMemo(() => {
        const indexMap = new Map(localItems.map((item, i) => [item.id, i]))

        return [...localItems].sort((a, b) => {
            const aPrivate = !!a.is_private
            const bPrivate = !!b.is_private
            if (aPrivate !== bPrivate) return aPrivate ? -1 : 1

            const aChecked = !!a.checked
            const bChecked = !!b.checked
            if (aChecked !== bChecked) return aChecked ? -1 : 1

            return (indexMap.get(a.id) ?? 0) - (indexMap.get(b.id) ?? 0)
        })
    }, [localItems])

    const secondaryPillBtnClass =
        "inline-flex items-center justify-center h-8 px-2.5 rounded-full text-xs font-medium whitespace-nowrap shrink-0 bg-tabiji-mist/70 hover:bg-tabiji-mist text-tabiji-charcoal dark:bg-white/8 dark:hover:bg-white/14 dark:text-tabiji-paper transition-colors touch-manipulation disabled:opacity-50"
    const primaryActionBtnClass =
        "inline-flex items-center justify-center h-8 px-3 rounded-full text-xs font-semibold whitespace-nowrap shrink-0 bg-tabiji-forest hover:bg-tabiji-forest/90 text-tabiji-paper dark:bg-emerald-600 dark:hover:bg-emerald-500 dark:text-white transition-colors touch-manipulation disabled:opacity-50"

    return (
        <div
            onKeyDown={handleCardKeyDown}
            className="bg-white/95 dark:bg-[#182320]/90 border border-tabiji-forest/10 dark:border-white/10 rounded-2xl p-4 shadow-[0_2px_12px_rgba(11,48,38,0.05)] dark:shadow-[0_2px_14px_rgba(0,0,0,0.3)] transition-all"
        >
            {/* 標題列 */}
            <div className="flex flex-wrap items-center justify-between gap-2 mb-3.5">
                <div className="flex items-center gap-2.5 min-w-[min(100%,9rem)] flex-1">
                    <div className="w-8 h-8 rounded-xl bg-indigo-500/12 dark:bg-indigo-400/15 text-indigo-700 dark:text-indigo-300 flex items-center justify-center shrink-0">
                        <ListChecks className="w-4 h-4" />
                    </div>
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 min-w-0">
                        <span className="text-sm font-bold text-tabiji-charcoal dark:text-tabiji-paper leading-snug wrap-break-word">
                            {zh ? "行前清單" : "Pre-trip Checklist"}
                        </span>
                        {totalCount > 0 && (
                            <span className="text-xs font-semibold tabular-nums text-indigo-700 dark:text-indigo-300 bg-indigo-500/12 dark:bg-indigo-400/15 px-2 py-0.5 rounded-full shrink-0">
                                {completedCount}/{totalCount} ({progressPercent}%)
                            </span>
                        )}
                    </div>
                </div>
                {!readOnly && !isAdding && !isEditing && (
                    <div className="flex flex-wrap items-center justify-end gap-1.5 shrink-0 ml-auto">
                        {localItems.length > 0 && (
                            <button
                                type="button"
                                onClick={handleStartEdit}
                                disabled={isUpdating}
                                className={secondaryPillBtnClass}
                            >
                                <Pencil className="w-3 h-3 mr-1" />
                                {zh ? "編輯" : "Edit"}
                            </button>
                        )}
                        <button
                            type="button"
                            onClick={() => setIsAdding(true)}
                            disabled={isUpdating}
                            className={secondaryPillBtnClass}
                        >
                            <Plus className="w-3.5 h-3.5 mr-0.5" />
                            {zh ? "新增" : "Add"}
                        </button>
                    </div>
                )}
                {isEditing && (
                    <div className="flex flex-wrap items-center justify-end gap-1.5 shrink-0 ml-auto">
                        <button
                            type="button"
                            className={secondaryPillBtnClass}
                            onClick={handleCancelEdit}
                        >
                            {zh ? "取消" : "Cancel"}
                        </button>
                        <button
                            type="button"
                            className={primaryActionBtnClass}
                            onClick={handleSaveEdit}
                            disabled={isUpdating}
                        >
                            {isUpdating ? (
                                <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                            ) : (
                                <Check className="w-3.5 h-3.5 mr-1" />
                            )}
                            {zh ? "儲存" : "Save"}
                        </button>
                    </div>
                )}
            </div>

            {/* 進度條 */}
            {totalCount > 0 && (
                <div className="h-1.5 bg-indigo-500/12 dark:bg-indigo-400/15 rounded-full mb-3.5 overflow-hidden">
                    <div
                        className="h-full bg-indigo-600 dark:bg-indigo-400 rounded-full transition-all duration-300"
                        style={{ width: `${progressPercent}%` }}
                    />
                </div>
            )}

            {/* 清單項目 */}
            <div className="space-y-1.5">
                {/* 現代空狀態＋4 顆旅途常用快選晶片 */}
                {localItems.length === 0 && !isAdding && !isEditing && (
                    <div className="py-6 px-4 text-center rounded-xl bg-tabiji-paper/45 dark:bg-white/[0.02] border border-dashed border-tabiji-forest/12 dark:border-white/10">
                        <div className="w-11 h-11 rounded-2xl bg-indigo-500/12 dark:bg-indigo-400/15 text-indigo-700 dark:text-indigo-300 flex items-center justify-center mx-auto mb-2.5">
                            <ListChecks className="w-5 h-5" />
                        </div>
                        <p className="text-sm font-semibold text-tabiji-charcoal dark:text-tabiji-paper">
                            {zh ? "尚無行前清單項目" : "No checklist items yet"}
                        </p>
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 mb-3.5">
                            {zh
                                ? "把出發前必備物品記下來，逐項打勾確認"
                                : "List your essential travel gear and check them off one by one"}
                        </p>
                        {!readOnly && (
                            <>
                                <button
                                    type="button"
                                    onClick={() => setIsAdding(true)}
                                    disabled={isUpdating}
                                    className={primaryActionBtnClass}
                                >
                                    <Plus className="w-3.5 h-3.5 mr-1" />
                                    {zh ? "新增第一筆項目" : "Add First Item"}
                                </button>
                                <div className="mt-4 pt-3.5 border-t border-tabiji-forest/10 dark:border-white/10">
                                    <p className="text-[11px] font-medium text-slate-500 dark:text-slate-400 mb-2">
                                        {zh ? "快速加入旅途必備：" : "Quick-add essentials:"}
                                    </p>
                                    <div className="flex flex-wrap items-center justify-center gap-1.5">
                                        {QUICK_ADD_PRESETS.map((preset) => {
                                            const label = zh ? preset.zh : preset.en
                                            return (
                                                <button
                                                    key={preset.id}
                                                    type="button"
                                                    disabled={isUpdating}
                                                    onClick={() => addItemWithText(label, false)}
                                                    className="inline-flex items-center gap-1 px-2.5 h-7 rounded-full text-xs font-medium bg-white/90 dark:bg-white/6 text-tabiji-charcoal dark:text-tabiji-paper border border-tabiji-forest/12 dark:border-white/12 hover:bg-indigo-500/10 hover:text-indigo-700 dark:hover:bg-indigo-400/15 dark:hover:text-indigo-300 transition-colors touch-manipulation disabled:opacity-50"
                                                >
                                                    <span>+ {label}</span>
                                                </button>
                                            )
                                        })}
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                )}

                {/* 編輯模式：顯示所有項目的編輯表單 */}
                {isEditing &&
                    editData.map((item) => (
                        <div
                            key={item.id}
                            className="flex items-center gap-2 p-2.5 bg-tabiji-paper/65 dark:bg-white/[0.04] rounded-xl border border-tabiji-forest/12 dark:border-white/12"
                        >
                            <Square className="w-4 h-4 text-indigo-400 shrink-0" />
                            <Input
                                className="flex-1 h-9 text-sm bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                value={item.text}
                                onChange={(e) => handleUpdateEditItem(item.id, e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.nativeEvent.isComposing) return
                                    if (e.key === "Enter") {
                                        e.preventDefault()
                                        handleSaveEdit()
                                    }
                                    if (e.key === "Escape") {
                                        e.preventDefault()
                                        e.stopPropagation()
                                        handleCancelEdit()
                                    }
                                }}
                            />
                        </div>
                    ))}

                {/* 正常模式：顯示清單（解耦同級按鈕 DOM 架構） */}
                {!isEditing && (
                    <AnimatePresence mode="popLayout">
                        {sortedItems.map((item) => (
                            <motion.div
                                key={item.id}
                                layout={!shouldReduceMotion}
                                initial={shouldReduceMotion ? false : { opacity: 0, scale: 0.96 }}
                                animate={{ opacity: 1, scale: 1 }}
                                exit={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.96 }}
                                transition={
                                    shouldReduceMotion
                                        ? { duration: 0 }
                                        : {
                                              layout: { type: "spring", stiffness: 500, damping: 35 },
                                              opacity: { duration: 0.15 },
                                          }
                                }
                                className={cn(
                                    "group flex items-center gap-2 p-2.5 rounded-xl border transition-colors",
                                    item.checked
                                        ? "bg-indigo-500/8 dark:bg-indigo-400/10 border-indigo-500/15 dark:border-indigo-400/20"
                                        : "bg-tabiji-paper/55 dark:bg-white/[0.03] border-tabiji-forest/8 dark:border-white/8 hover:bg-tabiji-paper/85 dark:hover:bg-white/[0.06]",
                                    item.is_private && "opacity-75 border-dashed border-amber-500/35"
                                )}
                            >
                                {/* 同級勾選主按鈕 (Sibling Button 1: 完整無障礙鍵盤與點擊區) */}
                                <button
                                    type="button"
                                    onClick={() => toggleItem(item.id)}
                                    disabled={readOnly || isUpdating}
                                    aria-pressed={item.checked}
                                    className="flex-1 min-w-0 flex items-center gap-2.5 text-left touch-manipulation disabled:cursor-default"
                                >
                                    <motion.span
                                        className="shrink-0 flex items-center justify-center"
                                        animate={shouldReduceMotion ? undefined : { scale: item.checked ? 1.08 : 1 }}
                                        transition={{ type: "spring", stiffness: 400, damping: 20 }}
                                    >
                                        {item.checked ? (
                                            <CheckSquare className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
                                        ) : (
                                            <Square className="w-5 h-5 text-slate-400 dark:text-slate-500" />
                                        )}
                                    </motion.span>
                                    <span
                                        className={cn(
                                            "flex-1 min-w-0 text-sm font-medium wrap-anywhere transition-colors",
                                            item.checked
                                                ? "line-through text-slate-400 dark:text-slate-500"
                                                : "text-tabiji-charcoal dark:text-tabiji-paper"
                                        )}
                                    >
                                        {item.is_private && (
                                            <EyeOff className="w-3.5 h-3.5 inline mr-1.5 text-amber-500" />
                                        )}
                                        {item.text}
                                    </span>
                                </button>

                                {/* 同級隱私切換 + 刪除按鈕 (Sibling Buttons 2 & 3) */}
                                {!readOnly && (
                                    <div className="flex items-center gap-0.5 shrink-0">
                                        <button
                                            type="button"
                                            onClick={() => handleTogglePrivacy(item.id)}
                                            aria-label={
                                                item.is_private
                                                    ? zh
                                                        ? "設為公開"
                                                        : "Make public"
                                                    : zh
                                                      ? "設為私人"
                                                      : "Make private"
                                            }
                                            title={
                                                item.is_private
                                                    ? zh
                                                        ? "設為公開"
                                                        : "Make public"
                                                    : zh
                                                      ? "設為私人"
                                                      : "Make private"
                                            }
                                            disabled={processingItems.has(item.id) || isUpdating}
                                            className={cn(
                                                "p-1.5 rounded-lg transition-colors min-w-8 min-h-8 flex items-center justify-center touch-manipulation",
                                                processingItems.has(item.id)
                                                    ? "opacity-50 cursor-not-allowed"
                                                    : item.is_private
                                                      ? "text-amber-500 hover:text-amber-600 hover:bg-amber-500/10"
                                                      : "text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-tabiji-mist/50 dark:hover:bg-white/10"
                                            )}
                                        >
                                            {processingItems.has(item.id) ? (
                                                <Loader2 className="w-4 h-4 animate-spin" />
                                            ) : item.is_private ? (
                                                <EyeOff className="w-4 h-4" />
                                            ) : (
                                                <Eye className="w-4 h-4" />
                                            )}
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => removeItem(item.id)}
                                            aria-label={zh ? `刪除項目 ${item.text}` : `Delete item ${item.text}`}
                                            disabled={processingItems.has(item.id) || isUpdating}
                                            className={cn(
                                                "p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-500/10 transition-colors min-w-8 min-h-8 flex items-center justify-center touch-manipulation",
                                                processingItems.has(item.id) && "opacity-50 cursor-not-allowed"
                                            )}
                                        >
                                            {processingItems.has(item.id) ? (
                                                <Loader2 className="w-4 h-4 animate-spin" />
                                            ) : (
                                                <X className="w-4 h-4" />
                                            )}
                                        </button>
                                    </div>
                                )}
                            </motion.div>
                        ))}
                    </AnimatePresence>
                )}

                {/* 新增分層內嵌表單 (含 IME 組字守衛與隱私微開關) */}
                {isAdding && (
                    <div className="bg-tabiji-paper/65 dark:bg-white/[0.04] rounded-xl p-3.5 border border-tabiji-forest/12 dark:border-white/12 space-y-2.5 animate-in fade-in zoom-in-95 duration-200">
                        <div className="flex items-center gap-2">
                            <Square className="w-4 h-4 text-indigo-500 shrink-0" />
                            <Input
                                value={newItemText}
                                onChange={(e) => setNewItemText(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.nativeEvent.isComposing) return
                                    if (e.key === "Enter") {
                                        e.preventDefault()
                                        addItem()
                                    }
                                    if (e.key === "Escape") {
                                        e.preventDefault()
                                        e.stopPropagation()
                                        handleCancelAdd()
                                    }
                                }}
                                placeholder={zh ? "輸入待辦事項（例如：護照影本、充電線）..." : "Enter a to-do item..."}
                                className="flex-1 h-10 text-sm bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                autoFocus
                            />
                        </div>
                        <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-tabiji-forest/10 dark:border-white/10">
                            <button
                                type="button"
                                aria-pressed={newItemPrivate}
                                onClick={() => setNewItemPrivate((prev) => !prev)}
                                className={cn(
                                    "inline-flex items-center gap-1.5 px-2.5 h-8 rounded-full text-xs font-medium transition-colors touch-manipulation",
                                    newItemPrivate
                                        ? "bg-amber-500/15 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300 border border-amber-500/30"
                                        : "bg-white/70 dark:bg-white/6 text-slate-600 dark:text-slate-300 border border-tabiji-forest/10 dark:border-white/10 hover:bg-tabiji-mist/60 dark:hover:bg-white/10"
                                )}
                            >
                                {newItemPrivate ? (
                                    <>
                                        <EyeOff className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                                        <span>{zh ? "僅自己可見" : "Only me"}</span>
                                    </>
                                ) : (
                                    <>
                                        <Eye className="w-3.5 h-3.5 text-slate-400" />
                                        <span>{zh ? "公開" : "Public"}</span>
                                    </>
                                )}
                            </button>
                            <div className="flex items-center gap-1.5 ml-auto">
                                <button
                                    type="button"
                                    onClick={handleCancelAdd}
                                    className={secondaryPillBtnClass}
                                >
                                    {zh ? "取消" : "Cancel"}
                                </button>
                                <button
                                    type="button"
                                    onClick={addItem}
                                    disabled={!newItemText.trim() || isUpdating}
                                    className={primaryActionBtnClass}
                                >
                                    <Check className="w-3.5 h-3.5 mr-1" />
                                    {zh ? "新增" : "Add"}
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}
