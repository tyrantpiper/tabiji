/**
 * @vitest-environment jsdom
 */
import React from "react"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react"

const { mockFlyTo, mockFitBounds, mockGetCenter, mockGetZoom, mockGeocodeSearch, mockLocalSearch } = vi.hoisted(() => ({
    mockFlyTo: vi.fn(),
    mockFitBounds: vi.fn(),
    mockGetCenter: vi.fn(() => ({ lat: 48.1371, lng: 11.5754 })),
    mockGetZoom: vi.fn(() => 14.4),
    mockGeocodeSearch: vi.fn(),
    mockLocalSearch: vi.fn(() => []),
}))

vi.mock("maplibre-gl", () => ({
    setWorkerUrl: vi.fn(),
}))

vi.mock("react-map-gl/maplibre", () => {
    const MockMap = React.forwardRef(function MockMap(
        props: { children?: React.ReactNode },
        ref: React.ForwardedRef<unknown>
    ) {
        React.useImperativeHandle(ref, () => ({
            flyTo: mockFlyTo,
            fitBounds: mockFitBounds,
            getCenter: mockGetCenter,
            getZoom: mockGetZoom,
            getBounds: () => ({
                getWest: () => 121.4,
                getSouth: () => 24.9,
                getEast: () => 121.7,
                getNorth: () => 25.2,
            }),
            getMap: () => null,
        }))
        return <div data-testid="mock-map">{props.children}</div>
    })
    return {
        default: MockMap,
        Marker: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
        Popup: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
        Source: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
        Layer: () => null,
        NavigationControl: () => null,
        AttributionControl: () => null,
        GlobeControl: () => null,
    }
})

vi.mock("framer-motion", () => ({
    AnimatePresence: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
    motion: {
        div: ({ children, ...rest }: React.HTMLAttributes<HTMLDivElement>) => <div {...rest}>{children}</div>,
    },
}))

vi.mock("@/components/POIDetailDrawer", () => ({
    default: ({ isOpen, poi }: { isOpen: boolean; poi: { name?: string } | null }) =>
        isOpen ? <div data-testid="poi-drawer-open">{poi?.name}</div> : null,
}))

vi.mock("@/hooks/useLocalGeocode", () => ({
    useLocalGeocode: () => ({
        search: mockLocalSearch,
        isLoaded: true,
        isLoading: false,
    }),
}))

vi.mock("@/lib/api", () => ({
    API: {
        GEOCODE: "/api/geocode/search",
        POI: "/api/poi",
    },
    geocodeApi: {
        search: (...args: unknown[]) => mockGeocodeSearch(...args),
    },
}))

vi.mock("@/lib/hooks/usePoiPool", () => ({
    usePoiPool: () => ({
        pois: [],
        addPoi: vi.fn(),
        removePoi: vi.fn(),
        refresh: vi.fn(),
    }),
}))

vi.mock("@/components/MapillaryViewer", () => ({
    default: () => null,
}))

vi.mock("@/lib/mapillary", () => ({
    isMapillaryAvailable: () => false,
}))

vi.mock("@/hooks/useFlyoverController", () => ({
    useFlyoverController: () => ({
        isTouring: false,
        isOrbiting: false,
        isPaused: false,
        currentTourIndex: -1,
        currentTourPOI: null,
        startTour: vi.fn(),
        togglePauseTour: vi.fn(),
        skipToNext: vi.fn(),
        cancelFlight: vi.fn(),
    }),
}))

vi.mock("@/components/TourHudCapsule", () => ({
    TourHudCapsule: () => null,
}))

vi.mock("@/components/MapControlCapsule", () => ({
    MapControlCapsule: () => null,
}))

vi.mock("@/lib/LanguageContext", () => ({
    useLanguage: () => ({
        lang: "zh",
        t: (k: string) => k,
    }),
}))

