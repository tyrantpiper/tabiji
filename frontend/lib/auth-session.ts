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
 * 取得當前已緩存的 Session Token (同步快速讀取)
 */
export function getCachedToken(): string | null {
    if (typeof window === "undefined") return null;
    try {
        return localStorage.getItem(TOKEN_KEY);
    } catch {
        return null;
    }
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
                if (data.user_id && !storedKey) {
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
