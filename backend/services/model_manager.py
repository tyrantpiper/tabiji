"""
Model Manager Service - Next-Gen Architecture v23.1
===================================================

Intelligent multi-tier routing with:
- Capability Registry: Chart-based enforcement (supports_schema, property_ordering)
- V23.1 Financial Nomenclature: subtotal_amount, total_amount, items
- Fail-Fast Policy: Immediate rejection of 401/403 errors
- Explicit Fallback: Seamless transition to Gemma 3 for non-strict tasks
- Async Lifecycle: Formal aclose() path for resource management
- Temperature Guard: Enforced 1.0 for Gemini 3
"""

import copy
import time
import os
import asyncio
import base64
import json
import re
import hashlib
import random
import contextlib
import weakref
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass
from google import genai
from google.genai import types, errors
try:
    from google.genai._gaos.lib import compat_errors as _compat_errors
    _MODEL_API_ERRORS = (errors.APIError, _compat_errors.APIError)
except ImportError:  # pragma: no cover
    _compat_errors = None
    _MODEL_API_ERRORS = (errors.APIError,)
from typing import Optional, List, Dict, Any, Union, Tuple, Iterator

# --- 路由策略 (從 ai_config 導入) ---
from utils.ai_config import (
    DAILY_ROUTING,
    HEAVY_ROUTING,
    EXTRACTION_ROUTING,
    GEOCODE_ROUTING,
    WORKHORSE_MODEL,
    WORKHORSE_MOE,
    WORKHORSE_PENULTIMATE,
    WORKHORSE_ROUTING,
)


# ═══════════════════════════════════════════════════════════════
# 🧩 Capability Registry (查表執法)
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ModelCaps:
    supports_schema: bool
    supports_tools: bool
    supports_media_resolution: bool
    supports_thinking: bool  # 🚀 v21.2: Gemini 3.x 與 Gemma 4 31B 支援思考等級控制
    supports_grounding: bool # 🚀 v26.4: Gemma 4 原生支援搜尋增強
    requires_property_ordering: bool
    allow_extraction_fallback: bool
    family: str  # "gemini" / "gemma"
    supported_thinking_levels: Optional[Tuple[str, ...]] = None


MODEL_CAPS: Dict[str, ModelCaps] = {
    "gemini-3.8-flash": ModelCaps(
        supports_schema=True,
        supports_tools=True,       # 🟢 啟用頂級神經連結能力
        supports_media_resolution=True,
        supports_thinking=True,    # 🚀 1,048,576 (1M) Tokens 超長上下文與長鏈推論
        supports_grounding=True,   # 🚀 Google Search & Maps Grounding
        requires_property_ordering=False,
        allow_extraction_fallback=True,
        family="gemini",
        supported_thinking_levels=("low", "medium", "high"),
    ),
    "gemini-3.7-flash": ModelCaps(
        supports_schema=True,
        supports_tools=True,       # 🟢 啟用頂級神經連結能力
        supports_media_resolution=True,
        supports_thinking=True,    # 🚀 64K 超長推論
        supports_grounding=True,   # 🚀 Google Search & Maps Grounding
        requires_property_ordering=False,
        allow_extraction_fallback=True,
        family="gemini",
    ),
    "gemini-3.5-flash-lite": ModelCaps(
        supports_schema=True,
        supports_tools=True,       # 🟢 啟用極速神經連結能力
        supports_media_resolution=False,
        supports_thinking=True,
        supports_grounding=True,   # 🚀 500 RPD Map Grounding & 1.5K Search Grounding
        requires_property_ordering=False,
        allow_extraction_fallback=True,
        family="gemini",
    ),
    "gemini-3.1-flash-lite": ModelCaps(
        supports_schema=True,
        supports_tools=True,       # 🟢 啟用神經連結能力
        supports_media_resolution=False,
        supports_thinking=True,
        supports_grounding=False,
        requires_property_ordering=False,
        allow_extraction_fallback=True,
        family="gemini",
    ),
    "gemini-3.6-flash": ModelCaps(
        supports_schema=True,
        supports_tools=True,
        supports_media_resolution=True,
        supports_thinking=True,
        supports_grounding=True,
        requires_property_ordering=False,
        allow_extraction_fallback=True,
        family="gemini",
    ),
    "gemini-3.5-flash": ModelCaps(
        supports_schema=True,
        supports_tools=True,       # 🟢 啟用頂級神經連結能力
        supports_media_resolution=True,
        supports_thinking=True,
        supports_grounding=False,
        requires_property_ordering=False,
        allow_extraction_fallback=True,
        family="gemini",
    ),
    "gemini-3-flash-preview": ModelCaps(
        supports_schema=True,
        supports_tools=False,      # 🛡️ 暫時禁用以防 429
        supports_media_resolution=True,
        supports_thinking=True,
        supports_grounding=False,
        requires_property_ordering=False,
        allow_extraction_fallback=True,
        family="gemini",
    ),
    "gemini-2.5-flash": ModelCaps(
        supports_schema=True,
        supports_tools=True,
        supports_media_resolution=False,
        supports_thinking=True,
        supports_grounding=False,
        requires_property_ordering=False,
        allow_extraction_fallback=True,
        family="gemini",
    ),
    "gemma-3-27b-it": ModelCaps(
        supports_schema=True,
        supports_tools=True,
        supports_media_resolution=False,
        supports_thinking=False,
        supports_grounding=False,
        requires_property_ordering=False,
        allow_extraction_fallback=False,
        family="gemma",
    ),
    "gemma-4-31b-it": ModelCaps(
        supports_schema=True,
        supports_tools=True,
        supports_media_resolution=True,
        supports_thinking=True,
        supports_grounding=False,
        requires_property_ordering=False,
        allow_extraction_fallback=False,
        family="gemma",
        supported_thinking_levels=("minimal", "high"),
    ),
    "gemma-4-26b-a4b-it": ModelCaps(
        supports_schema=True,
        supports_tools=True,
        supports_media_resolution=True,
        supports_thinking=True,
        supports_grounding=False,
        requires_property_ordering=False,
        allow_extraction_fallback=False,
        family="gemma",
        supported_thinking_levels=("minimal", "high"),
    ),
}

# 宣告 AI 可用的神經連結卡片 (Neural Link Tools)
# 🔒 必須使用 types.Tool(function_declarations=[...]) 包裝，裸列表會被 SDK 忽略

ADD_ITINERARY_DECL = types.FunctionDeclaration(
    name="add_itinerary_item",
    description="Add one or multiple points of interest to the user's itinerary for a specific day. Include as much detail as possible. When adding multiple places, use the 'items' array.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "day": types.Schema(type=types.Type.INTEGER, description="The day number (1-indexed)"),
            "place_name": types.Schema(type=types.Type.STRING, description="Name of the place"),
            "category": types.Schema(type=types.Type.STRING, description="Category: restaurant, attraction, hotel, transport, shopping, cafe, bar, park, museum, temple, etc."),
            "desc": types.Schema(type=types.Type.STRING, description="Brief description of the place (1-2 sentences)"),
            "lat": types.Schema(type=types.Type.NUMBER, description="Latitude coordinate of the place"),
            "lng": types.Schema(type=types.Type.NUMBER, description="Longitude coordinate of the place"),
            "time_slot": types.Schema(type=types.Type.STRING, description="Suggested visit time in HH:MM format (e.g., '10:00', '14:30')"),
            "duration": types.Schema(type=types.Type.STRING, description="Estimated visit duration (e.g., '1-2 hours', '30 min')"),
            "rating": types.Schema(type=types.Type.NUMBER, description="Place rating from 0.0 to 5.0 if known"),
            "estimated_cost": types.Schema(type=types.Type.INTEGER, description="Estimated cost in local currency"),
            "link_url": types.Schema(type=types.Type.STRING, description="Official website URL or relevant link for the place (e.g., 'https://www.senso-ji.jp/')"),
            "sub_items": types.Schema(
                type=types.Type.ARRAY,
                description="List of notable sub-items: recommended dishes for restaurants, must-see exhibits for museums, key shops for malls, etc.",
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "name": types.Schema(type=types.Type.STRING, description="Sub-item name (e.g., 'Tonkotsu Ramen', 'Mona Lisa')"),
                        "desc": types.Schema(type=types.Type.STRING, description="Brief note about this sub-item"),
                        "link": types.Schema(type=types.Type.STRING, description="URL for this sub-item if available"),
                    },
                    required=["name"]
                )
            ),
            "items": types.Schema(
                type=types.Type.ARRAY,
                description="List of POI items when adding multiple activities at once. Each object contains day, place_name, category, desc, lat, lng, time_slot, duration, rating, etc.",
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "day": types.Schema(type=types.Type.INTEGER, description="The day number (1-indexed)"),
                        "place_name": types.Schema(type=types.Type.STRING, description="Name of the place"),
                        "category": types.Schema(type=types.Type.STRING, description="Category: restaurant, attraction, etc."),
                        "desc": types.Schema(type=types.Type.STRING, description="Brief description"),
                        "lat": types.Schema(type=types.Type.NUMBER),
                        "lng": types.Schema(type=types.Type.NUMBER),
                        "time_slot": types.Schema(type=types.Type.STRING, description="Suggested visit time in HH:MM format"),
                        "duration": types.Schema(type=types.Type.STRING),
                        "rating": types.Schema(type=types.Type.NUMBER),
                        "estimated_cost": types.Schema(type=types.Type.INTEGER),
                        "link_url": types.Schema(type=types.Type.STRING),
                    },
                    required=["place_name"]
                )
            )
        }
    )
)

REMOVE_ITINERARY_DECL = types.FunctionDeclaration(
    name="remove_itinerary_item",
    description="Propose removing a specific activity or place from the user's current itinerary.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "place_name": types.Schema(type=types.Type.STRING, description="Name of the place or activity to remove"),
            "day": types.Schema(type=types.Type.INTEGER, description="Day number if specified by user (1-indexed)"),
            "item_id": types.Schema(type=types.Type.STRING, description="Item ID if known from conversation context"),
            "reason": types.Schema(type=types.Type.STRING, description="Brief reason for removal")
        },
        required=["place_name"]
    )
)

ADD_EXPENSE_DECL = types.FunctionDeclaration(
    name="add_expense",
    description="Record a confirmed expense or explicit logging request to the user's travel expense tracker. ONLY invoke when the user explicitly requests to record or log an expense (e.g., '記帳', '幫我記一筆', '花了xxx'). DO NOT invoke for price inquiries, general questions, or search requests.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "day": types.Schema(type=types.Type.INTEGER, description="The day number (1-indexed)"),
            "title": types.Schema(type=types.Type.STRING, description="Description of the expense"),
            "amount": types.Schema(type=types.Type.NUMBER, description="Amount in local currency (supports decimals)"),
            "currency": types.Schema(type=types.Type.STRING, description="Currency code (e.g., 'JPY', 'USD', 'TWD')"),
            "category": types.Schema(type=types.Type.STRING, description="Expense category: food, transport, accommodation, ticket, shopping, other"),
            "payment_method": types.Schema(type=types.Type.STRING, description="Payment method: cash, card, ic_card, other"),
            "notes": types.Schema(type=types.Type.STRING, description="Additional notes about the expense"),
            "items": types.Schema(
                type=types.Type.ARRAY,
                description="Itemized breakdown of the expense (e.g., individual dishes, tickets, products)",
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "original_name": types.Schema(type=types.Type.STRING, description="Item name in original language"),
                        "translated_name": types.Schema(type=types.Type.STRING, description="Item name translated to user's language"),
                        "amount": types.Schema(type=types.Type.NUMBER, description="Price of this item"),
                    },
                    required=["original_name", "amount"]
                )
            ),
        },
        required=["day", "title", "amount", "currency"]
    )
)

