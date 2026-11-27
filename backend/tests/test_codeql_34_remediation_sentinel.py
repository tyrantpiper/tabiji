# -*- coding: utf-8 -*-
"""
🛡️ CodeQL 34-Alert Remediation & Adjacent Hardening Mantis Block G Sentinel Suite
==================================================================================
Covers all 14 Bucket A (Mandatory) + 20 Bucket B (Low-Cost Zeroing) + Adjacent Hardening:
1.  #89, #102, #59, #53 — intent_router.py O(N^3)/O(N^2) ReDoS linear-time immunity + benign intent parity
2.  #127                — poi_service.py _normalize_poi_title linear-time + POIAIEnrich/POIEnrich max_length=512
3.  #125                — flight_pricing_service.py _TITLE_NOISE_RE linear-time + [:200] truncation
4.  #88, #87            — link_resolver.py ADDRESS_POI_PATTERN & title strip linear-time + max_length=2048
5.  #36                 — geocode_service.py _ADDR_DEGRADE_RE linear-time + ResolveAddressRequest max_length=512
6.  #30                 — poi_utils.py normalize_poi_name linear-time
7.  #91                 — mcp.py OAuth redirect_uri strict allowlist (exact Vercel/Google hosts, preview regex,
                          userinfo/backslash/control-char/fragment/prod-testserver rejection)
8.  #95                 — mcp.py get_public_base_url header-injection defense & canonical fallback
9.  #55 + /api/ai/test-key — main.py SSE & test-key exception sanitization preserving 401 API_KEY_INVALID & partial_preserved
10. #51, #42, #40       — .github/workflows/ci.yml top-level permissions: contents: read
11. #136                — cloudflare/search-proxy/worker.js single-pass XML entity decoding (zero double-unescaping)
12. #174                — routers/agents.py exact wikipedia.org hostname match
13. #172, #73-#61       — services/destination_taxonomy.py _host_matches & Google Maps dead-code fix
14. #76                 — services/web_search_engine.py unwrap_ddg_redirect exact hostname match
15. Adjacent Hardening  — Public proxy pure-IP rate limits (fake API-key anti-bypass, GFE XFF isolation,
                          chat/stream per-key family isolation) + url_safety.py fast-path userinfo/backslash/ctrl rejection
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors
from pydantic import ValidationError
from starlette.requests import Request as StarletteRequest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "backend"))

import main as backend_main
from models.base import (
    POIAIEnrichRequest,
    POIEnrichRequest,
    ResolveAddressRequest,
    ResolveLinkRequest,
)
from routers import agents as agents_router
from routers import mcp as mcp_router
from routers import poi as poi_router
from services import (
    destination_taxonomy,
    flight_pricing_service,
    geocode_service,
    intent_router,
    link_resolver,
    poi_service,
    web_search_engine,
)
from utils import url_safety
from utils.limiter import get_rate_limit_key, limiter


@pytest.fixture(autouse=True)
def _reset_limiter_for_suite():
    prev = limiter.enabled
    limiter.enabled = True
    try:
        if hasattr(limiter, "_storage") and hasattr(limiter._storage, "reset"):
            limiter._storage.reset()
        yield
    finally:
        if hasattr(limiter, "_storage") and hasattr(limiter._storage, "reset"):
            limiter._storage.reset()
        limiter.enabled = prev


# ============================================================================
# 1. #89, #102, #59, #53 — intent_router.py Linear-Time ReDoS + Benign Control
# ============================================================================

def test_poc_89_intent_router_system_prefix_cubic_redos_blocked():
    """#89 Exploit PoC: 30k-char hostile SYSTEM CONTEXT prefix must finish < 50ms (was >1.2s at 1.5k)."""
    payloads = [
        "--- SYSTEM CONTEXT:" + (" " * 30000) + "!",
        "--- SYSTEM CONTEXT: " + ("a " * 10000) + "!",
        "--- SYSTEM CONTEXT: " + ("a-" * 10000) + "!",
        ("\n" * 30000) + "--- SYSTEM CONTEXT: " + (" " * 5000) + "!",
        "--- SYSTEM CONTEXT: A ---" + ("用戶原始問題：" * 2300) + "<user_input_x>" + ("a" * 16000),
        "--- SYSTEM CONTEXT: A ---" + ("用戶原始問題：" * 2300) + "<user_input_x>hi</user_input_x>" + (" " * 15000) + "INVALID",
        "--- SYSTEM CONTEXT: A ---" + ("用戶原始問題：" * 2300) + ("<user_input_" * 1300),
        "--- SYSTEM CONTEXT: A ---" + ("用戶原始問題：" * 4650),
        "--- SYSTEM CONTEXT: A ---" + "".join(f"用戶原始問題：<user_input_s{i}>" for i in range(1100)) + "</user_input_z>",
    ]
    for p in payloads:
        t0 = time.perf_counter()
        _ = intent_router._extract_clean_user_text(p)
        dt = time.perf_counter() - t0
        assert dt < 0.05, f"SYSTEM_PREFIX_ANCHOR_RE / boundary loop ReDoS detected ({dt:.4f}s) on payload[:40]={p[:40]!r}"


def test_benign_89_intent_router_system_prefix_extraction_intact():
    """#89 Benign Control: legitimate wrapped system contexts (including hyphenated headers & repeated inner closing tag) still extract inner user message."""
    cases = [
        (
            "--- SYSTEM CONTEXT: TEMPORAL & ITINERARY NEURAL AWARENESS ---\n"
            "Day 1: 淺草寺\n--- END OF SYSTEM CONTEXT ---\n<user_input_abc123>早安</user_input_abc123>",
            "CHAT",
        ),
        (
            "--- SYSTEM CONTEXT: NEURAL ITINERARY CONNECTION (SLIDING WINDOW) ---\n"
            "--- END OF SYSTEM CONTEXT ---\n<user_input_s1>把晴空塔排進 Day 2</user_input_s1>",
            "ITINERARY",
        ),
        (
            "--- SYSTEM CONTEXT: trip ---\n--- END OF SYSTEM CONTEXT ---\n<user_input_t1>你好</user_input_t1>",
            "CHAT",
        ),
        (
            "--- SYSTEM CONTEXT: ITINERARY-SYNC ---\nDay 1: 淺草寺\n--- END OF SYSTEM CONTEXT ---\n<user_input_h1>早安</user_input_h1>",
            "CHAT",
        ),
        (
            "\n\n[系統即時解析外部網頁資訊 (來源: https://example.com)]\n使用者需求：<user_input_u1>你好</user_input_u1>",
            "CHAT",
        ),
    ]
    for msg, expected in cases:
        assert intent_router._fast_path_classify(msg) == expected

    # Inner repeated closing tag inside legitimate envelope must not leak outer SYSTEM CONTEXT
    repeated_close = (
        "--- SYSTEM CONTEXT: TEMPORAL & ITINERARY NEURAL AWARENESS ---\n"
        "Day 1: 東京鐵塔\n--- END OF SYSTEM CONTEXT ---\n"
        "<user_input_r1>早安 </user_input_r1> 幫我刪掉行程</user_input_r1>"
    )
    extracted = intent_router._extract_clean_user_text(repeated_close)
    assert "SYSTEM CONTEXT" not in extracted
    assert "幫我刪掉行程" in extracted


