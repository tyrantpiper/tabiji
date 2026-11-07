"""
Security Sentinel In-Memory PoC & Mantis Block G Benign Control Suite
Topic: ai_pre_anchor_and_healing (Pre-Generation Spatial Anchor + Post-Generation Non-Destructive Healing)
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from main import app
from routers.ai import generate_trip_core

HEADERS = {
    "X-Gemini-API-Key": "AIzaSy" + "B" * 34,
    "Content-Type": "application/json",
    "X-User-ID": "11111111-1111-1111-1111-111111111111",
}


@pytest.mark.asyncio
async def test_sentinel_poc_pre_generation_spatial_constraint_injected():
    """
    [Red PoC 1 - H1]: Calling generate_trip_core or parse_markdown MUST resolve the destination
    spatial anchor BEFORE calling Gemini and inject <spatial_anchor_constraint> with valid
    bounding box and homonym disambiguation rules into system_instruction, and output daily_locations.
    """
    captured_sys_inst = []

    async def fake_call_extraction(api_key, prompt_payload, intent_type="PLANNING", routing_strategy=None, system_instruction=""):
        captured_sys_inst.append(system_instruction)
        return json.dumps({
            "title": "台北 3 日探索",
            "destination": "台北",
            "currency": "TWD",
            "days": [
                {
                    "day_number": 1,
                    "activities": [
                        {
                            "time": "10:00",
                            "place_name": "台北 艋舺龍山寺",
                            "category": "sightseeing",
                            "desc": "百年古蹟",
                            "lat": 25.0372,
                            "lng": 121.4999,
                        }
                    ],
                }
            ],
            "day_metadata": [],
            "ai_review": "精彩行程",
        })

    with patch("services.model_manager.call_extraction", side_effect=fake_call_extraction), \
         patch("routers.ai.call_extraction", side_effect=fake_call_extraction):
        res = await generate_trip_core("幫我規劃台北 3 日遊，想去龍山寺與大稻埕", api_key="AIzaSyTest")

    assert len(captured_sys_inst) == 1
    sys_inst = captured_sys_inst[0]
    assert "<spatial_anchor_constraint>" in sys_inst, "Missing <spatial_anchor_constraint> in pre-generation system instruction!"
    assert "TW" in sys_inst
    assert "25.03" in sys_inst and "121.56" in sys_inst
    assert "daily_locations" in res and "1" in res["daily_locations"], "Missing auto-populated daily_locations in generated trip!"


@pytest.mark.asyncio
async def test_sentinel_poc_ai_generate_hallucinated_cross_country_and_homonym_healed():
    """
    [Red PoC 2 - H2]: When Gemini hallucinates Seoul Yongsan coordinates (37.5299, 126.9645)
    or intra-country Lukang coordinates (24.0499, 120.4357) for '龍山寺' in a Taipei trip,
    generate_trip_core MUST intercept the out-of-anchor coordinate and heal it to Taipei (25.0372, 121.4999).
    """
    hallucinated_json = json.dumps({
        "title": "3 Day Taipei Explorer ✨",
        "destination": "Taipei",
        "currency": "TWD",
        "days": [
            {
                "day_number": 1,
                "activities": [
                    {
                        "time": "10:00",
                        "place_name": "大稻埕迪化街",
                        "category": "sightseeing",
                        "desc": "老街散步",
                        "lat": 25.0551,
                        "lng": 121.5083,
                    },
                    {
                        "time": "15:00",
                        "place_name": "龍山寺",
                        "category": "sightseeing",
                        "desc": "萬華古蹟",
                        "lat": 37.5299,   # Hallucinated Seoul Yongsan Station!
                        "lng": 126.9645,
                    },
                ],
            }
        ],
        "day_metadata": [],
        "ai_review": "Great Taipei trip",
    })

    with patch("services.model_manager.call_extraction", new_callable=AsyncMock, return_value=hallucinated_json), \
         patch("routers.ai.call_extraction", new_callable=AsyncMock, return_value=hallucinated_json):
        res = await generate_trip_core("<travel_inquiry><destination>台北</destination></travel_inquiry>", api_key="AIzaSyTest")

    items = res["items"]
    longshan = next(i for i in items if "龍山寺" in i["place_name"])
    assert 24.95 <= longshan["lat"] <= 25.15, f"Expected Taipei lat ~25.0372, got {longshan['lat']}"
    assert 121.40 <= longshan["lng"] <= 121.65, f"Expected Taipei lng ~121.4999, got {longshan['lng']}"


@pytest.mark.asyncio
async def test_sentinel_poc_parse_md_hallucinated_coords_healed_while_url_coords_preserved():
    """
    [Red PoC 3 - H2]: In POST /api/ai/parse-md, if Gemini outputs hallucinated Seoul coordinates
    (37.5299, 126.9645) for '龍山寺' in a Taipei itinerary, it MUST be healed to Taipei (25.0372, 121.4999),
    while an item with a verified Google Maps URL coordinate MUST be 100% preserved.
    """
    mock_parsed = json.dumps({
        "title": "台北萬華一日遊",
        "destination": "台北",
        "start_date": "2026-05-01",
        "end_date": "2026-05-01",
        "items": [
            {
                "day_number": 1,
                "time_slot": "10:00",
                "place_name": "剝皮寮歷史街區",
                "category": "sightseeing",
                "desc": "清代街區",
                "lat": None,
                "lng": None,
                "link_url": "https://www.google.com/maps/place/Bopiliao/@25.0368,121.5022,17z",
            },
            {
                "day_number": 1,
                "time_slot": "14:00",
                "place_name": "龍山寺",
                "category": "sightseeing",
                "desc": "香火鼎盛",
                "lat": 37.5299,   # Hallucinated Seoul coordinate!
                "lng": 126.9645,
            },
        ],
    })

    transport = ASGITransport(app=app)
    with patch("routers.ai.call_extraction", new_callable=AsyncMock, return_value=mock_parsed):
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/api/ai/parse-md",
                headers=HEADERS,
                json={"markdown_text": "# 台北萬華一日遊\n- 10:00 剝皮寮歷史街區\n- 14:00 龍山寺"},
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            items = body["items"]
            assert items[0]["lat"] == pytest.approx(25.0368, abs=1e-4)
            assert items[0]["lng"] == pytest.approx(121.5022, abs=1e-4)
            assert "_url_verified" not in items[0]
            assert 24.95 <= items[1]["lat"] <= 25.15, f"Expected Taipei lat for 龍山寺, got {items[1]['lat']}"
            assert 121.40 <= items[1]["lng"] <= 121.65, f"Expected Taipei lng for 龍山寺, got {items[1]['lng']}"


@pytest.mark.asyncio
async def test_sentinel_poc_parse_md_itinerary_id_bola_blocked():
    """
    [Red PoC 4 - H3]: When POST /api/ai/parse-md is called with `itinerary_id` belonging to another
    user's private trip, the endpoint MUST block unauthorized access with HTTP 403.
    """
    victim_trip_id = "99999999-9999-4999-9999-999999999999"
    attacker_user_id = "11111111-1111-1111-1111-111111111111"
    victim_owner_id = "22222222-2222-2222-2222-222222222222"

    mock_sb = MagicMock()

    def table_side_effect(name):
        tbl = MagicMock()
        if name == "itineraries":
            tbl.select.return_value.eq.return_value.execute.return_value.data = [
                {"id": victim_trip_id, "title": "機密東京行程", "created_by": victim_owner_id, "content": {}}
            ]
        elif name == "trip_members":
            tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = []
        return tbl

    mock_sb.table.side_effect = table_side_effect

    from utils.deps import get_supabase, get_verified_user
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: attacker_user_id
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/api/ai/parse-md",
                headers=HEADERS,
                json={"markdown_text": "- 10:00 龍山寺", "itinerary_id": victim_trip_id},
            )
            assert resp.status_code == 403, f"Expected 403 BOLA block for unauthorized itinerary_id, got {resp.status_code}"
    finally:
        app.dependency_overrides.pop(get_supabase, None)
        app.dependency_overrides.pop(get_verified_user, None)


@pytest.mark.asyncio
async def test_sentinel_poc_save_and_import_to_trip_spatial_healing():
    """
    [Red PoC 5 - H4]: POST /api/trips/import-to-trip and POST /api/trips/save-itinerary MUST heal
    items with cross-country hallucinated coordinates (e.g. Seoul 37.5299, 126.9645 in a Taipei trip)
    before inserting into Supabase `itinerary_items`.
    """
    trip_id = "b260f84f-cdea-4a00-a5f1-91564d31d966"
    owner_id = "11111111-1111-1111-1111-111111111111"
    inserted_batches = []

    mock_sb = MagicMock()

    def table_side_effect(name):
        tbl = MagicMock()
        if name == "itineraries":
            tbl.select.return_value.eq.return_value.execute.return_value.data = [
                {
                    "id": trip_id,
                    "title": "3 Day Taipei Explorer ✨",
                    "created_by": owner_id,
                    "start_date": "2026-05-01",
                    "end_date": "2026-05-03",
                    "content": {},
                }
            ]
            tbl.update.return_value.eq.return_value.execute.return_value.data = [{"id": trip_id}]
        elif name == "itinerary_items":
            tbl.select.return_value.eq.return_value.execute.return_value.data = [
                {
                    "day_number": 1,
                    "place_name": "大稻埕迪化街",
                    "location_lat": 25.0551,
                    "location_lng": 121.5083,
                }
            ]

            def capture_insert(payload):
                if isinstance(payload, list):
                    inserted_batches.extend(payload)
                else:
                    inserted_batches.append(payload)
                res = MagicMock()
                res.data = payload if isinstance(payload, list) else [payload]
                return res

            tbl.insert.side_effect = lambda p: MagicMock(execute=lambda: capture_insert(p))
        return tbl

    mock_sb.table.side_effect = table_side_effect

    from utils.deps import get_supabase, get_verified_user
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: owner_id
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/api/trips/import-to-trip",
                headers=HEADERS,
                json={
                    "trip_id": trip_id,
                    "items": [
                        {
                            "day_number": 1,
                            "time_slot": "17:00",
                            "place_name": "龍山寺",
                            "category": "sightseeing",
                            "desc": "萬華龍山寺",
                            "lat": 37.5299,   # Hallucinated Seoul coordinate!
                            "lng": 126.9645,
                        }
                    ],
                },
            )
            assert resp.status_code == 200, resp.text
            assert len(inserted_batches) == 1
            rec = inserted_batches[0]
            assert 24.95 <= rec["location_lat"] <= 25.15, f"Expected Taipei lat, got {rec['location_lat']}"
            assert 121.40 <= rec["location_lng"] <= 121.65, f"Expected Taipei lng, got {rec['location_lng']}"
    finally:
        app.dependency_overrides.pop(get_supabase, None)
        app.dependency_overrides.pop(get_verified_user, None)


# ==============================================================================
# Mantis Block G Benign Controls (Prove zero over-blocking & Chesterton's Fence)
# ==============================================================================

@pytest.mark.asyncio
async def test_benign_multi_city_tokyo_osaka_trip_preserves_both_cities():
    """
    [Benign Control 1]: A multi-city itinerary ('東京大阪 2 日遊', Day 1 in Tokyo, Day 2 in Osaka 400km away)
    MUST preserve both Day 1 Tokyo coordinates and Day 2 Osaka coordinates without false-positive overwriting
    Osaka back to Tokyo, and populate daily_locations for both days.
    """
    from services.geocode_service import resolve_prompt_spatial_anchor, verify_and_heal_itinerary_coords
    items = [
        {"day_number": 1, "place_name": "淺草寺", "lat": 35.7148, "lng": 139.7967},
        {"day_number": 1, "place_name": "東京鐵塔", "lat": 35.6586, "lng": 139.7454},
        {"day_number": 2, "place_name": "道頓堀", "lat": 34.6687, "lng": 135.5013},
        {"day_number": 2, "place_name": "大阪城", "lat": 34.6873, "lng": 135.5262},
    ]
    pre_anchor = await resolve_prompt_spatial_anchor("幫我規劃日本東京、大阪雙城自由行")
    assert "東京" in pre_anchor["regions"] and "大阪" in pre_anchor["regions"]

    healed_items, daily_locs = await verify_and_heal_itinerary_coords(
        items,
        trip_meta={"title": "東京大阪雙城遊", "destination": "東京、大阪"},
        pre_anchor=pre_anchor,
    )
    assert healed_items[0]["lat"] == pytest.approx(35.7148, abs=1e-3)
    assert healed_items[2]["lat"] == pytest.approx(34.6687, abs=1e-3)
    assert healed_items[3]["lat"] == pytest.approx(34.6873, abs=1e-3)
    assert "1" in daily_locs and "2" in daily_locs
    assert 35.5 <= daily_locs["1"]["lat"] <= 35.9
    assert 34.5 <= daily_locs["2"]["lat"] <= 34.9


@pytest.mark.asyncio
async def test_benign_osm_zero_results_non_destructive_fallback():
    """
    [Benign Control 2 - Chesterton's Fence]:
    1. When an item has a valid in-city coordinate ('淺草今半 國際通本店 (午餐)' at 35.7135, 139.7925),
       no external geocode call is made and the coordinate is preserved.
    2. When an item has a cross-country hallucinated coordinate (37.5299, 126.9645 in a Taipei trip)
       AND smart_geocode_logic returns 0 results (e.g. OSM down or obscure name), it MUST non-destructively
       fall back to the day's Taipei anchor center (~25.0330, 121.5654) rather than leaving Seoul or None!
    """
    from services.geocode_service import resolve_prompt_spatial_anchor, verify_and_heal_itinerary_coords
    items = [
        {"day_number": 1, "place_name": "大稻埕無名私房神祕巷弄小吃攤", "lat": 37.5299, "lng": 126.9645},
    ]
    pre_anchor = await resolve_prompt_spatial_anchor("台北一日遊")
    with patch("services.geocode_service.smart_geocode_logic", new_callable=AsyncMock, return_value={"results": []}):
        healed_items, _ = await verify_and_heal_itinerary_coords(
            items,
            trip_meta={"title": "台北一日遊", "destination": "台北"},
            pre_anchor=pre_anchor,
        )
    assert healed_items[0]["lat"] is not None and healed_items[0]["lng"] is not None
    assert 24.95 <= healed_items[0]["lat"] <= 25.15
    assert 121.45 <= healed_items[0]["lng"] <= 121.65


@pytest.mark.asyncio
async def test_benign_pure_image_parse_md_cot_endogenous_anchor():
    """
    [Benign Control 3]: When user uploads only an image (markdown_text is empty and no itinerary_id),
    resolve_prompt_spatial_anchor returns an endogenous CoT prompt instruction, and post-generation
    healing uses the AI-extracted destination ('台北') to heal any hallucinated coordinates.
    """
    from services.geocode_service import (
        resolve_prompt_spatial_anchor,
        build_spatial_constraint_prompt,
        verify_and_heal_itinerary_coords,
    )
    pre_anchor = await resolve_prompt_spatial_anchor("")
    prompt_block = build_spatial_constraint_prompt(pre_anchor)
    assert "<spatial_anchor_constraint>" in prompt_block
    assert "destination" in prompt_block

    items = [{"day_number": 1, "place_name": "龍山寺", "lat": 37.5299, "lng": 126.9645}]
    healed, _ = await verify_and_heal_itinerary_coords(
        items,
        trip_meta={"title": "台北美食古蹟一日遊", "destination": "台北"},
        pre_anchor=pre_anchor,
    )
    assert 24.95 <= healed[0]["lat"] <= 25.15


@pytest.mark.asyncio
async def test_benign_valid_in_bounds_ai_coords_zero_external_geocode_calls():
    """
    [Benign Control 4 - Latency & Rate-Limit Protection]:
    When Gemini outputs valid in-bounds coordinates for a Taipei trip, smart_geocode_logic
    MUST NOT be called for those items (0 external requests).
    """
    from services.geocode_service import resolve_prompt_spatial_anchor, verify_and_heal_itinerary_coords
    items = [
        {"day_number": 1, "place_name": "台北101觀景台", "lat": 25.0339, "lng": 121.5645},
        {"day_number": 1, "place_name": "大安森林公園", "lat": 25.0330, "lng": 121.5354},
    ]
    pre_anchor = await resolve_prompt_spatial_anchor("台北一日遊")
    with patch("services.geocode_service.smart_geocode_logic", new_callable=AsyncMock) as mock_geo:
        healed, _ = await verify_and_heal_itinerary_coords(
            items,
            trip_meta={"title": "台北一日遊", "destination": "台北"},
            pre_anchor=pre_anchor,
        )
        assert mock_geo.call_count == 0
        assert healed[0]["lat"] == 25.0339
        assert healed[1]["lat"] == 25.0330


@pytest.mark.asyncio
async def test_benign_multi_city_trip_object_and_cluster_preservation():
    """
    [Benign Control 5]:
    1. When trip_meta has `id` and `content` (as in save_itinerary / import_to_trip) for a multi-city
       trip ('東京大阪雙城遊') without pre_anchor, Day 2 Osaka items must NOT be overwritten to Tokyo.
    2. Even when the trip title only mentions '東京 2 日遊', if Day 2 has a coherent multi-item cluster
       in Osaka ('道頓堀' + '大阪城', 3.2km apart), Day 2's anchor resolves to Osaka with 0 geocode calls.
    """
    from services.geocode_service import verify_and_heal_itinerary_coords
    items = [
        {"day_number": 1, "place_name": "淺草寺", "lat": 35.7148, "lng": 139.7967},
        {"day_number": 1, "place_name": "東京鐵塔", "lat": 35.6586, "lng": 139.7454},
        {"day_number": 2, "place_name": "道頓堀", "lat": 34.6687, "lng": 135.5013},
        {"day_number": 2, "place_name": "大阪城", "lat": 34.6873, "lng": 135.5262},
    ]
    with patch("services.geocode_service.smart_geocode_logic", new_callable=AsyncMock) as mock_geo:
        healed_1, daily_locs_1 = await verify_and_heal_itinerary_coords(
            [dict(x) for x in items],
            trip_meta={"id": "trip-123", "title": "東京大阪雙城遊", "content": {"daily_locations": {}}},
        )
        assert mock_geo.call_count == 0
        assert healed_1[2]["lat"] == pytest.approx(34.6687, abs=1e-3)
        assert healed_1[3]["lat"] == pytest.approx(34.6873, abs=1e-3)
        assert 34.5 <= daily_locs_1["2"]["lat"] <= 34.9

        healed_2, daily_locs_2 = await verify_and_heal_itinerary_coords(
            [dict(x) for x in items],
            trip_meta={"id": "trip-456", "title": "東京 2 日遊", "content": {"daily_locations": {}}},
        )
        assert mock_geo.call_count == 0
        assert healed_2[2]["lat"] == pytest.approx(34.6687, abs=1e-3)
        assert healed_2[3]["lat"] == pytest.approx(34.6873, abs=1e-3)
        assert 34.5 <= daily_locs_2["2"]["lat"] <= 34.9


@pytest.mark.asyncio
async def test_benign_multi_country_and_cross_border_day_trip_preservation():
    """
    [Benign Control 6]:
    1. Multi-country trip ('倫敦、巴黎雙城遊', Day 1 GB, Day 2 FR) preserves both countries' coordinates
       with 0 external geocode calls.
    2. Cross-border day trip within <=80km of the day anchor (e.g. Singapore Day 1 visiting Johor Bahru
       at 1.4927, 103.7414, 18km away across the SG/MY border) preserves the cross-border coordinate.
    """
    from services.geocode_service import resolve_prompt_spatial_anchor, verify_and_heal_itinerary_coords
    euro_items = [
        {"day_number": 1, "place_name": "大笨鐘 Big Ben", "lat": 51.5007, "lng": -0.1246},
        {"day_number": 1, "place_name": "倫敦眼 London Eye", "lat": 51.5033, "lng": -0.1195},
        {"day_number": 2, "place_name": "艾菲爾鐵塔 Eiffel Tower", "lat": 48.8584, "lng": 2.2945},
        {"day_number": 2, "place_name": "羅浮宮 Louvre Museum", "lat": 48.8606, "lng": 2.3376},
    ]
    pre_euro = await resolve_prompt_spatial_anchor("倫敦、巴黎雙城遊")
    with patch("services.geocode_service.smart_geocode_logic", new_callable=AsyncMock) as mock_geo:
        healed_euro, euro_locs = await verify_and_heal_itinerary_coords(
            euro_items,
            trip_meta={"title": "倫敦、巴黎雙城遊", "destination": "倫敦、巴黎"},
            pre_anchor=pre_euro,
        )
        assert mock_geo.call_count == 0
        assert healed_euro[0]["lat"] == pytest.approx(51.5007, abs=1e-3)
        assert healed_euro[2]["lat"] == pytest.approx(48.8584, abs=1e-3)
        assert 51.3 <= euro_locs["1"]["lat"] <= 51.7
        assert 48.6 <= euro_locs["2"]["lat"] <= 49.0

        sg_jb_items = [
            {"day_number": 1, "place_name": "濱海灣金沙酒店", "lat": 1.2834, "lng": 103.8607},
            {"day_number": 1, "place_name": "濱海灣花園", "lat": 1.2816, "lng": 103.8636},
            {"day_number": 2, "place_name": "新山城中坊 JB City Square", "lat": 1.4927, "lng": 103.7414},
        ]
        healed_sg, sg_locs = await verify_and_heal_itinerary_coords(
            sg_jb_items,
            trip_meta={
                "title": "新加坡 2 日遊",
                "destination": "新加坡",
                "daily_locations": {"2": {"name": "新山", "lat": 1.4927, "lng": 103.7414}},
            },
        )
        assert mock_geo.call_count == 0
        assert healed_sg[2]["lat"] == pytest.approx(1.4927, abs=1e-3)
        assert healed_sg[2]["lng"] == pytest.approx(103.7414, abs=1e-3)
        assert "2" in sg_locs and sg_locs["2"]["lat"] == pytest.approx(1.4927, abs=1e-3)


@pytest.mark.asyncio
async def test_benign_real_jwt_get_verified_user_and_unknown_dest_fallback():
    """
    [Benign Control 7]:
    1. Verifies parse_markdown with itinerary_id and a real Bearer JWT (without dependency_overrides on get_verified_user)
       calls get_verified_user(request, auth_header=...) cleanly with 0 unexpected-keyword errors.
    2. Verifies resolve_trip_spatial_anchor falls back to smart_geocode_logic for unknown global towns (e.g., '策馬特')
       not present in static LOCATION_KEYWORDS / GLOBAL_CITY_ANCHORS.
    """
    import time
    import uuid
    import jwt
    from utils.deps import get_session_secret, get_supabase, get_gemini_key, get_verified_user
    from services.geocode_service import resolve_trip_spatial_anchor

    owner_uuid = str(uuid.uuid4())
    token = jwt.encode(
        {
            "sub": owner_uuid,
            "iss": "tabiji-core",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "type": "device_session",
        },
        get_session_secret(),
        algorithm="HS256",
    )
    mock_sb = MagicMock()

    def table_side_effect(name):
        tbl = MagicMock()
        if name == "itineraries":
            tbl.select.return_value.eq.return_value.execute.return_value.data = [
                {"id": "trip-real-jwt", "title": "台北美食遊", "created_by": owner_uuid, "content": {}}
            ]
        elif name == "itinerary_items":
            tbl.select.return_value.eq.return_value.execute.return_value.data = []
        return tbl

    mock_sb.table.side_effect = table_side_effect
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_gemini_key] = lambda: "AIzaSyDummyKeyForSentinelTest1234567890123"
    app.dependency_overrides.pop(get_verified_user, None)

    try:
        with patch("services.model_manager.call_extraction", new_callable=AsyncMock) as mock_extract, \
             patch("routers.ai.call_extraction", new_callable=AsyncMock) as mock_extract_ai:
            mock_json = json.dumps({
                "title": "台北美食遊",
                "destination": "台北",
                "items": [{"day_number": 1, "place_name": "台北101", "lat": 25.0339, "lng": 121.5644}],
            })
            mock_extract.return_value = mock_json
            mock_extract_ai.return_value = mock_json
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
                resp = await ac.post(
                    "/api/ai/parse-md",
                    json={"markdown_text": "Day 1: 台北101", "itinerary_id": "trip-real-jwt"},
                    headers={"Authorization": f"Bearer {token}"},
                )
            assert resp.status_code == 200, f"Expected 200 with real JWT, got {resp.status_code}: {resp.text}"
    finally:
        app.dependency_overrides.pop(get_supabase, None)
        app.dependency_overrides.pop(get_gemini_key, None)

    with patch("services.geocode_service.smart_geocode_logic", new_callable=AsyncMock) as mock_smart:
        mock_smart.return_value = {"results": [{"lat": 46.0207, "lng": 7.7491, "country": "CH"}]}
        anc = await resolve_trip_spatial_anchor({"title": "策馬特滑雪之旅", "destination": "策馬特"}, day_number=1)
        assert anc["lat"] == pytest.approx(46.0207, abs=1e-3)
        assert anc["lng"] == pytest.approx(7.7491, abs=1e-3)
        assert anc["country"] == "CH"


@pytest.mark.asyncio
async def test_sentinel_poc_post_audit_1_import_and_save_daily_locations_anchor_poisoning_and_partial_drop():
    """
    [Red PoC Post-Audit 1 - BLOCK-1]:
    1. When POST /api/trips/import-to-trip is called on a Taipei trip with a polluted `daily_locations`
       (including an unreferenced Day 2 key `{"1": {"name": "首爾", ...}, "2": {"name": "首爾", ...}}`)
       and a homonym item ("龍山寺" at 37.5299, 126.9645), the polluted request.daily_locations MUST NOT hijack
       the Taipei trip's Tier 1 spatial anchor to South Korea (KR)! Both the item and daily_locations["1"]
       must be healed to Taipei (~25.03, ~121.50), and unreferenced poisoned daily_locations["2"] must be evicted.
    2. When POST /api/trips/save-itinerary is called for a 2-day Taipei trip with partial
       `daily_locations` (Day 1 valid Taipei, Day 2 omitted, Day 3 poisoned Seoul), Day 2's resolved daily_locations
       MUST NOT be dropped by Python's `or` short-circuit, and poisoned Day 3 MUST NOT be re-inserted!
    """
    trip_id = "b260f84f-cdea-4a00-a5f1-91564d31d966"
    owner_id = "11111111-1111-1111-1111-111111111111"
    updated_contents = []
    inserted_items = []
    saved_trips = []

    mock_sb = MagicMock()

    def table_side_effect(name):
        tbl = MagicMock()
        if name == "itineraries":
            tbl.select.return_value.eq.return_value.execute.return_value.data = [
                {
                    "id": trip_id,
                    "title": "台北 3 日探索",
                    "created_by": owner_id,
                    "start_date": "2026-05-01",
                    "end_date": "2026-05-03",
                    "content": {"daily_locations": {"1": {"name": "台北", "lat": 25.0330, "lng": 121.5654}}},
                }
            ]

            def capture_update(payload):
                updated_contents.append(payload)
                m = MagicMock()
                m.eq.return_value.execute.return_value.data = [{"id": trip_id}]
                return m

            tbl.update.side_effect = capture_update

            def capture_insert(payload):
                saved_trips.append(payload)
                m = MagicMock()
                m.execute.return_value.data = [{"id": trip_id}]
                return m

            tbl.insert.side_effect = capture_insert
        elif name == "itinerary_items":
            tbl.select.return_value.eq.return_value.execute.return_value.data = []

            def capture_item_insert(payload):
                inserted_items.append(payload)
                m = MagicMock()
                m.execute.return_value.data = payload if isinstance(payload, list) else [payload]
                return m

            tbl.insert.side_effect = capture_item_insert
        elif name == "trip_members":
            tbl.insert.return_value.execute.return_value.data = [{"id": "m1"}]
        elif name == "users":
            tbl.select.return_value.eq.return_value.execute.return_value.data = [{"id": owner_id}]
            tbl.upsert.return_value.execute.return_value.data = [{"id": owner_id}]
        return tbl

    mock_sb.table.side_effect = table_side_effect

    from utils.deps import get_supabase, get_verified_user
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: owner_id
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            # Part 1: import-to-trip with poisoned Seoul daily_locations (including unreferenced Day 2)
            resp = await client.post(
                "/api/trips/import-to-trip",
                headers=HEADERS,
                json={
                    "trip_id": trip_id,
                    "user_id": owner_id,
                    "daily_locations": {
                        "1": {"name": "首爾", "lat": 37.5665, "lng": 126.9780},
                        "2": {"name": "首爾", "lat": 37.5665, "lng": 126.9780},
                    },
                    "items": [
                        {
                            "day_number": 1,
                            "time_slot": "10:00",
                            "place_name": "龍山寺",
                            "category": "sightseeing",
                            "lat": 37.5299,
                            "lng": 126.9645,
                        }
                    ],
                },
            )
            assert resp.status_code == 200, resp.text
            assert len(inserted_items) == 1
            healed_item = inserted_items[0][0]
            assert 24.95 <= healed_item["location_lat"] <= 25.15, f"Anchor poisoning! Got {healed_item['location_lat']}"
            assert len(updated_contents) >= 1
            persisted_dls = updated_contents[0]["content"]["daily_locations"]
            persisted_dl_1 = persisted_dls["1"]
            assert 24.95 <= persisted_dl_1["lat"] <= 25.15, f"Persisted daily_locations['1'] poisoned to {persisted_dl_1}"
            assert "2" not in persisted_dls, f"Unreferenced poisoned daily_locations['2'] was not evicted: {persisted_dls}"

            # Part 2: save-itinerary with partial daily_locations (Day 1 valid, Day 2 omitted, Day 3 poisoned Seoul)
            resp2 = await client.post(
                "/api/trips/save-itinerary",
                headers=HEADERS,
                json={
                    "title": "台北 2 日遊",
                    "creator_name": "Ryan",
                    "user_id": owner_id,
                    "daily_locations": {
                        "1": {"name": "台北信義", "lat": 25.0339, "lng": 121.5644},
                        "3": {"name": "首爾", "lat": 37.5665, "lng": 126.9780},
                    },
                    "items": [
                        {"day_number": 1, "time_slot": "10:00", "place_name": "台北101", "category": "sightseeing", "lat": 25.0339, "lng": 121.5644},
                        {"day_number": 2, "time_slot": "10:00", "place_name": "大稻埕碼頭", "category": "sightseeing", "lat": 25.0569, "lng": 121.5076},
                    ],
                },
            )
            assert resp2.status_code == 200, resp2.text
            saved_dl = saved_trips[0]["content"]["daily_locations"]
            assert "1" in saved_dl and "2" in saved_dl, f"Partial daily_locations dropped Day 2! Got {saved_dl}"
            assert "3" not in saved_dl, f"Poisoned daily_locations['3'] re-inserted in save_itinerary! Got {saved_dl}"
    finally:
        app.dependency_overrides.pop(get_supabase, None)
        app.dependency_overrides.pop(get_verified_user, None)


@pytest.mark.asyncio
async def test_sentinel_poc_post_audit_2_mcp_intra_country_homonym_and_batch_insert():
    """
    [Red PoC Post-Audit 2 - BLOCK-2]:
    When an external MCP AI calls `manage_itinerary_node` (action='add' or 'update') on a Taipei trip
    and passes Lukang Longshan Temple (鹿港龍山寺, 24.0500, 120.4355, ~158km away in Taiwan) or
    Fengshan Longshan Temple (鳳山龍山寺, 22.6258, 120.3601, ~295km away in Taiwan) for `place_name='龍山寺'`,
    the MCP handler MUST reject the >50km homonym drift and heal it to Taipei (~25.0372, 121.4999),
    and execute a batch insert (`isinstance(payload, list)`) with single-item fallback!
    """
    import time
    import uuid
    import jwt
    from utils.deps import get_session_secret, get_supabase

    user_uuid = str(uuid.uuid4())
    trip_uuid = str(uuid.uuid4())
    token = jwt.encode(
        {
            "sub": user_uuid,
            "iss": "tabiji-core",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "type": "device_session",
        },
        get_session_secret(),
        algorithm="HS256",
    )

    inserted_rows = []
    insert_payload_types = []
    mock_sb = MagicMock()

    def table_side_effect(name):
        tbl = MagicMock()
        if name == "itineraries":
            tbl.select.return_value.eq.return_value.execute.return_value.data = [
                {
                    "id": trip_uuid,
                    "title": "台北文化一日遊",
                    "created_by": user_uuid,
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-01",
                    "content": {"daily_locations": {"1": {"name": "台北", "lat": 25.0330, "lng": 121.5654}}},
                }
            ]
        elif name == "itinerary_items":
            tbl.select.return_value.eq.return_value.order.return_value.execute.return_value.data = []

            def capture_insert(payload):
                insert_payload_types.append(type(payload))
                if isinstance(payload, list):
                    inserted_rows.extend(payload)
                else:
                    inserted_rows.append(payload)
                m = MagicMock()
                m.execute.return_value.data = payload if isinstance(payload, list) else [payload]
                return m

            tbl.insert.side_effect = capture_insert
        return tbl

    mock_sb.table.side_effect = table_side_effect
    with patch("routers.mcp.get_supabase", return_value=mock_sb), \
         patch("services.geocode_service.smart_geocode_logic", new_callable=AsyncMock) as mock_geo:
        mock_geo.return_value = {
            "results": [{"name": "艋舺龍山寺", "lat": 25.0372, "lng": 121.4999, "country": "TW"}]
        }
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/api/mcp",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "jsonrpc": "2.0",
                    "id": 99,
                    "method": "tools/call",
                    "params": {
                        "name": "manage_itinerary_node",
                        "arguments": {
                            "trip_id": trip_uuid,
                            "day_index": 1,
                            "action": "add",
                            "places": [
                                {
                                    "place_name": "龍山寺",
                                    "lat": 24.0500,  # 鹿港龍山寺 (~158km from Taipei, < 500km!)
                                    "lng": 120.4355,
                                }
                            ],
                        },
                    },
                },
            )
        assert resp.status_code == 200
        assert len(inserted_rows) == 1
        assert insert_payload_types == [list], f"Expected batch insert with list payload, got {insert_payload_types}"
        assert 24.95 <= inserted_rows[0]["location_lat"] <= 25.15, (
            f"Intra-country homonym (Lukang 24.05) bypassed MCP 500km check! Got {inserted_rows[0]['location_lat']}"
        )

        # Part 2: Verify single-item fallback when batch insert raises an exception
        fallback_rows = []
        fallback_calls = []

        def table_fallback_side_effect(name):
            tbl = MagicMock()
            if name == "itineraries":
                tbl.select.return_value.eq.return_value.execute.return_value.data = [
                    {
                        "id": trip_uuid,
                        "title": "台北文化一日遊",
                        "created_by": user_uuid,
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-01",
                        "content": {"daily_locations": {"1": {"name": "台北", "lat": 25.0330, "lng": 121.5654}}},
                    }
                ]
            elif name == "itinerary_items":
                tbl.select.return_value.eq.return_value.order.return_value.execute.return_value.data = []

                def capture_fallback_insert(payload):
                    fallback_calls.append(type(payload))
                    m = MagicMock()
                    if isinstance(payload, list):
                        m.execute.side_effect = RuntimeError("Simulated PostgREST batch error")
                    else:
                        fallback_rows.append(payload)
                        m.execute.return_value.data = [payload]
                    return m

                tbl.insert.side_effect = capture_fallback_insert
            return tbl

        mock_sb.table.side_effect = table_fallback_side_effect
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp_fb = await client.post(
                "/api/mcp",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "jsonrpc": "2.0",
                    "id": 100,
                    "method": "tools/call",
                    "params": {
                        "name": "manage_itinerary_node",
                        "arguments": {
                            "trip_id": trip_uuid,
                            "day_index": 1,
                            "action": "add",
                            "places": [
                                {"place_name": "台北101", "lat": 25.0339, "lng": 121.5644},
                                {"place_name": "中正紀念堂", "lat": 25.0347, "lng": 121.5219},
                            ],
                        },
                    },
                },
            )
        assert resp_fb.status_code == 200
        assert fallback_calls == [list, dict, dict], f"Expected [list, dict, dict] fallback sequence, got {fallback_calls}"
        assert [r["place_name"] for r in fallback_rows] == ["台北101", "中正紀念堂"]


@pytest.mark.asyncio
async def test_sentinel_poc_post_audit_3_create_item_non_empty_hallucinated_coords_healed():
    """
    [Red PoC Post-Audit 3 - BLOCK-3]:
    When POST /api/trips/items (`create_item`) is called on a Taipei trip with non-empty
    cross-country hallucinated coordinates (`place_name='龍山寺', lat=37.5299, lng=126.9645`),
    `create_item` MUST validate against the trip's spatial anchor and heal it to Taipei (~25.0372, 121.4999)!
    """
    trip_id = "b260f84f-cdea-4a00-a5f1-91564d31d966"
    owner_id = "11111111-1111-1111-1111-111111111111"
    inserted_single = []

    mock_sb = MagicMock()

    def table_side_effect(name):
        tbl = MagicMock()
        if name == "trip_members":
            tbl.select.return_value.eq.return_value.eq.return_value.execute.return_value.data = [{"user_id": owner_id}]
        elif name == "itineraries":
            tbl.select.return_value.eq.return_value.execute.return_value.data = [
                {"id": trip_id, "title": "台北古蹟遊", "content": {"daily_locations": {"1": {"name": "台北", "lat": 25.0330, "lng": 121.5654}}}}
            ]
        elif name == "itinerary_items":
            tbl.select.return_value.eq.return_value.execute.return_value.data = []

            def capture_insert(payload):
                inserted_single.append(payload)
                m = MagicMock()
                m.execute.return_value.data = [{**payload, "id": "item-new-1"}]
                return m

            tbl.insert.side_effect = capture_insert
        return tbl

    mock_sb.table.side_effect = table_side_effect
    from utils.deps import get_supabase, get_verified_user
    app.dependency_overrides[get_supabase] = lambda: mock_sb
    app.dependency_overrides[get_verified_user] = lambda: owner_id
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
                        "itinerary_id": trip_id,
                        "day_number": 1,
                        "time_slot": "14:00",
                        "place_name": "龍山寺",
                        "category": "sightseeing",
                        "lat": 37.5299,
                        "lng": 126.9645,
                    },
                )
            assert resp.status_code == 200
            assert len(inserted_single) == 1
            assert 24.95 <= inserted_single[0]["location_lat"] <= 25.15, (
                f"create_item accepted Seoul coords (37.5299) without spatial healing! Got {inserted_single[0]['location_lat']}"
            )
    finally:
        app.dependency_overrides.pop(get_supabase, None)
        app.dependency_overrides.pop(get_verified_user, None)


@pytest.mark.asyncio
async def test_sentinel_poc_post_audit_4_oauth_authorize_state_url_encoding():
    """
    [Red PoC Post-Audit 4 - BLOCK-4]:
    When GET /api/oauth/authorize is called with a `state` containing `&`, `=`, `+`, or `#`
    (e.g. `state="csrf=1&evil_param=injected#frag"`), `oauth_authorize` MUST URL-encode `state`
    in the 302 Location header so that `evil_param` is not injected as a top-level query param!
    """
    import uuid
    import urllib.parse
    valid_uid = str(uuid.uuid4())
    raw_state = "csrf=1&evil_param=injected#frag"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver", follow_redirects=False) as client:
        resp = await client.get(
            "/api/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": valid_uid,
                "redirect_uri": "https://www.perplexity.ai/rest/connections/oauth_callback",
                "state": raw_state,
            },
        )
    assert resp.status_code == 302
    loc = resp.headers["location"]
    parsed = urllib.parse.urlparse(loc)
    qs = urllib.parse.parse_qs(parsed.query)
    assert "evil_param" not in qs, f"Unescaped state injected top-level query param! Location: {loc}"
    assert parsed.fragment == "", f"Unescaped state injected URL fragment! Location: {loc}"
    assert qs.get("state") == [raw_state], f"Decoded state mismatch: {qs.get('state')}"


def test_sentinel_poc_post_audit_5_trip_dialogs_clears_stale_daily_locations_on_merge():
    """
    [Red PoC Post-Audit 5 - BLOCK-5]:
    In `frontend/components/itinerary/TripDialogs.tsx`, when `saveTarget === 'existing'` in
    `handleSaveAiOrImportTrip`, `tripsApi.importToTrip` MUST pass `daily_locations: {}` so that
    stale `result.daily_locations` from a prior parse cannot overwrite the target existing trip's
    spatial anchor if the user switches target trips on the preview screen.
    """
    from pathlib import Path
    tsx_path = Path(__file__).resolve().parents[2] / "frontend" / "components" / "itinerary" / "TripDialogs.tsx"
    tsx_content = tsx_path.read_text(encoding="utf-8")
    assert "const data = await tripsApi.importToTrip(targetId, {" in tsx_content
    import_block = tsx_content.split("const data = await tripsApi.importToTrip(targetId, {")[1].split("})")[0]
    assert "daily_locations: {}," in import_block, (
        f"TripDialogs.tsx importToTrip still passes stale result.daily_locations! Block:\\n{import_block}"
    )



