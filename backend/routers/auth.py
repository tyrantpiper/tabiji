"""
🛡️ Tabiji Authentication & Session Management Router (v2026)
Implements the 1Password Secret Key / Local-First Recovery Key paradigm.
Provides:
- POST /api/auth/session: Silent issuance / exchange of cryptographically signed JWT.
- POST /api/auth/recover: Landing page recovery key restoration with rate limiting.
"""

import os
import time
import uuid
import jwt
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from typing import Optional
from utils.deps import get_session_secret, get_supabase
from utils.limiter import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SessionRequest(BaseModel):
    recovery_key: Optional[str] = Field(None, description="Existing user UUID / recovery key")


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    user_id: str
    is_new: bool


def is_valid_uuid(val: str) -> bool:
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def create_session_jwt(user_id: str, secret: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iss": "tabiji-core",
        "iat": now,
        "exp": now + (365 * 86400),  # 1 year long-lived PWA session
        "type": "device_session"
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@router.post("/session", response_model=SessionResponse)
async def create_or_exchange_session(
    body: SessionRequest,
    secret: str = Depends(get_session_secret)
):
    """
    ✨ 靜默憑證領取與兌換 (Silent Session Exchange)
    - 若傳入有效 recovery_key (UUID)：簽發包含該 ID 之 JWT (老用戶無痛換票)
    - 若未傳入：生成全新 UUID v4 並簽發 JWT (新用戶秒開)
    """
    user_id = body.recovery_key
    is_new = False

    if user_id and is_valid_uuid(user_id):
        final_uid = str(user_id).strip()
    else:
        final_uid = str(uuid.uuid4())
        is_new = True

    token = create_session_jwt(final_uid, secret)
    return SessionResponse(
        access_token=token,
        user_id=final_uid,
        is_new=is_new
    )


@router.post("/recover", response_model=SessionResponse)
@limiter.limit("5/minute")
async def recover_account_with_key(
    request: Request,
    body: SessionRequest,
    secret: str = Depends(get_session_secret)
):
    """
    🛡️ 首頁專屬恢復金鑰還原帳號 (Restricted Recovery Endpoint)
    受 SlowAPI 限流保護 (5次/分鐘)，徹底杜絕暴力枚舉。
    """
    if not body.recovery_key or not is_valid_uuid(body.recovery_key):
        raise HTTPException(status_code=400, detail="Invalid recovery key format")

    final_uid = str(body.recovery_key).strip()
    token = create_session_jwt(final_uid, secret)
    return SessionResponse(
        access_token=token,
        user_id=final_uid,
        is_new=False
    )
