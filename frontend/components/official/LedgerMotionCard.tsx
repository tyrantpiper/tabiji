"use client"

import React, { useState } from "react"
import { motion, useReducedMotion } from "framer-motion"
import { Coins, Users, Utensils, Train, Hotel, ArrowRightLeft } from "lucide-react"
import { useOfficialLanguage } from "@/lib/OfficialLanguageContext"
import { TypewriterHeading } from "./TypewriterHeading"

type CurrencyCode = "JPY" | "TWD" | "USD"

interface CurrencyConfig {
  code: CurrencyCode
  symbol: string
  name: string
  flag: string
  rate: number // relative to JPY
  decimals: number
}

const CURRENCIES: Record<CurrencyCode, CurrencyConfig> = {
  JPY: { code: "JPY", symbol: "¥", name: "日圓", flag: "🇯🇵", rate: 1, decimals: 0 },
  TWD: { code: "TWD", symbol: "NT$", name: "台幣", flag: "🇹🇼", rate: 0.2081, decimals: 0 },
  USD: { code: "USD", symbol: "$", name: "美元", flag: "🇺🇸", rate: 0.006486, decimals: 2 },
}

interface ExpenseItem {
  id: string
  category: string
  categoryEn: string
  title: string
  titleEn: string
  icon: React.ElementType
  amountJPY: number
}

const EXPENSES: ExpenseItem[] = [
  { id: "dining", category: "餐飲", categoryEn: "Dining", title: "跨國美食與在地饗宴", titleEn: "Local Gourmet & Culinary Journey", icon: Utensils, amountJPY: 8200 },
  { id: "transit", category: "交通", categoryEn: "Transit", title: "跨國航班與城際接駁", titleEn: "Intercity Rail & Subway Rides", icon: Train, amountJPY: 3400 },
  { id: "stay", category: "住宿", categoryEn: "Stay", title: "景觀設計精品旅宿", titleEn: "Boutique Design Hotel", icon: Hotel, amountJPY: 6900 },
]

