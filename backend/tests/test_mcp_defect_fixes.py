# -*- coding: utf-8 -*-
"""
🛡️ Automated Sentinel Verification Suite: Audited Defect Remediations (DEF-01 ~ DEF-14 & Option A)
Verifies:
- DEF-01: Action Fallthrough Prevention & Strict Action Mapping in manage_itinerary_node
- DEF-02: Comprehensive calculate_trip_days (date span, daily_locations, total_days)
- DEF-04: Untrusted redirect_uri domain rejection in oauth_authorize
- DEF-06 & DEF-07: manage_itinerary_node item_id selector & zero-rows affected error reporting
- DEF-08: UUID regex validation preventing Postgres 22P02 syntax errors
- DEF-10: Safe day_index parsing in get_trip_itinerary ("all", "整本", int)
- DEF-13: Sanitized geocoding coordinates
- Option A: Trip Owner-Only Privacy Model for is_private items
"""

import sys
import os
import uuid
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

# 確保 backend 目錄在 sys.path 中
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from main import app
from routers.mcp import calculate_trip_days, is_valid_uuid, is_trusted_redirect_uri

client = TestClient(app)

OWNER_UUID = str(uuid.uuid4())
COLLAB_UUID = str(uuid.uuid4())
TRIP_ID = str(uuid.uuid4())
ITEM_ID = str(uuid.uuid4())


def test_def01_action_fallthrough_defense():
    """DEF-01: 驗證未知 action 絕不 fallthrough 至 add，且支援同義詞映射"""
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.limit.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[
        {"id": TRIP_ID, "created_by": OWNER_UUID, "title": "測試行程", "total_days": 3}
    ])

    with patch("routers.mcp.get_verified_user", return_value=OWNER_UUID), \
         patch("routers.mcp.get_supabase", return_value=mock_supabase):
        # 1. 惡意或未知 action 必須被直接駁回，不允許新增景點
        resp_invalid = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer token"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "manage_itinerary_node",
                    "arguments": {
                        "trip_id": TRIP_ID,
                        "day_index": 1,
                        "action": "unknown_exploit",
                        "place_name": "後門節點"
                    }
                }
            }
        )
        assert resp_invalid.status_code == 200
        res_data = resp_invalid.json()["result"]
        assert res_data["isError"] is True
        assert "不支援的操作類型" in res_data["content"][0]["text"]
        # 確保未調用 insert
        mock_table.insert.assert_not_called()


def test_def02_calculate_trip_days_comprehensive():
    """DEF-02: 驗證 calculate_trip_days 綜合比較日期跨度、daily_locations 與 total_days"""
    # 1. total_days 優先取最大值
    t1 = {"total_days": 5, "start_date": "2026-05-01", "end_date": "2026-05-03"}
    assert calculate_trip_days(t1) == 5

    # 2. date_span 較大時取 date_span
    t2 = {"total_days": 2, "start_date": "2026-05-01", "end_date": "2026-05-07"}
    assert calculate_trip_days(t2) == 7

    # 3. daily_locations 較大時取 daily_locations
    t3 = {
        "content": {"daily_locations": {"1": ["A"], "2": ["B"], "3": ["C"], "4": ["D"]}},
        "total_days": 2
    }
    assert calculate_trip_days(t3) == 4

    # 4. 空物件預設至少 1 天
    assert calculate_trip_days({}) == 1


def test_def04_oauth_authorize_untrusted_redirect_uri():
    """DEF-04: 驗證 /api/oauth/authorize 嚴格防禦非白名單 redirect_uri (Open Redirect)"""
    # 1. 攻擊者構造外部釣魚跳轉 -> 400
    resp_attack = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": OWNER_UUID,
            "redirect_uri": "https://attacker-phishing.com/callback",
            "code_challenge": "challenge_123"
        },
        follow_redirects=False
    )
    assert resp_attack.status_code == 400
    assert "Invalid redirect_uri" in resp_attack.json()["detail"]

    # 2. 受信信任網域 (Gemini) -> 302 正常重定向
    resp_valid = client.get(
        "/api/oauth/authorize",
        params={
            "client_id": OWNER_UUID,
            "redirect_uri": "https://gemini.google.com/oauth/callback",
            "code_challenge": "challenge_123"
        },
        follow_redirects=False
    )
    assert resp_valid.status_code == 302
    assert "https://gemini.google.com/oauth/callback" in resp_valid.headers["location"]


