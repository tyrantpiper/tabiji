"use client"

import { useState, useRef, useEffect } from "react"
import Image from "next/image"
import { ZoomableImage } from "@/components/ui/zoomable-image"
import { Camera, Loader2, Trash2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { toast } from "sonner"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import { VisuallyHidden } from "@radix-ui/react-visually-hidden"
import { compressImage, type ImagePresetName } from "@/lib/image-utils"
import { useLanguage } from "@/lib/LanguageContext"
import { cloudinaryApi } from "@/lib/api"

const DIRECT_PASS_RASTER_MIMES = new Set(["image/webp", "image/jpeg", "image/png"])
const DIRECT_PASS_MAX_BYTES = 4 * 1024 * 1024

function inferPresetFromFolder(folder?: string): ImagePresetName {
    const normalized = (folder || "").toLowerCase()
    if (normalized.includes("avatars")) return "avatar"
    if (normalized.includes("receipts")) return "receipt"
    if (normalized.includes("covers")) return "cover"
    if (normalized.includes("hotels")) return "document"
    return "spot"
}

function blobToDataUrl(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onloadend = () => {
            if (typeof reader.result === "string") {
                resolve(reader.result)
            } else {
                reject(new Error("Failed to encode image as data URL"))
            }
        }
        reader.onerror = () => reject(reader.error || new Error("FileReader error"))
        reader.readAsDataURL(blob)
    })
}

export interface ImageUploadSuccessPayload {
    url: string
    file: Blob | File
    dataUrl?: string
}

interface ImageUploadProps {
    value?: string
    onChange: (url: string) => void
    onUploadSuccess?: (payload: ImageUploadSuccessPayload) => void
    onRemove?: () => void
    folder?: string
    preset?: ImagePresetName
    className?: string
    icon?: React.ReactNode
    showPreview?: boolean
}

