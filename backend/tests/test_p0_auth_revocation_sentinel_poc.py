"""
🛡️ Security Sentinel Sandbox In-Memory PoC: P0 Auth Revocation, Vault Guard & Concurrency Healing
Tests:
- TC-1: Vulnerability Reproduction: Unpatched vault endpoint exposes rotated credentials to stale tokens (ver 1).
- TC-2: Mantis Patch Verification: Patched endpoint rejects stale token (ver 1 < db_ver 2) with 401 Unauthorized.
- TC-3: Legitimate Key Sync: Token with matching version (ver 2 == db_ver 2) receives decrypted recovery key.
- TC-4: Legacy Dirty Data Resilience: When database credential_version is None, defaults safely to 1.
- TC-5: Concurrent Silent Upgrade Self-Healing: Optimistic lock loser detects empty update rows and syncs winner's key.
- TC-6: Full Multi-Device Rotation, Revocation & Re-anchoring Lifecycle.
- TC-7: Vulnerability Reproduction: Unpatched endpoint exposes victim's JWT over the wire and leaks user existence oracle.
- TC-8: Mantis Patch Verification: Patched endpoint asserts expected_user_id server-side before JWT generation and outputs uniform 401 error.
"""

import time
import base64
import os
import hashlib
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


def decrypt_recovery_key(encrypted_payload: str, vault_key: bytes) -> Optional[str]:
    raw_data = base64.b64decode(encrypted_payload.encode("utf-8"))
    nonce = raw_data[:12]
    ciphertext = raw_data[12:]
    aesgcm = AESGCM(vault_key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


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
# Test Case 1: Unpatched Logic Vulnerability Reproduction
# ---------------------------------------------------------------------------
def test_tc1_unpatched_vault_exposes_rotated_key():
    """VULNERABILITY REPRODUCTION: Unpatched vault returns ver:2 key to ver:1 token."""
    app = FastAPI()
    db = {
        "user_alice": {
            "id": "user_alice",
            "recovery_key_encrypted": encrypt_recovery_key("tbj_rec_v2_new_secret_key_9999", VAULT_KEY),
            "credential_version": 2  # Alice rotated key
        }
    }

    # Unpatched implementation of get_verified_user_with_grace (returns only sub)
    def unpatched_get_user(authorization: Optional[str] = Header(None)) -> str:
        token = authorization.split(" ")[1]
        payload = jwt.decode(token, SECRET, algorithms=["HS256"], options={"verify_exp": False})
        return payload["sub"]

    @app.get("/api/auth/credential")
    def unpatched_credential_endpoint(user_id: str = Depends(unpatched_get_user)):
        user = db.get(user_id)
        enc = user["recovery_key_encrypted"]
        return {"recovery_key": decrypt_recovery_key(enc, VAULT_KEY)}

    client = TestClient(app)
    # Stolen/leaked pre-rotation token (ver: 1)
    stale_token_v1 = make_test_jwt("user_alice", ver=1)

    res = client.get("/api/auth/credential", headers={"Authorization": f"Bearer {stale_token_v1}"})
    # Flaw: Unpatched returns 200 with the NEW key, completely piercing rotation!
    assert res.status_code == 200
    assert res.json()["recovery_key"] == "tbj_rec_v2_new_secret_key_9999"


# ---------------------------------------------------------------------------
# Test Case 2 & 3: Patched Mantis Guard (VerifiedSession + Version Gate)
# ---------------------------------------------------------------------------
class VerifiedSession(BaseModel):
    user_id: str
    token_version: int


def patched_get_verified_session(authorization: Optional[str] = Header(None)) -> VerifiedSession:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    token = authorization.split(" ")[1].strip()
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"], issuer="tabiji-core", options={"verify_exp": False})
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    return VerifiedSession(
        user_id=payload["sub"],
        token_version=int(payload.get("ver") or 1)
    )


def test_tc2_patched_vault_rejects_revoked_stale_token():
    """MANTIS PATCH VERIFICATION: Patched endpoint rejects ver:1 token with 401."""
    app = FastAPI()
    db = {
        "user_alice": {
            "id": "user_alice",
            "recovery_key_encrypted": encrypt_recovery_key("tbj_rec_v2_new_secret_key_9999", VAULT_KEY),
            "credential_version": 2
        }
    }

    @app.get("/api/auth/credential")
    def patched_credential_endpoint(session: VerifiedSession = Depends(patched_get_verified_session)):
        user = db.get(session.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        db_ver = int(user.get("credential_version") or 1)
        if session.token_version < db_ver:
            raise HTTPException(
                status_code=401,
                detail="Credential has been rotated. This session is revoked."
            )
        
        enc = user["recovery_key_encrypted"]
        return {
            "recovery_key": decrypt_recovery_key(enc, VAULT_KEY),
            "credential_version": db_ver
        }

    client = TestClient(app)

    # 1. Attacker using stale token (ver 1 < db_ver 2) -> REJECTED (401)
    stale_token_v1 = make_test_jwt("user_alice", ver=1)
    res_stale = client.get("/api/auth/credential", headers={"Authorization": f"Bearer {stale_token_v1}"})
    assert res_stale.status_code == 401
    assert "revoked" in res_stale.json()["detail"].lower()

    # 2. Legitimate user using fresh token (ver 2 == db_ver 2) -> ACCEPTED (200)
    fresh_token_v2 = make_test_jwt("user_alice", ver=2)
    res_fresh = client.get("/api/auth/credential", headers={"Authorization": f"Bearer {fresh_token_v2}"})
    assert res_fresh.status_code == 200
    assert res_fresh.json()["recovery_key"] == "tbj_rec_v2_new_secret_key_9999"
    assert res_fresh.json()["credential_version"] == 2


def test_tc4_legacy_dirty_data_version_none_safely_defaults():
    """DIRTY DATA RESILIENCE: credential_version = None does not crash and defaults to 1."""
    app = FastAPI()
    db = {
        "user_legacy": {
            "id": "user_legacy",
            "recovery_key_encrypted": encrypt_recovery_key("tbj_rec_v1_legacy_key", VAULT_KEY),
            "credential_version": None  # Legacy row without migration
        }
    }

    @app.get("/api/auth/credential")
    def patched_credential_endpoint(session: VerifiedSession = Depends(patched_get_verified_session)):
        user = db.get(session.user_id)
        db_ver = int(user.get("credential_version") or 1)
        if session.token_version < db_ver:
            raise HTTPException(status_code=401, detail="Session revoked")
        enc = user["recovery_key_encrypted"]
        return {"recovery_key": decrypt_recovery_key(enc, VAULT_KEY), "credential_version": db_ver}

    client = TestClient(app)
    token_v1 = make_test_jwt("user_legacy", ver=1)
    res = client.get("/api/auth/credential", headers={"Authorization": f"Bearer {token_v1}"})
    assert res.status_code == 200
    assert res.json()["credential_version"] == 1
    assert res.json()["recovery_key"] == "tbj_rec_v1_legacy_key"


# ---------------------------------------------------------------------------
# Test Case 5: Concurrent Silent Upgrade Self-Healing Simulation
# ---------------------------------------------------------------------------
def test_tc5_concurrent_silent_upgrade_self_healing():
    """CONCURRENCY RACE RESILIENCE: Loser of optimistic lock auto-syncs winner's key."""
    # Shared DB row starting with no recovery key (legacy user)
    db_state = {
        "id": "user_legacy_concurrency",
        "recovery_key_id": None,
        "recovery_key_encrypted": None,
        "credential_version": None
    }

    def simulate_silent_upgrade(device_name: str, new_key: str):
        # Optimistic update: only updates if recovery_key_id is None
        if db_state["recovery_key_id"] is None:
            # Device wins race
            db_state["recovery_key_id"] = f"key_{device_name}"
            db_state["recovery_key_encrypted"] = encrypt_recovery_key(new_key, VAULT_KEY)
            db_state["credential_version"] = 1
            updated = True
        else:
            updated = False

        if not updated:
            # Auto-healing: fetch DB state and decrypt winner's key
            synced_key = decrypt_recovery_key(db_state["recovery_key_encrypted"], VAULT_KEY)
            return {"recovery_key": synced_key, "winner": False}
        return {"recovery_key": new_key, "winner": True}

    # Device A executes first
    res_a = simulate_silent_upgrade("DeviceA", "tbj_rec_deviceA_key_1111")
    assert res_a["winner"] is True
    assert res_a["recovery_key"] == "tbj_rec_deviceA_key_1111"

    # Device B executes second concurrently
    res_b = simulate_silent_upgrade("DeviceB", "tbj_rec_deviceB_key_2222")
    assert res_b["winner"] is False
    # Crucial assertion: Device B self-heals and receives Device A's persisted key!
    assert res_b["recovery_key"] == "tbj_rec_deviceA_key_1111"
    assert db_state["recovery_key_id"] == "key_DeviceA"


# ---------------------------------------------------------------------------
# Test Case 6: Full Multi-Device Rotation, Revocation & Re-anchoring Lifecycle
# ---------------------------------------------------------------------------
def test_tc6_full_device_lifecycle_reauth():
    """
    COMPLETE LIFECYCLE:
    1. Device A rotates key from Key 1 -> Key 2 (ver 1 -> ver 2).
    2. Device B (dormant/offline) attempts to sync with stale JWT (ver 1) -> 401.
    3. Device B attempts to get credential with stale JWT (ver 1) -> 401.
    4. Device B obtains Key 2 and calls /api/auth/session to exchange.
    5. Server returns fresh JWT (ver 2).
    6. Device B syncs mutations using fresh JWT -> 200 OK.
    """
    app = FastAPI()

    # In-memory DB simulating Supabase tables
    db_users = {
        "user_alice": {
            "id": "user_alice",
            "recovery_key_id": "keyid2222",
            "recovery_secret_hash": hashlib.sha256("tbj_rec_keyid2222_entropy2222".encode()).hexdigest(),
            "recovery_key_encrypted": encrypt_recovery_key("tbj_rec_keyid2222_entropy2222", VAULT_KEY),
            "credential_version": 2
        }
    }
    user_trips = []

    @app.get("/api/auth/credential")
    def credential_endpoint(session: VerifiedSession = Depends(patched_get_verified_session)):
        user = db_users.get(session.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        db_ver = int(user.get("credential_version") or 1)
        if session.token_version < db_ver:
            raise HTTPException(status_code=401, detail="Credential rotated, session revoked")
        return {"recovery_key": decrypt_recovery_key(user["recovery_key_encrypted"], VAULT_KEY)}

    @app.post("/api/auth/session")
    def session_endpoint(body: Dict[str, str]):
        raw_key = body.get("recovery_key", "").strip()
        parts = raw_key.split("_")
        if len(parts) < 4 or parts[0] != "tbj" or parts[1] != "rec":
            raise HTTPException(status_code=400, detail="Invalid format")
        key_id = parts[2]
        # Match user
        user = next((u for u in db_users.values() if u.get("recovery_key_id") == key_id), None)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid recovery key")
        # Verify hash
        if user["recovery_secret_hash"] != hashlib.sha256(raw_key.encode()).hexdigest():
            raise HTTPException(status_code=401, detail="Hash mismatch")
        
        token = make_test_jwt(user["id"], ver=user["credential_version"])
        return {
            "access_token": token,
            "user_id": user["id"],
            "recovery_key": raw_key
        }

    @app.post("/api/trips/sync")
    def trip_sync_endpoint(
        body: Dict[str, Any],
        session: VerifiedSession = Depends(patched_get_verified_session)
    ):
        user = db_users.get(session.user_id)
        if not user or session.token_version < int(user.get("credential_version") or 1):
            raise HTTPException(status_code=401, detail="Session expired or rotated")
        user_trips.append(body)
        return {"status": "synced", "total": len(user_trips)}

    client = TestClient(app)

    # 1. Device B has old token ver: 1
    device_b_stale_token = make_test_jwt("user_alice", ver=1)

    # 2. Device B tries to sync offline trip item
    sync_res = client.post(
        "/api/trips/sync",
        headers={"Authorization": f"Bearer {device_b_stale_token}"},
        json={"title": "Tokyo Tower Sunset", "time": "18:00"}
    )
    assert sync_res.status_code == 401
    assert len(user_trips) == 0  # No trip synced yet

    # 3. Device B tries to fetch credential with stale token
    cred_res = client.get(
        "/api/auth/credential",
        headers={"Authorization": f"Bearer {device_b_stale_token}"}
    )
    assert cred_res.status_code == 401

    # 4. Device B takes Key 2 from Device A
    key_2 = "tbj_rec_keyid2222_entropy2222"
    exchange_res = client.post("/api/auth/session", json={"recovery_key": key_2})
    assert exchange_res.status_code == 200
    data = exchange_res.json()
    assert data["user_id"] == "user_alice"
    device_b_new_token = data["access_token"]

    # 5. Device B retries syncing offline trip with new token
    sync_res_new = client.post(
        "/api/trips/sync",
        headers={"Authorization": f"Bearer {device_b_new_token}"},
        json={"title": "Tokyo Tower Sunset", "time": "18:00"}
    )
    assert sync_res_new.status_code == 200
    assert sync_res_new.json()["status"] == "synced"
    assert len(user_trips) == 1
    assert user_trips[0]["title"] == "Tokyo Tower Sunset"


# ---------------------------------------------------------------------------
# Test Case 7: Vulnerability Reproduction: Wire-Level JWT Exposure & Account Oracle
# ---------------------------------------------------------------------------
def test_tc7_wire_jwt_leak_and_oracle_enumeration_reproduction():
    """
    VULNERABILITY REPRODUCTION:
    Unpatched endpoint sends victim's JWT over HTTP when attacker probes victim's recovery key.
    Differentiated error messages also confirm account existence (Oracle leak).
    """
    app = FastAPI()
    db_users = {
        "user_alice": {
            "id": "11111111-1111-1111-1111-111111111111",
            "recovery_key_id": "keyalice",
            "recovery_secret_hash": hashlib.sha256("tbj_rec_keyalice_secretalice1111222233334444".encode()).hexdigest(),
            "credential_version": 2
        },
        "user_bob": {
            "id": "22222222-2222-2222-2222-222222222222",
            "recovery_key_id": "keybob01",
            "recovery_secret_hash": hashlib.sha256("tbj_rec_keybob01_secretbob1111222233334444".encode()).hexdigest(),
            "credential_version": 1
        }
    }

    # Unpatched endpoint: Does not take or enforce expected_user_id
    class UnpatchedSessionRequest(BaseModel):
        recovery_key: str

    @app.post("/api/auth/session")
    def unpatched_session_endpoint(req: UnpatchedSessionRequest):
        raw_key = req.recovery_key.strip()
        parts = raw_key.split("_")
        if len(parts) != 4 or parts[0] != "tbj" or parts[1] != "rec":
            raise HTTPException(status_code=400, detail="Invalid format")
        key_id = parts[2]
        user = next((u for u in db_users.values() if u["recovery_key_id"] == key_id), None)
        if not user:
            raise HTTPException(status_code=404, detail="引繼碼不存在")
        if user["recovery_secret_hash"] != hashlib.sha256(raw_key.encode()).hexdigest():
            raise HTTPException(status_code=401, detail="密碼錯誤")

        # Flaw 1: Always generates JWT for whatever user the key belongs to!
        token = make_test_jwt(user["id"], ver=user["credential_version"])
        return {
            "access_token": token,
            "user_id": user["id"],
            "recovery_key": raw_key
        }

    client = TestClient(app)

    # Attacker (Alice's stolen/untrusted client) submits Bob's recovery key
    bob_key = "tbj_rec_keybob01_secretbob1111222233334444"
    res = client.post("/api/auth/session", json={"recovery_key": bob_key})

    # Flaw 1 Proof: 200 OK returned with Bob's JWT transmitted over the wire!
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["user_id"] == "22222222-2222-2222-2222-222222222222"
    assert "access_token" in res_data
    assert res_data["access_token"] is not None

    # Attacker can inspect and decode Bob's JWT directly from HTTP payload!
    decoded = jwt.decode(res_data["access_token"], SECRET, algorithms=["HS256"], options={"verify_exp": False})
    assert decoded["sub"] == "22222222-2222-2222-2222-222222222222"

    # Flaw 2 Proof (Oracle Enumeration): Different errors leak existence
    res_unknown = client.post("/api/auth/session", json={"recovery_key": "tbj_rec_keynonex_secret1111222233334444"})
    assert res_unknown.status_code == 404
    assert res_unknown.json()["detail"] == "引繼碼不存在"  # Leaks non-existence!


# ---------------------------------------------------------------------------
# Test Case 8: Mantis Patch Verification: Server-Side expected_user_id & Zero-Token Gate
# ---------------------------------------------------------------------------
def test_tc8_mantis_patch_server_expected_user_guard_and_uniform_401():
    """
    MANTIS PATCH VERIFICATION:
    1. Server accepts expected_user_id parameter.
    2. Before generating ANY token, server checks user['id'].lower() == expected_user_id.lower().
    3. If mismatched, returns 401 with UNIFORM generic error.
    4. HTTP Response payload contains ZERO tokens (access_token is NEVER created or serialized).
    5. Legacy UUID path also enforces expected_user_id check.
    6. Non-existent keys, bad hashes, and mismatched users all return identical 401.
    """
    app = FastAPI()
    db_users = {
        "user_alice": {
            "id": "11111111-1111-1111-1111-111111111111",
            "recovery_key_id": "keyalice",
            "recovery_secret_hash": hashlib.sha256("tbj_rec_keyalice_secretalice1111222233334444".encode()).hexdigest(),
            "credential_version": 2
        },
        "user_bob": {
            "id": "22222222-2222-2222-2222-222222222222",
            "recovery_key_id": "keybob01",
            "recovery_secret_hash": hashlib.sha256("tbj_rec_keybob01_secretbob1111222233334444".encode()).hexdigest(),
            "credential_version": 1
        }
    }

    UNIFORM_ERROR = "引繼碼驗證失敗，無法在此設備恢復同步。請確認引繼碼是否正確。"

    class PatchedSessionRequest(BaseModel):
        recovery_key: Optional[str] = None
        expected_user_id: Optional[str] = None

    @app.post("/api/auth/session")
    def patched_session_endpoint(req: PatchedSessionRequest):
        raw_key = (req.recovery_key or "").strip()

        # Modern recovery key path
        parts = raw_key.split("_")
        if len(parts) == 4 and parts[0] == "tbj" and parts[1] == "rec":
            key_id = parts[2]
            user = next((u for u in db_users.values() if u["recovery_key_id"] == key_id), None)
            if not user or user["recovery_secret_hash"] != hashlib.sha256(raw_key.encode()).hexdigest():
                raise HTTPException(status_code=401, detail=UNIFORM_ERROR)
            
            # 🛡️ Server-Side Expected User ID Gate: BEFORE JWT issuance!
            if req.expected_user_id:
                if user["id"].strip().lower() != req.expected_user_id.strip().lower():
                    # REJECT BEFORE CREATING JWT!
                    raise HTTPException(status_code=401, detail=UNIFORM_ERROR)

            token = make_test_jwt(user["id"], ver=user["credential_version"])
            return {"access_token": token, "user_id": user["id"], "recovery_key": raw_key}

        # Legacy UUID path
        if len(raw_key) == 36 and "-" in raw_key:
            clean_uid = raw_key.lower()
            user = next((u for u in db_users.values() if u["id"].lower() == clean_uid), None)
            if not user:
                raise HTTPException(status_code=401, detail=UNIFORM_ERROR)
            
            # 🛡️ Legacy path also enforces expected_user_id
            if req.expected_user_id:
                if clean_uid != req.expected_user_id.strip().lower():
                    raise HTTPException(status_code=401, detail=UNIFORM_ERROR)

            token = make_test_jwt(user["id"], ver=user["credential_version"])
            return {"access_token": token, "user_id": user["id"], "recovery_key": raw_key}

        raise HTTPException(status_code=401, detail=UNIFORM_ERROR)

    client = TestClient(app)

    alice_uuid = "11111111-1111-1111-1111-111111111111"
    bob_key = "tbj_rec_keybob01_secretbob1111222233334444"

    # 1. Attacker on Alice's device tries Bob's key with expected_user_id = Alice
    res_mismatch = client.post("/api/auth/session", json={
        "recovery_key": bob_key,
        "expected_user_id": alice_uuid
    })
    # Must be HTTP 401
    assert res_mismatch.status_code == 401
    res_mismatch_body = res_mismatch.json()
    assert res_mismatch_body["detail"] == UNIFORM_ERROR
    # Wire-Level Defense Proof: ZERO token in payload!
    assert "access_token" not in res_mismatch_body
    assert "user_id" not in res_mismatch_body

    # 2. Unknown key also returns identical 401 & error string (Oracle Proof)
    res_unknown = client.post("/api/auth/session", json={
        "recovery_key": "tbj_rec_keynonex_secret1111222233334444",
        "expected_user_id": alice_uuid
    })
    assert res_unknown.status_code == 401
    assert res_unknown.json()["detail"] == UNIFORM_ERROR

    # 3. Bad hash also returns identical 401 & error string (Oracle Proof)
    res_bad_hash = client.post("/api/auth/session", json={
        "recovery_key": "tbj_rec_keybob01_secretwrong0000000000000000",
        "expected_user_id": alice_uuid
    })
    assert res_bad_hash.status_code == 401
    assert res_bad_hash.json()["detail"] == UNIFORM_ERROR

    # 4. Legacy UUID bypass attempt with mismatched expected_user_id is blocked
    bob_uuid = "22222222-2222-2222-2222-222222222222"
    res_legacy_mismatch = client.post("/api/auth/session", json={
        "recovery_key": bob_uuid,
        "expected_user_id": alice_uuid
    })
    assert res_legacy_mismatch.status_code == 401
    assert res_legacy_mismatch.json()["detail"] == UNIFORM_ERROR
    assert "access_token" not in res_legacy_mismatch.json()

    # 5. Legitimate Alice key re-auth with matching expected_user_id SUCCEEDS
    alice_key = "tbj_rec_keyalice_secretalice1111222233334444"
    res_legit = client.post("/api/auth/session", json={
        "recovery_key": alice_key,
        "expected_user_id": alice_uuid
    })
    assert res_legit.status_code == 200
    legit_data = res_legit.json()
    assert legit_data["user_id"] == alice_uuid
    assert "access_token" in legit_data
    token_payload = jwt.decode(legit_data["access_token"], SECRET, algorithms=["HS256"], options={"verify_exp": False})
    assert token_payload["sub"] == alice_uuid

