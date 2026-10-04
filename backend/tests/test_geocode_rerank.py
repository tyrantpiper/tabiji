"""
Unit and Integration Tests for Parallel Geocoding & Top-K Reranking
-------------------------------------------------------------------
Tests:
1. BBOX validation and Antimeridian crossing defense
2. CJK character-spaced similarity and rational spatial decay
3. Country filter graceful fallback (cross-border preservation)
4. Top-K reranking: Homonym disambiguation & cross-border preservation
5. smart_geocode_logic integration with bbox parameter
"""

import pytest
import math
from unittest.mock import patch, AsyncMock
from services.geocode_service import (
    sanitize_bbox,
    haversine_km,
    cjk_text_similarity,
    proximity_decay,
    rerank_top_k,
    filter_results_by_country,
    smart_geocode_logic,
    COUNTRY_BOUNDS
)


# ==========================================
# 1. BBOX Sanitization & Antimeridian Defense
# ==========================================
def test_sanitize_bbox_valid():
    # Tokyo viewport bounds
    assert sanitize_bbox("139.5,35.5,139.9,35.8") == "139.50000,35.50000,139.90000,35.80000"
    # Negative coordinates (Southern hemisphere / West)
    assert sanitize_bbox("-73.98,40.70,-73.90,40.75") == "-73.98000,40.70000,-73.90000,40.75000"


def test_sanitize_bbox_antimeridian_and_invalids():
    # Antimeridian crossing (minLon 179 > maxLon -179)
    assert sanitize_bbox("179.0,-20.0,-179.0,-15.0") is None
    # Inverted latitudes (minLat > maxLat)
    assert sanitize_bbox("139.5,36.0,139.9,35.0") is None
    # Out of latitude range [-90, 90]
    assert sanitize_bbox("139.5,-95.0,139.9,35.0") is None
    # Non-numeric or SQL injection attempts
    assert sanitize_bbox("139.5; DROP TABLE users;") is None
    assert sanitize_bbox("invalid,coordinates,here,foo") is None
    assert sanitize_bbox("") is None
    assert sanitize_bbox(None) is None


# ==========================================
# 2. CJK Similarity & Rational Spatial Decay
# ==========================================
def test_cjk_text_similarity():
    # Exact match
    assert cjk_text_similarity("桃園機場", "桃園機場") == 1.0
    # Substring containment bonus
    sim_contained = cjk_text_similarity("桃園機場", "臺灣桃園國際機場")
    assert sim_contained >= 0.85
    # Token overlap
    sim_overlap = cjk_text_similarity("台中一中", "臺中市立第一高級中學校")
    assert sim_overlap > 0.4
    # Empty query or target
    assert cjk_text_similarity("", "東京") == 0.0
    assert cjk_text_similarity("東京", "") == 0.0


def test_proximity_decay():
    # 0 km distance -> 1.0
    assert proximity_decay(0.0) == 1.0
    # 15 km distance -> ~0.91 (neighborhood priority)
    assert proximity_decay(15.0) > 0.90
    # 50 km distance -> 0.75 (metropolitan area)
    assert round(proximity_decay(50.0), 2) == 0.75
    # 150 km distance -> 0.50 (half-life at 150km)
    assert round(proximity_decay(150.0), 2) == 0.50
    # 2000 km distance -> ~0.07 (smooth tail, never cliff drops to 0.0)
    assert proximity_decay(2000.0) > 0.05


# ==========================================
# 3. Country Filter Graceful Fallback
# ==========================================
def test_filter_results_by_country_normal():
    # Places inside Japan
    tokyo_poi = [{"name": "東京鐵塔", "lat": 35.6586, "lng": 139.7454}]
    filtered = filter_results_by_country(tokyo_poi, "JP", strict=True)
    assert len(filtered) == 1
    assert filtered[0]["name"] == "東京鐵塔"


