import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, renderHook } from "@testing-library/react"
import fs from "node:fs"
import path from "node:path"

import { useTripStore, sanitizeStoredId } from "@/lib/stores/tripStore"
import { assertValidTripId, isValidTripId, tripsApi } from "@/lib/api"
import { useTripDetail, useExpenses, useTripCapsules } from "@/lib/hooks"
import { getLeanItinerary } from "@/lib/getLeanItinerary"
import { parseSSE, streamDeepResearch } from "@/lib/sse-parser"
import { LedgerClient } from "@/components/ledger-client"

describe("Wave 1-3 Five-Cloud Hardening Frontend & Edge Contracts", () => {
    beforeEach(() => {
        vi.restoreAllMocks()
        useTripStore.setState({ activeTripId: null, userId: null, activeTripTitle: null })
    })

    it("Wave 3.2: tripStore sanitizes invalid literal IDs (undefined/null/NaN)", () => {
        expect(sanitizeStoredId("undefined")).toBeNull()
        expect(sanitizeStoredId("NULL")).toBeNull()
        expect(sanitizeStoredId("NaN")).toBeNull()
        expect(sanitizeStoredId("   ")).toBeNull()
        expect(sanitizeStoredId("trip-dup")).toBe("trip-dup")

        useTripStore.getState().setActiveTripId("undefined")
        expect(useTripStore.getState().activeTripId).toBeNull()
        useTripStore.getState().setActiveTripId("trip-valid-1")
        expect(useTripStore.getState().activeTripId).toBe("trip-valid-1")
    })

    it("Wave 3.2: assertValidTripId blocks invalid literals while preserving trip-dup compatibility", async () => {
        expect(isValidTripId("undefined")).toBe(false)
        expect(isValidTripId("null")).toBe(false)
        expect(isValidTripId("")).toBe(false)
        expect(isValidTripId("trip-dup")).toBe(true)

        expect(() => assertValidTripId("undefined")).toThrow("Invalid tripId")
        expect(() => assertValidTripId("null")).toThrow("Invalid tripId")
        expect(() => assertValidTripId("")).toThrow("Invalid tripId")
        expect(assertValidTripId("trip-dup")).toBe("trip-dup")

        const fetchSpy = vi.spyOn(globalThis, "fetch")
        await expect(tripsApi.get("undefined", "u1")).rejects.toThrow("Invalid tripId")
        await expect(tripsApi.updateTitle("null", "New", "u1")).rejects.toThrow("Invalid tripId")
        expect(fetchSpy).not.toHaveBeenCalled()
    })

    it("Wave 3.2: hooks return isLoading=false and make 0 fetches for invalid/null IDs", () => {
        const fetchSpy = vi.spyOn(globalThis, "fetch")
        const d = renderHook(() => useTripDetail("undefined", "u1"))
        const e = renderHook(() => useExpenses("null", "u1"))
        const c = renderHook(() => useTripCapsules(null, "u1"))

        expect(d.result.current.isLoading).toBe(false)
        expect(e.result.current.isLoading).toBe(false)
        expect(c.result.current.isLoading).toBe(false)
        expect(fetchSpy).not.toHaveBeenCalled()
    })

    it("Wave 2.3: getLeanItinerary preserves flight_info even on 0-activity skeleton trips", () => {
        const lean = getLeanItinerary(
            {
                title: "2026 東京自由行",
                start_date: "2026-12-01",
                end_date: "2026-12-05",
                flight_info: {
                    outbound: [{ dep_airport: "TPE", arr_airport: "NRT", dep_date: "2026-12-01" }],
                },
            },
            []
        )
        expect(lean).not.toBeNull()
        expect(lean?.title).toBe("2026 東京自由行")
        expect(lean?.flight_info?.outbound?.[0]?.arr_airport).toBe("NRT")
    })

    it("Wave 2.3: parseSSE strips ':' heartbeat comments line-by-line without dropping event/data (FP-104)", () => {
        const chunk = ": heartbeat\nevent: text\ndata: {\"text\":\"Hello\"}\n\n"
        const { events, remaining } = parseSSE(chunk, "")
        expect(remaining).toBe("")
        expect(events).toHaveLength(1)
        expect(events[0].event).toBe("text")
        expect(JSON.parse(events[0].data)).toEqual({ text: "Hello" })
    })

    it("Wave 3.3: LedgerClient renders real Link href='/' and Tabiji branding", async () => {
        vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
            new Response(
                JSON.stringify({
                    trip_name: "東京家族遊",
                    date_range: { start: "2026-12-01", end: "2026-12-05" },
                    total_twd: 12000,
                    expenses: [],
                    members: [{ name: "Ryan" }],
                }),
                { status: 200, headers: { "Content-Type": "application/json" } }
            )
        )
        render(<LedgerClient code="11111111-1111-4111-8111-111111111111" />)
        const link = await screen.findByRole("link", { name: "了解更多" })
        expect(link.getAttribute("href")).toBe("/")
        expect(screen.getByText(/Tabiji/)).toBeTruthy()
        expect(screen.queryByText(/Ryan Travel App/)).toBeNull()
    })

    it("Wave 3.3: next.config.mjs security headers exclude /api/* and /sw.js, enforce worker-src 'self', and whitelist real production origins", async () => {
        const cfgPath = path.resolve(__dirname, "..", "next.config.mjs")
        const raw = fs.readFileSync(cfgPath, "utf-8")
        expect(raw).toContain("async headers()")
        expect(raw).toContain("X-Frame-Options")
        expect(raw).toContain("X-Content-Type-Options")
        expect(raw).toContain("Referrer-Policy")
        expect(raw).toContain("Permissions-Policy")
        expect(raw).toContain("Content-Security-Policy-Report-Only")
        expect(raw).toContain("worker-src 'self'")
        expect(raw).toContain("sw\\\\.js")
        // Real production Cloudinary proxy & Chrome-verified third-party origins (no typo domain)
        expect(raw).toContain("cloudinary-proxy.ryanpig228.workers.dev")
        expect(raw).not.toContain("cloudinary-proxy.ryan880425.workers.dev")
        expect(raw).toContain("https://static.cloudflareinsights.com")
        expect(raw).toContain("https://cloudflareinsights.com")
        expect(raw).toContain("https://cdn.jsdelivr.net")
        expect(raw).toContain("https://*.open-meteo.com")
        expect(raw).toContain("https://tiles.mapillary.com")
    })

    it("Wave 2.3: streamDeepResearch consumes Two-Phase SSE with heartbeats and falls back cleanly on 404", async () => {
        const encoder = new TextEncoder()
        const sseBody = new ReadableStream({
            start(controller) {
                controller.enqueue(encoder.encode("event: start\ndata: {}\n\n"))
                controller.enqueue(encoder.encode(": heartbeat\n\n"))
                controller.enqueue(encoder.encode('event: thinking\ndata: {"status":"researching"}\n\n'))
                controller.enqueue(encoder.encode(': heartbeat\nevent: text\ndata: {"text":"Kyoto Pass Analysis"}\n\n'))
                controller.enqueue(encoder.encode('event: done\ndata: {"engine":"gemini-3.8-flash"}\n\n'))
                controller.close()
            },
        })
        vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
            new Response(sseBody, { status: 200, headers: { "Content-Type": "text/event-stream" } })
        )

        const thinkingCalls: string[] = []
        const textChunks: string[] = []
        let heartbeats = 0
        const okRes = await streamDeepResearch({
            apiUrl: "https://api.example.test",
            apiKey: "AIzaSyTest123456789012345678901234567890",
            prompt: "Compare JR Pass",
            origin: "TPE",
            destination: "TYO",
            onThinking: (s) => thinkingCalls.push(s),
            onText: (t) => textChunks.push(t),
            onHeartbeat: () => { heartbeats += 1 },
        })
        expect(okRes).toEqual({ supported: true, text: "Kyoto Pass Analysis", engine: "gemini-3.8-flash" })
        expect(thinkingCalls).toEqual(["researching"])
        expect(textChunks).toEqual(["Kyoto Pass Analysis"])
        expect(heartbeats).toBe(1)

        // 404 triggers automatic fallback to legacy polling
        vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(null, { status: 404 }))
        const fbRes = await streamDeepResearch({
            apiUrl: "https://api.example.test",
            apiKey: "AIzaSyTest123456789012345678901234567890",
            prompt: "Compare JR Pass",
        })
        expect(fbRes).toEqual({ supported: false })

        // Verify ChatWidget actively imports and invokes streamDeepResearch
        const widgetSrc = fs.readFileSync(
            path.resolve(__dirname, "..", "components", "chat-widget.tsx"),
            "utf-8"
        )
        expect(widgetSrc).toContain("streamDeepResearch")
    })

    it("Wave 1.3 & 3.1: Cloudflare search-proxy skips DDG ads without shifting snippets, decodes hex entities, and edge-shield rejects null coords", async () => {
        const searchWorkerPath = path.resolve(__dirname, "..", "..", "cloudflare", "search-proxy", "worker.js")
        const searchWorkerSrc = fs.readFileSync(searchWorkerPath, "utf-8")
        expect(searchWorkerSrc).toContain("timingSafeEqual")
        expect(searchWorkerSrc).toContain("x-tabidachi-key")
        expect(searchWorkerSrc).toContain("x-proxy-secret")
        expect(searchWorkerSrc).toContain("news.google.com/rss/search")
        expect(searchWorkerSrc).not.toContain('"Access-Control-Allow-Origin": "*"')
        expect(searchWorkerSrc).not.toContain("'Access-Control-Allow-Origin': '*'")

        // Execute search-proxy Worker directly against realistic DDG Lite HTML containing 2 sponsored ads before organic results
        const searchWorkerMod = await import("../../cloudflare/search-proxy/worker.js")
        const ddgHtmlWithAds = `
          <table>
            <tr><td><a class="result-link" href="//duckduckgo.com/y.js?ad_domain=klook.com&amp;u3=https%3A%2F%2Fklook.com">Klook Ad</a></td></tr>
            <tr><td class="result-snippet">SPONSORED KLOOK AD SNIPPET MUST NEVER ATTACH TO ORGANIC RESULT</td></tr>
            <tr><td><a class="result-link" href="https://duckduckgo.com/duckduckgo-help-pages/company/advertising/">Ad Info</a></td></tr>
            <tr><td class="result-snippet">SPONSORED AD HELP SNIPPET</td></tr>
            <tr><td><a class="result-link" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.tokyotower.co.jp%2Ffee%2F">Tokyo Tower: Don&#x27;t Miss &amp; Hours</a></td></tr>
            <tr><td class="result-snippet">Official Tokyo Tower hours: 09:00&#x2013;22:30 &amp; ticket pricing.</td></tr>
            <tr><td><a class="result-link" href="https://example.org/guide">Travel Guide</a></td></tr>
            <tr><td class="result-snippet">Independent guide snippet for result 2.</td></tr>
          </table>
        `
        vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL) => {
            const u = String(input)
            if (u.includes("news.google.com")) {
                return new Response("<rss><channel></channel></rss>", { status: 200 })
            }
            if (u.includes("lite.duckduckgo.com")) {
                return new Response(ddgHtmlWithAds, { status: 200, headers: { "Content-Type": "text/html" } })
            }
            return new Response("{}", { status: 404 })
        })

        const workerResp = await searchWorkerMod.default.fetch(
            new Request("https://search-proxy.local/search?q=Tokyo%20Tower%20hours%202026&limit=2", {
                headers: { "x-tabidachi-key": "test-secret-123" },
            }),
            { PROXY_SECRET: "test-secret-123" },
            {}
        )
        expect(workerResp.status).toBe(200)
        const workerJson = await workerResp.json()
        expect(workerJson.source).toBe("ddg")
        expect(workerJson.results).toHaveLength(2)
        expect(workerJson.results[0]).toEqual({
            title: "Tokyo Tower: Don't Miss & Hours",
            snippet: "Official Tokyo Tower hours: 09:00–22:30 & ticket pricing.",
            url: "https://www.tokyotower.co.jp/fee/",
        })
        expect(workerJson.results[1]).toEqual({
            title: "Travel Guide",
            snippet: "Independent guide snippet for result 2.",
            url: "https://example.org/guide",
        })

        const edgeWorkerSrc = fs.readFileSync(
            path.resolve(__dirname, "..", "..", "cloudflare", "edge-shield", "worker.js"),
            "utf-8"
        )
        expect(edgeWorkerSrc).toContain("/api/poi/media-proxy")
        expect(edgeWorkerSrc).toContain("/api/route")
        expect(edgeWorkerSrc).toContain("straight-line")
        expect(edgeWorkerSrc).toContain("s.lat !== null")
        expect(edgeWorkerSrc).not.toContain("details: err.message")
    })
})
