"""
Regression Sentinel Tests: Multi-User Privacy Isolation, Collaboration Merge-Safety,
UUID Masking across Trip Endpoints, and GDPR Solo SYSTEM Sample Trip Reclamation.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
from utils.deps import get_supabase, get_verified_user
from routers.trips import mask_member_id

OWNER_ID = "11111111-1111-4111-8111-111111111111"
COLLAB_ID = "22222222-2222-4222-8222-222222222222"
TRIP_ID = "33333333-3333-4333-8333-333333333333"


class FakeQuery:
    def __init__(self, store, table_name):
        self.store = store
        self.table_name = table_name
        self._op = "select"
        self._payload = None
        self._filters = []
        self._limit = None

    def select(self, *_args, **_kwargs):
        self._op = "select"
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

    def in_(self, col, vals):
        self._filters.append(("in", col, list(vals)))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _matches(self, row):
        for kind, col, val in self._filters:
            if kind == "eq" and row.get(col) != val:
                return False
            if kind == "in" and row.get(col) not in val:
                return False
        return True

    def execute(self):
        rows = self.store.setdefault(self.table_name, [])
        if self._op == "select":
            matched = [dict(r) for r in rows if self._matches(r)]
            if self._limit is not None:
                matched = matched[: self._limit]
            return MagicMock(data=matched)
        if self._op == "update":
            updated = []
            for r in rows:
                if self._matches(r):
                    r.update(self._payload)
                    updated.append(dict(r))
            return MagicMock(data=updated)
        if self._op == "delete":
            kept = []
            deleted = []
            for r in rows:
                if self._matches(r):
                    deleted.append(dict(r))
                else:
                    kept.append(r)
            self.store[self.table_name] = kept
            return MagicMock(data=deleted)
        return MagicMock(data=[])


class FakeSupabase:
    def __init__(self, store):
        self.store = store

    def table(self, name):
        return FakeQuery(self.store, name)


@pytest.fixture
def make_client():
    created_clients = []

    def _factory(store, current_user_id):
        fake_db = FakeSupabase(store)
        app.dependency_overrides[get_supabase] = lambda: fake_db
        app.dependency_overrides[get_verified_user] = lambda: current_user_id
        c = TestClient(app)
        created_clients.append(c)
        return c

    yield _factory
    app.dependency_overrides.clear()


def _base_store():
    return {
        "itineraries": [
            {
                "id": TRIP_ID,
                "title": "Tokyo Collab Privacy Trip",
                "creator_name": "Owner",
                "created_by": OWNER_ID,
                "start_date": "2026-12-01",
                "end_date": "2026-12-03",
                "share_code": "ROOM99",
                "public_id": "pub_room99",
                "content": {
                    "day_checklists": {
                        "1": [
                            "Legacy Plain String Item",
                            {"id": "c-pub", "text": "Public Checklist", "checked": False, "is_private": False},
                            {
                                "id": "c-own-priv",
                                "text": "OWNER_SECRET_CHK",
                                "checked": False,
                                "is_private": True,
                                "private_owner_id": OWNER_ID,
                            },
                            {
                                "id": "c-legacy-priv",
                                "text": "LEGACY_OWNERLESS_PRIV",
                                "checked": False,
                                "is_private": True,
                            },
                        ]
                    },
                    "day_costs": {
                        "1": [
                            {"item": "Public Ramen", "amount": "1200", "currency": "JPY", "is_private": False},
                            {
                                "item": "OWNER_SECRET_COST",
                                "amount": "99999",
                                "currency": "JPY",
                                "is_private": True,
                                "private_owner_id": OWNER_ID,
                            },
                        ]
                    },
                    "day_tickets": {
                        "1": [
                            {"name": "Public JR Pass", "price": "5000", "currency": "JPY", "is_private": False},
                            {
                                "name": "OWNER_SECRET_TICKET",
                                "price": "88888",
                                "currency": "JPY",
                                "is_private": True,
                                "private_owner_id": OWNER_ID,
                            },
                        ]
                    },
                    "credit_cards": [
                        {"id": "card-pub", "name": "Shared Card", "is_public": True, "creator_id": OWNER_ID},
                        {"id": "card-own-priv", "name": "OWNER_SECRET_CARD", "is_public": False, "creator_id": OWNER_ID},
                    ],
                },
            }
        ],
        "trip_members": [
            {"id": "m-1", "itinerary_id": TRIP_ID, "user_id": OWNER_ID, "user_name": "Owner"},
            {"id": "m-2", "itinerary_id": TRIP_ID, "user_id": COLLAB_ID, "user_name": "Collab"},
        ],
        "itinerary_items": [
            {
                "id": "item-pub",
                "itinerary_id": TRIP_ID,
                "day_number": 1,
                "time_slot": "10:00",
                "place_name": "Senso-ji",
                "original_name": "Senso-ji",
                "category": "sightseeing",
                "notes": "",
                "location_lat": 35.71,
                "location_lng": 139.79,
                "cost_amount": 0,
                "is_private": False,
            },
            {
                "id": "item-priv",
                "itinerary_id": TRIP_ID,
                "day_number": 1,
                "time_slot": "19:00",
                "place_name": "OWNER_SECRET_PROPOSAL_SPOT",
                "original_name": "Secret",
                "category": "sightseeing",
                "notes": "Private",
                "location_lat": 35.65,
                "location_lng": 139.74,
                "cost_amount": 0,
                "is_private": True,
                "private_owner_id": OWNER_ID,
            },
        ],
        "user_trips_view": [],
    }


def _populate_user_trips_view(store):
    trip = store["itineraries"][0]
    store["user_trips_view"] = [
        {**trip, "user_id": OWNER_ID},
        {**trip, "user_id": COLLAB_ID},
    ]


def test_patch_day_data_preserves_hidden_foreign_private_items_and_enforces_owner(make_client):
    """P0 Data Loss + Ownership Guard: Collaborator PATCH must preserve Owner's hidden private items
    across checklists, costs, and tickets, and bind caller's own private items to JWT user_id."""
    store = _base_store()
    collab_client = make_client(store, COLLAB_ID)

    resp = collab_client.patch(
        f"/api/trips/{TRIP_ID}/day-data",
        json={
            "day": 1,
            "day_checklists": {
                "1": [
                    {"id": "c-pub", "text": "Public Checklist Edited", "checked": True, "is_private": False, "private_owner_id": OWNER_ID},
                    # Collaborator omits private_owner_id -> server must bind COLLAB_ID
                    {"id": "c-collab-priv", "text": "COLLAB_SECRET_CHK", "checked": False, "is_private": True},
                    # Collaborator tries to spoof OWNER_ID -> server must override with COLLAB_ID
                    {"id": "c-collab-spoof", "text": "COLLAB_SPOOF_CHK", "checked": False, "is_private": True, "private_owner_id": OWNER_ID},
                ]
            },
            "day_costs": {
                "1": [
                    {"item": "Public Ramen", "amount": "1200", "currency": "JPY", "is_private": False},
                    {"item": "Collab Snack", "amount": "500", "currency": "JPY", "is_private": False},
                ]
            },
            "day_tickets": {
                "1": [
                    {"name": "Public JR Pass", "price": "5000", "currency": "JPY", "is_private": False},
                ]
            },
        },
    )
    assert resp.status_code == 200

    saved_content = store["itineraries"][0]["content"]
    chk_by_id = {c["id"]: c for c in saved_content["day_checklists"]["1"] if isinstance(c, dict)}
    assert "c-own-priv" in chk_by_id
    assert chk_by_id["c-own-priv"]["text"] == "OWNER_SECRET_CHK"
    assert "c-legacy-priv" in chk_by_id
    assert chk_by_id["c-collab-priv"]["private_owner_id"] == COLLAB_ID
    assert chk_by_id["c-collab-spoof"]["private_owner_id"] == COLLAB_ID
    assert "private_owner_id" not in chk_by_id["c-pub"]

    cost_names = {c["item"] for c in saved_content["day_costs"]["1"]}
    assert "OWNER_SECRET_COST" in cost_names
    assert "Collab Snack" in cost_names

    ticket_names = {t["name"] for t in saved_content["day_tickets"]["1"]}
    assert "OWNER_SECRET_TICKET" in ticket_names
    assert "Public JR Pass" in ticket_names

    # Now Owner edits Day 1 and removes Owner's own private items -> Owner's items delete, Collab's survive!
    owner_client = make_client(store, OWNER_ID)
    resp_owner = owner_client.patch(
        f"/api/trips/{TRIP_ID}/day-data",
        json={
            "day": 1,
            "day_checklists": {
                "1": [
                    {"id": "c-pub", "text": "Public Checklist Edited", "checked": True, "is_private": False},
                ]
            },
        },
    )
    assert resp_owner.status_code == 200
    after_owner = {c["id"]: c for c in store["itineraries"][0]["content"]["day_checklists"]["1"] if isinstance(c, dict)}
    assert "c-own-priv" not in after_owner
    assert "c-legacy-priv" not in after_owner
    assert "c-collab-priv" in after_owner
    assert after_owner["c-collab-priv"]["private_owner_id"] == COLLAB_ID


