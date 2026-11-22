/**
 * Cloudflare Worker: cloudinary-proxy
 *
 * 職責：
 * 1. Cloudinary 圖片邊緣代理與格式最佳化 (WebP / AVIF) + c_limit 防放大
 * 2. 嚴格路徑白名單與防盜鏈保護 (new URL() 精確主機名稱比對，同時相容 iOS Standalone PWA)
 * 3. 安全邊緣快取 (按格式隔離 Cache Key、剝除上游 cdn-cache-control / vary / x-cld-error，僅快取 GET 200 image/*)
 * 4. 注入 Access-Control-Allow-Origin: *，支援 HTML5 Canvas (html2canvas / PDF 匯出)
 */

const DEFAULT_CLOUDINARY_CLOUD_NAME = 'dnpcnwrcu';
const ALLOWED_WIDTHS = new Set(['320', '640', '768', '1024', '1280']);
const ALLOWED_EXACT_HOSTS = new Set([
  'travel-pwa-five.vercel.app',
  'tabijiapp.com',
  'www.tabijiapp.com',
  'localhost',
  '127.0.0.1',
]);
const ALLOWED_VERCEL_PREVIEW_HOST_RE = /^travel-[a-z0-9-]+-tyrantpipers-projects\.vercel\.app$/;
const STRICT_PROXY_PATH_RE = /^\/w_(320|640|768|1024|1280)\/(v\d+\/[a-zA-Z0-9_./-]+)$/;
const WIDTH_PREFIX_RE = /^\/w_(\d+)\//;

const STRIP_UPSTREAM_HEADERS = [
  'cdn-cache-control',
  'cloudflare-cdn-cache-control',
  'vary',
  'set-cookie',
  'x-cld-error',
  'access-control-expose-headers',
  'server-timing',
];

export function prefersAvif(rawAcceptHeader) {
  if (!rawAcceptHeader || typeof rawAcceptHeader !== 'string') return false;
  const parts = rawAcceptHeader.toLowerCase().split(',');
  for (const part of parts) {
    const tokens = part.trim().split(';');
    if (tokens[0]?.trim() !== 'image/avif') continue;
    let q = 1;
    for (let i = 1; i < tokens.length; i += 1) {
      const [k, v] = tokens[i].split('=');
      if (k?.trim() === 'q' && v !== undefined) {
        const parsed = Number.parseFloat(v.trim());
        if (!Number.isNaN(parsed)) q = parsed;
      }
    }
    if (q > 0) return true;
  }
  return false;
}

export function resolveCloudName(env) {
  const configured = typeof env?.CLOUDINARY_CLOUD_NAME === 'string' ? env.CLOUDINARY_CLOUD_NAME.trim() : '';
  return configured && !configured.includes('REDACTED') ? configured : DEFAULT_CLOUDINARY_CLOUD_NAME;
}

function isAllowedOriginUrl(rawHeaderValue) {
  if (!rawHeaderValue || typeof rawHeaderValue !== 'string') return false;
  try {
    const parsed = new URL(rawHeaderValue.trim());
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
      return false;
    }
    const host = parsed.hostname.toLowerCase();
    return ALLOWED_EXACT_HOSTS.has(host) || ALLOWED_VERCEL_PREVIEW_HOST_RE.test(host);
  } catch {
    return false;
  }
}

export function isOriginAllowed(referer, origin) {
  const cleanReferer = typeof referer === 'string' ? referer.trim() : '';
  const cleanOrigin = typeof origin === 'string' ? origin.trim() : '';

  // iOS Standalone PWA / privacy mode may omit both Referer and Origin
  if (!cleanReferer && !cleanOrigin) {
    return true;
  }
  if (cleanOrigin && !isAllowedOriginUrl(cleanOrigin)) {
    return false;
  }
  if (cleanReferer && !isAllowedOriginUrl(cleanReferer)) {
    return false;
  }
  return true;
}

export function parseProxyPath(rawPathname) {
  if (!rawPathname || typeof rawPathname !== 'string') {
    return { ok: false, status: 400, reason: 'Invalid path' };
  }

  // Block encoded traversal, dot-dot segments, double slashes, transform commas/colons, control chars
  if (
    rawPathname.includes('%') ||
    rawPathname.includes('..') ||
    rawPathname.includes('//') ||
    rawPathname.includes(',') ||
    rawPathname.includes(':') ||
    rawPathname.includes('\\')
  ) {
    return { ok: false, status: 400, reason: 'Forbidden path syntax' };
  }

  const widthPrefixMatch = rawPathname.match(WIDTH_PREFIX_RE);
  if (widthPrefixMatch && !ALLOWED_WIDTHS.has(widthPrefixMatch[1])) {
    return { ok: false, status: 403, reason: 'Forbidden: Invalid Image Width' };
  }

  const strictMatch = rawPathname.match(STRICT_PROXY_PATH_RE);
  if (!strictMatch) {
    return { ok: false, status: 400, reason: 'Invalid image proxy path' };
  }

  const width = strictMatch[1];
  const assetPath = strictMatch[2];
  const segments = assetPath.split('/');
  if (segments.some((seg) => !seg || seg === '.' || seg === '..' || seg.startsWith('.'))) {
    return { ok: false, status: 400, reason: 'Forbidden path segment' };
  }

  return { ok: true, width, assetPath };
}

