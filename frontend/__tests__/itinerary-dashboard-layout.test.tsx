import React from "react"
import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import ItineraryDashboardHub from "@/components/itinerary/ItineraryDashboardHub"
import IOSBottomSheet from "@/components/itinerary/IOSBottomSheet"

// Mock hooks & language context
vi.mock("@/lib/LanguageContext", () => ({
  useLanguage: () => ({ lang: "zh", t: (k: string) => k })
}))

vi.mock("@/lib/hooks", () => ({
  useHaptic: () => ({
    tap: vi.fn(),
    selection: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
    custom: vi.fn(),
  })
}))

describe("ItineraryDashboardHub Component", () => {
  it("renders full-width AI Review card and 2x2 grid cards properly", () => {
    const handleSelectTab = vi.fn()
    render(
      <ItineraryDashboardHub
        day={1}
        review="🎯 行程綜合評分：94 分（極佳）\n✅ 規劃順暢"
        notes={[{ icon: "⚠️", title: "穿著防滑鞋", content: "路面濕滑" }]}
        costs={[{ item: "拉麵", amount: "1,200", currency: "JPY" }]}
        tickets={[{ name: "JR Pass", price: "28,000", currency: "JPY" }]}
        dayChecklists={{ "1": [{ id: "c1", text: "護照", checked: true }] }}
        onSelectTab={handleSelectTab}
      />
    )

    // Check full-width AI review card exists and displays extracted score
    expect(screen.getByText("AI 深度審核報告")).toBeDefined()
    expect(screen.getByText("94")).toBeDefined()

    // Check 2x2 grid cards exist
    expect(screen.getByText("每日重點提醒")).toBeDefined()
    expect(screen.getByText("穿著防滑鞋", { exact: false })).toBeDefined()

    expect(screen.getByText("預估花費")).toBeDefined()
    expect(screen.getByText("JPY 1,200")).toBeDefined()

    expect(screen.getByText("交通票券")).toBeDefined()
    expect(screen.getByText("JR Pass")).toBeDefined()

    expect(screen.getByText("行前清單")).toBeDefined()
    expect(screen.getByText("完成")).toBeDefined()
  })

  it("triggers onSelectTab with correct identifier when card is tapped", () => {
    const handleSelectTab = vi.fn()
    render(
      <ItineraryDashboardHub
        day={1}
        onSelectTab={handleSelectTab}
      />
    )

    // Click AI review card
    fireEvent.click(screen.getByText("AI 深度審核報告"))
    expect(handleSelectTab).toHaveBeenCalledWith("ai_review")

    // Click Checklist card (now Card 2)
    fireEvent.click(screen.getByText("行前清單"))
    expect(handleSelectTab).toHaveBeenCalledWith("checklist")

    // Click Costs card (now Card 4)
    fireEvent.click(screen.getByText("預估花費"))
    expect(handleSelectTab).toHaveBeenCalledWith("costs")
  })

  it("verifies 2x2 grid card order: Tips -> Checklist -> Tickets -> Costs", () => {
    render(
      <ItineraryDashboardHub
        day={1}
        costs={[{ item: "壽司", amount: "3,000", currency: "JPY" }]}
        dayChecklists={{ "1": [{ id: "c1", text: "護照", checked: false }] }}
        onSelectTab={vi.fn()}
      />
    )

    // Get all 4 grid buttons
    const buttons = screen.getAllByRole("button")
    // Filter the 4 2x2 grid buttons (excluding the AI review full-width banner)
    const gridButtons = buttons.filter(btn => 
      btn.textContent?.includes("每日重點提醒") ||
      btn.textContent?.includes("行前清單") ||
      btn.textContent?.includes("交通票券") ||
      btn.textContent?.includes("預估花費")
    )

    expect(gridButtons).toHaveLength(4)
    expect(gridButtons[0].textContent).toContain("每日重點提醒")
    expect(gridButtons[1].textContent).toContain("行前清單")
    expect(gridButtons[2].textContent).toContain("交通票券")
    expect(gridButtons[3].textContent).toContain("預估花費")
  })
})

