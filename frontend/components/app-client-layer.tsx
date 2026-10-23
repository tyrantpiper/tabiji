"use client"

import dynamic from "next/dynamic"
import { Suspense, useEffect } from "react"
import { initSessionLifecycleListener, fetchLatestRecoveryKey } from "@/lib/auth-session"
import { getSupabaseClient } from "@/lib/supabase"
import { useLanguage } from "@/lib/LanguageContext"
import { toast } from "sonner"

import { SessionReauthModal } from "@/components/auth/session-reauth-modal"

// 🚀 [Perf Audit 2026] 建立客戶端隔離區 (Client Boundary)
// 1. 解決 Server Component (layout.tsx) 不能直接使用 ssr:false dynamic 的限制
// 2. 確保 AI 機器人在背景獨立 Hydrate，不阻塞首屏渲染
// 3. 🛡️ 於頂層守護 Session 生命週期（斷網恢復自動領票、前台喚醒自癒、跨裝置即時金鑰同步、401 原地熱重錨）
const ChatWidget = dynamic(() => import("@/components/chat-widget").then(mod => mod.default), {
    ssr: false,
})

export function AppClientLayer() {
    const { lang } = useLanguage()
    const zh = lang === "zh"

    useEffect(() => {
        const cleanupSession = initSessionLifecycleListener();

        // 📡 全域跨裝置金鑰輪替即時廣播監聽 (Global Multi-Device Credential Sync)
        let channelCleanup = () => {};
        if (typeof window !== "undefined") {
            const currentUuid = localStorage.getItem("user_uuid");
            if (currentUuid) {
                const client = getSupabaseClient();
                if (client) {
                    const channel = client.channel(`user-sync:${currentUuid}`);
                    channel.on("broadcast", { event: "CREDENTIAL_ROTATED" }, () => {
                        fetchLatestRecoveryKey().catch(() => {});
                    }).subscribe();
                    channelCleanup = () => {
                        client.removeChannel(channel);
                    };
                }
            }
        }

        // 🔔 監聽金鑰本機更新事件並彈出輕量通知
        const handleKeyUpdated = () => {
            toast.info(zh ? "✨ 帳號引繼碼已自其他裝置同步更新" : "✨ Recovery key synced from another device");
        };
        window.addEventListener("tabiji:recovery_key_updated", handleKeyUpdated);

        return () => {
            cleanupSession();
            channelCleanup();
            window.removeEventListener("tabiji:recovery_key_updated", handleKeyUpdated);
        };
    }, [zh]);

    return (
        <>
            <Suspense fallback={null}>
                <ChatWidget />
            </Suspense>
            <SessionReauthModal />
        </>
    )
}


