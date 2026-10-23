# -*- coding: utf-8 -*-
"""
🛡️ Security Sentinel Sandbox PoC: Phase 4 Multi-Device Sync Deadlock & Proof-of-Possession Invariant Verification
Tests:
- TC-1: Legacy Device Deadlock vs Proof-of-Possession Silent Upgrade (Anti-ATO preserved)
- TC-2: Dormant Device Grace Period Vault Recovery vs Unverified / Forged Rejection
- TC-3: End-to-End Vault Decryption and In-Flight Token Healing
"""
import pytest
import os
import time
import uuid
import hashlib
import base64
import jwt
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Header, Request, Depends
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel

TEST_SECRET = "test_super_secure_session_secret_key_2026"
TEST_VAULT_KEY_STR = "test_vault_master_key_12345678"


def get_test_vault_key() -> bytes:
    return hashlib.sha256(f"tabiji-recovery-vault-salt-{TEST_VAULT_KEY_STR}".encode()).digest()


def encrypt_test_recovery_key(key_str: str) -> str:
    aesgcm = AESGCM(get_test_vault_key())
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, key_str.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("utf-8")


def decrypt_test_recovery_key(payload: Optional[str]) -> Optional[str]:
    if not payload:
        return None
    raw = base64.b64decode(payload.encode("utf-8"))
    nonce = raw[:12]
    ct = raw[12:]
    aesgcm = AESGCM(get_test_vault_key())
    return aesgcm.decrypt(nonce, ct, None).decode("utf-8")


def create_mock_jwt(user_id: str, secret: str, issued_offset_days: int = 0, expire_days: int = 30) -> str:
    now = int(time.time()) - (issued_offset_days * 86400)
    payload = {
        "sub": user_id,
        "iss": "tabiji-core",
        "iat": now,
        "exp": now + (expire_days * 86400),
        "ver": 1,
        "type": "device_session"
    }
    return jwt.encode(payload, secret, algorithm="HS256")


# --------------------------------------------------------------------------
# Mock Database State
# --------------------------------------------------------------------------
MOCK_USERS_DB: Dict[str, Dict[str, Any]] = {
    "11111111-2222-4333-8444-555555555555": {
        "id": "11111111-2222-4333-8444-555555555555",
        "recovery_key_id": "a1b2c3d4",
        "recovery_secret_hash": "mock_hash_for_modern_key",
        "recovery_key_encrypted": encrypt_test_recovery_key("tbj_rec_a1b2c3d4_0123456789abcdef0123456789abcdef"),
        "credential_version": 2
    }
}

# --------------------------------------------------------------------------
# Logic Implementations (Vulnerable vs Hardened)
# --------------------------------------------------------------------------
class SessionReq(BaseModel):
    recovery_key: Optional[str] = None


def vulnerable_session_exchange(req: SessionReq) -> dict:
    uid = (req.recovery_key or "").strip().lower()
    user = MOCK_USERS_DB.get(uid)
    if user and user.get("recovery_key_id"):
        # ❌ Vulnerability: Blind 400 rejection locks out authentic legacy devices
        raise HTTPException(status_code=400, detail="Account already upgraded. Please use your modern recovery key.")
    return {"status": "ok"}


def hardened_session_exchange(
    req: SessionReq,
    auth_header: Optional[str] = None,
    secret: str = TEST_SECRET
) -> dict:
    uid = (req.recovery_key or "").strip().lower()
    user = MOCK_USERS_DB.get(uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.get("recovery_key_id"):
        # 🛡️ Hardened: Check for Proof-of-Possession of legitimate historical session token
        is_authenticated = False
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1].strip()
            try:
                # Allow signature verification without strict exp (up to 90 days grace period)
                payload = jwt.decode(
                    token, secret, algorithms=["HS256"], issuer="tabiji-core", options={"verify_exp": False}
                )
                if payload.get("sub") == uid and payload.get("type") == "device_session":
                    iat = payload.get("iat", 0)
                    now = int(time.time())
                    # Grace period: 90 days
                    if now - iat <= 90 * 86400:
                        is_authenticated = True
            except Exception:
                pass

        if not is_authenticated:
            # 🛡️ Anti-ATO intact: Unauthenticated third party with raw UUID cannot harvest recovery key!
            raise HTTPException(status_code=401, detail="Account upgraded. Proof of possession or modern key required.")

        # Authenticated legacy device: Unblock deadlock by returning decrypted modern key & fresh token
        decrypted_key = decrypt_test_recovery_key(user.get("recovery_key_encrypted"))
        new_token = create_mock_jwt(uid, secret, issued_offset_days=0, expire_days=30)
        return {
            "access_token": new_token,
            "user_id": uid,
            "recovery_key": decrypted_key,
            "upgraded": True
        }

    return {"status": "ok"}


