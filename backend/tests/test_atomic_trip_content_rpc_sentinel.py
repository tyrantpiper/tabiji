"""
Security Sentinel & Concurrency Verification Suite
Topic: atomic_trip_content_rpc (Phase 1 Pure Postgres Atomic RPC + Thread-Safe HTTP/1.1 Pool)

Includes:
- Mantis Block G Benign Controls (must pass BEFORE and AFTER patch)
- Red -> Green PoC Exploits & Static DDL Contract Guards
- 12-Thread HTTP/1.1 Concurrency Stress Test (guards against httpcore 1.0.9 HTTP2Connection crash)
- Cross-Instance (Zero Shared trip_lock) Interleaved Concurrent Write Suite
"""

import asyncio
import copy
import inspect
import os
import re
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from postgrest.exceptions import APIError
from supabase import ClientOptions, create_client

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app  # noqa: E402
from routers import trips as trips_router  # noqa: E402
from routers import ai as ai_router  # noqa: E402
from utils.deps import get_gemini_key, get_supabase, get_verified_user  # noqa: E402

OWNER_ID = "11111111-1111-4111-8111-111111111111"
COLLAB_ID = "22222222-2222-4222-8222-222222222222"
STRANGER_ID = "99999999-9999-4999-8999-999999999999"
TRIP_ID = "33333333-3333-4333-8333-333333333333"
DUMMY_API_KEY = "AIzaSyAtomicTripRpcSentinelTestKey1234567"
MIGRATION_PATH = REPO_ROOT / "supabase" / "migrations" / "20261125_atomic_trip_content_rpcs.sql"


class _AtomicQuery:
    def __init__(self, db, table_name: str):
        self.db = db
        self.table_name = table_name
        self._op = "select"
        self._payload = None
        self._filters = []

    def select(self, *_args, **_kwargs):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def _matches(self, row):
        return all(row.get(col) == val for _, col, val in self._filters)

    def execute(self):
        # Emulate real Postgres UUID column type enforcement when strict_uuid=True
        if self.db.strict_uuid and self.table_name in ("itineraries", "trip_members", "itinerary_items"):
            for _, col, val in self._filters:
                if col in ("id", "itinerary_id") and not re.match(
                    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                    str(val or ""),
                    re.IGNORECASE,
                ):
                    raise APIError({"code": "22P02", "message": f'invalid input syntax for type uuid: "{val}"'})
        # Intentionally yield between read and write on non-atomic RMW paths so
        # cross-instance race tests deterministically expose lost updates if RPC is bypassed!
        if self.db.rmw_delay_sec > 0 and self.table_name == "itineraries":
            time.sleep(self.db.rmw_delay_sec)
        with self.db._store_lock:
            rows = self.db.store.setdefault(self.table_name, [])
            if self._op == "select":
                return MagicMock(data=[copy.deepcopy(r) for r in rows if self._matches(r)])
            if self._op == "insert":
                items = self._payload if isinstance(self._payload, list) else [self._payload]
                out = []
                for entry in items:
                    rec = copy.deepcopy(entry)
                    rec.setdefault("id", str(uuid.uuid4()))
                    rows.append(rec)
                    out.append(copy.deepcopy(rec))
                return MagicMock(data=out)
            if self._op == "update":
                out = []
                for r in rows:
                    if self._matches(r):
                        r.update(copy.deepcopy(self._payload))
                        out.append(copy.deepcopy(r))
                return MagicMock(data=out)
            if self._op == "delete":
                kept, deleted = [], []
                for r in rows:
                    if self._matches(r):
                        deleted.append(copy.deepcopy(r))
                    else:
                        kept.append(r)
                self.db.store[self.table_name] = kept
                return MagicMock(data=deleted)
            return MagicMock(data=[])


