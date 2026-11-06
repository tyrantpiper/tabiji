# -*- coding: utf-8 -*-
"""
🛡️ Security Sentinel Simulation & Adversarial PoC Suite: MCP Trip Expansion
Validates RFC 9728 discovery, cross-tenant isolation on list_user_trips,
BOLA defense on get_trip_itinerary, AI coordinate sanity guardrails,
day_index bounds checking, incremental sort_order, and Mantis Block G controls.
"""

import pytest
import uuid
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from main import app

client = TestClient(app)

ALICE_UUID = str(uuid.uuid4())
MALLORY_UUID = str(uuid.uuid4())
ALICE_TRIP_ID = str(uuid.uuid4())
MALLORY_TRIP_ID = str(uuid.uuid4())


# ==============================================================================
# Phase 1: Target 4 - RFC 9728 Protected Resource Discovery
# ==============================================================================

def test_sentinel_poc_rfc9728_protected_resource_discovery():
    """驗證 Model Context Protocol 2026-07-28 規範要求的 RFC 9728 Discovery 端點"""
    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200, f"Expected 200 from RFC 9728, got {resp.status_code}"
    data = resp.json()
    assert "resource" in data
    assert "authorization_servers" in data
    assert isinstance(data["authorization_servers"], list)


# ==============================================================================
# Phase 2: Target 1 - list_user_trips Cross-Tenant IDOR Defense
# ==============================================================================

