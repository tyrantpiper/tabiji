-- T5, T6, T7, T8: Activity address persistence, Agent fallback tasks DB store,
-- Atomic trip capsule day shifting (Day 0 preserved, 23505 safe),
-- Mapillary expression-indexed reference counting, and capsule photo cleanup trigger.

-- 1. T6: Add persisted address column on itinerary_items
ALTER TABLE public.itinerary_items
ADD COLUMN IF NOT EXISTS address TEXT;

-- 2. T8: Expression index for fast Mapillary reference counting inside trigger
CREATE INDEX IF NOT EXISTS idx_itinerary_items_mly_ref_id
ON public.itinerary_items (
    (COALESCE(
        NULLIF(preview_metadata->>'mapillary_image_id', ''),
        substring(preview_metadata->>'mapillary_thumb' FROM '/ryan_travel/streetview/mly_([0-9]+)')
    ))
);

-- 3. T7c: Persistent multi-instance fallback task table for Deep Research
CREATE TABLE IF NOT EXISTS public.agent_fallback_tasks (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'running',
    output_text TEXT,
    error_message TEXT,
    engine TEXT NOT NULL DEFAULT 'gemini-3.5-flash-lite-fallback',
    key_hash TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '24 hours')
);

CREATE INDEX IF NOT EXISTS idx_agent_fallback_tasks_expires_at
ON public.agent_fallback_tasks (expires_at);

ALTER TABLE public.agent_fallback_tasks ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.agent_fallback_tasks FROM anon, authenticated;
GRANT ALL ON TABLE public.agent_fallback_tasks TO service_role;

