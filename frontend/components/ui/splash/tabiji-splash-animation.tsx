"use client"

import React, { useEffect } from "react"
import { motion } from "framer-motion"

interface TabijiSplashAnimationProps {
    onComplete?: () => void
}

/**
 * 31 點連續平滑向量軌跡路徑 (Vector Motion Guide)
 * 涵蓋頭頂 (610, 480) -> 人形大衣下擺 -> 提箱輪廓 -> 筆勢過渡連寫 tabiji 至飛機尾部 (1580, 1060)
 */
const VECTOR_GUIDE_PATH =
    "M 610,480 C 593.3,493.3 516.7,526.7 510,560 C 503.3,593.3 545.0,648.3 570,680 C 595.0,711.7 658.3,723.3 660,750 C 661.7,776.7 604.2,795.0 580,840 C 555.8,885.0 535.8,956.7 515,1020 C 494.2,1083.3 470.8,1153.3 455,1220 C 439.2,1286.7 420.8,1371.7 420,1420 C 419.2,1468.3 433.3,1505.0 450,1510 C 466.7,1515.0 491.7,1488.3 520,1450 C 548.3,1411.7 583.3,1335.0 620,1280 C 656.7,1225.0 713.3,1153.3 740,1120 C 766.7,1086.7 762.5,1108.3 780,1080 C 797.5,1051.7 836.7,916.7 845,950 C 853.3,983.3 815.8,1238.3 830,1280 C 844.2,1321.7 896.7,1231.7 930,1200 C 963.3,1168.3 1005.0,1098.3 1030,1090 C 1055.0,1081.7 1058.3,1141.7 1080,1150 C 1101.7,1158.3 1133.3,1175.0 1160,1140 C 1186.7,1105.0 1223.3,940.0 1240,940 C 1256.7,940.0 1245.0,1106.7 1260,1140 C 1275.0,1173.3 1315.0,1153.3 1330,1140 C 1345.0,1126.7 1343.3,1060.0 1350,1060 C 1356.7,1060.0 1360.0,1136.7 1370,1140 C 1380.0,1143.3 1400.8,1048.3 1410,1080 C 1419.2,1111.7 1416.7,1313.3 1425,1330 C 1433.3,1346.7 1447.5,1211.7 1460,1180 C 1472.5,1148.3 1488.3,1160.0 1500,1140 C 1511.7,1120.0 1519.2,1063.3 1530,1060 C 1540.8,1056.7 1556.7,1120.0 1565,1120 C 1573.3,1120.0 1577.5,1070.0 1580,1060"

