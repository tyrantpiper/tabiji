import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { AIKeyDialog } from '@/components/ai/ai-key-dialog'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'

describe('AIKeyDialog & Dialog Overflow Defense Test Suite', () => {
    beforeEach(() => {
        vi.clearAllMocks()
        localStorage.clear()
    })

    it('TDD-1: DialogContent contains overflow-x-hidden and responsive padding p-4 sm:p-6', () => {
        const { getByTestId } = render(
            <Dialog open={true}>
                <DialogContent data-testid="dialog-content">
                    <DialogTitle>Test Title</DialogTitle>
                    <DialogDescription>Test Desc</DialogDescription>
                    <div>Test Content</div>
                </DialogContent>
            </Dialog>
        )
        const content = getByTestId('dialog-content')
        expect(content.className).toContain('overflow-x-hidden')
        expect(content.className).toContain('overflow-y-auto')
        expect(content.className).toContain('p-4')
        expect(content.className).toContain('sm:p-6')
    })

    it('TDD-2: AIKeyDialog DialogFooter uses responsive layout (flex-col on mobile, sm:flex-row on desktop)', () => {
        render(
            <AIKeyDialog open={true} onOpenChange={vi.fn()} />
        )
        const footer = document.body.querySelector('[data-slot="dialog-footer"]')
        expect(footer).not.toBeNull()
        // Must contain flex-col for mobile and sm:flex-row for desktop
        expect(footer?.className).toContain('flex-col')
        expect(footer?.className).toContain('sm:flex-row')
        // Must NOT force horizontal flex-row without media queries
        expect(footer?.className).not.toMatch(/^flex\s+flex-row\s+justify-between/)
    })

    it('TDD-3: AIKeyDialog Accordion items have min-w-0 flex-1 break-words on text containers', () => {
        render(
            <AIKeyDialog open={true} onOpenChange={vi.fn()} />
        )
        // Expand the accordion item
        const trigger = screen.getByText(/🤔/i)
        fireEvent.click(trigger)

        const stepItems = document.body.querySelectorAll('.flex.gap-3')
        expect(stepItems.length).toBeGreaterThan(0)
        stepItems.forEach((item) => {
            const textContainer = item.querySelector('.min-w-0.flex-1')
            expect(textContainer).not.toBeNull()
        })
    })

    it('TDD-4: Input field triggers handleSaveApiKey on Enter key press', () => {
        const onOpenChange = vi.fn()
        render(<AIKeyDialog open={true} onOpenChange={onOpenChange} />)
        const input = screen.getByPlaceholderText(/AIzaSy/i)
        
        fireEvent.change(input, { target: { value: 'AIzaSyTestKey123456789' } })
        fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' })

        // Check that key was encrypted and stored
        expect(localStorage.getItem('user_gemini_key')).not.toBeNull()
        expect(onOpenChange).toHaveBeenCalledWith(false)
    })
})
