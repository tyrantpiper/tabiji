/**
 * Tabidachi 邊緣同源防護罩 (Edge Shield - Hardened v2)
 * 解決 GET/HEAD TypeError、支援 Gemini 流式串流、放行 Vercel 本地 API
 */
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const pathname = url.pathname;

    // 1. 放行 Vercel 本地處理的 API（如 Cloudinary 收據簽章與本地路由）
    if (pathname.startsWith('/api/sign-cloudinary') || pathname.startsWith('/api/parse-receipt')) {
      return fetch(request);
    }

    // 2. 目標 Google Cloud Run 實例
    const TARGET_HOST = 'antigravity-backend-589255638719.us-central1.run.app';
    const backendUrl = new URL(url.pathname + url.search, `https://${TARGET_HOST}`);

    // ⚡ 2.5 邊緣高速電纜快取：/api/geocode/search (POST-to-GET 虛擬快取適配器)
    if (pathname === '/api/geocode/search' && request.method === 'POST') {
      try {
        const clonedReq = request.clone();
        const bodyJson = await clonedReq.json().catch(() => ({}));
        const query = (bodyJson.query || '').trim().toLowerCase();
        const rawBbox = bodyJson.bbox || '';

        let quantizedBbox = '';
        if (rawBbox && typeof rawBbox === 'string') {
          const parts = rawBbox.split(',').map(Number);
          if (parts.length === 4 && parts.every(Number.isFinite)) {
            quantizedBbox = parts.map(p => p.toFixed(2)).join(',');
          }
        }

        const country = (bodyJson.country || '').trim().toUpperCase();

        // 構造專屬虛擬 GET Cache Key (100% 符合 Cloudflare 官方 Cache API 限制)
        const cacheKeyUrl = new URL(`https://cache.tabijiapp.com/api/geocode/search`);
        cacheKeyUrl.searchParams.set('q', query);
        if (quantizedBbox) cacheKeyUrl.searchParams.set('bbox', quantizedBbox);
        if (country) cacheKeyUrl.searchParams.set('country', country);

        const cache = caches.default;
        const cacheKey = cacheKeyUrl.toString();

        // 嘗試讀取邊緣快取 (0ms 跨洲直出)
        const cachedResp = await cache.match(cacheKey);
        if (cachedResp) {
          const hitHeaders = new Headers(cachedResp.headers);
          hitHeaders.set('X-Edge-Cache', 'HIT');
          hitHeaders.set('X-Edge-Shield', 'Cloudflare-Worker-Active');
          return new Response(cachedResp.body, {
            status: cachedResp.status,
            headers: hitHeaders,
          });
        }

        // 未命中：帶入邊緣地理標頭並安全轉發（使用 JSON.stringify 避免消耗原始 Stream）
        const originHeaders = new Headers(request.headers);
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

        // 僅對成功且具有內容的結果寫入 7 天邊緣快取
        if (backendResp.ok) {
          const cloneResp = backendResp.clone();
          const data = await cloneResp.json().catch(() => null);
          if (data && Array.isArray(data.results) && data.results.length > 0) {
            const cacheHeaders = new Headers(backendResp.headers);
            cacheHeaders.set('Cache-Control', 'public, max-age=604800, s-maxage=604800');
            const respToCache = new Response(JSON.stringify(data), {
              status: backendResp.status,
              headers: cacheHeaders,
            });
            ctx.waitUntil(cache.put(cacheKey, respToCache));
          }
        }

        const outHeaders = new Headers(backendResp.headers);
        outHeaders.set('X-Edge-Cache', 'MISS');
        outHeaders.set('X-Edge-Shield', 'Cloudflare-Worker-Active');
        return new Response(backendResp.body, {
          status: backendResp.status,
          headers: outHeaders,
        });
      } catch (e) {
        // 若快取邏輯遭遇任何異常，平滑退回既有代理，絕不中斷連線
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
      redirect: 'follow',
      body: isBodyAllowed ? request.body : undefined,
    };

    if (isBodyAllowed && request.body) {
      initOptions.duplex = 'half';
    }

    try {
      const response = await fetch(backendUrl.toString(), initOptions);
      
      const responseHeaders = new Headers(response.headers);
      responseHeaders.set('X-Edge-Shield', 'Cloudflare-Worker-Active');

      return new Response(response.body, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
    } catch (err) {
      return new Response(JSON.stringify({
        error: "Backend Edge Proxy Error",
        detail: err.message
      }), {
        status: 502,
        headers: { "Content-Type": "application/json" }
      });
    }
  }
};
