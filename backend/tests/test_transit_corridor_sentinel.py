"""
Security Sentinel Red/Green PoC & Mantis Block G Test Suite
Target: Transit Corridor & Cross-Island Spatial Defense (VULN-CORRIDOR-001 ~ 004)
"""
import os
import sys
from unittest.mock import AsyncMock, patch
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.geocode_service import (
    build_spatial_constraint_prompt,
    resolve_prompt_spatial_anchor,
    resolve_trip_spatial_anchor,
    verify_and_heal_itinerary_coords,
)


# ==============================================================================
# 🔴 Phase 3 Red Gate: Adversarial PoC Tests (Must FAIL on unpatched baseline)
# ==============================================================================


@pytest.mark.asyncio
async def test_sentinel_poc_corridor_1_shinkansen_and_island_flight_preservation():
    """
    VULN-CORRIDOR-001:
    1) 東京 -> 京都 500km 新幹線轉場日：當行程標題為『日本自由行』且外部 OSM 超時時，
       上午東京景點與下午京都景點均不得被單一中位數誤判為 >180km 離群點而覆寫，
       且 daily_locations['1'] 必須標記為 type='transit_corridor' 並產生 '東京 → 京都'。
    2) 台北 -> 澎湖 260km 國內線跨海日：含撞名地標『澎湖天后宮』不得被台北錨點以 >50km 撞名誤殺。
    """
    async def mock_timeout_geocode(*args, **kwargs):
        return {"results": []}

    with patch("services.geocode_service.smart_geocode_logic", side_effect=mock_timeout_geocode):
        # Case A: 東京 -> 京都 500km 新幹線轉場日
        items_jp = [
            {
                "day_number": 1,
                "place_name": "淺草寺雷門",
                "category": "sightseeing",
                "lat": 35.7148,
                "lng": 139.7967,
            },
            {
                "day_number": 1,
                "place_name": "東京鐵塔",
                "category": "sightseeing",
                "lat": 35.6586,
                "lng": 139.7454,
            },
            {
                "day_number": 1,
                "place_name": "搭乘東海道新幹線前往京都",
                "category": "transit",
                "lat": 35.6812,
                "lng": 139.7671,
            },
            {
                "day_number": 1,
                "place_name": "伏見稻荷大社",
                "category": "sightseeing",
                "lat": 34.9671,
                "lng": 135.7727,
            },
            {
                "day_number": 1,
                "place_name": "清水寺",
                "category": "sightseeing",
                "lat": 34.9949,
                "lng": 135.7850,
            },
        ]
        healed_jp, dl_jp = await verify_and_heal_itinerary_coords(
            items_jp,
            trip_meta={"title": "2026 日本自由行"},
        )

        # 東京與京都景點必須 100% 保留原座標，絕不能被覆寫到同一城市
        assert abs(healed_jp[0]["lat"] - 35.7148) < 0.01
        assert abs(healed_jp[3]["lat"] - 34.9671) < 0.01
        assert abs(healed_jp[3]["lng"] - 135.7727) < 0.01
        assert abs(healed_jp[4]["lat"] - 34.9949) < 0.01
        assert dl_jp["1"].get("type") == "transit_corridor"
        assert "東京" in dl_jp["1"]["name"] and "京都" in dl_jp["1"]["name"]
        assert "→" in dl_jp["1"]["name"]
        assert len(dl_jp["1"].get("segments") or []) == 2

        # Case B: 台北 -> 澎湖 260km 跨海離島航班日 (含撞名地標『澎湖天后宮』)
        items_tw = [
            {
                "day_number": 1,
                "place_name": "台北 101",
                "category": "sightseeing",
                "lat": 25.0339,
                "lng": 121.5645,
            },
            {
                "day_number": 1,
                "place_name": "松山機場飛往澎湖馬公",
                "category": "transit",
                "lat": 25.0630,
                "lng": 121.5517,
            },
            {
                "day_number": 1,
                "place_name": "澎湖天后宮",
                "category": "sightseeing",
                "lat": 23.5647,
                "lng": 119.5643,
            },
            {
                "day_number": 1,
                "place_name": "澎湖跨海大橋",
                "category": "sightseeing",
                "lat": 23.6583,
                "lng": 119.5481,
            },
        ]
        healed_tw, dl_tw = await verify_and_heal_itinerary_coords(
            items_tw,
            trip_meta={"title": "2026 台灣海島遊"},
        )
        # 澎湖天后宮位於澎湖子群 (<50km)，不得被台北錨點當作撞名漂移誤殺回台北！
        assert abs(healed_tw[2]["lat"] - 23.5647) < 0.01
        assert abs(healed_tw[2]["lng"] - 119.5643) < 0.01
        assert abs(healed_tw[3]["lat"] - 23.6583) < 0.01
        assert dl_tw["1"].get("type") == "transit_corridor"
        assert "台北" in dl_tw["1"]["name"] and ("澎湖" in dl_tw["1"]["name"] or "馬公" in dl_tw["1"]["name"])

        # Case C: 包含抵達端交通節點 (抵達京都車站) 之新幹線轉場日
        items_arr = [
            {"day_number": 1, "place_name": "淺草寺雷門", "category": "sightseeing", "lat": 35.7148, "lng": 139.7967},
            {"day_number": 1, "place_name": "搭乘東海道新幹線", "category": "transit", "lat": 35.6812, "lng": 139.7671},
            {"day_number": 1, "place_name": "抵達京都車站", "category": "transit", "lat": 34.9858, "lng": 135.7588},
            {"day_number": 1, "place_name": "清水寺", "category": "sightseeing", "lat": 34.9949, "lng": 135.7850},
        ]
        healed_arr, dl_arr = await verify_and_heal_itinerary_coords(
            items_arr,
            trip_meta={"title": "日本自由行"},
        )
        assert abs(healed_arr[2]["lat"] - 34.9858) < 0.01
        assert dl_arr["1"].get("type") == "transit_corridor"
        assert len(dl_arr["1"].get("segments") or []) == 2


