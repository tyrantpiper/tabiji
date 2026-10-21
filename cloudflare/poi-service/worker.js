/**
 * Tabidachi Cloudflare POI Service (poi-service)
 * 邊緣全局景點庫微服務：支援 Google Maps 共享清單/單點解析與 D1 雲端持久化
 */

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-User-ID, Authorization",
};

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      ...CORS_HEADERS,
      "Content-Type": "application/json; charset=utf-8",
    },
  });
}

const UUID_V4_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function extractUserId(request) {
  const xUser = request.headers.get("X-User-ID");
  if (xUser && UUID_V4_REGEX.test(xUser.trim())) {
    return xUser.trim();
  }

  const auth = request.headers.get("Authorization");
  if (auth && auth.startsWith("Bearer ")) {
    try {
      const parts = auth.split(" ")[1].split(".");
      if (parts.length === 3) {
        const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
        if (payload && payload.sub && UUID_V4_REGEX.test(String(payload.sub).trim())) {
          return String(payload.sub).trim();
        }
      }
    } catch {}
  }

  return null;
}

// 🛡️ 符合官方 D1 規範的批次寫入 (嚴格 <= 90 筆原子分塊，杜絕 100 條語句上限)
async function batchInsertPois(db, userId, places, rawUrl) {
  const now = Date.now();
  const CHUNK_SIZE = 90;
  const allInserted = [];

  // 🛡️ 座標防禦過濾：嚴格剔除缺少合法數值經緯度的項目，防止 D1 NOT NULL 約束崩潰
  const validPlaces = (places || []).filter(
    (p) => p && typeof p.lat === "number" && typeof p.lng === "number" && !Number.isNaN(p.lat) && !Number.isNaN(p.lng)
  );

  if (validPlaces.length === 0) {
    return [];
  }

  for (let i = 0; i < validPlaces.length; i += CHUNK_SIZE) {
    const chunk = validPlaces.slice(i, i + CHUNK_SIZE);
    const statements = chunk.map((p) => {
      const id = crypto.randomUUID();
      return db.prepare(`
        INSERT INTO user_poi_pool (
          id, user_id, title, address, lat, lng, google_place_id,
          category, rating, user_notes, source_url, is_pinned, pin_color, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, lat, lng) DO UPDATE SET
          title = CASE 
            WHEN user_poi_pool.source_url IS NULL OR user_poi_pool.source_url = excluded.source_url THEN excluded.title 
            ELSE user_poi_pool.title 
          END,
          address = COALESCE(excluded.address, user_poi_pool.address),
          user_notes = COALESCE(excluded.user_notes, user_poi_pool.user_notes),
          source_url = COALESCE(excluded.source_url, user_poi_pool.source_url),
          updated_at = excluded.updated_at
        RETURNING *
      `).bind(
        id,
        userId,
        p.title || "景點地點",
        p.address || null,
        p.lat,
        p.lng,
        p.google_place_id || null,
        p.category || "attraction",
        p.rating || null,
        p.user_notes || null,
        p.source_url || rawUrl,
        1,
        "#E56E25",
        now,
        now
      );
    });

    const batchResults = await db.batch(statements);
    for (const res of batchResults) {
      if (res.results && res.results.length > 0) {
        allInserted.push(...res.results);
      }
    }
  }

  return allInserted;
}

