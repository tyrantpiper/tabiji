import React from "react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import {
    isMapNavigationUrl,
    isSafeHttpUrl,
    splitNavigationAndMemoLinks,
} from "@/lib/location-utils"

const mockCreateItem = vi.fn().mockResolvedValue({ status: "success", data: [{ id: "new-item-1" }] })
const mockResolveLink = vi.fn()
const mockOpenExternalLink = vi.fn()
const mockToastInfo = vi.fn()
const mockToastSuccess = vi.fn()
const mockToastError = vi.fn()

vi.mock("@/lib/api", async () => {
    const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
    return {
        ...actual,
        itemsApi: {
            ...actual.itemsApi,
            create: (...args: unknown[]) => mockCreateItem(...args),
        },
        poiApi: {
            ...actual.poiApi,
            enrich: vi.fn().mockResolvedValue(null),
        },
        geocodeApi: {
            ...actual.geocodeApi,
            resolveLink: (...args: unknown[]) => mockResolveLink(...args),
        },
    }
})

vi.mock("@/lib/utils", async () => {
    const actual = await vi.importActual<typeof import("@/lib/utils")>("@/lib/utils")
    return {
        ...actual,
        openExternalLink: (...args: unknown[]) => mockOpenExternalLink(...args),
    }
})

vi.mock("@/lib/trip-context", () => ({
    useTripContext: () => ({
        activeTripId: "trip-taipei-1",
        activeTrip: { id: "trip-taipei-1", title: "3 Day Taipei Explorer ✨", total_days: 3, start_date: "2026-10-11" },
        mutate: vi.fn(),
        userId: "user-123",
    }),
}))

vi.mock("@/lib/hooks/useTripRealtime", () => ({
    broadcastTripEvent: vi.fn().mockResolvedValue(undefined),
}))

vi.mock("@/lib/LanguageContext", () => ({
    useLanguage: () => ({
        t: (k: string) => k,
        lang: "zh",
        isReady: true,
    }),
}))

vi.mock("sonner", () => ({
    toast: {
        info: (...args: unknown[]) => mockToastInfo(...args),
        success: (...args: unknown[]) => mockToastSuccess(...args),
        error: (...args: unknown[]) => mockToastError(...args),
    },
}))

vi.mock("@/lib/mapillary", () => ({
    searchNearbyImage: vi.fn().mockResolvedValue(null),
    uploadMapillaryToCloudinary: vi.fn().mockResolvedValue(null),
}))

vi.mock("@/components/poi-search", () => ({
    POISearch: ({ onSelectPOI }: { onSelectPOI: (poi: { name: string; lat: number; lng: number; website?: string; opening_hours?: string }) => void }) => (
        <button
            type="button"
            data-testid="mock-poi-select"
            onClick={() =>
                onSelectPOI({
                    name: "北海 -HOKKAI- お初天神店",
                    lat: 34.7024,
                    lng: 135.5002,
                    website: "https://www.instagram.com/reel/Dd-M_DVvHWP/",
                })
            }
        >
            Select Mock POI
        </button>
    ),
}))

import POIPreviewCard, { parseRawPoiArgs } from "@/components/chat/POIPreviewCard"
import BatchPOIPreviewCard from "@/components/chat/BatchPOIPreviewCard"
import { TimelineCard } from "@/components/timeline-card"
import { ActivityEditModal } from "@/components/itinerary/ActivityEditModal"
import type { Activity, ItineraryItemState } from "@/lib/itinerary-types"

