/**
 * Tabidachi 專用邊緣檢索執行器 (Cloudflare Edge Multi-Engine Search Runner v2.1)
 * 作用：Fail-Closed 雙標頭密碼鎖 + 多引擎優先鏈 (Tavily -> Firecrawl -> DDG Lite 200-only || Google News RSS 雙源合併 -> 條件維基)，
 * 含短寬限窗防隊頭阻塞、雙鍵去重與全語系 Unicode 檢索安全網，嚴防 202 CAPTCHA 誤判與無關維基毒化。
 */

const OUTBOUND_USER_AGENT = "TabijiTravelPWA/1.0 (https://www.tabijiapp.com; contact@tabijiapp.com)";
const BROWSER_USER_AGENT =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

const MAX_QUERY_ANALYZE_LEN = 500;
const RSS_SUPPLEMENT_MAX = 2;
const RSS_GRACE_AFTER_DDG_MS = 600;
const RSS_TOTAL_BUDGET_WHEN_DDG_OK_MS = 1800;
const GRACE_TIMEOUT = Symbol("grace_timeout");

const TEMPORAL_KEYWORD_RE =
  /(?:營業時間|開放時間|休館|公休|票價|門票|價錢|價格|費用|預約|訂位|購票|最新|今天|明天|今年|公告|停駛|暫停|活動|祭典|櫻花|楓葉|天氣|匯率|営業時間|開館時間|定休日|休業|入場料|料金|予約|チケット|最新情報|天気|為替|開催|영업시간|휴무|입장료|가격|예약|티켓|최신|축제|날씨|환율|เวลาเปิดปิด|ราคา|ตั๋ว|จอง|ล่าสุด|เทศกาล|สภาพอากาศ|\b(?:ticket|tickets|price|prices|hours|opening|open|close|closed|reservation|booking|schedule|status|news|event|forecast|2025|2026|2027|2028|horaires?|billets?|tarifs?|prix|offnungszeiten|eintritt|horarios?|entradas?|precios?|orari|biglietti)\b)/i;
const TEMPORAL_KEYWORD_STRIP_RE = new RegExp(TEMPORAL_KEYWORD_RE.source, "gi");

// 中文／日文／韓文／泰文口語與檢索模板停用詞（長詞優先，避免無害問句詞或模板詞如「推薦」「附近」「食べログ」「맛집」「ที่เที่ยว」把正常新聞過濾為 0）
const CJK_CONVERSATIONAL_STOPWORD_RE =
  /(?:食べログ|맛집|おすすめ|オススメ|ランキング|アクセス|行き方|口コミ|まとめ|人気|観光|グルメ|가볼만한곳|추천|근처|인기|여행|코스|정보|후기|리뷰|어디|알려줘|ที่เที่ยว|ร้านอร่อย|ยอดนิยม|แนะนำ|รีวิว|เที่ยว|ใกล้|最熱門|這附近|有沒有|哪裡有|請問|幫我|推薦|附近|熱門|哪裡|哪家|這裡|這家|這個|這些|那些|一下|什麼|怎麼|可以|介紹|資訊|情報|攻略|心得|評價|行程|必吃|必去|值得|好吃|好玩|這)/g;

// 嚴格僅收錄繁體中文特有字／舊字體（排除日文常用漢字如 個/車/業/旅/飯/館/線/買/開/機/資，避免純日文查詢誤判為 zh-TW）
const ZH_TW_LOCALE_SIGNAL_RE =
  /[這哪麼裡嗎呢吧站營鐵廣劃臺灣體賣關廳點麵訊價樂圓轉樓區號實處邊學國淺澀櫻獨繪氣經驗歡總覽藝藥覺證條專齋燒壽圖萬與對會濱澤驛]/;
const ZH_TW_PHRASE_SIGNAL_RE =
  /(?:推薦|附近|最熱門|必吃|必去|伴手禮|美食|景點|行程|攻略|自由行|好吃|好玩|營業時間|門票|票價|訂位)/;
// 日文新字體特有字（繁體中文不用此字形，輔助識別含「の」等少假名日文查詢）
const JP_SHINJITAI_RE = /[駅浅渋桜図広転売営鉄払読両団県区発変沢楽歳辺観権実焼麺斎寿浜]/;