# 個別工具實例
ADD_ITINERARY_TOOL = types.Tool(function_declarations=[ADD_ITINERARY_DECL])
REMOVE_ITINERARY_TOOL = types.Tool(function_declarations=[REMOVE_ITINERARY_DECL])
EXPENSE_TOOL = types.Tool(function_declarations=[ADD_EXPENSE_DECL])

# 🛡️ 2026 Gemma 4 超扁平化工具宣告 (Depth=1，徹底杜絕巢狀 Schema 引發之 Google 500 錯誤)
ADD_ITINERARY_FLAT_DECL = types.FunctionDeclaration(
    name="add_itinerary_item",
    description="Add a single point of interest to the user's itinerary. To recommend multiple places, invoke this tool multiple times in parallel.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "day": types.Schema(type=types.Type.INTEGER, description="Day number (1-indexed)"),
            "place_name": types.Schema(type=types.Type.STRING, description="Exact name of the place"),
            "category": types.Schema(type=types.Type.STRING, description="Category: restaurant, attraction, cafe, park, museum, etc."),
            "desc": types.Schema(type=types.Type.STRING, description="Brief 1-2 sentence description"),
            "lat": types.Schema(type=types.Type.NUMBER, description="Latitude coordinate"),
            "lng": types.Schema(type=types.Type.NUMBER, description="Longitude coordinate"),
            "duration": types.Schema(type=types.Type.STRING, description="Estimated duration, e.g. '1-2 hours'"),
            "link_url": types.Schema(type=types.Type.STRING, description="Official website or reference URL"),
        },
        required=["place_name", "category"]
    )
)
ADD_ITINERARY_FLAT_TOOL = types.Tool(function_declarations=[ADD_ITINERARY_FLAT_DECL])

ADD_EXPENSE_FLAT_DECL = types.FunctionDeclaration(
    name="add_expense",
    description="Record a confirmed expense to the user's travel expense tracker.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "day": types.Schema(type=types.Type.INTEGER, description="The day number (1-indexed)"),
            "title": types.Schema(type=types.Type.STRING, description="Description of the expense"),
            "amount": types.Schema(type=types.Type.NUMBER, description="Amount in local currency"),
            "currency": types.Schema(type=types.Type.STRING, description="Currency code (e.g., 'JPY', 'USD', 'TWD')"),
            "category": types.Schema(type=types.Type.STRING, description="Expense category: food, transport, accommodation, ticket, shopping, other"),
            "payment_method": types.Schema(type=types.Type.STRING, description="Payment method: cash, card, ic_card, other"),
            "notes": types.Schema(type=types.Type.STRING, description="Additional notes about the expense"),
        },
        required=["day", "title", "amount", "currency"]
    )
)
ADD_EXPENSE_FLAT_TOOL = types.Tool(function_declarations=[ADD_EXPENSE_FLAT_DECL])

# 🌐 2026 零成本聯網搜尋與網頁閱讀工具宣告
SEARCH_WEB_DECL = types.FunctionDeclaration(
    name="search_web",
    description="Search the live internet for up-to-date travel information, real-time ticket prices, opening hours, weather, or recent news.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "query": types.Schema(
                type=types.Type.STRING,
                description="Search query terms (e.g., 'Tokyo Skytree opening hours', 'Shinjuku Gyoen weather today')."
            ),
            "site_filter": types.Schema(
                type=types.Type.STRING,
                description="Optional domain to restrict search to (e.g., 'tokyo-skytree.jp', 'tabelog.com')."
            )
        },
        required=["query"]
    )
)

FETCH_WEBPAGE_DECL = types.FunctionDeclaration(
    name="fetch_webpage",
    description="Read and extract clean markdown text from a specific web URL (official sites, blog posts, travel guides).",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "url": types.Schema(
                type=types.Type.STRING,
                description="The complete http/https URL to read."
            ),
            "wait_for_selector": types.Schema(
                type=types.Type.STRING,
                description="Optional CSS selector to wait for before extracting (useful for dynamic single-page applications)."
            ),
            "target_selector": types.Schema(
                type=types.Type.STRING,
                description="Optional CSS selector to narrow down extraction to a specific article or table container."
            )
        },
        required=["url"]
    )
)

SEARCH_WEB_TOOL = types.Tool(function_declarations=[SEARCH_WEB_DECL])
FETCH_WEBPAGE_TOOL = types.Tool(function_declarations=[FETCH_WEBPAGE_DECL])
SEARCH_TOOLS = [types.Tool(function_declarations=[SEARCH_WEB_DECL, FETCH_WEBPAGE_DECL])]

# 🌐 2026 世界時間查詢工具宣告 (Server-side ReAct)
GET_WORLD_TIME_DECL = types.FunctionDeclaration(
    name="get_world_time",
    description="Query current accurate time, date, and timezone for any specific global city, country, or timezone identifier. ONLY invoke when the user explicitly asks about time in an external city/country (e.g. '現在倫敦幾點？', '紐約時間').",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "query": types.Schema(
                type=types.Type.STRING,
                description="City name, country, or IANA timezone (e.g., 'London', 'New York', 'Paris', 'Europe/London')."
            )
        },
        required=["query"]
    )
)
GET_WORLD_TIME_TOOL = types.Tool(function_declarations=[GET_WORLD_TIME_DECL])

# 🌐 2026 空間感知地理查詢工具宣告 (基於 Photon + Overpass 雙軌韌性代理)
SEARCH_NEARBY_PLACES_DECL = types.FunctionDeclaration(
    name="search_nearby_places",
    description="Search real-world points of interest (restaurants, convenience stores, attractions, pharmacies) near a landmark, address, or coordinates. Use this to ground recommendations in factual spatial data.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "anchor_place": types.Schema(
                type=types.Type.STRING,
                description="Landmark, station, or address name (e.g., '淺草寺', '新宿車站', 'Tokyo Station')."
            ),
            "category": types.Schema(
                type=types.Type.STRING,
                description="Category of places: 'restaurant', 'cafe', 'convenience', 'pharmacy', 'attraction', 'supermarket', 'shopping'."
            ),
            "keyword": types.Schema(
                type=types.Type.STRING,
                description="Optional specific cuisine or item (e.g., '拉麵', '鰻魚飯', '藥妝', '抹茶')."
            ),
            "radius_meters": types.Schema(
                type=types.Type.INTEGER,
                description="Search radius in meters (default 500, max 1500)."
            )
        },
        required=["anchor_place"]
    )
)
SEARCH_NEARBY_PLACES_TOOL = types.Tool(function_declarations=[SEARCH_NEARBY_PLACES_DECL])

# 組合工具集 (維持既有引用相容)
NEURAL_LINK_TOOLS = [
    types.Tool(
        function_declarations=[
            ADD_ITINERARY_DECL,
            REMOVE_ITINERARY_DECL,
            ADD_EXPENSE_DECL,
        ]
    )
]

# 🌐 2026: 全功能神經連結 + 聯網工具集 (行程/刪除/記帳/搜尋/精讀/世界時間/地理感知一應俱全)
ALL_CHAT_TOOLS = [
    types.Tool(
        function_declarations=[
            ADD_ITINERARY_DECL,
            REMOVE_ITINERARY_DECL,
            ADD_EXPENSE_DECL,
            SEARCH_WEB_DECL,
            FETCH_WEBPAGE_DECL,
            GET_WORLD_TIME_DECL,
            SEARCH_NEARBY_PLACES_DECL,
        ]
    )
]

# 🌐 2026: 搜尋專屬工具集 (徹底排除 ADD_EXPENSE_DECL，杜絕搜尋態誤彈記帳卡片)
SEARCH_CHAT_TOOLS = [
    types.Tool(
        function_declarations=[
            ADD_ITINERARY_DECL,
            REMOVE_ITINERARY_DECL,
            SEARCH_WEB_DECL,
            FETCH_WEBPAGE_DECL,
            GET_WORLD_TIME_DECL,
            SEARCH_NEARBY_PLACES_DECL,
        ]
    )
]

# 意圖分群
INTENTS_REQUIRING_JSON = {"EXTRACTION", "PLANNING", "PARSE_MD", "POI_ENRICH", "MEMORY_EXTRACT"}
TOOL_REQUIRED_INTENTS = {"ITINERARY", "REMOVE_ITINERARY", "EXPENSE", "COMPOSITE"}
LOW_THINKING_SUPPRESSED_INTENTS = {
    "GEOCODE", "INTENT_PARSE", "SUMMARIZE", "POI_ENRICH", "POI_RECOMMEND",
    "MEMORY_EXTRACT", "VERIFY", "EXTRACTION", "PARSE_MD"
}
INTENTS_ALLOW_GEMMA_LAST_RESORT = {
    "PLANNING", "PARSE_MD", "SUMMARIZE", "POI_ENRICH", "POI_RECOMMEND",
    "MEMORY_EXTRACT", "DIAGNOSIS", "DAY_REVIEW", "CHAT", "GEOCODE",
    "ITINERARY", "REMOVE_ITINERARY", "EXPENSE", "COMPOSITE", "INTENT_PARSE", "SEARCH"
}


def _default_afc_disabled() -> types.AutomaticFunctionCallingConfig:
    return types.AutomaticFunctionCallingConfig(disable=True)


def _make_thinking_config(level: str, include_thoughts: bool = False) -> types.ThinkingConfig:
    return types.ThinkingConfig(include_thoughts=include_thoughts, thinking_level=level)


# 🛡️ 2026: 模型與意圖自適應多型工具工廠 (Polymorphic Tool Adapter)
def get_tools_for_model(model_name: str, intent_type: str = "CHAT") -> Optional[List[types.Tool]]:
    """依據模型家族與任務意圖，動態返回最佳多型工具組合"""
    caps = MODEL_CAPS.get(model_name)
    if not caps or not caps.supports_tools:
        return None

    # Gemma 家族：精準掛載單層超扁平化工具 (Depth=1)，絕不多塞無關或深層巢狀工具
    if caps.family == "gemma":
        if intent_type in ("ITINERARY", "SEARCH", "CHAT", "DIAGNOSIS"):
            return [types.Tool(function_declarations=[ADD_ITINERARY_FLAT_DECL])]
        elif intent_type == "EXPENSE":
            return [types.Tool(function_declarations=[ADD_EXPENSE_FLAT_DECL])]
        elif intent_type == "REMOVE_ITINERARY":
            return [types.Tool(function_declarations=[REMOVE_ITINERARY_DECL])]
        elif intent_type == "COMPOSITE":
            return [types.Tool(function_declarations=[ADD_ITINERARY_FLAT_DECL, ADD_EXPENSE_FLAT_DECL])]
        return None

    # Gemini 家族：享有完整 4 層巢狀批次能力
    if intent_type == "SEARCH":
        return SEARCH_CHAT_TOOLS
    elif intent_type == "REMOVE_ITINERARY":
        return [REMOVE_ITINERARY_TOOL]
    elif intent_type == "ITINERARY":
        return [ADD_ITINERARY_TOOL]
    elif intent_type == "EXPENSE":
        return [EXPENSE_TOOL]
    elif intent_type == "COMPOSITE":
        return [ADD_ITINERARY_TOOL, EXPENSE_TOOL]
    elif intent_type == "DIAGNOSIS":
        return [ADD_ITINERARY_TOOL]
    return NEURAL_LINK_TOOLS



# ═══════════════════════════════════════════════════════════════
# 🔄 Client Lifecycle (以 api_key 為隔離鍵)
# ═══════════════════════════════════════════════════════════════

