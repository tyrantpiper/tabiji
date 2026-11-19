"""
Comprehensive Regression & Security Sentinel Tests for Tracks T1, T5, T6, T7, T8, T9
===================================================================================
Covers:
- T1: FastAPI notifications & Web Push router auth, BOLA ownership checks, HTTPS push validation
- T5: capsules.py trip_members + created_by (excluding SYSTEM), trips.py delete_trip/delete_day/add_day/update_trip_dates RPC calls & Day 0 migration invariants
- T6: Activity address persistence & serialization across create/update/detail/latest/share
- T7: POI ai-enrich key-free Wikipedia graceful fallback, users.py .limit(1) legacy recovery, agents.py persistent fallback DB + key_hash BOLA check
- T8: Migration SQL verification for Mapillary indexed ref-counting + trip_capsule_entries cleanup trigger
- T9: model_manager.call_extraction_stream + ai.py progressive SSE stream & separated heartbeat frames
"""

import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from routers.agents import (
    _FALLBACK_TASKS,
    __reset_fallback_tasks_for_testing,
)
from routers.poi import POI_ENRICH_CACHE
from utils.deps import get_supabase, get_verified_user


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chain_table(
    *,
    select_data=None,
    select_count=None,
    update_data=None,
    delete_data=None,
    upsert_data=None,
    insert_data=None,
):
    tbl = MagicMock()

    # Select chain supporting .eq().order().range().execute() / .limit().execute() / .single().execute() / .gt().execute()
    sel_chain = MagicMock()
    sel_res = MagicMock(data=select_data if select_data is not None else [], count=select_count)
    sel_chain.eq.return_value = sel_chain
    sel_chain.neq.return_value = sel_chain
    sel_chain.gt.return_value = sel_chain
    sel_chain.gte.return_value = sel_chain
    sel_chain.order.return_value = sel_chain
    sel_chain.range.return_value = sel_chain
    sel_chain.limit.return_value = sel_chain
    sel_chain.single.return_value = sel_chain
    sel_chain.execute.return_value = sel_res
    tbl.select.return_value = sel_chain

    # Update chain
    upd_chain = MagicMock()
    upd_res = MagicMock(data=update_data if update_data is not None else [])
    upd_chain.eq.return_value = upd_chain
    upd_chain.in_.return_value = upd_chain
    upd_chain.execute.return_value = upd_res
    tbl.update.return_value = upd_chain

    # Delete chain
    del_chain = MagicMock()
    del_res = MagicMock(data=delete_data if delete_data is not None else [])
    del_chain.eq.return_value = del_chain
    del_chain.lt.return_value = del_chain
    del_chain.in_.return_value = del_chain
    del_chain.execute.return_value = del_res
    tbl.delete.return_value = del_chain

    # Upsert / Insert chains
    ups_chain = MagicMock()
    ups_chain.execute.return_value = MagicMock(data=upsert_data if upsert_data is not None else [{"ok": True}])
    tbl.upsert.return_value = ups_chain

    ins_chain = MagicMock()
    ins_chain.execute.return_value = MagicMock(data=insert_data if insert_data is not None else [{"id": "new-1"}])
    tbl.insert.return_value = ins_chain

    return tbl


@pytest.fixture
def clean_overrides():
    yield
    app.dependency_overrides.clear()
    __reset_fallback_tasks_for_testing()
    POI_ENRICH_CACHE.clear()


# ---------------------------------------------------------------------------
# T1: Notifications & Web Push Router
# ---------------------------------------------------------------------------

