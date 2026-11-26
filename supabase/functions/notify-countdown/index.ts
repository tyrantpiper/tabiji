// @ts-nocheck
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-webhook-timestamp, x-webhook-signature',
};

const MAX_SIGNED_WEBHOOK_BYTES = 1024 * 1024;
const WEBHOOK_SIGNATURE_MAX_SKEW_SEC = 300;
const WEBHOOK_TIMESTAMP_RE = /^\d{10,13}$/;
const WEBHOOK_SIG_HEX64_RE = /^[0-9a-f]{64}$/i;
const JWT_SEGMENT_RE = /^[A-Za-z0-9_-]+=*$/;

// Countdown milestones (days before trip)
const COUNTDOWN_DAYS = [7, 3, 1];

const COUNTDOWN_EMOJI: Record<number, string> = {
  7: '✈️',
  3: '📦',
  1: '🎉',
};

function isPlainObject(val: unknown): val is Record<string, unknown> {
  return Boolean(val) && typeof val === 'object' && !Array.isArray(val);
}

function timingSafeEqual(a: string, b: string): boolean {
  const enc = new TextEncoder();
  const ab = enc.encode(a);
  const bb = enc.encode(b);
  if (ab.length !== bb.length) return false;
  let diff = 0;
  for (let i = 0; i < ab.length; i++) {
    diff |= ab[i] ^ bb[i];
  }
  return diff === 0;
}

function isUsableServiceKey(val: unknown): val is string {
  if (typeof val !== 'string') return false;
  const trimmed = val.trim();
  return Boolean(trimmed) && !trimmed.startsWith('sb_publishable_');
}

function resolveSupabaseInternalApiKeys(): string[] {
  const candidates: string[] = [];
  const pushUnique = (val: unknown) => {
    if (!isUsableServiceKey(val)) return;
    const trimmed = val.trim();
    if (!candidates.includes(trimmed)) {
      candidates.push(trimmed);
    }
  };

  try {
    const parsed = JSON.parse(Deno.env.get('SUPABASE_SECRET_KEYS') || '{}');
    if (isPlainObject(parsed)) {
      pushUnique(parsed.default);
      for (const val of Object.values(parsed)) {
        pushUnique(val);
      }
    }
  } catch {
    // ignore malformed SUPABASE_SECRET_KEYS JSON
  }
  pushUnique(Deno.env.get('SUPABASE_SECRET_KEY'));
  pushUnique(Deno.env.get('SUPABASE_SERVICE_ROLE_KEY'));
  return candidates;
}

function resolveServiceSecretKey(): string {
  const keys = resolveSupabaseInternalApiKeys();
  return keys.length > 0 ? keys[0] : '';
}

function decodeJwtPayload(token: string): Record<string, unknown> | null {
  if (!token || /[\s\r\n]/.test(token)) return null;
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  if (!parts.every((part) => part.length > 0 && JWT_SEGMENT_RE.test(part))) return null;
  try {
    let b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/').replace(/=+$/, '');
    const pad = b64.length % 4;
    if (pad === 1) return null;
    if (pad > 0) b64 += '='.repeat(4 - pad);
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) {
      bytes[i] = bin.charCodeAt(i);
    }
    const parsed = JSON.parse(new TextDecoder().decode(bytes));
    return isPlainObject(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function isValidServiceRoleJwtClaims(payload: Record<string, unknown> | null): boolean {
  if (!payload || payload.role !== 'service_role') return false;
  const exp = payload.exp;
  if (typeof exp !== 'number' || !Number.isFinite(exp)) return false;
  const nowSec = Math.floor(Date.now() / 1000);
  if (exp <= nowSec) return false;
  if (payload.nbf !== undefined) {
    if (typeof payload.nbf !== 'number' || !Number.isFinite(payload.nbf) || payload.nbf > nowSec) {
      return false;
    }
  }
  return true;
}

async function verifyServiceRoleTokenViaGoTrue(token: string, supabaseUrl: string): Promise<boolean> {
  const baseUrl = (supabaseUrl || '').trim().replace(/\/+$/, '');
  if (!baseUrl) return false;
  try {
    const parsedUrl = new URL(baseUrl);
    if (parsedUrl.protocol !== 'https:' && parsedUrl.protocol !== 'http:') return false;
  } catch {
    return false;
  }
  if (!isValidServiceRoleJwtClaims(decodeJwtPayload(token))) return false;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000);
  try {
    const resp = await fetch(`${baseUrl}/auth/v1/admin/users?page=1&per_page=1`, {
      method: 'GET',
      headers: {
        apikey: token,
        Authorization: `Bearer ${token}`,
      },
      signal: controller.signal,
    });
    await resp.body?.cancel().catch(() => {});
    return resp.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function verifyNotifyWebhookSignatureViaRpc(
  ts: number,
  signatureHex: string,
  rawBody: string,
  supabaseUrl: string
): Promise<boolean> {
  const baseUrl = (supabaseUrl || '').trim().replace(/\/+$/, '');
  if (!baseUrl) return false;
  try {
    const parsedUrl = new URL(baseUrl);
    if (parsedUrl.protocol !== 'https:' && parsedUrl.protocol !== 'http:') return false;
  } catch {
    return false;
  }

  const keys = resolveSupabaseInternalApiKeys();
  if (keys.length === 0) return false;

  const payloadJson = JSON.stringify({
    p_timestamp: ts,
    p_signature: signatureHex.toLowerCase(),
    p_body: rawBody,
  });

  for (const key of keys) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        apikey: key,
      };
      if (!key.startsWith('sb_')) {
        headers.Authorization = `Bearer ${key}`;
      }
      const resp = await fetch(`${baseUrl}/rest/v1/rpc/verify_notify_webhook_signature`, {
        method: 'POST',
        headers,
        body: payloadJson,
        signal: controller.signal,
      });
      if (resp.ok) {
        try {
          const verified = await resp.json();
          return verified === true;
        } catch {
          return false;
        }
      }
      await resp.body?.cancel().catch(() => {});
      if (resp.status !== 401 && resp.status !== 403) {
        return false;
      }
    } catch {
      return false;
    } finally {
      clearTimeout(timeoutId);
    }
  }
  return false;
}

