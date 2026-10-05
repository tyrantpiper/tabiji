import React from "react"
import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { WeatherPanel } from "@/components/itinerary/WeatherPanel"
import { DayWeather } from "@/lib/itinerary-types"

// Mock hooks & language context
const translations: Record<string, string> = {
  w_apparent: "體感溫度",
  w_rain_prob: "降雨與濕度",
  w_uv: "紫外線指數",
  w_clothing: "穿衣",
  w_wind: "風速",
  w_humidity: "相對濕度",
  w_elevation: "海拔",
  w_ecmwf_badge: "ECMWF",
}

vi.mock("@/lib/LanguageContext", () => ({
  useLanguage: () => ({
    lang: "zh",
    t: (k: string, opt?: Record<string, string>) => {
      if (opt?.wbgt) return `WBGT ${opt.wbgt}`
      if (opt?.value) return `信心度 ${opt.value}%`
      return translations[k] || k
    }
  })
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

const mockWeatherData: DayWeather[] = [
  { time: "09:00", temp: 22, code: 1, precipitation_probability: 10, humidity: 55, uvIndex: 4, windSpeed: 12, apparent_temperature: 21 },
  { time: "12:00", temp: 26, code: 0, precipitation_probability: 35, humidity: 50, uvIndex: 6, windSpeed: 15, apparent_temperature: 25 },
  { time: "15:00", temp: 24, code: 61, precipitation_probability: 80, humidity: 75, uvIndex: 3, windSpeed: 18, apparent_temperature: 24 },
  { time: "18:00", temp: 19, code: 2, precipitation_probability: 15, humidity: 65, uvIndex: 1, windSpeed: 10, apparent_temperature: 18 },
]

describe("WeatherPanel - iOS Bento Grid System", () => {
  it("renders Hero temperature, location, and AI attire capsule in collapsed mode", () => {
    const handleEditLocation = vi.fn()
    render(
      <WeatherPanel
        day={1}
        weatherData={mockWeatherData}
        weatherMode="live"
        weatherConfidence={90}
        elevation={45}
        resolvedLocation={{ name: "京都車站", lat: 34.9858, lng: 135.7588 }}
        currentTimezone="Asia/Tokyo"
        onEditLocation={handleEditLocation}
      />
    )

    // Check location
    expect(screen.getByText("京都車站")).toBeDefined()

    // Check Hero current temp (Math.round(22) = 22°)
    expect(screen.getAllByText("22°").length).toBeGreaterThan(0)

    // Check High / Low
    expect(screen.getByText("H:26°")).toBeDefined()
    expect(screen.getByText("L:19°")).toBeDefined()

    // Check AI attire capsule
    expect(screen.getByText("穿衣指南：", { exact: false })).toBeDefined()

    // Check 24h scrubber conditional precipitation (35% and 80% should appear, 10% and 15% should be hidden)
    expect(screen.getByText("35%")).toBeDefined()
    expect(screen.getByText("80%")).toBeDefined()
    expect(screen.queryByText("10%")).toBeNull()
    expect(screen.queryByText("15%")).toBeNull()

    // Bento 2x2 should NOT be visible initially (collapsed state)
    expect(screen.queryByText("體感溫度")).toBeNull()
  })

  it("toggles 2x2 Bento Matrix smoothly on expand button click", () => {
    render(
      <WeatherPanel
        day={1}
        weatherData={mockWeatherData}
        weatherMode="forecast"
        weatherConfidence={85}
        elevation={120}
        resolvedLocation={{ name: "淺草寺", lat: 35.7148, lng: 139.7967 }}
        currentTimezone="Asia/Tokyo"
        onEditLocation={vi.fn()}
      />
    )

    // Click expand
    const expandButton = screen.getByText("查看詳細氣象")
    fireEvent.click(expandButton)

    // Verify 4 Bento cards exist in expanded mode
    expect(screen.getByText("體感溫度")).toBeDefined()
    expect(screen.getByText("降雨與濕度")).toBeDefined()
    expect(screen.getByText("紫外線指數")).toBeDefined()
    expect(screen.getByText("風速與空氣")).toBeDefined()

    // Click collapse
    const collapseButton = screen.getByText("收合詳細氣象")
    fireEvent.click(collapseButton)
  })

  it("🛡️ 溫差除以零邊界守衛：全天恆溫 (max === min) 絕不崩潰且不產生 NaN", () => {
    const overcastConstantData: DayWeather[] = [
      { time: "09:00", temp: 15, code: 3, precipitation_probability: 20 },
      { time: "12:00", temp: 15, code: 3, precipitation_probability: 20 },
    ]

    render(
      <WeatherPanel
        day={2}
        weatherData={overcastConstantData}
        weatherMode="live"
        weatherConfidence={70}
        elevation={10}
        resolvedLocation={{ name: "札幌", lat: 43.0618, lng: 141.3545 }}
        currentTimezone="Asia/Tokyo"
        onEditLocation={vi.fn()}
      />
    )

    expect(screen.getByText("H:15°")).toBeDefined()
    expect(screen.getByText("L:15°")).toBeDefined()
    expect(screen.getAllByText("15°").length).toBeGreaterThan(0)
  })

  it("🛡️ 空陣列離線防護：無氣象資料時安全降級為骨架屏，無 NaN 或報錯", () => {
    render(
      <WeatherPanel
        day={3}
        weatherData={[]}
        weatherMode="live"
        weatherConfidence={null}
        elevation={null}
        resolvedLocation={null}
        currentTimezone="Asia/Tokyo"
        onEditLocation={vi.fn()}
      />
    )

    expect(screen.getByText("--°")).toBeDefined()
    expect(screen.getByText("--° / --°")).toBeDefined()
  })
})
