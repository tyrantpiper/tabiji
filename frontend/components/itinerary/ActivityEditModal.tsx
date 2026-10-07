"use client"

import { useState, useEffect, useRef } from "react"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"
import { toast } from "sonner"
import { MultiImageUpload } from "@/components/ui/multi-image-upload"
import { POISearch } from "@/components/poi-search"
import { COUNTRY_REGIONS } from "@/lib/constants"
import { ItineraryItemState, LocationInfo, DailyLocation, GeocodeResult } from "@/lib/itinerary-types"
import { geocodeApi } from "@/lib/api"
import { useHaptic } from "@/lib/hooks"
import { useLanguage } from "@/lib/LanguageContext"
import { X, Loader2, CheckCircle2, AlertCircle, ChevronDown, ChevronUp, StickyNote } from "lucide-react"
import { Switch } from "@/components/ui/switch"
import { extractCoordsFromUrl, isGoogleMapsUrl } from "../../lib/location-utils"

const ACTIVITY_CATEGORIES = [
    { id: 'sightseeing', icon: '🎯', label: '景點', labelEn: 'Sightseeing' },
    { id: 'food', icon: '🍽️', label: '美食', labelEn: 'Food' },
    { id: 'hotel', icon: '🏨', label: '住宿', labelEn: 'Hotel' },
    { id: 'transport', icon: '🚃', label: '交通', labelEn: 'Transport' },
    { id: 'shopping', icon: '🛍️', label: '購物', labelEn: 'Shopping' },
    { id: 'activity', icon: '🎭', label: '活動', labelEn: 'Activity' },
]

const TYPE_LABELS: { [key: string]: string } = {
    restaurant: '🍽️', cafe: '☕', fast_food: '🍔',
    station: '🚉', bus_stop: '🚌', subway_entrance: '🚇',
    hotel: '🏨', hostel: '🛏️', attraction: '🎯',
    museum: '🏛️', park: '🌳', temple: '⛩️', shrine: '⛩️',
    shop: '🛍️', mall: '🏬', supermarket: '🛒',
}

interface ActivityEditModalProps {
    isOpen: boolean
    onOpenChange: (open: boolean) => void
    editItem: ItineraryItemState | null
    setEditItem: (item: ItineraryItemState | null) => void
    isAddMode: boolean
    isSaving: boolean
    onSave: () => void
    dailyLoc?: DailyLocation
    tripTitle?: string  // 🆕 智能搜尋用
    biasLoc?: { lat: number, lng: number } // 🆕 Smart Geocoding Bias
}