function sanitizeUrl(raw) {
  if (!raw || typeof raw !== "string") return null;
  const match = raw.match(/(https?:\/\/[^\s]+)/);
  if (!match) return null;
  return match[1].replace(/[.,!?:;"'。，！？]+$/, "");
}

function isGoogleMapsUrl(urlStr) {
  try {
    const u = new URL(urlStr);
    if (u.protocol !== "https:" && u.protocol !== "http:") return false;
    const host = u.hostname.toLowerCase();
    return (
      host === "maps.app.goo.gl" ||
      host === "goo.gl" ||
      host === "google.com" ||
      host.endsWith(".google.com") ||
      host === "maps.google.com" ||
      host.endsWith(".google.co.jp") ||
      host.endsWith(".google.com.tw")
    );
  } catch {
    return false;
  }
}

// 🌐 跟隨 302 重定向取得最終網址
async function followRedirects(url, maxRedirects = 5) {
  let currentUrl = url;
  for (let i = 0; i < maxRedirects; i++) {
    const resp = await fetch(currentUrl, {
      method: "GET",
      redirect: "manual",
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      },
    });

    const status = resp.status;
    if (status === 301 || status === 302 || status === 303 || status === 307 || status === 308) {
      const location = resp.headers.get("Location");
      if (location) {
        currentUrl = new URL(location, currentUrl).toString();
        continue;
      }
    }

    return { finalUrl: currentUrl, response: resp };
  }
  return { finalUrl: currentUrl, response: null };
}

// 🔍 解析 Google Maps 網址 (單點或共享清單)
async function parseGoogleMapsLink(rawInput) {
  const cleanUrl = sanitizeUrl(rawInput);
  if (!cleanUrl || !isGoogleMapsUrl(cleanUrl)) {
    throw new Error("INVALID_MAPS_URL");
  }

  const { finalUrl, response } = await followRedirects(cleanUrl);
  const places = [];

  // A. 判定是否為共享清單 (Placelists)
  if (finalUrl.includes("/placelists/list/") || finalUrl.includes("/placelists/")) {
    let html = "";
    if (response) {
      html = await response.text();
    } else {
      const fetchResp = await fetch(finalUrl, {
        headers: {
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
          "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        },
      });
      html = await fetchResp.text();
    }

    // 正則匹配 coordinates
    const coordMatches = [...html.matchAll(/\[null,\s*null,\s*(-?\d+\.\d+),\s*(-?\d+\.\d+)\]/g)];
    const titleMatches = [...html.matchAll(/"([^"]{2,60})",null,null,null,null,\[null,null,(-?\d+\.\d+),(-?\d+\.\d+)\]/g)];
    const placeIdMatches = [...html.matchAll(/ChIJ[A-Za-z0-9_-]{23,}/g)];

    if (titleMatches.length > 0) {
      for (const m of titleMatches) {
        const title = m[1];
        const lat = parseFloat(m[2]);
        const lng = parseFloat(m[3]);
        if (!isNaN(lat) && !isNaN(lng) && lat !== 0 && lng !== 0) {
          places.push({
            title: title.replace(/\\"/g, '"').trim(),
            lat,
            lng,
            source_url: finalUrl,
            category: "attraction",
          });
        }
      }
    } else if (coordMatches.length > 0) {
      // 容錯提取：若未匹配到標準結構，利用座標提取去重
      const seen = new Set();
      let index = 1;
      for (const m of coordMatches) {
        const lat = parseFloat(m[1]);
        const lng = parseFloat(m[2]);
        const key = `${lat.toFixed(4)},${lng.toFixed(4)}`;
        if (!seen.has(key) && !isNaN(lat) && !isNaN(lng) && lat !== 0 && lng !== 0) {
          seen.add(key);
          places.push({
            title: `景點地點 #${index++}`,
            lat,
            lng,
            source_url: finalUrl,
            category: "attraction",
          });
        }
      }
    }
  }

  // B. 若為單一地點或 Placelist 萃取無果時，降級提取單點座標
  if (places.length === 0) {
    let lat = null;
    let lng = null;
    let title = "已儲存地點";

    // 1. 座標模式 @lat,lng
    const matchA = finalUrl.match(/@(-?\d+\.\d+),(-?\d+\.\d+)/);
    if (matchA) {
      lat = parseFloat(matchA[1]);
      lng = parseFloat(matchA[2]);
    }

    // 2. 座標模式 !3dlat!4dlng
    if (!lat) {
      const matchB = finalUrl.match(/!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/);
      if (matchB) {
        lat = parseFloat(matchB[1]);
        lng = parseFloat(matchB[2]);
      }
    }

    // 3. 名稱模式 /place/NAME/
    const placeMatch = finalUrl.match(/\/place\/([^/@?]+)/);
    if (placeMatch) {
      try {
        title = decodeURIComponent(placeMatch[1].replace(/\+/g, " "));
      } catch {}
    }

    if (lat !== null && lng !== null && !isNaN(lat) && !isNaN(lng)) {
      places.push({
        title,
        lat,
        lng,
        source_url: cleanUrl,
        category: "attraction",
      });
    }
  }

  return places;
}

export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    const url = new URL(request.url);
    const pathname = url.pathname;
    const userId = extractUserId(request);
    if (!userId) {
      return jsonResponse({ error: "Unauthorized: Invalid or missing X-User-ID (RFC 4122 UUIDv4 required)" }, 401);
    }

    try {
      // 1. GET /api/poi/all - 查詢使用者所有收藏地點 (100% 命中 idx_poi_user_created 索引)
      if (pathname === "/api/poi/all" && request.method === "GET") {
        const stmt = env.DB.prepare(
          "SELECT * FROM user_poi_pool WHERE user_id = ? ORDER BY created_at DESC LIMIT 500"
        ).bind(userId);
        const { results } = await stmt.all();
        return jsonResponse(results || []);
      }

      // 2. POST /api/poi/import-link - 貼上連結解析並以 D1 batch 原子分塊寫入
      if (pathname === "/api/poi/import-link" && request.method === "POST") {
        const body = await request.json().catch(() => ({}));
        const rawUrl = body.url;
        if (!rawUrl) {
          return jsonResponse({ success: false, error: "Missing url parameter" }, 400);
        }

        const parsedPlaces = await parseGoogleMapsLink(rawUrl);
        if (parsedPlaces.length === 0) {
          return jsonResponse({ success: false, error: "無法從該連結提取到有效座標" }, 422);
        }

        const insertedItems = await batchInsertPois(env.DB, userId, parsedPlaces, rawUrl);

        return jsonResponse({
          success: true,
          count: insertedItems.length,
          items: insertedItems,
        });
      }

      // 2.5. POST /api/poi/batch-save - 接收已解析的標準 POI 清單並以 D1 batch 原子分塊寫入
      if (pathname === "/api/poi/batch-save" && request.method === "POST") {
        const body = await request.json().catch(() => ({}));
        const items = body.items;
        if (!Array.isArray(items) || items.length === 0) {
          return jsonResponse({ success: false, error: "Empty or invalid items array" }, 400);
        }

        const insertedItems = await batchInsertPois(env.DB, userId, items, items[0]?.source_url || "");
        return jsonResponse({
          success: true,
          count: insertedItems.length,
          items: insertedItems,
        });
      }

      // 3. POST /api/poi/add - 自訂手動新增景點
      if (pathname === "/api/poi/add" && request.method === "POST") {
        const body = await request.json().catch(() => ({}));
        if (!body.title || body.lat === undefined || body.lng === undefined) {
          return jsonResponse({ success: false, error: "Missing required fields" }, 400);
        }

        const now = Date.now();
        const id = crypto.randomUUID();
        const stmt = env.DB.prepare(`
          INSERT INTO user_poi_pool (
            id, user_id, title, address, lat, lng, google_place_id,
            category, rating, user_notes, source_url, is_pinned, pin_color, created_at, updated_at
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          ON CONFLICT(user_id, lat, lng) DO UPDATE SET
            title = excluded.title,
            user_notes = excluded.user_notes,
            updated_at = excluded.updated_at
          RETURNING *
        `).bind(
          id,
          userId,
          body.title,
          body.address || null,
          body.lat,
          body.lng,
          body.google_place_id || null,
          body.category || "attraction",
          body.rating || null,
          body.user_notes || null,
          body.source_url || null,
          body.is_pinned !== undefined ? (body.is_pinned ? 1 : 0) : 1,
          body.pin_color || "#E56E25",
          now,
          now
        );

        const created = await stmt.first();
        return jsonResponse(created);
      }

      // 4. PATCH /api/poi/:id/note - 編輯使用者備註
      const noteMatch = pathname.match(/^\/api\/poi\/([^/]+)\/note$/);
      if (noteMatch && request.method === "PATCH") {
        const id = noteMatch[1];
        const body = await request.json().catch(() => ({}));
        const now = Date.now();
        const stmt = env.DB.prepare(
          "UPDATE user_poi_pool SET user_notes = ?, updated_at = ? WHERE id = ? AND user_id = ? RETURNING *"
        ).bind(body.note || "", now, id, userId);
        const updated = await stmt.first();
        return jsonResponse(updated || { id, user_notes: body.note });
      }

      // 5. PATCH /api/poi/:id/pin - 切換地圖釘選
      const pinMatch = pathname.match(/^\/api\/poi\/([^/]+)\/pin$/);
      if (pinMatch && request.method === "PATCH") {
        const id = pinMatch[1];
        const body = await request.json().catch(() => ({}));
        const now = Date.now();
        const isPinnedVal = body.is_pinned ? 1 : 0;
        const stmt = env.DB.prepare(
          "UPDATE user_poi_pool SET is_pinned = ?, updated_at = ? WHERE id = ? AND user_id = ? RETURNING *"
        ).bind(isPinnedVal, now, id, userId);
        const updated = await stmt.first();
        return jsonResponse(updated || { id, is_pinned: isPinnedVal });
      }

      // 5.5. PATCH /api/poi/:id/category - 切換地點分類
      const catMatch = pathname.match(/^\/api\/poi\/([^/]+)\/category$/);
      if (catMatch && request.method === "PATCH") {
        const id = catMatch[1];
        const body = await request.json().catch(() => ({}));
        const now = Date.now();
        // 🛡️ 放行標準 7 大類別與合規之自訂協定 custom:<emoji>:<name>:<color>
        const isValidCategory = (cat) => {
          if (typeof cat !== "string") return false;
          const standardCategories = ["attraction", "food", "cafe", "shopping", "hotel", "transport", "other"];
          if (standardCategories.includes(cat)) return true;
          return cat.startsWith("custom:") && cat.split(":").length >= 4;
        };
        const category = isValidCategory(body.category) ? body.category : "attraction";
        const stmt = env.DB.prepare(
          "UPDATE user_poi_pool SET category = ?, updated_at = ? WHERE id = ? AND user_id = ? RETURNING *"
        ).bind(category, now, id, userId);
        const updated = await stmt.first();
        return jsonResponse(updated || { id, category });
      }

      // 6. DELETE /api/poi/:id - 刪除景點
      const delMatch = pathname.match(/^\/api\/poi\/([^/]+)$/);
      if (delMatch && request.method === "DELETE") {
        const id = delMatch[1];
        const stmt = env.DB.prepare(
          "DELETE FROM user_poi_pool WHERE id = ? AND user_id = ?"
        ).bind(id, userId);
        await stmt.run();
        return jsonResponse({ success: true, id });
      }

      return jsonResponse({ error: "Endpoint Not Found" }, 404);
    } catch (err) {
      console.error("[poi-service] Internal error:", err);
      return jsonResponse({ error: err.message || "Internal Server Error" }, 500);
    }
  },
};
