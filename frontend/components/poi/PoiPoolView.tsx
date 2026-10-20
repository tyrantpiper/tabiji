"use client"

import React, { useState, useMemo, useRef } from "react"
import dynamic from "next/dynamic"
import { motion, AnimatePresence } from "framer-motion"
import {
    ChevronLeft, ChevronRight, ChevronDown, ChevronUp, Bookmark, Search, Link as LinkIcon, Sparkles, Clipboard,
    MapPin, ExternalLink, StickyNote, Plus, Trash2, Check, X, Loader2,
    Utensils, Coffee, Landmark, ShoppingBag, Hotel, Train, Star, Compass, Clock, Map as MapIcon
} from "lucide-react"
import { TranslationKey } from "@/lib/i18n"
import { useLanguage } from "@/lib/LanguageContext"
import { useHaptic } from "@/lib/hooks"
import { usePoiPool } from "@/lib/hooks/usePoiPool"
import { POIItem, POICategory } from "@/lib/poi-types"
import { Trip } from "@/lib/itinerary-types"
import { cn, openExternalLink } from "@/lib/utils"
import { toast } from "sonner"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog"

const PoiPoolMap = dynamic(() => import("./PoiPoolMap"), {
    ssr: false,
    loading: () => (
        <div className="w-full h-48 bg-black/5 dark:bg-white/5 animate-pulse rounded-2xl flex items-center justify-center text-xs text-[#5C6B68]">
            載入地圖中...
        </div>
    )
})

interface PoiPoolViewProps {
    userId: string | null
    currentTrip?: Trip | null
    allTrips?: Trip[]
    totalDays?: number
    onBack: () => void
    onAddPoiToTrip?: (targetTripId: string, dayNum: number, poi: POIItem, timeStr?: string) => Promise<void>
}

// 🏷️ 類別圖示與色彩映射
const CATEGORY_MAP: Record<POICategory, { labelKey: TranslationKey; icon: React.ElementType; color: string; bg: string }> = {
    attraction: { labelKey: "poi_cat_attraction", icon: Landmark, color: "text-emerald-600 dark:text-emerald-400", bg: "bg-emerald-50 dark:bg-emerald-950/40" },
    food: { labelKey: "poi_cat_food", icon: Utensils, color: "text-amber-600 dark:text-amber-400", bg: "bg-amber-50 dark:bg-amber-950/40" },
    cafe: { labelKey: "poi_cat_cafe", icon: Coffee, color: "text-orange-600 dark:text-orange-400", bg: "bg-orange-50 dark:bg-orange-950/40" },
    shopping: { labelKey: "poi_cat_shopping", icon: ShoppingBag, color: "text-pink-600 dark:text-pink-400", bg: "bg-pink-50 dark:bg-pink-950/40" },
    hotel: { labelKey: "poi_cat_hotel", icon: Hotel, color: "text-indigo-600 dark:text-indigo-400", bg: "bg-indigo-50 dark:bg-indigo-950/40" },
    transport: { labelKey: "poi_cat_transport", icon: Train, color: "text-blue-600 dark:text-blue-400", bg: "bg-blue-50 dark:bg-blue-950/40" },
    other: { labelKey: "poi_cat_all", icon: Compass, color: "text-slate-600 dark:text-slate-400", bg: "bg-slate-50 dark:bg-slate-800" },
}

