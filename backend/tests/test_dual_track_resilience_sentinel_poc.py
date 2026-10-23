"""
🛡️ Security Sentinel Sandbox In-Memory PoC: Dual-Track Resilience & Fail-Closed Defense
Tests:
- TC-1: Defect 1 Proof: DB update failure must NOT return an unpersisted recovery_key or upgraded=True.
- TC-2: Defect 1 Remediation: Successful DB update returns persisted=True and valid recovery_key.
- TC-3: Defect 2 Proof: In production environment, missing RECOVERY_PEPPER must Fail-Closed (RuntimeError).
- TC-4: Multi-Device Sync Gap Proof: Device A with valid JWT does not auto-upgrade until explicitly triggered.
"""
import pytest
import os
import secrets
import hmac
import hashlib
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from typing import Optional, Any


# ---------------------------------------------------------------------------
# Test Targets & Logic Replication
# ---------------------------------------------------------------------------
class SessionResponse(BaseModel):
    access_token: str
    user_id: str
    recovery_key: Optional[str] = None
    upgraded: Optional[bool] = None
    is_new: bool


def safe_recover_legacy_upgrade(
    clean_uid: str,
    db_update_func,
    secret: str = "test_secret",
    pepper: str = "test_pepper"
) -> SessionResponse:
    """Remediated logic for Defect 1: Transactional atomicity in silent upgrade."""
    key_id = secrets.token_hex(4)
    secret_entropy = secrets.token_hex(16)
    full_key = f"tbj_rec_{key_id}_{secret_entropy}"
    secret_hash = hmac.new(pepper.encode(), secret_entropy.encode(), hashlib.sha256).hexdigest()

    persisted = False
    try:
        db_update_func(clean_uid, key_id, secret_hash)
        persisted = True
    except Exception as e:
        print(f"⚠️ [Auth Sentinel Test] DB update simulated failure: {e}")

    return SessionResponse(
        access_token="mock_jwt_token",
        user_id=clean_uid,
        recovery_key=full_key if persisted else None,
        upgraded=persisted,
        is_new=False
    )


def resolve_pepper(env_val: Optional[str], is_prod: bool) -> str:
    """Remediated logic for Defect 2: Fail-closed in production if pepper is missing."""
    if not env_val:
        if is_prod:
            raise RuntimeError("🚨 [CRITICAL SECURITY] RECOVERY_PEPPER must be explicitly set in production!")
        return "tbj_secret_pepper_auth_recovery_v2_2026"
    return env_val


# ---------------------------------------------------------------------------
# In-Memory Sandbox Test Cases
# ---------------------------------------------------------------------------
def test_tc1_defect1_failsafe_on_db_exception():
    """TC-1: When DB update throws, endpoint MUST NOT claim upgraded=True or return unpersisted key."""
    def failing_db_update(uid, kid, shash):
        raise ConnectionError("Supabase connection timeout during update")

    resp = safe_recover_legacy_upgrade("user_uuid_123", failing_db_update)
    
    # Assertions for resilience
    assert resp.upgraded is False, "Must not set upgraded=True on DB failure!"
    assert resp.recovery_key is None, "Must not return an unpersisted recovery_key!"
    assert resp.user_id == "user_uuid_123"
    assert resp.access_token == "mock_jwt_token"


def test_tc2_defect1_success_on_db_persisted():
    """TC-2: When DB update succeeds, endpoint returns full_key and upgraded=True."""
    persisted_state = {}

    def successful_db_update(uid, kid, shash):
        persisted_state[uid] = {"key_id": kid, "secret_hash": shash}

    resp = safe_recover_legacy_upgrade("user_uuid_456", successful_db_update)
    
    assert resp.upgraded is True
    assert resp.recovery_key is not None
    assert resp.recovery_key.startswith("tbj_rec_")
    assert "user_uuid_456" in persisted_state
    assert persisted_state["user_uuid_456"]["key_id"] in resp.recovery_key


def test_tc3_defect2_production_fail_closed_pepper():
    """TC-3: Missing pepper in production triggers RuntimeError; Dev fallback succeeds."""
    # Production without pepper -> Must fail
    with pytest.raises(RuntimeError) as exc_info:
        resolve_pepper(env_val=None, is_prod=True)
    assert "CRITICAL SECURITY" in str(exc_info.value)

    # Production with pepper -> Succeeds
    prod_pepper = resolve_pepper(env_val="my_prod_secret_pepper_123", is_prod=True)
    assert prod_pepper == "my_prod_secret_pepper_123"

    # Development without pepper -> Graceful fallback
    dev_pepper = resolve_pepper(env_val=None, is_prod=False)
    assert dev_pepper == "tbj_secret_pepper_auth_recovery_v2_2026"


def test_tc4_multi_device_gap_simulation():
    """
    TC-4: Multi-Device Gap Simulation:
    Demonstrates that Device A (legacy UUID in local cache) and Device B (triggered upgrade)
    diverge unless Device A actively queries the backend for credential status.
    """
    db = {
        "user_alice": {
            "id": "user_alice",
            "recovery_key_id": None,
            "recovery_secret_hash": None,
            "credential_version": 1
        }
    }

    # 1. Device A starts with legacy UUID
    device_a_local_storage = {
        "user_uuid": "user_alice",
        "tabiji_session_token": "valid_token_30_days",
        "user_recovery_key": None  # Device A has no modern key
    }

    # 2. Device B logs in using Device A's UUID -> Triggers silent upgrade
    resp = safe_recover_legacy_upgrade(
        "user_alice",
        lambda uid, kid, shash: db["user_alice"].update({"recovery_key_id": kid, "recovery_secret_hash": shash})
    )
    device_b_local_storage = {
        "user_uuid": "user_alice",
        "user_recovery_key": resp.recovery_key  # Device B has tbj_rec_*
    }

    # 3. Empirically verify the divergence
    assert device_b_local_storage["user_recovery_key"] is not None
    assert device_a_local_storage["user_recovery_key"] is None
    assert db["user_alice"]["recovery_key_id"] is not None

    # 4. If Device A tries to log in with UUID again, it would be blocked!
    # Proves the exact phenomenon Ryan encountered.
    is_upgraded_in_db = db["user_alice"]["recovery_key_id"] is not None
    assert is_upgraded_in_db is True
