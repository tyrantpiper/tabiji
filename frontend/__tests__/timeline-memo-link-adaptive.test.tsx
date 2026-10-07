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

// Mock openExternalLink in lib/utils
const mockOpenExternalLink = vi.fn()
vi.mock('@/lib/utils', async () => {
    const actual = await vi.importActual<Record<string, unknown>>('@/lib/utils')
    return {
        ...actual,
        openExternalLink: (...args: unknown[]) => mockOpenExternalLink(...args)
    }
})

import { TimelineCard } from '@/components/timeline-card'

describe('🛡️ Security Sentinel & Adaptive Layout: Memo Link Long Content Defense', () => {
    const longTextActivity: Activity = {
        id: 'act-long-1',
        day_number: 1,
        time_slot: '11:00',
        time: '11:00',
        place: '元町公園散策',
        desc: '橫濱山手西洋館巡禮與綠蔭散策',
        category: 'sightseeing',
        lat: 35.43813,
        lng: 139.65137,
        memo: '坐落於橫濱山手地區的山坡上，曾是外國人居留地...',
        sub_items: [
            {
                name: 'Uchiki Pan (Uchiki Bakery)',
                desc: 'Tabelog 擁有 3.72高分 \\(^^*)/ England (英格蘭山型吐司) 咖哩麵包 (Curry Pan) 肉桂吐司 超長註解連續無空格字元WWWWWWWWWWWWWWWWWWWWWWWWWWWWWWWW',
                link: 'https://tabelog.com/kanagawa/A1401/A140105/14000109/'
            },
            {
                name: 'O to U',
                desc: 'Tabelog 高達 3.62 分!! 十字紅豆麵包 (あんぱん / Anpan) 奶油麵包',
                link: 'https://tabelog.com/kanagawa/A1401/A140105/14075128/'
            },
            {
                name: '純文字景點資訊無連結',
                desc: '無外連純文字備註，左側應自適應佔滿寬度'
            }
        ]
    }

    it('TC-Adaptive-1: 點開此地備忘錄，子項目標題與長註解必須具備 break-words 自適應折行，禁止 whitespace-nowrap 橫向撐破', () => {
        render(
            <TimelineCard
                activity={longTextActivity}
                index={0}
                onEdit={vi.fn()}
                onDelete={vi.fn()}
                onUpdateActivity={vi.fn().mockResolvedValue(true)}
            />
        )

        // 打開此地備忘錄
        fireEvent.click(screen.getByText('tc_local_memo'))
        const dialog = screen.getByRole('dialog')
        expect(dialog).toBeInTheDocument()

        // 驗證標題與長註解具備 wrap-break-word 自適應折行 class，絕不能包含 whitespace-nowrap
        const descNode = within(dialog).getByText(/Tabelog 擁有 3.72高分/i)
        expect(descNode.className).toContain('wrap-break-word')
        expect(descNode.className).not.toContain('whitespace-nowrap')
    })

    it('TC-Adaptive-2: 外部連結按鈕必須具備 shrink-0 錨定，點擊時觸發 openExternalLink 且阻斷冒泡', () => {
        const cardClickSpy = vi.fn()
        render(
            <div onClick={cardClickSpy}>
                <TimelineCard
                    activity={longTextActivity}
                    index={0}
                    onEdit={vi.fn()}
                    onDelete={vi.fn()}
                    onUpdateActivity={vi.fn().mockResolvedValue(true)}
                />
            </div>
        )

        // 打開彈窗
        fireEvent.click(screen.getByText('tc_local_memo'))
        const dialog = screen.getByRole('dialog')

        // 尋找外部連結按鈕
        const linkButtons = within(dialog).getAllByTitle('開啟外部連結')
        expect(linkButtons.length).toBe(2) // 前兩項有 link，第三項無 link

        // 驗證按鈕具有 shrink-0
        expect(linkButtons[0].className).toContain('shrink-0')

        // 點擊第一個連結按鈕
        fireEvent.click(linkButtons[0])

        // 驗證呼叫 openExternalLink 且切斷冒泡
        expect(mockOpenExternalLink).toHaveBeenCalledWith('https://tabelog.com/kanagawa/A1401/A140105/14000109/')
        expect(cardClickSpy).not.toHaveBeenCalled()
    })

    it('TC-Adaptive-3: 無連結項目 (Null/Empty Link) 不得渲染空按鈕，文字自適應展示', () => {
        render(
            <TimelineCard
                activity={longTextActivity}
                index={0}
                onEdit={vi.fn()}
                onDelete={vi.fn()}
                onUpdateActivity={vi.fn().mockResolvedValue(true)}
            />
        )

        // 打開彈窗
        fireEvent.click(screen.getByText('tc_local_memo'))
        const dialog = screen.getByRole('dialog')

        // 驗證第三個項目純文字在彈窗內渲染正常
        expect(within(dialog).getByText('純文字景點資訊無連結')).toBeInTheDocument()
        expect(within(dialog).getByText('無外連純文字備註，左側應自適應佔滿寬度')).toBeInTheDocument()
    })
})
