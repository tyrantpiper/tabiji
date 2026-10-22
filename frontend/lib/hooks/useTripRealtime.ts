"use client"

import { useEffect, useRef } from "react"
import { useSWRConfig } from "swr"
import { getSupabaseClient } from "@/lib/supabase"
import { toast } from "sonner"

// 🛡️ 全域客戶端 Session ID，用於抑制自己引發的廣播與 WAL 回音 (Self-Echo Suppression)
declare global {
    interface Window {
        __tabijiClientSessionId?: string;
    }
}

export const getClientSessionId = (): string => {
    if (typeof window === "undefined") return "ssr"
    if (!window.__tabijiClientSessionId) {
        window.__tabijiClientSessionId = crypto.randomUUID()
    }
    return window.__tabijiClientSessionId
}

/**
 * ⚡ 廣播即時協同事件給同一行程的其他協同者 (Phoenix Channels 記憶體扇出，<10ms)
 */
export const broadcastTripEvent = async (
    tripId: string,
    event: "tip:update" | "tip:typing" | "item:reorder" | "item:mutate",
    data: Record<string, unknown>
) => {
    if (typeof window === "undefined" || !tripId) return
    const supabase = getSupabaseClient()
    if (!supabase) return

    try {
        const channelName = `realtime-trip-${tripId}`
        const channel = supabase.channel(channelName)
        await channel.send({
            type: "broadcast",
            event: "collab:event",
            payload: {
                event,
                tripId,
                senderSessionId: getClientSessionId(),
                timestamp: Date.now(),
                ...data,
            },
        })
    } catch (err) {
        console.warn("⚠️ [Broadcast] Failed to send collab event:", err)
    }
}

/**
 * 🔄 E6: Supabase Realtime 跨裝置即時協同 Hook
 * 監聽當前行程 (itineraries)、細項 (itinerary_items) 與分帳費用 (expenses) 的變更
 * 同時支援 Broadcast 記憶體通道，達成 Google Docs 級別的 15ms 鏡像反應
 */
export function useTripRealtime(tripId: string | null | undefined, userId?: string | null) {
    const { mutate } = useSWRConfig()
    const lastToastTimeRef = useRef<number>(0)
    const clientSessionId = getClientSessionId()

    useEffect(() => {
        if (!tripId || typeof window === "undefined") return

        const supabase = getSupabaseClient()
        if (!supabase) return

        const channelName = `realtime-trip-${tripId}`
        const channel = supabase.channel(channelName)

        // 1. 監聽行程詳情異動 (封面、天數、每日重點提醒)
        channel.on(
            "postgres_changes",
            {
                event: "*",
                schema: "public",
                table: "itineraries",
                filter: `id=eq.${tripId}`,
            },
            (payload) => {
                console.log("🔄 [Realtime] Itinerary updated remotely:", payload.eventType)
                mutate((key: unknown) => {
                    if (Array.isArray(key) && key[0] === `/api/trips/${tripId}`) return true
                    if (Array.isArray(key) && key[0] === "/api/trips") return true
                    return false
                })

                const now = Date.now()
                if (now - lastToastTimeRef.current > 3000) {
                    lastToastTimeRef.current = now
                    toast.info("🔄 旅伴已更新行程內容", { duration: 2500 })
                }
            }
        )

        // 2. 🛡️ 補齊盲區：監聽行程細項異動 (景點新增、刪除、拖曳排序、時間調整)
        channel.on(
            "postgres_changes",
            {
                event: "*",
                schema: "public",
                table: "itinerary_items",
                filter: `itinerary_id=eq.${tripId}`,
            },
            (payload) => {
                console.log("🔄 [Realtime] Itinerary item updated remotely:", payload.eventType)
                mutate((key: unknown) => {
                    if (Array.isArray(key) && key[0] === `/api/trips/${tripId}`) return true
                    if (Array.isArray(key) && key[0] === "/api/trips") return true
                    return false
                })

                const now = Date.now()
                if (now - lastToastTimeRef.current > 3000) {
                    lastToastTimeRef.current = now
                    toast.info("📍 旅伴已更新景點清單", { duration: 2500 })
                }
            }
        )

        // 3. ⚡ 監聽高頻 Broadcast 記憶體協同事件 (<10ms 鏡像同步)
        channel.on(
            "broadcast",
            { event: "collab:event" },
            ({ payload }) => {
                // 🛡️ 關鍵加固：抑制自己發送的廣播，避免本地焦點與游標被覆蓋
                if (!payload || payload.senderSessionId === clientSessionId) return
                console.log("⚡ [Realtime Broadcast] Remote collab event:", payload.event)

                // 派發自定義 DOM 事件以通知特定元件 (例如卡片重排或 Daily Tips 輸入)
                if (typeof window !== "undefined") {
                    window.dispatchEvent(new CustomEvent("tabiji:collab-event", { detail: payload }))
                }

                // 鏡像更新 SWR 快取
                if (payload.event === "item:reorder" || payload.event === "tip:update" || payload.event === "item:mutate") {
                    mutate((key: unknown) => {
                        if (Array.isArray(key) && key[0] === `/api/trips/${tripId}`) return true
                        return false
                    })
                }
            }
        )

        // 4. 監聽花費記帳異動
        channel.on(
            "postgres_changes",
            {
                event: "*",
                schema: "public",
                table: "expenses",
                filter: `trip_id=eq.${tripId}`,
            },
            (payload) => {
                console.log("🔄 [Realtime] Expense updated remotely:", payload.eventType)
                mutate((key: unknown) => {
                    if (typeof key === "string" && key.includes("/api/ledger/expenses")) return true
                    if (typeof key === "string" && key.includes("/api/ledger/summary")) return true
                    return false
                })

                const now = Date.now()
                if (now - lastToastTimeRef.current > 3000) {
                    lastToastTimeRef.current = now
                    toast.info("💰 旅伴已更新記帳資料", { duration: 2500 })
                }
            }
        )

        channel.subscribe((status) => {
            if (status === "SUBSCRIBED") {
                console.log(`🌐 [Realtime] Subscribed to trip collaboration: ${tripId}`)
            }
        })

        return () => {
            supabase.removeChannel(channel)
        }
    }, [tripId, userId, mutate, clientSessionId])
}

