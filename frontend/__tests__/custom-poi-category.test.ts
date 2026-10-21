import { describe, it, expect } from "vitest"
import {
    serializeCustomCategory,
    parseCategory,
    harvestCustomCategories,
    STANDARD_CATEGORIES,
} from "@/lib/poi-category-protocol"
import { POIItem } from "@/lib/poi-types"

describe("Custom POI Category Protocol Engine", () => {
    describe("serializeCustomCategory", () => {
        it("should format valid inputs into the self-contained protocol string", () => {
            const result = serializeCustomCategory("🍜", "拉麵", "#F59E0B")
            expect(result).toBe("custom:🍜:拉麵:#F59E0B")
        })

        it("should sanitize colons in category name to avoid delimiter collisions", () => {
            const result = serializeCustomCategory("☕", "下午茶:鬆餅", "#E56E25")
            expect(result).toBe("custom:☕:下午茶：鬆餅:#E56E25")
            expect(result.split(":")).toHaveLength(4)
        })

        it("should ensure color has a leading hash #", () => {
            const result = serializeCustomCategory("⛩️", "神社", "10B981")
            expect(result).toBe("custom:⛩️:神社:#10B981")
        })

        it("should fallback to default emoji and name if empty inputs given", () => {
            const result = serializeCustomCategory("", "", "#E56E25")
            expect(result).toBe("custom:📍:自訂:#E56E25")
        })
    })

    describe("parseCategory", () => {
        it("should parse custom protocol strings with emoji, label, and color", () => {
            const parsed = parseCategory("custom:🍜:拉麵:#F59E0B")
            expect(parsed.isCustom).toBe(true)
            expect(parsed.key).toBe("custom:🍜:拉麵:#F59E0B")
            expect(parsed.emoji).toBe("🍜")
            expect(parsed.label).toBe("拉麵")
            expect(parsed.color).toBe("#F59E0B")
            expect(parsed.bg).toBe("#F59E0B1A")
        })

        it("should handle embedded colons safely by joining middle segments", () => {
            const parsed = parseCategory("custom:☕:下午茶:鬆餅:#E56E25")
            expect(parsed.isCustom).toBe(true)
            expect(parsed.emoji).toBe("☕")
            expect(parsed.label).toBe("下午茶:鬆餅")
            expect(parsed.color).toBe("#E56E25")
        })

        it("should parse standard categories accurately", () => {
            for (const cat of STANDARD_CATEGORIES) {
                const parsed = parseCategory(cat)
                expect(parsed.isCustom).toBe(false)
                expect(parsed.key).toBe(cat)
                expect(parsed.icon).toBeDefined()
                expect(parsed.color).toBeDefined()
                expect(parsed.bg).toBeDefined()
            }
        })

        it("should gracefully degrade to other for null, empty or corrupted strings", () => {
            expect(parseCategory(null).key).toBe("other")
            expect(parseCategory(undefined).key).toBe("other")
            expect(parseCategory("").key).toBe("other")
            expect(parseCategory("custom:").key).toBe("other")
            expect(parseCategory("custom:🍜").key).toBe("other")
            expect(parseCategory("unknown_random_cat").key).toBe("other")
        })
    })

    describe("harvestCustomCategories", () => {
        it("should deduplicate multiple POIs with identical custom categories", () => {
            const mockPois: POIItem[] = [
                { id: "1", user_id: "u1", title: "一蘭", lat: 25.0, lng: 121.5, category: "custom:🍜:拉麵:#F59E0B", is_pinned: false, created_at: 1, updated_at: 1 },
                { id: "2", user_id: "u1", title: "鼎泰豐", lat: 25.1, lng: 121.6, category: "food", is_pinned: false, created_at: 2, updated_at: 2 },
                { id: "3", user_id: "u1", title: "麵屋一燈", lat: 25.2, lng: 121.7, category: "custom:🍜:拉麵:#F59E0B", is_pinned: false, created_at: 3, updated_at: 3 },
                { id: "4", user_id: "u1", title: "淺草寺", lat: 25.3, lng: 121.8, category: "custom:⛩️:神社:#EF4444", is_pinned: false, created_at: 4, updated_at: 4 },
                { id: "5", user_id: "u1", title: "台北101", lat: 25.4, lng: 121.9, category: "attraction", is_pinned: false, created_at: 5, updated_at: 5 },
            ]

            const harvested = harvestCustomCategories(mockPois)
            expect(harvested).toHaveLength(2)

            const keys = harvested.map((h) => h.key)
            expect(keys).toContain("custom:🍜:拉麵:#F59E0B")
            expect(keys).toContain("custom:⛩️:神社:#EF4444")
            expect(keys).not.toContain("food")
            expect(keys).not.toContain("attraction")
        })

        it("should return empty array when no custom categories exist or pois is empty", () => {
            expect(harvestCustomCategories([])).toEqual([])
            expect(harvestCustomCategories([
                { id: "1", user_id: "u1", title: "景點", lat: 25.0, lng: 121.5, category: "attraction", is_pinned: false, created_at: 1, updated_at: 1 }
            ])).toEqual([])
        })
    })
})
