/**
 * @vitest-environment node
 */
import fs from 'node:fs'
import path from 'node:path'
import vm from 'node:vm'
import ts from 'typescript'
import { describe, it, expect } from 'vitest'

function loadCleanupCloudinaryExports(envMap: Record<string, string>) {
    const repoRoot = path.resolve(__dirname, '..', '..')
    const srcPath = path.join(repoRoot, 'supabase', 'functions', 'cleanup-cloudinary', 'index.ts')
    const rawSrc = fs.readFileSync(srcPath, 'utf-8').replace(/^import\s+"jsr:[^"]+";\s*$/m, '')
    const compiled = ts.transpileModule(rawSrc, {
        compilerOptions: {
            module: ts.ModuleKind.CommonJS,
            target: ts.ScriptTarget.ES2022,
            esModuleInterop: true,
        },
    })
    const mod = { exports: {} as Record<string, unknown> }
    const sandbox = {
        module: mod,
        exports: mod.exports,
        Deno: { env: { get: (k: string) => envMap[k] } },
        fetch: globalThis.fetch,
        AbortController: globalThis.AbortController,
        Request,
        Response,
        Headers,
        URL,
        FormData,
        TextEncoder,
        TextDecoder,
        crypto: globalThis.crypto,
        atob: globalThis.atob,
        console,
        setTimeout,
        clearTimeout,
    }
    vm.runInNewContext(compiled.outputText, sandbox, { filename: srcPath })
    return mod.exports as {
        handleCleanupRequest: (req: Request) => Promise<Response>
    }
}

function loadEdgeServeHandler(
    relPath: string,
    envMap: Record<string, string>,
    createClientSpy: (url: string, key: string) => unknown,
) {
    const repoRoot = path.resolve(__dirname, '..', '..')
    const srcPath = path.join(repoRoot, relPath)
    const holder: { handler: ((req: Request) => Promise<Response>) | null } = { handler: null }
    const rawSrc = fs.readFileSync(srcPath, 'utf-8')
        .replace(/^import\s+"jsr:[^"]+";\s*$/m, '')
        .replace(/^import\s+\{\s*createClient\s*\}\s+from\s+"npm:@supabase\/supabase-js@2";\s*$/m, '')

    const compiled = ts.transpileModule(rawSrc, {
        compilerOptions: {
            module: ts.ModuleKind.CommonJS,
            target: ts.ScriptTarget.ES2022,
            esModuleInterop: true,
        },
    })
    const mod = { exports: {} as Record<string, unknown> }
    const sandbox = {
        module: mod,
        exports: mod.exports,
        createClient: createClientSpy,
        Deno: {
            env: { get: (k: string) => envMap[k] },
            serve: (fn: (req: Request) => Promise<Response>) => {
                holder.handler = fn
            },
        },
        fetch: globalThis.fetch,
        AbortController: globalThis.AbortController,
        Request,
        Response,
        Headers,
        URL,
        FormData,
        TextEncoder,
        TextDecoder,
        crypto: globalThis.crypto,
        atob: globalThis.atob,
        console,
        setTimeout,
        clearTimeout,
    }
    vm.runInNewContext(compiled.outputText, sandbox, { filename: srcPath })
    if (!holder.handler) {
        throw new Error(`Expected ${relPath} to register Deno.serve handler`)
    }
    return holder.handler
}

function createEmptySupabaseStub() {
    const chain = {
        select: () => chain,
        eq: () => chain,
        neq: () => chain,
        gte: () => chain,
        contains: () => chain,
        limit: () => Promise.resolve({ data: [] }),
        single: () => Promise.resolve({ data: { title: 'Stub Trip' } }),
        then: (resolve: (v: unknown) => unknown) => Promise.resolve({ data: [] }).then(resolve),
    }
    return { from: () => chain }
}

