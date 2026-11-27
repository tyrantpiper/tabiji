"use client"

import { ExternalLink } from "lucide-react"
import { useLanguage } from "@/lib/LanguageContext"

export interface GroundingSource {
    title: string
    uri: string
    citation_index?: number
    category?: string
    badge?: {
        text: string
        color?: string
    }
    snippet?: string
}

interface SourceCitationProps {
    sources: GroundingSource[]
}

const SAFE_SOURCE_URI_RE = /^https?:\/\//i
// 靜態完整宣告即時新聞徽章色票，確保 Tailwind CSS v4 編譯期必收錄相關 utility classes
const NEWS_SOURCE_BADGE_COLOR =
    "text-sky-600 dark:text-sky-400 bg-sky-500/10 border-sky-500/30 dark:border-sky-500/20"
const DEFAULT_SOURCE_BADGE_COLOR =
    "text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-800/80 border-slate-200 dark:border-slate-700/60"

/**
 * 📚 來源標籤 (Source Citation)
 * 
 * 支援雙軌在地與全球情報徽章、序號錨定 [1]、[2] 與暗色模式適配
 */
export default function SourceCitation({ sources }: SourceCitationProps) {
    const { lang } = useLanguage()
    const zh = lang === 'zh'
    if (!Array.isArray(sources) || sources.length === 0) return null

    const safeSources = sources.filter(
        (s) => Boolean(s && typeof s === "object" && typeof s.uri === "string" && SAFE_SOURCE_URI_RE.test(s.uri.trim()))
    )
    if (safeSources.length === 0) return null

    return (
        <div className="flex flex-wrap items-center gap-1.5 mt-2 pt-2 border-t border-slate-100 dark:border-slate-800/60">
            <span className="text-[10px] font-medium text-slate-400 dark:text-slate-500 mr-0.5">
                {zh ? '來源：' : 'Sources:'}
            </span>
            {safeSources.map((source, idx) => {
                const rawBadgeColor = typeof source.badge?.color === "string" ? source.badge.color.trim() : ""
                const rawBadgeText = typeof source.badge?.text === "string" ? source.badge.text.trim() : ""
                const badgeColor =
                    rawBadgeColor ||
                    (source.category === "news" ? NEWS_SOURCE_BADGE_COLOR : DEFAULT_SOURCE_BADGE_COLOR)
                const citationNum =
                    typeof source.citation_index === "number" && Number.isFinite(source.citation_index)
                        ? source.citation_index
                        : (idx + 1)
                const safeUri = source.uri.trim()
                const hostname = (() => {
                    try {
                        return new URL(safeUri).hostname.replace(/^www\./, '')
                    } catch {
                        return safeUri
                    }
                })()
                const safeTitle = typeof source.title === "string" ? source.title.trim() : ""
                const safeSnippet = typeof source.snippet === "string" ? source.snippet.trim() : ""

                return (
                    <a
                        key={idx}
                        href={safeUri}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] rounded-full border transition-all hover:scale-105 active:scale-95 ${badgeColor}`}
                        title={safeSnippet || safeTitle || safeUri}
                    >
                        <span className="font-semibold text-[9px] opacity-80">[{citationNum}]</span>
                        {rawBadgeText && (
                            <span className="font-medium text-[9px] mr-0.5">{rawBadgeText}</span>
                        )}
                        <span className="max-w-27.5 truncate">
                            {safeTitle || hostname}
                        </span>
                        <ExternalLink className="w-2.5 h-2.5 opacity-50 shrink-0" />
                    </a>
                )
            })}
        </div>
    )
}
