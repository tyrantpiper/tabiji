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

/**
 * 📚 來源標籤 (Source Citation)
 * 
 * 支援雙軌在地與全球情報徽章、序號錨定 [1]、[2] 與暗色模式適配
 */
export default function SourceCitation({ sources }: SourceCitationProps) {
    const { lang } = useLanguage()
    const zh = lang === 'zh'
    if (!sources || sources.length === 0) return null

    return (
        <div className="flex flex-wrap items-center gap-1.5 mt-2 pt-2 border-t border-slate-100 dark:border-slate-800/60">
            <span className="text-[10px] font-medium text-slate-400 dark:text-slate-500 mr-0.5">
                {zh ? '來源：' : 'Sources:'}
            </span>
            {sources.map((source, idx) => {
                const badgeColor = source.badge?.color || "text-slate-600 dark:text-slate-300 bg-slate-100 dark:bg-slate-800/80 border-slate-200 dark:border-slate-700/60"
                const citationNum = source.citation_index || (idx + 1)
                const hostname = (() => {
                    try {
                        return new URL(source.uri).hostname.replace(/^www\./, '')
                    } catch {
                        return source.uri
                    }
                })()

                return (
                    <a
                        key={idx}
                        href={source.uri}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] rounded-full border transition-all hover:scale-105 active:scale-95 ${badgeColor}`}
                        title={source.snippet || source.title || source.uri}
                    >
                        <span className="font-semibold text-[9px] opacity-80">[{citationNum}]</span>
                        {source.badge?.text && (
                            <span className="font-medium text-[9px] mr-0.5">{source.badge.text}</span>
                        )}
                        <span className="max-w-27.5 truncate">
                            {source.title || hostname}
                        </span>
                        <ExternalLink className="w-2.5 h-2.5 opacity-50 shrink-0" />
                    </a>
                )
            })}
        </div>
    )
}
