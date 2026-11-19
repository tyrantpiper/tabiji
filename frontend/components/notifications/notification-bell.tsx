"use client"

import { useState, useEffect, useCallback } from "react"
import { Bell, CheckCheck, Users, DollarSign, Plane, Megaphone, X, Trash2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { getSupabaseClient } from "@/lib/supabase"
import { notificationsApi, type NotificationItemDto } from "@/lib/api"
import { isUserLoggedIn } from "@/lib/auth-session"
import { useLanguage } from "@/lib/LanguageContext"
import { useTheme } from "@/lib/ThemeContext"
import { motion, AnimatePresence } from "framer-motion"
import { useRouter } from "next/navigation"
import { dispatchDeepLink } from "@/lib/hooks/useDeepLinkRouter"
import { useHaptic } from "@/lib/hooks"
import { toast } from "sonner"

type Notification = NotificationItemDto

function readEstablishedBellUserId(): string | null {
    if (typeof window === "undefined" || !isUserLoggedIn()) return null
    try {
        const raw = localStorage.getItem("user_uuid")?.trim() || ""
        if (!raw || raw === "null" || raw === "undefined" || /^tbj_rec_/i.test(raw)) {
            return null
        }
        return raw
    } catch {
        return null
    }
}

const TYPE_ICONS: Record<string, typeof Users> = {
    trip_invite: Users,
    new_expense: DollarSign,
    trip_countdown: Plane,
    system_announcement: Megaphone,
}

const TYPE_COLORS: Record<string, string> = {
    trip_invite: "bg-blue-100 text-blue-600 dark:bg-blue-900/40 dark:text-blue-400",
    new_expense: "bg-emerald-100 text-emerald-600 dark:bg-emerald-900/40 dark:text-emerald-400",
    trip_countdown: "bg-amber-100 text-amber-600 dark:bg-amber-900/40 dark:text-amber-400",
    system_announcement: "bg-purple-100 text-purple-600 dark:bg-purple-900/40 dark:text-purple-400",
}

function timeAgo(dateStr: string, zh: boolean): string {
    const diff = Date.now() - new Date(dateStr).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return zh ? "剛剛" : "Just now"
    if (mins < 60) return zh ? `${mins} 分鐘前` : `${mins}m ago`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return zh ? `${hours} 小時前` : `${hours}h ago`
    const days = Math.floor(hours / 24)
    return zh ? `${days} 天前` : `${days}d ago`
}

// 🛡️ 模組層級全域單例戳記：跨組件卸載與路由跳轉依然保持 2000ms 物理節流
export let globalLastRefreshTimestamp = 0

/** 僅供單元測試隔離重置模組狀態使用 */
export function __resetGlobalRefreshTimestampForTesting() {
    globalLastRefreshTimestamp = 0
}

export function dispatchGlobalRefreshThrottled() {
    const now = Date.now()
    if (now - globalLastRefreshTimestamp >= 2000) {
        globalLastRefreshTimestamp = now
        if (typeof window !== "undefined") {
            window.dispatchEvent(
                new CustomEvent("tabidachi-trigger-refresh", {
                    detail: { timestamp: now, source: "notification-bell" }
                })
            )
        }
    }
}

export function NotificationBell() {
    const { lang } = useLanguage()
    const zh = lang === "zh"
    const { currentTheme, accentColor } = useTheme()
    const router = useRouter()
    const haptic = useHaptic()
    const [isOpen, setIsOpen] = useState(false)
    const [ringCount, setRingCount] = useState(0)
    const [notifications, setNotifications] = useState<Notification[]>([])
    const [unreadCount, setUnreadCount] = useState(0)

    const handleBellClick = () => {
        const nextOpen = !isOpen
        setIsOpen(nextOpen)
        // 🛡️ 僅在「展開」時觸發微動與重新整理，收合時靜默
        if (nextOpen) {
            setRingCount((c) => c + 1)
            haptic.selection()
            fetchNotifications()
            dispatchGlobalRefreshThrottled()
        }
    }

    const fetchNotifications = useCallback(async () => {
        const userId = readEstablishedBellUserId()
        if (!userId) return

        try {
            const data = await notificationsApi.list(30, 0)
            const items = Array.isArray(data?.items) ? data.items : []
            setNotifications(items)
            setUnreadCount(
                typeof data?.unread_count === "number"
                    ? data.unread_count
                    : items.filter((n) => !n.is_read).length
            )
        } catch {
            // Silently preserve current notifications during offline/transient failures
        }
    }, [])

    useEffect(() => {
        if (typeof window === "undefined") return

        const supabase = getSupabaseClient()
        let activeUserId: string | null = null
        let userChannel: ReturnType<NonNullable<ReturnType<typeof getSupabaseClient>>["channel"]> | null = null
        let globalChannel: ReturnType<NonNullable<ReturnType<typeof getSupabaseClient>>["channel"]> | null = null

        const cleanupChannels = () => {
            if (supabase) {
                if (userChannel) supabase.removeChannel(userChannel)
                if (globalChannel) supabase.removeChannel(globalChannel)
            }
            userChannel = null
            globalChannel = null
            activeUserId = null
        }

        const syncNotificationsAndRealtime = () => {
            const currentUserId = readEstablishedBellUserId()
            if (!currentUserId) {
                cleanupChannels()
                setNotifications([])
                setUnreadCount(0)
                return
            }

            void fetchNotifications()

            if (supabase && currentUserId !== activeUserId) {
                cleanupChannels()
                activeUserId = currentUserId

                userChannel = supabase
                    .channel(`user-notif:${currentUserId}`)
                    .on("broadcast", { event: "notif:refresh" }, () => {
                        void fetchNotifications()
                    })
                    .subscribe()

                globalChannel = supabase
                    .channel("user-notif:broadcast")
                    .on("broadcast", { event: "notif:refresh" }, () => {
                        void fetchNotifications()
                    })
                    .subscribe()
            }
        }

        const initialFetch = setTimeout(syncNotificationsAndRealtime, 0)

        const handleLoginChange = () => syncNotificationsAndRealtime()
        const handleStorage = (e: StorageEvent) => {
            if (!e.key || e.key === "user_uuid" || e.key === "user_nickname" || e.key === "user_recovery_key") {
                syncNotificationsAndRealtime()
            }
        }
        const handleVisibility = () => {
            if (document.visibilityState === "visible" && readEstablishedBellUserId()) {
                void fetchNotifications()
            }
        }

        window.addEventListener("user-login-state-changed", handleLoginChange)
        window.addEventListener("storage", handleStorage)
        document.addEventListener("visibilitychange", handleVisibility)

        return () => {
            clearTimeout(initialFetch)
            window.removeEventListener("user-login-state-changed", handleLoginChange)
            window.removeEventListener("storage", handleStorage)
            document.removeEventListener("visibilitychange", handleVisibility)
            cleanupChannels()
        }
    }, [fetchNotifications])

    const markAsRead = async (id: string) => {
        if (!readEstablishedBellUserId()) return
        const prevNotifications = notifications
        const prevUnread = unreadCount
        const target = prevNotifications.find((n) => n.id === id)

        setNotifications((prev) =>
            prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
        )
        if (target && !target.is_read) {
            setUnreadCount((prev) => Math.max(0, prev - 1))
        }

        try {
            await notificationsApi.markRead(id)
        } catch {
            setNotifications(prevNotifications)
            setUnreadCount(prevUnread)
            toast.error(zh ? "通知已讀更新失敗，請稍後再試" : "Failed to update notification")
        }
    }

    const markAllRead = async () => {
        if (!readEstablishedBellUserId()) return
        const prevNotifications = notifications
        const prevUnread = unreadCount

        setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })))
        setUnreadCount(0)

        try {
            await notificationsApi.markAllRead()
        } catch {
            setNotifications(prevNotifications)
            setUnreadCount(prevUnread)
            toast.error(zh ? "全部已讀操作失敗，請稍後再試" : "Failed to mark all as read")
        }
    }

    // 刪除單筆通知
    const deleteNotification = async (id: string, e: React.MouseEvent) => {
        e.stopPropagation() // 防止觸發 handleNotificationClick
        if (!readEstablishedBellUserId()) return
        const prevNotifications = notifications
        const prevUnread = unreadCount

        // 先從 UI 移除（樂觀更新）
        const target = prevNotifications.find((n) => n.id === id)
        setNotifications((prev) => prev.filter((n) => n.id !== id))
        if (target && !target.is_read) {
            setUnreadCount((c) => Math.max(0, c - 1))
        }

        try {
            await notificationsApi.delete(id)
        } catch {
            setNotifications(prevNotifications)
            setUnreadCount(prevUnread)
            toast.error(zh ? "刪除通知失敗，請稍後再試" : "Failed to delete notification")
        }
    }

    // 清除全部通知
    const clearAllNotifications = async () => {
        if (!readEstablishedBellUserId()) return
        const prevNotifications = notifications
        const prevUnread = unreadCount

        // 樂觀更新
        setNotifications([])
        setUnreadCount(0)

        try {
            await notificationsApi.clearAll()
        } catch {
            setNotifications(prevNotifications)
            setUnreadCount(prevUnread)
            toast.error(zh ? "清除通知失敗，請稍後再試" : "Failed to clear notifications")
        }
    }

    const handleNotificationClick = (notif: Notification) => {
        if (!notif.is_read) markAsRead(notif.id)
        setIsOpen(false)
        // Deep link navigation handled by the app's routing
        if (notif.link) {
            dispatchDeepLink(notif.link)
            router.push(notif.link)
        }
    }

    return (
        <div className="relative">
            {/* Bell Button */}
            <button
                onClick={handleBellClick}
                className="relative p-2 rounded-full hover:bg-stone-100 dark:hover:bg-slate-800 transition-colors active:scale-95"
                aria-label={zh ? "通知" : "Notifications"}
            >
                <motion.div
                    key={ringCount}
                    animate={{ rotate: ringCount > 0 ? [0, -14, 14, -10, 10, -5, 5, 0] : 0 }}
                    transition={{ duration: 0.55, ease: "easeInOut" }}
                >
                    <Bell className="w-5 h-5 text-slate-600 dark:text-slate-300" />
                </motion.div>
                {unreadCount > 0 && (
                    <motion.span
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        className="absolute -top-0.5 -right-0.5 min-w-4.5 h-4.5 flex items-center justify-center rounded-full text-[10px] font-bold text-white px-1"
                        style={{ backgroundColor: accentColor !== "default" ? currentTheme.primary : "#ef4444" }}
                    >
                        {unreadCount > 99 ? "99+" : unreadCount}
                    </motion.span>
                )}
            </button>

            {/* Notification Panel Overlay */}
            <AnimatePresence>
                {isOpen && (
                    <>
                        {/* Backdrop */}
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            className="fixed inset-0 z-200"
                            onClick={() => setIsOpen(false)}
                        />
                        {/* Panel */}
                        <motion.div
                            initial={{ opacity: 0, y: -10, scale: 0.95 }}
                            animate={{ opacity: 1, y: 0, scale: 1 }}
                            exit={{ opacity: 0, y: -10, scale: 0.95 }}
                            transition={{ type: "spring", stiffness: 400, damping: 30 }}
                            className="absolute right-0 top-12 z-201 w-85 max-h-[70vh] bg-white dark:bg-slate-900 rounded-2xl shadow-2xl border border-stone-200 dark:border-slate-700 overflow-hidden"
                        >
                            {/* Header */}
                            <div className="flex items-center justify-between px-4 py-3 border-b border-stone-100 dark:border-slate-800">
                                <h3 className="text-sm font-bold text-slate-800 dark:text-white">
                                    {zh ? "通知" : "Notifications"}
                                </h3>
                                <div className="flex items-center gap-1">
                                    {unreadCount > 0 && (
                                        <button
                                            onClick={markAllRead}
                                            className="text-[11px] text-blue-600 dark:text-blue-400 hover:underline px-2 py-1 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
                                        >
                                            <CheckCheck className="w-3.5 h-3.5 inline mr-1" />
                                            {zh ? "全部已讀" : "Read all"}
                                        </button>
                                    )}
                                    {notifications.length > 0 && (
                                        <button
                                            onClick={clearAllNotifications}
                                            className="text-[11px] text-red-500 dark:text-red-400 hover:underline px-2 py-1 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                                        >
                                            <Trash2 className="w-3.5 h-3.5 inline mr-1" />
                                            {zh ? "清除全部" : "Clear all"}
                                        </button>
                                    )}
                                    <button
                                        onClick={() => setIsOpen(false)}
                                        className="p-1 rounded-lg hover:bg-stone-100 dark:hover:bg-slate-800 transition-colors"
                                    >
                                        <X className="w-4 h-4 text-slate-400" />
                                    </button>
                                </div>
                            </div>

                            {/* Notification List */}
                            <div className="overflow-y-auto max-h-[calc(70vh-52px)] overscroll-contain">
                                {notifications.length === 0 ? (
                                    <div className="py-12 text-center">
                                        <Bell className="w-10 h-10 mx-auto text-stone-300 dark:text-slate-600 mb-3" />
                                        <p className="text-sm text-stone-400 dark:text-slate-500">
                                            {zh ? "暫無通知" : "No notifications yet"}
                                        </p>
                                    </div>
                                ) : (
                                    notifications.map((notif) => {
                                        const Icon = TYPE_ICONS[notif.type] || Bell
                                        const colorClass = TYPE_COLORS[notif.type] || ""
                                        return (
                                            <button
                                                key={notif.id}
                                                onClick={() => handleNotificationClick(notif)}
                                                className={cn(
                                                    "w-full text-left px-4 py-3 flex gap-3 items-start border-b border-stone-50 dark:border-slate-800/50 hover:bg-stone-50 dark:hover:bg-slate-800/50 transition-colors",
                                                    !notif.is_read && "bg-blue-50/50 dark:bg-blue-950/20"
                                                )}
                                            >
                                                <div className={cn("w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5", colorClass)}>
                                                    <Icon className="w-4 h-4" />
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <p className={cn(
                                                        "text-sm leading-snug",
                                                        notif.is_read
                                                            ? "text-slate-500 dark:text-slate-400"
                                                            : "text-slate-800 dark:text-white font-medium"
                                                    )}>
                                                        {notif.body}
                                                    </p>
                                                    <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-1">
                                                        {timeAgo(notif.created_at, zh)}
                                                    </p>
                                                </div>
                                                <div className="flex items-center gap-1 shrink-0 ml-1">
                                                    {!notif.is_read && (
                                                        <div className="w-2 h-2 rounded-full bg-blue-500" />
                                                    )}
                                                    <button
                                                        onClick={(e) => deleteNotification(notif.id, e)}
                                                        className="p-1 rounded-md text-slate-300 dark:text-slate-600 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                                                        aria-label={zh ? "刪除通知" : "Delete notification"}
                                                    >
                                                        <X className="w-3.5 h-3.5" />
                                                    </button>
                                                </div>
                                            </button>
                                        )
                                    })
                                )}
                            </div>
                        </motion.div>
                    </>
                )}
            </AnimatePresence>
        </div>
    )
}
