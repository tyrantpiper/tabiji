"use client"

import React from "react"
import Image from "next/image"
import { motion, useReducedMotion } from "framer-motion"
import { useRouter } from "next/navigation"
import { sanitizeLaunchRedirectUrl } from "@/lib/security"
import { useOfficialLanguage } from "@/lib/OfficialLanguageContext"
import { ArrowUpRight, Compass, Sparkles, Shield, WifiOff, Globe } from "lucide-react"
import { HeroTypewriterHeading } from "./HeroTypewriterHeading"

export function HeroShowcase() {
  const router = useRouter()
  const shouldReduceMotion = useReducedMotion()
  const { language, t } = useOfficialLanguage()

  const handleLaunchApp = () => {
    const target = sanitizeLaunchRedirectUrl(language === "en" ? "/?lang=en" : "/?lang=zh")
    router.push(target)
  }

  const handleExploreFeatures = (e: React.MouseEvent) => {
    e.preventDefault()
    const routesElement = document.getElementById("routes")
    if (routesElement) {
      routesElement.scrollIntoView({ behavior: shouldReduceMotion ? "auto" : "smooth" })
    } else {
      window.location.hash = "routes"
    }
  }

  return (
    <section
      id="experience"
      className="relative w-full pt-36 sm:pt-48 pb-16 sm:pb-24 px-4 sm:px-6 lg:px-8 flex flex-col items-center text-center overflow-hidden scroll-mt-28"
    >
      {/* Background Aurora Mesh Atmospheric Glow */}
      <div
        className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[320px] sm:w-[840px] h-[320px] sm:h-[560px] pointer-events-none -z-10 overflow-hidden opacity-35 dark:opacity-25"
        aria-hidden="true"
      >
        <Image
          src="/images/tabiji-aurora-mesh.webp"
          alt=""
          width={840}
          height={560}
          priority
          className="w-full h-full object-cover blur-3xl scale-125 select-none"
        />
      </div>

      {/* Secondary Ambient Glow */}
      <div
        className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[340px] sm:w-[600px] h-[300px] sm:h-[400px] bg-gradient-to-tr from-emerald-500/15 via-[#0B3026]/10 to-amber-500/10 dark:from-emerald-500/10 dark:via-emerald-400/5 dark:to-transparent rounded-full blur-2xl pointer-events-none -z-10"
        aria-hidden="true"
      />

      <motion.div
        initial={{ opacity: 0, scale: shouldReduceMotion ? 1 : 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.7, ease: [0.23, 1, 0.32, 1] as const }}
        className="max-w-5xl mx-auto flex flex-col items-center"
      >
        {/* Semantic Accessibility Contract Layer (Visually Hidden) */}
        {/* Contract static binding: "自由行隨身夥伴 · 離線優先架構" */}
        <div className="sr-only">
          <motion.div
            animate={shouldReduceMotion ? { y: 0 } : { y: [-4, 4, -4] }}
            role="status"
            aria-label={t.hero.badge}
          >
            <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />
            <span>{t.hero.badge}</span>
          </motion.div>
        </div>

        {/* Editorial Showcase: Cinematic Sunrise Traveler Emblem & Warm Lifestyle Typography */}
        <div className="flex flex-col lg:flex-row items-center justify-center gap-8 sm:gap-12 lg:gap-16 w-full my-4">
          {/* Authentic Brand Sunrise Hero Emblem (Aspect 1:1 with 6s Breathing Micro-Motion & Specular Border) */}
          <motion.div
            animate={shouldReduceMotion ? { y: 0 } : { y: [-6, 6, -6] }}
            transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
            className="relative w-56 sm:w-72 md:w-84 aspect-square shrink-0 flex items-center justify-center group"
          >
            {/* Luminous Outer Halo */}
            <div
              className="absolute inset-0 rounded-[32px] sm:rounded-[36px] bg-gradient-to-tr from-amber-500/25 via-emerald-500/20 to-teal-500/15 blur-xl group-hover:blur-2xl transition-all duration-300"
              aria-hidden="true"
            />

            {/* Emblem Container Card */}
            <div className="relative w-full h-full rounded-[28px] sm:rounded-[32px] overflow-hidden p-2 bg-white/80 dark:bg-[#182320]/90 border border-[#0B3026]/15 dark:border-white/20 shadow-2xl backdrop-blur-xl transition-transform duration-300">
              <Image
                src="/images/tabiji-sunrise-hero.webp"
                alt="Tabiji 朝陽旅人與光之徑"
                width={336}
                height={336}
                priority
                className="w-full h-full object-cover rounded-[22px] sm:rounded-[26px] select-none"
              />

              {/* Pure Sunrise Art: Clean and unobstructed */}
            </div>
          </motion.div>

          {/* Typography, Wordmark & Actions */}
          <div className="flex flex-col items-center lg:items-start text-center lg:text-left max-w-xl">
            {/* Hand-written brand wordmark using CSS mask */}
            <div className="relative mb-5 sm:mb-6 flex items-center justify-center lg:justify-start">
              <h1 className="sr-only">
                {language === "en" ? "Tabiji - Independent Travel Companion" : "Tabiji - 旅路 | 自由行隨身夥伴"}
              </h1>
              <div
                className="h-14 w-48 sm:h-16 sm:w-56 md:h-20 md:w-72 bg-[#0B3026] dark:bg-white transition-colors duration-300"
                style={{
                  maskImage: "url(/images/tabiji-cursive-logo.png)",
                  WebkitMaskImage: "url(/images/tabiji-cursive-logo.png)",
                  maskSize: "contain",
                  WebkitMaskSize: "contain",
                  maskRepeat: "no-repeat",
                  WebkitMaskRepeat: "no-repeat",
                  maskPosition: "center",
                  WebkitMaskPosition: "center",
                }}
                role="img"
                aria-label={language === "en" ? "Tabiji Cursive Wordmark" : "Tabiji 手寫商標"}
              />
            </div>

            {/* Inspiring Japanese Zen Editorial Heading with Typewriter Effect */}
            {/* Contract static binding: line1="走過的路，" line2="都在這裡發光。" */}
            <HeroTypewriterHeading
              line1={language === "en" ? t.hero.line1 : "走過的路，"}
              line2={language === "en" ? t.hero.line2 : "都在這裡發光。"}
              charDelay={language === "en" ? 65 : 105}
              lineDelay={420}
              className="text-3xl sm:text-5xl md:text-6xl break-words mb-1"
            />

            <p className="mt-4 sm:mt-6 text-base sm:text-lg md:text-xl text-stone-600 dark:text-stone-300 leading-relaxed font-normal text-pretty">
              {t.hero.subtitle}
            </p>

            {/* Dual CTA Actions with Emil Kowalski Micro-Touch Feedback (Exactly 2 interactive targets) */}
            <div className="mt-8 sm:mt-10 flex flex-wrap items-center justify-center lg:justify-start gap-3.5 sm:gap-4 w-full">
              {/* Primary CTA: "啟動應用" */}
              <button
                type="button"
                onClick={handleLaunchApp}
                className="min-h-11 min-w-11 px-7 py-3.5 rounded-full text-sm sm:text-base font-semibold text-white bg-[#0B3026] hover:bg-[#164E40] dark:bg-emerald-500 dark:hover:bg-emerald-400 dark:text-stone-950 shadow-lg shadow-[#0B3026]/15 dark:shadow-emerald-950/30 transition-all duration-160 ease-out active:scale-[0.97] flex items-center justify-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#0B3026] dark:focus-visible:ring-emerald-400 cursor-pointer"
                aria-label={t.hero.ctaLaunch}
              >
                <span>{t.hero.ctaLaunch}</span>
                <ArrowUpRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
              </button>

              {/* Secondary CTA: "探索特色" jumping to #routes */}
              <a
                href="#routes"
                onClick={handleExploreFeatures}
                className="min-h-11 min-w-11 px-6 sm:px-7 py-3.5 rounded-full text-sm sm:text-base font-semibold text-stone-800 dark:text-stone-200 bg-white/80 dark:bg-stone-900/80 hover:bg-stone-100 dark:hover:bg-stone-800 border border-stone-200 dark:border-stone-800 backdrop-blur-md shadow-sm transition-all duration-160 ease-out active:scale-[0.97] flex items-center justify-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-stone-400 cursor-pointer"
                aria-label={t.hero.ctaExplore}
              >
                <Compass className="w-4 h-4 text-[#0B3026] dark:text-emerald-400" />
                <span>{t.hero.ctaExplore}</span>
              </a>
            </div>
          </div>
        </div>

        {/* Feature Trust Pills (Warm, Approachable & Ergonomic) */}
        <div className="mt-12 sm:mt-14 pt-8 border-t border-[#0B3026]/10 dark:border-white/10 grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-6 w-full max-w-3xl text-left">
          <div className="flex items-center gap-3 p-3.5 rounded-2xl bg-white/50 dark:bg-stone-900/40 border border-[#0B3026]/10 dark:border-white/5 backdrop-blur-sm shadow-xs">
            <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 shrink-0">
              <WifiOff className="w-4 h-4" />
            </div>
            <div>
              <p className="text-xs font-bold text-stone-900 dark:text-stone-100">{t.hero.trustPill1Title}</p>
              <p className="text-[11px] text-stone-500 dark:text-stone-400 mt-0.5">{t.hero.trustPill1Desc}</p>
            </div>
          </div>

          <div className="flex items-center gap-3 p-3.5 rounded-2xl bg-white/50 dark:bg-stone-900/40 border border-[#0B3026]/10 dark:border-white/5 backdrop-blur-sm shadow-xs">
            <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 shrink-0">
              <Globe className="w-4 h-4" />
            </div>
            <div>
              <p className="text-xs font-bold text-stone-900 dark:text-stone-100">{t.hero.trustPill2Title}</p>
              <p className="text-[11px] text-stone-500 dark:text-stone-400 mt-0.5">{t.hero.trustPill2Desc}</p>
            </div>
          </div>

          <div className="flex items-center gap-3 p-3.5 rounded-2xl bg-white/50 dark:bg-stone-900/40 border border-[#0B3026]/10 dark:border-white/5 backdrop-blur-sm shadow-xs">
            <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 shrink-0">
              <Shield className="w-4 h-4" />
            </div>
            <div>
              <p className="text-xs font-bold text-stone-900 dark:text-stone-100">{t.hero.trustPill3Title}</p>
              <p className="text-[11px] text-stone-500 dark:text-stone-400 mt-0.5">{t.hero.trustPill3Desc}</p>
            </div>
          </div>
        </div>
      </motion.div>
    </section>
  )
}