def test_get_trips_and_latest_and_detail_isolate_private_data_and_raw_uuids(make_client):
    """P0 Privacy & UUID Isolation across GET /api/trips, GET /api/trips/itinerary/latest,
    and GET /api/trips/{trip_id} (including user_trips_view user_id collision fix)."""
    store = _base_store()
    # Add a collaborator-owned private checklist item as well
    store["itineraries"][0]["content"]["day_checklists"]["1"].append(
        {
            "id": "c-collab-own",
            "text": "COLLAB_OWN_PRIVATE",
            "checked": False,
            "is_private": True,
            "private_owner_id": COLLAB_ID,
        }
    )
    _populate_user_trips_view(store)

    # 1. Collaborator calls GET /api/trips
    collab_client = make_client(store, COLLAB_ID)
    res_list = collab_client.get("/api/trips")
    assert res_list.status_code == 200
    list_json = json.dumps(res_list.json(), ensure_ascii=False)
    assert "OWNER_SECRET_CHK" not in list_json
    assert "LEGACY_OWNERLESS_PRIV" not in list_json
    assert "OWNER_SECRET_COST" not in list_json
    assert "OWNER_SECRET_TICKET" not in list_json
    assert "OWNER_SECRET_CARD" not in list_json
    assert OWNER_ID not in list_json
    assert "COLLAB_OWN_PRIVATE" in list_json
    assert "Public Ramen" in list_json
    assert res_list.json()[0]["credit_cards"][0]["creator_id"] == mask_member_id(OWNER_ID, TRIP_ID)

    # 2. Collaborator calls GET /api/trips/itinerary/latest (user_trips_view has user_id == COLLAB_ID!)
    res_latest = collab_client.get("/api/trips/itinerary/latest")
    assert res_latest.status_code == 200
    latest_json = json.dumps(res_latest.json(), ensure_ascii=False)
    assert "OWNER_SECRET_PROPOSAL_SPOT" not in latest_json
    assert "OWNER_SECRET_COST" not in latest_json
    assert "OWNER_SECRET_TICKET" not in latest_json
    assert "OWNER_SECRET_CHK" not in latest_json
    assert OWNER_ID not in latest_json
    assert "Senso-ji" in latest_json

    # 3. Owner calls GET /api/trips/{trip_id}: rescues legacy ownerless item, handles plain string item,
    #    and MUST NOT see Collaborator's private item or Collaborator's raw UUID!
    owner_client = make_client(store, OWNER_ID)
    res_owner = owner_client.get(f"/api/trips/{TRIP_ID}")
    assert res_owner.status_code == 200
    owner_json = json.dumps(res_owner.json(), ensure_ascii=False)
    assert "Legacy Plain String Item" in owner_json
    assert "OWNER_SECRET_CHK" in owner_json
    assert "LEGACY_OWNERLESS_PRIV" in owner_json
    assert "COLLAB_OWN_PRIVATE" not in owner_json
    assert COLLAB_ID not in owner_json