export function PoiPoolView({
    userId,
    currentTrip,
    allTrips = [],
    totalDays = 1,
    onBack,
    onAddPoiToTrip,
}: PoiPoolViewProps) {
    const { t } = useLanguage()
    const haptic = useHaptic()

    const {
        poiList,
        isLoading,
        importLink,
        updateNote,
        updateCategory,
        togglePin,
        deletePoi,
    } = usePoiPool(userId)

    // 🔍 搜尋與 Omnibar 狀態
    const [omnibarInput, setOmnibarInput] = useState("")
    const [selectedCategory, setSelectedCategory] = useState<POICategory | "all" | "pinned">("all")
    const [isImporting, setIsImporting] = useState(false)

    // 🗺️ 地圖檢視狀態 (Google Maps Saved Places UX)
    const [showMap, setShowMap] = useState(true)
    const [selectedPoiOnMap, setSelectedPoiOnMap] = useState<string | null>(null)

    // 📝 行內備註編輯狀態
    const [editingNoteId, setEditingNoteId] = useState<string | null>(null)
    const [noteDraft, setNoteDraft] = useState("")
    const noteInputRef = useRef<HTMLInputElement>(null)

    // 🗓️ 排入行程記錄反查快取 (poiId -> Set of "tripName:dayNum")
    const [scheduledRecords, setScheduledRecords] = useState<Record<string, { tripTitle: string; day: number }[]>>({})

    // 🗓️ 雙階行程排入互動狀態 (支援首頁與行程間定向排程、選擇天數與時間)
    const [schedulingPoi, setSchedulingPoi] = useState<POIItem | null>(null)
    const [selectedTripForScheduling, setSelectedTripForScheduling] = useState<Trip | null>(null)
    const [selectedDayForScheduling, setSelectedDayForScheduling] = useState<number>(1)
    const [selectedTimeForScheduling, setSelectedTimeForScheduling] = useState<string>("未定")

    // 判斷當前 Omnibar 輸入是否為地圖網址
    const isUrl = useMemo(() => {
        const trimmed = omnibarInput.trim()
        return /(https?:\/\/[^\s]+)/i.test(trimmed) || /maps\.app\.goo\.gl|google\.com\/maps/i.test(trimmed)
    }, [omnibarInput])

    // 統計數據
    const stats = useMemo(() => {
        const total = poiList.length
        const pinned = poiList.filter((p) => p.is_pinned).length
        return { total, pinned }
    }, [poiList])

    // 當前有效天數清單 (行程內模式)
    const calculatedDays = useMemo(() => {
        if (!currentTrip) return Array.from({ length: totalDays || 1 }, (_, i) => i + 1)
        if (Array.isArray(currentTrip.days) && currentTrip.days.length > 0) {
            return currentTrip.days.map((d) => d.day)
        }
        return Array.from({ length: totalDays || 1 }, (_, i) => i + 1)
    }, [currentTrip, totalDays])

    // 篩選後清單
    const filteredPois = useMemo(() => {
        let list = [...poiList]

        // 1. 類別過濾
        if (selectedCategory === "pinned") {
            list = list.filter((p) => Boolean(p.is_pinned))
        } else if (selectedCategory !== "all") {
            list = list.filter((p) => p.category === selectedCategory)
        }

        // 2. 關鍵字搜尋 (若非 URL 模式)
        const q = omnibarInput.trim().toLowerCase()
        if (q && !isUrl) {
            list = list.filter((p) =>
                p.title.toLowerCase().includes(q) ||
                (p.address && p.address.toLowerCase().includes(q)) ||
                (p.user_notes && p.user_notes.toLowerCase().includes(q))
            )
        }

        return list
    }, [poiList, selectedCategory, omnibarInput, isUrl])

    // 📋 剪貼簿一鍵貼上
    const handlePasteClipboard = async () => {
        haptic.tap()
        try {
            if (!navigator.clipboard?.readText) {
                toast.info(t('poi_clipboard_denied') || "無法讀取剪貼簿，請直接在輸入框長按貼上")
                return
            }
            const text = await navigator.clipboard.readText()
            if (text && text.trim()) {
                setOmnibarInput(text.trim())
                if (/(https?:\/\/[^\s]+)/.test(text)) {
                    await handleExecuteImport(text.trim())
                }
            } else {
                toast.info("剪貼簿為空")
            }
        } catch (err) {
            console.warn("[PoiPool] Clipboard read rejected:", err)
            toast.info(t('poi_clipboard_denied') || "無法存取剪貼簿，請直接在輸入框長按貼上")
        }
    }

    // 🚀 執行匯入
    const handleExecuteImport = async (urlToImport?: string) => {
        const targetUrl = urlToImport || omnibarInput.trim()
        if (!targetUrl) return
        setIsImporting(true)
        haptic.tap()
        try {
            await importLink(targetUrl)
            setOmnibarInput("")
        } finally {
            setIsImporting(false)
        }
    }

    // 💾 儲存行內備註
    const handleSaveNote = async (poiId: string) => {
        const trimmed = noteDraft.trim()
        await updateNote(poiId, trimmed)
        setEditingNoteId(null)
        setNoteDraft("")
    }

    // 📅 連續排程處理 (支援指定時間)
    const handleSchedulePoi = async (targetTrip: Trip, dayNum: number, poi: POIItem, timeStr?: string) => {
        haptic.selection()
        const finalTime = timeStr || "未定"
        if (onAddPoiToTrip) {
            await onAddPoiToTrip(targetTrip.id, dayNum, poi, finalTime)
        }

        // 本機即時標記排入狀態
        setScheduledRecords((prev) => {
            const current = prev[poi.id] || []
            return {
                ...prev,
                [poi.id]: [...current, { tripTitle: targetTrip.title || "Trip", day: dayNum }]
            }
        })

        toast.success(
            finalTime && finalTime !== "未定"
                ? `已加入第 ${dayNum} 天 (${finalTime}) 行程！`
                : t('poi_added_to_trip', { day: dayNum }) || `已加入第 ${dayNum} 天行程！`
        )
    }

    return (
        <div className="w-full h-dvh flex flex-col bg-[#F6F5EE] dark:bg-[#121A18] overflow-hidden select-none">
            {/* ── 1. 置頂導航列 (Sticky Header) ─────────────────────────────────── */}
            <header className="shrink-0 px-4 sm:px-6 pt-[calc(max(env(safe-area-inset-top,0px),0px)+0.75rem)] pb-3 border-b border-black/5 dark:border-white/10 bg-white/70 dark:bg-[#182320]/70 backdrop-blur-xl flex items-center justify-between z-20">
                <div className="flex items-center gap-3">
                    <button
                        type="button"
                        onClick={() => {
                            haptic.selection()
                            onBack()
                        }}
                        className="w-9 h-9 rounded-full flex items-center justify-center bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-[#1E2927] dark:text-[#E5EBEA] active:scale-90 transition-all cursor-pointer"
                        aria-label="Back"
                    >
                        <ChevronLeft className="w-5 h-5 -ml-0.5" />
                    </button>
                    <div>
                        <div className="flex items-center gap-2">
                            <h1 className="text-base font-bold text-[#1E2927] dark:text-[#E5EBEA] tracking-tight flex items-center gap-1.5">
                                <Bookmark className="w-4 h-4 fill-amber-500/30 text-[#E56E25] dark:text-amber-400" />
                                <span>{t('poi_drawer_title') || "全域景點口袋庫"}</span>
                            </h1>
                        </div>
                        <p className="text-[11px] text-[#5C6B68] dark:text-[#A2B1AE] truncate max-w-60 sm:max-w-xs">
                            {currentTrip ? currentTrip.title : (t('poi_drawer_desc') || "儲存喜愛地點，隨時排入行程")}
                        </p>
                    </div>
                </div>

                {/* 📊 統計徽章 */}
                <div className="flex items-center gap-1.5">
                    <div className="px-2.5 py-1 rounded-full bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/5 text-[11px] font-bold text-[#1E2927] dark:text-[#E5EBEA] flex items-center gap-1">
                        <span>{t('poi_total_places') || "總計"}</span>
                        <span className="font-mono text-[#E56E25] dark:text-amber-400">{stats.total}</span>
                    </div>
                    <div className="px-2.5 py-1 rounded-full bg-amber-500/10 dark:bg-amber-400/10 border border-amber-500/20 text-[11px] font-bold text-[#E56E25] dark:text-amber-400 flex items-center gap-1">
                        <span>📌 {t('poi_pinned_count') || "已釘選"}</span>
                        <span className="font-mono">{stats.pinned}</span>
                    </div>
                </div>
            </header>

            {/* ── 2. 智慧全能列 (Smart Omnibar) ─────────────────────────────────── */}
            <div className="shrink-0 p-4 sm:px-6 bg-white/40 dark:bg-[#182320]/40 border-b border-black/5 dark:border-white/5 backdrop-blur-md">
                <div className="max-w-4xl mx-auto space-y-3">
                    <div className="relative flex items-center">
                        <div className="absolute left-3.5 text-[#5C6B68] dark:text-[#A2B1AE] pointer-events-none">
                            {isUrl ? (
                                <LinkIcon className="w-4 h-4 text-[#E56E25] dark:text-amber-400 animate-pulse" />
                            ) : (
                                <Search className="w-4 h-4" />
                            )}
                        </div>

                        <input
                            type="text"
                            value={omnibarInput}
                            onChange={(e) => setOmnibarInput(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter" && isUrl) {
                                    handleExecuteImport()
                                }
                            }}
                            placeholder={t('poi_search_or_paste') || "搜尋景點、筆記，或貼上 Google Maps 網址..."}
                            className="w-full pl-10 pr-24 py-2.5 rounded-2xl bg-white dark:bg-[#1E2927] border border-[#0B3026]/10 dark:border-white/10 text-sm text-[#1E2927] dark:text-[#E5EBEA] placeholder:text-[#5C6B68]/60 dark:placeholder:text-[#A2B1AE]/50 focus:outline-hidden focus:ring-2 focus:ring-[#E56E25]/30 shadow-xs transition-all"
                        />

                        {/* 右側按鈕群 */}
                        <div className="absolute right-2 flex items-center gap-1">
                            {omnibarInput && !isUrl && (
                                <button
                                    type="button"
                                    onClick={() => setOmnibarInput("")}
                                    className="p-1.5 rounded-full text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                                >
                                    <X className="w-3.5 h-3.5" />
                                </button>
                            )}

                            {isUrl ? (
                                <button
                                    type="button"
                                    onClick={() => handleExecuteImport()}
                                    disabled={isImporting}
                                    className="px-3 py-1.5 rounded-xl bg-linear-to-r from-amber-500 to-orange-500 text-white text-xs font-bold shadow-md hover:from-amber-600 hover:to-orange-600 active:scale-95 transition-all flex items-center gap-1.5 disabled:opacity-50"
                                >
                                    {isImporting ? (
                                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                    ) : (
                                        <Sparkles className="w-3.5 h-3.5" />
                                    )}
                                    <span>{t('poi_resolve_and_import') || "解析匯入"}</span>
                                </button>
                            ) : (
                                <button
                                    type="button"
                                    onClick={handlePasteClipboard}
                                    className="px-2.5 py-1.5 rounded-xl bg-black/5 dark:bg-white/10 hover:bg-black/10 dark:hover:bg-white/15 text-slate-700 dark:text-slate-200 text-xs font-bold transition-all flex items-center gap-1 active:scale-95"
                                    title={t('poi_paste_from_clipboard') || "貼上剪貼簿"}
                                >
                                    <Clipboard className="w-3.5 h-3.5 text-[#E56E25] dark:text-amber-400" />
                                    <span className="hidden sm:inline">{t('poi_paste_from_clipboard') || "貼上"}</span>
                                </button>
                            )}
                        </div>
                    </div>

                    {/* 🏷️ 分類過濾列 */}
                    <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5">
                        <button
                            type="button"
                            onClick={() => setSelectedCategory("all")}
                            className={cn(
                                "px-3 py-1 rounded-full text-xs font-bold transition-all shrink-0 active:scale-95",
                                selectedCategory === "all"
                                    ? "bg-[#1E2927] text-white dark:bg-[#E5EBEA] dark:text-[#121A18] shadow-xs"
                                    : "bg-black/5 dark:bg-white/5 text-[#5C6B68] dark:text-[#A2B1AE] hover:bg-black/10"
                            )}
                        >
                            {t('poi_cat_all') || "全部"} ({poiList.length})
                        </button>

                        <button
                            type="button"
                            onClick={() => setSelectedCategory("pinned")}
                            className={cn(
                                "px-3 py-1 rounded-full text-xs font-bold transition-all shrink-0 active:scale-95 flex items-center gap-1",
                                selectedCategory === "pinned"
                                    ? "bg-amber-500 text-white shadow-xs"
                                    : "bg-amber-500/10 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20"
                            )}
                        >
                            <span>📌 {t('poi_pinned_count') || "已釘選"}</span>
                            <span>({stats.pinned})</span>
                        </button>

                        {(["attraction", "food", "cafe", "shopping", "hotel", "transport"] as POICategory[]).map((cat) => {
                            const meta = CATEGORY_MAP[cat]
                            const count = poiList.filter((p) => p.category === cat).length
                            if (count === 0 && selectedCategory !== cat) return null
                            const IconComponent = meta.icon

                            return (
                                <button
                                    key={cat}
                                    type="button"
                                    onClick={() => setSelectedCategory(cat)}
                                    className={cn(
                                        "px-3 py-1 rounded-full text-xs font-bold transition-all shrink-0 active:scale-95 flex items-center gap-1.5",
                                        selectedCategory === cat
                                            ? "bg-[#1E2927] text-white dark:bg-[#E5EBEA] dark:text-[#121A18] shadow-xs"
                                            : "bg-black/5 dark:bg-white/5 text-[#5C6B68] dark:text-[#A2B1AE] hover:bg-black/10"
                                    )}
                                >
                                    <IconComponent className="w-3 h-3" />
                                    <span>{t(meta.labelKey) || cat}</span>
                                    <span className="opacity-60 text-[10px]">({count})</span>
                                </button>
                            )
                        })}
                    </div>
                </div>
            </div>

            {/* ── 3. 景點卡片清單與互動地圖 (Spacious POI Card Stream & Map) ─────────────────────── */}
            <div className="flex-1 overflow-y-auto overscroll-contain p-4 sm:p-6">
                <div className="max-w-4xl mx-auto space-y-4 pb-[max(env(safe-area-inset-bottom),2rem)]">
                    {/* 🗺️ POI Pocket 互動地圖總覽 (Google Maps Saved Places UX) */}
                    {filteredPois.some((p) => p.lat && p.lng) && (
                        <div className="space-y-2">
                            <div className="flex items-center justify-between px-1">
                                <span className="text-xs font-bold text-[#5C6B68] dark:text-[#A2B1AE] flex items-center gap-1.5">
                                    <MapIcon className="w-3.5 h-3.5 text-[#E56E25]" />
                                    <span>{t('poi_map_overview') || "地點分布地圖"}</span>
                                </span>
                                <button
                                    type="button"
                                    onClick={() => {
                                        haptic.tap()
                                        setShowMap((prev) => !prev)
                                    }}
                                    className="text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:underline flex items-center gap-1 cursor-pointer"
                                >
                                    {showMap ? (
                                        <>
                                            <ChevronUp className="w-3.5 h-3.5" />
                                            <span>{t('poi_collapse_map') || "收起地圖"}</span>
                                        </>
                                    ) : (
                                        <>
                                            <ChevronDown className="w-3.5 h-3.5" />
                                            <span>{t('poi_expand_map') || "展開地圖"}</span>
                                        </>
                                    )}
                                </button>
                            </div>

                            <AnimatePresence>
                                {showMap && (
                                    <motion.div
                                        initial={{ opacity: 0, scale: 0.98 }}
                                        animate={{ opacity: 1, scale: 1 }}
                                        exit={{ opacity: 0, scale: 0.98 }}
                                        transition={{ duration: 0.25 }}
                                        className="w-full h-80 sm:h-96 overflow-hidden rounded-2xl"
                                    >
                                        <PoiPoolMap
                                            pois={filteredPois}
                                            selectedPoiId={selectedPoiOnMap}
                                            onSelectPoi={(p) => {
                                                setSelectedPoiOnMap(p.id)
                                            }}
                                            onSchedulePoi={(p) => {
                                                setSchedulingPoi(p)
                                            }}
                                        />
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </div>
                    )}

                    {isLoading && poiList.length === 0 ? (
                        <div className="py-20 flex flex-col items-center justify-center text-[#5C6B68] dark:text-[#A2B1AE] space-y-3">
                            <Loader2 className="w-8 h-8 animate-spin text-[#E56E25]" />
                            <p className="text-sm font-medium">{t('poi_importing') || "正在載入景點庫..."}</p>
                        </div>
                    ) : filteredPois.length === 0 ? (
                        <div className="py-20 flex flex-col items-center justify-center text-center px-4">
                            <div className="w-16 h-16 rounded-3xl bg-amber-500/10 dark:bg-amber-400/10 flex items-center justify-center text-[#E56E25] dark:text-amber-400 mb-4 shadow-inner">
                                <Bookmark className="w-8 h-8" />
                            </div>
                            <h3 className="text-base font-bold text-[#1E2927] dark:text-[#E5EBEA]">
                                {omnibarInput ? (t('poi_no_results') || "未找到符合的景點") : (t('poi_empty_title') || "口袋清單空空如也")}
                            </h3>
                            <p className="text-xs text-[#5C6B68] dark:text-[#A2B1AE] mt-1 max-w-sm">
                                {omnibarInput ? (t('poi_no_results_desc') || "請嘗試更換關鍵字或點擊上方「解析匯入」") : (t('poi_empty_desc') || "貼上 Google 地圖分享連結或清單網址，自動萃取所有地點！")}
                            </p>
                        </div>
                    ) : (
                        filteredPois.map((poi) => {
                            const catMeta = CATEGORY_MAP[poi.category] || CATEGORY_MAP.other
                            const IconComp = catMeta.icon
                            const isEditingNote = editingNoteId === poi.id
                            const scheduled = scheduledRecords[poi.id] || []

                            return (
                                <motion.div
                                    key={poi.id}
                                    layout
                                    initial={{ opacity: 0, y: 8 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, scale: 0.95 }}
                                    className="bg-white/80 dark:bg-[#1E2927]/80 backdrop-blur-md rounded-2xl p-4 sm:p-5 border border-black/5 dark:border-white/10 shadow-xs hover:shadow-md transition-all space-y-3"
                                >
                                    {/* 頂行：分類圖示、店名、評分與導航按鈕 */}
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="flex items-start gap-3 flex-1 min-w-0">
                                            {/* 🏷️ 分類圖示 - 支援點擊自訂切換 (Issue #5) */}
                                            <DropdownMenu>
                                                <DropdownMenuTrigger asChild>
                                                    <button
                                                        type="button"
                                                        className={cn(
                                                            "w-10 h-10 rounded-xl flex items-center justify-center shrink-0 shadow-2xs hover:scale-105 active:scale-95 transition-all cursor-pointer relative group",
                                                            catMeta.bg,
                                                            catMeta.color
                                                        )}
                                                        title={t('poi_change_category_tooltip') || "點擊切換分類圖示"}
                                                    >
                                                        <IconComp className="w-5 h-5" />
                                                    </button>
                                                </DropdownMenuTrigger>
                                                <DropdownMenuContent align="start" className="w-44 p-1 rounded-2xl shadow-xl">
                                                    <DropdownMenuLabel className="text-[11px] text-slate-400 font-bold px-2 py-1">
                                                        {t('poi_change_category_label') || "變更地點類別"}
                                                    </DropdownMenuLabel>
                                                    <DropdownMenuSeparator />
                                                    {(["attraction", "food", "cafe", "shopping", "hotel", "transport", "other"] as POICategory[]).map((cKey) => {
                                                        const cm = CATEGORY_MAP[cKey]
                                                        const CIcon = cm.icon
                                                        const isCur = poi.category === cKey
                                                        return (
                                                            <DropdownMenuItem
                                                                key={cKey}
                                                                onClick={() => {
                                                                    updateCategory(poi.id, cKey)
                                                                }}
                                                                className={cn(
                                                                    "flex items-center gap-2 px-2.5 py-1.5 rounded-xl text-xs font-semibold cursor-pointer",
                                                                    isCur ? "bg-black/5 dark:bg-white/10 font-bold" : ""
                                                                )}
                                                            >
                                                                <div className={cn("w-6 h-6 rounded-lg flex items-center justify-center", cm.bg, cm.color)}>
                                                                    <CIcon className="w-3.5 h-3.5" />
                                                                </div>
                                                                <span className="flex-1">{t(cm.labelKey) || cKey}</span>
                                                                {isCur && <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />}
                                                            </DropdownMenuItem>
                                                        )
                                                    })}
                                                </DropdownMenuContent>
                                            </DropdownMenu>

                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    <h3 className="text-sm sm:text-base font-bold text-[#1E2927] dark:text-[#E5EBEA] truncate">
                                                        {poi.title}
                                                    </h3>
                                                    {poi.rating && (
                                                        <span className="flex items-center gap-0.5 text-xs font-bold text-amber-500 bg-amber-50 dark:bg-amber-950/40 px-1.5 py-0.5 rounded-md">
                                                            <Star className="w-3 h-3 fill-amber-500" />
                                                            <span>{poi.rating}</span>
                                                        </span>
                                                    )}
                                                </div>
                                                {/* 🛡️ 乾淨地址過濾：絕不顯示 http/https 或未解碼 URL */}
                                                {poi.address && !poi.address.startsWith("http") && !poi.address.includes("%") && (
                                                    <p className="text-xs text-[#5C6B68] dark:text-[#A2B1AE] mt-0.5 truncate flex items-center gap-1">
                                                        <MapPin className="w-3 h-3 shrink-0" />
                                                        <span className="truncate">{poi.address}</span>
                                                    </p>
                                                )}
                                            </div>
                                        </div>

                                        {/* Google Maps 跳轉按鈕 */}
                                        <button
                                            type="button"
                                            onClick={() => {
                                                const url = poi.source_url || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(poi.title)}`
                                                openExternalLink(url)
                                            }}
                                            className="px-2.5 py-1.5 rounded-xl bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 text-slate-600 dark:text-slate-300 text-xs font-semibold flex items-center gap-1 shrink-0 transition-colors"
                                            title={t('poi_open_maps') || "在 Google 地圖中開啟"}
                                        >
                                            <ExternalLink className="w-3.5 h-3.5" />
                                            <span className="hidden sm:inline">{t('poi_open_maps') || "開啟地圖"}</span>
                                        </button>
                                    </div>

                                    {/* 📝 行內即時備註編輯區 (Inline Quick Note) */}
                                    <div className="pt-1">
                                        {isEditingNote ? (
                                            <div className="flex items-center gap-2 bg-[#F6F5EE] dark:bg-[#121A18] rounded-xl px-3 py-1.5 border border-amber-500/40">
                                                <StickyNote className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                                                <input
                                                    ref={noteInputRef}
                                                    type="text"
                                                    value={noteDraft}
                                                    onChange={(e) => setNoteDraft(e.target.value)}
                                                    onKeyDown={(e) => {
                                                        if (e.key === "Enter") handleSaveNote(poi.id)
                                                        if (e.key === "Escape") setEditingNoteId(null)
                                                    }}
                                                    onBlur={() => handleSaveNote(poi.id)}
                                                    placeholder={t('poi_notes_placeholder') || "輸入個人筆記（如必吃、營業時間）..."}
                                                    className="w-full bg-transparent text-xs text-[#1E2927] dark:text-[#E5EBEA] outline-hidden placeholder:text-slate-400"
                                                    autoFocus
                                                />
                                                <button
                                                    type="button"
                                                    onMouseDown={(e) => e.preventDefault()}
                                                    onClick={() => handleSaveNote(poi.id)}
                                                    className="p-1 rounded-full text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950/40"
                                                >
                                                    <Check className="w-3.5 h-3.5" />
                                                </button>
                                            </div>
                                        ) : (
                                            <div
                                                onClick={() => {
                                                    setEditingNoteId(poi.id)
                                                    setNoteDraft(poi.user_notes || "")
                                                }}
                                                className="group cursor-pointer rounded-xl px-3 py-2 bg-black/2 dark:bg-white/2 hover:bg-black/5 dark:hover:bg-white/5 border border-transparent hover:border-black/5 dark:hover:border-white/5 transition-colors flex items-center justify-between"
                                            >
                                                <div className="flex items-center gap-2 min-w-0">
                                                    <StickyNote className="w-3.5 h-3.5 text-amber-500/70 group-hover:text-amber-500 shrink-0" />
                                                    <p className={cn(
                                                        "text-xs truncate",
                                                        poi.user_notes
                                                            ? "text-[#1E2927] dark:text-[#E5EBEA] font-medium"
                                                            : "text-[#5C6B68]/60 dark:text-[#A2B1AE]/50 italic"
                                                    )}>
                                                        {poi.user_notes || (t('poi_notes_placeholder') || "點擊新增個人筆記（例如必吃料理、需預約）...")}
                                                    </p>
                                                </div>
                                                <span className="text-[10px] text-amber-600 dark:text-amber-400 opacity-0 group-hover:opacity-100 transition-opacity font-bold">
                                                    {t('edit') || "編輯"}
                                                </span>
                                            </div>
                                        )}
                                    </div>

                                    {/* 底部操作欄：釘選切換、排入天數、刪除與排程徽章 */}
                                    <div className="flex items-center justify-between pt-2 border-t border-black/5 dark:border-white/5 gap-2 flex-wrap">
                                        {/* 左側：釘選開關與排入狀態 */}
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <button
                                                type="button"
                                                onClick={() => togglePin(poi.id, poi.is_pinned)}
                                                className={cn(
                                                    "px-3 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 active:scale-95",
                                                    poi.is_pinned
                                                        ? "bg-[#E56E25] text-white shadow-xs"
                                                        : "bg-black/5 dark:bg-white/5 text-[#5C6B68] dark:text-[#A2B1AE] hover:bg-black/10"
                                                )}
                                            >
                                                <Bookmark className={cn("w-3.5 h-3.5", poi.is_pinned ? "fill-white" : "")} />
                                                <span>{poi.is_pinned ? (t('poi_pinned_on_map') || "已釘選至地圖") : (t('poi_pin_toggle') || "釘選到地圖")}</span>
                                            </button>

                                            {/* 已排入標籤徽章 */}
                                            {scheduled.map((rec, idx) => (
                                                <span
                                                    key={idx}
                                                    className="px-2 py-1 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 text-[11px] font-bold flex items-center gap-1"
                                                >
                                                    <Check className="w-3 h-3" />
                                                    <span>{rec.tripTitle ? `${rec.tripTitle} ` : ""}{t('poi_day_n', { day: rec.day }) || `Day ${rec.day}`}</span>
                                                </span>
                                            ))}
                                        </div>

                                        {/* 右側：排入行程選單 ＋ 刪除 */}
                                        <div className="flex items-center gap-2">
                                            {/* 🗓️ 排入行程 (支援單行程快速天數與全景雙階排程) */}
                                            {currentTrip ? (
                                                // 行程頁模式：直接選天數，或開啟雙階排程選擇其他行程
                                                <DropdownMenu>
                                                    <DropdownMenuTrigger asChild>
                                                        <button
                                                            type="button"
                                                            className="px-3 py-1.5 rounded-xl bg-linear-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white text-xs font-bold shadow-xs flex items-center gap-1 active:scale-95 transition-all"
                                                        >
                                                            <Plus className="w-3.5 h-3.5" />
                                                            <span>{t('poi_add_to_trip') || "排入行程"}</span>
                                                        </button>
                                                    </DropdownMenuTrigger>
                                                    <DropdownMenuContent align="end" className="w-48 p-1.5 rounded-2xl bg-white/95 dark:bg-[#1E2927]/95 backdrop-blur-xl border border-black/10 dark:border-white/10 shadow-2xl">
                                                        <DropdownMenuLabel className="text-xs font-bold text-[#5C6B68] dark:text-[#A2B1AE] px-2 py-1">
                                                            {t('poi_select_day') || "選擇排入天數"}
                                                        </DropdownMenuLabel>
                                                        <DropdownMenuSeparator />
                                                        {calculatedDays.map((d) => (
                                                            <DropdownMenuItem
                                                                key={d}
                                                                onClick={() => handleSchedulePoi(currentTrip, d, poi)}
                                                                className="text-xs font-bold text-[#1E2927] dark:text-[#E5EBEA] rounded-xl px-2.5 py-2 cursor-pointer focus:bg-emerald-50 dark:focus:bg-emerald-950/40 flex items-center justify-between"
                                                            >
                                                                <span>{t('poi_day_n', { day: d }) || `第 ${d} 天`}</span>
                                                                <span className="text-[10px] text-amber-600 dark:text-amber-400 font-normal">未定時間</span>
                                                            </DropdownMenuItem>
                                                        ))}
                                                        {allTrips.length > 1 && (
                                                            <>
                                                                <DropdownMenuSeparator />
                                                                <DropdownMenuItem
                                                                    onClick={() => {
                                                                        haptic.tap()
                                                                        setSchedulingPoi(poi)
                                                                        setSelectedTripForScheduling(null)
                                                                    }}
                                                                    className="text-xs text-[#5C6B68] dark:text-[#A2B1AE] rounded-xl px-2.5 py-1.5 cursor-pointer focus:bg-black/5 dark:focus:bg-white/5 flex items-center justify-between"
                                                                >
                                                                    <span>{t('poi_other_trips') || "選擇其他行程..."}</span>
                                                                    <ChevronRight className="w-3.5 h-3.5 opacity-60" />
                                                                </DropdownMenuItem>
                                                            </>
                                                        )}
                                                    </DropdownMenuContent>
                                                </DropdownMenu>
                                            ) : (
                                                // 首頁模式：點擊開啟全景式雙階排程對話框 (Step 1 選擇行程 -> Step 2 選擇天數)
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        haptic.tap()
                                                        setSchedulingPoi(poi)
                                                        setSelectedTripForScheduling(null)
                                                    }}
                                                    className="px-3 py-1.5 rounded-xl bg-linear-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white text-xs font-bold shadow-xs flex items-center gap-1 active:scale-95 transition-all"
                                                >
                                                    <Plus className="w-3.5 h-3.5" />
                                                    <span>{t('poi_add_to_trip') || "排入行程"}</span>
                                                </button>
                                            )}

                                            {/* 🗑️ 刪除按鈕 */}
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    if (window.confirm(t('poi_delete_confirm') || "確定要從口袋名單中移除此景點？")) {
                                                        deletePoi(poi.id)
                                                    }
                                                }}
                                                className="p-1.5 rounded-xl text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors"
                                                title={t('delete') || "刪除"}
                                            >
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                        </div>
                                    </div>
                                </motion.div>
                            )
                        })
                    )}
                </div>
            </div>

            {/* 🗓️ 雙階行程排程視窗 (Two-Step Trip & Day Triage Modal) */}
            <Dialog
                open={!!schedulingPoi}
                onOpenChange={(open) => {
                    if (!open) {
                        setSchedulingPoi(null)
                        setSelectedTripForScheduling(null)
                    }
                }}
            >
                <DialogContent className="sm:max-w-md rounded-3xl p-5 sm:p-6 bg-white/95 dark:bg-[#1E2927]/95 backdrop-blur-xl border border-black/10 dark:border-white/10 shadow-2xl">
                    {!selectedTripForScheduling ? (
                        // ── STEP 1: 選擇目標行程 ──
                        <div className="space-y-4">
                            <DialogHeader>
                                <DialogTitle className="text-base font-bold text-[#1E2927] dark:text-[#E5EBEA] flex items-center gap-2">
                                    <span className="w-6 h-6 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-xs flex items-center justify-center font-bold">1</span>
                                    <span>{t('poi_select_trip') || "選擇目標行程"}</span>
                                </DialogTitle>
                                <DialogDescription className="text-xs text-[#5C6B68] dark:text-[#A2B1AE]">
                                    {schedulingPoi ? (
                                        <span>將 <strong className="text-[#1E2927] dark:text-[#E5EBEA] font-bold">「{schedulingPoi.title}」</strong> 加入以下哪趟旅程？</span>
                                    ) : (
                                        t('poi_select_trip_desc') || "選擇要加入的地點與行程"
                                    )}
                                </DialogDescription>
                            </DialogHeader>

                            <div className="max-h-72 overflow-y-auto space-y-2 pr-1">
                                {allTrips.length === 0 ? (
                                    <div className="py-8 text-center text-xs text-[#5C6B68] dark:text-[#A2B1AE]">
                                        {t('poi_no_trips') || "目前沒有已建立的行程，請先至首頁建立新行程"}
                                    </div>
                                ) : (
                                    allTrips.map((tr) => {
                                        const daysCount = Array.isArray(tr.days) && tr.days.length > 0 ? tr.days.length : 1
                                        const dateStr = tr.start_date
                                            ? `${tr.start_date.split('T')[0].replace(/-/g, '/')} ~ ${(tr.end_date || tr.start_date).split('T')[0].replace(/-/g, '/')}`
                                            : null

                                        return (
                                            <button
                                                key={tr.id}
                                                type="button"
                                                onClick={() => {
                                                    haptic.selection()
                                                    setSelectedTripForScheduling(tr)
                                                }}
                                                className="w-full text-left p-3.5 rounded-2xl bg-black/3 dark:bg-white/4 hover:bg-emerald-500/10 hover:border-emerald-500/30 border border-transparent transition-all flex items-center justify-between group active:scale-[0.98] cursor-pointer"
                                            >
                                                <div className="min-w-0 flex-1 pr-3">
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-sm">📍</span>
                                                        <h4 className="text-sm font-bold text-[#1E2927] dark:text-[#E5EBEA] truncate group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">
                                                            {tr.title}
                                                        </h4>
                                                    </div>
                                                    <div className="flex items-center gap-2 mt-1 text-[11px] text-[#5C6B68] dark:text-[#A2B1AE]">
                                                        {dateStr && <span>{dateStr}</span>}
                                                        <span className="px-1.5 py-0.2 rounded bg-black/5 dark:bg-white/5 font-mono">
                                                            {daysCount} 天
                                                        </span>
                                                    </div>
                                                </div>
                                                <ChevronRight className="w-4 h-4 text-slate-400 group-hover:text-emerald-500 group-hover:translate-x-0.5 transition-all shrink-0" />
                                            </button>
                                        )
                                    })
                                )}
                            </div>
                        </div>
                    ) : (
                        // ── STEP 2: 選擇排入天數與時間 (Issue #1) ──
                        <div className="space-y-4">
                            <DialogHeader>
                                <div className="flex items-center justify-between mb-1">
                                    <button
                                        type="button"
                                        onClick={() => {
                                            haptic.selection()
                                            setSelectedTripForScheduling(null)
                                        }}
                                        className="text-xs font-bold text-emerald-600 dark:text-emerald-400 hover:underline flex items-center gap-1 cursor-pointer"
                                    >
                                        <ChevronLeft className="w-3.5 h-3.5" />
                                        <span>{t('poi_back_to_trips') || "返回選擇行程"}</span>
                                    </button>
                                    <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[10px] font-bold">
                                        {t('poi_step_2_of_2') || "步驟 2 / 2"}
                                    </span>
                                </div>
                                <DialogTitle className="text-base font-bold text-[#1E2927] dark:text-[#E5EBEA] truncate">
                                    📍 {selectedTripForScheduling.title}
                                </DialogTitle>
                                <DialogDescription className="text-xs text-[#5C6B68] dark:text-[#A2B1AE]">
                                    {t('poi_select_day_and_time') || "請選擇加入第幾天與預計時間："}
                                </DialogDescription>
                            </DialogHeader>

                            {/* 天數選擇區 */}
                            <div className="space-y-1.5">
                                <label className="text-xs font-bold text-[#1E2927] dark:text-[#E5EBEA] flex items-center gap-1">
                                    <span>{t('poi_select_day') || "選擇天數"}</span>
                                    <span className="text-emerald-600 dark:text-emerald-400">*</span>
                                </label>
                                <div className="grid grid-cols-3 gap-2 max-h-36 overflow-y-auto pr-1">
                                    {(Array.isArray(selectedTripForScheduling.days) && selectedTripForScheduling.days.length > 0
                                        ? selectedTripForScheduling.days.map((d) => d.day)
                                        : [1, 2, 3]
                                    ).map((d) => {
                                        let dateLabel = ""
                                        if (selectedTripForScheduling.start_date) {
                                            const [sy, sm, sd] = selectedTripForScheduling.start_date.split('T')[0].split('-').map(Number)
                                            const dt = new Date(sy, sm - 1, sd + (d - 1))
                                            dateLabel = `${dt.getMonth() + 1}/${dt.getDate()} (${["日", "一", "二", "三", "四", "五", "六"][dt.getDay()]})`
                                        }
                                        const isSelected = selectedDayForScheduling === d

                                        return (
                                            <button
                                                key={d}
                                                type="button"
                                                onClick={() => {
                                                    haptic.selection()
                                                    setSelectedDayForScheduling(d)
                                                }}
                                                className={cn(
                                                    "p-2 rounded-2xl border transition-all text-center flex flex-col items-center justify-center gap-0.5 active:scale-95 cursor-pointer",
                                                    isSelected
                                                        ? "bg-emerald-600 text-white border-emerald-600 shadow-md font-bold"
                                                        : "bg-black/3 dark:bg-white/4 hover:bg-black/5 dark:hover:bg-white/10 text-[#1E2927] dark:text-[#E5EBEA] border-black/5 dark:border-white/5"
                                                )}
                                            >
                                                <span className="text-xs font-bold">
                                                    {t('poi_day_n', { day: d }) || `第 ${d} 天`}
                                                </span>
                                                {dateLabel && (
                                                    <span className={cn("text-[9px]", isSelected ? "text-white/80" : "text-[#5C6B68] dark:text-[#A2B1AE]")}>
                                                        {dateLabel}
                                                    </span>
                                                )}
                                            </button>
                                        )
                                    })}
                                </div>
                            </div>

                            {/* ⏰ 時間選擇區 (Issue #1) */}
                            <div className="space-y-2 pt-2 border-t border-black/5 dark:border-white/10">
                                <div className="flex items-center justify-between">
                                    <label className="text-xs font-bold text-[#1E2927] dark:text-[#E5EBEA] flex items-center gap-1">
                                        <Clock className="w-3.5 h-3.5 text-[#E56E25]" />
                                        <span>{t('poi_time_optional') || "預計時間 (選填)"}</span>
                                    </label>
                                    <span className="text-[10px] font-mono font-bold text-emerald-600 dark:text-emerald-400">
                                        {selectedTimeForScheduling}
                                    </span>
                                </div>

                                {/* 快捷時段膠囊 */}
                                <div className="flex flex-wrap gap-1.5">
                                    {[
                                        { label: t('poi_time_unset') || "未定", value: "未定" },
                                        { label: "09:00 上午", value: "09:00" },
                                        { label: "12:00 午餐", value: "12:00" },
                                        { label: "14:30 下午", value: "14:30" },
                                        { label: "18:30 晚餐", value: "18:30" },
                                        { label: "20:30 宵夜", value: "20:30" },
                                    ].map((tp) => (
                                        <button
                                            key={tp.label}
                                            type="button"
                                            onClick={() => {
                                                haptic.selection()
                                                setSelectedTimeForScheduling(tp.value)
                                            }}
                                            className={cn(
                                                "px-2.5 py-1 rounded-full text-[11px] font-semibold transition-all active:scale-95 cursor-pointer",
                                                selectedTimeForScheduling === tp.value
                                                    ? "bg-[#1E2927] text-white dark:bg-[#E5EBEA] dark:text-[#121A18] shadow-xs"
                                                    : "bg-black/5 dark:bg-white/5 text-[#5C6B68] dark:text-[#A2B1AE] hover:bg-black/10"
                                            )}
                                        >
                                            {tp.label}
                                        </button>
                                    ))}
                                </div>

                                {/* 自訂精確時間輸入 */}
                                <div className="flex items-center gap-2 pt-1">
                                    <span className="text-[11px] text-[#5C6B68] dark:text-[#A2B1AE]">{t('poi_custom_time') || "或自訂時間："}</span>
                                    <input
                                        type="time"
                                        value={selectedTimeForScheduling === "未定" ? "" : selectedTimeForScheduling}
                                        onChange={(e) => {
                                            if (e.target.value) {
                                                setSelectedTimeForScheduling(e.target.value)
                                            }
                                        }}
                                        className="px-2 py-1 rounded-xl bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/10 text-xs font-mono text-[#1E2927] dark:text-[#E5EBEA] focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                                    />
                                    {selectedTimeForScheduling !== "未定" && (
                                        <button
                                            type="button"
                                            onClick={() => setSelectedTimeForScheduling("未定")}
                                            className="text-[10px] text-slate-400 hover:text-slate-600 underline"
                                        >
                                            {t('poi_reset_time') || "重設為未定"}
                                        </button>
                                    )}
                                </div>
                            </div>

                            {/* 確認排入按鈕 */}
                            <button
                                type="button"
                                onClick={async () => {
                                    if (schedulingPoi && selectedTripForScheduling && selectedDayForScheduling) {
                                        await handleSchedulePoi(
                                            selectedTripForScheduling,
                                            selectedDayForScheduling,
                                            schedulingPoi,
                                            selectedTimeForScheduling
                                        )
                                        setSchedulingPoi(null)
                                        setSelectedTripForScheduling(null)
                                        setSelectedTimeForScheduling("未定")
                                    }
                                }}
                                className="w-full py-3 rounded-2xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-sm shadow-md active:scale-[0.98] transition-all flex items-center justify-center gap-2 cursor-pointer mt-2"
                            >
                                <Plus className="w-4 h-4" />
                                <span>
                                    排入第 {selectedDayForScheduling} 天行程
                                    {selectedTimeForScheduling !== "未定" ? ` (${selectedTimeForScheduling})` : ""}
                                </span>
                            </button>
                        </div>
                    )}
                </DialogContent>
            </Dialog>
        </div>
    )
}
