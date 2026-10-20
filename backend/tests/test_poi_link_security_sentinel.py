"""
Test POI Link Security Sentinel
Verifies SSRF prevention, URL sanitization, and input safety for the POI extraction pipeline.
"""

import pytest
from utils.url_safety import is_safe_url, get_safe_ip
import re

def test_url_safety_blocks_loopback_and_metadata():
    # 1. Loopback addresses
    assert not is_safe_url("http://127.0.0.1:8000/internal")
    assert not is_safe_url("http://localhost:3000")
    assert not is_safe_url("http://0.0.0.0")

    # 2. Cloud metadata link-local
    assert not is_safe_url("http://169.254.169.254/computeMetadata/v1/")
    assert not is_safe_url("http://169.254.1.1")

    # 3. Private LAN addresses
    assert not is_safe_url("http://192.168.1.1/admin")
    assert not is_safe_url("http://10.0.0.1/secret")
    assert not is_safe_url("http://172.16.0.1/db")

    # 4. Dangerous / non-HTTP protocols
    assert not is_safe_url("file:///etc/passwd")
    assert not is_safe_url("gopher://127.0.0.1:6379")
    assert not is_safe_url("javascript:alert(1)")


def test_url_safety_allows_public_maps():
    assert is_safe_url("https://maps.app.goo.gl/ABC123XYZ")
    assert is_safe_url("https://www.google.com/maps/place/Tokyo+Tower")
    assert is_safe_url("https://maps.google.com/?cid=123456")


def test_mobile_share_sanitization():
    # Simulate iOS/Android Google Maps share clipboard text
    raw_inputs = [
        "東京拉麵私房地圖 https://maps.app.goo.gl/TestToken123",
        "Check out this place on Google Maps: 伏見稻荷大社 https://maps.app.goo.gl/TestToken456。",
        "https://www.google.com/maps/placelists/list/1a2b3c4d5e! Click here!",
        "隨手記 https://goo.gl/maps/ShortToken?entry=ttu..."
    ]

    expected_clean = [
        "https://maps.app.goo.gl/TestToken123",
        "https://maps.app.goo.gl/TestToken456",
        "https://www.google.com/maps/placelists/list/1a2b3c4d5e",
        "https://goo.gl/maps/ShortToken?entry=ttu"
    ]

    for raw, expected in zip(raw_inputs, expected_clean):
        match = re.search(r'(https?://[^\s]+)', raw)
        assert match is not None
        clean = match.group(1).rstrip('.,!?:;"\'。，！？')
        assert clean == expected


def test_poi_link_ssrf_security_guard():
    # Direct validation of SSRF defense without reliance on obsolete router
    assert not is_safe_url("http://127.0.0.1:8008/api/trips")
    assert not is_safe_url("http://169.254.169.254/latest/meta-data/")
    assert not is_safe_url("http://metadata.google.internal/computeMetadata/v1/")

