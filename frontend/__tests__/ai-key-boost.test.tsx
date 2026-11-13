import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { AIKeyDialog } from '@/components/ai/ai-key-dialog'
import { ApiKeySettings } from '@/components/ApiKeySettings'
import { decryptData, encryptData, getSecureApiKey } from '@/lib/security'

describe('API Key Dialogs /boost Remediation Suite (Dev Sentinel Guard & AQ. Format)', () => {
    const originalEnvKey = process.env.NEXT_PUBLIC_DEV_GEMINI_KEY

    beforeEach(() => {
        vi.clearAllMocks()
        localStorage.clear()
        delete process.env.NEXT_PUBLIC_DEV_GEMINI_KEY
    })

    afterEach(() => {
        if (originalEnvKey !== undefined) {
            process.env.NEXT_PUBLIC_DEV_GEMINI_KEY = originalEnvKey
        } else {
            delete process.env.NEXT_PUBLIC_DEV_GEMINI_KEY
        }
        localStorage.clear()
    })

    it('AIKeyDialog does NOT encrypt or persist "(開發者模式)" / "(Dev Mode)" sentinel into localStorage', () => {
        process.env.NEXT_PUBLIC_DEV_GEMINI_KEY = 'AQ.Ab8RN6DevBackdoorKeyExample1234567890123456789'
        const onOpenChange = vi.fn()
        render(<AIKeyDialog open={true} onOpenChange={onOpenChange} />)

        const input = document.getElementById('apiKeyInput') as HTMLInputElement
        expect(input).not.toBeNull()
        expect(input.value).toBe('')
        expect(input.placeholder).toMatch(/\(開發者模式\)|\(Dev Mode\)/)

        const saveBtn = screen.getByRole('button', { name: /儲存設定|Save/i })
        fireEvent.click(saveBtn)
        expect(localStorage.getItem('user_gemini_key')).toBeNull()

        // Even if someone manually enters a sentinel string, Save must reject persisting it
        fireEvent.change(input, { target: { value: '(開發者模式)' } })
        fireEvent.click(saveBtn)
        expect(localStorage.getItem('user_gemini_key')).toBeNull()

        fireEvent.change(input, { target: { value: '(Dev Mode)' } })
        fireEvent.click(saveBtn)
        expect(localStorage.getItem('user_gemini_key')).toBeNull()
    })

    it('AIKeyDialog self-heals previously poisoned Dev Mode sentinel stored in localStorage', () => {
        localStorage.setItem('user_gemini_key', encryptData('(Dev Mode)'))
        render(<AIKeyDialog open={true} onOpenChange={vi.fn()} />)

        expect(localStorage.getItem('user_gemini_key')).toBeNull()
        const input = document.getElementById('apiKeyInput') as HTMLInputElement
        expect(input.value).toBe('')
    })

    it('getSecureApiKey and dialogs self-heal zh-TW "(開發者模式)" sentinel before ASCII sanitize turns it into "()"', () => {
        // Reproduces exact CJK strip hazard: sanitize("(開發者模式)") === "()"
        localStorage.setItem('user_gemini_key', encryptData('(開發者模式)'))
        expect(getSecureApiKey()).toBe('')
        expect(localStorage.getItem('user_gemini_key')).toBeNull()

        localStorage.setItem('gemini_api_key', '(開發者模式)')
        expect(getSecureApiKey()).toBe('')
        expect(localStorage.getItem('gemini_api_key')).toBeNull()

        // Poisoned key falls back cleanly to dev key instead of leaking "()"
        process.env.NEXT_PUBLIC_DEV_GEMINI_KEY = 'AQ.Ab8RN6FallbackDevKey12345678901234567890123456'
        localStorage.setItem('user_gemini_key', encryptData('(開發者模式)'))
        render(<AIKeyDialog open={true} onOpenChange={vi.fn()} />)
        expect(localStorage.getItem('user_gemini_key')).toBeNull()
        expect(getSecureApiKey()).toBe('AQ.Ab8RN6FallbackDevKey12345678901234567890123456')
        const input = document.getElementById('apiKeyInput') as HTMLInputElement
        expect(input.value).toBe('')
    })

    it('AIKeyDialog persists AQ. Auth Keys cleanly and updates guidance for AQ. + AIza compatibility', () => {
        const aqKey = 'AQ.Ab8RN6UserValidKey12345678901234567890123456'
        const onOpenChange = vi.fn()
        render(<AIKeyDialog open={true} onOpenChange={onOpenChange} />)

        const input = screen.getByPlaceholderText(/AQ\./i) as HTMLInputElement
        expect(input.placeholder).toContain('AIza')

        // Open accordion instructions
        const trigger = screen.getByText(/🤔/i)
        fireEvent.click(trigger)
        expect(document.body.textContent).toContain('AQ.')
        expect(document.body.textContent).toContain('AIza...')

        fireEvent.change(input, { target: { value: aqKey } })
        fireEvent.click(screen.getByRole('button', { name: /儲存設定|Save/i }))

        const stored = localStorage.getItem('user_gemini_key')
        expect(stored).not.toBeNull()
        expect(decryptData(stored!)).toBe(aqKey)
        expect(getSecureApiKey()).toBe(aqKey)
        expect(onOpenChange).toHaveBeenCalledWith(false)
    })

    it('ApiKeySettings shows AQ. placeholder and guidance with legacy AIza compatibility and avoids sentinel leaks', () => {
        const onKeySaved = vi.fn()
        const { container } = render(<ApiKeySettings onKeySaved={onKeySaved} />)

        const triggerBtn = container.querySelector('button')
        expect(triggerBtn).not.toBeNull()
        fireEvent.click(triggerBtn!)

        const input = screen.getByPlaceholderText(/AQ\./i) as HTMLInputElement
        expect(input.placeholder).toContain('AIza')

        const accordionTrigger = screen.getByText(/API Key\?/i)
        fireEvent.click(accordionTrigger)
        expect(document.body.textContent).toContain('AQ.')
        expect(document.body.textContent).toContain('AIza...')

        const aqKey = 'AQ.Ab8RN6SettingsKey12345678901234567890123456'
        fireEvent.change(input, { target: { value: aqKey } })
        fireEvent.click(screen.getByRole('button', { name: /儲存設定|Save Settings/i }))

        expect(decryptData(localStorage.getItem('user_gemini_key')!)).toBe(aqKey)
        expect(onKeySaved).toHaveBeenLastCalledWith(aqKey)
    })

    it('ApiKeySettings Clear unlocks input in Dev Mode and cleans legacy key too', () => {
        process.env.NEXT_PUBLIC_DEV_GEMINI_KEY = 'AQ.Ab8RN6SettingsDevKey1234567890123456789012345'
        localStorage.setItem('gemini_api_key', 'AIzaSyLegacyOldKey1234567890123456789012345')
        const onKeySaved = vi.fn()
        const { container } = render(<ApiKeySettings onKeySaved={onKeySaved} />)

        fireEvent.click(container.querySelector('button')!)
        const input = document.getElementById('apiKey') as HTMLInputElement
        expect(input.disabled).toBe(false)

        // With no localStorage override, dev mode locks input
        localStorage.clear()
        const { container: c2 } = render(<ApiKeySettings onKeySaved={vi.fn()} />)
        fireEvent.click(c2.querySelectorAll('button')[0]!)
        const devInputs = document.querySelectorAll('#apiKey') as NodeListOf<HTMLInputElement>
        const devInput = devInputs[devInputs.length - 1]
        expect(devInput.disabled).toBe(true)

        // Clicking Clear must unlock input so user can type a custom key
        const clearBtns = screen.getAllByRole('button', { name: /清除|Clear/i })
        fireEvent.click(clearBtns[clearBtns.length - 1])
        expect(devInput.disabled).toBe(false)
        expect(devInput.value).toBe('')
        expect(localStorage.getItem('user_gemini_key')).toBeNull()
        expect(localStorage.getItem('gemini_api_key')).toBeNull()
    })
})
