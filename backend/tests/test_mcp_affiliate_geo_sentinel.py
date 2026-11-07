# -*- coding: utf-8 -*-
"""
🛡️ Security Sentinel In-Memory PoC & Mantis Block G Benign Control Suite
Topic: MCP Real Affiliate Attribution (tp.media) & Global 4-Tier Dynamic Spatial Anchoring
Date: 2026-11-07
"""

import urllib.parse
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

import services.geocode_service as geocode_service
from main import app
from services.geocode_service import (
    extract_region_for_search,
    normalize_for_fuzzy,
    smart_geocode_logic,
    translate_famous_landmark,
)

client = TestClient(app)

ALICE_UUID = "11111111-2222-3333-4444-555555555555"
TAIPEI_TRIP_ID = "b260f84f-cdea-4a00-a5f1-91564d31d966"


# ==============================================================================
# Phase 3: Red Team PoC Tests (Must FAIL before patch, PASS after patch)
# ==============================================================================

def test_sentinel_poc_mcp_affiliate_broken_domain_and_placeholder():
    """
    [PoC 1] 證明舊版 MCP 導出無效網域 tabiji.app 且 /go/klook 使用假佔位符 TABIJI_AFF_888，
    修復後必須導出真實 Travelpayouts tp.media (marker=602410, p=4110) 分潤連結。
    """
    with patch("routers.mcp.get_verified_user", return_value=ALICE_UUID):
        resp = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer valid_alice_token"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "recommend_tickets",
                    "arguments": {
                        "place_name": "大稻埕迪化街",
                        "destination": "台北",
                    },
                },
            },
        )
        assert resp.status_code == 200
        text = resp.json()["result"]["content"][0]["text"]
        assert "tabiji.app/go/" not in text
        assert "TABIJI_AFF_888" not in text
        assert "https://tp.media/r?" in text
        assert "marker=602410" in text
        assert "p=4110" in text

    # 2. 驗證 /go/klook 端點亦導向真實 tp.media (marker=602410)
    resp_go = client.get(f"/go/klook/{TAIPEI_TRIP_ID}?item=大稻埕迪化街", follow_redirects=False)
    assert resp_go.status_code == 302
    loc = resp_go.headers["location"]
    assert "TABIJI_AFF_888" not in loc
    assert loc.startswith("https://tp.media/r?")
    assert "marker=602410" in loc
    assert "p=4110" in loc

    # 3. 驗證 MCP initialize 自動注入 instructions (強制指導外部 AI 遵守地理消歧義 SOP，無須人類手動下指令)
    resp_init = client.post(
        "/api/mcp",
        json={"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}},
    )
    assert resp_init.status_code == 200
    init_res = resp_init.json()["result"]
    assert "instructions" in init_res and len(init_res["instructions"]) > 50
    assert "同名景點" in init_res["instructions"] or "城市" in init_res["instructions"]

    # 4. 驗證 tools/list 之 manage_itinerary_node 參數 Schema 包含明確地理消歧義規範
    resp_tools = client.post("/api/mcp", json={"jsonrpc": "2.0", "id": 0, "method": "tools/list", "params": {}})
    tools = resp_tools.json()["result"]["tools"]
    manage_tool = next(t for t in tools if t["name"] == "manage_itinerary_node")
    pn_desc = manage_tool["inputSchema"]["properties"]["places"]["items"]["properties"]["place_name"]["description"]
    assert "城市" in pn_desc or "區域" in pn_desc


@pytest.mark.asyncio
async def test_sentinel_poc_taipei_longshan_temple_hijacked_to_seoul_yongsan():
    """
    [PoC 2] 證明舊版 normalize_for_fuzzy 將『龍山寺』與首爾『龍山站』抹除為相同詞根『竜山』，
    導致台北行程 (3 Day Taipei Explorer ✨) 新增『龍山寺』時誤配至韓國首爾龍山站 (37.5299, 126.9645)。
    修復後必須精準定位於台北萬華龍山寺 (約 25.037, 121.500)。
    """
    # 1. 驗證『龍山寺』與『龍山站』正規化後絕不可碰撞為同一字串
    assert normalize_for_fuzzy("龍山寺") != normalize_for_fuzzy("龍山站")

    # 2. 驗證在台北行程錨點下搜尋『龍山寺』，回傳台北萬華座標而非首爾 (37.5299, 126.9645)
    res = await smart_geocode_logic(
        query="龍山寺",
        limit=1,
        trip_title="3 Day Taipei Explorer ✨",
        lat=25.0460,
        lng=121.5053,
        country="TW",
        region="Taipei",
    )
    assert res and res.get("results")
    top = res["results"][0]
    assert 24.9 <= top["lat"] <= 25.2, f"Expected Taipei lat, got {top['lat']}"
    assert 121.4 <= top["lng"] <= 121.7, f"Expected Taipei lng, got {top['lng']}"


def test_sentinel_poc_extract_region_english_title_number_pollution():
    """
    [PoC 3] 證明舊版 extract_region_for_search 遇到英文或帶年份之標題時：
    - '3 Day Taipei Explorer ✨' 會回傳數字 '3'
    - '2026 東京自由行' 會回傳年份 '2026'
    - 'Alice 東京行程' 會回傳人名 'Alice'
    修復後必須提取出純淨的目的地名稱（且當國名與城市並存時優先提取城市，無空白年份亦正常剝離）。
    """
    assert extract_region_for_search("3 Day Taipei Explorer ✨").lower() == "taipei"
    assert extract_region_for_search("2026 東京自由行") == "東京"
    assert extract_region_for_search("Alice 東京行程") == "東京"
    assert extract_region_for_search("7 Days in Cusco") == "Cusco"
    assert extract_region_for_search("台灣台中一日遊") == "台中"
    assert extract_region_for_search("South Korea Seoul 4 Days").lower() == "seoul"
    assert extract_region_for_search("Peru Cusco 7 Days") == "Cusco"
    assert extract_region_for_search("2026庫斯科自由行") == "庫斯科"


@pytest.mark.asyncio
async def test_sentinel_poc_limit_one_premature_break_skips_nominatim_and_rerank():
    """
    [PoC 4] 證明舊版 smart_geocode_logic 在 limit=1 時，只要 Photon 投機搜尋回傳 1 筆遠端同名結果，
    effective_limit=1 就會立刻 break 跳過 Nominatim，使 rerank_top_k 無法選出錨點附近的正確結果。
    測試場景：全球任一非字典城市（秘魯庫斯科 Cusco: -13.5167, -71.9788），搜尋『Plaza Mayor』，
    Photon 假設只回傳西班牙馬德里 Plaza Mayor (40.4155, -3.7074)，而 Nominatim 回傳庫斯科本地結果 (-13.5168, -71.9785)。
    修復後必須完整執行 Nominatim 並由距離衰減選出庫斯科本地結果！
    """
    photon_madrid_decoy = [
        {"lat": 40.4155, "lng": -3.7074, "name": "Plaza Mayor", "address": "Madrid, Spain", "type": "square"}
    ]
    nominatim_cusco_local = [
        {"lat": "-13.5168", "lon": "-71.9785", "name": "Plaza Mayor de Cusco", "display_name": "Plaza Mayor, Cusco, Peru", "type": "square", "importance": 0.75}
    ]

    mock_nom_resp = MagicMock()
    mock_nom_resp.json.return_value = nominatim_cusco_local

    with (
        patch("services.geocode_service.geocode_with_photon", new=AsyncMock(return_value=photon_madrid_decoy)),
        patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_nom_resp)),
    ):
        res = await smart_geocode_logic(
            query="Plaza Mayor",
            limit=1,
            trip_title="7 Days in Cusco",
            lat=-13.5167,
            lng=-71.9788,
            region="Cusco",
        )
        assert res and res.get("results")
        winner = res["results"][0]
        assert abs(winner["lat"] - (-13.5168)) < 0.05, f"Expected Cusco (-13.5168), but got Madrid decoy {winner}"


