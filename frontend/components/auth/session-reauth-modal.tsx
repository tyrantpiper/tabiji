"use client"

import React, { useState, useEffect, useCallback } from "react"
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { reanchorSessionWithKey, resetAndStartFreshSession, dismissReauthPrompt } from "@/lib/auth-session"
import { useLanguage } from "@/lib/LanguageContext"
import { ShieldAlert, KeyRound, RefreshCw, CheckCircle2, AlertTriangle, UserPlus } from "lucide-react"
import { toast } from "sonner"

const TBJ_REC_REGEX = /^tbj_rec_[0-9a-f]{8}_[0-9a-f]{32}$/i;

export function SessionReauthModal() {
    const { lang } = useLanguage()
    const zh = lang === "zh"

    const [isOpen, setIsOpen] = useState(false)
    const [recoveryKeyInput, setRecoveryKeyInput] = useState("")
    const [isSubmitting, setIsSubmitting] = useState(false)
    const [errorMessage, setErrorMessage] = useState<string | null>(null)
    const [customReason, setCustomReason] = useState<string | null>(null)
    const [isSuccess, setIsSuccess] = useState(false)

    useEffect(() => {
        const handleReauthRequired = (e: Event) => {
            const customEvent = e as CustomEvent<{ reason?: string }>;
            const reason = customEvent.detail?.reason;
            setCustomReason(reason || null);
            setIsOpen(true);
            setErrorMessage(null);
            setIsSuccess(false);
        };

        window.addEventListener("tabiji:session_reauth_required", handleReauthRequired);
        window.addEventListener("tabiji:credential_upgrade_required", handleReauthRequired);
        return () => {
            window.removeEventListener("tabiji:session_reauth_required", handleReauthRequired);
            window.removeEventListener("tabiji:credential_upgrade_required", handleReauthRequired);
        };
    }, []);

    const handleRestore = useCallback(async () => {
        const cleanKey = recoveryKeyInput.trim()
        if (!cleanKey) {
            setErrorMessage(zh ? "請輸入引繼碼" : "Please enter recovery key")
            return
        }

        if (!TBJ_REC_REGEX.test(cleanKey)) {
            setErrorMessage(zh ? "引繼碼驗證失敗，無法在此設備恢復同步。請確認引繼碼是否正確。" : "Verification failed. Unable to restore sync on this device. Please verify recovery key.")
            return
        }

        setIsSubmitting(true)
        setErrorMessage(null)

        try {
            await reanchorSessionWithKey(cleanKey)
            setIsSuccess(true)
            toast.success(zh ? "✨ 引繼碼驗證成功！雲端同步已無縫復原。" : "✨ Re-authenticated successfully! Sync restored.")
            setTimeout(() => {
                setIsOpen(false)
                setIsSuccess(false)
                setRecoveryKeyInput("")
            }, 800)
        } catch (err) {
            const msg = err instanceof Error ? err.message : String(err)
            setErrorMessage(msg)
        } finally {
            setIsSubmitting(false)
        }
    }, [recoveryKeyInput, zh])

    const handleDismissOffline = () => {
        dismissReauthPrompt()
        setIsOpen(false)
        setErrorMessage(null)
        toast.info(zh ? "已暫時切換為離線模式，本機行程安全保留中。" : "Offline mode active. Local data is safely preserved.")
    }

    return (
        <Dialog open={isOpen} onOpenChange={(open) => {
            if (!open && !isSubmitting) {
                handleDismissOffline()
            }
        }}>
            <DialogContent
                className="max-w-md p-6 bg-[#FCFBF7] dark:bg-[#151E1C] border-[#0B3026]/10 dark:border-white/10 rounded-2xl shadow-2xl"
                showCloseButton={!isSubmitting}
            >
                <DialogHeader className="space-y-3">
                    <div className="w-12 h-12 rounded-xl bg-[#E56E25]/10 dark:bg-[#E56E25]/20 flex items-center justify-center text-[#E56E25]">
                        <ShieldAlert className="w-6 h-6" />
                    </div>
                    <DialogTitle className="text-lg font-bold text-[#1E2927] dark:text-[#E5EBEA]">
                        {zh ? "需要原地驗證最新引繼碼" : "In-Place Re-authentication Required"}
                    </DialogTitle>
                    <DialogDescription className="text-xs text-[#1E2927]/70 dark:text-[#E5EBEA]/70 leading-relaxed space-y-1.5">
                        {customReason && (
                            <span className="block font-medium text-[#E56E25] bg-[#E56E25]/10 p-2 rounded-lg border border-[#E56E25]/20">
                                ⚠️ {customReason}
                            </span>
                        )}
                        <span className="block">
                            {zh
                                ? "您的本機離線行程與記帳完全安全保留中（可隨意滑動瀏覽）。由於憑證已在其他裝置輪替更新或過期，雲端同步動作已暫時凍結。"
                                : "Your local offline itineraries and expenses are safely preserved. Cloud synchronization is temporarily frozen because your credentials were rotated on another device."}
                        </span>
                        <span className="block text-[#1E2927]/90 dark:text-[#E5EBEA]/90 font-medium">
                            {zh
                                ? "請在此直接貼上最新引繼碼以「原地復原連線」，您無需登出！"
                                : "Please paste your latest recovery key to restore connection in-place without logging out!"}
                        </span>
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-3 my-2">
                    <div className="relative">
                        <KeyRound className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#1E2927]/40 dark:text-[#E5EBEA]/40" />
                        <Input
                            value={recoveryKeyInput}
                            onChange={(e) => {
                                setRecoveryKeyInput(e.target.value)
                                if (errorMessage) setErrorMessage(null)
                            }}
                            placeholder="tbj_rec_xxxxxxxx_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                            className="pl-10 text-xs font-mono bg-white dark:bg-[#0B1514] border-[#0B3026]/15 dark:border-white/15 focus:border-[#E56E25]"
                            disabled={isSubmitting || isSuccess}
                            autoComplete="off"
                            autoCapitalize="off"
                            spellCheck="false"
                        />
                    </div>

                    {errorMessage && (
                        <div className="flex items-start gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-600 dark:text-red-400 text-xs animate-in fade-in-50">
                            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                            <span className="leading-tight">{errorMessage}</span>
                        </div>
                    )}

                    {isSuccess && (
                        <div className="flex items-center gap-2 p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-600 dark:text-emerald-400 text-xs animate-in fade-in-50">
                            <CheckCircle2 className="w-4 h-4 shrink-0" />
                            <span>{zh ? "驗證成功，正在喚醒同步佇列..." : "Verified! Resuming outbox..."}</span>
                        </div>
                    )}
                </div>

                <DialogFooter className="flex flex-col-reverse sm:flex-row gap-2 pt-2">
                    <Button
                        type="button"
                        variant="ghost"
                        onClick={async () => {
                            if (typeof window !== "undefined" && window.confirm(zh ? "確定要清除本機失效引繼碼並建立全新訪客帳號嗎？" : "Clear invalid recovery key and create a new account?")) {
                                setIsSubmitting(true);
                                try {
                                    await resetAndStartFreshSession();
                                    toast.success(zh ? "已建立全新訪客帳號，雲端連線已復原。" : "Created fresh account, sync restored.");
                                    setIsOpen(false);
                                    window.location.reload();
                                } catch {
                                    toast.error(zh ? "重設失敗，請重試" : "Failed to reset");
                                } finally {
                                    setIsSubmitting(false);
                                }
                            }
                        }}
                        disabled={isSubmitting || isSuccess}
                        className="w-full sm:w-auto text-xs text-red-500/80 hover:text-red-600 hover:bg-red-500/10 rounded-xl h-10"
                    >
                        <UserPlus className="w-3.5 h-3.5 mr-1.5" />
                        {zh ? "重設為全新帳號" : "Reset & Start Fresh"}
                    </Button>
                    <div className="flex-1" />
                    <Button
                        type="button"
                        variant="ghost"
                        onClick={handleDismissOffline}
                        disabled={isSubmitting || isSuccess}
                        className="w-full sm:w-auto text-xs text-[#1E2927]/60 dark:text-[#E5EBEA]/60 hover:bg-black/5 dark:hover:bg-white/5 rounded-xl h-10"
                    >
                        {zh ? "稍後驗證 (保持離線)" : "Dismiss (Stay Offline)"}
                    </Button>
                    <Button
                        type="button"
                        onClick={handleRestore}
                        disabled={isSubmitting || isSuccess || !recoveryKeyInput.trim()}
                        className="w-full sm:w-auto text-xs bg-[#0B3026] hover:bg-[#13493B] text-white dark:bg-[#E56E25] dark:hover:bg-[#F2823A] rounded-xl h-10 font-medium shadow-sm transition-all"
                    >
                        {isSubmitting ? (
                            <>
                                <RefreshCw className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                                {zh ? "驗證中..." : "Verifying..."}
                            </>
                        ) : (
                            <>
                                <KeyRound className="w-3.5 h-3.5 mr-1.5" />
                                {zh ? "恢復連線與同步" : "Restore Connection"}
                            </>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
