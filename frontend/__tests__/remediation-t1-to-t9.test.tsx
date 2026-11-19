import fs from "node:fs"
import path from "node:path"
import vm from "node:vm"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen, act, fireEvent, waitFor } from "@testing-library/react"
import React from "react"
import { LanguageProvider } from "@/lib/LanguageContext"
import { ThemeProvider } from "@/lib/ThemeContext"
import { toast } from "sonner"
import { consumeTripStream, itemsApi, API_HOST } from "@/lib/api"
import { ItineraryItemSchema } from "@/lib/schemas"
import { NotificationBell } from "@/components/notifications/notification-bell"
import { CapsuleUnveilingCeremony } from "@/components/itinerary/CapsuleUnveilingCeremony"
import POIDetailDrawer from "@/components/POIDetailDrawer"
import { TimelineCard } from "@/components/timeline-card"
import { useTripRealtime } from "@/lib/hooks/useTripRealtime"
import { SWRConfig } from "swr"

// Mock next/navigation
vi.mock("next/navigation", () => ({
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
    usePathname: () => "/",
    useSearchParams: () => new URLSearchParams(),
}))

// Mock next/image cleanly
vi.mock("next/image", () => ({
    default: (props: Record<string, unknown>) => {
        // eslint-disable-next-line @next/next/no-img-element
        return <img src={String(props.src || "")} alt={String(props.alt || "")} onError={props.onError as React.ReactEventHandler<HTMLImageElement>} />
    },
}))

// Mock supabase client cleanly
const broadcastListeners: Record<string, Array<() => void>> = {}
const collabHandlers: Record<string, Array<(arg: { payload: Record<string, unknown> }) => void>> = {}
const channelSubscriptionTypes: string[] = []
const mockRemoveChannel = vi.fn()
vi.mock("@/lib/supabase", () => ({
    getSupabaseClient: () => ({
        channel: (topic: string) => {
            const ch = {
                on: (type: string, filter: { event?: string }, cb: (arg?: unknown) => void) => {
                    channelSubscriptionTypes.push(type)
                    if (type === "broadcast" && filter?.event === "collab:event") {
                        collabHandlers[topic] = collabHandlers[topic] || []
                        collabHandlers[topic].push(cb as (arg: { payload: Record<string, unknown> }) => void)
                    } else {
                        broadcastListeners[topic] = broadcastListeners[topic] || []
                        broadcastListeners[topic].push(cb as () => void)
                    }
                    return ch
                },
                subscribe: (cb?: (status: string) => void) => {
                    if (typeof cb === "function") cb("SUBSCRIBED")
                    return ch
                },
                send: vi.fn().mockResolvedValue("ok"),
            }
            return ch
        },
        removeChannel: mockRemoveChannel,
    }),
}))