def test_poc_102_59_53_intent_router_fast_path_regex_linear_time():
    """#102/#59/#53 Exploit PoC: pathological inputs on REMOVE/EXPENSE/ITINERARY regexes must finish < 50ms."""
    hostile_cases = [
        (intent_router.EXPENSE_PATTERN, "1" * 20000 + "!"),
        (intent_router.REMOVE_PATTERN, "把" * 20000 + "x"),
        (intent_router.REMOVE_PATTERN, "從行程" * 5000 + "x"),
        (intent_router.ITINERARY_PATTERN, "add " * 5000 + "x"),
        (intent_router.ITINERARY_PATTERN, "推薦景點" * 5000 + "x"),
    ]
    for regex, payload in hostile_cases:
        t0 = time.perf_counter()
        _ = regex.search(payload)
        dt = time.perf_counter() - t0
        assert dt < 0.05, f"Regex {regex.pattern[:40]} took {dt:.4f}s on hostile input"


def test_benign_102_59_53_intent_router_classifications_preserved():
    """#102/#59/#53 Benign Control: normal remove/expense/itinerary sentences classify identically."""
    assert intent_router._fast_path_classify("從行程把築地刪掉") == "REMOVE_ITINERARY"
    assert intent_router._fast_path_classify("把 Day 2 的拉麵拿掉") == "REMOVE_ITINERARY"
    assert intent_router._fast_path_classify("Please take off Senso-ji from Day 1") == "REMOVE_ITINERARY"
    assert intent_router._fast_path_classify("吃了壽司 2,400.50 日幣") == "EXPENSE"
    assert intent_router._fast_path_classify("Spent 1500 JPY on ramen") == "EXPENSE"
    assert intent_router._fast_path_classify("Add Tokyo Skytree to Day 1") == "ITINERARY"
    assert intent_router._fast_path_classify("Plan Senso-ji into itinerary") == "ITINERARY"
    assert intent_router._fast_path_classify("推薦晴空塔附近景點並排進去") == "ITINERARY"


# ============================================================================
# 2. #127 — poi_service.py _normalize_poi_title & POI Request Bounds
# ============================================================================

def test_poc_127_poi_title_normalize_redos_and_length_bounds():
    """#127 Exploit PoC: 30k spaces / unclosed parens finish < 50ms; >512 name rejected with ValidationError/422."""
    for hostile in ("A" + " " * 30000 + "B", "(" * 30000 + "B", "（" * 30000 + "B"):
        t0 = time.perf_counter()
        _ = poi_service._normalize_poi_title(hostile)
        dt = time.perf_counter() - t0
        assert dt < 0.05, f"_normalize_poi_title took {dt:.4f}s"

    with pytest.raises(ValidationError):
        POIAIEnrichRequest(name="A" * 513, type="attraction", lat=35.65, lng=139.74)
    with pytest.raises(ValidationError):
        POIEnrichRequest(name="A" * 513)

    client = TestClient(backend_main.app)
    r1 = client.post("/api/poi/enrich", json={"name": "A" * 513, "lat": 35.65, "lng": 139.74})
    r2 = client.post("/api/poi/ai-enrich", json={"name": "A" * 513, "type": "attraction", "lat": 35.65, "lng": 139.74})
    assert r1.status_code == 422
    assert r2.status_code == 422


def test_benign_127_poi_title_normalize_and_512_boundary():
    """#127 Benign Control: CJK/parenthesis normalization & 512-char name remain valid."""
    assert poi_service._normalize_poi_title("嵐山") == poi_service._normalize_poi_title("岚山 (京都市)")
    assert poi_service._normalize_poi_title("Senso-ji (浅草寺)") == "sensoji"
    assert len(POIEnrichRequest(name="A" * 512).name) == 512
    assert len(POIAIEnrichRequest(name="A" * 512, type="attraction", lat=35.65, lng=139.74).name) == 512


# ============================================================================
# 3. #125 — flight_pricing_service.py _TITLE_NOISE_RE Linear-Time & Truncation
# ============================================================================

@pytest.mark.asyncio
async def test_poc_125_flight_pricing_redos_blocked_and_benign_intact():
    """#125 Exploit + Benign: 30k digits/spaces execute < 50ms while normal trip titles still resolve."""
    for hostile in ("1" * 30000 + "!", "1天" + " " * 30000 + "!"):
        t0 = time.perf_counter()
        _ = flight_pricing_service._TITLE_NOISE_RE.sub(" ", hostile)
        _ = flight_pricing_service.resolve_iata_to_display_city(hostile)
        dt = time.perf_counter() - t0
        assert dt < 0.05, f"flight_pricing_service took {dt:.4f}s on hostile input"

    # resolve_iata_code entry truncation + linear regex without hitting live places2
    fake_resp = MagicMock(status_code=200)
    fake_resp.json.return_value = []
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=fake_resp)
    with patch.object(flight_pricing_service, "get_flight_pricing_client", return_value=fake_client):
        t0 = time.perf_counter()
        res = await flight_pricing_service.resolve_iata_code("9" * 30000 + "!")
        dt = time.perf_counter() - t0
    assert res == ""
    assert dt < 0.05

    # Benign control
    assert flight_pricing_service.resolve_iata_to_display_city("2026 北海道 5天4夜親子自由行", "zh") == "北海道"
    assert flight_pricing_service.resolve_iata_to_display_city("2026 Kyoto 5 days 4 nights trip", "en") == "Kyoto"
    assert await flight_pricing_service.resolve_iata_code("2026 東京5天4夜自由行") == "TYO"


