/**
 * Tabidachi 專用邊緣檢索執行器 (Cloudflare Edge Multi-Engine Search Runner v2)
 * 作用：Fail-Closed 雙標頭密碼鎖 + 多引擎優先鏈 (Tavily -> Firecrawl -> Google News RSS -> DDG Lite 200-only -> 條件維基)，
 * 嚴防 202 CAPTCHA 誤判與無關維基毒化。
 */

const OUTBOUND_USER_AGENT = "TabijiTravelPWA/1.0 (https://www.tabijiapp.com; contact@tabijiapp.com)";
const BROWSER_USER_AGENT =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

const TEMPORAL_KEYWORD_RE =
  /(?:營業時間|開放時間|休館|公休|票價|門票|價錢|價格|費用|預約|訂位|購票|最新|今天|明天|今年|公告|停駛|暫停|活動|祭典|櫻花|楓葉|天氣|匯率|営業時間|開館時間|定休日|休業|入場料|料金|予約|チケット|最新情報|天気|為替|開催|\b(?:ticket|tickets|price|prices|hours|opening|open|close|closed|reservation|booking|schedule|status|news|event|forecast|2025|2026|2027|2028)\b)/i;
const TEMPORAL_KEYWORD_STRIP_RE = new RegExp(TEMPORAL_KEYWORD_RE.source, "gi");

// 中文／日文／韓文口語與檢索模板停用詞（避免無害問句詞或模板詞如「推薦」「附近」「食べログ」「맛집」「おすすめ」「アクセス」把正常新聞過濾為 0）
const CJK_CONVERSATIONAL_STOPWORD_RE =
  /(?:食べログ|맛집|おすすめ|オススメ|ランキング|アクセス|行き方|口コミ|まとめ|人気|観光|グルメ|最熱門|這附近|有沒有|哪裡有|請問|幫我|推薦|附近|熱門|哪裡|哪家|這裡|這家|這個|這些|那些|一下|什麼|怎麼|可以|介紹|資訊|情報|攻略|心得|評價|行程|必吃|必去|值得|好吃|好玩|這)/g;

// 嚴格僅收錄繁體中文特有字／舊字體（排除日文常用漢字如 個/車/業/旅/飯/館/線/買/開/機/資，避免純日文查詢誤判為 zh-TW）
const ZH_TW_LOCALE_SIGNAL_RE =
  /[這哪麼裡嗎呢吧站營鐵廣劃臺灣體賣關廳點麵訊價樂圓轉樓區號實處邊學國淺澀櫻獨繪氣經驗歡總覽藝藥覺證條專齋燒壽圖萬與對會濱澤驛]/;
const ZH_TW_PHRASE_SIGNAL_RE =
  /(?:推薦|附近|最熱門|必吃|必去|伴手禮|美食|景點|行程|攻略|自由行|好吃|好玩|營業時間|門票|票價|訂位)/;
// 日文新字體特有字（繁體中文不用此字形，輔助識別含「の」等少假名日文查詢）
const JP_SHINJITAI_RE = /[駅浅渋桜図広転売営鉄払読両団県区発変沢楽歳辺観権実焼麺斎寿浜]/;

const LATIN_STOPWORDS = new Set([
  "the", "for", "and", "in", "of", "to", "a", "an", "is", "are", "at", "on", "with",
  "how", "what", "when", "where", "who", "why", "from", "by", "about", "info", "guide",
  "ticket", "tickets", "price", "prices", "hours", "opening", "open", "close", "closed",
  "2024", "2025", "2026", "2027", "2028",
  // 後端雙軌模板注入之論壇／泛用旅遊詞（不可作為新聞主題核心詞，避免離題業配憑 ptt/dcard 繞過相關性過濾）
  "ptt", "dcard", "pantip", "openrice", "eater", "reddit",
  "travel", "local", "tips", "recommendations", "recommendation", "hidden", "gems", "street", "food",
  "japantravel", "koreatravel", "thailandtourism", "singaporetravel", "vietnamtravel", "traveleurope", "hongkongtravel",
]);

function hasTemporalKeyword(query) {
  return TEMPORAL_KEYWORD_RE.test(String(query || ""));
}