export function ActivityEditModal({
    isOpen,
    onOpenChange,
    editItem,
    setEditItem,
    isAddMode,
    isSaving,
    onSave,
    dailyLoc,
    tripTitle,  // 🆕 智能搜尋用
    biasLoc,    // 🆕 Smart Geocoding Bias
}: ActivityEditModalProps) {
    const [searchCountry, setSearchCountry] = useState("")
    const [searchRegion, setSearchRegion] = useState("")
    const [placeSearchResults, setPlaceSearchResults] = useState<LocationInfo[]>([])
    const [isSearching, setIsSearching] = useState(false)
    const [isResolvingLink, setIsResolvingLink] = useState(false)
    const [resolveStatus, setResolveStatus] = useState<'idle' | 'success' | 'fallback' | 'error'>('idle')
    const [isResolvingAddress, setIsResolvingAddress] = useState(false)
    const [addressResolveStatus, setAddressResolveStatus] = useState<'idle' | 'success' | 'error'>('idle')
    const [isPoiExplorerOpen, setIsPoiExplorerOpen] = useState(false)
    const [isCoordinatesOpen, setIsCoordinatesOpen] = useState(false)
    const haptic = useHaptic()
    const { t, lang } = useLanguage()
    const zh = lang === 'zh'
    const originalUrlRef = useRef<string>("")

    // 🛡️ Mantis 防禦機制：追蹤活動 ID 與最新物件指標 (SEC-ACT-001)
    const editItemRef = useRef(editItem)
    editItemRef.current = editItem
    const activeItemIdRef = useRef<string | undefined>(editItem?.id)

    useEffect(() => {
        activeItemIdRef.current = editItem?.id
    }, [editItem?.id])

    // 🕵️ 奈米級追蹤：掛載時捕獲原始網址，並重置人工狀態
    useEffect(() => {
        if (isOpen && editItem) {
            originalUrlRef.current = editItem.link_url || ""
            // 重置人工編輯狀態（除非已經標記過）
            if (editItem.isManualCoords === undefined) {
                setEditItem({ ...editItem, isManualCoords: false })
            }
        }
    }, [isOpen, editItem, setEditItem])

    const handleSearchPlace = async () => {
        if (!editItem?.place?.trim()) return
        setIsSearching(true)
        try {
            // 🧠 決定位置權重 (Location Bias)
            // 優先順序: 1. 當前編輯項目的座標 (若是修改) 2. 外部傳入的偏差座標 (Sequential) 3. 當日位置
            const targetLat = (editItem.lat ? Number(editItem.lat) : undefined) || biasLoc?.lat || dailyLoc?.lat
            const targetLng = (editItem.lng ? Number(editItem.lng) : undefined) || biasLoc?.lng || dailyLoc?.lng

            // 🆕 使用結構化參數（取代字串拼接）
            const data = await geocodeApi.search({
                query: editItem.place.trim(),       // 純淨的搜尋字串
                limit: 5,
                tripTitle,
                lat: targetLat,
                lng: targetLng,
                country: searchCountry || undefined,  // 🆕 結構化國家過濾
                region: searchRegion || undefined     // 🆕 結構化區域過濾
            })
            setPlaceSearchResults((data.results || []).map((item: GeocodeResult) => ({
                name: item.name,
                display_name: item.address || item.name,
                lat: item.lat,
                lng: item.lng,
                type: item.type || "place",
                source: item.source
            })))
        } catch { toast.error(zh ? '搜尋失敗' : 'Search failed') }
        finally { setIsSearching(false) }
    }

    // 🧠 Heuristic Dual-Link Engine (Split-Field)
    const handleResolveLink = async (type: "map" | "media") => {
        const url = type === "map" ? editItem?.link_url : editItem?.website_link
        if (!url || !editItem) return

        // ⚡ Tier 1: Client-side Regex (Only for Map coordinates)
        if (type === "map") {
            const extracted = extractCoordsFromUrl(url)
            if (extracted.lat && extracted.lng) {
                updateCoords(extracted.lat, extracted.lng)
                setResolveStatus('success')
                toast.success(zh ? "已從連結自動提取座標" : "Coords extracted from link")
                // 🚀 Decoupling: Continue to backend to fetch metadata (images) if possible
            }
        }

        // 🌐 Tier 2: Backend Neural Engine (Scraper + Geocoder)
        if (type === "map" && !isGoogleMapsUrl(url)) {
            toast.info(zh ? "此連結不包含可識別座標，請使用搜尋功能" : "This link has no coordinates, use search instead")
            return
        }

        setIsResolvingLink(true)
        setResolveStatus('idle')
        try {
            const result = await geocodeApi.resolveLink(url, type)
            if (result.success) {
                if (type === "map" && result.lat && result.lng) {
                    // 🧬 v35.80: Clean Name Logic (Atomic Overwrite)
                    // Supports: " - ", " | ", Maps, 地圖, 地图, マップ, etc.
                    // 🧬 v35.82: DNA-Level Overwrite Priority
                    const rawTitle = result.metadata?.title || "";
                    const cleanedTitle = rawTitle
                        .replace(/\s*[-|]\s*Google\s*(Maps|地图|地圖|マップ|映射|map|search)/gi, "")
                        .trim();
                    
                    // 🛡️ Ensure query (path extraction) wins over old name if title is generic/empty
                    const cleanName = cleanedTitle || result.query || editItem.place;

                    const newMetadata = result.metadata?.image ? {
                        ...editItem.preview_metadata,
                        map_image: result.metadata.image
                    } : editItem.preview_metadata;

                    console.log("🛡️ [Audit] Place Name resolved & overwritten:", cleanName);

                    // 🛡️ Mantis Dual-Ref Guard: Drop if switched item or closed
                    const targetId = editItem.id
                    if (activeItemIdRef.current !== targetId) return
                    const latest = editItemRef.current || editItem

                    setEditItem({
                        ...latest,
                        place: cleanName,
                        lat: result.lat,
                        lng: result.lng,
                        isManualCoords: true,
                        preview_metadata: newMetadata
                    })
                    setResolveStatus(result.method?.includes('jit') ? 'fallback' : 'success')
                    toast.success(result.method?.includes('jit') ? (zh ? "已透過地名語意自動定位" : "Located via semantic analysis") : (zh ? "已完成座標解析" : "Coordinate resolved"))
                } else if (type === "media") {
                    const meta = result.metadata || {}
                    // 🧠 Quantum Merge: Ensure og_image/title is stored without deleting map_image
                    // 🛡️ v35.38: Standard setEditItem (no closure issue for media type)
                    setEditItem({
                        ...editItem,
                        preview_metadata: {
                            ...editItem.preview_metadata,
                            og_image: meta.image,
                            og_title: meta.title
                        }
                    })
                    setResolveStatus('success')
                    toast.success(zh ? "官網首圖解析成功！" : "Website image parsed!")
                }
            } else {
                setResolveStatus('error')
                toast.error((zh ? "解析失敗：" : "Parse failed: ") + (result.error || (zh ? "請檢查網址" : "Check URL")))
            }
        } catch (e) {
            console.error("Link Resolution Error:", e)
            setResolveStatus('error')
        } finally {
            setIsResolvingLink(false)
        }
    }

    const handleResolveAddress = async () => {
        if (!editItem?.address?.trim()) return
        const targetId = editItem.id
        setIsResolvingAddress(true)
        setAddressResolveStatus('idle')
        try {
            const data = await geocodeApi.resolveAddress(editItem.address)
            // 🛡️ Mantis Dual-Ref Guard: Drop if switched item or closed
            if (activeItemIdRef.current !== targetId) return
            const latest = editItemRef.current || editItem

            if (data.success && data.lat && data.lng) {
                // 順向補填: 如果 place 為空，拿 name 或 address 當 place
                const currentPlace = latest.place?.trim()
                const newPlace = currentPlace ? currentPlace : (data.name || data.address || "")
                setEditItem({
                    ...latest,
                    lat: data.lat,
                    lng: data.lng,
                    place: newPlace,
                    isManualCoords: true
                })
                setAddressResolveStatus('success')
                toast.success(zh ? "地址高精解析成功" : "Address resolved with high precision")
            }
        } catch (error: unknown) {
            setAddressResolveStatus('error')
            const err = error as { message?: string, retryable?: boolean }
            const msg = err.message || (zh ? "無法在地圖上定位此地址" : "Address not found")
            const isRetryable = err.retryable
            
            if (isRetryable) {
                toast.error(`⚠️ ${msg}`, { duration: 5000 })
            } else {
                toast.error(msg)
            }
        } finally {
            setIsResolvingAddress(false)
        }
    }

    const updateCoords = (lat: number | string, lng: number | string) => {
        if (!editItem) return
        setEditItem({
            ...editItem,
            lat: lat,
            lng: lng,
            isManualCoords: true // 🚩 探針發射：只要座標變動，系統自動退讓
        })
    }

    const handleSelectLocation = (loc: LocationInfo) => {
        if (editItem) {
            setEditItem({
                ...editItem,
                place: loc.name,
                address: loc.address || loc.display_name, // 順向自動帶入
                lat: loc.lat,
                lng: loc.lng,
                isManualCoords: true, // 🚩 手動選擇地點視同人工座標
                link_url: editItem.link_url || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(loc.name)}`
            })
            setPlaceSearchResults([])
        }
    }

    const handleAddTag = (inputId: string) => {
        const input = document.getElementById(inputId) as HTMLInputElement
        const newTag = input?.value?.trim()
        if (editItem && newTag && !(editItem.tags || []).includes(newTag)) {
            setEditItem({ ...editItem, tags: [...(editItem.tags || []), newTag] })
            input.value = ''
        }
    }

    if (!editItem) return null

    const hasCoordsForPOI = (editItem.lat && editItem.lng) || (dailyLoc?.lat && dailyLoc?.lng)

    return (
        <Sheet open={isOpen} onOpenChange={onOpenChange}>
            <SheetContent
                side="bottom"
                className="h-[90vh] max-h-[90vh] rounded-t-3xl border-t border-slate-200 dark:border-slate-800 bg-slate-100 dark:bg-slate-950 p-0 flex flex-col overflow-hidden z-160 [&>button:last-child]:hidden"
            >
                {/* iOS Navigation Bar */}
                <SheetHeader className="h-14 px-4 flex flex-row items-center justify-between bg-white dark:bg-slate-900 border-b border-slate-200/80 dark:border-slate-800 shrink-0">
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => onOpenChange(false)}
                        className="text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200 font-medium px-2 h-9"
                    >
                        {zh ? "取消" : "Cancel"}
                    </Button>

                    <div className="flex flex-col items-center">
                        <div className="w-9 h-1 bg-slate-300 dark:bg-slate-600 rounded-full mb-1" />
                        <SheetTitle className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                            {isAddMode ? (zh ? "新增行程" : "Add Activity") : (zh ? "編輯行程" : "Edit Activity")}
                        </SheetTitle>
                        <SheetDescription className="sr-only">
                            {isAddMode ? "Add activity" : "Edit activity"}
                        </SheetDescription>
                    </div>

                    <Button
                        type="button"
                        size="sm"
                        disabled={isSaving || isResolvingAddress || isResolvingLink}
                        onClick={() => {
                            (document.activeElement as HTMLElement)?.blur()
                            onSave()
                        }}
                        className="bg-blue-600 hover:bg-blue-700 text-white font-bold px-3.5 h-8 text-xs rounded-full shadow-xs disabled:opacity-50 transition-all active:scale-95 flex items-center gap-1.5"
                    >
                        {isSaving ? (
                            <>
                                <Loader2 className="w-3 h-3 animate-spin" />
                                <span>{zh ? "儲存中" : "Saving"}</span>
                            </>
                        ) : isResolvingAddress || isResolvingLink ? (
                            <>
                                <Loader2 className="w-3 h-3 animate-spin" />
                                <span>{zh ? "解析中" : "Resolving"}</span>
                            </>
                        ) : (
                            zh ? "完成" : "Done"
                        )}
                    </Button>
                </SheetHeader>

                {/* iOS Inset Grouped Scroll Content */}
                <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 overscroll-contain">
                    {/* Media Header: MultiImageUpload */}
                    <div className="flex justify-center py-1">
                        <MultiImageUpload
                            values={editItem.image_urls || (editItem.image_url ? [editItem.image_url] : [])}
                            onChange={(urls) => setEditItem({ ...editItem, image_urls: urls, image_url: urls[0] || "" })}
                            maxImages={5}
                            folder="ryan_travel/spots"
                        />
                    </div>

                    {/* Card 1: 主要資訊與地點探索 (Primary Identity & Discovery) */}
                    <div className="space-y-1.5">
                        <div className="px-1 text-[11px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                            {zh ? "主要資訊與地點探索" : "Primary Identity & Discovery"}
                        </div>
                        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/70 dark:border-slate-800 shadow-xs divide-y divide-slate-100 dark:divide-slate-800/80 overflow-hidden">
                            {/* 地點搜尋漏斗: 國家區域篩選 + 地點輸入 + 搜尋 + 周邊探索 */}
                            <div className="p-3.5 space-y-2.5">
                                <div className="flex items-center justify-between">
                                    <Label className="text-xs font-semibold text-slate-700 dark:text-slate-200 flex items-center gap-1.5">
                                        <span>📍</span> {t('place')}
                                    </Label>
                                    {/* 探索周邊 POI 快速觸發膠囊按鈕 */}
                                    <button
                                        type="button"
                                        onClick={() => {
                                            haptic.tap()
                                            setIsPoiExplorerOpen(!isPoiExplorerOpen)
                                        }}
                                        className={cn(
                                            "inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium transition-all active:scale-95",
                                            isPoiExplorerOpen
                                                ? "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 font-semibold"
                                                : "bg-slate-100 hover:bg-slate-200/80 text-slate-600 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700/80"
                                        )}
                                    >
                                        <span>✨</span>
                                        <span>{zh ? "周邊探索" : "Explore POI"}</span>
                                        {isPoiExplorerOpen ? (
                                            <ChevronUp className="w-3 h-3 ml-0.5 text-amber-700 dark:text-amber-300" />
                                        ) : (
                                            <ChevronDown className="w-3 h-3 ml-0.5 text-slate-400" />
                                        )}
                                    </button>
                                </div>

                                {/* 1. 國家與區域微型篩選條 (Country / Region Filter Header) */}
                                <div className="grid grid-cols-2 gap-2 bg-slate-50/70 dark:bg-slate-800/30 p-2 rounded-xl border border-slate-100 dark:border-slate-800/60">
                                    <div className="relative">
                                        <Input
                                            list="country-options"
                                            placeholder={zh ? "🌍 國家 (可手打或自選)" : "🌍 Country (Type/select)"}
                                            className="text-[16px] sm:text-xs h-8 bg-white dark:bg-slate-800 border-slate-200/80 dark:border-slate-700 px-2"
                                            value={searchCountry}
                                            onChange={(e) => {
                                                setSearchCountry(e.target.value)
                                                setSearchRegion("")
                                            }}
                                        />
                                        <datalist id="country-options">
                                            <option value="Japan">🇯🇵 Japan / 日本</option>
                                            <option value="Taiwan">🇹🇼 Taiwan / 台灣</option>
                                            <option value="South Korea">🇰🇷 South Korea / 韓國</option>
                                            <option value="Thailand">🇹🇭 Thailand / 泰國</option>
                                            <option value="Vietnam">🇻🇳 Vietnam / 越南</option>
                                            <option value="Hong Kong">🇭🇰 Hong Kong / 香港</option>
                                            <option value="Singapore">🇸🇬 Singapore / 新加坡</option>
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
                                            className="w-full h-8 rounded-lg border border-slate-200/80 dark:border-slate-700 bg-white dark:bg-slate-800 text-foreground px-2 py-0.5 text-xs shadow-2xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-blue-500"
                                            value={searchRegion}
                                            onChange={(e) => setSearchRegion(e.target.value)}
                                        >
                                            <option value="">🏙️ {zh ? "地區 (全部)" : "Region (All)"}</option>
                                            {COUNTRY_REGIONS[searchCountry].map(region => (
                                                <option key={region} value={region}>{region}</option>
                                            ))}
                                        </select>
                                    ) : (
                                        <Input
                                            placeholder={zh ? "🏙️ 地區 (可選)" : "🏙️ Region (opt)"}
                                            className="text-[16px] sm:text-xs h-8 bg-white dark:bg-slate-800 border-slate-200/80 dark:border-slate-700"
                                            value={searchRegion}
                                            onChange={(e) => setSearchRegion(e.target.value)}
                                        />
                                    )}
                                </div>

                                {/* 2. 地點名稱輸入與搜尋按鈕 */}
                                <div className="flex gap-2">
                                    <Input
                                        value={editItem.place || ""}
                                        onChange={(e) => setEditItem({ ...editItem, place: e.target.value })}
                                        placeholder={zh ? "輸入商家或景點名稱..." : "Search place name..."}
                                        onKeyDown={(e) => e.key === 'Enter' && handleSearchPlace()}
                                        className="text-[16px] sm:text-sm h-10 flex-1 bg-slate-50/50 dark:bg-slate-800/40"
                                    />
                                    <Button
                                        type="button"
                                        variant="secondary"
                                        size="sm"
                                        disabled={isSearching}
                                        onClick={handleSearchPlace}
                                        className="h-10 px-3.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-200 font-medium"
                                    >
                                        {isSearching ? <Loader2 className="w-4 h-4 animate-spin" /> : '🔍'}
                                    </Button>
                                </div>

                                {/* 3. 地點搜尋結果列表 */}
                                {placeSearchResults.length > 0 && (
                                    <div className="space-y-1 max-h-44 overflow-y-auto border border-slate-200/80 dark:border-slate-700/80 rounded-xl p-2 bg-slate-50 dark:bg-slate-800/60 mt-1">
                                        {placeSearchResults.map((loc, idx) => {
                                            const icon = TYPE_LABELS[loc.type || ''] || '📍'
                                            return (
                                                <button
                                                    key={idx}
                                                    type="button"
                                                    className="w-full text-left p-2.5 rounded-lg hover:bg-amber-50 dark:hover:bg-amber-950/30 transition-colors"
                                                    onClick={() => handleSelectLocation(loc)}
                                                >
                                                    <div className="flex items-center gap-2 mb-0.5 min-w-0">
                                                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-200/70 dark:bg-slate-700 text-slate-700 dark:text-slate-200 shrink-0">
                                                            {icon} {loc.type || (zh ? '地點' : 'Place')}
                                                        </span>
                                                        <span className="font-bold text-xs text-slate-800 dark:text-slate-200 truncate">{loc.name}</span>
                                                    </div>
                                                    <div className="text-[10px] text-slate-500 dark:text-slate-400 truncate">
                                                        {loc.display_name}
                                                    </div>
                                                    <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                                                        {loc.lat?.toFixed(6)}, {loc.lng?.toFixed(6)}
                                                    </div>
                                                </button>
                                            )
                                        })}
                                    </div>
                                )}

                                {/* 4. 周邊 POI 探索展開區塊 (Progressive Drawer) */}
                                {isPoiExplorerOpen && (
                                    <div className="pt-2 border-t border-dashed border-amber-200/80 dark:border-amber-800/60 space-y-2">
                                        <div className="flex items-center justify-between">
                                            <Label className="text-xs font-semibold text-amber-800 dark:text-amber-300 flex items-center gap-1.5">
                                                <span>✨</span> {zh ? '探索周邊 POI' : 'Explore Nearby POIs'}
                                            </Label>
                                            <span className="text-[10px] text-slate-400">
                                                {hasCoordsForPOI ? (zh ? "根據當前錨點" : "Based on current anchor") : (zh ? "需經緯度座標" : "Requires coords")}
                                            </span>
                                        </div>
                                        {hasCoordsForPOI ? (
                                            <POISearch
                                                centerLat={Number(editItem.lat) || dailyLoc?.lat || 35.6895}
                                                centerLng={Number(editItem.lng) || dailyLoc?.lng || 139.6917}
                                                onSelectPOI={(poi) => {
                                                    setEditItem({
                                                        ...editItem,
                                                        place: poi.name,
                                                        lat: poi.lat,
                                                        lng: poi.lng,
                                                        isManualCoords: true,
                                                        link_url: editItem.link_url || poi.website || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(poi.name)}`,
                                                        desc: poi.opening_hours ? `${zh ? '營業' : 'Hours'}: ${poi.opening_hours}` : (editItem.desc || "")
                                                    })
                                                    toast.success(zh ? `已選擇: ${poi.name}` : `Selected: ${poi.name}`)
                                                }}
                                            />
                                        ) : (
                                            <div className="text-xs text-slate-400 text-center py-3 bg-slate-50/60 dark:bg-slate-800/40 rounded-xl border border-dashed border-slate-200 dark:border-slate-800">
                                                💡 {zh ? '先輸入座標或搜尋地點以啟用周邊 POI 探索' : 'Search a place first to enable nearby POI search'}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>

                            {/* Category Segmented Control Strip */}
                            <div className="p-3.5 space-y-2">
                                <Label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                                    {zh ? "活動分類" : "Category"}
                                </Label>
                                <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5 px-0.5">
                                    {ACTIVITY_CATEGORIES.map(cat => (
                                        <button
                                            key={cat.id}
                                            type="button"
                                            onClick={() => {
                                                haptic.tap()
                                                setEditItem({ ...editItem, category: cat.id })
                                            }}
                                            className={cn(
                                                "shrink-0 px-3 py-1.5 rounded-full text-xs font-medium flex items-center gap-1.5 transition-all active:scale-95",
                                                editItem.category === cat.id
                                                    ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900 shadow-xs font-bold"
                                                    : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300 hover:bg-slate-200/80"
                                            )}
                                        >
                                            <span>{cat.icon}</span>
                                            <span>{zh ? cat.label : cat.labelEn}</span>
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {/* Time Section: iOS Compact Time Capsule with Presets */}
                            <div className="p-3.5 space-y-2.5">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2.5">
                                        <Label className="text-xs font-semibold text-slate-700 dark:text-slate-200 flex items-center gap-1.5 shrink-0">
                                            <span>🕒</span> {t('time')}
                                        </Label>
                                        {/* 磨砂時間膠囊輸入框 */}
                                        <div className="relative inline-flex items-center">
                                            <Input
                                                type="time"
                                                value={editItem.time || ""}
                                                onChange={(e) => setEditItem({ ...editItem, time: e.target.value })}
                                                className="w-32 h-8 text-center font-mono font-medium text-[16px] sm:text-xs rounded-full bg-slate-100 hover:bg-slate-200/80 dark:bg-slate-800 dark:hover:bg-slate-700/80 border border-slate-200/80 dark:border-slate-700 text-slate-800 dark:text-slate-100 shadow-2xs transition-colors cursor-pointer px-2"
                                            />
                                        </div>
                                    </div>

                                    {/* 當前時段標籤 (依時數智慧判斷) */}
                                    {editItem.time && (
                                        <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500 font-mono">
                                            {(() => {
                                                const [h] = editItem.time.split(':').map(Number)
                                                if (isNaN(h)) return ""
                                                if (h < 6) return zh ? "凌晨" : "Dawn"
                                                if (h < 12) return zh ? "上午" : "AM"
                                                if (h < 14) return zh ? "中午" : "Noon"
                                                if (h < 18) return zh ? "下午" : "PM"
                                                return zh ? "晚間" : "Night"
                                            })()}
                                        </span>
                                    )}
                                </div>

                                {/* 快捷時段標籤快速切換膠囊 (一鍵填入) */}
                                <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5">
                                    <span className="text-[10px] text-slate-400 shrink-0 font-medium mr-0.5">
                                        {zh ? "快捷:" : "Quick:"}
                                    </span>
                                    {[
                                        { label: zh ? "早 09:00" : "09:00", value: "09:00" },
                                        { label: zh ? "午 12:00" : "12:00", value: "12:00" },
                                        { label: zh ? "午茶 15:00" : "15:00", value: "15:00" },
                                        { label: zh ? "晚 18:00" : "18:00", value: "18:00" },
                                        { label: zh ? "夜 20:30" : "20:30", value: "20:30" },
                                    ].map((slot) => {
                                        const isSelected = editItem.time === slot.value
                                        return (
                                            <button
                                                key={slot.value}
                                                type="button"
                                                onClick={() => {
                                                    haptic.tap()
                                                    setEditItem({ ...editItem, time: slot.value })
                                                }}
                                                className={cn(
                                                    "shrink-0 px-2.5 py-1 rounded-full text-[11px] font-medium transition-all active:scale-95",
                                                    isSelected
                                                        ? "bg-blue-600 text-white dark:bg-blue-500 font-bold shadow-2xs"
                                                        : "bg-slate-100 hover:bg-slate-200/80 text-slate-600 dark:bg-slate-800/80 dark:hover:bg-slate-700/80 dark:text-slate-300 border border-slate-200/50 dark:border-slate-700/60"
                                                )}
                                            >
                                                {slot.label}
                                            </button>
                                        )
                                    })}
                                    {editItem.time && (
                                        <button
                                            type="button"
                                            onClick={() => {
                                                haptic.tap()
                                                setEditItem({ ...editItem, time: "" })
                                            }}
                                            className="shrink-0 px-2 py-1 rounded-full text-[10px] text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
                                        >
                                            {zh ? "清除" : "Clear"}
                                        </button>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Card 2: 精準定位與導航 (Location & Navigation) */}
                    <div className="space-y-1.5">
                        <div className="px-1 text-[11px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                            {zh ? "精準定位與導航" : "Location & Navigation"}
                        </div>
                        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/70 dark:border-slate-800 shadow-xs divide-y divide-slate-100 dark:divide-slate-800/80 overflow-hidden">
                            {/* Address Geocode Engine */}
                            <div className="p-3.5 space-y-2">
                                <div className="flex justify-between items-center">
                                    <Label className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 flex items-center gap-1.5">
                                        <span>📍</span> {zh ? '地址解析引擎' : 'Address Engine'}
                                    </Label>
                                    <div className="flex items-center gap-2">
                                        {isResolvingAddress && <Loader2 className="w-3 h-3 text-emerald-500 animate-spin" />}
                                        {!isResolvingAddress && addressResolveStatus === 'success' && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />}
                                        {!isResolvingAddress && addressResolveStatus === 'error' && <AlertCircle className="w-3.5 h-3.5 text-rose-500" />}
                                    </div>
                                </div>
                                <div className="flex flex-col gap-2">
                                    <textarea
                                        placeholder={zh ? "貼上混亂地址，AI 會為您精確定位...\n(例: 105台北市松山區敦化北路100號)" : "Paste full address..."}
                                        className="text-[16px] sm:text-sm min-h-16 w-full resize-y rounded-xl border border-emerald-200/80 dark:border-emerald-800/50 bg-emerald-50/30 dark:bg-emerald-950/20 px-3 py-2 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-500"
                                        value={editItem.address || ''}
                                        onChange={(e) => {
                                            setEditItem({ ...editItem, address: e.target.value })
                                            setAddressResolveStatus('idle')
                                        }}
                                    />
                                    <div className="flex justify-end">
                                        <Button
                                            type="button"
                                            size="sm"
                                            disabled={isResolvingAddress || !editItem.address?.trim()}
                                            onClick={handleResolveAddress}
                                            className="h-8 px-4 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs transition-all active:scale-95 disabled:bg-slate-200 dark:disabled:bg-slate-800 disabled:text-slate-400"
                                        >
                                            {isResolvingAddress ? <Loader2 className="w-3 h-3 animate-spin" /> : (zh ? "高精解析" : "GEOCODE")}
                                        </Button>
                                    </div>
                                </div>
                            </div>

                            {/* Navigation URL */}
                            <div className="p-3.5 space-y-2">
                                <div className="flex justify-between items-center">
                                    <Label className="text-xs font-semibold text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
                                        <span>🔗</span> {zh ? '導航網址' : 'Navigation URL'}
                                    </Label>
                                    <div className="flex items-center gap-2">
                                        {isResolvingLink && <Loader2 className="w-3 h-3 text-amber-500 animate-spin" />}
                                        {!isResolvingLink && resolveStatus === 'success' && <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />}
                                        {!isResolvingLink && resolveStatus === 'fallback' && (
                                            <div className="flex items-center gap-1 text-[10px] text-amber-600 font-bold">
                                                <AlertCircle className="w-3 h-3" />
                                                {zh ? '語意定位' : 'Semantic'}
                                            </div>
                                        )}
                                    </div>
                                </div>
                                <div className="flex gap-2">
                                    <Input
                                        placeholder="https://maps.app.goo.gl/..."
                                        className="text-[16px] sm:text-sm h-10 bg-slate-50/50 dark:bg-slate-800/40 flex-1"
                                        value={editItem.link_url || ''}
                                        onChange={(e) => {
                                            setEditItem({ ...editItem, link_url: e.target.value })
                                            setResolveStatus('idle')
                                        }}
                                    />
                                    <Button
                                        type="button"
                                        variant="secondary"
                                        size="sm"
                                        disabled={isResolvingLink || !editItem.link_url?.trim()}
                                        onClick={() => handleResolveLink("map")}
                                        className="h-10 px-3 bg-amber-100 hover:bg-amber-200 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300 font-semibold"
                                    >
                                        {isResolvingLink ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : (zh ? "解析" : "Resolve")}
                                    </Button>
                                </div>
                            </div>

                            {/* Progressive Disclosure: Manual Coordinates */}
                            <div>
                                <button
                                    type="button"
                                    onClick={() => {
                                        haptic.tap()
                                        setIsCoordinatesOpen(!isCoordinatesOpen)
                                    }}
                                    className="w-full px-3.5 py-3 flex items-center justify-between text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors"
                                >
                                    <span className="flex items-center gap-1.5">
                                        <span>⚙️</span> {zh ? "手動經緯度微調 (選填)" : "Manual Coordinates (Optional)"}
                                    </span>
                                    {isCoordinatesOpen ? (
                                        <ChevronUp className="w-4 h-4 text-slate-400" />
                                    ) : (
                                        <ChevronDown className="w-4 h-4 text-slate-400" />
                                    )}
                                </button>

                                {isCoordinatesOpen && (
                                    <div className="p-3.5 pt-1 space-y-3 bg-slate-50/40 dark:bg-slate-950/30 border-t border-slate-100 dark:border-slate-800">
                                        <div className="space-y-1.5">
                                            <Label className="text-xs text-slate-500">{zh ? "經緯度座標" : "Coordinates"}</Label>
                                            <div className="flex gap-2">
                                                <Input
                                                    placeholder="Lat"
                                                    className="text-[16px] sm:text-xs font-mono h-9"
                                                    value={editItem.lat || ''}
                                                    onChange={(e) => setEditItem({ ...editItem, lat: e.target.value, isManualCoords: true })}
                                                />
                                                <Input
                                                    placeholder="Lng"
                                                    className="text-[16px] sm:text-xs font-mono h-9"
                                                    value={editItem.lng || ''}
                                                    onChange={(e) => setEditItem({ ...editItem, lng: e.target.value, isManualCoords: true })}
                                                />
                                            </div>
                                            <div className="flex justify-between items-center px-1">
                                                <span className="text-[10px] text-slate-400 font-medium">
                                                    {editItem.lat && editItem.lng ? "📍 Precise Geolocation" : "🔍 Search mode"}
                                                </span>
                                                <div className="flex items-center gap-2">
                                                    {(editItem.preview_metadata?.og_image || editItem.preview_metadata?.map_image) && (
                                                        <Button
                                                            type="button"
                                                            variant="ghost"
                                                            size="sm"
                                                            className="h-6 text-[10px] text-blue-500 hover:text-blue-600 hover:bg-blue-50 font-bold px-1.5"
                                                            onClick={() => {
                                                                haptic.tap()
                                                                setEditItem({ ...editItem, preview_metadata: {} })
                                                                toast.info(zh ? "已清除連結預覽" : "Link preview cleared")
                                                            }}
                                                        >
                                                            <X className="w-3 h-3 mr-0.5" /> Clear Preview
                                                        </Button>
                                                    )}
                                                    <Button
                                                        type="button"
                                                        variant="ghost"
                                                        size="sm"
                                                        className="h-6 text-[10px] text-red-500 hover:text-red-600 hover:bg-red-50 font-bold px-1.5 flex items-center gap-0.5"
                                                        onClick={() => {
                                                            haptic.tap()
                                                            setEditItem({ ...editItem, lat: null, lng: null, isManualCoords: true })
                                                        }}
                                                    >
                                                        <X className="w-3 h-3" /> Clear Coords
                                                    </Button>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Card 3: 備忘筆記與標籤 (Notes & Tags) */}
                    <div className="space-y-1.5">
                        <div className="px-1 text-[11px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                            {zh ? "備忘筆記與標籤" : "Notes & Tags"}
                        </div>
                        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/70 dark:border-slate-800 shadow-xs divide-y divide-slate-100 dark:divide-slate-800/80 overflow-hidden">
                            {/* 自適應備忘筆記 */}
                            <div className="p-3.5 space-y-1.5">
                                <Label className="text-xs font-semibold text-slate-600 dark:text-slate-300 flex items-center gap-1.5">
                                    <StickyNote className="w-3.5 h-3.5 text-amber-500" />
                                    {t('notes')}
                                </Label>
                                <textarea
                                    rows={3}
                                    value={editItem.desc || ""}
                                    onChange={(e) => {
                                        setEditItem({ ...editItem, desc: e.target.value })
                                        e.target.style.height = 'auto'
                                        e.target.style.height = `${Math.max(88, e.target.scrollHeight)}px`
                                    }}
                                    placeholder={zh ? "備忘或行程詳細指引（文字高度將自動依內容延展）..." : "Detailed memo or guide (auto-expands)..."}
                                    style={{ fieldSizing: "content" } as React.CSSProperties}
                                    className="w-full min-h-22 text-[16px] sm:text-xs rounded-xl border border-slate-200/80 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/40 px-3 py-2.5 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-all"
                                />
                            </div>

                            {/* 標籤系統與快捷推薦庫 */}
                            <div className="p-3.5 space-y-3">
                                <div className="space-y-1.5">
                                    <div className="flex items-center justify-between">
                                        <Label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                                            {zh ? "已選標籤" : "Tags"}
                                        </Label>
                                        <span className="text-[10px] text-slate-400">
                                            {zh ? "點擊標籤可直接移除" : "Click to remove"}
                                        </span>
                                    </div>
                                    <div className="flex flex-wrap gap-1.5 min-h-6">
                                        {(editItem.tags || []).length > 0 ? (
                                            (editItem.tags || []).map((tag: string, i: number) => (
                                                <button
                                                    key={i}
                                                    type="button"
                                                    onClick={() => {
                                                        haptic.tap()
                                                        setEditItem({
                                                            ...editItem,
                                                            tags: (editItem.tags || []).filter((_: string, idx: number) => idx !== i)
                                                        })
                                                    }}
                                                    className="bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-950/40 dark:hover:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300 border border-indigo-200/70 dark:border-indigo-800/70 px-2.5 py-1 rounded-full text-xs font-medium flex items-center gap-1.5 transition-all active:scale-95 group"
                                                    title={zh ? "點擊移除" : "Click to remove"}
                                                >
                                                    <span>{tag}</span>
                                                    <span className="w-3.5 h-3.5 rounded-full flex items-center justify-center font-bold text-indigo-400 group-hover:text-red-500 text-[11px] leading-none">
                                                        ×
                                                    </span>
                                                </button>
                                            ))
                                        ) : (
                                            <span className="text-[11px] text-slate-400 italic py-0.5">
                                                {zh ? "尚未加入任何標籤" : "No tags yet"}
                                            </span>
                                        )}
                                    </div>
                                </div>

                                {/* 常用快捷推薦標籤 */}
                                <div className="space-y-1.5 pt-1 border-t border-slate-100 dark:border-slate-800/80">
                                    <div className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">
                                        {zh ? "常用推薦標籤" : "Quick Suggestions"}
                                    </div>
                                    <div className="flex flex-wrap gap-1.5">
                                        {[
                                            { label: zh ? "必去 🌟" : "Must-visit 🌟", value: "必去" },
                                            { label: zh ? "美食 🍽️" : "Food 🍽️", value: "美食" },
                                            { label: zh ? "需預約 🎫" : "Booking Req 🎫", value: "需預約" },
                                            { label: zh ? "拍照打卡 📸" : "Photo Spot 📸", value: "拍照打卡" },
                                            { label: zh ? "雨天備案 ☔" : "Rain Plan ☔", value: "雨天備案" },
                                            { label: zh ? "伴手禮 🛍️" : "Souvenir 🛍️", value: "伴手禮" }
                                        ].map((chip) => {
                                            const isSelected = (editItem.tags || []).includes(chip.value)
                                            return (
                                                <button
                                                    key={chip.value}
                                                    type="button"
                                                    onClick={() => {
                                                        haptic.tap()
                                                        if (isSelected) {
                                                            setEditItem({
                                                                ...editItem,
                                                                tags: (editItem.tags || []).filter((t: string) => t !== chip.value)
                                                            })
                                                        } else {
                                                            setEditItem({
                                                                ...editItem,
                                                                tags: [...(editItem.tags || []), chip.value]
                                                            })
                                                        }
                                                    }}
                                                    className={cn(
                                                        "text-[11px] px-2.5 py-1 rounded-lg border font-medium transition-all active:scale-95",
                                                        isSelected
                                                            ? "bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200 border-slate-300 dark:border-slate-600 font-semibold"
                                                            : "bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100 dark:hover:bg-slate-700/60 text-slate-600 dark:text-slate-400 border-slate-200/70 dark:border-slate-700/70"
                                                    )}
                                                >
                                                    {chip.label}
                                                </button>
                                            )
                                        })}
                                    </div>
                                </div>

                                {/* 自訂標籤輸入行 */}
                                <div className="flex gap-2 pt-1">
                                    <Input
                                        id="activity-tag-input"
                                        placeholder={zh ? "自訂輸入標籤..." : "Custom tag..."}
                                        className="text-[16px] sm:text-xs h-9 flex-1 bg-slate-50/50 dark:bg-slate-800/40 rounded-xl"
                                        onKeyDown={(e) => {
                                            if (e.key === 'Enter') {
                                                e.preventDefault()
                                                handleAddTag('activity-tag-input')
                                            }
                                        }}
                                    />
                                    <Button
                                        type="button"
                                        variant="secondary"
                                        size="sm"
                                        onClick={() => handleAddTag('activity-tag-input')}
                                        className="h-9 px-3.5 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 rounded-xl font-bold"
                                    >
                                        +
                                    </Button>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Card 4: 偏好設定 (Settings) */}
                    <div className="space-y-1.5">
                        <div className="px-1 text-[11px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                            {zh ? "偏好設定" : "Preferences"}
                        </div>
                        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200/70 dark:border-slate-800 shadow-xs divide-y divide-slate-100 dark:divide-slate-800/80 overflow-hidden">
                            {/* VIP Highlight Toggle */}
                            <div className="p-3.5 flex items-center justify-between bg-amber-50/20 dark:bg-amber-950/10">
                                <div className="space-y-0.5">
                                    <div className="text-xs font-semibold text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
                                        <span>🌟</span> {zh ? "重點高亮行程 (VIP)" : "VIP Highlight"}
                                    </div>
                                    <p className="text-[11px] text-amber-600/70 dark:text-amber-400/70">
                                        {zh ? "在時間軸以發光金框凸顯，適合必去景點" : "Highlighted with glowing amber border on timeline"}
                                    </p>
                                </div>
                                <Switch
                                    checked={!!editItem.is_highlight}
                                    onCheckedChange={(checked) => {
                                        haptic.tap()
                                        setEditItem({ ...editItem, is_highlight: checked })
                                    }}
                                />
                            </div>

                            {/* Private Mode Toggle */}
                            <div className="p-3.5 flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <div className="text-xs font-semibold text-slate-700 dark:text-slate-200 flex items-center gap-1.5">
                                        <span>🔒</span> {zh ? "私密行程" : "Private Activity"}
                                    </div>
                                    <p className="text-[11px] text-slate-400">
                                        {zh ? "僅供本人檢視 (本機標記)" : "Only visible to you (Local Tag)"}
                                    </p>
                                </div>
                                <Switch
                                    checked={!!editItem.is_private}
                                    onCheckedChange={(checked) => {
                                        haptic.tap()
                                        setEditItem({ ...editItem, is_private: checked })
                                    }}
                                />
                            </div>

                            {/* No Navigation Toggle */}
                            <div className="p-3.5 flex items-center justify-between">
                                <div className="space-y-0.5">
                                    <div className="text-xs font-semibold text-slate-700 dark:text-slate-200 flex items-center gap-1.5">
                                        <span>🗺️</span> {zh ? "不須導航" : "No Navigation"}
                                    </div>
                                    <p className="text-[11px] text-slate-400">
                                        {zh ? "在行程卡片上隱藏地圖導航按鈕" : "Hide map navigation button on card"}
                                    </p>
                                </div>
                                <Switch
                                    checked={!!editItem.hide_navigation}
                                    onCheckedChange={(checked) => {
                                        haptic.tap()
                                        setEditItem({ ...editItem, hide_navigation: checked })
                                    }}
                                />
                            </div>
                        </div>
                    </div>
                </div>
            </SheetContent>
        </Sheet>
    )
}