describe('Supabase Edge Functions Secret Keys Support', () => {
    it('notify-countdown, notify-event, and cleanup-cloudinary resolve SUPABASE_SECRET_KEYS / SUPABASE_SECRET_KEY and authorize sb_secret_ cleanly', async () => {
        const repoRoot = path.resolve(__dirname, '..', '..')
        const notifyCountdown = fs.readFileSync(
            path.join(repoRoot, 'supabase', 'functions', 'notify-countdown', 'index.ts'),
            'utf-8',
        )
        const notifyEvent = fs.readFileSync(
            path.join(repoRoot, 'supabase', 'functions', 'notify-event', 'index.ts'),
            'utf-8',
        )
        const notifyBroadcast = fs.readFileSync(
            path.join(repoRoot, 'supabase', 'functions', 'notify-broadcast', 'index.ts'),
            'utf-8',
        )
        const cleanupCloudinary = fs.readFileSync(
            path.join(repoRoot, 'supabase', 'functions', 'cleanup-cloudinary', 'index.ts'),
            'utf-8',
        )

        for (const [name, src] of [
            ['notify-countdown', notifyCountdown],
            ['notify-event', notifyEvent],
            ['notify-broadcast', notifyBroadcast],
        ] as const) {
            expect(src, `${name} should define resolveServiceSecretKey`).toContain('function resolveServiceSecretKey')
            expect(src, `${name} should read SUPABASE_SECRET_KEYS`).toContain('SUPABASE_SECRET_KEYS')
            expect(src, `${name} should read SUPABASE_SECRET_KEY`).toContain('SUPABASE_SECRET_KEY')
            expect(src, `${name} must not pass bare SUPABASE_SERVICE_ROLE_KEY!`).not.toContain("Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!")
        }

        expect(cleanupCloudinary).toContain('const internalApiKeys = resolveSupabaseInternalApiKeys()')
        expect(cleanupCloudinary).toContain('internalApiKeys.some((key) => timingSafeEqual(token, key))')
        expect(cleanupCloudinary).toContain('internalApiKeys.some((key) => timingSafeEqual(apiKeyHeader, key))')
        expect(cleanupCloudinary).not.toContain('const serviceRoleKey = getEnv("SUPABASE_SERVICE_ROLE_KEY").trim()')

        // Execute compiled cleanup-cloudinary handler in-memory to verify real runtime auth behavior
        const { handleCleanupRequest } = loadCleanupCloudinaryExports({
            SUPABASE_URL: 'https://example.supabase.co',
            SUPABASE_SECRET_KEYS: JSON.stringify({
                default: 'sb_secret_unit_test_default',
                pub_mistake: 'sb_publishable_must_never_authorize',
            }),
            SUPABASE_SECRET_KEY: 'sb_secret_unit_test_singular',
        })

        // 1. Authorized via `apikey: sb_secret_...` with NO Authorization header (matches @supabase/supabase-js functions.invoke)
        const resApiKey = await handleCleanupRequest(new Request('https://edge.local/cleanup-cloudinary', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', apikey: 'sb_secret_unit_test_default' },
            body: JSON.stringify({ type: 'DELETE', table: 'itineraries', old_record: { id: 't1' } }),
        }))
        expect(resApiKey.status).toBe(200)

        // 2. Authorized via `Authorization: Bearer sb_secret_...` using singular SUPABASE_SECRET_KEY
        const resBearer = await handleCleanupRequest(new Request('https://edge.local/cleanup-cloudinary', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: 'Bearer sb_secret_unit_test_singular' },
            body: JSON.stringify({ type: 'DELETE', table: 'itineraries', old_record: { id: 't2' } }),
        }))
        expect(resBearer.status).toBe(200)

        // 3. Publishable key must NEVER be accepted even if mistakenly present in env JSON
        const resPub = await handleCleanupRequest(new Request('https://edge.local/cleanup-cloudinary', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', apikey: 'sb_publishable_must_never_authorize' },
            body: JSON.stringify({ type: 'DELETE', table: 'itineraries', old_record: { id: 't3' } }),
        }))
        expect(resPub.status).toBe(401)

        // Execute compiled notify-countdown and notify-event handlers in-memory to verify secret key resolution at runtime
        const countdownKeysSeen: string[] = []
        const countdownHandler = loadEdgeServeHandler(
            'supabase/functions/notify-countdown/index.ts',
            {
                SUPABASE_URL: 'https://example.supabase.co',
                SUPABASE_SECRET_KEYS: JSON.stringify({
                    default: 'sb_publishable_must_be_ignored',
                    secondary: 'sb_secret_countdown_secondary',
                }),
                SUPABASE_SERVICE_ROLE_KEY: 'legacy_srk_should_not_win',
            },
            (_url, key) => {
                countdownKeysSeen.push(key)
                return createEmptySupabaseStub()
            },
        )
        const countdownRes = await countdownHandler(new Request('https://edge.local/notify-countdown', { method: 'POST' }))
        expect(countdownRes.status).toBe(200)
        expect(countdownKeysSeen).toEqual(['sb_secret_countdown_secondary'])

        const eventKeysSeen: string[] = []
        const eventHandler = loadEdgeServeHandler(
            'supabase/functions/notify-event/index.ts',
            {
                SUPABASE_URL: 'https://example.supabase.co',
                SUPABASE_SECRET_KEYS: '["sb_publishable_array_invalid"]',
                SUPABASE_SECRET_KEY: 'sb_secret_event_singular',
            },
            (_url, key) => {
                eventKeysSeen.push(key)
                return createEmptySupabaseStub()
            },
        )
        const eventRes = await eventHandler(new Request('https://edge.local/notify-event', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                type: 'INSERT',
                table: 'trip_members',
                record: { itinerary_id: 'trip-1', user_id: 'u-1', user_name: 'Alice' },
            }),
        }))
        expect(eventRes.status).toBe(200)
        expect(eventKeysSeen).toEqual(['sb_secret_event_singular'])

        const broadcastKeysSeen: string[] = []
        const broadcastHandler = loadEdgeServeHandler(
            'supabase/functions/notify-broadcast/index.ts',
            {
                SUPABASE_URL: 'https://example.supabase.co',
                BROADCAST_SECRET: 'test-broadcast-secret',
                SUPABASE_SECRET_KEYS: JSON.stringify({
                    default: 'sb_secret_broadcast_default',
                    legacy_pub: 'sb_publishable_must_ignore',
                }),
                SUPABASE_SERVICE_ROLE_KEY: 'legacy_srk_should_not_win',
            },
            (_url, key) => {
                broadcastKeysSeen.push(key)
                const chain = {
                    select: () => chain,
                    eq: () => chain,
                    contains: () => chain,
                    limit: () => Promise.resolve({ data: [{ id: 'existing-notif' }] }),
                }
                return { from: () => chain }
            },
        )
        const broadcastRes = await broadcastHandler(new Request('https://edge.local/notify-broadcast', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: 'Bearer test-broadcast-secret',
            },
            body: JSON.stringify({
                title: 'Test Title',
                body: 'Test Body',
                broadcast_id: 'dedup-check-1',
            }),
        }))
        expect(broadcastRes.status).toBe(200)
        expect(broadcastKeysSeen).toEqual(['sb_secret_broadcast_default'])

        // Verify Realtime Broadcast emits opaque notif:refresh with apikey header (and NO Authorization Bearer on sb_secret_*)
        const origFetch = globalThis.fetch
        const recordedBroadcastCalls: Array<{ url: string; headers: Record<string, string>; body: unknown }> = []
        globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
            recordedBroadcastCalls.push({
                url: String(url),
                headers: (init?.headers || {}) as Record<string, string>,
                body: JSON.parse(String(init?.body || '{}')),
            })
            return new Response(JSON.stringify({ ok: true }), { status: 202 })
        }) as typeof fetch

        try {
            const broadcastSendHandler = loadEdgeServeHandler(
                'supabase/functions/notify-broadcast/index.ts',
                {
                    SUPABASE_URL: 'https://example.supabase.co',
                    BROADCAST_SECRET: 'test-broadcast-secret',
                    SUPABASE_SECRET_KEY: 'sb_secret_realtime_check',
                },
                () => ({
                    from: (tbl: string) => {
                        if (tbl === 'users') {
                            return {
                                select: () => Promise.resolve({ data: [{ id: 'u-100' }], error: null }),
                            }
                        }
                        if (tbl === 'push_subscriptions') {
                            return {
                                select: () => Promise.resolve({ data: [{ user_id: 'u-100' }, { user_id: 'u-200' }], error: null }),
                            }
                        }
                        if (tbl === 'notifications') {
                            return {
                                select: () => ({
                                    eq: () => ({ contains: () => ({ limit: () => Promise.resolve({ data: [] }) }) }),
                                }),
                                insert: () => Promise.resolve({ error: null }),
                            }
                        }
                        return createEmptySupabaseStub().from()
                    },
                }),
            )
            const res = await broadcastSendHandler(new Request('https://edge.local/notify-broadcast', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: 'Bearer test-broadcast-secret' },
                body: JSON.stringify({ title: 'Notice', body: 'Hello' }),
            }))
            expect(res.status).toBe(200)
            expect(recordedBroadcastCalls.length).toBe(1)
            expect(recordedBroadcastCalls[0].url).toBe('https://example.supabase.co/realtime/v1/api/broadcast')
            expect(recordedBroadcastCalls[0].headers.apikey).toBe('sb_secret_realtime_check')
            expect(recordedBroadcastCalls[0].headers.Authorization).toBeUndefined()
            expect((recordedBroadcastCalls[0].body as { messages: Array<{ topic: string; event: string; payload: { ts: number } }> }).messages[0].topic).toBe('user-notif:broadcast')
            expect((recordedBroadcastCalls[0].body as { messages: Array<{ topic: string; event: string }> }).messages[0].event).toBe('notif:refresh')

            // Also verify notify-event emits unprefixed `user-notif:<uid>` matching supabase.channel('user-notif:<uid>')
            recordedBroadcastCalls.length = 0
            const eventBroadcastHandler = loadEdgeServeHandler(
                'supabase/functions/notify-event/index.ts',
                {
                    SUPABASE_URL: 'https://example.supabase.co',
                    SUPABASE_SECRET_KEY: 'sb_secret_event_broadcast_check',
                },
                () => ({
                    from: (tbl: string) => {
                        if (tbl === 'itineraries') {
                            return {
                                select: () => ({ eq: () => ({ single: () => Promise.resolve({ data: { title: 'Kyoto' } }) }) }),
                            }
                        }
                        if (tbl === 'trip_members') {
                            return {
                                select: () => ({ eq: () => ({ neq: () => Promise.resolve({ data: [{ user_id: 'u-target-1' }] }) }) }),
                            }
                        }
                        if (tbl === 'notifications') {
                            return { insert: () => Promise.resolve({ error: null }) }
                        }
                        return createEmptySupabaseStub().from()
                    },
                }),
            )
            const evRes = await eventBroadcastHandler(new Request('https://edge.local/notify-event', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    type: 'INSERT',
                    table: 'trip_members',
                    record: { itinerary_id: 'trip-1', user_id: 'u-new', user_name: 'Alice' },
                }),
            }))
            expect(evRes.status).toBe(200)
            expect(recordedBroadcastCalls.length).toBe(1)
            expect((recordedBroadcastCalls[0].body as { messages: Array<{ topic: string; event: string }> }).messages[0].topic).toBe('user-notif:u-target-1')
            expect((recordedBroadcastCalls[0].body as { messages: Array<{ topic: string; event: string }> }).messages[0].event).toBe('notif:refresh')
        } finally {
            globalThis.fetch = origFetch
        }
    })
})
