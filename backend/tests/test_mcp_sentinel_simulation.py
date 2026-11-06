# -*- coding: utf-8 -*-
"""
🛡️ Security Sentinel Simulation & In-Memory PoC Suite: Tabiji Remote MCP & Connected Apps
Simulates official Google Connected Apps Platform (Gemini) and Perplexity MCP specifications.
Enforces Mantis Block G Benign Control, IDOR isolation, and Open-Redirect immunity.
"""

import pytest
import hmac
import hashlib
import time
import uuid
import re
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

# ==============================================================================
# 1. 模擬業務邏輯與安全防禦實作 (Prototype under Audit)
# ==============================================================================

# 模擬資料庫與 Session Store
MOCK_USERS = {
    "user_alice": {"id": "user_alice_uuid", "name": "Alice"},
    "user_mallory": {"id": "user_mallory_uuid", "name": "Mallory (Attacker)"}
}

MOCK_TOKENS = {
    "tbj_pat_alice_valid_secret": "user_alice_uuid",
    "tbj_pat_mallory_valid_secret": "user_mallory_uuid"
}

MOCK_TRIPS = {
    "trip_alice_tokyo": {
        "id": "trip_alice_tokyo",
        "user_id": "user_alice_uuid",
        "title": "Alice 東京5日遊",
        "nodes": [
            {"id": "node_1", "day_index": 1, "place_name": "淺草寺", "arrival_time": "10:00"}
        ]
    }
}

# 合法分潤 OTA 白名單
ALLOWED_AFFILIATE_PARTNERS = {
    "klook": "https://affiliate.klook.com/jump?aff_id=TABIJI_AFF_888&target=",
    "kkday": "https://www.kkday.com/zh-tw/affiliate/jump?cid=TABIJI_AFF_999&url=",
    "booking": "https://www.booking.com/index.html?aid=TABIJI_BOOKING_111&label="
}

# ------------------------------------------------------------------------------
# 安全相容的核心函式
# ------------------------------------------------------------------------------

