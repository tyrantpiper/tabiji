"use client"

import React from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { OfficialHeader } from "@/components/official/OfficialHeader"
import { HeroShowcase } from "@/components/official/HeroShowcase"
import { LiveDeviceTheater } from "@/components/official/LiveDeviceTheater"
import { BentoMotionGrid } from "@/components/official/BentoMotionGrid"
import { OfficialFooter } from "@/components/official/OfficialFooter"
import { sanitizeLaunchRedirectUrl } from "@/lib/security"
import { useOfficialLanguage } from "@/lib/OfficialLanguageContext"
import {
  ArrowUpRight,
  ShieldCheck,
  WifiOff,
  Lock,
  CheckCircle,
  FileText,
  Coins,
} from "lucide-react"

export default function OfficialPage() {
  const router = useRouter()
  const { language, t } = useOfficialLanguage()

  const handleLaunchApp = () => {
    const target = sanitizeLaunchRedirectUrl(language === "en" ? "/?lang=en" : "/?lang=zh")
    router.push(target)
  }

  return (
    <div className="relative min-h-screen w-full overflow-x-hidden bg-[#F6F5EE] text-[#1E2927] dark:bg-[#121A18] dark:text-[#E5EBEA] transition-colors duration-300">
      {/* 1. Glassmorphism Floating Header */}
      <OfficialHeader />

      {/* Main Content Area */}
      <main className="w-full flex flex-col items-center">
        {/* 2. Brand Hero Showcase with Spring Badge & Masked Wordmark */}
        <HeroShowcase />

        {/* 2.5. Real Smartphone Device Theater (Apple iPhone 15 Pro PWA Showcase) */}
        <LiveDeviceTheater />

        {/* 3. Three Live Motion Bento Grid (#routes, #offline, #ledger) */}
        <BentoMotionGrid />

        {/* 4. Architecture & Engineering Highlights */}
        <section
          className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 sm:py-24 border-t border-[#0B3026]/10 dark:border-white/10"
          aria-label={language === "en" ? "Core Travel Philosophy & Architecture" : "純粹初衷與技術哲學"}
        >
          <div className="text-center max-w-3xl mx-auto mb-12 sm:mb-16">
            <span className="text-xs font-semibold uppercase tracking-wider text-emerald-800 dark:text-emerald-400">
              {t.craft.badge}
            </span>
            <h2 className="text-2xl sm:text-4xl font-extrabold tracking-tight text-stone-900 dark:text-stone-50 mt-2">
              {t.craft.heading}
            </h2>
            <p className="mt-3 text-sm sm:text-base text-stone-600 dark:text-stone-300 leading-relaxed font-normal">
              {t.craft.subtitle}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {/* Pillar 1: Offline First */}
            <div className="p-6 sm:p-7 rounded-3xl bg-white/70 dark:bg-[#182320]/80 border border-[#0B3026]/10 dark:border-white/10 backdrop-blur-md shadow-xs flex flex-col justify-between">
              <div>
                <div className="p-3 rounded-2xl bg-emerald-500/10 text-emerald-800 dark:text-emerald-400 w-fit mb-4">
                  <WifiOff className="w-5 h-5" />
                </div>
                <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-400 mb-1">
                  {t.craft.pillars[0].num}
                </div>
                <h3 className="text-base font-bold text-stone-900 dark:text-stone-100 mb-2">
                  {t.craft.pillars[0].title}
                </h3>
                <p className="text-xs sm:text-sm text-stone-600 dark:text-stone-400 leading-relaxed">
                  {t.craft.pillars[0].desc}
                </p>
              </div>
            </div>

            {/* Pillar 2: Smart Currency Split */}
            <div className="p-6 sm:p-7 rounded-3xl bg-white/70 dark:bg-[#182320]/80 border border-[#0B3026]/10 dark:border-white/10 backdrop-blur-md shadow-xs flex flex-col justify-between">
              <div>
                <div className="p-3 rounded-2xl bg-emerald-500/10 text-emerald-800 dark:text-emerald-400 w-fit mb-4">
                  <Coins className="w-5 h-5" />
                </div>
                <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-400 mb-1">
                  {t.craft.pillars[1].num}
                </div>
                <h3 className="text-base font-bold text-stone-900 dark:text-stone-100 mb-2">
                  {t.craft.pillars[1].title}
                </h3>
                <p className="text-xs sm:text-sm text-stone-600 dark:text-stone-400 leading-relaxed">
                  {t.craft.pillars[1].desc}
                </p>
              </div>
            </div>

            {/* Pillar 3: Privacy by Design */}
            <div className="p-6 sm:p-7 rounded-3xl bg-white/70 dark:bg-[#182320]/80 border border-[#0B3026]/10 dark:border-white/10 backdrop-blur-md shadow-xs flex flex-col justify-between">
              <div>
                <div className="p-3 rounded-2xl bg-emerald-500/10 text-emerald-800 dark:text-emerald-400 w-fit mb-4">
                  <Lock className="w-5 h-5" />
                </div>
                <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-400 mb-1">
                  {t.craft.pillars[2].num}
                </div>
                <h3 className="text-base font-bold text-stone-900 dark:text-stone-100 mb-2">
                  {t.craft.pillars[2].title}
                </h3>
                <p className="text-xs sm:text-sm text-stone-600 dark:text-stone-400 leading-relaxed">
                  {t.craft.pillars[2].desc}
                </p>
              </div>
            </div>

            {/* Pillar 4: Transparent Trust */}
            <div className="p-6 sm:p-7 rounded-3xl bg-white/70 dark:bg-[#182320]/80 border border-[#0B3026]/10 dark:border-white/10 backdrop-blur-md shadow-xs flex flex-col justify-between">
              <div>
                <div className="p-3 rounded-2xl bg-emerald-500/10 text-emerald-800 dark:text-emerald-400 w-fit mb-4">
                  <ShieldCheck className="w-5 h-5" />
                </div>
                <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-400 mb-1">
                  {t.craft.pillars[3].num}
                </div>
                <h3 className="text-base font-bold text-stone-900 dark:text-stone-100 mb-2">
                  {t.craft.pillars[3].title}
                </h3>
                <p className="text-xs sm:text-sm text-stone-600 dark:text-stone-400 leading-relaxed">
                  {t.craft.pillars[3].desc}
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* 5. Launch CTA Action Banner */}
        <section
          className="w-full max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-16 sm:py-24"
          aria-label={language === "en" ? "Launch Tabiji App Now" : "立即啟動 Tabiji 應用"}
        >
          <div className="relative rounded-3xl p-8 sm:p-12 bg-gradient-to-br from-[#0B3026] via-[#123E33] to-[#164E40] text-white shadow-2xl overflow-hidden flex flex-col md:flex-row items-center justify-between gap-8">
            {/* Background Decorative Rings */}
            <div
              className="absolute -right-20 -bottom-20 w-80 h-80 rounded-full border border-white/10 pointer-events-none"
              aria-hidden="true"
            />
            <div
              className="absolute -right-10 -bottom-10 w-60 h-60 rounded-full border border-white/10 pointer-events-none"
              aria-hidden="true"
            />

            <div className="max-w-xl text-center md:text-left z-10">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-400/20 text-emerald-200 border border-emerald-400/30 mb-4">
                <CheckCircle className="w-3.5 h-3.5" />
                <span>{t.cta.badge}</span>
              </div>
              <h2 className="text-2xl sm:text-4xl font-extrabold tracking-tight leading-tight">
                {t.cta.heading}
              </h2>
              <p className="mt-3 text-sm sm:text-base text-emerald-100/90 leading-relaxed font-normal">
                {t.cta.subtitle}
              </p>
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-3 z-10 w-full sm:w-auto">
              <button
                type="button"
                onClick={handleLaunchApp}
                className="w-full sm:w-auto min-h-[44px] min-w-[44px] px-8 py-3.5 rounded-full text-sm sm:text-base font-bold text-[#0B3026] bg-white hover:bg-emerald-50 shadow-lg shadow-black/20 transition-all duration-160 ease-out active:scale-[0.97] flex items-center justify-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-white cursor-pointer"
                aria-label={t.cta.launchAria}
              >
                <span>{t.cta.launch}</span>
                <ArrowUpRight className="w-4 h-4" />
              </button>

              <Link
                href="/official/terms"
                className="w-full sm:w-auto min-h-[44px] min-w-[44px] px-6 py-3.5 rounded-full text-sm font-medium text-emerald-100 hover:text-white bg-white/10 hover:bg-white/15 border border-white/15 transition-all duration-160 ease-out active:scale-[0.97] flex items-center justify-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-white"
                aria-label={t.cta.termsAria}
              >
                <FileText className="w-4 h-4" />
                <span>{t.cta.terms}</span>
              </Link>
            </div>
          </div>
        </section>
      </main>

      {/* 6. Official Footer with Legal Center Links */}
      <OfficialFooter />
    </div>
  )
}