class AtomicFakeSupabase:
    """In-memory PostgreSQL 17 atomic RPC emulator with real row-level locking."""

    def __init__(self, store: dict, *, rmw_delay_sec: float = 0.0, rpc_delay_sec: float = 0.0, strict_uuid: bool = False):
        self.store = store
        self.rmw_delay_sec = rmw_delay_sec
        self.rpc_delay_sec = rpc_delay_sec
        self.strict_uuid = strict_uuid
        self._store_lock = threading.Lock()
        self._row_lock = threading.Lock()
        self.rpc_calls = []
        self.rpc_threads = []
        self.rpc_error_queue = []

    def table(self, name: str):
        return _AtomicQuery(self, name)

    def rpc(self, fn_name: str, params: dict):
        db = self

        class _RpcExec:
            def execute(self_inner):
                db.rpc_threads.append(threading.get_ident())
                db.rpc_calls.append((fn_name, copy.deepcopy(params)))
                if db.rpc_error_queue:
                    err = db.rpc_error_queue.pop(0)
                    if err is not None:
                        raise err
                if db.rpc_delay_sec > 0:
                    time.sleep(db.rpc_delay_sec)
                with db._row_lock:
                    data = db._dispatch_rpc(fn_name, copy.deepcopy(params))
                return MagicMock(data=data)

        return _RpcExec()

    def _is_member(self, trip_id: str, uid: str) -> bool:
        return any(
            m.get("itinerary_id") == trip_id and str(m.get("user_id") or "").strip() == uid
            for m in self.store.get("trip_members", [])
        )

    def _find_trip(self, trip_id: str):
        return next((t for t in self.store.get("itineraries", []) if t.get("id") == trip_id), None)

    def _dispatch_rpc(self, fn_name: str, params: dict) -> dict:
        trip_id = str(params.get("p_trip_id") or "").strip()
        uid = str(params.get("p_user_id") or "").strip()
        patch_obj = params.get("p_patch")
        if not isinstance(patch_obj, dict):
            patch_obj = {}

        if fn_name == "patch_trip_day_data_atomic":
            day = params.get("p_day")
            if day is None or int(day) < 0:
                raise APIError({"code": "22023", "message": f"Invalid day number: {day}"})
            allow_bypass = bool(params.get("p_allow_creator_bypass", False))
            if not allow_bypass:
                if not self._is_member(trip_id, uid):
                    return {"status": "forbidden"}
                trip = self._find_trip(trip_id)
                if not trip:
                    return {"status": "not_found"}
                is_owner = str(trip.get("created_by") or "").strip() == uid
            else:
                trip = self._find_trip(trip_id)
                if not trip:
                    return {"status": "not_found"}
                is_owner = str(trip.get("created_by") or "").strip() == uid
                if not is_owner and not self._is_member(trip_id, uid):
                    return {"status": "forbidden"}

            content = copy.deepcopy(trip.get("content")) if isinstance(trip.get("content"), dict) else {}
            day_key = str(day)

            if "day_notes" in patch_obj:
                sub = dict(content.get("day_notes")) if isinstance(content.get("day_notes"), dict) else {}
                val = patch_obj["day_notes"].get(day_key, []) if isinstance(patch_obj["day_notes"], dict) else []
                sub[day_key] = val if val is not None else []
                content["day_notes"] = sub

            for field in ("day_costs", "day_tickets", "day_checklists"):
                if field in patch_obj:
                    sub = dict(content.get(field)) if isinstance(content.get(field), dict) else {}
                    existing = sub.get(day_key) if isinstance(sub.get(day_key), list) else []
                    submitted_raw = patch_obj[field].get(day_key, []) if isinstance(patch_obj[field], dict) else []
                    submitted = submitted_raw if isinstance(submitted_raw, list) else []
                    sub[day_key] = trips_router._merge_day_items_preserving_hidden_private(
                        existing, submitted, uid, is_owner
                    )
                    content[field] = sub

            if "day_ai_reviews" in patch_obj:
                sub = dict(content.get("day_ai_reviews")) if isinstance(content.get("day_ai_reviews"), dict) else {}
                val = patch_obj["day_ai_reviews"].get(day_key, "") if isinstance(patch_obj["day_ai_reviews"], dict) else ""
                sub[day_key] = val if val is not None else ""
                content["day_ai_reviews"] = sub

            if patch_obj.get("delete_day_ai_review") is True:
                sub = dict(content.get("day_ai_reviews")) if isinstance(content.get("day_ai_reviews"), dict) else {}
                if day_key in sub:
                    sub.pop(day_key, None)
                    content["day_ai_reviews"] = sub

            if "daily_locations" in patch_obj and isinstance(patch_obj["daily_locations"], dict):
                sub = dict(content.get("daily_locations")) if isinstance(content.get("daily_locations"), dict) else {}
                if day_key in patch_obj["daily_locations"]:
                    sub[day_key] = patch_obj["daily_locations"][day_key]
                    content["daily_locations"] = sub

            trip["content"] = content
            return {"status": "ok"}

        if fn_name == "patch_trip_info_atomic":
            if not self._is_member(trip_id, uid):
                return {"status": "forbidden"}
            trip = self._find_trip(trip_id)
            if not trip:
                return {"status": "not_found"}
            is_owner = str(trip.get("created_by") or "").strip() == uid
            content = copy.deepcopy(trip.get("content")) if isinstance(trip.get("content"), dict) else {}

            if "credit_cards" in patch_obj:
                submitted = patch_obj["credit_cards"] if isinstance(patch_obj["credit_cards"], list) else []
                content["credit_cards"] = trips_router._merge_cards_preserving_hidden_private(
                    content.get("credit_cards", []), submitted, uid, is_owner
                )
            if "flight_info" in patch_obj:
                val = patch_obj["flight_info"]
                trip["flight_info"] = None if val is None else val
                content["flight_info"] = val
            if "hotel_info" in patch_obj:
                val = patch_obj["hotel_info"]
                trip["hotel_info"] = None if val is None else val
                content["hotel_info"] = val

            trip["content"] = content
            return {"status": "ok"}

        if fn_name == "merge_trip_import_content_atomic":
            trip = self._find_trip(trip_id)
            if not trip:
                return {"status": "not_found"}
            is_owner = str(trip.get("created_by") or "").strip() == uid
            if not is_owner and not self._is_member(trip_id, uid):
                return {"status": "forbidden"}
            content = copy.deepcopy(trip.get("content")) if isinstance(trip.get("content"), dict) else {}

            if isinstance(patch_obj.get("day_notes"), dict):
                sub = dict(content.get("day_notes")) if isinstance(content.get("day_notes"), dict) else {}
                for k, v in patch_obj["day_notes"].items():
                    if v is None:
                        continue
                    if isinstance(sub.get(k), list):
                        if isinstance(v, list):
                            sub[k] = sub[k] + v
                    else:
                        sub[k] = v
                content["day_notes"] = sub

            for field in ("day_costs", "day_tickets", "day_checklists"):
                if isinstance(patch_obj.get(field), dict):
                    sub = dict(content.get(field)) if isinstance(content.get(field), dict) else {}
                    sanitized = trips_router._sanitize_imported_day_map(patch_obj[field], uid)
                    for k, v in sanitized.items():
                        if isinstance(sub.get(k), list) and isinstance(v, list):
                            sub[k] = sub[k] + v
                        elif isinstance(v, list):
                            sub[k] = v
                    content[field] = sub

            if patch_obj.get("ai_review"):
                content["ai_review"] = patch_obj["ai_review"]

            if isinstance(patch_obj.get("daily_locations"), dict):
                existing_locs = dict(content.get("daily_locations")) if isinstance(content.get("daily_locations"), dict) else {}
                merged = dict(patch_obj["daily_locations"])
                merged.update(existing_locs)  # Existing takes precedence!
                content["daily_locations"] = merged

            max_day = params.get("p_max_imported_day")
            fallback_start = params.get("p_fallback_start_date")
            if max_day and int(max_day) > 0:
                existing_start = trip.get("start_date")
                if not existing_start and fallback_start:
                    trip["start_date"] = fallback_start
                    existing_start = fallback_start
                if existing_start:
                    start_dt = datetime.strptime(str(existing_start).split("T")[0], "%Y-%m-%d")
                    cand_end_dt = start_dt + timedelta(days=int(max_day) - 1)
                    existing_end = trip.get("end_date")
                    if not existing_end:
                        if int(max_day) > 1:
                            trip["end_date"] = cand_end_dt.strftime("%Y-%m-%d")
                    else:
                        old_end_dt = datetime.strptime(str(existing_end).split("T")[0], "%Y-%m-%d")
                        if cand_end_dt > old_end_dt:
                            trip["end_date"] = cand_end_dt.strftime("%Y-%m-%d")

            trip["content"] = content
            return {"status": "ok"}

        raise APIError({"code": "PGRST202", "message": f"Could not find the function public.{fn_name}"})