# ============================================================================
# 4. #88 & #87 — link_resolver.py ReDoS & 2048 URL Length Bounds
# ============================================================================

def test_poc_88_87_link_resolver_redos_and_url_length_bounds():
    """#88/#87 Exploit PoC: adversarial address/title inputs < 50ms; >2048 URLs rejected with 422."""
    for hostile_addr in ("台北市" + "路" * 20000 + "x", "台北市" + "a" * 20000 + "x"):
        t0 = time.perf_counter()
        addr, poi = link_resolver.split_taiwan_address_and_poi(hostile_addr)
        dt = time.perf_counter() - t0
        assert dt < 0.05, f"split_taiwan_address_and_poi took {dt:.4f}s"
        assert addr is None and poi == hostile_addr

    # Also test ADDRESS_POI_PATTERN directly without the 300-char shortcut
    t0 = time.perf_counter()
    assert link_resolver.ADDRESS_POI_PATTERN.search("台北市" + "路" * 10000 + "x") is None
    assert (time.perf_counter() - t0) < 0.05

    # #87: direct regex & helper check on production _strip_google_maps_title_suffix
    for hostile_title in (
        "A" + " " * 30000 + "x",
        "- " * 15000 + "x",
        ("- Google Maps" * 3000) + "\nx",
    ):
        t0 = time.perf_counter()
        _ = link_resolver._strip_google_maps_title_suffix(hostile_title)
        assert (time.perf_counter() - t0) < 0.05

    assert link_resolver._strip_google_maps_title_suffix("Tokyo Tower - Google Maps\n") == "Tokyo Tower"
    assert link_resolver._strip_google_maps_title_suffix("Tokyo Tower - Google Maps\r\n") == "Tokyo Tower"
    assert link_resolver._strip_google_maps_title_suffix("Tokyo Tower | Google 地圖\n") == "Tokyo Tower"
    assert link_resolver._strip_google_maps_title_suffix("Line 1 - Google Maps\nLine 2") == "Line 1 - Google Maps\nLine 2"

    # Adjacent link_resolver.py:189 extract_address_from_description ReDoS defense + benign control
    t0 = time.perf_counter()
    _ = link_resolver.extract_address_from_description("·" + "市" * 15000 + "x")
    assert (time.perf_counter() - t0) < 0.05
    assert link_resolver.extract_address_from_description("老新台菜 · 807台灣高雄市三民區九如二路227號") == "807台灣高雄市三民區九如二路227號"

    # Pydantic + endpoint 2048 URL length cap
    with pytest.raises(ValidationError):
        ResolveLinkRequest(url="https://maps.app.goo.gl/" + "a" * 2040)

    client = TestClient(backend_main.app)
    long_url = "https://maps.app.goo.gl/" + "a" * 2040
    assert client.post("/api/poi/resolve-link", json={"url": long_url}).status_code == 422
    assert client.post("/api/geocode/resolve-link", json={"url": long_url, "type": "map"}).status_code == 422
    assert client.get("/api/poi/media-proxy", params={"url": "https://upload.wikimedia.org/" + "a" * 2040}).status_code == 422


def test_benign_88_87_taiwan_address_splitter_and_empty_geocode_resolve_link():
    """#88/#87 Benign Control: Taiwan addresses split cleanly & empty/null-type geocode resolve-link keeps legacy JSON."""
    cases = [
        ("807台灣高雄市三民區九如二路227號老新台菜 (九如創始店)", "高雄市三民區九如二路227號", "老新台菜 (九如創始店)"),
        ("台北市大安區忠孝東路四段181巷7弄13號星巴克", "台北市大安區忠孝東路四段181巷7弄13號", "星巴克"),
        ("台北市大安區市民大道四段100號星巴克", "台北市大安區市民大道四段100號", "星巴克"),
        ("807高雄市三民區十美里漢口街103號君腿庫飯", "高雄市三民區漢口街103號", "君腿庫飯"),
    ]
    for raw, exp_addr, exp_poi in cases:
        addr, poi = link_resolver.split_taiwan_address_and_poi(raw)
        assert addr == exp_addr
        assert poi == exp_poi

    client = TestClient(backend_main.app)
    r_empty = client.post("/api/geocode/resolve-link", json={})
    assert r_empty.status_code == 200
    assert r_empty.json() == {"success": False, "error": "No URL provided"}
    r_null_type = client.post("/api/geocode/resolve-link", json={"url": None, "type": None})
    assert r_null_type.status_code == 200
    assert r_null_type.json() == {"success": False, "error": "No URL provided"}


# ============================================================================
# 5. #36 — geocode_service.py _ADDR_DEGRADE_RE & ResolveAddressRequest Bound
# ============================================================================

def test_poc_36_geocode_address_degrade_redos_and_length_bound():
    """#36 Exploit + Benign: 30k digits execute < 50ms; >512 address rejected; normal street degradation preserved."""
    t0 = time.perf_counter()
    _ = geocode_service._ADDR_DEGRADE_RE.sub("", "1" * 30000 + "x")
    assert (time.perf_counter() - t0) < 0.05

    with pytest.raises(ValidationError):
        ResolveAddressRequest(address="a" * 513)
    assert len(ResolveAddressRequest(address="a" * 512).address) == 512

    client = TestClient(backend_main.app)
    assert client.post("/api/geocode/resolve-address", json={"address": "a" * 513}).status_code == 422

    # Benign control
    assert geocode_service._ADDR_DEGRADE_RE.sub("", "台北市大安區忠孝東路四段181巷7弄13號").strip() == "台北市大安區忠孝東路四段"
    assert geocode_service._ADDR_DEGRADE_RE.sub("", "台北市信義路五段7號3F, Taiwan").strip() == "台北市信義路五段, Taiwan"


# ============================================================================
# 6. #30 — poi_utils.py normalize_poi_name ReDoS Defense
# ============================================================================

