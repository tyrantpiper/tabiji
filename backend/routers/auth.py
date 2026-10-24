"""
🛡️ Tabiji Authentication & Session Management Router (v2026 - Dual-Track Hardened)
Implements dual-track architecture:
- Identity Anchor: Immutable user_id (UUID v4) preserved for all DB relations and offline caches.
- Recovery Credential: Independent, revocable Stripe-style prefixed recovery key (tbj_rec_<id>_<secret>).
- Silent Upgrade Bridge: Legacy UUID sessions are automatically upgraded to modern recovery keys without lockout.
Provides:
- POST /api/auth/session: Silent issuance / exchange of cryptographically signed JWT.
- POST /api/auth/recover: Landing page recovery key restoration with rate limiting.
- POST /api/auth/rotate: Invalidation of compromised recovery keys and rotation to fresh credentials.
"""

import os
import re
import time
import uuid
import hmac
import hashlib
import secrets
import base64
import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, HTTPException, Request, Depends, Header
from starlette.concurrency import run_in_threadpool
from supabase import Client
from pydantic import BaseModel, Field
from typing import Optional, Any
from utils.deps import get_session_secret, get_supabase, get_verified_user
from utils.limiter import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])

UUID_V4_REGEX = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', 
    re.IGNORECASE
)
TBJ_REC_REGEX = re.compile(
    r'^tbj_rec_[0-9a-f]{8}_[0-9a-f]{32}$',
    re.IGNORECASE
)
RECOVERY_PEPPER = os.getenv("RECOVERY_PEPPER")
if not RECOVERY_PEPPER:
    is_prod = os.getenv("ENV") == "production" or os.getenv("NODE_ENV") == "production" or os.getenv("PROD") == "1"
    if is_prod:
        raise RuntimeError("🚨 [CRITICAL SECURITY] RECOVERY_PEPPER must be explicitly set in production!")
    RECOVERY_PEPPER = "tbj_secret_pepper_auth_recovery_v2_2026"


UNIFORM_AUTH_ERROR = "引繼碼驗證失敗，無法在此設備恢復同步。請確認引繼碼是否正確。"


class SessionRequest(BaseModel):
    recovery_key: Optional[str] = Field(None, description="Existing user recovery key (tbj_rec_*) or legacy UUID")
    expected_user_id: Optional[str] = Field(None, description="Expected user UUID when re-anchoring an existing device session")


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    user_id: str
    is_new: bool
    recovery_key: Optional[str] = None
    upgraded: Optional[bool] = None


def is_valid_uuid(val: Any) -> bool:
    if not val or not isinstance(val, str):
        return False
    return bool(UUID_V4_REGEX.match(val.strip()))


def is_valid_tbj_rec(val: Any) -> bool:
    if not val or not isinstance(val, str):
        return False
    return bool(TBJ_REC_REGEX.match(val.strip()))


def generate_prefixed_recovery_key() -> tuple[str, str, str]:
    """Generates (full_key, key_id, secret_hash) using Stripe-style format."""
    key_id = secrets.token_hex(4)  # 8 hex chars (O(1) B-tree lookup key)
    secret_entropy = secrets.token_hex(16)  # 32 hex chars (128-bit secret entropy)
    full_key = f"tbj_rec_{key_id}_{secret_entropy}"
    secret_hash = hmac.new(
        RECOVERY_PEPPER.encode(), secret_entropy.encode(), hashlib.sha256
    ).hexdigest()
    return full_key, key_id, secret_hash


def get_vault_master_key(fallback_secret: Optional[str] = None) -> str:
    """
    🛡️ 獨立長生命週期資料加密主密鑰 (Key Encryption Key)
    優先取用專用 VAULT_MASTER_KEY，未設定時以獨立專屬鹽值派生自 session_secret。
    """
    vault_secret = os.getenv("VAULT_MASTER_KEY")
    if vault_secret and len(vault_secret) >= 16:
        return vault_secret
    sec = fallback_secret or get_session_secret()
    return hashlib.sha256(f"tabiji-dedicated-vault-salt-{sec}".encode()).hexdigest()


def derive_vault_key(master_secret: Optional[str] = None) -> bytes:
    """Derives a deterministic 256-bit key for AES-256-GCM vault from server secret."""
    secret = get_vault_master_key(fallback_secret=master_secret)
    return hashlib.sha256(f"tabiji-recovery-vault-salt-{secret}".encode()).digest()


