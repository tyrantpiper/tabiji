"use client"

import React, { useState, useRef, useEffect } from "react"
import { X, Camera, Lock, Loader2 } from "lucide-react"
import Image from "next/image"
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { VisuallyHidden } from "@radix-ui/react-visually-hidden"
import { Button } from "@/components/ui/button"
import { toast } from "sonner"
import { useHaptic } from "@/lib/hooks"
import { useLanguage } from "@/lib/LanguageContext"
import { uploadCapsulePhotoToCloudinary } from "@/lib/capsule-upload"
import { capsulesApi } from "@/lib/api"
import { TripCapsuleEntry } from "@/lib/itinerary-types"

interface PolaroidCapsuleModalProps {
    isOpen: boolean
    onOpenChange: (open: boolean) => void
    tripId: string
    day: number
    userId?: string
    existingEntry?: TripCapsuleEntry | null
    onSuccess?: () => void
}

const MOOD_EMOJIS = [
    { emoji: "🥳", labelZh: "嗨翻", labelEn: "Excited" },
    { emoji: "🤩", labelZh: "驚艷", labelEn: "Amazed" },
    { emoji: "🍜", labelZh: "吃貨", labelEn: "Foodie" },
    { emoji: "😴", labelZh: "累趴", labelEn: "Exhausted" },
    { emoji: "🤯", labelZh: "震撼", labelEn: "Mindblown" },
    { emoji: "✨", labelZh: "溫馨", labelEn: "Cherished" },
    { emoji: "🤣", labelZh: "爆笑", labelEn: "Hilarious" },
    { emoji: "😭", labelZh: "崩潰", labelEn: "Meltdown" },
    { emoji: "☕", labelZh: "愜意", labelEn: "Chill" },
    { emoji: "💸", labelZh: "爆買", labelEn: "Broke" },
    { emoji: "📸", labelZh: "狂拍", labelEn: "Photogenic" },
    { emoji: "🍺", labelZh: "微醺", labelEn: "Tipsy" },
]

