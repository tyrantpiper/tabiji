"""
Cloudinary Upload Signing Router
--------------------------------
Issues authenticated, short-lived SHA-1 upload signatures for direct browser-to-Cloudinary
uploads so CLOUDINARY_API_SECRET lives exclusively on the Cloud Run backend (never Vercel).

Security controls:
1. Pre-auth rightmost-XFF IP rate limit runs BEFORE get_verified_user to shield
   supabase.auth.get_user() fallback from unauthenticated floods without trusting
   spoofable CF-Connecting-IP or leftmost X-Forwarded-For headers (CWE-290).
2. Mandatory JWT authentication via Depends(get_verified_user), preserving
   app.dependency_overrides[get_verified_user] and avoiding duplicate JWT decoding.
3. Per-user SlowAPI rate limit (60/minute) keyed strictly by verified user ID
   (uid:{user_id}), immune to X-Gemini-API-Key / IP header spoofing.
4. Strict parameter allowlist, folder allowlist + subpath regex, non-bool integer
   timestamp within ±600s, and public_id overwrite protection (restricted solely to
   ryan_travel/streetview with ^mly_[0-9A-Za-z_-]{1,64}$).
5. Atomic { signature, apiKey, cloudName } response with Cache-Control: no-store
   to enable zero-downtime Cloudinary key rotation.
"""

from collections import OrderedDict, deque
import hashlib
import json
import re
import threading
import time
from typing import Dict, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from routers.users import _get_cloudinary_config
from utils.deps import get_verified_user
from utils.limiter import limiter

router = APIRouter(tags=["cloudinary"])

ALLOWED_PARAM_KEYS = frozenset({"timestamp", "folder", "public_id"})
ALLOWED_FOLDERS = ("tabidachi_capsules", "ryan_travel", "trip_covers", "receipts")
STREETVIEW_FOLDER = "ryan_travel/streetview"

_SAFE_FOLDER_RE = re.compile(r"^[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)*\Z")
_DIGIT_TIMESTAMP_RE = re.compile(r"^[1-9][0-9]{0,11}\Z")
_ASCII_UINT_RE = re.compile(r"^[0-9]+\Z")
_STREETVIEW_PUBLIC_ID_RE = re.compile(r"^mly_[0-9A-Za-z_-]{1,64}\Z")
_TIMESTAMP_SKEW_SECONDS = 600
_MAX_SIGN_BODY_BYTES = 4096

# Pre-auth IP rate limit protects get_verified_user() / supabase.auth.get_user() fallback.
# Uses a generous per-IP ceiling so shared Cloudflare/NAT egress IPs are not impacted.
_PREAUTH_IP_LIMIT = 240
_PREAUTH_IP_WINDOW_SECONDS = 60.0
_PREAUTH_MAX_TRACKED_IPS = 4096
_PREAUTH_LOCK = threading.Lock()
_PREAUTH_IP_HITS: "OrderedDict[str, deque]" = OrderedDict()


def _extract_trusted_client_ip(request: Request) -> str:
    """
    Extract client IP strictly from the rightmost Google Frontend (GFE) X-Forwarded-For
    hop across ALL X-Forwarded-For header occurrences (RFC 9110 §5.3) or direct socket
    peer address. Never trusts spoofable CF-Connecting-IP, X-Real-IP, or leftmost
    X-Forwarded-For values (CWE-290).
    """
    xff_headers = request.headers.getlist("x-forwarded-for")
    for raw_header in reversed(xff_headers):
        # Walk backwards from the tail without splitting attacker-padded headers into O(N) lists
        remaining = raw_header.rstrip(" ,\t")
        while remaining:
            if "," in remaining:
                head, tail = remaining.rsplit(",", 1)
                candidate = tail.strip()
                if candidate:
                    return candidate[:64].lower()
                remaining = head.rstrip(" ,\t")
            else:
                candidate = remaining.strip()
                if candidate:
                    return candidate[:64].lower()
                break
    if request.client and request.client.host:
        return str(request.client.host).strip()[:64].lower() or "unknown"
    return "unknown"


async def _enforce_preauth_ip_limit(request: Request) -> None:
    """Pre-auth sliding-window IP limiter executed strictly before JWT verification."""
    if not limiter.enabled:
        return

    client_ip = _extract_trusted_client_ip(request)
    now = time.monotonic()
    cutoff = now - _PREAUTH_IP_WINDOW_SECONDS

    with _PREAUTH_LOCK:
        bucket = _PREAUTH_IP_HITS.get(client_ip)
        if bucket is not None:
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if not bucket:
                _PREAUTH_IP_HITS.pop(client_ip, None)
                bucket = None

        if bucket is not None and len(bucket) >= _PREAUTH_IP_LIMIT:
            _PREAUTH_IP_HITS.move_to_end(client_ip)
            raise HTTPException(
                status_code=429,
                detail="Too many upload signing requests. Please try again shortly.",
                headers={
                    "Retry-After": str(int(_PREAUTH_IP_WINDOW_SECONDS)),
                    "Cache-Control": "no-store",
                },
            )

        if bucket is None:
            if len(_PREAUTH_IP_HITS) >= _PREAUTH_MAX_TRACKED_IPS:
                expired_ips = [
                    ip
                    for ip, hits in _PREAUTH_IP_HITS.items()
                    if not hits or hits[-1] <= cutoff
                ]
                for ip in expired_ips:
                    _PREAUTH_IP_HITS.pop(ip, None)
                while len(_PREAUTH_IP_HITS) >= _PREAUTH_MAX_TRACKED_IPS:
                    _PREAUTH_IP_HITS.popitem(last=False)
            bucket = deque()
            _PREAUTH_IP_HITS[client_ip] = bucket
        else:
            _PREAUTH_IP_HITS.move_to_end(client_ip)

        bucket.append(now)


