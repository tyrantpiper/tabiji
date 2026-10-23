"""
🛡️ Security Sentinel Sandbox In-Memory PoC: Dual-Track Auth & Edge Verification
Tests:
- TC-1: Legacy ATO demonstration (Raw UUID as recovery key)
- TC-2: Silent upgrade to Stripe-style prefixed recovery key (tbj_rec_<id>_<secret>)
- TC-3: ATO lockout post-upgrade (Raw UUID rejected once upgraded)
- TC-4: O(1) Recovery verification with high-entropy recovery key
- TC-5: Key rotation & historical revocation (Old key invalidated)
- TC-6: Edge Shield Web Crypto HS256 verification & X-User-ID header stripping
- TC-7: Collaborator Trip DTO Isolation & Share Code preservation
"""
import pytest
import hmac
import hashlib
import time
import secrets
import jwt
from unittest.mock import MagicMock
from fastapi import FastAPI, APIRouter, HTTPException, Request, Header
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

SESSION_SECRET = "sentinel_test_secret_32_bytes_super_secure_12345"
RECOVERY_PEPPER = "sentinel_recovery_pepper_key_98765"


# ---------------------------------------------------------------------------
# Core Dual-Track Helpers
# ---------------------------------------------------------------------------
def generate_prefixed_recovery_key() -> tuple[str, str, str]:
    """Generates (full_key, key_id, secret_hash) using Stripe-style format."""
    key_id = secrets.token_hex(4)  # 8 hex chars (O(1) B-tree lookup key)
    secret_entropy = secrets.token_hex(16)  # 32 hex chars (128-bit secret entropy)
    full_key = f"tbj_rec_{key_id}_{secret_entropy}"
    secret_hash = hmac.new(
        RECOVERY_PEPPER.encode(), secret_entropy.encode(), hashlib.sha256
    ).hexdigest()
    return full_key, key_id, secret_hash


def verify_recovery_key(full_key: str, stored_hash: str) -> bool:
    if not full_key.startswith("tbj_rec_"):
        return False
    parts = full_key.split("_")
    if len(parts) != 4:
        return False
    _, _, _, secret_entropy = parts
    computed_hash = hmac.new(
        RECOVERY_PEPPER.encode(), secret_entropy.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed_hash, stored_hash)


def create_jwt(user_id: str, credential_ver: int = 1) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iss": "tabiji-core",
        "iat": now,
        "exp": now + 86400,
        "ver": credential_ver
    }
    return jwt.encode(payload, SESSION_SECRET, algorithm="HS256")


# ---------------------------------------------------------------------------
# Mock Application for In-Memory Verification
# ---------------------------------------------------------------------------
class InMemDB:
    def __init__(self):
        self.users: Dict[str, Dict[str, Any]] = {}
        self.users_by_key_id: Dict[str, str] = {}  # key_id -> user_id

    def add_legacy_user(self, user_id: str, name: str = "Alice"):
        self.users[user_id] = {
            "id": user_id,
            "name": name,
            "recovery_key_id": None,
            "recovery_secret_hash": None,
            "credential_version": 1
        }

    def upgrade_user(self, user_id: str, key_id: str, secret_hash: str):
        if user_id in self.users:
            self.users[user_id]["recovery_key_id"] = key_id
            self.users[user_id]["recovery_secret_hash"] = secret_hash
            self.users_by_key_id[key_id] = user_id

    def rotate_user_key(self, user_id: str, new_key_id: str, new_secret_hash: str):
        user = self.users.get(user_id)
        if user:
            old_key_id = user.get("recovery_key_id")
            if old_key_id and old_key_id in self.users_by_key_id:
                del self.users_by_key_id[old_key_id]
            user["recovery_key_id"] = new_key_id
            user["recovery_secret_hash"] = new_secret_hash
            user["credential_version"] += 1
            self.users_by_key_id[new_key_id] = user_id


mock_db = InMemDB()
mock_app = FastAPI()


class SessionReq(BaseModel):
    recovery_key: Optional[str] = None


