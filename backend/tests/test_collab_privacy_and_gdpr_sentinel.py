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
            if self.table_name == "user_trips_view" and self.store.get("_raise_view_error"):
                raise RuntimeError("simulated user_trips_view outage")
            matched = [dict(r) for r in rows if self._matches(r)]
            if self._limit is not None:
                matched = matched[: self._limit]
            return MagicMock(data=matched)
        if self._op == "insert":
            items = self._payload if isinstance(self._payload, list) else [self._payload]
            inserted = []
            for entry in items:
                rec = dict(entry)
                rec.setdefault("id", f"ins-{len(rows) + 1}")
                rows.append(rec)
                inserted.append(dict(rec))
            return MagicMock(data=inserted)
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


def test_patch_info_blocks_card_creator_forgery_hijacking_privatization_and_hidden_id_collision(make_client):
    """P0 Credit Card Ownership & Oracle Guard:
    1. New public card forging creator_id=OWNER_ID must be bound to JWT COLLAB_ID.
    2. Editing Owner's existing public card with creator_id=COLLAB_ID must keep OWNER_ID.
    3. Flipping Owner's existing public card to is_public=False must be blocked (stays public + OWNER_ID).
    4. Submitting hidden foreign private card's id must NOT leak OWNER_ID or create duplicate ids.
    5. Benign control: card creator CAN toggle their own card between public and private.
    """
    store = _base_store()
    store["itineraries"][0]["content"]["credit_cards"].append(
        {"id": "card-pub-steal", "name": "Owner Shared Steal Target", "is_public": True, "creator_id": OWNER_ID}
    )
    collab_client = make_client(store, COLLAB_ID)

    res = collab_client.patch(
        f"/api/trips/{TRIP_ID}/info",
        json={
            "credit_cards": [
                {"id": "card-forged-new", "name": "Forged Public", "is_public": True, "creator_id": OWNER_ID},
                {"id": "card-pub", "name": "Shared Card Edited", "is_public": True, "creator_id": COLLAB_ID},
                {"id": "card-pub-steal", "name": "Tried To Steal", "is_public": False, "creator_id": COLLAB_ID},
                {"id": "card-own-priv", "name": "Colliding Public Clone", "is_public": True, "creator_id": ""},
            ]
        },
    )
    assert res.status_code == 200

    saved_cards = store["itineraries"][0]["content"]["credit_cards"]
    ids = [c["id"] for c in saved_cards]
    assert len(ids) == len(set(ids)), "Duplicate card IDs must never exist after hidden-ID collision"
    by_id = {c["id"]: c for c in saved_cards}

    # 1. Forged new public card bound to COLLAB_ID
    assert by_id["card-forged-new"]["creator_id"] == COLLAB_ID
    # 2. Existing Owner public card preserved original OWNER_ID despite tools-view sending COLLAB_ID
    assert by_id["card-pub"]["creator_id"] == OWNER_ID
    # 3. Existing Owner public card could NOT be privatized/stolen by Collaborator
    assert by_id["card-pub-steal"]["is_public"] is True
    assert by_id["card-pub-steal"]["creator_id"] == OWNER_ID
    # 4. Hidden Owner private card survived untouched; colliding clone got re-minted ID & bound to COLLAB_ID
    assert by_id["card-own-priv"]["name"] == "OWNER_SECRET_CARD"
    assert by_id["card-own-priv"]["is_public"] is False
    assert by_id["card-own-priv"]["creator_id"] == OWNER_ID
    clones = [c for c in saved_cards if c.get("name") == "Colliding Public Clone"]
    assert len(clones) == 1
    assert clones[0]["id"] != "card-own-priv"
    assert clones[0]["creator_id"] == COLLAB_ID

    # 5. Benign control: Collaborator CAN privatize Collaborator's OWN card; Owner CAN privatize Owner's OWN card
    res_collab_own = collab_client.patch(
        f"/api/trips/{TRIP_ID}/info",
        json={
            "credit_cards": [
                {"id": "card-forged-new", "name": "Forged Public", "is_public": False},
                {"id": "card-pub", "name": "Shared Card Edited", "is_public": True},
                {"id": "card-pub-steal", "name": "Tried To Steal", "is_public": True},
            ]
        },
    )
    assert res_collab_own.status_code == 200
    after_collab = {c["id"]: c for c in store["itineraries"][0]["content"]["credit_cards"]}
    assert after_collab["card-forged-new"]["is_public"] is False
    assert after_collab["card-forged-new"]["creator_id"] == COLLAB_ID

    owner_client = make_client(store, OWNER_ID)
    res_owner_own = owner_client.patch(
        f"/api/trips/{TRIP_ID}/info",
        json={
            "credit_cards": [
                {"id": "card-pub", "name": "Shared Card Now Private", "is_public": False},
                {"id": "card-own-priv", "name": "OWNER_SECRET_CARD", "is_public": False},
            ]
        },
    )
    assert res_owner_own.status_code == 200
    after_owner = {c["id"]: c for c in store["itineraries"][0]["content"]["credit_cards"]}
    assert after_owner["card-pub"]["is_public"] is False
    assert after_owner["card-pub"]["creator_id"] == OWNER_ID
    # Collab's hidden private card survived Owner's update!
    assert "card-forged-new" in after_owner


