import React from "react"
import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import ItineraryDashboardHub from "@/components/itinerary/ItineraryDashboardHub"
import { CapsuleProgressSummary } from "@/lib/itinerary-types"

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

describe("Trip Time Capsule Hero & Layout Tests", () => {
  it("renders Capsule Hero Card at the top and triggers onCapsuleClick", () => {
    const handleCapsuleClick = vi.fn()
    const handleSelectTab = vi.fn()

    const mockSummary: CapsuleProgressSummary = {
      trip_id: "trip-123",
      is_unlocked: false,
      total_members: 3,
      submitted_members_count: 1,
      has_current_user_submitted: false,
      my_entries: [],
      revealed_entries: []
    }

    render(
      <ItineraryDashboardHub
        day={1}
        capsuleSummary={mockSummary}
        onCapsuleClick={handleCapsuleClick}
        onSelectTab={handleSelectTab}
      />
    )

    // Verify capsule card title and count
    expect(screen.getByText("Day 1 旅伴時光膠囊")).toBeDefined()
    expect(screen.getByText("未封存")).toBeDefined()
    expect(screen.getByText("👥 1/3 人")).toBeDefined()
    expect(screen.getByText("點擊記錄今日秘密真心話與拍立得，旅後全體解鎖 ✨")).toBeDefined()

    // Trigger click on capsule card
    fireEvent.click(screen.getByText("Day 1 旅伴時光膠囊"))
    expect(handleCapsuleClick).toHaveBeenCalledTimes(1)
  })

  it("renders unlocked status correctly when trip is finished", () => {
    const mockSummary: CapsuleProgressSummary = {
      trip_id: "trip-123",
      is_unlocked: true,
      total_members: 3,
      submitted_members_count: 3,
      has_current_user_submitted: true,
      my_entries: [],
      revealed_entries: []
    }

    render(
      <ItineraryDashboardHub
        day={1}
        capsuleSummary={mockSummary}
        onCapsuleClick={vi.fn()}
        onSelectTab={vi.fn()}
      />
    )

    expect(screen.getByText("已破印")).toBeDefined()
    expect(screen.getByText("🎉 膠囊已解鎖！點擊啟動回憶揭曉盛典 (3D 翻轉卡牌)")).toBeDefined()
    expect(screen.getByText("啟動盛典")).toBeDefined()
  })

  it("renders submitted status when user has sealed their entry", () => {
    const mockSummary: CapsuleProgressSummary = {
      trip_id: "trip-123",
      is_unlocked: false,
      total_members: 2,
      submitted_members_count: 2,
      has_current_user_submitted: true,
      my_entries: [],
      revealed_entries: []
    }

    render(
      <ItineraryDashboardHub
        day={1}
        capsuleSummary={mockSummary}
        onCapsuleClick={vi.fn()}
        onSelectTab={vi.fn()}
      />
    )

    expect(screen.getByText("已封存")).toBeDefined()
    expect(screen.getByText("你的今日真心話已安全封存，回國前旅伴無法偷看 🔒")).toBeDefined()
  })

  it("renders sample guidance mode when isSample is true", () => {
    const handleCapsuleClick = vi.fn()

    render(
      <ItineraryDashboardHub
        day={1}
        isSample={true}
        capsuleSummary={null}
        onCapsuleClick={handleCapsuleClick}
        onSelectTab={vi.fn()}
      />
    )

    expect(screen.getByText("旅伴時光膠囊功能導覽")).toBeDefined()
    expect(screen.getByText("單人範本")).toBeDefined()
    expect(screen.getByText("範本")).toBeDefined()
    expect(screen.getByText("💡 範本行程僅供體驗。建立專屬自訂行程並邀請旅伴，即可共同封存膠囊！")).toBeDefined()

    fireEvent.click(screen.getByText("旅伴時光膠囊功能導覽"))
    expect(handleCapsuleClick).toHaveBeenCalledTimes(1)
  })
})