function loadEdgeShieldWorker() {
    const repoRoot = path.resolve(__dirname, "..", "..")
    const workerPath = path.join(repoRoot, "cloudflare", "edge-shield", "worker.js")
    const rawCode = fs.readFileSync(workerPath, "utf-8")
    const transformed = rawCode.replace(/export\s+default\s+\{/, "module.exports = {")
    const mod = { exports: {} as { fetch: (req: Request, env: Record<string, unknown>, ctx: { waitUntil: (p: Promise<unknown>) => void }) => Promise<Response> } }
    const cacheStore = new Map<string, Response>()
    const sandbox = {
        module: mod,
        exports: mod.exports,
        URL,
        Request,
        Response,
        Headers,
        fetch: vi.fn(),
        caches: {
            default: {
                match: async (k: string) => {
                    const hit = cacheStore.get(k)
                    return hit ? hit.clone() : undefined
                },
                put: async (k: string, resp: Response) => {
                    cacheStore.set(k, resp.clone())
                },
            },
        },
        crypto: globalThis.crypto,
        TextEncoder,
        TextDecoder,
        console,
        atob: globalThis.atob,
        btoa: globalThis.btoa,
    }
    vm.runInNewContext(transformed, sandbox, { filename: workerPath })
    return { worker: mod.exports, cacheStore, mockFetch: sandbox.fetch }
}

describe("T1–T9 Remediation Verification Suite", () => {
    const originalFetch = global.fetch

    beforeEach(() => {
        localStorage.clear()
        Object.keys(broadcastListeners).forEach((k) => delete broadcastListeners[k])
        Object.keys(collabHandlers).forEach((k) => delete collabHandlers[k])
        channelSubscriptionTypes.length = 0
        vi.clearAllMocks()
    })

    afterEach(() => {
        global.fetch = originalFetch
    })

    it("T1: NotificationBell skips unauthenticated/tbj_rec_ cold-start requests and loads + rolls back via FastAPI", async () => {
        const fetchMock = vi.fn()
        global.fetch = fetchMock as unknown as typeof fetch

        // 1. Unauthenticated cold start -> 0 network requests
        const { unmount } = render(
            <ThemeProvider>
                <LanguageProvider>
                    <NotificationBell />
                </LanguageProvider>
            </ThemeProvider>
        )
        await act(async () => {
            await new Promise((r) => setTimeout(r, 20))
        })
        expect(fetchMock).not.toHaveBeenCalled()
        unmount()

        // 2. Offline tbj_rec_ placeholder -> STILL 0 network requests (prevents spurious 401 modal!)
        localStorage.setItem("user_uuid", "tbj_rec_12345678_1234567890abcdef1234567890abcdef")
        localStorage.setItem("user_nickname", "OfflineUser")
        const { unmount: unmountRec } = render(
            <ThemeProvider>
                <LanguageProvider>
                    <NotificationBell />
                </LanguageProvider>
            </ThemeProvider>
        )
        await act(async () => {
            await new Promise((r) => setTimeout(r, 20))
        })
        expect(fetchMock).not.toHaveBeenCalled()
        unmountRec()

        // 3. Logged-in user -> fetches via /api/notifications, listens to Broadcast, rolls back failed markRead
        localStorage.setItem("user_uuid", "11111111-1111-4111-8111-111111111111")
        localStorage.setItem("user_nickname", "Ryan")
        localStorage.setItem("tabiji_session_token", "fake.jwt.token")

        fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
            const url = String(input)
            if (url.includes("/api/notifications") && (!init?.method || init.method === "GET")) {
                return new Response(
                    JSON.stringify({
                        items: [{
                            id: "22222222-2222-4222-8222-222222222222",
                            user_id: "11111111-1111-4111-8111-111111111111",
                            type: "trip_invite",
                            title: "Trip Ready",
                            body: "Kyoto awaits",
                            link: null,
                            metadata: {},
                            is_read: false,
                            created_at: new Date().toISOString(),
                        }],
                        unread_count: 1,
                    }),
                    { status: 200, headers: { "Content-Type": "application/json" } }
                )
            }
            if (url.includes("/read") && init?.method === "PATCH") {
                return new Response(JSON.stringify({ error: "db down" }), { status: 500 })
            }
            return new Response("{}", { status: 200 })
        })

        render(
            <ThemeProvider>
                <LanguageProvider>
                    <NotificationBell />
                </LanguageProvider>
            </ThemeProvider>
        )

        await waitFor(() => {
            expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/notifications"), undefined)
        })
        expect(broadcastListeners["user-notif:11111111-1111-4111-8111-111111111111"]?.length).toBeGreaterThanOrEqual(1)
        expect(broadcastListeners["user-notif:broadcast"]?.length).toBeGreaterThanOrEqual(1)

        // Open bell and click unread notification -> failed PATCH should roll unread badge back to 1 and show error toast
        const toastErrorSpy = vi.spyOn(toast, "error").mockImplementation(() => "")
        const bellBtn = screen.getByLabelText(/通知|Notifications/i)
        fireEvent.click(bellBtn)
        await waitFor(() => {
            expect(screen.getByText("Kyoto awaits")).toBeTruthy()
        })
        fireEvent.click(screen.getByText("Kyoto awaits"))
        await waitFor(() => {
            expect(screen.getByText("1")).toBeTruthy()
            expect(toastErrorSpy).toHaveBeenCalled()
        })
        toastErrorSpy.mockRestore()
    })

    it("T3: Edge Shield geocode cache bypasses on Gemini headers and isolates v=2 key without zoom noise", async () => {
        const { worker, cacheStore, mockFetch } = loadEdgeShieldWorker()
        mockFetch.mockImplementation(async () =>
            new Response(JSON.stringify({ results: [{ name: "Tokyo", lat: 35.68, lng: 139.76 }] }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
            })
        )
        const waitUntil = vi.fn()
        const ctx = { waitUntil }
        const env = {}

        // 1. Gemini key bypasses edge cache cleanly
        const bypassReq = new Request("https://www.tabijiapp.com/api/geocode/search", {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-Gemini-API-Key": "AIzaSyTestBypass123" },
            body: JSON.stringify({ query: "ramen", locale: "zh", region: "Shibuya", lat: 35.659, lng: 139.701 }),
        })
        const bypassRes = await worker.fetch(bypassReq, env, ctx)
        expect(bypassRes.headers.get("X-Edge-Cache")).toBe("BYPASS")
        expect(cacheStore.size).toBe(0)

        // 2. Normal request caches with v=2 key; noisy zoom jitter still HITS same cache key!
        const reqZoom11 = new Request("https://www.tabijiapp.com/api/geocode/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: "Senso-ji", locale: "en", region: "Asakusa", lat: 35.7148, lng: 139.7967, zoom: 11.2, limit: 5, tripTitle: "Tokyo Spring" }),
        })
        const res1 = await worker.fetch(reqZoom11, env, ctx)
        expect(res1.headers.get("X-Edge-Cache")).toBe("MISS")
        await Promise.all(waitUntil.mock.calls.map((c) => c[0]))
        expect(cacheStore.size).toBe(1)

        const keys = Array.from(cacheStore.keys())
        expect(keys[0]).toContain("v=2")
        expect(keys[0]).toContain("locale=en")
        expect(keys[0]).toContain("region=asakusa")
        expect(keys[0]).not.toContain("zoom=")

        // Same payload with different zoom -> HIT!
        const reqZoom15 = new Request("https://www.tabijiapp.com/api/geocode/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: "Senso-ji", locale: "en", region: "Asakusa", lat: 35.7148, lng: 139.7967, zoom: 15.8, limit: 5, tripTitle: "Tokyo Spring" }),
        })
        const res2 = await worker.fetch(reqZoom15, env, ctx)
        expect(res2.headers.get("X-Edge-Cache")).toBe("HIT")

        // Distinct locale -> different key (MISS, zero cross-locale poisoning!)
        const reqZh = new Request("https://www.tabijiapp.com/api/geocode/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: "Senso-ji", locale: "zh", region: "Asakusa", lat: 35.7148, lng: 139.7967, zoom: 15.8, limit: 5, tripTitle: "Tokyo Spring" }),
        })
        const res3 = await worker.fetch(reqZh, env, ctx)
        expect(res3.headers.get("X-Edge-Cache")).toBe("MISS")
        await Promise.all(waitUntil.mock.calls.map((c) => c[0]))
        expect(cacheStore.size).toBe(2)
    })

    it("T5: CapsuleUnveilingCeremony resets activeDay when reopened or initialDay changes and preserves Day 0", async () => {
        const entries = [
            { id: "c0", trip_id: "t1", day_number: 0, author_id: "u1", author_name: "Ryan", mood_emoji: "🎉", content: "Finale memory", is_sealed: false, created_at: "2026-01-01" },
            { id: "c2", trip_id: "t1", day_number: 2, author_id: "u1", author_name: "Ryan", mood_emoji: "🍜", content: "Day 2 ramen", is_sealed: false, created_at: "2026-01-01" },
        ]
        const { rerender } = render(
            <LanguageProvider>
                <CapsuleUnveilingCeremony
                    isOpen={true}
                    onClose={vi.fn()}
                    entries={entries}
                    totalDays={3}
                    tripTitle="Tokyo"
                    initialDay={0}
                />
            </LanguageProvider>
        )
        expect(screen.getByText("Finale memory")).toBeTruthy()

        // Close and reopen with initialDay=2 -> activeDay must reset to 2!
        rerender(
            <LanguageProvider>
                <CapsuleUnveilingCeremony
                    isOpen={false}
                    onClose={vi.fn()}
                    entries={entries}
                    totalDays={3}
                    tripTitle="Tokyo"
                    initialDay={0}
                />
            </LanguageProvider>
        )
        rerender(
            <LanguageProvider>
                <CapsuleUnveilingCeremony
                    isOpen={true}
                    onClose={vi.fn()}
                    entries={entries}
                    totalDays={3}
                    tripTitle="Tokyo"
                    initialDay={2}
                />
            </LanguageProvider>
        )
        expect(screen.getByText("Day 2 ramen")).toBeTruthy()
    })

    it("T6: itemsApi.create sends website_link and address, and ItineraryItemSchema accepts address", async () => {
        const fetchMock = vi.fn().mockResolvedValueOnce(
            new Response(JSON.stringify({ status: "success", data: [{ id: "i-1" }] }), { status: 200 })
        )
        global.fetch = fetchMock as unknown as typeof fetch

        await itemsApi.create({
            trip_id: "t-1",
            user_id: "u-1",
            day: 1,
            time: "10:00",
            place: "Tokyo Tower",
            address: "4-2-8 Shibakoen, Minato City, Tokyo",
            website_link: "https://www.tokyotower.co.jp/",
        })

        const reqInit = fetchMock.mock.calls[0][1] as RequestInit
        const sent = JSON.parse(String(reqInit.body))
        expect(sent.address).toBe("4-2-8 Shibakoen, Minato City, Tokyo")
        expect(sent.website_link).toBe("https://www.tokyotower.co.jp/")

        const parsed = ItineraryItemSchema.safeParse({
            id: "i-1",
            itinerary_id: "t-1",
            day_number: 1,
            place_name: "Tokyo Tower",
            address: "4-2-8 Shibakoen, Minato City, Tokyo",
        })
        expect(parsed.success).toBe(true)
        if (parsed.success) {
            expect(parsed.data.address).toBe("4-2-8 Shibakoen, Minato City, Tokyo")
        }
    })

    it("T7: POIDetailDrawer displays free Wiki notice when ai_key_missing=true and suppresses rating=0 literal", async () => {
        global.fetch = vi.fn().mockResolvedValueOnce(
            new Response(
                JSON.stringify({
                    summary: "Famous historic shrine in Kyoto.",
                    must_try: [],
                    rating: 0,
                    status: "PARTIAL_SUCCESS",
                    warnings: ["NO_API_KEY"],
                    cultural_desc: "Built in 711 AD.",
                    ai_key_missing: true,
                }),
                { status: 200, headers: { "Content-Type": "application/json" } }
            )
        ) as unknown as typeof fetch

        render(
            <LanguageProvider>
                <POIDetailDrawer
                    isOpen={true}
                    onClose={vi.fn()}
                    poi={{ name: "Fushimi Inari", type: "shrine", lat: 34.9671, lng: 135.7727 }}
                />
            </LanguageProvider>
        )

        const analyzeBtn = await screen.findByRole("button", { name: /Explore|探索/i })
        fireEvent.click(analyzeBtn)

        await waitFor(() => {
            expect(screen.getByText(/Wikipedia Reference Mode|免費百科資料模式/i)).toBeTruthy()
        })
        expect(screen.queryByText("0")).toBeNull()
        expect(screen.queryByText(/⭐ 0/)).toBeNull()
    })

    it("T9: consumeTripStream parses : keep-alive comment preceding event: complete without dropping event", async () => {
        const encoder = new TextEncoder()
        const stream = new ReadableStream<Uint8Array>({
            start(controller) {
                controller.enqueue(encoder.encode(': keep-alive\nevent: progress\ndata: {"percent":22,"stage":"THINKING","message":"Planning"}\n\n'))
                controller.enqueue(encoder.encode(': keep-alive\nevent: complete\ndata: {"title":"Osaka Food Tour","items":[]}'))
                controller.close()
            },
        })
        const res = new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } })
        const events: number[] = []
        const result = await consumeTripStream(res, (p) => events.push(p.percent))
        expect(events).toEqual([22])
        expect(result).toEqual({ title: "Osaka Food Tour", items: [] })
    })

    it("T9: share/[shareCode]/page.tsx does not lock force-cache", () => {
        const sharePagePath = path.resolve(__dirname, "..", "app", "share", "[shareCode]", "page.tsx")
        const src = fs.readFileSync(sharePagePath, "utf-8")
        expect(sharePagePath).toBeTruthy()
        expect(src).not.toContain("force-cache")
        expect(src).toContain("revalidate: 60")
        expect(API_HOST).toBeDefined()
    })

    it("T2: useTripRealtime registers only broadcast (zero postgres_changes) and reacts to item:mutate", () => {
        function TestRealtimeProbe() {
            useTripRealtime("trip-rt-1", "u1")
            return <div>rt-ready</div>
        }
        render(
            <SWRConfig value={{ provider: () => new Map() }}>
                <TestRealtimeProbe />
            </SWRConfig>
        )
        expect(channelSubscriptionTypes).toContain("broadcast")
        expect(channelSubscriptionTypes).not.toContain("postgres_changes")
        expect(collabHandlers["realtime-trip-trip-rt-1"]?.length).toBe(1)

        const eventSpy = vi.fn()
        window.addEventListener("tabiji:collab-event", eventSpy)
        try {
            collabHandlers["realtime-trip-trip-rt-1"][0]({
                payload: { event: "item:mutate", senderSessionId: "other-session-123" },
            })
            collabHandlers["realtime-trip-trip-rt-1"][0]({
                payload: { event: "info:update", senderSessionId: "other-session-123" },
            })
            expect(eventSpy).toHaveBeenCalledTimes(2)
        } finally {
            window.removeEventListener("tabiji:collab-event", eventSpy)
        }

        const removeSrc = fs.readFileSync(path.resolve(__dirname, "..", "components", "chat", "RemoveItemPreviewCard.tsx"), "utf-8")
        const expenseSrc = fs.readFileSync(path.resolve(__dirname, "..", "components", "chat", "ExpensePreviewCard.tsx"), "utf-8")
        expect(removeSrc).toContain('broadcastTripEvent(activeTripId, "item:mutate"')
        expect(expenseSrc).toContain('broadcastTripEvent(activeTripId, "expense:update"')
    })

    it("T4: day-map and FullscreenMapModal preserve L1 localMapped results across debounce and L2 error fallback", () => {
        const dayMapSrc = fs.readFileSync(path.resolve(__dirname, "..", "components", "day-map.tsx"), "utf-8")
        const modalSrc = fs.readFileSync(path.resolve(__dirname, "..", "components", "FullscreenMapModal.tsx"), "utf-8")
        expect(dayMapSrc).toContain("setResults(localMapped)")
        expect(modalSrc).toContain("setResults(localMapped)")
        expect(dayMapSrc).not.toContain("setResults([])  // Anti-flicker")
    })

    it("T8: TimelineCard gracefully falls back to og_image when shared mly_ streetview image 404s", async () => {
        render(
            <LanguageProvider>
                <TimelineCard
                    index={0}
                    onEdit={vi.fn()}
                    onDelete={vi.fn()}
                    onUpdateActivity={vi.fn().mockResolvedValue(true)}
                    activity={{
                        id: "act-mly-404",
                        time: "10:00",
                        time_slot: "10:00",
                        place: "Arashiyama",
                        preview_metadata: {
                            mapillary_thumb: "https://res.cloudinary.com/dnpcnwrcu/image/upload/v1/ryan_travel/streetview/mly_1414593269762424.jpg",
                            og_image: "https://example.com/arashiyama-fallback.jpg",
                        },
                    }}
                />
            </LanguageProvider>
        )

        const img1 = screen.getByRole("img", { name: "Arashiyama" }) as HTMLImageElement
        expect(img1.getAttribute("src")).toContain("mly_1414593269762424")

        // Simulate 404 on broken mly_ Cloudinary image -> must fall forward to og_image!
        fireEvent.error(img1)
        await waitFor(() => {
            const img2 = screen.getByRole("img", { name: "Arashiyama" }) as HTMLImageElement
            expect(img2.getAttribute("src")).toContain("arashiyama-fallback.jpg")
        })

        // Simulate fallback failing too -> hides cleanly without broken img tag
        fireEvent.error(screen.getByRole("img", { name: "Arashiyama" }))
        await waitFor(() => {
            expect(screen.queryByRole("img", { name: "Arashiyama" })).toBeNull()
        })
    })

    it("T9: pdf-generator handles check_in/check_out aliases and omits dangling hyphen when empty", () => {
        const pdfSrc = fs.readFileSync(path.resolve(__dirname, "..", "lib", "pdf-generator.ts"), "utf-8")
        expect(pdfSrc).toContain("hotel.check_in ?? hotel.checkIn")
        expect(pdfSrc).toContain("hotel.check_out ?? hotel.checkOut")
        expect(pdfSrc).toContain("stayRange ?")
    })
})
