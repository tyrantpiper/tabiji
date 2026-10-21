"""
🛡️ Security Sentinel: Post-Patch Verification Test Suite for P0 Auth & IDOR Hardening
Verifies:
1. Private endpoints strictly require Bearer JWT (401 Unauthorized without token)
2. Spoofed X-User-ID without Bearer token is rejected (401 Unauthorized)
3. POST /api/auth/session provides silent token issuance & exchange
4. POST /api/auth/recover provides rate-limited recovery restoration
5. Dynamic Masking in trips: collaborators cannot view creator's real UUID
6. Dynamic Masking in expenses: collaborators cannot view creator's or payer's real UUID
7. Hardcoded Header endpoints (e.g. /leave) now strictly enforce Bearer JWT
"""

import time
import jwt
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from main import app
from utils.deps import get_supabase, get_session_secret


@pytest.fixture
def mock_supabase():
    client = MagicMock()
    return client


@pytest.fixture
def test_client(mock_supabase):
    app.dependency_overrides[get_supabase] = lambda: mock_supabase
    app.state.supabase = mock_supabase
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def make_token(user_id: str) -> str:
    secret = get_session_secret()
    payload = {
        "sub": user_id,
        "iss": "tabiji-core",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "type": "device_session"
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def make_auth_headers(user_id: str) -> dict:
    return {"Authorization": f"Bearer {make_token(user_id)}"}


def test_auth_sentinel_unauthenticated_request_rejected(test_client):
    """[VERIFICATION 1]: Request without token is rejected with 401."""
    response = test_client.get("/api/trips")
    assert response.status_code == 401
    assert "token" in response.json()["detail"].lower()


def test_auth_sentinel_spoofed_x_user_id_rejected(test_client):
    """[VERIFICATION 2]: Spoofed X-User-ID without valid Bearer token is rejected with 401."""
    victim_id = "00000000-0000-0000-0000-000000000001"
    response = test_client.get(
        "/api/trips",
        headers={"X-User-ID": victim_id}
    )
    assert response.status_code == 401


def test_auth_sentinel_valid_token_accepted(test_client, mock_supabase):
    """[VERIFICATION 3]: Valid Bearer JWT is authenticated via in-memory fast decode."""
    user_id = "00000000-0000-0000-0000-000000000001"
    mock_supabase.table().select().eq().execute.return_value = MagicMock(
        data=[{"id": "trip-1", "title": "My Trip", "created_by": user_id}]
    )

    response = test_client.get(
        "/api/trips",
        headers=make_auth_headers(user_id)
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_auth_sentinel_session_endpoint_issuance_and_exchange(test_client):
    """[VERIFICATION 4]: POST /api/auth/session issues valid token."""
    # New user
    res1 = test_client.post("/api/auth/session", json={})
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["is_new"] is True
    assert "access_token" in d1

    # Existing user exchange
    existing_key = "2a8b7442-9b9c-491d-aadc-b13311af418d"
    res2 = test_client.post("/api/auth/session", json={"recovery_key": existing_key})
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["is_new"] is False
    assert d2["user_id"] == existing_key


def test_auth_sentinel_recover_endpoint(test_client):
    """[VERIFICATION 5]: POST /api/auth/recover restores account."""
    existing_key = "2a8b7442-9b9c-491d-aadc-b13311af418d"
    res = test_client.post("/api/auth/recover", json={"recovery_key": existing_key})
    assert res.status_code == 200
    assert res.json()["user_id"] == existing_key


def test_auth_sentinel_trip_masking_collaborator_vs_owner(test_client, mock_supabase):
    """[VERIFICATION 6]: Collaborator Bob CANNOT see Alice's UUID, while Alice sees her own UUID."""
    alice_id = "11111111-1111-1111-1111-111111111111"
    bob_id = "22222222-2222-2222-2222-222222222222"

    mock_supabase.table().select().eq().execute.side_effect = [
        # Trip
        MagicMock(data=[{
            "id": "shared-trip-123",
            "title": "Tokyo Trip",
            "created_by": alice_id,
            "creator_name": "Alice",
            "start_date": "2026-11-01",
            "end_date": "2026-11-05",
            "content": {}
        }]),
        # Members
        MagicMock(data=[
            {"user_id": alice_id, "user_name": "Alice", "user_avatar": ""},
            {"user_id": bob_id, "user_name": "Bob", "user_avatar": ""}
        ]),
        # Items
        MagicMock(data=[])
    ]

    # Bob queries trip
    res_bob = test_client.get(
        "/api/trips/shared-trip-123",
        headers=make_auth_headers(bob_id)
    )
    assert res_bob.status_code == 200
    data_bob = res_bob.json()

    # Bob MUST NOT see Alice's raw UUID
    assert data_bob["is_owner"] is False
    assert data_bob["created_by"] is None
    bob_view_alice_id = next(m["user_id"] for m in data_bob["members"] if m["user_name"] == "Alice")
    assert bob_view_alice_id != alice_id
    assert bob_view_alice_id.startswith("mem_")

    # Reset mock for Alice
    mock_supabase.table().select().eq().execute.side_effect = [
        MagicMock(data=[{
            "id": "shared-trip-123",
            "title": "Tokyo Trip",
            "created_by": alice_id,
            "creator_name": "Alice",
            "start_date": "2026-11-01",
            "end_date": "2026-11-05",
            "content": {}
        }]),
        MagicMock(data=[
            {"user_id": alice_id, "user_name": "Alice", "user_avatar": ""},
            {"user_id": bob_id, "user_name": "Bob", "user_avatar": ""}
        ]),
        MagicMock(data=[])
    ]

    # Alice queries trip
    res_alice = test_client.get(
        "/api/trips/shared-trip-123",
        headers=make_auth_headers(alice_id)
    )
    assert res_alice.status_code == 200
    data_alice = res_alice.json()

    # Alice CAN see her own UUID and is_owner is True
    assert data_alice["is_owner"] is True
    assert data_alice["created_by"] == alice_id


def test_auth_sentinel_expenses_masking(test_client, mock_supabase):
    """[VERIFICATION 7]: Collaborator Bob CANNOT see Alice's UUID in expenses."""
    alice_id = "11111111-1111-1111-1111-111111111111"
    bob_id = "22222222-2222-2222-2222-222222222222"

    mock_supabase.table().select().eq().execute.return_value = MagicMock(
        data=[{
            "id": "exp-1",
            "itinerary_id": "shared-trip-123",
            "title": "Dinner",
            "amount": 5000.0,
            "is_public": True,
            "created_by": alice_id,
            "creator_name": "Alice",
            "payer_id": alice_id,
            "payer_name": "Alice"
        }]
    )

    res = test_client.get(
        "/api/expenses/shared-trip-123/expenses",
        headers=make_auth_headers(bob_id)
    )
    assert res.status_code == 200
    expenses = res.json()
    assert len(expenses) == 1
    # Bob MUST see masked IDs
    assert expenses[0]["created_by"] != alice_id
    assert expenses[0]["created_by"].startswith("mem_")
    assert expenses[0]["payer_id"] != alice_id
    assert expenses[0]["payer_id"].startswith("mem_")


def test_auth_sentinel_leave_trip_requires_jwt(test_client):
    """[VERIFICATION 8]: POST /leave without Bearer token is rejected with 401."""
    res = test_client.post(
        "/api/trips/trip-123/leave",
        headers={"X-User-ID": "22222222-2222-2222-2222-222222222222"}
    )
    assert res.status_code == 401
