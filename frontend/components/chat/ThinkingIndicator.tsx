"use client"

import { Loader2, Globe } from "lucide-react"
import { cn } from "@/lib/utils"
import { useLanguage } from "@/lib/LanguageContext"

interface ThinkingIndicatorProps {
    phase: "thinking" | "searching"
    isExpanded?: boolean
    onToggle?: () => void
}

/**
 * 🧠 脈衝手風琴 (Pulse Accordion)
 * 
 * 視覺化 AI 處理狀態：
 * - thinking: 紫色脈衝 - AI 正在深度規劃
 * - searching: 藍色掃描 - 正在連網驗證
 */
export default function ThinkingIndicator({
    phase,
    isExpanded = false,
    onToggle
}: ThinkingIndicatorProps) {
    const isThinking = phase === "thinking"
    const { lang } = useLanguage()
    const zh = lang === 'zh'

    return (
        <div
            className={cn(
                "flex items-center gap-3 p-3 rounded-2xl rounded-tl-none border shadow-xs cursor-pointer transition-all",
                isThinking
                    ? "bg-tabiji-mist/60 dark:bg-white/5 border-tabiji-forest/15 dark:border-white/10 text-tabiji-forest dark:text-tabiji-paper"
                    : "bg-tabiji-mist/40 dark:bg-white/5 border-tabiji-forest/15 dark:border-white/10 text-tabiji-forest dark:text-emerald-400"
            )}
            onClick={onToggle}
        >
            {/* Icon with pulse animation */}
            <div className={cn(
                "relative flex items-center justify-center w-8 h-8 rounded-full",
                isThinking ? "bg-tabiji-forest/10 dark:bg-white/10" : "bg-emerald-500/10 dark:bg-emerald-500/20"
            )}>
                {/* Pulse ring */}
                <div className={cn(
                    "absolute inset-0 rounded-full animate-ping opacity-30",
                    isThinking ? "bg-tabiji-forest/40 dark:bg-white/30" : "bg-emerald-500/40"
                )} />

                {/* Icon */}
                {isThinking ? (
                    <Loader2 className="w-4 h-4 animate-spin text-tabiji-forest dark:text-tabiji-paper" />
                ) : (
                    <Globe className="w-4 h-4 animate-pulse text-emerald-600 dark:text-emerald-400" />
                )}
            </div>

            {/* Status text */}
            <div className="flex-1">
                <p className={cn(
                    "text-sm font-medium",
                    isThinking ? "text-tabiji-charcoal dark:text-tabiji-paper" : "text-tabiji-forest dark:text-emerald-400"
                )}>
                    {isThinking
                        ? (zh ? "🧠 AI 正在進行深度規劃..." : "🧠 AI is planning...")
                        : (zh ? "🌏 正在連網查證即時旅遊資訊..." : "🌏 Verifying real-time travel info online...")
                    }
                </p>

                {/* Expanded details */}
                {isExpanded && (
                    <p className={cn(
                        "text-xs mt-1 opacity-70",
                        isThinking ? "text-tabiji-slate dark:text-tabiji-paper/70" : "text-emerald-600 dark:text-emerald-400"
                    )}>
                        {isThinking
                            ? (zh ? "AI 隨行旅伴正在縝密推理行程..." : "AI Companion is carefully planning your trip...")
                            : (zh ? "連網即時查證官方最新資訊..." : "Verifying real-time information online...")
                        }
                    </p>
                )}
            </div>

            {/* Expand hint */}
            <span className="text-xs opacity-50">
                {isExpanded ? "▲" : "▼"}
            </span>
        </div>
    )
}
