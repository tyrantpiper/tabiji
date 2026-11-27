import pytest
import asyncio
import sys
import os
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch
from starlette.requests import Request as StarletteRequest

# 🚀 Path Setup: Ensure backend and current dir are in sys.path
root_dir = os.getcwd() # Workspace root
backend_dir = os.path.join(root_dir, "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Now we can import reliably
from routers.poi import ai_enrich_poi
from models.base import POIAIEnrichRequest
from tests.poi_contract.poi_factory import create_mock_wiki_result, create_mock_ai_result, get_contract_combination_rules

def _make_poi_http_request() -> StarletteRequest:
    return StarletteRequest({
        "type": "http",
        "method": "POST",
        "path": "/api/poi/ai-enrich",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "server": ("testserver", 80),
        "app": SimpleNamespace(state=SimpleNamespace(client=MagicMock())),
    })


@pytest.mark.asyncio
async def test_poi_enrich_status_matrix():
    """
    🔬 核心合約測試：驗證 AI 與 Wiki 各種成功/失敗組合下的最終狀態碼。
    """
    rules = get_contract_combination_rules()
    
    for rule in rules:
        # 1. 準備 Mock 資料
        ai_data = create_mock_ai_result() if rule["ai"] else {"summary": None}
        wiki_data = create_mock_wiki_result(status=rule["wiki"])
        
        # 2. 設置 Mock
        with patch('routers.poi.call_extraction', new_callable=AsyncMock) as m_ai, \
             patch('routers.poi.enrich_poi_complete', new_callable=AsyncMock) as m_wiki, \
             patch('routers.poi.POI_ENRICH_CACHE', {}), \
             patch('routers.poi.generate_v2_cache_key', return_value="test_key"):
            
            m_ai.return_value = json.dumps(ai_data)
            m_wiki.return_value = wiki_data
            
            # 3. 執行 (必須帶上 api_key 否則會觸發 400)
            request = POIAIEnrichRequest(
                name="Test POI", 
                type="attraction", 
                lat=0, 
                lng=0,
                api_key="mock_key_for_contract_test"
            )
            result = await ai_enrich_poi(_make_poi_http_request(), request)
            
            # 4. 斷言合約一致性
            print(f"Testing AI={rule['ai']}/Wiki={rule['wiki']} -> Expected: {rule['expected']}, Actual: {result['status']}")
            assert result["status"] == rule["expected"], f"Contract breach for case: AI={rule['ai']}, Wiki={rule['wiki']}"

@pytest.mark.asyncio
async def test_poi_contract_warnings_downgrade():
    """
    🛡️ 驗證當輔助資料抓取逾時或缺失時，狀態必須降落至 PARTIAL_SUCCESS。
    """
    # 案例：AI 成功，但 Wikipedia 逾時
    ai_data = create_mock_ai_result()
    wiki_data = create_mock_wiki_result(
        status="PARTIAL_SUCCESS", 
        cultural_desc=None, 
        warnings=["WIKIPEDIA_TIMEOUT"]
    )
    
    with patch('routers.poi.call_extraction', new_callable=AsyncMock) as m_ai, \
         patch('routers.poi.enrich_poi_complete', new_callable=AsyncMock) as m_wiki, \
         patch('routers.poi.POI_ENRICH_CACHE', {}), \
         patch('routers.poi.generate_v2_cache_key', return_value="test_key"):
        
        m_ai.return_value = json.dumps(ai_data)
        m_wiki.return_value = wiki_data
        
        request = POIAIEnrichRequest(
            name="Timeout POI", 
            type="attraction", 
            lat=0, 
            lng=0,
            api_key="mock_key_for_contract_test"
        )
        result = await ai_enrich_poi(_make_poi_http_request(), request)
        
        assert result["status"] == "PARTIAL_SUCCESS"
        assert "WIKIPEDIA_TIMEOUT" in result["warnings"]
        print("✅ Warning-driven status downgrade verified.")
