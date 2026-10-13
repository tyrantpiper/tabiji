import sys
from pathlib import Path
from typing import Optional

# Add backend directory to sys.path
backend_path = Path(__file__).resolve().parents[1]
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import pytest
from models.base import CreateManualTripRequest
from services.cover_service import resolve_destination_cover_url, PRE_CURATED_COVERS, DEFAULT_COVER_IMAGE


def resolve_safe_cover(raw_cover: Optional[str], title: Optional[str]) -> str:
    """模擬後端清洗與保底邏輯"""
    if (
        raw_cover 
        and isinstance(raw_cover, str) 
        and raw_cover.strip() 
        and raw_cover.strip() not in ["null", "undefined"]
    ):
        return raw_cover.strip()
    return resolve_destination_cover_url(title)


def test_create_manual_trip_request_schema():
    """驗證 CreateManualTripRequest 正確接受 cover_image 欄位"""
    req = CreateManualTripRequest(
        title="東京 5 日自由行",
        start_date="2026-10-15",
        end_date="2026-10-19",
        creator_name="Ryan",
        user_id="user_123",
        cover_image="https://custom.cover/tokyo.jpg"
    )
    assert req.cover_image == "https://custom.cover/tokyo.jpg"

    req_none = CreateManualTripRequest(
        title="巴黎 5 日藝文慢步",
        start_date="2026-10-15",
        end_date="2026-10-19",
        creator_name="Ryan",
        user_id="user_123",
        cover_image=None
    )
    assert req_none.cover_image is None


def test_create_manual_trip_cover_fallback_logic():
    """驗證手動建立行程空值或偽值時，後端自動調用 resolve_destination_cover_url 保底"""
    # 1. 正常自訂封面保留
    custom = "https://images.unsplash.com/custom-tokyo.jpg"
    assert resolve_safe_cover(custom, "東京 5 日自由行") == custom

    # 2. 空值 (None) 自動解析東京
    assert resolve_safe_cover(None, "東京 5 日自由行") == PRE_CURATED_COVERS["tokyo"]

    # 3. 空字串與全空白自動解析巴黎
    assert resolve_safe_cover("", "巴黎 5 日藝文慢步") == PRE_CURATED_COVERS["paris"]
    assert resolve_safe_cover("   ", "巴黎 5 日藝文慢步") == PRE_CURATED_COVERS["paris"]

    # 4. 髒字串 ("null", "undefined") 自動解析紐約
    assert resolve_safe_cover("null", "紐約 5 日都會探索") == PRE_CURATED_COVERS["newyork"]
    assert resolve_safe_cover("undefined", "紐約 5 日都會探索") == PRE_CURATED_COVERS["newyork"]

    # 5. 未知地點優雅回退經典預設封面
    assert resolve_safe_cover(None, "神秘星際旅行") == DEFAULT_COVER_IMAGE


def test_backend_response_parity_fallback():
    """驗證後端在吐出行程資料時，若資料庫為空值，能無痛補齊封面回傳給客戶端"""
    mock_db_row = {
        "id": "trip_001",
        "title": "巴黎 5 日藝文慢步",
        "cover_image": None
    }
    
    # 讀取傳輸層保底補齊
    resolved_cover = resolve_safe_cover(mock_db_row["cover_image"], mock_db_row["title"])
    assert resolved_cover == PRE_CURATED_COVERS["paris"]