def _base_store():
    return {
        "itineraries": [
            {
                "id": TRIP_ID,
                "title": "Tokyo Atomic Trip",
                "created_by": OWNER_ID,
                "start_date": "2026-12-01",
                "end_date": "2026-12-02",
                "flight_info": {"outbound": [{"code": "JL802"}]},
                "hotel_info": [{"name": "Initial Hotel"}],
                "content": {
                    "daily_locations": {"1": {"name": "Tokyo Existing", "lat": 35.68, "lng": 139.76}},
                    "day_checklists": {
                        "0": [{"id": "d0-old", "text": "Day 0 Pre-trip", "is_private": False}],
                        "1": [
                            {"id": "own-chk", "text": "OWNER_PRIV_CHK", "is_private": True, "private_owner_id": OWNER_ID}
                        ],
                    },
                    "day_costs": {"1": []},
                    "day_tickets": {"1": []},
                    "day_ai_reviews": {"2": "Old Day 2 review to delete"},
                    "credit_cards": [
                        {"id": "pub-card", "name": "Shared Card", "is_public": True, "creator_id": OWNER_ID},
                        {"id": "own-priv-card", "name": "OWNER_PRIV_CARD", "is_public": False, "creator_id": OWNER_ID},
                    ],
                },
            }
        ],
        "trip_members": [
            {"id": "m1", "itinerary_id": TRIP_ID, "user_id": OWNER_ID},
            {"id": "m2", "itinerary_id": TRIP_ID, "user_id": COLLAB_ID},
        ],
        "itinerary_items": [
            {
                "id": "it-1",
                "itinerary_id": TRIP_ID,
                "day_number": 1,
                "time_slot": "09:00",
                "place_name": "Tokyo Station",
                "category": "sightseeing",
                "notes": "",
                "location_lat": 35.6812,
                "location_lng": 139.7671,
            }
        ],
    }


# ==============================================================================
# Mantis Block G: Benign Controls (MUST PASS BEFORE & AFTER PATCH)
# ==============================================================================


def test_benign_legacy_magicmock_client_stays_compatible():
    """Benign Control 1: Legacy sentinel tests using bare MagicMock() with non-UUID trip_id
    and only .table() configured MUST continue to pass."""
    mock_sb = MagicMock()
    mock_sb.table().select().eq().eq().execute.return_value = MagicMock(data=[{"user_id": OWNER_ID}])
    mock_sb.table().select().eq().execute.return_value = MagicMock(
        data=[{"id": "trip-legacy-1", "created_by": OWNER_ID, "content": {}}]
    )
    mock_sb.table().update().eq().execute.return_value = MagicMock(data=[{"id": "trip-legacy-1"}])

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: OWNER_ID
    try:
        client = TestClient(app)
        r1 = client.patch("/api/trips/trip-legacy-1/day-data", json={"day": 1, "day_notes": {"1": ["ok"]}})
        r2 = client.patch("/api/trips/trip-legacy-1/info", json={"flight_info": {"outbound": []}})
        r3 = client.patch("/api/trips/trip-legacy-1/location", json={"day": 1, "name": "Tokyo", "lat": 35.68, "lng": 139.76})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_benign_member_single_write_succeeds():
    """Benign Control 2: Normal single-user day-data & info updates succeed cleanly."""
    store = _base_store()
    db = AtomicFakeSupabase(store)
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_verified_user] = lambda: OWNER_ID
    try:
        client = TestClient(app)
        r_day = client.patch(
            f"/api/trips/{TRIP_ID}/day-data",
            json={"day": 1, "day_notes": {"1": ["Bring umbrella"]}},
        )
        assert r_day.status_code == 200
        assert store["itineraries"][0]["content"]["day_notes"]["1"] == ["Bring umbrella"]

        r_info = client.patch(
            f"/api/trips/{TRIP_ID}/info",
            json={"hotel_info": [{"name": "Updated Hotel"}]},
        )
        assert r_info.status_code == 200
        assert store["itineraries"][0]["hotel_info"] == [{"name": "Updated Hotel"}]
    finally:
        app.dependency_overrides.clear()


# ==============================================================================
# Red -> Green PoC Exploits & Contract Guards
# ==============================================================================


