import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MCPConnectorDialog } from '@/components/ai/mcp-connector-dialog'
import * as authSession from '@/lib/auth-session'
import { toast } from 'sonner'

// Mock sonner toast
vi.mock('sonner', () => ({
    toast: {
        success: vi.fn(),
        error: vi.fn(),
        warning: vi.fn(),
        info: vi.fn(),
    }
}))

describe('MCPConnectorDialog Test Suite', () => {
    const mockJwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXIifQ.mock_signature"

    beforeEach(() => {
        vi.clearAllMocks()
        localStorage.clear()
        vi.spyOn(authSession, 'getValidSessionToken').mockResolvedValue(mockJwt)
    })

    it('TDD-1: Automatically loads standard signed session JWT and renders masked password input', async () => {
        render(<MCPConnectorDialog open={true} onOpenChange={vi.fn()} />)

        // Wait for token to load into password input
        await waitFor(() => {
            const passwordInput = document.querySelector('input[type="password"]') as HTMLInputElement | null
            expect(passwordInput).not.toBeNull()
            expect(passwordInput?.value).toBe(mockJwt)
        })

        expect(authSession.getValidSessionToken).toHaveBeenCalled()
    })

    it('TDD-2: Eye button toggles token input type between password and text', async () => {
        render(<MCPConnectorDialog open={true} onOpenChange={vi.fn()} />)

        await waitFor(() => {
            const tokenInput = document.querySelector('input[value="' + mockJwt + '"]') as HTMLInputElement | null
            expect(tokenInput).not.toBeNull()
            expect(tokenInput?.type).toBe('password')
            expect(screen.getByTitle(/顯示憑證|Show Token/i)).toBeDefined()
        })

        const toggleBtn = screen.getByTitle(/顯示憑證|Show Token/i)
        let tokenInput = document.querySelector('input[value="' + mockJwt + '"]') as HTMLInputElement
        expect(tokenInput).not.toBeNull()
        expect(tokenInput.type).toBe('password')

        // Click eye to reveal
        fireEvent.click(toggleBtn)
        await waitFor(() => {
            tokenInput = document.querySelector('input[value="' + mockJwt + '"]') as HTMLInputElement
            expect(tokenInput).not.toBeNull()
            expect(tokenInput.type).toBe('text')
        })

        // Click eye to hide
        fireEvent.click(toggleBtn)
        await waitFor(() => {
            tokenInput = document.querySelector('input[value="' + mockJwt + '"]') as HTMLInputElement
            expect(tokenInput).not.toBeNull()
            expect(tokenInput.type).toBe('password')
        })
    })

    it('TDD-3: Server URL is rendered and copy triggers clipboard API and toast', async () => {
        const writeTextMock = vi.fn().mockResolvedValue(undefined)
        Object.assign(navigator, {
            clipboard: {
                writeText: writeTextMock
            }
        })

        render(<MCPConnectorDialog open={true} onOpenChange={vi.fn()} />)

        await waitFor(() => {
            expect(screen.getByText(/複製網址|Copy URL/i)).toBeDefined()
        })

        const copyUrlBtn = screen.getByText(/複製網址|Copy URL/i)
        fireEvent.click(copyUrlBtn)

        await waitFor(() => {
            expect(writeTextMock).toHaveBeenCalledWith(expect.stringContaining('/api/mcp'))
            expect(toast.success).toHaveBeenCalled()
        })
    })

    it('TDD-4: Non-HTTPS environment displays warning banner for cloud AI', async () => {
        render(<MCPConnectorDialog open={true} onOpenChange={vi.fn()} />)

        await waitFor(() => {
            expect(screen.getByText(/本機 HTTP 開發環境提示|Local HTTP Environment Notice/i)).toBeDefined()
            expect(screen.getByText(/Cloudflare Tunnel/i)).toBeDefined()
        })
    })

    it('TDD-5: Renders guidance tabs for Gemini and Perplexity', async () => {
        render(<MCPConnectorDialog open={true} onOpenChange={vi.fn()} />)

        await waitFor(() => {
            expect(screen.getByRole('tab', { name: /Gemini/i })).toBeDefined()
        })

        // Gemini tab trigger is present
        const geminiTab = screen.getByRole('tab', { name: /Gemini/i })
        expect(geminiTab).toBeDefined()

        // Perplexity tab trigger is present
        const perplexityTab = screen.getByRole('tab', { name: /Perplexity/i })
        expect(perplexityTab).toBeDefined()

        // Trigger switch
        fireEvent.pointerDown(perplexityTab, { button: 0 })
        fireEvent.click(perplexityTab)
        fireEvent.keyDown(perplexityTab, { key: 'Enter', code: 'Enter' })

        // Check tabs exist
        expect(geminiTab.getAttribute('data-slot')).toBe('tabs-trigger')
        expect(perplexityTab.getAttribute('data-slot')).toBe('tabs-trigger')
    })

    it('TDD-6: Clipboard failure triggers execCommand fallback and text selection', async () => {
        // Mock clipboard.writeText rejection
        Object.assign(navigator, {
            clipboard: {
                writeText: vi.fn().mockRejectedValue(new Error('Permission denied'))
            }
        })
        const execCommandMock = vi.fn().mockReturnValue(false)
        document.execCommand = execCommandMock

        render(<MCPConnectorDialog open={true} onOpenChange={vi.fn()} />)

        await waitFor(() => {
            const tokenInput = document.querySelector('input[type="password"]') as HTMLInputElement | null
            expect(tokenInput?.value).toBe(mockJwt)
        })

        const copyTokenBtn = screen.getByText(/複製金鑰|Copy Token/i)
        fireEvent.click(copyTokenBtn)

        await waitFor(() => {
            expect(execCommandMock).toHaveBeenCalledWith('copy')
            // Token should be revealed on manual selection fallback
            const revealedInput = document.querySelector('input[value="' + mockJwt + '"]') as HTMLInputElement | null
            expect(revealedInput?.type).toBe('text')
            expect(toast.error).toHaveBeenCalled()
        })
    })

    it('TDD-7: Token refresh button calls getValidSessionToken and updates token', async () => {
        const refreshedJwt = "refreshed.jwt.token"
        const spy = vi.spyOn(authSession, 'getValidSessionToken')
            .mockResolvedValueOnce(mockJwt)
            .mockResolvedValueOnce(refreshedJwt)

        render(<MCPConnectorDialog open={true} onOpenChange={vi.fn()} />)

        await waitFor(() => {
            const input = document.querySelector('input[value="' + mockJwt + '"]')
            expect(input).not.toBeNull()
        })

        const refreshBtn = screen.getByLabelText(/重新整理憑證|Refresh Token/i)
        fireEvent.click(refreshBtn)

        await waitFor(() => {
            expect(spy).toHaveBeenCalledTimes(2)
            const refreshedInput = document.querySelector('input[value="' + refreshedJwt + '"]')
            expect(refreshedInput).not.toBeNull()
        })
    })

    it('TDD-8: Client ID is rendered from localStorage user_uuid and supports one-click copy', async () => {
        const mockUserId = "test-user-uuid-12345"
        localStorage.setItem("user_uuid", mockUserId)

        const writeTextMock = vi.fn().mockResolvedValue(undefined)
        Object.assign(navigator, {
            clipboard: {
                writeText: writeTextMock
            }
        })

        render(<MCPConnectorDialog open={true} onOpenChange={vi.fn()} />)

        await waitFor(() => {
            const clientIdInput = document.querySelector(`input[value="${mockUserId}"]`) as HTMLInputElement | null
            expect(clientIdInput).not.toBeNull()
            expect(screen.getByText(/複製 ID|Copy Client ID|Copy ID/i)).toBeDefined()
        })

        const copyIdBtn = screen.getByText(/複製 ID|Copy Client ID|Copy ID/i)
        fireEvent.click(copyIdBtn)

        await waitFor(() => {
            expect(writeTextMock).toHaveBeenCalledWith(mockUserId)
            expect(toast.success).toHaveBeenCalled()
        })
    })

    it('TDD-9: Gemini guide renders Google account prerequisite notice and maps the 3 fields', async () => {
        render(<MCPConnectorDialog open={true} onOpenChange={vi.fn()} />)

        await waitFor(() => {
            // Check prerequisite notice
            expect(screen.getByText(/保留活動記錄|personal Google account|Keep Activity/i)).toBeDefined()
            // Check 3 fields guidance
            expect(screen.getByText(/第 1 欄|Field 1/i)).toBeDefined()
            expect(screen.getByText(/第 2 與 3 欄|Fields 2 & 3/i)).toBeDefined()
        })
    })

    it('TDD-10: Client ID falls back to JWT sub when localStorage user_uuid and store are empty', async () => {
        const { useTripStore } = await import('@/lib/stores/tripStore')
        useTripStore.setState({ userId: "" })
        localStorage.removeItem("user_uuid")

        render(<MCPConnectorDialog open={true} onOpenChange={vi.fn()} />)

        await waitFor(() => {
            const clientIdInput = document.querySelector('input[value="test-user"]') as HTMLInputElement | null
            expect(clientIdInput).not.toBeNull()
        })
    })
})
