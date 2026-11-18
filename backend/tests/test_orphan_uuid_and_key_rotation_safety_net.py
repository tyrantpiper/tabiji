# -*- coding: utf-8 -*-
"""
Regression & Sentinel Verification Suite:
1. Orphan UUID v4 self-healing in POST /api/auth/session (AC-1, AC-2)
2. Supabase new API key (sb_secret_ / sb_publishable_) header builder (AC-5)
3. Fast-fail in get_verified_user for invalid iss == "tabiji-core" JWTs (AC-5)
4. H2 VAULT_MASTER_KEY backwards-compatible decryption across key rotation
5. /api/health/deep & PUT /api/users/me outgoing PostgREST headers with sb_secret_
"""

import hashlib
import os
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import _deep_health_cache, app  # noqa: E402
from routers.auth import (  # noqa: E402
    UNIFORM_AUTH_ERROR,
    decrypt_recovery_key,
    derive_vault_key,
    encrypt_recovery_key,
)
from utils.deps import (  # noqa: E402
    build_supabase_rest_headers,
    get_session_secret,
    get_supabase,
    get_verified_user,
)


def _make_empty_supabase_mock():
    """Creates a Supabase mock where users / trip_members / itineraries initially have 0 rows."""
    client = MagicMock()
    inserted_rows = []

    def table_router(table_name: str):
        tbl = MagicMock()
        tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        tbl.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        if table_name == "users":
            def record_insert(payload):
                inserted_rows.append(payload)
                return MagicMock(execute=lambda: MagicMock(data=[payload]))

            tbl.insert.side_effect = record_insert
        return tbl

    client.table.side_effect = table_router
    client._inserted_rows = inserted_rows
    return client


def test_ac1_orphan_uuid_self_heals_and_issues_tbj_rec_key():
    """AC-1: Valid unregistered orphan UUID v4 with matching expected_user_id bootstraps public.users and returns 200."""
    orphan_uid = str(uuid.uuid4())
    mock_sb = _make_empty_supabase_mock()

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    try:
        with TestClient(app) as client:
            res = client.post(
                "/api/auth/session",
                json={"recovery_key": orphan_uid, "expected_user_id": orphan_uid.upper()},
            )
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    data = res.json()
    assert data["user_id"] == orphan_uid.lower()
    assert data["is_new"] is False
    assert data["upgraded"] is True
    assert data["recovery_key"].startswith("tbj_rec_")
    assert data["access_token"]

    # Verify JWT signed with active secret and matching sub
    decoded = jwt.decode(
        data["access_token"],
        get_session_secret(),
        algorithms=["HS256"],
        issuer="tabiji-core",
    )
    assert decoded["sub"] == orphan_uid.lower()

    # Verify DB insert happened with expected columns
    assert len(mock_sb._inserted_rows) == 1
    row = mock_sb._inserted_rows[0]
    assert row["id"] == orphan_uid.lower()
    assert row["credential_version"] == 1
    assert row["recovery_key_id"]
    assert row["recovery_secret_hash"]
    assert row["recovery_key_encrypted"]


def test_ac1_orphan_uuid_without_expected_user_id_still_self_heals():
    """Backwards compatibility: older clients omitting expected_user_id also self-heal on orphan UUID."""
    orphan_uid = str(uuid.uuid4())
    mock_sb = _make_empty_supabase_mock()

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    try:
        with TestClient(app) as client:
            res = client.post("/api/auth/session", json={"recovery_key": orphan_uid})
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    body = res.json()
    assert body["user_id"] == orphan_uid.lower()
    assert body["is_new"] is False
    assert body["upgraded"] is True
    assert body["recovery_key"].startswith("tbj_rec_")


