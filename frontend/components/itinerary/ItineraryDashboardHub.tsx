"use client"

import React, { useMemo } from "react"
import { motion } from "framer-motion"
import {
  Sparkles,
  AlertCircle,
  AlertTriangle,
  Wallet,
  Ticket,
  CheckSquare,
  ChevronRight,
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  Lock,
  Compass
} from "lucide-react"
import { cn } from "@/lib/utils"
import { useLanguage } from "@/lib/LanguageContext"
import { useHaptic } from "@/lib/hooks"
import { DashboardSectionTab } from "./IOSBottomSheet"
import { CapsuleProgressSummary } from "@/lib/itinerary-types"
import {
  calculateDayCostsSummary,
  calculateChecklistProgress,
  extractAIReviewHighlights
} from "@/lib/itinerary-metrics"

interface NoteItem {
  icon?: string
  title: string
  content: string
}

interface CostItem {
  item: string
  amount: string
  currency?: string
  note?: string
}

interface TicketItem {
  name: string
  price: string
  currency?: string
  note?: string
}

interface ItineraryDashboardHubProps {
  day: number
  review?: string
  notes?: NoteItem[]
  costs?: CostItem[]
  tickets?: TicketItem[]
  dayChecklists?: unknown
  defaultCurrency?: string
  isSample?: boolean
  capsuleSummary?: CapsuleProgressSummary | null
  onCapsuleClick?: () => void
  onSelectTab: (tab: DashboardSectionTab) => void
}

