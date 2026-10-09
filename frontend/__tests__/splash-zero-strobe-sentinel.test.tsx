import { describe, it, expect, vi, beforeEach } from "vitest";
import fs from "node:fs";
import path from "node:path";

describe("🛡️ Security Sentinel: Zero-Strobe & Lifecycle Handover Proof", () => {
    beforeEach(() => {
        sessionStorage.clear();
        vi.clearAllMocks();
    });

    it("SENTINEL-1: 證偽並杜絕 __dismissHardSkeleton 在動畫完成 Paint 前同步撕開骨架", () => {
        // 模擬全域 __dismissHardSkeleton
        (window as unknown as { __dismissHardSkeleton: () => void }).__dismissHardSkeleton = vi.fn();

        // 模擬 PWA standalone 模式
        Object.defineProperty(window, "matchMedia", {
            writable: true,
            value: vi.fn().mockImplementation((query: string) => ({
                matches: query === "(display-mode: standalone)",
            })),
        });

        // 驗證源碼：若 standalone 且需要播放動畫，mount 時不得同步調用 __dismissHardSkeleton
        const splashSource = fs.readFileSync(
            path.resolve(__dirname, "../components/ui/splash-screen.tsx"),
            "utf-8"
        );

        // 如果要播放開屏動畫，禁止在 useEffect 一開頭就同步暴力調用 __dismissHardSkeleton
        expect(splashSource).not.toMatch(/setIsStandalone\(standalone\)[\s\S]*?__dismissHardSkeleton\(\)[\s\S]*?if \(hasShown \|\| !standalone\)/);
    });

    it("SENTINEL-2: AppShellSkeleton 嚴格維持夜幕色 #162832 且不可包含刺眼白卡片 DOM", () => {
        const landingSource = fs.readFileSync(
            path.resolve(__dirname, "../components/views/landing-page.tsx"),
            "utf-8"
        );

        // 必須保持 TC-5 契約
        expect(landingSource).toContain("if (!mounted) return <AppShellSkeleton />;");

        // 提取 AppShellSkeleton 函式區塊
        const skeletonMatch = landingSource.match(/function AppShellSkeleton\(\) \{([\s\S]*?)\}/);
        expect(skeletonMatch).not.toBeNull();
        const skeletonBody = skeletonMatch![1];

        // 嚴禁在未水合骨架中包含白光 Header、白光導航或灰色卡片
        expect(skeletonBody).not.toContain("bg-stone-200");
        expect(skeletonBody).not.toContain("bg-white/50");
        expect(skeletonBody).not.toContain("bg-white");
        expect(skeletonBody).toContain("#162832");
    });

    it("SENTINEL-3: 登入頁面草寫 Logo 與人物立繪不可包含方形水墨背景卡片與雜線", () => {
        const landingSource = fs.readFileSync(
            path.resolve(__dirname, "../components/views/landing-page.tsx"),
            "utf-8"
        );

        // 不得包含舊版橘色水墨底圖
        expect(landingSource).not.toContain("/images/tabiji-person-icon.png");
        expect(landingSource).not.toContain("tabiji-aurora-bg.png");

        // 必須採用高精度線稿遮罩
        expect(landingSource).toContain("/images/tabiji-person-outline.png");
        expect(landingSource).toContain("/images/tabiji-cursive-logo.png");
    });
});
