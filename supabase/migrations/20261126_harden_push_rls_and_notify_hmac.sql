-- Wave 1.1, 1.2 & 3.3 Security Hardening Migration (2026-11-26)
-- ============================================================================
-- 1. Lock down public.push_subscriptions to Default-Deny for PUBLIC/anon/authenticated
--    (all reads/writes flow through FastAPI service_role & Edge Functions).
-- 2. Create isolated Vault secret `notify_webhook_secret`, constant-time
--    `verify_notify_webhook_signature`, Vault-HMAC signed `notify_event_webhook()`,
--    and `dispatch_trip_countdown_daily()` for pg_cron `trip-countdown-daily`.
-- 3. Remove legacy plaintext Bearer fallback (`app.settings.service_role_key`) from
--    `webhook_cleanup_cloudinary()`, and add GIN-indexed cross-row reference-counting
--    protection for shared `ryan_travel/spots/<public_id>` assets across
--    `itinerary_items.image_url` (text) and `itinerary_items.image_urls` (jsonb).

-- ----------------------------------------------------------------------------
-- 1. Wave 1.1: Default-Deny RLS & DAC Lockdown on public.push_subscriptions
-- ----------------------------------------------------------------------------
REVOKE ALL ON TABLE public.push_subscriptions FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE public.push_subscriptions TO service_role;
DROP POLICY IF EXISTS "Users manage own push subscriptions" ON public.push_subscriptions;
ALTER TABLE public.push_subscriptions ENABLE ROW LEVEL SECURITY;

-- ----------------------------------------------------------------------------
-- 2. Wave 1.2: Vault HMAC-SHA256 for notify-event & notify-countdown
-- ----------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM vault.secrets WHERE name = 'notify_webhook_secret'
  ) THEN
    PERFORM vault.create_secret(
      encode(extensions.gen_random_bytes(32), 'hex'),
      'notify_webhook_secret',
      'Internal HMAC-SHA256 secret for pg_net notify-event and notify-countdown webhooks'
    );
  END IF;
END
$$;

