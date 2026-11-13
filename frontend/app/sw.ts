/// <reference lib="webworker" />
import { defaultCache } from "@serwist/next/worker";
import type { SerwistGlobalConfig } from "serwist";
import { Serwist, CacheFirst, NetworkFirst, NetworkOnly, StaleWhileRevalidate, ExpirationPlugin } from "serwist";
import {
  isExternalCdnImageRequest,
  isSensitiveOrDynamicApiRequest,
  isNavigationFallbackRequest,
  sanitizePushLink,
  isSameOriginClientUrl,
  purgeLegacyApiCaches,
} from "../lib/sw-routing";

declare const self: ServiceWorkerGlobalScope & SerwistGlobalConfig;

/**
 * 🛡️ WebKit 重定向淨化器 (Clean Response)
 * 消除 Vercel CDN 或重定向帶有的 redirected: true 毒丸標記
 * 避免 iOS WebKit WebClip 容器在離線載入時拒絕呈現引發死白屏
 */
function cleanResponse(res: Response | undefined): Response | undefined {
  if (!res) return res;
  if (!res.redirected) return res;
  if (res.bodyUsed) return res;
  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers: new Headers(res.headers),
  });
}

const serwist: Serwist = new Serwist({
  precacheEntries: self.__SW_MANIFEST,
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: false, // 🛑 徹底停用，消除 iOS WebKit Standalone 冷啟動 Race Condition
  fallbacks: {
    entries: [
      {
        url: "/",
        matcher({ request }) {
          return request.destination === "document";
        },
      },
    ],
  },
  runtimeCaching: [
    {
      // 🏝️ 本地地理編碼資料 (離線優先)
      matcher: /\/data\/.*\.json$/,
      handler: new CacheFirst({
        cacheName: "local-data",
        plugins: [
          new ExpirationPlugin({
            maxAgeSeconds: 60 * 60 * 24 * 30, // 30 days
          }),
        ],
      }),
    },
    {
      // 🗺️ 地圖樣式、字型與雪碧圖快取 (離線必備，30天)
      matcher: /^https:\/\/tiles\.openfreemap\.org\/(styles|fonts|sprites)\/.*/,
      handler: new CacheFirst({
        cacheName: "map-styles-and-assets",
        plugins: [
          new ExpirationPlugin({
            maxEntries: 150,
            maxAgeSeconds: 60 * 60 * 24 * 30, // 30 days
          }),
        ],
      }),
    },
    {
      // 🗺️ 地圖圖磚快取 (網路優先，離線備援)
      matcher: /^https:\/\/tiles\.openfreemap\.org\/.*/,
      handler: new NetworkFirst({
        cacheName: "map-tiles",
        plugins: [
          new ExpirationPlugin({
            maxEntries: 500,
            maxAgeSeconds: 60 * 60 * 24 * 7, // 7 days
          }),
        ],
      }),
    },
    {
      // 🛰️ 衛星圖層快取
      matcher: /^https:\/\/server\.arcgisonline\.com\/.*/,
      handler: new CacheFirst({
        cacheName: "satellite-tiles",
        plugins: [
          new ExpirationPlugin({
            maxEntries: 100,
            maxAgeSeconds: 60 * 60 * 24 * 14, // 14 days
          }),
        ],
      }),
    },
    {
      // 🔒 強制所有同源 /api/* 與 Supabase Auth 走 NetworkOnly，嚴禁落入 defaultCache "apis" (防跨帳號快取洩漏與舊資料中毒)
      // ⚡ 離線讀取委任 L0/L1/L2 (idb-storage)；離線突變委任 IndexedDB SyncQueue (含動態 JWT 刷新與 401 Outbox 凍結)
      matcher: ({ url, sameOrigin }) => isSensitiveOrDynamicApiRequest({ url, sameOrigin }),
      handler: new NetworkOnly(),
    },
    {
      // 🖼️ 外部景點圖片與 Next.js 最佳化圖片快取 (嚴格根網域/子網域邊界比對)
      matcher: ({ url, sameOrigin }) => isExternalCdnImageRequest({ url, sameOrigin }),
      handler: new StaleWhileRevalidate({
        cacheName: "trip-external-images",
        plugins: [
          new ExpirationPlugin({
            maxEntries: 300, // 300 張全量解鎖 (約 30MB)
            maxAgeSeconds: 60 * 60 * 24 * 30, // 快取 30 天
          }),
        ],
      }),
    },
    {
      // ⚡ Next.js 核心 JS Chunks 離線快取 (CacheFirst 保證秒開，30天)
      matcher: /\/_next\/static.+\.js$/i,
      handler: new CacheFirst({
        cacheName: "next-static-js-assets",
        plugins: [
          new ExpirationPlugin({
            maxEntries: 128,
            maxAgeSeconds: 60 * 60 * 24 * 30, // 30 天
          }),
        ],
      }),
    },
    {
      // 🎨 Next.js 靜態樣式檔與全域 CSS 離線快取 (CacheFirst，30天)
      matcher: /\.(?:css|less)$/i,
      handler: new CacheFirst({
        cacheName: "static-style-assets",
        plugins: [
          new ExpirationPlugin({
            maxEntries: 64,
            maxAgeSeconds: 60 * 60 * 24 * 30, // 30 天
          }),
        ],
      }),
    },
    {
      // 🚀 導航離線備援 (Navigation Fallback: 斷網重開瀏覽器時直接提供已快取的 App Shell)
      // 嚴格排除 /api/ 與 Next.js 的 _rsc 參數，徹底杜絕水合撕裂
      matcher: ({ request, url }) => isNavigationFallbackRequest({ request, url }),
      handler: new NetworkFirst({
        cacheName: "app-shell-navigation",
        networkTimeoutSeconds: 2, // 2 秒內網路不通立即自本地快取提取 App Shell
        plugins: [
          new ExpirationPlugin({
            maxEntries: 30,
            maxAgeSeconds: 60 * 60 * 24 * 30, // 快取 30 天
          }),
          {
            // 🛡️ 關鍵容錯保險：任何未快取子路徑離線訪問失敗時，保底自快取吐出根目錄 App Shell (/)
            handlerDidError: async (): Promise<Response> => {
              try {
                const navCache = await caches.open("app-shell-navigation");
                const cachedNav = await navCache.match("/", { ignoreSearch: true });
                if (cachedNav) return cleanResponse(cachedNav)!;
              } catch (e) {
                console.warn("[SW] navCache match failed:", e);
              }

              try {
                const precachedShell: Response | undefined = await serwist.matchPrecache("/");
                if (precachedShell) return cleanResponse(precachedShell)!;
              } catch (e) {
                console.warn("[SW] matchPrecache failed:", e);
              }

              try {
                const cacheKeys = await caches.keys();
                for (const key of cacheKeys) {
                  if (key.includes("precache")) {
                    const pCache = await caches.open(key);
                    const match = await pCache.match("/", { ignoreSearch: true });
                    if (match) return cleanResponse(match)!;
                  }
                }
              } catch (e) {
                console.warn("[SW] precache keys search failed:", e);
              }

              // 🛡️ 絕不向 WebKit 回傳 Response.error()！回傳內聯 Zero-JS 物理硬骨架，杜絕「Safari無法打開網頁」
              return new Response(
                `<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Tabiji</title><style>body{margin:0;background:#fafaf9;font-family:system-ui,-apple-system,sans-serif;display:flex;flex-direction:column;height:100vh}.hdr{height:56px;background:#fff;border-bottom:1px solid #e7e5e4;display:flex;align-items:center;padding:0 16px;font-weight:700}.cnt{flex:1;padding:16px;display:flex;flex-direction:column;gap:12px}.bx{height:96px;background:#e7e5e4;border-radius:16px;animation:pulse 1.5s ease-in-out infinite}@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}</style></head><body><div class="hdr">Tabiji</div><div class="cnt"><div class="bx"></div><div class="bx"></div><div class="bx"></div></div></body></html>`,
                {
                  status: 200,
                  headers: { "Content-Type": "text/html; charset=utf-8" },
                }
              );
            },
          },
        ],
        // 🛡️ 關鍵補足：忽略 URL query 參數差異 (?source=pwa 等均能 100% 命中快取的 App Shell)
        matchOptions: {
          ignoreSearch: true,
        },
      }),
    },
    ...defaultCache,
  ],
});

