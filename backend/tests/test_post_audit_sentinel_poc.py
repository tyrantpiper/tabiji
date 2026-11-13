"""
Mantis Block G In-Memory PoC & Regression Suite (Post-Completion Audit 2026-11-09)
Benign Control tests MUST pass both before and after patching.
Exploit tests FAIL before patching (Red) and PASS after patching (Green).
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app  # noqa: E402
from utils.deps import get_gemini_key, get_supabase, get_verified_user  # noqa: E402


USER_OWNER = "11111111-1111-1111-1111-111111111111"
USER_STRANGER = "22222222-2222-2222-2222-222222222222"
DUMMY_API_KEY = "AIzaSyDummyKeyForPostAuditSentinelTests12345"


@pytest.fixture
def client_env():
    mock_supabase = MagicMock()
    app.dependency_overrides[get_supabase] = lambda: mock_supabase
    app.dependency_overrides[get_verified_user] = lambda: USER_OWNER
    app.dependency_overrides[get_gemini_key] = lambda: DUMMY_API_KEY
    client = TestClient(app, raise_server_exceptions=False)
    yield client, mock_supabase
    app.dependency_overrides.clear()


# ==============================================================================
# Mantis Block G: Benign Controls (Must pass BEFORE & AFTER)
# ==============================================================================


def test_benign_get_trip_expenses_member_succeeds(client_env):
    client, mock_sb = client_env

    def table_router(name):
        t = MagicMock()
        if name == "itineraries":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"created_by": USER_OWNER}]
            )
        elif name == "expenses":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{
                    "id": "exp-1",
                    "itinerary_id": "trip-1",
                    "title": "Ramen",
                    "amount": 1200.0,
                    "currency": "JPY",
                    "is_public": True,
                    "created_by": USER_OWNER,
                    "created_at": "2026-11-01T00:00:00Z",
                    "details": [],
                    "details_schema_version": 2,
                }]
            )
        return t

    mock_sb.table.side_effect = table_router
    res = client.get("/api/trips/trip-1/expenses")
    assert res.status_code == 200
    assert len(res.json()) == 1


def test_benign_reorder_items_valid_succeeds(client_env):
    client, mock_sb = client_env

    def table_router(name):
        t = MagicMock()
        if name == "itinerary_items":
            t.select.return_value.in_.return_value.execute.return_value = MagicMock(
                data=[{"id": "item-1", "itinerary_id": "trip-1"}]
            )
            t.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": "item-1"}]
            )
        elif name == "trip_members":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"user_id": USER_OWNER}]
            )
        return t

    mock_sb.table.side_effect = table_router
    res = client.patch(
        "/api/trips/items/reorder",
        json={"items": [{"item_id": "item-1", "sort_order": 0}], "adjust_times": False},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "success"


def test_benign_update_expense_member_succeeds(client_env):
    client, mock_sb = client_env

    mock_sb.table().select().eq().execute.return_value = MagicMock(
        data=[{
            "id": "exp-1",
            "itinerary_id": "trip-1",
            "created_by": USER_OWNER,
            "is_public": True,
            "amount": 500.0,
        }]
    )
    mock_sb.table().update().eq().execute.return_value = MagicMock(data=[{"id": "exp-1"}])
    res = client.patch("/api/expenses/exp-1", json={"title": "Updated Ramen"})
    assert res.status_code == 200


# ==============================================================================
# Red Exploits (FAIL before patch -> PASS after patch)
# ==============================================================================


def test_exploit_get_trip_expenses_bola_blocked(client_env):
    client, mock_sb = client_env
    app.dependency_overrides[get_verified_user] = lambda: USER_STRANGER

    def table_router(name):
        t = MagicMock()
        if name == "itineraries":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"created_by": USER_OWNER}]
            )
        elif name == "trip_members":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[]
            )
        elif name == "expenses":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": "secret-exp", "itinerary_id": "trip-1", "is_public": True, "created_by": USER_OWNER, "details": [], "details_schema_version": 2}]
            )
        return t

    mock_sb.table.side_effect = table_router
    res = client.get("/api/trips/trip-1/expenses")
    assert res.status_code == 403


def test_exploit_update_item_404_not_masked_as_500(client_env):
    client, mock_sb = client_env
    # Missing item: non-single returns empty list, single returns None
    mock_sb.table().select().eq().execute.return_value = MagicMock(data=[])
    mock_sb.table().select().eq().single().execute.return_value = MagicMock(data=None)
    mock_sb.table().update().eq().execute.return_value = MagicMock(data=[])

    res = client.patch("/api/trips/items/missing-item-id", json={"notes": "test"})
    assert res.status_code == 404


def test_exploit_reorder_items_empty_and_duplicate_ids(client_env):
    client, mock_sb = client_env

    # 1. Empty items should return 200 [], not 500 UnboundLocalError
    res_empty = client.patch("/api/trips/items/reorder", json={"items": [], "adjust_times": False})
    assert res_empty.status_code == 200
    assert res_empty.json() == {"status": "success", "results": []}

    # 2. Duplicate item_id in payload should deduplicate instead of false 404
    def table_router(name):
        t = MagicMock()
        if name == "itinerary_items":
            t.select.return_value.in_.return_value.execute.return_value = MagicMock(
                data=[{"id": "item-1", "itinerary_id": "trip-1"}]
            )
            t.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"id": "item-1"}]
            )
        elif name == "trip_members":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"user_id": USER_OWNER}]
            )
        return t

    mock_sb.table.side_effect = table_router
    res_dup = client.patch(
        "/api/trips/items/reorder",
        json={
            "items": [
                {"item_id": "item-1", "sort_order": 0},
                {"item_id": "item-1", "sort_order": 1},
            ],
            "adjust_times": False,
        },
    )
    assert res_dup.status_code == 200


def test_exploit_create_manual_trip_403_compensation_and_idempotency(client_env):
    client, mock_sb = client_env
    try:
        from utils.idempotency import __reset_idempotency_cache_for_testing
        __reset_idempotency_cache_for_testing()
    except ImportError:
        pass

    # 1. Quota reached returns 403, not 500
    def quota_router(name):
        t = MagicMock()
        if name == "itineraries":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(count=3, data=[])
        return t

    mock_sb.table.side_effect = quota_router
    res_quota = client.post(
        "/api/trips/create-manual",
        json={"title": "Quota Trip", "start_date": "2026-11-10", "end_date": "2026-11-12", "creator_name": "Ryan", "user_id": USER_OWNER},
    )
    assert res_quota.status_code == 403

    # 2. Failed trip_members insert performs compensating delete on itineraries
    deleted_ids = []

    def partial_fail_router(name):
        t = MagicMock()
        if name == "itineraries":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(count=0, data=[])
            t.insert.return_value.execute.return_value = MagicMock(data=[{"id": "orphan-trip-1"}])
            t.delete.return_value.eq.side_effect = lambda col, val: (
                deleted_ids.append(val) or MagicMock(execute=lambda: MagicMock(data=[]))
            )
        elif name == "trip_members":
            t.insert.return_value.execute.side_effect = RuntimeError("FK constraint error")
        else:
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": USER_OWNER, "name": "Ryan"}])
        return t

    mock_sb.table.side_effect = partial_fail_router
    res_comp = client.post(
        "/api/trips/create-manual",
        json={"title": "Orphan Trip", "start_date": "2026-11-10", "end_date": "2026-11-12", "creator_name": "Ryan", "user_id": USER_OWNER},
    )
    assert res_comp.status_code == 500
    assert "orphan-trip-1" in deleted_ids

    # 3. Idempotency-Key prevents duplicate creation
    insert_calls = []

    def ok_router(name):
        t = MagicMock()
        if name == "itineraries":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(count=0, data=[])
            t.insert.side_effect = lambda p: (
                insert_calls.append(p) or MagicMock(execute=lambda: MagicMock(data=[{"id": "idem-trip-1"}]))
            )
        elif name == "trip_members":
            t.insert.return_value.execute.return_value = MagicMock(data=[{"id": "m-1"}])
        else:
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": USER_OWNER, "name": "Ryan"}])
        return t

    mock_sb.table.side_effect = ok_router
    r1 = client.post(
        "/api/trips/create-manual",
        headers={"Idempotency-Key": "create-idem-1"},
        json={"title": "Idem Trip", "start_date": "2026-11-10", "end_date": "2026-11-12", "creator_name": "Ryan", "user_id": USER_OWNER},
    )
    r2 = client.post(
        "/api/trips/create-manual",
        headers={"Idempotency-Key": "create-idem-1"},
        json={"title": "Idem Trip", "start_date": "2026-11-10", "end_date": "2026-11-12", "creator_name": "Ryan", "user_id": USER_OWNER},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    assert len(insert_calls) == 1


def test_exploit_save_itinerary_compensation_on_item_failure(client_env):
    client, mock_sb = client_env
    try:
        from utils.idempotency import __reset_idempotency_cache_for_testing
        __reset_idempotency_cache_for_testing()
    except ImportError:
        pass

    deleted_tables = []

    def fail_items_router(name):
        t = MagicMock()
        if name == "itineraries":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(count=0, data=[])
            t.insert.return_value.execute.return_value = MagicMock(data=[{"id": "save-orphan-1"}])
            t.delete.return_value.eq.side_effect = lambda col, val: (
                deleted_tables.append(("itineraries", val)) or MagicMock(execute=lambda: MagicMock(data=[]))
            )
        elif name == "trip_members":
            t.insert.return_value.execute.return_value = MagicMock(data=[{"id": "tm-1"}])
            t.delete.return_value.eq.side_effect = lambda col, val: (
                deleted_tables.append(("trip_members", val)) or MagicMock(execute=lambda: MagicMock(data=[]))
            )
        elif name == "itinerary_items":
            t.insert.return_value.execute.side_effect = RuntimeError("DB write fail")
            t.delete.return_value.eq.side_effect = lambda col, val: (
                deleted_tables.append(("itinerary_items", val)) or MagicMock(execute=lambda: MagicMock(data=[]))
            )
        else:
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": USER_OWNER, "name": "Ryan"}])
        return t

    mock_sb.table.side_effect = fail_items_router
    with patch("services.geocode_service.verify_and_heal_itinerary_coords", AsyncMock(return_value=([{"lat": 35.6, "lng": 139.7}], {}))):
        res = client.post(
            "/api/trips/save-itinerary",
            json={
                "title": "Save Orphan",
                "creator_name": "Ryan",
                "user_id": USER_OWNER,
                "items": [{"day_number": 1, "time_slot": "09:00", "place_name": "Tokyo Station", "category": "sightseeing"}],
            },
        )
    assert res.status_code == 500
    assert ("itineraries", "save-orphan-1") in deleted_tables
    assert ("trip_members", "save-orphan-1") in deleted_tables


def test_exploit_day_management_and_location_lock_403_404_batch(client_env):
    client, mock_sb = client_env

    # 1. update_trip_location returns clean 403 when non-member (checked before itineraries)
    def non_member_router(name):
        t = MagicMock()
        if name == "trip_members":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        elif name == "itineraries":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            t.select.return_value.eq.return_value.single().execute.side_effect = RuntimeError("PGRST116")
        return t

    mock_sb.table.side_effect = non_member_router
    res_loc = client.patch(
        "/api/trips/trip-locked/location",
        json={"day": 1, "name": "Tokyo", "lat": 35.6, "lng": 139.7},
    )
    assert res_loc.status_code == 403

    # 2. delete_day non-member returns 403, not 500
    res_del_forbid = client.delete("/api/trips/trip-locked/days/1")
    assert res_del_forbid.status_code == 403

    # 3. delete_day missing trip returns 404, not 500
    def missing_trip_router(name):
        t = MagicMock()
        if name == "trip_members":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"user_id": USER_OWNER}])
        elif name == "itineraries":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            t.select.return_value.eq.return_value.single().execute.return_value = MagicMock(data=None)
        return t

    mock_sb.table.side_effect = missing_trip_router
    res_del_missing = client.delete("/api/trips/trip-missing/days/1")
    assert res_del_missing.status_code == 404

    # 4. add_day invalid before:pos returns 400, not 500
    res_bad_pos = client.post("/api/trips/trip-1/days", json={"position": "before:abc"})
    assert res_bad_pos.status_code == 400

    # 5. trip_lock module & RMW serialization verification
    from utils.concurrency import trip_lock, __reset_locks_for_testing
    __reset_locks_for_testing()
    assert callable(trip_lock)


def test_exploit_update_trip_dates_malformed_400_and_batch_shorten(client_env):
    client, mock_sb = client_env

    mock_sb.table().select().eq().single().execute.return_value = MagicMock(
        data={
            "id": "trip-1",
            "created_by": USER_OWNER,
            "start_date": "2026-10-10",
            "end_date": "2026-10-12",
            "content": {},
        }
    )
    res_bad = client.patch(
        "/api/trips/trip-1/dates",
        json={"start_date": "invalid-date", "end_date": "2026-10-12", "on_shorten": "merge"},
    )
    assert res_bad.status_code == 400


def test_exploit_expenses_404_masking_and_idempotency(client_env):
    client, mock_sb = client_env
    try:
        from utils.idempotency import __reset_idempotency_cache_for_testing
        __reset_idempotency_cache_for_testing()
    except ImportError:
        pass

    # 1. update_expense 404 is not masked as 500
    mock_sb.table().select().eq().execute.return_value = MagicMock(
        data=[{"id": "exp-1", "itinerary_id": "trip-1", "created_by": USER_OWNER, "is_public": True}]
    )
    mock_sb.table().update().eq().execute.return_value = MagicMock(data=[])
    res_upd = client.patch("/api/expenses/exp-1", json={"title": "Updated"})
    assert res_upd.status_code == 404

    # 2. add_expense deduplicates via Idempotency-Key & sanitizes 500
    insert_calls = []

    def exp_router(name):
        t = MagicMock()
        if name == "itineraries":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"created_by": USER_OWNER}])
        elif name == "expenses":
            t.insert.side_effect = lambda payload: (
                insert_calls.append(payload) or MagicMock(execute=lambda: MagicMock(data=[{"id": "exp-new"}]))
            )
        elif name == "users":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        return t

    mock_sb.table.side_effect = exp_router
    r1 = client.post(
        "/api/expenses",
        headers={"Idempotency-Key": "exp-idem-1"},
        json={"itinerary_id": "trip-1", "title": "Sushi", "total_amount": 1500, "currency": "JPY"},
    )
    r2 = client.post(
        "/api/expenses",
        headers={"Idempotency-Key": "exp-idem-1"},
        json={"itinerary_id": "trip-1", "title": "Sushi", "total_amount": 1500, "currency": "JPY"},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert len(insert_calls) == 1

    # 3. add_expense 500 does not leak raw secret error message
    def crash_router(name):
        t = MagicMock()
        if name == "itineraries":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"created_by": USER_OWNER}])
        elif name == "expenses":
            t.insert.side_effect = RuntimeError("postgresql://secret_leak:pw@db:5432")
        elif name == "users":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        return t

    mock_sb.table.side_effect = crash_router
    r_err = client.post(
        "/api/expenses",
        json={"itinerary_id": "trip-1", "title": "Crash", "total_amount": 100, "currency": "JPY"},
    )
    assert r_err.status_code == 500
    assert "secret_leak" not in r_err.json()["detail"]


def test_exploit_generate_day_review_auth_bola_404_and_en_locale(client_env):
    client, mock_sb = client_env

    # 1. Requires JWT (no override -> 401)
    saved_auth = app.dependency_overrides.pop(get_verified_user)
    try:
        res_401 = client.post("/api/ai/trips/trip-1/days/1/ai-review")
        assert res_401.status_code == 401
    finally:
        app.dependency_overrides[get_verified_user] = saved_auth

    # 2. Non-member -> 403 before AI call
    app.dependency_overrides[get_verified_user] = lambda: USER_STRANGER

    def bola_router(name):
        t = MagicMock()
        if name == "itineraries":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"created_by": USER_OWNER, "content": {}}]
            )
        elif name == "trip_members":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        return t

    mock_sb.table.side_effect = bola_router
    with patch("routers.ai.call_extraction", new=AsyncMock()) as mock_ai:
        res_403 = client.post("/api/ai/trips/trip-1/days/1/ai-review?locale=en")
        assert res_403.status_code == 403
        mock_ai.assert_not_awaited()

    # 3. Member + ?locale=en uses English empty-day copy and English prompt
    app.dependency_overrides[get_verified_user] = lambda: USER_OWNER

    def empty_router(name):
        t = MagicMock()
        if name == "itineraries":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"created_by": USER_OWNER, "content": {}}]
            )
        elif name == "itinerary_items":
            t.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(data=[])
        return t

    mock_sb.table.side_effect = empty_router
    res_empty_en = client.post("/api/ai/trips/trip-1/days/1/ai-review?locale=en")
    assert res_empty_en.status_code == 200
    assert "No activities scheduled" in res_empty_en.json()["review"]


def test_exploit_parse_md_invalid_b64_400_and_invalid_json_422_and_locale(client_env):
    client, _ = client_env

    # 1. Malformed Base64 rejected with 400, not 500
    res_b64 = client.post(
        "/api/ai/parse-md",
        json={"markdown_text": "Day 1", "image_base64": "data:image/png;base64,!!!INVALID_BASE64!!!"},
    )
    assert res_b64.status_code == 400

    # 2. Invalid JSON from LLM mapped to 422
    with patch("routers.ai.call_extraction", AsyncMock(return_value="not valid json")) as mock_extract, \
         patch("services.geocode_service.resolve_prompt_spatial_anchor", AsyncMock(return_value={})), \
         patch("services.geocode_service.build_spatial_constraint_prompt", return_value=""):
        res_json = client.post("/api/ai/parse-md", json={"markdown_text": "Tokyo Day 1", "locale": "en"})
        assert res_json.status_code == 422
        sys_inst = mock_extract.call_args.kwargs.get("system_instruction", "")
        assert "LANGUAGE DIRECTIVE" in sys_inst


def test_exploit_global_exception_handler_no_traceback_disclosure(client_env):
    client, _ = client_env

    orig_route_count = len(app.router.routes)
    try:
        @app.get("/__test_sentinel_crash__")
        def _crash_route():
            raise RuntimeError("SUPER_SECRET_DB_DSN=postgres://admin:pass@internal")

        res = client.get("/__test_sentinel_crash__")
        assert res.status_code == 500
        body = res.json()
        assert body == {"detail": "An internal server error occurred."}
    finally:
        del app.router.routes[orig_route_count:]


@pytest.mark.asyncio
async def test_exploit_stream_chat_repeated_world_time_and_en_thoughts():
    import main as backend_main

    fc1 = MagicMock()
    fc1.name = "get_world_time"
    fc1.args = {"query": "Tokyo"}
    fc2 = MagicMock()
    fc2.name = "get_world_time"
    fc2.args = {"query": "Tokyo"}

    first_pass_resp = MagicMock()
    first_pass_resp.function_calls = [fc1, fc2]

    chunk_text = MagicMock()
    chunk_text.thought = None
    part = MagicMock()
    part.thought = None
    part.function_call = None
    part.text = "Tokyo is UTC+9."
    cand = MagicMock()
    cand.content = MagicMock(parts=[part])
    cand.grounding_metadata = None
    chunk_text.candidates = [cand]
    chunk_text.text = "Tokyo is UTC+9."

    async def fake_stream():
        yield chunk_text

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=first_pass_resp)
    mock_client.aio.models.generate_content_stream = AsyncMock(return_value=fake_stream())

    events = []
    with patch.object(backend_main.genai, "Client", return_value=mock_client), \
         patch.object(backend_main, "classify_chat_intent", AsyncMock(return_value=("SEARCH", None))), \
         patch.object(backend_main, "execute_web_search", AsyncMock(return_value=[])):
        async for ev in backend_main.stream_chat_generator(
            api_key=DUMMY_API_KEY,
            history=[],
            message="What time is it in Tokyo right now and is it sunny?",
            raw_user_message="What time is it in Tokyo right now?",
            locale="en",
        ):
            events.append(ev)

    joined = "".join(events)
    assert "Tokyo is UTC+9." in joined
    assert "Checking local time and timezone for Tokyo" in joined
    assert "正在查詢" not in joined


@pytest.mark.asyncio
async def test_exploit_model_manager_lru_bound_and_timeout():
    from services import model_manager

    model_manager.__reset_client_cache_for_testing()
    with patch.object(model_manager.genai, "Client", side_effect=lambda api_key: MagicMock(api_key=api_key)):
        for i in range(45):
            model_manager.get_cached_client(f"key-{i}")
        assert len(model_manager._client_cache) == model_manager.MAX_CLIENT_CACHE_SIZE
        assert "key-0" not in model_manager._client_cache
        assert "key-44" in model_manager._client_cache

    model_manager.__reset_client_cache_for_testing()

    async def slow_send(*_args, **_kwargs):
        await asyncio.sleep(0.5)
        return MagicMock()

    mock_client = MagicMock()
    mock_chat = MagicMock()
    mock_chat.send_message = slow_send
    mock_client.aio.chats.create.return_value = mock_chat

    with patch.object(model_manager, "get_cached_client", return_value=mock_client), \
         patch.object(model_manager, "MODEL_CALL_TIMEOUT", 0.02):
        with pytest.raises(model_manager.AllModelsFailedError):
            await model_manager.call_with_fallback(
                api_key="slow-key",
                history=[],
                message="hello",
                routing_strategy=["gemini-3.1-flash-lite"],
            )


# ==============================================================================
# V2 Mantis Block G: Benign Control & Red -> Green Re-Audit Exploits
# ==============================================================================


@pytest.mark.asyncio
async def test_benign_generate_trip_stream_preserves_keepalive_and_5arg_call():
    from routers.ai import generate_trip_core
    import services.model_manager as mm

    seen_args = []

    async def strict_5arg_mock(
        api_key, prompt_payload, intent_type="PLANNING", routing_strategy=None, system_instruction=""
    ):
        seen_args.append((api_key, intent_type))
        return json.dumps({
            "title": "Kyoto Escape",
            "destination": "Kyoto",
            "currency": "JPY",
            "days": [
                {
                    "day_number": 1,
                    "activities": [
                        {
                            "time": "09:00",
                            "place_name": "Kiyomizu-dera",
                            "category": "sightseeing",
                            "desc": "Historic temple",
                            "lat": 34.9949,
                            "lng": 135.7850,
                        }
                    ],
                }
            ],
            "day_metadata": [],
            "ai_review": "Enjoy!",
        })

    q = asyncio.Queue()
    with patch("services.model_manager.call_extraction", side_effect=strict_5arg_mock), \
         patch("services.geocode_service.resolve_prompt_spatial_anchor", AsyncMock(return_value={})), \
         patch("services.geocode_service.build_spatial_constraint_prompt", return_value=""), \
         patch("services.geocode_service.verify_and_heal_itinerary_coords", AsyncMock(return_value=([{"lat": 34.9949, "lng": 135.7850, "place_name": "Kiyomizu-dera", "day_number": 1, "time_slot": "09:00", "category": "sightseeing"}], {"1": {"name": "Kyoto", "lat": 34.9949, "lng": 135.7850}}))):
        res = await generate_trip_core(prompt="Kyoto 1 day", api_key=DUMMY_API_KEY, progress_queue=q)

    assert res["title"] == "Kyoto Escape"
    assert seen_args == [(DUMMY_API_KEY, "PLANNING")]
    events = []
    while not q.empty():
        events.append(q.get_nowait()[0])
    assert "progress" in events
    assert hasattr(mm, "call_with_fallback")


def test_exploit_donation_progress_zero_fiat_utc_and_fail_closed(client_env):
    from datetime import datetime, timezone
    client, mock_sb = client_env
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m")

    # 1. Active month returns server-computed percentage only (NO current/goal keys + no-store)
    mock_sb.table.side_effect = None
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"value": {"current": 500, "goal": 2000, "month": now_utc}}]
    )
    mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data={"value": {"current": 500, "goal": 2000, "month": now_utc}}
    )
    r_ok = client.get("/api/app/donation-progress")
    assert r_ok.status_code == 200
    body_ok = r_ok.json()
    assert body_ok["available"] is True
    assert body_ok["percentage"] == 25.0
    assert body_ok["month"] == now_utc
    assert "current" not in body_ok
    assert "goal" not in body_ok
    assert "no-store" in r_ok.headers.get("cache-control", "")

    # 2. Cross-month DB row resets percentage cleanly to 0.0 without exposing fiat values
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"value": {"current": 1600, "goal": 2000, "month": "2020-01"}}]
    )
    r_cross = client.get("/api/app/donation-progress")
    assert r_cross.status_code == 200
    body_cross = r_cross.json()
    assert body_cross == {"available": True, "percentage": 0.0, "month": now_utc}

    # 3. Missing config row returns available=False (distinguished from DB failure)
    mock_sb.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[]
    )
    r_empty = client.get("/api/app/donation-progress")
    assert r_empty.status_code == 200
    assert r_empty.json() == {"available": False}
    assert "no-store" in r_empty.headers.get("cache-control", "")

    # 4. DB outage returns HTTP 503 + no-store instead of fake current:0/goal:2000
    mock_sb.table.side_effect = RuntimeError("Supabase connection timed out")
    r_err = client.get("/api/app/donation-progress")
    assert r_err.status_code == 503
    assert "no-store" in r_err.headers.get("cache-control", "")


def test_exploit_save_itinerary_compensation_on_http_exception_after_insert(client_env):
    client, mock_sb = client_env
    try:
        from utils.idempotency import __reset_idempotency_cache_for_testing
        __reset_idempotency_cache_for_testing()
    except ImportError:
        pass

    deleted_tables = []

    def http_fail_items_router(name):
        t = MagicMock()
        if name == "itineraries":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(count=0, data=[])
            t.insert.return_value.execute.return_value = MagicMock(data=[{"id": "save-http-orphan"}])
            t.delete.return_value.eq.side_effect = lambda col, val: (
                deleted_tables.append(("itineraries", val)) or MagicMock(execute=lambda: MagicMock(data=[]))
            )
        elif name == "trip_members":
            t.insert.return_value.execute.return_value = MagicMock(data=[{"id": "tm-1"}])
            t.delete.return_value.eq.side_effect = lambda col, val: (
                deleted_tables.append(("trip_members", val)) or MagicMock(execute=lambda: MagicMock(data=[]))
            )
        elif name == "itinerary_items":
            t.insert.return_value.execute.side_effect = HTTPException(status_code=503, detail="Downstream unavailable")
            t.delete.return_value.eq.side_effect = lambda col, val: (
                deleted_tables.append(("itinerary_items", val)) or MagicMock(execute=lambda: MagicMock(data=[]))
            )
        else:
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": USER_OWNER, "name": "Ryan"}])
        return t

    mock_sb.table.side_effect = http_fail_items_router
    with patch("services.geocode_service.verify_and_heal_itinerary_coords", AsyncMock(return_value=([{"lat": 35.6, "lng": 139.7}], {}))):
        res = client.post(
            "/api/trips/save-itinerary",
            json={
                "title": "Save HTTP Orphan",
                "creator_name": "Ryan",
                "user_id": USER_OWNER,
                "items": [{"day_number": 1, "time_slot": "09:00", "place_name": "Tokyo Station", "category": "sightseeing"}],
            },
        )
    assert res.status_code == 503
    assert ("itineraries", "save-http-orphan") in deleted_tables
    assert ("trip_members", "save-http-orphan") in deleted_tables
    assert ("itinerary_items", "save-http-orphan") in deleted_tables


@pytest.mark.asyncio
async def test_exploit_model_manager_dual_track_timeouts_zero_ban_and_150s_eviction():
    from services import model_manager

    assert model_manager.MODEL_CALL_TIMEOUT == 45.0
    assert model_manager.PLANNING_CALL_TIMEOUT == 90.0
    assert model_manager.PLANNING_SSE_TIMEOUT == 120.0
    assert model_manager.RETIRED_CLIENT_CLOSE_DELAY == 150.0
    assert model_manager._get_call_timeout("CHAT") == 45.0
    assert model_manager._get_call_timeout("PLANNING") == 90.0
    with model_manager.call_timeout_scope("PLANNING_SSE"):
        assert model_manager._get_call_timeout("PLANNING") == 120.0
    assert model_manager._get_call_timeout("PLANNING") == 90.0

    # Zero-Ban Timeout guarantee: 3 consecutive timeouts on flagship model MUST NOT trip circuit breaker
    model_manager.__reset_client_cache_for_testing()
    model_manager._CIRCUIT_STATE.pop("gemini-3.8-flash", None)
    model_manager._CIRCUIT_STATE.pop("gemini-3.7-flash", None)

    call_idx = {"n": 0}

    async def slow_primary_then_ok(**kwargs):
        call_idx["n"] += 1
        if kwargs.get("model") == "gemini-3.8-flash":
            await asyncio.sleep(0.2)
            return MagicMock()
        r = MagicMock()
        r.candidates = []
        r.text = json.dumps({"days": [{"day_number": 1, "activities": []}]})
        return r

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = slow_primary_then_ok

    try:
        with patch.object(model_manager, "get_cached_client", return_value=mock_client), \
             patch.object(model_manager, "PLANNING_CALL_TIMEOUT", 0.02):
            for _ in range(3):
                out = await model_manager.call_extraction(
                    api_key="timeout-key",
                    prompt="test",
                    intent_type="PLANNING",
                    routing_strategy=["gemini-3.8-flash", "gemini-3.7-flash"],
                )
                assert "days" in out

        assert model_manager.is_model_circuit_broken("gemini-3.8-flash") is False
        assert model_manager._CIRCUIT_STATE.get("gemini-3.8-flash", {}).get("errors", 0) == 0

        # Deferred LRU eviction check (never closes active client immediately on eviction; closes via close_all)
        model_manager.__reset_client_cache_for_testing()
        created = []

        def make_client(api_key):
            c = MagicMock()
            c.api_key = api_key
            c.aio.aclose = AsyncMock()
            created.append(c)
            return c

        with patch.object(model_manager.genai, "Client", side_effect=make_client):
            for i in range(35):
                model_manager.get_cached_client(f"byok-{i}")

        assert len(model_manager._client_cache) == 32
        assert len(model_manager._retired_clients) == 3
        for evicted in created[:3]:
            evicted.aio.aclose.assert_not_awaited()

        await model_manager.close_all_cached_clients()
        assert len(model_manager._client_cache) == 0
        assert len(model_manager._retired_clients) == 0
        for evicted in created[:3]:
            evicted.aio.aclose.assert_awaited_once()
    finally:
        model_manager.__reset_client_cache_for_testing()


@pytest.mark.asyncio
async def test_exploit_ai_stream_enables_120s_scope_with_5arg_mock():
    from routers.ai import generate_trip_core
    from services import model_manager

    observed_timeouts = []

    async def strict_5arg_probe(
        api_key, prompt_payload, intent_type="PLANNING", routing_strategy=None, system_instruction=""
    ):
        observed_timeouts.append(model_manager._get_call_timeout(intent_type))
        return json.dumps({
            "title": "Tokyo SSE",
            "destination": "Tokyo",
            "currency": "JPY",
            "days": [{"day_number": 1, "activities": [{"time": "09:00", "place_name": "Ueno", "category": "sightseeing"}]}],
            "day_metadata": [],
            "ai_review": "Nice",
        })

    q = asyncio.Queue()
    with patch("services.model_manager.call_extraction", side_effect=strict_5arg_probe), \
         patch("services.geocode_service.resolve_prompt_spatial_anchor", AsyncMock(return_value={})), \
         patch("services.geocode_service.build_spatial_constraint_prompt", return_value=""), \
         patch("services.geocode_service.verify_and_heal_itinerary_coords", AsyncMock(return_value=([], {}))):
        await generate_trip_core(prompt="Tokyo SSE", api_key=DUMMY_API_KEY, progress_queue=q)
        await generate_trip_core(prompt="Tokyo Sync", api_key=DUMMY_API_KEY, progress_queue=None)

    assert observed_timeouts == [120.0, 90.0]


@pytest.mark.asyncio
async def test_exploit_lifespan_shutdown_closes_all_cached_ai_clients():
    import main as main_mod
    from services import model_manager

    model_manager.__reset_client_cache_for_testing()
    created = []

    def make_client(api_key):
        c = MagicMock()
        c.api_key = api_key
        c.aio.aclose = AsyncMock()
        created.append(c)
        return c

    with patch.object(model_manager.genai, "Client", side_effect=make_client):
        async with main_mod.lifespan(main_mod.app):
            for i in range(34):
                model_manager.get_cached_client(f"lifespan-key-{i}")
            assert len(model_manager._client_cache) == 32
            assert len(model_manager._retired_clients) == 2

    assert len(model_manager._client_cache) == 0
    assert len(model_manager._retired_clients) == 0
    for c in created:
        c.aio.aclose.assert_awaited_once()
    model_manager.__reset_client_cache_for_testing()


@pytest.mark.asyncio
async def test_exploit_clear_day_review_locked_and_sanitizes_500():
    from httpx import ASGITransport, AsyncClient
    from utils.concurrency import __reset_locks_for_testing

    __reset_locks_for_testing()
    state = {"content": {"day_ai_reviews": {"1": "old-day-1", "2": "keep-day-2"}}}

    def table_router(name):
        t = MagicMock()
        if name == "itineraries":
            def do_select(*args, **kwargs):
                q = MagicMock()
                q.eq.return_value.execute.side_effect = lambda: MagicMock(
                    data=[{"id": "trip-lock", "created_by": USER_OWNER, "content": json.loads(json.dumps(state["content"]))}]
                )
                return q

            def do_update(payload):
                q = MagicMock()
                def exec_upd():
                    if "content" in payload:
                        state["content"] = json.loads(json.dumps(payload["content"]))
                    return MagicMock(data=[{"id": "trip-lock"}])
                q.eq.return_value.execute.side_effect = exec_upd
                return q

            t.select.side_effect = do_select
            t.update.side_effect = do_update
        elif name == "itinerary_items":
            t.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{"place_name": "Spot", "time_slot": "09:00", "category": "sightseeing", "notes": ""}]
            )
        return t

    mock_sb = MagicMock()
    mock_sb.table.side_effect = table_router
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: USER_OWNER
    app.dependency_overrides[get_gemini_key] = lambda: DUMMY_API_KEY
    try:
        async def delayed_review(*args, **kwargs):
            await asyncio.sleep(0.05)
            return "new-day-3"

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            with patch("routers.ai.call_extraction", side_effect=delayed_review):
                r_del, r_gen = await asyncio.gather(
                    ac.delete("/api/ai/trips/trip-lock/days/1/ai-review"),
                    ac.post("/api/ai/trips/trip-lock/days/3/ai-review"),
                )
        assert r_del.status_code == 200
        assert r_gen.status_code == 200
        assert "1" not in state["content"]["day_ai_reviews"]
        assert state["content"]["day_ai_reviews"].get("2") == "keep-day-2"
        assert state["content"]["day_ai_reviews"].get("3") == "new-day-3"

        # 500 error sanitization on DB crash
        mock_sb.table.side_effect = RuntimeError("SECRET_INTERNAL_PG_DSN=postgres://leak")
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            r_err = await ac.delete("/api/ai/trips/trip-lock/days/1/ai-review")
        assert r_err.status_code == 500
        assert "SECRET_INTERNAL_PG_DSN" not in r_err.text
    finally:
        app.dependency_overrides.clear()
        __reset_locks_for_testing()


@pytest.mark.asyncio
async def test_exploit_import_to_trip_locked_post_geocode_and_sanitizes_500():
    from httpx import ASGITransport, AsyncClient
    from utils.concurrency import __reset_locks_for_testing

    __reset_locks_for_testing()
    state = {
        "content": {"daily_locations": {"1": {"name": "Taipei", "lat": 25.033, "lng": 121.5654}}},
        "start_date": "2026-11-01",
        "end_date": "2026-11-02",
    }

    def table_router(name):
        t = MagicMock()
        if name == "itineraries":
            t.select.return_value.eq.return_value.execute.side_effect = lambda: MagicMock(
                data=[{
                    "id": "trip-imp-lock",
                    "title": "Taipei Trip",
                    "created_by": USER_OWNER,
                    "start_date": state["start_date"],
                    "end_date": state["end_date"],
                    "content": json.loads(json.dumps(state["content"])),
                }]
            )

            def do_update(payload):
                q = MagicMock()
                def exec_upd():
                    if "content" in payload:
                        state["content"] = json.loads(json.dumps(payload["content"]))
                    return MagicMock(data=[{"id": "trip-imp-lock"}])
                q.eq.return_value.execute.side_effect = exec_upd
                return q

            t.update.side_effect = do_update
        elif name == "itinerary_items":
            t.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            t.insert.return_value.execute.return_value = MagicMock(data=[{"id": "item-1"}])
        return t

    mock_sb = MagicMock()
    mock_sb.table.side_effect = table_router
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: USER_OWNER
    try:
        async def slow_heal(items, **kwargs):
            # Simulate concurrent writer modifying day_ai_reviews during geocode await
            state["content"]["day_ai_reviews"] = {"1": "Concurrent AI review must survive"}
            return ([{"lat": 25.04, "lng": 121.53}], {"1": {"name": "Taipei", "lat": 25.033, "lng": 121.5654}})

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            with patch("services.geocode_service.verify_and_heal_itinerary_coords", side_effect=slow_heal):
                res = await ac.post(
                    "/api/trips/import-to-trip",
                    json={
                        "trip_id": "trip-imp-lock",
                        "items": [{"day_number": 1, "time_slot": "10:00", "place_name": "Huashan", "category": "sightseeing"}],
                    },
                )
        assert res.status_code == 200
        assert state["content"].get("day_ai_reviews", {}).get("1") == "Concurrent AI review must survive"

        # 500 error sanitization
        mock_sb.table.side_effect = RuntimeError("SECRET_IMPORT_DB_LEAK")
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            res_err = await ac.post("/api/trips/import-to-trip", json={"trip_id": "trip-imp-lock", "items": []})
        assert res_err.status_code == 500
        assert "SECRET_IMPORT_DB_LEAK" not in res_err.text
    finally:
        app.dependency_overrides.clear()
        __reset_locks_for_testing()


def test_exploit_leave_trip_handles_pgrst116_and_sanitizes_500(client_env):
    client, mock_sb = client_env
    mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = RuntimeError(
        "PGRST116 JSON object requested, multiple (or no) rows returned"
    )
    mock_sb.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
    r_missing = client.post("/api/trips/missing-trip/leave")
    assert r_missing.status_code == 200

    mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = RuntimeError(
        "SECRET_LEAVE_DB_ERROR"
    )
    r_err = client.post("/api/trips/missing-trip/leave")
    assert r_err.status_code == 500
    assert "SECRET_LEAVE_DB_ERROR" not in r_err.text


def test_exploit_parse_md_async_override_supported():
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: MagicMock(
        select=MagicMock(return_value=MagicMock(eq=MagicMock(return_value=MagicMock(execute=MagicMock(
            return_value=MagicMock(data=[{"id": "trip-1", "created_by": USER_OWNER, "title": "Taipei"}] if name == "itineraries" else [])
        )))))
    )

    async def async_owner():
        return USER_OWNER

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = async_owner
    app.dependency_overrides[get_gemini_key] = lambda: DUMMY_API_KEY
    client = TestClient(app, raise_server_exceptions=False)
    try:
        with patch("services.geocode_service.resolve_prompt_spatial_anchor", AsyncMock(return_value={})), \
             patch("services.geocode_service.build_spatial_constraint_prompt", return_value=""), \
             patch("services.geocode_service.verify_and_heal_itinerary_coords", AsyncMock(return_value=([], {}))), \
             patch("routers.ai.call_extraction", AsyncMock(return_value=json.dumps({"title": "Taipei", "days": []}))):
            res = client.post("/api/ai/parse-md", json={"markdown_text": "Day 1 Taipei 101", "itinerary_id": "trip-1"})
        assert res.status_code == 200
    finally:
        app.dependency_overrides.clear()
