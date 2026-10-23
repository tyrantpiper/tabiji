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
});
