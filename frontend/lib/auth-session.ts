/**
 * 🛡️ Tabiji Client-Side Session & Identity Manager
 * Implements the 1Password Secret Key / Local-First Recovery Key paradigm.
 * 
 * Guarantees:
 * 1. Offline-Safe Boot: Never blocks app initialization if offline.
 * 2. In-Flight Deduplication: Multiple concurrent calls resolve the same promise.
 * 3. Zero-Disruption Upgrade: Silently exchanges legacy user_uuid for signed JWT.
 */

import { SyncEngineControl } from "./sync-engine";

const TOKEN_KEY = "tabiji_session_token";
const RECOVERY_KEY = "user_uuid";

let inFlightSessionPromise: Promise<string | null> | null = null;
let isReauthBroadcasting = false;
let lastRestoredAt = 0;
let lastExchangeFailedAt = 0;

export function __resetExchangeFailedForTesting() {
    lastExchangeFailedAt = 0;
}

export const UNIFORM_REAUTH_ERROR = "引繼碼驗證失敗，無法在此設備恢復同步。請確認引繼碼是否正確。";

let lastDismissedAt = 0;

export function dismissReauthPrompt() {
    lastDismissedAt = Date.now();
}

export function triggerReauthPrompt(reason?: string) {
    // 🛡️ 重認證成功後 5 秒冷卻，或使用者點擊「稍後驗證」關閉後 5 秒輕量冷卻防震盪
    if (Date.now() - lastRestoredAt < 5000) return;
    if (Date.now() - lastDismissedAt < 5000) return;
    if (isReauthBroadcasting) return;
    isReauthBroadcasting = true;
    if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("tabiji:session_reauth_required", {
            detail: { reason }
        }));
        // 同步觸發升級事件以保證舊監聽器最大相容性
        window.dispatchEvent(new CustomEvent("tabiji:credential_upgrade_required", {
            detail: { reason }
        }));
    }
    setTimeout(() => { isReauthBroadcasting = false; }, 3000);
}

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

let lastVaultSyncTime = 0;

/**
 * 🛰️ 全域連線與前台恢復監聽器 (Online & Visibility Auto-Exchange)
 * 當 PWA 從完全斷網恢復連線，或自背景喚醒至前台時：
 * 1. 若當前無有效憑證，自動觸發背景換票以確保所有請求可用。
 * 2. 若已有憑證，背景自動向密文保險庫校準引繼碼，杜絕離線/休眠導致之多裝置脫節。
 */
