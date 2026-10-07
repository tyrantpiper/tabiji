"use client"

import React, { useState } from "react"
import { Footprints, Train, Car, Bike, ExternalLink, Settings2, Clock, Check } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { cn } from "@/lib/utils"
import { useLanguage } from "@/lib/LanguageContext"
import { useHaptic } from "@/lib/hooks"
import { Activity } from "@/lib/itinerary-types"
import {
    computeTransitSegment,
    TravelMode,
    isValidCoordinate
} from "@/lib/transit-connector"

interface TransitSegmentConnectorProps {
    fromActivity: Activity
    toActivity: Activity
    onUpdateFromActivity?: (id: string, updates: Partial<Activity>) => Promise<boolean>
    className?: string
}

const MODE_ICONS: Record<TravelMode, React.ReactNode> = {
    walking: <Footprints className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />,
    transit: <Train className="w-3 h-3 text-indigo-600 dark:text-indigo-400" />,
    driving: <Car className="w-3 h-3 text-amber-600 dark:text-amber-400" />,
    bicycling: <Bike className="w-3 h-3 text-sky-600 dark:text-sky-400" />
}

export const TRANSIT_MODE_PLACEHOLDERS: Record<TravelMode, { zh: string; en: string }> = {
    transit: {
        zh: "如: 地鐵2號線/公車/高鐵",
        en: "e.g. Metro / Bus / Express"
    },
    driving: {
        zh: "如: Uber/計程車/自駕",
        en: "e.g. Uber / Taxi / Drive"
    },
    walking: {
        zh: "如: 經公園步道/地下街",
        en: "e.g. Park Walk / Underpass"
    },
    bicycling: {
        zh: "如: 共享單車/自行車道",
        en: "e.g. Shared Bike / Path"
    }
}

export const TRANSIT_QUICK_CHIPS: Record<TravelMode, Array<{ labelZh: string; labelEn: string; value: string }>> = {
    transit: [
        { labelZh: "🚇 地鐵/捷運", labelEn: "🚇 Metro", value: "地鐵" },
        { labelZh: "🚌 巴士/公車", labelEn: "🚌 Bus", value: "公車" },
        { labelZh: "🚄 火車/高鐵", labelEn: "🚄 Train", value: "火車" },
        { labelZh: "⛴️ 渡輪", labelEn: "⛴️ Ferry", value: "渡輪" }
    ],
    driving: [
        { labelZh: "🚕 計程車", labelEn: "🚕 Taxi", value: "計程車" },
        { labelZh: "🚗 Uber", labelEn: "🚗 Uber", value: "Uber" },
        { labelZh: "🚙 租車自駕", labelEn: "🚙 Rental", value: "租車" }
    ],
    walking: [
        { labelZh: "🚶 步行直達", labelEn: "🚶 Direct", value: "步行直達" },
        { labelZh: "🌳 經步道", labelEn: "🌳 Walkway", value: "經步道" },
        { labelZh: "🛍️ 地下街", labelEn: "🛍️ Underground", value: "地下街" }
    ],
    bicycling: [
        { labelZh: "🚲 共享單車", labelEn: "🚲 Share Bike", value: "共享單車" },
        { labelZh: "🚴 專用車道", labelEn: "🚴 Bike Lane", value: "專用車道" }
    ]
}

