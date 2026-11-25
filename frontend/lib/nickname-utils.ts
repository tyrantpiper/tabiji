/**
 * 🛡️ Shared Client-Side Nickname Sanitization & Placeholder Guard Utilities
 * Pure zero-side-effect helpers kept separate from auth-session.ts so Vitest mocks
 * of `@/lib/auth-session` never disable UI nickname sanitization.
 *
 * Parity contract with backend `sanitize_bootstrap_name` (`backend/routers/auth.py`):
 * - Strips ASCII control chars (0x00-0x1f except whitespace, 0x7f-0x9f) and Unicode
 *   zero-width / format / Bidi override code points.
 * - Collapses all Unicode whitespace (`\s+`, incl. fullwidth U+3000 & NBSP) to single space.
 * - Rejects invisible-only strings (incl. stray ZWJ/VS15/VS16).
 * - Clamps to at most 64 Unicode code points on Grapheme Cluster boundaries via Intl.Segmenter.
 * - Re-checks invalid literals (`null`/`undefined`) and default placeholders AFTER clamping.
 */

export const MAX_NICKNAME_LENGTH = 64;

const INVALID_LITERAL_NICKNAMES = new Set(["null", "undefined"]);

const DEFAULT_PLACEHOLDER_NICKNAMES = new Set([
    "traveler",
    "new traveler",
    "unknown traveler",
    "legacy traveler",
    "null",
    "undefined",
]);

function isStrippedInvisibleOrControlCode(code: number): boolean {
    if (code === 0x09 || code === 0x0a || code === 0x0d) return false;
    if (code < 0x20 || (code >= 0x7f && code <= 0x9f)) return true;
    return (
        code === 0x00ad ||
        code === 0x061c ||
        code === 0x200b ||
        code === 0x200c ||
        code === 0x200e ||
        code === 0x200f ||
        (code >= 0x202a && code <= 0x202e) ||
        (code >= 0x2060 && code <= 0x206f) ||
        code === 0xfeff
    );
}

function normalizeNicknameText(raw: string): string {
    let cleaned = "";
    for (let i = 0; i < raw.length; i++) {
        const code = raw.charCodeAt(i);
        if (isStrippedInvisibleOrControlCode(code)) {
            continue;
        }
        cleaned += raw[i];
    }
    const normalized = cleaned
        .replace(/\s+/g, " ")
        .trim()
        .replace(/^\u200d+|\u200d+$/g, "")
        .trim();
    if (!normalized || !normalized.replace(/[\u200d\ufe0e\ufe0f\s]+/g, "")) {
        return "";
    }
    return normalized;
}

function truncateGraphemeSafe(text: string, maxCodePoints: number): string {
    const codePoints = Array.from(text);
    if (codePoints.length <= maxCodePoints) {
        return text;
    }

    if (typeof Intl !== "undefined" && typeof Intl.Segmenter === "function") {
        const segmenter = new Intl.Segmenter("en", { granularity: "grapheme" });
        let out = "";
        let used = 0;
        for (const { segment } of segmenter.segment(text)) {
            const segLen = Array.from(segment).length;
            if (used + segLen > maxCodePoints) {
                break;
            }
            out += segment;
            used += segLen;
        }
        return out.trim().replace(/\u200d+$/g, "").trim();
    }

    return codePoints
        .slice(0, maxCodePoints)
        .join("")
        .trim()
        .replace(/\u200d+$/g, "")
        .trim();
}

/**
 * 🛡️ 判斷暱稱是否為系統預設佔位符（或空值 / 無效字串）
 */
export function isDefaultPlaceholderNickname(name: string | null | undefined): boolean {
    if (!name || typeof name !== "string") return true;
    const normalized = normalizeNicknameText(name);
    if (!normalized) return true;
    return DEFAULT_PLACEHOLDER_NICKNAMES.has(normalized.toLowerCase());
}

/**
 * 🛡️ 清洗使用者主動輸入／存檔之暱稱（適用 LandingPage 登入與 ProfileView 儲存）：
 * - 剝除控制／零寬／Bidi 字元並折疊所有 Unicode 空白
 * - 依 Grapheme 邊界安全截斷至 64 碼點（與後端完全對稱，避免二次 updateProfile 覆蓋清洗結果）
 * - 截斷前後皆嚴格封鎖空白、純隱形字元與字面 `"null"`/`"undefined"` (FP-095)
 */
export function normalizeUserInputNickname(name: string | null | undefined): string | undefined {
    if (!name || typeof name !== "string") return undefined;
    const normalized = normalizeNicknameText(name);
    if (!normalized || INVALID_LITERAL_NICKNAMES.has(normalized.toLowerCase())) {
        return undefined;
    }
    const bounded = truncateGraphemeSafe(normalized, MAX_NICKNAME_LENGTH);
    if (
        !bounded ||
        !bounded.replace(/[\u200d\ufe0e\ufe0f\s]+/g, "") ||
        INVALID_LITERAL_NICKNAMES.has(bounded.toLowerCase())
    ) {
        return undefined;
    }
    return bounded;
}

/**
 * 🛡️ 清洗並回傳有效非預設暱稱；若為預設佔位名（含 Traveler / New Traveler 等）或空白則回傳 undefined
 */
export function sanitizeEffectiveNickname(name: string | null | undefined): string | undefined {
    const candidate = normalizeUserInputNickname(name);
    if (!candidate || DEFAULT_PLACEHOLDER_NICKNAMES.has(candidate.toLowerCase())) {
        return undefined;
    }
    return candidate;
}