export function initSessionLifecycleListener(): () => void {
    if (typeof window === "undefined") return () => {};

    const handleReconnectOrResume = () => {
        if (!navigator.onLine) return;

        if (!getCachedToken()) {
            console.log("🛰️ [Auth] Network restored or resumed, auto-exchanging session token...");
            ensureValidSession().catch(() => {});
        } else if (Date.now() - lastVaultSyncTime > 15000) {
            lastVaultSyncTime = Date.now();
            fetchLatestRecoveryKey().catch(() => {});
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
        return localStorage.getItem("user_recovery_key") || localStorage.getItem(RECOVERY_KEY);
    } catch {
        return null;
    }
}

/**
 * 確保當前裝置持有有效的 Session JWT
 * - 若已有 Token：直接回傳
 * - 若離線狀態：靜默回傳 null，保障 PWA 離線自癒不中斷
 * - 若聯網狀態：背景向後端換票/領票 (攜帶現有 Token 作為持有證明 Proof-of-Possession 以支援舊裝置升級)
 */
export async function ensureValidSession(): Promise<string | null> {
    if (typeof window === "undefined") return null;

    const existingToken = getCachedToken();
    if (existingToken) return existingToken;

    // 🛡️ 換票冷卻保護：若上次換票已確認 401 失敗，10 秒內阻斷重複轟炸後端
    if (Date.now() - lastExchangeFailedAt < 10000) {
        return null;
    }

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
            const rawToken = typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null;
            const headers: Record<string, string> = { "Content-Type": "application/json" };
            if (rawToken) {
                headers["Authorization"] = `Bearer ${rawToken}`;
            }

            const res = await fetch("/api/auth/session", {
                method: "POST",
                headers,
                body: JSON.stringify({ recovery_key: storedKey || undefined })
            });

            if (!res.ok) {
                console.warn(`⚠️ [Auth] Session exchange returned HTTP ${res.status}`);
                if (res.status === 401) {
                    lastExchangeFailedAt = Date.now();
                    const err = await res.json().catch(() => ({}));
                    const detail = typeof err.detail === "string" ? err.detail : undefined;
                    // 🛡️ 凡換票收到 401，立即攜帶原因喚醒重認證彈窗，拒絕靜默假死
                    triggerReauthPrompt(detail);
                }
                return null;
            }

            const data = await res.json();
            if (data?.access_token) {
                localStorage.setItem(TOKEN_KEY, data.access_token);
                // 🛡️ 雙軌固化：既有 UUID 與新版專屬引繼碼同步持久化
                if (data.recovery_key) {
                    const currentKey = localStorage.getItem("user_recovery_key");
                    if (currentKey !== data.recovery_key) {
                        localStorage.setItem("user_recovery_key", data.recovery_key);
                        if (typeof window !== "undefined") {
                            window.dispatchEvent(new CustomEvent("tabiji:recovery_key_updated", {
                                detail: { recoveryKey: data.recovery_key }
                            }));
                        }
                    }
                }
                if (storedKey && !data.upgraded) {
                    const currentUuid = localStorage.getItem(RECOVERY_KEY);
                    if (currentUuid && data.user_id && data.user_id !== currentUuid) {
                        console.error("🚨 [Auth] Security Sentinel Alert: Session response user_id differs from stored recovery key! Refusing to overwrite key.");
                        throw new Error("Identity mismatch — refusing to overwrite recovery key");
                    }
                } else if (data.user_id) {
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
        if (data.recovery_key) {
            localStorage.setItem("user_recovery_key", data.recovery_key);
        }
        return {
            accessToken: data.access_token,
            userId: data.user_id,
            isNew: false
        };
    }

    throw new Error("Failed to restore session token");
}

/**
 * 個人頁面專用：主動輪替引繼金鑰並使舊金鑰作廢 (Key Rotation & Revocation)
 */
export async function rotateAccountRecoveryKey(): Promise<string> {
    const token = getCachedToken();
    if (!token) throw new Error("No active session token available");

    const res = await fetch("/api/auth/rotate", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
        }
    });

    if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Failed to rotate recovery key (${res.status})`);
    }

    const data = await res.json();
    if (data?.recovery_key) {
        localStorage.setItem("user_recovery_key", data.recovery_key);
        if (data.access_token) {
            localStorage.setItem(TOKEN_KEY, data.access_token);
        }
        return data.recovery_key as string;
    }

    throw new Error("Invalid rotation response from server");
}

/**
 * 跨裝置保險庫同步：主動向雲端密文保險庫獲取最新引繼金鑰
 * 🛡️ 支援寬限期：優先採用快取有效 Token，若已過期則回退攜帶本地歷史 Token 供後端驗簽自癒
 */
export async function fetchLatestRecoveryKey(): Promise<string | null> {
    const token = typeof window !== "undefined" ? (getCachedToken() || localStorage.getItem(TOKEN_KEY)) : null;
    if (!token) return null;

    try {
        const res = await fetch("/api/auth/credential", {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        });
        if (!res.ok) {
            if (res.status === 401 && typeof window !== "undefined") {
                localStorage.removeItem(TOKEN_KEY);
            }
            return null;
        }
        const data = await res.json();
        if (data?.recovery_key) {
            const currentKey = localStorage.getItem("user_recovery_key");
            if (currentKey !== data.recovery_key) {
                localStorage.setItem("user_recovery_key", data.recovery_key);
                if (typeof window !== "undefined") {
                    window.dispatchEvent(new CustomEvent("tabiji:recovery_key_updated", {
                        detail: { recoveryKey: data.recovery_key }
                    }));
                }
            }
            return data.recovery_key as string;
        }
    } catch (err) {
        console.warn("⚠️ [Auth] Failed to sync latest recovery key from vault:", err);
    }
    return null;
}

const TBJ_REC_REGEX = /^tbj_rec_[0-9a-f]{8}_[0-9a-f]{32}$/i;

/**
 * 🛡️ [Sentinel Local-First Patch] 原地重錨定會話憑證 (In-Place Session Re-anchoring)
 * 1. 驗證金鑰格式，防止無效請求衝擊後端
 * 2. 呼叫 /api/auth/session 換票
 * 3. 🛡️ 執行 Wrong-User Guard：比對 user_id.toLowerCase()，防止拿他人金鑰覆蓋本地既有行程
 * 4. 原地寫入 localStorage (不呼叫 localStorage.clear()，確保離線行程 100% 留存)
 * 5. 喚醒 SyncEngineControl.resume()，自動無縫沖刷積壓的離線寄件匣
 */
export async function reanchorSessionWithKey(newRecoveryKey: string): Promise<string> {
    const cleanKey = newRecoveryKey.trim();
    if (!TBJ_REC_REGEX.test(cleanKey)) {
        throw new Error(UNIFORM_REAUTH_ERROR);
    }

    const currentUuid = typeof window !== "undefined" ? localStorage.getItem(RECOVERY_KEY) : null;
    const res = await fetch("/api/auth/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            recovery_key: cleanKey,
            expected_user_id: currentUuid || undefined,
        })
    });

    if (!res.ok) {
        throw new Error(UNIFORM_REAUTH_ERROR);
    }

    const data = await res.json();
    if (!data?.access_token || !data?.user_id) {
        throw new Error(UNIFORM_REAUTH_ERROR);
    }

    // 🛡️ 雙重保險防禦 (Defense-in-Depth)：若伺服器返回異常使用者 ID，直接拋出統一錯誤
    if (currentUuid && data.user_id.toLowerCase() !== currentUuid.toLowerCase()) {
        throw new Error(UNIFORM_REAUTH_ERROR);
    }

    localStorage.setItem(TOKEN_KEY, data.access_token);
    localStorage.setItem("user_recovery_key", cleanKey);
    localStorage.setItem(RECOVERY_KEY, data.user_id);
    lastRestoredAt = Date.now();
    lastExchangeFailedAt = 0;

    if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("tabiji:recovery_key_updated", { detail: { recoveryKey: cleanKey } }));
        window.dispatchEvent(new CustomEvent("tabiji:session_restored"));
    }

    // 恢復寄件匣同步
    SyncEngineControl.resume();
    return data.access_token;
}

/**
 * 🛡️ 清除失效引繼金鑰並重新建立全新訪客會話 (Fresh Anonymous Session Reset)
 */
export async function resetAndStartFreshSession(): Promise<SessionInfo | null> {
    if (typeof window === "undefined") return null;
    localStorage.removeItem("user_recovery_key");
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(RECOVERY_KEY);
    lastExchangeFailedAt = 0;

    try {
        const res = await fetch("/api/auth/session", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({})
        });

        if (!res.ok) return null;
        const data = await res.json();
        if (data?.access_token && data?.user_id) {
            localStorage.setItem(TOKEN_KEY, data.access_token);
            localStorage.setItem(RECOVERY_KEY, data.user_id);
            if (data.recovery_key) {
                localStorage.setItem("user_recovery_key", data.recovery_key);
            }
            lastRestoredAt = Date.now();
            SyncEngineControl.resume();
            return {
                accessToken: data.access_token,
                userId: data.user_id,
                isNew: true
            };
        }
    } catch (err) {
        console.warn("⚠️ [Auth] Failed to start fresh session:", err);
    }
    return null;
}

