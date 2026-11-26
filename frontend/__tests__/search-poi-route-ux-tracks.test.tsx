import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react"
import fs from "node:fs"
import path from "node:path"

import POIDetailDrawer, { type POIBasicData } from "@/components/POIDetailDrawer"
import { MultiDayMasterMap, isCrossRegionDayStops, prioritizeDayRouteSpecs } from "@/components/itinerary/MultiDayMasterMap"
import type { Trip } from "@/lib/itinerary-types"

// Mock MapLibre & map sub-hooks so we can render <MultiDayMasterMap /> behaviorally in jsdom
let latestCapturedFeatures: Array<{ properties?: Record<string, unknown>; geometry?: { type?: string; coordinates?: unknown } }> = []
vi.mock("react-map-gl/maplibre", () => ({
    default: ({ children }: { children?: React.ReactNode }) => <div data-testid="mock-map">{children}</div>,
    Source: ({ data, children }: { data?: { features?: typeof latestCapturedFeatures }; children?: React.ReactNode }) => {
        if (data?.features) {
            latestCapturedFeatures = data.features
        }
        return <div data-testid="mock-source">{children}</div>
    },
    Layer: () => null,
    Marker: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
    NavigationControl: () => null,
    AttributionControl: () => null,
}))
vi.mock("maplibre-gl", () => ({ setWorkerUrl: vi.fn() }))
vi.mock("@/lib/hooks/usePoiPool", () => ({ usePoiPool: () => ({ poiList: [] }) }))
vi.mock("@/hooks/useFlyoverController", () => ({
    useFlyoverController: () => ({
        isFlying: false,
        isTouring: false,
        isOrbiting: false,
        isPaused: false,
        currentTourIndex: 0,
        currentTourPOI: null,
        triggerFlyover: vi.fn(),
        startTour: vi.fn(),
        skipToNext: vi.fn(),
        togglePauseTour: vi.fn(),
        cancelFlight: vi.fn(),
    }),
}))
vi.mock("@/components/MapillaryViewer", () => ({ default: () => null }))
vi.mock("@/components/TourHudCapsule", () => ({ TourHudCapsule: () => null }))
vi.mock("@/components/MapControlCapsule", () => ({ MapControlCapsule: () => null }))
vi.mock("@/lib/mapillary", () => ({ isMapillaryAvailable: () => false }))

// Mock LanguageContext & hooks for deterministic POIDetailDrawer rendering
vi.mock("@/lib/LanguageContext", () => ({
    useLanguage: () => ({
        lang: "zh",
        t: (k: string) => k,
    }),
}))

vi.mock("@/lib/hooks", () => ({
    useHaptic: () => ({
        tap: vi.fn(),
        selection: vi.fn(),
        success: vi.fn(),
    }),
}))

