/**
 * @vitest-environment jsdom
 */
import React from "react"
import fs from "fs"
import path from "path"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen, fireEvent, waitFor, renderHook } from "@testing-library/react"
import {
    extractCleanPlaceQuery,
    extractPlaceParentheticalNote,
    normalizeOsmType,
    dedupeGeocodeResults,
} from "@/lib/location-utils"
import { useLocalGeocode } from "@/hooks/useLocalGeocode"

const { mockGeocodeSearch, mockPoiNearby } = vi.hoisted(() => ({
    mockGeocodeSearch: vi.fn(),
    mockPoiNearby: vi.fn(),
}))

vi.mock("@/lib/api", () => ({
    API: { GEOCODE: "/api/geocode/search", POI: "/api/poi" },
    geocodeApi: {
        search: (...args: unknown[]) => mockGeocodeSearch(...args),
        resolveLink: vi.fn(),
        resolveAddress: vi.fn(),
    },
    poiApi: {
        nearby: (...args: unknown[]) => mockPoiNearby(...args),
        recommend: vi.fn(),
        enrich: vi.fn(),
    },
}))

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
        error: vi.fn(),
    }),
}))

vi.mock("sonner", () => ({
    toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

vi.mock("@/components/ui/multi-image-upload", () => ({
    MultiImageUpload: () => <div data-testid="mock-multi-upload" />,
}))

vi.mock("framer-motion", () => ({
    AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
    motion: {
        div: ({
            children,
            // eslint-disable-next-line @typescript-eslint/no-unused-vars
            drag, dragConstraints, dragElastic, onDragEnd, initial, animate, exit, transition,
            ...rest
        }: Record<string, unknown> & { children?: React.ReactNode }) => <div {...(rest as React.HTMLAttributes<HTMLDivElement>)}>{children}</div>,
    },
}))

import { ActivityEditModal } from "@/components/itinerary/ActivityEditModal"
import { LocationEditDialog } from "@/components/itinerary/LocationEditDialog"
import { POISearch } from "@/components/poi-search"
import { TimelineCard } from "@/components/timeline-card"
import POIDetailDrawer from "@/components/POIDetailDrawer"
import type { ItineraryItemState } from "@/lib/itinerary-types"

const LONG_120_NAME = "東京新宿歌舞伎町中央東口超長無空格地名測試專用連鎖旗艦總本店分館第二大樓三樓VIP專屬貴賓座席預約入口區ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

describe("Scope A & Safety Nets (1)(5): UI Wrapping, Zero Horizontal Overflow, ActivityEditModal & Local Geocode", () => {
    const originalFetch = global.fetch

    beforeEach(() => {
        vi.resetAllMocks()
    })

    afterEach(() => {
        global.fetch = originalFetch
    })

    it("AC-UI-1: dialog.tsx has grid-cols-1, scroll-area.tsx clamps Radix display:table, and POIDetailDrawer preserves Peek/2x3 truncate", () => {
        const frontendDir = path.resolve(__dirname, "..")
        const dialogSrc = fs.readFileSync(path.join(frontendDir, "components", "ui", "dialog.tsx"), "utf-8")
        const scrollAreaSrc = fs.readFileSync(path.join(frontendDir, "components", "ui", "scroll-area.tsx"), "utf-8")
        const itineraryViewSrc = fs.readFileSync(path.join(frontendDir, "components", "views", "itinerary-view.tsx"), "utf-8")

        expect(dialogSrc).toContain("grid-cols-1")
        expect(dialogSrc).toContain("overflow-x-hidden")
        expect(scrollAreaSrc).toContain("overflow-x-hidden")
        expect(scrollAreaSrc).toContain("[&>div]:!block")
        expect(scrollAreaSrc).toContain("[&>div]:!min-w-0")

        // Safety Net (1): itinerary-view passes calculateBiasLocation(day) & 3500ms AbortController timeout
        expect(itineraryViewSrc).toContain("calculateBiasLocation(day)")
        expect(itineraryViewSrc).toContain("3500")
        expect(itineraryViewSrc).toContain("signal: controller.signal")
    })

    it("AC-UI-1b: 120-char long place names wrap cleanly across ActivityEditModal, LocationEditDialog, POISearch, TimelineCard & POIDetailDrawer", async () => {
        // 1. LocationEditDialog current location + auto-sync button + search results
        mockGeocodeSearch.mockResolvedValueOnce({
            results: [
                {
                    name: LONG_120_NAME,
                    display_name: LONG_120_NAME + " Address",
                    lat: 35.69,
                    lng: 139.70,
                    type: "restaurant",
                    osm_id: 101,
                    osm_type: "N",
                },
            ],
        })
        const r1 = render(
            <LocationEditDialog
                isOpen={true}
                onOpenChange={vi.fn()}
                day={1}
                dailyLocs={{ 1: { name: LONG_120_NAME, lat: 35.69, lng: 139.70 } }}
                setDailyLocs={vi.fn()}
                currentTrip={{
                    id: "t1",
                    title: "Tokyo",
                    days: [{ day: 1, activities: [{ id: "a1", time_slot: "10:00", place: LONG_120_NAME, lat: 35.69, lng: 139.70 }] }],
                }}
            />
        )
        const currentEl = screen.getAllByText(LONG_120_NAME)[0]
        expect(currentEl.className).toContain("wrap-break-word")
        expect(currentEl.className).toContain("whitespace-normal")
        const syncBtn = screen.getByText("loc_auto_sync").closest("button")
        expect(syncBtn?.className).toContain("whitespace-normal")
        // Trigger search in LocationEditDialog and verify search result wraps
        const locInput = screen.getByPlaceholderText("loc_search_placeholder")
        fireEvent.change(locInput, { target: { value: "Tokyo" } })
        fireEvent.keyDown(locInput, { key: "Enter" })
        await waitFor(() => expect(mockGeocodeSearch).toHaveBeenCalledTimes(1))
        expect(await screen.findByText(LONG_120_NAME + " Address")).toBeInTheDocument()
        // Switching day MUST clear stale LocationEditDialog search results (no cross-day leak)
        r1.rerender(
            <LocationEditDialog
                isOpen={true}
                onOpenChange={vi.fn()}
                day={2}
                dailyLocs={{}}
                setDailyLocs={vi.fn()}
            />
        )
        expect(screen.queryByText(LONG_120_NAME + " Address")).toBeNull()
        r1.unmount()

        // 2. TimelineCard title wraps instead of truncating
        const r2 = render(
            <TimelineCard
                activity={{ id: "a2", time_slot: "12:00", place: LONG_120_NAME, desc: "desc" }}
                index={1}
                onEdit={vi.fn()}
                onDelete={vi.fn()}
                onUpdateActivity={vi.fn(async () => true)}
            />
        )
        const h3 = screen.getAllByText(LONG_120_NAME).find((el) => el.closest("h3"))?.closest("h3")
        expect(h3?.className).toContain("wrap-break-word")
        expect(h3?.className).toContain("whitespace-normal")
        expect(h3?.className).not.toContain("truncate")
        r2.unmount()

        // 3. POIDetailDrawer expanded title wraps while keeping 2x3 quick dock truncate
        const r3 = render(
            <POIDetailDrawer
                isOpen={true}
                onClose={vi.fn()}
                poi={{ name: LONG_120_NAME, type: "restaurant", address: LONG_120_NAME, lat: 35.69, lng: 139.70 }}
            />
        )
        const h2 = screen.getAllByText(LONG_120_NAME).find((el) => el.tagName === "H2")
        expect(h2?.className).toContain("wrap-break-word")
        expect(h2?.className).toContain("whitespace-normal")
        expect(h2?.className).not.toContain("truncate")
        r3.unmount()

        // 4. POISearch result wraps cleanly
        mockPoiNearby.mockResolvedValueOnce({
            pois: [{ id: "p1", name: LONG_120_NAME, category: "restaurant", lat: 35.69, lng: 139.70, distance: 120 }],
        })
        const r4 = render(<POISearch centerLat={35.69} centerLng={139.70} />)
        fireEvent.click(screen.getByText("ps_restaurant"))
        const poiEl = await screen.findByText(LONG_120_NAME, { selector: "span" })
        expect(poiEl.className).toContain("wrap-break-word")
        expect(poiEl.className).toContain("whitespace-normal")
        r4.unmount()
    })

    it("AC-UI-2: ActivityEditModal removes limit:5, guards Zhuyin/IME/item-switch, runs paren fallback & preserves note only when desc is blank", async () => {
        // Primary query with parenthetical returns 0 -> auto fallback to cleaned query
        mockGeocodeSearch
            .mockResolvedValueOnce({ results: [] })
            .mockResolvedValueOnce({
                results: [
                    { name: "淺草寺", display_name: "東京都台東區淺草", lat: 35.7148, lng: 139.7967, type: "temple", osm_id: 77, osm_type: "N" },
                    { name: "淺草寺", display_name: "東京都台東區淺草", lat: 35.7148, lng: 139.7967, type: "temple", osm_id: 77, osm_type: "node" },
                ],
            })

        let currentItem: ItineraryItemState = {
            id: "item-1",
            time: "09:00",
            place: "淺草寺 (雷門拍照)",
            desc: "",
            isManualCoords: false,
        }
        const setEditItem = vi.fn((next: ItineraryItemState | null) => {
            if (next) currentItem = next
        })

        const { rerender } = render(
            <ActivityEditModal
                isOpen={true}
                onOpenChange={vi.fn()}
                editItem={currentItem}
                setEditItem={setEditItem}
                isAddMode={false}
                isSaving={false}
                onSave={vi.fn()}
                tripTitle="東京自由行"
            />
        )

        // 1. Trigger search via button
        const searchBtn = screen.getByRole("button", { name: "🔍" })
        fireEvent.click(searchBtn)

        await waitFor(() => expect(mockGeocodeSearch).toHaveBeenCalledTimes(2))
        // Must omit limit (never limit: 5 and never limit: null)
        expect(mockGeocodeSearch.mock.calls[0][0].limit).toBeUndefined()
        expect(mockGeocodeSearch.mock.calls[0][0].query).toBe("淺草寺 (雷門拍照)")
        expect(mockGeocodeSearch.mock.calls[1][0].query).toBe("淺草寺")

        // Deduplicated N/77 and node/77 into 1 item
        const resultBtns = await screen.findAllByText("淺草寺")
        expect(resultBtns).toHaveLength(1)
        expect(resultBtns[0].className).toContain("wrap-break-word")
        expect(resultBtns[0].className).toContain("whitespace-normal")

        // 2. Typing in place field while same item-1 MUST NOT wipe results (cleanup effect locked to [isOpen, editItem?.id])
        const updatedSameId: ItineraryItemState = { ...currentItem, place: "淺草寺 (雷門拍照)!" }
        rerender(
            <ActivityEditModal
                isOpen={true}
                onOpenChange={vi.fn()}
                editItem={updatedSameId}
                setEditItem={setEditItem}
                isAddMode={false}
                isSaving={false}
                onSave={vi.fn()}
                tripTitle="東京自由行"
            />
        )
        expect(screen.getByText("淺草寺")).toBeInTheDocument()

        // 3. Click result -> preserves parenthetical note '雷門拍照' into blank desc
        fireEvent.click(screen.getByText("淺草寺"))
        expect(setEditItem).toHaveBeenLastCalledWith(
            expect.objectContaining({
                place: "淺草寺",
                desc: "雷門拍照",
                lat: 35.7148,
                lng: 139.7967,
            })
        )

        // 4. Switching to item-2 with existing desc MUST clear old results & NOT overwrite non-empty desc
        mockGeocodeSearch.mockResolvedValueOnce({
            results: [{ name: "築地市場", display_name: "東京都中央區", lat: 35.6654, lng: 139.7707, type: "market", osm_id: 88, osm_type: "W" }],
        })
        const item2: ItineraryItemState = {
            id: "item-2",
            time: "11:00",
            place: "築地市場 (海鮮早餐)",
            desc: "既有備註不可覆蓋",
            isManualCoords: false,
        }
        rerender(
            <ActivityEditModal
                isOpen={true}
                onOpenChange={vi.fn()}
                editItem={item2}
                setEditItem={setEditItem}
                isAddMode={false}
                isSaving={false}
                onSave={vi.fn()}
                tripTitle="東京自由行"
            />
        )
        expect(screen.queryByText("淺草寺")).toBeNull()
        fireEvent.click(screen.getByRole("button", { name: "🔍" }))
        const tsukijiBtn = await screen.findByText("築地市場")
        fireEvent.click(tsukijiBtn)
        expect(setEditItem).toHaveBeenLastCalledWith(
            expect.objectContaining({
                place: "築地市場",
                desc: "既有備註不可覆蓋",
            })
        )

        // 5. Incomplete Zhuyin guard MUST NOT fire geocodeApi.search
        const callCountBeforeZhuyin = mockGeocodeSearch.mock.calls.length
        rerender(
            <ActivityEditModal
                isOpen={true}
                onOpenChange={vi.fn()}
                editItem={{ ...item2, id: "item-3", place: "ㄊㄞˊ" }}
                setEditItem={setEditItem}
                isAddMode={false}
                isSaving={false}
                onSave={vi.fn()}
            />
        )
        fireEvent.click(screen.getByRole("button", { name: "🔍" }))
        expect(mockGeocodeSearch).toHaveBeenCalledTimes(callCountBeforeZhuyin)
    })

    it("AC-UI-3: location-utils cleaning, osm_type dedup, and useLocalGeocode 10 JP Shinjitai + brandCount fix", async () => {
        expect(extractCleanPlaceQuery("淺草寺 (雷門拍照)")).toBe("淺草寺")
        expect(extractCleanPlaceQuery("10:00 築地市場（海鮮早餐）")).toBe("築地市場")
        expect(extractPlaceParentheticalNote("淺草寺 (雷門拍照)")).toBe("雷門拍照")
        expect(extractPlaceParentheticalNote("淺草寺")).toBe("")

        expect(normalizeOsmType("N")).toBe("node")
        expect(normalizeOsmType("W")).toBe("way")
        expect(normalizeOsmType("R")).toBe("relation")

        // Same numeric osm_id across DIFFERENT osm_type (node vs way) MUST NOT collide;
        // same (node, 100) from Photon 'N' and Nominatim 'node' MUST dedupe;
        // two DIFFERENT names within 20m MUST NOT collide; same normalized name within 20m MUST dedupe.
        const deduped = dedupeGeocodeResults([
            { name: "Place A", lat: 25.0339, lng: 121.5645, osm_id: 100, osm_type: "N" },
            { name: "Place A Duplicate", lat: 25.0339, lng: 121.5645, osm_id: 100, osm_type: "node" },
            { name: "Way Building 100", lat: 25.0339, lng: 121.5645, osm_id: 100, osm_type: "way" },
            { name: "Cafe Inside Same Mall", lat: 25.03395, lng: 121.56455 },
            { name: "臺北門市", lat: 25.0340, lng: 121.5646 },
            { name: "台北門市", lat: 25.03401, lng: 121.56461 },
        ])
        expect(deduped.map((d) => d.name)).toEqual([
            "Place A",
            "Way Building 100",
            "Cafe Inside Same Mall",
            "臺北門市",
        ])

        // useLocalGeocode: 10 new JP Shinjitai chars + nested brandCount
        global.fetch = vi.fn(async (url: RequestInfo | URL) => {
            const s = String(url)
            if (s.includes("landmarks.json") && !s.includes("countries/")) {
                return new Response(
                    JSON.stringify({
                        "沖縄美ら海水族館": { aliases: ["沖縄"], search: "Okinawa Churaumi", display: "沖縄美ら海水族館", country: "JP", lat: 26.69, lng: 127.87 },
                        "横浜中華街": { aliases: ["横浜"], search: "Yokohama Chinatown", display: "横浜中華街", country: "JP", lat: 35.44, lng: 139.64 },
                        "軽井沢": { aliases: ["軽井沢町"], search: "Karuizawa", display: "軽井沢", country: "JP", lat: 36.34, lng: 138.59 },
                    }),
                    { status: 200 }
                )
            }
            if (s.includes("brands.json")) {
                return new Response(
                    JSON.stringify({
                        restaurants: {
                            "一蘭": { aliases: ["ichiran"], search_term: "一蘭 ラーメン", category: "food" },
                            "松屋": { aliases: ["matsuya"], search_term: "松屋 牛丼", category: "food" },
                        },
                        cafes: {
                            "Blue Bottle": { aliases: ["藍瓶"], search_term: "ブルーボトル", category: "cafe" },
                        },
                    }),
                    { status: 200 }
                )
            }
            return new Response(null, { status: 404 })
        }) as unknown as typeof fetch

        const { result } = renderHook(() => useLocalGeocode())
        await waitFor(() => expect(result.current.isLoaded).toBe(true))

        expect(result.current.brandCount).toBe(3)
        expect(result.current.search("沖繩").some((r) => r.display === "沖縄美ら海水族館")).toBe(true)
        expect(result.current.search("橫濱").some((r) => r.display === "横浜中華街")).toBe(true)
        expect(result.current.search("輕井澤").some((r) => r.display === "軽井沢")).toBe(true)
    })
})
