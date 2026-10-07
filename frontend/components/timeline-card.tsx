"use client"

import { useState, useEffect, memo } from "react"
import {
    MapPin, Utensils, Train, ShoppingBag, Bed, Camera, Copy,
    StickyNote, MoreHorizontal, Edit, Trash2, ExternalLink, Lightbulb, X, Info, Plus
} from "lucide-react"
import { cn, formatCurrency, openExternalLink, getOptimizedImageUrl } from "@/lib/utils"
import {
    Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
    DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import Image from "next/image"
import { ZoomableImage } from "@/components/ui/zoomable-image"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { RichTextarea } from "@/components/ui/rich-textarea"
import { RichDisplay } from "@/components/ui/rich-display"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
    Table, TableBody, TableCell, TableRow,
} from "@/components/ui/table"

import { Activity, SubItem } from "@/lib/itinerary-types"
import { searchNearbyImage, uploadMapillaryToCloudinary } from "@/lib/mapillary"
import { toast } from "sonner"
import { useLanguage } from "@/lib/LanguageContext"
import { SyncStatusBadge } from "@/components/ui/SyncStatusBadge"
import { useSyncStatusStore } from "@/lib/stores/syncStatusStore"

interface TimelineCardProps {
    activity: Activity
    isLast?: boolean
    index: number
    onEdit: (item: Activity) => void
    onDelete: (id: string) => void
    onUpdateActivity: (id: string, updates: Partial<Activity>) => Promise<boolean> // 整合更新
    onOpenDetail?: (item: Activity) => void
}

