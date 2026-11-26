"use client"

import { useState, useRef, useCallback, useEffect } from "react"
import Map, { MapRef, Marker, Source, Layer, NavigationControl, AttributionControl, MapLayerMouseEvent, GlobeControl } from "react-map-gl/maplibre"
import { motion, AnimatePresence } from "framer-motion"
import { ArrowLeft, Satellite, Map as MapIcon, Search, X, Loader2, MapPin, Clock, Crosshair } from "lucide-react"
import { toast } from "sonner"
import "maplibre-gl/dist/maplibre-gl.css"
import { setWorkerUrl } from "maplibre-gl"

if (typeof window !== "undefined") {
    setWorkerUrl("/maplibre/maplibre-gl-worker.mjs")
}
import { Input } from "@/components/ui/input"
import { MAP_STYLES, MAP_LOCALIZATION } from "@/lib/constants"
import { geocodeApi } from "@/lib/api"
import POIDetailDrawer, { POIBasicData } from "@/components/POIDetailDrawer"
import { useLocalGeocode } from "@/hooks/useLocalGeocode"
import { debugLog } from "@/lib/debug"
import { useLanguage } from "@/lib/LanguageContext"
import { SearchResult } from "@/lib/itinerary-types"
import { getDistanceKm, getSmartZoomConfig, isMacroGeoResult, isUsableMacroExtent, dedupeGeocodeResults } from "@/lib/location-utils"

const INCOMPLETE_ZHUYIN_RE = /[\u3100-\u312F\u31A0-\u31BF]/

// ViewState 類型
interface ViewState {
    longitude: number
    latitude: number
    zoom: number
}

// 活動類型
interface Activity {
    id?: string
    time?: string
    place?: string
    lat?: number
    lng?: number
    category?: string
}

interface FullscreenMapModalProps {
    isOpen: boolean
    onClose: () => void
    initialViewState: ViewState
    activities: Activity[]
    onAddPOI?: (poi: POIBasicData, time: string, notes?: string) => void
    tripTitle?: string  // 🆕 行程標題（用於智能搜尋）
}

// 搜尋歷史 Hook
const HISTORY_KEY = "map_search_history"
function useSearchHistory() {
    const [history, setHistory] = useState<SearchResult[]>(() => {
        if (typeof window === 'undefined') return []
        try {
            const stored = localStorage.getItem(HISTORY_KEY)
            return stored ? JSON.parse(stored) : []
        } catch { return [] }
    })

    const addToHistory = useCallback((item: SearchResult) => {
        setHistory(prev => {
            const updated = [item, ...prev.filter(h => h.name !== item.name)].slice(0, 5)
            localStorage.setItem(HISTORY_KEY, JSON.stringify(updated))
            return updated
        })
    }, [])

    return { history, addToHistory }
}

