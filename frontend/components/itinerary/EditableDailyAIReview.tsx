"use client"

import { useState, useMemo, useRef } from "react"
import { ChevronDown, Loader2, RefreshCw, Sparkles, Trash2 } from "lucide-react"
import { tripsApi } from "@/lib/api"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import { useLanguage } from "@/lib/LanguageContext"
import { extractAIReviewHighlights } from "@/lib/itinerary-metrics"

interface EditableDailyAIReviewProps {
    tripId: string
    day: number
    review: string | undefined
    userId?: string              // 🆕 新增
    readOnly?: boolean
    onUpdate: (newReview?: string) => Promise<void> | void  // 刷新行程資料
    className?: string
}

/**
 * 🕵️ AI 深度審核組件
 * 
 * 功能:
 * - 首次生成 AI 審核報告
 * - 重新審核（刷新）
 * - 清除審核報告
 * - 美觀列點渲染
 */
export default function EditableDailyAIReview({
    tripId,
    day,
    review,
    userId,
    readOnly = false,
    onUpdate,
    className,
}: EditableDailyAIReviewProps) {
    const [isLoading, setIsLoading] = useState(false)
    const { lang } = useLanguage()
    const zh = lang === 'zh'
    const [loadingAction, setLoadingAction] = useState<"generate" | "clear" | null>(null)
    const [isExpanded, setIsExpanded] = useState(true)  // 預設展開以利抽屜內直接閱讀
    const actionLockRef = useRef(false)

    // 🚀 樂觀即時狀態 (Optimistic Instant State: 綁定 tripId-day 防跨天串擾)
    const scopeKey = `${tripId}-${day}`
    const [optimisticState, setOptimisticState] = useState<{ key: string; value: string | null }>({
        key: scopeKey,
        value: null,
    })

    const effectiveReview = optimisticState.key === scopeKey && optimisticState.value !== null
        ? optimisticState.value
        : review

    const highlights = useMemo(() => extractAIReviewHighlights(effectiveReview), [effectiveReview])
    const cleanText = highlights.cleanReviewText || effectiveReview

    // 生成/重新生成 AI 審核
    const handleGenerate = async () => {
        if (readOnly || isLoading || actionLockRef.current || !tripId) return

        actionLockRef.current = true
        setIsLoading(true)
        setLoadingAction("generate")

        try {
            const res = await tripsApi.generateAIReview(tripId, day, userId, lang)
            if (res && res.review) {
                setOptimisticState({ key: scopeKey, value: res.review })
            }
            toast.success(zh ? `Day ${day} AI 審核完成!` : `Day ${day} AI review complete!`)
            await onUpdate(res?.review)
        } catch (error) {
            console.error("AI Review failed:", error)
            toast.error(error instanceof Error ? error.message : (zh ? "AI 審核失敗" : "AI review failed"))
        } finally {
            setIsLoading(false)
            setLoadingAction(null)
            actionLockRef.current = false
        }
    }

    // 清除審核報告
    const handleClear = async () => {
        if (readOnly || isLoading || actionLockRef.current || !tripId) return

        actionLockRef.current = true
        setIsLoading(true)
        setLoadingAction("clear")

        try {
            await tripsApi.clearAIReview(tripId, day, userId)
            setOptimisticState({ key: scopeKey, value: "" })
            toast.success(zh ? "已清除審核報告" : "Review cleared")
            await onUpdate("")
        } catch (error) {
            console.error("Clear failed:", error)
            toast.error(zh ? "清除失敗" : "Clear failed")
        } finally {
            setIsLoading(false)
            setLoadingAction(null)
            actionLockRef.current = false
        }
    }

    // 格式化審核報告 - 識別標題和列表項目 (補齊暗黑模式高對比色票)
    const formatReview = (text: string | null | undefined) => {
        if (!text) return null
        const normalizedText = String(text).replace(/\\n/g, '\n')
        const lines = normalizedText.split('\n')

        return lines.map((line, i) => {
            const trimmed = line.trim()
            if (!trimmed) return <div key={i} className="h-2" />

            // 標題行 (🎯, ✅, ⚠️, 💡 開頭)
            if (/^[🎯✅⚠️💡]/.test(trimmed)) {
                return (
                    <p key={i} className="font-bold text-tabiji-charcoal dark:text-tabiji-paper mt-4 first:mt-0 mb-2">
                        {trimmed}
                    </p>
                )
            }

            // 數字列表 (1. 2. 3. 開頭)
            if (/^\d+\./.test(trimmed)) {
                return (
                    <p key={i} className="pl-4 py-0.5 text-slate-700 dark:text-slate-300">
                        {trimmed}
                    </p>
                )
            }

            // 項目行 (• 開頭)
            if (trimmed.startsWith('•')) {
                return (
                    <p key={i} className="pl-4 py-0.5 text-slate-700 dark:text-slate-300">
                        {trimmed}
                    </p>
                )
            }

            return (
                <p key={i} className="py-0.5 text-slate-700 dark:text-slate-300">
                    {trimmed}
                </p>
            )
        })
    }

    const unifiedCardClass =
        "bg-white/95 dark:bg-[#182320]/90 border border-tabiji-forest/10 dark:border-white/10 rounded-2xl p-4 shadow-[0_2px_12px_rgba(11,48,38,0.05)] dark:shadow-[0_2px_14px_rgba(0,0,0,0.3)]"

    // 無審核報告 - 顯示統一和紙白／深翠黑現代空狀態卡片
    if (!effectiveReview) {
        return (
            <div className={cn(unifiedCardClass, className)}>
                <div className="flex items-center gap-2.5 mb-3.5">
                    <div className="w-8 h-8 rounded-xl bg-emerald-500/12 dark:bg-emerald-400/15 text-emerald-700 dark:text-emerald-300 flex items-center justify-center shrink-0">
                        <Sparkles className="w-4 h-4" />
                    </div>
                    <h3 className="text-sm font-bold text-tabiji-charcoal dark:text-tabiji-paper">
                        {zh ? "AI 深度審核報告" : "AI Review Report"}
                    </h3>
                </div>
                <div className="py-6 px-4 text-center rounded-xl bg-tabiji-paper/45 dark:bg-white/[0.02] border border-dashed border-tabiji-forest/12 dark:border-white/10">
                    <div className="w-11 h-11 rounded-2xl bg-emerald-500/12 dark:bg-emerald-400/15 text-emerald-700 dark:text-emerald-300 flex items-center justify-center mx-auto mb-2.5">
                        <Sparkles className="w-5 h-5" />
                    </div>
                    <p className="text-sm font-semibold text-tabiji-charcoal dark:text-tabiji-paper">
                        {zh ? "尚未生成當日行程審核" : "No AI itinerary review yet"}
                    </p>
                    <p className={cn("text-xs text-slate-500 dark:text-slate-400 mt-1", !readOnly && "mb-4")}>
                        {zh
                            ? "由 AI 從時間節奏、動線順暢與體力負荷五維度剖析當日行程"
                            : "Analyze daily pacing, route efficiency, and fatigue across 5 dimensions"}
                    </p>
                    {!readOnly && (
                        <button
                            type="button"
                            onClick={handleGenerate}
                            disabled={isLoading}
                            className="inline-flex items-center justify-center h-9 px-4 rounded-full text-xs font-semibold bg-tabiji-forest hover:bg-tabiji-forest/90 text-tabiji-paper dark:bg-emerald-600 dark:hover:bg-emerald-500 dark:text-white transition-colors touch-manipulation disabled:opacity-50"
                        >
                            {isLoading && loadingAction === "generate" ? (
                                <>
                                    <Loader2 className="w-4 h-4 mr-1.5 animate-spin" />
                                    {zh ? "AI 正在審核中..." : "AI is reviewing..."}
                                </>
                            ) : (
                                <>
                                    <Sparkles className="w-3.5 h-3.5 mr-1.5" />
                                    {zh ? "生成 AI 深度審核報告" : "Generate AI Review"}
                                </>
                            )}
                        </button>
                    )}
                </div>
            </div>
        )
    }

    // 有審核報告 - 顯示報告 + 操作按鈕 (可收合)
    return (
        <div className={cn(unifiedCardClass, className)}>
            {/* Header - 語意化收合按鈕與同級操作列 */}
            <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="flex-1 min-w-[min(100%,9rem)]">
                    <button
                        type="button"
                        aria-expanded={isExpanded}
                        onClick={() => setIsExpanded((prev) => !prev)}
                        className="w-full flex items-center gap-2.5 text-left cursor-pointer select-none rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tabiji-forest/40 dark:focus-visible:ring-emerald-400/40"
                    >
                        <span className="w-8 h-8 rounded-xl bg-emerald-500/12 dark:bg-emerald-400/15 text-emerald-700 dark:text-emerald-300 flex items-center justify-center shrink-0">
                            <Sparkles className="w-4 h-4" />
                        </span>
                        <span className="text-sm font-bold text-tabiji-charcoal dark:text-tabiji-paper flex items-center gap-1.5 min-w-0 leading-snug wrap-break-word">
                            <span>{zh ? "AI 深度審核報告" : "AI Review Report"}</span>
                            <ChevronDown
                                className={cn(
                                    "w-4 h-4 text-slate-400 dark:text-slate-400 transition-transform duration-200 shrink-0",
                                    isExpanded && "rotate-180"
                                )}
                            />
                        </span>
                    </button>
                </h3>
                {!readOnly && (
                    <div className="flex items-center gap-1 shrink-0 ml-auto">
                        {/* 重新審核 */}
                        <button
                            type="button"
                            className="h-8 w-8 rounded-full flex items-center justify-center bg-tabiji-mist/70 hover:bg-tabiji-mist text-tabiji-charcoal dark:bg-white/8 dark:hover:bg-white/14 dark:text-tabiji-paper transition-colors touch-manipulation disabled:opacity-50"
                            onClick={handleGenerate}
                            disabled={isLoading}
                            aria-label={zh ? "重新審核" : "Re-review"}
                            title={zh ? "重新審核" : "Re-review"}
                        >
                            {isLoading && loadingAction === "generate" ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                                <RefreshCw className="w-3.5 h-3.5" />
                            )}
                        </button>
                        {/* 清除 */}
                        <button
                            type="button"
                            className="h-8 w-8 rounded-full flex items-center justify-center bg-tabiji-mist/70 hover:bg-red-500/12 text-slate-500 hover:text-red-500 dark:bg-white/8 dark:hover:bg-red-500/20 dark:text-slate-300 dark:hover:text-red-400 transition-colors touch-manipulation disabled:opacity-50"
                            onClick={handleClear}
                            disabled={isLoading}
                            aria-label={zh ? "清除審核" : "Clear review"}
                            title={zh ? "清除審核" : "Clear review"}
                        >
                            {isLoading && loadingAction === "clear" ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                                <Trash2 className="w-3.5 h-3.5" />
                            )}
                        </button>
                    </div>
                )}
            </div>

            {/* Content - 可收合 */}
            <div
                className={cn(
                    "overflow-hidden transition-all duration-300 ease-in-out",
                    isExpanded ? "max-h-750 opacity-100 mt-3.5" : "max-h-0 opacity-0 mt-0"
                )}
            >
                {/* 📊 五維量規微型健康指標卡片 */}
                {highlights.dimensions && (
                    <div className="mb-3.5 p-3 bg-tabiji-paper/65 dark:bg-white/[0.04] rounded-xl border border-tabiji-forest/10 dark:border-white/10 space-y-2.5">
                        <div className="flex items-center justify-between text-xs font-semibold text-tabiji-charcoal dark:text-tabiji-paper">
                            <span>{zh ? "五維審核量規指標" : "Health Rubric Metrics"}</span>
                            {highlights.score !== null && (
                                <span className="tabular-nums font-bold text-emerald-700 dark:text-emerald-300">
                                    {zh ? `總評分: ${highlights.score} / 100` : `Score: ${highlights.score} / 100`}
                                </span>
                            )}
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                            {[
                                { label: zh ? "時間節奏" : "Pacing", val: highlights.dimensions.pacing },
                                { label: zh ? "動線順暢" : "Route", val: highlights.dimensions.route },
                                { label: zh ? "停留合理" : "Duration", val: highlights.dimensions.duration },
                                { label: zh ? "體力負荷" : "Fatigue", val: highlights.dimensions.fatigue },
                                { label: zh ? "時段契合" : "Timing", val: highlights.dimensions.timing },
                            ].map((dim) => (
                                <div key={dim.label} className="space-y-0.5">
                                    <div className="flex justify-between text-[10px] text-slate-500 dark:text-slate-400">
                                        <span>{dim.label}</span>
                                        <span className="tabular-nums font-medium text-tabiji-charcoal dark:text-tabiji-paper">{dim.val} / 20</span>
                                    </div>
                                    <div className="w-full h-1.5 bg-tabiji-forest/10 dark:bg-white/10 rounded-full overflow-hidden">
                                        <div
                                            className={cn(
                                                "h-full rounded-full transition-all duration-300",
                                                dim.val >= 17 ? "bg-emerald-500" : dim.val >= 14 ? "bg-amber-500" : "bg-rose-500"
                                            )}
                                            style={{ width: `${Math.max(0, Math.min(100, (dim.val / 20) * 100))}%` }}
                                        />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                <div className="text-sm text-tabiji-charcoal dark:text-tabiji-paper leading-relaxed space-y-1 wrap-break-word [overflow-wrap:anywhere]">
                    {formatReview(cleanText)}
                </div>
            </div>
        </div>
    )
}