async def _bind_verified_user_for_sign(
    request: Request,
    _preauth: None = Depends(_enforce_preauth_ip_limit),
    user_id: str = Depends(get_verified_user),
) -> str:
    """
    Bind verified user_id onto request.state after pre-auth IP check and
    get_verified_user() so SlowAPI can rate-limit by uid without double decoding JWT.
    """
    request.state.verified_user_id = user_id
    return user_id


def _cloudinary_sign_rate_limit_key(request: Request) -> str:
    """Per-user SlowAPI key_func isolated from X-Gemini-API-Key and spoofable IP headers."""
    uid = getattr(request.state, "verified_user_id", None)
    if isinstance(uid, str) and uid.strip():
        return f"uid:{uid.strip().lower()}"
    return f"ip:{_extract_trusted_client_ip(request)}"


def __reset_cloudinary_sign_rate_limits_for_testing() -> None:
    """Reset module-level pre-auth IP buckets and SlowAPI storage for deterministic tests."""
    with _PREAUTH_LOCK:
        _PREAUTH_IP_HITS.clear()
    storage = getattr(limiter, "_storage", None)
    if storage is not None and hasattr(storage, "reset"):
        storage.reset()


def _is_allowed_folder(target_folder: object) -> bool:
    if not isinstance(target_folder, str):
        return False
    if not target_folder or len(target_folder) > 160:
        return False
    if not _SAFE_FOLDER_RE.match(target_folder):
        return False
    return any(
        target_folder == allowed or target_folder.startswith(f"{allowed}/")
        for allowed in ALLOWED_FOLDERS
    )


def _parse_valid_timestamp(raw_timestamp: object, now_ts: int) -> int:
    if isinstance(raw_timestamp, bool):
        raise HTTPException(status_code=400, detail="Invalid or expired timestamp")

    if isinstance(raw_timestamp, int):
        ts = raw_timestamp
    elif isinstance(raw_timestamp, str) and _DIGIT_TIMESTAMP_RE.match(raw_timestamp):
        ts = int(raw_timestamp)
    else:
        raise HTTPException(status_code=400, detail="Invalid or expired timestamp")

    if ts <= 0 or abs(ts - now_ts) > _TIMESTAMP_SKEW_SECONDS:
        raise HTTPException(status_code=400, detail="Invalid or expired timestamp")
    return ts


@router.post("/api/sign-cloudinary")
@limiter.limit("60/minute", key_func=_cloudinary_sign_rate_limit_key)
async def sign_cloudinary_upload(
    request: Request,
    user_id: str = Depends(_bind_verified_user_for_sign),
):
    """
    Generate an authenticated Cloudinary SHA-1 upload signature.
    Returns atomic { signature, apiKey, cloudName } for zero-downtime key rotation.
    """
    declared_length: Optional[str] = None
    for raw_cl in request.headers.getlist("content-length"):
        for part in raw_cl.split(","):
            token = part.strip(" \t")
            if not _ASCII_UINT_RE.match(token):
                raise HTTPException(status_code=400, detail="Invalid signing payload")
            norm_length = token.lstrip("0") or "0"
            if declared_length is not None and norm_length != declared_length:
                raise HTTPException(status_code=400, detail="Invalid signing payload")
            declared_length = norm_length

    if declared_length is not None:
        if len(declared_length) > 10 or int(declared_length) > _MAX_SIGN_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Signing payload too large")

    chunks = bytearray()
    async for chunk in request.stream():
        if len(chunks) + len(chunk) > _MAX_SIGN_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Signing payload too large")
        chunks.extend(chunk)

    try:
        body = json.loads(chunks.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid signing payload")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid signing payload")

    params_to_sign = body.get("paramsToSign")
    if not isinstance(params_to_sign, dict) or not params_to_sign:
        raise HTTPException(status_code=400, detail="Invalid signing payload")

    for key in params_to_sign.keys():
        if not isinstance(key, str) or key not in ALLOWED_PARAM_KEYS:
            raise HTTPException(status_code=400, detail="Unauthorized signing parameter")

    target_folder = params_to_sign.get("folder")
    if not _is_allowed_folder(target_folder):
        raise HTTPException(status_code=400, detail="Unauthorized upload folder")

    now_ts = int(time.time())
    timestamp = _parse_valid_timestamp(params_to_sign.get("timestamp"), now_ts)

    sanitized_params: Dict[str, Union[str, int]] = {
        "timestamp": timestamp,
        "folder": target_folder,
    }

    if "public_id" in params_to_sign:
        if target_folder != STREETVIEW_FOLDER:
            raise HTTPException(
                status_code=400,
                detail="Custom public_id is not permitted for this folder",
            )
        raw_public_id = params_to_sign.get("public_id")
        if not isinstance(raw_public_id, str) or not _STREETVIEW_PUBLIC_ID_RE.match(raw_public_id):
            raise HTTPException(status_code=400, detail="Invalid public_id")
        sanitized_params["public_id"] = raw_public_id

    cloud_name, api_key, api_secret = _get_cloudinary_config()
    if not (cloud_name and api_key and api_secret):
        raise HTTPException(
            status_code=500,
            detail="Upload signing service is not configured",
        )

    canonical_params = "&".join(
        f"{k}={sanitized_params[k]}" for k in sorted(sanitized_params.keys())
    )
    signature = hashlib.sha1(f"{canonical_params}{api_secret}".encode("utf-8")).hexdigest()

    return JSONResponse(
        content={
            "signature": signature,
            "apiKey": api_key,
            "cloudName": cloud_name,
        },
        headers={"Cache-Control": "no-store"},
    )