export default function FullscreenMapModal({
    isOpen,
    onClose,
    initialViewState,
    activities,
    onAddPOI,
    tripTitle  // 🆕 行程標題
}: FullscreenMapModalProps) {
    const { t, lang } = useLanguage()
    const mapRef = useRef<MapRef>(null)
    const inputRef = useRef<HTMLInputElement>(null)
    const abortControllerRef = useRef<AbortController | null>(null)  // 🆕 P5: 取消前一個請求
    const requestSeqRef = useRef(0)
    const isComposingRef = useRef(false)
    const touchStartPosRef = useRef<{ x: number; y: number } | null>(null)
    const longPressTimerRef = useRef<NodeJS.Timeout | null>(null)
    const isMoveDetectedRef = useRef(false)
    const [mapMode, setMapMode] = useState<'standard' | 'satellite'>('standard')
    const [mapLoaded, setMapLoaded] = useState(false)

    // 搜尋狀態
    const [query, setQuery] = useState("")
    const [selectedQuery, setSelectedQuery] = useState<string | null>(null)
    const [results, setResults] = useState<SearchResult[]>([])
    const [isTyping, setIsTyping] = useState(false)     // 🆕 輸入中（debounce 期間）
    const [isSearching, setIsSearching] = useState(false) // 搜尋中（API 調用中）
    const [showSearch, setShowSearch] = useState(false)
    const { history, addToHistory } = useSearchHistory()

    // 📍 紅色大頭針狀態 (搜尋結果或手動點選)
    const [searchResultMarker, setSearchResultMarker] = useState<{ lat: number; lng: number; name: string } | null>(null)

    // POI Drawer 狀態
    const [poiDrawerOpen, setPoiDrawerOpen] = useState(false)
    const [selectedPOI, setSelectedPOI] = useState<POIBasicData | null>(null)
    const [userLocation, setUserLocation] = useState<{ lat: number; lng: number } | null>(null)
    const [isLocating, setIsLocating] = useState(false)

    // 標記點
    const markers = activities.filter(a => a.lat && a.lng) as (Activity & { lat: number; lng: number })[]

    // 🆕 輸入變更處理（立即回饋）
    const handleQueryChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const value = e.target.value
        setSelectedQuery(null)
        setQuery(value)
        if (value.length >= 2 && !INCOMPLETE_ZHUYIN_RE.test(value)) {
            setIsTyping(true)  // 立即顯示「準備中」
        } else {
            setIsTyping(false)
            if (value.length < 2) {
                setResults([])
            }
        }
    }

    // 🏕️ Local Geocode Hook (L1 本地秒回)
    const { search: localSearch, isLoaded: localDataLoaded } = useLocalGeocode()

    // Debounced 搜尋 (L1 本地 + L2 API，AbortController + requestSeq 防競態 + 保留後端智慧排序全量顯示)
    useEffect(() => {
        if (query.length < 2) {
            abortControllerRef.current?.abort()
            requestSeqRef.current += 1
            setResults([])
            setIsTyping(false)
            setIsSearching(false)
            return
        }

        // 關閉搜尋面板或剛點選某筆結果時不發送多餘 L2 API 請求（保留結果列表供重新開啟）
        if (!showSearch || selectedQuery === query) {
            abortControllerRef.current?.abort()
            requestSeqRef.current += 1
            setIsTyping(false)
            setIsSearching(false)
            return
        }

        // 進入新防抖週期前中止舊請求並清掉舊 loading 態，避免鍵入新字時舊 spinner 殘留
        abortControllerRef.current?.abort()
        setIsSearching(false)

        const currentQuery = query  // 🆕 快照防止競態
        let localMapped: SearchResult[] = []

        // 🏕️ L1: 本地即時搜尋 (毫秒級，全量回傳精準匹配結果)
        if (localDataLoaded) {
            const localResults = localSearch(currentQuery)
            if (localResults.length > 0) {
                const mapped: SearchResult[] = localResults
                    .filter(r => r.lat && r.lng)
                    .map(r => ({
                        name: r.display,
                        lat: r.lat!,
                        lng: r.lng!,
                        address: r.country || '',
                        country: r.country,
                        type: r.type,
                        source: 'local' as const
                    }))
                if (mapped.length > 0) {
                    localMapped = mapped
                    setResults(localMapped)
                    setIsTyping(false)
                    debugLog(`🏕️ L1 本地秒回: ${mapped.length} 筆結果`)
                }
            }
        }

        // 🛡️ 未完成注音符號早退：僅呈現 L1 本地結果，重設輸入/搜尋狀態，不消耗 L2 API
        if (INCOMPLETE_ZHUYIN_RE.test(currentQuery)) {
            abortControllerRef.current?.abort()
            requestSeqRef.current += 1
            setIsTyping(false)
            setIsSearching(false)
            setResults(localMapped)
            return
        }

        // 🆕 API 搜尋 (300ms debounce)
        const timer = setTimeout(async () => {
            // 🆕 P5: 取消前一個尚未完成的請求
            abortControllerRef.current?.abort()
            const controller = new AbortController()
            abortControllerRef.current = controller
            const signal = controller.signal
            const seq = ++requestSeqRef.current

            setIsTyping(false)
            setIsSearching(true)
            setResults(localMapped)
            try {
                const center = mapRef.current?.getCenter()
                const currentZoom = mapRef.current?.getZoom() ?? initialViewState.zoom ?? 12

                const data = await geocodeApi.search({
                    query: currentQuery,
                    tripTitle,
                    lat: center?.lat ?? initialViewState.latitude,
                    lng: center?.lng ?? initialViewState.longitude,
                    zoom: currentZoom,
                    locale: lang,
                    signal
                })
                if (seq !== requestSeqRef.current || signal.aborted) {
                    return
                }

                const rawResults: SearchResult[] = data.results || []
                // 優先保留後端智慧排序 ([...rawResults])，再併入未重複之 L1 本地結果（(normOsmType, osm_id) + 同名 50m 全域去重）
                const combined: SearchResult[] = dedupeGeocodeResults([...rawResults, ...localMapped])

                const latestCenter = mapRef.current?.getCenter()
                const refLat = userLocation?.lat ?? latestCenter?.lat ?? initialViewState.latitude
                const refLng = userLocation?.lng ?? latestCenter?.lng ?? initialViewState.longitude
                const withDistance = combined.map(r => ({
                    ...r,
                    _distKm: getDistanceKm(refLat, refLng, r.lat, r.lng)
                }))

                setResults(withDistance)
                debugLog(`🔄 Merged ${rawResults.length} cloud + ${localMapped.length} local results`)
            } catch (e) {
                // 🆕 P5: 忽略 AbortError (正常取消行為)
                if (e instanceof Error && e.name === 'AbortError') {
                    debugLog(`🚫 L2 請求已取消: ${currentQuery}`)
                    return
                }
                if (seq === requestSeqRef.current && !signal.aborted) {
                    setResults(localMapped)
                }
            } finally {
                if (seq === requestSeqRef.current && !signal.aborted) {
                    setIsSearching(false)
                }
            }
        }, 300)

        return () => {
            clearTimeout(timer)
            abortControllerRef.current?.abort()  // 🆕 cleanup 時也取消
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [query, selectedQuery, showSearch, tripTitle, initialViewState.latitude, initialViewState.longitude, localDataLoaded, localSearch])

    // Esc 鍵退出（若上層圖片 Lightbox 開啟或事件已被攔截，優先讓 Lightbox 關閉）
    useEffect(() => {
        const handleEsc = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                if (e.isComposing || e.defaultPrevented || document.querySelector('[data-testid="poi-image-lightbox"]')) {
                    return
                }
                if (showSearch) {
                    setShowSearch(false)
                } else {
                    onClose()
                }
            }
        }
        window.addEventListener("keydown", handleEsc)
        return () => window.removeEventListener("keydown", handleEsc)
    }, [onClose, showSearch])

    // 自動 focus 搜尋框
    useEffect(() => {
        if (showSearch && inputRef.current) {
            inputRef.current.focus()
        }
    }, [showSearch])

    // 飛到指定位置（L2-1 智慧分流：宏觀行政區僅 fitBounds/flyTo 展開視野不開抽屜；具體 POI 插紅針並開抽屜）
    const flyTo = useCallback((result: SearchResult) => {
        addToHistory(result)
        setSelectedQuery(result.name)
        setQuery(result.name)
        setShowSearch(false)
        const zoomConfig = getSmartZoomConfig(result)

        if (isMacroGeoResult(result)) {
            setSearchResultMarker(null)
            setPoiDrawerOpen(false)
            if (isUsableMacroExtent(result.extent)) {
                const [minLon, minLat, maxLon, maxLat] = result.extent
                mapRef.current?.fitBounds(
                    [[minLon, minLat], [maxLon, maxLat]],
                    {
                        padding: 48,
                        duration: zoomConfig.duration,
                        maxZoom: zoomConfig.zoom,
                        bearing: 0,
                        pitch: 0,
                    }
                )
            } else {
                mapRef.current?.flyTo({
                    center: [result.lng, result.lat],
                    zoom: zoomConfig.zoom,
                    duration: zoomConfig.duration,
                    bearing: 0,
                    pitch: 0,
                })
            }
            return
        }

        mapRef.current?.flyTo({
            center: [result.lng, result.lat],
            zoom: zoomConfig.zoom,
            duration: zoomConfig.duration
        })

        // 🆕 設置標記點（紅色大頭針）
        setSearchResultMarker({ lat: result.lat, lng: result.lng, name: result.name })

        // 建立 POI 並開啟 Drawer
        setSelectedPOI({
            name: result.name,
            type: result.type || "place",
            lat: result.lat,
            lng: result.lng,
            address: result.address
        })
        setPoiDrawerOpen(true)
    }, [addToHistory])

    // 📍 定位功能
    const handleLocateMe = useCallback(() => {
        if (!("geolocation" in navigator)) {
            toast.error(t('map_geolocation_unsupported'))
            return
        }
        setIsLocating(true)
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const { latitude, longitude } = position.coords
                setUserLocation({ lat: latitude, lng: longitude })
                setIsLocating(false)

                // 飛到用戶位置
                mapRef.current?.flyTo({
                    center: [longitude, latitude],
                    zoom: 15,
                    duration: 1000
                })
            },
            (error) => {
                setIsLocating(false)
                console.error("Geolocation error:", error)
                if (error.code === error.PERMISSION_DENIED) {
                    toast.error(t('map_geolocation_denied'))
                } else {
                    toast.error(t('map_geolocation_failed') + error.message)
                }
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        )
    }, [t])

    // 地圖載入
    const handleMapLoad = useCallback(() => {
        setMapLoaded(true)
        const map = mapRef.current?.getMap()
        if (!map) return

        if (!map.getSource('satellite')) {
            map.addSource('satellite', {
                type: 'raster',
                tiles: [MAP_STYLES.SATELLITE],
                tileSize: 256
            })
        }
        if (!map.getLayer('satellite-layer')) {
            map.addLayer({
                id: 'satellite-layer',
                type: 'raster',
                source: 'satellite',
                layout: { visibility: 'none' }
            }, map.getStyle()?.layers?.[0]?.id)
        }

        // 🌍 全球中文化：所有標籤優先顯示繁體中文
        const allLayers = map.getStyle()?.layers || []
        let chineseLayerCount = 0
        allLayers.forEach(layer => {
            if (layer.type === 'symbol' && 'layout' in layer && layer.layout?.['text-field']) {
                try {
                    map.setLayoutProperty(layer.id, 'text-field', MAP_LOCALIZATION.CHINESE_LABEL_EXPRESSION)
                    chineseLayerCount++
                } catch { /* 部分圖層可能不支援 */ }
            }
        })
        debugLog(`🌍 全螢幕地圖: 已將 ${chineseLayerCount} 個標籤圖層中文化`)
    }, [])

    // 切換衛星模式
    const toggleMapMode = useCallback(() => {
        const map = mapRef.current?.getMap()
        if (!map || !mapLoaded) return

        const newMode = mapMode === 'standard' ? 'satellite' : 'standard'
        setMapMode(newMode)
        map.setLayoutProperty('satellite-layer', 'visibility', newMode === 'satellite' ? 'visible' : 'none')
    }, [mapMode, mapLoaded])

    // POI 點擊
    const handleMapClick = useCallback((e: MapLayerMouseEvent) => {
        const map = mapRef.current?.getMap()
        if (!map) return

        const features = map.queryRenderedFeatures(e.point, {
            layers: map.getStyle()?.layers?.filter(l => l.id.includes('poi') || l.id.includes('label')).map(l => l.id) || []
        })

        if (features.length > 0) {
            const feature = features[0]
            const props = feature.properties || {}
            const coords = feature.geometry.type === 'Point'
                ? (feature.geometry as GeoJSON.Point).coordinates
                : [e.lngLat.lng, e.lngLat.lat]

            // 🌍 中文名稱優先級
            const getName = () => {
                for (const key of MAP_LOCALIZATION.CHINESE_NAME_KEYS) {
                    if (props[key]) return props[key]
                }
                return t('map_location_point')
            }

            const poiData: POIBasicData = {
                name: getName(),
                type: props.class || props.subclass || 'place',
                lat: coords[1] as number,
                lng: coords[0] as number,
                address: props.address
            }

            // 🆕 設置標記點（紅色大頭針）
            setSearchResultMarker({ lat: poiData.lat, lng: poiData.lng, name: poiData.name })

            setSelectedPOI(poiData)
            setPoiDrawerOpen(true)
        }
    }, [t])

    // 🆕 2026 Logic: 處理地圖長按 (任意取點)
    const handleMapLongPress = useCallback((e: MapLayerMouseEvent) => {
        const { lng, lat } = e.lngLat

        const poiData: POIBasicData = {
            name: t('map_location_point'),
            type: 'place',
            lat: lat,
            lng: lng,
        }

        // 設置標記點（紅色大頭針）
        setSearchResultMarker({ lat, lng, name: poiData.name })

        setSelectedPOI(poiData)
        setPoiDrawerOpen(true)
    }, [t])

    // 🆕 跨設備長按偵測 (手機/平板/電腦)
    const handlePointerStart = useCallback((e: MapLayerMouseEvent) => {
        const isTouchEvent = 'touches' in e.originalEvent
        if (isTouchEvent && (e.originalEvent as unknown as TouchEvent).touches?.length > 1) return

        const { x, y } = e.point
        touchStartPosRef.current = { x, y }
        isMoveDetectedRef.current = false

        if (longPressTimerRef.current) clearTimeout(longPressTimerRef.current)

        longPressTimerRef.current = setTimeout(() => {
            handleMapLongPress(e)
            longPressTimerRef.current = null
        }, 500)
    }, [handleMapLongPress])

    const handlePointerMove = useCallback((e: MapLayerMouseEvent) => {
        if (!touchStartPosRef.current) return

        const { x, y } = e.point
        const dist = Math.sqrt(
            Math.pow(x - touchStartPosRef.current.x, 2) +
            Math.pow(y - touchStartPosRef.current.y, 2)
        )

        // 🆕 2026 修復：若移動超過 5 像素，判定為平移並鎖定狀態，取消長按計時
        if (dist > 5) {
            isMoveDetectedRef.current = true
            if (longPressTimerRef.current) {
                clearTimeout(longPressTimerRef.current)
                longPressTimerRef.current = null
            }
        }
    }, [])

    const handlePointerEnd = useCallback(() => {
        if (longPressTimerRef.current) {
            clearTimeout(longPressTimerRef.current)
            longPressTimerRef.current = null
        }
        touchStartPosRef.current = null
    }, [])

    // 🆕 2026 修復：監聽地圖原生移動事件，一旦開始平移則鎖定狀態並取消計時
    const handleMapMoveStart = useCallback(() => {
        isMoveDetectedRef.current = true
        if (longPressTimerRef.current) {
            clearTimeout(longPressTimerRef.current)
            longPressTimerRef.current = null
        }
    }, [])

    // 🆕 卸載時清理定時器
    useEffect(() => {
        return () => {
            if (longPressTimerRef.current) clearTimeout(longPressTimerRef.current)
        }
    }, [])

    if (!isOpen) return null

    const showHistory = query.length === 0 && history.length > 0
    // 🆕 統一「搜尋完成」狀態：排除未完成注音與剛點選結果重開狀態，避免誤閃「無結果」
    const hasIncompleteZhuyin = INCOMPLETE_ZHUYIN_RE.test(query)
    const searchDone = query.length >= 2 && !hasIncompleteZhuyin && selectedQuery !== query && !isTyping && !isSearching
    const showResults = query.length >= 2 && !isTyping && results.length > 0
    const showNoResults = searchDone && results.length === 0

    return (
        <AnimatePresence>
            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="fixed inset-0 z-9999 bg-black"
            >
                {/* 🗺️ 全螢幕地圖 */}
                <Map
                    ref={mapRef}
                    initialViewState={initialViewState}
                    style={{ width: "100%", height: "100%" }}
                    mapStyle={mapMode === 'satellite' ? MAP_STYLES.SATELLITE : MAP_STYLES.VECTOR}
                    onLoad={handleMapLoad}
                    onMoveStart={handleMapMoveStart}
                    onMouseDown={handlePointerStart}
                    onMouseMove={handlePointerMove}
                    onMouseUp={handlePointerEnd}
                    onClick={handleMapClick}
                    onContextMenu={(e) => {
                        // 🆕 2026 修復：僅在非觸控移動時允許觸發長按邏輯
                        e.originalEvent.preventDefault()
                        if (!isMoveDetectedRef.current) {
                            handleMapLongPress(e)
                        }
                    }}
                    attributionControl={false}
                    minZoom={1}
                    maxZoom={20}
                    projection="globe"
                >
                    <NavigationControl position="top-right" showCompass={false} />
                    <GlobeControl position="top-right" />
                    <AttributionControl position="bottom-right" compact />

                    {/* 路線 */}
                    {markers.length >= 2 && (
                        <Source
                            id="route-line"
                            type="geojson"
                            data={{
                                type: "Feature",
                                properties: {},
                                geometry: {
                                    type: "LineString",
                                    coordinates: markers.map(m => [m.lng, m.lat])
                                }
                            }}
                        >
                            <Layer
                                id="route"
                                type="line"
                                paint={{
                                    "line-color": "#6366f1",
                                    "line-width": 4,
                                    "line-opacity": 0.8
                                }}
                            />
                        </Source>
                    )}

                    {/* 標記點 */}
                    {markers.map((m, i) => (
                        <Marker key={`marker-${i}`} longitude={m.lng} latitude={m.lat}>
                            <div className="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center text-sm font-bold shadow-lg border-2 border-white">
                                {i + 1}
                            </div>
                        </Marker>
                    ))}

                    {/* 📍 用戶位置藍點標記 */}
                    {userLocation && (
                        <Marker
                            longitude={userLocation.lng}
                            latitude={userLocation.lat}
                            anchor="center"
                        >
                            <div className="relative">
                                <div className="absolute -inset-3 bg-blue-400/30 rounded-full animate-ping" />
                                <div className="w-4 h-4 bg-blue-500 border-2 border-white rounded-full shadow-lg" />
                            </div>
                        </Marker>
                    )}

                    {/* 🆕 搜尋結果標記（紅色大頭針） */}
                    {searchResultMarker && (
                        <Marker
                            key="search-pin"
                            longitude={searchResultMarker.lng}
                            latitude={searchResultMarker.lat}
                            anchor="bottom"
                        >
                            <div className="relative animate-bounce" style={{ animationDuration: '0.6s', animationIterationCount: 3 }}>
                                {/* 陰影 */}
                                <div
                                    className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-4 h-1 bg-black/30 rounded-full blur-sm"
                                />
                                {/* 大頭針 */}
                                <div className="relative">
                                    {/* 針體 */}
                                    <div
                                        className="w-8 h-8 bg-red-500 rounded-full border-3 border-white shadow-lg flex items-center justify-center"
                                        style={{
                                            boxShadow: '0 4px 12px rgba(239, 68, 68, 0.5), 0 2px 4px rgba(0,0,0,0.2)'
                                        }}
                                    >
                                        <div className="w-2 h-2 bg-white rounded-full" />
                                    </div>
                                    {/* 針尖 */}
                                    <div
                                        className="absolute left-1/2 -translate-x-1/2 w-0 h-0"
                                        style={{
                                            borderLeft: '6px solid transparent',
                                            borderRight: '6px solid transparent',
                                            borderTop: '10px solid #ef4444',
                                            top: '26px'
                                        }}
                                    />
                                </div>
                            </div>
                        </Marker>
                    )}
                </Map>

                {/* 🔙 返回按鈕 (左上角，簡化) */}
                <button
                    onClick={onClose}
                    className="absolute top-4 left-4 z-20 h-12 w-12 bg-white rounded-full shadow-lg flex items-center justify-center hover:bg-slate-50 transition-colors"
                    style={{ top: "max(16px, env(safe-area-inset-top))" }}
                >
                    <ArrowLeft className="w-6 h-6 text-slate-700" />
                </button>

                {/* 🛰️ 衛星切換 (右下角) */}
                <button
                    onClick={toggleMapMode}
                    className="absolute bottom-24 right-4 z-20 h-12 w-12 bg-white rounded-full shadow-lg flex items-center justify-center hover:bg-slate-50 transition-colors"
                >
                    {mapMode === 'satellite' ? <MapIcon className="w-5 h-5" /> : <Satellite className="w-5 h-5" />}
                </button>

                {/* 📍 定位按鈕 */}
                <button
                    onClick={handleLocateMe}
                    disabled={isLocating}
                    className="absolute bottom-40 right-4 z-20 h-12 w-12 bg-white rounded-full shadow-lg flex items-center justify-center hover:bg-slate-50 active:scale-95 transition-all disabled:opacity-50"
                    title={t('map_my_location') || "定位我的位置"}
                >
                    {isLocating ? (
                        <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
                    ) : (
                        <Crosshair className="w-5 h-5 text-blue-500" />
                    )}
                </button>

                {/* 🔍 搜尋按鈕 (底部固定) */}
                {!showSearch && (
                    <button
                        onClick={() => setShowSearch(true)}
                        className="absolute bottom-6 left-4 right-4 z-20 h-14 bg-white rounded-full shadow-xl flex items-center px-5 gap-3 hover:bg-slate-50 transition-colors"
                        style={{ marginBottom: "env(safe-area-inset-bottom)" }}
                    >
                        <Search className="w-5 h-5 text-slate-400" />
                        <span className="text-slate-500">{t('map_search_ai')}</span>
                    </button>
                )}

                {/* 🔍 搜尋 Sheet (底部展開) */}
                <AnimatePresence>
                    {showSearch && (
                        <motion.div
                            initial={{ y: "100%" }}
                            animate={{ y: 0 }}
                            exit={{ y: "100%" }}
                            transition={{ type: "spring", damping: 25, stiffness: 300 }}
                            className="absolute bottom-0 left-0 right-0 z-30 bg-white rounded-t-3xl shadow-2xl"
                            style={{ paddingBottom: "max(16px, env(safe-area-inset-bottom))" }}
                        >
                            {/* 拖曳指示條 */}
                            <div className="flex justify-center py-3">
                                <div className="w-10 h-1 bg-slate-300 rounded-full" />
                            </div>

                            {/* 搜尋輸入 */}
                            <div className="px-4 pb-2">
                                <div className="relative">
                                    <Search className="absolute left-4 top-3.5 w-5 h-5 text-slate-400" />
                                    <Input
                                        ref={inputRef}
                                        value={query}
                                        onChange={handleQueryChange}
                                        onCompositionStart={() => { isComposingRef.current = true }}
                                        onCompositionEnd={() => { setTimeout(() => { isComposingRef.current = false }, 0) }}
                                        onKeyDown={(e) => {
                                            if (e.key === 'Enter') {
                                                if (e.nativeEvent.isComposing || isComposingRef.current || e.nativeEvent.keyCode === 229) return
                                                if (results.length > 0 && !isTyping && !isSearching) {
                                                    flyTo(results[0])
                                                }
                                            }
                                        }}
                                        placeholder={t('map_search_ai')}
                                        className="h-12 pl-12 pr-10 rounded-xl border-slate-200 text-base"
                                    />
                                    {query && (
                                        <button
                                            onClick={() => {
                                                setSelectedQuery(null)
                                                setQuery("")
                                                setIsTyping(false)
                                                setResults([])
                                            }}
                                            className="absolute right-3 top-3.5 text-slate-400 hover:text-slate-600"
                                        >
                                            <X className="w-5 h-5" />
                                        </button>
                                    )}
                                </div>
                            </div>

                            {/* 結果列表（四重軸向鎖定，可滾動顯示全量智慧排序結果與長地名自動換行） */}
                            <div
                                className="max-h-[55vh] overflow-y-auto overflow-x-hidden overscroll-x-none overscroll-y-contain touch-pan-y"
                                style={{ touchAction: "pan-y" }}
                            >
                                {/* 歷史紀錄 */}
                                {showHistory && (
                                    <>
                                        <div className="px-4 py-2 text-xs font-medium text-slate-400 uppercase">{t('map_recent_search')}</div>
                                        {history.map((h, i) => (
                                            <button
                                                key={i}
                                                onClick={() => flyTo(h)}
                                                className="w-full max-w-full min-w-0 overflow-hidden px-4 py-3 text-left hover:bg-slate-50 flex items-start gap-3"
                                            >
                                                <Clock className="w-4 h-4 mt-0.5 text-slate-400 shrink-0" />
                                                <span className="min-w-0 flex-1 wrap-break-word [word-break:break-word] whitespace-normal line-clamp-2 leading-snug">{h.name}</span>
                                            </button>
                                        ))}
                                    </>
                                )}

                                {/* 🆕 輸入中（debounce 期間）- 淡色提示 */}
                                {isTyping && !isSearching && (
                                    <div className="px-4 py-4 flex items-center gap-2 text-slate-400 transition-opacity duration-200">
                                        <div className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-pulse" />
                                        <span className="text-sm">{t('map_enter_query')}</span>
                                    </div>
                                )}

                                {/* 搜尋中（API 調用中）- 明顯 Loading */}
                                {isSearching && (
                                    <div className="px-4 py-6 flex items-center justify-center gap-2 text-indigo-500 transition-opacity duration-200">
                                        <Loader2 className="w-4 h-4 animate-spin" />
                                        <span>{t('map_searching')}</span>
                                    </div>
                                )}

                                {/* 搜尋結果 */}
                                {showResults && results.map((r, i) => (
                                    <button
                                        key={r.osm_id ? `${r.osm_type || 'x'}-${r.osm_id}-${i}` : i}
                                        onClick={() => flyTo(r)}
                                        className="w-full max-w-full min-w-0 overflow-hidden px-4 py-3 text-left hover:bg-slate-50 flex items-start gap-3"
                                    >
                                        <MapPin className="w-4 h-4 mt-0.5 text-slate-400 shrink-0" />
                                        <div className="min-w-0 flex-1">
                                            <div className="font-medium wrap-break-word [word-break:break-word] whitespace-normal leading-snug">
                                                {r.name}
                                                {r.cross_country && (
                                                    <span className="text-[10px] text-amber-500 ml-1 font-medium">🌍</span>
                                                )}
                                            </div>
                                            {r.address && (
                                                <div className="text-xs text-slate-500 wrap-break-word [word-break:break-word] whitespace-normal line-clamp-2 leading-snug">{r.address}</div>
                                            )}
                                            {(r.city || r.country) && (
                                                <p className="text-[11px] text-slate-400 mt-0.5 wrap-break-word [word-break:break-word] whitespace-normal leading-snug">
                                                    {[r.city, r.country].filter(Boolean).join(" · ")}
                                                </p>
                                            )}
                                            {r._distKm != null && (
                                                <div className="text-[10px] text-slate-400 mt-1 flex items-center gap-1">
                                                    <span className="bg-slate-100 px-1.5 py-0.5 rounded-md font-medium">
                                                        📍 {r._distKm.toFixed(1)} km
                                                    </span>
                                                </div>
                                            )}
                                        </div>
                                    </button>
                                ))}

                                {/* 🆕 無結果提示 */}
                                {showNoResults && (
                                    <div className="px-4 py-4 text-center text-slate-500 text-sm">
                                        {t('map_no_results', { query })}
                                    </div>
                                )}

                                {/* AI 語意搜尋選項 - 暫時隱藏，保留程式碼供未來開發 */}
                                {/* {showAIOption && (
                                    <button
                                        onClick={handleAISearch}
                                        disabled={aiSearching}
                                        className="w-full px-4 py-3 text-left hover:bg-purple-50 flex items-center gap-3 border-t"
                                    >
                                        {aiSearching ? (
                                            <>
                                                <Loader2 className="w-5 h-5 text-purple-500 animate-spin" />
                                                <span className="text-purple-600">🧠 AI 正在分析位置...</span>
                                            </>
                                        ) : (
                                            <>
                                                <Sparkles className="w-5 h-5 text-purple-500" />
                                                <span>
                                                    <span className="font-medium text-purple-600">✨ 使用 AI 搜尋</span>
                                                    <span className="text-slate-500 ml-1">「{query}」</span>
                                                </span>
                                            </>
                                        )}
                                    </button>
                                )} */}
                            </div>

                            {/* 關閉按鈕 */}
                            <div className="px-4 pt-2">
                                <button
                                    onClick={() => setShowSearch(false)}
                                    className="w-full py-3 text-slate-500 text-sm font-medium"
                                >
                                    {t('cancel')}
                                </button>
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* 📍 POI Detail Drawer */}
                <POIDetailDrawer
                    isOpen={poiDrawerOpen}
                    onClose={() => {
                        setPoiDrawerOpen(false)
                        setSearchResultMarker(null)
                    }}
                    poi={selectedPOI}
                    suggestedTime="12:00"
                    onAddToItinerary={(poi, time, aiSummary) => {
                        if (onAddPOI) {
                            const notes = aiSummary
                                ? `${aiSummary.summary}\n必點: ${aiSummary.must_try?.join(', ') || ''}`
                                : undefined
                            onAddPOI(poi, time, notes)
                        }
                    }}
                />
            </motion.div>
        </AnimatePresence>
    )
}
