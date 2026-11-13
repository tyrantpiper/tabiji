"use client"

import React, { useState, useEffect, useRef } from "react"
import Image from "next/image"
import {
  motion,
  AnimatePresence,
  useReducedMotion,
  useMotionValue,
  useTransform,
  animate,
} from "framer-motion"
import {
  Smartphone,
  Navigation,
  Ticket,
  Coins,
  Plane,
  ShieldCheck,
  Play,
  Pause,
  Users,
  MapPin,
  Sun,
  Plus,
  Calendar,
  Bookmark,
  Receipt,
  Calculator,
  CreditCard,
  PieChart,
  List,
  ChevronLeft,
} from "lucide-react"
import { useOfficialLanguage } from "@/lib/OfficialLanguageContext"
import { TypewriterHeading } from "./TypewriterHeading"

type TheaterMode = "route" | "pass" | "ledger"

interface ModeConfig {
  id: TheaterMode
  label: string
  icon: React.ElementType
}

const MODES: ModeConfig[] = [
  { id: "pass", label: "【斷網抵達】離線秒開", icon: Ticket },
  { id: "route", label: "【地鐵穿行】向量航線", icon: Navigation },
  { id: "ledger", label: "【餐後分帳】精準平攤", icon: Coins },
]

const CYCLE_DURATION_MS = 4000

