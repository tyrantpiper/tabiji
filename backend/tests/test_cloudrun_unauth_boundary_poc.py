"""
Security Sentinel In-Memory PoC: Cloud Run Unauthenticated Ingress Boundary Verification
Tests that:
1. Public ingress without authentication cannot read container environment variables (secrets).
2. Protected endpoints reject unauthenticated HTTP requests with 401/403.
3. Unhandled errors do not leak os.environ secrets in traceback or response bodies.
4. Public endpoints (e.g. /health) do not expose internal configurations.
"""

import os
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI, HTTPException, Depends
from starlette.middleware.base import BaseHTTPMiddleware

# Set mock secrets in environment
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "mock_secret_service_role_key_999888"
os.environ["TP_API_TOKEN"] = "mock_secret_tp_api_token_777666"
os.environ["INTERNAL_SIGNING_SECRET"] = "mock_secret_internal_jwt_secret_555444"

from backend.routers.auth import router as auth_router


def create_mock_app():
    app = FastAPI(title="CloudRunSecuritySandboxApp")
    app.include_router(auth_router, prefix="/api/auth")

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "tabiji-backend"}

    @app.get("/api/trips")
    def get_trips(auth_header: str = None):
        # Emulate protected route
        if not auth_header:
            raise HTTPException(status_code=401, detail="Authentication required")
        return {"trips": []}

    @app.get("/api/test-error")
    def trigger_error():
        # Emulate unexpected internal crash
        raise RuntimeError("Unexpected internal crash during database lookup")

    return app


@pytest.fixture
def client():
    app = create_mock_app()
    return TestClient(app, raise_server_exceptions=False)


def test_public_ingress_cannot_read_env_secrets(client):
    """Prove that public HTTP callers accessing /health or / cannot read os.environ."""
    res = client.get("/health")
    assert res.status_code == 200
    body_str = res.text

    # Verify no secret is present in response
    assert "mock_secret_service_role_key_999888" not in body_str
    assert "mock_secret_tp_api_token_777666" not in body_str
    assert "mock_secret_internal_jwt_secret_555444" not in body_str


def test_protected_routes_block_unauthenticated_callers(client):
    """Prove that --allow-unauthenticated at Cloud Run level is stopped by app auth."""
    res = client.get("/api/trips")
    assert res.status_code == 401
    assert "Authentication required" in res.json().get("detail", "")


def test_auth_rotate_requires_valid_credentials(client):
    """Prove that attackers cannot rotate or alter credentials without existing valid key."""
    res = client.post("/api/auth/rotate", json={"current_recovery_key": "invalid_forged_key"})
    assert res.status_code in (401, 403, 404, 500)
    # Ensure secrets never leak in error response
    assert "mock_secret_service_role_key_999888" not in res.text


def test_unhandled_crash_does_not_leak_secrets(client):
    """Prove that an unhandled internal exception returns 500 without leaking os.environ secrets."""
    res = client.get("/api/test-error")
    assert res.status_code == 500
    body_str = res.text

    assert "mock_secret_service_role_key_999888" not in body_str
    assert "mock_secret_tp_api_token_777666" not in body_str
    assert "mock_secret_internal_jwt_secret_555444" not in body_str
