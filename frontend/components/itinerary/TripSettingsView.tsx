"use client"

import { useState, useRef } from "react"
import Image from "next/image"
import { 
    ChevronLeft, 
    Camera, 
    Eye, 
    RotateCcw, 
    Trash2, 
    Edit3, 
    Calendar, 
    Key, 
    Copy, 
    Check, 
    AlertTriangle, 
    Loader2, 
    Sparkles, 
    ChevronRight,
    LogOut
} from "lucide-react"
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { VisuallyHidden } from "@radix-ui/react-visually-hidden"
import { ZoomableImage } from "@/components/ui/zoomable-image"
import { useLanguage } from "@/lib/LanguageContext"
import { useHaptic } from "@/lib/hooks"
import { compressImage } from "@/lib/image-utils"
import { tripsApi } from "@/lib/api"
import { resolveDestinationCover } from "@/lib/destination-covers"
import { type Trip } from "@/lib/itinerary-types"
import { toast } from "sonner"

interface TripSettingsViewProps {
    trip?: Trip
    currentTrip?: Trip
    userId?: string | null
    totalDays?: number
    onBack: () => void
    onUpdate?: () => Promise<void>
    onTripUpdated?: () => Promise<void>
    onOpenDatePicker?: () => void
    onDeleteDay?: (dayNum: number) => Promise<void> | void
    onDeleteOrLeave?: () => void
    onTripDeleted?: () => void
}