def test_poc_30_poi_utils_normalize_redos_and_benign():
    """#30 Exploit + Benign: 30k spaces / open brackets finish < 50ms while normal bracket stripping is preserved."""
    from utils.poi_utils import normalize_poi_name

    for hostile in (" " * 30000 + "x", "(" * 30000 + "x", "【" * 30000 + "x", "[" * 30000 + "x"):
        t0 = time.perf_counter()
        _ = normalize_poi_name(hostile)
        assert (time.perf_counter() - t0) < 0.05

    assert normalize_poi_name("淺草寺 (Senso-ji)") == "淺草寺"
    assert normalize_poi_name("  淺草寺 (Senso-ji Temple) [Historic Landmark]  ") == "淺草寺"
    assert normalize_poi_name("A (foo) B") == "a b"
    assert normalize_poi_name("A(foo)B") == "ab"


# ============================================================================
# 7. #91 — mcp.py OAuth Redirect URI Hardening
# ============================================================================

def test_poc_91_oauth_redirect_uri_blocks_wildcards_userinfo_and_prod_testserver(monkeypatch):
    """#91 Exploit PoC: wildcard vercel/googleusercontent, userinfo @, backslash, ctrl chars, fragment, prod testserver all rejected."""
    malicious_uris = [
        "https://evil-attacker.vercel.app/steal",
        "https://travel-pwa-evil.vercel.app/steal",
        "https://script.googleusercontent.com/macros/s/evil/exec",
        "https://lh3.googleusercontent.com/evil",
        "https://attacker.com@www.tabijiapp.com/callback",
        "https://user:pass@claude.ai/api/mcp/auth_callback",
        "https://www.tabijiapp.com\\@evil.com/callback",
        "https://www.tabijiapp.com/callback\r\nX-Inject: 1",
        "https://www.tabijiapp.com/callback\x00evil",
        "https://www.tabijiapp.com/callback\x85",
        "https://www.tabijiapp.com/callback#frag",
        "https://www.tabijiapp.com/callback#",
        "http://localhost:0/callback",
        "https://claude.ai:/api/mcp/auth_callback",
        "http://www.tabijiapp.com/callback",
        "https://www.tabijiapp.com./callback",
        "https://.tabijiapp.com/callback",
        "https://..claude.ai/callback",
        "https://sub..google.com/callback",
        "https://-sub.tabijiapp.com/callback",
        "https://sub-.tabijiapp.com/callback",
    ]
    for uri in malicious_uris:
        assert mcp_router.is_trusted_redirect_uri(uri) is False, f"Malicious redirect_uri was allowed: {uri!r}"

    # Production MUST reject testserver (set synthetic 32-byte SESSION_SECRET_KEY for CI runners without .env)
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-prod-session-secret-key-32b!")
    assert mcp_router.is_trusted_redirect_uri("http://testserver/oauth/callback") is False
    assert mcp_router.is_trusted_redirect_uri("https://testserver/oauth/callback") is False

    # Endpoint enforces 400 on malicious redirect and preserves RFC 3986 %20 state + existing query params on benign redirect
    client = TestClient(backend_main.app)
    r_bad = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": "3f7abf22-b447-4281-b240-584549c79943",
            "redirect_uri": "https://evil-attacker.vercel.app/steal",
            "response_type": "code",
        },
        follow_redirects=False,
    )
    assert r_bad.status_code == 400

    r_ok = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": "3f7abf22-b447-4281-b240-584549c79943",
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback?token=a+b%2Fc",
            "response_type": "code",
            "state": "session 123",
        },
        follow_redirects=False,
    )
    assert r_ok.status_code == 302
    loc = r_ok.headers["location"]
    assert loc.startswith("https://claude.ai/api/mcp/auth_callback?token=a+b%2Fc&code=")
    assert "&state=session%20123" in loc


def test_benign_91_oauth_redirect_uri_preserves_all_legitimate_clients(monkeypatch):
    """#91 Benign Control: official Vercel prod/preview, Google OAuth redirects, AI platforms, tabiji, localhost stay allowed."""
    monkeypatch.setenv("ENV", "production")
    legitimate_uris = [
        "https://travel-pwa-five.vercel.app/oauth/callback",
        "https://travel-abc123def-tyrantpipers-projects.vercel.app/oauth/callback",
        "https://oauth-redirect.googleusercontent.com/r/user_bound_custom-mcp",
        "https://oauth-redirect-sandbox.googleusercontent.com/r/user_bound_custom-mcp",
        "https://gemini.google.com/oauth-callback",
        "https://claude.ai/api/mcp/auth_callback",
        "https://claude.com/api/mcp/auth_callback",
        "https://chatgpt.com/connector_platform_oauth_redirect",
        "https://platform.openai.com/oauth/callback",
        "https://www.perplexity.ai/rest/connections/oauth_callback",
        "https://www.tabijiapp.com/callback",
        "https://tabiji.app/oauth/callback",
        "http://localhost:3000/callback",
        "http://127.0.0.1:8000/callback",
    ]
    for uri in legitimate_uris:
        assert mcp_router.is_trusted_redirect_uri(uri) is True, f"Legitimate redirect_uri was rejected: {uri!r}"


# ============================================================================
# 8. #95 — mcp.py get_public_base_url Header Poisoning Defense
# ============================================================================

def _make_header_request(headers: dict[str, str]) -> StarletteRequest:
    raw_headers = [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()]
    return StarletteRequest({
        "type": "http",
        "method": "GET",
        "path": "/.well-known/oauth-authorization-server",
        "headers": raw_headers,
        "scheme": "https",
        "server": ("antigravity-backend-589255638719.us-central1.run.app", 443),
    })


def test_poc_95_get_public_base_url_blocks_header_poisoning(monkeypatch):
    """#95 Exploit PoC: userinfo X-Forwarded-Host, malicious X-Forwarded-Proto, unknown Host, prod testserver all neutralized."""
    monkeypatch.setenv("ENV", "production")

    poison_cases = [
        {"x-forwarded-host": "www.tabijiapp.com:443@evil.com", "x-forwarded-proto": "https"},
        {"x-forwarded-host": "www.tabijiapp.com", "x-forwarded-proto": "https://evil.com#"},
        {"host": "evil-tabijiapp.com"},
        {"host": "antigravity-backend-589255638719.us-central1.run.app"},
        {"x-forwarded-host": "www.tabijiapp.com:8443", "x-forwarded-proto": "https"},
        {"x-forwarded-host": "testserver", "x-forwarded-proto": "http"},
        {"host": "localhost:8000"},
    ]
    for hdrs in poison_cases:
        base = mcp_router.get_public_base_url(_make_header_request(hdrs))
        assert base == "https://www.tabijiapp.com", f"Header poisoning bypassed for {hdrs!r} -> {base!r}"