def verify_bearer_token(authorization: Optional[str] = Header(None)) -> str:
    """身分驗證守衛：解析 Bearer Token 並映射 user_id"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization.split(" ")[1]
    user_id = MOCK_TOKENS.get(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or revoked access token")
    return user_id

def format_mcp_tool_result(text_content: str, is_error: bool = False) -> Dict[str, Any]:
    """遵循 MCP 2024-11-05 / 2026 規範的標準 ToolResult Content Envelope"""
    return {
        "content": [
            {
                "type": "text",
                "text": text_content
            }
        ],
        "isError": is_error
    }

def sanitize_destination_url(partner: str, target_param: str) -> str:
    """防範 Open Redirect 與 SSRF：驗證夥伴與跳轉參數"""
    if partner not in ALLOWED_AFFILIATE_PARTNERS:
        raise HTTPException(status_code=400, detail="Disallowed affiliate partner")
    
    # 嚴格禁止偽造 scheme、換行符、javascript 協議、雙斜線或反斜線
    if (
        not re.match(r'^[\w\-\./\?=&%~+]+$', target_param, re.UNICODE)
        or "://" in target_param
        or target_param.startswith("//")
        or "//" in target_param
        or "\\" in target_param
    ):
        raise HTTPException(status_code=400, detail="Invalid target parameter detected")
        
    base_prefix = ALLOWED_AFFILIATE_PARTNERS[partner]
    return f"{base_prefix}{target_param}"

# ------------------------------------------------------------------------------
# 建構測試專用 FastAPI App
# ------------------------------------------------------------------------------
def create_test_app(enable_patches: bool = True) -> FastAPI:
    app = FastAPI(title="Tabiji MCP Sentinel Simulation")

    # [1] Google Connected Apps 所需之 OAuth 2.1 Discovery
    @app.get("/.well-known/oauth-authorization-server")
    async def oauth_discovery(request: Request):
        if not enable_patches:
            # 漏洞狀態：缺失該端點，回傳 404
            raise HTTPException(status_code=404, detail="Not Found")
        base_url = str(request.base_url).rstrip("/")
        return {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/api/oauth/authorize",
            "token_endpoint": f"{base_url}/api/oauth/token",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"]
        }

    # [2] 分潤跳轉網關
    @app.get("/go/{partner}/{target_id:path}")
    async def affiliate_gateway(partner: str, target_id: str):
        if not enable_patches:
            # 漏洞狀態：直接跳轉，無白名單與協議校驗 (Open Redirect)
            return RedirectResponse(url=target_id, status_code=302)
        safe_url = sanitize_destination_url(partner, target_id)
        return RedirectResponse(url=safe_url, status_code=302)

    # [3] MCP JSON-RPC 2.0 端點
    @app.post("/api/mcp")
    async def mcp_rpc(request: Request, authorization: Optional[str] = Header(None)):
        payload = await request.json()
        method = payload.get("method")
        req_id = payload.get("id")
        params = payload.get("params", {})

        # Google Gemini / Perplexity 的握手方法無需事先認證
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "tabiji-mcp-server", "version": "1.0.0"}
                }
            }

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "manage_itinerary_node",
                            "description": "在 Tabiji 行程中新增、修改或刪除景點節點",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "trip_id": {"type": "string"},
                                    "day_index": {"type": "integer"},
                                    "action": {"type": "string", "enum": ["add", "remove", "update"]},
                                    "place_name": {"type": "string"}
                                },
                                "required": ["trip_id", "day_index", "action"]
                            }
                        }
                    ]
                }
            }

        # 涉及使用者資料之 Tool Call 必須驗證 Token
        user_id = verify_bearer_token(authorization)

        if method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})

            if tool_name == "manage_itinerary_node":
                trip_id = args.get("trip_id")
                trip = MOCK_TRIPS.get(trip_id)
                if not trip:
                    if not enable_patches:
                        return {"jsonrpc": "2.0", "id": req_id, "result": {"error": "Trip not found"}}
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": format_mcp_tool_result("行程不存在", is_error=True)
                    }

                # 租戶隔離校驗 (IDOR 守護)
                if enable_patches and trip["user_id"] != user_id:
                    # 補丁修復狀態：阻斷跨租戶越權修改
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": format_mcp_tool_result("權限不足：您無法修改他人行程", is_error=True)
                    }

                # 執行新增節點
                new_node = {
                    "id": f"node_{uuid.uuid4().hex[:6]}",
                    "day_index": args.get("day_index", 1),
                    "place_name": args.get("place_name", "未知地點"),
                    "arrival_time": "14:00"
                }
                trip["nodes"].append(new_node)

                if not enable_patches:
                    # 漏洞狀態：回傳原生 Dict，違反 MCP 官方 Envelope 格式
                    return {"jsonrpc": "2.0", "id": req_id, "result": {"status": "success", "node": new_node}}

                # 補丁狀態：標準 Envelope 封裝 + 分潤連結注入
                affiliate_link = "https://tabiji.app/go/klook/skytree-ticket"
                msg = f"已成功將 {new_node['place_name']} 加入第 {new_node['day_index']} 天行程！推薦門票: [點此預訂快速通關]({affiliate_link})"
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": format_mcp_tool_result(msg, is_error=False)
                }

        raise HTTPException(status_code=400, detail="Unknown method")

    return app

# ==============================================================================
# 2. In-Memory 測試案例 (紅軍 PoC ✕ 藍軍防禦 ✕ Mantis Block G 良性對照)
# ==============================================================================

@pytest.fixture
def vulnerable_client():
    app = create_test_app(enable_patches=False)
    return TestClient(app)

@pytest.fixture
def patched_client():
    app = create_test_app(enable_patches=True)
    return TestClient(app)


# ------------------------------------------------------------------------------
# [假說 1] Google OAuth 2.1 Discovery 缺失測試
# ------------------------------------------------------------------------------
def test_poc_missing_oauth_discovery(vulnerable_client):
    """紅軍 PoC: 未實作 OAuth Discovery 端點導致 404 (Google 連線拒絕)"""
    res = vulnerable_client.get("/.well-known/oauth-authorization-server")
    assert res.status_code == 404

def test_benign_oauth_metadata_discovery(patched_client):
    """藍軍良性對照: 合法回傳 RFC 8414 OAuth 2.1 Metadata"""
    res = patched_client.get("/.well-known/oauth-authorization-server")
    assert res.status_code == 200
    data = res.json()
    assert "authorization_endpoint" in data
    assert "token_endpoint" in data
    assert "S256" in data["code_challenge_methods_supported"]


# ------------------------------------------------------------------------------
# [假說 2] 跨租戶 IDOR 越權修改測試
# ------------------------------------------------------------------------------
def test_poc_cross_tenant_idor_mutation(vulnerable_client):
    """紅軍 PoC: 攻擊者 Mallory 攜帶自身有效 Token，越權修改 Alice 的行程"""
    res = vulnerable_client.post(
        "/api/mcp",
        headers={"Authorization": "Bearer tbj_pat_mallory_valid_secret"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "manage_itinerary_node",
                "arguments": {
                    "trip_id": "trip_alice_tokyo",
                    "day_index": 2,
                    "action": "add",
                    "place_name": "黑客惡意景點"
                }
            }
        }
    )
    assert res.status_code == 200
    # 在未修復狀態下，Alice 的行程被 Mallory 成功串改 (狀態碼 200 且無權限拒絕)
    data = res.json()
    assert "status" in data["result"] and data["result"]["status"] == "success"

def test_benign_prevent_cross_tenant_idor(patched_client):
    """藍軍良性對照: 攻擊者被嚴格判定為權限不足，且正常 Alice 能成功修改"""
    # 1. Mallory 嘗試篡改 Alice 行程 ➔ 必須被阻斷
    res_mallory = patched_client.post(
        "/api/mcp",
        headers={"Authorization": "Bearer tbj_pat_mallory_valid_secret"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "manage_itinerary_node",
                "arguments": {
                    "trip_id": "trip_alice_tokyo",
                    "day_index": 2,
                    "action": "add",
                    "place_name": "黑客惡意景點"
                }
            }
        }
    )
    assert res_mallory.status_code == 200
    res_data = res_mallory.json()["result"]
    assert res_data["isError"] is True
    assert "權限不足" in res_data["content"][0]["text"]

    # 2. Mantis Block G: 合法 Alice 自身呼叫 ➔ 必須順暢通過且格式正確
    res_alice = patched_client.post(
        "/api/mcp",
        headers={"Authorization": "Bearer tbj_pat_alice_valid_secret"},
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "manage_itinerary_node",
                "arguments": {
                    "trip_id": "trip_alice_tokyo",
                    "day_index": 2,
                    "action": "add",
                    "place_name": "東京晴空塔"
                }
            }
        }
    )
    assert res_alice.status_code == 200
    alice_data = res_alice.json()["result"]
    assert alice_data["isError"] is False
    assert "已成功將 東京晴空塔" in alice_data["content"][0]["text"]
    assert "https://tabiji.app/go/klook/skytree-ticket" in alice_data["content"][0]["text"]


# ------------------------------------------------------------------------------
# [假說 3] MCP Content Envelope 格式合規性測試
# ------------------------------------------------------------------------------
def test_benign_mcp_content_envelope_compliance(patched_client):
    """藍軍良性對照: 回傳結構必須嚴格包含 content list 與 type='text'"""
    res = patched_client.post(
        "/api/mcp",
        headers={"Authorization": "Bearer tbj_pat_alice_valid_secret"},
        json={
            "jsonrpc": "2.0",
            "id": 100,
            "method": "tools/call",
            "params": {
                "name": "manage_itinerary_node",
                "arguments": {
                    "trip_id": "trip_alice_tokyo",
                    "day_index": 1,
                    "action": "add",
                    "place_name": "雷門大燈籠"
                }
            }
        }
    )
    assert res.status_code == 200
    result = res.json()["result"]
    assert "content" in result
    assert isinstance(result["content"], list)
    assert result["content"][0]["type"] == "text"
    assert "isError" in result


# ------------------------------------------------------------------------------
# [假說 4] 分潤跳轉網關 Open-Redirect 攻擊測試
# ------------------------------------------------------------------------------
def test_poc_open_redirect_abuse(vulnerable_client):
    """紅軍 PoC: 未限制白名單時，攻擊者可藉由 /go 構造釣魚網址"""
    res = vulnerable_client.get("/go/klook/https://evil-phishing-site.com", follow_redirects=False)
    # 漏洞狀態：直接跳轉至惡意釣魚網址
    assert res.status_code == 302
    assert res.headers["location"] == "https://evil-phishing-site.com"

def test_benign_affiliate_safe_redirect(patched_client):
    """藍軍良性對照: 拒絕惡意跨站協議跳轉，僅允許合法白名單拼裝"""
    # 1. 攻擊者嘗試偽造絕對網址 ➔ 攔截 400
    res_attack = patched_client.get("/go/klook/https://evil-phishing-site.com", follow_redirects=False)
    assert res_attack.status_code == 400
    assert "Invalid target" in res_attack.json()["detail"]

    # 2. 偽造非法 Partner ➔ 攔截 400
    res_bad_partner = patched_client.get("/go/malicious_partner/ticket_123", follow_redirects=False)
    assert res_bad_partner.status_code == 400

    # 3. Mantis Block G: 合法 Klook 票券跳轉 ➔ 順暢跳轉至官方帶 Tag 網址
    res_valid = patched_client.get("/go/klook/activity/12345-skytree", follow_redirects=False)
    assert res_valid.status_code == 302
    assert res_valid.headers["location"] == "https://affiliate.klook.com/jump?aff_id=TABIJI_AFF_888&target=activity/12345-skytree"

