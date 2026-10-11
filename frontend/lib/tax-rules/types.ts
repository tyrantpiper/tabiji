/**
 * Types & Schema for Global Tax & Rate Actuary (全球多國免稅與匯率精算器)
 */

export type RefundMode = 'in_store' | 'intermediary_airport' | 'direct_customs' | 'none'

export type ThresholdStatus = 'QUALIFIED' | 'BELOW_THRESHOLD' | 'NO_TAX_FREE'

export interface TaxLabelDictionary {
    inclusive: string                 // Localized label, e.g. "含稅 (税込)" or "含稅 (TTC)" or "含稅"
    exclusive: string                 // Localized label, e.g. "未稅 (税抜)" or "未稅 (HT)" or "未稅"
}

export interface CountryTaxRule {
    countryCode: string               // ISO 2-letter code (e.g. 'JP', 'KR', 'FR', 'IT', 'US', 'GB')
    countryName: {
        zh: string
        en: string
        ja: string
    }
    flag: string                      // Emoji flag (e.g. '🇯🇵')
    currency: string                  // 3-letter currency code (e.g. 'JPY', 'EUR', 'USD')
    vatRate: number                   // Standard VAT / consumption tax rate (e.g. 0.10 for 10%)
    reducedVatRate?: number           // Reduced rate for food/groceries
    minSpendThreshold: number         // Minimum spend required for tax exemption
    isThresholdTaxInclusive: boolean  // true = threshold is evaluated on gross (含稅), false = evaluated on net (未稅)
    refundMode: RefundMode            // Mode of tax refund operation
    agencyFeeRatio: number            // Estimated fee taken by intermediaries like Global Blue (e.g. 0.30 = 30%)
    hasTaxFree: boolean               // Whether tourist tax-free shopping is supported
    taxLabels?: TaxLabelDictionary    // 🆕 Localized tax labels based on destination
    isCustom?: boolean                // 🆕 Whether this is a user-defined custom rule
    warningNotes?: {
        zh: string
        en: string
    }
    effectiveDate?: string            // ISO date string if policy changes on a specific date (e.g. '2026-11-01')
    postEffectiveRule?: Partial<CountryTaxRule> // Rule overrides when current date >= effectiveDate
}

export interface CreditCardItem {
    id: string
    name: string
    rewardRate: number                // Percentage, e.g. 3.0 for 3%
    rewardLimit?: number              // TWD limit
    notes?: string
}

export interface TapeItem {
    id: string
    expression: string                // e.g. "1980 * 3 + 500"
    amount: number                    // Evaluated amount, e.g. 6440
    note?: string                     // Optional item name / memo
    timestamp: number
}

export interface SplitStrategy {
    cardA: CreditCardItem
    cardB: CreditCardItem
    spendA_Twd: number
    spendB_Twd: number
    rewardA_Twd: number
    rewardB_Twd: number
    totalNetRewardTwd: number
    advantageTwd: number              // Advantage in TWD compared to single best card
}

export interface CardRecommendationResult {
    bestSingleCard: CardCalculation
    splitStrategy?: SplitStrategy
}

export interface ActuaryInput {
    amount: number                    // Input sticker price in foreign currency
    isTaxInclusive: boolean           // true = user entered tax-inclusive, false = tax-exclusive
    countryRule: CountryTaxRule       // Active country rule
    exchangeRate: number              // Target currency to TWD exchange rate (e.g. 0.22 for JPY/TWD)
    cards?: CreditCardItem[]          // User's configured credit cards
    customVatRate?: number            // Optional user override for VAT rate
    customThreshold?: number          // Optional user override for threshold
}

export interface CardCalculation {
    card: CreditCardItem
    netTwdCost: number                // Final TWD charged on statement
    savingsComparedToCash: number     // TWD saved compared to cash/base exchange
    isBestOption: boolean
    isLimitWarning: boolean
}

export interface ActuaryResult {
    rawAmount: number
    baseAmount: number                // Tax-exclusive net amount (未稅價)
    grossAmount: number               // Tax-inclusive total amount (含稅價)
    taxAmount: number                 // Total tax embedded or added (消費稅/VAT)
    effectiveVatRate: number
    thresholdStatus: ThresholdStatus
    thresholdAmount: number
    shortfall: number                 // Amount needed to reach tax-free threshold (in foreign currency)
    potentialTaxSavingsTwd: number    // TWD saved if reaching threshold
    estimatedNetRefund: number        // Actual refund expected after agency commission
    refundCurrency: string
    netCostForeign: number            // Amount paid after tax refund (in foreign currency)
    netCostTwdCash: number            // TWD paid via cash (at pure exchange rate)
    cardCalculations: CardCalculation[]
    bestCard: CardCalculation | null
    cardRecommendation?: CardRecommendationResult
    dccWarning: boolean               // True if EU/Intermediary mode where DCC trap is prevalent
}