vi.mock("sonner", () => ({
    toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

import FullscreenMapModal from "@/components/FullscreenMapModal"
import DayMap from "@/components/day-map"

describe("AC-UI-5: FullscreenMapModal Search Race-Guard, Unlimited Smart-Ranked List, Zhuyin Early Exit & Macro/POI Branching", () => {
    beforeEach(() => {
        vi.clearAllMocks()
        localStorage.clear()
        vi.useFakeTimers({ shouldAdvanceTime: true })
    })

    afterEach(() => {
        vi.useRealTimers()
    })

    it("sends real mapCenter without bbox/limit:5, renders all 8 smart-ranked results in order, and branches macro vs POI click", async () => {
        const eightResults = [
            {
                name: "Germany",
                lat: 51.1657,
                lng: 10.4515,
                type: "country",
                admin_level: 2,
                extent: [5.86, 47.27, 15.04, 55.10],
                osm_id: 51477,
                _score: 0.99,
            },
            {
                name: "France",
                lat: 46.2276,
                lng: 2.2137,
                type: "country",
                admin_level: 2,
                // Trans-oceanic >45 deg extent -> must fall back to flyTo, not fitBounds!
                extent: [-61.8, -21.4, 55.8, 51.1],
                osm_id: 2202162,
                _score: 0.92,
            },
            ...Array.from({ length: 6 }, (_, i) => ({
                name: `Cafe Spot ${i + 1}`,
                lat: 48.137 + i * 0.003,
                lng: 11.575,
                type: "cafe",
                osm_id: 9000 + i,
                _score: 0.85 - i * 0.02,
            })),
        ]
        mockGeocodeSearch.mockResolvedValueOnce({ results: eightResults })

        render(
            <FullscreenMapModal
                isOpen={true}
                onClose={vi.fn()}
                initialViewState={{ latitude: 25.0339, longitude: 121.5645, zoom: 12 }}
                activities={[]}
                tripTitle="3 Day Taipei Explorer"
            />
        )

        // Open search sheet
        fireEvent.click(screen.getByText("map_search_ai"))
        const input = screen.getByPlaceholderText("map_search_ai")

        // 1. Incomplete Zhuyin MUST NOT call geocodeApi.search, MUST NOT stick in searching/typing state, and MUST NOT flash map_no_results
        fireEvent.change(input, { target: { value: "ㄊㄞˊ" } })
        await act(async () => {
            await vi.advanceTimersByTimeAsync(400)
        })
        expect(mockGeocodeSearch).not.toHaveBeenCalled()
        expect(screen.queryByText("map_searching")).toBeNull()
        expect(screen.queryByText("map_enter_query")).toBeNull()
        expect(screen.queryByText("map_no_results")).toBeNull()

        // 2. Real query -> calls geocodeApi.search with live mapCenter (Munich), NO bbox, NO limit: 5
        fireEvent.change(input, { target: { value: "德國" } })
        await act(async () => {
            await vi.advanceTimersByTimeAsync(350)
        })

        await waitFor(() => expect(mockGeocodeSearch).toHaveBeenCalledTimes(1))
        const payload = mockGeocodeSearch.mock.calls[0][0]
        expect(payload.lat).toBeCloseTo(48.1371, 3)
        expect(payload.lng).toBeCloseTo(11.5754, 3)
        expect(payload.bbox).toBeUndefined()
        expect(payload.limit).toBeUndefined()
        expect(payload.signal).toBeInstanceOf(AbortSignal)

        // All 8 results rendered (no 5-item cap!)
        expect(await screen.findByText("Germany")).toBeInTheDocument()
        expect(screen.getByText("Cafe Spot 6")).toBeInTheDocument()

        // 3. Clicking macro country with usable extent -> fitBounds with bearing:0, pitch:0 and NO POIDetailDrawer!
        fireEvent.click(screen.getByText("Germany"))
        expect(mockFitBounds).toHaveBeenCalledWith(
            [[5.86, 47.27], [15.04, 55.10]],
            expect.objectContaining({ bearing: 0, pitch: 0 })
        )
        expect(screen.queryByTestId("poi-drawer-open")).toBeNull()

        // Selecting a result and closing search MUST NOT trigger a wasted L2 API call
        await act(async () => {
            await vi.advanceTimersByTimeAsync(400)
        })
        expect(mockGeocodeSearch).toHaveBeenCalledTimes(1)

        // 4. Reopen search and click trans-oceanic France (>45 deg extent) -> falls back to flyTo(bearing:0,pitch:0), NO drawer!
        fireEvent.click(screen.getByText("map_search_ai"))
        fireEvent.click(screen.getByText("France"))
        expect(mockFlyTo).toHaveBeenCalledWith(
            expect.objectContaining({ center: [2.2137, 46.2276], bearing: 0, pitch: 0 })
        )
        expect(screen.queryByTestId("poi-drawer-open")).toBeNull()

        // 5. Reopen search and click concrete POI -> flyTo AND opens POIDetailDrawer!
        fireEvent.click(screen.getByText("map_search_ai"))
        fireEvent.click(screen.getByText("Cafe Spot 1"))
        expect(await screen.findByTestId("poi-drawer-open")).toHaveTextContent("Cafe Spot 1")
    })

    it("aborts and discards stale slow out-of-order L2 response without overwriting newer query", async () => {
        let resolveSlow!: (val: unknown) => void
        const slowPromise = new Promise((resolve) => {
            resolveSlow = resolve
        })

        mockGeocodeSearch
            .mockImplementationOnce(() => slowPromise)
            .mockResolvedValueOnce({
                results: [{ name: "Newer Result Tokyo", lat: 35.68, lng: 139.76, type: "station", osm_id: 2 }],
            })

        render(
            <FullscreenMapModal
                isOpen={true}
                onClose={vi.fn()}
                initialViewState={{ latitude: 25.0339, longitude: 121.5645, zoom: 12 }}
                activities={[]}
            />
        )

        fireEvent.click(screen.getByText("map_search_ai"))
        const input = screen.getByPlaceholderText("map_search_ai")

        fireEvent.change(input, { target: { value: "Slow Query" } })
        await act(async () => {
            await vi.advanceTimersByTimeAsync(350)
        })
        expect(mockGeocodeSearch).toHaveBeenCalledTimes(1)
        const firstSignal = mockGeocodeSearch.mock.calls[0][0].signal as AbortSignal
        expect(firstSignal.aborted).toBe(false)

        // Newer query fires -> must abort first signal
        fireEvent.change(input, { target: { value: "Tokyo Station" } })
        await act(async () => {
            await vi.advanceTimersByTimeAsync(350)
        })
        expect(firstSignal.aborted).toBe(true)
        expect(await screen.findByText("Newer Result Tokyo")).toBeInTheDocument()

        // Late resolution of slow first promise MUST NOT overwrite newer result
        await act(async () => {
            resolveSlow({
                results: [{ name: "Stale Slow Ghost", lat: 10, lng: 10, type: "cafe", osm_id: 1 }],
            })
        })
        expect(screen.queryByText("Stale Slow Ghost")).toBeNull()
        expect(screen.getByText("Newer Result Tokyo")).toBeInTheDocument()
    })

    it("mounts DayMap directly: Zhuyin early-exit, real mapCenter without bbox/limit:5, unlimited list, macro/POI split & abort race guard", async () => {
        const eightResults = [
            {
                name: "Germany",
                lat: 51.1657,
                lng: 10.4515,
                type: "country",
                admin_level: 2,
                extent: [5.86, 47.27, 15.04, 55.10],
                osm_id: 51477,
                _score: 0.99,
            },
            ...Array.from({ length: 7 }, (_, i) => ({
                name: `DayMap Cafe ${i + 1}`,
                lat: 48.137 + i * 0.003,
                lng: 11.575,
                type: "cafe",
                osm_id: 7000 + i,
                _score: 0.85 - i * 0.02,
            })),
        ]

        let resolveSlow!: (val: unknown) => void
        const slowPromise = new Promise((resolve) => {
            resolveSlow = resolve
        })

        mockGeocodeSearch
            .mockImplementationOnce(() => slowPromise)
            .mockResolvedValueOnce({ results: eightResults })

        render(
            <DayMap
                activities={[]}
                dailyLoc={{ name: "Taipei", lat: 25.0339, lng: 121.5645 }}
                tripTitle="3 Day Taipei Explorer"
            />
        )

        // Open DayMap search overlay
        fireEvent.click(screen.getByTitle("map_search"))
        const input = screen.getByPlaceholderText("map_search_placeholder")

        // 1. Incomplete Zhuyin -> NO API call, NO stuck spinner, NO false map_no_results flash
        fireEvent.change(input, { target: { value: "ㄊㄞˊ" } })
        await act(async () => {
            await vi.advanceTimersByTimeAsync(400)
        })
        expect(mockGeocodeSearch).not.toHaveBeenCalled()
        expect(screen.queryByText("map_searching")).toBeNull()
        expect(screen.queryByText("map_no_results")).toBeNull()

        // 2. Start slow L2 query, then type a newer query while slow is in-flight
        fireEvent.change(input, { target: { value: "Slow Munich" } })
        await act(async () => {
            await vi.advanceTimersByTimeAsync(350)
        })
        expect(mockGeocodeSearch).toHaveBeenCalledTimes(1)
        const firstSignal = mockGeocodeSearch.mock.calls[0][0].signal as AbortSignal
        expect(firstSignal.aborted).toBe(false)

        // Typing newer query must immediately abort slow request and clear stale searching spinner during debounce
        fireEvent.change(input, { target: { value: "德國" } })
        expect(firstSignal.aborted).toBe(true)
        expect(screen.queryByText("map_searching")).toBeNull()

        await act(async () => {
            await vi.advanceTimersByTimeAsync(350)
        })
        await waitFor(() => expect(mockGeocodeSearch).toHaveBeenCalledTimes(2))
        const secondPayload = mockGeocodeSearch.mock.calls[1][0]
        expect(secondPayload.lat).toBeCloseTo(48.1371, 3)
        expect(secondPayload.lng).toBeCloseTo(11.5754, 3)
        expect(secondPayload.bbox).toBeUndefined()
        expect(secondPayload.limit).toBeUndefined()

        // Late slow response MUST NOT overwrite newer 8 results
        await act(async () => {
            resolveSlow({ results: [{ name: "DayMap Stale Ghost", lat: 10, lng: 10, type: "cafe", osm_id: 99 }] })
        })
        expect(await screen.findByText("Germany")).toBeInTheDocument()
        expect(screen.getByText("DayMap Cafe 7")).toBeInTheDocument()
        expect(screen.queryByText("DayMap Stale Ghost")).toBeNull()

        // 3. Click macro Germany -> fitBounds(bearing:0, pitch:0) and NO POIDetailDrawer
        fireEvent.click(screen.getByText("Germany"))
        expect(mockFitBounds).toHaveBeenCalledWith(
            [[5.86, 47.27], [15.04, 55.10]],
            expect.objectContaining({ bearing: 0, pitch: 0 })
        )
        expect(screen.queryByTestId("poi-drawer-open")).toBeNull()

        // 4. Reopen search WITHOUT editing query -> MUST NOT trigger a redundant L2 API call or flash map_no_results
        fireEvent.click(screen.getByTitle("map_search"))
        await act(async () => {
            await vi.advanceTimersByTimeAsync(400)
        })
        expect(mockGeocodeSearch).toHaveBeenCalledTimes(2)
        expect(screen.queryByText("map_no_results")).toBeNull()

        // 5. Typing a new query searches normally and clicking concrete POI opens POIDetailDrawer
        mockGeocodeSearch.mockResolvedValueOnce({ results: eightResults })
        const input2 = screen.getByPlaceholderText("map_search_placeholder")
        fireEvent.change(input2, { target: { value: "Cafe" } })
        await act(async () => {
            await vi.advanceTimersByTimeAsync(350)
        })
        fireEvent.click(await screen.findByText("DayMap Cafe 1"))
        expect(await screen.findByTestId("poi-drawer-open")).toHaveTextContent("DayMap Cafe 1")
    })

    it("FullscreenMapModal: selecting a history item and reopening search MUST NOT trigger wasted L2 call or flash map_no_results", async () => {
        localStorage.setItem(
            "map_search_history",
            JSON.stringify([{ name: "Barcelona", lat: 41.387, lng: 2.169, type: "city", osm_id: 347950 }])
        )
        render(
            <FullscreenMapModal
                isOpen={true}
                onClose={vi.fn()}
                initialViewState={{ latitude: 25.0339, longitude: 121.5645, zoom: 12 }}
                activities={[]}
            />
        )

        fireEvent.click(screen.getByText("map_search_ai"))
        fireEvent.click(await screen.findByText("Barcelona"))
        expect(mockFlyTo).toHaveBeenCalledWith(expect.objectContaining({ center: [2.169, 41.387], bearing: 0, pitch: 0 }))

        // Reopen search with query="Barcelona" and results=[] -> MUST NOT call API and MUST NOT flash map_no_results!
        fireEvent.click(screen.getByText("map_search_ai"))
        await act(async () => {
            await vi.advanceTimersByTimeAsync(400)
        })
        expect(mockGeocodeSearch).not.toHaveBeenCalled()
        expect(screen.queryByText("map_no_results")).toBeNull()
    })
})
