/**
 * 🛡️ Tabiji Client-Side Session & Identity Manager
 * Implements the 1Password Secret Key / Local-First Recovery Key paradigm.
 * 
 * Guarantees:
 * 1. Offline-Safe Boot: Never blocks app initialization if offline.
 * 2. In-Flight Deduplication: Multiple concurrent calls resolve the same promise.
 * 3. Zero-Disruption Upgrade: Silently exchanges legacy user_uuid for signed JWT.
 */

const TOKEN_KEY = "tabiji_session_token";
const RECOVERY_KEY = "user_uuid";

let inFlightSessionPromise: Promise<string | null> | null = null;

export interface SessionInfo {
    accessToken: string;
    userId: string;
    isNew: boolean;
}

/**
 * 🛡️ 驗證 JWT 格式及有效期限 (exp)
 * 包含 60 秒的時鐘偏移 (clock-skew) 容錯
 */
export function isTokenValid(token: string | null): boolean {
    if (!token || typeof token !== "string") return false;
    try {
        const parts = token.split(".");
        if (parts.length !== 3) return false;
        const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
        const jsonStr = typeof atob !== "undefined"
            ? decodeURIComponent(
                atob(base64)
                    .split("")
                    .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
                    .join("")
            )
            : Buffer.from(base64, "base64").toString("utf-8");
        const payload = JSON.parse(jsonStr);
        if (!payload || typeof payload !== "object") return false;
        if (!payload.exp) return true;
        const now = Math.floor(Date.now() / 1000);
        return payload.exp > now + 60;
    } catch {
        return false;
    }
}

/**
 * 取得當前已緩存的 Session Token (同步快速讀取)
 * 🛡️ 具備過期與格式自癒能力：若發現已過期或損毀自動自 localStorage 剔除
 */
export function getCachedToken(): string | null {
    if (typeof window === "undefined") return null;
    try {
        const token = localStorage.getItem(TOKEN_KEY);
        if (!token) return null;
        if (!isTokenValid(token)) {
            console.warn("🛡️ [Auth] Cached session token is expired or corrupted, purging...");
            localStorage.removeItem(TOKEN_KEY);
            return null;
        }
        return token;
    } catch {
        return null;
    }
}

/**
 * 🛰️ 全域連線與前台恢復監聽器 (Online & Visibility Auto-Exchange)
 * 當 PWA 從完全斷網恢復連線，或自背景喚醒至前台時，
 * 若當前無有效憑證，自動觸發背景換票以確保所有請求可用。
 */
export function initSessionLifecycleListener(): () => void {
    if (typeof window === "undefined") return () => {};

    const handleReconnectOrResume = () => {
        if (navigator.onLine && !getCachedToken()) {
            console.log("🛰️ [Auth] Network restored or resumed, auto-exchanging session token...");
            ensureValidSession().catch(() => {});
        }
    };

    window.addEventListener("online", handleReconnectOrResume);
    document.addEventListener("visibilitychange", handleReconnectOrResume);

    // Initial check on mount
    handleReconnectOrResume();

    return () => {
        window.removeEventListener("online", handleReconnectOrResume);
        document.removeEventListener("visibilitychange", handleReconnectOrResume);
    };
}

/**
 * 取得當前專屬帳號恢復金鑰 (Recovery Key / UUID)
 */
export function getRecoveryKey(): string | null {
    if (typeof window === "undefined") return null;
    try {
        return localStorage.getItem(RECOVERY_KEY);
    } catch {
        return null;
    }
}

/**
 * 確保當前裝置持有有效的 Session JWT
 * - 若已有 Token：直接回傳
 * - 若離線狀態：靜默回傳 null，保障 PWA 離線自癒不中斷
 * - 若聯網狀態：背景向後端換票/領票
 */
export async function ensureValidSession(): Promise<string | null> {
    if (typeof window === "undefined") return null;

    const existingToken = getCachedToken();
    if (existingToken) return existingToken;

    // 🧪 測試環境防護：單元測試環境下若無主動換票需求則直接返回現有狀態，防止 unhandled network fetch
    if (process.env.NODE_ENV === "test" && !process.env.TEST_AUTH_EXCHANGE) {
        return existingToken;
    }

    // 📴 離線防禦：離線時不發起請求，避免觸發網路錯誤阻斷開機
    if (typeof navigator !== "undefined" && !navigator.onLine) {
        console.warn("📴 [Auth] Offline mode detected. Operating locally without session exchange.");
        return null;
    }

    // 🔒 單例防抖：避免多分頁或併發請求重複換票
    if (inFlightSessionPromise) {
        return inFlightSessionPromise;
    }

    inFlightSessionPromise = (async () => {
        try {
            const storedKey = getRecoveryKey();
            const res = await fetch("/api/auth/session", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ recovery_key: storedKey || undefined })
            });

            if (!res.ok) {
                console.warn(`⚠️ [Auth] Session exchange returned HTTP ${res.status}`);
                return null;
            }

            const data = await res.json();
            if (data?.access_token) {
                localStorage.setItem(TOKEN_KEY, data.access_token);
                // 🛡️ 金鑰同步防衛：若初次無 key 或後端強制換發新使用者 (is_new === true)，同步覆寫 localStorage
                if (data.user_id && (!storedKey || data.is_new)) {
                    localStorage.setItem(RECOVERY_KEY, data.user_id);
                }
                return data.access_token as string;
            }
            return null;
        } catch (err) {
            console.warn("⚠️ [Auth] Silent session exchange failed:", err);
            return null;
        } finally {
            inFlightSessionPromise = null;
        }
    })();

    return inFlightSessionPromise;
}

/**
 * 首頁專用：以使用者輸入之恢復金鑰還原帳號 (Recovery Key Restoration)
 */
export async function restoreAccountWithKey(recoveryKey: string): Promise<SessionInfo> {
    const cleanKey = recoveryKey.trim();
    if (!cleanKey) {
        throw new Error("Please enter a valid recovery key");
    }

    const res = await fetch("/api/auth/recover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recovery_key: cleanKey })
    });

    if (!res.ok) {
        if (res.status === 429) {
            throw new Error("Too many recovery attempts. Please wait a minute and try again.");
        }
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || "Invalid recovery key");
    }

    const data = await res.json();
    if (data?.access_token) {
        localStorage.setItem(TOKEN_KEY, data.access_token);
        localStorage.setItem(RECOVERY_KEY, data.user_id);
        return {
            accessToken: data.access_token,
            userId: data.user_id,
            isNew: false
        };
    }

    throw new Error("Failed to restore session token");
}
