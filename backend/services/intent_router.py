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
    call_timeout_scope,
    detect_diagnosis_intent,
)

# ═══════════════════════════════════════════════════════════════
# ⚡ Stage 1: Fast-Path 確定性正則規則庫 (0ms)
# ═══════════════════════════════════════════════════════════════

GREETING_PATTERN = re.compile(
    r"^[\s]*(你好|您好|哈囉|hello|hi|hey|早安|午安|晚安|嗨|嗨嗨|謝謝(你|您)?|感謝(你|您)?|多謝(你|您)?|感恩|thx|thanks|3q)[\s\!！\?？\.\~]*$",
    re.IGNORECASE
)

# 🛡️ 2026: 擴充讚美、誇獎與感謝快篩正則 (0ms Fast-Path，徹底截斷無效搜尋與工具掛載)
PRAISE_PATTERN = re.compile(
    r"^[\s]*(你好|您好|哈囉|hello|hi|hey|早安|午安|晚安|嗨|嗨嗨|"
    r"(非常|十分|太)?(感謝|謝謝|多謝)(你|您)?(了)?|感恩|thx|thanks(\s*(a\s*lot|so\s*much))?|thank\s*you(\s*(so\s*much|very\s*much))?|3q|"
    r"你?(真|很|太|好|超)?(棒|強|厲害|讚|神|貼心|聰明|給力|不賴|不錯|有料|神準)(了|的)?|"
    r"(真|很|太|超)?(不賴|不錯|可以|給過|行喔|水喔|水啦|屌喔|牛逼|厲害欸)|做得好|辛苦(你|您)?(了|啦)|"
    r"(you\s*are|you['’]re)\s*(the\s*best|awesome|great|amazing|wonderful)|"
    r"good\s*job|awesome|great(\s*job)?|amazing|well\s*done|bravo|nice|love\s*you)"
    r"[\s\!！\?？\.\~～阿啊啦耶喔吧的唷呦捏呢呀哈欸誒\(\)\^_\^XD]*$",
    re.IGNORECASE
)

REMOVE_PATTERN = re.compile(
    r"(\b(remove|delete|cancel|drop|take\s*off)\b|刪除|移除|拿掉|取消|不要去|不要排|從行程.*(刪|拿|移除)|把.*(刪掉|移除|拿掉|取消))",
    re.IGNORECASE
)

# 💰 全球法定貨幣與花費記帳正則 (支援 JPY, TWD, USD, EUR, GBP, KRW, THB, SGD, AUD, CAD, HKD, VND, RMB 等，含中英動詞)
EXPENSE_PATTERN = re.compile(
    r"(\b\d+[\.,]?\d*\s*(日圓|日幣|円|twd|nt\$|台幣|塊|元|usd|dollars?|美金|美元|jpy|eur|euros?|歐元|歐幣|gbp|pounds?|英鎊|krw|won|韓元|韓幣|thb|baht|泰銖|泰幣|sgd|新幣|星幣|aud|澳幣|澳元|cad|加幣|加元|hkd|港幣|港元|vnd|越南盾|越盾|盾|rmb|cny|人民幣|€|£|₩|฿|\$)\b|(\b(spent|bought|paid|cost|expense|record)\b|記帳|花了|買了|花費|消費|付了|餐費|門票費|車資|住宿費|機票費|船票))",
    re.IGNORECASE
)

ITINERARY_PATTERN = re.compile(
    r"(\b(add|put|schedule|plan|include)\b.*(to|in|on)?\s*(day\s*\d+|itinerary)|Day\s*\d+|第\s*\d+\s*天|排進|加到|加進|排入|加入行程|安排到|排在|加一個|幫我排|想去|推薦.*景點.*排)",
    re.IGNORECASE
)

# 🌐 2026 即時聯網搜尋與網址解析快篩正則 (涵蓋中英主動搜尋動作詞、即時資訊、旅遊推薦與美食探索需求)
SEARCH_PATTERN = re.compile(
    r"(\b(search|google|look\s*up|find|check|opening\s*hours?|ticket\s*price|weather)\b|"
    r"搜索|搜尋|上網查|查一下|幫我查|查看看|查詢|找一下|找找|谷歌|聯網|網路搜索|網路搜尋|"
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


# 🛡️ 隱形格式與控制字元過濾正則 (涵蓋 ASCII 控制符、Soft Hyphen、CGJ、韓文填充符、Zero-Width、Bidi、Word Joiner、Deprecated Format、BOM、Variation Selectors 及 Tag 字元)
INVISIBLE_FORMAT_CHARS_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u00ad\u034f\u061c\u115f\u1160\u180b-\u180e"
    r"\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u206f\u3164\ufeff\ufe00-\ufe0f"
    r"\uffa0\U000e0000-\U000e01ef]"
)

