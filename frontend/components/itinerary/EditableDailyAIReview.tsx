"use client"

import { useState, useMemo } from "react"
import { ChevronDown, Loader2, RefreshCw, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
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
    onUpdate: (newReview?: string) => Promise<void> | void  // 刷新行程資料
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
    onUpdate
}: EditableDailyAIReviewProps) {
    const [isLoading, setIsLoading] = useState(false)
    const { lang } = useLanguage()
    const zh = lang === 'zh'
    const [loadingAction, setLoadingAction] = useState<"generate" | "clear" | null>(null)
    const [isExpanded, setIsExpanded] = useState(true)  // 預設展開以利抽屜內直接閱讀

    // 🚀 樂觀即時狀態 (Optimistic Instant State: 零延遲立即反映)
    const [optimisticReview, setOptimisticReview] = useState<string | null>(null)

    const effectiveReview = optimisticReview !== null ? optimisticReview : review

    const highlights = useMemo(() => extractAIReviewHighlights(effectiveReview), [effectiveReview])
    const cleanText = highlights.cleanReviewText || effectiveReview

    // 生成/重新生成 AI 審核
    const handleGenerate = async () => {
        if (isLoading || !tripId) return

        setIsLoading(true)
        setLoadingAction("generate")

        try {
            const res = await tripsApi.generateAIReview(tripId, day, userId)
            if (res && res.review) {
                setOptimisticReview(res.review)
            }
            toast.success(zh ? `Day ${day} AI 審核完成!` : `Day ${day} AI review complete!`)
            await onUpdate(res?.review)
        } catch (error) {
            console.error("AI Review failed:", error)
            toast.error(error instanceof Error ? error.message : (zh ? "AI 審核失敗" : "AI review failed"))
        } finally {
            setIsLoading(false)
            setLoadingAction(null)
        }
    }

    // 清除審核報告
    const handleClear = async () => {
        if (isLoading || !tripId) return

        setIsLoading(true)
        setLoadingAction("clear")

        try {
            await tripsApi.clearAIReview(tripId, day, userId)
            setOptimisticReview("")
            toast.success(zh ? "已清除審核報告" : "Review cleared")
            await onUpdate("")
        } catch (error) {
            console.error("Clear failed:", error)
            toast.error(zh ? "清除失敗" : "Clear failed")
        } finally {
            setIsLoading(false)
            setLoadingAction(null)
        }
    }

    // 格式化審核報告 - 識別標題和列表項目
    const formatReview = (text: string | null | undefined) => {
        if (!text) return null
        // 處理可能的 literal \n 字串
        const normalizedText = String(text).replace(/\\n/g, '\n')
        const lines = normalizedText.split('\n')

        return lines.map((line, i) => {
            const trimmed = line.trim()
            if (!trimmed) return <div key={i} className="h-2" />  // 空行增加間距

            // 標題行 (🎯, ✅, ⚠️, 💡 開頭)
            if (/^[🎯✅⚠️💡]/.test(trimmed)) {
                return (
                    <p key={i} className="font-bold text-indigo-900 mt-4 first:mt-0 mb-2">
                        {trimmed}
                    </p>
                )
            }

            // 數字列表 (1. 2. 3. 開頭)
            if (/^\d+\./.test(trimmed)) {
                return (
                    <p key={i} className="pl-4 py-0.5 text-indigo-700">
                        {trimmed}
                    </p>
                )
            }

            // 項目行 (• 開頭)
            if (trimmed.startsWith('•')) {
                return (
                    <p key={i} className="pl-4 py-0.5 text-indigo-700">
                        {trimmed}
                    </p>
                )
            }

            return <p key={i} className="py-0.5">{trimmed}</p>
        })
    }

    // 無審核報告 - 顯示生成按鈕
    if (!effectiveReview) {
        return (
            <div className="mx-6 mt-4">
                <Button
                    variant="outline"
                    className={cn(
                        "w-full py-6 border-dashed border-2 border-indigo-300",
                        "bg-linear-to-br from-indigo-50/50 to-purple-50/50",
                        "hover:border-indigo-400 hover:bg-indigo-50",
                        "text-indigo-600 font-medium",
                        "touch-manipulation"
                    )}
                    onClick={handleGenerate}
                    disabled={isLoading}
                >
                    {isLoading && loadingAction === "generate" ? (
                        <>
                            <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                            AI 正在審核中...
                        </>
                    ) : (
                        <>
                            <span className="text-xl mr-2">🕵️</span>
                            {zh ? '生成 AI 深度審核報告' : 'Generate AI Review'}
                        </>
                    )}
                </Button>
            </div>
        )
    }

    // 有審核報告 - 顯示報告 + 操作按鈕 (可收合)
    return (
        <div className="mx-6 mt-4 p-5 bg-linear-to-br from-indigo-50 to-purple-50 border border-indigo-200 rounded-2xl shadow-sm">
            {/* Header - 點擊展開/收合 */}
            <div
                className="flex items-center justify-between cursor-pointer select-none"
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <h3 className="text-base font-bold text-indigo-900 flex items-center gap-2">
                    <span className="text-lg">🕵️</span> {zh ? 'AI 深度審核報告' : 'AI Review Report'}
                    <ChevronDown
                        className={cn(
                            "w-4 h-4 text-indigo-500 transition-transform duration-200",
                            isExpanded && "rotate-180"
                        )}
                    />
                </h3>
                <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                    {/* 重新審核 */}
                    <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0 text-indigo-600 hover:bg-indigo-100 touch-manipulation"
                        onClick={handleGenerate}
                        disabled={isLoading}
                        title={zh ? "重新審核" : "Re-review"}
                    >
                        {isLoading && loadingAction === "generate" ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                            <RefreshCw className="w-4 h-4" />
                        )}
                    </Button>
                    {/* 清除 */}
                    <Button
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0 text-red-500 hover:bg-red-100 touch-manipulation"
                        onClick={handleClear}
                        disabled={isLoading}
                        title={zh ? "清除審核" : "Clear review"}
                    >
                        {isLoading && loadingAction === "clear" ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                            <Trash2 className="w-4 h-4" />
                        )}
                    </Button>
                </div>
            </div>

            {/* Content - 可收合 */}
            <div
                className={cn(
                    "overflow-hidden transition-all duration-300 ease-in-out",
                    isExpanded ? "max-h-750 opacity-100 mt-3" : "max-h-0 opacity-0 mt-0"
                )}
            >
                {/* 📊 五維量規微型健康指標卡片 */}
                {highlights.dimensions && (
                    <div className="mb-3.5 p-3 bg-white/80 dark:bg-card/80 backdrop-blur rounded-xl border border-indigo-100 dark:border-indigo-950/40 space-y-2.5">
                        <div className="flex items-center justify-between text-xs font-semibold text-indigo-950 dark:text-indigo-200">
                            <span>{zh ? "五維審核量規指標" : "Health Rubric Metrics"}</span>
                            {highlights.score !== null && (
                                <span className="tabular-nums font-bold text-indigo-600 dark:text-indigo-400">
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
                                    <div className="flex justify-between text-[10px] text-muted-foreground">
                                        <span>{dim.label}</span>
                                        <span className="tabular-nums font-medium text-foreground">{dim.val} / 20</span>
                                    </div>
                                    <div className="w-full h-1.5 bg-indigo-100 dark:bg-zinc-800 rounded-full overflow-hidden">
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

                <div className="text-sm text-indigo-800 leading-relaxed space-y-1">
                    {formatReview(cleanText)}
                </div>
            </div>
        </div>
    )
}