async function authorizeNotifyRequest(req: Request, supabaseUrl: string): Promise<boolean> {
  const internalApiKeys = resolveSupabaseInternalApiKeys();
  const authHeader = req.headers.get('authorization') || '';
  const bearerMatch = authHeader.trim().match(/^bearer\s+(.+)$/i);
  const token = bearerMatch ? bearerMatch[1].trim() : '';
  const apiKeyHeader = (req.headers.get('apikey') || '').trim();
  const webhookTsHeader = (req.headers.get('x-webhook-timestamp') || '').trim();
  const webhookSigHeader = (req.headers.get('x-webhook-signature') || '').trim();

  let authorized =
    (Boolean(token) && internalApiKeys.some((key) => timingSafeEqual(token, key))) ||
    (Boolean(apiKeyHeader) && internalApiKeys.some((key) => timingSafeEqual(apiKeyHeader, key)));

  if (!authorized && token) {
    authorized = await verifyServiceRoleTokenViaGoTrue(token, supabaseUrl);
  }

  if (!authorized && webhookTsHeader && webhookSigHeader) {
    const contentLenHeader = req.headers.get('content-length');
    const declaredLen = contentLenHeader ? Number(contentLenHeader) : 0;
    const withinDeclaredLimit = !Number.isFinite(declaredLen) || declaredLen <= MAX_SIGNED_WEBHOOK_BYTES;

    if (
      withinDeclaredLimit &&
      WEBHOOK_TIMESTAMP_RE.test(webhookTsHeader) &&
      WEBHOOK_SIG_HEX64_RE.test(webhookSigHeader)
    ) {
      const ts = Number(webhookTsHeader);
      const nowSec = Math.floor(Date.now() / 1000);
      if (Number.isSafeInteger(ts) && Math.abs(nowSec - ts) <= WEBHOOK_SIGNATURE_MAX_SKEW_SEC) {
        const rawBody = await req.text();
        if (new TextEncoder().encode(rawBody).byteLength <= MAX_SIGNED_WEBHOOK_BYTES) {
          authorized = await verifyNotifyWebhookSignatureViaRpc(ts, webhookSigHeader, rawBody, supabaseUrl);
        }
      }
    }
  }

  return authorized;
}