def test_benign_95_get_public_base_url_preserves_trusted_domains(monkeypatch):
    """#95 Benign Control: trusted proxy domains and non-prod localhost continue working."""
    monkeypatch.setenv("ENV", "production")
    assert mcp_router.get_public_base_url(
        _make_header_request({"x-forwarded-host": "www.tabijiapp.com", "x-forwarded-proto": "https"})
    ) == "https://www.tabijiapp.com"
    assert mcp_router.get_public_base_url(
        _make_header_request({"x-forwarded-host": "travel-pwa-five.vercel.app", "x-forwarded-proto": "https"})
    ) == "https://travel-pwa-five.vercel.app"

    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("NODE_ENV", raising=False)
    monkeypatch.delenv("PROD", raising=False)
    assert mcp_router.get_public_base_url(
        _make_header_request({"host": "localhost:8000"})
    ) == "http://localhost:8000"
    assert mcp_router.get_public_base_url(
        _make_header_request({"host": "localhost:00080"})
    ) == "https://www.tabijiapp.com"


# ============================================================================
# 9. #55 & /api/ai/test-key — Exception Sanitization
# ============================================================================

@pytest.mark.asyncio
async def test_poc_55_sse_errors_sanitized_while_preserving_auth_and_partial_contracts():
    """#55 Exploit + Benign: raw upstream exception strings never leak in SSE 400 or partial_preserved errors; 401 API_KEY_INVALID stays intact."""
    # Case 1: 400 bad_request must NOT leak raw exception text
    bad_req_err = genai_errors.APIError(400, {"error": {"message": "INTERNAL_UPSTREAM_SECRET_400_STACK"}})
    mock_client_400 = MagicMock()
    mock_client_400.aio.models.generate_content_stream = AsyncMock(side_effect=bad_req_err)
    with patch.object(backend_main.genai, "Client", return_value=mock_client_400), \
         patch.object(backend_main, "classify_chat_intent", AsyncMock(return_value=("CHAT", []))), \
         patch.object(backend_main, "build_effective_routing", return_value=["gemini-3.6-flash"]):
        ev_400 = [
            ev async for ev in backend_main.stream_chat_generator(
                api_key="AIzaSySanitize400TestKey1234567890123",
                history=[],
                message="hello",
                raw_user_message="hello",
                locale="en",
            )
        ]
    joined_400 = "".join(ev_400)
    assert "event: error" in joined_400
    assert '"code": 400' in joined_400
    assert "INTERNAL_UPSTREAM_SECRET_400_STACK" not in joined_400

    # Case 2: Mid-stream exception after substantial output must preserve partial_preserved & hide raw error
    long_text = "東京淺草寺雷門周邊有許多經典和菓子與抹茶老店，非常適合上午安排兩小時悠閒散步參觀。" * 5

    class _FailMidStream:
        def __init__(self):
            self._step = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._step == 0:
                self._step += 1
                chunk = MagicMock(spec=["text", "thought", "candidates"])
                chunk.text = long_text
                chunk.thought = None
                chunk.candidates = []
                return chunk
            raise RuntimeError("INTERNAL_SOCKET_SECRET_PARTIAL_999")

    mock_client_partial = MagicMock()
    mock_client_partial.aio.models.generate_content_stream = AsyncMock(return_value=_FailMidStream())
    with patch.object(backend_main.genai, "Client", return_value=mock_client_partial), \
         patch.object(backend_main, "classify_chat_intent", AsyncMock(return_value=("CHAT", []))), \
         patch.object(backend_main, "build_effective_routing", return_value=["gemini-3.6-flash"]):
        ev_partial = [
            ev async for ev in backend_main.stream_chat_generator(
                api_key="AIzaSySanitizePartialTestKey123456789",
                history=[],
                message="介紹淺草寺",
                raw_user_message="介紹淺草寺",
                locale="zh-TW",
            )
        ]
    joined_partial = "".join(ev_partial)
    assert "event: error" in joined_partial
    assert '"partial_preserved": true' in joined_partial
    assert "INTERNAL_SOCKET_SECRET_PARTIAL_999" not in joined_partial

    # Case 3 (Benign): 401 auth_fail still emits API_KEY_INVALID + code 401
    auth_err = genai_errors.APIError(401, {"error": {"message": "API_KEY_INVALID_UPSTREAM_RAW"}})
    mock_client_401 = MagicMock()
    mock_client_401.aio.models.generate_content_stream = AsyncMock(side_effect=auth_err)
    with patch.object(backend_main.genai, "Client", return_value=mock_client_401), \
         patch.object(backend_main, "classify_chat_intent", AsyncMock(return_value=("CHAT", []))), \
         patch.object(backend_main, "build_effective_routing", return_value=["gemini-3.6-flash"]):
        ev_401 = [
            ev async for ev in backend_main.stream_chat_generator(
                api_key="AIzaSySanitize401TestKey1234567890123",
                history=[],
                message="hello",
                raw_user_message="hello",
                locale="en",
            )
        ]
    joined_401 = "".join(ev_401)
    assert '"message": "API_KEY_INVALID"' in joined_401
    assert '"code": 401' in joined_401
    assert "API_KEY_INVALID_UPSTREAM_RAW" not in joined_401


def test_poc_55_api_test_key_sanitizes_429_and_400_details():
    """/api/ai/test-key must never echo raw upstream exception message in 429 or 400 HTTP responses."""
    client = TestClient(backend_main.app)
    mock_client = MagicMock()

    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=genai_errors.APIError(429, {"error": {"message": "SECRET_QUOTA_PROJECT_12345"}})
    )
    with patch("main.genai.Client", return_value=mock_client):
        r429 = client.post("/api/ai/test-key", headers={"X-Gemini-API-Key": "AIzaSyTestKeySan429_" + "1" * 20})
    assert r429.status_code == 429
    assert "SECRET_QUOTA_PROJECT_12345" not in r429.text

    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=genai_errors.APIError(400, {"error": {"message": "SECRET_BAD_REQ_TRACE_98765"}})
    )
    with patch("main.genai.Client", return_value=mock_client):
        r400 = client.post("/api/ai/test-key", headers={"X-Gemini-API-Key": "AIzaSyTestKeySan400_" + "2" * 20})
    assert r400.status_code == 400
    assert "SECRET_BAD_REQ_TRACE_98765" not in r400.text