def test_sentinel_poc_external_ai_hallucinated_cross_country_coords():
    """
    [PoC 5] 證明當外部 AI 呼叫 manage_itinerary_node (action='add' 或 action='update')
    傳入無座標或傳入錯誤跨國座標 (如首爾 37.5299, 126.9645) 至台北行程時，
    後端必須透過 4 層動態空間錨點 (由同日既有景點 大稻埕 25.0551, 121.5083 與 剝皮寮 25.0368, 121.5022 鎖定台北萬華)
    自動攔截並糾偏為台北萬華龍山寺座標！
    """
    mock_supabase = MagicMock()
    mock_trip_data = MagicMock(data=[
        {
            "id": TAIPEI_TRIP_ID,
            "title": "3 Day Taipei Explorer ✨",
            "created_by": ALICE_UUID,
            "content": {"daily_locations": {}},
        }
    ])
    existing_day1_items = [
        {"day_number": 1, "place_name": "大稻埕迪化街", "location_lat": 25.0551, "location_lng": 121.5083, "sort_order": 10},
        {"day_number": 1, "place_name": "剝皮寮歷史街區", "location_lat": 25.0368, "location_lng": 121.5022, "sort_order": 20},
    ]
    inserted_records = []
    updated_payloads = []

    def mock_table_exec(table_name):
        t = MagicMock()
        t.select.return_value = t
        t.eq.return_value = t
        t.order.return_value = t
        t.limit.return_value = t
        if table_name == "itineraries":
            t.execute.return_value = mock_trip_data
        elif table_name == "itinerary_items":
            t.execute.return_value = MagicMock(data=existing_day1_items)
            t.insert.side_effect = lambda rec: MagicMock(
                execute=lambda: (inserted_records.extend(rec) if isinstance(rec, list) else inserted_records.append(rec))
                or MagicMock(data=rec if isinstance(rec, list) else [rec])
            )

            def mock_update(up_rec):
                updated_payloads.append(up_rec)
                up_chain = MagicMock()
                up_chain.eq.return_value = up_chain
                up_chain.execute.return_value = MagicMock(data=[{"id": "134f98cc-4861-4e20-a7d8-5126be224740", "place_name": "龍山寺", **up_rec}])
                return up_chain

            t.update.side_effect = mock_update
        return t

    mock_supabase.table.side_effect = mock_table_exec

    with (
        patch("routers.mcp.get_verified_user", return_value=ALICE_UUID),
        patch("routers.mcp.get_supabase", return_value=mock_supabase),
    ):
        resp = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer valid_alice_token"},
            json={
                "jsonrpc": "2.0",
                "id": 99,
                "method": "tools/call",
                "params": {
                    "name": "manage_itinerary_node",
                    "arguments": {
                        "trip_id": TAIPEI_TRIP_ID,
                        "day_index": 1,
                        "action": "add",
                        "places": [
                            {
                                "place_name": "龍山寺",
                                "lat": 37.5299,  # 模擬外部 AI 誤傳首爾座標
                                "lng": 126.9645,
                                "arrival_time": "17:00",
                            }
                        ],
                    },
                },
            },
        )
        assert resp.status_code == 200
        assert len(inserted_records) == 1
        rec = inserted_records[0]
        assert rec["place_name"] == "龍山寺"
        assert 24.9 <= rec["location_lat"] <= 25.2, f"Expected Taipei lat, got {rec['location_lat']}"
        assert 121.4 <= rec["location_lng"] <= 121.7, f"Expected Taipei lng, got {rec['location_lng']}"

        # 2. 驗證 action="update" 時，若外部 AI 誤傳首爾跨國座標 (37.5299, 126.9645)，同樣攔截並糾偏為台北萬華龍山寺座標
        resp_up = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer valid_alice_token"},
            json={
                "jsonrpc": "2.0",
                "id": 100,
                "method": "tools/call",
                "params": {
                    "name": "manage_itinerary_node",
                    "arguments": {
                        "trip_id": TAIPEI_TRIP_ID,
                        "day_index": 1,
                        "action": "update",
                        "places": [
                            {
                                "place_name": "龍山寺",
                                "lat": 37.5299,
                                "lng": 126.9645,
                                "notes": "參拜月老",
                            }
                        ],
                    },
                },
            },
        )
        assert resp_up.status_code == 200
        assert len(updated_payloads) == 1
        up_rec = updated_payloads[0]
        assert 24.9 <= up_rec["location_lat"] <= 25.2, f"Expected Taipei lat on update, got {up_rec['location_lat']}"
        assert 121.4 <= up_rec["location_lng"] <= 121.7, f"Expected Taipei lng on update, got {up_rec['location_lng']}"