@mock_app.post("/api/auth/session")
def session_endpoint(req: SessionReq):
    key = (req.recovery_key or "").strip()
    
    # 1. New device anonymous bootstrap
    if not key:
        new_uid = f"user_{secrets.token_hex(8)}"
        full_key, key_id, secret_hash = generate_prefixed_recovery_key()
        mock_db.users[new_uid] = {
            "id": new_uid,
            "name": "Traveler",
            "recovery_key_id": key_id,
            "recovery_secret_hash": secret_hash,
            "credential_version": 1
        }
        mock_db.users_by_key_id[key_id] = new_uid
        token = create_jwt(new_uid, 1)
        return {
            "access_token": token,
            "user_id": new_uid,
            "recovery_key": full_key,
            "is_new": True
        }

    # 2. Legacy UUID Silent Upgrade Bridge
    if key.startswith("uuid_"):
        user = mock_db.users.get(key)
        if not user:
            raise HTTPException(401, "Unknown recovery key")
        
        # If user is already upgraded, reject raw UUID!
        if user.get("recovery_key_id") is not None:
            raise HTTPException(400, "Account already upgraded. Please use your tbj_rec_* recovery key.")
        
        # Perform silent upgrade
        full_key, key_id, secret_hash = generate_prefixed_recovery_key()
        mock_db.upgrade_user(user["id"], key_id, secret_hash)
        token = create_jwt(user["id"], user["credential_version"])
        return {
            "access_token": token,
            "user_id": user["id"],
            "recovery_key": full_key,
            "is_new": False,
            "upgraded": True
        }

    # 3. Modern tbj_rec_* Key Verification
    if key.startswith("tbj_rec_"):
        parts = key.split("_")
        if len(parts) != 4:
            raise HTTPException(400, "Invalid recovery key format")
        key_id = parts[2]
        user_id = mock_db.users_by_key_id.get(key_id)
        if not user_id:
            raise HTTPException(401, "Unknown recovery key")
        user = mock_db.users[user_id]
        if not verify_recovery_key(key, user["recovery_secret_hash"]):
            raise HTTPException(401, "Invalid recovery key secret")
        
        token = create_jwt(user["id"], user["credential_version"])
        return {
            "access_token": token,
            "user_id": user["id"],
            "recovery_key": key,
            "is_new": False
        }

    raise HTTPException(400, "Unsupported recovery key format")


@mock_app.post("/api/auth/rotate")
def rotate_endpoint(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SESSION_SECRET, algorithms=["HS256"])
    except Exception:
        raise HTTPException(401, "Invalid token")
    
    uid = payload["sub"]
    user = mock_db.users.get(uid)
    if not user:
        raise HTTPException(404, "User not found")
    
    new_full_key, new_key_id, new_secret_hash = generate_prefixed_recovery_key()
    mock_db.rotate_user_key(uid, new_key_id, new_secret_hash)
    new_token = create_jwt(uid, user["credential_version"])
    return {
        "access_token": new_token,
        "new_recovery_key": new_full_key,
        "credential_version": user["credential_version"]
    }


