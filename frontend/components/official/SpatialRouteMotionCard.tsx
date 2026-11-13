"use client"

import React, { useState } from "react"
import { motion, useReducedMotion } from "framer-motion"
import { Globe, Plane, Navigation, Clock, CheckCircle2 } from "lucide-react"
import { useOfficialLanguage } from "@/lib/OfficialLanguageContext"
import { TypewriterHeading } from "./TypewriterHeading"

interface Waypoint {
  id: string
  name: string
  en: string
  flag: string
  code: string
  x: number
  y: number
  tz: string
  distance: string
  distanceEn: string
  tag: string
  tagEn: string
}

const WAYPOINTS: Waypoint[] = [
  {
    id: "taipei",
    name: "台北",
    en: "Taipei",
    flag: "🇹🇼",
    code: "TPE",
    x: 380,
    y: 195,
    tz: "UTC+8",
    distance: "核心協調起點",
    distanceEn: "Core Hub Origin",
    tag: "亞洲智慧協調樞紐",
    tagEn: "Asia Coordination Hub",
  },
  {
    id: "tokyo",
    name: "東京",
    en: "Tokyo",
    flag: "🇯🇵",
    code: "HND",
    x: 440,
    y: 130,
    tz: "UTC+9",
    distance: "+2,180 km",
    distanceEn: "+2,180 km",
    tag: "都會漫遊與鐵道接駁",
    tagEn: "Urban Transit & Metro Sync",
  },
  {
    id: "reykjavik",
    name: "雷克雅維克",
    en: "Reykjavik",
    flag: "🇮🇸",
    code: "KEF",
    x: 130,
    y: 65,
    tz: "UTC+0",
    distance: "+8,700 km",
    distanceEn: "+8,700 km",
    tag: "北極圈極光與冰原航線",
    tagEn: "Arctic Aurora & Glacier Path",
  },
  {
    id: "paris",
    name: "巴黎",
    en: "Paris",
    flag: "🇫🇷",
    code: "CDG",
    x: 200,
    y: 110,
    tz: "UTC+1",
    distance: "+9,800 km",
    distanceEn: "+9,800 km",
    tag: "歐洲跨城鐵路樞紐",
    tagEn: "European High-Speed Rail Hub",
  },
  {
    id: "newyork",
    name: "紐約",
    en: "New York",
    flag: "🇺🇸",
    code: "JFK",
    x: 80,
    y: 175,
    tz: "UTC-5",
    distance: "+12,500 km",
    distanceEn: "+12,500 km",
    tag: "跨大西洋跨時區漫遊",
    tagEn: "Transatlantic Cross-Zone Path",
  },
]

