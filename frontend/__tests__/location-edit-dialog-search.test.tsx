/**
 * @vitest-environment jsdom
 */
import React from "react"
import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { LocationEditDialog } from "@/components/itinerary/LocationEditDialog"
import { geocodeApi } from "@/lib/api"

vi.mock("@/lib/LanguageContext", () => ({
  useLanguage: () => ({
    lang: "zh",
    t: (k: string, opt?: Record<string, string>) => {
      if (opt?.day) return `修改第 ${opt.day} 天當日地點`
      if (opt?.name) return `已更新為 ${opt.name}`
      const map: Record<string, string> = {
        loc_search: "搜尋地點",
        loc_search_placeholder: "搜尋地點...",
        loc_current: "目前地點",
        loc_auto_sync: "自動同步",
      }
      return map[k] || k
    }
  })
}))

vi.mock("@/lib/api", () => ({
  geocodeApi: {
    search: vi.fn()
  }
}))

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn()
  }
}))

describe("LocationEditDialog - Country Typeahead & Place Search", () => {
  it("renders country input with datalist and region selector", () => {
    render(
      <LocationEditDialog
        isOpen={true}
        onOpenChange={vi.fn()}
        day={1}
        dailyLocs={{
          1: { name: "故宮博物院", lat: 25.1024, lng: 121.5485 }
        }}
        setDailyLocs={vi.fn()}
      />
    )

    // Check current location is displayed with coords in dialog
    expect(screen.getByText("故宮博物院")).toBeDefined()
    expect(screen.getByText("25.1024, 121.5485")).toBeDefined()

    // 🛡️ Country input has datalist connected
    const countryInput = screen.getByPlaceholderText(/🌍 國家/) as HTMLInputElement
    expect(countryInput).toBeDefined()
    expect(countryInput.getAttribute("list")).toBe("loc-edit-country-options")

    // Check datalist options exist
    const datalist = document.getElementById("loc-edit-country-options")
    expect(datalist).toBeDefined()
    expect(datalist?.querySelector('option[value="Taiwan"]')).toBeDefined()
    expect(datalist?.querySelector('option[value="Japan"]')).toBeDefined()
  })

  it("triggers geocode search with structured country and query parameters", async () => {
    const mockSearch = vi.mocked(geocodeApi.search)
    mockSearch.mockResolvedValueOnce({
      results: [
        {
          name: "台北 101",
          address: "台北市信義區信義路五段7號",
          lat: 25.0339,
          lng: 121.5644,
          type: "attraction"
        }
      ]
    })

    const setDailyLocs = vi.fn()
    const onOpenChange = vi.fn()

    render(
      <LocationEditDialog
        isOpen={true}
        onOpenChange={onOpenChange}
        day={1}
        dailyLocs={{}}
        setDailyLocs={setDailyLocs}
      />
    )

    const countryInput = screen.getByPlaceholderText(/🌍 國家/)
    const searchInput = screen.getByPlaceholderText("搜尋地點...")

    // Type country and query
    fireEvent.change(countryInput, { target: { value: "Taiwan" } })
    fireEvent.change(searchInput, { target: { value: "台北 101" } })

    // Submit search via Enter
    fireEvent.keyDown(searchInput, { key: "Enter" })

    await waitFor(() => {
      expect(mockSearch).toHaveBeenCalledWith(
        expect.objectContaining({
          query: "台北 101",
          country: "Taiwan"
        })
      )
    })

    // Search result is displayed
    await waitFor(() => {
      expect(screen.getByText("台北 101")).toBeDefined()
    })

    // Click result to apply
    fireEvent.click(screen.getByText("台北 101"))

    expect(setDailyLocs).toHaveBeenCalledWith(
      expect.objectContaining({
        1: {
          name: "台北 101",
          lat: 25.0339,
          lng: 121.5644
        }
      })
    )
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
