# -*- coding: utf-8 -*-
"""
Security Sentinel PoC & Regression Suite (2026-11-18):
Verifies production auth cutover & defense-in-depth invariants against REAL routers/auth.py + utils/deps.py:
1. Unauthenticated expected_user_id == clean_uid MUST NOT bypass PoP or ADR-009 on upgraded accounts.
2. LEGACY_SESSION_SECRET_KEY / PREVIOUS_SESSION_SECRET_KEY enables silent migration for valid unrotated (db_ver == 1) devices.
3. ADR-009 State-Bifurcated Revocation strictly rejects old version JWTs (token_ver < db_ver) even if signed by LEGACY_SESSION_SECRET_KEY.
4. Normal business endpoint dependency deps.get_verified_user strictly rejects LEGACY_SESSION_SECRET_KEY tokens (forces seamless silent upgrade).
5. LEGACY_VAULT_MASTER_KEY backwards-compatible vault decryption across VAULT_MASTER_KEY cutover.
6. Mantis Block G Benign Controls verify normal tbj_rec_*, rotated vN sessions, and orphan UUID self-healing still succeed.
"""

import base64
import hashlib
import hmac
import json
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app  # noqa: E402
from routers.auth import (  # noqa: E402
    encrypt_recovery_key,
    generate_prefixed_recovery_key,
)
from utils.deps import get_session_secret, get_supabase, get_verified_user  # noqa: E402
from utils.limiter import limiter  # noqa: E402


def _make_in_memory_users_supabase(initial_users: dict[str, dict]):
    users = {k.lower(): dict(v) for k, v in initial_users.items()}
    client = MagicMock()

    def table_router(table_name: str):
        tbl = MagicMock()

        def handle_select(*args, **kwargs):
            sel = MagicMock()

            def handle_eq(col: str, val: str):
                eq_obj = MagicMock()

                def _exec():
                    if table_name != "users":
                        return MagicMock(data=[])
                    clean = str(val).strip().lower()
                    if col == "id":
                        row = users.get(clean)
                        return MagicMock(data=[dict(row)] if row else [])
                    if col == "recovery_key_id":
                        matches = [dict(r) for r in users.values() if r.get("recovery_key_id") == val]
                        return MagicMock(data=matches[:1])
                    return MagicMock(data=[])

                eq_obj.execute.side_effect = _exec
                eq_obj.limit.return_value.execute.side_effect = _exec
                return eq_obj

            sel.eq.side_effect = handle_eq
            return sel

        def handle_update(payload: dict):
            upd = MagicMock()

            def handle_eq(col: str, val: str):
                def _exec():
                    if table_name == "users" and col == "id":
                        uid = str(val).strip().lower()
                        if uid in users:
                            users[uid].update(payload)
                            return MagicMock(data=[dict(users[uid])])
                    return MagicMock(data=[])

                return MagicMock(execute=_exec)

            upd.eq.side_effect = handle_eq
            return upd

        tbl.select.side_effect = handle_select
        tbl.update.side_effect = handle_update
        return tbl

    client.table.side_effect = table_router
    client._users = users
    return client


def _mint_jwt(uid: str, secret: str, ver: int = 1, iat_offset: int = 0, exp_offset: int = 3600) -> str:
    now = int(time.time())
    payload = {
        "sub": uid,
        "iss": "tabiji-core",
        "iat": now + iat_offset,
        "exp": now + exp_offset,
        "ver": ver,
        "type": "device_session",
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _mint_raw_hs256_jwt(payload: dict, secret: str) -> str:
    """Signs raw HS256 JWT without PyJWT InsecureKeyLengthWarning when testing short-key rejection."""
    def _b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    header_b64 = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64(sig)}"


@pytest.fixture(autouse=True)
def _disable_limiter():
    orig = limiter.enabled
    limiter.enabled = False
    try:
        yield
    finally:
        limiter.enabled = orig


