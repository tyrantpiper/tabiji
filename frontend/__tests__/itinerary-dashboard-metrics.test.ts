import { describe, it, expect } from "vitest"
import {
  calculateDayCostsSummary,
  calculateChecklistProgress,
  extractAIReviewHighlights
} from "../lib/itinerary-metrics"

describe("itinerary-metrics - calculateDayCostsSummary", () => {
  it("handles empty or undefined costs gracefully", () => {
    expect(calculateDayCostsSummary([], "JPY")).toEqual({
      primaryTotal: 0,
      primaryCurrency: "JPY",
      hasMultipleCurrencies: false,
    })
    expect(calculateDayCostsSummary(undefined as unknown as Array<{ amount?: string }>, "USD")).toEqual({
      primaryTotal: 0,
      primaryCurrency: "USD",
      hasMultipleCurrencies: false,
    })
  })

  it("handles comma-separated and string amounts without NaN", () => {
    const costs = [
      { amount: "1,500", currency: "JPY" },
      { amount: "3,250.50", currency: "JPY" },
      { amount: " 250 ", currency: "JPY" },
    ]
    const summary = calculateDayCostsSummary(costs, "JPY")
    expect(summary.primaryTotal).toBe(5000.5)
    expect(summary.primaryCurrency).toBe("JPY")
    expect(summary.hasMultipleCurrencies).toBe(false)
  })

  it("detects multiple currencies and isolates primary currency", () => {
    const costs = [
      { amount: "1000", currency: "JPY" },
      { amount: "500", currency: "TWD" },
    ]
    const summary = calculateDayCostsSummary(costs, "JPY")
    expect(summary.primaryTotal).toBe(1000)
    expect(summary.primaryCurrency).toBe("JPY")
    expect(summary.hasMultipleCurrencies).toBe(true)
  })

  it("ignores non-numeric or negative values", () => {
    const costs = [
      { amount: "invalid", currency: "JPY" },
      { amount: "-500", currency: "JPY" },
      { amount: "1200", currency: "JPY" },
    ]
    const summary = calculateDayCostsSummary(costs, "JPY")
    expect(summary.primaryTotal).toBe(1200)
  })
})

describe("itinerary-metrics - calculateChecklistProgress", () => {
  it("handles empty checklist store", () => {
    expect(calculateChecklistProgress(null, 1)).toEqual({ completed: 0, total: 0 })
    expect(calculateChecklistProgress({}, 2)).toEqual({ completed: 0, total: 0 })
  })

  it("calculates regular day items correctly", () => {
    const dayChecklists = {
      "2": [
        { id: "1", text: "護照", is_completed: true },
        { id: "2", text: "日幣", is_completed: false },
        { id: "3", text: "相機", completed: true }, // handles both is_completed and completed
      ]
    }
    expect(calculateChecklistProgress(dayChecklists, 2)).toEqual({ completed: 2, total: 3 })
  })

  it("merges Day 0 (pre-trip) and Day 1 with de-duplication on day 1", () => {
    const dayChecklists = {
      "0": [
        { id: "p1", text: "買保險", is_completed: true },
        { id: "dup", text: "行動電源", is_completed: false },
      ],
      "1": [
        { id: "dup", text: "行動電源 (已確認)", is_completed: true },
        { id: "d1", text: "機場換票", is_completed: false },
      ]
    }
    // "dup" should be merged and de-duplicated
    const result = calculateChecklistProgress(dayChecklists, 1)
    expect(result.total).toBe(3) // p1, dup, d1
    expect(result.completed).toBe(2) // p1 (true), dup (from d1: true)
  })
})

