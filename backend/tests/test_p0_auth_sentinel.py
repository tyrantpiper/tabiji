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


def test_auth_sentinel_day_data_requires_jwt(test_client, mock_supabase):
    """[VERIFICATION 9]: PATCH /day-data without Bearer token is rejected with 401."""
    alice_id = "11111111-1111-1111-1111-111111111111"
    attacker_id = "22222222-2222-2222-2222-222222222222"

    # 1. Unauthenticated / spoofed Header rejected
    res = test_client.patch(
        "/api/trips/trip-123/day-data",
        json={"day": 1, "notes": "test note"},
        headers={"X-User-ID": attacker_id}
    )
    assert res.status_code == 401

    # 2. Authenticated with Bearer token accepted
    mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=[{"user_id": alice_id}])
    mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[{"id": "trip-123", "content": {"daily_locations": {}}}])
    mock_supabase.table().update().eq().execute.return_value = MagicMock(data=[{"id": "trip-123"}])

    auth_res = test_client.patch(
        "/api/trips/trip-123/day-data",
        json={"day": 1, "notes": "test note"},
        headers=make_auth_headers(alice_id)
    )
    assert auth_res.status_code == 200


def test_auth_sentinel_ledger_share_requires_jwt(test_client, mock_supabase):
    """[VERIFICATION 10]: PATCH /ledger-share without Bearer token is rejected with 401."""
    alice_id = "11111111-1111-1111-1111-111111111111"
    attacker_id = "22222222-2222-2222-2222-222222222222"

    # 1. Unauthenticated / spoofed Header rejected
    res = test_client.patch(
        "/api/trips/trip-123/ledger-share",
        headers={"X-User-ID": attacker_id}
    )
    assert res.status_code == 401

    # 2. Authenticated with Bearer token accepted
    mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=[{"user_id": alice_id}])
    mock_supabase.table().update().eq().execute.return_value = MagicMock(data=[{"id": "trip-123"}])

    auth_res = test_client.patch(
        "/api/trips/trip-123/ledger-share",
        headers=make_auth_headers(alice_id)
    )
    assert auth_res.status_code == 200


def test_auth_sentinel_seed_sample_requires_jwt(test_client, mock_supabase):
    """[VERIFICATION 11]: POST /trips/seed-sample without Bearer token is rejected with 401."""
    alice_id = "11111111-1111-1111-1111-111111111111"
    attacker_id = "22222222-2222-2222-2222-222222222222"

    # 1. Unauthenticated / spoofed Header rejected
    res = test_client.post(
        "/api/trips/seed-sample",
        headers={"X-User-ID": attacker_id}
    )
    assert res.status_code == 401

    # 2. Authenticated with Bearer token accepted
    mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[])
    mock_supabase.table().insert().execute.return_value = MagicMock(data=[{"id": "sample-trip-1"}])

    auth_res = test_client.post(
        "/api/trips/seed-sample",
        headers=make_auth_headers(alice_id)
    )
    assert auth_res.status_code == 200


def test_auth_sentinel_gdpr_delete_requires_jwt_and_ownership(test_client, mock_supabase):
    """[VERIFICATION 12]: DELETE /api/user/{user_id}/data strictly requires Bearer JWT and ownership."""
    alice_id = "11111111-1111-1111-1111-111111111111"
    victim_id = "33333333-3333-3333-3333-333333333333"
    attacker_id = "22222222-2222-2222-2222-222222222222"

    # 1. Unauthenticated -> 401
    res = test_client.delete(f"/api/user/{victim_id}/data")
    assert res.status_code == 401

    # 2. Attacker trying to delete victim's data -> 403 Forbidden
    res_attacker = test_client.delete(
        f"/api/user/{victim_id}/data",
        headers=make_auth_headers(attacker_id)
    )
    assert res_attacker.status_code == 403

    # 3. Legitimate user deleting own data -> 200 OK
    mock_supabase.table().select().eq().execute.return_value = MagicMock(data=[])
    mock_supabase.table().delete().eq().execute.return_value = MagicMock(data=[])
    res_owner = test_client.delete(
        f"/api/user/{alice_id}/data",
        headers=make_auth_headers(alice_id)
    )
    assert res_owner.status_code == 200


