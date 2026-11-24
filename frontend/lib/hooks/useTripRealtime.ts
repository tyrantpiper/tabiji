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

function isPrivateRecord(entry: unknown): boolean {
    return Boolean(entry && typeof entry === "object" && (entry as { is_private?: boolean }).is_private)
}

/**
 * 🛡️ 傳輸層隱私剝離：任何經由共享 WebSocket 頻道廣播的清單／花費／票券
 * 絕對禁止夾帶 is_private: true 項目或 private_owner_id 原生使用者 UUID。
 */
export function stripPrivateForBroadcast<T>(items: T[]): T[] {
    if (!Array.isArray(items)) return []
    const result: T[] = []
    for (const entry of items) {
        if (!entry || typeof entry !== "object") {
            result.push(entry)
            continue
        }
        if ((entry as { is_private?: boolean }).is_private) {
            continue
        }
        if ("private_owner_id" in entry) {
            const { private_owner_id: _omitted, ...publicCopy } = entry as Record<string, unknown>
            void _omitted
            result.push(publicCopy as T)
        } else {
            result.push(entry)
        }
    }
    return result
}

/**
 * 🛡️ 接收端隱私過濾：公開項目放行；具 private_owner_id 之私人項目僅建立者本人可見；
 * 無主歷史私人項目僅於 allowOwnerlessRescue 為真（行程建立者）時放行。
 */
export function filterVisiblePrivateItems<T>(
    items: T[],
    currentUserId?: string | null,
    allowOwnerlessRescue = false
): T[] {
    if (!Array.isArray(items)) return []
    return items.filter((entry) => {
        if (!entry || typeof entry !== "object") return false
        const rec = entry as { is_private?: boolean; private_owner_id?: string }
        if (!rec.is_private) return true
        if (rec.private_owner_id) {
            return Boolean(currentUserId && rec.private_owner_id === currentUserId)
        }
        return allowOwnerlessRescue
    })
}

/**
 * 🛡️ 接收端安全合併：將旅伴廣播的公開更新與本機既有之個人私人項目合併，
 * 避免他方公開廣播把自己的私人項目從 DOM 或 SWR 快取中洗掉。
 */
export function mergeIncomingWithLocalPrivate<T>(
    existing: T[] | undefined | null,
    incoming: T[],
    currentUserId?: string | null,
    allowOwnerlessIncoming = false,
    allowOwnerlessExisting = false
): T[] {
    const visibleIncoming = filterVisiblePrivateItems(incoming, currentUserId, allowOwnerlessIncoming)
    const existingList = Array.isArray(existing) ? existing : []
    const existingOwnPrivate = filterVisiblePrivateItems(
        existingList,
        currentUserId,
        allowOwnerlessExisting
    ).filter((entry) => isPrivateRecord(entry))

    if (existingOwnPrivate.length === 0) {
        return visibleIncoming
    }

    const incomingIds = new Set<string>()
    for (const item of visibleIncoming) {
        if (item && typeof item === "object" && "id" in item && typeof (item as { id?: unknown }).id === "string") {
            incomingIds.add((item as { id: string }).id)
        }
    }

    const preservedPrivate = existingOwnPrivate.filter((item) => {
        if (item && typeof item === "object" && "id" in item && typeof (item as { id?: unknown }).id === "string") {
            return !incomingIds.has((item as { id: string }).id)
        }
        const sig = JSON.stringify(item)
        return !visibleIncoming.some((inc) => JSON.stringify(inc) === sig)
    })

    return [...visibleIncoming, ...preservedPrivate]
}

/**
 * ⚡ 廣播即時協同事件給同一行程的其他協同者 (Phoenix Channels 記憶體扇出，<10ms)
 * 🛡️ 強制剝離所有私人項目與原生 private_owner_id UUID，確保 WebSocket 傳輸層零私密外洩
 */
