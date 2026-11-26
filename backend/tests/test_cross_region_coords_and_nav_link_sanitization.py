"""
Bug Hunter Red->Green & Benign Control Test Suite:
1. Cross-region confirmed coordinate preservation & text-coordinate self-consistency
   (Osaka restaurant added into Taipei trip must keep 34.7024, 135.5002 with 0 smart_geocode_logic calls,
    while Taipei homonym '龍山寺' with Seoul coords still heals to Taipei).
2. Navigation URL (link_url) strict map-domain whitelist & automatic memo link routing
   (Instagram / Threads / official websites are stripped from link_url and routed to sub_items & website_link).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from main import app


HEADERS = {
    "Content-Type": "application/json",
    "X-User-ID": "11111111-1111-1111-1111-111111111111",
}
TRIP_ID = "b260f84f-cdea-4a00-a5f1-91564d31d966"
OWNER_ID = "11111111-1111-1111-1111-111111111111"


def _make_create_item_mock_sb(trip_title: str = "3 Day Taipei Explorer ✨", daily_locations: dict | None = None):
    inserted_rows = []
    mock_sb = MagicMock()

    def table_side_effect(name):
        tbl = MagicMock()
        if name == "trip_members":
            tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
                {"user_id": OWNER_ID}
            ]
        elif name == "itineraries":
            tbl.select.return_value.eq.return_value.execute.return_value.data = [
                {
                    "id": TRIP_ID,
                    "title": trip_title,
                    "created_by": OWNER_ID,
                    "content": {
                        "daily_locations": daily_locations
                        if daily_locations is not None
                        else {"1": {"name": "Taipei", "lat": 25.0551, "lng": 121.5084}}
                    },
                }
            ]
        elif name == "itinerary_items":
            tbl.select.return_value.eq.return_value.execute.return_value.data = []

            def capture_insert(payload):
                inserted_rows.append(payload)
                m = MagicMock()
                m.execute.return_value.data = [{**payload, "id": "item-new-1"}]
                return m

            tbl.insert.side_effect = capture_insert
        return tbl

    mock_sb.table.side_effect = table_side_effect
    return mock_sb, inserted_rows


# ═══════════════════════════════════════════════════════════════════════════════
# Bug 1: Cross-Region Coordinates & Self-Consistency
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_bug1_osaka_poi_in_taipei_trip_preserves_coords_without_preserve_flag():
    """
    [Bug 1 Red->Green via Text-Coord Self-Consistency]:
    POST /api/trips/items adding '北海 -HOKKAI- お初天神店' (34.7024, 135.5002, Osaka notes)
    into '3 Day Taipei Explorer ✨' MUST preserve (34.7024, 135.5002) with 0 smart_geocode_logic calls,
    even when preserve_coords is not set (default False).
    """
    mock_sb, inserted = _make_create_item_mock_sb()
    from utils.deps import get_supabase, get_verified_user

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: OWNER_ID
    try:
        with patch("services.geocode_service.smart_geocode_logic", new_callable=AsyncMock) as mock_geo:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.post(
                    "/api/trips/items",
                    headers=HEADERS,
                    json={
                        "itinerary_id": TRIP_ID,
                        "day_number": 1,
                        "time_slot": "18:00",
                        "place_name": "北海 -HOKKAI- お初天神店",
                        "category": "restaurant",
                        "notes": "大阪超人氣壽司吃到飽，提供全60種豐富品項",
                        "lat": 34.7024,
                        "lng": 135.5002,
                    },
                )
            assert resp.status_code == 200
            assert mock_geo.call_count == 0
            assert len(inserted) == 1
            assert inserted[0]["location_lat"] == pytest.approx(34.7024, abs=1e-4)
            assert inserted[0]["location_lng"] == pytest.approx(135.5002, abs=1e-4)
    finally:
        app.dependency_overrides.pop(get_supabase, None)
        app.dependency_overrides.pop(get_verified_user, None)


@pytest.mark.asyncio
async def test_bug1_preserve_coords_flag_keeps_confirmed_foreign_coords_zero_geocode():
    """
    [Bug 1 Red->Green via preserve_coords=True]:
    Even for an English-only venue with no country keyword in notes/address,
    preserve_coords=True preserves confirmed non-homonym coordinates with 0 smart_geocode_logic calls.
    """
    mock_sb, inserted = _make_create_item_mock_sb()
    from utils.deps import get_supabase, get_verified_user

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: OWNER_ID
    try:
        with patch("services.geocode_service.smart_geocode_logic", new_callable=AsyncMock) as mock_geo:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.post(
                    "/api/trips/items",
                    headers=HEADERS,
                    json={
                        "itinerary_id": TRIP_ID,
                        "day_number": 1,
                        "time_slot": "19:00",
                        "place_name": "Bistro Lumiere",
                        "category": "restaurant",
                        "lat": 48.8566,
                        "lng": 2.3522,
                        "preserve_coords": True,
                    },
                )
            assert resp.status_code == 200
            assert mock_geo.call_count == 0
            assert inserted[0]["location_lat"] == pytest.approx(48.8566, abs=1e-4)
            assert inserted[0]["location_lng"] == pytest.approx(2.3522, abs=1e-4)
    finally:
        app.dependency_overrides.pop(get_supabase, None)
        app.dependency_overrides.pop(get_verified_user, None)


@pytest.mark.asyncio
async def test_bug1_benign_control_homonym_longshan_seoul_coords_still_healed_even_with_preserve_coords():
    """
    [Bug 1 Benign Control]:
    Ambiguous homonym '龍山寺' with Seoul coords (37.5299, 126.9645) and NO Korean text clues
    in a Taipei trip MUST still heal to Taipei (~25.0372, 121.4999), even if preserve_coords=True.
    """
    mock_sb, inserted = _make_create_item_mock_sb(trip_title="台北古蹟遊")
    from utils.deps import get_supabase, get_verified_user

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: OWNER_ID
    try:
        with patch("services.geocode_service.smart_geocode_logic", new_callable=AsyncMock) as mock_geo:
            mock_geo.return_value = {
                "results": [{"name": "艋舺龍山寺", "lat": 25.0372, "lng": 121.4999, "country": "TW"}]
            }
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.post(
                    "/api/trips/items",
                    headers=HEADERS,
                    json={
                        "itinerary_id": TRIP_ID,
                        "day_number": 1,
                        "time_slot": "14:00",
                        "place_name": "龍山寺",
                        "category": "sightseeing",
                        "lat": 37.5299,
                        "lng": 126.9645,
                        "preserve_coords": True,
                    },
                )
            assert resp.status_code == 200
            assert mock_geo.call_count == 1
            assert 24.95 <= inserted[0]["location_lat"] <= 25.15
            assert 121.40 <= inserted[0]["location_lng"] <= 121.65
    finally:
        app.dependency_overrides.pop(get_supabase, None)
        app.dependency_overrides.pop(get_verified_user, None)


@pytest.mark.asyncio
async def test_bug1_weak_substring_collision_refuses_to_overwrite_valid_coords():
    """
    [Bug 1 Weak-Match Relevance Guard]:
    When out_of_country healing runs on a non-homonym place with valid coords and smart_geocode_logic
    returns an unrelated short-substring match (e.g. '北海福座' for '北海初天神壽司專門店'),
    verify_and_heal_itinerary_coords MUST refuse to overwrite the original valid coordinates.
    """
    from services.geocode_service import verify_and_heal_itinerary_coords

    items = [
        {
            "day_number": 1,
            "place_name": "北海初天神壽司專門店",  # Pure Hanzi (no kana/city keyword), valid JP coords
            "lat": 34.7024,
            "lng": 135.5002,
        }
    ]
    with patch("services.geocode_service.smart_geocode_logic", new_callable=AsyncMock) as mock_geo:
        mock_geo.return_value = {
            "results": [{"name": "北海福座", "lat": 25.0395471, "lng": 121.424726, "country": "TW"}]
        }
        healed, _ = await verify_and_heal_itinerary_coords(
            items,
            trip_meta={"title": "3 Day Taipei Explorer ✨"},
        )
        assert mock_geo.call_count == 1
        assert healed[0]["lat"] == pytest.approx(34.7024, abs=1e-4)
        assert healed[0]["lng"] == pytest.approx(135.5002, abs=1e-4)


def test_bug1_culinary_dish_name_not_misclassified_as_foreign_city():
    """
    [Bug 1 Edge Case]: '大阪燒' is a dish name, not an Osaka location clue;
    '大阪超人氣壽司吃到飽' IS an Osaka location clue.
    """
    from services.geocode_service import is_self_consistent_foreign_place

    assert is_self_consistent_foreign_place(
        {"place_name": "老字號大阪燒專賣店", "notes": "超好吃的大阪燒"},
        34.6937,
        135.5023,
    ) is False
    assert is_self_consistent_foreign_place(
        {"place_name": "北海 -HOKKAI- お初天神店", "notes": "大阪超人氣壽司吃到飽"},
        34.7024,
        135.5002,
    ) is True


# ═══════════════════════════════════════════════════════════════════════════════
# Bug 2: Map-Only Navigation URL Whitelist & Memo Link Routing
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "url",
    [
        "https://maps.app.goo.gl/abc123XYZ",
        "https://goo.gl/maps/abc123XYZ",
        "https://www.google.com/maps/place/Tokyo+Tower/@35.6586,139.7454,17z",
        "https://www.google.com.tw/maps/search/?api=1&query=Osaka",
        "https://maps.google.co.jp/?q=34.7024,135.5002",
        "https://maps.apple.com/?ll=34.7024,135.5002",
        "https://www.openstreetmap.org/?mlat=34.7024&mlon=135.5002",
        "https://osm.org/go/7P52",
        "https://map.naver.com/p/entry/place/12345",
        "https://naver.me/abcdef",
        "https://map.kakao.com/link/map/12345",
        "https://kko.to/abcdef",
        "https://map.yahoo.co.jp/place?gid=12345",
        "https://www.bing.com/maps?cp=34.7024~135.5002",
        "https://ditu.amap.com/place/B000A83M61",
        "https://map.baidu.com/@13525210,3640150,15z",
        "https://www.waze.com/ul?ll=34.7024,135.5002",
    ],
)
def test_bug2_is_map_navigation_url_accepts_allowed_map_domains(url):
    from routers.trips import is_map_navigation_url

    assert is_map_navigation_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instagram.com/reel/Dd-M_DVvHWP/",
        "https://www.threads.net/@tabiji/post/123",
        "https://www.tiktok.com/@travel/video/123",
        "https://tabelog.com/osaka/A2701/A270101/27123456/",
        "https://www.senso-ji.jp/",
        "https://www.google.com/search?q=osaka",
        "https://goo.gl/forms/abc",
        "https://www.bing.com/search?q=tokyo",
        "https://maps.google.com.evil.com/maps",
        "https://maps.google.com@evil.com/maps",
        "https://evil.com/https://maps.google.com",
        "https://evil-osm.org/go/123",
        "javascript:alert(1)//https://maps.google.com",
        "data:text/html,<script>alert(1)</script>",
        "",
        None,
    ],
)
def test_bug2_is_map_navigation_url_rejects_non_map_and_spoofed_urls(url):
    from routers.trips import is_map_navigation_url

    assert is_map_navigation_url(url) is False


@pytest.mark.asyncio
async def test_bug2_create_item_routes_ig_link_to_sub_items_and_clears_link_url():
    """
    [Bug 2 Red->Green - POST /api/trips/items]:
    Passing Instagram Reel URL in link_url MUST clear link_url to None,
    append a deduplicated Instagram entry into sub_items, and retain website_link.
    Passing a valid Google Maps URL MUST keep link_url intact.
    """
    ig_url = "https://www.instagram.com/reel/Dd-M_DVvHWP/"
    gmaps_url = "https://maps.app.goo.gl/OsakaHokkai123"
    mock_sb, inserted = _make_create_item_mock_sb()
    from utils.deps import get_supabase, get_verified_user

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: OWNER_ID
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1) IG link passed in link_url
            resp_ig = await client.post(
                "/api/trips/items",
                headers=HEADERS,
                json={
                    "itinerary_id": TRIP_ID,
                    "day_number": 1,
                    "time_slot": "18:00",
                    "place_name": "北海 -HOKKAI- お初天神店",
                    "category": "restaurant",
                    "notes": "大阪壽司吃到飽",
                    "lat": 34.7024,
                    "lng": 135.5002,
                    "preserve_coords": True,
                    "link_url": ig_url,
                    "sub_items": [{"name": "全60種 寿司食べ放題コース"}],
                },
            )
            assert resp_ig.status_code == 200
            row_ig = inserted[0]
            assert row_ig["link_url"] is None
            assert row_ig["website_link"] == ig_url
            assert len(row_ig["sub_items"]) == 2
            assert row_ig["sub_items"][0]["name"] == "全60種 寿司食べ放題コース"
            assert row_ig["sub_items"][1] == {"name": "Instagram 參考連結", "link": ig_url}

            # 2) Idempotent when frontend already put IG link into sub_items & website_link
            resp_dedup = await client.post(
                "/api/trips/items",
                headers=HEADERS,
                json={
                    "itinerary_id": TRIP_ID,
                    "day_number": 1,
                    "time_slot": "18:00",
                    "place_name": "北海 -HOKKAI- お初天神店",
                    "category": "restaurant",
                    "lat": 34.7024,
                    "lng": 135.5002,
                    "preserve_coords": True,
                    "link_url": None,
                    "website_link": ig_url,
                    "sub_items": [
                        {"name": "全60種 寿司食べ放題コース"},
                        {"name": "Instagram 參考連結", "link": ig_url},
                    ],
                },
            )
            assert resp_dedup.status_code == 200
            assert len(inserted[1]["sub_items"]) == 2

            # 3) Valid Google Maps URL preserved in link_url
            resp_map = await client.post(
                "/api/trips/items",
                headers=HEADERS,
                json={
                    "itinerary_id": TRIP_ID,
                    "day_number": 1,
                    "time_slot": "18:00",
                    "place_name": "北海 -HOKKAI- お初天神店",
                    "category": "restaurant",
                    "lat": 34.7024,
                    "lng": 135.5002,
                    "preserve_coords": True,
                    "link_url": gmaps_url,
                },
            )
            assert resp_map.status_code == 200
            assert inserted[2]["link_url"] == gmaps_url
            assert inserted[2]["sub_items"] == []

            # 4) javascript: XSS payload dropped completely
            resp_xss = await client.post(
                "/api/trips/items",
                headers=HEADERS,
                json={
                    "itinerary_id": TRIP_ID,
                    "day_number": 1,
                    "time_slot": "18:00",
                    "place_name": "北海 -HOKKAI- お初天神店",
                    "category": "restaurant",
                    "lat": 34.7024,
                    "lng": 135.5002,
                    "preserve_coords": True,
                    "link_url": "javascript:alert(1)",
                    "website_link": "javascript:alert(2)",
                },
            )
            assert resp_xss.status_code == 200
            assert inserted[3]["link_url"] is None
            assert inserted[3]["website_link"] is None
            assert inserted[3]["sub_items"] == []
    finally:
        app.dependency_overrides.pop(get_supabase, None)
        app.dependency_overrides.pop(get_verified_user, None)


@pytest.mark.asyncio
async def test_bug2_update_item_routes_ig_link_without_jit_or_coord_wipe_and_respects_deleted_sub_items():
    """
    [Bug 2 Red->Green - PATCH /api/trips/items/{id}]:
    1) PATCHing IG URL into link_url sets link_url=None, appends to existing sub_items,
       sets website_link, does NOT invoke resolve_google_maps_link, and does NOT wipe coords.
    2) PATCHing memo/sub_items=[] with unchanged website_link MUST NOT resurrect the deleted link.
    """
    ig_url = "https://www.instagram.com/reel/Dd-M_DVvHWP/"
    updated_payloads = []
    existing_row = {
        "itinerary_id": TRIP_ID,
        "link_url": None,
        "website_link": None,
        "sub_items": [{"name": "招牌壽司"}],
        "location_lat": 34.7024,
        "location_lng": 135.5002,
        "image_url": None,
        "image_urls": [],
        "place_name": "北海 -HOKKAI- お初天神店",
        "is_private": False,
    }

    mock_sb = MagicMock()

    def table_side_effect(name):
        tbl = MagicMock()
        if name == "trip_members":
            tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [
                {"user_id": OWNER_ID}
            ]
        elif name == "itinerary_items":
            tbl.select.return_value.eq.return_value.execute.return_value.data = [dict(existing_row)]

            def capture_update(payload):
                updated_payloads.append(payload)
                m = MagicMock()
                m.eq.return_value.execute.return_value.data = [{**existing_row, **payload, "id": "item-1"}]
                return m

            tbl.update.side_effect = capture_update
        return tbl

    mock_sb.table.side_effect = table_side_effect
    from utils.deps import get_supabase, get_verified_user

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: OWNER_ID
    try:
        with patch("routers.trips.resolve_google_maps_link", new_callable=AsyncMock) as mock_resolve:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp1 = await client.patch(
                    "/api/trips/items/item-1",
                    headers=HEADERS,
                    json={"link_url": ig_url},
                )
                assert resp1.status_code == 200
                assert mock_resolve.call_count == 0
                assert updated_payloads[0]["link_url"] is None
                assert updated_payloads[0]["website_link"] == ig_url
                assert "location_lat" not in updated_payloads[0]
                assert "location_lng" not in updated_payloads[0]
                assert updated_payloads[0]["sub_items"] == [
                    {"name": "招牌壽司"},
                    {"name": "Instagram 參考連結", "link": ig_url},
                ]

                # Simulate user deleting sub_items in DetailDialog (sends unchanged website_link)
                existing_row["website_link"] = ig_url
                existing_row["sub_items"] = [{"name": "Instagram 參考連結", "link": ig_url}]
                resp2 = await client.patch(
                    "/api/trips/items/item-1",
                    headers=HEADERS,
                    json={"memo": "已整理", "website_link": ig_url, "sub_items": []},
                )
                assert resp2.status_code == 200
                assert updated_payloads[1]["sub_items"] == []
    finally:
        app.dependency_overrides.pop(get_supabase, None)
        app.dependency_overrides.pop(get_verified_user, None)


def test_bug2_model_manager_schemas_separate_map_link_and_website_link():
    """
    [Bug 2 Schema Contract]:
    ADD_ITINERARY_DECL, ADD_ITINERARY_FLAT_DECL (Depth=1), PARSE_MD, and PLANNING
    all declare website_link and restrict link_url to map navigation URLs.
    """
    from services.model_manager import (
        ADD_ITINERARY_DECL,
        ADD_ITINERARY_FLAT_DECL,
        build_json_schema_for_intent,
    )

    # 1. ADD_ITINERARY_DECL (top-level & items[])
    decl_props = ADD_ITINERARY_DECL.parameters.properties
    assert "website_link" in decl_props
    assert "map" in decl_props["link_url"].description.lower()
    assert "instagram" in decl_props["link_url"].description.lower()
    item_props = decl_props["items"].items.properties
    assert "website_link" in item_props
    assert "map" in item_props["link_url"].description.lower()

    # 2. ADD_ITINERARY_FLAT_DECL (Gemma Depth=1 preserved)
    flat_props = ADD_ITINERARY_FLAT_DECL.parameters.properties
    assert "website_link" in flat_props
    assert "items" not in flat_props
    assert "sub_items" not in flat_props
    assert "map" in flat_props["link_url"].description.lower()

    # 3. PARSE_MD & PLANNING schemas
    parse_md_props = build_json_schema_for_intent("PARSE_MD")["properties"]["items"]["items"]["properties"]
    assert "website_link" in parse_md_props
    assert "map" in parse_md_props["link_url"]["description"].lower()

    planning_props = (
        build_json_schema_for_intent("PLANNING")["properties"]["days"]["items"]["properties"]["activities"]["items"]["properties"]
    )
    assert "website_link" in planning_props
    assert "map" in planning_props["link_url"]["description"].lower()


@pytest.mark.asyncio
async def test_bug1_preserve_coords_null_island_triggers_healing_and_explicit_foreign_homonym_preserved():
    """
    [Bug 1 Edge Cases]:
    1) preserve_coords=True with (0.0, 0.0) Null Island MUST NOT be preserved; triggers healing.
    2) preserve_coords=True with explicit foreign homonym '東京迪士尼' + JP coords MUST be preserved.
    """
    mock_sb, inserted = _make_create_item_mock_sb(trip_title="台北古蹟遊")
    from utils.deps import get_supabase, get_verified_user

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: OWNER_ID
    try:
        with patch("services.geocode_service.smart_geocode_logic", new_callable=AsyncMock) as mock_geo:
            mock_geo.return_value = {
                "results": [{"name": "台北101", "lat": 25.0339, "lng": 121.5645, "country": "TW"}]
            }
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                r_zero = await client.post(
                    "/api/trips/items",
                    headers=HEADERS,
                    json={
                        "itinerary_id": TRIP_ID,
                        "day_number": 1,
                        "time_slot": "10:00",
                        "place_name": "台北101",
                        "category": "sightseeing",
                        "lat": 0.0,
                        "lng": 0.0,
                        "preserve_coords": True,
                    },
                )
                assert r_zero.status_code == 200
                assert mock_geo.call_count == 1
                assert inserted[0]["location_lat"] == pytest.approx(25.0339, abs=1e-4)

                r_disney = await client.post(
                    "/api/trips/items",
                    headers=HEADERS,
                    json={
                        "itinerary_id": TRIP_ID,
                        "day_number": 1,
                        "time_slot": "12:00",
                        "place_name": "東京迪士尼樂園",
                        "category": "sightseeing",
                        "lat": 35.6329,
                        "lng": 139.8804,
                        "preserve_coords": True,
                    },
                )
                assert r_disney.status_code == 200
                assert mock_geo.call_count == 1  # No extra call!
                assert inserted[1]["location_lat"] == pytest.approx(35.6329, abs=1e-4)
                assert inserted[1]["location_lng"] == pytest.approx(139.8804, abs=1e-4)
    finally:
        app.dependency_overrides.pop(get_supabase, None)
        app.dependency_overrides.pop(get_verified_user, None)


@pytest.mark.asyncio
async def test_bug2_save_itinerary_and_import_to_trip_sanitize_non_map_links():
    """
    [Bug 2 Defense-in-Depth]:
    Both POST /api/trips/save-itinerary and POST /api/trips/import-to-trip sanitize non-map link_url
    (IG / Threads / official site) into sub_items & website_link while clearing link_url to None.
    """
    ig_url = "https://www.instagram.com/reel/Dd-M_DVvHWP/"
    gmaps_url = "https://www.google.com/maps/place/Taipei+101/@25.0339,121.5645,17z"
    saved_batches = []
    mock_sb = MagicMock()

    def table_side_effect(name):
        tbl = MagicMock()
        if name == "users":
            tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{"id": OWNER_ID}]
        elif name == "itineraries":
            tbl.insert.return_value.execute.return_value.data = [{"id": TRIP_ID}]
            tbl.select.return_value.eq.return_value.execute.return_value.data = [
                {
                    "id": TRIP_ID,
                    "title": "台北美食遊",
                    "created_by": OWNER_ID,
                    "start_date": "2026-10-11",
                    "end_date": "2026-10-12",
                    "content": {"daily_locations": {"1": {"name": "台北", "lat": 25.0330, "lng": 121.5654}}},
                }
            ]
            tbl.update.return_value.eq.return_value.execute.return_value.data = [{"id": TRIP_ID}]
        elif name == "trip_members":
            tbl.insert.return_value.execute.return_value.data = [{"user_id": OWNER_ID}]
            tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"user_id": OWNER_ID}]
        elif name == "itinerary_items":
            tbl.select.return_value.eq.return_value.execute.return_value.data = []

            def capture_insert(payload):
                saved_batches.append(payload)
                m = MagicMock()
                m.execute.return_value.data = payload if isinstance(payload, list) else [payload]
                return m

            tbl.insert.side_effect = capture_insert
        return tbl

    mock_sb.table.side_effect = table_side_effect
    from utils.deps import get_supabase, get_verified_user

    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: OWNER_ID
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            r_save = await client.post(
                "/api/trips/save-itinerary",
                headers=HEADERS,
                json={
                    "title": "台北美食遊",
                    "creator_name": "Ryan",
                    "user_id": OWNER_ID,
                    "start_date": "2026-10-11",
                    "items": [
                        {
                            "day_number": 1,
                            "time_slot": "18:00",
                            "place_name": "北海 -HOKKAI- お初天神店",
                            "category": "restaurant",
                            "desc": "大阪壽司吃到飽",
                            "lat": 34.7024,
                            "lng": 135.5002,
                            "link_url": ig_url,
                        },
                        {
                            "day_number": 1,
                            "time_slot": "10:00",
                            "place_name": "台北101",
                            "category": "sightseeing",
                            "lat": 25.0339,
                            "lng": 121.5645,
                            "link_url": gmaps_url,
                        },
                    ],
                },
            )
            assert r_save.status_code == 200
            save_rows = saved_batches[0]
            assert save_rows[0]["link_url"] is None
            assert save_rows[0]["website_link"] == ig_url
            assert save_rows[0]["sub_items"] == [{"name": "Instagram 參考連結", "link": ig_url}]
            assert save_rows[0]["location_lat"] == pytest.approx(34.7024, abs=1e-4)
            assert save_rows[1]["link_url"] == gmaps_url

            r_import = await client.post(
                "/api/trips/import-to-trip",
                headers=HEADERS,
                json={
                    "trip_id": TRIP_ID,
                    "items": [
                        {
                            "day_number": 2,
                            "time_slot": "19:00",
                            "place_name": "北海 -HOKKAI- お初天神店",
                            "category": "restaurant",
                            "desc": "大阪壽司吃到飽",
                            "lat": 34.7024,
                            "lng": 135.5002,
                            "link_url": ig_url,
                        }
                    ],
                },
            )
            assert r_import.status_code == 200
            import_rows = saved_batches[1]
            assert import_rows[0]["link_url"] is None
            assert import_rows[0]["website_link"] == ig_url
            assert import_rows[0]["sub_items"] == [{"name": "Instagram 參考連結", "link": ig_url}]
            assert import_rows[0]["location_lat"] == pytest.approx(34.7024, abs=1e-4)
    finally:
        app.dependency_overrides.pop(get_supabase, None)
        app.dependency_overrides.pop(get_verified_user, None)


@pytest.mark.asyncio
async def test_bug1_contradictory_home_country_text_and_intra_country_explicit_city_guard():
    """
    [Bug 1 Hardening]:
    1) A Taipei branch mentioning Osaka flavor ('北海 台北店', notes='源自大阪風味') with Japan coords
       contradicts allowed_countries={'TW'} and MUST still be healed back to Taipei.
    2) Decorative 'の' ('茶の魔手') MUST NOT be misclassified as Japanese JP.
    3) Intra-country cross-city explicit Osaka spot inside '2026 東京自由行' MUST preserve Osaka coords (0 geocode calls).
    4) Multi-word English match tokens are split before whitespace stripping.
    """
    from services.geocode_service import (
        verify_and_heal_itinerary_coords,
        is_self_consistent_foreign_place,
        _is_weak_out_of_country_match,
    )

    assert is_self_consistent_foreign_place(
        {"place_name": "茶の魔手", "notes": "台南知名手搖飲"},
        34.7024,
        135.5002,
        allowed_countries={"TW"},
    ) is False

    assert _is_weak_out_of_country_match("Grand Central Station", "Grand Central Terminal") is False
    assert _is_weak_out_of_country_match("Cafe Lumiere Paris", "Cafe Taipei") is True

    # 1) Contradictory Taipei branch with Japan coords MUST heal to Taipei
    with patch("services.geocode_service.smart_geocode_logic", new_callable=AsyncMock) as mock_geo:
        mock_geo.return_value = {
            "results": [{"name": "北海 台北店", "lat": 25.0418, "lng": 121.5439, "country": "TW"}]
        }
        healed_tw, _ = await verify_and_heal_itinerary_coords(
            [
                {
                    "day_number": 1,
                    "place_name": "北海 台北店",
                    "notes": "源自大阪風味的壽司店",
                    "lat": 34.7024,
                    "lng": 135.5002,
                }
            ],
            trip_meta={"title": "3 Day Taipei Explorer ✨"},
        )
        assert mock_geo.call_count == 1
        assert 24.95 <= healed_tw[0]["lat"] <= 25.15

    # 2) Intra-country explicit Osaka spot in a Tokyo trip preserves Osaka coords with 0 geocode calls
    with patch("services.geocode_service.smart_geocode_logic", new_callable=AsyncMock) as mock_geo_jp:
        healed_osaka, _ = await verify_and_heal_itinerary_coords(
            [
                {
                    "day_number": 1,
                    "place_name": "北海 -HOKKAI- お初天神店",
                    "notes": "大阪超人氣壽司吃到飽",
                    "lat": 34.7024,
                    "lng": 135.5002,
                }
            ],
            trip_meta={
                "title": "2026 東京自由行",
                "content": {"daily_locations": {"1": {"name": "東京", "lat": 35.6895, "lng": 139.6917}}},
            },
        )
        assert mock_geo_jp.call_count == 0
        assert healed_osaka[0]["lat"] == pytest.approx(34.7024, abs=1e-4)
        assert healed_osaka[0]["lng"] == pytest.approx(135.5002, abs=1e-4)


def test_bug2_sample_trip_items_all_satisfy_map_only_link_url_invariant():
    """Built-in sample trip items MUST only store map navigation URLs in link_url."""
    from routers.sample_trip import SAMPLE_ITEMS
    from routers.trips import is_map_navigation_url

    for item in SAMPLE_ITEMS:
        link_url = item.get("link_url")
        if link_url:
            assert is_map_navigation_url(link_url), f"Non-map link_url in sample_trip: {item['place_name']} -> {link_url}"


@pytest.mark.asyncio
async def test_bug2_parse_markdown_preview_sanitizes_ig_link_out_of_link_url():
    """POST /api/ai/parse-md preview JSON MUST separate non-map link_url into website_link + sub_items."""
    import json
    from utils.deps import get_gemini_key, get_supabase, get_verified_user

    ig_url = "https://www.instagram.com/reel/Dd-M_DVvHWP/"
    mock_json = json.dumps(
        {
            "title": "大阪美食遊",
            "destination": "大阪",
            "items": [
                {
                    "day_number": 1,
                    "time_slot": "18:00",
                    "place_name": "北海 -HOKKAI- お初天神店",
                    "category": "restaurant",
                    "desc": "大阪壽司吃到飽",
                    "lat": 34.7024,
                    "lng": 135.5002,
                    "link_url": ig_url,
                }
            ],
        }
    )

    app.dependency_overrides[get_gemini_key] = lambda: "AIzaSyDummyKeyForTest1234567890123456789"
    app.dependency_overrides[get_supabase] = lambda: MagicMock()
    app.dependency_overrides[get_verified_user] = lambda: OWNER_ID
    try:
        with patch("services.model_manager.call_extraction", new_callable=AsyncMock, return_value=mock_json), \
             patch("routers.ai.call_extraction", new_callable=AsyncMock, return_value=mock_json):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.post(
                    "/api/ai/parse-md",
                    headers=HEADERS,
                    json={"markdown_text": "Day 1 大阪 北海 -HOKKAI- お初天神店"},
                )
        assert resp.status_code == 200, resp.text
        item = resp.json()["items"][0]
        assert item["link_url"] is None
        assert item["website_link"] == ig_url
        assert item["sub_items"] == [{"name": "Instagram 參考連結", "link": ig_url}]
    finally:
        app.dependency_overrides.pop(get_gemini_key, None)
        app.dependency_overrides.pop(get_supabase, None)
        app.dependency_overrides.pop(get_verified_user, None)