function resolveNewsLocale(query) {
  const q = String(query || "");
  // 剝除後端繁中在地模板注入的「食べログ」再計算假名比例，避免單一外來詞誤導語系
  const qForLocale = q.replace(/食べログ/g, " ");
  const kanaCount = (qForLocale.match(/[\u3040-\u30ff]/g) || []).length;
  const nonNoKanaCount = (qForLocale.replace(/の/g, "").match(/[\u3040-\u30ff]/g) || []).length;
  const hanCount = (qForLocale.match(/[\u4e00-\u9fff]/g) || []).length;
  const hasZhTwSignal = ZH_TW_LOCALE_SIGNAL_RE.test(qForLocale) || ZH_TW_PHRASE_SIGNAL_RE.test(qForLocale);
  const hasJpShinjitai = JP_SHINJITAI_RE.test(qForLocale);
  const isPredominantlyJapanese =
    !hasZhTwSignal &&
    (
      nonNoKanaCount > 0 ||
      (kanaCount > 0 && (hanCount === 0 || hasJpShinjitai || kanaCount / (kanaCount + hanCount) >= 0.25))
    );

  if (isPredominantlyJapanese) {
    return { hl: "ja", gl: "JP", ceid: "JP:ja" };
  }
  if (hanCount > 0 || kanaCount > 0 || /[\u3040-\u30ff]/.test(q)) {
    return { hl: "zh-TW", gl: "TW", ceid: "TW:zh-Hant" };
  }
  return { hl: "en-US", gl: "US", ceid: "US:en" };
}

function decodeXmlEntities(str) {
  return String(str || "")
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&#x([0-9a-fA-F]+);/g, (_, hex) => {
      const code = parseInt(hex, 16);
      return Number.isFinite(code) ? String.fromCodePoint(code) : "";
    })
    .replace(/&#(\d+);/g, (_, num) => {
      const code = parseInt(num, 10);
      return Number.isFinite(code) ? String.fromCodePoint(code) : "";
    });
}

function extractCoreTokens(query) {
  const cleaned = String(query || "")
    .replace(/site:\S+/gi, " ")
    .replace(TEMPORAL_KEYWORD_STRIP_RE, " ")
    .replace(CJK_CONVERSATIONAL_STOPWORD_RE, " ")
    .toLowerCase();

  const tokens = new Set();
  // ASCII / Latin words >= 2 chars
  const latinMatches = cleaned.match(/[a-z0-9]{2,}/g) || [];
  for (const w of latinMatches) {
    if (!LATIN_STOPWORDS.has(w)) {
      tokens.add(w);
    }
  }
  // CJK runs -> bigrams (or exact run if length 1-2)
  const cjkRuns = cleaned.match(/[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]+/g) || [];
  for (const run of cjkRuns) {
    if (run.length <= 2) {
      tokens.add(run);
    } else {
      for (let i = 0; i <= run.length - 2; i++) {
        tokens.add(run.slice(i, i + 2));
      }
    }
  }
  return Array.from(tokens);
}

function isRelevantTitle(query, candidateText, minRatio = 0.5) {
  const qNorm = String(query || "").replace(/site:\S+/gi, "").trim().toLowerCase();
  const cNorm = String(candidateText || "").trim().toLowerCase();
  if (!qNorm || !cNorm) return false;
  // Direct containment check for clean short names (e.g. "東京鐵塔", "東京")
  const strippedCandidate = cNorm.replace(/\s*\([^)]*\)\s*/g, "").trim();
  if (strippedCandidate.length >= 2 && (qNorm.includes(strippedCandidate) || strippedCandidate.includes(qNorm))) {
    return true;
  }
  const tokens = extractCoreTokens(qNorm);
  if (tokens.length === 0) return false;
  let hits = 0;
  for (const tok of tokens) {
    if (cNorm.includes(tok)) hits += 1;
  }
  return (hits / tokens.length) >= minRatio;
}

function isRelevantNewsItem(query, title, sourceName = "") {
  const combined = `${title || ""} ${sourceName || ""}`.toLowerCase();
  const tokens = extractCoreTokens(query);
  if (tokens.length === 0) return true;
  let hits = 0;
  for (const tok of tokens) {
    if (combined.includes(tok)) hits += 1;
  }
  if (tokens.length === 1) return hits >= 1;
  return hits >= Math.max(1, Math.ceil(tokens.length * 0.34));
}

