import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import { formatNumberSafe } from "./format"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * 💰 Safe currency formatting
 */
export function formatCurrency(
  amount: number | string | null | undefined,
  fallback: string = "0"
) {
  return formatNumberSafe(amount, fallback);
}

export { formatNumberSafe } from "./format"

/**
 * 🌍 Safe PWA External Link Opener
 * 解決 iOS 17.4+ PWA (Standalone WebKit) 環境下，直接使用 window.open 
 * 觸發 Universal Link (如 Google Maps) 會跳出「不支援的連結無法開啟」的問題。
 */
export function openExternalLink(url?: string | null) {
    if (!url) return;

    const trimmed = url.trim();
    // 🛡️ Sentinel Defense: 僅允許安全的外部協議，阻斷 javascript: / data: / vbscript:
    if (!/^(https?|maps|geo|tel|mailto):/i.test(trimmed)) {
        console.warn(`[Security] Blocked unsafe external link protocol: ${trimmed}`);
        return;
    }
    
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || 
                  (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    
    const nav = window.navigator as unknown as { standalone?: boolean };
    
    if (isIOS && nav.standalone) {
        // iOS PWA 專用降級解法：動態建立 <a> 標籤，模擬實體點擊
        const a = document.createElement('a');
        a.href = trimmed;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    } else {
        // Android, Web, 與非 PWA 環境：維持原生呼叫
        window.open(trimmed, '_blank', 'noopener,noreferrer');
    }
}

/**
 * 🖼️ 將原始 Cloudinary 網址轉換為 Cloudflare Worker Proxy 網址
 * 自動套用白名單內的寬度 (例如 w_640)，並透過 Worker 在邊緣節點進行格式優化與快取。
 */
export function getOptimizedImageUrl(originalUrl?: string | null, width: 320 | 640 | 768 | 1024 | 1280 = 640): string {
    if (!originalUrl) return '';

    // 檢查是否為 Cloudinary 的圖片 URL
    if (originalUrl.includes('res.cloudinary.com')) {
        // 使用正則表達式萃取 /image/upload/ 後面的路徑
        // 例如：https://res.cloudinary.com/REDACTED_CLOUDINARY_CLOUD/image/upload/v12345/my_image.jpg
        // 會萃取出 /v12345/my_image.jpg
        // 如果原本的 URL 已經包含其他轉換參數 (如 /w_1024,c_limit...)，也會被拔掉保留最乾淨的路徑
        const uploadPathMatch = originalUrl.match(/\/image\/upload\/(?:[a-zA-Z0-9_,]+\/)?(v\d+\/.*)$/);
        
        if (uploadPathMatch && uploadPathMatch[1]) {
            const cleanPath = uploadPathMatch[1];
            // 🛡️ 優先讀取環境變數或專案真實 Cloudflare Worker，絕不使用硬編碼無效主機
            const rawHost = process.env.NEXT_PUBLIC_CLOUDINARY_PROXY_HOST;
            const workerHost = rawHost !== undefined ? rawHost.trim() : "cloudinary-proxy.ryanpig228.workers.dev";
            
            if (workerHost && !workerHost.includes("REDACTED") && workerHost.toLowerCase() !== "none") {
                return `https://${workerHost}/w_${width}/${cleanPath}`;
            }

            // 🛡️ 雙保險原生轉換：直接截取 base url (/image/upload/) 拼接精確的 cleanPath
            const baseMatch = originalUrl.match(/^(https:\/\/res\.cloudinary\.com\/[^/]+\/image\/upload\/)/);
            if (baseMatch) {
                return `${baseMatch[1]}w_${width},c_limit,f_auto,q_auto/${cleanPath}`;
            }
        }
    }
    
    return originalUrl;
}
