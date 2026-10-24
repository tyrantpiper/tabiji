"""
🛡️ Security Sentinel Sandbox In-Memory PoC: POST /api/auth/rotate Revocation Guard & Anti-Bypass Verification

Tests:
- TC-1: Vulnerability Reproduction: Unpatched /api/auth/rotate allows stale pre-rotation token (ver: 1 < db_ver: 2) to rotate account to ver: 3.
- TC-2: Mantis Patch Verification: Patched /api/auth/rotate enforces state-bifurcated version check (session.token_version < db_ver -> 401).
- TC-3: Legitimate Key Rotation: Client with current token (ver: 2 == db_ver: 2) successfully rotates credentials to ver: 3.
- TC-4: Initial Account Rotation: Client on initial account (db_ver: 1) with token ver: 1 successfully rotates to ver: 2.
- TC-5: Dirty Data Resilience: When database credential_version is None, safely coerces to 1 without crash.
- TC-6: Tampering & Expiration Boundary: Tampered or fully expired tokens are rejected with 401.
"""

import time
import base64
import os
import hashlib
import secrets
import jwt
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel
from typing import Optional, Dict, Any


SECRET = "sentinel_test_secret_pepper_2026_super_secure"
VAULT_KEY = hashlib.sha256(f"tabiji-recovery-vault-salt-{SECRET}".encode()).digest()


