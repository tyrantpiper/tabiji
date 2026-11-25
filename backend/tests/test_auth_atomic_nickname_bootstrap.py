# -*- coding: utf-8 -*-
"""
Unit & Sentinel Test Suite: Atomic Nickname Bootstrap on POST /api/auth/session
-------------------------------------------------------------------------------
Verifies:
1. Brand-new user bootstrap (and legacy fallback insert) atomically persists sanitized `name`.
2. Omitted, blank, control-only, or placeholder names default safely to 'Traveler'.
3. Control characters are stripped/collapsed and length boundaries (64-char clamp, >256 422) hold.
4. Orphan UUID self-healing (and partial legacy orphan missing public.users row) persists `name`.
5. Existing users (tbj_rec_*, upgraded PoP, legacy silent upgrade, /recover) NEVER have `name` overwritten.
"""

from __future__ import annotations

import hashlib
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import jwt
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app  # noqa: E402
from routers.auth import (  # noqa: E402
    DEFAULT_BOOTSTRAP_NAME,
    MAX_BOOTSTRAP_NAME_LEN,
    encrypt_recovery_key,
    generate_prefixed_recovery_key,
    sanitize_bootstrap_name,
)
from utils.deps import get_supabase  # noqa: E402
from utils.limiter import limiter  # noqa: E402


def _make_in_memory_supabase(
    initial_users: dict[str, dict[str, Any]] | None = None,
    *,
    trip_member_uids: set[str] | None = None,
    fail_first_user_insert: bool = False,
):
    users = {k.lower(): dict(v) for k, v in (initial_users or {}).items()}
    member_uids = {u.lower() for u in (trip_member_uids or set())}
    inserted_payloads: list[dict[str, Any]] = []
    updated_payloads: list[tuple[str, dict[str, Any]]] = []
    insert_attempts = {"count": 0}

    client = MagicMock()

    def table_router(table_name: str):
        tbl = MagicMock()

        def handle_select(*args, **kwargs):
            sel = MagicMock()

            def handle_eq(col: str, val: str):
                eq_obj = MagicMock()

                def _exec():
                    clean = str(val).strip().lower()
                    if table_name == "users":
                        if col == "id":
                            row = users.get(clean)
                            return MagicMock(data=[dict(row)] if row else [])
                        if col == "recovery_key_id":
                            matches = [dict(r) for r in users.values() if r.get("recovery_key_id") == val]
                            return MagicMock(data=matches[:1])
                    if table_name == "trip_members" and col == "user_id":
                        if clean in member_uids:
                            return MagicMock(data=[{"user_id": clean}])
                    return MagicMock(data=[])

                eq_obj.execute.side_effect = _exec
                eq_obj.limit.return_value.execute.side_effect = _exec
                return eq_obj

            sel.eq.side_effect = handle_eq
            return sel

        def handle_insert(payload: dict[str, Any]):
            ins = MagicMock()

            def _exec():
                if table_name == "users":
                    insert_attempts["count"] += 1
                    if fail_first_user_insert and insert_attempts["count"] == 1:
                        raise RuntimeError("simulated missing column on first insert")
                    uid = str(payload["id"]).strip().lower()
                    if uid in users:
                        raise RuntimeError("duplicate key value violates unique constraint")
                    row = dict(payload)
                    users[uid] = row
                    inserted_payloads.append(dict(payload))
                    return MagicMock(data=[dict(row)])
                return MagicMock(data=[dict(payload)])

            ins.execute.side_effect = _exec
            return ins

        def handle_update(payload: dict[str, Any]):
            upd = MagicMock()

            def handle_eq(col: str, val: str):
                def _exec():
                    if table_name == "users" and col == "id":
                        uid = str(val).strip().lower()
                        if uid in users:
                            updated_payloads.append((uid, dict(payload)))
                            users[uid].update(payload)
                            return MagicMock(data=[dict(users[uid])])
                    return MagicMock(data=[])

                return MagicMock(execute=_exec)

            upd.eq.side_effect = handle_eq
            return upd

        tbl.select.side_effect = handle_select
        tbl.insert.side_effect = handle_insert
        tbl.update.side_effect = handle_update
        return tbl

    client.table.side_effect = table_router
    client._users = users
    client._inserted_payloads = inserted_payloads
    client._updated_payloads = updated_payloads
    return client


def _mint_jwt(uid: str, secret: str, ver: int = 1) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "sub": uid,
            "iss": "tabiji-core",
            "iat": now,
            "exp": now + 3600,
            "ver": ver,
            "type": "device_session",
        },
        secret,
        algorithm="HS256",
    )


