"""
Security Sentinel In-Memory Verification Suite for POST /api/sign-cloudinary
============================================================================
Verifies:
1. Mantis Block G Benign Controls (all legitimate upload folders, streetview public_id,
   atomic {signature, apiKey, cloudName}, Cache-Control: no-store, CLOUDINARY_URL fallback,
   and FastAPI dependency_overrides[get_verified_user] compatibility).
2. Mandatory JWT authentication (401 on missing/forged/expired tokens, zero BYOK trigger keywords).
3. public_id overwrite protection (restricted solely to ryan_travel/streetview with ^mly_[0-9A-Za-z_-]{1,64}$).
4. Parameter allowlist, folder allowlist/traversal/delimiter/newline smuggling rejection.
5. Timestamp skew (±600s, blocking year-2050 pre-signing), bool/float/Unicode-digit rejection.
6. Per-user SlowAPI rate limit (60/min keyed strictly by uid) immune to X-Gemini-API-Key,
   CF-Connecting-IP, and leftmost X-Forwarded-For spoofing (CWE-290).
7. Pre-auth rightmost-XFF IP rate limit executing strictly BEFORE get_verified_user()
   to protect supabase.auth.get_user() fallback from unauthenticated floods.
"""

import asyncio
import hashlib
import json
import time
import uuid
from unittest.mock import MagicMock

import jwt
import pytest
from fastapi.testclient import TestClient

from main import app
import routers.cloudinary as cloudinary_router
from routers.cloudinary import __reset_cloudinary_sign_rate_limits_for_testing
from utils.deps import get_supabase, get_verified_user
from utils.limiter import limiter

TEST_SESSION_SECRET = "test-session-secret-cloudinary-sign-sentinel-2026-32b"
TEST_CLOUD_NAME = "demo_cloud_sandbox"
TEST_API_KEY = "111122223333444"
TEST_API_SECRET = "synthetic_test_secret_not_prod_xyz"
BYOK_TRIGGER_WORDS = ("gemini", "api key", "金鑰")


def _mint_session_jwt(
    user_id: str,
    *,
    secret: str = TEST_SESSION_SECRET,
    exp_offset: int = 3600,
    issuer: str = "tabiji-core",
    token_type: str = "device_session",
) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iss": issuer,
        "iat": now,
        "exp": now + exp_offset,
        "type": token_type,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _expected_sha1(params: dict, secret: str) -> str:
    canonical = "&".join(f"{k}={params[k]}" for k in sorted(params.keys()))
    return hashlib.sha1(f"{canonical}{secret}".encode("utf-8")).hexdigest()


