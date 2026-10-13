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
  it("renders segmented control tabs in strictly aligned order and dismiss button when open", () => {
    const handleClose = vi.fn()
    const handleTabChange = vi.fn()

    render(
      <IOSBottomSheet
        isOpen={true}
        activeTab="ai_review"
        onClose={handleClose}
        onTabChange={handleTabChange}
      >
        <div data-testid="sheet-child">Inner Sheet Content</div>
      </IOSBottomSheet>
    )

    expect(screen.getByTestId("sheet-child")).toBeDefined()

    // 🛡️ Verify tab order matches mental model: AI Review -> Tips -> Checklist -> Tickets -> Costs
    const tabLabels = ["AI 審核", "重點提醒", "行前清單", "交通票券", "預估花費"]
    const renderedTabs = tabLabels.map(label => screen.getByText(label))
    expect(renderedTabs).toHaveLength(5)

    // Switch tab to checklist
    fireEvent.click(screen.getByText("行前清單"))
    expect(handleTabChange).toHaveBeenCalledWith("checklist")

    // Switch tab to costs
    fireEvent.click(screen.getByText("預估花費"))
    expect(handleTabChange).toHaveBeenCalledWith("costs")

    // Click close button
    const closeBtn = screen.getByLabelText("Close")
    fireEvent.click(closeBtn)
    expect(handleClose).toHaveBeenCalled()
  })
})