MAX_CLIENT_CACHE_SIZE = 32
MODEL_CALL_TIMEOUT = 45.0
GEMMA_CALL_TIMEOUT = 35.0
PLANNING_CALL_TIMEOUT = 90.0
PLANNING_SSE_TIMEOUT = 120.0
RETIRED_CLIENT_CLOSE_DELAY = 150.0

_TIMEOUT_OVERRIDE_CTX: ContextVar[Optional[Union[str, float]]] = ContextVar(
    "_TIMEOUT_OVERRIDE_CTX", default=None
)
_client_cache: "OrderedDict[str, genai.Client]" = OrderedDict()
_sync_client_cache: "OrderedDict[str, genai.Client]" = OrderedDict()
_loop_client_caches: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, OrderedDict[str, genai.Client]]" = (
    weakref.WeakKeyDictionary()
)
_client_loop_refs: Dict[str, Tuple[Optional["weakref.ref[asyncio.AbstractEventLoop]"], bool]] = {}
_retired_clients: Dict[int, Tuple[genai.Client, Optional[asyncio.Task]]] = {}
_retired_loop_refs: Dict[int, Optional["weakref.ref[asyncio.AbstractEventLoop]"]] = {}


@contextlib.contextmanager
def call_timeout_scope(scope_or_seconds: Optional[Union[str, float]]) -> Iterator[None]:
    """在 async 任務上下文內切換逾時層級，無需更動既有多方 Mock 函式簽名。"""
    token = _TIMEOUT_OVERRIDE_CTX.set(scope_or_seconds)
    try:
        yield
    finally:
        _TIMEOUT_OVERRIDE_CTX.reset(token)


def _get_call_timeout(intent_type: str, model_name: Optional[str] = None) -> float:
    """雙軌逾時分級：SSE PLANNING=120s、非串流 PLANNING/PARSE_MD=90s、Gemma 4 上限 35s、其餘快速意圖=45s。"""
    override = _TIMEOUT_OVERRIDE_CTX.get()
    if isinstance(override, (int, float)) and override > 0:
        return float(override)
    if override == "PLANNING_SSE":
        base_timeout = PLANNING_SSE_TIMEOUT
    elif intent_type in ("PLANNING", "PARSE_MD"):
        base_timeout = PLANNING_CALL_TIMEOUT
    else:
        base_timeout = MODEL_CALL_TIMEOUT

    if model_name:
        caps = MODEL_CAPS.get(model_name)
        if caps and caps.family == "gemma":
            return min(base_timeout, GEMMA_CALL_TIMEOUT)
    return base_timeout


async def _close_retired_client_later(client_id: int, retired_client: genai.Client) -> None:
    try:
        await asyncio.sleep(RETIRED_CLIENT_CLOSE_DELAY)
        await retired_client.aio.aclose()
    except asyncio.CancelledError:
        raise
    except Exception:
        pass
    finally:
        _retired_clients.pop(client_id, None)
        _retired_loop_refs.pop(client_id, None)


def _close_client_sync_quietly(client: Any) -> None:
    close_fn = getattr(client, "close", None)
    if callable(close_fn):
        with contextlib.suppress(Exception):
            close_fn()


def _purge_closed_loop_entries() -> None:
    closed_loops = [loop for loop in list(_loop_client_caches.keys()) if loop.is_closed()]
    for dead_loop in closed_loops:
        dead_cache = _loop_client_caches.pop(dead_loop, None)
        if dead_cache:
            for dead_client in dead_cache.values():
                _close_client_sync_quietly(dead_client)

    dead_retired_ids = [
        cid for cid, loop_ref in list(_retired_loop_refs.items())
        if loop_ref is not None and (loop_ref() is None or loop_ref().is_closed())
    ]
    for cid in dead_retired_ids:
        _retired_loop_refs.pop(cid, None)
        retired_entry = _retired_clients.pop(cid, None)
        if retired_entry is not None:
            retired_client, task = retired_entry
            if task is not None and not task.done():
                with contextlib.suppress(Exception):
                    task.cancel()
            _close_client_sync_quietly(retired_client)


def get_cached_client(api_key: str) -> genai.Client:
    """取得或建立 genai.Client（以 (event_loop, api_key) 分桶隔離並保留同迴圈重用，LRU 上限淘汰採 150s 延遲關閉防切斷長串流）"""
    try:
        current_loop: Optional[asyncio.AbstractEventLoop] = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    _purge_closed_loop_entries()

    if current_loop is not None:
        target_cache = _loop_client_caches.get(current_loop)
        if target_cache is None:
            target_cache = OrderedDict()
            _loop_client_caches[current_loop] = target_cache
    else:
        target_cache = _sync_client_cache

    client = target_cache.get(api_key)
    if client is not None:
        target_cache.move_to_end(api_key)
    else:
        client = genai.Client(api_key=api_key)
        target_cache[api_key] = client
        while len(target_cache) > MAX_CLIENT_CACHE_SIZE:
            _, evicted = target_cache.popitem(last=False)
            client_id = id(evicted)
            if current_loop is not None:
                task = current_loop.create_task(_close_retired_client_later(client_id, evicted))
                _retired_clients[client_id] = (evicted, task)
                _retired_loop_refs[client_id] = weakref.ref(current_loop)
            else:
                _close_client_sync_quietly(evicted)

    # 同步暴露當前執行上下文的快取視圖，維持舊有診斷與測試契約相容性
    _client_cache.clear()
    _client_cache.update(target_cache)
    _client_loop_refs.clear()
    loop_ref_entry = (
        weakref.ref(current_loop) if current_loop is not None else None,
        current_loop is not None,
    )
    for k in target_cache:
        _client_loop_refs[k] = loop_ref_entry
    return client


async def close_all_cached_clients() -> None:
    """正式回收所有非同步連線資源 (含同步快取、各事件迴圈快取與 LRU 延遲淘汰待機連線)"""
    unique_clients: List[genai.Client] = []
    seen_ids = set()

    def _collect(c: Optional[genai.Client]) -> None:
        if c is not None and id(c) not in seen_ids:
            seen_ids.add(id(c))
            unique_clients.append(c)

    for c in _sync_client_cache.values():
        _collect(c)
    for lcache in list(_loop_client_caches.values()):
        for c in lcache.values():
            _collect(c)
    for c in _client_cache.values():
        _collect(c)

    _sync_client_cache.clear()
    _loop_client_caches.clear()
    _client_cache.clear()
    _client_loop_refs.clear()

    retired_entries = list(_retired_clients.values())
    _retired_clients.clear()
    _retired_loop_refs.clear()
    for retired_client, task in retired_entries:
        if task is not None and not task.done():
            task.cancel()
        _collect(retired_client)

    if unique_clients:
        print(f"🧹 Closing {len(unique_clients)} AI clients...")
        # 並發關閉，忽略已失效連線的報錯
        await asyncio.gather(*(c.aio.aclose() for c in unique_clients), return_exceptions=True)
        print("✅ AI Clients shutdown complete")


def __reset_client_cache_for_testing() -> None:
    """重置模組級 Client 快取與延遲淘汰任務，確保測試隔離。"""
    _sync_client_cache.clear()
    _loop_client_caches.clear()
    _client_cache.clear()
    _client_loop_refs.clear()
    for _, task in list(_retired_clients.values()):
        if task is not None and not task.done():
            task.cancel()
    _retired_clients.clear()
    _retired_loop_refs.clear()





# ═══════════════════════════════════════════════════════════════
# 🏭 Config Factory (根據意圖生成 GenerateContentConfig)
# ═══════════════════════════════════════════════════════════════

# --- 診斷意圖偵測關鍵字 ---
DIAGNOSIS_KEYWORDS = [
    "行程建議", "好不好", "順不順", "會不會太趕", "來得及嗎",
    "這樣排", "幫我看", "診斷", "健檢", "評估", "分析這個行程",
    "路線順嗎", "時間夠嗎", "會太累嗎", "能遍完嗎",
    "有什麼建議", "要調整嗎", "怎麼樣",
    # English diagnosis keywords (Bilingual support)
    "makes sense", "check itinerary", "review", "diagnosis", "checkup",
    "too rushed", "pacing", "suggestions", "feasible", "rate my trip",
    "is this route", "enough time", "too tiring", "any recommendations"
]


def detect_diagnosis_intent(message: str) -> bool:
    """偵測是否為行程診斷請求"""
    message_lower = message.lower()
    return any(kw in message_lower for kw in DIAGNOSIS_KEYWORDS)


# ═══════════════════════════════════════════════════════════════
# 🏭 Config Factory (主線化 JSON Schema)
# ═══════════════════════════════════════════════════════════════

def build_json_schema_for_intent(intent_type: str) -> Optional[Dict[str, Any]]:
    """意圖對應的結構化定義"""
    if intent_type == "EXTRACTION":
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "expense_date": {"type": "string"},
                "date": {"type": "string"},
                "currency": {"type": "string"},
                "subtotal_amount": {"type": "number"},
                "tax_amount": {"type": "number"},
                "tip_amount": {"type": "number"},
                "service_charge_amount": {"type": "number"},
                "discount_amount": {"type": "number"},
                "total_amount": {"type": "number"},
                "category": {"type": "string"},
                "notes": {"type": "string"},
                "diagnostics": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "message": {"type": "string"},
                    }
                },
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "original_name": {"type": "string"},
                            "translated_name": {"type": "string"},
                            "amount": {"type": "number"}
                        },
                        "required": ["original_name", "amount"]
                    }
                }
            },
            "required": ["title", "currency", "total_amount", "items"]
        }
    if intent_type == "PARSE_MD":
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "destination": {"type": "string"},
                "start_date": {"type": "string", "description": "ISO date string (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "ISO date string (YYYY-MM-DD)"},
                "currency": {"type": "string"},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "day_number": {"type": "integer"},
                            "time_slot": {"type": "string"},
                            "place_name": {"type": "string"},
                            "original_name": {"type": "string"},
                            "category": {"type": "string"},
                            "desc": {"type": "string"},
                            "tags": {"type": "array", "items": {"type": "string"}},
                            "lat": {"type": "number"},
                            "lng": {"type": "number"},
                            "link_url": {"type": "string"},
                            "is_highlight": {"type": "boolean"},
                            "sub_items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "checked": {"type": "boolean"},
                                        "desc": {"type": "string"},
                                        "link": {"type": "string"}
                                    },
                                    "required": ["name"]
                                }
                            },
                        },
                        "required": ["day_number", "place_name"]
                    }
                },
                "day_metadata": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "day_number": {"type": "integer"},
                            "notes": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "icon": {"type": "string"},
                                        "title": {"type": "string"},
                                        "item": {"type": "string"},
                                        "content": {"type": "string"},
                                    }
                                }
                            },
                            "costs": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "item": {"type": "string"},
                                        "amount": {"type": "string"}
                                    }
                                }
                            },
                            "tickets": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "price": {"type": "string"}
                                    }
                                }
                            },
                        },
                        "required": ["day_number"]
                    }
                },
                "ai_review": {"type": "string"},
            },
            "required": ["title", "items"],
        }
    if intent_type == "POI_ENRICH":
        return {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "must_try": {"type": "array", "items": {"type": "string"}},
                "rating": {"type": "number"},
                "business_status": {"type": "string"},
            },
            "required": ["summary"],
        }
    if intent_type == "MEMORY_EXTRACT":
        return {
            "type": "object",
            "properties": {
                "preferences": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string"},
                            "preference": {"type": "string"},
                        },
                        "required": ["category", "preference"],
                    }
                }
            },
            "required": ["preferences"],
        }
    if intent_type == "PLANNING":
        # 🆕 v28.7 Nested Per-Day Architecture (Hard Enforcement)
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "destination": {"type": "string"},
                "currency": {"type": "string"},
                "start_date": {"type": "string", "description": "ISO date string (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "ISO date string (YYYY-MM-DD)"},
                "days": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "day_number": {"type": "integer"},
                            "activities": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "time": {"type": "string", "description": "e.g. 08:30"},
                                        "place_name": {"type": "string"},
                                        "category": {"type": "string"},
                                        "desc": {"type": "string"},
                                        "lat": {"type": "number"},
                                        "lng": {"type": "number"},
                                        "tags": {"type": "array", "items": {"type": "string"}},
                                        "is_highlight": {"type": "boolean"},
                                        "sub_items": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "name": {"type": "string"},
                                                    "checked": {"type": "boolean"},
                                                    "desc": {"type": "string"},
                                                    "link": {"type": "string"}
                                                },
                                                "required": ["name"]
                                            }
                                        },
                                        "link_url": {"type": "string"}
                                    },
                                    "required": ["time", "place_name", "category"],
                                }
                            }
                        },
                        "required": ["day_number", "activities"]
                    }
                },
                "ai_review": {"type": "string"},
                "day_metadata": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "day_number": {"type": "integer"},
                            "notes": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "icon": {"type": "string"},
                                        "title": {"type": "string"},
                                        "item": {"type": "string"},
                                        "content": {"type": "string"}
                                    }
                                }
                            },
                            "costs": {"type": "array", "items": {"type": "object", "properties": {"item": {"type": "string"}, "amount": {"type": "string"}}}},
                            "tickets": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "price": {"type": "string"}}}}
                        },
                        "required": ["day_number"]
                    }
                }
            },
            "required": ["days"],
        }
    return None