def test_t1_notifications_require_verified_user(clean_overrides):
    client = TestClient(app)
    res_get = client.get("/api/notifications")
    res_read_all = client.patch("/api/notifications/read-all")
    res_push = client.post(
        "/api/push/subscribe",
        json={"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "p256dh": "k1", "auth": "a1"},
    )
    assert res_get.status_code == 401
    assert res_read_all.status_code == 401
    assert res_push.status_code == 401


def test_t1_notifications_crud_and_cross_user_isolation(clean_overrides):
    uid = "11111111-1111-4111-8111-111111111111"
    notif_id = "22222222-2222-4222-8222-222222222222"
    other_notif_id = "33333333-3333-4333-8333-333333333333"

    mock_sb = MagicMock()

    # Track update/delete targets dynamically so cross-user ID returns [] -> 404
    notif_tbl = MagicMock()
    notif_tbl.select.side_effect = lambda *args, **kwargs: (
        _make_chain_table(select_data=[{"id": notif_id}], select_count=1).select()
        if kwargs.get("count") == "exact"
        else _make_chain_table(
            select_data=[
                {
                    "id": notif_id,
                    "user_id": uid,
                    "type": "trip_invite",
                    "title": "Welcome",
                    "body": "You joined",
                    "link": "/",
                    "metadata": {},
                    "is_read": False,
                    "created_at": "2026-11-19T00:00:00Z",
                }
            ]
        ).select()
    )

    def _update_side_effect(payload):
        chain = MagicMock()
        seen = {}

        def _eq(k, v):
            seen[k] = v
            return chain

        chain.eq.side_effect = _eq
        chain.execute.side_effect = lambda: MagicMock(
            data=[{"id": notif_id, **payload}] if seen.get("id") in (None, notif_id) and seen.get("user_id") == uid else []
        )
        return chain

    def _delete_side_effect():
        chain = MagicMock()
        seen = {}

        def _eq(k, v):
            seen[k] = v
            return chain

        chain.eq.side_effect = _eq
        chain.execute.side_effect = lambda: MagicMock(
            data=[{"id": seen.get("id", notif_id)}] if seen.get("id") in (None, notif_id) and seen.get("user_id") == uid else []
        )
        return chain

    notif_tbl.update.side_effect = _update_side_effect
    notif_tbl.delete.side_effect = _delete_side_effect
    mock_sb.table.return_value = notif_tbl

    app.dependency_overrides[get_verified_user] = lambda: uid
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    client = TestClient(app)

    r_list = client.get("/api/notifications")
    assert r_list.status_code == 200
    assert r_list.json()["unread_count"] == 1
    assert len(r_list.json()["items"]) == 1

    r_bad_uuid = client.patch("/api/notifications/not-a-uuid/read")
    assert r_bad_uuid.status_code == 400

    r_cross_read = client.patch(f"/api/notifications/{other_notif_id}/read")
    assert r_cross_read.status_code == 404

    r_read_ok = client.patch(f"/api/notifications/{notif_id}/read")
    assert r_read_ok.status_code == 200

    r_read_all = client.patch("/api/notifications/read-all")
    assert r_read_all.status_code == 200

    r_cross_del = client.delete(f"/api/notifications/{other_notif_id}")
    assert r_cross_del.status_code == 404

    r_del_ok = client.delete(f"/api/notifications/{notif_id}")
    assert r_del_ok.status_code == 200

    r_clear = client.delete("/api/notifications")
    assert r_clear.status_code == 200


def test_t1_push_subscription_ssrf_and_https_validation(clean_overrides):
    uid = "11111111-1111-4111-8111-111111111111"
    push_tbl = _make_chain_table()
    mock_sb = MagicMock()
    mock_sb.table.return_value = push_tbl

    app.dependency_overrides[get_verified_user] = lambda: uid
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    client = TestClient(app)

    for bad_endpoint in [
        "http://fcm.googleapis.com/send/abc",
        "javascript:alert(1)",
        "https://localhost/push",
        "https://127.0.0.1/push",
        "https://10.0.0.5/push",
        "https://192.168.1.10/push",
        "https://169.254.169.254/latest/meta-data",
        "https://user:pass@fcm.googleapis.com/send/abc",
        "not-a-url",
    ]:
        r_bad = client.post(
            "/api/push/subscribe",
            json={"endpoint": bad_endpoint, "p256dh": "pub", "auth": "sec"},
        )
        assert r_bad.status_code == 400, f"Expected 400 for {bad_endpoint}, got {r_bad.status_code}"

    r_ok = client.post(
        "/api/push/subscribe",
        json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/token-123",
            "p256dh": "pub-key",
            "auth": "auth-sec",
            "user_agent": "Chrome/130",
        },
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["status"] == "subscribed"
    upsert_payload = push_tbl.upsert.call_args[0][0]
    assert upsert_payload["user_id"] == uid

    r_del = client.request(
        "DELETE",
        "/api/push/subscribe",
        json={"endpoint": "https://fcm.googleapis.com/fcm/send/token-123"},
    )
    assert r_del.status_code == 200


# ---------------------------------------------------------------------------
# T5 & T6: Capsules total_members, shift_trip_capsules RPC, Delete Cascade, Address
# ---------------------------------------------------------------------------

def test_t5_capsules_total_members_excludes_system_and_dedups(clean_overrides):
    uid = "alice"
    trip_tbl = _make_chain_table(
        select_data=[{
            "id": "trip-1",
            "created_by": "alice",
            "user_id": "SYSTEM",
            "start_date": "2026-10-01",
            "end_date": "2099-10-05",
            "is_capsule_unlocked": False,
        }]
    )
    members_tbl = _make_chain_table(
        select_data=[
            {"user_id": "alice"},
            {"user_id": "bob"},
            {"user_id": "alice"},
            {"user_id": "SYSTEM"},
            {"user_id": ""},
        ]
    )
    cap_tbl = _make_chain_table(select_data=[])

    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: (
        trip_tbl if name == "itineraries"
        else members_tbl if name == "trip_members"
        else cap_tbl
    )

    app.dependency_overrides[get_verified_user] = lambda: uid
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    client = TestClient(app)

    res = client.get("/api/trips/trip-1/capsules?day_number=0")
    assert res.status_code == 200
    assert res.json()["total_members"] == 2


def test_t5_delete_trip_cleans_capsules_before_parent_and_day_ops_invoke_rpc(clean_overrides):
    uid = "owner-1"
    delete_order = []

    def table_factory(name: str):
        if name == "itineraries":
            tbl = _make_chain_table(
                select_data=[{
                    "id": "trip-ops",
                    "created_by": uid,
                    "start_date": "2026-10-01",
                    "end_date": "2026-10-04",
                    "content": {},
                }],
                delete_data=[{"id": "trip-ops"}],
            )
        elif name == "itinerary_items":
            tbl = _make_chain_table(
                select_data=[{"id": "item-3", "day_number": 3}],
                delete_data=[{"id": "item-3"}],
                update_data=[{"id": "item-3"}],
            )
        else:
            tbl = _make_chain_table(
                select_data=[{"user_id": uid}],
                delete_data=[{"id": "deleted-1"}],
                insert_data=[{"id": "item-new"}],
            )
        orig_del = tbl.delete.return_value.execute

        def rec_del():
            delete_order.append(name)
            return orig_del()

        tbl.delete.return_value.execute = rec_del
        return tbl

    mock_sb = MagicMock()
    mock_sb.table.side_effect = table_factory
    mock_sb.rpc.return_value.execute.return_value = MagicMock(data=None)

    app.dependency_overrides[get_verified_user] = lambda: uid
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    client = TestClient(app)

    # 1. delete_day calls shift_trip_capsules(delete_shift)
    r_del_day = client.delete("/api/trips/trip-ops/days/2")
    assert r_del_day.status_code == 200
    mock_sb.rpc.assert_any_call(
        "shift_trip_capsules",
        {"p_trip_id": "trip-ops", "p_op": "delete_shift", "p_pivot_day": 2},
    )

    # 2. add_day with position="before:2" calls shift_trip_capsules(insert_shift)
    r_add_day = client.post("/api/trips/trip-ops/days", json={"position": "before:2"})
    assert r_add_day.status_code == 200
    mock_sb.rpc.assert_any_call(
        "shift_trip_capsules",
        {"p_trip_id": "trip-ops", "p_op": "insert_shift", "p_pivot_day": 2},
    )

    # 3. delete_trip deletes trip_capsule_entries BEFORE itineraries
    delete_order.clear()
    r_del_trip = client.delete("/api/trips/trip-ops")
    assert r_del_trip.status_code == 200
    assert "trip_capsule_entries" in delete_order
    assert "itineraries" in delete_order
    assert delete_order.index("trip_capsule_entries") < delete_order.index("itineraries")


def test_t6_item_address_roundtrip_across_crud_detail_and_share(clean_overrides):
    uid = "owner-1"
    created_item = {
        "id": "item-addr-1",
        "itinerary_id": "trip-addr",
        "day_number": 1,
        "time_slot": "09:30:00",
        "place_name": "Kiyomizu-dera",
        "original_name": "清水寺",
        "category": "sightseeing",
        "notes": "Morning visit",
        "memo": "",
        "location_lat": 34.9949,
        "location_lng": 135.7850,
        "cost_amount": 0,
        "address": "1-294 Kiyomizu, Higashiyama Ward, Kyoto",
        "website_link": "https://www.kiyomizudera.or.jp/",
        "tags": [],
        "sub_items": [],
        "image_urls": [],
        "is_private": False,
        "sort_order": 0,
    }
    trip_row = {
        "id": "trip-addr",
        "public_id": "pub_testaddr",
        "title": "Kyoto Trip",
        "created_by": uid,
        "creator_name": "Ryan",
        "start_date": "2026-10-01",
        "end_date": "2026-10-02",
        "content": {},
    }

    itineraries_tbl = _make_chain_table(select_data=[trip_row])
    members_tbl = _make_chain_table(select_data=[{"user_id": uid, "user_name": "Ryan"}])
    items_tbl = _make_chain_table(
        select_data=[created_item],
        insert_data=[created_item],
        update_data=[created_item],
    )

    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: (
        itineraries_tbl if name == "itineraries"
        else members_tbl if name == "trip_members"
        else items_tbl
    )

    app.dependency_overrides[get_verified_user] = lambda: uid
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    client = TestClient(app)

    r_create = client.post(
        "/api/trips/items",
        json={
            "itinerary_id": "trip-addr",
            "day_number": 1,
            "time_slot": "09:30",
            "place_name": "Kiyomizu-dera",
            "category": "sightseeing",
            "address": "1-294 Kiyomizu, Higashiyama Ward, Kyoto",
            "website_link": "https://www.kiyomizudera.or.jp/",
        },
    )
    assert r_create.status_code == 200
    assert items_tbl.insert.call_args[0][0]["address"] == "1-294 Kiyomizu, Higashiyama Ward, Kyoto"

    r_update = client.patch(
        "/api/trips/items/item-addr-1",
        json={"address": "Updated Kyoto Address"},
    )
    assert r_update.status_code == 200
    assert items_tbl.update.call_args[0][0]["address"] == "Updated Kyoto Address"

    r_detail = client.get("/api/trips/trip-addr")
    assert r_detail.status_code == 200
    assert r_detail.json()["days"][0]["activities"][0]["address"] == "1-294 Kiyomizu, Higashiyama Ward, Kyoto"

    r_share = client.get("/api/trips/share/pub_testaddr")
    assert r_share.status_code == 200
    assert r_share.json()["days"][0]["activities"][0]["address"] == "1-294 Kiyomizu, Higashiyama Ward, Kyoto"


# ---------------------------------------------------------------------------
# T7: POI Wiki Fallback, Users .limit(1), Agents Persistent DB & BOLA
# ---------------------------------------------------------------------------

def test_t7_poi_ai_enrich_degrades_to_free_wiki_without_api_key(clean_overrides):
    client = TestClient(app)
    wiki_payload = {
        "status": "SUCCESS",
        "warnings": [],
        "cultural_desc": "Historic Kyoto temple founded in 778.",
        "travel_tips": "Arrive early.",
        "resolved_language": "en",
        "image_url": "https://upload.wikimedia.org/kiyomizu.jpg",
        "official_url": "https://www.kiyomizudera.or.jp/",
    }

    with patch("routers.poi.call_extraction", new_callable=AsyncMock) as mock_ai, \
         patch("routers.poi.enrich_poi_complete", new_callable=AsyncMock, return_value=wiki_payload):
        res = client.post(
            "/api/poi/ai-enrich",
            json={
                "name": "Kiyomizu-dera",
                "type": "temple",
                "lat": 34.9949,
                "lng": 135.7850,
                "api_key": "",
                "locale": "en",
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "PARTIAL_SUCCESS"
        assert body["ai_key_missing"] is True
        assert "NO_API_KEY" in body["warnings"]
        assert body["cultural_desc"] == "Historic Kyoto temple founded in 778."
        assert body["rating"] == 0
        mock_ai.assert_not_awaited()


def test_t7_users_profile_uses_limit_1_for_legacy_fallback(clean_overrides):
    uid = "11111111-1111-4111-8111-111111111111"
    users_tbl = _make_chain_table(select_data=[])
    itin_tbl = _make_chain_table(select_data=[{"creator_name": "Legacy Ryan"}])
    mock_sb = MagicMock()
    mock_sb.table.side_effect = lambda name: users_tbl if name == "users" else itin_tbl

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    client = TestClient(app)

    res = client.get(f"/api/users/{uid}/profile")
    assert res.status_code == 200
    assert res.json()["name"] == "Legacy Ryan"
    assert res.json()["id"] == uid
    users_tbl.select().eq().limit.assert_called_with(1)
    users_tbl.select().eq().single.assert_not_called()


def test_t7_agents_fallback_persists_db_and_enforces_key_hash_bola(clean_overrides):
    owner_key = "AIzaSy" + "O" * 34
    attacker_key = "AIzaSy" + "A" * 34
    owner_hash = hashlib.sha256(owner_key.encode("utf-8")).hexdigest()

    stored_rows = {}
    tasks_tbl = MagicMock()

    def _upsert(row, on_conflict=None):
        stored_rows[row["id"]] = dict(row)
        c = MagicMock()
        c.execute.return_value = MagicMock(data=[row])
        return c

    def _select(*args, **kwargs):
        sel = MagicMock()
        target = {}

        def _eq(k, v):
            target[k] = v
            return sel

        sel.eq.side_effect = _eq
        sel.limit.return_value = sel
        sel.execute.side_effect = lambda: MagicMock(
            data=[stored_rows[target["id"]]] if target.get("id") in stored_rows else []
        )
        return sel

    def _update(payload):
        upd = MagicMock()
        target = {}

        def _eq(k, v):
            target[k] = v
            return upd

        upd.eq.side_effect = _eq

        def _exec():
            tid = target.get("id")
            if tid in stored_rows and stored_rows[tid].get("key_hash") == target.get("key_hash"):
                stored_rows[tid].update(payload)
                return MagicMock(data=[stored_rows[tid]])
            return MagicMock(data=[])

        upd.execute.side_effect = _exec
        return upd

    tasks_tbl.upsert.side_effect = _upsert
    tasks_tbl.select.side_effect = _select
    tasks_tbl.update.side_effect = _update
    tasks_tbl.delete.return_value.lt.return_value.execute.return_value = MagicMock(data=[])

    mock_sb = MagicMock()
    mock_sb.table.return_value = tasks_tbl
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    client = TestClient(app)

    fake_client = MagicMock()
    fake_client.interactions.create.side_effect = RuntimeError("Sandbox queued")

    with patch("routers.agents._get_agents_genai_client", return_value=fake_client), \
         patch("routers.agents._execute_flash_fallback_task", new_callable=AsyncMock):
        start_res = client.post(
            "/api/agents/research",
            json={"prompt": "Kyoto 3 days"},
            headers={"X-Gemini-API-Key": owner_key},
        )
    assert start_res.status_code == 200
    task_id = start_res.json()["interaction_id"]
    assert task_id in stored_rows
    assert stored_rows[task_id]["key_hash"] == owner_hash
    assert owner_key not in json.dumps(stored_rows[task_id])

    # Simulate Cloud Run instance restart: clear process-local _FALLBACK_TASKS!
    _FALLBACK_TASKS.clear()

    # Attacker with different API key -> 403
    attacker_poll = client.get(
        f"/api/agents/interactions/{task_id}",
        headers={"X-Gemini-API-Key": attacker_key},
    )
    assert attacker_poll.status_code == 403

    attacker_cancel = client.post(
        f"/api/agents/interactions/{task_id}/cancel",
        headers={"X-Gemini-API-Key": attacker_key},
    )
    assert attacker_cancel.status_code == 403

    # Legitimate owner polls & cancels cleanly from DB even when in-memory dict was cleared!
    owner_poll = client.get(
        f"/api/agents/interactions/{task_id}",
        headers={"X-Gemini-API-Key": owner_key},
    )
    assert owner_poll.status_code == 200
    assert owner_poll.json()["status"] == "running"

    # Expired TTL row returns 404
    stored_rows[task_id]["expires_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    expired_poll = client.get(
        f"/api/agents/interactions/{task_id}",
        headers={"X-Gemini-API-Key": owner_key},
    )
    assert expired_poll.status_code == 404


# ---------------------------------------------------------------------------
# T5 / T8: Migration DDL Contract Assertions
# ---------------------------------------------------------------------------

def test_t5_t8_migration_ddl_contracts():
    sql_path = REPO_ROOT / "supabase" / "migrations" / "20261119_bug_hunter_remediation_schema.sql"
    sql = sql_path.read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS address TEXT" in sql
    assert "idx_itinerary_items_mly_ref_id" in sql
    assert "CREATE TABLE IF NOT EXISTS public.agent_fallback_tasks" in sql
    assert "REVOKE ALL ON TABLE public.agent_fallback_tasks FROM anon, authenticated" in sql
    assert "GRANT ALL ON TABLE public.agent_fallback_tasks TO service_role" in sql
    assert "CREATE OR REPLACE FUNCTION public.shift_trip_capsules" in sql
    assert "REVOKE ALL ON FUNCTION public.shift_trip_capsules(UUID, TEXT, INTEGER) FROM PUBLIC, anon, authenticated" in sql
    assert "day_number + 10000" in sql
    assert "AND day_number > 0" in sql
    assert "p_op = 'truncate_merge'" in sql
    assert "v_old_json #- '{preview_metadata,mapillary_thumb}'" in sql
    assert "EXCEPTION" in sql
    assert "CREATE TRIGGER cleanup_cloudinary_trigger" in sql
    assert "ON public.trip_capsule_entries" in sql


# ---------------------------------------------------------------------------
# T9: Streaming Extraction & Progressive SSE Events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_t9_call_extraction_stream_thoughts_chunks_and_fallback():
    import services.model_manager as mm

    thought_steps = []
    chunk_lengths = []

    class _StreamList:
        def __init__(self, items):
            self._items = iter(items)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._items)
            except StopIteration:
                raise StopAsyncIteration

    chunk1 = SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[
            SimpleNamespace(thought=True, text="thinking...")
        ]))]
    )
    chunk2 = SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[
            SimpleNamespace(thought=False, text='{"title":"Kyoto",')
        ]))]
    )
    chunk3 = SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=[
            SimpleNamespace(thought=False, text='"days":[]}')
        ]))]
    )

    thought_only = SimpleNamespace(
        candidates=[SimpleNamespace(finish_reason="STOP", content=SimpleNamespace(parts=[
            SimpleNamespace(thought=True, text="only thought")
        ]))]
    )

    call_count = 0

    async def fake_stream(*, model, contents, config):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _StreamList([thought_only])  # Primary emits thought-only -> must fallback!
        return _StreamList([chunk1, chunk2, chunk3])

    fake_client = MagicMock()
    fake_client.aio.models.generate_content_stream = fake_stream

    with patch.object(mm, "get_cached_client", return_value=fake_client):
        result = await mm.call_extraction_stream(
            api_key="AIzaSyStreamUnitKey123456789",
            prompt="Kyoto 1 day",
            intent_type="PLANNING",
            routing_strategy=["gemini-3.5-flash-lite", "gemini-3.6-flash"],
            on_thought=lambda n: thought_steps.append(n),
            on_chunk=lambda c: chunk_lengths.append(c),
        )

    assert json.loads(result) == {"title": "Kyoto", "days": []}
    assert call_count == 2
    assert thought_steps[-1] >= 1
    assert chunk_lengths == [17, 27]


