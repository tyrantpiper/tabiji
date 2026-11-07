"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import {
    Bot, Server, Key, Copy, Check, Eye, EyeOff, AlertTriangle, Loader2, RefreshCw, Fingerprint, Info
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
    Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger, DialogFooter
} from "@/components/ui/dialog"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { useLanguage } from "@/lib/LanguageContext"
import { useHaptic } from "@/lib/hooks"
import { getValidSessionToken } from "@/lib/auth-session"
import { useTripStore } from "@/lib/stores/tripStore"
import { toast } from "sonner"
import { cn } from "@/lib/utils"

interface MCPConnectorDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    trigger?: React.ReactNode
}

export function MCPConnectorDialog({ open, onOpenChange, trigger }: MCPConnectorDialogProps) {
    const { t, lang } = useLanguage()
    const zh = lang === "zh"
    const haptic = useHaptic()

    const urlInputRef = useRef<HTMLInputElement>(null)
    const clientIdInputRef = useRef<HTMLInputElement>(null)
    const tokenInputRef = useRef<HTMLInputElement>(null)

    const storeUserId = useTripStore((state) => state.userId)

    const [mounted, setMounted] = useState(false)
    const [clientId, setClientId] = useState<string>("")
    const [token, setToken] = useState<string>("")
    const [isLoadingToken, setIsLoadingToken] = useState<boolean>(false)
    const [showToken, setShowToken] = useState<boolean>(false)
    const [copiedField, setCopiedField] = useState<"url" | "clientId" | "token" | null>(null)

    // 🌐 客戶端掛載偵測以計算 Origin 網址與 HTTPS 狀態及用戶端識別碼
    useEffect(() => {
        // eslint-disable-next-line react-hooks/set-state-in-effect -- SSR hydration safety
        setMounted(true)
        const storedId = (typeof window !== "undefined" ? localStorage.getItem("user_uuid") : null) || storeUserId || ""
        setClientId(storedId)
    }, [storeUserId])

    const serverUrl = mounted && typeof window !== "undefined" ? `${window.location.origin}/api/mcp` : ""
    const isNonHttps = mounted && typeof window !== "undefined" && window.location.protocol !== "https:"

    // 🛡️ 手動刷新/重試獲取標準長效 Session JWT
    const loadToken = useCallback((showLoading = true) => {
        if (showLoading) setIsLoadingToken(true)
        return getValidSessionToken()
            .then((sessionToken) => {
                setToken(sessionToken || "")
                if (sessionToken && !clientId) {
                    try {
                        const parts = sessionToken.split(".")
                        if (parts.length === 3) {
                            const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/")
                            const jsonStr = typeof atob !== "undefined"
                                ? decodeURIComponent(atob(base64).split("").map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2)).join(""))
                                : Buffer.from(base64, "base64").toString("utf-8")
                            const payload = JSON.parse(jsonStr)
                            if (payload?.sub) {
                                setClientId(payload.sub)
                            }
                        }
                    } catch {
                        // ignore
                    }
                }
            })
            .catch((err) => {
                console.warn("Failed to load session JWT for MCP:", err)
            })
            .finally(() => {
                setIsLoadingToken(false)
            })
    }, [clientId])

    // 🛡️ 自動獲取標準簽署之長效 Session JWT (避免原始引繼碼 tbj_rec_* 混淆導致 401 拒絕)
    useEffect(() => {
        if (!open) return
        let isCancelled = false
        // eslint-disable-next-line react-hooks/set-state-in-effect -- Dialog open async bootstrap
        setIsLoadingToken(true)

        const storedId = (typeof window !== "undefined" ? localStorage.getItem("user_uuid") : null) || storeUserId || ""
        setClientId(storedId)

        getValidSessionToken()
            .then((sessionToken) => {
                if (!isCancelled) {
                    setToken(sessionToken || "")
                    if (!storedId && sessionToken) {
                        try {
                            const parts = sessionToken.split(".")
                            if (parts.length === 3) {
                                const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/")
                                const jsonStr = typeof atob !== "undefined"
                                    ? decodeURIComponent(atob(base64).split("").map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2)).join(""))
                                    : Buffer.from(base64, "base64").toString("utf-8")
                                const payload = JSON.parse(jsonStr)
                                if (payload?.sub) {
                                    setClientId(payload.sub)
                                }
                            }
                        } catch {
                            // ignore
                        }
                    }
                }
            })
            .catch((err) => {
                console.warn("Failed to load session JWT for MCP:", err)
            })
            .finally(() => {
                if (!isCancelled) {
                    setIsLoadingToken(false)
                }
            })

        return () => {
            isCancelled = true
        }
    }, [open, storeUserId])

    // 📋 安全剪貼簿複製：優先使用 Clipboard API，失敗時退回 execCommand，再失敗退回文字選取
    const handleCopy = useCallback(async (text: string, field: "url" | "clientId" | "token") => {
        if (!text) return
        haptic.tap()
        let succeeded = false

        if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
            try {
                await navigator.clipboard.writeText(text)
                succeeded = true
            } catch {
                succeeded = false
            }
        }

        if (!succeeded) {
            try {
                const textArea = document.createElement("textarea")
                textArea.value = text
                textArea.style.position = "fixed"
                textArea.style.left = "-9999px"
                textArea.style.top = "-9999px"
                textArea.setAttribute("readonly", "")
                document.body.appendChild(textArea)
                textArea.focus()
                textArea.select()
                textArea.setSelectionRange(0, text.length)
                succeeded = document.execCommand("copy")
                document.body.removeChild(textArea)
            } catch {
                succeeded = false
            }
        }

        if (succeeded) {
            haptic.success()
            setCopiedField(field)
            setTimeout(() => setCopiedField(null), 2000)
            toast.success(t("mcp_copied_toast") || (zh ? "已複製到剪貼簿" : "Copied to clipboard"))
        } else {
            // 🛡️ 文字選取回退機制 (Text Selection Fallback)
            if (field === "token") {
                setShowToken(true)
                setTimeout(() => {
                    tokenInputRef.current?.focus()
                    tokenInputRef.current?.select()
                }, 50)
            } else if (field === "url") {
                urlInputRef.current?.focus()
                urlInputRef.current?.select()
            } else if (field === "clientId") {
                clientIdInputRef.current?.focus()
                clientIdInputRef.current?.select()
            }
            toast.error(t("mcp_copied_manual") || (zh ? "無法自動複製，已為您選取文字，請手動複製 (Ctrl+C / Cmd+C)" : "Failed to copy automatically. Text selected, please copy manually (Ctrl+C / Cmd+C)"))
        }
    }, [haptic, t, zh])

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            {trigger && <DialogTrigger asChild>{trigger}</DialogTrigger>}
            <DialogContent className="sm:max-w-md bg-white/95 dark:bg-[#1E2927]/95 backdrop-blur-xl border-[#0B3026]/10 dark:border-white/10 rounded-2xl shadow-xl">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-base font-bold text-[#1E2927] dark:text-[#E5EBEA]">
                        <Bot className="w-5 h-5 text-teal-600 dark:text-teal-400" />
                        {t("mcp_dialog_title")}
                    </DialogTitle>
                    <DialogDescription className="text-xs text-[#0B3026]/70 dark:text-[#88A29A]">
                        {t("mcp_dialog_desc")}
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-2">
                    {/* ⚠️ HTTP 非安全環境提示 (Cloud AI 需 HTTPS 端點) */}
                    {isNonHttps && (
                        <div className="rounded-xl p-3 bg-amber-500/10 border border-amber-500/25 text-amber-800 dark:text-amber-300 text-xs flex items-start gap-2.5">
                            <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                            <div className="space-y-1">
                                <div className="font-semibold">{zh ? "本機 HTTP 開發環境提示" : "Local HTTP Environment Notice"}</div>
                                <div className="text-[11px] leading-relaxed opacity-90">
                                    {zh
                                        ? "雲端 AI (Google Gemini / Perplexity) 需透過公開 HTTPS 網域 (如 Cloudflare Tunnel 或正式網址) 才能連線至此 MCP 端點。本機 localhost 端點僅供本地桌面工具連線。"
                                        : "Cloud AI services (Google Gemini / Perplexity) require a public HTTPS endpoint (e.g. via Cloudflare Tunnel) to connect to Tabiji MCP. Localhost endpoints are only reachable by local desktop clients."}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* 1. MCP Server URL */}
                    <div className="space-y-1.5">
                        <Label className="text-xs font-semibold text-[#0B3026]/70 dark:text-[#88A29A] flex items-center gap-1.5">
                            <Server className="w-3.5 h-3.5 text-teal-600 dark:text-teal-400" />
                            {t("mcp_server_url")}
                        </Label>
                        <div className="relative flex items-center">
                            <Input
                                ref={urlInputRef}
                                type="text"
                                value={serverUrl}
                                readOnly
                                className="font-mono text-xs pr-24 bg-black/5 dark:bg-white/5 border-[#0B3026]/15 dark:border-white/15 h-9"
                            />
                            <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => handleCopy(serverUrl, "url")}
                                className="absolute right-1 h-7 px-2 text-xs flex items-center gap-1 text-teal-700 dark:text-teal-300 hover:bg-teal-500/10"
                                aria-label={copiedField === "url" ? (zh ? "已複製" : "Copied") : t("mcp_copy_url")}
                            >
                                {copiedField === "url" ? (
                                    <>
                                        <Check className="w-3.5 h-3.5 text-emerald-600" />
                                        <span className="text-[11px] font-medium">{zh ? "已複製" : "Copied"}</span>
                                    </>
                                ) : (
                                    <>
                                        <Copy className="w-3.5 h-3.5" />
                                        <span className="text-[11px] font-medium">{t("mcp_copy_url")}</span>
                                    </>
                                )}
                            </Button>
                        </div>
                    </div>

                    {/* 2. Client ID */}
                    <div className="space-y-1.5">
                        <Label className="text-xs font-semibold text-[#0B3026]/70 dark:text-[#88A29A] flex items-center gap-1.5">
                            <Fingerprint className="w-3.5 h-3.5 text-teal-600 dark:text-teal-400" />
                            {t("mcp_client_id")}
                        </Label>
                        <div className="relative flex items-center">
                            <Input
                                ref={clientIdInputRef}
                                type="text"
                                value={clientId}
                                readOnly
                                placeholder={zh ? "尚無用戶端識別碼" : "No Client ID available"}
                                className="font-mono text-xs pr-24 bg-black/5 dark:bg-white/5 border-[#0B3026]/15 dark:border-white/15 h-9"
                            />
                            <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => handleCopy(clientId, "clientId")}
                                disabled={!clientId}
                                className="absolute right-1 h-7 px-2 text-xs flex items-center gap-1 text-teal-700 dark:text-teal-300 hover:bg-teal-500/10"
                                aria-label={copiedField === "clientId" ? (zh ? "已複製" : "Copied") : t("mcp_copy_client_id")}
                            >
                                {copiedField === "clientId" ? (
                                    <>
                                        <Check className="w-3.5 h-3.5 text-emerald-600" />
                                        <span className="text-[11px] font-medium">{zh ? "已複製" : "Copied"}</span>
                                    </>
                                ) : (
                                    <>
                                        <Copy className="w-3.5 h-3.5" />
                                        <span className="text-[11px] font-medium">{t("mcp_copy_client_id")}</span>
                                    </>
                                )}
                            </Button>
                        </div>
                    </div>

                    {/* 3. MCP Connection Token (JWT) */}
                    <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                            <Label className="text-xs font-semibold text-[#0B3026]/70 dark:text-[#88A29A] flex items-center gap-1.5">
                                <Key className="w-3.5 h-3.5 text-teal-600 dark:text-teal-400" />
                                {t("mcp_connection_token")}
                            </Label>
                            <div className="flex items-center gap-1">
                                <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => loadToken(true)}
                                    disabled={isLoadingToken}
                                    className="h-6 px-1.5 text-[11px] text-[#0B3026]/70 dark:text-[#88A29A] hover:text-teal-700 dark:hover:text-teal-300 hover:bg-teal-500/10 rounded-md transition-colors flex items-center gap-1"
                                    title={t("mcp_refresh_token") || (zh ? "重新整理憑證" : "Refresh Token")}
                                    aria-label={t("mcp_refresh_token") || (zh ? "重新整理憑證" : "Refresh Token")}
                                >
                                    <RefreshCw className={cn("w-3 h-3", isLoadingToken && "animate-spin")} />
                                    <span>{zh ? "重新整理" : "Refresh"}</span>
                                </Button>
                                <Button
                                    type="button"
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => setShowToken(!showToken)}
                                    className="h-6 px-1.5 text-[11px] text-[#0B3026]/70 dark:text-[#88A29A] hover:text-teal-700 dark:hover:text-teal-300 hover:bg-teal-500/10 rounded-md transition-colors flex items-center gap-1"
                                    title={showToken ? (zh ? "隱藏憑證" : "Hide Token") : (zh ? "顯示憑證" : "Show Token")}
                                    aria-label={showToken ? (zh ? "隱藏憑證" : "Hide Token") : (zh ? "顯示憑證" : "Show Token")}
                                >
                                    {showToken ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                                    <span>{showToken ? (zh ? "隱藏" : "Hide") : (zh ? "顯示" : "Show")}</span>
                                </Button>
                            </div>
                        </div>
                        <div className="relative flex items-center">
                            <Input
                                ref={tokenInputRef}
                                type={showToken ? "text" : "password"}
                                value={isLoadingToken ? (zh ? "正在取得安全連線憑證..." : "Fetching signed JWT...") : token}
                                readOnly
                                disabled={isLoadingToken}
                                placeholder={zh ? "尚無有效連線憑證" : "No connection token available"}
                                className="font-mono text-xs pr-24 bg-black/5 dark:bg-white/5 border-[#0B3026]/15 dark:border-white/15 h-9"
                            />
                            <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                onClick={() => handleCopy(token, "token")}
                                disabled={isLoadingToken || !token}
                                className="absolute right-1 h-7 px-2 text-xs flex items-center gap-1 text-teal-700 dark:text-teal-300 hover:bg-teal-500/10"
                                aria-label={copiedField === "token" ? (zh ? "已複製" : "Copied") : t("mcp_copy_token")}
                            >
                                {isLoadingToken ? (
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                ) : copiedField === "token" ? (
                                    <>
                                        <Check className="w-3.5 h-3.5 text-emerald-600" />
                                        <span className="text-[11px] font-medium">{zh ? "已複製" : "Copied"}</span>
                                    </>
                                ) : (
                                    <>
                                        <Copy className="w-3.5 h-3.5" />
                                        <span className="text-[11px] font-medium">{t("mcp_copy_token")}</span>
                                    </>
                                )}
                            </Button>
                        </div>
                    </div>

                    {/* 設定指引分頁 (Gemini & Perplexity) */}
                    <Tabs defaultValue="gemini" className="w-full pt-1">
                        <TabsList className="grid w-full grid-cols-2 bg-[#0B3026]/5 dark:bg-white/5 p-1 rounded-xl">
                            <TabsTrigger
                                value="gemini"
                                className="text-xs rounded-lg py-1.5 data-[state=active]:bg-white dark:data-[state=active]:bg-[#1E2927] data-[state=active]:shadow-xs"
                            >
                                {t("mcp_guide_gemini")}
                            </TabsTrigger>
                            <TabsTrigger
                                value="perplexity"
                                className="text-xs rounded-lg py-1.5 data-[state=active]:bg-white dark:data-[state=active]:bg-[#1E2927] data-[state=active]:shadow-xs"
                            >
                                {t("mcp_guide_perplexity")}
                            </TabsTrigger>
                        </TabsList>
                        <TabsContent value="gemini" className="mt-2.5 space-y-2.5">
                            {/* ℹ️ Google 帳號先決條件提醒 */}
                            <div className="rounded-xl p-3 bg-teal-500/10 border border-teal-500/25 text-teal-900 dark:text-teal-200 text-xs flex items-start gap-2.5">
                                <Info className="w-4 h-4 text-teal-600 dark:text-teal-400 shrink-0 mt-0.5" />
                                <div className="space-y-1">
                                    <div className="font-semibold">{zh ? "Google 帳號先決條件" : "Google Account Prerequisites"}</div>
                                    <div className="text-[11px] leading-relaxed opacity-90">
                                        {t("mcp_prerequisite_note")}
                                    </div>
                                </div>
                            </div>

                            <div className="rounded-xl bg-[#0B3026]/5 dark:bg-white/5 border border-[#0B3026]/10 dark:border-white/10 p-3 space-y-2 text-xs text-[#0B3026]/80 dark:text-[#E5EBEA]/80">
                                <div className="flex gap-2 items-start">
                                    <span className="w-4 h-4 rounded-full bg-teal-600/10 text-teal-600 dark:text-teal-400 font-bold flex items-center justify-center shrink-0 text-[10px] mt-0.5">1</span>
                                    <div>{zh ? "前往 Google Gemini「設定」中的「已連結的應用程式 (Connected Apps)」並點擊新增。" : "Open Google Gemini Settings -> Connected Apps and click Add."}</div>
                                </div>
                                <div className="flex gap-2 items-start">
                                    <span className="w-4 h-4 rounded-full bg-teal-600/10 text-teal-600 dark:text-teal-400 font-bold flex items-center justify-center shrink-0 text-[10px] mt-0.5">2</span>
                                    <div>{zh ? "第 1 欄：複製上方的「MCP 伺服器網址」並貼入 Endpoint 網址欄位。" : "Field 1: Copy 'MCP Server URL' above and paste into Endpoint URL."}</div>
                                </div>
                                <div className="flex gap-2 items-start">
                                    <span className="w-4 h-4 rounded-full bg-teal-600/10 text-teal-600 dark:text-teal-400 font-bold flex items-center justify-center shrink-0 text-[10px] mt-0.5">3</span>
                                    <div>{zh ? "第 2 與 3 欄：分別複製「客戶端 ID (Client ID)」與「連線憑證 (Client Secret / JWT)」填入對應欄位。" : "Fields 2 & 3: Copy 'Client ID' and 'Connection Token (Client Secret / JWT)' into their fields."}</div>
                                </div>
                                <div className="flex gap-2 items-start">
                                    <span className="w-4 h-4 rounded-full bg-teal-600/10 text-teal-600 dark:text-teal-400 font-bold flex items-center justify-center shrink-0 text-[10px] mt-0.5">4</span>
                                    <div>{zh ? "完成授權後，即可直接向 Gemini 詢問：「幫我查看 Tabiji 上的行程」或即時新增景點！" : "Save and start asking Gemini: 'View my Tabiji trips' or add new itinerary stops!"}</div>
                                </div>
                            </div>
                        </TabsContent>
                        <TabsContent value="perplexity" className="mt-2.5">
                            <div className="rounded-xl bg-[#0B3026]/5 dark:bg-white/5 border border-[#0B3026]/10 dark:border-white/10 p-3 space-y-2 text-xs text-[#0B3026]/80 dark:text-[#E5EBEA]/80">
                                <div className="flex gap-2 items-start">
                                    <span className="w-4 h-4 rounded-full bg-teal-600/10 text-teal-600 dark:text-teal-400 font-bold flex items-center justify-center shrink-0 text-[10px] mt-0.5">1</span>
                                    <div>{zh ? "進入 Perplexity「Settings」->「MCP Connectors / External Tools」。" : "Navigate to Perplexity Settings -> MCP Connectors / External Tools."}</div>
                                </div>
                                <div className="flex gap-2 items-start">
                                    <span className="w-4 h-4 rounded-full bg-teal-600/10 text-teal-600 dark:text-teal-400 font-bold flex items-center justify-center shrink-0 text-[10px] mt-0.5">2</span>
                                    <div>{zh ? "新增自訂伺服器，將 Tabiji 的「MCP 伺服器網址」填入。" : "Add a custom server and enter the Tabiji MCP Server URL."}</div>
                                </div>
                                <div className="flex gap-2 items-start">
                                    <span className="w-4 h-4 rounded-full bg-teal-600/10 text-teal-600 dark:text-teal-400 font-bold flex items-center justify-center shrink-0 text-[10px] mt-0.5">3</span>
                                    <div>{zh ? "展開「進階 (Advanced)」：將驗證選為「API 金鑰 (API Key)」並貼入「連線憑證」；或選「OAuth」分別填入「客戶端 ID」與「連線憑證」。" : "Under Advanced: select 'API Key' and paste 'Connection Token', or select 'OAuth' and fill in 'Client ID' & 'Connection Token'."}</div>
                                </div>
                                <div className="flex gap-2 items-start">
                                    <span className="w-4 h-4 rounded-full bg-teal-600/10 text-teal-600 dark:text-teal-400 font-bold flex items-center justify-center shrink-0 text-[10px] mt-0.5">4</span>
                                    <div>{zh ? "儲存後即可在 Perplexity 查詢中即時調用 Tabiji 行程資料與景點推薦。" : "Enable to allow Perplexity to seamlessly read and modify your Tabiji trips."}</div>
                                </div>
                            </div>
                        </TabsContent>
                    </Tabs>
                </div>

                <DialogFooter className="pt-2">
                    <Button
                        type="button"
                        onClick={() => onOpenChange(false)}
                        className="w-full bg-[#1E2927] hover:bg-[#2A3B37] text-white dark:bg-white dark:text-[#1E2927] dark:hover:bg-white/90 h-9 text-xs font-semibold rounded-xl"
                    >
                        {zh ? "完成" : "Done"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
