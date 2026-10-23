"""
🛡️ Security Sentinel Simulation: Status Quo Real-World Behavioral Telemetry
Simulates exact behavior of current production code without changes:
- SIM-1: Normal Multi-Device Seamless Convergence (Phone & Mac sync smoothly).
- SIM-2: Stolen Device Threat Model (Attacker holding stolen token extracts rotated key & retains access).
- SIM-3: Dormant Device (>90 days) Resilience vs Lockout.
"""

import time
import base64
import os
import hashlib
import jwt
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.testclient import TestClient
from pydantic import BaseModel
from typing import Optional


SECRET = "status_quo_simulation_secret_2026"
VAULT_KEY = hashlib.sha256(f"tabiji-recovery-vault-salt-{SECRET}".encode()).digest()


def encrypt_key(raw_key: str) -> str:
    aesgcm = AESGCM(VAULT_KEY)
    nonce = os.urandom(12)
    return base64.b64encode(nonce + aesgcm.encrypt(nonce, raw_key.encode("utf-8"), None)).decode("utf-8")


def decrypt_key(payload: str) -> str:
    raw = base64.b64decode(payload.encode("utf-8"))
    return AESGCM(VAULT_KEY).decrypt(raw[:12], raw[12:], None).decode("utf-8")


def create_token(uid: str, ver: int, age_days: float = 0) -> str:
    now = int(time.time())
    iat = int(now - (age_days * 86400))
    payload = {
        "sub": uid,
        "iss": "tabiji-core",
        "iat": iat,
        "exp": iat + (30 * 86400),
        "ver": ver,
        "type": "device_session"
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


# Exact Status Quo FastAPI implementation
app = FastAPI()

sim_db = {
    "alice": {
        "id": "alice",
        "recovery_key_id": "key_v1",
        "recovery_key_encrypted": encrypt_key("tbj_rec_v1_initial_key_1111222233334444"),
        "credential_version": 1
    }
}


def status_quo_get_verified_user(authorization: Optional[str] = Header(None)) -> str:
    """Exact logic from deps.py: Local HS256 decode, no DB check, no ver check."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"], issuer="tabiji-core", options={"require": ["exp"]})
        return payload["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def status_quo_get_verified_user_with_grace(authorization: Optional[str] = Header(None)) -> str:
    """Exact logic from auth.py:452: HS256 decode with 90-day grace, NO ver check."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"], issuer="tabiji-core")
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        try:
            payload = jwt.decode(token, SECRET, algorithms=["HS256"], issuer="tabiji-core", options={"verify_exp": False})
            now = int(time.time())
            if now - payload.get("iat", 0) <= 90 * 86400:
                return payload["sub"]
        except Exception:
            pass
    raise HTTPException(status_code=401, detail="Invalid token")


@app.get("/api/trips")
def get_trips(uid: str = Depends(status_quo_get_verified_user)):
    return {"status": "ok", "user": uid, "trips": ["Tokyo 2026", "Kyoto 2026"]}


@app.get("/api/auth/credential")
def get_credential(uid: str = Depends(status_quo_get_verified_user_with_grace)):
    user = sim_db.get(uid)
    return {
        "recovery_key": decrypt_key(user["recovery_key_encrypted"]),
        "credential_version": user["credential_version"]
    }


client = TestClient(app)


def test_sim1_multi_device_seamless_convergence():
    """SIM-1: Normal legitimate multi-device sync works 100% seamlessly."""
    # 1. Device A and B both start on Key 1
    token_device_a = create_token("alice", ver=1, age_days=1)
    token_device_b = create_token("alice", ver=1, age_days=1)

    # 2. Device A rotates key to Key 2
    sim_db["alice"]["recovery_key_id"] = "key_v2"
    sim_db["alice"]["recovery_key_encrypted"] = encrypt_key("tbj_rec_v2_new_fresh_key_5555666677778888")
    sim_db["alice"]["credential_version"] = 2

    # 3. Device B wakes up 5 days later and fetches latest key
    res_b = client.get("/api/auth/credential", headers={"Authorization": f"Bearer {token_device_b}"})
    assert res_b.status_code == 200
    # Device B seamlessly receives Key 2 without any user interruption!
    assert res_b.json()["recovery_key"] == "tbj_rec_v2_new_fresh_key_5555666677778888"


def test_sim2_stolen_phone_compromise_real_world_consequence():
    """SIM-2: Demonstrates the exact security cost of status quo when a phone is stolen."""
    # Alice's phone is stolen. The phone holds token_stolen (issued under ver: 1).
    token_stolen = create_token("alice", ver=1, age_days=2)

    # Alice discovers the loss and rotates credentials on her laptop to ver: 2
    sim_db["alice"]["recovery_key_id"] = "key_v2"
    sim_db["alice"]["recovery_key_encrypted"] = encrypt_key("tbj_rec_v2_alice_secret_new_key")
    sim_db["alice"]["credential_version"] = 2

    # --- Attacker Action 1: Reading business data ---
    # Attacker calls /api/trips with stolen token (ver: 1)
    res_trips = client.get("/api/trips", headers={"Authorization": f"Bearer {token_stolen}"})
    # [REALITY CHECK]: Trips are STILL accessible because deps.py does not verify version!
    assert res_trips.status_code == 200
    assert "Tokyo 2026" in res_trips.json()["trips"]

    # --- Attacker Action 2: Exfiltrating modern recovery key ---
    # Attacker's phone triggers background sync to /api/auth/credential
    res_cred = client.get("/api/auth/credential", headers={"Authorization": f"Bearer {token_stolen}"})
    # [REALITY CHECK]: Attacker is GIVEN the new key!
    assert res_cred.status_code == 200
    assert res_cred.json()["recovery_key"] == "tbj_rec_v2_alice_secret_new_key"
    assert res_cred.json()["credential_version"] == 2


def test_sim3_dormant_device_older_than_90_days():
    """SIM-3: Device dormant for 95 days is rejected by grace period endpoint."""
    old_token = create_token("alice", ver=1, age_days=95)
    res = client.get("/api/auth/credential", headers={"Authorization": f"Bearer {old_token}"})
    assert res.status_code == 401
