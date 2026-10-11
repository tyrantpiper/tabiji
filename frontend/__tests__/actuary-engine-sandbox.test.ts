import { describe, it, expect } from "vitest"
import { calculateTaxActuary, safeRound } from "../lib/tax-rules/actuaryEngine"
import { DEFAULT_TAX_RULES, resolveEffectiveTaxRule } from "../lib/tax-rules/defaultTaxRules"
import { CreditCardItem } from "../lib/tax-rules/types"

describe("🛡️ Global Tax Actuary Sandbox Engine Verification", () => {
    const jpRule = DEFAULT_TAX_RULES.find(r => r.countryCode === 'JP')!
    const itRule = DEFAULT_TAX_RULES.find(r => r.countryCode === 'IT')!
    const ukRule = DEFAULT_TAX_RULES.find(r => r.countryCode === 'GB')!
    const usRule = DEFAULT_TAX_RULES.find(r => r.countryCode === 'US')!

    it("1. 驗證含稅價除數數學反推（杜絕市面 10% 溢計除數膨脹 Bug）", () => {
        // 含稅 110 円，稅率 10%
        const res = calculateTaxActuary({
            amount: 110,
            isTaxInclusive: true,
            countryRule: jpRule,
            exchangeRate: 0.22
        })

        // 未稅淨額必須是 100，稅額必須是 10
        expect(res.baseAmount).toBe(100)
        expect(res.taxAmount).toBe(10)
        expect(res.grossAmount).toBe(110)
        // 嚴格斷言：不可等於錯誤的 110 * 0.1 = 11
        expect(res.taxAmount).not.toBe(11)
    })

    it("2. 驗證未稅價直接計算與含稅總額", () => {
        const res = calculateTaxActuary({
            amount: 100,
            isTaxInclusive: false,
            countryRule: jpRule,
            exchangeRate: 0.22
        })

        expect(res.baseAmount).toBe(100)
        expect(res.taxAmount).toBe(10)
        expect(res.grossAmount).toBe(110)
    })

    it("3. 驗證日本未稅 5,000 円門檻邊際判定 (Tax-Exclusive Basis)", () => {
        // 含稅 5,200 円（未稅約 4,727.27 円 < 5,000）
        const belowRes = calculateTaxActuary({
            amount: 5200,
            isTaxInclusive: true,
            countryRule: jpRule,
            exchangeRate: 0.22
        })

        expect(belowRes.thresholdStatus).toBe("BELOW_THRESHOLD")
        expect(belowRes.shortfall).toBeGreaterThan(0)
        expect(belowRes.shortfall).toBe(safeRound(5000 - 4727.27))
        expect(belowRes.estimatedNetRefund).toBe(0)

        // 含稅 5,500 円（未稅剛好 5,000 円 >= 5,000）
        const qualifiedRes = calculateTaxActuary({
            amount: 5500,
            isTaxInclusive: true,
            countryRule: jpRule,
            exchangeRate: 0.22
        })

        expect(qualifiedRes.thresholdStatus).toBe("QUALIFIED")
        expect(qualifiedRes.shortfall).toBe(0)
        expect(qualifiedRes.estimatedNetRefund).toBe(500) // 日本 100% 現折
    })

    it("4. 驗證義大利 OTELLO 2.0 新制 €70.01 含稅門檻 (Tax-Inclusive Basis)", () => {
        // 義大利門檻為含稅 €70.01
        const res = calculateTaxActuary({
            amount: 75.0,
            isTaxInclusive: true,
            countryRule: itRule,
            exchangeRate: 35.0
        })

        expect(res.thresholdStatus).toBe("QUALIFIED")
        // 22% VAT，代辦商手續費 30%
        // base = 75 / 1.22 = 61.48, tax = 75 - 61.48 = 13.52
        // net refund = 13.52 * 0.70 = 9.46
        expect(res.estimatedNetRefund).toBe(9.46)
        expect(res.dccWarning).toBe(true) // 歐盟代辦商觸發 DCC 避坑警告
    })

    it("5. 驗證英美無觀光退稅國家之邊界防禦", () => {
        const ukRes = calculateTaxActuary({
            amount: 100,
            isTaxInclusive: true,
            countryRule: ukRule,
            exchangeRate: 41.5
        })
        expect(ukRes.thresholdStatus).toBe("NO_TAX_FREE")
        expect(ukRes.estimatedNetRefund).toBe(0)

        const usRes = calculateTaxActuary({
            amount: 100,
            isTaxInclusive: false,
            countryRule: usRule,
            exchangeRate: 32.5
        })
        expect(usRes.thresholdStatus).toBe("NO_TAX_FREE")
        expect(usRes.estimatedNetRefund).toBe(0)
    })

    it("6. 驗證個人信用卡 1.5% 海外手續費與回饋折抵精算及最佳卡片推薦", () => {
        const testCards: CreditCardItem[] = [
            { id: "card-a", name: "JCB 玫瑰卡", rewardRate: 3.3, rewardLimit: 1000 },
            { id: "card-b", name: "標準 Visa 卡", rewardRate: 1.0 }
        ]

        const res = calculateTaxActuary({
            amount: 10000, // 10,000 JPY
            isTaxInclusive: true,
            countryRule: jpRule,
            exchangeRate: 0.22,
            cards: testCards
        })

        // 免稅 10% 現折：實付 9,090.91 JPY * 0.22 = 2,000 NT$ (現金)
        expect(res.cardCalculations.length).toBe(2)
        const cardA = res.cardCalculations.find(c => c.card.id === "card-a")!
        const cardB = res.cardCalculations.find(c => c.card.id === "card-b")!

        // Card A: 3.3% 回饋 - 1.5% 手續費 = 淨賺 1.8% -> 費用比現金便宜
        expect(cardA.savingsComparedToCash).toBeGreaterThan(0)
        // Card B: 1.0% 回饋 - 1.5% 手續費 = 淨虧 0.5% -> 費用比現金貴
        expect(cardB.savingsComparedToCash).toBeLessThan(0)

        // 最佳卡片推薦必須是 Card A
        expect(res.bestCard?.card.id).toBe("card-a")
        expect(cardA.isBestOption).toBe(true)
        expect(cardB.isBestOption).toBe(false)
    })

    it("7. 驗證日本 2026/11/01 大改制時序守衛 (Temporal Guard)", () => {
        const preDate = new Date("2026-10-15T00:00:00Z")
        const postDate = new Date("2026-11-05T00:00:00Z")

        const resolvedPre = resolveEffectiveTaxRule(jpRule, preDate)
        expect(resolvedPre.refundMode).toBe("in_store")
        expect(resolvedPre.agencyFeeRatio).toBe(0)

        const resolvedPost = resolveEffectiveTaxRule(jpRule, postDate)
        expect(resolvedPost.refundMode).toBe("intermediary_airport")
        expect(resolvedPost.agencyFeeRatio).toBe(0.05)
    })

    it("8. 驗證極端惡意輸入防禦（NaN、Infinity、負數、零匯率）", () => {
        const nanRes = calculateTaxActuary({
            amount: NaN,
            isTaxInclusive: true,
            countryRule: jpRule,
            exchangeRate: 0.22
        })
        expect(nanRes.rawAmount).toBe(0)
        expect(nanRes.baseAmount).toBe(0)
        expect(nanRes.taxAmount).toBe(0)

        const negRes = calculateTaxActuary({
            amount: -5000,
            isTaxInclusive: true,
            countryRule: jpRule,
            exchangeRate: 0.22
        })
        expect(negRes.rawAmount).toBe(0)

        const zeroRateRes = calculateTaxActuary({
            amount: 1000,
            isTaxInclusive: true,
            countryRule: jpRule,
            exchangeRate: 0 // 匯率為 0 時 fallback 為 1.0
        })
        expect(Number.isFinite(zeroRateRes.netCostTwdCash)).toBe(true)
    })

    it("9. 驗證購物計算機算式安全評估器（四則運算優先權、懸空運算子修補、除零防禦）", async () => {
        const { evaluateArithmeticExpression } = await import("../lib/tax-rules/actuaryEngine")

        // 乘法優先於加法: 1500 + 3200 * 2 = 7900
        expect(evaluateArithmeticExpression("1500 + 3200 * 2")).toBe(7900)
        // 浮點數運算
        expect(evaluateArithmeticExpression("1980 * 3 + 550.5")).toBe(6490.5)
        // 懸空運算子自動修補: "1500 + 300 *" -> 1800
        expect(evaluateArithmeticExpression("1500 + 300 *")).toBe(1800)
        expect(evaluateArithmeticExpression("1500 +")).toBe(1500)
        // 除以零防禦: 返回 null
        expect(evaluateArithmeticExpression("5000 / 0")).toBeNull()
        // 無效字元過濾
        expect(evaluateArithmeticExpression("abc")).toBeNull()
        expect(evaluateArithmeticExpression("")).toBeNull()
    })

    it("10. 驗證目的國在地化動態稅制標籤（日本、歐盟、韓國、通用）", async () => {
        const { getLocalizedTaxLabels, DEFAULT_TAX_RULES } = await import("../lib/tax-rules/defaultTaxRules")
        const jp = DEFAULT_TAX_RULES.find(r => r.countryCode === 'JP')!
        const fr = DEFAULT_TAX_RULES.find(r => r.countryCode === 'FR')!
        const kr = DEFAULT_TAX_RULES.find(r => r.countryCode === 'KR')!
        const us = DEFAULT_TAX_RULES.find(r => r.countryCode === 'US')!

        const jpLabels = getLocalizedTaxLabels(jp, true)
        expect(jpLabels.inclusive).toContain("税込")
        expect(jpLabels.exclusive).toContain("税抜")

        const frLabels = getLocalizedTaxLabels(fr, true)
        expect(frLabels.inclusive).toContain("TTC")
        expect(frLabels.exclusive).toContain("HT")

        const krLabels = getLocalizedTaxLabels(kr, true)
        expect(krLabels.inclusive).toContain("과세")

        const usLabels = getLocalizedTaxLabels(us, true)
        expect(usLabels.inclusive).toBe("含稅")
        expect(usLabels.exclusive).toBe("未稅")
    })

    it("11. 驗證信用卡回饋上限正規化（現金上限 vs 可刷本金門檻）", async () => {
        const { resolveCardStrategy } = await import("../lib/tax-rules/actuaryEngine")

        // 卡片 A: 5% 回饋，回饋金上限 1,000 元（可刷上限 = 1000 / 0.05 = 20,000 元）
        const cards: CreditCardItem[] = [
            { id: "card-a", name: "頂級神卡", rewardRate: 5.0, rewardLimit: 1000 }
        ]

        // 消費 15,000 TWD（未達 20,000 上限）：回饋 750 TWD，isLimitWarning = false
        const resUnder = resolveCardStrategy(cards, 15000)
        expect(resUnder?.bestSingleCard.isLimitWarning).toBe(false)
        expect(resUnder?.bestSingleCard.savingsComparedToCash).toBe(safeRound(750 - 15000 * 0.015)) // 750 - 225 = 525

        // 消費 30,000 TWD（超過 20,000 上限）：回饋封頂 1,000 TWD，isLimitWarning = true
        const resOver = resolveCardStrategy(cards, 30000)
        expect(resOver?.bestSingleCard.isLimitWarning).toBe(true)
        expect(resOver?.bestSingleCard.savingsComparedToCash).toBe(safeRound(1000 - 30000 * 0.015)) // 1000 - 450 = 550
    })

    it("12. 驗證超額刷卡之「雙卡最佳拆單神策」（卡 A 頂格滿額 + 卡 B 接力無上限）", async () => {
        const { resolveCardStrategy } = await import("../lib/tax-rules/actuaryEngine")

        const cards: CreditCardItem[] = [
            { id: "card-a", name: "富邦 J 卡", rewardRate: 5.0, rewardLimit: 1000 }, // 滿額 20,000
            { id: "card-b", name: "台新 FlyGo", rewardRate: 3.5 }                    // 無上限
        ]

        // 消費 30,000 TWD
        // 單刷 Card A: 回饋 1,000 - 手續費 450 = 淨賺 550
        // 單刷 Card B: 30,000 * 3.5% = 1,050 - 手續費 450 = 淨賺 600
        // 拆單雙卡組合技:
        // Card A 刷 20,000 (回饋 1,000)
        // Card B 刷 10,000 (回饋 350)
        // 總回饋 1,350 - 總手續費 450 = 淨賺 900
        // 拆單相較單刷最優 (600) 多賺: 900 - 600 = 300 TWD!
        const res = resolveCardStrategy(cards, 30000)
        expect(res).not.toBeNull()
        expect(res?.splitStrategy).toBeDefined()
        expect(res?.splitStrategy?.cardA.id).toBe("card-a")
        expect(res?.splitStrategy?.spendA_Twd).toBe(20000)
        expect(res?.splitStrategy?.cardB.id).toBe("card-b")
        expect(res?.splitStrategy?.spendB_Twd).toBe(10000)
        expect(res?.splitStrategy?.totalNetRewardTwd).toBe(900)
        expect(res?.splitStrategy?.advantageTwd).toBe(300)
    })

    it("13. 驗證拆單摩擦力守衛（差額 < 30 元或次卡 < 100 元不主動建議實體拆單）", async () => {
        const { resolveCardStrategy } = await import("../lib/tax-rules/actuaryEngine")

        const cards: CreditCardItem[] = [
            { id: "card-a", name: "微額滿額卡", rewardRate: 3.1, rewardLimit: 930 }, // 滿額 30,000
            { id: "card-b", name: "微額次佳卡", rewardRate: 3.0 }                    // 無上限
        ]

        // 消費 30,150 TWD: 次卡僅刷 150，回饋利差僅 (3.1% - 3.0%) * 150 = 0.15 TWD，小於 30 元門檻
        const res = resolveCardStrategy(cards, 30150)
        // 應退化為單卡推薦，不輸出 splitStrategy
        expect(res?.splitStrategy).toBeUndefined()
        expect(res?.bestSingleCard).toBeDefined()
    })
})