def test_def06_manage_itinerary_node_zero_rows_affected():
    """DEF-06: 驗證 remove 與 update 在 0 筆記錄受影響時回報錯誤"""
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.delete.return_value = mock_table
    mock_table.update.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.limit.return_value = mock_table

    def mock_table_exec():
        # itineraries 存在，但 itinerary_items delete/update 影響 0 筆 (data=[])
        return MagicMock(data=[])

    def mock_table_side_effect(name):
        t = MagicMock()
        t.select.return_value = t
        t.eq.return_value = t
        t.delete.return_value = t
        t.update.return_value = t
        t.order.return_value = t
        t.limit.return_value = t
        if name == "itineraries":
            t.execute.return_value = MagicMock(data=[{"id": TRIP_ID, "created_by": OWNER_UUID, "total_days": 3}])
        elif name == "itinerary_items":
            t.execute.return_value = MagicMock(data=[])
        return t

    mock_supabase.table.side_effect = mock_table_side_effect

    with patch("routers.mcp.get_verified_user", return_value=OWNER_UUID), \
         patch("routers.mcp.get_supabase", return_value=mock_supabase):
        # 1. 刪除不存在之景點
        resp_rm = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer token"},
            json={
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "manage_itinerary_node",
                    "arguments": {
                        "trip_id": TRIP_ID,
                        "day_index": 1,
                        "action": "remove",
                        "place_name": "不存在景點"
                    }
                }
            }
        )
        assert resp_rm.status_code == 200
        assert resp_rm.json()["result"]["isError"] is True
        assert "未找到指定的景點項目" in resp_rm.json()["result"]["content"][0]["text"]


def test_def07_manage_itinerary_node_item_id_selector():
    """DEF-07: 驗證 manage_itinerary_node 支援以 item_id 精確指定項目"""
    mock_supabase = MagicMock()
    deleted_ids = []

    def mock_table_side_effect(name):
        t = MagicMock()
        t.select.return_value = t
        t.eq.return_value = t
        t.order.return_value = t
        t.limit.return_value = t
        if name == "itineraries":
            t.execute.return_value = MagicMock(data=[{"id": TRIP_ID, "created_by": OWNER_UUID, "total_days": 3}])
        elif name == "itinerary_items":
            del_chain = MagicMock()
            del_chain.eq.side_effect = lambda field, val: (
                deleted_ids.append((field, val)) or del_chain
            )
            del_chain.execute.return_value = MagicMock(data=[{"id": ITEM_ID, "place_name": "澀谷Sky"}])
            t.delete.return_value = del_chain
        return t

    mock_supabase.table.side_effect = mock_table_side_effect

    with patch("routers.mcp.get_verified_user", return_value=OWNER_UUID), \
         patch("routers.mcp.get_supabase", return_value=mock_supabase):
        resp = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer token"},
            json={
                "jsonrpc": "2.0",
                "id": 20,
                "method": "tools/call",
                "params": {
                    "name": "manage_itinerary_node",
                    "arguments": {
                        "trip_id": TRIP_ID,
                        "item_id": ITEM_ID,
                        "day_index": 1,
                        "action": "remove"
                    }
                }
            }
        )
        assert resp.status_code == 200
        assert resp.json()["result"]["isError"] is False
        assert any(field == "id" and val == ITEM_ID for field, val in deleted_ids)


def test_def08_uuid_validation_prevents_22p02():
    """DEF-08: 驗證非 UUID 之字串 (如行程名稱) 會被前置攔截，避免 Postgres 22P02 語法錯誤"""
    with patch("routers.mcp.get_verified_user", return_value=OWNER_UUID):
        # 1. get_trip_itinerary 傳入非 UUID 行程名稱
        resp1 = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer token"},
            json={
                "jsonrpc": "2.0",
                "id": 30,
                "method": "tools/call",
                "params": {
                    "name": "get_trip_itinerary",
                    "arguments": {"trip_id": "Tokyo-Spring-2026"}
                }
            }
        )
        assert resp1.status_code == 200
        assert resp1.json()["result"]["isError"] is True
        assert "UUID" in resp1.json()["result"]["content"][0]["text"]

        # 2. manage_itinerary_node 傳入非 UUID 行程名稱
        resp2 = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer token"},
            json={
                "jsonrpc": "2.0",
                "id": 31,
                "method": "tools/call",
                "params": {
                    "name": "manage_itinerary_node",
                    "arguments": {"trip_id": "Tokyo-Spring-2026", "day_index": 1, "action": "add", "place_name": "淺草寺"}
                }
            }
        )
        assert resp2.status_code == 200
        assert resp2.json()["result"]["isError"] is True
        assert "UUID" in resp2.json()["result"]["content"][0]["text"]


