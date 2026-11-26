/**
 * @vitest-environment jsdom
 */
import React, { useRef, useState } from "react"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react"

const {
    mockStreamChat,
    mockToastError,
    mockToastInfo,
    mockToastSuccess,
    mockCompressImage,
} = vi.hoisted(() => ({
    mockStreamChat: vi.fn(),
    mockToastError: vi.fn(),
    mockToastInfo: vi.fn(),
    mockToastSuccess: vi.fn(),
    mockCompressImage: vi.fn(),
}))

vi.mock("@/lib/image-utils", async (importOriginal) => {
    const actual = await importOriginal<typeof import("@/lib/image-utils")>()
    return {
        ...actual,
        compressImage: (...args: unknown[]) => mockCompressImage(...args),
    }
})

vi.mock("@/lib/sse-parser", async () => {
    const actual = await vi.importActual<typeof import("@/lib/sse-parser")>("@/lib/sse-parser")
    return {
        ...actual,
        streamChat: (...args: unknown[]) => mockStreamChat(...args),
    }
})

vi.mock("@/lib/trip-context", () => ({
    useTripContext: () => ({
        activeTrip: { id: "trip-1", title: "Tokyo 5 Days" },
        activeTripId: "trip-1",
        userId: "user-1",
    }),
}))

vi.mock("@/lib/stores/tripStore", () => ({
    useFocusedDay: () => 1,
}))

vi.mock("@/lib/hooks", () => ({
    useTripDetail: () => ({
        trip: { id: "trip-1", title: "Tokyo 5 Days", items: [] },
    }),
}))

vi.mock("@/lib/polling-manager", () => ({
    useDynamicPolling: () => 0,
}))

vi.mock("@/lib/security", () => ({
    getSecureApiKey: () => "AIzaSyMockChatComposerTestKey1234",
}))

vi.mock("@/lib/stores/weatherStore", () => ({
    useWeatherStore: () => ({
        getWeatherData: () => null,
    }),
}))

vi.mock("@/lib/search-cache", () => ({
    setSearchCache: vi.fn().mockResolvedValue(undefined),
}))

vi.mock("@/lib/auth-session", () => ({
    getCachedToken: () => "mock-session-jwt",
    ensureValidSession: vi.fn().mockResolvedValue("mock-session-jwt"),
    wasLastAuthExchangeTransientFailure: () => false,
}))

vi.mock("sonner", () => ({
    toast: {
        error: (...args: unknown[]) => mockToastError(...args),
        info: (...args: unknown[]) => mockToastInfo(...args),
        success: (...args: unknown[]) => mockToastSuccess(...args),
    },
}))

import ChatComposer, { type ChatComposerProps } from "@/components/chat/ChatComposer"
import ChatWidget from "@/components/chat-widget"
import { LanguageProvider } from "@/lib/LanguageContext"
import { chatTranslations } from "@/lib/i18n/chat"

function ComposerHarness(
    overrides: Partial<Omit<ChatComposerProps, "textareaRef">> & {
        initialInput?: string
        initialDeepResearch?: boolean
    } = {}
) {
    const [input, setInput] = useState(overrides.initialInput ?? "")
    const [isDeepResearch, setIsDeepResearch] = useState(overrides.initialDeepResearch ?? false)
    const textareaRef = useRef<HTMLTextAreaElement | null>(null)

    return (
        <LanguageProvider>
            <ChatComposer
                input={overrides.input ?? input}
                onInputChange={(val) => {
                    setInput(val)
                    overrides.onInputChange?.(val)
                }}
                onSend={overrides.onSend ?? vi.fn()}
                onStop={overrides.onStop ?? vi.fn()}
                isLoading={overrides.isLoading ?? false}
                isDeepResearch={overrides.isDeepResearch ?? isDeepResearch}
                onToggleDeepResearch={(next) => {
                    setIsDeepResearch(next)
                    overrides.onToggleDeepResearch?.(next)
                }}
                selectedImage={overrides.selectedImage ?? null}
                imagePreviewError={overrides.imagePreviewError ?? false}
                isCompressingImage={overrides.isCompressingImage ?? false}
                onImageFileSelect={overrides.onImageFileSelect ?? vi.fn()}
                onImagePreviewError={overrides.onImagePreviewError ?? vi.fn()}
                onRemoveImage={overrides.onRemoveImage ?? vi.fn()}
                textareaRef={textareaRef}
            />
        </LanguageProvider>
    )
}

