/**
 * Tabidachi 專用邊緣檢索執行器 (Cloudflare Edge Multi-Engine Search Runner)
 * 作用：由 Cloudflare 邊緣 Anycast 節點聚合檢索 (DDG Lite / Wikipedia OpenSearch API)，返回乾淨 JSON 給 Cloud Run
 */
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // 1. 安全金鑰防禦 (若有設定 PROXY_SECRET 則驗證)
    const secret = request.headers.get("x-tabidachi-key");
    if (env.PROXY_SECRET && secret !== env.PROXY_SECRET) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" }
      });
    }

    // 2. 路由：/search?q=關鍵字&limit=3
    if (url.pathname === "/search") {
      const q = url.searchParams.get("q");
      const limit = parseInt(url.searchParams.get("limit") || "3", 10);
      if (!q) {
        return new Response(JSON.stringify({ error: "Missing query" }), { status: 400 });
      }

      const results = [];

      // 嘗試 1: DuckDuckGo Lite
      try {
        const ddgResp = await fetch("https://lite.duckduckgo.com/lite/", {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
          },
          body: new URLSearchParams({ q }).toString()
        });

        if (ddgResp.ok) {
          const html = await ddgResp.text();
          const linkRegex = /<a[^>]+class=["'][^"']*result-link[^"']*["'][^>]+href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi;
          const snippetRegex = /<td[^>]+class=["'][^"']*result-snippet[^"']*["'][^>]*>([\s\S]*?)<\/td>/gi;

          const links = [];
          let match;
          while ((match = linkRegex.exec(html)) !== null && links.length < limit) {
            links.push({
              href: match[1],
              title: match[2].replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim()
            });
          }

          const snippets = [];
          while ((match = snippetRegex.exec(html)) !== null && snippets.length < limit) {
            snippets.push(match[1].replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim());
          }

          for (let i = 0; i < links.length; i++) {
            let realUrl = links[i].href;
            if (realUrl.includes("uddg=")) {
              const m = realUrl.match(/uddg=([^&]+)/);
              if (m) realUrl = decodeURIComponent(m[1]);
            }
            results.push({
              title: links[i].title,
              snippet: snippets[i] || "",
              url: realUrl
            });
          }
        }
      } catch (e) {
        // DDG 異常時平滑降級至維基百科
      }

      // 嘗試 2: 若 DDG 被 202 軟挑戰攔截，啟用 Wikipedia 官方 OpenSearch API 邊緣直連
      if (results.length === 0) {
        try {
          const wikiUrl = `https://zh.wikipedia.org/w/api.php?action=opensearch&search=${encodeURIComponent(q)}&limit=${limit}&namespace=0&format=json`;
          const wikiResp = await fetch(wikiUrl, {
            headers: {
              "User-Agent": "TabidachiTravelPWA/1.0 (https://tabidachi.app; dev@tabidachi.app)",
              "Accept": "application/json"
            }
          });
          if (wikiResp.ok) {
            const data = await wikiResp.json();
            const titles = data[1] || [];
            const descriptions = data[2] || [];
            const urls = data[3] || [];
            for (let i = 0; i < titles.length; i++) {
              if (urls[i]) {
                results.push({
                  title: `${titles[i]} (維基百科)`,
                  snippet: descriptions[i] || `關於 ${titles[i]} 的開放百科條目詳細資訊。`,
                  url: urls[i]
                });
              }
            }
          }
        } catch (e) {
          // Wiki 亦異常時回傳空陣列
        }
      }

      return new Response(JSON.stringify({ results, source: results.length > 0 ? (results[0].title.includes("維基百科") ? "wikipedia" : "ddg") : "none" }), {
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
      });
    }

    return new Response(JSON.stringify({ status: "Tabidachi Search Proxy Ready" }), {
      headers: { "Content-Type": "application/json" }
    });
  }
};
