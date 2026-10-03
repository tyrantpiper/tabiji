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