-- 4. T5/T9: Atomic RPC for shifting/truncating trip_capsule_entries without uq_trip_day_author (23505) collisions
-- Strictly preserves Day 0 finale capsules (day_number = 0).
CREATE OR REPLACE FUNCTION public.shift_trip_capsules(
    p_trip_id UUID,
    p_op TEXT,
    p_pivot_day INTEGER
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public', 'pg_temp'
AS $function$
BEGIN
    IF p_trip_id IS NULL OR p_pivot_day IS NULL OR p_pivot_day < 1 THEN
        RETURN;
    END IF;

    IF p_op = 'delete_shift' THEN
        DELETE FROM public.trip_capsule_entries
        WHERE trip_id = p_trip_id
          AND day_number = p_pivot_day
          AND day_number > 0;

        UPDATE public.trip_capsule_entries
        SET day_number = day_number + 10000,
            updated_at = NOW()
        WHERE trip_id = p_trip_id
          AND day_number > p_pivot_day;

        UPDATE public.trip_capsule_entries
        SET day_number = day_number - 10001,
            updated_at = NOW()
        WHERE trip_id = p_trip_id
          AND day_number > 10000;

    ELSIF p_op = 'insert_shift' THEN
        UPDATE public.trip_capsule_entries
        SET day_number = day_number + 10000,
            updated_at = NOW()
        WHERE trip_id = p_trip_id
          AND day_number >= p_pivot_day
          AND day_number > 0;

        UPDATE public.trip_capsule_entries
        SET day_number = day_number - 9999,
            updated_at = NOW()
        WHERE trip_id = p_trip_id
          AND day_number > 10000;

    ELSIF p_op = 'truncate_delete' THEN
        DELETE FROM public.trip_capsule_entries
        WHERE trip_id = p_trip_id
          AND day_number > p_pivot_day;

    ELSIF p_op = 'truncate_merge' THEN
        WITH candidates AS (
            SELECT DISTINCT ON (e.author_id) e.id
            FROM public.trip_capsule_entries e
            WHERE e.trip_id = p_trip_id
              AND e.day_number > p_pivot_day
              AND NOT EXISTS (
                  SELECT 1
                  FROM public.trip_capsule_entries cur
                  WHERE cur.trip_id = p_trip_id
                    AND cur.day_number = p_pivot_day
                    AND cur.author_id = e.author_id
              )
            ORDER BY e.author_id, e.day_number ASC, e.created_at ASC
        )
        UPDATE public.trip_capsule_entries
        SET day_number = p_pivot_day,
            updated_at = NOW()
        WHERE id IN (SELECT id FROM candidates);

        DELETE FROM public.trip_capsule_entries
        WHERE trip_id = p_trip_id
          AND day_number > p_pivot_day;
    ELSE
        RAISE EXCEPTION 'Unsupported shift_trip_capsules operation: %', p_op;
    END IF;
END;
$function$;

REVOKE ALL ON FUNCTION public.shift_trip_capsules(UUID, TEXT, INTEGER) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.shift_trip_capsules(UUID, TEXT, INTEGER) TO service_role;

-- 5. T8: Mapillary reference-counting in webhook_cleanup_cloudinary + attach to trip_capsule_entries
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
    v_payload jsonb;
    v_headers jsonb;
    v_hmac_secret text;
    v_ts bigint;
    v_sig text;
    v_legacy_srk text;
BEGIN
    v_old_json := to_jsonb(OLD);
    v_new_json := CASE WHEN TG_OP = 'UPDATE' THEN to_jsonb(NEW) ELSE NULL END;

    -- Skip no-op updates on trip_capsule_entries (e.g., day_number shifts or text-only edits)
    IF TG_TABLE_NAME = 'trip_capsule_entries' THEN
        IF NULLIF(btrim(COALESCE(v_old_json->>'photo_url', '')), '') IS NULL THEN
            RETURN COALESCE(NEW, OLD);
        END IF;
        IF TG_OP = 'UPDATE' AND (v_old_json->>'photo_url') IS NOT DISTINCT FROM (v_new_json->>'photo_url') THEN
            RETURN COALESCE(NEW, OLD);
        END IF;
    END IF;

    -- Indexed Mapillary reference-counting guard: protect shared streetviews from premature deletion
    IF TG_TABLE_NAME = 'itinerary_items' AND v_old_json IS NOT NULL THEN
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
                    v_old_item_id := NULLIF(v_old_json->>'id', '')::uuid;
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
    END IF;

    v_payload := jsonb_build_object(
        'old_record', v_old_json,
        'new_record', v_new_json,
        'table', TG_TABLE_NAME,
        'type', TG_OP
    );

    v_headers := jsonb_build_object('Content-Type', 'application/json');

    SELECT decrypted_secret
      INTO v_hmac_secret
      FROM vault.decrypted_secrets
     WHERE name = 'cleanup_webhook_secret'
     LIMIT 1;

    IF v_hmac_secret IS NOT NULL AND length(v_hmac_secret) >= 32 THEN
        v_ts := floor(extract(epoch FROM clock_timestamp()))::bigint;
        v_sig := encode(
            extensions.hmac(
                convert_to(v_ts::text || '.' || v_payload::text, 'utf8'),
                convert_to(v_hmac_secret, 'utf8'),
                'sha256'
            ),
            'hex'
        );
        v_headers := v_headers || jsonb_build_object(
            'x-webhook-timestamp', v_ts::text,
            'x-webhook-signature', v_sig
        );
    ELSE
        v_legacy_srk := NULLIF(btrim(current_setting('app.settings.service_role_key', true)), '');
        IF v_legacy_srk IS NOT NULL THEN
            v_headers := v_headers || jsonb_build_object(
                'Authorization', 'Bearer ' || v_legacy_srk
            );
        END IF;
    END IF;

    PERFORM net.http_post(
        url := 'https://oudnkmigfueuyvxqpqwn.supabase.co/functions/v1/cleanup-cloudinary',
        headers := v_headers,
        body := v_payload
    );

    RETURN COALESCE(NEW, OLD);
END;
$function$;

DROP TRIGGER IF EXISTS cleanup_cloudinary_trigger ON public.trip_capsule_entries;
CREATE TRIGGER cleanup_cloudinary_trigger
AFTER DELETE OR UPDATE ON public.trip_capsule_entries
FOR EACH ROW
EXECUTE FUNCTION public.webhook_cleanup_cloudinary();
