# -*- coding: utf-8 -*-
"""
Security Sentinel & Top-K Overhaul Verification Test Suite (Scope B + Safety Nets 1-4)
Standard: In-Memory Pytest + Mantis Block G Benign Control (Zero Live Network)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request

import services.geocode_service as gs
from models.base import GeocodeSearchRequest
from routers.geocode import geocode_search
from services.geocode_service import (
    COUNTRY_BOUNDS,
    __reset_geocode_runtime_state_for_testing,
    _detect_city_prefix_anchor,
    _extract_clean_place_query,
    _is_chain_brand_entry,
    _translate_via_micro_dict,
    cjk_text_similarity,
    rerank_top_k,
    resolve_fusion_anchor_coords,
    smart_geocode_logic,
    translate_famous_landmark,
)
from services.smart_search_service import _soft_filter_overpass_pois


def _make_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/geocode/search",
        "headers": [],
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def reset_geo_runtime():
    __reset_geocode_runtime_state_for_testing()
    yield
    __reset_geocode_runtime_state_for_testing()


# ==============================================================================
# AC-PBT-1: CJK Ordered-Subsequence, Anti-Subset & Bigram Recall Conservation
# ==============================================================================
def test_pbt_cjk_text_similarity_ordered_subseq_anti_subset_and_bigram():
    # Ordered subsequence with bigram recall
    assert cjk_text_similarity("桃園機場", "臺灣桃園國際機場") >= 0.85

    # Reordered characters MUST NOT score high
    assert cjk_text_similarity("台中", "臺中市") > 0.90
    assert cjk_text_similarity("台中", "中台禪寺") < 0.60
    assert cjk_text_similarity("台中", "臺中市") > cjk_text_similarity("台中", "中台禪寺")

    # Short subset target MUST be discounted below full match
    assert cjk_text_similarity("大阪燒", "大阪燒肉雙子") >= 0.85
    assert cjk_text_similarity("大阪燒", "大阪") < 0.80
    assert cjk_text_similarity("大阪燒", "大阪燒肉雙子") > cjk_text_similarity("大阪燒", "大阪")

    # Branch / flagship specificity
    assert cjk_text_similarity("一蘭總店", "一蘭") < 0.50
    assert cjk_text_similarity("新宿一蘭拉麵", "一蘭 新宿中央東口店") > cjk_text_similarity("新宿一蘭拉麵", "一蘭拉麵")


# ==============================================================================
# AC-GEO-1 (B1): Full-Distance Exact Gate, Chain Exclusion & Zero Overwrite
# ==============================================================================
@pytest.mark.asyncio
async def test_b1_blocks_substring_and_chain_hijack_preserves_branch_name():
    # 1. BRANDS_DB exact match preserves display_name (sentinel L129-130), landmark_data is None
    terms_exact, disp_exact, lm_exact = translate_famous_landmark("一蘭", country_code="JP")
    assert disp_exact is not None
    assert lm_exact is None
    assert any("ラーメン" in t for t in terms_exact)

    # 2. BRANDS_DB substring preserves area prefix and sets display_name=None
    terms_sub, disp_sub, lm_sub = translate_famous_landmark("新宿一蘭拉麵", country_code="JP")
    assert disp_sub is None
    assert lm_sub is None
    assert any("新宿" in t and "一蘭" in t for t in terms_sub)

    # 3. Substring / facility-tail queries MUST NOT match LANDMARKS_DB
    for blocked_q, cc in [
        ("台南龍山寺", "TW"),
        ("龍山寺站", "TW"),
        ("台北101美食", "TW"),
        ("東京迪士尼飯店", "JP"),
    ]:
        _, disp, lm = translate_famous_landmark(blocked_q, country_code=cc)
        assert lm is None, f"Query '{blocked_q}' must not match LANDMARKS_DB entry"
        assert disp is None, f"Query '{blocked_q}' must not inject landmark display"

    # 4. All BRANDS_DB overlapping entries in LANDMARKS_DB are recognized as chain brands
    gs.get_fuzzy_index()
    assert _is_chain_brand_entry("一蘭拉麵", gs.LANDMARKS_DB.get("一蘭拉麵"), "一蘭拉麵", "一蘭拉麵") is True
    assert _is_chain_brand_entry("一蘭 新宿中央東口店", gs.LANDMARKS_DB.get("一蘭 新宿中央東口店"), "一蘭 新宿中央東口店", "一蘭 新宿中央東口店") is True
    assert _is_chain_brand_entry("敘敘苑", gs.LANDMARKS_DB.get("敘敘苑"), "敘敘苑", "敘敘苑") is True
    assert _is_chain_brand_entry("東京鐵塔", gs.LANDMARKS_DB.get("東京鐵塔"), "東京鐵塔", "東京鐵塔") is False

    # 5. Tokyo searching '新宿一蘭拉麵' MUST NOT instant-return Shibuya or overwrite branch name
    shinjuku_branches = [
        {"lat": 35.6908, "lng": 139.7027, "name": "一蘭 新宿中央東口店", "address": "Shinjuku", "type": "restaurant", "osm_id": 5001},
        {"lat": 35.6617, "lng": 139.7037, "name": "一蘭 澀谷店", "address": "Shibuya", "type": "restaurant", "osm_id": 5002},
    ]
    with patch("services.geocode_service.geocode_with_photon", new=AsyncMock(return_value=shinjuku_branches)), \
         patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(status_code=200, json=lambda: []))):
        res = await smart_geocode_logic("新宿一蘭拉麵", limit=None, lat=35.6895, lng=139.6917, country="JP")
    assert res["source"] != "landmarks_db"
    assert res["results"][0]["name"] == "一蘭 新宿中央東口店"

    # 6. Tokyo searching '東京迪士尼飯店' MUST NOT instant-return Disneyland park
    disney_hotels = [
        {"lat": 35.6361, "lng": 139.8832, "name": "東京迪士尼樂園大飯店", "address": "Urayasu", "type": "hotel", "osm_key": "tourism", "osm_id": 6001},
    ]
    with patch("services.geocode_service.geocode_with_photon", new=AsyncMock(return_value=disney_hotels)), \
         patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(status_code=200, json=lambda: []))):
        res_hotel = await smart_geocode_logic("東京迪士尼飯店", limit=None, lat=35.6895, lng=139.6917, country="JP")
    assert res_hotel["source"] != "landmarks_db"
    assert res_hotel["results"][0]["name"] == "東京迪士尼樂園大飯店"


@pytest.mark.asyncio
async def test_b1_benign_homonym_distance_and_exact_unique_landmark_instant_return():
    # Benign 1: Taipei searching exact '東京鐵塔' (>80km, unique, non-chain) -> 0ms landmarks_db
    res_tower = await smart_geocode_logic("東京鐵塔", limit=None, lat=25.0339, lng=121.5645)
    assert res_tower["source"] == "landmarks_db"
    assert abs(res_tower["results"][0]["lat"] - 35.6586) < 0.01

    # Benign 2: Taipei searching exact bare '龍山寺' (<=80km) -> deterministic offline CI pass
    res_taipei_ls = await smart_geocode_logic("龍山寺", limit=1, lat=25.0460, lng=121.5053, country="TW")
    assert res_taipei_ls["source"] == "landmarks_db"
    assert abs(res_taipei_ls["results"][0]["lat"] - 25.0372) < 0.02

    # Homonym Guard: Kaohsiung (>80km) OR no-coords searching bare '龍山寺' MUST NOT instant-return Taipei!
    kaohsiung_cands = [
        {"lat": 22.6258, "lng": 120.3601, "name": "鳳山龍山寺", "address": "高雄市鳳山區", "type": "place_of_worship", "osm_key": "amenity", "importance": 0.35, "osm_id": 7001},
        {"lat": 22.6255, "lng": 120.3605, "name": "龍山寺", "address": "高雄市鳳山區", "type": "bus_stop", "osm_key": "highway", "importance": None, "osm_id": 7002},
    ]
    with patch("services.geocode_service.geocode_with_photon", new=AsyncMock(return_value=[kaohsiung_cands[1]])), \
         patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(status_code=200, json=lambda: [{
             "lat": "22.6258", "lon": "120.3601", "name": "鳳山龍山寺",
             "display_name": "鳳山龍山寺, 鳳山區, 高雄市, 台灣",
             "type": "place_of_worship", "class": "amenity", "osm_id": 7001, "osm_type": "way",
             "importance": 0.35, "address": {"city": "高雄市", "country": "台灣"}, "extratags": {},
         }]))):
        res_kh = await smart_geocode_logic("龍山寺", limit=None, lat=22.6273, lng=120.3014, country="TW")
    assert res_kh["source"] != "landmarks_db"
    # AC-GEO-2: Temple MUST outrank bus_stop even when Photon bus_stop has importance=None!
    assert res_kh["results"][0]["name"] == "鳳山龍山寺"

    # No-coords bare '龍山寺' also blocked from single-point instant return AND does NOT leak 'Lungshan Temple Taipei' into Photon queries!
    captured_nocoord_q = []

    async def fake_photon_nocoord(q, limit=25, lat=None, lng=None, zoom=None, location_bias_scale=None, osm_tag=None, country_code=None, bbox=None):
        captured_nocoord_q.append(q)
        return kaohsiung_cands

    with patch("services.geocode_service.geocode_with_photon", side_effect=fake_photon_nocoord), \
         patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(status_code=200, json=lambda: []))):
        res_nocoord = await smart_geocode_logic("龍山寺", limit=None, lat=None, lng=None)
    assert res_nocoord["source"] != "landmarks_db"
    assert all("Taipei" not in q for q in captured_nocoord_q), f"Leaked Taipei alias: {captured_nocoord_q}"


# ==============================================================================
# AC-GEO-2 (B2): Monotonic Cross-Script Floor, _batch_rank & Temple vs Station
# ==============================================================================
def test_b2_monotonic_cross_script_and_batch_rank_and_temple_vs_bus_stop():
    # 1. When Latin variant is already in query_variants, unrelated Latin store MUST NOT beat partial match
    cands = [
        {"lat": 48.1375, "lng": 11.5755, "name": "Random Bakery", "type": "bakery", "source": "photon", "_batch_rank": 0},
        {"lat": 48.1378, "lng": 11.5754, "name": "Neues Rathaus", "type": "townhall", "source": "photon", "_batch_rank": 1},
    ]
    ranked = rerank_top_k(
        cands, query="市政廳", bias_lat=48.1371, bias_lng=11.5754,
        target_country="DE", limit=None, query_variants=["Munich Rathaus", "Rathaus", "市政廳"],
    )
    assert ranked[0]["name"] == "Neues Rathaus"
    assert "_batch_rank" not in ranked[0]

    # 2. Temple beats bus stop, while explicit station query still puts station #1
    ls_cands = [
        {"lat": 22.6255, "lng": 120.3605, "name": "龍山寺", "type": "bus_stop", "osm_key": "highway", "source": "photon", "_batch_rank": 0},
        {"lat": 22.6258, "lng": 120.3601, "name": "鳳山龍山寺", "type": "place_of_worship", "osm_key": "amenity", "importance": 0.35, "source": "nominatim", "_batch_rank": 0},
    ]
    ranked_temple = rerank_top_k(ls_cands, query="龍山寺", bias_lat=22.6273, bias_lng=120.3014, target_country="TW", limit=None)
    assert ranked_temple[0]["name"] == "鳳山龍山寺"

    st_cands = [
        {"lat": 25.0372, "lng": 121.4999, "name": "艋舺龍山寺", "type": "place_of_worship", "osm_key": "amenity", "importance": 0.55, "source": "nominatim"},
        {"lat": 25.0352, "lng": 121.4998, "name": "龍山寺", "type": "station", "osm_key": "railway", "importance": 0.45, "source": "photon"},
    ]
    ranked_st = rerank_top_k(st_cands, query="龍山寺站", bias_lat=25.0370, bias_lng=121.5000, target_country="TW", limit=None)
    assert ranked_st[0]["type"] == "station"


# ==============================================================================
# AC-GEO-3 (B3): City-Prefix Spatial Anchor Switch & Preserved Micro-Dict Contract
# ==============================================================================
@pytest.mark.asyncio
async def test_b3_city_prefix_anchor_munich_city_hall_from_taipei_and_country_bounds():
    # Micro-dict contract strictly unchanged
    assert _translate_via_micro_dict("札幌車站", "JP") == ["Sapporo 駅", "Sapporo Station"]
    assert _translate_via_micro_dict("那霸機場", "JP") == ["Naha 空港", "Naha Airport"]

    # Culinary dish '大阪燒' MUST NOT switch city anchor away from Taipei
    assert _detect_city_prefix_anchor("大阪燒") is None
    # Real city-prefix queries switch anchor
    hit_muc = _detect_city_prefix_anchor("慕尼黑市政廳")
    assert hit_muc is not None and hit_muc[1]["country"] == "DE" and hit_muc[2] == "市政廳"
    hit_tn = _detect_city_prefix_anchor("台南龍山寺")
    assert hit_tn is not None and hit_tn[1]["country"] == "TW"

    # Expanded COUNTRY_BOUNDS (80+ countries)
    assert len(COUNTRY_BOUNDS) >= 75
    assert "EG" in COUNTRY_BOUNDS and "LU" in COUNTRY_BOUNDS and "AR" in COUNTRY_BOUNDS

    captured_photon_coords = []

    async def fake_photon(q, limit=25, lat=None, lng=None, zoom=None, location_bias_scale=None, osm_tag=None, country_code=None, bbox=None):
        captured_photon_coords.append((q, lat, lng, bbox))
        return [
            {"lat": 45.6305, "lng": -94.7525, "name": "New Munich City Hall", "address": "Minnesota, USA", "type": "townhall", "osm_key": "amenity", "osm_id": 8001},
            {"lat": 48.1378, "lng": 11.5754, "name": "Neues Rathaus", "address": "Marienplatz, Munich, Germany", "type": "townhall", "osm_key": "amenity", "osm_id": 8002},
        ]

    with patch("services.geocode_service.geocode_with_photon", side_effect=fake_photon), \
         patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(status_code=200, json=lambda: []))):
        res = await smart_geocode_logic(
            query="慕尼黑市政廳",
            limit=None,
            trip_title="3 Day Taipei Explorer",
            lat=25.0339,
            lng=121.5645,
            bbox="121.45,24.95,121.65,25.15",
        )
    assert res["results"][0]["name"] == "Neues Rathaus"
    assert all(b is None for _, _, _, b in captured_photon_coords)
    assert any(c_lat is not None and abs(c_lat - 48.1351) < 0.05 for _, c_lat, _, _ in captured_photon_coords)


# ==============================================================================
# AC-GEO-4 (B4): Safe Fusion Anchor Resolution, Soft Filter, Dedup & Limit Slice
# ==============================================================================
@pytest.mark.asyncio
async def test_b4_fusion_skips_when_anchorless_dedupes_and_enforces_limit():
    # 1. Anchorless generic query ('ramen') MUST resolve (None, None) and skip smart_search (NO blind Tokyo!)
    assert resolve_fusion_anchor_coords(None, None, "ramen", None, None, None) == (None, None)
    # Subdistrict 'Shinjuku ramen' resolves Shinjuku coords
    sj_lat, sj_lng = resolve_fusion_anchor_coords(None, None, "Shinjuku ramen", None, None, None)
    assert abs(sj_lat - 35.6938) < 0.01 and abs(sj_lng - 139.7034) < 0.01

    req = _make_request()
    base_geo = {"results": [{"name": "Local Ramen", "lat": 25.03, "lng": 121.56}]}
    with patch("routers.geocode.smart_geocode_logic", new_callable=AsyncMock, return_value=base_geo), \
         patch("routers.geocode.is_poi_query", return_value=True), \
         patch("routers.geocode.smart_search", new_callable=AsyncMock) as mock_smart:
        res_no_anchor = await geocode_search(req, GeocodeSearchRequest(query="ramen", limit=5), x_gemini_key="k")
    mock_smart.assert_not_called()
    assert res_no_anchor == base_geo

    # 2. Fusion deduplicates same-normalized-name <50m AND enforces body.limit without 2nd rerank_top_k
    smart_payload = {
        "results": [
            {"name": "Ichiran Shinjuku", "lat": 35.6908, "lng": 139.7027, "address": "Shinjuku"},
            {"name": "Fuunji Ramen", "lat": 35.6868, "lng": 139.6994, "address": "Shinjuku"},
        ]
    }
    base_with_dup = {
        "results": [
            {"name": "Ichiran Shinjuku", "lat": 35.69081, "lng": 139.70271, "source": "photon"},  # <50m same name dup
            {"name": "Base Geo Kept Order", "lat": 35.695, "lng": 139.705, "source": "nominatim"},
        ]
    }
    with patch("routers.geocode.smart_geocode_logic", new_callable=AsyncMock, return_value=base_with_dup), \
         patch("routers.geocode.is_poi_query", return_value=True), \
         patch("routers.geocode.smart_search", new_callable=AsyncMock, return_value=smart_payload):
        res_lim = await geocode_search(req, GeocodeSearchRequest(query="Shinjuku ramen", limit=2), x_gemini_key="k")
        res_all = await geocode_search(req, GeocodeSearchRequest(query="Shinjuku ramen", limit=5), x_gemini_key="k")

    assert len(res_lim["results"]) == 2
    assert [r["name"] for r in res_all["results"]] == ["Ichiran Shinjuku", "Fuunji Ramen", "Base Geo Kept Order"]

    # 3. Overpass soft filter prioritizes cuisine/name match and falls back cleanly if all unmatched
    raw_pois = [
        {"name": "Trattoria Bella", "cuisine": "italian", "category": "restaurant"},
        {"name": "Menya Sho", "cuisine": "ramen", "category": "restaurant"},
    ]
    filtered = _soft_filter_overpass_pois(raw_pois, "ramen", ["新宿拉麵"], "新宿")
    assert [p["name"] for p in filtered] == ["Menya Sho"]

    unmatched_fallback = _soft_filter_overpass_pois([raw_pois[0]], "ramen", ["拉麵"], None)
    assert len(unmatched_fallback) == 1 and unmatched_fallback[0]["name"] == "Trattoria Bella"


# ==============================================================================
# AC-GEO-5 (B5) & Safety Net (1): limit=1 Upstream Pool >= 15 & Paren Fallback
# ==============================================================================
@pytest.mark.asyncio
async def test_b5_limit_one_upstream_pool_and_backend_single_pass_paren_fallback():
    captured_limits = []

    async def fake_photon_pool(q, limit=25, lat=None, lng=None, zoom=None, location_bias_scale=None, osm_tag=None, country_code=None, bbox=None):
        captured_limits.append(limit)
        return [
            {"lat": 25.03 + i * 0.001, "lng": 121.56, "name": f"Cafe Spot {i}", "type": "cafe", "osm_id": 9100 + i}
            for i in range(5)
        ]

    with patch("services.geocode_service.geocode_with_photon", side_effect=fake_photon_pool), \
         patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(status_code=200, json=lambda: []))):
        res_one = await smart_geocode_logic("Cafe Spot", limit=1, lat=25.03, lng=121.56)
    assert len(res_one["results"]) == 1
    assert captured_limits and captured_limits[0] >= 15

    # Backend single-pass parenthetical fallback: '淺草寺 (雷門拍照)' -> '淺草寺'
    assert _extract_clean_place_query("淺草寺 (雷門拍照)") == "淺草寺"
    assert _extract_clean_place_query("10:00 築地市場（海鮮早餐）") == "築地市場"

    queried = []

    async def fake_photon_paren(q, limit=25, lat=None, lng=None, zoom=None, location_bias_scale=None, osm_tag=None, country_code=None, bbox=None):
        queried.append(q)
        if "雷門拍照" in q:
            return []
        return [{"lat": 35.7148, "lng": 139.7967, "name": "淺草寺", "type": "temple", "osm_id": 9200}]

    with patch("services.geocode_service.geocode_with_photon", side_effect=fake_photon_paren), \
         patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(status_code=200, json=lambda: []))):
        res_paren = await smart_geocode_logic("淺草寺 (雷門拍照)", limit=None, lat=35.71, lng=139.79, country="JP", allow_overpass=False)
    assert len(res_paren["results"]) >= 1
    assert res_paren["results"][0]["name"] == "淺草寺"

    # Single-pass guard: if fallback ALSO returns empty, MUST terminate without recursion
    with patch("services.geocode_service.geocode_with_photon", new=AsyncMock(return_value=[])), \
         patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(status_code=200, json=lambda: []))):
        res_empty = await smart_geocode_logic("不存在神祕地點 (測試備註)", limit=None, allow_overpass=False)
    assert res_empty["results"] == []


# ==============================================================================
# Adversarial Review Regression Guards (6 Real Bugs Fixed Post-Prior-Attempt)
# ==============================================================================
@pytest.mark.asyncio
async def test_adversarial_fixes_shinjuku_ichiran_disney_hotel_fast_paren_and_dish_fusion():
    # 1. Fusion anchor dish guard: '大阪燒' with region='台北' MUST resolve Taipei, NOT Osaka!
    tp_lat, tp_lng = resolve_fusion_anchor_coords(None, None, "大阪燒", "台北", "台北美食", None)
    assert tp_lat is not None and tp_lng is not None
    assert abs(tp_lat - 25.033) < 0.05 and abs(tp_lng - 121.5654) < 0.05

    # 2. Substring JP chain brand strips generic OSM tag tail ('ラーメン') so Shinjuku branches crush Saitama!
    terms_sj, disp_sj, lm_sj = translate_famous_landmark("新宿一蘭拉麵", country_code="JP")
    assert disp_sj is None and lm_sj is None
    assert "新宿 一蘭" in terms_sj
    assert all("ラーメン" not in t for t in terms_sj)

    # Even if Saitama '一蘭(ラーメン)' is mixed into candidates with Shinjuku OSM '一蘭' (address='東京都新宿区...'),
    # subdistrict half_life=5km + prefix-address credit MUST rank Shinjuku #1!
    mixed_ichiran = [
        {"lat": 35.9588, "lng": 139.6541, "name": "一蘭(ラーメン)", "address": "埼玉県さいたま市", "city": "さいたま市", "type": "fast_food", "source": "photon", "_batch_rank": 0},
        {"lat": 35.6944, "lng": 139.7016, "name": "一蘭", "address": "東京都新宿区歌舞伎町", "city": "東京都", "type": "restaurant", "source": "photon", "_batch_rank": 1},
    ]
    ranked_sj = rerank_top_k(
        mixed_ichiran,
        query="新宿一蘭拉麵",
        bias_lat=35.6938,
        bias_lng=139.7034,
        target_country="JP",
        limit=None,
        query_variants=["新宿 一蘭", "新宿一蘭拉麵"],
        is_subdistrict_anchor=True,
        prefix_label="新宿",
    )
    assert ranked_sj[0]["name"] == "一蘭"
    assert abs(ranked_sj[0]["lat"] - 35.6944) < 0.01

    # 3. Landmark + Facility micro-dict & anchor switch ('東京迪士尼飯店' -> Urayasu Disney Hotel, hotel beats bus_stop!)
    disney_terms = _translate_via_micro_dict("東京迪士尼飯店", "JP")
    assert "Tokyo Disneyland Hotel" in disney_terms
    assert "東京ディズニーランドホテル" in disney_terms
    # Subdistrict + Facility also supported without breaking city contract
    assert _translate_via_micro_dict("札幌車站", "JP") == ["Sapporo 駅", "Sapporo Station"]
    assert "Shinjuku Hotel" in _translate_via_micro_dict("新宿飯店", "JP")

    disney_anchor = _detect_city_prefix_anchor("東京迪士尼飯店")
    assert disney_anchor is not None
    assert abs(disney_anchor[1]["lat"] - 35.6329) < 0.02

    disney_hotel_vs_bus = [
        {"lat": 35.6372, "lng": 139.8780, "name": "東京ディズニーランドホテル", "type": "bus_stop", "osm_key": "highway", "source": "photon", "_batch_rank": 0},
        {"lat": 35.6368, "lng": 139.8783, "name": "東京ディズニーランドホテル", "type": "hotel", "osm_key": "tourism", "source": "photon", "_batch_rank": 1},
    ]
    ranked_dh = rerank_top_k(
        disney_hotel_vs_bus,
        query="東京迪士尼飯店",
        bias_lat=35.6329,
        bias_lng=139.8804,
        target_country="JP",
        limit=None,
        query_variants=["Tokyo Disneyland Hotel", "東京ディズニーランドホテル", "東京迪士尼飯店", "ホテル", "Hotel"],
        is_subdistrict_anchor=True,
        prefix_label="東京迪士尼",
    )
    assert ranked_dh[0]["type"] == "hotel"

    # 4. Fast parenthetical fallback MUST skip slow Nominatim/Overpass on the noisy raw pass when speculative Photon returns []!
    mock_nom = AsyncMock(return_value=MagicMock(status_code=200, json=lambda: []))
    mock_overpass = AsyncMock(return_value=None)
    with patch("services.geocode_service.geocode_with_photon", new=AsyncMock(return_value=[])), \
         patch("httpx.AsyncClient.get", new=mock_nom), \
         patch("services.geocode_service.search_overpass_by_name", new=mock_overpass):
        res_fast_paren = await smart_geocode_logic(
            "淺草寺 (雷門拍照)", limit=1, lat=35.71, lng=139.79, country="JP", allow_overpass=True
        )
    assert res_fast_paren["source"] == "landmarks_db"
    assert res_fast_paren["results"][0]["name"] == "淺草寺"
    assert mock_nom.call_count == 0, "Noisy raw parenthetical pass must NOT waste time calling Nominatim"
    assert mock_overpass.call_count == 0, "Noisy raw parenthetical pass must NOT waste time calling Overpass"


@pytest.mark.asyncio
async def test_explicit_city_nominatim_fallback_locks_country_and_retries_admin_region():
    """
    Production Resilience Regression (Live Cloud Run 2026-11-23):
    When Photon transiently returns [] for an explicit city in GLOBAL_CITY_ANCHORS:
    1) '那霸' MUST pass countrycodes='jp' to Nominatim so pinyin homophones in China ('那巴'/'那坝') never poison results.
    2) '沖繩' (is_admin_region=True) MUST NOT break after 1st Nominatim call returning only city '沖縄市';
       it must proceed to the 2nd variant ('Okinawa') to capture province '沖縄県'.
    """
    captured_naha_params = []

    async def fake_naha_get(url, params=None, headers=None):
        captured_naha_params.append(dict(params or {}))
        return MagicMock(
            status_code=200,
            json=lambda: [
                {
                    "lat": "26.2122",
                    "lon": "127.6791",
                    "name": "那覇市",
                    "display_name": "那覇市, 沖縄県, 日本",
                    "class": "boundary",
                    "type": "administrative",
                    "addresstype": "city",
                    "osm_id": 4004422,
                    "osm_type": "relation",
                    "address": {"city": "那覇市", "state": "沖縄県", "country": "日本", "country_code": "jp"},
                    "extratags": {"admin_level": "7"},
                    "importance": 0.65,
                }
            ],
        )

    with patch("services.geocode_service.geocode_with_photon", new=AsyncMock(return_value=[])), \
         patch("services.geocode_service._nominatim_rate_limit_wait", new=AsyncMock()), \
         patch("httpx.AsyncClient.get", side_effect=fake_naha_get):
        res_naha = await smart_geocode_logic("那霸", limit=5)

    assert len(captured_naha_params) == 1
    assert captured_naha_params[0].get("countrycodes") == "jp", f"Expected countrycodes=jp, got {captured_naha_params[0]}"
    assert res_naha["results"][0]["name"] == "那覇市"
    assert abs(res_naha["results"][0]["lat"] - 26.2122) < 0.01

    captured_oki_params = []

    async def fake_oki_get(url, params=None, headers=None):
        captured_oki_params.append(dict(params or {}))
        q = (params or {}).get("q", "")
        if q == "沖縄":
            return MagicMock(
                status_code=200,
                json=lambda: [
                    {
                        "lat": "26.3344",
                        "lon": "127.8057",
                        "name": "沖縄市",
                        "display_name": "沖縄市, 沖縄県, 日本",
                        "class": "boundary",
                        "type": "administrative",
                        "addresstype": "city",
                        "osm_id": 4004427,
                        "osm_type": "relation",
                        "address": {"city": "沖縄市", "state": "沖縄県", "country": "日本", "country_code": "jp"},
                        "extratags": {"admin_level": "7"},
                        "importance": 0.55,
                    }
                ],
            )
        return MagicMock(
            status_code=200,
            json=lambda: [
                {
                    "lat": "26.5707",
                    "lon": "128.0255",
                    "name": "沖縄県",
                    "display_name": "沖縄県, 日本",
                    "class": "boundary",
                    "type": "administrative",
                    "addresstype": "province",
                    "osm_id": 3795658,
                    "osm_type": "relation",
                    "address": {"province": "沖縄県", "country": "日本", "country_code": "jp"},
                    "extratags": {"admin_level": "4"},
                    "importance": 0.72,
                }
            ],
        )

    with patch("services.geocode_service.geocode_with_photon", new=AsyncMock(return_value=[])), \
         patch("services.geocode_service._nominatim_rate_limit_wait", new=AsyncMock()), \
         patch("httpx.AsyncClient.get", side_effect=fake_oki_get):
        res_oki = await smart_geocode_logic("沖繩", limit=5)

    assert len(captured_oki_params) == 2, f"Admin region fallback must retry 2nd variant when 1st only returns city: {captured_oki_params}"
    assert all(p.get("countrycodes") == "jp" for p in captured_oki_params)
    assert res_oki["results"][0]["name"] == "沖縄県"
    assert res_oki["results"][0]["type"] == "province"
