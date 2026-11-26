"use client"

/**
 * SSE Parser - 解析 Server-Sent Events 串流
 * 
 * 處理跨 chunk 分割的事件，提供穩定的事件回調
 */

export interface SSEEvent {
    event: string
    data: string
}

import * as authSession from './auth-session'

export interface SSEHandlers {
    onStart?: () => void
    onThinking?: (status: string, meta?: { query?: string; url?: string; thought?: string }) => void
    onText?: (text: string) => void
    onTool?: (toolCall: { name: string; args: Record<string, unknown> }) => void
    onSignature?: (thought: string) => void
    onDone?: (data: {
        model_used: string;
        raw_parts: { text: string }[];
        sources?: Array<{
            title: string;
            url?: string;
            uri?: string;
            citation_index?: number;
            category?: string;
            badge?: { text: string; color: string };
            snippet?: string;
        }>
    }) => void
    onError?: (error: { message: string; code: number }) => void
    onReset?: (data?: { reason?: string; model?: string }) => void
    onHeartbeat?: () => void
}

/**
 * 解析 SSE 格式的字串
 * 處理跨 chunk 的事件分割
 */
export function parseSSE(chunk: string, buffer: string): { events: SSEEvent[]; remaining: string } {
    const fullData = buffer + chunk
    const events: SSEEvent[] = []

    // SSE 事件以 \n\n 分隔
    const parts = fullData.split("\n\n")

    // 最後一個可能是不完整的，保留
    const remaining = parts.pop() || ""

    for (const part of parts) {
        if (!part.trim()) continue

        // 逐行剔除 `:` 心跳/註解行（避免 FP-104：心跳行與 event:/data: 黏在同一區塊時誤殺整個事件）
        const rawLines = part.split("\n")
        let sawComment = false
        let eventName = "message"
        const dataLines: string[] = []
        let hasEventOrData = false

        for (const rawLine of rawLines) {
            const line = rawLine.replace(/\r$/, "")
            if (!line.trim()) continue
            if (line.trimStart().startsWith(":")) {
                sawComment = true
                continue
            }
            if (line.startsWith("event:")) {
                eventName = line.slice(6).trim()
                hasEventOrData = true
            } else if (line.startsWith("data:")) {
                dataLines.push(line.slice(5).trim())
                hasEventOrData = true
            }
        }

        if (!hasEventOrData) {
            if (sawComment) {
                events.push({ event: "heartbeat", data: "" })
            }
            continue
        }

        events.push({ event: eventName, data: dataLines.join("\n") })
    }

    return { events, remaining }
}

/**
 * 處理 SSE 事件，呼叫對應的 handler
 */
export function handleSSEEvent(event: SSEEvent, handlers: SSEHandlers): boolean {
    let isTerminal = false
    try {
        switch (event.event) {
            case "start":
                handlers.onStart?.()
                break

            case "thinking":
                try {
                    const thinkingData = JSON.parse(event.data)
                    const hasMeta = Boolean(thinkingData.query || thinkingData.url || thinkingData.thought)
                    if (hasMeta) {
                        handlers.onThinking?.(thinkingData.status, {
                            query: thinkingData.query,
                            url: thinkingData.url,
                            thought: thinkingData.thought,
                        })
                    } else {
                        handlers.onThinking?.(thinkingData.status)
                    }
                } catch {
                    handlers.onThinking?.(event.data)
                }
                break

            case "text":
                const textData = JSON.parse(event.data)
                handlers.onText?.(textData.text)
                break

            case "tool":
                const toolData = JSON.parse(event.data)
                handlers.onTool?.(toolData.function_call)
                break

            case "signature":
                const sigData = JSON.parse(event.data)
                handlers.onSignature?.(sigData.thought)
                break

            case "done":
                const doneData = JSON.parse(event.data)
                handlers.onDone?.(doneData)
                isTerminal = true  // done 也是終結事件
                break

            case "error":
                try {
                    const errorData = JSON.parse(event.data)
                    handlers.onError?.(errorData)
                } catch {
                    handlers.onError?.({ message: event.data || "Unknown SSE streaming error", code: 500 })
                }
                isTerminal = true  // 🛡️ error 是終結事件
                break

            case "reset":
                try {
                    const resetData = event.data ? JSON.parse(event.data) : undefined
                    handlers.onReset?.(resetData)
                } catch {
                    handlers.onReset?.()
                }
                break

            case "heartbeat":
                handlers.onHeartbeat?.()
                break
        }
    } catch (e) {
        console.error("SSE event parse error:", e, event)
    }
    return isTerminal
}