# ============================================================================
# 10. #51, #42, #40 — .github/workflows/ci.yml Least-Privilege Permissions
# ============================================================================

def test_poc_51_42_40_ci_workflow_declares_least_privilege_permissions():
    """#51/#42/#40: .github/workflows/ci.yml must declare top-level permissions: contents: read."""
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    content = ci_path.read_text(encoding="utf-8")
    try:
        import yaml
        parsed = yaml.safe_load(content)
        assert parsed.get("permissions") == {"contents": "read"}
    except ImportError:
        assert "permissions:\n  contents: read" in content.replace("\r\n", "\n")


# ============================================================================
# 11. #136 — cloudflare/search-proxy/worker.js Single-Pass XML Entity Decoding
# ============================================================================

def test_poc_136_worker_xml_entities_single_pass_no_double_unescape():
    """#136 Exploit + Benign: execute real decodeXmlEntities from worker.js via Node to verify zero double-decoding."""
    node_bin = shutil.which("node")
    if not node_bin:
        pytest.skip("node runtime unavailable")

    worker_path = REPO_ROOT / "cloudflare" / "search-proxy" / "worker.js"
    worker_src = worker_path.read_text(encoding="utf-8")
    # Extract XML_NAMED_ENTITIES + decodeXmlEntities directly from worker.js
    m = re.search(
        r"(const XML_NAMED_ENTITIES\s*=\s*\{[\s\S]*?\};\s*function decodeXmlEntities\(str\)\s*\{[\s\S]*?\n\})",
        worker_src,
    )
    assert m is not None, "Expected single-pass XML_NAMED_ENTITIES + decodeXmlEntities in worker.js"

    js_probe = (
        m.group(1)
        + "\n"
        + """
const assert = require('assert');
// Exploit: double-encoded tags MUST NOT decode into live HTML tags
assert.strictEqual(decodeXmlEntities('&amp;lt;b&amp;gt;hi&amp;lt;/b&amp;gt;'), '&lt;b&gt;hi&lt;/b&gt;');
assert.strictEqual(decodeXmlEntities('&amp;amp;'), '&amp;');
assert.strictEqual(decodeXmlEntities('&amp;#x3c;script&amp;#x3e;'), '&#x3c;script&#x3e;');
assert.strictEqual(decodeXmlEntities('&amp;#60;'), '&#60;');
// Exploit: NUL and UTF-16 surrogates are rejected, and 10k unclosed CDATA runs in linear <10ms
assert.strictEqual(decodeXmlEntities('&#0;&#xD800;&#xDFFF;'), '');
const t0 = performance.now();
decodeXmlEntities('<![CDATA['.repeat(10000));
assert.ok(performance.now() - t0 < 50, 'Unclosed CDATA ReDoS regression');
// Benign: normal single-encoded RSS/HTML entities & multiple CDATA sections still decode accurately
assert.strictEqual(
  decodeXmlEntities('<![CDATA[Tokyo &amp; Kyoto &lt;2026&gt; &quot;Guide&quot; &#39;A&#39; &apos;B&apos; &#x4E1C;&#20140;&nbsp;1]]>'),
  'Tokyo & Kyoto <2026> "Guide" \\'A\\' \\'B\\' 东京 1'
);
assert.strictEqual(
  decodeXmlEntities('<![CDATA[A &amp;lt; B]]> + <![CDATA[C &amp; D]]>'),
  'A &lt; B + C & D'
);
console.log('WORKER_XML_SINGLE_PASS_OK');
"""
    )
    proc = subprocess.run([node_bin, "-e", js_probe], capture_output=True, text=True, check=False, timeout=10)
    assert proc.returncode == 0, f"Node verification failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
    assert "WORKER_XML_SINGLE_PASS_OK" in proc.stdout


# ============================================================================
# 12-14. #174, #172, #73-#61, #76 — Exact Hostname Matching & Dead-Code Fix
# ============================================================================

def test_poc_174_agents_wikipedia_exact_host_match():
    """#174 Exploit + Benign: non-exact or malformed wikipedia hosts must NOT be treated as Wikipedia; en.wikipedia.org still gets slug title."""
    fake_interaction = MagicMock(outputs=[], steps=[])
    clean_text = (
        "參考 [1](https://evilwikipedia.org/wiki/Evil_Trap) "
        "與 [2](https://.wikipedia.org/wiki/Tokyo_Tower) "
        "與 [3](https://en.wikipedia.org/wiki/Tokyo_Tower)"
    )
    candidates = agents_router._extract_antigravity_raw_candidates(fake_interaction, clean_text)
    by_url = {c["url"]: c["title"] for c in candidates}
    assert by_url["https://evilwikipedia.org/wiki/Evil_Trap"] == "evilwikipedia.org"
    assert by_url["https://.wikipedia.org/wiki/Tokyo_Tower"] != "Tokyo Tower - Wikipedia"
    assert by_url["https://en.wikipedia.org/wiki/Tokyo_Tower"] == "Tokyo Tower - Wikipedia"


