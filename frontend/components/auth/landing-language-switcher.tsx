"use client"

import { motion, useReducedMotion } from "framer-motion"
import type { Language } from "@/lib/LanguageContext"
import { cn } from "@/lib/utils"

export interface LandingLanguageSwitcherLabels {
    groupAria: string
    zhLabel: string
    enLabel: string
    switchToZhAria: string
    switchToEnAria: string
}

export interface LandingLanguageSwitcherProps {
    lang: Language
    onChange: (nextLang: Language) => void
    disabled?: boolean
    labels: LandingLanguageSwitcherLabels
    className?: string
}

export function LandingLanguageSwitcher({
    lang,
    onChange,
    disabled = false,
    labels,
    className,
}: LandingLanguageSwitcherProps) {
    const shouldReduceMotion = Boolean(useReducedMotion())

    const options: Array<{
        value: Language
        label: string
        ariaLabel: string
    }> = [
        { value: "zh", label: labels.zhLabel, ariaLabel: labels.switchToZhAria },
        { value: "en", label: labels.enLabel, ariaLabel: labels.switchToEnAria },
    ]

    return (
        <div
            role="group"
            aria-label={labels.groupAria}
            className={cn(
                "inline-flex items-center p-0.5 rounded-full border border-stone-200/80 dark:border-slate-700/80 bg-white/85 dark:bg-slate-800/85 backdrop-blur-md shadow-xs isolate select-none touch-manipulation",
                className
            )}
        >
            {options.map((option) => {
                const isActive = lang === option.value
                return (
                    <button
                        key={option.value}
                        type="button"
                        disabled={disabled}
                        aria-pressed={isActive}
                        aria-label={option.ariaLabel}
                        onClick={() => {
                            if (!disabled) {
                                onChange(option.value)
                            }
                        }}
                        className={cn(
                            "relative min-h-11 min-w-11 px-3 rounded-full text-xs whitespace-nowrap shrink-0 flex items-center justify-center transition-colors duration-160 ease-out touch-manipulation select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 dark:focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-slate-800 disabled:opacity-50 disabled:pointer-events-none disabled:cursor-not-allowed",
                            !disabled && "cursor-pointer active:scale-[0.96]",
                            isActive
                                ? "text-white dark:text-slate-900 font-bold"
                                : "text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white font-semibold"
                        )}
                    >
                        {isActive && (
                            <motion.span
                                aria-hidden="true"
                                layoutId={shouldReduceMotion ? undefined : "landing-lang-pill"}
                                transition={
                                    shouldReduceMotion
                                        ? { duration: 0 }
                                        : { type: "spring", stiffness: 400, damping: 30 }
                                }
                                className="absolute inset-0 rounded-full bg-slate-900 dark:bg-white shadow-xs z-0"
                            />
                        )}
                        <span className="relative z-10">{option.label}</span>
                    </button>
                )
            })}
        </div>
    )
}
