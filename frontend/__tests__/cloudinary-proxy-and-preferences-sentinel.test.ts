/**
 * 🛡️ Cloudflare Proxy & Preferences Fallback Sentinel Test Suite
 * 
 * Verifies:
 * 1. Cloudinary proxy URL never outputs invalid REDACTED_WORKER_HOST placeholder.
 * 2. Active Cloudflare worker domain fallback (cloudinary-proxy.ryanpig228.workers.dev) + Cloudinary native CDN transform fallback.
 * 3. usersApi.getPreferences gracefully degrades to [] on 401/403/404 without unhandled rejections.
 * 4. usersApi.getPreferences parses valid 200 responses correctly.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { getOptimizedImageUrl } from "../lib/utils";
import { usersApi } from "../lib/api";

describe("🛡️ Cloudflare Worker Proxy & Preferences Graceful Degradation Sentinel", () => {
    const originalEnv = process.env;

    beforeEach(() => {
        vi.resetModules();
        process.env = { ...originalEnv };
    });

    afterEach(() => {
        process.env = originalEnv;
        vi.restoreAllMocks();
    });

    describe("1. Cloudinary Proxy URL Optimization & Zero-Deadlock Fallback", () => {
        const sampleCloudinaryUrl = "https://res.cloudinary.com/dnpcnwrcu/image/upload/v1792785423/ryan_travel/streetview/mly_947387631644042.jpg";

        it("TC-1: Should NEVER output REDACTED_WORKER_HOST placeholder in optimized URLs", () => {
            const optimized = getOptimizedImageUrl(sampleCloudinaryUrl, 320);
            expect(optimized).not.toContain("REDACTED");
            expect(optimized).not.toContain("redacted");
        });

        it("TC-2: Default configuration uses active Cloudflare Worker (cloudinary-proxy.ryanpig228.workers.dev)", () => {
            delete process.env.NEXT_PUBLIC_CLOUDINARY_PROXY_HOST;
            const optimized = getOptimizedImageUrl(sampleCloudinaryUrl, 320);
            expect(optimized).toBe("https://cloudinary-proxy.ryanpig228.workers.dev/w_320/v1792785423/ryan_travel/streetview/mly_947387631644042.jpg");
        });

        it("TC-3: Uses custom NEXT_PUBLIC_CLOUDINARY_PROXY_HOST when explicitly provided", () => {
            process.env.NEXT_PUBLIC_CLOUDINARY_PROXY_HOST = "custom-worker.example.workers.dev";
            const optimized = getOptimizedImageUrl(sampleCloudinaryUrl, 640);
            expect(optimized).toBe("https://custom-worker.example.workers.dev/w_640/v1792785423/ryan_travel/streetview/mly_947387631644042.jpg");
        });

        it("TC-4: Falls back gracefully to native Cloudinary dynamic transform when worker host is explicitly disabled ('none' or empty)", () => {
            process.env.NEXT_PUBLIC_CLOUDINARY_PROXY_HOST = "none";
            const optimized = getOptimizedImageUrl(sampleCloudinaryUrl, 320);
            expect(optimized).toContain("res.cloudinary.com/dnpcnwrcu/image/upload/w_320,c_limit,f_auto,q_auto/v1792785423/ryan_travel/streetview/mly_947387631644042.jpg");
        });

        it("TC-5: Non-Cloudinary URLs or empty inputs pass through completely untouched", () => {
            expect(getOptimizedImageUrl(null)).toBe("");
            expect(getOptimizedImageUrl("https://images.unsplash.com/photo-12345")).toBe("https://images.unsplash.com/photo-12345");
        });
    });

    describe("2. usersApi.getPreferences Graceful Fallback & Auth Resilience", () => {
        it("TC-6: Gracefully returns empty array [] on 401 Unauthorized without throwing Error", async () => {
            const originalFetch = globalThis.fetch;
            globalThis.fetch = vi.fn().mockResolvedValue({
                ok: false,
                status: 401,
                json: async () => ({ detail: "Missing or invalid authentication token" }),
                text: async () => "Missing or invalid authentication token"
            } as Response);

            const result = await usersApi.getPreferences("mock-user-123");
            expect(result).toEqual([]);

            globalThis.fetch = originalFetch;
        });

        it("TC-7: Gracefully returns empty array [] on 404 Not Found without throwing Error", async () => {
            const originalFetch = globalThis.fetch;
            globalThis.fetch = vi.fn().mockResolvedValue({
                ok: false,
                status: 404,
                json: async () => ({ detail: "Preferences not found" }),
                text: async () => "Not Found"
            } as Response);

            const result = await usersApi.getPreferences("mock-user-123");
            expect(result).toEqual([]);

            globalThis.fetch = originalFetch;
        });

        it("TC-8: Gracefully returns empty array [] on network error without throwing unhandled rejection", async () => {
            const originalFetch = globalThis.fetch;
            globalThis.fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));

            const result = await usersApi.getPreferences("mock-user-123");
            expect(result).toEqual([]);

            globalThis.fetch = originalFetch;
        });

        it("TC-9: Returns parsed preferences when response is 200 OK", async () => {
            const mockPrefs = [
                { id: "p1", user_id: "u1", category: "diet", preference: "no beef", created_at: "2026-10-24T00:00:00Z" }
            ];
            const originalFetch = globalThis.fetch;
            globalThis.fetch = vi.fn().mockResolvedValue({
                ok: true,
                status: 200,
                json: async () => mockPrefs
            } as Response);

            const result = await usersApi.getPreferences("u1");
            expect(result).toEqual(mockPrefs);

            globalThis.fetch = originalFetch;
        });
    });
});