def test_poc_172_73_to_61_destination_taxonomy_exact_host_and_google_maps_fix():
    """#172/#73-#61 Exploit + Benign: spoofed host substrings stay 'general'; real Google Maps URLs get 'review' badge."""
    raw = [
        {"title": "Spoof PTT", "url": "https://ptt.cc.attacker.com/bbs/Food/1", "snippet": "food"},
        {"title": "Spoof Yelp", "url": "https://evil-yelp.com/biz/ramen", "snippet": "ramen"},
        {"title": "Spoof TheFork", "url": "https://thefork.attacker.com/r/1", "snippet": "paris"},
        {"title": "Spoof Official", "url": "https://travel.taipei.evil.com/spot", "snippet": "taipei"},
        {"title": "Spoof Reddit", "url": "https://evil-reddit.com/r/JapanTravel", "snippet": "tokyo"},
        {"title": "Spoof TripAdvisor", "url": "https://tripadvisor.com.tw.evil.com/Attraction", "snippet": "tokyo"},
        {"title": "Malformed Dot PTT", "url": "https://.ptt.cc/bbs/Food/1", "snippet": "food"},
        {"title": "Malformed DoubleDot Official", "url": "https://..japan.travel/en/", "snippet": "japan"},
        {"title": "Non-HTTP Scheme Yelp", "url": "ftp://yelp.com/biz/ramen", "snippet": "ramen"},
        {"title": "Real Google Maps", "url": "https://www.google.com/maps/place/Tokyo+Tower", "snippet": "tower"},
        {"title": "Real Google Maps JP", "url": "https://www.google.co.jp/maps/place/Tokyo+Tower", "snippet": "tower"},
        {"title": "Real Google Maps TW", "url": "https://maps.google.com.tw/?q=Taipei+101", "snippet": "taipei"},
        {"title": "Real TripAdvisor TW", "url": "https://www.tripadvisor.com.tw/Attraction_Review-Tokyo.html", "snippet": "tokyo"},
        {"title": "Real Yelp TW", "url": "https://www.yelp.com.tw/biz/ramen", "snippet": "ramen"},
        {"title": "Real PTT", "url": "https://www.ptt.cc/bbs/Japan_Travel/M.1.html", "snippet": "tokyo"},
        {"title": "Real TheFork", "url": "https://www.thefork.fr/restaurant/le-bistro", "snippet": "paris"},
        {"title": "Real Official", "url": "https://www.japan.travel/en/spot/tokyo/", "snippet": "japan"},
    ]
    out = destination_taxonomy.classify_and_filter_results(raw, "東京美食景點", dest_code="JP")
    by_title = {item["title"]: item for item in out}

    # Exploits MUST NOT receive trusted badges
    for spoof in (
        "Spoof PTT",
        "Spoof Yelp",
        "Spoof TheFork",
        "Spoof Official",
        "Spoof Reddit",
        "Spoof TripAdvisor",
        "Malformed Dot PTT",
        "Malformed DoubleDot Official",
        "Non-HTTP Scheme Yelp",
    ):
        assert by_title[spoof]["category"] == "general", f"{spoof} misclassified as {by_title[spoof]['category']}"

    # Benign controls (including previously dead-code Google Maps branch & regional ccTLDs!)
    for gm_title in ("Real Google Maps", "Real Google Maps JP", "Real Google Maps TW"):
        assert by_title[gm_title]["category"] == "review"
        assert "景點美食評分" in by_title[gm_title]["badge"]["text"]
    assert by_title["Real TripAdvisor TW"]["category"] == "global_forum"
    assert by_title["Real Yelp TW"]["category"] == "review"
    assert "Yelp" in by_title["Real Yelp TW"]["badge"]["text"]
    assert by_title["Real PTT"]["category"] == "local_forum"
    assert "PTT" in by_title["Real PTT"]["badge"]["text"]
    assert by_title["Real TheFork"]["category"] == "local_forum"
    assert "TheFork" in by_title["Real TheFork"]["badge"]["text"]
    assert by_title["Real Official"]["category"] == "official"


def test_poc_76_unwrap_ddg_redirect_exact_host_match():
    """#76 Exploit + Benign: non-exact/malformed hosts & non-HTTP schemes must NOT unwrap; real DDG HTTP(S) redirects still unwrap."""
    for blocked in (
        "https://duckduckgo.com.attacker.com/l/?uddg=https%3A%2F%2Fexample.com%2Ftarget",
        "https://.duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ftarget",
        "ftp://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ftarget",
        "https://duckduckgo.com/l/?uddg=data%3Atext%2Fplain%2Chi",
    ):
        assert web_search_engine.unwrap_ddg_redirect(blocked) == blocked

    assert web_search_engine.unwrap_ddg_redirect(
        "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ftokyo&rut=1"
    ) == "https://example.com/tokyo"
    assert web_search_engine.unwrap_ddg_redirect(
        "https://html.duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fkyoto"
    ) == "https://example.com/kyoto"


# ============================================================================
# 15. Adjacent Hardening: Pure-IP Public Rate Limits & url_safety Fast-Path
# ============================================================================

