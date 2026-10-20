import { NextResponse } from "next/server";
import { POIItem, POICategory } from "@/lib/poi-types";

// In-Memory store for fast local development / session persistence
// Key: userId -> POIItem[]
const GLOBAL_POI_MEMORY_STORE: Record<string, POIItem[]> = {};

function getUserId(request: Request): string {
    const fromHeader = request.headers.get("X-User-ID");
    if (fromHeader && fromHeader.trim().length > 0) return fromHeader.trim();
    return "guest-session";
}

function sanitizeUrl(raw: string): string | null {
    if (!raw || typeof raw !== "string") return null;
    const match = raw.match(/(https?:\/\/[^\s]+)/);
    if (!match) return null;
    return match[1].replace(/[.,!?:;"'。，！？]+$/, "");
}

async function followRedirects(url: string, maxRedirects = 6) {
    let currentUrl = url;

    for (let i = 0; i < maxRedirects; i++) {
        try {
            const resp = await fetch(currentUrl, {
                method: "GET",
                redirect: "manual",
                headers: {
                    "User-Agent":
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                    "Accept":
                        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                },
            });

            const status = resp.status;
            if ([301, 302, 303, 307, 308].includes(status)) {
                const loc = resp.headers.get("Location");
                if (loc) {
                    currentUrl = new URL(loc, currentUrl).toString();
                    continue;
                }
            }

            // Check if HTML contains meta refresh
            const contentType = resp.headers.get("content-type") || "";
            if (contentType.includes("text/html")) {
                const text = await resp.text();
                const metaRefreshMatch = text.match(/<meta[^>]*http-equiv=["']?refresh["']?[^>]*content=["']?[0-9]+;\s*url=['"]?([^"'>]+)['"]?/i);
                if (metaRefreshMatch && metaRefreshMatch[1]) {
                    currentUrl = new URL(metaRefreshMatch[1], currentUrl).toString();
                    continue;
                }
                // Return cached text so we don't need to re-read body
                return { finalUrl: currentUrl, html: text };
            }

            return { finalUrl: currentUrl, html: "" };
        } catch (e) {
            console.error("[POI Proxy] Redirect trace error:", e);
            break;
        }
    }
    return { finalUrl: currentUrl, html: "" };
}

// 🔍 解析 Google 地圖連結 (單點或清單)
async function extractPlacesFromGoogleMaps(rawInput: string) {
    const cleanUrl = sanitizeUrl(rawInput);
    if (!cleanUrl) {
        throw new Error("請輸入有效的網址");
    }

    const { finalUrl, html } = await followRedirects(cleanUrl);
    const places: { title: string; lat: number; lng: number; address: string; category: POICategory }[] = [];

    // 1. 檢查是否為 Google Maps 共享清單 (Placelists)
    if (finalUrl.includes("/placelists/") || finalUrl.includes("/placelists/list")) {
        let contentHtml = html;
        if (!contentHtml) {
            try {
                const r = await fetch(finalUrl, {
                    headers: {
                        "User-Agent":
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                    },
                });
                contentHtml = await r.text();
            } catch {}
        }

        if (contentHtml) {
            // A. 正則匹配清單標題與座標組: "標題",null,null,null,null,[null,null,lat,lng]
            const titleMatches = [...contentHtml.matchAll(/"([^"]{2,60})",null,null,null,null,\[null,null,(-?\d+\.\d+),(-?\d+\.\d+)\]/g)];
            if (titleMatches.length > 0) {
                for (const m of titleMatches) {
                    const rawTitle = m[1];
                    const lat = parseFloat(m[2]);
                    const lng = parseFloat(m[3]);
                    if (!isNaN(lat) && !isNaN(lng) && lat !== 0 && lng !== 0) {
                        const cleanTitle = rawTitle.replace(/\\"/g, '"').replace(/\\u([0-9a-fA-F]{4})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16))).trim();
                        places.push({
                            title: cleanTitle,
                            lat,
                            lng,
                            address: cleanUrl,
                            category: "attraction",
                        });
                    }
                }
            } else {
                // B. 容錯座標匹配
                const coordMatches = [...contentHtml.matchAll(/\[null,\s*null,\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)\]/g)];
                const seen = new Set<string>();
                let idx = 1;
                for (const m of coordMatches) {
                    const lat = parseFloat(m[1]);
                    const lng = parseFloat(m[2]);
                    const key = `${lat.toFixed(4)},${lng.toFixed(4)}`;
                    if (!seen.has(key) && !isNaN(lat) && !isNaN(lng) && lat !== 0 && lng !== 0) {
                        seen.add(key);
                        places.push({
                            title: `口袋清單景點 #${idx++}`,
                            lat,
                            lng,
                            address: cleanUrl,
                            category: "attraction",
                        });
                    }
                }
            }
        }
    }

    // 2. 若不是清單或清單未取出，解析單點
    if (places.length === 0) {
        let lat: number | null = null;
        let lng: number | null = null;
        let title = "已儲存地點";

        // A. @lat,lng
        const matchA = finalUrl.match(/@(-?\d+\.\d+),(-?\d+\.\d+)/);
        if (matchA) {
            lat = parseFloat(matchA[1]);
            lng = parseFloat(matchA[2]);
        }

        // B. !3dlat!4dlng (Protobuf / Place URL)
        if (!lat) {
            const matchB = finalUrl.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/);
            if (matchB) {
                lat = parseFloat(matchB[1]);
                lng = parseFloat(matchB[2]);
            }
        }

        // C. staticmap center=lat,lng
        if (!lat && html) {
            const matchC = html.match(/center=(-?\d+\.\d+)(?:%2C|,)(-?\d+\.\d+)/);
            if (matchC) {
                lat = parseFloat(matchC[1]);
                lng = parseFloat(matchC[2]);
            }
        }

        // D. 提取地點標題 /place/NAME/
        const placeMatch = finalUrl.match(/\/place\/([^/@?]+)/);
        if (placeMatch) {
            try {
                title = decodeURIComponent(placeMatch[1].replace(/\+/g, " "));
            } catch {}
        } else if (html) {
            const titleTagMatch = html.match(/<title>(.*?)<\/title>/i);
            if (titleTagMatch) {
                const rawTitle = titleTagMatch[1]
                    .replace(/\s*-\s*Google\s*(Maps|地圖).*/i, "")
                    .replace(/\s*·\s*Google\s*(Maps|地圖).*/i, "")
                    .trim();
                if (rawTitle && !rawTitle.toLowerCase().includes("google maps")) {
                    title = rawTitle;
                }
            }
        }

        // E. 判斷類別
        let category: POICategory = "attraction";
        const lowerTitle = title.toLowerCase();
        if (/咖啡|cafe|coffee/.test(lowerTitle)) category = "cafe";
        else if (/餐廳|料理|麵|飯|鍋|食堂|food|restaurant|bar/.test(lowerTitle)) category = "food";
        else if (/飯店|酒店|旅館|hotel|hostel|inn/.test(lowerTitle)) category = "hotel";
        else if (/站|車站|station|airport|terminal/.test(lowerTitle)) category = "transport";
        else if (/商場|市場|百貨|shop|store|market/.test(lowerTitle)) category = "shopping";

        if (lat !== null && lng !== null && !isNaN(lat) && !isNaN(lng)) {
            places.push({
                title,
                lat,
                lng,
                address: cleanUrl,
                category,
            });
        }
    }

    return places;
}

// ── Next.js App Router Catch-All Route Handlers ───────────────────────────────

export async function GET(request: Request, context: { params: Promise<{ path: string[] }> }) {
    const { path } = await context.params;
    const userId = getUserId(request);
    const action = path[0];

    // GET /api/poi/all
    if (action === "all") {
        const items = GLOBAL_POI_MEMORY_STORE[userId] || [];
        return NextResponse.json(items);
    }

    return NextResponse.json({ error: "Endpoint not found" }, { status: 404 });
}

export async function POST(request: Request, context: { params: Promise<{ path: string[] }> }) {
    const { path } = await context.params;
    const userId = getUserId(request);
    const action = path[0];

    // POST /api/poi/import-link
    if (action === "import-link") {
        try {
            const body = await request.json().catch(() => ({}));
            const { url } = body;
            if (!url) {
                return NextResponse.json({ error: "缺少連結 URL" }, { status: 400 });
            }

            const extracted = await extractPlacesFromGoogleMaps(url);
            if (extracted.length === 0) {
                return NextResponse.json(
                    { error: "無法自此連結解析地點座標，請確認 Google 地圖連結是否正確" },
                    { status: 422 }
                );
            }

            const now = Date.now();
            const newPois: POIItem[] = extracted.map((p) => ({
                id: `poi_${crypto.randomUUID().slice(0, 12)}`,
                user_id: userId,
                title: p.title,
                address: p.address,
                lat: p.lat,
                lng: p.lng,
                google_place_id: null,
                category: p.category,
                rating: null,
                user_notes: "",
                source_url: url,
                is_pinned: false,
                pin_color: "#E56E25",
                created_at: now,
                updated_at: now,
            }));

            // 儲存於本機記憶體字典中
            const current = GLOBAL_POI_MEMORY_STORE[userId] || [];
            GLOBAL_POI_MEMORY_STORE[userId] = [...newPois, ...current];

            return NextResponse.json({
                success: true,
                count: newPois.length,
                items: newPois,
            });
        } catch (err: unknown) {
            console.error("[POI Import] Error:", err);
            return NextResponse.json(
                { error: err instanceof Error ? err.message : "解析地點時發生未知錯誤" },
                { status: 500 }
            );
        }
    }

    // POST /api/poi/add
    if (action === "add") {
        try {
            const dto = await request.json();
            const now = Date.now();
            const newItem: POIItem = {
                id: `poi_${crypto.randomUUID().slice(0, 12)}`,
                user_id: userId,
                title: dto.title,
                address: dto.address || dto.title,
                lat: dto.lat,
                lng: dto.lng,
                google_place_id: dto.google_place_id || null,
                category: dto.category || "attraction",
                rating: dto.rating || null,
                user_notes: dto.user_notes || "",
                source_url: dto.source_url || null,
                is_pinned: Boolean(dto.is_pinned),
                pin_color: dto.pin_color || "#E56E25",
                created_at: now,
                updated_at: now,
            };

            const current = GLOBAL_POI_MEMORY_STORE[userId] || [];
            GLOBAL_POI_MEMORY_STORE[userId] = [newItem, ...current];

            return NextResponse.json(newItem);
        } catch (err: unknown) {
            return NextResponse.json(
                { error: err instanceof Error ? err.message : "新增景點失敗" },
                { status: 500 }
            );
        }
    }

    return NextResponse.json({ error: "Endpoint not found" }, { status: 404 });
}

export async function PATCH(request: Request, context: { params: Promise<{ path: string[] }> }) {
    const { path } = await context.params;
    const userId = getUserId(request);
    const poiId = path[0];
    const subAction = path[1];

    const current = GLOBAL_POI_MEMORY_STORE[userId] || [];
    const item = current.find((p) => p.id === poiId);

    if (!item) {
        return NextResponse.json({ error: "景點未找到" }, { status: 404 });
    }

    const body = await request.json().catch(() => ({}));

    // PATCH /api/poi/:id/note
    if (subAction === "note") {
        item.user_notes = body.note || "";
        item.updated_at = Date.now();
        return NextResponse.json(item);
    }

    // PATCH /api/poi/:id/pin
    if (subAction === "pin") {
        item.is_pinned = Boolean(body.is_pinned);
        item.updated_at = Date.now();
        return NextResponse.json(item);
    }

    // PATCH /api/poi/:id/category
    if (subAction === "category") {
        const validCategories: POICategory[] = ["attraction", "food", "cafe", "shopping", "hotel", "transport", "other"];
        item.category = validCategories.includes(body.category) ? body.category : "attraction";
        item.updated_at = Date.now();
        return NextResponse.json(item);
    }

    return NextResponse.json({ error: "Endpoint not found" }, { status: 404 });
}

export async function DELETE(request: Request, context: { params: Promise<{ path: string[] }> }) {
    const { path } = await context.params;
    const userId = getUserId(request);
    const poiId = path[0];

    const current = GLOBAL_POI_MEMORY_STORE[userId] || [];
    GLOBAL_POI_MEMORY_STORE[userId] = current.filter((p) => p.id !== poiId);

    return NextResponse.json({ success: true });
}
