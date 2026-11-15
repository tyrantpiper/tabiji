-- Replace broken/unset app.settings.service_role_key webhook auth in
-- public.webhook_cleanup_cloudinary() with Postgres-native Vault HMAC-SHA256
-- verification and pin search_path / EXECUTE privileges to satisfy Supabase
-- security advisors (0011, 0028, 0029) without committing any secret literals.

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM vault.secrets WHERE name = 'cleanup_webhook_secret'
  ) THEN
    PERFORM vault.create_secret(
      encode(extensions.gen_random_bytes(32), 'hex'),
      'cleanup_webhook_secret',
      'Internal HMAC-SHA256 secret for pg_net cleanup-cloudinary database webhook'
    );
  END IF;
END
$$;

CREATE OR REPLACE FUNCTION public.verify_cleanup_webhook_signature(
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
   WHERE name = 'cleanup_webhook_secret'
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

REVOKE ALL ON FUNCTION public.verify_cleanup_webhook_signature(bigint, text, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.verify_cleanup_webhook_signature(bigint, text, text) TO service_role;

CREATE OR REPLACE FUNCTION public.webhook_cleanup_cloudinary()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, vault, extensions, pg_temp
AS $function$
DECLARE
  v_payload jsonb;
  v_headers jsonb;
  v_hmac_secret text;
  v_ts bigint;
  v_sig text;
  v_legacy_srk text;
BEGIN
  v_payload := jsonb_build_object(
    'old_record', row_to_json(OLD),
    'new_record', CASE WHEN TG_OP = 'UPDATE' THEN row_to_json(NEW) ELSE null END,
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