/**
 * 串流聊天請求
 * 使用 fetch POST + ReadableStream (支援 BYOK Headers)
 */
export async function streamChat(
    apiUrl: string,
    message: string,
    history: Array<{ role: string; displayContent?: string; rawParts?: unknown[] }>,
    apiKey: string,
    handlers: SSEHandlers,
    signal?: AbortSignal,
    // 🆕 新增行程上下文、使用者 ID 與時間感知
    itinerary?: unknown,
    focused_day?: number,
    userId?: string,
    clientTime?: string,
    clientTimezone?: string,
    locale?: string
): Promise<void> {
    const defaultTime = clientTime || new Date().toISOString()
    const defaultTz = clientTimezone || (typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().timeZone : "Asia/Taipei")

    let token = authSession.getCachedToken()
    if (!token && typeof window !== "undefined") {
        token = await authSession.ensureValidSession().catch(() => null)
    }

    const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "X-Gemini-API-Key": apiKey,
        "X-User-ID": userId || ""
    }
    if (token) {
        headers["Authorization"] = `Bearer ${token}`
    }

    const requestPayload = JSON.stringify({
        message,
        history: history.map(msg => ({
            role: msg.role,
            rawParts: msg.rawParts,
            displayContent: msg.displayContent
        })),
        thought_signatures: [],  // Round-trip signatures if needed
        // 🆕 帶入行程上下文與焦點天數
        current_itinerary: itinerary,
        focused_day: focused_day,
        // 🆕 即時時間與時區感知
        client_time: defaultTime,
        client_timezone: defaultTz,
        locale: locale || "zh"
    });

    let response = await fetch(`${apiUrl}/api/chat/stream`, {
        method: "POST",
        headers,
        body: requestPayload,
        signal
    });

    // 🛡️ 401 自癒重試防禦：僅針對 Tabiji Session JWT 過期重刷；若是 Gemini API Key 401 失敗，保留本地 Session 不誤刪
    if (response.status === 401 && typeof window !== "undefined" && !signal?.aborted) {
        let errDetail = ""
        try {
            const errJson = await response.clone().json()
            errDetail = String(errJson?.detail || errJson?.message || "")
        } catch {
            errDetail = await response.clone().text().catch(() => "")
        }
        const isGeminiKeyAuthError = /gemini|api[_ ]?key|金鑰|個人檔案|profile|google ai studio|已失效|無效或已過期/i.test(errDetail)
        const hasSessionToken = Boolean(token || localStorage.getItem("tabiji_session_token"))

        if (!isGeminiKeyAuthError && hasSessionToken) {
            console.warn("⚠️ [SSE] Received 401 Unauthorized during stream handshake, refreshing session token...")
            const freshToken = await authSession.ensureValidSession(true).catch(() => null)
            if (!freshToken) {
                const isTransientFailure = typeof authSession.wasLastAuthExchangeTransientFailure === "function" && authSession.wasLastAuthExchangeTransientFailure()
                if (!isTransientFailure) {
                    localStorage.removeItem("tabiji_session_token")
                }
            }
            if (freshToken && !signal?.aborted) {
                headers["Authorization"] = `Bearer ${freshToken}`
                response = await fetch(`${apiUrl}/api/chat/stream`, {
                    method: "POST",
                    headers,
                    body: requestPayload,
                    signal
                })
            }
        } else if (isGeminiKeyAuthError) {
            throw new Error(errDetail || "API_KEY_INVALID")
        }
    }

    if (!response.ok) {
        let errDetail = ""
        try {
            const errJson = await response.clone().json()
            errDetail = String(errJson?.detail || errJson?.message || "")
        } catch {
            errDetail = ""
        }
        throw new Error(errDetail || `HTTP ${response.status}: ${response.statusText}`)
    }

    if (!response.body) {
        throw new Error("No response body")
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""
    let streamTerminated = false  // 🛡️ 終結旗標

    try {
        while (true) {
            // 🆕 v3.7: 檢查是否已被 abort
            if (signal?.aborted || streamTerminated) {
                if (signal?.aborted) console.log("🛑 SSE 已被用戶中斷")
                break
            }

            const { done, value } = await reader.read()
            if (done) break

            // 🆕 再次檢查 abort（在 read 等待期間可能被 abort）
            if (signal?.aborted) {
                console.log("🛑 SSE 在讀取時被中斷")
                break
            }

            const chunk = decoder.decode(value, { stream: true })
            const { events, remaining } = parseSSE(chunk, buffer)
            buffer = remaining

            for (const event of events) {
                // 🆕 處理事件前也檢查 abort
                if (signal?.aborted || streamTerminated) break
                const isTerminal = handleSSEEvent(event, handlers)
                if (isTerminal) {
                    streamTerminated = true
                    break
                }
            }
        }

        // 處理最後剩餘的 buffer（只在未 abort 且未終結時）
        if (buffer.trim() && !signal?.aborted && !streamTerminated) {
            const { events } = parseSSE(buffer + "\n\n", "")
            for (const event of events) {
                handleSSEEvent(event, handlers)
            }
        }
    } finally {
        reader.releaseLock()
    }
}