def test_auth_sentinel_import_to_trip_requires_jwt_and_membership(test_client, mock_supabase):
    """[VERIFICATION 13]: POST /api/trips/import-to-trip strictly requires Bearer JWT and membership."""
    charlie_id = "44444444-4444-4444-4444-444444444444"
    attacker_id = "22222222-2222-2222-2222-222222222222"

    # 1. Unauthenticated -> 401
    res = test_client.post(
        "/api/trips/import-to-trip",
        json={"trip_id": "trip-123", "items": []}
    )
    assert res.status_code == 401

    # 2. Non-member/non-creator -> 403 Forbidden
    def table_router_forbidden(table_name):
        mock_t = MagicMock()
        if table_name == "itineraries":
            mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": "trip-123", "created_by": charlie_id, "content": {}}]
            )
        elif table_name == "trip_members":
            mock_t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        return mock_t

    mock_supabase.table.side_effect = table_router_forbidden
    res_forbidden = test_client.post(
        "/api/trips/import-to-trip",
        json={"trip_id": "trip-123", "items": []},
        headers=make_auth_headers(attacker_id)
    )
    assert res_forbidden.status_code == 403

    # 3. Trip owner -> 200 OK
    def table_router_owner(table_name):
        mock_t = MagicMock()
        if table_name == "itineraries":
            mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": "trip-123", "created_by": charlie_id, "content": {}}]
            )
            mock_t.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": "trip-123"}])
        elif table_name == "itinerary_items":
            mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            mock_t.insert.return_value.execute.return_value = MagicMock(data=[])
        return mock_t

    mock_supabase.table.side_effect = table_router_owner
    res_owner = test_client.post(
        "/api/trips/import-to-trip",
        json={"trip_id": "trip-123", "items": []},
        headers=make_auth_headers(charlie_id)
    )
    assert res_owner.status_code == 200


def test_auth_sentinel_save_itinerary_binds_verified_jwt_user(test_client, mock_supabase):
    """[VERIFICATION 14]: POST /api/trips/save-itinerary enforces verified user_id over body request.user_id."""
    alice_id = "11111111-1111-1111-1111-111111111111"
    victim_id = "33333333-3333-3333-3333-333333333333"
    recorded_inserts = []

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "itineraries":
            mock_res = MagicMock(count=0, data=[])
            mock_res.count = 0
            mock_t.select.return_value.eq.return_value.execute.return_value = mock_res
            def record_insert(payload):
                recorded_inserts.append(payload)
                return MagicMock(execute=lambda: MagicMock(data=[{"id": "new-trip-1"}]))
            mock_t.insert.side_effect = record_insert
        else:
            mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            mock_t.insert.return_value.execute.return_value = MagicMock(data=[])
            mock_t.upsert.return_value.execute.return_value = MagicMock(data=[])
        return mock_t

    mock_supabase.table.side_effect = table_router

    res = test_client.post(
        "/api/trips/save-itinerary",
        json={
            "title": "Tokyo Trip",
            "creator_name": "Alice",
            "user_id": victim_id,
            "items": []
        },
        headers=make_auth_headers(alice_id)
    )
    assert res.status_code == 200
    # Verify the created_by sent to Supabase was the verified JWT user_id
    assert any(c.get("created_by") == alice_id for c in recorded_inserts)


def test_auth_sentinel_clear_ai_review_requires_jwt_and_membership(test_client, mock_supabase):
    """[VERIFICATION 15]: DELETE /api/ai/trips/{trip_id}/days/{day}/ai-review requires JWT and membership."""
    owner_id = "55555555-5555-5555-5555-555555555555"
    stranger_id = "66666666-6666-6666-6666-666666666666"

    # 1. Unauthenticated -> 401
    res = test_client.delete("/api/ai/trips/trip-123/days/1/ai-review")
    assert res.status_code == 401

    # 2. Non-member -> 403
    mock_supabase.table().select().eq().execute.return_value = MagicMock(
        data=[{"id": "trip-123", "created_by": owner_id, "content": {}}]
    )
    mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=[])
    res_forbidden = test_client.delete(
        "/api/ai/trips/trip-123/days/1/ai-review",
        headers=make_auth_headers(stranger_id)
    )
    assert res_forbidden.status_code == 403

    # 3. Trip owner -> 200
    mock_supabase.table().update().eq().execute.return_value = MagicMock(data=[{"id": "trip-123"}])
    res_owner = test_client.delete(
        "/api/ai/trips/trip-123/days/1/ai-review",
        headers=make_auth_headers(owner_id)
    )
    assert res_owner.status_code == 200


