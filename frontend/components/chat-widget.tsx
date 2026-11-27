"use client"

import { useState, useRef, useEffect, useCallback, useMemo } from "react"
import { X, User } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useTripContext } from "@/lib/trip-context"
import { useFocusedDay } from "@/lib/stores/tripStore"
import { useTripDetail } from "@/lib/hooks"
import { useDynamicPolling } from "@/lib/polling-manager"
import { getSecureApiKey } from "@/lib/security"
import { getLeanItinerary, LeanItinerary } from "@/lib/getLeanItinerary"
import SourceCitation from "@/components/chat/SourceCitation"
import ThinkingIndicator from "@/components/chat/ThinkingIndicator"
import POIPreviewCard, { extractItineraryFunctionCalls } from "@/components/chat/POIPreviewCard"
import BatchPOIPreviewCard from "@/components/chat/BatchPOIPreviewCard"
import RemoveItemPreviewCard, { extractRemoveFunctionCall } from "@/components/chat/RemoveItemPreviewCard"
import ExpensePreviewCard, { extractExpenseFunctionCall } from "@/components/chat/ExpensePreviewCard"
import DeepResearchCard, { type DeepResearchData } from "@/components/chat/DeepResearchCard"
import ChatComposer from "@/components/chat/ChatComposer"
import { streamChat, streamDeepResearch, sanitizeGroundingSources } from "@/lib/sse-parser"
import { setSearchCache } from "@/lib/search-cache"
import { toast } from "sonner"
import { API_HOST } from "@/lib/api"
import { useWeatherStore } from "@/lib/stores/weatherStore"
import { debugLog } from "@/lib/debug"
import { useLanguage, type TranslationKey } from "@/lib/LanguageContext"
import { compressImage, isImageFile, readImageFileAsDataUrl } from "@/lib/image-utils"
import { type ParsedItinerary, type ParsedItineraryItem } from "@/lib/itinerary-types"
import * as authSession from "@/lib/auth-session"

// 🆕 Part 結構 (與 Gemini API 對應，支援駝峰與蛇形雙格式)
interface Part {
    text?: string
    function_call?: { name: string; args: Record<string, unknown> }
    functionCall?: { name: string; args: Record<string, unknown> }
    thought?: string  // 思想簽名 (加密)
    _raw?: string
}

// 🆕 v22.1: JSON 防漏閥與行程偵測
function tryParseItinerary(text: string): ParsedItinerary | null {
    if (!text || !text.includes('{"')) return null
    try {
        // 嘗試提取 JSON (處理可能存在的 Markdown 標籤)
        const cleanJson = text.replace(/```json|```/g, "").trim()
        const data = JSON.parse(cleanJson)
        if (data.items && Array.isArray(data.items)) {
            return data as ParsedItinerary
        }
        // 處理嵌套在 data 裡的情況
        if (data.data && data.data.items) {
            return data.data as ParsedItinerary
        }
    } catch (error) {
        console.error("Failed to parse itinerary from chat content:", error)
        return null
    }
    return null
}

// 🆕 來源標籤
interface GroundingSource {
    title: string
    uri: string
    citation_index?: number
    category?: string
    badge?: {
        text: string
        color?: string
    }
    snippet?: string
}

interface Message {
    role: "user" | "model"
    displayContent: string    // UI 渲染用的文字
    rawParts: Part[]          // 🔒 Round-trip 回後端 (含 thought_signature)
    groundingSources?: GroundingSource[]  // 來源標籤 (如有)
    modelUsed?: string        // 使用的模型 (調試用)
    sources?: Array<{ title: string; url: string }>  // 🆕 v3.7.1: 三源引用
    researchData?: DeepResearchData // 🆕 v2026: Antigravity 深度研究數據
}

interface Position {
    x: number
    y: number
}

// 城市座標映射
const CITY_COORDS: Record<string, { lat: number; lng: number }> = {
    "東京": { lat: 35.6895, lng: 139.6917 },
    "tokyo": { lat: 35.6895, lng: 139.6917 },
    "大阪": { lat: 34.6937, lng: 135.5023 },
    "osaka": { lat: 34.6937, lng: 135.5023 },
    "京都": { lat: 35.0116, lng: 135.7681 },
    "kyoto": { lat: 35.0116, lng: 135.7681 },
    "福岡": { lat: 33.5904, lng: 130.4017 },
    "名古屋": { lat: 35.1815, lng: 136.9066 },
    "札幌": { lat: 43.0618, lng: 141.3545 },
    "沖繩": { lat: 26.2124, lng: 127.6809 },
}

/** 🆕 Read device safe area bottom inset from CSS env() bridge */
function getSafeAreaBottom(): number {
    if (typeof window === 'undefined') return 0
    const val = getComputedStyle(document.documentElement).getPropertyValue('--sab').trim()
    return parseInt(val, 10) || 0
}

