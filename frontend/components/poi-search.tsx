"use client"

import { useRef, useState } from "react"
import { MapPin, Plus, Sparkles, Loader2, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { poiApi } from "@/lib/api"
import { useLanguage } from "@/lib/LanguageContext"
import { getSecureApiKey } from "@/lib/security"


// POI 類別定義
const POI_CATEGORIES = [
    { id: "department_store", name: "百貨", icon: "🏬" },
    { id: "restaurant", name: "美食", icon: "🍽️" },
    { id: "convenience", name: "超商", icon: "🏪" },
    { id: "supermarket", name: "超市", icon: "🛒" },
    { id: "pharmacy", name: "藥局", icon: "💊" },
    { id: "popular", name: "熱門", icon: "🔥" }
]

// Category name lookup for i18n
const CATEGORY_KEYS: Record<string, string> = {
    department_store: 'ps_department',
    restaurant: 'ps_restaurant',
    convenience: 'ps_convenience',
    supermarket: 'ps_supermarket',
    pharmacy: 'ps_pharmacy',
    popular: 'ps_popular'
}

interface POI {
    id: string
    name: string
    category: string
    lat: number
    lng: number
    distance?: number
    rating?: number
    opening_hours?: string
    address?: string
    phone?: string
    website?: string
    source?: string
}

interface POISearchProps {
    centerLat: number
    centerLng: number
    onSelectPOI?: (poi: POI) => void
    className?: string
}

export function POISearch({ centerLat, centerLng, onSelectPOI, className }: POISearchProps) {
    const { t, lang } = useLanguage()
    const zh = lang === "zh"
    const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
    const [pois, setPois] = useState<POI[]>([])
    const [isLoading, setIsLoading] = useState(false)
    const [searchError, setSearchError] = useState<string | null>(null)
    const [aiRecommendation, setAiRecommendation] = useState<string | null>(null)
    const [isAiLoading, setIsAiLoading] = useState(false)
    const requestSeqRef = useRef(0)

    const runCategorySearch = async (categoryId: string) => {
        const seq = ++requestSeqRef.current
        setSelectedCategory(categoryId)
        setIsLoading(true)
        setSearchError(null)
        setPois([])
        setAiRecommendation(null)

        try {
            const userId = localStorage.getItem("user_uuid") || ""
            const data = await poiApi.nearby(centerLat, centerLng, categoryId, userId)
            if (requestSeqRef.current !== seq) return
            setPois(Array.isArray(data?.pois) ? data.pois : [])
        } catch (e) {
            if (requestSeqRef.current !== seq) return
            console.error("POI search error:", e)
            setSearchError(zh ? "周邊景點載入失敗，請稍後重試" : "Failed to load nearby places. Please try again.")
        } finally {
            if (requestSeqRef.current === seq) {
                setIsLoading(false)
            }
        }
    }

    const handleCategoryClick = async (categoryId: string) => {
        if (selectedCategory === categoryId) {
            // 再次點擊同類別 = 取消搜索並作廢在途請求
            requestSeqRef.current += 1
            setSelectedCategory(null)
            setIsLoading(false)
            setSearchError(null)
            setPois([])
            setAiRecommendation(null)
            return
        }

        await runCategorySearch(categoryId)
    }

    const handleAiRecommend = async () => {
        if (pois.length === 0) return

        setIsAiLoading(true)
        setAiRecommendation(null)

        try {
            const apiKey = getSecureApiKey()

            if (!apiKey) {
                setAiRecommendation(t('ps_no_api_key'))
                return
            }

            const userId = localStorage.getItem("user_uuid") || ""
            const data = await poiApi.recommend({
                pois: pois.slice(0, 10),
                user_query: zh ? "請推薦最適合觀光客的一間，說明原因。" : "Please recommend the best spot for tourists and explain why.",
                api_key: apiKey,
                user_preferences: JSON.parse(localStorage.getItem("poi_preferences") || "{}"),
                locale: lang
            }, userId)
            setAiRecommendation(data.recommendation)
        } catch (e) {
            console.error("AI recommend error:", e)
            setAiRecommendation(t('ps_ai_failed'))
        } finally {
            setIsAiLoading(false)
        }
    }

    const getRatingStars = (rating?: number) => {
        if (!rating) return null
        const normalized = Math.min(5, Math.round(rating / 2))
        return "⭐".repeat(normalized)
    }

    return (
        <div className={className}>
            {/* 類別快速按鈕列 */}
            <div className="flex flex-wrap gap-2 py-2">
                {POI_CATEGORIES.map((cat) => (
                    <button
                        type="button"
                        key={cat.id}
                        onClick={() => handleCategoryClick(cat.id)}
                        className={`flex-shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-full text-sm font-medium transition-all ${selectedCategory === cat.id
                            ? "bg-amber-500 text-white shadow-md"
                            : "bg-secondary border border-input text-secondary-foreground hover:bg-secondary/80"
                            }`}
                    >
                        <span>{cat.icon}</span>
                        <span>{t(CATEGORY_KEYS[cat.id] as Parameters<typeof t>[0]) || cat.name}</span>
                    </button>
                ))}
            </div>

            {/* 搜索結果 / 空狀態 / 錯誤重試 */}
            {selectedCategory !== null && (
                <div className="mt-3">
                    {isLoading ? (
                        <div className="flex items-center justify-center py-8 text-slate-400">
                            <Loader2 className="w-5 h-5 animate-spin mr-2" />
                            <span>{t('ps_searching')}</span>
                        </div>
                    ) : searchError ? (
                        <div className="flex flex-col items-center justify-center gap-2 py-6 px-3 rounded-xl border border-dashed border-red-200 dark:border-red-900/50 bg-red-50/40 dark:bg-red-950/20 text-center">
                            <p className="text-xs text-red-600 dark:text-red-400">{searchError}</p>
                            <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => runCategorySearch(selectedCategory)}
                                className="h-7 text-xs gap-1.5"
                            >
                                <RefreshCw className="w-3.5 h-3.5" />
                                {zh ? "重試" : "Retry"}
                            </Button>
                        </div>
                    ) : pois.length === 0 ? (
                        <div className="flex items-center justify-center py-6 px-3 rounded-xl border border-dashed border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/30 text-xs text-slate-500 dark:text-slate-400 text-center">
                            {zh ? "附近暫無此類別地點，請嘗試其他類別" : "No nearby places found in this category"}
                        </div>
                    ) : (
                        <>
                            {/* AI 推薦按鈕 */}
                            <div className="flex justify-between items-center mb-2">
                                <span className="text-xs text-slate-500 dark:text-slate-400">
                                    {t('ps_result_count', { count: String(pois.length) })}
                                </span>
                                <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    onClick={handleAiRecommend}
                                    disabled={isAiLoading}
                                    className="text-amber-600 dark:text-amber-400 hover:text-amber-700 hover:bg-amber-50 dark:hover:bg-amber-950/40"
                                >
                                    {isAiLoading ? (
                                        <Loader2 className="w-4 h-4 animate-spin mr-1" />
                                    ) : (
                                        <Sparkles className="w-4 h-4 mr-1" />
                                    )}
                                    {t('ps_ai_recommend')}
                                </Button>
                            </div>

                            {/* AI 推薦結果 */}
                            {aiRecommendation && (
                                <Card className="p-3 mb-3 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-950/40 dark:to-orange-950/30 border-amber-200 dark:border-amber-800/60">
                                    <div className="flex items-start gap-2">
                                        <Sparkles className="w-4 h-4 text-amber-500 mt-0.5 flex-shrink-0" />
                                        <p className="text-sm text-slate-700 dark:text-amber-100">{aiRecommendation}</p>
                                    </div>
                                </Card>
                            )}

                            {/* POI 列表 (支援 20 筆結果獨立垂直滾動) */}
                            <div
                                data-testid="poi-results-scroll-container"
                                className="max-h-[300px] overflow-y-auto overflow-x-hidden touch-pan-y overscroll-x-none overscroll-y-contain pr-1"
                                style={{ touchAction: "pan-y" }}
                            >
                                <div className="space-y-2">
                                    {pois.map((poi) => (
                                        <div
                                            key={poi.id}
                                            className="p-3 bg-card rounded-lg border border-border hover:border-amber-300 hover:shadow-sm transition-all cursor-pointer"
                                            onClick={() => onSelectPOI?.(poi)}
                                        >
                                            <div className="flex justify-between items-start">
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2 min-w-0">
                                                        <MapPin className="w-3.5 h-3.5 text-slate-400" />
                                                        <span className="font-medium text-slate-800 dark:text-slate-100 text-sm truncate">
                                                            {poi.name}
                                                        </span>
                                                    </div>
                                                    <div className="flex items-center gap-3 mt-1 text-xs text-slate-500 dark:text-slate-400">
                                                        <span>{poi.distance}m</span>
                                                        {poi.rating && (
                                                            <span>{getRatingStars(poi.rating)}</span>
                                                        )}
                                                        {poi.opening_hours && (
                                                            <span className="truncate max-w-[120px]">
                                                                {poi.opening_hours}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                                {onSelectPOI && (
                                                    <Button
                                                        type="button"
                                                        variant="ghost"
                                                        size="sm"
                                                        className="h-7 w-7 p-0 text-slate-400 hover:text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-950/40"
                                                        onClick={(e) => {
                                                            e.stopPropagation()
                                                            onSelectPOI(poi)
                                                        }}
                                                    >
                                                        <Plus className="w-4 h-4" />
                                                    </Button>
                                                )}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </>
                    )}
                </div>
            )}
        </div>
    )
}