export function SpatialRouteMotionCard() {
  const shouldReduceMotion = useReducedMotion()
  const { language, t } = useOfficialLanguage()
  const [selectedWaypoint, setSelectedWaypoint] = useState<Waypoint>(WAYPOINTS[0])

  return (
    <div className="h-full flex flex-col justify-between rounded-3xl p-6 sm:p-8 bg-white/75 dark:bg-[#182320]/80 border border-[#0B3026]/10 dark:border-white/10 backdrop-blur-xl shadow-lg relative overflow-hidden group">
      {/* Top Header Badge */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-800 dark:text-emerald-300">
            <Globe className="w-4 h-4" />
          </div>
          <div>
            <span className="block text-[11px] font-semibold uppercase tracking-wider text-emerald-800 dark:text-emerald-400">
              ✦ Global Waypoints Synced
            </span>
            {/* Contract static binding: text="空間航線巡航" */}
            <TypewriterHeading
              text={language === "en" ? t.bento.routes.title : "空間航線巡航"}
              as="h3"
              className="text-lg sm:text-xl font-bold text-stone-900 dark:text-stone-50"
            />
            <p className="text-xs text-emerald-800 dark:text-emerald-400 font-semibold mt-0.5">
              {t.bento.routes.subtitle}
            </p>
          </div>
        </div>
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-[#0B3026]/5 dark:bg-white/10 text-stone-700 dark:text-stone-300">
          <Plane className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
          {t.bento.routes.tag}
        </span>
      </div>

      <p className="text-xs sm:text-sm text-stone-600 dark:text-stone-400 mb-4 leading-relaxed font-normal">
        {t.bento.routes.desc}
      </p>

      {/* SVG Motion Canvas */}
      <div className="relative w-full aspect-[15/8] bg-stone-100/70 dark:bg-stone-900/60 rounded-2xl border border-stone-200/60 dark:border-stone-800/80 p-2 sm:p-4 overflow-hidden flex items-center justify-center">
        {/* Subtle coordinate grid lines */}
        <div
          className="absolute inset-0 opacity-[0.04] dark:opacity-[0.06] bg-[radial-gradient(#0B3026_1px,transparent_1px)]"
          style={{ backgroundSize: "16px 16px" }}
          aria-hidden="true"
        />

        <svg
          viewBox="0 0 600 320"
          className="w-full h-auto overflow-visible select-none"
          aria-label="全球旅遊多航點航線圖"
        >
          <defs>
            <linearGradient id="routeGradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#0B3026" stopOpacity="0.8" />
              <stop offset="50%" stopColor="#10B981" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#E56E25" stopOpacity="0.8" />
            </linearGradient>

            <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>

          {/* Background Reference Tracks */}
          <path
            d="M 380 195 Q 410 160 440 130"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeDasharray="4 4"
            vectorEffect="non-scaling-stroke"
            strokeLinecap="round"
            className="text-stone-300 dark:text-stone-700 opacity-60"
          />
          <path
            d="M 440 130 Q 285 30 130 65"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeDasharray="4 4"
            vectorEffect="non-scaling-stroke"
            strokeLinecap="round"
            className="text-stone-300 dark:text-stone-700 opacity-60"
          />
          <path
            d="M 130 65 Q 165 85 200 110"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeDasharray="4 4"
            vectorEffect="non-scaling-stroke"
            strokeLinecap="round"
            className="text-stone-300 dark:text-stone-700 opacity-60"
          />
          <path
            d="M 200 110 Q 140 135 80 175"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeDasharray="4 4"
            vectorEffect="non-scaling-stroke"
            strokeLinecap="round"
            className="text-stone-300 dark:text-stone-700 opacity-60"
          />
          <path
            d="M 80 175 Q 230 290 380 195"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeDasharray="4 4"
            vectorEffect="non-scaling-stroke"
            strokeLinecap="round"
            className="text-stone-300 dark:text-stone-700 opacity-60"
          />

          {/* Dynamic Arc Pulling Animation (60FPS GPU Accelerated) */}
          <motion.path
            d="M 380 195 Q 410 160 440 130 Q 285 30 130 65 Q 165 85 200 110 Q 140 135 80 175 Q 230 290 380 195"
            fill="none"
            stroke="url(#routeGradient)"
            strokeWidth="2.5"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: shouldReduceMotion ? 1 : [0.1, 1, 0.1] }}
            transition={{
              duration: 6,
              repeat: Infinity,
              ease: "easeInOut",
            }}
          />

          {/* Micro-Waypoint Pulses & Nodes */}
          {WAYPOINTS.map((wp, index) => {
            const isSelected = selectedWaypoint.id === wp.id
            return (
              <g key={wp.id} className="cursor-pointer" onClick={() => setSelectedWaypoint(wp)}>
                {/* Outer Ripple Wave */}
                <motion.circle
                  cx={wp.x}
                  cy={wp.y}
                  r={isSelected ? 14 : 9}
                  fill="none"
                  stroke={isSelected ? "#10B981" : "#E56E25"}
                  strokeWidth="1.5"
                  initial={{ scale: 1, opacity: 0.8 }}
                  animate={
                    shouldReduceMotion
                      ? { scale: 1, opacity: 0.3 }
                      : { scale: [1, 2.2], opacity: [0.8, 0] }
                  }
                  transition={{
                    duration: 2.4,
                    repeat: Infinity,
                    ease: "easeOut",
                    delay: index * 0.4,
                  }}
                />

                {/* Core Dot */}
                <circle
                  cx={wp.x}
                  cy={wp.y}
                  r={isSelected ? 5.5 : 4}
                  fill={isSelected ? "#10B981" : "#E56E25"}
                  className="transition-all duration-200"
                />

                {/* Waypoint Text Label */}
                <text
                  x={wp.x}
                  y={wp.y + 16}
                  textAnchor="middle"
                  className={`text-[11px] font-semibold select-none ${
                    isSelected
                      ? "fill-emerald-800 dark:fill-emerald-300 font-bold"
                      : "fill-stone-600 dark:fill-stone-300"
                  }`}
                >
                  {language === "en" ? wp.en : wp.name}
                </text>
              </g>
            )
          })}
        </svg>
      </div>

      {/* Interactive Waypoint Quick Selector (min 44x44px touch ergonomics) */}
      <div className="mt-4 flex flex-wrap items-center gap-1.5 sm:gap-2">
        {WAYPOINTS.map((wp) => {
          const isSelected = selectedWaypoint.id === wp.id
          return (
            <button
              key={wp.id}
              type="button"
              onClick={() => setSelectedWaypoint(wp)}
              className={`min-h-11 px-3.5 py-2 rounded-full text-xs font-medium transition-all duration-160 ease-out active:scale-[0.97] flex items-center gap-1.5 cursor-pointer ${
                isSelected
                  ? "bg-[#0B3026] text-white dark:bg-emerald-500 dark:text-stone-950 font-semibold shadow-sm"
                  : "bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300 hover:bg-stone-200 dark:hover:bg-stone-700"
              }`}
              aria-label={language === "en" ? `Select waypoint ${wp.en}` : `選擇航點 ${wp.name}`}
            >
              <span>{wp.flag}</span>
              <span>{language === "en" ? wp.en : wp.name}</span>
            </button>
          )
        })}
      </div>

      {/* Selected Waypoint Detail Card */}
      <div className="mt-4 p-3.5 rounded-2xl bg-stone-50 dark:bg-stone-900/60 border border-stone-200/60 dark:border-stone-800 flex items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2.5">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
          <div>
            <p className="font-semibold text-stone-900 dark:text-stone-100">
              {selectedWaypoint.flag} {language === "en" ? selectedWaypoint.en : selectedWaypoint.name} ({selectedWaypoint.code}) · {language === "en" ? selectedWaypoint.tagEn : selectedWaypoint.tag}
            </p>
            <p className="text-stone-500 dark:text-stone-400 flex items-center gap-2 text-[11px] mt-0.5">
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" /> {selectedWaypoint.tz}
              </span>
              <span>•</span>
              <span className="flex items-center gap-1">
                <Navigation className="w-3 h-3" /> {language === "en" ? selectedWaypoint.distanceEn : selectedWaypoint.distance}
              </span>
            </p>
          </div>
        </div>
        <span className="text-[11px] font-semibold text-emerald-700 dark:text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded-full shrink-0">
          {t.bento.routes.ready}
        </span>
      </div>
    </div>
  )
}

