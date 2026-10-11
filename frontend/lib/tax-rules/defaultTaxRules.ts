/**
 * Default Seed Rules Matrix for Global Tax & Rate Actuary (全球多國免稅與匯率精算種子矩陣)
 * Verified against 2025–2026 official customs & tax regulations worldwide.
 */

import { CountryTaxRule } from "./types"

export const DEFAULT_TAX_RULES: CountryTaxRule[] = [
    {
        countryCode: "JP",
        countryName: { zh: "日本", en: "Japan", ja: "日本" },
        flag: "🇯🇵",
        currency: "JPY",
        vatRate: 0.10,
        reducedVatRate: 0.08,
        minSpendThreshold: 5000,
        isThresholdTaxInclusive: false, // 5,000 円是「未稅價 (税抜)」
        refundMode: "in_store",
        agencyFeeRatio: 0.0,
        hasTaxFree: true,
        effectiveDate: "2026-11-01",
        postEffectiveRule: {
            refundMode: "intermediary_airport",
            agencyFeeRatio: 0.05,
            warningNotes: {
                zh: "日本於 2026/11/01 起實施新制：全面改為機場出境過機退稅，店內需先付含稅價；取消消耗品 50 萬円上限與封條限制。",
                en: "From Nov 1, 2026: Tax refund takes place at airport departure kiosks. Full price is paid in-store; ¥500k consumables cap abolished."
            }
        },
        warningNotes: {
            zh: "單店單日未稅消費滿 5,000 日圓可享 10% 現折免稅（食品/飲料適用 8% 輕減稅率）。",
            en: "Tax-free available on purchases over ¥5,000 (pre-tax). General goods & consumables qualify."
        }
    },
    {
        countryCode: "KR",
        countryName: { zh: "韓國", en: "South Korea", ja: "韓国" },
        flag: "🇰🇷",
        currency: "KRW",
        vatRate: 0.10,
        minSpendThreshold: 15000,
        isThresholdTaxInclusive: true, // 單筆滿 15,000 韓元含稅
        refundMode: "in_store",
        agencyFeeRatio: 0.28,
        hasTaxFree: true,
        warningNotes: {
            zh: "單筆滿 15,000 韓元可於店內出示護照即時扣減或至機場 Kiosk 退稅。2026 年起外國人醫美退稅方案正式落日終止。",
            en: "Instant tax refund available in-store over ₩15,000. Foreigner cosmetic surgery tax refund sunsetted in 2026."
        }
    },
    {
        countryCode: "FR",
        countryName: { zh: "法國", en: "France", ja: "フランス" },
        flag: "🇫🇷",
        currency: "EUR",
        vatRate: 0.20,
        reducedVatRate: 0.10,
        minSpendThreshold: 100.01,
        isThresholdTaxInclusive: true, // 單店同一天含稅滿 €100.01
        refundMode: "intermediary_airport",
        agencyFeeRatio: 0.30,
        hasTaxFree: true,
        warningNotes: {
            zh: "法國標準增值稅為 20%，代辦商（Global Blue/Planet）手續費約 30%，實退率約 11.5%~13%。退稅請於機場 PABLO 機器掃描條碼。",
            en: "20% VAT with €100.01 minimum. Net refund is ~12% after agency cut. Scan form at airport PABLO kiosk."
        }
    },
    {
        countryCode: "IT",
        countryName: { zh: "義大利", en: "Italy", ja: "イタリア" },
        flag: "🇮🇹",
        currency: "EUR",
        vatRate: 0.22,
        reducedVatRate: 0.10,
        minSpendThreshold: 70.01,
        isThresholdTaxInclusive: true, // 2024-2026 新制 OTELLO 2.0 門檻 €70.01
        refundMode: "intermediary_airport",
        agencyFeeRatio: 0.30,
        hasTaxFree: true,
        warningNotes: {
            zh: "義大利新制 OTELLO 2.0 門檻大幅下修至 €70.01（原 €154.94），標準 VAT 為 22%，實退率約 12.5%~14.5%。",
            en: "OTELLO 2.0 threshold lowered to €70.01. Standard 22% VAT yields ~13% net refund after intermediary fees."
        }
    },
    {
        countryCode: "DE",
        countryName: { zh: "德國", en: "Germany", ja: "ドイツ" },
        flag: "🇩🇪",
        currency: "EUR",
        vatRate: 0.19,
        reducedVatRate: 0.07,
        minSpendThreshold: 50.00,
        isThresholdTaxInclusive: true,
        refundMode: "intermediary_airport",
        agencyFeeRatio: 0.32,
        hasTaxFree: true,
        warningNotes: {
            zh: "德國門檻極低（€50.00 含稅），標準 VAT 為 19%，實退約 10%~12%。出境時需先給 Zoll 海關蓋章再至代辦處領款。",
            en: "Low €50.00 threshold with 19% VAT. Requires German Customs (Zoll) stamp prior to agency payout."
        }
    },
    {
        countryCode: "ES",
        countryName: { zh: "西班牙", en: "Spain", ja: "スペイン" },
        flag: "🇪🇸",
        currency: "EUR",
        vatRate: 0.21,
        reducedVatRate: 0.10,
        minSpendThreshold: 0, // 西班牙無最低金額門檻
        isThresholdTaxInclusive: true,
        refundMode: "intermediary_airport",
        agencyFeeRatio: 0.30,
        hasTaxFree: true,
        warningNotes: {
            zh: "西班牙為全歐盟極少數「無退稅門檻 (€0)」國家，小額精品均可索取 DIVA 退稅單，實退約 12%~15%。",
            en: "Spain has no minimum purchase limit (€0). Validate via DIVA digital kiosks at international airports."
        }
    },
    {
        countryCode: "GB",
        countryName: { zh: "英國", en: "United Kingdom", ja: "イギリス" },
        flag: "🇬🇧",
        currency: "GBP",
        vatRate: 0.20,
        minSpendThreshold: 0,
        isThresholdTaxInclusive: true,
        refundMode: "none",
        agencyFeeRatio: 0,
        hasTaxFree: false,
        warningNotes: {
            zh: "⚠️ 英國自脫歐 (Brexit) 後已全面取消海外旅客觀光退稅購物 (Tax-Free Shopping)，所有標價均無法辦理退稅。",
            en: "⚠️ Tax-free shopping for overseas visitors was abolished post-Brexit. No VAT refund is available in the UK."
        }
    },
    {
        countryCode: "US",
        countryName: { zh: "美國", en: "United States", ja: "アメリカ" },
        flag: "🇺🇸",
        currency: "USD",
        vatRate: 0.08875, // NYC 代表性綜合消費稅 (0% ~ 10.25%)
        minSpendThreshold: 0,
        isThresholdTaxInclusive: false,
        refundMode: "none",
        agencyFeeRatio: 0,
        hasTaxFree: false,
        warningNotes: {
            zh: "⚠️ 美國各州銷售稅為地方稅，聯邦無退稅機制（僅免稅州如奧勒岡/德拉瓦稅率為 0%），一般觀光客無法退稅。",
            en: "⚠️ No federal VAT in the US. State/local sales tax is generally non-refundable to tourists (tax-free states: OR, DE, NH, MT)."
        }
    },
    {
        countryCode: "TH",
        countryName: { zh: "泰國", en: "Thailand", ja: "タイ" },
        flag: "🇹🇭",
        currency: "THB",
        vatRate: 0.07,
        minSpendThreshold: 2000,
        isThresholdTaxInclusive: true,
        refundMode: "intermediary_airport",
        agencyFeeRatio: 0.15,
        hasTaxFree: true,
        warningNotes: {
            zh: "單店單日滿 2,000 泰銖需請店家開立 PP10 黃單，出境時全部黃單累計滿 5,000 泰銖可於機場海關蓋章退稅（實退約 5%~6%）。",
            en: "Minimum 2,000 THB/store with PP10 tax form. Total departure claims must reach 5,000 THB to process at customs."
        }
    },
    {
        countryCode: "SG",
        countryName: { zh: "新加坡", en: "Singapore", ja: "シンガポール" },
        flag: "🇸🇬",
        currency: "SGD",
        vatRate: 0.09, // 2024 年上調至 9%
        minSpendThreshold: 100,
        isThresholdTaxInclusive: true,
        refundMode: "direct_customs",
        agencyFeeRatio: 0.12,
        hasTaxFree: true,
        warningNotes: {
            zh: "消費滿 S$100（同商家當日最多可湊 3 張發票），可於樟宜機場 eTRS 自助機台辦理退稅（扣除微量系統手續費實退約 7%~8%）。",
            en: "Spend S$100+ (up to 3 same-day receipts per store) to claim via eTRS kiosks at Changi Airport. Net ~7.5%."
        }
    },
    {
        countryCode: "AU",
        countryName: { zh: "澳洲", en: "Australia", ja: "オーストラリア" },
        flag: "🇦🇺",
        currency: "AUD",
        vatRate: 0.10,
        minSpendThreshold: 300,
        isThresholdTaxInclusive: true,
        refundMode: "direct_customs",
        agencyFeeRatio: 0.02, // 澳洲海關全額退稅，僅扣少量跨國轉帳手續費
        hasTaxFree: true,
        warningNotes: {
            zh: "出境前 60 天內，於同一商業登記號 (ABN) 商家累計滿 A$300 即可透過 TRS 機場櫃檯全額退還 10% GST，無私營代辦商抽成！",
            en: "Spend A$300+ with the same ABN within 60 days before flight. Reclaim full 10% GST directly via TRS without private agency cuts!"
        }
    },
    {
        countryCode: "CA",
        countryName: { zh: "加拿大", en: "Canada", ja: "カナダ" },
        flag: "🇨🇦",
        currency: "CAD",
        vatRate: 0.13,
        minSpendThreshold: 0,
        isThresholdTaxInclusive: false,
        refundMode: "none",
        agencyFeeRatio: 0,
        hasTaxFree: false,
        warningNotes: {
            zh: "⚠️ 加拿大已廢止訪客退稅計劃 (Visitor Rebate Program)，外國旅客無法申請聯邦 GST/HST 退稅。",
            en: "⚠️ Canada abolished the Visitor Rebate Program. GST/HST is non-refundable for international tourists."
        }
    },
    {
        countryCode: "VN",
        countryName: { zh: "越南", en: "Vietnam", ja: "ベトナム" },
        flag: "🇻🇳",
        currency: "VND",
        vatRate: 0.10,
        minSpendThreshold: 2000000,
        isThresholdTaxInclusive: true,
        refundMode: "intermediary_airport",
        agencyFeeRatio: 0.15,
        hasTaxFree: true,
        taxLabels: { inclusive: "含稅 (VAT)", exclusive: "未稅" },
        warningNotes: {
            zh: "單店單日滿 2,000,000 越南盾（約 NT$2,600），向店家索取退稅發票，於河內/胡志明國際機場海關出示退稅（實退率約 8.5%）。",
            en: "Vietnam 10% VAT refund for purchases of 2,000,000+ VND. Process at Hanoi/Saigon international airports."
        }
    },
    {
        countryCode: "HK",
        countryName: { zh: "香港", en: "Hong Kong", ja: "香港" },
        flag: "🇭🇰",
        currency: "HKD",
        vatRate: 0.0,
        minSpendThreshold: 0,
        isThresholdTaxInclusive: true,
        refundMode: "in_store",
        agencyFeeRatio: 0,
        hasTaxFree: true,
        taxLabels: { inclusive: "含稅", exclusive: "免稅" },
        warningNotes: {
            zh: "香港為自由免稅港，全境無商品消費稅或增值稅，標價即為免稅價（菸酒等應課稅品除外）。",
            en: "Hong Kong is a free tax port with 0% VAT. Prices are naturally tax-free."
        }
    },
    {
        countryCode: "TW",
        countryName: { zh: "台灣", en: "Taiwan", ja: "台湾" },
        flag: "🇹🇼",
        currency: "TWD",
        vatRate: 0.05,
        minSpendThreshold: 2000,
        isThresholdTaxInclusive: true,
        refundMode: "in_store",
        agencyFeeRatio: 0.20,
        hasTaxFree: true,
        taxLabels: { inclusive: "含稅", exclusive: "未稅" },
        warningNotes: {
            zh: "外籍旅客同一天於貼有退稅標誌之特約商店累計含稅消費滿 NT$ 2,000，可辦理 5% 營業稅退稅（扣除手續費實退約 4%）。",
            en: "Foreign travelers spending NT$2,000+ same day at authorized stores can claim 5% VAT (net ~4% after processing fee)."
        }
    },
    {
        countryCode: "CH",
        countryName: { zh: "瑞士", en: "Switzerland", ja: "スイス" },
        flag: "🇨🇭",
        currency: "CHF",
        vatRate: 0.081,
        reducedVatRate: 0.026,
        minSpendThreshold: 300,
        isThresholdTaxInclusive: true,
        refundMode: "intermediary_airport",
        agencyFeeRatio: 0.25,
        hasTaxFree: true,
        taxLabels: { inclusive: "含稅 (TTC/MWST)", exclusive: "未稅 (HT)" },
        warningNotes: {
            zh: "瑞士標準增值稅率為 8.1%，單筆含稅達 CHF 300 可退稅。非歐盟成員國，退稅單需於瑞士出境口蓋章。",
            en: "Switzerland standard VAT is 8.1% with CHF 300 threshold. Not an EU member; customs stamp required at Swiss border."
        }
    },
    {
        countryCode: "IS",
        countryName: { zh: "冰島", en: "Iceland", ja: "アイスランド" },
        flag: "🇮🇸",
        currency: "ISK",
        vatRate: 0.24,
        reducedVatRate: 0.11,
        minSpendThreshold: 12000,
        isThresholdTaxInclusive: true,
        refundMode: "intermediary_airport",
        agencyFeeRatio: 0.28,
        hasTaxFree: true,
        taxLabels: { inclusive: "含稅 (VSK)", exclusive: "未稅" },
        warningNotes: {
            zh: "冰島標準 VAT 為 24%（食品/書籍為 11%），單張發票含稅滿 12,000 ISK 可申請退稅，實退約 14%。",
            en: "Iceland 24% standard VAT with 12,000 ISK threshold. Scan forms or get customs stamp at Keflavik Airport."
        }
    },
    {
        countryCode: "NO",
        countryName: { zh: "挪威", en: "Norway", ja: "ノルウェー" },
        flag: "🇳🇴",
        currency: "NOK",
        vatRate: 0.25,
        reducedVatRate: 0.15,
        minSpendThreshold: 315,
        isThresholdTaxInclusive: true,
        refundMode: "intermediary_airport",
        agencyFeeRatio: 0.30,
        hasTaxFree: true,
        taxLabels: { inclusive: "含稅 (MVA)", exclusive: "未稅" },
        warningNotes: {
            zh: "挪威標準 MVA 高達 25%，一般商品滿 NOK 315、食品滿 NOK 290 即可退稅，實退約 12%~19%。",
            en: "Norway standard 25% VAT. Threshold NOK 315 for regular goods, NOK 290 for food."
        }
    }
]

