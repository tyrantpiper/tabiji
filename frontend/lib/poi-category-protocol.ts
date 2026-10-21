import React from "react"
import { Landmark, Utensils, Coffee, ShoppingBag, Hotel, Train, Compass } from "lucide-react"
import { POIItem, StandardPOICategory } from "./poi-types"
import type { TranslationKey } from "./i18n"

export type { StandardPOICategory }

export interface ParsedCategory {
    isCustom: boolean
    key: string
    label: string
    labelKey?: TranslationKey
    emoji?: string
    color: string
    bg: string
    icon?: React.ElementType
}

export const STANDARD_CATEGORIES: StandardPOICategory[] = [
    "attraction",
    "food",
    "cafe",
    "shopping",
    "hotel",
    "transport",
    "other",
]

export const CATEGORY_MAP: Record<StandardPOICategory, { labelKey: TranslationKey; icon: React.ElementType; color: string; bg: string }> = {
    attraction: { labelKey: "poi_cat_attraction", icon: Landmark, color: "text-emerald-600 dark:text-emerald-400", bg: "bg-emerald-50 dark:bg-emerald-950/40" },
    food: { labelKey: "poi_cat_food", icon: Utensils, color: "text-amber-600 dark:text-amber-400", bg: "bg-amber-50 dark:bg-amber-950/40" },
    cafe: { labelKey: "poi_cat_cafe", icon: Coffee, color: "text-orange-600 dark:text-orange-400", bg: "bg-orange-50 dark:bg-orange-950/40" },
    shopping: { labelKey: "poi_cat_shopping", icon: ShoppingBag, color: "text-pink-600 dark:text-pink-400", bg: "bg-pink-50 dark:bg-pink-950/40" },
    hotel: { labelKey: "poi_cat_hotel", icon: Hotel, color: "text-indigo-600 dark:text-indigo-400", bg: "bg-indigo-50 dark:bg-indigo-950/40" },
    transport: { labelKey: "poi_cat_transport", icon: Train, color: "text-blue-600 dark:text-blue-400", bg: "bg-blue-50 dark:bg-blue-950/40" },
    other: { labelKey: "poi_cat_all", icon: Compass, color: "text-slate-600 dark:text-slate-400", bg: "bg-slate-50 dark:bg-slate-800" },
}

export const THEME_COLOR_PALETTE = [
    { name: "蜜柑橘", hex: "#E56E25", bgClass: "bg-[#E56E25]" },
    { name: "琥珀黃", hex: "#F59E0B", bgClass: "bg-amber-500" },
    { name: "翡翠綠", hex: "#10B981", bgClass: "bg-emerald-500" },
    { name: "青空藍", hex: "#0EA5E9", bgClass: "bg-sky-500" },
    { name: "琉璃靛", hex: "#6366F1", bgClass: "bg-indigo-500" },
    { name: "紫羅蘭", hex: "#8B5CF6", bgClass: "bg-purple-500" },
    { name: "櫻花粉", hex: "#EC4899", bgClass: "bg-pink-500" },
    { name: "玄石墨", hex: "#64748B", bgClass: "bg-slate-500" },
]

export const CURATED_TRAVEL_EMOJIS = [
    {
        group: "美食推薦",
        emojis: ["🍜", "🍣", "🍱", "🍢", "🍧", "☕", "🍵", "🍺", "🍶", "🥐", "🥩", "🍦", "🍔", "🥞", "🥟"],
    },
    {
        group: "景點觀光",
        emojis: ["⛩️", "🏯", "🎡", "🎢", "🎨", "📷", "🌸", "🍁", "♨️", "🎆", "🗼", "🏖️", "🏛️", "🗿", "🌅"],
    },
    {
        group: "購物生活",
        emojis: ["🛍️", "🛒", "🎁", "👟", "💊", "📚", "🎮", "💄", "🕶️", "🧸", "👗", "🏪", "🏷️", "💳"],
    },
    {
        group: "戶外交通",
        emojis: ["⛰️", "🏕️", "🚴", "🛹", "🎿", "🤿", "🎣", "🚂", "✈️", "🚢", "🚕", "🚌", "🚡", "⚓"],
    },
]

/**
 * 序列化自訂類別為協定字串 custom:<emoji>:<name>:<colorHex>
 * 🛡️ 冒號轉義為全形冒號，杜絕協定注入破壞
 */
export function serializeCustomCategory(emoji: string, name: string, colorHex: string): string {
    const cleanEmoji = emoji.trim() || "📍"
    const cleanName = name.replaceAll(":", "：").trim() || "自訂"
    const cleanColor = colorHex.startsWith("#") ? colorHex : `#${colorHex}`
    return `custom:${cleanEmoji}:${cleanName}:${cleanColor}`
}

/**
 * 解析類別字串（自訂協定或預設類別）
 */
export function parseCategory(catStr: string | null | undefined): ParsedCategory {
    if (!catStr) {
        const otherMeta = CATEGORY_MAP.other
        return {
            isCustom: false,
            key: "other",
            label: "全部",
            labelKey: otherMeta.labelKey,
            color: otherMeta.color,
            bg: otherMeta.bg,
            icon: otherMeta.icon,
        }
    }

    if (catStr.startsWith("custom:")) {
        const parts = catStr.split(":")
        if (parts.length >= 4) {
            const emoji = parts[1] || "📍"
            const color = parts[parts.length - 1] || "#E56E25"
            const label = parts.slice(2, parts.length - 1).join(":") || "自訂"
            return {
                isCustom: true,
                key: catStr,
                label,
                emoji,
                color,
                bg: `${color}1A`, // 10% alpha background
            }
        }
    }

    // 標準預設類別
    const stdKey = (catStr in CATEGORY_MAP ? catStr : "other") as StandardPOICategory
    const meta = CATEGORY_MAP[stdKey]
    return {
        isCustom: false,
        key: stdKey,
        label: stdKey,
        labelKey: meta.labelKey,
        color: meta.color,
        bg: meta.bg,
        icon: meta.icon,
    }
}

/**
 * 跨 POIs 動態收割提取使用中的自訂類別（去重、純淨、防覆蓋）
 */
export function harvestCustomCategories(pois: POIItem[]): ParsedCategory[] {
    const map = new Map<string, ParsedCategory>()
    for (const p of pois || []) {
        if (p?.category && typeof p.category === "string" && p.category.startsWith("custom:")) {
            if (!map.has(p.category)) {
                map.set(p.category, parseCategory(p.category))
            }
        }
    }
    return Array.from(map.values())
}