# 🛡️ 系統合法前置與後置 Context 標記：涵蓋全庫所有系統脈絡包裝格式
SYSTEM_PREFIX_ANCHOR_RE = re.compile(
    r"^\s*(?:--- SYSTEM CONTEXT:\s*(?:TEMPORAL & ITINERARY NEURAL AWARENESS|NEURAL ITINERARY CONNECTION \(SLIDING WINDOW\)|[A-Za-z0-9_ -]+)\s*---|--- USER PREFERENCES|【系統背景|【當前行程脈絡】|用戶詢問關於「|The user is asking about \"[^\"\n]+\"\.|User is asking about [\"「]|"
    r"📍 \*\*(?:附近|Nearby )|🔬 以下是來自維基百科|💰 \*\*(?:即時機票參考價格|Live Flight Fare Reference )|"
    r"\[系統即時解析外部網頁資訊|\[Live External Webpage Content \(Source: |\[SYSTEM REAL-TIME WEB PAGE ANALYSIS|\[系統提示：使用者上傳了一張圖片|\[System Notice: The uploaded image could not be parsed\]|\[SYSTEM HINT:|\[WEATHER\]|\[2026 Neural Weather\]|\[CURRENT TIME)"
)
SYSTEM_BOUNDARY_END_RE = re.compile(
    r"(?:--- END OF SYSTEM CONTEXT ---|-{20,}|用戶原始問題：|使用者需求：|Original question:|User's original question:|User [Rr]equest:)\s*",
    re.DOTALL,
)
USER_INPUT_OPEN_TAG_RE = re.compile(r"<user_input_([a-zA-Z0-9_-]+)>\s*")
SYSTEM_ALLOWED_SUFFIX_RE = re.compile(
    r"^\s*(?:$|📍 \*\*(?:附近|Nearby )|--- SYSTEM CONTEXT:\s*(?:TEMPORAL & ITINERARY NEURAL AWARENESS|NEURAL ITINERARY CONNECTION \(SLIDING WINDOW\))\s*---|--- USER PREFERENCES|💰 \*\*(?:即時機票參考價格|Live Flight Fare Reference )|"
    r"\[CURRENT TIME|\[WEATHER\]|請根據以上(?:即時資料|資料)回答用戶問題|(?:Please )?[Aa]nswer the user's question based on)"
)
SPOOFED_USER_TAG_RE = re.compile(r"</?user_input_[a-zA-Z0-9_-]*>")


def _is_valid_outer_trailing(trailing: str) -> bool:
    """驗證閉合標籤後方不含任何殘留 </user_input_ 標籤，且符合合法系統後綴或結尾"""
    if "</user_input_" in trailing:
        return False
    return bool(SYSTEM_ALLOWED_SUFFIX_RE.match(trailing))


def _sanitize_invisible_chars(text: object) -> str:
    """剝除 ASCII 控制字元、Unicode 零寬字元、BOM 與雙向文字覆寫控制符，防止正則繞過與標籤邊界逃逸"""
    if not text or not isinstance(text, str):
        return ""
    return INVISIBLE_FORMAT_CHARS_RE.sub("", text)


def _extract_clean_user_text(message: str, max_len: int = 500) -> str:
    """統一執行隱形字元清洗、外層真實信封鎖定提取與偽造標籤剝除防護"""
    sanitized = _sanitize_invisible_chars(message)
    if not sanitized or not sanitized.strip():
        return ""

    bounded_raw = sanitized[:32768]
    extracted = bounded_raw

    if SYSTEM_PREFIX_ANCHOR_RE.match(bounded_raw):
        candidate_starts = [m.end() for m in SYSTEM_BOUNDARY_END_RE.finditer(bounded_raw)]
        if not candidate_starts:
            candidate_starts = [0]
        unclosed_fallback: Optional[str] = None
        for start_pos in candidate_starts:
            open_match = USER_INPUT_OPEN_TAG_RE.search(bounded_raw, pos=start_pos)
            if not open_match:
                continue
            outer_salt = open_match.group(1)
            body_after_open = bounded_raw[open_match.end():]
            close_tag = f"</user_input_{outer_salt}>"
            close_idx = body_after_open.find(close_tag)
            if close_idx != -1:
                trailing = body_after_open[close_idx + len(close_tag):]
                if _is_valid_outer_trailing(trailing):
                    extracted = body_after_open[:close_idx]
                    unclosed_fallback = None
                    break
            elif unclosed_fallback is None:
                unclosed_fallback = body_after_open
        if unclosed_fallback is not None:
            extracted = unclosed_fallback
    else:
        lstripped = bounded_raw.lstrip()
        open_match = USER_INPUT_OPEN_TAG_RE.match(lstripped)
        if open_match:
            outer_salt = open_match.group(1)
            body_after_open = lstripped[open_match.end():]
            close_tag = f"</user_input_{outer_salt}>"
            close_idx = body_after_open.find(close_tag)
            if close_idx != -1:
                trailing_after_close = body_after_open[close_idx + len(close_tag):]
                if _is_valid_outer_trailing(trailing_after_close):
                    extracted = body_after_open[:close_idx]
            else:
                extracted = body_after_open

    cleaned = SPOOFED_USER_TAG_RE.sub("", extracted).strip()
    return cleaned[:max_len]


