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


@pytest.mark.asyncio
async def test_instagram_reel_opengraph_fallback():
    """驗證 Instagram Reel 網址能透過 OpenGraph 確定性抽取貼文內容（不依賴 CI 外網連線）"""
    ig_url = "https://www.instagram.com/reel/DX8x6XOtEqI/?stkn=MXZ3YWxibjJzejBtZg=="
    og_resp = MagicMock(spec=httpx.Response)
    og_resp.status_code = 200
    og_resp.text = (
        "<html><head>"
        '<meta property="og:title" content="大阪難波超人氣燒肉 焼肉エイト" />'
        '<meta property="og:site_name" content="Instagram" />'
        '<meta property="og:description" content="大阪燒肉推薦：焼肉エイト 黑毛和牛" />'
        "</head></html>"
    )

    mock_client = AsyncMock()
    mock_client.get.return_value = og_resp

    with patch("services.web_search_engine.get_search_client", return_value=mock_client):
        result = await fetch_jina_reader(ig_url)

    assert result["status"] == "success", f"Result status failed: {result}"
    markdown = result.get("markdown", "")
    assert "焼肉エイト" in markdown or "燒肉" in markdown or "大阪" in markdown, (
        f"Instagram post content not found in markdown: {markdown[:300]}"
    )


@pytest.mark.asyncio
async def test_instagram_login_wall_rejected_and_degrades_cleanly():
    """驗證遭遇 IG 登入牆（中/英文）與 Jina 阻擋時，不回傳偽陽性 success 並可優雅降級"""
    ig_url = "https://www.instagram.com/reel/DX8x6XOtEqI/?stkn=MXZ3YWxibjJzejBtZg=="

    zh_login_resp = MagicMock(spec=httpx.Response)
    zh_login_resp.status_code = 200
    zh_login_resp.text = (
        "<html><head><title>登入 • Instagram</title>"
        '<meta property="og:description" content="歡迎回到 Instagram。登入以查看親朋好友的更新動態。" />'
        "</head><body></body></html>"
    )

    jina_403_resp = MagicMock(spec=httpx.Response)
    jina_403_resp.status_code = 403
    jina_403_resp.text = "Blocked ASN"

    mock_client = AsyncMock()
    mock_client.get.side_effect = [zh_login_resp, jina_403_resp]

    with patch("services.web_search_engine.get_search_client", return_value=mock_client):
        result = await fetch_jina_reader(ig_url)

    assert result["status"] == "error"
    assert result["error_code"] == "READER_UNAVAILABLE"
    assert result["markdown"] == ""
    assert mock_client.get.await_count == 2  # OpenGraph 不應重複請求兩次

    # Case B: Jina 回傳 200 但內容仍為英文 Login Wall
    en_login_resp = MagicMock(spec=httpx.Response)
    en_login_resp.status_code = 200
    en_login_resp.text = "# Login • Instagram\n\nWelcome back to Instagram. Sign in to check out what your friends are sharing."

    mock_client_en = AsyncMock()
    mock_client_en.get.side_effect = [zh_login_resp, en_login_resp]

    with patch("services.web_search_engine.get_search_client", return_value=mock_client_en):
        res_login = await fetch_jina_reader(ig_url)

    assert res_login["status"] == "error"
    assert res_login["error_code"] == "LOGIN_WALL"
    assert res_login["markdown"] == ""

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
