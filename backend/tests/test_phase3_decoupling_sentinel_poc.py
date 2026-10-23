# -*- coding: utf-8 -*-
"""
🛡️ Security Sentinel Sandbox PoC: Phase 3 Architecture Decoupling & Invariant Verification
Tests:
- TC-1: Key Derivation Decoupling Invariant (JWT Signing Secret vs Resting Data Vault Key)
- TC-2: PostgREST Anon Data API Column Isolation Invariant (users table sensitive columns)
- TC-3: Inactive Stale Device Silent Upgrade Notification Invariant (401 upgraded event trigger)
"""
import pytest
import os
import hashlib
import base64
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Header, Request, Depends
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel

# ---------------------------------------------------------
# TC-1: Key Derivation Decoupling Invariant
# ---------------------------------------------------------
def old_derive_vault_key(master_secret: str) -> bytes:
    """VULNERABLE: Direct 1:1 binding to session secret"""
    return hashlib.sha256(f"tabiji-recovery-vault-salt-{master_secret}".encode()).digest()


def hardened_get_vault_master_key(env_dict: dict, session_secret: str) -> str:
    """HARDENED: Decoupled via dedicated VAULT_MASTER_KEY or dedicated salt"""
    vault_secret = env_dict.get("VAULT_MASTER_KEY")
    if vault_secret and len(vault_secret) >= 16:
        return vault_secret
    return hashlib.sha256(f"tabiji-dedicated-vault-salt-{session_secret}".encode()).hexdigest()


def hardened_derive_vault_key(master_secret: Optional[str] = None, env_dict: Optional[dict] = None, session_secret: Optional[str] = None) -> bytes:
    if master_secret:
        return hashlib.sha256(f"tabiji-recovery-vault-salt-{master_secret}".encode()).digest()
    env = env_dict or os.environ
    sec = session_secret or "default_secret"
    key_str = hardened_get_vault_master_key(env, sec)
    return hashlib.sha256(f"tabiji-recovery-vault-salt-{key_str}".encode()).digest()


def encrypt_payload(plaintext: str, key: bytes) -> str:
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("utf-8")


def decrypt_payload(encrypted: Optional[str], key: bytes) -> Optional[str]:
    if not encrypted:
        return None
    try:
        raw = base64.b64decode(encrypted.encode("utf-8"))
        if len(raw) < 28:
            return None
        nonce = raw[:12]
        ct = raw[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
    except Exception:
        return None


def test_tc1_key_derivation_decoupling():
    """
    Simulates JWT signing secret rotation:
    - In vulnerable model: Rotating SESSION_SECRET breaks vault decryption.
    - In hardened model: VAULT_MASTER_KEY protects vault decryption across JWT rotations.
    """
    raw_key = "tbj_rec_11223344_0123456789abcdef0123456789abcdef"
    initial_session_secret = "initial_jwt_session_secret_key_2026"
    rotated_session_secret = "emergency_rotated_jwt_secret_key_2026"

    # 1. Vulnerable Model Failure Demonstration
    vuln_vault_key_1 = old_derive_vault_key(initial_session_secret)
    encrypted_payload_vuln = encrypt_payload(raw_key, vuln_vault_key_1)
    
    vuln_vault_key_2 = old_derive_vault_key(rotated_session_secret)
    decrypted_after_rotation_vuln = decrypt_payload(encrypted_payload_vuln, vuln_vault_key_2)
    assert decrypted_after_rotation_vuln is None, "Vulnerable model should fail decryption after JWT secret rotation!"

    # 2. Hardened Model Success Demonstration
    env = {"VAULT_MASTER_KEY": "permanent_vault_master_key_32_bytes_safe"}
    hardened_key_1 = hardened_derive_vault_key(env_dict=env, session_secret=initial_session_secret)
    encrypted_payload_hardened = encrypt_payload(raw_key, hardened_key_1)

    # JWT rotated, but VAULT_MASTER_KEY remains constant
    hardened_key_2 = hardened_derive_vault_key(env_dict=env, session_secret=rotated_session_secret)
    decrypted_after_rotation_hardened = decrypt_payload(encrypted_payload_hardened, hardened_key_2)
    assert decrypted_after_rotation_hardened == raw_key, "Hardened model must preserve vault decryptability across JWT secret rotation!"


# ---------------------------------------------------------
# TC-2: PostgREST Anon Data API Column Isolation Invariant
# ---------------------------------------------------------
def test_tc2_anon_column_isolation():
    """
    Simulates PostgREST column projection rules:
    - Anon role must only be permitted to query safe public columns (id, name, created_at).
    - Querying sensitive columns (recovery_key_id, recovery_secret_hash, recovery_key_encrypted) must be rejected.
    """
    all_columns = {
        "id": "11111111-2222-3333-4444-555555555555",
        "name": "Alice",
        "created_at": "2026-10-23T00:00:00Z",
        "recovery_key_id": "11223344",
        "recovery_secret_hash": "deadbeef" * 8,
        "recovery_key_encrypted": "base64encryptedblob=="
    }
    allowed_anon_columns = {"id", "name", "created_at"}

    def postgrest_select_filter(role: str, requested_columns: list[str]) -> dict:
        if role == "anon":
            for col in requested_columns:
                if col not in allowed_anon_columns:
                    raise PermissionError(f"Permission denied for column '{col}' of relation 'users'")
            return {k: all_columns[k] for k in requested_columns if k in allowed_anon_columns}
        return {k: all_columns[k] for k in requested_columns}

    # Anon queries public profile: Allowed
    public_res = postgrest_select_filter("anon", ["id", "name"])
    assert public_res == {"id": "11111111-2222-3333-4444-555555555555", "name": "Alice"}

    # Anon attempts to dump recovery_secret_hash: Blocked
    with pytest.raises(PermissionError) as exc:
        postgrest_select_filter("anon", ["id", "recovery_secret_hash"])
    assert "recovery_secret_hash" in str(exc.value)


# ---------------------------------------------------------
# TC-3: Inactive Stale Device Silent Upgrade Notification Invariant
# ---------------------------------------------------------
def test_tc3_inactive_device_upgrade_signal():
    """
    Simulates backend /api/auth/session returning 401 with 'upgraded' detail
    when a stale device requests exchange with an old UUID, and verifies client dispatch logic.
    """
    app = FastAPI()

    # User in DB is already upgraded
    db_users = {
        "legacy-user-uuid-1234": {
            "id": "legacy-user-uuid-1234",
            "recovery_secret_hash": "existing_hash",
            "credential_version": 2
        }
    }

    class SessionReq(BaseModel):
        recovery_key: Optional[str] = None

    @app.post("/api/auth/session")
    def session_exchange(req: SessionReq):
        key = req.recovery_key
        if key in db_users:
            if db_users[key].get("recovery_secret_hash"):
                raise HTTPException(
                    status_code=401,
                    detail="Account already upgraded. Please use your modern recovery key (tbj_rec_*)."
                )
        return {"token": "dummy_token"}

    client = TestClient(app)

    # 1. Stale device calls session exchange with legacy UUID
    res = client.post("/api/auth/session", json={"recovery_key": "legacy-user-uuid-1234"})
    assert res.status_code == 401
    detail = res.json().get("detail", "")
    assert "already upgraded" in detail

    # 2. Client-side handling simulation
    dispatched_events = []
    def client_handle_session_response(status_code: int, error_detail: str):
        if status_code == 401 and "upgraded" in error_detail.lower():
            dispatched_events.append("tabiji:credential_upgrade_required")

    client_handle_session_response(res.status_code, detail)
    assert "tabiji:credential_upgrade_required" in dispatched_events
