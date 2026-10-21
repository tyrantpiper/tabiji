import os
from fastapi import Header, HTTPException, Request
from supabase import create_client, Client


async def get_gemini_key(
    x_gemini_api_key: str = Header(None, alias="X-Gemini-API-Key"),
    auth_header: str = Header(None, alias="Authorization")
):
    """
    🔒 BYOK (Bring Your Own Key) 模式
    
    驗證使用者提供的 Gemini API Key。
    支援雙重提取路徑：
    1. 優先從 X-Gemini-API-Key 讀取 (標準)
    2. 回落從 Authorization: Bearer <key> 讀取 (向後相容/相本轉發)
    """
    final_key = x_gemini_api_key
    
    # 🔄 Fallback: 如果標準 Header 為空，試著從 Authorization 提取
    if not final_key and auth_header:
        if auth_header.startswith("Bearer "):
            final_key = auth_header.split(" ")[1]
            print(f"📡 [Auth] API Key extracted from Authorization header")
        else:
            final_key = auth_header
            
    # 調試日誌
    if final_key:
        # 🛡️ Security Hardened: Do not print keys in production
        pass
    
    # 🚫 沒有 Key 或格式不對，直接拒絕
    if not final_key or len(final_key) < 39:
        print(f"❌ API Key 驗證失敗：未提供或格式無效")
        from utils.constants import GEMINI_KEY_REQUIRED_MSG
        raise HTTPException(
            status_code=401, 
            detail=GEMINI_KEY_REQUIRED_MSG
        )
    
    return final_key


import hashlib
import jwt


def get_session_secret() -> str:
    """獲取 JWT 簽章密鑰，若未設置則衍生自 SUPABASE_KEY 安全雜湊保底"""
    secret = os.getenv("SESSION_SECRET_KEY")
    if secret and len(secret) >= 16:
        return secret
    supabase_key = os.getenv("SUPABASE_KEY", "")
    if supabase_key:
        return hashlib.sha256(f"tabiji-session-salt-{supabase_key}".encode()).hexdigest()
    return "tabiji-default-dev-fallback-secret-key-32chars!!"


def get_supabase(request: Request) -> Client:
    """從 app.state 獲取全域 Supabase 客戶端 (使用 Service Role Key)"""
    return request.app.state.supabase

async def get_verified_user(
    request: Request,
    auth_header: str = Header(None, alias="Authorization")
) -> str:
    """
    🛡️ 嚴格密碼學身分驗證依賴 (JWT-Only)
    徹底拔除 X-User-ID 明文 Header 回退信任漏洞。
    """
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")

    token = auth_header.split(" ")[1].strip()
    secret = get_session_secret()

    # 1. 本地高速記憶體驗證 (0.05ms)
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        verified_uid = payload.get("sub")
        if verified_uid:
            return str(verified_uid)
    except jwt.PyJWTError:
        pass

    # 2. Supabase 官方 Token 相容校驗 (若未來串接 OAuth)
    try:
        supabase: Client = request.app.state.supabase
        user_res = supabase.auth.get_user(token)
        if user_res and user_res.user:
            return str(user_res.user.id)
    except Exception:
        pass

    raise HTTPException(status_code=401, detail="Invalid or expired token")
