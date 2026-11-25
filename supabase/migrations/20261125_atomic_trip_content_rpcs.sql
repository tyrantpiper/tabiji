-- Phase 1 Pure Postgres Atomic Trip Content RPCs + Legacy High-Risk RPC Removal + Trigger No-Op Guard
-- ===================================================================================================
-- 1. Drop legacy SECURITY DEFINER public.update_trip_credit_cards(UUID, JSONB) exposed to authenticated.
-- 2. Harden public.webhook_cleanup_cloudinary() with an itineraries UPDATE no-op guard checking
--    cover_image ONLY (matching live cleanup-cloudinary v8, which inspects itineraries.cover_image).
-- 3. Add 3 SECURITY DEFINER, service_role-only atomic RPCs using FOR NO KEY UPDATE + transaction-local
--    lock_timeout (3000ms) / statement_timeout (8000ms) + safe top-level object merge (`|| jsonb_build_object`).

-- 1. Remove high-risk legacy authenticated-callable RPC
DROP FUNCTION IF EXISTS public.update_trip_credit_cards(UUID, JSONB);

-- 2. Update public.webhook_cleanup_cloudinary() with itineraries UPDATE cover_image no-op guard
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

    -- Skip no-op updates on itineraries when cover_image has nothing to delete or did not change
    -- (matches live cleanup-cloudinary v8, which inspects itineraries.cover_image only)
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

REVOKE ALL ON FUNCTION public.webhook_cleanup_cloudinary() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.webhook_cleanup_cloudinary() TO postgres, service_role;

