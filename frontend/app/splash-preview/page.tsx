"use client"

import React, { useState } from "react"
import { TabijiSplashAnimation } from "@/components/ui/splash/tabiji-splash-animation"
import { RotateCcw, Home, Sparkles, Eye } from "lucide-react"
import Link from "next/link"

export default function SplashPreviewPage() {
    const [replayKey, setReplayKey] = useState(0)
    const [isCompleted, setIsCompleted] = useState(false)
    const [showBlueprint, setShowBlueprint] = useState(false)

    const handleReplay = () => {
        setIsCompleted(false)
        setReplayKey((prev) => prev + 1)
    }

    return (
        <div className="relative min-h-screen w-full bg-slate-950 text-white font-sans overflow-hidden">
            {/* 開屏動畫播放本體 */}
            <TabijiSplashAnimation
                key={replayKey}
                onComplete={() => setIsCompleted(true)}
            />

            {/* 控制浮動面板 (在動畫播放時保持在最頂層) */}
            <div 
                className="fixed bottom-6 left-1/2 -translate-x-1/2 z-100000 flex items-center gap-3 px-4 py-2.5 rounded-full bg-slate-900/85 backdrop-blur-xl border border-white/15 shadow-2xl transition-all"
            >
                <button
                    onClick={handleReplay}
                    className="flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-linear-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400 text-white text-xs font-semibold shadow-md active:scale-95 transition-all cursor-pointer border-none"
                    title="重新播放動畫"
                >
                    <RotateCcw className="w-3.5 h-3.5" />
                    重播動畫 (Replay)
                </button>

                <button
                    onClick={() => setShowBlueprint((prev) => !prev)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/10 hover:bg-white/20 text-slate-200 text-xs font-medium border border-white/10 transition-all cursor-pointer"
                    title="查看拆解藍圖"
                >
                    <Eye className="w-3.5 h-3.5 text-amber-400" />
                    {showBlueprint ? "隱藏藍圖" : "技術拆解"}
                </button>

                <Link
                    href="/"
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/10 hover:bg-white/20 text-slate-200 text-xs font-medium border border-white/10 transition-all no-underline"
                    title="返回首頁"
                >
                    <Home className="w-3.5 h-3.5" />
                    返回首頁
                </Link>

                <div className="hidden sm:flex items-center gap-1.5 pl-2 border-l border-white/15 text-[11px] text-slate-400">
                    <Sparkles className="w-3 h-3 text-amber-400" />
                    <span>狀態: {isCompleted ? "✅ 播放完畢 (已交接首頁)" : "✨ 渲染播放中..."}</span>
                </div>
            </div>

            {/* 雙層複合技術拆解面板 (可選開啟) */}
            {showBlueprint && (
                <div className="fixed top-6 right-6 z-100000 w-80 max-w-[90vw] p-4 rounded-2xl bg-slate-900/90 backdrop-blur-xl border border-white/20 text-xs shadow-2xl space-y-2.5">
                    <div className="font-bold text-amber-400 text-sm flex items-center gap-1.5">
                        <Sparkles className="w-4 h-4" />
                        雙層複合技術 (Exploded Blueprint)
                    </div>
                    <ul className="space-y-1.5 text-slate-300 leading-relaxed list-disc list-inside">
                        <li><strong className="text-white">底層:</strong> 滿版日落復古漸層背景 (#E25248 ➔ #9D9065 ➔ #3C6F84)</li>
                        <li><strong className="text-white">光軌/路徑層:</strong> 31 點三次貝茲平滑 SVG 導引線 (Track Matte)</li>
                        <li><strong className="text-white">遮罩層:</strong> 100% 還原原畫藤井風輪廓與草寫 tabiji 白線 (去除飛機)</li>
                        <li><strong className="text-white">頂層:</strong> 獨立喚醒之 3D 紙飛機 (133x131)，拍翅後衝出螢幕</li>
                        <li><strong className="text-white">轉場:</strong> 雙向雲霧展開與高斯模糊淡出 (2.0s 終點)</li>
                    </ul>
                </div>
            )}
        </div>
    )
}