async function emitCountdownRefreshBroadcast(
  supabaseUrl: string,
  serviceKey: string,
  userIds: string[]
): Promise<void> {
  const baseUrl = (supabaseUrl || '').trim().replace(/\/+$/, '');
  const key = (serviceKey || '').trim();
  const uniqueIds = Array.from(new Set(userIds.map((id) => (id || '').trim()).filter(Boolean)));
  if (!baseUrl || !key || uniqueIds.length === 0) return;

  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const timeoutId = controller ? setTimeout(() => controller.abort(), 2000) : null;
  try {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      apikey: key,
    };
    if (!key.startsWith('sb_')) {
      headers.Authorization = `Bearer ${key}`;
    }

    const ts = Date.now();
    const messages = uniqueIds.map((uid) => ({
      topic: `user-notif:${uid}`,
      event: 'notif:refresh',
      payload: { ts },
    }));

    const resp = await fetch(`${baseUrl}/realtime/v1/api/broadcast`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ messages }),
      ...(controller ? { signal: controller.signal } : {}),
    });
    if (!resp.ok) {
      console.warn('notify-countdown broadcast non-2xx:', resp.status);
    }
    await resp.body?.cancel().catch(() => {});
  } catch (err) {
    console.warn('notify-countdown broadcast refresh skipped:', err);
  } finally {
    if (timeoutId !== null) clearTimeout(timeoutId);
  }
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  if (req.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'Method not allowed' }), {
      status: 405,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }

  const supabaseUrl = (Deno.env.get('SUPABASE_URL') || '').trim();
  const authorized = await authorizeNotifyRequest(req, supabaseUrl);
  if (!authorized) {
    return new Response(JSON.stringify({ error: 'Unauthorized' }), {
      status: 401,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }

  try {
    const supabase = createClient(
      supabaseUrl,
      resolveServiceSecretKey()
    );

    // Find trips starting in 7, 3, or 1 days
    const results = [];

    for (const daysAhead of COUNTDOWN_DAYS) {
      const targetDate = new Date();
      targetDate.setDate(targetDate.getDate() + daysAhead);
      const dateStr = targetDate.toISOString().split('T')[0];

      const { data: trips } = await supabase
        .from('itineraries')
        .select('id, title, start_date')
        .eq('start_date', dateStr);

      if (!trips || trips.length === 0) continue;

      for (const trip of trips) {
        // Get all members of this trip
        const { data: members } = await supabase
          .from('trip_members')
          .select('user_id')
          .eq('itinerary_id', trip.id);

        if (!members || members.length === 0) continue;

        for (const member of members) {
          // Dedup: check if we already sent this type today
          const todayStart = new Date();
          todayStart.setHours(0, 0, 0, 0);

          const { data: existing } = await supabase
            .from('notifications')
            .select('id')
            .eq('user_id', member.user_id)
            .eq('type', 'trip_countdown')
            .gte('created_at', todayStart.toISOString())
            .contains('metadata', { trip_id: trip.id, days_left: daysAhead })
            .limit(1);

          if (existing && existing.length > 0) continue;

          const emoji = COUNTDOWN_EMOJI[daysAhead] || '✈️';
          const title = `${emoji} Trip Countdown!`;
          const body = daysAhead === 1
            ? `Tomorrow is the day! "${trip.title}" starts tomorrow!`
            : `"${trip.title}" is ${daysAhead} days away!`;

          // Insert notification
          const { error: insertErr } = await supabase
            .from('notifications')
            .insert({
              user_id: member.user_id,
              type: 'trip_countdown',
              title,
              body,
              link: `/?trip=${trip.id}&day=0`,
              metadata: { trip_id: trip.id, days_left: daysAhead },
            });

          if (insertErr) {
            console.error('Insert notification failed:', insertErr);
          } else {
            results.push({ user: member.user_id, trip: trip.title, days: daysAhead });
          }

          // Attempt Web Push
          const vapidPub = Deno.env.get('VAPID_PUBLIC_KEY');
          const vapidPriv = Deno.env.get('VAPID_PRIVATE_KEY');

          if (vapidPub && vapidPriv) {
            try {
              const { default: webpush } = await import('npm:web-push@3');
              webpush.setVapidDetails('mailto:ryanpig228@gmail.com', vapidPub, vapidPriv);

              const { data: subs } = await supabase
                .from('push_subscriptions')
                .select('endpoint, p256dh, auth')
                .eq('user_id', member.user_id);

              if (subs) {
                for (const sub of subs) {
                  try {
                    await webpush.sendNotification(
                      { endpoint: sub.endpoint, keys: { p256dh: sub.p256dh, auth: sub.auth } },
                      JSON.stringify({ title, body, link: `/?trip=${trip.id}&day=0`, tag: 'trip_countdown' })
                    );
                  } catch (pushErr: unknown) {
                    console.error('Push send failed:', pushErr);
                    if ((pushErr as { statusCode?: number })?.statusCode === 410) {
                      await supabase.from('push_subscriptions').delete().eq('endpoint', sub.endpoint);
                    }
                  }
                }
              }
            } catch (e) {
              console.error('Web push module error:', e);
            }
          }
        }
      }
    }

    if (results.length > 0) {
      await emitCountdownRefreshBroadcast(
        Deno.env.get('SUPABASE_URL') || '',
        resolveServiceSecretKey(),
        results.map((r) => String(r.user || ''))
      );
    }

    return new Response(
      JSON.stringify({ message: 'OK', notifications_sent: results.length, details: results }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  } catch (error) {
    console.error('notify-countdown error:', error);
    return new Response(
      JSON.stringify({ error: 'Internal server error' }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
