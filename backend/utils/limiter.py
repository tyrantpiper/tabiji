import hashlib
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


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