describe("Tracks A–C: Search Proxy Parallel Race, POIDetailDrawer Option A + Lightbox, MultiDayMasterMap Route Guards", () => {
    beforeEach(() => {
        vi.restoreAllMocks()
    })

    afterEach(() => {
        vi.restoreAllMocks()
    })

    // -------------------------------------------------------------------------
    // Track A: cloudflare/search-proxy/worker.js
    // -------------------------------------------------------------------------
    it("Track A: search-proxy races DDG || RSS in parallel, prefers DDG over RSS, fixes zh-TW/ja locale, and filters CJK stopwords", async () => {
        const searchWorkerMod = await import("../../cloudflare/search-proxy/worker.js")

        const seenRssUrls: string[] = []
        const ddgOkHtml = `
          <table>
            <tr><td><a class="result-link" href="https://www.tokyoeki-1bangai.co.jp/">東京車站一番街官方指南</a></td></tr>
            <tr><td class="result-snippet">2026 東京車站美食、拉麵街與伴手禮完整導覽。</td></tr>
          </table>
        `
        const rssOkXml = `
          <rss><channel>
            <item>
              <title>東京車站必逛伴手禮 2026 最新清單 - 旅遊新聞</title>
              <link>https://news.example.tw/tokyo-station-2026</link>
              <pubDate>Thu, 26 Nov 2026 08:00:00 GMT</pubDate>
              <source>旅遊新聞</source>
            </item>
          </channel></rss>
        `

        // Case 1: Both DDG and RSS succeed -> DDG wins (higher quality web result)
        vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL) => {
            const u = String(input)
            if (u.includes("news.google.com")) {
                seenRssUrls.push(u)
                return new Response(rssOkXml, { status: 200 })
            }
            if (u.includes("lite.duckduckgo.com")) {
                return new Response(ddgOkHtml, { status: 200 })
            }
            return new Response("{}", { status: 404 })
        })

        const respBoth = await searchWorkerMod.default.fetch(
            new Request("https://search-proxy.local/search?q=" + encodeURIComponent("東京車站 食べログ 推薦") + "&limit=3", {
                headers: { "x-tabidachi-key": "secret-track-a" },
            }),
            { PROXY_SECRET: "secret-track-a" },
            {}
        )
        expect(respBoth.status).toBe(200)
        const jsonBoth = await respBoth.json()
        expect(jsonBoth.source).toBe("ddg")
        expect(jsonBoth.results[0].url).toBe("https://www.tokyoeki-1bangai.co.jp/")
        // Crucial: "東京車站 食べログ 推薦" must query zh-TW Google News, NOT hl=ja&gl=JP
        expect(seenRssUrls[0]).toContain("hl=zh-TW")
        expect(seenRssUrls[0]).toContain("gl=TW")

        // Case 2: DDG returns 202 anti-bot CAPTCHA -> RSS fallback returns results without stopword over-filtering
        seenRssUrls.length = 0
        vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL) => {
            const u = String(input)
            if (u.includes("news.google.com")) {
                seenRssUrls.push(u)
                return new Response(rssOkXml, { status: 200 })
            }
            if (u.includes("lite.duckduckgo.com")) {
                return new Response("<html>CAPTCHA</html>", { status: 202 })
            }
            return new Response("{}", { status: 404 })
        })

        const respRssFallback = await searchWorkerMod.default.fetch(
            new Request("https://search-proxy.local/search?q=" + encodeURIComponent("東京車站 2026 行程推薦 附近最熱門") + "&limit=3", {
                headers: { "x-tabidachi-key": "secret-track-a" },
            }),
            { PROXY_SECRET: "secret-track-a" },
            {}
        )
        expect(respRssFallback.status).toBe(200)
        const jsonRss = await respRssFallback.json()
        expect(jsonRss.source).toBe("google_news_rss")
        expect(jsonRss.results).toHaveLength(1)
        expect(jsonRss.results[0].title).toContain("東京車站必逛伴手禮")
        expect(seenRssUrls[0]).toContain("hl=zh-TW")

        // Case 3: Genuine Japanese queries (including Kanji-heavy travel queries like 浅草寺 営業時間 アクセス / 新宿 ランチ 予約 / 個室) use hl=ja&gl=JP and strip Japanese stopwords
        const jpNewsXml = `
          <rss><channel>
            <item>
              <title>浅草寺本堂・雷門の参拝ガイド 2026 - 旅チャンネル</title>
              <link>https://news.example.jp/sensoji</link>
              <pubDate>Thu, 26 Nov 2026 08:00:00 GMT</pubDate>
              <source>旅チャンネル</source>
            </item>
            <item>
              <title>新宿ランチのおすすめ個室レストラン10選 - グルメ新聞</title>
              <link>https://news.example.jp/shinjuku-lunch</link>
              <pubDate>Thu, 26 Nov 2026 08:00:00 GMT</pubDate>
              <source>グルメ新聞</source>
            </item>
          </channel></rss>
        `
        vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL) => {
            const u = String(input)
            if (u.includes("news.google.com")) {
                seenRssUrls.push(u)
                return new Response(jpNewsXml, { status: 200 })
            }
            if (u.includes("lite.duckduckgo.com")) {
                return new Response("<html>CAPTCHA</html>", { status: 202 })
            }
            return new Response("{}", { status: 404 })
        })
        for (const jpQuery of [
            "渋谷駅 ラーメン おすすめ",
            "浅草の旅館 おすすめ",
            "東京のおすすめ美術館",
            "新宿で買い物 おすすめ",
            "浅草寺 営業時間 アクセス",
            "新宿 ランチ 予約",
            "京都 清水寺 チケット",
            "新宿 個室 ランチ おすすめ",
        ]) {
            seenRssUrls.length = 0
            const rJp = await searchWorkerMod.default.fetch(
                new Request("https://search-proxy.local/search?q=" + encodeURIComponent(jpQuery) + "&limit=2", {
                    headers: { "x-tabidachi-key": "secret-track-a" },
                }),
                { PROXY_SECRET: "secret-track-a" },
                {}
            )
            expect(seenRssUrls[0]).toContain("hl=ja")
            expect(seenRssUrls[0]).toContain("gl=JP")
            if (jpQuery === "浅草寺 営業時間 アクセス" || jpQuery === "新宿 個室 ランチ おすすめ") {
                const jJp = await rJp.json()
                expect(jJp.source).toBe("google_news_rss")
                expect(jJp.results.length).toBeGreaterThanOrEqual(1)
            }
        }

        // Case 3b: Taxonomy forum keywords (ptt/dcard) must NOT let off-topic supplement spam bypass city relevance
        const pttSpamXml = `
          <rss><channel>
            <item>
              <title>2026鋅保健食品推薦》PTT、Dcard實測5款品牌 - 風傳媒</title>
              <link>https://news.example.tw/zinc-spam</link>
              <pubDate>Thu, 26 Nov 2026 08:00:00 GMT</pubDate>
              <source>風傳媒</source>
            </item>
            <item>
              <title>PTT、Dcard 推薦 6 家台北夜市必吃美食 - 旅遊誌</title>
              <link>https://news.example.tw/taipei-food</link>
              <pubDate>Thu, 26 Nov 2026 08:00:00 GMT</pubDate>
              <source>旅遊誌</source>
            </item>
          </channel></rss>
        `
        vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL) => {
            const u = String(input)
            if (u.includes("news.google.com")) {
                return new Response(pttSpamXml, { status: 200 })
            }
            if (u.includes("lite.duckduckgo.com")) {
                return new Response("<html>CAPTCHA</html>", { status: 202 })
            }
            return new Response("{}", { status: 404 })
        })
        const respPtt = await searchWorkerMod.default.fetch(
            new Request("https://search-proxy.local/search?q=" + encodeURIComponent("台北 最新 ptt dcard 推薦") + "&limit=3", {
                headers: { "x-tabidachi-key": "secret-track-a" },
            }),
            { PROXY_SECRET: "secret-track-a" },
            {}
        )
        const jsonPtt = await respPtt.json()
        expect(jsonPtt.source).toBe("google_news_rss")
        expect(jsonPtt.results).toHaveLength(1)
        expect(jsonPtt.results[0].title).toContain("台北夜市")
        expect(jsonPtt.results[0].title).not.toContain("保健食品")

        // Case 4: Multi-temporal query ("淺草寺 2026 營業時間 門票") must strip ALL temporal tokens globally (not just the first!)
        const sensoRssXml = `
          <rss><channel>
            <item>
              <title>淺草寺參拜人潮創新高 雷門周邊必訪亮點 - 旅遊新聞</title>
              <link>https://news.example.tw/sensoji-2026</link>
              <pubDate>Thu, 26 Nov 2026 08:00:00 GMT</pubDate>
              <source>旅遊新聞</source>
            </item>
          </channel></rss>
        `
        vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL) => {
            const u = String(input)
            if (u.includes("news.google.com")) {
                return new Response(sensoRssXml, { status: 200 })
            }
            if (u.includes("lite.duckduckgo.com")) {
                return new Response("<html>CAPTCHA</html>", { status: 202 })
            }
            return new Response("{}", { status: 404 })
        })
        const respMultiTemporal = await searchWorkerMod.default.fetch(
            new Request("https://search-proxy.local/search?q=" + encodeURIComponent("淺草寺 2026 營業時間 門票") + "&limit=3", {
                headers: { "x-tabidachi-key": "secret-track-a" },
            }),
            { PROXY_SECRET: "secret-track-a" },
            {}
        )
        const jsonMultiTemporal = await respMultiTemporal.json()
        expect(jsonMultiTemporal.source).toBe("google_news_rss")
        expect(jsonMultiTemporal.results).toHaveLength(1)
        expect(jsonMultiTemporal.results[0].title).toContain("淺草寺")

        // Case 5: Zero head-of-line blocking — fast DDG result MUST return immediately & abort stalled RSS (never wait 2800ms)
        let rssAborted = false
        vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
            const u = String(input)
            if (u.includes("lite.duckduckgo.com")) {
                return Promise.resolve(new Response(ddgOkHtml, { status: 200 }))
            }
            if (u.includes("news.google.com")) {
                return new Promise<Response>((_, reject) => {
                    const sig = init?.signal
                    if (sig?.aborted) {
                        rssAborted = true
                        reject(new DOMException("Aborted", "AbortError"))
                        return
                    }
                    sig?.addEventListener("abort", () => {
                        rssAborted = true
                        reject(new DOMException("Aborted", "AbortError"))
                    })
                })
            }
            return Promise.resolve(new Response("{}", { status: 404 }))
        })
        const t0 = performance.now()
        const respFastDdg = await searchWorkerMod.default.fetch(
            new Request("https://search-proxy.local/search?q=" + encodeURIComponent("Tokyo Station 2026 guide") + "&limit=3", {
                headers: { "x-tabidachi-key": "secret-track-a" },
            }),
            { PROXY_SECRET: "secret-track-a" },
            {}
        )
        const elapsedMs = performance.now() - t0
        const jsonFastDdg = await respFastDdg.json()
        expect(jsonFastDdg.source).toBe("ddg")
        expect(jsonFastDdg.results).toHaveLength(1)
        expect(rssAborted).toBe(true)
        expect(elapsedMs).toBeLessThan(500)
    })

    // -------------------------------------------------------------------------
    // Track B: POIDetailDrawer Option A + Lightbox
    // -------------------------------------------------------------------------
    it("Track B: POIDetailDrawer Option A renders max-w-2xl + detent-adaptive height + object-contain + Portal Lightbox (close by button/backdrop/ESC/POI switch/onError)", () => {
        const shibaPoi: POIBasicData = {
            name: "芝公園",
            type: "park",
            lat: 35.6548,
            lng: 139.7485,
            image_url: "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a1/Shiba_Park.jpg/960px-Shiba_Park.jpg",
        }
        const towerPoi: POIBasicData = {
            name: "東京鐵塔",
            type: "attraction",
            lat: 35.6586,
            lng: 139.7454,
            image_url: "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b2/Tokyo_Tower.jpg/960px-Tokyo_Tower.jpg",
        }

        const { rerender } = render(
            <POIDetailDrawer
                isOpen={true}
                onClose={vi.fn()}
                poi={shibaPoi}
                isInternal={true}
            />
        )

        // 1. Half detent height (h-44 sm:h-52) + max-w-2xl wrapper + foreground object-contain + blurred backdrop
        const trigger = screen.getByTestId("poi-image-trigger")
        expect(trigger.parentElement?.className).toContain("max-w-2xl")
        expect(trigger.className).toContain("h-44")
        expect(trigger.className).toContain("sm:h-52")
        expect(trigger.className).not.toContain("md:h-80")

        const mainImg = screen.getByAltText("芝公園")
        expect(mainImg.className).toContain("object-contain")
        expect(mainImg.getAttribute("src")).toContain("/api/poi/media-proxy?url=")
        expect(mainImg.getAttribute("src")).toContain("960px-Shiba_Park.jpg")

        // 2. Switch detent to "full" -> height adapts to h-56 sm:h-72 md:h-80
        fireEvent.click(screen.getByRole("button", { name: "全屏" }))
        expect(trigger.className).toContain("h-56")
        expect(trigger.className).toContain("sm:h-72")
        expect(trigger.className).toContain("md:h-80")

        // 3. Click thumbnail -> opens fullscreen Lightbox portaled to document.body, focuses 44x44 safe-area close button
        const parentModalClose = vi.fn()
        const parentEscListener = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                if (e.isComposing || e.defaultPrevented || document.querySelector('[data-testid="poi-image-lightbox"]')) {
                    return
                }
                parentModalClose()
            }
        }
        window.addEventListener("keydown", parentEscListener)
        try {
            fireEvent.click(trigger)
            const lightbox = screen.getByTestId("poi-image-lightbox")
            expect(lightbox.getAttribute("role")).toBe("dialog")
            expect(lightbox.parentElement).toBe(document.body)

            const closeBtn = screen.getByRole("button", { name: "關閉圖片預覽" })
            expect(document.activeElement).toBe(closeBtn)
            expect(closeBtn.className).toContain("w-11")
            expect(closeBtn.className).toContain("h-11")
            expect(closeBtn.className).toContain("env(safe-area-inset-top")
            expect(closeBtn.className).toContain("sm:right-[calc(env(safe-area-inset-right,0px)+1.5rem)]")
            expect(closeBtn.className).not.toContain("sm:top-6")
            expect(closeBtn.className).not.toContain("sm:right-6")

            // 4. Close Lightbox via ESC key -> Lightbox closes, parent modal stays open, focus returns to trigger button
            fireEvent.keyDown(window, { key: "Escape" })
            expect(screen.queryByTestId("poi-image-lightbox")).toBeNull()
            expect(parentModalClose).not.toHaveBeenCalled()
            expect(document.activeElement).toBe(trigger)
        } finally {
            window.removeEventListener("keydown", parentEscListener)
        }

        // 5. Reopen & close via backdrop click
        fireEvent.click(trigger)
        expect(screen.getByTestId("poi-image-lightbox")).toBeTruthy()
        fireEvent.click(screen.getByTestId("poi-image-lightbox"))
        expect(screen.queryByTestId("poi-image-lightbox")).toBeNull()

        // 6. Reopen & close via explicit close button
        fireEvent.click(trigger)
        fireEvent.click(screen.getByRole("button", { name: "關閉圖片預覽" }))
        expect(screen.queryByTestId("poi-image-lightbox")).toBeNull()

        // 7. Reopen & switch POI -> Lightbox auto-closes immediately
        fireEvent.click(trigger)
        expect(screen.getByTestId("poi-image-lightbox")).toBeTruthy()
        rerender(
            <POIDetailDrawer
                isOpen={true}
                onClose={vi.fn()}
                poi={towerPoi}
                isInternal={true}
            />
        )
        expect(screen.queryByTestId("poi-image-lightbox")).toBeNull()

        // 8. Broken image triggers silent hide (zero broken img)
        const towerImg = screen.getByAltText("東京鐵塔")
        fireEvent.error(towerImg)
        expect(screen.queryByTestId("poi-image-trigger")).toBeNull()
    })

    // -------------------------------------------------------------------------
    // Track C: MultiDayMasterMap cross-ocean guard + selectedDay priority + 15s timeout
    // -------------------------------------------------------------------------
    it("Track C: MultiDayMasterMap skips cross-ocean/cross-region days, prioritizes selectedDay, and uses 15s timeout", () => {
        // 1. Taipei -> Narita flight day (latSpan ~10.7, lngSpan ~19.2) MUST be skipped
        expect(
            isCrossRegionDayStops([
                { lat: 25.0797, lng: 121.2342 }, // TPE
                { lat: 35.7720, lng: 140.3929 }, // NRT
            ])
        ).toBe(true)

        // 2. Pure longitude cross-region (> 5 deg) MUST also be skipped
        expect(
            isCrossRegionDayStops([
                { lat: 35.68, lng: 135.0 },
                { lat: 35.70, lng: 141.0 },
            ])
        ).toBe(true)

        // 3. Normal Tokyo city day MUST NOT be skipped
        expect(
            isCrossRegionDayStops([
                { lat: 35.6586, lng: 139.7454 },
                { lat: 35.6548, lng: 139.7485 },
                { lat: 35.6762, lng: 139.6503 },
            ])
        ).toBe(false)

        // 4. Empty or single-stop day returns false
        expect(isCrossRegionDayStops([])).toBe(false)
        expect(isCrossRegionDayStops([{ lat: 35.6586, lng: 139.7454 }])).toBe(false)

        // 5. prioritizeDayRouteSpecs puts selected day first without disturbing remaining order
        const specs = [
            { dayNum: 2 },
            { dayNum: 3 },
            { dayNum: 7 },
            { dayNum: 8 },
        ]
        expect(prioritizeDayRouteSpecs(specs, 7).map((s) => s.dayNum)).toEqual([7, 2, 3, 8])
        expect(prioritizeDayRouteSpecs(specs, 0).map((s) => s.dayNum)).toEqual([2, 3, 7, 8])
        expect(prioritizeDayRouteSpecs(specs, 99).map((s) => s.dayNum)).toEqual([2, 3, 7, 8])

        // 6. Verify MultiDayMasterMap source enforces 15000ms timeout, cross-region filter, lng !== 0 guard, and FullscreenMapModal Lightbox ESC yield
        const mapSrc = fs.readFileSync(
            path.resolve(__dirname, "..", "components", "itinerary", "MultiDayMasterMap.tsx"),
            "utf-8"
        )
        expect(mapSrc).toContain("!isCrossRegionDayStops(spec.validDayStops)")
        expect(mapSrc).toContain("Number(a.lng) !== 0")
        expect(mapSrc).toContain("prioritizeDayRouteSpecs(")
        expect(mapSrc).toContain("15000")

        const fullscreenSrc = fs.readFileSync(
            path.resolve(__dirname, "..", "components", "FullscreenMapModal.tsx"),
            "utf-8"
        )
        expect(fullscreenSrc).toContain('poi-image-lightbox')
        expect(fullscreenSrc).toContain("e.defaultPrevented")
    })

    it("Track C (Behavioral): MultiDayMasterMap skips cross-ocean days, preempts mid-load queue when user clicks Day 5, and clears stale polylines when switching to cross-ocean-only trip", async () => {
        latestCapturedFeatures = []
        const makeAct = (id: string, place: string, lat: number, lng: number) => ({
            id,
            time: "10:00",
            place,
            lat,
            lng,
            category: "sightseeing",
        })

        const sixDayTrip: Trip = {
            id: "trip-6d",
            title: "東京 6 日",
            days: [
                // Day 1: TPE -> NRT cross-ocean flight (MUST BE SKIPPED)
                { day: 1, activities: [makeAct("d1a", "TPE", 25.0797, 121.2342), makeAct("d1b", "NRT", 35.7720, 140.3929)] },
                // Days 2-5: Normal Tokyo city stops (distinct latitudes for identification)
                { day: 2, activities: [makeAct("d2a", "D2A", 35.6200, 139.7200), makeAct("d2b", "D2B", 35.6250, 139.7250)] },
                { day: 3, activities: [makeAct("d3a", "D3A", 35.6300, 139.7300), makeAct("d3b", "D3B", 35.6350, 139.7350)] },
                { day: 4, activities: [makeAct("d4a", "D4A", 35.6400, 139.7400), makeAct("d4b", "D4B", 35.6450, 139.7450)] },
                { day: 5, activities: [makeAct("d5a", "D5A", 35.6500, 139.7500), makeAct("d5b", "D5B", 35.6550, 139.7550)] },
                // Day 6: NRT -> TPE cross-ocean flight (MUST BE SKIPPED)
                { day: 6, activities: [makeAct("d6a", "NRT", 35.7720, 140.3929), makeAct("d6b", "TPE", 25.0797, 121.2342)] },
            ],
        } as unknown as Trip

        const resolvers: Record<string, (resp: Response) => void> = {}
        const fetchedOrder: string[] = []

        vi.spyOn(globalThis, "fetch").mockImplementation((_url, init) => {
            const parsed = JSON.parse(String(init?.body || "{}")) as { stops?: Array<{ name?: string; lat: number; lng: number }> }
            const firstName = parsed.stops?.[0]?.name || "UNKNOWN"
            fetchedOrder.push(firstName)
            return new Promise<Response>((resolve) => {
                resolvers[firstName] = resolve
            })
        })

        const { rerender } = render(<MultiDayMasterMap trip={sixDayTrip} />)

        // 1. Concurrency cap = 2 -> Day 2 & Day 3 start immediately; cross-ocean Day 1 & Day 6 NEVER fire
        await waitFor(() => {
            expect(fetchedOrder).toEqual(["D2A", "D3A"])
        })

        // 2. User clicks Day 5 tab ("切換至 Day 5") while Day 2 & Day 3 are still in-flight
        fireEvent.click(screen.getByRole("button", { name: "切換至 Day 5" }))

        // 3. Release Day 2 -> worker MUST preempt remainingQueue and fetch Day 5 BEFORE Day 4!
        await act(async () => {
            resolvers["D2A"](new Response(JSON.stringify({
                source: "osrm-fossgis",
                route: { geometry: { type: "LineString", coordinates: [[139.72, 35.62], [139.722, 35.622], [139.725, 35.625]] } },
            }), { status: 200 }))
        })

        await waitFor(() => {
            expect(fetchedOrder).toEqual(["D2A", "D3A", "D5A"])
        })

        // Release remaining in-flight fetches cleanly
        await act(async () => {
            resolvers["D3A"](new Response(JSON.stringify({
                source: "osrm-fossgis",
                route: { geometry: { type: "LineString", coordinates: [[139.73, 35.63], [139.735, 35.635]] } },
            }), { status: 200 }))
            resolvers["D5A"](new Response(JSON.stringify({
                source: "osrm-fossgis",
                route: { geometry: { type: "LineString", coordinates: [[139.75, 35.65], [139.755, 35.655]] } },
            }), { status: 200 }))
        })
        await waitFor(() => {
            expect(fetchedOrder).toEqual(["D2A", "D3A", "D5A", "D4A"])
        })
        await act(async () => {
            resolvers["D4A"](new Response(JSON.stringify({
                source: "osrm-fossgis",
                route: { geometry: { type: "LineString", coordinates: [[139.74, 35.64], [139.745, 35.645]] } },
            }), { status: 200 }))
        })
        expect(fetchedOrder).not.toContain("TPE")
        expect(fetchedOrder).not.toContain("NRT")

        // 4. Switch to a trip whose Day 2 is cross-ocean (specs becomes empty) -> stale 3-point Tokyo road polyline MUST be cleared!
        const crossOceanOnlyTrip: Trip = {
            id: "trip-flight-only",
            title: "跨洋轉機",
            days: [
                { day: 2, activities: [makeAct("f2a", "TPE", 25.0797, 121.2342), makeAct("f2b", "NRT", 35.7720, 140.3929)] },
            ],
        } as unknown as Trip
        rerender(<MultiDayMasterMap trip={crossOceanOnlyTrip} />)

        await waitFor(() => {
            const day2Route = latestCapturedFeatures.find(
                (f) => f.properties?.type === "daily-route" && f.properties?.day === 2
            )
            expect(day2Route?.geometry?.coordinates).toEqual([
                [121.2342, 25.0797],
                [140.3929, 35.772],
            ])
        })
    })
})
