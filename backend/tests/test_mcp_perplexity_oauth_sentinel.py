# -*- coding: utf-8 -*-
"""
🛡️ Security Sentinel Adversarial Test Suite: Perplexity / Claude / ChatGPT OAuth 2.1 & Cross-Instance Resilience
Covers:
1. Target 1: backend/routers/mcp.py:perplexity_and_ai_redirect_uri_allowlist_and_https_enforcement
2. Target 2: backend/routers/mcp.py:oauth_code_cross_instance_state_loss_and_replay_defense
3. Target 3: backend/routers/mcp.py:oauth_client_id_validation_and_jwt_self_healing
4. Target 4: backend/routers/mcp.py:oauth_token_basic_auth_and_refresh_grant_contradiction
5. Target 5: backend/main.py:cors_claude_and_chatgpt_origin_preflight
6. Mantis Block G Benign Controls (Google Gemini OAuth intact, Open Redirect blocked, Localhost HTTP allowed)
"""

import base64
import hashlib
import urllib.parse
import jwt
from fastapi.testclient import TestClient
from main import app
from routers.mcp import OAUTH_CODES
from utils.deps import get_session_secret

client = TestClient(app)

ALICE_UUID = "3f7abf22-b447-4281-b240-584549c79943"


def _make_pkce_pair(verifier: str = "sentinel_perplexity_pkce_verifier_2026_secure"):
    h = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(h).decode("ascii").rstrip("=")
    return verifier, challenge


def test_sentinel_poc_perplexity_claude_chatgpt_redirect_uri_and_https_enforcement():
    """
    [Red Team PoC 1]
    Target: backend/routers/mcp.py:perplexity_and_ai_redirect_uri_allowlist_and_https_enforcement
    1. Perplexity, Claude, and ChatGPT official HTTPS OAuth callbacks must be permitted (302).
    2. Unencrypted HTTP on external trusted domains (e.g. http://www.google.com/callback) must be blocked (400).
    """
    _, challenge = _make_pkce_pair()
    trusted_ai_callbacks = [
        "https://www.perplexity.ai/rest/connections/oauth_callback",
        "https://enterprise.perplexity.ai/rest/connections/oauth_callback",
        "https://claude.ai/api/mcp/auth_callback",
        "https://claude.com/api/mcp/auth_callback",
        "https://chatgpt.com/connector_platform_oauth_redirect",
    ]
    for cb in trusted_ai_callbacks:
        resp = client.get(
            "/api/oauth/authorize",
            params={
                "client_id": ALICE_UUID,
                "redirect_uri": cb,
                "response_type": "code",
                "state": "state_xyz",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302, f"Expected 302 for trusted callback {cb}, got {resp.status_code}: {resp.text}"
        assert resp.headers["location"].startswith(f"{cb}?code=tbj_code_")

    # HTTP Downgrade attack on external trusted domain must be rejected (400)
    resp_http_downgrade = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": ALICE_UUID,
            "redirect_uri": "http://www.google.com/oauth/callback",
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert resp_http_downgrade.status_code == 400


def test_sentinel_poc_cross_instance_stateless_oauth_code_and_replay_defense():
    """
    [Red Team PoC 2]
    Target: backend/routers/mcp.py:oauth_code_cross_instance_state_loss_and_replay_defense
    Simulates Cloud Run multi-instance scaling where GET /api/oauth/authorize lands on Instance A,
    and POST /api/oauth/token from Perplexity's cloud backend lands on Instance B (where OAUTH_CODES is empty).
    Also verifies that replaying the same stateless code a second time on Instance B is strictly blocked.
    """
    verifier, challenge = _make_pkce_pair("cross_instance_verifier_9876543210")
    cb = "https://www.perplexity.ai/rest/connections/oauth_callback"

    resp_auth = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": ALICE_UUID,
            "redirect_uri": cb,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert resp_auth.status_code == 302
    parsed = urllib.parse.urlparse(resp_auth.headers["location"])
    auth_code = urllib.parse.parse_qs(parsed.query)["code"][0]

    # Simulate routing to a fresh Cloud Run instance (Instance B has empty OAUTH_CODES)
    OAUTH_CODES.clear()

    # First exchange on Instance B must succeed via stateless signed auth_code verification
    resp_token = client.post(
        "/api/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": cb,
            "client_id": ALICE_UUID,
            "code_verifier": verifier,
        },
    )
    assert resp_token.status_code == 200, f"Cross-instance token exchange failed: {resp_token.text}"
    token_data = resp_token.json()
    assert "access_token" in token_data
    decoded = jwt.decode(token_data["access_token"], get_session_secret(), algorithms=["HS256"], issuer="tabiji-core")
    assert decoded["sub"] == ALICE_UUID

    # Second exchange (replay attack) on Instance B must be rejected with 400
    resp_replay = client.post(
        "/api/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": cb,
            "client_id": ALICE_UUID,
            "code_verifier": verifier,
        },
    )
    assert resp_replay.status_code == 400
    assert "Invalid or expired authorization code" in resp_replay.json()["detail"]


