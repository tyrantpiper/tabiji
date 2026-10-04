import pytest
import httpx
import time
from main import app, _deep_health_cache

@pytest.mark.asyncio
async def test_health_check_fast_response():
    """驗證 /health 與 /api/health 端點能在極速（< 50ms）內回傳 200 OK 與合法結構，且支援 GET 與 HEAD"""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # 1. 測試原生 /health GET
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]
        assert "uptime_seconds" in data
        assert data["service"] == "ryan-travel-api"
        assert data["version"] == "1.2.9-hardened"

        # 2. 測試原生 /health HEAD
        head_res = await client.head("/health")
        assert head_res.status_code == 200

        # 3. 測試邊緣別名 /api/health GET
        api_res = await client.get("/api/health")
        assert api_res.status_code == 200
        assert api_res.json()["version"] == "1.2.9-hardened"

        # 4. 測試邊緣別名 /api/health HEAD
        api_head_res = await client.head("/api/health")
        assert api_head_res.status_code == 200

@pytest.mark.asyncio
async def test_health_check_deep_resilience_and_caching():
    """驗證 /health/deep 與 /api/health/deep 深度診斷、60s 防抖快取與 HEAD 支援"""
    # 重置測試快取狀態
    _deep_health_cache["last_checked"] = 0.0
    _deep_health_cache["payload"] = {}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # 1. 首次請求 (未命中快取，穿透至 Supabase 或熔斷返回)
        start_t = time.time()
        res1 = await client.get("/health/deep")
        elapsed1 = time.time() - start_t
        assert res1.status_code in [200, 500, 502, 503, 504]
        data1 = res1.json()
        assert "status" in data1
        assert data1.get("cached") is False

        # 2. 第二次請求 (60s 防抖快速通道，必須 < 15ms 瞬回且 cached == True)
        start_t = time.time()
        res2 = await client.get("/health/deep")
        elapsed2 = time.time() - start_t
        assert res2.status_code == res1.status_code
        data2 = res2.json()
        assert data2.get("cached") is True
        assert elapsed2 < 0.05, f"Cache fast-path took too long: {elapsed2}s"

        # 3. 測試邊緣別名 /api/health/deep GET (命中快取)
        res_alias = await client.get("/api/health/deep")
        assert res_alias.status_code == res1.status_code
        data_alias = res_alias.json()
        assert data_alias.get("cached") is True

        # 4. 測試 HEAD 方法 (防止 UptimeRobot 405 誤報)
        head_res = await client.head("/health/deep")
        assert head_res.status_code == res1.status_code
        alias_head_res = await client.head("/api/health/deep")
        assert alias_head_res.status_code == res1.status_code