@pytest.fixture(autouse=True)
def _disable_limiter():
    orig = limiter.enabled
    limiter.enabled = False
    try:
        yield
    finally:
        limiter.enabled = orig


def test_sanitize_bootstrap_name_edge_cases():
    assert sanitize_bootstrap_name(None) == DEFAULT_BOOTSTRAP_NAME
    assert sanitize_bootstrap_name("") == DEFAULT_BOOTSTRAP_NAME
    assert sanitize_bootstrap_name("   \t\r\n  ") == DEFAULT_BOOTSTRAP_NAME
    assert sanitize_bootstrap_name("\x00\x07\x1f\x7f\u0085") == DEFAULT_BOOTSTRAP_NAME
    for placeholder in ("Traveler", "traveler", "New Traveler", "Unknown Traveler", "Legacy Traveler", "null", "undefined"):
        assert sanitize_bootstrap_name(placeholder) == DEFAULT_BOOTSTRAP_NAME

    assert sanitize_bootstrap_name("  海獺  ") == "海獺"
    assert sanitize_bootstrap_name("Alice\r\n\t\x00Bob") == "Alice Bob"
    assert sanitize_bootstrap_name("Tokyo Traveler") == "Tokyo Traveler"
    assert sanitize_bootstrap_name("A" * 100) == "A" * MAX_BOOTSTRAP_NAME_LEN
    # Boundary trailing space after slicing must be trimmed
    assert sanitize_bootstrap_name(("A" * 63) + "  B") == "A" * 63

    # Invisible / zero-width / Bidi control characters & Unicode fullwidth/NBSP whitespace
    for bad in (
        "\u200b",
        "\ufeff",
        "\u200b\u200c\ufeff",
        "\u200d",
        "\u200d\ufe0f",
        "Traveler\u200b",
        "New\u3000Traveler",
        "New\u00a0Traveler",
        "null" + ("e" + "\u0301" * 61),
        "undefined" + ("e" + "\u0301" * 61),
    ):
        assert sanitize_bootstrap_name(bad) == DEFAULT_BOOTSTRAP_NAME
    # Fullwidth/NBSP whitespace is collapsed cleanly before truncation
    assert sanitize_bootstrap_name("null" + ("\u3000" * 60) + "x") == "null x"

    assert sanitize_bootstrap_name("\u202eAlice\u200b") == "Alice"
    assert sanitize_bootstrap_name("海獺 🦦👨‍💻") == "海獺 🦦👨‍💻"

    # Grapheme-safe 64-code-point boundary truncation (no dangling ZWJ, split flag, or split combining mark)
    assert sanitize_bootstrap_name(("A" * 62) + "👨‍💻") == "A" * 62
    assert sanitize_bootstrap_name(("A" * 62) + "👨‍👩‍👧‍👦") == "A" * 62
    assert sanitize_bootstrap_name(("A" * 63) + "🇹🇼") == "A" * 63
    assert sanitize_bootstrap_name(("A" * 63) + "e\u0301") == "A" * 63
    assert sanitize_bootstrap_name("e" + ("\u0301" * 70)) == DEFAULT_BOOTSTRAP_NAME
    assert sanitize_bootstrap_name("🦦" * 70) == "🦦" * MAX_BOOTSTRAP_NAME_LEN