@pytest.mark.asyncio
async def test_auth_sentinel_get_gemini_key_excludes_jwt():
    """[VERIFICATION 16]: get_gemini_key strictly ignores session JWTs in Authorization header."""
    from utils.deps import get_gemini_key
    from fastapi import HTTPException

    session_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHpunv_vRebL_bNmW_example"
    with pytest.raises(HTTPException) as exc_info:
        await get_gemini_key(x_gemini_api_key=None, auth_header=f"Bearer {session_jwt}")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_sentinel_get_gemini_key_handles_malformed_bearer():
    """[VERIFICATION 17]: get_gemini_key safely handles malformed Bearer headers without IndexError."""
    from utils.deps import get_gemini_key
    from fastapi import HTTPException

    for malformed in ["Bearer", "Bearer ", "Bearer    ", ""]:
        with pytest.raises(HTTPException) as exc_info:
            await get_gemini_key(x_gemini_api_key=None, auth_header=malformed)
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_sentinel_get_gemini_key_accepts_valid_gemini_key():
    """[VERIFICATION 18]: get_gemini_key accepts genuine Gemini API key (>=39 chars non-JWT)."""
    from utils.deps import get_gemini_key

    valid_key = "AIzaSy" + "A" * 33  # 39 chars
    # Via X-Gemini-API-Key
    res1 = await get_gemini_key(x_gemini_api_key=valid_key, auth_header=None)
    assert res1 == valid_key

    # Via Authorization fallback
    res2 = await get_gemini_key(x_gemini_api_key=None, auth_header=f"Bearer {valid_key}")
    assert res2 == valid_key


def test_delete_trip_before_authorization_prevented(test_client, mock_supabase):
    """[VERIFICATION 19]: Non-owner DELETE /api/trips/{trip_id} is rejected with 403 BEFORE any expenses are deleted."""
    owner_id = "11111111-1111-1111-1111-111111111111"
    attacker_id = "22222222-2222-2222-2222-222222222222"
    trip_id = "target-trip-123"

    mock_itineraries = MagicMock()
    mock_itineraries.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": trip_id, "created_by": owner_id}]
    )

    mock_expenses = MagicMock()
    
    def table_router(table_name):
        if table_name == "itineraries":
            return mock_itineraries
        if table_name == "expenses":
            return mock_expenses
        return MagicMock()

    mock_supabase.table.side_effect = table_router

    # Attacker attempts to delete victim's trip
    res = test_client.delete(
        f"/api/trips/{trip_id}",
        headers=make_auth_headers(attacker_id)
    )
    assert res.status_code == 403
    assert "只有行程創立者可以刪除行程" in res.json()["detail"]

    # CRITICAL: Verify expenses.delete() was NEVER called!
    assert not mock_expenses.delete.called


def test_public_trip_omits_join_secrets(test_client, mock_supabase):
    """[VERIFICATION 20]: GET /api/trips/share/{public_id} strictly omits share_code and reservation_code."""
    mock_itineraries = MagicMock()
    mock_items = MagicMock()

    mock_itineraries.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "trip-pub-123",
            "public_id": "pub_abcdef12",
            "title": "Public Tokyo Trip",
            "created_by": "secret-owner-uuid",
            "creator_name": "Host",
            "start_date": "2026-11-01",
            "share_code": "SECRET-JOIN-123",
            "content": {}
        }]
    )

    mock_items.select.return_value.eq.return_value.order.return_value.order.return_value.order.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "item-1",
            "place_name": "Tokyo Tower",
            "day_number": 1,
            "sort_order": 0,
            "time_slot": "10:00:00",
            "cost_amount": 1000,
            "notes": "Tokyo Tower observation deck",
            "category": "sightseeing",
            "location_lat": 35.6586,
            "location_lng": 139.7454,
            "reservation_code": "SECRET-RESERVATION-CODE-999",
            "is_private": False
        }]
    )

    def table_router(table_name):
        if table_name == "itineraries":
            return mock_itineraries
        if table_name == "itinerary_items":
            return mock_items
        return MagicMock()

    mock_supabase.table.side_effect = table_router

    res = test_client.get("/api/trips/share/pub_abcdef12")
    assert res.status_code == 200
    data = res.json()

    # Verify join/reservation secrets are stripped from public consumption
    assert "share_code" not in data or data.get("share_code") == ""
    activities = data["days"][0]["activities"]
    assert activities[0].get("reservation_code") is None


