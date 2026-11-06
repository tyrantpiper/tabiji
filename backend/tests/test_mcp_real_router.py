# -*- coding: utf-8 -*-
"""
🛡️ Real Router Integration Test Suite: Tabiji Remote MCP & Affiliate Gateway
Tests the actual routers mounted in backend/main.py.
Verifies RFC 8414 OAuth 2.1 metadata discovery, MCP JSON-RPC 2.0 dispatcher,
IDOR cross-tenant defense, Mantis Block G envelope, and Open-Redirect protection.
"""

import sys
import os
import uuid
import pytest
from unittest.mock import MagicMock, patch

# 確保 backend 目錄在 sys.path 中
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

ALICE_UUID = str(uuid.uuid4())
MALLORY_UUID = str(uuid.uuid4())
TRIP_ID = str(uuid.uuid4())


def test_oauth_metadata_discovery_real():
    """驗證 Google Connected Apps OAuth 2.1 Discovery 端點正常工作"""
    resp = client.get("/.well-known/oauth-authorization-server")
    assert resp.status_code == 200
    data = resp.json()
    assert "authorization_endpoint" in data
    assert "token_endpoint" in data
    assert "S256" in data["code_challenge_methods_supported"]
    assert "code" in data["response_types_supported"]


def test_mcp_initialize_real():
    """驗證 MCP initialize 握手協商"""
    resp = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {}
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == 1
    assert data["result"]["protocolVersion"] == "2024-11-05"
    assert "tools" in data["result"]["capabilities"]


def test_mcp_notifications_initialized_real():
    """驗證 MCP notifications/initialized 握手回應"""
    resp = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
    )
    assert resp.status_code == 200


def test_mcp_tools_list_real():
    """驗證 MCP tools/list 回傳宣告之工具列表"""
    resp = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    tools = data["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "manage_itinerary_node" in tool_names
    assert "recommend_tickets" in tool_names


def test_mcp_auth_missing_or_invalid():
    """驗證 tools/call 未提供或無效 Bearer Token 回傳 JSON-RPC 錯誤"""
    # 1. 缺失 Authorization header
    resp = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "manage_itinerary_node", "arguments": {}}
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"]["code"] == -32000
    assert "Unauthorized" in data["error"]["message"]

    # 2. 無效 Token
    resp_invalid = client.post(
        "/api/mcp",
        headers={"Authorization": "Bearer invalid_garbage_token"},
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "manage_itinerary_node", "arguments": {}}
        }
    )
    assert resp_invalid.status_code == 200
    data_inv = resp_invalid.json()
    assert data_inv["error"]["code"] == -32000


def test_mcp_idor_isolation_real():
    """驗證攻擊者 Mallory 攜帶有效 Token 嘗試越權修改 Alice 行程時被拒絕"""
    # 模擬 Supabase 回傳 Alice 的行程 (created_by: ALICE_UUID)
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[
        {"id": TRIP_ID, "created_by": ALICE_UUID, "title": "Alice 東京行程"}
    ])

    with patch("routers.mcp.get_verified_user", return_value=MALLORY_UUID), \
         patch("routers.mcp.get_supabase", return_value=mock_supabase):
        resp = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer valid_mallory_token"},
            json={
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "manage_itinerary_node",
                    "arguments": {
                        "trip_id": TRIP_ID,
                        "day_index": 1,
                        "action": "add",
                        "place_name": "黑客惡意景點"
                    }
                }
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["isError"] is True
        assert "權限不足" in data["result"]["content"][0]["text"]