describe("itinerary-metrics - extractAIReviewHighlights", () => {
  it("extracts score, rating, and warnings from review markdown", () => {
    const sampleReview = `
🎯 行程綜合評分：92 分（極佳）
✅ 時間規劃：節奏得宜
⚠️ 注意事項：傍晚景點可能人潮擁擠，建議提早 30 分鐘抵達
💡 文化禮儀：神社參拜請輕聲
`
    const highlights = extractAIReviewHighlights(sampleReview)
    expect(highlights.score).toBe(92)
    expect(highlights.hasWarning).toBe(true)
    expect(highlights.status).toBe("excellent")
    expect(highlights.warningSnippet).toContain("傍晚景點可能人潮擁擠")
  })

  it("handles undefined or empty review safely", () => {
    const emptyHighlights = extractAIReviewHighlights(undefined)
    expect(emptyHighlights.score).toBeNull()
    expect(emptyHighlights.dimensions).toBeNull()
    expect(emptyHighlights.hasWarning).toBe(false)
    expect(emptyHighlights.status).toBe("pending")
    expect(emptyHighlights.warningSnippet).toBeNull()
    expect(emptyHighlights.cleanReviewText).toBe("")
  })

  it("parses ```evaluation machine block with 5 dimensions and strips raw block from clean text", () => {
    const sampleReview = `
[🎯 總評]
行程整體充實，涵蓋多處代表性地標。

[✅ 優點]
時間節奏得宜，動線極為順暢。

\`\`\`evaluation
SCORE: 88
PACING: 18
ROUTE: 19
DURATION: 17
FATIGUE: 16
TIMING: 18
STATUS: HEALTHY
\`\`\`
`
    const highlights = extractAIReviewHighlights(sampleReview)
    expect(highlights.score).toBe(88)
    expect(highlights.status).toBe("excellent")
    expect(highlights.dimensions).toEqual({
      pacing: 18,
      route: 19,
      duration: 17,
      fatigue: 16,
      timing: 18,
    })
    // 機器代碼必須被剝離
    expect(highlights.cleanReviewText).not.toContain("```evaluation")
    expect(highlights.cleanReviewText).toContain("[🎯 總評]")
  })

  it("🛡️ 核心防禦：文字中出現『建議預留 20 分鐘車程』時，絕不可誤判為 20 分", () => {
    const reviewWithMinutes = `
[🎯 總評]
行程規劃得宜，建議交通時間預留 20 分鐘以防延誤。
景點停留約 30 分鐘。
`
    const highlights = extractAIReviewHighlights(reviewWithMinutes)
    // 絕不可把「20 分鐘」或「30 分鐘」當成評分！
    expect(highlights.score).toBeNull()
    expect(highlights.status).toBe("pending")
  })

  it("🛡️ 語意強型別鎖定：低於 70 分絕對不可標註為 good 或健康", () => {
    const lowScoreReview = `
\`\`\`evaluation
SCORE: 45
PACING: 8
ROUTE: 10
DURATION: 9
FATIGUE: 8
TIMING: 10
STATUS: CRITICAL
\`\`\`
`
    const highlights = extractAIReviewHighlights(lowScoreReview)
    expect(highlights.score).toBe(45)
    expect(highlights.status).toBe("needs_attention") // 絕對不可為 good
  })

  it("clamps dimension values to 0-20 and score to 0-100", () => {
    const overflowReview = `
\`\`\`evaluation
SCORE: 120
PACING: 25
ROUTE: -5
DURATION: 20
FATIGUE: 18
TIMING: 19
STATUS: HEALTHY
\`\`\`
`
    const highlights = extractAIReviewHighlights(overflowReview)
    expect(highlights.score).toBe(100) // clamped to 100
    expect(highlights.dimensions?.pacing).toBe(20) // clamped to 20
    expect(highlights.dimensions?.route).toBe(0) // clamped to 0
  })

  it("supports dual-track Chinese dimension keys and ratings", () => {
    const chineseReview = `
[🎯 總評]
全天行程流暢，景點集中。

\`\`\`yaml
總評分: 86
時間節奏: 18/20
動線順暢: 17/20
停留合理: 16/20
體力負荷: 18/20
時段契合: 17/20
STATUS: HEALTHY
\`\`\`
`
    const highlights = extractAIReviewHighlights(chineseReview)
    expect(highlights.score).toBe(86)
    expect(highlights.status).toBe("excellent")
    expect(highlights.dimensions).toEqual({
      pacing: 18,
      route: 17,
      duration: 16,
      fatigue: 18,
      timing: 17,
    })
  })

  it("tolerates unclosed code fence block at EOF gracefully", () => {
    const unclosedReview = `
[🎯 總評]
行程時間適當。

\`\`\`evaluation
SCORE: 82
PACING: 16
ROUTE: 17
DURATION: 16
FATIGUE: 17
TIMING: 16
STATUS: HEALTHY
`
    const highlights = extractAIReviewHighlights(unclosedReview)
    expect(highlights.score).toBe(82)
    expect(highlights.dimensions?.pacing).toBe(16)
  })

  it("handles empty blueprint review without false pending status", () => {
    const emptyReview = "💡 當天尚未安排任何景點藍圖，建議先添加一些行程點，我才能為您進行深度審核。"
    const highlights = extractAIReviewHighlights(emptyReview)
    expect(highlights.score).toBeNull()
    expect(highlights.warningSnippet).toBe("當天尚未安排景點藍圖，請先添加行程點")
  })

  it("🛡️ Red Test 1: Extracts score correctly even when preceding code fences exist in review", () => {
    const reviewWithMultipleBlocks = `
\`\`\`markdown
[🎯 總評]
這是一份緊湊但合理的東京一日遊。
\`\`\`

\`\`\`
交通備註：搭乘 JR 山手線
\`\`\`

\`\`\`evaluation
SCORE: 89
PACING: 18
ROUTE: 17
DURATION: 18
FATIGUE: 18
TIMING: 18
STATUS: HEALTHY
\`\`\`
`
    const highlights = extractAIReviewHighlights(reviewWithMultipleBlocks)
    expect(highlights.score).toBe(89)
    expect(highlights.status).toBe("excellent")
    expect(highlights.dimensions?.pacing).toBe(18)
  })

  it("🛡️ Red Test 2: Auto-sums total score when 5 dimensions exist but SCORE line is missing", () => {
    const reviewWithoutTotalScore = `
[🎯 總評]
全天時間分配合理。

\`\`\`evaluation
PACING: 18
ROUTE: 17
DURATION: 16
FATIGUE: 17
TIMING: 18
STATUS: HEALTHY
\`\`\`
`
    const highlights = extractAIReviewHighlights(reviewWithoutTotalScore)
    expect(highlights.score).toBe(86) // 18 + 17 + 16 + 17 + 18 = 86
    expect(highlights.status).toBe("excellent")
  })

  it("🛡️ Red Test 3: Infers status from statusTag when numeric score is missing", () => {
    const statusTagReview = `
[🎯 總評]
行程整體安排得宜，時間節奏從容，適合家庭出遊。

\`\`\`evaluation
STATUS: HEALTHY
\`\`\`
`
    const highlights = extractAIReviewHighlights(statusTagReview)
    expect(highlights.status).toBe("excellent")
    expect(highlights.cleanReviewText).toContain("行程整體安排得宜")
  })

  it("🛡️ Red Test 4: Extracts score from Chinese colon or bold formatting without code fence", () => {
    const rawChineseReview = `
[🎯 總評]
**總評分**：87分
整體節奏舒適，動線順暢。
`
    const highlights = extractAIReviewHighlights(rawChineseReview)
    expect(highlights.score).toBe(87)
    expect(highlights.status).toBe("excellent")
  })

  it("🛡️ Sentinel Guard: handles malformed non-array checklist stores without throwing TypeError", () => {
    // Malformed input where Day 0 is an object instead of an array
    const malformedStoreDay1 = {
      "0": { items: [] },
      "1": "invalid_string_instead_of_array",
    }
    expect(() => calculateChecklistProgress(malformedStoreDay1, 1)).not.toThrow()
    expect(calculateChecklistProgress(malformedStoreDay1, 1)).toEqual({ completed: 0, total: 0 })

    // Malformed input on Day 2
    const malformedStoreDay2 = {
      "2": 42,
    }
    expect(() => calculateChecklistProgress(malformedStoreDay2, 2)).not.toThrow()
    expect(calculateChecklistProgress(malformedStoreDay2, 2)).toEqual({ completed: 0, total: 0 })
  })

  it("🛡️ Sentinel Guard: handles non-string or malformed currency in cost calculation", () => {
    const costsWithMalformedCurrency = [
      { amount: 1000, currency: 123 as unknown as string },
      { amount: "500", currency: null as unknown as string },
      { amount: "2000", currency: "  jpy  " },
    ]
    expect(() => calculateDayCostsSummary(costsWithMalformedCurrency, "JPY")).not.toThrow()
    const result = calculateDayCostsSummary(costsWithMalformedCurrency, "JPY")
    expect(result.primaryTotal).toBe(2500) // 500 (fallback JPY) + 2000 (trimmed JPY)
  })
})