def encrypt_recovery_key(recovery_key: str, vault_key: bytes) -> str:
    """Encrypts full recovery key with AES-256-GCM for authorized multi-device sync."""
    aesgcm = AESGCM(vault_key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, recovery_key.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("utf-8")


def decrypt_recovery_key(encrypted_payload: Optional[str], vault_key: bytes) -> Optional[str]:
    """Decrypts AES-256-GCM recovery key payload."""
    if not encrypted_payload:
        return None
    try:
        raw_data = base64.b64decode(encrypted_payload.encode("utf-8"))
        if len(raw_data) < 28:
            return None
        nonce = raw_data[:12]
        ciphertext = raw_data[12:]
        aesgcm = AESGCM(vault_key)
        return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
    except Exception:
        return None


def verify_recovery_key(full_key: str, stored_hash: Optional[str]) -> bool:
    if not stored_hash or not is_valid_tbj_rec(full_key):
        return False
    parts = full_key.strip().split("_")
    if len(parts) != 4:
        return False
    secret_entropy = parts[3]
    computed_hash = hmac.new(
        RECOVERY_PEPPER.encode(), secret_entropy.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed_hash, stored_hash)


def create_session_jwt(user_id: str, secret: str, credential_ver: int = 1) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iss": "tabiji-core",
        "iat": now,
        "exp": now + (30 * 86400),  # 30 天效期 (由前端 401 攔截器靜默換發)
        "ver": credential_ver,
        "type": "device_session"
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def legacy_identity_exists(supabase: Client, uid: str) -> bool:
    """🛡️ 雙保險戶籍查核：優先查 users，後備查 members 與 itineraries"""
    for table, col in (("users", "id"), ("trip_members", "user_id"), ("itineraries", "created_by")):
        try:
            res = supabase.table(table).select(col).eq(col, uid).limit(1).execute()
            if res.data:
                return True
        except Exception:
            continue
    return False


def get_user_record_by_id(supabase: Client, uid: str) -> Optional[dict]:
    try:
        res = supabase.table("users").select("id, recovery_key_id, recovery_secret_hash, recovery_key_encrypted, credential_version").eq("id", uid).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception:
        pass
    return None


def get_user_record_by_key_id(supabase: Client, key_id: str) -> Optional[dict]:
    try:
        res = supabase.table("users").select("id, recovery_key_id, recovery_secret_hash, credential_version").eq("recovery_key_id", key_id).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
    except Exception:
        pass
    return None


@router.post("/session", response_model=SessionResponse)
@limiter.limit("20/minute")
async def create_or_exchange_session(
    request: Request,
    body: SessionRequest,
    auth_header: Optional[str] = Header(None, alias="Authorization"),
    secret: str = Depends(get_session_secret),
    supabase: Client = Depends(get_supabase),
):
    """
    ✨ 雙軌憑證領取與靜默升級 (Dual-Track Session Exchange & Silent Upgrade)
    - 帶有 tbj_rec_*：O(1) 索引檢索驗簽換票。
    - 帶有 legacy UUID：若尚未綁定金鑰，自動升級簽發新引繼碼；若已升級且持合法舊憑證則無縫解密新鑰匙，無憑證則拒絕原生 UUID (杜絕 ATO)。
    - 未帶 key：生成全新 UUID 與新版引繼碼。
    """
    raw_key = (body.recovery_key or "").strip()

    # 1. 現代化前綴引繼碼校驗路徑
    if is_valid_tbj_rec(raw_key):
        parts = raw_key.split("_")
        key_id = parts[2]
        user = await run_in_threadpool(get_user_record_by_key_id, supabase, key_id)
        if not user or not verify_recovery_key(raw_key, user.get("recovery_secret_hash")):
            raise HTTPException(status_code=401, detail=UNIFORM_AUTH_ERROR)
        
        # 🛡️ 伺服器端帳號錨定防衛 (Server-Side Expected User ID Gate)
        # 嚴禁在身分不符時向網路傳輸目標帳號之 JWT 或使用者識別碼，徹底阻絕傳輸外洩與 Oracle 枚舉
        if body.expected_user_id:
            if user["id"].strip().lower() != body.expected_user_id.strip().lower():
                raise HTTPException(status_code=401, detail=UNIFORM_AUTH_ERROR)
        
        token = create_session_jwt(user["id"], secret, user.get("credential_version", 1))
        return SessionResponse(
            access_token=token,
            user_id=user["id"],
            recovery_key=raw_key,
            is_new=False,
        )

    # 2. 舊版 UUID 靜默平滑升級路徑 (Zero-Breakage Legacy Migration)
    if is_valid_uuid(raw_key):
        clean_uid = raw_key.lower()
        # 🛡️ 舊版 UUID 遷移路徑同樣受 expected_user_id 伺服器端防衛
        if body.expected_user_id:
            if clean_uid != body.expected_user_id.strip().lower():
                raise HTTPException(status_code=401, detail=UNIFORM_AUTH_ERROR)

        exists = await run_in_threadpool(legacy_identity_exists, supabase, clean_uid)
        if not exists:
            raise HTTPException(status_code=401, detail=UNIFORM_AUTH_ERROR)

        user_rec = await run_in_threadpool(get_user_record_by_id, supabase, clean_uid)
        
        # 🛡️ 雙軌平滑升級：若帳號已升級，校驗合法持有證明 (Proof-of-Possession)
        if user_rec and user_rec.get("recovery_key_id"):
            is_authenticated = False
            token_ver = 1
            if auth_header and auth_header.startswith("Bearer "):
                cand_token = auth_header.split(" ")[1].strip()
                try:
                    payload = jwt.decode(
                        cand_token,
                        secret,
                        algorithms=["HS256"],
                        issuer="tabiji-core",
                        options={"verify_exp": False, "require": ["sub", "iss", "iat", "type"]}
                    )
                    now = int(time.time())
                    sub = str(payload.get("sub") or "").strip()
                    if (
                        payload.get("type") == "device_session"
                        and sub.lower() == clean_uid
                        and (now - payload.get("iat", 0) <= 90 * 86400)
                    ):
                        token_ver = int(payload.get("ver") or 1)
                        is_authenticated = True
                except Exception:
                    pass

            if not is_authenticated:
                raise HTTPException(
                    status_code=401, 
                    detail="Account already upgraded. Please use your modern recovery key (tbj_rec_*)."
                )

            # 🛡️ 狀態機二元分流防衛 (ADR-009 State-Bifurcated Guard)
            # 若帳號曾受威脅並執行金鑰輪替 (db_ver > 1)，舊版 Token (token_ver < db_ver) 視為已撤銷，徹底阻斷旁路提權
            db_ver = int(user_rec.get("credential_version") or 1)
            if db_ver > 1 and token_ver < db_ver:
                raise HTTPException(
                    status_code=401,
                    detail="Credential has been rotated. This session is revoked."
                )

            # 🛡️ 驗證通過之合法舊設備：解密保險庫下發最新金鑰與新 Session，消除死結
            vault_key = derive_vault_key(secret)
            decrypted_key = decrypt_recovery_key(user_rec.get("recovery_key_encrypted"), vault_key)
            token = create_session_jwt(clean_uid, secret, db_ver)
            return SessionResponse(
                access_token=token,
                user_id=clean_uid,
                recovery_key=decrypted_key,
                upgraded=True,
                is_new=False,
            )

        # 靜默升級：確保資料庫寫入成功後才下發新金鑰，若失敗則降級回傳舊版 Session
        full_key, key_id, secret_hash = generate_prefixed_recovery_key()
        vault_key = derive_vault_key(secret)
        encrypted_key = encrypt_recovery_key(full_key, vault_key)
        persisted = False
        try:
            await run_in_threadpool(
                lambda: supabase.table("users").update({
                    "recovery_key_id": key_id,
                    "recovery_secret_hash": secret_hash,
                    "recovery_key_encrypted": encrypted_key,
                    "credential_version": 1,
                    "recovery_updated_at": "now()"
                }).eq("id", clean_uid).execute()
            )
            persisted = True
        except Exception as e:
            print(f"⚠️ [Auth] Warning: Could not persist upgraded credentials: {e}")

        token = create_session_jwt(clean_uid, secret, 1)
        return SessionResponse(
            access_token=token,
            user_id=clean_uid,
            recovery_key=full_key if persisted else None,
            upgraded=persisted,
            is_new=False,
        )

    # 3. 格式無效直接拒絕
    if raw_key:
        raise HTTPException(status_code=400, detail="Invalid recovery key format")

    # 4. 全新無金鑰裝置秒開 (生成全新 UUID 與專屬引繼金鑰)
    new_uid = str(uuid.uuid4())
    full_key, key_id, secret_hash = generate_prefixed_recovery_key()
    vault_key = derive_vault_key(secret)
    encrypted_key = encrypt_recovery_key(full_key, vault_key)
    try:
        await run_in_threadpool(
            lambda: supabase.table("users").insert({
                "id": new_uid,
                "name": "Traveler",
                "recovery_key_id": key_id,
                "recovery_secret_hash": secret_hash,
                "recovery_key_encrypted": encrypted_key,
                "credential_version": 1
            }).execute()
        )
    except Exception as e:
        # 後備：若 users 表無新欄位，降級寫入基礎資訊
        try:
            await run_in_threadpool(
                lambda: supabase.table("users").insert({"id": new_uid, "name": "Traveler"}).execute()
            )
        except Exception as e2:
            print(f"🔥 [Auth] DB bootstrap error: {e2}")
            raise HTTPException(status_code=503, detail="Account bootstrap failed")

    token = create_session_jwt(new_uid, secret, 1)
    return SessionResponse(
        access_token=token,
        user_id=new_uid,
        recovery_key=full_key,
        is_new=True,
    )


@router.post("/recover", response_model=SessionResponse)
@limiter.limit("5/minute")
async def recover_account_with_key(
    request: Request,
    body: SessionRequest,
    secret: str = Depends(get_session_secret),
    supabase: Client = Depends(get_supabase),
):
    """
    🛡️ 首頁專屬恢復金鑰還原帳號 (Restricted Recovery Endpoint)
    受 SlowAPI 限流保護 (5次/分鐘)，支援新版 tbj_rec_* 與未升級之舊版 UUID。
    """
    raw_key = (body.recovery_key or "").strip()

    # 1. 現代化前綴金鑰還原
    if is_valid_tbj_rec(raw_key):
        parts = raw_key.split("_")
        key_id = parts[2]
        user = await run_in_threadpool(get_user_record_by_key_id, supabase, key_id)
        if not user or not verify_recovery_key(raw_key, user.get("recovery_secret_hash")):
            raise HTTPException(status_code=404, detail="Account not found")

        token = create_session_jwt(user["id"], secret, user.get("credential_version", 1))
        return SessionResponse(
            access_token=token,
            user_id=user["id"],
            recovery_key=raw_key,
            is_new=False,
        )

    # 2. 舊版 UUID 還原相容
    if is_valid_uuid(raw_key):
        clean_uid = raw_key.lower()
        exists = await run_in_threadpool(legacy_identity_exists, supabase, clean_uid)
        if not exists:
            raise HTTPException(status_code=404, detail="Account not found")

        user_rec = await run_in_threadpool(get_user_record_by_id, supabase, clean_uid)
        if user_rec and user_rec.get("recovery_key_id"):
            raise HTTPException(
                status_code=400, 
                detail="Account upgraded. Please use your tbj_rec_* recovery key."
            )

        # 靜默升級：確保資料庫寫入成功後才下發新金鑰，若失敗則降級回傳舊版 Session
        full_key, key_id, secret_hash = generate_prefixed_recovery_key()
        vault_key = derive_vault_key(secret)
        encrypted_key = encrypt_recovery_key(full_key, vault_key)
        persisted = False
        try:
            await run_in_threadpool(
                lambda: supabase.table("users").update({
                    "recovery_key_id": key_id,
                    "recovery_secret_hash": secret_hash,
                    "recovery_key_encrypted": encrypted_key,
                    "credential_version": 1,
                    "recovery_updated_at": "now()"
                }).eq("id", clean_uid).execute()
            )
            persisted = True
        except Exception as e:
            print(f"⚠️ [Auth] Warning: Could not persist upgraded credentials during recover: {e}")

        token = create_session_jwt(clean_uid, secret, 1)
        return SessionResponse(
            access_token=token,
            user_id=clean_uid,
            recovery_key=full_key if persisted else None,
            upgraded=persisted,
            is_new=False,
        )

    raise HTTPException(status_code=400, detail="Invalid recovery key format")


@router.post("/rotate", response_model=SessionResponse)
@limiter.limit("5/minute")
async def rotate_recovery_key(
    request: Request,
    current_user: str = Depends(get_verified_user),
    secret: str = Depends(get_session_secret),
    supabase: Client = Depends(get_supabase),
):
    """
    🔄 憑證輪替與歷史暴露作廢 (Revocation & Key Rotation)
    核發全新引繼金鑰，立即使所有先前暴露或外洩之金鑰失效。
    """
    user_rec = await run_in_threadpool(get_user_record_by_id, supabase, current_user)
    current_ver = (user_rec.get("credential_version", 1) if user_rec else 1) + 1

    new_full_key, new_key_id, new_secret_hash = generate_prefixed_recovery_key()
    vault_key = derive_vault_key(secret)
    new_encrypted_key = encrypt_recovery_key(new_full_key, vault_key)
    try:
        await run_in_threadpool(
            lambda: supabase.table("users").update({
                "recovery_key_id": new_key_id,
                "recovery_secret_hash": new_secret_hash,
                "recovery_key_encrypted": new_encrypted_key,
                "credential_version": current_ver,
                "recovery_updated_at": "now()"
            }).eq("id", current_user).execute()
        )
    except Exception as e:
        print(f"🔥 [Auth] Failed to rotate recovery credentials: {e}")
        raise HTTPException(status_code=503, detail="Credential rotation temporarily unavailable")

    new_token = create_session_jwt(current_user, secret, current_ver)
    return SessionResponse(
        access_token=new_token,
        user_id=current_user,
        recovery_key=new_full_key,
        is_new=False,
    )


class VerifiedSession(BaseModel):
    user_id: str
    token_version: int = 1


async def get_verified_session_with_grace(
    request: Request,
    auth_header: str = Header(None, alias="Authorization"),
    secret: str = Depends(get_session_secret),
) -> VerifiedSession:
    """
    🛡️ 自癒寬限期身分驗證依賴 (Grace-Period Token Verification)
    優先標準驗證 (有效 JWT)；若過期但簽名未遭竄改且在 90 天寬限期內，允許存取保險庫自癒。
    回傳 VerifiedSession 物件以嚴格閉合金鑰輪替後的版本號檢驗。
    """
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")

    token = auth_header.split(" ")[1].strip()

    # 1. 優先標準解碼校驗 (未過期)
    try:
        payload = jwt.decode(
            token, 
            secret, 
            algorithms=["HS256"],
            issuer="tabiji-core",
            options={"require": ["sub", "iss", "iat", "exp", "type"]}
        )
        sub = str(payload.get("sub") or "").strip()
        if payload.get("type") == "device_session" and UUID_V4_REGEX.match(sub):
            return VerifiedSession(
                user_id=sub,
                token_version=int(payload.get("ver") or 1)
            )
    except jwt.ExpiredSignatureError:
        # 2. 🛡️ 寬限期驗簽 (過期 <= 90 天之合法伺服器簽署歷史憑證)
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                issuer="tabiji-core",
                options={"verify_exp": False, "require": ["sub", "iss", "iat", "type"]}
            )
            now = int(time.time())
            sub = str(payload.get("sub") or "").strip()
            if (
                payload.get("type") == "device_session" 
                and UUID_V4_REGEX.match(sub)
                and (now - payload.get("iat", 0) <= 90 * 86400)
            ):
                return VerifiedSession(
                    user_id=sub,
                    token_version=int(payload.get("ver") or 1)
                )
        except Exception:
            pass
    except Exception:
        pass

    raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_verified_user_with_grace(
    session: VerifiedSession = Depends(get_verified_session_with_grace),
) -> str:
    return session.user_id


