/**
 * Pure Functional Computation Engine for Global Tax & Rate Actuary (全球退稅與匯率精算引擎)
 * Strictly zero side-effects, defensive float handling, and deterministic output.
 */

import {
    ActuaryInput, ActuaryResult, CardCalculation, CardRecommendationResult,
    CountryTaxRule, CreditCardItem
} from "./types"
import { resolveEffectiveTaxRule } from "./defaultTaxRules"

/**
 * Rounds a number defensively to avoid IEEE 754 floating-point artifacts.
 */
export function safeRound(value: number, decimals: number = 2): number {
    if (!Number.isFinite(value)) return 0
    const factor = Math.pow(10, decimals)
    return Math.round((value + Number.EPSILON) * factor) / factor
}

/**
 * Deterministic Arithmetic Expression Evaluator (Zero eval / Zero new Function).
 * Supports standard + - * / with operator precedence, dangling operator repair, and zero division guard.
 */
export function evaluateArithmeticExpression(expr: string): number | null {
    if (!expr || typeof expr !== 'string') return null
    // Strip all characters except numbers, decimal point, and operators
    let sanitized = expr.replace(/[^0-9+\-*/.]/g, '').trim()
    // Trim trailing dangling operators, e.g. "1500+" -> "1500"
    sanitized = sanitized.replace(/[+\-*/.]+$/, '')
    if (!sanitized) return null

    try {
        const tokens = sanitized.match(/(\d+\.?\d*|[+\-*/])/g)
        if (!tokens || tokens.length === 0) return null

        // Pass 1: Multiplication and Division
        const intermediate: (number | string)[] = []
        for (let i = 0; i < tokens.length; i++) {
            const token = tokens[i]
            if (token === '*' || token === '/') {
                const prev = intermediate.pop()
                if (typeof prev !== 'number') return null
                const nextStr = tokens[++i]
                if (!nextStr) return null
                const next = parseFloat(nextStr)
                if (!Number.isFinite(next)) return null
                if (token === '/' && next === 0) return null // Division by zero guard
                intermediate.push(token === '*' ? prev * next : prev / next)
            } else if (!isNaN(parseFloat(token))) {
                intermediate.push(parseFloat(token))
            } else {
                intermediate.push(token)
            }
        }

        // Pass 2: Addition and Subtraction
        let total = intermediate[0]
        if (typeof total !== 'number' || !Number.isFinite(total)) return null

        for (let i = 1; i < intermediate.length; i += 2) {
            const op = intermediate[i]
            const next = intermediate[i + 1]
            if (typeof next !== 'number' || !Number.isFinite(next)) return null
            if (op === '+') total += next
            else if (op === '-') total -= next
            else return null
        }

        return Number.isFinite(total) && total >= 0 ? safeRound(total) : null
    } catch {
        return null
    }
}

/**
 * Resolves single best card and intelligent double-card split strategy.
 * Normalizes cashback cap (rewardLimit in TWD) vs eligible spend.
 */