# ==============================================================================
# Phase 4: Mantis Block G Benign Control Tests (Must PASS)
# ==============================================================================

@pytest.mark.asyncio
async def test_benign_seoul_trip_yongsan_station_still_resolves_to_seoul():
    """
    [Block G Benign Control 1] 在韓國首爾行程中搜尋『龍山站』或『龍山電子商街』，必須正常回傳首爾龍山區座標。
    """
    res = await smart_geocode_logic(
        query="龍山站",
        limit=1,
        trip_title="首爾 4 日自由行",
        lat=37.5665,
        lng=126.9780,
        country="KR",
        region="首爾",
    )
    assert res and res.get("results")
    top = res["results"][0]
    assert abs(top["lat"] - 37.5299) < 0.05
    assert abs(top["lng"] - 126.9645) < 0.05


@pytest.mark.asyncio
async def test_benign_multi_city_day_anchor_priority():
    """
    [Block G Benign Control 2] 驗證跨國雙城行程（標題為『東京・首爾雙城遊』，但第 5 天 daily_locations 設定為首爾）
    resolve_trip_spatial_anchor 必須優先錨定第 5 天的首爾座標，而非被標題的『東京』誤導。
    """
    trip = {
        "title": "東京・首爾雙城遊",
        "content": {
            "daily_locations": {
                "1": {"name": "東京", "lat": 35.6895, "lng": 139.6917},
                "5": {"name": "首爾", "lat": 37.5665, "lng": 126.9780},
            }
        },
    }
    resolve_fn = getattr(geocode_service, "resolve_trip_spatial_anchor", None)
    assert resolve_fn is not None, "resolve_trip_spatial_anchor missing"
    anchor_day5 = await resolve_fn(trip, day_number=5, existing_items=[])
    assert abs(anchor_day5["lat"] - 37.5665) < 0.01
    assert abs(anchor_day5["lng"] - 126.9780) < 0.01
    assert anchor_day5["country"] == "KR"