def test_patch_info_preserves_hidden_foreign_private_cards_and_restores_masked_creator(make_client):
    """PATCH /api/trips/{trip_id}/info must preserve hidden foreign private credit cards
    and restore original creator_id when a collaborator submits a masked public card."""
    store = _base_store()
    collab_client = make_client(store, COLLAB_ID)

    # Collaborator reads masked public card from GET /api/trips/{id}
    det = collab_client.get(f"/api/trips/{TRIP_ID}").json()
    masked_pub_card = det["credit_cards"][0]
    assert masked_pub_card["creator_id"].startswith("mem_")

    # Collaborator submits masked public card + new private card
    res = collab_client.patch(
        f"/api/trips/{TRIP_ID}/info",
        json={
            "credit_cards": [
                masked_pub_card,
                {"id": "card-collab-priv", "name": "COLLAB_SECRET_CARD", "is_public": False},
            ]
        },
    )
    assert res.status_code == 200

    cards = {c["id"]: c for c in store["itineraries"][0]["content"]["credit_cards"]}
    assert "card-own-priv" in cards
    assert cards["card-own-priv"]["creator_id"] == OWNER_ID
    assert cards["card-pub"]["creator_id"] == OWNER_ID
    assert cards["card-collab-priv"]["creator_id"] == COLLAB_ID


