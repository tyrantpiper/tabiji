"use client"

import useSWR from "swr"
import { useCallback, useEffect } from "react"
import { get, set } from "idb-keyval"
import { poiPoolApi } from "@/lib/api"
import { POIItem, CreatePOIDTO, POICategory } from "@/lib/poi-types"
import { toast } from "sonner"
import { useLanguage } from "@/lib/LanguageContext"
import { useHaptic } from "@/lib/hooks"

const IDB_POI_KEY_PREFIX = "tabidachi_user_poi_pool_"

export function usePoiPool(userId: string | null) {
    const { t } = useLanguage()
    const haptic = useHaptic()
    const swrKey = userId ? `poi_pool_${userId}` : null

    const { data: poiList, mutate, error, isLoading } = useSWR<POIItem[]>(
        swrKey,
        async () => {
            if (!userId) return []
            try {
                const remote = await poiPoolApi.getAll(userId)
                // 異步同步至本機 IndexedDB 快取 (0ms 離線可用)
                await set(`${IDB_POI_KEY_PREFIX}${userId}`, remote)
                return remote
            } catch (err) {
                // 網路斷線或離線時，降級從 IndexedDB 載入
                const cached = await get<POIItem[]>(`${IDB_POI_KEY_PREFIX}${userId}`)
                if (cached && Array.isArray(cached)) {
                    return cached
                }
                throw err
            }
        },
        {
            revalidateOnFocus: false,
            dedupingInterval: 30000,
        }
    )

    // 本機首次掛載時，先自 IndexedDB 灌水 (Hydration)
    useEffect(() => {
        if (!userId) return
        get<POIItem[]>(`${IDB_POI_KEY_PREFIX}${userId}`).then((cached) => {
            if (cached && Array.isArray(cached) && !poiList) {
                mutate(cached, false)
            }
        }).catch(() => {})
    }, [userId, poiList, mutate])

    // ➕ 貼上連結匯入 (單點或共享清單)
    const importLink = useCallback(async (url: string) => {
        if (!userId) {
            toast.error(t('profile_user_not_found') || "未找到使用者識別碼")
            return
        }

        const toastId = toast.loading(t('poi_importing') || "正在解析地點...")
        try {
            haptic.tap()
            const res = await poiPoolApi.importLink(url, userId)
            if (res.success && res.items?.length > 0) {
                haptic.success()
                await mutate((prev) => {
                    const current = prev || []
                    const newItems = res.items.filter((item: POIItem) => !current.some((c) => c.id === item.id))
                    const updated = [...newItems, ...current]
                    set(`${IDB_POI_KEY_PREFIX}${userId}`, updated).catch(() => {})
                    return updated
                }, false)

                toast.success(
                    t('poi_import_success', { count: res.count }) || `成功匯入 ${res.count} 個景點！`,
                    { id: toastId }
                )
            } else {
                toast.error(res.error || t('poi_import_failed') || "解析失敗，請確認連結", { id: toastId })
            }
        } catch (err) {
            console.error("[usePoiPool] importLink error:", err)
            haptic.error()
            toast.error(t('poi_import_failed') || "解析失敗，請確認連結格式", { id: toastId })
        }
    }, [userId, mutate, t, haptic])

    // ➕ 手動自訂新增 POI
    const addPoi = useCallback(async (dto: CreatePOIDTO) => {
        if (!userId) return
        try {
            haptic.tap()
            const newPoi = await poiPoolApi.create(dto, userId)
            await mutate((prev) => {
                const updated = [newPoi, ...(prev || [])]
                set(`${IDB_POI_KEY_PREFIX}${userId}`, updated).catch(() => {})
                return updated
            }, false)
            haptic.success()
        } catch (err) {
            console.error("[usePoiPool] addPoi error:", err)
            haptic.error()
        }
    }, [userId, mutate, haptic])

    // 📝 更新使用者自訂備註 (立即更新本機 + 遠端非同步同步)
    const updateNote = useCallback(async (id: string, note: string) => {
        if (!userId) return
        // 樂觀更新 (Optimistic UI)
        await mutate((prev) => {
            const updated = (prev || []).map((item) =>
                item.id === id ? { ...item, user_notes: note, updated_at: Date.now() } : item
            )
            set(`${IDB_POI_KEY_PREFIX}${userId}`, updated).catch(() => {})
            return updated
        }, false)

        try {
            await poiPoolApi.updateNote(id, note, userId)
        } catch (err) {
            console.error("[usePoiPool] updateNote error:", err)
        }
    }, [userId, mutate])

    // 📌 切換地圖釘選狀態 (is_pinned)
    const togglePin = useCallback(async (id: string, currentPinStatus: boolean) => {
        if (!userId) return
        const nextStatus = !currentPinStatus
        haptic.tap()

        // 樂觀更新
        await mutate((prev) => {
            const updated = (prev || []).map((item) =>
                item.id === id ? { ...item, is_pinned: nextStatus, updated_at: Date.now() } : item
            )
            set(`${IDB_POI_KEY_PREFIX}${userId}`, updated).catch(() => {})
            return updated
        }, false)

        try {
            await poiPoolApi.togglePin(id, nextStatus, userId)
            toast.success(nextStatus ? (t('poi_pinned_on_map') || "已釘選在地圖上") : (t('poi_unpinned') || "已取消釘選"))
        } catch (err) {
            console.error("[usePoiPool] togglePin error:", err)
        }
    }, [userId, mutate, t, haptic])

    // 🏷️ 更新分類 (類別/圖示切換)
    const updateCategory = useCallback(async (id: string, category: POICategory) => {
        if (!userId) return
        haptic.selection()

        // 樂觀更新
        await mutate((prev) => {
            const updated = (prev || []).map((item) =>
                item.id === id ? { ...item, category, updated_at: Date.now() } : item
            )
            set(`${IDB_POI_KEY_PREFIX}${userId}`, updated).catch(() => {})
            return updated
        }, false)

        try {
            await poiPoolApi.updateCategory(id, category, userId)
        } catch (err) {
            console.error("[usePoiPool] updateCategory error:", err)
        }
    }, [userId, mutate, haptic])

    // 🗑️ 刪除景點
    const deletePoi = useCallback(async (id: string) => {
        if (!userId) return
        haptic.tap()

        // 樂觀更新
        await mutate((prev) => {
            const updated = (prev || []).filter((item) => item.id !== id)
            set(`${IDB_POI_KEY_PREFIX}${userId}`, updated).catch(() => {})
            return updated
        }, false)

        try {
            await poiPoolApi.delete(id, userId)
            toast.success(t('delete') || "已刪除")
        } catch (err) {
            console.error("[usePoiPool] deletePoi error:", err)
        }
    }, [userId, mutate, t, haptic])

    return {
        poiList: poiList || [],
        isLoading,
        error,
        importLink,
        addPoi,
        updateNote,
        updateCategory,
        togglePin,
        deletePoi,
        mutate,
    }
}