export const broadcastTripEvent = async (
    tripId: string,
    event: "tip:update" | "tip:typing" | "item:reorder" | "item:mutate" | "checklist:update" | "expense:update" | "info:update" | "capsule:update" | "capsule:unveil",
    data: Record<string, unknown>
) => {
    if (typeof window === "undefined" || !tripId) return
    const safeData: Record<string, unknown> = (() => {
        if (event === "checklist:update" && Array.isArray(data.items)) {
            return { ...data, items: stripPrivateForBroadcast(data.items) }
        }
        if (
            event === "tip:update" &&
            (data.type === "costs" || data.type === "tickets") &&
            Array.isArray(data.data)
        ) {
            return { ...data, data: stripPrivateForBroadcast(data.data) }
        }
        return data
    })()

    await RealtimeChannelCoordinator.get().broadcast(tripId, event, {
        tripId,
        senderSessionId: getClientSessionId(),
        timestamp: Date.now(),
        ...safeData,
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

        // ⚡ Broadcast 記憶體協同事件 (<10ms 鏡像同步；不再依賴會被匿名 RLS 靜默攔截的 postgres_changes)
        channel.on(
            "broadcast",
            { event: "collab:event" },
            ({ payload }) => {
                // 🛡️ 關鍵加固：抑制自己發送的廣播，避免本地焦點與游標被覆蓋
                if (!payload || payload.senderSessionId === clientSessionId) return
                console.log("⚡ [Realtime Broadcast] Remote collab event:", payload.event)

                // 🛡️ 派發自定義 DOM 事件前先過濾他人的私人項目，防止敏感私人資料閃現至協作者畫面
                const sanitizedPayload = (() => {
                    if (payload.event === "checklist:update" && Array.isArray(payload.items)) {
                        return { ...payload, items: filterVisiblePrivateItems(payload.items, userId, false) }
                    }
                    if (
                        payload.event === "tip:update" &&
                        (payload.type === "costs" || payload.type === "tickets") &&
                        Array.isArray(payload.data)
                    ) {
                        return { ...payload, data: filterVisiblePrivateItems(payload.data, userId, false) }
                    }
                    return payload
                })()

                // 派發自定義 DOM 事件以通知特定元件 (例如卡片重排、Daily Tips 或 Checklist 輸入)
                if (typeof window !== "undefined") {
                    window.dispatchEvent(new CustomEvent("tabiji:collab-event", { detail: sanitizedPayload }))
                }

                // 鏡像更新 SWR 快取 (針對細項異動與拖曳與行程主表設定變更)
                if (payload.event === "item:reorder" || payload.event === "item:mutate" || payload.event === "info:update") {
                    mutate((key: unknown) => {
                        if (Array.isArray(key) && key[0] === `/api/trips/${tripId}`) return true
                        if (Array.isArray(key) && key[0] === "/api/trips") return true
                        return false
                    }, undefined, { revalidate: true })

                    if (payload.event === "item:mutate") {
                        const now = Date.now()
                        if (now - lastToastTimeRef.current > 3000) {
                            lastToastTimeRef.current = now
                            toast.info("📍 旅伴已更新景點清單", { duration: 2500 })
                        }
                    }
                }

                // 📝 每日提醒 / 花費 / 票券 / 行前清單廣播事件：同步 SWR 行程詳情快取並背景校驗
                if (payload.event === "tip:update" || payload.event === "checklist:update") {
                    const rawDayIndex = payload.dayIndex
                    const dayKey =
                        rawDayIndex !== undefined &&
                        rawDayIndex !== null &&
                        String(rawDayIndex).trim() !== ""
                            ? Number(rawDayIndex)
                            : null
                    const hasValidDay = dayKey !== null && Number.isInteger(dayKey) && dayKey >= 0

                    mutate(
                        (key: unknown) => Array.isArray(key) && key[0] === `/api/trips/${tripId}`,
                        // eslint-disable-next-line @typescript-eslint/no-explicit-any
                        (current: any) => {
                            if (!current || typeof current !== "object" || !hasValidDay) return current
                            const isTripOwner = Boolean(userId && current.created_by && current.created_by === userId)
                            if (payload.event === "checklist:update" && Array.isArray(payload.items)) {
                                const existingDayItems =
                                    current.day_checklists?.[dayKey] ?? current.day_checklists?.[String(dayKey)]
                                const mergedItems = mergeIncomingWithLocalPrivate(
                                    existingDayItems,
                                    payload.items,
                                    userId,
                                    false,
                                    isTripOwner
                                )
                                const nextChecklists = {
                                    ...(current.day_checklists || {}),
                                    [dayKey]: mergedItems,
                                }
                                if (dayKey === 1) {
                                    const existingDay0 =
                                        current.day_checklists?.[0] ?? current.day_checklists?.["0"]
                                    nextChecklists[0] = filterVisiblePrivateItems(
                                        Array.isArray(existingDay0) ? existingDay0 : [],
                                        userId,
                                        isTripOwner
                                    ).filter((entry) => isPrivateRecord(entry))
                                }
                                return {
                                    ...current,
                                    day_checklists: nextChecklists,
                                }
                            }
                            if (payload.event === "tip:update" && Array.isArray(payload.data)) {
                                const fieldMap: Record<string, string> = {
                                    notes: "day_notes",
                                    costs: "day_costs",
                                    tickets: "day_tickets",
                                }
                                const targetField = typeof payload.type === "string" ? fieldMap[payload.type] : undefined
                                if (targetField) {
                                    const existingDayData =
                                        current[targetField]?.[dayKey] ?? current[targetField]?.[String(dayKey)]
                                    const nextDayValue =
                                        targetField === "day_notes"
                                            ? payload.data
                                            : mergeIncomingWithLocalPrivate(
                                                existingDayData,
                                                payload.data,
                                                userId,
                                                false,
                                                isTripOwner
                                            )
                                    return {
                                        ...current,
                                        [targetField]: {
                                            ...(current[targetField] || {}),
                                            [dayKey]: nextDayValue,
                                        },
                                    }
                                }
                            }
                            return current
                        },
                        { revalidate: true }
                    )
                }

                // 💰 記帳廣播事件處理
                if (payload.event === "expense:update") {
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

