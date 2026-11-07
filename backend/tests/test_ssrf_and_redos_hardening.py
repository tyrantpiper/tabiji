"""
Test SSRF & ReDoS Hardening Sentinel
Validates:
1. create_safe_client request hook intercepting initial & 302 redirect SSRF attacks
2. is_ip_safe blocking full range of RFC1918, CGNAT, link-local, loopback, IPv6 local
3. is_safe_url blocking BLOCKED_HOSTNAMES while preserving SAFE_WIKI_DOMAINS
4. web_search_engine delegation to is_safe_url
5. geocode_service ReDoS immunity with bounded regex and string truncation
"""

import pytest
import httpx
import asyncio
import time
from utils.url_safety import is_safe_url, is_ip_safe, create_safe_client, BLOCKED_HOSTNAMES, SAFE_WIKI_DOMAINS
from services.web_search_engine import is_safe_external_url, get_search_client
from services.geocode_service import extract_region_for_search, extract_all_regions_from_text


# ============================================================================
# 1. IP & Hostname Safety Tests
# ============================================================================

def test_is_ip_safe_blocked_subnets():
    # 127.0.0.0/8
    assert not is_ip_safe("127.0.0.1")
    assert not is_ip_safe("127.255.255.254")

    # 10.0.0.0/8
    assert not is_ip_safe("10.0.0.1")
    assert not is_ip_safe("10.254.1.1")

    # 172.16.0.0/12
    assert not is_ip_safe("172.16.0.1")
    assert not is_ip_safe("172.31.255.255")

    # 192.168.0.0/16
    assert not is_ip_safe("192.168.1.1")
    assert not is_ip_safe("192.168.100.200")

    # 169.254.0.0/16 (Cloud Metadata)
    assert not is_ip_safe("169.254.169.254")
    assert not is_ip_safe("169.254.1.1")

    # 100.64.0.0/10 (CGNAT)
    assert not is_ip_safe("100.64.0.1")
    assert not is_ip_safe("100.127.255.254")

    # 0.0.0.0/8
    assert not is_ip_safe("0.0.0.0")
    assert not is_ip_safe("0.1.2.3")

    # IPv6 ::1/128, fc00::/7, fe80::/10
    assert not is_ip_safe("::1")
    assert not is_ip_safe("fc00::1")
    assert not is_ip_safe("fd12:3456:789a::1")
    assert not is_ip_safe("fe80::1")

    # IPv4-mapped IPv6
    assert not is_ip_safe("::ffff:127.0.0.1")
    assert not is_ip_safe("::ffff:169.254.169.254")

    # Public IPs
    assert is_ip_safe("8.8.8.8")
    assert is_ip_safe("1.1.1.1")
    assert is_ip_safe("93.184.215.14")


def test_is_safe_url_blocked_hostnames():
    for host in BLOCKED_HOSTNAMES:
        assert not is_safe_url(f"http://{host}/api")
        assert not is_safe_url(f"https://{host}:8080/data")
        assert not is_safe_url(f"http://{host}./data")

    # Additional edge cases: integer IP, trailing dot FQDN, 0 literal
    assert not is_safe_url("http://2130706433/")
    assert not is_safe_url("http://0/")
    assert not is_safe_url("http://localhost./")
    assert not is_safe_url("http://metadata.google.internal./computeMetadata/v1")


def test_is_safe_url_preserves_wiki_domains():
    for domain in SAFE_WIKI_DOMAINS:
        assert is_safe_url(f"https://{domain}/wiki/Main_Page")
        assert is_safe_url(f"https://en.{domain}/wiki/Tokyo")


def test_web_search_engine_delegates_to_is_safe_url():
    assert is_safe_external_url("https://www.tokyo-skytree.jp/") is True
    assert is_safe_external_url("http://127.0.0.1:8000/secret") is False
    assert is_safe_external_url("http://metadata.google.internal/computeMetadata/v1") is False
    assert is_safe_external_url("http://169.254.169.254/latest/meta-data") is False
    assert is_safe_external_url("http://100.64.0.1/admin") is False


# ============================================================================
# 2. create_safe_client & 302 Redirect SSRF Interception Tests
# ============================================================================

@pytest.mark.asyncio
async def test_create_safe_client_blocks_direct_ssrf():
    client = create_safe_client()
    try:
        with pytest.raises(ValueError, match="SSRF Blocked"):
            await client.get("http://127.0.0.1:8080/admin")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_create_safe_client_blocks_302_redirect_to_metadata():
    def mock_redirect_handler(request: httpx.Request):
        if "start" in str(request.url):
            return httpx.Response(302, headers={"Location": "http://169.254.169.254/computeMetadata/v1/"})
        return httpx.Response(200, text="SHOULD_NOT_REACH")

    transport = httpx.MockTransport(mock_redirect_handler)
    client = create_safe_client(transport=transport, follow_redirects=True)
    try:
        with pytest.raises(ValueError, match="SSRF Blocked"):
            await client.get("https://en.wikipedia.org/start")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_create_safe_client_blocks_302_redirect_to_private_ip():
    def mock_redirect_handler(request: httpx.Request):
        if "start" in str(request.url):
            return httpx.Response(302, headers={"Location": "http://10.0.0.5/internal/status"})
        return httpx.Response(200, text="SHOULD_NOT_REACH")

    transport = httpx.MockTransport(mock_redirect_handler)
    client = create_safe_client(transport=transport, follow_redirects=True)
    try:
        with pytest.raises(ValueError, match="SSRF Blocked"):
            await client.get("https://en.wikipedia.org/start")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_create_safe_client_allows_safe_redirect():
    def mock_redirect_handler(request: httpx.Request):
        if "hop1" in str(request.url):
            return httpx.Response(302, headers={"Location": "https://en.wikipedia.org/hop2"})
        return httpx.Response(200, text="TARGET_REACHED")

    transport = httpx.MockTransport(mock_redirect_handler)
    client = create_safe_client(transport=transport, follow_redirects=True)
    try:
        resp = await client.get("https://en.wikipedia.org/hop1")
        assert resp.status_code == 200
        assert resp.text == "TARGET_REACHED"
    finally:
        await client.aclose()


# ============================================================================
# 3. Geocode Service ReDoS Immunity Tests
# ============================================================================

def test_extract_region_for_search_redos_defense():
    # Normal extractions
    assert extract_region_for_search("台北 3 日遊") == "台北"
    assert extract_region_for_search("東京 5天4夜 自由行") == "東京"
    assert extract_region_for_search("京都五日遊") == "京都"

    # Malicious pathological payload: long repetitive tokens that would hang unbounded regex
    malicious_input = ("9" * 300 + "日遊" + "天" * 200) * 10
    t0 = time.time()
    result = extract_region_for_search(malicious_input)
    duration = time.time() - t0
    # Must terminate virtually instantaneously (< 0.05s)
    assert duration < 0.05, f"extract_region_for_search took {duration:.4f}s - potential ReDoS vulnerability!"


def test_extract_all_regions_from_text_redos_defense():
    # Normal extraction
    regions = extract_all_regions_from_text("<destination>東京、京都</destination>")
    assert "東京" in regions
    assert "京都" in regions

    # Malicious oversized XML payload (> 100k characters)
    malicious_xml = "<destination>" + "A" * 50000 + "</destination>"
    t0 = time.time()
    result = extract_all_regions_from_text(malicious_xml)
    duration = time.time() - t0
    assert duration < 0.05, f"extract_all_regions_from_text took {duration:.4f}s - potential ReDoS vulnerability!"
