// @ts-nocheck
import "jsr:@supabase/functions-js/edge-runtime.d.ts";

/**
 * Pure-Deno Cloudinary asset cleanup Edge Function (zero Node SDK / sandbox compatibility dependencies).
 * Uses Web Crypto SHA-1 Admin/Upload destroy signature so it runs natively on Supabase Edge Runtime.
 */

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-webhook-secret, x-webhook-timestamp, x-webhook-signature",
};

function getEnv(name: string): string {
  if (typeof Deno !== "undefined" && Deno?.env && typeof Deno.env.get === "function") {
    return Deno.env.get(name) || "";
  }
  return "";
}

function timingSafeEqual(a: string, b: string): boolean {
  const enc = new TextEncoder();
  const ab = enc.encode(a);
  const bb = enc.encode(b);
  if (ab.length !== bb.length) return false;
  let diff = 0;
  for (let i = 0; i < ab.length; i++) {
    diff |= ab[i] ^ bb[i];
  }
  return diff === 0;
}

function isPlainObject(val: unknown): val is Record<string, unknown> {
  return Boolean(val) && typeof val === "object" && !Array.isArray(val);
}

function parseJsonIfString(val: unknown): unknown {
  if (typeof val !== "string") return val;
  const trimmed = val.trim();
  if (
    (trimmed.startsWith("[") && trimmed.endsWith("]")) ||
    (trimmed.startsWith("{") && trimmed.endsWith("}"))
  ) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return val;
    }
  }
  return val;
}

const JWT_SEGMENT_RE = /^[A-Za-z0-9_-]+=*$/;

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  if (!token || /[\s\r\n]/.test(token)) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  if (!parts.every((part) => part.length > 0 && JWT_SEGMENT_RE.test(part))) return null;
  try {
    let b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/").replace(/=+$/, "");
    const pad = b64.length % 4;
    if (pad === 1) return null;
    if (pad > 0) b64 += "=".repeat(4 - pad);
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) {
      bytes[i] = bin.charCodeAt(i);
    }
    const parsed = JSON.parse(new TextDecoder().decode(bytes));
    return isPlainObject(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function isValidServiceRoleJwtClaims(payload: Record<string, unknown> | null): boolean {
  if (!payload) return false;
  if (payload.role !== "service_role") return false;
  const exp = payload.exp;
  if (typeof exp !== "number" || !Number.isFinite(exp)) return false;
  const nowSec = Math.floor(Date.now() / 1000);
  if (exp <= nowSec) return false;
  if (payload.nbf !== undefined) {
    if (typeof payload.nbf !== "number" || !Number.isFinite(payload.nbf) || payload.nbf > nowSec) {
      return false;
    }
  }
  return true;
}

async function verifyServiceRoleTokenViaGoTrue(token: string, supabaseUrl: string): Promise<boolean> {
  const baseUrl = supabaseUrl.trim().replace(/\/+$/, "");
  if (!baseUrl) return false;
  let parsedUrl: URL;
  try {
    parsedUrl = new URL(baseUrl);
  } catch {
    return false;
  }
  if (parsedUrl.protocol !== "https:" && parsedUrl.protocol !== "http:") {
    return false;
  }

  const payload = decodeJwtPayload(token);
  if (!isValidServiceRoleJwtClaims(payload)) return false;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000);
  try {
    const resp = await fetch(`${baseUrl}/auth/v1/admin/users?page=1&per_page=1`, {
      method: "GET",
      headers: {
        apikey: token,
        Authorization: `Bearer ${token}`,
      },
      signal: controller.signal,
    });
    await resp.body?.cancel().catch(() => {});
    return resp.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeoutId);
  }
}

const MAX_SIGNED_WEBHOOK_BYTES = 1024 * 1024;
const WEBHOOK_SIGNATURE_MAX_SKEW_SEC = 300;
const WEBHOOK_TIMESTAMP_RE = /^\d{10,13}$/;
const WEBHOOK_SIG_HEX64_RE = /^[0-9a-f]{64}$/i;

function resolveSupabaseInternalApiKeys(): string[] {
  const candidates: string[] = [];
  const pushUnique = (val: unknown) => {
    if (typeof val !== "string") return;
    const trimmed = val.trim();
    if (trimmed && !candidates.includes(trimmed)) {
      candidates.push(trimmed);
    }
  };

  pushUnique(getEnv("SUPABASE_SERVICE_ROLE_KEY"));
  const secretKeysJson = getEnv("SUPABASE_SECRET_KEYS").trim();
  if (secretKeysJson) {
    try {
      const parsed = JSON.parse(secretKeysJson);
      if (isPlainObject(parsed)) {
        pushUnique(parsed.default);
        for (const val of Object.values(parsed)) {
          pushUnique(val);
        }
      }
    } catch {
      // ignore malformed SUPABASE_SECRET_KEYS JSON
    }
  }
  return candidates;
}

