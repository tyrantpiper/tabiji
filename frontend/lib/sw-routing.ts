/**
 * Service Worker Pure Routing, Hostname Allowlist, Push Link Sanitizer & Cache Purge Helpers
 * ==========================================================================================
 * Zero side effects — shared cleanly between frontend/app/sw.ts (Serwist runtime) and Vitest unit tests.
 */

export const EXTERNAL_CDN_DOMAINS = [
  "cloudinary.com",
  "workers.dev",
  "unsplash.com",
  "googleusercontent.com",
  "flagcdn.com",
  "mapillary.com",
] as const;

export const SUPABASE_AUTH_DOMAINS = ["supabase.co"] as const;

export const LEGACY_API_CACHE_NAMES = ["trips-api-cache", "apis"] as const;

export function normalizeHostname(hostname: string): string {
  return hostname.trim().toLowerCase().replace(/\.+$/, "");
}

export function isAllowedDomainOrSubdomain(
  hostname: string,
  allowedDomains: readonly string[]
): boolean {
  const normalized = normalizeHostname(hostname);
  if (!normalized) return false;
  return allowedDomains.some((rawDomain) => {
    const domain = normalizeHostname(rawDomain);
    if (!domain) return false;
    return normalized === domain || normalized.endsWith(`.${domain}`);
  });
}

export function isExternalCdnImageRequest({
  url,
  sameOrigin = true,
}: {
  url: Pick<URL, "hostname" | "pathname">;
  sameOrigin?: boolean;
}): boolean {
  const isNextImage =
    sameOrigin &&
    (url.pathname === "/_next/image" || url.pathname.startsWith("/_next/image/"));
  const isExternalCdn = isAllowedDomainOrSubdomain(url.hostname, EXTERNAL_CDN_DOMAINS);
  return isNextImage || isExternalCdn;
}

export function isSensitiveOrDynamicApiRequest({
  url,
  sameOrigin = false,
}: {
  url: Pick<URL, "hostname" | "pathname">;
  sameOrigin?: boolean;
}): boolean {
  const isSupabaseAuth =
    isAllowedDomainOrSubdomain(url.hostname, SUPABASE_AUTH_DOMAINS) &&
    url.pathname.includes("/auth/v1/");
  const isSameOriginApi =
    sameOrigin && (url.pathname === "/api" || url.pathname.startsWith("/api/"));
  const isExplicitSensitiveApiPath =
    url.pathname.startsWith("/api/auth/") ||
    url.pathname.startsWith("/api/sign-cloudinary") ||
    url.pathname.startsWith("/api/parse-receipt") ||
    url.pathname === "/api/trips" ||
    url.pathname.startsWith("/api/trips/");
  return isSupabaseAuth || isSameOriginApi || isExplicitSensitiveApiPath;
}

export function isNavigationFallbackRequest({
  request,
  url,
}: {
  request: Pick<Request, "mode">;
  url: Pick<URL, "pathname" | "searchParams">;
}): boolean {
  return (
    request.mode === "navigate" &&
    url.pathname !== "/api" &&
    !url.pathname.startsWith("/api/") &&
    !url.searchParams.has("_rsc")
  );
}

function hasControlOrBackslash(input: string): boolean {
  for (let i = 0; i < input.length; i++) {
    const code = input.charCodeAt(i);
    if (code <= 0x1f || code === 0x7f || code === 0x5c) {
      return true;
    }
  }
  return false;
}

export function sanitizePushLink(rawLink: unknown): string {
  if (typeof rawLink !== "string" || hasControlOrBackslash(rawLink)) {
    return "/";
  }
  const trimmed = rawLink.trim();
  if (!trimmed || !trimmed.startsWith("/") || trimmed.startsWith("//")) {
    return "/";
  }
  if (/^\/%(?:5c|2f)/i.test(trimmed)) {
    return "/";
  }
  try {
    const parsed = new URL(trimmed, "https://tabiji.invalid");
    if (parsed.origin !== "https://tabiji.invalid") return "/";
    if (!parsed.pathname.startsWith("/") || parsed.pathname.startsWith("//")) return "/";
    if (hasControlOrBackslash(parsed.href)) return "/";
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return "/";
  }
}

export function isSameOriginClientUrl(clientUrl: string, selfOrigin: string): boolean {
  if (!clientUrl || !selfOrigin) return false;
  try {
    return new URL(clientUrl).origin === new URL(selfOrigin).origin;
  } catch {
    return false;
  }
}

export async function purgeLegacyApiCaches(
  cacheStorage: CacheStorage | undefined = typeof caches !== "undefined" ? caches : undefined
): Promise<string[]> {
  if (!cacheStorage || typeof cacheStorage.delete !== "function") {
    return [];
  }
  const deletedNames: string[] = [];
  await Promise.all(
    LEGACY_API_CACHE_NAMES.map(async (cacheName) => {
      try {
        const deleted = await cacheStorage.delete(cacheName);
        if (deleted) deletedNames.push(cacheName);
      } catch {
        // Ignore CacheStorage cleanup errors
      }
    })
  );
  return deletedNames;
}

