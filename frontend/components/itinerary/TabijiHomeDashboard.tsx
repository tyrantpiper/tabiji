"use client"

import React from "react"
import Image from "next/image"
import { 
    Calendar, 
    Compass, 
    Plus, 
    Users, 
    Trash2, 
    Download, 
    LogOut, 
    Loader2, 
    Hash
} from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { toast } from "sonner"
import { Trip, Activity } from "@/lib/itinerary-types"
import { generateTripPDF, downloadPDF, TripPDFData } from "@/lib/pdf-generator"
import { tripsApi } from "@/lib/api"
import { useLanguage } from "@/lib/LanguageContext"
import { useHaptic } from "@/lib/hooks"
import { ZenRenew } from "@/components/ui/zen-renew"

interface TabijiHomeDashboardProps {
    trips: Trip[]
    userId: string | null
    isTripsLoading: boolean
    onSelectTrip: (id: string) => void
    onDeleteTrip: (id: string) => void
    onLeaveTrip: (id: string) => void
    leavingTripId: string | null
    onRefresh: () => Promise<void>
    onOpenCreateModal: () => void
    onOpenJoinDialog: () => void
}

export function TabijiHomeDashboard({
    trips,
    userId,
    isTripsLoading,
    onSelectTrip,
    onDeleteTrip,
    onLeaveTrip,
    leavingTripId,
    onRefresh,
    onOpenCreateModal,
    onOpenJoinDialog,
}: TabijiHomeDashboardProps) {
    const { t } = useLanguage()
    const haptic = useHaptic()

    // 🔒 PDF Generation Handler (保持 100% 相同功能無降級)
    const handleDownloadPDF = async (trip: Trip) => {
        const toastId: string | number = toast.loading(t('trip_pdf_loading') || "正在匯出旅程手冊 PDF...")
        try {
            const fullTrip = await tripsApi.get(trip.id, userId || "")

            const pdfData: TripPDFData = {
                title: fullTrip.title || trip.title,
                startDate: new Date(fullTrip.start_date || trip.start_date).toLocaleDateString(),
                endDate: new Date(fullTrip.end_date || trip.end_date || trip.start_date).toLocaleDateString(),
                coverImage: fullTrip.cover_image,
                days: (fullTrip.days || []).map((d: { day: number; activities?: Activity[] }) => ({
                    day: d.day,
                    date: (() => {
                        const start = new Date(fullTrip.start_date || trip.start_date)
                        start.setDate(start.getDate() + d.day - 1)
                        return start.toLocaleDateString()
                    })(),
                    location: fullTrip.daily_locations?.[d.day]?.name,
                    activities: (d.activities || []).map((a: Activity) => ({
                        time: a.time || "00:00",
                        place: a.place || a.place_name || "",
                        desc: a.desc || a.notes || "",
                        category: a.category || "other",
                        memo: a.memo
                    })),
                    notes: fullTrip.day_notes?.[d.day] || []
                })),
                hotels: Array.isArray(fullTrip.hotel_info) 
                    ? fullTrip.hotel_info 
                    : (fullTrip.hotel_info && Object.keys(fullTrip.hotel_info).length > 0 
                        ? [fullTrip.hotel_info] 
                        : [])
            }

            const blobUrl = await generateTripPDF(pdfData, (current, total, stage) => {
                toast.loading(`${stage} (${current}/${total})`, { id: toastId })
            })
            toast.dismiss(toastId)
            downloadPDF(blobUrl, `${trip.title || "trip"}.pdf`)
            toast.success(t('trip_pdf_success') || "PDF 下載完成！")
        } catch (err) {
            console.error(err)
            toast.dismiss(toastId)
            toast.error(t('trip_pdf_failed') || "PDF 匯出失敗，請稍後再試")
        }
    }

    return (
        <div className="space-y-6 pb-24 select-none">
            {/* ── 1. Hero 簡約大標與重新整理 ───────────────────────────────────────── */}
            <header className="flex items-center justify-between pt-[calc(max(env(safe-area-inset-top,0px),0px)+3.5rem)] sm:pt-[calc(max(env(safe-area-inset-top,0px),0px)+2.5rem)]">
                <div className="space-y-1">
                    <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold tracking-widest text-[#E56E25] uppercase">
                            tabiji・旅路
                        </span>
                        <div className="w-1.5 h-1.5 rounded-full bg-[#E56E25] animate-pulse" />
                    </div>
                    <h1 className="text-2xl font-bold tracking-tight text-[#1E2927] dark:text-[#E5EBEA]">
                        Tabiji
                    </h1>
                    <p className="text-xs text-[#5C6B68] dark:text-[#A2B1AE] tracking-wide">
                        {t('manage_journeys')}
                    </p>
                </div>

                <div className="flex items-center gap-2.5">
                    <ZenRenew 
                        onRefresh={onRefresh} 
                        successMessage={t('update_success')} 
                        errorMessage={t('update_failed')} 
                    />
                </div>
            </header>

            {/* ── 2. 快捷行動膠囊 (Action Quick Pills) ─────────────────────────────── */}
            <div className="grid grid-cols-2 gap-3">
                <Button
                    type="button"
                    onClick={() => {
                        haptic.selection()
                        onOpenCreateModal()
                    }}
                    className="h-11 rounded-xl bg-[#0B3026] hover:bg-[#164E40] text-white dark:bg-[#164E40] dark:hover:bg-[#1F5F4F] shadow-xs flex items-center justify-center gap-2 text-xs font-medium cursor-pointer border-none outline-hidden"
                >
                    <Plus className="w-4 h-4 text-[#E56E25]" />
                    <span>{t('create_trip') || "規劃新旅程"}</span>
                </Button>

                <Button
                    type="button"
                    variant="outline"
                    onClick={() => {
                        haptic.selection()
                        onOpenJoinDialog()
                    }}
                    className="h-11 rounded-xl bg-white dark:bg-[#182320] text-[#1E2927] dark:text-[#E5EBEA] border-[#0B3026]/10 dark:border-white/10 hover:bg-[#EAE8DE]/50 dark:hover:bg-[#1F2C29] shadow-xs flex items-center justify-center gap-2 text-xs font-medium cursor-pointer outline-hidden"
                >
                    <Users className="w-4 h-4 text-[#0B3026] dark:text-[#A2B1AE]" />
                    <span>{t('join_trip') || "加入房間代碼"}</span>
                </Button>
            </div>

            {/* ── 3. 直觀上下滑動行程清單 (Vertical Trips List) ─────────────────────── */}
            <section className="space-y-3">
                <div className="flex items-center justify-between px-1">
                    <h2 className="text-xs font-semibold tracking-wider text-[#1E2927] dark:text-[#E5EBEA] uppercase">
                        {t('my_trips') || "我的旅程"} ({trips.length})
                    </h2>
                </div>

                {/* 骨架屏載入態 (Skeleton Loading State) */}
                {isTripsLoading && (
                    <div className="flex flex-col space-y-4">
                        {[1, 2, 3].map((i) => (
                            <div 
                                key={i} 
                                className="w-full h-44 rounded-2xl bg-[#EAE8DE]/60 dark:bg-[#182320] animate-pulse" 
                            />
                        ))}
                    </div>
                )}

                {/* 空狀態 (Empty State) */}
                {!isTripsLoading && trips.length === 0 && (
                    <div className="text-center py-12 bg-white dark:bg-[#182320] rounded-2xl border border-dashed border-[#0B3026]/15 dark:border-white/10 p-6 space-y-3">
                        <div className="w-12 h-12 mx-auto rounded-full bg-[#EAE8DE]/50 dark:bg-[#1F2C29] flex items-center justify-center text-[#E56E25]">
                            <Compass className="w-6 h-6" />
                        </div>
                        <div>
                            <p className="text-sm font-medium text-[#1E2927] dark:text-[#E5EBEA]">{t('trip_no_trips') || "尚無任何旅程"}</p>
                            <p className="text-xs text-[#5C6B68] dark:text-[#A2B1AE] mt-1">{t('trip_create_hint') || "點擊上方按鈕，開啟你的第一個 tabiji 旅行計畫"}</p>
                        </div>
                    </div>
                )}

                {/* 📜 縱向卡片清單 (Vertical Trips Cards) */}
                {!isTripsLoading && trips.length > 0 && (
                    <div className="flex flex-col space-y-4">
                        {trips.map((trip: Trip, index: number) => (
                            <Card 
                                key={trip.id} 
                                className="p-0 overflow-hidden border border-[#0B3026]/8 dark:border-white/10 shadow-xs hover:shadow-md transition-all rounded-2xl bg-white dark:bg-[#182320] relative group flex flex-col justify-between"
                            >
                                {/* 刪除按鈕 (僅本人行程可見) */}
                                <div className="absolute top-2.5 right-2.5 z-20">
                                    {userId && trip.created_by === userId && (
                                        <Button
                                            variant="destructive"
                                            size="icon"
                                            className="w-7 h-7 rounded-full shadow-md bg-red-500/90 hover:bg-red-600 border border-white/20 transition-all active:scale-90"
                                            onClick={(e) => { 
                                                e.stopPropagation(); 
                                                onDeleteTrip(trip.id) 
                                            }}
                                        >
                                            <Trash2 className="w-3.5 h-3.5 text-white" />
                                        </Button>
                                    )}
                                </div>

                                {/* 頂部封面與資訊 (可點擊進入行程) */}
                                <button 
                                    type="button" 
                                    className="w-full text-left cursor-pointer transition-all duration-200 active:scale-[0.99] block p-0 border-none bg-transparent outline-hidden" 
                                    onClick={() => {
                                        haptic.selection()
                                        onSelectTrip(trip.id)
                                    }}
                                >
                                    <div className="h-36 sm:h-44 bg-[#121A18] relative rounded-t-2xl overflow-hidden">
                                        {trip.cover_image ? (
                                            <div className="relative w-full h-full">
                                                <Image 
                                                    src={trip.cover_image} 
                                                    alt="cover" 
                                                    fill 
                                                    className="object-cover opacity-85 group-hover:scale-105 transition-transform duration-500" 
                                                    unoptimized 
                                                    priority={index === 0}
                                                />
                                            </div>
                                        ) : (
                                            <div className="absolute inset-0 bg-linear-to-br from-[#0B3026] to-[#121A18]" />
                                        )}

                                        {/* 漸變層遮罩 */}
                                        <div className="absolute inset-0 bg-linear-to-t from-black/75 via-black/25 to-transparent" />

                                        {/* 標籤徽章 */}
                                        {trip.is_sample ? (
                                            <div className="absolute top-3 left-3 bg-[#E56E25] px-2.5 py-0.5 rounded-full text-[10px] text-white font-semibold flex items-center gap-1 shadow-xs">
                                                {t('sample_trip_badge') || "示範旅程"}
                                            </div>
                                        ) : (
                                            <div className="absolute top-3 left-3 bg-black/50 backdrop-blur-xs px-2 py-0.5 rounded-full text-[10px] text-white/90 font-mono flex items-center gap-1">
                                                <Hash className="w-2.5 h-2.5 text-[#E56E25]" /> {trip.share_code || "PRIVATE"}
                                            </div>
                                        )}

                                        {/* 行程名稱與日期 */}
                                        <div className="absolute bottom-3.5 left-4 right-4 text-white">
                                            <h3 className="font-bold text-base sm:text-lg truncate drop-shadow-xs">{trip.title}</h3>
                                            <p className="text-[11px] sm:text-xs opacity-80 flex items-center gap-1.5 mt-0.5">
                                                <Calendar className="w-3 h-3 text-[#E56E25]" />
                                                {new Date(trip.start_date || new Date().toISOString()).toLocaleDateString()}
                                            </p>
                                        </div>
                                    </div>
                                </button>

                                {/* 底部功能欄 (PDF 匯出、作者標籤、退出旅程) */}
                                <div className="px-4 py-2.5 bg-white dark:bg-[#182320] flex justify-between items-center rounded-b-2xl border-t border-[#0B3026]/5 dark:border-white/5">
                                    <button
                                        type="button"
                                        className="text-[11px] text-[#5C6B68] dark:text-[#A2B1AE] bg-[#EAE8DE]/60 dark:bg-[#1F2C29] px-2.5 py-0.5 rounded-full transition-colors cursor-pointer border-none outline-hidden"
                                        onClick={() => {
                                            haptic.selection()
                                            onSelectTrip(trip.id)
                                        }}
                                    >
                                        By {trip.is_sample ? 'Tabiji' : (trip.creator_name || 'Explorer')}
                                    </button>

                                    <div className="flex items-center gap-2">
                                        {trip.is_sample ? (
                                            <span className="text-[11px] text-[#E56E25] font-medium px-2 h-7 flex items-center">
                                                {t('sample_trip_explore') || "探索靈感"}
                                            </span>
                                        ) : (
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                className="text-xs text-[#0B3026] dark:text-[#E5EBEA] hover:bg-[#EAE8DE]/50 dark:hover:bg-[#1F2C29] gap-1 px-2.5 h-7 rounded-lg"
                                                onClick={(e) => { 
                                                    e.stopPropagation(); 
                                                    handleDownloadPDF(trip) 
                                                }}
                                            >
                                                <Download className="w-3.5 h-3.5 text-[#E56E25]" /> PDF
                                            </Button>
                                        )}

                                        {userId && trip.created_by !== userId && (
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                className="text-xs text-rose-500 hover:text-rose-700 hover:bg-rose-50 dark:hover:bg-[#1F2C29] gap-1 px-2.5 h-7 rounded-lg"
                                                disabled={leavingTripId === trip.id}
                                                onClick={(e) => { 
                                                    e.stopPropagation(); 
                                                    onLeaveTrip(trip.id) 
                                                }}
                                            >
                                                {leavingTripId === trip.id ? (
                                                    <Loader2 className="w-3 h-3 animate-spin" />
                                                ) : (
                                                    <LogOut className="w-3.5 h-3.5" />
                                                )} 
                                                {t('trip_leave') || "退出"}
                                            </Button>
                                        )}
                                    </div>
                                </div>
                            </Card>
                        ))}
                    </div>
                )}
            </section>
        </div>
    )
}