async function verifyWebhookSignatureViaRpc(
  ts: number,
  signatureHex: string,
  rawBody: string,
  supabaseUrl: string
): Promise<boolean> {
  const baseUrl = supabaseUrl.trim().replace(/\/+$/, "");
  if (!baseUrl) return false;
  let parsedUrl: URL;
  try {
    parsedUrl = new URL(baseUrl);
  } catch {
    return false;
  }
  if (parsedUrl.protocol !== "https:" && parsedUrl.protocol !== "http:") {
    return false;
  }

  const keys = resolveSupabaseInternalApiKeys();
  if (keys.length === 0) return false;

  const payloadJson = JSON.stringify({
    p_timestamp: ts,
    p_signature: signatureHex.toLowerCase(),
    p_body: rawBody,
  });

  for (const key of keys) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        apikey: key,
      };
      if (!key.startsWith("sb_secret_")) {
        headers.Authorization = `Bearer ${key}`;
      }
      const resp = await fetch(`${baseUrl}/rest/v1/rpc/verify_cleanup_webhook_signature`, {
        method: "POST",
        headers,
        body: payloadJson,
        signal: controller.signal,
      });
      if (resp.ok) {
        try {
          const verified = await resp.json();
          return verified === true;
        } catch {
          return false;
        }
      }
      await resp.body?.cancel().catch(() => {});
      if (resp.status !== 401 && resp.status !== 403) {
        return false;
      }
    } catch {
      return false;
    } finally {
      clearTimeout(timeoutId);
    }
  }
  return false;
}

export async function signCloudinaryDestroy(
  publicId: string,
  timestamp: number,
  apiSecret: string,
  invalidate = true
): Promise<string> {
  // Cloudinary signature requires parameters sorted alphabetically (excluding file, api_key, resource_type)
  const parts: string[] = [];
  if (invalidate) {
    parts.push("invalidate=true");
  }
  parts.push(`public_id=${publicId}`);
  parts.push(`timestamp=${timestamp}`);
  const payload = `${parts.join("&")}${apiSecret}`;

  const digest = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(payload));
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

const SINGLE_TRANSFORM_SEGMENT_RE =
  /^(?:[wh]_\d+(?:\.\d+)?|c_(?:scale|fit|limit|mfit|fill|lfill|pad|lpad|mpad|fill_pad|crop|thumb|imagga_crop|imagga_scale)|q_(?:auto(?::(?:best|good|eco|low))?|\d+(?::\d+)?)|f_(?:auto|webp|avif|jpg|jpeg|png|gif|svg|pdf|mp4|webm)|dpr_(?:auto|\d+(?:\.\d+)?)|g_(?:auto(?::[a-z_]+)?|face|faces|center|north|south|east|west|north_east|north_west|south_east|south_west)|fl_[a-z0-9_.:-]+|e_[a-z0-9_.:-]+|ar_\d+(?::\d+|\.\d+)?|t_[a-zA-Z0-9_-]+|b_(?:auto(?::[a-z_]+)?|rgb:[0-9a-fA-F]{3,8}|[a-z]+))$/;

function parseCloudinaryUploadPath(pathname: string): string | null {
  const match =
    pathname.match(/^\/[^/]+\/(?:image|video|raw)\/upload\/(.+)$/) ||
    pathname.match(/^\/(?:image|video|raw)\/upload\/(.+)$/) ||
    pathname.match(/^\/upload\/(.+)$/);
  return match ? match[1] : null;
}

function isTransformSegment(seg: string): boolean {
  return seg.includes(",") || SINGLE_TRANSFORM_SEGMENT_RE.test(seg);
}

