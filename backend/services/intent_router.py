"""
Intent & Dynamic Tool Router (Hybrid Two-Stage)
-----------------------------------------------
Stage 1: 0ms 確定性正則快篩 (問候、記帳、新增行程、移除行程、健檢、複合)
Stage 2: 31B 工作馬極速語意前置分類 (1.0s 超時平滑降級)
"""

from collections.abc import Mapping
import inspect
import os
import re
import json
import asyncio
from typing import Tuple, List, Optional, Dict, Any
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
    get_cached_client,
    _MODEL_API_ERRORS,
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
    r"(\b(?:remove|delete|cancel|drop|take[ \t]{0,3}off)\b|刪除|移除|拿掉|取消|不要去|不要排|從行程[^\n]{0,80}(?:刪|拿)|把[^把\n]{0,120}(?:刪掉|移除|拿掉|取消))",
    re.IGNORECASE
)

# 💰 全球法定貨幣與花費記帳正則 (支援 JPY, TWD, USD, EUR, GBP, KRW, THB, SGD, AUD, CAD, HKD, VND, RMB 等，含中英動詞)
EXPENSE_PATTERN = re.compile(
    r"(\b\d{1,15}(?:[.,]\d{1,6}){0,4}[ \t]{0,4}(?:日圓|日幣|円|twd|nt\$|台幣|塊|元|usd|dollars?|美金|美元|jpy|eur|euros?|歐元|歐幣|gbp|pounds?|英鎊|krw|won|韓元|韓幣|thb|baht|泰銖|泰幣|sgd|新幣|星幣|aud|澳幣|澳元|cad|加幣|加元|hkd|港幣|港元|vnd|越南盾|越盾|盾|rmb|cny|人民幣|€|£|₩|฿|\$)\b|(\b(?:spent|bought|paid|cost|expense|record)\b|記帳|花了|買了|花費|消費|付了|餐費|門票費|車資|住宿費|機票費|船票))",
    re.IGNORECASE
)

ITINERARY_PATTERN = re.compile(
    r"(\b(?:add|put|schedule|plan|include)\b[^\n]{0,120}(?:day[ \t]{0,4}\d{1,3}|itinerary)\b|Day[ \t]{0,4}\d{1,3}|第[ \t]{0,4}\d{1,3}[ \t]{0,4}天|排進|加到|加進|排入|加入行程|安排到|排在|加一個|幫我排|想去|推薦[^\n]{0,60}景點[^排\n]{0,40}排)",
    re.IGNORECASE
)