def test_filter_results_by_country_graceful_cross_border():
    # User planning a JP trip but searching for Taiwan departure airport
    tw_airport = [{"name": "臺灣桃園國際機場", "lat": 25.0797, "lng": 121.2342, "source": "photon"}]
    # Must NOT return empty list! It must gracefully return the original results.
    filtered = filter_results_by_country(tw_airport, "JP", strict=True)
    assert len(filtered) == 1
    assert filtered[0]["name"] == "臺灣桃園國際機場"


# ==========================================
# 4. Top-K Reranking Multi-Factor Fusion
# ==========================================
def test_top_k_homonym_disambiguation():
    """
    Homonym '大安' (Da'an):
    Taipei Da'an (Taiwan) vs Jilin Da'an (China) vs Zigong Da'an (China)
    With bias at Taipei (25.033, 121.565) and target_country='TW',
    Taipei Da'an MUST be ranked #1.
    """
    candidates = [
        {"name": "大安市 (吉林省)", "lat": 45.503, "lng": 124.295, "importance": 0.70, "source": "photon"},
        {"name": "大安區 (臺北市)", "lat": 25.026, "lng": 121.543, "importance": 0.65, "source": "photon"},
        {"name": "大安區 (自貢市)", "lat": 29.363, "lng": 104.782, "importance": 0.60, "source": "nominatim"}
    ]
    ranked = rerank_top_k(
        candidates,
        query="大安",
        bias_lat=25.033,
        bias_lng=121.565,
        target_country="TW",
        limit=3
    )
    assert len(ranked) == 3
    assert "臺北市" in ranked[0]["name"]
    assert ranked[0]["_score"] > ranked[1]["_score"]


def test_top_k_cross_border_preservation():
    """
    Cross-border transit search:
    User is in Tokyo (lat 35.6895, lng 139.6917, country 'JP'),
    searches for '桃園機場'.
    '臺灣桃園國際機場' must be returned with solid relevance score.
    """
    candidates = [
        {"name": "臺灣桃園國際機場", "lat": 25.0797, "lng": 121.2342, "importance": 0.75, "source": "photon"},
        {"name": "桃園國際機場第二航廈", "lat": 25.0777, "lng": 121.2328, "importance": 0.65, "source": "nominatim"}
    ]
    ranked = rerank_top_k(
        candidates,
        query="桃園機場",
        bias_lat=35.6895,
        bias_lng=139.6917,
        target_country="JP",
        limit=2
    )
    assert len(ranked) == 2
    assert "臺灣桃園國際機場" in ranked[0]["name"]
    assert ranked[0]["_score"] > 0.50


# ==========================================
# 5. smart_geocode_logic Integration
# ==========================================
@pytest.mark.asyncio
async def test_smart_geocode_logic_with_bbox_and_rerank():
    """Test smart_geocode_logic receives bbox and reranks results."""
    mock_photon_results = [
        {"lat": 35.7147, "lng": 139.7966, "name": "淺草寺", "address": "東京都台東區淺草", "source": "photon", "importance": 0.8},
        {"lat": 35.7111, "lng": 139.7964, "name": "雷門", "address": "東京都台東區", "source": "photon", "importance": 0.7}
    ]
    with patch("services.geocode_service.geocode_with_photon", new_callable=AsyncMock) as mock_photon:
        mock_photon.return_value = mock_photon_results
        
        res = await smart_geocode_logic(
            query="淺草巷弄特色小吃",
            limit=2,
            lat=35.7100,
            lng=139.7900,
            country="JP",
            bbox="139.78,35.70,139.81,35.72"
        )
        
        assert "results" in res
        assert len(res["results"]) == 2
        # Check that scores were computed and attached
        assert "_score" in res["results"][0]
        # Bbox was passed down into geocode_with_photon
        mock_photon.assert_called()
        call_kwargs = mock_photon.call_args_list[0].kwargs
        assert call_kwargs.get("bbox") == "139.78,35.70,139.81,35.72"
