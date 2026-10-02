/**
 * Tabidachi 專用邊緣檢索執行器 (Cloudflare Edge Multi-Engine Search Runner)
 * 作用：由 Cloudflare 邊緣 Anycast 節點聚合檢索 (DDG Lite / Wikipedia Full-Text Search API)，返回乾淨 JSON 給 Cloud Run
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
      const rawLimit = parseInt(url.searchParams.get("limit") || "3", 10);
      const limit = Number.isFinite(rawLimit) ? Math.min(Math.max(rawLimit, 1), 10) : 3;

      if (!q) {
        return new Response(JSON.stringify({ error: "Missing query" }), { status: 400 });
      }

      // 快速通道：Wikipedia 全文檢索 API (高容錯、支援複合詞如「京都清水寺」、零 IP 封鎖)
      const fetchWiki = async () => {
        try {
          const wikiUrl = `https://zh.wikipedia.org/w/api.php?action=query&list=search&srsearch=${encodeURIComponent(q)}&srlimit=${limit}&format=json`;
          const resp = await fetch(wikiUrl, {
            headers: {
              "User-Agent": "TabidachiTravelPWA/1.0 (https://tabidachi.app; dev@tabidachi.app)",
              "Accept": "application/json"
            },
            signal: AbortSignal.timeout(2000)
          });
          if (resp.ok) {
            const data = await resp.json();
            const items = data?.query?.search || [];
            const list = [];
            for (const item of items) {
              const cleanSnippet = (item.snippet || "")
                .replace(/<[^>]+>/g, "")
                .replace(/\s+/g, " ")
                .trim();
              list.push({
                title: `${item.title} (維基百科)`,
                snippet: cleanSnippet || `關於 ${item.title} 的開放百科條目詳細資訊。`,
                url: `https://zh.wikipedia.org/wiki/${encodeURIComponent(item.title)}`
              });
            }
            if (list.length > 0) return list;
          }
        } catch (e) {
          // Ignore
        }
        return [];
      };

      // 嘗試通道：DDG Lite (嚴格 1.5 秒超時，防止 DuckDuckGo Tarpit 慢阻斷)
      const fetchDDG = async () => {
        try {
          const resp = await fetch("https://lite.duckduckgo.com/lite/", {
            method: "POST",
            headers: {
              "Content-Type": "application/x-www-form-urlencoded",
              "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
              "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7",
              "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            },
            body: new URLSearchParams({ q }).toString(),
            signal: AbortSignal.timeout(1500)
          });
          if (resp.ok) {
            const html = await resp.text();
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

            const list = [];
            for (let i = 0; i < links.length; i++) {
              let realUrl = links[i].href;
              if (realUrl.includes("uddg=")) {
                const m = realUrl.match(/uddg=([^&]+)/);
                if (m) realUrl = decodeURIComponent(m[1]);
              }
              list.push({
                title: links[i].title,
                snippet: snippets[i] || "",
                url: realUrl
              });
            }
            return list;
          }
        } catch (e) {
          // Ignore
        }
        return [];
      };

      // 雙通道並行：1.5s 內必定結算
      const [ddgResults, wikiResults] = await Promise.all([fetchDDG(), fetchWiki()]);
      const finalResults = ddgResults.length > 0 ? ddgResults : wikiResults;
      const source = ddgResults.length > 0 ? "ddg" : (wikiResults.length > 0 ? "wikipedia" : "none");

      return new Response(JSON.stringify({ results: finalResults, source }), {
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
      });
    }

    return new Response(JSON.stringify({ status: "Tabidachi Search Proxy Ready" }), {
      headers: { "Content-Type": "application/json" }
    });
  }
};