def get_generation_config(intent_type: str) -> types.GenerateContentConfig:
    """Config 工廠 — 根據意圖類型生成對應配置"""
    afc_off = _default_afc_disabled()
    base_configs = {
        "PLANNING": types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=32768,  # 🚀 足額輸出空間，防止大地理跨度多日巢狀 JSON 被思考吞噬截斷
            thinking_config=_make_thinking_config("medium", include_thoughts=False),
            media_resolution="media_resolution_high",
            response_mime_type="application/json",
            automatic_function_calling=afc_off,
        ),
        "PARSE_MD": types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=32768,
            thinking_config=_make_thinking_config("low", include_thoughts=False),
            media_resolution="media_resolution_high",
            response_mime_type="application/json",
            automatic_function_calling=afc_off,
        ),
        "VERIFY": types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=1024,
            thinking_config=_make_thinking_config("minimal", include_thoughts=False),
            media_resolution="media_resolution_high",
            automatic_function_calling=afc_off,
        ),
        "DIAGNOSIS": types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=8192,  # 🚀 Maximize for deep analysis
            thinking_config=_make_thinking_config("low", include_thoughts=False),
            media_resolution="media_resolution_high",
            tools=NEURAL_LINK_TOOLS,  # 🆕 注入行程神經連結工具集
            automatic_function_calling=afc_off,
        ),
        "DAY_REVIEW": types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=8192,
            thinking_config=_make_thinking_config("low", include_thoughts=False),
            automatic_function_calling=afc_off,
        ),
        "EXTRACTION": types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=16384,  # 🚀 足額空間容納長收據多細項
            thinking_config=_make_thinking_config("minimal", include_thoughts=False),
            response_mime_type="application/json",
            automatic_function_calling=afc_off,
        ),
        "SUMMARIZE": types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=1024,
            thinking_config=_make_thinking_config("minimal", include_thoughts=False),
            automatic_function_calling=afc_off,
        ),
        "POI_ENRICH": types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=1024,
            thinking_config=_make_thinking_config("minimal", include_thoughts=False),
            response_mime_type="application/json",
            automatic_function_calling=afc_off,
        ),
        "POI_RECOMMEND": types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=1024,
            thinking_config=_make_thinking_config("minimal", include_thoughts=False),
            automatic_function_calling=afc_off,
        ),
        "MEMORY_EXTRACT": types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=1024,
            thinking_config=_make_thinking_config("minimal", include_thoughts=False),
            response_mime_type="application/json",
            automatic_function_calling=afc_off,
        ),
        "GEOCODE": types.GenerateContentConfig(
            temperature=0,
            max_output_tokens=256,
            thinking_config=_make_thinking_config("minimal", include_thoughts=False),
            automatic_function_calling=afc_off,
        ),
        "INTENT_PARSE": types.GenerateContentConfig(
            temperature=0,
            max_output_tokens=256,
            thinking_config=_make_thinking_config("minimal", include_thoughts=False),
            automatic_function_calling=afc_off,
        ),
        "ITINERARY": types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=4096,
            thinking_config=_make_thinking_config("low", include_thoughts=False),
            tools=[ADD_ITINERARY_TOOL],
            automatic_function_calling=afc_off,
        ),
        "REMOVE_ITINERARY": types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=4096,
            thinking_config=_make_thinking_config("low", include_thoughts=False),
            tools=[REMOVE_ITINERARY_TOOL],
            automatic_function_calling=afc_off,
        ),
        "EXPENSE": types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=4096,
            thinking_config=_make_thinking_config("low", include_thoughts=False),
            tools=[EXPENSE_TOOL],
            automatic_function_calling=afc_off,
        ),
        "COMPOSITE": types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=4096,
            thinking_config=_make_thinking_config("low", include_thoughts=False),
            tools=[ADD_ITINERARY_TOOL, EXPENSE_TOOL],
            automatic_function_calling=afc_off,
        ),
        "CHAT": types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=4096,
            thinking_config=_make_thinking_config("low", include_thoughts=False),
            automatic_function_calling=afc_off,
        ),
        "SEARCH": types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=4096,
            thinking_config=_make_thinking_config("low", include_thoughts=False),
            automatic_function_calling=afc_off,
        ),
    }

    config = base_configs.get(
        intent_type,
        types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=2048,
            thinking_config=_make_thinking_config("low", include_thoughts=False),
            automatic_function_calling=afc_off,
        ),
    )

    # 🚀 主線化 Structured Output
    if intent_type in INTENTS_REQUIRING_JSON and intent_type != "CHAT":
        schema = build_json_schema_for_intent(intent_type)
        if schema:
            config.response_mime_type = "application/json"
            config.response_json_schema = schema

    return config


# ═══════════════════════════════════════════════════════════════
# 🛡️ Core: Sanitizer (查表執行配置淨化)
# ═══════════════════════════════════════════════════════════════

def _extract_thinking_level_str(level_val: Any) -> str:
    if level_val is None:
        return ""
    if hasattr(level_val, "value"):
        level_val = level_val.value
    s = str(level_val).strip().lower()
    if s in ("thinking_level_unspecified", "unspecified", "none"):
        return ""
    if "." in s:
        s = s.rsplit(".", 1)[-1]
    return s


def _normalize_thinking_config_for_caps(
    tc: Optional[types.ThinkingConfig],
    model_name: str,
    intent_type: str,
    caps: ModelCaps,
) -> Optional[types.ThinkingConfig]:
    """依模型家族精準校正 thinking_config，杜絕 Gemini 2.5 動態 -1 / Gemini 3 / Gemma 4 預設過度思考或混用 thinking_budget。"""
    if not caps.supports_thinking:
        return None

    is_low_suppressed = intent_type in LOW_THINKING_SUPPRESSED_INTENTS
    is_gemini25 = (caps.family == "gemini" and model_name.startswith("gemini-2.5"))
    if is_gemini25:
        if tc is None:
            if is_low_suppressed:
                return types.ThinkingConfig(include_thoughts=False, thinking_budget=0)
            return None
        requested_level = _extract_thinking_level_str(getattr(tc, "thinking_level", None))
        budget = getattr(tc, "thinking_budget", None)
        include_thoughts = False if is_low_suppressed else bool(getattr(tc, "include_thoughts", False))
        if is_low_suppressed:
            budget = 0
        elif budget is None and requested_level == "minimal":
            budget = 0
        if budget is not None or include_thoughts:
            return types.ThinkingConfig(
                include_thoughts=include_thoughts,
                thinking_budget=budget,
            )
        return None

    is_gemini3_or_gemma4 = (
        (caps.family == "gemini" and model_name.startswith("gemini-3"))
        or model_name.startswith("gemma-4")
    )

    # Gemma 4 31B 若不傳 thinking_config，API 會預設啟用深度思考！必須顯式指定 level
    if tc is None:
        if caps.family == "gemma" or is_low_suppressed:
            requested_level = "minimal"
            include_thoughts = False
            budget = None
        else:
            return None
    else:
        requested_level = _extract_thinking_level_str(getattr(tc, "thinking_level", None))
        include_thoughts = bool(getattr(tc, "include_thoughts", False))
        budget = getattr(tc, "thinking_budget", None)

    if is_low_suppressed:
        include_thoughts = False
        if not requested_level or requested_level in ("medium", "high"):
            requested_level = "minimal"

    if not requested_level:
        requested_level = "minimal" if caps.family == "gemma" else "low"

    allowed = caps.supported_thinking_levels
    if allowed:
        allowed_lower = tuple(lvl.lower() for lvl in allowed)
        if allowed_lower == ("low", "high"):
            if requested_level in ("minimal", "medium", "low"):
                requested_level = "low"
            else:
                requested_level = "high"
        elif allowed_lower == ("minimal", "high"):
            if requested_level in ("minimal", "low", "medium"):
                requested_level = "minimal"
            else:
                requested_level = "high"
        elif requested_level not in allowed_lower:
            if "minimal" in allowed_lower:
                requested_level = "minimal"
            elif "low" in allowed_lower:
                requested_level = "low"
            else:
                requested_level = allowed_lower[0]

    if is_gemini3_or_gemma4:
        budget = None

    return types.ThinkingConfig(
        include_thoughts=include_thoughts,
        thinking_level=requested_level,
        thinking_budget=budget,
    )


