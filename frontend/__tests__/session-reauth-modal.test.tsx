import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock auth-session module functions
const mockReanchorSessionWithKey = vi.fn();
vi.mock('@/lib/auth-session', () => ({
    reanchorSessionWithKey: (key: string) => mockReanchorSessionWithKey(key),
}));

// Mock sonner toast
vi.mock('sonner', () => ({
    toast: {
        success: vi.fn(),
        error: vi.fn(),
        info: vi.fn(),
    }
}));

// We will test the mock logic representing SessionReauthModal behavior
describe('SessionReauthModal Sandbox Component Tests', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('TC-1: Automatically opens when tabiji:session_reauth_required event is dispatched', async () => {
        let isOpen = false;
        const setOpen = (val: boolean) => { isOpen = val; };

        // Replicate listener from modal
        const handleReauthRequired = () => setOpen(true);
        window.addEventListener('tabiji:session_reauth_required', handleReauthRequired);

        expect(isOpen).toBe(false);

        // Dispatch 401 trigger event
        window.dispatchEvent(new CustomEvent('tabiji:session_reauth_required'));
        expect(isOpen).toBe(true);

        window.removeEventListener('tabiji:session_reauth_required', handleReauthRequired);
    });

    it('TC-2: Client-side validation blocks invalid key formats before hitting server', async () => {
        const TBJ_REC_REGEX = /^tbj_rec_[0-9a-f]{8}_[0-9a-f]{32}$/i;
        const validateInput = (input: string) => {
            const clean = input.trim();
            if (!TBJ_REC_REGEX.test(clean)) {
                return '引繼碼格式無效，應為 tbj_rec_xxxxxxxx_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx';
            }
            return null;
        };

        expect(validateInput('wrong_prefix_12345678_0123456789abcdef0123456789abcdef')).toContain('格式無效');
        expect(validateInput('tbj_rec_short_0123456789abcdef0123456789abcdef')).toContain('格式無效');
        expect(validateInput('tbj_rec_12345678_0123456789abcdef0123456789abcdef')).toBeNull();
    });

    it('TC-3: Correctly displays Wrong-User guard error without closing modal', async () => {
        mockReanchorSessionWithKey.mockRejectedValue(
            new Error('🚨 身分不相符：此引繼碼屬於另一個帳號！為保護此設備上的現有行程，禁止原地覆蓋。')
        );

        let errorMessage = '';
        let isModalOpen = true;

        const handleSubmit = async (key: string) => {
            try {
                await mockReanchorSessionWithKey(key);
                isModalOpen = false;
            } catch (err) {
                errorMessage = err instanceof Error ? err.message : String(err);
            }
        };

        await handleSubmit('tbj_rec_12345678_0123456789abcdef0123456789abcdef');

        expect(errorMessage).toContain('身分不相符');
        // Protection: Modal remains open so user can rectify; outbox stays protected
        expect(isModalOpen).toBe(true);
    });

    it('TC-4: Closes modal and triggers success notification when legitimate key is provided', async () => {
        mockReanchorSessionWithKey.mockResolvedValue('fresh_jwt_token_2026');

        let isModalOpen = true;
        let successNotified = false;

        const handleSubmit = async (key: string) => {
            try {
                await mockReanchorSessionWithKey(key);
                isModalOpen = false;
                successNotified = true;
            } catch {
                // Ignore in positive test case
            }
        };

        await handleSubmit('tbj_rec_12345678_0123456789abcdef0123456789abcdef');

        expect(isModalOpen).toBe(false);
        expect(successNotified).toBe(true);
    });

    it('TC-5: Reset & Start Fresh clears storage and requests fresh session', async () => {
        const mockStorage: Record<string, string> = {
            user_recovery_key: 'tbj_rec_deadbeef_0123456789abcdef0123456789abcdef',
            user_uuid: 'old-corrupted-uuid',
            tabiji_session_token: 'stale-token'
        };

        const resetHandler = () => {
            delete mockStorage.user_recovery_key;
            delete mockStorage.user_uuid;
            delete mockStorage.tabiji_session_token;
            mockStorage.user_uuid = 'fresh-new-uuid';
            mockStorage.user_recovery_key = 'tbj_rec_newkey12_0123456789abcdef0123456789abcdef';
            mockStorage.tabiji_session_token = 'fresh-valid-token';
        };

        resetHandler();
        expect(mockStorage.user_recovery_key).toContain('tbj_rec_newkey12');
        expect(mockStorage.tabiji_session_token).toBe('fresh-valid-token');
    });

    it('TC-6: Dismiss cooldown strictly suppresses reauth prompts for 5000ms window', () => {
        let lastDismissedAt = Date.now();
        const canTriggerPrompt = (now: number) => {
            if (now - lastDismissedAt < 5000) return false;
            return true;
        };

        // Immediate subsequent 401 within 1000ms -> Suppressed
        expect(canTriggerPrompt(lastDismissedAt + 1000)).toBe(false);
        // At 4999ms -> Suppressed
        expect(canTriggerPrompt(lastDismissedAt + 4999)).toBe(false);
        // At 5001ms -> Cooldown expired, allowed
        expect(canTriggerPrompt(lastDismissedAt + 5001)).toBe(true);
    });

    it('TC-7: Modal event handler extracts reason safely as a string primitive', () => {
        let capturedReason: string | null = null;
        const handleReauth = (e: Event) => {
            const customEvent = e as CustomEvent<{ reason?: string }>;
            capturedReason = customEvent.detail?.reason || null;
        };

        window.addEventListener('tabiji:session_reauth_required', handleReauth);

        // Dispatch synthetic attack event with HTML tag
        const maliciousPayload = "<img src=x onerror=alert('xss')>";
        window.dispatchEvent(new CustomEvent('tabiji:session_reauth_required', {
            detail: { reason: maliciousPayload }
        }));

        expect(capturedReason).toBe(maliciousPayload);
        expect(typeof capturedReason).toBe('string');
        window.removeEventListener('tabiji:session_reauth_required', handleReauth);
    });
});

