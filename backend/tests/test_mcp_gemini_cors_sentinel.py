# -*- coding: utf-8 -*-
"""
🛡️ Security Sentinel In-Memory PoC Test Suite: MCP Gemini CORS & RFC 9728 Compliance
Validates:
1. Target SEC-MCP-CORS-001: OPTIONS Preflight for https://gemini.google.com and https://aistudio.google.com
2. Target SEC-MCP-RFC9728-001: Public domain & HTTPS preservation via get_public_base_url
3. Target SEC-MCP-PROTO-001: Dynamic Protocol Version Negotiation (2026-07-28, 2025-03-26, 2024-11-05)
4. Target SEC-MCP-PROBE-001: HTTP GET / HEAD health & readiness probes
5. Mantis Block G: Benign controls preserving localhost, tabiji origins, and rejecting evil origins
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_benign_local_origins_allowed():
    """Mantis Block G: Localhost and official domain preflight must succeed"""
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type"
    }
    resp = client.options("/api/mcp", headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_benign_malicious_origin_blocked():
    """Mantis Block G: Malicious/untrusted origin must be rejected"""
    headers = {
        "Origin": "https://malicious-phishing-site.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type"
    }
    resp = client.options("/api/mcp", headers=headers)
    # Disallowed origins are rejected by Starlette CORS with 400 or no allow-origin header
    assert resp.status_code == 400 or resp.headers.get("access-control-allow-origin") is None


def test_benign_forged_forwarded_host_injection_rejected():
    """Mantis Block G: Forged X-Forwarded-Host header must not poison discovery metadata"""
    forged_headers = {
        "x-forwarded-host": "evil-phishing-site.com",
        "x-forwarded-proto": "https"
    }
    resp = client.get("/.well-known/oauth-protected-resource", headers=forged_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "evil-phishing-site.com" not in data["resource"]
    assert "evil-phishing-site.com" not in data["authorization_servers"][0]


def test_sentinel_poc_cors_gemini_options_preflight():
    """
    Target: backend/main.py:mcp_cors_external_ai_preflight_rejection
    Verifies that Google Gemini and AI Studio web origins receive valid CORS preflight headers.
    """
    origins_to_test = [
        "https://gemini.google.com",
        "https://aistudio.google.com"
    ]
    for origin in origins_to_test:
        headers = {
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type,mcp-session-id"
        }
        resp = client.options("/api/mcp", headers=headers)
        assert resp.status_code == 200, f"Expected 200 for origin {origin}, got {resp.status_code} ({resp.text})"
        assert resp.headers.get("access-control-allow-origin") == origin


def test_sentinel_poc_rfc9728_public_domain_preservation():
    """
    Target: backend/routers/mcp.py:rfc9728_domain_and_protocol_tear
    Verifies that reverse-proxy forwarded headers preserve https://www.tabijiapp.com
    and do not leak internal Cloud Run or testserver origins.
    """
    forwarded_headers = {
        "x-forwarded-host": "www.tabijiapp.com",
        "x-forwarded-proto": "https",
        "host": "www.tabijiapp.com"
    }
    
    # 1. Protected Resource Metadata (RFC 9728)
    resp = client.get("/.well-known/oauth-protected-resource", headers=forwarded_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["resource"] == "https://www.tabijiapp.com/api/mcp"
    assert data["authorization_servers"] == ["https://www.tabijiapp.com"]
    
    # 2. Authorization Server Metadata (RFC 8414)
    resp_auth = client.get("/.well-known/oauth-authorization-server", headers=forwarded_headers)
    assert resp_auth.status_code == 200
    auth_data = resp_auth.json()
    assert auth_data["issuer"] == "https://www.tabijiapp.com"
    assert auth_data["authorization_endpoint"] == "https://www.tabijiapp.com/api/oauth/authorize"
    assert auth_data["token_endpoint"] == "https://www.tabijiapp.com/api/oauth/token"


def test_sentinel_poc_protocol_version_negotiation():
    """
    Target: backend/routers/mcp.py:legacy_protocol_version_negotiation_failure
    Verifies protocolVersion negotiation for 2026-07-28 and 2025-03-26.
    """
    # 1. Requesting 2026-07-28
    resp_2026 = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "init-1",
            "method": "initialize",
            "params": {
                "protocolVersion": "2026-07-28",
                "capabilities": {}
            }
        }
    )
    assert resp_2026.status_code == 200
    assert resp_2026.json()["result"]["protocolVersion"] == "2026-07-28"

    # 2. Requesting 2025-03-26
    resp_2025 = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "init-2",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {}
            }
        }
    )
    assert resp_2025.status_code == 200
    assert resp_2025.json()["result"]["protocolVersion"] == "2025-03-26"

    # 3. Mantis Block G: Backwards compatibility when params is empty or omitted
    resp_legacy = client.post(
        "/api/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "init-legacy",
            "method": "initialize",
            "params": {}
        }
    )
    assert resp_legacy.status_code == 200
    assert resp_legacy.json()["result"]["protocolVersion"] == "2024-11-05"


def test_sentinel_poc_http_get_head_probes():
    """
    Target: backend/routers/mcp.py:http_get_head_discovery_probe_blocked
    Verifies that GET and HEAD requests to /api/mcp return 200 OK for connectivity verification.
    """
    # 1. GET probe
    resp_get = client.get("/api/mcp")
    assert resp_get.status_code == 200
    get_data = resp_get.json()
    assert get_data["status"] == "ok"
    assert "tabiji-mcp-server" in get_data.get("server", "")

    # 2. HEAD probe
    resp_head = client.head("/api/mcp")
    assert resp_head.status_code == 200