def test_poc_migration_ddl_security_and_contract_invariants():
    """PoC 1: Verify SQL migration enforces every security, locking, timeout, and JSONB safety invariant."""
    assert MIGRATION_PATH.is_file(), f"Missing migration file: {MIGRATION_PATH}"
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    # 1. Drops high-risk legacy authenticated-callable SECURITY DEFINER RPC
    assert re.search(
        r"DROP\s+FUNCTION\s+IF\s+EXISTS\s+public\.update_trip_credit_cards\s*\(\s*UUID\s*,\s*JSONB\s*\)\s*;",
        sql,
        re.IGNORECASE,
    ), "Migration MUST drop public.update_trip_credit_cards(UUID, JSONB)"

    # 2. webhook_cleanup_cloudinary itineraries UPDATE no-op guard checks cover_image ONLY (matches cleanup-cloudinary v8)
    trigger_match = re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\.webhook_cleanup_cloudinary\(\).*?\$function\$;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert trigger_match, "Migration MUST update public.webhook_cleanup_cloudinary()"
    trigger_body = trigger_match.group(0)
    assert "TG_TABLE_NAME = 'itineraries'" in trigger_body
    assert "TG_OP = 'UPDATE'" in trigger_body
    assert "cover_image" in trigger_body
    assert "hotel_info" not in trigger_body, "Trigger guard must inspect cover_image ONLY to match live cleanup-cloudinary v8"

    # 3. Verify all 3 atomic RPCs exist with exact signatures, DAC, search_path, timeouts, FOR NO KEY UPDATE, safe merge
    expected_rpcs = [
        ("patch_trip_day_data_atomic", r"p_allow_creator_bypass\s+BOOLEAN\s+DEFAULT\s+false"),
        ("patch_trip_info_atomic", r"p_patch\s+JSONB"),
        (
            "merge_trip_import_content_atomic",
            r"p_max_imported_day\s+INTEGER\s+DEFAULT\s+NULL.*p_fallback_start_date\s+DATE\s+DEFAULT\s+NULL",
        ),
    ]
    for fn_name, sig_pat in expected_rpcs:
        fn_match = re.search(
            rf"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\.{fn_name}\s*\((.*?)\).*?\$function\$;",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert fn_match, f"Missing RPC function: {fn_name}"
        fn_sig = fn_match.group(1)
        fn_body = fn_match.group(0)
        assert re.search(sig_pat, fn_sig, re.IGNORECASE | re.DOTALL), f"{fn_name} signature mismatch"
        assert re.search(r"SECURITY\s+DEFINER", fn_body, re.IGNORECASE)
        assert re.search(r"SET\s+search_path\s+TO\s+'public',\s*'pg_temp'", fn_body, re.IGNORECASE)
        assert "set_config('lock_timeout', '3000ms', true)" in fn_body
        assert "set_config('statement_timeout', '8000ms', true)" in fn_body
        assert "FOR NO KEY UPDATE" in fn_body
        assert "jsonb_typeof" in fn_body
        assert "v_content || jsonb_build_object(" in fn_body
        # Must NOT use bare jsonb_set / 2-level jsonb_set_lax which drop/wipe on NULL or {}
        assert "jsonb_set(" not in fn_body.lower()
        assert "jsonb_set_lax(" not in fn_body.lower()

        assert re.search(
            rf"REVOKE\s+ALL\s+ON\s+FUNCTION\s+public\.{fn_name}\([^)]+\)\s+FROM\s+PUBLIC,\s*anon,\s*authenticated\s*;",
            sql,
            re.IGNORECASE,
        ), f"Missing REVOKE on {fn_name}"
        assert re.search(
            rf"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+public\.{fn_name}\([^)]+\)\s+TO\s+service_role\s*;",
            sql,
            re.IGNORECASE,
        ), f"Missing GRANT service_role on {fn_name}"

    # 4. Specific business edge-case invariants inside RPC bodies
    assert "delete_day_ai_review" in sql
    assert "daily_locations" in sql
    assert "gen_random_uuid()" in sql
    assert "p_day < 0" in sql


def test_poc_supabase_client_uses_threadsafe_http11_pool_and_12_thread_stress():
    """PoC 2: main.py & deps.py MUST build Supabase client with http2=False httpx.Client,
    warm up .postgrest on startup, close supabase_http_client on shutdown, and survive 12-thread RPC concurrency."""
    import main as main_mod
    import utils.deps as deps_mod

    main_src = inspect.getsource(main_mod.lifespan)
    deps_src = inspect.getsource(deps_mod)

    assert "supabase_http_client" in main_src, "lifespan must track and close app.state.supabase_http_client"
    assert "http2=False" in deps_src or "http2=False" in main_src, "Supabase httpx.Client must set http2=False"
    assert "postgrest" in deps_src or "postgrest" in main_src, "Supabase client must warm up .postgrest on init thread"
    assert hasattr(deps_mod, "create_threadsafe_supabase_client"), "deps.py must expose create_threadsafe_supabase_client"

    # Real 12-thread stress test with httpx.Client(http2=False) + supabase-py create_client
    call_counter = {"n": 0}
    counter_lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        with counter_lock:
            call_counter["n"] += 1
        return httpx.Response(200, json={"status": "ok"})

    http_client = httpx.Client(
        http2=False,
        follow_redirects=True,
        timeout=httpx.Timeout(120.0, connect=10.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        transport=httpx.MockTransport(handler),
    )
    sb = create_client(
        "https://example.supabase.co",
        "sb_secret_threadsafe_test_key_123456",
        options=ClientOptions(httpx_client=http_client),
    )
    _ = sb.postgrest
    assert sb.postgrest.session is http_client

    errors = []

    def worker(worker_id: int):
        try:
            for step in range(5):
                res = sb.rpc("patch_trip_day_data_atomic", {"p_day": step, "w": worker_id}).execute()
                assert res.data == {"status": "ok"}
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    http_client.close()

    assert not errors, f"12-thread concurrent supabase.rpc failed: {errors}"
    assert call_counter["n"] == 60


@pytest.mark.asyncio
async def test_poc_cross_instance_concurrent_writes_zero_data_loss():
    """PoC 3: With in-process trip_lock DISABLED (simulating multi-instance Cloud Run),
    interleaved concurrent writes across all 6 endpoints MUST retain 100% of writes via atomic RPC."""
    store = _base_store()
    # Non-zero rmw_delay_sec guarantees Python RMW would race & drop updates if RPC wasn't used!
    db = AtomicFakeSupabase(store, rmw_delay_sec=0.04, rpc_delay_sec=0.005)

    @asynccontextmanager
    async def _noop_lock(_trip_id: str):
        yield

    current_uid = {"val": OWNER_ID}
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_verified_user] = lambda: current_uid["val"]
    app.dependency_overrides[get_gemini_key] = lambda: DUMMY_API_KEY

    try:
        transport = ASGITransport(app=app)
        with patch.object(trips_router, "trip_lock", _noop_lock), \
             patch.object(ai_router, "trip_lock", _noop_lock), \
             patch.object(ai_router, "call_extraction", AsyncMock(return_value="Day 1 AI Review OK")), \
             patch(
                 "services.geocode_service.verify_and_heal_itinerary_coords",
                 AsyncMock(
                     return_value=(
                         [{"lat": 35.01, "lng": 135.76}],
                         {
                             "1": {"name": "SHOULD_NOT_OVERWRITE_DAY1", "lat": 0.0, "lng": 0.0},
                             "4": {"name": "Kyoto Day 4", "lat": 35.01, "lng": 135.76},
                         },
                     )
                 ),
             ):
            async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
                # Use explicit per-request auth via dependency override switched cleanly via separate requests
                # Owner + Collab interleaved across all 6 content writers
                async def as_user(uid, coro_fn):
                    app.dependency_overrides[get_verified_user] = lambda u=uid: u
                    return await coro_fn()

                # Fire concurrent mutations (Owner & Collab separated via JWT tokens to avoid shared override race)
                from utils.deps import get_session_secret
                import jwt

                def auth_hdr(uid: str) -> dict:
                    tok = jwt.encode(
                        {
                            "sub": uid,
                            "iss": "tabiji-core",
                            "iat": int(time.time()),
                            "exp": int(time.time()) + 3600,
                            "type": "device_session",
                        },
                        get_session_secret(),
                        algorithm="HS256",
                    )
                    return {"Authorization": f"Bearer {tok}"}

                app.dependency_overrides.pop(get_verified_user, None)

                tasks = [
                    # 1. Collab updates Day 1 checklists (must preserve Owner's hidden private checklist!)
                    ac.patch(
                        f"/api/trips/{TRIP_ID}/day-data",
                        headers=auth_hdr(COLLAB_ID),
                        json={
                            "day": 1,
                            "day_checklists": {
                                "1": [
                                    {"id": "c-pub-1", "text": "Collab Public", "is_private": False},
                                    {"id": "c-priv-1", "text": "COLLAB_PRIV_CHK", "is_private": True},
                                ]
                            },
                        },
                    ),
                    # 2. Owner clears Day 0 checklist (day=0 support!)
                    ac.patch(
                        f"/api/trips/{TRIP_ID}/day-data",
                        headers=auth_hdr(OWNER_ID),
                        json={"day": 0, "day_checklists": {"0": []}},
                    ),
                    # 3. Owner updates Day 1 costs
                    ac.patch(
                        f"/api/trips/{TRIP_ID}/day-data",
                        headers=auth_hdr(OWNER_ID),
                        json={"day": 1, "day_costs": {"1": [{"item": "Shinkansen", "amount": "14000"}]}},
                    ),
                    # 4. Collab adds private credit card (must preserve Owner's hidden private card!)
                    ac.patch(
                        f"/api/trips/{TRIP_ID}/info",
                        headers=auth_hdr(COLLAB_ID),
                        json={
                            "credit_cards": [
                                {"id": "pub-card", "name": "Shared Card", "is_public": True, "creator_id": "mem_masked"},
                                {"id": "collab-card", "name": "COLLAB_PRIV_CARD", "is_public": False},
                            ]
                        },
                    ),
                    # 5. Owner updates flight_info & hotel_info concurrently with Collab's credit_cards
                    ac.patch(
                        f"/api/trips/{TRIP_ID}/info",
                        headers=auth_hdr(OWNER_ID),
                        json={
                            "flight_info": {"outbound": [{"code": "NH852"}]},
                            "hotel_info": [{"name": "Park Hyatt Tokyo"}],
                        },
                    ),
                    # 6. Owner updates Day 2 location
                    ac.patch(
                        f"/api/trips/{TRIP_ID}/location",
                        headers=auth_hdr(OWNER_ID),
                        json={"day": 2, "name": "Kamakura", "lat": 35.3192, "lng": 139.5467},
                    ),
                    # 7. Owner generates Day 1 AI review
                    ac.post(
                        f"/api/ai/trips/{TRIP_ID}/days/1/ai-review?locale=zh",
                        headers={**auth_hdr(OWNER_ID), "X-Gemini-API-Key": DUMMY_API_KEY},
                    ),
                    # 8. Owner deletes Day 2 AI review
                    ac.delete(
                        f"/api/ai/trips/{TRIP_ID}/days/2/ai-review",
                        headers=auth_hdr(OWNER_ID),
                    ),
                    # 9. Owner imports Day 4 item + notes + daily_locations (extends end_date to 2026-12-04)
                    ac.post(
                        "/api/trips/import-to-trip",
                        headers=auth_hdr(OWNER_ID),
                        json={
                            "trip_id": TRIP_ID,
                            "items": [
                                {
                                    "day_number": 4,
                                    "time_slot": "10:00",
                                    "place_name": "Fushimi Inari",
                                    "category": "sightseeing",
                                }
                            ],
                            "day_notes": {"4": ["Early morning hike"]},
                        },
                    ),
                ]
                responses = await asyncio.gather(*tasks)

        for idx, resp in enumerate(responses):
            assert resp.status_code == 200, f"Task #{idx + 1} failed: {resp.status_code} {resp.text}"

        # Assert RPC was actually invoked for ALL 9 concurrent writes!
        rpc_names = [name for name, _ in db.rpc_calls]
        assert "patch_trip_day_data_atomic" in rpc_names
        assert "patch_trip_info_atomic" in rpc_names
        assert "merge_trip_import_content_atomic" in rpc_names
        assert len(db.rpc_calls) == 9

        trip = store["itineraries"][0]
        content = trip["content"]

        # 100% survival checks across every field
        chk_ids = {c["id"] for c in content["day_checklists"]["1"] if isinstance(c, dict)}
        assert {"own-chk", "c-pub-1", "c-priv-1"}.issubset(chk_ids)
        assert content["day_checklists"]["0"] == []
        assert content["day_costs"]["1"] == [{"item": "Shinkansen", "amount": "14000"}]

        cards_by_id = {c["id"]: c for c in content["credit_cards"]}
        assert {"pub-card", "own-priv-card", "collab-card"}.issubset(cards_by_id.keys())
        assert cards_by_id["pub-card"]["creator_id"] == OWNER_ID
        assert cards_by_id["collab-card"]["creator_id"] == COLLAB_ID

        assert trip["flight_info"] == {"outbound": [{"code": "NH852"}]}
        assert trip["hotel_info"] == [{"name": "Park Hyatt Tokyo"}]
        assert content["flight_info"] == {"outbound": [{"code": "NH852"}]}
        assert content["hotel_info"] == [{"name": "Park Hyatt Tokyo"}]

        # Existing Day 1 location preserved (NOT overwritten by import), Day 2 & Day 4 added
        assert content["daily_locations"]["1"]["name"] == "Tokyo Existing"
        assert content["daily_locations"]["2"]["name"] == "Kamakura"
        assert content["daily_locations"]["4"]["name"] == "Kyoto Day 4"

        # AI reviews: Day 1 created, Day 2 explicitly deleted
        assert content["day_ai_reviews"]["1"] == "Day 1 AI Review OK"
        assert "2" not in content["day_ai_reviews"]

        # Import notes + non-shrinking end_date extended from 2026-12-02 -> 2026-12-04
        assert content["day_notes"]["4"] == ["Early morning hike"]
        assert trip["end_date"] == "2026-12-04"
    finally:
        app.dependency_overrides.clear()


def test_poc_non_uuid_trip_id_precheck_blocks_22p02_without_hitting_rpc():
    """PoC 4: Invalid trip_id UUID MUST return 403 (member endpoints) or 404 (creator-bypass endpoints)
    BEFORE calling supabase.rpc, preventing Postgres 22P02 -> 500."""
    store = _base_store()
    db = AtomicFakeSupabase(store, strict_uuid=True)
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_verified_user] = lambda: OWNER_ID
    app.dependency_overrides[get_gemini_key] = lambda: DUMMY_API_KEY
    try:
        client = TestClient(app)
        assert client.patch("/api/trips/not-a-uuid/day-data", json={"day": 1}).status_code == 403
        assert client.patch("/api/trips/not-a-uuid/info", json={"credit_cards": []}).status_code == 403
        assert client.patch("/api/trips/not-a-uuid/location", json={"day": 1, "name": "X", "lat": 1.0, "lng": 1.0}).status_code == 403

        assert client.post("/api/trips/import-to-trip", json={"trip_id": "not-a-uuid", "items": []}).status_code == 404
        assert client.post("/api/ai/trips/not-a-uuid/days/1/ai-review").status_code == 404
        assert client.delete("/api/ai/trips/not-a-uuid/days/1/ai-review").status_code == 404
        assert len(db.rpc_calls) == 0, "Invalid UUID must never invoke Postgres RPC"
    finally:
        app.dependency_overrides.clear()