def test_unauthenticated_expected_user_id_does_not_bypass_pop_or_revocation(monkeypatch):
    """
    Verifies cross-origin anchor self-healing vs bare UUID rejection & ADR-009 revocation:
    1. Bare UUID without expected_user_id MUST fail with 401 on upgraded accounts.
    2. Mismatched expected_user_id != victim_uid MUST fail with 401.
    3. Revoked Bearer token (token_ver < db_ver on db_ver > 1) MUST fail 401 even when expected_user_id == victim_uid.
    4. Cross-origin tokenless tab sending matching recovery_key == expected_user_id == clean_uid
       safely self-heals from the server vault and returns current db_ver JWT.
    """
    current_secret = "current-prod-session-secret-2026-xyz"
    vault_secret = "current-prod-vault-master-key-2026-xyz"
    monkeypatch.setenv("SESSION_SECRET_KEY", current_secret)
    monkeypatch.setenv("VAULT_MASTER_KEY", vault_secret)

    uid_v1 = str(uuid.uuid4())
    uid_v4 = str(uuid.uuid4())
    other_uid = str(uuid.uuid4())
    k1, id1, h1 = generate_prefixed_recovery_key()
    k4, id4, h4 = generate_prefixed_recovery_key()
    vault_key = hashlib.sha256(f"tabiji-recovery-vault-salt-{vault_secret}".encode()).digest()

    mock_sb = _make_in_memory_users_supabase({
        uid_v1: {
            "id": uid_v1,
            "recovery_key_id": id1,
            "recovery_secret_hash": h1,
            "recovery_key_encrypted": encrypt_recovery_key(k1, vault_key),
            "credential_version": 1,
        },
        uid_v4: {
            "id": uid_v4,
            "recovery_key_id": id4,
            "recovery_secret_hash": h4,
            "recovery_key_encrypted": encrypt_recovery_key(k4, vault_key),
            "credential_version": 4,
        },
    })

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    try:
        with TestClient(app) as client:
            for victim_uid, expected_key, ver in ((uid_v1, k1, 1), (uid_v4, k4, 4)):
                # Bare UUID blind probe without expected_user_id -> 401
                res_bare = client.post(
                    "/api/auth/session",
                    json={"recovery_key": victim_uid},
                )
                assert res_bare.status_code == 401
                assert "tbj_rec_" in res_bare.json()["detail"]

                # Cross-account expected_user_id mismatch -> 401
                res_mismatch = client.post(
                    "/api/auth/session",
                    json={"recovery_key": victim_uid, "expected_user_id": other_uid},
                )
                assert res_mismatch.status_code == 401

                # Tokenless same-origin tab with matching anchor -> 200 silent self-healing
                res_anchor = client.post(
                    "/api/auth/session",
                    json={"recovery_key": victim_uid, "expected_user_id": victim_uid.upper()},
                )
                assert res_anchor.status_code == 200
                body_anchor = res_anchor.json()
                assert body_anchor["user_id"] == victim_uid
                assert body_anchor["recovery_key"] == expected_key
                assert body_anchor["upgraded"] is True
                decoded = jwt.decode(
                    body_anchor["access_token"],
                    current_secret,
                    algorithms=["HS256"],
                    issuer="tabiji-core",
                )
                assert decoded["ver"] == ver

            # Revoked PoP token (ver=3 < db_ver=4) MUST be rejected even with matching expected_user_id
            revoked_v3 = _mint_jwt(uid_v4, current_secret, ver=3)
            res_rev = client.post(
                "/api/auth/session",
                json={"recovery_key": uid_v4, "expected_user_id": uid_v4},
                headers={"Authorization": f"Bearer {revoked_v3}"},
            )
            assert res_rev.status_code == 401
            assert "revoked" in res_rev.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_legacy_session_secret_enables_pop_upgrade_and_grace_while_enforcing_adr009(monkeypatch):
    """
    Verifies:
    - Unrotated db_ver=1 upgraded user holding LEGACY_SESSION_SECRET_KEY JWT (even expired <= 90d)
      smoothly re-exchanges via /api/auth/session for a new JWT signed by current SESSION_SECRET_KEY + decrypted key.
    - Rotated db_ver=4 user holding old ver=1..3 LEGACY_SESSION_SECRET_KEY JWT is strictly rejected 401 (ADR-009)
      on /api/auth/session, /api/auth/credential, and /api/auth/rotate.
    - Rotated db_ver=4 user holding pre-cutover valid ver=4 LEGACY_SESSION_SECRET_KEY JWT works on /api/auth/credential.
    """
    current_secret = "current-prod-session-secret-2026-abc"
    legacy_secret = "legacy-pre-cutover-session-secret-2026"
    current_vault = "current-prod-vault-master-key-v2-2026"
    legacy_vault = "legacy-pre-cutover-vault-master-v1-2026"

    monkeypatch.setenv("SESSION_SECRET_KEY", current_secret)
    monkeypatch.setenv("LEGACY_SESSION_SECRET_KEY", legacy_secret)
    monkeypatch.setenv("VAULT_MASTER_KEY", current_vault)
    monkeypatch.setenv("LEGACY_VAULT_MASTER_KEY", legacy_vault)

    uid_v1 = str(uuid.uuid4())
    uid_v4 = str(uuid.uuid4())
    k1, id1, h1 = generate_prefixed_recovery_key()
    k4, id4, h4 = generate_prefixed_recovery_key()

    legacy_vault_key = hashlib.sha256(f"tabiji-recovery-vault-salt-{legacy_vault}".encode()).digest()
    current_vault_key = hashlib.sha256(f"tabiji-recovery-vault-salt-{current_vault}".encode()).digest()

    mock_sb = _make_in_memory_users_supabase({
        uid_v1: {
            "id": uid_v1,
            "recovery_key_id": id1,
            "recovery_secret_hash": h1,
            # Encrypted with legacy vault key to verify backwards-compatible fallback too!
            "recovery_key_encrypted": encrypt_recovery_key(k1, legacy_vault_key),
            "credential_version": 1,
        },
        uid_v4: {
            "id": uid_v4,
            "recovery_key_id": id4,
            "recovery_secret_hash": h4,
            "recovery_key_encrypted": encrypt_recovery_key(k4, current_vault_key),
            "credential_version": 4,
        },
    })

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    try:
        with TestClient(app) as client:
            # 1. Valid unrotated (db_ver=1) device holding expired (10d ago) legacy-secret JWT -> 200 upgrade
            legacy_expired_v1 = _mint_jwt(uid_v1, legacy_secret, ver=1, iat_offset=-40 * 86400, exp_offset=-10 * 86400)
            res_ok = client.post(
                "/api/auth/session",
                json={"recovery_key": uid_v1, "expected_user_id": uid_v1},
                headers={"Authorization": f"Bearer {legacy_expired_v1}"},
            )
            assert res_ok.status_code == 200
            body_ok = res_ok.json()
            assert body_ok["user_id"] == uid_v1
            assert body_ok["recovery_key"] == k1
            # Newly minted token must verify under current_secret!
            decoded = jwt.decode(body_ok["access_token"], current_secret, algorithms=["HS256"], issuer="tabiji-core")
            assert decoded["sub"] == uid_v1

            # 2. Grace /credential with legacy-secret expired token for unrotated user -> 200
            res_cred = client.get("/api/auth/credential", headers={"Authorization": f"Bearer {legacy_expired_v1}"})
            assert res_cred.status_code == 200
            assert res_cred.json()["recovery_key"] == k1

            # 3. ADR-009 Strict Revocation: db_ver=4 user with ver=3 JWT signed by legacy_secret -> 401 everywhere
            revoked_legacy_v3 = _mint_jwt(uid_v4, legacy_secret, ver=3, iat_offset=-1000, exp_offset=3600)
            res_rev_sess = client.post(
                "/api/auth/session",
                json={"recovery_key": uid_v4, "expected_user_id": uid_v4},
                headers={"Authorization": f"Bearer {revoked_legacy_v3}"},
            )
            assert res_rev_sess.status_code == 401
            assert "revoked" in res_rev_sess.json()["detail"].lower()

            res_rev_cred = client.get("/api/auth/credential", headers={"Authorization": f"Bearer {revoked_legacy_v3}"})
            assert res_rev_cred.status_code == 401

            res_rev_rot = client.post("/api/auth/rotate", headers={"Authorization": f"Bearer {revoked_legacy_v3}"})
            assert res_rev_rot.status_code == 401

            # 4. Pre-cutover rotated user holding matching ver=4 legacy_secret JWT -> allowed on /credential
            valid_legacy_v4 = _mint_jwt(uid_v4, legacy_secret, ver=4, iat_offset=-1000, exp_offset=3600)
            res_cred_v4 = client.get("/api/auth/credential", headers={"Authorization": f"Bearer {valid_legacy_v4}"})
            assert res_cred_v4.status_code == 200
            assert res_cred_v4.json()["recovery_key"] == k4
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_deps_get_verified_user_rejects_legacy_secret_jwt(monkeypatch):
    """
    Business API dependency deps.get_verified_user MUST remain strict to active SESSION_SECRET_KEY
    so old-secret JWTs fail 401 and force silent upgrade via /api/auth/session.
    """
    current_secret = "current-prod-session-secret-strict"
    legacy_secret = "legacy-pre-cutover-session-secret-strict"
    monkeypatch.setenv("SESSION_SECRET_KEY", current_secret)
    monkeypatch.setenv("LEGACY_SESSION_SECRET_KEY", legacy_secret)

    uid = str(uuid.uuid4())
    legacy_tok = _mint_jwt(uid, legacy_secret, ver=1)
    with pytest.raises(HTTPException) as exc:
        await get_verified_user(f"Bearer {legacy_tok}")
    assert exc.value.status_code == 401

    current_tok = _mint_jwt(uid, current_secret, ver=1)
    assert await get_verified_user(f"Bearer {current_tok}") == uid