def test_ac1_orphan_uuid_concurrent_insert_race_recovers_with_pop_and_rejects_without_pop():
    """Concurrent PK collision on users.insert falls back to get_user_record_by_id instead of failing 503."""
    orphan_uid = str(uuid.uuid4())
    secret = get_session_secret()
    winner_key = "tbj_rec_12345678_abcdef0123456789abcdef0123456789"
    encrypted_winner = encrypt_recovery_key(winner_key, derive_vault_key(secret))

    def make_race_supabase():
        client = MagicMock()
        users_select_calls = {"count": 0}

        def table_router(table_name: str):
            tbl = MagicMock()
            if table_name == "users":
                def select_exec():
                    users_select_calls["count"] += 1
                    # First lookup (legacy_identity_exists) sees empty; post-insert race lookup finds winner row
                    if users_select_calls["count"] <= 1:
                        return MagicMock(data=[])
                    return MagicMock(
                        data=[{
                            "id": orphan_uid,
                            "recovery_key_id": "12345678",
                            "recovery_secret_hash": "hash",
                            "recovery_key_encrypted": encrypted_winner,
                            "credential_version": 1,
                        }]
                    )

                tbl.select.return_value.eq.return_value.limit.return_value.execute.side_effect = select_exec
                tbl.insert.return_value.execute.side_effect = RuntimeError("duplicate key value violates unique constraint")
            else:
                tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            return tbl

        client.table.side_effect = table_router
        return client

    pop_jwt = jwt.encode(
        {
            "sub": orphan_uid,
            "iss": "tabiji-core",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "ver": 1,
            "type": "device_session",
        },
        secret,
        algorithm="HS256",
    )

    # Case A: Loser has valid PoP JWT -> decrypts winner's recovery key and returns 200
    app.dependency_overrides[get_supabase] = make_race_supabase
    try:
        with TestClient(app) as client:
            res_pop = client.post(
                "/api/auth/session",
                json={"recovery_key": orphan_uid},
                headers={"Authorization": f"Bearer {pop_jwt}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert res_pop.status_code == 200
    assert res_pop.json()["recovery_key"] == winner_key
    assert res_pop.json()["upgraded"] is True

    # Case B: Loser has NO PoP JWT -> must fail closed with 401 (no ATO), never 503
    app.dependency_overrides[get_supabase] = make_race_supabase
    try:
        with TestClient(app) as client:
            res_no_pop = client.post("/api/auth/session", json={"recovery_key": orphan_uid})
    finally:
        app.dependency_overrides.clear()

    assert res_no_pop.status_code == 401


def test_ac1_orphan_uuid_total_db_failure_returns_503():
    """If both users.insert and fallback lookup fail, endpoint returns 503 instead of silently issuing unpersisted credentials."""
    orphan_uid = str(uuid.uuid4())
    mock_sb = _make_empty_supabase_mock()

    def failing_router(table_name: str):
        tbl = MagicMock()
        tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        if table_name == "users":
            tbl.insert.return_value.execute.side_effect = RuntimeError("DB connection refused")
        return tbl

    mock_sb.table.side_effect = failing_router
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    try:
        with TestClient(app) as client:
            res = client.post("/api/auth/session", json={"recovery_key": orphan_uid})
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 503


def test_ac2_mismatched_expected_user_id_blocks_orphan_bootstrap_and_recover_stays_404():
    """AC-2: Mismatched expected_user_id returns 401 without DB insert; /api/auth/recover keeps 404 for unknown UUID."""
    orphan_uid = str(uuid.uuid4())
    other_uid = str(uuid.uuid4())
    mock_sb = _make_empty_supabase_mock()

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    try:
        with TestClient(app) as client:
            res_session = client.post(
                "/api/auth/session",
                json={"recovery_key": orphan_uid, "expected_user_id": other_uid},
            )
            res_recover = client.post(
                "/api/auth/recover",
                json={"recovery_key": orphan_uid},
            )
    finally:
        app.dependency_overrides.clear()

    assert res_session.status_code == 401
    assert res_session.json()["detail"] == UNIFORM_AUTH_ERROR
    assert "access_token" not in res_session.json()
    assert len(mock_sb._inserted_rows) == 0

    assert res_recover.status_code == 404
    assert res_recover.json()["detail"] == "Account not found"
    assert len(mock_sb._inserted_rows) == 0


def test_ac5_build_supabase_rest_headers_handles_new_and_legacy_keys():
    """AC-5: New sb_secret_/sb_publishable_ keys omit Authorization: Bearer; legacy JWT keys keep both."""
    secret_headers = build_supabase_rest_headers("  sb_secret_test_only_123  ")
    assert secret_headers == {"apikey": "sb_secret_test_only_123"}
    assert "Authorization" not in secret_headers

    pub_headers = build_supabase_rest_headers("sb_publishable_test_only_456")
    assert pub_headers == {"apikey": "sb_publishable_test_only_456"}
    assert "Authorization" not in pub_headers

    legacy_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.sig"
    legacy_headers = build_supabase_rest_headers(
        legacy_jwt,
        {"Content-Type": "application/json", "Prefer": "return=representation"},
    )
    assert legacy_headers["apikey"] == legacy_jwt
    assert legacy_headers["Authorization"] == f"Bearer {legacy_jwt}"
    assert legacy_headers["Content-Type"] == "application/json"
    assert legacy_headers["Prefer"] == "return=representation"

    empty_headers = build_supabase_rest_headers("")
    assert empty_headers == {"apikey": ""}
    assert "Authorization" not in empty_headers


@pytest.mark.asyncio
async def test_ac5_get_verified_user_fast_fails_rotated_tabiji_core_jwt_without_supabase_call(monkeypatch):
    """AC-5: Invalid signature JWT with iss=='tabiji-core' must fail 401 immediately without calling supabase.auth.get_user."""
    monkeypatch.setenv("SESSION_SECRET_KEY", "new_rotated_secret_key_0123456789abcdef0123456789abcdef")

    old_secret = "old_rotated_secret_key_0123456789abcdef0123456789abcdef"
    user_uuid = str(uuid.uuid4())
    stale_tabiji_jwt = jwt.encode(
        {
            "sub": user_uuid,
            "iss": "tabiji-core",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "type": "device_session",
        },
        old_secret,
        algorithm="HS256",
    )

    mock_sb = MagicMock()
    mock_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(supabase=mock_sb)))

    with pytest.raises(HTTPException) as exc_info:
        await get_verified_user(request=mock_request, auth_header=f"Bearer {stale_tabiji_jwt}")

    assert exc_info.value.status_code == 401
    mock_sb.auth.get_user.assert_not_called()

    # Non-tabiji-core JWT (e.g. Supabase GoTrue OAuth JWT) still delegates to supabase.auth.get_user
    oauth_user_id = str(uuid.uuid4())
    external_jwt = jwt.encode(
        {
            "sub": oauth_user_id,
            "iss": "https://example.supabase.co/auth/v1",
            "exp": int(time.time()) + 3600,
        },
        "external_oauth_secret_0123456789abcdef",
        algorithm="HS256",
    )
    mock_sb.auth.get_user.return_value = SimpleNamespace(user=SimpleNamespace(id=oauth_user_id))
    resolved = await get_verified_user(request=mock_request, auth_header=f"Bearer {external_jwt}")
    assert resolved == oauth_user_id
    mock_sb.auth.get_user.assert_called_once_with(external_jwt)