export function PolaroidCapsuleModal({
    isOpen,
    onOpenChange,
    tripId,
    day,
    userId,
    existingEntry,
    onSuccess,
}: PolaroidCapsuleModalProps) {
    const { lang } = useLanguage()
    const zh = lang === "zh"
    const haptic = useHaptic()

    const [mood, setMood] = useState<string>("✨")
    const [content, setContent] = useState<string>("")
    const [photoUrl, setPhotoUrl] = useState<string | null>(null)
    const [uploading, setUploading] = useState<boolean>(false)
    const [uploadProgress, setUploadProgress] = useState<number>(0)
    const [saving, setSaving] = useState<boolean>(false)
    const [isCustomEmojiOpen, setIsCustomEmojiOpen] = useState<boolean>(false)
    const [customEmojiInput, setCustomEmojiInput] = useState<string>("")

    const fileInputRef = useRef<HTMLInputElement>(null)

    // 當打開或 existingEntry 變動時同步狀態
    useEffect(() => {
        if (isOpen) {
            setIsCustomEmojiOpen(false)
            setCustomEmojiInput("")
            if (existingEntry) {
                setMood(existingEntry.mood_emoji || "✨")
                setContent(existingEntry.content || "")
                setPhotoUrl(existingEntry.photo_url || null)
            } else {
                setMood("✨")
                setContent("")
                setPhotoUrl(null)
            }
            setUploadProgress(0)
            setUploading(false)
            setSaving(false)
        }
    }, [isOpen, existingEntry, day])

    const handlePhotoSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (!file) return

        setUploading(true)
        setUploadProgress(10)
        haptic.selection()

        try {
            const url = await uploadCapsulePhotoToCloudinary(file, (percent) => {
                setUploadProgress(percent)
            })
            setPhotoUrl(url)
            toast.success(zh ? "拍立得相片上傳成功！" : "Photo uploaded!")
            haptic.success()
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : "上傳失敗"
            toast.error(msg)
            haptic.error()
        } finally {
            setUploading(false)
            if (fileInputRef.current) fileInputRef.current.value = ""
        }
    }

    const handleSave = async () => {
        if (!content.trim()) {
            toast.error(zh ? "請寫下一兩句今天的心得真心話～" : "Please write a short note for today.")
            return
        }

        if (content.length > 500) {
            toast.error(zh ? "內容不能超過 500 字元。" : "Content cannot exceed 500 characters.")
            return
        }

        setSaving(true)
        haptic.tap()

        try {
            await capsulesApi.submit(
                tripId,
                {
                    day_number: day,
                    mood_emoji: mood,
                    content: content.trim(),
                    photo_url: photoUrl,
                },
                userId
            )

            toast.success(zh ? "🔒 心得已成功封存入時光膠囊！" : "🔒 Capsule sealed into vault!")
            haptic.success()
            onSuccess?.()
            onOpenChange(false)
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : "封存失敗"
            toast.error(msg)
            haptic.error()
        } finally {
            setSaving(false)
        }
    }

    return (
        <Dialog open={isOpen} onOpenChange={onOpenChange}>
            <DialogContent
                showCloseButton={false}
                overlayClassName="bg-[#0B3026]/45 dark:bg-black/65 backdrop-blur-md transition-all duration-300"
                className="max-w-md w-[92vw] sm:w-full p-0 flex flex-col max-h-[88vh] sm:max-h-[85vh] overflow-hidden rounded-3xl bg-[#F6F5EE] dark:bg-[#182320] text-[#1E2927] dark:text-[#E5EBEA] border border-[#0B3026]/10 dark:border-white/10 shadow-2xl shadow-[#0B3026]/15 dark:shadow-black/70 ring-1 ring-[#E56E25]/10 dark:ring-white/5 transition-colors"
            >
                <VisuallyHidden>
                    <DialogTitle>
                        {day === 0 ? "旅程終局總結膠囊" : `Day ${day} 旅伴時光膠囊`}
                    </DialogTitle>
                    <DialogDescription>
                        記錄今天的私密心得與拍立得相片，旅程結束前其他人無法偷看。
                    </DialogDescription>
                </VisuallyHidden>

                {/* 頂部 Header (唯一關閉按鈕，避免雙重打叉) */}
                <div className="shrink-0 relative px-5 pt-4.5 pb-3 border-b border-[#0B3026]/8 dark:border-white/10 flex items-center justify-between bg-linear-to-b from-[#EAE8DE]/80 to-[#F6F5EE] dark:from-[#121A18] dark:to-[#182320] transition-colors">
                    <div className="flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-xl bg-[#E56E25]/15 dark:bg-[#F0803C]/20 border border-[#E56E25]/30 flex items-center justify-center text-[#E56E25] dark:text-[#F0803C]">
                            <Lock className="w-4 h-4" />
                        </div>
                        <div>
                            <h3 className="text-sm font-bold tracking-tight text-[#1E2927] dark:text-white flex items-center gap-1.5">
                                {day === 0 ? (zh ? "旅程終局總結膠囊" : "Trip Finale Capsule") : (zh ? `Day ${day} 旅伴時光膠囊` : `Day ${day} Time Capsule`)}
                            </h3>
                            <p className="text-[11px] text-[#5C6B68] dark:text-[#A2B1AE]">
                                {zh ? "旅途中僅你可見 ｜ 旅程結束全體破印" : "Sealed until trip ends"}
                            </p>
                        </div>
                    </div>
                    <button
                        type="button"
                        onClick={() => onOpenChange(false)}
                        className="p-1.5 rounded-full text-[#5C6B68] hover:text-[#1E2927] dark:text-[#A2B1AE] dark:hover:text-white hover:bg-[#EAE8DE] dark:hover:bg-white/10 transition-colors"
                        aria-label="Close"
                    >
                        <X className="w-4 h-4" />
                    </button>
                </div>

                {/* 拍立得相框本體與內容 (獨立滾動區，平滑滑動) */}
                <div className="flex-1 overflow-y-auto overscroll-contain p-4 sm:p-5 space-y-4">
                    {/* 拍立得照片外框 (精緻緊湊 224px 尺寸，減輕滑動負擔) */}
                    <div className="mx-auto w-full max-w-56 bg-white p-2.5 pb-4 rounded-lg shadow-xl shadow-[#0B3026]/10 dark:shadow-black/50 text-[#1E2927] border border-[#0B3026]/5 -rotate-1 transition-transform hover:rotate-0">
                        <div
                            onClick={() => !uploading && fileInputRef.current?.click()}
                            className="relative w-full aspect-square bg-[#F6F5EE] dark:bg-[#121A18] rounded border border-[#0B3026]/10 dark:border-white/10 overflow-hidden flex flex-col items-center justify-center cursor-pointer group"
                        >
                            {photoUrl ? (
                                <>
                                    <Image
                                        src={photoUrl}
                                        alt="Polaroid"
                                        fill
                                        className="object-cover"
                                        unoptimized
                                    />
                                    <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white text-xs font-medium gap-1">
                                        <Camera className="w-4 h-4" />
                                        {zh ? "更換相片" : "Change"}
                                    </div>
                                </>
                            ) : (
                                <div className="flex flex-col items-center justify-center gap-1 text-[#5C6B68] dark:text-[#A2B1AE] p-3 text-center">
                                    {uploading ? (
                                        <>
                                            <Loader2 className="w-6 h-6 text-[#E56E25] dark:text-[#F0803C] animate-spin" />
                                            <span className="text-[11px] font-medium text-[#1E2927] dark:text-[#E5EBEA]">
                                                {zh ? `上傳中 ${uploadProgress}%` : `Uploading ${uploadProgress}%`}
                                            </span>
                                        </>
                                    ) : (
                                        <>
                                            <div className="w-9 h-9 rounded-full bg-[#EAE8DE]/80 dark:bg-white/10 flex items-center justify-center text-[#0B3026] dark:text-[#E5EBEA] group-hover:scale-110 transition-transform">
                                                <Camera className="w-4 h-4" />
                                            </div>
                                            <span className="text-[11px] font-semibold text-[#1E2927] dark:text-[#E5EBEA]">
                                                {zh ? "點擊添加拍立得照片" : "Add Polaroid Photo"}
                                            </span>
                                            <span className="text-[9px] text-[#5C6B68] dark:text-[#A2B1AE]">
                                                {zh ? "可選 ｜ 上限 8MB" : "Optional ｜ Max 8MB"}
                                            </span>
                                        </>
                                    )}
                                </div>
                            )}
                        </div>

                        {/* 拍立得底片手寫字樣式 Mood Tag */}
                        <div className="mt-2.5 flex items-center justify-between px-1">
                            <span className="font-serif italic text-xs text-[#1E2927]/80 tracking-wider">
                                {day === 0 ? "Trip Finale" : `Day ${day} Memo`}
                            </span>
                            <span className="text-base sm:text-lg leading-none">{mood}</span>
                        </div>
                    </div>

                    <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={handlePhotoSelect}
                    />

                    {/* 心情選擇列 (12 款精選雙排網格 + 自選 Emoji) */}
                    <div>
                        <div className="flex items-center justify-between mb-2">
                            <label className="text-[11px] font-semibold text-[#5C6B68] dark:text-[#A2B1AE] uppercase tracking-wider">
                                {zh ? "今天的心情代表 Emoji" : "Today's Mood"}
                            </label>
                            <button
                                type="button"
                                onClick={() => {
                                    setIsCustomEmojiOpen(!isCustomEmojiOpen)
                                    haptic.tap()
                                }}
                                className="text-[11px] text-[#E56E25] dark:text-[#F0803C] hover:opacity-80 font-semibold flex items-center gap-1 transition-opacity"
                            >
                                {isCustomEmojiOpen ? (zh ? "關閉自訂" : "Close") : (zh ? "➕ 自選 Emoji" : "➕ Custom")}
                            </button>
                        </div>

                        {/* 自選 Emoji 展開輸入條 */}
                        {isCustomEmojiOpen && (
                            <div className="mb-2.5 p-2 rounded-xl bg-[#EAE8DE]/70 dark:bg-[#121A18] border border-[#E56E25]/40 flex items-center gap-2">
                                <input
                                    type="text"
                                    value={customEmojiInput}
                                    onChange={(e) => setCustomEmojiInput(e.target.value.trim())}
                                    placeholder={zh ? "貼上或輸入任意 Emoji (如 ⛩️, 🍣, 💖)" : "Enter any Emoji..."}
                                    className="flex-1 bg-transparent text-xs text-[#1E2927] dark:text-white placeholder:text-[#5C6B68]/60 dark:placeholder:text-[#A2B1AE]/50 focus:outline-none px-2"
                                    maxLength={4}
                                />
                                <Button
                                    type="button"
                                    size="sm"
                                    onClick={() => {
                                        if (customEmojiInput) {
                                            setMood(customEmojiInput)
                                            haptic.success()
                                            setIsCustomEmojiOpen(false)
                                            setCustomEmojiInput("")
                                        }
                                    }}
                                    className="h-7 px-3 bg-[#E56E25] dark:bg-[#F0803C] hover:opacity-90 text-white font-semibold text-xs rounded-lg shadow-sm"
                                >
                                    {zh ? "套用" : "Apply"}
                                </Button>
                            </div>
                        )}

                        <div className="grid grid-cols-6 gap-1.5 sm:gap-2">
                            {MOOD_EMOJIS.map((m) => (
                                <button
                                    key={m.emoji}
                                    type="button"
                                    onClick={() => {
                                        setMood(m.emoji)
                                        haptic.selection()
                                    }}
                                    className={`py-2 rounded-xl flex flex-col items-center gap-0.5 border transition-all ${
                                        mood === m.emoji
                                            ? "bg-[#E56E25]/15 dark:bg-[#F0803C]/25 border-[#E56E25] dark:border-[#F0803C] text-[#E56E25] dark:text-[#F0803C] scale-105 shadow-sm shadow-[#E56E25]/20 font-bold"
                                            : "bg-[#EAE8DE]/60 dark:bg-[#121A18]/80 border-[#0B3026]/8 dark:border-white/10 text-[#5C6B68] dark:text-[#A2B1AE] hover:bg-[#EAE8DE] dark:hover:bg-[#1F2C29] hover:text-[#1E2927] dark:hover:text-white"
                                    }`}
                                >
                                    <span className="text-base sm:text-lg leading-none">{m.emoji}</span>
                                    <span className="text-[9px] font-medium leading-none mt-1">
                                        {zh ? m.labelZh : m.labelEn}
                                    </span>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* 真心話輸入框 */}
                    <div>
                        <div className="flex items-center justify-between mb-1.5">
                            <label className="text-[11px] font-semibold text-[#5C6B68] dark:text-[#A2B1AE] uppercase tracking-wider">
                                {zh ? "寫給旅伴的真心話 (旅程結束前保密)" : "Note to travelers"}
                            </label>
                            <span
                                className={`text-[10px] tabular-nums font-mono ${
                                    content.length > 480 ? "text-rose-500 font-bold" : "text-[#5C6B68] dark:text-[#A2B1AE]"
                                }`}
                            >
                                {content.length}/500
                            </span>
                        </div>
                        <textarea
                            value={content}
                            onChange={(e) => setContent(e.target.value.slice(0, 500))}
                            placeholder={
                                zh
                                    ? "今天有什麼好笑、感動、或是其實走得很累的真心話？大膽寫下來吧，回國前沒有人看得到～"
                                    : "Write raw reflections, funny moments, or honest feelings for this day..."
                            }
                            rows={4}
                            className="w-full bg-[#EAE8DE]/50 dark:bg-[#121A18] border border-[#0B3026]/10 dark:border-white/10 rounded-2xl p-3.5 text-xs text-[#1E2927] dark:text-[#E5EBEA] placeholder:text-[#5C6B68]/60 dark:placeholder:text-[#A2B1AE]/50 focus:outline-none focus:ring-2 focus:ring-[#E56E25]/50 resize-none transition-all leading-relaxed"
                        />
                    </div>
                </div>

                {/* 底部操作工具列 (Sticky 固定在最底端，絕不截斷) */}
                <div className="shrink-0 sticky bottom-0 bg-[#F6F5EE]/95 dark:bg-[#182320]/95 backdrop-blur border-t border-[#0B3026]/8 dark:border-white/10 p-3.5 sm:p-4 flex items-center gap-2 z-10">
                    <Button
                        variant="ghost"
                        onClick={() => onOpenChange(false)}
                        className="flex-1 text-[#5C6B68] dark:text-[#A2B1AE] hover:text-[#1E2927] dark:hover:text-white hover:bg-[#EAE8DE] dark:hover:bg-white/10 rounded-xl text-xs h-10"
                    >
                        {zh ? "取消" : "Cancel"}
                    </Button>
                    <Button
                        onClick={handleSave}
                        disabled={saving || uploading}
                        className="flex-2 bg-linear-to-r from-[#E56E25] to-[#d85e17] dark:from-[#F0803C] dark:to-[#E56E25] hover:opacity-90 text-white font-bold rounded-xl text-xs h-10 shadow-lg shadow-[#E56E25]/25 transition-all flex items-center justify-center gap-1.5"
                    >
                        {saving ? (
                            <>
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                {zh ? "封存中..." : "Sealing..."}
                            </>
                        ) : (
                            <>
                                <Lock className="w-3.5 h-3.5" />
                                {zh ? "封存進時光膠囊" : "Seal Capsule"}
                            </>
                        )}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    )
}
