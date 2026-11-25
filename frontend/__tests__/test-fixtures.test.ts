import { createHash } from 'node:crypto';
import { afterEach, describe, expect, it } from 'vitest';
import {
    ALL_FIXED_TEST_USER_IDS,
    STATIC_ROLE_TEST_USER_IDS,
    SYNTHETIC_RYAN_TEST_ID,
    TEST_USERS,
    resolveRyanTestUserId,
} from '@/lib/constants/test-fixtures';

const RFC4122_UUID_V4_REGEX =
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MAIN_USER_SHA256 =
    '1b9110f155d92fc3cee7dba9833489dd1e29c5ee57b54fafb7d7ed6b5e100d2d';
const PERSONAL_QA_SHA256 =
    'df53a6abe0fa38b52ecf55f21d794ac5d47e6d370af2c6ac7d6f6d3c829e0c29';

function sha256(value: string): string {
    return createHash('sha256').update(value.trim().toLowerCase(), 'utf-8').digest('hex');
}

describe('Standardized 6-Account Dual-Track Test Fixtures (frontend)', () => {
    const origNextPublic = process.env.NEXT_PUBLIC_TEST_USER_RYAN_TEST_ID;
    const origServer = process.env.TEST_USER_RYAN_TEST_ID;

    afterEach(() => {
        if (origNextPublic === undefined) {
            delete process.env.NEXT_PUBLIC_TEST_USER_RYAN_TEST_ID;
        } else {
            process.env.NEXT_PUBLIC_TEST_USER_RYAN_TEST_ID = origNextPublic;
        }
        if (origServer === undefined) {
            delete process.env.TEST_USER_RYAN_TEST_ID;
        } else {
            process.env.TEST_USER_RYAN_TEST_ID = origServer;
        }
    });

    it('defines all 6 unique roles with dual-track authMode and Edge Shield v4 metadata', () => {
        expect(Object.keys(TEST_USERS).sort()).toEqual([
            'CAPSULE',
            'EDITOR',
            'OWNER',
            'RYAN_TEST',
            'STRANGER',
            'VIEWER',
        ]);
        expect(STATIC_ROLE_TEST_USER_IDS).toHaveLength(5);
        expect(ALL_FIXED_TEST_USER_IDS).toHaveLength(6);
        expect(new Set(ALL_FIXED_TEST_USER_IDS).size).toBe(6);

        // Only VIEWER is pinned legacy; all other 5 are modern
        const legacyRoles = Object.entries(TEST_USERS)
            .filter(([, meta]) => meta.authMode === 'legacy')
            .map(([role]) => role);
        expect(legacyRoles).toEqual(['VIEWER']);

        // Only RYAN_TEST is Edge Shield RFC 4122 UUID v4 compatible
        const edgeRoles = Object.entries(TEST_USERS)
            .filter(([, meta]) => meta.edgeV4Compatible)
            .map(([role]) => role);
        expect(edgeRoles).toEqual(['RYAN_TEST']);

        expect(SYNTHETIC_RYAN_TEST_ID).toBe('00000000-0000-4000-8000-000000000006');
        expect(RFC4122_UUID_V4_REGEX.test(SYNTHETIC_RYAN_TEST_ID)).toBe(true);
        expect(sha256(SYNTHETIC_RYAN_TEST_ID)).not.toBe(MAIN_USER_SHA256);
        expect(sha256(SYNTHETIC_RYAN_TEST_ID)).not.toBe(PERSONAL_QA_SHA256);
    });

    it('resolves RYAN_TEST via RFC 4122 v4 env injection with whitespace fallthrough and safe fallback', () => {
        delete process.env.NEXT_PUBLIC_TEST_USER_RYAN_TEST_ID;
        delete process.env.TEST_USER_RYAN_TEST_ID;
        expect(resolveRyanTestUserId()).toBe(SYNTHETIC_RYAN_TEST_ID);

        // Non-v4 UUID falls back safely to synthetic RFC 4122 v4
        process.env.NEXT_PUBLIC_TEST_USER_RYAN_TEST_ID = '00000000-0000-0000-0000-000000000099';
        expect(resolveRyanTestUserId()).toBe(SYNTHETIC_RYAN_TEST_ID);

        // Whitespace-only primary env var falls through to TEST_USER_RYAN_TEST_ID
        const validV4 = '12345678-1234-4123-8123-123456789ABC';
        process.env.NEXT_PUBLIC_TEST_USER_RYAN_TEST_ID = '   ';
        process.env.TEST_USER_RYAN_TEST_ID = validV4;
        expect(resolveRyanTestUserId()).toBe(validV4.toLowerCase());
    });
});