def test_gdpr_delete_reclaims_solo_orphan_system_sample_trip(make_client):
    """DELETE /api/user/{user_id}/data must reclaim solo SYSTEM sample trips
    while leaving shared SYSTEM trips with other members intact."""
    solo_sys_id = "44444444-4444-4444-8444-444444444444"
    shared_sys_id = "55555555-5555-4555-8555-555555555555"
    store = {
        "itineraries": [
            {"id": solo_sys_id, "title": "Solo Sample", "created_by": "SYSTEM"},
            {"id": shared_sys_id, "title": "Shared Sample", "created_by": "SYSTEM"},
        ],
        "trip_members": [
            {"id": "tm-1", "itinerary_id": solo_sys_id, "user_id": OWNER_ID},
            {"id": "tm-2", "itinerary_id": shared_sys_id, "user_id": OWNER_ID},
            {"id": "tm-3", "itinerary_id": shared_sys_id, "user_id": COLLAB_ID},
        ],
        "itinerary_items": [
            {"id": "si-1", "itinerary_id": solo_sys_id, "place_name": "Solo Spot"},
            {"id": "si-2", "itinerary_id": shared_sys_id, "place_name": "Shared Spot"},
        ],
        "expenses": [],
        "trip_capsule_entries": [],
        "user_preferences": [],
        "notifications": [],
        "push_subscriptions": [],
        "users": [{"id": OWNER_ID, "name": "Owner", "avatar_url": None}],
    }

    owner_client = make_client(store, OWNER_ID)
    res = owner_client.delete(f"/api/user/{OWNER_ID}/data")
    assert res.status_code == 200
    body = res.json()
    assert body["deleted"]["trips"] == 1
    assert body["deleted"]["items"] == 1

    remaining_trip_ids = {t["id"] for t in store["itineraries"]}
    assert solo_sys_id not in remaining_trip_ids
    assert shared_sys_id in remaining_trip_ids
    remaining_item_ids = {i["id"] for i in store["itinerary_items"]}
    assert "si-1" not in remaining_item_ids
    assert "si-2" in remaining_item_ids
