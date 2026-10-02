"""
Intent & Dynamic Tool Router (Hybrid Two-Stage)
-----------------------------------------------
Stage 1: 0ms 確定性正則快篩 (問候、記帳、新增行程、移除行程、健檢、複合)
Stage 2: 31B 工作馬極速語意前置分類 (1.0s 超時平滑降級)
"""

import re
import json
import asyncio
from typing import Tuple, List, Optional
from google.genai import types

from services.model_manager import (
    ADD_ITINERARY_TOOL,
    REMOVE_ITINERARY_TOOL,
    EXPENSE_TOOL,
    SEARCH_TOOLS,
    NEURAL_LINK_TOOLS,
    ALL_CHAT_TOOLS,
    call_extraction_server,
    detect_diagnosis_intent,
)

# ═══════════════════════════════════════════════════════════════
# ⚡ Stage 1: Fast-Path 確定性正則規則庫 (0ms)
# ═══════════════════════════════════════════════════════════════

GREETING_PATTERN = re.compile(
    r"^[\s]*(你好|您好|哈囉|hello|hi|hey|早安|午安|晚安|嗨|嗨嗨|謝謝(你|您)?|感謝(你|您)?|多謝(你|您)?|感恩|thx|thanks|3q)[\s\!！\?？\.\~]*$",
    re.IGNORECASE
)

REMOVE_PATTERN = re.compile(
    r"(刪除|移除|拿掉|取消|不要去|不要排|從行程.*(刪|拿|移除)|把.*(刪掉|移除|拿掉|取消))",
    re.IGNORECASE
)

# 💰 全球法定貨幣與花費記帳正則 (支援 JPY, TWD, USD, EUR, GBP, KRW, THB, SGD, AUD, CAD, HKD, VND, RMB 等)
EXPENSE_PATTERN = re.compile(
    r"(\b\d+[\.,]?\d*\s*(日圓|日幣|円|twd|nt\$|台幣|塊|元|usd|dollars?|美金|美元|jpy|eur|euros?|歐元|歐幣|gbp|pounds?|英鎊|krw|won|韓元|韓幣|thb|baht|泰銖|泰幣|sgd|新幣|星幣|aud|澳幣|澳元|cad|加幣|加元|hkd|港幣|港元|vnd|越南盾|越盾|盾|rmb|cny|人民幣|€|£|₩|฿|\$)\b|(記帳|花了|買了|花費|消費|付了|餐費|門票費|車資|住宿費|機票費|船票))",
    re.IGNORECASE
)

ITINERARY_PATTERN = re.compile(
    r"(排進|加到|加進|排入|加入行程|安排到|排在|加一個|Day\s*\d+|第\s*\d+\s*天|幫我排|想去|推薦.*景點.*排)",
    re.IGNORECASE
)

# 🌐 2026 即時聯網搜尋與網址解析快篩正則 (涵蓋主動搜尋動作詞、即時資訊、旅遊推薦與美食探索需求)
SEARCH_PATTERN = re.compile(
    r"(搜索|搜尋|上網查|查一下|幫我查|查看看|查詢|找一下|找找|google|谷歌|聯網|網路搜索|網路搜尋|"
    r"最新|即時|新聞|今天|明天|這週|這週末|天氣|降雨|幾點開|幾點關|營業時間|公休|休館|門票|票價|官網|預約|排隊|交通|怎麼去|轉乘|https?://|"
    r"推薦|私房|隱藏版|必吃|必去|必買|必訪|必看|老饕|小吃|美食|在地人|當地人|在地美食|外國旅客|背包客|好不好吃|好玩嗎|好吃|好玩|好逛|熱門|評價|評分|看法|攻略|指南|夜市|伴手禮|名產|特產|拉麵|燒肉|壽司|居酒屋|咖啡廳|早午餐)",
    re.IGNORECASE
)

CHAT_INTENT_PROMPT = """分析使用者在旅遊 App 中的對話意圖，輸出純 JSON (不要任何 markdown)：
{{
  "intent": "chat|itinerary|remove_itinerary|expense|composite|diagnosis|search"
}}

意圖定義：
- chat: 一般諮詢、閒聊、文化景點問答
- itinerary: 要求新增、推薦並安排景點至行程
- remove_itinerary: 要求刪除、取消或拿掉行程中的景點/活動
- expense: 記錄花費、記帳、消費金額
- composite: 同時包含排程與花費記帳
- diagnosis: 詢問行程是否順暢、合理性健檢
- search: 詢問即時資訊、最新消息、官網營業狀態、票價、天氣或提供外部網址

使用者訊息：「{message}」
"""


