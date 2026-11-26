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
import unicodedata
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
DEFAULT_BOOTSTRAP_NAME = "Traveler"
MAX_BOOTSTRAP_NAME_LEN = 64
_BOOTSTRAP_WHITESPACE_RE = re.compile(r"\s+")
_BOOTSTRAP_CTRL_STRIP_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f"
    r"\u00ad\u061c\u200b\u200c\u200e\u200f\u202a-\u202e\u2060-\u206f\ufeff]"
)
_BOOTSTRAP_INVISIBLE_ONLY_RE = re.compile(r"[\u200d\ufe0e\ufe0f\s]+")
_BOOTSTRAP_PLACEHOLDER_NAMES = frozenset({
    "traveler",
    "new traveler",
    "unknown traveler",
    "legacy traveler",
    "null",
    "undefined",
})


def _is_regional_indicator(ch: str) -> bool:
    cp = ord(ch)
    return 0x1F1E6 <= cp <= 0x1F1FF


def _is_grapheme_extender(ch: str) -> bool:
    cp = ord(ch)
    if cp in (0xFE0E, 0xFE0F, 0x20E3) or 0x1F3FB <= cp <= 0x1F3FF or 0xE0020 <= cp <= 0xE007F:
        return True
    return unicodedata.category(ch) in ("Mn", "Mc", "Me")


def _truncate_grapheme_safe(text: str, max_len: int) -> str:
    """
    Truncate text to at most `max_len` Unicode code points without splitting
    ZWJ emoji sequences, regional indicator flag pairs, emoji modifiers,
    variation selectors, or combining mark clusters.
    """
    if len(text) <= max_len:
        return text

    clusters: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        start = i
        ch = text[i]
        i += 1
        if _is_regional_indicator(ch) and i < n and _is_regional_indicator(text[i]):
            i += 1
            clusters.append(text[start:i])
            continue
        while i < n:
            if _is_grapheme_extender(text[i]):
                i += 1
                continue
            if text[i] == "\u200d" and i + 1 < n and not text[i + 1].isspace():
                i += 2
                continue
            break
        clusters.append(text[start:i])

    out_parts: list[str] = []
    used = 0
    for cluster in clusters:
        c_len = len(cluster)
        if used + c_len > max_len:
            break
        out_parts.append(cluster)
        used += c_len
    return "".join(out_parts).strip().strip("\u200d").strip()


def sanitize_bootstrap_name(raw_name: Optional[str]) -> str:
    """
    Sanitize optional initial display name for new-user / orphan-UUID bootstrap.
    Strips control/invisible/Bidi characters, collapses all Unicode whitespace,
    enforces a grapheme-safe length bound, and falls back to DEFAULT_BOOTSTRAP_NAME
    ('Traveler') when blank, invisible-only, or placeholder.
    """
    if not isinstance(raw_name, str):
        return DEFAULT_BOOTSTRAP_NAME
    cleaned = _BOOTSTRAP_CTRL_STRIP_RE.sub("", raw_name)
    cleaned = _BOOTSTRAP_WHITESPACE_RE.sub(" ", cleaned).strip().strip("\u200d").strip()
    if not cleaned or not _BOOTSTRAP_INVISIBLE_ONLY_RE.sub("", cleaned):
        return DEFAULT_BOOTSTRAP_NAME
    if cleaned.lower() in _BOOTSTRAP_PLACEHOLDER_NAMES:
        return DEFAULT_BOOTSTRAP_NAME
    if len(cleaned) > MAX_BOOTSTRAP_NAME_LEN:
        cleaned = _truncate_grapheme_safe(cleaned, MAX_BOOTSTRAP_NAME_LEN)
    if (
        not cleaned
        or not _BOOTSTRAP_INVISIBLE_ONLY_RE.sub("", cleaned)
        or cleaned.lower() in _BOOTSTRAP_PLACEHOLDER_NAMES
    ):
        return DEFAULT_BOOTSTRAP_NAME
    return cleaned