CREATE OR REPLACE FUNCTION public.verify_notify_webhook_signature(
  p_timestamp bigint,
  p_signature text,
  p_body text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, vault, extensions, pg_temp
AS $function$
DECLARE
  v_secret text;
  v_now bigint;
  v_expected text;
  v_sig text;
  v_a bytea;
  v_b bytea;
  v_diff integer := 0;
  v_i integer;
BEGIN
  IF p_timestamp IS NULL OR p_signature IS NULL OR p_body IS NULL THEN
    RETURN false;
  END IF;

  v_sig := lower(btrim(p_signature));
  IF length(v_sig) <> 64 OR v_sig !~ '^[0-9a-f]{64}$' THEN
    RETURN false;
  END IF;

  v_now := floor(extract(epoch FROM clock_timestamp()))::bigint;
  IF abs(v_now - p_timestamp) > 300 THEN
    RETURN false;
  END IF;

  SELECT decrypted_secret
    INTO v_secret
    FROM vault.decrypted_secrets
   WHERE name = 'notify_webhook_secret'
   LIMIT 1;

  IF v_secret IS NULL OR length(v_secret) < 32 THEN
    RETURN false;
  END IF;

  v_expected := encode(
    extensions.hmac(
      convert_to(p_timestamp::text || '.' || p_body, 'utf8'),
      convert_to(v_secret, 'utf8'),
      'sha256'
    ),
    'hex'
  );

  IF length(v_expected) <> 64 THEN
    RETURN false;
  END IF;

  v_a := convert_to(v_sig, 'utf8');
  v_b := convert_to(v_expected, 'utf8');
  IF octet_length(v_a) <> 64 OR octet_length(v_b) <> 64 THEN
    RETURN false;
  END IF;

  FOR v_i IN 0..63 LOOP
    v_diff := v_diff | (get_byte(v_a, v_i) # get_byte(v_b, v_i));
  END LOOP;

  RETURN v_diff = 0;
END;
$function$;

REVOKE ALL ON FUNCTION public.verify_notify_webhook_signature(bigint, text, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.verify_notify_webhook_signature(bigint, text, text) TO service_role;

CREATE OR REPLACE FUNCTION public.notify_event_webhook()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public', 'vault', 'extensions', 'pg_temp'
AS $function$
DECLARE
  v_edge_fn_url text := 'https://oudnkmigfueuyvxqpqwn.supabase.co/functions/v1/notify-event';
  v_payload jsonb;
  v_headers jsonb;
  v_hmac_secret text;
  v_ts bigint;
  v_sig text;
BEGIN
  v_payload := jsonb_build_object(
    'type', TG_OP,
    'table', TG_TABLE_NAME,
    'schema', TG_TABLE_SCHEMA,
    'record', row_to_json(NEW)::jsonb
  );

  SELECT decrypted_secret
    INTO v_hmac_secret
    FROM vault.decrypted_secrets
   WHERE name = 'notify_webhook_secret'
   LIMIT 1;

  IF v_hmac_secret IS NULL OR length(v_hmac_secret) < 32 THEN
    RAISE WARNING 'notify_event_webhook: Vault secret notify_webhook_secret missing or invalid; skipping dispatch';
    RETURN NEW;
  END IF;

  v_ts := floor(extract(epoch FROM clock_timestamp()))::bigint;
  v_sig := encode(
    extensions.hmac(
      convert_to(v_ts::text || '.' || v_payload::text, 'utf8'),
      convert_to(v_hmac_secret, 'utf8'),
      'sha256'
    ),
    'hex'
  );

  v_headers := jsonb_build_object(
    'Content-Type', 'application/json',
    'x-webhook-timestamp', v_ts::text,
    'x-webhook-signature', v_sig
  );

  PERFORM net.http_post(
    url := v_edge_fn_url,
    headers := v_headers,
    body := v_payload
  );

  RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION public.notify_event_webhook() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.notify_event_webhook() TO postgres, service_role;

CREATE OR REPLACE FUNCTION public.dispatch_trip_countdown_daily()
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public', 'vault', 'extensions', 'pg_temp'
AS $function$
DECLARE
  v_edge_fn_url text := 'https://oudnkmigfueuyvxqpqwn.supabase.co/functions/v1/notify-countdown';
  v_payload jsonb := '{}'::jsonb;
  v_headers jsonb;
  v_hmac_secret text;
  v_ts bigint;
  v_sig text;
  v_request_id bigint;
BEGIN
  SELECT decrypted_secret
    INTO v_hmac_secret
    FROM vault.decrypted_secrets
   WHERE name = 'notify_webhook_secret'
   LIMIT 1;

  IF v_hmac_secret IS NULL OR length(v_hmac_secret) < 32 THEN
    RAISE WARNING 'dispatch_trip_countdown_daily: Vault secret notify_webhook_secret missing or invalid; skipping dispatch';
    RETURN NULL;
  END IF;

  v_ts := floor(extract(epoch FROM clock_timestamp()))::bigint;
  v_sig := encode(
    extensions.hmac(
      convert_to(v_ts::text || '.' || v_payload::text, 'utf8'),
      convert_to(v_hmac_secret, 'utf8'),
      'sha256'
    ),
    'hex'
  );

  v_headers := jsonb_build_object(
    'Content-Type', 'application/json',
    'x-webhook-timestamp', v_ts::text,
    'x-webhook-signature', v_sig
  );

  SELECT net.http_post(
    url := v_edge_fn_url,
    headers := v_headers,
    body := v_payload
  ) INTO v_request_id;

  RETURN v_request_id;
END;
$function$;

REVOKE ALL ON FUNCTION public.dispatch_trip_countdown_daily() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.dispatch_trip_countdown_daily() TO postgres, service_role;

DO $$
DECLARE
  v_job_id bigint;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'cron') THEN
    SELECT jobid
      INTO v_job_id
      FROM cron.job
     WHERE jobname = 'trip-countdown-daily'
     LIMIT 1;

    IF v_job_id IS NOT NULL THEN
      PERFORM cron.alter_job(
        job_id := v_job_id,
        command := 'SELECT public.dispatch_trip_countdown_daily() AS request_id;'
      );
    END IF;
  END IF;
END
$$;

-- ----------------------------------------------------------------------------
-- 3. Wave 3.3: Indexed Cloudinary `spots` Cross-Row Ref-Count Guard +
--    Remove Legacy Plaintext Bearer Fallback in webhook_cleanup_cloudinary()
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.extract_spot_cloudinary_ids(
  p_image_url text,
  p_image_urls jsonb
)
RETURNS text[]
LANGUAGE sql
IMMUTABLE
SET search_path = public, pg_temp
AS $$
  SELECT COALESCE(
    ARRAY(
      SELECT DISTINCT m[1]
      FROM (
        SELECT regexp_match(p_image_url, '/ryan_travel/spots/([A-Za-z0-9_-]+)') AS m
        WHERE p_image_url IS NOT NULL AND p_image_url <> ''
        UNION ALL
        SELECT regexp_match(elem, '/ryan_travel/spots/([A-Za-z0-9_-]+)') AS m
        FROM jsonb_array_elements_text(
          CASE
            WHEN p_image_urls IS NOT NULL AND jsonb_typeof(p_image_urls) = 'array'
            THEN p_image_urls
            ELSE '[]'::jsonb
          END
        ) AS elem
      ) sub
      WHERE m IS NOT NULL AND m[1] IS NOT NULL AND m[1] <> ''
    ),
    ARRAY[]::text[]
  );
$$;

CREATE INDEX IF NOT EXISTS idx_itinerary_items_spot_ref_ids
ON public.itinerary_items
USING GIN (public.extract_spot_cloudinary_ids(image_url, image_urls));

CREATE OR REPLACE FUNCTION public.webhook_cleanup_cloudinary()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public', 'vault', 'extensions', 'pg_temp'
AS $function$
DECLARE
    v_old_json jsonb;
    v_new_json jsonb;
    v_old_mly_thumb text;
    v_new_mly_thumb text;
    v_mly_id text;
    v_old_item_id uuid;
    v_old_img_url text;
    v_spot_id text;
    v_filtered_urls jsonb;
    v_payload jsonb;
    v_headers jsonb;
    v_hmac_secret text;
    v_ts bigint;
    v_sig text;
BEGIN
    v_old_json := to_jsonb(OLD);
    v_new_json := CASE WHEN TG_OP = 'UPDATE' THEN to_jsonb(NEW) ELSE NULL END;

    -- Skip no-op updates on itineraries when cover_image has nothing to delete or did not change
    IF TG_TABLE_NAME = 'itineraries' AND TG_OP = 'UPDATE' THEN
        IF NULLIF(btrim(COALESCE(v_old_json->>'cover_image', '')), '') IS NULL
           OR (v_old_json->>'cover_image') IS NOT DISTINCT FROM (v_new_json->>'cover_image') THEN
            RETURN NEW;
        END IF;
    END IF;

    -- Skip no-op updates on trip_capsule_entries (e.g., day_number shifts or text-only edits)
    IF TG_TABLE_NAME = 'trip_capsule_entries' THEN
        IF NULLIF(btrim(COALESCE(v_old_json->>'photo_url', '')), '') IS NULL THEN
            RETURN COALESCE(NEW, OLD);
        END IF;
        IF TG_OP = 'UPDATE' AND (v_old_json->>'photo_url') IS NOT DISTINCT FROM (v_new_json->>'photo_url') THEN
            RETURN COALESCE(NEW, OLD);
        END IF;
    END IF;

    -- Indexed reference-counting guards on itinerary_items:
    -- (a) Mapillary streetviews (`mly_*`)
    -- (b) Shared spot photos (`ryan_travel/spots/<public_id>`) across `image_url` (text) & `image_urls` (jsonb)
    IF TG_TABLE_NAME = 'itinerary_items' AND v_old_json IS NOT NULL THEN
        v_old_item_id := NULLIF(v_old_json->>'id', '')::uuid;

        -- (a) Mapillary streetview guard
        BEGIN
            v_old_mly_thumb := v_old_json->'preview_metadata'->>'mapillary_thumb';
            v_new_mly_thumb := CASE
                WHEN v_new_json IS NOT NULL THEN v_new_json->'preview_metadata'->>'mapillary_thumb'
                ELSE NULL
            END;

            IF TG_OP = 'DELETE' OR v_old_mly_thumb IS DISTINCT FROM v_new_mly_thumb THEN
                v_mly_id := NULLIF(
                    COALESCE(
                        NULLIF(v_old_json->'preview_metadata'->>'mapillary_image_id', ''),
                        substring(v_old_mly_thumb FROM '/ryan_travel/streetview/mly_([0-9]+)')
                    ),
                    ''
                );

                IF v_mly_id IS NOT NULL THEN
                    IF EXISTS (
                        SELECT 1
                        FROM public.itinerary_items
                        WHERE id <> v_old_item_id
                          AND COALESCE(
                              NULLIF(preview_metadata->>'mapillary_image_id', ''),
                              substring(preview_metadata->>'mapillary_thumb' FROM '/ryan_travel/streetview/mly_([0-9]+)')
                          ) = v_mly_id
                    ) THEN
                        v_old_json := v_old_json #- '{preview_metadata,mapillary_thumb}';
                    END IF;
                END IF;
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                NULL;
        END;

        -- (b) Shared spot photos guard using GIN index idx_itinerary_items_spot_ref_ids
        BEGIN
            v_old_img_url := v_old_json->>'image_url';
            IF v_old_img_url IS NOT NULL AND v_old_img_url <> '' THEN
                v_spot_id := substring(v_old_img_url FROM '/ryan_travel/spots/([A-Za-z0-9_-]+)');
                IF v_spot_id IS NOT NULL AND v_spot_id <> '' THEN
                    IF EXISTS (
                        SELECT 1
                        FROM public.itinerary_items
                        WHERE id <> v_old_item_id
                          AND public.extract_spot_cloudinary_ids(image_url, image_urls) @> ARRAY[v_spot_id]
                    ) THEN
                        v_old_json := v_old_json - 'image_url';
                    END IF;
                END IF;
            END IF;

            IF v_old_json ? 'image_urls' AND jsonb_typeof(v_old_json->'image_urls') = 'array' THEN
                SELECT COALESCE(jsonb_agg(elem ORDER BY ord), '[]'::jsonb)
                  INTO v_filtered_urls
                  FROM jsonb_array_elements(v_old_json->'image_urls') WITH ORDINALITY AS t(elem, ord)
                 WHERE jsonb_typeof(elem) <> 'string'
                    OR substring((elem #>> '{}') FROM '/ryan_travel/spots/([A-Za-z0-9_-]+)') IS NULL
                    OR NOT EXISTS (
                        SELECT 1
                        FROM public.itinerary_items
                        WHERE id <> v_old_item_id
                          AND public.extract_spot_cloudinary_ids(image_url, image_urls)
                              @> ARRAY[substring((elem #>> '{}') FROM '/ryan_travel/spots/([A-Za-z0-9_-]+)')]
                    );
                v_old_json := jsonb_set(v_old_json, '{image_urls}', v_filtered_urls, true);
            END IF;
        EXCEPTION
            WHEN OTHERS THEN
                NULL;
        END;
    END IF;

    v_payload := jsonb_build_object(
        'old_record', v_old_json,
        'new_record', v_new_json,
        'table', TG_TABLE_NAME,
        'type', TG_OP
    );

    SELECT decrypted_secret
      INTO v_hmac_secret
      FROM vault.decrypted_secrets
     WHERE name = 'cleanup_webhook_secret'
     LIMIT 1;

    -- Fail-Closed: zero plaintext Bearer fallback in net.http_request_queue
    IF v_hmac_secret IS NULL OR length(v_hmac_secret) < 32 THEN
        RAISE WARNING 'webhook_cleanup_cloudinary: Vault secret cleanup_webhook_secret missing or invalid; skipping dispatch';
        RETURN COALESCE(NEW, OLD);
    END IF;

    v_ts := floor(extract(epoch FROM clock_timestamp()))::bigint;
    v_sig := encode(
        extensions.hmac(
            convert_to(v_ts::text || '.' || v_payload::text, 'utf8'),
            convert_to(v_hmac_secret, 'utf8'),
            'sha256'
        ),
        'hex'
    );

    v_headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'x-webhook-timestamp', v_ts::text,
        'x-webhook-signature', v_sig
    );

    PERFORM net.http_post(
        url := 'https://oudnkmigfueuyvxqpqwn.supabase.co/functions/v1/cleanup-cloudinary',
        headers := v_headers,
        body := v_payload
    );

    RETURN COALESCE(NEW, OLD);
END;
$function$;

REVOKE ALL ON FUNCTION public.webhook_cleanup_cloudinary() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.webhook_cleanup_cloudinary() TO postgres, service_role;