def test_h2_vault_master_key_decrypts_legacy_ciphertext_after_full_key_rotation(monkeypatch):
    """Pinned H2 VAULT_MASTER_KEY decrypts legacy recovery_key_encrypted after rotating SUPABASE_KEY and SESSION_SECRET_KEY."""
    old_supabase_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.legacy_service_role_payload.legacy_sig"
    plaintext_recovery_key = "tbj_rec_deadbeef_00112233445566778899aabbccddeeff"

    # 1. Legacy environment: VAULT_MASTER_KEY and SESSION_SECRET_KEY unset, derived from OLD SUPABASE_KEY
    monkeypatch.delenv("VAULT_MASTER_KEY", raising=False)
    monkeypatch.delenv("SESSION_SECRET_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_KEY", old_supabase_key)

    legacy_vault_key = derive_vault_key()
    ciphertext = encrypt_recovery_key(plaintext_recovery_key, legacy_vault_key)

    # Compute H1 -> H2 per Cloud Cutover Runbook
    h1 = hashlib.sha256(f"tabiji-session-salt-{old_supabase_key}".encode()).hexdigest()
    h2 = hashlib.sha256(f"tabiji-dedicated-vault-salt-{h1}".encode()).hexdigest()

    # 2. Rotated environment: SUPABASE_KEY -> sb_secret_, SESSION_SECRET_KEY -> new 64-hex, VAULT_MASTER_KEY -> H2
    monkeypatch.setenv("SUPABASE_KEY", "sb_secret_new_test_key_999999")
    monkeypatch.setenv("SESSION_SECRET_KEY", "a" * 64)
    monkeypatch.setenv("VAULT_MASTER_KEY", h2)

    rotated_vault_key = derive_vault_key(get_session_secret())
    assert rotated_vault_key == legacy_vault_key
    assert decrypt_recovery_key(ciphertext, rotated_vault_key) == plaintext_recovery_key


