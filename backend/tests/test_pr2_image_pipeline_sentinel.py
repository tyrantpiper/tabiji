# -*- coding: utf-8 -*-
"""
Security Sentinel In-Memory PoC & Mantis Block G Benign Control Test Suite (PR 2)
=================================================================================
Verifies:
1. Module-level Pillow Image.MAX_IMAGE_PIXELS == 50_000_000 (zero worker-thread mutation).
2. Frontend/Backend bit-for-bit aligned receipt geometry (compute_receipt_target_dimensions).
3. /api/ai/parse-receipt:
   - Rejects invalid base64 without imageUrl (400) & unsupported Data URL MIME (400).
   - Falls back to safe_download_image(body.imageUrl) when body.image base64 fails and imageUrl is provided.
   - Benign control: valid direct body.image skips safe_download_image completely (0 downloads).
4. /api/chat:
   - Rejects unsupported MIME (image/svg+xml, text/html), invalid base64, and oversized payloads with 400 (not swallowed).
   - Gracefully degrades corrupt image bytes (strict=True ValueError -> text-only notice).
   - Benign control: valid high-res PNG is downscaled <= 2048px and forwarded to call_with_fallback.
"""

import base64
import io
import json
import os
import sys
from unittest.mock import AsyncMock, patch

from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import app
from routers.ai import compute_receipt_target_dimensions, process_and_optimize_image_sync
from utils.deps import get_verified_user

client = TestClient(app)

HEADERS = {
    "X-Gemini-API-Key": "AIzaSyPR2SentinelTestKey" + "1" * 16,
    "Content-Type": "application/json",
}