async function sha256TimingSafeEqual(a, b) {
  const enc = new TextEncoder();
  const [hashA, hashB] = await Promise.all([
    crypto.subtle.digest("SHA-256", enc.encode(String(a || ""))),
    crypto.subtle.digest("SHA-256", enc.encode(String(b || ""))),
  ]);
  const viewA = new Uint8Array(hashA);
  const viewB = new Uint8Array(hashB);
  if (typeof crypto.subtle.timingSafeEqual === "function") {
    return crypto.subtle.timingSafeEqual(viewA, viewB);
  }
  let diff = 0;
  for (let i = 0; i < viewA.length; i++) {
    diff |= viewA[i] ^ viewB[i];
  }
  return diff === 0;
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

async function fetchTavily(q, limit, apiKey) {
  const key = (apiKey || "").trim();
  if (!key) return [];
  try {
    const resp = await fetch("https://api.tavily.com/search", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "User-Agent": OUTBOUND_USER_AGENT,
      },
      body: JSON.stringify({
        api_key: key,
        query: q,
        max_results: limit,
        search_depth: "basic",
      }),
      signal: AbortSignal.timeout(2800),
    });
    if (resp.status === 402 || resp.status === 429 || resp.status >= 500 || !resp.ok) {
      return [];
    }
    const data = await resp.json();
    const items = Array.isArray(data?.results) ? data.results : [];
    return items
      .filter((item) => item && typeof item.url === "string" && item.url.startsWith("http"))
      .slice(0, limit)
      .map((item) => ({
        title: String(item.title || "").trim(),
        snippet: String(item.content || "").trim().slice(0, 400),
        url: item.url.trim(),
      }));
  } catch {
    return [];
  }
}