export function TripSettingsView({
    trip: tripProp,
    currentTrip: currentTripProp,
    userId,
    totalDays: totalDaysProp,
    onBack,
    onUpdate,
    onTripUpdated,
    onOpenDatePicker,
    onDeleteDay,
    onDeleteOrLeave,
    onTripDeleted
}: TripSettingsViewProps) {
    const trip = currentTripProp || tripProp
    const handleUpdate = onTripUpdated || onUpdate || (async () => {})
    const handleDeleteOrLeave = onTripDeleted || onDeleteOrLeave || (() => {})

    const { lang } = useLanguage()
    const zh = lang === "zh"
    const haptic = useHaptic()

    const [loading, setLoading] = useState(false)
    const [previewOpen, setPreviewOpen] = useState(false)
    const fileInputRef = useRef<HTMLInputElement>(null)

    // ✏️ 標題修改對話框狀態
    const [editTitleOpen, setEditTitleOpen] = useState(false)
    const [titleInput, setTitleInput] = useState(trip?.title || "")
    const [isSavingTitle, setIsSavingTitle] = useState(false)

    // 🔑 房間代碼複製反饋
    const [copiedCode, setCopiedCode] = useState(false)

    // 🚨 刪除/退出對話框狀態
    const [dangerDialogOpen, setDangerDialogOpen] = useState(false)
    const [isDangerActionLoading, setIsDangerActionLoading] = useState(false)

    // 🗓️ 天數管理狀態
    const [deletingDayNum, setDeletingDayNum] = useState<number | null>(null)
    const [isDeletingDay, setIsDeletingDay] = useState(false)

    // 計算實際天數
    const calculatedTotalDays = totalDaysProp || (() => {
        if (!trip?.start_date) return 1
        const startStr = trip.start_date.split('T')[0]
        const endStr = trip.end_date ? trip.end_date.split('T')[0] : startStr
        const [sy, sm, sd] = startStr.split('-').map(Number)
        const [ey, em, ed] = endStr.split('-').map(Number)
        const d = Math.max(1, Math.round((new Date(ey, em - 1, ed).getTime() - new Date(sy, sm - 1, sd).getTime()) / (1000 * 60 * 60 * 24)) + 1)
        const maxDayFromItems = (Array.isArray(trip?.days) && trip.days.length > 0)
            ? Math.max(...trip.days.map((x) => x.day || 1))
            : 1
        return Math.max(d, maxDayFromItems)
    })()

    const dayNumbers = Array.from({ length: calculatedTotalDays }, (_, i) => i + 1)

    const getDayInfo = (dayNum: number) => {
        if (trip?.start_date) {
            const [y, m, d] = trip.start_date.split('T')[0].split('-').map(Number)
            const dt = new Date(y, m - 1, d + (dayNum - 1))
            const weekNames = zh 
                ? ["週日", "週一", "週二", "週三", "週四", "週五", "週六"]
                : ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
            return `${dt.getMonth() + 1}/${dt.getDate()} (${weekNames[dt.getDay()]})`
        }
        return `Day ${dayNum}`
    }

    const getDayActivityCount = (dayNum: number) => {
        if (!trip?.days || !Array.isArray(trip.days)) return 0
        const found = trip.days.find(d => d.day === dayNum)
        return found?.activities?.length || 0
    }

    const handleConfirmDeleteDay = async () => {
        if (!deletingDayNum || !onDeleteDay) return
        setIsDeletingDay(true)
        haptic.tap()
        try {
            await onDeleteDay(deletingDayNum)
            await handleUpdate()
            toast.success(zh ? `已成功刪除第 ${deletingDayNum} 天` : `Day ${deletingDayNum} deleted successfully`)
            setDeletingDayNum(null)
        } catch {
            toast.error(zh ? "刪除天數失敗" : "Failed to delete day")
        } finally {
            setIsDeletingDay(false)
        }
    }

    if (!trip) return null

    const isOwner = Boolean(trip.created_by && userId && trip.created_by === userId)
    const displayCover = trip.cover_image || resolveDestinationCover(trip.title)
    const hasCustomCover = Boolean(trip.cover_image)

    // 📸 處理自訂圖片上傳 (Cloudinary)
    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file) return
        e.target.value = ""

        setLoading(true)
        haptic.tap()
        const folder = "ryan_travel/covers"

        try {
            const compressedFile = await compressImage(file, {
                maxWidth: 4096,
                maxHeight: 4096,
                quality: 0.85
            })

            const cloudName = process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME
            const apiKey = process.env.NEXT_PUBLIC_CLOUDINARY_API_KEY

            if (!cloudName || !apiKey) {
                toast.error(zh ? "系統設定不完整，無法上傳圖片" : "Upload service not properly configured")
                setLoading(false)
                return
            }

            const timestamp = Math.round(Date.now() / 1000)
            const paramsToSign = { timestamp, folder }

            const signRes = await fetch("/api/sign-cloudinary", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ paramsToSign }),
            })

            if (!signRes.ok) {
                toast.error(zh ? "簽名授權失敗" : "Failed to obtain upload signature")
                setLoading(false)
                return
            }

            const { signature } = await signRes.json()

            const url = `https://api.cloudinary.com/v1_1/${cloudName}/image/upload`
            const data = new FormData()
            data.append("file", compressedFile, file.name)
            data.append("timestamp", timestamp.toString())
            data.append("folder", folder)
            data.append("signature", signature)
            data.append("api_key", apiKey)

            const uploadRes = await fetch(url, {
                method: "POST",
                body: data,
            })

            if (!uploadRes.ok) {
                toast.error(zh ? "圖片上傳失敗，請稍後再試" : "Failed to upload image, please try again")
                setLoading(false)
                return
            }

            const result = await uploadRes.json()
            if (!result.secure_url) {
                toast.error(zh ? "未取得有效圖片連結" : "Invalid image URL received")
                setLoading(false)
                return
            }

            await tripsApi.updateCover(trip.id, result.secure_url, userId || undefined)
            haptic.success()
            toast.success(zh ? "封面已更新！" : "Cover photo updated!")
            await handleUpdate()
        } catch (error) {
            console.error("[TripSettingsView] Upload error:", error)
            haptic.error()
            toast.error(zh ? "上傳過程發生錯誤" : "Error uploading cover photo")
        } finally {
            setLoading(false)
        }
    }

    // 🔄 恢復為城市預設封面
    const handleResetToDefault = async () => {
        haptic.selection()
        setLoading(true)
        try {
            const defaultCover = resolveDestinationCover(trip.title)
            await tripsApi.updateCover(trip.id, defaultCover, userId || undefined)
            haptic.success()
            toast.success(zh ? "已恢復為預設城市封面" : "Reset to default city cover")
            await handleUpdate()
        } catch (error) {
            console.error("[TripSettingsView] Reset error:", error)
            haptic.error()
            toast.error(zh ? "恢復預設失敗" : "Failed to reset cover")
        } finally {
            setLoading(false)
        }
    }

    // 🗑️ 移除封面照
    const handleRemoveCover = async () => {
        haptic.selection()
        setLoading(true)
        try {
            await tripsApi.updateCover(trip.id, null, userId || undefined)
            haptic.success()
            toast.success(zh ? "已移除自訂封面" : "Cover photo removed")
            await handleUpdate()
        } catch (error) {
            console.error("[TripSettingsView] Remove error:", error)
            haptic.error()
            toast.error(zh ? "移除封面失敗" : "Failed to remove cover")
        } finally {
            setLoading(false)
        }
    }

    // ✏️ 儲存標題變更
    const handleSaveTitle = async () => {
        const cleanTitle = titleInput.trim()
        if (!cleanTitle) {
            haptic.error()
            toast.warning(zh ? "行程名稱不可為空" : "Trip title cannot be empty")
            return
        }

        setIsSavingTitle(true)
        try {
            await tripsApi.updateTitle(trip.id, cleanTitle, userId || undefined)
            haptic.success()
            toast.success(zh ? "行程名稱已更新！" : "Trip title updated!")
            setEditTitleOpen(false)
            await handleUpdate()
        } catch (error) {
            console.error("[TripSettingsView] Title update error:", error)
            haptic.error()
            toast.error(zh ? "更新行程名稱失敗" : "Failed to update trip title")
        } finally {
            setIsSavingTitle(false)
        }
    }

    // 🔑 複製房間代碼
    const handleCopyShareCode = async () => {
        if (!trip.share_code) return
        haptic.tap()
        try {
            await navigator.clipboard.writeText(trip.share_code)
            setCopiedCode(true)
            toast.success(zh ? "已複製房間代碼！" : "Room code copied!")
            setTimeout(() => setCopiedCode(false), 2000)
        } catch {
            toast.error(zh ? "無法複製" : "Failed to copy")
        }
    }

    // 🚨 執行退出或刪除行程
    const handleConfirmDangerAction = async () => {
        if (!userId) {
            toast.error(zh ? "找不到使用者身分" : "User identity not found")
            return
        }

        setIsDangerActionLoading(true)
        haptic.selection()

        try {
            if (isOwner) {
                // 行程創立者 ➔ 刪除整趟行程
                await tripsApi.delete(trip.id, userId)
                haptic.success()
                toast.success(zh ? "行程已刪除" : "Trip deleted successfully")
            } else {
                // 行程協作成員 ➔ 退出行程
                await tripsApi.leave(trip.id, userId)
                haptic.success()
                toast.success(zh ? "已退出此行程" : "Left trip successfully")
            }
            setDangerDialogOpen(false)
            handleDeleteOrLeave()
        } catch (error) {
            console.error("[TripSettingsView] Danger action error:", error)
            haptic.error()
            toast.error(error instanceof Error ? error.message : (zh ? "操作失敗" : "Action failed"))
        } finally {
            setIsDangerActionLoading(false)
        }
    }

    // 計算天數與晚數
    const dateRangeText = (() => {
        if (!trip.start_date) return zh ? "未設定日期" : "No date set"
        const start = trip.start_date.split("T")[0]
        const end = trip.end_date ? trip.end_date.split("T")[0] : start
        return `${start} ~ ${end}`
    })()

    return (
        <div className="w-full min-h-full pb-32 bg-[#F6F5EE] dark:bg-[#121A18] text-[#1E2927] dark:text-[#E5EBEA]">
            <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={handleFileChange}
                disabled={loading}
            />

            <div className="w-full max-w-4xl lg:max-w-5xl mx-auto px-5 sm:px-8 pt-14 sm:pt-12">
                {/* 1. iOS Top Navigation Bar */}
                <div className="flex items-center justify-between mb-6">
                    <button
                        type="button"
                        onClick={() => {
                            haptic.selection()
                            onBack()
                        }}
                        className="w-10 h-10 -ml-1 rounded-full flex items-center justify-center bg-white/80 dark:bg-[#1E2927]/80 border border-[#0B3026]/10 dark:border-white/10 text-[#1E2927] dark:text-[#E5EBEA] hover:bg-black/5 dark:hover:bg-white/5 active:scale-90 transition-all shadow-2xs cursor-pointer select-none"
                        aria-label="Back"
                    >
                        <ChevronLeft className="w-5 h-5 -ml-0.5" />
                    </button>
                    <h1 className="text-base font-bold text-[#1E2927] dark:text-[#E5EBEA]">
                        {zh ? "行程設定" : "Trip Settings"}
                    </h1>
                    <div className="w-10" />
                </div>

                {/* 2. Group 1: 封面照片管理 (Cover Management) */}
                <div className="mb-6">
                    <div className="px-1 mb-2 text-xs font-bold text-[#0B3026]/60 dark:text-[#88A29A] uppercase tracking-wider">
                        {zh ? "封面照片" : "Cover Photo"}
                    </div>
                    <div className="bg-white/80 dark:bg-[#1E2927]/80 backdrop-blur-md rounded-2xl overflow-hidden shadow-xs border border-[#0B3026]/10 dark:border-white/10">
                        {/* 16:9 封面預覽大圖卡片 */}
                        <div className="relative w-full h-44 sm:h-52 bg-stone-200 dark:bg-slate-800 overflow-hidden">
                            <Image
                                src={displayCover}
                                alt={trip.title}
                                fill
                                className="object-cover"
                                sizes="(max-width: 768px) 100vw, 800px"
                                priority
                            />
                            <div className="absolute inset-0 bg-linear-to-t from-black/70 via-black/20 to-transparent flex items-end justify-between p-4">
                                <div className="space-y-0.5">
                                    <span className="text-[11px] font-bold text-white/90 flex items-center gap-1.5 drop-shadow-xs">
                                        <Sparkles className="w-3.5 h-3.5 text-amber-300" />
                                        <span>{hasCustomCover ? (zh ? "自訂上傳封面" : "Custom Cover") : (zh ? "自動匹配城市預設" : "Auto City Cover")}</span>
                                    </span>
                                    <p className="text-sm font-bold text-white drop-shadow-sm truncate max-w-xs sm:max-w-md">
                                        {trip.title}
                                    </p>
                                </div>

                                {displayCover && (
                                    <button
                                        type="button"
                                        onClick={() => {
                                            haptic.selection()
                                            setPreviewOpen(true)
                                        }}
                                        className="px-3 py-1.5 rounded-full bg-black/40 hover:bg-black/60 backdrop-blur-md border border-white/20 text-white text-xs font-semibold flex items-center gap-1.5 transition-all active:scale-95 cursor-pointer select-none"
                                    >
                                        <Eye className="w-3.5 h-3.5" />
                                        <span>{zh ? "檢視大圖" : "View"}</span>
                                    </button>
                                )}
                            </div>
                        </div>

                        {/* 封面操作項目清單 */}
                        <div className="divide-y divide-[#0B3026]/5 dark:divide-white/5">
                            {/* 上傳更換封面 */}
                            <button
                                type="button"
                                onClick={() => {
                                    haptic.selection()
                                    fileInputRef.current?.click()
                                }}
                                disabled={loading}
                                className="w-full flex items-center justify-between p-4 text-left hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer border-none bg-transparent outline-hidden disabled:opacity-50"
                            >
                                <div className="flex items-center gap-3">
                                    <Camera className="w-4 h-4 text-emerald-500" />
                                    <div>
                                        <div className="text-sm font-medium text-[#1E2927] dark:text-[#E5EBEA]">
                                            {zh ? "上傳新封面照" : "Upload New Cover"}
                                        </div>
                                        <div className="text-xs text-[#0B3026]/50 dark:text-[#88A29A]/60">
                                            {zh ? "支援 JPG、PNG，自動最佳化畫質" : "Supports JPG, PNG; automatically optimized"}
                                        </div>
                                    </div>
                                </div>
                                {loading ? (
                                    <Loader2 className="w-4 h-4 animate-spin text-emerald-500" />
                                ) : (
                                    <ChevronRight className="w-4 h-4 text-[#0B3026]/40 dark:text-[#88A29A]/50" />
                                )}
                            </button>

                            {/* 恢復預設城市封面 */}
                            <button
                                type="button"
                                onClick={handleResetToDefault}
                                disabled={loading}
                                className="w-full flex items-center justify-between p-4 text-left hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer border-none bg-transparent outline-hidden disabled:opacity-50"
                            >
                                <div className="flex items-center gap-3">
                                    <RotateCcw className="w-4 h-4 text-amber-500" />
                                    <div>
                                        <div className="text-sm font-medium text-[#1E2927] dark:text-[#E5EBEA]">
                                            {zh ? "恢復預設城市封面" : "Reset to City Cover"}
                                        </div>
                                        <div className="text-xs text-[#0B3026]/50 dark:text-[#88A29A]/60">
                                            {zh ? "依行程目的地自動匹配精美封面" : "Auto-matches curated destination cover"}
                                        </div>
                                    </div>
                                </div>
                                <ChevronRight className="w-4 h-4 text-[#0B3026]/40 dark:text-[#88A29A]/50" />
                            </button>

                            {/* 移除封面照 (僅在有自訂封面時顯示) */}
                            {hasCustomCover && (
                                <button
                                    type="button"
                                    onClick={handleRemoveCover}
                                    disabled={loading}
                                    className="w-full flex items-center justify-between p-4 text-left hover:bg-rose-500/10 transition-colors text-rose-600 dark:text-rose-400 cursor-pointer border-none bg-transparent outline-hidden disabled:opacity-50"
                                >
                                    <div className="flex items-center gap-3">
                                        <Trash2 className="w-4 h-4 text-rose-500" />
                                        <span className="text-sm font-medium">
                                            {zh ? "移除自訂封面" : "Remove Custom Cover"}
                                        </span>
                                    </div>
                                    <ChevronRight className="w-4 h-4 text-rose-400/50" />
                                </button>
                            )}
                        </div>
                    </div>
                </div>

                {/* 3. Group 2: 行程基本資訊 (Trip Basics) */}
                <div className="mb-6">
                    <div className="px-1 mb-2 text-xs font-bold text-[#0B3026]/60 dark:text-[#88A29A] uppercase tracking-wider">
                        {zh ? "行程資訊與偏好" : "Trip Information"}
                    </div>
                    <div className="bg-white/80 dark:bg-[#1E2927]/80 backdrop-blur-md rounded-2xl overflow-hidden shadow-xs border border-[#0B3026]/10 dark:border-white/10 divide-y divide-[#0B3026]/5 dark:divide-white/5">
                        {/* 編輯名稱 */}
                        <button
                            type="button"
                            onClick={() => {
                                haptic.selection()
                                setTitleInput(trip.title)
                                setEditTitleOpen(true)
                            }}
                            className="w-full flex items-center justify-between p-4 text-left hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer border-none bg-transparent outline-hidden"
                        >
                            <div className="flex items-center gap-3">
                                <Edit3 className="w-4 h-4 text-indigo-500" />
                                <div>
                                    <div className="text-sm font-medium text-[#1E2927] dark:text-[#E5EBEA]">
                                        {zh ? "行程名稱" : "Trip Title"}
                                    </div>
                                    <div className="text-xs text-[#0B3026]/60 dark:text-[#88A29A] truncate max-w-xs sm:max-w-md">
                                        {trip.title}
                                    </div>
                                </div>
                            </div>
                            <ChevronRight className="w-4 h-4 text-[#0B3026]/40 dark:text-[#88A29A]/50" />
                        </button>

                        {/* 調整日期 */}
                        <button
                            type="button"
                            onClick={() => {
                                haptic.selection()
                                onOpenDatePicker?.()
                            }}
                            className="w-full flex items-center justify-between p-4 text-left hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer border-none bg-transparent outline-hidden"
                        >
                            <div className="flex items-center gap-3">
                                <Calendar className="w-4 h-4 text-[#1E2927] dark:text-[#E5EBEA]" />
                                <div>
                                    <div className="text-sm font-medium text-[#1E2927] dark:text-[#E5EBEA]">
                                        {zh ? "旅行日期區間" : "Trip Date Range"}
                                    </div>
                                    <div className="text-xs text-[#0B3026]/60 dark:text-[#88A29A]">
                                        {dateRangeText}
                                    </div>
                                </div>
                            </div>
                            <ChevronRight className="w-4 h-4 text-[#0B3026]/40 dark:text-[#88A29A]/50" />
                        </button>

                        {/* 房間代碼複製 */}
                        {trip.share_code && (
                            <button
                                type="button"
                                onClick={handleCopyShareCode}
                                className="w-full flex items-center justify-between p-4 text-left hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer border-none bg-transparent outline-hidden"
                            >
                                <div className="flex items-center gap-3">
                                    <Key className="w-4 h-4 text-amber-500" />
                                    <div>
                                        <div className="text-sm font-medium text-[#1E2927] dark:text-[#E5EBEA]">
                                            {zh ? "房間分享代碼" : "Share Room Code"}
                                        </div>
                                        <div className="text-xs font-mono font-bold text-amber-600 dark:text-amber-400 tracking-wider">
                                            {trip.share_code}
                                        </div>
                                    </div>
                                </div>
                                <div className="flex items-center gap-1.5 text-xs font-semibold text-[#0B3026]/60 dark:text-[#88A29A]">
                                    {copiedCode ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                                    <span>{copiedCode ? (zh ? "已複製" : "Copied") : (zh ? "點擊複製" : "Copy")}</span>
                                </div>
                            </button>
                        )}
                    </div>
                </div>

                {/* 3. Group: 天數結構與日程管理 (Day Structure Management) */}
                <div className="mb-6">
                    <div className="flex items-center justify-between px-1 mb-2">
                        <div className="text-xs font-bold text-[#0B3026]/60 dark:text-[#88A29A] uppercase tracking-wider">
                            {zh ? "天數結構管理" : "Day Structure Management"}
                        </div>
                        <div className="text-xs text-[#0B3026]/50 dark:text-[#88A29A]/60 font-medium">
                            {zh ? `共 ${calculatedTotalDays} 天` : `${calculatedTotalDays} Days Total`}
                        </div>
                    </div>
                    <div className="bg-white/80 dark:bg-[#1E2927]/80 backdrop-blur-md rounded-2xl overflow-hidden shadow-xs border border-[#0B3026]/10 dark:border-white/10 divide-y divide-[#0B3026]/5 dark:divide-white/5">
                        {dayNumbers.map((d) => {
                            const dateLabel = getDayInfo(d)
                            const actCount = getDayActivityCount(d)
                            return (
                                <div
                                    key={d}
                                    className="flex items-center justify-between p-4 hover:bg-black/2 dark:hover:bg-white/2 transition-colors"
                                >
                                    <div className="flex items-center gap-3">
                                        <div className="w-8 h-8 rounded-full bg-emerald-500/10 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 font-bold text-xs flex items-center justify-center select-none">
                                            D{d}
                                        </div>
                                        <div>
                                            <div className="text-sm font-semibold text-[#1E2927] dark:text-[#E5EBEA]">
                                                {zh ? `第 ${d} 天` : `Day ${d}`} · <span className="text-xs font-normal opacity-80">{dateLabel}</span>
                                            </div>
                                            <div className="text-xs text-[#0B3026]/50 dark:text-[#88A29A]/60">
                                                {actCount > 0 
                                                    ? (zh ? `${actCount} 個景點活動` : `${actCount} activities`)
                                                    : (zh ? "尚無安排活動 (空白日)" : "No activities")}
                                            </div>
                                        </div>
                                    </div>

                                    {onDeleteDay && (
                                        <button
                                            type="button"
                                            disabled={calculatedTotalDays <= 1 || isDeletingDay}
                                            onClick={() => {
                                                haptic.selection()
                                                setDeletingDayNum(d)
                                            }}
                                            className="px-2.5 py-1 text-xs font-medium rounded-lg text-rose-500 hover:bg-rose-500/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all flex items-center gap-1 cursor-pointer border-none bg-transparent"
                                            title={calculatedTotalDays <= 1 ? (zh ? "單日行程無法刪除" : "Cannot delete single day") : (zh ? `刪除第 ${d} 天` : `Delete Day ${d}`)}
                                        >
                                            <Trash2 className="w-3.5 h-3.5" />
                                            <span className="hidden sm:inline">{zh ? "刪除此天" : "Delete"}</span>
                                        </button>
                                    )}
                                </div>
                            )
                        })}
                    </div>
                </div>

                {/* 4. Group 4: 危險操作區 (Danger Zone) */}
                <div className="mb-6">
                    <div className="px-1 mb-2 text-xs font-bold text-rose-500 uppercase tracking-wider">
                        {zh ? "危險操作" : "Danger Zone"}
                    </div>
                    <div className="bg-white/80 dark:bg-[#1E2927]/80 backdrop-blur-md rounded-2xl overflow-hidden shadow-xs border border-rose-500/20">
                        <button
                            type="button"
                            onClick={() => {
                                haptic.error()
                                setDangerDialogOpen(true)
                            }}
                            className="w-full flex items-center justify-between p-4 text-left hover:bg-rose-500/10 transition-colors text-rose-600 dark:text-rose-400 cursor-pointer border-none bg-transparent outline-hidden"
                        >
                            <div className="flex items-center gap-3">
                                {isOwner ? (
                                    <AlertTriangle className="w-4 h-4 text-rose-500" />
                                ) : (
                                    <LogOut className="w-4 h-4 text-rose-500" />
                                )}
                                <div>
                                    <div className="text-sm font-medium">
                                        {isOwner ? (zh ? "刪除整趟行程" : "Delete Itinerary") : (zh ? "退出此行程" : "Leave Itinerary")}
                                    </div>
                                    <div className="text-xs text-rose-500/70">
                                        {isOwner ? (zh ? "此操作不可逆，將清空所有天數與細項" : "Irreversible; removes all itinerary items") : (zh ? "退出後將無法繼續檢視與協同編輯" : "You will lose access to this trip")}
                                    </div>
                                </div>
                            </div>
                            <ChevronRight className="w-4 h-4 text-rose-400/50" />
                        </button>
                    </div>
                </div>
            </div>

            {/* 放大預覽對話框 */}
            {displayCover && (
                <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
                    <DialogContent className="max-w-4xl p-0 bg-transparent border-none shadow-none text-white flex items-center justify-center">
                        <VisuallyHidden>
                            <DialogTitle>{trip.title} 封面大圖</DialogTitle>
                        </VisuallyHidden>
                        <div className="relative max-h-[85vh] max-w-[90vw] overflow-hidden rounded-2xl bg-black/80">
                            <ZoomableImage
                                src={displayCover}
                                alt={trip.title}
                                className="w-full h-auto max-h-[85vh] object-contain rounded-2xl"
                            />
                        </div>
                    </DialogContent>
                </Dialog>
            )}

            {/* ✏️ 編輯標題對話框 */}
            <Dialog open={editTitleOpen} onOpenChange={setEditTitleOpen}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle>{zh ? "編輯行程名稱" : "Edit Trip Title"}</DialogTitle>
                        <DialogDescription>
                            {zh ? "修改此行程的顯示名稱，將同步更新給所有協作成員。" : "Update the display name of this itinerary for all collaborators."}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="py-2 space-y-2">
                        <Label htmlFor="trip-title-input">{zh ? "行程名稱" : "Title"}</Label>
                        <Input
                            id="trip-title-input"
                            value={titleInput}
                            onChange={(e) => setTitleInput(e.target.value)}
                            placeholder={zh ? "例如：2026 東京春季自由行" : "e.g. 2026 Tokyo Spring Trip"}
                            maxLength={80}
                            autoFocus
                        />
                    </div>
                    <DialogFooter>
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => setEditTitleOpen(false)}
                            disabled={isSavingTitle}
                        >
                            {zh ? "取消" : "Cancel"}
                        </Button>
                        <Button
                            type="button"
                            onClick={handleSaveTitle}
                            disabled={isSavingTitle || !titleInput.trim()}
                            className="bg-indigo-600 hover:bg-indigo-700 text-white font-bold"
                        >
                            {isSavingTitle ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : null}
                            {zh ? "儲存變更" : "Save Changes"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* 🚨 刪除 / 退出行程確認對話框 */}
            <Dialog open={dangerDialogOpen} onOpenChange={setDangerDialogOpen}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 text-rose-600">
                            <AlertTriangle className="w-5 h-5" />
                            {isOwner ? (zh ? "確定要刪除行程？" : "Delete this trip?") : (zh ? "確定要退出行程？" : "Leave this trip?")}
                        </DialogTitle>
                        <DialogDescription>
                            {isOwner
                                ? (zh ? `您即將刪除「${trip.title}」。此操作將永久清除所有景點細項、記帳與照片，且無法復原。` : `You are about to permanently delete "${trip.title}". This cannot be undone.`)
                                : (zh ? `您即將退出「${trip.title}」。退出後若要重新加入，需輸入房間代碼。` : `You are about to leave "${trip.title}". You will need the room code to rejoin.`)}
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => setDangerDialogOpen(false)}
                            disabled={isDangerActionLoading}
                        >
                            {zh ? "取消" : "Cancel"}
                        </Button>
                        <Button
                            type="button"
                            variant="destructive"
                            onClick={handleConfirmDangerAction}
                            disabled={isDangerActionLoading}
                        >
                            {isDangerActionLoading ? <Loader2 className="w-4 h-4 mr-1.5 animate-spin" /> : null}
                            {isOwner ? (zh ? "確認刪除" : "Delete Permanently") : (zh ? "確認退出" : "Leave Trip")}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* 🗓️ 刪除天數安全確認對話框 */}
            <Dialog open={deletingDayNum !== null} onOpenChange={(open) => !open && setDeletingDayNum(null)}>
                <DialogContent className="sm:max-w-md bg-white dark:bg-[#1E2927] border border-[#0B3026]/10 dark:border-white/10 rounded-2xl">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 text-rose-600 dark:text-rose-400">
                            <AlertTriangle className="w-5 h-5" />
                            {zh ? `確定要刪除第 ${deletingDayNum} 天？` : `Delete Day ${deletingDayNum}?`}
                        </DialogTitle>
                        <DialogDescription className="text-xs text-[#0B3026]/70 dark:text-[#88A29A] mt-2">
                            {zh 
                                ? "刪除後，當天的所有景點與活動將被移除，後續天數將自動往前遞補，行程結束日期亦會相應縮短 1 天。此操作不可復原。"
                                : "All activities in this day will be removed, subsequent days will shift forward, and the trip duration will decrease by 1 day. This cannot be undone."}
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter className="mt-4 flex gap-2 justify-end">
                        <Button
                            type="button"
                            variant="outline"
                            onClick={() => setDeletingDayNum(null)}
                            disabled={isDeletingDay}
                            className="rounded-xl"
                        >
                            {zh ? "取消" : "Cancel"}
                        </Button>
                        <Button
                            type="button"
                            variant="destructive"
                            onClick={handleConfirmDeleteDay}
                            disabled={isDeletingDay}
                            className="rounded-xl bg-rose-600 hover:bg-rose-700 text-white font-bold"
                        >
                            {isDeletingDay ? (
                                <span className="flex items-center gap-1.5">
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                    {zh ? "刪除中..." : "Deleting..."}
                                </span>
                            ) : (
                                zh ? "確認刪除" : "Confirm Delete"
                            )}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    )
}
