"use client"

import { useState, useEffect, useCallback, useRef } from "react"

export interface UseIdleBreathingOptions {
    /** 閒置觸發延遲 (毫秒)，預設 2500ms */
    idleTimeoutMs?: number
    /** 是否啟用呼吸降敏 (例如未吸頂時可傳 false)，預設 true */
    enabled?: boolean
}

/**
 * 🌬️ useIdleBreathing
 * 閒置呼吸降敏狀態機：
 * - 停止操作/滾動達指定時間後進入 20% 極透降敏態
 * - 滾動、游標 Hover 或手指觸控瞬間以 150ms 極速甦醒
 */
export function useIdleBreathing(
    scrollerEl: HTMLElement | null,
    options: UseIdleBreathingOptions = {}
) {
    const { idleTimeoutMs = 2500, enabled = true } = options
    const [isIdle, setIsIdle] = useState(false)
    const [isInteracting, setIsInteracting] = useState(false)
    const [prevEnabled, setPrevEnabled] = useState(enabled)
    const idleTimerRef = useRef<NodeJS.Timeout | null>(null)

    // 當 enabled 狀態切換時 (例如從未吸頂切換至吸頂)，重設為甦醒態
    if (prevEnabled !== enabled) {
        setPrevEnabled(enabled)
        setIsIdle(false)
    }

    const wakeUp = useCallback(() => {
        setIsIdle(false)
        if (idleTimerRef.current) {
            clearTimeout(idleTimerRef.current)
        }
        if (enabled) {
            idleTimerRef.current = setTimeout(() => {
                setIsIdle(true)
            }, idleTimeoutMs)
        }
    }, [enabled, idleTimeoutMs])

    // 監聽滾動喚醒與排程閒置降敏
    useEffect(() => {
        if (!enabled) {
            if (idleTimerRef.current) clearTimeout(idleTimerRef.current)
            return
        }

        idleTimerRef.current = setTimeout(() => {
            setIsIdle(true)
        }, idleTimeoutMs)

        const handleScroll = () => {
            wakeUp()
        }

        if (scrollerEl) {
            scrollerEl.addEventListener("scroll", handleScroll, { passive: true })
        }

        return () => {
            if (scrollerEl) {
                scrollerEl.removeEventListener("scroll", handleScroll)
            }
            if (idleTimerRef.current) {
                clearTimeout(idleTimerRef.current)
            }
        }
    }, [scrollerEl, enabled, idleTimeoutMs, wakeUp])

    // 滑鼠 Hover 處理 (Touch-Safe: 僅對 mouse 生效)
    const handlePointerEnter = useCallback((e: React.PointerEvent) => {
        if (e.pointerType === "mouse") {
            setIsInteracting(true)
            setIsIdle(false)
        }
    }, [])

    const handlePointerLeave = useCallback((e: React.PointerEvent) => {
        if (e.pointerType === "mouse") {
            setIsInteracting(false)
            wakeUp()
        }
    }, [wakeUp])

    // 手指觸碰瞬間甦醒
    const handleTouchWake = useCallback(() => {
        setIsInteracting(true)
        wakeUp()
        setTimeout(() => setIsInteracting(false), 500)
    }, [wakeUp])

    const isDimmed = enabled && isIdle && !isInteracting

    return {
        isDimmed,
        wakeUp,
        handlers: {
            onPointerEnter: handlePointerEnter,
            onPointerLeave: handlePointerLeave,
            onPointerDown: handleTouchWake,
            onTouchStart: handleTouchWake
        }
    }
}