@pytest.mark.asyncio
async def test_sentinel_poc_corridor_2_anti_hallucination_split_guard():
    """
    VULN-CORRIDOR-002 (Invariant 1):
    1) 隱性自駕轉場日（無 transit 標籤，但新區域有 >= 2 個合法景點 MinPts >= 2）應合法切分為走廊。
    2) 單點 AI 跨區座標幻覺（東京駐留日中間夾雜 1 個無交通標籤、無同城支撐的大阪假座標），
       嚴禁分裂為 1 點自證子群，必須留在東京子群並被導正回東京！
    """
    async def mock_tokyo_healer(query, **kwargs):
        if "一蘭" in query:
            return {"results": [{"lat": 35.6617, "lng": 139.7011, "name": "一蘭 澀谷店"}]}
        return {"results": []}

    with patch("services.geocode_service.smart_geocode_logic", side_effect=mock_tokyo_healer):
        # Part 1: 隱性自駕轉場 (東京 2 點 -> 京都 2 點，無 transit 類別，但符合 MinPts >= 2)
        implicit_corridor_items = [
            {"day_number": 1, "place_name": "明治神宮", "category": "sightseeing", "lat": 35.6764, "lng": 139.6993},
            {"day_number": 1, "place_name": "表參道 Hills", "category": "shopping", "lat": 35.6673, "lng": 139.7088},
            {"day_number": 1, "place_name": "金閣寺", "category": "sightseeing", "lat": 35.0394, "lng": 135.7292},
            {"day_number": 1, "place_name": "嵐山渡月橋", "category": "sightseeing", "lat": 35.0116, "lng": 135.6778},
        ]
        healed_imp, dl_imp = await verify_and_heal_itinerary_coords(
            implicit_corridor_items,
            trip_meta={"title": "日本關東關西自駕遊"},
        )
        assert dl_imp["1"].get("type") == "transit_corridor"
        assert abs(healed_imp[0]["lat"] - 35.6764) < 0.01
        assert abs(healed_imp[2]["lat"] - 35.0394) < 0.01

        # Part 2: 東京駐留日夾雜單點大阪幻覺 (MinPts == 1, 無 transit, 非已知目標城市)
        hallucinated_stay_items = [
            {"day_number": 1, "place_name": "淺草寺", "category": "sightseeing", "lat": 35.7148, "lng": 139.7967},
            {"day_number": 1, "place_name": "一蘭拉麵", "category": "food", "lat": 34.6687, "lng": 135.5013},  # 大阪道頓堀幻覺座標
            {"day_number": 1, "place_name": "晴空塔", "category": "sightseeing", "lat": 35.7101, "lng": 139.8107},
        ]
        healed_stay, dl_stay = await verify_and_heal_itinerary_coords(
            hallucinated_stay_items,
            trip_meta={"title": "2026 東京自由行"},
        )
        # 絕不可被切分為東京 -> 大阪走廊！
        assert dl_stay["1"].get("type") != "transit_corridor"
        assert "大阪" not in dl_stay["1"]["name"]
        # 大阪幻覺座標必須被攔截並導正回東京 (lat > 35.5)
        assert healed_stay[1]["lat"] > 35.5
        assert healed_stay[1]["lng"] > 139.5


