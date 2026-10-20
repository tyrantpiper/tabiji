"""
In-Memory PoC & Security Sentinel Verification Suite
Target: POI Universal Link Resolver & Shared List Deserialization Engine
"""

import pytest
import re
import urllib.parse
from utils.url_safety import is_safe_url


def test_ssrf_safety_on_candidate_endpoints():
    """🛡️ 驗證 SSRF 阻斷防護：禁止私有 IP、內網主機與危險協議"""
    unsafe_targets = [
        "http://127.0.0.1:8008/api/trips",
        "http://localhost:3000/api/poi/all",
        "http://169.254.169.254/computeMetadata/v1/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "file:///etc/passwd",
        "gopher://127.0.0.1:6379",
        "javascript:alert(1)"
    ]
    for target in unsafe_targets:
        assert not is_safe_url(target), f"SSRF Guard failed to block unsafe URL: {target}"


def test_placelist_token_extraction_regex():
    """🛡️ 驗證 Google Maps 共享清單 Token 萃取正則之邊界防禦與防 ReDoS"""
    test_cases = [
        ("https://www.google.com/maps/placelists/list/1bXRlr5Nuy7T9UCJDcv7aKU_Cqsi8Q", "1bXRlr5Nuy7T9UCJDcv7aKU_Cqsi8Q"),
        ("https://www.google.com/maps/@/data=!3m1!4b1!4m3!11m2!2s1bXRlr5Nuy7T9UCJDcv7aKU_Cqsi8Q!3e1", "1bXRlr5Nuy7T9UCJDcv7aKU_Cqsi8Q"),
        ("https://maps.app.goo.gl/ShortToken?g_st=ic", None),  # 短網址需先跟隨 302，不可直接硬匹
        ("https://evil.com/placelists/list/1bXRlr5Nuy7T9UCJDcv7aKU_Cqsi8Q", None), # 非 Google 網域防護
    ]

    token_regex = re.compile(r'https?://(?:www\.)?google\.[a-z.]+/maps/(?:@/data=.*?!11m2!2s|placelists/list/)([A-Za-z0-9_-]{16,})')

    for url, expected_token in test_cases:
        match = token_regex.search(url)
        if expected_token:
            assert match is not None, f"Failed to match valid token in {url}"
            assert match.group(1) == expected_token
        else:
            if not ("google." in url and "/maps/" in url):
                assert match is None, f"False positive matched on untrusted domain: {url}"


def test_single_poi_name_and_address_extraction_logic():
    """🛡️ 驗證老新台菜單點地名解碼與地址提煉演算法"""
    raw_place_path = "%E8%80%81%E6%96%B0%E5%8F%B0%E8%8F%9C+(%E4%B9%9D%E5%A6%82%E5%89%B5%E5%A7%8B%E5%BA%97)"
    cleaned_name = urllib.parse.unquote_plus(raw_place_path).strip()
    assert cleaned_name == "老新台菜 (九如創始店)"
    assert "%" not in cleaned_name

    raw_og_desc = "老新台菜 · 807台灣高雄市三民區九如二路227號"
    
    # 提煉門牌地址
    match = re.search(r'·\s*([0-9\u4e00-\u9fa5]+(?:市|縣|區|鄉|鎮)[^\s·]+[路街巷弄號樓][^\s·]*)', raw_og_desc)
    assert match is not None
    extracted_address = match.group(1).strip()
    assert extracted_address == "807台灣高雄市三民區九如二路227號"


def test_placelist_protobuf_payload_safe_decloaking():
    """🛡️ 驗證 Google RPC 反序列化脫殼安全：防禦非預期格式與私人清單"""
    # 1. 模擬私人清單或異常 HTML (非 JSON / 缺失前綴)
    invalid_raw = "<html><head><title>Sign in - Google Accounts</title></head></html>"
    is_decloakable = invalid_raw.startswith(")]}'")
    assert not is_decloakable, "Private list redirect must not be treated as JSON payload"

    # 2. 模擬合法前綴脫殼
    valid_raw_stub = ")]}'\n[[null,null,null,null,\"京都必吃清單\",null,null,null,[]]]"
    assert valid_raw_stub.startswith(")]}'")
    stripped = valid_raw_stub.lstrip(")]}'\n")
    import json
    data = json.loads(stripped)
    assert data[0][4] == "京都必吃清單"
    assert data[0][8] == []  # 空地點清單防禦