export default function ChatWidget() {
    const { t, lang } = useLanguage()
    const zh = lang === "zh"
    // 🔒 登錄狀態檢查 - 未登錄時不顯示聊天氣泡
    const [isLoggedIn, setIsLoggedIn] = useState(false)
    const [isDeepResearch, setIsDeepResearch] = useState(false)

    useEffect(() => {
        // 初始檢查
        const checkLogin = () => {
            const rawUserId = localStorage.getItem("user_uuid")?.trim()
            const userName = localStorage.getItem("user_nickname")?.trim()
            const hasValidId = Boolean(rawUserId && rawUserId !== "null" && rawUserId !== "undefined")
            setIsLoggedIn(Boolean(hasValidId && userName))
        }
        checkLogin()

        // 監聽 storage 變化 (跨 tab 同步)
        window.addEventListener('storage', checkLogin)
        // 🆕 監聯同 tab 登入狀態變化
        window.addEventListener('user-login-state-changed', checkLogin)
        return () => {
            window.removeEventListener('storage', checkLogin)
            window.removeEventListener('user-login-state-changed', checkLogin)
        }
    }, [])

    // 🔒 登錄狀態 - 在 JSX 中使用此變數決定是否渲染

    // ✅ 直接使用 TripContext（現在 ChatWidget 在 TripProvider 內）
    const { activeTrip, activeTripId, userId: contextUserId } = useTripContext()

    // 🆕 取得行程詳細資料 (包含 items)
    // 🔧 FIX: 傳入 contextUserId 確保 SWR 鍵值完整
    // 🔧 FIX 2: 加入 useDynamicPolling 的 refreshInterval，對齊 ItineraryView 的 SWR Key 實現快取共用
    const refreshInterval = useDynamicPolling()
    const { trip: tripDetail } = useTripDetail(activeTripId, contextUserId, refreshInterval)
    const weatherStore = useWeatherStore()

    // 從行程標題解析位置（即時更新）
    const tripLocation = useMemo(() => {
        if (!activeTrip?.title) return null
        const titleLower = (activeTrip.title as string).toLowerCase()
        for (const [city, coords] of Object.entries(CITY_COORDS)) {
            if (titleLower.includes(city)) {
                return { ...coords, name: city }
            }
        }
        return null
    }, [activeTrip])

    const focusedDay = useFocusedDay()
    // 🆕 產生精簡版行程供 AI 使用 (含 day_notes/costs/checklists/tickets)
    const leanItinerary: LeanItinerary | null = useMemo(() => {
        if (!activeTrip || !tripDetail) return null // 🔧 FIX: Don't check for .items yet

        // 🔧 2026 FIX: Flatten API 'days' structure to 'items' & map keys
        let items = tripDetail.items
        if (!items && tripDetail.days && Array.isArray(tripDetail.days)) {
            items = (tripDetail.days as Array<{ day: number; activities: Array<Record<string, unknown> & { time: string; place: string }> }>).flatMap((d) =>
                d.activities.map((act) => ({
                    ...act,
                    day_number: d.day,
                    time_slot: act.time,      // Map API 'time' to 'time_slot'
                    place_name: act.place     // Map API 'place' to 'place_name'
                }))
            )
        }

        // 即使為 0 景點新行程，只要有 title 或 flight_info 亦回傳骨架供即時票價上下文使用
        const safeItems = Array.isArray(items) ? items : []
        const tripFlightInfo = tripDetail.flight_info || (activeTrip as { flight_info?: LeanItinerary["flight_info"] }).flight_info
        if (safeItems.length === 0 && !activeTrip.title?.trim() && !tripFlightInfo) return null

        const lean = getLeanItinerary(
            {
                ...activeTrip,
                flight_info: tripFlightInfo,
            },
            safeItems,
            tripDetail.day_notes,   // 🆕 每日注意事項
            tripDetail.day_costs,   // 🆕 每日預估花費
            tripDetail.day_checklists, // 🆕 2026 Checklist
            tripDetail.day_tickets,    // 🆕 2026 Tickets
            focusedDay               // 🆕 2026 Adaptive Focus
        )

        // 🔗 🆕 2026 Neural Connection: 注入天氣數據
        if (lean && tripLocation) {
            const today = new Date().toISOString().split('T')[0]
            const cached = weatherStore.getWeatherData(tripLocation.lat, tripLocation.lng, today)
            if (cached) {
                const isStale = Date.now() - cached.timestamp > 3 * 60 * 60 * 1000 // 3小時過期
                const avgTemp = cached.forecast.length > 0
                    ? Math.round(cached.forecast.reduce((a, b) => a + b.temp, 0) / cached.forecast.length)
                    : '--'

                lean.weather_context = zh
                    ? `[2026 Neural Weather]
- 當前位置: ${tripLocation.name}
- 預測均溫: ${avgTemp}°C
- 信心度: ${cached.confidenceScore ?? '--'}%
- WBGT 風險: ${(cached.confidenceScore ?? 100) < 50 ? '高 (預報不穩)' : '正常'}
${isStale ? '⚠️ 提醒：此數據已超過 3 小時，可能存在誤差。' : ''}`
                    : `[2026 Neural Weather]
- Location: ${tripLocation.name}
- Forecast Avg Temp: ${avgTemp}°C
- Confidence: ${cached.confidenceScore ?? '--'}%
- WBGT Risk: ${(cached.confidenceScore ?? 100) < 50 ? 'High (unstable forecast)' : 'Normal'}
${isStale ? '⚠️ Note: Data is over 3 hours old and may vary.' : ''}`
            }
        }

        if (lean) {
            debugLog("🧠 Neural Connection Active: Itinerary context generated", {
                title: lean.title,
                days: lean.total_days,
                focused: lean.focused_day,
                hasWeather: !!lean.weather_context
            })
        }

        return lean
    }, [activeTrip, tripDetail, tripLocation, weatherStore, focusedDay, zh])

    const [isOpen, setIsOpen] = useState(false)
    // 🆕 向後相容：將舊格式訊息遷移到新格式
    const hydrateMessage = (msg: Partial<Message> & { content?: string }): Message => ({
        role: msg.role || "model",
        displayContent: msg.displayContent || msg.content || "",
        rawParts: msg.rawParts || [{ text: msg.displayContent || msg.content || "" }],
        groundingSources: msg.groundingSources || msg.sources?.map(s => ({ title: s.title, uri: s.url })),
        modelUsed: msg.modelUsed,
        researchData: msg.researchData
    })

    const [messages, setMessages] = useState<Message[]>([
        hydrateMessage({
            role: "model",
            displayContent: "__GREETING__"
        })
    ])
    const [input, setInput] = useState("")
    const [isLoading, setIsLoading] = useState(false)
    // 🆕 即時聯網搜尋/閱讀狀態
    const [searchStatus, setSearchStatus] = useState<{
        phase: "thinking" | "searching"
        query?: string
        url?: string
    }>({ phase: "thinking" })
    const [selectedImage, setSelectedImage] = useState<string | null>(null)
    const [imagePreviewError, setImagePreviewError] = useState(false)
    const [isCompressingImage, setIsCompressingImage] = useState(false)
    const compressingImageRef = useRef(false)
    const imageUploadGenRef = useRef(0)
    const isDeepResearchRef = useRef(false)
    // 🆕 v3.5: 保存失敗的訊息用於重試
    const [lastFailedMessage, setLastFailedMessage] = useState<string | null>(null)
    // 🆕 v3.6: 記憶摘要永動機
    const [memorySummary, setMemorySummary] = useState<string | null>(null)
    const [isSummarizing, setIsSummarizing] = useState(false)
    const messagesEndRef = useRef<HTMLDivElement>(null)
    const textareaRef = useRef<HTMLTextAreaElement>(null)
    // 🆕 v5.3: 行動端 Auto-Dock 狀態 (地圖運鏡時自動下潛收合，避免遮擋主地圖)
    const [isDocked, setIsDocked] = useState(false)
    const [isComposerMenuOpen, setIsComposerMenuOpen] = useState(false)
    // 🆕 v3.5: AbortController for stopping generation
    const abortControllerRef = useRef<AbortController | null>(null)
    const activePollIntervalsRef = useRef<Set<ReturnType<typeof setInterval>>>(new Set())
    const activeResearchIdRef = useRef<string | null>(null)
    const isMountedRef = useRef(true)

    useEffect(() => {
        isDeepResearchRef.current = isDeepResearch
    }, [isDeepResearch])

    const clearAllPollIntervals = () => {
        activePollIntervalsRef.current.forEach((id) => clearInterval(id))
        activePollIntervalsRef.current.clear()
    }

    const cancelResearchBackend = useCallback((interactionId: string) => {
        if (!interactionId || interactionId.startsWith("stream_")) return
        try {
            const k = getSecureApiKey()
            if (!k) return
            void fetch(`${API_HOST}/api/agents/interactions/${interactionId}/cancel`, {
                method: "POST",
                headers: { "X-Gemini-API-Key": k }
            }).catch((e) => {
                console.error("Cancel failed:", e)
            })
        } catch (e) {
            console.error("Cancel failed:", e)
        }
    }, [])

    // 🛡️ Cleanup AbortController & polling intervals on unmount to prevent memory leaks
    useEffect(() => {
        isMountedRef.current = true
        const intervals = activePollIntervalsRef.current
        return () => {
            isMountedRef.current = false
            activeResearchIdRef.current = null
            abortControllerRef.current?.abort()
            intervals.forEach((id) => clearInterval(id))
            intervals.clear()
        }
    }, [])

    useEffect(() => {
        const handleMapFlyTo = () => {
            if (isOpen && typeof window !== "undefined" && window.innerWidth < 768) {
                setIsComposerMenuOpen(false)
                setIsDocked(true)
            }
        }
        window.addEventListener("tabidachi:map-flyto", handleMapFlyTo)
        return () => {
            window.removeEventListener("tabidachi:map-flyto", handleMapFlyTo)
        }
    }, [isOpen])

    // ----------------------------------------------------------------------
    // 🆕 修復：當使用者切換不同行程時，強制清除上一個行程的對話記憶與摘要
    // ----------------------------------------------------------------------
    const prevTripIdRef = useRef(activeTripId)

    useEffect(() => {
        if (activeTripId && prevTripIdRef.current !== activeTripId) {
            // 🚨 關鍵補全：切斷前一個行程還在生成的 AI 回應與背景輪詢
            imageUploadGenRef.current += 1
            compressingImageRef.current = false
            setIsCompressingImage(false)
            setIsComposerMenuOpen(false)
            const prevResearchId = activeResearchIdRef.current
            activeResearchIdRef.current = null
            abortControllerRef.current?.abort()
            abortControllerRef.current = null
            clearAllPollIntervals()
            if (prevResearchId) {
                cancelResearchBackend(prevResearchId)
            }
            setIsLoading(false)
            isDeepResearchRef.current = false
            setIsDeepResearch(false)
            setSelectedImage(null)
            setImagePreviewError(false)

            // 重置對話清單為初始的打招呼訊息
            setMessages([
                hydrateMessage({
                    role: "model",
                    displayContent: "__GREETING__"
                })
            ])

            // 清除長期的記憶摘要片段
            setMemorySummary(null)

            // 更新追蹤器
            prevTripIdRef.current = activeTripId

            // (選用) 切換時自動將可能開著的聊天氣泡關閉
            if (isOpen) {
                setIsOpen(false)
            }
        }
    }, [activeTripId, isOpen, cancelResearchBackend])

    // Draggable state & 2D Magnetic Snap
    const [position, setPosition] = useState<Position>({ x: 16, y: 100 })
    const [isDragging, setIsDragging] = useState(false)
    const [isIdle, setIsIdle] = useState(false)
    const dragRef = useRef<HTMLDivElement>(null)
    const dragOffset = useRef<Position>({ x: 0, y: 0 })
    const hasMovedRef = useRef(false)

    // 4 秒無操作自動半透明 (Idle Dimming)
    useEffect(() => {
        if (isOpen || isDragging) {
            setIsIdle(false)
            return
        }
        const timer = setTimeout(() => setIsIdle(true), 4000)
        return () => clearTimeout(timer)
    }, [isOpen, isDragging, position])

    // Load saved position + clamp to current viewport
    useEffect(() => {
        const saved = localStorage.getItem("chat_widget_position")
        if (saved) {
            try {
                const pos = JSON.parse(saved)
                // 🆕 Clamp to current viewport on load
                const buttonSize = 56
                const margin = 16
                const safeBottom = getSafeAreaBottom()
                const minY = 80 + safeBottom
                const maxY = window.innerHeight - buttonSize - margin
                pos.y = Math.max(minY, Math.min(pos.y, maxY))
                setPosition(pos)
            } catch { }
        }
    }, [])

    // 🆕 Re-clamp position on viewport resize / orientation change
    useEffect(() => {
        const reclamp = () => {
            setPosition(prev => {
                const buttonSize = 56
                const margin = 16
                const safeBottom = getSafeAreaBottom()
                const minY = 80 + safeBottom
                const maxY = window.innerHeight - buttonSize - margin
                const clampedY = Math.max(minY, Math.min(prev.y, maxY))
                const clampedX = Math.max(margin, Math.min(prev.x, window.innerWidth - buttonSize - margin))
                if (clampedY !== prev.y || clampedX !== prev.x) {
                    const newPos = { x: clampedX, y: clampedY }
                    localStorage.setItem("chat_widget_position", JSON.stringify(newPos))
                    return newPos
                }
                return prev
            })
        }

        window.addEventListener('resize', reclamp)
        window.addEventListener('orientationchange', reclamp)
        return () => {
            window.removeEventListener('resize', reclamp)
            window.removeEventListener('orientationchange', reclamp)
        }
    }, [])

    // Auto-scroll
    useEffect(() => {
        if (isOpen && !isDocked) {
            messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
        }
    }, [messages, isOpen, isDocked])

    // Handle drag start
    const handleDragStart = useCallback((clientX: number, clientY: number) => {
        if (!dragRef.current) return
        const rect = dragRef.current.getBoundingClientRect()
        dragOffset.current = {
            x: clientX - rect.left,
            y: clientY - rect.top
        }
        hasMovedRef.current = false
        setIsDragging(true)
    }, [])

    // Handle drag move - 2D AssistiveTouch free movement within safe margins
    const handleDragMove = useCallback((clientX: number, clientY: number) => {
        if (!isDragging) return

        hasMovedRef.current = true
        const buttonSize = 56
        const margin = 16
        const safeBottom = getSafeAreaBottom()
        const minY = 80 + safeBottom
        const maxY = window.innerHeight - buttonSize - margin

        // 2D 雙向自由位移計算
        const newX = window.innerWidth - clientX - (buttonSize - dragOffset.current.x)
        const clampedX = Math.max(margin, Math.min(newX, window.innerWidth - buttonSize - margin))
        const newY = window.innerHeight - clientY - (buttonSize - dragOffset.current.y)
        const clampedY = Math.max(minY, Math.min(newY, maxY))

        setPosition({ x: clampedX, y: clampedY })
    }, [isDragging])

    // Handle drag end - 2D 彈簧磁吸貼齊最近邊緣 (左右) + Haptic 反饋
    const handleDragEnd = useCallback(() => {
        if (isDragging) {
            setIsDragging(false)
            const buttonSize = 56
            // 判斷離左側還是右側邊界更近
            const snapToRight = position.x < (window.innerWidth - buttonSize) / 2
            const targetX = snapToRight ? 16 : window.innerWidth - buttonSize - 16
            const snappedPosition = { x: targetX, y: position.y }
            setPosition(snappedPosition)
            localStorage.setItem("chat_widget_position", JSON.stringify(snappedPosition))
            if (typeof navigator !== 'undefined' && navigator.vibrate) {
                navigator.vibrate(10)
            }
            setTimeout(() => {
                hasMovedRef.current = false
            }, 80)
        }
    }, [isDragging, position.x, position.y])

    // Mouse events
    const handleMouseDown = (e: React.MouseEvent) => {
        e.preventDefault()
        handleDragStart(e.clientX, e.clientY)
    }

    // Touch events
    const handleTouchStart = (e: React.TouchEvent) => {
        const touch = e.touches[0]
        if (touch) {
            handleDragStart(touch.clientX, touch.clientY)
        }
    }

    // Global event listeners
    useEffect(() => {
        const handleMouseMove = (e: MouseEvent) => handleDragMove(e.clientX, e.clientY)
        const handleTouchMove = (e: TouchEvent) => {
            if (e.touches.length > 0) {
                e.preventDefault() // Prevent page scroll during drag
                handleDragMove(e.touches[0].clientX, e.touches[0].clientY)
            }
        }
        const handleEnd = () => handleDragEnd()

        if (isDragging) {
            document.addEventListener("mousemove", handleMouseMove)
            document.addEventListener("mouseup", handleEnd)
            document.addEventListener("touchmove", handleTouchMove, { passive: false })
            document.addEventListener("touchend", handleEnd)
            // Prevent body scroll while dragging
            document.body.style.overflow = "hidden"
        }

        return () => {
            document.removeEventListener("mousemove", handleMouseMove)
            document.removeEventListener("mouseup", handleEnd)
            document.removeEventListener("touchmove", handleTouchMove)
            document.removeEventListener("touchend", handleEnd)
            // Restore body scroll
            document.body.style.overflow = ""
        }
    }, [isDragging, handleDragMove, handleDragEnd])

    const handleSendMessage = async () => {
        if ((!input.trim() && !selectedImage) || isLoading || compressingImageRef.current) return

        // Check for API key
        const apiKey = getSecureApiKey()
        if (!apiKey) {
            const errorMsg = t('ai_apikey_missing')
            setMessages(prev => [
                ...prev,
                hydrateMessage({ role: "user", displayContent: input }),
                hydrateMessage({ role: "model", displayContent: errorMsg })
            ])
            setInput("")
            return
        }

        const userMsg = input
        const currentImage = selectedImage

        imageUploadGenRef.current += 1
        setInput("")
        setSelectedImage(null)
        setImagePreviewError(false)
        if (textareaRef.current) {
            textareaRef.current.style.height = "auto"
        }

        // 🆕 建立使用者訊息 (新格式)
        const userMessage: Message = {
            role: "user",
            displayContent: userMsg + (currentImage ? t('ai_image_uploaded') : ""),
            rawParts: [{ text: userMsg }]
        }

        setMessages(prev => [...prev, userMessage])
        setIsLoading(true)

        // 🆕 v3.5: 建立 AbortController
        const currentController = new AbortController()
        abortControllerRef.current = currentController

        // 🆕 v3.6: 記憶摘要永動機
        const PREHEAT_THRESHOLD = 20  // 預熱觸發點
        const MAX_HISTORY = 25        // 最大歷史條數
        const KEEP_RECENT = 10        // 保留最近 N 條

        // 預熱觸發摘要（背景執行，不阻塞）
        if (messages.length >= PREHEAT_THRESHOLD && messages.length < MAX_HISTORY && !memorySummary && !isSummarizing) {
            setIsSummarizing(true)
            toast.info(t('ai_summarizing'), { duration: 2000 })

            const toSummarize = messages.slice(0, messages.length - KEEP_RECENT)
            const targetUserId = contextUserId || localStorage.getItem("user_uuid") || ""
            void (async () => {
                try {
                    let token = authSession.getCachedToken()
                    if (!token && typeof window !== "undefined") {
                        token = await authSession.ensureValidSession().catch(() => null)
                    }
                    const buildHeaders = (authToken: string | null): Record<string, string> => {
                        const h: Record<string, string> = {
                            "Content-Type": "application/json",
                            "X-Gemini-API-Key": apiKey,
                            "X-User-ID": targetUserId
                        }
                        if (authToken) {
                            h["Authorization"] = `Bearer ${authToken}`
                        }
                        return h
                    }
                    const payload = JSON.stringify({
                        history: toSummarize.map((m: Message) => ({
                            role: m.role,
                            displayContent: m.displayContent
                        })),
                        locale: lang
                    })
                    let res = await fetch(`${API_HOST}/api/chat/summarize`, {
                        method: "POST",
                        headers: buildHeaders(token),
                        body: payload
                    })
                    if (res.status === 401 && typeof window !== "undefined") {
                        let errDetail = ""
                        try {
                            const errJson = await res.clone().json()
                            errDetail = String(errJson?.detail || errJson?.message || "")
                        } catch {
                            errDetail = await res.clone().text().catch(() => "")
                        }
                        const isGeminiKeyAuthError = /gemini|api[_ ]?key|金鑰|個人檔案|profile|google ai studio|已失效|無效或已過期/i.test(errDetail)
                        const hasSessionToken = Boolean(token || localStorage.getItem("tabiji_session_token"))
                        if (!isGeminiKeyAuthError && hasSessionToken) {
                            const freshToken = await authSession.ensureValidSession(true).catch(() => null)
                            if (freshToken) {
                                res = await fetch(`${API_HOST}/api/chat/summarize`, {
                                    method: "POST",
                                    headers: buildHeaders(freshToken),
                                    body: payload
                                })
                            } else {
                                const isTransientFailure = typeof authSession.wasLastAuthExchangeTransientFailure === "function" && authSession.wasLastAuthExchangeTransientFailure()
                                if (!isTransientFailure) {
                                    localStorage.removeItem("tabiji_session_token")
                                }
                            }
                        }
                    }
                    if (!res.ok) throw new Error(`HTTP ${res.status}`)
                    const data = await res.json()
                    if (data.summary) {
                        setMemorySummary(data.summary)
                        toast.success(t('ai_summarized'))
                    }
                } catch (err) {
                    console.error(t('ai_summary_failed'), err)
                } finally {
                    setIsSummarizing(false)
                }
            })()
        }

        // 準備 history
        let historySource = messages
        if (messages.length > MAX_HISTORY) {
            if (memorySummary) {
                // 有摘要：注入摘要 + 最近 N 條
                toast.success(t('ai_using_memory'))
                const recentMessages = messages.slice(-KEEP_RECENT)
                const summaryPrefix = zh ? "[對話記憶摘要]" : "[Memory Summary]"
                const summaryMessage = {
                    role: "model" as const,
                    rawParts: [{ text: `${summaryPrefix} ${memorySummary}` }],
                    displayContent: `${summaryPrefix} ${memorySummary}`
                }
                historySource = [summaryMessage, ...recentMessages]
            } else {
                // 無摘要：Fallback 到簡單截斷
                toast.info(t('ai_history_limit'))
                historySource = messages.slice(-MAX_HISTORY)
            }
        }
        // 🛡️ 歷史衛生檢查：防止連續相同 role 導致 Gemini 400 錯誤
        const sanitizedSource: typeof historySource = []
        for (const m of historySource) {
            const prev = sanitizedSource[sanitizedSource.length - 1]
            if (prev && prev.role === m.role) {
                // 連續相同 role → 插入一個空的對方佔位訊息
                const placeholderRole = m.role === "user" ? "model" : "user"
                sanitizedSource.push(hydrateMessage({
                    role: placeholderRole as "user" | "model",
                    displayContent: placeholderRole === "model"
                        ? (zh ? "[AI 處理中]" : "[AI Processing]")
                        : (zh ? "[繼續]" : "[Continue]")
                }))
            }
            sanitizedSource.push(m)
        }
        const history = sanitizedSource.map(m => ({
            role: m.role,
            rawParts: m.rawParts,
            displayContent: m.displayContent
        }))

        // 🔬 Antigravity System 2: 深度研究模式分流 (附圖時強制走多模態 /api/chat，防止圖片被靜默丟棄)
        const isDeepIntent = !currentImage && (isDeepResearch || userMsg.startsWith("/research") || userMsg.includes("深度研究") || userMsg.includes("演算法精算"))
        if (isDeepIntent && apiKey) {
            setIsLoading(true)
            setSearchStatus({ phase: "thinking" })
            const cleanPrompt = userMsg.replace(/^\/research\s*/, "").trim()
            try {
                // 優先自 tripDetail.flight_info 提取合法 IATA，並計算真實 days[].activities 總數與精簡每日行程摘要
                const outboundLeg = Array.isArray(tripDetail?.flight_info?.outbound)
                    ? tripDetail.flight_info.outbound[0]
                    : undefined
                const iataOrigin = typeof outboundLeg?.dep_airport === "string" && /^[A-Za-z]{3}$/.test(outboundLeg.dep_airport.trim())
                    ? outboundLeg.dep_airport.trim().toUpperCase()
                    : undefined
                const iataDestination = typeof outboundLeg?.arr_airport === "string" && /^[A-Za-z]{3}$/.test(outboundLeg.arr_airport.trim())
                    ? outboundLeg.arr_airport.trim().toUpperCase()
                    : undefined

                let researchBookingContext: string | undefined
                if (tripDetail) {
                    const daysArr = Array.isArray(tripDetail.days)
                        ? (tripDetail.days as Array<{ day: number; activities?: Array<{ place?: string; place_name?: string; time?: string }> }>)
                        : []
                    const totalActivities = daysArr.length > 0
                        ? daysArr.reduce((acc, d) => acc + (Array.isArray(d.activities) ? d.activities.length : 0), 0)
                        : (Array.isArray(tripDetail.items) ? tripDetail.items.length : 0)
                    const daySummaries = daysArr
                        .filter((d) => Array.isArray(d.activities) && d.activities.length > 0)
                        .slice(0, 10)
                        .map((d) => {
                            const places = (d.activities || [])
                                .slice(0, 6)
                                .map((a) => a.place || a.place_name || "")
                                .filter(Boolean)
                                .join(" -> ")
                            return `Day ${d.day}: ${places}`
                        })
                    const parts = [
                        `Trip: ${tripDetail.title || activeTrip?.title || ""}`,
                        `Activities: ${totalActivities}`,
                    ]
                    if (tripDetail.start_date || tripDetail.end_date) {
                        parts.push(`Dates: ${tripDetail.start_date || "?"} ~ ${tripDetail.end_date || "?"}`)
                    }
                    if (iataOrigin && iataDestination) {
                        parts.push(`Flight: ${iataOrigin} -> ${iataDestination}`)
                    }
                    if (daySummaries.length > 0) {
                        parts.push(`Schedule: ${daySummaries.join(" | ").slice(0, 600)}`)
                    }
                    researchBookingContext = parts.join(", ")
                }

                // Opt-in Two-Phase SSE 深度研究（保持 HTTP 活躍避開 Cloud Run cpu-throttling 凍結；遇 404/非串流自動退回 JSON 輪詢）
                const streamId = `stream_${Date.now()}`
                let streamCardInserted = false
                const ensureStreamCard = (engineName = "gemini-flash-stream") => {
                    if (streamCardInserted || !isMountedRef.current || currentController.signal.aborted) return
                    streamCardInserted = true
                    activeResearchIdRef.current = streamId
                    setMessages(prev => [...prev, hydrateMessage({
                        role: "model",
                        displayContent: "",
                        researchData: {
                            id: streamId,
                            status: "running",
                            prompt: cleanPrompt,
                            engine: engineName,
                        }
                    })])
                }

                const streamRes = await streamDeepResearch({
                    apiUrl: API_HOST,
                    apiKey,
                    prompt: cleanPrompt,
                    origin: iataOrigin || undefined,
                    destination: iataDestination || activeTrip?.title || undefined,
                    booking_context: researchBookingContext,
                    locale: lang,
                    signal: currentController.signal,
                    onThinking: () => {
                        ensureStreamCard()
                    },
                    onText: (chunkText) => {
                        ensureStreamCard()
                        if (!isMountedRef.current || currentController.signal.aborted) return
                        setMessages(prev => prev.map(m =>
                            m.researchData?.id === streamId
                                ? {
                                    ...m,
                                    displayContent: (m.displayContent || "") + chunkText,
                                    researchData: {
                                        ...m.researchData,
                                        outputText: (m.researchData.outputText || "") + chunkText,
                                    }
                                }
                                : m
                        ))
                    },
                })

                if (streamRes.supported) {
                    if (activeResearchIdRef.current === streamId) {
                        activeResearchIdRef.current = null
                    }
                    if (!isMountedRef.current || currentController.signal.aborted) return
                    if (streamRes.error) {
                        if (streamCardInserted) {
                            setMessages(prev => prev.map(m =>
                                m.researchData?.id === streamId
                                    ? {
                                        ...m,
                                        researchData: {
                                            ...m.researchData,
                                            status: "failed",
                                            error: streamRes.error,
                                        }
                                    }
                                    : m
                            ))
                        }
                        toast.error(streamRes.error)
                    } else {
                        const finalOutput = streamRes.text || ""
                        const finalEngine = streamRes.engine || "gemini-flash-stream"
                        const finalSources = streamRes.sources && streamRes.sources.length > 0 ? streamRes.sources : undefined
                        if (streamCardInserted) {
                            setMessages(prev => prev.map(m =>
                                m.researchData?.id === streamId
                                    ? {
                                        ...m,
                                        displayContent: finalOutput,
                                        researchData: {
                                            ...m.researchData,
                                            status: "completed",
                                            outputText: finalOutput,
                                            engine: finalEngine,
                                            ...(finalSources ? { sources: finalSources } : {}),
                                        }
                                    }
                                    : m
                            ))
                        } else {
                            setMessages(prev => [...prev, hydrateMessage({
                                role: "model",
                                displayContent: finalOutput,
                                researchData: {
                                    id: streamId,
                                    status: "completed",
                                    prompt: cleanPrompt,
                                    outputText: finalOutput,
                                    engine: finalEngine,
                                    ...(finalSources ? { sources: finalSources } : {}),
                                }
                            })])
                        }
                    }
                    if (abortControllerRef.current === currentController) {
                        setIsLoading(false)
                    }
                    isDeepResearchRef.current = false
                    setIsDeepResearch(false)
                    return
                }

                const res = await fetch(`${API_HOST}/api/agents/research`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-Gemini-API-Key": apiKey
                    },
                    signal: currentController.signal,
                    body: JSON.stringify({
                        prompt: cleanPrompt,
                        origin: iataOrigin || undefined,
                        destination: iataDestination || activeTrip?.title || undefined,
                        booking_context: researchBookingContext,
                        locale: lang
                    })
                })
                if (!res.ok) {
                    let startDetail = ""
                    try {
                        const errJson = await res.clone().json()
                        startDetail = String(errJson?.detail || errJson?.message || "")
                    } catch {
                        startDetail = ""
                    }
                    throw new Error(startDetail || `HTTP ${res.status}`)
                }
                const data = await res.json()
                if (!isMountedRef.current || currentController.signal.aborted) return
                const interactionId = data.interaction_id
                activeResearchIdRef.current = interactionId

                // 插入初始卡片狀態
                const initialResearchData: DeepResearchData = {
                    id: interactionId,
                    status: "running",
                    prompt: cleanPrompt,
                    engine: data.engine
                }
                setMessages(prev => [...prev, hydrateMessage({
                    role: "model",
                    displayContent: "",
                    researchData: initialResearchData
                })])

                // 背景輪詢狀態 (含 404/401/連續錯誤熔斷防禦、AbortSignal 中止與 Unmount 清理)
                let consecutivePollErrors = 0
                const pollInterval = setInterval(async () => {
                    if (!isMountedRef.current || currentController.signal.aborted) {
                        clearInterval(pollInterval)
                        activePollIntervalsRef.current.delete(pollInterval)
                        return
                    }
                    const failResearchCard = (errMsg: string) => {
                        clearInterval(pollInterval)
                        activePollIntervalsRef.current.delete(pollInterval)
                        if (activeResearchIdRef.current === interactionId) {
                            activeResearchIdRef.current = null
                        }
                        if (!isMountedRef.current || currentController.signal.aborted) return
                        setMessages(prev => {
                            const updated = [...prev]
                            const targetIdx = updated.findIndex(m => m.researchData?.id === interactionId)
                            if (targetIdx === -1) return prev
                            updated[targetIdx] = {
                                ...updated[targetIdx],
                                displayContent: updated[targetIdx].displayContent || "",
                                researchData: {
                                    id: interactionId,
                                    status: "failed",
                                    prompt: cleanPrompt,
                                    engine: data.engine,
                                    error: errMsg
                                }
                            }
                            return updated
                        })
                        toast.error(errMsg)
                        if (abortControllerRef.current === currentController) {
                            setIsLoading(false)
                        }
                    }

                    try {
                        const pollRes = await fetch(`${API_HOST}/api/agents/interactions/${interactionId}`, {
                            headers: { "X-Gemini-API-Key": apiKey },
                            signal: currentController.signal
                        })
                        if (!isMountedRef.current || currentController.signal.aborted) {
                            clearInterval(pollInterval)
                            activePollIntervalsRef.current.delete(pollInterval)
                            return
                        }
                        if (!pollRes.ok) {
                            consecutivePollErrors += 1
                            if (pollRes.status === 404 || pollRes.status === 401 || pollRes.status === 403 || consecutivePollErrors >= 3) {
                                let detail = `HTTP ${pollRes.status}`
                                try {
                                    const errBody = await pollRes.json()
                                    if (errBody?.detail) detail = errBody.detail
                                } catch { /* keep HTTP code */ }
                                failResearchCard(detail)
                            }
                            return
                        }
                        consecutivePollErrors = 0
                        const pollData = await pollRes.json()
                        if (!isMountedRef.current || currentController.signal.aborted) {
                            clearInterval(pollInterval)
                            activePollIntervalsRef.current.delete(pollInterval)
                            return
                        }
                        if (pollData.status === "completed" || pollData.status === "failed" || pollData.status === "cancelled") {
                            clearInterval(pollInterval)
                            activePollIntervalsRef.current.delete(pollInterval)
                            if (activeResearchIdRef.current === interactionId) {
                                activeResearchIdRef.current = null
                            }
                            const pollSources = Array.isArray(pollData.sources)
                                ? sanitizeGroundingSources(pollData.sources)
                                : []
                            setMessages(prev => {
                                const updated = [...prev]
                                const targetIdx = updated.findIndex(m => m.researchData?.id === interactionId)
                                if (targetIdx === -1) return prev
                                updated[targetIdx] = {
                                    ...updated[targetIdx],
                                    displayContent: pollData.output_text || "",
                                    researchData: {
                                        id: interactionId,
                                        status: pollData.status,
                                        prompt: cleanPrompt,
                                        outputText: pollData.output_text,
                                        engine: pollData.engine,
                                        ...(pollSources.length > 0 ? { sources: pollSources } : {}),
                                        error: pollData.error
                                    }
                                }
                                return updated
                            })
                            if (pollData.status === "failed" && pollData.error) {
                                toast.error(pollData.error)
                            }
                            if (abortControllerRef.current === currentController) {
                                setIsLoading(false)
                            }
                        }
                    } catch (err) {
                        if (!isMountedRef.current || currentController.signal.aborted || (err instanceof Error && err.name === "AbortError")) {
                            clearInterval(pollInterval)
                            activePollIntervalsRef.current.delete(pollInterval)
                            return
                        }
                        console.error("Polling interaction failed:", err)
                        consecutivePollErrors += 1
                        if (consecutivePollErrors >= 3) {
                            failResearchCard(zh ? "深度研究狀態輪詢失敗，請稍後重試" : "Failed to poll research task status")
                        }
                    }
                }, 2000)
                activePollIntervalsRef.current.add(pollInterval)

                isDeepResearchRef.current = false
                setIsDeepResearch(false)
                return
            } catch (err) {
                if (currentController.signal.aborted || !isMountedRef.current) {
                    return
                }
                console.error("Failed to start deep research:", err)
                const errMessage = err instanceof Error ? err.message : ""
                toast.error(errMessage || (zh ? "啟動深度研究失敗" : "Failed to start research"))
                if (abortControllerRef.current === currentController) {
                    setIsLoading(false)
                }
                isDeepResearchRef.current = false
                setIsDeepResearch(false)
                return
            }
        }

        // 🆕 嘗試使用 Streaming API
        let streamingText = ""
        let streamingRawParts: Part[] = []
        let streamingSuccess = false
        let streamErroredWithPartial = false
        let streamEmptyError = false
        let streamingFatalAuthError: string | null = null

        // 如果有圖片，跳過 streaming (目前不支援)
        if (!currentImage && apiKey) {
            setSearchStatus({ phase: "thinking" })
            try {
                await streamChat(
                    API_HOST,
                    userMsg,
                    history,
                    apiKey,
                    {
                        onStart: () => {
                            debugLog("🟢 SSE 連線建立")
                        },
                        onThinking: (status, meta) => {
                            if (currentController.signal.aborted || !isMountedRef.current) return
                            debugLog("🧠 AI 思考中:", status, meta)
                            if (status === "searching" || status === "reading") {
                                setSearchStatus({
                                    phase: "searching",
                                    query: meta?.query,
                                    url: meta?.url
                                })
                            } else {
                                setSearchStatus({ phase: "thinking" })
                            }
                        },
                        onTool: (toolCall) => {
                            if (currentController.signal.aborted || !isMountedRef.current) return
                            debugLog("🛠️ SSE 收到 Tool Call:", toolCall)
                            setSearchStatus({ phase: "thinking" })
                            const part: Part = {
                                function_call: toolCall,
                                functionCall: toolCall,
                                _raw: JSON.stringify(toolCall)
                            }
                            streamingRawParts.push(part)
                            setMessages(prev => {
                                const updated = [...prev]
                                const lastMsg = updated[updated.length - 1]
                                if (lastMsg?.role === "model" && lastMsg.modelUsed === "__streaming__") {
                                    const parts = lastMsg.rawParts ? [...lastMsg.rawParts] : []
                                    const isDup = parts.some(p => {
                                        const existing = p.function_call || p.functionCall
                                        return existing?.name === toolCall.name &&
                                            JSON.stringify(existing?.args) === JSON.stringify(toolCall.args)
                                    })
                                    if (!isDup) {
                                        parts.push(part)
                                    }
                                    updated[updated.length - 1] = {
                                        ...lastMsg,
                                        rawParts: parts
                                    }
                                } else {
                                    updated.push(hydrateMessage({
                                        role: "model",
                                        displayContent: streamingText,
                                        rawParts: [part],
                                        modelUsed: "__streaming__"
                                    }))
                                }
                                return updated
                            })
                        },
                        onText: (text) => {
                            if (currentController.signal.aborted || !isMountedRef.current) return
                            setSearchStatus({ phase: "thinking" })
                            streamingText += text
                            // 🆕 即時更新 UI (打字機效果)
                            setMessages(prev => {
                                const updated = [...prev]
                                const lastMsg = updated[updated.length - 1]
                                if (lastMsg?.role === "model" && lastMsg.modelUsed === "__streaming__") {
                                    // 🟢 修復 React State Mutation 導致的重複渲染/錯誤
                                    updated[updated.length - 1] = {
                                        ...lastMsg,
                                        displayContent: streamingText
                                    }
                                } else {
                                    updated.push(hydrateMessage({
                                        role: "model",
                                        displayContent: streamingText,
                                        modelUsed: "__streaming__"
                                    }))
                                }
                                return updated
                            })
                        },
                        onDone: (data) => {
                            if (currentController.signal.aborted || !isMountedRef.current) return
                            debugLog("✅ SSE 完成:", data.model_used, "來源數:", data.sources?.length ?? 0)
                            setSearchStatus({ phase: "thinking" })
                            streamingRawParts = (data.raw_parts && data.raw_parts.length > 0) ? (data.raw_parts as Part[]) : streamingRawParts
                            streamingSuccess = true

                            // 更新最終訊息 (🆕 v5.3: 修復純 Tool Call 回應時佔位訊息缺失)
                            const groundingSources = data.sources?.map(s => ({
                                title: s.title,
                                uri: s.uri || s.url || "",
                                citation_index: s.citation_index,
                                category: s.category,
                                badge: s.badge,
                                snippet: s.snippet
                            }))

                            // 🆕 儲存至本機裝置搜尋快取 (IndexedDB / RAM)
                            const cleanText = streamingText.replace(/[\u200B-\u200D\uFEFF]/g, "").trim()
                            const hasCards = Boolean(
                                extractRemoveFunctionCall(streamingRawParts) ||
                                extractItineraryFunctionCalls(streamingRawParts).length > 0 ||
                                extractExpenseFunctionCall(streamingRawParts)
                            )
                            if (!cleanText && !hasCards) {
                                // 🛡️ 嚴禁以假問候語掩飾 AI 空回應，明確呈現錯誤並保留重試狀態
                                streamingSuccess = false
                                streamEmptyError = true
                                setLastFailedMessage(userMsg)
                                const emptyErrMsg = zh ? "⚠️ AI 回應為空，請重試。" : "⚠️ AI returned an empty response. Please try again."
                                toast.error(emptyErrMsg)
                                setMessages(prev => {
                                    const updated = [...prev]
                                    const lastMsg = updated[updated.length - 1]
                                    if (lastMsg?.role === "model" && lastMsg.modelUsed === "__streaming__") {
                                        updated[updated.length - 1] = {
                                            ...lastMsg,
                                            displayContent: emptyErrMsg,
                                            rawParts: [{ text: emptyErrMsg }],
                                            modelUsed: data.model_used || "empty_error"
                                        }
                                    } else {
                                        updated.push(hydrateMessage({
                                            role: "model",
                                            displayContent: emptyErrMsg,
                                            rawParts: [{ text: emptyErrMsg }],
                                            modelUsed: data.model_used || "empty_error"
                                        }))
                                    }
                                    return updated
                                })
                                return
                            }
                            if (groundingSources && groundingSources.length > 0 && cleanText) {
                                setSearchCache(userMsg, groundingSources, cleanText).catch(() => {})
                            }
                            setMessages(prev => {
                                const updated = [...prev]
                                const lastMsg = updated[updated.length - 1]
                                const effectiveText = cleanText
                                if (lastMsg?.role === "model" && lastMsg.modelUsed === "__streaming__") {
                                    // 已有串流佔位訊息 → 🟢 取代整個 Object 防止 Mutation 錯誤
                                    updated[updated.length - 1] = {
                                        ...lastMsg,
                                        displayContent: effectiveText,
                                        rawParts: streamingRawParts,
                                        modelUsed: data.model_used,
                                        groundingSources
                                    }
                                } else {
                                    // 🟢 純 Tool Call 回應或保底回應 → 新增 model 訊息
                                    updated.push(hydrateMessage({
                                        role: "model",
                                        displayContent: effectiveText,
                                        rawParts: streamingRawParts,
                                        modelUsed: data.model_used,
                                        groundingSources
                                    }))
                                }
                                return updated
                            })
                        },
                        onReset: () => {
                            if (currentController.signal.aborted || !isMountedRef.current) return
                            streamingText = ""
                            streamingRawParts = []
                            setSearchStatus({ phase: "thinking" })
                            setMessages(prev => {
                                const updated = [...prev]
                                const lastMsg = updated[updated.length - 1]
                                if (lastMsg?.role === "model" && lastMsg.modelUsed === "__streaming__") {
                                    updated[updated.length - 1] = {
                                        ...lastMsg,
                                        displayContent: "",
                                        rawParts: []
                                    }
                                }
                                return updated
                            })
                        },
                        onError: (error) => {
                            if (currentController.signal.aborted || !isMountedRef.current) return
                            setSearchStatus({ phase: "thinking" })
                            // 🛡️ 如果 onDone 已經成功處理，忽略後續 error 事件
                            if (streamingSuccess) return
                            
                            console.error("🔴 SSE 錯誤:", JSON.stringify(error, null, 2))
                            const errDetail = (error as { detail?: string; message?: string })?.detail || error?.message

                            if (error?.code === 401 || error?.message === "API_KEY_INVALID") {
                                streamingFatalAuthError = errDetail || (zh ? "Gemini API Key 無效或已過期，請檢查設定" : "Invalid or expired Gemini API Key")
                                toast.error(streamingFatalAuthError)
                                setMessages(prev => [...prev, hydrateMessage({
                                    role: "model",
                                    displayContent: `⚠️ ${streamingFatalAuthError}`
                                })])
                                return
                            }

                            // 若已經接收到文字，明確標示錯誤中斷但不偽裝為成功，也不重複觸發 fallback 覆蓋部分回覆
                            if (streamingText.trim().length > 0) {
                                streamErroredWithPartial = true
                                const interruptedNotice = zh ? "\n\n[⚠️ 系統提示：連線異常，訊息中斷]" : "\n\n[⚠️ System notice: Connection lost, response interrupted]"
                                const finalPartialText = streamingText + interruptedNotice
                                streamingText = finalPartialText
                                toast.error(errDetail || (zh ? "AI 回應中斷，請稍後重試" : "AI stream interrupted, please retry"))
                                setMessages(prev => {
                                    const updated = [...prev]
                                    const lastMsg = updated[updated.length - 1]
                                    if (lastMsg?.role === "model") {
                                        updated[updated.length - 1] = {
                                            ...lastMsg,
                                            displayContent: finalPartialText,
                                            rawParts: [{ text: finalPartialText }],
                                            modelUsed: "error_recovered"
                                        }
                                    }
                                    return updated
                                })
                            }
                        }
                    },
                    currentController.signal,  // 🆕 傳入 AbortSignal
                    leanItinerary,  // 🆕 行程上下文
                    focusedDay,   // 🆕 v3.8: 傳入當前焦點天數
                    contextUserId || localStorage.getItem("user_uuid") || "",
                    undefined,
                    undefined,
                    lang  // 🌐 雙語語系管線傳遞
                )
            } catch (streamError) {
                console.error("⚠️ Streaming 失敗，使用 fallback:", streamError)
            }
        }

        // 🔄 Fallback: 如果 streaming 失敗或有圖片，使用原有 API (401 金鑰無效或已渲染錯誤中斷部分結果時不重複發請求)
        if (!streamingSuccess && !streamErroredWithPartial && !streamEmptyError && !streamingFatalAuthError && !currentController.signal.aborted) {
            try {
                let token = authSession.getCachedToken()
                if (!token && typeof window !== "undefined") {
                    token = await authSession.ensureValidSession().catch(() => null)
                }
                const headers: Record<string, string> = {
                    "Content-Type": "application/json",
                    "X-Gemini-API-Key": apiKey,
                    "X-User-ID": contextUserId || localStorage.getItem("user_uuid") || ""
                }
                if (token) {
                    headers["Authorization"] = `Bearer ${token}`
                }
                const chatPayload = JSON.stringify({
                    message: userMsg,
                    history: history,
                    image: currentImage,
                    location: tripLocation,
                    // 🆕 注入精簡版行程上下文與即時時間
                    current_itinerary: leanItinerary,
                    focused_day: focusedDay,
                    client_time: new Date().toISOString(),
                    client_timezone: typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().timeZone : "Asia/Taipei",
                    locale: lang
                })

                let res = await fetch(`${API_HOST}/api/chat`, {
                    method: "POST",
                    headers,
                    body: chatPayload,
                    signal: currentController.signal
                })

                // 🛡️ 401 自癒重試防禦：僅針對後端 Session Token 失效刷新，切勿因 Gemini API Key 401 誤刪用戶 Session
                if (res.status === 401 && typeof window !== "undefined") {
                    const errText = await res.clone().text().catch(() => "")
                    const isGeminiKeyAuthError = /gemini|api[_ ]?key|金鑰|個人檔案|profile|google ai studio|已失效|無效或已過期/i.test(errText)
                    if (!isGeminiKeyAuthError && (token || localStorage.getItem("tabiji_session_token"))) {
                        console.warn("⚠️ [Chat] Received 401 Unauthorized in fallback chat, refreshing session token...")
                        const freshToken = await authSession.ensureValidSession(true).catch(() => null)
                        if (!freshToken) {
                            const isTransientFailure = typeof authSession.wasLastAuthExchangeTransientFailure === "function" && authSession.wasLastAuthExchangeTransientFailure()
                            if (!isTransientFailure) {
                                localStorage.removeItem("tabiji_session_token")
                            }
                        }
                        if (freshToken) {
                            headers["Authorization"] = `Bearer ${freshToken}`
                            res = await fetch(`${API_HOST}/api/chat`, {
                                method: "POST",
                                headers,
                                body: chatPayload,
                                signal: currentController.signal
                            })
                        }
                    }
                }

                if (currentController.signal.aborted || !isMountedRef.current) return

                const data = await res.json()

                if (!res.ok) throw new Error(data.detail || "Failed to send message")
                const hasFallbackCards = Boolean(
                    data.raw_parts?.some((p: Part) => p.function_call || p.functionCall)
                )
                if (!String(data.response || "").trim() && !hasFallbackCards) {
                    throw new Error(zh ? "AI 回應為空，請重試。" : "AI returned an empty response. Please try again.")
                }

                const aiMessage: Message = {
                    role: "model",
                    displayContent: data.response,
                    rawParts: data.raw_parts || [{ text: data.response }],
                    groundingSources: data.grounding_metadata?.sources,
                    modelUsed: data.model_used
                }

                setMessages(prev => [...prev, aiMessage])
            } catch (error) {
                if (currentController.signal.aborted || (error instanceof Error && error.name === "AbortError") || !isMountedRef.current) {
                    return
                }
                console.error(error)
                // 🆕 v3.5: 保存失敗訊息供重試
                setLastFailedMessage(userMsg)
                setMessages(prev => [
                    ...prev,
                    hydrateMessage({ role: "model", displayContent: t('ai_connection_error') })
                ])
            }
        }

        // 🆕 清除失敗狀態（如果成功）
        if (streamingSuccess) {
            setLastFailedMessage(null)
        }

        if (isMountedRef.current && abortControllerRef.current === currentController) {
            setSearchStatus({ phase: "thinking" })
            setIsLoading(false)
        }
    }

    const handleStopGeneration = useCallback(() => {
        const researchIdToCancel = activeResearchIdRef.current
        activeResearchIdRef.current = null
        abortControllerRef.current?.abort()
        abortControllerRef.current = null
        if (activePollIntervalsRef.current.size > 0 || researchIdToCancel) {
            clearAllPollIntervals()
            setMessages(prev => prev.map(m =>
                m.researchData?.status === "running"
                    ? { ...m, researchData: { ...m.researchData, status: "cancelled" } }
                    : m
            ))
            if (researchIdToCancel) {
                cancelResearchBackend(researchIdToCancel)
            }
        }
        setSearchStatus({ phase: "thinking" })
        setIsLoading(false)
    }, [cancelResearchBackend])

    const handleToggleDeepResearch = useCallback((next: boolean) => {
        if (next && (selectedImage || compressingImageRef.current)) {
            return
        }
        if (next === isDeepResearchRef.current) {
            return
        }
        isDeepResearchRef.current = next
        setIsDeepResearch(next)
        toast.info(
            next ? t('ai_composer_deep_research_on') : t('ai_composer_deep_research_off'),
            { position: "top-center", duration: 2200 }
        )
    }, [selectedImage, t])

    const handleRemoveImage = useCallback(() => {
        imageUploadGenRef.current += 1
        compressingImageRef.current = false
        setIsCompressingImage(false)
        setSelectedImage(null)
        setImagePreviewError(false)
    }, [])

    const handleImageFile = useCallback(async (file: File) => {
        if (!file || compressingImageRef.current) return

        if (!isImageFile(file) || (file.type || "").trim().toLowerCase().startsWith("image/svg")) {
            toast.error(zh ? "請選擇圖片檔案 (JPG, PNG, WEBP, HEIC)" : "Please select an image file (JPG, PNG, WEBP, HEIC)")
            return
        }
        if (file.size > 25 * 1024 * 1024) {
            toast.error(zh ? "原始圖片請小於 25MB" : "Raw image must be under 25MB")
            return
        }

        const currentGen = ++imageUploadGenRef.current
        compressingImageRef.current = true
        setIsCompressingImage(true)
        try {
            const compressed = await compressImage(file, "ai_input")
            if (!isMountedRef.current || imageUploadGenRef.current !== currentGen) return
            if (compressed.size > 10 * 1024 * 1024) {
                toast.error(zh ? "壓縮後圖片仍超過 10MB，請選擇較小圖片" : "Compressed image still exceeds 10MB")
                return
            }

            const dataUrl = await readImageFileAsDataUrl(compressed)
            if (!isMountedRef.current || imageUploadGenRef.current !== currentGen) return
            setImagePreviewError(false)
            setSelectedImage(dataUrl)
            if (isDeepResearchRef.current) {
                isDeepResearchRef.current = false
                setIsDeepResearch(false)
                toast.info(t('ai_composer_deep_research_auto_off'), { position: "top-center", duration: 2400 })
            }
        } catch (err) {
            if (!isMountedRef.current || imageUploadGenRef.current !== currentGen) return
            console.error("[ChatWidget] Image compression error:", err)
            toast.error(zh ? "圖片處理失敗，請重試" : "Failed to process image")
        } finally {
            if (imageUploadGenRef.current === currentGen) {
                compressingImageRef.current = false
                if (isMountedRef.current) {
                    setIsCompressingImage(false)
                }
            }
        }
    }, [zh, t])

    // 🔒 未登錄時不渲染任何內容
    if (!isLoggedIn) return null

    return (
        <>
            {/* Chat Window - Fullscreen Immersive with Desktop Centering & Dark Mode */}
            {isOpen && (
                <>
                {isDocked && (
                    <div
                        onClick={() => setIsDocked(false)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => { if (e.key === 'Enter') setIsDocked(false) }}
                        className="fixed bottom-4 left-4 right-4 z-110 h-14 bg-tabiji-forest/95 dark:bg-[#182320]/95 backdrop-blur-md text-tabiji-paper rounded-2xl shadow-2xl flex items-center justify-between px-4 cursor-pointer animate-in slide-in-from-bottom duration-200 border border-white/20 active:scale-[0.98] select-none"
                    >
                        <div className="flex items-center gap-2.5 text-sm font-medium">
                            <span className="relative flex h-3 w-3 shrink-0">
                                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                                <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500" />
                            </span>
                            <span className="truncate">{zh ? "📍 正在地圖預覽地點... 點擊返回對話" : "📍 Previewing on map... Tap to resume"}</span>
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0 text-xs bg-white/20 hover:bg-white/30 text-white font-medium px-3 py-1.5 rounded-xl transition-all">
                            <span>{zh ? "展開對話" : "Open"}</span>
                        </div>
                    </div>
                )}
                    <div className={cn("fixed inset-0 z-110 flex flex-col bg-black/35 backdrop-blur-xs animate-in fade-in duration-200", isDocked && "hidden pointer-events-none")}>
                    <div className="w-full max-w-3xl mx-auto h-full flex flex-col bg-tabiji-paper dark:bg-tabiji-dark shadow-2xl md:border-x md:border-tabiji-forest/10 dark:md:border-white/10 overflow-hidden">
                        {/* Header - 和紙透光微毛玻璃手帳風 */}
                        <div className="bg-tabiji-paper/85 dark:bg-tabiji-dark/85 backdrop-blur-md p-4 flex justify-between items-center shrink-0 border-b border-tabiji-forest/10 dark:border-white/10">
                            <div className="flex items-center gap-2.5">
                                <div className="relative w-9 h-9 rounded-full overflow-hidden bg-white/80 dark:bg-tabiji-charcoal/80 flex items-center justify-center shrink-0 border border-tabiji-forest/15 dark:border-white/20 shadow-xs">
                                    {/* eslint-disable-next-line @next/next/no-img-element */}
                                    <img src="/images/ryan-bot-avatar.webp" alt="Ryan AI" className="w-8 h-8 object-contain" />
                                </div>
                                <div>
                                    <h3 className="font-bold text-sm text-tabiji-charcoal dark:text-tabiji-paper flex items-center gap-1.5">
                                        Ryan AI Assistant
                                        <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse inline-block" />
                                    </h3>
                                    <p className="text-[10px] text-tabiji-slate opacity-90">{t('ai_subtitle')}</p>
                                </div>
                            </div>
                            <button onClick={() => { setIsComposerMenuOpen(false); setIsOpen(false); setIsDocked(false) }} className="hover:bg-tabiji-forest/5 dark:hover:bg-white/10 p-1.5 rounded-full text-tabiji-slate hover:text-tabiji-charcoal dark:hover:text-tabiji-paper transition-colors cursor-pointer">
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        {/* Messages Area */}
                        <div className="flex-1 overflow-y-auto overflow-x-hidden p-4 md:p-6 space-y-4 bg-tabiji-paper dark:bg-tabiji-dark scroll-smooth">
                            {messages.map((msg, idx) => {
                                // 🛡️ Zero Empty Bubble Shield: 物理隱藏無文字且無任何卡片的幽靈空白訊息
                                const cleanContent = msg.displayContent?.replace(/[\u200B-\u200D\uFEFF]/g, "").trim() || ""
                                const hasCards = Boolean(
                                    extractRemoveFunctionCall(msg.rawParts) ||
                                    extractItineraryFunctionCalls(msg.rawParts).length > 0 ||
                                    extractExpenseFunctionCall(msg.rawParts) ||
                                    msg.researchData
                                )
                                if (msg.role === "model" && !cleanContent && !hasCards) {
                                    return null
                                }
                                return (
                                <div key={idx} className={cn("flex gap-3 min-w-0", msg.role === "user" ? "max-w-[85%] ml-auto flex-row-reverse" : "max-w-[95%]")}>
                                    <div className={cn(
                                        "w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-1 overflow-hidden",
                                        msg.role === "model" ? "bg-white/90 dark:bg-[#182320] border border-tabiji-forest/15 dark:border-white/15 shadow-xs" : "bg-tabiji-forest/10 dark:bg-tabiji-charcoal text-tabiji-forest dark:text-tabiji-paper"
                                    )}>
                                        {msg.role === "model" ? (
                                            /* eslint-disable-next-line @next/next/no-img-element */
                                            <img src="/images/ryan-bot-avatar.webp" alt="Ryan AI" className="w-6 h-6 object-contain" />
                                        ) : (
                                            <User className="w-5 h-5" />
                                        )}
                                    </div>
                                    <div className={cn(
                                        "p-3.5 md:p-4 rounded-2xl text-sm shadow-xs min-w-0 wrap-anywhere",
                                        msg.role === "model" ? "bg-white dark:bg-[#182320] text-tabiji-charcoal dark:text-tabiji-paper rounded-tl-none border border-tabiji-forest/8 dark:border-white/8 shadow-xs" : "bg-tabiji-forest text-tabiji-paper dark:bg-tabiji-forest dark:text-tabiji-paper rounded-tr-none shadow-xs"
                                    )}>
                                        {msg.role === "model" ? (
                                            <>
                                                {/* 🆕 移除行程預覽卡片 (如果有 remove_itinerary_item function_call) */}
                                                {(() => {
                                                    const removeData = extractRemoveFunctionCall(msg.rawParts)
                                                    if (removeData) {
                                                        return <RemoveItemPreviewCard removeData={removeData} currentTrip={tripDetail} />
                                                    }
                                                    return null
                                                })()}
                                                {/* 🆕 POI 預覽卡片 (支援單筆或多筆批次) */}
                                                {(() => {
                                                    const poiItems = extractItineraryFunctionCalls(msg.rawParts)
                                                    if (poiItems.length === 1) {
                                                        return <POIPreviewCard poiData={poiItems[0]} />
                                                    } else if (poiItems.length > 1) {
                                                        return <BatchPOIPreviewCard items={poiItems} />
                                                    }
                                                    return null
                                                })()}
                                                {/* 🆕 記帳預覽卡片 (如果有 function_call) */}
                                                {(() => {
                                                    const expenseData = extractExpenseFunctionCall(msg.rawParts)
                                                    if (expenseData) {
                                                        return <ExpensePreviewCard expenseData={expenseData} />
                                                    }
                                                    return null
                                                })()}
                                                {/* 🔬 Antigravity 深度研究任務卡片 */}
                                                {msg.researchData && (
                                                    <DeepResearchCard
                                                        data={msg.researchData}
                                                        onCancel={async (id) => {
                                                            if (activeResearchIdRef.current === id) {
                                                                activeResearchIdRef.current = null
                                                                abortControllerRef.current?.abort()
                                                                abortControllerRef.current = null
                                                                clearAllPollIntervals()
                                                                setSearchStatus({ phase: "thinking" })
                                                                setIsLoading(false)
                                                            }
                                                            setMessages(prev => prev.map(m =>
                                                                m.researchData?.id === id && m.researchData.status === "running"
                                                                    ? { ...m, researchData: { ...m.researchData, status: "cancelled" } }
                                                                    : m
                                                            ))
                                                            try {
                                                                if (id.startsWith("stream_")) {
                                                                    toast.info(zh ? "已取消深度研究任務" : "Research cancelled", { position: "top-center", duration: 2200 })
                                                                } else {
                                                                    const k = getSecureApiKey()
                                                                    if (k) {
                                                                        await fetch(`${API_HOST}/api/agents/interactions/${id}/cancel`, {
                                                                            method: "POST",
                                                                            headers: { "X-Gemini-API-Key": k }
                                                                        })
                                                                        toast.info(zh ? "已取消深度研究任務" : "Research cancelled", { position: "top-center", duration: 2200 })
                                                                    }
                                                                }
                                                            } catch (e) {
                                                                console.error("Cancel failed:", e)
                                                            }
                                                        }}
                                                        onAddToItinerary={(content) => {
                                                            const event = new CustomEvent("ai-import-itinerary", { detail: { content } })
                                                            window.dispatchEvent(event)
                                                            toast.success(zh ? "已將研究成果傳送至行程匯入器" : "Sent to itinerary importer")
                                                            const navEvent = new CustomEvent("navigate-to-trips")
                                                            window.dispatchEvent(navEvent)
                                                            setIsComposerMenuOpen(false)
                                                            setIsOpen(false)
                                                        }}
                                                    />
                                                )}
                                                {cleanContent ? (
                                                    <div className="markdown-body prose prose-sm max-w-none prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-a:text-tabiji-forest dark:prose-a:text-emerald-400 prose-a:font-semibold hover:prose-a:underline wrap-anywhere">
                                                        {(() => {
                                                            const itinerary = tryParseItinerary(cleanContent)
                                                        if (itinerary) {
                                                            // 🛡️ JSON 防漏閥：將 JSON 轉為友善的 Markdown
                                                            const summary = `### ✨ ${itinerary.title || t('ai_itinerary_found' as TranslationKey)}\n` +
                                                                itinerary.items.slice(0, 5).map((it: ParsedItineraryItem) => `- Day ${it.day_number}: ${it.place_name} (${it.time_slot || ''})`).join('\n') +
                                                                (itinerary.items.length > 5 ? (zh ? `\n... (還有 ${itinerary.items.length - 5} 個地點)` : `\n... (${itinerary.items.length - 5} more spots)`) : '')
                                                            return <ReactMarkdown remarkPlugins={[remarkGfm]}>{summary}</ReactMarkdown>
                                                        }
                                                        if (cleanContent === "__GREETING__") {
                                                            return (
                                                                <div className="space-y-3">
                                                                    <div className="p-3.5 rounded-xl bg-tabiji-mist/35 dark:bg-white/5 border border-tabiji-forest/10 dark:border-white/10 shadow-xs">
                                                                        {/* 頂部 Header */}
                                                                        <div className="flex items-center gap-3 pb-2.5 mb-2.5 border-b border-tabiji-forest/8 dark:border-white/10">
                                                                            <div className="relative shrink-0">
                                                                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                                                                <img
                                                                                    src="/images/ryan-bot-hero.webp"
                                                                                    alt="Ryan AI Companion"
                                                                                    className="w-11 h-11 object-contain drop-shadow-[0_4px_12px_rgba(11,48,38,0.2)]"
                                                                                />
                                                                                <span className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-white dark:ring-tabiji-dark" />
                                                                            </div>
                                                                            <div className="min-w-0">
                                                                                <div className="flex items-center gap-1.5">
                                                                                    <h4 className="font-semibold text-xs text-tabiji-charcoal dark:text-tabiji-paper">
                                                                                        {zh ? 'Ryan AI 隨行旅伴' : 'Ryan AI Companion'}
                                                                                    </h4>
                                                                                    <span className="text-[10px] px-1.5 py-0.2 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-medium border border-emerald-500/20">
                                                                                        Online
                                                                                    </span>
                                                                                </div>
                                                                                <p className="text-[11px] text-tabiji-slate">
                                                                                    {t('ai_subtitle')}
                                                                                </p>
                                                                            </div>
                                                                        </div>

                                                                        {/* 迎賓內容 Markdown 渲染 */}
                                                                        <div className="text-xs text-tabiji-charcoal dark:text-tabiji-paper/90 leading-relaxed [&_p]:my-1.5 [&_strong]:text-tabiji-forest dark:[&_strong]:text-emerald-300 [&_strong]:font-semibold [&_ul]:my-1.5 [&_ul]:space-y-1 [&_ul]:pl-4 [&_ul]:list-disc [&_li]:leading-normal">
                                                                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                                                {t('ai_greet_msg')}
                                                                            </ReactMarkdown>
                                                                        </div>

                                                                        {/* 🆕 快捷提示詞膠囊按鈕 */}
                                                                        <div className="mt-3 pt-2.5 border-t border-tabiji-forest/8 dark:border-white/10 flex flex-wrap gap-1.5">
                                                                            <button
                                                                                type="button"
                                                                                onClick={() => {
                                                                                    setInput(t('ai_quick_checkup' as TranslationKey) || "幫我看這行程順不順？")
                                                                                    textareaRef.current?.focus()
                                                                                }}
                                                                                className="text-[11px] px-2.5 py-1 rounded-full bg-white/90 dark:bg-white/10 text-tabiji-forest dark:text-tabiji-paper border border-tabiji-forest/15 dark:border-white/15 hover:bg-tabiji-forest/5 dark:hover:bg-white/15 transition-colors cursor-pointer active:scale-95 shadow-2xs font-medium flex items-center gap-1"
                                                                            >
                                                                                🩺 {t('ai_quick_checkup' as TranslationKey) || "幫我看這行程順不順？"}
                                                                            </button>
                                                                            <button
                                                                                type="button"
                                                                                onClick={() => {
                                                                                    setInput(t('ai_quick_food' as TranslationKey) || "推薦這附近必吃美食")
                                                                                    textareaRef.current?.focus()
                                                                                }}
                                                                                className="text-[11px] px-2.5 py-1 rounded-full bg-white/90 dark:bg-white/10 text-tabiji-charcoal dark:text-tabiji-paper border border-tabiji-forest/15 dark:border-white/15 hover:bg-tabiji-forest/5 dark:hover:bg-white/15 transition-colors cursor-pointer active:scale-95 shadow-2xs flex items-center gap-1"
                                                                            >
                                                                                🍜 {t('ai_quick_food' as TranslationKey) || "推薦這附近必吃美食"}
                                                                            </button>
                                                                            <button
                                                                                type="button"
                                                                                onClick={() => {
                                                                                    setInput(t('ai_quick_traffic' as TranslationKey) || "今天行程交通怎麼搭最順？")
                                                                                    textareaRef.current?.focus()
                                                                                }}
                                                                                className="text-[11px] px-2.5 py-1 rounded-full bg-white/90 dark:bg-white/10 text-tabiji-charcoal dark:text-tabiji-paper border border-tabiji-forest/15 dark:border-white/15 hover:bg-tabiji-forest/5 dark:hover:bg-white/15 transition-colors cursor-pointer active:scale-95 shadow-2xs flex items-center gap-1"
                                                                            >
                                                                                🚇 {t('ai_quick_traffic' as TranslationKey) || "今天行程交通怎麼搭？"}
                                                                            </button>
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                            )
                                                        }
                                                        return <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleanContent}</ReactMarkdown>
                                                    })()}
                                                </div>
                                                ) : null}

                                                {/* 🆕 v22.1: 一鍵匯入橋樑 */}
                                                {(cleanContent && (tryParseItinerary(cleanContent) || cleanContent.includes('| Day |') || cleanContent.includes('## Day 1'))) && (
                                                    <div className="mt-3">
                                                        <Button
                                                            size="sm"
                                                            variant="outline"
                                                            className="w-full h-9 rounded-xl border-tabiji-amber/30 bg-tabiji-amber/15 text-tabiji-amber hover:bg-tabiji-amber/25 hover:border-tabiji-amber/40 font-bold gap-2 shadow-xs transition-all active:scale-95 cursor-pointer"
                                                            onClick={async () => {
                                                                // 將內容傳遞給 ToolsView (透過事件)
                                                                const event = new CustomEvent('ai-import-itinerary', {
                                                                    detail: { content: msg.displayContent }
                                                                })
                                                                window.dispatchEvent(event)
                                                                toast.success(t('ai_sending_to_import' as TranslationKey))
                                                                // 自動開啟行程介面 (Itinerary View)
                                                                const navEvent = new CustomEvent('navigate-to-trips')
                                                                window.dispatchEvent(navEvent)
                                                                setIsComposerMenuOpen(false)
                                                                setIsOpen(false)
                                                            }}
                                                        >
                                                            ✨ {t('ai_one_click_import' as TranslationKey) || "立即匯入行程"}
                                                        </Button>
                                                    </div>
                                                )}

                                                {/* 來源標籤 */}
                                                {msg.groundingSources && msg.groundingSources.length > 0 && (
                                                    <SourceCitation sources={msg.groundingSources} />
                                                )}

                                            </>
                                        ) : (
                                            <div className="whitespace-pre-wrap wrap-anywhere">{msg.displayContent}</div>
                                        )}
                                    </div>
                                </div>
                            )})}
                            {isLoading && (
                                <div className="flex gap-3 max-w-[85%]">
                                    <div className="relative w-8 h-8 rounded-full bg-white/90 dark:bg-[#182320] border border-tabiji-forest/15 dark:border-white/15 flex items-center justify-center shrink-0 mt-1 overflow-hidden shadow-xs">
                                        {/* eslint-disable-next-line @next/next/no-img-element */}
                                        <img src="/images/ryan-bot-avatar.webp" alt="Ryan AI Thinking" className="w-6 h-6 object-contain animate-pulse" />
                                        <span className="absolute inset-0 rounded-full border border-emerald-500/40 animate-ping pointer-events-none" />
                                    </div>
                                    <div className="flex flex-col gap-2">
                                        {/* 🆕 脈衝手風琴 */}
                                        <ThinkingIndicator phase={searchStatus.phase} />
                                        {searchStatus.phase === "searching" && (searchStatus.query || searchStatus.url) && (
                                            <div className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-tabiji-forest dark:text-emerald-300 bg-tabiji-mist/50 dark:bg-white/5 border border-tabiji-forest/15 dark:border-white/10 rounded-xl shadow-2xs animate-in fade-in duration-200 max-w-sm">
                                                <span className="relative flex h-2 w-2 shrink-0">
                                                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                                                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                                                </span>
                                                <span className="truncate">
                                                    {searchStatus.query ? `🔍 ${searchStatus.query}` : `🌐 ${searchStatus.url}`}
                                                </span>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                            {/* 🆕 v3.5: 重試按鈕 */}
                            {lastFailedMessage && !isLoading && (
                                <div className="flex justify-center">
                                    <button
                                        onClick={() => {
                                            setInput(lastFailedMessage)
                                            setLastFailedMessage(null)
                                            // 移除最後一條錯誤訊息
                                            setMessages(prev => prev.slice(0, -1))
                                        }}
                                        className="text-sm bg-tabiji-forest/10 text-tabiji-forest dark:text-tabiji-paper dark:bg-white/10 px-4 py-2 rounded-full hover:bg-tabiji-forest/15 transition-colors flex items-center gap-2 cursor-pointer"
                                    >
                                        🔄 {t('ai_retry')}
                                    </button>
                                </div>
                            )}
                            <div ref={messagesEndRef} />
                        </div>

                        {/* Unified Two-Zone Composer */}
                        <ChatComposer
                            input={input}
                            onInputChange={setInput}
                            onSend={handleSendMessage}
                            onStop={handleStopGeneration}
                            isLoading={isLoading}
                            isDeepResearch={isDeepResearch}
                            onToggleDeepResearch={handleToggleDeepResearch}
                            selectedImage={selectedImage}
                            imagePreviewError={imagePreviewError}
                            isCompressingImage={isCompressingImage}
                            onImageFileSelect={handleImageFile}
                            onImagePreviewError={() => setImagePreviewError(true)}
                            onRemoveImage={handleRemoveImage}
                            textareaRef={textareaRef}
                            menuOpen={isComposerMenuOpen && !isDocked}
                            onMenuOpenChange={setIsComposerMenuOpen}
                            isHidden={isDocked}
                        />
                    </div>
                </div>
                </>
            )}

            {/* Toggle Button - 2D Edge Draggable Liquid Glass (hidden when fullscreen chat is open & undocked so it never obscures the Two-Zone Composer) */}
            <div
                ref={dragRef}
                className={cn("fixed z-110 will-change-transform transform-gpu", isOpen && !isDocked && "hidden")}
                style={{
                    right: position.x,
                    bottom: position.y,
                    touchAction: isDragging ? "none" : "auto",
                    willChange: isDragging ? "right, bottom" : "auto"
                }}
            >
                <Button
                    id="tour-ai-bot"
                    size="icon"
                    className={cn(
                        "h-14 w-14 rounded-full transition-all duration-300 hover:scale-105 touch-none relative overflow-hidden",
                        "backdrop-blur-2xl border border-tabiji-forest/15 dark:border-white/20 hover:bg-tabiji-paper dark:hover:bg-tabiji-dark",
                        isOpen
                            ? "bg-tabiji-paper/90 dark:bg-tabiji-dark/90 text-tabiji-charcoal dark:text-tabiji-paper shadow-md"
                            : "bg-tabiji-paper/90 dark:bg-tabiji-dark/90 text-tabiji-forest dark:text-tabiji-paper shadow-[0_8px_32px_rgba(11,48,38,0.12),inset_0_1px_1px_rgba(255,255,255,0.8)] dark:shadow-[0_8px_32px_rgba(0,0,0,0.5),inset_0_1px_1px_rgba(255,255,255,0.1)]",
                        isIdle && !isOpen && !isDragging ? "opacity-40 hover:opacity-100" : "opacity-100",
                        isDragging && "scale-110 shadow-2xl"
                    )}
                    onClick={() => { if (!hasMovedRef.current) { setIsComposerMenuOpen(false); setIsOpen(!isOpen); setIsDocked(false) } }}
                    onMouseDown={handleMouseDown}
                    onTouchStart={handleTouchStart}
                >
                    {isOpen ? (
                        <X className="w-6 h-6 text-tabiji-charcoal dark:text-tabiji-paper" />
                    ) : (
                        <div className="relative w-full h-full flex items-center justify-center">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                                src="/images/ryan-bot-avatar.webp"
                                alt="Ryan AI"
                                className="w-9 h-9 object-contain drop-shadow-[0_2px_8px_rgba(11,48,38,0.3)] transition-transform hover:scale-110"
                            />
                            {isLoading && (
                                <span className="absolute inset-0 rounded-full border-2 border-emerald-500/80 animate-ping pointer-events-none" />
                            )}
                        </div>
                    )}
                </Button>
            </div>
        </>
    )
}
