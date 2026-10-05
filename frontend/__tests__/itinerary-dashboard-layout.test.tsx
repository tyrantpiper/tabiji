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

    // Click Costs card
    fireEvent.click(screen.getByText("預估花費"))
    expect(handleSelectTab).toHaveBeenCalledWith("costs")
  })
})

describe("IOSBottomSheet Component", () => {
  it("renders segmented control tabs and dismiss button when open", () => {
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
    expect(screen.getByText("AI 審核")).toBeDefined()
    expect(screen.getByText("重點提醒")).toBeDefined()
    expect(screen.getByText("預估花費")).toBeDefined()
    expect(screen.getByText("交通票券")).toBeDefined()
    expect(screen.getByText("行前清單")).toBeDefined()

    // Switch tab
    fireEvent.click(screen.getByText("預估花費"))
    expect(handleTabChange).toHaveBeenCalledWith("costs")

    // Click close button
    const closeBtn = screen.getByLabelText("Close")
    fireEvent.click(closeBtn)
    expect(handleClose).toHaveBeenCalled()
  })
})
