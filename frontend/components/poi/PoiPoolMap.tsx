"use client"

import React, { useRef, useEffect, useState, useMemo, useCallback } from "react"
import Map, { Marker, Popup, NavigationControl, AttributionControl } from "react-map-gl/maplibre"
import type { MapRef } from "react-map-gl/maplibre"
import "maplibre-gl/dist/maplibre-gl.css"
import { setWorkerUrl } from "maplibre-gl"
import { POIItem } from "@/lib/poi-types"
import { parseCategory } from "@/lib/poi-category-protocol"
import { MAP_STYLES } from "@/lib/constants"
import { MapPin, Plus, ExternalLink, Compass } from "lucide-react"
import { cn, openExternalLink } from "@/lib/utils"
import { useLanguage } from "@/lib/LanguageContext"

if (typeof window !== "undefined") {
    setWorkerUrl("/maplibre/maplibre-gl-worker.mjs")
}

interface PoiPoolMapProps {
    pois: POIItem[]
    selectedPoiId?: string | null
    onSelectPoi?: (poi: POIItem) => void
    onSchedulePoi?: (poi: POIItem) => void
    className?: string
}

export default function PoiPoolMap({
    pois,
    selectedPoiId,
    onSelectPoi,
    onSchedulePoi,
    className
}: PoiPoolMapProps) {
    const { t } = useLanguage()
    const mapRef = useRef<MapRef | null>(null)
    const [popupPoi, setPopupPoi] = useState<POIItem | null>(null)

    // 有效座標的 POI 清單
    const validPois = useMemo(() => {
        return pois.filter((p) => typeof p.lat === "number" && typeof p.lng === "number" && !isNaN(p.lat) && !isNaN(p.lng) && p.lat !== 0 && p.lng !== 0)
    }, [pois])

    // 自動計算初始地圖視角
    const initialViewState = useMemo(() => {
        if (validPois.length > 0) {
            const first = validPois[0]
            return {
                longitude: first.lng,
                latitude: first.lat,
                zoom: 12,
            }
        }
        return {
            longitude: 120.3014,
            latitude: 22.6273,
            zoom: 11,
        }
    }, [validPois])

    // 當 POI 列表變動或使用者點選時自動縮放至包絡面 (Bounding Box)
    const fitAllPins = useCallback(() => {
        if (!mapRef.current || validPois.length === 0) return

        if (validPois.length === 1) {
            mapRef.current.flyTo({
                center: [validPois[0].lng, validPois[0].lat],
                zoom: 14,
                duration: 800,
            })
            return
        }

        let minLng = validPois[0].lng
        let maxLng = validPois[0].lng
        let minLat = validPois[0].lat
        let maxLat = validPois[0].lat

        for (const p of validPois) {
            if (p.lng < minLng) minLng = p.lng
            if (p.lng > maxLng) maxLng = p.lng
            if (p.lat < minLat) minLat = p.lat
            if (p.lat > maxLat) maxLat = p.lat
        }

        mapRef.current.fitBounds(
            [
                [minLng, minLat],
                [maxLng, maxLat],
            ],
            { padding: { top: 40, bottom: 40, left: 40, right: 40 }, maxZoom: 15, duration: 800 }
        )
    }, [validPois])

    // 首次載入或 POI 清單更換時自動視角聚焦
    useEffect(() => {
        const timer = setTimeout(() => {
            fitAllPins()
        }, 350)
        return () => clearTimeout(timer)
    }, [fitAllPins])

    // 外部選取 POI 時 FlyTo
    useEffect(() => {
        if (!selectedPoiId || !mapRef.current) return
        const target = validPois.find((p) => p.id === selectedPoiId)
        if (target) {
            mapRef.current.flyTo({
                center: [target.lng, target.lat],
                zoom: 15,
                duration: 700,
            })
        }
    }, [selectedPoiId, validPois])

    return (
        <div className={cn("relative w-full h-full overflow-hidden rounded-2xl border border-black/10 dark:border-white/10 shadow-inner bg-slate-100 dark:bg-slate-900", className)}>
            <Map
                ref={mapRef}
                initialViewState={initialViewState}
                mapStyle={MAP_STYLES.VECTOR}
                attributionControl={false}
                style={{ width: "100%", height: "100%" }}
            >
                <AttributionControl compact={true} position="bottom-right" />
                <NavigationControl position="top-right" showCompass={false} />

                {/* 📌 POI Markers */}
                {validPois.map((p) => {
                    const parsed = parseCategory(p.category)
                    const IconComp = parsed.icon || Compass
                    const isSelected = p.id === (selectedPoiId || popupPoi?.id)

                    return (
                        <Marker
                            key={p.id}
                            longitude={p.lng}
                            latitude={p.lat}
                            anchor="bottom"
                            onClick={(e) => {
                                e.originalEvent.stopPropagation()
                                setPopupPoi(p)
                                if (onSelectPoi) onSelectPoi(p)
                            }}
                        >
                            <div className="relative group cursor-pointer -translate-y-1 active:scale-95 transition-transform">
                                {/* 圓圈圖示標籤 */}
                                <div
                                    style={parsed.isCustom && !isSelected && !p.is_pinned ? { borderColor: parsed.color } : undefined}
                                    className={cn(
                                        "w-8 h-8 rounded-full flex items-center justify-center shadow-lg transition-all border-2",
                                        isSelected
                                            ? "bg-[#E56E25] text-white border-white scale-125 z-30 ring-4 ring-amber-500/30"
                                            : p.is_pinned
                                            ? "bg-amber-500 text-white border-white scale-110"
                                            : "bg-white dark:bg-[#1E2927] text-[#1E2927] dark:text-[#E5EBEA] border-[#E56E25]/60 hover:scale-115 hover:border-[#E56E25]"
                                    )}
                                >
                                    {parsed.isCustom ? (
                                        <span className="text-xs leading-none select-none">{parsed.emoji}</span>
                                    ) : (
                                        <IconComp className="w-4 h-4" />
                                    )}
                                </div>
                                {/* 針尖小倒三角 */}
                                <div
                                    style={parsed.isCustom && !isSelected && !p.is_pinned ? { borderTopColor: parsed.color } : undefined}
                                    className={cn(
                                        "w-0 h-0 border-l-4 border-l-transparent border-r-4 border-r-transparent border-t-[5px] mx-auto",
                                        isSelected ? "border-t-[#E56E25]" : p.is_pinned ? "border-t-amber-500" : "border-t-white dark:border-t-[#1E2927]"
                                    )}
                                />
                                {/* 懸浮地名標籤 */}
                                <div className="absolute left-1/2 -translate-x-1/2 -top-6 px-1.5 py-0.5 rounded-md bg-black/80 text-white text-[10px] font-bold whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none shadow-md">
                                    {p.title}
                                </div>
                            </div>
                        </Marker>
                    )
                })}

                {/* 💬 Marker Popup */}
                {popupPoi && (
                    <Popup
                        longitude={popupPoi.lng}
                        latitude={popupPoi.lat}
                        anchor="top"
                        onClose={() => setPopupPoi(null)}
                        closeOnClick={false}
                        className="tabidachi-map-popup"
                    >
                        <div className="p-1 space-y-1.5 max-w-52.5 text-left">
                            {(() => {
                                const popupCat = parseCategory(popupPoi.category)
                                return (
                                    <div className="flex items-center gap-1.5">
                                        <span
                                            className="inline-flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded-md"
                                            style={{ backgroundColor: `${popupCat.color}20`, color: popupCat.color }}
                                        >
                                            <span>{popupCat.emoji || "📍"}</span>
                                            <span>{popupCat.label}</span>
                                        </span>
                                    </div>
                                )
                            })()}
                            <h4 className="text-xs font-bold text-slate-800 dark:text-slate-100 truncate">
                                {popupPoi.title}
                            </h4>
                            {popupPoi.address && !popupPoi.address.startsWith("http") && !popupPoi.address.includes("%") && (
                                <p className="text-[10px] text-slate-500 dark:text-slate-400 line-clamp-2">
                                    {popupPoi.address}
                                </p>
                            )}
                            <div className="flex items-center gap-1.5 pt-1 border-t border-slate-100 dark:border-slate-800">
                                {onSchedulePoi && (
                                    <button
                                        type="button"
                                        onClick={() => {
                                            onSchedulePoi(popupPoi)
                                        }}
                                        className="flex-1 px-2 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-[10px] font-bold flex items-center justify-center gap-1 cursor-pointer transition-colors"
                                    >
                                        <Plus className="w-3 h-3" />
                                        <span>{t('poi_add_to_trip') || "排入行程"}</span>
                                    </button>
                                )}
                                <button
                                    type="button"
                                    onClick={() => {
                                        const url = popupPoi.source_url || `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(popupPoi.title)}`
                                        openExternalLink(url)
                                    }}
                                    className="p-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 text-slate-600 dark:text-slate-300 text-[10px] cursor-pointer"
                                    title={t('poi_open_maps') || "開啟地圖"}
                                >
                                    <ExternalLink className="w-3 h-3" />
                                </button>
                            </div>
                        </div>
                    </Popup>
                )}
            </Map>

            {/* 🎯 回到全局視角按鈕 */}
            <button
                type="button"
                onClick={fitAllPins}
                className="absolute left-3 bottom-3 px-2.5 py-1.5 rounded-xl bg-white/90 dark:bg-[#1E2927]/90 hover:bg-white dark:hover:bg-[#1E2927] text-[#1E2927] dark:text-[#E5EBEA] text-xs font-bold shadow-md border border-black/10 dark:border-white/10 flex items-center gap-1 backdrop-blur-md transition-all active:scale-95 cursor-pointer z-10"
                title={t('poi_fit_all') || "聚焦所有景點"}
            >
                <MapPin className="w-3.5 h-3.5 text-[#E56E25]" />
                <span>{t('poi_fit_all') || "全覽"} ({validPois.length})</span>
            </button>
        </div>
    )
}