def sanitize_config_for_model(
    config: types.GenerateContentConfig,
    model_name: str,
    intent_type: str,
    explicit_grounding: bool = False,
) -> types.GenerateContentConfig:
    """根據模型能力表 (MODEL_CAPS) 淨化配置"""
    safe = copy.deepcopy(config)
    caps = MODEL_CAPS.get(model_name)

    # 全系統強制停用 Google GenAI SDK 自動遠端工具迴圈 (AFC)
    if getattr(safe, "automatic_function_calling", None) is None:
        safe.automatic_function_calling = _default_afc_disabled()

    if not caps:
        lower_name = (model_name or "").lower()
        tc = getattr(safe, "thinking_config", None)
        if lower_name.startswith(("gemini-3", "gemma-4")):
            if tc is not None:
                lvl = _extract_thinking_level_str(getattr(tc, "thinking_level", None))
                inc = False if intent_type in LOW_THINKING_SUPPRESSED_INTENTS else bool(getattr(tc, "include_thoughts", False))
                if intent_type in LOW_THINKING_SUPPRESSED_INTENTS and (not lvl or lvl in ("medium", "high")):
                    lvl = "minimal"
                elif not lvl:
                    lvl = "minimal" if lower_name.startswith("gemma-4") else "low"
                safe.thinking_config = types.ThinkingConfig(
                    include_thoughts=inc,
                    thinking_level=lvl,
                    thinking_budget=None,
                )
            elif lower_name.startswith("gemma-4") or intent_type in LOW_THINKING_SUPPRESSED_INTENTS:
                safe.thinking_config = types.ThinkingConfig(
                    include_thoughts=False,
                    thinking_level="minimal",
                )
            if lower_name.startswith("gemini-3"):
                if hasattr(safe, "temperature"):
                    safe.temperature = None
                if hasattr(safe, "top_p"):
                    safe.top_p = None
                if hasattr(safe, "top_k"):
                    safe.top_k = None
        elif lower_name.startswith("gemini-2.5"):
            if tc is not None:
                budget = getattr(tc, "thinking_budget", None)
                inc = False if intent_type in LOW_THINKING_SUPPRESSED_INTENTS else bool(getattr(tc, "include_thoughts", False))
                if budget is None and intent_type in LOW_THINKING_SUPPRESSED_INTENTS:
                    budget = 0
                if budget is not None or inc:
                    safe.thinking_config = types.ThinkingConfig(
                        include_thoughts=inc,
                        thinking_budget=budget,
                    )
                else:
                    safe.thinking_config = None
        else:
            safe.thinking_config = None
        return safe

    # 1. 移除不支援的工具 (v26.4 精細化：區分一般工具與搜尋增強，Gemma 單層扁平化多型轉接)
    if caps.family == "gemma":
        if intent_type in (
            "GEOCODE", "INTENT_PARSE", "SUMMARIZE", "EXTRACTION",
            "POI_ENRICH", "POI_RECOMMEND", "MEMORY_EXTRACT", "VERIFY", "PARSE_MD", "DAY_REVIEW"
        ):
            safe.tools = None
        elif hasattr(safe, 'tools') and safe.tools and caps.supports_tools:
            safe.tools = get_tools_for_model(model_name, intent_type)
        elif not caps.supports_tools:
            safe.tools = None
    elif hasattr(safe, 'tools') and safe.tools:
        if not caps.supports_tools:
            safe.tools = None
        elif not caps.supports_grounding:
            # 如果不支援 Grounding，過濾掉 google_search / google_maps 工具，保留自定義函數等
            new_tools = []
            for tool in safe.tools:
                # 處理 SDK 物件格式
                if (hasattr(tool, 'google_search') and tool.google_search) or (hasattr(tool, 'google_maps') and tool.google_maps):
                    continue
                # 處理 字典格式
                if isinstance(tool, dict) and ("google_search" in tool or "google_maps" in tool):
                    continue
                new_tools.append(tool)
            safe.tools = new_tools if new_tools else None

    # 2. 移除不支援的解析度
    if hasattr(safe, 'media_resolution') and not caps.supports_media_resolution:
        safe.media_resolution = None

    # 3. 🚀 2026 搜尋與地圖 Grounding 守護 (杜絕免費金鑰 429 RESOURCE_EXHAUSTED 地圖陷阱)
    # 🛡️ 嚴格約束：只有在顯式請求 Grounding (explicit_grounding=True) 時才注入；
    # 一般 CHAT、ITINERARY、DIAGNOSIS、COMPOSITE、ACTUARY 業務流程全面採用乾淨業務工具，嚴禁盲目追加 Google Maps Grounding
    should_inject_grounding = (explicit_grounding is True)

    if intent_type == "SEARCH":
        # 🛡️ SEARCH 意圖純粹使用自定義 search_web 工具，絕對禁止追加 Google 原生付費 Grounding
        pass
    elif should_inject_grounding and caps.family == "gemini" and caps.supports_grounding and intent_type in ["CHAT", "DIAGNOSIS", "ITINERARY", "COMPOSITE"]:
        if not safe.tools:
            safe.tools = []
        # 2026 官方 Tool Combination: 同時注入 Google Search 與 Google Maps
        safe.tools.append(
            types.Tool(
                google_search=types.GoogleSearch(),
                google_maps=types.GoogleMaps(enable_widget=True)
            )
        )

    # 4. 思想配置精準校正 (支援 Gemma 4 31B thinking_level 與 supports_thinking=False 剝離)
    safe.thinking_config = _normalize_thinking_config_for_caps(
        getattr(safe, "thinking_config", None),
        model_name,
        intent_type,
        caps,
    )

    # 4b. Gemini 3.x 取樣參數完全移除 (2026 官方最佳實踐)
    if caps.family == "gemini" and model_name.startswith("gemini-3"):
        if hasattr(safe, 'temperature'):
            safe.temperature = None
        if hasattr(safe, 'top_p'):
            safe.top_p = None
        if hasattr(safe, 'top_k'):
            safe.top_k = None

    # 5. Schema 降級與隱式修正 (關鍵核心)
    require_json = intent_type in INTENTS_REQUIRING_JSON
    if require_json:
        if not caps.supports_schema:
            # 模型不支援 Schema，將 MIME 設回 text 並移除 schema
            safe.response_mime_type = None
            safe.response_json_schema = None
        elif caps.requires_property_ordering and safe.response_json_schema:
            # 對於需要 propertyOrdering 的模型 (如 Gemini 2.0)，執行注入
            safe.response_json_schema = inject_property_ordering(safe.response_json_schema)

    return safe


def inject_property_ordering(schema: Dict[str, Any]) -> Dict[str, Any]:
    """遞歸注入 propertyOrdering 以確保 Schema 嚴格相容性 (v21)"""
    out = copy.deepcopy(schema)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            props = node.get("properties")
            if isinstance(props, dict) and "propertyOrdering" not in node:
                node["propertyOrdering"] = list(props.keys())
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(out)
    return out


# ═══════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════
# 🚦 Routing Hub & Error Classifier (法典級)
# ═══════════════════════════════════════════════════════════════

class AIProtocolError(Exception):
    """AI 協議層異常基類"""
    pass

class NonRetryableAuthError(AIProtocolError):
    """401/403 認證失敗，立即終止 Fallback"""
    pass

class NonRetryableRequestError(AIProtocolError):
    """400 壞請求（非 Config 問題），立即終止"""
    pass

class AllModelsFailedError(AIProtocolError):
    """所有 Fallback 路徑均告失敗"""
    def __init__(self, attempts: List[Dict]):
        self.attempts = attempts
        super().__init__(f"All candidate models failed. Trace: {attempts}")


# ═══════════════════════════════════════════════════════════════
# 🚦 Circuit Breaker (多租戶隔離熔斷器與 429 中繼資料解析)
# ═══════════════════════════════════════════════════════════════

_CIRCUIT_STATE = {}  # {key: {"errors": int, "cooldown_until": float}}
ERROR_THRESHOLD = 3
COOLDOWN_PERIOD = 300       # 5 分鐘 (伺服器故障 500/503)
RATE_LIMIT_COOLDOWN = 12    # 12 秒 (429 速率限制專用短冷卻期，10~15s 區間)


def parse_429_metadata(err: Union[errors.APIError, Exception]) -> Dict[str, Any]:
    """
    結構化解析 HTTP 429 RESOURCE_EXHAUSTED 中繼資料
    依序檢查 err.details 中的 QuotaFailure 與 RetryInfo (retryDelay)，
    包含字串化 JSON 解析，並在欠缺結構化欄位時安全回退至 err.message/str(err) 正則匹配。
    """
    retry_delay = 0.0
    is_daily = False
    quota_reason = "rate_limit_exceeded"

    raw_msg = getattr(err, "message", "") or ""
    err_str = str(err)
    search_corpus = f"{raw_msg} {err_str}"
    lower_corpus = search_corpus.lower()

    # 1. 檢查 err.details (結構化 Protobuf / Dict 列表 / JSON 字串)
    details = getattr(err, "details", None)
    if isinstance(details, str) and details.strip():
        search_corpus += f" {details}"
        try:
            parsed_details = json.loads(details)
            details = parsed_details
        except Exception:
            pass

    detail_items: List[Any] = []
    if isinstance(details, list):
        detail_items = details
    elif isinstance(details, dict):
        if "error" in details and isinstance(details["error"], dict):
            sub_details = details["error"].get("details", [])
            if isinstance(sub_details, str):
                try:
                    sub_details = json.loads(sub_details)
                except Exception:
                    pass
            detail_items = sub_details if isinstance(sub_details, list) else []
        elif "details" in details and isinstance(details["details"], list):
            detail_items = details["details"]
        else:
            detail_items = [details]

    for item in detail_items:
        if isinstance(item, dict):
            # A. 提取 RetryInfo (retryDelay)
            type_str = str(item.get("@type", "")).lower()
            if "retryinfo" in type_str or "retrydelay" in item or "retry_delay" in item:
                delay_val = item.get("retryDelay") or item.get("retry_delay")
                if delay_val is not None:
                    if isinstance(delay_val, (int, float)):
                        retry_delay = float(delay_val)
                    elif isinstance(delay_val, str):
                        delay_str = delay_val.strip().lower()
                        if delay_str.endswith("ms"):
                            try:
                                retry_delay = float(delay_str[:-2]) / 1000.0
                            except ValueError:
                                pass
                        elif delay_str.endswith("s"):
                            try:
                                retry_delay = float(delay_str[:-1])
                            except ValueError:
                                pass
                        else:
                            try:
                                retry_delay = float(delay_str)
                            except ValueError:
                                pass

            # B. 提取 QuotaFailure (violations)
            if "quotafailure" in type_str or "violations" in item:
                violations = item.get("violations", [])
                if isinstance(violations, list):
                    for v in violations:
                        desc = ""
                        if isinstance(v, dict):
                            desc = str(v.get("description", "")) or str(v.get("subject", ""))
                        else:
                            desc = str(v)
                        desc_lower = desc.lower()
                        if any(k in desc_lower for k in ["perday", "daily", "rpd", "day"]):
                            is_daily = True
                            quota_reason = "daily_quota_exhausted"
                        elif "minute" in desc_lower or "rpm" in desc_lower or "rate_limit" in desc_lower:
                            quota_reason = "rate_limit_per_minute"
                        elif desc:
                            quota_reason = desc[:80]

    # 2. 文本啟發式回退 (Fallback Regex across search_corpus)
    if retry_delay <= 0.0:
        delay_match = re.search(r"retry\s+(?:in|after)\s+([0-9\.]+)\s*(s|ms|seconds|second)?", search_corpus, re.IGNORECASE)
        if delay_match:
            val = float(delay_match.group(1))
            unit = (delay_match.group(2) or "s").lower()
            retry_delay = val / 1000.0 if unit == "ms" else val
        else:
            delay_field_match = re.search(r"retryDelay[\"':\s]+([0-9\.]+)\s*(s|ms)?", search_corpus, re.IGNORECASE)
            if delay_field_match:
                val = float(delay_field_match.group(1))
                unit = (delay_field_match.group(2) or "s").lower()
                retry_delay = val / 1000.0 if unit == "ms" else val

    if not is_daily:
        if any(k in lower_corpus for k in ["perday", "per day", "daily requests", "daily quota", "rpd quota"]):
            is_daily = True
            quota_reason = "daily_quota_exhausted"

    return {
        "retry_delay": max(0.0, retry_delay),
        "is_daily": is_daily,
        "quota_reason": quota_reason,
    }


def _get_circuit_key(model_name: str, api_key: Optional[str] = None) -> str:
    """以 (hash(api_key), model_name) 為鍵進行多租戶物理隔離，杜絕全域污染"""
    if api_key:
        key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
        return f"{key_hash}:{model_name}"
    return f"global:{model_name}"


def is_model_circuit_broken(model_name: str, api_key: Optional[str] = None) -> bool:
    """檢查模型在特定 API Key 上是否處於熔斷冷卻期"""
    key = _get_circuit_key(model_name, api_key)
    state = _CIRCUIT_STATE.get(key)
    if not state and api_key:
        # 向後相容檢查無 key 的全域狀態
        state = _CIRCUIT_STATE.get(model_name) or _CIRCUIT_STATE.get(f"global:{model_name}")
    elif not state:
        state = _CIRCUIT_STATE.get(model_name)

    if not state:
        return False

    if time.time() < state.get("cooldown_until", 0):
        return True

    # 超過冷卻時間，重置狀態 (半開狀態)
    if state.get("errors", 0) >= ERROR_THRESHOLD:
        _CIRCUIT_STATE[key] = {"errors": 0, "cooldown_until": 0}
        if model_name in _CIRCUIT_STATE:
            _CIRCUIT_STATE[model_name] = {"errors": 0, "cooldown_until": 0}
    return False


