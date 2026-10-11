import sys
from pathlib import Path

# Add backend directory to sys.path
backend_path = Path(__file__).resolve().parents[1]
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

import pytest
from services.geocode_service import (
    LOCATION_KEYWORDS,
    detect_country_from_keywords,
    infer_currency_from_destination
)

def test_patched_global_destination_recognition_and_currency():
    """驗證修復後：歐美亞三大代表城市均能精準識別國碼與法定貨幣，無迴歸現象"""
    # 1. 斷言 LOCATION_KEYWORDS 已成功收錄 FR 與 US
    assert "FR" in LOCATION_KEYWORDS
    assert "US" in LOCATION_KEYWORDS
    assert "JP" in LOCATION_KEYWORDS
    
    # 2. 亞洲 (東京)
    assert detect_country_from_keywords("東京 5 日自由行") == "JP"
    assert infer_currency_from_destination("東京 5 日自由行") == "JPY"
    
    # 3. 歐洲 (巴黎)
    assert detect_country_from_keywords("巴黎 5 日藝文浪漫") == "FR"
    assert infer_currency_from_destination("巴黎 5 日藝文浪漫") == "EUR"
    
    # 4. 美洲 (紐約)
    assert detect_country_from_keywords("紐約 5 日都會經典") == "US"
    assert infer_currency_from_destination("紐約 5 日都會經典") == "USD"
    
    # 5. 英文查詢相容性 (i18n Compatibility)
    assert detect_country_from_keywords("Paris 5-Day Highlights") == "FR"
    assert infer_currency_from_destination("Paris 5-Day Highlights") == "EUR"
    assert detect_country_from_keywords("New York 5-Day Urban Explorer") == "US"
    assert infer_currency_from_destination("New York 5-Day Urban Explorer") == "USD"
    assert detect_country_from_keywords("Tokyo 5-Day Highlights") == "JP"
    assert infer_currency_from_destination("Tokyo 5-Day Highlights") == "JPY"
