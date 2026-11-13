"use client"

import { createContext, useContext, useState, useEffect, useCallback, ReactNode, Suspense } from 'react'
import { usePathname, useSearchParams } from 'next/navigation'
import { translations, type TranslationKey } from './i18n'
export type { TranslationKey }

type Language = 'en' | 'zh'

interface LanguageContextType {
    lang: Language
    setLang: (lang: Language) => void
    t: (key: TranslationKey, params?: Record<string, string | number>) => string
    formatDate: (date: Date) => string
    isReady: boolean
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined)

function LanguageUrlHandoffObserver({ onAdoptLang }: { onAdoptLang: (lang: Language) => void }) {
    const pathname = usePathname()
    const searchParams = useSearchParams()

    useEffect(() => {
        if (typeof window === 'undefined') return
        const currentPathname = pathname || window.location.pathname
        if (currentPathname.startsWith('/official')) return

        const urlLang = searchParams?.get('lang') ?? new URLSearchParams(window.location.search).get('lang')
        if (urlLang === 'en' || urlLang === 'zh') {
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
            if (urlLang === 'en' || urlLang === 'zh') {
                setLangState(urlLang)
                localStorage.setItem('app_language', urlLang)
                document.cookie = `app_language=${urlLang}; path=/; max-age=31536000; SameSite=Lax`
                return
            }
        }

        const saved = localStorage.getItem('app_language') as Language
        if (saved && (saved === 'en' || saved === 'zh')) {
            setLangState(saved)
        }
    }, [])

    const setLang = useCallback((newLang: Language) => {
        setLangState(newLang)
        localStorage.setItem('app_language', newLang)
        // Sync to cookie so Server Components (SSR) can read the language preference
        document.cookie = `app_language=${newLang}; path=/; max-age=31536000; SameSite=Lax`
    }, [])

    /**
     * Translate a key with optional parameter interpolation.
     * Usage: t('greeting', { name: 'Ryan' }) → "Hello, Ryan!"
     * The dictionary value should contain `{name}` as placeholder.
     */
    const t = useCallback((key: TranslationKey, params?: Record<string, string | number>): string => {
        const dict = translations[lang] as Record<string, string>
        let result: string = dict[key] || key
        if (params) {
            Object.entries(params).forEach(([k, v]) => {
                result = result.replace(new RegExp(`\\{${k}\\}`, 'g'), String(v))
            })
        }
        return result
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
            t: (key: TranslationKey) => {
                const dict = translations.zh as Record<string, string>
                return dict[key] || key
            },
            formatDate: (date: Date) => date.toLocaleDateString('zh-TW'),
            isReady: true,
        }
    }
    return context
}
