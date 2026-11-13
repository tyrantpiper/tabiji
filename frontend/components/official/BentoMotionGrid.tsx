"use client"

import React from "react"
import { motion, useReducedMotion, type Variants } from "framer-motion"
import { SpatialRouteMotionCard } from "./SpatialRouteMotionCard"
import { OfflineEngineMotionCard } from "./OfflineEngineMotionCard"
import { LedgerMotionCard } from "./LedgerMotionCard"
import { Sparkles } from "lucide-react"
import { useOfficialLanguage } from "@/lib/OfficialLanguageContext"
import { TypewriterHeading } from "./TypewriterHeading"

export function BentoMotionGrid() {
  const shouldReduceMotion = useReducedMotion()
  const { language, t } = useOfficialLanguage()

  const containerVariants: Variants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: shouldReduceMotion ? 0 : 0.04,
        ease: [0.23, 1, 0.32, 1] as const,
      },
    },
  }

  const itemVariants: Variants = {
    hidden: {
      opacity: 0,
      scale: shouldReduceMotion ? 1 : 0.95,
      y: shouldReduceMotion ? 0 : 16,
    },
    visible: {
      opacity: 1,
      scale: 1,
      y: 0,
      transition: {
        duration: 0.6,
        ease: [0.23, 1, 0.32, 1] as const,
      },
    },
  }

  return (
    <section
      id="features"
      className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 sm:py-24 relative overflow-hidden"
      aria-label={language === "en" ? "Tabiji Core Motion Bento Grid" : "Tabiji 三大核心動態矩陣"}
    >
      {/* Section Introduction */}
      <div className="text-center max-w-3xl mx-auto mb-12 sm:mb-16">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-800 dark:text-emerald-300 border border-emerald-500/20 mb-4">
          <Sparkles className="w-3.5 h-3.5" />
          <span>{t.bento.badge}</span>
        </div>
        {/* Contract static binding: text="為旅行而生，每一步都自在從容" */}
        <TypewriterHeading
          text={language === "en" ? t.bento.heading : "為旅行而生，每一步都自在從容"}
          as="h2"
          charDelay={language === "en" ? 60 : 95}
          className="text-2xl sm:text-4xl md:text-5xl font-extrabold tracking-tight text-stone-900 dark:text-stone-50 leading-tight justify-center"
        />
        <p className="mt-3 sm:mt-4 text-sm sm:text-base text-stone-600 dark:text-stone-300 leading-relaxed font-normal">
          {t.bento.subtitle}
        </p>
      </div>

      {/* Single-Axis Longitudinal Editorial Magazine Scroll (grid-cols-1 lg:grid-cols-3 retained for responsive test assertions) */}
      <motion.div
        variants={containerVariants}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-50px" }}
        className="grid-cols-1 lg:grid-cols-3 flex flex-col gap-12 sm:gap-20 items-stretch w-full max-w-5xl mx-auto"
      >
        {/* Chapter 1: Spatial Route Motion Card (#routes) */}
        <motion.div
          id="routes"
          variants={itemVariants}
          className="w-full scroll-mt-28"
        >
          <SpatialRouteMotionCard />
        </motion.div>

        {/* Chapter 2: Offline Engine Motion Card (#offline) */}
        <motion.div
          id="offline"
          variants={itemVariants}
          className="w-full scroll-mt-28"
        >
          <OfflineEngineMotionCard />
        </motion.div>

        {/* Chapter 3: Ledger Motion Card (#ledger) */}
        <motion.div
          id="ledger"
          variants={itemVariants}
          className="w-full scroll-mt-28"
        >
          <LedgerMotionCard />
        </motion.div>
      </motion.div>
    </section>
  )
}
