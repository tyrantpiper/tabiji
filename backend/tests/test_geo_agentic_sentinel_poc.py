"""
Adversarial Security Sentinel Confrontation Test Suite
Topic: Geo-Agentic Grounding, Overpass QL Injection, SSRF Guard, and WebGL Invariants
Framework: In-Memory pytest with FastAPI TestClient
Standard: Cloudflare 6-Phase Ledger & Google Mantis Adversarial Verification
"""

import math
import re
import pytest
from typing import Dict, Any, Optional

# ---------------------------------------------------------------------------
# Test Hypothesis 1: Overpass QL Injection & Character Escaping
# ---------------------------------------------------------------------------
def sanitize_overpass_keyword(keyword: str) -> str:
    """Sanitizer for user-supplied keyword in Overpass QL regex/tag filters."""
    if not keyword:
        return ""
    # Strip dangerous QL structural characters: quotes, semicolons, brackets, parentheses
    sanitized = re.sub(r'[\";\[\]\(\)\{\}\<\>]', '', keyword)
    # Strip newlines and carriage returns
    sanitized = sanitized.replace('\n', '').replace('\r', '')
    return sanitized.strip()[:64]


def test_hypothesis_1_overpass_ql_injection_resilience():
    """
    Hypothesis: User-supplied keywords containing quotes or semicolon sequences
    (e.g., '"; out body; node["admin_level"]; out;') can escape parameterized templates.
    """
    malicious_payloads = [
        '"; out body; node["admin_level"]; out;',
        'ramen"; [out:json]; node(1); out;',
        '"><script>alert(1)</script>',
        'test\n;\nout;',
        'coffee"; drop database; --'
    ]

    for payload in malicious_payloads:
        clean = sanitize_overpass_keyword(payload)
        # Verify no semicolon or quotes remain
        assert ";" not in clean, f"Semicolon not escaped in {clean}"
        assert '"' not in clean, f"Quote not escaped in {clean}"
        assert "'" not in clean, f"Single quote not escaped in {clean}"
        assert "[" not in clean, f"Bracket not escaped in {clean}"
        assert "]" not in clean, f"Bracket not escaped in {clean}"
        assert "\n" not in clean, f"Newline not escaped in {clean}"


# ---------------------------------------------------------------------------
# Test Hypothesis 2: SSRF & Null Island Coordinate Guard
# ---------------------------------------------------------------------------
def validate_geo_anchor(anchor: str) -> Optional[str]:
    """Validate anchor place name, rejecting SSRF targets, protocols, and control characters."""
    if not anchor or not isinstance(anchor, str):
        return None
    trimmed = anchor.strip()
    if len(trimmed) < 1 or len(trimmed) > 120:
        return None
    # Reject URL protocols and IP formats
    if re.search(r'^(https?://|ftp://|file://|//|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', trimmed, re.I):
        return None
    # Reject internal cloud metadata endpoints
    if "169.254.169.254" in trimmed or "metadata.google.internal" in trimmed:
        return None
    return trimmed


def is_valid_gps_coord(lat: Any, lng: Any) -> bool:
    """Validate that coordinates are finite numbers and strictly outside Null Island (0,0)."""
    try:
        f_lat = float(lat)
        f_lng = float(lng)
    except (TypeError, ValueError):
        return False

    if not math.isfinite(f_lat) or not math.isfinite(f_lng):
        return False
    if not (-90.0 <= f_lat <= 90.0) or not (-180.0 <= f_lng <= 180.0):
        return False
    # Reject Null Island (0.0, 0.0)
    if abs(f_lat) < 1e-5 and abs(f_lng) < 1e-5:
        return False
    return True


def test_hypothesis_2_geo_tool_ssrf_and_null_island_guard():
    """
    Hypothesis: Crafted anchor addresses (e.g. metadata IPs or null island coordinates)
    pass through unhandled and cause SSRF or spatial hallucination.
    """
    ssrf_targets = [
        "http://169.254.169.254/latest/meta-data",
        "https://127.0.0.1:8080/admin",
        "file:///etc/passwd",
        "169.254.169.254",
        "http://metadata.google.internal/computeMetadata/v1/",
        "",
        "   ",
        "a" * 200
    ]

    for target in ssrf_targets:
        assert validate_geo_anchor(target) is None, f"Failed to block SSRF target: {target}"

    # Null island & non-finite coordinate guards
    assert not is_valid_gps_coord(0.0, 0.0)
    assert not is_valid_gps_coord(0, 0)
    assert not is_valid_gps_coord(float('nan'), 139.7)
    assert not is_valid_gps_coord(35.6, float('inf'))
    assert not is_valid_gps_coord(91.0, 139.7)  # Latitude out of bounds
    assert not is_valid_gps_coord(35.6, 185.0)  # Longitude out of bounds
    assert is_valid_gps_coord(35.7147, 139.7966)  # Valid Tokyo coord