async function fetchFirecrawl(q, limit, apiKey) {
  const key = (apiKey || "").trim();
  if (!key) return [];
  try {
    const resp = await fetch("https://api.firecrawl.dev/v1/search", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${key}`,
        "User-Agent": OUTBOUND_USER_AGENT,
      },
      body: JSON.stringify({
        query: q,
        limit,
      }),
      signal: AbortSignal.timeout(2800),
    });
    if (resp.status === 402 || resp.status === 429 || resp.status >= 500 || !resp.ok) {
      return [];
    }
    const data = await resp.json();
    const items = Array.isArray(data?.data) ? data.data : [];
    return items
      .filter((item) => item && typeof item.url === "string" && item.url.startsWith("http"))
      .slice(0, limit)
      .map((item) => ({
        title: String(item.title || "").trim(),
        snippet: String(item.description || item.markdown || "").trim().slice(0, 400),
        url: item.url.trim(),
      }));
  } catch {
    return [];
  }
}

async function fetchGoogleNewsRSS(q, limit, timeoutMs = 2800, externalSignal = null) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const onExternalAbort = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) {
      clearTimeout(timeoutId);
      return [];
    }
    externalSignal.addEventListener("abort", onExternalAbort, { once: true });
  }
  try {
    const { hl, gl, ceid } = resolveNewsLocale(q);

    const rssUrl =
      `https://news.google.com/rss/search?q=${encodeURIComponent(q)}` +
      `&hl=${encodeURIComponent(hl)}&gl=${encodeURIComponent(gl)}&ceid=${encodeURIComponent(ceid)}`;

    const resp = await fetch(rssUrl, {
      headers: {
        "User-Agent": OUTBOUND_USER_AGENT,
        Accept: "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
      },
      signal: controller.signal,
    });
    if (resp.status !== 200) return [];

    const xml = await resp.text();
    const itemRegex = /<item\b[^>]*>([\s\S]*?)<\/item>/gi;
    const list = [];
    let m;
    while ((m = itemRegex.exec(xml)) !== null && list.length < limit) {
      const block = m[1];
      const titleMatch = block.match(/<title\b[^>]*>([\s\S]*?)<\/title>/i);
      const linkMatch = block.match(/<link\b[^>]*>([\s\S]*?)<\/link>/i);
      const pubDateMatch = block.match(/<pubDate\b[^>]*>([\s\S]*?)<\/pubDate>/i);
      const sourceMatch = block.match(/<source\b[^>]*>([\s\S]*?)<\/source>/i);

      const title = decodeXmlEntities(titleMatch ? titleMatch[1] : "").replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
      const link = decodeXmlEntities(linkMatch ? linkMatch[1] : "").trim();
      const pubDate = decodeXmlEntities(pubDateMatch ? pubDateMatch[1] : "").trim();
      const sourceName = decodeXmlEntities(sourceMatch ? sourceMatch[1] : "").replace(/<[^>]+>/g, "").trim();

      if (!title || !link || !link.startsWith("http")) continue;
      if (!isRelevantNewsItem(q, title, sourceName)) continue;

      const isZh = hl.startsWith("zh");
      const metaParts = [];
      if (sourceName) metaParts.push(isZh ? `來源: ${sourceName}` : `Source: ${sourceName}`);
      if (pubDate) metaParts.push(isZh ? `發布: ${pubDate}` : `Published: ${pubDate}`);
      const snippet = isZh
        ? `[新聞/活動標題線索] ${title}${metaParts.length ? ` (${metaParts.join(" | ")})` : ""}`
        : `[News/Event Headline Lead] ${title}${metaParts.length ? ` (${metaParts.join(" | ")})` : ""}`;

      list.push({
        title,
        snippet,
        url: link,
      });
    }
    return list;
  } catch {
    return [];
  } finally {
    clearTimeout(timeoutId);
    if (externalSignal) {
      externalSignal.removeEventListener("abort", onExternalAbort);
    }
  }
}

async function fetchDDGLite(q, limit, timeoutMs = 2800) {
  try {
    const resp = await fetch("https://lite.duckduckgo.com/lite/", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": BROWSER_USER_AGENT,
        "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7",
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      },
      body: new URLSearchParams({ q }).toString(),
      signal: AbortSignal.timeout(timeoutMs),
    });
    // Strictly require HTTP 200 (reject HTTP 202 anti-bot CAPTCHA pages)
    if (resp.status !== 200) return [];

    const html = await resp.text();
    const anchorRegex = /<a\b([^>]*)>([\s\S]*?)<\/a>/gi;
    const singleSnippetRegex = /<td[^>]+class=["'][^"']*result-snippet[^"']*["'][^>]*>([\s\S]*?)<\/td>/i;

    // Collect ALL result-link anchors (including ads) with positions so each link pairs
    // strictly with the snippet in its own slice before the next result-link (prevents ad-row off-by-N shift).
    const allAnchors = [];
    let match;
    while ((match = anchorRegex.exec(html)) !== null) {
      const attrs = match[1];
      if (!/class=["'][^"']*result-link[^"']*["']/i.test(attrs)) continue;
      const hrefMatch = attrs.match(/href=["']([^"']+)["']/i);
      if (!hrefMatch) continue;
      let realUrl = decodeXmlEntities(hrefMatch[1]).trim();
      if (realUrl.startsWith("//")) realUrl = `https:${realUrl}`;
      if (realUrl.includes("uddg=")) {
        const m = realUrl.match(/uddg=([^&]+)/);
        if (m) {
          try {
            realUrl = decodeURIComponent(m[1]);
          } catch {
            // keep original
          }
        }
      }
      const isAd =
        !realUrl.startsWith("http") ||
        /^https?:\/\/(?:www\.)?duckduckgo\.com\/(?:y\.js|duckduckgo-help-pages)/i.test(realUrl) ||
        realUrl.includes("ad_domain=");
      allAnchors.push({
        start: match.index,
        end: anchorRegex.lastIndex,
        url: realUrl,
        title: decodeXmlEntities(match[2].replace(/<[^>]+>/g, "")).replace(/\s+/g, " ").trim(),
        isAd,
      });
    }

    const list = [];
    for (let i = 0; i < allAnchors.length && list.length < limit; i++) {
      const cur = allAnchors[i];
      if (cur.isAd) continue;
      const sliceEnd = i + 1 < allAnchors.length ? allAnchors[i + 1].start : html.length;
      const segment = html.slice(cur.end, sliceEnd);
      const snipMatch = segment.match(singleSnippetRegex);
      const snippet = snipMatch
        ? decodeXmlEntities(snipMatch[1].replace(/<[^>]+>/g, "")).replace(/\s+/g, " ").trim()
        : "";
      list.push({
        title: cur.title,
        snippet,
        url: cur.url,
      });
    }
    return list;
  } catch {
    return [];
  }
}

async function fetchConditionalWiki(q, limit) {
  if (hasTemporalKeyword(q)) return [];
  try {
    const isCjk = /[\u4e00-\u9fff]/.test(q);
    const wikiLang = isCjk ? "zh" : "en";
    const wikiUrl = `https://${wikiLang}.wikipedia.org/w/api.php?action=query&list=search&srsearch=${encodeURIComponent(q)}&srlimit=${Math.min(limit + 2, 10)}&format=json`;
    const resp = await fetch(wikiUrl, {
      headers: {
        "User-Agent": OUTBOUND_USER_AGENT,
        Accept: "application/json",
      },
      signal: AbortSignal.timeout(1200),
    });
    if (resp.status !== 200) return [];
    const data = await resp.json();
    const items = data?.query?.search || [];
    const list = [];
    for (const item of items) {
      const title = String(item?.title || "").trim();
      if (!title || !isRelevantTitle(q, title, 0.5)) continue;
      const cleanSnippet = String(item?.snippet || "")
        .replace(/<[^>]+>/g, "")
        .replace(/\s+/g, " ")
        .trim();
      list.push({
        title: wikiLang === "zh" ? `${title} (維基百科)` : `${title} (Wikipedia)`,
        snippet: cleanSnippet || (wikiLang === "zh" ? `關於 ${title} 的開放百科條目詳細資訊。` : `Encyclopedia entry about ${title}.`),
        url: `https://${wikiLang}.wikipedia.org/wiki/${encodeURIComponent(title)}`,
      });
      if (list.length >= limit) break;
    }
    return list;
  } catch {
    return [];
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // 1. Fail-Closed 雙標頭密碼鎖 (接受 x-tabidachi-key 或 x-proxy-secret，經 SHA-256 + timingSafeEqual 比對)
    const expectedSecret = String(env?.PROXY_SECRET || "").trim();
    if (!expectedSecret) {
      return jsonResponse({ error: "Search proxy secret not configured" }, 503);
    }

    const providedSecret = String(
      request.headers.get("x-tabidachi-key") || request.headers.get("x-proxy-secret") || ""
    ).trim();
    if (!providedSecret || !(await sha256TimingSafeEqual(providedSecret, expectedSecret))) {
      return jsonResponse({ error: "Unauthorized" }, 401);
    }

    // 2. 路由：/search?q=關鍵字&limit=3
    if (url.pathname === "/search") {
      const q = (url.searchParams.get("q") || "").trim();
      const rawLimit = parseInt(url.searchParams.get("limit") || "3", 10);
      const limit = Number.isFinite(rawLimit) ? Math.min(Math.max(rawLimit, 1), 10) : 3;

      if (!q) {
        return jsonResponse({ error: "Missing query" }, 400);
      }

      // 優先鏈 1: Tavily -> Firecrawl (選配每月重置免費額度)
      const tavilyResults = await fetchTavily(q, limit, env?.TAVILY_API_KEY);
      if (tavilyResults.length > 0) {
        return jsonResponse({ results: tavilyResults, source: "tavily" });
      }

      const firecrawlResults = await fetchFirecrawl(q, limit, env?.FIRECRAWL_API_KEY);
      if (firecrawlResults.length > 0) {
        return jsonResponse({ results: firecrawlResults, source: "firecrawl" });
      }

      // 優先鏈 2: 免 Key 並行競速 (DDG Lite 200-only 2500ms || Google News RSS 2800ms)
      // 品質優先且零隊頭阻塞：雙軌同時發起，DDG 有結果即刻中斷 RSS 秒回，杜絕 Promise.all 空等慢速 RSS 2.8s
      const rssController = new AbortController();
      const ddgPromise = fetchDDGLite(q, limit, 2500);
      const rssPromise = fetchGoogleNewsRSS(q, limit, 2800, rssController.signal);
      const ddgResults = await ddgPromise;
      if (ddgResults.length > 0) {
        rssController.abort();
        rssPromise.catch(() => []);
        return jsonResponse({ results: ddgResults, source: "ddg" });
      }
      const newsResults = await rssPromise;
      if (newsResults.length > 0) {
        return jsonResponse({ results: newsResults, source: "google_news_rss" });
      }

      // 優先鏈 4: 條件維基 (含時效詞禁走 + 嚴格標題相關性門檻；未達標回空)
      const wikiResults = await fetchConditionalWiki(q, limit);
      if (wikiResults.length > 0) {
        return jsonResponse({ results: wikiResults, source: "wikipedia" });
      }

      return jsonResponse({ results: [], source: "none" });
    }

    return jsonResponse({ status: "Tabidachi Search Proxy Ready" });
  },
};
