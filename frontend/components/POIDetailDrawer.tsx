"use client"

import { useState, useEffect, useCallback } from "react"
import { motion, AnimatePresence, type PanInfo } from "framer-motion"

export type POIDrawerDetent = "peek" | "half" | "full"

const SPRING_CONFIG = {
    type: "spring",
    stiffness: 380,
    damping: 32,
    mass: 0.8,
} as const
import {
    X, MapPin, Phone, Globe, Clock,
    Navigation, Share2, Plus, Sparkles,
    ExternalLink, Image as ImageIcon, Loader2,
    BookOpen, Tent, AlertCircle, Plane
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { useHaptic } from "@/lib/hooks"
import { poiApi } from "@/lib/api"
import { useLanguage } from "@/lib/LanguageContext"
import { getSecureApiKey } from "@/lib/security"
import { openExternalLink } from "@/lib/utils"
import { isMapillaryAvailable } from "@/lib/mapillary"
import { Camera } from "lucide-react"

export interface ClusterItem {
    id?: string;
    lat: number;
    lng: number;
    place: string;
    number: number;
    time?: string;
    category?: string;
    desc?: string;
    notes?: string;
    time_slot?: string;
}

// POI 基礎資料 (來自 OSM 向量圖層)
export interface POIBasicData {
    name: string
    type: string  // restaurant, cafe, shop, etc.
    address?: string
    lat: number
    lng: number
    phone?: string
    website?: string
    opening_hours?: string
    photo_url?: string   // 🆕 Optional photo from external sources
    image_url?: string   // 🆕 Alternative image field
    clusterItems?: ClusterItem[] // 🆕 Added for Cluster Support
    number?: number      // 🆕 Added for Itinerary Sequence
    poi_id?: string;      // 🆕 Added for precise caching
    wikidata_id?: string; // 🆕 Added for precise caching
}

// AI 增強資料
export interface POIEnrichData {
    summary: string;
    must_try: string[];
    rating: number;
    cultural_desc?: string;       // Layer 2: Wikipedia (Primary)
    travel_tips?: string;         // Layer 3: WikiVoyage (Secondary)
    resolved_language?: string;   // BCP 47 (e.g., "zh-TW")
    image_url?: string;           // 🆕 Phase 5: Wikipedia/Wikidata image
    status: "SUCCESS" | "PARTIAL_SUCCESS" | "FAILED";
    warnings?: string[];
}

interface POIDetailDrawerProps {
    isOpen: boolean
    onClose: () => void
    poi: POIBasicData | null
    onAddToItinerary?: (poi: POIBasicData, time: string, aiSummary?: POIEnrichData) => void
    suggestedTime?: string  // 建議時間 (來自父組件計算)
    isInternal?: boolean    // 🆕 是否在容器內部 (例如地圖內)
    onSelectClusterItem?: (item: ClusterItem) => void // 🆕 點擊群聚項目
    onOpenStreetView?: (lat: number, lng: number) => void // 📸 街景按鈕
    onFlyover?: (lat: number, lng: number) => void // ✈️ 3D 飛越按鈕
}

export default function POIDetailDrawer({
    isOpen,
    onClose,
    poi,
    onAddToItinerary,
    suggestedTime = "10:00",
    isInternal = false,
    onSelectClusterItem,
    onOpenStreetView,
    onFlyover
}: POIDetailDrawerProps) {
    const haptic = useHaptic()
    const { t } = useLanguage()
    const [aiData, setAiData] = useState<POIEnrichData | null>(null)
    const [aiLoading, setAiLoading] = useState(false)
    const [aiError, setAiError] = useState<string | null>(null)
    const [selectedTime, setSelectedTime] = useState(suggestedTime)
    const [isSharing, setIsSharing] = useState(false)
    const [detent, setDetent] = useState<POIDrawerDetent>("half")

    // 🚀 Phase 3 Logic Guards (Unified Flow)
    const isLegacy = aiData && !('status' in aiData)
    const effectiveStatus = isLegacy ? undefined : aiData?.status
    
    const hasSummary = !!aiData?.summary?.trim()
    const hasCulturalDesc = !!aiData?.cultural_desc?.trim()
    const hasTravelTips = !!aiData?.travel_tips?.trim()
    const hasRenderableEnrichContent = hasSummary || hasCulturalDesc || hasTravelTips
    
    const showSkeleton = aiLoading && !hasRenderableEnrichContent
    const showWikipediaHint = effectiveStatus === "PARTIAL_SUCCESS" && !hasCulturalDesc
    const isFailed = effectiveStatus === "FAILED"

    // 🛡️ 狀態重置：當 POI 變更或關閉時清除舊資料並回歸半屏預設
    useEffect(() => {
        setAiData(null)
        setAiError(null)
        setAiLoading(false)
        setSelectedTime(suggestedTime)
        setDetent("half")
    }, [poi?.name, poi?.lat, poi?.lng, suggestedTime, isOpen])

    // 🖐️ iOS 智慧手勢吸附判定
    const handleDragEnd = useCallback(
        (_: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => {
            const { offset, velocity } = info

            // 1. 向下快速甩動 (velocity.y > 550) 或超大幅度下拉 (offset.y > 140) -> 關閉
            if (velocity.y > 550 || offset.y > 140) {
                haptic.tap()
                onClose()
                return
            }

            // 2. Full 檔位邏輯
            if (detent === "full") {
                if (offset.y > 45 || velocity.y > 200) {
                    haptic.selection()
                    setDetent("half")
                }
                return
            }

            // 3. Half 檔位邏輯
            if (detent === "half") {
                if (offset.y < -45 || velocity.y < -200) {
                    haptic.selection()
                    setDetent("full")
                } else if (offset.y > 50 || velocity.y > 200) {
                    haptic.selection()
                    setDetent("peek")
                }
                return
            }

            // 4. Peek 檔位邏輯
            if (detent === "peek") {
                if (offset.y < -30 || velocity.y < -150) {
                    haptic.selection()
                    setDetent("half")
                } else if (offset.y > 45) {
                    haptic.tap()
                    onClose()
                }
                return
            }
        },
        [detent, haptic, onClose]
    )

    // 視窗高度映射：isInternal (地圖容器內) 採百分比，全域模式採 vh
    const heightClass = (() => {
        if (detent === "peek") return "h-[110px]"
        if (detent === "full") return isInternal ? "h-[92%]" : "h-[90vh]"
        return isInternal ? "h-[56%] min-h-[360px]" : "h-[58vh] min-h-[360px]"
    })()

    if (!poi) return null

    // 類別圖示對照
    const getTypeIcon = (type: string) => {
        const typeMap: Record<string, string> = {
            restaurant: "🍽️",
            cafe: "☕",
            bar: "🍺",
            shop: "🛍️",
            hotel: "🏨",
            museum: "🏛️",
            park: "🌳",
            temple: "⛩️",
            default: "📍"
        }
        return typeMap[type.toLowerCase()] || typeMap.default
    }

    // 深層連結：Google Maps 導航
    const handleNavigate = () => {
        haptic.tap()
        const url = `https://www.google.com/maps/dir/?api=1&destination=${poi.lat},${poi.lng}`
        openExternalLink(url)
    }

    // 深層連結：Google Image 搜尋（包含位置資訊）
    const handleViewPhotos = () => {
        haptic.tap()
        // 優先用地址，其次用坐標（給 Google 提示是日本的店）
        let locationHint = ''
        if (poi.address) {
            locationHint = poi.address.split(',')[0]
        } else if (aiData?.resolved_language) {
            // 🆕 根據解析語言提供動態地理提示 (Phase 6.3)
            const lang = aiData.resolved_language.toLowerCase()
            if (lang.includes('fa')) locationHint = '伊朗 Iran'
            else if (lang.includes('ja')) locationHint = '日本 Japan'
            else if (lang.includes('ko')) locationHint = '韓國 Korea'
            else if (lang.includes('fr')) locationHint = '法國 France'
            else if (lang.includes('de')) locationHint = '德國 Germany'
        }
        const query = encodeURIComponent(`${poi.name} ${locationHint}`.trim())
        const url = `https://www.google.com/search?tbm=isch&q=${query}`
        openExternalLink(url)
    }

    // Web Share API
    const handleShare = async () => {
        if (isSharing) return
        haptic.tap()

        if (navigator.share) {
            setIsSharing(true)
            try {
                await navigator.share({
                    title: poi.name,
                    text: `${poi.name} - ${poi.type}`,
                    url: `https://www.google.com/maps/search/?api=1&query=${poi.lat},${poi.lng}`
                })
            } catch (err) {
                const error = err as Error
                if (error.name !== 'AbortError' && error.name !== 'InvalidStateError') {
                    console.error("POI Share failed:", err)
                }
            } finally {
                setIsSharing(false)
            }
        }
    }

    // 加入行程
    const handleAddToItinerary = () => {
        haptic.success()
        onAddToItinerary?.(poi, selectedTime, aiData || undefined)
        onClose()
    }

    // AI 分析 (Layer 2)
    const handleAIAnalyze = async () => {

        haptic.tap()
        setAiLoading(true)
        setAiError(null)

        try {
            const userId = localStorage.getItem("user_uuid") || ""
            const data = await poiApi.enrich({
                name: poi.name,
                type: poi.type,
                lat: poi.lat,
                lng: poi.lng,
                api_key: getSecureApiKey(),
                poi_id: poi.poi_id,
                wikidata_id: poi.wikidata_id
            }, userId)

            setAiData(data)
        } catch {
            setAiError(t('poi_ai_failed'))
        } finally {
            setAiLoading(false)
        }
    }

    return (
        <AnimatePresence>
            {isOpen && (
                <>
                    {/* 1. 階梯式背景遮罩 (Peek 完全無遮罩可操作地圖, Half 輕遮罩, Full 高斯模糊) */}
                    {detent !== "peek" && (
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: 0.2 }}
                            onClick={() => {
                                haptic.tap()
                                if (detent === "full") {
                                    setDetent("half")
                                } else {
                                    onClose()
                                }
                            }}
                            className={`${isInternal ? 'absolute' : 'fixed'} inset-0 transition-colors duration-300 ${isInternal ? 'z-40' : 'z-100'} ${detent === "full" ? 'bg-black/50 backdrop-blur-sm' : 'bg-black/20'}`}
                        />
                    )}

                    {/* 2. Drawer 主體面板 */}
                    <motion.div
                        initial={{ y: "100%" }}
                        animate={{ y: 0 }}
                        exit={{ y: "100%" }}
                        transition={SPRING_CONFIG}
                        className={`${isInternal ? 'absolute' : 'fixed'} bottom-0 left-0 right-0 ${isInternal ? 'z-50 border-t border-x border-slate-200/80 dark:border-slate-800' : 'z-100 shadow-2xl border-t border-slate-200/80 dark:border-slate-800'} bg-white/96 dark:bg-slate-900/96 backdrop-blur-xl saturate-180 shadow-[inset_0_1.5px_1px_0_rgba(255,255,255,0.8),0_-8px_32px_rgba(0,0,0,0.12)] dark:shadow-[inset_0_1px_0.5px_0_rgba(255,255,255,0.1),0_-8px_32px_rgba(0,0,0,0.3)] rounded-t-3xl overflow-hidden flex flex-col ${heightClass} transition-[height] duration-300 ease-out`}
                    >
                        {/* 3. 頂部拖曳把手與操作列 (Touch Delegation for Drag) */}
                        <motion.div
                            drag="y"
                            dragConstraints={{ top: 0, bottom: 0 }}
                            dragElastic={{ top: 0.1, bottom: 0.6 }}
                            onDragEnd={handleDragEnd}
                            style={{ touchAction: "pan-y" }}
                            className="w-full pt-2.5 pb-2 px-4 flex flex-col items-center cursor-grab active:cursor-grabbing select-none shrink-0"
                        >
                            {/* iOS Drag Pill - 點擊可在 peek 與 half 之間快速切換 */}
                            <button
                                type="button"
                                onClick={() => {
                                    haptic.selection()
                                    setDetent(prev => prev === "peek" ? "half" : "peek")
                                }}
                                className="py-1 px-4 -my-1 cursor-pointer focus:outline-none"
                                aria-label="Toggle Detent"
                            >
                                <div className="w-11 h-1.5 rounded-full bg-slate-300/80 dark:bg-slate-600/80 hover:bg-slate-400 dark:hover:bg-slate-500 transition-colors shadow-[inset_0_1px_1px_rgba(0,0,0,0.1)]" />
                            </button>

                            {/* 頂部操作列：分類標籤、檔位切換按鈕、關閉按鈕 */}
                            <div className="w-full flex items-center justify-between mt-1 px-1">
                                <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 tracking-wide flex items-center gap-1.5 min-w-0">
                                    <span className="shrink-0">{poi.type === 'cluster' ? '📑' : getTypeIcon(poi.type)}</span>
                                    <span className="truncate max-w-35 sm:max-w-50">
                                        {poi.type === 'cluster'
                                            ? (poi.clusterItems ? `群聚清單 (${poi.clusterItems.length})` : poi.name)
                                            : poi.name}
                                    </span>
                                </span>

                                <div className="flex items-center gap-1.5 shrink-0">
                                    {/* 展開/收合檔位按鈕 */}
                                    <button
                                        type="button"
                                        onClick={() => {
                                            haptic.selection()
                                            setDetent(prev => {
                                                if (prev === "peek") return "half"
                                                if (prev === "half") return "full"
                                                return "half"
                                            })
                                        }}
                                        className="text-xs font-semibold px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors cursor-pointer"
                                    >
                                        {detent === "full" ? "半屏" : (detent === "half" ? "全屏" : "展開")}
                                    </button>

                                    {/* 圓形關閉按鈕 */}
                                    <button
                                        type="button"
                                        onClick={() => {
                                            haptic.tap()
                                            onClose()
                                        }}
                                        className="p-1 rounded-full text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-all active:scale-90 cursor-pointer"
                                        aria-label="Close"
                                    >
                                        <X className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                        </motion.div>

                        {/* 4. 內容主體區 */}
                        {detent === "peek" ? (
                            /* 🆕 PEEK 最小化狀態 (保留原本收起的精練特色) */
                            <div
                                onClick={() => {
                                    haptic.selection()
                                    setDetent("half")
                                }}
                                className="px-5 pb-3 flex items-center justify-between gap-3 cursor-pointer select-none"
                            >
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                        <h3 className="text-sm font-bold text-slate-900 dark:text-white truncate">{poi.name}</h3>
                                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500 font-medium shrink-0">
                                            {poi.type}
                                        </span>
                                    </div>
                                    <p className="text-xs text-slate-500 truncate mt-0.5">{poi.address || poi.type || "點擊或上滑展開詳情"}</p>
                                </div>
                                <span className="text-xs font-bold text-indigo-600 dark:text-indigo-400 shrink-0">
                                    向上展開 ↑
                                </span>
                            </div>
                        ) : poi.type === 'cluster' ? (
                            /* 🆕 CLUSTER LIST VIEW (群聚清單流式滾動 - 軸向嚴格鎖定) */
                            <div 
                                className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden touch-pan-y overscroll-x-none overscroll-y-contain px-5 pb-6 space-y-4"
                                style={{ touchAction: "pan-y" }}
                            >
                                <div className="flex items-center gap-2 mb-2">
                                    <div className="w-1.5 h-6 bg-indigo-500 rounded-full" />
                                    <h3 className="text-lg font-black text-slate-900 dark:text-white">{poi.name}</h3>
                                </div>
                                <div className="grid gap-2 pr-1">
                                    {poi.clusterItems?.map((item, idx) => (
                                        <button
                                            key={item.id || idx}
                                            onClick={() => {
                                                haptic.tap();
                                                if (onSelectClusterItem) {
                                                    onSelectClusterItem(item);
                                                } else {
                                                    onAddToItinerary?.({
                                                        name: item.place,
                                                        type: item.category || 'sightseeing',
                                                        lat: item.lat,
                                                        lng: item.lng,
                                                        address: item.desc || item.notes
                                                    }, item.time || "10:00");
                                                }
                                            }}
                                            className="w-full text-left p-4 bg-slate-50 dark:bg-slate-800 hover:bg-indigo-50 dark:hover:bg-indigo-900/40 rounded-2xl border border-slate-100 dark:border-slate-800 transition-all active:scale-[0.98] group"
                                        >
                                            <div className="flex items-center justify-between">
                                                <div className="flex items-center gap-3">
                                                    <div className="w-8 h-8 rounded-full bg-indigo-500 text-white flex items-center justify-center text-xs font-black shadow-lg shadow-indigo-500/20">
                                                        {item.number}
                                                    </div>
                                                    <div>
                                                        <div className="text-sm font-bold text-slate-900 dark:text-white group-hover:text-indigo-600 transition-colors truncate">{item.place}</div>
                                                        <div className="text-[10px] text-slate-400 font-mono mt-0.5">{item.time || item.time_slot || '--:--'}</div>
                                                    </div>
                                                </div>
                                                <div className="text-slate-300 group-hover:translate-x-1 transition-transform">→</div>
                                            </div>
                                        </button>
                                    ))}
                                </div>
                                <p className="text-[10px] text-slate-400 text-center italic">{t('poi_tap_to_view')}</p>
                            </div>
                        ) : (
                            /* 🆕 POI DETAIL VIEW (景點詳情流式滾動 - 四重軸向鎖定) */
                            <div 
                                className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden touch-pan-y overscroll-x-none overscroll-y-contain px-5 pb-6 space-y-4"
                                style={{ touchAction: "pan-y" }}
                            >
                                {/* ========== Layer 1: OSM 骨架層 ========== */}

                                {/* Header */}
                                <div className="flex items-start gap-3">
                                    {poi.number ? (
                                        <div className="w-10 h-10 rounded-full bg-indigo-500 text-white flex items-center justify-center text-sm font-black shadow-lg shadow-indigo-500/20 shrink-0">
                                            {poi.number}
                                        </div>
                                    ) : (
                                        <span className="text-3xl">{getTypeIcon(poi.type)}</span>
                                    )}
                                    <div className="flex-1 min-w-0">
                                        <h2 className="text-xl font-bold text-slate-900 dark:text-white truncate">
                                            {poi.name}
                                        </h2>
                                        <p className="text-sm text-slate-500 dark:text-slate-400 capitalize">
                                            {poi.type}
                                        </p>
                                    </div>
                                </div>

                                {/* 基礎資訊 (具備視覺呼吸感) */}
                                <div className="space-y-2.5 text-sm">
                                    {poi.address && (
                                        <div className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
                                            <MapPin className="w-4 h-4 shrink-0 text-slate-400" />
                                            <span className="line-clamp-2">{poi.address}</span>
                                        </div>
                                    )}
                                    {poi.phone && (
                                        <a
                                            href={`tel:${poi.phone}`}
                                            className="flex items-center gap-2 text-blue-600 dark:text-blue-400 hover:underline"
                                        >
                                            <Phone className="w-4 h-4 shrink-0" />
                                            <span>{poi.phone}</span>
                                        </a>
                                    )}
                                    {poi.website && (
                                        <button
                                            type="button"
                                            onClick={() => openExternalLink(poi.website)}
                                            className="flex items-center gap-2 text-blue-600 dark:text-blue-400 hover:underline text-left cursor-pointer w-full min-w-0"
                                        >
                                            <Globe className="w-4 h-4 shrink-0" />
                                            <span className="truncate flex-1">{poi.website}</span>
                                            <ExternalLink className="w-3 h-3 shrink-0" />
                                        </button>
                                    )}
                                    {poi.opening_hours && (
                                        <div className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
                                            <Clock className="w-4 h-4 shrink-0 text-slate-400" />
                                            <span>{poi.opening_hours}</span>
                                        </div>
                                    )}
                                </div>

                                {/* 🎯 主行動條 (Primary Action Bar)：整合時間輸入與加入行程，無行程回調時優雅降級為全寬導航 */}
                                {onAddToItinerary ? (
                                    <div className="flex items-center gap-2 p-1.5 bg-slate-100/90 dark:bg-slate-800/90 rounded-2xl border border-slate-200/70 dark:border-slate-700/70 shadow-inner">
                                        <div className="flex items-center gap-1.5 px-3 py-1.5 bg-white dark:bg-slate-700 rounded-xl shadow-xs shrink-0">
                                            <Clock className="w-4 h-4 text-indigo-500 shrink-0" />
                                            <input
                                                type="time"
                                                value={selectedTime}
                                                onChange={(e) => setSelectedTime(e.target.value)}
                                                className="text-xs font-bold text-slate-800 dark:text-slate-100 bg-transparent border-none outline-none p-0 cursor-pointer w-16"
                                                aria-label={t('poi_add_time')}
                                            />
                                        </div>
                                        <Button
                                            onClick={handleAddToItinerary}
                                            className="flex-1 h-10 gap-2 bg-linear-to-r from-indigo-500 via-indigo-600 to-purple-600 hover:from-indigo-600 hover:to-purple-700 text-white font-bold text-xs rounded-xl shadow-md shadow-indigo-500/20 active:scale-[0.98] transition-all min-w-0 cursor-pointer"
                                        >
                                            <Plus className="w-4 h-4 shrink-0" />
                                            <span className="truncate">{t('poi_add_to_trip')}</span>
                                        </Button>
                                    </div>
                                ) : (
                                    <Button
                                        onClick={handleNavigate}
                                        className="w-full h-11 gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-sm rounded-2xl shadow-md shadow-indigo-600/20 active:scale-[0.98] transition-all cursor-pointer"
                                    >
                                        <Navigation className="w-4 h-4 shrink-0" />
                                        <span>{t('tc_navigate')}</span>
                                    </Button>
                                )}

                                {/* 🛠️ Tier 2: 一體化毛玻璃純圖示藥丸島 (Segmented Icon Capsule) */}
                                <div 
                                    className="w-full max-w-sm mx-auto h-12 rounded-2xl bg-slate-100/70 dark:bg-slate-800/60 backdrop-blur-md border border-slate-200/50 dark:border-slate-700/50 shadow-xs flex items-center justify-around px-2 touch-manipulation"
                                    onPointerDown={(e) => e.stopPropagation()}
                                >
                                    {/* 1. 導航按鈕 (僅主行動條有「加入行程」時渲染，避免重複) */}
                                    {onAddToItinerary && (
                                        <button
                                            type="button"
                                            onClick={handleNavigate}
                                            title={t('tc_navigate')}
                                            aria-label={t('tc_navigate')}
                                            className="flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-150 hover:bg-white/80 dark:hover:bg-slate-700/60 active:scale-90 cursor-pointer"
                                        >
                                            <Navigation className="w-4 h-4 text-indigo-500 shrink-0" />
                                        </button>
                                    )}

                                    {/* 2. 街景預覽 */}
                                    {isMapillaryAvailable() && onOpenStreetView && (
                                        <button
                                            type="button"
                                            onClick={() => onOpenStreetView(poi.lat, poi.lng)}
                                            title={t('mapillary_streetview')}
                                            aria-label={t('mapillary_streetview')}
                                            className="flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-150 hover:bg-white/80 dark:hover:bg-slate-700/60 active:scale-90 cursor-pointer"
                                        >
                                            <Camera className="w-4 h-4 text-emerald-500 shrink-0" />
                                        </button>
                                    )}

                                    {/* 3. 3D 飛越 */}
                                    {onFlyover && (
                                        <button
                                            type="button"
                                            onClick={() => onFlyover(poi.lat, poi.lng)}
                                            title={t('flyover_poi')}
                                            aria-label={t('flyover_poi')}
                                            className="flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-150 hover:bg-white/80 dark:hover:bg-slate-700/60 active:scale-90 cursor-pointer"
                                        >
                                            <Plane className="w-4 h-4 text-purple-500 shrink-0" />
                                        </button>
                                    )}

                                    {/* 4. 尋找更多照片 */}
                                    <button
                                        type="button"
                                        onClick={handleViewPhotos}
                                        title={t('poi_more_photos')}
                                        aria-label={t('poi_more_photos')}
                                        className="flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-150 hover:bg-white/80 dark:hover:bg-slate-700/60 active:scale-90 cursor-pointer"
                                    >
                                        <ImageIcon className="w-4 h-4 text-amber-500 shrink-0" />
                                    </button>

                                    {/* 5. 在 Google Maps 打開 (MapPin 具象圖釘) */}
                                    <button
                                        type="button"
                                        onClick={() => {
                                            const url = `https://www.google.com/maps/search/?api=1&query=${poi.lat},${poi.lng}`
                                            openExternalLink(url)
                                        }}
                                        title={t('poi_open_gmaps')}
                                        aria-label={t('poi_open_gmaps')}
                                        className="flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-150 hover:bg-white/80 dark:hover:bg-slate-700/60 active:scale-90 cursor-pointer"
                                    >
                                        <MapPin className="w-4 h-4 text-blue-500 shrink-0" />
                                    </button>

                                    {/* 6. 分享 */}
                                    <button
                                        type="button"
                                        onClick={handleShare}
                                        title={t('share')}
                                        aria-label={t('share')}
                                        className="flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-150 hover:bg-white/80 dark:hover:bg-slate-700/60 active:scale-90 cursor-pointer"
                                    >
                                        <Share2 className="w-4 h-4 text-slate-500 dark:text-slate-400 shrink-0" />
                                    </button>
                                </div>

                                {/* ========== Layer 2: AI 智慧層 ========== */}

                                <div className="border-t border-slate-200 dark:border-slate-700 pt-3">
                                    {!aiData && !aiLoading && (
                                        <Button
                                            onClick={handleAIAnalyze}
                                            variant="outline"
                                            className="w-full h-10 gap-2 bg-purple-50/60 dark:bg-purple-950/20 hover:bg-purple-100/60 dark:hover:bg-purple-900/30 border-purple-200/60 dark:border-purple-800/40 text-purple-700 dark:text-purple-300 text-xs font-bold rounded-xl transition-all active:scale-[0.98] cursor-pointer"
                                        >
                                            <Sparkles className="w-3.5 h-3.5 text-purple-500" />
                                            <span>✨ {t('poi_explore')}</span>
                                        </Button>
                                    )}

                                    {showSkeleton && (
                                        <div className="space-y-4 animate-pulse">
                                            {/* Summary Skeleton */}
                                            <div className="space-y-2">
                                                <div className="flex items-center gap-2">
                                                    <Loader2 className="w-4 h-4 animate-spin text-purple-500" />
                                                    <div className="h-4 bg-purple-100 dark:bg-purple-900/30 rounded w-24" />
                                                </div>
                                                <div className="h-3 bg-slate-200 dark:bg-slate-700 rounded w-full" />
                                                <div className="h-3 bg-slate-200 dark:bg-slate-700 rounded w-5/6" />
                                            </div>
                                            {/* Wikipedia Skeleton */}
                                            <div className="pt-2">
                                                <div className="h-24 bg-slate-100 dark:bg-slate-800 rounded-xl w-full" />
                                            </div>
                                            {/* Travel Tips Skeleton */}
                                            <div>
                                                <div className="h-16 bg-slate-100 dark:bg-slate-800 rounded-xl w-full" />
                                            </div>
                                        </div>
                                    )}

                                    {aiError || (isFailed && !aiLoading) ? (
                                        <div className="flex flex-col items-center gap-3 p-4 bg-red-50 dark:bg-red-900/10 rounded-xl border border-red-100 dark:border-red-800/30">
                                            <AlertCircle className="w-8 h-8 text-red-500 opacity-50" />
                                            <p className="text-sm text-red-600 dark:text-red-400 font-medium">
                                                {aiError || t('poi_ai_failed')}
                                            </p>
                                            <Button 
                                                onClick={handleAIAnalyze}
                                                size="sm"
                                                variant="outline"
                                                className="border-red-200 dark:border-red-800 text-red-600 hover:bg-red-50"
                                            >
                                                重試分析 (Retry)
                                            </Button>
                                        </div>
                                    ) : null}

                                    {aiData && (
                                        <motion.div
                                            initial={{ opacity: 0, y: 10 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            className="space-y-4"
                                        >
                                            {/* Layer 1: AI / Core Summary */}
                                            <div className="bg-linear-to-br from-purple-50 to-indigo-50 dark:from-purple-900/20 dark:to-indigo-900/20 rounded-xl p-4 space-y-3">
                                                <div className="flex items-center gap-2">
                                                    <Sparkles className="w-4 h-4 text-purple-500" />
                                                    <span className="text-sm font-semibold text-purple-700 dark:text-purple-300">
                                                        {t('poi_ai_suggestion')}
                                                    </span>
                                                    {aiData.rating && (
                                                        <span className="ml-auto text-sm font-bold text-amber-600">
                                                            ⭐ {aiData.rating.toFixed(1)}
                                                        </span>
                                                    )}
                                                </div>
                                                <p className="text-sm text-slate-700 dark:text-slate-300">
                                                    {aiData.summary}
                                                </p>
                                                {aiData.must_try && aiData.must_try.length > 0 && (
                                                    <div className="pt-1">
                                                        <p className="text-xs font-semibold text-purple-600 dark:text-purple-400 mb-1">
                                                            🍽️ {t('poi_take_photo')}
                                                        </p>
                                                        <ul className="text-sm text-slate-600 dark:text-slate-400 list-disc list-inside">
                                                            {aiData.must_try.map((item, i) => (
                                                                <li key={i}>{item}</li>
                                                            ))}
                                                        </ul>
                                                    </div>
                                                )}
                                            </div>

                                            {/* Layer 2: Wikipedia Insight (Primary) */}
                                            <div className="space-y-2">
                                                <div className="flex items-center gap-2 px-1">
                                                    <BookOpen className="w-4 h-4 text-indigo-500" />
                                                    <span id="wiki-insight-label" className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                                                        Wikipedia Insight
                                                    </span>
                                                </div>
                                                
                                                <div className="relative min-h-25">
                                                    {hasCulturalDesc ? (
                                                        <div 
                                                            tabIndex={0}
                                                            role="region"
                                                            aria-labelledby="wiki-insight-label"
                                                            className="max-h-35 overflow-y-auto p-4 bg-slate-50 dark:bg-slate-800/50 rounded-xl text-sm text-slate-600 dark:text-slate-300 leading-relaxed focus:ring-2 focus:ring-indigo-500/50 outline-none transition-shadow"
                                                        >
                                                            {aiData.cultural_desc}
                                                            {/* Bottom Fade Overlay */}
                                                            <div className="absolute bottom-0 left-0 right-0 h-8 bg-linear-to-t from-white/90 dark:from-slate-900/90 to-transparent pointer-events-none rounded-b-xl" />
                                                        </div>
                                                    ) : showWikipediaHint ? (
                                                        <div className="p-4 border border-dashed border-slate-200 dark:border-slate-700 rounded-xl flex items-center justify-center gap-2 text-slate-400">
                                                            <AlertCircle className="w-4 h-4" />
                                                            <span className="text-xs italic" aria-live="polite">
                                                                Partial data temporarily unavailable.
                                                            </span>
                                                        </div>
                                                    ) : null}
                                                </div>
                                            </div>

                                            {/* Layer 3: Travel Tips (Secondary) */}
                                            {hasTravelTips && (
                                                <div className="space-y-2">
                                                    <div className="flex items-center gap-2 px-1">
                                                        <Tent className="w-4 h-4 text-emerald-500" />
                                                        <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                                                            Travel Tips
                                                        </span>
                                                    </div>
                                                    <div className="p-4 bg-emerald-50/50 dark:bg-emerald-900/10 border border-emerald-100/50 dark:border-emerald-800/30 rounded-xl text-sm text-slate-600 dark:text-slate-300">
                                                        {aiData.travel_tips}
                                                    </div>
                                                </div>
                                            )}

                                            {/* Layer 4: Meta Footer */}
                                            <div className="flex justify-between items-center pt-2 px-1">
                                                <div className="flex items-center gap-1.5">
                                                    {aiData.status === "PARTIAL_SUCCESS" && (
                                                        <div 
                                                            className="flex items-center gap-1 text-[10px] font-medium text-amber-600 dark:text-amber-500 bg-amber-50 dark:bg-amber-900/20 px-2 py-0.5 rounded-full"
                                                            aria-label="Partial data available"
                                                            title="Some data sources timed out or failed"
                                                        >
                                                            <AlertCircle className="w-3 h-3" />
                                                            <span>PARTIAL</span>
                                                        </div>
                                                    )}
                                                </div>
                                                
                                                {aiData.resolved_language && (
                                                    <div className="flex items-center gap-2 text-[10px] font-bold text-slate-400 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-sm tracking-tighter">
                                                        <span className="opacity-70">RESOURCE LANGUAGE:</span>
                                                        <span className="text-slate-500 dark:text-slate-300 uppercase">{aiData.resolved_language.toUpperCase()}</span>
                                                    </div>
                                                )}
                                            </div>
                                        </motion.div>
                                    )}
                                </div>
                            </div>
                        )}
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    )
}