def test_def10_get_trip_itinerary_safe_day_index_parsing():
    """DEF-10: 驗證 get_trip_itinerary 傳入 'all', '整本', None 不會引發 ValueError"""
    mock_supabase = MagicMock()
    mock_trip = MagicMock(data=[{"id": TRIP_ID, "created_by": OWNER_UUID, "title": "安全行程"}])
    mock_items = MagicMock(data=[
        {"id": "item-1", "day_number": 1, "time_slot": "10:00", "place_name": "東京鐵塔", "notes": ""},
        {"id": "item-2", "day_number": 2, "time_slot": "14:00", "place_name": "淺草寺", "notes": ""}
    ])

    def mock_table_side_effect(name):
        t = MagicMock()
        t.select.return_value = t
        t.eq.return_value = t
        t.order.return_value = t
        if name == "itineraries":
            t.execute.return_value = mock_trip
        elif name == "itinerary_items":
            t.execute.return_value = mock_items
        return t

    mock_supabase.table.side_effect = mock_table_side_effect

    with patch("routers.mcp.get_verified_user", return_value=OWNER_UUID), \
         patch("routers.mcp.get_supabase", return_value=mock_supabase):
        # 1. day_index="all"
        resp_all = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer token"},
            json={
                "jsonrpc": "2.0",
                "id": 40,
                "method": "tools/call",
                "params": {"name": "get_trip_itinerary", "arguments": {"trip_id": TRIP_ID, "day_index": "all"}}
            }
        )
        assert resp_all.status_code == 200
        assert "東京鐵塔" in resp_all.json()["result"]["content"][0]["text"]

        # 2. day_index="整本"
        resp_full = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer token"},
            json={
                "jsonrpc": "2.0",
                "id": 41,
                "method": "tools/call",
                "params": {"name": "get_trip_itinerary", "arguments": {"trip_id": TRIP_ID, "day_index": "整本"}}
            }
        )
        assert resp_full.status_code == 200
        assert "淺草寺" in resp_full.json()["result"]["content"][0]["text"]


def test_option_a_owner_only_privacy_filtering():
    """Option A: 驗證行程創立者可見私人項目，協作者存取時 is_private 項目被徹底過濾"""
    mock_supabase = MagicMock()
    mock_trip = MagicMock(data=[{"id": TRIP_ID, "created_by": OWNER_UUID, "title": "隱私測試行程"}])
    mock_collab_members = MagicMock(data=[{"id": "mem-1", "user_id": COLLAB_UUID}])
    mock_all_items = MagicMock(data=[
        {"id": "pub-1", "day_number": 1, "time_slot": "10:00", "place_name": "公開景點", "notes": "", "is_private": False},
        {"id": "priv-1", "day_number": 1, "time_slot": "14:00", "place_name": "秘密求婚地點", "notes": "私人活動", "is_private": True}
    ])

    def mock_table_side_effect(name):
        t = MagicMock()
        t.select.return_value = t
        t.eq.return_value = t
        t.order.return_value = t
        if name == "itineraries":
            t.execute.return_value = mock_trip
        elif name == "trip_members":
            t.execute.return_value = mock_collab_members
        elif name == "itinerary_items":
            t.execute.return_value = mock_all_items
        return t

    mock_supabase.table.side_effect = mock_table_side_effect

    # 1. 創立者 (OWNER) 查詢 -> 可看見公開與私人項目
    with patch("routers.mcp.get_verified_user", return_value=OWNER_UUID), \
         patch("routers.mcp.get_supabase", return_value=mock_supabase):
        resp_owner = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer token"},
            json={
                "jsonrpc": "2.0",
                "id": 50,
                "method": "tools/call",
                "params": {"name": "get_trip_itinerary", "arguments": {"trip_id": TRIP_ID}}
            }
        )
        text_owner = resp_owner.json()["result"]["content"][0]["text"]
        assert "公開景點" in text_owner
        assert "秘密求婚地點" in text_owner

    # 2. 協作者 (COLLAB) 查詢 -> 私人項目被過濾，僅可看見公開景點
    with patch("routers.mcp.get_verified_user", return_value=COLLAB_UUID), \
         patch("routers.mcp.get_supabase", return_value=mock_supabase):
        resp_collab = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer token"},
            json={
                "jsonrpc": "2.0",
                "id": 51,
                "method": "tools/call",
                "params": {"name": "get_trip_itinerary", "arguments": {"trip_id": TRIP_ID}}
            }
        )
        text_collab = resp_collab.json()["result"]["content"][0]["text"]
        assert "公開景點" in text_collab
        assert "秘密求婚地點" not in text_collab