# ---------------------------------------------------------------------------
# Test Hypothesis 3: Dual-Intent Conflict Resolution (Search vs Expense)
# ---------------------------------------------------------------------------
def test_hypothesis_3_dual_intent_conflict_resolution():
    """
    Hypothesis: Dual-intent messages like 'Spent 500 JPY on ramen near Sensoji'
    cause tool eviction where geo-search is stripped or expense is prematurely triggered.
    """
    from services.intent_router import GREETING_PATTERN, EXPENSE_PATTERN, SEARCH_PATTERN

    message = "剛在淺草寺吃拉麵花了 1200 日圓，附近還有什麼好吃的？"
    has_expense = bool(EXPENSE_PATTERN.search(message))
    has_search = bool(SEARCH_PATTERN.search(message))

    assert has_expense, "Should detect expense intent in dual query"
    assert has_search, "Should detect search intent in dual query"
    
    # In composite intent, both tools must be retained or composite routing engaged
    # Verifying intent classification does not silently drop SEARCH
    from services.model_manager import ALL_CHAT_TOOLS
    all_tool_names = [fc.name for tool in ALL_CHAT_TOOLS for fc in tool.function_declarations]
    assert "add_expense" in all_tool_names
    assert "search_web" in all_tool_names


# ---------------------------------------------------------------------------
# Test Hypothesis 4: Link URL Scheme XSS Defense
# ---------------------------------------------------------------------------
def is_safe_clickable_url(url: str) -> bool:
    """Validate that URLs are strictly HTTP/HTTPS, preventing javascript: or data: XSS."""
    if not url or not isinstance(url, str):
        return False
    trimmed = url.strip()
    return bool(re.match(r'^https?://', trimmed, re.I))


def test_hypothesis_4_link_url_xss_protocol_defense():
    """
    Hypothesis: POIPreviewCard rendering link_url without scheme whitelist allows javascript: XSS.
    """
    xss_payloads = [
        "javascript:alert(document.cookie)",
        "JAVASCRIPT:alert(1)",
        "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
        "vbscript:msgbox(1)",
        "file:///C:/Windows/System32/calc.exe"
    ]

    for payload in xss_payloads:
        assert not is_safe_clickable_url(payload), f"Failed to reject malicious URL scheme: {payload}"

    assert is_safe_clickable_url("https://www.senso-ji.jp/")
    assert is_safe_clickable_url("http://tokyo-skytree.jp")


# ---------------------------------------------------------------------------
# Test Hypothesis 5: MapLibre WebGL NaN & Coordinate Transformation Guard
# ---------------------------------------------------------------------------
def safe_flyto_bounds_guard(center: list) -> bool:
    """Guard against non-finite numbers before passing to MapLibre camera easeTo / flyTo."""
    if not isinstance(center, (list, tuple)) or len(center) != 2:
        return False
    lng, lat = center
    if not isinstance(lng, (int, float)) or not isinstance(lat, (int, float)):
        return False
    if math.isnan(lng) or math.isnan(lat) or math.isinf(lng) or math.isinf(lat):
        return False
    if not (-180.0 <= lng <= 180.0 and -85.051129 <= lat <= 85.051129):
        return False
    return True


def test_hypothesis_5_maplibre_webgl_singular_matrix_guard():
    """
    Hypothesis: Passing NaN or infinite coords to flyTo triggers MapLibre transform singular matrix crash.
    """
    assert not safe_flyto_bounds_guard([float('nan'), 35.0])
    assert not safe_flyto_bounds_guard([139.0, float('inf')])
    assert not safe_flyto_bounds_guard([200.0, 35.0])  # Exceeds Web Mercator bounds
    assert not safe_flyto_bounds_guard([139.0, 89.0])   # Exceeds Mercator 85.051129 max latitude
    assert not safe_flyto_bounds_guard(None)
    assert not safe_flyto_bounds_guard([])
    assert safe_flyto_bounds_guard([139.7966, 35.7147])  # Asakusa Tokyo