def test_sentinel_poc_client_id_validation_and_jwt_self_healing():
    """
    [Red Team PoC 3]
    Target: backend/routers/mcp.py:oauth_client_id_validation_and_jwt_self_healing
    1. If user accidentally pastes their Connection Token (JWT) into Client ID, oauth_authorize self-heals
       and extracts the underlying UUID so the resulting token has a valid UUID sub.
    2. If user passes whitespace-padded UUID, it is stripped cleanly.
    3. If user passes an invalid non-UUID string (e.g. 'random_invalid_client'), oauth_authorize rejects
       immediately with HTTP 400 instead of issuing a poisoned token that fails later at tools/call.
    """
    verifier, challenge = _make_pkce_pair("self_healing_verifier_1234567890")
    cb = "https://www.perplexity.ai/rest/connections/oauth_callback"

    # Case 1: User pastes valid JWT into Client ID field
    sample_jwt = jwt.encode(
        {"sub": ALICE_UUID, "iss": "tabiji-core", "type": "device_session"},
        get_session_secret(),
        algorithm="HS256",
    )
    resp_jwt_cid = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": f"  {sample_jwt}  ",
            "redirect_uri": cb,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert resp_jwt_cid.status_code == 302
    code_from_jwt = urllib.parse.parse_qs(urllib.parse.urlparse(resp_jwt_cid.headers["location"]).query)["code"][0]

    resp_tok = client.post(
        "/api/oauth/token",
        json={
            "grant_type": "authorization_code",
            "code": code_from_jwt,
            "redirect_uri": cb,
            "code_verifier": verifier,
        },
    )
    assert resp_tok.status_code == 200
    issued_payload = jwt.decode(
        resp_tok.json()["access_token"], get_session_secret(), algorithms=["HS256"], issuer="tabiji-core"
    )
    assert issued_payload["sub"] == ALICE_UUID

    # Case 2: Invalid garbage client_id must be rejected at authorize time (400)
    resp_garbage = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": "not-a-valid-uuid-or-jwt",
            "redirect_uri": cb,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert resp_garbage.status_code == 400
    assert "Invalid client_id" in resp_garbage.json()["detail"]