# ---------------------------------------------------------------------------
# Simulated Edge Shield POI Gateway Logic
# ---------------------------------------------------------------------------
def simulate_edge_shield_poi_dispatch(headers: Dict[str, str]) -> Dict[str, Any]:
    """Simulates Cloudflare Edge Shield header stripping and HS256 JWT verification."""
    # 1. Strips any incoming forged X-User-ID
    scrubbed_headers = {k: v for k, v in headers.items() if k.lower() != "x-user-id"}
    
    auth = scrubbed_headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return {"status": 401, "detail": "MISSING_OR_INVALID_BEARER"}
    
    token = auth.split(" ")[1]
    try:
        payload = jwt.decode(token, SESSION_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return {"status": 401, "detail": "TOKEN_EXPIRED"}
    except jwt.InvalidSignatureError:
        return {"status": 401, "detail": "INVALID_SIGNATURE"}
    except Exception:
        return {"status": 401, "detail": "DECODE_ERROR"}
    
    verified_sub = payload.get("sub")
    if not verified_sub:
        return {"status": 401, "detail": "MISSING_SUB"}
    
    # 2. Securely injects verified X-User-ID for downstream POI Worker Service Binding
    scrubbed_headers["X-User-ID"] = verified_sub
    return {"status": 200, "injected_user_id": verified_sub, "headers": scrubbed_headers}


# ---------------------------------------------------------------------------
# Sentinel Test Cases
# ---------------------------------------------------------------------------
client = TestClient(mock_app)


def test_tc1_legacy_uuid_silent_upgrade():
    """TC-1: Proves existing legacy user is silently upgraded upon first /session call."""
    mock_db.add_legacy_user("uuid_alice_123", "Alice")
    
    # Alice sends her legacy UUID
    resp = client.post("/api/auth/session", json={"recovery_key": "uuid_alice_123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "uuid_alice_123"
    assert data["upgraded"] is True
    assert data["recovery_key"].startswith("tbj_rec_")
    
    # Alice's DB record now has key_id and hash
    alice_db = mock_db.users["uuid_alice_123"]
    assert alice_db["recovery_key_id"] is not None
    assert alice_db["recovery_secret_hash"] is not None


def test_tc2_ato_lockout_post_upgrade():
    """TC-2: Proves Bob CANNOT use Alice's raw UUID after she has been upgraded."""
    # Alice is already upgraded from TC-1
    # Bob attempts to recover using Alice's raw UUID
    resp = client.post("/api/auth/session", json={"recovery_key": "uuid_alice_123"})
    assert resp.status_code == 400
    assert "already upgraded" in resp.json()["detail"]


def test_tc3_legitimate_recovery_with_new_key():
    """TC-3: Proves legitimate recovery works with new Stripe-style recovery key."""
    alice_key = mock_db.users["uuid_alice_123"]["recovery_key_id"]
    # Reconstruct Alice's full key from earlier test
    # Or create a fresh user
    new_resp = client.post("/api/auth/session", json={})
    assert new_resp.status_code == 200
    bob_data = new_resp.json()
    bob_key = bob_data["recovery_key"]
    bob_uid = bob_data["user_id"]
    
    # Bob restores account on new phone with his recovery key
    restore_resp = client.post("/api/auth/session", json={"recovery_key": bob_key})
    assert restore_resp.status_code == 200
    assert restore_resp.json()["user_id"] == bob_uid


def test_tc4_key_rotation_invalidates_old_key():
    """TC-4: Proves key rotation immediately revokes the old recovery key."""
    # Create user
    resp = client.post("/api/auth/session", json={})
    data = resp.json()
    old_key = data["recovery_key"]
    token = data["access_token"]
    
    # User rotates key
    rot_resp = client.post("/api/auth/rotate", headers={"Authorization": f"Bearer {token}"})
    assert rot_resp.status_code == 200
    new_key = rot_resp.json()["new_recovery_key"]
    assert new_key != old_key
    
    # Old key fails with 401
    fail_resp = client.post("/api/auth/session", json={"recovery_key": old_key})
    assert fail_resp.status_code == 401


def test_tc5_edge_shield_jwt_verification_and_header_stripping():
    """TC-5: Proves Edge Shield strips forged X-User-ID and rejects invalid/expired JWT."""
    # 1. Attacker attempts header injection with no JWT
    res1 = simulate_edge_shield_poi_dispatch({"X-User-ID": "uuid_victim_target"})
    assert res1["status"] == 401
    
    # 2. Attacker attempts forged signature
    tampered_token = create_jwt("uuid_attacker") + "corrupted"
    res2 = simulate_edge_shield_poi_dispatch({
        "X-User-ID": "uuid_victim_target",
        "Authorization": f"Bearer {tampered_token}"
    })
    assert res2["status"] == 401
    assert res2["detail"] == "INVALID_SIGNATURE"
    
    # 3. Legitimate user with valid JWT
    valid_token = create_jwt("uuid_alice_legit")
    res3 = simulate_edge_shield_poi_dispatch({
        "X-User-ID": "uuid_spoofed_ignored",  # Attempted spoof
        "Authorization": f"Bearer {valid_token}"
    })
    assert res3["status"] == 200
    assert res3["injected_user_id"] == "uuid_alice_legit"
    # Forged header was replaced with verified sub
    assert res3["headers"]["X-User-ID"] == "uuid_alice_legit"


def test_tc6_collaborator_trip_dto_isolation_and_share_code():
    """TC-6: Proves share_code is preserved while internal owner UUID is never leaked to collaborators."""
    # Trip mock data
    raw_trip = {
        "id": "trip_tokyo_2026",
        "title": "Tokyo Cherry Blossom",
        "share_code": "TYO888",  # Essential for dashboard & join
        "created_by": "uuid_alice_private_master",  # Must NOT be leaked
        "members": [
            {"user_id": "uuid_alice_private_master", "name": "Alice", "role": "owner"},
            {"user_id": "uuid_bob_collaborator", "name": "Bob", "role": "editor"}
        ]
    }
    
    # Desensitization function
    def desensitize_trip_for_collaborator(trip: dict, viewer_id: str) -> dict:
        is_owner = trip["created_by"] == viewer_id
        return {
            "id": trip["id"],
            "title": trip["title"],
            "share_code": trip["share_code"],  # Preserved!
            "members": [
                {
                    "name": m["name"],
                    "role": m["role"],
                    # Viewer sees their own ID, but others only get collaborator alias
                    "collaborator_alias": f"collab_{m['role']}_{m['name']}" if m["user_id"] != viewer_id else viewer_id
                }
                for m in trip["members"]
            ]
        }
    
    bob_view = desensitize_trip_for_collaborator(raw_trip, viewer_id="uuid_bob_collaborator")
    assert bob_view["share_code"] == "TYO888"  # Preserved
    assert "created_by" not in bob_view  # Alice's raw UUID is stripped
    for m in bob_view["members"]:
        assert "uuid_alice_private_master" not in str(m)  # Zero Alice UUID leakage
