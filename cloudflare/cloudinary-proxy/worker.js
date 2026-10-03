/**
 * Cloudflare Worker: cloudinary-proxy
 * 
 * 職責：
 * 1. Cloudinary 圖片邊緣代理與格式最佳化 (WebP / AVIF)
 * 2. 邊緣節點雙重快取 (Cloudflare Cache API + Browser Cache-Control)
 * 3. 防盜鏈保護 (支援 tabijiapp.com, travel-pwa-five.vercel.app, localhost 與 PWA 模式)
 * 4. 注入 Access-Control-Allow-Origin: *，支援 HTML5 Canvas (html2canvas / PDF 匯出)
 */

const CLOUDINARY_CLOUD_NAME = 'dnpcnwrcu'; 
// 生產環境防護：只允許這些特定的寬度參數。防止惡意者窮舉寬度 (如 w_101, w_102) 耗盡額度
const ALLOWED_WIDTHS = ['320', '640', '768', '1024', '1280']; 

// 允許的來源 (包含本地開發、舊版 Vercel 與自訂主網域)
const ALLOWED_ORIGIN_PATTERNS = [
  'travel-pwa-five.vercel.app',
  'tabijiapp.com',
  'www.tabijiapp.com',
  'localhost',
  '127.0.0.1'
];

function isOriginAllowed(referer, origin) {
  // 檢查 Referer
  if (referer) {
    if (ALLOWED_ORIGIN_PATTERNS.some(pattern => referer.includes(pattern)) || referer.includes('.vercel.app')) {
      return true;
    }
  }
  // 檢查 Origin
  if (origin) {
    if (ALLOWED_ORIGIN_PATTERNS.some(pattern => origin.includes(pattern)) || origin.includes('.vercel.app')) {
      return true;
    }
  }
  // 若兩者皆未攜帶（常見於手機 Standalone PWA、原生 Image preloading 或嚴格防追蹤隱私模式）
  // 只要路徑符合規格，予以放行以保障 PWA 使用者體驗
  if (!referer && !origin) {
    return true;
  }
  return false;
}

export default {
  async fetch(request, env, ctx) {
    // 處理 CORS Preflight (OPTIONS)
    if (request.method.toUpperCase() === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
          'Access-Control-Allow-Headers': '*',
          'Access-Control-Max-Age': '86400',
        },
      });
    }

    const url = new URL(request.url);
    const acceptHeader = request.headers.get('Accept') || '';
    const referer = request.headers.get('Referer') || '';
    const origin = request.headers.get('Origin') || '';

    // 1. 防盜鏈與來源驗證
    if (!isOriginAllowed(referer, origin)) {
      return new Response('Forbidden: Invalid Referer or Origin', { status: 403 });
    }

    // ⭐ 關鍵：使用 Cloudflare Cache API (確保 workers.dev 也能邊緣快取)
    const cache = caches.default;
    const cacheKey = new Request(request.url, request);
    let response = await cache.match(cacheKey);

    // 如果快取命中了，注入 CORS 標頭後直接回傳，完全不消耗 Cloudinary 流量
    if (response) {
      const cachedResponse = new Response(response.body, response);
      cachedResponse.headers.set('Access-Control-Allow-Origin', '*');
      return cachedResponse;
    }

    // === 如果快取沒命中，才去 Cloudinary 抓圖 ===
    
    // 2. 解析路徑與參數
    let imagePath = url.pathname;
    let widthParam = '';

    const widthMatch = imagePath.match(/^\/w_(\d+)(\/.*)/);
    if (widthMatch) {
      const requestedWidth = widthMatch[1];
      // 3. 安全過濾：檢查請求的寬度是否在白名單內
      if (!ALLOWED_WIDTHS.includes(requestedWidth)) {
        return new Response('Forbidden: Invalid Image Width', { status: 403 });
      }
      widthParam = `w_${requestedWidth},`;
      imagePath = widthMatch[2]; 
    }
    
    // 4. 節省點數策略：避免 f_auto
    let format = 'f_webp'; 
    if (acceptHeader.includes('image/avif')) {
      format = 'f_avif';
    }

    const optimizationParams = `${widthParam}${format},q_auto`;

    // 5. 發送請求到 Cloudinary
    const cloudinaryUrl = `https://res.cloudinary.com/${CLOUDINARY_CLOUD_NAME}/image/upload/${optimizationParams}${imagePath}`;
    const cloudinaryRequest = new Request(cloudinaryUrl, request);
    response = await fetch(cloudinaryRequest);
    
    // 6. 確保 Cloudflare 與瀏覽器雙重快取，並注入 CORS
    response = new Response(response.body, response);
    // s-maxage 讓 Cloudflare Edge 記住，max-age 讓使用者的瀏覽器記住 (一年)
    response.headers.set('Cache-Control', 'public, s-maxage=31536000, max-age=31536000, immutable'); 
    response.headers.set('Access-Control-Allow-Origin', '*');
    
    // ⭐ 將抓回來的圖片寫入 Cloudflare 快取，下一次其他訪客要同一張圖時就會直接命中 Cache！
    ctx.waitUntil(cache.put(cacheKey, response.clone()));
    
    return response;
  },
};