@pytest.fixture(autouse=True)
def _isolated_cloudinary_env(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET_KEY", TEST_SESSION_SECRET)
    monkeypatch.setenv("CLOUDINARY_CLOUD_NAME", TEST_CLOUD_NAME)
    monkeypatch.setenv("CLOUDINARY_API_KEY", TEST_API_KEY)
    monkeypatch.setenv("CLOUDINARY_API_SECRET", TEST_API_SECRET)
    monkeypatch.delenv("CLOUDINARY_URL", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_CLOUDINARY_API_KEY", raising=False)

    prev_enabled = limiter.enabled
    limiter.enabled = True
    __reset_cloudinary_sign_rate_limits_for_testing()
    try:
        yield
    finally:
        __reset_cloudinary_sign_rate_limits_for_testing()
        limiter.enabled = prev_enabled
        app.dependency_overrides.pop(get_verified_user, None)
        app.dependency_overrides.pop(get_supabase, None)


# =====================================================================
# Mantis Block G: Benign Control Tests
# =====================================================================


def test_benign_valid_folders_and_sha1_signature_contract():
    client = TestClient(app)
    uid = str(uuid.uuid4())
    token = _mint_session_jwt(uid)
    now_ts = int(time.time())

    legitimate_folders = [
        "ryan_travel",
        "ryan_travel/covers",
        "ryan_travel/spots",
        "ryan_travel/hotels",
        "ryan_travel/avatars",
        f"ryan_travel/receipts/{uid}",
        "tabidachi_capsules",
        "trip_covers",
        "receipts",
    ]

    for folder in legitimate_folders:
        resp = client.post(
            "/api/sign-cloudinary",
            headers={"Authorization": f"Bearer {token}"},
            json={"paramsToSign": {"timestamp": now_ts, "folder": folder}},
        )
        assert resp.status_code == 200, f"folder={folder} failed: {resp.text}"
        assert resp.headers.get("cache-control") == "no-store"
        data = resp.json()
        assert data == {
            "signature": _expected_sha1({"timestamp": now_ts, "folder": folder}, TEST_API_SECRET),
            "apiKey": TEST_API_KEY,
            "cloudName": TEST_CLOUD_NAME,
        }
        assert TEST_API_SECRET not in resp.text


def test_benign_streetview_public_id_and_string_timestamp():
    client = TestClient(app)
    token = _mint_session_jwt(str(uuid.uuid4()))
    now_ts = int(time.time())

    resp = client.post(
        "/api/sign-cloudinary",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "paramsToSign": {
                "timestamp": str(now_ts),
                "folder": "ryan_travel/streetview",
                "public_id": "mly_1414593269762424",
            }
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    expected = _expected_sha1(
        {
            "timestamp": now_ts,
            "folder": "ryan_travel/streetview",
            "public_id": "mly_1414593269762424",
        },
        TEST_API_SECRET,
    )
    assert data["signature"] == expected
    assert data["apiKey"] == TEST_API_KEY
    assert data["cloudName"] == TEST_CLOUD_NAME


def test_benign_cloudinary_url_fallback_and_whitespace_stripping(monkeypatch):
    monkeypatch.delenv("CLOUDINARY_CLOUD_NAME", raising=False)
    monkeypatch.delenv("CLOUDINARY_API_KEY", raising=False)
    monkeypatch.delenv("CLOUDINARY_API_SECRET", raising=False)
    monkeypatch.setenv(
        "CLOUDINARY_URL",
        "  cloudinary://555666777:fallback_secret_trimmed@fallback_cloud \r\n",
    )

    client = TestClient(app)
    token = _mint_session_jwt(str(uuid.uuid4()))
    now_ts = int(time.time())

    resp = client.post(
        "/api/sign-cloudinary",
        headers={"Authorization": f"Bearer {token}"},
        json={"paramsToSign": {"timestamp": now_ts, "folder": "tabidachi_capsules"}},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["cloudName"] == "fallback_cloud"
    assert data["apiKey"] == "555666777"
    assert data["signature"] == _expected_sha1(
        {"timestamp": now_ts, "folder": "tabidachi_capsules"},
        "fallback_secret_trimmed",
    )


def test_benign_dependency_override_get_verified_user_preserved():
    override_uid = str(uuid.uuid4())
    app.dependency_overrides[get_verified_user] = lambda: override_uid

    client = TestClient(app)
    now_ts = int(time.time())
    resp = client.post(
        "/api/sign-cloudinary",
        json={"paramsToSign": {"timestamp": now_ts, "folder": "ryan_travel/covers"}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["apiKey"] == TEST_API_KEY


# =====================================================================
# Adversarial Security Tests
# =====================================================================


def test_attack_unauthenticated_and_forged_jwt_rejected_401():
    client = TestClient(app)
    now_ts = int(time.time())
    payload = {"paramsToSign": {"timestamp": now_ts, "folder": "ryan_travel/covers"}}

    # 1. Missing Authorization
    res_missing = client.post("/api/sign-cloudinary", json=payload)
    assert res_missing.status_code == 401
    detail_missing = str(res_missing.json().get("detail", "")).lower()
    for word in BYOK_TRIGGER_WORDS:
        assert word not in detail_missing

    # 2. Forged JWT signed with attacker secret
    forged_jwt = _mint_session_jwt(
        str(uuid.uuid4()),
        secret="attacker-forged-secret-of-at-least-32-bytes",
    )
    res_forged = client.post(
        "/api/sign-cloudinary",
        headers={"Authorization": f"Bearer {forged_jwt}"},
        json=payload,
    )
    assert res_forged.status_code == 401
    detail_forged = str(res_forged.json().get("detail", "")).lower()
    for word in BYOK_TRIGGER_WORDS:
        assert word not in detail_forged

    # 3. Expired JWT
    expired_jwt = _mint_session_jwt(str(uuid.uuid4()), exp_offset=-120)
    res_expired = client.post(
        "/api/sign-cloudinary",
        headers={"Authorization": f"Bearer {expired_jwt}"},
        json=payload,
    )
    assert res_expired.status_code == 401
    detail_expired = str(res_expired.json().get("detail", "")).lower()
    for word in BYOK_TRIGGER_WORDS:
        assert word not in detail_expired


def test_attack_public_id_overwrite_protection():
    client = TestClient(app)
    token = _mint_session_jwt(str(uuid.uuid4()))
    now_ts = int(time.time())
    headers = {"Authorization": f"Bearer {token}"}

    # public_id forbidden on every non-streetview folder (prevents overwriting victim assets)
    disallowed_folders = [
        "ryan_travel",
        "ryan_travel/avatars",
        "ryan_travel/covers",
        "ryan_travel/spots",
        "ryan_travel/receipts/victim-uid",
        "tabidachi_capsules",
        "trip_covers",
        "receipts",
    ]
    for folder in disallowed_folders:
        resp = client.post(
            "/api/sign-cloudinary",
            headers=headers,
            json={"paramsToSign": {"timestamp": now_ts, "folder": folder, "public_id": "mly_12345"}},
        )
        assert resp.status_code == 400, f"public_id unexpectedly accepted for folder={folder}"

    # Invalid public_id formats even inside ryan_travel/streetview
    bad_public_ids = [
        "victim_avatar_123",
        "mly_",
        "mly_../other",
        "mly_123/456",
        "mly_123&overwrite=true",
        "mly_123\n",
        "mly_" + ("a" * 65),
        None,
        12345,
    ]
    for bad_pid in bad_public_ids:
        resp = client.post(
            "/api/sign-cloudinary",
            headers=headers,
            json={
                "paramsToSign": {
                    "timestamp": now_ts,
                    "folder": "ryan_travel/streetview",
                    "public_id": bad_pid,
                }
            },
        )
        assert resp.status_code == 400, f"Bad public_id unexpectedly accepted: {bad_pid!r}"


def test_attack_parameter_injection_and_folder_smuggling():
    client = TestClient(app)
    token = _mint_session_jwt(str(uuid.uuid4()))
    now_ts = int(time.time())
    headers = {"Authorization": f"Bearer {token}"}

    # Unauthorized signing parameter keys
    for extra_key, extra_val in [
        ("overwrite", True),
        ("invalidate", True),
        ("eager", "w_100"),
        ("transformation", "c_scale,w_500"),
        ("upload_preset", "unsigned_preset"),
        ("notification_url", "https://evil.example/hook"),
        ("callback", "https://evil.example/cb"),
    ]:
        resp = client.post(
            "/api/sign-cloudinary",
            headers=headers,
            json={"paramsToSign": {"timestamp": now_ts, "folder": "ryan_travel/covers", extra_key: extra_val}},
        )
        assert resp.status_code == 400, f"Extra key {extra_key} unexpectedly accepted"

    # Malicious / malformed folders
    bad_folders = [
        None,
        "",
        "attacker_bucket",
        "ryan_travel_evil",
        "ryan_travel/../evil",
        "ryan_travel\\covers",
        "ryan_travel/covers&overwrite=true",
        "ryan_travel/covers?x=1",
        "ryan_travel/covers\n",
        "ryan_travel//covers",
        "/ryan_travel/covers",
        "ryan_travel/covers/",
        "ryan_travel/" + ("a" * 160),
    ]
    for folder in bad_folders:
        resp = client.post(
            "/api/sign-cloudinary",
            headers=headers,
            json={"paramsToSign": {"timestamp": now_ts, "folder": folder}},
        )
        assert resp.status_code == 400, f"Bad folder unexpectedly accepted: {folder!r}"

    # Malformed payloads
    assert client.post("/api/sign-cloudinary", headers=headers, json={}).status_code == 400
    assert client.post("/api/sign-cloudinary", headers=headers, json={"paramsToSign": {}}).status_code == 400
    assert client.post("/api/sign-cloudinary", headers=headers, json={"paramsToSign": []}).status_code == 400
    assert client.post(
        "/api/sign-cloudinary",
        headers={**headers, "Content-Type": "application/json"},
        content=b"not-valid-json",
    ).status_code == 400


def test_attack_timestamp_skew_bool_float_and_unicode_digits(monkeypatch):
    client = TestClient(app)
    now_ts = int(time.time())
    monkeypatch.setattr(cloudinary_router.time, "time", lambda: float(now_ts))
    token = _mint_session_jwt(str(uuid.uuid4()))
    headers = {"Authorization": f"Bearer {token}"}

    bad_timestamps = [
        2524608000,           # Year 2050 pre-signed token
        now_ts + 601,         # Just beyond +600s skew
        now_ts - 601,         # Just beyond -600s skew
        0,
        -100,
        True,                 # Python bool is subclass of int
        False,
        float(now_ts) + 0.5,  # Fractional float
        float(now_ts),        # Exact float
        "١٧٠٠٠٠٠٠٠٠",          # Non-ASCII Unicode digits
        f"{now_ts}\n",        # Trailing newline
        None,
    ]
    for bad_ts in bad_timestamps:
        resp = client.post(
            "/api/sign-cloudinary",
            headers=headers,
            json={"paramsToSign": {"timestamp": bad_ts, "folder": "ryan_travel/covers"}},
        )
        assert resp.status_code == 400, f"Bad timestamp unexpectedly accepted: {bad_ts!r}"

    # Exact boundary acceptance within ±600s (deterministic under frozen wall clock)
    for ok_ts in (now_ts - 600, now_ts + 600):
        resp = client.post(
            "/api/sign-cloudinary",
            headers=headers,
            json={"paramsToSign": {"timestamp": ok_ts, "folder": "ryan_travel/covers"}},
        )
        assert resp.status_code == 200, f"Valid boundary timestamp rejected: {ok_ts}"


def test_attack_per_user_rate_limit_immune_to_header_spoofing():
    client = TestClient(app)
    uid_a = str(uuid.uuid4())
    uid_b = str(uuid.uuid4())
    token_a = _mint_session_jwt(uid_a)
    token_b = _mint_session_jwt(uid_b)
    now_ts = int(time.time())

    # User A exhausts 60/min limit while rotating spoofable headers every single request
    for i in range(60):
        resp = client.post(
            "/api/sign-cloudinary",
            headers={
                "Authorization": f"Bearer {token_a}",
                "X-Gemini-API-Key": f"spoof-rotate-key-{i:04d}-1234567890123456789",
                "X-Gemini-Key": f"spoof-alt-key-{i:04d}-123456789012345678901",
                "CF-Connecting-IP": f"198.51.100.{(i % 250) + 1}",
                "X-Forwarded-For": f"203.0.113.{(i % 250) + 1}, 35.190.1.10",
            },
            json={"paramsToSign": {"timestamp": now_ts, "folder": "ryan_travel/covers"}},
        )
        assert resp.status_code == 200, f"Request {i + 1}/60 unexpectedly failed: {resp.status_code}"

    # 61st request from User A MUST hit 429 even with brand new spoofed headers,
    # while preserving outermost CORS headers for trusted origins.
    blocked = client.post(
        "/api/sign-cloudinary",
        headers={
            "Authorization": f"Bearer {token_a}",
            "Origin": "https://www.tabijiapp.com",
            "X-Gemini-API-Key": "spoof-brand-new-key-9999999999999999",
            "CF-Connecting-IP": "192.0.2.200",
            "X-Forwarded-For": "192.0.2.201, 35.190.1.10",
        },
        json={"paramsToSign": {"timestamp": now_ts, "folder": "ryan_travel/covers"}},
    )
    assert blocked.status_code == 429
    assert blocked.headers.get("access-control-allow-origin") == "https://www.tabijiapp.com"

    # User B sharing the EXACT same rightmost egress IP is NOT affected by User A's bucket
    user_b_resp = client.post(
        "/api/sign-cloudinary",
        headers={
            "Authorization": f"Bearer {token_b}",
            "X-Forwarded-For": "203.0.113.99, 35.190.1.10",
        },
        json={"paramsToSign": {"timestamp": now_ts, "folder": "ryan_travel/covers"}},
    )
    assert user_b_resp.status_code == 200


def test_attack_preauth_ip_limiter_blocks_unauth_flood_before_supabase_fallback(monkeypatch):
    monkeypatch.setattr(cloudinary_router, "_PREAUTH_IP_LIMIT", 5)

    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.side_effect = Exception("Invalid opaque token")
    monkeypatch.setattr("utils.deps.get_supabase", lambda request=None: mock_supabase)

    client = TestClient(app)
    now_ts = int(time.time())
    payload = {"paramsToSign": {"timestamp": now_ts, "folder": "ryan_travel/covers"}}

    # 5 unauthenticated requests with non-tabiji-core opaque tokens from same rightmost GFE IP
    # while rotating spoofable CF-Connecting-IP and leftmost XFF
    for i in range(5):
        resp = client.post(
            "/api/sign-cloudinary",
            headers={
                "Authorization": f"Bearer opaque-external-token-{i}",
                "CF-Connecting-IP": f"198.51.100.{i + 1}",
                "X-Forwarded-For": f"203.0.113.{i + 1}, 34.100.200.5",
            },
            json=payload,
        )
        assert resp.status_code == 401

    assert mock_supabase.auth.get_user.call_count == 5

    # 6th request from the same rightmost GFE IP MUST return 429 BEFORE supabase.auth.get_user()
    blocked = client.post(
        "/api/sign-cloudinary",
        headers={
            "Authorization": "Bearer opaque-external-token-flood",
            "CF-Connecting-IP": "198.51.100.99",
            "X-Forwarded-For": "203.0.113.99, 34.100.200.5",
        },
        json=payload,
    )
    assert blocked.status_code == 429
    assert mock_supabase.auth.get_user.call_count == 5
    detail_429 = str(blocked.json().get("detail", "")).lower()
    for word in BYOK_TRIGGER_WORDS:
        assert word not in detail_429

    # Different rightmost GFE IP is isolated into its own bucket
    other_ip_resp = client.post(
        "/api/sign-cloudinary",
        headers={
            "Authorization": "Bearer opaque-external-token-other-ip",
            "X-Forwarded-For": "203.0.113.1, 34.100.200.99",
        },
        json=payload,
    )
    assert other_ip_resp.status_code == 401
    assert mock_supabase.auth.get_user.call_count == 6


def test_missing_cloudinary_config_returns_500_without_byok_keywords(monkeypatch):
    monkeypatch.delenv("CLOUDINARY_CLOUD_NAME", raising=False)
    monkeypatch.delenv("CLOUDINARY_API_KEY", raising=False)
    monkeypatch.delenv("CLOUDINARY_API_SECRET", raising=False)
    monkeypatch.delenv("CLOUDINARY_URL", raising=False)

    client = TestClient(app)
    token = _mint_session_jwt(str(uuid.uuid4()))
    now_ts = int(time.time())

    resp = client.post(
        "/api/sign-cloudinary",
        headers={"Authorization": f"Bearer {token}"},
        json={"paramsToSign": {"timestamp": now_ts, "folder": "ryan_travel/covers"}},
    )
    assert resp.status_code == 500
    body_lower = resp.text.lower()
    assert "cloudinary_api_secret" not in body_lower
    for word in BYOK_TRIGGER_WORDS:
        assert word not in body_lower


def test_benign_zero_double_jwt_decode_and_secret_trailing_ws_stripped(monkeypatch):
    """Mantis Block G benign control: single JWT decode per request + secret CRLF trimming."""
    monkeypatch.setenv("CLOUDINARY_API_SECRET", f"  {TEST_API_SECRET}\r\n ")

    decode_calls = []
    orig_decode = jwt.decode

    def _spy_decode(*args, **kwargs):
        decode_calls.append(True)
        return orig_decode(*args, **kwargs)

    monkeypatch.setattr("utils.deps.jwt.decode", _spy_decode)

    client = TestClient(app)
    token = _mint_session_jwt(str(uuid.uuid4()))
    now_ts = int(time.time())

    resp = client.post(
        "/api/sign-cloudinary",
        headers={"Authorization": f"Bearer {token}"},
        json={"paramsToSign": {"timestamp": now_ts, "folder": "ryan_travel/covers"}},
    )
    assert resp.status_code == 200, resp.text
    assert len(decode_calls) == 1, f"Expected exactly 1 jwt.decode call, got {len(decode_calls)}"
    assert resp.json()["signature"] == _expected_sha1(
        {"timestamp": now_ts, "folder": "ryan_travel/covers"},
        TEST_API_SECRET,
    )


def test_attack_multi_header_xff_and_inflated_xff_cannot_bypass_preauth_limit(monkeypatch):
    """CWE-290 regression: multiple X-Forwarded-For headers (RFC 9110 §5.3) must use true rightmost hop."""
    monkeypatch.setattr(cloudinary_router, "_PREAUTH_IP_LIMIT", 5)

    mock_supabase = MagicMock()
    mock_supabase.auth.get_user.side_effect = Exception("Invalid opaque token")
    monkeypatch.setattr("utils.deps.get_supabase", lambda request=None: mock_supabase)

    client = TestClient(app)
    now_ts = int(time.time())
    payload = {"paramsToSign": {"timestamp": now_ts, "folder": "ryan_travel/covers"}}

    for i in range(5):
        req = client.build_request(
            "POST",
            "/api/sign-cloudinary",
            headers=[
                ("Authorization", f"Bearer opaque-multi-xff-{i}"),
                ("X-Forwarded-For", f"198.51.100.{i + 1}, " + (", " * 500) + f"203.0.113.{i + 1}"),
                ("X-Forwarded-For", "34.100.200.5"),
            ],
            json=payload,
        )
        resp = client.send(req)
        assert resp.status_code == 401

    assert mock_supabase.auth.get_user.call_count == 5

    blocked_req = client.build_request(
        "POST",
        "/api/sign-cloudinary",
        headers=[
            ("Authorization", "Bearer opaque-multi-xff-flood"),
            ("X-Forwarded-For", "198.51.100.250"),
            ("X-Forwarded-For", "34.100.200.5, "),
        ],
        json=payload,
    )
    blocked = client.send(blocked_req)
    assert blocked.status_code == 429
    assert blocked.headers.get("retry-after") == "60"
    assert blocked.headers.get("cache-control") == "no-store"
    assert mock_supabase.auth.get_user.call_count == 5


def test_attack_uuid_case_variation_cannot_split_per_user_rate_limit():
    """Rate limit key must normalize UUID hex case so mixed-case sub cannot double quota."""
    client = TestClient(app)
    uid_lower = "3f7abf22-b447-4281-b240-584549c79943"
    token_lower = _mint_session_jwt(uid_lower)
    token_upper = _mint_session_jwt(uid_lower.upper())
    now_ts = int(time.time())

    for i in range(60):
        resp = client.post(
            "/api/sign-cloudinary",
            headers={"Authorization": f"Bearer {token_lower}"},
            json={"paramsToSign": {"timestamp": now_ts, "folder": "ryan_travel/covers"}},
        )
        assert resp.status_code == 200, f"Request {i + 1}/60 failed: {resp.status_code}"

    blocked_upper = client.post(
        "/api/sign-cloudinary",
        headers={"Authorization": f"Bearer {token_upper}"},
        json={"paramsToSign": {"timestamp": now_ts, "folder": "ryan_travel/covers"}},
    )
    assert blocked_upper.status_code == 429


def test_attack_oversized_payload_and_leading_zero_timestamp_rejected():
    """Reject leading-zero digit strings (canonicalization drift) and oversized JSON bodies (>4KB)."""
    client = TestClient(app)
    token = _mint_session_jwt(str(uuid.uuid4()))
    headers = {"Authorization": f"Bearer {token}"}
    now_ts = int(time.time())

    # Leading-zero timestamp string rejected (400)
    resp_leading_zero = client.post(
        "/api/sign-cloudinary",
        headers=headers,
        json={"paramsToSign": {"timestamp": f"0{now_ts}", "folder": "ryan_travel/covers"}},
    )
    assert resp_leading_zero.status_code == 400

    # Oversized JSON payload rejected (413) without BYOK keywords
    resp_oversized = client.post(
        "/api/sign-cloudinary",
        headers=headers,
        json={"paramsToSign": {"timestamp": now_ts, "folder": "ryan_travel/covers"}, "junk": "A" * 8192},
    )
    assert resp_oversized.status_code == 413
    detail_413 = str(resp_oversized.json().get("detail", "")).lower()
    for word in BYOK_TRIGGER_WORDS:
        assert word not in detail_413


def test_attack_preauth_ip_lru_eviction_and_window_expiry(monkeypatch):
    """
    Pre-auth IP limiter must use LRU (not FIFO) eviction so an actively flooding IP
    inserted earliest cannot have its bucket wiped when a single new IP arrives at capacity,
    must normalize IPv6 hex case, and must prune expired buckets once the window elapses.
    """
    monkeypatch.setattr(cloudinary_router, "_PREAUTH_MAX_TRACKED_IPS", 5)
    monkeypatch.setattr(cloudinary_router, "_PREAUTH_IP_LIMIT", 3)

    fake_clock = [1000.0]
    monkeypatch.setattr(cloudinary_router.time, "monotonic", lambda: fake_clock[0])

    client = TestClient(app)
    now_ts = int(time.time())
    payload = {"paramsToSign": {"timestamp": now_ts, "folder": "ryan_travel/covers"}}

    # 1. Attacker IPv6 hits once at t=1000 (inserted at front of LRU table)
    r1 = client.post("/api/sign-cloudinary", headers={"X-Forwarded-For": "2001:DB8::1"}, json=payload)
    assert r1.status_code == 401

    # 2. 4 other IPs arrive at t=1001..1004, filling the table to capacity (5/5)
    for k in range(2, 6):
        fake_clock[0] += 1.0
        rk = client.post("/api/sign-cloudinary", headers={"X-Forwarded-For": f"10.0.0.{k}"}, json=payload)
        assert rk.status_code == 401

    # 3. Attacker IPv6 sends 2 more requests with lowercase hex (must share same bucket & move to MRU)
    fake_clock[0] = 1020.0
    for _ in range(2):
        r_more = client.post("/api/sign-cloudinary", headers={"X-Forwarded-For": "2001:db8::1"}, json=payload)
        assert r_more.status_code == 401

    # 4th request hits pre-auth 429 and refreshes MRU position
    r_blocked_before = client.post("/api/sign-cloudinary", headers={"X-Forwarded-For": "2001:DB8::1"}, json=payload)
    assert r_blocked_before.status_code == 429
    assert r_blocked_before.headers.get("retry-after") == "60"
    assert r_blocked_before.headers.get("cache-control") == "no-store"

    # 4. A single new IP arrives at capacity -> must evict idle 10.0.0.2, NOT active flooder 2001:db8::1
    fake_clock[0] = 1021.0
    r_new_ip = client.post("/api/sign-cloudinary", headers={"X-Forwarded-For": "10.0.0.99"}, json=payload)
    assert r_new_ip.status_code == 401
    assert "10.0.0.2" not in cloudinary_router._PREAUTH_IP_HITS
    assert "2001:db8::1" in cloudinary_router._PREAUTH_IP_HITS

    # Active flooder MUST still be blocked (429)
    r_blocked_after = client.post("/api/sign-cloudinary", headers={"X-Forwarded-For": "2001:db8::1"}, json=payload)
    assert r_blocked_after.status_code == 429

    # 5. Once window (>60s) elapses, expired buckets prune and IP recovers cleanly
    fake_clock[0] = 1085.0
    r_recovered = client.post("/api/sign-cloudinary", headers={"X-Forwarded-For": "2001:db8::1"}, json=payload)
    assert r_recovered.status_code == 401


def test_attack_content_length_smuggling_and_chunked_stream_cutoff():
    """
    Verify RFC 9110 Content-Length strictness (rejecting negative, signed, underscored,
    Unicode-digit, empty, and conflicting duplicate Content-Length headers) and verify
    chunked streaming without Content-Length aborts immediately at >4096 bytes without
    draining subsequent chunks from ASGI receive().
    """
    client = TestClient(app)
    token = _mint_session_jwt(str(uuid.uuid4()))
    now_ts = int(time.time())
    valid_bytes = json.dumps(
        {"paramsToSign": {"timestamp": now_ts, "folder": "ryan_travel/covers"}}
    ).encode("utf-8")

    # Malformed / negative / non-ASCII Content-Length must return 400
    for bad_cl in ("-1", "+10", "1_000", "abc", ""):
        resp = client.post(
            "/api/sign-cloudinary",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Length": bad_cl,
                "Content-Type": "application/json",
            },
            content=valid_bytes,
        )
        assert resp.status_code == 400, f"Malformed Content-Length={bad_cl!r} returned {resp.status_code}"

    # Conflicting multi-header Content-Length must return 400
    req_conflict = client.build_request(
        "POST",
        "/api/sign-cloudinary",
        headers=[
            ("Authorization", f"Bearer {token}"),
            ("Content-Length", "10"),
            ("Content-Length", "99999"),
            ("Content-Type", "application/json"),
        ],
        content=valid_bytes,
    )
    assert client.send(req_conflict).status_code == 400

    # Identical oversized multi-header & huge-digit Content-Length must return 413
    req_dup_large = client.build_request(
        "POST",
        "/api/sign-cloudinary",
        headers=[
            ("Authorization", f"Bearer {token}"),
            ("Content-Length", "5000"),
            ("Content-Length", "5000"),
            ("Content-Type", "application/json"),
        ],
        content=valid_bytes,
    )
    assert client.send(req_dup_large).status_code == 413

    resp_giant_cl = client.post(
        "/api/sign-cloudinary",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Length": "9" * 5000,
            "Content-Type": "application/json",
        },
        content=valid_bytes,
    )
    assert resp_giant_cl.status_code == 413

    # Exact 4096-byte body without Content-Length (chunked) succeeds (200)
    prefix = valid_bytes[:-1] + b',"pad":"'
    suffix = b'"}'
    pad_len = 4096 - len(prefix) - len(suffix)
    exact_chunks = [prefix, b"A" * pad_len, suffix]

    def _gen_exact():
        yield from exact_chunks

    resp_exact = client.post(
        "/api/sign-cloudinary",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        content=_gen_exact(),
    )
    assert resp_exact.status_code == 200

    # Direct ASGI chunked stream (no Content-Length) exceeding 4096 bytes must abort with 413
    # on chunk 3 (4097th byte) and NEVER await chunk 4..20 from receive().
    async def _run_asgi_stream_cutoff():
        stream_chunks = [b"A" * 2048, b"B" * 2048, b"C", b"D" * 2048, b"E" * 2048]
        receive_calls = 0
        sent_messages = []

        async def _receive():
            nonlocal receive_calls
            if receive_calls < len(stream_chunks):
                chunk = stream_chunks[receive_calls]
                receive_calls += 1
                more = receive_calls < len(stream_chunks)
                return {"type": "http.request", "body": chunk, "more_body": more}
            return {"type": "http.request", "body": b"", "more_body": False}

        async def _send(message):
            sent_messages.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/sign-cloudinary",
            "raw_path": b"/api/sign-cloudinary",
            "query_string": b"",
            "headers": [
                (b"host", b"testserver"),
                (b"authorization", f"Bearer {token}".encode("ascii")),
                (b"content-type", b"application/json"),
                (b"transfer-encoding", b"chunked"),
            ],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        }
        await app(scope, _receive, _send)
        return receive_calls, sent_messages

    receive_calls, sent_messages = asyncio.run(_run_asgi_stream_cutoff())
    start_msg = next(m for m in sent_messages if m["type"] == "http.response.start")
    assert start_msg["status"] == 413
    assert receive_calls == 3, f"Expected immediate cutoff on 3rd chunk (4097 bytes), read {receive_calls} chunks"
