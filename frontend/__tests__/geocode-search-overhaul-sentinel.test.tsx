/**
 * @vitest-environment jsdom
 */
import fs from "fs"
import path from "path"
import vm from "vm"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { waitFor, renderHook } from "@testing-library/react"
import { GeocodeResponseSchema, GeocodeResultSchema } from "@/lib/schemas"
import { getSmartZoomConfig, isMacroGeoResult, isUsableMacroExtent } from "@/lib/location-utils"
import { useLocalGeocode } from "@/hooks/useLocalGeocode"

function loadEdgeShieldWorker() {
    const repoRoot = path.resolve(__dirname, "..", "..")
    const workerPath = path.join(repoRoot, "cloudflare", "edge-shield", "worker.js")
    const rawCode = fs.readFileSync(workerPath, "utf-8")
    const transformed = rawCode.replace(/export\s+default\s+\{/, "module.exports = {")
    const mod = {
        exports: {} as {
            fetch: (
                req: Request,
                env: Record<string, unknown>,
                ctx: { waitUntil: (p: Promise<unknown>) => void }
            ) => Promise<Response>
        },
    }
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

describe("Geocode Search Overhaul — Schema, Location Utils, Local Geocode & Edge Shield Sentinel", () => {
    const originalFetch = global.fetch

    beforeEach(() => {
        vi.clearAllMocks()
    })

    afterEach(() => {
        global.fetch = originalFetch
    })

    it("AC-UI-5.1: GeocodeResultSchema & GeocodeResponseSchema preserve osm_id, display_name, city, country, state, source", () => {
        const parsed = GeocodeResponseSchema.parse({
            source: "photon",
            results: [
                {
                    lat: 25.0339,
                    lng: 121.5645,
                    name: "Starbucks Taipei 101",
                    display_name: "Starbucks, Xinyi, Taipei, Taiwan",
                    original_name: "Starbucks",
                    osm_id: 987654321,
                    osm_type: "N",
                    city: "Taipei",
                    state: "Taiwan",
                    country: "Taiwan",
                    importance: 0.72,
                    type: "cafe",
                    extent: [121.56, 25.03, 121.57, 25.04],
                },
            ],
        })
        expect(parsed.source).toBe("photon")
        expect(parsed.results[0].osm_id).toBe(987654321)
        expect(parsed.results[0].display_name).toBe("Starbucks, Xinyi, Taipei, Taiwan")
        expect(parsed.results[0].city).toBe("Taipei")
        expect(parsed.results[0].country).toBe("Taiwan")
        expect(parsed.results[0].importance).toBe(0.72)

        const parsedSingle = GeocodeResultSchema.parse({ lat: 48.137, lng: 11.575, name: "Rathaus", osm_id: "way-42" })
        expect(parsedSingle.osm_id).toBe("way-42")
    })

    it("AC-UI-5.2: isMacroGeoResult, getSmartZoomConfig & isUsableMacroExtent guard trans-oceanic extents (>45 deg)", () => {
        expect(isMacroGeoResult({ type: "country", admin_level: 2 })).toBe(true)
        expect(isMacroGeoResult({ type: "city", admin_level: 6 })).toBe(true)
        expect(isMacroGeoResult({ type: "administrative", admin_level: null })).toBe(true)
        expect(isMacroGeoResult({ type: "region" })).toBe(true)
        expect(isMacroGeoResult({ type: "cafe", admin_level: null })).toBe(false)
        expect(isMacroGeoResult({ type: "station", admin_level: 8 })).toBe(false)

        expect(getSmartZoomConfig({ type: "administrative" })).toEqual({ zoom: 10.5, duration: 1600 })
        expect(getSmartZoomConfig({ type: "region" })).toEqual({ zoom: 10.5, duration: 1600 })

        // Valid Germany extent (~9 deg lon, ~8 deg lat) -> usable
        expect(isUsableMacroExtent([5.86, 47.27, 15.04, 55.10])).toBe(true)
        // Trans-oceanic France / USA extent (>45 deg span) -> rejected to trigger clean flyTo fallback
        expect(isUsableMacroExtent([-61.8, -21.4, 55.8, 51.1])).toBe(false)
        expect(isUsableMacroExtent([-179.0, 18.9, -66.9, 71.4])).toBe(false)
        // Inverted or degenerate extent -> rejected
        expect(isUsableMacroExtent([121.6, 25.1, 121.4, 25.0])).toBe(false)
        expect(isUsableMacroExtent([121.5, 25.0, 121.5, 25.0])).toBe(false)
        expect(isUsableMacroExtent(null)).toBe(false)
    })

    it("Safety Net #4: useLocalGeocode aligns 臺->台, prevents 龍山寺/龍山站 collision, uses AND+substring filter, and returns unlimited matches", async () => {
        const mockLandmarks = {
            "臺南孔廟": { aliases: ["tainan confucius temple"], search: "Tainan Confucius Temple", display: "臺南孔廟", country: "TW", lat: 22.9904, lng: 120.2043 },
            "龍山寺": { aliases: ["艋舺龍山寺"], search: "Lungshan Temple", display: "艋舺龍山寺", country: "TW", lat: 25.0372, lng: 121.4999 },
            "龍山站": { aliases: ["yongsan station"], search: "Yongsan Station", display: "首爾龍山站", country: "KR", lat: 37.5299, lng: 126.9645 },
            "築地市場": { aliases: ["tsukiji"], search: "Tsukiji Market", display: "築地市場", country: "JP", lat: 35.6654, lng: 139.7707 },
            "東京鐵塔": { aliases: ["tokyo tower"], search: "Tokyo Tower", display: "東京鐵塔", country: "JP", lat: 35.6586, lng: 139.7454 },
            "台北 101": { aliases: ["taipei 101"], search: "Taipei 101", display: "台北 101", country: "TW", lat: 25.0339, lng: 121.5645 },
            ...Object.fromEntries(
                Array.from({ length: 8 }, (_, i) => [
                    `台北咖啡${i + 1}`,
                    { aliases: [], search: `Taipei Cafe ${i + 1}`, display: `台北咖啡${i + 1}`, country: "TW", lat: 25.03 + i * 0.001, lng: 121.56 },
                ])
            ),
        }

        global.fetch = vi.fn(async (url: RequestInfo | URL) => {
            const s = String(url)
            if (s.includes("landmarks.json") && !s.includes("countries/")) {
                return new Response(JSON.stringify(mockLandmarks), { status: 200 })
            }
            if (s.includes("brands.json")) {
                return new Response(JSON.stringify({}), { status: 200 })
            }
            return new Response(null, { status: 404 })
        }) as unknown as typeof fetch

        const { result } = renderHook(() => useLocalGeocode())
        await waitFor(() => expect(result.current.isLoaded).toBe(true))

        // 1. 臺->台 normalization works
        const tainanHits = result.current.search("台南")
        expect(tainanHits.some((r) => r.display === "臺南孔廟")).toBe(true)

        // 2. 龍山寺 does NOT collide with 龍山站
        const templeHits = result.current.search("龍山寺")
        expect(templeHits.some((r) => r.display === "艋舺龍山寺")).toBe(true)
        expect(templeHits.some((r) => r.display === "首爾龍山站")).toBe(false)

        // 3. AND + substring guard prevents '市政廳' from matching '築地市場' via shared char '市'
        const hallHits = result.current.search("市政廳")
        expect(hallHits).toHaveLength(0)

        // 4. Omitting limit returns ALL 8 matches (no artificial 5-item cap)
        const cafeHits = result.current.search("台北咖啡")
        expect(cafeHits).toHaveLength(8)

        // 5. Whitespace / multi-word CJK & mixed queries still match cleanly
        expect(result.current.search("東京 鐵塔").some((r) => r.display === "東京鐵塔")).toBe(true)
        expect(result.current.search("台北101").some((r) => r.display === "台北 101")).toBe(true)
    })

    it("Edge Shield worker.js: strips Content-Encoding/Length on cache write, skips ArcGIS caching, and isolates macro zoom<=10", async () => {
        const { worker, cacheStore, mockFetch } = loadEdgeShieldWorker()
        const waitUntil = vi.fn()
        const ctx = { waitUntil }
        const env = {}

        const captured: { forwardedHeaders: Headers | null } = { forwardedHeaders: null }
        mockFetch.mockImplementationOnce(async (_url: string, init?: RequestInit) => {
            captured.forwardedHeaders = new Headers(init?.headers)
            return new Response(
                JSON.stringify({ results: [{ name: "Munich Rathaus", lat: 48.137, lng: 11.575 }], source: "photon" }),
                {
                    status: 200,
                    headers: {
                        "Content-Type": "application/json",
                        "Content-Encoding": "gzip",
                        "Content-Length": "999",
                        "Set-Cookie": "sid=leak",
                    },
                }
            )
        })

        const req1 = new Request("https://www.tabijiapp.com/api/geocode/search", {
            method: "POST",
            headers: { "Content-Type": "application/json", "Content-Length": "123", "Content-Encoding": "gzip" },
            body: JSON.stringify({ query: "Rathaus", lat: 48.137, lng: 11.575, zoom: 14, locale: "zh" }),
        })
        const res1 = await worker.fetch(req1, env, ctx)
        expect(res1.headers.get("X-Edge-Cache")).toBe("MISS")
        expect(captured.forwardedHeaders?.has("Content-Length")).toBe(false)
        expect(captured.forwardedHeaders?.has("Content-Encoding")).toBe(false)

        await Promise.all(waitUntil.mock.calls.map((c) => c[0]))
        expect(cacheStore.size).toBe(1)

        // Verify cached entry has clean headers (NO Content-Encoding, NO Set-Cookie!)
        const cachedEntry = Array.from(cacheStore.values())[0]
        expect(cachedEntry.headers.get("Content-Encoding")).toBeNull()
        expect(cachedEntry.headers.get("Set-Cookie")).toBeNull()
        expect(cachedEntry.headers.get("Content-Type")).toContain("application/json")

        // Macro zoom <= 10 (aligned with backend int_zoom <= 10) gets distinct cache key (zb=macro) -> MISS
        mockFetch.mockImplementationOnce(async () =>
            new Response(JSON.stringify({ results: [{ name: "Germany", lat: 51.16, lng: 10.45 }], source: "photon" }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
            })
        )
        const reqMacro = new Request("https://www.tabijiapp.com/api/geocode/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: "Rathaus", lat: 48.137, lng: 11.575, zoom: 10, locale: "zh" }),
        })
        const resMacro = await worker.fetch(reqMacro, env, ctx)
        expect(resMacro.headers.get("X-Edge-Cache")).toBe("MISS")
        await Promise.all(waitUntil.mock.calls.map((c) => c[0]))
        expect(cacheStore.size).toBe(2)
        expect(Array.from(cacheStore.keys()).some((k) => k.includes("zb=macro"))).toBe(true)

        // Zoom 6 shares the macro bucket (zb=macro) -> HIT!
        const reqMacroZ6 = new Request("https://www.tabijiapp.com/api/geocode/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: "Rathaus", lat: 48.137, lng: 11.575, zoom: 6, locale: "zh" }),
        })
        const resMacroZ6 = await worker.fetch(reqMacroZ6, env, ctx)
        expect(resMacroZ6.headers.get("X-Edge-Cache")).toBe("HIT")

        // City/local zoom 11.2 and 15.8 share the non-macro bucket (preserving T3 contract) -> HIT!
        // Also verify dynamic whitelisted CORS reflection on HIT (never cached in shared store, never reflected for evil origins!)
        expect(cachedEntry.headers.get("Access-Control-Allow-Origin")).toBeNull()
        const reqLocalZ11 = new Request("https://www.tabijiapp.com/api/geocode/search", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Origin": "https://travel-pwa-five.vercel.app",
            },
            body: JSON.stringify({ query: "Rathaus", lat: 48.137, lng: 11.575, zoom: 11.2, locale: "zh" }),
        })
        const resLocalZ11 = await worker.fetch(reqLocalZ11, env, ctx)
        expect(resLocalZ11.headers.get("X-Edge-Cache")).toBe("HIT")
        expect(resLocalZ11.headers.get("Access-Control-Allow-Origin")).toBe("https://travel-pwa-five.vercel.app")
        expect(resLocalZ11.headers.get("Access-Control-Allow-Credentials")).toBe("true")
        expect(resLocalZ11.headers.get("Vary")).toBe("Origin")
        expect(resLocalZ11.headers.get("X-Content-Type-Options")).toBe("nosniff")

        // Untrusted origin on HIT MUST NOT receive Access-Control-Allow-Origin
        const reqEvilOrigin = new Request("https://www.tabijiapp.com/api/geocode/search", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Origin": "https://evil-attacker.example",
            },
            body: JSON.stringify({ query: "Rathaus", lat: 48.137, lng: 11.575, zoom: 11.2, locale: "zh" }),
        })
        const resEvilOrigin = await worker.fetch(reqEvilOrigin, env, ctx)
        expect(resEvilOrigin.headers.get("X-Edge-Cache")).toBe("HIT")
        expect(resEvilOrigin.headers.get("Access-Control-Allow-Origin")).toBeNull()

        // ArcGIS source MUST NOT be written to 7-day edge cache
        mockFetch.mockImplementationOnce(async () =>
            new Response(JSON.stringify({ results: [{ name: "ArcGIS Spot", lat: 25.03, lng: 121.56, source: "arcgis" }], source: "arcgis" }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
            })
        )
        const reqArcgis = new Request("https://www.tabijiapp.com/api/geocode/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: "ArcGIS Only Spot", lat: 25.03, lng: 121.56, zoom: 14, locale: "zh" }),
        })
        const resArcgis = await worker.fetch(reqArcgis, env, ctx)
        expect(resArcgis.status).toBe(200)
        await Promise.all(waitUntil.mock.calls.map((c) => c[0]))
        expect(cacheStore.size).toBe(2) // Unchanged!
    })
})
