# -*- coding: utf-8 -*-
"""
🛡️ Security Sentinel Simulation Suite: Tabiji MCP UI & Next.js Gateway Contracts
Validates Next.js rewrite boundary, Session JWT issuance vs raw recovery key confusion,
and Mantis Block G Benign Control.
"""

import pytest
import jwt
import time
import uuid
from typing import Optional
from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from utils.deps import get_session_secret, get_verified_user
from routers.mcp import router as mcp_router

MOCK_USER_UUID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
MOCK_RECOVERY_KEY = "tbj_rec_12345678_1234567890abcdef1234567890abcdef"

def create_mcp_gateway_test_app(simulate_nextjs_rewrites: bool = True) -> FastAPI:
    """模擬 Next.js 與 FastAPI 後端整合的閘道環境"""
    app = FastAPI(title="Tabiji Gateway Simulation")
    app.state.session_secret = get_session_secret()

    # 掛載 MCP 路由
    app.include_router(mcp_router)

    # 模擬 Next.js 閘道路由過濾 (若 simulate_nextjs_rewrites=False，則 /.well-known 未被轉發)
    @app.middleware("http")
    async def nextjs_rewrite_proxy_middleware(request: Request, call_next):
        path = request.url.path
        if not simulate_nextjs_rewrites:
            # 漏洞狀態：Next.js 未配置 /.well-known 轉發，直接回傳 Next.js 404
            if path.startswith("/.well-known"):
                return JSONResponse(status_code=404, content={"detail": "Next.js App Router: Path not found"})
        return await call_next(request)

    return app

# ==============================================================================
# 測試案例
# ==============================================================================

def test_poc_raw_recovery_key_rejected_by_auth():
    """
    [假說 2 - 紅軍 PoC]
    直接拿引繼碼 (tbj_rec_*) 作為 Bearer Token，後端必須嚴格拒絕 (401)，
    證明計畫中『直接使用 user_recovery_key 複製貼入 Gemini』的推論是錯誤且會失效的。
    """
    app = create_mcp_gateway_test_app()
    client = TestClient(app)

    # 攜帶裸露引繼碼呼叫 MCP
    res = client.post(
        "/api/mcp",
        headers={"Authorization": f"Bearer {MOCK_RECOVERY_KEY}"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "manage_itinerary_node",
                "arguments": {"trip_id": str(uuid.uuid4()), "day_index": 1, "action": "add"}
            }
        }
    )
    # 必須被阻斷：回傳 JSON-RPC 401 錯誤碼
    assert res.status_code == 200
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == -32000
    assert "Unauthorized" in data["error"]["message"]

def test_benign_signed_session_jwt_accepted_by_auth():
    """
    [假說 2 - 藍軍良性對照 (Mantis Block G)]
    透過 SESSION_SECRET 簽署的標準長效 Session JWT 傳入後端，必須能成功解析 user_id。
    """
    app = create_mcp_gateway_test_app()
    client = TestClient(app)

    # 簽署合法 JWT (模擬前端 getValidSessionToken() 取得的合法憑證)
    secret = get_session_secret()
    valid_jwt = jwt.encode(
        {
            "sub": MOCK_USER_UUID,
            "exp": int(time.time()) + 3600 * 24 * 30, # 30天有效
            "type": "session"
        },
        secret,
        algorithm="HS256"
    )

    # 攜帶合規 JWT 呼叫 tools/list (無權限拒絕)
    res = client.post(
        "/api/mcp",
        headers={"Authorization": f"Bearer {valid_jwt}"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    )
    assert res.status_code == 200
    data = res.json()
    assert "result" in data
    assert "tools" in data["result"]
    assert len(data["result"]["tools"]) >= 2

def test_poc_missing_nextjs_wellknown_rewrite_rejection():
    """
    [假說 1 - 紅軍 PoC]
    若 Next.js rewrites 漏掉 /.well-known，Google Gemini 探針被 404 攔截。
    """
    # 模擬未配置轉發之 Next.js 閘道
    vulnerable_app = create_mcp_gateway_test_app(simulate_nextjs_rewrites=False)
    client = TestClient(vulnerable_app)

    res = client.get("/.well-known/oauth-authorization-server")
    assert res.status_code == 404
    assert "Next.js" in res.json()["detail"]

def test_benign_nextjs_wellknown_rewrite_success():
    """
    [假說 1 - 藍軍良性對照 (Mantis Block G)]
    補齊 Next.js rewrites 後，/.well-known 成功轉發至 FastAPI 並回傳 RFC 8414 Metadata。
    """
    patched_app = create_mcp_gateway_test_app(simulate_nextjs_rewrites=True)
    client = TestClient(patched_app)

    res = client.get("/.well-known/oauth-authorization-server")
    assert res.status_code == 200
    data = res.json()
    assert "authorization_endpoint" in data
    assert "token_endpoint" in data
    assert "S256" in data["code_challenge_methods_supported"]