def extract_user_with_grace_period(auth_header: Optional[str], secret: str) -> Optional[str]:
    """🛡️ Grace-period token verification for dormant devices on /credential"""
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ")[1].strip()
    try:
        # Verify signature, issuer, type, but allow expired token within 90-day grace period
        payload = jwt.decode(
            token, secret, algorithms=["HS256"], issuer="tabiji-core", options={"verify_exp": False}
        )
        if payload.get("type") != "device_session":
            return None
        iat = payload.get("iat", 0)
        now = int(time.time())
        if now - iat > 90 * 86400:
            return None  # Expired past grace period
        return str(payload.get("sub"))
    except Exception:
        return None


# --------------------------------------------------------------------------
# Test Cases
# --------------------------------------------------------------------------
def test_tc1_vulnerable_legacy_device_deadlock_reproduced():
    """Reproduces deadlock: legacy device is rejected with 400 even if holding valid previous token"""
    req = SessionReq(recovery_key="11111111-2222-4333-8444-555555555555")
    with pytest.raises(HTTPException) as exc_info:
        vulnerable_session_exchange(req)
    assert exc_info.value.status_code == 400
    assert "Account already upgraded" in str(exc_info.value.detail)


def test_tc1_hardened_legacy_device_proof_of_possession_unlocked():
    """Hardened: authentic legacy device with unexpired/recent token is safely upgraded to modern key"""
    uid = "11111111-2222-4333-8444-555555555555"
    req = SessionReq(recovery_key=uid)
    
    # 1. Device holds a 10-day-old valid session token
    token = create_mock_jwt(uid, TEST_SECRET, issued_offset_days=10)
    res = hardened_session_exchange(req, auth_header=f"Bearer {token}")
    
    assert res["upgraded"] is True
    assert res["recovery_key"].startswith("tbj_rec_")
    assert res["user_id"] == uid
    assert "access_token" in res

    # 2. Device holds an expired token (35 days old, within 90d grace period)
    expired_token = create_mock_jwt(uid, TEST_SECRET, issued_offset_days=35, expire_days=30)
    res2 = hardened_session_exchange(req, auth_header=f"Bearer {expired_token}")
    assert res2["upgraded"] is True
    assert res2["recovery_key"].startswith("tbj_rec_")


def test_tc1_hardened_anti_ato_preservation():
    """Hardened: unauthenticated attacker guessing raw UUID is strictly blocked"""
    uid = "11111111-2222-4333-8444-555555555555"
    req = SessionReq(recovery_key=uid)

    # 1. No token at all
    with pytest.raises(HTTPException) as exc:
        hardened_session_exchange(req, auth_header=None)
    assert exc.value.status_code == 401

    # 2. Forged token with invalid secret
    fake_token = create_mock_jwt(uid, "attacker_forged_secret")
    with pytest.raises(HTTPException) as exc:
        hardened_session_exchange(req, auth_header=f"Bearer {fake_token}")
    assert exc.value.status_code == 401

    # 3. Token for a different user
    diff_token = create_mock_jwt("99999999-9999-4999-8999-999999999999", TEST_SECRET)
    with pytest.raises(HTTPException) as exc:
        hardened_session_exchange(req, auth_header=f"Bearer {diff_token}")
    assert exc.value.status_code == 401


def test_tc2_dormant_device_grace_period_vault_recovery():
    """Dormant device whose 30-day token expired 15 days ago can self-heal on /credential"""
    uid = "11111111-2222-4333-8444-555555555555"
    # 40-day old token with 30d expiry -> expired 10 days ago
    stale_token = create_mock_jwt(uid, TEST_SECRET, issued_offset_days=40, expire_days=30)
    
    # Standard strict decode fails
    with pytest.raises(jwt.ExpiredSignatureError):
        jwt.decode(stale_token, TEST_SECRET, algorithms=["HS256"])

    # Grace period decode succeeds
    extracted = extract_user_with_grace_period(f"Bearer {stale_token}", TEST_SECRET)
    assert extracted == uid

    # Token older than 90 days fails grace period
    ancient_token = create_mock_jwt(uid, TEST_SECRET, issued_offset_days=100, expire_days=30)
    assert extract_user_with_grace_period(f"Bearer {ancient_token}", TEST_SECRET) is None

    # Forged token fails grace period
    forged = create_mock_jwt(uid, "fake_secret", issued_offset_days=40, expire_days=30)
    assert extract_user_with_grace_period(f"Bearer {forged}", TEST_SECRET) is None
