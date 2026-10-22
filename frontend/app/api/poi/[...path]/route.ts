import { NextRequest, NextResponse } from "next/server";

const CLOUDFLARE_D1_BASE = process.env.CLOUDFLARE_POI_SERVICE_URL || "https://tabijiapp.com/api/poi";
const BACKEND_BASE = (process.env.INTERNAL_BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8008").replace(/\/+$/, "") + "/api/poi";

/**
 * 🛡️ 雙模態同態路由分流器
 * - POI 口袋庫端點 (all, import-link, add, :id, :id/*) ➔ 100% 直連 Cloudflare D1
 * - POI AI 與搜尋端點 (categories, nearby, recommend, ai-enrich, enrich) ➔ 直連 FastAPI 後端
 */
function isPoiPoolSubpath(subPath: string): boolean {
    const actions = ["all", "import-link", "add", "batch-save"];
    if (actions.includes(subPath)) return true;
    return /^([0-9a-fA-F-]+|poi_[^/]+)(\/(note|pin|category))?$/.test(subPath);
}

async function proxyRequest(
    req: NextRequest,
    context: { params: Promise<{ path: string[] }> }
) {
    const { path } = await context.params;
    const subPath = path ? path.join("/") : "";
    const isPool = isPoiPoolSubpath(subPath);
    const targetBase = isPool ? CLOUDFLARE_D1_BASE : BACKEND_BASE;

    const incomingUrl = new URL(req.url);
    const targetUrl = new URL(`${targetBase}/${subPath}`);
    targetUrl.search = incomingUrl.search; // 🛡️ 完整保留所有 Query String 參數

    // 1. 深度清洗標頭：移除 Host 與連線限制標頭，防止 Cloudflare / Cloud Run 邊緣拒絕
    const headers = new Headers();
    req.headers.forEach((val, key) => {
        const lower = key.toLowerCase();
        if (!["host", "connection", "content-length"].includes(lower)) {
            headers.set(key, val);
        }
    });
    headers.set("Host", new URL(targetBase).host);

    // 2. 嚴格防禦 GET / HEAD 攜帶 Body 導致 Fetch TypeError
    const method = req.method.toUpperCase();
    const isBodyAllowed = !["GET", "HEAD"].includes(method);
    const body = isBodyAllowed ? await req.blob() : undefined;

    try {
        const resp = await fetch(targetUrl.toString(), {
            method,
            headers,
            body,
            redirect: "manual",
        });

        // 🛡️ 本地開發與測試環境優雅降級：若遠端 D1 判定為測試固定帳號或拒絕存取，
        // GET /api/poi/all 優雅回傳空陣列 []，防止本地 App Session Token 遭到非預期清除
        if (resp.status === 401 && isPool && subPath === "all" && method === "GET") {
            return NextResponse.json([]);
        }

        const respHeaders = new Headers(resp.headers);
        respHeaders.delete("content-encoding"); // 避免代理雙重壓縮損壞

        return new NextResponse(resp.body, {
            status: resp.status,
            statusText: resp.statusText,
            headers: respHeaders,
        });
    } catch (err) {
        if (isPool && subPath === "all" && method === "GET") {
            return NextResponse.json([]);
        }
        console.error(`[POI Proxy] Failed to reach ${isPool ? "Cloudflare D1" : "Backend"}:`, err);
        return NextResponse.json(
            { error: "POI_SERVICE_UNREACHABLE", detail: String(err) },
            { status: 502 }
        );
    }
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
export const OPTIONS = proxyRequest;