@pytest.mark.asyncio
async def test_sentinel_poc_corridor_3_corridor_amnesia_on_reverification_and_mcp():
    """
    VULN-CORRIDOR-003 (Invariant 4):
    當行程之 daily_locations['1'] 已儲存 type='transit_corridor' 與 segments=[東京, 京都]（頂層 lat/lng 為京都），
    後續呼叫 verify_and_heal_itinerary_coords 或遠端 MCP manage_itinerary_node 新增上午東京景點時，
    必須識別東京屬於當日合法走廊子群，不得將東京景點當作 >180km 離群點誤殺！
    """
    existing_corridor_trip = {
        "id": "11111111-2222-3333-4444-555555555555",
        "created_by": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "title": "東京京都雙城遊",
        "start_date": "2026-11-01",
        "end_date": "2026-11-05",
        "content": {
            "daily_locations": {
                "1": {
                    "name": "東京 → 京都",
                    "lat": 35.0116,
                    "lng": 135.7681,
                    "type": "transit_corridor",
                    "segments": [
                        {"name": "東京", "lat": 35.6895, "lng": 139.6917},
                        {"name": "京都", "lat": 35.0116, "lng": 135.7681},
                    ],
                }
            }
        },
    }

    async def mock_empty_geo(*args, **kwargs):
        return {"results": []}

    with patch("services.geocode_service.smart_geocode_logic", side_effect=mock_empty_geo):
        # 1) 測試 verify_and_heal_itinerary_coords 二次驗證不失憶
        new_items = [
            {"day_number": 1, "place_name": "築地場外市場", "lat": 35.6655, "lng": 139.7707},
            {"day_number": 1, "place_name": "二條城", "lat": 35.0142, "lng": 135.7482},
        ]
        healed, dl_out = await verify_and_heal_itinerary_coords(
            new_items,
            trip_meta=existing_corridor_trip,
        )
        assert abs(healed[0]["lat"] - 35.6655) < 0.01, "東京上午景點遭京都頂層錨點誤殺！"
        assert abs(healed[0]["lng"] - 139.7707) < 0.01
        assert abs(healed[1]["lat"] - 35.0142) < 0.01
        assert len(dl_out["1"].get("segments") or []) == 2

        # 2) 測試 resolve_trip_spatial_anchor 回傳 segments 供 MCP 使用
        anc = await resolve_trip_spatial_anchor(existing_corridor_trip, day_number=1)
        assert len(anc.get("segments") or []) == 2

        # 3) 測試遠端 MCP manage_itinerary_node 新增東京景點至京都走廊日不被誤殺
        from unittest.mock import MagicMock
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        alice_uid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        trip_id = existing_corridor_trip["id"]
        inserted_records = []
        mock_sb = MagicMock()
        def mock_table(tn):
            t = MagicMock()
            t.select.return_value = t
            t.eq.return_value = t
            t.order.return_value = t
            t.limit.return_value = t
            if tn == "itineraries":
                t.execute.return_value = MagicMock(data=[existing_corridor_trip])
            elif tn == "trip_members":
                t.execute.return_value = MagicMock(data=[])
            elif tn == "itinerary_items":
                t.execute.return_value = MagicMock(data=[])
                t.insert.side_effect = lambda rec: (inserted_records.extend(rec) if isinstance(rec, list) else inserted_records.append(rec)) or MagicMock(data=rec if isinstance(rec, list) else [rec])
            return t
        mock_sb.table.side_effect = mock_table
        with patch("routers.mcp.get_verified_user", return_value=alice_uid), \
             patch("routers.mcp.get_supabase", return_value=mock_sb):
            resp = client.post(
                "/api/mcp",
                headers={"Authorization": "Bearer test"},
                json={
                    "jsonrpc": "2.0",
                    "id": 201,
                    "method": "tools/call",
                    "params": {
                        "name": "manage_itinerary_node",
                        "arguments": {
                            "trip_id": trip_id,
                            "day_index": 1,
                            "action": "add",
                            "places": [{"place_name": "築地場外市場", "lat": 35.6655, "lng": 139.7707}]
                        }
                    }
                }
            )
            assert resp.status_code == 200
            assert resp.json()["result"]["isError"] is False
            assert len(inserted_records) == 1
            assert abs(inserted_records[0]["location_lat"] - 35.6655) < 0.01


