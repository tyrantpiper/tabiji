"use client"

import { useState, useEffect, useCallback } from "react"
import { ChevronLeft, Calendar, ChevronDown } from "lucide-react"
import { motion } from "framer-motion"
import { cn } from "@/lib/utils"
import { TripSwitcher } from "@/components/trip-switcher"
import { ShareButton } from "@/components/itinerary/ShareButton"
import { TripMembersSheet } from "@/components/itinerary/TripMembersSheet"
import { ZenRenew } from "@/components/ui/zen-renew"
import { Trip } from "@/lib/itinerary-types"
import { useLanguage } from "@/lib/LanguageContext"
import { useHaptic } from "@/lib/hooks"
import { useIdleBreathing } from "@/lib/hooks/useIdleBreathing"

interface ItineraryHeaderProps {
    currentTrip?: Trip
    dayNumbers: number[]
    day: number
    setDay: (d: number) => void
    onBack: () => void
    onOpenDatePicker?: () => void
    onDeleteDay: (dayNum: number) => void
    getDateInfo: (dayNum: number) => { date: string; week: string }
    userId: string | null
    onRefresh: () => Promise<void>
    shouldShowDateSkeleton: boolean
    scrollerEl?: HTMLElement | null
}

export function ItineraryHeader({
    currentTrip,
    dayNumbers,
    day,
    setDay,
    onBack,
    onOpenDatePicker,
    onDeleteDay,
    getDateInfo,
    userId,
    onRefresh,
    shouldShowDateSkeleton,
    scrollerEl = null
}: ItineraryHeaderProps) {
    const totalDays = dayNumbers.length
    const { t } = useLanguage()
    const haptic = useHaptic()
    const [isSticky, setIsSticky] = useState(false)

    // 偵測滾動深度以判斷是否進入吸頂狀態 (> 120px)
    const checkSticky = useCallback(() => {
        if (!scrollerEl) {
            setIsSticky(false)
            return
        }
        setIsSticky(scrollerEl.scrollTop > 120)
    }, [scrollerEl])

    useEffect(() => {
        if (!scrollerEl) return
        scrollerEl.addEventListener("scroll", checkSticky, { passive: true })
        const rafId = requestAnimationFrame(checkSticky)
        return () => {
            cancelAnimationFrame(rafId)
            scrollerEl.removeEventListener("scroll", checkSticky)
        }
    }, [scrollerEl, checkSticky])

    // 🌬️ 閒置呼吸降敏狀態機 (僅在吸頂時啟用，閒置 2.5 秒降至 20% 極透態)
    const { isDimmed, handlers: idleHandlers } = useIdleBreathing(scrollerEl, {
        idleTimeoutMs: 2500,
        enabled: isSticky
    })

    // Format date capsule text
    const dateCapsuleText = (() => {
        if (!currentTrip?.start_date) {
            return `${totalDays} ${t('ov_total_days') || '天'}`
        }
        const startStr = currentTrip.start_date.split('T')[0]
        const endStr = currentTrip.end_date ? currentTrip.end_date.split('T')[0] : startStr
        const nights = Math.max(0, totalDays - 1)
        const durationStr = nights === 0 
            ? (t('cal_single_day') || '1 天當日來回') 
            : `${totalDays} 天 ${nights} 晚`
        return `${startStr} - ${endStr} · ${durationStr}`
    })()

    return (
        <>
            {/* 頂部 Hero 資訊與操作區 (隨滾動自然隱藏，釋放視野) */}
            <div className="bg-[#F6F5EE] dark:bg-[#121A18] pt-12 pb-3">
                <div className="px-6 flex flex-col sm:flex-row justify-between items-start sm:items-end mb-1 gap-4 sm:gap-2">
                    <div className="w-full sm:w-auto min-w-0">
                        <button
                            onClick={() => {
                                haptic.selection()
                                onBack()
                            }}
                            className="w-10 h-10 -ml-1 rounded-full flex items-center justify-center bg-stone-100/80 dark:bg-slate-700/80 hover:bg-stone-200/80 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 active:scale-90 transition-all cursor-pointer shadow-2xs mb-2 select-none"
                            aria-label="Back"
                        >
                            <ChevronLeft className="w-5 h-5 -ml-0.5" />
                        </button>
                        <TripSwitcher className="w-full sm:w-60 justify-start px-0 font-bold text-2xl tracking-tight border-none shadow-none bg-transparent text-[#1E2927] dark:text-[#E5EBEA] hover:bg-black/5 dark:hover:bg-white/5 h-auto py-1" />
                        
                        {/* 📅 iOS Date Range Capsule Button */}
                        {onOpenDatePicker && (
                            <div className="mt-1">
                                <button
                                    onClick={onOpenDatePicker}
                                    className="inline-flex items-center gap-1.5 px-3 py-1 bg-slate-100/80 dark:bg-slate-700/60 hover:bg-slate-200/80 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-semibold rounded-full border border-slate-200/80 dark:border-slate-600/60 shadow-xs transition-all active:scale-95 group"
                                    title={t('cal_title') || '調整旅行日期'}
                                >
                                    <Calendar className="w-3.5 h-3.5 text-emerald-500 group-hover:scale-110 transition-transform" />
                                    <span>{dateCapsuleText}</span>
                                    <ChevronDown className="w-3 h-3 opacity-60 ml-0.5" />
                                </button>
                            </div>
                        )}
                    </div>

                    <div className="flex items-center justify-between w-full sm:w-auto sm:gap-4 min-w-0">
                        <div className="flex items-center gap-2">
                            {currentTrip?.public_id && (
                                <ShareButton
                                    publicId={currentTrip.public_id}
                                    tripTitle={currentTrip.title}
                                />
                            )}
                            {currentTrip && (
                                <TripMembersSheet
                                    tripId={currentTrip.id}
                                    members={currentTrip.members || []}
                                    createdBy={currentTrip.created_by || ""}
                                    currentUserId={userId || ""}
                                    onMemberKicked={onRefresh}
                                />
                            )}
                        </div>
                        <ZenRenew onRefresh={onRefresh} successMessage={t('update_success')} errorMessage={t('update_failed')} />
                    </div>
                </div>
            </div>

            {/* 🗓️ 智慧吸頂天數膠囊列 (Sticky Blur: 始終吸附頂部且透出下方時間軸毛玻璃，吸頂閒置時 20% 呼吸極透) */}
            <div
                className={cn(
                    "sticky top-0 z-30 bg-[#F6F5EE]/85 dark:bg-[#121A18]/85 backdrop-blur-md border-b border-[#0B3026]/8 dark:border-white/10 py-2 shadow-2xs transition-all",
                    isDimmed
                        ? "opacity-20 duration-500 ease-in-out hover:opacity-100"
                        : "opacity-100 duration-150 ease-out"
                )}
                {...idleHandlers}
            >
                <div className="flex gap-3 overflow-x-auto px-6 no-scrollbar items-center">
                    {shouldShowDateSkeleton ? (
                        [1, 2, 3].map(i => (
                            <div key={i} className="w-14 h-14 bg-slate-200 dark:bg-slate-700 rounded-lg animate-pulse shrink-0" />
                        ))
                    ) : (
                        <>
                            {/* 🆕 總覽 (Overview) Tab */}
                            <div className="relative flex flex-col items-center">
                                <button
                                    onClick={() => setDay(0)}
                                    className={cn(
                                        "day-btn relative flex flex-col items-center min-w-14 py-2 px-2.5 rounded-lg border transition-colors",
                                        day === 0
                                            ? "text-white bg-[#0B3026] dark:bg-[#164E40] border-[#0B3026] dark:border-[#164E40] shadow-sm"
                                            : "bg-white dark:bg-[#182320] hover:bg-[#EAE8DE]/60 dark:hover:bg-[#1F2C29] text-[#1E2927] dark:text-[#E5EBEA] border-[#0B3026]/10 dark:border-white/10"
                                    )}
                                >
                                    {day === 0 && (
                                        <motion.div
                                            layoutId="day-indicator"
                                            className="absolute inset-0 bg-[#0B3026] dark:bg-[#164E40] rounded-lg -z-10"
                                            transition={{ type: "spring", stiffness: 500, damping: 30 }}
                                        />
                                    )}
                                    <span className="text-[10px] opacity-70">ALL</span>
                                    <span className="font-bold text-xs">{t('ov_overview_tab') || '總覽'}</span>
                                </button>
                            </div>

                            {dayNumbers.map((d) => {
                                const { date, week } = getDateInfo(d)
                                return (
                                    <div key={d} className="relative flex flex-col items-center">
                                        <button
                                            onClick={() => setDay(d)}
                                            className={cn(
                                                "day-btn relative flex flex-col items-center min-w-14 py-2 rounded-lg border",
                                                day === d
                                                    ? "text-white bg-[#0B3026] dark:bg-[#164E40] border-[#0B3026] dark:border-[#164E40] shadow-sm"
                                                    : "bg-white dark:bg-[#182320] hover:bg-[#EAE8DE]/60 dark:hover:bg-[#1F2C29] text-[#1E2927] dark:text-[#E5EBEA] border-[#0B3026]/10 dark:border-white/10"
                                            )}
                                        >
                                            {day === d && (
                                                <motion.div
                                                    layoutId="day-indicator"
                                                    className="absolute inset-0 bg-[#0B3026] dark:bg-[#164E40] rounded-lg -z-10"
                                                    transition={{ type: "spring", stiffness: 500, damping: 30 }}
                                                />
                                            )}
                                            <span className="text-[10px] opacity-70">{week}</span>
                                            <span className="font-bold">{date}</span>
                                        </button>
                                        {totalDays > 1 && day === d && (
                                            <button
                                                onClick={(e) => { e.stopPropagation(); onDeleteDay(d) }}
                                                className="mt-1.5 px-2.5 py-1 text-[10px] font-medium 
                                                        text-red-400 bg-red-50/80 backdrop-blur-sm
                                                        border border-red-200/60 rounded-full shadow-sm 
                                                        active:scale-95 active:bg-red-100
                                                        transition-transform duration-100"
                                            >
                                                {t('iv_delete_this_day')}
                                            </button>
                                        )}
                                    </div>
                                )
                            })}
                        </>
                    )}
                </div>
            </div>
        </>
    )
}