export function TransitSegmentConnector({
    fromActivity,
    toActivity,
    onUpdateFromActivity,
    className
}: TransitSegmentConnectorProps) {
    const { lang } = useLanguage()
    const zh = lang === 'zh'
    const haptic = useHaptic()

    const [isOpen, setIsOpen] = useState(false)
    const [selectedMode, setSelectedMode] = useState<TravelMode>(
        (fromActivity.transit_override?.mode as TravelMode) || 'walking'
    )
    const [customMinutes, setCustomMinutes] = useState<string>(
        fromActivity.transit_override?.duration_minutes ? String(fromActivity.transit_override.duration_minutes) : ""
    )
    const [customNote, setCustomNote] = useState<string>(
        fromActivity.transit_override?.custom_note || ""
    )
    const [isSaving, setIsSaving] = useState(false)

    // 🛡️ 座標有效性檢查
    if (
        !isValidCoordinate(fromActivity.lat, fromActivity.lng) ||
        !isValidCoordinate(toActivity.lat, toActivity.lng)
    ) {
        return null
    }

    const origin = {
        lat: Number(fromActivity.lat),
        lng: Number(fromActivity.lng),
        name: fromActivity.place_name || fromActivity.place || ""
    }
    const destination = {
        lat: Number(toActivity.lat),
        lng: Number(toActivity.lng),
        name: toActivity.place_name || toActivity.place || ""
    }

    const segment = computeTransitSegment(
        origin,
        destination,
        (fromActivity.transit_override?.mode as TravelMode) || undefined
    )

    if (!segment) return null

    // 優先使用手動覆寫時間，其次使用演算法推估時間
    const displayMinutes = fromActivity.transit_override?.duration_minutes || segment.estimatedMinutes
    const displayMode = (fromActivity.transit_override?.mode as TravelMode) || segment.recommendedMode

    const handleSaveOverride = async () => {
        if (!onUpdateFromActivity || !fromActivity.id) return
        setIsSaving(true)
        haptic.tap()

        const parsedMinutes = customMinutes ? parseInt(customMinutes, 10) : undefined
        const updates: Partial<Activity> = {
            transit_override: {
                mode: selectedMode,
                duration_minutes: Number.isFinite(parsedMinutes) && (parsedMinutes || 0) > 0 ? parsedMinutes : undefined,
                custom_note: customNote.trim() || undefined
            }
        }

        try {
            await onUpdateFromActivity(fromActivity.id, updates)
            setIsOpen(false)
        } catch (e) {
            console.error("Failed to save transit override:", e)
        } finally {
            setIsSaving(false)
        }
    }

    return (
        <div
            className={cn("my-1.5 flex items-center justify-center relative z-10 touch-manipulation", className)}
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => e.stopPropagation()}
        >
            <Popover open={isOpen} onOpenChange={setIsOpen}>
                <PopoverTrigger asChild>
                    <button
                        type="button"
                        aria-label="Transit Segment Options"
                        className={cn(
                            "group inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium transition-all shadow-2xs",
                            "bg-white/90 dark:bg-slate-800/90 hover:bg-slate-100 dark:hover:bg-slate-700",
                            "border border-slate-200/80 dark:border-slate-700/80 text-slate-700 dark:text-slate-300",
                            "active:scale-95 cursor-pointer backdrop-blur-xs select-none"
                        )}
                        onClick={() => {
                            haptic.tap()
                            setIsOpen(!isOpen)
                        }}
                    >
                        {MODE_ICONS[displayMode] || MODE_ICONS.walking}
                        <span className="tracking-tight">{displayMinutes} {zh ? "分" : "min"}</span>
                        <span className="text-slate-300 dark:text-slate-600">·</span>
                        <span className="text-[10px] text-slate-500 dark:text-slate-400 font-normal">
                            {segment.distanceKm} km
                        </span>
                        {fromActivity.transit_override?.custom_note && (
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 ml-0.5" />
                        )}
                    </button>
                </PopoverTrigger>

                <PopoverContent
                    side="bottom"
                    align="center"
                    className="w-[min(94vw,480px)] sm:w-115 p-4.5 sm:p-5 rounded-3xl bg-white/98 dark:bg-slate-900/98 backdrop-blur-md shadow-2xl border border-slate-200/90 dark:border-slate-800 text-xs"
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={(e) => e.stopPropagation()}
                >
                    <div className="space-y-4">
                        <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-2.5">
                            <span className="font-bold text-sm text-slate-800 dark:text-slate-100 flex items-center gap-1.5">
                                <Settings2 className="w-4 h-4 text-indigo-500" />
                                {zh ? "交通銜接設定" : "Transit Settings"}
                            </span>
                            <a
                                href={segment.googleMapsUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline font-medium"
                                onClick={() => haptic.tap()}
                            >
                                {zh ? "路線導航" : "Directions"}
                                <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                        </div>

                        {/* 交通工具切換網格 */}
                        <div className="space-y-1.5">
                            <Label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                                {zh ? "交通方式" : "Travel Mode"}
                            </Label>
                            <div className="grid grid-cols-4 gap-2">
                                {(['walking', 'transit', 'driving', 'bicycling'] as TravelMode[]).map((mode) => (
                                    <button
                                        key={mode}
                                        type="button"
                                        className={cn(
                                            "flex flex-col items-center justify-center py-2.5 rounded-xl border text-xs font-medium transition-all active:scale-95",
                                            selectedMode === mode
                                                ? "bg-indigo-50 dark:bg-indigo-950/60 border-indigo-300 dark:border-indigo-700 text-indigo-700 dark:text-indigo-300 shadow-2xs font-bold"
                                                : "bg-slate-50 dark:bg-slate-800/80 border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700"
                                        )}
                                        onClick={() => {
                                            haptic.tap()
                                            setSelectedMode(mode)
                                        }}
                                    >
                                        {MODE_ICONS[mode]}
                                        <span className="mt-1 capitalize">
                                            {mode === 'walking' ? (zh ? '步行' : 'Walk') :
                                                mode === 'transit' ? (zh ? '大眾' : 'Transit') :
                                                mode === 'driving' ? (zh ? '行車' : 'Drive') :
                                                (zh ? '單車' : 'Bike')}
                                        </span>
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* 手動覆寫時長與備註：採用非對稱佈局，將更多空間保留給文字提示框 */}
                        <div className="space-y-3">
                            <div className="grid grid-cols-[104px_1fr] sm:grid-cols-[112px_1fr] gap-2.5">
                                <div className="space-y-1">
                                    <Label className="text-xs font-semibold text-slate-600 dark:text-slate-300 flex items-center gap-1 truncate">
                                        <Clock className="w-3 h-3 text-slate-400 shrink-0" /> {zh ? "自訂時間" : "Time (m)"}
                                    </Label>
                                    <div className="relative">
                                        <Input
                                            type="number"
                                            min="1"
                                            max="999"
                                            placeholder={String(segment.estimatedMinutes)}
                                            value={customMinutes}
                                            onChange={(e) => setCustomMinutes(e.target.value)}
                                            className="h-10 text-[16px] sm:text-xs px-2.5 pr-6 rounded-xl bg-slate-50/80 dark:bg-slate-800/80"
                                        />
                                        <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-slate-400 pointer-events-none font-medium">
                                            {zh ? "分" : "m"}
                                        </span>
                                    </div>
                                </div>
                                <div className="space-y-1 min-w-0">
                                    <Label className="text-xs font-semibold text-slate-600 dark:text-slate-300 truncate block">
                                        {zh ? "備註班次 / 交通方式" : "Notes / Transit Line"}
                                    </Label>
                                    <Input
                                        type="text"
                                        maxLength={30}
                                        placeholder={zh ? TRANSIT_MODE_PLACEHOLDERS[selectedMode].zh : TRANSIT_MODE_PLACEHOLDERS[selectedMode].en}
                                        value={customNote}
                                        onChange={(e) => setCustomNote(e.target.value)}
                                        className="h-10 text-[16px] sm:text-xs px-3 rounded-xl bg-slate-50/80 dark:bg-slate-800/80 truncate placeholder:text-slate-400 dark:placeholder:text-slate-500 placeholder:truncate"
                                    />
                                </div>
                            </div>

                            {/* 全球快捷交通膠囊 */}
                            <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5">
                                <span className="text-[10px] text-slate-400 shrink-0 font-medium">
                                    {zh ? "快捷:" : "Quick:"}
                                </span>
                                {TRANSIT_QUICK_CHIPS[selectedMode].map((chip) => {
                                    const isFilled = customNote.includes(chip.value)
                                    return (
                                        <button
                                            key={chip.value}
                                            type="button"
                                            onClick={() => {
                                                haptic.tap()
                                                if (!customNote.trim()) {
                                                    setCustomNote(zh ? chip.value : chip.labelEn.replace(/^[^\w]+/, ''))
                                                } else if (!isFilled) {
                                                    const prefix = zh ? chip.value : chip.labelEn.replace(/^[^\w]+/, '')
                                                    setCustomNote(`${prefix} ${customNote}`.slice(0, 30))
                                                }
                                            }}
                                            className={cn(
                                                "shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium transition-all active:scale-95 border",
                                                isFilled
                                                    ? "bg-indigo-100 border-indigo-300 text-indigo-800 dark:bg-indigo-950/60 dark:border-indigo-700 dark:text-indigo-300 font-semibold"
                                                    : "bg-slate-50 hover:bg-slate-100 dark:bg-slate-800/60 dark:hover:bg-slate-700/60 border-slate-200/60 dark:border-slate-700/60 text-slate-600 dark:text-slate-300"
                                            )}
                                        >
                                            {zh ? chip.labelZh : chip.labelEn}
                                        </button>
                                    )
                                })}
                            </div>
                        </div>

                        {/* 儲存按鈕 */}
                        {onUpdateFromActivity && (
                            <Button
                                size="sm"
                                disabled={isSaving}
                                className="w-full h-10 text-xs sm:text-sm rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-bold shadow-xs active:scale-95 transition-all"
                                onClick={handleSaveOverride}
                            >
                                <Check className="w-4 h-4 mr-1.5" />
                                {zh ? "儲存交通設定" : "Save Settings"}
                            </Button>
                        )}
                    </div>
                </PopoverContent>
            </Popover>
        </div>
    )
}