export function resolveCardStrategy(
    cards: CreditCardItem[],
    spendTwd: number
): CardRecommendationResult | null {
    if (!cards || cards.length === 0 || spendTwd <= 0) return null

    const OVERSEAS_FEE = 0.015

    // 1. Calculate each card's performance
    const cardCalcs: (CardCalculation & {
        rawReward: number
        eligibleSpend: number
        maxEligibleSpend: number
        isCapped: boolean
    })[] = cards.map(card => {
        const rateDecimal = (card.rewardRate || 0) / 100
        const grossFee = safeRound(spendTwd * OVERSEAS_FEE)
        
        // rewardLimit is the cashback cap in TWD (e.g. 1000 TWD)
        const maxEligibleSpend = card.rewardLimit && card.rewardLimit > 0 && rateDecimal > 0
            ? safeRound(card.rewardLimit / rateDecimal)
            : Infinity

        const isCapped = spendTwd > maxEligibleSpend
        const eligibleSpend = isCapped ? maxEligibleSpend : spendTwd
        const rawReward = safeRound(eligibleSpend * rateDecimal)
        const netTwdCost = safeRound(spendTwd + grossFee - rawReward)
        const savingsComparedToCash = safeRound(rawReward - grossFee)

        return {
            card,
            netTwdCost,
            savingsComparedToCash,
            isBestOption: false,
            isLimitWarning: isCapped,
            rawReward,
            eligibleSpend,
            maxEligibleSpend,
            isCapped
        }
    })

    // Sort by net lowest cost (highest savings)
    cardCalcs.sort((a, b) => a.netTwdCost - b.netTwdCost)
    const bestSingle = cardCalcs[0]
    bestSingle.isBestOption = true

    // 2. Intelligent Split Recommendation
    let splitStrategy: CardRecommendationResult['splitStrategy'] | undefined = undefined

    // Find the card with the highest reward rate that has a cap
    const cardsByRate = [...cardCalcs].sort((x, y) => (y.card.rewardRate || 0) - (x.card.rewardRate || 0))
    const highestRateCard = cardsByRate[0]

    // Only consider split if the highest rate card is capped and there is at least one other card
    if (highestRateCard && highestRateCard.isCapped && Number.isFinite(highestRateCard.maxEligibleSpend) && cardCalcs.length >= 2) {
        const cardA = highestRateCard
        // Candidates for secondary card: sorted by highest rate
        const secondaryCandidates = cardsByRate.filter(c => c.card.id !== cardA.card.id)
        const candidateB = secondaryCandidates[0]

        const spendA = safeRound(cardA.maxEligibleSpend)
        const spendB = safeRound(spendTwd - spendA)

        // Split friction guards:
        // - Remainder spend must be >= 100 TWD
        if (spendB >= 100) {
            const rateDecimalB = (candidateB.card.rewardRate || 0) / 100
            const maxEligibleB = candidateB.card.rewardLimit && candidateB.card.rewardLimit > 0 && rateDecimalB > 0
                ? safeRound(candidateB.card.rewardLimit / rateDecimalB)
                : Infinity

            const eligibleB = Math.min(spendB, maxEligibleB)
            const rewardB = safeRound(eligibleB * rateDecimalB)
            const rewardA = cardA.rawReward // Already at limit
            const totalFee = safeRound(spendTwd * OVERSEAS_FEE)
            const combinedNetReward = safeRound(rewardA + rewardB - totalFee)
            const advantage = safeRound(combinedNetReward - bestSingle.savingsComparedToCash)

            // Must produce meaningful savings (>= 30 TWD) to justify multi-card swipe friction
            if (advantage >= 30) {
                splitStrategy = {
                    cardA: cardA.card,
                    cardB: candidateB.card,
                    spendA_Twd: spendA,
                    spendB_Twd: spendB,
                    rewardA_Twd: rewardA,
                    rewardB_Twd: rewardB,
                    totalNetRewardTwd: combinedNetReward,
                    advantageTwd: advantage
                }
            }
        }
    }

    return {
        bestSingleCard: {
            card: bestSingle.card,
            netTwdCost: bestSingle.netTwdCost,
            savingsComparedToCash: bestSingle.savingsComparedToCash,
            isBestOption: true,
            isLimitWarning: bestSingle.isLimitWarning
        },
        splitStrategy
    }
}

