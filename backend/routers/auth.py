"""
🛡️ Tabiji Authentication & Session Management Router (v2026)
Implements the 1Password Secret Key / Local-First Recovery Key paradigm.
Provides:
- POST /api/auth/session: Silent issuance / exchange of cryptographically signed JWT.
- POST /api/auth/recover: Landing page recovery key restoration with rate limiting.
"""

import os
import re
import time
import uuid
import jwt
from fastapi import APIRouter, HTTPException, Request, Depends
from starlette.concurrency import run_in_threadpool
from supabase import Client
from pydantic import BaseModel, Field
from typing import Optional, Any
from utils.deps import get_session_secret, get_supabase
from utils.limiter import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])

UUID_V4_REGEX = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', 
    re.IGNORECASE
)


class SessionRequest(BaseModel):
    recovery_key: Optional[str] = Field(None, description="Existing user UUID / recovery key")


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    user_id: str
    is_new: bool


def is_valid_uuid(val: Any) -> bool:
    if not val or not isinstance(val, str):
        return False
    return bool(UUID_V4_REGEX.match(val.strip()))


def normalize_uuid_or_400(val: Optional[str]) -> str:
    """🛡️ 嚴格校驗並歸一化 UUID，杜絕型別錯誤與注入"""
    if not val or not isinstance(val, str):
        raise HTTPException(status_code=400, detail="Recovery key is required")
    cleaned = val.strip().lower()
    if not UUID_V4_REGEX.match(cleaned):
        raise HTTPException(status_code=400, detail="Invalid recovery key format")
    return cleaned


def create_session_jwt(user_id: str, secret: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iss": "tabiji-core",
        "iat": now,
        "exp": now + (30 * 86400),  # 30 天效期 (由前端 401 攔截器靜默換發)
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


@router.post("/session", response_model=SessionResponse)
@limiter.limit("20/minute")
async def create_or_exchange_session(
    request: Request,
    body: SessionRequest,
    secret: str = Depends(get_session_secret),
    supabase: Client = Depends(get_supabase),
):
    """
    ✨ 靜默憑證領取與安全換發 (Hardened Silent Session Exchange)
    - 帶有 recovery_key：必須通過資料庫存在性查核，查無回傳 401 (拒絕洗白老用戶)
    - 未帶 key：生成全新 UUID 並寫入 public.users
    """
    if body.recovery_key:
        uid = normalize_uuid_or_400(body.recovery_key)
        try:
            exists = await run_in_threadpool(legacy_identity_exists, supabase, uid)
        except Exception as e:
            print(f"🔥 [Auth] DB error during session check: {e}")
            raise HTTPException(status_code=503, detail="Identity check temporarily unavailable")

        if not exists:
            # 🛡️ 查無此人絕不降級成新用戶，回傳 401 保障本地金鑰不被覆寫
            raise HTTPException(status_code=401, detail="Unknown recovery key")

        token = create_session_jwt(uid, secret)
        return SessionResponse(
            access_token=token,
            user_id=uid,
            is_new=False,
        )

    # 全新無金鑰裝置秒開
    new_uid = str(uuid.uuid4())
    try:
        await run_in_threadpool(
            lambda: supabase.table("users").insert({"id": new_uid, "name": "Traveler"}).execute()
        )
    except Exception as e:
        print(f"🔥 [Auth] DB bootstrap error: {e}")
        raise HTTPException(status_code=503, detail="Account bootstrap failed")

    token = create_session_jwt(new_uid, secret)
    return SessionResponse(
        access_token=token,
        user_id=new_uid,
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
    受 SlowAPI 限流保護 (5次/分鐘)，且強制查核帳號真實存在。
    """
    clean_uid = normalize_uuid_or_400(body.recovery_key)

    try:
        exists = await run_in_threadpool(legacy_identity_exists, supabase, clean_uid)
    except Exception as e:
        print(f"🔥 [Auth] DB error during recover check: {e}")
        raise HTTPException(status_code=503, detail="Identity check temporarily unavailable")

    if not exists:
        raise HTTPException(status_code=404, detail="Account not found")

    token = create_session_jwt(clean_uid, secret)
    return SessionResponse(
        access_token=token,
        user_id=clean_uid,
        is_new=False,
    )