-- 3. Atomic RPC #1: day-data, daily_locations, and POST/DELETE day AI review
CREATE OR REPLACE FUNCTION public.patch_trip_day_data_atomic(
    p_trip_id UUID,
    p_user_id TEXT,
    p_day INTEGER,
    p_patch JSONB,
    p_allow_creator_bypass BOOLEAN DEFAULT false
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_uid TEXT;
    v_day_key TEXT;
    v_patch JSONB;
    v_is_member BOOLEAN := false;
    v_is_owner BOOLEAN := false;
    v_created_by TEXT;
    v_raw_content JSONB;
    v_content JSONB;
    v_submap JSONB;
    v_existing_arr JSONB;
    v_submitted_raw JSONB;
    v_submitted_arr JSONB;
    v_hidden_foreign JSONB;
    v_normalized_submitted JSONB;
    v_day_val JSONB;
    v_review_val JSONB;
    v_field TEXT;
    v_dirty BOOLEAN := false;
BEGIN
    PERFORM set_config('lock_timeout', '3000ms', true);
    PERFORM set_config('statement_timeout', '8000ms', true);

    v_uid := btrim(COALESCE(p_user_id, ''));
    IF p_day IS NULL OR p_day < 0 THEN
        RAISE EXCEPTION 'Invalid day number: %', p_day USING ERRCODE = '22023';
    END IF;

    IF p_trip_id IS NULL THEN
        IF COALESCE(p_allow_creator_bypass, false) THEN
            RETURN jsonb_build_object('status', 'not_found');
        END IF;
        RETURN jsonb_build_object('status', 'forbidden');
    END IF;

    IF v_uid = '' THEN
        RETURN jsonb_build_object('status', 'forbidden');
    END IF;

    -- Dual-track authorization:
    -- - Standard member endpoints (day-data, location): 403-before-404 via trip_members first
    -- - Creator-bypass endpoints (POST/DELETE ai-review): 404-before-403 via itineraries lock first
    IF NOT COALESCE(p_allow_creator_bypass, false) THEN
        SELECT EXISTS (
            SELECT 1
              FROM public.trip_members
             WHERE itinerary_id = p_trip_id
               AND user_id::text = v_uid
        ) INTO v_is_member;

        IF NOT v_is_member THEN
            RETURN jsonb_build_object('status', 'forbidden');
        END IF;

        SELECT content, created_by::text
          INTO v_raw_content, v_created_by
          FROM public.itineraries
         WHERE id = p_trip_id
           FOR NO KEY UPDATE;

        IF NOT FOUND THEN
            RETURN jsonb_build_object('status', 'not_found');
        END IF;

        v_is_owner := COALESCE(btrim(COALESCE(v_created_by, '')) = v_uid, false);
    ELSE
        SELECT content, created_by::text
          INTO v_raw_content, v_created_by
          FROM public.itineraries
         WHERE id = p_trip_id
           FOR NO KEY UPDATE;

        IF NOT FOUND THEN
            RETURN jsonb_build_object('status', 'not_found');
        END IF;

        v_is_owner := COALESCE(btrim(COALESCE(v_created_by, '')) = v_uid, false);
        IF NOT v_is_owner THEN
            SELECT EXISTS (
                SELECT 1
                  FROM public.trip_members
                 WHERE itinerary_id = p_trip_id
                   AND user_id::text = v_uid
            ) INTO v_is_member;

            IF NOT v_is_member THEN
                RETURN jsonb_build_object('status', 'forbidden');
            END IF;
        END IF;
    END IF;

    v_patch := CASE
        WHEN p_patch IS NOT NULL AND jsonb_typeof(p_patch) = 'object' THEN p_patch
        ELSE '{}'::jsonb
    END;

    v_content := CASE
        WHEN v_raw_content IS NOT NULL AND jsonb_typeof(v_raw_content) = 'object' THEN v_raw_content
        ELSE '{}'::jsonb
    END;

    v_day_key := p_day::text;

    -- 1. day_notes (non-private per-day array/payload)
    IF v_patch ? 'day_notes' THEN
        v_submap := CASE
            WHEN v_content ? 'day_notes' AND jsonb_typeof(v_content->'day_notes') = 'object' THEN v_content->'day_notes'
            ELSE '{}'::jsonb
        END;
        v_day_val := CASE
            WHEN jsonb_typeof(v_patch->'day_notes') = 'object' AND (v_patch->'day_notes') ? v_day_key
                THEN (v_patch->'day_notes')->v_day_key
            ELSE '[]'::jsonb
        END;
        IF v_day_val IS NULL OR v_day_val = 'null'::jsonb THEN
            v_day_val := '[]'::jsonb;
        END IF;
        v_content := v_content || jsonb_build_object('day_notes', v_submap || jsonb_build_object(v_day_key, v_day_val));
        v_dirty := true;
    END IF;

    -- 2. Privacy-aware day array fields: day_costs, day_tickets, day_checklists
    FOREACH v_field IN ARRAY ARRAY['day_costs', 'day_tickets', 'day_checklists'] LOOP
        IF v_patch ? v_field THEN
            v_submap := CASE
                WHEN v_content ? v_field AND jsonb_typeof(v_content->v_field) = 'object' THEN v_content->v_field
                ELSE '{}'::jsonb
            END;
            v_existing_arr := CASE
                WHEN v_submap ? v_day_key AND jsonb_typeof(v_submap->v_day_key) = 'array' THEN v_submap->v_day_key
                ELSE '[]'::jsonb
            END;
            v_submitted_raw := CASE
                WHEN jsonb_typeof(v_patch->v_field) = 'object' AND (v_patch->v_field) ? v_day_key
                    THEN (v_patch->v_field)->v_day_key
                ELSE '[]'::jsonb
            END;
            v_submitted_arr := CASE
                WHEN v_submitted_raw IS NOT NULL AND jsonb_typeof(v_submitted_raw) = 'array' THEN v_submitted_raw
                ELSE '[]'::jsonb
            END;

            -- Preserve hidden foreign private items untouched (including legacy ownerless private items when caller is not owner)
            SELECT COALESCE(jsonb_agg(elem ORDER BY ord), '[]'::jsonb)
              INTO v_hidden_foreign
              FROM jsonb_array_elements(v_existing_arr) WITH ORDINALITY AS t(elem, ord)
             WHERE jsonb_typeof(elem) = 'object'
               AND jsonb_typeof(elem->'is_private') = 'boolean'
               AND (elem->'is_private') = 'true'::jsonb
               AND (
                   (btrim(COALESCE(elem->>'private_owner_id', '')) <> ''
                    AND btrim(COALESCE(elem->>'private_owner_id', '')) <> v_uid)
                   OR (btrim(COALESCE(elem->>'private_owner_id', '')) = ''
                       AND NOT v_is_owner)
               );

            -- Bind caller's private items to verified JWT v_uid; canonicalize non-boolean is_private to false; keep legacy strings intact
            SELECT COALESCE(
                jsonb_agg(
                    CASE
                        WHEN jsonb_typeof(elem) <> 'object' THEN elem
                        WHEN jsonb_typeof(elem->'is_private') = 'boolean' AND (elem->'is_private') = 'true'::jsonb
                            THEN elem || jsonb_build_object('is_private', true, 'private_owner_id', v_uid)
                        WHEN elem ? 'is_private'
                            THEN (elem - 'private_owner_id') || jsonb_build_object('is_private', false)
                        ELSE elem - 'private_owner_id'
                    END
                    ORDER BY ord
                ),
                '[]'::jsonb
            )
              INTO v_normalized_submitted
              FROM jsonb_array_elements(v_submitted_arr) WITH ORDINALITY AS t(elem, ord);

            v_content := v_content || jsonb_build_object(
                v_field,
                v_submap || jsonb_build_object(v_day_key, v_normalized_submitted || v_hidden_foreign)
            );
            v_dirty := true;
        END IF;
    END LOOP;

    -- 3. day_ai_reviews write
    IF v_patch ? 'day_ai_reviews' THEN
        v_submap := CASE
            WHEN v_content ? 'day_ai_reviews' AND jsonb_typeof(v_content->'day_ai_reviews') = 'object'
                THEN v_content->'day_ai_reviews'
            ELSE '{}'::jsonb
        END;
        v_review_val := CASE
            WHEN jsonb_typeof(v_patch->'day_ai_reviews') = 'object' AND (v_patch->'day_ai_reviews') ? v_day_key
                THEN (v_patch->'day_ai_reviews')->v_day_key
            ELSE '""'::jsonb
        END;
        IF v_review_val IS NULL OR v_review_val = 'null'::jsonb THEN
            v_review_val := '""'::jsonb;
        END IF;
        v_content := v_content || jsonb_build_object(
            'day_ai_reviews',
            v_submap || jsonb_build_object(v_day_key, v_review_val)
        );
        v_dirty := true;
    END IF;

    -- 4. delete_day_ai_review explicit key removal
    IF v_patch ? 'delete_day_ai_review'
       AND jsonb_typeof(v_patch->'delete_day_ai_review') = 'boolean'
       AND (v_patch->'delete_day_ai_review') = 'true'::jsonb THEN
        v_submap := CASE
            WHEN v_content ? 'day_ai_reviews' AND jsonb_typeof(v_content->'day_ai_reviews') = 'object'
                THEN v_content->'day_ai_reviews'
            ELSE '{}'::jsonb
        END;
        IF v_submap ? v_day_key THEN
            v_content := v_content || jsonb_build_object('day_ai_reviews', v_submap - v_day_key);
            v_dirty := true;
        END IF;
    END IF;

    -- 5. daily_locations single-day update
    IF v_patch ? 'daily_locations'
       AND jsonb_typeof(v_patch->'daily_locations') = 'object'
       AND (v_patch->'daily_locations') ? v_day_key THEN
        v_submap := CASE
            WHEN v_content ? 'daily_locations' AND jsonb_typeof(v_content->'daily_locations') = 'object'
                THEN v_content->'daily_locations'
            ELSE '{}'::jsonb
        END;
        v_content := v_content || jsonb_build_object(
            'daily_locations',
            v_submap || jsonb_build_object(v_day_key, (v_patch->'daily_locations')->v_day_key)
        );
        v_dirty := true;
    END IF;

    IF v_dirty THEN
        UPDATE public.itineraries
           SET content = v_content
         WHERE id = p_trip_id;
    END IF;

    RETURN jsonb_build_object('status', 'ok');
END;
$function$;

REVOKE ALL ON FUNCTION public.patch_trip_day_data_atomic(UUID, TEXT, INTEGER, JSONB, BOOLEAN) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.patch_trip_day_data_atomic(UUID, TEXT, INTEGER, JSONB, BOOLEAN) TO service_role;

-- 4. Atomic RPC #2: trip info (credit_cards with 5 ownership invariants, flight_info, hotel_info)
CREATE OR REPLACE FUNCTION public.patch_trip_info_atomic(
    p_trip_id UUID,
    p_user_id TEXT,
    p_patch JSONB
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_uid TEXT;
    v_patch JSONB;
    v_is_member BOOLEAN := false;
    v_is_owner BOOLEAN := false;
    v_created_by TEXT;
    v_raw_content JSONB;
    v_content JSONB;
    v_flight_col JSONB;
    v_hotel_col JSONB;
    v_has_flight BOOLEAN := false;
    v_has_hotel BOOLEAN := false;
    v_has_cards BOOLEAN := false;
    v_existing_cards JSONB;
    v_submitted_cards JSONB;
    v_hidden_cards JSONB := '[]'::jsonb;
    v_hidden_ids TEXT[] := ARRAY[]::TEXT[];
    v_seen_ids TEXT[] := ARRAY[]::TEXT[];
    v_visible_by_id JSONB := '{}'::jsonb;
    v_norm_cards JSONB := '[]'::jsonb;
    v_card JSONB;
    v_cleaned JSONB;
    v_prev_card JSONB;
    v_cid TEXT;
    v_new_id TEXT;
    v_card_creator TEXT;
    v_prev_creator TEXT;
    v_is_card_public BOOLEAN;
    v_submitted_is_public BOOLEAN;
    v_is_card_visible BOOLEAN;
    v_caller_owns_prev BOOLEAN;
BEGIN
    PERFORM set_config('lock_timeout', '3000ms', true);
    PERFORM set_config('statement_timeout', '8000ms', true);

    v_uid := btrim(COALESCE(p_user_id, ''));
    IF p_trip_id IS NULL OR v_uid = '' THEN
        RETURN jsonb_build_object('status', 'forbidden');
    END IF;

    -- 403-before-404: verify membership first
    SELECT EXISTS (
        SELECT 1
          FROM public.trip_members
         WHERE itinerary_id = p_trip_id
           AND user_id::text = v_uid
    ) INTO v_is_member;

    IF NOT v_is_member THEN
        RETURN jsonb_build_object('status', 'forbidden');
    END IF;

    SELECT content, flight_info, hotel_info, created_by::text
      INTO v_raw_content, v_flight_col, v_hotel_col, v_created_by
      FROM public.itineraries
     WHERE id = p_trip_id
       FOR NO KEY UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'not_found');
    END IF;

    v_is_owner := COALESCE(btrim(COALESCE(v_created_by, '')) = v_uid, false);

    v_patch := CASE
        WHEN p_patch IS NOT NULL AND jsonb_typeof(p_patch) = 'object' THEN p_patch
        ELSE '{}'::jsonb
    END;

    v_content := CASE
        WHEN v_raw_content IS NOT NULL AND jsonb_typeof(v_raw_content) = 'object' THEN v_raw_content
        ELSE '{}'::jsonb
    END;

    -- 1. Credit cards merge enforcing all 5 security & ownership invariants + mem_* restoration
    IF v_patch ? 'credit_cards' THEN
        v_has_cards := true;
        v_existing_cards := CASE
            WHEN v_content ? 'credit_cards' AND jsonb_typeof(v_content->'credit_cards') = 'array'
                THEN v_content->'credit_cards'
            ELSE '[]'::jsonb
        END;
        v_submitted_cards := CASE
            WHEN jsonb_typeof(v_patch->'credit_cards') = 'array' THEN v_patch->'credit_cards'
            ELSE '[]'::jsonb
        END;

        -- Partition existing cards into visible_by_id vs hidden_foreign_cards
        FOR v_card IN
            SELECT elem
              FROM jsonb_array_elements(v_existing_cards) WITH ORDINALITY AS t(elem, ord)
             ORDER BY ord
        LOOP
            IF jsonb_typeof(v_card) <> 'object' THEN
                v_is_card_visible := true;
            ELSE
                v_is_card_public := (
                    jsonb_typeof(v_card->'is_public') = 'boolean'
                    AND (v_card->'is_public') = 'true'::jsonb
                );
                IF v_is_card_public THEN
                    v_is_card_visible := true;
                ELSE
                    v_card_creator := btrim(COALESCE(v_card->>'creator_id', ''));
                    IF v_card_creator <> '' THEN
                        v_is_card_visible := (v_card_creator = v_uid);
                    ELSE
                        v_is_card_visible := v_is_owner;
                    END IF;
                END IF;
            END IF;

            IF v_is_card_visible THEN
                IF jsonb_typeof(v_card) = 'object' THEN
                    v_cid := btrim(COALESCE(v_card->>'id', ''));
                    IF v_cid <> '' THEN
                        v_visible_by_id := v_visible_by_id || jsonb_build_object(v_cid, v_card);
                    END IF;
                END IF;
            ELSE
                v_hidden_cards := v_hidden_cards || jsonb_build_array(v_card);
                IF jsonb_typeof(v_card) = 'object' THEN
                    v_cid := btrim(COALESCE(v_card->>'id', ''));
                    IF v_cid <> '' THEN
                        v_hidden_ids := array_append(v_hidden_ids, v_cid);
                    END IF;
                END IF;
            END IF;
        END LOOP;

        -- Normalize submitted cards under the 5 invariants
        FOR v_card IN
            SELECT elem
              FROM jsonb_array_elements(v_submitted_cards) WITH ORDINALITY AS t(elem, ord)
             ORDER BY ord
        LOOP
            IF jsonb_typeof(v_card) <> 'object' THEN
                v_norm_cards := v_norm_cards || jsonb_build_array(v_card);
                CONTINUE;
            END IF;

            v_cleaned := v_card;
            v_cid := btrim(COALESCE(v_cleaned->>'id', ''));

            -- Invariant 1: Block hidden private card ID collision / oracle AND duplicate submitted IDs
            IF v_cid <> '' AND (v_cid = ANY(v_hidden_ids) OR v_cid = ANY(v_seen_ids)) THEN
                v_new_id := gen_random_uuid()::text;
                v_cleaned := v_cleaned || jsonb_build_object('id', v_new_id);
                v_seen_ids := array_append(v_seen_ids, v_new_id);
                v_prev_card := NULL;
            ELSIF v_cid <> '' THEN
                v_seen_ids := array_append(v_seen_ids, v_cid);
                IF v_visible_by_id ? v_cid THEN
                    v_prev_card := v_visible_by_id->v_cid;
                ELSE
                    v_prev_card := NULL;
                END IF;
            ELSE
                v_prev_card := NULL;
            END IF;

            -- Canonicalize submitted is_public strictly as JSON boolean (prevents SQL/Python truthiness desync)
            v_submitted_is_public := (
                jsonb_typeof(v_cleaned->'is_public') = 'boolean'
                AND (v_cleaned->'is_public') = 'true'::jsonb
            );

            -- Invariants 2-5: Creator binding, mem_* restoration, anti-hijack, anti-privatization
            IF v_prev_card IS NULL THEN
                v_cleaned := v_cleaned || jsonb_build_object('creator_id', v_uid, 'is_public', v_submitted_is_public);
            ELSE
                v_prev_creator := btrim(COALESCE(v_prev_card->>'creator_id', ''));
                v_caller_owns_prev := (v_prev_creator = v_uid) OR (v_prev_creator = '' AND v_is_owner);
                IF v_caller_owns_prev THEN
                    v_cleaned := v_cleaned || jsonb_build_object('creator_id', v_uid, 'is_public', v_submitted_is_public);
                ELSE
                    -- Lock original creator_id (restoring masked mem_* or preserving '' on legacy ownerless card)
                    -- and force is_public=true to block non-creator privatization/theft
                    v_cleaned := v_cleaned || jsonb_build_object('creator_id', v_prev_creator, 'is_public', true);
                END IF;
            END IF;

            v_norm_cards := v_norm_cards || jsonb_build_array(v_cleaned);
        END LOOP;

        v_content := v_content || jsonb_build_object('credit_cards', v_norm_cards || v_hidden_cards);
    END IF;

    -- 2. flight_info (explicit JSON null -> SQL NULL on top-level column, 'null'::jsonb inside content)
    IF v_patch ? 'flight_info' THEN
        v_has_flight := true;
        IF (v_patch->'flight_info') IS NULL OR (v_patch->'flight_info') = 'null'::jsonb THEN
            v_flight_col := NULL;
            v_content := v_content || jsonb_build_object('flight_info', 'null'::jsonb);
        ELSE
            v_flight_col := v_patch->'flight_info';
            v_content := v_content || jsonb_build_object('flight_info', v_patch->'flight_info');
        END IF;
    END IF;

    -- 3. hotel_info (explicit JSON null -> SQL NULL on top-level column, 'null'::jsonb inside content)
    IF v_patch ? 'hotel_info' THEN
        v_has_hotel := true;
        IF (v_patch->'hotel_info') IS NULL OR (v_patch->'hotel_info') = 'null'::jsonb THEN
            v_hotel_col := NULL;
            v_content := v_content || jsonb_build_object('hotel_info', 'null'::jsonb);
        ELSE
            v_hotel_col := v_patch->'hotel_info';
            v_content := v_content || jsonb_build_object('hotel_info', v_patch->'hotel_info');
        END IF;
    END IF;

    IF v_has_cards OR v_has_flight OR v_has_hotel THEN
        UPDATE public.itineraries
           SET content = v_content,
               flight_info = CASE WHEN v_has_flight THEN v_flight_col ELSE flight_info END,
               hotel_info = CASE WHEN v_has_hotel THEN v_hotel_col ELSE hotel_info END
         WHERE id = p_trip_id;
    END IF;

    RETURN jsonb_build_object('status', 'ok');
END;
$function$;

REVOKE ALL ON FUNCTION public.patch_trip_info_atomic(UUID, TEXT, JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.patch_trip_info_atomic(UUID, TEXT, JSONB) TO service_role;

-- 5. Atomic RPC #3: import-to-trip content merge + in-lock non-shrinking end_date extension
CREATE OR REPLACE FUNCTION public.merge_trip_import_content_atomic(
    p_trip_id UUID,
    p_user_id TEXT,
    p_patch JSONB,
    p_max_imported_day INTEGER DEFAULT NULL,
    p_fallback_start_date DATE DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_uid TEXT;
    v_patch JSONB;
    v_is_owner BOOLEAN := false;
    v_is_member BOOLEAN := false;
    v_created_by TEXT;
    v_raw_content JSONB;
    v_content JSONB;
    v_raw_start_text TEXT;
    v_raw_end_text TEXT;
    v_existing_start DATE;
    v_existing_end DATE;
    v_effective_start DATE;
    v_candidate_end DATE;
    v_next_start_date DATE;
    v_next_end_date DATE;
    v_set_start BOOLEAN := false;
    v_set_end BOOLEAN := false;
    v_submap JSONB;
    v_existing_locs JSONB;
    v_sanitized_arr JSONB;
    v_field TEXT;
    v_k TEXT;
    v_val JSONB;
BEGIN
    PERFORM set_config('lock_timeout', '3000ms', true);
    PERFORM set_config('statement_timeout', '8000ms', true);

    v_uid := btrim(COALESCE(p_user_id, ''));
    IF p_trip_id IS NULL THEN
        RETURN jsonb_build_object('status', 'not_found');
    END IF;
    IF v_uid = '' THEN
        RETURN jsonb_build_object('status', 'forbidden');
    END IF;

    -- 404-before-403 matching import_to_trip contract (creator or member)
    SELECT content, created_by::text, start_date::text, end_date::text
      INTO v_raw_content, v_created_by, v_raw_start_text, v_raw_end_text
      FROM public.itineraries
     WHERE id = p_trip_id
       FOR NO KEY UPDATE;

    IF NOT FOUND THEN
        RETURN jsonb_build_object('status', 'not_found');
    END IF;

    v_is_owner := COALESCE(btrim(COALESCE(v_created_by, '')) = v_uid, false);
    IF NOT v_is_owner THEN
        SELECT EXISTS (
            SELECT 1
              FROM public.trip_members
             WHERE itinerary_id = p_trip_id
               AND user_id::text = v_uid
        ) INTO v_is_member;

        IF NOT v_is_member THEN
            RETURN jsonb_build_object('status', 'forbidden');
        END IF;
    END IF;

    v_patch := CASE
        WHEN p_patch IS NOT NULL AND jsonb_typeof(p_patch) = 'object' THEN p_patch
        ELSE '{}'::jsonb
    END;

    v_content := CASE
        WHEN v_raw_content IS NOT NULL AND jsonb_typeof(v_raw_content) = 'object' THEN v_raw_content
        ELSE '{}'::jsonb
    END;

    -- 1. Append merge day_notes
    IF v_patch ? 'day_notes' AND jsonb_typeof(v_patch->'day_notes') = 'object' THEN
        v_submap := CASE
            WHEN v_content ? 'day_notes' AND jsonb_typeof(v_content->'day_notes') = 'object'
                THEN v_content->'day_notes'
            ELSE '{}'::jsonb
        END;
        FOR v_k, v_val IN SELECT key, value FROM jsonb_each(v_patch->'day_notes') LOOP
            IF v_val IS NULL OR v_val = 'null'::jsonb THEN
                CONTINUE;
            END IF;
            IF v_submap ? v_k AND jsonb_typeof(v_submap->v_k) = 'array' THEN
                IF jsonb_typeof(v_val) = 'array' THEN
                    v_submap := v_submap || jsonb_build_object(v_k, (v_submap->v_k) || v_val);
                END IF;
                -- Never overwrite an existing day_notes array with a non-array payload
            ELSE
                v_submap := v_submap || jsonb_build_object(v_k, v_val);
            END IF;
        END LOOP;
        v_content := v_content || jsonb_build_object('day_notes', v_submap);
    END IF;

    -- 2. Append merge privacy-sanitized day_costs, day_tickets, day_checklists
    FOREACH v_field IN ARRAY ARRAY['day_costs', 'day_tickets', 'day_checklists'] LOOP
        IF v_patch ? v_field AND jsonb_typeof(v_patch->v_field) = 'object' THEN
            v_submap := CASE
                WHEN v_content ? v_field AND jsonb_typeof(v_content->v_field) = 'object'
                    THEN v_content->v_field
                ELSE '{}'::jsonb
            END;
            FOR v_k, v_val IN SELECT key, value FROM jsonb_each(v_patch->v_field) LOOP
                -- Only accept arrays for privacy-bearing day lists; never allow non-array payloads to wipe hidden private items
                IF jsonb_typeof(v_val) = 'array' THEN
                    SELECT COALESCE(
                        jsonb_agg(
                            CASE
                                WHEN jsonb_typeof(elem) <> 'object' THEN elem
                                WHEN jsonb_typeof(elem->'is_private') = 'boolean' AND (elem->'is_private') = 'true'::jsonb
                                    THEN elem || jsonb_build_object('is_private', true, 'private_owner_id', v_uid)
                                WHEN elem ? 'is_private'
                                    THEN (elem - 'private_owner_id') || jsonb_build_object('is_private', false)
                                ELSE elem - 'private_owner_id'
                            END
                            ORDER BY ord
                        ),
                        '[]'::jsonb
                    )
                      INTO v_sanitized_arr
                      FROM jsonb_array_elements(v_val) WITH ORDINALITY AS t(elem, ord);

                    IF v_submap ? v_k AND jsonb_typeof(v_submap->v_k) = 'array' THEN
                        v_submap := v_submap || jsonb_build_object(v_k, (v_submap->v_k) || v_sanitized_arr);
                    ELSE
                        v_submap := v_submap || jsonb_build_object(v_k, v_sanitized_arr);
                    END IF;
                END IF;
            END LOOP;
            v_content := v_content || jsonb_build_object(v_field, v_submap);
        END IF;
    END LOOP;

    -- 3. Merge ai_review when non-empty
    IF v_patch ? 'ai_review'
       AND (v_patch->'ai_review') IS NOT NULL
       AND (v_patch->'ai_review') <> 'null'::jsonb
       AND btrim(COALESCE(v_patch->>'ai_review', '')) <> '' THEN
        v_content := v_content || jsonb_build_object('ai_review', v_patch->'ai_review');
    END IF;

    -- 4. Merge daily_locations with existing-wins precedence: imported || existing
    IF v_patch ? 'daily_locations' AND jsonb_typeof(v_patch->'daily_locations') = 'object' THEN
        v_existing_locs := CASE
            WHEN v_content ? 'daily_locations' AND jsonb_typeof(v_content->'daily_locations') = 'object'
                THEN v_content->'daily_locations'
            ELSE '{}'::jsonb
        END;
        v_content := v_content || jsonb_build_object(
            'daily_locations',
            (v_patch->'daily_locations') || v_existing_locs
        );
    END IF;

    -- 5. In-lock start_date backfill & strictly non-shrinking end_date extension
    IF p_max_imported_day IS NOT NULL AND p_max_imported_day > 0 THEN
        BEGIN
            v_existing_start := NULLIF(btrim(split_part(COALESCE(v_raw_start_text, ''), 'T', 1)), '')::date;
        EXCEPTION
            WHEN OTHERS THEN
                v_existing_start := NULL;
        END;

        BEGIN
            v_existing_end := NULLIF(btrim(split_part(COALESCE(v_raw_end_text, ''), 'T', 1)), '')::date;
        EXCEPTION
            WHEN OTHERS THEN
                v_existing_end := NULL;
        END;

        IF v_existing_start IS NULL AND p_fallback_start_date IS NOT NULL THEN
            v_next_start_date := p_fallback_start_date;
            v_set_start := true;
        END IF;

        v_effective_start := COALESCE(v_existing_start, p_fallback_start_date);
        IF v_effective_start IS NOT NULL THEN
            v_candidate_end := v_effective_start + (p_max_imported_day - 1);
            IF v_existing_end IS NULL THEN
                IF p_max_imported_day > 1 THEN
                    v_next_end_date := v_candidate_end;
                    v_set_end := true;
                END IF;
            ELSIF v_candidate_end > v_existing_end THEN
                v_next_end_date := v_candidate_end;
                v_set_end := true;
            END IF;
        END IF;
    END IF;

    -- Direct assignment branches avoid CASE type mismatch whether start_date/end_date are DATE or TEXT
    IF v_set_start AND v_set_end THEN
        UPDATE public.itineraries
           SET content = v_content,
               start_date = v_next_start_date,
               end_date = v_next_end_date
         WHERE id = p_trip_id;
    ELSIF v_set_start THEN
        UPDATE public.itineraries
           SET content = v_content,
               start_date = v_next_start_date
         WHERE id = p_trip_id;
    ELSIF v_set_end THEN
        UPDATE public.itineraries
           SET content = v_content,
               end_date = v_next_end_date
         WHERE id = p_trip_id;
    ELSE
        UPDATE public.itineraries
           SET content = v_content
         WHERE id = p_trip_id;
    END IF;

    RETURN jsonb_build_object('status', 'ok', 'is_owner', v_is_owner);
END;
$function$;

REVOKE ALL ON FUNCTION public.merge_trip_import_content_atomic(UUID, TEXT, JSONB, INTEGER, DATE) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.merge_trip_import_content_atomic(UUID, TEXT, JSONB, INTEGER, DATE) TO service_role;