def test_sentinel_poc_oauth_token_basic_auth_and_refresh_grant():
    """
    [Red Team PoC 4]
    Target: backend/routers/mcp.py:oauth_token_basic_auth_and_refresh_grant_contradiction
    1. Verifies RFC 6749 Section 2.3.1 HTTP Basic Authentication (client_secret_basic) at /api/oauth/token,
       including mismatch detection when Basic Auth client_id differs from authorized client_id.
    2. Verifies grant_type='refresh_token' (advertised in /.well-known/oauth-authorization-server) works seamlessly.
    """
    verifier, challenge = _make_pkce_pair("basic_auth_verifier_1234567890")
    cb = "https://www.perplexity.ai/rest/connections/oauth_callback"

    resp_auth = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": ALICE_UUID,
            "redirect_uri": cb,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert resp_auth.status_code == 302
    auth_code = urllib.parse.parse_qs(urllib.parse.urlparse(resp_auth.headers["location"]).query)["code"][0]

    # 1a. Mismatched Basic Auth client_id must be rejected with 400
    wrong_basic = base64.b64encode(b"00000000-0000-4000-8000-000000000999:secret").decode("ascii")
    resp_bad_basic = client.post(
        "/api/oauth/token",
        headers={"Authorization": f"Basic {wrong_basic}"},
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": cb,
            "code_verifier": verifier,
        },
    )
    assert resp_bad_basic.status_code == 400
    assert "client_id mismatch" in resp_bad_basic.json()["detail"]

    # 1b. Valid Basic Auth client_id exchange succeeds and returns refresh_token
    resp_auth2 = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": ALICE_UUID,
            "redirect_uri": cb,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    auth_code2 = urllib.parse.parse_qs(urllib.parse.urlparse(resp_auth2.headers["location"]).query)["code"][0]
    valid_basic = base64.b64encode(f"{ALICE_UUID}:my_secret_jwt".encode("ascii")).decode("ascii")

    resp_ok_basic = client.post(
        "/api/oauth/token",
        headers={"Authorization": f"Basic {valid_basic}"},
        data={
            "grant_type": "authorization_code",
            "code": auth_code2,
            "redirect_uri": cb,
            "code_verifier": verifier,
        },
    )
    assert resp_ok_basic.status_code == 200
    tok_json = resp_ok_basic.json()
    assert "access_token" in tok_json
    assert "refresh_token" in tok_json

    # 2. Refresh token grant works as advertised in oauth_metadata
    resp_refresh = client.post(
        "/api/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tok_json["refresh_token"],
        },
    )
    assert resp_refresh.status_code == 200
    refreshed_json = resp_refresh.json()
    assert "access_token" in refreshed_json
    decoded = jwt.decode(refreshed_json["access_token"], get_session_secret(), algorithms=["HS256"], issuer="tabiji-core")
    assert decoded["sub"] == ALICE_UUID


def test_sentinel_poc_cors_claude_chatgpt_preflight():
    """
    [Red Team PoC 5]
    Target: backend/main.py:cors_claude_and_chatgpt_origin_preflight
    Verifies that CORS preflight requests from https://claude.ai and https://chatgpt.com are permitted.
    """
    for origin in ("https://claude.ai", "https://chatgpt.com", "https://www.perplexity.ai"):
        resp = client.options(
            "/api/mcp",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
        assert resp.status_code == 200, f"CORS preflight failed for {origin}: {resp.status_code}"
        assert resp.headers.get("access-control-allow-origin") == origin


# ============================================================================
# Mantis Block G: Benign Control Group (良性對照防閹割測試)
# ============================================================================

def test_benign_google_gemini_oauth_flow_intact():
    """[Mantis Block G 1] Google Gemini OAuth redirect and token exchange remain 100% functional."""
    verifier, challenge = _make_pkce_pair("gemini_benign_verifier_1234567890")
    cb = "https://oauth-redirect.googleusercontent.com/r/user_bound_custom-mcp"

    resp_auth = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": ALICE_UUID,
            "redirect_uri": cb,
            "response_type": "code",
            "state": "gemini_state",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert resp_auth.status_code == 302
    code = urllib.parse.parse_qs(urllib.parse.urlparse(resp_auth.headers["location"]).query)["code"][0]

    resp_token = client.post(
        "/api/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cb,
            "client_id": ALICE_UUID,
            "code_verifier": verifier,
        },
    )
    assert resp_token.status_code == 200
    assert resp_token.json()["token_type"] == "Bearer"


def test_benign_malicious_open_redirect_blocked():
    """[Mantis Block G 2] Malicious domains, lookalike domains, and non-HTTPS external URLs are strictly blocked."""
    _, challenge = _make_pkce_pair()
    malicious_uris = [
        "https://evil-perplexity.ai/callback",
        "https://perplexity.ai.attacker.com/callback",
        "http://www.perplexity.ai/rest/connections/oauth_callback",
        "javascript:alert(1)",
        "https://attacker.com/perplexity.ai",
    ]
    for uri in malicious_uris:
        resp = client.get(
            "/api/oauth/authorize",
            params={
                "client_id": ALICE_UUID,
                "redirect_uri": uri,
                "response_type": "code",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 400, f"Malicious URI {uri} was not blocked!"


def test_benign_localhost_http_development_allowed():
    """[Mantis Block G 3] Local development over http://localhost and http://127.0.0.1 remains permitted."""
    _, challenge = _make_pkce_pair()
    for local_uri in ("http://localhost:3000/api/oauth/callback", "http://127.0.0.1:8000/callback"):
        resp = client.get(
            "/api/oauth/authorize",
            params={
                "client_id": ALICE_UUID,
                "redirect_uri": local_uri,
                "response_type": "code",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
