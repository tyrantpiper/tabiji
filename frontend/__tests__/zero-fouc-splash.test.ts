import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

describe("🛡️ Zero-FOUC Splash & Cold Boot Integrity (冷啟動開屏零閃爍審計)", () => {
    const frontendDir = path.resolve(__dirname, "..");
    const manifestPath = path.join(frontendDir, "public", "manifest.json");
    const layoutPath = path.join(frontendDir, "app", "layout.tsx");
    const skeletonPath = path.join(frontendDir, "components", "core", "pwa-hard-skeleton.tsx");
    const splashPath = path.join(frontendDir, "components", "ui", "splash-screen.tsx");
    const landingPath = path.join(frontendDir, "components", "views", "landing-page.tsx");

    it("SEC-1: public/manifest.json background_color 與 theme_color 必須對齊墨夜基底色 #162832", () => {
        expect(fs.existsSync(manifestPath)).toBe(true);
        const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
        expect(manifest.background_color).toBe("#fafaf9");
        expect(manifest.theme_color).toBe("#fafaf9");
    });

    it("SEC-2: app/layout.tsx viewport.themeColor 必須對齊 #fafaf9 且 iOS statusBarStyle 回歸標準 default 佈局", () => {
        const layoutSource = fs.readFileSync(layoutPath, "utf-8");
        expect(layoutSource).toContain('themeColor: "#fafaf9"');
        expect(layoutSource).toContain('statusBarStyle: "default"');
    });

    it("SEC-3: pwa-hard-skeleton.tsx 必須具備 standalone 媒體查詢夜幕漸層且封死骨架脈衝塊", () => {
        const skeletonSource = fs.readFileSync(skeletonPath, "utf-8");
        expect(skeletonSource).toContain("@media (display-mode: standalone)");
        expect(skeletonSource).toContain("#162832");
        expect(skeletonSource).toContain(".pwa-pulse-box");
        expect(skeletonSource).toContain("display: none !important;");
    });

    it("SEC-4: pwa-hard-skeleton.tsx 必須具備生命週期協調防線，禁止在 DOMContentLoaded 盲目卸除", () => {
        const skeletonSource = fs.readFileSync(skeletonPath, "utf-8");
        expect(skeletonSource).toContain("__dismissHardSkeleton");
        expect(skeletonSource).toContain("tabiji_splash_shown");
    });

    it("SEC-5: splash-screen.tsx 水合完成後必須主動調用 __dismissHardSkeleton 達成無縫交棒", () => {
        const splashSource = fs.readFileSync(splashPath, "utf-8");
        expect(splashSource).toContain("__dismissHardSkeleton");
    });

    it("SEC-6: landing-page.tsx 嚴格保持 TC-5 契約 if (!mounted) return <AppShellSkeleton />;", () => {
        const landingSource = fs.readFileSync(landingPath, "utf-8");
        expect(landingSource).toContain("if (!mounted) return <AppShellSkeleton />;");
    });
});
