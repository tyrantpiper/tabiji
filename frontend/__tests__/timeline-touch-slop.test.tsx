import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import React, { useRef, useState } from 'react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'

/**
 * 📱 沙盒驗證：Touch-Slop 手勢消歧義演算法 PoC
 * 驗證在滑動與點擊下的狀態隔離
 */
function TestTouchSlopDropdown() {
    const isTouchInteraction = useRef(false)
    const startCoords = useRef<{ x: number; y: number } | null>(null)
    const isScrolling = useRef(false)
    const [open, setOpen] = useState(false)

    const onPointerDown = (e: React.PointerEvent) => {
        e.stopPropagation()
        if (e.pointerType === 'touch') {
            isTouchInteraction.current = true
            isScrolling.current = false
            startCoords.current = { x: e.clientX, y: e.clientY }
            // 阻止 Radix 在 touch pointerdown 的第 0 毫秒立即開啟選單
            e.preventDefault()
        } else {
            isTouchInteraction.current = false
        }
    }

    const onPointerMove = (e: React.PointerEvent) => {
        if (!isTouchInteraction.current || !startCoords.current) return
        const deltaX = Math.abs(e.clientX - startCoords.current.x)
        const deltaY = Math.abs(e.clientY - startCoords.current.y)
        if (deltaX > 8 || deltaY > 8) {
            isScrolling.current = true
        }
    }

    const onPointerUp = () => {
        if (!isTouchInteraction.current) return
        startCoords.current = null
    }

    const onClick = (e: React.MouseEvent) => {
        e.stopPropagation()
        if (isTouchInteraction.current) {
            if (isScrolling.current) {
                e.preventDefault()
                isScrolling.current = false
                isTouchInteraction.current = false
                return
            }
            // 觸控設備且非滾動（精準 Tap）：手動切換開關
            setOpen((prev) => !prev)
            isTouchInteraction.current = false
            return
        }
        // 桌面端滑鼠/鍵盤：完全不干涉，交由 Radix 原生邏輯處理
    }

    return (
        <DropdownMenu.Root open={open} onOpenChange={setOpen}>
            <DropdownMenu.Trigger asChild>
                <button
                    data-testid="test-trigger-btn"
                    onPointerDown={onPointerDown}
                    onPointerMove={onPointerMove}
                    onPointerUp={onPointerUp}
                    onClick={onClick}
                >
                    Trigger
                </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Content data-testid="test-menu-content">
                <DropdownMenu.Item onSelect={() => {}}>Edit</DropdownMenu.Item>
            </DropdownMenu.Content>
        </DropdownMenu.Root>
    )
}

describe('Touch-Slop Gesture Disambiguation Sandbox Verification', () => {
    it('TC-1 (滑動情境): 手指垂直位移超過 8px 時，選單 100% 保持關閉', () => {
        render(<TestTouchSlopDropdown />)
        const trigger = screen.getByTestId('test-trigger-btn')

        // 1. 手指按下 (y = 100)
        fireEvent.pointerDown(trigger, { pointerType: 'touch', clientX: 50, clientY: 100 })

        // 2. 手指滑動位移 (y = 125, delta = 25px > 8px)
        fireEvent.pointerMove(trigger, { pointerType: 'touch', clientX: 50, clientY: 125 })

        // 3. 手指抬起與點擊釋放
        fireEvent.pointerUp(trigger, { pointerType: 'touch', clientX: 50, clientY: 125 })
        fireEvent.click(trigger)

        // 4. 驗證選單內容未出現
        expect(screen.queryByTestId('test-menu-content')).toBeNull()
    })

    it('TC-2 (輕點情境): 手指微動小於 8px (Tap) 時，選單正常展開', () => {
        render(<TestTouchSlopDropdown />)
        const trigger = screen.getByTestId('test-trigger-btn')

        // 1. 手指按下 (y = 100)
        fireEvent.pointerDown(trigger, { pointerType: 'touch', clientX: 50, clientY: 100 })

        // 2. 手指微動 (y = 102, delta = 2px < 8px)
        fireEvent.pointerMove(trigger, { pointerType: 'touch', clientX: 50, clientY: 102 })

        // 3. 手指抬起與點擊釋放
        fireEvent.pointerUp(trigger, { pointerType: 'touch', clientX: 50, clientY: 102 })
        fireEvent.click(trigger)

        // 4. 驗證選單順利展開
        expect(screen.getByTestId('test-menu-content')).toBeInTheDocument()
    })

    it('TC-3 (桌面情境): 滑鼠左鍵點擊時，選單正常展開', () => {
        render(<TestTouchSlopDropdown />)
        const trigger = screen.getByTestId('test-trigger-btn')

        fireEvent.pointerDown(trigger, { pointerType: 'mouse', button: 0 })
        fireEvent.click(trigger, { button: 0 })

        expect(screen.getByTestId('test-menu-content')).toBeInTheDocument()
    })

    it('TC-4 (防止點擊穿透外層卡片): 滑動三點按鈕時，外層卡片 onClick 100% 不會被觸發', () => {
        const cardClickSpy = vi.fn()
        render(
            <div data-testid="test-card-container" onClick={cardClickSpy}>
                <TestTouchSlopDropdown />
            </div>
        )
        const trigger = screen.getByTestId('test-trigger-btn')

        // 手指滑動位移 20px
        fireEvent.pointerDown(trigger, { pointerType: 'touch', clientX: 50, clientY: 100 })
        fireEvent.pointerMove(trigger, { pointerType: 'touch', clientX: 50, clientY: 120 })
        fireEvent.pointerUp(trigger, { pointerType: 'touch', clientX: 50, clientY: 120 })
        fireEvent.click(trigger)

        // 驗證選單未開，且外層卡片點擊事件未觸發！
        expect(screen.queryByTestId('test-menu-content')).toBeNull()
        expect(cardClickSpy).not.toHaveBeenCalled()
    })

    it('TC-5 (橫向滑動情境): 手指水平位移超過 8px 時，同樣判定為滑動並阻斷選單', () => {
        render(<TestTouchSlopDropdown />)
        const trigger = screen.getByTestId('test-trigger-btn')

        fireEvent.pointerDown(trigger, { pointerType: 'touch', clientX: 50, clientY: 100 })
        fireEvent.pointerMove(trigger, { pointerType: 'touch', clientX: 70, clientY: 100 }) // X 位移 20px
        fireEvent.pointerUp(trigger, { pointerType: 'touch', clientX: 70, clientY: 100 })
        fireEvent.click(trigger)

        expect(screen.queryByTestId('test-menu-content')).toBeNull()
    })
})
