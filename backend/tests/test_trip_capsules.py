"""
Test Suite for Trip Time Capsule Endpoints
Tests:
- GET /api/trips/{trip_id}/capsules during trip (sealed, BOLA redacted)
- GET /api/trips/{trip_id}/capsules after trip (unsealed, revealed)
- Non-member 403 isolation
- POST /api/trips/{trip_id}/capsules (validation, size, freeze on unlock)
"""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta

from main import app
from utils.deps import get_supabase, get_verified_user

client = TestClient(app)

# Helper mock setup
def create_mock_supabase(trip_data: dict, capsule_entries: list):
    mock_sb = MagicMock()
    
    def table_side_effect(name: str):
        mock_table = MagicMock()
        if name in ("trips", "itineraries"):
            mock_select = MagicMock()
            mock_eq = MagicMock()
            mock_eq.execute.return_value = MagicMock(data=[trip_data] if trip_data else [])
            mock_select.eq.return_value = mock_eq
            mock_table.select.return_value = mock_select
            
            # Update mock
            mock_update = MagicMock()
            mock_update_eq = MagicMock()
            mock_update_eq.execute.return_value = MagicMock(data=[trip_data])
            mock_update.eq.return_value = mock_update_eq
            mock_table.update.return_value = mock_update
            return mock_table

        elif name == "trip_capsule_entries":
            mock_select = MagicMock()
            mock_eq1 = MagicMock()
            mock_eq2 = MagicMock()
            
            # Chainable eq calls
            mock_eq1.execute.return_value = MagicMock(data=capsule_entries)
            mock_eq2.execute.return_value = MagicMock(data=capsule_entries)
            mock_eq1.eq.return_value = mock_eq2
            mock_select.eq.return_value = mock_eq1
            mock_table.select.return_value = mock_select

            # Upsert mock
            mock_upsert = MagicMock()
            mock_upsert_exec = MagicMock()
            def upsert_execute():
                upsert_data = mock_table.upsert.call_args[0][0]
                return MagicMock(data=[{**upsert_data, "id": "saved-capsule-1"}])
            mock_upsert_exec.execute.side_effect = upsert_execute
            mock_table.upsert.return_value = mock_upsert_exec
            return mock_table

        return mock_table

    mock_sb.table.side_effect = table_side_effect
    return mock_sb


@pytest.fixture
def mock_trip_in_progress():
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")
    return {
        "id": "trip-tokyo-1",
        "user_id": "alice",
        "members": ["bob"],
        "start_date": "2026-10-10",
        "end_date": tomorrow,
        "is_capsule_unlocked": False
    }


@pytest.fixture
def mock_trip_completed():
    yesterday = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")
    return {
        "id": "trip-tokyo-ended",
        "user_id": "alice",
        "members": ["bob"],
        "start_date": "2026-10-01",
        "end_date": yesterday,
        "is_capsule_unlocked": True
    }


def test_get_capsules_during_trip_redacts_for_collaborator(mock_trip_in_progress):
    """During trip, collaborator Bob can see Alice has submitted, but content/photo is null."""
    entries = [
        {
            "id": "cap-alice-1",
            "trip_id": "trip-tokyo-1",
            "day_number": 1,
            "author_id": "alice",
            "author_name": "Alice",
            "mood_emoji": "🤫",
            "content": "Secret note for Bob",
            "photo_url": "https://res.cloudinary.com/dnpcnwrcu/image/upload/sample.webp",
            "created_at": "2026-10-10T10:00:00Z",
            "updated_at": "2026-10-10T10:00:00Z"
        }
    ]
    mock_sb = create_mock_supabase(mock_trip_in_progress, entries)

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: "bob" # Bob viewing

    try:
        response = client.get("/api/trips/trip-tokyo-1/capsules")
        assert response.status_code == 200
        data = response.json()

        assert data["is_unlocked"] is False
        assert data["total_members"] == 2
        assert data["submitted_members_count"] == 1
        assert data["has_current_user_submitted"] is False

        # Alice's entry must be redacted
        assert len(data["revealed_entries"]) == 1
        alice_entry = data["revealed_entries"][0]
        assert alice_entry["content"] is None
        assert alice_entry["photo_url"] is None
        assert alice_entry["mood_emoji"] is None
        assert alice_entry["is_sealed"] is True

        # Bob has no own entry
        assert len(data["my_entries"]) == 0
    finally:
        app.dependency_overrides.clear()


def test_get_capsules_during_trip_visible_for_author(mock_trip_in_progress):
    """During trip, author Alice can see her own content and photo."""
    entries = [
        {
            "id": "cap-alice-1",
            "trip_id": "trip-tokyo-1",
            "day_number": 1,
            "author_id": "alice",
            "author_name": "Alice",
            "mood_emoji": "🥳",
            "content": "Alice's own thoughts",
            "photo_url": "https://res.cloudinary.com/dnpcnwrcu/image/upload/sample.webp",
            "created_at": "2026-10-10T10:00:00Z",
            "updated_at": "2026-10-10T10:00:00Z"
        }
    ]
    mock_sb = create_mock_supabase(mock_trip_in_progress, entries)

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: "alice" # Alice viewing

    try:
        response = client.get("/api/trips/trip-tokyo-1/capsules")
        assert response.status_code == 200
        data = response.json()

        assert data["is_unlocked"] is False
        assert data["has_current_user_submitted"] is True
        assert len(data["my_entries"]) == 1
        my_cap = data["my_entries"][0]
        assert my_cap["content"] == "Alice's own thoughts"
        assert my_cap["photo_url"] == "https://res.cloudinary.com/dnpcnwrcu/image/upload/sample.webp"
        assert my_cap["mood_emoji"] == "🥳"
    finally:
        app.dependency_overrides.clear()


