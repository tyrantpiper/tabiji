# -*- coding: utf-8 -*-
"""
Nearby POI Search Resilience & Hedged Fallback Suite (Mantis Block G):
Verifies:
1. When Overpass API returns HTTP 502 or ReadTimeout, search_poi_combined seamlessly returns
   Photon /reverse (or Wikipedia Geosearch) POIs in parallel without returning count=0.
2. Coordinate-aware language selection & 5-minute spatial cache + __resetNearbyPoiCacheForTesting().
3. Benign control: When Overpass succeeds cleanly, Overpass entries are prioritized & returned.
"""

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app  # noqa: E402
from services import poi_service  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_cache():
    poi_service.__resetNearbyPoiCacheForTesting()
    yield
    poi_service.__resetNearbyPoiCacheForTesting()


@pytest.mark.asyncio
async def test_overpass_502_triggers_photon_reverse_fallback():
    """Exploit/Resilience: Overpass 502 must not return [] when Photon /reverse has valid POIs."""
    overpass_req = httpx.Request("POST", poi_service.OVERPASS_API)
    overpass_502 = httpx.Response(502, request=overpass_req)

    photon_payload = {
        "features": [
            {
                "properties": {
                    "osm_id": 1001,
                    "name": "Ningxia Beef Noodles",
                    "street": "Ningxia Rd",
                    "housenumber": "12",
                    "district": "Datong District",
                },
                "geometry": {"coordinates": [121.515, 25.056]},
            },
            {
                # Unnamed node should be ignored cleanly
                "properties": {"osm_id": 1002, "street": "Unnamed Alley"},
                "geometry": {"coordinates": [121.516, 25.057]},
            },
        ]
    }

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def post(self, url, data=None, headers=None):
            return overpass_502

        async def get(self, url, params=None):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = photon_payload
            return resp

    with patch("services.poi_service.httpx.AsyncClient", side_effect=MockClient), \
         patch("services.poi_service.is_safe_url", return_value=True):
        pois = await poi_service.search_poi_combined(25.0551, 121.5083, "restaurant", radius=1000, timeout=2.5)

    assert len(pois) == 1
    assert pois[0]["name"] == "Ningxia Beef Noodles"
    assert pois[0]["source"] == "photon_reverse"
    assert pois[0]["category"] == "restaurant"


@pytest.mark.asyncio
async def test_overpass_timeout_uses_parallel_hedged_execution_and_wiki_for_popular():
    """When Overpass times out and category is popular, Photon + Wiki Geosearch execute in parallel without blocking."""
    async def slow_overpass(*args, **kwargs):
        await asyncio.sleep(0.3)
        return []

    wiki_json = {
        "query": {
            "geosearch": [
                {"pageid": 888, "title": "Dihua Old Street", "lat": 25.056, "lon": 121.509},
            ]
        }
    }

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def get(self, url, params=None):
            resp = MagicMock()
            resp.status_code = 200
            if "wikipedia.org" in url:
                resp.json.return_value = wiki_json
            else:
                resp.json.return_value = {"features": []}
            return resp

    started = time.monotonic()
    with patch("services.poi_service.search_overpass", side_effect=slow_overpass), \
         patch("services.poi_service.httpx.AsyncClient", side_effect=MockClient), \
         patch("services.poi_service.is_safe_url", return_value=True):
        pois = await poi_service.search_poi_combined(25.0551, 121.5083, "popular", radius=1000, timeout=2.5)
    elapsed = time.monotonic() - started

    assert elapsed < 1.5
    assert any(p["name"] == "Dihua Old Street" and p["source"] == "wikipedia" for p in pois)


@pytest.mark.asyncio
async def test_nearby_cache_hits_and_benign_overpass_priority():
    """Mantis Block G Benign Control: Overpass results take precedence and 5-min cache avoids duplicate HTTP calls."""
    overpass_pois = [
        {
            "id": "osm_42",
            "name": "Taipei Main Mall",
            "category": "department_store",
            "lat": 25.0478,
            "lng": 121.517,
            "distance": 450,
            "source": "osm",
        }
    ]
    mock_overpass = AsyncMock(return_value=overpass_pois)
    mock_fallback = AsyncMock(return_value=[])

    with patch("services.poi_service.search_overpass", mock_overpass), \
         patch("services.poi_service.search_nearby_fallback", mock_fallback):
        first = await poi_service.search_poi_combined(25.0478, 121.517, "department_store", radius=1000, timeout=2.5)
        second = await poi_service.search_poi_combined(25.0478, 121.517, "department_store", radius=1000, timeout=2.5)

    assert len(first) == 1
    assert first[0]["source"] == "osm"
    assert second == first
    assert mock_overpass.await_count == 1
    assert mock_fallback.await_count == 1


def test_router_poi_nearby_returns_resilient_results():
    """Verify GET /api/poi/nearby passes timeout<=2.5 and returns resilient payload."""
    sample_pois = [
        {
            "id": "photon_1",
            "name": "Tsuruha Drug New Chitose",
            "category": "pharmacy",
            "lat": 42.7875,
            "lng": 141.6753,
            "distance": 95,
            "source": "photon_reverse",
        }
    ]
    with patch("routers.poi.search_poi_combined", new_callable=AsyncMock, return_value=sample_pois) as mock_comb:
        with TestClient(app) as client:
            res = client.get("/api/poi/nearby?lat=42.7875&lng=141.6753&category=pharmacy&radius=1000")
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 1
    assert body["pois"][0]["name"] == "Tsuruha Drug New Chitose"
    assert mock_comb.call_args.kwargs.get("timeout") == 2.5
