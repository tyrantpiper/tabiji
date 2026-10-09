"use client"

import { useState, useEffect, useCallback } from "react"
import { AnimatePresence } from "framer-motion"
import { TabijiSplashAnimation } from "./splash/tabiji-splash-animation"

export function SplashScreen() {
    const [show, setShow] = useState(true)
    const [isStandalone, setIsStandalone] = useState(false)
    const [renderKey, setRenderKey] = useState(0)

    // 檢查 PWA 模式和是否已顯示過閃屏 (支援 ?splash=1 強制預覽與重播)
    useEffect(() => {
        const isDev = process.env.NODE_ENV === "development"
        const urlParams = new URLSearchParams(window.location.search)
        const forcePreview = urlParams.has("splash") || (isDev && urlParams.has("preview"))

        // 檢查是否為 PWA 模式或開發者顯式調試預覽
        const standalone =
            forcePreview ||
            window.matchMedia("(display-mode: standalone)").matches ||
            (window.navigator as unknown as { standalone?: boolean }).standalone === true
        // eslint-disable-next-line react-hooks/set-state-in-effect -- PWA detection requires init on mount
        setIsStandalone(standalone)

        // 檢查是否已經顯示過（若 forcePreview 則忽略 sessionStorage 限制，允許反覆調試預覽）
        const hasShown =
            !forcePreview &&
            (sessionStorage.getItem("tabiji_splash_shown") ||
                sessionStorage.getItem("splash_shown"))

        if (hasShown || !standalone) {
            setShow(false)
            // 🛡️ 不需播放開屏動畫時，立即釋放硬骨架屏
            if (typeof window !== "undefined" && typeof (window as unknown as { __dismissHardSkeleton?: () => void }).__dismissHardSkeleton === "function") {
                (window as unknown as { __dismissHardSkeleton: () => void }).__dismissHardSkeleton()
            }
            return
        }

        // 綁定全域調試函式，方便開發者在控制台隨時重播動畫
        if (typeof window !== "undefined") {
            ;(window as unknown as { __replayTabijiSplash?: () => void }).__replayTabijiSplash = () => {
                setIsStandalone(true)
                setShow(true)
                setRenderKey(prev => prev + 1)
            }
        }
    }, [])

    const handleComplete = useCallback(() => {
        setShow(false)
        sessionStorage.setItem("tabiji_splash_shown", "true")
        if (typeof window !== "undefined" && typeof (window as unknown as { __dismissHardSkeleton?: () => void }).__dismissHardSkeleton === "function") {
            (window as unknown as { __dismissHardSkeleton: () => void }).__dismissHardSkeleton()
        }
    }, [])

    // 非 PWA 模式且非強制預覽則不顯示
    if (!isStandalone) return null

    return (
        <AnimatePresence mode="wait">
            {show && <TabijiSplashAnimation key={renderKey} onComplete={handleComplete} />}
        </AnimatePresence>
    )
}

