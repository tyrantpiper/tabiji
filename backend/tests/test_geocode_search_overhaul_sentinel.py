# -*- coding: utf-8 -*-
"""
Security Sentinel & Overhaul Verification Test Suite
Topic: Global Map Search, Multilingual Geocoding, Unlimited Smart-Ranked Results & Edge Safety Nets
Standard: In-Memory Pytest + Mantis Block G Benign Control
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import services.geocode_service as gs
import services.model_manager as mm
from models.base import GeocodeSearchRequest
from services.geocode_service import (
    __reset_geocode_runtime_state_for_testing,
    _get_nominatim_lock,
    _strip_wiki_parenthetical,
    cjk_text_similarity,
    filter_results_by_country,
    geocode_with_photon,
    get_country_display_name,
    infer_country_from_coords,
    normalize_cjk_chars,
    normalize_extent,
    rerank_top_k,
    smart_geocode_logic,
    translate_famous_landmark,
    translate_place_name,
)


@pytest.fixture(autouse=True)
def reset_geo_state():
    __reset_geocode_runtime_state_for_testing()
    yield
    __reset_geocode_runtime_state_for_testing()


# ==============================================================================
# AC-PBT-1: CJK Variant Symmetry & Branch Name Preservation
# ==============================================================================
def test_pbt_cjk_variant_symmetry_and_branch_preservation():
    sim_tai_1 = cjk_text_similarity("台南", "臺南市")
    sim_tai_2 = cjk_text_similarity("臺南", "臺南市")
    assert sim_tai_1 == sim_tai_2
    assert sim_tai_1 >= 0.85

    assert cjk_text_similarity("台中市", "臺中市") == 1.0
    assert normalize_cjk_chars("一蘭總店") != normalize_cjk_chars("一蘭")
    assert cjk_text_similarity("一蘭總店", "一蘭總店") > cjk_text_similarity("一蘭總店", "一蘭 新宿店")


# ==============================================================================
# AC-PBT-2: Extent Normalization Conservation (Photon & Nominatim)
# ==============================================================================
def test_pbt_extent_normalization_photon_and_nominatim():
    # Photon returns [minLon, maxLat, maxLon, minLat] (inverted lat!)
    photon_ext = normalize_extent([121.45, 25.21, 121.66, 24.96], source_format="photon")
    assert photon_ext == [121.45, 24.96, 121.66, 25.21]
    assert photon_ext[0] <= photon_ext[2] and photon_ext[1] <= photon_ext[3]

    # Nominatim returns [minLat, maxLat, minLon, maxLon] as strings
    nom_ext = normalize_extent(["47.2701", "55.0992", "5.8663", "15.0419"], source_format="nominatim")
    assert nom_ext == [5.8663, 47.2701, 15.0419, 55.0992]
    assert nom_ext[0] <= nom_ext[2] and nom_ext[1] <= nom_ext[3]

    # Invalid / NaN / out-of-range extents rejected safely
    assert normalize_extent([float("nan"), 0, 1, 1]) is None
    assert normalize_extent([0, -95, 1, 10]) is None
    assert normalize_extent([1, 2]) is None


# ==============================================================================
# Safety Net #1: model_manager GEOCODE timeout (0.9s), no Gemma auto-fallback, fast-fail 503
# ==============================================================================
@pytest.mark.asyncio
async def test_model_manager_geocode_excludes_gemma_and_fast_timeout():
    assert "GEOCODE" not in mm.INTENTS_ALLOW_GEMMA_LAST_RESORT
    routing = mm.build_effective_routing("GEOCODE")
    assert not any("gemma" in m for m in routing)
    assert mm._get_call_timeout("GEOCODE") == pytest.approx(0.9)

    # _execute_with_transient_retry MUST NOT sleep on 503 when tag includes GEOCODE or timeout <= 3.0
    from google.genai.errors import APIError

    calls = 0

    async def failing_503(_cfg):
        nonlocal calls
        calls += 1
        raise APIError(503, "Service Unavailable")

    with patch("services.model_manager.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(APIError):
            await mm._execute_with_transient_retry(
                failing_503, "gemini-3.5-flash-lite", MagicMock(), 0.9, "Extraction:GEOCODE"
            )
    assert calls == 1
    mock_sleep.assert_not_called()


# ==============================================================================
# Safety Net #2: Coord-to-Country, BRANDS_DB JP-only, LANDMARKS >80km Exact Match, Wiki Strip
# ==============================================================================
def test_coord_country_inference_nearest_city_and_smallest_bbox():
    assert infer_country_from_coords(48.1371, 11.5754) == "DE"  # Munich
    assert infer_country_from_coords(60.1699, 24.9384) == "FI"  # Helsinki
    assert infer_country_from_coords(47.3769, 8.5417) == "CH"   # Zurich (must not be hijacked by DE/FR/IT)
    assert infer_country_from_coords(48.2082, 16.3738) == "AT"  # Vienna
    assert infer_country_from_coords(1.3521, 103.8198) == "SG"  # Singapore (smaller than MY/ID)
    assert infer_country_from_coords(25.0339, 121.5645) == "TW" # Taipei
    assert infer_country_from_coords(0.0, 0.0) is None          # Null Island rejected
    assert get_country_display_name("FI") == "芬蘭"
    assert get_country_display_name("NL") == "荷蘭"
    assert get_country_display_name("CZ") == "捷克"
    assert _strip_wiki_parenthetical("Central Station (Helsinki)") == "Central Station"
    assert _strip_wiki_parenthetical("新天鵝堡（巴伐利亞）") == "新天鵝堡"


def test_brands_db_scoped_to_japan_only():
    # In Taiwan, searching '咖哩' MUST NOT be rewritten to Japanese 'CoCo壱番屋 カレー'
    terms_tw, disp_tw, _ = translate_famous_landmark("咖哩", country_code="TW")
    assert terms_tw == ["咖哩"]
    assert disp_tw is None

    # In Japan, '一蘭' still resolves via Japan brand/landmark DB
    terms_jp, disp_jp, _ = translate_famous_landmark("一蘭", country_code="JP")
    assert disp_jp is not None


@pytest.mark.asyncio
async def test_landmarks_db_over_80km_exact_full_term_only_and_homonym_guard():
    # 1. Taipei trip searching exact '東京鐵塔' (>80km, non-homonym, exact match) -> 0ms instant return
    res_exact = await smart_geocode_logic(
        query="東京鐵塔",
        limit=None,
        trip_title="3 Day Taipei Explorer",
        lat=25.0339,
        lng=121.5645,
    )
    assert res_exact["source"] == "landmarks_db"
    assert abs(res_exact["results"][0]["lat"] - 35.6586) < 0.01

    # 2. Substring query '東京鐵塔附近美食' (>80km, NOT exact full-term match) -> MUST NOT instant return tower only
    mock_photon = [{"lat": 35.659, "lng": 139.746, "name": "東京鐵塔周邊居酒屋", "address": "Tokyo", "type": "restaurant"}]
    with patch("services.geocode_service.geocode_with_photon", new=AsyncMock(return_value=mock_photon)), \
         patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(status_code=200, json=lambda: []))):
        res_sub = await smart_geocode_logic(
            query="東京鐵塔附近美食",
            limit=None,
            trip_title="3 Day Taipei Explorer",
            lat=25.0339,
            lng=121.5645,
        )
    assert res_sub["source"] != "landmarks_db"
    assert res_sub["results"][0]["name"] == "東京鐵塔周邊居酒屋"


# ==============================================================================
# Safety Net #3: Photon Params (zoom int, scale 0.2), No Concat, No Auto osm_tag, Breaker, Event-Loop Lock
# ==============================================================================
@pytest.mark.asyncio
async def test_photon_params_scale_inversion_fix_integer_zoom_and_osm_fields():
    captured_params = {}

    async def fake_get(self, url, params=None, **kwargs):
        captured_params.update(params or {})
        resp = MagicMock()
        resp.status_code = 200
        resp.content = json.dumps({
            "features": [{
                "geometry": {"coordinates": [121.5645, 25.0339]},
                "properties": {
                    "name": "Starbucks Taipei 101",
                    "osm_value": "cafe",
                    "osm_key": "amenity",
                    "osm_id": 987654321,
                    "osm_type": "N",
                    "city": "Taipei",
                    "country": "Taiwan",
                    "extent": [121.56, 25.04, 121.57, 25.03],
                },
            }]
        }).encode("utf-8")
        return resp

    with patch.object(gs.httpx.AsyncClient, "get", new=fake_get):
        results = await geocode_with_photon("Starbucks", limit=25, lat=25.0339, lng=121.5645, zoom=14.6)

    assert captured_params["q"] == "Starbucks"
    assert captured_params["zoom"] == 15
    assert isinstance(captured_params["zoom"], int)
    assert captured_params["location_bias_scale"] == 0.2
    assert "osm_tag" not in captured_params
    assert results and results[0]["osm_id"] == 987654321
    assert results[0]["city"] == "Taipei"
    assert results[0]["extent"] == [121.56, 25.03, 121.57, 25.04]

    # Verify station query does NOT concatenate simplified variant or inject osm_tag=railway:station
    captured_params.clear()
    with patch.object(gs.httpx.AsyncClient, "get", new=fake_get):
        await geocode_with_photon("東京車站", limit=20, lat=35.68, lng=139.76, zoom=12.2)
    assert captured_params["q"] == "東京車站"
    assert " " not in captured_params["q"]
    assert "osm_tag" not in captured_params
    assert captured_params["zoom"] == 12
    assert captured_params["location_bias_scale"] == 0.4


@pytest.mark.asyncio
async def test_photon_circuit_breaker_and_event_loop_bucketed_lock():
    # Verify Photon 15s breaker opens on 429 and short-circuits subsequent call
    call_count = 0

    async def fake_429(self, url, params=None, **kwargs):
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        resp.status_code = 429
        resp.content = b"Too Many Requests"
        return resp

    with patch("services.geocode_service._is_httpx_get_mocked", return_value=False), \
         patch.object(gs.httpx.AsyncClient, "get", new=fake_429):
        r1 = await geocode_with_photon("Tokyo", limit=5)
        r2 = await geocode_with_photon("Tokyo", limit=5)
    assert r1 is None and r2 is None
    assert call_count == 1  # Second call short-circuited by 15s breaker!

    # Verify event-loop bucketed lock works across independent event loops
    lock_current = _get_nominatim_lock()
    assert isinstance(lock_current, asyncio.Lock)


# ==============================================================================
# User Core Requirement: Unlimited Smart-Ranked Results & strict=False Preservation
# ==============================================================================
@pytest.mark.asyncio
async def test_unlimited_smart_ranked_results_and_non_strict_cross_country_preservation():
    # 1. GeocodeSearchRequest default limit is None (unlimited upstream smart-ranked)
    req = GeocodeSearchRequest(query="Starbucks")
    assert req.limit is None

    # 2. filter_results_by_country with strict=False MUST NOT drop cross-country results
    mixed = [
        {"name": "大阪燒 台北信義店", "lat": 25.034, "lng": 121.565, "type": "restaurant"},
        {"name": "大阪燒 奈良本店", "lat": 34.683, "lng": 135.829, "type": "restaurant"},
        {"name": "大阪府", "lat": 34.693, "lng": 135.502, "type": "state", "admin_level": 4},
    ]
    kept = filter_results_by_country(mixed, "JP", strict=False)
    assert len(kept) == 3

    # 3. Rerank with Taipei bias & zoom=14: Taipei okonomiyaki MUST be #1, NOT 大阪府 and NOT Nara!
    ranked_oko = rerank_top_k(mixed, "大阪燒", bias_lat=25.0339, bias_lng=121.5645, target_country="TW", limit=None, zoom=14)
    assert len(ranked_oko) == 3
    assert ranked_oko[0]["name"] == "大阪燒 台北信義店"

    # 4. Returning all 12 deduplicated smart-ranked results when limit=None (no 5-item truncation!)
    twelve_cafes = [
        {"lat": 25.0339 + i * 0.002, "lng": 121.5645, "name": f"Starbucks Branch {i}", "address": "Taipei", "type": "cafe", "osm_id": 1000 + i}
        for i in range(12)
    ]
    with patch("services.geocode_service.geocode_with_photon", new=AsyncMock(return_value=twelve_cafes)), \
         patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(status_code=200, json=lambda: []))):
        res_all = await smart_geocode_logic(
            query="Starbucks",
            limit=None,
            lat=25.0339,
            lng=121.5645,
            zoom=15,
        )
    assert len(res_all["results"]) == 12
    # Closest branch (i=0) ranks #1
    assert res_all["results"][0]["name"] == "Starbucks Branch 0"
    assert res_all["results"][0]["_score"] >= res_all["results"][-1]["_score"]

    # 5. Backwards compatibility: explicit limit=3 strictly returns 3
    with patch("services.geocode_service.geocode_with_photon", new=AsyncMock(return_value=twelve_cafes)):
        res_three = await smart_geocode_logic(
            query="Starbucks",
            limit=3,
            lat=25.0339,
            lng=121.5645,
            zoom=15,
        )
    assert len(res_three["results"]) == 3


# ==============================================================================
# AC-Geo-3 & AC-Trans-4: Cross-City, Cross-Country, EU Zero-Key Translation, JP Station
# ==============================================================================
@pytest.mark.asyncio
async def test_cross_city_taichung_and_explicit_country_finland_no_taipei_hijack():
    photon_calls = []

    async def fake_photon(q, limit=25, lat=None, lng=None, zoom=None, location_bias_scale=None, osm_tag=None, country_code=None, bbox=None):
        photon_calls.append({"q": q, "bbox": bbox, "osm_tag": osm_tag, "lat": lat, "lng": lng})
        if "Finland" in q or "芬蘭" in q:
            return [{
                "lat": 61.9241, "lng": 25.7482, "name": "Finland", "address": "Finland",
                "type": "country", "admin_level": 2, "extent": [19.4, 59.4, 31.6, 70.1], "osm_id": 54224,
            }]
        return [
            {"lat": 24.1477, "lng": 120.6736, "name": "臺中市", "address": "Taiwan", "type": "city", "admin_level": 6, "extent": [120.46, 24.0, 121.45, 24.44], "osm_id": 111},
            {"lat": 24.1120, "lng": 120.6160, "name": "台中", "address": "Taichung", "type": "station", "osm_id": 222},
        ]

    with patch("services.geocode_service.geocode_with_photon", side_effect=fake_photon), \
         patch("services.geocode_service.search_overpass_by_name", new=AsyncMock()) as mock_overpass, \
         patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(status_code=200, json=lambda: []))):
        res_tc = await smart_geocode_logic(
            query="台中",
            limit=None,
            trip_title="3 Day Taipei Explorer",
            lat=25.0339,
            lng=121.5645,
            zoom=12,
            bbox="121.45,24.95,121.65,25.15",
        )
        assert res_tc["results"][0]["name"] == "臺中市"
        assert all("Taipei" not in c["q"] for c in photon_calls)
        assert all(c["bbox"] is None for c in photon_calls)

        photon_calls.clear()
        res_fi = await smart_geocode_logic(
            query="芬蘭",
            limit=None,
            trip_title="3 Day Taipei Explorer",
            lat=25.0339,
            lng=121.5645,
            zoom=12,
            bbox="121.45,24.95,121.65,25.15",
        )
        assert res_fi["results"][0]["type"] == "country"
        assert res_fi["results"][0]["extent"] == [19.4, 59.4, 31.6, 70.1]
        assert all(c["bbox"] is None for c in photon_calls)
        mock_overpass.assert_not_called()


@pytest.mark.asyncio
async def test_eu_coord_first_zero_key_translation_and_zhuyin_guard():
    # Incomplete Zhuyin returns immediately without calling AI or Wiki
    zhuyin_res = await translate_place_name("ㄊㄞˊ", "DE", api_key=None)
    assert zhuyin_res == ["ㄊㄞˊ"]

    # Zero-key Munich '市政廳' -> includes 'Rathaus' and 'City Hall'
    de_terms = await translate_place_name("市政廳", "DE", api_key=None)
    assert "Rathaus" in de_terms and "City Hall" in de_terms

    # Zero-key Helsinki '中央車站' -> includes 'Päärautatieasema' and 'Central Station'
    fi_terms = await translate_place_name("中央車站", "FI", api_key=None)
    assert any("Päärautatieasema" in t for t in fi_terms) and "Central Station" in fi_terms

    # Zero-key Wikipedia langlinks fallback with parenthetical stripping
    wiki_payload = {
        "query": {
            "pages": {
                "12345": {
                    "langlinks": [
                        {"lang": "de", "*": "Schloss Neuschwanstein (Bayern)"},
                        {"lang": "en", "*": "Neuschwanstein Castle (Germany)"},
                    ]
                }
            }
        }
    }
    mock_wiki_resp = MagicMock(status_code=200)
    mock_wiki_resp.json.return_value = wiki_payload
    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_wiki_resp)):
        wiki_terms = await translate_place_name("新天鵝堡", "DE", api_key=None)
    assert "Schloss Neuschwanstein" in wiki_terms
    assert "Neuschwanstein Castle" in wiki_terms
    assert all("(" not in t for t in wiki_terms)


def test_rerank_multi_variant_and_jp_station_without_eki_compensation():
    candidates = [
        {"lat": 35.6820, "lng": 139.7660, "name": "東京車站畫廊", "type": "museum", "osm_key": "tourism", "importance": 0.55},
        {"lat": 35.6815, "lng": 139.7665, "name": "東京車站大飯店", "type": "hotel", "osm_key": "tourism", "importance": 0.60},
        {"lat": 35.6812, "lng": 139.7671, "name": "東京", "type": "station", "osm_key": "railway", "importance": 0.75},
    ]
    ranked = rerank_top_k(
        candidates,
        query="東京車站",
        bias_lat=25.0339,
        bias_lng=121.5645,
        target_country="JP",
        limit=None,
        query_variants=["東京駅", "東京車站"],
    )
    assert ranked[0]["name"] == "東京"
    assert ranked[0]["type"] == "station"


# ==============================================================================
# Round 2 Adversarial Audit Fixes: Barcelona/Iceland/Hakodate, Native Country,
# Cross-Script Guard, City-Prefix + Nearest-City Civic/Station, OSM Dedup & Lock
# ==============================================================================
def test_poi_tail_word_boundaries_preserve_barcelona_iceland_and_hakodate():
    assert gs._has_poi_or_food_intent("Barcelona") is False
    assert gs._has_poi_or_food_intent("冰島") is False
    assert gs._has_poi_or_food_intent("函館") is False
    assert gs._has_poi_or_food_intent("新店") is False
    assert gs._has_poi_or_food_intent("大阪燒") is True
    assert gs._has_poi_or_food_intent("cocktail bar") is True

    barc_hit = gs._detect_explicit_city_anchor("Barcelona")
    assert barc_hit is not None and barc_hit[1]["country"] == "ES"
    hako_hit = gs._detect_explicit_city_anchor("函館")
    assert hako_hit is not None and hako_hit[1]["country"] == "JP"

    # Native country name (Ísland) MUST outrank Taipei shaved-ice shop (冰島雪花冰)
    iceland_cands = [
        {"lat": 25.04, "lng": 121.56, "name": "冰島雪花冰", "type": "cafe", "source": "photon_speculative"},
        {"lat": 64.9842, "lng": -18.1059, "name": "Ísland", "type": "country", "admin_level": 2, "source": "photon_global"},
    ]
    ranked = rerank_top_k(
        iceland_cands,
        query="冰島",
        bias_lat=25.0339,
        bias_lng=121.5645,
        target_country="IS",
        limit=None,
        zoom=12,
        query_variants=["Iceland", "冰島"],
        is_explicit_country=True,
    )
    assert ranked[0]["name"] == "Ísland"
    assert ranked[0]["_score"] >= 0.90


def test_cross_script_floor_does_not_hijack_paris_or_latin_diacritics():
    # Searching 'Paris' from Taipei MUST NOT let local CJK cafe beat Paris, France
    paris_cands = [
        {"lat": 25.041, "lng": 121.555, "name": "巴黎香榭咖啡", "type": "cafe", "source": "photon_speculative"},
        {"lat": 48.8566, "lng": 2.3522, "name": "Paris", "type": "city", "admin_level": 6, "source": "photon_global"},
    ]
    ranked = rerank_top_k(
        paris_cands,
        query="Paris",
        bias_lat=25.0339,
        bias_lng=121.5645,
        target_country="FR",
        limit=None,
        zoom=12,
        is_explicit_city=True,
    )
    assert ranked[0]["name"] == "Paris"
    assert ranked[0]["_score"] > ranked[1]["_score"] + 0.15

    # Latin diacritic 'Café' vs ASCII 'Starbucks' is NOT cross-script (both Latin)
    assert bool(gs._NON_LATIN_SCRIPT_RE.search("café")) is False
    assert bool(gs._NON_LATIN_SCRIPT_RE.search("münchen")) is False
    assert bool(gs._NON_LATIN_SCRIPT_RE.search("星巴克")) is True


@pytest.mark.asyncio
async def test_city_prefix_detection_nearest_city_micro_dict_and_civic_station_ranking():
    # City-prefix country detection unlocks EU/global queries from Taipei trip
    assert gs._detect_country_from_city_prefix("慕尼黑市政廳") == "DE"
    assert gs._detect_country_from_city_prefix("赫爾辛基中央車站") == "FI"
    assert gs._detect_country_from_city_prefix("維也納歌劇院") == "AT"
    assert gs._detect_country_from_city_prefix("巴塞隆納聖家堂") == "ES"

    # Nearest-city qualification prepends 'Munich Rathaus' while keeping generic 'Rathaus'
    munich_terms = await translate_place_name("市政廳", "DE", api_key=None, lat=48.1371, lng=11.5754)
    assert munich_terms[0] == "Munich Rathaus"
    assert "Rathaus" in munich_terms

    # Generic micro-dict must NOT hardcode Munich-only Viktualienmarkt for Berlin '市場'
    berlin_market = await translate_place_name("市場", "DE", api_key=None, lat=52.5200, lng=13.4050)
    assert all("Viktualienmarkt" not in t for t in berlin_market)
    assert berlin_market[0] == "Berlin Markt"

    # Civic building (Neues Rathaus townhall) MUST outrank nearby pharmacy/restaurant/bus_stop
    munich_cands = [
        {"lat": 48.1374, "lng": 11.5760, "name": "Rathaus-Apotheke", "type": "pharmacy", "osm_key": "amenity", "source": "photon"},
        {"lat": 48.0761, "lng": 11.6623, "name": "Rathaus", "type": "bus_stop", "osm_key": "highway", "source": "photon"},
        {"lat": 48.1378, "lng": 11.5754, "name": "Neues Rathaus", "type": "townhall", "osm_key": "amenity", "source": "photon"},
    ]
    ranked_civic = rerank_top_k(
        munich_cands,
        query="市政廳",
        bias_lat=48.1371,
        bias_lng=11.5754,
        target_country="DE",
        limit=None,
        zoom=14,
        query_variants=["Munich Rathaus", "Rathaus", "City Hall", "市政廳"],
    )
    assert ranked_civic[0]["name"] == "Neues Rathaus"

    # Major rail station MUST outrank minor tram_stop for '中央車站'
    helsinki_cands = [
        {"lat": 60.1704, "lng": 24.9407, "name": "Päärautatieasema", "type": "tram_stop", "osm_key": "railway", "source": "photon"},
        {"lat": 60.1721, "lng": 24.9412, "name": "Helsinki", "type": "station", "osm_key": "railway", "source": "photon"},
    ]
    ranked_fi = rerank_top_k(
        helsinki_cands,
        query="中央車站",
        bias_lat=60.1699,
        bias_lng=24.9384,
        target_country="FI",
        limit=None,
        zoom=14,
        query_variants=["Helsinki Päärautatieasema", "Päärautatieasema", "Central Station", "中央車站"],
    )
    assert ranked_fi[0]["name"] == "Helsinki"
    assert ranked_fi[0]["type"] == "station"


@pytest.mark.asyncio
async def test_photon_nominatim_osm_type_dedup_metadata_merge_and_display_name():
    # Photon returns osm_type='R' while Nominatim returns osm_type='relation' for the same entity
    photon_hit = [{
        "lat": 48.1378, "lng": 11.5754, "name": "Neues Rathaus",
        "display_name": "Germany, Bavaria, Munich", "address": "Germany, Bavaria, Munich",
        "type": "townhall", "osm_key": "amenity", "osm_id": 147095, "osm_type": "R",
        "extent": None, "source": "photon",
    }]
    nom_dup = [{
        "lat": "48.1380", "lon": "11.5756", "name": "Neues Rathaus",
        "display_name": "Neues Rathaus, Marienplatz, Munich, Germany",
        "type": "townhall", "class": "amenity", "osm_id": 147095, "osm_type": "relation",
        "boundingbox": ["48.1370", "48.1385", "11.5745", "11.5765"], "address": {"city": "Munich", "country": "Germany"},
        "extratags": {},
    }]
    mock_nom_resp = MagicMock(status_code=200)
    mock_nom_resp.json.return_value = nom_dup

    with patch("services.geocode_service.geocode_with_photon", new=AsyncMock(return_value=photon_hit)), \
         patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_nom_resp)):
        res = await smart_geocode_logic(
            query="Neues Rathaus",
            limit=None,
            lat=48.1371,
            lng=11.5754,
            zoom=14,
        )
    # Must deduplicate R/147095 and relation/147095 into 1 item AND enrich missing extent from Nominatim!
    assert len(res["results"]) == 1
    assert res["results"][0]["display_name"]
    assert res["results"][0]["extent"] == [11.5745, 48.137, 11.5765, 48.1385]


@pytest.mark.asyncio
async def test_resolve_address_pipeline_parses_ai_outside_nominatim_lock_and_uses_shared_limiter():
    lock_was_held_during_ai = False
    limiter_called = 0

    async def fake_gemma_parse(addr, user_key=None):
        nonlocal lock_was_held_during_ai
        lock_was_held_during_ai = _get_nominatim_lock().locked()
        return {"country": "Taiwan", "city": "Taipei", "street": "信義路五段7號"}

    async def fake_limiter():
        nonlocal limiter_called
        limiter_called += 1

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "features": [{
            "geometry": {"coordinates": [121.5645, 25.0339]},
            "properties": {"geocoding": {"name": "Taipei 101", "label": "信義路五段7號, 台北"}},
        }]
    }

    with patch("services.geocode_service.geocode_with_gas", new=AsyncMock(return_value=None)), \
         patch("services.geocode_service.ARCGIS_API_KEY", ""), \
         patch("services.geocode_service._gemma_parse_address", side_effect=fake_gemma_parse), \
         patch("services.geocode_service._nominatim_rate_limit_wait", side_effect=fake_limiter), \
         patch.object(gs.HTTPX_CLIENT, "get", new=AsyncMock(return_value=mock_resp)):
        out = await gs.resolve_address_pipeline("台北市信義路五段7號")

    assert out is not None and abs(out["lat"] - 25.0339) < 1e-4
    assert lock_was_held_during_ai is False
    assert limiter_called == 1


# ==============================================================================
# Minor Flaw #1 Fix: City vs Same-Name Province/State Disambiguation & Dedup Global Photon
# ==============================================================================
def test_city_outranks_same_name_province_or_state_while_preserving_explicit_state_and_country():
    # 1. Barcelona (anchor city): city MUST outrank enveloping province
    barc_cands = [
        {"lat": 41.387, "lng": 2.169, "name": "Barcelona", "type": "province", "osm_key": "place", "admin_level": 6, "source": "photon_speculative"},
        {"lat": 41.382, "lng": 2.177, "name": "Barcelona", "type": "city", "osm_key": "place", "admin_level": 8, "source": "photon_speculative"},
    ]
    ranked_barc = rerank_top_k(
        barc_cands,
        query="Barcelona",
        bias_lat=25.0339,
        bias_lng=121.5645,
        target_country="ES",
        limit=None,
        zoom=12,
        is_explicit_city=True,
    )
    assert ranked_barc[0]["type"] == "city"
    assert ranked_barc[1]["type"] == "province"

    # 2. General non-anchor city (Valencia): city MUST still outrank province without hardcoding
    val_cands = [
        {"lat": 39.469, "lng": -0.376, "name": "Valencia", "type": "province", "osm_key": "place", "admin_level": 6, "source": "photon"},
        {"lat": 39.469, "lng": -0.376, "name": "Valencia", "type": "city", "osm_key": "place", "admin_level": 8, "source": "photon"},
    ]
    ranked_val = rerank_top_k(
        val_cands,
        query="Valencia",
        bias_lat=25.0339,
        bias_lng=121.5645,
        target_country="ES",
        limit=None,
        zoom=12,
        is_explicit_city=False,
    )
    assert ranked_val[0]["type"] == "city"

    # 3. New York: city MUST outrank state
    ny_cands = [
        {"lat": 42.95, "lng": -75.52, "name": "New York", "type": "state", "osm_key": "place", "admin_level": 4, "source": "photon"},
        {"lat": 40.71, "lng": -74.00, "name": "New York", "type": "city", "osm_key": "place", "admin_level": 5, "source": "photon"},
    ]
    ranked_ny = rerank_top_k(
        ny_cands,
        query="New York",
        bias_lat=25.0339,
        bias_lng=121.5645,
        target_country="US",
        limit=None,
        zoom=12,
        is_explicit_city=True,
    )
    assert ranked_ny[0]["type"] == "city"

    # 4. 大阪: 大阪市 (city, fuzz=0.95) > 大阪府 (province, fuzz=0.95) > 大阪狭山市 (city, fuzz=0.91 < 0.95)
    osaka_cands = [
        {"lat": 34.69, "lng": 135.50, "name": "大阪府", "type": "province", "osm_key": "place", "admin_level": 4, "source": "photon"},
        {"lat": 34.69, "lng": 135.50, "name": "大阪市", "type": "city", "osm_key": "place", "admin_level": 7, "source": "photon"},
        {"lat": 34.50, "lng": 135.55, "name": "大阪狭山市", "type": "city", "osm_key": "place", "admin_level": 7, "source": "photon"},
    ]
    ranked_osaka = rerank_top_k(
        osaka_cands,
        query="大阪",
        bias_lat=25.0339,
        bias_lng=121.5645,
        target_country="JP",
        limit=None,
        zoom=12,
        is_explicit_city=True,
    )
    assert [r["name"] for r in ranked_osaka] == ["大阪市", "大阪府", "大阪狭山市"]

    # 5. Explicit state/province query ('大阪府' / 'Barcelona province') keeps province/state #1
    ranked_pref = rerank_top_k(
        osaka_cands,
        query="大阪府",
        bias_lat=25.0339,
        bias_lng=121.5645,
        target_country="JP",
        limit=None,
        zoom=12,
        is_explicit_city=True,
    )
    assert ranked_pref[0]["name"] == "大阪府"

    # 6. Explicit country query ('德國' / 'Luxembourg') keeps country #1 over same-name city
    lux_cands = [
        {"lat": 49.611, "lng": 6.131, "name": "Luxembourg", "type": "city", "osm_key": "place", "admin_level": 8, "source": "photon_global"},
        {"lat": 49.815, "lng": 6.130, "name": "Luxembourg", "type": "country", "osm_key": "place", "admin_level": 2, "source": "photon_global"},
    ]
    ranked_lux = rerank_top_k(
        lux_cands,
        query="盧森堡",
        bias_lat=25.0339,
        bias_lng=121.5645,
        target_country="LU",
        limit=None,
        zoom=12,
        query_variants=["Luxembourg", "盧森堡"],
        is_explicit_country=True,
    )
    assert ranked_lux[0]["type"] == "country"


@pytest.mark.asyncio
async def test_explicit_city_without_cjk_variant_does_not_duplicate_photon_call():
    photon_calls = []

    async def fake_photon(q, limit=25, lat=None, lng=None, zoom=None, location_bias_scale=None, osm_tag=None, country_code=None, bbox=None):
        photon_calls.append(q)
        return [
            {"lat": 41.387, "lng": 2.169, "name": "Barcelona", "type": "province", "osm_key": "place", "admin_level": 6, "osm_id": 1},
            {"lat": 41.382, "lng": 2.177, "name": "Barcelona", "type": "city", "osm_key": "place", "admin_level": 8, "osm_id": 2},
        ]

    with patch("services.geocode_service.geocode_with_photon", side_effect=fake_photon), \
         patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(status_code=200, json=lambda: []))):
        res = await smart_geocode_logic(
            query="Barcelona",
            limit=None,
            trip_title="3 Day Taipei Explorer",
            lat=25.0339,
            lng=121.5645,
            zoom=12,
        )
    assert photon_calls == ["Barcelona"]
    assert res["results"][0]["type"] == "city"


@pytest.mark.asyncio
async def test_cjk_explicit_city_uses_0ms_anchor_en_and_survives_wiki_outage_or_native_names():
    # 1. '巴塞隆納' MUST resolve 'Barcelona' via 0ms GLOBAL_CITY_ANCHORS without calling Wikipedia
    photon_calls = []

    async def fake_photon(q, limit=25, lat=None, lng=None, zoom=None, location_bias_scale=None, osm_tag=None, country_code=None, bbox=None):
        photon_calls.append(q)
        if q == "Barcelona":
            return [
                {"lat": 41.387, "lng": 2.169, "name": "Barcelona", "type": "province", "osm_key": "place", "admin_level": 6, "osm_id": 11},
                {"lat": 41.382, "lng": 2.177, "name": "Barcelona", "type": "city", "osm_key": "place", "admin_level": 8, "osm_id": 12},
            ]
        return [
            {"lat": 24.1506, "lng": 120.6657, "name": "巴塞隆納大樓", "type": "apartments", "osm_key": "building", "osm_id": 13},
        ]

    with patch("services.geocode_service._translate_via_wikipedia_langlinks", new=AsyncMock()) as mock_wiki, \
         patch("services.geocode_service.geocode_with_photon", side_effect=fake_photon), \
         patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(status_code=200, json=lambda: []))):
        res = await smart_geocode_logic(
            query="巴塞隆納",
            limit=None,
            trip_title="3 Day Taipei Explorer",
            lat=25.0339,
            lng=121.5645,
            zoom=12,
        )
    mock_wiki.assert_not_called()
    assert "Barcelona" in photon_calls
    assert res["results"][0]["name"] == "Barcelona"
    assert res["results"][0]["type"] == "city"

    # 2. Even if Photon is down and Nominatim returns Simplified '巴塞罗那' vs local '巴塞隆納大樓',
    #    anchor-aligned city '巴塞罗那' MUST outrank local apartment '巴塞隆納大樓'!
    fallback_cands = [
        {"lat": 24.1506, "lng": 120.6657, "name": "巴塞隆納大樓", "type": "apartments", "osm_key": "building", "source": "photon_speculative"},
        {"lat": 41.3826, "lng": 2.1771, "name": "巴塞罗那", "type": "city", "osm_key": "place", "admin_level": 8, "source": "nominatim"},
    ]
    ranked_fallback = rerank_top_k(
        fallback_cands,
        query="巴塞隆納",
        bias_lat=25.0339,
        bias_lng=121.5645,
        target_country="ES",
        limit=None,
        zoom=12,
        query_variants=["Barcelona", "巴塞隆納"],
        is_explicit_city=True,
        explicit_city_coords=(41.3874, 2.1686),
    )
    assert ranked_fallback[0]["name"] == "巴塞罗那"
    assert ranked_fallback[0]["type"] == "city"

    # 3. Native European city name ('München' for '慕尼黑') aligns via anchor coords and beats distant decoy
    munich_cands = [
        {"lat": 25.04, "lng": 121.55, "name": "慕尼黑啤酒屋", "type": "restaurant", "osm_key": "amenity", "source": "photon_speculative"},
        {"lat": 48.1371, "lng": 11.5754, "name": "München", "type": "city", "osm_key": "place", "admin_level": 6, "source": "photon_global"},
    ]
    ranked_muc = rerank_top_k(
        munich_cands,
        query="慕尼黑",
        bias_lat=25.0339,
        bias_lng=121.5645,
        target_country="DE",
        limit=None,
        zoom=12,
        query_variants=["Munich", "慕尼黑"],
        is_explicit_city=True,
        explicit_city_coords=(48.1351, 11.5820),
    )
    assert ranked_muc[0]["name"] == "München"
    assert ranked_muc[0]["type"] == "city"


# ==============================================================================
# Adversarial Review Regression Guards:
# 1. Duplicate-coord anchor EN lookup (札幌!=Hokkaido, 那霸!=Okinawa)
# 2. Latin word-level similarity & neighboring-city hijack prevention (Hoboken, Ixelles, Badalona)
# 3. English exonym vs non-Latin endonym (Athens->Αθήνα, Bangkok->กรุงเทพมหานคร, Tokyo->東京都, Seoul->서울특별시)
# 4. JP Shinjitai cities (沖繩->沖縄県, 那霸->那覇市, 橫濱->横浜市, 輕井澤->軽井沢町)
# 5. Landmark hijack guard on explicit city/country (福岡, 札幌, Singapore != 樟宜國際機場)
# 6. OSM SAR handling for HK / MO (no countrycode=hk/mo blackout, no place:country osm_tag)
# ==============================================================================
def test_anchor_english_disambiguation_and_latin_similarity_guards():
    from services.geocode_service import (
        GLOBAL_CITY_ANCHORS,
        _get_city_anchor_english_name,
        _translate_via_micro_dict,
        _jp_kanji_variant,
    )

    assert _get_city_anchor_english_name(GLOBAL_CITY_ANCHORS["札幌"]) == "Sapporo"
    assert _get_city_anchor_english_name(GLOBAL_CITY_ANCHORS["北海道"]) == "Hokkaido"
    assert _get_city_anchor_english_name(GLOBAL_CITY_ANCHORS["那霸"]) == "Naha"
    assert _get_city_anchor_english_name(GLOBAL_CITY_ANCHORS["沖繩"]) == "Okinawa"
    assert _get_city_anchor_english_name(GLOBAL_CITY_ANCHORS["清邁"]) == "Chiang Mai"

    assert _translate_via_micro_dict("札幌車站", "JP") == ["Sapporo 駅", "Sapporo Station"]
    assert _translate_via_micro_dict("那霸機場", "JP") == ["Naha 空港", "Naha Airport"]

    assert _jp_kanji_variant("沖繩") == "沖縄"
    assert _jp_kanji_variant("那霸") == "那覇"
    assert _jp_kanji_variant("橫濱") == "横浜"
    assert _jp_kanji_variant("輕井澤") == "軽井沢"
    assert _jp_kanji_variant("神戶") == "神戸"

    # Latin accent folding + word-level similarity must not inflate unrelated neighbors
    assert cjk_text_similarity("Zurich", "Zürich") == 1.0
    assert cjk_text_similarity("New York", "Hoboken") < 0.45
    assert cjk_text_similarity("Brussels", "Ixelles") < 0.45
    assert cjk_text_similarity("Barcelona", "L'Hospitalet de Llobregat") < 0.45
    assert cjk_text_similarity("Barcelona", "Badalona") < 0.85


def test_rerank_blocks_neighbor_hijack_and_ranks_non_latin_capitals_and_jp_shinjitai():
    # 1. Hoboken (3.5km from NYC) MUST NOT get anchor-aligned boost on '紐約'
    nyc_cands = [
        {"lat": 40.7439, "lng": -74.0324, "name": "Hoboken", "type": "city", "osm_key": "place", "admin_level": 8, "source": "photon_speculative"},
        {"lat": 40.7128, "lng": -74.0060, "name": "New York", "type": "city", "osm_key": "place", "admin_level": 5, "source": "photon_global"},
    ]
    ranked_nyc = rerank_top_k(
        nyc_cands,
        query="紐約",
        bias_lat=25.0339,
        bias_lng=121.5645,
        target_country="US",
        limit=None,
        zoom=12,
        query_variants=["New York", "紐約"],
        is_explicit_city=True,
        explicit_city_coords=(40.7128, -74.0060),
    )
    assert ranked_nyc[0]["name"] == "New York"
    assert ranked_nyc[0]["_score"] - ranked_nyc[1]["_score"] > 0.40

    # 2. '沖繩' (is_admin_region_anchor=True) MUST rank 沖縄県 above Naha
    oki_cands = [
        {"lat": 26.2124, "lng": 127.6809, "name": "Naha", "type": "city", "osm_key": "place", "admin_level": 7, "source": "photon_global"},
        {"lat": 26.3344, "lng": 127.8056, "name": "沖縄県", "type": "province", "osm_key": "place", "admin_level": 4, "source": "photon_global"},
    ]
    ranked_oki = rerank_top_k(
        oki_cands,
        query="沖繩",
        bias_lat=25.0339,
        bias_lng=121.5645,
        target_country="JP",
        limit=None,
        zoom=12,
        query_variants=["沖縄", "Okinawa", "沖繩"],
        is_explicit_city=True,
        explicit_city_coords=(26.2124, 127.6809),
        is_admin_region_anchor=True,
    )
    assert ranked_oki[0]["name"] == "沖縄県"

    # 3. English exonyms vs non-Latin capitals: Athens -> Αθήνα, Bangkok -> กรุงเทพมหานคร, Tokyo -> 東京都
    ath_cands = [
        {"lat": 33.9519, "lng": -83.3576, "name": "Athens", "type": "city", "osm_key": "place", "admin_level": 8, "source": "photon_speculative"},
        {"lat": 37.9838, "lng": 23.7275, "name": "Αθήνα", "type": "city", "osm_key": "place", "admin_level": 8, "source": "photon_speculative"},
    ]
    ranked_ath = rerank_top_k(
        ath_cands,
        query="Athens",
        bias_lat=25.0339,
        bias_lng=121.5645,
        target_country="GR",
        limit=None,
        zoom=12,
        query_variants=["Athens"],
        is_explicit_city=True,
        explicit_city_coords=(37.9838, 23.7275),
    )
    assert ranked_ath[0]["name"] == "Αθήνα"

    tokyo_cands = [
        {"lat": 35.686, "lng": 139.744, "name": "TOKYO-FM", "type": "studio", "osm_key": "amenity", "source": "photon_speculative"},
        {"lat": 35.6895, "lng": 139.6917, "name": "東京都", "type": "province", "osm_key": "place", "admin_level": 4, "source": "photon_speculative"},
    ]
    ranked_tokyo = rerank_top_k(
        tokyo_cands,
        query="Tokyo",
        bias_lat=25.0339,
        bias_lng=121.5645,
        target_country="JP",
        limit=None,
        zoom=12,
        query_variants=["Tokyo"],
        is_explicit_city=True,
        explicit_city_coords=(35.6895, 139.6917),
    )
    assert ranked_tokyo[0]["name"] == "東京都"


@pytest.mark.asyncio
async def test_explicit_city_country_not_hijacked_by_landmarks_and_sar_hk_mo_supported():
    # 1. ASCII alias 'sin' MUST NOT match inside 'Singapore'
    _, disp_sg, _ = translate_famous_landmark("Singapore", country_code="SG")
    assert disp_sg is None

    # 2. Explicit city '福岡' MUST NOT instant-return single ramen shop from LANDMARKS_DB
    async def fake_fukuoka(q, limit=25, lat=None, lng=None, zoom=None, location_bias_scale=None, osm_tag=None, country_code=None, bbox=None):
        return [
            {"lat": 33.5904, "lng": 130.4017, "name": "福岡市", "type": "city", "osm_key": "place", "admin_level": 7, "osm_id": 101},
            {"lat": 33.6064, "lng": 130.4183, "name": "福岡県", "type": "province", "osm_key": "place", "admin_level": 4, "osm_id": 102},
        ]

    with patch("services.geocode_service.geocode_with_photon", side_effect=fake_fukuoka), \
         patch("httpx.AsyncClient.get", new=AsyncMock(return_value=MagicMock(status_code=200, json=lambda: []))):
        res_fuk = await smart_geocode_logic("福岡", limit=None, lat=25.0339, lng=121.5645, zoom=12)
    assert res_fuk["source"] != "landmarks_db"
    assert res_fuk["results"][0]["name"] == "福岡市"

    # 3. HK/MO SAR: geocode_with_photon MUST NOT pass countrycode=hk (uses bbox instead), and smart_geocode_logic("香港") MUST NOT pass osm_tag="place:country"
    captured_params = []

    async def fake_httpx_get(self, url, params=None, **kwargs):
        captured_params.append(dict(params or {}))
        payload = json.dumps({
            "features": [{
                "geometry": {"coordinates": [114.1694, 22.3193]},
                "properties": {"name": "香港 Hong Kong", "osm_value": "city", "osm_key": "place", "osm_id": 913110, "osm_type": "R", "country": "中国", "extra": {"admin_level": "4"}},
            }]
        }).encode("utf-8")
        resp = MagicMock()
        resp.status_code = 200
        resp.content = payload
        resp.json.return_value = []
        return resp

    with patch("httpx.AsyncClient.get", new=fake_httpx_get):
        res_hk = await smart_geocode_logic("香港", limit=None, lat=25.0339, lng=121.5645, zoom=12)

    assert len(res_hk["results"]) >= 1
    assert res_hk["results"][0]["name"] == "香港 Hong Kong"
    for p in captured_params:
        assert p.get("countrycode") != "hk"
        assert p.get("osm_tag") != "place:country"
        assert "bbox" in p
