import React from "react"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen, fireEvent, waitFor, renderHook, act } from "@testing-library/react"
import { toast } from "sonner"

// Hoisted mocks for clean isolation across tests
const mockGetCachedToken = vi.fn<() => string | null>(() => "jwt-token-initial")
const mockEnsureValidSession = vi.fn<(force?: boolean) => Promise<string | null>>(async () => "jwt-token-refreshed")
const mockSyncEnqueue = vi.fn(async () => undefined)
const mockTripMutate = vi.fn(async () => undefined)
const mockReloadTripDetail = vi.fn(async () => undefined)

let mockTripContextValue: Record<string, unknown> = {}
let mockTripDetailValue: Record<string, unknown> = {}

vi.mock("sonner", () => ({
    toast: {
        success: vi.fn(),
        error: vi.fn(),
        info: vi.fn(),
    },
}))

vi.mock("next/image", () => ({
    default: (props: Record<string, unknown>) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={String(props.src || "")} alt={String(props.alt || "")} />
    ),
}))

vi.mock("@/lib/auth-session", () => ({
    getCachedToken: () => mockGetCachedToken(),
    ensureValidSession: (force?: boolean) => mockEnsureValidSession(force),
    getLastAuthExchangeError: () => null,
    triggerReauthPrompt: vi.fn(),
    wasLastAuthExchangeTransientFailure: () => false,
}))

vi.mock("@/lib/sync-engine", () => ({
    SyncQueue: {
        enqueue: (...args: unknown[]) => mockSyncEnqueue(...(args as [])),
        peek: vi.fn(async () => []),
        dequeue: vi.fn(async () => undefined),
        incrementRetry: vi.fn(async () => undefined),
    },
    MAX_RETRIES: 3,
    SyncEngineControl: {
        isPaused: () => false,
        pause: vi.fn(),
    },
}))

vi.mock("@/lib/LanguageContext", () => ({
    useLanguage: () => ({
        t: (key: string) => key,
        lang: "zh",
    }),
}))

vi.mock("@/lib/trip-context", () => ({
    useTripContext: () => mockTripContextValue,
}))

const EMPTY_EXPENSES: never[] = []
const mockExpensesMutate = vi.fn()
const mockHaptic = { tap: vi.fn(), success: vi.fn(), error: vi.fn() }

vi.mock("react-virtuoso", () => ({
    Virtuoso: ({ data = [], itemContent }: { data?: unknown[]; itemContent?: (i: number, item: unknown) => React.ReactNode }) => (
        <div data-testid="virtuoso">{data.map((item, i) => <div key={i}>{itemContent?.(i, item)}</div>)}</div>
    ),
}))

vi.mock("@/lib/hooks", () => ({
    useExpenses: () => ({ expenses: EMPTY_EXPENSES, mutate: mockExpensesMutate, isLoading: false }),
    useHaptic: () => mockHaptic,
    useTripDetail: () => mockTripDetailValue,
}))

vi.mock("@/lib/hooks/useTripRealtime", () => ({
    broadcastTripEvent: vi.fn(async () => undefined),
}))

vi.mock("@/lib/idb-storage", () => ({
    saveTripSnapshot: vi.fn(async () => undefined),
}))

vi.mock("@/lib/stores/tripStore", () => ({
    useTargetExpenseId: () => null,
    useTripStore: (selector: (s: Record<string, unknown>) => unknown) =>
        selector({ setTargetExpenseId: vi.fn() }),
}))

vi.mock("@/lib/stores/syncStatusStore", () => ({
    useSyncStatusStore: Object.assign(
        (selector?: (s: Record<string, unknown>) => unknown) => {
            const state = {
                isOnline: true,
                pendingCount: 0,
                updateStatus: vi.fn(),
                setIsOnline: vi.fn(),
            }
            return selector ? selector(state) : state
        },
        {
            getState: () => ({
                updateStatus: vi.fn(),
                setIsOnline: vi.fn(),
            }),
        }
    ),
}))

vi.mock("@/components/trip-switcher", () => ({
    TripSwitcher: () => <div data-testid="trip-switcher" />,
}))

