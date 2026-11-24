"use client"

import { useState, useMemo, useEffect, useCallback, useRef } from "react"
import { AlertCircle, Wallet, Ticket, Plus, X, Check, Calculator, Eye, EyeOff, Loader2, Pencil } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useHaptic } from "@/lib/hooks"
import { toast } from "sonner"
import { cn } from "@/lib/utils"
import { useLanguage } from "@/lib/LanguageContext"
import { NoteItem, CostItem, TicketItem } from "@/lib/itinerary-types"
import { parseCostAmount } from "@/lib/itinerary-metrics"

interface EditableDailyTipsProps {
    tripId: string
    day: number
    notes: NoteItem[]
    costs: CostItem[]
    tickets: TicketItem[]
    onUpdate: (type: "notes" | "costs" | "tickets", data: NoteItem[] | CostItem[] | TicketItem[]) => Promise<boolean>
    readOnly?: boolean
    userId?: string  // 🆕 For tracking who set privacy
    defaultCurrency?: string
    displaySection?: "all" | "notes" | "costs" | "tickets" // 🆕 支援單獨渲染特定區塊
    className?: string                                     // 🆕 自訂外層樣式
}

interface NoteIconCategory {
    id: string
    labelZh: string
    labelEn: string
    icons: string[]
}

// 🎨 圖標庫 - 5 大分類雙語結構化排列
const NOTE_ICON_CATEGORIES: NoteIconCategory[] = [
    {
        id: "alerts",
        labelZh: "警示與提醒",
        labelEn: "Alerts & Tips",
        icons: ["⚠️", "💡", "📢", "🔔", "⏰", "📅"],
    },
    {
        id: "transport",
        labelZh: "交通與移動",
        labelEn: "Transport",
        icons: ["✈️", "🚇", "🚌", "🚗", "🚶", "📍"],
    },
    {
        id: "dining",
        labelZh: "餐飲與美食",
        labelEn: "Dining",
        icons: ["🍽️", "☕", "🍜", "🍱", "🍺", "🍰"],
    },
    {
        id: "stay_tickets",
        labelZh: "住宿與票券",
        labelEn: "Stay & Tickets",
        icons: ["🏨", "🏠", "🔑", "🎫", "🎭", "🎢"],
    },
    {
        id: "shopping_gear",
        labelZh: "購物與實用",
        labelEn: "Shopping & Gear",
        icons: ["🛒", "🛍️", "💳", "🏧", "🎒", "📸", "💊", "☂️", "🔋"],
    },
]

// 🛡️ 安全擷取視覺字素陣列 (Grapheme Clusters)，防止 UTF-16 Surrogate Pair 截斷或整句溢位
function extractGraphemes(input: string): string[] {
    const trimmed = input.trim()
    if (!trimmed) return []
    if (typeof Intl !== "undefined" && "Segmenter" in Intl) {
        const segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" })
        return Array.from(segmenter.segment(trimmed), (seg) => seg.segment)
    }
    return Array.from(trimmed)
}

// 🛡️ 支援連續替換單字素 ("🍜" + "🍕" -> "🍕")，同時保留貼上長句擷取首字素 ("🍜 一蘭拉麵" / "🍜一蘭拉麵" -> "🍜")
function resolveIconGrapheme(input: string, prevCommitted: string): string {
    const trimmed = input.trim()
    if (!trimmed) return ""

    const graphemes = extractGraphemes(trimmed)
    if (graphemes.length === 0) return ""
    if (graphemes.length === 1) return graphemes[0]

    const prevGrapheme = extractGraphemes(prevCommitted)[0] || ""
    if (prevGrapheme && trimmed !== prevGrapheme) {
        if (trimmed.startsWith(prevGrapheme)) {
            const added = trimmed.slice(prevGrapheme.length)
            const addedGraphemes = extractGraphemes(added)
            if (addedGraphemes.length === 1) {
                return addedGraphemes[0]
            }
        } else if (trimmed.endsWith(prevGrapheme)) {
            const prepended = trimmed.slice(0, trimmed.length - prevGrapheme.length)
            const prependedGraphemes = extractGraphemes(prepended)
            if (prependedGraphemes.length === 1) {
                return prependedGraphemes[0]
            }
        }
    }

    return graphemes[0]
}

// 🛡️ 安全讀取使用者識別碼，防禦 Safari 隱私模式 / WebView Storage SecurityError
function resolveOwnerId(userId?: string): string | undefined {
    if (userId) return userId
    try {
        if (typeof localStorage !== "undefined") {
            return localStorage.getItem("user_uuid") || undefined
        }
    } catch {
        // Ignore storage SecurityError in restricted environments
    }
    return undefined
}