def test_private_itinerary_items_bola_declassification_deletion_reorder_and_collab_create_blocked(make_client):
    """P0 Private Itinerary Item Isolation:
    Production `itinerary_items` has `is_private` (no `private_owner_id` column).
    Collaborators MUST be blocked (403) from creating private items, declassifying/editing/deleting/reordering
    Owner's private items, or privatizing public items; Owner and public benign operations MUST still succeed.
    """
    store = _base_store()
    # Match real production schema: itinerary_items rows have is_private, NO private_owner_id column
    for row in store["itinerary_items"]:
        row.pop("private_owner_id", None)

    collab_client = make_client(store, COLLAB_ID)

    # 1. Collaborator cannot create a private itinerary item (would vanish from Collab & leak to Owner)
    r_create_priv = collab_client.post(
        "/api/trips/items",
        json={
            "itinerary_id": TRIP_ID,
            "day_number": 1,
            "time_slot": "20:00",
            "place_name": "Collab Hidden Attempt",
            "category": "sightseeing",
            "lat": 35.66,
            "lng": 139.70,
            "is_private": True,
        },
    )
    assert r_create_priv.status_code == 403

    # 2. Collaborator cannot declassify/exfiltrate Owner's private item via PATCH
    r_declassify = collab_client.patch("/api/trips/items/item-priv", json={"is_private": False})
    assert r_declassify.status_code == 403
    assert next(i for i in store["itinerary_items"] if i["id"] == "item-priv")["is_private"] is True

    # 3. Collaborator cannot privatize a shared public item
    r_privatize = collab_client.patch("/api/trips/items/item-pub", json={"is_private": True})
    assert r_privatize.status_code == 403

    # 4. Collaborator cannot delete Owner's private item
    r_del_priv = collab_client.delete("/api/trips/items/item-priv")
    assert r_del_priv.status_code == 403
    assert any(i["id"] == "item-priv" for i in store["itinerary_items"])

    # 5. Collaborator cannot reorder Owner's private item
    r_reorder_priv = collab_client.patch(
        "/api/trips/items/reorder",
        json={"items": [{"item_id": "item-priv", "sort_order": 0}], "adjust_times": False},
    )
    assert r_reorder_priv.status_code == 403

    # 6. Benign Control (Collaborator): public create / update / reorder / delete all succeed
    r_collab_pub = collab_client.post(
        "/api/trips/items",
        json={
            "itinerary_id": TRIP_ID,
            "day_number": 1,
            "time_slot": "11:00",
            "place_name": "Collab Public Cafe",
            "category": "food",
            "lat": 35.67,
            "lng": 139.71,
            "is_private": False,
        },
    )
    assert r_collab_pub.status_code == 200
    pub_created_id = r_collab_pub.json()["data"][0]["id"]
    assert collab_client.patch(f"/api/trips/items/{pub_created_id}", json={"notes": "Great coffee"}).status_code == 200
    assert collab_client.patch(
        "/api/trips/items/reorder",
        json={"items": [{"item_id": pub_created_id, "sort_order": 1}], "adjust_times": False},
    ).status_code == 200
    assert collab_client.delete(f"/api/trips/items/{pub_created_id}").status_code == 200

    # 7. Benign Control (Owner): private create / update / reorder / delete all succeed
    owner_client = make_client(store, OWNER_ID)
    r_owner_priv = owner_client.post(
        "/api/trips/items",
        json={
            "itinerary_id": TRIP_ID,
            "day_number": 1,
            "time_slot": "21:00",
            "place_name": "Owner Private Dinner",
            "category": "food",
            "lat": 35.65,
            "lng": 139.74,
            "is_private": True,
        },
    )
    assert r_owner_priv.status_code == 200
    own_created_id = r_owner_priv.json()["data"][0]["id"]
    assert owner_client.patch(f"/api/trips/items/{own_created_id}", json={"notes": "Ring box"}).status_code == 200
    assert owner_client.patch(
        "/api/trips/items/reorder",
        json={"items": [{"item_id": own_created_id, "sort_order": 2}], "adjust_times": False},
    ).status_code == 200
    assert owner_client.delete(f"/api/trips/items/{own_created_id}").status_code == 200


def test_get_trips_fallback_prefers_content_and_masks_foreign_legacy_user_id(make_client):
    """When user_trips_view fails and GET /api/trips falls back to itineraries,
    content fields take precedence over stale top-level columns and foreign user_id is masked."""
    store = _base_store()
    store["_raise_view_error"] = True
    store["itineraries"][0]["user_id"] = OWNER_ID
    store["itineraries"][0]["day_costs"] = {"1": [{"item": "STALE_TOP_LEVEL_COST", "amount": "1"}]}

    collab_client = make_client(store, COLLAB_ID)
    res = collab_client.get("/api/trips")
    assert res.status_code == 200
    payload = res.json()
    raw = json.dumps(payload, ensure_ascii=False)
    assert OWNER_ID not in raw
    assert "OWNER_SECRET_COST" not in raw
    assert "STALE_TOP_LEVEL_COST" not in raw
    assert "Public Ramen" in raw
    assert payload[0]["created_by"] is None
    assert payload[0].get("user_id") is None