export function LedgerMotionCard() {
  const shouldReduceMotion = useReducedMotion()
  const { language, t } = useOfficialLanguage()
  const [currency, setCurrency] = useState<CurrencyCode>("JPY")
  const [splitFourWays, setSplitFourWays] = useState(true)

  const config = CURRENCIES[currency]
  const totalJPY = EXPENSES.reduce((sum, item) => sum + item.amountJPY, 0) // 18,500
  const activeAmount = splitFourWays ? totalJPY / 4 : totalJPY

  // Format currency value
  const formatAmount = (jpyValue: number) => {
    const converted = jpyValue * config.rate
    if (config.decimals === 0) {
      return Math.round(converted).toLocaleString("en-US")
    }
    return converted.toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  }

  return (
    <div className="h-full flex flex-col justify-between rounded-3xl p-6 sm:p-8 bg-white/75 dark:bg-[#182320]/80 border border-[#0B3026]/10 dark:border-white/10 backdrop-blur-xl shadow-lg relative overflow-hidden group">
      {/* Top Header */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-800 dark:text-emerald-300">
              <Coins className="w-4 h-4" />
            </div>
            {/* Contract static binding: text="智慧多幣別分帳" */}
            <div>
              <span className="block text-[11px] font-semibold uppercase tracking-wider text-emerald-800 dark:text-emerald-400">
                ✦ Real-Time Multi-Currency
              </span>
              <TypewriterHeading
                text={language === "en" ? t.bento.ledger.title : "智慧多幣別分帳"}
                as="h3"
                className="text-lg sm:text-xl font-bold text-stone-900 dark:text-stone-50"
              />
              <p className="text-xs text-emerald-800 dark:text-emerald-400 font-semibold mt-0.5">
                {t.bento.ledger.subtitle}
              </p>
            </div>
          </div>

          {/* Split Mode Toggle Button (min 44x44px touch target) */}
          <button
            type="button"
            onClick={() => setSplitFourWays((prev) => !prev)}
            className="min-h-11 min-w-11 px-3.5 py-2 rounded-full text-xs font-semibold bg-stone-100 hover:bg-stone-200 dark:bg-stone-800 dark:hover:bg-stone-700 text-stone-700 dark:text-stone-300 transition-all duration-160 ease-out active:scale-[0.97] flex items-center gap-1.5 cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
            aria-label={splitFourWays ? (language === "en" ? t.bento.ledger.toTotalAria : "切換為全團總額") : (language === "en" ? t.bento.ledger.toSplitAria : "切換為4人平攤")}
          >
            <Users className="w-3.5 h-3.5 text-[#0B3026] dark:text-emerald-400" />
            <span>{splitFourWays ? t.bento.ledger.splitFour : t.bento.ledger.totalGroup}</span>
          </button>
        </div>

        <p className="text-xs sm:text-sm text-stone-600 dark:text-stone-400 mb-6 leading-relaxed font-normal">
          {t.bento.ledger.desc}
        </p>

        {/* Currency Switcher Buttons (min 44x44px touch ergonomics) */}
        <div className="flex items-center gap-2 mb-6" role="tablist" aria-label={language === "en" ? "Select currency" : "選擇幣別"}>
          {(Object.keys(CURRENCIES) as CurrencyCode[]).map((code) => {
            const item = CURRENCIES[code]
            const isSelected = currency === code
            return (
              <button
                key={code}
                type="button"
                role="tab"
                aria-selected={isSelected}
                onClick={() => setCurrency(code)}
                className={`min-h-11 flex-1 px-3 py-2 rounded-2xl text-xs font-bold transition-all duration-160 ease-out active:scale-[0.97] flex items-center justify-center gap-1.5 cursor-pointer ${
                  isSelected
                    ? "bg-[#0B3026] text-white dark:bg-emerald-500 dark:text-stone-950 shadow-md"
                    : "bg-stone-100 dark:bg-stone-800/80 text-stone-600 dark:text-stone-400 hover:bg-stone-200 dark:hover:bg-stone-700"
                }`}
              >
                <span>{item.flag}</span>
                <span>{item.code}</span>
              </button>
            )
          })}
        </div>

        {/* Multi-Currency Real-Time Scrolling Number Counter */}
        <div className="p-5 rounded-2xl bg-stone-100/70 dark:bg-stone-900/60 border border-stone-200/60 dark:border-stone-800 text-center mb-6">
          <p className="text-xs text-stone-500 dark:text-stone-400 font-medium mb-1">
            {splitFourWays ? t.bento.ledger.perPerson : t.bento.ledger.totalAmount}
          </p>
          <div className="flex items-baseline justify-center gap-1.5 overflow-hidden">
            <span className="text-xl sm:text-2xl font-bold text-stone-500 dark:text-stone-400">
              {config.symbol}
            </span>
            {/* Smooth Spring Counter (Compositor transform/opacity only) */}
            <motion.span
              key={`${currency}-${splitFourWays}`}
              initial={{ opacity: 0, y: shouldReduceMotion ? 0 : 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                duration: 0.35,
                ease: [0.23, 1, 0.32, 1] as const,
              }}
              className="text-3xl sm:text-4xl font-extrabold tracking-tight text-stone-900 dark:text-stone-50"
            >
              {formatAmount(activeAmount)}
            </motion.span>
          </div>
          <p className="text-[11px] text-stone-500 dark:text-stone-400 mt-1 flex items-center justify-center gap-1">
            <ArrowRightLeft className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
            <span>{t.bento.ledger.rateNote}</span>
          </p>
        </div>
      </div>

      {/* Spring Physics Interactive Expense Category Cards (whileHover={{ y: -4, scale: 1.02 }}) */}
      <div className="flex flex-col gap-2.5">
        {EXPENSES.map((exp) => {
          const Icon = exp.icon
          const itemAmount = splitFourWays ? exp.amountJPY / 4 : exp.amountJPY
          return (
            <motion.div
              key={exp.id}
              whileHover={
                shouldReduceMotion
                  ? undefined
                  : { y: -4, scale: 1.02 }
              }
              transition={
                shouldReduceMotion
                  ? { duration: 0 }
                  : { type: "spring", stiffness: 90, damping: 22, mass: 1 }
              }
              className="p-3.5 rounded-2xl bg-stone-50 dark:bg-stone-900/60 border border-stone-200/60 dark:border-stone-800 flex items-center justify-between gap-3 text-xs shadow-sm hover:shadow-md transition-shadow cursor-default"
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-800 dark:text-emerald-400 shrink-0">
                  <Icon className="w-3.5 h-3.5" />
                </div>
                <div className="min-w-0">
                  <p className="font-semibold text-stone-900 dark:text-stone-100 truncate">
                    {language === "en" ? exp.titleEn : exp.title}
                  </p>
                  <p className="text-[11px] text-stone-500 dark:text-stone-400">
                    {language === "en" ? exp.categoryEn : exp.category} {splitFourWays && (language === "en" ? "· 4-Way Split" : "· 每人平攤")}
                  </p>
                </div>
              </div>
              <motion.span
                key={`${currency}-${splitFourWays}-${exp.id}`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.25 }}
                className="font-bold text-stone-900 dark:text-stone-100 shrink-0 text-right"
              >
                {config.symbol} {formatAmount(itemAmount)}
              </motion.span>
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}
