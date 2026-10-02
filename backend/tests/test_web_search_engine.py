import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from services.web_search_engine import (
    unwrap_ddg_redirect,
    is_safe_external_url,
    execute_web_search,
    fetch_jina_reader,
    _search_ddg_html_fallback,
)


def test_unwrap_ddg_redirect():
    # 1. DDG tracker redirect URL
    wrapped = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.tokyo-skytree.jp%2F&rut=123"
    assert unwrap_ddg_redirect(wrapped) == "https://www.tokyo-skytree.jp/"

    # 2. Fully qualified DDG tracker redirect URL
    wrapped_full = "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpath%3Fa%3D1&rut=xyz"
    assert unwrap_ddg_redirect(wrapped_full) == "https://example.com/path?a=1"

    # 3. Direct URL without wrapping
    direct = "https://example.com/direct-link"
    assert unwrap_ddg_redirect(direct) == direct

    # 4. Empty or invalid input
    assert unwrap_ddg_redirect("") == ""
    assert unwrap_ddg_redirect("not-a-url") == "not-a-url"


def test_is_safe_external_url():
    # 1. Valid public HTTP/HTTPS URLs
    assert is_safe_external_url("https://www.tokyo-skytree.jp/") is True
    assert is_safe_external_url("http://example.com/page") is True

    # 2. Loopback and localhost (SSRF protection)
    assert is_safe_external_url("http://localhost:8008/api") is False
    assert is_safe_external_url("http://127.0.0.1:8000/secret") is False
    assert is_safe_external_url("http://0.0.0.0:80/") is False
    assert is_safe_external_url("http://[::1]/") is False

    # 3. Private / Cloud Metadata IP addresses (RFC1918 & AWS/GCP metadata)
    assert is_safe_external_url("http://192.168.1.1/admin") is False
    assert is_safe_external_url("http://10.0.0.1/") is False
    assert is_safe_external_url("http://172.16.0.1/") is False
    assert is_safe_external_url("http://169.254.169.254/latest/meta-data") is False

    # 4. Unsupported or dangerous protocols
    assert is_safe_external_url("file:///etc/passwd") is False
    assert is_safe_external_url("ftp://example.com/file") is False
    assert is_safe_external_url("javascript:alert(1)") is False
    assert is_safe_external_url("") is False


@pytest.mark.asyncio
async def test_execute_web_search_empty():
    results = await execute_web_search("   ")
    assert results == []


@pytest.mark.asyncio
async def test_execute_web_search_ddgs_success():
    mock_items = [
        {
            "title": "東京晴空塔 TOKYO SKYTREE",
            "href": "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.tokyo-skytree.jp%2F&rut=1",
            "body": "營業時間：10:00 - 21:00，最終入場 20:00。"
        }
    ]

    mock_ddgs_instance = MagicMock()
    mock_ddgs_instance.text.return_value = mock_items
    mock_ddgs_instance.__enter__.return_value = mock_ddgs_instance
    mock_ddgs_instance.__exit__.return_value = None

    with patch("ddgs.DDGS", return_value=mock_ddgs_instance):
        results = await execute_web_search("晴空塔 營業時間")
        assert len(results) == 1
        assert results[0]["title"] == "東京晴空塔 TOKYO SKYTREE"
        assert results[0]["url"] == "https://www.tokyo-skytree.jp/"
        assert "10:00" in results[0]["snippet"]


@pytest.mark.asyncio
async def test_execute_web_search_fallback_on_ddgs_error():
    mock_fallback_results = [
        {
            "title": "備援端點結果",
            "url": "https://example.com/fallback",
            "snippet": "靜態端點搜尋內容"
        }
    ]

    with patch("ddgs.DDGS", side_effect=Exception("DDGS Cloud IP Block")):
        with patch("services.web_search_engine._search_ddg_html_fallback", new_callable=AsyncMock) as mock_html:
            mock_html.return_value = mock_fallback_results
            results = await execute_web_search("東京美食推薦")
            assert results == mock_fallback_results
            mock_html.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_jina_reader_ssrf_guard():
    # Private IP must be rejected immediately without calling external HTTP
    result = await fetch_jina_reader("http://127.0.0.1:8000/internal")
    assert result["status"] == "error"
    assert result["error_code"] == "INVALID_URL"
    assert result["markdown"] == ""


@pytest.mark.asyncio
async def test_fetch_jina_reader_success():
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.text = "# 東京晴空塔\n\n最新營業時間為 10:00 至 21:00。"

    with patch("services.web_search_engine.get_search_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = await fetch_jina_reader("https://www.tokyo-skytree.jp/")
        assert result["status"] == "success"
        assert result["url"] == "https://www.tokyo-skytree.jp/"
        assert "東京晴空塔" in result["markdown"]


@pytest.mark.asyncio
async def test_fetch_jina_reader_401_graceful_fallback():
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 401
    mock_response.text = "Unauthorized - ASN reputation"

    with patch("services.web_search_engine.get_search_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = await fetch_jina_reader("https://www.tokyo-skytree.jp/")
        assert result["status"] == "error"
        assert result["error_code"] == "READER_UNAVAILABLE"
        assert "搜尋摘要" in result["message"]
        assert result["markdown"] == ""


@pytest.mark.asyncio
async def test_fetch_jina_reader_timeout_graceful_fallback():
    with patch("services.web_search_engine.get_search_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")
        mock_get_client.return_value = mock_client

        result = await fetch_jina_reader("https://www.tokyo-skytree.jp/")
        assert result["status"] == "error"
        assert result["error_code"] == "TIMEOUT"
        assert "過慢" in result["message"]
        assert result["markdown"] == ""


@pytest.mark.asyncio
async def test_execute_web_search_cloudflare_edge_success():
    mock_cf_results = [
        {
            "title": "Cloudflare 邊緣結果",
            "url": "https://example.com/cf-edge",
            "snippet": "來自 Cloudflare Worker 的搜尋摘要"
        }
    ]

    with patch("services.web_search_engine._sync_ddgs_call", side_effect=Exception("DDGS 403")):
        with patch("services.web_search_engine._search_cloudflare_edge", new_callable=AsyncMock) as mock_cf:
            mock_cf.return_value = mock_cf_results
            results = await execute_web_search("東京景點推薦")
            assert results == mock_cf_results
            mock_cf.assert_called_once()


@pytest.mark.asyncio
async def test_execute_web_search_wikipedia_fallback_success():
    mock_wiki_results = [
        {
            "title": "東京 (維基百科)",
            "url": "https://zh.wikipedia.org/wiki/東京",
            "snippet": "關於 東京 的開放百科條目詳細資訊"
        }
    ]

    with patch("services.web_search_engine._sync_ddgs_call", side_effect=Exception("DDGS 403")):
        with patch("services.web_search_engine._search_cloudflare_edge", new_callable=AsyncMock) as mock_cf:
            mock_cf.return_value = []
            with patch("services.web_search_engine._search_ddg_html_fallback", new_callable=AsyncMock) as mock_html:
                mock_html.return_value = []
                with patch("services.web_search_engine._search_wikipedia_fallback", new_callable=AsyncMock) as mock_wiki:
                    mock_wiki.return_value = mock_wiki_results
                    results = await execute_web_search("東京")
                    assert results == mock_wiki_results
                    mock_wiki.assert_called_once()

