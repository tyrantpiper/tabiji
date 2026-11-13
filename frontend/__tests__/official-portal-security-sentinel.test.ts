import { describe, it, expect } from "vitest"
import { sanitizeLaunchRedirectUrl } from "../lib/security"

/**
 * 🛡️ 官方旗艦站安全導航與防 Open Redirect 驗證函式
 * 重新導出以保持既有測試與外部套件引用相容
 */
export { sanitizeLaunchRedirectUrl }

describe("Official Portal Security Sentinel & Navigation Safeguard", () => {
    it("benign_control: 合法內部路徑應正常放行", () => {
        expect(sanitizeLaunchRedirectUrl("/")).toBe("/")
        expect(sanitizeLaunchRedirectUrl("/?action=new-trip")).toBe("/?action=new-trip")
        expect(sanitizeLaunchRedirectUrl("/explore")).toBe("/explore")
    })

    it("exploit_prevention: 阻斷 Open Redirect (外部網址 / 雙斜線協定)", () => {
        expect(sanitizeLaunchRedirectUrl("https://evil.com")).toBe("/")
        expect(sanitizeLaunchRedirectUrl("http://evil.com")).toBe("/")
        expect(sanitizeLaunchRedirectUrl("//evil.com")).toBe("/")
        expect(sanitizeLaunchRedirectUrl("///evil.com")).toBe("/")
    })

    it("exploit_prevention: 阻斷 JavaScript 偽協議與反斜線繞過", () => {
        expect(sanitizeLaunchRedirectUrl("javascript:alert(1)")).toBe("/")
        expect(sanitizeLaunchRedirectUrl("data:text/html,evil")).toBe("/")
        expect(sanitizeLaunchRedirectUrl("/\\evil.com")).toBe("/")
    })

    it("exploit_prevention: 空值、undefined 與非法型別安全降級為 /", () => {
        expect(sanitizeLaunchRedirectUrl(null)).toBe("/")
        expect(sanitizeLaunchRedirectUrl(undefined)).toBe("/")
        expect(sanitizeLaunchRedirectUrl("")).toBe("/")
        expect(sanitizeLaunchRedirectUrl("   ")).toBe("/")
    })
})

