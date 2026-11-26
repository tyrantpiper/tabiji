/**
 * Location Utilities (2026 Heuristic Engine)
 * Handles coordinate extraction and URL processing
 */
import type { SubItem } from "./itinerary-types"

// Pattern A: @lat,lng
const RE_COORD_A = /@(-?\d+\.\d+),(-?\d+\.\d+)/;
// 🆕 2026 Pattern B+: Non-consecutive !3d/!4d (handles intermediate params like !8m2)
const RE_LAT = /!3d(-?\d+\.\d+)/;
const RE_LNG = /!4d(-?\d+\.\d+)/;

export interface ExtractedLocation {
    lat: number | null;
    lng: number | null;
    method: 'client_regex_a' | 'client_regex_b' | 'none';
}

/**
 * ⚡ Tier 1: Client-side Regex Extraction
 * Zero-latency extraction for long URLs
 */
export function extractCoordsFromUrl(url: string): ExtractedLocation {
    if (!url) return { lat: null, lng: null, method: 'none' };

    // 🛡️ Pre-processing: Decode %21 to ! for robust matching
    const decodedUrl = decodeURIComponent(url.replace(/%21/g, '!'));

    // 🆕 Priority 1: Try Pattern B+ (!3d / !4d - Precise Pinpoint, allows gaps)
    const latMatch = decodedUrl.match(RE_LAT);
    const lngMatch = decodedUrl.match(RE_LNG);

    if (latMatch && lngMatch) {
        return {
            lat: parseFloat(latMatch[1]),
            lng: parseFloat(lngMatch[1]),
            method: 'client_regex_b'
        };
    }

    // 🆕 Priority 2: Try Pattern A (@lat,lng - Map Center Fallback)
    const matchA = decodedUrl.match(RE_COORD_A);
    if (matchA) {
        return {
            lat: parseFloat(matchA[1]),
            lng: parseFloat(matchA[2]),
            method: 'client_regex_a'
        };
    }

    return { lat: null, lng: null, method: 'none' };
}

/**
 * Check if a URL is any type of Google Maps link (shortlink or standard search)
 */
export function isGoogleMapsUrl(url: string | null | undefined): boolean {
    if (!url) return false;
    return /goo\.gl|maps\.app\.goo\.gl|google\.(?:com|co\.jp|com\.tw)\/maps/.test(url);
}

export function isGoogleMapsShortlink(url: string): boolean {
    return /goo\.gl|maps\.app\.goo\.gl/.test(url);
}

const GOOGLE_MAPS_HOST_RE = /^maps\.google\.(?:com|co\.[a-z]{2}|com\.[a-z]{2}|[a-z]{2,3})$/
const GOOGLE_WEB_HOST_RE = /^(?:www\.|m\.)?google\.(?:com|co\.[a-z]{2}|com\.[a-z]{2}|[a-z]{2,3})$/
const EXACT_MAP_HOSTS = new Set([
    "maps.app.goo.gl",
    "maps.apple.com",
    "beta.maps.apple.com",
    "openstreetmap.org",
    "www.openstreetmap.org",
    "osm.org",
    "www.osm.org",
    "map.naver.com",
    "m.map.naver.com",
    "naver.me",
    "map.kakao.com",
    "m.map.kakao.com",
    "kko.to",
    "map.yahoo.co.jp",
    "maps.loco.yahoo.co.jp",
    "amap.com",
    "www.amap.com",
    "ditu.amap.com",
    "surl.amap.com",
    "uri.amap.com",
    "map.baidu.com",
    "j.map.baidu.com",
    "api.map.baidu.com",
    "waze.com",
    "www.waze.com",
    "ul.waze.com",
])
const BING_HOSTS = new Set(["bing.com", "www.bing.com", "cn.bing.com"])

/**
 * 驗證是否為合法 http(s) URL（防範 javascript:/data:/控制字元與帳密權威混淆）
 */
