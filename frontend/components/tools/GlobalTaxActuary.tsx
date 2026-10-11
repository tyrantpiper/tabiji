"use client"

import { useState, useEffect, useMemo, useId } from "react"
import { motion, AnimatePresence } from "framer-motion"
import {
    Calculator, AlertTriangle, ShieldCheck, CreditCard as CardIcon,
    Check, PlusCircle, Info, Globe, Search, Plus, Trash2,
    Sparkles, RotateCcw, Edit2
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { cn } from "@/lib/utils"
import { useLanguage } from "@/lib/LanguageContext"
import { useHaptic } from "@/lib/hooks"
import { getExchangeRate } from "@/lib/currency"
import { CountingNumber } from "@/components/ui/counting-number"

import { CountryTaxRule, CreditCardItem, ActuaryResult, TapeItem } from "@/lib/tax-rules/types"
import { DEFAULT_TAX_RULES, resolveEffectiveTaxRule, getLocalizedTaxLabels } from "@/lib/tax-rules/defaultTaxRules"
import { calculateTaxActuary, evaluateArithmeticExpression } from "@/lib/tax-rules/actuaryEngine"

const POPULAR_COUNTRY_CODES = ["JP", "KR", "FR", "IT", "DE", "ES", "TH", "SG", "AU", "US", "GB"]

interface GlobalTaxActuaryProps {
    cards?: CreditCardItem[]
    defaultCurrency?: string
    onAddExpense?: (expense: {
        title: string
        amount: number
        currency: string
        payment_method?: string
        card_name?: string
        cashback_rate?: number
    }) => void
}

export function GlobalTaxActuary({
    cards = [],
    defaultCurrency,
    onAddExpense
}: GlobalTaxActuaryProps) {
    const { lang } = useLanguage()
    const isZh = lang === 'zh'
    const haptic = useHaptic()
    const customVatId = useId()
    const customThresholdId = useId()

    // 1. Country Selection & In-Memory Custom Countries State
    const [customCountries, setCustomCountries] = useState<CountryTaxRule[]>([])
    const allCountries = useMemo(() => {
        const map = new Map<string, CountryTaxRule>()
        for (const rule of [...DEFAULT_TAX_RULES, ...customCountries]) {
            map.set(rule.countryCode, rule)
        }
        return Array.from(map.values())
    }, [customCountries])

    const [selectedCountryCode, setSelectedCountryCode] = useState<string>(() => {
        if (defaultCurrency) {
            const matched = DEFAULT_TAX_RULES.find(r => r.currency.toUpperCase() === defaultCurrency.toUpperCase())
            if (matched) return matched.countryCode
        }
        return "JP"
    })

    const activeRule = useMemo(() => {
        const found = allCountries.find(r => r.countryCode === selectedCountryCode) || allCountries[0]
        return resolveEffectiveTaxRule(found)
    }, [allCountries, selectedCountryCode])

    // Dynamic localized labels (税込/税抜 for JP, TTC/HT for EU, 과세 for KR, standard for others)
    const localizedLabels = useMemo(() => getLocalizedTaxLabels(activeRule, isZh), [activeRule, isZh])

    // 2. Calculator & Shopping Tape State (In-Memory Session Only)
    const [amountStr, setAmountStr] = useState<string>("10000")
    const [isTaxInclusive, setIsTaxInclusive] = useState<boolean>(true) // true = 含稅價, false = 未稅價
    const [isCalcOpen, setIsCalcOpen] = useState<boolean>(false)
    const [calcExpr, setCalcExpr] = useState<string>("")
    const [calcNote, setCalcNote] = useState<string>("")
    const [tapeItems, setTapeItems] = useState<TapeItem[]>([])

    // Computed tape total
    const tapeTotal = useMemo(() => {
        return tapeItems.reduce((acc, it) => acc + it.amount, 0)
    }, [tapeItems])

    // If tape has items, it drives the master amount
    const parsedAmount = tapeItems.length > 0 ? tapeTotal : (parseFloat(amountStr) || 0)

    // 3. Exchange Rate & Overrides State
    const [exchangeRate, setExchangeRate] = useState<number>(0.22)
    const [isEditingRate, setIsEditingRate] = useState<boolean>(false)
    const [isLoadingRate, setIsLoadingRate] = useState<boolean>(false)
    const [customVatRate, setCustomVatRate] = useState<number | undefined>(undefined)
    const [customThreshold, setCustomThreshold] = useState<number | undefined>(undefined)
    const [isRuleInfoOpen, setIsRuleInfoOpen] = useState<boolean>(false)

    // 4. Country Search & Creation Dialog State
    const [isCountryModalOpen, setIsCountryModalOpen] = useState<boolean>(false)
    const [countrySearchQuery, setCountrySearchQuery] = useState<string>("")
    const [isCreatingCustomCountry, setIsCreatingCustomCountry] = useState<boolean>(false)
    const [newCountryName, setNewCountryName] = useState<string>("")
    const [newCountryCode, setNewCountryCode] = useState<string>("")
    const [newCurrencyCode, setNewCurrencyCode] = useState<string>("")
    const [newVatRatePct, setNewVatRatePct] = useState<string>("10")
    const [newThresholdVal, setNewThresholdVal] = useState<string>("0")
    const [newIsGrossThreshold, setNewIsGrossThreshold] = useState<boolean>(true)

    // Sync exchange rate when currency changes
    useEffect(() => {
        let isMounted = true
        const fetchRate = async () => {
            setIsLoadingRate(true)
            try {
                const rate = await getExchangeRate(activeRule.currency)
                if (isMounted) {
                    setExchangeRate(rate > 0 ? rate : 1.0)
                }
            } catch {
                if (isMounted) setExchangeRate(1.0)
            } finally {
                if (isMounted) setIsLoadingRate(false)
            }
        }
        fetchRate()
        return () => { isMounted = false }
    }, [activeRule.currency])

    // Core Calculation Output
    const result: ActuaryResult = useMemo(() => {
        return calculateTaxActuary({
            amount: parsedAmount,
            isTaxInclusive,
            countryRule: activeRule,
            exchangeRate,
            cards,
            customVatRate,
            customThreshold
        })
    }, [parsedAmount, isTaxInclusive, activeRule, exchangeRate, cards, customVatRate, customThreshold])

    // Threshold Progress Percentage
    const thresholdPercentage = useMemo(() => {
        if (!activeRule.hasTaxFree || activeRule.minSpendThreshold <= 0) return 0
        const basis = activeRule.isThresholdTaxInclusive ? result.grossAmount : result.baseAmount
        const target = result.thresholdAmount || 1
        return Math.min(100, Math.round((basis / target) * 100))
    }, [activeRule, result])

    const handleSelectCountry = (code: string) => {
        haptic.selection()
        setSelectedCountryCode(code)
        setCustomVatRate(undefined)
        setCustomThreshold(undefined)
        setIsCountryModalOpen(false)
    }

    // Calculator Keypad Actions
    const handleKeypadPress = (val: string) => {
        haptic.tap()
        if (val === 'C') {
            setCalcExpr("")
        } else if (val === '⌫') {
            setCalcExpr(prev => prev.slice(0, -1))
        } else if (val === '=') {
            const evaluated = evaluateArithmeticExpression(calcExpr)
            if (evaluated !== null) {
                setCalcExpr(String(evaluated))
            }
        } else {
            setCalcExpr(prev => prev + val)
        }
    }

    // Add current calc expression to tape
    const handleAddCurrentToTape = () => {
        const evaluated = evaluateArithmeticExpression(calcExpr)
        if (evaluated === null || evaluated <= 0) return

        haptic.success()
        const newItem: TapeItem = {
            id: crypto.randomUUID(),
            expression: calcExpr,
            amount: evaluated,
            note: calcNote.trim() || undefined,
            timestamp: Date.now()
        }

        setTapeItems(prev => [...prev, newItem])
        setCalcExpr("")
        setCalcNote("")
    }

    // Delete single item from tape
    const handleDeleteTapeItem = (id: string) => {
        haptic.selection()
        setTapeItems(prev => prev.filter(it => it.id !== id))
    }

    // Clear entire tape
    const handleClearTape = () => {
        haptic.tap()
        setTapeItems([])
    }

    // Save user custom country to session
    const handleSaveCustomCountry = () => {
        if (!newCountryName.trim() || !newCurrencyCode.trim()) return
        haptic.success()

        const code = (newCountryCode.trim() || newCurrencyCode.trim().slice(0, 2)).toUpperCase()
        const vatRate = (parseFloat(newVatRatePct) || 0) / 100
        const threshold = parseFloat(newThresholdVal) || 0

        const customRule: CountryTaxRule = {
            countryCode: code,
            countryName: { zh: newCountryName, en: newCountryName, ja: newCountryName },
            flag: "🌐",
            currency: newCurrencyCode.toUpperCase(),
            vatRate,
            minSpendThreshold: threshold,
            isThresholdTaxInclusive: newIsGrossThreshold,
            refundMode: threshold > 0 ? "in_store" : "none",
            agencyFeeRatio: 0.2,
            hasTaxFree: threshold > 0,
            isCustom: true,
            taxLabels: {
                inclusive: isZh ? "含稅" : "Tax Incl.",
                exclusive: isZh ? "未稅" : "Tax Excl."
            }
        }

        setCustomCountries(prev => [...prev, customRule])
        setSelectedCountryCode(code)
        setIsCreatingCustomCountry(false)
        setIsCountryModalOpen(false)
        // Reset form
        setNewCountryName("")
        setNewCountryCode("")
        setNewCurrencyCode("")
    }

    const filteredCountries = useMemo(() => {
        if (!countrySearchQuery.trim()) return allCountries
        const q = countrySearchQuery.toLowerCase()
        return allCountries.filter(c =>
            c.countryName.zh.toLowerCase().includes(q) ||
            c.countryName.en.toLowerCase().includes(q) ||
            c.currency.toLowerCase().includes(q) ||
            c.countryCode.toLowerCase().includes(q)
        )
    }, [allCountries, countrySearchQuery])

    return (
        <div className="space-y-6">
            {/* 🇯🇵 1. 熱門國家快速切換膠囊帶 + 🌐 更多國家搜尋 */}
            <div className="space-y-2">
                <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-[#1E2927]/80 dark:text-[#E5EBEA]/80 flex items-center gap-1.5">
                        <Calculator className="w-3.5 h-3.5 text-[#E56E25]" />
                        {isZh ? "目的國與稅制矩陣" : "Destination & Tax Matrix"}
                    </span>
                    <button
                        type="button"
                        onClick={() => setIsRuleInfoOpen(true)}
                        className="text-[11px] text-[#0B3026] dark:text-emerald-400 font-medium flex items-center gap-1 hover:underline cursor-pointer"
                    >
                        <Info className="w-3 h-3" />
                        {isZh ? "海關規則依據" : "Customs Rules Info"}
                    </button>
                </div>

                <div className="flex items-center gap-1.5 overflow-x-auto pb-2 scrollbar-none -mx-1 px-1">
                    {POPULAR_COUNTRY_CODES.map(code => {
                        const rule = allCountries.find(r => r.countryCode === code)
                        if (!rule) return null
                        const isSelected = selectedCountryCode === code

                        return (
                            <button
                                key={code}
                                type="button"
                                onClick={() => handleSelectCountry(code)}
                                className={cn(
                                    "px-3 py-1.5 rounded-xl text-xs font-semibold shrink-0 transition-all cursor-pointer flex items-center gap-1.5 border active:scale-95",
                                    isSelected
                                        ? "bg-[#0B3026] dark:bg-[#164E40] text-white border-transparent shadow-xs"
                                        : "bg-white/80 dark:bg-[#1E2927]/60 text-[#1E2927]/70 dark:text-[#E5EBEA]/70 border-[#0B3026]/10 dark:border-white/10 hover:border-[#E56E25]/30"
                                )}
                            >
                                <span className="text-sm">{rule.flag}</span>
                                <span>{isZh ? rule.countryName.zh : rule.countryName.en}</span>
                                <span className="text-[10px] opacity-70">({rule.currency})</span>
                            </button>
                        )
                    })}

                    {/* 🌐 更多國家 / 自訂搜尋按鈕 */}
                    <button
                        type="button"
                        onClick={() => {
                            haptic.tap()
                            setIsCountryModalOpen(true)
                        }}
                        className={cn(
                            "px-3 py-1.5 rounded-xl text-xs font-semibold shrink-0 transition-all cursor-pointer flex items-center gap-1.5 border active:scale-95",
                            !POPULAR_COUNTRY_CODES.includes(selectedCountryCode)
                                ? "bg-[#0B3026] dark:bg-[#164E40] text-white border-transparent shadow-xs"
                                : "bg-white/80 dark:bg-[#1E2927]/60 text-[#1E2927]/80 dark:text-[#E5EBEA]/80 border-[#0B3026]/10 dark:border-white/10 hover:border-[#E56E25]/40"
                        )}
                    >
                        <Globe className="w-3.5 h-3.5 text-[#E56E25]" />
                        <span>
                            {!POPULAR_COUNTRY_CODES.includes(selectedCountryCode)
                                ? `${activeRule.flag} ${isZh ? activeRule.countryName.zh : activeRule.countryName.en}`
                                : (isZh ? "更多國家..." : "More...")}
                        </span>
                    </button>
                </div>
            </div>

            {/* 💰 2. 雙向金額輸入、在地化含稅/未稅切換與計算機按鈕 */}
            <Card className="rounded-2xl border-[#0B3026]/10 dark:border-white/10 bg-white/90 dark:bg-[#1E2927]/80 backdrop-blur-md shadow-xs overflow-hidden">
                <CardContent className="p-4 sm:p-5 space-y-4">
                    <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
                        <div className="flex-1">
                            <div className="flex items-center justify-between mb-1.5">
                                <Label className="text-xs font-semibold text-slate-500 dark:text-slate-400">
                                    {isZh ? `輸入 ${activeRule.flag} ${activeRule.currency} 標價金額` : `Sticker Price (${activeRule.currency})`}
                                </Label>
                                {tapeItems.length > 0 && (
                                    <Badge className="bg-[#0B3026]/10 dark:bg-emerald-400/15 text-[#0B3026] dark:text-emerald-300 border-none text-[10px]">
                                        紙帶鎖定累計中 ({tapeItems.length} 項)
                                    </Badge>
                                )}
                            </div>

                            <div className="relative flex items-center">
                                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-lg font-bold text-slate-400">
                                    {activeRule.currency}
                                </span>
                                <Input
                                    type="number"
                                    inputMode="decimal"
                                    value={tapeItems.length > 0 ? String(tapeTotal) : amountStr}
                                    onChange={(e) => {
                                        if (tapeItems.length === 0) setAmountStr(e.target.value)
                                    }}
                                    readOnly={tapeItems.length > 0}
                                    placeholder="0"
                                    className={cn(
                                        "h-13 pl-15 pr-24 text-2xl font-bold rounded-xl border-stone-200 dark:border-slate-700 tracking-tight transition-all",
                                        tapeItems.length > 0
                                            ? "bg-amber-50/50 dark:bg-amber-950/20 text-[#0B3026] dark:text-emerald-300"
                                            : "bg-stone-50/80 dark:bg-slate-900/60"
                                    )}
                                />
                                {/* 展開/折疊計算機按鈕 */}
                                <button
                                    type="button"
                                    onClick={() => {
                                        haptic.tap()
                                        setIsCalcOpen(prev => !prev)
                                    }}
                                    className={cn(
                                        "absolute right-2 px-2.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer flex items-center gap-1 active:scale-95",
                                        isCalcOpen
                                            ? "bg-[#E56E25] text-white shadow-xs"
                                            : "bg-stone-200/80 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-stone-300 dark:hover:bg-slate-700"
                                    )}
                                >
                                    <Calculator className="w-3.5 h-3.5" />
                                    <span>{isCalcOpen ? "收起" : "計算機"}</span>
                                </button>
                            </div>
                        </div>

                        {/* 在地化動態含稅 vs 未稅 Segmented Toggle */}
                        <div className="sm:self-end">
                            <Label className="text-xs font-semibold text-slate-500 dark:text-slate-400 mb-1.5 block">
                                {isZh ? "標價型態" : "Price Type"}
                            </Label>
                            <div className="flex bg-stone-100 dark:bg-slate-800 p-1 rounded-xl border border-stone-200 dark:border-slate-700 text-xs font-semibold select-none h-13 items-center">
                                <button
                                    type="button"
                                    onClick={() => {
                                        haptic.selection()
                                        setIsTaxInclusive(true)
                                    }}
                                    className={cn(
                                        "h-full px-3.5 rounded-lg transition-all cursor-pointer flex items-center justify-center gap-1",
                                        isTaxInclusive
                                            ? "bg-white dark:bg-slate-700 text-[#0B3026] dark:text-emerald-300 shadow-2xs font-bold"
                                            : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                                    )}
                                >
                                    <span>{localizedLabels.inclusive}</span>
                                </button>
                                <button
                                    type="button"
                                    onClick={() => {
                                        haptic.selection()
                                        setIsTaxInclusive(false)
                                    }}
                                    className={cn(
                                        "h-full px-3.5 rounded-lg transition-all cursor-pointer flex items-center justify-center gap-1",
                                        !isTaxInclusive
                                            ? "bg-white dark:bg-slate-700 text-[#E56E25] dark:text-amber-400 shadow-2xs font-bold"
                                            : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
                                    )}
                                >
                                    <span>{localizedLabels.exclusive}</span>
                                </button>
                            </div>
                        </div>
                    </div>

                    {/* 🧮 內嵌手持購物計算機與鍵盤 (可展開/折疊) */}
                    <AnimatePresence>
                        {isCalcOpen && (
                            <motion.div
                                initial={{ opacity: 0, height: 0 }}
                                animate={{ opacity: 1, height: "auto" }}
                                exit={{ opacity: 0, height: 0 }}
                                className="overflow-hidden pt-2"
                            >
                                <div className="p-3.5 rounded-xl bg-stone-100/80 dark:bg-slate-900/80 border border-stone-200 dark:border-slate-800 space-y-3">
                                    <div className="flex items-center justify-between">
                                        <span className="text-xs font-bold text-[#1E2927] dark:text-[#E5EBEA] flex items-center gap-1.5">
                                            <Calculator className="w-3.5 h-3.5 text-[#E56E25]" />
                                            {isZh ? "購物連續計算機" : "Shopping Calculator"}
                                        </span>
                                        <span className="text-[11px] text-slate-400">
                                            {isZh ? "支援四則運算，可逐筆加入暫存紙帶" : "Supports + - × ÷ with Tally Tape"}
                                        </span>
                                    </div>

                                    {/* 算式輸入與品名備註 */}
                                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                                        <div className="sm:col-span-2 relative">
                                            <Input
                                                value={calcExpr}
                                                onChange={(e) => setCalcExpr(e.target.value)}
                                                placeholder={isZh ? "輸入算式，如 1980*3 + 550" : "e.g. 1980*3 + 550"}
                                                className="h-10 text-sm font-mono font-bold rounded-lg bg-white dark:bg-slate-800 pr-16"
                                            />
                                            {calcExpr && (
                                                <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs font-bold text-emerald-600 dark:text-emerald-400">
                                                    = {evaluateArithmeticExpression(calcExpr) ?? "..."}
                                                </span>
                                            )}
                                        </div>
                                        <div>
                                            <Input
                                                value={calcNote}
                                                onChange={(e) => setCalcNote(e.target.value)}
                                                placeholder={isZh ? "備註品名 (選填)" : "Memo (Optional)"}
                                                className="h-10 text-xs rounded-lg bg-white dark:bg-slate-800"
                                            />
                                        </div>
                                    </div>

                                    {/* 計算機九宮格實體按鍵 */}
                                    <div className="grid grid-cols-4 gap-1.5 text-sm font-bold font-mono">
                                        {['C', '⌫', '/', '*'].map(key => (
                                            <button
                                                key={key}
                                                type="button"
                                                onClick={() => handleKeypadPress(key)}
                                                className="h-9 rounded-lg bg-stone-200/90 dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-stone-300 active:scale-95 transition-all cursor-pointer"
                                            >
                                                {key === '/' ? '÷' : key === '*' ? '×' : key}
                                            </button>
                                        ))}
                                        {['7', '8', '9', '-'].map(key => (
                                            <button
                                                key={key}
                                                type="button"
                                                onClick={() => handleKeypadPress(key)}
                                                className="h-9 rounded-lg bg-white dark:bg-slate-800/80 text-slate-800 dark:text-slate-100 hover:bg-stone-100 active:scale-95 transition-all cursor-pointer border border-stone-200/50 dark:border-slate-700/50"
                                            >
                                                {key}
                                            </button>
                                        ))}
                                        {['4', '5', '6', '+'].map(key => (
                                            <button
                                                key={key}
                                                type="button"
                                                onClick={() => handleKeypadPress(key)}
                                                className="h-9 rounded-lg bg-white dark:bg-slate-800/80 text-slate-800 dark:text-slate-100 hover:bg-stone-100 active:scale-95 transition-all cursor-pointer border border-stone-200/50 dark:border-slate-700/50"
                                            >
                                                {key}
                                            </button>
                                        ))}
                                        {['1', '2', '3', '='].map(key => (
                                            <button
                                                key={key}
                                                type="button"
                                                onClick={() => handleKeypadPress(key)}
                                                className={cn(
                                                    "h-9 rounded-lg transition-all cursor-pointer active:scale-95",
                                                    key === '='
                                                        ? "bg-[#0B3026] text-white dark:bg-emerald-600 font-bold"
                                                        : "bg-white dark:bg-slate-800/80 text-slate-800 dark:text-slate-100 border border-stone-200/50 dark:border-slate-700/50"
                                                )}
                                            >
                                                {key}
                                            </button>
                                        ))}
                                    </div>

                                    {/* 底部功能鍵：0、.、加入清單 */}
                                    <div className="grid grid-cols-4 gap-1.5 font-bold font-mono">
                                        <button
                                            type="button"
                                            onClick={() => handleKeypadPress('0')}
                                            className="h-9 rounded-lg bg-white dark:bg-slate-800/80 text-slate-800 dark:text-slate-100 border border-stone-200/50 dark:border-slate-700/50 active:scale-95"
                                        >
                                            0
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => handleKeypadPress('.')}
                                            className="h-9 rounded-lg bg-white dark:bg-slate-800/80 text-slate-800 dark:text-slate-100 border border-stone-200/50 dark:border-slate-700/50 active:scale-95"
                                        >
                                            .
                                        </button>
                                        <Button
                                            type="button"
                                            onClick={handleAddCurrentToTape}
                                            disabled={!calcExpr || evaluateArithmeticExpression(calcExpr) === null}
                                            className="col-span-2 h-9 bg-[#E56E25] hover:bg-[#D55E15] text-white text-xs font-bold rounded-lg active:scale-95"
                                        >
                                            <Plus className="w-3.5 h-3.5 mr-1" />
                                            {isZh ? "加入暫存紙帶" : "Add to Tape"}
                                        </Button>
                                    </div>
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>

                    {/* 🧾 暫存購物紙帶歷史清單 (Tally Tape Reel) */}
                    {tapeItems.length > 0 && (
                        <div className="p-3.5 rounded-xl bg-amber-50/60 dark:bg-amber-950/20 border border-amber-200/60 dark:border-amber-800/40 space-y-2.5">
                            <div className="flex items-center justify-between">
                                <span className="text-xs font-bold text-amber-900 dark:text-amber-200 flex items-center gap-1.5">
                                    <span>🧾 購物暫存紙帶明細 ({tapeItems.length} 筆)</span>
                                </span>
                                <button
                                    type="button"
                                    onClick={handleClearTape}
                                    className="text-[11px] text-rose-500 hover:underline flex items-center gap-0.5 cursor-pointer"
                                >
                                    <RotateCcw className="w-3 h-3" />
                                    <span>{isZh ? "清空紙帶" : "Clear Tape"}</span>
                                </button>
                            </div>

                            <div className="max-h-40 overflow-y-auto space-y-1.5 pr-1 scrollbar-thin">
                                {tapeItems.map((item, index) => (
                                    <div
                                        key={item.id}
                                        className="flex items-center justify-between text-xs p-2 rounded-lg bg-white dark:bg-slate-900 border border-amber-100 dark:border-slate-800"
                                    >
                                        <div className="flex items-center gap-2 truncate">
                                            <span className="font-mono text-slate-400 font-bold">#{index + 1}</span>
                                            <span className="font-mono font-medium truncate">{item.expression}</span>
                                            {item.note && (
                                                <Badge className="bg-stone-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 text-[10px] px-1.5 py-0 h-4 border-none truncate">
                                                    {item.note}
                                                </Badge>
                                            )}
                                        </div>

                                        <div className="flex items-center gap-2 shrink-0">
                                            <span className="font-bold text-slate-900 dark:text-slate-100">
                                                {item.amount.toLocaleString()} {activeRule.currency}
                                            </span>
                                            <button
                                                type="button"
                                                onClick={() => handleDeleteTapeItem(item.id)}
                                                className="text-slate-400 hover:text-rose-500 cursor-pointer p-0.5"
                                            >
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>

                            <div className="flex items-center justify-between pt-1 border-t border-amber-200/60 dark:border-amber-800/40 text-xs font-bold text-amber-950 dark:text-amber-100">
                                <span>{isZh ? "紙帶總金額" : "Tape Total"}</span>
                                <span className="text-sm font-extrabold text-[#0B3026] dark:text-emerald-300">
                                    {tapeTotal.toLocaleString()} {activeRule.currency}
                                </span>
                            </div>
                        </div>
                    )}

                    {/* 匯率資訊條 (支援點擊原地手動覆寫匯率) */}
                    <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 px-1 pt-1 border-t border-stone-100 dark:border-slate-800">
                        <div className="flex items-center gap-1.5">
                            <span>即時匯率: 1 {activeRule.currency} ≈</span>
                            {isEditingRate ? (
                                <input
                                    type="number"
                                    step="0.001"
                                    value={exchangeRate}
                                    onChange={(e) => setExchangeRate(parseFloat(e.target.value) || 1.0)}
                                    onBlur={() => setIsEditingRate(false)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') setIsEditingRate(false)
                                    }}
                                    autoFocus
                                    className="w-18 px-1.5 py-0.5 rounded border border-[#E56E25] bg-white dark:bg-slate-900 text-xs font-bold text-[#1E2927] dark:text-white"
                                />
                            ) : (
                                <button
                                    type="button"
                                    onClick={() => setIsEditingRate(true)}
                                    className="font-bold underline decoration-dotted hover:text-[#E56E25] cursor-pointer flex items-center gap-1"
                                    title={isZh ? "點擊自訂/覆寫匯率" : "Click to edit rate"}
                                >
                                    <span>{exchangeRate}</span>
                                    <Edit2 className="w-2.5 h-2.5 opacity-50" />
                                </button>
                            )}
                            <span>TWD</span>
                            {isLoadingRate && <span className="animate-spin text-xs">⏳</span>}
                        </div>

                        <div className="flex items-center gap-2">
                            <span>未稅: {result.baseAmount.toLocaleString()} {activeRule.currency}</span>
                            <span>•</span>
                            <span>稅金: {result.taxAmount.toLocaleString()} {activeRule.currency}</span>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* 🎯 3. 退稅門檻與湊單動態狀態卡 */}
            <Card className="rounded-2xl border-[#0B3026]/10 dark:border-white/10 bg-white/90 dark:bg-[#1E2927]/80 backdrop-blur-md shadow-xs overflow-hidden">
                <CardContent className="p-4 sm:p-5 space-y-3.5">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-[#1E2927] dark:text-[#E5EBEA]">
                                {isZh ? "海關免稅門檻狀態" : "Customs Threshold Status"}
                            </span>
                            {result.thresholdStatus === 'QUALIFIED' && (
                                <Badge className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30 text-[10px] font-bold">
                                    <Check className="w-3 h-3 mr-1" /> 已達標
                                </Badge>
                            )}
                            {result.thresholdStatus === 'BELOW_THRESHOLD' && (
                                <Badge className="bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30 text-[10px] font-bold">
                                    未達門檻 ({thresholdPercentage}%)
                                </Badge>
                            )}
                            {result.thresholdStatus === 'NO_TAX_FREE' && (
                                <Badge className="bg-slate-500/15 text-slate-600 dark:text-slate-400 border-slate-500/30 text-[10px]">
                                    無觀光退稅
                                </Badge>
                            )}
                        </div>

                        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                            門檻: {activeRule.minSpendThreshold > 0
                                ? `${activeRule.minSpendThreshold.toLocaleString()} ${activeRule.currency} (${activeRule.isThresholdTaxInclusive ? "含稅" : "未稅"})`
                                : "無最低門檻"
                            }
                        </span>
                    </div>

                    {/* Progress Bar (Only when tax-free exists) */}
                    {activeRule.hasTaxFree && activeRule.minSpendThreshold > 0 && (
                        <div className="space-y-1.5">
                            <Progress value={thresholdPercentage} className="h-2 rounded-full bg-stone-100 dark:bg-slate-800" />
                            {result.thresholdStatus === 'BELOW_THRESHOLD' && (
                                <p className="text-xs text-amber-600 dark:text-amber-400 font-medium flex items-center justify-between">
                                    <span>
                                        🛒 再湊 <strong>{result.shortfall.toLocaleString()}</strong> {activeRule.currency} 即可解鎖免稅！
                                    </span>
                                    <span>預估可省約 <strong>NT$ {result.potentialTaxSavingsTwd.toLocaleString()}</strong></span>
                                </p>
                            )}
                            {result.thresholdStatus === 'QUALIFIED' && (
                                <p className="text-xs text-emerald-600 dark:text-emerald-400 font-medium">
                                    🎉 本次消費已享免稅！預估實退金額：<strong>{result.estimatedNetRefund.toLocaleString()} {activeRule.currency}</strong> (約 NT$ {(result.estimatedNetRefund * exchangeRate).toFixed(0)})
                                </p>
                            )}
                        </div>
                    )}

                    {/* ⚠️ 無退稅警示 (英美加等國) */}
                    {!activeRule.hasTaxFree && (
                        <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-800 dark:text-amber-200 flex items-start gap-2">
                            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                            <div>
                                <p className="font-semibold">{isZh ? "注意：該國無外國旅客觀光退稅" : "Notice: No Tourist Tax Refund"}</p>
                                <p className="opacity-80 mt-0.5">{isZh ? activeRule.warningNotes?.zh : activeRule.warningNotes?.en}</p>
                            </div>
                        </div>
                    )}

                    {/* 🛡️ DCC 避坑卡片 (歐盟等代辦商模式) */}
                    {result.dccWarning && (
                        <motion.div
                            initial={{ opacity: 0, y: 4 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-xs text-rose-800 dark:text-rose-200 flex items-start gap-2"
                        >
                            <ShieldCheck className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                            <div>
                                <p className="font-bold flex items-center gap-1">
                                    <span>⚠️ 防掠奪性匯差陷阱 (Anti-DCC Defense)</span>
                                </p>
                                <p className="opacity-90 mt-0.5 leading-relaxed">
                                    {isZh
                                        ? "在機場辦理退稅至信用卡時，若機台或櫃檯詢問退款幣別，請務必勾選「當地貨幣 (EUR)」，切勿選新台幣 (TWD)！否則代辦商將加收 8%~15% 的 DCC 動態匯差手續費。"
                                        : "Always choose the LOCAL CURRENCY (EUR) for your credit card refund. Never select your home currency, or intermediaries will impose a predatory 8%~15% DCC markup!"
                                    }
                                </p>
                            </div>
                        </motion.div>
                    )}
                </CardContent>
            </Card>

            {/* 💳 4. 信用卡海外 1.5% 手續費 ✕ 回饋淨利差 ✕ 雙卡拆單神策 */}
            <Card className="rounded-2xl border-[#0B3026]/10 dark:border-white/10 bg-white/90 dark:bg-[#1E2927]/80 backdrop-blur-md shadow-xs overflow-hidden">
                <CardContent className="p-4 sm:p-5 space-y-4">
                    <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-[#1E2927] dark:text-[#E5EBEA] flex items-center gap-1.5">
                            <CardIcon className="w-3.5 h-3.5 text-blue-600" />
                            {isZh ? "海外刷卡實質淨支出比較 (含 1.5% 交易手續費)" : "Overseas Card Net Statement Cost"}
                        </span>
                        <span className="text-xs text-slate-500">
                            現金實付: NT$ {result.netCostTwdCash.toLocaleString()}
                        </span>
                    </div>

                    {/* 💡 雙卡拆單神策 Banner (若金額超越最高卡上限且能多賺 NT$30 以上) */}
                    {result.cardRecommendation?.splitStrategy && (
                        <div className="p-3.5 rounded-xl bg-linear-to-r from-amber-500/15 via-emerald-500/15 to-transparent border border-emerald-500/30 text-xs space-y-2">
                            <div className="flex items-center justify-between">
                                <span className="font-bold text-[#0B3026] dark:text-emerald-300 flex items-center gap-1.5">
                                    <Sparkles className="w-4 h-4 text-[#E56E25]" />
                                    <span>💡 雙卡拆單賺滿神策</span>
                                </span>
                                <Badge className="bg-emerald-600 text-white font-bold text-[10px]">
                                    比單刷多賺 NT$ {result.cardRecommendation.splitStrategy.advantageTwd.toLocaleString()}
                                </Badge>
                            </div>
                            <p className="text-slate-600 dark:text-slate-300 text-[11px] leading-relaxed">
                                最高回饋卡已達上限！建議分兩筆刷卡，把頂格回饋榨乾：
                            </p>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1 font-mono text-xs">
                                <div className="p-2 rounded-lg bg-white/80 dark:bg-slate-900/80 border border-stone-200 dark:border-slate-800">
                                    <p className="font-bold text-slate-900 dark:text-white">
                                        1. {result.cardRecommendation.splitStrategy.cardA.name}
                                    </p>
                                    <p className="text-[11px] text-slate-500 mt-0.5">
                                        刷滿額 <strong>NT$ {result.cardRecommendation.splitStrategy.spendA_Twd.toLocaleString()}</strong>
                                        （賺滿回饋 NT$ {result.cardRecommendation.splitStrategy.rewardA_Twd.toLocaleString()}）
                                    </p>
                                </div>
                                <div className="p-2 rounded-lg bg-white/80 dark:bg-slate-900/80 border border-stone-200 dark:border-slate-800">
                                    <p className="font-bold text-slate-900 dark:text-white">
                                        2. {result.cardRecommendation.splitStrategy.cardB.name}
                                    </p>
                                    <p className="text-[11px] text-slate-500 mt-0.5">
                                        刷剩餘 <strong>NT$ {result.cardRecommendation.splitStrategy.spendB_Twd.toLocaleString()}</strong>
                                        （接力回饋 NT$ {result.cardRecommendation.splitStrategy.rewardB_Twd.toLocaleString()}）
                                    </p>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* 單卡列表 */}
                    {cards && cards.length > 0 ? (
                        <div className="space-y-2">
                            {result.cardCalculations.map((calc) => (
                                <div
                                    key={calc.card.id}
                                    className={cn(
                                        "p-3 rounded-xl border transition-all flex items-center justify-between gap-3",
                                        calc.isBestOption
                                            ? "bg-emerald-500/10 dark:bg-emerald-400/15 border-emerald-500/40 text-emerald-950 dark:text-emerald-100 shadow-2xs"
                                            : "bg-stone-50/80 dark:bg-slate-900/40 border-stone-200 dark:border-slate-800 text-slate-700 dark:text-slate-300"
                                    )}
                                >
                                    <div className="min-w-0 flex-1">
                                        <div className="flex items-center gap-2">
                                            <p className="font-semibold text-sm truncate">{calc.card.name}</p>
                                            {calc.isBestOption && (
                                                <Badge className="bg-emerald-600 text-white text-[10px] px-1.5 py-0 h-4.5 font-bold shrink-0">
                                                    👑 最省錢
                                                </Badge>
                                            )}
                                        </div>
                                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                                            回饋 {calc.card.rewardRate}% - 1.5% 手續費 = 淨差
                                            <span className={cn(
                                                "ml-1 font-bold",
                                                (calc.card.rewardRate - 1.5) >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-500"
                                            )}>
                                                {(calc.card.rewardRate - 1.5) >= 0 ? "+" : ""}{(calc.card.rewardRate - 1.5).toFixed(1)}%
                                            </span>
                                            {calc.isLimitWarning && (
                                                <span className="ml-2 text-rose-500 font-bold">⚠️ 已超過該卡上限</span>
                                            )}
                                        </p>
                                    </div>

                                    <div className="text-right shrink-0">
                                        <p className="font-bold text-base text-[#1E2927] dark:text-white">
                                            NT$ <CountingNumber value={calc.netTwdCost} />
                                        </p>
                                        <p className={cn(
                                            "text-[11px] font-medium",
                                            calc.savingsComparedToCash >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-500"
                                        )}>
                                            {calc.savingsComparedToCash >= 0
                                                ? `比現金省 NT$ ${calc.savingsComparedToCash.toLocaleString()}`
                                                : `比現金貴 NT$ ${Math.abs(calc.savingsComparedToCash).toLocaleString()}`
                                            }
                                        </p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="p-4 rounded-xl border border-dashed border-stone-200 dark:border-slate-800 text-center text-xs text-slate-400 space-y-1">
                            <p>尚未加入信用卡資訊，目前顯示純現金換算。</p>
                            <p className="text-[11px] opacity-70">可至「卡片」頁籤新增您的海外回饋神卡（如 JCB 3%、玫瑰卡 3.3%）！</p>
                        </div>
                    )}

                    {/* ➕ 一鍵轉入行程記帳按鈕 */}
                    {onAddExpense && parsedAmount > 0 && (
                        <Button
                            type="button"
                            onClick={() => {
                                haptic.success()
                                onAddExpense({
                                    title: `${activeRule.countryName.zh} 購物 (${isTaxInclusive ? "含稅" : "未稅"})`,
                                    amount: result.netCostForeign,
                                    currency: activeRule.currency,
                                    payment_method: result.bestCard ? "CreditCard" : "Cash",
                                    card_name: result.bestCard?.card.name,
                                    cashback_rate: result.bestCard?.card.rewardRate
                                })
                            }}
                            className="w-full h-11 bg-[#0B3026] hover:bg-[#123E32] text-white font-bold rounded-xl shadow-xs cursor-pointer transition-all active:scale-98 flex items-center justify-center gap-2 mt-2"
                        >
                            <PlusCircle className="w-4 h-4" />
                            <span>{isZh ? "一鍵轉入這趟行程記帳" : "Record in Trip Expenses"}</span>
                            <span className="text-xs opacity-75 font-normal">
                                ({result.netCostForeign.toLocaleString()} {activeRule.currency} ≈ NT$ {result.bestCard ? result.bestCard.netTwdCost.toLocaleString() : result.netCostTwdCash.toLocaleString()})
                            </span>
                        </Button>
                    )}
                </CardContent>
            </Card>

            {/* 🌐 國家選擇與自訂國家對話框 */}
            <Dialog open={isCountryModalOpen} onOpenChange={setIsCountryModalOpen}>
                <DialogContent className="max-w-md rounded-2xl p-5">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 text-lg">
                            <Globe className="w-5 h-5 text-[#E56E25]" />
                            <span>{isZh ? "選擇或自訂目的國" : "Select or Custom Destination"}</span>
                        </DialogTitle>
                        <DialogDescription className="text-xs text-slate-500">
                            {isZh ? "搜尋全球預載免稅國或自由輸入當地稅率" : "Search destinations or customize tax rules"}
                        </DialogDescription>
                    </DialogHeader>

                    {!isCreatingCustomCountry ? (
                        <div className="space-y-3 py-2">
                            {/* 搜尋輸入框 */}
                            <div className="relative">
                                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                                <Input
                                    value={countrySearchQuery}
                                    onChange={(e) => setCountrySearchQuery(e.target.value)}
                                    placeholder={isZh ? "搜尋國家名稱、幣別代碼 (例如：瑞士, CHF)" : "Search country or currency..."}
                                    className="pl-9 h-10 text-xs rounded-xl"
                                />
                            </div>

                            {/* 國家清單 */}
                            <div className="max-h-60 overflow-y-auto space-y-1.5 pr-1 scrollbar-thin">
                                {filteredCountries.map(c => (
                                    <button
                                        key={c.countryCode}
                                        type="button"
                                        onClick={() => handleSelectCountry(c.countryCode)}
                                        className={cn(
                                            "w-full p-2.5 rounded-xl border text-left flex items-center justify-between text-xs transition-all cursor-pointer active:scale-98",
                                            selectedCountryCode === c.countryCode
                                                ? "bg-[#0B3026] text-white border-transparent font-bold"
                                                : "bg-stone-50 dark:bg-slate-900 border-stone-200 dark:border-slate-800 hover:border-[#E56E25]/50"
                                        )}
                                    >
                                        <div className="flex items-center gap-2">
                                            <span className="text-base">{c.flag}</span>
                                            <div>
                                                <p className="font-semibold">{isZh ? c.countryName.zh : c.countryName.en}</p>
                                                <p className="text-[10px] opacity-70">
                                                    {c.currency} • VAT {(c.vatRate * 100).toFixed(1)}% • 門檻 {c.minSpendThreshold > 0 ? `${c.minSpendThreshold.toLocaleString()} (${c.isThresholdTaxInclusive ? "含稅" : "未稅"})` : "無"}
                                                </p>
                                            </div>
                                        </div>
                                        {selectedCountryCode === c.countryCode && (
                                            <Check className="w-4 h-4 shrink-0 text-white" />
                                        )}
                                    </button>
                                ))}
                            </div>

                            {/* ➕ 自訂新國家按鈕 */}
                            <Button
                                type="button"
                                variant="outline"
                                onClick={() => setIsCreatingCustomCountry(true)}
                                className="w-full h-10 rounded-xl text-xs font-bold border-dashed border-[#E56E25]/50 text-[#E56E25] hover:bg-[#E56E25]/10"
                            >
                                <Plus className="w-4 h-4 mr-1" />
                                {isZh ? "找不到？自訂新國家與稅制" : "Custom New Destination"}
                            </Button>
                        </div>
                    ) : (
                        /* 自訂國家表單 */
                        <div className="space-y-3 py-2 text-xs">
                            <div className="space-y-1">
                                <Label className="text-[11px]">{isZh ? "國家/地區名稱" : "Country Name"}</Label>
                                <Input
                                    value={newCountryName}
                                    onChange={(e) => setNewCountryName(e.target.value)}
                                    placeholder={isZh ? "例：馬來西亞" : "e.g. Malaysia"}
                                    className="h-9 rounded-lg"
                                />
                            </div>

                            <div className="grid grid-cols-2 gap-2">
                                <div className="space-y-1">
                                    <Label className="text-[11px]">{isZh ? "貨幣代碼 (3 碼)" : "Currency (3 letters)"}</Label>
                                    <Input
                                        value={newCurrencyCode}
                                        onChange={(e) => setNewCurrencyCode(e.target.value.toUpperCase())}
                                        placeholder="MYR"
                                        maxLength={3}
                                        className="h-9 rounded-lg uppercase font-mono"
                                    />
                                </div>
                                <div className="space-y-1">
                                    <Label className="text-[11px]">{isZh ? "國家代碼 (2 碼)" : "Country Code"}</Label>
                                    <Input
                                        value={newCountryCode}
                                        onChange={(e) => setNewCountryCode(e.target.value.toUpperCase())}
                                        placeholder="MY"
                                        maxLength={2}
                                        className="h-9 rounded-lg uppercase font-mono"
                                    />
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-2">
                                <div className="space-y-1">
                                    <Label className="text-[11px]">{isZh ? "消費稅/VAT (%)" : "VAT Rate (%)"}</Label>
                                    <Input
                                        type="number"
                                        value={newVatRatePct}
                                        onChange={(e) => setNewVatRatePct(e.target.value)}
                                        placeholder="10"
                                        className="h-9 rounded-lg font-mono"
                                    />
                                </div>
                                <div className="space-y-1">
                                    <Label className="text-[11px]">{isZh ? "免稅門檻金額" : "Tax-free Threshold"}</Label>
                                    <Input
                                        type="number"
                                        value={newThresholdVal}
                                        onChange={(e) => setNewThresholdVal(e.target.value)}
                                        placeholder="0"
                                        className="h-9 rounded-lg font-mono"
                                    />
                                </div>
                            </div>

                            <div className="flex items-center justify-between p-2 rounded-lg bg-stone-100 dark:bg-slate-900 border text-[11px]">
                                <span>{isZh ? "門檻判定標準" : "Threshold Basis"}</span>
                                <button
                                    type="button"
                                    onClick={() => setNewIsGrossThreshold(prev => !prev)}
                                    className="px-2 py-0.5 rounded font-bold bg-white dark:bg-slate-800 border"
                                >
                                    {newIsGrossThreshold ? (isZh ? "含稅價判定" : "Gross Basis") : (isZh ? "未稅價判定" : "Net Basis")}
                                </button>
                            </div>

                            <div className="flex items-center gap-2 pt-2">
                                <Button
                                    type="button"
                                    variant="outline"
                                    onClick={() => setIsCreatingCustomCountry(false)}
                                    className="flex-1 h-9 rounded-xl text-xs"
                                >
                                    {isZh ? "返回搜尋" : "Back"}
                                </Button>
                                <Button
                                    type="button"
                                    onClick={handleSaveCustomCountry}
                                    disabled={!newCountryName.trim() || !newCurrencyCode.trim()}
                                    className="flex-1 h-9 bg-[#0B3026] text-white rounded-xl text-xs font-bold"
                                >
                                    {isZh ? "建立並套用" : "Create & Apply"}
                                </Button>
                            </div>
                        </div>
                    )}
                </DialogContent>
            </Dialog>

            {/* ℹ️ 規則與海關背景詳細對話框 */}
            <Dialog open={isRuleInfoOpen} onOpenChange={setIsRuleInfoOpen}>
                <DialogContent className="max-w-md rounded-2xl p-5">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2 text-lg">
                            <span>{activeRule.flag}</span>
                            <span>{activeRule.countryName.zh} 海關退稅規則與依據</span>
                        </DialogTitle>
                        <DialogDescription className="text-xs text-slate-500">
                            依據 2025–2026 最新官方海關與各國稅務局條例
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-3.5 text-xs text-slate-700 dark:text-slate-300 py-2">
                        <div className="p-3 rounded-xl bg-stone-50 dark:bg-slate-900 space-y-1.5 border border-stone-200 dark:border-slate-800">
                            <p><strong>標準稅率：</strong> {(activeRule.vatRate * 100).toFixed(1)}%</p>
                            <p><strong>最低門檻：</strong> {activeRule.minSpendThreshold > 0 ? `${activeRule.minSpendThreshold.toLocaleString()} ${activeRule.currency}` : "無門檻"}</p>
                            <p><strong>退稅模式：</strong> {
                                activeRule.refundMode === 'in_store' ? "店內護照掃描現折" :
                                    activeRule.refundMode === 'intermediary_airport' ? "代辦商機場海關過機退款 (扣約 25%~35% 手續費)" :
                                        activeRule.refundMode === 'direct_customs' ? "政府海關直接全額退稅" : "無觀光退稅"
                            }</p>
                        </div>

                        {activeRule.warningNotes && (
                            <div className="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-800 dark:text-amber-200">
                                <p className="font-bold mb-1">政策重點：</p>
                                <p className="leading-relaxed">{activeRule.warningNotes.zh}</p>
                            </div>
                        )}

                        {/* 自訂稅率與門檻（供特殊商品覆寫） */}
                        <div className="pt-2 border-t space-y-2">
                            <p className="font-semibold text-slate-800 dark:text-slate-200">🛠️ 進階自訂調整（針對特殊商品）：</p>
                            <div className="grid grid-cols-2 gap-2">
                                <div>
                                    <Label htmlFor={customVatId} className="text-[11px] text-slate-500">自訂稅率 (%)</Label>
                                    <Input
                                        id={customVatId}
                                        type="number"
                                        placeholder={(activeRule.vatRate * 100).toString()}
                                        value={customVatRate !== undefined ? (customVatRate * 100).toString() : ""}
                                        onChange={(e) => {
                                            const v = parseFloat(e.target.value)
                                            setCustomVatRate(!isNaN(v) && v >= 0 ? v / 100 : undefined)
                                        }}
                                        className="h-8 text-xs rounded-lg mt-1"
                                    />
                                </div>
                                <div>
                                    <Label htmlFor={customThresholdId} className="text-[11px] text-slate-500">自訂門檻 ({activeRule.currency})</Label>
                                    <Input
                                        id={customThresholdId}
                                        type="number"
                                        placeholder={activeRule.minSpendThreshold.toString()}
                                        value={customThreshold !== undefined ? customThreshold.toString() : ""}
                                        onChange={(e) => {
                                            const v = parseFloat(e.target.value)
                                            setCustomThreshold(!isNaN(v) && v >= 0 ? v : undefined)
                                        }}
                                        className="h-8 text-xs rounded-lg mt-1"
                                    />
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="flex justify-end pt-2">
                        <Button
                            size="sm"
                            onClick={() => setIsRuleInfoOpen(false)}
                            className="bg-slate-900 text-white rounded-xl text-xs px-4"
                        >
                            關閉
                        </Button>
                    </div>
                </DialogContent>
            </Dialog>
        </div>
    )
}