// 越南語雙層辨識：VIET_UNIQUE_RE 僅含越南語獨有字元（角標 ơ/ư 與 U+1EA0-U+1EF9 聲調母音），
// VIET_SECONDARY_RE 含越南語亦常用但與歐洲語系共用的重音字，需 vietUniqueCount >= 1 && total >= 2 防劫持英文查詢（如 "Best Phở in Hanoi 2026"）
const VIET_UNIQUE_RE = /[ơưƠƯ\u1ea0-\u1ef9]/g;
const VIET_SECONDARY_RE = /[ăđàáâãèéêìíòóôõùúýĂĐÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝ]/g;

// 顯式白名單映射：防未知 locale 字串污染 Wikipedia 主機名或 Accept-Language 標頭
const WIKI_LANG_BY_HL = Object.freeze({
  "zh-TW": "zh",
  ja: "ja",
  ko: "ko",
  th: "th",
  vi: "vi",
  "en-US": "en",
});

const ACCEPT_LANG_BY_HL = Object.freeze({
  "zh-TW": "zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7",
  ja: "ja-JP,ja;q=0.9,en;q=0.7",
  ko: "ko-KR,ko;q=0.9,en;q=0.7",
  th: "th-TH,th;q=0.9,en;q=0.7",
  vi: "vi-VN,vi;q=0.9,en;q=0.7",
  "en-US": "en-US,en;q=0.9",
});

const HANGUL_TRAILING_PARTICLE_RE = /(?:에서|으로|부터|까지|에는|에도)$/;
const PUBLISHER_SEPARATORS = [" - ", " – ", " — ", " | ", " ｜ ", "｜"];
const TRACKING_PARAM_RE = /^(?:utm_.*|fbclid|gclid|oc)$/i;

const LATIN_STOPWORDS = new Set([
  "the", "for", "and", "in", "of", "to", "a", "an", "is", "are", "at", "on", "with",
  "how", "what", "when", "where", "who", "why", "from", "by", "about", "info", "guide",
  "best", "top", "near", "nearby", "things", "visit", "trip", "tour", "blog", "review", "reviews",
  "ngon", "du", "de", "la", "le", "les", "der", "die", "das", "und", "el", "los", "las", "del",
  "ticket", "tickets", "price", "prices", "hours", "opening", "open", "close", "closed",
  "2024", "2025", "2026", "2027", "2028",
  // 後端雙軌模板注入之論壇／泛用旅遊詞（不可作為新聞主題核心詞，避免離題業配憑 ptt/dcard 繞過相關性過濾）
  "ptt", "dcard", "pantip", "openrice", "eater", "reddit",
  "travel", "local", "tips", "recommendations", "recommendation", "hidden", "gems", "street", "food",
  "japantravel", "koreatravel", "thailandtourism", "singaporetravel", "vietnamtravel", "traveleurope", "hongkongtravel",
]);

/**
 * 雙端對稱 Unicode 正規化：
 * 先截斷 500 字元並做 NFC 確保韓文音節與日文濁音不被拆裂，
 * 僅對拉丁字系片段執行 NFD 去結合音標與歐陸／越語／土語特殊字母折疊，最後轉小寫。
 * @param {string} [str]
 * @returns {string}
 */
function normalizeForMatch(str) {
  return String(str || "")
    .slice(0, MAX_QUERY_ANALYZE_LEN)
    .normalize("NFC")
    .replace(/\p{Script=Latin}[\p{Script=Latin}\u0300-\u036f]*/gu, (seg) =>
      seg
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[đð]/gi, "d")
        .replace(/ø/gi, "o")
        .replace(/ł/gi, "l")
        .replace(/ı/g, "i")
        .replace(/[ßẞ]/g, "ss")
        .replace(/æ/gi, "ae")
        .replace(/œ/gi, "oe")
    )
    .toLowerCase();
}

function hasTemporalKeyword(query) {
  return TEMPORAL_KEYWORD_RE.test(normalizeForMatch(query));
}

/**
 * @param {string} [query]
 * @returns {{ hl: string; gl: string; ceid: string }}
 */