@pytest.mark.asyncio
async def test_benign_lukang_longshan_temple_not_hijacked_to_taipei():
    """
    [Block G Benign Control 3] 在彰化鹿港行程中搜尋『鹿港龍山寺』，必須回傳彰化鹿港龍山寺 (24.0499, 120.4357)，
    絕不可因同處台灣境內 (距離 153km < 300km) 被誤判秒回台北萬華艋舺龍山寺 (25.0372, 121.4999)。
    """
    res = await smart_geocode_logic(
        query="鹿港龍山寺",
        limit=1,
        trip_title="彰化鹿港一日遊",
        lat=24.0560,
        lng=120.4350,
        country="TW",
    )
    assert res and res.get("results")
    top = res["results"][0]
    assert abs(top["lat"] - 24.0499) < 0.05, f"Expected Lukang lat (~24.05), got {top['lat']}"
    assert abs(top["lng"] - 120.4357) < 0.05, f"Expected Lukang lng (~120.44), got {top['lng']}"


def test_benign_affiliate_gateway_open_redirect_defense_preserved():
    """
    [Block G Benign Control 4] 確保 /go/{partner} 的 Open Redirect 防禦 100% 完整保留。
    """
    assert client.get("/go/klook/https://evil-phishing.com", follow_redirects=False).status_code == 400
    assert client.get("/go/klook///evil.com", follow_redirects=False).status_code == 400
    assert client.get("/go/unknown_partner/test", follow_redirects=False).status_code == 400
    assert client.get("/go/klook/\\evil.com", follow_redirects=False).status_code == 400
    assert client.get("/go/klook/tokyo?url=https://evil.com", follow_redirects=False).status_code == 400