function makeNoStoreResponse(body, status, extraHeaders = {}) {
  return new Response(body, {
    status,
    headers: {
      'Cache-Control': 'no-store',
      'Access-Control-Allow-Origin': '*',
      ...extraHeaders,
    },
  });
}

export default {
  async fetch(request, env, ctx) {
    const method = (request.method || 'GET').toUpperCase();

    // 1. CORS Preflight (OPTIONS)
    if (method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
          'Access-Control-Allow-Headers': '*',
          'Access-Control-Max-Age': '86400',
          'Cache-Control': 'no-store',
        },
      });
    }

    // 2. Method allowlist: only GET / HEAD permitted
    if (method !== 'GET' && method !== 'HEAD') {
      return makeNoStoreResponse('Method Not Allowed', 405, {
        Allow: 'GET, HEAD, OPTIONS',
      });
    }

    const url = new URL(request.url);
    const acceptHeader = (request.headers.get('Accept') || '').toLowerCase();
    const referer = request.headers.get('Referer') || '';
    const origin = request.headers.get('Origin') || '';

    // 3. Anti-hotlink strict hostname validation
    if (!isOriginAllowed(referer, origin)) {
      return makeNoStoreResponse('Forbidden: Invalid Referer or Origin', 403);
    }

    // 4. Strict path & width allowlist validation (blocks transform injection & traversal)
    const parsedPath = parseProxyPath(url.pathname);
    if (!parsedPath.ok) {
      return makeNoStoreResponse(parsedPath.reason, parsedPath.status);
    }

    // 5. Negotiate format (respecting q=0) and isolate Cache Key by format
    const format = prefersAvif(acceptHeader) ? 'f_avif' : 'f_webp';
    const cache = typeof caches !== 'undefined' ? caches.default : null;
    const cacheKeyUrl = new URL(`${url.origin}${url.pathname}`);
    cacheKeyUrl.searchParams.set('fmt', format);
    const cacheKey = new Request(cacheKeyUrl.toString(), { method: 'GET' });

    if (cache && method === 'GET') {
      const cached = await cache.match(cacheKey);
      if (cached) {
        const cachedResponse = new Response(cached.body, cached);
        cachedResponse.headers.set('Access-Control-Allow-Origin', '*');
        return cachedResponse;
      }
    }

    // 6. Upstream fetch to Cloudinary with c_limit, resolved cloud name, and canonical Accept header
    const cloudName = resolveCloudName(env);
    const optimizationParams = `w_${parsedPath.width},c_limit,${format},q_auto`;
    const cloudinaryUrl = `https://res.cloudinary.com/${cloudName}/image/upload/${optimizationParams}/${parsedPath.assetPath}`;
    const canonicalAccept = format === 'f_avif' ? 'image/avif,image/webp,*/*' : 'image/webp,*/*';

    let upstreamResponse;
    try {
      upstreamResponse = await fetch(cloudinaryUrl, {
        method,
        headers: {
          Accept: canonicalAccept,
        },
      });
    } catch {
      return makeNoStoreResponse('Bad Gateway: Upstream image fetch failed', 502);
    }

    // 7. Rebuild headers, stripping upstream cache-poisoning/debug headers
    const headers = new Headers(upstreamResponse.headers);
    for (const h of STRIP_UPSTREAM_HEADERS) {
      headers.delete(h);
    }
    headers.set('Access-Control-Allow-Origin', '*');
    headers.set('X-Content-Type-Options', 'nosniff');

    const contentType = (headers.get('content-type') || '').trim().toLowerCase();
    // Never serve or cache SVG or non-image 200 payloads on the proxy origin (prevents Stored SVG/HTML XSS)
    if (
      contentType.startsWith('image/svg') ||
      (upstreamResponse.status === 200 && !contentType.startsWith('image/'))
    ) {
      return makeNoStoreResponse('Unsupported Media Type', 415, {
        'Content-Security-Policy': 'sandbox',
        'X-Content-Type-Options': 'nosniff',
      });
    }

    const isValidImage200 = upstreamResponse.status === 200 && contentType.startsWith('image/');

    if (isValidImage200) {
      headers.set('Cache-Control', 'public, s-maxage=31536000, max-age=31536000, immutable');
    } else {
      headers.set('Cache-Control', 'no-store');
      headers.set('Content-Security-Policy', 'sandbox');
    }

    const finalResponse = new Response(method === 'HEAD' ? null : upstreamResponse.body, {
      status: upstreamResponse.status,
      statusText: upstreamResponse.statusText,
      headers,
    });

    if (cache && method === 'GET' && isValidImage200) {
      const putPromise = cache.put(cacheKey, finalResponse.clone());
      if (ctx && typeof ctx.waitUntil === 'function') {
        ctx.waitUntil(putPromise);
      } else {
        await putPromise;
      }
    }

    return finalResponse;
  },
};