@pytest.mark.asyncio
async def test_health_deep_and_users_me_use_sb_secret_without_bearer_header(monkeypatch):
    """Integration: /api/health/deep and PUT /api/users/me pass apikey: sb_secret_... without Authorization: Bearer sb_secret_..."""
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "sb_secret_test_only_header_check")
    monkeypatch.setenv("SESSION_SECRET_KEY", "test_session_secret_key_0123456789abcdef")

    _deep_health_cache["last_checked"] = 0.0
    _deep_health_cache["payload"] = {}

    captured_health_headers = []

    async def fake_health_get(url, headers=None, timeout=None):
        captured_health_headers.append(dict(headers or {}))
        return httpx.Response(200, json=[{"id": "trip-1"}])

    fake_app_client = MagicMock()
    fake_app_client.get = AsyncMock(side_effect=fake_health_get)
    prev_client = getattr(app.state, "client", None)
    app.state.client = fake_app_client
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            res = await client.get("/api/health/deep")

        assert res.status_code == 200
        assert len(captured_health_headers) == 1
        assert captured_health_headers[0]["apikey"] == "sb_secret_test_only_header_check"
        assert "Authorization" not in captured_health_headers[0]
    finally:
        app.state.client = prev_client
        _deep_health_cache["last_checked"] = 0.0
        _deep_health_cache["payload"] = {}

    # Now verify PUT /api/users/me REST headers
    user_uuid = str(uuid.uuid4())
    user_jwt = jwt.encode(
        {
            "sub": user_uuid,
            "iss": "tabiji-core",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "type": "device_session",
        },
        get_session_secret(),
        algorithm="HS256",
    )

    captured_users_headers = []

    async def fake_users_get(url, headers=None):
        captured_users_headers.append(("GET", dict(headers or {})))
        return httpx.Response(200, json=[{"id": user_uuid}])

    async def fake_users_patch(url, headers=None, content=None):
        captured_users_headers.append(("PATCH", dict(headers or {})))
        return httpx.Response(200, json=[{"id": user_uuid, "name": "Ryan"}])

    with patch("routers.users.HTTPX_CLIENT.get", new=AsyncMock(side_effect=fake_users_get)), \
         patch("routers.users.HTTPX_CLIENT.patch", new=AsyncMock(side_effect=fake_users_patch)):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            res_put = await client.put(
                "/api/users/me",
                json={"name": "Ryan"},
                headers={"Authorization": f"Bearer {user_jwt}"},
            )

    assert res_put.status_code == 200
    assert len(captured_users_headers) == 2
    for _, hdrs in captured_users_headers:
        assert hdrs["apikey"] == "sb_secret_test_only_header_check"
        assert "Authorization" not in hdrs
        assert hdrs["Content-Type"] == "application/json"
        assert hdrs["Prefer"] == "return=representation"