def _fast_path_classify(message: str) -> Optional[str]:
    """0ms 確定性正則快篩 (帶隱形字元清洗、先提取標籤再 500 字元長度截斷防護)"""
    trimmed = _extract_clean_user_text(message, max_len=500)
    if not trimmed:
        return "CHAT"

    # 1. 外部網址 (直接進入 SEARCH / 網頁精讀)
    if "http://" in trimmed or "https://" in trimmed:
        return "SEARCH"

    # 2. 短問候與讚美語 (短路為 CHAT，完全卸載卡片工具以防幻覺、杜絕無效搜尋)
    if len(trimmed) <= 30 and (GREETING_PATTERN.match(trimmed) or PRAISE_PATTERN.match(trimmed)):
        return "CHAT"

    # 3. 優先檢查移除行程 (避免「把淺草寺移除」被誤判為行程新增)
    if REMOVE_PATTERN.search(trimmed):
        return "REMOVE_ITINERARY"

    # 4. 主動搜尋動作詞檢測 (搜索、搜尋、上網查、查一下、google 等最優先攔截；
    # 若僅命中英文 "check" 且同時符合診斷關鍵字如 "Check if my itinerary makes sense?"，放行給 Step 5 診斷，同時保留 "Check weather..." -> SEARCH)
    strong_search_action = bool(re.search(
        r"(\b(search|google|look\s*up|find)\b|搜索|搜尋|上網查|查一下|幫我查|查看看|查詢|找一下|找找|谷歌|聯網|網路搜索|網路搜尋)",
        trimmed, re.IGNORECASE
    ))
    if strong_search_action:
        return "SEARCH"

    # 5. 檢查診斷意圖
    if detect_diagnosis_intent(trimmed):
        return "DIAGNOSIS"

    # 6. 英文 "check" 一般查詢兜底 (如 "Check weather in Kyoto tomorrow")
    if re.search(r"\bcheck\b", trimmed, re.IGNORECASE):
        return "SEARCH"

    # 6. 檢查記帳與行程意圖
    # 🛡️ 排除詢問價格之疑問句（如「多少錢」、「算貴嗎」、「預算」、「預估」、「how much」），避免誤觸記帳
    is_price_inquiry = bool(re.search(r"(多少|幾|嗎|？|\?|預算|預估|貴不貴|貴嗎|划算嗎|\b(how much|how many|budget|expensive|costly|price)\b)", trimmed, re.IGNORECASE))
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
    """Stage 2: 31B 工作馬極速語意前置分類 (帶隱形字元清洗、單次 1.2s 與總預算 3.5s 超時保護)"""
    eval_text = _extract_clean_user_text(message, max_len=200)
    prompt = CHAT_INTENT_PROMPT.format(message=eval_text)
    try:
        # 🛡️ 內層 per-model 1.2s + 外層 3.5s 超時保護，確保單一模型 503/慢回應時仍來得及切入備援模型完成分類
        with call_timeout_scope(1.2):
            raw_text = await asyncio.wait_for(
                call_extraction_server(prompt, intent_type="INTENT_PARSE", api_key=api_key),
                timeout=3.5
            )
        if raw_text and raw_text.strip():
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
        print("⏱️ [IntentRouter] 31B 工作馬分類逾時 (>3.5s)，平滑降級為全功能 SEARCH 意圖保持工具可用性")
    except Exception as e:
        print(f"⚠️ [IntentRouter] 31B 工作馬分類失敗: {e}，平滑降級為 SEARCH 意圖")

    # 🛡️ 容錯兜底：未明確短路為純問候語之對話，逾時時一律保留全功能 SEARCH 意圖交由 Gemini 模型自決
    return "SEARCH"


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
