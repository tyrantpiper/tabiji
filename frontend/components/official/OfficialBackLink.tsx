"use client"

import React from "react"
import Link from "next/link"
import { ArrowLeft } from "lucide-react"
import { useOfficialLanguage } from "@/lib/OfficialLanguageContext"

export interface OfficialBackLinkProps {
  href?: string
  className?: string
  "aria-label"?: string
}

export function OfficialBackLink({
  href = "/official",
  className = "inline-flex items-center gap-2 min-h-11 px-3 py-2 rounded-full text-sm font-medium text-stone-600 dark:text-stone-400 hover:text-[#0B3026] dark:hover:text-emerald-400 hover:bg-stone-100 dark:hover:bg-stone-800/50 transition-all duration-160 ease-out active:scale-[0.97]",
  "aria-label": customAriaLabel,
}: OfficialBackLinkProps) {
  const { language } = useOfficialLanguage()
  const isEn = language === "en"

  const defaultLabel = isEn ? "Back to official portal home" : "返回官方網站首頁"
  const label = customAriaLabel && !isEn ? customAriaLabel : defaultLabel
  const text = isEn ? "Back to Official Home" : "返回官方首頁"

  return (
    <Link
      href={href}
      className={className}
      aria-label={label}
    >
      <ArrowLeft className="w-4 h-4" />
      <span>{text}</span>
    </Link>
  )
}
