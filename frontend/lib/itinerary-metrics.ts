import { ChecklistItem } from "@/lib/itinerary-types"

export interface CostSummary {
  primaryTotal: number
  primaryCurrency: string
  hasMultipleCurrencies: boolean
}

export interface ChecklistProgress {
  completed: number
  total: number
}

export interface AIReviewDimensions {
  pacing: number
  route: number
  duration: number
  fatigue: number
  timing: number
}

export interface AIReviewHighlights {
  score: number | null
  dimensions: AIReviewDimensions | null
  status: "excellent" | "good" | "needs_attention" | "pending"
  hasWarning: boolean
  warningSnippet: string | null
  cleanReviewText: string
}

/**
 * 🛡️ 具備極致容錯性之五維量規區塊解析正則 (支援中英雙軌、代碼塊容錯與無圍欄降級)
 * 兼容: SCORE: 85, **SCORE**: 85/100, 總分: 85, PACING: 18/20, 時間節奏: 18 等格式
 */
function parseEvaluationBlock(text: string): {
  score: number | null
  dimensions: AIReviewDimensions | null
  statusTag: string | null
} {
  // 1. 優先精準鎖定包含評分或量規關鍵字的 code block (杜絕抓到一般 markdown 或前置文字圍欄)
  const blockMatch = text.match(/```(?:evaluation|eval|metrics|score|yaml|text|markdown)?\s*([\s\S]*?(?:SCORE|PACING|ROUTE|DURATION|FATIGUE|TIMING|STATUS|總分|評分|綜合評分)[\s\S]*?)(?:```|$)/i)
  const targetContent = blockMatch && blockMatch[1].trim().length > 0 ? blockMatch[1] : text

  const extractVal = (keyPattern: string, max: number): number | null => {
    const reg = new RegExp(`(?:\\*\\*)?(?:${keyPattern})(?:\\*\\*)?\\s*[:：=＝]\\s*(-?\\d{1,3})(?:\\s*(?:\\/${max}|分))?`, "i")
    // 先自鎖定的區塊解析，若區塊內無匹配則 fallback 至全文匹配
    const match = targetContent.match(reg) || text.match(reg)
    if (!match) return null
    const num = parseInt(match[1], 10)
    return isNaN(num) ? null : Math.max(0, Math.min(max, num))
  }

  let score = extractVal("SCORE|TOTAL_SCORE|TOTAL|OVERALL|總評分|綜合評分|總分|得分|總得分|行程評分|評分|分數", 100)
  const pacing = extractVal("PACING|時間節奏|節奏緩衝", 20)
  const route = extractVal("ROUTE|動線順暢|路線順暢", 20)
  const duration = extractVal("DURATION|停留合理|活動時長", 20)
  const fatigue = extractVal("FATIGUE|體力負荷|體能負荷", 20)
  const timing = extractVal("TIMING|時段契合|營業契合", 20)

  const hasAllDimensions = pacing !== null && route !== null && duration !== null && fatigue !== null && timing !== null

  // 🛡️ 容錯補正：若 AI 未輸出 SCORE 總分，但輸出了全部 5 個維度，自動計算五維總和 (滿分 100)
  if (score === null && hasAllDimensions) {
    score = pacing + route + duration + fatigue + timing
  }

  const statusReg = /(?:STATUS|評估狀態)\s*[:：=＝]\s*([A-Za-z_\u4e00-\u9fa5]+)/i
  const statusMatch = targetContent.match(statusReg) || text.match(statusReg)
  const statusTag = statusMatch ? statusMatch[1].toUpperCase() : null

  return {
    score,
    dimensions: hasAllDimensions ? { pacing, route, duration, fatigue, timing } : null,
    statusTag,
  }
}

/**
 * 🤖 從 AI 審核報告文字萃取評分、五維量規、狀態與警訊快覽
 * 具備三階安全降級防線，徹底杜絕「20 分鐘」誤抓為 20 分
 */