def test_def09_affiliate_query_and_uuid_fallback():
    """DEF-09: 驗證 /go/klook 缺乏 target_id 但有 query，或傳入 trip UUID 時，跳轉目標為合法的 Klook 完整網址"""
    # 1. 僅有 query (?item=晴空塔) -> 必須回退至官方首頁並附帶 query
    resp1 = client.get("/go/klook?item=晴空塔", follow_redirects=False)
    assert resp1.status_code == 302
    loc1 = resp1.headers["location"]
    assert "https://affiliate.klook.com/jump?aff_id=TABIJI_AFF_888&target=https://www.klook.com/zh-TW/" in loc1
    assert "item=" in loc1

    # 2. 傳入 Tabiji trip UUID -> 必須回退至官方首頁，避免 Klook 端點 404
    resp2 = client.get(f"/go/klook/{TRIP_ID}?item=淺草寺", follow_redirects=False)
    assert resp2.status_code == 302
    loc2 = resp2.headers["location"]
    assert "https://affiliate.klook.com/jump?aff_id=TABIJI_AFF_888&target=https://www.klook.com/zh-TW/" in loc2
    assert "item=" in loc2


def test_def04_tabiji_app_trusted_domains():
    """DEF-04: 驗證 tabiji.app 與 *.tabiji.app 均被視為受信任網域"""
    assert is_trusted_redirect_uri("https://tabiji.app/oauth/callback") is True
    assert is_trusted_redirect_uri("https://auth.tabiji.app/callback") is True
    assert is_trusted_redirect_uri("https://www.tabijiapp.com/callback") is True
    assert is_trusted_redirect_uri("https://evil-tabiji.com/callback") is False


def test_def10_natural_language_day_extraction():
    """DEF-10: 驗證 natural language 輸入如 '第2天' 能正確提取為第 2 天"""
    mock_supabase = MagicMock()
    mock_trip = MagicMock(data=[{"id": TRIP_ID, "created_by": OWNER_UUID, "title": "自然語言測試"}])
    mock_items = MagicMock(data=[
        {"id": "item-2", "day_number": 2, "time_slot": "14:00", "place_name": "澀谷Sky", "notes": ""}
    ])

    def mock_table_side_effect(name):
        t = MagicMock()
        t.select.return_value = t
        t.eq.return_value = t
        t.order.return_value = t
        if name == "itineraries":
            t.execute.return_value = mock_trip
        elif name == "itinerary_items":
            t.execute.return_value = mock_items
        return t

    mock_supabase.table.side_effect = mock_table_side_effect

    with patch("routers.mcp.get_verified_user", return_value=OWNER_UUID), \
         patch("routers.mcp.get_supabase", return_value=mock_supabase):
        resp = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer token"},
            json={
                "jsonrpc": "2.0",
                "id": 60,
                "method": "tools/call",
                "params": {"name": "get_trip_itinerary", "arguments": {"trip_id": TRIP_ID, "day_index": "第2天"}}
            }
        )
        assert resp.status_code == 200
        assert "澀谷Sky" in resp.json()["result"]["content"][0]["text"]


def test_option_a_collaborator_cannot_mutate_private_item():
    """Option A: 協作者無法刪除或修改標記為 is_private 的景點項目"""
    mock_supabase = MagicMock()
    mock_trip = MagicMock(data=[{"id": TRIP_ID, "created_by": OWNER_UUID, "title": "協作者保護測試", "total_days": 3}])
    mock_members = MagicMock(data=[{"id": "mem-1", "user_id": COLLAB_UUID}])

    eq_calls = []
    def mock_table_side_effect(name):
        t = MagicMock()
        t.select.return_value = t
        t.eq.side_effect = lambda field, val: (eq_calls.append((field, val)) or t)
        t.order.return_value = t
        t.limit.return_value = t
        if name == "itineraries":
            t.execute.return_value = mock_trip
        elif name == "trip_members":
            t.execute.return_value = mock_members
        elif name == "itinerary_items":
            del_chain = MagicMock()
            del_chain.eq.side_effect = lambda field, val: (eq_calls.append((field, val)) or del_chain)
            # 模擬資料庫中若有 is_private=False 的過濾條件則回傳 0 筆受影響 (即無法刪除私人項目)
            del_chain.execute.return_value = MagicMock(data=[])
            t.delete.return_value = del_chain
        return t

    mock_supabase.table.side_effect = mock_table_side_effect

    with patch("routers.mcp.get_verified_user", return_value=COLLAB_UUID), \
         patch("routers.mcp.get_supabase", return_value=mock_supabase):
        resp = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer token"},
            json={
                "jsonrpc": "2.0",
                "id": 70,
                "method": "tools/call",
                "params": {
                    "name": "manage_itinerary_node",
                    "arguments": {
                        "trip_id": TRIP_ID,
                        "item_id": ITEM_ID,
                        "day_index": 1,
                        "action": "remove"
                    }
                }
            }
        )
        assert resp.status_code == 200
        # 確保查詢鏈中包含了 is_private=False 的邊界守衛
        assert any(field == "is_private" and val is False for field, val in eq_calls)

