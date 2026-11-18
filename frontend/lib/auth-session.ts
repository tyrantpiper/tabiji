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
const POP_TOKEN_KEY = "tabiji_pop_token";
const RECOVERY_KEY = "user_uuid";
const TBJ_REC_REGEX = /^tbj_rec_[0-9a-f]{8}_[0-9a-f]{32}$/i;

let inFlightSession: { id: number; fingerprint: string; promise: Promise<string | null> } | null = null;
let sessionAttemptCounter = 0;
let isReauthBroadcasting = false;
let lastRestoredAt = 0;
let lastFailedExchangeFingerprint: string | null = null;
let lastAuthExchangeError: string | null = null;
let lastExchangeTransientFailure = false;

function readEstablishedUuid(): string | null {
    if (typeof window === "undefined") return null;
    const rawCurrentUuid = localStorage.getItem(RECOVERY_KEY)?.trim() || null;
    const isOfflineRecPlaceholder = Boolean(rawCurrentUuid && TBJ_REC_REGEX.test(rawCurrentUuid));
    return (
        rawCurrentUuid &&
        rawCurrentUuid !== "null" &&
        rawCurrentUuid !== "undefined" &&
        !isOfflineRecPlaceholder
    ) ? rawCurrentUuid : null;
}

function buildExchangeFingerprint(storedKey: string | null, establishedUuid: string | null, rawToken: string | null): string {
    return JSON.stringify([storedKey || "", establishedUuid || "", rawToken || ""]);
}

export function getLastAuthExchangeError(): string | null {
    return lastAuthExchangeError;
}

export function wasLastAuthExchangeTransientFailure(): boolean {
    return lastExchangeTransientFailure;
}

export function __resetExchangeFailedForTesting() {
    inFlightSession = null;
    lastVaultSyncTime = 0;
    lastFailedExchangeFingerprint = null;
    lastAuthExchangeError = null;
    lastExchangeTransientFailure = false;
    lastDismissedAt = 0;
    lastRestoredAt = 0;
    isReauthBroadcasting = false;
    isReauthDismissedInMemory = false;
}

export const UNIFORM_REAUTH_ERROR = "引繼碼驗證失敗，無法在此設備恢復同步。請確認引繼碼是否正確。";

let lastDismissedAt = 0;
let isReauthDismissedInMemory = false;

export function dismissReauthPrompt() {
    lastDismissedAt = Date.now();
    isReauthDismissedInMemory = true;
}

/**
 * 🛡️ 檢查當前本機是否具備完整之登入使用者身分 (已登入狀態機閘門)
 */
export function isUserLoggedIn(): boolean {
    if (typeof window === "undefined") return false;
    try {
        const uid = localStorage.getItem(RECOVERY_KEY)?.trim();
        const nick = localStorage.getItem("user_nickname")?.trim();
        const hasValidUid = Boolean(uid && uid !== "null" && uid !== "undefined");
        const hasNicknameAndId = Boolean(nick && hasValidUid);
        const recKey = localStorage.getItem("user_recovery_key")?.trim();
        const hasModernRecoveryKey = Boolean(recKey && recKey !== "null" && recKey !== "undefined");
        return hasNicknameAndId || hasModernRecoveryKey;
    } catch {
        return false;
    }
}

