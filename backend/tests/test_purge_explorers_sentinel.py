"""
Sentinel Test Suite for Safe Explorer Sample Trip Purge
-------------------------------------------------------
Verifies that the purge script's candidate filtering logic is mathematically sound,
strictly prevents accidental deletion of real users, and upholds all invariants.
"""

import pytest
from unittest.mock import MagicMock
from scripts.purge_sample_explorers_safely import (
    inspect_and_filter_candidates,
    PROTECTED_NAMES,
    SAMPLE_TRIP_TITLE,
    CHUNK_SIZE,
)


def test_chunk_size_is_strictly_safe():
    """Verify CHUNK_SIZE does not exceed PostgREST URI limits."""
    assert CHUNK_SIZE <= 50, f"CHUNK_SIZE {CHUNK_SIZE} is too large for PostgREST URI limits"


def test_protected_names_contain_real_users():
    """Verify protected whitelist contains critical developer and production names."""
    for name in ["ryan", "mimi", "chungshi", "抑制劑"]:
        assert name in PROTECTED_NAMES, f"Critical name {name} missing from PROTECTED_NAMES whitelist"


def test_filter_disqualifies_protected_name():
    """Verify users whose name is in PROTECTED_NAMES are never qualified."""
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value.data = []

    explorers = [
        {"id": "user-ryan", "name": "Ryan"},
        {"id": "user-mimi", "name": "Mimi"},
        {"id": "user-clean", "name": "Explorer"},
    ]

    result = inspect_and_filter_candidates(mock_supabase, explorers)
    qualified_ids = [q["user"]["id"] for q in result["qualified"]]
    disqualified_ids = [d["user"]["id"] for d in result["disqualified"]]

    assert "user-ryan" in disqualified_ids
    assert "user-mimi" in disqualified_ids
    assert "user-clean" in qualified_ids


def test_filter_disqualifies_users_with_expenses():
    """Verify users whose sample trip has associated expenses are rejected from purge."""
    mock_supabase = MagicMock()
    
    # Mock memberships
    mock_memberships = [
        {"id": "m1", "user_id": "u-clean", "itinerary_id": "itin-clean", "user_name": "Explorer"},
        {"id": "m2", "user_id": "u-spent", "itinerary_id": "itin-spent", "user_name": "Explorer"},
    ]
    # Mock itineraries
    mock_itineraries = [
        {"id": "itin-clean", "title": SAMPLE_TRIP_TITLE, "created_by": "SYSTEM"},
        {"id": "itin-spent", "title": SAMPLE_TRIP_TITLE, "created_by": "SYSTEM"},
    ]
    # Mock expenses: itin-spent has an expense!
    mock_expenses = [
        {"id": "exp-1", "itinerary_id": "itin-spent"}
    ]

    def mock_table(table_name):
        mock_builder = MagicMock()
        if table_name == "trip_members":
            mock_builder.select.return_value.in_.return_value.execute.return_value.data = mock_memberships
        elif table_name == "itineraries":
            mock_builder.select.return_value.in_.return_value.execute.return_value.data = mock_itineraries
        elif table_name == "expenses":
            mock_builder.select.return_value.in_.return_value.execute.return_value.data = mock_expenses
        elif table_name == "trip_capsule_entries":
            mock_builder.select.return_value.in_.return_value.execute.return_value.data = []
        return mock_builder

    mock_supabase.table.side_effect = mock_table

    explorers = [
        {"id": "u-clean", "name": "Explorer"},
        {"id": "u-spent", "name": "Explorer"},
    ]

    result = inspect_and_filter_candidates(mock_supabase, explorers)
    qualified_ids = [q["user"]["id"] for q in result["qualified"]]
    disqualified_ids = [d["user"]["id"] for d in result["disqualified"]]

    assert "u-clean" in qualified_ids
    assert "u-spent" in disqualified_ids
    assert any("has associated expenses" in d["reason"] for d in result["disqualified"])


def test_filter_disqualifies_users_with_multiple_trips():
    """Verify users who created additional trips beyond sample are protected."""
    mock_supabase = MagicMock()

    mock_memberships = [
        {"id": "m1", "user_id": "u-multi", "itinerary_id": "itin-1", "user_name": "Explorer"},
        {"id": "m2", "user_id": "u-multi", "itinerary_id": "itin-2", "user_name": "Explorer"},
    ]
    mock_itineraries = [
        {"id": "itin-1", "title": SAMPLE_TRIP_TITLE, "created_by": "SYSTEM"},
        {"id": "itin-2", "title": "Tokyo Trip", "created_by": "USER"},
    ]

    def mock_table(table_name):
        mock_builder = MagicMock()
        if table_name == "trip_members":
            mock_builder.select.return_value.in_.return_value.execute.return_value.data = mock_memberships
        elif table_name == "itineraries":
            mock_builder.select.return_value.in_.return_value.execute.return_value.data = mock_itineraries
        elif table_name in ("expenses", "trip_capsule_entries"):
            mock_builder.select.return_value.in_.return_value.execute.return_value.data = []
        return mock_builder

    mock_supabase.table.side_effect = mock_table

    explorers = [{"id": "u-multi", "name": "Explorer"}]
    result = inspect_and_filter_candidates(mock_supabase, explorers)

    disqualified_ids = [d["user"]["id"] for d in result["disqualified"]]
    assert "u-multi" in disqualified_ids
    assert any("multiple" in d["reason"] for d in result["disqualified"])