export function isSafeHttpUrl(url: string | null | undefined): boolean {
    if (!url || typeof url !== "string") return false
    const raw = url.trim()
    if (!raw || /[\\\r\n\t]/.test(raw)) return false
    try {
        const parsed = new URL(raw)
        if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return false
        if (!parsed.hostname || parsed.username || parsed.password) return false
        return true
    } catch {
        return false
    }
}

/**
 * 檢查網址是否屬於合法地圖導航網域白名單（嚴格 URL 解析，杜絕 IG／官網／偽造子網域混入導航網址）
 */
export function isMapNavigationUrl(url: string | null | undefined): boolean {
    if (!isSafeHttpUrl(url)) return false
    try {
        const parsed = new URL(url!.trim())
        const host = parsed.hostname.toLowerCase().replace(/\.$/, "")
        const pathname = parsed.pathname.toLowerCase()
        if (!host) return false
        if (EXACT_MAP_HOSTS.has(host)) return true
        if (GOOGLE_MAPS_HOST_RE.test(host)) return true
        if (GOOGLE_WEB_HOST_RE.test(host) && (pathname === "/maps" || pathname.startsWith("/maps/"))) return true
        if (host === "goo.gl" && (pathname === "/maps" || pathname.startsWith("/maps/"))) return true
        if (BING_HOSTS.has(host) && (pathname === "/maps" || pathname.startsWith("/maps/"))) return true
        return false
    } catch {
        return false
    }
}

function normalizeUrlForDedupe(url: string): string {
    const raw = (url || "").trim()
    if (!raw) return ""
    try {
        const parsed = new URL(raw)
        const path = parsed.pathname.replace(/\/+$/, "")
        return `${parsed.protocol.toLowerCase()}//${parsed.host.toLowerCase()}${path}${parsed.search}`
    } catch {
        return raw.replace(/\/+$/, "")
    }
}

export function getReferenceLinkLabel(url: string, zh = true): string {
    let host = ""
    try {
        host = new URL(url.trim()).hostname.toLowerCase().replace(/\.$/, "")
    } catch {
        host = ""
    }
    if (host.startsWith("www.")) host = host.slice(4)
    else if (host.startsWith("m.")) host = host.slice(2)

    if (host === "instagram.com" || host === "instagr.am" || host.endsWith(".instagram.com")) {
        return zh ? "Instagram 參考連結" : "Instagram Link"
    }
    if (host === "threads.net" || host === "threads.com" || host.endsWith(".threads.net") || host.endsWith(".threads.com")) {
        return zh ? "Threads 參考連結" : "Threads Link"
    }
    if (host === "tiktok.com" || host.endsWith(".tiktok.com")) {
        return zh ? "TikTok 參考連結" : "TikTok Link"
    }
    if (host === "youtube.com" || host === "youtu.be" || host.endsWith(".youtube.com")) {
        return zh ? "YouTube 參考連結" : "YouTube Link"
    }
    if (host === "facebook.com" || host === "fb.com" || host === "fb.watch" || host.endsWith(".facebook.com")) {
        return zh ? "Facebook 參考連結" : "Facebook Link"
    }
    if (host === "x.com" || host === "twitter.com" || host.endsWith(".x.com") || host.endsWith(".twitter.com")) {
        return zh ? "X / Twitter 參考連結" : "X / Twitter Link"
    }
    if (host === "xiaohongshu.com" || host === "xhslink.com" || host.endsWith(".xiaohongshu.com")) {
        return zh ? "小紅書參考連結" : "Xiaohongshu Link"
    }
    if (host === "tabelog.com" || host.endsWith(".tabelog.com")) {
        return zh ? "Tabelog 食評連結" : "Tabelog Link"
    }
    if (host.startsWith("tripadvisor.") || host.includes(".tripadvisor.")) {
        return zh ? "TripAdvisor 參考連結" : "TripAdvisor Link"
    }
    if (host === "klook.com" || host.endsWith(".klook.com")) {
        return zh ? "Klook 預訂連結" : "Klook Link"
    }
    if (host === "kkday.com" || host.endsWith(".kkday.com")) {
        return zh ? "KKday 預訂連結" : "KKday Link"
    }
    if (
        host === "booking.com" ||
        host === "agoda.com" ||
        host.endsWith(".booking.com") ||
        host.endsWith(".agoda.com") ||
        host.startsWith("airbnb.") ||
        host.includes(".airbnb.")
    ) {
        return zh ? "訂房參考連結" : "Booking Link"
    }
    return zh ? "官方網站 / 參考連結" : "Official Site / Reference"
}

