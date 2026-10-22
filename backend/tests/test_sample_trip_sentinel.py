import pytest
import httpx
import time
import jwt
from unittest.mock import MagicMock
from main import app
from utils.deps import get_supabase, get_session_secret

def make_auth_header(uid: str):
    token = jwt.encode(
        {
            "sub": uid,
            "iss": "tabiji-core",
            "type": "device_session",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600
        },
        get_session_secret(),
        algorithm="HS256"
    )
    return {"Authorization": f"Bearer {token}"}

class MockQueryBuilder:
    def __init__(self, data=None):
        self._data = data if data is not None else []
        self._action = "select"

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def insert(self, payload):
        if isinstance(payload, dict):
            self._data = [{**payload, "id": "mock-trip-uuid-123"}]
        elif isinstance(payload, list):
            self._data = [{**p, "id": f"mock-item-{i}"} for i, p in enumerate(payload)]
        return self

    def execute(self):
        res = MagicMock()
        res.data = self._data
        return res

class MockSupabaseClient:
    def __init__(self, has_existing_sample=False):
        self.has_existing_sample = has_existing_sample

    def table(self, table_name: str):
        if table_name == "trip_members":
            if self.has_existing_sample:
                return MockQueryBuilder(data=[{"itinerary_id": "existing-sample-id"}])
            return MockQueryBuilder(data=[])
        elif table_name == "itineraries":
            if self.has_existing_sample:
                return MockQueryBuilder(data=[{"id": "existing-sample-id"}])
            return MockQueryBuilder(data=[{"id": "new-sample-trip-id"}])
        elif table_name == "itinerary_items":
            return MockQueryBuilder(data=[])
        return MockQueryBuilder(data=[])

@pytest.mark.asyncio
async def test_seed_sample_trip_missing_user_id_returns_401():
    """Security Sentinel: Missing Bearer JWT must be rejected with 401."""
    app.dependency_overrides[get_supabase] = lambda: MockSupabaseClient()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post("/api/trips/seed-sample")
            assert response.status_code == 401
            assert "token" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_supabase, None)

@pytest.mark.asyncio
async def test_seed_sample_trip_dedup_skips_duplicate_seed():
    """Security Sentinel: Idempotent dedup prevents duplicate seeding and quota bypass."""
    mock_supabase = MockSupabaseClient(has_existing_sample=True)
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                "/api/trips/seed-sample",
                headers=make_auth_header("77777777-7777-7777-7777-777777777777")
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "skipped"
            assert data["reason"] == "already_has_sample"
    finally:
        app.dependency_overrides.pop(get_supabase, None)

@pytest.mark.asyncio
async def test_seed_sample_trip_success_for_new_user():
    """Security Sentinel: Initial seed creates sample trip with SYSTEM attribution."""
    mock_supabase = MockSupabaseClient(has_existing_sample=False)
    app.dependency_overrides[get_supabase] = lambda: mock_supabase

    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.post(
                "/api/trips/seed-sample",
                headers=make_auth_header("88888888-8888-8888-8888-888888888888")
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["is_sample"] is True
            assert "trip_id" in data
    finally:
        app.dependency_overrides.pop(get_supabase, None)