def test_sentinel_poc_list_user_trips_idor_isolation():
    """驗證 list_user_trips 嚴格隔離租戶，Mallory 無法獲取 Alice 的行程"""
    mock_supabase = MagicMock()
    mock_table = MagicMock()
    mock_supabase.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.in_.return_value = mock_table
    mock_table.order.return_value = mock_table

    # 模擬 Alice 擁有一個行程，且身為另一個行程的成員
    mock_owned = MagicMock(data=[
        {"id": ALICE_TRIP_ID, "title": "Alice 東京行程", "total_days": 5, "start_date": "2026-04-01", "created_by": ALICE_UUID}
    ])
    mock_member = MagicMock(data=[])

    def mock_table_exec(table_name):
        t = MagicMock()
        t.select.return_value = t
        t.eq.return_value = t
        t.in_.return_value = t
        t.order.return_value = t
        if table_name == "itineraries":
            t.execute.return_value = mock_owned
        elif table_name == "trip_members":
            t.execute.return_value = mock_member
        return t

    mock_supabase.table.side_effect = mock_table_exec

    with patch("routers.mcp.get_verified_user", return_value=ALICE_UUID), \
         patch("routers.mcp.get_supabase", return_value=mock_supabase):
        resp = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer alice_valid_jwt"},
            json={
                "jsonrpc": "2.0",
                "id": 101,
                "method": "tools/call",
                "params": {"name": "list_user_trips", "arguments": {}}
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data
        text_content = data["result"]["content"][0]["text"]
        assert "Alice 東京行程" in text_content
        assert MALLORY_TRIP_ID not in text_content


# ==============================================================================
# Phase 3: Target 2 - get_trip_itinerary BOLA Access Control Defense
# ==============================================================================

def test_sentinel_poc_get_trip_itinerary_bola_rejection():
    """驗證 get_trip_itinerary 具備物件級授權 (BOLA) 防禦，Mallory 探測 Alice 行程直接駁回"""
    mock_supabase = MagicMock()
    mock_trip_data = MagicMock(data=[
        {"id": ALICE_TRIP_ID, "title": "Alice 東京行程", "created_by": ALICE_UUID, "total_days": 3}
    ])
    mock_member_data = MagicMock(data=[])

    def mock_table_exec(table_name):
        t = MagicMock()
        t.select.return_value = t
        t.eq.return_value = t
        if table_name == "itineraries":
            t.execute.return_value = mock_trip_data
        elif table_name == "trip_members":
            t.execute.return_value = mock_member_data
        return t

    mock_supabase.table.side_effect = mock_table_exec

    with patch("routers.mcp.get_verified_user", return_value=MALLORY_UUID), \
         patch("routers.mcp.get_supabase", return_value=mock_supabase):
        resp = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer mallory_valid_jwt"},
            json={
                "jsonrpc": "2.0",
                "id": 102,
                "method": "tools/call",
                "params": {"name": "get_trip_itinerary", "arguments": {"trip_id": ALICE_TRIP_ID}}
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["isError"] is True
        assert "權限不足" in data["result"]["content"][0]["text"]


# ==============================================================================
# Phase 4: Target 3 - manage_itinerary_node Batch, Sanity & Day Bounds Defense
# ==============================================================================

def test_sentinel_poc_manage_itinerary_node_day_bounds_defense():
    """驗證當 AI 傳入超過行程 total_days 的 day_index 時，系統阻斷幽靈孤兒資料產生"""
    mock_supabase = MagicMock()
    mock_trip_data = MagicMock(data=[
        {"id": ALICE_TRIP_ID, "title": "Alice 東京行程", "created_by": ALICE_UUID, "total_days": 3}
    ])
    mock_member_data = MagicMock(data=[])

    def mock_table_exec(table_name):
        t = MagicMock()
        t.select.return_value = t
        t.eq.return_value = t
        if table_name == "itineraries":
            t.execute.return_value = mock_trip_data
        elif table_name == "trip_members":
            t.execute.return_value = mock_member_data
        return t

    mock_supabase.table.side_effect = mock_table_exec

    with patch("routers.mcp.get_verified_user", return_value=ALICE_UUID), \
         patch("routers.mcp.get_supabase", return_value=mock_supabase):
        resp = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer alice_valid_jwt"},
            json={
                "jsonrpc": "2.0",
                "id": 103,
                "method": "tools/call",
                "params": {
                    "name": "manage_itinerary_node",
                    "arguments": {
                        "trip_id": ALICE_TRIP_ID,
                        "day_index": 10,  # 超出 3 天上限
                        "action": "add",
                        "places": [{"place_name": "富士山"}]
                    }
                }
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["isError"] is True
        assert "天數錯誤" in data["result"]["content"][0]["text"]


def test_sentinel_poc_manage_itinerary_node_coordinate_sanity_defense():
    """驗證 AI 輸出的幻覺座標 (lat=999, lng=999) 被自動剔除並回退，不污染資料庫"""
    mock_supabase = MagicMock()
    mock_trip_data = MagicMock(data=[
        {"id": ALICE_TRIP_ID, "title": "Alice 東京行程", "created_by": ALICE_UUID, "total_days": 3}
    ])
    mock_member_data = MagicMock(data=[])
    mock_items_data = MagicMock(data=[])
    inserted_records = []

    def mock_table_exec(table_name):
        t = MagicMock()
        t.select.return_value = t
        t.eq.return_value = t
        t.order.return_value = t
        t.limit.return_value = t
        if table_name == "itineraries":
            t.execute.return_value = mock_trip_data
        elif table_name == "trip_members":
            t.execute.return_value = mock_member_data
        elif table_name == "itinerary_items":
            t.execute.return_value = mock_items_data
            t.insert.side_effect = lambda rec: MagicMock(execute=lambda: inserted_records.append(rec) or MagicMock(data=[rec]))
        return t

    mock_supabase.table.side_effect = mock_table_exec

    with patch("routers.mcp.get_verified_user", return_value=ALICE_UUID), \
         patch("routers.mcp.get_supabase", return_value=mock_supabase):
        resp = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer alice_valid_jwt"},
            json={
                "jsonrpc": "2.0",
                "id": 104,
                "method": "tools/call",
                "params": {
                    "name": "manage_itinerary_node",
                    "arguments": {
                        "trip_id": ALICE_TRIP_ID,
                        "day_index": 1,
                        "action": "add",
                        "places": [
                            # 1. 幻覺座標：應該被剔除
                            {"place_name": "測試幻覺", "lat": 999.0, "lng": 999.0},
                            # 2. 合法有效座標：應該被直接採納
                            {"place_name": "東京晴空塔", "lat": 35.7100, "lng": 139.8107}
                        ]
                    }
                }
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["isError"] is False
        assert len(inserted_records) == 2
        # 第一筆幻覺座標被過濾為 None 或 Geocode 結果 (非 999)
        assert inserted_records[0]["location_lat"] != 999.0
        # 第二筆合法座標直接秒存
        assert inserted_records[1]["location_lat"] == 35.7100
        assert inserted_records[1]["location_lng"] == 139.8107
        # 序列序號遞增
        assert inserted_records[1]["sort_order"] > inserted_records[0]["sort_order"]


# ==============================================================================
# Phase 5: Mantis Block G Benign Controls
# ==============================================================================

def test_benign_single_place_addition():
    """良性對照組 1：單筆景點相容新增模式運作正常"""
    mock_supabase = MagicMock()
    mock_trip_data = MagicMock(data=[
        {"id": ALICE_TRIP_ID, "title": "Alice 東京行程", "created_by": ALICE_UUID, "total_days": 3}
    ])
    inserted_records = []

    def mock_table_exec(table_name):
        t = MagicMock()
        t.select.return_value = t
        t.eq.return_value = t
        t.order.return_value = t
        t.limit.return_value = t
        if table_name == "itineraries":
            t.execute.return_value = mock_trip_data
        elif table_name == "trip_members":
            t.execute.return_value = MagicMock(data=[])
        elif table_name == "itinerary_items":
            t.execute.return_value = MagicMock(data=[])
            t.insert.side_effect = lambda rec: MagicMock(execute=lambda: inserted_records.append(rec) or MagicMock(data=[rec]))
        return t

    mock_supabase.table.side_effect = mock_table_exec

    with patch("routers.mcp.get_verified_user", return_value=ALICE_UUID), \
         patch("routers.mcp.get_supabase", return_value=mock_supabase):
        resp = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer alice_valid_jwt"},
            json={
                "jsonrpc": "2.0",
                "id": 105,
                "method": "tools/call",
                "params": {
                    "name": "manage_itinerary_node",
                    "arguments": {
                        "trip_id": ALICE_TRIP_ID,
                        "day_index": 2,
                        "action": "add",
                        "place_name": "淺草寺",
                        "arrival_time": "10:00",
                        "notes": "參拜雷門"
                    }
                }
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["isError"] is False
        assert len(inserted_records) == 1
        assert inserted_records[0]["place_name"] == "淺草寺"


def test_benign_recommend_tickets():
    """良性對照組 2：票券推薦與安全分潤導流保持正常運作"""
    with patch("routers.mcp.get_verified_user", return_value=ALICE_UUID):
        resp = client.post(
            "/api/mcp",
            headers={"Authorization": "Bearer alice_valid_jwt"},
            json={
                "jsonrpc": "2.0",
                "id": 106,
                "method": "tools/call",
                "params": {
                    "name": "recommend_tickets",
                    "arguments": {
                        "place_name": "東京晴空塔",
                        "destination": "東京"
                    }
                }
            }
        )
        assert resp.status_code == 200
        data = resp.json()
        text = data["result"]["content"][0]["text"]
        assert "東京晴空塔" in text
        assert "https://tabiji.app/go/klook/" in text