def test_poc_lock_timeout_55p03_deadlock_40p01_retry_and_409_conflict():
    """PoC 5: 55P03 / 40P01 retries once with short jitter backoff and returns 409 Conflict if still locked."""
    store = _base_store()
    db = AtomicFakeSupabase(store)
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_verified_user] = lambda: OWNER_ID
    try:
        client = TestClient(app)

        # Case A: Single transient 55P03 -> retries once and succeeds (200)
        db.rpc_error_queue = [APIError({"code": "55P03", "message": "canceling statement due to lock timeout"})]
        r_retry_ok = client.patch(
            f"/api/trips/{TRIP_ID}/day-data",
            json={"day": 1, "day_notes": {"1": ["Retry succeeded"]}},
        )
        assert r_retry_ok.status_code == 200
        assert len(db.rpc_calls) == 2

        # Case B: Persistent 55P03 -> 409 Conflict
        db.rpc_calls.clear()
        db.rpc_error_queue = [
            APIError({"code": "55P03", "message": "lock timeout"}),
            APIError({"code": "55P03", "message": "lock timeout"}),
        ]
        r_409_lock = client.patch(f"/api/trips/{TRIP_ID}/info", json={"flight_info": {"outbound": []}})
        assert r_409_lock.status_code == 409
        assert len(db.rpc_calls) == 2

        # Case C: Persistent 40P01 deadlock -> 409 Conflict
        db.rpc_calls.clear()
        db.rpc_error_queue = [
            APIError({"code": "40P01", "message": "deadlock detected"}),
            APIError({"code": "40P01", "message": "deadlock detected"}),
        ]
        r_409_deadlock = client.patch(
            f"/api/trips/{TRIP_ID}/location",
            json={"day": 1, "name": "Tokyo", "lat": 35.68, "lng": 139.76},
        )
        assert r_409_deadlock.status_code == 409
        assert len(db.rpc_calls) == 2
    finally:
        app.dependency_overrides.clear()