export function calculateTaxActuary(input: ActuaryInput): ActuaryResult {
    // 🛡️ Step 1: Input Sanitization & Defensive Guards
    const rawAmount = Number.isFinite(input.amount) && input.amount > 0 ? input.amount : 0
    const rawRate = Number.isFinite(input.exchangeRate) && input.exchangeRate > 0 ? input.exchangeRate : 1.0

    // Resolve temporal rules (e.g., Japan 2026/11 transition)
    const effectiveRule: CountryTaxRule = resolveEffectiveTaxRule(input.countryRule)

    // User-overridable VAT rate & Threshold
    const vatRate = Number.isFinite(input.customVatRate) && (input.customVatRate ?? -1) >= 0
        ? (input.customVatRate as number)
        : effectiveRule.vatRate

    const thresholdAmount = Number.isFinite(input.customThreshold) && (input.customThreshold ?? -1) >= 0
        ? (input.customThreshold as number)
        : effectiveRule.minSpendThreshold

    // 🛡️ Step 2: Exact Mathematical Inversion
    let baseAmount = 0
    let grossAmount = 0
    let taxAmount = 0

    if (rawAmount > 0) {
        if (input.isTaxInclusive) {
            // Price P includes tax: Base = P / (1 + vatRate), Tax = P - Base
            grossAmount = safeRound(rawAmount)
            baseAmount = vatRate > 0 ? safeRound(grossAmount / (1 + vatRate)) : grossAmount
            taxAmount = safeRound(grossAmount - baseAmount)
        } else {
            // Price P is tax-exclusive: Base = P, Gross = P * (1 + vatRate)
            baseAmount = safeRound(rawAmount)
            taxAmount = safeRound(baseAmount * vatRate)
            grossAmount = safeRound(baseAmount + taxAmount)
        }
    }

    // 🛡️ Step 3: Threshold Evaluation
    let thresholdStatus: ActuaryResult['thresholdStatus'] = 'NO_TAX_FREE'
    let shortfall = 0
    let potentialTaxSavingsTwd = 0

    if (effectiveRule.hasTaxFree && vatRate > 0) {
        // Evaluate spend basis according to each nation's statutory rules
        // e.g., Japan evaluates on pre-tax (baseAmount >= 5,000), EU evaluates on gross (grossAmount >= 70.01/100.01)
        const evaluatedBasis = effectiveRule.isThresholdTaxInclusive ? grossAmount : baseAmount

        if (evaluatedBasis >= thresholdAmount) {
            thresholdStatus = 'QUALIFIED'
            shortfall = 0
        } else {
            thresholdStatus = 'BELOW_THRESHOLD'
            shortfall = safeRound(thresholdAmount - evaluatedBasis)
            // If user reaches threshold, potential tax saved:
            const potentialTax = effectiveRule.isThresholdTaxInclusive
                ? safeRound(thresholdAmount - (thresholdAmount / (1 + vatRate)))
                : safeRound(thresholdAmount * vatRate)
            potentialTaxSavingsTwd = safeRound(potentialTax * rawRate)
        }
    } else {
        thresholdStatus = 'NO_TAX_FREE'
        shortfall = 0
    }

    // 🛡️ Step 4: Net Refund Calculation (Intermediary & Processing Cut)
    let estimatedNetRefund = 0
    if (thresholdStatus === 'QUALIFIED' && taxAmount > 0) {
        switch (effectiveRule.refundMode) {
            case 'in_store':
                // Instant 100% deduction in-store
                estimatedNetRefund = taxAmount
                break
            case 'intermediary_airport': {
                // Deduct Global Blue / Planet agency fee (typical 25%~35%)
                const feeRatio = Math.min(0.5, Math.max(0, effectiveRule.agencyFeeRatio))
                estimatedNetRefund = safeRound(taxAmount * (1 - feeRatio))
                break
            }
            case 'direct_customs': {
                // Direct government customs refund (Australia/Singapore), minus minor transaction fee
                const feeRatio = Math.min(0.2, Math.max(0, effectiveRule.agencyFeeRatio))
                estimatedNetRefund = safeRound(taxAmount * (1 - feeRatio))
                break
            }
            case 'none':
            default:
                estimatedNetRefund = 0
                break
        }
    }

    // Foreign currency amount actually out of pocket after refund
    const netCostForeign = safeRound(grossAmount - estimatedNetRefund)

    // Base cash cost in TWD (Pure exchange rate, no bank card fees)
    const netCostTwdCash = safeRound(netCostForeign * rawRate)

    // 🛡️ Step 5: Card Actuary & Strategy Recommendation
    const cardRecommendation = input.cards && input.cards.length > 0
        ? resolveCardStrategy(input.cards, netCostTwdCash)
        : null

    const cardCalculations: CardCalculation[] = []
    let bestCard: CardCalculation | null = null

    if (input.cards && input.cards.length > 0) {
        const OVERSEAS_FEE = 0.015
        for (const card of input.cards) {
            const rateDecimal = (card.rewardRate || 0) / 100
            const maxEligibleSpend = card.rewardLimit && card.rewardLimit > 0 && rateDecimal > 0
                ? safeRound(card.rewardLimit / rateDecimal)
                : Infinity
            const isCapped = netCostTwdCash > maxEligibleSpend
            const eligibleSpend = isCapped ? maxEligibleSpend : netCostTwdCash
            const rawReward = safeRound(eligibleSpend * rateDecimal)
            const grossFee = safeRound(netCostTwdCash * OVERSEAS_FEE)
            const netTwdCost = safeRound(netCostTwdCash + grossFee - rawReward)
            const savingsComparedToCash = safeRound(rawReward - grossFee)

            cardCalculations.push({
                card,
                netTwdCost,
                savingsComparedToCash,
                isBestOption: false,
                isLimitWarning: isCapped
            })
        }

        cardCalculations.sort((a, b) => a.netTwdCost - b.netTwdCost)
        if (cardCalculations.length > 0) {
            bestCard = cardCalculations[0]
            bestCard.isBestOption = true
        }
    }

    // 🛡️ Step 6: DCC Warning Flag
    // Trigger DCC warning when intermediary mode is active and refund is available
    const dccWarning = effectiveRule.refundMode === 'intermediary_airport' && estimatedNetRefund > 0

    return {
        rawAmount,
        baseAmount,
        grossAmount,
        taxAmount,
        effectiveVatRate: vatRate,
        thresholdStatus,
        thresholdAmount,
        shortfall,
        potentialTaxSavingsTwd,
        estimatedNetRefund,
        refundCurrency: effectiveRule.currency,
        netCostForeign,
        netCostTwdCash,
        cardCalculations,
        bestCard,
        cardRecommendation: cardRecommendation || undefined,
        dccWarning
    }
}
