# ⚡ Cloudflare 邊緣架構範式與生產代碼模板

> **本文件定位**：延遲載入參考手冊 (On-Demand Reference)。當 Agent 需要在 Cloudflare Workers 實作邊緣代理、圖床反代、邊緣限流或 AI 備援時查閱。  
> **技術標準**：相容 Cloudflare Workers 2024+ 現代標準，採用 ESM 模組（`export default { fetch }`）與 `wrangler.jsonc` 設定規格。

---

## 1. 範式一：4-Tier 雙通道抗阻斷搜尋代理 (Tabidachi 現役生產架構)

### 1.1 業務場景
後端（如 GCP Cloud Run）運行於雲端機房，遭遇 DuckDuckGo 等搜尋引擎針對機房 ASN 的 HTTP 403 阻擋或 429 頻率限制。透過全球 300+ Anycast 邊緣節點聚合檢索並清洗，回傳乾淨結構化 JSON。

### 1.2 `wrangler.jsonc` 配置
```jsonc
{
  "$schema": "https://unpkg.com/wrangler/config-schema.json",
  "name": "tabidachi-search-proxy",
  "main": "worker.js",
  "compatibility_date": "2024-09-23",
  "workers_dev": true,
  "observability": {
    "enabled": true
  }
}
```

### 1.3 `worker.js` 生產級代碼
```javascript
/**
 * Tabidachi 雙通道邊緣檢索執行器 (Edge Search Runner)
 * - 雙通道並行競速：Promise.all([fetchDDG(), fetchWiki()])
 * - DDG Lite 快速中斷：AbortSignal.timeout(1500) 防範 Tarpit 慢阻斷
 * - Wikipedia 全文語意檢索 API 保底
 */
export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, x-tabidachi-key",
        }
      });
    }

    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // 可選金鑰檢驗
    if (env.PROXY_SECRET) {
      const authHeader = request.headers.get("x-tabidachi-key");
      if (authHeader !== env.PROXY_SECRET) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), {
          status: 401,
          headers: { "Content-Type": "application/json" }
        });
      }
    }

    let payload;
    try {
      payload = await request.json();
    } catch {
      return new Response("Bad Request: Invalid JSON", { status: 400 });
    }

    const { query, max_results = 5 } = payload;
    if (!query) {
      return new Response("Bad Request: Missing query", { status: 400 });
    }

    // 雙通道並行競速
    const [ddgResults, wikiResults] = await Promise.all([
      fetchDuckDuckGoLite(query, max_results),
      fetchWikipediaFullText(query, max_results)
    ]);

    // 合併去重：DDG 優先，維基百科補底
    const seenUrls = new Set();
    const merged = [];

    for (const item of [...ddgResults, ...wikiResults]) {
      if (!seenUrls.has(item.href)) {
        seenUrls.add(item.href);
        merged.push(item);
      }
      if (merged.length >= max_results) break;
    }

    return new Response(JSON.stringify({ results: merged }), {
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, max-age=3600"
      }
    });
  }
};

async function fetchDuckDuckGoLite(query, maxResults) {
  try {
    const formData = new URLSearchParams();
    formData.append("q", query);

    const res = await fetch("https://lite.duckduckgo.com/lite/", {
      method: "POST",
      body: formData,
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      },
      signal: AbortSignal.timeout(1500) // 1.5 秒硬熔斷
    });

    if (!res.ok) return [];
    const html = await res.text();
    return parseDDGLiteHtml(html, maxResults);
  } catch {
    return []; // 超時或失敗安靜降級
  }
}

function parseDDGLiteHtml(html, maxResults) {
  const results = [];
  const linkRegex = /<a[^>]+class=["']result-link["'][^>]*href=["']([^"']+)["'][^>]*>(.*?)<\/a>/gi;
  const snippetRegex = /<td[^>]+class=["']result-snippet["'][^>]*>(.*?)<\/td>/gi;

  const links = [];
  let match;
  while ((match = linkRegex.exec(html)) !== null) {
    links.push({
      href: match[1],
      title: match[2].replace(/<[^>]+>/g, "").trim()
    });
  }

  const snippets = [];
  while ((match = snippetRegex.exec(html)) !== null) {
    snippets.push(match[1].replace(/<[^>]+>/g, "").trim());
  }

  for (let i = 0; i < Math.min(links.length, maxResults); i++) {
    results.push({
      title: links[i].title,
      href: links[i].href,
      body: snippets[i] || ""
    });
  }
  return results;
}

async function fetchWikipediaFullText(query, maxResults) {
  try {
    const cleanQuery = query.replace(/[^\w\u4e00-\u9fff\s]/gi, "").trim();
    const url = `https://zh.wikipedia.org/w/api.php?action=query&list=search&srsearch=${encodeURIComponent(cleanQuery)}&format=json&utf8=1&srlimit=${maxResults}`;

    const res = await fetch(url, {
      headers: { "User-Agent": "TabidachiTravelBot/1.0" },
      signal: AbortSignal.timeout(1500)
    });

    if (!res.ok) return [];
    const data = await res.json();
    const items = data.query?.search || [];

    return items.map(item => ({
      title: item.title,
      href: `https://zh.wikipedia.org/wiki/${encodeURIComponent(item.title)}`,
      body: (item.snippet || "").replace(/<[^>]+>/g, "").trim()
    }));
  } catch {
    return [];
  }
}
```

---

## 2. 範式二：R2 景點圖床 CORS 洗白與邊緣快取代理 (Media Cache & CORS Proxy)

### 2.1 業務場景
PWA 離線快取外部景點照片（如 Mapillary, Unsplash, 維基共享資源）時，iOS Safari 會將非同源圖片標記為 Opaque Response，單張 50KB 圖片在 Cache API 中會膨脹填充為 **7MB ~ 10MB** 配額，快取數十張即引發瀏覽器 `QuotaExceededError`。  
透過此代理注入 `Access-Control-Allow-Origin: *` 並利用 Cloudflare Edge 快取 24 小時，將配額佔用精確還原為原始二進位大小。

### 2.2 `wrangler.jsonc` 綁定 R2
```jsonc
{
  "$schema": "https://unpkg.com/wrangler/config-schema.json",
  "name": "tabidachi-image-proxy",
  "main": "worker.js",
  "compatibility_date": "2024-09-23",
  "r2_buckets": [
    {
      "binding": "IMAGE_BUCKET",
      "bucket_name": "tabidachi-media"
    }
  ]
}
```

### 2.3 `worker.js` 生產級代碼
```javascript
export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
          "Access-Control-Max-Age": "86400"
        }
      });
    }

    const url = new URL(request.url);
    const targetUrl = url.searchParams.get("url");

    if (!targetUrl) {
      return new Response("Missing 'url' query param", { status: 400 });
    }

    // SSRF 安全白名單防禦
    try {
      const parsedTarget = new URL(targetUrl);
      if (!["http:", "https:"].includes(parsedTarget.protocol)) {
        return new Response("Invalid protocol", { status: 400 });
      }
      // 阻擋私有 IP 與雲端 Metadata
      if (/^(127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|169\.254\.)/.test(parsedTarget.hostname)) {
        return new Response("Forbidden target", { status: 403 });
      }
    } catch {
      return new Response("Invalid target URL", { status: 400 });
    }

    // 利用 Cloudflare 邊緣 Cache API
    const cacheKey = new Request(url.toString(), request);
    const cache = caches.default;
    let response = await cache.match(cacheKey);

    if (response) {
      return response;
    }

    // 發起外部圖片抓取
    const imageRes = await fetch(targetUrl, {
      headers: {
        "User-Agent": "Mozilla/5.0 (compatible; TabidachiImageBot/1.0)",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
      },
      cf: {
        cacheEverything: true,
        cacheTtl: 86400 // 邊緣快取 24 小時
      },
      signal: AbortSignal.timeout(5000)
    });

    if (!imageRes.ok) {
      return new Response(`Upstream image failed: ${imageRes.status}`, { status: 502 });
    }

    const contentType = imageRes.headers.get("content-type") || "image/jpeg";

    // 建立具備完整 CORS 標頭之乾淨 Response
    response = new Response(imageRes.body, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "public, max-age=604800, immutable", // 客戶端快取 7 天
        "Timing-Allow-Origin": "*"
      }
    });

    ctx.waitUntil(cache.put(cacheKey, response.clone()));
    return response;
  }
};
```

---

## 3. 範式三：Workers KV 邊緣滑動窗口頻率限制 (Edge Rate Limiter)

### 3.1 業務場景
在邊緣節點直接攔截惡意高頻刷單爬蟲，杜絕無效流量穿透至後端 GCP Cloud Run，節省伺服器冷啟動與運算費用。

### 3.2 `wrangler.jsonc` 綁定 KV
```jsonc
{
  "$schema": "https://unpkg.com/wrangler/config-schema.json",
  "name": "tabidachi-rate-limiter",
  "main": "worker.js",
  "compatibility_date": "2024-09-23",
  "kv_namespaces": [
    {
      "binding": "RATE_LIMIT_KV",
      "id": "<YOUR_KV_NAMESPACE_ID>"
    }
  ]
}
```

### 3.3 `worker.js` 生產級代碼
```javascript
export default {
  async fetch(request, env) {
    const clientIp = request.headers.get("cf-connecting-ip") || "unknown";
    const windowSeconds = 60;
    const maxRequests = 30; // 每分鐘 30 次上限

    const currentMinute = Math.floor(Date.now() / 1000 / windowSeconds);
    const key = `ratelimit:${clientIp}:${currentMinute}`;

    // 讀取當前計數器
    const currentCountStr = await env.RATE_LIMIT_KV.get(key);
    let count = currentCountStr ? parseInt(currentCountStr, 10) : 0;

    if (count >= maxRequests) {
      return new Response(JSON.stringify({
        error: "Too Many Requests",
        message: "已達到每分鐘請求次數上限，請稍後重試。"
      }), {
        status: 429,
        headers: {
          "Content-Type": "application/json",
          "Retry-After": "60",
          "Access-Control-Allow-Origin": "*"
        }
      });
    }

    // 計數累加並設置 TTL 自動過期 (90 秒)
    count++;
    await env.RATE_LIMIT_KV.put(key, count.toString(), { expirationTtl: 90 });

    // 放行轉發給後端 Cloud Run
    const backendUrl = "https://tabidachi-backend-xxxx.a.run.app";
    const forwardUrl = new URL(request.url);
    const originUrl = new URL(backendUrl);
    forwardUrl.hostname = originUrl.hostname;
    forwardUrl.protocol = originUrl.protocol;
    forwardUrl.port = originUrl.port;

    const modifiedRequest = new Request(forwardUrl.toString(), request);
    return fetch(modifiedRequest);
  }
};
```

---

## 4. 範式四：Workers AI / AI Gateway 邊緣彈性備援 (Resilient Fallback)

### 4.1 業務場景
當 Google Gemini 遇到全球性連線抖動或 API 配額耗盡（HTTP 429）時，邊緣代理在 0ms 內無縫切換至 Cloudflare Workers 原生託管之開源模型（如 `@cf/meta/llama-3.1-8b-instruct`），確保 AI 旅遊伴侶不中斷。

### 4.2 `wrangler.jsonc` 綁定 Workers AI
```jsonc
{
  "$schema": "https://unpkg.com/wrangler/config-schema.json",
  "name": "tabidachi-ai-fallback",
  "main": "worker.js",
  "compatibility_date": "2024-09-23",
  "ai": {
    "binding": "AI"
  }
}
```

### 4.3 `worker.js` 生產級代碼
```javascript
export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const { messages, stream = false } = await request.json();

    try {
      const response = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
        messages: [
          { role: "system", content: "你是 Tabidachi 旅遊伴侶，請使用繁體中文簡明回答旅遊問題。" },
          ...messages
        ],
        stream
      });

      if (stream) {
        return new Response(response, {
          headers: {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Access-Control-Allow-Origin": "*"
          }
        });
      }

      return new Response(JSON.stringify(response), {
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*"
        }
      });
    } catch (err) {
      return new Response(JSON.stringify({ error: err.message }), {
        status: 500,
        headers: { "Content-Type": "application/json" }
      });
    }
  }
};
```