def test_poc_pgrst202_fallback_kill_switch_and_fail_closed_info_500_sanitization(monkeypatch):
    """PoC 6: PGRST202 & ENABLE_ATOMIC_TRIP_RPC=0 fall back cleanly; unexpected errors fail closed
    and PATCH /info MUST NOT leak raw exception text (fixing trips.py:L1795)."""
    store = _base_store()
    db = AtomicFakeSupabase(store)
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_verified_user] = lambda: OWNER_ID
    try:
        client = TestClient(app)

        # 1. PGRST202 falls back to Python RMW cleanly
        db.rpc_error_queue = [APIError({"code": "PGRST202", "message": "Could not find the function"})]
        r_pgrst = client.patch(f"/api/trips/{TRIP_ID}/info", json={"hotel_info": [{"name": "Fallback Hotel"}]})
        assert r_pgrst.status_code == 200
        assert store["itineraries"][0]["hotel_info"] == [{"name": "Fallback Hotel"}]

        # 2. Kill-switch ENABLE_ATOMIC_TRIP_RPC=0 skips RPC completely
        db.rpc_calls.clear()
        monkeypatch.setenv("ENABLE_ATOMIC_TRIP_RPC", "0")
        r_ks = client.patch(f"/api/trips/{TRIP_ID}/day-data", json={"day": 1, "day_notes": {"1": ["KillSwitch"]}})
        assert r_ks.status_code == 200
        assert len(db.rpc_calls) == 0
        monkeypatch.delenv("ENABLE_ATOMIC_TRIP_RPC", raising=False)

        # 3. Unexpected DB error fails closed (500) and NEVER leaks raw secret/DSN in PATCH /info
        db.rpc_error_queue = [RuntimeError("SECRET_PG_DSN_LEAK=postgres://admin:pwd@internal:5432/db")]
        r_500 = client.patch(f"/api/trips/{TRIP_ID}/info", json={"flight_info": {"outbound": []}})
        assert r_500.status_code == 500
        assert "SECRET_PG_DSN_LEAK" not in r_500.text
        assert "postgres://" not in r_500.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_poc_rpc_executes_off_event_loop_via_run_in_threadpool():
    """PoC 7: Blocking Supabase RPC call runs in worker threadpool and never blocks the asyncio event loop."""
    store = _base_store()
    db = AtomicFakeSupabase(store, rpc_delay_sec=0.08)
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_verified_user] = lambda: OWNER_ID
    main_thread_id = threading.get_ident()
    ticks = 0

    async def heartbeat():
        nonlocal ticks
        for _ in range(4):
            await asyncio.sleep(0.015)
            ticks += 1

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            resp, _ = await asyncio.gather(
                ac.patch(f"/api/trips/{TRIP_ID}/day-data", json={"day": 1, "day_notes": {"1": ["NonBlocking"]}}),
                heartbeat(),
            )
        assert resp.status_code == 200
        assert len(db.rpc_threads) == 1
        assert db.rpc_threads[0] != main_thread_id, "RPC MUST run off the event loop via run_in_threadpool"
        assert ticks >= 2, f"Event loop was blocked during RPC execution (ticks={ticks})"
    finally:
        app.dependency_overrides.clear()


