"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { AnimatePresence, motion, useReducedMotion } from "framer-motion"
import {
    ArrowUp,
    Camera,
    Coffee,
    Compass,
    Image as ImageIcon,
    Loader2,
    Pill,
    Plus,
    Square,
    Telescope,
    Utensils,
    X,
} from "lucide-react"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useLanguage, type TranslationKey } from "@/lib/LanguageContext"
import { isImageFile } from "@/lib/image-utils"
import { cn } from "@/lib/utils"

export interface ChatComposerProps {
    input: string
    onInputChange: (value: string) => void
    onSend: () => void
    onStop: () => void
    isLoading: boolean
    isDeepResearch: boolean
    onToggleDeepResearch: (next: boolean) => void
    selectedImage: string | null
    imagePreviewError: boolean
    isCompressingImage: boolean
    onImageFileSelect: (file: File) => void
    onImagePreviewError: () => void
    onRemoveImage: () => void
    textareaRef: React.RefObject<HTMLTextAreaElement | null>
    menuOpen?: boolean
    onMenuOpenChange?: (open: boolean) => void
    isHidden?: boolean
}

interface QuickChipItem {
    id: string
    labelKey: TranslationKey
    promptKey: TranslationKey
    icon: typeof Compass
    accent?: boolean
}

const QUICK_CHIPS: readonly QuickChipItem[] = [
    {
        id: "explore",
        labelKey: "ai_chip_explore_label",
        promptKey: "ai_chip_explore_prompt",
        icon: Compass,
        accent: true,
    },
    {
        id: "ramen",
        labelKey: "ai_chip_ramen_label",
        promptKey: "ai_chip_ramen_prompt",
        icon: Utensils,
    },
    {
        id: "pharmacy",
        labelKey: "ai_chip_pharmacy_label",
        promptKey: "ai_chip_pharmacy_prompt",
        icon: Pill,
    },
    {
        id: "cafe",
        labelKey: "ai_chip_cafe_label",
        promptKey: "ai_chip_cafe_prompt",
        icon: Coffee,
    },
] as const

function triggerSubtleHaptic(): void {
    try {
        if (typeof navigator !== "undefined" && typeof navigator.vibrate === "function") {
            navigator.vibrate(10)
        }
    } catch {
        // Ignore restricted or unsupported vibration environments
    }
}

function extractImageFileFromClipboard(clipboardData: DataTransfer | null | undefined): File | null {
    if (!clipboardData) return null
    const plainText =
        typeof clipboardData.getData === "function"
            ? clipboardData.getData("text/plain")
            : ""
    if (plainText && plainText.trim().length > 0) {
        return null
    }

    if (clipboardData.items && clipboardData.items.length > 0) {
        for (let i = 0; i < clipboardData.items.length; i += 1) {
            const item = clipboardData.items[i]
            if (item && item.kind === "file") {
                const file = typeof item.getAsFile === "function" ? item.getAsFile() : null
                if (file && isImageFile(file)) {
                    return file
                }
            }
        }
    }

    if (clipboardData.files && clipboardData.files.length > 0) {
        for (let i = 0; i < clipboardData.files.length; i += 1) {
            const file = clipboardData.files[i]
            if (file && isImageFile(file)) {
                return file
            }
        }
    }

    return null
}

function hasFileTransferType(dataTransfer: DataTransfer | null | undefined): boolean {
    if (!dataTransfer?.types) return false
    return Array.from(dataTransfer.types).includes("Files")
}

