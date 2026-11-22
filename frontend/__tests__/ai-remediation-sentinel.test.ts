import fs from 'fs'
import path from 'path'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { AiParseResponseSchema, AiGenerateResponseSchema } from '@/lib/schemas'
import { aiApi, API } from '@/lib/api'
import { streamChat } from '@/lib/sse-parser'

describe('AI Systemic Remediation Sentinel (Frontend)', () => {
    const originalFetch = global.fetch

    beforeEach(() => {
        vi.restoreAllMocks()
    })

    afterEach(() => {
        global.fetch = originalFetch
        vi.unstubAllGlobals()
    })

    it('preserves currency & destination in AiParseResponseSchema and AiGenerateResponseSchema', () => {
        const parsed = AiParseResponseSchema.safeParse({
            title: 'Hokkaido 5 Days',
            destination: 'Sapporo',
            currency: 'JPY',
            start_date: '2026-12-01',
            end_date: '2026-12-05',
            items: [{ day: 1, place_name: 'Odori Park' }],
            day_metadata: [{ day: 1, notes: [{ icon: '🍜', title: 'Ramen', content: 'Sapporo miso' }] }],
        })
        expect(parsed.success).toBe(true)
        if (parsed.success) {
            expect(parsed.data.currency).toBe('JPY')
            expect(parsed.data.destination).toBe('Sapporo')
            expect(parsed.data.day_metadata).toHaveLength(1)
        }

        const generated = AiGenerateResponseSchema.safeParse({
            status: 'success',
            data: {
                title: 'Osaka Food Tour',
                destination: 'Osaka',
                currency: 'JPY',
                items: [],
            },
        })
        expect(generated.success).toBe(true)
        if (generated.success) {
            expect(generated.data.data?.currency).toBe('JPY')
            expect(generated.data.data?.destination).toBe('Osaka')
        }
    })

    it('actuaryChat surfaces FastAPI data.detail instead of generic fallback error', async () => {
        global.fetch = vi.fn().mockResolvedValueOnce({
            ok: false,
            status: 401,
            json: async () => ({ detail: 'Gemini API Key 無效或已過期' }),
        }) as unknown as typeof fetch

        await expect(
            aiApi.actuaryChat([], ['Ryan'], 'Split the bill', [], 'zh')
        ).rejects.toThrow('Gemini API Key 無效或已過期')
    })

    it('aiApi.parseReceipt forwards X-Gemini-API-Key, Accept-Language, locale, and direct image / imageUrl payload while orphan Next proxy is deleted', async () => {
        // Verify unauthenticated orphan Next.js proxy route is removed
        const orphanRoutePath = path.resolve(__dirname, '../app/api/parse-receipt/route.ts')
        expect(fs.existsSync(orphanRoutePath)).toBe(false)

        const storageMap: Record<string, string> = {
            user_gemini_key: 'AIzaSyProxyHeaderForwardTest12345',
        }
        vi.stubGlobal('localStorage', {
            getItem: vi.fn((k: string) => storageMap[k] ?? null),
            setItem: vi.fn((k: string, v: string) => { storageMap[k] = v }),
            removeItem: vi.fn((k: string) => { delete storageMap[k] }),
            clear: vi.fn(() => { Object.keys(storageMap).forEach(k => delete storageMap[k]) }),
        })

        const mockUpstreamFetch = vi.fn().mockResolvedValueOnce({
            ok: true,
            status: 200,
            json: async () => ({ title: '7-11', currency: 'JPY', expense_date: '2026-11-11', total_amount: 550 }),
        })
        global.fetch = mockUpstreamFetch as unknown as typeof fetch

        const receiptUrl = 'https://res.cloudinary.com/dnpcnwrcu/image/upload/v1/ryan_travel/receipts/r1.webp'
        const directDataUrl = 'data:image/webp;base64,UklGRh4AAABXRUJQVlA4TBEAAAAvAAAAAAfQ//73v/+BiOh/AAA='
        const res = await aiApi.parseReceipt(receiptUrl, directDataUrl, 'en')

        expect(res.title).toBe('7-11')
        expect(mockUpstreamFetch).toHaveBeenCalledTimes(1)
        const [fetchUrl, fetchInit] = mockUpstreamFetch.mock.calls[0]
        expect(fetchUrl).toBe(API.RECEIPT_PARSE)
        expect(fetchInit.headers['X-Gemini-API-Key']).toBe('AIzaSyProxyHeaderForwardTest12345')
        expect(fetchInit.headers['Accept-Language']).toBe('en-US')
        expect(JSON.parse(fetchInit.body)).toEqual({
            imageUrl: receiptUrl,
            image: directDataUrl,
            locale: 'en',
        })
    })

    it('401 from Gemini API Key does NOT wipe tabiji_session_token in apiFetch', async () => {
        const expFuture = Math.floor(Date.now() / 1000) + 3600
        const payloadB64 = Buffer.from(JSON.stringify({ sub: 'user-1', exp: expFuture })).toString('base64url')
        const validJwt = `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.${payloadB64}.sig`

        const storageMap: Record<string, string> = {
            tabiji_session_token: validJwt,
            gemini_api_key: 'bad-gemini-key',
        }
        vi.stubGlobal('localStorage', {
            getItem: vi.fn((k: string) => storageMap[k] ?? null),
            setItem: vi.fn((k: string, v: string) => { storageMap[k] = v }),
            removeItem: vi.fn((k: string) => { delete storageMap[k] }),
            clear: vi.fn(() => { Object.keys(storageMap).forEach(k => delete storageMap[k]) }),
        })
        const mockRes = new Response(
            JSON.stringify({ detail: 'Your Google Gemini API Key is invalid' }),
            { status: 401, headers: { 'Content-Type': 'application/json' } }
        )
        global.fetch = vi.fn().mockResolvedValueOnce(mockRes) as unknown as typeof fetch

        await expect(
            aiApi.parseMarkdown({ markdown_text: '# Day 1 Senso-ji' })
        ).rejects.toThrow('Your Google Gemini API Key is invalid')

        expect(storageMap.tabiji_session_token).toBe(validJwt)
    })

    it('streamChat preserves tabiji_session_token on Gemini 401 and only clears it on Session 401', async () => {
        const expFuture = Math.floor(Date.now() / 1000) + 3600
        const payloadB64 = Buffer.from(JSON.stringify({ sub: 'user-1', exp: expFuture })).toString('base64url')
        const validJwt = `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.${payloadB64}.sig`

        const storageMap: Record<string, string> = {
            tabiji_session_token: validJwt,
        }
        const removeSpy = vi.fn((k: string) => { delete storageMap[k] })
        vi.stubGlobal('localStorage', {
            getItem: vi.fn((k: string) => storageMap[k] ?? null),
            setItem: vi.fn((k: string, v: string) => { storageMap[k] = v }),
            removeItem: removeSpy,
            clear: vi.fn(() => { Object.keys(storageMap).forEach(k => delete storageMap[k]) }),
        })

        // Case 1: Gemini API Key 401 must NOT remove tabiji_session_token
        global.fetch = vi.fn().mockResolvedValueOnce(
            new Response(
                JSON.stringify({ detail: 'Your Google Gemini API Key is invalid or expired' }),
                { status: 401, headers: { 'Content-Type': 'application/json' } }
            )
        ) as unknown as typeof fetch

        await expect(
            streamChat('http://localhost:8000', 'hi', [], 'bad-gemini-key', {})
        ).rejects.toThrow('Your Google Gemini API Key is invalid or expired')

        expect(storageMap.tabiji_session_token).toBe(validJwt)
        expect(removeSpy).not.toHaveBeenCalled()

        // Case 2: Backend Tabiji Session 401 triggers session clear + refresh attempt
        global.fetch = vi.fn().mockResolvedValueOnce(
            new Response(
                JSON.stringify({ detail: 'Session token expired' }),
                { status: 401, headers: { 'Content-Type': 'application/json' } }
            )
        ) as unknown as typeof fetch

        await expect(
            streamChat('http://localhost:8000', 'hi', [], 'good-gemini-key', {})
        ).rejects.toThrow('Session token expired')

        expect(removeSpy).toHaveBeenCalledWith('tabiji_session_token')
        expect(storageMap.tabiji_session_token).toBeUndefined()
    })
})