export function TabijiSplashAnimation({ onComplete }: TabijiSplashAnimationProps) {
    useEffect(() => {
        // 🛡️ 動畫 DOM 實體掛載就緒，安全平滑隱藏底層硬骨架
        if (typeof window !== "undefined" && typeof (window as unknown as { __dismissHardSkeleton?: () => void }).__dismissHardSkeleton === "function") {
            (window as unknown as { __dismissHardSkeleton: () => void }).__dismissHardSkeleton()
        }

        const timer = setTimeout(() => {
            onComplete?.()
        }, 2400)

        return () => clearTimeout(timer)
    }, [onComplete])

    return (
        <motion.div
            className="fixed inset-0 flex items-center justify-center overflow-hidden select-none bg-[#162832]"
            style={{
                zIndex: 99999,
            }}
            initial={{ opacity: 1, scaleX: 1, filter: "blur(0px)" }}
            exit={{
                opacity: 0,
                scaleX: 1.06,
                filter: "blur(16px)",
                transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] },
            }}
        >
            {/* 🌌 三幕式動態日落漸層暈開背景 (Three-Act Dynamic Gradient Aurora) */}
            <div
                data-testid="tabiji-aurora-bg"
                className="absolute inset-0 pointer-events-none overflow-hidden"
            >
                {/* 第一幕：底層莫蘭迪深藍綠夜幕 (Morandi Deep Teal Base: 0.0s - 0.5s) */}
                <div
                    className="absolute inset-0"
                    style={{
                        background: "linear-gradient(135deg, #162832 0%, #1B3B48 50%, #254A5A 100%)",
                    }}
                />

                {/* 第二幕：暖橘夕陽墨水暈開層 (Blooming Ink Orb) - 固化 blur(75px)，連續平滑曲線驅動 */}
                <motion.div
                    data-testid="tabiji-ink-orb"
                    className="absolute w-[min(115vw,760px)] h-[min(115vw,760px)] rounded-full"
                    style={{
                        background: "radial-gradient(circle, #E25248 0%, #D46238 45%, #9D9065 72%, transparent 100%)",
                        filter: "blur(75px)",
                        willChange: "transform, opacity",
                        transform: "translate3d(0,0,0)",
                    }}
                    initial={{
                        x: "35%",
                        y: "30%",
                        scale: 0.45,
                        opacity: 0.35,
                    }}
                    animate={{
                        x: "-8%",
                        y: "2%",
                        scale: 1.9,
                        opacity: 0.9,
                    }}
                    transition={{
                        duration: 1.8,
                        delay: 0.15,
                        ease: [0.16, 1, 0.3, 1],
                    }}
                />

                {/* 第三幕：終態黃金比例日落漸層 (Final Golden Sunset) - 於 Act 2 後期平滑淡入融為一體 */}
                <motion.div
                    className="absolute inset-0"
                    style={{
                        background: "linear-gradient(135deg, #E25248 0%, #9D9065 48%, #3C6F84 100%)",
                    }}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{
                        delay: 0.85,
                        duration: 0.95,
                        ease: "easeInOut",
                    }}
                />
            </div>

            {/* 雙層複合動畫 Stage (自適應視窗等比縮放，上限 680px) - 移除 drop-shadow-2xl 消除每幀卷積負擔 */}
            <div className="relative z-10 w-[min(90vw,680px)] h-[min(90vw,680px)] flex items-center justify-center">
                <svg
                    viewBox="0 0 2048 2048"
                    className="w-full h-full overflow-visible"
                    aria-label="Tabiji Opening Animation"
                >
                    <defs>
                        {/* 軌跡遮罩 (Track Matte)：一筆畫主幹導向 + 區域水墨漸進綻放 (Trailing Bloom) + 全畫布融合 */}
                        <mask id="tabiji-track-matte" maskUnits="userSpaceOnUse">
                            {/* 遮罩初始底色：純黑 (完全遮蔽) */}
                            <rect width="2048" height="2048" fill="black" />

                            {/* 1. 一筆畫主幹導向路徑 (Guide Path Leader) */}
                            <motion.path
                                d={VECTOR_GUIDE_PATH}
                                fill="none"
                                stroke="white"
                                strokeWidth="120"
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                initial={{ pathLength: 0 }}
                                animate={{ pathLength: 1 }}
                                transition={{
                                    duration: 1.25,
                                    ease: [0.25, 0.1, 0.25, 1],
                                }}
                            />

                            {/* 2. 區域水墨漸進綻放層 (Trailing Bloom Zones) */}
                            {/* Zone 1: 頭頂蓬鬆捲髮與五官輪廓水墨綻放 */}
                            <motion.ellipse
                                cx="620"
                                cy="580"
                                rx="240"
                                ry="220"
                                fill="white"
                                style={{ transformOrigin: "620px 580px" }}
                                initial={{ opacity: 0, scale: 0.2 }}
                                animate={{ opacity: 1, scale: 1 }}
                                transition={{
                                    duration: 0.55,
                                    delay: 0.18,
                                    ease: "easeOut",
                                }}
                            />

                            {/* Zone Hood: 連帽與雙肩立體剪影水墨展開 (完全覆蓋 X: 600~900, Y: 650~950 的 15,714 像素，根除突兀彈出) */}
                            <motion.ellipse
                                cx="740"
                                cy="790"
                                rx="240"
                                ry="200"
                                fill="white"
                                style={{ transformOrigin: "740px 790px" }}
                                initial={{ opacity: 0, scale: 0.2 }}
                                animate={{ opacity: 1, scale: 1 }}
                                transition={{
                                    duration: 0.55,
                                    delay: 0.32,
                                    ease: "easeOut",
                                }}
                            />

                            {/* Zone 2: 大衣輪廓水墨綻放 */}
                            <motion.ellipse
                                cx="560"
                                cy="1150"
                                rx="280"
                                ry="430"
                                fill="white"
                                style={{ transformOrigin: "560px 1150px" }}
                                initial={{ opacity: 0, scale: 0.2 }}
                                animate={{ opacity: 1, scale: 1 }}
                                transition={{
                                    duration: 0.6,
                                    delay: 0.48,
                                    ease: "easeOut",
                                }}
                            />

                            {/* Zone 3: tabiji 草寫連筆與 3 顆字母手寫圓點水墨展開 */}
                            <motion.rect
                                x="760"
                                y="900"
                                width="880"
                                height="490"
                                rx="60"
                                fill="white"
                                style={{ transformOrigin: "760px 1150px" }}
                                initial={{ opacity: 0, scaleX: 0 }}
                                animate={{ opacity: 1, scaleX: 1 }}
                                transition={{
                                    duration: 0.55,
                                    delay: 0.75,
                                    ease: "easeOut",
                                }}
                            />

                            {/* 3. 全畫布 100% 畫質融合保證層 (Full Canvas Unification Layer) */}
                            {/* 確保動畫終點時遮罩 100% 覆蓋全圖，95,588 像素零裁切還原原畫 */}
                            <motion.rect
                                width="2048"
                                height="2048"
                                fill="white"
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                transition={{
                                    duration: 0.35,
                                    delay: 1.15,
                                    ease: "easeInOut",
                                }}
                            />
                        </mask>

                        {/* 光軌微光光暈濾鏡 */}
                        <filter id="tabiji-glow" x="-20%" y="-20%" width="140%" height="140%">
                            <feGaussianBlur stdDeviation="8" result="blur" />
                            <feMerge>
                                <feMergeNode in="blur" />
                                <feMergeNode in="SourceGraphic" />
                            </feMerge>
                        </filter>
                    </defs>

                    {/* 遮罩層：套用 Track Matte 的高解析原畫白線條（人物+連筆 tabiji 字體） */}
                    <image
                        href="/images/tabiji-art-mask.png"
                        width="2048"
                        height="2048"
                        mask="url(#tabiji-track-matte)"
                    />

                    {/* 頂層：獨立 3D 紙飛機 (Fly Element) */}
                    <motion.g
                        style={{
                            transformOrigin: "1640px 1050px",
                        }}
                        initial={{
                            opacity: 0,
                            scale: 0.85,
                            rotate: 0,
                            x: 0,
                            y: 0,
                        }}
                        animate={{
                            opacity: [0, 0, 1, 1, 1, 0],
                            scale: [0.85, 0.85, 1, 1.08, 1.2, 1.4],
                            rotate: [0, 0, -5, 4, -8, -16],
                            x: [0, 0, 0, 20, 80, 260],
                            y: [0, 0, 0, -12, -55, -190],
                        }}
                        transition={{
                            duration: 2.0,
                            times: [0, 0.55, 0.65, 0.78, 0.88, 1.0],
                            ease: [0.2, 0.8, 0.2, 1],
                        }}
                    >
                        <image
                            href="/images/tabiji-paper-plane.png"
                            x="1575"
                            y="990"
                            width="133"
                            height="131"
                        />
                    </motion.g>
                </svg>
            </div>
        </motion.div>
    )
}