export interface SplitLinksResult {
    link_url?: string
    website_link?: string
    sub_items: SubItem[]
}

/**
 * 將導航網址 (link_url) 與參考網址 (website_link / 非地圖連結) 嚴格分流：
 * - link_url 僅保留合法地圖導航網址
 * - 非地圖連結（IG / Threads / 官網等）自動歸入 sub_items（此地備忘錄 → 相關連結，去重）與 website_link
 */
export function splitNavigationAndMemoLinks(
    linkUrl?: string | null,
    websiteLink?: string | null,
    subItems?: SubItem[] | null,
    zh = true
): SplitLinksResult {
    const cleanSubItems: SubItem[] = Array.isArray(subItems)
        ? subItems
            .filter((item): item is SubItem => Boolean(item && typeof item === "object"))
            .map((item) => ({ ...item }))
        : []

    const seenLinks = new Set<string>()
    for (const item of cleanSubItems) {
        if (typeof item.link === "string" && item.link.trim()) {
            seenLinks.add(normalizeUrlForDedupe(item.link))
        }
    }

    const rawLink = typeof linkUrl === "string" ? linkUrl.trim() : ""
    const rawWeb = typeof websiteLink === "string" ? websiteLink.trim() : ""

    let cleanLinkUrl: string | undefined = undefined
    let cleanWebsiteLink: string | undefined = isSafeHttpUrl(rawWeb) ? rawWeb : undefined
    const memoCandidates: string[] = []

    if (rawLink) {
        if (isMapNavigationUrl(rawLink)) {
            cleanLinkUrl = rawLink
        } else if (isSafeHttpUrl(rawLink)) {
            memoCandidates.push(rawLink)
            if (!cleanWebsiteLink) {
                cleanWebsiteLink = rawLink
            }
        }
    }

    if (cleanWebsiteLink && !isMapNavigationUrl(cleanWebsiteLink)) {
        memoCandidates.push(cleanWebsiteLink)
    }

    for (const candidate of memoCandidates) {
        const norm = normalizeUrlForDedupe(candidate)
        if (norm && !seenLinks.has(norm)) {
            seenLinks.add(norm)
            cleanSubItems.push({
                name: getReferenceLinkLabel(candidate, zh),
                link: candidate,
            })
        }
    }

    return {
        link_url: cleanLinkUrl,
        website_link: cleanWebsiteLink,
        sub_items: cleanSubItems,
    }
}

/**
 * 📏 簡易 Haversine 距離計算 (km)
 */