export const TimelineCard = memo(function TimelineCard({
    activity,
    isLast,
    index,
    onEdit,
    onDelete,
    onUpdateActivity,
    onOpenDetail
}: TimelineCardProps) {
    const { t } = useLanguage()
    const [showDetail, setShowDetail] = useState(false)
    const [showPhotoPreview, setShowPhotoPreview] = useState(false)  // 🆕 圖片預覽狀態
    const [imageError, setImageError] = useState(false) // 🆕 圖片載入失敗狀態

    const firstImageUrl = activity?.image_urls?.[0] || activity?.image_url || activity?.preview_metadata?.mapillary_thumb || activity?.preview_metadata?.map_image || activity?.preview_metadata?.og_image;
    const [lastImageUrl, setLastImageUrl] = useState(firstImageUrl)

    if (firstImageUrl !== lastImageUrl) {
        setImageError(false)
        setLastImageUrl(firstImageUrl)
    }

    // ⚡ E4: 取得景點離線樂觀同步狀態
    const syncMeta = useSyncStatusStore(state => 
        activity?.id ? (state.mutations[activity.id] || Object.values(state.mutations).find(m => m.entityId === activity.id || m.tempId === activity.id)) : undefined
    )

    if (!activity) return null;

    // 判斷是否為 Header 卡片
    const isHeader = activity.category === 'header' || (activity.time || activity.time_slot || "00:00") === '00:00'

    // 🔧 FIX: 導航按鈕邏輯 - sub_items 和導航應並存，不互斥
    const hideMapBtn =
        activity.hide_navigation ||
        ["家中", "家裡", "機上", "飛機上", "等待登機", "home", "on plane", "boarding"].some(k => (activity.place || "").toLowerCase().includes(k)) ||
        (activity.category === 'transport' && !activity.link_url && !activity.lat) ||
        isHeader;

    const openGoogleMap = (e: React.MouseEvent) => {
        e.stopPropagation()
        const url = activity.link_url?.startsWith('http')
            ? activity.link_url
            : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(activity.link_url || activity.place || "")}`;
        openExternalLink(url)
    }

    const getIcon = () => {
        if (isHeader) return <Lightbulb className="w-3.5 h-3.5" />
        const cat = activity.category ? activity.category.toLowerCase().trim() : "sightseeing"
        const title = (activity.place || "").toLowerCase()
        if (cat === "food" || title.includes("餐廳") || title.includes("restaurant") || title.includes("cafe")) return <Utensils className="w-3.5 h-3.5" />
        if (cat === "transport" || title.includes("車站") || title.includes("機場") || title.includes("station") || title.includes("airport")) return <Train className="w-3.5 h-3.5" />
        if (cat === "shopping" || title.includes("百貨") || title.includes("超市") || title.includes("department") || title.includes("market") || title.includes("mall")) return <ShoppingBag className="w-3.5 h-3.5" />
        if (cat === "hotel" || title.includes("飯店") || title.includes("民宿") || title.includes("hotel") || title.includes("hostel")) return <Bed className="w-3.5 h-3.5" />
        return <Camera className="w-3.5 h-3.5" />
    }

    const renderContent = () => {
        // 🆕 支援多圖片：優先使用 image_urls，fallback 到 image_url
        const uploadedImages = activity.image_urls?.length
            ? activity.image_urls
            : (activity.image_url ? [activity.image_url] : [])

        const previewImage = activity.preview_metadata?.mapillary_thumb
            || activity.preview_metadata?.map_image
            || activity.preview_metadata?.og_image

        // 合併陣列：上傳圖片優先，最後補上系統預覽圖
        const images = [...uploadedImages]
        if (previewImage && !images.includes(previewImage)) {
            images.push(previewImage)
        }

        const hasImage = images.length > 0 && !imageError

        return (
            <div className="flex items-start justify-between gap-3">
                {/* 編輯選單 - Mobile Friendly & iOS Frosted Glass Disc */}
                <div className="absolute top-3.5 right-3.5 z-20" onPointerDown={(e) => e.stopPropagation()} onClick={(e) => e.stopPropagation()}>
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7 rounded-full transition-all touch-manipulation flex items-center justify-center p-0 shadow-xs active:scale-90 bg-slate-100/90 hover:bg-slate-200/90 dark:bg-slate-800/90 dark:hover:bg-slate-700/90 text-slate-500 hover:text-slate-800 dark:text-slate-300 dark:hover:text-white backdrop-blur-md border border-slate-200/80 dark:border-slate-700/80"
                            >
                                <MoreHorizontal className="w-3.5 h-3.5 text-slate-600 dark:text-slate-300" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="min-w-35">
                            <DropdownMenuItem onClick={() => onEdit(activity)} className="py-2.5 text-xs">
                                <Edit className="w-3.5 h-3.5 mr-2" /> {t('tc_edit_all')}
                            </DropdownMenuItem>
                            <DropdownMenuItem className="text-red-600 py-2.5 text-xs" onClick={() => onDelete(activity.id || '')}>
                                <Trash2 className="w-3.5 h-3.5 mr-2" /> {t('delete')}
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>

                {/* 左側資訊區 */}
                <div className="flex-1 min-w-0 pr-2">
                    <div className="flex items-center gap-2 mb-1">
                        <h3 className={cn("font-bold text-slate-900 dark:text-white leading-tight truncate", isHeader ? "text-xl" : "text-base")}>
                            <span>{activity.place || (isHeader ? "Notice" : "Unknown Place")}</span>
                        </h3>
                        {syncMeta && <SyncStatusBadge status={syncMeta.status} errorMessage={syncMeta.errorMessage} />}
                    </div>

                    <div className="flex items-center gap-1.5 mb-2 flex-wrap">
                        <span className={cn(
                            "text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border flex items-center gap-1 font-medium",
                            isHeader
                                ? "bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-700 font-bold"
                                : (activity.category === 'transport'
                                    ? "bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-600"
                                    : "bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700")
                        )}>
                            {getIcon()} {isHeader ? "INFO" : (activity.category || "sightseeing")}
                        </span>
                        {activity.is_private && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-50 text-amber-600 border border-amber-200/60 flex items-center gap-1 font-medium">
                                🔒 {t('private') || "Private"}
                            </span>
                        )}
                        {activity.tags?.slice(0, 3).map((tag: string) => (
                            <span key={tag} className="text-[9px] px-1.5 py-0.5 rounded bg-rose-50 text-rose-600 border border-rose-100">
                                #{tag}
                            </span>
                        ))}
                    </div>

                    <p className={cn(
                        "text-slate-600 dark:text-slate-300 leading-relaxed font-light whitespace-pre-wrap",
                        isHeader ? "text-sm mb-3" : "text-xs mb-2.5 line-clamp-2"
                    )}>
                        {activity.desc || t('tc_add_memo_hint')}
                    </p>

                    {/* 附屬表格 (若有 - 依原邏輯展示，Header 與一般行程均完整渲染) */}
                    {activity.sub_items && activity.sub_items.length > 0 && (
                        <div
                            className="mb-2.5 overflow-x-auto rounded-lg border border-slate-200/80 dark:border-slate-700/80 bg-slate-50/70 dark:bg-slate-800/40 touch-pan-x"
                            onPointerDown={(e) => e.stopPropagation()}
                            onClick={(e) => e.stopPropagation()}
                        >
                            <Table className="w-full table-fixed min-w-56">
                                <TableBody>
                                    {activity.sub_items.map((item: SubItem, i: number) => (
                                        <TableRow key={i} className="border-b border-slate-100 dark:border-slate-700 last:border-0">
                                            <TableCell className="py-1.5 px-2.5 align-top w-[calc(100%-36px)]">
                                                <div className="text-[11px] font-bold text-slate-700 dark:text-slate-200 truncate">{item.name}</div>
                                                {item.desc && <div className="text-[9px] text-slate-500 dark:text-slate-400 truncate">{item.desc}</div>}
                                            </TableCell>
                                            {item.link ? (
                                                <TableCell className="py-1 px-1.5 text-right align-middle w-9 shrink-0">
                                                    <button
                                                        type="button"
                                                        className="p-1 rounded-full bg-blue-50 text-blue-600 hover:bg-blue-100 transition-colors"
                                                        onPointerDown={(e) => e.stopPropagation()}
                                                        onClick={(e) => { e.stopPropagation(); openExternalLink(item.link); }}
                                                    >
                                                        <ExternalLink className="w-2.5 h-2.5" />
                                                    </button>
                                                </TableCell>
                                            ) : <TableCell className="w-0 p-0" />}
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </div>
                    )}

                    {/* 按鈕區 */}
                    <div className="flex items-center gap-2" onPointerDown={(e) => e.stopPropagation()} onClick={(e) => e.stopPropagation()}>
                        {!hideMapBtn && (
                            <Button
                                variant="outline"
                                size="sm"
                                className="h-7 px-2 text-[11px] bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 rounded-lg"
                                onClick={openGoogleMap}
                            >
                                <MapPin className="w-3 h-3 mr-1 text-emerald-600" /> {t('tc_navigate')}
                            </Button>
                        )}

                        <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-[11px] text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg"
                            onClick={(e) => {
                                e.stopPropagation()
                                if (onOpenDetail) {
                                    onOpenDetail(activity)
                                } else {
                                    setShowDetail(true)
                                }
                            }}
                        >
                            <StickyNote className="w-3 h-3 mr-1 text-amber-500" /> {t('tc_local_memo')}
                        </Button>
                    </div>
                </div>

                {/* 右側 72px 圓角縮圖 (僅非 Header 且有圖片時展示，加 mr-8 與右上角按鈕完全錯開) */}
                {!isHeader && hasImage && (
                    <div
                        className="w-18 h-18 rounded-xl overflow-hidden relative border border-slate-200/80 dark:border-slate-700/80 shrink-0 self-start shadow-2xs group-hover:scale-102 transition-transform bg-slate-100 dark:bg-slate-800 cursor-pointer mr-8"
                        onPointerDown={(e) => e.stopPropagation()}
                        onClick={(e) => {
                            e.stopPropagation()
                            setShowPhotoPreview(true)
                        }}
                    >
                        <Image
                            src={getOptimizedImageUrl(images[0], 320)}
                            alt={activity.place || "Thumbnail"}
                            fill
                            className="object-cover"
                            unoptimized
                            onError={() => setImageError(true)}
                        />
                        {images.length > 1 && (
                            <div className="absolute bottom-1 right-1 bg-black/65 backdrop-blur-xs text-white text-[9px] font-bold px-1.5 py-0.5 rounded-full ring-1 ring-white/20">
                                +{images.length - 1}
                            </div>
                        )}
                        {images[0] === activity.preview_metadata?.mapillary_thumb && (
                            <div className="absolute top-1 left-1 bg-emerald-600/90 text-white text-[8px] font-bold px-1 py-0.2 rounded">
                                360°
                            </div>
                        )}
                    </div>
                )}
            </div>
        )
    }

    // 🗺️ 檢查座標是否有效以決定可點擊狀態
    const hasValidCoords = Boolean(
        activity.lat && activity.lng &&
        !isNaN(typeof activity.lat === 'string' ? parseFloat(activity.lat) : activity.lat) &&
        !isNaN(typeof activity.lng === 'string' ? parseFloat(activity.lng) : activity.lng)
    )

    // 🗺️ 卡片本體點擊聚焦地圖處理 (防禦性排除按鈕、選單、輸入、表格等互動區)
    const handleCardClick = (e: React.MouseEvent) => {
        const target = e.target as HTMLElement
        if (target.closest('button, [role="menuitem"], input, a, table')) return

        const rawLat = activity.lat
        const rawLng = activity.lng
        const lat = typeof rawLat === 'string' ? parseFloat(rawLat) : (typeof rawLat === 'number' ? rawLat : null)
        const lng = typeof rawLng === 'string' ? parseFloat(rawLng) : (typeof rawLng === 'number' ? rawLng : null)

        if (lat !== null && lng !== null && !isNaN(lat) && !isNaN(lng)) {
            window.dispatchEvent(new CustomEvent('tabidachi-focus-map-activity', {
                detail: {
                    id: activity.id,
                    lat,
                    lng,
                    place: activity.place
                }
            }))
        }
    }

    return (
        <div className="flex gap-4 relative group">
            {/* 左側：時間 + 序號 (寬度加寬至 w-14，時間與序號間距放寬至 mt-2，序號升級為 24px) */}
            <div className="flex flex-col items-center w-14 shrink-0 pt-0.5">
                {!isHeader && (
                    <span className="text-xs font-mono font-bold text-slate-500 dark:text-slate-400 tracking-tight select-none">
                        {activity.time || activity.time_slot || "00:00"}
                    </span>
                )}
                {isHeader ? (
                    <div className="w-6 h-6 rounded-full mt-2 bg-amber-100 dark:bg-amber-900/50 text-amber-600 dark:text-amber-400 flex items-center justify-center border-2 border-white dark:border-slate-900 shadow-sm z-10">
                        <Lightbulb className="w-3.5 h-3.5" strokeWidth={3} />
                    </div>
                ) : (
                    <div className="w-6 h-6 rounded-full mt-2 bg-slate-800 dark:bg-slate-200 text-white dark:text-slate-800 flex items-center justify-center text-[10px] font-bold z-10 border-2 border-white dark:border-slate-900 shadow-sm">
                        {index}
                    </div>
                )}
                {!isLast && <div className="w-px flex-1 bg-slate-200 dark:bg-slate-700 my-1.5" />}
            </div>
            {/* 右側：卡片內容 (點擊本體平滑滾動並 FlyTo 聚焦下方地圖) */}
            <div
                onClick={handleCardClick}
                className={cn(
                    "timeline-card flex-1 min-w-0 mb-4 mt-0.5 relative pt-5.5 pb-4.5 px-4.5 sm:px-5 rounded-2xl transition-all duration-200 shadow-xs active:scale-[0.995]",
                    hasValidCoords ? "cursor-pointer" : "cursor-default",
                    isHeader ? "bg-amber-50/30 dark:bg-amber-900/20 border-2 border-amber-200/70 dark:border-amber-700/70" :
                        (activity.is_highlight
                            ? "bg-amber-50/15 dark:bg-amber-950/20 border-2 border-amber-400 dark:border-amber-500 shadow-[0_0_16px_rgba(251,191,36,0.22)] dark:shadow-[0_0_20px_rgba(245,158,11,0.18)]"
                            : "bg-white dark:bg-slate-800/90 border-2 border-slate-200/90 dark:border-slate-700/85 hover:border-slate-300 dark:hover:border-slate-600"
                        )
                )}
            >
                {renderContent()}
            </div>

            {/* 傳遞 hideMapBtn 給彈窗 */}
            <DetailDialog
                open={showDetail}
                onOpenChange={setShowDetail}
                activity={activity}
                onMap={openGoogleMap}
                hideMapBtn={hideMapBtn}
                onUpdateActivity={onUpdateActivity}
            />

            {/* 🆕 全螢幕圖片預覽 (支援多圖片) */}
            <Dialog open={showPhotoPreview} onOpenChange={setShowPhotoPreview}>
                <DialogContent className="max-w-[95vw] max-h-[90vh] p-0 bg-black/95 border-0 flex items-center justify-center">
                    <DialogHeader className="sr-only">
                        <DialogTitle>{t('tc_photo_preview')}</DialogTitle>
                        <DialogDescription>
                            {t('tc_photo_preview_desc')}
                        </DialogDescription>
                    </DialogHeader>
                    <PhotoGalleryPreview
                        activity={activity}
                        onClose={() => setShowPhotoPreview(false)}
                    />
                </DialogContent>
            </Dialog>
        </div>
    )
})

// --- 升級版彈窗 (可編輯備忘錄) ---
interface DetailDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    activity: Activity
    onMap: (e: React.MouseEvent) => void
    hideMapBtn: boolean
    onUpdateActivity: (id: string, updates: Partial<Activity>) => Promise<boolean>
}

function DetailDialog({ open, onOpenChange, activity, onMap, hideMapBtn, onUpdateActivity }: DetailDialogProps) {
    const { t, lang } = useLanguage()
    const zh = lang === 'zh'
    // Use activity.id + open as key to reset state when activity changes
    const [isEditing, setIsEditing] = useState(false)
    const [note, setNote] = useState(activity.memo || "")
    const [mediaLink, setMediaLink] = useState(activity.website_link || "")
    const [reservationCode, setReservationCode] = useState(activity.reservation_code || "")
    const [cost, setCost] = useState(activity.cost !== undefined && activity.cost !== null ? String(activity.cost) : "")
    // 👇 新增：連結列表狀態
    const [links, setLinks] = useState<SubItem[]>(activity.sub_items || [])
    const [saving, setSaving] = useState(false)
    const [fetchingMapillary, setFetchingMapillary] = useState(false) // 🆕 抓取街景中
    // 🔧 FIX: Use proper useEffect for state sync (was causing render-during-render)
    useEffect(() => {
        // Reset state when dialog opens or activity changes
        if (open) {
            setNote(activity.memo || "")
            setMediaLink(activity.website_link || "")
            setLinks(activity.sub_items || [])
            setReservationCode(activity.reservation_code || "")
            setCost(activity.cost !== undefined && activity.cost !== null ? String(activity.cost) : "")
            setIsEditing(false)
        }
    }, [open, activity.id, activity.memo, activity.sub_items, activity.website_link, activity.reservation_code, activity.cost])

    const handleSave = async () => {
        if (saving) return // 防止重複點擊
        setSaving(true)
        try {
            // 🆕 優化：在儲存前過濾完全空白的連結
            const filteredLinks = links.filter(l => l.name?.trim() || l.link?.trim())

            // 🛡️ 數值安全過濾：防止 NaN 與無效非數字輸入污染後端
            const rawCost = cost.trim() === '' ? undefined : Number(cost)
            const safeCost = (rawCost !== undefined && Number.isFinite(rawCost) && rawCost >= 0) ? rawCost : undefined

            // 🆕 關鍵修復：整合為單一 API 呼叫，徹底解決並發 500 錯誤與 UI 不同步
            const success = await onUpdateActivity(activity.id || '', {
                memo: note,
                website_link: mediaLink,
                sub_items: filteredLinks,
                reservation_code: reservationCode.trim() || undefined,
                cost: safeCost
            })

            if (success) {
                toast.success(t('tc_saved'))
                setIsEditing(false)
            }
        } finally {
            setSaving(false)
        }
    }

    // 連結操作
    const addLink = () => setLinks([...links, { name: "", desc: "", link: "" }])
    const removeLink = (idx: number) => setLinks(links.filter((_, i) => i !== idx))
    const updateLink = (idx: number, field: keyof SubItem, val: string) => {
        setLinks(prev => prev.map((link, i) =>
            i === idx ? { ...link, [field]: val } : link
        ))
    }

    const handleFetchMapillary = async () => {
        if (!activity.lat || !activity.lng) return;
        setFetchingMapillary(true);
        try {
            const image = await searchNearbyImage(activity.lat, activity.lng);
            if (image) {
                // 上傳至 Cloudinary 獲取永久 URL
                const permanentUrl = await uploadMapillaryToCloudinary(image.thumb_1024_url, image.id);
                
                const success = await onUpdateActivity(activity.id!, {
                    preview_metadata: {
                        ...activity.preview_metadata,
                        mapillary_thumb: permanentUrl || image.thumb_1024_url,
                        mapillary_image_id: image.id,
                        mapillary_is_pano: image.is_pano
                    }
                });
                if (success) {
                    toast.success(t('mapillary_fetch_success') || 'Street view image fetched');
                }
            } else {
                toast.error(t('mapillary_no_coverage') || 'No street imagery available');
            }
        } catch {
            toast.error('Failed to fetch street view');
        } finally {
            setFetchingMapillary(false);
        }
    }

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="sm:max-w-lg md:max-w-xl p-0 overflow-hidden bg-stone-50 dark:bg-slate-900 gap-0">
                <div className="p-6 bg-white dark:bg-slate-800 border-b border-slate-100 dark:border-slate-700">
                    <DialogHeader>
                        <DialogTitle className="text-2xl font-serif font-bold text-slate-900 dark:text-white">{activity.place || "Details"}</DialogTitle>
                        <DialogDescription className="sr-only">
                            {t('tc_detail_desc')}
                        </DialogDescription>
                    </DialogHeader>
                </div>
                <ScrollArea className="max-h-[72vh]">
                    <div className="p-6 space-y-6">

                        {/* 1. 攻略/簡介 (唯讀) */}
                        <div className="space-y-2">
                            <h4 className="text-xs font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest flex items-center gap-2">
                                <Info className="w-3.5 h-3.5 text-slate-400" /> {zh ? "景點簡介與攻略" : "Info & Guide"}
                            </h4>
                            <div className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed bg-slate-50 dark:bg-slate-800 p-4 rounded-xl border border-slate-100 dark:border-slate-700 shadow-2xs whitespace-pre-wrap">
                                {activity.desc || t('tc_no_desc')}
                            </div>
                        </div>

                        {/* 2. 預約代碼與預估花費 (就地展示與即時編輯) */}
                        <div className="space-y-2">
                            <div className="flex justify-between items-center">
                                <h4 className="text-xs font-bold text-indigo-500 dark:text-indigo-400 uppercase tracking-widest flex items-center gap-2">
                                    <span>🎫</span> {zh ? "預約代碼與預估花費" : "Reservation & Cost"}
                                </h4>
                                {!isEditing && (
                                    <button
                                        type="button"
                                        onClick={() => setIsEditing(true)}
                                        className="text-xs text-blue-500 hover:underline flex items-center gap-1 font-medium"
                                    >
                                        <Edit className="w-3 h-3" /> {t('edit')}
                                    </button>
                                )}
                            </div>

                            {isEditing ? (
                                <div className="grid grid-cols-2 gap-3 p-3.5 bg-white dark:bg-slate-800 rounded-xl border border-indigo-200/80 dark:border-indigo-900/60 shadow-2xs">
                                    <div className="space-y-1">
                                        <Label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">
                                            {t('tc_reservation_code')}
                                        </Label>
                                        <Input
                                            value={reservationCode}
                                            onChange={(e) => setReservationCode(e.target.value)}
                                            placeholder={zh ? "訂位代號 / PNR" : "PNR / Code"}
                                            className="h-9 text-xs font-mono bg-slate-50 dark:bg-slate-900"
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <Label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">
                                            {t('tc_estimated_cost')}
                                        </Label>
                                        <Input
                                            type="number"
                                            value={cost}
                                            onChange={(e) => setCost(e.target.value)}
                                            placeholder={zh ? "金額" : "Amount"}
                                            className="h-9 text-xs font-mono bg-slate-50 dark:bg-slate-900"
                                        />
                                    </div>
                                </div>
                            ) : (
                                (reservationCode || (cost && cost !== "0")) ? (
                                    <div className="grid grid-cols-2 gap-3">
                                        <div className="p-3 bg-white dark:bg-slate-800/80 rounded-xl border border-slate-200/80 dark:border-slate-700 shadow-2xs flex items-center justify-between">
                                            <div className="min-w-0 pr-2">
                                                <div className="text-[10px] text-slate-400 uppercase font-bold tracking-wider mb-0.5">
                                                    {t('tc_reservation_code')}
                                                </div>
                                                <div className="text-xs font-bold text-slate-800 dark:text-slate-100 font-mono truncate">
                                                    {reservationCode || (zh ? "無代碼" : "None")}
                                                </div>
                                            </div>
                                            {reservationCode && (
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        if (navigator?.clipboard?.writeText) {
                                                            navigator.clipboard.writeText(reservationCode)
                                                                .then(() => toast.success(zh ? "預約代碼已複製 ✓" : "Code copied ✓"))
                                                                .catch(() => toast.info(reservationCode))
                                                        } else {
                                                            toast.info(reservationCode)
                                                        }
                                                    }}
                                                    className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-400 hover:text-slate-600 transition-colors shrink-0"
                                                    title={zh ? "複製預約代碼" : "Copy code"}
                                                >
                                                    <Copy className="w-3.5 h-3.5" />
                                                </button>
                                            )}
                                        </div>

                                        <div className="p-3 bg-white dark:bg-slate-800/80 rounded-xl border border-slate-200/80 dark:border-slate-700 shadow-2xs">
                                            <div className="text-[10px] text-slate-400 uppercase font-bold tracking-wider mb-0.5">
                                                {t('tc_estimated_cost')}
                                            </div>
                                            <div className="text-xs font-bold text-slate-800 dark:text-slate-100 font-mono">
                                                {cost ? `¥${formatCurrency(Number(cost))}` : (zh ? "未設定" : "None")}
                                            </div>
                                        </div>
                                    </div>
                                ) : (
                                    <button
                                        type="button"
                                        onClick={() => setIsEditing(true)}
                                        className="w-full py-2.5 px-3 rounded-xl border border-dashed border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-700 bg-white/50 dark:bg-slate-800/40 text-slate-400 hover:text-indigo-600 text-xs flex items-center justify-center gap-1.5 transition-colors"
                                    >
                                        <Plus className="w-3.5 h-3.5" />
                                        <span>{zh ? "新增預約代碼或預估花費" : "Add reservation code or cost"}</span>
                                    </button>
                                )
                            )}
                        </div>

                        {/* 3. Memo & Links (私密備忘與外部連結) */}
                        <div className="space-y-2">
                            <div className="flex justify-between items-center">
                                <h4 className="text-xs font-bold text-amber-500 dark:text-amber-400 uppercase tracking-widest flex items-center gap-2">
                                    <StickyNote className="w-3.5 h-3.5" /> {zh ? "私密備忘與連結" : "Memo & Links"}
                                </h4>
                                {!isEditing && (
                                    <button onClick={() => setIsEditing(true)} className="text-xs text-blue-500 hover:underline flex items-center gap-1 font-medium">
                                        <Edit className="w-3 h-3" /> {t('edit')}
                                    </button>
                                )}
                            </div>

                            {isEditing ? (
                                <div className="space-y-4 bg-white dark:bg-slate-800 p-3 rounded-xl border border-amber-200 dark:border-amber-700 shadow-2xs">
                                    {/* Memo 編輯 - 使用 RichTextarea */}
                                    <RichTextarea
                                        value={note}
                                        onChange={setNote}
                                        placeholder={t('tc_memo_placeholder')}
                                        className="bg-yellow-50/30"
                                        minHeight="80px"
                                    />

                                    {/* 連結編輯 */}
                                    <div className="space-y-2">
                                        <Label className="text-[10px] text-slate-400 uppercase font-semibold">{t('tc_links_label')}</Label>
                                        {links.map((link, i) => (
                                            <div key={i} className="space-y-1 p-2 bg-slate-50 dark:bg-slate-900 rounded-lg border border-slate-100 dark:border-slate-700 relative">
                                                <button onClick={() => removeLink(i)} className="absolute top-1 right-1 text-slate-300 hover:text-red-500"><X className="w-3 h-3" /></button>
                                                <Input className="h-7 text-xs" placeholder={t('tc_link_name_ph')} value={link.name || ""} onChange={e => updateLink(i, 'name', e.target.value)} />
                                                <Input className="h-7 text-xs" placeholder={t('tc_link_desc_ph')} value={link.desc || ""} onChange={e => updateLink(i, 'desc', e.target.value)} />
                                                <Input className="h-7 text-xs font-mono text-blue-600" placeholder="https://..." value={link.link || ""} onChange={e => updateLink(i, 'link', e.target.value)} />
                                            </div>
                                        ))}
                                        <Button size="sm" variant="outline" onClick={addLink} className="w-full h-7 text-xs">{t('tc_add_link')}</Button>
                                    </div>

                                    <div className="flex gap-2 justify-end pt-2 border-t border-slate-100 dark:border-slate-700">
                                        <Button size="sm" variant="ghost" onClick={() => setIsEditing(false)} disabled={saving}>{t('cancel')}</Button>
                                        <Button size="sm" onClick={handleSave} disabled={saving} className="bg-amber-500 hover:bg-amber-600 text-white font-bold shadow-xs">
                                            {saving ? t('saving') : t('tc_save_changes')}
                                        </Button>
                                    </div>
                                </div>
                            ) : (
                                // 唯讀顯示模式
                                <div className="space-y-3">
                                    {/* Memo 顯示 - 使用 RichDisplay */}
                                    <div
                                        className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed bg-yellow-50/50 dark:bg-amber-900/20 p-4 rounded-xl border border-dashed border-amber-200 dark:border-amber-700 cursor-text hover:bg-yellow-50 dark:hover:bg-amber-900/30 transition-colors"
                                        onClick={() => setIsEditing(true)}
                                    >
                                        {note ? <RichDisplay text={note} /> : <span className="text-slate-400 italic flex items-center gap-2"><Plus className="w-3 h-3" /> {t('tc_add_memo')}</span>}
                                    </div>

                                    {/* Links 顯示 (如果有) */}
                                    {links.length > 0 && (
                                        <div className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700 shadow-2xs bg-white dark:bg-slate-800">
                                            <Table>
                                                <TableBody>
                                                    {links.map((item: SubItem, i: number) => (
                                                        <TableRow key={i} className="hover:bg-slate-50 dark:hover:bg-slate-700">
                                                            <TableCell className="py-2 px-3 align-top">
                                                                <div className="text-xs font-bold text-slate-700 dark:text-slate-200">{item.name}</div>
                                                                {item.desc && <div className="text-[10px] text-slate-500 dark:text-slate-400">{item.desc}</div>}
                                                            </TableCell>
                                                            <TableCell className="py-2 px-2 text-right align-middle w-10">
                                                                {item.link && (
                                                                    <button
                                                                        type="button"
                                                                        className="p-1.5 rounded-full bg-blue-50 text-blue-600 hover:bg-blue-100"
                                                                        onClick={(e) => { e.stopPropagation(); openExternalLink(item.link); }}
                                                                    >
                                                                        <ExternalLink className="w-3 h-3" />
                                                                    </button>
                                                                )}
                                                            </TableCell>
                                                        </TableRow>
                                                    ))}
                                                </TableBody>
                                            </Table>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>

                        {/* 4. 街景預覽 (移至最底部) */}
                        {activity.lat && activity.lng && (
                            <div className="p-3.5 bg-emerald-50/50 dark:bg-emerald-900/10 rounded-xl border border-emerald-100 dark:border-emerald-800 space-y-2.5">
                                <div className="flex items-center gap-1.5">
                                    <Camera className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                                    <span className="text-[10px] text-emerald-600 dark:text-emerald-400 uppercase font-bold tracking-wider">
                                        {t('mapillary_streetview') || 'Street View'}
                                    </span>
                                    {activity.preview_metadata?.mapillary_is_pano && (
                                        <span className="text-[9px] bg-emerald-200/60 dark:bg-emerald-800/40 text-emerald-700 dark:text-emerald-300 px-1.5 py-0.5 rounded-full font-bold">360°</span>
                                    )}
                                </div>
                                {/* Row 1: [Copy] [Coordinates] */}
                                <div className="flex gap-1.5 items-center">
                                    <button
                                        type="button"
                                        className="h-8 w-8 shrink-0 flex items-center justify-center rounded-md border border-emerald-200 dark:border-emerald-700 bg-white dark:bg-slate-800 hover:bg-emerald-50 dark:hover:bg-emerald-900/30 transition-colors"
                                        onClick={() => {
                                            const lat = typeof activity.lat === 'string' ? parseFloat(activity.lat) : activity.lat
                                            const lng = typeof activity.lng === 'string' ? parseFloat(activity.lng) : activity.lng
                                            navigator.clipboard.writeText(`${lat}, ${lng}`)
                                            toast.success(zh ? '座標已複製 ✓' : 'Coordinates copied ✓')
                                        }}
                                        title={zh ? "複製座標" : "Copy coordinates"}
                                    >
                                        <Copy className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                                    </button>
                                    <div className="h-8 text-xs flex-1 flex items-center px-3 bg-white dark:bg-slate-800 border border-emerald-200 dark:border-emerald-700 rounded-md text-slate-600 dark:text-slate-300 font-mono">
                                        {(typeof activity.lat === 'string' ? parseFloat(activity.lat) : activity.lat)?.toFixed(5)}, {(typeof activity.lng === 'string' ? parseFloat(activity.lng) : activity.lng)?.toFixed(5)}
                                    </div>
                                </div>
                                {/* Row 2: [Fetch Street View Button] — 滿版 */}
                                <Button
                                    size="sm"
                                    className="w-full h-9 text-xs bg-emerald-500 hover:bg-emerald-600 text-white border-0 gap-1.5 font-bold shadow-xs"
                                    onClick={handleFetchMapillary}
                                    disabled={fetchingMapillary}
                                >
                                    <Camera className="w-3.5 h-3.5" />
                                    {fetchingMapillary ? '...' : (t('fetch_streetview') || 'Fetch Street View')}
                                </Button>
                                {activity.preview_metadata?.mapillary_thumb && (
                                    <p className="text-[10px] text-emerald-600 dark:text-emerald-400 text-center font-medium">✓ Street view image loaded</p>
                                )}
                            </div>
                        )}
                    </div>
                </ScrollArea>

                {/* 底部按鈕 */}
                <div className="p-4 bg-white dark:bg-slate-800 border-t border-slate-100 dark:border-slate-700 flex gap-3">
                    {!hideMapBtn && (
                        <Button variant="outline" className="flex-1 dark:border-slate-600 dark:text-slate-300" onClick={onMap}>
                            <MapPin className="w-4 h-4 mr-2" /> Google Maps
                        </Button>
                    )}
                    <Button className={cn("flex-1 bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:bg-slate-800 dark:hover:bg-slate-100", hideMapBtn ? "w-full" : "")} onClick={() => onOpenChange(false)}>
                        Close
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    )
}

// --- 🆕 多圖片藝廊預覽元件 ---
interface PhotoGalleryPreviewProps {
    activity: Activity
    onClose: () => void
}

function PhotoGalleryPreview({ activity, onClose }: PhotoGalleryPreviewProps) {
    // 🆕 Image Hunter: 結合上傳的圖片與自動抓取的街景/預覽圖，讓它們共存
    const uploadedImages = activity.image_urls?.length
        ? activity.image_urls
        : (activity.image_url ? [activity.image_url] : [])

    const previewImage = activity.preview_metadata?.mapillary_thumb
        || activity.preview_metadata?.map_image
        || activity.preview_metadata?.og_image

    // 合併陣列：上傳圖片優先，最後補上系統預覽圖 (如果還不在清單中的話)
    const images = [...uploadedImages]
    if (previewImage && !images.includes(previewImage)) {
        images.push(previewImage)
    }

    const [currentIndex, setCurrentIndex] = useState(0)

    if (images.length === 0) return null

    return (
        <div className="relative w-full h-[80vh] flex flex-col justify-center">
            <ZoomableImage
                src={getOptimizedImageUrl(images[currentIndex], 1024)}
                alt={activity.place || "Preview"}
                onClose={onClose}
            />

            {/* 🆕 圖片導航指示器 (Dots) */}
            {images.length > 1 && (
                <div className="absolute top-4 left-1/2 -translate-x-1/2 flex gap-1.5 z-50">
                    {images.map((_, i) => (
                        <button
                            key={i}
                            onClick={(e) => { e.stopPropagation(); setCurrentIndex(i); }}
                            className={cn(
                                "w-2 h-2 rounded-full transition-all duration-300",
                                i === currentIndex
                                    ? "bg-white scale-125 shadow-[0_0_8px_rgba(255,255,255,0.8)]"
                                    : "bg-white/30 hover:bg-white/50"
                            )}
                        />
                    ))}
                </div>
            )}

            {/* 🆕 左右切換按鈕 (中心側邊) */}
            {images.length > 1 && (
                <>
                    <button
                        onClick={(e) => { e.stopPropagation(); setCurrentIndex((prev) => (prev - 1 + images.length) % images.length); }}
                        className="absolute left-4 top-1/2 -translate-y-1/2 w-10 h-10 flex items-center justify-center bg-black/40 hover:bg-black/60 text-white rounded-full backdrop-blur-sm transition-all z-50"
                    >
                        <span className="text-xl">←</span>
                    </button>
                    <button
                        onClick={(e) => { e.stopPropagation(); setCurrentIndex((prev) => (prev + 1) % images.length); }}
                        className="absolute right-4 top-1/2 -translate-y-1/2 w-10 h-10 flex items-center justify-center bg-black/40 hover:bg-black/60 text-white rounded-full backdrop-blur-sm transition-all z-50"
                    >
                        <span className="text-xl">→</span>
                    </button>
                </>
            )}

            {/* 🆕 頁碼顯示 */}
            {images.length > 1 && (
                <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-black/50 text-white text-xs px-3 py-1.5 rounded-full backdrop-blur-sm z-50">
                    {currentIndex + 1} / {images.length}
                </div>
            )}
        </div>
    )
}