export function LiveDeviceTheater() {
  const shouldReduceMotion = useReducedMotion()
  const { language, t } = useOfficialLanguage()
  const mock = t.mockDevice
  const [activeMode, setActiveMode] = useState<TheaterMode>("pass")
  const [isPaused, setIsPaused] = useState(false)
  const [pauseReason, setPauseReason] = useState<"hover" | "manual">("hover")
  const progress = useMotionValue(0)
  const progressWidth = useTransform(progress, [0, 1], ["0%", "100%"])
  const controlsRef = useRef<ReturnType<typeof animate> | null>(null)
  const remainingMsRef = useRef<number>(CYCLE_DURATION_MS)
  const startTimeRef = useRef<number | null>(null)

  // Auto-play continuous loop (every 4 seconds with precise wall-clock fallback)
  useEffect(() => {
    if (isPaused) {
      controlsRef.current?.stop()
      if (startTimeRef.current !== null) {
        const elapsed = Date.now() - startTimeRef.current
        remainingMsRef.current = Math.max(0, remainingMsRef.current - elapsed)
        startTimeRef.current = null
      }
      return
    }

    startTimeRef.current = Date.now()
    const currentRemaining = remainingMsRef.current > 0 ? remainingMsRef.current : CYCLE_DURATION_MS
    remainingMsRef.current = currentRemaining

    if (!shouldReduceMotion) {
      const currentVal = progress.get()
      const remainingFraction = Math.max(0, 1 - currentVal)
      const durationSec = remainingFraction <= 0.001
        ? currentRemaining / 1000
        : (remainingFraction * CYCLE_DURATION_MS) / 1000

      if (remainingFraction <= 0.001) {
        progress.set(0)
      }

      controlsRef.current = animate(progress, 1, {
        duration: durationSec,
        ease: "linear",
      })
    }

    const timer = setTimeout(() => {
      progress.set(0)
      remainingMsRef.current = CYCLE_DURATION_MS
      startTimeRef.current = null
      setActiveMode((prev) => {
        const currentIndex = MODES.findIndex((m) => m.id === prev)
        const nextIndex = (currentIndex + 1) % MODES.length
        return MODES[nextIndex].id
      })
    }, currentRemaining)

    return () => {
      clearTimeout(timer)
      controlsRef.current?.stop()
      if (startTimeRef.current !== null) {
        const elapsed = Date.now() - startTimeRef.current
        remainingMsRef.current = Math.max(0, remainingMsRef.current - elapsed)
        startTimeRef.current = null
      }
    }
  }, [activeMode, isPaused, shouldReduceMotion, progress])

  const handleSelectMode = (mode: TheaterMode) => {
    controlsRef.current?.stop()
    progress.set(0)
    remainingMsRef.current = CYCLE_DURATION_MS
    startTimeRef.current = null
    setIsPaused(true)
    setPauseReason("manual")
    setActiveMode(mode)
  }

  const handleTogglePlayPause = () => {
    setIsPaused((prev) => {
      const next = !prev
      if (next) {
        setPauseReason("manual")
        controlsRef.current?.stop()
      }
      return next
    })
  }

  return (
    <section
      id="device-theater"
      className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 sm:py-20 relative overflow-hidden"
      aria-label={language === "en" ? "Tabiji Live Device Theater" : "Tabiji 真機互動劇院"}
    >
      {/* Background Ambient Aurora Halo */}
      <div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-72 sm:w-[500px] h-72 sm:h-[500px] bg-gradient-to-tr from-emerald-500/15 via-teal-500/10 to-amber-500/15 rounded-full blur-3xl pointer-events-none"
        aria-hidden="true"
      />

      {/* Section Header */}
      <div className="text-center max-w-2xl mx-auto mb-8 sm:mb-12">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-800 dark:text-emerald-300 border border-emerald-500/20 mb-3 sm:mb-4">
          <Smartphone className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
          <span>{t.theater.badge}</span>
        </div>
        {/* Contract static binding: text="握在掌心的，是整座城市的從容" */}
        <TypewriterHeading
          text={language === "en" ? t.theater.heading : "握在掌心的，是整座城市的從容"}
          as="h2"
          charDelay={language === "en" ? 65 : 105}
          className="text-2xl sm:text-4xl md:text-5xl font-extrabold tracking-tight text-stone-900 dark:text-stone-50 leading-tight justify-center"
        />
        <p className="mt-3 text-xs sm:text-base text-stone-600 dark:text-stone-300 leading-relaxed font-normal">
          {t.theater.subtitle}
        </p>
      </div>

      {/* Mode Switcher Pills (min 44x44px touch targets) */}
      <div
        className="flex items-center justify-center gap-2 sm:gap-3 mb-4 sm:mb-6 flex-wrap"
        role="tablist"
        aria-label={language === "en" ? "Interactive device screen tabs" : "真機畫面切換"}
      >
        {MODES.map((mode) => {
          const Icon = mode.icon
          const isSelected = activeMode === mode.id
          const modeLabel = t.theater.modes[mode.id] || mode.label
          return (
            <button
              key={mode.id}
              type="button"
              role="tab"
              aria-selected={isSelected}
              onClick={() => handleSelectMode(mode.id)}
              className={`min-h-11 min-w-11 px-4 py-2.5 rounded-full text-xs sm:text-sm font-semibold transition-all duration-160 ease-out active:scale-[0.97] flex items-center gap-2 cursor-pointer border ${
                isSelected
                  ? "bg-[#0B3026] text-white border-[#0B3026] shadow-md dark:bg-emerald-500 dark:text-stone-950 dark:border-emerald-400"
                  : "bg-white/80 dark:bg-stone-900/80 text-stone-600 dark:text-stone-300 border-stone-200 dark:border-stone-800 hover:border-emerald-500/40"
              }`}
            >
              <Icon className="w-4 h-4 text-emerald-400 dark:text-emerald-950" />
              <span>{modeLabel}</span>
            </button>
          )
        })}
      </div>

      {/* 3-Segment Aviation Progress Bar & Loop Controller */}
      <div className="w-full max-w-[310px] sm:max-w-xs mx-auto mb-6 sm:mb-8 flex flex-col gap-1.5">
        <div
          className="w-full flex items-center justify-between gap-2"
          role="region"
          aria-label={language === "en" ? "Live preview carousel progress" : "實機預覽輪播進度條"}
        >
          {MODES.map((mode, index) => {
            const currentIndex = MODES.findIndex((m) => m.id === activeMode)
            const isCurrent = activeMode === mode.id
            const isPast = currentIndex > index
            const modeLabel = t.theater.modes[mode.id] || mode.label
            return (
              <button
                key={mode.id}
                type="button"
                onClick={() => handleSelectMode(mode.id)}
                aria-label={language === "en" ? `Switch to ${modeLabel} demo (Step ${index + 1}/3)` : `切換至 ${modeLabel} 示範 (進度段 ${index + 1}/3)`}
                className="min-h-11 min-w-11 flex-1 flex items-center justify-center p-1 rounded-full cursor-pointer group focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
              >
                <div className="w-full h-1.5 rounded-full bg-stone-300/60 dark:bg-stone-800 overflow-hidden relative">
                  {isPast && (
                    <div className="h-full w-full bg-emerald-500 dark:bg-emerald-400 rounded-full" />
                  )}
                  {isCurrent &&
                    (shouldReduceMotion ? (
                      <div className="h-full w-full bg-emerald-500 dark:bg-emerald-400 rounded-full" />
                    ) : (
                      <motion.div
                        style={{ width: progressWidth }}
                        className="h-full bg-emerald-500 dark:bg-emerald-400 rounded-full"
                      />
                    ))}
                </div>
              </button>
            )
          })}
        </div>

        {/* Status indicator and Play/Pause Toggle */}
        <div className="w-full flex items-center justify-between text-[11px] text-stone-500 dark:text-stone-400 px-1">
          <div className="flex items-center gap-1.5 font-mono">
            <span
              className={`w-2 h-2 rounded-full ${
                isPaused ? "bg-amber-400" : "bg-emerald-400 animate-pulse"
              }`}
            />
            <span>
              {isPaused
                ? pauseReason === "manual"
                  ? t.theater.statusPausedManual
                  : t.theater.statusPausedHover
                : t.theater.statusLive}
            </span>
          </div>

          <button
            type="button"
            onClick={handleTogglePlayPause}
            className="min-h-11 min-w-11 px-2.5 py-1.5 rounded-full inline-flex items-center justify-center gap-1 text-[11px] font-semibold text-stone-600 dark:text-stone-300 hover:text-stone-900 dark:hover:text-white transition-colors cursor-pointer"
            aria-label={isPaused ? (language === "en" ? t.theater.playAria : "繼續自動輪播") : (language === "en" ? t.theater.pauseAria : "暫停自動輪播")}
          >
            {isPaused ? (
              <>
                <Play className="w-3 h-3 fill-current text-emerald-500" />
                <span>{t.theater.play}</span>
              </>
            ) : (
              <>
                <Pause className="w-3 h-3 fill-current text-amber-500" />
                <span>{t.theater.pause}</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Realistic Apple Titanium Smartphone Container */}
      <div
        className="relative w-full max-w-[310px] sm:max-w-xs mx-auto flex items-center justify-center select-none"
        onMouseEnter={() => {
          if (!isPaused) {
            setIsPaused(true)
            setPauseReason("hover")
          }
        }}
        onMouseLeave={() => {
          if (isPaused && pauseReason === "hover") {
            setIsPaused(false)
          }
        }}
        onTouchStart={() => {
          if (!isPaused) {
            setIsPaused(true)
            setPauseReason("hover")
          }
        }}
        onTouchEnd={() => {
          if (isPaused && pauseReason === "hover") {
            setIsPaused(false)
          }
        }}
        onTouchCancel={() => {
          if (isPaused && pauseReason === "hover") {
            setIsPaused(false)
          }
        }}
      >
        {/* Physical Smartphone Buttons (Left: Volume / Mute, Right: Power) */}
        <div className="absolute -left-[5px] top-24 w-[5px] h-9 bg-stone-700 dark:bg-stone-600 rounded-l-sm" aria-hidden="true" />
        <div className="absolute -left-[5px] top-36 w-[5px] h-12 bg-stone-700 dark:bg-stone-600 rounded-l-sm" aria-hidden="true" />
        <div className="absolute -left-[5px] top-52 w-[5px] h-12 bg-stone-700 dark:bg-stone-600 rounded-l-sm" aria-hidden="true" />
        <div className="absolute -right-[5px] top-32 w-[5px] h-16 bg-stone-700 dark:bg-stone-600 rounded-r-sm" aria-hidden="true" />

        {/* Outer Titanium Bezel */}
        <div className="w-full rounded-[44px] sm:rounded-[48px] p-2.5 sm:p-3 bg-gradient-to-b from-[#3a3a3d] via-[#242426] to-[#1a1a1c] border border-white/20 shadow-[0_20px_50px_-10px_rgba(0,0,0,0.5)]">
          {/* Inner Screen Display (19.5:9 phone aspect) */}
          <div
            className="relative w-full aspect-[9/19] rounded-[34px] sm:rounded-[38px] overflow-hidden bg-[#F6F5EE] dark:bg-[#121A18] text-[#1E2927] dark:text-[#E5EBEA] flex flex-col justify-between border border-stone-300/80 dark:border-black shadow-inner"
            aria-hidden="true"
          >
            {/* Top Status Bar & Dynamic Island (z-30) */}
            <div className="w-full flex items-center justify-between text-[11px] font-semibold text-stone-700 dark:text-stone-300 px-4 pt-2 pb-1 shrink-0 z-30 bg-[#F6F5EE]/95 dark:bg-[#121A18]/95 backdrop-blur-md border-b border-stone-200/50 dark:border-white/5">
              <span>9:41</span>
              {/* Dynamic Island Pill */}
              <div className="w-20 h-4 bg-black rounded-full flex items-center justify-end px-2 gap-1 border border-white/10 shadow-sm">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              </div>
              <div className="flex items-center gap-1 text-[10px]">
                <span>5G</span>
                <span className="w-4 h-2 border border-current rounded-[2px] p-[1px] flex items-center">
                  <span className="h-full w-full bg-current rounded-[1px]" />
                </span>
              </div>
            </div>

            {/* App Micro Sub-Header Bar (z-20) */}
            <div className="w-full px-3 py-1.5 flex items-center justify-between shrink-0 z-20 bg-stone-100/80 dark:bg-[#16221F] border-b border-stone-200/60 dark:border-white/5 text-[10px]">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-[#E56E25]" />
                <span className="font-bold tracking-wider text-xs">{mock.subHeader.brand}</span>
              </div>
              <span className="px-2 py-0.5 rounded-full text-[9px] font-semibold bg-emerald-500/15 text-emerald-800 dark:text-emerald-300 border border-emerald-500/20">
                {activeMode === "pass"
                  ? mock.subHeader.taglinePass
                  : activeMode === "route"
                  ? mock.subHeader.taglineRoute
                  : mock.subHeader.taglineLedger}
              </span>
            </div>

            {/* Central Viewport Mask (z-10, aria-hidden for DOM testing isolation) */}
            <div className="flex-1 relative overflow-hidden px-2.5 pt-1.5 pb-1" aria-hidden="true">
              <AnimatePresence initial={false} mode="popLayout">
                <motion.div
                  key={activeMode}
                  initial={{ opacity: 0, x: shouldReduceMotion ? 0 : 28 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: shouldReduceMotion ? 0 : -28 }}
                  transition={{ duration: 0.32, ease: [0.23, 1, 0.32, 1] }}
                  className="h-full w-full flex flex-col"
                >
                  {/* Micro-Scroll Container: auto-scrolls subtly when active, locked when paused or reducedMotion */}
                  <motion.div
                    animate={
                      shouldReduceMotion || isPaused
                        ? { y: 0 }
                        : { y: [0, -22, 0] }
                    }
                    transition={
                      shouldReduceMotion
                        ? { duration: 0 }
                        : isPaused
                          ? { duration: 0.2, ease: "easeOut" }
                          : {
                              duration: 3.8,
                              ease: "easeInOut",
                              times: [0, 0.55, 1],
                              repeat: Infinity,
                              repeatDelay: 0.2,
                            }
                    }
                    className="flex flex-col gap-2 w-full pb-2"
                  >
                    {activeMode === "route" && (
                      <div className="flex flex-col gap-2 w-full">
                        {/* 1. Real PWA Tabiji Home Dashboard Header */}
                        <div className="flex items-center justify-between pb-0.5">
                          <div className="space-y-0.5">
                            <div className="flex items-center gap-1.5">
                              <span className="text-[10px] font-semibold tracking-widest text-[#E56E25] uppercase">
                                {mock.routeMode.brandHeader}
                              </span>
                              <span className="w-1.5 h-1.5 rounded-full bg-[#E56E25] animate-pulse" />
                            </div>
                            <div className="text-sm font-bold tracking-tight text-[#1E2927] dark:text-[#E5EBEA]">
                              Tabiji
                            </div>
                            <div className="text-[9px] text-[#5C6B68] dark:text-[#A2B1AE]">
                              {mock.routeMode.heading}
                            </div>
                          </div>
                          <div className="w-7 h-7 rounded-full flex items-center justify-center bg-white dark:bg-[#182320] border border-black/5 dark:border-white/5 text-amber-600 shadow-2xs">
                            <Bookmark className="w-3.5 h-3.5 fill-amber-500/20 text-amber-600 dark:text-amber-400" />
                          </div>
                        </div>

                        {/* 2. Quick Action Pills (1:1 PWA buttons) */}
                        <div className="grid grid-cols-2 gap-2">
                          <div className="h-8 rounded-xl bg-[#0B3026] text-white flex items-center justify-center gap-1.5 text-[10px] font-medium shadow-xs">
                            <Plus className="w-3 h-3 text-[#E56E25]" />
                            <span>{mock.routeMode.btnNew}</span>
                          </div>
                          <div className="h-8 rounded-xl bg-white dark:bg-[#182320] text-[#1E2927] dark:text-[#E5EBEA] border border-[#0B3026]/10 dark:border-white/10 flex items-center justify-center gap-1.5 text-[10px] font-medium shadow-xs">
                            <Users className="w-3 h-3 text-[#0B3026] dark:text-[#A2B1AE]" />
                            <span>{mock.routeMode.btnJoin}</span>
                          </div>
                        </div>

                        {/* 3. Section Title */}
                        <div className="flex items-center justify-between px-0.5 pt-0.5 text-[10px] font-semibold tracking-wider text-[#1E2927] dark:text-[#E5EBEA] uppercase">
                          <span>{mock.routeMode.myTrips}</span>
                        </div>

                        {/* 4. Real Trip Card 1 (Taipei Explorer) */}
                        <div className="rounded-xl overflow-hidden border border-[#0B3026]/10 dark:border-white/10 shadow-xs bg-white dark:bg-[#182320]">
                          <div className="h-20 bg-[#121A18] relative overflow-hidden">
                            <Image
                              src="/images/tabiji-sunrise-hero.webp"
                              alt="3 Day Taipei Explorer"
                              fill
                              sizes="280px"
                              className="object-cover opacity-90"
                              unoptimized
                            />
                            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/25 to-transparent" />
                            <div className="absolute top-2 left-2 bg-[#E56E25] px-2 py-0.5 rounded-full text-[8px] text-white font-semibold">
                              {mock.routeMode.card1Badge}
                            </div>
                            <div className="absolute bottom-1.5 left-2.5 right-2.5 text-white">
                              <div className="font-bold text-[11px] truncate">{mock.routeMode.card1Title}</div>
                              <div className="text-[9px] opacity-80 flex items-center gap-1 mt-0.5">
                                <Calendar className="w-2.5 h-2.5 text-[#E56E25]" />
                                <span>2026/3/10</span>
                              </div>
                            </div>
                          </div>
                          <div className="px-2.5 py-1.5 flex justify-between items-center text-[9px] border-t border-[#0B3026]/5 dark:border-white/5">
                            <span className="text-[#5C6B68] dark:text-[#A2B1AE] bg-[#EAE8DE]/60 dark:bg-[#1F2C29] px-2 py-0.5 rounded-full">
                              By Tabiji
                            </span>
                            <span className="text-[#E56E25] font-medium">
                              {mock.routeMode.card1Action}
                            </span>
                          </div>
                        </div>

                        {/* 5. Real Trip Card 2 (Tokyo Free Travel) */}
                        <div className="rounded-xl overflow-hidden border border-[#0B3026]/10 dark:border-white/10 shadow-xs bg-white dark:bg-[#182320]">
                          <div className="h-16 bg-[#16221F] relative overflow-hidden">
                            <div className="absolute inset-0 bg-gradient-to-tr from-stone-900 via-stone-800 to-emerald-950 opacity-95" />
                            <div className="absolute top-2 left-2 bg-black/60 px-2 py-0.5 rounded-full text-[8px] text-white/90 font-mono">
                              # 539070
                            </div>
                            <div className="absolute bottom-1.5 left-2.5 right-2.5 text-white">
                              <div className="font-bold text-[11px] truncate">{mock.routeMode.card2Title}</div>
                              <div className="text-[9px] opacity-80 flex items-center gap-1 mt-0.5">
                                <Calendar className="w-2.5 h-2.5 text-[#E56E25]" />
                                <span>2026/10/1</span>
                              </div>
                            </div>
                          </div>
                          <div className="px-2.5 py-1.5 flex justify-between items-center text-[9px] border-t border-[#0B3026]/5 dark:border-white/5">
                            <span className="text-[#5C6B68] dark:text-[#A2B1AE] bg-[#EAE8DE]/60 dark:bg-[#1F2C29] px-2 py-0.5 rounded-full">
                              {mock.routeMode.card2Author}
                            </span>
                            <span className="text-stone-500 dark:text-stone-400 font-medium">
                              📥 PDF
                            </span>
                          </div>
                        </div>
                      </div>
                    )}

                    {activeMode === "pass" && (
                      <div className="flex flex-col gap-2 w-full">
                        {/* Real PWA Itinerary Header Bar */}
                        <div className="flex items-center justify-between text-[10px] pb-0.5 border-b border-stone-200/50 dark:border-white/5">
                          <div className="flex items-center gap-1">
                            <ChevronLeft className="w-3.5 h-3.5 text-stone-500" />
                            <span className="font-bold truncate max-w-[140px]">3 Day Taipei Explorer</span>
                          </div>
                          <span className="text-[8px] text-stone-400">{mock.passMode.tripDuration}</span>
                        </div>

                        {/* Real Day Switcher Capsules */}
                        <div className="flex items-center gap-1 text-[8px] font-semibold">
                          <span className="px-2 py-0.5 rounded-full bg-stone-200/70 dark:bg-stone-800 text-stone-600 dark:text-stone-300">
                            {mock.passMode.dayAll}
                          </span>
                          <span className="px-2 py-0.5 rounded-full bg-[#0B3026] text-white dark:bg-emerald-500 dark:text-stone-950 shadow-xs">
                            TUE 3/10
                          </span>
                          <span className="px-2 py-0.5 rounded-full bg-stone-200/70 dark:bg-stone-800 text-stone-600 dark:text-stone-300">
                            WED 3/11
                          </span>
                          <span className="px-2 py-0.5 rounded-full bg-stone-200/70 dark:bg-stone-800 text-stone-600 dark:text-stone-300">
                            THU 3/12
                          </span>
                        </div>

                        {/* Real Weather Capsule */}
                        <div className="p-2 rounded-xl bg-white dark:bg-[#182320] border border-stone-200/80 dark:border-white/10 shadow-xs flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <div className="w-7 h-7 rounded-lg bg-amber-500/10 dark:bg-amber-400/10 flex items-center justify-center text-amber-500">
                              <Sun className="w-3.5 h-3.5" />
                            </div>
                            <div>
                              <div className="flex items-center gap-1 text-[10px] font-bold">
                                <MapPin className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
                                {/* Contract static binding: 台北 101 */}
                                <span>{mock.passMode.weatherLocation}</span>
                              </div>
                              <p className="text-[8px] text-stone-500 dark:text-stone-400">{mock.passMode.weatherDesc}</p>
                            </div>
                          </div>
                          <span className="text-[8px] font-mono font-semibold px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">
                            {mock.passMode.weatherStatus}
                          </span>
                        </div>

                        {/* Offline Active Shield Banner */}
                        <div className="p-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-[9px] text-emerald-800 dark:text-emerald-200 flex items-center justify-between">
                          <div className="flex items-center gap-1.5 font-bold">
                            <ShieldCheck className="w-3 h-3 text-emerald-600 dark:text-emerald-400 shrink-0" />
                            {/* Contract static binding: 100% 離線可用 · 本地自癒快照 */}
                            <span>{mock.passMode.offlineBanner}</span>
                          </div>
                          <span className="text-[8px] font-mono text-emerald-600 dark:text-emerald-400">{mock.passMode.offlineLatency}</span>
                        </div>

                        {/* Real Boarding Pass Card */}
                        <div className="p-2.5 rounded-xl bg-white dark:bg-[#182320] border border-stone-200/80 dark:border-white/10 shadow-sm space-y-1.5 relative overflow-hidden">
                          <div className="flex justify-between items-center pb-1 border-b border-dashed border-stone-200 dark:border-stone-800">
                            {/* Contract static binding: FLIGHT TB-2026 */}
                            <span className="text-[9px] font-mono font-bold text-stone-600 dark:text-stone-400">{mock.passMode.boardingPass.flight}</span>
                            <span className="text-[8px] font-extrabold px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-700 dark:text-amber-300">{mock.passMode.boardingPass.class}</span>
                          </div>
                          <div className="flex justify-between items-center py-0.5">
                            <div>
                              <p className="text-[8px] text-stone-400">{mock.passMode.boardingPass.originLabel}</p>
                              <p className="font-extrabold text-[11px]">{mock.passMode.boardingPass.originValue}</p>
                            </div>
                            <Plane className="w-3.5 h-3.5 text-amber-500 transform rotate-45" />
                            <div className="text-right">
                              <p className="text-[8px] text-stone-400">{mock.passMode.boardingPass.destLabel}</p>
                              <p className="font-extrabold text-[11px] text-emerald-600 dark:text-emerald-400">{mock.passMode.boardingPass.destValue}</p>
                            </div>
                          </div>
                          <div className="pt-1 border-t border-dashed border-stone-200 dark:border-stone-800 flex justify-between items-center text-[8px] text-stone-500 dark:text-stone-400">
                            {/* Contract static binding: 護照與國際機票 */}
                            <span>{mock.passMode.boardingPass.passSub}</span>
                            <span className="font-mono text-stone-600 dark:text-stone-400 tracking-widest font-bold">|||| | || ||||</span>
                          </div>
                        </div>

                        {/* Real Timeline Activity 1 */}
                        <div className="p-2 rounded-xl bg-white dark:bg-[#182320] border border-stone-200/80 dark:border-white/10 shadow-xs space-y-0.5">
                          <div className="flex items-center justify-between text-[10px]">
                            <div className="flex items-center gap-1 font-bold">
                              <span className="text-amber-600 dark:text-amber-400">09:30</span>
                              {/* Contract static binding: 台北 101 */}
                              <span>{mock.passMode.timeline1.title}</span>
                            </div>
                            <span className="text-[8px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-700 dark:text-amber-300">
                              {mock.passMode.timeline1.tag}
                            </span>
                          </div>
                          <p className="text-[8px] text-stone-500 dark:text-stone-400">
                            {mock.passMode.timeline1.desc}
                          </p>
                        </div>

                        {/* Walking transport connection */}
                        <div className="flex items-center gap-2 px-2 text-[8px] text-stone-400">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                          <span className="border-l border-dashed border-stone-300 dark:border-stone-700 h-2.5" />
                          <span>{mock.passMode.transit1}</span>
                        </div>

                        {/* Real Timeline Activity 2 */}
                        <div className="p-2 rounded-xl bg-white dark:bg-[#182320] border border-stone-200/80 dark:border-white/10 shadow-xs space-y-0.5">
                          <div className="flex items-center justify-between text-[10px]">
                            <div className="flex items-center gap-1 font-bold">
                              <span className="text-emerald-600 dark:text-emerald-400">12:00</span>
                              {/* Contract static binding: 鼎泰豐 101 店 */}
                              <span>{mock.passMode.timeline2.title}</span>
                            </div>
                            <span className="text-[8px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-700 dark:text-emerald-300">
                              {mock.passMode.timeline2.tag}
                            </span>
                          </div>
                          <p className="text-[8px] text-stone-500 dark:text-stone-400">{mock.passMode.timeline2.desc}</p>
                        </div>

                        {/* Real Timeline Activity 3 */}
                        <div className="p-2 rounded-xl bg-white dark:bg-[#182320] border border-stone-200/80 dark:border-white/10 shadow-xs space-y-0.5">
                          <div className="flex items-center justify-between text-[10px]">
                            <div className="flex items-center gap-1 font-bold">
                              <span className="text-stone-600 dark:text-stone-300">15:30</span>
                              {/* Contract static binding: 象山步道 · 巨石觀景台 */}
                              <span>{mock.passMode.timeline3.title}</span>
                            </div>
                            <span className="text-[8px] text-stone-400">{mock.passMode.timeline3.tag}</span>
                          </div>
                          <p className="text-[8px] text-stone-500 dark:text-stone-400">
                            {mock.passMode.timeline3.desc}
                          </p>
                        </div>

                        {/* Storage status & Floating Map Capsule */}
                        <div className="flex items-center justify-between pt-0.5">
                          <div className="px-2 py-1 rounded-lg bg-stone-200/60 dark:bg-stone-800/60 text-[8px] text-stone-600 dark:text-stone-300 flex items-center gap-1.5">
                            <span>{mock.passMode.storageStatus}</span>
                            {/* Contract static binding: 已同步完整資料 */}
                            <span className="font-bold text-emerald-600 dark:text-emerald-400">{mock.passMode.syncStatus}</span>
                          </div>
                          <div className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-[#0B3026] text-white dark:bg-emerald-500 dark:text-stone-950 text-[9px] font-bold shadow-md">
                            <MapPin className="w-2.5 h-2.5 text-emerald-400 dark:text-emerald-950" />
                            <span>{mock.passMode.mapPinBadge}</span>
                          </div>
                        </div>
                      </div>
                    )}

                    {activeMode === "ledger" && (
                      <div className="flex flex-col gap-2 w-full">
                        {/* Real PWA Tools View Header */}
                        <div className="flex items-center justify-between pb-0.5 border-b border-stone-200/50 dark:border-white/5">
                          <div className="space-y-0.5">
                            <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#E56E25]/10 text-[#E56E25] text-[8px] font-semibold">
                              <span className="w-1 h-1 rounded-full bg-[#E56E25] animate-pulse" />
                              tabiji・{mock.ledgerMode.badge}
                            </div>
                            <div className="text-xs font-bold text-[#1E2927] dark:text-[#E5EBEA]">
                              {mock.ledgerMode.title}
                            </div>
                          </div>
                        </div>

                        {/* Real Segmented Tabs Strip (卡片 / 記帳 / 精算器) */}
                        <div className="grid grid-cols-3 bg-white/70 dark:bg-[#182320]/80 rounded-xl p-1 border border-[#0B3026]/10 dark:border-white/10 text-center text-[9px] font-semibold">
                          <div className="py-1 rounded-lg flex items-center justify-center gap-1 text-stone-500">
                            <CreditCard className="w-3 h-3" />
                            <span>{mock.ledgerMode.tabs.cards}</span>
                          </div>
                          <div className="py-1 rounded-lg flex items-center justify-center gap-1 bg-[#0B3026] text-white dark:bg-emerald-500 dark:text-stone-950 shadow-xs">
                            <Receipt className="w-3 h-3" />
                            <span>{mock.ledgerMode.tabs.ledger}</span>
                          </div>
                          <div className="py-1 rounded-lg flex items-center justify-center gap-1 text-stone-500">
                            <Calculator className="w-3 h-3" />
                            <span>{mock.ledgerMode.tabs.calc}</span>
                          </div>
                        </div>

                        {/* Real Filter Strip (總計/列表, 全部/公帳/私帳) */}
                        <div className="flex items-center justify-between gap-1 text-[8px]">
                          <div className="flex gap-1">
                            <span className="px-2 py-0.5 rounded-lg bg-[#0B3026] text-white dark:bg-emerald-500 dark:text-stone-950 font-semibold flex items-center gap-1">
                              <PieChart className="w-2.5 h-2.5" />
                              {mock.ledgerMode.filterTotal}
                            </span>
                            <span className="px-2 py-0.5 rounded-lg bg-stone-200/60 dark:bg-stone-800 text-stone-600 dark:text-stone-300 flex items-center gap-1">
                              <List className="w-2.5 h-2.5" />
                              {mock.ledgerMode.filterList}
                            </span>
                          </div>
                          <div className="flex gap-1 bg-stone-200/60 dark:bg-stone-800 p-0.5 rounded-lg font-medium text-stone-600 dark:text-stone-300">
                            <span className="px-1.5 py-0.5 rounded bg-white dark:bg-stone-700 shadow-2xs font-bold">{mock.ledgerMode.filterAll}</span>
                            <span className="px-1.5 py-0.5">{mock.ledgerMode.filterPublic}</span>
                            <span className="px-1.5 py-0.5">{mock.ledgerMode.filterPrivate}</span>
                          </div>
                        </div>

                        {/* Multi-Currency & AA Split Summary Card */}
                        <div className="p-2 rounded-xl bg-white dark:bg-[#182320] border border-stone-200/80 dark:border-white/10 shadow-xs space-y-0.5 text-center">
                          <div className="flex items-center justify-between text-[8px] text-stone-500 dark:text-stone-400 pb-1 border-b border-stone-100 dark:border-white/5">
                            <span className="font-bold">{mock.ledgerMode.summaryTitle}</span>
                            {/* Contract static binding: TWD ⇄ JPY 0.215 */}
                            <span className="font-mono text-emerald-600 dark:text-emerald-400">TWD ⇄ JPY 0.215</span>
                          </div>
                          <p className="text-[8px] text-stone-400 pt-0.5">{mock.ledgerMode.summaryPerPerson}</p>
                          {/* Contract static binding: NT$ 4,283 */}
                          <p className="text-lg font-extrabold text-[#0B3026] dark:text-emerald-400 leading-tight">
                            NT$ 4,283
                          </p>
                          {/* Contract static binding: NT$ 12,850 */}
                          <p className="text-[8px] text-stone-400">{mock.ledgerMode.summaryTotal}</p>
                        </div>

                        {/* Real Expense Items */}
                        <div className="space-y-1 text-[9px]">
                          <div className="p-1.5 rounded-lg bg-white dark:bg-[#182320] border border-stone-200/80 dark:border-white/10 flex justify-between items-center">
                            <div>
                              <span className="font-bold block text-[9px]">{mock.ledgerMode.item1.title}</span>
                              <span className="text-[8px] text-stone-400">{mock.ledgerMode.item1.meta}</span>
                            </div>
                            <span className="font-bold text-stone-800 dark:text-stone-200">NT$ 2,400</span>
                          </div>
                          <div className="p-1.5 rounded-lg bg-white dark:bg-[#182320] border border-stone-200/80 dark:border-white/10 flex justify-between items-center">
                            <div>
                              <span className="font-bold block text-[9px]">{mock.ledgerMode.item2.title}</span>
                              <span className="text-[8px] text-stone-400">{mock.ledgerMode.item2.meta}</span>
                            </div>
                            <span className="font-bold text-stone-800 dark:text-stone-200">NT$ 1,650</span>
                          </div>
                          <div className="p-1.5 rounded-lg bg-white dark:bg-[#182320] border border-stone-200/80 dark:border-white/10 flex justify-between items-center">
                            <div>
                              <span className="font-bold block text-[9px]">{mock.ledgerMode.item3.title}</span>
                              <span className="text-[8px] text-stone-400">{mock.ledgerMode.item3.meta}</span>
                            </div>
                            <span className="font-bold text-stone-800 dark:text-stone-200">NT$ 8,800</span>
                          </div>
                        </div>

                        {/* Floating Add Expense Action */}
                        <div className="flex justify-end pt-0.5">
                          <div className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-[#0B3026] text-white dark:bg-emerald-500 dark:text-stone-950 text-[9px] font-bold shadow-md">
                            <Plus className="w-2.5 h-2.5" />
                            <span>{mock.ledgerMode.btnAdd}</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </motion.div>
                </motion.div>
              </AnimatePresence>
            </div>

            {/* Bottom Fixed Frosted Dock & Home Indicator (z-30) */}
            <div className="w-full px-3 pt-1 pb-1.5 shrink-0 z-30 bg-gradient-to-t from-[#F6F5EE] via-[#F6F5EE]/95 to-transparent dark:from-[#121A18] dark:via-[#121A18]/95" aria-hidden="true">
              {/* Floating 4-Column Dock */}
              <div className="w-full rounded-2xl bg-white/90 dark:bg-[#182320]/95 backdrop-blur-md border border-stone-200/80 dark:border-white/10 p-1 grid grid-cols-4 gap-1 shadow-sm text-center">
                <div className={`py-1 rounded-xl flex flex-col items-center justify-center transition-all ${activeMode === "pass" ? "bg-[#0B3026] text-white dark:bg-emerald-500 dark:text-stone-950 shadow-xs" : "text-stone-500 dark:text-stone-400"}`}>
                  <Ticket className="w-3 h-3" />
                  <span className="text-[8px] font-bold mt-0.5">{mock.dock.arrival}</span>
                </div>
                <div className={`py-1 rounded-xl flex flex-col items-center justify-center transition-all ${activeMode === "route" ? "bg-[#0B3026] text-white dark:bg-emerald-500 dark:text-stone-950 shadow-xs" : "text-stone-500 dark:text-stone-400"}`}>
                  <Navigation className="w-3 h-3" />
                  <span className="text-[8px] font-bold mt-0.5">{mock.dock.transit}</span>
                </div>
                <div className={`py-1 rounded-xl flex flex-col items-center justify-center transition-all ${activeMode === "ledger" ? "bg-[#0B3026] text-white dark:bg-emerald-500 dark:text-stone-950 shadow-xs" : "text-stone-500 dark:text-stone-400"}`}>
                  <Coins className="w-3 h-3" />
                  <span className="text-[8px] font-bold mt-0.5">{mock.dock.split}</span>
                </div>
                <div className="py-1 rounded-xl flex flex-col items-center justify-center text-stone-500 dark:text-stone-400">
                  <Users className="w-3 h-3" />
                  <span className="text-[8px] font-bold mt-0.5">{mock.dock.profile}</span>
                </div>
              </div>
              <div className="w-full flex justify-center pt-1.5">
                <div className="w-24 h-1 bg-stone-400/50 dark:bg-white/40 rounded-full" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
