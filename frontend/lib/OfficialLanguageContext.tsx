"use client"

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
} from "react"
import {
  type OfficialLanguage,
  type OfficialTranslations,
  officialTranslations,
} from "./official-translations"

export const OFFICIAL_PORTAL_LANG_KEY = "tabiji_official_portal_lang"

export interface OfficialLanguageContextValue {
  language: OfficialLanguage
  setLanguage: (lang: OfficialLanguage) => void
  t: OfficialTranslations
}

const defaultContextValue: OfficialLanguageContextValue = {
  language: "zh",
  setLanguage: () => {},
  t: officialTranslations.zh,
}

const OfficialLanguageContext =
  createContext<OfficialLanguageContextValue>(defaultContextValue)

function getInitialOfficialLanguage(): OfficialLanguage {
  if (typeof window === "undefined") {
    return "zh"
  }
  try {
    const searchParams = new URLSearchParams(window.location.search)
    const urlLang = searchParams.get("lang")
    if (urlLang === "en" || urlLang === "zh") {
      try {
        sessionStorage.setItem(OFFICIAL_PORTAL_LANG_KEY, urlLang)
      } catch {}
      return urlLang
    }

    const storedLang = sessionStorage.getItem(OFFICIAL_PORTAL_LANG_KEY)
    if (storedLang === "en" || storedLang === "zh") {
      return storedLang
    }
  } catch {
    // In restricted contexts, fail gracefully
  }
  return "zh"
}

export function OfficialLanguageProvider({
  children,
}: {
  children: React.ReactNode
}) {
  const [language, setLanguageState] = useState<OfficialLanguage>(
    getInitialOfficialLanguage
  )

  // Listen to browser history navigation (back / forward)
  useEffect(() => {
    const handlePopState = () => {
      try {
        const searchParams = new URLSearchParams(window.location.search)
        const urlLang = searchParams.get("lang")
        if (urlLang === "en") {
          setLanguageState("en")
          try {
            sessionStorage.setItem(OFFICIAL_PORTAL_LANG_KEY, "en")
          } catch {}
        } else if (urlLang === "zh") {
          setLanguageState("zh")
          try {
            sessionStorage.setItem(OFFICIAL_PORTAL_LANG_KEY, "zh")
          } catch {}
        } else {
          // If URL has no lang param during history navigation (popstate),
          // it represents navigation back to the default Chinese portal route
          setLanguageState("zh")
          try {
            sessionStorage.setItem(OFFICIAL_PORTAL_LANG_KEY, "zh")
          } catch {}
        }
      } catch {}
    }

    window.addEventListener("popstate", handlePopState)
    return () => window.removeEventListener("popstate", handlePopState)
  }, [])

  const setLanguage = useCallback((newLang: OfficialLanguage) => {
    const safeLang: OfficialLanguage = newLang === "en" ? "en" : "zh"
    setLanguageState(safeLang)

    try {
      if (typeof window !== "undefined") {
        sessionStorage.setItem(OFFICIAL_PORTAL_LANG_KEY, safeLang)

        const url = new URL(window.location.href)
        if (safeLang === "en") {
          url.searchParams.set("lang", "en")
        } else {
          url.searchParams.delete("lang")
        }
        window.history.replaceState(null, "", url.pathname + url.search + url.hash)
      }
    } catch {
      // Graceful fallback
    }
  }, [])

  const t = useMemo(() => {
    return officialTranslations[language] || officialTranslations.zh
  }, [language])

  const value = useMemo(
    () => ({
      language,
      setLanguage,
      t,
    }),
    [language, setLanguage, t]
  )

  return (
    <OfficialLanguageContext.Provider value={value}>
      {children}
    </OfficialLanguageContext.Provider>
  )
}

export function useOfficialLanguage(): OfficialLanguageContextValue {
  const context = useContext(OfficialLanguageContext)
  return context || defaultContextValue
}
