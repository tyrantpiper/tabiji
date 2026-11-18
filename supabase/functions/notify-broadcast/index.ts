// @ts-nocheck
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// Batch size for Web Push sends
const PUSH_BATCH_SIZE = 50;

function isUsableServiceKey(val: unknown): val is string {
  if (typeof val !== 'string') return false;
  const trimmed = val.trim();
  return Boolean(trimmed) && !trimmed.startsWith('sb_publishable_');
}

function resolveServiceSecretKey(): string {
  try {
    const parsed = JSON.parse(Deno.env.get('SUPABASE_SECRET_KEYS') || '{}');
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      if (isUsableServiceKey((parsed as Record<string, unknown>).default)) {
        return (parsed as Record<string, string>).default.trim();
      }
      for (const val of Object.values(parsed)) {
        if (isUsableServiceKey(val)) {
          return val.trim();
        }
      }
    }
  } catch {
    // ignore malformed SUPABASE_SECRET_KEYS JSON
  }
  const singular = Deno.env.get('SUPABASE_SECRET_KEY');
  if (isUsableServiceKey(singular)) return singular.trim();
  const legacy = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
  if (isUsableServiceKey(legacy)) return legacy.trim();
  return '';
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    // === Auth: verify BROADCAST_SECRET ===
    const authHeader = req.headers.get('authorization') || '';
    const token = authHeader.replace('Bearer ', '');
    const broadcastSecret = Deno.env.get('BROADCAST_SECRET');

    if (!broadcastSecret || token !== broadcastSecret) {
      return new Response(
        JSON.stringify({ error: 'Forbidden: invalid BROADCAST_SECRET' }),
        { status: 403, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // === Parse payload ===
    const { title, body, link, broadcast_id } = await req.json();

    if (!title || !body) {
      return new Response(
        JSON.stringify({ error: 'Missing required fields: title, body' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    const supabase = createClient(
      Deno.env.get('SUPABASE_URL')!,
      resolveServiceSecretKey()
    );

    // === Dedup check ===
    if (broadcast_id) {
      const { data: existing } = await supabase
        .from('notifications')
        .select('id')
        .eq('type', 'system_announcement')
        .contains('metadata', { broadcast_id })
        .limit(1);

      if (existing && existing.length > 0) {
        return new Response(
          JSON.stringify({ message: 'Broadcast already sent', broadcast_id }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        );
      }
    }

    // === Get all users ===
    const { data: users, error: usersErr } = await supabase
      .from('users')
      .select('id');

    if (usersErr || !users) {
      return new Response(
        JSON.stringify({ error: 'Failed to fetch users', detail: usersErr?.message }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // === Get all push subscriptions (to include anonymous users) ===
    const { data: subs, error: subsErr } = await supabase
      .from('push_subscriptions')
      .select('user_id');

    if (subsErr) {
      console.error('Failed to fetch push subscriptions:', subsErr);
    }

    // === Union of users and subscribers ===
    const targetUserIds = new Set<string>([
      ...users.map((u) => u.id),
      ...(subs || []).map((s) => s.user_id)
    ]);

    if (targetUserIds.size === 0) {
      return new Response(
        JSON.stringify({ error: 'No users or subscriptions found' }),
        { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // === Bulk insert in-app notifications ===
    const notifications = Array.from(targetUserIds).map((userId) => ({
      user_id: userId,
      type: 'system_announcement',
      title,
      body,
      link: link || '/',
      metadata: broadcast_id ? { broadcast_id } : {},
    }));

    const { error: insertErr } = await supabase
      .from('notifications')
      .insert(notifications);

    if (insertErr) {
      console.error('Failed to insert broadcast notifications:', insertErr);
    }

    // === Web Push ===
    let pushesSent = 0;
    let pushesFailed = 0;
    let cleaned = 0;

    const vapidPub = Deno.env.get('VAPID_PUBLIC_KEY');
    const vapidPriv = Deno.env.get('VAPID_PRIVATE_KEY');

    if (vapidPub && vapidPriv) {
      const { default: webpush } = await import('npm:web-push@3');
      webpush.setVapidDetails('mailto:ryanpig228@gmail.com', vapidPub, vapidPriv);

      const { data: allSubs } = await supabase
        .from('push_subscriptions')
        .select('endpoint, p256dh, auth');

      if (allSubs && allSubs.length > 0) {
        const pushPayload = JSON.stringify({
          title,
          body,
          link: link || '/',
          tag: 'system_announcement',
        });

        // Process in batches
        for (let i = 0; i < allSubs.length; i += PUSH_BATCH_SIZE) {
          const batch = allSubs.slice(i, i + PUSH_BATCH_SIZE);
          const results = await Promise.allSettled(
            batch.map((sub) =>
              webpush.sendNotification(
                { endpoint: sub.endpoint, keys: { p256dh: sub.p256dh, auth: sub.auth } },
                pushPayload
              )
            )
          );

          for (let j = 0; j < results.length; j++) {
            if (results[j].status === 'fulfilled') {
              pushesSent++;
            } else {
              pushesFailed++;
              const err = (results[j] as PromiseRejectedResult).reason;
              if (err?.statusCode === 410) {
                await supabase.from('push_subscriptions').delete().eq('endpoint', batch[j].endpoint);
                cleaned++;
              }
            }
          }
        }
      }
    }

    return new Response(
      JSON.stringify({
        message: 'Broadcast sent',
        broadcast_id: broadcast_id || null,
        users_notified: targetUserIds.size,
        pushes_sent: pushesSent,
        pushes_failed: pushesFailed,
        expired_cleaned: cleaned,
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  } catch (error) {
    console.error('notify-broadcast error:', error);
    return new Response(
      JSON.stringify({ error: (error as Error).message }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