@pytest.mark.asyncio
async def test_sentinel_poc_corridor_4_zero_dict_corridor_and_bridge_action_noise():
    """
    VULN-CORRIDOR-004 (Invariant 2 & Invariant 3):
    1) 全球無字典走廊（秘魯 Lima -> Cusco 580km）：不在 27 城靜態表中，仍必須保留兩端座標並動態生成不重複之走廊名稱。
    2) 含 ACTION_NOISE_KEYWORDS 之交通橋接節點（『搭乘新幹線前往京都』無座標）應自動錨定至出發地子群，而非留 None；
       而含 ACTION_NOISE_KEYWORDS 之純動作雜訊若夾帶跨國假座標（巴黎），必須被攔截清除或導正！
    """
    async def mock_empty_geo(*args, **kwargs):
        return {"results": []}

    with patch("services.geocode_service.smart_geocode_logic", side_effect=mock_empty_geo):
        # Part 1: 秘魯 Lima (-12.0464, -77.0428) -> Cusco (-13.5320, -71.9675) 580km 國內線轉場
        peru_items = [
            {"day_number": 1, "place_name": "Lima Plaza Mayor", "category": "sightseeing", "lat": -12.0464, "lng": -77.0428},
            {"day_number": 1, "place_name": "Lima Miraflores Park", "category": "sightseeing", "lat": -12.1211, "lng": -77.0305},
            {"day_number": 1, "place_name": "LATAM Flight to Cusco", "category": "transit", "lat": -12.0219, "lng": -77.1143},
            {"day_number": 1, "place_name": "Cusco Plaza de Armas", "category": "sightseeing", "lat": -13.5168, "lng": -71.9788},
            {"day_number": 1, "place_name": "Sacsayhuaman Cusco", "category": "sightseeing", "lat": -13.5097, "lng": -71.9817},
        ]
        healed_pe, dl_pe = await verify_and_heal_itinerary_coords(
            peru_items,
            trip_meta={"title": "2026 Peru Expedition"},
        )
        assert abs(healed_pe[0]["lat"] - (-12.0464)) < 0.01
        assert abs(healed_pe[3]["lat"] - (-13.5168)) < 0.01
        assert dl_pe["1"].get("type") == "transit_corridor"
        seg_names = [s["name"] for s in (dl_pe["1"].get("segments") or [])]
        assert len(seg_names) == 2 and seg_names[0] != seg_names[1]

        # Part 2: 交通橋接節點無座標錨定 & 純動作雜訊跨國假座標攔截
        bridge_and_noise_items = [
            {"day_number": 1, "place_name": "淺草寺", "category": "sightseeing", "lat": 35.7148, "lng": 139.7967},
            {"day_number": 1, "place_name": "上野公園", "category": "sightseeing", "lat": 35.7141, "lng": 139.7741},
            {"day_number": 1, "place_name": "搭乘新幹線前往京都", "category": "transit", "lat": None, "lng": None},
            {"day_number": 1, "place_name": "飯店 check-in 休息", "category": "hotel", "lat": 48.8566, "lng": 2.3522},  # 巴黎假座標
            {"day_number": 1, "place_name": "京都塔", "category": "sightseeing", "lat": 34.9875, "lng": 135.7593},
            {"day_number": 1, "place_name": "錦市場", "category": "food", "lat": 35.0050, "lng": 135.7649},
        ]
        healed_bn, _ = await verify_and_heal_itinerary_coords(
            bridge_and_noise_items,
            trip_meta={"title": "東京京都自由行"},
        )
        # 交通橋接節點無座標時，應自動錨定至出發地 (東京 ~35.71)
        assert healed_bn[2]["lat"] is not None and abs(healed_bn[2]["lat"] - 35.714) < 0.1
        # 純動作雜訊夾帶巴黎假座標 (48.8566, 2.3522)，絕不得原樣放行！
        assert healed_bn[3]["lat"] is None or healed_bn[3]["lat"] < 40.0

        # Part 3: Step 3 LANDMARKS_DB 動態走廊命名 (札幌 -> 函館 250km，函館非 27 城但靠 LANDMARKS_DB 命中函館山)
        hakodate_items = [
            {"day_number": 1, "place_name": "札幌電視塔", "category": "sightseeing", "lat": 43.0611, "lng": 141.3564},
            {"day_number": 1, "place_name": "搭乘特急北斗號前往函館", "category": "transit", "lat": 43.0611, "lng": 141.3564},
            {"day_number": 1, "place_name": "五稜郭公園", "category": "sightseeing", "lat": 41.7969, "lng": 140.7568},
            {"day_number": 1, "place_name": "金森紅磚倉庫", "category": "sightseeing", "lat": 41.7661, "lng": 140.7161},
        ]
        healed_hako, dl_hako = await verify_and_heal_itinerary_coords(
            hakodate_items,
            trip_meta={"title": "札幌函館鐵道遊"},
        )
        assert dl_hako["1"].get("type") == "transit_corridor"
        assert "函館" in dl_hako["1"]["name"]