function resolveNewsLocale(query) {
  const q = String(query || "").slice(0, MAX_QUERY_ANALYZE_LEN).normalize("NFC");
  // 剝除後端繁中在地模板注入的「食べログ」「맛집」再計算字系比例，避免單一外來詞誤導語系
  const qForLocale = q.replace(/食べログ|맛집/g, " ");
  const kanaCount = (qForLocale.match(/[\u3040-\u30ff]/g) || []).length;
  const nonNoKanaCount = (qForLocale.replace(/の/g, "").match(/[\u3040-\u30ff]/g) || []).length;
  const hanCount = (qForLocale.match(/[\u4e00-\u9fff]/g) || []).length;
  const hangulCount = (qForLocale.match(/[\uac00-\ud7af]/g) || []).length;
  const thaiCount = (qForLocale.match(/[\u0e00-\u0e7f]/g) || []).length;
  const vietUniqueCount = (qForLocale.match(VIET_UNIQUE_RE) || []).length;
  const vietSecondaryCount = (qForLocale.match(VIET_SECONDARY_RE) || []).length;
  const hasZhTwSignal = ZH_TW_LOCALE_SIGNAL_RE.test(qForLocale) || ZH_TW_PHRASE_SIGNAL_RE.test(qForLocale);
  const hasJpShinjitai = JP_SHINJITAI_RE.test(qForLocale);

  // 無歧義非中日字系（韓/泰/越）：必同時守衛 !hasZhTwSignal && hanCount === 0 && kanaCount === 0，
  // 防止繁中或純假名日文混外來詞遭劫持
  if (!hasZhTwSignal && hanCount === 0 && kanaCount === 0) {
    if (hangulCount > 0) {
      return { hl: "ko", gl: "KR", ceid: "KR:ko" };
    }
    if (thaiCount >= 2) {
      return { hl: "th", gl: "TH", ceid: "TH:th" };
    }
    if (vietUniqueCount >= 1 && (vietUniqueCount + vietSecondaryCount) >= 2) {
      return { hl: "vi", gl: "VN", ceid: "VN:vi" };
    }
  }

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
      return Number.isFinite(code) && code >= 0 && code <= 0x10ffff ? String.fromCodePoint(code) : "";
    })
    .replace(/&#(\d+);/g, (_, num) => {
      const code = parseInt(num, 10);
      return Number.isFinite(code) && code >= 0 && code <= 0x10ffff ? String.fromCodePoint(code) : "";
    });
}

/**
 * @param {string} [query]
 * @returns {string[]}
 */
function extractCoreTokens(query) {
  const cleaned = normalizeForMatch(query)
    .replace(/site:\S+/gi, " ")
    .replace(TEMPORAL_KEYWORD_STRIP_RE, " ")
    .replace(CJK_CONVERSATIONAL_STOPWORD_RE, " ");

  const tokens = new Set();

  // 1. CJK runs -> bigrams (or exact run if length 1-2)
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

  // 2. Korean Hangul runs -> 詞幹替換（去常見 2 字助詞，避免雙寫稀釋命中比例）
  const hangulRuns = cleaned.match(/[\uac00-\ud7af]{2,}/g) || [];
  for (const run of hangulRuns) {
    if (run.length >= 4 && HANGUL_TRAILING_PARTICLE_RE.test(run)) {
      const stem = run.replace(HANGUL_TRAILING_PARTICLE_RE, "");
      tokens.add(stem.length >= 2 ? stem : run);
    } else {
      tokens.add(run);
    }
  }

  // 3. Thai runs -> 長度 <= 6 收整段，否則取 4 字滑動視窗（單段最多 12 個 token）
  const thaiRuns = cleaned.match(/[\u0e00-\u0e7f]{2,}/g) || [];
  for (const run of thaiRuns) {
    if (run.length <= 6) {
      tokens.add(run);
    } else {
      let added = 0;
      for (let i = 0; i <= run.length - 4 && added < 12; i++) {
        tokens.add(run.slice(i, i + 4));
        added += 1;
      }
    }
  }

  // 4. 先遮罩東亞字系（CJK/Hangul/Thai）再抽其餘 Unicode 字母／數字（保留如 "台北101" 之 "101"）
  const nonEastAsian = cleaned.replace(
    /[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af\u0e00-\u0e7f]+/g,
    " "
  );
  const unicodeWordMatches = nonEastAsian.match(/[\p{L}\p{N}][\p{L}\p{N}\p{M}]+/gu) || [];
  for (const w of unicodeWordMatches) {
    if (!LATIN_STOPWORDS.has(w)) {
      tokens.add(w);
    }
  }

  return Array.from(tokens);
}

