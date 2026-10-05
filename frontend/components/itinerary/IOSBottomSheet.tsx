"use client"

import React, { useEffect, useState, useRef, useCallback, useSyncExternalStore } from "react"
import { createPortal } from "react-dom"
import { motion, AnimatePresence, PanInfo } from "framer-motion"
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
  children,
}: IOSBottomSheetProps) {
  const { lang } = useLanguage()
  const zh = lang === "zh"
  const haptic = useHaptic()
  const isMounted = useSyncExternalStore(subscribeNoop, () => true, () => false)
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

  // 監聽 ESC 鍵關閉
  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
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

  const tabs: Array<{ id: DashboardSectionTab; label: string; icon: React.ComponentType<{ className?: string }> }> = [
    { id: "ai_review", label: zh ? "AI 審核" : "AI Review", icon: Sparkles },
    { id: "tips", label: zh ? "重點提醒" : "Tips", icon: AlertCircle },
    { id: "costs", label: zh ? "預估花費" : "Costs", icon: Wallet },
    { id: "tickets", label: zh ? "交通票券" : "Tickets", icon: Ticket },
    { id: "checklist", label: zh ? "行前清單" : "Checklist", icon: CheckSquare },
  ]

  if (!isMounted) return null

  // 視窗高度映射：half: 55vh, full: 90vh
  const heightClass = detent === "full" ? "h-[90vh]" : "h-[60vh] sm:h-[55vh]"

  const sheetContent = (
    <AnimatePresence mode="wait">
      {isOpen && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-100 flex flex-col justify-end"
        >
          {/* 1. Backdrop 遮罩 (高斯模糊背景) */}
          <motion.div
            key="sheet-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
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
            transition={SPRING_CONFIG}
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
              className="w-full pt-2.5 pb-2 px-4 flex flex-col items-center cursor-grab active:cursor-grabbing select-none"
            >
              {/* iOS Drag Pill */}
              <div className="w-11 h-1.5 rounded-full bg-muted-foreground/30 hover:bg-muted-foreground/50 transition-colors" />

              {/* 頂部操作列：標題、切換檔位指示、關閉按鈕 */}
              <div className="w-full flex items-center justify-between mt-1 px-1">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                  {zh ? "當日智慧看板" : "Daily Dashboard"}
                </span>

                <div className="flex items-center gap-2">
                  {/* 展開/收合檔位按鈕 */}
                  <button
                    type="button"
                    onClick={() => {
                      haptic.selection()
                      setDetent((prev) => (prev === "full" ? "half" : "full"))
                    }}
                    className="text-xs text-primary/80 hover:text-primary font-medium px-2 py-0.5 rounded-md hover:bg-muted/50 transition-colors"
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
                    className="w-7 h-7 rounded-full bg-muted/80 hover:bg-muted text-muted-foreground hover:text-foreground flex items-center justify-center transition-colors"
                    aria-label="Close"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </motion.div>

            {/* 4. iOS Segmented Control (分段控制列) */}
            <div className="px-4 py-1.5 border-b border-border/40">
              <div className="flex items-center p-1 bg-muted/50 dark:bg-zinc-800/60 rounded-xl overflow-x-auto no-scrollbar gap-1">
                {tabs.map((tab) => {
                  const Icon = tab.icon
                  const isActive = activeTab === tab.id
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => {
                        haptic.selection()
                        onTabChange(tab.id)
                      }}
                      className={cn(
                        "relative flex-1 min-w-18 py-1.5 px-2 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition-colors whitespace-nowrap",
                        isActive
                          ? "text-foreground font-semibold"
                          : "text-muted-foreground hover:text-foreground/80"
                      )}
                    >
                      {isActive && (
                        <motion.div
                          layoutId="active-segmented-pill"
                          className="absolute inset-0 bg-background dark:bg-zinc-700 rounded-lg shadow-sm"
                          transition={{ type: "spring", stiffness: 450, damping: 35 }}
                        />
                      )}
                      <span className="relative z-10 flex items-center gap-1">
                        <Icon className={cn("w-3.5 h-3.5", isActive ? "text-primary" : "text-muted-foreground")} />
                        {tab.label}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* 5. 模組內容展示區 (可獨立上下滾動，隔離外部 drag) */}
            <div
              ref={contentScrollRef}
              className="flex-1 overflow-y-auto overscroll-contain px-4 py-3 pb-8"
              style={{ WebkitOverflowScrolling: "touch" }}
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
