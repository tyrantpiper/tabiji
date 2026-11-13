import { describe, it, expect } from "vitest"
import { sanitizeLaunchRedirectUrl } from "../lib/security"
import fs from "node:fs"
import path from "node:path"
import { execSync } from "node:child_process"

describe("Milestone 1 Adversarial Challenger Stress Harness", () => {
  describe("1. Protocol-Relative & Multi-Slash Bypass Attempts", () => {
    const multiSlashPayloads = [
      "//evil.com",
      "///evil.com",
      "////evil.com",
      "/////evil.com",
      "//localhost",
      "///localhost",
      "//127.0.0.1",
      "//attacker.com/path",
      "//tabiji.attacker.com",
      "//google.com/%2f..",
      "//https://evil.com",
    ]

    for (const payload of multiSlashPayloads) {
      it(`blocks protocol-relative URL: "${payload}" -> "/"`, () => {
        expect(sanitizeLaunchRedirectUrl(payload)).toBe("/")
      })
    }
  })

  describe("2. Backslash Evasion & Mixed-Slash Attempts", () => {
    const backslashPayloads = [
      "/\\evil.com",
      "\\evil.com",
      "\\\\evil.com",
      "/\\/evil.com",
      "\\/evil.com",
      "/\\/\\evil.com",
      "/path\\with\\backslash",
      "\\localhost",
      "\\\\127.0.0.1",
      "/explore\\evil",
      "/transit\\evil",
    ]

    for (const payload of backslashPayloads) {
      it(`blocks backslash evasion: "${payload}" -> "/"`, () => {
        expect(sanitizeLaunchRedirectUrl(payload)).toBe("/")
      })
    }
  })

  describe("3. Scheme Injection & Pseudo-Protocols", () => {
    const schemePayloads = [
      "javascript:alert(1)",
      "javascript:void(0)",
      "javascript:confirm(1)",
      "JavaScript:alert(1)",
      "JAVASCRIPT:alert(document.cookie)",
      "data:text/html,<script>alert(1)</script>",
      "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
      "data:application/javascript,alert(1)",
      "vbscript:msgbox(1)",
      "vbscript:alert(1)",
      "blob:https://evil.com/49257-234",
      "file:///etc/passwd",
      "about:blank",
      "http://evil.com",
      "https://evil.com",
      "http://localhost:3000",
      "https://localhost:3000",
      "ftp://evil.com",
      "ws://evil.com",
      "wss://evil.com",
      "chrome://settings",
    ]

    for (const payload of schemePayloads) {
      it(`blocks scheme injection: "${payload}" -> "/"`, () => {
        expect(sanitizeLaunchRedirectUrl(payload)).toBe("/")
      })
    }
  })

  describe("4. Null-byte, Control Characters & Encoding Exploits", () => {
    const controlPayloads = [
      "/%00/evil.com",
      "/\0/evil.com",
      "/\x00",
      "/\u0000",
      "/ %00 / evil",
      "/%0d%0aSet-Cookie:evil",
      "/\r\nevil.com",
      "/\tevil.com",
      "/explore\0",
      "/transit\0",
      "/%00",
      "/%2500",
      "/%20/evil.com",
    ]

    for (const payload of controlPayloads) {
      it(`neutralizes control characters / null bytes: "${JSON.stringify(payload)}" -> "/"`, () => {
        expect(sanitizeLaunchRedirectUrl(payload)).toBe("/")
      })
    }
  })

  describe("5. Whitelist Prefix Boundaries & Directory Traversal", () => {
    const boundaryPayloads = [
      "/exploits",
      "/explore_evil",
      "/explore-evil",
      "/explorer",
      "/explore/subroute",
      "/explore/settings",
      "/transit/subroute",
      "/transit/bus",
      "/transit_evil",
      "/transit-evil",
      "/transits",
      "/..",
      "/../",
      "/../../evil.com",
      "/explore/../../evil.com",
      "/transit/../../evil.com",
      "/admin",
      "/api",
      "/api/v1/auth",
      "/settings",
      "/official",
      "/official/terms",
      "/official/privacy",
      "/login",
      "/logout",
    ]

    for (const payload of boundaryPayloads) {
      it(`strictly confines to whitelist boundaries: "${payload}" -> "/"`, () => {
        expect(sanitizeLaunchRedirectUrl(payload)).toBe("/")
      })
    }
  })

  describe("6. Poisoned Query Parameter Attempts", () => {
    const poisonedQueries = [
      "/?trip=https://evil.com",
      "/?trip=http://evil.com",
      "/?trip=javascript:alert(1)",
      "/?trip=data:text/html",
      "/?trip=\\evil.com",
      "/?trip=/\\evil.com",
      "/?action=new-trip&url=https://evil.com",
      "/?action=javascript:alert(1)",
    ]

    for (const query of poisonedQueries) {
      it(`rejects query parameter containing colon/backslash: "${query}" -> "/"`, () => {
        expect(sanitizeLaunchRedirectUrl(query)).toBe("/")
      })
    }
  })

  describe("7. Falsy, Malformed, and Non-String Type Boundary Testing", () => {
    it("handles null safely -> '/'", () => {
      expect(sanitizeLaunchRedirectUrl(null)).toBe("/")
    })

    it("handles undefined safely -> '/'", () => {
      expect(sanitizeLaunchRedirectUrl(undefined)).toBe("/")
    })

    it("handles empty string safely -> '/'", () => {
      expect(sanitizeLaunchRedirectUrl("")).toBe("/")
    })

    it("handles whitespace string safely -> '/'", () => {
      expect(sanitizeLaunchRedirectUrl("   ")).toBe("/")
      expect(sanitizeLaunchRedirectUrl("\t\n\r")).toBe("/")
    })

    it("handles non-string types safely -> '/'", () => {
      expect(sanitizeLaunchRedirectUrl(123 as unknown as string)).toBe("/")
      expect(sanitizeLaunchRedirectUrl(true as unknown as string)).toBe("/")
      expect(sanitizeLaunchRedirectUrl({} as unknown as string)).toBe("/")
      expect(sanitizeLaunchRedirectUrl([] as unknown as string)).toBe("/")
    })
  })

  describe("8. Legitimate Deep Links & Whitelisted Routes Preservation", () => {
    it("preserves exact root path '/'", () => {
      expect(sanitizeLaunchRedirectUrl("/")).toBe("/")
    })

    it("preserves canonical deep link with UUID: '/?trip=123e4567-e89b-12d3-a456-426614174000'", () => {
      const deepLink = "/?trip=123e4567-e89b-12d3-a456-426614174000"
      expect(sanitizeLaunchRedirectUrl(deepLink)).toBe(deepLink)
    })

    it("preserves complex deep link query: '/?trip=kyoto-2026-xyz&day=3&tab=itinerary'", () => {
      const deepLink = "/?trip=kyoto-2026-xyz&day=3&tab=itinerary"
      expect(sanitizeLaunchRedirectUrl(deepLink)).toBe(deepLink)
    })

    it("preserves instant trip creation action: '/?action=new-trip'", () => {
      expect(sanitizeLaunchRedirectUrl("/?action=new-trip")).toBe("/?action=new-trip")
    })

    it("preserves whitelisted explore path '/explore'", () => {
      expect(sanitizeLaunchRedirectUrl("/explore")).toBe("/explore")
    })

    it("preserves explore with queries: '/explore?category=temple&region=kansai'", () => {
      const exploreUrl = "/explore?category=temple&region=kansai"
      expect(sanitizeLaunchRedirectUrl(exploreUrl)).toBe(exploreUrl)
    })

    it("preserves whitelisted transit path '/transit'", () => {
      expect(sanitizeLaunchRedirectUrl("/transit")).toBe("/transit")
    })

    it("preserves transit with queries: '/transit?from=HND&to=NRT'", () => {
      const transitUrl = "/transit?from=HND&to=NRT"
      expect(sanitizeLaunchRedirectUrl(transitUrl)).toBe(transitUrl)
    })
  })

  describe("9. Core Frozen Invariants Physical File Integrity", () => {
    const frontendDir = path.resolve(__dirname, "..")
    const repoRootDir = path.resolve(frontendDir, "..")
    const pagePath = path.join(frontendDir, "app", "page.tsx")
    const swPath = path.join(frontendDir, "app", "sw.ts")
    const manifestPath = path.join(frontendDir, "public", "manifest.json")

    it("frontend/app/page.tsx exists and is identical to HEAD", () => {
      expect(fs.existsSync(pagePath)).toBe(true)
      const diff = execSync("git diff HEAD -- frontend/app/page.tsx", { cwd: repoRootDir, encoding: "utf-8" })
      expect(diff.trim()).toBe("")
    })

    it("frontend/app/sw.ts enforces hardened API NetworkOnly, hostname suffix guard & push sanitization", () => {
      expect(fs.existsSync(swPath)).toBe(true)
      const swSrc = fs.readFileSync(swPath, "utf-8")
      expect(swSrc).toContain("isSensitiveOrDynamicApiRequest")
      expect(swSrc).toContain("sanitizePushLink")
      expect(swSrc).toContain("serwist.addEventListeners")
      expect(swSrc).not.toContain("url.hostname.includes(")
    })

    it("frontend/public/manifest.json exists and is identical to HEAD", () => {
      expect(fs.existsSync(manifestPath)).toBe(true)
      const diff = execSync("git diff HEAD -- frontend/public/manifest.json", { cwd: repoRootDir, encoding: "utf-8" })
      expect(diff.trim()).toBe("")
    })

    it("git status reports 0 modifications to portal/manifest invariant files", () => {
      const status = execSync("git status --porcelain frontend/app/page.tsx frontend/public/manifest.json", { cwd: repoRootDir, encoding: "utf-8" })
      expect(status.trim()).toBe("")
    })
  })
})
