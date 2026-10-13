/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi } from 'vitest'
import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { ItineraryHeader } from '@/components/itinerary/ItineraryHeader'
import { TripSettingsView } from '@/components/itinerary/TripSettingsView'
import { Trip, Activity } from '@/lib/itinerary-types'

// Mock TripSwitcher
vi.mock('@/components/trip-switcher', () => ({
    TripSwitcher: () => <div data-testid="trip-switcher">TripSwitcher</div>
}))

// Mock haptic
vi.mock('@/lib/hooks', () => ({
    useHaptic: () => ({
        tap: vi.fn(),
        selection: vi.fn(),
        success: vi.fn(),
        error: vi.fn()
    })
}))

// Mock language
vi.mock('@/lib/LanguageContext', () => ({
    useLanguage: () => ({
        lang: 'zh',
        t: (k: string) => {
            const map: Record<string, string> = {
                'ov_total_days': '天',
                'iv_delete_this_day': '刪除這一天',
                'cal_title': '調整旅行日期'
            }
            return map[k] || k
        }
    })
}))

// Mock next/image
vi.mock('next/image', () => ({
    default: ({ alt = '', ...props }: React.ComponentProps<'img'>) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img alt={alt} {...props} />
    )
}))

// Mock framer-motion
vi.mock('framer-motion', () => ({
    motion: {
        div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>
    },
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>
}))

describe('Calendar Date Shift & Day Lifecycle Architecture (Issue 1, 2, 3)', () => {
    const act1: Activity = { id: 'a1', time_slot: '10:00', place: '淺草寺' }
    const act2: Activity = { id: 'a2', time_slot: '14:00', place: '晴空塔' }
    const act3: Activity = { id: 'a3', time_slot: '18:00', place: '澀谷' }

    const mockTrip: Trip = {
        id: 'trip-alpha',
        title: '東京浪漫五日遊',
        start_date: '2026-10-10',
        end_date: '2026-10-14',
        created_by: 'user-ryan',
        days: [
            { day: 1, activities: [act1] },
            { day: 2, activities: [act2] },
            { day: 3, activities: [act3] },
            { day: 4, activities: [] },
            { day: 5, activities: [] },
        ]
    }

    it('TC-1 (Issue 3): ItineraryHeader NO LONGER renders the hanging "刪除這一天" button under active day', () => {
        const onDeleteDay = vi.fn()
        const setDay = vi.fn()
        const getDateInfo = (d: number) => ({ date: `10/${9 + d}`, week: 'MON' })

        render(
            <ItineraryHeader
                currentTrip={mockTrip}
                dayNumbers={[1, 2, 3, 4, 5]}
                day={1}
                setDay={setDay}
                onBack={vi.fn()}
                onDeleteDay={onDeleteDay}
                userId="user-ryan"
                onRefresh={vi.fn()}
                shouldShowDateSkeleton={false}
                getDateInfo={getDateInfo}
            />
        )

        // Verify day buttons are rendered
        expect(screen.getByText('10/10')).toBeDefined()

        // 🛡️ CRITICAL ASSERTION: The hanging "刪除這一天" button MUST NOT exist in ItineraryHeader!
        expect(screen.queryByText('刪除這一天')).toBeNull()
    })

    it('TC-2 (Issue 3): TripSettingsView renders "天數結構管理" with safe day deletion', async () => {
        const onDeleteDay = vi.fn()
        const onUpdate = vi.fn()

        render(
            <TripSettingsView
                currentTrip={mockTrip}
                userId="user-ryan"
                totalDays={5}
                onBack={vi.fn()}
                onTripUpdated={onUpdate}
                onDeleteDay={onDeleteDay}
            />
        )

        // Verify Day Structure section is present
        expect(screen.getByText('天數結構管理')).toBeDefined()
        expect(screen.getByText('第 1 天 ·')).toBeDefined()
        expect(screen.getByText('第 2 天 ·')).toBeDefined()
        expect(screen.getByText('第 5 天 ·')).toBeDefined()

        // Click delete day 5
        const deleteButtons = screen.getAllByTitle(/刪除第 \d+ 天/)
        expect(deleteButtons.length).toBe(5)

        // Trigger delete on Day 5
        fireEvent.click(deleteButtons[4])

        // Verify safe confirmation dialog opens
        expect(screen.getByText('確定要刪除第 5 天？')).toBeDefined()

        // Confirm delete
        const confirmBtn = screen.getByText('確認刪除')
        fireEvent.click(confirmBtn)

        expect(onDeleteDay).toHaveBeenCalledWith(5)
    })

    it('TC-3 (Issue 3 Edge Case): TripSettingsView disables day deletion when totalDays <= 1', () => {
        const singleDayTrip: Trip = {
            id: 'trip-single',
            title: '一日遊',
            start_date: '2026-10-10',
            end_date: '2026-10-10',
            days: [{ day: 1, activities: [] }]
        }

        render(
            <TripSettingsView
                currentTrip={singleDayTrip}
                userId="user-ryan"
                totalDays={1}
                onBack={vi.fn()}
                onDeleteDay={vi.fn()}
            />
        )

        const deleteBtn = screen.getByTitle('單日行程無法刪除')
        expect((deleteBtn as HTMLButtonElement).disabled).toBe(true)
    })
})
