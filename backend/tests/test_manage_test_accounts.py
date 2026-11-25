# -*- coding: utf-8 -*-
"""
In-Memory Security Sentinel & Unit Test Suite: scripts/manage_test_accounts.py
------------------------------------------------------------------------------
Strictly follows CI CWD Isolation (dynamic REPO_ROOT injection) and In-Memory Mocking
(zero live Supabase or external HTTP mutations). Covers Mantis Block G benign controls
and every safety guardrail:
1. Full-table pagination (> 1,000 rows) preventing PostgREST max_rows truncation.
2. Strict Dry-Run default for --purge and --upgrade-pool (zero deletes / zero POSTs).
3. SHA-256 hard-protected whitelist (main account + 6-account test pool) & real-user safety.
4. Guardrail conflict resolutions (a) has_external_expenses vs TEST-SUCCESS and
   (b) exempt [Test] Editor membership on TEST-FULL-FLOW + fk_itineraries_user CASCADE check.
5. Empty SYSTEM sample trip strict created_by == 'SYSTEM' (protecting NULL) + 1h cooldown.
6. FK delete order, uuid_only() Postgres 22P02 defense, and 25-row / 0.3s trigger throttling.
7. Redacted physical JSON backup path containment & recursive stripping of all 5 secret keys.
8. Explicit Cloudinary destroy verification (HTTP 200 & ok/not found; rejects 401 loudly).
9. --upgrade-pool preflight, VIEWER/RYAN_TEST hard-lock, /api/health/deep warmup, timeout=30.0,
   strict response checks, bare `git check-ignore -q`, atomic merge & finally cleanup, and
   PARTIAL_UPGRADE_DESYNC timeout re-probe.
"""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import httpx
import pytest