@pytest.mark.asyncio
async def test_t9_generate_trip_core_emits_real_stream_progress_milestones():
    from routers.ai import generate_trip_core
    import services.model_manager as mm

    async def fake_stream_fn(api_key, prompt, intent_type="PLANNING", routing_strategy=None, system_instruction=None, on_thought=None, on_chunk=None):
        if on_thought:
            await on_thought(1)
            await on_thought(2)
        if on_chunk:
            await on_chunk(200)
            await on_chunk(1600)
            await on_chunk(3200)
        return json.dumps({
            "title": "Kyoto 1D",
            "destination": "Kyoto",
            "currency": "JPY",
            "days": [{"day_number": 1, "activities": [{"time": "09:00", "place_name": "Kiyomizu-dera", "lat": 34.9949, "lng": 135.7850}]}],
        })

    q: asyncio.Queue = asyncio.Queue()
    with patch.object(mm, "call_extraction_stream", side_effect=fake_stream_fn), \
         patch("services.geocode_service.resolve_prompt_spatial_anchor", AsyncMock(return_value=None)), \
         patch("services.geocode_service.build_spatial_constraint_prompt", return_value=""), \
         patch("services.geocode_service.verify_and_heal_itinerary_coords", AsyncMock(return_value=([{"day_number": 1, "place_name": "Kiyomizu-dera", "time_slot": "09:00", "lat": 34.9949, "lng": 135.7850}], {}))):
        res = await generate_trip_core(prompt="Kyoto 1 day", api_key="AIzaSyDummy123", locale="en", progress_queue=q)

    assert res["title"] == "Kyoto 1D"
    percents = []
    while not q.empty():
        ev_type, payload = q.get_nowait()
        if ev_type == "progress":
            percents.append(payload["percent"])

    assert percents[0] == 15
    assert 20 in percents
    assert any(21 <= p <= 24 for p in percents)
    assert any(25 <= p <= 68 for p in percents)
    assert 75 in percents
    assert 90 in percents
    assert percents == sorted(percents)


