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

// 🛡️ 模組級單例頻道協調器 (保證連線建立期廣播不丟包、集中管理跨組件通道)
class RealtimeChannelCoordinator {
    private static instance: RealtimeChannelCoordinator | null = null;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    private channelMap: Map<string, any> = new Map();
    private statusMap: Map<string, "DISCONNECTED" | "CONNECTING" | "SUBSCRIBED"> = new Map();
    private queueMap: Map<string, Array<{ event: string; payload: Record<string, unknown> }>> = new Map();

    public static get(): RealtimeChannelCoordinator {
        if (!RealtimeChannelCoordinator.instance) {
            RealtimeChannelCoordinator.instance = new RealtimeChannelCoordinator();
        }
        return RealtimeChannelCoordinator.instance;
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    public attach(tripId: string, channel: any) {
        this.channelMap.set(tripId, channel);
        this.statusMap.set(tripId, "CONNECTING");
    }

    public setSubscribed(tripId: string) {
        this.statusMap.set(tripId, "SUBSCRIBED");
        const queue = this.queueMap.get(tripId) || [];
        const channel = this.channelMap.get(tripId);
        while (queue.length > 0) {
            const item = queue.shift();
            if (item && channel) {
                channel.send({ type: "broadcast", event: item.event, payload: item.payload }).catch(() => {});
            }
        }
    }

    public detach(tripId: string) {
        this.channelMap.delete(tripId);
        this.statusMap.delete(tripId);
        this.queueMap.delete(tripId); // 🧹 清理殘留佇列避免跨生命週期幽靈重放
    }

    public async broadcast(tripId: string, event: string, payload: Record<string, unknown>) {
        const channel = this.channelMap.get(tripId);
        const status = this.statusMap.get(tripId);

        if (status === "SUBSCRIBED" && channel) {
            try {
                const res = await channel.send({ type: "broadcast", event: "collab:event", payload: { ...payload, event } });
                if (res === "ok") return;
            } catch { /* Fallback to queue */ }
        }

        // 未就緒或連線暫斷時排入佇列
        if (!this.queueMap.has(tripId)) {
            this.queueMap.set(tripId, []);
        }
        this.queueMap.get(tripId)!.push({ event: "collab:event", payload: { ...payload, event } });

        // 保底：若 Hook 尚未掛載該頻道，使用 Supabase 臨時頻道發送
        if (!channel && typeof window !== "undefined") {
            const supabase = getSupabaseClient();
            if (supabase) {
                const fallbackChannel = supabase.channel(`realtime-trip-${tripId}`);
                fallbackChannel.send({ type: "broadcast", event: "collab:event", payload: { ...payload, event } }).catch(() => {});
            }
        }
    }
}

/**
 * ⚡ 廣播即時協同事件給同一行程的其他協同者 (Phoenix Channels 記憶體扇出，<10ms)
 */
export const broadcastTripEvent = async (
    tripId: string,
    event: "tip:update" | "tip:typing" | "item:reorder" | "item:mutate" | "checklist:update" | "expense:update" | "info:update" | "capsule:update" | "capsule:unveil",
    data: Record<string, unknown>
) => {
    if (typeof window === "undefined" || !tripId) return
    await RealtimeChannelCoordinator.get().broadcast(tripId, event, {
        tripId,
        senderSessionId: getClientSessionId(),
        timestamp: Date.now(),
        ...data,
    });
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
        RealtimeChannelCoordinator.get().attach(tripId, channel)

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
                }, undefined, { revalidate: true })

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
                }, undefined, { revalidate: true })

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

                // 派發自定義 DOM 事件以通知特定元件 (例如卡片重排、Daily Tips 或 Checklist 輸入)
                if (typeof window !== "undefined") {
                    window.dispatchEvent(new CustomEvent("tabiji:collab-event", { detail: payload }))
                }

                // 鏡像更新 SWR 快取 (針對細項異動與拖曳)
                // ⚡ 核心解耦：tip:update 與 checklist:update 禁止立即打 GET，由 DOM 事件記憶體鏡像先行，待資料庫落盤後由 postgres_changes 權威核實
                if (payload.event === "item:reorder" || payload.event === "item:mutate") {
                    mutate((key: unknown) => {
                        if (Array.isArray(key) && key[0] === `/api/trips/${tripId}`) return true
                        return false
                    })
                }

                // 💰 記帳廣播事件處理
                if (payload.event === "expense:update") {
                    mutate((key: unknown) => {
                        if (Array.isArray(key) && typeof key[0] === "string" && key[0].startsWith(`/api/trips/${tripId}/expenses`)) return true
                        if (typeof key === "string" && key.includes(`/api/trips/${tripId}/expenses`)) return true
                        return false
                    }, undefined, { revalidate: true })
                }

                // 📮 時光膠囊廣播事件處理 (進度刷新與破印盛典同步)
                if (payload.event === "capsule:update" || payload.event === "capsule:unveil") {
                    mutate((key: unknown) => {
                        if (Array.isArray(key) && typeof key[0] === "string" && key[0].startsWith(`/api/trips/${tripId}/capsules`)) return true
                        if (typeof key === "string" && key.includes(`/api/trips/${tripId}/capsules`)) return true
                        return false
                    }, undefined, { revalidate: true })

                    if (payload.event === "capsule:update") {
                        const now = Date.now()
                        if (now - lastToastTimeRef.current > 3000) {
                            lastToastTimeRef.current = now
                            toast.info("💌 旅伴已封存時光膠囊", { duration: 2500 })
                        }
                    }
                }
            }
        )

        // 4. 💰 補齊公帳盲區：監聽分帳支出異動 (新增、修改、刪除費用)
        channel.on(
            "postgres_changes",
            {
                event: "*",
                schema: "public",
                table: "expenses",
                filter: `itinerary_id=eq.${tripId}`,
            },
            (payload) => {
                console.log("🔄 [Realtime] Expense updated remotely:", payload.eventType)
                // 🛡️ 關鍵加固：SWR key 為 Tuple [`/api/trips/${tripId}/expenses`, userId]，採 Predicate 精準刷新
                mutate((key: unknown) => {
                    if (Array.isArray(key) && typeof key[0] === "string" && key[0].startsWith(`/api/trips/${tripId}/expenses`)) return true
                    if (typeof key === "string" && key.includes(`/api/trips/${tripId}/expenses`)) return true
                    if (typeof key === "string" && (key.includes("/api/ledger/expenses") || key.includes("/api/ledger/summary"))) return true
                    return false
                }, undefined, { revalidate: true })

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
                RealtimeChannelCoordinator.get().setSubscribed(tripId)
            }
        })

        return () => {
            RealtimeChannelCoordinator.get().detach(tripId)
            supabase.removeChannel(channel)
        }
    }, [tripId, userId, mutate, clientSessionId])
}