def test_get_capsules_after_trip_reveals_all(mock_trip_completed):
    """After trip ended, both Alice and Bob see all entries fully unsealed."""
    entries = [
        {
            "id": "cap-alice-1",
            "trip_id": "trip-tokyo-ended",
            "day_number": 1,
            "author_id": "alice",
            "author_name": "Alice",
            "mood_emoji": "🥳",
            "content": "Surprise revealed!",
            "photo_url": "https://res.cloudinary.com/dnpcnwrcu/image/upload/sample.webp",
            "created_at": "2026-10-01T10:00:00Z",
            "updated_at": "2026-10-01T10:00:00Z"
        }
    ]
    mock_sb = create_mock_supabase(mock_trip_completed, entries)

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: "bob" # Bob viewing after unlock

    try:
        response = client.get("/api/trips/trip-tokyo-ended/capsules")
        assert response.status_code == 200
        data = response.json()

        assert data["is_unlocked"] is True
        assert len(data["revealed_entries"]) == 1
        revealed = data["revealed_entries"][0]
        assert revealed["content"] == "Surprise revealed!"
        assert revealed["photo_url"] == "https://res.cloudinary.com/dnpcnwrcu/image/upload/sample.webp"
        assert revealed["is_sealed"] is False
    finally:
        app.dependency_overrides.clear()


def test_non_member_access_forbidden(mock_trip_in_progress):
    """Eve is not a trip member and is rejected with 403."""
    mock_sb = create_mock_supabase(mock_trip_in_progress, [])

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: "eve" # Outsider

    try:
        response = client.get("/api/trips/trip-tokyo-1/capsules")
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_submit_capsule_validation_and_freeze(mock_trip_in_progress, mock_trip_completed):
    """Test validation constraints and freezing modifications once unlocked."""
    mock_sb_in_prog = create_mock_supabase(mock_trip_in_progress, [])
    app.dependency_overrides[get_supabase] = lambda: mock_sb_in_prog
    app.dependency_overrides[get_verified_user] = lambda: "alice"

    try:
        # 1. Valid submission
        valid_payload = {
            "day_number": 1,
            "mood_emoji": "✨",
            "content": "Today was amazing!",
            "photo_url": "https://res.cloudinary.com/dnpcnwrcu/image/upload/tokyo.webp"
        }
        res = client.post("/api/trips/trip-tokyo-1/capsules", json=valid_payload)
        assert res.status_code == 200
        assert res.json()["content"] == "Today was amazing!"

        # 2. Reject non-Cloudinary image
        bad_photo = {
            "day_number": 1,
            "mood_emoji": "✨",
            "content": "Test",
            "photo_url": "https://evil.com/exploit.jpg"
        }
        res_bad = client.post("/api/trips/trip-tokyo-1/capsules", json=bad_photo)
        assert res_bad.status_code == 422

        # 3. Reject over 500 characters
        long_content = {
            "day_number": 1,
            "mood_emoji": "✨",
            "content": "A" * 501,
            "photo_url": None
        }
        res_long = client.post("/api/trips/trip-tokyo-1/capsules", json=long_content)
        assert res_long.status_code == 422

        # 4. Freeze modification when trip is completed
        mock_sb_ended = create_mock_supabase(mock_trip_completed, [])
        app.dependency_overrides[get_supabase] = lambda: mock_sb_ended
        res_frozen = client.post("/api/trips/trip-tokyo-ended/capsules", json=valid_payload)
        assert res_frozen.status_code == 403
        assert "frozen" in res_frozen.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


def test_sample_trip_capsule_isolation():
    """Verify sample/demo trip (created_by=SYSTEM) isolates capsules and rejects collaborative submission."""
    sample_trip = {
        "id": "trip-sample-taipei",
        "created_by": "SYSTEM",
        "title": "3 Day Taipei Explorer ✨",
        "content": {"is_sample": True},
        "members": ["user-explorer"],
        "start_date": "2026-03-10",
        "end_date": "2026-03-12"
    }
    mock_sb = create_mock_supabase(sample_trip, [])
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: "user-explorer"

    try:
        # 1. GET returns isolated demo empty state without locking into unlocked state
        get_res = client.get("/api/trips/trip-sample-taipei/capsules")
        assert get_res.status_code == 200
        data = get_res.json()
        assert data["is_unlocked"] is False
        assert data["total_members"] == 1
        assert len(data["revealed_entries"]) == 0
        assert len(data["my_entries"]) == 0

        # 2. POST rejects submission with 400 Bad Request
        payload = {
            "day_number": 1,
            "mood_emoji": "✨",
            "content": "Trying to submit to sample trip",
            "photo_url": None
        }
        post_res = client.post("/api/trips/trip-sample-taipei/capsules", json=payload)
        assert post_res.status_code == 400
        assert "sample" in post_res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()

