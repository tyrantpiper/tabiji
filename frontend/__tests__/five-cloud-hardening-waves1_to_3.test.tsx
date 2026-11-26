import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, renderHook } from "@testing-library/react"
import fs from "node:fs"
import path from "node:path"

import { useTripStore, sanitizeStoredId } from "@/lib/stores/tripStore"
import { assertValidTripId, isValidTripId, tripsApi } from "@/lib/api"
import { useTripDetail, useExpenses, useTripCapsules } from "@/lib/hooks"
import { getLeanItinerary } from "@/lib/getLeanItinerary"
import { parseSSE } from "@/lib/sse-parser"
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

    it("Wave 3.3: next.config.mjs security headers exclude /api/* and /sw.js and enforce worker-src 'self'", async () => {
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
    })

    it("Wave 1.3 & 3.1: Cloudflare workers enforce Fail-Closed secret, no CORS wildcard, and route/media-proxy caching", () => {
        const searchWorker = fs.readFileSync(
            path.resolve(__dirname, "..", "..", "cloudflare", "search-proxy", "worker.js"),
            "utf-8"
        )
        expect(searchWorker).toContain("timingSafeEqual")
        expect(searchWorker).toContain("x-tabidachi-key")
        expect(searchWorker).toContain("x-proxy-secret")
        expect(searchWorker).toContain("news.google.com/rss/search")
        expect(searchWorker).not.toContain('"Access-Control-Allow-Origin": "*"')
        expect(searchWorker).not.toContain("'Access-Control-Allow-Origin': '*'")

        const edgeWorker = fs.readFileSync(
            path.resolve(__dirname, "..", "..", "cloudflare", "edge-shield", "worker.js"),
            "utf-8"
        )
        expect(edgeWorker).toContain("/api/poi/media-proxy")
        expect(edgeWorker).toContain("/api/route")
        expect(edgeWorker).toContain("straight-line")
        expect(edgeWorker).not.toContain("details: err.message")
    })
})