describe("IOSBottomSheet Component", () => {
  it("renders 5-column pure-icon capsule tabs in strict order with zero visible text, dynamic header, z-115 layer, and dismiss button", () => {
    const handleClose = vi.fn()
    const handleTabChange = vi.fn()

    const { rerender } = render(
      <IOSBottomSheet
        isOpen={true}
        activeTab="ai_review"
        onClose={handleClose}
        onTabChange={handleTabChange}
        tabIndicators={{ ai_review: true, tips: false, checklist: true, tickets: false, costs: true }}
      >
        <div data-testid="sheet-child">Inner Sheet Content</div>
      </IOSBottomSheet>
    )

    expect(screen.getByTestId("sheet-child")).toBeDefined()

    // 🛡️ Layer safety: z-115 floats cleanly above standby AI orb (z-110)
    const dialog = screen.getByRole("dialog")
    expect(dialog.className).toContain("z-115")

    // 🛡️ Dynamic header reflects active tab
    expect(dialog.textContent).toContain("當日智慧看板")
    expect(dialog.textContent).toContain("AI 審核")

    // 🛡️ 5-column pure-icon frosted capsule (zero horizontal scroll, zero visible text)
    const tablist = screen.getByRole("tablist")
    expect(tablist.className).toContain("grid-cols-5")
    expect(tablist.className).not.toContain("overflow-x-auto")

    const expectedLabels = ["AI 審核", "重點提醒", "行前清單", "交通票券", "預估花費"]
    const tabs = screen.getAllByRole("tab")
    expect(tabs).toHaveLength(5)
    expect(tabs.map((tab) => tab.getAttribute("aria-label"))).toEqual(expectedLabels)
    expect(tabs.map((tab) => tab.getAttribute("title"))).toEqual(expectedLabels)
    for (const tab of tabs) {
      expect(tab.textContent?.trim()).toBe("")
      expect(tab.className).toContain("h-11")
    }
    expect(tabs[0].getAttribute("aria-selected")).toBe("true")
    expect(tabs[2].getAttribute("aria-selected")).toBe("false")

    // 🛡️ Micro-dot indicators strictly reflect tabIndicators prop
    expect(screen.getByTestId("tab-indicator-ai_review")).toBeDefined()
    expect(screen.getByTestId("tab-indicator-checklist")).toBeDefined()
    expect(screen.getByTestId("tab-indicator-costs")).toBeDefined()
    expect(screen.queryByTestId("tab-indicator-tips")).toBeNull()
    expect(screen.queryByTestId("tab-indicator-tickets")).toBeNull()

    // Switch tab to checklist via accessible name
    fireEvent.click(screen.getByRole("tab", { name: "行前清單" }))
    expect(handleTabChange).toHaveBeenCalledWith("checklist")

    // Switch tab to costs via accessible name
    fireEvent.click(screen.getByRole("tab", { name: "預估花費" }))
    expect(handleTabChange).toHaveBeenCalledWith("costs")

    // Keyboard roving navigation (ArrowRight from ai_review -> tips)
    fireEvent.keyDown(tabs[0], { key: "ArrowRight" })
    expect(handleTabChange).toHaveBeenCalledWith("tips")

    // Rerender with checklist active and verify dynamic header syncs
    rerender(
      <IOSBottomSheet
        isOpen={true}
        activeTab="checklist"
        onClose={handleClose}
        onTabChange={handleTabChange}
      >
        <div data-testid="sheet-child">Inner Sheet Content</div>
      </IOSBottomSheet>
    )
    expect(screen.getByRole("dialog").textContent).toContain("行前清單")
    // Backward compatibility: omitting tabIndicators renders zero dots
    expect(screen.queryByTestId("tab-indicator-ai_review")).toBeNull()

    // Click close button (localized zh aria-label)
    const closeBtn = screen.getByLabelText("關閉")
    fireEvent.click(closeBtn)
    expect(handleClose).toHaveBeenCalled()
  })

  it("enforces fourfold scroll axis-lock + safe-area bottom inset and activates tabs[0] cleanly on unknown activeTab", () => {
    render(
      <IOSBottomSheet
        isOpen={true}
        activeTab={"unknown_tab" as unknown as "ai_review"}
        onClose={vi.fn()}
        onTabChange={vi.fn()}
      >
        <div data-testid="sheet-fallback-child">Fallback Content</div>
      </IOSBottomSheet>
    )

    const child = screen.getByTestId("sheet-fallback-child")
    const scrollContainer = child.parentElement!
    expect(scrollContainer.className).toContain("min-h-0")
    expect(scrollContainer.className).toContain("overflow-y-auto")
    expect(scrollContainer.className).toContain("overflow-x-hidden")
    expect(scrollContainer.className).toContain("overscroll-x-none")
    expect(scrollContainer.className).toContain("overscroll-y-contain")
    expect(scrollContainer.className).toContain("touch-pan-y")
    expect(scrollContainer.className).toContain("safe-area-inset-bottom")
    expect(screen.getByRole("dialog").textContent).toContain("AI 審核")

    // Normalized fallback must select tabs[0] and keep tablist keyboard-reachable (tabIndex=0)
    const tabs = screen.getAllByRole("tab")
    expect(tabs[0].getAttribute("aria-selected")).toBe("true")
    expect(tabs[0].getAttribute("tabindex")).toBe("0")
    expect(tabs[1].getAttribute("aria-selected")).toBe("false")
    expect(tabs[1].getAttribute("tabindex")).toBe("-1")
  })

  it("does NOT close on Escape while a higher-layer Radix Dialog or Popover is open, and closes cleanly once clear", () => {
    const handleClose = vi.fn()
    render(
      <IOSBottomSheet
        isOpen={true}
        activeTab="checklist"
        onClose={handleClose}
        onTabChange={vi.fn()}
      >
        <div data-testid="sheet-esc-child">Checklist Content</div>
      </IOSBottomSheet>
    )

    // Simulate SessionReauthModal (Radix DialogContent) open on top of IOSBottomSheet
    const mockReauthDialog = document.createElement("div")
    mockReauthDialog.setAttribute("data-slot", "dialog-content")
    mockReauthDialog.setAttribute("data-state", "open")
    document.body.appendChild(mockReauthDialog)

    fireEvent.keyDown(window, { key: "Escape" })
    expect(handleClose).not.toHaveBeenCalled()

    // Simulate emoji Popover open on top of IOSBottomSheet
    document.body.removeChild(mockReauthDialog)
    const mockPopover = document.createElement("div")
    mockPopover.setAttribute("data-slot", "popover-content")
    mockPopover.setAttribute("data-state", "open")
    document.body.appendChild(mockPopover)

    fireEvent.keyDown(window, { key: "Escape" })
    expect(handleClose).not.toHaveBeenCalled()

    // Once higher overlays close, Escape dismisses IOSBottomSheet normally
    document.body.removeChild(mockPopover)
    fireEvent.keyDown(window, { key: "Escape" })
    expect(handleClose).toHaveBeenCalledTimes(1)
  })
})
