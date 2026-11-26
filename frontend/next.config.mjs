import { fileURLToPath } from 'url';
import path from 'path';
import { withSerwist } from '@serwist/turbopack';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
    reactStrictMode: true,
    reactCompiler: true,      // 自動 Memoization
    turbopack: {
        root: __dirname,      // 物理座標鎖定
    },
    cacheComponents: true,       // 🚀 [2026 Stable] 開啟組件級緩存與局部預渲染 (PPR)
    partialPrefetching: true,    // ⚡ [2026 Stable] 消除 Warning，開啟局部預抓取 (Partial Prefetching) 實現秒開跳轉
    experimental: {
        optimizePackageImports: [
            "lucide-react",
            "jspdf",
            "react-virtuoso",
            "@dnd-kit/core",
            "framer-motion",
            "sonner"
        ],
    },
    images: {
        remotePatterns: [
            { protocol: 'https', hostname: 'res.cloudinary.com' },
            { protocol: 'https', hostname: 'lh3.googleusercontent.com' },
            { protocol: 'https', hostname: 'lh5.googleusercontent.com' },
            { protocol: 'https', hostname: 'maps.googleapis.com' },
            { protocol: 'https', hostname: 'images.unsplash.com' },
            { protocol: 'https', hostname: 'plus.unsplash.com' },
            { protocol: 'https', hostname: 'flagcdn.com' },
        ],
    },
    // 👇 強制顯示開發指示器
    devIndicators: {
        appIsrStatus: true,
        buildActivity: true,
        buildActivityPosition: 'bottom-right',
    },
    // 🛡️ Wave 3.3: 全站安全回應標頭（排除 /api/* 與 /sw.js 以保留各自專屬策略與快取規則）
    async headers() {
        const cspReportOnly = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
            "worker-src 'self'",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' data: https://fonts.gstatic.com",
            "img-src 'self' data: blob: https://res.cloudinary.com https://cloudinary-proxy.ryan880425.workers.dev https://*.tabijiapp.com https://upload.wikimedia.org https://thumb.wikimedia.org https://commons.wikimedia.org https://lh3.googleusercontent.com https://lh5.googleusercontent.com https://maps.googleapis.com https://images.unsplash.com https://plus.unsplash.com https://flagcdn.com https://server.arcgisonline.com https://tiles.openfreemap.org https://tiles.mapterhorn.com https://*.fbcdn.net https://*.mapillary.com https:",
            "connect-src 'self' https://www.tabijiapp.com https://tabijiapp.com https://antigravity-backend-589255638719.us-central1.run.app https://oudnkmigfueuyvxqpqwn.supabase.co wss://oudnkmigfueuyvxqpqwn.supabase.co https://api.cloudinary.com https://res.cloudinary.com https://cloudinary-proxy.ryan880425.workers.dev https://api.open-meteo.com https://api.exchangerate-api.com https://open.er-api.com https://tiles.openfreemap.org https://server.arcgisonline.com https://tiles.mapterhorn.com https://graph.mapillary.com https://generativelanguage.googleapis.com",
            "frame-ancestors 'none'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ].join('; ');

        return [
            {
                source: '/((?!api(?:/|$)|sw\\.js$).*)',
                headers: [
                    { key: 'X-Frame-Options', value: 'DENY' },
                    { key: 'X-Content-Type-Options', value: 'nosniff' },
                    { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
                    { key: 'Permissions-Policy', value: 'camera=(self), microphone=(), geolocation=(self), interest-cohort=()' },
                    { key: 'Content-Security-Policy-Report-Only', value: cspReportOnly },
                ],
            },
        ];
    },
    // 🚀 本機開發與邊緣反向代理 (Local Development & Edge Reverse Proxy)
    // 使用 fallback rewrites，確保本地 App Router 優先處理，其餘路由（含 /api/sign-cloudinary）統一轉發至後端
    async rewrites() {
        const rawTarget = process.env.INTERNAL_BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8008";
        const backendTarget = rawTarget.replace(/\/+$/, "");
        return {
            fallback: [
                {
                    source: "/api/:path*",
                    destination: `${backendTarget}/api/:path*`,
                },
                {
                    source: "/.well-known/:path*",
                    destination: `${backendTarget}/.well-known/:path*`,
                },
                {
                    source: "/go/:path*",
                    destination: `${backendTarget}/go/:path*`,
                },
            ],
        };
    },
};

export default withSerwist(nextConfig);
