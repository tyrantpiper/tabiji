/**
 * Tabidachi 邊緣同源防護罩 (Edge Shield - Hardened v2)
 * 解決 GET/HEAD TypeError、支援 Gemini 流式串流、放行 Vercel 本地 API
 */
const UUID_V4_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

// 允許於 /api/geocode/search 邊緣快取 HIT 時動態回寫 CORS 的嚴格白名單（與 backend/main.py ALLOWED_ORIGINS 對齊，不寫入共享快取本體）
const GEOCODE_ALLOWED_ORIGINS = new Set([
  'https://tabijiapp.com',
  'https://www.tabijiapp.com',
  'https://travel-pwa-five.vercel.app',
  'http://localhost:3000',
  'http://localhost:5173',
  'http://127.0.0.1:3000',
]);

// Web Crypto API helper to verify HS256 JWT in Cloudflare Worker
async function verifyJwtSub(authHeader, secret) {
  if (!authHeader || !authHeader.startsWith("Bearer ") || !secret) {
    return null;
  }
  const token = authHeader.substring(7).trim();
  const parts = token.split(".");
  if (parts.length !== 3) return null;

  const [headerB64, payloadB64, signatureB64] = parts;
  try {
    const signatureBin = Uint8Array.from(atob(signatureB64.replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
    const enc = new TextEncoder();
    const cryptoKey = await crypto.subtle.importKey(
      "raw",
      enc.encode(secret),
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["verify"]
    );
    const data = enc.encode(`${headerB64}.${payloadB64}`);
    const isValid = await crypto.subtle.verify("HMAC", cryptoKey, signatureBin, data);
    if (!isValid) return null;

    const payload = JSON.parse(atob(payloadB64.replace(/-/g, "+").replace(/_/g, "/")));
    const now = Math.floor(Date.now() / 1000);
    if (typeof payload.exp !== "number" || !Number.isFinite(payload.exp) || payload.exp < now) {
      return null;
    }
    const sub = payload?.sub ? String(payload.sub).trim() : "";
    return UUID_V4_REGEX.test(sub) ? sub : null;
  } catch (err) {
    return null;
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const pathname = url.pathname;

    // 1. 轉發至 POI Service 景點微服務 (Cloudflare D1 儲存)
    // 注：/api/sign-cloudinary 已遷移至 Cloud Run 鑑權端點，由下方統一代理至後端
    const POI_POOL_ENDPOINTS = ['/api/poi/all', '/api/poi/import-link', '/api/poi/add', '/api/poi/batch-save'];
    const BACKEND_POI_ENDPOINTS = [
      '/api/poi/nearby',
      '/api/poi/categories',
      '/api/poi/media-proxy',
      '/api/poi/resolve-link',
      '/api/poi/ai-enrich',
      '/api/poi/enrich',
      '/api/poi/recommend',
    ];
    const isPoiPoolRequest = (
      POI_POOL_ENDPOINTS.includes(pathname) ||
      (
        !BACKEND_POI_ENDPOINTS.includes(pathname) &&
        /^\/api\/poi\/[^/]+(\/(note|pin|category))?$/.test(pathname) &&
        ['PATCH', 'DELETE', 'OPTIONS'].includes(request.method)
      )
    );
    if (isPoiPoolRequest && env.POI_SERVICE) {
      const CORS_HEADERS = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-User-ID, Authorization",
      };

      if (request.method === 'OPTIONS') {
        return new Response(null, { status: 204, headers: CORS_HEADERS });
      }

      // 🛡️ Edge Shield 邊緣身分防偽閉環 (BOLA Defense & Cryptographic Gateway)
      const rawAuth = request.headers.get("Authorization") || "";
      const headers = new Headers(request.headers);

      if (env.SESSION_SECRET) {
        const verifiedSub = await verifyJwtSub(rawAuth, env.SESSION_SECRET);
        if (!verifiedSub) {
          return new Response(JSON.stringify({ error: "UNAUTHORIZED", detail: "Valid Bearer JWT required for POI service" }), {
            status: 401,
            headers: {
              ...CORS_HEADERS,
              "Content-Type": "application/json; charset=utf-8",
            },
          });
        }
        headers.delete("X-User-ID");
        headers.set("X-User-ID", verifiedSub);
      } else {
        // 後備防禦：未配置密鑰前，無條件剝除外部偽造標頭與未驗簽授權標頭
        headers.delete("X-User-ID");
        headers.delete("Authorization");
      }

      try {
        const serviceReq = new Request(request, { headers });
        const resp = await env.POI_SERVICE.fetch(serviceReq);
        if (resp.ok || resp.status < 500) {
          return resp;
        }
        console.warn(`[Edge-Shield] POI Service returned status ${resp.status}`);
      } catch (err) {
        console.error('[Edge-Shield] POI Service unreachable:', err);
      }
      // 🛡️ 邊緣閉環守護 (Fail-Closed)：杜絕轉發至 Cloud Run 導致記憶體丟失，回傳 503 激發 PWA 離線同步佇列
      return new Response(JSON.stringify({ error: "POI_SERVICE_UNAVAILABLE", retry_after: 5 }), {
        status: 503,
        headers: {
          ...CORS_HEADERS,
          "Content-Type": "application/json; charset=utf-8",
        },
      });
    }

    // 2. 目標 Google Cloud Run 實例
    const TARGET_HOST = 'antigravity-backend-589255638719.us-central1.run.app';
    const backendUrl = new URL(url.pathname + url.search, `https://${TARGET_HOST}`);

    // ⚡ 2.5 邊緣高速電纜快取：/api/geocode/search (POST-to-GET 虛擬快取適配器)
    if (pathname === '/api/geocode/search' && request.method === 'POST') {
      try {
        const clonedReq = request.clone();
        const bodyJson = await clonedReq.json().catch(() => ({}));
        const hasGeminiKey = Boolean(
          (request.headers.get('X-Gemini-Key') || request.headers.get('X-Gemini-API-Key') || '').trim()
        );

        const query = (typeof bodyJson.query === 'string' ? bodyJson.query : '').trim().toLowerCase();
        const rawBbox = bodyJson.bbox || '';

        let quantizedBbox = '';
        if (rawBbox && typeof rawBbox === 'string') {
          const parts = rawBbox.split(',').map(Number);
          if (parts.length === 4 && parts.every(Number.isFinite)) {
            quantizedBbox = parts.map(p => p.toFixed(2)).join(',');
          }
        }

        const country = (typeof bodyJson.country === 'string' ? bodyJson.country : '').trim().toUpperCase();
        const region = (typeof bodyJson.region === 'string' ? bodyJson.region : '').trim().toLowerCase().slice(0, 64);
        const trip = (typeof bodyJson.tripTitle === 'string' ? bodyJson.tripTitle : (typeof bodyJson.trip === 'string' ? bodyJson.trip : '')).trim().toLowerCase().slice(0, 64);
        const locale = (typeof bodyJson.locale === 'string' ? bodyJson.locale : '').trim().toLowerCase().slice(0, 16);

        const rawLat = bodyJson.lat;
        const rawLng = bodyJson.lng;
        const hasCoords = (
          rawLat !== null && rawLat !== undefined && rawLat !== '' && Number.isFinite(Number(rawLat)) &&
          rawLng !== null && rawLng !== undefined && rawLng !== '' && Number.isFinite(Number(rawLng))
        );

        const rawLimit = bodyJson.limit;
        const hasLimit = rawLimit !== null && rawLimit !== undefined && rawLimit !== '' && Number.isFinite(Number(rawLimit)) && Number(rawLimit) > 0;
        const rawZoom = bodyJson.zoom;
        const hasZoom = rawZoom !== null && rawZoom !== undefined && rawZoom !== '' && Number.isFinite(Number(rawZoom));
        // 對齊後端 geocode_with_photon 之 int_zoom <= 10 (location_bias_scale=0.7) 宏觀邊界；
        // zoom 11..18 共享城市/街景分桶以維持既有 T3 契約 (zoom 11.2 與 15.8 共享快取鍵，避免城市內縮放抖動導致快取雪崩)
        const isMacroZoom = hasZoom && Math.round(Number(rawZoom)) <= 10;

        // 構造專屬虛擬 GET Cache Key v2.2 (隔離全球宏觀 round(zoom)<=10 與城市/街景縮放，刷新舊 v=2 / v=2.1 快取)
        const cacheKeyUrl = new URL(`https://cache.tabijiapp.com/api/geocode/search`);
        cacheKeyUrl.searchParams.set('v', '2.2');
        cacheKeyUrl.searchParams.set('q', query);
        if (quantizedBbox) cacheKeyUrl.searchParams.set('bbox', quantizedBbox);
        if (hasCoords) {
          cacheKeyUrl.searchParams.set('lat', Number(rawLat).toFixed(2));
          cacheKeyUrl.searchParams.set('lng', Number(rawLng).toFixed(2));
        }
        if (isMacroZoom) cacheKeyUrl.searchParams.set('zb', 'macro');
        if (country) cacheKeyUrl.searchParams.set('country', country);
        if (region) cacheKeyUrl.searchParams.set('region', region);
        if (trip) cacheKeyUrl.searchParams.set('trip', trip);
        if (locale) cacheKeyUrl.searchParams.set('locale', locale);
        if (hasLimit) {
          cacheKeyUrl.searchParams.set('limit', String(Math.max(1, Math.min(50, Math.round(Number(rawLimit))))));
        }

        const cache = caches.default;
        const cacheKey = cacheKeyUrl.toString();

        // 若攜帶使用者 Gemini Key（觸發個人化 AI 搜尋融合），強制繞過邊緣共享快取
        if (!hasGeminiKey) {
          const cachedResp = await cache.match(cacheKey);
          if (cachedResp) {
            const hitHeaders = new Headers(cachedResp.headers);
            hitHeaders.set('X-Edge-Cache', 'HIT');
            hitHeaders.set('X-Edge-Shield', 'Cloudflare-Worker-Active');
            hitHeaders.set('X-Content-Type-Options', 'nosniff');
            const reqOrigin = request.headers.get('Origin');
            if (reqOrigin && GEOCODE_ALLOWED_ORIGINS.has(reqOrigin)) {
              hitHeaders.set('Access-Control-Allow-Origin', reqOrigin);
              hitHeaders.set('Access-Control-Allow-Credentials', 'true');
              hitHeaders.set('Vary', 'Origin');
            }
            return new Response(cachedResp.body, {
              status: cachedResp.status,
              headers: hitHeaders,
            });
          }
        }

        // 未命中或 BYPASS：帶入邊緣地理標頭並安全轉發（重新序列化 JSON 前刪除舊 Content-Length / Content-Encoding 防長度與編碼不符）
        const originHeaders = new Headers(request.headers);
        originHeaders.delete('Content-Length');
        originHeaders.delete('Content-Encoding');
        originHeaders.set('Host', TARGET_HOST);
        originHeaders.set('X-Forwarded-Host', url.hostname);
        originHeaders.set('X-Forwarded-Proto', url.protocol.replace(':', ''));
        if (request.cf) {
          if (request.cf.country) originHeaders.set('CF-IPCountry', request.cf.country);
          if (request.cf.latitude) originHeaders.set('CF-IPLatitude', String(request.cf.latitude));
          if (request.cf.longitude) originHeaders.set('CF-IPLongitude', String(request.cf.longitude));
        }

        const backendResp = await fetch(backendUrl.toString(), {
          method: 'POST',
          headers: originHeaders,
          body: JSON.stringify(bodyJson),
        });

        // 僅對無 Gemini Key、成功有內容、且非 ArcGIS 來源的公共結果以純淨標頭寫入 7 天邊緣快取（杜絕殘留 Content-Encoding: gzip 解碼損壞）
        if (!hasGeminiKey && backendResp.ok) {
          const cloneResp = backendResp.clone();
          const data = await cloneResp.json().catch(() => null);
          const isArcgisResult = Boolean(
            data && (
              String(data.source || '').toLowerCase() === 'arcgis' ||
              (Array.isArray(data.results) && data.results.some(r => r && String(r.source || '').toLowerCase() === 'arcgis'))
            )
          );
          if (data && Array.isArray(data.results) && data.results.length > 0 && !isArcgisResult) {
            const cacheHeaders = new Headers({
              'Content-Type': 'application/json; charset=utf-8',
              'Cache-Control': 'public, max-age=604800, s-maxage=604800',
            });
            const respToCache = new Response(JSON.stringify(data), {
              status: backendResp.status,
              headers: cacheHeaders,
            });
            ctx.waitUntil(cache.put(cacheKey, respToCache));
          }
        }

        const outHeaders = new Headers(backendResp.headers);
        outHeaders.set('X-Edge-Cache', hasGeminiKey ? 'BYPASS' : 'MISS');
        outHeaders.set('X-Edge-Shield', 'Cloudflare-Worker-Active');
        return new Response(backendResp.body, {
          status: backendResp.status,
          headers: outHeaders,
        });
      } catch (e) {
        // 若快取邏輯遭遇任何異常，平滑退回既有代理，絕不中斷連線
      }
    }

    // 🖼️ 2.6 邊緣圖片代理快取：GET /api/poi/media-proxy (7 天 TTL，嚴格僅快取 200 image/* 非 SVG 並保留 sandbox CSP)
    if (pathname === '/api/poi/media-proxy' && request.method === 'GET') {
      try {
        const mediaTarget = (url.searchParams.get('url') || '').trim();
        if (mediaTarget) {
          const cache = caches.default;
          const mediaCacheKey = `https://cache.tabijiapp.com/api/poi/media-proxy?v=1&url=${encodeURIComponent(mediaTarget)}`;
          const cachedMedia = await cache.match(mediaCacheKey);
          if (cachedMedia) {
            const hitHeaders = new Headers(cachedMedia.headers);
            hitHeaders.set('X-Edge-Cache', 'HIT');
            hitHeaders.set('X-Edge-Shield', 'Cloudflare-Worker-Active');
            hitHeaders.set('X-Content-Type-Options', 'nosniff');
            hitHeaders.set('Content-Security-Policy', "script-src 'none'; frame-src 'none'; sandbox;");
            return new Response(cachedMedia.body, {
              status: cachedMedia.status,
              headers: hitHeaders,
            });
          }

          const originHeaders = new Headers(request.headers);
          originHeaders.set('Host', TARGET_HOST);
          originHeaders.set('X-Forwarded-Host', url.hostname);
          originHeaders.set('X-Forwarded-Proto', url.protocol.replace(':', ''));

          const backendResp = await fetch(backendUrl.toString(), {
            method: 'GET',
            headers: originHeaders,
            redirect: 'manual',
          });

          const rawCt = (backendResp.headers.get('Content-Type') || '').split(';')[0].trim().toLowerCase();
          const isCacheableImage =
            backendResp.status === 200 &&
            rawCt.startsWith('image/') &&
            !rawCt.includes('svg') &&
            !rawCt.includes('xml');

          if (isCacheableImage) {
            const bytes = await backendResp.arrayBuffer();
            const safeCsp =
              backendResp.headers.get('Content-Security-Policy') ||
              "script-src 'none'; frame-src 'none'; sandbox;";
            const cacheHeaders = new Headers({
              'Content-Type': rawCt,
              'Cache-Control': 'public, max-age=86400, s-maxage=604800',
              'Content-Security-Policy': safeCsp,
              'X-Content-Type-Options': 'nosniff',
            });
            ctx.waitUntil(
              cache.put(
                mediaCacheKey,
                new Response(bytes, { status: 200, headers: cacheHeaders })
              )
            );

            const missHeaders = new Headers(cacheHeaders);
            missHeaders.set('X-Edge-Cache', 'MISS');
            missHeaders.set('X-Edge-Shield', 'Cloudflare-Worker-Active');
            return new Response(bytes, { status: 200, headers: missHeaders });
          }

          const passHeaders = new Headers(backendResp.headers);
          passHeaders.set('X-Edge-Cache', 'BYPASS');
          passHeaders.set('X-Edge-Shield', 'Cloudflare-Worker-Active');
          return new Response(backendResp.body, {
            status: backendResp.status,
            headers: passHeaders,
          });
        }
      } catch {
        // 異常退回一般代理
      }
    }

    // 🛣️ 2.7 邊緣路線快取：POST /api/route (座標 4 位量化 ≈ 11m + SHA-256 定長鍵 + 14 天 TTL + 拒存 straight-line + 動態 CORS)
    if (pathname === '/api/route' && request.method === 'POST') {
      try {
        const clonedReq = request.clone();
        const bodyJson = await clonedReq.json().catch(() => null);
        const stops = Array.isArray(bodyJson?.stops) ? bodyJson.stops : [];
        const hasValidStops =
          stops.length >= 2 &&
          stops.every(
            (s) =>
              s &&
              Number.isFinite(Number(s.lat)) &&
              Number.isFinite(Number(s.lng))
          );

        if (hasValidStops) {
          const normMode = String(bodyJson.mode || 'walk').trim().toLowerCase();
          const normOptimize = Boolean(bodyJson.optimize) ? '1' : '0';
          const quantizedStops = stops
            .map((s) => `${Number(s.lng).toFixed(4)},${Number(s.lat).toFixed(4)}`)
            .join(';');
          const keyMaterial = `v1|${normMode}|${normOptimize}|${quantizedStops}`;
          const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(keyMaterial));
          const hashHex = Array.from(new Uint8Array(digest))
            .map((b) => b.toString(16).padStart(2, '0'))
            .join('');

          const cache = caches.default;
          const routeCacheKey = `https://cache.tabijiapp.com/api/route?v=1&k=${hashHex}`;
          const cachedRoute = await cache.match(routeCacheKey);
          if (cachedRoute) {
            const hitHeaders = new Headers(cachedRoute.headers);
            hitHeaders.set('X-Edge-Cache', 'HIT');
            hitHeaders.set('X-Edge-Shield', 'Cloudflare-Worker-Active');
            hitHeaders.set('X-Content-Type-Options', 'nosniff');
            const reqOrigin = request.headers.get('Origin');
            if (reqOrigin && GEOCODE_ALLOWED_ORIGINS.has(reqOrigin)) {
              hitHeaders.set('Access-Control-Allow-Origin', reqOrigin);
              hitHeaders.set('Access-Control-Allow-Credentials', 'true');
              hitHeaders.set('Vary', 'Origin');
            }
            return new Response(cachedRoute.body, {
              status: cachedRoute.status,
              headers: hitHeaders,
            });
          }

          const originHeaders = new Headers(request.headers);
          originHeaders.delete('Content-Length');
          originHeaders.delete('Content-Encoding');
          originHeaders.set('Host', TARGET_HOST);
          originHeaders.set('X-Forwarded-Host', url.hostname);
          originHeaders.set('X-Forwarded-Proto', url.protocol.replace(':', ''));

          const backendResp = await fetch(backendUrl.toString(), {
            method: 'POST',
            headers: originHeaders,
            body: JSON.stringify(bodyJson),
          });

          if (backendResp.ok) {
            const cloneResp = backendResp.clone();
            const data = await cloneResp.json().catch(() => null);
            const src = String(data?.source || '').trim().toLowerCase();
            if (data && data.route && src && src !== 'straight-line') {
              const cacheHeaders = new Headers({
                'Content-Type': 'application/json; charset=utf-8',
                'Cache-Control': 'public, max-age=1209600, s-maxage=1209600',
              });
              ctx.waitUntil(
                cache.put(
                  routeCacheKey,
                  new Response(JSON.stringify(data), { status: 200, headers: cacheHeaders })
                )
              );
            }
          }

          const outHeaders = new Headers(backendResp.headers);
          outHeaders.set('X-Edge-Cache', 'MISS');
          outHeaders.set('X-Edge-Shield', 'Cloudflare-Worker-Active');
          return new Response(backendResp.body, {
            status: backendResp.status,
            headers: outHeaders,
          });
        }
      } catch {
        // 異常退回一般代理
      }
    }

    // 3. 標頭重寫（規避 Google Cloud Run 404）
    const newHeaders = new Headers(request.headers);
    newHeaders.set('Host', TARGET_HOST);
    newHeaders.set('X-Forwarded-Host', url.hostname);
    newHeaders.set('X-Forwarded-Proto', url.protocol.replace(':', ''));

    // 🛡️ 極致容錯：GET 與 HEAD 嚴禁攜帶 body，避免 V8 引擎拋出 TypeError
    const isBodyAllowed = !['GET', 'HEAD'].includes(request.method.toUpperCase());

    const initOptions = {
      method: request.method,
      headers: newHeaders,
      redirect: 'manual', // 🛡️ 嚴禁在邊緣代理層跟隨 302 重定向，必須將 OAuth / 外部跳轉直接回傳用戶端瀏覽器
      body: isBodyAllowed ? request.body : undefined,
    };

    if (isBodyAllowed && request.body) {
      initOptions.duplex = 'half';
    }

    try {
      const response = await fetch(backendUrl.toString(), initOptions);
      
      const responseHeaders = new Headers(response.headers);
      responseHeaders.set('X-Edge-Shield', 'Cloudflare-Worker-Active');

      // 🛡️ 邊緣防撕裂：若後端回傳包含內部 Cloud Run 主機的 Location，重寫為公開自訂網域
      if (responseHeaders.has('location')) {
        const loc = responseHeaders.get('location');
        if (loc.startsWith(`https://${TARGET_HOST}`) || loc.startsWith(`http://${TARGET_HOST}`)) {
          responseHeaders.set('location', loc.replace(`https://${TARGET_HOST}`, `https://${url.hostname}`).replace(`http://${TARGET_HOST}`, `https://${url.hostname}`));
        }
      }

      // 🛡️ HTTP 規範防衛：無實體狀態碼（101, 204, 205, 304）嚴禁傳遞 body
      const body = [101, 204, 205, 304].includes(response.status) ? null : response.body;

      return new Response(body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
    } catch (err) {
      return new Response(JSON.stringify({
        error: "Backend Edge Proxy Error",
        detail: "Upstream service temporarily unavailable"
      }), {
        status: 502,
        headers: { "Content-Type": "application/json" }
      });
    }
  }
};