class SessionRequest(BaseModel):
    recovery_key: Optional[str] = Field(None, description="Existing user recovery key (tbj_rec_*) or legacy UUID")
    expected_user_id: Optional[str] = Field(None, description="Expected user UUID when re-anchoring an existing device session")
    name: Optional[str] = Field(
        None,
        max_length=256,
        description="Optional initial display name applied ONLY when creating a new user or bootstrapping an orphan UUID",
    )


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
    優先取用專用 VAULT_MASTER_KEY；生產環境嚴格 Fail-Closed，非生產環境以獨立專屬鹽值派生自 session_secret。
    """
    vault_secret = os.getenv("VAULT_MASTER_KEY")
    if vault_secret and len(vault_secret) >= 16:
        return vault_secret
    is_prod = os.getenv("ENV") == "production" or os.getenv("NODE_ENV") == "production" or os.getenv("PROD") == "1"
    if is_prod and not fallback_secret:
        raise RuntimeError("🚨 [CRITICAL SECURITY] VAULT_MASTER_KEY is required in production environment!")
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


def get_legacy_session_secrets(current_secret: Optional[str] = None) -> list[str]:
    """
    🔄 金鑰輪替過渡期歷史 Session 簽章密鑰列表
    僅供 auth.py PoP 升級橋與 90 天寬限端點驗簽舊裝置憑證，絕不開放一般業務依賴直接使用，
    藉此強制舊 JWT 透過 /api/auth/session 靜默遷移至最新密鑰簽發的憑證。
    """
    candidates: list[str] = []
    for env_name in ("LEGACY_SESSION_SECRET_KEY", "PREVIOUS_SESSION_SECRET_KEY"):
        raw = os.getenv(env_name, "")
        for part in raw.split(","):
            s = part.strip()
            if s and len(s) >= 16 and s != current_secret and s not in candidates:
                candidates.append(s)
    return candidates


def decrypt_recovery_key_with_fallback(encrypted_payload: Optional[str], current_secret: str) -> Optional[str]:
    """Decrypts vault payload with primary key first, then bounded legacy vault/session transition secrets."""
    if not encrypted_payload:
        return None
    primary_vault_key = derive_vault_key(current_secret)
    decrypted = decrypt_recovery_key(encrypted_payload, primary_vault_key)
    if decrypted is not None:
        return decrypted

    for env_name in ("LEGACY_VAULT_MASTER_KEY", "PREVIOUS_VAULT_MASTER_KEY"):
        raw = os.getenv(env_name, "")
        for part in raw.split(","):
            v_sec = part.strip()
            if v_sec and len(v_sec) >= 16:
                alt_key = hashlib.sha256(f"tabiji-recovery-vault-salt-{v_sec}".encode()).digest()
                decrypted = decrypt_recovery_key(encrypted_payload, alt_key)
                if decrypted is not None:
                    return decrypted

    for leg_sec in get_legacy_session_secrets(current_secret):
        alt_master = hashlib.sha256(f"tabiji-dedicated-vault-salt-{leg_sec}".encode()).hexdigest()
        alt_key = hashlib.sha256(f"tabiji-recovery-vault-salt-{alt_master}".encode()).digest()
        decrypted = decrypt_recovery_key(encrypted_payload, alt_key)
        if decrypted is not None:
            return decrypted

    return None


def decode_device_session_jwt(
    token: str,
    current_secret: str,
    verify_exp: bool = True,
) -> Optional[dict]:
    """
    🔐 多密鑰安全驗簽 (先驗當前密鑰，再依序驗舊版過渡密鑰)
    必須嚴格符合 HS256 / iss=tabiji-core / type=device_session / UUID v4 sub。
    """
    secrets_to_try = [current_secret] + get_legacy_session_secrets(current_secret)
    required_claims = ["sub", "iss", "iat", "exp", "type"] if verify_exp else ["sub", "iss", "iat", "type"]
    for cand_secret in secrets_to_try:
        try:
            payload = jwt.decode(
                token,
                cand_secret,
                algorithms=["HS256"],
                issuer="tabiji-core",
                options={"verify_exp": verify_exp, "require": required_claims},
            )
            sub = str(payload.get("sub") or "").strip()
            if payload.get("type") == "device_session" and UUID_V4_REGEX.match(sub):
                return payload
        except jwt.PyJWTError:
            continue
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

    # 2. 舊版 UUID 靜默平滑升級路徑 (Zero-Breakage Legacy Migration & Orphan Self-Healing)
    if is_valid_uuid(raw_key):
        clean_uid = raw_key.lower()
        # 🛡️ 舊版 UUID 遷移路徑同樣受 expected_user_id 伺服器端防衛
        if body.expected_user_id:
            if clean_uid != body.expected_user_id.strip().lower():
                raise HTTPException(status_code=401, detail=UNIFORM_AUTH_ERROR)

        exists = await run_in_threadpool(legacy_identity_exists, supabase, clean_uid)
        user_rec = await run_in_threadpool(get_user_record_by_id, supabase, clean_uid) if exists else None

        # 🛠️ Bug Hunter 修復：有效 UUID v4 且通過 expected_user_id 檢查之離線/已清理孤兒身分，原地靜默補登並核發 tbj_rec_*
        if not exists or not user_rec:
            bootstrap_name = sanitize_bootstrap_name(body.name)
            full_key, key_id, secret_hash = generate_prefixed_recovery_key()
            vault_key = derive_vault_key(secret)
            encrypted_key = encrypt_recovery_key(full_key, vault_key)
            persisted = False
            try:
                await run_in_threadpool(
                    lambda: supabase.table("users").insert({
                        "id": clean_uid,
                        "name": bootstrap_name,
                        "recovery_key_id": key_id,
                        "recovery_secret_hash": secret_hash,
                        "recovery_key_encrypted": encrypted_key,
                        "credential_version": 1,
                    }).execute()
                )
                persisted = True
            except Exception as e:
                # 併發競爭保護：若另一請求剛完成建檔，回查既有 user_rec 並交由下方雙軌分支處理
                user_rec = await run_in_threadpool(get_user_record_by_id, supabase, clean_uid)
                if not user_rec:
                    print(f"⚠️ [Auth] Warning: Could not bootstrap orphan uuid {clean_uid}: {e}")
                    raise HTTPException(status_code=503, detail="Account bootstrap temporarily unavailable")

            if persisted:
                token = create_session_jwt(clean_uid, secret, 1)
                return SessionResponse(
                    access_token=token,
                    user_id=clean_uid,
                    recovery_key=full_key,
                    upgraded=True,
                    is_new=False,
                )
        
        # 🛡️ 雙軌平滑升級：若帳號已升級，強制校驗合法持有證明 (Proof-of-Possession)
        if user_rec and user_rec.get("recovery_key_id"):
            is_authenticated = False
            token_ver = 1
            if auth_header and auth_header.startswith("Bearer "):
                cand_token = auth_header.split(" ")[1].strip()
                payload = decode_device_session_jwt(cand_token, secret, verify_exp=False)
                if payload is not None:
                    try:
                        now = int(time.time())
                        sub = str(payload.get("sub") or "").strip()
                        if sub.lower() == clean_uid and (now - payload.get("iat", 0) <= 90 * 86400):
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
            # 若帳號曾受威脅並執行金鑰輪替 (db_ver > 1)，持有舊版 Token (token_ver < db_ver) 視為已撤銷，徹底阻斷旁路提權
            db_ver = int(user_rec.get("credential_version") or 1)
            if db_ver > 1 and token_ver < db_ver:
                raise HTTPException(
                    status_code=401,
                    detail="Credential has been rotated. This session is revoked."
                )

            # 🛡️ 驗證通過之合法舊設備：解密保險庫下發最新金鑰與新 Session，消除死結
            decrypted_key = decrypt_recovery_key_with_fallback(user_rec.get("recovery_key_encrypted"), secret)
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

    # 4. 全新無金鑰裝置秒開 (生成全新 UUID 與專屬引繼金鑰，原子寫入初始暱稱)
    bootstrap_name = sanitize_bootstrap_name(body.name)
    new_uid = str(uuid.uuid4())
    full_key, key_id, secret_hash = generate_prefixed_recovery_key()
    vault_key = derive_vault_key(secret)
    encrypted_key = encrypt_recovery_key(full_key, vault_key)
    try:
        await run_in_threadpool(
            lambda: supabase.table("users").insert({
                "id": new_uid,
                "name": bootstrap_name,
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
                lambda: supabase.table("users").insert({"id": new_uid, "name": bootstrap_name}).execute()
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

    # 1. 優先標準解碼校驗 (未過期，含過渡期歷史密鑰)
    payload = decode_device_session_jwt(token, secret, verify_exp=True)
    if payload is not None:
        try:
            sub = str(payload.get("sub") or "").strip()
            return VerifiedSession(
                user_id=sub,
                token_version=int(payload.get("ver") or 1)
            )
        except Exception:
            pass

    # 2. 🛡️ 寬限期驗簽 (過期 <= 90 天之合法伺服器簽署歷史憑證，含過渡期歷史密鑰)
    payload = decode_device_session_jwt(token, secret, verify_exp=False)
    if payload is not None:
        try:
            now = int(time.time())
            sub = str(payload.get("sub") or "").strip()
            if now - payload.get("iat", 0) <= 90 * 86400:
                return VerifiedSession(
                    user_id=sub,
                    token_version=int(payload.get("ver") or 1)
                )
        except Exception:
            pass

    raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post("/rotate", response_model=SessionResponse)
@limiter.limit("5/minute")
async def rotate_recovery_key(
    request: Request,
    session: VerifiedSession = Depends(get_verified_session_with_grace),
    secret: str = Depends(get_session_secret),
    supabase: Client = Depends(get_supabase),
):
    """
    🔄 憑證輪替與歷史暴露作廢 (Revocation & Key Rotation)
    核發全新引繼金鑰，立即使所有先前暴露或外洩之金鑰失效。
    """
    user_rec = await run_in_threadpool(get_user_record_by_id, supabase, session.user_id)
    if not user_rec:
        raise HTTPException(status_code=404, detail="User not found")

    db_ver = int(user_rec.get("credential_version") or 1)

    # 🛡️ ADR-009 輪替端點狀態分流硬性撤銷守衛 (Enforce Revocation on Rotation Endpoint)
    # 若帳號曾受威脅並已輪替 (db_ver > 1)，歷史舊版 Token (token_ver < db_ver) 嚴禁再次發起輪替！
    if db_ver > 1 and session.token_version < db_ver:
        raise HTTPException(
            status_code=401,
            detail="Credential has been rotated. This session is revoked."
        )

    current_ver = db_ver + 1

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
            }).eq("id", session.user_id).execute()
        )
    except Exception as e:
        print(f"🔥 [Auth] Failed to rotate recovery credentials: {e}")
        raise HTTPException(status_code=503, detail="Credential rotation temporarily unavailable")

    new_token = create_session_jwt(session.user_id, secret, current_ver)
    return SessionResponse(
        access_token=new_token,
        user_id=session.user_id,
        recovery_key=new_full_key,
        is_new=False,
    )


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
        decrypted_key = decrypt_recovery_key_with_fallback(enc_payload, secret) if enc_payload else None

        return CredentialResponse(
            recovery_key=decrypted_key,
            credential_version=db_ver
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"🔥 [Auth] Failed to retrieve recovery credential: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve credential")