def test_mantis_block_g_benign_control_and_tamper_rejection(monkeypatch):
    """
    Mantis Block G Benign Control:
    - Legitimate tbj_rec_* + expected_user_id succeeds -> 200.
    - Forged legacy JWT with wrong secret or >90d expired -> 401.
    - Short (<16 char) LEGACY_SESSION_SECRET_KEY is ignored safely.
    - Rotating credential increments credential_version and issues new current-secret JWT.
    """
    current_secret = "current-prod-session-secret-benign"
    monkeypatch.setenv("SESSION_SECRET_KEY", current_secret)
    monkeypatch.setenv("LEGACY_SESSION_SECRET_KEY", "too-short")
    monkeypatch.setenv("VAULT_MASTER_KEY", "current-prod-vault-master-benign-2026")

    uid = str(uuid.uuid4())
    k1, id1, h1 = generate_prefixed_recovery_key()
    vault_key = hashlib.sha256(b"tabiji-recovery-vault-salt-current-prod-vault-master-benign-2026").digest()
    mock_sb = _make_in_memory_users_supabase({
        uid: {
            "id": uid,
            "recovery_key_id": id1,
            "recovery_secret_hash": h1,
            "recovery_key_encrypted": encrypt_recovery_key(k1, vault_key),
            "credential_version": 1,
        }
    })

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    try:
        with TestClient(app) as client:
            # Benign tbj_rec_* exchange
            res = client.post("/api/auth/session", json={"recovery_key": k1, "expected_user_id": uid})
            assert res.status_code == 200
            tok = res.json()["access_token"]

            # Forged short secret rejected (minted via raw HMAC to satisfy RFC 7518 zero-warning test hygiene)
            now = int(time.time())
            forged_short = _mint_raw_hs256_jwt(
                {"sub": uid, "iss": "tabiji-core", "iat": now, "exp": now + 3600, "ver": 1, "type": "device_session"},
                "too-short",
            )
            res_short = client.post(
                "/api/auth/session",
                json={"recovery_key": uid},
                headers={"Authorization": f"Bearer {forged_short}"},
            )
            assert res_short.status_code == 401

            # Comma-separated PREVIOUS_SESSION_SECRET_KEY & legacy session-derived vault key also supported
            prev_secret = "previous-rotated-session-secret-key-2026-32bytes"
            monkeypatch.setenv("PREVIOUS_SESSION_SECRET_KEY", f"ignored-short,{prev_secret}")
            prev_tok = _mint_jwt(uid, prev_secret, ver=1)
            res_prev = client.post(
                "/api/auth/session",
                json={"recovery_key": uid, "expected_user_id": uid},
                headers={"Authorization": f"Bearer {prev_tok}"},
            )
            assert res_prev.status_code == 200
            assert res_prev.json()["recovery_key"] == k1

            # >90d expired PoP rejected
            stale_91d = _mint_jwt(uid, current_secret, ver=1, iat_offset=-91 * 86400, exp_offset=-61 * 86400)
            res_stale = client.post(
                "/api/auth/session",
                json={"recovery_key": uid},
                headers={"Authorization": f"Bearer {stale_91d}"},
            )
            assert res_stale.status_code == 401

            # Benign rotation works and old key immediately fails
            res_rot = client.post("/api/auth/rotate", headers={"Authorization": f"Bearer {tok}"})
            assert res_rot.status_code == 200
            new_k = res_rot.json()["recovery_key"]
            assert new_k != k1
            assert client.post("/api/auth/session", json={"recovery_key": k1}).status_code == 401
            assert client.post("/api/auth/session", json={"recovery_key": new_k, "expected_user_id": uid}).status_code == 200
    finally:
        app.dependency_overrides.clear()
