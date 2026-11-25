from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from services.intent_router import classify_chat_intent
from services.web_search_engine import fetch_jina_reader


@pytest.mark.asyncio
async def test_intent_not_poisoned_by_itinerary_context():
    """驗證即使 Prompt 內含台北 Day 1 行程脈絡，使用者輸入 IG 網址仍必須被分類為 SEARCH"""
    raw_url = "https://www.instagram.com/reel/DX8x6XOtEqI/?stkn=MXZ3YWxibjJzejBtZg=="
    
    # 1. 裸 URL 測試
    intent_raw, tools_raw = await classify_chat_intent(raw_url)
    assert intent_raw == "SEARCH", f"Expected SEARCH, got {intent_raw}"
    assert len(tools_raw) > 0, "SEARCH intent must mount search tools"

    # 2. 帶有 XML tag 的包裝 (Prompt 注入格式)
    wrapped_message = f"""【當前行程脈絡】
Day 1: 台北車站 -> 榕錦時光生活園區
Day 2: 故宮博物院

<user_input_abc123>
{raw_url}
</user_input_abc123>"""
    
    intent_wrapped, tools_wrapped = await classify_chat_intent(wrapped_message)
    assert intent_wrapped == "SEARCH", f"Expected SEARCH, got {intent_wrapped}"
    assert len(tools_wrapped) > 0, "SEARCH intent must mount search tools"


def _make_stream_cm(status_code: int, body_text: str, encoding: str = "utf-8"):
    """Build an async context manager mimicking httpx.AsyncClient.stream()."""
    raw_bytes = body_text.encode(encoding)

    class _MockStreamResp:
        def __init__(self):
            self.status_code = status_code
            self.encoding = encoding

        async def aiter_bytes(self, chunk_size: int = 65536):
            yield raw_bytes

    class _StreamCM:
        async def __aenter__(self):
            return _MockStreamResp()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    return _StreamCM()


@pytest.mark.asyncio
async def test_instagram_reel_opengraph_fallback():
    """驗證 Instagram Reel 網址能透過 OpenGraph 確定性抽取貼文內容（不依賴 CI 外網連線）"""
    ig_url = "https://www.instagram.com/reel/DX8x6XOtEqI/?stkn=MXZ3YWxibjJzejBtZg=="
    og_html = (
        "<html><head>"
        '<meta property="og:title" content="大阪難波超人氣燒肉 焼肉エイト" />'
        '<meta property="og:site_name" content="Instagram" />'
        '<meta property="og:description" content="大阪燒肉推薦：焼肉エイト 黑毛和牛" />'
        "</head></html>"
    )

    mock_client = AsyncMock()
    mock_client.stream = MagicMock(return_value=_make_stream_cm(200, og_html))

    with patch("services.web_search_engine.get_search_client", return_value=mock_client):
        result = await fetch_jina_reader(ig_url)

    assert result["status"] == "success", f"Result status failed: {result}"
    markdown = result.get("markdown", "")
    assert "焼肉エイト" in markdown or "燒肉" in markdown or "大阪" in markdown, (
        f"Instagram post content not found in markdown: {markdown[:300]}"
    )


@pytest.mark.asyncio
async def test_instagram_login_wall_rejected_and_degrades_cleanly():
    """驗證遭遇 IG 登入牆（中/英文）與 Jina 阻擋時，依序嘗試 OG(1次) -> Embed(1次) -> Jina(1次)，不回傳偽陽性且絕不重打 OG/Embed"""
    ig_url = "https://www.instagram.com/reel/DX8x6XOtEqI/?stkn=MXZ3YWxibjJzejBtZg=="
    expected_embed_url = "https://www.instagram.com/p/DX8x6XOtEqI/embed/captioned/"
    expected_jina_url = f"https://r.jina.ai/{ig_url}"

    zh_login_html = (
        "<html><head><title>登入 • Instagram</title>"
        '<meta property="og:description" content="歡迎回到 Instagram。登入以查看親朋好友的更新動態。" />'
        "</head><body></body></html>"
    )

    # Case A: OG 登入牆 -> Embed 登入牆 -> Jina 403，嚴格各呼叫 1 次且 Jina 失敗後絕不重試 OG/Embed
    stream_urls_a = []

    def _dispatch_stream_a(method, url, *args, **kwargs):
        stream_urls_a.append(url)
        if url.startswith("https://r.jina.ai/"):
            return _make_stream_cm(403, "Blocked ASN")
        return _make_stream_cm(200, zh_login_html)

    mock_client = AsyncMock()
    mock_client.stream = MagicMock(side_effect=_dispatch_stream_a)

    with patch("services.web_search_engine.get_search_client", return_value=mock_client):
        result = await fetch_jina_reader(ig_url)

    assert result["status"] == "error"
    assert result["error_code"] == "READER_UNAVAILABLE"
    assert result["markdown"] == ""
    assert stream_urls_a == [ig_url, expected_embed_url, expected_jina_url]
    assert stream_urls_a.count(ig_url) == 1              # 原 OG URL 僅請求 1 次
    assert stream_urls_a.count(expected_embed_url) == 1  # Embed URL 僅請求 1 次
    assert stream_urls_a.count(expected_jina_url) == 1   # Jina 僅呼叫 1 次且失敗後不重打 OG/Embed

    # Case B: Jina 回傳 200 但內容仍為英文 Login Wall
    en_login_md = "# Login • Instagram\n\nWelcome back to Instagram. Sign in to check out what your friends are sharing."
    stream_urls_b = []

    def _dispatch_stream_b(method, url, *args, **kwargs):
        stream_urls_b.append(url)
        if url.startswith("https://r.jina.ai/"):
            return _make_stream_cm(200, en_login_md)
        return _make_stream_cm(200, zh_login_html)

    mock_client_en = AsyncMock()
    mock_client_en.stream = MagicMock(side_effect=_dispatch_stream_b)

    with patch("services.web_search_engine.get_search_client", return_value=mock_client_en):
        res_login = await fetch_jina_reader(ig_url)

    assert res_login["status"] == "error"
    assert res_login["error_code"] == "LOGIN_WALL"
    assert res_login["markdown"] == ""
    assert stream_urls_b == [ig_url, expected_embed_url, expected_jina_url]

    # Benign control: 一般美食部落格提到 Instagram 不應被誤判為登入牆
    blog_resp = MagicMock(spec=httpx.Response)
    blog_resp.status_code = 200
    blog_resp.text = "# 大阪燒肉推薦\n\n在 Instagram 上爆紅的焼肉エイト，歡迎造訪。"

    mock_client_blog = AsyncMock()
    mock_client_blog.get.return_value = blog_resp

    with patch("services.web_search_engine.get_search_client", return_value=mock_client_blog):
        res_blog = await fetch_jina_reader("https://example.com/osaka-bbq")

    assert res_blog["status"] == "success"
    assert "焼肉エイト" in res_blog["markdown"]