export default function ChatComposer({
    input,
    onInputChange,
    onSend,
    onStop,
    isLoading,
    isDeepResearch,
    onToggleDeepResearch,
    selectedImage,
    imagePreviewError,
    isCompressingImage,
    onImageFileSelect,
    onImagePreviewError,
    onRemoveImage,
    textareaRef,
    menuOpen: controlledMenuOpen,
    onMenuOpenChange,
    isHidden = false,
}: ChatComposerProps) {
    const { t } = useLanguage()
    const shouldReduceMotion = Boolean(useReducedMotion())

    const [internalMenuOpen, setInternalMenuOpen] = useState(false)
    const [isFileDragOver, setIsFileDragOver] = useState(false)

    const menuOpen = (controlledMenuOpen ?? internalMenuOpen) && !isHidden
    const setMenuOpen = useCallback(
        (next: boolean) => {
            setInternalMenuOpen(next)
            onMenuOpenChange?.(next)
        },
        [onMenuOpenChange]
    )

    const photoInputRef = useRef<HTMLInputElement>(null)
    const cameraInputRef = useRef<HTMLInputElement>(null)
    const closeFocusTargetRef = useRef<"trigger" | "textarea" | "none">("trigger")

    const deepResearchBlocked = Boolean(selectedImage) || isCompressingImage
    const canSend = Boolean(input.trim() || selectedImage) && !isCompressingImage && !isLoading
    const showQuickChips =
        !input.trim() &&
        !selectedImage &&
        !isCompressingImage &&
        !isDeepResearch &&
        !isLoading

    // Synchronize textarea auto-grow whenever input or visibility changes (typing, quick chips, retry, undock, or send clear)
    useEffect(() => {
        if (isHidden) return
        const el = textareaRef.current
        if (!el) return
        el.style.height = "auto"
        if (input && el.scrollHeight > 0) {
            el.style.height = `${Math.min(el.scrollHeight, 128)}px`
        }
    }, [input, isHidden, textareaRef])

    const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        e.target.value = ""
        if (file) {
            onImageFileSelect(file)
        }
    }

    const handleUploadPhotoClick = () => {
        if (isCompressingImage) return
        triggerSubtleHaptic()
        closeFocusTargetRef.current = "none"
        // Synchronous click preserves iOS Safari transient user activation
        photoInputRef.current?.click()
        setMenuOpen(false)
    }

    const handleTakePhotoClick = () => {
        if (isCompressingImage) return
        triggerSubtleHaptic()
        closeFocusTargetRef.current = "none"
        cameraInputRef.current?.click()
        setMenuOpen(false)
    }

    const handleDeepResearchMenuClick = () => {
        if (deepResearchBlocked) return
        triggerSubtleHaptic()
        closeFocusTargetRef.current = "textarea"
        onToggleDeepResearch(!isDeepResearch)
        setMenuOpen(false)
    }

    const handlePopoverCloseAutoFocus = (e: Event) => {
        const target = closeFocusTargetRef.current
        closeFocusTargetRef.current = "trigger"
        if (target === "textarea") {
            e.preventDefault()
            textareaRef.current?.focus()
        } else if (target === "none") {
            e.preventDefault()
        }
    }

    const handleQuickChipClick = (prompt: string) => {
        triggerSubtleHaptic()
        onInputChange(prompt)
        textareaRef.current?.focus()
    }

    const handleTextareaPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
        if (isCompressingImage) return
        const imageFile = extractImageFileFromClipboard(e.clipboardData)
        if (imageFile) {
            e.preventDefault()
            onImageFileSelect(imageFile)
        }
    }

    const handleCardDragEnter = (e: React.DragEvent<HTMLDivElement>) => {
        if (!hasFileTransferType(e.dataTransfer)) return
        e.preventDefault()
        if (isCompressingImage) return
        setIsFileDragOver(true)
    }

    const handleCardDragOver = (e: React.DragEvent<HTMLDivElement>) => {
        if (!hasFileTransferType(e.dataTransfer)) return
        e.preventDefault()
        if (isCompressingImage) {
            e.dataTransfer.dropEffect = "none"
            if (isFileDragOver) {
                setIsFileDragOver(false)
            }
            return
        }
        e.dataTransfer.dropEffect = "copy"
        if (!isFileDragOver) {
            setIsFileDragOver(true)
        }
    }

    const handleCardDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
            setIsFileDragOver(false)
        }
    }

    const handleCardDrop = (e: React.DragEvent<HTMLDivElement>) => {
        if (!hasFileTransferType(e.dataTransfer)) return
        e.preventDefault()
        setIsFileDragOver(false)
        if (isCompressingImage) return
        const droppedFile = e.dataTransfer.files?.[0]
        if (droppedFile) {
            onImageFileSelect(droppedFile)
        }
    }

    return (
        <div className="p-3 md:p-4 bg-tabiji-paper/95 dark:bg-tabiji-dark/95 border-t border-tabiji-forest/10 dark:border-white/10 shrink-0 pb-[max(0.75rem,env(safe-area-inset-bottom))] w-full max-w-full min-w-0">
            {/* Hidden file inputs — Sentinel Lock: standard album input MUST remain first in DOM */}
            <input
                ref={photoInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                aria-hidden="true"
                tabIndex={-1}
                onChange={handleFileInputChange}
            />
            <input
                ref={cameraInputRef}
                type="file"
                accept="image/*"
                capture="environment"
                className="hidden"
                aria-hidden="true"
                tabIndex={-1}
                onChange={handleFileInputChange}
            />

            {/* Smart-collapsing exploration chips */}
            <AnimatePresence initial={false}>
                {showQuickChips && (
                    <motion.div
                        key="composer-quick-chips"
                        initial={shouldReduceMotion ? { opacity: 1 } : { opacity: 0, maxHeight: 0 }}
                        animate={shouldReduceMotion ? { opacity: 1 } : { opacity: 1, maxHeight: 96 }}
                        exit={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, maxHeight: 0 }}
                        transition={shouldReduceMotion ? { duration: 0 } : { duration: 0.16, ease: "easeOut" }}
                        className="overflow-hidden w-full max-w-full min-w-0"
                    >
                        <div
                            className="flex items-center gap-1.5 overflow-x-auto overscroll-x-contain pb-2 scrollbar-none select-none text-xs w-full max-w-full min-w-0"
                            style={{ touchAction: "pan-x" }}
                        >
                            {QUICK_CHIPS.map((chip) => {
                                const Icon = chip.icon
                                return (
                                    <button
                                        key={chip.id}
                                        type="button"
                                        onClick={() => handleQuickChipClick(t(chip.promptKey))}
                                        className={cn(
                                            "shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 min-h-8 rounded-full border transition-colors active:scale-95 shadow-2xs cursor-pointer touch-manipulation focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tabiji-forest/35 dark:focus-visible:ring-emerald-400/45",
                                            chip.accent
                                                ? "bg-white dark:bg-white/10 text-tabiji-forest dark:text-emerald-300 border-tabiji-forest/18 dark:border-emerald-400/25 hover:bg-tabiji-forest/5 dark:hover:bg-white/15 font-medium"
                                                : "bg-white dark:bg-white/8 text-tabiji-charcoal dark:text-tabiji-paper border-tabiji-forest/12 dark:border-white/14 hover:bg-tabiji-forest/5 dark:hover:bg-white/14"
                                        )}
                                    >
                                        <Icon className="w-3.5 h-3.5 shrink-0 opacity-85" aria-hidden="true" />
                                        <span className="truncate">{t(chip.labelKey)}</span>
                                    </button>
                                )
                            })}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Two-Zone Unified Composer Card */}
            <div
                onDragEnter={handleCardDragEnter}
                onDragOver={handleCardDragOver}
                onDragLeave={handleCardDragLeave}
                onDrop={handleCardDrop}
                className={cn(
                    "w-full max-w-full min-w-0 rounded-[24px] border transition-all duration-200",
                    isDeepResearch
                        ? "border-tabiji-forest/40 ring-2 ring-tabiji-forest/12 bg-linear-to-b from-emerald-50/40 to-white dark:border-emerald-400/40 dark:ring-emerald-400/15 dark:from-emerald-950/35 dark:to-[#182320] shadow-[0_2px_14px_rgba(11,48,38,0.1)] dark:shadow-[0_2px_16px_rgba(0,0,0,0.4)] focus-within:border-tabiji-forest/55 focus-within:ring-tabiji-forest/20 dark:focus-within:border-emerald-400/55 dark:focus-within:ring-emerald-400/25"
                        : "bg-white dark:bg-[#182320] border-tabiji-forest/12 dark:border-white/12 shadow-[0_2px_12px_rgba(11,48,38,0.06)] dark:shadow-[0_2px_14px_rgba(0,0,0,0.35)] focus-within:border-tabiji-forest/35 focus-within:ring-2 focus-within:ring-tabiji-forest/10 dark:focus-within:border-emerald-400/35 dark:focus-within:ring-emerald-400/12",
                    isFileDragOver && !isCompressingImage && "border-tabiji-forest/55 ring-2 ring-tabiji-forest/20 dark:border-emerald-400/55 dark:ring-emerald-400/20"
                )}
            >
                {/* Zone 1: Optional Attachment Slot + Full-Width Borderless Auto-Grow Textarea */}
                <div className="px-3.5 pt-3 pb-1.5 min-w-0">
                    {(isCompressingImage || selectedImage) && (
                        <div className="mb-2.5 flex flex-wrap items-center gap-2">
                            {selectedImage && (
                                <div className="relative inline-block">
                                    {imagePreviewError ? (
                                        <div className="h-16 px-3 rounded-xl border border-emerald-200 dark:border-emerald-800 bg-emerald-50/70 dark:bg-emerald-950/40 flex items-center gap-2 text-xs text-emerald-800 dark:text-emerald-200">
                                            <ImageIcon className="w-4 h-4 shrink-0" aria-hidden="true" />
                                            <span className="truncate">{t("ai_composer_heic_ready")}</span>
                                        </div>
                                    ) : (
                                        /* eslint-disable-next-line @next/next/no-img-element */
                                        <img
                                            src={selectedImage}
                                            alt="Selected"
                                            onError={onImagePreviewError}
                                            className="h-16 w-auto max-w-36 object-cover rounded-xl border border-tabiji-forest/15 dark:border-white/15 shadow-2xs"
                                        />
                                    )}
                                    <button
                                        type="button"
                                        onClick={() => {
                                            triggerSubtleHaptic()
                                            onRemoveImage()
                                        }}
                                        aria-label={t("ai_composer_remove_image")}
                                        title={t("ai_composer_remove_image")}
                                        className="absolute -top-2 -right-2 h-6 w-6 rounded-full bg-tabiji-charcoal/90 hover:bg-tabiji-charcoal dark:bg-tabiji-paper dark:hover:bg-tabiji-paper/90 text-white dark:text-tabiji-dark flex items-center justify-center shadow-sm transition-transform active:scale-95 cursor-pointer touch-manipulation focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tabiji-forest/40 dark:focus-visible:ring-emerald-400/50"
                                    >
                                        <X className="w-3.5 h-3.5" aria-hidden="true" />
                                    </button>
                                </div>
                            )}

                            {isCompressingImage && (
                                <div
                                    role="status"
                                    aria-live="polite"
                                    className="inline-flex items-center gap-2 h-10 px-3 rounded-xl bg-tabiji-mist/60 dark:bg-white/8 border border-tabiji-forest/12 dark:border-white/12 text-xs text-tabiji-forest dark:text-tabiji-paper"
                                >
                                    <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0 text-tabiji-forest dark:text-emerald-400" aria-hidden="true" />
                                    <span className="truncate">{t("ai_composer_compressing_image")}</span>
                                </div>
                            )}
                        </div>
                    )}

                    <textarea
                        ref={textareaRef}
                        rows={1}
                        placeholder={
                            isDeepResearch
                                ? t("ai_composer_deep_research_placeholder")
                                : t("ai_ask_placeholder")
                        }
                        className="block w-full min-h-10 max-h-32 resize-none bg-transparent border-0 p-0 text-sm text-tabiji-charcoal dark:text-tabiji-paper placeholder:text-tabiji-slate/85 dark:placeholder:text-tabiji-slate focus:outline-hidden leading-relaxed"
                        value={input}
                        onChange={(e) => onInputChange(e.target.value)}
                        onPaste={handleTextareaPaste}
                        onKeyDown={(e) => {
                            if (e.nativeEvent.isComposing) return
                            if (e.key === "Enter" && !e.shiftKey) {
                                e.preventDefault()
                                if (canSend) {
                                    onSend()
                                }
                            }
                        }}
                    />
                </div>

                {/* Zone 2: Clean Action Toolbar (Left: + & Mode Pill | Right: Send <-> Stop) */}
                <div className="flex items-center justify-between gap-2 px-2.5 pb-2.5 pt-1 min-w-0">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                        <Popover open={menuOpen} onOpenChange={setMenuOpen}>
                            <PopoverTrigger asChild>
                                <button
                                    type="button"
                                    aria-label={t("ai_composer_more_actions")}
                                    aria-expanded={menuOpen}
                                    title={t("ai_composer_more_actions")}
                                    onClick={() => triggerSubtleHaptic()}
                                    className={cn(
                                        "h-10 w-10 min-h-10 min-w-10 shrink-0 rounded-full flex items-center justify-center transition-colors active:scale-95 cursor-pointer touch-manipulation select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tabiji-forest/40 dark:focus-visible:ring-emerald-400/50 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-[#182320]",
                                        menuOpen
                                            ? "bg-tabiji-forest/14 text-tabiji-forest dark:bg-white/16 dark:text-tabiji-paper"
                                            : "bg-tabiji-mist/70 hover:bg-tabiji-mist text-tabiji-forest dark:bg-white/8 dark:hover:bg-white/14 dark:text-tabiji-paper"
                                    )}
                                >
                                    <motion.span
                                        aria-hidden="true"
                                        animate={{ rotate: menuOpen ? 45 : 0 }}
                                        transition={
                                            shouldReduceMotion
                                                ? { duration: 0 }
                                                : { type: "spring", stiffness: 420, damping: 28 }
                                        }
                                        className="inline-flex items-center justify-center"
                                    >
                                        <Plus className="w-5 h-5" strokeWidth={2.2} />
                                    </motion.span>
                                </button>
                            </PopoverTrigger>

                            <PopoverContent
                                side="top"
                                align="start"
                                sideOffset={10}
                                collisionPadding={12}
                                onCloseAutoFocus={handlePopoverCloseAutoFocus}
                                className="w-[min(17rem,calc(100vw-2rem))] p-1.5 rounded-2xl bg-white/95 dark:bg-[#182320]/95 backdrop-blur-xl border border-tabiji-forest/12 dark:border-white/12 shadow-[0_12px_36px_rgba(11,48,38,0.14)] dark:shadow-[0_12px_36px_rgba(0,0,0,0.55)] text-tabiji-charcoal dark:text-tabiji-paper"
                            >
                                <div className="flex flex-col gap-0.5">
                                    {/* Media Input Group */}
                                    <button
                                        type="button"
                                        disabled={isCompressingImage}
                                        onClick={handleUploadPhotoClick}
                                        className="w-full min-h-11 px-2.5 py-2 rounded-xl flex items-center gap-3 text-left transition-colors hover:bg-tabiji-mist/70 dark:hover:bg-white/8 active:scale-[0.99] cursor-pointer touch-manipulation disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tabiji-forest/35 dark:focus-visible:ring-emerald-400/45"
                                    >
                                        <span className="h-8 w-8 rounded-lg bg-tabiji-mist/80 dark:bg-white/10 text-tabiji-forest dark:text-tabiji-paper flex items-center justify-center shrink-0">
                                            <ImageIcon className="w-4 h-4" aria-hidden="true" />
                                        </span>
                                        <span className="min-w-0 flex-1">
                                            <span className="block truncate text-sm font-medium text-tabiji-charcoal dark:text-tabiji-paper">
                                                {t("ai_composer_upload_photo")}
                                            </span>
                                            <span className="block truncate text-[11px] text-tabiji-slate">
                                                {t("ai_composer_upload_photo_desc")}
                                            </span>
                                        </span>
                                    </button>

                                    <button
                                        type="button"
                                        disabled={isCompressingImage}
                                        onClick={handleTakePhotoClick}
                                        className="w-full min-h-11 px-2.5 py-2 rounded-xl flex items-center gap-3 text-left transition-colors hover:bg-tabiji-mist/70 dark:hover:bg-white/8 active:scale-[0.99] cursor-pointer touch-manipulation disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tabiji-forest/35 dark:focus-visible:ring-emerald-400/45"
                                    >
                                        <span className="h-8 w-8 rounded-lg bg-tabiji-mist/80 dark:bg-white/10 text-tabiji-forest dark:text-tabiji-paper flex items-center justify-center shrink-0">
                                            <Camera className="w-4 h-4" aria-hidden="true" />
                                        </span>
                                        <span className="min-w-0 flex-1">
                                            <span className="block truncate text-sm font-medium text-tabiji-charcoal dark:text-tabiji-paper">
                                                {t("ai_composer_take_photo")}
                                            </span>
                                            <span className="block truncate text-[11px] text-tabiji-slate">
                                                {t("ai_composer_take_photo_desc")}
                                            </span>
                                        </span>
                                    </button>

                                    <div
                                        role="separator"
                                        className="my-1 mx-2 h-px bg-tabiji-forest/10 dark:bg-white/10"
                                    />

                                    {/* AI Mode Group */}
                                    <button
                                        type="button"
                                        disabled={deepResearchBlocked}
                                        aria-pressed={isDeepResearch}
                                        onClick={handleDeepResearchMenuClick}
                                        className={cn(
                                            "w-full min-h-11 px-2.5 py-2 rounded-xl flex items-center gap-3 text-left transition-colors touch-manipulation focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tabiji-forest/35 dark:focus-visible:ring-emerald-400/45",
                                            deepResearchBlocked
                                                ? "opacity-50 cursor-not-allowed"
                                                : isDeepResearch
                                                    ? "bg-tabiji-forest/8 dark:bg-emerald-500/12 hover:bg-tabiji-forest/12 dark:hover:bg-emerald-500/18 cursor-pointer active:scale-[0.99]"
                                                    : "hover:bg-tabiji-mist/70 dark:hover:bg-white/8 cursor-pointer active:scale-[0.99]"
                                        )}
                                    >
                                        <span
                                            className={cn(
                                                "h-8 w-8 rounded-lg flex items-center justify-center shrink-0 transition-colors",
                                                isDeepResearch && !deepResearchBlocked
                                                    ? "bg-tabiji-forest text-tabiji-paper dark:bg-emerald-500/25 dark:text-emerald-300"
                                                    : "bg-tabiji-mist/80 dark:bg-white/10 text-tabiji-forest dark:text-tabiji-paper"
                                            )}
                                        >
                                            <Telescope className="w-4 h-4" aria-hidden="true" />
                                        </span>
                                        <span className="min-w-0 flex-1">
                                            <span className="block truncate text-sm font-medium text-tabiji-charcoal dark:text-tabiji-paper">
                                                {t("ai_composer_deep_research")}
                                            </span>
                                            <span className="block truncate text-[11px] text-tabiji-slate">
                                                {deepResearchBlocked
                                                    ? t("ai_composer_deep_research_disabled_img")
                                                    : t("ai_composer_deep_research_desc")}
                                            </span>
                                        </span>
                                        {/* Purely visual toggle pill indicator (no nested button) */}
                                        <span
                                            aria-hidden="true"
                                            className={cn(
                                                "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full p-0.5 transition-colors",
                                                isDeepResearch && !deepResearchBlocked
                                                    ? "bg-tabiji-forest dark:bg-emerald-500"
                                                    : "bg-tabiji-forest/15 dark:bg-white/15"
                                            )}
                                        >
                                            <span
                                                className={cn(
                                                    "inline-block h-4 w-4 rounded-full bg-white shadow-xs transition-transform",
                                                    isDeepResearch && !deepResearchBlocked
                                                        ? "translate-x-4"
                                                        : "translate-x-0"
                                                )}
                                            />
                                        </span>
                                    </button>
                                </div>
                            </PopoverContent>
                        </Popover>

                        {/* Active Deep Research Shimmer Pill (single non-nested dismiss button) */}
                        <AnimatePresence initial={false}>
                            {isDeepResearch && (
                                <motion.button
                                    key="deep-research-pill"
                                    type="button"
                                    initial={shouldReduceMotion ? { opacity: 1 } : { opacity: 0, scale: 0.92, x: -6 }}
                                    animate={shouldReduceMotion ? { opacity: 1 } : { opacity: 1, scale: 1, x: 0 }}
                                    exit={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.92, x: -6 }}
                                    transition={shouldReduceMotion ? { duration: 0 } : { duration: 0.14, ease: "easeOut" }}
                                    aria-label={t("ai_composer_remove_mode")}
                                    title={t("ai_composer_remove_mode")}
                                    onClick={() => {
                                        triggerSubtleHaptic()
                                        onToggleDeepResearch(false)
                                        textareaRef.current?.focus()
                                    }}
                                    className="inline-flex items-center gap-1.5 h-9 max-w-[11rem] sm:max-w-xs px-3 rounded-full text-xs font-medium bg-tabiji-forest/10 hover:bg-tabiji-forest/16 text-tabiji-forest border border-tabiji-forest/20 dark:bg-emerald-500/15 dark:hover:bg-emerald-500/22 dark:text-emerald-300 dark:border-emerald-400/25 transition-colors active:scale-95 cursor-pointer touch-manipulation select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tabiji-forest/40 dark:focus-visible:ring-emerald-400/50"
                                >
                                    <Telescope className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                                    <span className="truncate">{t("ai_composer_deep_research")}</span>
                                    <X className="w-3.5 h-3.5 shrink-0 opacity-75" aria-hidden="true" />
                                </motion.button>
                            )}
                        </AnimatePresence>
                    </div>

                    {/* Right Primary Action: Send <-> Stop Morph */}
                    {isLoading ? (
                        <button
                            type="button"
                            onClick={() => {
                                triggerSubtleHaptic()
                                onStop()
                            }}
                            aria-label={t("ai_stop")}
                            title={t("ai_stop")}
                            className="h-10 w-10 min-h-10 min-w-10 shrink-0 rounded-full flex items-center justify-center bg-tabiji-charcoal hover:bg-tabiji-charcoal/90 text-white dark:bg-tabiji-paper dark:hover:bg-tabiji-paper/90 dark:text-tabiji-dark shadow-xs transition-all active:scale-95 cursor-pointer touch-manipulation select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tabiji-forest/40 dark:focus-visible:ring-emerald-400/50 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-[#182320]"
                        >
                            <Square className="w-3.5 h-3.5 fill-current" aria-hidden="true" />
                        </button>
                    ) : (
                        <button
                            type="button"
                            disabled={!canSend}
                            onClick={() => {
                                if (!canSend) return
                                triggerSubtleHaptic()
                                onSend()
                            }}
                            aria-label={t("ai_composer_send")}
                            title={t("ai_composer_send")}
                            className={cn(
                                "h-10 w-10 min-h-10 min-w-10 shrink-0 rounded-full flex items-center justify-center transition-all touch-manipulation select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tabiji-forest/40 dark:focus-visible:ring-emerald-400/50 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-[#182320]",
                                canSend
                                    ? "bg-tabiji-forest hover:bg-tabiji-forest/90 text-tabiji-paper dark:bg-emerald-600 dark:hover:bg-emerald-500 dark:text-white shadow-xs cursor-pointer active:scale-95"
                                    : "bg-tabiji-forest/12 text-tabiji-slate/50 dark:bg-white/8 dark:text-white/30 cursor-not-allowed"
                            )}
                        >
                            <ArrowUp className="w-5 h-5" strokeWidth={2.4} aria-hidden="true" />
                        </button>
                    )}
                </div>
            </div>
        </div>
    )
}