export function triggerReauthPrompt(reason?: string) {
    // 🛡️ 訪客/未登入者硬阻斷：未登入者絕不具備重認證上下文，嚴禁廣播彈窗
    if (!isUserLoggedIn()) {
        console.warn("🛡️ [Auth] Suppressed triggerReauthPrompt: User is not logged in.");
        return;
    }
    // 🛡️ 若使用者於當前頁內明確點擊「稍後驗證」，保持離線靜默至重新整理或成功驗證
    if (isReauthDismissedInMemory) return;
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

function isJwtStructure(token: string | null): boolean {
    if (!token || typeof token !== "string") return false;
    try {
        const parts = token.split(".");
        const b64UrlPart = /^[A-Za-z0-9_-]+={0,2}$/;
        if (parts.length !== 3 || !b64UrlPart.test(parts[0]) || !b64UrlPart.test(parts[1]) || !b64UrlPart.test(parts[2])) {
            return false;
        }
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
        return Boolean(payload && typeof payload === "object" && !Array.isArray(payload));
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
            if (isJwtStructure(token)) {
                localStorage.setItem(POP_TOKEN_KEY, token);
            }
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
        if (!isUserLoggedIn()) return;

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
 * 取得當前有效的 Session JWT，優先自快取讀取，若快取無效或不存在則向後端換票
 * 防止以未簽署之原始引繼碼 (tbj_rec_*) 直通後端導致 401 拒絕
 */
export async function getValidSessionToken(): Promise<string | null> {
    const cached = getCachedToken();
    if (cached) return cached;
    return await ensureValidSession().catch(() => null);
}

/**
 * 確保當前裝置持有有效的 Session JWT
 * - 若已有 Token：直接回傳
 * - 若離線狀態：靜默回傳 null，保障 PWA 離線自癒不中斷
 * - 若聯網狀態：背景向後端換票/領票 (攜帶現有 Token 作為持有證明 Proof-of-Possession 以支援舊裝置升級)
 */
export async function ensureValidSession(forceRefresh: boolean = false): Promise<string | null> {
    if (typeof window === "undefined") return null;

    if (!forceRefresh) {
        const existingToken = getCachedToken();
        if (existingToken) return existingToken;
    }

    const storedKey = getRecoveryKey();
    const establishedUuid = readEstablishedUuid();
    const currentToken = localStorage.getItem(TOKEN_KEY);
    const currentPopToken = localStorage.getItem(POP_TOKEN_KEY);
    const currentPopOrToken = currentToken || currentPopToken;
    const exchangeFingerprint = buildExchangeFingerprint(storedKey, establishedUuid, currentPopOrToken);

    // 🛡️ 失效憑證指紋熔斷保護：
    // 1. 相同失效憑證指紋於本頁週期內鎖定，徹底消除 SWR 15s 輪詢重複轟炸 /api/auth/session 401
    // 2. 憑證指紋變更時（例如跨分頁 localStorage 同步或更新引繼碼/Session Token）立即解鎖，避免舊失敗時間窗誤鎖新憑證
    if (lastFailedExchangeFingerprint !== null && lastFailedExchangeFingerprint === exchangeFingerprint) {
        lastExchangeTransientFailure = false;
        return null;
    }

    // 🔒 單例防抖：僅對相同憑證指紋合併進行中的換票請求，避免指紋更新後誤匯流至舊請求並提前刪毀有效 Token
    if (inFlightSession && inFlightSession.fingerprint === exchangeFingerprint) {
        return inFlightSession.promise;
    }

    let backedUpValidToken: string | null = null;
    if (forceRefresh) {
        try {
            if (currentToken && isJwtStructure(currentToken)) {
                localStorage.setItem(POP_TOKEN_KEY, currentToken);
                if (isTokenValid(currentToken)) {
                    backedUpValidToken = currentToken;
                }
            }
            localStorage.removeItem(TOKEN_KEY);
        } catch {
            // ignore storage errors
        }
    }

    lastExchangeTransientFailure = false;

    const restoreBackedUpTokenOnTransientError = () => {
        lastExchangeTransientFailure = true;
        if (backedUpValidToken && !localStorage.getItem(TOKEN_KEY)) {
            try {
                localStorage.setItem(TOKEN_KEY, backedUpValidToken);
            } catch {
                // ignore storage errors
            }
        }
    };

    // 🧪 測試環境防護：單元測試環境下若無主動換票需求則直接返回現有狀態，防止 unhandled network fetch
    if (process.env.NODE_ENV === "test" && !process.env.TEST_AUTH_EXCHANGE) {
        return getCachedToken();
    }

    // 📴 離線防禦：離線時不發起請求，避免觸發網路錯誤阻斷開機
    if (typeof navigator !== "undefined" && !navigator.onLine) {
        console.warn("📴 [Auth] Offline mode detected. Operating locally without session exchange.");
        restoreBackedUpTokenOnTransientError();
        return null;
    }

    const attemptId = ++sessionAttemptCounter;
    const sessionPromise = (async (): Promise<string | null> => {
        try {
            const latestKey = getRecoveryKey();
            const latestEstablishedUuid = readEstablishedUuid();
            const rawToken = typeof window !== "undefined"
                ? (localStorage.getItem(TOKEN_KEY) || localStorage.getItem(POP_TOKEN_KEY))
                : null;
            const activeFingerprint = buildExchangeFingerprint(latestKey, latestEstablishedUuid, rawToken);
            const headers: Record<string, string> = { "Content-Type": "application/json" };
            if (rawToken) {
                headers["Authorization"] = `Bearer ${rawToken}`;
            }

            const res = await fetch("/api/auth/session", {
                method: "POST",
                headers,
                body: JSON.stringify({
                    recovery_key: latestKey || undefined,
                    expected_user_id: latestEstablishedUuid || undefined,
                })
            });

            const postFetchFingerprint = buildExchangeFingerprint(
                getRecoveryKey(),
                readEstablishedUuid(),
                typeof window !== "undefined"
                    ? (localStorage.getItem(TOKEN_KEY) || localStorage.getItem(POP_TOKEN_KEY))
                    : null
            );
            const isCurrentAttempt = inFlightSession?.id === attemptId;
            if (postFetchFingerprint !== activeFingerprint) {
                const latestCached = getCachedToken();
                if (isCurrentAttempt && !latestCached && !res.ok && res.status !== 401) {
                    restoreBackedUpTokenOnTransientError();
                }
                return latestCached;
            }

            if (!res.ok) {
                console.warn(`⚠️ [Auth] Session exchange returned HTTP ${res.status}`);
                if (res.status === 401) {
                    if (isUserLoggedIn()) {
                        lastExchangeTransientFailure = false;
                        lastFailedExchangeFingerprint = activeFingerprint;
                        const err = await res.json().catch(() => ({}));
                        const detail = typeof err.detail === "string" ? err.detail : undefined;
                        lastAuthExchangeError = detail || null;
                        // 🛡️ 凡換票收到 401，立即攜帶原因喚醒重認證彈窗，拒絕靜默假死
                        triggerReauthPrompt(detail);
                    } else {
                        // 🛡️ 訪客自癒機制：無效孤兒 UUID 立即物理清除，重置冷卻，絕不觸發彈窗！
                        console.warn("🛡️ [Auth] Purging invalid orphan identity for unauthenticated visitor.");
                        localStorage.removeItem(TOKEN_KEY);
                        localStorage.removeItem(POP_TOKEN_KEY);
                        localStorage.removeItem("user_recovery_key");
                        localStorage.removeItem(RECOVERY_KEY);
                        lastFailedExchangeFingerprint = null; // 🔓 立即解開指紋鎖定，保證使用者輸入暱稱時可秒開換票
                        lastAuthExchangeError = null;
                        lastExchangeTransientFailure = false;
                        isReauthDismissedInMemory = false;
                    }
                } else {
                    restoreBackedUpTokenOnTransientError();
                }
                return null;
            }

            const data = await res.json();
            if (data?.access_token) {
                const rawCurrentUuid = localStorage.getItem(RECOVERY_KEY)?.trim() || null;
                const isOfflineRecPlaceholder = Boolean(rawCurrentUuid && TBJ_REC_REGEX.test(rawCurrentUuid));
                const resolvedUuid = (
                    rawCurrentUuid &&
                    rawCurrentUuid !== "null" &&
                    rawCurrentUuid !== "undefined" &&
                    !isOfflineRecPlaceholder
                ) ? rawCurrentUuid : null;

                // 🛡️ 先驗證身分一致性再寫入任何憑證，防止異常回應污染本地 Token / 引繼碼
                if (latestKey && !data.upgraded && resolvedUuid && data.user_id) {
                    if (data.user_id.toLowerCase() !== resolvedUuid.toLowerCase()) {
                        console.error("🚨 [Auth] Security Sentinel Alert: Session response user_id differs from stored recovery key! Refusing to overwrite key.");
                        throw new Error("Identity mismatch — refusing to overwrite recovery key");
                    }
                }

                lastFailedExchangeFingerprint = null;
                lastAuthExchangeError = null;
                lastExchangeTransientFailure = false;
                isReauthDismissedInMemory = false;
                localStorage.setItem(TOKEN_KEY, data.access_token);
                localStorage.setItem(POP_TOKEN_KEY, data.access_token);
                // 🛡️ 雙軌固化：既有 UUID 與新版專屬引繼碼同步持久化
                if (data.recovery_key) {
                    const currentKey = localStorage.getItem("user_recovery_key");
                    if (currentKey !== data.recovery_key) {
                        localStorage.setItem("user_recovery_key", data.recovery_key);
                        if (typeof window !== "undefined") {
                            window.dispatchEvent(new CustomEvent("tabiji:recovery_key_updated", {
                                detail: { 
                                    recoveryKey: data.recovery_key,
                                    source: data.is_new ? "initial_bootstrap" : "session_exchange"
                                }
                            }));
                        }
                    }
                }
                if (data.user_id && (!establishedUuid || data.upgraded)) {
                    localStorage.setItem(RECOVERY_KEY, data.user_id);
                    if (
                        typeof window !== "undefined" &&
                        rawCurrentUuid !== data.user_id &&
                        (isOfflineRecPlaceholder || Boolean(localStorage.getItem("user_nickname")))
                    ) {
                        window.dispatchEvent(new CustomEvent("user-login-state-changed"));
                    }
                }
                return data.access_token as string;
            }
            return null;
        } catch (err) {
            console.warn("⚠️ [Auth] Silent session exchange failed:", err);
            if (inFlightSession?.id === attemptId) {
                restoreBackedUpTokenOnTransientError();
            }
            return null;
        } finally {
            if (inFlightSession?.id === attemptId) {
                inFlightSession = null;
            }
        }
    })();

    inFlightSession = { id: attemptId, fingerprint: exchangeFingerprint, promise: sessionPromise };
    return sessionPromise;
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
        localStorage.setItem(POP_TOKEN_KEY, data.access_token);
        localStorage.setItem(RECOVERY_KEY, data.user_id);
        if (data.recovery_key) {
            localStorage.setItem("user_recovery_key", data.recovery_key);
        }
        lastRestoredAt = Date.now();
        inFlightSession = null;
        lastFailedExchangeFingerprint = null;
        lastAuthExchangeError = null;
        lastExchangeTransientFailure = false;
        isReauthDismissedInMemory = false;
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
    const token = getCachedToken() || (typeof window !== "undefined" ? localStorage.getItem(POP_TOKEN_KEY) : null);
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
            localStorage.setItem(POP_TOKEN_KEY, data.access_token);
        }
        inFlightSession = null;
        lastFailedExchangeFingerprint = null;
        lastAuthExchangeError = null;
        lastExchangeTransientFailure = false;
        isReauthDismissedInMemory = false;
        return data.recovery_key as string;
    }

    throw new Error("Invalid rotation response from server");
}

/**
 * 跨裝置保險庫同步：主動向雲端密文保險庫獲取最新引繼金鑰
 * 🛡️ 支援寬限期：優先採用快取有效 Token，若已過期則回退攜帶本地歷史 Token 供後端驗簽自癒
 */
export async function fetchLatestRecoveryKey(): Promise<string | null> {
    const token = typeof window !== "undefined"
        ? (getCachedToken() || localStorage.getItem(TOKEN_KEY) || localStorage.getItem(POP_TOKEN_KEY))
        : null;
    if (!token) return null;

    try {
        const res = await fetch("/api/auth/credential", {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        });
        if (!res.ok) {
            if (res.status === 401 && typeof window !== "undefined") {
                if (localStorage.getItem(TOKEN_KEY) === token) {
                    if (isJwtStructure(token)) {
                        localStorage.setItem(POP_TOKEN_KEY, token);
                    }
                    localStorage.removeItem(TOKEN_KEY);
                }
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
                        detail: { 
                            recoveryKey: data.recovery_key,
                            source: "remote_sync"
                        }
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

    const currentUuid = readEstablishedUuid();
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
    localStorage.setItem(POP_TOKEN_KEY, data.access_token);
    localStorage.setItem("user_recovery_key", cleanKey);
    localStorage.setItem(RECOVERY_KEY, data.user_id);
    lastRestoredAt = Date.now();
    inFlightSession = null;
    lastFailedExchangeFingerprint = null;
    lastAuthExchangeError = null;
    lastExchangeTransientFailure = false;
    isReauthDismissedInMemory = false;

    if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("tabiji:recovery_key_updated", { detail: { recoveryKey: cleanKey, source: "local_reanchor" } }));
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
    localStorage.removeItem(POP_TOKEN_KEY);
    localStorage.removeItem(RECOVERY_KEY);
    inFlightSession = null;
    lastFailedExchangeFingerprint = null;
    lastAuthExchangeError = null;
    lastExchangeTransientFailure = false;
    isReauthDismissedInMemory = false;

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
            localStorage.setItem(POP_TOKEN_KEY, data.access_token);
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