def _fast_path_classify(message: str) -> Optional[str]:
    """0ms 確定性正則快篩"""
    trimmed = message.strip()
    if not trimmed:
        return "CHAT"

    # 🛡️ 解除上下文污染：若傳入字串帶有 <user_input_{salt}>...</user_input_{salt}>，優先提取真實輸入
    user_input_match = re.search(r"<user_input_[^>]+>\s*(.*?)\s*</user_input_[^>]+>", trimmed, re.DOTALL)
    if user_input_match:
        trimmed = user_input_match.group(1).strip()
        if not trimmed:
            return "CHAT"

    # 1. 外部網址 (直接進入 SEARCH / 網頁精讀)
    if "http://" in trimmed or "https://" in trimmed:
        return "SEARCH"

    # 2. 短問候語 (短路為 CHAT，完全卸載卡片工具以防幻覺)
    if len(trimmed) <= 8 and GREETING_PATTERN.match(trimmed):
        return "CHAT"

    # 3. 優先檢查移除行程 (避免「把淺草寺移除」被誤判為行程新增)
    if REMOVE_PATTERN.search(trimmed):
        return "REMOVE_ITINERARY"

    # 4. 主動搜尋動作詞檢測 (搜索、搜尋、上網查、查一下、google 等最優先攔截，避免「查這家好不好吃」被誤判為健檢)
    has_search_action = bool(re.search(
        r"(搜索|搜尋|上網查|查一下|幫我查|查看看|查詢|找一下|找找|google|谷歌|聯網|網路搜索|網路搜尋)",
        trimmed, re.IGNORECASE
    ))
    if has_search_action:
        return "SEARCH"

    # 5. 檢查診斷意圖
    if detect_diagnosis_intent(trimmed):
        return "DIAGNOSIS"

    # 6. 檢查記帳與行程意圖
    # 🛡️ 排除詢問價格之疑問句（如「多少錢」、「算貴嗎」、「預算」、「預估」），避免誤觸記帳
    is_price_inquiry = bool(re.search(r"(多少|幾|嗎|？|\?|預算|預估|貴不貴|貴嗎|划算嗎)", trimmed))
    has_expense = bool(EXPENSE_PATTERN.search(trimmed)) and not is_price_inquiry
    has_itinerary = bool(ITINERARY_PATTERN.search(trimmed))

    if has_expense and has_itinerary:
        return "COMPOSITE"
    if has_expense:
        return "EXPENSE"
    if has_itinerary:
        return "ITINERARY"

    # 7. 檢查即時名詞搜尋 (營業時間、公休、幾點開、門票等即時資訊需求)
    if SEARCH_PATTERN.search(trimmed):
        return "SEARCH"

    return None


async def _workhorse_classify(message: str, api_key: Optional[str] = None) -> str:
    """Stage 2: 31B 工作馬極速語意前置分類 (帶 1.0s 硬性超時保護)"""
    user_input_match = re.search(r"<user_input_[^>]+>\s*(.*?)\s*</user_input_[^>]+>", message, re.DOTALL)
    eval_text = user_input_match.group(1).strip() if user_input_match else message
    prompt = CHAT_INTENT_PROMPT.format(message=eval_text[:200])
    try:
        # 使用 1.0 秒超時保護，避免網路卡頓拖累對話首包時間
        raw_text = await asyncio.wait_for(
            call_extraction_server(prompt, intent_type="INTENT_PARSE", api_key=api_key),
            timeout=1.0
        )
        match = re.search(r'\{[\s\S]*\}', raw_text)
        if match:
            data = json.loads(match.group())
            intent = data.get("intent", "").lower()
            intent_map = {
                "chat": "CHAT",
                "itinerary": "ITINERARY",
                "remove_itinerary": "REMOVE_ITINERARY",
                "expense": "EXPENSE",
                "composite": "COMPOSITE",
                "diagnosis": "DIAGNOSIS",
                "search": "SEARCH",
            }
            if intent in intent_map:
                return intent_map[intent]
    except asyncio.TimeoutError:
        print("⏱️ [IntentRouter] 31B 工作馬分類逾時 (>1.0s)，平滑降級為 CHAT")
    except Exception as e:
        print(f"⚠️ [IntentRouter] 31B 工作馬分類失敗: {e}")

    return "CHAT"


async def classify_chat_intent(
    message: str,
    api_key: Optional[str] = None
) -> Tuple[str, List[types.Tool]]:
    """
    統一意圖分流進入點
    Returns:
        (intent_type, tools_to_mount)
    """
    # Stage 1: 0ms 正則快線
    intent = _fast_path_classify(message)

    # Stage 2: 模糊語意啟動 31B 工作馬
    if not intent:
        intent = await _workhorse_classify(message, api_key=api_key)

    # 動態工具綁定映射表 (保持原有單元測試契約相容)
    tool_map = {
        "SEARCH": ALL_CHAT_TOOLS,          # 🌐 搜尋/精讀 + 神經連結 (排程/刪除/記帳) 全具備
        "REMOVE_ITINERARY": [REMOVE_ITINERARY_TOOL],
        "ITINERARY": [ADD_ITINERARY_TOOL],
        "EXPENSE": [EXPENSE_TOOL],
        "COMPOSITE": [ADD_ITINERARY_TOOL, EXPENSE_TOOL],
        "DIAGNOSIS": [ADD_ITINERARY_TOOL],
        "CHAT": [],                        # 🛡️ 純打招呼 (你好/謝謝) 卸載工具，防禦幻覺卡片
    }

    selected_tools = tool_map.get(intent, [])
    try:
        print(f"🧭 [IntentRouter] 命中意圖: {intent} (掛載工具數: {len(selected_tools)})")
    except Exception:
        pass
    return intent, selected_tools