function resolveCloudinaryCredentials(): { cloudName: string; apiKey: string; apiSecret: string } {
  let cloudName = (
    getEnv("CLOUDINARY_CLOUD_NAME") ||
    getEnv("NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME")
  ).trim();
  let apiKey = (
    getEnv("CLOUDINARY_API_KEY") ||
    getEnv("NEXT_PUBLIC_CLOUDINARY_API_KEY")
  ).trim();
  let apiSecret = getEnv("CLOUDINARY_API_SECRET").trim();

  if (!cloudName || !apiKey || !apiSecret) {
    const cloudinaryUrl = getEnv("CLOUDINARY_URL").trim();
    if (cloudinaryUrl) {
      try {
        const parsed = new URL(cloudinaryUrl);
        if (parsed.protocol === "cloudinary:") {
          if (!cloudName && parsed.hostname) cloudName = decodeURIComponent(parsed.hostname).trim();
          if (!apiKey && parsed.username) apiKey = decodeURIComponent(parsed.username).trim();
          if (!apiSecret && parsed.password) apiSecret = decodeURIComponent(parsed.password).trim();
        }
      } catch {
        // ignore malformed CLOUDINARY_URL
      }
    }
  }
  return { cloudName, apiKey, apiSecret };
}

export function isSafePublicId(val: unknown): val is string {
  if (typeof val !== "string") return false;
  const trimmed = val.trim();
  if (!trimmed || trimmed.length > 256) return false;
  if (trimmed.includes("..") || trimmed.startsWith("/") || trimmed.endsWith("/") || trimmed.includes("//")) {
    return false;
  }
  if (!/^[a-zA-Z0-9_./-]+$/.test(trimmed)) return false;
  return !trimmed.split("/").some((seg) => seg === "" || seg === "." || seg === "..");
}

export function isCloudinaryUrl(val: unknown): val is string {
  if (typeof val !== "string") return false;
  const trimmed = val.trim();
  if (!trimmed) return false;
  try {
    const u = new URL(trimmed);
    if (u.protocol !== "https:" && u.protocol !== "http:") return false;
    const host = u.hostname.toLowerCase().replace(/\.+$/, "");
    if (host !== "res.cloudinary.com" && !host.endsWith(".cloudinary.com")) {
      return false;
    }
    return parseCloudinaryUploadPath(u.pathname) !== null;
  } catch {
    return false;
  }
}

export function extractPublicId(url: unknown): string | null {
  if (!isCloudinaryUrl(url)) return null;
  try {
    const u = new URL(url.trim());
    const pathname = decodeURIComponent(u.pathname);
    const remainder = parseCloudinaryUploadPath(pathname);
    if (!remainder) return null;
    let segments = remainder.split("/").filter((s) => s.length > 0);
    if (segments.length === 0) return null;

    // Strip optional transformations and version prefix (/upload/(?:v\d+/)?...)
    const versionIdx = segments.findIndex((seg, idx) => idx < segments.length - 1 && /^v\d+$/.test(seg));
    if (versionIdx !== -1) {
      segments = segments.slice(versionIdx + 1);
    } else {
      while (segments.length > 1 && isTransformSegment(segments[0])) {
        segments.shift();
      }
    }

    if (segments.length === 0) return null;
    if (segments.length === 1 && /^v\d+$/.test(segments[0])) return null;

    const isRaw = inferResourceTypeFromUrl(u.href, null) === "raw";
    const joined = segments.join("/");
    const withoutExt = isRaw ? joined : joined.replace(/\.[^./]+$/, "");
    return isSafePublicId(withoutExt) ? withoutExt.trim() : null;
  } catch {
    return null;
  }
}

export function extractCloudinaryUrls(record: unknown): string[] {
  if (!isPlainObject(record)) return [];
  const urls: string[] = [];
  const pushIfCloudinary = (val: unknown) => {
    if (typeof val === "string") {
      const trimmed = val.trim();
      if (isCloudinaryUrl(trimmed)) {
        urls.push(trimmed);
      }
    }
  };

  pushIfCloudinary(record.image_url);
  pushIfCloudinary(record.cover_image);
  pushIfCloudinary(record.avatar_url);
  pushIfCloudinary(record.photo_url);

  const imageUrls = parseJsonIfString(record.image_urls);
  if (Array.isArray(imageUrls)) {
    for (const u of imageUrls) {
      pushIfCloudinary(u);
    }
  }

  const previewMeta = parseJsonIfString(record.preview_metadata);
  if (isPlainObject(previewMeta)) {
    pushIfCloudinary(previewMeta.mapillary_thumb);
    pushIfCloudinary(previewMeta.map_image);
    pushIfCloudinary(previewMeta.og_image);
  }

  const details = parseJsonIfString(record.details);
  if (Array.isArray(details)) {
    for (const item of details) {
      if (isPlainObject(item)) {
        pushIfCloudinary(item.image_url);
      }
    }
  } else if (isPlainObject(details) && Array.isArray(details.items)) {
    for (const item of details.items) {
      if (isPlainObject(item)) {
        pushIfCloudinary(item.image_url);
      }
    }
  }

  return Array.from(new Set(urls));
}

