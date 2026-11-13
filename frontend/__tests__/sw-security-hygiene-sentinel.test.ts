import { describe, it, expect, vi } from "vitest";
import fs from "node:fs";
import path from "node:path";
import {
  normalizeHostname,
  isAllowedDomainOrSubdomain,
  EXTERNAL_CDN_DOMAINS,
  isExternalCdnImageRequest,
  isSensitiveOrDynamicApiRequest,
  isNavigationFallbackRequest,
  sanitizePushLink,
  isSameOriginClientUrl,
  purgeLegacyApiCaches,
} from "@/lib/sw-routing";
import { deleteTripSnapshot } from "@/lib/idb-storage";

describe("🛡️ Security Sentinel: Service Worker Routing, Cache Isolation & Teamwork Hygiene", () => {
  const frontendDir = path.resolve(__dirname, "..");
  const repoRoot = path.resolve(frontendDir, "..");

  describe("Gate 1: CodeQL Incomplete URL Substring Sanitization Defense", () => {
    it("allows legitimate apex & subdomain CDN hosts (including FQDN trailing dots)", () => {
      expect(normalizeHostname("RES.CLOUDINARY.COM.")).toBe("res.cloudinary.com");
      expect(isAllowedDomainOrSubdomain("res.cloudinary.com", EXTERNAL_CDN_DOMAINS)).toBe(true);
      expect(isAllowedDomainOrSubdomain("res.cloudinary.com.", EXTERNAL_CDN_DOMAINS)).toBe(true);
      expect(
        isAllowedDomainOrSubdomain("cloudinary-proxy.ryanpig228.workers.dev", EXTERNAL_CDN_DOMAINS)
      ).toBe(true);
      expect(isAllowedDomainOrSubdomain("images.unsplash.com", EXTERNAL_CDN_DOMAINS)).toBe(true);
      expect(isAllowedDomainOrSubdomain("lh3.googleusercontent.com", EXTERNAL_CDN_DOMAINS)).toBe(true);
      expect(isAllowedDomainOrSubdomain("flagcdn.com", EXTERNAL_CDN_DOMAINS)).toBe(true);
      expect(isAllowedDomainOrSubdomain("tiles.mapillary.com", EXTERNAL_CDN_DOMAINS)).toBe(true);
    });

    it("rejects lookalike/prefix/suffix spoofing CDN & Supabase hosts", () => {
      const spoofedHosts = [
        "evil-cloudinary.com",
        "cloudinary.com.attacker.com",
        "notworkers.dev",
        "workers.dev.evil.org",
        "evil-unsplash.com",
        "evil-supabase.co",
        "supabase.co.attacker.com",
        "",
      ];
      for (const host of spoofedHosts) {
        expect(isAllowedDomainOrSubdomain(host, EXTERNAL_CDN_DOMAINS)).toBe(false);
        expect(
          isExternalCdnImageRequest({
            url: new URL(`https://${host || "invalid.local"}/photo.jpg`),
            sameOrigin: false,
          })
        ).toBe(false);
        expect(
          isSensitiveOrDynamicApiRequest({
            url: new URL(`https://${host || "invalid.local"}/auth/v1/token`),
            sameOrigin: false,
          })
        ).toBe(host === "" ? false : false);
      }
    });

    it("enforces sameOrigin check for /_next/image and allows real supabase.co auth endpoints", () => {
      expect(
        isExternalCdnImageRequest({
          url: new URL("https://tabijiapp.com/_next/image?url=%2Ficon.png&w=256&q=75"),
          sameOrigin: true,
        })
      ).toBe(true);
      expect(
        isExternalCdnImageRequest({
          url: new URL("https://evil.com/_next/image?url=foo"),
          sameOrigin: false,
        })
      ).toBe(false);
      expect(
        isSensitiveOrDynamicApiRequest({
          url: new URL("https://projref.supabase.co/auth/v1/token?grant_type=refresh_token"),
          sameOrigin: false,
        })
      ).toBe(true);
    });
  });

  describe("Gate 2: Zero Cross-User API CacheStorage Leakage (NetworkOnly Override)", () => {
    it("forces NetworkOnly on /api/trips (no trailing slash) and all same-origin /api/* paths", () => {
      const sameOriginEndpoints = [
        "/api",
        "/api/trips",
        "/api/trips/",
        "/api/trips/trip-123",
        "/api/users/me/preferences",
        "/api/expenses/trip-123",
        "/api/poi/all",
        "/api/app/donation-progress",
        "/api/auth/session",
        "/api/sign-cloudinary",
        "/api/parse-receipt",
      ];
      for (const ep of sameOriginEndpoints) {
        expect(
          isSensitiveOrDynamicApiRequest({
            url: new URL(`https://tabijiapp.com${ep}`),
            sameOrigin: true,
          })
        ).toBe(true);
      }
    });

    it("does NOT falsely block benign non-API static CDN images or /explore navigation", () => {
      expect(
        isSensitiveOrDynamicApiRequest({
          url: new URL("https://res.cloudinary.com/demo/image/upload/v1/sample.jpg"),
          sameOrigin: false,
        })
      ).toBe(false);
      expect(
        isSensitiveOrDynamicApiRequest({
          url: new URL("https://tabijiapp.com/explore?category=temple"),
          sameOrigin: true,
        })
      ).toBe(false);
    });

    it("places NetworkOnly API guard BEFORE ...defaultCache in sw.ts and removes dead bgSyncPlugin", () => {
      const swSrc = fs.readFileSync(path.join(frontendDir, "app", "sw.ts"), "utf-8");
      const guardIdx = swSrc.indexOf("isSensitiveOrDynamicApiRequest");
      const defaultCacheIdx = swSrc.indexOf("...defaultCache");
      expect(guardIdx).toBeGreaterThan(-1);
      expect(defaultCacheIdx).toBeGreaterThan(guardIdx);
      expect(swSrc).not.toContain("BackgroundSyncPlugin");
      expect(swSrc).not.toContain("bgSyncPlugin");
    });
  });

  describe("Gate 3: Push Notification Link & Client Origin Sanitization", () => {
    it("rejects backslash, control char, protocol-relative, and external redirect payloads", () => {
      const payloads = [
        "/\\\\evil.com",
        "\\\\evil.com",
        "//evil.com",
        "///evil.com",
        "/%5cevil.com",
        "/%2fevil.com",
        "javascript:alert(1)",
        "https://evil.com/trip",
        "/\\t/evil.com",
        "/\\n/evil.com",
        "/\\0/evil.com",
        "",
        "   ",
        null,
        undefined,
        123,
      ];
      for (const payload of payloads) {
        expect(sanitizePushLink(payload)).toBe("/");
      }
    });

    it("preserves benign internal deep links", () => {
      expect(sanitizePushLink("/")).toBe("/");
      expect(sanitizePushLink("/?trip=trip-abc&tab=tools&expense_id=exp-xyz")).toBe(
        "/?trip=trip-abc&tab=tools&expense_id=exp-xyz"
      );
      expect(sanitizePushLink("/explore?category=temple")).toBe("/explore?category=temple");
    });

    it("enforces exact origin equality instead of substring .includes()", () => {
      expect(isSameOriginClientUrl("https://tabijiapp.com/?trip=123", "https://tabijiapp.com")).toBe(true);
      expect(
        isSameOriginClientUrl("https://evil.com/?next=https://tabijiapp.com", "https://tabijiapp.com")
      ).toBe(false);
      expect(isSameOriginClientUrl("https://tabijiapp.com.evil.com/", "https://tabijiapp.com")).toBe(false);
    });
  });

  describe("Gate 4: Navigation Fallback Guard & Legacy 'apis' / 'trips-api-cache' Purge", () => {
    it("allows normal document navigation and blocks /api or _rsc", () => {
      expect(
        isNavigationFallbackRequest({
          request: { mode: "navigate" },
          url: new URL("https://tabijiapp.com/?trip=123"),
        })
      ).toBe(true);
      expect(
        isNavigationFallbackRequest({
          request: { mode: "navigate" },
          url: new URL("https://tabijiapp.com/api/trips"),
        })
      ).toBe(false);
      expect(
        isNavigationFallbackRequest({
          request: { mode: "navigate" },
          url: new URL("https://tabijiapp.com/?_rsc=abc"),
        })
      ).toBe(false);
    });

    it("purges both trips-api-cache and apis on activation & deleteTripSnapshot", async () => {
      const deleteBucketSpy = vi.fn(async (name: string) => name === "apis" || name === "trips-api-cache");
      const mockBuckets = {
        delete: deleteBucketSpy,
      } as unknown as CacheStorage;

      const purged = await purgeLegacyApiCaches(mockBuckets);
      expect(purged).toContain("trips-api-cache");
      expect(purged).toContain("apis");

      // Also verify deleteTripSnapshot cleans matching trip & trips list entries across both buckets
      const deletedUrls: string[] = [];
      const openSpy = vi.fn(async (cacheName: string) => {
        const entries =
          cacheName === "apis"
            ? [
                new Request("https://tabijiapp.com/api/trips"),
                new Request("https://tabijiapp.com/api/trips/trip-ghost"),
                new Request("https://tabijiapp.com/api/trips/trip-ghost-other"),
                new Request("https://tabijiapp.com/api/trips/trip-keep"),
              ]
            : [
                new Request("https://tabijiapp.com/api/trips/trip-ghost"),
                new Request("https://tabijiapp.com/api/trips/trip-ghost-other"),
              ];
        return {
          keys: async () => entries,
          delete: async (req: Request) => {
            deletedUrls.push(`${cacheName}:${new URL(req.url).pathname}`);
            return true;
          },
        };
      });
      const origCaches = (globalThis as { caches?: CacheStorage }).caches;
      Object.defineProperty(globalThis, "caches", {
        configurable: true,
        value: { open: openSpy },
      });
      try {
        await deleteTripSnapshot("trip-ghost");
      } finally {
        Object.defineProperty(globalThis, "caches", {
          configurable: true,
          value: origCaches,
        });
      }
      expect(deletedUrls).toContain("trips-api-cache:/api/trips/trip-ghost");
      expect(deletedUrls).toContain("apis:/api/trips/trip-ghost");
      expect(deletedUrls).toContain("apis:/api/trips");
      expect(deletedUrls).not.toContain("apis:/api/trips/trip-keep");
      expect(deletedUrls).not.toContain("apis:/api/trips/trip-ghost-other");
      expect(deletedUrls).not.toContain("trips-api-cache:/api/trips/trip-ghost-other");
    });
  });

  describe("Gate 5: Compiled public/sw.js Integrity & Non-Self-Precache", () => {
    it("excludes /sw.js and /sw.js.map from self.__SW_MANIFEST and matches current sw.ts behavior", () => {
      const swBuilt = fs.readFileSync(path.join(frontendDir, "public", "sw.js"), "utf-8");
      const arrEnd = swBuilt.indexOf("];");
      const arrStart = swBuilt.indexOf("[");
      expect(arrStart).toBeGreaterThan(-1);
      expect(arrEnd).toBeGreaterThan(arrStart);
      const manifest = eval(swBuilt.slice(arrStart, arrEnd + 1)) as Array<{
        url: string;
        revision?: string | null;
      }>;
      expect(manifest.some((entry) => entry.url === "/sw.js" || entry.url === "/sw.js.map")).toBe(false);
      expect(manifest.some((entry) => entry.url === "/")).toBe(true);
      expect(swBuilt).toContain("trips-api-cache");
      expect(swBuilt).toContain("tabiji.invalid");
      expect(fs.existsSync(path.join(repoRoot, ".gitignore"))).toBe(true);
    });
  });
});