def record_model_error(
    model_name: str,
    api_key: Optional[str] = None,
    is_rate_limit: bool = False
):
    """記錄模型錯誤並視情況觸發熔斷（區分 429 速率限制 12s 與 5xx 伺服器故障 300s）"""
    key = _get_circuit_key(model_name, api_key)
    state = _CIRCUIT_STATE.get(key, {"errors": 0, "cooldown_until": 0})
    state["errors"] += 1

    cooldown = RATE_LIMIT_COOLDOWN if is_rate_limit else COOLDOWN_PERIOD
    if state["errors"] >= ERROR_THRESHOLD:
        state["cooldown_until"] = time.time() + cooldown

    _CIRCUIT_STATE[key] = state
    # 若無 api_key，同步相容舊版直接以 model_name 為 key 之單元測試
    if not api_key:
        _CIRCUIT_STATE[model_name] = state


def _get_api_error_code(err: Any) -> Optional[int]:
    code = getattr(err, "code", None)
    if code is None:
        code = getattr(err, "status_code", None)
    return code


def classify_api_error(err: Any) -> str:
    """法典化錯誤分類規範 (同時相容 google.genai.errors.APIError.code 與 compat_errors.APIStatusError.status_code)"""
    code = _get_api_error_code(err)
    raw_msg = getattr(err, "message", "") or ""
    full_str = f"{raw_msg} {str(err)}".lower()

    # 🛡️ 2026 金鑰遷移增強：精準辨識 401/403、未授權金鑰、已廢棄或被封鎖 (Blocked) 金鑰
    if code in (401, 403) or any(k in full_str for k in [
        "api_key_invalid", "permission_denied", "api key not valid", 
        "blocked", "key expired", "unauthenticated", "invalid api key"
    ]):
        return "auth_fail"
    if code in (429, 500, 502, 503, 504):
        return "retryable"
    if code == 400:
        # 對話歷史結構缺少 thought_signature 屬於不可原位降級重試的協定錯誤，須 Fail-Fast 阻斷 config_unsupported 誤判
        if "thought_signature" in full_str or "thoughtsignature" in full_str or "thought signature" in full_str:
            return "bad_request"
        # 偵測是否為「參數不相容」導致的 400
        schemaish = any(k in full_str for k in [
            "response_json_schema", "response_schema", "response schema", "response_mime_type",
            "invalid argument", "unsupported", "propertyordering",
            "tool use with response", "function calling is not enabled", "tools is not supported", "tools are not supported",
            "thinking", "thinking_level", "thinking_budget", "automatic_function_calling"
        ])
        return "config_unsupported" if schemaish else "bad_request"
    return "unknown"


def build_effective_routing(
    intent_type: str,
    routing_strategy: Optional[List[str]] = None,
    api_key: Optional[str] = None,
) -> List[str]:
    # 1. 建立初始路由並套用熔斷檢查
    if routing_strategy:
        base_routing = list(routing_strategy)
    elif intent_type in (
        "CHAT", "DIAGNOSIS", "DAY_REVIEW", "SEARCH", "ITINERARY",
        "REMOVE_ITINERARY", "EXPENSE", "COMPOSITE", "VERIFY",
        "POI_ENRICH", "POI_RECOMMEND", "MEMORY_EXTRACT"
    ):
        base_routing = list(DAILY_ROUTING)
    elif intent_type in ("GEOCODE", "SUMMARIZE", "INTENT_PARSE"):
        base_routing = list(WORKHORSE_ROUTING)
    elif intent_type == "EXTRACTION":
        base_routing = list(EXTRACTION_ROUTING)
    else:
        base_routing = list(HEAVY_ROUTING)

    # 工具強制意圖（如 ADD/REMOVE ITINERARY、EXPENSE）避免空轉在 supports_tools=False 模型
    if intent_type in TOOL_REQUIRED_INTENTS:
        tool_capable = [
            m for m in base_routing
            if not (MODEL_CAPS.get(m) and not MODEL_CAPS[m].supports_tools)
        ]
        if tool_capable:
            base_routing = tool_capable

    routing = [m for m in base_routing if not is_model_circuit_broken(m, api_key=api_key)]

    if intent_type in INTENTS_ALLOW_GEMMA_LAST_RESORT:
        # 🚀 2026 多層級救援 (L1 Penultimate 31B -> L2 MoE 26B)
        rescue_tier = [WORKHORSE_PENULTIMATE, WORKHORSE_MOE]
        for model_name in rescue_tier:
            # 🛡️ 熔斷器檢查：若模型正在「冷卻」，則跳過此救援層
            if is_model_circuit_broken(model_name, api_key=api_key):
                continue
            if model_name not in routing:
                routing.append(model_name)

    return routing


def summarize_response_diagnostics(response: Any) -> Dict[str, Any]:
    """萃取回應診斷資訊（finish_reason 與 parts 組成），避免吞錯時無從追蹤。"""
    if response is None:
        return {"finish_reason": None, "parts": ["<none>"]}
    cands = getattr(response, "candidates", None)
    if not isinstance(cands, list) or not cands:
        txt = getattr(response, "text", None)
        txt_len = len(txt) if isinstance(txt, str) else 0
        return {"finish_reason": None, "parts": [f"<no_candidates text_len={txt_len}>"]}

    cand0 = cands[0]
    finish_reason = getattr(cand0, "finish_reason", None)
    content = getattr(cand0, "content", None)
    parts = getattr(content, "parts", None) if content else None
    part_summary: List[str] = []
    if isinstance(parts, list):
        for p in parts:
            is_thought = bool(getattr(p, "thought", False) is True)
            txt = getattr(p, "text", None)
            fc = getattr(p, "function_call", None)
            fc_name = getattr(fc, "name", None) if fc is not None else None
            if is_thought:
                t_len = len(txt) if isinstance(txt, str) else 0
                part_summary.append(f"thought(len={t_len})")
            elif isinstance(fc_name, str) and fc_name:
                part_summary.append(f"function_call({fc_name})")
            elif isinstance(txt, str):
                part_summary.append(f"text(len={len(txt)})")
            else:
                part_summary.append("other_part")
    return {"finish_reason": str(finish_reason) if finish_reason is not None else None, "parts": part_summary}


def _has_function_calls(response: Any) -> bool:
    if response is None:
        return False
    cands = getattr(response, "candidates", None)
    if isinstance(cands, list):
        for cand in cands:
            content = getattr(cand, "content", None)
            parts = getattr(content, "parts", None) if content else None
            if isinstance(parts, list):
                for part in parts:
                    fc = getattr(part, "function_call", None)
                    if fc is not None and isinstance(getattr(fc, "name", None), str) and fc.name:
                        return True
    top_fcs = getattr(response, "function_calls", None)
    if isinstance(top_fcs, list):
        for fc in top_fcs:
            if fc is not None and isinstance(getattr(fc, "name", None), str) and fc.name:
                return True
    return False


def build_degraded_config_on_400(
    config: types.GenerateContentConfig,
    err: Optional[errors.APIError] = None,
) -> types.GenerateContentConfig:
    """當模型回傳 400 config_unsupported 時，原地剝除可能不受支援的 thinking_config / AFC / schema 重試一次。"""
    degraded = copy.deepcopy(config)
    raw_msg = getattr(err, "message", "") or ""
    msg = f"{raw_msg} {str(err or '')}".lower()

    if hasattr(degraded, "thinking_config"):
        degraded.thinking_config = None
    if "automatic_function_calling" in msg and hasattr(degraded, "automatic_function_calling"):
        degraded.automatic_function_calling = None

    schema_related = any(
        k in msg for k in (
            "schema", "response_json_schema", "response_schema",
            "response_mime_type", "propertyordering", "json"
        )
    )
    thinking_or_afc_only = any(
        k in msg for k in ("thinking", "thinking_level", "thinking_budget", "automatic_function_calling")
    )
    if schema_related or not thinking_or_afc_only:
        if hasattr(degraded, "response_json_schema"):
            degraded.response_json_schema = None
        if hasattr(degraded, "response_schema"):
            degraded.response_schema = None
        if hasattr(degraded, "response_mime_type"):
            degraded.response_mime_type = None

    return degraded


async def _execute_with_transient_retry(
    invoke_fn,
    model_name: str,
    config: types.GenerateContentConfig,
    timeout_sec: float,
    tag: str,
):
    """執行單一模型請求，具備 429 快速重試、5xx 短退避單次重試、及 400 config_unsupported 原地自癒降階重試。"""
    retried_429 = False
    retried_5xx = False
    retried_config = False
    current_config = config

    while True:
        try:
            return await asyncio.wait_for(invoke_fn(current_config), timeout=timeout_sec)
        except _MODEL_API_ERRORS as e:
            code = _get_api_error_code(e)
            kind = classify_api_error(e)

            if kind == "config_unsupported" and not retried_config:
                retried_config = True
                print(f"🛠️ [{tag} 400 Self-Heal] {model_name} config_unsupported ({e}); stripping thinking/schema & retrying once...")
                current_config = build_degraded_config_on_400(current_config, e)
                continue

            if code == 429 and not retried_429:
                meta = parse_429_metadata(e)
                retry_delay = meta.get("retry_delay", 0.0)
                is_daily = meta.get("is_daily", False)
                if not is_daily and retry_delay <= 1.5:
                    retried_429 = True
                    sleep_sec = retry_delay if retry_delay > 0.0 else 0.1
                    print(f"⏳ [{tag} 429 Quick Retry] {model_name} rate limit throttled, waiting {sleep_sec:.2f}s before retry...")
                    await asyncio.sleep(sleep_sec)
                    continue

            if code in (500, 502, 503, 504) and not retried_5xx:
                retried_5xx = True
                sleep_sec = 0.8 + random.uniform(0.05, 0.25)
                print(f"⏳ [{tag} {code} Short Retry] {model_name} transient server error, waiting {sleep_sec:.2f}s before retry...")
                await asyncio.sleep(sleep_sec)
                continue

            raise


