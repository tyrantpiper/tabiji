"""
Security Sentinel In-Memory PoC Test Suite:
parse_markdown Deep Geocoding & SSRF / DOS / Type Confusion Defense

Validates:
1. SSRF and Domain Sanitization Guard for user-supplied link_url
2. Concurrency Semaphore & Per-Item 2.5s Timeout Shield
3. Type Confusion & Safe Float Defense
4. Structure Flattening Gate & Dynamic Self-Bootstrapping Spatial Anchor
"""

import pytest
import asyncio
import math
from typing import Optional, Dict, Any, List
from unittest.mock import AsyncMock, patch

from utils.url_safety import is_safe_url
from utils.molecular_parser import get_molecular_parser


# --- Implementation Prototype under Test (Mirroring ai.py enhancement) ---

def safe_float(val: Any) -> Optional[float]:
    """🛡️ Type Confusion Guard: Converts any messy LLM input to float or None."""
    try:
        if val is not None and str(val).strip().lower() not in ("none", "null", "n/a", ""):
            f = float(val)
            return f if (f != 0.0 and not math.isnan(f)) else None
    except (ValueError, TypeError):
        pass
    return None


def is_allowed_google_maps_url(url: Optional[str]) -> bool:
    """🛡️ SSRF Guard: Whitelist only official Google Maps domains and verify safety."""
    if not url:
        return False
    if not is_safe_url(url):
        return False
    # Strict domain regex with boundary anchor
    import re
    return bool(re.search(r'^https?://(?:maps\.app\.goo\.gl|goo\.gl/maps|(?:www\.)?google\.(?:com|co\.jp|com\.tw)/maps)(?:/|\?|$)', url))


async def run_deep_geocoding_pipeline(
    data: Dict[str, Any],
    mock_link_resolver=None,
    mock_smart_geocode=None
) -> Dict[str, Any]:
    """
    In-memory reproduction of the proposed ai.py parse_markdown deep geocoding pipeline.
    """
    # Step 0: Structure Flattening Gate (Days -> Flat Items)
    if not data.get("items") and "days" in data:
        flat_items = []
        for d in data["days"]:
            dn = d.get("day_number") or d.get("day") or 1
            for act in d.get("activities", []):
                act["day_number"] = dn
                act["place_name"] = act.get("place_name") or act.get("place") or "Unknown"
                act["time_slot"] = act.get("time_slot") or act.get("time") or "00:00"
                flat_items.append(act)
        data["items"] = flat_items

    raw_items = data.get("items", [])
    if not raw_items:
        return data

    mol_parser = get_molecular_parser()

    # Step 1: Zero-cost Long URL extraction
    for it in raw_items:
        it["lat"] = safe_float(it.get("lat"))
        it["lng"] = safe_float(it.get("lng"))
        link = it.get("link_url")
        if not it["lat"] and link and is_allowed_google_maps_url(link):
            coords = mol_parser.parse_url(link)
            if coords:
                it["lat"] = coords["lat"]
                it["lng"] = coords["lng"]

    # Step 2: Dynamic Spatial Anchor
    bias_lat, bias_lng = None, None
    raw_dest = data.get("destination") or data.get("title") or ""
    
    if raw_dest and "自由行" not in raw_dest:
        if mock_smart_geocode:
            anchor_res = await mock_smart_geocode(query=raw_dest, limit=1)
            if anchor_res and anchor_res.get("results"):
                bias_lat = anchor_res["results"][0].get("lat")
                bias_lng = anchor_res["results"][0].get("lng")

    # Self-bootstrapping anchor from already resolved items
    if not bias_lat:
        for it in raw_items:
            if it.get("lat") and it.get("lng"):
                bias_lat, bias_lng = it["lat"], it["lng"]
                break

    # Step 3: Concurrency Semaphore (10) & 2.5s Timeout Safe Lookup
    sem = asyncio.Semaphore(10)
    ACTION_NOISE_KEYWORDS = ("集合", "搭乘", "休息", "抵達", "出發", "退稅")

    async def _safe_geocode_item(item: dict) -> dict:
        if item.get("lat") and item.get("lng"):
            return item

        link = item.get("link_url")
        # SSRF-Protected Shortlink rescue
        if link and is_allowed_google_maps_url(link) and ("maps.app.goo.gl" in link or "goo.gl/maps" in link):
            if mock_link_resolver:
                async with sem:
                    try:
                        resolved = await asyncio.wait_for(mock_link_resolver(link), timeout=2.5)
                        if resolved and resolved.get("lat") and resolved.get("lng"):
                            item["lat"] = resolved["lat"]
                            item["lng"] = resolved["lng"]
                            return item
                    except Exception:
                        pass

        place_name = item.get("place_name") or item.get("original_name") or ""
        if not place_name or any(noise in place_name for noise in ACTION_NOISE_KEYWORDS):
            return item

        if mock_smart_geocode:
            async with sem:
                try:
                    geo_res = await asyncio.wait_for(
                        mock_smart_geocode(
                            query=place_name,
                            limit=1,
                            lat=bias_lat,
                            lng=bias_lng
                        ),
                        timeout=2.5
                    )
                    if geo_res and geo_res.get("results"):
                        item["lat"] = geo_res["results"][0]["lat"]
                        item["lng"] = geo_res["results"][0]["lng"]
                except Exception:
                    pass

        return item

    data["items"] = await asyncio.gather(*[_safe_geocode_item(it) for it in raw_items])
    return data