def test_mcp_legitimate_call_alice_real():
    """驗證合法擁有者 Alice 呼叫 manage_itinerary_node 順暢通過且遵循 Mantis Block G"""
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[
        {"id": TRIP_ID, "created_by": ALICE_UUID, "title": "Alice 東京行程"}
    ])

    with patch("routers.mcp.get_verified_user", return_value=ALICE_UUID), \
         patch("routers.mcp.get_supabase", return_value=mock_supabase):
        resp = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer valid_alice_token"},
            json={
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {
                    "name": "manage_itinerary_node",
                    "arguments": {
                        "trip_id": TRIP_ID,
                        "day_index": 2,
                        "action": "add",
                        "place_name": "東京晴空塔"
                    }
                }
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data["result"]
        assert result["isError"] is False
        assert isinstance(result["content"], list)
        assert result["content"][0]["type"] == "text"
        assert "東京晴空塔" in result["content"][0]["text"]
        assert "https://tabiji.app/go/klook/" in result["content"][0]["text"]


def test_mcp_recommend_tickets_real():
    """驗證 recommend_tickets 推薦工具回傳標準 Envelope"""
    with patch("routers.mcp.get_verified_user", return_value=ALICE_UUID):
        resp = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer valid_alice_token"},
            json={
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {
                    "name": "recommend_tickets",
                    "arguments": {
                        "place_name": "teamLab Planets",
                        "destination": "東京"
                    }
                }
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["isError"] is False
        assert "teamLab Planets" in data["result"]["content"][0]["text"]


def test_mcp_unknown_tool_and_method():
    """驗證未知工具或未定義方法回傳 -32601 錯誤碼"""
    with patch("routers.mcp.get_verified_user", return_value=ALICE_UUID):
        # 1. 未知工具
        resp_tool = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer valid_alice_token"},
            json={
                "jsonrpc": "2.0",
                "id": 20,
                "method": "tools/call",
                "params": {"name": "non_existent_tool", "arguments": {}}
            }
        )
        assert resp_tool.status_code == 200
        assert resp_tool.json()["error"]["code"] == -32601

        # 2. 未知方法
        resp_method = client.post(
            "/api/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 21,
                "method": "unknown_rpc_procedure"
            }
        )
        assert resp_method.status_code == 200
        assert resp_method.json()["error"]["code"] == -32601


# ═══════════════════════════════════════════════════════════════════════════════
# Affiliate Gateway Tests (/go)
# ═══════════════════════════════════════════════════════════════════════════════

def test_affiliate_gateway_whitelisted_redirect():
    """驗證合法白名單夥伴跳轉為 302 重導向"""
    resp_klook = client.get("/go/klook/activity/123-tokyo-tower", follow_redirects=False)
    assert resp_klook.status_code == 302
    assert "https://affiliate.klook.com/jump?aff_id=TABIJI_AFF_888&target=activity/123-tokyo-tower" == resp_klook.headers["location"]

    resp_kkday = client.get("/go/kkday/product/456", follow_redirects=False)
    assert resp_kkday.status_code == 302
    assert "https://www.kkday.com/zh-tw/affiliate/jump?cid=TABIJI_AFF_999&url=product/456" == resp_kkday.headers["location"]


def test_affiliate_gateway_open_redirect_defense():
    """驗證防範 Open Redirect 與 SSRF 攻擊"""
    # 1. 偽造包含 scheme 的絕對網址
    resp1 = client.get("/go/klook/https://evil-phishing.com", follow_redirects=False)
    assert resp1.status_code == 400

    # 2. 協議相對網址 (//evil.com)
    resp2 = client.get("/go/klook///evil.com", follow_redirects=False)
    assert resp2.status_code == 400

    # 3. 非白名單合作夥伴
    resp3 = client.get("/go/unknown_partner/test", follow_redirects=False)
    assert resp3.status_code == 400

    # 4. 反斜線路徑繞過攻擊
    resp4 = client.get("/go/klook/\\evil.com", follow_redirects=False)
    assert resp4.status_code == 400

    # 5. Query String 中嘗試注入 Open Redirect 協議
    resp5 = client.get("/go/klook/tokyo?url=https://evil.com", follow_redirects=False)
    assert resp5.status_code == 400


def test_affiliate_gateway_unicode_and_query_forwarding():
    """驗證 Unicode 地區名稱 (東京) 與 Query String (?item=東京晴空塔) 正常跳轉且安全保留"""
    resp = client.get("/go/klook/東京?item=東京晴空塔", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert "https://affiliate.klook.com/jump?aff_id=TABIJI_AFF_888&target=" in location
    assert "item=" in location


def test_mcp_malformed_payload():
    """驗證非 dict 之 payload (例如 []) 回傳 400 而非 500"""
    resp = client.post("/api/mcp", json=[])
    assert resp.status_code == 400
    assert "Invalid JSON-RPC payload" in resp.json()["detail"]


def test_mcp_null_or_missing_arguments():
    """驗證 arguments 為 None 或 missing trip_id 順暢處理不拋出 500"""
    with patch("routers.mcp.get_verified_user", return_value=ALICE_UUID):
        # 1. arguments: None
        resp_null = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer valid_alice_token"},
            json={
                "jsonrpc": "2.0",
                "id": 30,
                "method": "tools/call",
                "params": {"name": "manage_itinerary_node", "arguments": None}
            }
        )
        assert resp_null.status_code == 200
        assert resp_null.json()["result"]["isError"] is True
        assert "缺少必要的行程識別碼" in resp_null.json()["result"]["content"][0]["text"]

        # 2. missing trip_id
        resp_notrip = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer valid_alice_token"},
            json={
                "jsonrpc": "2.0",
                "id": 31,
                "method": "tools/call",
                "params": {"name": "manage_itinerary_node", "arguments": {"place_name": "富士山"}}
            }
        )
        assert resp_notrip.status_code == 200
        assert resp_notrip.json()["result"]["isError"] is True