# ==============================================================================
# 🟢 Phase 4 Mantis Block G: Benign Control & Non-Regression Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_benign_corridor_1_single_city_stay_day_unchanged():
    """Mantis Block G 1: 一般單一城市駐留日維持 type='stay' (或相容格式)，0 額外請求。"""
    items = [
        {"day_number": 1, "place_name": "台北 101", "lat": 25.0339, "lng": 121.5645},
        {"day_number": 1, "place_name": "中正紀念堂", "lat": 25.0347, "lng": 121.5219},
    ]
    healed, dl = await verify_and_heal_itinerary_coords(items, trip_meta={"title": "台北一日遊"})
    assert abs(healed[0]["lat"] - 25.0339) < 0.001
    assert abs(healed[1]["lat"] - 25.0347) < 0.001
    assert dl["1"]["name"] == "台北"
    assert dl["1"].get("type", "stay") == "stay"


@pytest.mark.asyncio
async def test_benign_corridor_2_three_city_multi_split_corridor():
    """Mantis Block G 2: 單日 3 城雙轉場（東京 -> 名古屋 -> 京都），3 個子群各自獨立保全。"""
    items = [
        {"day_number": 1, "place_name": "東京車站一番街", "category": "shopping", "lat": 35.6812, "lng": 139.7671},
        {"day_number": 1, "place_name": "搭乘新幹線前往名古屋", "category": "transit", "lat": 35.6812, "lng": 139.7671},
        {"day_number": 1, "place_name": "名古屋城", "category": "sightseeing", "lat": 35.1847, "lng": 136.8997},
        {"day_number": 1, "place_name": "熱田神宮", "category": "sightseeing", "lat": 35.1256, "lng": 136.9079},
        {"day_number": 1, "place_name": "搭乘新幹線前往京都", "category": "transit", "lat": 35.1709, "lng": 136.8815},
        {"day_number": 1, "place_name": "八坂神社", "category": "sightseeing", "lat": 35.0037, "lng": 135.7785},
    ]
    healed, dl = await verify_and_heal_itinerary_coords(items, trip_meta={"title": "東海道縱貫遊"})
    assert abs(healed[0]["lat"] - 35.6812) < 0.01
    assert abs(healed[2]["lat"] - 35.1847) < 0.01
    assert abs(healed[5]["lat"] - 35.0037) < 0.01
    assert dl["1"].get("type") == "transit_corridor"
    assert len(dl["1"].get("segments") or []) == 3


