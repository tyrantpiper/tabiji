/**
 * Destination Covers Registry (frontend/lib/destination-covers.ts)
 * Pre-curated, high-aesthetic, ultra-compressed WebP hero images (~60KB).
 * Zero external API cost, zero rate-limit, instant PWA offline boot.
 */

export const PRE_CURATED_COVERS: Record<string, string> = {
    tokyo: "https://images.unsplash.com/photo-1503899036084-c55cdd92da26?w=1200&q=80&auto=format&fit=crop",
    kyoto: "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?w=1200&q=80&auto=format&fit=crop",
    osaka: "https://images.unsplash.com/photo-1590559899731-a382839e5549?w=1200&q=80&auto=format&fit=crop",
    taipei: "https://images.unsplash.com/photo-1508248017083-161676430b91?w=1200&q=80&auto=format&fit=crop",
    paris: "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=1200&q=80&auto=format&fit=crop",
    newyork: "https://images.unsplash.com/photo-1496442226666-8d4d0e62e6e9?w=1200&q=80&auto=format&fit=crop",
    london: "https://images.unsplash.com/photo-1513635269975-59663e0ac1ad?w=1200&q=80&auto=format&fit=crop",
    seoul: "https://images.unsplash.com/photo-1538485399081-7191377e8241?w=1200&q=80&auto=format&fit=crop",
    bangkok: "https://images.unsplash.com/photo-1508009603885-50cf7c579365?w=1200&q=80&auto=format&fit=crop",
    hokkaido: "https://images.unsplash.com/photo-1542051841857-5f90071e7989?w=1200&q=80&auto=format&fit=crop",
    iceland: "https://images.unsplash.com/photo-1504893524553-b855bce32c67?w=1200&q=80&auto=format&fit=crop",
}

export const DEFAULT_COVER_IMAGE = "https://images.unsplash.com/photo-1488646953014-85cb44e25828?w=1200&q=80&auto=format&fit=crop"

export const CITY_ALIASES: Record<string, string> = {
    "東京": "tokyo",
    "tokyo": "tokyo",
    "京都": "kyoto",
    "kyoto": "kyoto",
    "大阪": "osaka",
    "osaka": "osaka",
    "台北": "taipei",
    "taipei": "taipei",
    "巴黎": "paris",
    "paris": "paris",
    "紐約": "newyork",
    "new york": "newyork",
    "nyc": "newyork",
    "倫敦": "london",
    "london": "london",
    "首爾": "seoul",
    "seoul": "seoul",
    "曼谷": "bangkok",
    "bangkok": "bangkok",
    "北海道": "hokkaido",
    "hokkaido": "hokkaido",
    "冰島": "iceland",
    "iceland": "iceland",
}

/**
 * 根據行程標題與目的地智能解析最佳封面圖
 */
export function resolveDestinationCover(title?: string, destination?: string): string {
    const combined = `${title || ''} ${destination || ''}`.toLowerCase()

    for (const [keyword, cityKey] of Object.entries(CITY_ALIASES)) {
        if (combined.includes(keyword)) {
            const url = PRE_CURATED_COVERS[cityKey]
            if (url) return url
        }
    }

    return DEFAULT_COVER_IMAGE
}