export function ImageUpload({
    value,
    onChange,
    onUploadSuccess,
    onRemove,
    folder = "ryan_travel",
    preset,
    className,
    icon,
    showPreview = true,
}: ImageUploadProps) {
    const { t, lang } = useLanguage()
    const zh = lang === 'zh'
    const [loading, setLoading] = useState(false)
    const [progress, setProgress] = useState(0)
    const [previewOpen, setPreviewOpen] = useState(false)
    const fileInputRef = useRef<HTMLInputElement>(null)
    const uploadingRef = useRef(false)
    const isMountedRef = useRef(true)
    const activeXhrRef = useRef<XMLHttpRequest | null>(null)

    useEffect(() => {
        isMountedRef.current = true
        return () => {
            isMountedRef.current = false
            uploadingRef.current = false
            if (activeXhrRef.current) {
                try {
                    activeXhrRef.current.abort()
                } catch {
                    // ignore abort errors during unmount
                }
                activeXhrRef.current = null
            }
        }
    }, [])

    const triggerFilePicker = () => {
        if (loading || uploadingRef.current) return
        fileInputRef.current?.click()
    }

    const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file) return
        e.target.value = ""

        if (uploadingRef.current) return
        uploadingRef.current = true
        setLoading(true)
        setProgress(0)
        try {
            const targetPreset = preset ?? inferPresetFromFolder(folder)
            const compressedFile = await compressImage(file, targetPreset)
            if (!isMountedRef.current) return

            const timestamp = Math.round(Date.now() / 1000);
            const paramsToSign = { timestamp, folder };
            const signData = await cloudinaryApi.signUpload(paramsToSign);
            if (!isMountedRef.current) return

            const cloudName = signData.cloudName || process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME
            const apiKey = signData.apiKey || process.env.NEXT_PUBLIC_CLOUDINARY_API_KEY

            if (!cloudName || !apiKey) {
                console.error("Missing Cloudinary env vars:", { cloudName: !!cloudName, apiKey: !!apiKey })
                toast.error(zh ? `環境變數缺失！請確認 .env.local 並重啟前端。` : `Missing env vars! Check .env.local and restart.`)
                uploadingRef.current = false
                setLoading(false)
                setProgress(0)
                return
            }

            const { signature } = signData;

            let precomputedDataUrl: string | undefined
            if (
                onUploadSuccess &&
                DIRECT_PASS_RASTER_MIMES.has((compressedFile.type || "").toLowerCase()) &&
                compressedFile.size <= DIRECT_PASS_MAX_BYTES
            ) {
                precomputedDataUrl = await blobToDataUrl(compressedFile).catch(() => undefined)
                if (!isMountedRef.current) return
            }

            const url = `https://api.cloudinary.com/v1_1/${cloudName}/image/upload`
            const data = new FormData()
            const uploadName = compressedFile instanceof File ? compressedFile.name : file.name
            data.append("file", compressedFile, uploadName)
            data.append("timestamp", timestamp.toString())
            data.append("folder", folder)
            data.append("signature", signature)
            data.append("api_key", apiKey)

            const xhr = new XMLHttpRequest()
            activeXhrRef.current = xhr

            xhr.upload.onprogress = (event) => {
                if (!isMountedRef.current) return
                if (event.lengthComputable) {
                    const percent = Math.round((event.loaded / event.total) * 100)
                    setProgress(percent)
                }
            }

            xhr.onload = () => {
                if (activeXhrRef.current === xhr) {
                    activeXhrRef.current = null
                }
                if (!isMountedRef.current) {
                    uploadingRef.current = false
                    return
                }
                try {
                    if (xhr.status === 200) {
                        const result = JSON.parse(xhr.responseText)
                        if (result?.secure_url && typeof result.secure_url === "string") {
                            const safeUrl = result.secure_url.replace(/\.(heic|heif)(?=[?#]|$)/i, ".jpg")
                            onChange(safeUrl)
                            onUploadSuccess?.({ url: safeUrl, file: compressedFile, dataUrl: precomputedDataUrl })
                            toast.success(t('img_upload_success'))
                        } else {
                            console.error("Cloudinary error:", result)
                            toast.error(zh ? `Cloudinary 錯誤: ${result?.error?.message || JSON.stringify(result)}` : `Cloudinary error: ${result?.error?.message || JSON.stringify(result)}`)
                        }
                    } else {
                        toast.error(zh ? `上傳失敗: ${xhr.status}` : `Upload failed: ${xhr.status}`)
                    }
                } catch (parseError) {
                    console.error("Cloudinary response parse error:", parseError)
                    toast.error(t('img_upload_failed'))
                } finally {
                    uploadingRef.current = false
                    if (isMountedRef.current) {
                        setLoading(false)
                        setProgress(0)
                    }
                }
            }

            xhr.onerror = () => {
                if (activeXhrRef.current === xhr) {
                    activeXhrRef.current = null
                }
                uploadingRef.current = false
                if (!isMountedRef.current) return
                toast.error(t('img_upload_failed'))
                setLoading(false)
                setProgress(0)
            }

            xhr.onabort = () => {
                if (activeXhrRef.current === xhr) {
                    activeXhrRef.current = null
                }
                uploadingRef.current = false
                if (!isMountedRef.current) return
                setLoading(false)
                setProgress(0)
            }

            xhr.open("POST", url)
            xhr.send(data)

        } catch (error) {
            console.error("Upload error:", error)
            uploadingRef.current = false
            if (isMountedRef.current) {
                toast.error(t('img_upload_failed'))
                setLoading(false)
                setProgress(0)
            }
        }
    }

    const handleRemove = () => {
        onRemove?.()
        onChange("")
    }

    return (
        <>
            <div className={cn("relative flex items-center gap-3", className)}>
                {/* 已上傳的圖片 - 點擊可預覽 */}
                {value && (
                    <div className="flex flex-col items-center gap-1">
                        <div
                            className={cn(
                                "relative h-16 w-16 rounded-lg overflow-hidden border border-slate-200 transition-all",
                                showPreview ? "cursor-pointer hover:ring-2 hover:ring-blue-500" : "cursor-default"
                            )}
                            onClick={() => showPreview && setPreviewOpen(true)}
                        >
                            <Image src={value} alt="Upload" fill className="object-cover" unoptimized />
                        </div>
                        {/* 移除按鈕 - 在圖片下方 */}
                        <button
                            type="button"
                            onClick={handleRemove}
                            className="text-[10px] text-slate-400 hover:text-red-500 flex items-center gap-0.5 border border-dashed border-slate-300 hover:border-red-400 px-1.5 py-0.5 rounded transition-colors"
                        >
                            <Trash2 className="w-3 h-3" />
                            {zh ? '移除' : 'Remove'}
                        </button>
                    </div>
                )}

                {/* 上傳按鈕 - 永遠顯示（可以上傳/替換圖片）*/}
                {icon ? (
                    <div
                        onClick={triggerFilePicker}
                        aria-disabled={loading}
                        className={cn("flex items-center justify-center cursor-pointer", loading && "pointer-events-none opacity-60", className)}
                    >
                        {loading ? (
                            <span className="text-[10px] font-mono text-blue-500">{progress}%</span>
                        ) : icon}
                    </div>
                ) : (
                    <div
                        onClick={triggerFilePicker}
                        aria-disabled={loading}
                        className={cn(
                            "h-16 w-16 rounded-lg border-2 border-dashed border-slate-300 flex flex-col items-center justify-center cursor-pointer hover:bg-slate-50 hover:border-blue-400 transition-colors shrink-0",
                            loading && "pointer-events-none opacity-60"
                        )}
                    >
                        {loading ? (
                            <div className="flex flex-col items-center">
                                <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
                                <span className="text-[10px] text-blue-500 font-mono mt-1">{progress}%</span>
                            </div>
                        ) : (icon || <Camera className="w-5 h-5 text-slate-400" />)}
                    </div>
                )}

                <input
                    type="file"
                    ref={fileInputRef}
                    className="hidden"
                    accept="image/*"
                    onChange={handleUpload}
                />
            </div>

            {/* 全螢幕預覽 Dialog (可縮放) */}
            <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
                <DialogContent className="max-w-[95vw] max-h-[90vh] p-0 bg-black/95 border-0 flex items-center justify-center z-[160]">
                    <VisuallyHidden>
                        <DialogTitle>{t('img_preview')}</DialogTitle>
                        <DialogDescription>{t('img_preview_desc')}</DialogDescription>
                    </VisuallyHidden>
                    {value && (
                        <div className="relative w-full h-[80vh]">
                            <ZoomableImage
                                src={value}
                                alt="Preview"
                                onClose={() => setPreviewOpen(false)}
                            />
                        </div>
                    )}
                </DialogContent>
            </Dialog>
        </>
    )
}