export function extractAIReviewHighlights(
  reviewText: string | undefined | null
): AIReviewHighlights {
  if (!reviewText || typeof reviewText !== "string" || !reviewText.trim()) {
    return {
      score: null,
      dimensions: null,
      status: "pending",
      hasWarning: false,
      warningSnippet: null,
      cleanReviewText: "",
    }
  }

  const normalized = reviewText.replace(/\\n/g, "\n")
  // 清理機器標籤圍欄 (僅移除帶有 evaluation/eval/metrics/score 標記或包含評分參數的代碼圍欄)
  let cleanReviewText = normalized
    .replace(/```(?:evaluation|eval|metrics|score)[\s\S]*?(?:```|$)/gi, "")
    .replace(/```(?:yaml|text|markdown)?\s*(?:SCORE|PACING)[\s\S]*?(?:```|$)/gi, "")
    .trim()
  
  // 若為無圍欄裸寫機器行，過濾結尾的機器參數行
  cleanReviewText = cleanReviewText
    .split("\n")
    .filter((line) => !/^(?:SCORE|TOTAL_SCORE|PACING|ROUTE|DURATION|FATIGUE|TIMING|STATUS)\s*[:：=＝]/i.test(line.trim()))
    .join("\n")
    .trim()

  const lines = cleanReviewText.split("\n").map((l) => l.trim()).filter(Boolean)

  let warningSnippet: string | null = null
  let hasWarning = false

  // 0. 尚未安排景點專用友善快覽
  if (normalized.includes("尚未安排任何景點") || normalized.includes("尚未安排景點")) {
    return {
      score: null,
      dimensions: null,
      status: "pending",
      hasWarning: false,
      warningSnippet: "當天尚未安排景點藍圖，請先添加行程點",
      cleanReviewText,
    }
  }

  // 1. 搜尋警訊 (如: ⚠️, 🚨, 注意事項, 警示, 擁擠)
  for (const line of lines) {
    if (!warningSnippet && (/^[⚠️🚨❗]/.test(line) || /注意|警訊|提醒|擁擠/.test(line))) {
      hasWarning = true
      const cleanLine = line.replace(/^[⚠️🚨❗\s:：]+/, "").trim()
      warningSnippet = cleanLine.length > 45 ? `${cleanLine.slice(0, 45)}...` : cleanLine
    }
  }

  // 2. 第一階防禦：優先解析結構化機器標籤區塊 (雙軌容錯)
  const parsedBlock = parseEvaluationBlock(normalized)
  let score: number | null = parsedBlock.score
  const dimensions: AIReviewDimensions | null = parsedBlock.dimensions

  // 3. 第二階防禦：若無機器區塊，採用嚴格關鍵字特徵掃描 (強制排除「分鐘/分車程/秒」)
  if (score === null) {
    for (const line of lines) {
      // 必須包含明確的評分語境，且後方絕非「鐘」或時間單位
      if (/(?:評分|綜合評分|總分|得分|score)/i.test(line)) {
        const scoreMatch = line.match(/(?:評分|綜合評分|總分|得分|score)[^\d]*(\d{1,3})(?:\s*(?:分|\/100))?(?!\s*鐘|\s*秒)/i)
        if (scoreMatch && !score) {
          const parsed = parseInt(scoreMatch[1], 10)
          if (parsed >= 0 && parsed <= 100) {
            score = parsed
          }
        }
      }
    }
  }

  // 4. 語意嚴格鎖定 (Zero-Semantic-Mismatch)
  let status: AIReviewHighlights["status"] = "pending"
  if (score !== null) {
    if (score >= 85) status = "excellent"
    else if (score >= 70) status = "good"
    else status = "needs_attention"
  } else if (parsedBlock.statusTag) {
    if (parsedBlock.statusTag.includes("HEALTHY") || parsedBlock.statusTag.includes("EXCELLENT")) status = "excellent"
    else if (parsedBlock.statusTag.includes("WARNING") || parsedBlock.statusTag.includes("CRITICAL")) status = "needs_attention"
    else status = "good"
  } else {
    status = hasWarning ? "needs_attention" : "pending"
  }

  return {
    score,
    dimensions,
    status,
    hasWarning,
    warningSnippet,
    cleanReviewText,
  }
}

/**
 * 🛡️ 容錯清洗金額字串，防止千分位逗號引發 NaN
 * 支援多幣別分組統計，自動隔離主幣別總額
 */
export function calculateDayCostsSummary(
  costs: Array<{ amount?: string | number; currency?: string }> | undefined | null,
  defaultCurrency = "JPY"
): CostSummary {
  if (!costs || !Array.isArray(costs) || costs.length === 0) {
    return {
      primaryTotal: 0,
      primaryCurrency: defaultCurrency,
      hasMultipleCurrencies: false,
    }
  }

  const totalsByCurrency: Record<string, number> = {}

  for (const c of costs) {
    if (!c) continue
    const rawAmount = typeof c.amount === "number"
      ? c.amount
      : parseFloat(String(c.amount || "").replace(/,/g, "").trim())

    if (!isNaN(rawAmount) && rawAmount > 0) {
      const curr = String(c.currency || defaultCurrency).trim().toUpperCase()
      totalsByCurrency[curr] = (totalsByCurrency[curr] || 0) + rawAmount
    }
  }

  const currencies = Object.keys(totalsByCurrency)
  if (currencies.length === 0) {
    return {
      primaryTotal: 0,
      primaryCurrency: defaultCurrency,
      hasMultipleCurrencies: false,
    }
  }

  const primaryCurrency = totalsByCurrency[defaultCurrency.toUpperCase()] !== undefined
    ? defaultCurrency.toUpperCase()
    : currencies[0]

  return {
    primaryTotal: totalsByCurrency[primaryCurrency],
    primaryCurrency,
    hasMultipleCurrencies: currencies.length > 1,
  }
}

/**
 * 🛡️ 嚴格對齊 Day 0 + Day 1 去重合併清單進度計算
 */
export function calculateChecklistProgress(
  rawDayChecklists: unknown,
  day: number
): ChecklistProgress {
  if (!rawDayChecklists || typeof rawDayChecklists !== "object") {
    return { completed: 0, total: 0 }
  }

  const store = rawDayChecklists as Record<string, unknown>
  let items: ChecklistItem[] = []

  if (day === 1) {
    const raw0 = store[0] !== undefined ? store[0] : store["0"]
    const raw1 = store[1] !== undefined ? store[1] : store["1"]
    const d0 = Array.isArray(raw0) ? (raw0 as ChecklistItem[]) : []
    const d1 = Array.isArray(raw1) ? (raw1 as ChecklistItem[]) : []
    const map = new Map<string, ChecklistItem>()
    ;[...d0, ...d1].forEach((item) => {
      if (item && item.id) {
        map.set(item.id, item)
      }
    })
    items = Array.from(map.values())
  } else {
    const rawItems = store[day] !== undefined ? store[day] : store[String(day)]
    items = Array.isArray(rawItems) ? (rawItems as ChecklistItem[]) : []
  }

  if (!Array.isArray(items)) {
    return { completed: 0, total: 0 }
  }

  type LegacyChecklistProps = ChecklistItem & {
    is_completed?: boolean
    completed?: boolean
  }

  const total = items.length
  const completed = items.filter((i) => {
    if (!i) return false
    const item = i as LegacyChecklistProps
    return Boolean(item.checked) || Boolean(item.is_completed) || Boolean(item.completed)
  }).length

  return { completed, total }
}