export interface StreamDeepResearchParams {
    apiUrl: string
    apiKey: string
    prompt: string
    origin?: string
    destination?: string
    booking_context?: string
    locale?: string
    signal?: AbortSignal
    onThinking?: (status: string) => void
    onText?: (text: string) => void
    onHeartbeat?: () => void
}

export interface StreamDeepResearchResult {
    supported: boolean
    text?: string
    engine?: string
    error?: string
}

/**
 * Opt-in Two-Phase SSE 深度研究用戶端。
 * 遇 404/405/非 event-stream 回應時回傳 { supported: false }，供呼叫端無縫退回 JSON 輪詢。
 */
export async function streamDeepResearch(
    params: StreamDeepResearchParams
): Promise<StreamDeepResearchResult> {
    let response: Response
    try {
        response = await fetch(`${params.apiUrl}/api/agents/research/stream`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Gemini-API-Key": params.apiKey,
            },
            signal: params.signal,
            body: JSON.stringify({
                prompt: params.prompt,
                origin: params.origin || undefined,
                destination: params.destination || undefined,
                booking_context: params.booking_context || undefined,
                locale: params.locale || "zh",
            }),
        })
    } catch (err) {
        if ((err as Error)?.name === "AbortError") throw err
        return { supported: false }
    }

    if (response.status === 404 || response.status === 405 || response.status === 501) {
        return { supported: false }
    }
    const contentType = response.headers.get("content-type") || ""
    if (!response.ok) {
        let detail = ""
        try {
            const errJson = await response.clone().json()
            detail = String(errJson?.detail || errJson?.message || "")
        } catch {
            detail = ""
        }
        return { supported: true, error: detail || `HTTP ${response.status}` }
    }
    if (!contentType.includes("text/event-stream") || !response.body) {
        return { supported: false }
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""
    let collectedText = ""
    let engine = "gemini-flash-stream"
    let streamError: string | undefined
    let terminated = false

    try {
        while (!terminated && !params.signal?.aborted) {
            const { done, value } = await reader.read()
            if (done) break
            const chunk = decoder.decode(value, { stream: true })
            const { events, remaining } = parseSSE(chunk, buffer)
            buffer = remaining

            for (const ev of events) {
                if (params.signal?.aborted) break
                if (ev.event === "heartbeat") {
                    params.onHeartbeat?.()
                } else if (ev.event === "thinking") {
                    try {
                        const d = JSON.parse(ev.data)
                        params.onThinking?.(String(d?.status || "researching"))
                    } catch {
                        params.onThinking?.(ev.data || "researching")
                    }
                } else if (ev.event === "text") {
                    try {
                        const d = JSON.parse(ev.data)
                        if (typeof d?.text === "string") {
                            collectedText += d.text
                            params.onText?.(d.text)
                        }
                    } catch { /* ignore */ }
                } else if (ev.event === "done") {
                    try {
                        const d = JSON.parse(ev.data)
                        engine = String(d?.engine || d?.model_used || engine)
                    } catch { /* ignore */ }
                    terminated = true
                    break
                } else if (ev.event === "error") {
                    try {
                        const d = JSON.parse(ev.data)
                        streamError = String(d?.message || "Deep research failed")
                    } catch {
                        streamError = ev.data || "Deep research failed"
                    }
                    terminated = true
                    break
                }
            }
        }
    } finally {
        reader.releaseLock()
    }

    if (streamError) {
        return { supported: true, error: streamError }
    }
    return { supported: true, text: collectedText, engine }
}
