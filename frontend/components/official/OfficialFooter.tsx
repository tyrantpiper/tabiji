"use client"

import React from "react"
import Link from "next/link"
import { useOfficialLanguage } from "@/lib/OfficialLanguageContext"

export function OfficialFooter() {
  const { t, language } = useOfficialLanguage()

  return (
    <footer className="w-full border-t border-[#0B3026]/10 dark:border-white/10 bg-[#F6F5EE]/80 dark:bg-[#121A18]/90 transition-colors duration-300">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12 lg:py-16">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8 lg:gap-12">
          {/* Brand Column */}
          <div className="md:col-span-2 flex flex-col items-start gap-4">
            <Link
              href="/official"
              className="flex items-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B3026] dark:focus-visible:ring-emerald-400 rounded-lg"
              aria-label={t.nav.homeAria}
            >
              <div
                className="h-8 w-28 bg-[#0B3026] dark:bg-white transition-colors duration-300"
                style={{
                  maskImage: "url(/images/tabiji-cursive-logo.png)",
                  WebkitMaskImage: "url(/images/tabiji-cursive-logo.png)",
                  maskSize: "contain",
                  WebkitMaskSize: "contain",
                  maskRepeat: "no-repeat",
                  WebkitMaskRepeat: "no-repeat",
                  maskPosition: "left center",
                  WebkitMaskPosition: "left center",
                }}
                role="img"
                aria-label="Tabiji Logo"
              />
            </Link>
            <p className="text-sm text-stone-600 dark:text-stone-400 max-w-md leading-relaxed">
              {t.footer.desc}
            </p>
          </div>

          {/* Navigation Column (Strictly 3 links to keep ADV-M2-3.9 green at exactly 6 total text links) */}
          <div className="flex flex-col gap-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-stone-900 dark:text-stone-200">
              {t.footer.navTitle}
            </h4>
            <nav className="flex flex-col gap-1" aria-label={t.footer.navTitle}>
              <Link
                href="/official#routes"
                className="min-h-11 py-2.5 text-sm text-stone-600 dark:text-stone-400 hover:text-[#0B3026] dark:hover:text-emerald-400 transition-colors flex items-center"
              >
                {t.footer.routes}
              </Link>
              <Link
                href="/official#offline"
                className="min-h-11 py-2.5 text-sm text-stone-600 dark:text-stone-400 hover:text-[#0B3026] dark:hover:text-emerald-400 transition-colors flex items-center"
              >
                {t.footer.offline}
              </Link>
              <Link
                href="/official#ledger"
                className="min-h-11 py-2.5 text-sm text-stone-600 dark:text-stone-400 hover:text-[#0B3026] dark:hover:text-emerald-400 transition-colors flex items-center"
              >
                {t.footer.ledger}
              </Link>
            </nav>
          </div>

          {/* Legal Armor Column (3 links) */}
          <div className="flex flex-col gap-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-stone-900 dark:text-stone-200">
              {t.footer.legalTitle}
            </h4>
            <nav className="flex flex-col gap-1" aria-label={t.footer.legalTitle}>
              <Link
                href="/official/terms"
                className="min-h-11 py-2.5 text-sm text-stone-600 dark:text-stone-400 hover:text-[#0B3026] dark:hover:text-emerald-400 transition-colors flex items-center"
              >
                {/* 服務條款 */}
                {t.footer.terms}
              </Link>
              <Link
                href="/official/privacy"
                className="min-h-11 py-2.5 text-sm text-stone-600 dark:text-stone-400 hover:text-[#0B3026] dark:hover:text-emerald-400 transition-colors flex items-center"
              >
                {/* 隱私權政策 Privacy Policy */}
                {t.footer.privacy}
              </Link>
              <Link
                href={language === "en" ? "/?lang=en" : "/?lang=zh"}
                className="min-h-11 py-2.5 text-sm text-stone-600 dark:text-stone-400 hover:text-[#0B3026] dark:hover:text-emerald-400 transition-colors flex items-center"
              >
                {t.footer.backApp}
              </Link>
            </nav>
          </div>
        </div>

        {/* Disclaimer & Copyright */}
        <div className="mt-12 pt-8 border-t border-[#0B3026]/10 dark:border-white/10 flex flex-col md:flex-row items-center justify-between gap-4 text-xs text-stone-500 dark:text-stone-400">
          <p className="leading-relaxed text-center md:text-left max-w-2xl">
            {/* 旅遊協調 */}
            {t.footer.disclaimer}
          </p>
          <p className="shrink-0 font-medium">
            {/* © 2026 Tabiji (旅路). All rights reserved. */}
            {t.footer.copyright}
          </p>
        </div>
      </div>
    </footer>
  )
}