serwist.addEventListeners();

// 🧹 物理清除舊版殘留之 trips-api-cache 與 defaultCache "apis"，根除幽靈與跨帳號舊快取
self.addEventListener("activate", (event) => {
  event.waitUntil(
    purgeLegacyApiCaches(caches).then((purged) => {
      if (purged.length > 0) {
        console.log(`🧹 [SW] Purged legacy API caches successfully: ${purged.join(", ")}`);
      }
    })
  );
});

// === Web Push Notification Handler (Ported from legacy sw.js) ===
self.addEventListener("push", (event) => {
  let data: { title?: string; body?: string; tag?: string; link?: unknown } = {};
  if (event.data) {
    try {
      data = event.data.json();
    } catch {
      data = {};
    }
  }
  const title = data.title || "Tabiji 旅路";
  const options = {
    body: data.body || "",
    icon: "/icon.png",
    badge: "/icon.png",
    tag: data.tag || "default",
    data: { link: sanitizePushLink(data.link) },
    vibrate: [100, 50, 100],
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

// === E5: Notification Click Handler (Smart Tab Focus via postMessage) ===
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  // 🛡️ 嚴格同源相對路徑消毒（阻斷反斜線 /\evil.com 與控制字元繞過）
  const safeLink = sanitizePushLink(event.notification.data?.link);
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (isSameOriginClientUrl(client.url, self.location.origin) && "focus" in client) {
          client.focus();
          // 🔔 E5: 零重新整理 SPA 平滑導航，派發深層連結訊息
          client.postMessage({ type: "TABIJI_PUSH_NAVIGATE", url: safeLink });
          return;
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(safeLink);
      }
    })
  );
});
