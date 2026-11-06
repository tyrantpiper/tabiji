# -*- coding: utf-8 -*-
"""
🛡️ Security Sentinel Simulation Suite: Tabiji OAuth 2.1 End-to-End Flow
Simulates Google Gemini authorization code grant with mandatory PKCE S256 verification (RFC 7636).
Enforces Mantis Block G Benign Control and code replay prevention.
"""

import pytest
import jwt
import time
import uuid
import secrets
import hashlib
import base64
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, HTTPException, Query, Header
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel
from utils.deps import get_session_secret

MOCK_USER_ID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"

class OAuthTokenRequest(BaseModel):
    grant_type: str
    code: str
    redirect_uri: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    code_verifier: Optional[str] = None

def create_oauth_flow_app(enable_oauth_routes: bool = True) -> FastAPI:
    """建構 OAuth 2.1 沙盒測試環境"""
    app = FastAPI(title="Tabiji OAuth 2.1 Sandbox")
    session_secret = get_session_secret()
    app.state.session_secret = session_secret

    oauth_codes: Dict[str, Dict[str, Any]] = {}

    if enable_oauth_routes:
        @app.get("/api/oauth/authorize")
        async def oauth_authorize(
            client_id: str = Query(...),
            redirect_uri: str = Query(...),
            response_type: str = Query("code"),
            state: Optional[str] = Query(None),
            code_challenge: Optional[str] = Query(None),
            code_challenge_method: Optional[str] = Query("S256")
        ):
            auth_code = f"tbj_code_{secrets.token_hex(16)}"
            oauth_codes[auth_code] = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                "expires_at": time.time() + 300,
                "user_id": client_id
            }
            delimiter = "&" if "?" in redirect_uri else "?"
            callback_url = f"{redirect_uri}{delimiter}code={auth_code}"
            if state:
                callback_url += f"&state={state}"
            return RedirectResponse(url=callback_url, status_code=302)

        @app.post("/api/oauth/token")
        async def oauth_token(req: OAuthTokenRequest):
            code_record = oauth_codes.pop(req.code, None)
            if not code_record or time.time() > code_record["expires_at"]:
                raise HTTPException(status_code=400, detail="Invalid or expired authorization code")

            # 驗證 PKCE S256 (RFC 7636)
            expected_challenge = code_record.get("code_challenge")
            if expected_challenge:
                if not req.code_verifier:
                    raise HTTPException(status_code=400, detail="Missing PKCE code_verifier")
                h = hashlib.sha256(req.code_verifier.encode("ascii")).digest()
                actual_challenge = base64.urlsafe_b64encode(h).decode("ascii").rstrip("=")
                if actual_challenge != expected_challenge:
                    raise HTTPException(status_code=400, detail="PKCE S256 verification failed")

            user_id = code_record["user_id"]
            token_payload = {
                "sub": user_id,
                "exp": int(time.time()) + 3600 * 24 * 30,
                "type": "session"
            }
            access_token = jwt.encode(token_payload, session_secret, algorithm="HS256")
            return {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600 * 24 * 30
            }

    # 模擬受保護的 MCP 端點
    @app.post("/api/mcp")
    async def mcp_endpoint(request: Request, authorization: Optional[str] = Header(None)):
        if not authorization or not authorization.startswith("Bearer "):
            return {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Unauthorized"}}
        raw_token = authorization.split(" ")[1]
        try:
            payload = jwt.decode(raw_token, session_secret, algorithms=["HS256"])
            sub = payload.get("sub")
        except Exception:
            return {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Invalid token"}}

        return {
            "jsonrpc": "2.0",
            "result": {
                "content": [{"type": "text", "text": f"Hello {sub}, MCP operation authorized!"}],
                "isError": False
            }
        }

    return app

# ==============================================================================
# 對抗測試案例 (PoC ✕ 藍軍修復 ✕ Mantis Block G)
# ==============================================================================

def test_poc_missing_oauth_routes_returns_404():
    """[假說 1 - 紅軍 PoC] 未實裝 /api/oauth/authorize 與 /token 時返回 404"""
    vulnerable_app = create_oauth_flow_app(enable_oauth_routes=False)
    client = TestClient(vulnerable_app)

    # 1. Authorize 404 斷鏈
    res_auth = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": MOCK_USER_ID,
            "redirect_uri": "https://gemini.google.com/oauth-callback",
            "state": "xyz123"
        }
    )
    assert res_auth.status_code == 404

    # 2. Token 404 斷鏈
    res_token = client.post(
        "/api/oauth/token",
        json={"grant_type": "authorization_code", "code": "tbj_code_test"}
    )
    assert res_token.status_code == 404

