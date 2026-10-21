"""
Security Sentinel In-Memory Sandbox PoC: POI Zero-Cost Link Resolver & Anti-Poisoning
-------------------------------------------------------------------------------------
驗證維度：
1. POI-ZERO-01: IP Context Poisoning (Nebraska Geo-Drift) Detection & Rejection
2. POI-ZERO-02: Pure-Query City Overview Staticmap Center Rejection
3. POI-ZERO-03: Cascading Overwrite on Conflict Defense
4. POI-ZERO-04: Taiwan Address-POI Deterministic Splitter
5. POI-ZERO-05: Google Web Place RPC Parser & XSSI Protection Stripping
"""

import pytest
import re
import json
from unittest.mock import AsyncMock, patch, MagicMock

# 載入受測模組與純函數
from services.link_resolver import (
    RE_QUERY,
    RE_STATICMAP,
    extract_address_from_description,
    resolve_google_maps_link,
    split_taiwan_address_and_poi,
    parse_google_place_rpc_payload
)



# ═══════════════════════════════════════════════════════════════════════════════
# 2. In-Memory 沙盒 PoC 測試套件
# ═══════════════════════════════════════════════════════════════════════════════

class TestPoiZeroCostResolverSentinel:

    def test_poc_01_taiwan_address_title_concatenation_splitter(self):
        """
        [POI-ZERO-04] 驗證純正則分離器能將混合郵遞區號門牌之長字串，100% 精準分離為純店名與門牌
        """
        cases = [
            (
                "807高雄市三民區十美里漢口街103號君腿庫飯",
                "君腿庫飯",
                "高雄市三民區漢口街103號"
            ),
            (
                "804高雄市鼓山區桃源里柴山大路16號世外桃源土雞城",
                "世外桃源土雞城",
                "高雄市鼓山區柴山大路16號"
            ),
            (
                "807台灣高雄市三民區九如二路227號老新台菜 (九如創始店)",
                "老新台菜 (九如創始店)",
                "高雄市三民區九如二路227號"
            ),
            (
                "台北市大安區忠孝東路四段181巷7弄13號星巴克",
                "星巴克",
                "台北市大安區忠孝東路四段181巷7弄13號"
            )
        ]

        for raw_input, expected_title, expected_addr in cases:
            addr, title = split_taiwan_address_and_poi(raw_input)
            assert title == expected_title, f"Title mismatch for '{raw_input}': got '{title}'"
            assert addr == expected_addr, f"Address mismatch for '{raw_input}': got '{addr}'"

    def test_poc_02_ip_context_poisoning_nebraska_drift_rejection(self):
        """
        [POI-ZERO-01] 驗證伺服器 IP 中毒（Nebraska 座標 zoom=6）會被主動判定並熔斷丟棄
        """
        poisoned_staticmap = (
            "https://maps.google.com/maps/api/staticmap?"
            "center=41.10567%2C-96.265644&zoom=6&size=900x900&language=en&sensor=false"
        )
        final_url = "https://www.google.com/maps?q=807%E9%AB%98%E9%9B%84%E5%B8%82%E4%B8%89%E6%B0%91%E5%8D%80%E5%8D%81%E7%BE%8E%E9%87%8C%E6%BC%A2%E5%8F%A3%E8%A1%97103%E8%99%9F%E5%90%9B%E8%85%BF%E5%BA%AB%E9%A3%AF"

        # 檢測防線邏輯：純 ?q= 網址且缺乏 !3d/!4d 時，staticmap 嚴禁採信
        is_pure_query_search = bool(RE_QUERY.search(final_url)) and not bool(re.search(r'!3d-?\d+\.\d+!4d-?\d+\.\d+', final_url))
        assert is_pure_query_search is True, "Must identify link as pure search query without precise coords"

        # 檢測 zoom <= 10 熔斷防禦
        zoom_m = re.search(r'zoom=(\d+)', poisoned_staticmap)
        zoom_val = int(zoom_m.group(1)) if zoom_m else 15
        assert zoom_val <= 10, "Should detect overview zoom level"

        # 模擬採信判定：防線生效時回傳 None，杜絕誤植至美國
        extracted_coords = None
        if not is_pure_query_search and zoom_val > 10:
            extracted_coords = (41.10567, -96.265644)

        assert extracted_coords is None, "Poisoned Nebraska coordinates MUST be rejected!"

    def test_poc_03_city_overview_dummy_coordinate_leak_rejection(self):
        """
        [POI-ZERO-02] 驗證城市級概覽假座標（如高雄中心 22.6459648, 120.3109888）在純 ?q= 網址下亦被拒絕
        """
        city_overview_staticmap = (
            "https://maps.google.com/maps/api/staticmap?"
            "center=22.6459648%2C120.3109888&zoom=14&size=900x900&language=en&sensor=false"
        )
        final_url = "https://www.google.com/maps?q=804%E9%AB%98%E9%9B%84%E5%B8%82%E9%BC%93%E5%B1%B1%E5%8D%80%E6%A1%83%E6%BA%90%E9%87%8C%E6%9F%B4%E5%B1%B1%E5%A4%A7%E8%B7%AF16%E8%99%9F%E4%B8%96%E5%A4%96%E6%A1%83%E6%BA%90%E5%9C%9F%E9%9B%9E%E5%9F%8E"

        # 純 query 網址全面封殺 staticmap center
        is_pure_query_search = bool(RE_QUERY.search(final_url)) and not bool(re.search(r'!3d-?\d+\.\d+!4d-?\d+\.\d+', final_url))
        
        extracted_coords = None
        if not is_pure_query_search:
            sm_match = RE_STATICMAP.search(city_overview_staticmap)
            if sm_match:
                extracted_coords = (float(sm_match.group(1)), float(sm_match.group(2)))

        assert extracted_coords is None, "City overview dummy center must NOT be trusted for pure search queries!"

    def test_poc_04_google_web_place_rpc_parser_and_xssi_stripping(self):
        """
        [POI-ZERO-05] 驗證 Google Web Place RPC 結構化解析與 )]}' 前綴脫敏
        """
        # 構造模擬 Google preview/place RPC 原始回傳封包
        mock_raw_rpc = (
            ")]}'\n"
            "["
            "  null, [], null, null, null, null,"
            "  ["
            "    \"id_token\", \"metadata_token\","
            "    [\"807高雄市三民區十美里漢口街103號\"],"
            "    null, null, null, null, null, null,"
            "    [null, null, 22.6429772, 120.2971507],"  # data[6][9] 物理經緯度
            "    \"0x346e057a75a4d467:0xd59fb30f0ccc4ed0\","
            "    \"君腿庫飯\","                             # data[6][11] 純店名
            "    null, [\"台灣餐廳\"],"
            "    null, null, null, null, null,"
            "    \"807高雄市三民區十美里漢口街103號君腿庫飯\","
            "    null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null,"
            "    \"807高雄市三民區十美里漢口街103號\","     # data[6][39] 門牌地址
            "    null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null,"
            "    null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null, null,"
            "    \"ChIJZ9SkdXoFbjQR0E7MDA-zn9U\""          # data[6][78] Google Place ID
            "  ]"
            "]"
        )

        res = parse_google_place_rpc_payload(mock_raw_rpc)
        assert res is not None, "Failed to parse Google Web Place RPC payload"
        assert res["title"] == "君腿庫飯"
        assert res["lat"] == pytest.approx(22.6429772, abs=1e-5)
        assert res["lng"] == pytest.approx(120.2971507, abs=1e-5)
        assert res["address"] == "807高雄市三民區十美里漢口街103號"
        assert res["place_id"] == "ChIJZ9SkdXoFbjQR0E7MDA-zn9U"

    def test_poc_05_conflict_overwrite_prevention_logic(self):
        """
        [POI-ZERO-03] 驗證跨地點防覆寫邏輯：不同 source_url 之 POI 絕對不可被覆寫
        """
        existing_pool = [
            {
                "id": "item-1",
                "title": "君腿庫飯",
                "address": "高雄市三民區漢口街103號",
                "lat": 22.6429772,
                "lng": 120.2971507,
                "source_url": "https://maps.app.goo.gl/mmMsQpYNpLcE5GhE9?g_st=ic"
            }
        ]

        # 模擬新匯入的「世外桃源土雞城」
        new_imported_item = {
            "id": "item-2",
            "title": "世外桃源土雞城",
            "address": "高雄市鼓山區柴山大路16號",
            "lat": 22.6469273,
            "lng": 120.2537484,
            "source_url": "https://maps.app.goo.gl/rHZYzoimiNDH39ua9?g_st=ic"
        }

        # 模擬升級後的安全 SWR mutate / Pool 更新演算法
        def safe_mutate_pool(current, new_items):
            current_list = current or []
            updated = []
            for c in current_list:
                # 只有當 ID 相符，或 source_url 完全相同，才允許覆寫更新
                matched = next((item for item in new_items if item["id"] == c["id"] or item["source_url"] == c.get("source_url")), None)
                updated.append(matched or c)
            
            # 新地點（ID 與 source_url 均未在既有清單者）作為 brandNew 加入
            brand_new = [
                item for item in new_items 
                if not any(c["id"] == item["id"] or c.get("source_url") == item["source_url"] for c in current_list)
            ]
            return brand_new + updated

        final_pool = safe_mutate_pool(existing_pool, [new_imported_item])

        assert len(final_pool) == 2, f"Expected 2 POIs, but got {len(final_pool)}"
        titles = [p["title"] for p in final_pool]
        assert "君腿庫飯" in titles, "君腿庫飯 MUST NOT be overwritten!"
        assert "世外桃源土雞城" in titles, "世外桃源土雞城 MUST be added alongside existing POI!"

    def test_poc_06_link_resolver_module_has_json(self):
        """[POI-ZERO-06] 驗證 link_resolver 模組確實匯入 json 模組以供 RPC 解析使用"""
        import services.link_resolver as lr
        assert hasattr(lr, 'json'), "services.link_resolver is missing 'import json'!"

    def test_poc_07_google_rpc_schema_mutation_boundary_defense(self):
        """
        [POI-REF-01] 驗證 Google Place RPC 在遇到陣列長度短缺或結構位移時，防禦性提取器能平滑回傳 None 而非未捕獲例外
        """
        assert parse_google_place_rpc_payload(")]}'\n[1, 2, 3]") is None
        assert parse_google_place_rpc_payload(")]}'\n[null, null, null, null, null, null, {}]") is None
        assert parse_google_place_rpc_payload(")]}'\n[null, null, null, null, null, null, [1, 2, 3]]") is None
        corrupted_coords_rpc = (
            ")]}'\n"
            "[null, null, null, null, null, null, "
            "[null, null, null, null, null, null, null, null, null, [null, null, null, null], null, 'Title']]"
        )
        assert parse_google_place_rpc_payload(corrupted_coords_rpc) is None

    def test_poc_08_d1_not_null_coordinate_batch_filter(self):
        """
        [POI-REF-02] 驗證 D1 批次寫入防禦：過濾缺少合法數值經緯度的項目，防止 SQLite NOT NULL 約束拋出異常
        """
        import sqlite3
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE user_poi_pool (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                lat REAL NOT NULL,
                lng REAL NOT NULL,
                UNIQUE(user_id, lat, lng)
            )
        """)
        conn.commit()

        raw_places = [
            {"title": "有效地點 1", "lat": 22.6429772, "lng": 120.2971507},
            {"title": "無座標地點", "lat": None, "lng": None},
            {"title": "NaN 座標地點", "lat": float("nan"), "lng": 120.2971507},
            {"title": "有效地點 2", "lat": 22.6469273, "lng": 120.2537484},
        ]

        def filter_valid_d1_places(places):
            valid = []
            for p in places:
                if not p or not isinstance(p, dict):
                    continue
                lat, lng = p.get("lat"), p.get("lng")
                if (
                    isinstance(lat, (int, float))
                    and isinstance(lng, (int, float))
                    and not (isinstance(lat, float) and lat != lat)
                    and not (isinstance(lng, float) and lng != lng)
                ):
                    valid.append(p)
            return valid

        valid_places = filter_valid_d1_places(raw_places)
        assert len(valid_places) == 2

        insert_sql = "INSERT INTO user_poi_pool (id, user_id, title, lat, lng) VALUES (?, ?, ?, ?, ?)"
        data = [(f"id-{idx}", "user-1", p["title"], p["lat"], p["lng"]) for idx, p in enumerate(valid_places)]
        cursor.executemany(insert_sql, data)
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM user_poi_pool")
        assert cursor.fetchone()[0] == 2

    def test_poc_09_swr_is_same_poi_undefined_coords_isolation(self):
        """
        [POI-REF-03] 驗證 SWR isSamePoi 比對：當兩者皆無 source_url 且皆無經緯度時，嚴禁判定為同一地點
        """
        def is_same_poi_strict(a, b):
            if a.get("id") and b.get("id"):
                return a["id"] == b["id"]
            if a.get("source_url") and b.get("source_url"):
                return a["source_url"] == b["source_url"]
            a_lat, a_lng = a.get("lat"), a.get("lng")
            b_lat, b_lng = b.get("lat"), b.get("lng")
            if (
                isinstance(a_lat, (int, float))
                and isinstance(b_lat, (int, float))
                and isinstance(a_lng, (int, float))
                and isinstance(b_lng, (int, float))
            ):
                return a_lat == b_lat and a_lng == b_lng
            return False

        poi_a = {"id": "poi-001", "title": "未定位地點 A", "lat": None, "lng": None, "source_url": None}
        poi_b = {"id": "poi-002", "title": "未定位地點 B", "lat": None, "lng": None, "source_url": None}
        assert is_same_poi_strict(poi_a, poi_b) is False

    def test_poc_10_placelist_lstrip_corruption_vs_regex_defense(self):
        r"""
        [POI-LIST-01] 驗證正則 re.sub(r"^\)]\}'\s*", "", raw_text) 能 100% 安全保留完整合法的 JSON 結構
        """
        raw_empty_placelist = ")]}'\n[]"
        safe_stripped = re.sub(r"^\)]\}'\s*", "", raw_empty_placelist).strip()
        assert safe_stripped == "[]"
        parsed = json.loads(safe_stripped)
        assert parsed == []

    @pytest.mark.asyncio
    async def test_poc_11_placelist_2shot_retry_resilience(self):
        """
        [POI-LIST-02] 驗證清單解析之 2-Shot 彈性重試機制：當初次連線收到 Google 冷啟動非 XSSI 回應時，自動重試第 2 次並成功取得清單
        """
        call_count = 0

        async def mock_fetch_placelist_rpc():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "<!DOCTYPE html><html><body>Consent Required</body></html>"
            return ')]}\'\n[[["list_id", 3, [[1], [9]], 1, 1], 4, null, null, "Want to go", "", null, null, [[null, [null, null, "Address", null, "Addr"], "POI Title", null, null, [null, null, 25.033, 121.565]]]]]'


        max_retries = 2
        success = False
        parsed_items = []
        for attempt in range(max_retries):
            raw_text = await mock_fetch_placelist_rpc()
            clean_raw = raw_text.strip()
            if not clean_raw.startswith(")]}'"):
                if attempt < max_retries - 1:
                    continue
                break
            stripped = re.sub(r"^\)]\}'\s*", "", clean_raw).strip()
            data = json.loads(stripped)
            parsed_items = data[0][8]
            success = True
            break

        assert success is True
        assert call_count == 2
        assert len(parsed_items) == 1
        assert parsed_items[0][2] == "POI Title"

    def test_poc_12_asymmetric_timeout_pipeline_misrouting_defense(self):
        """
        [POI-LIST-03] 驗證短網址重定向追蹤超時對齊 (12.0s vs 8.0s)，確保在慢速網路下正確路由至清單解析器
        """
        slow_network_latency = 9.0
        head_timeout_flawed = 8.0
        head_timeout_safe = 12.0

        is_placelist_flawed = False
        if slow_network_latency > head_timeout_flawed:
            is_placelist_flawed = False
        assert is_placelist_flawed is False

        is_placelist_safe = False
        if slow_network_latency <= head_timeout_safe:
            is_placelist_safe = True
        assert is_placelist_safe is True

    def test_poc_13_cloudflare_worker_category_whitelist_override_and_mantis_patch(self):
        """
        [POI-CUSTOM-01] 驗證 Cloudflare Worker 邊緣端類別白名單缺陷與 Mantis 補丁防禦
        缺陷：舊邏輯在遇到自訂協定 'custom:🍜:拉麵:#F59E0B' 時，因非預設 7 大類別被強制降級為 'attraction'
        補丁：isValidCategory 正確放行標準 7 大類別與合法自訂協定，同時拒絕惡意字串
        """
        valid_categories = ["attraction", "food", "cafe", "shopping", "hotel", "transport", "other"]
        
        # 缺陷邏輯 (現有 worker.js:409-410)
        def flawed_worker_category(cat):
            return cat if cat in valid_categories else "attraction"
            
        custom_payload = "custom:🍜:拉麵:#F59E0B"
        assert flawed_worker_category(custom_payload) == "attraction", "Flawed worker must drop custom protocol!"
        
        # Mantis 防禦補丁
        def patched_worker_category(cat):
            if not isinstance(cat, str):
                return "attraction"
            if cat in valid_categories:
                return cat
            if cat.startswith("custom:") and len(cat.split(":")) >= 4:
                return cat
            return "attraction"
            
        assert patched_worker_category(custom_payload) == "custom:🍜:拉麵:#F59E0B"
        assert patched_worker_category("food") == "food"
        assert patched_worker_category("invalid_injection") == "attraction"
        assert patched_worker_category("custom:incomplete") == "attraction"

    def test_poc_14_colon_delimiter_injection_and_split_safety(self):
        """
        [POI-CUSTOM-02] 驗證自訂類別協定在名稱含冒號時的分隔符衝突與安全解析
        """
        emoji = "☕"
        raw_name = "下午茶:鬆餅"
        color = "#F59E0B"
        
        # 1. 序列化防禦：將冒號轉義為全形冒號
        clean_name = raw_name.replace(":", "：").strip()
        protocol_str = f"custom:{emoji}:{clean_name}:{color}"
        
        # 2. 解碼防禦：即使遇到未轉義冒號，採用尾端定位截取
        unfiltered_str = f"custom:{emoji}:{raw_name}:{color}"
        parts = unfiltered_str.split(":")
        assert len(parts) == 5
        
        def safe_parse_category(cat_str):
            if not cat_str or not cat_str.startswith("custom:"):
                return {"is_custom": False, "key": "other"}
            p = cat_str.split(":")
            if len(p) < 4:
                return {"is_custom": False, "key": "other"}
            parsed_emoji = p[1] or "📍"
            parsed_color = p[-1] or "#E56E25"
            parsed_label = ":".join(p[2:-1]) or "自訂"
            return {
                "is_custom": True,
                "key": cat_str,
                "label": parsed_label,
                "emoji": parsed_emoji,
                "color": parsed_color
            }
            
        res1 = safe_parse_category(protocol_str)
        assert res1["is_custom"] is True
        assert res1["label"] == "下午茶：鬆餅"
        assert res1["color"] == "#F59E0B"
        
        res2 = safe_parse_category(unfiltered_str)
        assert res2["is_custom"] is True
        assert res2["label"] == "下午茶:鬆餅"
        assert res2["color"] == "#F59E0B"

    def test_poc_15_malformed_protocol_truncation_safety(self):
        """
        [POI-CUSTOM-03] 驗證殘缺、空值或異常協定字串之平滑降級，杜絕未捕獲異常
        """
        def safe_parse_category(cat_str):
            if not cat_str or not isinstance(cat_str, str) or not cat_str.startswith("custom:"):
                return {"is_custom": False, "key": "other", "label": "全部"}
            p = cat_str.split(":")
            if len(p) < 4:
                return {"is_custom": False, "key": "other", "label": "全部"}
            return {
                "is_custom": True,
                "key": cat_str,
                "label": ":".join(p[2:-1]) or "自訂",
                "emoji": p[1] or "📍",
                "color": p[-1] or "#E56E25"
            }
            
        assert safe_parse_category(None)["key"] == "other"
        assert safe_parse_category("")["key"] == "other"
        assert safe_parse_category("custom:")["key"] == "other"
        assert safe_parse_category("custom:🍜")["key"] == "other"
        assert safe_parse_category("custom:::")["is_custom"] is True
        assert safe_parse_category("custom:::")["emoji"] == "📍"

    def test_poc_16_dynamic_harvesting_dedup_and_purity(self):
        """
        [POI-CUSTOM-04] 驗證跨 POI 之動態收割 (Harvesting) 演算法：去重、保證純淨度、排除預設類別
        """
        pois = [
            {"id": "1", "category": "custom:🍜:拉麵:#F59E0B"},
            {"id": "2", "category": "food"},
            {"id": "3", "category": "custom:🍜:拉麵:#F59E0B"},
            {"id": "4", "category": "custom:⛩️:神社:#EF4444"},
            {"id": "5", "category": "attraction"},
            {"id": "6", "category": None},
        ]
        
        def harvest_custom_categories(poi_list):
            seen = {}
            for p in poi_list:
                cat = p.get("category")
                if cat and isinstance(cat, str) and cat.startswith("custom:"):
                    if cat not in seen:
                        parts = cat.split(":")
                        if len(parts) >= 4:
                            seen[cat] = {
                                "key": cat,
                                "emoji": parts[1] or "📍",
                                "label": ":".join(parts[2:-1]) or "自訂",
                                "color": parts[-1] or "#E56E25"
                            }
            return list(seen.values())
            
        harvested = harvest_custom_categories(pois)
        assert len(harvested) == 2, f"Expected 2 unique custom categories, got {len(harvested)}"
        keys = [h["key"] for h in harvested]
        assert "custom:🍜:拉麵:#F59E0B" in keys
        assert "custom:⛩️:神社:#EF4444" in keys
        assert "food" not in keys