def _make_png_bytes(width: int, height: int, mode: str = "RGB") -> bytes:
    img = Image.new(mode, (width, height), (220, 40, 40, 128) if mode == "RGBA" else (220, 40, 40))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_data_url(raw: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def test_module_level_max_image_pixels_set_on_import():
    assert Image.MAX_IMAGE_PIXELS == 50_000_000


def test_benign_receipt_target_dimensions_parity_with_frontend():
    """Mantis Block G Benign Control: Bit-for-bit parity with frontend computeTargetDimensions."""
    assert compute_receipt_target_dimensions(4000, 3000, 2048) == (2048, 1536)
    assert compute_receipt_target_dimensions(1200, 4800, 2048) == (1024, 4096)
    assert compute_receipt_target_dimensions(1000, 5000, 2048) == (819, 4096)
    assert compute_receipt_target_dimensions(2000, 6000, 2048) == (1200, 3600)
    assert compute_receipt_target_dimensions(800, 600, 2048) == (800, 600)

    # Real Pillow verification on long 1:4 receipt
    long_receipt = _make_png_bytes(1200, 4800)
    out_bytes, out_mime = process_and_optimize_image_sync(long_receipt, max_dimension=2048)
    assert out_mime == "image/jpeg"
    with Image.open(io.BytesIO(out_bytes)) as res_img:
        assert res_img.size == (1024, 4096)


def test_process_and_optimize_strict_mode_raises_on_corrupt_bytes():
    corrupt = b"not-a-valid-image-stream"
    # Legacy default strict=False preserves fallback
    fallback_bytes, fallback_mime = process_and_optimize_image_sync(corrupt, max_dimension=2048, strict=False)
    assert fallback_bytes == corrupt
    assert fallback_mime == "image/jpeg"

    # Strict mode raises ValueError for /api/chat degradation guard
    try:
        process_and_optimize_image_sync(corrupt, max_dimension=2048, strict=True)
        assert False, "Expected ValueError in strict mode"
    except ValueError:
        pass


def test_parse_receipt_rejects_invalid_base64_and_svg_mime():
    res_bad_b64 = client.post(
        "/api/ai/parse-receipt",
        json={"image": "data:image/jpeg;base64,!!!NOT_BASE64!!!", "locale": "en"},
        headers=HEADERS,
    )
    assert res_bad_b64.status_code == 400

    svg_b64 = base64.b64encode(b"<svg xmlns='http://www.w3.org/2000/svg'/>").decode("ascii")
    res_svg = client.post(
        "/api/ai/parse-receipt",
        json={"image": f"data:image/svg+xml;base64,{svg_b64}", "locale": "en"},
        headers=HEADERS,
    )
    assert res_svg.status_code == 400


def test_benign_parse_receipt_direct_image_skips_download_and_falls_back_when_b64_corrupt():
    """Mantis Block G Benign Control: Direct base64 skips safe_download_image; corrupt base64 with imageUrl falls back cleanly."""
    ai_json = json.dumps({
        "title": "FamilyMart",
        "date": "2026-11-22",
        "currency": "JPY",
        "subtotal_amount": 400.0,
        "total_amount": 400.0,
        "items": [{"original_name": "Coffee", "translated_name": "咖啡", "amount": 400.0}],
    })
    tiny_png = _make_png_bytes(10, 10)

    # 1. Valid direct image -> safe_download_image MUST NOT be called
    with (
        patch("routers.ai.safe_download_image", new_callable=AsyncMock) as mock_dl,
        patch("routers.ai.call_extraction", new_callable=AsyncMock, return_value=ai_json),
    ):
        res = client.post(
            "/api/ai/parse-receipt",
            json={
                "image": _make_data_url(tiny_png, "image/png"),
                "imageUrl": "https://res.cloudinary.com/dnpcnwrcu/image/upload/v1/ryan_travel/receipts/r1.jpg",
                "locale": "zh",
            },
            headers=HEADERS,
        )
        assert res.status_code == 200
        assert mock_dl.await_count == 0

    # 2. Invalid base64 WITH imageUrl -> falls back to safe_download_image(imageUrl)
    with (
        patch("routers.ai.safe_download_image", new_callable=AsyncMock, return_value=(tiny_png, "image/png")) as mock_dl,
        patch("routers.ai.call_extraction", new_callable=AsyncMock, return_value=ai_json),
    ):
        res = client.post(
            "/api/ai/parse-receipt",
            json={
                "image": "data:image/jpeg;base64,!!!BROKEN_B64!!!",
                "imageUrl": "https://res.cloudinary.com/dnpcnwrcu/image/upload/v1/ryan_travel/receipts/r1.jpg",
                "locale": "zh",
            },
            headers=HEADERS,
        )
        assert res.status_code == 200
        assert mock_dl.await_count == 1


def test_chat_rejects_svg_invalid_base64_and_oversized_image_with_400():
    """HTTPException 400s in /api/chat image validation MUST propagate (never swallowed by except Exception)."""
    svg_b64 = base64.b64encode(b"<svg/>").decode("ascii")
    prev_override = app.dependency_overrides.get(get_verified_user)
    app.dependency_overrides[get_verified_user] = lambda: "00000000-0000-4000-8000-000000000001"
    try:
        with (
            patch("main.MemoryService.get_preferences_context", new_callable=AsyncMock, return_value=""),
            patch("main.classify_chat_intent", new_callable=AsyncMock, return_value=("CHAT", None)),
            patch("main.call_with_fallback", new_callable=AsyncMock) as mock_llm,
        ):
            res_svg = client.post(
                "/api/chat",
                json={"message": "What is this?", "image": f"data:image/svg+xml;base64,{svg_b64}", "locale": "en"},
                headers=HEADERS,
            )
            assert res_svg.status_code == 400

            res_bad_b64 = client.post(
                "/api/chat",
                json={"message": "What is this?", "image": "data:image/jpeg;base64,***INVALID***", "locale": "en"},
                headers=HEADERS,
            )
            assert res_bad_b64.status_code == 400

            oversized_b64 = "data:image/jpeg;base64," + ("A" * (28 * 1024 * 1024))
            res_big = client.post(
                "/api/chat",
                json={"message": "What is this?", "image": oversized_b64, "locale": "en"},
                headers=HEADERS,
            )
            assert res_big.status_code == 400
            assert mock_llm.await_count == 0
    finally:
        if prev_override is None:
            app.dependency_overrides.pop(get_verified_user, None)
        else:
            app.dependency_overrides[get_verified_user] = prev_override


def test_benign_chat_valid_image_downscaled_and_corrupt_bytes_gracefully_degrade():
    """Mantis Block G Benign Control: Valid PNG downscales cleanly; truly corrupt image bytes degrade gracefully to text."""
    captured_messages = []

    async def fake_call_with_fallback(**kwargs):
        captured_messages.append(kwargs["message"])
        return {
            "text": "Looks like Tokyo Station!",
            "raw_parts": [{"text": "Looks like Tokyo Station!"}],
            "model_used": "gemini-test",
            "grounding_metadata": None,
        }

    large_png = _make_png_bytes(3000, 2000, mode="RGBA")
    corrupt_b64 = base64.b64encode(b"valid-base64-but-not-an-image").decode("ascii")

    prev_override = app.dependency_overrides.get(get_verified_user)
    app.dependency_overrides[get_verified_user] = lambda: "00000000-0000-4000-8000-000000000001"
    try:
        with (
            patch("main.MemoryService.get_preferences_context", new_callable=AsyncMock, return_value=""),
            patch("main.classify_chat_intent", new_callable=AsyncMock, return_value=("CHAT", None)),
            patch("main.call_with_fallback", side_effect=fake_call_with_fallback),
        ):
            # 1. Valid high-res RGBA PNG -> downscaled <= 2048 JPEG and forwarded as multimodal [Part, Part]
            res_ok = client.post(
                "/api/chat",
                json={"message": "Where is this?", "image": _make_data_url(large_png, "image/png"), "locale": "en"},
                headers=HEADERS,
            )
            assert res_ok.status_code == 200
            assert isinstance(captured_messages[0], list)
            img_part = captured_messages[0][0]
            assert img_part.inline_data.mime_type == "image/jpeg"
            with Image.open(io.BytesIO(img_part.inline_data.data)) as decoded:
                assert max(decoded.size) <= 2048

            # 2. Corrupt image bytes (valid base64, valid MIME) -> gracefully degrades to text notice (200)
            res_corrupt = client.post(
                "/api/chat",
                json={"message": "Analyze please", "image": f"data:image/jpeg;base64,{corrupt_b64}", "locale": "en"},
                headers=HEADERS,
            )
            assert res_corrupt.status_code == 200
            assert isinstance(captured_messages[1], str)
            assert "System Notice" in captured_messages[1]
    finally:
        if prev_override is None:
            app.dependency_overrides.pop(get_verified_user, None)
        else:
            app.dependency_overrides[get_verified_user] = prev_override


def test_parse_md_rejects_svg_octet_stream_invalid_base64_and_oversized_image():
    """/api/ai/parse-md MUST enforce MIME allowlist and pre/post-decode size limits (matching /api/chat)."""
    svg_b64 = base64.b64encode(b"<svg xmlns='http://www.w3.org/2000/svg'/>").decode("ascii")
    raw_b64 = base64.b64encode(b"fake-bytes").decode("ascii")
    prev_override = app.dependency_overrides.get(get_verified_user)
    app.dependency_overrides[get_verified_user] = lambda: "00000000-0000-4000-8000-000000000001"
    try:
        with patch("routers.ai.call_extraction", new_callable=AsyncMock) as mock_extract:
            res_svg = client.post(
                "/api/ai/parse-md",
                json={"markdown_text": "", "user_id": "u1", "image_base64": f"data:image/svg+xml;base64,{svg_b64}", "locale": "en"},
                headers=HEADERS,
            )
            assert res_svg.status_code == 400

            res_octet = client.post(
                "/api/ai/parse-md",
                json={"markdown_text": "", "user_id": "u1", "image_base64": f"data:application/octet-stream;base64,{raw_b64}", "locale": "en"},
                headers=HEADERS,
            )
            assert res_octet.status_code == 400

            res_bad_b64 = client.post(
                "/api/ai/parse-md",
                json={"markdown_text": "", "user_id": "u1", "image_base64": "data:image/jpeg;base64,!!!BAD!!!", "locale": "en"},
                headers=HEADERS,
            )
            assert res_bad_b64.status_code == 400

            oversized = "data:image/jpeg;base64," + ("A" * (28 * 1024 * 1024))
            res_big = client.post(
                "/api/ai/parse-md",
                json={"markdown_text": "", "user_id": "u1", "image_base64": oversized, "locale": "en"},
                headers=HEADERS,
            )
            assert res_big.status_code == 400
            assert mock_extract.await_count == 0
    finally:
        if prev_override is None:
            app.dependency_overrides.pop(get_verified_user, None)
        else:
            app.dependency_overrides[get_verified_user] = prev_override


def test_benign_parse_md_downscales_highres_and_accepts_heic():
    """Mantis Block G Benign Control: /api/ai/parse-md downscales 3000x2000 PNG & processes image/heic via process_and_optimize_image_sync."""
    captured_parts = []

    async def fake_extract(api_key, parts, **kwargs):
        captured_parts.append(parts)
        return json.dumps({
            "title": "Tokyo Trip",
            "destination": "Tokyo",
            "items": [
                {
                    "day_number": 1,
                    "time_slot": "10:00",
                    "place_name": "Shinjuku",
                    "category": "spot",
                    "desc": "Explore",
                    "tags": [],
                    "sub_items": [],
                }
            ],
        })

    large_png = _make_png_bytes(3000, 2000, mode="RGBA")
    prev_override = app.dependency_overrides.get(get_verified_user)
    app.dependency_overrides[get_verified_user] = lambda: "00000000-0000-4000-8000-000000000001"
    try:
        with (
            patch("routers.ai.call_extraction", side_effect=fake_extract),
            patch("services.geocode_service.smart_geocode_logic", new_callable=AsyncMock, return_value=None),
        ):
            res_png = client.post(
                "/api/ai/parse-md",
                json={"markdown_text": "", "user_id": "u1", "image_base64": _make_data_url(large_png, "image/png"), "locale": "en"},
                headers=HEADERS,
            )
            assert res_png.status_code == 200
            img_part = captured_parts[0][0]
            assert img_part.inline_data.mime_type == "image/jpeg"
            with Image.open(io.BytesIO(img_part.inline_data.data)) as decoded:
                assert max(decoded.size) <= 2048

            res_heic = client.post(
                "/api/ai/parse-md",
                json={"markdown_text": "", "user_id": "u1", "image_base64": _make_data_url(large_png, "image/heic"), "locale": "en"},
                headers=HEADERS,
            )
            assert res_heic.status_code == 200
            heic_part = captured_parts[1][0]
            assert heic_part.inline_data.mime_type == "image/jpeg"
            with Image.open(io.BytesIO(heic_part.inline_data.data)) as decoded_heic:
                assert max(decoded_heic.size) <= 2048
    finally:
        if prev_override is None:
            app.dependency_overrides.pop(get_verified_user, None)
        else:
            app.dependency_overrides[get_verified_user] = prev_override
