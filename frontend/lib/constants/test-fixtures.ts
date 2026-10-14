/**
 * Standardized Test User Pool Constants (5 Static Roles)
 * Used across Playwright E2E tests, Vitest unit tests, and dev emulation.
 */
export const TEST_USERS = {
    OWNER: {
        id: '00000000-0000-0000-0000-000000000001',
        name: '[Test] Owner',
    },
    EDITOR: {
        id: '00000000-0000-0000-0000-000000000002',
        name: '[Test] Editor',
    },
    VIEWER: {
        id: '00000000-0000-0000-0000-000000000003',
        name: '[Test] Viewer',
    },
    CAPSULE: {
        id: '00000000-0000-0000-0000-000000000004',
        name: '[Test] CapsuleTester',
    },
    STRANGER: {
        id: '00000000-0000-0000-0000-000000000005',
        name: '[Test] Stranger',
    },
} as const;

export type TestUserRole = keyof typeof TEST_USERS;