// 🆕 IconPicker Component for categorized bilingual emoji selection
function IconPicker({
    value,
    onChange,
    zh = true,
}: {
    value: string
    onChange: (val: string) => void
    zh?: boolean
}) {
    const [isOpen, setIsOpen] = useState(false)
    const [customValue, setCustomValue] = useState("")
    const committedCustomRef = useRef("")

    const handleOpenChange = (nextOpen: boolean) => {
        if (nextOpen && customValue && customValue !== value) {
            setCustomValue("")
            committedCustomRef.current = ""
        }
        setIsOpen(nextOpen)
    }

    return (
        <Popover open={isOpen} onOpenChange={handleOpenChange}>
            <PopoverTrigger asChild>
                <button
                    type="button"
                    aria-label={zh ? "選擇圖示" : "Select or enter icon"}
                    title={zh ? "選擇或輸入圖示" : "Select or enter icon"}
                    className="w-11 h-10 text-lg shrink-0 flex items-center justify-center bg-white dark:bg-[#182320] border border-tabiji-forest/15 dark:border-white/15 rounded-xl hover:bg-tabiji-mist/60 dark:hover:bg-white/10 transition-colors touch-manipulation"
                >
                    {value || "⚠️"}
                </button>
            </PopoverTrigger>
            <PopoverContent
                collisionPadding={12}
                className="w-[min(17.5rem,calc(100vw-2rem))] p-3 rounded-2xl border-tabiji-forest/10 dark:border-white/10 bg-white dark:bg-[#182320] shadow-xl"
                align="start"
                onKeyDown={(e) => {
                    if (e.nativeEvent.isComposing) return
                    if (e.key === "Escape") {
                        e.preventDefault()
                        e.stopPropagation()
                        setIsOpen(false)
                    }
                }}
                onEscapeKeyDown={(e) => {
                    // Radix DismissableLayer passes the raw native KeyboardEvent directly in capture phase
                    if (e.isComposing) {
                        e.preventDefault()
                        return
                    }
                    e.stopPropagation()
                }}
            >
                <div className="space-y-2.5 max-h-64 overflow-y-auto pr-0.5">
                    {NOTE_ICON_CATEGORIES.map((category) => (
                        <div key={category.id} className="space-y-1">
                            <div className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 px-1">
                                {zh ? category.labelZh : category.labelEn}
                            </div>
                            <div className="grid grid-cols-6 gap-1">
                                {category.icons.map((icon) => (
                                    <button
                                        key={icon}
                                        type="button"
                                        onClick={() => {
                                            onChange(icon)
                                            setCustomValue("")
                                            committedCustomRef.current = ""
                                            setIsOpen(false)
                                        }}
                                        className={cn(
                                            "text-lg h-9 rounded-lg flex items-center justify-center hover:bg-tabiji-mist/70 dark:hover:bg-white/10 transition-colors touch-manipulation",
                                            value === icon && "bg-amber-500/15 dark:bg-amber-400/20 ring-1 ring-amber-500/40"
                                        )}
                                    >
                                        {icon}
                                    </button>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
                <div className="pt-2.5 mt-2 border-t border-tabiji-forest/10 dark:border-white/10">
                    <div className="flex gap-1.5">
                        <Input
                            placeholder={zh ? "貼上或輸入自訂 Emoji" : "Paste or type custom emoji"}
                            className="h-8 text-xs flex-1 bg-tabiji-paper/60 dark:bg-white/5 border-tabiji-forest/15 dark:border-white/15"
                            value={customValue}
                            onChange={(e) => {
                                const val = e.target.value
                                const isComposing = Boolean((e.nativeEvent as InputEvent)?.isComposing)
                                if (isComposing) {
                                    setCustomValue(val)
                                    return
                                }
                                const resolved = resolveIconGrapheme(val, committedCustomRef.current)
                                setCustomValue(resolved)
                                committedCustomRef.current = resolved
                                if (resolved) {
                                    onChange(resolved)
                                }
                            }}
                            onCompositionEnd={(e) => {
                                const resolved = resolveIconGrapheme(e.currentTarget.value, committedCustomRef.current)
                                setCustomValue(resolved)
                                committedCustomRef.current = resolved
                                if (resolved) {
                                    onChange(resolved)
                                }
                            }}
                            onKeyDown={(e) => {
                                if (e.nativeEvent.isComposing) return
                                if (e.key === "Enter") {
                                    e.preventDefault()
                                    e.stopPropagation()
                                    setIsOpen(false)
                                }
                                if (e.key === "Escape") {
                                    e.preventDefault()
                                    e.stopPropagation()
                                    setIsOpen(false)
                                }
                            }}
                        />
                        <Button
                            type="button"
                            size="sm"
                            aria-label={zh ? "確認自訂圖示" : "Confirm custom icon"}
                            className="h-8 px-2.5 bg-tabiji-forest hover:bg-tabiji-forest/90 text-tabiji-paper dark:bg-emerald-600 dark:hover:bg-emerald-500 dark:text-white"
                            onClick={() => setIsOpen(false)}
                        >
                            <Check className="w-3.5 h-3.5" />
                        </Button>
                    </div>
                </div>
            </PopoverContent>
        </Popover>
    )
}

// 🆕 橫向精緻幣別膠囊切換器 (取代舊版原生下拉選單，並自動鎖定與相容非預載自訂幣別)
function CurrencyPillSelector({
    value,
    onChange,
    defaultCurrency,
    extraCurrencies = [],
    zh = true,
}: {
    value?: string
    onChange: (currency: string) => void
    defaultCurrency: string
    extraCurrencies?: string[]
    zh?: boolean
}) {
    const [initialCurrency] = useState(value)
    const groupRef = useRef<HTMLDivElement | null>(null)
    const activePillRef = useRef<HTMLButtonElement | null>(null)
    const activeCurrency = value || defaultCurrency
    const options = useMemo(() => {
        const merged = [...CURRENCIES]
        for (const candidate of [initialCurrency, ...extraCurrencies, activeCurrency]) {
            if (candidate && !merged.includes(candidate)) {
                merged.push(candidate)
            }
        }
        return merged
    }, [initialCurrency, extraCurrencies, activeCurrency])

    useEffect(() => {
        const el = activePillRef.current
        const container = groupRef.current
        if (!el) return
        // 🛡️ 若外層具真實橫向捲動寬度，僅調整本條橫向 scrollLeft，杜絕 scrollIntoView 連帶將父層 IOSBottomSheet 垂直跳捲到底部
        if (container && container.scrollWidth > container.clientWidth) {
            const containerRect = container.getBoundingClientRect()
            const pillRect = el.getBoundingClientRect()
            if (pillRect.right > containerRect.right) {
                container.scrollLeft += pillRect.right - containerRect.right
            } else if (pillRect.left < containerRect.left) {
                container.scrollLeft -= containerRect.left - pillRect.left
            }
            return
        }
        if (typeof el.scrollIntoView === "function") {
            try {
                el.scrollIntoView({ inline: "nearest", block: "nearest" })
            } catch {
                el.scrollIntoView()
            }
        }
    }, [activeCurrency])

    return (
        <div
            ref={groupRef}
            role="group"
            aria-label={zh ? "選擇幣別" : "Currency selector"}
            className="flex items-center gap-1 overflow-x-auto scrollbar-none py-0.5 min-w-0 max-w-full"
        >
            {options.map((curr) => {
                const isSelected = curr === activeCurrency
                return (
                    <button
                        key={curr}
                        ref={isSelected ? activePillRef : undefined}
                        type="button"
                        aria-pressed={isSelected}
                        onClick={() => onChange(curr)}
                        className={cn(
                            "px-2.5 h-7 rounded-full text-xs font-semibold tracking-wide transition-all shrink-0 touch-manipulation",
                            isSelected
                                ? "bg-tabiji-forest text-tabiji-paper dark:bg-emerald-500 dark:text-slate-950 shadow-xs"
                                : "bg-white/80 dark:bg-white/6 text-slate-600 dark:text-slate-300 border border-tabiji-forest/10 dark:border-white/10 hover:bg-tabiji-mist/70 dark:hover:bg-white/12"
                        )}
                    >
                        {curr}
                    </button>
                )
            })}
        </div>
    )
}

// 🆕 新增／編輯表單底列隱私微開關
function PrivacyTogglePill({
    isPrivate,
    onToggle,
    zh,
}: {
    isPrivate: boolean
    onToggle: () => void
    zh: boolean
}) {
    return (
        <button
            type="button"
            aria-pressed={isPrivate}
            onClick={onToggle}
            className={cn(
                "inline-flex items-center gap-1.5 px-2.5 h-8 rounded-full text-xs font-medium transition-colors touch-manipulation",
                isPrivate
                    ? "bg-amber-500/15 text-amber-700 dark:bg-amber-400/15 dark:text-amber-300 border border-amber-500/30"
                    : "bg-white/70 dark:bg-white/6 text-slate-600 dark:text-slate-300 border border-tabiji-forest/10 dark:border-white/10 hover:bg-tabiji-mist/60 dark:hover:bg-white/10"
            )}
        >
            {isPrivate ? (
                <>
                    <EyeOff className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
                    <span>{zh ? "僅自己可見" : "Only me"}</span>
                </>
            ) : (
                <>
                    <Eye className="w-3.5 h-3.5 text-slate-400 dark:text-slate-400" />
                    <span>{zh ? "公開" : "Public"}</span>
                </>
            )}
        </button>
    )
}

// 🧠 AI Data Normalizer: 確保 AI 產出的 notes 能正確對應前端欄位
// 向下相容：舊格式 {item, content} → 新格式 {icon, title, content}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function normalizeNote(raw: any): NoteItem {
    if (!raw || typeof raw !== 'object') return { icon: '💡', title: '', content: '' }
    return {
        icon: raw.icon || undefined,
        title: raw.title || raw.item || '',
        content: raw.content || ''
    }
}

const CURRENCIES = ["JPY", "TWD", "USD", "EUR", "KRW", "HKD"]
const DEFAULT_CURRENCY = "TWD"

export default function EditableDailyTips({
    tripId: _tripId,  // eslint-disable-line @typescript-eslint/no-unused-vars
    day: _day,
    notes,
    costs,
    tickets,
    onUpdate,
    readOnly = false,
    userId,
    defaultCurrency,
    displaySection = "all",
    className,
}: EditableDailyTipsProps) {
    const { lang } = useLanguage()
    const zh = lang === 'zh'
    const haptic = useHaptic()
    const effectiveCurrency = (defaultCurrency || DEFAULT_CURRENCY).trim().toUpperCase() || DEFAULT_CURRENCY

    // Local state (initialized from props, synced via key prop from parent)
    const [localNotes, setLocalNotes] = useState<NoteItem[]>((notes || []).map(normalizeNote))
    const [localCosts, setLocalCosts] = useState<CostItem[]>(costs || [])
    const [localTickets, setLocalTickets] = useState<TicketItem[]>(tickets || [])

    // Adding state
    const [addingNote, setAddingNote] = useState(false)
    const [addingCost, setAddingCost] = useState(false)
    const [addingTicket, setAddingTicket] = useState(false)

    // 🆕 編輯模式狀態
    const [editingNotes, setEditingNotes] = useState(false)
    const [editingCosts, setEditingCosts] = useState(false)
    const [editingTickets, setEditingTickets] = useState(false)

    // 🆕 編輯中的資料副本
    const [editNotesData, setEditNotesData] = useState<NoteItem[]>([])
    const [editCostsData, setEditCostsData] = useState<CostItem[]>([])
    const [editTicketsData, setEditTicketsData] = useState<TicketItem[]>([])

    // Forms
    const [newNote, setNewNote] = useState<NoteItem>({ icon: "⚠️", title: "", content: "" })
    const [newCost, setNewCost] = useState<CostItem>({ item: "", amount: "", currency: "", note: "", is_private: false })
    const [newTicket, setNewTicket] = useState<TicketItem>({ name: "", price: "", currency: "", note: "", is_private: false })

    const [savingNotes, setSavingNotes] = useState(false)
    const [savingCosts, setSavingCosts] = useState(false)
    const [savingTickets, setSavingTickets] = useState(false)
    const saving = savingNotes || savingCosts || savingTickets

    // 🛡️ Synchronous single-frame lock refs to block double-tap duplicate creation
    const noteLockRef = useRef(false)
    const costLockRef = useRef(false)
    const ticketLockRef = useRef(false)

    // 🆕 Per-item processing state strictly for in-place row toggles (never populated on delete splice to avoid index-shift spinners)
    const [processingCosts, setProcessingCosts] = useState<Set<number>>(new Set())
    const [processingTickets, setProcessingTickets] = useState<Set<number>>(new Set())

    // 🔧 FIX: Sync local state when props update (async data loading)
    // 🛡️ L4 Protection: Skip sync if user is currently adding, editing, or saving an item
    useEffect(() => {
        if (!addingNote && !editingNotes && !savingNotes) {
            setLocalNotes((notes || []).map(normalizeNote))
        }
    }, [notes, addingNote, editingNotes, savingNotes])

    useEffect(() => {
        if (!addingCost && !editingCosts && !savingCosts && processingCosts.size === 0) {
            setLocalCosts(costs || [])
        }
    }, [costs, addingCost, editingCosts, savingCosts, processingCosts.size])

    useEffect(() => {
        if (!addingTicket && !editingTickets && !savingTickets && processingTickets.size === 0) {
            setLocalTickets(tickets || [])
        }
    }, [tickets, addingTicket, editingTickets, savingTickets, processingTickets.size])

    // ⚡ 即時協同：接收廣播事件，毫秒級反映同伴新增或修改的內容
    useEffect(() => {
        const handleCollab = (e: Event) => {
            const detail = (e as CustomEvent).detail
            if (detail?.event === "tip:update" && Number(detail?.dayIndex) === Number(_day)) {
                const currentOwnerId = resolveOwnerId(userId)
                const filterVisiblePrivate = <T extends { is_private?: boolean; private_owner_id?: string }>(items: T[]): T[] =>
                    items.filter((entry) => {
                        if (!entry || typeof entry !== "object") return false
                        if (!entry.is_private) return true
                        return Boolean(currentOwnerId && entry.private_owner_id && entry.private_owner_id === currentOwnerId)
                    })

                if (detail.type === "notes" && !editingNotes && !addingNote && !savingNotes) {
                    if (Array.isArray(detail.data)) {
                        setLocalNotes(detail.data.map(normalizeNote))
                    }
                } else if (detail.type === "costs" && !editingCosts && !addingCost && !savingCosts && processingCosts.size === 0) {
                    if (Array.isArray(detail.data)) {
                        setLocalCosts(filterVisiblePrivate(detail.data as CostItem[]))
                    }
                } else if (detail.type === "tickets" && !editingTickets && !addingTicket && !savingTickets && processingTickets.size === 0) {
                    if (Array.isArray(detail.data)) {
                        setLocalTickets(filterVisiblePrivate(detail.data as TicketItem[]))
                    }
                }
            }
        }
        window.addEventListener("tabiji:collab-event", handleCollab)
        return () => window.removeEventListener("tabiji:collab-event", handleCollab)
    }, [_day, userId, editingNotes, addingNote, savingNotes, editingCosts, addingCost, savingCosts, processingCosts.size, editingTickets, addingTicket, savingTickets, processingTickets.size])

    // 🆕 Exchange rates for conversion display
    const [exchangeRates, setExchangeRates] = useState<Record<string, number>>({ JPY: 0.22 }) // Default JPY→TWD

    // Fetch exchange rates on mount with unmount guard
    useEffect(() => {
        let isCancelled = false
        const fetchRates = async () => {
            try {
                const res = await fetch(
                    "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/twd.json"
                )
                const data = await res.json()
                if (!isCancelled && data?.twd) {
                    const rates: Record<string, number> = {}
                    for (const [cur, rate] of Object.entries(data.twd)) {
                        if (typeof rate === 'number' && rate > 0) {
                            rates[cur.toUpperCase()] = 1 / rate // Invert: TWD per unit
                        }
                    }
                    setExchangeRates(rates)
                }
            } catch { /* Use default rates */ }
        }
        fetchRates()
        return () => {
            isCancelled = true
        }
    }, [])

    // === Helpers ===
    const formatCurrency = (amount: string | number, currency?: string) => {
        const parsed = parseCostAmount(amount, currency, effectiveCurrency)
        if (parsed.amount === null) return String(amount)

        const displayCurrency = parsed.currency
        const baseDisplay = `${displayCurrency} ${parsed.amount.toLocaleString()}`

        if (displayCurrency !== 'TWD' && exchangeRates[displayCurrency]) {
            const twdAmount = Math.round(parsed.amount * exchangeRates[displayCurrency])
            return `${baseDisplay} (≈NT$${twdAmount.toLocaleString()})`
        }

        return baseDisplay
    }

    const calculateTotal = useCallback((items: { amount?: string; price?: string; currency?: string }[]) => {
        const totals: Record<string, number> = {}
        items.forEach(item => {
            const valRaw = item.amount ?? item.price
            const parsed = parseCostAmount(valRaw, item.currency, effectiveCurrency)
            if (parsed.amount !== null && parsed.amount > 0) {
                totals[parsed.currency] = (totals[parsed.currency] || 0) + parsed.amount
            }
        })
        return totals
    }, [effectiveCurrency])

    const costsTotal = useMemo(() => calculateTotal(localCosts), [localCosts, calculateTotal])
    const ticketsTotal = useMemo(() => calculateTotal(localTickets), [localTickets, calculateTotal])
    const costExtraCurrencies = useMemo(() => {
        const set = new Set<string>()
        const source = editingCosts ? [...localCosts, ...editCostsData] : localCosts
        for (const item of source) {
            const parsed = parseCostAmount(item.amount, item.currency, effectiveCurrency)
            if (parsed.extractedCurrency) set.add(parsed.extractedCurrency)
            if (typeof item.currency === "string" && item.currency.trim()) {
                set.add(item.currency.trim().toUpperCase())
            }
        }
        return Array.from(set)
    }, [localCosts, editCostsData, editingCosts, effectiveCurrency])
    const ticketExtraCurrencies = useMemo(() => {
        const set = new Set<string>()
        const source = editingTickets ? [...localTickets, ...editTicketsData] : localTickets
        for (const item of source) {
            const parsed = parseCostAmount(item.price, item.currency, effectiveCurrency)
            if (parsed.extractedCurrency) set.add(parsed.extractedCurrency)
            if (typeof item.currency === "string" && item.currency.trim()) {
                set.add(item.currency.trim().toUpperCase())
            }
        }
        return Array.from(set)
    }, [localTickets, editTicketsData, editingTickets, effectiveCurrency])

    // === Draft Reset & Cancel Helpers ===
    const handleCancelAddNote = useCallback(() => {
        setAddingNote(false)
        setNewNote({ icon: "⚠️", title: "", content: "" })
    }, [])

    const handleCancelAddCost = useCallback(() => {
        setAddingCost(false)
        setNewCost({ item: "", amount: "", currency: "", note: "", is_private: false })
    }, [])

    const handleCancelAddTicket = useCallback(() => {
        setAddingTicket(false)
        setNewTicket({ name: "", price: "", currency: "", note: "", is_private: false })
    }, [])

    const handleCancelEditNotes = useCallback(() => {
        setEditingNotes(false)
        setEditNotesData([])
        haptic.tap()
    }, [haptic])

    const handleCancelEditCosts = useCallback(() => {
        setEditingCosts(false)
        setEditCostsData([])
        haptic.tap()
    }, [haptic])

    const handleCancelEditTickets = useCallback(() => {
        setEditingTickets(false)
        setEditTicketsData([])
        haptic.tap()
    }, [haptic])

    const hasOpenOverlay = () =>
        Boolean(
            document.querySelector(
                '[data-slot="dialog-content"][data-state="open"], [data-slot="alert-dialog-content"][data-state="open"], [data-slot="popover-content"][data-state="open"]'
            )
        )

    // 🛡️ 攔截內嵌新增／編輯表單的 Escape，避免在輸入框或表單按鈕聚焦時冒泡關閉父層 IOSBottomSheet
    const hasActiveForm = addingNote || editingNotes || addingCost || editingCosts || addingTicket || editingTickets
    useEffect(() => {
        if (!hasActiveForm) return
        const handleDocumentKeyDown = (e: KeyboardEvent) => {
            if (e.key !== "Escape" || e.isComposing || e.defaultPrevented || hasOpenOverlay()) return
            e.preventDefault()
            e.stopPropagation()
            if (editingNotes) handleCancelEditNotes()
            else if (addingNote) handleCancelAddNote()
            else if (editingCosts) handleCancelEditCosts()
            else if (addingCost) handleCancelAddCost()
            else if (editingTickets) handleCancelEditTickets()
            else if (addingTicket) handleCancelAddTicket()
        }
        document.addEventListener("keydown", handleDocumentKeyDown)
        return () => document.removeEventListener("keydown", handleDocumentKeyDown)
    }, [
        hasActiveForm,
        addingNote,
        editingNotes,
        addingCost,
        editingCosts,
        addingTicket,
        editingTickets,
        handleCancelAddNote,
        handleCancelEditNotes,
        handleCancelAddCost,
        handleCancelEditCosts,
        handleCancelAddTicket,
        handleCancelEditTickets,
    ])

    const handleNotesCardKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
        if (e.nativeEvent.isComposing || e.key !== "Escape" || e.defaultPrevented || hasOpenOverlay()) return
        if (!addingNote && !editingNotes) return
        e.preventDefault()
        e.stopPropagation()
        if (editingNotes) handleCancelEditNotes()
        else if (addingNote) handleCancelAddNote()
    }

    const handleCostsCardKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
        if (e.nativeEvent.isComposing || e.key !== "Escape" || e.defaultPrevented || hasOpenOverlay()) return
        if (!addingCost && !editingCosts) return
        e.preventDefault()
        e.stopPropagation()
        if (editingCosts) handleCancelEditCosts()
        else if (addingCost) handleCancelAddCost()
    }

    const handleTicketsCardKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
        if (e.nativeEvent.isComposing || e.key !== "Escape" || e.defaultPrevented || hasOpenOverlay()) return
        if (!addingTicket && !editingTickets) return
        e.preventDefault()
        e.stopPropagation()
        if (editingTickets) handleCancelEditTickets()
        else if (addingTicket) handleCancelAddTicket()
    }

    // === Handlers ===

    // Notes
    const handleAddNote = async () => {
        if (savingNotes || noteLockRef.current) return
        if (!newNote.title.trim()) {
            toast.error(zh ? "請輸入標題" : "Please enter a title")
            return
        }
        noteLockRef.current = true
        const prevNotes = localNotes
        const updated = [...localNotes, { ...newNote, title: newNote.title.trim(), content: newNote.content.trim() }]
        // ⚡ 0ms 樂觀立即更新
        setLocalNotes(updated)
        setNewNote({ icon: "⚠️", title: "", content: "" })
        setAddingNote(false)
        haptic.tap()
        setSavingNotes(true)
        try {
            if (await onUpdate("notes", updated)) {
                toast.success(zh ? "已新增提醒" : "Reminder added")
            } else {
                setLocalNotes(prevNotes)
                toast.error(zh ? "新增失敗" : "Failed to add")
            }
        } catch {
            setLocalNotes(prevNotes)
            toast.error(zh ? "新增失敗" : "Failed to add")
        } finally {
            setSavingNotes(false)
            noteLockRef.current = false
        }
    }

    const handleRemoveNote = async (idx: number) => {
        if (savingNotes || noteLockRef.current) return
        noteLockRef.current = true
        haptic.tap()
        const prevNotes = localNotes
        const updated = localNotes.filter((_, i) => i !== idx)
        setLocalNotes(updated)
        setSavingNotes(true)
        try {
            if (await onUpdate("notes", updated)) {
                toast.success(zh ? "已移除" : "Removed")
            } else {
                setLocalNotes(prevNotes)
                toast.error(zh ? "移除失敗" : "Failed to remove")
            }
        } catch {
            setLocalNotes(prevNotes)
            toast.error(zh ? "移除失敗" : "Failed to remove")
        } finally {
            setSavingNotes(false)
            noteLockRef.current = false
        }
    }

    const handleStartEditNotes = () => {
        setEditNotesData([...localNotes])
        setEditingNotes(true)
        handleCancelAddNote()
        haptic.tap()
    }

    const handleSaveNotes = async () => {
        if (savingNotes || noteLockRef.current) return
        if (editNotesData.some((note) => !(note.title ?? "").trim())) {
            toast.error(zh ? "請輸入標題" : "Please enter a title")
            return
        }
        const normalizedNotes = editNotesData.map((note) => ({
            ...note,
            title: (note.title ?? "").trim(),
            content: (note.content ?? "").trim(),
        }))
        noteLockRef.current = true
        haptic.tap()
        setSavingNotes(true)
        try {
            if (await onUpdate("notes", normalizedNotes)) {
                setLocalNotes(normalizedNotes)
                setEditingNotes(false)
                setEditNotesData([])
                toast.success(zh ? "已儲存修改" : "Changes saved")
            } else {
                toast.error(zh ? "儲存失敗" : "Save failed")
            }
        } catch {
            toast.error(zh ? "儲存失敗" : "Save failed")
        } finally {
            setSavingNotes(false)
            noteLockRef.current = false
        }
    }

    const handleUpdateEditNote = (idx: number, field: keyof NoteItem, value: string) => {
        setEditNotesData(prev => prev.map((note, i) =>
            i === idx ? { ...note, [field]: value } : note
        ))
    }

    // Costs
    const handleAddCost = async () => {
        if (savingCosts || costLockRef.current) return
        if (!newCost.item.trim() || !newCost.amount.trim()) {
            toast.error(zh ? "請輸入項目和金額" : "Please enter item and amount")
            return
        }
        const parsedAmount = parseCostAmount(newCost.amount, newCost.currency || undefined, effectiveCurrency)
        if (parsedAmount.isNegative) {
            toast.error(zh ? "金額不可為負數" : "Amount cannot be negative")
            return
        }
        costLockRef.current = true
        const prevCosts = localCosts
        const isPrivate = Boolean(newCost.is_private)
        const costToAdd: CostItem = {
            item: newCost.item.trim(),
            amount: parsedAmount.normalizedAmount ?? newCost.amount.trim(),
            currency: parsedAmount.currency,
            note: newCost.note?.trim() || "",
            ...(isPrivate ? { is_private: true, private_owner_id: resolveOwnerId(userId) } : {}),
        }
        const updated = [...localCosts, costToAdd]
        // ⚡ 0ms 樂觀新增花費
        setLocalCosts(updated)
        setNewCost({ item: "", amount: "", currency: "", note: "", is_private: false })
        setAddingCost(false)
        haptic.tap()
        setSavingCosts(true)
        try {
            if (await onUpdate("costs", updated)) {
                toast.success(zh ? "已新增花費" : "Cost added")
            } else {
                setLocalCosts(prevCosts)
                toast.error(zh ? "新增失敗" : "Failed to add")
            }
        } catch {
            setLocalCosts(prevCosts)
            toast.error(zh ? "新增失敗" : "Failed to add")
        } finally {
            setSavingCosts(false)
            costLockRef.current = false
        }
    }

    const handleRemoveCost = async (idx: number) => {
        if (savingCosts || costLockRef.current) return
        costLockRef.current = true
        haptic.tap()
        const prevCosts = localCosts
        const updated = localCosts.filter((_, i) => i !== idx)
        setLocalCosts(updated)
        setSavingCosts(true)
        try {
            if (await onUpdate("costs", updated)) {
                toast.success(zh ? "已移除" : "Removed")
            } else {
                setLocalCosts(prevCosts)
                toast.error(zh ? "移除失敗" : "Failed to remove")
            }
        } catch {
            setLocalCosts(prevCosts)
            toast.error(zh ? "移除失敗" : "Failed to remove")
        } finally {
            setSavingCosts(false)
            costLockRef.current = false
        }
    }

    const handleTogglePrivacyCost = async (idx: number) => {
        if (processingCosts.has(idx) || savingCosts || costLockRef.current) return
        costLockRef.current = true
        haptic.tap()
        setProcessingCosts(prev => new Set(prev).add(idx))
        const prevCosts = localCosts
        const ownerId = resolveOwnerId(userId)
        const updated: CostItem[] = localCosts.map((c, i) =>
            i === idx ? {
                ...c,
                is_private: !c.is_private,
                private_owner_id: !c.is_private ? ownerId : undefined
            } : c
        )
        setLocalCosts(updated)
        setSavingCosts(true)
        try {
            if (await onUpdate("costs", updated)) {
                toast.success(updated[idx].is_private ? (zh ? "已設為私人" : "Set to private") : (zh ? "已設為公開" : "Set to public"))
            } else {
                setLocalCosts(prevCosts)
            }
        } catch {
            setLocalCosts(prevCosts)
        } finally {
            setSavingCosts(false)
            costLockRef.current = false
            setProcessingCosts(prev => {
                const next = new Set(prev)
                next.delete(idx)
                return next
            })
        }
    }

    const handleStartEditCosts = () => {
        setEditCostsData(
            localCosts.map((cost) => {
                const parsed = parseCostAmount(cost.amount, cost.currency, effectiveCurrency)
                return {
                    ...cost,
                    amount: parsed.normalizedAmount ?? String(cost.amount ?? ""),
                    currency: parsed.currency,
                }
            })
        )
        setEditingCosts(true)
        handleCancelAddCost()
        haptic.tap()
    }

    const handleSaveCosts = async () => {
        if (savingCosts || costLockRef.current) return
        if (editCostsData.some((cost) => !(cost.item ?? "").trim() || !String(cost.amount ?? "").trim())) {
            toast.error(zh ? "請輸入項目和金額" : "Please enter item and amount")
            return
        }
        const normalizedCosts: CostItem[] = []
        for (const cost of editCostsData) {
            const parsed = parseCostAmount(cost.amount, cost.currency, effectiveCurrency)
            if (parsed.isNegative) {
                toast.error(zh ? "金額不可為負數" : "Amount cannot be negative")
                return
            }
            normalizedCosts.push({
                ...cost,
                item: (cost.item ?? "").trim(),
                amount: parsed.normalizedAmount ?? String(cost.amount).trim(),
                currency: parsed.currency,
                ...(cost.note !== undefined ? { note: cost.note.trim() } : {}),
            })
        }
        costLockRef.current = true
        haptic.tap()
        setSavingCosts(true)
        try {
            if (await onUpdate("costs", normalizedCosts)) {
                setLocalCosts(normalizedCosts)
                setEditingCosts(false)
                setEditCostsData([])
                toast.success(zh ? "已儲存修改" : "Changes saved")
            } else {
                toast.error(zh ? "儲存失敗" : "Save failed")
            }
        } catch {
            toast.error(zh ? "儲存失敗" : "Save failed")
        } finally {
            setSavingCosts(false)
            costLockRef.current = false
        }
    }

    const handleUpdateEditCost = (idx: number, field: keyof CostItem, value: string) => {
        setEditCostsData(prev => prev.map((cost, i) =>
            i === idx ? { ...cost, [field]: value } : cost
        ))
    }

    const handleToggleEditCostPrivacy = (idx: number) => {
        const ownerId = resolveOwnerId(userId)
        setEditCostsData(prev => prev.map((cost, i) => {
            if (i !== idx) return cost
            const nextPrivate = !cost.is_private
            return {
                ...cost,
                is_private: nextPrivate,
                private_owner_id: nextPrivate ? (cost.private_owner_id || ownerId) : undefined,
            }
        }))
    }

    // Tickets
    const handleAddTicket = async () => {
        if (savingTickets || ticketLockRef.current) return
        if (!newTicket.name.trim() || !newTicket.price.trim()) {
            toast.error(zh ? "請輸入票券名稱和價格" : "Please enter ticket name and price")
            return
        }
        const parsedPrice = parseCostAmount(newTicket.price, newTicket.currency || undefined, effectiveCurrency)
        if (parsedPrice.isNegative) {
            toast.error(zh ? "價格不可為負數" : "Price cannot be negative")
            return
        }
        ticketLockRef.current = true
        const prevTickets = localTickets
        const isPrivate = Boolean(newTicket.is_private)
        const ticketToAdd: TicketItem = {
            name: newTicket.name.trim(),
            price: parsedPrice.normalizedAmount ?? newTicket.price.trim(),
            currency: parsedPrice.currency,
            note: newTicket.note?.trim() || "",
            ...(isPrivate ? { is_private: true, private_owner_id: resolveOwnerId(userId) } : {}),
        }
        const updated = [...localTickets, ticketToAdd]
        // ⚡ 0ms 樂觀新增票券
        setLocalTickets(updated)
        setNewTicket({ name: "", price: "", currency: "", note: "", is_private: false })
        setAddingTicket(false)
        haptic.tap()
        setSavingTickets(true)
        try {
            if (await onUpdate("tickets", updated)) {
                toast.success(zh ? "已新增票券" : "Ticket added")
            } else {
                setLocalTickets(prevTickets)
                toast.error(zh ? "新增失敗" : "Failed to add")
            }
        } catch {
            setLocalTickets(prevTickets)
            toast.error(zh ? "新增失敗" : "Failed to add")
        } finally {
            setSavingTickets(false)
            ticketLockRef.current = false
        }
    }

    const handleRemoveTicket = async (idx: number) => {
        if (savingTickets || ticketLockRef.current) return
        ticketLockRef.current = true
        haptic.tap()
        const prevTickets = localTickets
        const updated = localTickets.filter((_, i) => i !== idx)
        setLocalTickets(updated)
        setSavingTickets(true)
        try {
            if (await onUpdate("tickets", updated)) {
                toast.success(zh ? "已移除" : "Removed")
            } else {
                setLocalTickets(prevTickets)
                toast.error(zh ? "移除失敗" : "Failed to remove")
            }
        } catch {
            setLocalTickets(prevTickets)
            toast.error(zh ? "移除失敗" : "Failed to remove")
        } finally {
            setSavingTickets(false)
            ticketLockRef.current = false
        }
    }

    const handleTogglePrivacyTicket = async (idx: number) => {
        if (processingTickets.has(idx) || savingTickets || ticketLockRef.current) return
        ticketLockRef.current = true
        haptic.tap()
        setProcessingTickets(prev => new Set(prev).add(idx))
        const prevTickets = localTickets
        const ownerId = resolveOwnerId(userId)
        const updated: TicketItem[] = localTickets.map((t, i) =>
            i === idx ? {
                ...t,
                is_private: !t.is_private,
                private_owner_id: !t.is_private ? ownerId : undefined
            } : t
        )
        setLocalTickets(updated)
        setSavingTickets(true)
        try {
            if (await onUpdate("tickets", updated)) {
                toast.success(updated[idx].is_private ? (zh ? "已設為私人" : "Set to private") : (zh ? "已設為公開" : "Set to public"))
            } else {
                setLocalTickets(prevTickets)
            }
        } catch {
            setLocalTickets(prevTickets)
        } finally {
            setSavingTickets(false)
            ticketLockRef.current = false
            setProcessingTickets(prev => {
                const next = new Set(prev)
                next.delete(idx)
                return next
            })
        }
    }

    const handleStartEditTickets = () => {
        setEditTicketsData(
            localTickets.map((ticket) => {
                const parsed = parseCostAmount(ticket.price, ticket.currency, effectiveCurrency)
                return {
                    ...ticket,
                    price: parsed.normalizedAmount ?? String(ticket.price ?? ""),
                    currency: parsed.currency,
                }
            })
        )
        setEditingTickets(true)
        handleCancelAddTicket()
        haptic.tap()
    }

    const handleSaveTickets = async () => {
        if (savingTickets || ticketLockRef.current) return
        if (editTicketsData.some((ticket) => !(ticket.name ?? "").trim() || !String(ticket.price ?? "").trim())) {
            toast.error(zh ? "請輸入票券名稱和價格" : "Please enter ticket name and price")
            return
        }
        const normalizedTickets: TicketItem[] = []
        for (const ticket of editTicketsData) {
            const parsed = parseCostAmount(ticket.price, ticket.currency, effectiveCurrency)
            if (parsed.isNegative) {
                toast.error(zh ? "價格不可為負數" : "Price cannot be negative")
                return
            }
            normalizedTickets.push({
                ...ticket,
                name: (ticket.name ?? "").trim(),
                price: parsed.normalizedAmount ?? String(ticket.price).trim(),
                currency: parsed.currency,
                ...(ticket.note !== undefined ? { note: ticket.note.trim() } : {}),
            })
        }
        ticketLockRef.current = true
        haptic.tap()
        setSavingTickets(true)
        try {
            if (await onUpdate("tickets", normalizedTickets)) {
                setLocalTickets(normalizedTickets)
                setEditingTickets(false)
                setEditTicketsData([])
                toast.success(zh ? "已儲存修改" : "Changes saved")
            } else {
                toast.error(zh ? "儲存失敗" : "Save failed")
            }
        } catch {
            toast.error(zh ? "儲存失敗" : "Save failed")
        } finally {
            setSavingTickets(false)
            ticketLockRef.current = false
        }
    }

    const handleUpdateEditTicket = (idx: number, field: keyof TicketItem, value: string) => {
        setEditTicketsData(prev => prev.map((ticket, i) =>
            i === idx ? { ...ticket, [field]: value } : ticket
        ))
    }

    const handleToggleEditTicketPrivacy = (idx: number) => {
        const ownerId = resolveOwnerId(userId)
        setEditTicketsData(prev => prev.map((ticket, i) => {
            if (i !== idx) return ticket
            const nextPrivate = !ticket.is_private
            return {
                ...ticket,
                is_private: nextPrivate,
                private_owner_id: nextPrivate ? (ticket.private_owner_id || ownerId) : undefined,
            }
        }))
    }

    const showNotes = !displaySection || displaySection === "all" || displaySection === "notes"
    const showCosts = !displaySection || displaySection === "all" || displaySection === "costs"
    const showTickets = !displaySection || displaySection === "all" || displaySection === "tickets"

    // Shared card & button design tokens (Wabi-Sabi Tactile Sheet Cards)
    const unifiedCardClass =
        "bg-white/95 dark:bg-[#182320]/90 border border-tabiji-forest/10 dark:border-white/10 rounded-2xl p-4 shadow-[0_2px_12px_rgba(11,48,38,0.05)] dark:shadow-[0_2px_14px_rgba(0,0,0,0.3)]"
    const secondaryPillBtnClass =
        "inline-flex items-center justify-center h-8 px-2.5 rounded-full text-xs font-medium whitespace-nowrap shrink-0 bg-tabiji-mist/70 hover:bg-tabiji-mist text-tabiji-charcoal dark:bg-white/8 dark:hover:bg-white/14 dark:text-tabiji-paper transition-colors touch-manipulation disabled:opacity-50"
    const primaryActionBtnClass =
        "inline-flex items-center justify-center h-8 px-3 rounded-full text-xs font-semibold whitespace-nowrap shrink-0 bg-tabiji-forest hover:bg-tabiji-forest/90 text-tabiji-paper dark:bg-emerald-600 dark:hover:bg-emerald-500 dark:text-white transition-colors touch-manipulation disabled:opacity-50"

    return (
        <div className={cn(className || "mx-5 mb-6 space-y-4")}>
            {/* ⚠️ Notes Section */}
            {showNotes && (
                <div className={unifiedCardClass} onKeyDown={handleNotesCardKeyDown}>
                    <div className="flex flex-wrap items-center justify-between gap-2 mb-3.5">
                        <div className="flex items-center gap-2.5 min-w-[min(100%,9rem)] flex-1">
                            <div className="w-8 h-8 rounded-xl bg-amber-500/12 dark:bg-amber-400/15 text-amber-700 dark:text-amber-300 flex items-center justify-center shrink-0">
                                <AlertCircle className="w-4 h-4" />
                            </div>
                            <h4 className="text-sm font-bold text-tabiji-charcoal dark:text-tabiji-paper leading-snug wrap-break-word">
                                {zh ? "每日重點提醒" : "Daily Reminders"}
                            </h4>
                        </div>
                        {!readOnly && !editingNotes && !addingNote && (
                            <div className="flex flex-wrap items-center justify-end gap-1.5 shrink-0 ml-auto">
                                {localNotes.length > 0 && (
                                    <button
                                        type="button"
                                        disabled={savingNotes}
                                        className={secondaryPillBtnClass}
                                        onClick={handleStartEditNotes}
                                    >
                                        <Pencil className="w-3 h-3 mr-1" />
                                        {zh ? "編輯" : "Edit"}
                                    </button>
                                )}
                                <button
                                    type="button"
                                    disabled={savingNotes}
                                    className={secondaryPillBtnClass}
                                    onClick={() => setAddingNote(true)}
                                >
                                    <Plus className="w-3.5 h-3.5 mr-0.5" />
                                    {zh ? "新增" : "Add"}
                                </button>
                            </div>
                        )}
                        {editingNotes && (
                            <div className="flex flex-wrap items-center justify-end gap-1.5 shrink-0 ml-auto">
                                <button
                                    type="button"
                                    className={secondaryPillBtnClass}
                                    onClick={handleCancelEditNotes}
                                >
                                    {zh ? "取消" : "Cancel"}
                                </button>
                                <button
                                    type="button"
                                    className={primaryActionBtnClass}
                                    onClick={handleSaveNotes}
                                    disabled={saving}
                                >
                                    {saving ? (
                                        <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                                    ) : (
                                        <Check className="w-3.5 h-3.5 mr-1" />
                                    )}
                                    {zh ? "儲存" : "Save"}
                                </button>
                            </div>
                        )}
                    </div>

                    <div className="space-y-2.5">
                        {/* 編輯模式：顯示所有條目的編輯表單 */}
                        {editingNotes &&
                            editNotesData.map((note, idx) => (
                                <div
                                    key={idx}
                                    className="bg-tabiji-paper/65 dark:bg-white/[0.04] rounded-xl p-3 border border-tabiji-forest/10 dark:border-white/10 space-y-2.5"
                                >
                                    <div className="flex gap-2 items-center">
                                        <IconPicker
                                            value={note.icon || "⚠️"}
                                            onChange={(val) => handleUpdateEditNote(idx, "icon", val)}
                                            zh={zh}
                                        />
                                        <Input
                                            placeholder={zh ? "提醒標題" : "Reminder title"}
                                            className="flex-1 h-10 text-sm bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                            value={note.title}
                                            onChange={(e) => handleUpdateEditNote(idx, "title", e.target.value)}
                                            onKeyDown={(e) => {
                                                if (e.nativeEvent.isComposing) return
                                                if (e.key === "Enter") {
                                                    e.preventDefault()
                                                    handleSaveNotes()
                                                }
                                            }}
                                        />
                                    </div>
                                    <Input
                                        placeholder={zh ? "補充說明內容..." : "Additional details..."}
                                        className="h-9 text-sm bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                        value={note.content}
                                        onChange={(e) => handleUpdateEditNote(idx, "content", e.target.value)}
                                        onKeyDown={(e) => {
                                            if (e.nativeEvent.isComposing) return
                                            if (e.key === "Enter") {
                                                e.preventDefault()
                                                handleSaveNotes()
                                            }
                                        }}
                                    />
                                </div>
                            ))}

                        {/* 正常模式：顯示條目 */}
                        {!editingNotes &&
                            localNotes.map((note, idx) => (
                                <div
                                    key={idx}
                                    className="flex gap-3 items-start p-3 rounded-xl bg-tabiji-paper/55 dark:bg-white/[0.03] border border-tabiji-forest/8 dark:border-white/8 group"
                                >
                                    <div className="w-8 h-8 rounded-lg bg-amber-500/12 dark:bg-amber-400/15 flex items-center justify-center text-base leading-none shrink-0 mt-0.5">
                                        {note.icon || "⚠️"}
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-sm font-bold text-tabiji-charcoal dark:text-tabiji-paper wrap-break-word [overflow-wrap:anywhere]">
                                            {note.title}
                                        </div>
                                        {note.content && (
                                            <div className="text-xs text-slate-600 dark:text-slate-300 mt-0.5 whitespace-pre-line wrap-break-word [overflow-wrap:anywhere]">
                                                {note.content}
                                            </div>
                                        )}
                                    </div>
                                    {!readOnly && (
                                        <button
                                            type="button"
                                            onClick={() => handleRemoveNote(idx)}
                                            aria-label={zh ? `移除提醒 ${note.title}` : `Remove reminder ${note.title}`}
                                            className="p-1.5 rounded-lg transition-colors touch-manipulation min-w-8 min-h-8 flex items-center justify-center shrink-0 text-slate-400 hover:text-red-500 hover:bg-red-500/10 active:text-red-600"
                                        >
                                            <X className="w-4 h-4" />
                                        </button>
                                    )}
                                </div>
                            ))}

                        {/* 現代空狀態卡片 */}
                        {localNotes.length === 0 && !addingNote && !editingNotes && (
                            <div className="py-6 px-4 text-center rounded-xl bg-tabiji-paper/45 dark:bg-white/[0.02] border border-dashed border-tabiji-forest/12 dark:border-white/10">
                                <div className="w-11 h-11 rounded-2xl bg-amber-500/12 dark:bg-amber-400/15 text-amber-700 dark:text-amber-300 flex items-center justify-center mx-auto mb-2.5">
                                    <AlertCircle className="w-5 h-5" />
                                </div>
                                <p className="text-sm font-semibold text-tabiji-charcoal dark:text-tabiji-paper">
                                    {zh ? "尚無每日重點提醒" : "No daily reminders yet"}
                                </p>
                                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 mb-3.5">
                                    {zh
                                        ? "記錄當日集合時間、穿著建議或預約注意事項"
                                        : "Jot down meeting times, dress codes, or booking notes"}
                                </p>
                                {!readOnly && (
                                    <button
                                        type="button"
                                        onClick={() => setAddingNote(true)}
                                        className={primaryActionBtnClass}
                                    >
                                        <Plus className="w-3.5 h-3.5 mr-1" />
                                        {zh ? "新增第一筆提醒" : "Add First Reminder"}
                                    </button>
                                )}
                            </div>
                        )}

                        {/* 新增表單 (Linear 分層內嵌表單) */}
                        {addingNote && (
                            <div className="bg-tabiji-paper/65 dark:bg-white/[0.04] rounded-xl p-3.5 border border-tabiji-forest/12 dark:border-white/12 space-y-2.5 animate-in fade-in zoom-in-95 duration-200">
                                <div className="flex gap-2 items-center">
                                    <IconPicker
                                        value={newNote.icon || "⚠️"}
                                        onChange={(val) => setNewNote({ ...newNote, icon: val })}
                                        zh={zh}
                                    />
                                    <Input
                                        placeholder={zh ? "標題（例如：預約餐廳、攜帶折傘）" : "Title (e.g. Booking note, Bring umbrella)"}
                                        className="flex-1 h-10 text-sm bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                        value={newNote.title}
                                        onChange={(e) => setNewNote({ ...newNote, title: e.target.value })}
                                        onKeyDown={(e) => {
                                            if (e.nativeEvent.isComposing) return
                                            if (e.key === "Enter") {
                                                e.preventDefault()
                                                handleAddNote()
                                            }
                                            if (e.key === "Escape") {
                                                e.preventDefault()
                                                e.stopPropagation()
                                                handleCancelAddNote()
                                            }
                                        }}
                                    />
                                </div>
                                <Input
                                    placeholder={zh ? "補充說明內容（選填）..." : "Details or notes (optional)..."}
                                    className="h-9 text-sm bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                    value={newNote.content}
                                    onChange={(e) => setNewNote({ ...newNote, content: e.target.value })}
                                    onKeyDown={(e) => {
                                        if (e.nativeEvent.isComposing) return
                                        if (e.key === "Enter") {
                                            e.preventDefault()
                                            handleAddNote()
                                        }
                                        if (e.key === "Escape") {
                                            e.preventDefault()
                                            e.stopPropagation()
                                            handleCancelAddNote()
                                        }
                                    }}
                                />
                                <div className="flex justify-end gap-2 pt-1">
                                    <button
                                        type="button"
                                        className={secondaryPillBtnClass}
                                        onClick={handleCancelAddNote}
                                    >
                                        {zh ? "取消" : "Cancel"}
                                    </button>
                                    <button
                                        type="button"
                                        onClick={handleAddNote}
                                        disabled={saving}
                                        className={primaryActionBtnClass}
                                    >
                                        <Check className="w-3.5 h-3.5 mr-1" />
                                        {zh ? "新增" : "Add"}
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {(showCosts || showTickets) && (
                <div className={cn("grid gap-4", showCosts && showTickets ? "grid-cols-1 md:grid-cols-2" : "grid-cols-1")}>
                    {/* 💰 Costs Section */}
                    {showCosts && (
                        <div className={cn(unifiedCardClass, "flex flex-col h-full")} onKeyDown={handleCostsCardKeyDown}>
                            <div className="flex flex-wrap items-center justify-between gap-2 mb-3.5">
                                <div className="flex items-center gap-2.5 min-w-[min(100%,9rem)] flex-1">
                                    <div className="w-8 h-8 rounded-xl bg-tabiji-forest/10 dark:bg-emerald-400/15 text-tabiji-forest dark:text-emerald-300 flex items-center justify-center shrink-0">
                                        <Wallet className="w-4 h-4" />
                                    </div>
                                    <h4 className="text-sm font-bold text-tabiji-charcoal dark:text-tabiji-paper leading-snug wrap-break-word">
                                        {zh ? "預估花費" : "Estimated Costs"}
                                    </h4>
                                </div>
                                {!readOnly && !editingCosts && !addingCost && (
                                    <div className="flex flex-wrap items-center justify-end gap-1.5 shrink-0 ml-auto">
                                        {localCosts.length > 0 && (
                                            <button
                                                type="button"
                                                disabled={savingCosts}
                                                className={secondaryPillBtnClass}
                                                onClick={handleStartEditCosts}
                                            >
                                                <Pencil className="w-3 h-3 mr-1" />
                                                {zh ? "編輯" : "Edit"}
                                            </button>
                                        )}
                                        <button
                                            type="button"
                                            disabled={savingCosts}
                                            className={secondaryPillBtnClass}
                                            onClick={() => setAddingCost(true)}
                                        >
                                            <Plus className="w-3.5 h-3.5 mr-0.5" />
                                            {zh ? "新增" : "Add"}
                                        </button>
                                    </div>
                                )}
                                {editingCosts && (
                                    <div className="flex flex-wrap items-center justify-end gap-1.5 shrink-0 ml-auto">
                                        <button
                                            type="button"
                                            className={secondaryPillBtnClass}
                                            onClick={handleCancelEditCosts}
                                        >
                                            {zh ? "取消" : "Cancel"}
                                        </button>
                                        <button
                                            type="button"
                                            className={primaryActionBtnClass}
                                            onClick={handleSaveCosts}
                                            disabled={saving}
                                        >
                                            {saving ? (
                                                <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                                            ) : (
                                                <Check className="w-3.5 h-3.5 mr-1" />
                                            )}
                                            {zh ? "儲存" : "Save"}
                                        </button>
                                    </div>
                                )}
                            </div>

                            <div className="flex-1 space-y-2.5">
                                {/* 編輯模式：顯示所有花費的現代分層編輯表單 */}
                                {editingCosts &&
                                    editCostsData.map((cost, idx) => (
                                        <div
                                            key={idx}
                                            className="bg-tabiji-paper/65 dark:bg-white/[0.04] rounded-xl p-3 border border-tabiji-forest/10 dark:border-white/10 space-y-2.5"
                                        >
                                            <Input
                                                placeholder={zh ? "項目名稱" : "Item name"}
                                                className="h-10 text-sm bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                                value={cost.item}
                                                onChange={(e) => handleUpdateEditCost(idx, "item", e.target.value)}
                                                onKeyDown={(e) => {
                                                    if (e.nativeEvent.isComposing) return
                                                    if (e.key === "Enter") {
                                                        e.preventDefault()
                                                        handleSaveCosts()
                                                    }
                                                }}
                                            />
                                            <CurrencyPillSelector
                                                value={cost.currency || effectiveCurrency}
                                                defaultCurrency={effectiveCurrency}
                                                extraCurrencies={costExtraCurrencies}
                                                onChange={(curr) => handleUpdateEditCost(idx, "currency", curr)}
                                                zh={zh}
                                            />
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs font-bold px-2.5 h-10 rounded-xl bg-tabiji-mist/70 dark:bg-white/8 text-tabiji-charcoal dark:text-tabiji-paper inline-flex items-center justify-center shrink-0">
                                                    {cost.currency || effectiveCurrency}
                                                </span>
                                                <Input
                                                    placeholder={zh ? "輸入金額" : "Enter amount"}
                                                    className="flex-1 h-10 text-sm font-mono tabular-nums bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                                    type="text"
                                                    inputMode="decimal"
                                                    value={cost.amount}
                                                    onChange={(e) => handleUpdateEditCost(idx, "amount", e.target.value)}
                                                    onKeyDown={(e) => {
                                                        if (e.nativeEvent.isComposing) return
                                                        if (e.key === "Enter") {
                                                            e.preventDefault()
                                                            handleSaveCosts()
                                                        }
                                                    }}
                                                />
                                            </div>
                                            <Input
                                                placeholder={zh ? "備註（選填）" : "Note (optional)"}
                                                className="h-9 text-xs bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                                value={cost.note || ""}
                                                onChange={(e) => handleUpdateEditCost(idx, "note", e.target.value)}
                                                onKeyDown={(e) => {
                                                    if (e.nativeEvent.isComposing) return
                                                    if (e.key === "Enter") {
                                                        e.preventDefault()
                                                        handleSaveCosts()
                                                    }
                                                }}
                                            />
                                            <div className="flex items-center justify-between pt-1.5 border-t border-tabiji-forest/10 dark:border-white/10">
                                                <PrivacyTogglePill
                                                    isPrivate={Boolean(cost.is_private)}
                                                    onToggle={() => handleToggleEditCostPrivacy(idx)}
                                                    zh={zh}
                                                />
                                            </div>
                                        </div>
                                    ))}

                                {/* 正常模式：顯示花費列表（與票券統一備註置底排版） */}
                                {!editingCosts &&
                                    localCosts.map((cost, idx) => (
                                        <div
                                            key={idx}
                                            className={cn(
                                                "p-3 rounded-xl bg-tabiji-paper/55 dark:bg-white/[0.03] border border-tabiji-forest/8 dark:border-white/8 text-sm group",
                                                cost.is_private && "opacity-75 border-dashed border-amber-500/30"
                                            )}
                                        >
                                            <div className="flex flex-wrap justify-between items-center gap-2 min-w-0">
                                                <div className="font-semibold text-tabiji-charcoal dark:text-tabiji-paper min-w-[min(100%,6.5rem)] max-w-full flex-1 flex items-center gap-1.5">
                                                    {cost.is_private && (
                                                        <EyeOff className="w-3.5 h-3.5 shrink-0 text-amber-500" />
                                                    )}
                                                    <span className="min-w-0 flex-1 wrap-break-word [overflow-wrap:anywhere]">{cost.item}</span>
                                                </div>
                                                <div className="flex items-center gap-1.5 ml-auto max-w-full min-w-0">
                                                    <span className="text-right font-mono tabular-nums font-bold text-tabiji-forest dark:text-emerald-300 text-xs sm:text-sm min-w-0 wrap-break-word [overflow-wrap:anywhere]">
                                                        {formatCurrency(cost.amount, cost.currency)}
                                                    </span>
                                                    {!readOnly && (
                                                        <div className="flex items-center gap-0.5">
                                                            <button
                                                                type="button"
                                                                onClick={() => handleTogglePrivacyCost(idx)}
                                                                disabled={processingCosts.has(idx)}
                                                                aria-label={
                                                                    cost.is_private
                                                                        ? zh
                                                                            ? "設為公開"
                                                                            : "Make public"
                                                                        : zh
                                                                          ? "設為私人"
                                                                          : "Make private"
                                                                }
                                                                title={
                                                                    cost.is_private
                                                                        ? zh
                                                                            ? "設為公開"
                                                                            : "Make public"
                                                                        : zh
                                                                          ? "設為私人"
                                                                          : "Make private"
                                                                }
                                                                className={cn(
                                                                    "p-1.5 rounded-lg transition-colors touch-manipulation min-w-8 min-h-8 flex items-center justify-center",
                                                                    processingCosts.has(idx) && "opacity-50 cursor-not-allowed",
                                                                    cost.is_private
                                                                        ? "text-amber-500 hover:text-amber-600 hover:bg-amber-500/10"
                                                                        : "text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-tabiji-mist/50 dark:hover:bg-white/10"
                                                                )}
                                                            >
                                                                {processingCosts.has(idx) ? (
                                                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                                                ) : cost.is_private ? (
                                                                    <EyeOff className="w-3.5 h-3.5" />
                                                                ) : (
                                                                    <Eye className="w-3.5 h-3.5" />
                                                                )}
                                                            </button>
                                                            <button
                                                                type="button"
                                                                onClick={() => handleRemoveCost(idx)}
                                                                disabled={processingCosts.has(idx)}
                                                                aria-label={zh ? `移除花費 ${cost.item}` : `Remove cost ${cost.item}`}
                                                                className={cn(
                                                                    "p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-500/10 active:text-red-600 transition-colors touch-manipulation min-w-8 min-h-8 flex items-center justify-center",
                                                                    processingCosts.has(idx) && "opacity-50 cursor-not-allowed"
                                                                )}
                                                            >
                                                                {processingCosts.has(idx) ? (
                                                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                                                ) : (
                                                                    <X className="w-3.5 h-3.5" />
                                                                )}
                                                            </button>
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                            {cost.note && (
                                                <div className="text-xs text-slate-500 dark:text-slate-400 mt-1 wrap-break-word [overflow-wrap:anywhere]">
                                                    {cost.note}
                                                </div>
                                            )}
                                        </div>
                                    ))}

                                {/* Auto Sum Footer */}
                                {localCosts.length > 0 && Object.keys(costsTotal).length > 0 && (
                                    <div className="mt-3 pt-2.5 border-t border-tabiji-forest/10 dark:border-white/10 flex justify-between items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                                        <span className="flex items-center gap-1 font-medium shrink-0">
                                            <Calculator className="w-3.5 h-3.5" />
                                            {zh ? "小計" : "Subtotal"}
                                        </span>
                                        <div className="flex flex-wrap justify-end gap-2">
                                            {Object.entries(costsTotal).map(([curr, total]) => (
                                                <span
                                                    key={curr}
                                                    className="font-mono tabular-nums font-bold text-tabiji-charcoal dark:text-tabiji-paper bg-tabiji-mist/60 dark:bg-white/8 px-2 py-0.5 rounded-md"
                                                >
                                                    {curr} {total.toLocaleString()}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* 現代空狀態卡片 */}
                                {localCosts.length === 0 && !addingCost && !editingCosts && (
                                    <div className="py-6 px-4 text-center rounded-xl bg-tabiji-paper/45 dark:bg-white/[0.02] border border-dashed border-tabiji-forest/12 dark:border-white/10">
                                        <div className="w-11 h-11 rounded-2xl bg-tabiji-forest/10 dark:bg-emerald-400/15 text-tabiji-forest dark:text-emerald-300 flex items-center justify-center mx-auto mb-2.5">
                                            <Wallet className="w-5 h-5" />
                                        </div>
                                        <p className="text-sm font-semibold text-tabiji-charcoal dark:text-tabiji-paper">
                                            {zh ? "尚無預估花費記錄" : "No estimated costs yet"}
                                        </p>
                                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 mb-3.5">
                                            {zh
                                                ? "預先記下餐飲、門票與購物預算，自動換算台幣小計"
                                                : "Track dining, admission, and shopping budgets with auto subtotal"}
                                        </p>
                                        {!readOnly && (
                                            <button
                                                type="button"
                                                onClick={() => setAddingCost(true)}
                                                className={primaryActionBtnClass}
                                            >
                                                <Plus className="w-3.5 h-3.5 mr-1" />
                                                {zh ? "新增第一筆花費" : "Add First Cost"}
                                            </button>
                                        )}
                                    </div>
                                )}

                                {/* 新增花費：Linear 分層內嵌表單 */}
                                {addingCost && (
                                    <div className="bg-tabiji-paper/65 dark:bg-white/[0.04] rounded-xl p-3.5 border border-tabiji-forest/12 dark:border-white/12 space-y-2.5 animate-in fade-in zoom-in-95 duration-200">
                                        <Input
                                            placeholder={zh ? "項目名稱（例如：敘敘苑燒肉、伴手禮）" : "Item name (e.g. Ramen dinner, Souvenirs)"}
                                            className="h-10 text-sm bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                            value={newCost.item}
                                            onChange={(e) => setNewCost({ ...newCost, item: e.target.value })}
                                            onKeyDown={(e) => {
                                                if (e.nativeEvent.isComposing) return
                                                if (e.key === "Enter") {
                                                    e.preventDefault()
                                                    handleAddCost()
                                                }
                                                if (e.key === "Escape") {
                                                    e.preventDefault()
                                                    e.stopPropagation()
                                                    handleCancelAddCost()
                                                }
                                            }}
                                        />
                                        <CurrencyPillSelector
                                            value={newCost.currency || effectiveCurrency}
                                            defaultCurrency={effectiveCurrency}
                                            extraCurrencies={costExtraCurrencies}
                                            onChange={(curr) => setNewCost({ ...newCost, currency: curr })}
                                            zh={zh}
                                        />
                                        <div className="flex items-center gap-2">
                                            <span className="text-xs font-bold px-2.5 h-10 rounded-xl bg-tabiji-mist/70 dark:bg-white/8 text-tabiji-charcoal dark:text-tabiji-paper inline-flex items-center justify-center shrink-0">
                                                {newCost.currency || effectiveCurrency}
                                            </span>
                                            <Input
                                                placeholder={zh ? "輸入金額" : "Enter amount"}
                                                className="flex-1 h-10 text-sm font-mono tabular-nums bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                                type="text"
                                                inputMode="decimal"
                                                value={newCost.amount}
                                                onChange={(e) => setNewCost({ ...newCost, amount: e.target.value })}
                                                onKeyDown={(e) => {
                                                    if (e.nativeEvent.isComposing) return
                                                    if (e.key === "Enter") {
                                                        e.preventDefault()
                                                        handleAddCost()
                                                    }
                                                    if (e.key === "Escape") {
                                                        e.preventDefault()
                                                        e.stopPropagation()
                                                        handleCancelAddCost()
                                                    }
                                                }}
                                            />
                                        </div>
                                        <Input
                                            placeholder={zh ? "備註，例如付款方式、分攤說明（選填）" : "Note, e.g. payment method (optional)"}
                                            className="h-9 text-xs bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                            value={newCost.note}
                                            onChange={(e) => setNewCost({ ...newCost, note: e.target.value })}
                                            onKeyDown={(e) => {
                                                if (e.nativeEvent.isComposing) return
                                                if (e.key === "Enter") {
                                                    e.preventDefault()
                                                    handleAddCost()
                                                }
                                                if (e.key === "Escape") {
                                                    e.preventDefault()
                                                    e.stopPropagation()
                                                    handleCancelAddCost()
                                                }
                                            }}
                                        />
                                        <div className="flex flex-wrap items-center justify-between gap-2 pt-1.5 border-t border-tabiji-forest/10 dark:border-white/10">
                                            <PrivacyTogglePill
                                                isPrivate={Boolean(newCost.is_private)}
                                                onToggle={() =>
                                                    setNewCost((prev) => ({ ...prev, is_private: !prev.is_private }))
                                                }
                                                zh={zh}
                                            />
                                            <div className="flex items-center gap-1.5 ml-auto">
                                                <button
                                                    type="button"
                                                    className={secondaryPillBtnClass}
                                                    onClick={handleCancelAddCost}
                                                >
                                                    {zh ? "取消" : "Cancel"}
                                                </button>
                                                <button
                                                    type="button"
                                                    className={primaryActionBtnClass}
                                                    onClick={handleAddCost}
                                                    disabled={saving}
                                                >
                                                    <Check className="w-3.5 h-3.5 mr-1" />
                                                    {zh ? "新增" : "Add"}
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* 🎫 Tickets Section */}
                    {showTickets && (
                        <div className={cn(unifiedCardClass, "flex flex-col h-full")} onKeyDown={handleTicketsCardKeyDown}>
                            <div className="flex flex-wrap items-center justify-between gap-2 mb-3.5">
                                <div className="flex items-center gap-2.5 min-w-[min(100%,9rem)] flex-1">
                                    <div className="w-8 h-8 rounded-xl bg-sky-500/12 dark:bg-sky-400/15 text-sky-700 dark:text-sky-300 flex items-center justify-center shrink-0">
                                        <Ticket className="w-4 h-4" />
                                    </div>
                                    <h4 className="text-sm font-bold text-tabiji-charcoal dark:text-tabiji-paper leading-snug wrap-break-word">
                                        {zh ? "交通票券" : "Transport Tickets"}
                                    </h4>
                                </div>
                                {!readOnly && !editingTickets && !addingTicket && (
                                    <div className="flex flex-wrap items-center justify-end gap-1.5 shrink-0 ml-auto">
                                        {localTickets.length > 0 && (
                                            <button
                                                type="button"
                                                disabled={savingTickets}
                                                className={secondaryPillBtnClass}
                                                onClick={handleStartEditTickets}
                                            >
                                                <Pencil className="w-3 h-3 mr-1" />
                                                {zh ? "編輯" : "Edit"}
                                            </button>
                                        )}
                                        <button
                                            type="button"
                                            disabled={savingTickets}
                                            className={secondaryPillBtnClass}
                                            onClick={() => setAddingTicket(true)}
                                        >
                                            <Plus className="w-3.5 h-3.5 mr-0.5" />
                                            {zh ? "新增" : "Add"}
                                        </button>
                                    </div>
                                )}
                                {editingTickets && (
                                    <div className="flex flex-wrap items-center justify-end gap-1.5 shrink-0 ml-auto">
                                        <button
                                            type="button"
                                            className={secondaryPillBtnClass}
                                            onClick={handleCancelEditTickets}
                                        >
                                            {zh ? "取消" : "Cancel"}
                                        </button>
                                        <button
                                            type="button"
                                            className={primaryActionBtnClass}
                                            onClick={handleSaveTickets}
                                            disabled={saving}
                                        >
                                            {saving ? (
                                                <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                                            ) : (
                                                <Check className="w-3.5 h-3.5 mr-1" />
                                            )}
                                            {zh ? "儲存" : "Save"}
                                        </button>
                                    </div>
                                )}
                            </div>

                            <div className="flex-1 space-y-2.5">
                                {/* 編輯模式：顯示所有票券的現代分層編輯表單 */}
                                {editingTickets &&
                                    editTicketsData.map((ticket, idx) => (
                                        <div
                                            key={idx}
                                            className="bg-tabiji-paper/65 dark:bg-white/[0.04] rounded-xl p-3 border border-tabiji-forest/10 dark:border-white/10 space-y-2.5"
                                        >
                                            <Input
                                                placeholder={zh ? "票券名稱" : "Ticket name"}
                                                className="h-10 text-sm bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                                value={ticket.name}
                                                onChange={(e) => handleUpdateEditTicket(idx, "name", e.target.value)}
                                                onKeyDown={(e) => {
                                                    if (e.nativeEvent.isComposing) return
                                                    if (e.key === "Enter") {
                                                        e.preventDefault()
                                                        handleSaveTickets()
                                                    }
                                                }}
                                            />
                                            <CurrencyPillSelector
                                                value={ticket.currency || effectiveCurrency}
                                                defaultCurrency={effectiveCurrency}
                                                extraCurrencies={ticketExtraCurrencies}
                                                onChange={(curr) => handleUpdateEditTicket(idx, "currency", curr)}
                                                zh={zh}
                                            />
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs font-bold px-2.5 h-10 rounded-xl bg-tabiji-mist/70 dark:bg-white/8 text-tabiji-charcoal dark:text-tabiji-paper inline-flex items-center justify-center shrink-0">
                                                    {ticket.currency || effectiveCurrency}
                                                </span>
                                                <Input
                                                    placeholder={zh ? "輸入票價" : "Enter price"}
                                                    className="flex-1 h-10 text-sm font-mono tabular-nums bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                                    type="text"
                                                    inputMode="decimal"
                                                    value={ticket.price}
                                                    onChange={(e) => handleUpdateEditTicket(idx, "price", e.target.value)}
                                                    onKeyDown={(e) => {
                                                        if (e.nativeEvent.isComposing) return
                                                        if (e.key === "Enter") {
                                                            e.preventDefault()
                                                            handleSaveTickets()
                                                        }
                                                    }}
                                                />
                                            </div>
                                            <Input
                                                placeholder={zh ? "備註（選填）" : "Note (optional)"}
                                                className="h-9 text-xs bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                                value={ticket.note || ""}
                                                onChange={(e) => handleUpdateEditTicket(idx, "note", e.target.value)}
                                                onKeyDown={(e) => {
                                                    if (e.nativeEvent.isComposing) return
                                                    if (e.key === "Enter") {
                                                        e.preventDefault()
                                                        handleSaveTickets()
                                                    }
                                                }}
                                            />
                                            <div className="flex items-center justify-between pt-1.5 border-t border-tabiji-forest/10 dark:border-white/10">
                                                <PrivacyTogglePill
                                                    isPrivate={Boolean(ticket.is_private)}
                                                    onToggle={() => handleToggleEditTicketPrivacy(idx)}
                                                    zh={zh}
                                                />
                                            </div>
                                        </div>
                                    ))}

                                {/* 正常模式：顯示票券列表 */}
                                {!editingTickets &&
                                    localTickets.map((ticket, idx) => (
                                        <div
                                            key={idx}
                                            className={cn(
                                                "p-3 rounded-xl bg-tabiji-paper/55 dark:bg-white/[0.03] border border-tabiji-forest/8 dark:border-white/8 text-sm group",
                                                ticket.is_private && "opacity-75 border-dashed border-amber-500/30"
                                            )}
                                        >
                                            <div className="flex flex-wrap justify-between items-center gap-2 min-w-0">
                                                <div className="font-semibold text-tabiji-charcoal dark:text-tabiji-paper min-w-[min(100%,6.5rem)] max-w-full flex-1 flex items-center gap-1.5">
                                                    {ticket.is_private && (
                                                        <EyeOff className="w-3.5 h-3.5 shrink-0 text-amber-500" />
                                                    )}
                                                    <span className="min-w-0 flex-1 wrap-break-word [overflow-wrap:anywhere]">{ticket.name}</span>
                                                </div>
                                                <div className="flex items-center gap-1.5 ml-auto max-w-full min-w-0">
                                                    <span className="font-mono tabular-nums font-bold text-sky-700 dark:text-sky-300 text-xs sm:text-sm min-w-0 wrap-break-word [overflow-wrap:anywhere]">
                                                        {formatCurrency(ticket.price, ticket.currency)}
                                                    </span>
                                                    {!readOnly && (
                                                        <div className="flex items-center gap-0.5">
                                                            <button
                                                                type="button"
                                                                onClick={() => handleTogglePrivacyTicket(idx)}
                                                                disabled={processingTickets.has(idx)}
                                                                aria-label={
                                                                    ticket.is_private
                                                                        ? zh
                                                                            ? "設為公開"
                                                                            : "Make public"
                                                                        : zh
                                                                          ? "設為私人"
                                                                          : "Make private"
                                                                }
                                                                title={
                                                                    ticket.is_private
                                                                        ? zh
                                                                            ? "設為公開"
                                                                            : "Make public"
                                                                        : zh
                                                                          ? "設為私人"
                                                                          : "Make private"
                                                                }
                                                                className={cn(
                                                                    "p-1.5 rounded-lg transition-colors touch-manipulation min-w-8 min-h-8 flex items-center justify-center",
                                                                    processingTickets.has(idx) && "opacity-50 cursor-not-allowed",
                                                                    ticket.is_private
                                                                        ? "text-amber-500 hover:text-amber-600 hover:bg-amber-500/10"
                                                                        : "text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-tabiji-mist/50 dark:hover:bg-white/10"
                                                                )}
                                                            >
                                                                {processingTickets.has(idx) ? (
                                                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                                                ) : ticket.is_private ? (
                                                                    <EyeOff className="w-3.5 h-3.5" />
                                                                ) : (
                                                                    <Eye className="w-3.5 h-3.5" />
                                                                )}
                                                            </button>
                                                            <button
                                                                type="button"
                                                                onClick={() => handleRemoveTicket(idx)}
                                                                disabled={processingTickets.has(idx)}
                                                                aria-label={zh ? `移除票券 ${ticket.name}` : `Remove ticket ${ticket.name}`}
                                                                className={cn(
                                                                    "p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-500/10 active:text-red-600 transition-colors touch-manipulation min-w-8 min-h-8 flex items-center justify-center",
                                                                    processingTickets.has(idx) && "opacity-50 cursor-not-allowed"
                                                                )}
                                                            >
                                                                {processingTickets.has(idx) ? (
                                                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                                                ) : (
                                                                    <X className="w-3.5 h-3.5" />
                                                                )}
                                                            </button>
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                            {ticket.note && (
                                                <div className="text-xs text-slate-500 dark:text-slate-400 mt-1 wrap-break-word [overflow-wrap:anywhere]">
                                                    {ticket.note}
                                                </div>
                                            )}
                                        </div>
                                    ))}

                                {/* Auto Sum Footer */}
                                {localTickets.length > 0 && Object.keys(ticketsTotal).length > 0 && (
                                    <div className="mt-3 pt-2.5 border-t border-tabiji-forest/10 dark:border-white/10 flex justify-between items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                                        <span className="flex items-center gap-1 font-medium shrink-0">
                                            <Calculator className="w-3.5 h-3.5" />
                                            {zh ? "小計" : "Subtotal"}
                                        </span>
                                        <div className="flex flex-wrap justify-end gap-2">
                                            {Object.entries(ticketsTotal).map(([curr, total]) => (
                                                <span
                                                    key={curr}
                                                    className="font-mono tabular-nums font-bold text-sky-700 dark:text-sky-300 bg-sky-500/10 dark:bg-sky-400/15 px-2 py-0.5 rounded-md"
                                                >
                                                    {curr} {total.toLocaleString()}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {/* 現代空狀態卡片 */}
                                {localTickets.length === 0 && !addingTicket && !editingTickets && (
                                    <div className="py-6 px-4 text-center rounded-xl bg-tabiji-paper/45 dark:bg-white/[0.02] border border-dashed border-tabiji-forest/12 dark:border-white/10">
                                        <div className="w-11 h-11 rounded-2xl bg-sky-500/12 dark:bg-sky-400/15 text-sky-700 dark:text-sky-300 flex items-center justify-center mx-auto mb-2.5">
                                            <Ticket className="w-5 h-5" />
                                        </div>
                                        <p className="text-sm font-semibold text-tabiji-charcoal dark:text-tabiji-paper">
                                            {zh ? "尚無交通票券記錄" : "No transport tickets yet"}
                                        </p>
                                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 mb-3.5">
                                            {zh
                                                ? "整理 JR Pass、地鐵周遊券或特急班次座位資訊"
                                                : "Organize rail passes, subway tickets, or reserved seat notes"}
                                        </p>
                                        {!readOnly && (
                                            <button
                                                type="button"
                                                onClick={() => setAddingTicket(true)}
                                                className={primaryActionBtnClass}
                                            >
                                                <Plus className="w-3.5 h-3.5 mr-1" />
                                                {zh ? "新增第一筆票券" : "Add First Ticket"}
                                            </button>
                                        )}
                                    </div>
                                )}

                                {/* 新增票券：Linear 分層內嵌表單 */}
                                {addingTicket && (
                                    <div className="bg-tabiji-paper/65 dark:bg-white/[0.04] rounded-xl p-3.5 border border-tabiji-forest/12 dark:border-white/12 space-y-2.5 animate-in fade-in zoom-in-95 duration-200">
                                        <Input
                                            placeholder={zh ? "票券名稱（例如：Skyliner、東京地鐵 72h）" : "Ticket name (e.g. JR Pass, Subway 72h)"}
                                            className="h-10 text-sm bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                            value={newTicket.name}
                                            onChange={(e) => setNewTicket({ ...newTicket, name: e.target.value })}
                                            onKeyDown={(e) => {
                                                if (e.nativeEvent.isComposing) return
                                                if (e.key === "Enter") {
                                                    e.preventDefault()
                                                    handleAddTicket()
                                                }
                                                if (e.key === "Escape") {
                                                    e.preventDefault()
                                                    e.stopPropagation()
                                                    handleCancelAddTicket()
                                                }
                                            }}
                                        />
                                        <CurrencyPillSelector
                                            value={newTicket.currency || effectiveCurrency}
                                            defaultCurrency={effectiveCurrency}
                                            extraCurrencies={ticketExtraCurrencies}
                                            onChange={(curr) => setNewTicket({ ...newTicket, currency: curr })}
                                            zh={zh}
                                        />
                                        <div className="flex items-center gap-2">
                                            <span className="text-xs font-bold px-2.5 h-10 rounded-xl bg-tabiji-mist/70 dark:bg-white/8 text-tabiji-charcoal dark:text-tabiji-paper inline-flex items-center justify-center shrink-0">
                                                {newTicket.currency || effectiveCurrency}
                                            </span>
                                            <Input
                                                placeholder={zh ? "輸入金額" : "Enter amount"}
                                                className="flex-1 h-10 text-sm font-mono tabular-nums bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                                type="text"
                                                inputMode="decimal"
                                                value={newTicket.price}
                                                onChange={(e) => setNewTicket({ ...newTicket, price: e.target.value })}
                                                onKeyDown={(e) => {
                                                    if (e.nativeEvent.isComposing) return
                                                    if (e.key === "Enter") {
                                                        e.preventDefault()
                                                        handleAddTicket()
                                                    }
                                                    if (e.key === "Escape") {
                                                        e.preventDefault()
                                                        e.stopPropagation()
                                                        handleCancelAddTicket()
                                                    }
                                                }}
                                            />
                                        </div>
                                        <Input
                                            placeholder={zh ? "備註，例如班次時間、兌換櫃檯（選填）" : "Note, e.g. departure time, counter (optional)"}
                                            className="h-9 text-xs bg-white dark:bg-[#182320] border-tabiji-forest/15 dark:border-white/15"
                                            value={newTicket.note}
                                            onChange={(e) => setNewTicket({ ...newTicket, note: e.target.value })}
                                            onKeyDown={(e) => {
                                                if (e.nativeEvent.isComposing) return
                                                if (e.key === "Enter") {
                                                    e.preventDefault()
                                                    handleAddTicket()
                                                }
                                                if (e.key === "Escape") {
                                                    e.preventDefault()
                                                    e.stopPropagation()
                                                    handleCancelAddTicket()
                                                }
                                            }}
                                        />
                                        <div className="flex flex-wrap items-center justify-between gap-2 pt-1.5 border-t border-tabiji-forest/10 dark:border-white/10">
                                            <PrivacyTogglePill
                                                isPrivate={Boolean(newTicket.is_private)}
                                                onToggle={() =>
                                                    setNewTicket((prev) => ({ ...prev, is_private: !prev.is_private }))
                                                }
                                                zh={zh}
                                            />
                                            <div className="flex items-center gap-1.5 ml-auto">
                                                <button
                                                    type="button"
                                                    className={secondaryPillBtnClass}
                                                    onClick={handleCancelAddTicket}
                                                >
                                                    {zh ? "取消" : "Cancel"}
                                                </button>
                                                <button
                                                    type="button"
                                                    className={primaryActionBtnClass}
                                                    onClick={handleAddTicket}
                                                    disabled={saving}
                                                >
                                                    <Check className="w-3.5 h-3.5 mr-1" />
                                                    {zh ? "新增" : "Add"}
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