function inferResourceTypeFromUrl(
  url: string,
  explicitResourceType: "image" | "video" | "raw" | null
): "image" | "video" | "raw" {
  if (explicitResourceType) return explicitResourceType;
  try {
    const pathname = new URL(url).pathname;
    if (pathname.includes("/video/upload/")) return "video";
    if (pathname.includes("/raw/upload/")) return "raw";
  } catch {
    // fallback to image
  }
  return "image";
}

export async function handleCleanupRequest(req: Request): Promise<Response> {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const serviceRoleKey = getEnv("SUPABASE_SERVICE_ROLE_KEY").trim();
  const webhookSecret = getEnv("CLEANUP_WEBHOOK_SECRET").trim();
  const supabaseUrl = getEnv("SUPABASE_URL").trim();
  const authHeader = req.headers.get("authorization") || "";
  const bearerMatch = authHeader.trim().match(/^bearer\s+(.+)$/i);
  const token = bearerMatch ? bearerMatch[1].trim() : "";
  const reqWebhookSecret = (req.headers.get("x-webhook-secret") || "").trim();
  const webhookTsHeader = (req.headers.get("x-webhook-timestamp") || "").trim();
  const webhookSigHeader = (req.headers.get("x-webhook-signature") || "").trim();

  let authorized =
    Boolean(serviceRoleKey && token && timingSafeEqual(token, serviceRoleKey)) ||
    Boolean(webhookSecret && reqWebhookSecret && timingSafeEqual(reqWebhookSecret, webhookSecret));

  if (!authorized && token) {
    authorized = await verifyServiceRoleTokenViaGoTrue(token, supabaseUrl);
  }

  let rawBody: string | null = null;
  if (!authorized && webhookTsHeader && webhookSigHeader) {
    const contentLenHeader = req.headers.get("content-length");
    const declaredLen = contentLenHeader ? Number(contentLenHeader) : 0;
    const withinDeclaredLimit = !Number.isFinite(declaredLen) || declaredLen <= MAX_SIGNED_WEBHOOK_BYTES;

    if (
      withinDeclaredLimit &&
      WEBHOOK_TIMESTAMP_RE.test(webhookTsHeader) &&
      WEBHOOK_SIG_HEX64_RE.test(webhookSigHeader)
    ) {
      const ts = Number(webhookTsHeader);
      const nowSec = Math.floor(Date.now() / 1000);
      if (Number.isSafeInteger(ts) && Math.abs(nowSec - ts) <= WEBHOOK_SIGNATURE_MAX_SKEW_SEC) {
        rawBody = await req.text();
        if (new TextEncoder().encode(rawBody).byteLength <= MAX_SIGNED_WEBHOOK_BYTES) {
          authorized = await verifyWebhookSignatureViaRpc(ts, webhookSigHeader, rawBody, supabaseUrl);
        }
      }
    }
  }

  if (!authorized) {
    return new Response(JSON.stringify({ error: "Unauthorized" }), {
      status: 401,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  let parsedBody: unknown;
  try {
    parsedBody = rawBody !== null ? JSON.parse(rawBody) : await req.json();
  } catch {
    return new Response(JSON.stringify({ error: "Invalid JSON payload" }), {
      status: 400,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  if (!isPlainObject(parsedBody)) {
    return new Response(JSON.stringify({ error: "Invalid JSON payload" }), {
      status: 400,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const body = parsedBody;
  const explicitResourceType: "image" | "video" | "raw" | null =
    body.resource_type === "raw" || body.resource_type === "video" || body.resource_type === "image"
      ? body.resource_type
      : null;

  const hasExplicitPublicIdInput =
    body.public_id !== undefined ||
    body.publicId !== undefined ||
    body.public_ids !== undefined;

  const targetMap = new Map<string, { publicId: string; resourceType: "image" | "video" | "raw" }>();
  const addTarget = (publicId: unknown, resourceType: "image" | "video" | "raw") => {
    if (!isSafePublicId(publicId)) return;
    const trimmed = publicId.trim();
    const key = `${resourceType}:${trimmed}`;
    if (!targetMap.has(key)) {
      targetMap.set(key, { publicId: trimmed, resourceType });
    }
  };

  if (body.public_id !== undefined) addTarget(body.public_id, explicitResourceType ?? "image");
  if (body.publicId !== undefined) addTarget(body.publicId, explicitResourceType ?? "image");
  if (Array.isArray(body.public_ids)) {
    for (const id of body.public_ids) {
      addTarget(id, explicitResourceType ?? "image");
    }
  }

  const eventType = typeof body.type === "string" ? body.type.trim().toUpperCase() : "";
  const oldRecord = isPlainObject(body.old_record) ? body.old_record : null;
  const newRecord = isPlainObject(body.new_record)
    ? body.new_record
    : isPlainObject(body.record)
    ? body.record
    : null;
  const shouldDiffNew = eventType === "UPDATE" || (eventType !== "DELETE" && newRecord !== null);

  // Note: itineraries.public_id is a trip share slug (e.g. "pub_xxxxxxxx"), not a Cloudinary asset ID.
  const normalizedTable = typeof body.table === "string" ? body.table.trim().toLowerCase() : "";
  const isItinerariesTable =
    body?.table === "itineraries" ||
    normalizedTable === "itineraries" ||
    normalizedTable === "public.itineraries";
  if (body?.table !== "itineraries" && !isItinerariesTable) {
    if (oldRecord && typeof oldRecord.public_id === "string" && eventType !== "INSERT") {
      const unchangedOnUpdate =
        shouldDiffNew &&
        newRecord &&
        typeof newRecord.public_id === "string" &&
        newRecord.public_id.trim() === oldRecord.public_id.trim();
      if (!unchangedOnUpdate) {
        addTarget(oldRecord.public_id, explicitResourceType ?? "image");
      }
    } else if (
      !oldRecord &&
      (eventType === "DELETE" || eventType === "") &&
      newRecord &&
      typeof newRecord.public_id === "string"
    ) {
      addTarget(newRecord.public_id, explicitResourceType ?? "image");
    }
  }

  // Webhook URL extraction + UPDATE diffing (old_record minus new_record ?? record)
  if (oldRecord && eventType !== "INSERT") {
    const oldUrls = extractCloudinaryUrls(oldRecord);
    const newUrls = shouldDiffNew && newRecord ? new Set(extractCloudinaryUrls(newRecord)) : new Set<string>();
    const newPublicIds = new Set(
      Array.from(newUrls)
        .map((u) => extractPublicId(u))
        .filter((id): id is string => id !== null)
    );

    for (const oldUrl of oldUrls) {
      if (newUrls.has(oldUrl)) continue;
      const extractedId = extractPublicId(oldUrl);
      if (extractedId && !newPublicIds.has(extractedId)) {
        addTarget(extractedId, inferResourceTypeFromUrl(oldUrl, explicitResourceType));
      }
    }
  }

  const targets = Array.from(targetMap.values());
  const isGenuineWebhookWithoutExplicitIds =
    !hasExplicitPublicIdInput &&
    (oldRecord !== null || ((eventType === "INSERT" || eventType === "DELETE") && newRecord !== null));

  if (targets.length === 0) {
    if (isGenuineWebhookWithoutExplicitIds) {
      return new Response(JSON.stringify({ deleted: [] }), {
        status: 200,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify({ error: "No valid public_id supplied" }), {
      status: 400,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const { cloudName, apiKey, apiSecret } = resolveCloudinaryCredentials();
  if (!cloudName || !apiKey || !apiSecret) {
    return new Response(JSON.stringify({ error: "Cloudinary credentials not configured" }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  const results: Array<{ public_id: string; ok: boolean; status: number; result?: unknown }> = [];
  for (const { publicId, resourceType } of targets) {
    const endpoint = `https://api.cloudinary.com/v1_1/${encodeURIComponent(cloudName)}/${resourceType}/destroy`;
    const timestamp = Math.floor(Date.now() / 1000);
    const signature = await signCloudinaryDestroy(publicId, timestamp, apiSecret, true);

    const form = new FormData();
    form.set("public_id", publicId);
    form.set("timestamp", String(timestamp));
    form.set("api_key", apiKey);
    form.set("invalidate", "true");
    form.set("signature", signature);

    let respStatus = 502;
    let respOk = false;
    let data: unknown = null;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    try {
      const resp = await fetch(endpoint, { method: "POST", body: form, signal: controller.signal });
      respStatus = resp.status;
      respOk = resp.ok;
      try {
        data = await resp.json();
      } catch {
        data = { status: resp.status };
      }
    } catch {
      data = { error: "Cloudinary request failed" };
    } finally {
      clearTimeout(timeoutId);
    }
    results.push({ public_id: publicId, ok: respOk, status: respStatus, result: data });
  }

  const allOk = results.every((r) => r.ok);
  return new Response(JSON.stringify({ deleted: results }), {
    status: allOk ? 200 : 502,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

if (typeof Deno !== "undefined" && typeof Deno.serve === "function") {
  Deno.serve(handleCleanupRequest);
}
