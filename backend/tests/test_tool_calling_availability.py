import pytest
from services.intent_router import classify_chat_intent
from services.model_manager import (
    ADD_ITINERARY_DECL,
    REMOVE_ITINERARY_DECL,
    ADD_EXPENSE_DECL,
    SEARCH_WEB_DECL,
    FETCH_WEBPAGE_DECL,
    NEURAL_LINK_TOOLS,
    ALL_CHAT_TOOLS
)


@pytest.mark.asyncio
async def test_add_itinerary_tool_always_available():
    """驗證非明確特定句式的加入行程要求，必須具備 add_itinerary_item 工具"""
    queries = [
        "這家燒肉看起來很棒，幫我加進去",
        "推薦的第二個景點幫我排到第一天",
        "好啊，那幫我排進去行程",
        "把晴空塔加進去"
    ]
    for q in queries:
        intent, tools = await classify_chat_intent(q)
        assert len(tools) > 0, f"Query '{q}' (intent={intent}) has no tools!"
        func_names = [f.name for t in tools for f in t.function_declarations]
        assert "add_itinerary_item" in func_names, (
            f"Query '{q}' (intent={intent}) missing 'add_itinerary_item' in {func_names}"
        )


@pytest.mark.asyncio
async def test_remove_itinerary_tool_always_available():
    """驗證移除行程要求，必須具備 remove_itinerary_item 工具"""
    queries = [
        "把剛剛的淺草寺刪掉",
        "不要去晴空塔了，幫我拿掉",
        "取消第三天的行程"
    ]
    for q in queries:
        intent, tools = await classify_chat_intent(q)
        assert len(tools) > 0, f"Query '{q}' (intent={intent}) has no tools!"
        func_names = [f.name for t in tools for f in t.function_declarations]
        assert "remove_itinerary_item" in func_names, (
            f"Query '{q}' (intent={intent}) missing 'remove_itinerary_item' in {func_names}"
        )


@pytest.mark.asyncio
async def test_search_intent_retains_itinerary_tools():
    """驗證搜尋意圖（例如傳入網址）時，依然保留加入/移除行程與記帳工具"""
    url_query = "https://www.instagram.com/reel/DX8x6XOtEqI/ 幫我看這家並排進行程"
    intent, tools = await classify_chat_intent(url_query)
    assert intent == "SEARCH", f"Expected SEARCH, got {intent}"
    func_names = [f.name for t in tools for f in t.function_declarations]
    assert "fetch_webpage" in func_names or "search_web" in func_names
    assert "add_itinerary_item" in func_names, "SEARCH intent must also retain add_itinerary_item!"


@pytest.mark.asyncio
async def test_pure_greeting_unloads_tools():
    """純問候語（你好、早安）必須卸載工具以防幻覺生成卡片"""
    greetings = ["你好", "早安", "哈囉", "嗨嗨", "謝謝你"]
    for g in greetings:
        intent, tools = await classify_chat_intent(g)
        assert len(tools) == 0, f"Greeting '{g}' should have 0 tools, got {len(tools)}"
