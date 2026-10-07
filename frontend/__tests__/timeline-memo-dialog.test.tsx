import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import React from 'react'
import { Activity } from '@/lib/itinerary-types'

// Mock language hook
vi.mock('@/lib/LanguageContext', () => ({
    useLanguage: () => ({
        t: (k: string) => k,
        lang: 'zh'
    })
}))

// Mock sonner
vi.mock('sonner', () => ({
    toast: {
        success: vi.fn(),
        error: vi.fn(),
        info: vi.fn()
    }
}))

// Mock mapillary search and cloudinary upload
vi.mock('@/lib/mapillary', () => ({
    searchNearbyImage: vi.fn().mockResolvedValue(null),
    uploadMapillaryToCloudinary: vi.fn().mockResolvedValue(null)
}))

// Import TimelineCard directly to test DetailDialog invocation and content
import { TimelineCard } from '@/components/timeline-card'

describe('DetailDialog iOS Sheet & Truncation Elimination', () => {
    const mockActivity: Activity = {
        id: 'act-test-1',
        day_number: 1,
        time_slot: '10:00',
        time: '10:00',
        place: 'Tokyo Tower Observation Deck',
        desc: 'Panoramic city view with glass floor',
        category: 'sightseeing',
        lat: 35.6586,
        lng: 139.7454,
        memo: 'Remember to book top deck tour',
        reservation_code: 'TOK-9988',
        cost: 3000,
        sub_items: [
            { name: 'Official Guide', desc: 'English audio', link: 'https://example.com/guide' }
        ]
    }

    it('TC-1: 點開此地備忘錄，不再渲染底部冗餘之 Close 與 Google Maps 按鈕', () => {
        const onUpdate = vi.fn().mockResolvedValue(true)
        render(
            <TimelineCard
                activity={mockActivity}
                index={0}
                onEdit={vi.fn()}
                onDelete={vi.fn()}
                onUpdateActivity={onUpdate}
            />
        )

        // Find and click the local memo button
        const memoBtn = screen.getByText('tc_local_memo')
        fireEvent.click(memoBtn)

        // Dialog should be open
        const dialog = screen.getByRole('dialog')
        expect(dialog).toBeInTheDocument()
        expect(within(dialog).getByText('Tokyo Tower Observation Deck')).toBeInTheDocument()

        // 🛡️ Critical check: Redundant English Google Maps bottom button must NOT exist
        expect(within(dialog).queryByRole('button', { name: /Google Maps/i })).toBeNull()
        expect(within(dialog).queryByText('Google Maps')).toBeNull()

        // 🛡️ Verify iOS grabber pill handle exists on mobile layout
        const grabber = dialog.querySelector('.bg-slate-300')
        expect(grabber).toBeInTheDocument()
    })

    it('TC-2: 四層資訊拓撲 (Info, Reservation & Cost, Memo, Street View) 完整渲染', () => {
        const onUpdate = vi.fn().mockResolvedValue(true)
        render(
            <TimelineCard
                activity={mockActivity}
                index={0}
                onEdit={vi.fn()}
                onDelete={vi.fn()}
                onUpdateActivity={onUpdate}
            />
        )

        // Open dialog
        fireEvent.click(screen.getByText('tc_local_memo'))
        const dialog = screen.getByRole('dialog')

        // Layer 1: Info & Guide
        expect(within(dialog).getByText('Panoramic city view with glass floor')).toBeInTheDocument()

        // Layer 2: Reservation & Cost
        expect(within(dialog).getByText('TOK-9988')).toBeInTheDocument()
        expect(within(dialog).getByText('¥3,000')).toBeInTheDocument()

        // Layer 3: Memo & Links
        expect(within(dialog).getByText('Remember to book top deck tour')).toBeInTheDocument()
        expect(within(dialog).getByText('Official Guide')).toBeInTheDocument()

        // Layer 4: Street View & Coordinates
        expect(within(dialog).getByText(/35\.65860, 139\.74540/)).toBeInTheDocument()
    })

    it('TC-3: 點擊備忘錄彈窗內部文字與空白處時，事件被三層物理阻斷，絕不觸發背景卡片地圖跳轉', () => {
        const onUpdate = vi.fn().mockResolvedValue(true)
        const focusMapSpy = vi.fn()
        window.addEventListener('tabidachi-focus-map-activity', focusMapSpy)

        render(
            <TimelineCard
                activity={mockActivity}
                index={0}
                onEdit={vi.fn()}
                onDelete={vi.fn()}
                onUpdateActivity={onUpdate}
            />
        )

        // 1. 開啟此地備忘錄
        fireEvent.click(screen.getByText('tc_local_memo'))
        const dialog = screen.getByRole('dialog')
        expect(dialog).toBeInTheDocument()

        // 2. 點擊彈窗內部標題文字
        const titleEl = within(dialog).getByText('Tokyo Tower Observation Deck')
        fireEvent.click(titleEl)

        // 3. 點擊彈窗內部攻略內文
        const descEl = within(dialog).getByText('Panoramic city view with glass floor')
        fireEvent.click(descEl)

        // 4. 點擊彈窗主容器本身
        fireEvent.click(dialog)

        // 5. 驗證地圖聚焦事件在彈窗內被完全阻斷，未被觸發
        expect(focusMapSpy).not.toHaveBeenCalled()

        // 6. 零降級驗證：直接點擊卡片本體外部區域時，卡片依然能正常觸發地圖跳轉 CustomEvent
        const cardContainer = document.querySelector('.timeline-card')
        expect(cardContainer).not.toBeNull()
        if (cardContainer) {
            fireEvent.click(cardContainer)
            expect(focusMapSpy).toHaveBeenCalledTimes(1)
            expect(focusMapSpy).toHaveBeenCalledWith(
                expect.objectContaining({
                    detail: expect.objectContaining({
                        id: 'act-test-1',
                        lat: 35.6586,
                        lng: 139.7454,
                        place: 'Tokyo Tower Observation Deck'
                    })
                })
            )
        }

        window.removeEventListener('tabidachi-focus-map-activity', focusMapSpy)
    })

    it('TC-4: 手機端按壓三點按鈕垂直滑動 (>8px) 時，選單 100% 不開且地圖事件不被觸發', () => {
        const onUpdate = vi.fn().mockResolvedValue(true)
        const onEdit = vi.fn()
        const onDelete = vi.fn()
        const focusMapSpy = vi.fn()
        window.addEventListener('tabidachi-focus-map-activity', focusMapSpy)

        render(
            <TimelineCard
                activity={mockActivity}
                index={0}
                onEdit={onEdit}
                onDelete={onDelete}
                onUpdateActivity={onUpdate}
            />
        )

        // 找到三點按鈕 (具有 MoreHorizontal 圖示的 button)
        const moreButtons = screen.getAllByRole('button')
        const moreBtn = moreButtons.find(b => b.querySelector('svg.lucide-ellipsis')) || moreButtons[0]
        expect(moreBtn).toBeInTheDocument()

        // 1. 手指按下 (y = 100)
        fireEvent.pointerDown(moreBtn, { pointerType: 'touch', clientX: 50, clientY: 100 })

        // 2. 手指滑動 30px (> 8px 閾值)
        fireEvent.pointerMove(moreBtn, { pointerType: 'touch', clientX: 50, clientY: 130 })

        // 3. 手指抬起與釋放
        fireEvent.pointerUp(moreBtn, { pointerType: 'touch', clientX: 50, clientY: 130 })
        fireEvent.click(moreBtn)

        // 4. 驗證選單項目完全未彈出
        expect(screen.queryByText('tc_edit_all')).toBeNull()
        expect(screen.queryByText('delete')).toBeNull()

        // 5. 驗證無條件切斷冒泡有效：背後地圖跳轉 CustomEvent 完全未被觸發
        expect(focusMapSpy).not.toHaveBeenCalled()

        window.removeEventListener('tabidachi-focus-map-activity', focusMapSpy)
    })

    it('TC-5: 手機端精準輕點 (Tap, 位移 <8px) 三點按鈕時，選單順利展開', () => {
        const onUpdate = vi.fn().mockResolvedValue(true)
        const onEdit = vi.fn()
        const onDelete = vi.fn()

        render(
            <TimelineCard
                activity={mockActivity}
                index={0}
                onEdit={onEdit}
                onDelete={onDelete}
                onUpdateActivity={onUpdate}
            />
        )

        const moreButtons = screen.getAllByRole('button')
        const moreBtn = moreButtons.find(b => b.querySelector('svg.lucide-ellipsis')) || moreButtons[0]

        // 1. 手指按下 (y = 100)
        fireEvent.pointerDown(moreBtn, { pointerType: 'touch', clientX: 50, clientY: 100 })

        // 2. 手指微動 (y = 102, delta = 2px < 8px)
        fireEvent.pointerMove(moreBtn, { pointerType: 'touch', clientX: 50, clientY: 102 })

        // 3. 手指抬起與點擊釋放
        fireEvent.pointerUp(moreBtn, { pointerType: 'touch', clientX: 50, clientY: 102 })
        fireEvent.click(moreBtn)

        // 4. 驗證選單順利展開
        expect(screen.getByText('tc_edit_all')).toBeInTheDocument()
        expect(screen.getByText('delete')).toBeInTheDocument()
    })
})