def encrypt_recovery_key(recovery_key: str, vault_key: bytes) -> str:
    aesgcm = AESGCM(vault_key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, recovery_key.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_recovery_key(encrypted_payload: Optional[str], vault_key: bytes) -> Optional[str]:
    if not encrypted_payload:
        return None
    raw_data = base64.b64decode(encrypted_payload.encode("utf-8"))
    nonce = raw_data[:12]
    ciphertext = raw_data[12:]
    aesgcm = AESGCM(vault_key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


def generate_mock_prefixed_key() -> tuple[str, str, str]:
    key_id = secrets.token_hex(4)
    secret_entropy = secrets.token_hex(16)
    full_key = f"tbj_rec_{key_id}_{secret_entropy}"
    secret_hash = hashlib.sha256(secret_entropy.encode()).hexdigest()
    return full_key, key_id, secret_hash


def make_test_jwt(user_id: str, ver: int, expired: bool = False) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iss": "tabiji-core",
        "iat": now - 3600 if not expired else now - (40 * 86400),
        "exp": now + 3600 if not expired else now - 3600,
        "ver": ver,
        "type": "device_session"
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


# ---------------------------------------------------------------------------
# Models and Dependencies
# ---------------------------------------------------------------------------
class VerifiedSession(BaseModel):
    user_id: str
    token_version: int = 1


def unpatched_get_verified_user(authorization: Optional[str] = Header(None)) -> str:
    """Emulates backend/utils/deps.py:get_verified_user (stateless, returns only UUID)"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")
    token = authorization.split(" ")[1].strip()
    try:
        payload = jwt.decode(
            token,
            SECRET,
            algorithms=["HS256"],
            issuer="tabiji-core",
            options={"require": ["sub", "iss", "iat", "exp", "type"]}
        )
        if payload.get("type") == "device_session":
            return str(payload.get("sub"))
    except Exception:
        pass
    raise HTTPException(status_code=401, detail="Invalid or expired token")


def patched_get_verified_session(authorization: Optional[str] = Header(None)) -> VerifiedSession:
    """Emulates backend/routers/auth.py:get_verified_session_with_grace"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")
    token = authorization.split(" ")[1].strip()
    try:
        payload = jwt.decode(
            token,
            SECRET,
            algorithms=["HS256"],
            issuer="tabiji-core",
            options={"require": ["sub", "iss", "iat", "exp", "type"]}
        )
        if payload.get("type") == "device_session":
            return VerifiedSession(
                user_id=str(payload.get("sub")),
                token_version=int(payload.get("ver") or 1)
            )
    except jwt.ExpiredSignatureError:
        # Grace period check (<= 90 days)
        payload = jwt.decode(
            token,
            SECRET,
            algorithms=["HS256"],
            issuer="tabiji-core",
            options={"verify_exp": False, "require": ["sub", "iss", "iat", "type"]}
        )
        now = int(time.time())
        if payload.get("type") == "device_session" and (now - payload.get("iat", 0) <= 90 * 86400):
            return VerifiedSession(
                user_id=str(payload.get("sub")),
                token_version=int(payload.get("ver") or 1)
            )
    except Exception:
        pass
    raise HTTPException(status_code=401, detail="Invalid or expired token")


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_tc1_unpatched_rotate_allows_stale_token_rotation_bypass():
    """
    TC-1: [VULNERABILITY REPRODUCTION]
    Proves that the unpatched endpoint allows a client holding a pre-rotation token (ver: 1)
    to rotate credentials after another device already rotated the account to ver: 2.
    """
    app = FastAPI()
    alice_uuid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    db = {
        alice_uuid: {
            "id": alice_uuid,
            "recovery_key_id": "key_v2_active",
            "recovery_key_encrypted": encrypt_recovery_key("tbj_rec_key2_alicevalidsecret12345", VAULT_KEY),
            "credential_version": 2  # Already rotated by Alice on Device A
        }
    }

    @app.post("/api/auth/rotate")
    def unpatched_rotate_endpoint(current_user: str = Depends(unpatched_get_verified_user)):
        user_rec = db.get(current_user)
        if not user_rec:
            raise HTTPException(status_code=404, detail="User not found")
        # Flaw: No check on incoming token version!
        current_ver = (user_rec.get("credential_version", 1) if user_rec else 1) + 1
        new_full_key, new_key_id, _ = generate_mock_prefixed_key()
        db[current_user]["recovery_key_id"] = new_key_id
        db[current_user]["recovery_key_encrypted"] = encrypt_recovery_key(new_full_key, VAULT_KEY)
        db[current_user]["credential_version"] = current_ver

        new_token = make_test_jwt(current_user, ver=current_ver)
        return {
            "access_token": new_token,
            "user_id": current_user,
            "recovery_key": new_full_key,
            "credential_version": current_ver
        }

    client = TestClient(app)

    # Device B holds Alice's pre-rotation token (ver: 1)
    stale_token_v1 = make_test_jwt(alice_uuid, ver=1)

    res = client.post("/api/auth/rotate", headers={"Authorization": f"Bearer {stale_token_v1}"})

    # Flaw Confirmed: Returns HTTP 200 and advances DB version to 3!
    assert res.status_code == 200
    data = res.json()
    assert data["credential_version"] == 3
    assert db[alice_uuid]["credential_version"] == 3
    assert data["recovery_key"].startswith("tbj_rec_")


def test_tc2_patched_rotate_strictly_rejects_stale_token():
    """
    TC-2: [MANTIS PATCH VERIFICATION]
    Proves that with the patch applied, when db_ver > 1 and session.token_version < db_ver,
    POST /api/auth/rotate immediately raises HTTP 401 Unauthorized, and the database
    is not altered.
    """
    app = FastAPI()
    alice_uuid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    original_encrypted_key = encrypt_recovery_key("tbj_rec_key2_alicevalidsecret12345", VAULT_KEY)
    db = {
        alice_uuid: {
            "id": alice_uuid,
            "recovery_key_id": "key_v2_active",
            "recovery_key_encrypted": original_encrypted_key,
            "credential_version": 2  # Already rotated by Alice on Device A
        }
    }

    @app.post("/api/auth/rotate")
    def patched_rotate_endpoint(session: VerifiedSession = Depends(patched_get_verified_session)):
        user_rec = db.get(session.user_id)
        if not user_rec:
            raise HTTPException(status_code=404, detail="User not found")

        db_ver = int(user_rec.get("credential_version") or 1)

        # 🛡️ ADR-009 State-Bifurcated Revocation Guard
        if db_ver > 1 and session.token_version < db_ver:
            raise HTTPException(
                status_code=401,
                detail="Credential has been rotated. This session is revoked."
            )

        current_ver = db_ver + 1
        new_full_key, new_key_id, _ = generate_mock_prefixed_key()
        db[session.user_id]["recovery_key_id"] = new_key_id
        db[session.user_id]["recovery_key_encrypted"] = encrypt_recovery_key(new_full_key, VAULT_KEY)
        db[session.user_id]["credential_version"] = current_ver

        new_token = make_test_jwt(session.user_id, ver=current_ver)
        return {
            "access_token": new_token,
            "user_id": session.user_id,
            "recovery_key": new_full_key,
            "credential_version": current_ver
        }

    client = TestClient(app)

    # Device B holds Alice's pre-rotation token (ver: 1 < db_ver: 2)
    stale_token_v1 = make_test_jwt(alice_uuid, ver=1)

    res = client.post("/api/auth/rotate", headers={"Authorization": f"Bearer {stale_token_v1}"})

    # Protection Confirmed: Rejected with 401 and descriptive revocation message
    assert res.status_code == 401
    assert "revoked" in res.json()["detail"].lower()
    assert "credential has been rotated" in res.json()["detail"].lower()

    # DB Integrity Assertion: Key and version 2 were NOT changed!
    assert db[alice_uuid]["credential_version"] == 2
    assert db[alice_uuid]["recovery_key_id"] == "key_v2_active"
    assert db[alice_uuid]["recovery_key_encrypted"] == original_encrypted_key


def test_tc3_legitimate_current_token_can_rotate():
    """
    TC-3: [LEGITIMATE ROTATION]
    Proves that a legitimate client with a current token (ver: 2 == db_ver: 2)
    successfully rotates the credential to ver: 3.
    """
    app = FastAPI()
    alice_uuid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    db = {
        alice_uuid: {
            "id": alice_uuid,
            "recovery_key_id": "key_v2_active",
            "recovery_key_encrypted": encrypt_recovery_key("tbj_rec_key2_alicevalidsecret12345", VAULT_KEY),
            "credential_version": 2
        }
    }

    @app.post("/api/auth/rotate")
    def patched_rotate_endpoint(session: VerifiedSession = Depends(patched_get_verified_session)):
        user_rec = db.get(session.user_id)
        if not user_rec:
            raise HTTPException(status_code=404, detail="User not found")
        db_ver = int(user_rec.get("credential_version") or 1)
        if db_ver > 1 and session.token_version < db_ver:
            raise HTTPException(status_code=401, detail="Credential has been rotated. This session is revoked.")

        current_ver = db_ver + 1
        new_full_key, new_key_id, _ = generate_mock_prefixed_key()
        db[session.user_id]["recovery_key_id"] = new_key_id
        db[session.user_id]["recovery_key_encrypted"] = encrypt_recovery_key(new_full_key, VAULT_KEY)
        db[session.user_id]["credential_version"] = current_ver

        new_token = make_test_jwt(session.user_id, ver=current_ver)
        return {
            "access_token": new_token,
            "user_id": session.user_id,
            "recovery_key": new_full_key,
            "credential_version": current_ver
        }

    client = TestClient(app)

    # Valid current token (ver: 2)
    valid_token_v2 = make_test_jwt(alice_uuid, ver=2)
    res = client.post("/api/auth/rotate", headers={"Authorization": f"Bearer {valid_token_v2}"})

    assert res.status_code == 200
    data = res.json()
    assert data["credential_version"] == 3
    assert db[alice_uuid]["credential_version"] == 3
    assert data["recovery_key"].startswith("tbj_rec_")


def test_tc4_initial_unrotated_account_can_rotate():
    """
    TC-4: [INITIAL ACCOUNT FIRST ROTATION]
    Proves that on an account that has never been rotated before (db_ver: 1),
    a client possessing ver: 1 token can rotate to ver: 2.
    """
    app = FastAPI()
    bob_uuid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    db = {
        bob_uuid: {
            "id": bob_uuid,
            "recovery_key_id": "key_v1_initial",
            "recovery_key_encrypted": encrypt_recovery_key("tbj_rec_key1_bobinitialsecret12345", VAULT_KEY),
            "credential_version": 1  # Initial unrotated
        }
    }

    @app.post("/api/auth/rotate")
    def patched_rotate_endpoint(session: VerifiedSession = Depends(patched_get_verified_session)):
        user_rec = db.get(session.user_id)
        if not user_rec:
            raise HTTPException(status_code=404, detail="User not found")
        db_ver = int(user_rec.get("credential_version") or 1)
        if db_ver > 1 and session.token_version < db_ver:
            raise HTTPException(status_code=401, detail="Credential has been rotated. This session is revoked.")

        current_ver = db_ver + 1
        new_full_key, new_key_id, _ = generate_mock_prefixed_key()
        db[session.user_id]["recovery_key_id"] = new_key_id
        db[session.user_id]["recovery_key_encrypted"] = encrypt_recovery_key(new_full_key, VAULT_KEY)
        db[session.user_id]["credential_version"] = current_ver

        new_token = make_test_jwt(session.user_id, ver=current_ver)
        return {
            "access_token": new_token,
            "user_id": session.user_id,
            "recovery_key": new_full_key,
            "credential_version": current_ver
        }

    client = TestClient(app)

    token_v1 = make_test_jwt(bob_uuid, ver=1)
    res = client.post("/api/auth/rotate", headers={"Authorization": f"Bearer {token_v1}"})

    assert res.status_code == 200
    assert res.json()["credential_version"] == 2
    assert db[bob_uuid]["credential_version"] == 2


def test_tc5_dirty_data_resilience_none_credential_version():
    """
    TC-5: [DIRTY DATA RESILIENCE]
    Proves that if credential_version is None (legacy row), it safely coerces to 1,
    allowing rotation to ver: 2 without 500 error or TypeError.
    """
    app = FastAPI()
    charlie_uuid = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    db = {
        charlie_uuid: {
            "id": charlie_uuid,
            "recovery_key_id": "key_legacy_none",
            "recovery_key_encrypted": encrypt_recovery_key("tbj_rec_key0_legacykey12345", VAULT_KEY),
            "credential_version": None  # Un-migrated row
        }
    }

    @app.post("/api/auth/rotate")
    def patched_rotate_endpoint(session: VerifiedSession = Depends(patched_get_verified_session)):
        user_rec = db.get(session.user_id)
        if not user_rec:
            raise HTTPException(status_code=404, detail="User not found")
        db_ver = int(user_rec.get("credential_version") or 1)
        if db_ver > 1 and session.token_version < db_ver:
            raise HTTPException(status_code=401, detail="Credential has been rotated. This session is revoked.")

        current_ver = db_ver + 1
        new_full_key, new_key_id, _ = generate_mock_prefixed_key()
        db[session.user_id]["recovery_key_id"] = new_key_id
        db[session.user_id]["recovery_key_encrypted"] = encrypt_recovery_key(new_full_key, VAULT_KEY)
        db[session.user_id]["credential_version"] = current_ver

        new_token = make_test_jwt(session.user_id, ver=current_ver)
        return {
            "access_token": new_token,
            "user_id": session.user_id,
            "recovery_key": new_full_key,
            "credential_version": current_ver
        }

    client = TestClient(app)

    token_v1 = make_test_jwt(charlie_uuid, ver=1)
    res = client.post("/api/auth/rotate", headers={"Authorization": f"Bearer {token_v1}"})

    assert res.status_code == 200
    assert res.json()["credential_version"] == 2
    assert db[charlie_uuid]["credential_version"] == 2


def test_tc6_tampering_and_expiration_boundary():
    """
    TC-6: [BOUNDARIES & TAMPERING DEFENSE]
    Proves that forged signatures, invalid tokens, and expired tokens outside the 90-day grace window
    are strictly rejected with HTTP 401.
    """
    app = FastAPI()

    @app.post("/api/auth/rotate")
    def patched_rotate_endpoint(session: VerifiedSession = Depends(patched_get_verified_session)):
        return {"status": "ok", "user_id": session.user_id}

    client = TestClient(app)

    # 1. Missing Authorization header
    res1 = client.post("/api/auth/rotate")
    assert res1.status_code == 401

    # 2. Forged signature
    fake_token = make_test_jwt("david_uuid", ver=1) + "tampered"
    res2 = client.post("/api/auth/rotate", headers={"Authorization": f"Bearer {fake_token}"})
    assert res2.status_code == 401

    # 3. Token expired (> 90 days ago)
    now = int(time.time())
    ancient_payload = {
        "sub": "david_uuid",
        "iss": "tabiji-core",
        "iat": now - (100 * 86400),  # 100 days old (exceeds 90-day window)
        "exp": now - (70 * 86400),
        "ver": 1,
        "type": "device_session"
    }
    ancient_token = jwt.encode(ancient_payload, SECRET, algorithm="HS256")
    res3 = client.post("/api/auth/rotate", headers={"Authorization": f"Bearer {ancient_token}"})
    assert res3.status_code == 401
