"use client"

import dynamic from "next/dynamic"
import { Suspense, useEffect } from "react"
import { initSessionLifecycleListener } from "@/lib/auth-session"

// 🚀 [Perf Audit 2026] 建立客戶端隔離區 (Client Boundary)
// 1. 解決 Server Component (layout.tsx) 不能直接使用 ssr:false dynamic 的限制
// 2. 確保 AI 機器人在背景獨立 Hydrate，不阻塞首屏渲染
// 3. 🛡️ 於頂層守護 Session 生命週期（斷網恢復自動領票、前台喚醒自癒）
const ChatWidget = dynamic(() => import("@/components/chat-widget").then(mod => mod.default), {
    ssr: false,
})

export function AppClientLayer() {
    useEffect(() => {
        return initSessionLifecycleListener();
    }, []);

    return (
        <Suspense fallback={null}>
            <ChatWidget />
        </Suspense>
    )
}