describe("Unified ChatComposer & ChatWidget Safety Net Tests", () => {
    const originalFetch = global.fetch

    beforeEach(() => {
        vi.clearAllMocks()
        localStorage.clear()
        localStorage.setItem("user_uuid", "user-1")
        localStorage.setItem("user_nickname", "Ryan")
        Element.prototype.scrollIntoView = vi.fn()
        global.ResizeObserver = class {
            observe = vi.fn()
            unobserve = vi.fn()
            disconnect = vi.fn()
        } as unknown as typeof ResizeObserver
    })

    afterEach(() => {
        global.fetch = originalFetch
        vi.useRealTimers()
        localStorage.clear()
        vi.restoreAllMocks()
    })

    it("opens + Radix Popover menu with 3 actions in zh & en, preserves sentinel file-input DOM order, and avoids ghost accent bleed", async () => {
        const { container, unmount } = render(<ComposerHarness />)

        // Sentinel Lock: album input MUST be first without capture, camera input second with capture="environment"
        const fileInputs = Array.from(container.querySelectorAll('input[type="file"]')) as HTMLInputElement[]
        expect(fileInputs).toHaveLength(2)
        expect(fileInputs[0].getAttribute("accept")).toBe("image/*")
        expect(fileInputs[0].hasAttribute("capture")).toBe(false)
        expect(fileInputs[1].getAttribute("accept")).toBe("image/*")
        expect(fileInputs[1].getAttribute("capture")).toBe("environment")

        // No ghost variant / hover:bg-accent orange bleed on any composer button
        const composerButtons = Array.from(container.querySelectorAll("button"))
        for (const btn of composerButtons) {
            expect(btn.getAttribute("data-variant")).not.toBe("ghost")
            expect(btn.className).not.toContain("hover:bg-accent")
            expect(btn.querySelector("button")).toBeNull()
        }

        // Open + menu in zh
        fireEvent.click(screen.getByRole("button", { name: "更多工具" }))
        expect(await screen.findByText("上傳圖片")).toBeInTheDocument()
        expect(screen.getByText("拍照即問")).toBeInTheDocument()
        expect(screen.getByText("深度研究")).toBeInTheDocument()

        // Clicking Upload Photo synchronously triggers album input click
        const albumClickSpy = vi.spyOn(fileInputs[0], "click")
        fireEvent.click(screen.getByText("上傳圖片"))
        expect(albumClickSpy).toHaveBeenCalledTimes(1)

        // Clicking Take Photo synchronously triggers camera input click
        fireEvent.click(screen.getByRole("button", { name: "更多工具" }))
        const cameraClickSpy = vi.spyOn(fileInputs[1], "click")
        fireEvent.click(await screen.findByText("拍照即問"))
        expect(cameraClickSpy).toHaveBeenCalledTimes(1)

        unmount()

        // Switch to en and verify bilingual labels
        localStorage.setItem("app_language", "en")
        render(<ComposerHarness />)
        const moreBtnEn = await screen.findByRole("button", { name: "More actions" })
        fireEvent.click(moreBtnEn)
        expect(await screen.findByText("Upload photo")).toBeInTheDocument()
        expect(screen.getByText("Take photo")).toBeInTheDocument()
        expect(screen.getByText("Deep Research")).toBeInTheDocument()
    })

    it("toggles Deep Research from + menu, shows dismissible pill, swaps placeholder, focuses textarea, and collapses cleanly", async () => {
        render(<ComposerHarness />)

        const textarea = screen.getByRole("textbox")
        expect(textarea).toHaveAttribute("placeholder", "問問 Ryan...")

        fireEvent.click(screen.getByRole("button", { name: "更多工具" }))
        fireEvent.click(await screen.findByText("深度研究"))

        const dismissPill = await screen.findByRole("button", { name: "關閉深度研究模式" })
        expect(dismissPill).toBeInTheDocument()
        expect(dismissPill.querySelector("button")).toBeNull()
        expect(textarea).toHaveAttribute("placeholder", "輸入想深度研究或精算的主題...")
        await waitFor(() => {
            expect(document.activeElement).toBe(textarea)
        })

        // Single-click dismiss
        fireEvent.click(dismissPill)
        await waitFor(() => {
            expect(screen.queryByRole("button", { name: "關閉深度研究模式" })).not.toBeInTheDocument()
        })
        expect(textarea).toHaveAttribute("placeholder", "問問 Ryan...")
    })

    it("disables Deep Research option when an image is attached or compressing, and disables send while compressing", async () => {
        const onToggleDeepResearch = vi.fn()
        const onSend = vi.fn()
        const { rerender } = render(
            <ComposerHarness
                selectedImage="data:image/png;base64,AAAA"
                onToggleDeepResearch={onToggleDeepResearch}
                onSend={onSend}
            />
        )

        fireEvent.click(screen.getByRole("button", { name: "更多工具" }))
        const deepBtnWithImage = (await screen.findByText("深度研究")).closest("button")
        expect(deepBtnWithImage).toBeDisabled()
        expect(screen.getByText("移除圖片後可用")).toBeInTheDocument()
        fireEvent.click(deepBtnWithImage!)
        expect(onToggleDeepResearch).not.toHaveBeenCalled()

        // While compressing image, Deep Research AND Send must both be disabled
        rerender(
            <ComposerHarness
                input="Check this menu"
                selectedImage={null}
                isCompressingImage={true}
                onToggleDeepResearch={onToggleDeepResearch}
                onSend={onSend}
            />
        )
        expect(screen.getByText("正在最佳化圖片...")).toBeInTheDocument()
        const sendBtn = screen.getByRole("button", { name: "發送訊息" })
        expect(sendBtn).toBeDisabled()
        fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter", shiftKey: false })
        expect(onSend).not.toHaveBeenCalled()
    })

    it("smart-collapses exploration quick chips when typing, clicking a chip, or enabling Deep Research", async () => {
        render(<ComposerHarness />)

        // Visible in empty idle state
        const exploreChip = screen.getByRole("button", { name: /探索周邊/ })
        expect(exploreChip).toBeInTheDocument()
        expect(screen.getByRole("button", { name: /必吃拉麵/ })).toBeInTheDocument()
        expect(screen.getByRole("button", { name: /應急藥妝/ })).toBeInTheDocument()
        expect(screen.getByRole("button", { name: /特色咖啡/ })).toBeInTheDocument()

        // Clicking chip populates textarea and collapses chips
        fireEvent.click(exploreChip)
        const textarea = screen.getByRole("textbox") as HTMLTextAreaElement
        expect(textarea.value).toBe(chatTranslations.zh.ai_chip_explore_prompt)
        await waitFor(() => {
            expect(screen.queryByRole("button", { name: /探索周邊/ })).not.toBeInTheDocument()
        })

        // Clearing input brings chips back
        fireEvent.change(textarea, { target: { value: "" } })
        expect(await screen.findByRole("button", { name: /探索周邊/ })).toBeInTheDocument()

        // Enabling Deep Research hides chips too
        fireEvent.click(screen.getByRole("button", { name: "更多工具" }))
        fireEvent.click(await screen.findByText("深度研究"))
        await waitFor(() => {
            expect(screen.queryByRole("button", { name: /探索周邊/ })).not.toBeInTheDocument()
        })
    })

    it("morphs right button from Send to Stop when isLoading=true and respects IME composition guard", () => {
        const onSend = vi.fn()
        const onStop = vi.fn()

        const { rerender } = render(
            <ComposerHarness initialInput="Hello Tokyo" onSend={onSend} onStop={onStop} isLoading={false} />
        )

        const textarea = screen.getByRole("textbox")
        // IME composing Enter MUST NOT submit
        const composingEvent = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })
        Object.defineProperty(composingEvent, "isComposing", { value: true })
        textarea.dispatchEvent(composingEvent)
        expect(onSend).not.toHaveBeenCalled()

        // Clicking Send button submits
        fireEvent.click(screen.getByRole("button", { name: "發送訊息" }))
        expect(onSend).toHaveBeenCalledTimes(1)

        // Loading morphs into Stop button
        rerender(
            <ComposerHarness initialInput="" onSend={onSend} onStop={onStop} isLoading={true} />
        )
        const stopBtn = screen.getByRole("button", { name: "停止生成" })
        expect(stopBtn).toBeInTheDocument()
        expect(screen.queryByRole("button", { name: "發送訊息" })).not.toBeInTheDocument()
        fireEvent.click(stopBtn)
        expect(onStop).toHaveBeenCalledTimes(1)
    })

    it("silently supports image paste and file drop while refusing to hijack rich-text paste containing plain text", () => {
        const onImageFileSelect = vi.fn()
        render(<ComposerHarness onImageFileSelect={onImageFileSelect} />)

        const textarea = screen.getByRole("textbox")
        const pngFile = new File([new Uint8Array([137, 80, 78, 71])], "menu.png", { type: "image/png" })

        // 1. Pure image paste triggers onImageFileSelect
        fireEvent.paste(textarea, {
            clipboardData: {
                getData: () => "",
                items: [{ kind: "file", type: "image/png", getAsFile: () => pngFile }],
                files: [pngFile],
            },
        })
        expect(onImageFileSelect).toHaveBeenCalledTimes(1)
        expect(onImageFileSelect).toHaveBeenCalledWith(pngFile)

        // 2. Rich-text paste (both plain text + image snapshot from Docs/Sheets) MUST NOT be hijacked
        onImageFileSelect.mockClear()
        fireEvent.paste(textarea, {
            clipboardData: {
                getData: (type: string) => (type === "text/plain" ? "Shinjuku Ramen Budget" : ""),
                items: [{ kind: "file", type: "image/png", getAsFile: () => pngFile }],
                files: [pngFile],
            },
        })
        expect(onImageFileSelect).not.toHaveBeenCalled()

        // 3. Silent file drop triggers onImageFileSelect
        const dropTarget = textarea.closest("div.rounded-\\[24px\\]") as HTMLElement
        expect(dropTarget).toBeTruthy()
        fireEvent.drop(dropTarget, {
            dataTransfer: {
                types: ["Files"],
                files: [pngFile],
            },
        })
        expect(onImageFileSelect).toHaveBeenCalledTimes(1)
        expect(onImageFileSelect).toHaveBeenCalledWith(pngFile)
    })

    it("contains zero Ctrl+V / Cmd+V / shortcut / drag-drop copy in UI and i18n dictionaries (AC-8)", async () => {
        const forbiddenPattern = /ctrl\s*\+\s*v|cmd\s*\+\s*v|⌘\s*v|快捷鍵|shortcut|拖放|貼上圖片|drop\s+image|paste\s+image/i

        for (const dict of [chatTranslations.en, chatTranslations.zh]) {
            for (const value of Object.values(dict)) {
                expect(value).not.toMatch(forbiddenPattern)
            }
        }

        const { container } = render(<ComposerHarness />)
        fireEvent.click(screen.getByRole("button", { name: "更多工具" }))
        await screen.findByText("上傳圖片")

        expect(document.body.textContent || "").not.toMatch(forbiddenPattern)
        const elementsWithTitleOrAria = Array.from(container.querySelectorAll("[aria-label], [title], [placeholder]"))
        for (const el of elementsWithTitleOrAria) {
            expect(el.getAttribute("aria-label") || "").not.toMatch(forbiddenPattern)
            expect(el.getAttribute("title") || "").not.toMatch(forbiddenPattern)
            expect(el.getAttribute("placeholder") || "").not.toMatch(forbiddenPattern)
        }
    })

    it("ChatWidget integration: uploading valid image auto-disables Deep Research, invalid SVG keeps Deep Research on, and photo + keyword routes to /api/chat", async () => {
        const pngFile = new File([new Uint8Array([137, 80, 78, 71])], "menu.png", { type: "image/png" })
        const svgFile = new File(["<svg/>"], "evil.svg", { type: "image/svg+xml" })
        mockCompressImage.mockResolvedValue(pngFile)

        const fetchUrls: string[] = []
        const fetchBodies: string[] = []
        global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
            fetchUrls.push(String(input))
            fetchBodies.push(String(init?.body ?? ""))
            return new Response(
                JSON.stringify({
                    response: "This ramen menu costs 1200 JPY.",
                    raw_parts: [{ text: "This ramen menu costs 1200 JPY." }],
                }),
                { status: 200, headers: { "Content-Type": "application/json" } }
            )
        }) as unknown as typeof fetch

        const { container } = render(
            <LanguageProvider>
                <ChatWidget />
            </LanguageProvider>
        )
        fireEvent.click(screen.getByRole("button", { name: /Ryan AI/i }))

        // Enable Deep Research
        fireEvent.click(screen.getByRole("button", { name: "更多工具" }))
        fireEvent.click(await screen.findByText("深度研究"))
        expect(await screen.findByRole("button", { name: "關閉深度研究模式" })).toBeInTheDocument()

        const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement

        // Invalid SVG upload must NOT turn off Deep Research
        fireEvent.change(fileInput, { target: { files: [svgFile] } })
        expect(mockToastError).toHaveBeenCalledTimes(1)
        expect(screen.getByRole("button", { name: "關閉深度研究模式" })).toBeInTheDocument()

        // Valid PNG upload auto-disables Deep Research + toasts info
        fireEvent.change(fileInput, { target: { files: [pngFile] } })
        await waitFor(() => {
            expect(container.querySelector('img[alt="Selected"]')).toBeTruthy()
        })
        await waitFor(() => {
            expect(screen.queryByRole("button", { name: "關閉深度研究模式" })).not.toBeInTheDocument()
        })
        expect(mockToastInfo).toHaveBeenCalledWith(
            chatTranslations.zh.ai_composer_deep_research_auto_off,
            expect.objectContaining({ position: "top-center" })
        )

        // Safety Net: Typing keyword "深度研究" while photo is attached MUST still route to /api/chat with image, NOT /api/agents/research
        const textarea = screen.getByRole("textbox")
        fireEvent.change(textarea, { target: { value: "幫我深度研究這張菜單" } })
        fireEvent.click(screen.getByRole("button", { name: "發送訊息" }))

        await waitFor(() => {
            expect(screen.getByText(/This ramen menu costs 1200 JPY\./)).toBeInTheDocument()
        })
        expect(fetchUrls.some((u) => u.endsWith("/api/agents/research"))).toBe(false)
        expect(fetchUrls.some((u) => u.endsWith("/api/chat"))).toBe(true)
        const chatBody = JSON.parse(fetchBodies[0])
        expect(chatBody.image).toMatch(/^data:image\/png;base64,/)
    })

    it("ChatWidget integration: Stop button cleanly aborts in-flight image /api/chat without false connection error, and cancels active Deep Research polling", async () => {
        const pngFile = new File([new Uint8Array([137, 80, 78, 71])], "receipt.png", { type: "image/png" })
        mockCompressImage.mockResolvedValue(pngFile)

        let capturedSignal: AbortSignal | undefined
        global.fetch = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
            capturedSignal = init?.signal ?? undefined
            return new Promise<Response>((_resolve, reject) => {
                init?.signal?.addEventListener("abort", () => {
                    const abortErr = new Error("Aborted")
                    abortErr.name = "AbortError"
                    reject(abortErr)
                })
            })
        }) as unknown as typeof fetch

        const { container, unmount } = render(
            <LanguageProvider>
                <ChatWidget />
            </LanguageProvider>
        )
        fireEvent.click(screen.getByRole("button", { name: /Ryan AI/i }))

        const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement
        fireEvent.change(fileInput, { target: { files: [pngFile] } })
        await waitFor(() => {
            expect(container.querySelector('img[alt="Selected"]')).toBeTruthy()
        })

        fireEvent.click(screen.getByRole("button", { name: "發送訊息" }))
        const stopBtn = await screen.findByRole("button", { name: "停止生成" })
        fireEvent.click(stopBtn)

        expect(capturedSignal?.aborted).toBe(true)
        await waitFor(() => {
            expect(screen.getByRole("button", { name: "發送訊息" })).toBeInTheDocument()
        })
        expect(screen.queryByText(/連線中斷|Connection lost/)).not.toBeInTheDocument()
        unmount()

        // Second check: Stop button aborts in-flight poll, sends /cancel to save BYOK quota, clears polling interval, and marks card cancelled
        vi.useFakeTimers({ shouldAdvanceTime: true })
        let pollHits = 0
        let cancelHits = 0
        let inFlightPollSignal: AbortSignal | undefined
        let resolveStalePoll: ((res: Response) => void) | undefined
        global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
            const url = String(input)
            if (url.endsWith("/api/agents/research/stream")) {
                return new Response(null, { status: 404 })
            }
            if (url.endsWith("/api/agents/research")) {
                return new Response(
                    JSON.stringify({ interaction_id: "res_stop_1", engine: "fallback" }),
                    { status: 200, headers: { "Content-Type": "application/json" } }
                )
            }
            if (url.endsWith("/api/agents/interactions/res_stop_1/cancel")) {
                cancelHits += 1
                return new Response(JSON.stringify({ status: "cancelled" }), {
                    status: 200,
                    headers: { "Content-Type": "application/json" },
                })
            }
            pollHits += 1
            inFlightPollSignal = init?.signal ?? undefined
            // Hold the first poll in-flight so we can click Stop mid-request
            return new Promise<Response>((resolve) => {
                resolveStalePoll = resolve
            })
        }) as unknown as typeof fetch

        render(
            <LanguageProvider>
                <ChatWidget />
            </LanguageProvider>
        )
        fireEvent.click(screen.getByRole("button", { name: /Ryan AI/i }))
        const textarea = screen.getByRole("textbox")
        fireEvent.change(textarea, { target: { value: "/research Kyoto autumn passes" } })
        fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false })

        await act(async () => {
            await vi.advanceTimersByTimeAsync(2200)
        })
        expect(pollHits).toBe(1)

        fireEvent.click(screen.getByRole("button", { name: "停止生成" }))
        expect(inFlightPollSignal?.aborted).toBe(true)
        expect(cancelHits).toBe(1)

        // Even if the in-flight poll somehow resolves late with "completed", it MUST NOT overwrite the cancelled card
        await act(async () => {
            resolveStalePoll?.(
                new Response(
                    JSON.stringify({ status: "completed", output_text: "Stale completed overwrite" }),
                    { status: 200, headers: { "Content-Type": "application/json" } }
                )
            )
            await vi.advanceTimersByTimeAsync(6000)
        })
        expect(pollHits).toBe(1)
        expect(screen.getByText(/任務已由使用者取消|Task cancelled by user/)).toBeInTheDocument()
        expect(screen.queryByText(/Stale completed overwrite/)).not.toBeInTheDocument()
    })

    it("ChatWidget safety net: camera input clears value & compresses, and stop-then-resend prevents Request A unwind from clobbering Request B loading state", async () => {
        const jpgFile = new File([new Uint8Array([0xff, 0xd8, 0xff])], "street.jpg", { type: "image/jpeg" })
        mockCompressImage.mockResolvedValueOnce(jpgFile)

        let finishRequestA!: () => void
        let finishRequestB!: () => void
        mockStreamChat
            .mockImplementationOnce(async () => {
                await new Promise<void>((resolve) => {
                    finishRequestA = resolve
                })
            })
            .mockImplementationOnce(async (_url, _msg, _hist, _key, handlers) => {
                await new Promise<void>((resolve) => {
                    finishRequestB = () => {
                        handlers.onText?.("Fresh Request B reply")
                        handlers.onDone?.({
                            model_used: "gemini-3.5-flash-lite",
                            raw_parts: [{ text: "Fresh Request B reply" }],
                            sources: [],
                        })
                        resolve()
                    }
                })
            })

        const { container } = render(
            <LanguageProvider>
                <ChatWidget />
            </LanguageProvider>
        )
        fireEvent.click(screen.getByRole("button", { name: /Ryan AI/i }))

        // Camera input (2nd input[type="file"]) reuses the exact compression pipeline & clears value
        const fileInputs = Array.from(container.querySelectorAll('input[type="file"]')) as HTMLInputElement[]
        fireEvent.change(fileInputs[1], { target: { files: [jpgFile] } })
        await waitFor(() => {
            expect(mockCompressImage).toHaveBeenCalledWith(jpgFile, "ai_input")
            expect(container.querySelector('img[alt="Selected"]')).toBeTruthy()
        })
        expect(fileInputs[1].value).toBe("")
        // Remove image before text streaming race test
        fireEvent.click(screen.getByRole("button", { name: "移除圖片" }))
        expect(container.querySelector('img[alt="Selected"]')).toBeNull()

        const textarea = screen.getByRole("textbox")
        // Send Request A
        fireEvent.change(textarea, { target: { value: "Request A" } })
        fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false })
        const stopBtnA = await screen.findByRole("button", { name: "停止生成" })

        // Stop Request A, immediately send Request B
        fireEvent.click(stopBtnA)
        fireEvent.change(textarea, { target: { value: "Request B" } })
        fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false })
        expect(await screen.findByRole("button", { name: "停止生成" })).toBeInTheDocument()

        // Request A finishes unwinding AFTER Request B started — Request B MUST stay in loading state (Stop button visible)
        await act(async () => {
            finishRequestA()
            await Promise.resolve()
        })
        expect(screen.getByRole("button", { name: "停止生成" })).toBeInTheDocument()

        // Now complete Request B cleanly
        await act(async () => {
            finishRequestB()
            await Promise.resolve()
        })
        await waitFor(() => {
            expect(screen.getByText("Fresh Request B reply")).toBeInTheDocument()
            expect(screen.getByRole("button", { name: "發送訊息" })).toBeInTheDocument()
        })
    })

    it("ChatWidget safety net: mobile auto-dock closes open + Popover without leaving orphaned Portal, hides floating toggle while open, and keeps Popover closed on resume", async () => {
        const originalInnerWidth = window.innerWidth
        Object.defineProperty(window, "innerWidth", { value: 375, configurable: true, writable: true })
        try {
            const { container } = render(
                <LanguageProvider>
                    <ChatWidget />
                </LanguageProvider>
            )
            const toggleWrapper = container.querySelector("#tour-ai-bot")?.parentElement as HTMLElement
            expect(toggleWrapper).toBeTruthy()
            expect(toggleWrapper.className).not.toContain("hidden")

            fireEvent.click(screen.getByRole("button", { name: /Ryan AI/i }))
            // While fullscreen chat is open & undocked, floating toggle button MUST be hidden so it never overlaps the Two-Zone Composer
            expect(toggleWrapper.className).toContain("hidden")

            // Open + Popover menu
            fireEvent.click(screen.getByRole("button", { name: "更多工具" }))
            expect(await screen.findByText("上傳圖片")).toBeInTheDocument()

            // Trigger mobile map fly-to auto-dock -> Popover MUST close immediately
            await act(async () => {
                window.dispatchEvent(new Event("tabidachi:map-flyto"))
            })
            await waitFor(() => {
                expect(screen.queryByText("上傳圖片")).not.toBeInTheDocument()
            })

            // Resume chat from dock -> Popover MUST stay closed (not magically reopen)
            fireEvent.click(screen.getByText(/展開對話|Open/))
            expect(screen.queryByText("上傳圖片")).not.toBeInTheDocument()
        } finally {
            Object.defineProperty(window, "innerWidth", { value: originalInnerWidth, configurable: true, writable: true })
        }
    })

    it("ChatWidget safety net: Deep Research start failure does NOT fall through into streamChat, and DeepResearchCard cancel syncs Composer loading state", async () => {
        // Case 1: POST /api/agents/research fails -> toast error, Composer returns to Send, streamChat NOT called
        global.fetch = vi.fn(async () =>
            new Response(JSON.stringify({ detail: "Sandbox unavailable" }), {
                status: 503,
                headers: { "Content-Type": "application/json" },
            })
        ) as unknown as typeof fetch

        const view1 = render(
            <LanguageProvider>
                <ChatWidget />
            </LanguageProvider>
        )
        fireEvent.click(screen.getByRole("button", { name: /Ryan AI/i }))
        const textarea1 = screen.getByRole("textbox")
        fireEvent.change(textarea1, { target: { value: "/research Tokyo rail pass" } })
        fireEvent.keyDown(textarea1, { key: "Enter", shiftKey: false })

        await waitFor(() => {
            expect(mockToastError).toHaveBeenCalledWith("Sandbox unavailable")
            expect(screen.getByRole("button", { name: "發送訊息" })).toBeInTheDocument()
        })
        expect(mockStreamChat).not.toHaveBeenCalled()
        view1.unmount()

        // Case 2: Clicking DeepResearchCard's own Cancel button immediately resets Composer Stop -> Send and halts polling
        vi.useFakeTimers({ shouldAdvanceTime: true })
        let pollHits = 0
        let cardCancelHits = 0
        global.fetch = vi.fn(async (input: RequestInfo | URL) => {
            const url = String(input)
            if (url.endsWith("/api/agents/research/stream")) {
                return new Response(null, { status: 404 })
            }
            if (url.endsWith("/api/agents/research")) {
                return new Response(
                    JSON.stringify({ interaction_id: "res_card_cancel_1", engine: "fallback" }),
                    { status: 200, headers: { "Content-Type": "application/json" } }
                )
            }
            if (url.endsWith("/api/agents/interactions/res_card_cancel_1/cancel")) {
                cardCancelHits += 1
                return new Response(JSON.stringify({ status: "cancelled" }), {
                    status: 200,
                    headers: { "Content-Type": "application/json" },
                })
            }
            pollHits += 1
            return new Response(JSON.stringify({ status: "running" }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
            })
        }) as unknown as typeof fetch

        render(
            <LanguageProvider>
                <ChatWidget />
            </LanguageProvider>
        )
        fireEvent.click(screen.getByRole("button", { name: /Ryan AI/i }))
        const textarea2 = screen.getByRole("textbox")
        fireEvent.change(textarea2, { target: { value: "/research Osaka food crawl" } })
        fireEvent.keyDown(textarea2, { key: "Enter", shiftKey: false })

        const cardCancelBtn = await screen.findByRole("button", { name: /取消|Cancel/ })
        expect(screen.getByRole("button", { name: "停止生成" })).toBeInTheDocument()

        fireEvent.click(cardCancelBtn)
        await waitFor(() => {
            expect(screen.getByRole("button", { name: "發送訊息" })).toBeInTheDocument()
            expect(screen.getByText(/任務已由使用者取消|Task cancelled by user/)).toBeInTheDocument()
        })
        expect(cardCancelHits).toBe(1)

        await act(async () => {
            await vi.advanceTimersByTimeAsync(5000)
        })
        expect(pollHits).toBe(0)
    })

    it("ChatWidget safety net: removing image mid-replacement unlocks compression immediately and stale Gen 1 finally cannot unlock Gen 2 or corrupt late SSE", async () => {
        const img1 = new File([new Uint8Array([137, 80, 78, 71])], "first.png", { type: "image/png" })
        const img2 = new File([new Uint8Array([137, 80, 78, 71])], "second.png", { type: "image/png" })
        const img3 = new File([new Uint8Array([137, 80, 78, 71])], "third.png", { type: "image/png" })

        let resolveGen2!: (f: File) => void
        let resolveGen3!: (f: File) => void
        mockCompressImage
            .mockResolvedValueOnce(img1)
            .mockImplementationOnce(() => new Promise<File>((resolve) => { resolveGen2 = resolve }))
            .mockImplementationOnce(() => new Promise<File>((resolve) => { resolveGen3 = resolve }))

        const { container } = render(
            <LanguageProvider>
                <ChatWidget />
            </LanguageProvider>
        )
        fireEvent.click(screen.getByRole("button", { name: /Ryan AI/i }))
        const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement

        // Attach Image 1
        fireEvent.change(fileInput, { target: { files: [img1] } })
        await waitFor(() => {
            expect(container.querySelector('img[alt="Selected"]')).toBeTruthy()
        })

        // Start compressing replacement Image 2 (pending)
        fireEvent.change(fileInput, { target: { files: [img2] } })
        expect(await screen.findByText("正在最佳化圖片...")).toBeInTheDocument()

        // Click Remove (×) while Image 2 is compressing -> MUST immediately unlock Composer
        fireEvent.click(screen.getByRole("button", { name: "移除圖片" }))
        expect(screen.queryByText("正在最佳化圖片...")).not.toBeInTheDocument()
        expect(container.querySelector('img[alt="Selected"]')).toBeNull()

        // Start compressing Image 3 (active Gen 3)
        fireEvent.change(fileInput, { target: { files: [img3] } })
        expect(await screen.findByText("正在最佳化圖片...")).toBeInTheDocument()

        // Abandoned Image 2 now finishes -> MUST NOT render ghost thumbnail AND MUST NOT unlock active Image 3 compression
        await act(async () => {
            resolveGen2(img2)
            await Promise.resolve()
        })
        expect(screen.getByText("正在最佳化圖片...")).toBeInTheDocument()
        expect(container.querySelector('img[alt="Selected"]')).toBeNull()

        // Complete Image 3 cleanly
        await act(async () => {
            resolveGen3(img3)
        })
        await waitFor(() => {
            expect(container.querySelector('img[alt="Selected"]')).toBeTruthy()
            expect(screen.queryByText("正在最佳化圖片...")).not.toBeInTheDocument()
        })
    })

    it("ChatWidget safety net: late SSE callbacks from aborted Request A cannot corrupt Request B", async () => {
        let emitLateRequestAText!: () => void
        let finishRequestB!: () => void
        mockStreamChat
            .mockImplementationOnce(async (_url, _msg, _hist, _key, handlers) => {
                handlers.onStart?.()
                handlers.onText?.("Partial A")
                await new Promise<void>((resolve) => {
                    emitLateRequestAText = () => {
                        handlers.onText?.(" CORRUPTED_BY_A")
                        handlers.onDone?.({
                            model_used: "stale-a",
                            raw_parts: [{ text: "Partial A CORRUPTED_BY_A" }],
                            sources: [],
                        })
                        resolve()
                    }
                })
            })
            .mockImplementationOnce(async (_url, _msg, _hist, _key, handlers) => {
                handlers.onStart?.()
                handlers.onText?.("Clean B")
                await new Promise<void>((resolve) => {
                    finishRequestB = () => {
                        handlers.onDone?.({
                            model_used: "gemini-3.5-flash-lite",
                            raw_parts: [{ text: "Clean B" }],
                            sources: [],
                        })
                        resolve()
                    }
                })
            })

        render(
            <LanguageProvider>
                <ChatWidget />
            </LanguageProvider>
        )
        fireEvent.click(screen.getByRole("button", { name: /Ryan AI/i }))
        const textarea = screen.getByRole("textbox")

        fireEvent.change(textarea, { target: { value: "Msg A" } })
        fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false })
        await screen.findByText("Partial A")

        fireEvent.click(screen.getByRole("button", { name: "停止生成" }))

        fireEvent.change(textarea, { target: { value: "Msg B" } })
        fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false })
        await screen.findByText("Clean B")

        // Late callback from aborted Request A fires while Request B is streaming
        await act(async () => {
            emitLateRequestAText()
            await Promise.resolve()
        })
        expect(screen.queryByText(/CORRUPTED_BY_A/)).not.toBeInTheDocument()

        await act(async () => {
            finishRequestB()
            await Promise.resolve()
        })
        expect(screen.getByText("Clean B")).toBeInTheDocument()
    })
})
