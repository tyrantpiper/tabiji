/**
 * Security Utility - Tabidachi Frontend
 * Provides cryptographic functions and secure storage wrappers.
 */

/**
 * Generates a cryptographically secure UUID v4.
 * Falls back to a high-entropy Math.random implementation if Web Crypto is unavailable.
 */
export function generateSecureUUID(): string {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    
    // Fallback using crypto.getRandomValues if available
    if (typeof crypto !== 'undefined' && crypto.getRandomValues) {
        return (String(1e7) + -1e3 + -4e3 + -8e3 + -1e11).replace(/[018]/g, (c) => {
            const num = parseInt(c, 10);
            return (num ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> num / 4).toString(16);
        });
    }

    // If we reach here, the environment does not support Web Crypto API
    throw new Error('Cryptographically secure random number generation is not supported in this environment.');
}

/**
 * Secure Storage Prefix to identify encrypted/obfuscated data.
 */
const SECURE_PREFIX = '___SECURE_V1___';

/**
 * Obfuscates sensitive data for localStorage.
 * Note: While not true unbreakable encryption (since key is client-side), 
 * it prevents shoulder-surfing and simple data extraction from plain text.
 */
export function encryptData(data: string): string {
    if (!data) return data;
    try {
        // Base64 obfuscation with a unique salt/suffix for Tabidachi
        const salted = `tabidachi:${data}:secure`;
        return SECURE_PREFIX + btoa(unescape(encodeURIComponent(salted)));
    } catch (e) {
        console.error('Encryption error:', e);
        return data;
    }
}

/**
 * Decrypts data from localStorage with backward compatibility.
 */
export function decryptData(encryptedData: string | null): string | null {
    if (!encryptedData) return null;
    
    // Backward compatibility: If it doesn't have the prefix, treat as plain text
    if (!encryptedData.startsWith(SECURE_PREFIX)) {
        return encryptedData;
    }

    try {
        const base64 = encryptedData.replace(SECURE_PREFIX, '');
        // Validate base64 structure before decoding
        if (!/^[A-Za-z0-9+/]*={0,2}$/.test(base64)) {
            return encryptedData;
        }
        
        const decrypted = decodeURIComponent(escape(atob(base64)));
        
        // Extract original content: tabidachi:CONTENT:secure
        const match = decrypted.match(/^tabidachi:(.*):secure$/);
        return match ? match[1] : decrypted;
    } catch (e) {
        console.warn('Decryption failed, falling back to raw data:', e);
        return encryptedData; 
    }
}

export const DEV_MODE_SENTINELS = new Set(["(開發者模式)", "(Dev Mode)", "()"]);

/**
 * Universal Secure Key Provider
 * Handles Decryption -> Legacy Fallback -> Dev Key logic in one place.
 */
export function getSecureApiKey(): string {
    // 🛑 移除非 ASCII 字元，防止 'Failed to read headers property' 的 Fetch 崩潰
    const sanitize = (key: string) => key.replace(/[^\x20-\x7E]/g, '').trim();
    const isSentinel = (raw: string): boolean => {
        const trimmed = raw.trim();
        return DEV_MODE_SENTINELS.has(trimmed) || DEV_MODE_SENTINELS.has(sanitize(trimmed));
    };

    if (typeof window === 'undefined') {
        const envKey = sanitize(process.env.NEXT_PUBLIC_DEV_GEMINI_KEY || "");
        return DEV_MODE_SENTINELS.has(envKey) ? "" : envKey;
    }

    try {
        // 1. Try Primary Secure Key (Encrypted)
        const secureKey = localStorage.getItem("user_gemini_key");
        if (secureKey) {
            const decrypted = decryptData(secureKey);
            if (decrypted) {
                if (isSentinel(decrypted)) {
                    // Self-heal previously poisoned Dev Mode sentinel (e.g. "(開發者模式)" -> "()" after ASCII sanitize)
                    localStorage.removeItem("user_gemini_key");
                } else {
                    const clean = sanitize(decrypted);
                    if (clean) return clean;
                }
            }
        }

        // 2. Try Legacy Keys (Plain text fallback)
        const legacyKey = localStorage.getItem("gemini_api_key");
        if (legacyKey) {
            if (isSentinel(legacyKey)) {
                localStorage.removeItem("gemini_api_key");
            } else {
                const cleanLegacy = sanitize(legacyKey);
                if (cleanLegacy) return cleanLegacy;
            }
        }

        // 3. Final Fallback (Environment Variable)
        const envKey = sanitize(process.env.NEXT_PUBLIC_DEV_GEMINI_KEY || "");
        return DEV_MODE_SENTINELS.has(envKey) ? "" : envKey;
    } catch (e) {
        console.error("Critical error in key provider:", e);
        const envKey = sanitize(process.env.NEXT_PUBLIC_DEV_GEMINI_KEY || "");
        return DEV_MODE_SENTINELS.has(envKey) ? "" : envKey;
    }
}

/**
 * Safe URL Sanitizer
 * Verifies if a URL belongs to a trusted domain.
 */
export function isTrustedUrl(url: string, trustedDomain: string): boolean {
    if (!url) return false;
    try {
        const parsed = new URL(url);
        // Only allow HTTPS and exact domain match (or subdomains)
        return parsed.protocol === 'https:' && 
               (parsed.hostname === trustedDomain || parsed.hostname.endsWith('.' + trustedDomain));
    } catch {
        // Not a valid URL
        return false;
    }
}

/**
 * UUID v4 Format Guard
 * Validates whether an incoming string matches the standard UUID v4 format.
 */
export const UUID_V4_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const TBJ_REC_REGEX = /^tbj_rec_[0-9a-f]{8}_[0-9a-f]{32}$/i;

export function isValidUUID(uuid: string | null | undefined): boolean {
    if (!uuid || typeof uuid !== 'string') return false;
    return UUID_V4_REGEX.test(uuid.trim());
}

/**
 * Dual-Track Recovery Key Guard
 * Validates whether an incoming credential is a modern Stripe-style key (tbj_rec_*) or legacy UUID.
 */
export function isValidRecoveryKey(key: string | null | undefined): boolean {
    if (!key || typeof key !== 'string') return false;
    const clean = key.trim();
    return isValidUUID(clean) || TBJ_REC_REGEX.test(clean);
}

/**
 * 🛡️ 官方旗艦站安全導航與防 Open Redirect 驗證函式
 * 確保 /official 上的「啟動應用 (Launch App)」按鈕絕不接受任何外部網址或雙斜線跨域繞過
 * 僅允許白名單內部路徑（/、/?action=new-trip、/explore、/transit）及合法查詢字串，其餘降級為 "/"
 */
export function sanitizeLaunchRedirectUrl(targetUrl?: string | null): string {
    if (!targetUrl || typeof targetUrl !== "string") {
        return "/"
    }
    const clean = targetUrl.trim()
    // 嚴格阻斷包含協議、雙斜線 (//evil.com) 或冒號的任意跨域導航
    if (!clean.startsWith("/") || clean.startsWith("//") || clean.includes(":") || clean.includes("\\")) {
        return "/"
    }
    // 白名單合法應用內部相對路徑
    const ALLOWED_INTERNAL_PREFIXES = ["/", "/?action=new-trip", "/explore", "/transit"]
    const isWhitelisted = ALLOWED_INTERNAL_PREFIXES.some(prefix => clean === prefix || clean.startsWith(prefix + "?"))
    return isWhitelisted ? clean : "/"
}


