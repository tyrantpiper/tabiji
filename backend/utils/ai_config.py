"""
AI Configuration Constants (Next-Gen Architecture v5.0)
-------------------------------------------------------
Centralized AI model configuration with intelligent multi-tier routing.

Routing Strategies:
- DAILY_ROUTING:  日常對話、意圖解析、記憶萃取、POI 推薦、驗證
  → 首選 gemini-3.5-flash-lite (0.7s) → gemini-3.6-flash → gemini-3.1-flash-lite
- HEAVY_ROUTING:  行程生成、Markdown 重構、深度規劃
  → 首選 gemini-3.5-flash-lite → gemini-3.6-flash → gemini-3.1-flash-lite → gemini-3.8-flash
- WORKHORSE_MODEL: 地理引擎（翻譯、國家判斷、摘要）
  → 首選 gemini-3.5-flash-lite (0.7s) → gemini-3.6-flash → gemini-3.1-flash-lite

Reference:
  https://ai.google.dev/gemini-api/docs/models?hl=zh-tw
"""

from typing import List

# ═══════════════════════════════════════════════════════════════
# 🧭 Routing Strategies (Ordered: Primary → Fallback 1 → Fallback 2)
# ═══════════════════════════════════════════════════════════════

DAILY_ROUTING: List[str] = [
    "gemini-3.5-flash-lite",          # 🆕 首選實測最穩定 (0.7s, 500 RPD Map Grounding)
    "gemini-3.6-flash",               # 🚀 次選穩定旗艦，具備 Grounding (取代已棄用別名 gemini-3.5-flash)
    "gemini-3.1-flash-lite",          # 500 RPD, GA — 極速、支援思考/結構化
    "gemini-3.8-flash",               # 🚀 1M tokens 超長上下文 / 64K 輸出 SOTA 推論旗艦 (取代別名 gemini-3.7-flash)
    "gemini-3-flash-preview",         # 20 RPD, 全能型
]

HEAVY_ROUTING: List[str] = [
    "gemini-3.5-flash-lite",          # 🆕 3.5 Lite: 快速低延遲首選 (0.7s)
    "gemini-3.6-flash",               # 3.6 穩定次選 (取代已棄用別名 gemini-3.5-flash)
    "gemini-3.1-flash-lite",          # 500 RPD, 高額度優先
    "gemini-3.8-flash",               # 🚀 3.8: 1M Tokens 超長上下文 / 64K 輸出 (取代別名 gemini-3.7-flash)
    "gemini-3-flash-preview",         # 20 RPD
]

# 🧾 收據解析與 OCR 專屬極速視覺路由 (優先 500 RPD Flash-Lite，杜絕 1M Context 逾時)
EXTRACTION_ROUTING: List[str] = [
    "gemini-3.5-flash-lite",          # 🆕 500 RPD, 首選極速視覺結構化提取 (0.7s)
    "gemini-3.6-flash",               # 快速備援
    "gemini-3.1-flash-lite",          # 500 RPD, 快速備援
    "gemini-3.8-flash",               # 次世代 SOTA 旗艦備援 (取代別名 gemini-3.7-flash)
]

# ═══════════════════════════════════════════════════════════════
# 🐴 Workhorse Model (升級為 3.5-flash-lite / 3.6-flash，消除 Gemma 53s 逾時)
# ═══════════════════════════════════════════════════════════════

WORKHORSE_MOE: str = "gemma-4-26b-a4b-it"         # 高效混合專家 (4B Active, 1100+ tps)
WORKHORSE_PENULTIMATE: str = "gemma-4-31b-it"     # 31B 稠密模型

WORKHORSE_ROUTING: List[str] = [
    "gemini-3.5-flash-lite",          # 🚀 首選主要路由 (實測 0.7s 極速穩定)
    "gemini-3.6-flash",               # 穩定次選
    "gemini-3.1-flash-lite",          # 500 RPD 極速保底
]

WORKHORSE_MODEL: str = WORKHORSE_ROUTING[0]

GEOCODE_ROUTING: List[str] = WORKHORSE_ROUTING

# ═══════════════════════════════════════════════════════════════
# 🔗 Backward-Compatible Aliases (Phase 3 清除後可移除)
# ═══════════════════════════════════════════════════════════════

PRIMARY_MODEL = DAILY_ROUTING[0]
CREATIVE_MODEL = HEAVY_ROUTING[0]
SEARCH_MODEL = DAILY_ROUTING[1]        # gemini-3.6-flash
LITE_MODEL = DAILY_ROUTING[0]          # gemini-3.5-flash-lite
SMART_NO_TOOL_MODEL = DAILY_ROUTING[0]
REASONING_MODEL = WORKHORSE_MODEL
FALLBACK_MODEL = WORKHORSE_MODEL
