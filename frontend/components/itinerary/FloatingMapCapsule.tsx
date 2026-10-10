"use client"

import { useEffect, useState, useCallback } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Map, ArrowUp } from "lucide-react"
import { useLanguage } from "@/lib/LanguageContext"
import { useHaptic } from "@/lib/hooks"
import { useIdleBreathing } from "@/lib/hooks/useIdleBreathing"
import { cn } from "@/lib/utils"

interface FloatingMapCapsuleProps {
    scrollerEl: HTMLElement | null
    activityCount: number
}

export function FloatingMapCapsule({ scrollerEl, activityCount }: FloatingMapCapsuleProps) {
    const { lang } = useLanguage()
    const zh = lang === 'zh'
    const haptic = useHaptic()
    const [isVisible, setIsVisible] = useState(false)
    const [isAtMap, setIsAtMap] = useState(false)

    // 🌬️ 閒置呼吸降敏狀態機 (2.5 秒無操作自動進入 20% 極透態)
    const { isDimmed, handlers: idleHandlers } = useIdleBreathing(scrollerEl, {
        idleTimeoutMs: 2500,
        enabled: isVisible
    })

    const checkScrollState = useCallback(() => {
        if (!scrollerEl) return
        const scrollTop = scrollerEl.scrollTop
        const mapEl = document.getElementById("day-route-map-container")

        if (!mapEl) {
            setIsVisible(false)
            return
        }

        // 滾動超過 200px 且至少有 1 個行程時浮現
        const shouldShow = scrollTop > 200 && activityCount > 0
        setIsVisible(shouldShow)

        if (shouldShow) {
            const scrollerRect = scrollerEl.getBoundingClientRect()
            const mapRect = mapEl.getBoundingClientRect()
            // 當地圖頂部已進入滾動可視區中段（相對於視窗 < 300px）視為已到達地圖
            const atMapNow = mapRect.top - scrollerRect.top < 350
            setIsAtMap(atMapNow)
        }
    }, [scrollerEl, activityCount])

    useEffect(() => {
        if (!scrollerEl) return
        scrollerEl.addEventListener("scroll", checkScrollState, { passive: true })
        const rafId = requestAnimationFrame(checkScrollState)
        return () => {
            cancelAnimationFrame(rafId)
            scrollerEl.removeEventListener("scroll", checkScrollState)
        }
    }, [scrollerEl, checkScrollState])

    const handleCapsuleClick = () => {
        haptic.selection()
        if (!scrollerEl) return
        const mapEl = document.getElementById("day-route-map-container")

        if (isAtMap) {
            // 已在地圖 ➔ 回滾至時間軸頂部
            scrollerEl.scrollTo({ top: 0, behavior: "smooth" })
        } else if (mapEl) {
            // 在時間軸 ➔ 直達底部地圖
            const scrollerRect = scrollerEl.getBoundingClientRect()
            const mapRect = mapEl.getBoundingClientRect()
            const targetTop = scrollerEl.scrollTop + (mapRect.top - scrollerRect.top) - 60
            scrollerEl.scrollTo({ top: Math.max(0, targetTop), behavior: "smooth" })
        }
    }

    const backText = zh ? "回到行程" : "Back to Top"
    const mapText = zh ? "當日地圖" : "Daily Map"

    return (
        <AnimatePresence>
            {isVisible && (
                <motion.div
                    initial={{ opacity: 0, y: 24, scale: 0.9 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 24, scale: 0.9 }}
                    transition={{ type: "spring", stiffness: 450, damping: 30 }}
                    className={cn(
                        "fixed z-50 transition-all",
                        "bottom-[calc(max(env(safe-area-inset-bottom,16px),16px)+72px)] right-4",
                        "md:bottom-[calc(1.5rem+env(safe-area-inset-bottom,0px))] md:right-6"
                    )}
                    {...idleHandlers}
                >
                    <button
                        type="button"
                        onClick={handleCapsuleClick}
                        className={cn(
                            "inline-flex items-center gap-2 px-3.5 py-2 rounded-full text-xs font-bold select-none cursor-pointer shadow-lg border",
                            "bg-slate-900/90 dark:bg-slate-100/95 text-white dark:text-slate-900 border-white/20 dark:border-slate-800/20 backdrop-blur-md active:scale-95",
                            "transition-all",
                            isDimmed
                                ? "opacity-20 scale-95 duration-500 ease-in-out hover:opacity-100 hover:scale-100"
                                : "opacity-100 scale-100 duration-150 ease-out"
                        )}
                        title={isAtMap ? backText : mapText}
                    >
                        {isAtMap ? (
                            <>
                                <ArrowUp className="w-3.5 h-3.5 animate-bounce" />
                                <span>{backText}</span>
                            </>
                        ) : (
                            <>
                                <Map className="w-3.5 h-3.5 text-emerald-400 dark:text-emerald-600" />
                                <span>{mapText}</span>
                                <span className="px-1.5 py-0.2 text-[10px] rounded-full bg-white/20 dark:bg-slate-900/20 text-white dark:text-slate-900 font-mono">
                                    {activityCount}
                                </span>
                            </>
                        )}
                    </button>
                </motion.div>
            )}
        </AnimatePresence>
    )
}
