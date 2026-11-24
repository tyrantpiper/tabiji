import React from "react"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen, fireEvent, act } from "@testing-library/react"
import fs from "node:fs"
import path from "node:path"
import EditableDailyTips from "@/components/itinerary/EditableDailyTips"
import EditableDailyChecklist from "@/components/itinerary/EditableDailyChecklist"
import EditableDailyAIReview from "@/components/itinerary/EditableDailyAIReview"
import ItineraryDashboardHub from "@/components/itinerary/ItineraryDashboardHub"
import IOSBottomSheet from "@/components/itinerary/IOSBottomSheet"
import { useTripRealtime, getClientSessionId } from "@/lib/hooks/useTripRealtime"
import { tripsApi } from "@/lib/api"
import { toast } from "sonner"

const {
  mockSwrMutate,
  realtimeHandlers,
  mockSupabaseChannel,
  mockRemoveChannel,
} = vi.hoisted(() => {
  const mockSwrMutate = vi.fn()
  const realtimeHandlers: Record<string, (arg: { payload: Record<string, unknown> }) => void> = {}
  const mockRemoveChannel = vi.fn()
  const mockSupabaseChannel = vi.fn(() => {
    const ch = {
      on: vi.fn((_type: string, filter: { event?: string }, cb: (arg: { payload: Record<string, unknown> }) => void) => {
        if (filter?.event) realtimeHandlers[filter.event] = cb
        return ch
      }),
      subscribe: vi.fn((cb?: (status: string) => void) => {
        cb?.("SUBSCRIBED")
        return ch
      }),
      send: vi.fn().mockResolvedValue("ok"),
    }
    return ch
  })
  return { mockSwrMutate, realtimeHandlers, mockSupabaseChannel, mockRemoveChannel }
})

vi.mock("swr", () => ({
  useSWRConfig: () => ({ mutate: mockSwrMutate }),
}))

vi.mock("@/lib/supabase", () => ({
  getSupabaseClient: () => ({
    channel: mockSupabaseChannel,
    removeChannel: mockRemoveChannel,
  }),
}))

let mockLang: "zh" | "en" = "zh"

vi.mock("@/lib/LanguageContext", () => ({
  useLanguage: () => ({
    lang: mockLang,
    t: (k: string) => k,
  }),
}))

vi.mock("@/lib/hooks", () => ({
  useHaptic: () => ({
    tap: vi.fn(),
    selection: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
    custom: vi.fn(),
  }),
}))

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}))

const frontendDir = path.resolve(__dirname, "..")