def test_trip_detail_bola_prevented(test_client, mock_supabase):
    """[VERIFICATION 21]: Non-member cannot access GET /api/trips/{trip_id} (BOLA 403)."""
    owner_id = "11111111-1111-1111-1111-111111111111"
    stranger_id = "33333333-3333-3333-3333-333333333333"
    trip_id = "confidential-trip"

    mock_supabase.table().select().eq().execute.side_effect = [
        # Trip
        MagicMock(data=[{
            "id": trip_id,
            "title": "Secret Trip",
            "created_by": owner_id,
            "public_id": "pub-123"
        }]),
        # Members (Stranger is NOT in the list)
        MagicMock(data=[
            {"id": "mem-row-1", "user_id": owner_id, "user_name": "Owner", "user_avatar": ""}
        ])
    ]

    res = test_client.get(
        f"/api/trips/{trip_id}",
        headers=make_auth_headers(stranger_id)
    )
    assert res.status_code == 403
    assert "您不是此行程的成員" in res.json()["detail"]


def test_latest_itinerary_scoped_to_user(test_client, mock_supabase):
    """[VERIFICATION 22]: GET /api/trips/itinerary/latest queries user_trips_view filtered by authenticated user_id."""
    user_id = "00000000-0000-0000-0000-000000000001"
    trip_id = "user-own-trip"

    view_mock = MagicMock()
    items_mock = MagicMock()

    def table_router(table_name):
        if table_name == "user_trips_view":
            return view_mock
        if table_name == "itinerary_items":
            return items_mock
        return MagicMock()

    mock_supabase.table.side_effect = table_router
    view_mock.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": trip_id, "title": "My Latest Trip", "created_by": user_id, "start_date": "2026-11-01"}]
    )
    items_mock.select.return_value.eq.return_value.order.return_value.order.return_value.order.return_value.execute.return_value = MagicMock(
        data=[]
    )

    res = test_client.get(
        "/api/trips/itinerary/latest",
        headers=make_auth_headers(user_id)
    )
    assert res.status_code == 200
    assert res.json()["id"] == trip_id
    # Assert query was filtered by user_id
    view_mock.select.return_value.eq.assert_called_with("user_id", user_id)


def test_expense_membership_bola_prevented(test_client, mock_supabase):
    """[VERIFICATION 23]: GET /api/expenses/{trip_id}/expenses rejects non-members with 403."""
    owner_id = "11111111-1111-1111-1111-111111111111"
    stranger_id = "33333333-3333-3333-3333-333333333333"
    trip_id = "trip-locked"

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "itineraries":
            mock_t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"created_by": owner_id}]
            )
        elif table_name == "trip_members":
            mock_t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )
        return mock_t

    mock_supabase.table.side_effect = table_router

    res = test_client.get(
        f"/api/expenses/{trip_id}/expenses",
        headers=make_auth_headers(stranger_id)
    )
    assert res.status_code == 403
    assert "您不是此行程的成員" in res.json()["detail"]


def test_kick_member_masked_lookup_and_delete(test_client, mock_supabase):
    """[VERIFICATION 24]: DELETE /api/trips/{trip_id}/members/{ref} matches masked member_id and deletes by primary key id."""
    from routers.trips import mask_member_id

    owner_id = "11111111-1111-1111-1111-111111111111"
    victim_user_id = "22222222-2222-2222-2222-222222222222"
    trip_id = "trip-shared-999"
    member_record_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    masked_ref = mask_member_id(victim_user_id, trip_id)

    mock_members = MagicMock()
    mock_itineraries = MagicMock()

    mock_itineraries.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": trip_id, "created_by": owner_id}]
    )
    mock_members.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[
            {"id": member_record_id, "user_id": victim_user_id, "user_name": "Bob"}
        ]
    )

    def table_router(table_name):
        if table_name == "itineraries":
            return mock_itineraries
        if table_name == "trip_members":
            return mock_members
        return MagicMock()

    mock_supabase.table.side_effect = table_router

    # Owner kicks member using the masked reference "mem_..."
    res = test_client.delete(
        f"/api/trips/{trip_id}/members/{masked_ref}",
        headers=make_auth_headers(owner_id)
    )
    assert res.status_code == 200
    assert res.json()["status"] == "success"

    # CRITICAL: Verify deletion targeted the native primary key UUID id!
    # Chain is: .delete().eq("itinerary_id", trip_id).eq("id", member_record_id)
    mock_members.delete.return_value.eq.return_value.eq.assert_called_with("id", member_record_id)