vi.mock("@/components/expense-chart", () => ({
    ExpenseChart: () => <div data-testid="expense-chart" />,
    CATEGORY_COLORS: { general: "#64748b" },
}))

vi.mock("@/components/expense-dialog", () => ({
    ExpenseDialog: () => null,
}))

vi.mock("@/components/tools/GlobalTaxActuary", () => ({
    GlobalTaxActuary: () => null,
}))

vi.mock("@/components/ActuaryDialogCard", () => ({
    ActuaryDialogCard: () => null,
}))

vi.mock("@/components/ui/SyncStatusBadge", () => ({
    SyncStatusBadge: () => null,
}))

vi.mock("@/components/ui/image-upload", () => ({
    ImageUpload: () => <div data-testid="image-upload" />,
}))

vi.mock("@/components/views/info/FlightCard", () => ({
    FlightCard: () => <div data-testid="flight-card" />,
}))

vi.mock("@/components/views/info/BookingTab", () => ({
    BookingTab: () => <div data-testid="booking-tab" />,
}))

vi.mock("@/lib/security", () => ({
    encryptData: (s: string) => `enc:${s}`,
    decryptData: (s: string | null) => (s && s.startsWith("enc:") ? s.slice(4) : s),
    getSecureApiKey: () => "",
}))

import { tripsApi } from "@/lib/api"
import { useOfflineMutation } from "@/lib/sync-hooks"
import { ToolsView } from "@/components/views/tools-view"
import { InfoView } from "@/components/views/info-view"

const TRIP_ID = "33333333-3333-4333-8333-333333333333"
const USER_ID = "11111111-1111-4111-8111-111111111111"