class CredentialResponse(BaseModel):
    recovery_key: Optional[str] = None
    credential_version: int = 1


@router.get("/credential", response_model=CredentialResponse)
@limiter.limit("30/minute")
async def get_user_recovery_credential(
    request: Request,
    session: VerifiedSession = Depends(get_verified_session_with_grace),
    secret: str = Depends(get_session_secret),
    supabase: Client = Depends(get_supabase),
):
    """
    🛡️ 跨裝置引繼碼即時授權同步端點 (Authorized Multi-Device Credential Sync)
    僅允許持有有效 JWT 之本人設備存取，自 AES-256-GCM 雲端保險庫解密下發最新金鑰。
    """
    try:
        res = await run_in_threadpool(
            lambda: supabase.table("users").select(
                "recovery_key_encrypted, credential_version"
            ).eq("id", session.user_id).limit(1).execute()
        )
        if not res.data:
            raise HTTPException(status_code=404, detail="User not found")

        user_row = res.data[0]
        db_ver = int(user_row.get("credential_version") or 1)
        # 🛡️ 徹底阻斷輪替後的保險庫後門：若持有舊 Token 則視為已撤銷
        if session.token_version < db_ver:
            raise HTTPException(
                status_code=401,
                detail="Credential has been rotated. This session is revoked."
            )

        enc_payload = user_row.get("recovery_key_encrypted")
        vault_key = derive_vault_key(secret)
        decrypted_key = decrypt_recovery_key(enc_payload, vault_key) if enc_payload else None

        return CredentialResponse(
            recovery_key=decrypted_key,
            credential_version=db_ver
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"🔥 [Auth] Failed to retrieve recovery credential: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve credential")

