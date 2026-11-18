"use client"

import dynamic from "next/dynamic"
import { Suspense, useEffect } from "react"
import { usePathname } from "next/navigation"
import { initSessionLifecycleListener, fetchLatestRecoveryKey, isUserLoggedIn } from "@/lib/auth-session"
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

function OfficialRouteGuardedChatWidget() {
    const pathname = usePathname()
    if (pathname?.startsWith("/official")) {
        return null
    }
    return <ChatWidget />
}

function readActiveUserUuid(): string | null {
    if (typeof window === "undefined") return null;
    try {
        const raw = localStorage.getItem("user_uuid");
        if (!raw) return null;
        const trimmed = raw.trim();
        if (
            !trimmed ||
            trimmed === "null" ||
            trimmed === "undefined" ||
            trimmed.toLowerCase().startsWith("tbj_rec_")
        ) {
            return null;
        }
        return trimmed;
    } catch {
        return null;
    }
}

export function AppClientLayer() {
    const { lang } = useLanguage()
    const zh = lang === "zh"

    useEffect(() => {
        const cleanupSession = initSessionLifecycleListener();

        // 📡 全域跨裝置金鑰輪替即時廣播監聽 (Global Multi-Device Credential Sync)
        // 支援未登入訪客於 LandingPage 登入/引繼換帳號後動態綁定與清理舊頻道，無需整頁重載
        let activeUuid: string | null = null;
        let channelCleanup = () => {};

        const syncUserChannel = () => {
            if (typeof window === "undefined") return;
            const currentUuid = readActiveUserUuid();
            if (currentUuid === activeUuid) return;

            channelCleanup();
            channelCleanup = () => {};
            activeUuid = null;

            if (!currentUuid) return;

            const client = getSupabaseClient();
            if (client) {
                const channel = client.channel(`user-sync:${currentUuid}`);
                channel.on("broadcast", { event: "CREDENTIAL_ROTATED" }, () => {
                    fetchLatestRecoveryKey().catch(() => {});
                }).subscribe();
                activeUuid = currentUuid;
                channelCleanup = () => {
                    void Promise.resolve(client.removeChannel(channel)).catch(() => {});
                };
            }
        };

        const handleStorage = (e: StorageEvent) => {
            if (!e.key || e.key === "user_uuid") {
                syncUserChannel();
            }
        };

        syncUserChannel();
        window.addEventListener("user-login-state-changed", syncUserChannel);
        window.addEventListener("storage", handleStorage);

        return () => {
            window.removeEventListener("user-login-state-changed", syncUserChannel);
            window.removeEventListener("storage", handleStorage);
            channelCleanup();
            cleanupSession();
        };
    }, []);

    useEffect(() => {
        // 🔔 監聽金鑰本機更新事件並彈出輕量通知
        const handleKeyUpdated = (e: Event) => {
            const customEvent = e as CustomEvent<{ recoveryKey?: string; source?: string }>;
            if (!isUserLoggedIn()) return;
            if (customEvent.detail?.source !== "remote_sync") return;
            toast.info(zh ? "✨ 帳號引繼碼已自其他裝置同步更新" : "✨ Recovery key synced from another device");
        };
        window.addEventListener("tabiji:recovery_key_updated", handleKeyUpdated);

        return () => {
            window.removeEventListener("tabiji:recovery_key_updated", handleKeyUpdated);
        };
    }, [zh]);

    return (
        <>
            <Suspense fallback={null}>
                <OfficialRouteGuardedChatWidget />
            </Suspense>
            <SessionReauthModal />
        </>
    )
}


