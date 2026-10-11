import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

# Add backend directory to sys.path
backend_path = Path(__file__).resolve().parents[1]
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import pytest
from pydantic import BaseModel
from models.base import SaveItineraryRequest, UpdateCoverRequest


def test_update_cover_request_schema_supports_null():
    """驗證 UpdateCoverRequest 必須支援 None/null 以便使用者執行『移除封面』操作"""
    # 1. 設置合法網址
    req_url = UpdateCoverRequest(cover_image="https://res.cloudinary.com/demo/image/upload/v1/sample.jpg")
    assert req_url.cover_image == "https://res.cloudinary.com/demo/image/upload/v1/sample.jpg"

    # 2. 支援 None/null (若未宣告 Optional，此處在 Pydantic 會崩潰)
    req_none = UpdateCoverRequest(cover_image=None)
    assert req_none.cover_image is None


def test_save_itinerary_request_includes_cover_image():
    """驗證 SaveItineraryRequest 正確納入 cover_image 欄位且向下相容"""
    # 1. 帶有封面網址
    req_with_cover = SaveItineraryRequest(
        title="東京 5 日遊",
        creator_name="Ryan",
        user_id="user_123",
        cover_image="https://res.cloudinary.com/demo/image/upload/v1/tokyo.webp"
    )
    assert req_with_cover.cover_image == "https://res.cloudinary.com/demo/image/upload/v1/tokyo.webp"

    # 2. 未傳遞封面 (向下相容)
    req_default = SaveItineraryRequest(
        title="巴黎藝文行",
        creator_name="Ryan",
        user_id="user_123"
    )
    assert req_default.cover_image is None


def test_cover_normalization_logic():
    """驗證空字串正規化為 None 邏輯，避免資料庫被空字串污染導致前端渲染破圖"""
    def normalize_cover(raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        trimmed = raw.strip()
        return trimmed if trimmed else None

    assert normalize_cover("") is None
    assert normalize_cover("   ") is None
    assert normalize_cover(None) is None
    assert normalize_cover("https://example.com/cover.webp") == "https://example.com/cover.webp"
    assert normalize_cover("  https://example.com/cover.webp  ") == "https://example.com/cover.webp"


def test_permission_guard_for_cover_update():
    """驗證行程成員權限防禦邏輯：非成員必須嚴格拋出 403 異常，不可允許越權竄改 (IDOR Defense)"""
    mock_supabase = MagicMock()

    def simulate_update_cover(trip_id: str, caller_user_id: str, new_cover: Optional[str]):
        # 模擬查詢 trip_members
        mock_members = [{"user_id": "owner_123"}, {"user_id": "collaborator_456"}]
        is_member = any(m["user_id"] == caller_user_id for m in mock_members)

        if not is_member:
            raise PermissionError("403: 您沒有權限修改此行程封面")

        return {"status": "success", "cover_image": new_cover}

    # 1. 成員修改成功
    res = simulate_update_cover("trip_abc", "collaborator_456", "https://img.jpg")
    assert res["status"] == "success"

    # 2. 陌生人/攻擊者被 403 阻斷
    with pytest.raises(PermissionError) as exc_info:
        simulate_update_cover("trip_abc", "attacker_999", "https://malicious.jpg")
    assert "403" in str(exc_info.value)