def test_benign_full_google_gemini_oauth_handshake():
    """[假說 1 & 2 - 藍軍良性對照 (Mantis Block G)] 完整模擬 Google Gemini 授權並調用 MCP"""
    app = create_oauth_flow_app(enable_oauth_routes=True)
    client = TestClient(app)

    # 步驟 1: Google Gemini 生成 PKCE Verifier 與 S256 Challenge
    code_verifier = "high_entropy_random_verifier_string_1234567890_abcdef"
    h = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(h).decode("ascii").rstrip("=")

    # 步驟 2: Google 發起瀏覽器授權跳轉
    redirect_target = "https://gemini.google.com/oauth-callback"
    res_auth = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": MOCK_USER_ID,
            "redirect_uri": redirect_target,
            "response_type": "code",
            "state": "google_gemini_state_random",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256"
        },
        follow_redirects=False
    )
    assert res_auth.status_code == 302
    location = res_auth.headers["location"]
    assert location.startswith(redirect_target)
    assert "code=tbj_code_" in location
    assert "state=google_gemini_state_random" in location

    # 從重定向網址中解析出授權碼
    import urllib.parse
    parsed = urllib.parse.urlparse(location)
    q = urllib.parse.parse_qs(parsed.query)
    auth_code = q["code"][0]

    # 步驟 3: Google 攜帶 Verifier 向 /api/oauth/token 換取 JWT
    res_token = client.post(
        "/api/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": redirect_target,
            "client_id": MOCK_USER_ID,
            "code_verifier": code_verifier
        }
    )
    assert res_token.status_code == 200
    token_data = res_token.json()
    assert "access_token" in token_data
    access_token = token_data["access_token"]

    # 步驟 4: Google 攜帶 Access Token 調用 /api/mcp
    res_mcp = client.post(
        "/api/mcp",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call"}
    )
    assert res_mcp.status_code == 200
    mcp_result = res_mcp.json()["result"]
    assert mcp_result["isError"] is False
    assert MOCK_USER_ID in mcp_result["content"][0]["text"]

def test_poc_pkce_tampering_and_replay_defense():
    """[假說 2 - 紅軍 PoC] 測試 PKCE 篡改攔截與授權碼重放阻斷"""
    app = create_oauth_flow_app(enable_oauth_routes=True)
    client = TestClient(app)

    code_verifier = "legitimate_verifier_string_12345"
    h = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(h).decode("ascii").rstrip("=")

    # 授權生成 code
    res_auth = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": MOCK_USER_ID,
            "redirect_uri": "https://gemini.google.com/oauth-callback",
            "code_challenge": code_challenge
        },
        follow_redirects=False
    )
    location = res_auth.headers["location"]
    auth_code = location.split("code=")[1].split("&")[0]

    # 1. 攻擊者使用錯誤的 code_verifier 企圖偷換票 ➔ 必須被拒絕 (400)
    res_bad_verifier = client.post(
        "/api/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": auth_code,
            "code_verifier": "attacker_tampered_verifier"
        }
    )
    assert res_bad_verifier.status_code == 400
    assert "PKCE S256 verification failed" in res_bad_verifier.json()["detail"]

    # 2. 由於上一輪失敗已消耗 (pop) 該授權碼，攻擊者再次重放 ➔ 必須被拒絕 (400)
    res_replay = client.post(
        "/api/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": auth_code,
            "code_verifier": code_verifier
        }
    )
    assert res_replay.status_code == 400
    assert "Invalid or expired authorization code" in res_replay.json()["detail"]