# 🌐 2026 即時聯網搜尋與網址解析快篩正則 (混合漏斗：確定性搜尋與複合探索保留 0ms 快篩，寬鬆追問/詞彙交由 gemini-decision-1 仲裁)
SEARCH_PATTERN = re.compile(
    r"(\b(search|google|look\s*up|find|check|opening\s*hours?|ticket\s*price|weather)\b|"
    r"搜索|搜尋|上網查|查一下|幫我查|查看看|查詢|找一下|找找|谷歌|聯網|網路搜索|網路搜尋|"
    r"幾點開|幾點關|營業時間|公休|休館|門票|票價|官網|預約|降雨|怎麼去|轉乘|評分|https?://|"
    r"推薦.{0,120}(?:景點|餐廳|美食|小吃|拉麵|燒肉|壽司|居酒屋|咖啡廳|早午餐|私房|隱藏版|在地人|當地人|必吃|必去|必買)|"
    r"(?:有什麼|哪裡有).{0,80}(?:好吃|好玩|好逛|推薦|美食|早午餐|咖啡廳|景點)|"
    r"(?:外國旅客|在地人|當地人).{0,80}(?:評分|評價|推薦))",
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

# 🛡️ 系統合法前置與後置 Context 標記：涵蓋全庫所有系統脈絡包裝格式（非重疊有界正則，呼叫端先 lstrip 與 [:256] 切片防 O(N^3) ReDoS）
SYSTEM_PREFIX_ANCHOR_RE = re.compile(
    r"^(?:--- SYSTEM CONTEXT: (?:TEMPORAL & ITINERARY NEURAL AWARENESS|NEURAL ITINERARY CONNECTION \(SLIDING WINDOW\)|[A-Za-z0-9_]{1,40}(?: [A-Za-z0-9_-]{1,40}){0,8}) ---|--- USER PREFERENCES|【系統背景|【當前行程脈絡】|用戶詢問關於「|The user is asking about \"[^\"\n]{1,200}\"\.|User is asking about [\"「]|"
    r"📍 \*\*(?:附近|Nearby )|🔬 以下是來自維基百科|💰 \*\*(?:即時機票參考價格|Live Flight Fare Reference )|"
    r"\[系統即時解析外部網頁資訊|\[Live External Webpage Content \(Source: |\[SYSTEM REAL-TIME WEB PAGE ANALYSIS|\[系統提示：使用者上傳了一張圖片|\[System Notice: The uploaded image could not be parsed\]|\[SYSTEM HINT:|\[WEATHER\]|\[2026 Neural Weather\]|\[CURRENT TIME)"
)
SYSTEM_BOUNDARY_END_RE = re.compile(
    r"(?:--- END OF SYSTEM CONTEXT ---|(?<!-)-{20,}|用戶原始問題：|使用者需求：|Original question:|User's original question:|User [Rr]equest:)[ \t\r\n]{0,8}",
    re.DOTALL,
)
USER_INPUT_OPEN_TAG_RE = re.compile(r"<user_input_([a-zA-Z0-9_-]{1,64})>[ \t\r\n]{0,8}")
SYSTEM_ALLOWED_SUFFIX_RE = re.compile(
    r"^(?:$|📍 \*\*(?:附近|Nearby )|--- SYSTEM CONTEXT: (?:TEMPORAL & ITINERARY NEURAL AWARENESS|NEURAL ITINERARY CONNECTION \(SLIDING WINDOW\)) ---|--- USER PREFERENCES|💰 \*\*(?:即時機票參考價格|Live Flight Fare Reference )|"
    r"\[CURRENT TIME|\[WEATHER\]|請根據以上(?:即時資料|資料)回答用戶問題|(?:Please )?[Aa]nswer the user's question based on)"
)
SPOOFED_USER_TAG_RE = re.compile(r"</?user_input_[a-zA-Z0-9_-]{0,64}>")


def _is_valid_outer_trailing(trailing: str) -> bool:
    """驗證閉合標籤後方不含任何殘留 </user_input_ 標籤，且符合合法系統後綴或結尾"""
    if "</user_input_" in trailing:
        return False
    return bool(SYSTEM_ALLOWED_SUFFIX_RE.match(trailing.lstrip()[:256]))


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
    lstripped = bounded_raw.lstrip()
    extracted = bounded_raw

    if SYSTEM_PREFIX_ANCHOR_RE.match(lstripped[:256]):
        candidate_starts = [m.end() for m in SYSTEM_BOUNDARY_END_RE.finditer(bounded_raw)]
        if not candidate_starts:
            candidate_starts = [0]
        last_any_close = bounded_raw.rfind("</user_input_")
        last_open_start = -1
        missing_close_salts: set[str] = set()
        unclosed_fallback: Optional[str] = None
        for start_pos in candidate_starts:
            if start_pos <= last_open_start:
                continue
            open_match = USER_INPUT_OPEN_TAG_RE.search(bounded_raw, pos=start_pos)
            if not open_match:
                break
            last_open_start = open_match.start()
            body_start = open_match.end()
            if last_any_close < body_start:
                if unclosed_fallback is None:
                    unclosed_fallback = bounded_raw[body_start:]
                break
            outer_salt = open_match.group(1)
            close_tag = f"</user_input_{outer_salt}>"
            if outer_salt in missing_close_salts:
                abs_close_idx = -1
            else:
                abs_close_idx = bounded_raw.find(close_tag, body_start)
                if abs_close_idx == -1:
                    missing_close_salts.add(outer_salt)
            if abs_close_idx != -1:
                if abs_close_idx >= last_any_close:
                    trailing = bounded_raw[abs_close_idx + len(close_tag):]
                    if _is_valid_outer_trailing(trailing):
                        extracted = bounded_raw[body_start:abs_close_idx]
                        unclosed_fallback = None
                        break
            elif unclosed_fallback is None:
                unclosed_fallback = bounded_raw[body_start:]
        if unclosed_fallback is not None:
            extracted = unclosed_fallback
    else:
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


async def _decision_classify(
    message: str,
    api_key: Optional[str] = None,
    genai_client: Any = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """Stage 2a: gemini-decision-1 零輸出 Token 意圖分類 + 搜尋詞改寫判斷 (v1beta)"""
    eval_text = _extract_clean_user_text(message, max_len=500)
    if not eval_text:
        return "CHAT", {"source": "decision_empty", "needs_query_rewrite": False}

    effective_key = api_key or (os.getenv("GEMINI_API_KEY") or "").strip()
    if not effective_key and genai_client is None:
        return None, {"source": "no_key", "needs_query_rewrite": False}

    try:
        client = genai_client if genai_client is not None else get_cached_client(effective_key)
        decisions_res = getattr(getattr(client, "aio", None), "decisions", None)
        create_fn = getattr(decisions_res, "create", None)
        if not callable(create_fn):
            return None, {"source": "unsupported_client", "needs_query_rewrite": False}

        # 關閉 Speakeasy 預設 4 次退避重試 (最長 30s)，確保分類快速切換備援
        sdk_cfg = getattr(decisions_res, "sdk_configuration", None)
        rc = getattr(sdk_cfg, "retry_config", None)
        if rc is not None and type(rc).__name__ == "RetryConfig":
            rc.strategy = "none"
            rc.max_retries = 0
            rc.retry_connection_errors = False

        questions = {
            "intent": {
                "type": "choice",
                "instructions": "Classify the user's message intent inside a travel companion assistant.",
                "criteria": {
                    "chat": "Casual chitchat, emotional remark, greeting, praise, thanks, or general cultural trivia not needing live web search or tools",
                    "search": "Asking for live opening hours, latest news/updates, weather, prices/costs, restaurant/spot recommendations, or follow-up asking for more/latest info",
                    "itinerary": "Explicitly asking to add or schedule a specific place into the itinerary",
                    "remove_itinerary": "Asking to remove, delete, or cancel an itinerary activity",
                    "expense": "Explicitly asking to log or record a spent expense amount (excluding price inquiries)",
                    "composite": "Explicitly asking both to schedule an itinerary item and log an expense",
                    "diagnosis": "Asking to evaluate or diagnose itinerary route pacing or feasibility",
                    "other": "Ambiguous or does not clearly fit any category above",
                },
            },
            "needs_query_rewrite": {
                "type": "noul",
                "instructions": "True if the message is a follow-up, omits the place/city subject, or uses pronouns like this/that/latest info requiring conversation history to form a web search query.",
            },
        }

        maybe_coro = create_fn(
            model="gemini-decision-1",
            input=eval_text,
            questions=questions,
            api_version="v1beta",
            timeout=1.8,
        )
        if not inspect.isawaitable(maybe_coro):
            return None, {"source": "sync_mock_client", "needs_query_rewrite": False}

        resp = await asyncio.wait_for(maybe_coro, timeout=2.2)
        answers = getattr(resp, "answers", None)
        if not isinstance(answers, Mapping):
            return None, {"source": "invalid_decision_response", "needs_query_rewrite": False}
        intent_ans = answers.get("intent")
        rewrite_ans = answers.get("needs_query_rewrite")

        choice = str(getattr(intent_ans, "choice", "") or "").strip().lower()
        conf = float(getattr(intent_ans, "confidence", 0.0) or 0.0)
        rewrite_prob = float(getattr(rewrite_ans, "noul", 0.0) or 0.0)
        needs_query_rewrite = rewrite_prob >= 0.55

        intent_map = {
            "chat": "CHAT",
            "itinerary": "ITINERARY",
            "remove_itinerary": "REMOVE_ITINERARY",
            "expense": "EXPENSE",
            "composite": "COMPOSITE",
            "diagnosis": "DIAGNOSIS",
            "search": "SEARCH",
        }
        if choice == "other" or conf < 0.55 or choice not in intent_map:
            resolved = "SEARCH"
        else:
            resolved = intent_map[choice]

        meta = {
            "source": "gemini-decision-1",
            "choice": choice,
            "confidence": round(conf, 4),
            "needs_query_rewrite": needs_query_rewrite,
            "rewrite_prob": round(rewrite_prob, 4),
        }
        print(
            f"🧭 [IntentRouter] gemini-decision-1 命中: {resolved} "
            f"(choice={choice}, conf={conf:.3f}, needs_rewrite={needs_query_rewrite}/{rewrite_prob:.3f})"
        )
        return resolved, meta
    except asyncio.TimeoutError:
        print("⏱️ [IntentRouter] gemini-decision-1 逾時 (>2.2s)，切換 Stage 2b 備援分類")
    except _MODEL_API_ERRORS as e:
        print(f"⚠️ [IntentRouter] gemini-decision-1 API 異常 ({type(e).__name__})，切換 Stage 2b 備援分類")
    except Exception as e:
        print(f"⚠️ [IntentRouter] gemini-decision-1 未預期異常 ({type(e).__name__}: {e})，切換 Stage 2b 備援分類")

    return None, {"source": "decision_fallback", "needs_query_rewrite": False}


async def _workhorse_classify(message: str, api_key: Optional[str] = None) -> str:
    """Stage 2b: Flash-Lite 工作馬語意前置分類 (帶隱形字元清洗、單次 1.2s 與總預算 3.5s 超時保護)"""
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


async def classify_chat_intent_with_meta(
    message: str,
    api_key: Optional[str] = None,
    genai_client: Any = None,
) -> Tuple[str, List[types.Tool], Dict[str, Any]]:
    """
    統一意圖分流進入點（含 Decision 1 中繼訊號）
    Returns:
        (intent_type, tools_to_mount, meta)
    """
    # Stage 1: 0ms 正則快線
    intent = _fast_path_classify(message)
    meta: Dict[str, Any] = {"source": "fast_path", "needs_query_rewrite": False}

    # Stage 2a: 模糊語意優先啟動 gemini-decision-1
    if not intent:
        dec_intent, dec_meta = await _decision_classify(message, api_key=api_key, genai_client=genai_client)
        if dec_intent:
            intent = dec_intent
            meta = dec_meta
        else:
            # Stage 2b: Decision 1 不可用/逾時時平滑降級 Flash-Lite 工作馬
            intent = await _workhorse_classify(message, api_key=api_key)
            meta = {"source": "workhorse", "needs_query_rewrite": False}

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
        print(f"🧭 [IntentRouter] 命中意圖: {intent} (來源={meta.get('source')}, 掛載工具數: {len(selected_tools)})")
    except Exception:
        pass
    return intent, selected_tools, meta


async def classify_chat_intent(
    message: str,
    api_key: Optional[str] = None
) -> Tuple[str, List[types.Tool]]:
    """
    統一意圖分流進入點（向後相容雙元組簽名）
    Returns:
        (intent_type, tools_to_mount)
    """
    intent, selected_tools, _ = await classify_chat_intent_with_meta(message, api_key=api_key)
    return intent, selected_tools
