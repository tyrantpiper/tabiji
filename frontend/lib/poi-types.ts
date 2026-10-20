/**
 * POI Pool & Saved Places Type Definitions
 */

export type POICategory = "attraction" | "food" | "cafe" | "shopping" | "hotel" | "transport" | "other"

export interface POIItem {
    id: string
    user_id: string
    title: string
    address?: string | null
    lat: number
    lng: number
    google_place_id?: string | null
    category: POICategory
    rating?: number | null
    user_notes?: string | null
    source_url?: string | null
    is_pinned: boolean
    pin_color?: string
    created_at: number
    updated_at: number
}

export interface CreatePOIDTO {
    title: string
    address?: string | null
    lat: number
    lng: number
    google_place_id?: string | null
    category?: POICategory
    rating?: number | null
    user_notes?: string | null
    source_url?: string | null
    is_pinned?: boolean
    pin_color?: string
}

export interface ImportLinkResponse {
    success: boolean
    count: number
    items: POIItem[]
    error?: string
}
