"""
🛡️ Security Sentinel Sandbox In-Memory PoC: AES-256-GCM Vault & Cross-Device Key Sync
Tests:
- TC-1: AES-256-GCM encryption & decryption fidelity (Plaintext tbj_rec_* restored 100%).
- TC-2: Cryptographic Tamper Defense (Ciphertext or Tag tampering triggers InvalidTag / DecryptionError).
- TC-3: Key Isolation (Wrong master key fails decryption).
- TC-4: Authorized Credential Endpoint Simulation (Valid JWT receives decrypted key; invalid JWT rejected 401).
- TC-5: Multi-Device Sync Simulation (Device A rotates, DB updates vault, Device B fetches latest key).
"""
import pytest
import os
import base64
import secrets
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.testclient import TestClient
from pydantic import BaseModel
from typing import Optional, Dict, Any


# ---------------------------------------------------------------------------
# Cryptographic Vault Engine Implementation
# ---------------------------------------------------------------------------
def derive_vault_key(master_secret: str) -> bytes:
    """Derives a deterministic 256-bit (32-byte) key for AES-GCM from server secret."""
    return hashlib.sha256(f"tabiji-recovery-vault-salt-{master_secret}".encode()).digest()


def encrypt_recovery_key(recovery_key: str, vault_key: bytes) -> str:
    """
    Encrypts a recovery key using AES-256-GCM.
    Returns Base64 encoded string: Nonce (12 bytes) + Ciphertext + Auth Tag (16 bytes).
    """
    aesgcm = AESGCM(vault_key)
    nonce = os.urandom(12)  # 96-bit standard nonce for AES-GCM
    ciphertext = aesgcm.encrypt(nonce, recovery_key.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_recovery_key(encrypted_payload: str, vault_key: bytes) -> Optional[str]:
    """
    Decrypts AES-256-GCM payload.
    Returns decrypted recovery key, or raises an exception if tampered or invalid.
    """
    if not encrypted_payload:
        return None
    raw_data = base64.b64decode(encrypted_payload.encode("utf-8"))
    if len(raw_data) < 28:  # 12 nonce + 16 auth tag minimum
        raise ValueError("Invalid encrypted payload length")
    nonce = raw_data[:12]
    ciphertext = raw_data[12:]
    aesgcm = AESGCM(vault_key)
    decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    return decrypted_bytes.decode("utf-8")


# ---------------------------------------------------------------------------
# Sandbox Test Cases
# ---------------------------------------------------------------------------
SERVER_SECRET = "sentinel_vault_master_secret_key_2026_xyz"
VAULT_KEY = derive_vault_key(SERVER_SECRET)


def test_tc1_encryption_decryption_fidelity():
    """TC-1: Ensure plaintext recovery key is perfectly restored."""
    original_key = "tbj_rec_4ce43480_72b32646f2911f5a549a37e192f15a67"
    encrypted = encrypt_recovery_key(original_key, VAULT_KEY)
    
    assert encrypted != original_key
    assert isinstance(encrypted, str)
    
    decrypted = decrypt_recovery_key(encrypted, VAULT_KEY)
    assert decrypted == original_key


def test_tc2_tamper_defense_triggers_error():
    """TC-2: Tampering with ciphertext or auth tag must immediately fail decryption."""
    original_key = "tbj_rec_11223344_aabbccddeeff00112233445566778899"
    encrypted = encrypt_recovery_key(original_key, VAULT_KEY)
    
    # Tamper with the raw base64 string
    raw = bytearray(base64.b64decode(encrypted.encode("utf-8")))
    raw[-1] ^= 0xFF  # Flip bit in auth tag
    tampered_b64 = base64.b64encode(bytes(raw)).decode("utf-8")
    
    with pytest.raises(Exception):  # cryptography.exceptions.InvalidTag
        decrypt_recovery_key(tampered_b64, VAULT_KEY)


def test_tc3_wrong_master_key_fails_decryption():
    """TC-3: Decryption using wrong master key must fail."""
    original_key = "tbj_rec_55667788_99887766554433221100aabbccddeeff"
    encrypted = encrypt_recovery_key(original_key, VAULT_KEY)
    
    wrong_vault_key = derive_vault_key("attacker_fake_master_key")
    with pytest.raises(Exception):
        decrypt_recovery_key(encrypted, wrong_vault_key)


def test_tc4_authorized_credential_endpoint_flow():
    """TC-4: FastAPI TestClient flow verifying authorized credential retrieval."""
    app = FastAPI()
    db = {
        "user_alice": {
            "id": "user_alice",
            "recovery_key_encrypted": encrypt_recovery_key("tbj_rec_alice_key_1234567890abcdef12345678", VAULT_KEY),
            "credential_version": 1
        }
    }

    class CredentialResponse(BaseModel):
        recovery_key: Optional[str]
        credential_version: int

    @app.get("/api/auth/credential", response_model=CredentialResponse)
    def get_credential(authorization: Optional[str] = Header(None)):
        if not authorization or authorization != "Bearer valid_jwt_alice":
            raise HTTPException(status_code=401, detail="Unauthorized")
        
        user_record = db.get("user_alice")
        if not user_record:
            raise HTTPException(status_code=404, detail="User not found")
        
        enc_payload = user_record.get("recovery_key_encrypted")
        decrypted = decrypt_recovery_key(enc_payload, VAULT_KEY) if enc_payload else None
        return CredentialResponse(
            recovery_key=decrypted,
            credential_version=user_record.get("credential_version", 1)
        )

    client = TestClient(app)

    # 1. Unauthenticated request -> 401
    res_unauth = client.get("/api/auth/credential")
    assert res_unauth.status_code == 401

    # 2. Authenticated request with Alice's token -> 200 with decrypted key
    res_auth = client.get("/api/auth/credential", headers={"Authorization": "Bearer valid_jwt_alice"})
    assert res_auth.status_code == 200
    data = res_auth.json()
    assert data["recovery_key"] == "tbj_rec_alice_key_1234567890abcdef12345678"
    assert data["credential_version"] == 1


def test_tc5_multi_device_sync_lifecycle():
    """TC-5: Full lifecycle: Device A rotates -> Vault updates -> Device B fetches latest key."""
    db = {
        "user_alice": {
            "id": "user_alice",
            "recovery_key_id": "key_01",
            "recovery_key_encrypted": encrypt_recovery_key("tbj_rec_key01_secret1111222233334444", VAULT_KEY),
            "credential_version": 1
        }
    }

    # Device B initially has Key 1
    device_b_cache = decrypt_recovery_key(db["user_alice"]["recovery_key_encrypted"], VAULT_KEY)
    assert device_b_cache == "tbj_rec_key01_secret1111222233334444"

    # Device A executes rotation to Key 2
    new_key = "tbj_rec_key02_secret9999888877776666"
    db["user_alice"]["recovery_key_id"] = "key_02"
    db["user_alice"]["recovery_key_encrypted"] = encrypt_recovery_key(new_key, VAULT_KEY)
    db["user_alice"]["credential_version"] = 2

    # Device B receives Realtime trigger or opens Profile -> Queries vault
    synced_key_for_device_b = decrypt_recovery_key(db["user_alice"]["recovery_key_encrypted"], VAULT_KEY)
    assert synced_key_for_device_b == new_key
    assert synced_key_for_device_b != device_b_cache
