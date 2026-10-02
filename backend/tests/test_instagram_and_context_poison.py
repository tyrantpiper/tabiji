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
    """驗證 Instagram Reel 網址能透過 OpenGraph 取得真實大阪燒肉貼文內容"""
    ig_url = "https://www.instagram.com/reel/DX8x6XOtEqI/?stkn=MXZ3YWxibjJzejBtZg=="
    result = await fetch_jina_reader(ig_url)

    assert result["status"] == "success", f"Result status failed: {result}"
    markdown = result.get("markdown", "")
    assert "焼肉エイト" in markdown or "燒肉" in markdown or "大阪" in markdown, (
        f"Real Instagram post content not found in markdown: {markdown[:300]}"
    )