export default function ItineraryDashboardHub({
  day,
  review,
  notes = [],
  costs = [],
  tickets = [],
  dayChecklists,
  defaultCurrency = "JPY",
  isSample = false,
  capsuleSummary,
  onCapsuleClick,
  onSelectTab,
}: ItineraryDashboardHubProps) {
  const { lang } = useLanguage()
  const zh = lang === "zh"
  const haptic = useHaptic()

  // 1. 計算 AI 審核亮點
  const aiHighlights = useMemo(() => extractAIReviewHighlights(review), [review])
  const hasReview = Boolean(
    review &&
    typeof review === "string" &&
    review.trim().length > 0 &&
    !review.includes("尚未安排任何景點") &&
    !review.includes("尚未安排景點")
  )

  // 2. 計算花費摘要 (安全清洗防 NaN)
  const costSummary = useMemo(
    () => calculateDayCostsSummary(costs, defaultCurrency),
    [costs, defaultCurrency]
  )

  // 3. 計算清單進度 (Day 0+1 去重)
  const checklistProgress = useMemo(
    () => calculateChecklistProgress(dayChecklists, day),
    [dayChecklists, day]
  )

  // 點擊處理 (附帶觸覺反饋)
  const handleCardClick = (tab: DashboardSectionTab) => {
    haptic.selection()
    onSelectTab(tab)
  }

  // AI 評分狀態樣式
  const scoreBadgeColor = useMemo(() => {
    if (aiHighlights.score !== null) {
      if (aiHighlights.score >= 85) return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
      if (aiHighlights.score >= 70) return "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30"
      return "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30"
    }
    if (hasReview) {
      return "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/30"
    }
    return "bg-muted text-muted-foreground border-border/50"
  }, [aiHighlights.score, hasReview])

  const checklistPercentage = checklistProgress.total > 0
    ? Math.round((checklistProgress.completed / checklistProgress.total) * 100)
    : 0

  return (
    <div className="w-full px-4 py-2 space-y-2.5">
      {/* ──────────────────────────────────────────────────────────── */}
      {/* 1. 滿版橫卡: 📮 旅伴時光膠囊 (Hero Card - 第一順位)             */}
      {/* ──────────────────────────────────────────────────────────── */}
      <motion.button
        type="button"
        whileTap={{ scale: 0.985 }}
        onClick={() => {
          haptic.selection()
          onCapsuleClick?.()
        }}
        className={cn(
          "w-full text-left p-3.5 rounded-2xl transition-all duration-200 group border shadow-sm hover:shadow-md flex items-center justify-between gap-3",
          isSample
            ? "bg-linear-to-r from-sky-500/10 via-emerald-500/5 to-sky-500/10 border-sky-500/30 dark:border-sky-500/20 backdrop-blur-xl"
            : capsuleSummary?.is_unlocked
            ? "bg-linear-to-r from-amber-500/15 via-yellow-500/10 to-amber-500/15 border-amber-500/35 backdrop-blur-xl"
            : "bg-white/70 dark:bg-card/60 border-white/50 dark:border-white/10 backdrop-blur-xl"
        )}
      >
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={cn(
              "w-11 h-11 rounded-xl flex flex-col items-center justify-center border shrink-0 transition-transform group-hover:scale-105",
              isSample
                ? "bg-sky-500/15 text-sky-600 dark:text-sky-400 border-sky-500/30"
                : capsuleSummary?.is_unlocked
                ? "bg-amber-500/20 text-amber-500 border-amber-500/40"
                : capsuleSummary?.has_current_user_submitted
                ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                : "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30"
            )}
          >
            {isSample ? (
              <Compass className="w-5 h-5 text-sky-500 animate-pulse" />
            ) : capsuleSummary?.is_unlocked ? (
              <Sparkles className="w-5 h-5 text-amber-500 animate-pulse" />
            ) : capsuleSummary?.has_current_user_submitted ? (
              <CheckCircle2 className="w-5 h-5 text-emerald-500" />
            ) : (
              <Lock className="w-5 h-5 text-amber-500" />
            )}
            <span className="text-[8px] uppercase font-semibold leading-none mt-0.5 opacity-80">
              {isSample
                ? (zh ? "範本" : "Demo")
                : capsuleSummary?.is_unlocked
                ? (zh ? "已破印" : "Revealed")
                : capsuleSummary?.has_current_user_submitted
                ? (zh ? "已封存" : "Sealed")
                : (zh ? "未封存" : "Pending")}
            </span>
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-foreground tracking-tight">
                {isSample
                  ? (zh ? (day === 0 ? "旅程終局總結膠囊" : "旅伴時光膠囊功能導覽") : "Time Capsule Guidance")
                  : (zh ? (day === 0 ? "旅程終局總結膠囊" : `Day ${day} 旅伴時光膠囊`) : (day === 0 ? "Trip Finale Capsule" : `Day ${day} Time Capsule`))}
              </span>
              {isSample ? (
                <span className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.2 rounded-full bg-sky-500/20 text-sky-600 dark:text-sky-400 font-bold border border-sky-500/30">
                  {zh ? "單人範本" : "Sample Mode"}
                </span>
              ) : capsuleSummary?.is_unlocked ? (
                <span className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.2 rounded-full bg-amber-500/20 text-amber-600 dark:text-amber-400 font-bold border border-amber-500/30">
                  <Sparkles className="w-2.5 h-2.5" />
                  {zh ? "盛典解鎖" : "Unveiled"}
                </span>
              ) : (
                <span className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.2 rounded-full bg-muted text-muted-foreground font-medium">
                  {zh ? `👥 ${capsuleSummary?.submitted_members_count || 0}/${capsuleSummary?.total_members || 1} 人` : `👥 ${capsuleSummary?.submitted_members_count || 0}/${capsuleSummary?.total_members || 1}`}
                </span>
              )}
            </div>

            <p className="text-xs text-muted-foreground truncate mt-0.5">
              {isSample
                ? (zh ? "💡 範本行程僅供體驗。建立專屬自訂行程並邀請旅伴，即可共同封存膠囊！" : "💡 Sample trip mode. Create a shared trip to seal capsules with friends!")
                : capsuleSummary?.is_unlocked
                ? (zh ? "🎉 膠囊已解鎖！點擊啟動回憶揭曉盛典 (3D 翻轉卡牌)" : "🎉 Tap to launch full-screen 3D flip card ceremony!")
                : capsuleSummary?.has_current_user_submitted
                ? (zh ? "你的今日真心話已安全封存，回國前旅伴無法偷看 🔒" : "Your memo is safely sealed until trip ends 🔒")
                : (zh ? "點擊記錄今日秘密真心話與拍立得，旅後全體解鎖 ✨" : "Tap to record your secret memory and photo for today ✨")}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1 text-muted-foreground/70 group-hover:text-primary transition-colors shrink-0">
          <span className="text-[11px] font-medium hidden sm:inline">
            {isSample
              ? (zh ? "功能介紹" : "Info")
              : capsuleSummary?.is_unlocked
              ? (zh ? "啟動盛典" : "Launch")
              : (zh ? "記錄" : "Record")}
          </span>
          <ChevronRight className="w-4 h-4" />
        </div>
      </motion.button>

      {/* ──────────────────────────────────────────────────────────── */}
      {/* 2. 2x2 雙欄網格: 💡 重點提醒 / 💰 預估花費 / 🎫 交通票券 / ✅ 行前清單 */}
      {/* ──────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-2.5">
        {/* 卡片 1: 💡 每日重點提醒 */}
        <motion.button
          type="button"
          whileTap={{ scale: 0.98 }}
          onClick={() => handleCardClick("tips")}
          className={cn(
            "text-left p-3 rounded-2xl transition-all duration-200",
            "bg-white/70 dark:bg-card/60 backdrop-blur-xl",
            "border border-white/50 dark:border-white/10 shadow-sm hover:shadow-md",
            "flex flex-col justify-between min-h-20.5 group"
          )}
        >
          <div className="flex items-center justify-between w-full">
            <div className="w-7 h-7 rounded-lg bg-amber-500/10 dark:bg-amber-400/10 text-amber-600 dark:text-amber-400 flex items-center justify-center">
              <AlertCircle className="w-4 h-4" />
            </div>
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground tabular-nums">
              {notes.length} {zh ? "條" : ""}
            </span>
          </div>

          <div className="mt-2 min-w-0 w-full">
            <div className="text-[11px] font-semibold text-foreground truncate">
              {zh ? "每日重點提醒" : "Daily Tips"}
            </div>
            <p className="text-[10px] text-muted-foreground truncate mt-0.5">
              {notes.length > 0
                ? `${notes[0].icon || "💡"} ${notes[0].title}`
                : (zh ? "尚無重點備忘" : "No tips")}
            </p>
          </div>
        </motion.button>

        {/* 卡片 2: ✅ 行前清單 */}
        <motion.button
          type="button"
          whileTap={{ scale: 0.98 }}
          onClick={() => handleCardClick("checklist")}
          className={cn(
            "text-left p-3 rounded-2xl transition-all duration-200",
            "bg-white/70 dark:bg-card/60 backdrop-blur-xl",
            "border border-white/50 dark:border-white/10 shadow-sm hover:shadow-md",
            "flex flex-col justify-between min-h-20.5 group"
          )}
        >
          <div className="flex items-center justify-between w-full">
            <div className="w-7 h-7 rounded-lg bg-indigo-500/10 dark:bg-indigo-400/10 text-indigo-600 dark:text-indigo-400 flex items-center justify-center">
              <CheckSquare className="w-4 h-4" />
            </div>
            {checklistProgress.total > 0 && checklistProgress.completed === checklistProgress.total ? (
              <span className="inline-flex items-center gap-0.5 text-[9px] font-medium px-1.5 py-0.2 rounded-full bg-emerald-500/15 text-emerald-600">
                <CheckCircle2 className="w-2.5 h-2.5" />
                {zh ? "完成" : "Done"}
              </span>
            ) : (
              <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground tabular-nums">
                {checklistProgress.completed}/{checklistProgress.total}
              </span>
            )}
          </div>

          <div className="mt-2 min-w-0 w-full">
            <div className="text-[11px] font-semibold text-foreground truncate">
              {zh ? "行前清單" : "Checklist"}
            </div>

            {/* 微型進度條 */}
            <div className="mt-1 flex items-center gap-1.5">
              <div className="flex-1 h-1.5 rounded-full bg-muted/80 overflow-hidden">
                <div
                  className="h-full bg-indigo-500 rounded-full transition-all duration-300"
                  style={{ width: `${checklistPercentage}%` }}
                />
              </div>
              <span className="text-[9px] text-muted-foreground font-mono tabular-nums">
                {checklistPercentage}%
              </span>
            </div>
          </div>
        </motion.button>

        {/* 卡片 3: 🎫 交通票券 */}
        <motion.button
          type="button"
          whileTap={{ scale: 0.98 }}
          onClick={() => handleCardClick("tickets")}
          className={cn(
            "text-left p-3 rounded-2xl transition-all duration-200",
            "bg-white/70 dark:bg-card/60 backdrop-blur-xl",
            "border border-white/50 dark:border-white/10 shadow-sm hover:shadow-md",
            "flex flex-col justify-between min-h-20.5 group"
          )}
        >
          <div className="flex items-center justify-between w-full">
            <div className="w-7 h-7 rounded-lg bg-blue-500/10 dark:bg-blue-400/10 text-blue-600 dark:text-blue-400 flex items-center justify-center">
              <Ticket className="w-4 h-4" />
            </div>
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground tabular-nums">
              {tickets.length} {zh ? "張" : ""}
            </span>
          </div>

          <div className="mt-2 min-w-0 w-full">
            <div className="text-[11px] font-semibold text-foreground truncate">
              {zh ? "交通票券" : "Transit Tickets"}
            </div>
            <p className="text-[10px] text-muted-foreground truncate mt-0.5">
              {tickets.length > 0 ? tickets[0].name : (zh ? "尚無票券憑證" : "No tickets")}
            </p>
          </div>
        </motion.button>

        {/* 卡片 4: 💰 預估花費 */}
        <motion.button
          type="button"
          whileTap={{ scale: 0.98 }}
          onClick={() => handleCardClick("costs")}
          className={cn(
            "text-left p-3 rounded-2xl transition-all duration-200",
            "bg-white/70 dark:bg-card/60 backdrop-blur-xl",
            "border border-white/50 dark:border-white/10 shadow-sm hover:shadow-md",
            "flex flex-col justify-between min-h-20.5 group"
          )}
        >
          <div className="flex items-center justify-between w-full">
            <div className="w-7 h-7 rounded-lg bg-emerald-500/10 dark:bg-emerald-400/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
              <Wallet className="w-4 h-4" />
            </div>
            {costSummary.hasMultipleCurrencies && (
              <span className="text-[9px] font-medium px-1.5 py-0.2 rounded-full bg-primary/10 text-primary">
                {zh ? "多幣別" : "Multi"}
              </span>
            )}
          </div>

          <div className="mt-2 min-w-0 w-full">
            <div className="text-[11px] font-semibold text-foreground truncate">
              {zh ? "預估花費" : "Estimated Cost"}
            </div>
            <div className="text-xs font-bold text-foreground tabular-nums truncate mt-0.5">
              {costSummary.primaryCurrency} {costSummary.primaryTotal.toLocaleString()}
            </div>
          </div>
        </motion.button>
      </div>

      {/* ──────────────────────────────────────────────────────────── */}
      {/* 3. 滿版橫卡: 🤖 AI 深度審核報告 (移至看板下方)                 */}
      {/* ──────────────────────────────────────────────────────────── */}
      <motion.button
        type="button"
        whileTap={{ scale: 0.985 }}
        onClick={() => handleCardClick("ai_review")}
        className={cn(
          "w-full text-left p-3.5 rounded-2xl transition-all duration-200",
          "bg-white/70 dark:bg-card/60 backdrop-blur-xl",
          "border border-white/50 dark:border-white/10 shadow-sm hover:shadow-md",
          "flex items-center justify-between gap-3 group"
        )}
      >
        <div className="flex items-center gap-3 min-w-0">
          {/* 評分徽章 / 圖標 */}
          <div
            className={cn(
              "w-11 h-11 rounded-xl flex flex-col items-center justify-center border shrink-0 transition-transform group-hover:scale-105",
              scoreBadgeColor
            )}
          >
            {aiHighlights.score !== null ? (
              <>
                <span className="text-sm font-bold leading-none tabular-nums">
                  {aiHighlights.score}
                </span>
                <span className="text-[9px] uppercase font-semibold leading-none mt-0.5 opacity-80">
                  {zh ? "評分" : "Score"}
                </span>
              </>
            ) : hasReview ? (
              <>
                <ShieldCheck className="w-5 h-5 text-indigo-500" />
                <span className="text-[8px] uppercase font-semibold leading-none mt-0.5 opacity-80 text-indigo-600 dark:text-indigo-400">
                  {zh ? "已審核" : "Done"}
                </span>
              </>
            ) : (
              <Sparkles className="w-5 h-5 text-indigo-500" />
            )}
          </div>

          {/* 審核文字資訊 */}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-foreground tracking-tight">
                {zh ? "AI 深度審核報告" : "AI Itinerary Review"}
              </span>
              {aiHighlights.score !== null ? (
                aiHighlights.score >= 85 ? (
                  <span className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.2 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 font-medium">
                    <ShieldCheck className="w-2.5 h-2.5" />
                    {zh ? "極佳" : "Excellent"}
                  </span>
                ) : aiHighlights.score >= 70 ? (
                  <span className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.2 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400 font-medium">
                    <ShieldAlert className="w-2.5 h-2.5" />
                    {zh ? "大致流暢" : "Good"}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.2 rounded-full bg-rose-500/15 text-rose-600 dark:text-rose-400 font-medium">
                    <AlertTriangle className="w-2.5 h-2.5" />
                    {zh ? "建議調整" : "Review Needed"}
                  </span>
                )
              ) : aiHighlights.hasWarning ? (
                <span className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.2 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400 font-medium">
                  <ShieldAlert className="w-2.5 h-2.5" />
                  {zh ? "有提醒" : "Alert"}
                </span>
              ) : hasReview ? (
                <span className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.2 rounded-full bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 font-medium">
                  <ShieldCheck className="w-2.5 h-2.5" />
                  {zh ? "已審核" : "Reviewed"}
                </span>
              ) : (
                <span className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.2 rounded-full bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 font-medium">
                  <Sparkles className="w-2.5 h-2.5" />
                  {zh ? "尚未體檢" : "Pending"}
                </span>
              )}
            </div>

            <p className="text-xs text-muted-foreground truncate mt-0.5">
              {aiHighlights.warningSnippet
                ? aiHighlights.warningSnippet
                : aiHighlights.score !== null
                ? aiHighlights.score >= 85
                  ? (zh ? "行程規劃得宜，時間節奏流暢" : "Itinerary is well-balanced.")
                  : aiHighlights.score >= 70
                  ? (zh ? "整體流暢，部分點位略微緊湊" : "Overall good, slightly tight.")
                  : (zh ? "存在折返或時間不足，建議優化" : "Schedule may be tight. Tap to review.")
                : hasReview
                ? (zh ? "AI 深度審核完成，點擊查看詳細報告" : "AI review completed. Tap to view.")
                : (zh ? "尚未進行 AI 體檢，點擊啟動深度審核" : "No review yet. Tap to analyze.")}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1 text-muted-foreground/70 group-hover:text-primary transition-colors shrink-0">
          <span className="text-[11px] font-medium hidden sm:inline">
            {zh ? "查看分析" : "View"}
          </span>
          <ChevronRight className="w-4 h-4" />
        </div>
      </motion.button>
    </div>
  )
}