def test_mcp_actions_remove_and_update():
    """驗證 manage_itinerary_node 支援 remove 與 update 操作"""
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[
        {"id": TRIP_ID, "created_by": ALICE_UUID, "title": "Alice 東京行程"}
    ])

    with patch("routers.mcp.get_verified_user", return_value=ALICE_UUID), \
         patch("routers.mcp.get_supabase", return_value=mock_supabase):
        # 1. remove
        resp_rm = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer valid_alice_token"},
            json={
                "jsonrpc": "2.0",
                "id": 40,
                "method": "tools/call",
                "params": {
                    "name": "manage_itinerary_node",
                    "arguments": {
                        "trip_id": TRIP_ID,
                        "day_index": 1,
                        "action": "remove",
                        "place_name": "東京晴空塔"
                    }
                }
            }
        )
        assert resp_rm.status_code == 200
        assert "移除景點" in resp_rm.json()["result"]["content"][0]["text"]

        # 2. update
        resp_up = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer valid_alice_token"},
            json={
                "jsonrpc": "2.0",
                "id": 41,
                "method": "tools/call",
                "params": {
                    "name": "manage_itinerary_node",
                    "arguments": {
                        "trip_id": TRIP_ID,
                        "day_index": 1,
                        "action": "update",
                        "place_name": "東京鐵塔"
                    }
                }
            }
        )
        assert resp_up.status_code == 200
        assert "更新景點" in resp_up.json()["result"]["content"][0]["text"]


def test_real_oauth_authorize_and_token_flow():
    """驗證真機環境 /api/oauth/authorize 與 /api/oauth/token 流程與 PKCE S256 驗證"""
    import hashlib
    import base64
    import urllib.parse

    code_verifier = "real_router_verifier_string_abcdef1234567890"
    h = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(h).decode("ascii").rstrip("=")

    redirect_target = "https://gemini.google.com/oauth-callback"
    resp_auth = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": ALICE_UUID,
            "redirect_uri": redirect_target,
            "response_type": "code",
            "state": "test_state_123",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256"
        },
        follow_redirects=False
    )
    assert resp_auth.status_code == 302
    location = resp_auth.headers["location"]
    assert location.startswith(redirect_target)
    assert "code=tbj_code_" in location
    assert "state=test_state_123" in location

    parsed = urllib.parse.urlparse(location)
    q = urllib.parse.parse_qs(parsed.query)
    auth_code = q["code"][0]

    # Token exchange
    resp_token = client.post(
        "/api/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": redirect_target,
            "client_id": ALICE_UUID,
            "code_verifier": code_verifier
        }
    )
    assert resp_token.status_code == 200
    data = resp_token.json()
    assert "access_token" in data
    assert data["token_type"] == "Bearer"


def test_real_oauth_pkce_mismatch_and_replay_defense():
    """驗證真機端點防範 PKCE 篡改與授權碼重放攻擊"""
    import hashlib
    import base64

    code_verifier = "legit_verifier_12345"
    h = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(h).decode("ascii").rstrip("=")

    resp_auth = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": ALICE_UUID,
            "redirect_uri": "https://gemini.google.com/callback",
            "code_challenge": code_challenge
        },
        follow_redirects=False
    )
    location = resp_auth.headers["location"]
    auth_code = location.split("code=")[1].split("&")[0]

    # 1. Tampered verifier -> 400
    res_bad = client.post(
        "/api/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": auth_code,
            "code_verifier": "wrong_verifier"
        }
    )
    assert res_bad.status_code == 400
    assert "PKCE S256 verification failed" in res_bad.json()["detail"]

    # 2. Replay attack -> 400 (code was popped)
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


def test_real_oauth_form_urlencoded_rfc6749():
    """驗證標準 RFC 6749 application/x-www-form-urlencoded 格式之授權碼交換"""
    import hashlib
    import base64

    code_verifier = "form_urlencoded_verifier_1234567890abcdef"
    h = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(h).decode("ascii").rstrip("=")

    resp_auth = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": ALICE_UUID,
            "redirect_uri": "https://gemini.google.com/oauth-callback",
            "code_challenge": code_challenge
        },
        follow_redirects=False
    )
    assert resp_auth.status_code == 302
    auth_code = resp_auth.headers["location"].split("code=")[1].split("&")[0]

    # POST 使用 data= (發送 application/x-www-form-urlencoded)
    resp_token = client.post(
        "/api/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": "https://gemini.google.com/oauth-callback",
            "client_id": ALICE_UUID,
            "code_verifier": code_verifier
        }
    )
    assert resp_token.status_code == 200
    data = resp_token.json()
    assert "access_token" in data
    assert data["token_type"] == "Bearer"