describe("Daily Dashboard 5-Tab Cards Unification & Safety-Net Suite", () => {
  beforeEach(() => {
    mockLang = "zh"
    vi.clearAllMocks()
    // Keep background exchange-rate fetch pending during synchronous tests to avoid un-awaited microtask act() noise
    global.fetch = vi.fn(() => new Promise<Response>(() => {}))
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  // =========================================================================
  // 🛡️ Mantis Block G: Benign Controls (Must pass both Pre-Patch and Post-Patch)
  // =========================================================================
  it("benign_control_1: preserves core data rendering across EditableDailyTips, EditableDailyChecklist, and EditableDailyAIReview", () => {
    const onUpdateTips = vi.fn().mockResolvedValue(true)
    const onUpdateChecklist = vi.fn().mockResolvedValue(true)
    const onUpdateReview = vi.fn()

    render(
      <div>
        <EditableDailyTips
          tripId="trip-1"
          day={1}
          notes={[{ icon: "⚠️", title: "攜帶雨具", content: "午後陣雨" }]}
          costs={[{ item: "一蘭拉麵", amount: "1200", currency: "JPY", note: "晚餐" }]}
          tickets={[{ name: "Skyliner", price: "2580", currency: "JPY", note: "上野直達" }]}
          onUpdate={onUpdateTips}
          userId="user-123"
        />
        <EditableDailyChecklist
          tripId="trip-1"
          day={1}
          items={[
            { id: "c1", text: "護照正本", checked: true },
            { id: "c2", text: "日本網卡", checked: false },
          ]}
          onUpdate={onUpdateChecklist}
          userId="user-123"
        />
        <EditableDailyAIReview
          tripId="trip-1"
          day={1}
          review={"🎯 行程綜合評分：92 分\n1. 動線順暢\n• 時間充裕"}
          onUpdate={onUpdateReview}
          userId="user-123"
        />
      </div>
    )

    expect(screen.getByText("攜帶雨具")).toBeDefined()
    expect(screen.getByText("午後陣雨")).toBeDefined()
    expect(screen.getByText("一蘭拉麵")).toBeDefined()
    expect(screen.getByText("Skyliner")).toBeDefined()
    expect(screen.getByText("護照正本")).toBeDefined()
    expect(screen.getByText("日本網卡")).toBeDefined()
    expect(screen.getByText(/1\/2/)).toBeDefined()
    expect(screen.getByText(/AI 深度審核報告/)).toBeDefined()
  })

  // =========================================================================
  // 🔴 Exploit PoCs (Pre-Patch Red -> Post-Patch Green Safety Nets)
  // =========================================================================
  it("exploit_poc_1: EditableDailyChecklist rapid debounced toggles do not leak pendingUpdatesCount or roll back to intermediate dirty state", async () => {
    vi.useFakeTimers()
    let shouldSucceed = true
    const onUpdate = vi.fn().mockImplementation(async () => shouldSucceed)

    const initialItems = [
      { id: "c1", text: "Item 1", checked: false },
      { id: "c2", text: "Item 2", checked: false },
    ]

    const { rerender } = render(
      <EditableDailyChecklist
        tripId="trip-1"
        day={1}
        items={initialItems}
        onUpdate={onUpdate}
        userId="user-1"
      />
    )

    // Two rapid clicks within the 500ms debounce window
    fireEvent.click(screen.getByText("Item 1"))
    await act(async () => {
      vi.advanceTimersByTime(150)
    })
    fireEvent.click(screen.getByText("Item 2"))

    // Flush the 500ms debounce timer
    await act(async () => {
      vi.advanceTimersByTime(550)
    })

    expect(onUpdate).toHaveBeenCalledTimes(1)
    expect(onUpdate).toHaveBeenLastCalledWith([
      { id: "c1", text: "Item 1", checked: true },
      { id: "c2", text: "Item 2", checked: true },
    ])

    // Proof that pendingUpdatesCount was NOT leaked: external prop update must sync cleanly!
    const externalSyncedItems = [
      { id: "c1", text: "Item 1", checked: true },
      { id: "c2", text: "Item 2", checked: true },
      { id: "c3", text: "Companion Added Item 3", checked: false },
    ]
    rerender(
      <EditableDailyChecklist
        tripId="trip-1"
        day={1}
        items={externalSyncedItems}
        onUpdate={onUpdate}
        userId="user-1"
      />
    )
    expect(screen.getByText("Companion Added Item 3")).toBeDefined()

    // Now test failure rollback across multiple rapid clicks within 500ms:
    // Baseline has c1=true, c2=true, c3=false (2/3 checked).
    // Rapidly toggle c1 -> false, then c3 -> true, and have API fail (return false).
    // Rollback MUST restore BOTH c1=true and c3=false (the pre-debounce committed baseline).
    shouldSucceed = false
    fireEvent.click(screen.getByText("Item 1"))
    await act(async () => {
      vi.advanceTimersByTime(100)
    })
    fireEvent.click(screen.getByText("Companion Added Item 3"))
    await act(async () => {
      vi.advanceTimersByTime(550)
    })

    expect(screen.getByText(/2\/3/)).toBeDefined()
  })

  it("exploit_poc_2: EditableDailyChecklist catches rejected onUpdate without unhandled rejection and blocks single-frame double-tap duplicate creation", async () => {
    let resolveUpdate!: (val: boolean) => void
    const onUpdate = vi.fn().mockImplementation(
      () =>
        new Promise<boolean>((resolve) => {
          resolveUpdate = resolve
        })
    )

    render(
      <EditableDailyChecklist
        tripId="trip-1"
        day={1}
        items={[]}
        onUpdate={onUpdate}
        userId="user-1"
      />
    )

    // Quick-add chip in empty state: double-click synchronously in the same frame
    const passportChip = screen.getByRole("button", { name: /\+ 護照/ })
    fireEvent.click(passportChip)
    fireEvent.click(passportChip)

    expect(onUpdate).toHaveBeenCalledTimes(1)
    await act(async () => {
      resolveUpdate(true)
    })

    // Now test rejected promise handling on addItem
    const rejectingOnUpdate = vi.fn().mockRejectedValueOnce(new Error("Offline network drop"))
    const { unmount } = render(
      <EditableDailyChecklist
        tripId="trip-2"
        day={1}
        items={[]}
        onUpdate={rejectingOnUpdate}
        userId="user-1"
      />
    )

    const esimChip = screen.getAllByRole("button", { name: /\+ 網卡 \/ eSIM/ })[0]
    await act(async () => {
      fireEvent.click(esimChip)
    })

    expect(toast.error).toHaveBeenCalled()
    unmount()
  })

  it("exploit_poc_3: Privacy toggle and creation safely survive localStorage SecurityError when userId is omitted", async () => {
    const getItemSpy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("Access denied", "SecurityError")
    })

    const onUpdateTips = vi.fn().mockResolvedValue(true)
    render(
      <EditableDailyTips
        tripId="trip-1"
        day={1}
        displaySection="costs"
        notes={[]}
        costs={[{ item: "Taxi", amount: "1500", currency: "JPY" }]}
        tickets={[]}
        onUpdate={onUpdateTips}
      />
    )

    const privacyBtn = screen.getByTitle("設為私人")
    await act(async () => {
      fireEvent.click(privacyBtn)
    })

    expect(onUpdateTips).toHaveBeenCalledWith("costs", [
      expect.objectContaining({
        item: "Taxi",
        is_private: true,
        private_owner_id: undefined,
      }),
    ])

    getItemSpy.mockRestore()
  })

  it("exploit_poc_4: IconPicker extracts first grapheme cluster without corrupting surrogate pairs or overflowing full sentence and localizes categories", () => {
    const onUpdateTips = vi.fn().mockResolvedValue(true)
    render(
      <EditableDailyTips
        tripId="trip-1"
        day={1}
        displaySection="notes"
        notes={[]}
        costs={[]}
        tickets={[]}
        onUpdate={onUpdateTips}
      />
    )

    // Open Add Note form
    fireEvent.click(screen.getByRole("button", { name: /新增第一筆提醒/ }))

    // Open IconPicker popover
    const iconTrigger = screen.getByRole("button", { name: /選擇圖示|Select or enter icon/i })
    expect(iconTrigger.getAttribute("type")).toBe("button")
    fireEvent.click(iconTrigger)

    // Verify categorized sections in Chinese
    expect(screen.getByText("警示與提醒")).toBeDefined()
    expect(screen.getByText("交通與移動")).toBeDefined()
    expect(screen.getByText("餐飲與美食")).toBeDefined()
    expect(screen.getByText("住宿與票券")).toBeDefined()
    expect(screen.getByText("購物與實用")).toBeDefined()

    // Paste multi-character sentence starting with surrogate-pair emoji
    const customInput = screen.getByPlaceholderText("貼上或輸入自訂 Emoji")
    fireEvent.change(customInput, { target: { value: "🍜 一蘭拉麵必吃備註" } })

    // Trigger button should display ONLY the first emoji grapheme "🍜", not the whole sentence
    expect(iconTrigger.textContent).toBe("🍜")
    // And the custom input itself should normalize to the first grapheme so subsequent edits don't get stuck behind the old sentence
    expect((customInput as HTMLInputElement).value).toBe("🍜")
  })

  it("exploit_poc_5: EditableDailyChecklist cancels pending toggle debounce when immediate removeItem runs within 500ms, preventing zombie item resurrection", async () => {
    vi.useFakeTimers()
    const onUpdate = vi.fn().mockResolvedValue(true)

    render(
      <EditableDailyChecklist
        tripId="trip-1"
        day={1}
        items={[
          { id: "c1", text: "Item 1", checked: false },
          { id: "c2", text: "Item 2 To Delete", checked: false },
        ]}
        onUpdate={onUpdate}
        userId="user-1"
      />
    )

    // 1. Toggle Item 1 at t=0ms (schedules 500ms debounce timer)
    fireEvent.click(screen.getByText("Item 1"))
    await act(async () => {
      vi.advanceTimersByTime(150)
    })

    // 2. Delete Item 2 at t=150ms (immediate mutation within the 500ms debounce window)
    const deleteBtn = screen.getByRole("button", { name: /刪除項目 Item 2 To Delete/ })
    await act(async () => {
      fireEvent.click(deleteBtn)
    })

    expect(onUpdate).toHaveBeenCalledTimes(1)
    expect(onUpdate).toHaveBeenLastCalledWith([
      { id: "c1", text: "Item 1", checked: true },
    ])

    // 3. Advance past t=500ms: the cancelled debounce timer MUST NOT fire or resurrect Item 2!
    await act(async () => {
      vi.advanceTimersByTime(500)
    })

    expect(onUpdate).toHaveBeenCalledTimes(1)
    expect(screen.getByText("1/1 (100%)")).toBeDefined()
  })

  it("exploit_poc_6: CurrencyPillSelector retains non-preset currency (GBP) after clicking a preset pill and supports PrivacyTogglePill in Edit mode", async () => {
    const onUpdateTips = vi.fn().mockResolvedValue(true)

    render(
      <EditableDailyTips
        tripId="trip-1"
        day={1}
        displaySection="costs"
        notes={[]}
        costs={[{ item: "London Tube", amount: "15", currency: "GBP" }]}
        tickets={[]}
        onUpdate={onUpdateTips}
        userId="user-777"
        defaultCurrency="JPY"
      />
    )

    // Enter Edit mode
    fireEvent.click(screen.getByRole("button", { name: /編輯/ }))
    expect(screen.getByRole("button", { name: "GBP" })).toBeDefined()

    // Click preset pill "JPY" — "GBP" pill MUST remain in CurrencyPillSelector so user never loses original currency
    fireEvent.click(screen.getByRole("button", { name: "JPY" }))
    const gbpPillAfterSwitch = screen.getByRole("button", { name: "GBP" })
    expect(gbpPillAfterSwitch).toBeDefined()

    // Switch back to "GBP"
    fireEvent.click(gbpPillAfterSwitch)

    // Toggle PrivacyTogglePill inside Edit mode (AC-3 & Proposed Changes #3)
    const editPrivacyPill = screen.getByRole("button", { name: /公開|僅自己可見/ })
    fireEvent.click(editPrivacyPill)
    expect(editPrivacyPill.textContent).toContain("僅自己可見")

    // Save batch edits
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /儲存/ }))
    })

    expect(onUpdateTips).toHaveBeenCalledWith("costs", [
      expect.objectContaining({
        item: "London Tube",
        amount: "15",
        currency: "GBP",
        is_private: true,
        private_owner_id: "user-777",
      }),
    ])
  })

  it("exploit_poc_7: Escape inside IconPicker Popover or inline Add/Edit inputs closes only the inner UI without dismissing parent IOSBottomSheet, and blocks single-frame double-tap on AI Review & Delete", async () => {
    const handleSheetClose = vi.fn()
    const onUpdateTips = vi.fn().mockResolvedValue(true)
    const onUpdateChecklist = vi.fn().mockResolvedValue(true)

    const { unmount } = render(
      <IOSBottomSheet
        isOpen={true}
        activeTab="tips"
        onClose={handleSheetClose}
        onTabChange={vi.fn()}
      >
        <EditableDailyTips
          tripId="trip-1"
          day={1}
          displaySection="notes"
          notes={[]}
          costs={[]}
          tickets={[]}
          onUpdate={onUpdateTips}
        />
        <EditableDailyChecklist
          tripId="trip-1"
          day={1}
          items={[{ id: "c1", text: "Existing Item", checked: false }]}
          onUpdate={onUpdateChecklist}
        />
      </IOSBottomSheet>
    )

    // 1. Open Add Note form & open IconPicker Popover inside IOSBottomSheet
    fireEvent.click(screen.getByRole("button", { name: /新增第一筆提醒/ }))
    const iconTrigger = screen.getByRole("button", { name: /選擇圖示/ })
    fireEvent.click(iconTrigger)
    const customEmojiInput = screen.getByPlaceholderText("貼上或輸入自訂 Emoji")

    // Press Escape inside IconPicker Popover -> closes Popover, does NOT close IOSBottomSheet
    fireEvent.keyDown(customEmojiInput, { key: "Escape" })
    expect(handleSheetClose).not.toHaveBeenCalled()

    // 2. Press Escape inside Add Note title input -> closes inline Add Note form, does NOT close IOSBottomSheet
    const noteTitleInput = screen.getByPlaceholderText(/標題（例如/)
    fireEvent.keyDown(noteTitleInput, { key: "Escape" })
    expect(handleSheetClose).not.toHaveBeenCalled()
    expect(screen.queryByPlaceholderText(/標題（例如/)).toBeNull()

    // 3. Open Checklist Add form & press Escape inside its input -> closes inline Add form, does NOT close IOSBottomSheet
    const checklistAddBtns = screen.getAllByRole("button", { name: /\+?\s*新增$/ })
    fireEvent.click(checklistAddBtns[checklistAddBtns.length - 1])
    const checklistInput = screen.getByPlaceholderText(/輸入待辦事項/)
    fireEvent.keyDown(checklistInput, { key: "Escape" })
    expect(handleSheetClose).not.toHaveBeenCalled()
    expect(screen.queryByPlaceholderText(/輸入待辦事項/)).toBeNull()

    // 4. Single-frame double-tap on Checklist Delete button invokes onUpdate only ONCE
    const deleteBtn = screen.getByRole("button", { name: /刪除項目 Existing Item/ })
    await act(async () => {
      fireEvent.click(deleteBtn)
      fireEvent.click(deleteBtn)
    })
    expect(onUpdateChecklist).toHaveBeenCalledTimes(1)
    unmount()

    // 5. Single-frame double-tap on AI Review Generate button invokes tripsApi.generateAIReview only ONCE
    let resolveReview!: (val: { status: string; day: number; review: string }) => void
    const generateSpy = vi.spyOn(tripsApi, "generateAIReview").mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveReview = resolve
        })
    )

    render(
      <EditableDailyAIReview
        tripId="trip-1"
        day={1}
        review={undefined}
        onUpdate={vi.fn()}
        userId="user-1"
      />
    )

    const genBtn = screen.getByRole("button", { name: /生成 AI 深度審核報告/ })
    fireEvent.click(genBtn)
    fireEvent.click(genBtn)
    expect(generateSpy).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolveReview({ status: "ok", day: 1, review: "🎯 95 分" })
    })
    generateSpy.mockRestore()
  })

  // =========================================================================
  // ✨ New Specification Acceptance Tests (AC-1 through AC-6)
  // =========================================================================
  it("spec_1: enforces unified Washi-White / Deep-Forest surface, removes variant='ghost' orange bleed, and removes mx-6 on AI Review", () => {
    const tipsSrc = fs.readFileSync(
      path.join(frontendDir, "components/itinerary/EditableDailyTips.tsx"),
      "utf-8"
    )
    const checklistSrc = fs.readFileSync(
      path.join(frontendDir, "components/itinerary/EditableDailyChecklist.tsx"),
      "utf-8"
    )
    const reviewSrc = fs.readFileSync(
      path.join(frontendDir, "components/itinerary/EditableDailyAIReview.tsx"),
      "utf-8"
    )

    // Zero variant="ghost" across all 3 files
    expect(tipsSrc).not.toContain('variant="ghost"')
    expect(checklistSrc).not.toContain('variant="ghost"')
    expect(reviewSrc).not.toContain('variant="ghost"')

    // Zero native <select> in EditableDailyTips
    expect(tipsSrc).not.toContain("<select")

    // Zero pointer-events-none full-card freeze in EditableDailyChecklist
    expect(checklistSrc).not.toContain("pointer-events-none")

    // AI Review removes mx-6 and has dark mode text contrast classes
    expect(reviewSrc).not.toContain("mx-6")
    expect(reviewSrc).toContain("dark:text-")
  })

  it("spec_2: renders CurrencyPillSelector (with non-preset currency support) and PrivacyTogglePill on Costs & Tickets creation", async () => {
    const onUpdateTips = vi.fn().mockResolvedValue(true)

    render(
      <EditableDailyTips
        tripId="trip-1"
        day={1}
        displaySection="costs"
        notes={[]}
        costs={[{ item: "London Tube", amount: "15", currency: "GBP" }]}
        tickets={[]}
        onUpdate={onUpdateTips}
        userId="user-777"
        defaultCurrency="JPY"
      />
    )

    // Open Edit mode to verify non-preset currency "GBP" is preserved in CurrencyPillSelector
    fireEvent.click(screen.getByRole("button", { name: /編輯/ }))
    expect(screen.getByRole("button", { name: "GBP" })).toBeDefined()
    fireEvent.click(screen.getByRole("button", { name: /取消/ }))

    // Open Add Cost form
    fireEvent.click(screen.getByRole("button", { name: /\+?\s*新增/ }))

    // Select USD currency pill
    fireEvent.click(screen.getByRole("button", { name: "USD" }))

    // Fill item and amount
    fireEvent.change(screen.getByPlaceholderText(/項目名稱/), {
      target: { value: "Starbucks Reserve" },
    })
    fireEvent.change(screen.getByPlaceholderText(/輸入金額/), {
      target: { value: "25" },
    })

    // Toggle privacy to private during creation
    const privacyToggle = screen.getByRole("button", { name: /公開|僅自己可見/ })
    fireEvent.click(privacyToggle)
    expect(privacyToggle.textContent).toContain("僅自己可見")

    // Submit form
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^新增$/ }))
    })

    expect(onUpdateTips).toHaveBeenCalledWith("costs", [
      { item: "London Tube", amount: "15", currency: "GBP" },
      expect.objectContaining({
        item: "Starbucks Reserve",
        amount: "25",
        currency: "USD",
        is_private: true,
        private_owner_id: "user-777",
      }),
    ])
  })

  it("spec_3: blocks Enter submission during IME composition (isComposing: true) in EditableDailyChecklist and supports English empty states", async () => {
    const onUpdate = vi.fn().mockResolvedValue(true)
    const { unmount } = render(
      <EditableDailyChecklist
        tripId="trip-1"
        day={1}
        items={[]}
        onUpdate={onUpdate}
        userId="user-1"
      />
    )

    // Click primary empty state CTA to open add form
    fireEvent.click(screen.getByRole("button", { name: /新增第一筆項目/ }))

    const input = screen.getByPlaceholderText(/輸入待辦事項/)
    fireEvent.change(input, { target: { value: "護照影本" } })

    // Simulate IME composition Enter (should NOT submit)
    fireEvent.keyDown(input, { key: "Enter", isComposing: true })
    expect(onUpdate).not.toHaveBeenCalled()

    // Normal Enter after composition completes (SHOULD submit)
    await act(async () => {
      fireEvent.keyDown(input, { key: "Enter", isComposing: false })
    })
    expect(onUpdate).toHaveBeenCalledTimes(1)
    expect(onUpdate).toHaveBeenCalledWith([
      expect.objectContaining({
        text: "護照影本",
        checked: false,
      }),
    ])
    unmount()

    // Switch language to English and verify English empty states across Checklist, Tickets, and AI Review
    mockLang = "en"
    render(
      <div>
        <EditableDailyChecklist tripId="trip-1" day={1} items={[]} onUpdate={vi.fn()} />
        <EditableDailyTips
          tripId="trip-1"
          day={1}
          displaySection="tickets"
          notes={[]}
          costs={[]}
          tickets={[]}
          onUpdate={vi.fn()}
        />
        <EditableDailyAIReview tripId="trip-1" day={1} review={undefined} onUpdate={vi.fn()} />
      </div>
    )
    expect(screen.getByRole("button", { name: /\+ Passport/ })).toBeDefined()
    expect(screen.getByRole("button", { name: /\+ Universal Adapter/ })).toBeDefined()
    expect(screen.getByRole("button", { name: /Add First Ticket/ })).toBeDefined()
    expect(screen.getByRole("button", { name: /Generate AI Review/ })).toBeDefined()
  })

  // =========================================================================
  // 🔁 Round 2 P0–P3 Regression Safety Nets
  // =========================================================================
  it("reg_p0_1: upstream itinerary-view forwards defaultCurrency fallback ('JPY') and memoized stable array props to all dashboard tabs", () => {
    const viewSrc = fs.readFileSync(
      path.join(frontendDir, "components/views/itinerary-view.tsx"),
      "utf-8"
    )
    expect(viewSrc).toContain("EMPTY_NOTES")
    expect(viewSrc).toContain("EMPTY_COSTS")
    expect(viewSrc).toContain("EMPTY_TICKETS")
    expect(viewSrc).toContain("EMPTY_CHECKLIST")
    expect(viewSrc).toContain('const effectiveTripCurrency = currentTrip?.currency?.trim().toUpperCase() || "JPY"')
    const defaultCurrencyMatches = viewSrc.match(/defaultCurrency=\{effectiveTripCurrency\}/g) || []
    // Hub + 3 EditableDailyTips mounts (tips, costs, tickets)
    expect(defaultCurrencyMatches.length).toBeGreaterThanOrEqual(4)
    // Day 1 optimistic checklist patch must clear legacy Day 0 items so deleted Day 0 items do not resurrect
    expect(viewSrc).toContain("nextChecklists[0] = []")
    // No inline `|| []` on EditableDailyTips mounts
    expect(viewSrc).not.toMatch(/notes=\{getDayData\(currentTrip\?\.day_notes, day\) \|\| \[\]\}/)
    expect(viewSrc).not.toMatch(/costs=\{getDayData\(currentTrip\?\.day_costs, day\) \|\| \[\]\}/)
    expect(viewSrc).not.toMatch(/tickets=\{getDayData\(currentTrip\?\.day_tickets, day\) \|\| \[\]\}/)

    // Hub and Sheet must agree on JPY trip totals, embedded currency (THB), AND excluding 0-amount items from subtotal
    const sampleCosts = [
      { item: "拉麵", amount: "1,200" },
      { item: "烤肉", amount: "¥1,500" },
      { item: "泰式按摩", amount: "1500 THB" },
      { item: "免費公園", amount: "0", currency: "USD" },
    ]
    render(
      <div>
        <ItineraryDashboardHub
          day={1}
          costs={sampleCosts}
          defaultCurrency="JPY"
          onSelectTab={vi.fn()}
        />
        <EditableDailyTips
          tripId="trip-jpy"
          day={1}
          displaySection="costs"
          notes={[]}
          costs={sampleCosts}
          tickets={[]}
          defaultCurrency="JPY"
          onUpdate={vi.fn().mockResolvedValue(true)}
        />
      </div>
    )
    // Both Hub and Sheet show JPY 2,700 (not TWD 2,700!), Sheet subtotal includes THB 1,500, and excludes USD 0 from subtotal badges
    expect(screen.getAllByText("JPY 2,700").length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText(/THB 1,500/).length).toBeGreaterThanOrEqual(1)
    const subtotalRow = screen.getByText("小計").parentElement!
    expect(subtotalRow.textContent).not.toContain("USD 0")
  })

  it("reg_p0_2: comma-formatted amounts, embedded currencies, free/range text work with type='text' inputMode='decimal', edit sanitization, and negative rejection", async () => {
    const onUpdate = vi.fn().mockResolvedValue(true)
    const { container, rerender } = render(
      <EditableDailyTips
        tripId="trip-1"
        day={1}
        notes={[]}
        costs={[
          { item: "拉麵", amount: "1,200" },
          { item: "按摩", amount: "1500 THB" },
          { item: "神社", amount: "免費", currency: "JPY" },
          { item: "伴手禮", amount: "1,000~2,000", currency: "JPY" },
        ]}
        tickets={[{ name: "JR Pass", price: "28,000", currency: "JPY" }]}
        defaultCurrency="JPY"
        onUpdate={onUpdate}
      />
    )

    // Free and range text preserved verbatim in view mode, and THB 1,500 appears in both row and subtotal
    expect(screen.getByText("免費")).toBeDefined()
    expect(screen.getByText("1,000~2,000")).toBeDefined()
    expect(screen.getAllByText(/THB 1,500/).length).toBeGreaterThanOrEqual(2)

    // Enter Edit mode on Costs: inputs must be type="text" + inputMode="decimal" (zero type="number")
    const editButtons = screen.getAllByRole("button", { name: /編輯/ })
    fireEvent.click(editButtons[0]) // Costs edit button
    expect(container.querySelectorAll('input[type="number"]').length).toBe(0)

    const amountInputs = screen.getAllByPlaceholderText("輸入金額") as HTMLInputElement[]
    expect(amountInputs[0].getAttribute("type")).toBe("text")
    expect(amountInputs[0].getAttribute("inputmode")).toBe("decimal")
    // Sanitized on edit entry
    expect(amountInputs[0].value).toBe("1200")
    expect(amountInputs[1].value).toBe("1500")
    // Free/range preserved intact
    expect(amountInputs[2].value).toBe("免費")
    expect(amountInputs[3].value).toBe("1,000~2,000")

    // Reject negative amount in batch edit with bilingual toast error (zh)
    fireEvent.change(amountInputs[0], { target: { value: "-500" } })
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /儲存/ }))
    })
    expect(onUpdate).not.toHaveBeenCalled()
    expect(toast.error).toHaveBeenCalledWith("金額不可為負數")

    // Cancel Costs edit and check Tickets edit entry sanitization ("28,000" -> "28000")
    fireEvent.click(screen.getByRole("button", { name: /取消/ }))
    fireEvent.click(screen.getAllByRole("button", { name: /編輯/ })[1]) // Tickets edit button
    const ticketPriceInput = screen.getByPlaceholderText("輸入票價") as HTMLInputElement
    expect(ticketPriceInput.getAttribute("type")).toBe("text")
    expect(ticketPriceInput.getAttribute("inputmode")).toBe("decimal")
    expect(ticketPriceInput.value).toBe("28000")
    fireEvent.click(screen.getByRole("button", { name: /取消/ }))

    // Switch to English and test Add Cost negative rejection ("Amount cannot be negative") + embedded currency save ("NT$300")
    mockLang = "en"
    rerender(
      <EditableDailyTips
        tripId="trip-1"
        day={1}
        displaySection="costs"
        notes={[]}
        costs={[{ item: "拉麵", amount: "1,200" }]}
        tickets={[]}
        defaultCurrency="JPY"
        onUpdate={onUpdate}
      />
    )
    fireEvent.click(screen.getByRole("button", { name: /Add/ }))

    const addItemInput = screen.getByPlaceholderText(/Item name/)
    const addAmtInput = screen.getByPlaceholderText("Enter amount")
    expect(addAmtInput.getAttribute("type")).toBe("text")
    expect(addAmtInput.getAttribute("inputmode")).toBe("decimal")

    fireEvent.change(addItemInput, { target: { value: "Refund" } })
    fireEvent.change(addAmtInput, { target: { value: "-500" } })
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^Add$/ }))
    })
    expect(onUpdate).not.toHaveBeenCalled()
    expect(toast.error).toHaveBeenCalledWith("Amount cannot be negative")

    // Now enter "NT$300" and verify normalized amount & extracted TWD currency
    fireEvent.change(addItemInput, { target: { value: "Bubble Tea" } })
    fireEvent.change(addAmtInput, { target: { value: "NT$300" } })
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^Add$/ }))
    })
    expect(onUpdate).toHaveBeenCalledWith(
      "costs",
      expect.arrayContaining([
        expect.objectContaining({ item: "Bubble Tea", amount: "300", currency: "TWD" }),
      ])
    )
  })

  it("reg_p1_3: Escape inside batch-edit inputs or focused form buttons closes only inner form without dismissing IOSBottomSheet, while IconPicker Popover closes first", () => {
    const handleSheetClose = vi.fn()
    render(
      <IOSBottomSheet
        isOpen={true}
        activeTab="tips"
        onClose={handleSheetClose}
        onTabChange={vi.fn()}
      >
        <EditableDailyTips
          tripId="trip-1"
          day={1}
          notes={[{ icon: "⚠️", title: "集合時間", content: "09:00" }]}
          costs={[{ item: "拉麵", amount: "1200", currency: "JPY" }]}
          tickets={[{ name: "Skyliner", price: "2580", currency: "JPY" }]}
          defaultCurrency="JPY"
          onUpdate={vi.fn().mockResolvedValue(true)}
        />
        <EditableDailyChecklist
          tripId="trip-1"
          day={1}
          items={[{ id: "c1", text: "護照", checked: false }]}
          onUpdate={vi.fn().mockResolvedValue(true)}
        />
      </IOSBottomSheet>
    )

    // 1. Notes batch edit + IconPicker Popover: Escape on preset emoji button closes ONLY Popover
    const editButtons = screen.getAllByRole("button", { name: /編輯/ })
    fireEvent.click(editButtons[0]) // Notes Edit
    const iconTrigger = screen.getByRole("button", { name: "選擇圖示" })
    fireEvent.click(iconTrigger)
    const presetAirplane = screen.getByRole("button", { name: "✈️" })
    fireEvent.keyDown(presetAirplane, { key: "Escape" })
    // Popover closed, Notes batch-edit still open, IOSBottomSheet still open
    expect(screen.queryByPlaceholderText("貼上或輸入自訂 Emoji")).toBeNull()
    expect(screen.getByPlaceholderText("提醒標題")).toBeDefined()
    expect(handleSheetClose).not.toHaveBeenCalled()

    // 2. Escape inside Notes batch-edit input closes Notes edit form, NOT IOSBottomSheet
    fireEvent.keyDown(screen.getByPlaceholderText("提醒標題"), { key: "Escape" })
    expect(screen.queryByPlaceholderText("提醒標題")).toBeNull()
    expect(handleSheetClose).not.toHaveBeenCalled()

    // 3. Costs batch edit: Escape while focused on CurrencyPillSelector button or PrivacyTogglePill closes Costs edit, NOT IOSBottomSheet
    fireEvent.click(screen.getAllByRole("button", { name: /編輯/ })[1]) // Costs Edit
    const usdPill = screen.getByRole("button", { name: "USD" })
    fireEvent.keyDown(usdPill, { key: "Escape" })
    expect(screen.queryByPlaceholderText("項目名稱")).toBeNull()
    expect(handleSheetClose).not.toHaveBeenCalled()

    // 4. Add Cost form: Escape while focused on PrivacyTogglePill closes Add Cost and resets draft, NOT IOSBottomSheet
    fireEvent.click(screen.getAllByRole("button", { name: /新增/ })[1]) // Costs Add
    fireEvent.change(screen.getByPlaceholderText(/項目名稱/), { target: { value: "Draft Item" } })
    const costPrivacyPill = screen.getByRole("button", { name: /公開/ })
    fireEvent.keyDown(costPrivacyPill, { key: "Escape" })
    expect(screen.queryByPlaceholderText(/項目名稱/)).toBeNull()
    expect(handleSheetClose).not.toHaveBeenCalled()
    // Re-opening Add Cost shows reset blank draft
    fireEvent.click(screen.getAllByRole("button", { name: /新增/ })[1])
    expect((screen.getByPlaceholderText(/項目名稱/) as HTMLInputElement).value).toBe("")
    fireEvent.click(screen.getByRole("button", { name: "取消" }))

    // 5. Checklist Add form: Escape while focused on Privacy toggle button closes Checklist Add, NOT IOSBottomSheet
    const addBtns = screen.getAllByRole("button", { name: /新增/ })
    fireEvent.click(addBtns[addBtns.length - 1])
    const checklistPrivacyBtn = screen.getByRole("button", { name: /公開/ })
    fireEvent.keyDown(checklistPrivacyBtn, { key: "Escape" })
    expect(screen.queryByPlaceholderText(/輸入待辦事項/)).toBeNull()
    expect(handleSheetClose).not.toHaveBeenCalled()

    // 6. With no inline form open, Escape dismisses IOSBottomSheet normally
    fireEvent.keyDown(window, { key: "Escape" })
    expect(handleSheetClose).toHaveBeenCalledTimes(1)
  })

  it("reg_p1_4: batch-edit failure keeps form open with user edits intact, blocks empty rows, and delete never puts spinner/disabled state on shifted sibling row", async () => {
    const failingTipsUpdate = vi.fn().mockRejectedValueOnce(new Error("HTTP 500"))
    render(
      <EditableDailyTips
        tripId="trip-1"
        day={1}
        displaySection="costs"
        notes={[]}
        costs={[
          { item: "Row A", amount: "100", currency: "JPY" },
          { item: "Row B", amount: "200", currency: "JPY" },
        ]}
        tickets={[]}
        defaultCurrency="JPY"
        onUpdate={failingTipsUpdate}
      />
    )

    // 1. Enter Edit mode, blank out Row A -> empty validation blocks save
    fireEvent.click(screen.getByRole("button", { name: /編輯/ }))
    const itemInputs = screen.getAllByPlaceholderText("項目名稱") as HTMLInputElement[]
    fireEvent.change(itemInputs[0], { target: { value: "   " } })
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /儲存/ }))
    })
    expect(failingTipsUpdate).not.toHaveBeenCalled()
    expect(toast.error).toHaveBeenCalledWith("請輸入項目和金額")

    // 2. Enter valid edit, trigger HTTP 500 rejection -> edit form stays OPEN with edited value preserved
    fireEvent.change(itemInputs[0], { target: { value: "Edited Row A" } })
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /儲存/ }))
    })
    expect(failingTipsUpdate).toHaveBeenCalledTimes(1)
    expect(toast.error).toHaveBeenCalledWith("儲存失敗")
    expect((screen.getAllByPlaceholderText("項目名稱")[0] as HTMLInputElement).value).toBe("Edited Row A")

    // Cancel clears edit state
    fireEvent.click(screen.getByRole("button", { name: "取消" }))

    // 3. Delete Row A while onUpdate is pending -> shifted Row B MUST NOT be disabled or show Loader2 spinner
    let resolveDelete!: (ok: boolean) => void
    failingTipsUpdate.mockImplementationOnce(
      () => new Promise<boolean>((resolve) => { resolveDelete = resolve })
    )
    fireEvent.click(screen.getByRole("button", { name: "移除花費 Row A" }))
    // Row B shifted into index 0; verify its remove button is NOT disabled and has NO animate-spin loader
    const rowBRemoveBtn = screen.getByRole("button", { name: "移除花費 Row B" })
    expect((rowBRemoveBtn as HTMLButtonElement).disabled).toBe(false)
    expect(rowBRemoveBtn.querySelector(".animate-spin")).toBeNull()
    await act(async () => {
      resolveDelete(true)
    })

    // 4. Checklist batch-edit empty validation blocks blank item text
    const checklistUpdate = vi.fn().mockResolvedValue(true)
    render(
      <EditableDailyChecklist
        tripId="trip-1"
        day={1}
        items={[{ id: "c1", text: "護照", checked: false }]}
        onUpdate={checklistUpdate}
      />
    )
    const editBtns = screen.getAllByRole("button", { name: /編輯/ })
    fireEvent.click(editBtns[editBtns.length - 1])
    const chkInput = screen.getByDisplayValue("護照")
    fireEvent.change(chkInput, { target: { value: "   " } })
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /儲存/ }))
    })
    expect(checklistUpdate).not.toHaveBeenCalled()
    expect(toast.error).toHaveBeenCalledWith("請輸入項目內容")
  })

  it("reg_p1_5: useTripRealtime syncs & revalidates SWR trip detail on checklist:update & tip:update while preserving self-echo suppression and collab state across stable parent re-renders", () => {
    const EMPTY_CHK: Array<{ id: string; text: string; checked: boolean }> = []
    function RealtimeHarness({ tick }: { tick: number }) {
      useTripRealtime("trip-rt-1", "user-B")
      return (
        <div data-tick={tick}>
          <EditableDailyChecklist
            tripId="trip-rt-1"
            day={1}
            items={EMPTY_CHK}
            onUpdate={vi.fn().mockResolvedValue(true)}
            userId="user-B"
          />
        </div>
      )
    }

    const { rerender } = render(<RealtimeHarness tick={0} />)
    const collabCb = realtimeHandlers["collab:event"]
    expect(typeof collabCb).toBe("function")

    // 1. Self-echo MUST be suppressed (zero SWR mutate, zero DOM event update)
    act(() => {
      collabCb({
        payload: {
          event: "checklist:update",
          senderSessionId: getClientSessionId(),
          dayIndex: 1,
          items: [{ id: "self-1", text: "Self Echo Item", checked: false }],
        },
      })
    })
    expect(mockSwrMutate).not.toHaveBeenCalled()
    expect(screen.queryByText("Self Echo Item")).toBeNull()

    // 2. Remote checklist:update updates UI, survives unrelated parent re-render, and patches + revalidates SWR cache
    act(() => {
      collabCb({
        payload: {
          event: "checklist:update",
          senderSessionId: "remote-session-xyz",
          dayIndex: 1,
          items: [
            { id: "r1", text: "Remote Passport", checked: true },
            { id: "r2", text: "Secret Other User Item", checked: false, is_private: true, private_owner_id: "user-A" },
          ],
        },
      })
    })
    expect(screen.getByText("Remote Passport")).toBeDefined()
    // Foreign private item MUST NOT leak into live DOM via tabiji:collab-event!
    expect(screen.queryByText("Secret Other User Item")).toBeNull()

    // Parent re-render with stable empty prop reference MUST NOT clobber live collab state
    rerender(<RealtimeHarness tick={1} />)
    expect(screen.getByText("Remote Passport")).toBeDefined()
    expect(screen.queryByText("Secret Other User Item")).toBeNull()

    // Verify SWR mutate predicate & optimistic updater + revalidate: true
    expect(mockSwrMutate).toHaveBeenCalledTimes(1)
    const [matcher, updater, opts] = mockSwrMutate.mock.calls[0]
    expect(matcher(["/api/trips/trip-rt-1", "user-B"])).toBe(true)
    expect(matcher(["/api/trips/other-trip", "user-B"])).toBe(false)
    expect(opts).toEqual({ revalidate: true })
    const patchedTrip = updater({ id: "trip-rt-1", day_checklists: { 0: [{ id: "old0", text: "Old Day0", checked: false }] } })
    expect(patchedTrip.day_checklists[1]).toEqual([{ id: "r1", text: "Remote Passport", checked: true }])
    expect(patchedTrip.day_checklists[0]).toEqual([])

    // 3. Remote tip:update syncs day_costs in SWR cache and rejects empty-string dayIndex ("") without corrupting Day 0
    act(() => {
      collabCb({
        payload: {
          event: "tip:update",
          senderSessionId: "remote-session-xyz",
          dayIndex: 2,
          type: "costs",
          data: [
            { item: "壽司", amount: "3000", currency: "JPY" },
            { item: "他人秘密花費", amount: "9999", currency: "JPY", is_private: true, private_owner_id: "user-A" },
          ],
        },
      })
    })
    expect(mockSwrMutate).toHaveBeenCalledTimes(2)
    const [, tipUpdater, tipOpts] = mockSwrMutate.mock.calls[1]
    expect(tipOpts).toEqual({ revalidate: true })
    const patchedCostsTrip = tipUpdater({ id: "trip-rt-1", day_costs: {} })
    expect(patchedCostsTrip.day_costs[2]).toEqual([{ item: "壽司", amount: "3000", currency: "JPY" }])

    // Empty-string dayIndex must NOT coerce to Day 0
    act(() => {
      collabCb({
        payload: {
          event: "checklist:update",
          senderSessionId: "remote-session-xyz",
          dayIndex: "",
          items: [{ id: "bad", text: "Bad Day0", checked: false }],
        },
      })
    })
    const [, emptyDayUpdater] = mockSwrMutate.mock.calls[2]
    const unchanged = { id: "trip-rt-1", day_checklists: { 0: [{ id: "orig", text: "Keep", checked: false }] } }
    expect(emptyDayUpdater(unchanged)).toBe(unchanged)
  })

  it("reg_p2_6_7_8: IconPicker sequential replacement & preset reset & opaque collisionPadding, CurrencyPillSelector auto-scroll & localized aria-label, and responsive flex-wrap headers", () => {
    const scrollIntoViewMock = vi.fn()
    const origScrollIntoView = HTMLElement.prototype.scrollIntoView
    HTMLElement.prototype.scrollIntoView = scrollIntoViewMock

    try {
      const { container } = render(
        <div>
          <EditableDailyTips
            tripId="trip-1"
            day={1}
            notes={[{ icon: "⚠️", title: "Note 1", content: "" }]}
            costs={[{ item: "London Tube", amount: "15", currency: "GBP", note: "Zone 1" }]}
            tickets={[{ name: "Eurostar", price: "80", currency: "GBP", note: "Car 4" }]}
            defaultCurrency="JPY"
            onUpdate={vi.fn().mockResolvedValue(true)}
          />
          <EditableDailyChecklist
            tripId="trip-1"
            day={1}
            items={[{ id: "c1", text: "護照", checked: false }]}
            onUpdate={vi.fn().mockResolvedValue(true)}
          />
        </div>
      )

      // P2 #7: Card headers use flex-wrap and do NOT use truncate on card headings (prevents 10px crush at 320px + 130%)
      const headings = container.querySelectorAll("h4")
      expect(headings.length).toBe(3)
      headings.forEach((h) => {
        expect(h.className).not.toContain("truncate")
        expect(h.parentElement?.parentElement?.className).toContain("flex-wrap")
      })

      // P2 #6: IconPicker sequential replacement ("🍜" -> "🍜🍕" -> "🍕") & preset reset
      fireEvent.click(screen.getAllByRole("button", { name: /新增/ })[0]) // Notes Add
      const iconTrigger = screen.getByRole("button", { name: "選擇圖示" })
      fireEvent.click(iconTrigger)
      const popoverEl = document.querySelector('[data-slot="popover-content"]')
      expect(popoverEl?.className).toContain("bg-white")
      expect(popoverEl?.className).not.toContain("bg-white/98")

      const customInput = screen.getByPlaceholderText("貼上或輸入自訂 Emoji") as HTMLInputElement
      fireEvent.change(customInput, { target: { value: "🍜" } })
      expect(customInput.value).toBe("🍜")
      expect(iconTrigger.textContent).toBe("🍜")

      // Typing "🍕" after existing "🍜" produces "🍜🍕" -> MUST replace with "🍕"
      fireEvent.change(customInput, { target: { value: "🍜🍕" } })
      expect(customInput.value).toBe("🍕")
      expect(iconTrigger.textContent).toBe("🍕")

      // Pasting a no-space multi-grapheme phrase starting with current emoji ("🍕披薩推薦") MUST keep first grapheme "🍕", NOT "披"
      fireEvent.change(customInput, { target: { value: "🍕披薩推薦" } })
      expect(customInput.value).toBe("🍕")
      expect(iconTrigger.textContent).toBe("🍕")

      // Clicking a preset emoji clears customValue so reopening shows blank input
      fireEvent.click(screen.getByRole("button", { name: "✈️" }))
      expect(iconTrigger.textContent).toBe("✈️")
      fireEvent.click(iconTrigger)
      expect((screen.getByPlaceholderText("貼上或輸入自訂 Emoji") as HTMLInputElement).value).toBe("")
      // Escape during IME composition inside IconPicker MUST NOT dismiss Popover
      const escComposing = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })
      Object.defineProperty(escComposing, "isComposing", { value: true })
      screen.getByPlaceholderText("貼上或輸入自訂 Emoji").dispatchEvent(escComposing)
      expect(screen.getByPlaceholderText("貼上或輸入自訂 Emoji")).toBeDefined()
      fireEvent.keyDown(screen.getByPlaceholderText("貼上或輸入自訂 Emoji"), { key: "Escape" })

      // P2 #8: CurrencyPillSelector auto-scrolls trailing custom currency ("GBP") into view & localizes aria-label
      fireEvent.click(screen.getAllByRole("button", { name: /編輯/ })[1]) // Costs Edit
      const currencyGroup = screen.getByRole("group", { name: "選擇幣別" })
      expect(currencyGroup).toBeDefined()
      expect(scrollIntoViewMock).toHaveBeenCalledWith({ inline: "nearest", block: "nearest" })
    } finally {
      HTMLElement.prototype.scrollIntoView = origScrollIntoView
    }
  })

  it("reg_p3_9: EditableDailyAIReview uses semantic aria-expanded button with zero nested buttons, honors readOnly, and IOSBottomSheet localizes Close aria-label", () => {
    const { container, rerender } = render(
      <EditableDailyAIReview
        tripId="trip-1"
        day={1}
        review={"🎯 行程綜合評分：90 分\n1. 順暢"}
        onUpdate={vi.fn()}
      />
    )

    // Zero nested <button> elements
    expect(container.querySelectorAll("button button").length).toBe(0)

    const toggleBtn = screen.getByRole("button", { name: /AI 深度審核報告/ })
    expect(toggleBtn.getAttribute("aria-expanded")).toBe("true")
    fireEvent.click(toggleBtn)
    expect(toggleBtn.getAttribute("aria-expanded")).toBe("false")
    expect(screen.getByRole("button", { name: "重新審核" })).toBeDefined()
    expect(screen.getByRole("button", { name: "清除審核" })).toBeDefined()

    // readOnly hides Re-review & Clear in populated state, and hides Generate in empty state
    rerender(
      <EditableDailyAIReview
        tripId="trip-1"
        day={1}
        review={"🎯 行程綜合評分：90 分\n1. 順暢"}
        readOnly={true}
        onUpdate={vi.fn()}
      />
    )
    expect(screen.queryByRole("button", { name: "重新審核" })).toBeNull()
    expect(screen.queryByRole("button", { name: "清除審核" })).toBeNull()

    rerender(
      <EditableDailyAIReview
        tripId="trip-1"
        day={1}
        review={undefined}
        readOnly={true}
        onUpdate={vi.fn()}
      />
    )
    expect(screen.queryByRole("button", { name: /生成 AI 深度審核報告/ })).toBeNull()

    // IOSBottomSheet localized close aria-label: zh -> "關閉", en -> "Close"
    const { rerender: rerenderSheet } = render(
      <IOSBottomSheet isOpen={true} activeTab="tips" onClose={vi.fn()} onTabChange={vi.fn()}>
        <div>Sheet Body</div>
      </IOSBottomSheet>
    )
    expect(screen.getByLabelText("關閉")).toBeDefined()

    mockLang = "en"
    rerenderSheet(
      <IOSBottomSheet isOpen={true} activeTab="tips" onClose={vi.fn()} onTabChange={vi.fn()}>
        <div>Sheet Body</div>
      </IOSBottomSheet>
    )
    expect(screen.getByLabelText("Close")).toBeDefined()

    // P3 #9: Verify CostItem & TicketItem type fields in itinerary-types.ts & collisionPadding={12} in EditableDailyTips.tsx
    const typesSrc = fs.readFileSync(path.join(frontendDir, "lib/itinerary-types.ts"), "utf-8")
    expect(typesSrc).toMatch(/export interface CostItem[\s\S]*currency\?: string[\s\S]*is_private\?: boolean[\s\S]*private_owner_id\?: string/)
    expect(typesSrc).toMatch(/export interface TicketItem[\s\S]*currency\?: string[\s\S]*is_private\?: boolean[\s\S]*private_owner_id\?: string/)

    const tipsSrc = fs.readFileSync(path.join(frontendDir, "components/itinerary/EditableDailyTips.tsx"), "utf-8")
    expect(tipsSrc).toContain("collisionPadding={12}")
  })

  it("reg_r2_hardening: normalizes untrimmed currencies without duplicate pills and filters foreign private items on direct tip:update collab events", () => {
    render(
      <EditableDailyTips
        tripId="trip-1"
        day={1}
        displaySection="costs"
        notes={[]}
        costs={[{ item: "拉麵", amount: "1200", currency: " jpy " }]}
        tickets={[]}
        defaultCurrency="JPY"
        userId="user-B"
        onUpdate={vi.fn().mockResolvedValue(true)}
      />
    )

    // Untrimmed lowercase " jpy " must normalize to "JPY" without creating a duplicate pill
    fireEvent.click(screen.getByRole("button", { name: /編輯/ }))
    expect(screen.getAllByRole("button", { name: /^JPY$/i })).toHaveLength(1)
    fireEvent.click(screen.getByRole("button", { name: /取消/ }))

    // Direct tabiji:collab-event tip:update must filter foreign private items from live DOM
    act(() => {
      window.dispatchEvent(
        new CustomEvent("tabiji:collab-event", {
          detail: {
            event: "tip:update",
            dayIndex: 1,
            type: "costs",
            data: [
              { item: "公開拉麵", amount: "1200", currency: "JPY" },
              { item: "他人秘密伴手禮", amount: "5000", currency: "JPY", is_private: true, private_owner_id: "user-A" },
              { item: "我的私人花費", amount: "800", currency: "JPY", is_private: true, private_owner_id: "user-B" },
            ],
          },
        })
      )
    })
    expect(screen.getByText("公開拉麵")).toBeDefined()
    expect(screen.getByText("我的私人花費")).toBeDefined()
    expect(screen.queryByText("他人秘密伴手禮")).toBeNull()
  })
})