describe("Bug 1 & Bug 2: Map Navigation URL Whitelist, Memo Link Routing & Coordinate Preservation", () => {
    beforeEach(() => {
        vi.clearAllMocks()
    })

    describe("isMapNavigationUrl & splitNavigationAndMemoLinks", () => {
        it("accepts Google, Apple, OSM, Naver, Kakao, Yahoo JP, Bing Maps, Amap, Baidu, Waze URLs", () => {
            const validMapUrls = [
                "https://maps.app.goo.gl/abc123",
                "https://goo.gl/maps/abc123",
                "https://www.google.com/maps/place/Tokyo/@35.68,139.76,17z",
                "https://www.google.co.jp/maps/search/?api=1&query=Osaka",
                "https://maps.google.com.tw/?q=34.7024,135.5002",
                "https://maps.apple.com/?ll=34.7024,135.5002",
                "https://www.openstreetmap.org/?mlat=34.7024&mlon=135.5002",
                "https://osm.org/go/7P52",
                "https://map.naver.com/p/entry/place/12345",
                "https://naver.me/abcdef",
                "https://map.kakao.com/link/map/12345",
                "https://kko.to/abcdef",
                "https://map.yahoo.co.jp/place?gid=123",
                "https://www.bing.com/maps?cp=34.7024~135.5002",
                "https://ditu.amap.com/place/B000A83M61",
                "https://map.baidu.com/@13525210,3640150,15z",
                "https://www.waze.com/ul?ll=34.7024,135.5002",
            ]
            for (const url of validMapUrls) {
                expect(isMapNavigationUrl(url), `expected map URL: ${url}`).toBe(true)
            }
        })

        it("rejects Instagram, Threads, websites, non-map google/goo.gl links, spoofed domains, and javascript: XSS", () => {
            const invalidUrls = [
                "https://www.instagram.com/reel/Dd-M_DVvHWP/",
                "https://www.threads.net/@tabiji/post/123",
                "https://www.senso-ji.jp/",
                "https://www.google.com/search?q=osaka",
                "https://goo.gl/forms/abc",
                "https://maps.google.com.evil.com/maps",
                "https://maps.google.com@evil.com/maps",
                "https://evil.com/maps.google.com",
                "javascript:alert(1)",
                "data:text/html,<script>alert(1)</script>",
                "",
                null,
                undefined,
            ]
            for (const url of invalidUrls) {
                expect(isMapNavigationUrl(url), `expected non-map URL: ${String(url)}`).toBe(false)
            }
            expect(isSafeHttpUrl("javascript:alert(1)")).toBe(false)
            expect(isSafeHttpUrl("https://www.instagram.com/reel/Dd-M_DVvHWP/")).toBe(true)
        })

        it("splits IG link from link_url into sub_items & website_link without duplicating existing links", () => {
            const ig = "https://www.instagram.com/reel/Dd-M_DVvHWP/"
            const res = splitNavigationAndMemoLinks(ig, undefined, [{ name: "全60種 寿司食べ放題" }], true)
            expect(res.link_url).toBeUndefined()
            expect(res.website_link).toBe(ig)
            expect(res.sub_items).toEqual([
                { name: "全60種 寿司食べ放題" },
                { name: "Instagram 參考連結", link: ig },
            ])

            // Re-running is idempotent and does not duplicate
            const res2 = splitNavigationAndMemoLinks(res.link_url, res.website_link, res.sub_items, true)
            expect(res2.sub_items).toHaveLength(2)

            // Preserves Google Maps link_url while still syncing website_link to sub_items
            const gmaps = "https://maps.app.goo.gl/abc123"
            const res3 = splitNavigationAndMemoLinks(gmaps, ig, [], true)
            expect(res3.link_url).toBe(gmaps)
            expect(res3.website_link).toBe(ig)
            expect(res3.sub_items).toEqual([{ name: "Instagram 參考連結", link: ig }])
        })
    })

    describe("POIPreviewCard & BatchPOIPreviewCard", () => {
        it("sends preserve_coords: true, link_url: undefined, and routes IG link into sub_items & website_link", async () => {
            const ig = "https://www.instagram.com/reel/Dd-M_DVvHWP/"
            const parsed = parseRawPoiArgs({
                place_name: "北海 -HOKKAI- お初天神店",
                category: "restaurant",
                desc: "大阪超人氣壽司吃到飽",
                lat: 34.7024,
                lng: 135.5002,
                day: 1,
                time_slot: "18:00",
                link_url: ig,
                sub_items: [{ name: "全60種 寿司食べ放題コース" }],
            })

            render(<POIPreviewCard poiData={parsed} />)
            fireEvent.click(screen.getByRole("button", { name: /加入行程/ }))

            await waitFor(() => {
                expect(mockCreateItem).toHaveBeenCalledTimes(1)
            })
            expect(mockCreateItem).toHaveBeenCalledWith(
                expect.objectContaining({
                    place: "北海 -HOKKAI- お初天神店",
                    lat: 34.7024,
                    lng: 135.5002,
                    preserve_coords: true,
                    link_url: undefined,
                    website_link: ig,
                    sub_items: [
                        { name: "全60種 寿司食べ放題コース", desc: undefined, link: undefined },
                        { name: "Instagram 參考連結", link: ig },
                    ],
                })
            )
        })

        it("BatchPOIPreviewCard routes IG link into sub_items & sends preserve_coords: true", async () => {
            const ig = "https://www.instagram.com/reel/Dd-M_DVvHWP/"
            render(
                <BatchPOIPreviewCard
                    items={[
                        {
                            place_name: "北海 -HOKKAI- お初天神店",
                            category: "restaurant",
                            desc: "大阪壽司",
                            lat: 34.7024,
                            lng: 135.5002,
                            day_number: 1,
                            time_slot: "18:00",
                            link_url: ig,
                        },
                    ]}
                />
            )

            fireEvent.click(screen.getByRole("button", { name: /全部加入行程/ }))

            await waitFor(() => {
                expect(mockCreateItem).toHaveBeenCalledTimes(1)
            })
            expect(mockCreateItem).toHaveBeenCalledWith(
                expect.objectContaining({
                    lat: 34.7024,
                    lng: 135.5002,
                    preserve_coords: true,
                    link_url: undefined,
                    website_link: ig,
                    sub_items: [{ name: "Instagram 參考連結", link: ig }],
                })
            )
        })
    })

    describe("TimelineCard Navigation Guard (Legacy Polluted Data)", () => {
        it("falls back to Google Maps coordinates instead of opening Instagram when legacy link_url holds IG URL", () => {
            const pollutedActivity: Activity = {
                id: "act-legacy-ig",
                day_number: 1,
                time_slot: "18:00",
                time: "18:00",
                place: "北海 -HOKKAI- お初天神店",
                category: "restaurant",
                lat: 34.7024,
                lng: 135.5002,
                link_url: "https://www.instagram.com/reel/Dd-M_DVvHWP/",
            }

            render(
                <TimelineCard
                    activity={pollutedActivity}
                    index={1}
                    onEdit={vi.fn()}
                    onDelete={vi.fn()}
                    onUpdateActivity={vi.fn().mockResolvedValue(true)}
                />
            )

            fireEvent.click(screen.getByRole("button", { name: /tc_navigate/ }))
            expect(mockOpenExternalLink).toHaveBeenCalledTimes(1)
            expect(mockOpenExternalLink).toHaveBeenCalledWith(
                "https://www.google.com/maps/search/?api=1&query=34.7024%2C135.5002"
            )
        })

        it("opens valid map navigation link_url directly when clicking Navigate", () => {
            const cleanActivity: Activity = {
                id: "act-clean-map",
                day_number: 1,
                time_slot: "18:00",
                time: "18:00",
                place: "北海 -HOKKAI- お初天神店",
                category: "restaurant",
                lat: 34.7024,
                lng: 135.5002,
                link_url: "https://maps.app.goo.gl/OsakaHokkai123",
            }

            render(
                <TimelineCard
                    activity={cleanActivity}
                    index={1}
                    onEdit={vi.fn()}
                    onDelete={vi.fn()}
                    onUpdateActivity={vi.fn().mockResolvedValue(true)}
                />
            )

            fireEvent.click(screen.getByRole("button", { name: /tc_navigate/ }))
            expect(mockOpenExternalLink).toHaveBeenCalledWith("https://maps.app.goo.gl/OsakaHokkai123")
        })
    })

    describe("ActivityEditModal Navigation URL & Nearby POI Guards", () => {
        it("warns on non-map link_url and blocks resolveLink API call, and routes nearby POI website to sub_items/website_link", () => {
            const setEditItem = vi.fn()
            const initialItem: ItineraryItemState = {
                id: "act-edit-1",
                time: "18:00",
                place: "北海 -HOKKAI- お初天神店",
                desc: "大阪壽司",
                lat: 34.7024,
                lng: 135.5002,
                link_url: "https://www.instagram.com/reel/Dd-M_DVvHWP/",
                isManualCoords: false,
            }

            render(
                <ActivityEditModal
                    isOpen={true}
                    onOpenChange={vi.fn()}
                    editItem={initialItem}
                    setEditItem={setEditItem}
                    isAddMode={false}
                    isSaving={false}
                    onSave={vi.fn()}
                />
            )

            // Warning text shown for non-map URL in Navigation URL field
            expect(screen.getByText(/導航網址僅限地圖連結/)).toBeInTheDocument()

            // Clicking Resolve shows toast and does NOT call backend resolveLink
            fireEvent.click(screen.getByRole("button", { name: "解析" }))
            expect(mockResolveLink).not.toHaveBeenCalled()
            expect(mockToastInfo).toHaveBeenCalledWith(expect.stringContaining("此地備忘錄"))

            // Opening Nearby POI explorer and selecting a POI with IG website routes website to website_link & sub_items
            fireEvent.click(screen.getByRole("button", { name: /周邊探索/ }))
            fireEvent.click(screen.getByTestId("mock-poi-select"))

            const lastCall = setEditItem.mock.calls[setEditItem.mock.calls.length - 1][0] as ItineraryItemState
            expect(lastCall.link_url).toContain("https://www.google.com/maps/search/?api=1&query=")
            expect(lastCall.website_link).toBe("https://www.instagram.com/reel/Dd-M_DVvHWP/")
            expect(lastCall.sub_items).toEqual([
                { name: "Instagram 參考連結", link: "https://www.instagram.com/reel/Dd-M_DVvHWP/" },
            ])
        })
    })
})
