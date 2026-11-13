import { describe, it, expect } from "vitest"
import fs from "fs"
import path from "path"

/**
 * 🛡️ Security Sentinel PoC Suite (Mantis Block G Benign Control)
 * Target: profile-view.tsx Donation Amount Privacy & Percentage Refactor
 * Date: 2026-11-09
 */
describe("Security Sentinel: Profile Donation Amount Privacy & CLS Guard", () => {
    const profileViewPath = path.resolve(__dirname, "../components/views/profile-view.tsx")
    const content = fs.readFileSync(profileViewPath, "utf-8")

    // === Mantis Block G: Benign Control Tests (Must Pass Before & After) ===
    describe("Mantis Block G: Benign Control Invariants", () => {
        it("benign_control: should preserve profile_accumulator label without deletion", () => {
            expect(content).toContain("t('profile_accumulator')")
        })

        it("benign_control: should preserve donation monitor card structure and toggle", () => {
            expect(content).toContain("showDonation && (() => {")
            expect(content).toContain("isDonationLoading")
            expect(content).toContain("setDonationExpanded(!donationExpanded)")
        })

        it("benign_control: should preserve all milestone steps and labels", () => {
            expect(content).toContain("t('profile_donation_milestone_1')")
            expect(content).toContain("t('profile_donation_milestone_2')")
            expect(content).toContain("t('profile_donation_milestone_3')")
            expect(content).toContain("t('profile_donation_milestone_4')")
            expect(content).toContain("t('profile_donation_milestone_5')")
        })
    })

    // === Red Exploit 1: Raw Fiat Amount Privacy Leakage ===
    describe("Red Exploit 1: Raw Fiat Amount Privacy Leakage", () => {
        it("exploit_target_1: profile-view.tsx summary line must NOT render raw NT$ currency amount", () => {
            // RED before patch: contains NT${donationProgress.current.toLocaleString()}
            // GREEN after patch: raw currency amount removed
            expect(content).not.toContain("NT${donationProgress.current.toLocaleString()}")
            expect(content).not.toContain("/ ${donationProgress.goal.toLocaleString()}")
        })
    })

    // === Red Exploit 2: Skeleton Width CLS Layout Shift ===
    describe("Red Exploit 2: Skeleton Width CLS Layout Shift", () => {
        it("exploit_target_2: loading skeleton summary must not use w-32 designed for wide currency string", () => {
            // RED before patch: contains <Skeleton className="h-6 w-32
            // GREEN after patch: resized to w-14 to match percentage width
            expect(content).not.toContain('<Skeleton className="h-6 w-32 bg-[#0B3026]/10 dark:bg-white/10" />')
            expect(content).toContain('<Skeleton className="h-6 w-14 bg-[#0B3026]/10 dark:bg-white/10" />')
        })
    })

    // === Red Exploit 3: Micro-Percentage Decimal Preservation & a11y Label ===
    describe("Red Exploit 3: Micro-Percentage Decimal Preservation & a11y Label", () => {
        it("exploit_target_3: summary line must handle micro-percentage (<1%) and provide aria-label", () => {
            // RED before patch: lacks displayPercentage logic in summary line
            // GREEN after patch: handles percentage < 1 && percentage > 0 with toFixed(1)
            expect(content).toContain("displayPercentage")
            expect(content).toContain("aria-label=")
        })
    })
})