describe("Frontend P0 Atomic Info/Cards & Offline Auth Sentinel", () => {
    const origFetch = global.fetch

    beforeEach(() => {
        vi.clearAllMocks()
        localStorage.clear()
        localStorage.setItem("user_uuid", USER_ID)
        mockGetCachedToken.mockReturnValue("jwt-token-initial")
        mockEnsureValidSession.mockResolvedValue("jwt-token-refreshed")
        Object.defineProperty(navigator, "onLine", { value: true, configurable: true })

        mockTripContextValue = {
            activeTripId: TRIP_ID,
            activeTrip: {
                id: TRIP_ID,
                title: "Tokyo Trip",
                credit_cards: [
                    { id: "existing-card", name: "Existing Shared Card", rewardRate: 3, rewardLimit: 1000, notes: "", is_public: true, creator_id: USER_ID },
                ],
                start_date: "2026-12-01",
                end_date: "2026-12-03",
            },
            mutate: mockTripMutate,
            userId: USER_ID,
        }

        mockTripDetailValue = {
            trip: {
                id: TRIP_ID,
                title: "Tokyo Trip",
                flight_info: { outbound: [], inbound: [] },
                hotel_info: [
                    {
                        name: "Shinjuku Prince Hotel",
                        address: "Kabukicho, Shinjuku",
                        booking_id: "BK123",
                        check_in: "15:00",
                        check_out: "11:00",
                        phone: "03-3205-1111",
                        memo: "Original Hotel Memo",
                        image_url: "",
                        link_url: "",
                        hide_navigation: false,
                        lat: 35.694,
                        lng: 139.700,
                        links: [],
                    },
                ],
            },
            mutate: mockReloadTripDetail,
        }
    })

    afterEach(() => {
        global.fetch = origFetch
        vi.restoreAllMocks()
    })

    it("test_benign_updateInfo_online_succeeds_with_bearer_jwt", async () => {
        const fetchMock = vi.fn(async () =>
            new Response(JSON.stringify({ status: "success" }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
            })
        )
        global.fetch = fetchMock as unknown as typeof fetch

        const res = await tripsApi.updateInfo(TRIP_ID, { credit_cards: [] }, USER_ID)
        expect(res).toEqual({ status: "success" })
        expect(fetchMock).toHaveBeenCalledTimes(1)
        const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
        const headers = init.headers as Record<string, string>
        expect(headers.Authorization).toBe("Bearer jwt-token-initial")
    })

    it("test_poc_api_updateInfo_uses_offlineFetch_with_idempotency_and_offline_queue", async () => {
        // 1. Online call must include Idempotency-Key + Authorization Bearer
        const fetchMock = vi.fn(async () =>
            new Response(JSON.stringify({ status: "success" }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
            })
        )
        global.fetch = fetchMock as unknown as typeof fetch

        await tripsApi.updateInfo(TRIP_ID, { credit_cards: [{ id: "c1", name: "JCB" }] }, USER_ID)
        const [, onlineInit] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
        const onlineHeaders = onlineInit.headers as Record<string, string>
        expect(onlineHeaders["Idempotency-Key"]).toBeTruthy()
        expect(onlineHeaders["Authorization"]).toBe("Bearer jwt-token-initial")

        // 2. Offline call must enqueue into SyncQueue and return { status: 'queued', offline: true }
        Object.defineProperty(navigator, "onLine", { value: false, configurable: true })
        const queuedRes = await tripsApi.updateInfo(TRIP_ID, { credit_cards: [{ id: "c2", name: "Offline Card" }] }, USER_ID)
        expect(queuedRes).toMatchObject({ status: "queued", offline: true })
        expect(mockSyncEnqueue).toHaveBeenCalledTimes(1)

        // 3. Lie-Fi network rejection must also enqueue into SyncQueue
        Object.defineProperty(navigator, "onLine", { value: true, configurable: true })
        global.fetch = vi.fn(async () => {
            throw new TypeError("Failed to fetch")
        }) as unknown as typeof fetch
        const lieFiRes = await tripsApi.updateInfo(TRIP_ID, { credit_cards: [{ id: "c3", name: "LieFi Card" }] }, USER_ID)
        expect(lieFiRes).toMatchObject({ status: "queued", offline: true })
        expect(mockSyncEnqueue).toHaveBeenCalledTimes(2)

        // 4. HTTP 409 Conflict must throw error with status 409 and NOT enqueue
        global.fetch = vi.fn(async () =>
            new Response(JSON.stringify({ detail: "行程正由旅伴同步編輯中，請稍候重試" }), {
                status: 409,
                headers: { "Content-Type": "application/json" },
            })
        ) as unknown as typeof fetch
        await expect(tripsApi.updateInfo(TRIP_ID, { credit_cards: [] }, USER_ID)).rejects.toMatchObject({
            status: 409,
        })
        expect(mockSyncEnqueue).toHaveBeenCalledTimes(2)
    })

    it("test_poc_sync_hooks_useOfflineMutation_injects_jwt_and_retries_401", async () => {
        const fetchMock = vi
            .fn()
            .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Expired" }), { status: 401 }))
            .mockResolvedValueOnce(new Response(JSON.stringify({ status: "success" }), { status: 200 }))
        global.fetch = fetchMock as unknown as typeof fetch

        const { result } = renderHook(() => useOfflineMutation())
        let response: Response | { ok: boolean } | undefined
        await act(async () => {
            response = await result.current.mutate(`/api/trips/${TRIP_ID}/info`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json", "X-User-ID": USER_ID },
                body: JSON.stringify({ credit_cards: [] }),
            })
        })

        expect(fetchMock).toHaveBeenCalledTimes(2)
        const firstHeaders = new Headers((fetchMock.mock.calls[0][1] as RequestInit).headers)
        const secondHeaders = new Headers((fetchMock.mock.calls[1][1] as RequestInit).headers)
        expect(firstHeaders.get("Authorization")).toBe("Bearer jwt-token-initial")
        expect(mockEnsureValidSession).toHaveBeenCalledWith(true)
        expect(secondHeaders.get("Authorization")).toBe("Bearer jwt-token-refreshed")
        expect((response as Response).ok).toBe(true)
    })

    it("test_poc_tools_view_uses_tripsApi_updateInfo_rolls_back_on_error_and_handles_offline_and_no_trip", async () => {
        // Seed a legacy local card so we can verify localStorage is NOT cleared on remote failure
        localStorage.setItem(
            "credit_cards",
            `enc:${JSON.stringify([{ id: "legacy-local-1", name: "Legacy Local", rewardRate: 2, rewardLimit: 500, notes: "", is_public: false }])}`
        )

        const updateInfoSpy = vi.spyOn(tripsApi, "updateInfo")

        // Case 1: Remote save fails (401/409) -> rolls back sharedCards, keeps localStorage, fires toast.error (NOT success!)
        updateInfoSpy.mockRejectedValueOnce(Object.assign(new Error("Unauthorized"), { status: 401 }))

        const { unmount } = render(<ToolsView />)

        // Switch to Cards tab
        fireEvent.click(screen.getByText("tv_cards"))

        // Open add card dialog
        const addBtn = await screen.findByText("tv_add_card")
        fireEvent.click(addBtn)

        const nameInput = await screen.findByPlaceholderText("tv_card_name_ph")
        fireEvent.change(nameInput, { target: { value: "Broken Save Card" } })

        const submitButtons = screen.getAllByText("tv_add_card")
        fireEvent.click(submitButtons[submitButtons.length - 1])

        await waitFor(() => {
            expect(updateInfoSpy).toHaveBeenCalledTimes(1)
            expect(toast.error).toHaveBeenCalledWith("tv_card_save_failed")
        })
        expect(toast.success).not.toHaveBeenCalled()
        // Optimistic card must be rolled back (not rendered)
        expect(screen.queryByText("Broken Save Card")).toBeNull()
        // Local storage must NOT have been wiped prematurely
        expect(localStorage.getItem("credit_cards")).toContain("legacy-local-1")

        // Case 2: Offline queued ({ offline: true }) -> MUST NOT call tripMutate() so optimistic card survives!
        vi.clearAllMocks()
        updateInfoSpy.mockResolvedValueOnce({ status: "queued", offline: true })
        fireEvent.change(nameInput, { target: { value: "Offline Queued Card" } })
        const submitButtons2 = screen.getAllByText("tv_add_card")
        fireEvent.click(submitButtons2[submitButtons2.length - 1])

        await waitFor(() => {
            expect(updateInfoSpy).toHaveBeenCalledTimes(1)
            expect(toast.success).toHaveBeenCalled()
        })
        expect(mockTripMutate).not.toHaveBeenCalled()
        expect(screen.getByText("Offline Queued Card")).toBeTruthy()
        unmount()

        // Case 3: No active trip (!activeTripId) -> private card MUST persist to localStorage
        vi.clearAllMocks()
        localStorage.removeItem("credit_cards")
        mockTripContextValue = {
            activeTripId: null,
            activeTrip: null,
            mutate: mockTripMutate,
            userId: USER_ID,
        }
        render(<ToolsView />)
        fireEvent.click(screen.getByText("tv_cards"))
        fireEvent.click(await screen.findByText("tv_add_card"))
        const nameInputNoTrip = await screen.findByPlaceholderText("tv_card_name_ph")
        fireEvent.change(nameInputNoTrip, { target: { value: "Local Private Card" } })
        const submitButtons3 = screen.getAllByText("tv_add_card")
        fireEvent.click(submitButtons3[submitButtons3.length - 1])

        await waitFor(() => {
            expect(toast.success).toHaveBeenCalledWith("tv_card_saved_private")
        })
        expect(updateInfoSpy).not.toHaveBeenCalled()
        const savedLocal = localStorage.getItem("credit_cards") || ""
        expect(savedLocal).toContain("Local Private Card")
    })

    it("test_poc_tools_view_delete_card_rolls_back_on_error_and_revalidates", async () => {
        const updateInfoSpy = vi.spyOn(tripsApi, "updateInfo")
        updateInfoSpy.mockRejectedValueOnce(Object.assign(new Error("Conflict"), { status: 409 }))

        render(<ToolsView />)
        fireEvent.click(screen.getByText("tv_cards"))

        // Existing shared card is visible
        expect(await screen.findByText("Existing Shared Card")).toBeTruthy()

        // Trigger delete -> confirm AlertDialog
        fireEvent.click(screen.getByLabelText("tv_delete_card"))
        const deleteConfirmBtn = await screen.findByText("delete")
        fireEvent.click(deleteConfirmBtn)

        await waitFor(() => {
            expect(updateInfoSpy).toHaveBeenCalledTimes(1)
            expect(toast.error).toHaveBeenCalledWith("tv_card_delete_failed")
        })
        expect(toast.success).not.toHaveBeenCalled()
        // Rolled back: card still visible and tripMutate triggered for self-healing
        expect(screen.getByText("Existing Shared Card")).toBeTruthy()
        expect(mockTripMutate).toHaveBeenCalled()
    })

    it("test_poc_info_view_handleSaveInner_rolls_back_hotels_and_preserves_draft_on_failure", async () => {
        const updateInfoSpy = vi.spyOn(tripsApi, "updateInfo")
        updateInfoSpy.mockRejectedValueOnce(Object.assign(new Error("Conflict"), { status: 409 }))

        render(<InfoView />)

        // Switch to Accommodation (hotels) tab
        fireEvent.click(screen.getByText("accommodation"))

        // Open Hotel Detail dialog
        const detailsBtn = await screen.findByText("details")
        fireEvent.click(detailsBtn)

        // Click inner Edit button inside the hotel detail dialog
        const editButtons = await screen.findAllByText("edit")
        fireEvent.click(editButtons[editButtons.length - 1])

        // Modify Memo draft inside inner edit mode
        const memoTextarea = (await screen.findByDisplayValue("Original Hotel Memo")) as HTMLTextAreaElement
        fireEvent.change(memoTextarea, { target: { value: "Unsaved Draft WiFi 9999" } })

        // Click Save Changes -> remote fails with 409
        fireEvent.click(screen.getByText("Save Changes"))

        await waitFor(() => {
            expect(updateInfoSpy).toHaveBeenCalledTimes(1)
            expect(toast.error).toHaveBeenCalled()
            expect(mockReloadTripDetail).toHaveBeenCalled()
        })

        // CRITICAL: Must stay in innerEditing=true with tempHotel draft intact (NOT wiped by useEffect!)
        const preservedTextarea = (await screen.findByDisplayValue("Unsaved Draft WiFi 9999")) as HTMLTextAreaElement
        expect(preservedTextarea).toBeTruthy()
        expect(screen.getByText("Save Changes")).toBeTruthy()

        // Cancel inner edit -> must show rolled-back Original Hotel Memo (NOT the failed optimistic draft!)
        fireEvent.click(screen.getByText("Cancel"))
        expect(await screen.findByText("Original Hotel Memo")).toBeTruthy()
    })

    it("test_poc_info_view_offline_save_preserves_optimistic_edit_and_resets_draft_on_trip_switch", async () => {
        const updateInfoSpy = vi.spyOn(tripsApi, "updateInfo")
        updateInfoSpy.mockResolvedValueOnce({ status: "queued", offline: true })

        const { rerender } = render(<InfoView />)

        // Switch to Accommodation tab -> open Hotel Detail -> edit Memo
        fireEvent.click(screen.getByText("accommodation"))
        fireEvent.click(await screen.findByText("details"))
        const editButtons = await screen.findAllByText("edit")
        fireEvent.click(editButtons[editButtons.length - 1])

        const memoTextarea = (await screen.findByDisplayValue("Original Hotel Memo")) as HTMLTextAreaElement
        fireEvent.change(memoTextarea, { target: { value: "Offline Queued Hotel Memo" } })
        fireEvent.click(screen.getByText("Save Changes"))

        await waitFor(() => {
            expect(updateInfoSpy).toHaveBeenCalledTimes(1)
            expect(toast.success).toHaveBeenCalledWith("Done")
        })
        expect(mockReloadTripDetail).not.toHaveBeenCalled()

        // CRITICAL: View mode MUST keep the optimistic offline edit (NOT clobbered back to stale activeTripData!)
        expect(await screen.findByText("Offline Queued Hotel Memo")).toBeTruthy()

        // Now test failure -> switch activeTripId -> Trip 1's draft MUST NOT leak into Trip 2
        vi.clearAllMocks()
        updateInfoSpy.mockRejectedValueOnce(Object.assign(new Error("Conflict"), { status: 409 }))
        const editButtons2 = await screen.findAllByText("edit")
        fireEvent.click(editButtons2[editButtons2.length - 1])
        const memoTextarea2 = (await screen.findByDisplayValue("Offline Queued Hotel Memo")) as HTMLTextAreaElement
        fireEvent.change(memoTextarea2, { target: { value: "Trip1 Stuck Draft" } })
        fireEvent.click(screen.getByText("Save Changes"))
        await waitFor(() => {
            expect(toast.error).toHaveBeenCalled()
        })
        expect(await screen.findByDisplayValue("Trip1 Stuck Draft")).toBeTruthy()

        // Switch activeTripId to Trip 2
        const TRIP_2_ID = "44444444-4444-4444-8444-444444444444"
        mockTripContextValue = {
            ...mockTripContextValue,
            activeTripId: TRIP_2_ID,
            activeTrip: { id: TRIP_2_ID, title: "Osaka Trip" },
        }
        mockTripDetailValue = {
            trip: {
                id: TRIP_2_ID,
                title: "Osaka Trip",
                flight_info: { outbound: [], inbound: [] },
                hotel_info: [
                    {
                        name: "Namba Oriental Hotel",
                        address: "Namba",
                        booking_id: "OSK99",
                        check_in: "15:00",
                        check_out: "11:00",
                        phone: "",
                        memo: "Trip2 Clean Memo",
                        image_url: "",
                        link_url: "",
                        hide_navigation: false,
                        lat: 34.66,
                        lng: 135.50,
                        links: [],
                    },
                ],
            },
            mutate: mockReloadTripDetail,
        }
        rerender(<InfoView />)

        await waitFor(() => {
            expect(screen.queryByDisplayValue("Trip1 Stuck Draft")).toBeNull()
        })
    })

    it("test_poc_post_commit_revalidation_error_does_not_false_rollback_info_or_cards", async () => {
        // 1. InfoView: PATCH /info succeeds (200 OK), then reloadTripDetail() throws transient error
        const updateInfoSpy = vi.spyOn(tripsApi, "updateInfo")
        updateInfoSpy.mockResolvedValueOnce({ status: "success" })
        mockReloadTripDetail.mockRejectedValueOnce(new Error("Transient SWR refresh failure"))

        const { unmount } = render(<InfoView />)
        fireEvent.click(screen.getByText("accommodation"))
        fireEvent.click(await screen.findByText("details"))
        const editButtons = await screen.findAllByText("edit")
        fireEvent.click(editButtons[editButtons.length - 1])
        const memoTextarea = (await screen.findByDisplayValue("Original Hotel Memo")) as HTMLTextAreaElement
        fireEvent.change(memoTextarea, { target: { value: "Committed Server Memo" } })
        fireEvent.click(screen.getByText("Save Changes"))

        await waitFor(() => {
            expect(toast.success).toHaveBeenCalledWith("Done")
        })
        expect(toast.error).not.toHaveBeenCalled()
        expect(await screen.findByText("Committed Server Memo")).toBeTruthy()
        unmount()

        // 2. ToolsView: PATCH /info succeeds (200 OK), then tripMutate() throws transient error
        vi.clearAllMocks()
        updateInfoSpy.mockResolvedValueOnce({ status: "success" })
        mockTripMutate.mockRejectedValueOnce(new Error("Transient SWR list mutate failure"))

        render(<ToolsView />)
        fireEvent.click(screen.getByText("tv_cards"))
        fireEvent.click(await screen.findByText("tv_add_card"))
        const nameInput = await screen.findByPlaceholderText("tv_card_name_ph")
        fireEvent.change(nameInput, { target: { value: "Committed Card" } })
        const submitButtons = screen.getAllByText("tv_add_card")
        fireEvent.click(submitButtons[submitButtons.length - 1])

        await waitFor(() => {
            expect(toast.success).toHaveBeenCalled()
        })
        expect(toast.error).not.toHaveBeenCalled()
        expect(screen.getByText("Committed Card")).toBeTruthy()
    })
})
