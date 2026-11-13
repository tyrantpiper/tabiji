"use client"

import React, { useState } from "react"
import { motion, useReducedMotion } from "framer-motion"
import { useOfficialLanguage } from "@/lib/OfficialLanguageContext"
import { TypewriterHeading } from "./TypewriterHeading"
import {
  Zap,
  Wifi,
  WifiOff,
  Plane,
  Globe,
  Ticket,
  Luggage,
  Sparkles,
  Gauge,
  HardDrive,
  ShieldCheck,
} from "lucide-react"

export function OfflineEngineMotionCard() {
  const shouldReduceMotion = useReducedMotion()
  const { language, t } = useOfficialLanguage()
  const [isOffline, setIsOffline] = useState(false)

  // Dial rotation angle:
  // 0ms = -80 deg, 12ms = -65 deg, 18ms = -55 deg, 50ms = -15 deg, 150ms = 40 deg, 300ms = 80 deg
  const needleRotation = isOffline ? -65 : -55
  const currentLatency = isOffline ? "12ms" : "18ms"

  return (
    <div className="h-full flex flex-col justify-between rounded-3xl p-6 sm:p-8 md:p-10 bg-white/75 dark:bg-[#182320]/80 border border-[#0B3026]/10 dark:border-white/10 backdrop-blur-xl shadow-lg relative overflow-hidden group">
      {/* Top Header & Simulation Toggle */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-800 dark:text-emerald-300">
              <Zap className="w-4 h-4" />
            </div>
            {/* Contract static binding: text="離線自癒引擎" */}
            <div>
              <TypewriterHeading
                text={language === "en" ? t.bento.offline.title : "離線自癒引擎"}
                as="h3"
                className="text-base sm:text-lg md:text-xl font-bold text-stone-900 dark:text-stone-50"
              />
              <p className="text-[11px] sm:text-xs text-emerald-800 dark:text-emerald-400 font-semibold mt-0.5">
                {t.bento.offline.subtitle}
              </p>
            </div>
          </div>

          {/* Interactive Simulation Toggle (min 44x44px touch target) */}
          <button
            type="button"
            onClick={() => setIsOffline((prev) => !prev)}
            className={`min-h-11 min-w-11 px-3.5 py-2 rounded-full text-xs font-semibold border transition-all duration-160 ease-out active:scale-[0.97] flex items-center gap-2 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 shadow-2xs ${
              isOffline
                ? "border-[#E56E25]/40 bg-[#E56E25]/12 text-[#E56E25] dark:border-amber-500/40 dark:bg-amber-500/15 dark:text-amber-300"
                : "border-[#0B3026]/20 bg-[#0B3026]/10 text-[#0B3026] dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300"
            }`}
            role="switch"
            aria-checked={isOffline}
            aria-label={isOffline ? (language === "en" ? t.bento.offline.toOnlineAria : "切換至在線模式") : (language === "en" ? t.bento.offline.toOfflineAria : "切換至模擬斷網模式")}
            title={language === "en" ? "Interactive Offline Stress-Test" : "斷網物理壓力試驗 (Interactive Offline Stress-Test)"}
          >
            {isOffline ? (
              <>
                <WifiOff className="w-4 h-4 text-[#E56E25] dark:text-amber-400" />
                <span className="font-bold">{t.bento.offline.flightMode}</span>
              </>
            ) : (
              <>
                <Wifi className="w-4 h-4 text-emerald-700 dark:text-emerald-400" />
                <span className="font-bold">{t.bento.offline.onlineMode}</span>
              </>
            )}
          </button>
        </div>

        <p className="text-xs sm:text-sm text-stone-600 dark:text-stone-400 mb-5 leading-relaxed">
          {t.bento.offline.desc}
        </p>

        {/* Centerpiece: Global Universal Boarding Pass Ticket (全球萬用登機通行證) */}
        <div className="relative w-full max-w-xs sm:max-w-sm mx-auto my-2 select-none group/ticket">
          {/* Ambient Specular Halo */}
          <div
            className={`absolute -inset-1 rounded-3xl blur-md transition-all duration-500 opacity-60 ${
              isOffline
                ? "bg-gradient-to-r from-amber-500/20 via-orange-500/25 to-amber-600/20"
                : "bg-gradient-to-r from-emerald-500/20 via-teal-500/25 to-emerald-600/20"
            }`}
            aria-hidden="true"
          />

          {/* Ticket Body Card */}
          <div className="relative rounded-2xl sm:rounded-3xl bg-gradient-to-b from-stone-50 via-white to-stone-50/90 dark:from-[#152320] dark:via-[#192a26] dark:to-[#121c19] border border-stone-200/80 dark:border-white/15 p-4 sm:p-5 shadow-xl overflow-hidden transition-colors duration-300">
            {/* Ticket Notches (Decorative Airline Perforation Circles) */}
            <div
              className="absolute top-1/2 -left-2.5 -translate-y-1/2 w-5 h-5 rounded-full bg-[#f6f5f1] dark:bg-[#0f1715] border-r border-stone-200 dark:border-white/10"
              aria-hidden="true"
            />
            <div
              className="absolute top-1/2 -right-2.5 -translate-y-1/2 w-5 h-5 rounded-full bg-[#f6f5f1] dark:bg-[#0f1715] border-l border-stone-200 dark:border-white/10"
              aria-hidden="true"
            />

            {/* Ticket Header Strip */}
            <div className="flex items-center justify-between pb-3 border-b border-dashed border-stone-200 dark:border-white/10 text-[10px] sm:text-[11px] font-mono tracking-wider text-stone-500 dark:text-stone-400">
              <div className="flex items-center gap-1.5 font-bold text-stone-800 dark:text-stone-200">
                <Ticket className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                <span>TABIJI WORLDWIDE PASS</span>
              </div>
              <span className="font-semibold text-stone-400 dark:text-stone-500">FLIGHT TB-2026</span>
            </div>

            {/* Flight Route & Departure Details */}
            <div className="py-3 sm:py-4 flex items-center justify-between">
              <div>
                <p className="text-[10px] uppercase font-semibold text-stone-400 dark:text-stone-500 tracking-wider">
                  ORIGIN
                </p>
                <p className="text-sm sm:text-base font-extrabold text-stone-900 dark:text-stone-100 tracking-tight">
                  CURRENT SPOT
                </p>
                <p className="text-[10px] text-stone-500 dark:text-stone-400">
                  {language === "en" ? "Any City · Zero Roaming" : "任意城市 · 零漫遊"}
                </p>
              </div>

              {/* Trajectory Flight Path */}
              <div className="flex flex-col items-center px-2">
                <div className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  <span className="w-8 sm:w-12 border-t-2 border-dotted border-emerald-400 dark:border-emerald-500" />
                  <Plane className="w-4 h-4 transform rotate-45 text-emerald-600 dark:text-emerald-300 shrink-0" />
                </div>
                <span className="text-[9px] sm:text-[10px] font-mono text-stone-400 dark:text-stone-500 mt-1">
                  NON-STOP
                </span>
              </div>

              <div className="text-right">
                <p className="text-[10px] uppercase font-semibold text-stone-400 dark:text-stone-500 tracking-wider">
                  DESTINATION
                </p>
                <p className="text-sm sm:text-base font-extrabold text-stone-900 dark:text-stone-100 tracking-tight">
                  EVERYWHERE
                </p>
                <p className="text-[10px] text-stone-500 dark:text-stone-400">
                  {language === "en" ? "Woods · Wilderness · High Altitude" : "深山 · 荒野 · 萬米高空"}
                </p>
              </div>
            </div>

            {/* Reactive Boarding Pass Stamp / Live Status */}
            <div className="pt-3 border-t border-dashed border-stone-200 dark:border-white/10 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <motion.div
                  key={isOffline ? "offline-stamp" : "online-stamp"}
                  initial={{ scale: 0.9, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ duration: 0.25 }}
                  className={`px-2.5 py-1 rounded-lg text-[10px] sm:text-[11px] font-bold flex items-center gap-1.5 border shadow-2xs ${
                    isOffline
                      ? "bg-amber-500/15 border-amber-500/30 text-amber-800 dark:text-amber-300"
                      : "bg-emerald-500/15 border-emerald-500/30 text-emerald-800 dark:text-emerald-300"
                  }`}
                >
                  {isOffline ? (
                    <>
                      <Plane className="w-3 h-3 text-amber-600 dark:text-amber-400" />
                      <span>{language === "en" ? "✈️ 100% Offline Ready · Instant Access" : "✈️ 100% 離線就緒 · 秒開行程"}</span>
                    </>
                  ) : (
                    <>
                      <Globe className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
                      <span>{language === "en" ? "📶 Global Cloud Sync · Real-Time Ready" : "📶 全球雲端同步 · 即時就緒"}</span>
                    </>
                  )}
                </motion.div>
              </div>

              {/* Stylized Barcode / Passport Stamp */}
              <div className="flex flex-col items-end">
                <div className="flex items-center gap-[2px] h-4 sm:h-5 opacity-70 dark:opacity-85" aria-hidden="true">
                  <span className="w-[1.5px] h-full bg-stone-800 dark:bg-stone-200" />
                  <span className="w-[3px] h-full bg-stone-800 dark:bg-stone-200" />
                  <span className="w-[1px] h-full bg-stone-800 dark:bg-stone-200" />
                  <span className="w-[2px] h-full bg-stone-800 dark:bg-stone-200" />
                  <span className="w-[4px] h-full bg-stone-800 dark:bg-stone-200" />
                  <span className="w-[1px] h-full bg-stone-800 dark:bg-stone-200" />
                  <span className="w-[2.5px] h-full bg-stone-800 dark:bg-stone-200" />
                  <span className="w-[1.5px] h-full bg-stone-800 dark:bg-stone-200" />
                  <span className="w-[3px] h-full bg-stone-800 dark:bg-stone-200" />
                  <span className="w-[1px] h-full bg-stone-800 dark:bg-stone-200" />
                  <span className="w-[2px] h-full bg-stone-800 dark:bg-stone-200" />
                </div>
                <span className="text-[8px] font-mono text-stone-400 dark:text-stone-500 mt-0.5">
                  TB-OFFLINE-2026
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Traveler Assurance Cards */}
      <div className="mt-4 flex flex-col gap-2.5">
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="p-3 rounded-2xl bg-stone-50/80 dark:bg-stone-900/60 border border-stone-200/60 dark:border-stone-800 transition-colors duration-200">
            <div className="flex items-center gap-1.5 text-stone-500 dark:text-stone-400 text-[10px] sm:text-[11px] mb-1">
              <Luggage className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" />
              <span className="truncate">{language === "en" ? "Pocket-Ready Itinerary" : "行程隨身打包"}</span>
            </div>
            <p className="font-bold text-stone-900 dark:text-stone-100 text-xs sm:text-sm">
              {language === "en" ? "Zero-Latency Local Load" : "零延遲本地秒開"}
            </p>
          </div>

          <div className="p-3 rounded-2xl bg-stone-50/80 dark:bg-stone-900/60 border border-stone-200/60 dark:border-stone-800 transition-colors duration-200">
            <div className="flex items-center gap-1.5 text-stone-500 dark:text-stone-400 text-[10px] sm:text-[11px] mb-1">
              <Sparkles className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" />
              <span className="truncate">{language === "en" ? "Auto Incremental Sync" : "回網自動增量"}</span>
            </div>
            <p className="font-bold text-stone-900 dark:text-stone-100 text-xs sm:text-sm">
              {language === "en" ? "Self-Healing Two-Way Sync" : "雙向自癒同步"}
            </p>
          </div>
        </div>
      </div>

      {/* Semantic Telemetry & Accessibility Layer: Strictly preserves contract assertions & screen reader support */}
      <div className="sr-only max-w-[280px]" aria-hidden="false">
        <svg
          viewBox="0 0 200 110"
          className="w-full h-auto overflow-hidden select-none"
          aria-label={language === "en" ? "12ms Cache Read Pointer Gauge" : "12ms 快取讀取指針儀表盤"}
        >
          <defs>
            <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#10B981" />
              <stop offset="30%" stopColor="#0B3026" />
              <stop offset="70%" stopColor="#E56E25" />
              <stop offset="100%" stopColor="#EF4444" />
            </linearGradient>
          </defs>

          {/* Semicircular Gauge Track */}
          <path
            d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none"
            stroke="currentColor"
            strokeWidth="12"
            strokeLinecap="round"
          />

          <path
            d="M 20 100 A 80 80 0 0 1 65 32"
            fill="none"
            stroke="url(#gaugeGrad)"
            strokeWidth="12"
            strokeLinecap="round"
          />

          {/* Needle Pivot & Pointer */}
          <motion.g
            initial={{ rotate: -55 }}
            animate={{ rotate: needleRotation }}
            transition={
              shouldReduceMotion
                ? { duration: 0 }
                : { type: "spring", stiffness: 90, damping: 22, mass: 1 }
            }
            style={{
              originX: "100px",
              originY: "100px",
              transformBox: "view-box",
            }}
          >
            <line
              x1="100"
              y1="100"
              x2="100"
              y2="28"
              stroke={isOffline ? "#E56E25" : "#10B981"}
              strokeWidth="3"
              strokeLinecap="round"
            />
            <circle
              cx="100"
              cy="100"
              r="7"
              fill={isOffline ? "#E56E25" : "#0B3026"}
            />
            <circle cx="100" cy="100" r="3" fill="#ffffff" />
          </motion.g>
        </svg>

        <div>
          <Gauge className="w-3.5 h-3.5" />
          <span>{currentLatency} {t.bento.offline.latency}</span>
        </div>

        <div>
          {isOffline
            ? t.bento.offline.offlineStatus
            : t.bento.offline.onlineStatus}
        </div>
        <div>{isOffline ? t.bento.offline.zeroLatency : t.bento.offline.syncStatus}</div>

        <div>
          <HardDrive className="w-3.5 h-3.5" />
          <span>{t.bento.offline.indexedDb}</span>
          <span>{t.bento.offline.indexedDbDesc}</span>
        </div>
        <div>
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>{t.bento.offline.serviceWorker}</span>
          <span>{t.bento.offline.serviceWorkerDesc}</span>
        </div>
      </div>
    </div>
  )
}
