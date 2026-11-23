"use client"

import { useState, useRef, useEffect } from "react"
import { Search, Loader2 } from "lucide-react"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { toast } from "sonner"
import { GeocodeResult, DailyLocation, Trip, LocationInfo } from "@/lib/itinerary-types"
import { geocodeApi } from "@/lib/api"
import { dedupeGeocodeResults } from "@/lib/location-utils"
import { COUNTRY_REGIONS } from "@/lib/constants"
import { useLanguage } from "@/lib/LanguageContext"

const INCOMPLETE_ZHUYIN_RE = /[\u3100-\u312F\u31A0-\u31BF]/

interface LocationEditDialogProps {
    isOpen: boolean
    onOpenChange: (open: boolean) => void
    day: number
    dailyLocs: Record<number | string, DailyLocation>
    setDailyLocs: (locs: Record<number | string, DailyLocation>) => void
    currentTrip?: Trip
    biasLoc?: { lat: number, lng: number } // 🆕 Smart Geocoding Bias
}

export function LocationEditDialog({
    isOpen,
    onOpenChange,
    day,
    dailyLocs,
    setDailyLocs,
    currentTrip,
    biasLoc,    // 🆕 Smart Geocoding Bias
}: LocationEditDialogProps) {
    const { t, lang } = useLanguage()
    const zh = lang === 'zh'
    const [searchCountry, setSearchCountry] = useState("")
    const [dailyLocSearchRegion, setDailyLocSearchRegion] = useState("")
    const [newLocName, setNewLocName] = useState("")
    const [locSearchResults, setLocSearchResults] = useState<GeocodeResult[]>([])
    const [isLocSearching, setIsLocSearching] = useState(false)
    const [isSelectingLocation, setIsSelectingLocation] = useState(false)
    const isComposingRef = useRef(false)
    const abortControllerRef = useRef<AbortController | null>(null)
    const requestSeqRef = useRef(0)

    // 🛡️ 開關或切換天數時立即作廢在途搜尋並清空舊列表（防止跨日殘留舊結果或競態覆寫）
    useEffect(() => {
        abortControllerRef.current?.abort()
        requestSeqRef.current += 1
        setLocSearchResults([])
        setIsLocSearching(false)
        return () => {
            abortControllerRef.current?.abort()
        }
    }, [isOpen, day])

    const handleSearchLocation = async () => {
        const trimmed = newLocName.trim()
        if (!trimmed || INCOMPLETE_ZHUYIN_RE.test(trimmed)) return
        abortControllerRef.current?.abort()
        const controller = new AbortController()
        abortControllerRef.current = controller
        const seq = ++requestSeqRef.current
        setIsLocSearching(true)
        try {
            const data = await geocodeApi.search({
                query: trimmed,
                country: searchCountry || undefined,
                region: dailyLocSearchRegion || undefined,
                lat: biasLoc?.lat,
                lng: biasLoc?.lng,
                tripTitle: currentTrip?.title,
                locale: lang,
                signal: controller.signal
            })
            if (seq !== requestSeqRef.current || controller.signal.aborted) return
            const rawResults: GeocodeResult[] = data.results || []
            const deduped = dedupeGeocodeResults(rawResults)
            setLocSearchResults(deduped)
            if (rawResults.length === 0) {
                toast.error(t('loc_not_found'))
            }
        } catch (err) {
            if (err instanceof Error && err.name === 'AbortError') return
            if (seq !== requestSeqRef.current) return
            console.error("Search failed:", err)
            toast.error(t('loc_service_unavailable'))
        } finally {
            if (seq === requestSeqRef.current && !controller.signal.aborted) {
                setIsLocSearching(false)
            }
        }
    }

    const handleSelectLocation = async (loc: LocationInfo) => {
        if (isSelectingLocation) return
        setIsSelectingLocation(true)
        try {
            setDailyLocs({
                ...dailyLocs,
                [day]: {
                    name: loc.name,
                    lat: loc.lat,
                    lng: loc.lng
                }
            })
            onOpenChange(false)
            toast.success(t('loc_set_success', { name: loc.name }))
        } catch {
            toast.error(t('loc_set_failed'))
        } finally {
            setIsSelectingLocation(false)
        }
    }

    const handleManualLocation = () => {
        const latInput = document.getElementById('manual-lat') as HTMLInputElement
        const lngInput = document.getElementById('manual-lng') as HTMLInputElement
        const lat = parseFloat(latInput?.value)
        const lng = parseFloat(lngInput?.value)

        if (!isNaN(lat) && !isNaN(lng)) {
            setDailyLocs({
                ...dailyLocs,
                [day]: {
                    name: `${lat.toFixed(4)}, ${lng.toFixed(4)}`,
                    lat,
                    lng
                }
            })
            onOpenChange(false)
            toast.success(t('loc_cleared'))
        } else {
            toast.warning(t('loc_invalid_coords'))
        }
    }

    return (
        <Dialog open={isOpen} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>{t('loc_edit_title', { day: String(day) })}</DialogTitle>
                    <DialogDescription>
                        {t('loc_edit_desc')}
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4 min-w-0">
                    {/* 當前座標顯示 */}
                    {dailyLocs[day] && (
                        <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 min-w-0 overflow-hidden">
                            <div className="text-xs text-slate-500 mb-1">{t('loc_current')}</div>
                            <div className="font-bold text-slate-800 dark:text-slate-200 min-w-0 wrap-break-word [word-break:break-word] whitespace-normal leading-snug">{dailyLocs[day].name}</div>
                            <div className="text-xs text-slate-400 font-mono truncate">
                                {dailyLocs[day].lat?.toFixed(4)}, {dailyLocs[day].lng?.toFixed(4)}
                            </div>
                        </div>
                    )}

                    {/* 從活動同步按鈕 */}
                    {(() => {
                        const activityLoc = (Array.isArray(currentTrip?.days) ? currentTrip.days : []).find((d) => d.day === day)?.activities?.find((a) => a.lat && a.lng)
                        if (activityLoc) {
                            return (
                                <Button
                                    variant="outline"
                                    className="w-full max-w-full min-w-0 overflow-hidden justify-start text-left h-auto py-3 whitespace-normal"
                                    onClick={() => {
                                        setDailyLocs({ ...dailyLocs, [day]: { name: activityLoc.place || "Location", lat: activityLoc.lat!, lng: activityLoc.lng! } })
                                        onOpenChange(false)
                                    }}
                                >
                                    <div className="min-w-0 w-full">
                                        <div className="text-xs text-amber-600 font-bold">{t('loc_auto_sync')}</div>
                                        <div className="text-sm text-slate-700 dark:text-slate-300 wrap-break-word [word-break:break-word] whitespace-normal leading-snug">{activityLoc.place}</div>
                                        <div className="text-xs text-slate-400 font-mono truncate">{activityLoc.lat?.toFixed(4)}, {activityLoc.lng?.toFixed(4)}</div>
                                    </div>
                                </Button>
                            )
                        }
                        return null
                    })()}

                    {/* 搜尋區域 */}
                    <div className="space-y-2">
                        <label className="text-xs font-bold text-slate-700 dark:text-slate-300">
                            {t('loc_search')}
                        </label>

                        {/* 1. 國家與區域微型篩選條 (Country / Region Filter Header) */}
                        <div className="grid grid-cols-2 gap-2 min-w-0">
                            <div className="relative min-w-0">
                                <Input
                                    list="loc-edit-country-options"
                                    placeholder={zh ? "🌍 國家 (可手打或自選)" : "🌍 Country (Type/select)"}
                                    className="w-full min-w-0 text-[16px] sm:text-xs h-10 bg-slate-50/50 dark:bg-slate-800/40 border-slate-200/80 dark:border-slate-700 px-3 rounded-xl"
                                    value={searchCountry}
                                    onChange={(e) => {
                                        setSearchCountry(e.target.value)
                                        setDailyLocSearchRegion("")
                                    }}
                                />
                                <datalist id="loc-edit-country-options">
                                    <option value="Japan">🇯🇵 Japan / 日本</option>
                                    <option value="Taiwan">🇹🇼 Taiwan / 台灣</option>
                                    <option value="South Korea">🇰🇷 South Korea / 韓國</option>
                                    <option value="Thailand">🇹🇭 Thailand / 泰國</option>
                                    <option value="Vietnam">🇻🇳 Vietnam / 越南</option>
                                    <option value="Hong Kong">🇭🇰 Hong Kong / 香港</option>
                                    <option value="Singapore">🇸🇬 Singapore / 新加坡</option>
                                    <option value="Malaysia">🇲🇾 Malaysia / 馬來西亞</option>
                                    <option value="Philippines">🇵🇭 Philippines / 菲律賓</option>
                                    <option value="Indonesia">🇮🇩 Indonesia / 印尼</option>
                                    <option value="China">🇨🇳 China / 中國</option>
                                    <option value="USA">🇺🇸 USA / 美國</option>
                                    <option value="UK">🇬🇧 UK / 英國</option>
                                    <option value="France">🇫🇷 France / 法國</option>
                                    <option value="Italy">🇮🇹 Italy / 義大利</option>
                                    <option value="Germany">🇩🇪 Germany / 德國</option>
                                    <option value="Switzerland">🇨🇭 Switzerland / 瑞士</option>
                                    <option value="Iceland">🇮🇸 Iceland / 冰島</option>
                                    <option value="Australia">🇦🇺 Australia / 澳洲</option>
                                    <option value="New Zealand">🇳🇿 New Zealand / 紐西蘭</option>
                                    <option value="Canada">🇨🇦 Canada / 加拿大</option>
                                    <option value="Spain">🇪🇸 Spain / 西班牙</option>
                                </datalist>
                            </div>

                            {searchCountry && COUNTRY_REGIONS[searchCountry] ? (
                                <select
                                    className="w-full min-w-0 h-10 rounded-xl border border-slate-200/80 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/40 text-foreground px-3 py-1 text-xs shadow-2xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500"
                                    value={dailyLocSearchRegion}
                                    onChange={(e) => setDailyLocSearchRegion(e.target.value)}
                                >
                                    <option value="">🏙️ {zh ? "地區 (全部)" : "Region (All)"}</option>
                                    {COUNTRY_REGIONS[searchCountry].map(region => (
                                        <option key={region} value={region}>{region}</option>
                                    ))}
                                </select>
                            ) : (
                                <Input
                                    placeholder={zh ? "🏙️ 地區 (可選)" : "🏙️ Region (opt)"}
                                    className="w-full min-w-0 text-[16px] sm:text-xs h-10 bg-slate-50/50 dark:bg-slate-800/40 border-slate-200/80 dark:border-slate-700 px-3 rounded-xl"
                                    value={dailyLocSearchRegion}
                                    onChange={(e) => setDailyLocSearchRegion(e.target.value)}
                                />
                            )}
                        </div>

                        {/* 2. 地點名稱輸入與搜尋按鈕 */}
                        <div className="flex gap-2 min-w-0">
                            <Input
                                placeholder={t('loc_search_placeholder')}
                                value={newLocName}
                                onChange={e => setNewLocName(e.target.value)}
                                onCompositionStart={() => { isComposingRef.current = true }}
                                onCompositionEnd={() => { setTimeout(() => { isComposingRef.current = false }, 0) }}
                                onKeyDown={e => {
                                    if (e.key === 'Enter') {
                                        if (e.nativeEvent.isComposing || isComposingRef.current || e.nativeEvent.keyCode === 229) return
                                        handleSearchLocation()
                                    }
                                }}
                                className="flex-1 min-w-0 h-10 text-[16px] sm:text-sm bg-slate-50/50 dark:bg-slate-800/40 border-slate-200/80 dark:border-slate-700 rounded-xl px-3"
                            />
                            <Button
                                onClick={handleSearchLocation}
                                disabled={isLocSearching}
                                className="h-10 px-4 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-xl shrink-0"
                            >
                                {isLocSearching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                            </Button>
                        </div>
                    </div>


                    {locSearchResults.length > 0 && (
                        <div
                            className="space-y-2 max-h-60 overflow-y-auto overflow-x-hidden touch-pan-y overscroll-x-none overscroll-y-contain pr-1"
                            style={{ touchAction: "pan-y" }}
                        >
                            {locSearchResults.map((loc, idx) => {
                                const typeLabels: { [key: string]: string } = {
                                    restaurant: '🍴 餐廳', cafe: '☕ 咖啡廳', fast_food: '🍔 快餐',
                                    station: '🚉 車站', bus_stop: '🚌 公車站', subway_entrance: '🚇 地鐵站',
                                    hotel: '🏨 飯店', hostel: '🎒 青年旅館', guest_house: '🏘️ 民宿',
                                    attraction: '🚩 景點', museum: '🏛️ 博物館', park: '🌳 公園',
                                    temple: '⛩️ 寺廟', shrine: '⛩️ 神社', church: '⛪ 教堂',
                                    shop: '🛍️ 商店', mall: '🏬 購物中心', supermarket: '🛒 超市',
                                    convenience: '🏪 便利商店', department_store: '🏬 百貨公司',
                                    administrative: '🏛️ 行政區域', suburb: '🏘️ 市郊', city: '🏙️ 城市',
                                }
                                const typeLabel = typeLabels[loc.type || ''] || `📍 ${loc.type || '地點'}`

                                return (
                                    <button
                                        key={loc.osm_id ? `${loc.osm_type || 'x'}-${loc.osm_id}-${idx}` : idx}
                                        onClick={() => handleSelectLocation(loc)}
                                        disabled={isSelectingLocation}
                                        className="w-full max-w-full min-w-0 overflow-hidden text-left p-3 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-amber-50 dark:hover:bg-amber-900/30 hover:border-amber-300 dark:hover:border-amber-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                        <div className="flex items-start gap-2 mb-1 min-w-0">
                                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-200 shrink-0 mt-0.5">{typeLabel}</span>
                                            <span className="min-w-0 flex-1 font-bold text-sm text-slate-800 dark:text-white wrap-break-word [word-break:break-word] whitespace-normal leading-snug">{loc.name}</span>
                                        </div>
                                        <div className="text-[10px] text-slate-500 wrap-break-word [word-break:break-word] whitespace-normal line-clamp-2 leading-snug">
                                            {loc.display_name || loc.address || [loc.admin2, loc.admin1, loc.country].filter(Boolean).join(', ')}
                                        </div>
                                        <div className="text-[10px] text-slate-400 font-mono mt-0.5 truncate">
                                            {loc.lat?.toFixed(6)}, {loc.lng?.toFixed(6)}
                                        </div>
                                    </button>
                                )
                            })}
                        </div>
                    )}

                    <div className="space-y-2 pt-2 border-t border-dashed min-w-0">
                        <label className="text-xs font-bold text-slate-500">{t('loc_manual_title')}</label>
                        <div className="flex gap-2 min-w-0">
                            <Input placeholder={t('loc_lat_ph')} className="min-w-0 font-mono text-xs h-8" id="manual-lat" />
                            <Input placeholder={t('loc_lng_ph')} className="min-w-0 font-mono text-xs h-8" id="manual-lng" />
                            <Button size="sm" variant="secondary" className="shrink-0" onClick={handleManualLocation}>{t('loc_apply')}</Button>
                        </div>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}
