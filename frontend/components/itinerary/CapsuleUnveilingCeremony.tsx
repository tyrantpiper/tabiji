"use client"

import React, { useState, useEffect, useSyncExternalStore } from "react"
import { createPortal } from "react-dom"
import { motion, AnimatePresence } from "framer-motion"
import { X, Sparkles, ChevronLeft, ChevronRight, RotateCw, Image as ImageIcon } from "lucide-react"
import Image from "next/image"
import { useLanguage } from "@/lib/LanguageContext"
import { useHaptic } from "@/lib/hooks"
import { TripCapsuleEntry } from "@/lib/itinerary-types"

const emptySubscribe = () => () => {}
const getClientSnapshot = () => true
const getServerSnapshot = () => false

interface CapsuleUnveilingCeremonyProps {
    isOpen: boolean
    onClose: () => void
    entries: TripCapsuleEntry[]
    totalDays: number
    tripTitle?: string
    initialDay?: number
}

export function CapsuleUnveilingCeremony({
    isOpen,
    onClose,
    entries,
    totalDays,
    tripTitle,
    initialDay = 1,
}: CapsuleUnveilingCeremonyProps) {
    const { lang } = useLanguage()
    const zh = lang === "zh"
    const haptic = useHaptic()

    // 🛡️ SSR 安全守衛 (使用 useSyncExternalStore 確保無 cascading render 且客戶端安全執行 createPortal)
    const isClient = useSyncExternalStore(emptySubscribe, getClientSnapshot, getServerSnapshot)

    // 🛡️ Initial Day Clamp Guard: 確保初始天數落於合法區間 [1, totalDays] 或 0 (Finale)
    const normalizedInitialDay = initialDay >= 0 && initialDay <= totalDays ? initialDay : (totalDays > 0 ? 1 : 0)
    const [activeDay, setActiveDay] = useState<number>(normalizedInitialDay)
    const [currentTravelerIdx, setCurrentTravelerIdx] = useState<number>(0)
    const [flippedMap, setFlippedMap] = useState<Record<string, boolean>>({})

    // 🛡️ Body Scroll Lock & ESC 鍵安全退出守衛
    useEffect(() => {
        if (!isOpen) return
        const originalOverflow = document.body.style.overflow
        document.body.style.overflow = "hidden"

        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                onClose()
            }
        }
        window.addEventListener("keydown", handleKeyDown)

        return () => {
            document.body.style.overflow = originalOverflow
            window.removeEventListener("keydown", handleKeyDown)
        }
    }, [isOpen, onClose])

    if (!isClient) return null

    // 依天數分組條目
    const currentDayEntries = entries.filter((e) => e.day_number === activeDay)
    // 🛡️ Stale Index Clamp Guard: 確保旅伴索引絕不越界
    const safeTravelerIdx = Math.min(currentTravelerIdx, Math.max(0, currentDayEntries.length - 1))
    const currentEntry: TripCapsuleEntry | undefined = currentDayEntries[safeTravelerIdx]

    const isCurrentFlipped = currentEntry ? !!flippedMap[currentEntry.id] : false

    const handleFlip = () => {
        if (!currentEntry) return
        haptic.selection()
        setFlippedMap((prev) => ({
            ...prev,
            [currentEntry.id]: !prev[currentEntry.id],
        }))
    }

    const handleNextTraveler = () => {
        if (safeTravelerIdx < currentDayEntries.length - 1) {
            haptic.selection()
            setCurrentTravelerIdx(safeTravelerIdx + 1)
        }
    }

    const handlePrevTraveler = () => {
        if (safeTravelerIdx > 0) {
            haptic.selection()
            setCurrentTravelerIdx(safeTravelerIdx - 1)
        }
    }

    return createPortal(
        <AnimatePresence>
            {isOpen && (
                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.25 }}
                    className="fixed inset-0 z-120 h-dvh max-h-dvh bg-[#0A1612]/98 backdrop-blur-2xl flex flex-col justify-between text-[#E5EBEA] overflow-hidden select-none"
                >
                {/* 🌌 深松星夜環境暖光 (Ambient Twilight & Hearth Glow) */}
                <div className="absolute inset-0 pointer-events-none overflow-hidden -z-10">
                    <div className="absolute -top-32 left-1/2 -translate-x-1/2 w-150 h-90 bg-[radial-gradient(ellipse_at_top,var(--tw-gradient-stops))] from-[#E56E25]/20 via-[#0B3026]/15 to-transparent blur-3xl opacity-80" />
                    <div className="absolute -bottom-32 left-1/2 -translate-x-1/2 w-130 h-80 bg-[radial-gradient(ellipse_at_bottom,var(--tw-gradient-stops))] from-[#F0803C]/15 via-transparent to-transparent blur-3xl opacity-70" />
                </div>

                {/* 頂部導航與標題列 */}
                <div className="px-5 pt-12 pb-3.5 flex items-center justify-between border-b border-white/10 bg-[#0A1612]/60 backdrop-blur-md shrink-0">
                    <div className="flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-full bg-linear-to-tr from-[#E56E25] to-[#F0803C] flex items-center justify-center text-white shadow-lg shadow-[#E56E25]/30">
                            <Sparkles className="w-4 h-4" />
                        </div>
                        <div>
                            <h2 className="text-sm font-bold text-white tracking-wide">
                                {zh ? "旅伴時光膠囊破印盛典" : "Capsule Unveiling Ceremony"}
                            </h2>
                            <p className="text-[11px] text-[#F0803C] font-medium">
                                {tripTitle || (zh ? "精彩旅程回顧" : "Trip Memories")}
                            </p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="w-8 h-8 rounded-full bg-white/10 hover:bg-white/20 flex items-center justify-center text-[#A2B1AE] hover:text-white transition-colors"
                        aria-label="Close"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>

                {/* 天數切換膠囊 (Day 1..N + Finale) */}
                <div className="py-2.5 px-4 overflow-x-auto flex items-center gap-2 border-b border-white/5 scrollbar-none shrink-0 bg-[#0A1612]/40">
                    {Array.from({ length: totalDays }, (_, i) => i + 1).map((d) => (
                        <button
                            key={d}
                            onClick={() => {
                                setActiveDay(d)
                                setCurrentTravelerIdx(0)
                                haptic.selection()
                            }}
                            className={`px-3.5 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-all ${
                                activeDay === d
                                    ? "bg-linear-to-r from-[#E56E25] to-[#F0803C] text-white shadow-md shadow-[#E56E25]/30 scale-105 border border-[#F0803C]/40"
                                    : "bg-[#14231E]/80 text-[#A2B1AE] hover:bg-[#1C2F29] hover:text-white border border-white/5"
                            }`}
                        >
                            Day {d}
                        </button>
                    ))}
                    <button
                        onClick={() => {
                            setActiveDay(0)
                            setCurrentTravelerIdx(0)
                            haptic.selection()
                        }}
                        className={`px-3.5 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-all ${
                            activeDay === 0
                                ? "bg-linear-to-r from-[#E56E25] to-[#F0803C] text-white shadow-md shadow-[#E56E25]/30 scale-105 border border-[#F0803C]/40"
                                : "bg-[#14231E]/80 text-[#A2B1AE] hover:bg-[#1C2F29] hover:text-white border border-white/5"
                        }`}
                    >
                        {zh ? "終局總結" : "Finale"}
                    </button>
                </div>

                {/* 中央 3D 翻轉卡牌區域 (min-h-0 + overflow-y-auto 垂直自適應防截斷) */}
                <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain flex flex-col items-center justify-start sm:justify-center px-4 py-2 scrollbar-none">
                    {currentEntry ? (
                        <div className="relative w-full max-w-72 sm:max-w-82 max-h-[40vh] sm:max-h-[44vh] aspect-[3/4.2] flex items-center justify-center shrink-0">
                            <motion.div
                                onClick={handleFlip}
                                animate={{ rotateY: isCurrentFlipped ? 180 : 0 }}
                                transition={{ duration: 0.6, type: "spring", stiffness: 260, damping: 25 }}
                                className="w-full h-full relative cursor-pointer preserve-3d"
                                style={{ transformStyle: "preserve-3d" }}
                            >
                                {/* ──────── 正面: 拍立得照片卡 (Front Face) ──────── */}
                                <div
                                    className="absolute inset-0 w-full h-full bg-white text-[#1E2927] rounded-2xl p-3 sm:p-4 shadow-2xl shadow-black/40 flex flex-col justify-between backface-hidden border border-white/30"
                                    style={{ backfaceVisibility: "hidden" }}
                                >
                                    {/* 拍立得相框 (flex-1 min-h-0 自適應彈性收縮，不擠壓文字底籤) */}
                                    <div className="relative w-full flex-1 min-h-0 max-h-[58%] aspect-square mx-auto bg-[#F6F5EE] rounded-lg overflow-hidden border border-[#0B3026]/10 shadow-inner">
                                        {currentEntry.photo_url ? (
                                            <Image
                                                src={currentEntry.photo_url}
                                                alt="Polaroid Memory"
                                                fill
                                                className="object-cover"
                                                unoptimized
                                            />
                                        ) : (
                                            <div className="w-full h-full flex flex-col items-center justify-center gap-1.5 text-[#5C6B68]/60 bg-[#F6F5EE]">
                                                <ImageIcon className="w-8 h-8 opacity-30 text-[#0B3026]" />
                                                <span className="text-[11px] font-medium text-[#5C6B68]">
                                                    {zh ? "這一天未上傳相片" : "No photo attached"}
                                                </span>
                                            </div>
                                        )}
                                    </div>

                                    {/* 拍立得文字底籤 */}
                                    <div className="mt-2 shrink-0 flex items-center justify-between">
                                        <div>
                                            <div className="flex items-center gap-1.5">
                                                {currentEntry.author_avatar ? (
                                                    <Image
                                                        src={currentEntry.author_avatar}
                                                        alt={currentEntry.author_name || "Author"}
                                                        width={20}
                                                        height={20}
                                                        className="w-5 h-5 rounded-full object-cover border border-[#0B3026]/20"
                                                        unoptimized
                                                    />
                                                ) : null}
                                                <span className="text-xs font-bold text-[#1E2927] tracking-tight">
                                                    {currentEntry.author_name || (zh ? "旅伴" : "Traveler")}
                                                </span>
                                                <span className="text-base">{currentEntry.mood_emoji || "✨"}</span>
                                            </div>
                                            <p className="text-[10px] text-[#5C6B68] mt-0.5">
                                                {activeDay === 0 ? "Trip Finale" : `Day ${activeDay} Memoir`}
                                            </p>
                                        </div>
                                        <div className="flex items-center gap-1 text-[11px] font-semibold text-[#E56E25] bg-[#E56E25]/10 px-2 py-0.5 rounded-full border border-[#E56E25]/30">
                                            <RotateCw className="w-3 h-3" />
                                            <span>{zh ? "點擊翻面" : "Flip"}</span>
                                        </div>
                                    </div>
                                </div>

                                {/* ──────── 背面: 手寫真心話告白 (Back Face - 暖陽復古和紙箋) ──────── */}
                                <div
                                    className="absolute inset-0 w-full h-full bg-[#FAF6EB] text-[#2C221E] rounded-2xl p-4 sm:p-5 shadow-2xl shadow-black/50 border-2 border-[#E56E25]/35 flex flex-col justify-between rotate-y-180 backface-hidden ring-1 ring-[#0B3026]/10"
                                    style={{
                                        transform: "rotateY(180deg)",
                                        backfaceVisibility: "hidden",
                                    }}
                                >
                                    <div className="flex-1 min-h-0 flex flex-col">
                                        <div className="flex items-center justify-between border-b border-[#0B3026]/10 pb-2 mb-2 shrink-0">
                                            <div className="flex items-center gap-2">
                                                {currentEntry.author_avatar ? (
                                                    <Image
                                                        src={currentEntry.author_avatar}
                                                        alt={currentEntry.author_name || "Author"}
                                                        width={20}
                                                        height={20}
                                                        className="w-5 h-5 rounded-full object-cover border border-[#E56E25]/30"
                                                        unoptimized
                                                    />
                                                ) : null}
                                                <span className="text-lg leading-none">{currentEntry.mood_emoji || "✨"}</span>
                                                <span className="text-xs font-bold text-[#1E2927]">
                                                    {currentEntry.author_name || (zh ? "旅伴的真心話" : "Traveler's note")}
                                                </span>
                                            </div>
                                            <span className="text-[10px] font-mono font-bold text-[#E56E25] bg-[#E56E25]/10 px-2 py-0.5 rounded-full border border-[#E56E25]/20">
                                                {activeDay === 0 ? "Finale" : `Day ${activeDay}`}
                                            </span>
                                        </div>

                                        {/* 真心話內容 (長文支援平滑滾動，零溢出) */}
                                        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain pr-1 scrollbar-none">
                                            <p className="text-xs sm:text-sm text-[#2C221E] leading-relaxed font-serif whitespace-pre-wrap">
                                                {currentEntry.content || (zh ? "（無文字心得）" : "(No text)")}
                                            </p>
                                        </div>
                                    </div>

                                    <div className="pt-2 border-t border-[#0B3026]/10 shrink-0 flex items-center justify-between text-[10px] text-[#5C6B68]">
                                        <span className="tracking-wide">Tabidachi Time Capsule</span>
                                        <div className="flex items-center gap-1 font-semibold text-[#E56E25]">
                                            <RotateCw className="w-3 h-3" />
                                            <span>{zh ? "翻回正面" : "Flip back"}</span>
                                        </div>
                                    </div>
                                </div>
                            </motion.div>
                        </div>
                    ) : (
                        <div className="text-center p-8 bg-[#14231E]/60 rounded-3xl border border-white/10 max-w-xs shadow-xl shrink-0">
                            <span className="text-4xl block mb-2 opacity-50">📭</span>
                            <p className="text-xs font-semibold text-[#A2B1AE]">
                                {zh ? "這一天尚無旅伴封存的心得" : "No capsule entries for this day"}
                            </p>
                        </div>
                    )}

                    {/* 👥 旅伴頭像/名稱快速切換 Pills (多旅伴直覺導航) */}
                    {currentDayEntries.length > 1 && (
                        <div className="flex items-center gap-2 mt-2.5 overflow-x-auto max-w-full px-2 scrollbar-none shrink-0">
                            {currentDayEntries.map((entry, idx) => (
                                <button
                                    key={entry.id}
                                    onClick={() => {
                                        haptic.selection()
                                        setCurrentTravelerIdx(idx)
                                    }}
                                    className={`px-3 py-1 rounded-full text-xs font-medium flex items-center gap-1.5 transition-all ${
                                        idx === safeTravelerIdx
                                            ? "bg-linear-to-r from-[#E56E25] to-[#F0803C] text-white shadow-md shadow-[#E56E25]/30 scale-105 border border-[#F0803C]/40"
                                            : "bg-[#14231E]/80 text-[#A2B1AE] hover:bg-[#1C2F29] hover:text-white border border-white/5"
                                    }`}
                                >
                                    <span>{entry.mood_emoji || "✨"}</span>
                                    <span className="max-w-30 truncate">{entry.author_name || (zh ? `旅伴 ${idx + 1}` : `Traveler ${idx + 1}`)}</span>
                                </button>
                            ))}
                        </div>
                    )}

                    {/* 旅伴切換箭頭 (當該天有多位旅伴時) */}
                    {currentDayEntries.length > 1 && (
                        <div className="flex items-center gap-4 mt-2 shrink-0">
                            <button
                                onClick={handlePrevTraveler}
                                disabled={safeTravelerIdx === 0}
                                className="p-2 rounded-full bg-white/10 hover:bg-white/20 disabled:opacity-30 disabled:pointer-events-none transition-all"
                            >
                                <ChevronLeft className="w-4 h-4 text-white" />
                            </button>
                            <span className="text-xs font-mono text-[#A2B1AE]">
                                {safeTravelerIdx + 1} / {currentDayEntries.length}
                            </span>
                            <button
                                onClick={handleNextTraveler}
                                disabled={safeTravelerIdx === currentDayEntries.length - 1}
                                className="p-2 rounded-full bg-white/10 hover:bg-white/20 disabled:opacity-30 disabled:pointer-events-none transition-all"
                            >
                                <ChevronRight className="w-4 h-4 text-white" />
                            </button>
                        </div>
                    )}
                </div>

                {/* 底部導覽小提示 (加入 iOS Home Indicator 安全區留白) */}
                <div className="py-2.5 px-4 pb-[max(env(safe-area-inset-bottom,10px),10px)] border-t border-white/10 text-center text-[11px] text-[#A2B1AE] bg-[#0A1612]/80 backdrop-blur-md shrink-0">
                    {zh
                        ? "💡 點擊卡牌可進行 3D 翻轉；滑動上方天數可依日回顧整趟旅行回憶"
                        : "💡 Tap card to flip 3D front/back; switch tabs to browse all trip days."}
                </div>
            </motion.div>
        )}
    </AnimatePresence>,
    document.body
)
}