def test_poc_edge_cases_null_clear_negative_day_and_non_shrinking_end_date():
    """PoC 8: Explicit null clears flight/hotel to SQL NULL; day < 0 -> 400; non-shrinking end_date preserved."""
    store = _base_store()
    store["itineraries"][0]["end_date"] = "2026-12-06"  # 6-day trip
    db = AtomicFakeSupabase(store)
    app.dependency_overrides[get_supabase] = lambda: db
    app.dependency_overrides[get_verified_user] = lambda: OWNER_ID
    try:
        client = TestClient(app)

        # 1. Explicit JSON null clears flight_info & hotel_info
        r_clear = client.patch(f"/api/trips/{TRIP_ID}/info", json={"flight_info": None, "hotel_info": None})
        assert r_clear.status_code == 200
        assert store["itineraries"][0]["flight_info"] is None
        assert store["itineraries"][0]["hotel_info"] is None
        assert store["itineraries"][0]["content"]["flight_info"] is None
        assert store["itineraries"][0]["content"]["hotel_info"] is None

        # 2. Negative day rejected cleanly with 400
        r_neg = client.patch(f"/api/trips/{TRIP_ID}/day-data", json={"day": -1, "day_notes": {"-1": []}})
        assert r_neg.status_code == 400

        # 3. Importing Day 2 into a 6-day trip MUST NOT shrink end_date
        with patch(
            "services.geocode_service.verify_and_heal_itinerary_coords",
            AsyncMock(return_value=([{"lat": 35.68, "lng": 139.76}], {})),
        ):
            r_imp = client.post(
                "/api/trips/import-to-trip",
                json={
                    "trip_id": TRIP_ID,
                    "items": [{"day_number": 2, "time_slot": "11:00", "place_name": "Ueno", "category": "sightseeing"}],
                },
            )
        assert r_imp.status_code == 200
        assert store["itineraries"][0]["end_date"] == "2026-12-06"

        # 4. Unauthorized stranger gets 403 on member endpoints & creator-bypass endpoints
        app.dependency_overrides[get_verified_user] = lambda: STRANGER_ID
        assert client.patch(f"/api/trips/{TRIP_ID}/day-data", json={"day": 1}).status_code == 403
        assert client.patch(f"/api/trips/{TRIP_ID}/info", json={"credit_cards": []}).status_code == 403
        assert client.delete(f"/api/ai/trips/{TRIP_ID}/days/1/ai-review").status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_poc_dirty_boolean_desync_duplicate_card_ids_and_non_array_import_privacy_wipe(monkeypatch):
    """PoC 9 (Adversarial Review Round 2):
    1. Dirty non-boolean is_public='true' / is_private='true' MUST be canonicalized to boolean False
       in both SQL DDL and Python helpers so SQL/Python never desync (blocks poison card cloning & ghost items).
    2. Duplicate card IDs in submitted credit_cards MUST be deduplicated/re-minted (unique IDs invariant)
       in both SQL DDL (v_seen_ids) and Python helpers.
    3. Non-array day payloads in import-to-trip (e.g. day_checklists: {'1': 'wipe'}) MUST NOT overwrite
       existing arrays or destroy Owner's hidden private items in either SQL DDL or Python fallback.
    """
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    # 1. Static SQL DDL guards for all 3 fixes
    info_fn = re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\.patch_trip_info_atomic.*?\$function\$;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert info_fn is not None
    info_body = info_fn.group(0)
    assert "v_seen_ids" in info_body, "patch_trip_info_atomic must track v_seen_ids to prevent duplicate submitted card IDs"
    assert "jsonb_build_object('is_public', false)" in info_body or "jsonb_build_object('creator_id', v_uid, 'is_public'" in info_body, (
        "patch_trip_info_atomic must canonicalize non-boolean is_public to JSON boolean"
    )

    day_fn = re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\.patch_trip_day_data_atomic.*?\$function\$;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert day_fn is not None
    assert "jsonb_build_object('is_private', false)" in day_fn.group(0), (
        "patch_trip_day_data_atomic must canonicalize non-boolean is_private to JSON boolean false"
    )

    import_fn = re.search(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+public\.merge_trip_import_content_atomic.*?\$function\$;",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert import_fn is not None
    import_body = import_fn.group(0)
    assert "jsonb_build_object('is_private', false)" in import_body, (
        "merge_trip_import_content_atomic must canonicalize non-boolean is_private to JSON boolean false"
    )
    # Must NOT blindly overwrite existing privacy-bearing day arrays when imported day value is non-array
    privacy_loop = import_body.split("FOREACH v_field IN ARRAY ARRAY['day_costs', 'day_tickets', 'day_checklists']")[1].split("END LOOP;")[0]
    assert "ELSE\n                    v_submap := v_submap || jsonb_build_object(v_k, v_val);" not in privacy_loop, (
        "merge_trip_import_content_atomic must NOT overwrite existing day arrays with non-array import values"
    )

    # 2. Runtime Python helper & endpoint verification (SQL/Python strict boolean parity)
    assert trips_router._is_card_visible_to_user(
        {"id": "poison-1", "name": "Bomb", "is_public": "true", "creator_id": COLLAB_ID},
        OWNER_ID,
        True,
    ) is False, "Dirty string is_public='true' must NOT be treated as public by Python reader"

    assert trips_router._is_day_item_visible_to_user(
        {"id": "ghost-1", "text": "Ghost", "is_private": "true"},
        COLLAB_ID,
        False,
    ) is True, "Dirty string is_private='true' must NOT be treated as Owner's legacy private item"

    merged_cards = trips_router._merge_cards_preserving_hidden_private(
        [{"id": "pub-card", "name": "Owner Pub", "is_public": True, "creator_id": OWNER_ID}],
        [
            {"id": "poison-1", "name": "Bomb", "is_public": "true"},
            {"id": "dup-1", "name": "Dup A", "is_public": True},
            {"id": "dup-1", "name": "Dup B", "is_public": False},
            {"id": "pub-card", "name": "Owner Pub", "is_public": True},
            {"id": "pub-card", "name": "Owner Pub Clone Attempt", "is_public": False},
        ],
        COLLAB_ID,
        False,
    )
    ids = [c["id"] for c in merged_cards]
    assert len(ids) == len(set(ids)), f"Duplicate card IDs survived merge: {ids}"
    poison = next(c for c in merged_cards if c["name"] == "Bomb")
    assert poison["is_public"] is False
    owner_pub = next(c for c in merged_cards if c["id"] == "pub-card")
    assert owner_pub["creator_id"] == OWNER_ID and owner_pub["is_public"] is True

    merged_items = trips_router._merge_day_items_preserving_hidden_private(
        [],
        [{"id": "ghost-1", "text": "Ghost", "is_private": "true", "private_owner_id": OWNER_ID}],
        COLLAB_ID,
        False,
    )
    assert merged_items[0]["is_private"] is False
    assert "private_owner_id" not in merged_items[0]

    # 3. Non-array import-to-trip payload MUST NOT wipe Owner's hidden private checklist on Day 1
    #    (tested on BOTH RPC path and legacy Python RMW fallback path)
    for enable_rpc in ("1", "0"):
        store = _base_store()
        db = AtomicFakeSupabase(store)
        def _get_db():
            return db
        app.dependency_overrides[get_supabase] = _get_db
        app.dependency_overrides[get_verified_user] = lambda: COLLAB_ID
        monkeypatch.setenv("ENABLE_ATOMIC_TRIP_RPC", enable_rpc)
        try:
            with patch(
                "services.geocode_service.verify_and_heal_itinerary_coords",
                AsyncMock(return_value=([], {})),
            ):
                client = TestClient(app)
                r = client.post(
                    "/api/trips/import-to-trip",
                    json={
                        "trip_id": TRIP_ID,
                        "items": [],
                        "day_checklists": {"1": "WIPE_ATTEMPT"},
                        "day_costs": {"1": None},
                        "day_notes": {"1": "NOT_A_LIST"},
                    },
                )
            assert r.status_code == 200
            day1_chk = store["itineraries"][0]["content"]["day_checklists"]["1"]
            assert isinstance(day1_chk, list), f"enable_rpc={enable_rpc}: non-array import wiped day_checklists!"
            assert any(isinstance(x, dict) and x.get("id") == "own-chk" for x in day1_chk), (
                f"enable_rpc={enable_rpc}: Owner's hidden private checklist was wiped!"
            )
        finally:
            monkeypatch.delenv("ENABLE_ATOMIC_TRIP_RPC", raising=False)
            app.dependency_overrides.clear()