async def call_with_fallback(
    api_key: str,
    history: List[Dict],
    message: str,
    thought_signatures: Optional[List[Dict]] = None,
    intent_type: str = "CHAT",
    routing_strategy: Optional[List[str]] = None,
    system_instruction: Optional[str] = None,
    tools: Optional[List[Any]] = None,
    explicit_grounding: bool = False,
) -> Dict[str, Any]:
    """智能對話式呼叫 (v21 版)"""
    client = get_cached_client(api_key)
    chat_history = enforce_strict_alternating_turns(build_chat_history(history))
    base_config = get_generation_config(intent_type)
    if tools is not None:
        base_config.tools = copy.deepcopy(tools) if tools else None
    routing = build_effective_routing(intent_type, routing_strategy, api_key=api_key)
    require_json = intent_type in INTENTS_REQUIRING_JSON

    attempts = []

    for i, model_name in enumerate(routing):
        caps = MODEL_CAPS.get(model_name)
        if not caps:
            continue

        # 能力守門 (Capability Gate)
        if require_json and not caps.supports_schema:
            attempts.append({"model": model_name, "decision": "skip_no_schema"})
            continue

        if getattr(base_config, "tools", None) and not caps.supports_tools:
            attempts.append({"model": model_name, "decision": "skip_no_tools"})
            continue

        timeout_sec = _get_call_timeout(intent_type, model_name=model_name)
        try:
            config = sanitize_config_for_model(
                base_config, model_name, intent_type, explicit_grounding=explicit_grounding
            )
            if system_instruction:
                config.system_instruction = system_instruction
            label = "Primary" if i == 0 else f"Fallback#{i}"
            print(f"[{label}] {model_name} (intent={intent_type})...")

            async def _send(cfg):
                chat = client.aio.chats.create(
                    model=model_name,
                    history=chat_history,
                    config=cfg,
                )
                return await chat.send_message(message)

            response = await _execute_with_transient_retry(
                _send, model_name, config, timeout_sec, "Chat"
            )
            extracted = _extract_response(response, model_name)
            if not (extracted.get("text") or "").strip() and not _has_function_calls(response):
                diag = summarize_response_diagnostics(response)
                print(
                    f"⚠️ [Chat Empty Output] {model_name} (intent={intent_type}) returned empty visible text "
                    f"(finish_reason={diag['finish_reason']}, parts={diag['parts']}); triggering fallback"
                )
                record_model_error(model_name, api_key=api_key, is_rate_limit=False)
                attempts.append({"model": model_name, "decision": "empty_response", **diag})
                continue

            print(f"✅ {model_name} 成功回應")
            return extracted

        except asyncio.TimeoutError:
            print(f"⏱️ [Chat Timeout] {model_name} (intent={intent_type}) exceeded {timeout_sec}s; switching fallback without circuit ban")
            attempts.append({"model": model_name, "decision": "timeout", "timeout": timeout_sec})
            continue
        except _MODEL_API_ERRORS as e:
            kind = classify_api_error(e)
            err_code = _get_api_error_code(e)
            err_msg = getattr(e, "message", None) or str(e)
            is_429 = (err_code == 429)
            if kind not in ("auth_fail", "bad_request"):
                record_model_error(model_name, api_key=api_key, is_rate_limit=is_429)
            attempts.append({"model": model_name, "decision": kind, "code": err_code})

            if kind == "auth_fail":
                raise NonRetryableAuthError(f"{model_name} Auth Failed: {err_msg}")
            if kind == "bad_request":
                raise NonRetryableRequestError(f"{model_name} Bad Request: {err_msg}")

            # 🚀 平滑降級抖動 (Smooth Fallback Jitter): 防止 0ms 暴衝引發 GCP 專案層級突發限流
            if is_429:
                await asyncio.sleep(0.15 + random.uniform(0.01, 0.05))

            continue
        except Exception as e:
            print(f"⚠️ [Chat Error] {model_name} (intent={intent_type}) {type(e).__name__}: {e}")
            attempts.append({"model": model_name, "decision": "unexpected", "msg": str(e)})
            continue

    raise AllModelsFailedError(attempts)


# ═══════════════════════════════════════════════════════════════
# 🔍 call_verifier — POI 驗證
# ═══════════════════════════════════════════════════════════════

