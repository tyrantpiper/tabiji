import hashlib
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def extract_trusted_client_ip(request: Request) -> str:
    """
    Extract client IP strictly from the rightmost reverse-proxy (Google Frontend / GFE)
    X-Forwarded-For hop across ALL X-Forwarded-For header occurrences (RFC 9110 §5.3),
    or direct socket peer address. Never trusts spoofable leftmost X-Forwarded-For,
    CF-Connecting-IP, or X-Real-IP headers (CWE-290).
    """
    try:
        xff_headers = request.headers.getlist("x-forwarded-for")
        for raw_header in reversed(xff_headers):
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
    except Exception:
        pass
    return get_remote_address(request)


def get_public_ip_rate_limit_key(request: Request) -> str:
    """
    IP-only rate-limit key for public non-AI proxy endpoints (/api/route, /api/poi/enrich,
    /api/poi/nearby). Ignores arbitrary X-Gemini-API-Key headers so scripts cannot bypass
    limits by rotating fake keys, and reads rightmost trusted X-Forwarded-For on Cloud Run
    so distinct users do not collapse onto the shared GFE internal loopback IP.
    """
    return f"pubip:{extract_trusted_client_ip(request)}"


def get_rate_limit_key(request: Request) -> str:
    """
    優先使用用戶端提供的 X-Gemini-API-Key 雜湊隔離限流，
    徹底消除反向代理或本地 127.0.0.1 共享 IP 引發的偽 429 誤殺；
    若未攜帶金鑰，則安全回退至 get_remote_address。
    """
    try:
        api_key = (
            request.headers.get("X-Gemini-API-Key")
            or request.headers.get("x-gemini-api-key")
            or request.headers.get("X-Gemini-Key")
            or request.headers.get("x-gemini-key")
        )
        if api_key and api_key.strip():
            return f"key:{hashlib.sha256(api_key.strip().encode('utf-8')).hexdigest()[:16]}"
    except Exception:
        pass
    return get_remote_address(request)


limiter = Limiter(key_func=get_rate_limit_key)

