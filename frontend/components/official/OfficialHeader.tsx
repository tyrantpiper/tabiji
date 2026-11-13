"use client"

import React, { useState, useEffect, useRef } from "react"
import Link from "next/link"
import { useRouter, usePathname } from "next/navigation"
import { motion } from "framer-motion"
import { sanitizeLaunchRedirectUrl } from "@/lib/security"
import { useOfficialLanguage } from "@/lib/OfficialLanguageContext"
import { Menu, X, ArrowUpRight } from "lucide-react"

export function OfficialHeader() {
  const router = useRouter()
  const pathname = usePathname()
  const { language, setLanguage, t } = useOfficialLanguage()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const [activeSection, setActiveSection] = useState<string | null>("experience")
  const isManualScrollingRef = useRef(false)
  const manualScrollTimerRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    return () => {
      if (manualScrollTimerRef.current) {
        clearTimeout(manualScrollTimerRef.current)
      }
    }
  }, [])

  const isPortalHome = pathname === "/official" || pathname === "/official/"
  const currentLegalSection = !isPortalHome
    ? pathname?.includes("/terms")
      ? "terms"
      : pathname?.includes("/privacy")
      ? "privacy"
      : null
    : null
  const effectiveActiveSection = currentLegalSection ?? activeSection

  useEffect(() => {
    const handleScroll = () => {
      const currentScroll =
        (typeof window !== "undefined" ? window.scrollY : 0) ||
        (typeof document !== "undefined" && document.documentElement ? document.documentElement.scrollTop : 0) ||
        (typeof document !== "undefined" && document.body ? document.body.scrollTop : 0) ||
        0
      setScrolled(currentScroll > 20)
      if (currentScroll < 350 && !isManualScrollingRef.current) {
        setActiveSection("experience")
      }
    }

    handleScroll()
    window.addEventListener("scroll", handleScroll, { passive: true, capture: true })
    document.addEventListener("scroll", handleScroll, { passive: true })
    return () => {
      window.removeEventListener("scroll", handleScroll, { capture: true })
      document.removeEventListener("scroll", handleScroll)
    }
  }, [])

  // Smooth scroll compensation for direct hash navigation on mount
  useEffect(() => {
    if (!isPortalHome || typeof window === "undefined") return
    const hash = window.location.hash.replace("#", "")
    if (hash && ["experience", "routes", "offline", "ledger"].includes(hash)) {
      const timer = setTimeout(() => {
        setActiveSection(hash)
        const el = document.getElementById(hash)
        if (el) {
          const topOffset = 84
          const elementPosition = el.getBoundingClientRect().top
          const currentScroll =
            (window.scrollY || document.documentElement?.scrollTop || document.body?.scrollTop || 0)
          const offsetPosition = Math.max(0, elementPosition + currentScroll - topOffset)
          const prefersReducedMotion =
            typeof window.matchMedia === "function" &&
            window.matchMedia("(prefers-reduced-motion: reduce)").matches
          const scrollConfig: ScrollToOptions = {
            top: offsetPosition,
            behavior: prefersReducedMotion ? "auto" : "smooth",
          }
          if (typeof window.scrollTo === "function") window.scrollTo(scrollConfig)
          if (document.documentElement && typeof document.documentElement.scrollTo === "function") {
            document.documentElement.scrollTo(scrollConfig)
          }
          if (document.body && typeof document.body.scrollTo === "function") {
            document.body.scrollTo(scrollConfig)
          }
          setScrolled(offsetPosition > 20)
        }
      }, 100)
      return () => clearTimeout(timer)
    }
  }, [isPortalHome])

  // ScrollSpy with IntersectionObserver on Portal Root
  useEffect(() => {
    if (!isPortalHome) {
      return
    }

    if (typeof window === "undefined" || typeof IntersectionObserver === "undefined") {
      return
    }

    const sectionIds = ["experience", "routes", "offline", "ledger"]
    const observer = new IntersectionObserver(
      (entries) => {
        if (isManualScrollingRef.current) {
          return
        }
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id)
          }
        })
      },
      {
        rootMargin: "-20% 0px -55% 0px",
        threshold: 0.1,
      }
    )

    sectionIds.forEach((id) => {
      const el = document.getElementById(id)
      if (el) observer.observe(el)
    })

    return () => observer.disconnect()
  }, [isPortalHome])

  const handleLaunchApp = (e?: React.MouseEvent) => {
    if (e) e.preventDefault()
    const target = sanitizeLaunchRedirectUrl(language === "en" ? "/?lang=en" : "/?lang=zh")
    router.push(target)
  }

  const navLinks = [
    { name: language === "en" ? t.nav.experience : "行旅體驗", href: "/official#experience", id: "experience" },
    { name: language === "en" ? t.nav.routes : "航線巡航", href: "/official#routes", id: "routes" },
    { name: language === "en" ? t.nav.offline : "離線引擎", href: "/official#offline", id: "offline" },
    { name: language === "en" ? t.nav.ledger : "智慧分帳", href: "/official#ledger", id: "ledger" },
  ]

  const handleNavClick = (
    e: React.MouseEvent<HTMLAnchorElement>,
    link: (typeof navLinks)[number]
  ) => {
    if (isPortalHome && link.href.includes("#")) {
      e.preventDefault()
      isManualScrollingRef.current = true
      setActiveSection(link.id)
      if (manualScrollTimerRef.current) {
        clearTimeout(manualScrollTimerRef.current)
      }
      manualScrollTimerRef.current = setTimeout(() => {
        isManualScrollingRef.current = false
      }, 900)

      const el = document.getElementById(link.id)
      if (el) {
        const topOffset = 84
        const elementPosition = el.getBoundingClientRect().top
        const currentScroll =
          (typeof window !== "undefined" ? window.scrollY : 0) ||
          (typeof document !== "undefined" && document.documentElement ? document.documentElement.scrollTop : 0) ||
          (typeof document !== "undefined" && document.body ? document.body.scrollTop : 0) ||
          0
        const offsetPosition = Math.max(0, elementPosition + currentScroll - topOffset)

        if (typeof window !== "undefined") {
          const prefersReducedMotion =
            typeof window.matchMedia === "function" &&
            window.matchMedia("(prefers-reduced-motion: reduce)").matches
          const scrollConfig: ScrollToOptions = {
            top: offsetPosition,
            behavior: prefersReducedMotion ? "auto" : "smooth",
          }

          if (typeof window.scrollTo === "function") {
            window.scrollTo(scrollConfig)
          }
          if (document.documentElement && typeof document.documentElement.scrollTo === "function") {
            document.documentElement.scrollTo(scrollConfig)
          }
          if (document.body && typeof document.body.scrollTo === "function") {
            document.body.scrollTo(scrollConfig)
          }
          setScrolled(offsetPosition > 20)
        }
        if (
          typeof window !== "undefined" &&
          window.history &&
          typeof window.history.pushState === "function"
        ) {
          window.history.pushState(null, "", `#${link.id}`)
        }
      }
    }
  }

  return (
    <header className="fixed top-3 sm:top-5 left-1/2 -translate-x-1/2 z-50 w-[calc(100%-1.5rem)] max-w-6xl">
      <nav
        aria-label={language === "en" ? "Official Portal Navigation Bar" : "官方網站導覽列"}
        className={`w-full rounded-full border transition-all duration-300 backdrop-blur-2xl ${
          scrolled
            ? "bg-white/85 dark:bg-[#121A18]/90 border-[#0B3026]/15 dark:border-white/15 shadow-xl shadow-black/5 dark:shadow-black/25 py-2.5 px-4 sm:px-6"
            : "bg-white/70 dark:bg-[#121A18]/75 border-[#0B3026]/10 dark:border-white/10 shadow-lg shadow-black/5 dark:shadow-black/20 py-3 px-4 sm:px-6"
        } flex items-center justify-between`}
      >
        {/* Composite Brand Logo: Aluminum Person Totem + Cursive Wordmark */}
        <Link
          href="/official"
          className="min-h-11 min-w-11 flex items-center gap-2 sm:gap-2.5 group focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B3026] dark:focus-visible:ring-emerald-400 rounded-lg py-1"
          aria-label={t.nav.homeAria}
        >
          {/* Aluminum Person Totem */}
          <div
            className="h-8 w-8 bg-[#0B3026] dark:bg-stone-100 transition-colors duration-300 shrink-0"
            style={{
              maskImage: "url(/images/tabiji-person-outline.png?v=3)",
              WebkitMaskImage: "url(/images/tabiji-person-outline.png?v=3)",
              maskSize: "contain",
              WebkitMaskSize: "contain",
              maskRepeat: "no-repeat",
              WebkitMaskRepeat: "no-repeat",
              maskPosition: "center",
              WebkitMaskPosition: "center",
            }}
            role="img"
            aria-label="Tabiji Traveler Emblem"
          />
          {/* Cursive Wordmark (Retaining h-8 w-24 for test assertions) */}
          <div
            className="h-8 w-24 sm:h-9 sm:w-28 bg-[#0B3026] dark:bg-white transition-colors duration-300"
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
            aria-label="Tabiji Logo"
          />
        </Link>

        {/* Desktop Anchor Navigation Links */}
        <div className="hidden lg:flex items-center gap-1 xl:gap-2">
          {navLinks.map((link) => (
            <Link
              key={link.name}
              href={link.href}
              onClick={(e) => handleNavClick(e, link)}
              className="min-h-11 min-w-11 px-3 py-2 text-sm font-medium text-stone-700 dark:text-stone-300 hover:text-[#0B3026] dark:hover:text-white rounded-full transition-colors duration-160 flex items-center justify-center focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B3026] dark:focus-visible:ring-emerald-400 relative"
            >
              {effectiveActiveSection === link.id && (
                <motion.span
                  layoutId="active-scrollspy-pill"
                  className="absolute inset-0 rounded-full bg-[#0B3026] dark:bg-emerald-400 shadow-sm -z-10"
                  transition={{
                    type: "spring",
                    stiffness: 380,
                    damping: 30,
                  }}
                />
              )}
              <span className={effectiveActiveSection === link.id ? "text-white dark:text-stone-950 font-bold" : ""}>
                {link.name}
              </span>
            </Link>
          ))}
        </div>

        {/* Action Button & Mobile Menu Toggle */}
        <div className="flex items-center gap-2 sm:gap-3">
          {/* Desktop Bilingual Switcher Capsule (繁中 | EN) - Hidden on mobile (<640px) to prevent navbar overflow blowout */}
          <div
            className="hidden sm:inline-flex items-center p-0.5 rounded-full border border-[#0B3026]/15 dark:border-white/15 bg-stone-100/60 dark:bg-stone-800/60 backdrop-blur-sm text-xs font-medium"
            role="group"
            aria-label={t.langSwitcher.ariaLabel}
          >
            <button
              type="button"
              onClick={() => setLanguage("zh")}
              className={`min-h-11 min-w-11 px-3 rounded-full text-xs font-semibold transition-all duration-160 ease-out active:scale-[0.96] flex items-center justify-center cursor-pointer relative ${
                language === "zh"
                  ? "text-stone-900 dark:text-stone-900 font-bold"
                  : "text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-200"
              }`}
              aria-label="切換為繁體中文"
              aria-pressed={language === "zh"}
            >
              {language === "zh" && (
                <motion.span
                  layoutId="official-lang-pill"
                  className="absolute inset-0 rounded-full bg-white dark:bg-emerald-400 shadow-xs -z-10"
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
              <span>{t.langSwitcher.zh}</span>
            </button>
            <button
              type="button"
              onClick={() => setLanguage("en")}
              className={`min-h-11 min-w-11 px-3 rounded-full text-xs font-semibold transition-all duration-160 ease-out active:scale-[0.96] flex items-center justify-center cursor-pointer relative ${
                language === "en"
                  ? "text-stone-900 dark:text-stone-900 font-bold"
                  : "text-stone-600 dark:text-stone-400 hover:text-stone-900 dark:hover:text-stone-200"
              }`}
              aria-label="Switch to English"
              aria-pressed={language === "en"}
            >
              {language === "en" && (
                <motion.span
                  layoutId="official-lang-pill"
                  className="absolute inset-0 rounded-full bg-white dark:bg-emerald-400 shadow-xs -z-10"
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
              <span>{t.langSwitcher.en}</span>
            </button>
          </div>

          {/* Emil Kowalski CTA Button: active:scale-[0.97] + 160ms ease-out */}
          <button
            type="button"
            onClick={handleLaunchApp}
            className="min-h-11 min-w-11 px-4 sm:px-5 py-2.5 rounded-full text-xs sm:text-sm font-semibold text-white bg-[#0B3026] hover:bg-[#164E40] dark:bg-emerald-500 dark:hover:bg-emerald-400 dark:text-stone-950 shadow-sm transition-all duration-160 ease-out active:scale-[0.97] flex items-center gap-1.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#0B3026] dark:focus-visible:ring-emerald-400 cursor-pointer"
            aria-label={t.nav.launchApp}
          >
            <span>{t.nav.launchApp}</span>
            <ArrowUpRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </button>

          {/* Mobile Hamburger Button */}
          <button
            type="button"
            onClick={() => setMobileMenuOpen((prev) => !prev)}
            className="lg:hidden min-h-11 min-w-11 p-2 rounded-full text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors duration-160 flex items-center justify-center focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B3026] dark:focus-visible:ring-emerald-400 cursor-pointer"
            aria-label={mobileMenuOpen ? t.nav.closeMenu : t.nav.openMenu}
            aria-expanded={mobileMenuOpen}
          >
            {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </nav>

      {/* Mobile Menu Dropdown with Glassmorphism */}
      {mobileMenuOpen && (
        <div className="lg:hidden mt-2 w-full rounded-3xl backdrop-blur-2xl bg-white/90 dark:bg-[#121A18]/95 border border-[#0B3026]/10 dark:border-white/10 shadow-2xl p-4 transition-all duration-200">
          <div className="flex flex-col gap-1">
            {navLinks.map((link) => (
              <Link
                key={link.name}
                href={link.href}
                onClick={(e) => {
                  handleNavClick(e, link)
                  setMobileMenuOpen(false)
                }}
                className={`min-h-11 px-4 py-3 rounded-2xl text-sm font-medium transition-colors duration-160 flex items-center justify-between ${
                  effectiveActiveSection === link.id
                    ? "bg-[#0B3026] text-white dark:bg-emerald-500 dark:text-stone-950 font-bold"
                    : "text-stone-800 dark:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-800/60"
                }`}
              >
                <span>{link.name}</span>
                {effectiveActiveSection === link.id && (
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                )}
              </Link>
            ))}

            {/* Mobile Language Switcher */}
            <div className="flex items-center justify-between px-3 py-2 mt-2 pt-2 border-t border-stone-200/60 dark:border-stone-800">
              <span className="text-xs font-medium text-stone-500 dark:text-stone-400">
                {language === "en" ? "Language" : "介面語言"}
              </span>
              <div
                className="inline-flex items-center p-0.5 rounded-full border border-[#0B3026]/15 dark:border-white/15 bg-stone-100/60 dark:bg-stone-800/60 backdrop-blur-sm text-xs font-medium"
                role="group"
                aria-label={t.langSwitcher.ariaLabel}
              >
                <button
                  type="button"
                  onClick={() => setLanguage("zh")}
                  className={`min-h-11 min-w-11 px-3.5 rounded-full text-xs font-semibold transition-all duration-160 ease-out active:scale-[0.96] flex items-center justify-center cursor-pointer relative ${
                    language === "zh"
                      ? "text-stone-900 dark:text-stone-900 font-bold"
                      : "text-stone-600 dark:text-stone-400"
                  }`}
                  aria-label="切換為繁體中文"
                  aria-pressed={language === "zh"}
                >
                  {language === "zh" && (
                    <motion.span
                      layoutId="official-lang-pill-mobile"
                      className="absolute inset-0 rounded-full bg-white dark:bg-emerald-400 shadow-xs -z-10"
                      transition={{ type: "spring", stiffness: 400, damping: 30 }}
                    />
                  )}
                  <span>{t.langSwitcher.zh}</span>
                </button>
                <button
                  type="button"
                  onClick={() => setLanguage("en")}
                  className={`min-h-11 min-w-11 px-3.5 rounded-full text-xs font-semibold transition-all duration-160 ease-out active:scale-[0.96] flex items-center justify-center cursor-pointer relative ${
                    language === "en"
                      ? "text-stone-900 dark:text-stone-900 font-bold"
                      : "text-stone-600 dark:text-stone-400"
                  }`}
                  aria-label="Switch to English"
                  aria-pressed={language === "en"}
                >
                  {language === "en" && (
                    <motion.span
                      layoutId="official-lang-pill-mobile"
                      className="absolute inset-0 rounded-full bg-white dark:bg-emerald-400 shadow-xs -z-10"
                      transition={{ type: "spring", stiffness: 400, damping: 30 }}
                    />
                  )}
                  <span>{t.langSwitcher.en}</span>
                </button>
              </div>
            </div>

            <div className="pt-2 border-t border-stone-200 dark:border-stone-800 mt-1">
              <button
                type="button"
                onClick={(e) => {
                  setMobileMenuOpen(false)
                  handleLaunchApp(e)
                }}
                className="w-full min-h-11 py-3 px-4 rounded-2xl text-sm font-semibold text-white bg-[#0B3026] hover:bg-[#164E40] dark:bg-emerald-500 dark:text-stone-950 shadow-md transition-all duration-160 ease-out active:scale-[0.97] flex items-center justify-center gap-2 cursor-pointer"
                aria-label={t.nav.launchAppLong}
              >
                <span>{t.nav.launchAppLong}</span>
                <ArrowUpRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  )
}