@pytest.mark.asyncio
async def test_benign_corridor_3_url_verified_immunity_and_prompt_rule():
    """Mantis Block G 3: _url_verified 真實連結豁免與事前 Prompt 第 4 條跨城規則檢查。"""
    anchor = await resolve_prompt_spatial_anchor("東京、京都 5 日遊")
    prompt_text = build_spatial_constraint_prompt(anchor)
    assert "transit" in prompt_text.lower() or "轉場" in prompt_text

    items = [
        {"day_number": 1, "place_name": "自訂座標點", "lat": 34.99, "lng": 135.78, "_url_verified": True},
    ]
    healed, _ = await verify_and_heal_itinerary_coords(items, trip_meta={"title": "東京自由行"})
    assert healed[0]["lat"] == 34.99
    assert "_url_verified" not in healed[0]


@pytest.mark.asyncio
async def test_benign_corridor_4_round_trip_loop_and_mcp_add_corridor():
    """Mantis Block G 4: 單日環狀往返 (東京 -> 河口湖 -> 東京) 與遠端 MCP 走廊日新增上午東京景點不誤殺。"""
    loop_items = [
        {"day_number": 1, "place_name": "新宿車站", "category": "transit", "lat": 35.6896, "lng": 139.7006},
        {"day_number": 1, "place_name": "河口湖天上山公園", "category": "sightseeing", "lat": 35.5042, "lng": 138.7722},
        {"day_number": 1, "place_name": "大石公園", "category": "sightseeing", "lat": 35.5231, "lng": 138.7458},
        {"day_number": 1, "place_name": "搭乘高速巴士返回新宿", "category": "transit", "lat": 35.4982, "lng": 138.7686},
        {"day_number": 1, "place_name": "歌舞伎町一番街", "category": "nightlife", "lat": 35.6946, "lng": 139.7019},
        {"day_number": 1, "place_name": "東京都廳展望室", "category": "sightseeing", "lat": 35.6896, "lng": 139.6917},
    ]
    healed, dl = await verify_and_heal_itinerary_coords(loop_items, trip_meta={"title": "東京近郊一日遊"})
    assert abs(healed[1]["lat"] - 35.5042) < 0.01
    assert abs(healed[4]["lat"] - 35.6946) < 0.01
    assert dl["1"].get("type") == "transit_corridor"
    assert len(dl["1"].get("segments") or []) == 3

    # 驗證透過 MCP manage_itinerary_node 新增返程東京夜間景點（六本木之丘）
    from unittest.mock import MagicMock
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    alice_uid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    trip_id = "22222222-3333-4444-5555-666666666666"
    inserted_records = []
    mock_sb = MagicMock()
    mock_trip_data = MagicMock(data=[{
        "id": trip_id,
        "title": "東京近郊一日遊",
        "created_by": alice_uid,
        "total_days": 1,
        "content": {"daily_locations": dl},
    }])
    def mock_table(tn):
        t = MagicMock()
        t.select.return_value = t
        t.eq.return_value = t
        t.order.return_value = t
        t.limit.return_value = t
        if tn == "itineraries":
            t.execute.return_value = mock_trip_data
        elif tn == "trip_members":
            t.execute.return_value = MagicMock(data=[])
        elif tn == "itinerary_items":
            t.execute.return_value = MagicMock(data=[])
            t.insert.side_effect = lambda rec: (inserted_records.extend(rec) if isinstance(rec, list) else inserted_records.append(rec)) or MagicMock(data=rec if isinstance(rec, list) else [rec])
        return t
    mock_sb.table.side_effect = mock_table
    with patch("routers.mcp.get_verified_user", return_value=alice_uid), \
         patch("routers.mcp.get_supabase", return_value=mock_sb):
        resp = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer test"},
            json={
                "jsonrpc": "2.0",
                "id": 202,
                "method": "tools/call",
                "params": {
                    "name": "manage_itinerary_node",
                    "arguments": {
                        "trip_id": trip_id,
                        "day_index": 1,
                        "action": "add",
                        "places": [{"place_name": "六本木之丘展望台", "lat": 35.6604, "lng": 139.7292}]
                    }
                }
            }
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["isError"] is False
        assert len(inserted_records) == 1
        assert abs(inserted_records[0]["location_lat"] - 35.6604) < 0.01