@pytest.mark.asyncio
async def test_t9_generate_trip_core_parses_day_number_places_and_fallback_notice():
    from routers.ai import generate_trip_core
    import services.model_manager as mm

    class _StreamList:
        def __init__(self, items):
            self._items = iter(items)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._items)
            except StopIteration:
                raise StopAsyncIteration

    full_json = json.dumps({
        "title": "Tokyo 2D",
        "destination": "Tokyo",
        "currency": "JPY",
        "days": [
            {"day_number": 1, "activities": [{"time": "09:00", "place_name": "Senso-ji", "lat": 35.7148, "lng": 139.7967}]},
            {"day_number": 2, "activities": [{"time": "10:00", "place_name": "Meiji Jingu", "lat": 35.6764, "lng": 139.6993}]},
        ],
    })
    split_idx = full_json.index('"day_number": 2')
    c1 = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(thought=False, text=full_json[:split_idx])]))])
    c2 = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(thought=False, text=full_json[split_idx:])]))])
    thought_only = SimpleNamespace(candidates=[SimpleNamespace(finish_reason="STOP", content=SimpleNamespace(parts=[SimpleNamespace(thought=True, text="only thought")]))])

    calls = 0

    async def fake_stream(*, model, contents, config):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _StreamList([thought_only])
        return _StreamList([c1, c2])

    fake_client = MagicMock()
    fake_client.aio.models.generate_content_stream = fake_stream

    q: asyncio.Queue = asyncio.Queue()
    with patch.object(mm, "get_cached_client", return_value=fake_client), \
         patch.object(mm, "build_effective_routing", return_value=["gemini-3.5-flash-lite", "gemini-3.6-flash"]), \
         patch("services.geocode_service.resolve_prompt_spatial_anchor", AsyncMock(return_value=None)), \
         patch("services.geocode_service.build_spatial_constraint_prompt", return_value=""), \
         patch("services.geocode_service.verify_and_heal_itinerary_coords", AsyncMock(return_value=([{"day_number": 1, "place_name": "Senso-ji", "time_slot": "09:00", "lat": 35.7148, "lng": 139.7967}], {}))):
        res = await generate_trip_core(prompt="Tokyo 2 days", api_key="AIzaSyStreamTestKey1234567890", locale="zh", progress_queue=q)

    assert res["title"] == "Tokyo 2D"
    events = []
    while not q.empty():
        ev_type, payload = q.get_nowait()
        if ev_type == "progress":
            events.append(payload)

    messages = [e["message"] for e in events]
    assert any("切換高速備援模型重試中" in m for m in messages)
    day_events = [e for e in events if e.get("stage") == "STREAMING" and "current_day" in e]
    assert [e["current_day"] for e in day_events] == [1, 2]
    assert any("正在編排第 1 天行程" in e["message"] for e in day_events)
    assert any("正在編排第 2 天行程" in e["message"] for e in day_events)
    assert [e["percent"] for e in events] == sorted(e["percent"] for e in events)
