"""
In-Memory Security Sentinel Sandbox Test: Standardized 6-Account Dual-Track Test User Pool
Verifies role definitions, RFC 4122 v4 Edge Shield compatibility, cross-stack backend/frontend
fixture alignment, boundary defenses, stranger 403 access control, and zero live pollution.
"""
import hashlib
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

# CI CWD Isolation: inject REPO_ROOT and BACKEND_DIR
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent
for _p in (str(REPO_ROOT), str(BACKEND_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from main import app  # noqa: E402
from tests.fixtures.test_users import (  # noqa: E402
    ALL_FIXED_TEST_USER_IDS,
    LEGACY_PINNED_TEST_USER_IDS,
    MODERN_UPGRADEABLE_TEST_USER_IDS,
    RFC4122_UUID_V4_RE,
    STATIC_ROLE_TEST_USER_IDS,
    SYNTHETIC_RYAN_TEST_ID,
    TEST_USERS,
    TEST_USER_CAPSULE_ID,
    TEST_USER_EDITOR_ID,
    TEST_USER_OWNER_ID,
    TEST_USER_RYAN_TEST_ID,
    TEST_USER_STRANGER_ID,
    TEST_USER_VIEWER_ID,
    resolve_ryan_test_user_id,
)
from utils.deps import get_supabase, get_verified_user  # noqa: E402

# Synthetic Core User Fixture Constants (Isolated Fixtures)
FIXTURE_CORE_USER_1 = "11111111-2222-3333-4444-555555555551"
FIXTURE_CORE_USER_2 = "11111111-2222-3333-4444-555555555552"
FIXTURE_CORE_USER_3 = "11111111-2222-3333-4444-555555555553"

# SHA-256 of production main user, personal QA account, and protected external legacy users
# (NEVER embed plaintext production UUIDs in public source, tests, or docs)
MAIN_USER_SHA256 = "1b9110f155d92fc3cee7dba9833489dd1e29c5ee57b54fafb7d7ed6b5e100d2d"
PERSONAL_QA_SHA256 = "df53a6abe0fa38b52ecf55f21d794ac5d47e6d370af2c6ac7d6f6d3c829e0c29"
FORBIDDEN_PUBLIC_UUID_SHA256S = frozenset({
    PERSONAL_QA_SHA256,
    # Protected external production Legacy user UUIDs (must NEVER appear in tracked public files)
    "9ab6e258e5b70848f5ceab1d236c86fb69455464e80049d181a03a04edfc1700",
    "98faa948601211050c9d5954044c094d054ced7fa0ad41b3a543f9139e0369c3",
    "0e0fbb95a29482adb987ff48fa9bf15043e3680b8a07d5d4aa5f93800001f0d7",
})


def _sha256(val: str) -> str:
    return hashlib.sha256(val.strip().lower().encode("utf-8")).hexdigest()


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

        elif name == "trip_members":
            member_ids = list(trip_data.get("members") or []) if trip_data else []
            owner_uid = (trip_data.get("created_by") or trip_data.get("user_id")) if trip_data else None
            if owner_uid and owner_uid not in member_ids:
                member_ids = [owner_uid] + member_ids
            all_rows = [{"user_id": uid} for uid in member_ids]
            filters = {}
            mock_select = MagicMock()

            def _eq(col, val):
                filters[col] = val
                return mock_select

            mock_select.eq.side_effect = _eq
            mock_select.execute.side_effect = lambda: MagicMock(
                data=[r for r in all_rows if filters.get("user_id") is None or r["user_id"] == filters["user_id"]]
            )
            mock_table.select.return_value = mock_select
            return mock_table

        return mock_table

    mock_sb.table.side_effect = table_side_effect
    return mock_sb


def test_sentinel_test_pool_constants_integrity():
    """Verify all 6 fixed test pool roles, dual-track metadata, RFC 4122 v4 compliance, and isolation."""
    # 1. Exact 6 roles present and distinct
    expected_roles = {"OWNER", "EDITOR", "VIEWER", "CAPSULE", "STRANGER", "RYAN_TEST"}
    assert set(TEST_USERS.keys()) == expected_roles
    assert len(STATIC_ROLE_TEST_USER_IDS) == 5
    assert len(ALL_FIXED_TEST_USER_IDS) == 6
    assert len(set(ALL_FIXED_TEST_USER_IDS)) == 6

    # 2. All 5 static synthetic role UUIDs follow reserved prefix and stay separate from core fixtures
    real_fixture_ids = {FIXTURE_CORE_USER_1, FIXTURE_CORE_USER_2, FIXTURE_CORE_USER_3}
    for tid in STATIC_ROLE_TEST_USER_IDS:
        assert tid not in real_fixture_ids
        assert tid.startswith("00000000-0000-0000-0000-00000000000")
        assert _sha256(tid) != MAIN_USER_SHA256

    # 3. RYAN_TEST (both default synthetic and resolved) satisfies strict RFC 4122 UUID v4 (Edge Shield D1 POI)
    assert SYNTHETIC_RYAN_TEST_ID == "00000000-0000-4000-8000-000000000006"
    assert RFC4122_UUID_V4_RE.match(SYNTHETIC_RYAN_TEST_ID)
    assert RFC4122_UUID_V4_RE.match(TEST_USER_RYAN_TEST_ID)
    assert _sha256(TEST_USER_RYAN_TEST_ID) != MAIN_USER_SHA256
    assert TEST_USER_RYAN_TEST_ID not in real_fixture_ids

    # 4. Dual-track auth_mode contract: ONLY VIEWER is legacy; all other 5 are modern
    legacy_roles = [role for role, meta in TEST_USERS.items() if meta["auth_mode"] == "legacy"]
    modern_roles = [role for role, meta in TEST_USERS.items() if meta["auth_mode"] == "modern"]
    assert legacy_roles == ["VIEWER"]
    assert set(modern_roles) == {"OWNER", "EDITOR", "CAPSULE", "STRANGER", "RYAN_TEST"}
    assert LEGACY_PINNED_TEST_USER_IDS == frozenset({TEST_USER_VIEWER_ID})
    assert set(MODERN_UPGRADEABLE_TEST_USER_IDS) == {
        TEST_USER_OWNER_ID,
        TEST_USER_EDITOR_ID,
        TEST_USER_CAPSULE_ID,
        TEST_USER_STRANGER_ID,
    }

    # 5. Edge Shield v4 compatibility flag matches exact UUID v4 reality
    for role, meta in TEST_USERS.items():
        if role == "RYAN_TEST":
            assert meta["edge_shield_v4_compatible"] is True
        else:
            assert meta["edge_shield_v4_compatible"] is False


def test_sentinel_ryan_test_env_injection_and_zero_plaintext_leak(monkeypatch):
    """Verify RYAN_TEST supports RFC 4122 v4 env injection and public fixture source embeds zero personal QA UUID."""
    monkeypatch.delenv("TEST_USER_RYAN_TEST_ID", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_TEST_USER_RYAN_TEST_ID", raising=False)
    assert resolve_ryan_test_user_id() == SYNTHETIC_RYAN_TEST_ID

    # Invalid non-v4 env value falls back safely to synthetic v4
    monkeypatch.setenv("TEST_USER_RYAN_TEST_ID", "00000000-0000-0000-0000-000000000099")
    assert resolve_ryan_test_user_id() == SYNTHETIC_RYAN_TEST_ID

    # Valid RFC 4122 v4 env value is accepted & lowercased
    valid_v4 = "12345678-1234-4123-8123-123456789ABC"
    monkeypatch.setenv("TEST_USER_RYAN_TEST_ID", valid_v4)
    assert resolve_ryan_test_user_id() == valid_v4.lower()

    # Whitespace-only primary env var falls through cleanly to NEXT_PUBLIC_TEST_USER_RYAN_TEST_ID
    monkeypatch.setenv("TEST_USER_RYAN_TEST_ID", "   ")
    monkeypatch.setenv("NEXT_PUBLIC_TEST_USER_RYAN_TEST_ID", valid_v4)
    assert resolve_ryan_test_user_id() == valid_v4.lower()

    # Cross-stack alignment & zero plaintext personal QA / external legacy user UUIDs across public tests, scripts, and docs
    frontend_src = (REPO_ROOT / "frontend" / "lib" / "constants" / "test-fixtures.ts").read_text(encoding="utf-8")

    uuid_re = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
    scan_roots = (
        REPO_ROOT / "backend" / "tests",
        REPO_ROOT / "frontend" / "__tests__",
        REPO_ROOT / "frontend" / "lib" / "constants",
        REPO_ROOT / "scripts",
        REPO_ROOT / ".agents" / "domains",
        REPO_ROOT / "docs" / "journals",
    )
    allowed_suffixes = {".py", ".ts", ".tsx", ".js", ".mjs", ".md"}
    for root in scan_roots:
        if not root.exists():
            continue
        for file_path in root.rglob("*"):
            if (
                not file_path.is_file()
                or file_path.suffix.lower() not in allowed_suffixes
                or "__pycache__" in file_path.parts
            ):
                continue
            src = file_path.read_text(encoding="utf-8", errors="ignore")
            rel_label = file_path.relative_to(REPO_ROOT).as_posix()
            for found_uuid in uuid_re.findall(src):
                assert _sha256(found_uuid) not in FORBIDDEN_PUBLIC_UUID_SHA256S, (
                    f"Plaintext protected production/QA UUID leaked into public file {rel_label}!"
                )

    for role in ("OWNER", "EDITOR", "VIEWER", "CAPSULE", "STRANGER", "RYAN_TEST"):
        assert role in frontend_src
    assert SYNTHETIC_RYAN_TEST_ID in frontend_src
    assert "authMode: 'legacy'" in frontend_src
    assert "edgeV4Compatible: true" in frontend_src


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