export function getDistanceKm(
    lat1: number, lng1: number,
    lat2: number, lng2: number
): number {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLng = (lng2 - lng1) * Math.PI / 180;
    const a =
        Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(lat1 * Math.PI / 180) *
        Math.cos(lat2 * Math.PI / 180) *
        Math.sin(dLng / 2) * Math.sin(dLng / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

export interface SmartZoomConfig {
    zoom: number
    duration: number
}

/**
 * 依據 Photon 1.3.0 admin_level 與 osm_value/type 計算最佳相機縮放層級與飛行時長
 */
export function getSmartZoomConfig(result: {
    name?: string
    type?: string | null
    admin_level?: number | null
    osm_key?: string | null
}): SmartZoomConfig {
    const level = result.admin_level
    const type = (result.type || "").toLowerCase()

    // 1. 國家層級 (Level 2) -> 3D Globe 地球儀視野
    if (level === 2 || type === "country") {
        return { zoom: 3.5, duration: 2000 }
    }
    // 2. 州 / 省層級 (Level 3-4)
    if (level === 3 || level === 4 || type === "state" || type === "province") {
        return { zoom: 6.5, duration: 1800 }
    }
    // 3. 縣市 / 都會區層級 (Level 5-6)
    if (level === 5 || level === 6 || type === "city" || type === "county" || type === "municipality" || type === "region" || type === "administrative") {
        return { zoom: 10.5, duration: 1600 }
    }
    // 4. 市鎮 / 區層級 (Level 7-8)
    if (level === 7 || level === 8 || type === "district" || type === "town" || type === "suburb") {
        return { zoom: 13.5, duration: 1400 }
    }
    // 5. 一般景點、餐廳、飯店或具體門牌 (預設 POI)
    return { zoom: 16.5, duration: 1200 }
}

const MACRO_GEO_TYPES = new Set([
    "country",
    "state",
    "province",
    "city",
    "county",
    "municipality",
    "region",
    "administrative",
])

/**
 * 判斷搜尋結果是否為宏觀行政區（國家／省州／城市），點擊時僅展開該區視野、不開啟 POIDetailDrawer。
 */
export function isMacroGeoResult(result: {
    type?: string | null
    admin_level?: number | null
}): boolean {
    const level = result.admin_level
    if (typeof level === "number" && Number.isFinite(level) && level >= 1 && level <= 6) {
        return true
    }
    const type = (result.type || "").toLowerCase().trim()
    return MACRO_GEO_TYPES.has(type)
}

/**
 * 驗證 RFC 7946 extent ([minLon, minLat, maxLon, maxLat]) 是否適合 MapLibre fitBounds：
 * - 確保四值皆為有限數且滿足 min <= max 與 Web Mercator 安全緯度範圍
 * - 跨洋跨距守衛（經度或緯度跨距 > 45° 時退回 flyTo，避免法國/美國海外領地導致全球縮放到 zoom=1）
 */
export function isUsableMacroExtent(extent: unknown): extent is [number, number, number, number] {
    if (!Array.isArray(extent) || extent.length !== 4) return false
    const [minLon, minLat, maxLon, maxLat] = extent
    if (
        typeof minLon !== "number" || typeof minLat !== "number" ||
        typeof maxLon !== "number" || typeof maxLat !== "number" ||
        !Number.isFinite(minLon) || !Number.isFinite(minLat) ||
        !Number.isFinite(maxLon) || !Number.isFinite(maxLat)
    ) {
        return false
    }
    if (minLon < -180 || maxLon > 180 || minLon > maxLon) return false
    if (minLat < -85.051129 || maxLat > 85.051129 || minLat > maxLat) return false
    const lonSpan = maxLon - minLon
    const latSpan = maxLat - minLat
    if (lonSpan < 1e-4 && latSpan < 1e-4) return false
    if (lonSpan > 45 || latSpan > 45) return false
    return true
}

const PAREN_REMARK_GLOBAL_RE = /[(（[【]([^()（）[\]【】]{1,80})[)）\]】]/g
const LEADING_ACTIVITY_PREFIX_RE = /^(?:(?:day\s*\d+|d\d+|第\s*\d+\s*天)\s*[:：\-—–]?\s*|\d{1,2}:\d{2}(?:\s*[-~～]\s*\d{1,2}:\d{2})?\s+|(?:上午|下午|晚上|早上|中午|傍晚|早餐|午餐|晚餐|宵夜|前往|參觀|拜訪|逛逛|逛|吃)\s*[:：]\s*|(?:前往|參觀|拜訪|抵達|入住)\s+)/i

/**
 * 從帶括號備註或行程前綴的長活動標題中提取純淨搜尋地名
 * 例："淺草寺 (雷門拍照)" -> "淺草寺"、"10:00 築地市場（海鮮早餐）" -> "築地市場"
 */
export function extractCleanPlaceQuery(raw: string): string {
    const trimmed = (raw || "").trim()
    if (!trimmed) return ""
    const cleaned = trimmed
        .replace(PAREN_REMARK_GLOBAL_RE, " ")
        .replace(LEADING_ACTIVITY_PREFIX_RE, "")
        .replace(/\s+/g, " ")
        .replace(/^[\s\-—–|:：,，]+|[\s\-—–|:：,，]+$/g, "")
    return cleaned.length >= 2 ? cleaned : trimmed
}

/**
 * 提取活動標題內的括號備註文字（選取搜尋結果時若 desc 為空可無損保留）
 * 例："淺草寺 (雷門拍照)" -> "雷門拍照"
 */
export function extractPlaceParentheticalNote(raw: string): string {
    const trimmed = (raw || "").trim()
    if (!trimmed) return ""
    const notes: string[] = []
    const re = new RegExp(PAREN_REMARK_GLOBAL_RE.source, "g")
    let match: RegExpExecArray | null
    while ((match = re.exec(trimmed)) !== null) {
        const inner = (match[1] || "").trim()
        if (inner && !notes.includes(inner)) {
            notes.push(inner)
        }
    }
    return notes.join(" / ")
}

/**
 * 統一 Photon ('N'/'W'/'R') 與 Nominatim/Overpass ('node'/'way'/'relation') 之 OSM 型別
 */
export function normalizeOsmType(rawType?: string | null): string {
    const t = String(rawType || "").trim().toLowerCase()
    if (t === "n" || t === "node") return "node"
    if (t === "w" || t === "way") return "way"
    if (t === "r" || t === "relation") return "relation"
    return t
}

function normalizePlaceNameForDedupe(name?: string | null): string {
    return String(name || "")
        .trim()
        .toLowerCase()
        .replace(/臺/g, "台")
        .replace(/\s+/g, "")
}

export interface DedupeablePlace {
    name?: string
    lat?: number
    lng?: number
    latitude?: number
    longitude?: number
    osm_id?: number | string | null
    osm_type?: string | null
}

/**
 * 判斷兩筆地理編碼結果是否為同一實體：
 * 1) 相同正規化 (normOsmType, osm_id)（若其一缺 osm_type 仍容許相同 osm_id 比對）；
 * 2) 同正規化地名且距離 < 50m（避免同棟大樓內不同店家被誤去重）。
 */
export function isDuplicateGeocodeResult(a: DedupeablePlace, b: DedupeablePlace): boolean {
    if (a.osm_id != null && b.osm_id != null && String(a.osm_id) !== "" && String(a.osm_id) === String(b.osm_id)) {
        const typeA = normalizeOsmType(a.osm_type)
        const typeB = normalizeOsmType(b.osm_type)
        if (!typeA || !typeB || typeA === typeB) {
            return true
        }
    }
    const nameA = normalizePlaceNameForDedupe(a.name)
    const nameB = normalizePlaceNameForDedupe(b.name)
    if (!nameA || nameA !== nameB) return false
    const latA = a.lat ?? a.latitude
    const lngA = a.lng ?? a.longitude
    const latB = b.lat ?? b.latitude
    const lngB = b.lng ?? b.longitude
    if (
        typeof latA !== "number" || typeof lngA !== "number" ||
        typeof latB !== "number" || typeof lngB !== "number" ||
        !Number.isFinite(latA) || !Number.isFinite(lngA) ||
        !Number.isFinite(latB) || !Number.isFinite(lngB)
    ) {
        return false
    }
    return getDistanceKm(latA, lngA, latB, lngB) < 0.05
}

/**
 * 對地理編碼結果陣列進行穩定保序去重（(normOsmType, osm_id) + 同名 50m）
 */
export function dedupeGeocodeResults<T extends DedupeablePlace>(items: T[]): T[] {
    const out: T[] = []
    for (const item of items) {
        if (!out.some((existing) => isDuplicateGeocodeResult(existing, item))) {
            out.push(item)
        }
    }
    return out
}