def test_new_user_bootstrap_persists_atomic_name_and_fallback_insert(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret-atomic-name-2026")
    monkeypatch.setenv("VAULT_MASTER_KEY", "test-vault-master-atomic-name-2026")

    # 1. Primary insert writes sanitized CJK name atomically
    mock_sb = _make_in_memory_supabase()
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    try:
        with TestClient(app) as client:
            res = client.post("/api/auth/session", json={"name": "  海獺  "})
            assert res.status_code == 200
            data = res.json()
            assert data["is_new"] is True
            uid = data["user_id"]
            assert mock_sb._users[uid]["name"] == "海獺"
            assert mock_sb._inserted_payloads[-1]["name"] == "海獺"

            # Omitted name defaults to Traveler (backwards compatibility)
            res_default = client.post("/api/auth/session", json={})
            assert res_default.status_code == 200
            uid_default = res_default.json()["user_id"]
            assert mock_sb._users[uid_default]["name"] == "Traveler"

            # Blank / control-only name defaults to Traveler
            res_blank = client.post("/api/auth/session", json={"name": " \x00\r\n\t "})
            assert res_blank.status_code == 200
            assert mock_sb._users[res_blank.json()["user_id"]]["name"] == "Traveler"

            # Length > 64 and <= 256 is safely clamped to 64
            res_clamp = client.post("/api/auth/session", json={"name": "B" * 100})
            assert res_clamp.status_code == 200
            assert mock_sb._users[res_clamp.json()["user_id"]]["name"] == "B" * MAX_BOOTSTRAP_NAME_LEN

            # Length > 256 is rejected at schema boundary (422)
            res_too_long = client.post("/api/auth/session", json={"name": "C" * 257})
            assert res_too_long.status_code == 422

            # Non-string JSON types for `name` are rejected cleanly with 422
            for bad_payload in ({"name": 123}, {"name": ["Alice"]}, {"name": {"v": "Alice"}}, {"name": True}):
                res_bad = client.post("/api/auth/session", json=bad_payload)
                assert res_bad.status_code == 422
    finally:
        app.dependency_overrides.clear()

    # 2. Fallback insert (when full-column insert fails) ALSO preserves sanitized name
    mock_sb_fallback = _make_in_memory_supabase(fail_first_user_insert=True)
    app.dependency_overrides[get_supabase] = lambda: mock_sb_fallback
    try:
        with TestClient(app) as client:
            res_fb = client.post("/api/auth/session", json={"name": "Chungshi"})
            assert res_fb.status_code == 200
            uid_fb = res_fb.json()["user_id"]
            assert mock_sb_fallback._users[uid_fb] == {"id": uid_fb, "name": "Chungshi"}
    finally:
        app.dependency_overrides.clear()


def test_orphan_uuid_bootstrap_persists_atomic_name_and_respects_default(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-session-secret-orphan-name-2026")
    monkeypatch.setenv("VAULT_MASTER_KEY", "test-vault-master-orphan-name-2026")

    orphan_with_name = str(uuid.uuid4())
    orphan_no_name = str(uuid.uuid4())
    partial_legacy_orphan = str(uuid.uuid4())

    mock_sb = _make_in_memory_supabase(trip_member_uids={partial_legacy_orphan})
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    try:
        with TestClient(app) as client:
            # 1. Pure orphan UUID with local nickname
            res1 = client.post(
                "/api/auth/session",
                json={
                    "recovery_key": orphan_with_name,
                    "expected_user_id": orphan_with_name,
                    "name": "  William\n",
                },
            )
            assert res1.status_code == 200
            assert res1.json()["upgraded"] is True
            assert mock_sb._users[orphan_with_name]["name"] == "William"

            # 2. Pure orphan UUID without name -> defaults to Traveler
            res2 = client.post(
                "/api/auth/session",
                json={
                    "recovery_key": orphan_no_name,
                    "expected_user_id": orphan_no_name,
                },
            )
            assert res2.status_code == 200
            assert mock_sb._users[orphan_no_name]["name"] == "Traveler"

            # 3. Partial legacy orphan (exists in trip_members, missing public.users row) with nickname
            res3 = client.post(
                "/api/auth/session",
                json={
                    "recovery_key": partial_legacy_orphan,
                    "expected_user_id": partial_legacy_orphan,
                    "name": "Chungshi",
                },
            )
            assert res3.status_code == 200
            assert mock_sb._users[partial_legacy_orphan]["name"] == "Chungshi"
    finally:
        app.dependency_overrides.clear()


def test_existing_users_never_have_name_overwritten_on_session_or_recover(monkeypatch):
    session_secret = "test-session-secret-existing-guard-2026"
    vault_secret = "test-vault-master-existing-guard-2026"
    monkeypatch.setenv("SESSION_SECRET_KEY", session_secret)
    monkeypatch.setenv("VAULT_MASTER_KEY", vault_secret)

    modern_uid = str(uuid.uuid4())
    legacy_session_uid = str(uuid.uuid4())
    legacy_recover_uid = str(uuid.uuid4())

    modern_key, modern_key_id, modern_hash = generate_prefixed_recovery_key()
    vault_key = hashlib.sha256(f"tabiji-recovery-vault-salt-{vault_secret}".encode()).digest()

    mock_sb = _make_in_memory_supabase({
        modern_uid: {
            "id": modern_uid,
            "name": "OriginalModern",
            "recovery_key_id": modern_key_id,
            "recovery_secret_hash": modern_hash,
            "recovery_key_encrypted": encrypt_recovery_key(modern_key, vault_key),
            "credential_version": 1,
        },
        legacy_session_uid: {
            "id": legacy_session_uid,
            "name": "OriginalLegacySession",
            "recovery_key_id": None,
            "recovery_secret_hash": None,
            "recovery_key_encrypted": None,
            "credential_version": 1,
        },
        legacy_recover_uid: {
            "id": legacy_recover_uid,
            "name": "OriginalLegacyRecover",
            "recovery_key_id": None,
            "recovery_secret_hash": None,
            "recovery_key_encrypted": None,
            "credential_version": 1,
        },
    })

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    try:
        with TestClient(app) as client:
            # 1. Existing modern tbj_rec_* exchange with forged name -> untouched
            res_rec = client.post(
                "/api/auth/session",
                json={"recovery_key": modern_key, "expected_user_id": modern_uid, "name": "HijackedName"},
            )
            assert res_rec.status_code == 200
            assert mock_sb._users[modern_uid]["name"] == "OriginalModern"

            # 2. Existing upgraded user via PoP JWT + legacy UUID with forged name -> untouched
            pop_jwt = _mint_jwt(modern_uid, session_secret, ver=1)
            res_pop = client.post(
                "/api/auth/session",
                json={"recovery_key": modern_uid, "expected_user_id": modern_uid, "name": "HijackedPoP"},
                headers={"Authorization": f"Bearer {pop_jwt}"},
            )
            assert res_pop.status_code == 200
            assert mock_sb._users[modern_uid]["name"] == "OriginalModern"

            # 3. Existing un-upgraded legacy user silent upgrade via /session with forged name -> untouched
            res_leg = client.post(
                "/api/auth/session",
                json={"recovery_key": legacy_session_uid, "expected_user_id": legacy_session_uid, "name": "HijackedLegacy"},
            )
            assert res_leg.status_code == 200
            assert res_leg.json()["upgraded"] is True
            assert mock_sb._users[legacy_session_uid]["name"] == "OriginalLegacySession"
            assert all("name" not in payload for _, payload in mock_sb._updated_payloads)

            # 4. Existing un-upgraded legacy user via /recover with forged name -> untouched
            res_recover = client.post(
                "/api/auth/recover",
                json={"recovery_key": legacy_recover_uid, "name": "HijackedRecover"},
            )
            assert res_recover.status_code == 200
            assert mock_sb._users[legacy_recover_uid]["name"] == "OriginalLegacyRecover"
            assert all("name" not in payload for _, payload in mock_sb._updated_payloads)
    finally:
        app.dependency_overrides.clear()


def test_orphan_uuid_concurrent_insert_race_never_overwrites_winner_name(monkeypatch):
    """
    Simulates two concurrent orphan-UUID bootstrap requests arriving before either row exists:
    - Request A inserts 'FirstRealName' while Request B's initial existence check saw empty.
    - Request B hits unique-key violation on users.insert, re-reads winner row, and MUST NOT
      overwrite 'FirstRealName' (returns 401 without PoP, or returns winner key with valid PoP).
    """
    session_secret = "test-session-secret-race-guard-2026"
    vault_secret = "test-vault-master-race-guard-2026"
    monkeypatch.setenv("SESSION_SECRET_KEY", session_secret)
    monkeypatch.setenv("VAULT_MASTER_KEY", vault_secret)

    raced_uid = str(uuid.uuid4())
    winner_key, winner_key_id, winner_hash = generate_prefixed_recovery_key()
    vault_key = hashlib.sha256(f"tabiji-recovery-vault-salt-{vault_secret}".encode()).digest()

    mock_sb = _make_in_memory_supabase({
        raced_uid: {
            "id": raced_uid,
            "name": "FirstRealName",
            "recovery_key_id": winner_key_id,
            "recovery_secret_hash": winner_hash,
            "recovery_key_encrypted": encrypt_recovery_key(winner_key, vault_key),
            "credential_version": 1,
        }
    })

    # Force Request B's initial pre-insert check to observe `exists=False` (simulating TOCTOU race)
    import routers.auth as auth_router
    monkeypatch.setattr(auth_router, "legacy_identity_exists", lambda sb, uid: False)

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    try:
        with TestClient(app) as client:
            # Without PoP: duplicate insert -> re-read winner -> 401, name untouched
            res_no_pop = client.post(
                "/api/auth/session",
                json={"recovery_key": raced_uid, "expected_user_id": raced_uid, "name": "SecondAttempt"},
            )
            assert res_no_pop.status_code == 401
            assert mock_sb._users[raced_uid]["name"] == "FirstRealName"
            assert mock_sb._updated_payloads == []

            # With valid PoP: duplicate insert -> re-read winner -> 200 with winner key, name untouched
            pop_jwt = _mint_jwt(raced_uid, session_secret, ver=1)
            res_with_pop = client.post(
                "/api/auth/session",
                json={"recovery_key": raced_uid, "expected_user_id": raced_uid, "name": "SecondAttemptPoP"},
                headers={"Authorization": f"Bearer {pop_jwt}"},
            )
            assert res_with_pop.status_code == 200
            assert res_with_pop.json()["recovery_key"] == winner_key
            assert mock_sb._users[raced_uid]["name"] == "FirstRealName"
            assert mock_sb._updated_payloads == []
    finally:
        app.dependency_overrides.clear()
