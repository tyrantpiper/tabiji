"use client"

import { useState, useRef } from "react"
import { Camera, Loader2, RotateCcw, Trash2, Eye } from "lucide-react"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog"
import { VisuallyHidden } from "@radix-ui/react-visually-hidden"
import { ZoomableImage } from "@/components/ui/zoomable-image"
import { useLanguage } from "@/lib/LanguageContext"
import { useHaptic } from "@/lib/hooks"
import { compressImage } from "@/lib/image-utils"
import { tripsApi } from "@/lib/api"
import { resolveDestinationCover } from "@/lib/destination-covers"
import { toast } from "sonner"

interface TripCoverMenuProps {
    tripId: string
    currentCover?: string | null
    tripTitle: string
    userId?: string
    onUpdate?: () => void
}

export function TripCoverMenu({
    tripId,
    currentCover,
    tripTitle,
    userId,
    onUpdate
}: TripCoverMenuProps) {
    const { lang } = useLanguage()
    const zh = lang === "zh"
    const haptic = useHaptic()

    const [loading, setLoading] = useState(false)
    const [previewOpen, setPreviewOpen] = useState(false)
    const fileInputRef = useRef<HTMLInputElement>(null)

    // 📸 處理自訂圖片上傳 (Cloudinary)
    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file) return

        // 立即重設 input value 確保同一檔案可重複觸發
        e.target.value = ""

        setLoading(true)
        haptic.tap()
        const folder = "ryan_travel/covers"

        try {
            // 1. 圖片壓縮優化
            const compressedFile = await compressImage(file, {
                maxWidth: 4096,
                maxHeight: 4096,
                quality: 0.85
            })

            const cloudName = process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME
            const apiKey = process.env.NEXT_PUBLIC_CLOUDINARY_API_KEY

            if (!cloudName || !apiKey) {
                toast.error(zh ? "環境變數缺失，無法連線至 Cloudinary" : "Missing Cloudinary environment variables")
                setLoading(false)
                return
            }

            const timestamp = Math.round(Date.now() / 1000)
            const paramsToSign = { timestamp, folder }

            // 2. 取得後端簽名
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

            // 3. 上傳至 Cloudinary
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
                toast.error(zh ? "圖片上傳失敗" : "Failed to upload image to Cloudinary")
                setLoading(false)
                return
            }

            const result = await uploadRes.json()
            if (!result.secure_url) {
                toast.error(zh ? "未取得有效圖片連結" : "Invalid image URL received")
                setLoading(false)
                return
            }

            // 4. 更新後端資料庫
            await tripsApi.updateCover(tripId, result.secure_url, userId)
            haptic.success()
            toast.success(zh ? "封面已更新！" : "Cover photo updated!")
            onUpdate?.()
        } catch (error) {
            console.error("[TripCoverMenu] Upload error:", error)
            haptic.error()
            toast.error(zh ? "上傳過程發生錯誤" : "Error uploading cover photo")
        } finally {
            setLoading(false)
        }
    }

    // 🔄 恢復為城市預設高質感封面
    const handleResetToDefault = async () => {
        haptic.selection()
        setLoading(true)
        try {
            const defaultCover = resolveDestinationCover(tripTitle)
            await tripsApi.updateCover(tripId, defaultCover, userId)
            haptic.success()
            toast.success(zh ? "已恢復為預設城市封面" : "Reset to default city cover")
            onUpdate?.()
        } catch (error) {
            console.error("[TripCoverMenu] Reset error:", error)
            haptic.error()
            toast.error(zh ? "恢復預設失敗" : "Failed to reset cover")
        } finally {
            setLoading(false)
        }
    }

    // 🗑️ 移除封面照 (設為 null)
    const handleRemoveCover = async () => {
        haptic.selection()
        setLoading(true)
        try {
            await tripsApi.updateCover(tripId, null, userId)
            haptic.success()
            toast.success(zh ? "已移除封面" : "Cover photo removed")
            onUpdate?.()
        } catch (error) {
            console.error("[TripCoverMenu] Remove error:", error)
            haptic.error()
            toast.error(zh ? "移除封面失敗" : "Failed to remove cover")
        } finally {
            setLoading(false)
        }
    }

    return (
        <>
            <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={handleFileChange}
                disabled={loading}
            />

            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <button
                        type="button"
                        onClick={() => haptic.selection()}
                        disabled={loading}
                        className="w-10 h-10 rounded-full flex items-center justify-center bg-stone-100/80 dark:bg-slate-700/80 hover:bg-stone-200/80 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-200 active:scale-90 transition-all cursor-pointer shadow-2xs select-none disabled:opacity-50"
                        title={zh ? "設定行程封面" : "Trip Cover Settings"}
                        aria-label="Trip Cover Settings"
                    >
                        {loading ? (
                            <Loader2 className="w-5 h-5 animate-spin text-emerald-500" />
                        ) : (
                            <Camera className="w-5 h-5" />
                        )}
                    </button>
                </DropdownMenuTrigger>

                <DropdownMenuContent align="end" className="w-48 rounded-xl shadow-lg border border-stone-200 dark:border-slate-700 bg-white dark:bg-slate-800">
                    {/* 上傳更換封面 */}
                    <DropdownMenuItem
                        onClick={() => {
                            haptic.selection()
                            fileInputRef.current?.click()
                        }}
                        className="cursor-pointer gap-2 text-xs font-medium py-2 text-slate-700 dark:text-slate-200"
                    >
                        <Camera className="w-4 h-4 text-emerald-500" />
                        <span>{zh ? "上傳新封面照" : "Upload New Cover"}</span>
                    </DropdownMenuItem>

                    {/* 預覽大圖 (如果有封面) */}
                    {currentCover && (
                        <DropdownMenuItem
                            onClick={() => {
                                haptic.selection()
                                setPreviewOpen(true)
                            }}
                            className="cursor-pointer gap-2 text-xs font-medium py-2 text-slate-700 dark:text-slate-200"
                        >
                            <Eye className="w-4 h-4 text-indigo-500" />
                            <span>{zh ? "檢視封面大圖" : "View Cover Photo"}</span>
                        </DropdownMenuItem>
                    )}

                    <DropdownMenuSeparator className="bg-stone-200/60 dark:bg-slate-700/60" />

                    {/* 恢復預設城市封面 */}
                    <DropdownMenuItem
                        onClick={handleResetToDefault}
                        className="cursor-pointer gap-2 text-xs font-medium py-2 text-slate-700 dark:text-slate-200"
                    >
                        <RotateCcw className="w-4 h-4 text-amber-500" />
                        <span>{zh ? "恢復預設城市封面" : "Reset to City Cover"}</span>
                    </DropdownMenuItem>

                    {/* 移除封面 */}
                    {currentCover && (
                        <DropdownMenuItem
                            onClick={handleRemoveCover}
                            className="cursor-pointer gap-2 text-xs font-medium py-2 text-rose-600 dark:text-rose-400 focus:text-rose-600"
                        >
                            <Trash2 className="w-4 h-4" />
                            <span>{zh ? "移除封面照" : "Remove Cover"}</span>
                        </DropdownMenuItem>
                    )}
                </DropdownMenuContent>
            </DropdownMenu>

            {/* 放大預覽對話框 */}
            {currentCover && (
                <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
                    <DialogContent className="max-w-4xl p-0 bg-transparent border-none shadow-none text-white flex items-center justify-center">
                        <VisuallyHidden>
                            <DialogTitle>{tripTitle} 封面大圖</DialogTitle>
                        </VisuallyHidden>
                        <div className="relative max-h-[85vh] max-w-[90vw] overflow-hidden rounded-2xl bg-black/80">
                            <ZoomableImage
                                src={currentCover}
                                alt={tripTitle}
                                className="w-full h-auto max-h-[85vh] object-contain rounded-2xl"
                            />
                        </div>
                    </DialogContent>
                </Dialog>
            )}
        </>
    )
}