# CI CWD Isolation: works identically from repo root OR `cd backend && pytest`
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = Path(__file__).resolve().parent.parent
for _p in (str(REPO_ROOT), str(BACKEND_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import scripts.manage_test_accounts as mta  # noqa: E402
from tests.fixtures.test_users import (  # noqa: E402
    SYNTHETIC_RYAN_TEST_ID,
    TEST_USER_CAPSULE_ID,
    TEST_USER_EDITOR_ID,
    TEST_USER_OWNER_ID,
    TEST_USER_STRANGER_ID,
    TEST_USER_VIEWER_ID,
)


def _empty_snapshot(**overrides: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    base: Dict[str, List[Dict[str, Any]]] = {
        "users": [],
        "itineraries": [],
        "trip_members": [],
        "expenses": [],
        "trip_capsule_entries": [],
        "user_preferences": [],
        "notifications": [],
        "push_subscriptions": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. Pagination (> 1,000 rows)
# ---------------------------------------------------------------------------
def test_fetch_all_rows_paginates_beyond_postgrest_1000_limit():
    """fetch_all_rows must loop range() in 1,000-row pages until a short page is returned."""
    total_rows = [{"id": f"row-{i:04d}"} for i in range(2350)]
    seen_ranges: List[tuple[int, int]] = []

    mock_sb = MagicMock()

    def table_side_effect(name: str):
        tbl = MagicMock()

        def select_side_effect(cols: str):
            sel = MagicMock()

            def order_side_effect(col: str):
                ord_q = MagicMock()

                def range_side_effect(start: int, end: int):
                    seen_ranges.append((start, end))
                    sliced = total_rows[start : end + 1]
                    return MagicMock(execute=lambda: MagicMock(data=sliced))

                ord_q.range.side_effect = range_side_effect
                return ord_q

            sel.order.side_effect = order_side_effect
            return sel

        tbl.select.side_effect = select_side_effect
        return tbl

    mock_sb.table.side_effect = table_side_effect

    rows = mta.fetch_all_rows(mock_sb, "notifications", "id, user_id")
    assert len(rows) == 2350
    assert seen_ranges == [(0, 999), (1000, 1999), (2000, 2999)]


# ---------------------------------------------------------------------------
# 2. Strict Dry-Run Defaults
# ---------------------------------------------------------------------------
def test_purge_dry_run_performs_zero_deletes_and_zero_http_calls(monkeypatch):
    """Default --purge (without --execute) must execute zero .delete() calls and zero Cloudinary calls."""
    target_uid = mta.APPROVED_PURGE_USER_IDS[0]
    snapshot = _empty_snapshot(
        users=[{"id": target_uid, "name": "Test", "avatar_url": "https://res.cloudinary.com/demo/image/upload/v1/a.png"}],
    )

    mock_sb = MagicMock()
    mock_sb.table.return_value.delete.side_effect = AssertionError("Dry-Run must NEVER call .delete()!")
    monkeypatch.setattr(mta, "get_supabase_client", lambda: mock_sb)
    monkeypatch.setattr(mta, "load_database_snapshot", lambda sb, include_auth_status=False: snapshot)
    monkeypatch.setattr(mta, "fetch_rows_by_in_chunks", lambda *a, **kw: [])
    monkeypatch.setattr(mta, "assert_git_ignored", lambda *a, **kw: None)

    destroy_called = False

    def fail_destroy(*args, **kwargs):
        nonlocal destroy_called
        destroy_called = True
        raise AssertionError("Dry-Run must NEVER call Cloudinary destroy!")

    monkeypatch.setattr(mta, "destroy_cloudinary_assets_strict", fail_destroy)

    rc = mta.main(["--purge"])
    assert rc == 0
    assert not destroy_called
    mock_sb.table.return_value.delete.assert_not_called()


def test_upgrade_pool_dry_run_performs_zero_http_calls_and_zero_file_writes(tmp_path, monkeypatch):
    """Default --upgrade-pool (execute=False) makes zero HTTP calls and creates zero files."""
    env_file = tmp_path / ".env.test-pool.local"
    monkeypatch.setattr(mta, "verify_git_ignored", lambda *a, **kw: True)

    pool_rows = [
        {"id": TEST_USER_OWNER_ID, "name": "[Test] Owner", "recovery_key_id": None, "credential_version": 1},
        {"id": TEST_USER_EDITOR_ID, "name": "[Test] Editor", "recovery_key_id": None, "credential_version": 1},
        {"id": TEST_USER_VIEWER_ID, "name": "[Test] Viewer", "recovery_key_id": None, "credential_version": 1},
        {"id": TEST_USER_CAPSULE_ID, "name": "[Test] CapsuleTester", "recovery_key_id": None, "credential_version": 1},
        {"id": TEST_USER_STRANGER_ID, "name": "[Test] Stranger", "recovery_key_id": None, "credential_version": 1},
    ]
    monkeypatch.setattr(mta, "fetch_rows_by_in_chunks", lambda *a, **kw: pool_rows)

    mock_http = MagicMock()
    mock_http.get.side_effect = AssertionError("Dry-Run must NEVER call HTTP GET!")
    mock_http.post.side_effect = AssertionError("Dry-Run must NEVER call HTTP POST!")

    result = mta.upgrade_test_pool(
        MagicMock(),
        execute=False,
        env_out=env_file,
        repo_root=tmp_path,
        http_client=mock_http,
    )
    assert result["dry_run"] is True
    assert [r for r, _ in result["preflight"]["to_upgrade"]] == ["OWNER", "EDITOR", "CAPSULE", "STRANGER"]
    assert "VIEWER" in result["preflight"]["skipped_hard_locked"]
    assert "RYAN_TEST" in result["preflight"]["skipped_hard_locked"]
    assert not env_file.exists()


# ---------------------------------------------------------------------------
# 3. Hard-Protected SHA-256 Whitelist & Real User Isolation
# ---------------------------------------------------------------------------
def test_hard_protected_sha256_blocks_main_pool_and_real_users(monkeypatch):
    """Hard-protected accounts (main + 6-account pool) and real/shared users must NEVER be qualified."""
    env_ryan_v4 = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    monkeypatch.setenv("TEST_USER_RYAN_TEST_ID", env_ryan_v4)

    zack_uid = "25eff9b9-1111-4111-8111-111111111111"
    anon_traveler = "77777777-2222-4222-8222-222222222222"
    target_shared = mta.APPROVED_PURGE_USER_IDS[0]
    target_clean = mta.APPROVED_PURGE_USER_IDS[1]
    shared_trip_id = str(uuid.uuid4())

    # Even if an attacker injects protected IDs into approved_user_ids, SHA-256 guard must block all of them!
    poisoned_approved = [
        TEST_USER_OWNER_ID,
        TEST_USER_VIEWER_ID,
        SYNTHETIC_RYAN_TEST_ID,
        env_ryan_v4,
        target_shared,
        target_clean,
    ]
    # Verify main account digest matches hard-protected set without needing plaintext in source
    assert mta.MAIN_USER_UID_SHA256 in mta.HARD_PROTECTED_USER_ID_HASHES
    assert mta.RYAN_TEST_UID_SHA256 in mta.HARD_PROTECTED_USER_ID_HASHES
    assert mta.is_hard_protected_user(env_ryan_v4) is True

    snapshot = _empty_snapshot(
        users=[
            {"id": TEST_USER_OWNER_ID, "name": "[Test] Owner"},
            {"id": TEST_USER_VIEWER_ID, "name": "[Test] Viewer"},
            {"id": SYNTHETIC_RYAN_TEST_ID, "name": "Ryan Test"},
            {"id": env_ryan_v4, "name": "Ryan Test Env"},
            {"id": zack_uid, "name": "Zack"},
            {"id": anon_traveler, "name": "Traveler"},
            {"id": target_shared, "name": "Test"},
            {"id": target_clean, "name": "QA_Audit"},
        ],
        itineraries=[
            {"id": shared_trip_id, "title": "Real Shared Trip", "created_by": zack_uid, "user_id": None},
        ],
        trip_members=[
            {"id": str(uuid.uuid4()), "itinerary_id": shared_trip_id, "user_id": zack_uid, "user_name": "Zack"},
            {"id": str(uuid.uuid4()), "itinerary_id": shared_trip_id, "user_id": target_shared, "user_name": "Test"},
        ],
    )

    plan = mta.build_purge_plan(snapshot, approved_user_ids=poisoned_approved)
    assert plan["qualified_user_ids"] == [target_clean]
    dq_reasons = {d["user_id"]: d["reason"] for d in plan["disqualified_users"]}
    assert dq_reasons[TEST_USER_OWNER_ID] == "hard_protected_user"
    assert dq_reasons[TEST_USER_VIEWER_ID] == "hard_protected_user"
    assert dq_reasons[SYNTHETIC_RYAN_TEST_ID] == "hard_protected_user"
    assert dq_reasons[env_ryan_v4] == "hard_protected_user"
    assert dq_reasons[target_shared] == "shares_itinerary_with_non_target_user"
    assert zack_uid not in plan["qualified_user_ids"]
    assert anon_traveler not in plan["qualified_user_ids"]
    assert shared_trip_id not in plan["all_target_trip_ids"]


# ---------------------------------------------------------------------------
# 4. Guardrail Resolutions (a) & (b) + fk_itineraries_user CASCADE Guard
# ---------------------------------------------------------------------------
def test_guardrail_a_external_expenses_abort_while_test_success_expense_allowed():
    """
    Guardrail (a):
    - #29 daec9523 holding an expense on approved non-UUID orphan TEST-SUCCESS (0f2410b7-...) is ALLOWED.
    - Any target user holding an expense on an external non-approved itinerary is ABORTED (has_external_expenses).
    """
    daec_uid = "daec9523-d377-4752-bed8-17efe5bba1e5"
    other_target = mta.APPROVED_PURGE_USER_IDS[0]
    real_uid = "25eff9b9-1111-4111-8111-111111111111"
    test_success_trip_id = "0f2410b7-65f7-4489-a5b7-52f435d9213d"
    real_trip_id = str(uuid.uuid4())

    snapshot = _empty_snapshot(
        users=[
            {"id": daec_uid, "name": "開發者"},
            {"id": other_target, "name": "Test"},
            {"id": real_uid, "name": "Zack"},
        ],
        itineraries=[
            {"id": test_success_trip_id, "title": "TEST-SUCCESS", "created_by": "test-uuid", "user_id": None},
            {"id": real_trip_id, "title": "Zack Kyoto", "created_by": real_uid, "user_id": None},
        ],
        trip_members=[
            {"id": str(uuid.uuid4()), "itinerary_id": test_success_trip_id, "user_id": "test-uuid", "user_name": "Ryan"},
        ],
        expenses=[
            {
                "id": str(uuid.uuid4()),
                "itinerary_id": test_success_trip_id,
                "created_by": daec_uid,
                "payer_id": None,
                "title": "Test Expense",
                "amount": 100,
            },
            {
                "id": str(uuid.uuid4()),
                "itinerary_id": real_trip_id,
                "created_by": other_target,
                "payer_id": None,
                "title": "External Real Expense",
                "amount": 500,
            },
        ],
    )

    plan = mta.build_purge_plan(snapshot, approved_user_ids=[daec_uid, other_target])
    assert daec_uid in plan["qualified_user_ids"]
    assert other_target not in plan["qualified_user_ids"]
    dq = {d["user_id"]: d["reason"] for d in plan["disqualified_users"]}
    assert dq[other_target] == "has_external_expenses"


def test_guardrail_b_exempt_editor_on_test_full_flow_and_non_exempt_trip_aborted():
    """
    Guardrail (b):
    - [Test] Editor (00002) dangling membership on TEST-FULL-FLOW (f4a1773d-...) is exempted and removed,
      while [Test] Editor account stays untouched.
    - Any non-exempt real/pool user membership on another non-UUID itinerary aborts deleting that itinerary.
    """
    test_full_flow_id = "f4a1773d-582b-413a-8a1f-a27b9dfde549"
    other_non_uuid_trip_id = str(uuid.uuid4())
    editor_mem_id = str(uuid.uuid4())

    snapshot = _empty_snapshot(
        users=[
            {"id": TEST_USER_OWNER_ID, "name": "[Test] Owner"},
            {"id": TEST_USER_EDITOR_ID, "name": "[Test] Editor"},
        ],
        itineraries=[
            {"id": test_full_flow_id, "title": "TEST-FULL-FLOW", "created_by": "test-uuid", "user_id": None},
            {"id": other_non_uuid_trip_id, "title": "TEST-OTHER", "created_by": "test-uuid", "user_id": None},
        ],
        trip_members=[
            {"id": str(uuid.uuid4()), "itinerary_id": test_full_flow_id, "user_id": "test-uuid", "user_name": "Ryan"},
            {"id": editor_mem_id, "itinerary_id": test_full_flow_id, "user_id": TEST_USER_EDITOR_ID, "user_name": "[Test] Editor"},
            {"id": str(uuid.uuid4()), "itinerary_id": other_non_uuid_trip_id, "user_id": TEST_USER_OWNER_ID, "user_name": "[Test] Owner"},
        ],
    )

    plan = mta.build_purge_plan(snapshot, approved_user_ids=[])
    assert test_full_flow_id in plan["non_uuid_trip_ids"]
    assert [m["id"] for m in plan["exempt_member_rows"]] == [editor_mem_id]
    assert TEST_USER_EDITOR_ID not in plan["qualified_user_ids"]
    assert other_non_uuid_trip_id not in plan["non_uuid_trip_ids"]
    assert any(d["itinerary_id"] == other_non_uuid_trip_id for d in plan["disqualified_trips"])


def test_fk_itineraries_user_cascade_guard_protects_shared_user_id_itinerary():
    """
    If itineraries.user_id points to a target user while another non-target user is a member or creator,
    the target user MUST be disqualified so deleting public.users cannot trigger fk_itineraries_user CASCADE.
    """
    target_uid = mta.APPROVED_PURGE_USER_IDS[0]
    real_uid = "25eff9b9-1111-4111-8111-111111111111"
    cascade_trip_id = str(uuid.uuid4())

    snapshot = _empty_snapshot(
        users=[
            {"id": target_uid, "name": "Test"},
            {"id": real_uid, "name": "Zack"},
        ],
        itineraries=[
            {"id": cascade_trip_id, "title": "Shared Cascade Trip", "created_by": real_uid, "user_id": target_uid},
        ],
        trip_members=[
            {"id": str(uuid.uuid4()), "itinerary_id": cascade_trip_id, "user_id": real_uid, "user_name": "Zack"},
        ],
    )

    plan = mta.build_purge_plan(snapshot, approved_user_ids=[target_uid])
    assert target_uid not in plan["qualified_user_ids"]
    assert cascade_trip_id not in plan["all_target_trip_ids"]
    dq = {d["user_id"]: d["reason"] for d in plan["disqualified_users"]}
    assert dq[target_uid] == "owned_trip_creator_non_target"


# ---------------------------------------------------------------------------
# 5. Empty SYSTEM Sample Trip Guards (NULL Creator + 1h Cooldown)
# ---------------------------------------------------------------------------
def test_empty_system_trip_strict_creator_and_one_hour_cooldown_guard():
    """
    - created_by IS NULL historical itineraries must NEVER be deleted.
    - Empty SYSTEM sample itineraries < 1 hour old must be skipped (seed-sample concurrency guard).
    - Empty SYSTEM sample itineraries >= 1 hour old are safely targeted.
    """
    now = datetime(2026, 11, 25, 12, 0, 0, tzinfo=timezone.utc)
    null_creator_trip = str(uuid.uuid4())
    recent_system_trip = str(uuid.uuid4())
    old_system_trip = str(uuid.uuid4())

    snapshot = _empty_snapshot(
        itineraries=[
            {
                "id": null_creator_trip,
                "title": "2026 東京 × 橫濱 (修正版 II)",
                "created_by": None,
                "user_id": None,
                "created_at": (now - timedelta(days=30)).isoformat(),
            },
            {
                "id": recent_system_trip,
                "title": mta.SAMPLE_TRIP_TITLE,
                "created_by": "SYSTEM",
                "user_id": None,
                "created_at": (now - timedelta(minutes=20)).isoformat(),
            },
            {
                "id": old_system_trip,
                "title": mta.SAMPLE_TRIP_TITLE,
                "created_by": "SYSTEM",
                "user_id": None,
                "created_at": (now - timedelta(hours=3)).isoformat(),
            },
        ]
    )

    plan = mta.build_purge_plan(snapshot, now=now, approved_user_ids=[])
    assert plan["empty_system_trip_ids"] == [old_system_trip]
    assert null_creator_trip not in plan["all_target_trip_ids"]
    assert recent_system_trip not in plan["all_target_trip_ids"]
    assert plan["skipped_null_creator_trips_count"] == 1
    assert plan["skipped_recent_system_trips_count"] == 1


# ---------------------------------------------------------------------------
# 6. FK Delete Order, uuid_only() Guard & Trigger Batch Throttling (25 / 0.3s)
# ---------------------------------------------------------------------------
def test_execute_purge_fk_order_uuid_only_filter_and_trigger_throttling(monkeypatch):
    """
    Verify:
    - Exact multi-dimensional FK delete order across all 9 tables.
    - UUID-typed columns NEVER receive non-UUID strings (prevents Postgres 22P02).
    - TEXT notifications.user_id includes test-uuid and c4f87a37-...
    - itinerary_items (60 rows) deleted by id in [25, 25, 10] with 3x sleep(0.3).
    - itineraries (30 rows) deleted by id in [25, 5] with 2x sleep(0.3).
    """
    monkeypatch.setenv("CLOUDINARY_CLOUD_NAME", "demo")
    monkeypatch.setenv("CLOUDINARY_API_KEY", "k")
    monkeypatch.setenv("CLOUDINARY_API_SECRET", "s")

    target_uid = "daec9523-d377-4752-bed8-17efe5bba1e5"
    orphan_push_uid = "c4f87a37-0a3e-4052-93c2-aba9088aeb8c"
    orphan_push_id = str(uuid.uuid4())
    trip_ids = [str(uuid.uuid4()) for _ in range(30)]
    items = [{"id": str(uuid.uuid4()), "itinerary_id": trip_ids[0]} for _ in range(60)]

    plan = {
        "qualified_user_ids": [target_uid],
        "all_target_trip_ids": trip_ids,
        "exempt_member_rows": [{"id": str(uuid.uuid4())}],
        "orphan_explorer_members": [{"id": str(uuid.uuid4())}],
        "non_uuid_creators": ["test-uuid"],
        "orphan_explorer_user_ids": ["e2e-tester-uuid-1234"],
        "target_pref_user_ids": [target_uid, "test-uuid"],  # deliberately include non-UUID to test uuid_only()
        "target_notif_user_ids": [target_uid, "test-uuid", orphan_push_uid],
        "orphan_push_subs": [{"id": orphan_push_id, "user_id": orphan_push_uid}],
        "orphan_push_user_ids": [orphan_push_uid],
        "cloudinary_urls": ["https://res.cloudinary.com/demo/image/upload/v1/ryan_travel/avatars/test.png"],
    }

    delete_calls: List[tuple[str, str, List[str]]] = []
    sleeps: List[float] = []

    mock_sb = MagicMock()

    def table_side_effect(table_name: str):
        tbl = MagicMock()

        def delete_side_effect():
            del_q = MagicMock()

            def in_side_effect(col: str, vals: List[str]):
                delete_calls.append((table_name, col, list(vals)))
                return MagicMock(execute=lambda: MagicMock(data=[{"id": v} for v in vals]))

            del_q.in_.side_effect = in_side_effect
            return del_q

        tbl.delete.side_effect = delete_side_effect
        return tbl

    mock_sb.table.side_effect = table_side_effect

    mock_http = MagicMock()
    mock_http.post.return_value = httpx.Response(200, json={"result": "ok"})

    result = mta.execute_purge(
        mock_sb,
        plan,
        items,
        sleep_fn=lambda sec: sleeps.append(sec),
        http_client=mock_http,
    )

    # 1. Exact FK table order (first appearance of each table)
    first_seen_order: List[str] = []
    for tbl, _, _ in delete_calls:
        if tbl not in first_seen_order:
            first_seen_order.append(tbl)
    assert first_seen_order == [
        "expenses",
        "itinerary_items",
        "trip_capsule_entries",
        "trip_members",
        "itineraries",
        "user_preferences",
        "notifications",
        "push_subscriptions",
        "users",
    ]

    # 2. UUID-typed columns strictly receive valid UUIDs only
    uuid_columns = {
        ("expenses", "itinerary_id"),
        ("expenses", "created_by"),
        ("expenses", "payer_id"),
        ("itinerary_items", "id"),
        ("trip_capsule_entries", "trip_id"),
        ("trip_capsule_entries", "author_id"),
        ("trip_members", "id"),
        ("trip_members", "itinerary_id"),
        ("itineraries", "id"),
        ("user_preferences", "user_id"),
        ("push_subscriptions", "id"),
        ("users", "id"),
    }
    for tbl, col, vals in delete_calls:
        assert len(vals) <= mta.CHUNK_SIZE
        if (tbl, col) in uuid_columns:
            for v in vals:
                assert mta.is_valid_uuid(v), f"Non-UUID {v!r} sent to UUID column {tbl}.{col}!"

    # 3. Notifications TEXT column covers target user, test-uuid, and c4f87a37
    notif_vals = [v for tbl, col, vals in delete_calls if tbl == "notifications" and col == "user_id" for v in vals]
    assert target_uid in notif_vals
    assert "test-uuid" in notif_vals
    assert orphan_push_uid in notif_vals

    # 4. Row-level trigger throttling: 60 items -> [25, 25, 10], 30 trips -> [25, 5], 5 sleeps of 0.3s
    item_batches = [len(vals) for tbl, col, vals in delete_calls if tbl == "itinerary_items" and col == "id"]
    itin_batches = [len(vals) for tbl, col, vals in delete_calls if tbl == "itineraries" and col == "id"]
    assert item_batches == [25, 25, 10]
    assert itin_batches == [25, 5]
    assert sleeps == [0.3, 0.3, 0.3, 0.3, 0.3]
    assert result["cloudinary_results"] == {"ryan_travel/avatars/test": "ok"}


# ---------------------------------------------------------------------------
# 7. Redacted Physical Backup Path Containment & Sensitive Stripping
# ---------------------------------------------------------------------------
def test_redacted_backup_path_containment_and_sensitive_field_stripping(tmp_path, monkeypatch):
    """Backup must be locked to docs/migrations/backups/ and strip all 5 sensitive keys recursively."""
    # Reject bare filename, parent traversal, sibling prefix traversal (AD-198), and non-json
    for bad_path in (
        "backup.json",
        "../outside.json",
        "docs/migrations/backups/../escape.json",
        "docs/migrations/backups_evil/sneaky.json",
        "docs/migrations/backups/not_json.txt",
    ):
        with pytest.raises(ValueError):
            mta.resolve_safe_backup_path(bad_path, repo_root=tmp_path)

    # Valid path inside docs/migrations/backups/
    monkeypatch.setattr(mta, "verify_git_ignored", lambda *a, **kw: True)
    dirty_payload = {
        "timestamp": "2026-11-25T00:00:00Z",
        "users": [
            {
                "id": "82f4d62f-5388-416f-b54a-b4ebb7ea2266",
                "name": "Test",
                "recovery_secret_hash": "SECRET_HASH",
                "recovery_key_encrypted": "SECRET_CIPHERTEXT",
                "recovery_key_id": "deadbeef",
            }
        ],
        "push_subscriptions": [
            {
                "id": "sub-1",
                "user_id": "c4f87a37-0a3e-4052-93c2-aba9088aeb8c",
                "endpoint": "https://push.example/1",
                "p256dh": "SECRET_P256DH",
                "auth": "SECRET_AUTH",
            }
        ],
    }

    written, digest = mta.write_redacted_backup(
        dirty_payload,
        "docs/migrations/backups/test_redacted.json",
        repo_root=tmp_path,
    )
    assert written.exists()
    assert len(digest) == 64
    raw_text = written.read_text(encoding="utf-8")
    for secret_key in ("recovery_secret_hash", "recovery_key_encrypted", "recovery_key_id", "p256dh", "auth"):
        assert secret_key not in raw_text
    for secret_val in ("SECRET_HASH", "SECRET_CIPHERTEXT", "deadbeef", "SECRET_P256DH", "SECRET_AUTH"):
        assert secret_val not in raw_text
    parsed = json.loads(raw_text)
    assert parsed["users"][0]["name"] == "Test"
    assert parsed["push_subscriptions"][0]["endpoint"] == "https://push.example/1"


# ---------------------------------------------------------------------------
# 8. Strict Cloudinary Destroy Verification (Never Swallow 401)
# ---------------------------------------------------------------------------
def test_cloudinary_destroy_strict_verification_rejects_401_and_unexpected_result(monkeypatch):
    """Cloudinary destroy accepts HTTP 200 + ok/not found, and raises loudly on 401 or error result."""
    monkeypatch.setenv("CLOUDINARY_CLOUD_NAME", "dnpcnwrcu")
    monkeypatch.setenv("CLOUDINARY_API_KEY", "key_123")
    monkeypatch.setenv("CLOUDINARY_API_SECRET", "sec_456")

    url_ok = "https://res.cloudinary.com/dnpcnwrcu/image/upload/v1768719832/ryan_travel/avatars/avatar_ok.png"
    url_nf = "https://res.cloudinary.com/dnpcnwrcu/image/upload/v1768719832/ryan_travel/avatars/avatar_nf.png"

    # Benign control: HTTP 200 with "ok" and "not found" both pass
    client_ok = MagicMock()
    client_ok.post.side_effect = [
        httpx.Response(200, json={"result": "ok"}),
        httpx.Response(200, json={"result": "not found"}),
    ]
    res = mta.destroy_cloudinary_assets_strict([url_ok, url_nf], http_client=client_ok)
    assert res == {
        "ryan_travel/avatars/avatar_ok": "ok",
        "ryan_travel/avatars/avatar_nf": "not found",
    }

    # HTTP 401 MUST NOT be silently swallowed
    client_401 = MagicMock()
    client_401.post.return_value = httpx.Response(401, json={"error": {"message": "Invalid Signature"}})
    with pytest.raises(RuntimeError, match="HTTP 401"):
        mta.destroy_cloudinary_assets_strict([url_ok], http_client=client_401)

    # HTTP 200 with unexpected result MUST raise
    client_bad = MagicMock()
    client_bad.post.return_value = httpx.Response(200, json={"result": "error"})
    with pytest.raises(RuntimeError, match="unexpected result"):
        mta.destroy_cloudinary_assets_strict([url_ok], http_client=client_bad)

    # Missing credentials when URLs present MUST raise
    monkeypatch.delenv("CLOUDINARY_API_SECRET", raising=False)
    monkeypatch.delenv("CLOUDINARY_URL", raising=False)
    with pytest.raises(RuntimeError, match="credentials"):
        mta.destroy_cloudinary_assets_strict([url_ok], http_client=client_ok)


# ---------------------------------------------------------------------------
# 9. --upgrade-pool Safety Net (Warmup, Hard-Lock, Atomic Merge, Git Ignore, Desync)
# ---------------------------------------------------------------------------
def test_upgrade_pool_full_flow_warmup_hard_lock_atomic_merge_and_stdout_masking(
    tmp_path, monkeypatch, capsys
):
    """
    Verifies:
    - GET /api/health/deep warmup runs FIRST with timeout=30.0.
    - VIEWER (00003) and RYAN_TEST are hard-skipped even if injected in target_roles.
    - Already-upgraded role (CAPSULE) is skipped idempotently.
    - Existing keys in .env.test-pool.local are preserved via atomic merge (.env.test-pool.tmp.local -> os.replace).
    - Full plaintext tbj_rec_* NEVER appears in stdout.
    """
    env_file = tmp_path / ".env.test-pool.local"
    env_file.write_text(
        "TEST_USER_RYAN_TEST_RECOVERY_KEY=tbj_rec_11112222_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n",
        encoding="utf-8",
    )

    git_cmds: List[List[str]] = []

    def fake_run(cmd, **kwargs):
        git_cmds.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(mta.subprocess, "run", fake_run)

    pool_rows = [
        {"id": TEST_USER_OWNER_ID, "name": "[Test] Owner", "recovery_key_id": None, "credential_version": 1},
        {"id": TEST_USER_EDITOR_ID, "name": "[Test] Editor", "recovery_key_id": None, "credential_version": 1},
        {"id": TEST_USER_VIEWER_ID, "name": "[Test] Viewer", "recovery_key_id": None, "credential_version": 1},
        {"id": TEST_USER_CAPSULE_ID, "name": "[Test] CapsuleTester", "recovery_key_id": "abcd1234", "credential_version": 1},
        {"id": TEST_USER_STRANGER_ID, "name": "[Test] Stranger", "recovery_key_id": None, "credential_version": 1},
    ]
    monkeypatch.setattr(mta, "fetch_rows_by_in_chunks", lambda *a, **kw: pool_rows)

    key_owner = "tbj_rec_aaaa1111_0123456789abcdef0123456789abcdef"
    key_editor = "tbj_rec_bbbb2222_fedcba9876543210fedcba9876543210"
    key_stranger = "tbj_rec_cccc3333_00112233445566778899aabbccddeeff"

    http_trace: List[tuple[str, str, float]] = []
    mock_http = MagicMock()

    def fake_get(url, headers=None, timeout=None):
        http_trace.append(("GET", url, timeout))
        return httpx.Response(200, json={"status": "healthy"})

    def fake_post(url, json=None, headers=None, timeout=None):
        http_trace.append(("POST", url, timeout))
        uid = json["recovery_key"]
        mapping = {
            TEST_USER_OWNER_ID: key_owner,
            TEST_USER_EDITOR_ID: key_editor,
            TEST_USER_STRANGER_ID: key_stranger,
        }
        assert uid in mapping, f"Forbidden account sent to /api/auth/session: {uid}"
        return httpx.Response(
            200,
            json={
                "access_token": "jwt.tok.sig",
                "user_id": uid,
                "is_new": False,
                "upgraded": True,
                "recovery_key": mapping[uid],
            },
        )

    mock_http.get.side_effect = fake_get
    mock_http.post.side_effect = fake_post

    # Inject VIEWER and SYNTHETIC_RYAN_TEST_ID to prove hard-lock skips both!
    injected_roles = (
        ("OWNER", TEST_USER_OWNER_ID),
        ("VIEWER", TEST_USER_VIEWER_ID),
        ("EDITOR", TEST_USER_EDITOR_ID),
        ("CAPSULE", TEST_USER_CAPSULE_ID),
        ("STRANGER", TEST_USER_STRANGER_ID),
        ("RYAN_TEST", SYNTHETIC_RYAN_TEST_ID),
    )
    sleeps: List[float] = []

    res = mta.upgrade_test_pool(
        MagicMock(),
        execute=True,
        api_base="https://www.tabijiapp.com",
        env_out=env_file,
        repo_root=tmp_path,
        http_client=mock_http,
        sleep_fn=lambda s: sleeps.append(s),
        target_roles=injected_roles,
    )

    # 1. Warmup GET first with timeout=30.0, then exactly 3 POSTs (OWNER, EDITOR, STRANGER)
    assert http_trace[0] == ("GET", "https://www.tabijiapp.com/api/health/deep", 30.0)
    assert len(http_trace) == 4
    assert all(t == 30.0 for _, _, t in http_trace)
    assert sleeps == [0.5, 0.5]

    # 2. Bare `git check-ignore -q -- <path>` (strictly NO -v and NO --no-index!)
    assert len(git_cmds) >= 2
    for cmd in git_cmds:
        assert cmd[:4] == ["git", "check-ignore", "-q", "--"]
        assert "-v" not in cmd
        assert "--no-index" not in cmd

    # 3. Atomic merge preserved existing RYAN_TEST key AND added the 3 upgraded keys; no leftover tmp
    assert not (tmp_path / ".env.test-pool.tmp.local").exists()
    _, env_map = mta.parse_env_file(env_file)
    assert env_map["TEST_USER_RYAN_TEST_RECOVERY_KEY"] == "tbj_rec_11112222_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert env_map["TEST_USER_OWNER_RECOVERY_KEY"] == key_owner
    assert env_map["TEST_USER_EDITOR_RECOVERY_KEY"] == key_editor
    assert env_map["TEST_USER_STRANGER_RECOVERY_KEY"] == key_stranger
    assert "TEST_USER_VIEWER_RECOVERY_KEY" not in env_map

    # 4. Stdout never leaks plaintext recovery keys
    captured = capsys.readouterr().out
    for plain in (key_owner, key_editor, key_stranger):
        assert plain not in captured
    assert len(res["upgraded"]) == 3


def test_upgrade_pool_fail_closed_when_not_gitignored_and_cleans_tmp_on_replace_error(
    tmp_path, monkeypatch
):
    """Fail-closed if git check-ignore -q fails; clean up temp file in finally if os.replace fails."""
    env_file = tmp_path / ".env.test-pool.local"
    tmp_file = tmp_path / ".env.test-pool.tmp.local"

    # Case A: git check-ignore -q returns 1 (unignored) -> abort BEFORE any DB/HTTP call
    monkeypatch.setattr(
        mta.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", ""),
    )
    mock_http = MagicMock()
    mock_http.get.side_effect = AssertionError("Must fail closed before HTTP!")
    with pytest.raises(RuntimeError, match="FAIL-CLOSED"):
        mta.upgrade_test_pool(
            MagicMock(),
            execute=True,
            env_out=env_file,
            repo_root=tmp_path,
            http_client=mock_http,
        )

    # Case B: os.replace fails -> finally removes .env.test-pool.tmp.local cleanly
    monkeypatch.setattr(
        mta.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", ""),
    )
    monkeypatch.setattr(mta.os, "replace", lambda src, dst: (_ for _ in ()).throw(OSError("disk locked")))
    with pytest.raises(OSError, match="disk locked"):
        mta.atomic_merge_write_env(env_file, {"K": "V"}, repo_root=tmp_path)
    assert not tmp_file.exists()


def test_upgrade_pool_timeout_detects_partial_upgrade_desync_and_preserves_earlier_keys(
    tmp_path, monkeypatch
):
    """
    If role #1 succeeds and role #2 times out:
    - Role #1's key is already safely persisted on disk.
    - Script re-queries Supabase for role #2; if recovery_key_id IS NOT NULL, raises PartialUpgradeDesyncError.
    - Also verifies malformed response (upgraded=False / invalid key) fails loudly.
    """
    env_file = tmp_path / ".env.test-pool.local"
    monkeypatch.setattr(mta, "verify_git_ignored", lambda *a, **kw: True)

    pool_rows = [
        {"id": TEST_USER_OWNER_ID, "name": "[Test] Owner", "recovery_key_id": None, "credential_version": 1},
        {"id": TEST_USER_EDITOR_ID, "name": "[Test] Editor", "recovery_key_id": None, "credential_version": 1},
        {"id": TEST_USER_VIEWER_ID, "name": "[Test] Viewer", "recovery_key_id": None, "credential_version": 1},
        {"id": TEST_USER_CAPSULE_ID, "name": "[Test] CapsuleTester", "recovery_key_id": "cap12345", "credential_version": 1},
        {"id": TEST_USER_STRANGER_ID, "name": "[Test] Stranger", "recovery_key_id": "str12345", "credential_version": 1},
    ]
    monkeypatch.setattr(mta, "fetch_rows_by_in_chunks", lambda *a, **kw: pool_rows)

    key_owner = "tbj_rec_deadbeef_0123456789abcdef0123456789abcdef"

    # Mock Supabase re-probe returning recovery_key_id != None -> PARTIAL_UPGRADE_DESYNC
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": TEST_USER_EDITOR_ID, "recovery_key_id": "beef9999", "credential_version": 1}]
    )

    mock_http = MagicMock()
    mock_http.get.return_value = httpx.Response(200, json={"status": "healthy"})
    mock_http.post.side_effect = [
        httpx.Response(
            200,
            json={
                "access_token": "jwt",
                "user_id": TEST_USER_OWNER_ID,
                "is_new": False,
                "upgraded": True,
                "recovery_key": key_owner,
            },
        ),
        httpx.ReadTimeout("timed out after server commit"),
    ]

    with pytest.raises(mta.PartialUpgradeDesyncError, match="PARTIAL_UPGRADE_DESYNC"):
        mta.upgrade_test_pool(
            mock_sb,
            execute=True,
            env_out=env_file,
            repo_root=tmp_path,
            http_client=mock_http,
            sleep_fn=lambda _: None,
        )

    # Role #1 key MUST be preserved despite Role #2 timeout!
    _, saved = mta.parse_env_file(env_file)
    assert saved["TEST_USER_OWNER_RECOVERY_KEY"] == key_owner

    # Now verify invalid response (upgraded=False or bad recovery_key format) raises loudly
    mock_http_bad = MagicMock()
    mock_http_bad.get.return_value = httpx.Response(200, json={"status": "healthy"})
    mock_http_bad.post.return_value = httpx.Response(
        200,
        json={
            "access_token": "jwt",
            "user_id": TEST_USER_OWNER_ID,
            "is_new": False,
            "upgraded": False,
            "recovery_key": "not-a-tbj-rec-key",
        },
    )
    with pytest.raises(RuntimeError, match="Invalid upgrade response"):
        mta.upgrade_test_pool(
            mock_sb,
            execute=True,
            env_out=env_file,
            repo_root=tmp_path,
            http_client=mock_http_bad,
            sleep_fn=lambda _: None,
        )


# ---------------------------------------------------------------------------
# 10. Adversarial Fixed-Point, Collateral Isolation, Preflight & Transport Guards
# ---------------------------------------------------------------------------
def test_joint_fixed_point_disqualifies_non_uuid_trips_and_dependent_users():
    """
    Joint fixed-point convergence invariants:
    - If approved user U2 is disqualified (has_push_subscriptions), any non-UUID trip referencing U2
      MUST be disqualified too, which in turn MUST disqualify approved user U1 whose expense lives on that trip.
    - Any non-UUID trip carrying a non-target user's expense or capsule MUST be disqualified.
    """
    u1 = mta.APPROVED_PURGE_USER_IDS[0]
    u2 = mta.APPROVED_PURGE_USER_IDS[1]
    zack = "25eff9b9-1111-4111-8111-111111111111"
    t_with_u2 = str(uuid.uuid4())
    t_with_zack_exp = str(uuid.uuid4())
    t_with_zack_cap = str(uuid.uuid4())

    snapshot = _empty_snapshot(
        users=[
            {"id": u1, "name": "Test 1"},
            {"id": u2, "name": "Test 2"},
            {"id": zack, "name": "Zack"},
        ],
        itineraries=[
            {"id": t_with_u2, "title": "TEST-U2", "created_by": "test-uuid", "user_id": None},
            {"id": t_with_zack_exp, "title": "TEST-ZACK-EXP", "created_by": "test-uuid", "user_id": None},
            {"id": t_with_zack_cap, "title": "TEST-ZACK-CAP", "created_by": "test-uuid", "user_id": None},
        ],
        trip_members=[
            {"id": str(uuid.uuid4()), "itinerary_id": t_with_u2, "user_id": u2, "user_name": "Test 2"},
        ],
        expenses=[
            {"id": str(uuid.uuid4()), "itinerary_id": t_with_u2, "created_by": u1, "payer_id": None},
            {"id": str(uuid.uuid4()), "itinerary_id": t_with_zack_exp, "created_by": zack, "payer_id": None},
        ],
        trip_capsule_entries=[
            {"id": str(uuid.uuid4()), "trip_id": t_with_zack_cap, "author_id": zack, "photo_url": None},
        ],
        push_subscriptions=[
            {"id": str(uuid.uuid4()), "user_id": u2, "endpoint": "https://push.example/u2"},
        ],
    )

    plan = mta.build_purge_plan(snapshot, approved_user_ids=[u1, u2])
    assert t_with_u2 not in plan["all_target_trip_ids"]
    assert t_with_zack_exp not in plan["all_target_trip_ids"]
    assert t_with_zack_cap not in plan["all_target_trip_ids"]
    assert u2 not in plan["qualified_user_ids"]
    assert u1 not in plan["qualified_user_ids"]
    dq_users = {d["user_id"]: d["reason"] for d in plan["disqualified_users"]}
    assert dq_users[u2] == "has_push_subscriptions"
    assert dq_users[u1] == "has_external_expenses"
    dq_trips = {d["itinerary_id"]: d["reason"] for d in plan["disqualified_trips"]}
    assert dq_trips[t_with_u2] == "non_exempt_member_present"
    assert dq_trips[t_with_zack_exp] == "non_target_expense_on_trip"
    assert dq_trips[t_with_zack_cap] == "non_target_capsule_on_trip"


def test_execute_purge_never_deletes_collateral_members_or_non_target_items_and_protects_retained_orphans():
    """
    - When test-uuid has both a safe trip T_safe and a disqualified shared trip T_disq,
      execute_purge MUST NOT delete trip_members by user_id='test-uuid' (which would wipe T_disq).
    - When an orphan Explorer user still participates in a retained real trip, their notifications/preferences
      and retained trip membership MUST NOT be deleted.
    - Items belonging to non-target trips are filtered out defensively in execute_purge.
    """
    now = datetime(2026, 11, 25, 12, 0, 0, tzinfo=timezone.utc)
    zack = "25eff9b9-1111-4111-8111-111111111111"
    orphan_uid = str(uuid.uuid4())
    t_safe = str(uuid.uuid4())
    t_disq = str(uuid.uuid4())
    t_sys = str(uuid.uuid4())
    t_real = str(uuid.uuid4())

    snapshot = _empty_snapshot(
        users=[{"id": zack, "name": "Zack"}],
        itineraries=[
            {"id": t_safe, "title": "TEST-SAFE", "created_by": "test-uuid", "user_id": None},
            {"id": t_disq, "title": "TEST-SHARED", "created_by": "test-uuid", "user_id": None},
            {
                "id": t_sys,
                "title": mta.SAMPLE_TRIP_TITLE,
                "created_by": "SYSTEM",
                "user_id": None,
                "created_at": (now - timedelta(hours=5)).isoformat(),
            },
            {"id": t_real, "title": "Zack Shared", "created_by": zack, "user_id": None},
        ],
        trip_members=[
            {"id": str(uuid.uuid4()), "itinerary_id": t_safe, "user_id": "test-uuid", "user_name": "X"},
            {"id": str(uuid.uuid4()), "itinerary_id": t_disq, "user_id": "test-uuid", "user_name": "X"},
            {"id": str(uuid.uuid4()), "itinerary_id": t_disq, "user_id": zack, "user_name": "Zack"},
            {"id": str(uuid.uuid4()), "itinerary_id": t_sys, "user_id": orphan_uid, "user_name": "Explorer"},
            {"id": str(uuid.uuid4()), "itinerary_id": t_real, "user_id": orphan_uid, "user_name": "Old Friend"},
            {"id": str(uuid.uuid4()), "itinerary_id": t_real, "user_id": zack, "user_name": "Zack"},
        ],
        notifications=[
            {"id": str(uuid.uuid4()), "user_id": orphan_uid, "title": "Keep Me"},
            {"id": str(uuid.uuid4()), "user_id": "test-uuid", "title": "Purge Me"},
        ],
        user_preferences=[
            {"id": str(uuid.uuid4()), "user_id": orphan_uid, "category": "diet"},
        ],
    )

    plan = mta.build_purge_plan(snapshot, now=now, approved_user_ids=[])
    assert t_safe in plan["all_target_trip_ids"]
    assert t_sys in plan["all_target_trip_ids"]
    assert t_disq not in plan["all_target_trip_ids"]
    assert t_real not in plan["all_target_trip_ids"]
    # Orphan user still on t_real must keep notifications & preferences
    assert orphan_uid not in plan["target_notif_user_ids"]
    assert orphan_uid not in plan["target_pref_user_ids"]

    safe_item_id = str(uuid.uuid4())
    non_target_item_id = str(uuid.uuid4())
    delete_calls: List[tuple[str, str, List[str]]] = []
    mock_sb = MagicMock()

    def table_side_effect(table_name: str):
        tbl = MagicMock()

        def delete_side_effect():
            del_q = MagicMock()

            def in_side_effect(col: str, vals: List[str]):
                delete_calls.append((table_name, col, list(vals)))
                return MagicMock(execute=lambda: MagicMock(data=[]))

            del_q.in_.side_effect = in_side_effect
            return del_q

        tbl.delete.side_effect = delete_side_effect
        return tbl

    mock_sb.table.side_effect = table_side_effect

    mta.execute_purge(
        mock_sb,
        plan,
        [
            {"id": safe_item_id, "itinerary_id": t_safe},
            {"id": non_target_item_id, "itinerary_id": t_real},
        ],
        sleep_fn=lambda _: None,
    )

    # Zero trip_members deletes by user_id='test-uuid' or orphan_uid
    assert not any(
        tbl == "trip_members" and col == "user_id" and ("test-uuid" in vals or orphan_uid in vals)
        for tbl, col, vals in delete_calls
    )
    # Non-target item was never sent to itinerary_items delete
    deleted_item_ids = [
        v for tbl, col, vals in delete_calls if tbl == "itinerary_items" and col == "id" for v in vals
    ]
    assert deleted_item_ids == [safe_item_id]


def test_execute_purge_preflights_cloudinary_credentials_before_any_db_delete(monkeypatch):
    """If Cloudinary credentials are missing or cloud mismatches, execute_purge MUST abort with ZERO DB deletes."""
    for k in (
        "CLOUDINARY_CLOUD_NAME",
        "NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME",
        "CLOUDINARY_API_KEY",
        "NEXT_PUBLIC_CLOUDINARY_API_KEY",
        "CLOUDINARY_API_SECRET",
        "CLOUDINARY_URL",
    ):
        monkeypatch.delenv(k, raising=False)

    mock_sb = MagicMock()
    mock_sb.table.return_value.delete.side_effect = AssertionError(
        "DB delete must NEVER run when Cloudinary preflight fails!"
    )

    plan = {
        "qualified_user_ids": [mta.APPROVED_PURGE_USER_IDS[0]],
        "all_target_trip_ids": [str(uuid.uuid4())],
        "exempt_member_rows": [],
        "orphan_explorer_members": [],
        "target_pref_user_ids": [],
        "target_notif_user_ids": [],
        "orphan_push_subs": [],
        "cloudinary_urls": ["https://res.cloudinary.com/dnpcnwrcu/image/upload/v1/ryan_travel/avatars/x.png"],
    }

    with pytest.raises(RuntimeError, match="Cloudinary credentials"):
        mta.execute_purge(mock_sb, plan, [], sleep_fn=lambda _: None)
    mock_sb.table.assert_not_called()


def test_null_creator_and_lowercase_system_owned_via_user_id_disqualify_target_user():
    """
    A target user referenced by itineraries.user_id on a created_by IS NULL historical itinerary
    (or lowercase 'system' non-SYSTEM creator) MUST be disqualified so fk_itineraries_user CASCADE cannot delete it.
    """
    u1 = mta.APPROVED_PURGE_USER_IDS[0]
    u2 = mta.APPROVED_PURGE_USER_IDS[1]
    t_null = str(uuid.uuid4())
    t_lower_sys = str(uuid.uuid4())

    snapshot = _empty_snapshot(
        users=[{"id": u1, "name": "Test 1"}, {"id": u2, "name": "Test 2"}],
        itineraries=[
            {"id": t_null, "title": "Historical NULL", "created_by": None, "user_id": u1},
            {"id": t_lower_sys, "title": "Lowercase system", "created_by": "system", "user_id": u2},
        ],
    )

    plan = mta.build_purge_plan(snapshot, approved_user_ids=[u1, u2])
    assert u1 not in plan["qualified_user_ids"]
    assert u2 not in plan["qualified_user_ids"]
    assert t_null not in plan["all_target_trip_ids"]
    assert t_lower_sys not in plan["all_target_trip_ids"]
    dq = {d["user_id"]: d["reason"] for d in plan["disqualified_users"]}
    assert dq[u1] == "owned_trip_null_creator"
    assert dq[u2] == "owned_trip_creator_non_target"


def test_upgrade_pool_transport_error_desync_non_json_200_and_windows_replace_retry(
    tmp_path, monkeypatch
):
    """
    - httpx.RemoteProtocolError also triggers Supabase re-probe for PARTIAL_UPGRADE_DESYNC.
    - Non-JSON HTTP 200 (e.g. proxy HTML) raises a clean RuntimeError instead of JSONDecodeError.
    - atomic_merge_write_env retries transient Windows PermissionError on os.replace.
    """
    env_file = tmp_path / ".env.test-pool.local"
    monkeypatch.setattr(mta, "verify_git_ignored", lambda *a, **kw: True)

    pool_rows = [
        {"id": TEST_USER_OWNER_ID, "name": "[Test] Owner", "recovery_key_id": None, "credential_version": 1},
        {"id": TEST_USER_EDITOR_ID, "name": "[Test] Editor", "recovery_key_id": "ed123456", "credential_version": 1},
        {"id": TEST_USER_VIEWER_ID, "name": "[Test] Viewer", "recovery_key_id": None, "credential_version": 1},
        {"id": TEST_USER_CAPSULE_ID, "name": "[Test] CapsuleTester", "recovery_key_id": "cap12345", "credential_version": 1},
        {"id": TEST_USER_STRANGER_ID, "name": "[Test] Stranger", "recovery_key_id": "str12345", "credential_version": 1},
    ]
    monkeypatch.setattr(mta, "fetch_rows_by_in_chunks", lambda *a, **kw: pool_rows)

    # 1. RemoteProtocolError -> PARTIAL_UPGRADE_DESYNC
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": TEST_USER_OWNER_ID, "recovery_key_id": "abcd9999", "credential_version": 1}]
    )
    mock_http_drop = MagicMock()
    mock_http_drop.get.return_value = httpx.Response(200, json={"status": "healthy"})
    mock_http_drop.post.side_effect = httpx.RemoteProtocolError("connection reset after commit")
    with pytest.raises(mta.PartialUpgradeDesyncError, match="PARTIAL_UPGRADE_DESYNC"):
        mta.upgrade_test_pool(
            mock_sb,
            execute=True,
            env_out=env_file,
            repo_root=tmp_path,
            http_client=mock_http_drop,
            sleep_fn=lambda _: None,
        )

    # 2. Non-JSON HTTP 200 -> clean RuntimeError
    mock_http_html = MagicMock()
    mock_http_html.get.return_value = httpx.Response(200, json={"status": "healthy"})
    mock_http_html.post.return_value = httpx.Response(200, text="<html>challenge</html>")
    with pytest.raises(RuntimeError, match="non-JSON HTTP 200"):
        mta.upgrade_test_pool(
            mock_sb,
            execute=True,
            env_out=env_file,
            repo_root=tmp_path,
            http_client=mock_http_html,
            sleep_fn=lambda _: None,
        )

    # 3. Transient Windows PermissionError on os.replace succeeds on retry
    real_replace = mta.os.replace
    attempts = {"count": 0}

    def flaky_replace(src, dst):
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise PermissionError("transient AV lock")
        return real_replace(src, dst)

    monkeypatch.setattr(mta.os, "replace", flaky_replace)
    written = mta.atomic_merge_write_env(env_file, {"TEST_RETRY_KEY": "ok"}, repo_root=tmp_path)
    assert attempts["count"] == 2
    assert mta.parse_env_file(written)[1]["TEST_RETRY_KEY"] == "ok"
