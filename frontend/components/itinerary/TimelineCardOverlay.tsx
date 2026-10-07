"use client"

/**
 * TimelineCardOverlay - 拖曳時的覆蓋層卡片
 * 
 * 用於 DragOverlay，在拖曳時顯示卡片副本
 * 這是簡化版，只需視覺呈現
 */

import { memo } from "react"
import {
    MapPin, Utensils, Train, ShoppingBag, Bed, Camera, StickyNote
} from "lucide-react"
import { cn } from "@/lib/utils"
import Image from "next/image"
import { Activity } from "@/lib/itinerary-types"

const iconMap: Record<string, React.ElementType> = {
    sightseeing: Camera,
    food: Utensils,
    transport: Train,
    shopping: ShoppingBag,
    accommodation: Bed,
    note: StickyNote,
    default: MapPin,
}

interface TimelineCardOverlayProps {
    activity: Activity
}

export const TimelineCardOverlay = memo(function TimelineCardOverlay({
    activity
}: TimelineCardOverlayProps) {
    const Icon = iconMap[activity.category || "default"] || iconMap.default
    const isHeader = activity.category === 'header' ||
        (activity.time || activity.time_slot || "00:00") === '00:00'

    return (
        <div
            className={cn(
                "bg-white dark:bg-slate-800 rounded-2xl border-2 border-indigo-500 dark:border-indigo-400 shadow-2xl",
                "p-4 w-full",
                "ring-4 ring-indigo-200/50 dark:ring-indigo-900/50",
                "cursor-grabbing select-none"
            )}
            style={{
                boxShadow: "0 20px 40px rgba(0,0,0,0.25)",
                transform: "scale(1.02)",
            }}
        >
            {/* 1. 頂部時序膠囊列 */}
            <div className="flex items-center justify-between gap-2 mb-2.5">
                <div className="flex items-center gap-1.5 min-w-0">
                    {isHeader ? (
                        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-700 text-xs font-bold shadow-2xs">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                            <span>INFO</span>
                        </div>
                    ) : (
                        <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-indigo-50 dark:bg-indigo-950/50 border border-indigo-200 dark:border-indigo-800 text-indigo-700 dark:text-indigo-300 shadow-2xs">
                            <span className="text-xs font-mono font-bold tracking-tight">
                                {activity.time || activity.time_slot || "00:00"}
                            </span>
                        </div>
                    )}

                    {!isHeader && (
                        <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300 flex items-center gap-1 font-medium">
                            <Icon className="w-3 h-3 text-indigo-500" />
                            <span>{activity.category || "activity"}</span>
                        </span>
                    )}
                </div>

                <span className="text-[10px] text-indigo-500 dark:text-indigo-400 font-medium">
                    📍 移動中
                </span>
            </div>

            {/* 2. 主內容與縮圖 */}
            <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                    <h3 className="font-bold text-slate-900 dark:text-white truncate text-base">
                        {activity.place || activity.place_name || "未命名"}
                    </h3>
                    {activity.desc && (
                        <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2 mt-1">
                            {activity.desc}
                        </p>
                    )}
                </div>

                {activity.image_url && (
                    <div className="w-14 h-14 rounded-xl overflow-hidden shrink-0 border border-slate-200 dark:border-slate-700">
                        <Image
                            src={activity.image_url}
                            alt=""
                            width={56}
                            height={56}
                            className="object-cover w-full h-full"
                            unoptimized
                        />
                    </div>
                )}
            </div>
        </div>
    )
})
