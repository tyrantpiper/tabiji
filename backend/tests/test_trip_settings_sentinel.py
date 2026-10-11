"""
🛡️ In-Memory Security Sentinel Test Suite for Trip Settings
Verifies IDOR and privilege escalation protections for:
- POST /{trip_id}/leave (Owner cannot leave, member can leave)
- DELETE /{trip_id} (Only creator can delete, non-creator gets 403)
- PATCH /{trip_id}/title (Only member can update title)
- PATCH /{trip_id}/cover (Only member can update cover, null is allowed)
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from main import app
from utils.deps import get_supabase, get_verified_user


@pytest.fixture
def mock_supabase():
    client = MagicMock()
    return client


@pytest.fixture
def test_client(mock_supabase):
    app.dependency_overrides[get_supabase] = lambda: mock_supabase
    app.dependency_overrides[get_verified_user] = lambda: "attacker-user-id"
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_sentinel_delete_trip_idor_non_creator_blocked(test_client, mock_supabase):
    """
    [TC-1 IDOR Check]: Non-creator user cannot delete trip (403 Forbidden).
    """
    # Trip is created by "creator-user-id", caller is "attacker-user-id"
    mock_supabase.table().select().eq().execute.return_value = MagicMock(
        data=[{"id": "trip-123", "created_by": "creator-user-id"}]
    )

    response = test_client.delete(
        "/api/trips/trip-123",
        headers={"X-User-ID": "attacker-user-id"}
    )
    assert response.status_code == 403
    assert "只有行程創立者可以刪除行程" in response.json()["detail"]


def test_sentinel_owner_cannot_leave_must_delete(test_client, mock_supabase):
    """
    [TC-2 State Pollution Check]: Owner cannot leave trip via /leave (400 Bad Request).
    """
    app.dependency_overrides[get_verified_user] = lambda: "creator-user-id"
    
    mock_supabase.table().select().eq().single().execute.return_value = MagicMock(
        data={"id": "trip-123", "created_by": "creator-user-id"}
    )

    response = test_client.post(
        "/api/trips/trip-123/leave",
        headers={"X-User-ID": "creator-user-id"}
    )
    assert response.status_code == 400
    assert "Owner cannot leave trip" in response.json()["detail"]


def test_sentinel_update_title_non_member_blocked(test_client, mock_supabase):
    """
    [TC-3 IDOR Check]: Non-member cannot update trip title (403 Forbidden).
    """
    # Member check returns empty
    mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(data=[])

    response = test_client.patch(
        "/api/trips/trip-123/title",
        headers={"X-User-ID": "attacker-user-id"},
        json={"title": "Hacked Title"}
    )
    assert response.status_code == 403
    assert "您沒有權限修改此行程標題" in response.json()["detail"]


def test_sentinel_update_cover_clean_null_allowed(test_client, mock_supabase):
    """
    [TC-4 Cover Reset]: Member can set cover to null or empty string to reset cover.
    """
    app.dependency_overrides[get_verified_user] = lambda: "member-user-id"
    
    # Member check succeeds
    mock_supabase.table().select().eq().eq().execute.return_value = MagicMock(
        data=[{"user_id": "member-user-id"}]
    )
    mock_supabase.table().update().eq().execute.return_value = MagicMock(data=[{"id": "trip-123"}])

    response = test_client.patch(
        "/api/trips/trip-123/cover",
        headers={"X-User-ID": "member-user-id"},
        json={"cover_image": None}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["cover_image"] is None
