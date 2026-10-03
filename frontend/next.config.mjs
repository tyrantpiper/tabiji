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
    // 🚀 本機開發與邊緣反向代理 (Local Development & Edge Reverse Proxy)
    // 預設 after-files rewrites，確保本地 App Router (/api/sign-cloudinary) 優先由 Next.js 處理
    async rewrites() {
        const rawTarget = process.env.INTERNAL_BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8008";
        const backendTarget = rawTarget.replace(/\/+$/, "");
        return [
            {
                source: "/api/:path*",
                destination: `${backendTarget}/api/:path*`,
            },
        ];
    },
};

export default withSerwist(nextConfig);
