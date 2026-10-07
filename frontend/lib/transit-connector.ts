/**
 * 🚆 transit-connector.ts - 交通銜接距離計算與雙點導航引擎
 * 
 * 核心功能:
 * 1. Haversine 大圓球面幾何計算相鄰景點距離
 * 2. 智慧自適應交通時間推估 (步行 <1.5km, 大眾運輸 >=1.5km, 城際鐵路 >=50km)
 * 3. 安全無注入的 Google Maps 跨平台 Universal URL 生成 (RFC 3986)
 * 4. 嚴格的座標防禦與 NaN 熔斷
 */

export type TravelMode = 'walking' | 'transit' | 'driving' | 'bicycling'

export interface TransitCoords {
    lat: number
    lng: number
    name?: string
}

export interface TransitCalculationResult {
    distanceKm: number
    estimatedMinutes: number
    recommendedMode: TravelMode
    isIntercity: boolean
    googleMapsUrl: string
}

const EARTH_RADIUS_KM = 6371.0088

/**
 * 🛡️ 座標防禦性驗證器: 防止 NaN、Infinity、超界與型別注入
 */
export function isValidCoordinate(lat: unknown, lng: unknown): boolean {
    if (lat === null || lat === undefined || lng === null || lng === undefined) return false
    const numLat = typeof lat === 'number' ? lat : parseFloat(String(lat))
    const numLng = typeof lng === 'number' ? lng : parseFloat(String(lng))

    if (!Number.isFinite(numLat) || !Number.isFinite(numLng)) return false
    if (numLat < -90 || numLat > 90) return false
    if (numLng < -180 || numLng > 180) return false
    // 排除預設或無效原點 (0, 0)
    if (Math.abs(numLat) < 0.0001 && Math.abs(numLng) < 0.0001) return false

    return true
}

/**
 * 📐 Haversine 球面大圓幾何距離演算法 (單位: 公里)
 */
export function calculateHaversineDistance(
    lat1: number,
    lng1: number,
    lat2: number,
    lng2: number
): number {
    if (!isValidCoordinate(lat1, lng1) || !isValidCoordinate(lat2, lng2)) {
        return 0
    }

    const toRad = (degree: number) => (degree * Math.PI) / 180
    const dLat = toRad(lat2 - lat1)
    const dLng = toRad(lng2 - lng1)

    const a =
        Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
        Math.sin(dLng / 2) * Math.sin(dLng / 2)

    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
    const distance = EARTH_RADIUS_KM * c

    return Math.max(0, Math.round(distance * 100) / 100)
}

/**
 * ⏱️ 智能自適應交通時間推估
 * @param distanceKm 兩點距離 (公里)
 * @param manualMode 使用者手動指定的交通工具 (可選)
 */
export function estimateTransitTime(
    distanceKm: number,
    manualMode?: TravelMode
): { minutes: number; recommendedMode: TravelMode; isIntercity: boolean } {
    if (!Number.isFinite(distanceKm) || distanceKm <= 0) {
        return { minutes: 1, recommendedMode: 'walking', isIntercity: false }
    }

    const isIntercity = distanceKm >= 50
    let recommendedMode: TravelMode = manualMode || 'walking'

    if (!manualMode) {
        if (distanceKm < 1.5) {
            recommendedMode = 'walking'
        } else if (isIntercity) {
            recommendedMode = 'transit'
        } else {
            recommendedMode = 'transit'
        }
    }

    let minutes = 1
    switch (recommendedMode) {
        case 'walking':
            // 步行時速約 4.8 km/h -> 12.5 分鐘/公里
            minutes = Math.round(distanceKm * 12.5)
            break
        case 'bicycling':
            // 自行車時速約 15 km/h -> 4 分鐘/公里 + 1 分鐘緩衝
            minutes = Math.round(distanceKm * 4) + 1
            break
        case 'driving':
            // 市區行車時速約 30 km/h -> 2 分鐘/公里 + 3 分鐘紅綠燈
            minutes = Math.round(distanceKm * 2) + 3
            break
        case 'transit':
        default:
            if (isIntercity) {
                // 城際長途 (高鐵/城際鐵路): 平均時速推估 120 km/h + 15 分鐘等候轉乘
                minutes = Math.round((distanceKm / 120) * 60) + 15
            } else {
                // 市區大眾運輸 (地鐵/公車): 均速 22 km/h + 6 分鐘等候步行緩衝
                minutes = Math.round((distanceKm / 22) * 60) + 6
            }
            break
    }

    return {
        minutes: Math.max(1, minutes),
        recommendedMode,
        isIntercity
    }
}

/**
 * 🗺️ 安全生成 Google Maps 雙點路徑規劃 Universal URL (RFC 3986 防注入)
 */
export function generateGoogleMapsDirUrl(
    origin: TransitCoords,
    destination: TransitCoords,
    mode: TravelMode = 'walking'
): string {
    if (!isValidCoordinate(origin.lat, origin.lng) || !isValidCoordinate(destination.lat, destination.lng)) {
        return 'https://www.google.com/maps'
    }

    // Google Maps dir travelmode: walking | transit | driving | bicycling
    const validModes: Record<TravelMode, string> = {
        walking: 'walking',
        transit: 'transit',
        driving: 'driving',
        bicycling: 'bicycling'
    }
    const safeMode = validModes[mode] || 'walking'

    const originParam = `${origin.lat.toFixed(6)},${origin.lng.toFixed(6)}`
    const destParam = `${destination.lat.toFixed(6)},${destination.lng.toFixed(6)}`

    const url = new URL('https://www.google.com/maps/dir/')
    url.searchParams.set('api', '1')
    url.searchParams.set('origin', originParam)
    url.searchParams.set('destination', destParam)
    url.searchParams.set('travelmode', safeMode)

    return url.toString()
}

/**
 * 🚀 一鍵綜合計算交通銜接物件
 */
export function computeTransitSegment(
    origin: TransitCoords,
    destination: TransitCoords,
    overrideMode?: TravelMode
): TransitCalculationResult | null {
    if (!isValidCoordinate(origin.lat, origin.lng) || !isValidCoordinate(destination.lat, destination.lng)) {
        return null
    }

    const distanceKm = calculateHaversineDistance(origin.lat, origin.lng, destination.lat, destination.lng)
    const { minutes, recommendedMode, isIntercity } = estimateTransitTime(distanceKm, overrideMode)
    const googleMapsUrl = generateGoogleMapsDirUrl(origin, destination, recommendedMode)

    return {
        distanceKm,
        estimatedMinutes: minutes,
        recommendedMode,
        isIntercity,
        googleMapsUrl
    }
}