async def call_verifier(
    api_key: str,
    poi_data: Dict,
    query: str,
    routing_strategy: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Verifier — 驗證 POI 資訊，自動降級。
    """
    client = get_cached_client(api_key)
    base_config = get_generation_config("VERIFY")
    routing = build_effective_routing("VERIFY", routing_strategy, api_key=api_key)

    prompt = f"""請驗證以下地點的資訊：
地點：{poi_data.get('place_name', '未知')}

需要確認：{query}

請根據你的知識回答，如果不確定請說明。"""

    attempts: List[Dict[str, Any]] = []

    for i, model_name in enumerate(routing):
        timeout_sec = _get_call_timeout("VERIFY", model_name=model_name)
        try:
            config = sanitize_config_for_model(base_config, model_name, "VERIFY", explicit_grounding=False)

            async def _verify(cfg):
                return await client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=cfg,
                )

            response = await _execute_with_transient_retry(
                _verify, model_name, config, timeout_sec, "Verifier"
            )
            verified_data = extract_clean_response_text(response)
            if not verified_data or not verified_data.strip():
                diag = summarize_response_diagnostics(response)
                print(
                    f"⚠️ [Verifier Empty Output] {model_name} returned empty visible text "
                    f"(finish_reason={diag['finish_reason']}, parts={diag['parts']}); triggering fallback"
                )
                record_model_error(model_name, api_key=api_key, is_rate_limit=False)
                attempts.append({"model": model_name, "decision": "empty_output", "finish_reason": diag["finish_reason"]})
                continue

            return {
                "verified_data": verified_data,
                "grounding_metadata": _extract_grounding_metadata(response),
            }
        except asyncio.TimeoutError:
            attempts.append({"model": model_name, "decision": "timeout", "timeout": timeout_sec})
            print(f"⏱️ [Verifier Timeout] {model_name} exceeded {timeout_sec}s; skipping circuit ban")
        except _MODEL_API_ERRORS as e:
            kind = classify_api_error(e)
            err_code = _get_api_error_code(e)
            err_msg = getattr(e, "message", None) or str(e)
            is_429 = (err_code == 429)
            if kind not in ("auth_fail", "bad_request"):
                record_model_error(model_name, api_key=api_key, is_rate_limit=is_429)
            attempts.append({"model": model_name, "decision": kind, "code": err_code})
            print(f"⚠️ [Verifier] {model_name} 失敗 (HTTP {err_code}, kind={kind}): {e}")
            if kind == "auth_fail":
                raise NonRetryableAuthError(f"{model_name} Auth Failed: {err_msg}")
            if kind == "bad_request":
                raise NonRetryableRequestError(f"{model_name} Bad Request: {err_msg}")
            if is_429:
                await asyncio.sleep(0.15 + random.uniform(0.01, 0.05))
        except Exception as e:
            attempts.append({"model": model_name, "decision": "unexpected", "msg": str(e)})
            print(f"⚠️ [Verifier] {model_name} 未預期錯誤 ({type(e).__name__}): {e}")

    print("❌ [Verifier] 所有模型均不可用")
    raise AllModelsFailedError(attempts)


# ═══════════════════════════════════════════════════════════════
# 🤖 call_extraction — 統一調度核心 (v21)
# ═══════════════════════════════════════════════════════════════

async def call_extraction(
    api_key: str,
    prompt: Union[str, List[Any]],
    intent_type: str = "CHAT",
    routing_strategy: Optional[List[str]] = None,
    system_instruction: Optional[str] = None,
) -> str:
    """
    統一的 AI 提取/生成函數 (v21 版)
    
    具備 Fail-Fast, Capability Gating, 以及實體化 Gemma 備援。
    """
    client = get_cached_client(api_key)
    base_config = get_generation_config(intent_type)
    routing = build_effective_routing(intent_type, routing_strategy, api_key=api_key)
    require_json = intent_type in INTENTS_REQUIRING_JSON

    attempts = []

    for i, model_name in enumerate(routing):
        caps = MODEL_CAPS.get(model_name)
        if not caps:
            continue

        # 能力與任務匹配
        if require_json and not caps.supports_schema:
            attempts.append({"model": model_name, "decision": "skip_no_schema"})
            continue
        
        # Gemma 准入檢查 (v21.2 精確分類)
        if caps.family == "gemma":
            # 對於 EXTRACTION (收據圖片解析)，目前仍嚴格禁止 fallback
            # 但對於 PLANNING / PARSE_MD (行程生成/重構)，Gemma 3/4 具備處理結構化數據的能力，允許作為末位備援
            if intent_type == "EXTRACTION" and not caps.allow_extraction_fallback:
                attempts.append({"model": model_name, "decision": "skip_strict_extraction_prevention"})
                continue
            
            # 對於其餘任務，遵循 INTENTS_ALLOW_GEMMA_LAST_RESORT 白名單
            if intent_type not in INTENTS_ALLOW_GEMMA_LAST_RESORT:
                attempts.append({"model": model_name, "decision": "skip_intent_not_allowed_for_gemma"})
                continue

        timeout_sec = _get_call_timeout(intent_type, model_name=model_name)
        response = None
        text = ""
        try:
            config = sanitize_config_for_model(base_config, model_name, intent_type, explicit_grounding=False)
            if system_instruction:
                config.system_instruction = system_instruction
            label = "Primary" if i == 0 else f"Fallback#{i}"
            print(f"[{label}] {model_name} (intent={intent_type}, timeout={timeout_sec}s)...")

            async def _extract(cfg):
                return await client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=cfg,
                )

            response = await _execute_with_transient_retry(
                _extract, model_name, config, timeout_sec, "Extraction"
            )

            text = extract_clean_response_text(response)
            if not text or not text.strip():
                diag = summarize_response_diagnostics(response)
                print(
                    f"⚠️ [Extraction Empty Output] {model_name} (intent={intent_type}) returned empty visible text "
                    f"(finish_reason={diag['finish_reason']}, parts={diag['parts']}); triggering fallback"
                )
                record_model_error(model_name, api_key=api_key, is_rate_limit=False)
                attempts.append({"model": model_name, "decision": "empty_response", **diag})
                continue

            if require_json:
                text = _clean_json_text(text)
                # 確保 JSON 可解析
                json.loads(text)

            print(f"✅ {model_name} 成功回應")
            return text

        except asyncio.TimeoutError:
            print(f"⏱️ [Extraction Timeout] {model_name} (intent={intent_type}) exceeded {timeout_sec}s; switching fallback without circuit ban")
            attempts.append({"model": model_name, "decision": "timeout", "timeout": timeout_sec})
            continue
        except _MODEL_API_ERRORS as e:
            kind = classify_api_error(e)
            err_code = _get_api_error_code(e)
            err_msg = getattr(e, "message", None) or str(e)
            is_429 = (err_code == 429)
            if kind not in ("auth_fail", "bad_request"):
                record_model_error(model_name, api_key=api_key, is_rate_limit=is_429)
            attempts.append({"model": model_name, "decision": kind, "code": err_code})

            if kind == "auth_fail":
                raise NonRetryableAuthError(f"Auth Failed: {err_msg}")
            if kind == "bad_request":
                raise NonRetryableRequestError(f"Bad Request: {err_msg}")

            if is_429:
                await asyncio.sleep(0.15 + random.uniform(0.01, 0.05))
            continue

        except json.JSONDecodeError as e:
            diag = summarize_response_diagnostics(response)
            snippet = (text or "")[:160].replace("\n", "\\n")
            print(
                f"⚠️ [Extraction JSONDecodeError] {model_name} (intent={intent_type}, len={len(text or '')}, "
                f"finish_reason={diag['finish_reason']}): {e} | snippet={snippet!r}"
            )
            attempts.append({"model": model_name, "decision": "json_parse_fail", "finish_reason": diag["finish_reason"]})
            continue
        except Exception as e:
            print(f"⚠️ [Extraction Error] {model_name} (intent={intent_type}) {type(e).__name__}: {e}")
            attempts.append({"model": model_name, "decision": "exception", "msg": str(e)})
            continue

    raise AllModelsFailedError(attempts)


def _clean_json_text(text: str) -> str:
    """清理 Markdown 標籤"""
    if not text: return ""
    return text.replace("```json", "").replace("```", "").strip()


def map_ai_exception_to_http_status(
    exc: Exception,
    is_en: bool = False,
    fallback_detail: Optional[str] = None,
) -> Tuple[int, str, str]:
    """將模型調度引擎例外統一映射為精確的 (HTTP Status, Semantic Error Code, Detail Message)，避免全轉成 500。"""
    if isinstance(exc, NonRetryableAuthError):
        msg = (
            "Invalid or expired Gemini API Key. Please update your key in Profile."
            if is_en
            else "Gemini API Key 無效或已過期，請至個人設定更新金鑰。"
        )
        return 401, "auth_fail", msg
    if isinstance(exc, NonRetryableRequestError):
        msg = (
            f"Invalid AI request parameters: {exc}"
            if is_en
            else f"AI 請求參數無效：{exc}"
        )
        return 400, "bad_request", msg
    if isinstance(exc, AllModelsFailedError):
        msg = (
            "All AI models are currently busy or temporarily unavailable. Please try again later."
            if is_en
            else "所有 AI 模型目前暫時繁忙或無回應，請稍後再試。"
        )
        return 503, "all_models_failed", msg
    return 500, "internal_error", (
        fallback_detail
        or ("AI service encountered an unexpected error." if is_en else "AI 服務暫時發生異常，請稍後再試")
    )


async def call_extraction_server(
    prompt: str,
    intent_type: str = "GEOCODE",
    routing_strategy: Optional[List[str]] = None,
    api_key: Optional[str] = None,  # 🆕 允許從外部傳入 Key
    system_instruction: Optional[str] = None,
) -> str:
    """Server-side key 版本的 call_extraction，優先使用傳入的 api_key"""
    # 優先級：參數傳入的 Key > 系統環境變數
    effective_key = api_key or (os.getenv("GEMINI_API_KEY") or "").strip()
    
    if not effective_key:
        raise ValueError("GEMINI_API_KEY 環境變數未設定，且未提供用戶端 API Key")
        
    return await call_extraction(effective_key, prompt, intent_type, routing_strategy, system_instruction)


# ═══════════════════════════════════════════════════════════════
# 🔧 Internal Helpers
# ═══════════════════════════════════════════════════════════════

def build_chat_history(history: List[Dict]) -> List[types.Content]:
    """建構對話歷史 — 轉換為新 SDK 格式 (無損解析，相容思想簽名與工具呼叫)"""
    chat_history = []

    for msg in history:
        role = "user" if msg.get("role") == "user" else "model"
        
        # 取得原始 parts
        parts_list = []
        if "rawParts" in msg and msg["rawParts"]:
            parts_list = msg["rawParts"]
        elif "parts" in msg and msg["parts"]:
            parts_list = msg["parts"]
        else:
            content = msg.get("content") or msg.get("displayContent") or ""
            parts_list = [{"text": content}] if content else []

        sdk_parts = []
        for part in parts_list:
            if isinstance(part, str):
                sdk_parts.append(types.Part.from_text(text=part))
            elif isinstance(part, dict):
                # 提取與解碼 thought_signature (相容 bytes 與 Base64 str)
                ts_val = part.get("thought_signature") or part.get("thoughtSignature")
                ts_bytes = None
                if ts_val:
                    try:
                        ts_bytes = base64.b64decode(ts_val) if isinstance(ts_val, str) else ts_val
                    except Exception:
                        ts_bytes = ts_val.encode("utf-8") if isinstance(ts_val, str) else None

                # 1. 處理文字 (含思想簽名)
                if "text" in part and part["text"]:
                    if "thought" in part and part["thought"]:
                        sdk_parts.append(types.Part(
                            thought=True,
                            text=part["text"],
                            **({"thought_signature": ts_bytes} if ts_bytes else {})
                        ))
                    else:
                        sdk_parts.append(types.Part(
                            text=part["text"],
                            **({"thought_signature": ts_bytes} if ts_bytes else {})
                        ))
                
                # 2. 處理獨立思想簽名 (字串降級相容)
                elif "thought" in part and part["thought"]:
                    sdk_parts.append(types.Part(
                        thought=True,
                        text=part["thought"] if isinstance(part["thought"], str) else "Thinking...",
                        **({"thought_signature": ts_bytes} if ts_bytes else {})
                    ))
                
                # 3. 處理 Function Call (雙格式相容 + 思想簽名存檔點)
                elif "functionCall" in part or "function_call" in part:
                    fc = part.get("functionCall") or part.get("function_call")
                    if fc and "name" in fc:
                        fc_ts = fc.get("thought_signature") or fc.get("thoughtSignature") or ts_val
                        fc_ts_bytes = None
                        if fc_ts:
                            try:
                                fc_ts_bytes = base64.b64decode(fc_ts) if isinstance(fc_ts, str) else fc_ts
                            except Exception:
                                fc_ts_bytes = fc_ts.encode("utf-8") if isinstance(fc_ts, str) else None

                        sdk_parts.append(types.Part(
                            function_call=types.FunctionCall(
                                name=fc["name"],
                                args=dict(fc.get("args") or {}),
                                id=fc.get("id")
                            ),
                            **({"thought_signature": fc_ts_bytes} if fc_ts_bytes else {})
                        ))
                
                # 4. 處理 Function Response (雙格式相容)
                elif "functionResponse" in part or "function_response" in part:
                    fr = part.get("functionResponse") or part.get("function_response")
                    if fr and "name" in fr:
                        resp_data = fr.get("response") or {}
                        if not isinstance(resp_data, dict):
                            resp_data = {"result": resp_data}
                        sdk_parts.append(types.Part(
                            function_response=types.FunctionResponse(
                                name=fr["name"],
                                response=resp_data,
                                id=fr.get("id")
                            )
                        ))

        if sdk_parts:
            chat_history.append(types.Content(
                role=role,
                parts=sdk_parts
            ))

    return sanitize_dangling_tool_calls(chat_history)


def enforce_strict_alternating_turns(chat_history: List[types.Content]) -> List[types.Content]:
    """
    🛡️ 強制 multi-turn 嚴格交替 (user -> model -> user)，杜絕連續相同角色觸發 Gemini 400
    若上一則與當前為相同 role，將其 parts 智慧合併；若首則為 model，插入合法 user 佔位以滿足 API 規範。
    純粹函數設計：絕不在外部傳入物件上進行原地突變 (In-place Mutation)。
    """
    if not chat_history:
        return []

    merged: List[types.Content] = []
    for content in chat_history:
        if not content.parts:
            continue
        if merged and merged[-1].role == content.role:
            # 連續相同角色：建立新物件合併 parts，杜絕原地污染外部輸入
            merged[-1] = types.Content(
                role=merged[-1].role,
                parts=list(merged[-1].parts) + list(content.parts)
            )
        else:
            merged.append(types.Content(
                role=content.role,
                parts=list(content.parts)
            ))

    # 確保開頭為 user (Gemini multi-turn 必須由 user 開始)
    if merged and merged[0].role == "model":
        merged.insert(0, types.Content(role="user", parts=[types.Part.from_text(text="Hello")]))

    return merged


def sanitize_dangling_tool_calls(chat_history: List[types.Content]) -> List[types.Content]:
    """
    🛡️ 修復歷史紀錄中的懸空 Function Call，防止 Gemini 400 Bad Request
    規則：若 Content(role='model') 包含 function_call，但下一則 Content 並非對應的 function_response，
    自動補齊合成的 function_response (status: 'client_handled')。
    """
    sanitized: List[types.Content] = []
    i = 0
    while i < len(chat_history):
        content = chat_history[i]
        sanitized.append(content)
        if content.role == "model":
            pending_fcs = [
                part.function_call for part in content.parts 
                if hasattr(part, 'function_call') and part.function_call
            ]
            if pending_fcs:
                # 檢查下一個 Content 是否已為包含 function_response 的 user content
                next_content = chat_history[i + 1] if i + 1 < len(chat_history) else None
                has_response = (
                    next_content is not None and 
                    next_content.role == "user" and 
                    any(hasattr(p, 'function_response') and p.function_response for p in next_content.parts)
                )
                if not has_response:
                    # 自動補齊合法的對稱 response (附帶匹配的 call id 與 name)
                    dummy_responses = [
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=fc.name,
                                response={"status": "client_handled", "note": "Processed by client UI"},
                                id=getattr(fc, 'id', None)
                            )
                        )
                        for fc in pending_fcs
                    ]
                    sanitized.append(types.Content(role="user", parts=dummy_responses))
        i += 1
    return sanitized


def extract_clean_response_text(response: Any) -> str:
    """
    從 Gemini Response 或 Chunk 安全提取純文字，徹底杜絕 non-text parts 警告與 ValueError。
    向後相容標準 Google GenAI SDK GenerateContentResponse 物件與單元測試之 MagicMock。
    """
    if response is None:
        return ""
    cands = getattr(response, 'candidates', None)
    if isinstance(cands, list) and cands:
        text_parts = []
        for cand in cands:
            content = getattr(cand, 'content', None)
            parts = getattr(content, 'parts', None) if content else None
            if isinstance(parts, list):
                for p in parts:
                    txt = getattr(p, 'text', None)
                    is_thought = getattr(p, 'thought', False)
                    if isinstance(txt, str) and txt and not is_thought:
                        text_parts.append(txt)
        if text_parts:
            return "".join(text_parts)
        # 若 candidates 存在且已檢查過 parts (例如僅含 function_call)，不應再去調用 response.text 觸發 SDK warning
        has_any_part = any(getattr(getattr(cand, 'content', None), 'parts', None) for cand in cands)
        if has_any_part:
            return ""

    # 僅在非標準 SDK 物件 (例如 candidates=[] 的 MagicMock) 且 candidates 未提供文字時，才安全回退讀取 .text
    try:
        raw_text = getattr(response, 'text', None)
        return raw_text if isinstance(raw_text, str) else ""
    except Exception:
        return ""


def _extract_response(response, model_used: str) -> Dict[str, Any]:
    """從 Response 中提取完整資訊"""
    text = extract_clean_response_text(response)
    raw_parts = []

    cands = getattr(response, 'candidates', None)
    if isinstance(cands, list) and cands:
        candidate = cands[0]
        content = getattr(candidate, 'content', None)
        parts = getattr(content, 'parts', None) if content else None
        if isinstance(parts, list):
            for part in parts:
                raw_parts.append(_serialize_part(part))

    if not raw_parts:
        raw_parts = [{"text": text}]

    return {
        "text": text,
        "raw_parts": raw_parts,
        "model_used": model_used,
        "grounding_metadata": _extract_grounding_metadata(response),
    }


def _serialize_part(part) -> Dict:
    """序列化 Part 物件 (雙相容輸出，確保前端 camelCase 與後端 snake_case 全相容)"""
    serialized = {}

    if hasattr(part, 'text') and part.text:
        serialized["text"] = part.text

    # 相容新舊 SDK 的屬性名稱
    fc = None
    if hasattr(part, 'function_call') and part.function_call:
        fc = part.function_call
    elif hasattr(part, 'functionCall') and part.functionCall:
        fc = part.functionCall

    if fc:
        fc_id = getattr(fc, 'id', None)
        serialized["functionCall"] = {
            "name": fc.name,
            "args": dict(fc.args) if fc.args else {},
            **({"id": fc_id} if fc_id else {})
        }
        # 向上相容舊版本
        serialized["function_call"] = serialized["functionCall"]

    # 思想簽名 (Thought Signatures)
    if hasattr(part, 'thought') and part.thought:
        serialized["thought"] = part.thought

    # 🛡️ 2026: 原生思想簽名 (Native Thought Signature Passthrough)
    ts = getattr(part, 'thought_signature', None) or getattr(part, 'thoughtSignature', None)
    if ts is not None:
        serialized["thought_signature"] = base64.b64encode(ts).decode("utf-8") if isinstance(ts, bytes) else str(ts)
        serialized["thoughtSignature"] = serialized["thought_signature"]

    return serialized


def _extract_grounding_metadata(response) -> Optional[Dict]:
    """提取 Grounding Metadata（Google Search 來源引文）"""
    if not hasattr(response, 'candidates') or not response.candidates:
        return None

    candidate = response.candidates[0]

    if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
        gm = candidate.grounding_metadata
        sources = []

        if hasattr(gm, 'grounding_chunks'):
            for chunk in gm.grounding_chunks:
                if hasattr(chunk, 'web') and chunk.web:
                    sources.append({
                        "title": chunk.web.title if hasattr(chunk.web, 'title') else "Unknown",
                        "uri": chunk.web.uri if hasattr(chunk.web, 'uri') else ""
                    })

        return {"sources": sources} if sources else None

    return None
