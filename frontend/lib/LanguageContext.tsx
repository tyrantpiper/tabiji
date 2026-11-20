"use client"

import { createContext, useContext, useState, useEffect, useCallback, ReactNode, Suspense } from 'react'
import { usePathname, useSearchParams } from 'next/navigation'
import { translations, type TranslationKey } from './i18n'
export type { TranslationKey }

export type Language = 'en' | 'zh'

interface LanguageContextType {
    lang: Language
    setLang: (lang: Language) => void
    t: (key: TranslationKey, params?: Record<string, string | number>) => string
    formatDate: (date: Date) => string
    isReady: boolean
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined)

function isValidLanguage(value: unknown): value is Language {
    return value === 'en' || value === 'zh'
}

function persistLanguageStorage(targetLang: Language) {
    try {
        localStorage.setItem('app_language', targetLang)
    } catch {
        // Graceful fallback when localStorage is unavailable or throws QuotaExceededError
    }
    try {
        // Sync to cookie so Server Components (SSR) can read the language preference
        document.cookie = `app_language=${targetLang}; path=/; max-age=31536000; SameSite=Lax`
    } catch {
        // Graceful fallback when cookie access is restricted
    }
}

function translateTemplate(
    targetLang: Language,
    key: TranslationKey,
    params?: Record<string, string | number>
): string {
    const dict = (translations[targetLang] ?? translations.zh) as Record<string, string>
    const rawValue = Object.prototype.hasOwnProperty.call(dict, key) ? dict[key] : undefined
    let result: string = typeof rawValue === 'string' ? rawValue : key
    if (params) {
        for (const [k, v] of Object.entries(params)) {
            result = result.split(`{${k}}`).join(String(v))
        }
    }
    return result
}

function LanguageUrlHandoffObserver({ onAdoptLang }: { onAdoptLang: (lang: Language) => void }) {
    const pathname = usePathname()
    const searchParams = useSearchParams()

    useEffect(() => {
        if (typeof window === 'undefined') return
        const currentPathname = pathname || window.location.pathname
        if (currentPathname.startsWith('/official')) return

        const urlLang = searchParams?.get('lang') ?? new URLSearchParams(window.location.search).get('lang')
        if (isValidLanguage(urlLang)) {
            onAdoptLang(urlLang)
            try {
                const url = new URL(window.location.href)
                if (url.searchParams.has('lang')) {
                    url.searchParams.delete('lang')
                    window.history.replaceState(null, '', url.pathname + url.search + url.hash)
                }
            } catch {
                // Graceful fallback if history API is unavailable
            }
        }
    }, [pathname, searchParams, onAdoptLang])

    return null
}

export function LanguageProvider({ children }: { children: ReactNode }) {
    const [lang, setLangState] = useState<Language>('zh')
    const [mounted, setMounted] = useState(false)

    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect -- SSR hydration: setMounted must be called to detect client
        setMounted(true)

        const isOfficial = typeof window !== 'undefined' && window.location.pathname.startsWith('/official')
        if (!isOfficial) {
            const urlLang = new URLSearchParams(window.location.search).get('lang')
            if (isValidLanguage(urlLang)) {
                setLangState(urlLang)
                persistLanguageStorage(urlLang)
                return
            }
        }

        try {
            const saved = localStorage.getItem('app_language')
            if (isValidLanguage(saved)) {
                setLangState(saved)
            }
        } catch {
            // Graceful fallback when localStorage is blocked (e.g. Safari Private Mode)
        }
    }, [])

    const setLang = useCallback((newLang: Language) => {
        if (!isValidLanguage(newLang)) return
        setLangState(newLang)
        persistLanguageStorage(newLang)
    }, [])

    /**
     * Translate a key with optional parameter interpolation.
     * Usage: t('greeting', { name: 'Ryan' }) → "Hello, Ryan!"
     * The dictionary value should contain `{name}` as placeholder.
     */
    const t = useCallback((key: TranslationKey, params?: Record<string, string | number>): string => {
        return translateTemplate(lang, key, params)
    }, [lang])

    /** Format a Date according to the current app language (not OS locale). */
    const formatDate = useCallback((date: Date): string => {
        return date.toLocaleDateString(lang === 'en' ? 'en-US' : 'zh-TW')
    }, [lang])

    return (
        <LanguageContext.Provider value={{ lang, setLang, t, formatDate, isReady: mounted }}>
            {mounted && (
                <Suspense fallback={null}>
                    <LanguageUrlHandoffObserver onAdoptLang={setLang} />
                </Suspense>
            )}
            {children}
        </LanguageContext.Provider>
    )
}

export function useLanguage() {
    const context = useContext(LanguageContext)
    if (!context) {
        // Return default values if not in provider (for SSR)
        return {
            lang: 'zh' as Language,
            setLang: () => { },
            t: (key: TranslationKey, params?: Record<string, string | number>) =>
                translateTemplate('zh', key, params),
            formatDate: (date: Date) => date.toLocaleDateString('zh-TW'),
            isReady: true,
        }
    }
    return context
}
