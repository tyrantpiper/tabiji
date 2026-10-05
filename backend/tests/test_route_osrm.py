import pytest
from fastapi.testclient import TestClient
from main import app
from routers.route import haversine_distance_km, create_straight_fallback, RouteLRUCache
from models.base import RouteStop

client = TestClient(app)

def test_haversine_formula():
    # Taipei 101 (25.0339, 121.5645) to Raohe Night Market (25.0513, 121.5779)
    dist = haversine_distance_km(25.0339, 121.5645, 25.0513, 121.5779)
    assert 2.0 < dist < 3.0

def test_straight_fallback_structure():
    stops = [
        RouteStop(lat=25.0339, lng=121.5645, name="101"),
        RouteStop(lat=25.0513, lng=121.5779, name="Raohe")
    ]
    res = create_straight_fallback(stops, "walk")
    assert res["source"] == "straight-line"
    assert res["route"]["type"] == "Feature"
    assert res["route"]["geometry"]["type"] == "LineString"
    assert len(res["route"]["geometry"]["coordinates"]) == 2
    assert res["route"]["geometry"]["coordinates"][0] == [121.5645, 25.0339]

def test_route_lru_cache():
    cache = RouteLRUCache(maxsize=2, ttl_sec=5.0)
    cache.set("k1", {"data": 1})
    cache.set("k2", {"data": 2})
    assert cache.get("k1") == {"data": 1}
    
    # Eviction on exceeding maxsize
    cache.set("k3", {"data": 3})
    assert cache.get("k2") is None  # k2 was oldest after k1 was accessed
    assert cache.get("k1") == {"data": 1}
    assert cache.get("k3") == {"data": 3}

def test_calculate_route_endpoint():
    payload = {
        "stops": [
            {"lat": 25.0339, "lng": 121.5645, "name": "Taipei 101"},
            {"lat": 25.0513, "lng": 121.5779, "name": "Raohe"}
        ],
        "mode": "walk",
        "optimize": False
    }
    # First call - calculates or falls back
    res1 = client.post("/api/route", json=payload)
    assert res1.status_code == 200
    data1 = res1.json()
    assert "route" in data1
    assert data1["route"]["type"] == "Feature"
    assert data1["route"]["geometry"]["type"] == "LineString"
    assert len(data1["route"]["geometry"]["coordinates"]) >= 2

    # Second call - should hit cache
    res2 = client.post("/api/route", json=payload)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["distance"] == data1["distance"]
