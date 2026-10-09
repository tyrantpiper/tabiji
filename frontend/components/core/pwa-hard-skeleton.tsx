import React from "react"

/**
 * 🛡️ 零 JS 物理硬骨架 (Zero-JS Offline Hard Skeleton)
 * 作用：直接編譯進根目錄 HTML 靜態標籤中，在 WebKit 下載執行任何 JS Chunk 前，
 * 於第 0 毫秒直接呈現實體介面，物理杜絕任何白屏空窗！
 * 水合成功後透過 CSS 自動隱藏。
 */
export function PwaHardSkeleton() {
    return (
        <>
            <style
                dangerouslySetInnerHTML={{
                    __html: `
                    #pwa-hard-skeleton {
                        position: fixed;
                        inset: 0;
                        background: #162832;
                        z-index: 9995;
                        display: flex;
                        flex-direction: column;
                        justify-content: space-between;
                        padding-top: max(env(safe-area-inset-top), 16px);
                        padding-bottom: max(env(safe-area-inset-bottom), 12px);
                        box-sizing: border-box;
                        pointer-events: none;
                        transition: opacity 0.3s ease;
                    }
                    @media (display-mode: standalone) {
                        #pwa-hard-skeleton {
                            background: linear-gradient(135deg, #162832 0%, #1B3B48 50%, #254A5A 100%) !important;
                        }
                        #pwa-hard-skeleton .pwa-pulse-box {
                            display: none !important;
                        }
                    }
                    .dark #pwa-hard-skeleton {
                        background: #162832;
                    }
                    .pwa-pulse-box {
                        background: rgba(255,255,255,0.06);
                        border-radius: 16px;
                        animation: pwaPulse 1.8s ease-in-out infinite;
                    }
                    .dark .pwa-pulse-box {
                        background: rgba(255,255,255,0.06);
                    }
                    @keyframes pwaPulse {
                        0%, 100% { opacity: 0.6; }
                        50% { opacity: 0.25; }
                    }
                    /* 當 React 成功掛載後，全域標記隱藏骨架 */
                    body.hydrated #pwa-hard-skeleton {
                        display: none !important;
                    }
                    `
                }}
            />
            <div id="pwa-hard-skeleton" aria-hidden="true">
                {/* 頂部 Header */}
                <div style={{ padding: "0 20px", display: "flex", justifyContent: "space-between", alignItems: "center", height: "48px" }}>
                    <div className="pwa-pulse-box" style={{ width: "110px", height: "24px" }} />
                    <div className="pwa-pulse-box" style={{ width: "36px", height: "36px", borderRadius: "50%" }} />
                </div>

                {/* 內容預覽卡片 */}
                <div style={{ flex: 1, padding: "20px", display: "flex", flexDirection: "column", gap: "16px" }}>
                    <div className="pwa-pulse-box" style={{ width: "100%", height: "130px", borderRadius: "24px" }} />
                    <div className="pwa-pulse-box" style={{ width: "100%", height: "80px", borderRadius: "20px" }} />
                    <div className="pwa-pulse-box" style={{ width: "100%", height: "80px", borderRadius: "20px" }} />
                </div>

                {/* 底部導航 Bar */}
                <div style={{ padding: "0 28px", display: "flex", justifyContent: "space-around", alignItems: "center", height: "56px" }}>
                    <div className="pwa-pulse-box" style={{ width: "32px", height: "32px", borderRadius: "50%" }} />
                    <div className="pwa-pulse-box" style={{ width: "32px", height: "32px", borderRadius: "50%" }} />
                    <div className="pwa-pulse-box" style={{ width: "32px", height: "32px", borderRadius: "50%" }} />
                    <div className="pwa-pulse-box" style={{ width: "32px", height: "32px", borderRadius: "50%" }} />
                </div>
            </div>
            {/* 🚀 水合完成訊號腳本 (支援生命週期協調防線) */}
            <script
                dangerouslySetInnerHTML={{
                    __html: `
                    (function() {
                        function hideSkeleton() {
                            if (document.body) {
                                document.body.classList.add('hydrated');
                            }
                        }
                        window.__dismissHardSkeleton = hideSkeleton;
                        var isStandalone = window.matchMedia('(display-mode: standalone)').matches || (window.navigator && window.navigator.standalone === true);
                        var hasShown = sessionStorage.getItem('tabiji_splash_shown') || sessionStorage.getItem('splash_shown');
                        if (isStandalone && !hasShown) {
                            // PWA 啟動且尚未看過開屏：保持夜幕骨架直到 React 開屏動畫接管釋放
                        } else {
                            if (document.readyState === 'loading') {
                                window.addEventListener('DOMContentLoaded', hideSkeleton);
                            } else {
                                hideSkeleton();
                            }
                        }
                    })();
                    `
                }}
            />
        </>
    )
}
