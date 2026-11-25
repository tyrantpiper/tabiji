/**
 * Standardized Test User Pool Constants (6 Fixed Dual-Track Roles)
 * Used across Playwright E2E tests, Vitest unit tests, and dev emulation.
 * RYAN_TEST real UUID is injected via environment variable; public source uses synthetic RFC 4122 v4.
 */

const RFC4122_UUID_V4_REGEX =
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export const SYNTHETIC_RYAN_TEST_ID = '00000000-0000-4000-8000-000000000006' as const;

export type TestUserAuthMode = 'modern' | 'legacy';

export interface TestUserFixture {
    readonly id: string;
    readonly name: string;
    readonly authMode: TestUserAuthMode;
    readonly edgeV4Compatible: boolean;
}

export function resolveRyanTestUserId(): string {
    if (typeof process === 'undefined' || !process.env) {
        return SYNTHETIC_RYAN_TEST_ID;
    }
    const candidates = [
        process.env.NEXT_PUBLIC_TEST_USER_RYAN_TEST_ID,
        process.env.TEST_USER_RYAN_TEST_ID,
    ];
    for (const candidate of candidates) {
        const raw = (candidate || '').trim();
        if (raw) {
            return RFC4122_UUID_V4_REGEX.test(raw) ? raw.toLowerCase() : SYNTHETIC_RYAN_TEST_ID;
        }
    }
    return SYNTHETIC_RYAN_TEST_ID;
}

export const TEST_USERS = {
    OWNER: {
        id: '00000000-0000-0000-0000-000000000001',
        name: '[Test] Owner',
        authMode: 'modern',
        edgeV4Compatible: false,
    },
    EDITOR: {
        id: '00000000-0000-0000-0000-000000000002',
        name: '[Test] Editor',
        authMode: 'modern',
        edgeV4Compatible: false,
    },
    VIEWER: {
        id: '00000000-0000-0000-0000-000000000003',
        name: '[Test] Viewer',
        authMode: 'legacy',
        edgeV4Compatible: false,
    },
    CAPSULE: {
        id: '00000000-0000-0000-0000-000000000004',
        name: '[Test] CapsuleTester',
        authMode: 'modern',
        edgeV4Compatible: false,
    },
    STRANGER: {
        id: '00000000-0000-0000-0000-000000000005',
        name: '[Test] Stranger',
        authMode: 'modern',
        edgeV4Compatible: false,
    },
    RYAN_TEST: {
        id: resolveRyanTestUserId(),
        name: 'Ryan Test',
        authMode: 'modern',
        edgeV4Compatible: true,
    },
} as const satisfies Record<string, TestUserFixture>;

export type TestUserRole = keyof typeof TEST_USERS;

export const STATIC_ROLE_TEST_USER_IDS = [
    TEST_USERS.OWNER.id,
    TEST_USERS.EDITOR.id,
    TEST_USERS.VIEWER.id,
    TEST_USERS.CAPSULE.id,
    TEST_USERS.STRANGER.id,
] as const;

export const ALL_FIXED_TEST_USER_IDS = [
    ...STATIC_ROLE_TEST_USER_IDS,
    TEST_USERS.RYAN_TEST.id,
] as const;