function isRelevantTitle(query, candidateText, minRatio = 0.5) {
  const qNorm = normalizeForMatch(query).replace(/site:\S+/gi, "").trim();
  const cNorm = normalizeForMatch(candidateText).trim();
  if (!qNorm || !cNorm) return false;
  // Direct containment check for clean short names (e.g. "東京鐵塔", "東京", "München")
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

/**
 * @param {string} query
 * @param {string} title
 * @param {string} [sourceName]
 * @param {string[] | null} [precomputedTokens]
 * @returns {boolean}
 */
function isRelevantNewsItem(query, title, sourceName = "", precomputedTokens = null) {
  const combined = sourceName
    ? `${normalizeForMatch(title)} ${normalizeForMatch(sourceName)}`
    : normalizeForMatch(title);
  const tokens = Array.isArray(precomputedTokens) ? precomputedTokens : extractCoreTokens(query);
  if (tokens.length === 0) return true;
  let hits = 0;
  for (const tok of tokens) {
    if (combined.includes(tok)) hits += 1;
  }
  if (tokens.length === 1) return hits >= 1;
  return hits >= Math.max(1, Math.ceil(tokens.length * 0.34));
}

function stripTrailingPublisher(title) {
  const raw = String(title || "").slice(0, MAX_QUERY_ANALYZE_LEN).normalize("NFC").trim();
  if (!raw) return "";
  let bestIdx = -1;
  let bestSepLen = 0;
  for (const sep of PUBLISHER_SEPARATORS) {
    const idx = raw.lastIndexOf(sep);
    if (idx > bestIdx) {
      bestIdx = idx;
      bestSepLen = sep.length;
    }
  }
  if (bestIdx > 0) {
    const head = raw.slice(0, bestIdx).trim();
    const tail = raw.slice(bestIdx + bestSepLen).trim();
    if (head.length >= 4 && tail.length >= 1 && tail.length <= 40) {
      return head;
    }
  }
  return raw;
}

function canonicalizeUrl(rawUrl) {
  const trimmed = String(rawUrl || "").trim();
  if (!trimmed) return "";
  try {
    const u = new URL(trimmed);
    u.protocol = u.protocol.toLowerCase();
    u.hostname = u.hostname.toLowerCase();
    u.hash = "";
    for (const key of Array.from(u.searchParams.keys())) {
      if (TRACKING_PARAM_RE.test(key)) {
        u.searchParams.delete(key);
      }
    }
    u.searchParams.sort();
    const cleanPath = u.pathname.replace(/\/+$/, "") || "/";
    const search = u.searchParams.toString();
    const port = u.port ? `:${u.port}` : "";
    return `${u.protocol}//${u.hostname}${port}${cleanPath}${search ? `?${search}` : ""}`;
  } catch {
    return trimmed.toLowerCase().replace(/\/+$/, "");
  }
}

function normalizeRawTitleFingerprint(title) {
  return normalizeForMatch(title).replace(/[^\p{L}\p{N}]/gu, "");
}

function normalizeTitleFingerprint(title) {
  const stripped = stripTrailingPublisher(title);
  return normalizeRawTitleFingerprint(stripped);
}

function isDuplicateTitleFingerprint(fp, seenFingerprints) {
  if (!fp || fp.length < 8) return false;
  for (const seen of seenFingerprints) {
    if (fp === seen) return true;
    const minLen = Math.min(fp.length, seen.length);
    const maxLen = Math.max(fp.length, seen.length);
    if (minLen >= 10 && minLen / maxLen >= 0.75 && (fp.includes(seen) || seen.includes(fp))) {
      return true;
    }
  }
  return false;
}

/**
 * 雙鍵去重合併：DDG 前 limit 筆為主，RSS 補入最多 maxRssSupplement (預設 2) 筆不重複新聞；
 * 同步記錄去尾詞與原始標題指紋（解「標題｜副標」vs「標題｜副標 - 媒體」不對稱問題），
 * 並將收錄之 RSS 項目寫回 seenUrls 與 seenTitleFingerprints 防止新聞聯播重複。
 * @param {Array<{ title?: string; snippet?: string; url?: string }>} ddgResults
 * @param {Array<{ title?: string; snippet?: string; url?: string }>} newsResults
 * @param {number} limit
 * @param {number} [maxRssSupplement]
 * @returns {{ results: Array<{ title?: string; snippet?: string; url?: string }>; source: string }}
 */
function mergeDualSourceResults(ddgResults, newsResults, limit, maxRssSupplement = RSS_SUPPLEMENT_MAX) {
  const safeLimit = Number.isFinite(limit) ? Math.max(0, Math.floor(limit)) : 0;
  const safeMaxRss = Number.isFinite(maxRssSupplement)
    ? Math.max(0, Math.floor(maxRssSupplement))
    : RSS_SUPPLEMENT_MAX;
  const safeDdg = Array.isArray(ddgResults) ? ddgResults.slice(0, safeLimit) : [];
  const safeNews = Array.isArray(newsResults) ? newsResults : [];
  const seenUrls = new Set();
  const seenTitleFingerprints = [];
  const merged = [];
  let addedDdg = 0;

  const recordTitleFingerprints = (title) => {
    const fp = normalizeTitleFingerprint(title);
    if (fp.length >= 8) seenTitleFingerprints.push(fp);
    const rawFp = normalizeRawTitleFingerprint(title);
    if (rawFp.length >= 8 && rawFp !== fp) seenTitleFingerprints.push(rawFp);
  };

  for (const item of safeDdg) {
    if (!item) continue;
    merged.push(item);
    addedDdg += 1;
    const canonUrl = canonicalizeUrl(item.url);
    if (canonUrl) seenUrls.add(canonUrl);
    recordTitleFingerprints(item.title);
  }

  let addedNews = 0;
  for (const item of safeNews) {
    if (addedNews >= safeMaxRss) break;
    if (!item || !item.url) continue;
    const canonUrl = canonicalizeUrl(item.url);
    if (canonUrl && seenUrls.has(canonUrl)) continue;
    const fp = normalizeTitleFingerprint(item.title);
    if (isDuplicateTitleFingerprint(fp, seenTitleFingerprints)) continue;

    merged.push(item);
    if (canonUrl) seenUrls.add(canonUrl);
    recordTitleFingerprints(item.title);
    addedNews += 1;
  }

  const source =
    addedDdg > 0
      ? (addedNews > 0 ? "ddg+google_news_rss" : "ddg")
      : (addedNews > 0 ? "google_news_rss" : "none");

  return { results: merged, source };
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
      resp.body?.cancel?.()?.catch?.(() => {});
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
      resp.body?.cancel?.()?.catch?.(() => {});
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

async function fetchGoogleNewsRSS(q, limit, timeoutMs = 2800, externalSignal = null, locale = null) {
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
    const { hl, gl, ceid } = locale || resolveNewsLocale(q);

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
    if (resp.status !== 200) {
      resp.body?.cancel?.()?.catch?.(() => {});
      return [];
    }

    const xml = await resp.text();
    const coreTokens = extractCoreTokens(q);
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
      if (!isRelevantNewsItem(q, title, sourceName, coreTokens)) continue;

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

async function fetchDDGLite(q, limit, timeoutMs = 2800, locale = null) {
  try {
    const effectiveLocale = locale || resolveNewsLocale(q);
    const acceptLanguage = Object.prototype.hasOwnProperty.call(ACCEPT_LANG_BY_HL, effectiveLocale.hl)
      ? ACCEPT_LANG_BY_HL[effectiveLocale.hl]
      : ACCEPT_LANG_BY_HL["en-US"];
    const resp = await fetch("https://lite.duckduckgo.com/lite/", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": BROWSER_USER_AGENT,
        "Accept-Language": acceptLanguage,
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      },
      body: new URLSearchParams({ q }).toString(),
      signal: AbortSignal.timeout(timeoutMs),
    });
    // Strictly require HTTP 200 (reject HTTP 202 anti-bot CAPTCHA pages)
    if (resp.status !== 200) {
      resp.body?.cancel?.()?.catch?.(() => {});
      return [];
    }

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
    const seenUrls = new Set();
    const seenRawTitleFps = new Set();
    for (let i = 0; i < allAnchors.length && list.length < limit; i++) {
      const cur = allAnchors[i];
      if (cur.isAd) continue;
      const canonUrl = canonicalizeUrl(cur.url);
      if (canonUrl && seenUrls.has(canonUrl)) continue;
      const rawFp = normalizeRawTitleFingerprint(cur.title);
      if (rawFp.length >= 8 && seenRawTitleFps.has(rawFp)) continue;
      const sliceEnd = i + 1 < allAnchors.length ? allAnchors[i + 1].start : html.length;
      const segment = html.slice(cur.end, sliceEnd);
      const snipMatch = segment.match(singleSnippetRegex);
      const snippet = snipMatch
        ? decodeXmlEntities(snipMatch[1].replace(/<[^>]+>/g, "")).replace(/\s+/g, " ").trim()
        : "";
      if (canonUrl) seenUrls.add(canonUrl);
      if (rawFp.length >= 8) seenRawTitleFps.add(rawFp);
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

async function fetchConditionalWiki(q, limit, locale = null) {
  if (hasTemporalKeyword(q)) return [];
  try {
    const effectiveLocale = locale || resolveNewsLocale(q);
    const wikiLang = Object.prototype.hasOwnProperty.call(WIKI_LANG_BY_HL, effectiveLocale.hl)
      ? WIKI_LANG_BY_HL[effectiveLocale.hl]
      : "en";
    const wikiUrl = `https://${wikiLang}.wikipedia.org/w/api.php?action=query&list=search&srsearch=${encodeURIComponent(q)}&srlimit=${Math.min(limit + 2, 10)}&format=json`;
    const resp = await fetch(wikiUrl, {
      headers: {
        "User-Agent": OUTBOUND_USER_AGENT,
        Accept: "application/json",
      },
      signal: AbortSignal.timeout(1200),
    });
    if (resp.status !== 200) {
      resp.body?.cancel?.()?.catch?.(() => {});
      return [];
    }
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

export {
  resolveNewsLocale,
  normalizeForMatch,
  extractCoreTokens,
  isRelevantNewsItem,
  mergeDualSourceResults,
};

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

      // 單次解析語系並共用至 DDG、Google News RSS 與條件維基
      const locale = resolveNewsLocale(q);

      // 優先鏈 2: 免 Key 並行競速 + 短寬限窗雙源合併 (DDG Lite 200-only 2500ms || Google News RSS 2800ms)
      // 選項 A：DDG 前 limit 筆為主 + RSS 補最多 2 筆不重複新聞；DDG 早歸最多再等 RSS 600ms（總預算 1800ms）防隊頭阻塞
      const raceStartMs = Date.now();
      const rssController = new AbortController();
      const rssFetchLimit = Math.min(limit + RSS_SUPPLEMENT_MAX, 10);
      let rssSettled = false;
      let rssOutcome = [];

      const ddgPromise = fetchDDGLite(q, limit, 2500, locale);
      const rssTracked = fetchGoogleNewsRSS(q, rssFetchLimit, 2800, rssController.signal, locale)
        .then((res) => {
          rssSettled = true;
          rssOutcome = Array.isArray(res) ? res : [];
          return rssOutcome;
        })
        .catch(() => {
          rssSettled = true;
          rssOutcome = [];
          return rssOutcome;
        });

      const ddgResults = await ddgPromise;
      if (ddgResults.length > 0) {
        let newsResults = [];
        if (rssSettled) {
          newsResults = rssOutcome;
        } else {
          const elapsed = Date.now() - raceStartMs;
          const graceMs = Math.min(
            RSS_GRACE_AFTER_DDG_MS,
            Math.max(0, RSS_TOTAL_BUDGET_WHEN_DDG_OK_MS - elapsed)
          );
          if (graceMs > 0) {
            let graceTimerId;
            try {
              const raceWinner = await Promise.race([
                rssTracked,
                new Promise((resolve) => {
                  graceTimerId = setTimeout(() => resolve(GRACE_TIMEOUT), graceMs);
                }),
              ]);
              if (raceWinner === GRACE_TIMEOUT) {
                rssController.abort();
                newsResults = [];
              } else {
                newsResults = Array.isArray(raceWinner) ? raceWinner : [];
              }
            } finally {
              clearTimeout(graceTimerId);
            }
          } else {
            rssController.abort();
            newsResults = [];
          }
        }
        return jsonResponse(mergeDualSourceResults(ddgResults, newsResults, limit));
      }

      const newsResults = await rssTracked;
      if (newsResults.length > 0) {
        const dedupedNews = mergeDualSourceResults([], newsResults, 0, limit);
        if (dedupedNews.results.length > 0) {
          return jsonResponse(dedupedNews);
        }
      }

      // 優先鏈 4: 條件維基 (含時效詞禁走 + 嚴格標題相關性門檻；未達標回空)
      const wikiResults = await fetchConditionalWiki(q, limit, locale);
      if (wikiResults.length > 0) {
        return jsonResponse({ results: wikiResults, source: "wikipedia" });
      }

      return jsonResponse({ results: [], source: "none" });
    }

    return jsonResponse({ status: "Tabidachi Search Proxy Ready" });
  },
};
