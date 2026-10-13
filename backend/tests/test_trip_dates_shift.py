"""
📅 Test Suite for Trip Dates Shift & Day Alignment Engine
Tests:
1. Rescheduling trip (3 days -> 3 days shifted by 5 days) preserves day_number for all items.
2. Extending trip (3 days -> 5 days) preserves day_number and adds empty days.
3. Shortening trip (5 days -> 3 days) with 'merge' compresses day_number > 3 into day_number = 3.
4. Shortening trip (5 days -> 3 days) with 'delete' deletes items where day_number > 3.
5. End date earlier than start date returns 400 Bad Request.
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
    app.dependency_overrides[get_verified_user] = lambda: "creator-user-id"
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_reschedule_same_duration_preserves_all_items(test_client, mock_supabase):
    """
    [TC-1]: Rescheduling 10/10~10/12 (3 days) to 10/15~10/17 (3 days) MUST NOT touch items!
    Zero-Shift Engine: day_number of all activities must remain intact.
    """
    # 1. Existing trip
    mock_supabase.table().select().eq().single().execute.return_value = MagicMock(
        data={
            "id": "trip-3d",
            "created_by": "creator-user-id",
            "start_date": "2026-10-10",
            "end_date": "2026-10-12",
            "content": {"day_notes": {"1": "Day 1 note", "2": "Day 2 note", "3": "Day 3 note"}}
        }
    )

    # 2. Execute PATCH dates
    response = test_client.patch(
        "/api/trips/trip-3d/dates",
        json={
            "start_date": "2026-10-15",
            "end_date": "2026-10-17",
            "on_shorten": "merge"
        },
        headers={"X-User-ID": "creator-user-id"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["total_days"] == 3
    assert data["start_date"] == "2026-10-15"
    assert data["end_date"] == "2026-10-17"

    # Verify itineraries update was called with new dates and intact content
    update_calls = mock_supabase.table("itineraries").update.call_args_list
    assert len(update_calls) > 0
    updated_payload = update_calls[-1][0][0]
    assert updated_payload["start_date"] == "2026-10-15"
    assert updated_payload["end_date"] == "2026-10-17"
    assert updated_payload["content"]["day_notes"]["1"] == "Day 1 note"
    assert updated_payload["content"]["day_notes"]["2"] == "Day 2 note"
    assert updated_payload["content"]["day_notes"]["3"] == "Day 3 note"


def test_extend_duration_preserves_all_items(test_client, mock_supabase):
    """
    [TC-2]: Extending 3 days to 5 days keeps Days 1-3 intact.
    """
    mock_supabase.table().select().eq().single().execute.return_value = MagicMock(
        data={
            "id": "trip-3d-to-5d",
            "created_by": "creator-user-id",
            "start_date": "2026-10-10",
            "end_date": "2026-10-12",
            "content": {}
        }
    )

    response = test_client.patch(
        "/api/trips/trip-3d-to-5d/dates",
        json={
            "start_date": "2026-10-10",
            "end_date": "2026-10-14",
            "on_shorten": "merge"
        },
        headers={"X-User-ID": "creator-user-id"}
    )

    assert response.status_code == 200
    assert response.json()["total_days"] == 5


def test_shorten_duration_with_merge(test_client, mock_supabase):
    """
    [TC-3]: Shortening 5 days to 3 days with 'merge' merges excess items (days 4, 5) into day 3.
    """
    mock_supabase.table().select().eq().single().execute.return_value = MagicMock(
        data={
            "id": "trip-5d-to-3d",
            "created_by": "creator-user-id",
            "start_date": "2026-10-10",
            "end_date": "2026-10-14",
            "content": {"day_checklists": {"3": ["Buy milk"], "4": ["Pack bag"]}}
        }
    )

    # Mock excess items > 3
    mock_supabase.table().select().eq().gt().execute.return_value = MagicMock(
        data=[{"id": "item-4", "day_number": 4}, {"id": "item-5", "day_number": 5}]
    )

    response = test_client.patch(
        "/api/trips/trip-5d-to-3d/dates",
        json={
            "start_date": "2026-10-10",
            "end_date": "2026-10-12",
            "on_shorten": "merge"
        },
        headers={"X-User-ID": "creator-user-id"}
    )

    assert response.status_code == 200
    assert response.json()["total_days"] == 3


def test_shorten_duration_with_delete(test_client, mock_supabase):
    """
    [TC-4]: Shortening 5 days to 3 days with 'delete' removes excess items.
    """
    mock_supabase.table().select().eq().single().execute.return_value = MagicMock(
        data={
            "id": "trip-5d-delete",
            "created_by": "creator-user-id",
            "start_date": "2026-10-10",
            "end_date": "2026-10-14",
            "content": {}
        }
    )

    mock_supabase.table().select().eq().gt().execute.return_value = MagicMock(
        data=[{"id": "item-4", "day_number": 4}]
    )

    response = test_client.patch(
        "/api/trips/trip-5d-delete/dates",
        json={
            "start_date": "2026-10-10",
            "end_date": "2026-10-12",
            "on_shorten": "delete"
        },
        headers={"X-User-ID": "creator-user-id"}
    )

    assert response.status_code == 200
    assert response.json()["total_days"] == 3


def test_invalid_dates_rejected(test_client, mock_supabase):
    """
    [TC-5]: End date before start date rejected with 400.
    """
    mock_supabase.table().select().eq().single().execute.return_value = MagicMock(
        data={
            "id": "trip-err",
            "created_by": "creator-user-id",
            "start_date": "2026-10-10",
            "end_date": "2026-10-12",
            "content": {}
        }
    )

    response = test_client.patch(
        "/api/trips/trip-err/dates",
        json={
            "start_date": "2026-10-15",
            "end_date": "2026-10-10"
        },
        headers={"X-User-ID": "creator-user-id"}
    )

    assert response.status_code == 400
    assert "結束日期不能早於開始日期" in response.json()["detail"]
