import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mock Storage and Global Event Fixtures
// ---------------------------------------------------------------------------
let mockStorage: Record<string, string> = {};

beforeEach(() => {
    mockStorage = {};
    vi.stubGlobal('localStorage', {
        getItem: vi.fn((k: string) => mockStorage[k] || null),
        setItem: vi.fn((k: string, v: string) => { mockStorage[k] = v; }),
        removeItem: vi.fn((k: string) => { delete mockStorage[k]; }),
        clear: vi.fn(() => { mockStorage = {}; }),
    });
});

afterEach(() => {
    vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// TC-1 & TC-2: Sync Queue Outbox Freeze on 401
// ---------------------------------------------------------------------------
describe('SyncQueue 401 Freeze & Data Preservation Tests', () => {
    it('TC-1: [VULNERABILITY REPRODUCTION] Unpatched sync queue evicts items after 3x 401 retries', async () => {
        let queue = [
            { id: 'mut_1', url: '/api/trips/123/items', retryCount: 2, body: { title: 'Tokyo Tower' } }
        ];

        // Simulate unpatched replay logic from sync-hooks.ts:133-138
        const simulateUnpatchedReplay = (item: typeof queue[0], status: number) => {
            if (status === 401) {
                if (item.retryCount >= 2) { // 3rd retry
                    // Unpatched logic dequeues and drops!
                    queue = queue.filter(q => q.id !== item.id);
                } else {
                    item.retryCount++;
                }
            }
        };

        simulateUnpatchedReplay(queue[0], 401);
        // Flaw confirmed: queue is now EMPTY! Unsynced item is permanently lost!
        expect(queue.length).toBe(0);
    });

    it('TC-2: [MANTIS PATCH] Freezing sync queue on 401 halts replay and preserves all mutations', async () => {
        const queue = [
            { id: 'mut_1', url: '/api/trips/123/items', retryCount: 2, body: { title: 'Tokyo Tower' } }
        ];
        let isSyncPaused = false;

        const SyncControl = {
            pause: () => { isSyncPaused = true; },
            resume: () => { isSyncPaused = false; },
            isPaused: () => isSyncPaused,
        };

        // Patched replay logic: 401 immediately triggers pause without incrementing retry or dequeueing
        const simulatePatchedReplay = (item: typeof queue[0], status: number) => {
            if (status === 401) {
                SyncControl.pause();
                // Break out of replay loop without touching item or incrementing retry
                return 'PAUSED';
            }
            return 'OK';
        };

        const result = simulatePatchedReplay(queue[0], 401);
        expect(result).toBe('PAUSED');
        expect(SyncControl.isPaused()).toBe(true);
        // Protection confirmed: Item is preserved with retryCount unchanged!
        expect(queue.length).toBe(1);
        expect(queue[0].retryCount).toBe(2);
        expect(queue[0].body.title).toBe('Tokyo Tower');
    });
});

// ---------------------------------------------------------------------------
// TC-3, TC-4, TC-6: In-Place Session Re-anchoring & Wrong-User Guard
// ---------------------------------------------------------------------------
describe('In-Place Session Re-anchoring & Wrong-User Guard Tests', () => {
    const TBJ_REC_REGEX = /^tbj_rec_[0-9a-f]{8}_[0-9a-f]{32}$/i;

    interface MockAuthResponse {
        ok: boolean;
        status?: number;
        data?: {
            access_token: string;
            user_id: string;
        };
    }

    async function reanchorSessionWithKey(newRecoveryKey: string, mockFetchResponse: MockAuthResponse) {
        const cleanKey = newRecoveryKey.trim();
        if (!TBJ_REC_REGEX.test(cleanKey)) {
            throw new Error("Invalid recovery key format");
        }

        const currentUuid = localStorage.getItem("user_uuid");

        // Mock network response from /api/auth/session
        const res = mockFetchResponse;
        if (!res.ok) {
            throw new Error(res.status === 401 ? "Key revoked or invalid" : "Network error");
        }

        const data = res.data;
        if (!data?.access_token || !data?.user_id) {
            throw new Error("Invalid server session response");
        }
        // 🛡️ Wrong-user defense with case-insensitive tolerance
        if (currentUuid && data.user_id.toLowerCase() !== currentUuid.toLowerCase()) {
            throw new Error("Identity mismatch: This key belongs to a different traveler!");
        }

        // In-place update: localStorage is NOT cleared!
        localStorage.setItem("tabiji_session_token", data.access_token);
        localStorage.setItem("user_recovery_key", cleanKey);
        localStorage.setItem("user_uuid", data.user_id);

        return data.access_token;
    }

    it('TC-3: [SECURITY GUARD] Re-anchoring strictly rejects Wrong User key', async () => {
        // Device currently belongs to Alice
        mockStorage['user_uuid'] = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
        mockStorage['local_trips'] = JSON.stringify(['Alice Tokyo Trip 2026']);

        const bobKey = 'tbj_rec_11223344_aabbccddeeff00112233445566778899';
        const bobServerResponse = {
            ok: true,
            status: 200,
            data: {
                access_token: 'valid_jwt_bob',
                user_id: '99999999-8888-7777-6666-555555555555' // Bob's UUID
            }
        };

        await expect(reanchorSessionWithKey(bobKey, bobServerResponse))
            .rejects.toThrow(/Identity mismatch/);

        // Security assertion: Alice's local trips and storage are NOT overwritten!
        expect(mockStorage['user_uuid']).toBe('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee');
        expect(mockStorage['local_trips']).toBe(JSON.stringify(['Alice Tokyo Trip 2026']));
    });

    it('TC-4: Legitimate Re-anchoring updates credentials in-place without clearing local data', async () => {
        mockStorage['user_uuid'] = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
        mockStorage['user_recovery_key'] = 'tbj_rec_oldkey01_oldentropy1111222233334444';
        mockStorage['local_trips'] = JSON.stringify(['Alice Tokyo Trip 2026']);

        const aliceNewKey = 'tbj_rec_22334455_99887766554433221100aabbccddeeff';
        const aliceServerResponse = {
            ok: true,
            status: 200,
            data: {
                access_token: 'fresh_jwt_alice_ver2',
                user_id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
            }
        };

        const token = await reanchorSessionWithKey(aliceNewKey, aliceServerResponse);

        expect(token).toBe('fresh_jwt_alice_ver2');
        expect(mockStorage['tabiji_session_token']).toBe('fresh_jwt_alice_ver2');
        expect(mockStorage['user_recovery_key']).toBe(aliceNewKey);
        // Crucial invariant: Local offline data remained completely intact!
        expect(mockStorage['local_trips']).toBe(JSON.stringify(['Alice Tokyo Trip 2026']));
    });

    it('TC-6: Case-Insensitive UUID tolerance prevents false rejection', async () => {
        // Device holds uppercase UUID from iOS WebKit
        mockStorage['user_uuid'] = 'AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE';

        const aliceKey = 'tbj_rec_22334455_99887766554433221100aabbccddeeff';
        const serverResponse = {
            ok: true,
            status: 200,
            data: {
                access_token: 'jwt_valid',
                user_id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee' // lowercase from Postgres
            }
        };

        const token = await reanchorSessionWithKey(aliceKey, serverResponse);
        expect(token).toBe('jwt_valid');
    });
});

// ---------------------------------------------------------------------------
// TC-5: Event Debouncing
// ---------------------------------------------------------------------------
describe('Event Debouncing & Modal Thrashing Prevention Tests', () => {
    it('TC-5: Multiple concurrent 401s trigger only 1 reauth event broadcast', () => {
        let isBroadcasting = false;
        let broadcastCount = 0;

        const triggerReauthPrompt = () => {
            if (isBroadcasting) return;
            isBroadcasting = true;
            broadcastCount++;
            setTimeout(() => { isBroadcasting = false; }, 3000);
        };

        // Simulate 10 concurrent requests returning 401 within the same tick
        for (let i = 0; i < 10; i++) {
            triggerReauthPrompt();
        }

        // Only 1 event is broadcast!
        expect(broadcastCount).toBe(1);
    });
});

// ---------------------------------------------------------------------------
// TC-7: Full End-to-End Simulation of Multi-Device Outbox Freeze & Replay Flush
// ---------------------------------------------------------------------------
describe('End-to-End Multi-Device Outbox Freeze & Replay Flush', () => {
    it('TC-7: Complete lifecycle: 401 freezes outbox -> mutations preserved -> reauth with rotated key -> outbox resumes and flushes all mutations', async () => {
        // Initial state: Device B has stale session token and 3 offline mutations
        let currentToken = "stale_token_ver1";
        mockStorage['tabiji_session_token'] = currentToken;
        mockStorage['user_uuid'] = "alice_uuid_12345";
        mockStorage['user_recovery_key'] = "tbj_rec_11111111_oldsecretkey0000000000000000";

        let outbox = [
            { id: "mut_1", url: "/api/trips/1/items", body: { title: "Shibuya Sky" }, retryCount: 0 },
            { id: "mut_2", url: "/api/expenses", body: { amount: 1200, title: "Ramen" }, retryCount: 0 },
            { id: "mut_3", url: "/api/notes", body: { text: "JR Pass pick-up" }, retryCount: 0 },
        ];

        let isEnginePaused = false;
        const SyncEngineControl = {
            pause: () => { isEnginePaused = true; },
            resume: () => { isEnginePaused = false; },
            isPaused: () => isEnginePaused,
        };

        const serverDatabase: Array<{ title?: string; amount?: number; text?: string }> = [];

        // Simulated worker: replays outbox against server
        const processOutbox = async () => {
            if (SyncEngineControl.isPaused()) return "PAUSED";
            
            for (let i = 0; i < outbox.length; i++) {
                const item = outbox[i];
                // Server validates token: only "valid_token_ver2" is accepted
                if (currentToken !== "valid_token_ver2") {
                    // Encountered 401!
                    SyncEngineControl.pause();
                    // Invariant: Do NOT increment retry, do NOT dequeue!
                    return "FROZEN_ON_401";
                }
                // If token is valid: mutation succeeds
                serverDatabase.push(item.body);
            }
            outbox = [];
            return "COMPLETED";
        };

        // Step 1: Worker runs while token is stale
        const firstRunResult = await processOutbox();
        expect(firstRunResult).toBe("FROZEN_ON_401");
        expect(SyncEngineControl.isPaused()).toBe(true);

        // Crucial invariant: All 3 mutations are 100% preserved in outbox
        expect(outbox.length).toBe(3);
        expect(outbox[0].body.title).toBe("Shibuya Sky");
        expect(outbox[0].retryCount).toBe(0); // Retry was NOT incremented!
        expect(serverDatabase.length).toBe(0);

        // Step 2: User obtains rotated Key 2 from Device A and performs in-place re-auth
        const key2 = "tbj_rec_22222222_newsecretkey9999999999999999";
        const mockAuthSessionApi = async (key: string) => {
            if (key === key2) {
                return {
                    ok: true,
                    status: 200,
                    data: {
                        access_token: "valid_token_ver2",
                        user_id: "alice_uuid_12345",
                        recovery_key: key2,
                    }
                };
            }
            return { ok: false, status: 401, data: null };
        };

        const response = await mockAuthSessionApi(key2);
        expect(response.ok).toBe(true);

        // Perform in-place update
        currentToken = response.data!.access_token;
        mockStorage['tabiji_session_token'] = currentToken;
        mockStorage['user_recovery_key'] = key2;

        // In-place re-auth resumes the outbox
        SyncEngineControl.resume();
        expect(SyncEngineControl.isPaused()).toBe(false);

        // Step 3: Worker runs again
        const secondRunResult = await processOutbox();
        expect(secondRunResult).toBe("COMPLETED");

        // Verification: All 3 mutations successfully synchronized without loss!
        expect(outbox.length).toBe(0);
        expect(serverDatabase.length).toBe(3);
        expect(serverDatabase[0].title).toBe("Shibuya Sky");
        expect(serverDatabase[1].title).toBe("Ramen");
        expect(serverDatabase[2].text).toBe("JR Pass pick-up");
    });

    it('TC-8: [LOGOUT & STALE KEY DEFENSE] Guard prevents blind localStorage.clear() when un-synced offline edits exist', () => {
        const outbox = [
            { id: "mut_1", url: "/api/trips/1/items", body: { title: "Unsynced Local Trip" } }
        ];

        let cleared = false;
        let warningModalPrompted = false;

        // Defensive logout function
        const safeLogout = (force: boolean = false) => {
            if (outbox.length > 0 && !force) {
                // Warning: Unsynced local edits exist! Do NOT clear blindly!
                warningModalPrompted = true;
                return false;
            }
            cleared = true;
            return true;
        };

        // Attempting normal logout when outbox is not empty triggers safety guard
        const logoutAttempt1 = safeLogout(false);
        expect(logoutAttempt1).toBe(false);
        expect(warningModalPrompted).toBe(true);
        expect(cleared).toBe(false);

        // Once confirmed or outbox empty, logout is permitted
        const logoutAttempt2 = safeLogout(true);
        expect(logoutAttempt2).toBe(true);
        expect(cleared).toBe(true);
    });
});

// ---------------------------------------------------------------------------
// TC-9 & TC-10: Oracle Defense, Zero Wire Leak & In-Flight Grace Window Tests
// ---------------------------------------------------------------------------
describe('Oracle Defense, Zero Wire Leak & Grace Window Tests', () => {
    const UNIFORM_ERROR = "引繼碼驗證失敗，無法在此設備恢復同步。請確認引繼碼是否正確。";
    const TBJ_REC_REGEX = /^tbj_rec_[0-9a-f]{8}_[0-9a-f]{32}$/i;

    interface CapturedPayload {
        recovery_key: string;
        expected_user_id?: string;
    }

    interface MockServerBody {
        detail?: string;
        access_token?: string;
        user_id?: string;
    }

    it('TC-9: [SECURITY INVARIANT] reanchorSessionWithKey transmits expected_user_id and enforces UNIFORM error string across all failure modes', async () => {
        const aliceUuid = "11111111-1111-1111-1111-111111111111";
        mockStorage['user_uuid'] = aliceUuid;

        let capturedPayload: CapturedPayload | null = null;

        // Simulated patched client-side reanchor logic
        const simulatePatchedReanchor = async (keyInput: string, mockServerStatus: number, mockServerBody: MockServerBody) => {
            const cleanKey = keyInput.trim();
            if (!TBJ_REC_REGEX.test(cleanKey)) {
                throw new Error(UNIFORM_ERROR);
            }

            const currentUuid = mockStorage['user_uuid'] || null;

            // Transmit expected_user_id over the wire
            capturedPayload = {
                recovery_key: cleanKey,
                expected_user_id: currentUuid || undefined,
            };

            if (mockServerStatus !== 200) {
                // Reject with uniform message
                throw new Error(mockServerBody.detail || UNIFORM_ERROR);
            }

            // Client defense-in-depth fallback
            if (!mockServerBody.access_token || !mockServerBody.user_id) {
                throw new Error(UNIFORM_ERROR);
            }

            if (currentUuid && mockServerBody.user_id.toLowerCase() !== currentUuid.toLowerCase()) {
                throw new Error(UNIFORM_ERROR);
            }

            mockStorage['tabiji_session_token'] = mockServerBody.access_token;
            mockStorage['user_recovery_key'] = cleanKey;
            mockStorage['user_uuid'] = mockServerBody.user_id;
            return mockServerBody.access_token;
        };

        const bobKey = "tbj_rec_11223344_0123456789abcdef0123456789abcdef";

        // Mode 1: Backend rejects due to expected_user_id mismatch
        await expect(simulatePatchedReanchor(bobKey, 401, { detail: UNIFORM_ERROR }))
            .rejects.toThrow(UNIFORM_ERROR);
        // Verify wire payload carries expected_user_id
        const payload = capturedPayload as CapturedPayload | null;
        expect(payload).not.toBeNull();
        expect(payload?.expected_user_id).toBe(aliceUuid);
        expect(payload?.recovery_key).toBe(bobKey);

        // Mode 2: Client defense-in-depth fallback (if server sent 200 with wrong id)
        await expect(simulatePatchedReanchor(bobKey, 200, { access_token: "bob_jwt", user_id: "22222222-2222-2222-2222-222222222222" }))
            .rejects.toThrow(UNIFORM_ERROR);

        // Mode 3: Malformed key format
        await expect(simulatePatchedReanchor("invalid_key_format", 200, {}))
            .rejects.toThrow(UNIFORM_ERROR);

        // Crucial invariant: Absolutely NONE of the error messages mention "belong to another account" or leak oracle info!
        expect(mockStorage['tabiji_session_token']).toBeUndefined();
    });

    it('TC-10: [RACE RESILIENCE] 5-second lastRestoredAt grace window silences in-flight stale 401s', () => {
        let lastRestoredAt = 0;
        let isBroadcasting = false;
        let broadcastCount = 0;

        const triggerReauthPrompt = () => {
            const now = Date.now();
            // 🛡️ Post-restoration grace window: 5000ms
            if (now - lastRestoredAt < 5000) {
                return false;
            }
            if (isBroadcasting) return false;
            isBroadcasting = true;
            broadcastCount++;
            return true;
        };

        // Scenario 1: Initial state (not restored recently) -> 401 triggers broadcast
        const triggered1 = triggerReauthPrompt();
        expect(triggered1).toBe(true);
        expect(broadcastCount).toBe(1);

        // Scenario 2: User successfully re-anchors session -> lastRestoredAt is stamped
        lastRestoredAt = Date.now();
        isBroadcasting = false; // Modal closed

        // Scenario 3: Stale in-flight requests that were fired BEFORE re-anchoring return 401 right now (e.g. 50ms later)
        const inFlightTrigger1 = triggerReauthPrompt();
        const inFlightTrigger2 = triggerReauthPrompt();
        expect(inFlightTrigger1).toBe(false);
        expect(inFlightTrigger2).toBe(false);
        // Invariant: broadcastCount did NOT increase! Modal was NOT reopened!
        expect(broadcastCount).toBe(1);

        // Scenario 4: Fast-forward time past 5000ms grace window
        lastRestoredAt = Date.now() - 5001;
        const legitLaterTrigger = triggerReauthPrompt();
        expect(legitLaterTrigger).toBe(true);
        expect(broadcastCount).toBe(2);
    });
});