# --- Sentinel Test Suite ---

@pytest.mark.asyncio
async def test_ssrf_and_malicious_url_rejection():
    """Validates SSRF prevention: internal or non-Google URLs are rejected."""
    malicious_urls = [
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost:8000/admin",
        "https://evil.com/phishing?target=google.com/maps",
        "https://maps.app.goo.gl.attacker.com/evil",
        "https://goo.gl.attacker.com/maps",
        "javascript:alert(1)",
        "file:///etc/passwd"
    ]
    for url in malicious_urls:
        assert not is_allowed_google_maps_url(url), f"SSRF URL passed check: {url}"

    # Benign Control (Block G)
    benign_urls = [
        "https://maps.app.goo.gl/vX9Yh8mR1",
        "https://www.google.com/maps/place/Tokyo+Tower/@35.6585805,139.7454329,17z",
        "https://google.co.jp/maps/place/Kyoto/@35.0116,135.7681"
    ]
    for url in benign_urls:
        assert is_allowed_google_maps_url(url), f"Benign URL failed check: {url}"


@pytest.mark.asyncio
async def test_type_confusion_defense():
    """Validates that messy string / null / NaN inputs are safely cast without throwing."""
    assert safe_float("35.6585") == 35.6585
    assert safe_float(35.6585) == 35.6585
    assert safe_float("null") is None
    assert safe_float("None") is None
    assert safe_float("N/A") is None
    assert safe_float("") is None
    assert safe_float(0.0) is None
    assert safe_float(float("nan")) is None


@pytest.mark.asyncio
async def test_structure_flattening_and_dynamic_anchor_bootstrap():
    """
    Validates:
    1. LLM hallucinated 'days' structure is normalized before geocoding.
    2. Generic trip title ('自由行') triggers dynamic bootstrapping from Item 1's resolved URL.
    """
    payload = {
        "title": "5天4夜自由行",
        "days": [
            {
                "day_number": 1,
                "activities": [
                    {
                        "place_name": "東京鐵塔",
                        "link_url": "https://www.google.com/maps/place/Tokyo+Tower/@35.6585805,139.7454329,17z"
                    },
                    {
                        "place_name": "六本木之丘",
                        "link_url": None
                    }
                ]
            }
        ]
    }

    async def mock_smart_geocode(query, limit=1, lat=None, lng=None):
        if query == "六本木之丘" and lat == 35.6585805:
            # Successfully biased by Tokyo Tower's coordinates!
            return {"results": [{"lat": 35.6605, "lng": 139.7292}]}
        return {"results": []}

    res = await run_deep_geocoding_pipeline(payload, mock_smart_geocode=mock_smart_geocode)
    
    # Assert flattening succeeded
    assert "items" in res
    assert len(res["items"]) == 2
    # Item 1 resolved via MolecularParser
    assert res["items"][0]["lat"] == 35.6585805
    assert res["items"][0]["lng"] == 139.7454329
    # Item 2 resolved via smart_geocode using Item 1's bootstrapped anchor!
    assert res["items"][1]["lat"] == 35.6605
    assert res["items"][1]["lng"] == 139.7292


@pytest.mark.asyncio
async def test_concurrency_and_timeout_resilience():
    """
    Validates:
    1. A hanging lookup (3.5s delay) is terminated within 2.5s timeout.
    2. Action noise ('在飯店門口集合') is skipped without making lookup requests.
    3. Normal item resolves cleanly.
    """
    payload = {
        "title": "東京行",
        "items": [
            {"place_name": "在飯店門口集合"},
            {"place_name": "超慢伺服器景點"},
            {"place_name": "晴空塔"}
        ]
    }

    lookup_count = 0

    async def mock_smart_geocode(query, limit=1, lat=None, lng=None):
        nonlocal lookup_count
        lookup_count += 1
        if query == "超慢伺服器景點":
            await asyncio.sleep(4.0)  # Exceeds 2.5s timeout
            return {"results": [{"lat": 99.0, "lng": 99.0}]}
        if query == "晴空塔":
            return {"results": [{"lat": 35.7100, "lng": 139.8107}]}
        return {"results": []}

    res = await run_deep_geocoding_pipeline(payload, mock_smart_geocode=mock_smart_geocode)
    
    # Item 0 (Action noise) was skipped -> no geocode call
    assert res["items"][0].get("lat") is None
    # Item 1 timed out -> no crash, lat is None
    assert res["items"][1].get("lat") is None
    # Item 2 succeeded -> lat is populated
    assert res["items"][2]["lat"] == 35.7100
    assert res["items"][2]["lng"] == 139.8107
    # Lookup count should be exactly 3 (1 for '東京行' anchor + 2 for items; '在飯店門口集合' skipped)
    assert lookup_count == 3