/**
 * Resolves the effective tax rule considering dates and temporal transitions.
 */
export function resolveEffectiveTaxRule(rule: CountryTaxRule, currentDate: Date = new Date()): CountryTaxRule {
    if (!rule.effectiveDate || !rule.postEffectiveRule) {
        return rule
    }

    try {
        const thresholdDate = new Date(rule.effectiveDate)
        if (currentDate >= thresholdDate) {
            return {
                ...rule,
                ...rule.postEffectiveRule
            }
        }
    } catch {
        // Fallback to base rule on invalid date
    }

    return rule
}

/**
 * Resolves localized tax inclusive / exclusive display labels for a destination.
 */
export function getLocalizedTaxLabels(rule: CountryTaxRule, isZh: boolean = true): { inclusive: string; exclusive: string } {
    if (rule.taxLabels) {
        return rule.taxLabels
    }

    if (rule.countryCode === 'JP') {
        return {
            inclusive: isZh ? "含稅 (税込)" : "Tax Incl. (税込)",
            exclusive: isZh ? "未稅 (税抜)" : "Tax Excl. (税抜)"
        }
    }

    if (['FR', 'IT', 'DE', 'ES', 'CH'].includes(rule.countryCode)) {
        return {
            inclusive: isZh ? "含稅 (TTC)" : "Tax Incl. (TTC)",
            exclusive: isZh ? "未稅 (HT)" : "Tax Excl. (HT)"
        }
    }

    if (rule.countryCode === 'KR') {
        return {
            inclusive: isZh ? "含稅 (과세)" : "Tax Incl. (과세)",
            exclusive: isZh ? "未稅" : "Tax Excl."
        }
    }

    return {
        inclusive: isZh ? "含稅" : "Tax-Inclusive",
        exclusive: isZh ? "未稅" : "Tax-Exclusive"
    }
}