def test_poc_adjacent_public_proxy_ip_only_rate_limits_block_fake_key_bypass():
    """Rotating fake X-Gemini-API-Key must NOT bypass IP-only rate limits on all 6 public proxy routes."""
    client = TestClient(backend_main.app)

    # 1. POST /api/poi/ai-enrich (60/min pure IP)
    limiter._storage.reset()
    poi_router.__resetPoiEnrichCacheForTesting()
    with patch("routers.poi.enrich_poi_complete", AsyncMock(return_value={"status": "SUCCESS", "cultural_desc": "ok"})):
        ai_enrich_codes = [
            client.post(
                "/api/poi/ai-enrich",
                json={"name": "Tokyo Tower", "type": "attraction", "lat": 35.6586, "lng": 139.7454},
                headers={"X-Gemini-API-Key": f"fake-ai-enrich-{i}", "X-Forwarded-For": "203.0.113.51"},
            ).status_code
            for i in range(61)
        ]
        # Benign control: distinct real IP is unaffected
        other_ip = client.post(
            "/api/poi/ai-enrich",
            json={"name": "Tokyo Tower", "type": "attraction", "lat": 35.6586, "lng": 139.7454},
            headers={"X-Forwarded-For": "203.0.113.52"},
        )
    assert ai_enrich_codes[:60] == [200] * 60
    assert ai_enrich_codes[60] == 429
    assert other_ip.status_code == 200

    # 2. POST /api/geocode/search (60/min pure IP)
    limiter._storage.reset()
    with patch("routers.geocode.smart_geocode_logic", AsyncMock(return_value=[])):
        search_codes = [
            client.post(
                "/api/geocode/search",
                json={"query": "Tokyo"},
                headers={"X-Gemini-API-Key": f"fake-search-{i}", "X-Forwarded-For": "203.0.113.53"},
            ).status_code
            for i in range(61)
        ]
    assert search_codes[:60] == [200] * 60
    assert search_codes[60] == 429

    # 3. POST /api/geocode/resolve-link (60/min pure IP)
    limiter._storage.reset()
    geo_link_codes = [
        client.post(
            "/api/geocode/resolve-link",
            json={},
            headers={"X-Gemini-API-Key": f"fake-glink-{i}", "X-Forwarded-For": "203.0.113.54"},
        ).status_code
        for i in range(61)
    ]
    assert geo_link_codes[:60] == [200] * 60
    assert geo_link_codes[60] == 429

    # 4. POST /api/geocode/resolve-address (60/min pure IP)
    limiter._storage.reset()
    with patch("routers.geocode.resolve_address_pipeline", AsyncMock(return_value={"lat": 35.65, "lng": 139.74})):
        addr_codes = [
            client.post(
                "/api/geocode/resolve-address",
                json={"address": "Tokyo Tower"},
                headers={"X-Gemini-API-Key": f"fake-addr-{i}", "X-Forwarded-For": "203.0.113.55"},
            ).status_code
            for i in range(61)
        ]
    assert addr_codes[:60] == [200] * 60
    assert addr_codes[60] == 429

    # 5. POST /api/poi/resolve-link (30/min pure IP)
    limiter._storage.reset()
    poi_link_codes = [
        client.post(
            "/api/poi/resolve-link",
            json={"url": "http://127.0.0.1/blocked"},
            headers={"X-Gemini-API-Key": f"fake-plink-{i}", "X-Forwarded-For": "203.0.113.56"},
        ).status_code
        for i in range(31)
    ]
    assert poi_link_codes[:30] == [400] * 30
    assert poi_link_codes[30] == 429

    # 6. GET /api/poi/media-proxy (30/min pure IP)
    limiter._storage.reset()
    media_codes = [
        client.get(
            "/api/poi/media-proxy",
            params={"url": "https://evil.example/a.png"},
            headers={"X-Gemini-API-Key": f"fake-media-{i}", "X-Forwarded-For": "203.0.113.57"},
        ).status_code
        for i in range(31)
    ]
    assert media_codes[:30] == [400] * 30
    assert media_codes[30] == 429

    # 7. POST /api/geocode/reverse (60/min pure IP)
    limiter._storage.reset()
    with patch("routers.geocode.reverse_geocode_with_photon", AsyncMock(return_value={"name": "Tokyo", "address": "Minato"})):
        rev_codes = [
            client.post(
                "/api/geocode/reverse",
                json={"lat": 35.6586, "lng": 139.7454},
                headers={"X-Gemini-API-Key": f"fake-rev-{i}", "X-Forwarded-For": "203.0.113.58"},
            ).status_code
            for i in range(61)
        ]
    assert rev_codes[:60] == [200] * 60
    assert rev_codes[60] == 429


def test_benign_adjacent_chat_stream_keeps_per_api_key_family_isolation():
    """/api/chat/stream must remain keyed by X-Gemini-API-Key so family members on shared Wi-Fi stay isolated."""
    req_mom = StarletteRequest({
        "type": "http",
        "headers": [
            (b"x-forwarded-for", b"203.0.113.99"),
            (b"x-gemini-api-key", b"AIzaSyFamilyMemberMomKey123456789012345"),
        ],
    })
    req_dad = StarletteRequest({
        "type": "http",
        "headers": [
            (b"x-forwarded-for", b"203.0.113.99"),
            (b"x-gemini-api-key", b"AIzaSyFamilyMemberDadKey123456789012345"),
        ],
    })
    k_mom = get_rate_limit_key(req_mom)
    k_dad = get_rate_limit_key(req_dad)
    assert k_mom.startswith("key:") and k_dad.startswith("key:")
    assert k_mom != k_dad


def test_poc_adjacent_url_safety_fast_path_rejects_userinfo_backslash_ctrl_preserves_maps_at_path():
    """url_safety fast-path rejects @ userinfo, backslash, and control chars while allowing @ in Google Maps paths."""
    # Exploits blocked in pure-CPU fast path (even for SAFE_WIKI_DOMAINS!)
    assert url_safety.is_safe_url("https://127.0.0.1@en.wikipedia.org/wiki/Tokyo") is False
    assert url_safety.is_safe_url("https://user:pass@upload.wikimedia.org/a.png") is False
    assert url_safety.is_safe_url("https://en.wikipedia.org\\@127.0.0.1/wiki/Tokyo") is False
    assert url_safety.is_safe_url("https://en.wikipedia.org/wiki/Tokyo\r\nX-Test: 1") is False
    assert url_safety.is_safe_url("https://en.wikipedia.org/wiki/Tokyo\n") is False
    assert url_safety.is_safe_url("https://en.wikipedia.org/wiki/Tokyo\t") is False
    assert url_safety.is_safe_url("https://en.wikipedia.org/wiki/Tokyo\x85") is False
    assert url_safety.is_safe_url("https://en.wikipedia.org:0/wiki/Tokyo") is False
    assert url_safety.is_safe_url("https://127.0.0.1 .wikipedia.org/wiki/Tokyo") is False
    assert url_safety.is_safe_url("https://.wikipedia.org/wiki/Tokyo") is False
    assert url_safety.is_safe_url("https://..wikipedia.org/wiki/Tokyo") is False
    assert url_safety.is_safe_url("https://-sub.wikipedia.org/wiki/Tokyo") is False
    assert url_safety.is_safe_url("https://sub\xa0.wikipedia.org/wiki/Tokyo") is False
    assert url_safety.is_safe_url("https://en.wikipedia.org:/wiki/Tokyo") is False
    assert url_safety.is_safe_url("https://en.wikipedia.org:000443/wiki/Tokyo") is False

    # Benign controls
    assert url_safety.is_safe_url("  https://en.wikipedia.org/wiki/Tokyo  ") is True
    assert url_safety.is_safe_url("https://en.wikipedia.org/wiki/Tokyo") is True
    assert url_safety.is_safe_url("https://en.wikipedia.org:443/wiki/Tokyo") is True
    with patch("utils.url_safety.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("142.250.190.46", 0))]):
        assert url_safety.is_safe_url("https://www.google.com/maps/place/Tokyo+Tower/@35.6585805,139.7454329,17z") is True
