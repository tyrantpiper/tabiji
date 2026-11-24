"use client"

import React, { useEffect, useState, useRef, useCallback, useId, useSyncExternalStore } from "react"
import { createPortal } from "react-dom"
import { motion, AnimatePresence, PanInfo, useReducedMotion } from "framer-motion"
import { X, Sparkles, AlertCircle, Wallet, Ticket, CheckSquare } from "lucide-react"
import { cn } from "@/lib/utils"
import { useLanguage } from "@/lib/LanguageContext"
import { useHaptic } from "@/lib/hooks"

export type DashboardSectionTab = "ai_review" | "tips" | "costs" | "tickets" | "checklist"

interface IOSBottomSheetProps {
  isOpen: boolean
  activeTab: DashboardSectionTab
  onClose: () => void
  onTabChange: (tab: DashboardSectionTab) => void
  tabIndicators?: Partial<Record<DashboardSectionTab, boolean>>
  children: React.ReactNode
}

const SPRING_CONFIG = {
  type: "spring",
  stiffness: 380,
  damping: 32,
  mass: 0.8,
} as const

const subscribeNoop = () => () => {}

export default function IOSBottomSheet({
  isOpen,
  activeTab,
  onClose,
  onTabChange,
  tabIndicators,
  children,
}: IOSBottomSheetProps) {
  const { lang } = useLanguage()
  const zh = lang === "zh"
  const haptic = useHaptic()
  const isMounted = useSyncExternalStore(subscribeNoop, () => true, () => false)
  const shouldReduceMotion = Boolean(useReducedMotion())
  const pillLayoutId = useId()
  const dialogTitleId = useId()
  const [detent, setDetent] = useState<"half" | "full">("half")
  const contentScrollRef = useRef<HTMLDivElement>(null)

  const handleDismiss = useCallback(() => {
    setDetent("half")
    onClose()
  }, [onClose])

  // 🛡️ Zero-Leak Body Scroll Lock: 精確記錄並還原原始 overflow
  useEffect(() => {
    if (!isOpen) return
    const originalOverflow = document.body.style.overflow
    const originalTouchAction = document.body.style.touchAction
    document.body.style.overflow = "hidden"
    document.body.style.touchAction = "none"

    return () => {
      document.body.style.overflow = originalOverflow
      document.body.style.touchAction = originalTouchAction
    }
  }, [isOpen])

  // 監聽 ESC 鍵關閉 (若上方有更高層級 Radix Dialog/AlertDialog/Popover 開啟則放行，避免底抽連帶被關)
  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (
          e.defaultPrevented ||
          document.querySelector(
            '[data-slot="dialog-content"][data-state="open"], [data-slot="alert-dialog-content"][data-state="open"], [data-slot="popover-content"][data-state="open"]'
          )
        ) {
          return
        }
        handleDismiss()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [isOpen, handleDismiss])

  // 拖拽釋放判定
  const handleDragEnd = useCallback(
    (_: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => {
      const { offset, velocity } = info

      // 1. 向下拖曳超過 120px 或快速向下甩動 (velocityY > 500) -> 關閉
      if (offset.y > 120 || velocity.y > 500) {
        haptic.tap()
        handleDismiss()
        return
      }

      // 2. 向上拖曳 (offset.y < -50 或 velocity.y < -300) -> 吸附至 full
      if (offset.y < -50 || velocity.y < -300) {
        setDetent("full")
        return
      }

      // 3. 在 full 檔位向下輕拉 (offset.y > 50) -> 回退至 half
      if (detent === "full" && offset.y > 50) {
        setDetent("half")
        return
      }
    },
    [detent, haptic, handleDismiss]
  )

  const tabs: Array<{
    id: DashboardSectionTab
    label: string
    icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>
    activeColorClass: string
    dotColorClass: string
  }> = [
    {
      id: "ai_review",
      label: zh ? "AI 審核" : "AI Review",
      icon: Sparkles,
      activeColorClass: "text-emerald-600 dark:text-emerald-400",
      dotColorClass: "bg-emerald-500 dark:bg-emerald-400",
    },
    {
      id: "tips",
      label: zh ? "重點提醒" : "Tips",
      icon: AlertCircle,
      activeColorClass: "text-amber-600 dark:text-amber-400",
      dotColorClass: "bg-amber-500 dark:bg-amber-400",
    },
    {
      id: "checklist",
      label: zh ? "行前清單" : "Checklist",
      icon: CheckSquare,
      activeColorClass: "text-indigo-600 dark:text-indigo-400",
      dotColorClass: "bg-indigo-500 dark:bg-indigo-400",
    },
    {
      id: "tickets",
      label: zh ? "交通票券" : "Tickets",
      icon: Ticket,
      activeColorClass: "text-sky-600 dark:text-sky-400",
      dotColorClass: "bg-sky-500 dark:bg-sky-400",
    },
    {
      id: "costs",
      label: zh ? "預估花費" : "Costs",
      icon: Wallet,
      activeColorClass: "text-emerald-700 dark:text-emerald-300",
      dotColorClass: "bg-emerald-600 dark:bg-emerald-400",
    },
  ]

  const activeTabMeta = tabs.find((tab) => tab.id === activeTab) ?? tabs[0]

  const handleTabKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, currentIndex: number) => {
    let nextIndex: number | null = null
    if (e.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabs.length
    else if (e.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabs.length) % tabs.length
    else if (e.key === "Home") nextIndex = 0
    else if (e.key === "End") nextIndex = tabs.length - 1

    if (nextIndex !== null) {
      e.preventDefault()
      haptic.selection()
      onTabChange(tabs[nextIndex].id)
      const tablist = e.currentTarget.parentElement
      const nextBtn = tablist?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[nextIndex]
      nextBtn?.focus()
    }
  }

  if (!isMounted) return null

  // 視窗高度映射：half: 55vh, full: 90vh
  const heightClass = detent === "full" ? "h-[90vh]" : "h-[60vh] sm:h-[55vh]"

  const sheetContent = (
    <AnimatePresence mode="wait">
      {isOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby={dialogTitleId}
          className="fixed inset-0 z-115 flex flex-col justify-end"
        >
          {/* 1. Backdrop 遮罩 (高斯模糊背景) */}
          <motion.div
            key="sheet-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: shouldReduceMotion ? 0 : 0.2 }}
            onClick={handleDismiss}
            className="fixed inset-0 bg-black/40 backdrop-blur-md"
            style={{ touchAction: "none" }}
          />

          {/* 2. 底抽主面板 */}
          <motion.div
            key="sheet-panel"
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={shouldReduceMotion ? { duration: 0 } : SPRING_CONFIG}
            className={cn(
              "relative w-full max-w-2xl mx-auto rounded-t-[28px] overflow-hidden flex flex-col",
              "bg-background/95 dark:bg-zinc-900/95 backdrop-blur-2xl",
              "border-t border-white/30 dark:border-white/10 shadow-2xl",
              heightClass,
              "transition-[height] duration-300 ease-out"
            )}
          >
            {/* 3. 頂部觸控把手區域 (Touch Delegation for Dismiss) */}
            <motion.div
              drag="y"
              dragConstraints={{ top: 0, bottom: 0 }}
              dragElastic={{ top: 0, bottom: 0.6 }}
              onDragEnd={handleDragEnd}
              className="w-full pt-2.5 pb-2 px-4 flex flex-col items-center cursor-grab active:cursor-grabbing select-none shrink-0"
            >
              {/* iOS Drag Pill */}
              <div className="w-11 h-1.5 rounded-full bg-muted-foreground/30 hover:bg-muted-foreground/50 transition-colors" />

              {/* 頂部操作列：動態標題、切換檔位指示、關閉按鈕 */}
              <div className="w-full flex items-center justify-between gap-2 mt-1 px-1 min-w-0">
                <span
                  id={dialogTitleId}
                  className="min-w-0 flex-1 truncate text-xs font-medium text-muted-foreground tracking-wider"
                >
                  {zh ? "當日智慧看板" : "Daily Dashboard"}
                  <span aria-hidden="true" className="mx-1.5 opacity-50">·</span>
                  <span className="text-foreground font-semibold">{activeTabMeta.label}</span>
                </span>

                <div className="flex items-center gap-2 shrink-0">
                  {/* 展開/收合檔位按鈕 */}
                  <button
                    type="button"
                    onClick={() => {
                      haptic.selection()
                      setDetent((prev) => (prev === "full" ? "half" : "full"))
                    }}
                    className="text-xs text-foreground/80 hover:text-foreground dark:text-zinc-200 dark:hover:text-white font-medium px-2 py-0.5 rounded-md hover:bg-muted/50 transition-colors touch-manipulation cursor-pointer"
                  >
                    {detent === "full" ? (zh ? "半屏" : "Half") : (zh ? "全屏" : "Full")}
                  </button>

                  {/* 圓形關閉按鈕 */}
                  <button
                    type="button"
                    onClick={() => {
                      haptic.tap()
                      handleDismiss()
                    }}
                    className="w-7 h-7 rounded-full bg-muted/80 hover:bg-muted text-muted-foreground hover:text-foreground flex items-center justify-center transition-colors touch-manipulation cursor-pointer"
                    aria-label={zh ? "關閉" : "Close"}
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </motion.div>

            {/* 4. iOS Pure-Icon Frosted Glass Segmented Capsule (5 等分純圖示毛玻璃膠囊) */}
            <div className="px-4 py-1.5 border-b border-border/40 shrink-0">
              <div
                role="tablist"
                aria-label={zh ? "當日智慧看板分頁" : "Daily dashboard sections"}
                className="grid grid-cols-5 gap-1 p-1 rounded-2xl bg-muted/60 dark:bg-zinc-800/70 backdrop-blur-md border border-border/40 isolate"
              >
                {tabs.map((tab, index) => {
                  const Icon = tab.icon
                  const isActive = activeTabMeta.id === tab.id
                  const hasIndicator = Boolean(tabIndicators?.[tab.id])
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      role="tab"
                      aria-selected={isActive}
                      aria-label={tab.label}
                      title={tab.label}
                      data-tab-id={tab.id}
                      tabIndex={isActive ? 0 : -1}
                      onKeyDown={(e) => handleTabKeyDown(e, index)}
                      onClick={() => {
                        haptic.selection()
                        onTabChange(tab.id)
                      }}
                      className={cn(
                        "relative h-11 min-w-0 rounded-xl flex items-center justify-center transition-colors touch-manipulation cursor-pointer",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50",
                        isActive
                          ? "text-foreground"
                          : "text-muted-foreground hover:text-foreground/80"
                      )}
                    >
                      {isActive && (
                        <motion.span
                          layoutId={pillLayoutId}
                          aria-hidden="true"
                          className="absolute inset-0 z-0 bg-background dark:bg-zinc-700 rounded-xl shadow-xs ring-1 ring-black/5 dark:ring-white/10"
                          transition={shouldReduceMotion ? { duration: 0 } : { type: "spring", stiffness: 450, damping: 35 }}
                        />
                      )}
                      <span className="relative z-10 inline-flex items-center justify-center">
                        <Icon
                          aria-hidden="true"
                          className={cn(
                            "w-5 h-5 transition-colors",
                            isActive ? tab.activeColorClass : "text-muted-foreground"
                          )}
                        />
                        {hasIndicator && (
                          <span
                            data-testid={`tab-indicator-${tab.id}`}
                            aria-hidden="true"
                            className={cn(
                              "absolute -top-0.5 -right-1 w-1.5 h-1.5 rounded-full ring-2",
                              isActive
                                ? "ring-background dark:ring-zinc-700"
                                : "ring-muted/80 dark:ring-zinc-800",
                              tab.dotColorClass
                            )}
                          />
                        )}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* 5. 模組內容展示區 (四重軸鎖 + 流體高度 + iOS 安全區底距，隔離外部 drag) */}
            <div
              ref={contentScrollRef}
              className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden overscroll-x-none overscroll-y-contain touch-pan-y px-4 py-3 pb-[calc(env(safe-area-inset-bottom,0px)+2rem)]"
              style={{ touchAction: "pan-y", WebkitOverflowScrolling: "touch" }}
            >
              {children}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )

  return createPortal(sheetContent, document.body)
}