# ---------------------------------------------------------------------------
# Oracle Defense & Zero-Wire-Leak Integration Tests on Real App Router
# ---------------------------------------------------------------------------
def test_auth_session_server_side_expected_user_id_mismatch_blocks_jwt_and_prevents_oracle(test_client, mock_supabase):
    """
    [REAL ROUTER AUDIT]: Real POST /api/auth/session strictly asserts expected_user_id server-side.
    If expected_user_id does not match the recovery key's owner:
    1. Returns 401 Unauthorized.
    2. Response contains ZERO access_token / user_id (Zero Wire Leak).
    3. Response detail is UNIFORM_AUTH_ERROR (Zero Oracle Leak).
    """
    import hmac
    import hashlib
    from routers.auth import RECOVERY_PEPPER, UNIFORM_AUTH_ERROR

    victim_uid = "99999999-8888-7777-6666-555555555555"
    attacker_uid = "11111111-2222-3333-4444-555555555555"
    key_id = "abcd1234"
    secret_entropy = "0123456789abcdef0123456789abcdef"
    full_key = f"tbj_rec_{key_id}_{secret_entropy}"
    valid_hash = hmac.new(RECOVERY_PEPPER.encode(), secret_entropy.encode(), hashlib.sha256).hexdigest()

    # Mock user record returned from Supabase for this key_id
    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{
            "id": victim_uid,
            "recovery_key_id": key_id,
            "recovery_secret_hash": valid_hash,
            "credential_version": 1
        }]
    )

    # Attacker submits victim's key with attacker's expected_user_id
    res = test_client.post("/api/auth/session", json={
        "recovery_key": full_key,
        "expected_user_id": attacker_uid
    })

    # Assert 1: HTTP 401
    assert res.status_code == 401
    res_json = res.json()
    # Assert 2: Uniform error message (Oracle defense)
    assert res_json["detail"] == UNIFORM_AUTH_ERROR
    # Assert 3: Wire-level token zero leak
    assert "access_token" not in res_json
    assert "user_id" not in res_json


def test_auth_session_server_side_expected_user_id_match_issues_jwt(test_client, mock_supabase):
    """
    [REAL ROUTER AUDIT]: When expected_user_id matches recovery key owner, JWT is safely issued.
    """
    import hmac
    import hashlib
    from routers.auth import RECOVERY_PEPPER

    owner_uid = "88888888-7777-6666-5555-444444444444"
    key_id = "beef5678"
    secret_entropy = "11223344556677889900aabbccddeeff"
    full_key = f"tbj_rec_{key_id}_{secret_entropy}"
    valid_hash = hmac.new(RECOVERY_PEPPER.encode(), secret_entropy.encode(), hashlib.sha256).hexdigest()

    mock_supabase.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{
            "id": owner_uid,
            "recovery_key_id": key_id,
            "recovery_secret_hash": valid_hash,
            "credential_version": 2
        }]
    )

    res = test_client.post("/api/auth/session", json={
        "recovery_key": full_key,
        "expected_user_id": owner_uid
    })

    assert res.status_code == 200
    res_json = res.json()
    assert res_json["user_id"] == owner_uid
    assert "access_token" in res_json
    assert res_json["access_token"] is not None


def test_auth_session_legacy_uuid_expected_user_id_guard(test_client, mock_supabase):
    """
    [REAL ROUTER AUDIT]: Legacy UUID path also strictly blocks expected_user_id mismatch.
    """
    from routers.auth import UNIFORM_AUTH_ERROR

    victim_legacy_uuid = "22222222-3333-4444-5555-666666666666"
    attacker_uid = "77777777-8888-9999-0000-111111111111"

    # Attacker tries to exchange victim's legacy UUID while passing attacker_uid
    res = test_client.post("/api/auth/session", json={
        "recovery_key": victim_legacy_uuid,
        "expected_user_id": attacker_uid
    })

    assert res.status_code == 401
    assert res.json()["detail"] == UNIFORM_AUTH_ERROR
    assert "access_token" not in res.json()





