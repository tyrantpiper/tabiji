"use client"

import React, { useState } from "react"
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from "@/components/ui/dialog"
import {
    CURATED_TRAVEL_EMOJIS,
    THEME_COLOR_PALETTE,
    serializeCustomCategory,
} from "@/lib/poi-category-protocol"
import { cn } from "@/lib/utils"
import { Check, Sparkles } from "lucide-react"

interface CustomCategoryModalProps {
    isOpen: boolean
    onClose: () => void
    onSubmit: (categoryProtocol: string) => void
    initialEmoji?: string
    initialName?: string
    initialColor?: string
}

export function CustomCategoryModal({
    isOpen,
    onClose,
    onSubmit,
    initialEmoji = "🍜",
    initialName = "",
    initialColor = "#E56E25",
}: CustomCategoryModalProps) {
    const [emoji, setEmoji] = useState(initialEmoji)
    const [name, setName] = useState(initialName)
    const [colorHex, setColorHex] = useState(initialColor)
    const [activeGroupIndex, setActiveGroupIndex] = useState(0)

    const handleConfirm = () => {
        const cleanName = name.trim()
        if (!cleanName) return
        const protocol = serializeCustomCategory(emoji, cleanName, colorHex)
        onSubmit(protocol)
        onClose()
    }

    return (
        <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
            <DialogContent className="max-w-md w-[92vw] sm:w-full p-5 sm:p-6 rounded-3xl bg-white/95 dark:bg-[#1A2624]/95 backdrop-blur-xl border border-black/10 dark:border-white/10 shadow-2xl">
                <DialogHeader className="space-y-1 text-left">
                    <DialogTitle className="text-base sm:text-lg font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                        <Sparkles className="w-4 h-4 text-[#E56E25]" />
                        <span>自訂地點類別</span>
                    </DialogTitle>
                    <DialogDescription className="text-xs text-slate-500 dark:text-slate-400">
                        挑選專屬表情符號、類別名稱與主題色彩，打造個人化旅遊標籤
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 pt-2">
                    {/* 🎨 即時效果預覽 Live Preview Badge */}
                    <div className="p-3 rounded-2xl bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/5 flex items-center justify-between">
                        <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">
                            預覽效果
                        </span>
                        <div
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border font-bold text-xs shadow-2xs transition-all"
                            style={{
                                backgroundColor: `${colorHex}18`,
                                borderColor: `${colorHex}40`,
                                color: colorHex,
                            }}
                        >
                            <span className="text-sm leading-none">{emoji || "📍"}</span>
                            <span>{name.trim() || "類別名稱"}</span>
                        </div>
                    </div>

                    {/* 🔤 類別名稱輸入框 */}
                    <div className="space-y-1.5 text-left">
                        <label className="text-xs font-bold text-slate-700 dark:text-slate-300">
                            類別名稱 <span className="text-red-500">*</span>
                        </label>
                        <div className="relative">
                            <input
                                type="text"
                                maxLength={10}
                                value={name}
                                onChange={(e) => {
                                    // 🛡️ 冒號轉義過濾，最長 10 個字元
                                    const val = e.target.value.replaceAll(":", "")
                                    setName(val)
                                }}
                                onKeyDown={(e) => {
                                    if (e.key === "Enter" && name.trim()) {
                                        handleConfirm()
                                    }
                                }}
                                placeholder="例如：拉麵、扭蛋、拍照景點"
                                className="w-full px-3.5 py-2.5 rounded-xl bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 text-sm font-medium text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-[#E56E25]/30 focus:border-[#E56E25] transition-all"
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-slate-400 font-mono">
                                {name.length}/10
                            </span>
                        </div>
                    </div>

                    {/* 🌈 主題色票選擇器 */}
                    <div className="space-y-1.5 text-left">
                        <label className="text-xs font-bold text-slate-700 dark:text-slate-300">
                            主題色票
                        </label>
                        <div className="grid grid-cols-8 gap-2">
                            {THEME_COLOR_PALETTE.map((pal) => {
                                const isSelected = colorHex.toLowerCase() === pal.hex.toLowerCase()
                                return (
                                    <button
                                        key={pal.hex}
                                        type="button"
                                        onClick={() => setColorHex(pal.hex)}
                                        title={pal.name}
                                        className={cn(
                                            "w-7 h-7 sm:w-8 sm:h-8 rounded-full flex items-center justify-center transition-all cursor-pointer relative",
                                            isSelected ? "scale-110 ring-2 ring-offset-2 ring-offset-white dark:ring-offset-[#1A2624] ring-slate-800 dark:ring-slate-100" : "hover:scale-105 opacity-80 hover:opacity-100"
                                        )}
                                        style={{ backgroundColor: pal.hex }}
                                    >
                                        {isSelected && <Check className="w-3.5 h-3.5 text-white stroke-3" />}
                                    </button>
                                )
                            })}
                        </div>
                    </div>

                    {/* 😃 Emoji 選擇區（自訂輸入 ＋ 快捷網格） */}
                    <div className="space-y-2 text-left">
                        <div className="flex items-center justify-between">
                            <label className="text-xs font-bold text-slate-700 dark:text-slate-300">
                                表情符號圖示
                            </label>
                            {/* 自由輸入槽 */}
                            <div className="flex items-center gap-1">
                                <span className="text-[11px] text-slate-400">鍵盤輸入：</span>
                                <input
                                    type="text"
                                    maxLength={2}
                                    value={emoji}
                                    onChange={(e) => {
                                        const char = Array.from(e.target.value).slice(-1)[0] || "📍"
                                        setEmoji(char)
                                    }}
                                    className="w-8 h-7 text-center rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-sm focus:outline-hidden focus:ring-1 focus:ring-[#E56E25]"
                                />
                            </div>
                        </div>

                        {/* 分類切換 Tabs */}
                        <div className="flex gap-1 border-b border-black/5 dark:border-white/5 pb-1 overflow-x-auto no-scrollbar">
                            {CURATED_TRAVEL_EMOJIS.map((grp, idx) => (
                                <button
                                    key={grp.group}
                                    type="button"
                                    onClick={() => setActiveGroupIndex(idx)}
                                    className={cn(
                                        "px-2.5 py-1 rounded-lg text-xs font-semibold whitespace-nowrap transition-all cursor-pointer",
                                        activeGroupIndex === idx
                                            ? "bg-[#E56E25]/10 text-[#E56E25] font-bold"
                                            : "text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
                                    )}
                                >
                                    {grp.group}
                                </button>
                            ))}
                        </div>

                        {/* 精選 Emoji 網格 */}
                        <div className="grid grid-cols-8 gap-1.5 max-h-32 overflow-y-auto p-1 rounded-xl bg-slate-50/50 dark:bg-slate-900/40 border border-slate-200/50 dark:border-slate-800/50">
                            {CURATED_TRAVEL_EMOJIS[activeGroupIndex]?.emojis.map((em) => {
                                const isSelected = emoji === em
                                return (
                                    <button
                                        key={em}
                                        type="button"
                                        onClick={() => setEmoji(em)}
                                        className={cn(
                                            "w-8 h-8 rounded-lg flex items-center justify-center text-lg hover:bg-black/5 dark:hover:bg-white/10 transition-all cursor-pointer",
                                            isSelected ? "bg-amber-500/20 scale-110 ring-1 ring-[#E56E25]" : ""
                                        )}
                                    >
                                        {em}
                                    </button>
                                )
                            })}
                        </div>
                    </div>
                </div>

                {/* 底部操作按鈕 */}
                <div className="flex items-center justify-end gap-2 pt-2 border-t border-black/5 dark:border-white/5">
                    <button
                        type="button"
                        onClick={onClose}
                        className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-black/5 dark:hover:bg-white/5 transition-all cursor-pointer"
                    >
                        取消
                    </button>
                    <button
                        type="button"
                        onClick={handleConfirm}
                        disabled={!name.trim()}
                        className="px-5 py-2 rounded-xl text-xs font-bold bg-[#E56E25] text-white hover:bg-[#c95a1a] active:scale-95 transition-all shadow-md disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                    >
                        確定套用
                    </button>
                </div>
            </DialogContent>
        </Dialog>
    )
}
