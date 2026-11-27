import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen } from "@testing-library/react"

import { sanitizeGroundingSources, streamDeepResearch } from "@/lib/sse-parser"
import SourceCitation, { type GroundingSource } from "@/components/chat/SourceCitation"
import DeepResearchCard, { type DeepResearchData } from "@/components/chat/DeepResearchCard"

describe("Deep Research v2 News RSS Frontend Contracts (AC-7 & Security)", () => {
    beforeEach(() => {
        vi.restoreAllMocks()
    })

    it("sanitizeGroundingSources allows only http(s) URIs and rejects javascript:/data: XSS protocols", () => {
        const sanitized = sanitizeGroundingSources([
            {
                title: "北海道雪祭最新開幕資訊",
                uri: "https://news.google.com/rss/articles/CBMiSafe1",
                citation_index: 1,
                category: "news",
                badge: {
                    text: "📰 即時新聞",
                    color: "text-sky-600 dark:text-sky-400 bg-sky-500/10 border-sky-500/30 dark:border-sky-500/20",
                },
                snippet: "2026 開幕資訊",
            },
            { title: "XSS JS", uri: "javascript:alert(1)", citation_index: 2 },
            { title: "XSS Data", uri: "data:text/html,<script>alert(1)</script>", citation_index: 3 },
            { title: "XSS Upper", uri: "  JAVASCRIPT:void(0) ", citation_index: 4 },
            { title: "URL fallback field", url: "http://example.com/guide", citation_index: 5 },
            null,
            "invalid",
        ])

        expect(sanitized).toHaveLength(2)
        expect(sanitized[0].uri).toBe("https://news.google.com/rss/articles/CBMiSafe1")
        expect(sanitized[0].badge?.text).toBe("📰 即時新聞")
        expect(sanitized[1].uri).toBe("http://example.com/guide")
    })

    it("streamDeepResearch flushes trailing EOF buffer without \\n\\n and filters unsafe source URIs", async () => {
        const encoder = new TextEncoder()
        const donePayload = JSON.stringify({
            engine: "gemini-4-hydrogen",
            sources: [
                {
                    citation_index: 1,
                    title: "北海道冬季周遊電子票上市",
                    uri: "https://news.google.com/rss/articles/CBMi123",
                    category: "news",
                    badge: {
                        text: "📰 即時新聞",
                        color: "text-sky-600 dark:text-sky-400 bg-sky-500/10 border-sky-500/30 dark:border-sky-500/20",
                    },
                },
                {
                    citation_index: 2,
                    title: "Malicious Link",
                    uri: "javascript:alert(document.cookie)",
                },
            ],
        })
        const sseBody = new ReadableStream({
            start(controller) {
                controller.enqueue(encoder.encode('event: text\ndata: {"text":"報告內容 [1]"}\n\n'))
                // Intentionally omit trailing \n\n to verify EOF buffer flush!
                controller.enqueue(encoder.encode(`event: done\ndata: ${donePayload}`))
                controller.close()
            },
        })

        vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
            new Response(sseBody, { status: 200, headers: { "Content-Type": "text/event-stream" } })
        )

        const res = await streamDeepResearch({
            apiUrl: "https://api.example.test",
            apiKey: "AIzaSyTestKey1234567890123456789012345678",
            prompt: "北海道雪祭攻略",
            destination: "CTS",
        })

        expect(res.supported).toBe(true)
        expect(res.engine).toBe("gemini-4-hydrogen")
        expect(res.text).toBe("報告內容 [1]")
        expect(res.sources).toHaveLength(1)
        expect(res.sources?.[0].uri).toBe("https://news.google.com/rss/articles/CBMi123")
        expect(res.sources?.[0].badge?.text).toBe("📰 即時新聞")
    })

    it("streamDeepResearch omits `sources` key when event: done does not include sources", async () => {
        const encoder = new TextEncoder()
        const sseBody = new ReadableStream({
            start(controller) {
                controller.enqueue(encoder.encode('event: text\ndata: {"text":"Legacy output"}\n\n'))
                controller.enqueue(encoder.encode('event: done\ndata: {"engine":"gemini-3.8-flash"}\n\n'))
                controller.close()
            },
        })
        vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
            new Response(sseBody, { status: 200, headers: { "Content-Type": "text/event-stream" } })
        )

        const res = await streamDeepResearch({
            apiUrl: "https://api.example.test",
            apiKey: "AIzaSyTestKey1234567890123456789012345678",
            prompt: "Compare JR Pass",
        })

        expect(res).toEqual({ supported: true, text: "Legacy output", engine: "gemini-3.8-flash" })
        expect("sources" in res).toBe(false)
    })

    it("SourceCitation blocks non-http(s) URIs directly (defense-in-depth)", () => {
        const unsafeOnly: GroundingSource[] = [
            { title: "Evil", uri: "javascript:alert(1)", citation_index: 1 },
            { title: "Data", uri: "data:text/html,boom", citation_index: 2 },
        ]
        const { container } = render(<SourceCitation sources={unsafeOnly} />)
        expect(container.firstChild).toBeNull()
    })

    it("DeepResearchCard renders SourceCitation with live news badge when completed with sources, and omits it otherwise", () => {
        const completedWithSources: DeepResearchData = {
            id: "stream_1",
            status: "completed",
            prompt: "北海道雪祭攻略",
            outputText: "## 2026 北海道雪祭重點\n已開幕 [1]。",
            engine: "gemini-4-hydrogen",
            sources: [
                {
                    title: "北海道冬季周遊電子票上市",
                    uri: "https://news.google.com/rss/articles/CBMiNews1",
                    citation_index: 1,
                    category: "news",
                    badge: {
                        text: "📰 即時新聞",
                        color: "text-sky-600 dark:text-sky-400 bg-sky-500/10 border-sky-500/30 dark:border-sky-500/20",
                    },
                    snippet: "最新新聞線索",
                },
            ],
        }

        const { rerender } = render(<DeepResearchCard data={completedWithSources} />)
        expect(screen.getByText("📰 即時新聞")).toBeTruthy()
        expect(screen.getByText("北海道冬季周遊電子票上市")).toBeTruthy()
        const links = screen.getAllByRole("link")
        const newsLink = links.find((a) => a.getAttribute("href") === "https://news.google.com/rss/articles/CBMiNews1")
        expect(newsLink).toBeTruthy()
        expect(newsLink?.getAttribute("target")).toBe("_blank")
        expect(newsLink?.getAttribute("rel")).toBe("noopener noreferrer")

        // Completed without sources -> no Sources block
        rerender(
            <DeepResearchCard
                data={{
                    id: "stream_2",
                    status: "completed",
                    prompt: "純路線規劃",
                    outputText: "## 路線報告",
                    engine: "gemini-4-hydrogen",
                }}
            />
        )
        expect(screen.queryByText("📰 即時新聞")).toBeNull()
        expect(screen.queryByText(/來源：|Sources:/)).toBeNull()

        // Running state -> does not show citations prematurely
        rerender(
            <DeepResearchCard
                data={{
                    ...completedWithSources,
                    status: "running",
                }}
            />
        )
        expect(screen.queryByText("📰 即時新聞")).toBeNull()
    })
})
