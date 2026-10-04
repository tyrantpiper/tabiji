"""
Test Suite for AI Trip Generation: Synchronous Legacy & SSE Streaming Endpoints
Guarantees zero-regression on existing routes and verifies Cloudflare keepalive streaming.
"""

import pytest
import json
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from main import app

HEADERS = {
    "X-Gemini-API-Key": "AIzaSy" + "A" * 34,
    "Content-Type": "application/json"
}

MOCK_TRIP_JSON = json.dumps({
    "title": "東京探索之旅",
    "destination": "東京",
    "currency": "JPY",
    "days": [
        {
            "day_number": 1,
            "activities": [
                {
                    "time": "09:00",
                    "place_name": "淺草寺",
                    "category": "sightseeing",
                    "desc": "東京最古老的寺廟",
                    "lat": 35.7148,
                    "lng": 139.7967,
                    "tags": ["文化"],
                    "is_highlight": True
                }
            ]
        }
    ],
    "day_metadata": [],
    "ai_review": "建議提早出發避開人潮。"
})


@pytest.mark.asyncio
async def test_legacy_synchronous_generate_trip():
    """Verify legacy POST /api/ai/generate-trip works with zero regression."""
    transport = ASGITransport(app=app)
    with patch("services.model_manager.call_extraction", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = MOCK_TRIP_JSON
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            res = await client.post("/api/ai/generate-trip", json={"prompt": "東京一日遊"}, headers=HEADERS)
            assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
            data = res.json()
            assert data["status"] == "success"
            assert "data" in data
            trip = data["data"]
            assert trip["title"] == "東京探索之旅"
            assert trip["destination"] == "東京"
            assert trip["currency"] == "JPY"
            assert len(trip["items"]) == 1
            assert trip["items"][0]["place_name"] == "淺草寺"


@pytest.mark.asyncio
async def test_streaming_generate_trip_success():
    """Verify new POST /api/ai/generate-trip/stream delivers SSE events with keepalive headers."""
    transport = ASGITransport(app=app)
    with patch("services.model_manager.call_extraction", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = MOCK_TRIP_JSON
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with client.stream("POST", "/api/ai/generate-trip/stream", json={"prompt": "東京一日遊"}, headers=HEADERS) as res:
                assert res.status_code == 200, f"Expected 200, got {res.status_code}"
                assert res.headers["content-type"].startswith("text/event-stream")
                assert res.headers["cache-control"] == "no-cache, no-transform"
                assert res.headers["x-accel-buffering"] == "no"

                events = []
                data_lines = []
                has_connected_probe = False

                async for line in res.aiter_lines():
                    if line == ": connected":
                        has_connected_probe = True
                    elif line.startswith("event:"):
                        events.append(line.split(":", 1)[1].strip())
                    elif line.startswith("data:"):
                        data_lines.append(line.split(":", 1)[1].strip())

                assert has_connected_probe is True
                assert "progress" in events
                assert "complete" in events
                assert "error" not in events

                final_payload = json.loads(data_lines[-1])
                assert final_payload["status"] == "success"
                assert final_payload["data"]["title"] == "東京探索之旅"


@pytest.mark.asyncio
async def test_streaming_generate_trip_error_handling():
    """Verify unhandled error in generator cleanly emits event: error and closes without stalling."""
    transport = ASGITransport(app=app)
    with patch("services.model_manager.call_extraction", new_callable=AsyncMock) as mock_extract:
        mock_extract.side_effect = RuntimeError("Upstream Gemini Quota Exceeded")
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with client.stream("POST", "/api/ai/generate-trip/stream", json={"prompt": "東京一日遊"}, headers=HEADERS) as res:
                assert res.status_code == 200, f"Expected 200, got {res.status_code}"

                events = []
                data_lines = []
                async for line in res.aiter_lines():
                    if line.startswith("event:"):
                        events.append(line.split(":", 1)[1].strip())
                    elif line.startswith("data:"):
                        data_lines.append(line.split(":", 1)[1].strip())

                assert "error" in events
                assert "complete" not in events
                error_payload = json.loads(data_lines[-1])
                assert error_payload.get("detail") == "行程生成過程遭遇非預期錯誤，請稍後重試"


@pytest.mark.asyncio
async def test_streaming_generate_trip_http_exception():
    """Verify HTTPException detail is preserved and returned in event: error."""
    from fastapi import HTTPException
    transport = ASGITransport(app=app)
    with patch("services.model_manager.call_extraction", new_callable=AsyncMock) as mock_extract:
        mock_extract.side_effect = HTTPException(status_code=429, detail="API 速率超限，請稍後再試")
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with client.stream("POST", "/api/ai/generate-trip/stream", json={"prompt": "東京一日遊"}, headers=HEADERS) as res:
                assert res.status_code == 200

                events = []
                data_lines = []
                async for line in res.aiter_lines():
                    if line.startswith("event:"):
                        events.append(line.split(":", 1)[1].strip())
                    elif line.startswith("data:"):
                        data_lines.append(line.split(":", 1)[1].strip())

                assert "error" in events
                error_payload = json.loads(data_lines[-1])
                assert error_payload.get("detail") == "API 速率超限，請稍後再試"
