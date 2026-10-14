"""
In-Memory Security Sentinel Sandbox Test: Standardized Test User Pool
Verifies role definitions, boundary defenses, stranger 403 access control, and zero live pollution.
"""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from datetime import datetime, timezone, timedelta

from main import app
from utils.deps import get_supabase, get_verified_user

# 5 Standardized Test Role Constants
TEST_USER_OWNER_ID = "00000000-0000-0000-0000-000000000001"
TEST_USER_EDITOR_ID = "00000000-0000-0000-0000-000000000002"
TEST_USER_VIEWER_ID = "00000000-0000-0000-0000-000000000003"
TEST_USER_CAPSULE_ID = "00000000-0000-0000-0000-000000000004"
TEST_USER_STRANGER_ID = "00000000-0000-0000-0000-000000000005"

# Real Core User UUID Whitelist (Must NEVER collide or be impersonated)
REAL_USER_RYAN_ID = "3f7abf22-b447-4281-b240-584549c79943"
REAL_USER_PIG_ID = "66234892-200e-4a3f-98b4-dbb58dc6e3fa"
REAL_USER_AIMEE_ID = "c14d3bc6-0540-44ec-98f8-ad649c9ee261"


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
            return mock_table

        elif name == "trip_capsule_entries":
            mock_select = MagicMock()
            mock_eq1 = MagicMock()
            mock_eq2 = MagicMock()
            mock_eq1.execute.return_value = MagicMock(data=capsule_entries)
            mock_eq2.execute.return_value = MagicMock(data=capsule_entries)
            mock_eq1.eq.return_value = mock_eq2
            mock_select.eq.return_value = mock_eq1
            mock_table.select.return_value = mock_select
            return mock_table

        return mock_table

    mock_sb.table.side_effect = table_side_effect
    return mock_sb


def test_sentinel_test_pool_constants_integrity():
    """Verify all 5 test UUIDs are distinct, valid format, and don't collide with real users."""
    test_ids = [
        TEST_USER_OWNER_ID,
        TEST_USER_EDITOR_ID,
        TEST_USER_VIEWER_ID,
        TEST_USER_CAPSULE_ID,
        TEST_USER_STRANGER_ID,
    ]
    # 1. All 5 are distinct
    assert len(set(test_ids)) == 5
    
    # 2. Strict separation from real user whitelist
    real_ids = {REAL_USER_RYAN_ID, REAL_USER_PIG_ID, REAL_USER_AIMEE_ID}
    for tid in test_ids:
        assert tid not in real_ids
        assert tid.startswith("00000000-0000-0000-0000-00000000000")


def test_sentinel_stranger_cannot_access_private_capsule():
    """Sentinel Proof: Stranger ID receives 403 Forbidden when trying to access non-member trip capsules."""
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")
    trip_data = {
        "id": "mock-trip-id",
        "user_id": TEST_USER_OWNER_ID,
        "members": [TEST_USER_EDITOR_ID],
        "start_date": "2026-03-10",
        "end_date": tomorrow,
        "is_capsule_unlocked": False
    }
    mock_sb = create_mock_supabase(trip_data, [])
    
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: TEST_USER_STRANGER_ID
    
    try:
        client = TestClient(app)
        response = client.get(
            "/api/trips/mock-trip-id/capsules",
            headers={"x-user-id": TEST_USER_STRANGER_ID}
        )
        assert response.status_code == 403
        assert "Not authorized" in response.json().get("detail", "")
    finally:
        app.dependency_overrides.clear()


def test_sentinel_owner_editor_access_granted():
    """Sentinel Proof: Valid Test Pool members (Owner/Editor) pass access control."""
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")
    trip_data = {
        "id": "mock-trip-id",
        "user_id": TEST_USER_OWNER_ID,
        "members": [TEST_USER_EDITOR_ID],
        "start_date": "2026-03-10",
        "end_date": tomorrow,
        "is_capsule_unlocked": False
    }
    mock_sb = create_mock_supabase(trip_data, [])
    
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: TEST_USER_OWNER_ID
    
    try:
        client = TestClient(app)
        response = client.get(
            "/api/trips/mock-trip-id/capsules",
            headers={"x-user-id": TEST_USER_OWNER_ID}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_members"] == 2
        assert data["is_unlocked"] is False
    finally:
        app.dependency_overrides.clear()