def test_real_oauth_parameter_validation_and_errors():
    """驗證 OAuth 2.1 參數檢驗：response_type、code_challenge_method、grant_type、redirect_uri 與 client_id 邊界防禦"""
    import hashlib
    import base64
    import time
    from routers.mcp import OAUTH_CODES

    # 1. GET /api/oauth/authorize 不支援的 response_type -> 400
    res_bad_resp = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": ALICE_UUID,
            "redirect_uri": "https://gemini.google.com/callback",
            "response_type": "token"
        }
    )
    assert res_bad_resp.status_code == 400
    assert "Unsupported response_type" in res_bad_resp.json()["detail"]

    # 2. GET /api/oauth/authorize 不支援的 code_challenge_method (例如 plain) -> 400
    res_bad_method = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": ALICE_UUID,
            "redirect_uri": "https://gemini.google.com/callback",
            "code_challenge_method": "plain"
        }
    )
    assert res_bad_method.status_code == 400
    assert "Unsupported code_challenge_method" in res_bad_method.json()["detail"]

    # 建立合法 code
    code_verifier = "boundary_verifier_1234567890abcdef"
    h = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(h).decode("ascii").rstrip("=")

    resp_auth = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": ALICE_UUID,
            "redirect_uri": "https://gemini.google.com/callback",
            "code_challenge": code_challenge
        },
        follow_redirects=False
    )
    auth_code = resp_auth.headers["location"].split("code=")[1].split("&")[0]

    # 3. 不支援的 grant_type -> 400
    res_bad_grant = client.post(
        "/api/oauth/token",
        json={
            "grant_type": "client_credentials",
            "code": auth_code,
            "code_verifier": code_verifier
        }
    )
    assert res_bad_grant.status_code == 400
    assert "Unsupported grant_type" in res_bad_grant.json()["detail"]

    # 4. redirect_uri 不一致 -> 400 (代碼被消費)
    res_bad_redirect = client.post(
        "/api/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": "https://malicious-hijack.com/callback",
            "code_verifier": code_verifier
        }
    )
    assert res_bad_redirect.status_code == 400
    assert "redirect_uri mismatch" in res_bad_redirect.json()["detail"]

    # 5. client_id 不一致 -> 400
    resp_auth2 = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": ALICE_UUID,
            "redirect_uri": "https://gemini.google.com/callback",
            "code_challenge": code_challenge
        },
        follow_redirects=False
    )
    auth_code2 = resp_auth2.headers["location"].split("code=")[1].split("&")[0]

    res_bad_client = client.post(
        "/api/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": auth_code2,
            "client_id": "different-client-id",
            "code_verifier": code_verifier
        }
    )
    assert res_bad_client.status_code == 400
    assert "client_id mismatch" in res_bad_client.json()["detail"]

    # 6. 非 ASCII code_verifier (防範 500 crash) -> 400
    resp_auth3 = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": ALICE_UUID,
            "redirect_uri": "https://gemini.google.com/callback",
            "code_challenge": code_challenge
        },
        follow_redirects=False
    )
    auth_code3 = resp_auth3.headers["location"].split("code=")[1].split("&")[0]

    res_non_ascii = client.post(
        "/api/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": auth_code3,
            "code_verifier": "verifier_with_emoji_🔥"
        }
    )
    assert res_non_ascii.status_code == 400
    assert "Invalid code_verifier encoding" in res_non_ascii.json()["detail"]

    # 7. 模擬過期授權碼 (> 300 秒)
    resp_auth4 = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": ALICE_UUID,
            "redirect_uri": "https://gemini.google.com/callback",
            "code_challenge": code_challenge
        },
        follow_redirects=False
    )
    auth_code4 = resp_auth4.headers["location"].split("code=")[1].split("&")[0]
    OAUTH_CODES[auth_code4]["expires_at"] = time.time() - 10

    res_expired = client.post(
        "/api/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": auth_code4,
            "code_verifier": code_verifier
        }
    )
    assert res_expired.status_code == 400
    assert "Invalid or expired authorization code" in res_expired.json()["detail"]




