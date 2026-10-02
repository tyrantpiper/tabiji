import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import SourceCitation, { GroundingSource } from "@/components/chat/SourceCitation"

describe("SourceCitation Component", () => {
    it("renders nothing when sources array is empty or null", () => {
        const { container } = render(<SourceCitation sources={[]} />)
        expect(container.firstChild).toBeNull()
    })

    it("renders source items with citation index, badges, and truncated text", () => {
        const mockSources: GroundingSource[] = [
            {
                title: "台北旅遊官方網站",
                uri: "https://travel.taipei/zh-tw",
                citation_index: 1,
                category: "official",
                badge: { text: "🏛️ 官方觀光局", color: "text-emerald-500 bg-emerald-500/10 border-emerald-500/20" },
                snippet: "台北觀光指南"
            },
            {
                title: "PTT 台北美食熱議討論串",
                uri: "https://www.ptt.cc/bbs/Food/M.12345.html",
                citation_index: 2,
                category: "local_forum",
                badge: { text: "🇹🇼 PTT 在地情報", color: "text-blue-500 bg-blue-500/10 border-blue-500/20" }
            }
        ]

        render(<SourceCitation sources={mockSources} />)

        // Verify citation numbers
        expect(screen.getByText("[1]")).toBeDefined()
        expect(screen.getByText("[2]")).toBeDefined()

        // Verify badge labels
        expect(screen.getByText("🏛️ 官方觀光局")).toBeDefined()
        expect(screen.getByText("🇹🇼 PTT 在地情報")).toBeDefined()

        // Verify link attributes
        const links = screen.getAllByRole("link")
        expect(links).toHaveLength(2)
        expect(links[0].getAttribute("href")).toBe("https://travel.taipei/zh-tw")
        expect(links[0].getAttribute("target")).toBe("_blank")
        expect(links[0].getAttribute("rel")).toBe("noopener noreferrer")

        // Verify max-w-27.5 class is applied for truncation
        const titleSpan = screen.getByText("台北旅遊官方網站")
        expect(titleSpan.className).toContain("max-w-27.5")
        expect(titleSpan.className).toContain("truncate")
    })

    it("falls back to hostname when title is empty", () => {
        const mockSources: GroundingSource[] = [
            {
                title: "",
                uri: "https://www.reddit.com/r/travel/comments/abc",
                citation_index: 3
            }
        ]

        render(<SourceCitation sources={mockSources} />)
        expect(screen.getByText("reddit.com")).toBeDefined()
    })
})
