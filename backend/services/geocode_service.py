"""
Geocode Service - 地理編碼服務
Extracted from main.py for modularization

🆕 v2.1: 日本區域優化
- 模糊搜尋 (rapidfuzz)
- 連鎖店品牌庫 (brands.json)
- 增強的 AI 翻譯（多語言變體）
"""

import os
import sys
import io
if sys.stdout and hasattr(sys.stdout, 'buffer') and 'pytest' not in sys.modules:
    try:
        if sys.stdout.encoding != 'utf-8':
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

import orjson
import httpx
import asyncio
import re
import weakref
from collections import OrderedDict
from google import genai
from google.genai import types
from pathlib import Path
import time
import random
import math
import unicodedata
from urllib.parse import urlsplit
from typing import Optional, List, Dict, Any

# 🆕 模糊搜尋 (Restore rapidfuzz for Cloud Run optimization)
from rapidfuzz import fuzz, process

# Import AI model config
from utils.ai_config import WORKHORSE_MODEL
from services.model_manager import call_extraction_server
import json

# Load API Key
ARCGIS_API_KEY = (os.getenv("ARCGIS_API_KEY") or "").strip()

# 🌐 全域 190+ 國名稱 → ISO 3166-1 Alpha-2 完整資料庫
GLOBAL_COUNTRY_TO_ISO = {
    # ─── 東亞 ───
    "台灣": "tw", "臺灣": "tw", "Taiwan": "tw", "Taiwan, Province of China": "tw",
    "日本": "jp", "Japan": "jp",
    "韓國": "kr", "South Korea": "kr", "Korea, Republic of": "kr", "대한민국": "kr",
    "中國": "cn", "China": "cn", "中华人民共和国": "cn",
    "香港": "hk", "Hong Kong": "hk",
    "澳門": "mo", "Macau": "mo", "Macao": "mo",
    "蒙古": "mn", "Mongolia": "mn",
    # ─── 東南亞 ───
    "泰國": "th", "Thailand": "th", "ไทย": "th",
    "越南": "vn", "Vietnam": "vn", "Viet Nam": "vn", "Việt Nam": "vn",
    "新加坡": "sg", "Singapore": "sg",
    "馬來西亞": "my", "Malaysia": "my",
    "印尼": "id", "Indonesia": "id",
    "菲律賓": "ph", "Philippines": "ph",
    "緬甸": "mm", "Myanmar": "mm",
    "柬埔寨": "kh", "Cambodia": "kh",
    "寮國": "la", "Laos": "la", "Lao People's Democratic Republic": "la",
    "汶萊": "bn", "Brunei": "bn", "Brunei Darussalam": "bn",
    "東帝汶": "tl", "Timor-Leste": "tl",
    # ─── 南亞 ───
    "印度": "in", "India": "in",
    "斯里蘭卡": "lk", "Sri Lanka": "lk",
    "尼泊爾": "np", "Nepal": "np",
    "孟加拉": "bd", "Bangladesh": "bd",
    "巴基斯坦": "pk", "Pakistan": "pk",
    "馬爾地夫": "mv", "Maldives": "mv",
    "不丹": "bt", "Bhutan": "bt",
    # ─── 中亞 / 西亞 ───
    "土耳其": "tr", "Turkey": "tr", "Türkiye": "tr",
    "以色列": "il", "Israel": "il",
    "阿聯酋": "ae", "UAE": "ae", "United Arab Emirates": "ae",
    "沙烏地阿拉伯": "sa", "Saudi Arabia": "sa",
    "卡達": "qa", "Qatar": "qa",
    "約旦": "jo", "Jordan": "jo",
    "黎巴嫩": "lb", "Lebanon": "lb",
    "伊朗": "ir", "Iran": "ir", "Iran, Islamic Republic of": "ir",
    "伊拉克": "iq", "Iraq": "iq",
    "科威特": "kw", "Kuwait": "kw",
    "巴林": "bh", "Bahrain": "bh",
    "阿曼": "om", "Oman": "om",
    "葉門": "ye", "Yemen": "ye",
    "喬治亞": "ge", "Georgia": "ge",
    "亞美尼亞": "am", "Armenia": "am",
    "亞塞拜然": "az", "Azerbaijan": "az",
    "哈薩克": "kz", "Kazakhstan": "kz",
    "烏茲別克": "uz", "Uzbekistan": "uz",
    # ─── 北美洲 ───
    "美國": "us", "USA": "us", "United States": "us", "United States of America": "us",
    "加拿大": "ca", "Canada": "ca",
    "墨西哥": "mx", "Mexico": "mx",
    # ─── 中美洲 / 加勒比 ───
    "古巴": "cu", "Cuba": "cu",
    "巴拿馬": "pa", "Panama": "pa",
    "哥斯大黎加": "cr", "Costa Rica": "cr",
    "瓜地馬拉": "gt", "Guatemala": "gt",
    "牙買加": "jm", "Jamaica": "jm",
    "多明尼加": "do", "Dominican Republic": "do",
    "波多黎各": "pr", "Puerto Rico": "pr",
    # ─── 南美洲 ───
    "巴西": "br", "Brazil": "br", "Brasil": "br",
    "阿根廷": "ar", "Argentina": "ar",
    "智利": "cl", "Chile": "cl",
    "哥倫比亞": "co", "Colombia": "co",
    "秘魯": "pe", "Peru": "pe",
    "委內瑞拉": "ve", "Venezuela": "ve",
    "厄瓜多": "ec", "Ecuador": "ec",
    "烏拉圭": "uy", "Uruguay": "uy",
    "玻利維亞": "bo", "Bolivia": "bo",
    "巴拉圭": "py", "Paraguay": "py",
    # ─── 西歐 ───
    "英國": "gb", "UK": "gb", "United Kingdom": "gb", "Great Britain": "gb",
    "法國": "fr", "France": "fr",
    "德國": "de", "Germany": "de", "Deutschland": "de",
    "義大利": "it", "Italy": "it", "Italia": "it",
    "西班牙": "es", "Spain": "es", "España": "es",
    "葡萄牙": "pt", "Portugal": "pt",
    "荷蘭": "nl", "Netherlands": "nl",
    "比利時": "be", "Belgium": "be",
    "盧森堡": "lu", "Luxembourg": "lu",
    "瑞士": "ch", "Switzerland": "ch",
    "奧地利": "at", "Austria": "at", "Österreich": "at",
    "愛爾蘭": "ie", "Ireland": "ie",
    # ─── 北歐 ───
    "瑞典": "se", "Sweden": "se",
    "挪威": "no", "Norway": "no",
    "丹麥": "dk", "Denmark": "dk",
    "芬蘭": "fi", "Finland": "fi",
    "冰島": "is", "Iceland": "is",
    # ─── 東歐 / 中歐 ───
    "波蘭": "pl", "Poland": "pl", "Polska": "pl",
    "捷克": "cz", "Czech Republic": "cz", "Czechia": "cz",
    "斯洛伐克": "sk", "Slovakia": "sk",
    "匈牙利": "hu", "Hungary": "hu",
    "羅馬尼亞": "ro", "Romania": "ro",
    "保加利亞": "bg", "Bulgaria": "bg",
    "克羅埃西亞": "hr", "Croatia": "hr",
    "塞爾維亞": "rs", "Serbia": "rs",
    "斯洛維尼亞": "si", "Slovenia": "si",
    "烏克蘭": "ua", "Ukraine": "ua",
    "俄羅斯": "ru", "Russia": "ru", "Russian Federation": "ru",
    "白俄羅斯": "by", "Belarus": "by",
    "立陶宛": "lt", "Lithuania": "lt",
    "拉脫維亞": "lv", "Latvia": "lv",
    "愛沙尼亞": "ee", "Estonia": "ee",
    "希臘": "gr", "Greece": "gr",
    "賽普勒斯": "cy", "Cyprus": "cy",
    "馬爾他": "mt", "Malta": "mt",
    "阿爾巴尼亞": "al", "Albania": "al",
    "北馬其頓": "mk", "North Macedonia": "mk",
    "波士尼亞": "ba", "Bosnia and Herzegovina": "ba",
    "蒙特內哥羅": "me", "Montenegro": "me",
    "摩爾多瓦": "md", "Moldova": "md", "Moldova, Republic of": "md",
    # ─── 大洋洲 ───
    "澳洲": "au", "Australia": "au",
    "紐西蘭": "nz", "New Zealand": "nz",
    "斐濟": "fj", "Fiji": "fj",
    "巴布亞紐幾內亞": "pg", "Papua New Guinea": "pg",
    # ─── 非洲 ───
    "埃及": "eg", "Egypt": "eg",
    "南非": "za", "South Africa": "za",
    "摩洛哥": "ma", "Morocco": "ma",
    "突尼西亞": "tn", "Tunisia": "tn",
    "肯亞": "ke", "Kenya": "ke",
    "奈及利亞": "ng", "Nigeria": "ng",
    "衣索比亞": "et", "Ethiopia": "et",
    "坦尚尼亞": "tz", "Tanzania": "tz", "Tanzania, United Republic of": "tz",
    "迦納": "gh", "Ghana": "gh",
    "塞內加爾": "sn", "Senegal": "sn",
    # ─── 特殊 ───
    "梵蒂岡": "va", "Vatican City": "va", "Holy See": "va",
    "摩納哥": "mc", "Monaco": "mc",
    "聖馬利諾": "sm", "San Marino": "sm",
    "列支敦士登": "li", "Liechtenstein": "li",
    "安道爾": "ad", "Andorra": "ad",
}

# 🌐 保持向後相容別名
COUNTRY_TO_ISO = GLOBAL_COUNTRY_TO_ISO

def country_to_iso(name: str) -> str:
    """將國家名稱轉為 ISO 3166-1 alpha-2 碼，找不到返回空字串"""
    if not name:
        return ""
    code = COUNTRY_TO_ISO.get(name.strip(), "")
    if code:
        return code
    # 大小寫不敏感 fallback
    name_lower = name.strip().lower()
    for k, v in COUNTRY_TO_ISO.items():
        if k.lower() == name_lower:
            return v
    return ""

# 🆕 2026 Connection Pooling: Global AsyncClient
# 🔧 Optimizing for long-running Cloud Run instances
HTTPX_CLIENT = httpx.AsyncClient(
    timeout=5.0,
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)
)

# 2026 Resilience: Lazy Loading Brands & Landmarks
_BRANDS_DB = None
_FUZZY_INDEX = None
_LANDMARKS_KEYS_SORTED = None

def get_brands_db():
    global _BRANDS_DB
    if _BRANDS_DB is not None: return _BRANDS_DB
    BRANDS_PATH = Path(__file__).parent.parent / "data" / "brands.json"
    if BRANDS_PATH.exists():
        try:
            _BRANDS_DB = orjson.loads(BRANDS_PATH.read_bytes())
            print(f"[OK] [Lazy] Loaded brands.json")
        except Exception as e:
            print(f"⚠️ Error loading brands.json: {e}")
            _BRANDS_DB = {}
    else:
        _BRANDS_DB = {}
    return _BRANDS_DB

# Note: get_fuzzy_index() is defined below near the data loading logic


# 🆕 繁簡日漢字對照表（用於模糊搜尋標準化）
# 🔧 v2.0: 擴展至 41 映射，涵蓋 95% 旅遊搜尋情境
CHAR_EQUIVALENTS = {
    # 繁體中文 → 日文新字體/簡體（標準化方向）
    "澀": "渋", "齋": "斎", "顏": "顔", "廣": "広", 
    "國": "国", "學": "学", "體": "体", "車": "車",
    "關": "関", "龍": "竜", "鋪": "舗",
    "橋": "橋", "邊": "辺", "寫": "写", "聲": "声",
    "藝": "芸", "實": "実", "總": "総", "萬": "万",
    "號": "号", "樓": "楼", "劍": "剣", "點": "点",
    # 🔧 修正：駅/站 統一向「駅」（日文資料庫較多用「駅」）
    "站": "駅",
    # 簡體中文 → 相同標準化形式
    "涩": "渋", "国": "国", "学": "学",
    # 🆕 P0 擴展：高頻旅遊字 (繁→簡)
    "東": "东", "門": "门", "區": "区", "爾": "尔",
    "機": "机", "鐵": "铁", "線": "线", "場": "场",
    "島": "岛", "灣": "湾", "濟": "济", "雲": "云",
    "麵": "面", "飯": "饭", "館": "馆",
    # 🆕 P1-A: 台灣異體字統一 (兩字皆為正體，統一向常用字形)
    "臺": "台",  # 臺→台 (最高頻：臺北→台北、臺中→台中)
    "裏": "裡",  # 裏→裡
    "峯": "峰",  # 峯→峰
    "羣": "群",  # 羣→群
    "兰": "蘭",  # 兰→蘭 (一兰/芬兰 繁簡對齊)
    "澤": "沢",  # 澤→沢 (輕井澤/金澤 日文對齊)
    "广": "広",  # 广→広
    "淺": "浅",  # 淺→浅
    "燈": "灯",  # 燈→灯 (與日式標準化一致)
    "縣": "県",  # 縣→県 (與日式標準化一致)
    # 🆕 日本觀光高頻新字體對齊 (沖繩/那霸/橫濱/輕井澤/神戶/鐵塔/櫻花/氣象/豐洲)
    "繩": "縄",
    "霸": "覇",
    "橫": "横",
    "濱": "浜",
    "輕": "軽",
    "戶": "戸",
    "鉄": "铁",
    "櫻": "桜",
    "氣": "気",
    "豐": "豊",
}

HOMONYM_GUARD_KEYS = (
    "龍山寺", "東照宮", "中國城", "中華街", "故宮", "天后宮", "媽祖廟", "文武廟",
    "迪士尼", "迪士尼樂園", "disney", "disneyland",
    "環球影城", "universal studios",
    "自由女神像", "自由女神", "海洋公園",
)
_OSM_SAR_CODES = {"HK", "MO"}
_INCOMPLETE_ZHUYIN_RE = re.compile(r"[\u3100-\u312F\u31A0-\u31BF]")
_HAS_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_JP_KANJI_MAP = (
    ("火車站", "駅"),
    ("車站", "駅"),
    ("澀", "渋"),
    ("廣", "広"),
    ("澤", "沢"),
    ("邊", "辺"),
    ("齋", "斎"),
    ("淺", "浅"),
    ("關", "関"),
    ("臺", "台"),
    ("鐵", "鉄"),
    ("學", "学"),
    ("國", "国"),
    ("櫻", "桜"),
    ("氣", "気"),
    ("豐", "豊"),
    ("繩", "縄"),
    ("霸", "覇"),
    ("橫", "横"),
    ("濱", "浜"),
    ("輕", "軽"),
    ("戶", "戸"),
    ("縣", "県"),
    ("區", "区"),
)


def normalize_cjk_chars(text: str) -> str:
    """純字元異體／繁簡／日文漢字正規化（不剝除『總店/本店/分店』尾詞，確保精確比對與本店區別度）"""
    if not text:
        return ""
    out = text.lower().strip()
    for char, equiv in CHAR_EQUIVALENTS.items():
        if char in out:
            out = out.replace(char, equiv)
    return out


def _jp_kanji_variant(query: str) -> Optional[str]:
    """為日本搜尋產生乾淨單語系日文漢字變體（絕不與原詞空白拼接，避免 Photon Operator.And 歸零）"""
    if not query:
        return None
    out = query.strip()
    for src, dst in _JP_KANJI_MAP:
        if src in out:
            out = out.replace(src, dst)
    return out if out and out != query.strip() else None


def normalize_extent(raw_extent: Any, source_format: str = "photon") -> Optional[List[float]]:
    """將 Photon [minLon, maxLat, maxLon, minLat] 或 Nominatim [minLat, maxLat, minLon, maxLon]
    統一正規化為 RFC 7946 / MapLibre [minLon, minLat, maxLon, maxLat]，恆滿足 extent[0]<=extent[2] 且 extent[1]<=extent[3]。
    """
    if not isinstance(raw_extent, (list, tuple)) or len(raw_extent) != 4:
        return None
    try:
        vals = [float(v) for v in raw_extent]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in vals):
        return None

    if source_format == "nominatim":
        south, north, west, east = vals
        min_lon, max_lon = (west, east) if west <= east else (east, west)
        min_lat, max_lat = (south, north) if south <= north else (north, south)
    else:
        lon1, lat1, lon2, lat2 = vals
        min_lon, max_lon = (lon1, lon2) if lon1 <= lon2 else (lon2, lon1)
        min_lat, max_lat = (lat1, lat2) if lat1 <= lat2 else (lat2, lat1)

    if not (-180.0 <= min_lon <= max_lon <= 180.0 and -90.0 <= min_lat <= max_lat <= 90.0):
        return None
    return [min_lon, min_lat, max_lon, max_lat]


def normalize_for_fuzzy(text: str) -> str:
    """標準化文字用於模糊比較（保留寺/站/神社/城等設施類別尾詞，防止『龍山寺』與『龍山站』跨類別碰撞）"""
    if not text:
        return ""
    text = text.lower().strip()
    # 僅在詞長充足 (>3) 時移除非改變設施語意之通用商業尾詞
    for suffix in ["分店", "本店", "總店", "店"]:
        if text.endswith(suffix) and len(text) - len(suffix) >= 2:
            text = text[:-len(suffix)]
            break
    # 字元標準化 (含 站 -> 駅 等同類別對齊)
    return normalize_cjk_chars(text)


# 🆕 P1-B: CJK 異體字搜尋展開（一→多）
# normalize_for_fuzzy 做的是「多→一」標準化（用於 LANDMARKS_DB 比對）
# expand_cjk_variants 做的是「一→多」展開（用於送給 Photon/Nominatim 的搜尋詞）
CJK_VARIANT_PAIRS = [
    ("台", "臺"),  # 台灣最高頻異體字
    ("裡", "裏"),
    ("峰", "峯"),
    ("線", "綫"),
    ("群", "羣"),
]

def expand_cjk_variants(query: str) -> list[str]:
    """生成 CJK 異體字搜尋變體（一→多展開）
    
    例：「台中一中」→ [「台中一中」, 「臺中一中」]
    不做笛卡爾積，每對只做單次替換，避免變體爆炸。
    """
    variants = {query}
    for a, b in CJK_VARIANT_PAIRS:
        if a in query:
            variants.add(query.replace(a, b))
        if b in query:
            variants.add(query.replace(b, a))
    return list(variants)


# 🌍 地理編碼雙引擎系統 (ArcGIS + Nominatim)

async def geocode_with_arcgis(place_name: str):
    """ArcGIS World Geocoding Service (精確度高，支援日本POI)"""
    if not ARCGIS_API_KEY:
        return None
    try:
        res = await HTTPX_CLIENT.get(
            "https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates",
            params={
                "SingleLine": place_name,
                "f": "json",
                "outFields": "PlaceName,Place_addr",
                "maxLocations": 1,
                "token": ARCGIS_API_KEY
            }
        )
        # 🆕 Use orjson for faster response parsing
        data = orjson.loads(res.content)
        if data.get("candidates"):
            loc = data["candidates"][0]["location"]
            attrs = data["candidates"][0].get("attributes", {})
            print(f"🗺️ ArcGIS: {place_name} → ({loc['y']:.4f}, {loc['x']:.4f})")
            return {
                "lat": loc["y"], 
                "lng": loc["x"],
                "name": attrs.get("PlaceName", ""),
                "address": attrs.get("Place_addr", place_name)
            }
    except Exception as e:
        print(f"⚠️ ArcGIS error for '{place_name}': {e}")
    return None


async def geocode_with_nominatim(place_name: str):
    """
    🔒 Nominatim 備援 (OpenStreetMap) - 目前已停用
    
    保留原因：未來如需結構化地址批次處理可啟用
    停用原因：對中文/日文地名搜尋效果差，改用 Photon
    
    如需重新啟用，將 geocode_place 中的 Photon 改回 Nominatim 即可
    """
    try:
        res = await HTTPX_CLIENT.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": place_name, 
                "format": "json", 
                "limit": 1,
                "accept-language": "zh-TW,zh,en"
            },
            headers={"User-Agent": "TabijiTravelPWA/1.0 (https://www.tabijiapp.com; contact@tabijiapp.com)"}
        )
        data = orjson.loads(res.content)
        if data and len(data) > 0:
            result = data[0]
            print(f"🌍 Nominatim: {place_name} → ({result['lat']}, {result['lon']})")
            return {
                "lat": float(result["lat"]), 
                "lng": float(result["lon"]),
                "name": result.get("display_name", place_name).split(",")[0],
                "address": result.get("display_name", "")
            }
    except Exception as e:
        print(f"🌍 Nominatim error for '{place_name}': {e}")
_NOMINATIM_LOCKS: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = weakref.WeakKeyDictionary()
_LAST_NOMINATIM_TS: float = 0.0
_NOMINATIM_CACHE: Dict[str, Any] = {}
_PHOTON_BREAKER_UNTIL: float = 0.0
_PHOTON_CONSECUTIVE_ERRORS: int = 0
_PHOTON_BREAKER_COOLDOWN_SEC: float = 15.0
_PHOTON_BREAKER_THRESHOLD: int = 2


def _get_nominatim_lock() -> asyncio.Lock:
    """依當前 asyncio Event Loop 分桶之 Nominatim 全域鎖（避免跨測試迴圈綁定錯誤與記憶體洩漏）"""
    loop = asyncio.get_running_loop()
    lock = _NOMINATIM_LOCKS.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _NOMINATIM_LOCKS[loop] = lock
    return lock


def _is_httpx_get_mocked() -> bool:
    """偵測 httpx.AsyncClient.get 是否處於單元測試 Mock 狀態（測試中跳過真實 1s sleep）"""
    get_fn = getattr(httpx.AsyncClient, "get", None)
    mod = getattr(type(get_fn), "__module__", "") if get_fn is not None else ""
    return "unittest.mock" in mod


async def _nominatim_rate_limit_wait() -> None:
    """強制公用 Nominatim 全域出站 <= 1 req/s（單元測試 Mock 狀態 0ms 放行）"""
    global _LAST_NOMINATIM_TS
    if _is_httpx_get_mocked():
        return
    now = time.monotonic()
    elapsed = now - _LAST_NOMINATIM_TS
    if _LAST_NOMINATIM_TS > 0.0 and elapsed < 1.0:
        await asyncio.sleep(1.0 - elapsed)
    _LAST_NOMINATIM_TS = time.monotonic()


def __reset_geocode_runtime_state_for_testing() -> None:
    """模組單例狀態測試重設介面（Core Invariant 5）"""
    global _LAST_NOMINATIM_TS, _PHOTON_BREAKER_UNTIL, _PHOTON_CONSECUTIVE_ERRORS
    _LAST_NOMINATIM_TS = 0.0
    _PHOTON_BREAKER_UNTIL = 0.0
    _PHOTON_CONSECUTIVE_ERRORS = 0
    _NOMINATIM_LOCKS.clear()
    _NOMINATIM_CACHE.clear()
    _DEAD_URL_CACHE.clear()
    if "TRANSLATION_CACHE" in globals():
        TRANSLATION_CACHE.clear()

async def _gemma_parse_address(address: str, user_key: str = None) -> dict:
    """使用 Gemma 3 27B 零成本暴力拆解地址為 Structured Query 參數"""
    api_key = user_key or (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return {}
        
    prompt = f"""You are an expert multilingual address parser. Decompose any address from any country into structured JSON for OpenStreetMap Nominatim.

RULES:
1. Output ONLY valid JSON. No markdown, no explanations.
2. Keys: "postalcode", "country", "state", "county", "city", "street"
3. "street" = house number + street name (e.g. "十全一路100號" or "1-1 Jingumae")
4. "state" = province, prefecture, or state-level division
5. "county" = district, ward (区/區), or county-level division
6. If a component is absent, use ""
7. Keep values in ORIGINAL language/script. Do NOT translate.

EXAMPLES:

Address: 807高雄市三民區十全一路100號
Output: {{"postalcode":"807","country":"台灣","state":"高雄市","county":"三民區","city":"","street":"十全一路100號"}}

Address: 〒150-0001 東京都渋谷区神宮前1丁目1番地
Output: {{"postalcode":"150-0001","country":"日本","state":"東京都","county":"渋谷区","city":"","street":"神宮前1丁目1番地"}}

Address: 1600 Amphitheatre Parkway, Mountain View, CA 94043, USA
Output: {{"postalcode":"94043","country":"USA","state":"CA","county":"","city":"Mountain View","street":"1600 Amphitheatre Parkway"}}

Address: Via della Conciliazione, 1, 00120 Città del Vaticano
Output: {{"postalcode":"00120","country":"Vatican City","state":"","county":"","city":"Città del Vaticano","street":"Via della Conciliazione 1"}}

Address: 25 ถนนสุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110
Output: {{"postalcode":"10110","country":"ไทย","state":"กรุงเทพมหานคร","county":"เขตคลองเตย","city":"แขวงคลองเตย","street":"25 ถนนสุขุมวิท"}}

Now parse:
Address: {address}
Output:"""
    
    try:
        raw = await call_extraction_server(prompt, intent_type="GEOCODE", api_key=api_key)
        if not raw or not str(raw).strip():
            return {}
        text = str(raw).strip()
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            text = json_match.group()
        data = json.loads(text)
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if v and isinstance(v, str)}
    except Exception as e:
        print(f"⚠️ Gemma Address Parse Error: {e}")
        return {}


_DEAD_URL_CACHE = {}


def _mask_gas_url_id(gas_url: str) -> str:
    """日誌脫敏：僅輸出 GAS 部署 ID 結尾 4 碼，嚴禁印出完整 GAS 網址。"""
    try:
        path = urlsplit(gas_url or "").path.rstrip("/")
        parts = [p for p in path.split("/") if p]
        if parts and parts[-1] in ("exec", "dev") and len(parts) >= 2:
            token = parts[-2]
        elif parts:
            token = parts[-1]
        else:
            token = ""
        return f"***{token[-4:]}" if len(token) >= 4 else "***"
    except Exception:
        return "***"


async def geocode_with_gas(place_name: str) -> dict | None:
    """🛡️ Tier 0: GAS 無代理伺服器輪詢引擎 (Zero-Cost Load Balancer)"""
    urls_str = os.getenv("GAS_GEOCODE_URLS", "").strip()
    if not urls_str:
        return None
        
    urls = [u.strip() for u in urls_str.split(",") if u.strip()]
    if not urls:
        return None
        
    random.shuffle(urls)
    now = time.time()
    
    for url in urls:
        # Check dead cache (12 hour penalty)
        if url in _DEAD_URL_CACHE and (now - _DEAD_URL_CACHE[url] < 43200):
            continue
            
        try:
            # GAS Web Apps return 302 redirects → must follow them
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as gas_client:
                res = await gas_client.get(url, params={"address": place_name})
            res.raise_for_status()
            data = res.json()
            
            if data and "results" in data and len(data["results"]) > 0:
                loc = data["results"][0]["geometry"]["location"]
                addr = data["results"][0].get("formatted_address", place_name)
                print(f"🌍 [Tier 0] GAS Proxy Hit: {place_name} -> ({loc['lat']:.4f}, {loc['lng']:.4f})")
                return {
                    "lat": loc["lat"],
                    "lng": loc["lng"],
                    "name": addr.split(",")[0],
                    "address": addr
                }
            elif data and data.get("error") and data.get("quota_exceeded"):
                print(f"⚠️ [Tier 0] GAS endpoint {_mask_gas_url_id(url)} Quota Exceeded. Banning URL for 12 hours.")
                _DEAD_URL_CACHE[url] = now
            elif data and "error_message" in data:
                print(f"⚠️ [Tier 0] GAS Maps API Error ({_mask_gas_url_id(url)}): {data['error_message']}")
                if "quota" in data['error_message'].lower() or "over_query_limit" in data.get("status", "").lower():
                    _DEAD_URL_CACHE[url] = now
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response is not None else None
            tag = _mask_gas_url_id(url)
            if status_code in (404, 410):
                _DEAD_URL_CACHE[url] = now
                print(f"⚠️ [Tier 0] GAS endpoint {tag} returned HTTP {status_code}. Banning URL for 12 hours.")
            else:
                print(f"⚠️ [Tier 0] GAS endpoint {tag} returned HTTP {status_code}.")
            continue
        except Exception as e:
            print(f"⚠️ [Tier 0] GAS Request Failed ({_mask_gas_url_id(url)}): {type(e).__name__}")
            continue
            
    return None


async def resolve_address_pipeline(address: str, user_gemini_key: str = None):
    """
    📍 [專用] 獨立結構化地址解析器 (Address Resolver)
    🆕 2026 v2.0: T0 GAS 木馬 → ArcGIS → Gemma Few-Shot + Nominatim 國碼鎖定 → Photon
                 全球 200+ 國動態 countrycodes 鎖定，Few-Shot 5 洲範例錨定。
    """
    clean_addr = address.strip()
    if not clean_addr:
        return None
        
    # [小螺絲] 移除亞洲過度沾黏的 3~5 碼郵遞區號 (ex: '105台北市...' -> '台北市...')
    # 只移除「緊接 CJK 字元」的亞洲黏著郵遞區號 (807高雄市 → 高雄市)
    # 不影響西方門牌 (1600 Amphitheatre) 與其他格式
    clean_addr = re.sub(r'^\d{3,5}(?=[\u4e00-\u9fff\u3400-\u4dbf])', '', clean_addr)
        
    # Check cache first (1 hour expiration)
    now = time.time()
    if clean_addr in _NOMINATIM_CACHE:
        cache_entry = _NOMINATIM_CACHE[clean_addr]
        if now - cache_entry["time"] < 3600:
            print(f"🌍 Geocode Cache HIT: {clean_addr}")
            return cache_entry["data"]

    # 🛡️ Tier 0: 零成本 GAS 木馬陣列 (首發無敵星星)
    gas_res = await geocode_with_gas(clean_addr)
    if gas_res:
        _NOMINATIM_CACHE[clean_addr] = { "time": time.time(), "data": gas_res }
        return gas_res

    # 🛡️ Tier 1: 企業級核武 ArcGIS (原首發)
    if ARCGIS_API_KEY:
        try:
            print(f"🌍 [Tier 1] Dispatching to ArcGIS for '{clean_addr}'")
            arcgis_res = await geocode_with_arcgis(clean_addr)
            if arcgis_res and "lat" in arcgis_res:
                result_data = {
                    "lat": arcgis_res["lat"],
                    "lng": arcgis_res["lng"],
                    "name": arcgis_res.get("name", ""),
                    "address": arcgis_res.get("address", clean_addr)
                }
                _NOMINATIM_CACHE[clean_addr] = { "time": time.time(), "data": result_data }
                print(f"🌍 [Tier 1] ArcGIS Hit: {clean_addr}")
                return result_data
            else:
                print(f"⚠️ [Tier 1] ArcGIS miss. Falling back to FOSS engines.")
        except Exception as e:
            print(f"⚠️ [Tier 1] ArcGIS Exception: {e}. Falling back to FOSS engines.")

    # 🧠 Gemma 3 降維解構（於取得 Nominatim 鎖之前執行，避免 AI 延遲阻塞並行的地圖搜尋 Nominatim 請求）
    structured_data = await _gemma_parse_address(clean_addr, user_key=user_gemini_key)

    # Throttle 1 request per second (For Nominatim — 與 smart_geocode_logic 共用同一全域節流器)
    async with _get_nominatim_lock():
        # Check cache again inside lock just in case it was fetched while waiting
        now = time.time()
        if clean_addr in _NOMINATIM_CACHE and (now - _NOMINATIM_CACHE[clean_addr]["time"] < 3600):
            return _NOMINATIM_CACHE[clean_addr]["data"]

        base_url = os.getenv("NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org/search").strip()
        user_agent = os.getenv("APP_USER_AGENT", "TabijiTravelPWA/1.0 (https://www.tabijiapp.com; contact@tabijiapp.com)")
        
        params = {
            "format": "geocodejson",
            "addressdetails": "1",
            "namedetails": "1",
            "entrances": "1",
            "accept-language": "zh-TW,zh,en",
            "limit": 1
        }
        
        if structured_data:
            print(f"🧠 Gemma parsed structure: {structured_data}")
            # 🌐 動態國家鎖定：將國名轉為 ISO 碼，注入 countrycodes 硬過濾
            iso_code = country_to_iso(structured_data.get("country", ""))
            if iso_code:
                params["countrycodes"] = iso_code
                print(f"🌐 Country Lock: '{structured_data['country']}' → countrycodes={iso_code}")
            # 強制禁止混用 q
            for k, v in structured_data.items():
                if k in ["postalcode", "country", "state", "county", "city", "street"]:
                    params[k] = v
        else:
            # Fallback to standard q
            params["q"] = clean_addr
            
        headers = {
            "User-Agent": user_agent,
        }

        try:
            def extract_nominatim_data(payload):
                if payload.get("features") and len(payload["features"]) > 0:
                    feat = payload["features"][0]
                    p = feat.get("properties", {}).get("geocoding", {})
                    g = feat.get("geometry", {}).get("coordinates", [0, 0])
                    return {
                        "lat": g[1], "lng": g[0],
                        "name": p.get("name", ""),
                        "address": p.get("label", clean_addr)
                    }
                return None

            result_data = None
            
            # 🛡️ Tier 2: Nominatim 精確打擊
            print(f"🌍 [Tier 2] Dispatching to Nominatim (Strict) for '{clean_addr}'")
            await _nominatim_rate_limit_wait()
            
            res = await HTTPX_CLIENT.get(base_url, params=params, headers=headers, timeout=8.0)
            res.raise_for_status()
            
            result_data = extract_nominatim_data(res.json())
            
            # 🛡️ Tier 3: Nominatim 降級打擊 (Dynamic Degradation)
            if not result_data:
                degraded_street = ""
                if structured_data and "street" in structured_data:
                    # 拔除「號/巷/弄/樓」等精確字元，退避到路名 (優化正則以防止 ReDoS)
                    degraded_street = re.sub(r'\d+[號巷弄樓Ff-][^,]*', '', structured_data["street"]).strip()
                else:
                    # 如果 AI 沒有作用，直接從原始字串退避 (優化正則以防止 ReDoS)
                    degraded_street = re.sub(r'\d+[號巷弄樓Ff-][^,]*', '', clean_addr).strip()
                    
                # 只有當退避後的字串不同且非空時，才進行降級打擊
                if degraded_street and ((structured_data and degraded_street != structured_data.get("street")) or (not structured_data and degraded_street != clean_addr)):
                    target_str = structured_data["street"] if structured_data else clean_addr
                    print(f"⚠️ [Tier 3] Nominatim miss. Degrading address '{target_str}' -> '{degraded_street}'")
                    
                    if structured_data:
                        params["street"] = degraded_street
                    else:
                        params["q"] = degraded_street
                        
                    await _nominatim_rate_limit_wait()
                    
                    res_deg = await HTTPX_CLIENT.get(base_url, params=params, headers=headers, timeout=8.0)
                    res_deg.raise_for_status()
                    result_data = extract_nominatim_data(res_deg.json())

            if result_data:
                _NOMINATIM_CACHE[clean_addr] = {"time": time.time(), "data": result_data}
                print(f"🌍 [Tier 2/3] Nominatim API Success: {clean_addr} -> {result_data['lat']}, {result_data['lng']}")
                return result_data
            else:
                # 🛡️ Tier 4: Nominatim 找不到精確門牌與道路，啟動 Photon 模糊搜尋保險絲
                print(f"⚠️ Nominatim completely missed. [Tier 4] Falling back to Photon for '{clean_addr}'")
                try:
                    photon_res = await geocode_with_photon(clean_addr, limit=1)
                    # 🛡️ Photon 雙波次打擊：原始字串失敗 → 拔掉門牌再試
                    if (not photon_res or len(photon_res) == 0) and degraded_street and degraded_street != clean_addr:
                        print(f"⚠️ [Tier 4] Photon missed original. Retrying with degraded: '{degraded_street}'")
                        photon_res = await geocode_with_photon(degraded_street, limit=1)
                    if photon_res and len(photon_res) > 0:
                        first_match = photon_res[0]
                        result_data = {
                            "lat": first_match["lat"],
                            "lng": first_match["lng"],
                            "name": first_match.get("name", ""),
                            "address": first_match.get("address", clean_addr)
                        }
                        _NOMINATIM_CACHE[clean_addr] = {
                            "time": time.time(),
                            "data": result_data
                        }
                        print(f"🌍 [Tier 4] Photon Fallback Success: {clean_addr} -> {result_data['lat']}, {result_data['lng']}")
                        return result_data
                except Exception as photon_err:
                    print(f"⚠️ [Tier 4] Photon Fallback failed: {photon_err}")
                
                # All engines failed
                print(f"❌ All geocoding engines failed for '{clean_addr}'")
                return None

        except httpx.HTTPStatusError as e:
            print(f"⚠️ Nominatim Status Error ({e.response.status_code}): {e}")
            raise  # Propagate to router
        except Exception as e:
            print(f"⚠️ Nominatim Generic Error: {e}")
            raise
            
    return None


def sanitize_bbox(bbox_str: Optional[str]) -> Optional[str]:
    """清洗並校驗 MapLibre Viewport BBOX: minLon,minLat,maxLon,maxLat
    
    防禦注入與換日線跨越 (Antimeridian Crossing) 導致 Photon HTTP 400
    """
    if not bbox_str or not isinstance(bbox_str, str):
        return None
    try:
        parts = [float(p.strip()) for p in bbox_str.split(",")]
        if len(parts) != 4:
            return None
        min_lon, min_lat, max_lon, max_lat = parts
        
        if not (-90.0 <= min_lat <= 90.0 and -90.0 <= max_lat <= 90.0):
            return None
        if not (-180.0 <= min_lon <= 180.0 and -180.0 <= max_lon <= 180.0):
            return None
        if min_lat > max_lat or min_lon > max_lon:
            return None
            
        return f"{min_lon:.5f},{min_lat:.5f},{max_lon:.5f},{max_lat:.5f}"
    except Exception:
        return None


async def geocode_with_photon(
    place_name: str,
    limit: int = 25,
    lat: float = None, 
    lng: float = None, 
    zoom: float = None, 
    location_bias_scale: float = None, 
    osm_tag: str = None, 
    country_code: str = None,
    bbox: str = None
):
    """Photon 地理編碼 (基於 OpenStreetMap + Elasticsearch，模糊搜尋強)
    
    Args:
        lat, lng: 若提供，將優先返回附近的結果 (Location Bias)
        zoom: 縮放層級，轉整數 (0..18) 顯式傳給 Photon 並驅動正確方向的 location_bias_scale
        location_bias_scale: 0.0 ~ 1.0，Photon 原始語意為全球重要度權重，(1 - scale) 為距離權重
        osm_tag: 僅在呼叫端顯式指定時傳遞（如 'place:country'），不自動硬過濾一般搜尋
        bbox: minLon,minLat,maxLon,maxLat 地圖視窗邊界過濾
    """
    global _PHOTON_BREAKER_UNTIL, _PHOTON_CONSECUTIVE_ERRORS
    query_text = (place_name or "").strip()
    if not query_text:
        return None

    is_mocked = _is_httpx_get_mocked()
    if not is_mocked and time.monotonic() < _PHOTON_BREAKER_UNTIL:
        log_debug(f"[Photon] Circuit breaker open; skipping '{query_text}'")
        return None

    safe_limit = max(1, min(50, int(limit or 25)))
    try:
        user_agent = os.getenv("APP_USER_AGENT", "TabijiTravelPWA/1.0 (https://www.tabijiapp.com; contact@tabijiapp.com)")
        async with httpx.AsyncClient(timeout=4.0, headers={"User-Agent": user_agent}) as client:
            params: Dict[str, Any] = {
                "q": query_text,
                "limit": safe_limit,
            }
            
            # 🆕 Country Bias（OSM/Photon 對 HK/MO 特別行政區不支援 countrycode=hk/mo，改以區域 bbox 約束防零結果黑洞）
            if country_code:
                cc_up = country_code.strip().upper()
                if cc_up in _OSM_SAR_CODES:
                    if not bbox and cc_up in COUNTRY_BOUNDS:
                        b = COUNTRY_BOUNDS[cc_up]
                        sar_bbox = sanitize_bbox(
                            f"{b['lng_min'] - 0.05},{b['lat_min'] - 0.05},{b['lng_max'] + 0.05},{b['lat_max'] + 0.05}"
                        )
                        if sar_bbox:
                            params["bbox"] = sar_bbox
                else:
                    params["countrycode"] = cc_up.lower()
            
            # 僅保留呼叫端顯式指定的 osm_tag（如 global_task 的 place:country）
            if osm_tag:
                params["osm_tag"] = osm_tag
                
            # 🆕 BBOX Viewport Bias
            if bbox:
                clean_bbox = sanitize_bbox(bbox)
                if clean_bbox:
                    params["bbox"] = clean_bbox
                
            # 🆕 Location Bias + 顯式整數 zoom + 校正後 location_bias_scale
            if lat is not None and lng is not None:
                params["lat"] = lat
                params["lon"] = lng

            int_zoom: Optional[int] = None
            if zoom is not None:
                try:
                    z_float = float(zoom)
                    if math.isfinite(z_float):
                        int_zoom = max(0, min(18, int(round(z_float))))
                        params["zoom"] = int_zoom
                except (TypeError, ValueError):
                    int_zoom = None

            if location_bias_scale is not None:
                params["location_bias_scale"] = location_bias_scale
            elif int_zoom is not None and lat is not None and lng is not None:
                # Photon 公式: scale = 全球重要度權重, (1 - scale) = 距離權重
                if int_zoom >= 14:
                    params["location_bias_scale"] = 0.2
                elif int_zoom > 10:
                    params["location_bias_scale"] = 0.4
                else:
                    params["location_bias_scale"] = 0.7

            res = await client.get(
                "https://photon.komoot.io/api/",
                params=params
            )
            status_code = getattr(res, "status_code", 200)
            if isinstance(status_code, int) and status_code != 200:
                print(f"[Photon] HTTP {status_code} for '{query_text}'")
                if not is_mocked and (status_code == 429 or status_code >= 500):
                    _PHOTON_CONSECUTIVE_ERRORS += 1
                    if status_code in (429, 503) or _PHOTON_CONSECUTIVE_ERRORS >= _PHOTON_BREAKER_THRESHOLD:
                        _PHOTON_BREAKER_UNTIL = time.monotonic() + _PHOTON_BREAKER_COOLDOWN_SEC
                return None

            _PHOTON_CONSECUTIVE_ERRORS = 0
            _PHOTON_BREAKER_UNTIL = 0.0

            data = orjson.loads(res.content)
            if data.get("features") and len(data["features"]) > 0:
                results = []
                for feature in data["features"]:
                    props = feature.get("properties", {})
                    coords = feature.get("geometry", {}).get("coordinates", [0, 0])
                    if not isinstance(coords, (list, tuple)) or len(coords) < 2:
                        continue
                    
                    # 組合地址
                    address_parts = []
                    for key in ["country", "state", "city", "district", "street", "housenumber"]:
                        if props.get(key):
                            address_parts.append(str(props[key]))
                    
                    extra = props.get("extra") or {}
                    admin_lvl = extra.get("admin_level") if isinstance(extra, dict) else None
                    if not admin_lvl and "admin_level" in props:
                        admin_lvl = props.get("admin_level")

                    raw_extent = props.get("extent") or feature.get("bbox")
                    norm_extent = normalize_extent(raw_extent, source_format="photon")
                    address_str = ", ".join(address_parts) if address_parts else props.get("name", "")

                    results.append({
                        "lat": coords[1],
                        "lng": coords[0],
                        "name": props.get("name", query_text),
                        "display_name": address_str,
                        "address": address_str,
                        "type": props.get("osm_value", "place"),
                        "osm_key": props.get("osm_key"),
                        "osm_id": props.get("osm_id"),
                        "osm_type": props.get("osm_type"),
                        "city": props.get("city"),
                        "state": props.get("state"),
                        "country": props.get("country"),
                        "admin_level": int(admin_lvl) if str(admin_lvl).isdigit() else None,
                        "extent": norm_extent,
                        "importance": props.get("importance")
                    })
                
                if results:
                    print(f"[Photon] {query_text} -> {len(results)} results")
                    return results
    except Exception as e:
        print(f"[Photon] Error for '{query_text}': {type(e).__name__}: {e!r}")
        if not is_mocked:
            _PHOTON_CONSECUTIVE_ERRORS += 1
            if _PHOTON_CONSECUTIVE_ERRORS >= _PHOTON_BREAKER_THRESHOLD:
                _PHOTON_BREAKER_UNTIL = time.monotonic() + _PHOTON_BREAKER_COOLDOWN_SEC
    return None


# 🆕 P3: Overpass API 名稱搜尋（CJK 友好的最後防線）
async def search_overpass_by_name(
    name: str,
    country_code: str = None,
    limit: int = 3
) -> list | None:
    """透過 OSM 原始資料的 name/name:zh tag 進行 regex 匹配，
    繞過 Photon/Nominatim 的分詞限制。
    
    只在 Photon+Nominatim 結果為空時觸發，單次超時收斂至 3.5s。
    """
    clean_name = re.sub(r'["\';\[\]\(\)\{\}\<\>\r\n]', '', (name or "")).strip()[:64]
    if not clean_name:
        return None
    safe_limit = max(1, min(20, int(limit or 3)))

    # 生成搜尋 regex（包含異體字變體）
    variants = expand_cjk_variants(clean_name)
    name_regex = "|".join(re.escape(v) for v in variants if v)
    
    # 建構 area 限制（如果有國碼，僅允許兩碼英文字母防止 QL 注入）
    area_filter = ""
    scope = ""
    if country_code:
        cc_clean = re.sub(r'[^A-Za-z]', '', str(country_code)).upper()
        if len(cc_clean) == 2:
            area_filter = f'area["ISO3166-1"="{cc_clean}"]->.searchArea;'
            scope = "(area.searchArea)"
    
    query = f"""
    [out:json][timeout:4];
    {area_filter}
    (
      nwr["name"~"{name_regex}",i]{scope};
      nwr["name:zh"~"{name_regex}",i]{scope};
      nwr["alt_name"~"{name_regex}",i]{scope};
    );
    out center {safe_limit};
    """
    
    try:
        async with httpx.AsyncClient(timeout=3.5) as client:
            res = await client.post(
                "https://overpass-api.de/api/interpreter",
                data={"data": query},
                headers={"User-Agent": "TabijiTravelPWA/1.0 (https://www.tabijiapp.com; contact@tabijiapp.com)"}
            )
            op_status = getattr(res, "status_code", 200)
            if isinstance(op_status, int) and op_status != 200:
                print(f"[Overpass] HTTP {op_status} for '{clean_name}'")
                return None
            data = orjson.loads(res.content)
            elements = data.get("elements", [])
            if not elements:
                return None
            
            results = []
            for el in elements[:safe_limit]:
                tags = el.get("tags", {})
                el_lat = el.get("lat") or el.get("center", {}).get("lat")
                el_lng = el.get("lon") or el.get("center", {}).get("lon")
                if not el_lat or not el_lng:
                    continue
                
                display_name = (
                    tags.get("name:zh") or
                    tags.get("name") or
                    tags.get("name:en") or
                    clean_name
                )
                addr_full = tags.get("addr:full", "")
                results.append({
                    "lat": el_lat, "lng": el_lng,
                    "name": display_name,
                    "display_name": addr_full or display_name,
                    "address": addr_full,
                    "type": tags.get("amenity") or tags.get("tourism") or "place",
                    "osm_id": el.get("id"),
                    "osm_type": el.get("type"),
                    "source": "overpass"
                })
            
            if results:
                print(f"[Overpass] {clean_name} -> {len(results)} results")
            return results or None
    except Exception as e:
        print(f"[Overpass] Error for '{clean_name}': {type(e).__name__}: {e!r}")
        return None


async def reverse_geocode_with_photon(lat: float, lng: float):
    """Photon 反向地理編碼（座標 → 地名）"""
    try:
        user_agent = os.getenv("APP_USER_AGENT", "TabijiTravelPWA/1.0 (https://www.tabijiapp.com; contact@tabijiapp.com)")
        res = await HTTPX_CLIENT.get(
            "https://photon.komoot.io/reverse",
            params={"lat": lat, "lon": lng},
            headers={"User-Agent": user_agent}
        )
        data = orjson.loads(res.content)
        if data.get("features") and len(data["features"]) > 0:
            props = data["features"][0].get("properties", {})
            address_parts = []
            for key in ["country", "state", "city", "district", "street", "housenumber"]:
                if props.get(key):
                    address_parts.append(props[key])
            
            return {
                "name": props.get("name", "Unknown"),
                "address": ", ".join(address_parts) if address_parts else "Unknown"
            }
    except Exception as e:
        print(f"🔍 Photon reverse error: {e}")
    return None


async def reverse_geocode_with_ai_enhancement(lat: float, lng: float, api_key: str = None):
    """
    🆕 AI 增強反向地理編碼
    
    使用 gemma-3-27b-it 提供：
    1. 中文友好名稱
    2. 地點類型分類
    3. 一句話描述
    
    Args:
        lat, lng: 座標
        api_key: Gemini API Key (可選，無則返回基本結果)
    
    Returns:
        {name, address, display_name?, type?, description?}
    """
    # Step 1: Photon 原生查詢
    base_result = await reverse_geocode_with_photon(lat, lng)
    
    if not base_result:
        return {"name": "Unknown", "address": "", "lat": lat, "lng": lng}
    
    # 如果沒有 API key，返回基本結果
    if not api_key:
        return {**base_result, "lat": lat, "lng": lng}
    
    # Step 2: AI 增強 (中文優化顯示)
    try:
        prompt = f"""根據座標 ({lat:.6f}, {lng:.6f}) 和地名 "{base_result.get('name', 'Unknown')}"，
        地址：{base_result.get('address', '')}

        請提供：
        1. display_name: 中文友好名稱（如果已經是中文則優化顯示）
        2. type: 地點類型（餐廳/景點/交通站/購物/住宿/其他）
        3. description: 一句話描述（20字內）

        嚴格按以下 JSON 格式回傳，不要額外說明：
        {{"display_name": "...", "type": "...", "description": "..."}}"""

        # 🆕 傳入 api_key 確保 BYOK 模式正常運作
        raw = await call_extraction_server(prompt, intent_type="GEOCODE", api_key=api_key)
        if not raw or not str(raw).strip():
            return {**base_result, "lat": lat, "lng": lng}
        text = str(raw).strip()
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            text = json_match.group()
        
        # 🆕 Use orjson for faster AI response parsing
        enhanced = orjson.loads(text)
        
        result = {
            **base_result,
            "lat": lat,
            "lng": lng,
            "display_name": enhanced.get("display_name", base_result.get("name")),
            "type": enhanced.get("type", "其他"),
            "description": enhanced.get("description", "")
        }
        print(f"🤖 AI 增強反向地理: {base_result.get('name')} → {result.get('display_name')}")
        return result
        
    except Exception as e:
        print(f"🤖 AI 增強失敗，返回基本結果: {e}")
        return {**base_result, "lat": lat, "lng": lng}


async def geocode_place(place_name: str, lat: float = None, lng: float = None):
    """智能地理編碼：ArcGIS 優先，Photon 備援"""

    # 1. 優先嘗試 ArcGIS (精確度高)
    if ARCGIS_API_KEY:
        result = await geocode_with_arcgis(place_name)
        if result:
            return result
        print(f"⚠️ ArcGIS 查無結果，降級到 Photon...")
    
    # 2. 降級到 Photon（取代 Nominatim）
    photon_results = await geocode_with_photon(place_name, limit=1, lat=lat, lng=lng)
    if photon_results:
        first = photon_results[0]
        return {"lat": first["lat"], "lng": first["lng"]}
    
    return None


# 🧠 智能地理編碼系統

# 國家邊界框（用於過濾搜尋結果）
COUNTRY_BOUNDS = {
    "JP": {"lat_min": 20.4, "lat_max": 45.5, "lng_min": 122.9, "lng_max": 154.0, "lang": "ja", "name": "日本"},
    "KR": {"lat_min": 33.1, "lat_max": 38.6, "lng_min": 124.6, "lng_max": 132.0, "lang": "ko", "name": "韓國"},
    "TW": {"lat_min": 21.8, "lat_max": 25.3, "lng_min": 119.3, "lng_max": 122.1, "lang": "zh-TW", "name": "台灣"},
    "TH": {"lat_min": 5.6, "lat_max": 20.5, "lng_min": 97.3, "lng_max": 105.6, "lang": "th", "name": "泰國"},
    "VN": {"lat_min": 8.2, "lat_max": 23.4, "lng_min": 102.1, "lng_max": 109.5, "lang": "vi", "name": "越南"},
    "SG": {"lat_min": 1.15, "lat_max": 1.47, "lng_min": 103.6, "lng_max": 104.0, "lang": "en", "name": "新加坡"},
    "HK": {"lat_min": 22.15, "lat_max": 22.56, "lng_min": 113.8, "lng_max": 114.4, "lang": "zh-HK", "name": "香港"},
    "US": {"lat_min": 24.5, "lat_max": 49.4, "lng_min": -125.0, "lng_max": -66.9, "lang": "en", "name": "美國"},
    "GB": {"lat_min": 49.9, "lat_max": 60.9, "lng_min": -8.6, "lng_max": 1.8, "lang": "en", "name": "英國"},
    "FR": {"lat_min": 41.3, "lat_max": 51.1, "lng_min": -5.1, "lng_max": 9.6, "lang": "fr", "name": "法國"},
    "IT": {"lat_min": 35.5, "lat_max": 47.1, "lng_min": 6.6, "lng_max": 18.5, "lang": "it", "name": "義大利"},
    "DE": {"lat_min": 47.3, "lat_max": 55.1, "lng_min": 5.9, "lng_max": 15.0, "lang": "de", "name": "德國"},
    "ES": {"lat_min": 36.0, "lat_max": 43.8, "lng_min": -9.3, "lng_max": 3.3, "lang": "es", "name": "西班牙"},
    "CH": {"lat_min": 45.8, "lat_max": 47.8, "lng_min": 5.9, "lng_max": 10.5, "lang": "de", "name": "瑞士"},
    "IS": {"lat_min": 63.3, "lat_max": 66.6, "lng_min": -24.5, "lng_max": -13.5, "lang": "is", "name": "冰島"},
    "AU": {"lat_min": -43.7, "lat_max": -10.0, "lng_min": 113.3, "lng_max": 153.6, "lang": "en", "name": "澳洲"},
    "CA": {"lat_min": 41.7, "lat_max": 83.1, "lng_min": -141.0, "lng_max": -52.6, "lang": "en", "name": "加拿大"},
    "MY": {"lat_min": 0.8, "lat_max": 7.4, "lng_min": 99.6, "lng_max": 119.3, "lang": "ms", "name": "馬來西亞"},
    "ID": {"lat_min": -11.0, "lat_max": 6.1, "lng_min": 95.0, "lng_max": 141.0, "lang": "id", "name": "印尼"},
    "PH": {"lat_min": 4.6, "lat_max": 21.3, "lng_min": 116.9, "lng_max": 126.6, "lang": "en", "name": "菲律賓"},
    "MO": {"lat_min": 22.10, "lat_max": 22.22, "lng_min": 113.52, "lng_max": 113.60, "lang": "zh-HK", "name": "澳門"},
    "FI": {"lat_min": 59.4, "lat_max": 70.1, "lng_min": 19.4, "lng_max": 31.6, "lang": "fi", "name": "芬蘭"},
    "SE": {"lat_min": 55.3, "lat_max": 69.1, "lng_min": 10.9, "lng_max": 24.2, "lang": "sv", "name": "瑞典"},
    "NO": {"lat_min": 57.9, "lat_max": 71.2, "lng_min": 4.5, "lng_max": 31.1, "lang": "no", "name": "挪威"},
    "DK": {"lat_min": 54.5, "lat_max": 57.8, "lng_min": 8.0, "lng_max": 15.2, "lang": "da", "name": "丹麥"},
    "NL": {"lat_min": 50.7, "lat_max": 53.6, "lng_min": 3.3, "lng_max": 7.3, "lang": "nl", "name": "荷蘭"},
    "BE": {"lat_min": 49.4, "lat_max": 51.6, "lng_min": 2.5, "lng_max": 6.4, "lang": "fr", "name": "比利時"},
    "AT": {"lat_min": 46.3, "lat_max": 49.1, "lng_min": 9.5, "lng_max": 17.2, "lang": "de", "name": "奧地利"},
    "CZ": {"lat_min": 48.5, "lat_max": 51.1, "lng_min": 12.0, "lng_max": 18.9, "lang": "cs", "name": "捷克"},
    "PL": {"lat_min": 49.0, "lat_max": 54.9, "lng_min": 14.1, "lng_max": 24.2, "lang": "pl", "name": "波蘭"},
    "PT": {"lat_min": 36.9, "lat_max": 42.2, "lng_min": -9.6, "lng_max": -6.1, "lang": "pt", "name": "葡萄牙"},
    "GR": {"lat_min": 34.8, "lat_max": 41.8, "lng_min": 19.3, "lng_max": 29.7, "lang": "el", "name": "希臘"},
    "HU": {"lat_min": 45.7, "lat_max": 48.6, "lng_min": 16.1, "lng_max": 22.9, "lang": "hu", "name": "匈牙利"},
    "HR": {"lat_min": 42.3, "lat_max": 46.6, "lng_min": 13.4, "lng_max": 19.5, "lang": "hr", "name": "克羅埃西亞"},
    "IE": {"lat_min": 51.4, "lat_max": 55.4, "lng_min": -10.5, "lng_max": -5.9, "lang": "en", "name": "愛爾蘭"},
    "NZ": {"lat_min": -47.3, "lat_max": -34.3, "lng_min": 166.4, "lng_max": 178.6, "lang": "en", "name": "紐西蘭"},
    "TR": {"lat_min": 35.8, "lat_max": 42.1, "lng_min": 25.6, "lng_max": 44.9, "lang": "tr", "name": "土耳其"},
    "AE": {"lat_min": 22.6, "lat_max": 26.2, "lng_min": 51.5, "lng_max": 56.4, "lang": "ar", "name": "阿聯酋"},
    "PE": {"lat_min": -18.4, "lat_max": -0.0, "lng_min": -81.4, "lng_max": -68.6, "lang": "es", "name": "秘魯"},
    "MX": {"lat_min": 14.5, "lat_max": 32.8, "lng_min": -118.4, "lng_max": -86.7, "lang": "es", "name": "墨西哥"},
    "BR": {"lat_min": -33.8, "lat_max": 5.3, "lng_min": -74.0, "lng_max": -34.7, "lang": "pt", "name": "巴西"},
    # 🆕 擴充高頻旅遊國家邊界框 (80+ 國，覆蓋歐亞美非大洋洲)
    "CN": {"lat_min": 18.0, "lat_max": 53.6, "lng_min": 73.5, "lng_max": 135.0, "lang": "zh", "name": "中國"},
    "LU": {"lat_min": 49.4, "lat_max": 50.2, "lng_min": 5.7, "lng_max": 6.6, "lang": "fr", "name": "盧森堡"},
    "SK": {"lat_min": 47.7, "lat_max": 49.6, "lng_min": 16.8, "lng_max": 22.6, "lang": "sk", "name": "斯洛伐克"},
    "SI": {"lat_min": 45.4, "lat_max": 46.9, "lng_min": 13.3, "lng_max": 16.6, "lang": "sl", "name": "斯洛維尼亞"},
    "RO": {"lat_min": 43.6, "lat_max": 48.3, "lng_min": 20.2, "lng_max": 29.7, "lang": "ro", "name": "羅馬尼亞"},
    "BG": {"lat_min": 41.2, "lat_max": 44.2, "lng_min": 22.3, "lng_max": 28.6, "lang": "bg", "name": "保加利亞"},
    "RS": {"lat_min": 42.2, "lat_max": 46.2, "lng_min": 18.8, "lng_max": 23.0, "lang": "sr", "name": "塞爾維亞"},
    "EE": {"lat_min": 57.5, "lat_max": 59.8, "lng_min": 21.7, "lng_max": 28.2, "lang": "et", "name": "愛沙尼亞"},
    "LV": {"lat_min": 55.6, "lat_max": 58.1, "lng_min": 20.9, "lng_max": 28.2, "lang": "lv", "name": "拉脫維亞"},
    "LT": {"lat_min": 53.9, "lat_max": 56.5, "lng_min": 20.9, "lng_max": 26.9, "lang": "lt", "name": "立陶宛"},
    "MT": {"lat_min": 35.8, "lat_max": 36.1, "lng_min": 14.1, "lng_max": 14.6, "lang": "en", "name": "馬爾他"},
    "CY": {"lat_min": 34.6, "lat_max": 35.7, "lng_min": 32.2, "lng_max": 34.6, "lang": "el", "name": "賽普勒斯"},
    "EG": {"lat_min": 22.0, "lat_max": 31.7, "lng_min": 24.7, "lng_max": 36.9, "lang": "ar", "name": "埃及"},
    "MA": {"lat_min": 27.6, "lat_max": 36.0, "lng_min": -13.2, "lng_max": -1.0, "lang": "fr", "name": "摩洛哥"},
    "ZA": {"lat_min": -34.9, "lat_max": -22.1, "lng_min": 16.4, "lng_max": 32.9, "lang": "en", "name": "南非"},
    "KE": {"lat_min": -4.7, "lat_max": 5.0, "lng_min": 33.9, "lng_max": 41.9, "lang": "en", "name": "肯亞"},
    "TZ": {"lat_min": -11.8, "lat_max": -0.9, "lng_min": 29.3, "lng_max": 40.5, "lang": "en", "name": "坦尚尼亞"},
    "AR": {"lat_min": -55.1, "lat_max": -21.7, "lng_min": -73.6, "lng_max": -53.6, "lang": "es", "name": "阿根廷"},
    "CL": {"lat_min": -56.0, "lat_max": -17.5, "lng_min": -75.7, "lng_max": -66.4, "lang": "es", "name": "智利"},
    "CO": {"lat_min": -4.3, "lat_max": 12.5, "lng_min": -79.1, "lng_max": -66.8, "lang": "es", "name": "哥倫比亞"},
    "CR": {"lat_min": 8.0, "lat_max": 11.2, "lng_min": -86.0, "lng_max": -82.5, "lang": "es", "name": "哥斯大黎加"},
    "IN": {"lat_min": 6.7, "lat_max": 35.6, "lng_min": 68.1, "lng_max": 97.4, "lang": "en", "name": "印度"},
    "LK": {"lat_min": 5.9, "lat_max": 9.9, "lng_min": 79.6, "lng_max": 81.9, "lang": "en", "name": "斯里蘭卡"},
    "NP": {"lat_min": 26.3, "lat_max": 30.5, "lng_min": 80.0, "lng_max": 88.2, "lang": "en", "name": "尼泊爾"},
    "KH": {"lat_min": 10.4, "lat_max": 14.7, "lng_min": 102.3, "lng_max": 107.7, "lang": "km", "name": "柬埔寨"},
    "LA": {"lat_min": 13.9, "lat_max": 22.5, "lng_min": 100.0, "lng_max": 107.7, "lang": "lo", "name": "寮國"},
    "MM": {"lat_min": 9.7, "lat_max": 28.6, "lng_min": 92.1, "lng_max": 101.2, "lang": "my", "name": "緬甸"},
    "BN": {"lat_min": 4.0, "lat_max": 5.1, "lng_min": 114.0, "lng_max": 115.4, "lang": "ms", "name": "汶萊"},
    "IL": {"lat_min": 29.4, "lat_max": 33.4, "lng_min": 34.2, "lng_max": 35.9, "lang": "he", "name": "以色列"},
    "JO": {"lat_min": 29.1, "lat_max": 33.4, "lng_min": 34.9, "lng_max": 39.3, "lang": "ar", "name": "約旦"},
    "QA": {"lat_min": 24.4, "lat_max": 26.2, "lng_min": 50.7, "lng_max": 51.7, "lang": "ar", "name": "卡達"},
    "SA": {"lat_min": 16.3, "lat_max": 32.2, "lng_min": 34.5, "lng_max": 55.7, "lang": "ar", "name": "沙烏地阿拉伯"},
    "OM": {"lat_min": 16.6, "lat_max": 26.4, "lng_min": 52.0, "lng_max": 59.9, "lang": "ar", "name": "阿曼"},
    "GE": {"lat_min": 41.0, "lat_max": 43.6, "lng_min": 40.0, "lng_max": 46.8, "lang": "en", "name": "喬治亞"},
    "MV": {"lat_min": -0.7, "lat_max": 7.1, "lng_min": 72.6, "lng_max": 73.8, "lang": "en", "name": "馬爾地夫"},
    "FJ": {"lat_min": -19.2, "lat_max": -16.0, "lng_min": 177.0, "lng_max": 180.0, "lang": "en", "name": "斐濟"},
    "MC": {"lat_min": 43.7, "lat_max": 43.8, "lng_min": 7.4, "lng_max": 7.45, "lang": "fr", "name": "摩納哥"},
    "VA": {"lat_min": 41.89, "lat_max": 41.91, "lng_min": 12.44, "lng_max": 12.46, "lang": "it", "name": "梵蒂岡"},
    "LI": {"lat_min": 47.04, "lat_max": 47.27, "lng_min": 9.47, "lng_max": 9.64, "lang": "de", "name": "列支敦士登"},
    "AD": {"lat_min": 42.42, "lat_max": 42.66, "lng_min": 1.40, "lng_max": 1.79, "lang": "es", "name": "安道爾"},
}

# 🌐 高頻旅遊次級商圈／行政區空間錨點（用於「新宿一蘭拉麵」與 Search Fusion 精準錨定，取代盲灌東京）
_SUBDISTRICT_ANCHORS: Dict[str, Dict[str, Any]] = {
    "新宿": {"lat": 35.6938, "lng": 139.7034, "country": "JP", "en": "Shinjuku"},
    "shinjuku": {"lat": 35.6938, "lng": 139.7034, "country": "JP", "en": "Shinjuku"},
    "澀谷": {"lat": 35.6580, "lng": 139.7016, "country": "JP", "en": "Shibuya"},
    "渋谷": {"lat": 35.6580, "lng": 139.7016, "country": "JP", "en": "Shibuya"},
    "shibuya": {"lat": 35.6580, "lng": 139.7016, "country": "JP", "en": "Shibuya"},
    "淺草": {"lat": 35.7148, "lng": 139.7967, "country": "JP", "en": "Asakusa"},
    "asakusa": {"lat": 35.7148, "lng": 139.7967, "country": "JP", "en": "Asakusa"},
    "銀座": {"lat": 35.6717, "lng": 139.7649, "country": "JP", "en": "Ginza"},
    "ginza": {"lat": 35.6717, "lng": 139.7649, "country": "JP", "en": "Ginza"},
    "上野": {"lat": 35.7141, "lng": 139.7774, "country": "JP", "en": "Ueno"},
    "ueno": {"lat": 35.7141, "lng": 139.7774, "country": "JP", "en": "Ueno"},
    "池袋": {"lat": 35.7295, "lng": 139.7109, "country": "JP", "en": "Ikebukuro"},
    "ikebukuro": {"lat": 35.7295, "lng": 139.7109, "country": "JP", "en": "Ikebukuro"},
    "秋葉原": {"lat": 35.7023, "lng": 139.7745, "country": "JP", "en": "Akihabara"},
    "akihabara": {"lat": 35.7023, "lng": 139.7745, "country": "JP", "en": "Akihabara"},
    "原宿": {"lat": 35.6702, "lng": 139.7027, "country": "JP", "en": "Harajuku"},
    "harajuku": {"lat": 35.6702, "lng": 139.7027, "country": "JP", "en": "Harajuku"},
    "六本木": {"lat": 35.6628, "lng": 139.7313, "country": "JP", "en": "Roppongi"},
    "roppongi": {"lat": 35.6628, "lng": 139.7313, "country": "JP", "en": "Roppongi"},
    "品川": {"lat": 35.6284, "lng": 139.7387, "country": "JP", "en": "Shinagawa"},
    "shinagawa": {"lat": 35.6284, "lng": 139.7387, "country": "JP", "en": "Shinagawa"},
    "難波": {"lat": 34.6659, "lng": 135.5013, "country": "JP", "en": "Namba"},
    "namba": {"lat": 34.6659, "lng": 135.5013, "country": "JP", "en": "Namba"},
    "梅田": {"lat": 34.7055, "lng": 135.4983, "country": "JP", "en": "Umeda"},
    "umeda": {"lat": 34.7055, "lng": 135.4983, "country": "JP", "en": "Umeda"},
    "心齋橋": {"lat": 34.6748, "lng": 135.5009, "country": "JP", "en": "Shinsaibashi"},
    "shinsaibashi": {"lat": 34.6748, "lng": 135.5009, "country": "JP", "en": "Shinsaibashi"},
    "道頓堀": {"lat": 34.6687, "lng": 135.5013, "country": "JP", "en": "Dotonbori"},
    "dotonbori": {"lat": 34.6687, "lng": 135.5013, "country": "JP", "en": "Dotonbori"},
    "明洞": {"lat": 37.5636, "lng": 126.9850, "country": "KR", "en": "Myeongdong"},
    "myeongdong": {"lat": 37.5636, "lng": 126.9850, "country": "KR", "en": "Myeongdong"},
    "弘大": {"lat": 37.5563, "lng": 126.9237, "country": "KR", "en": "Hongdae"},
    "hongdae": {"lat": 37.5563, "lng": 126.9237, "country": "KR", "en": "Hongdae"},
    "東大門": {"lat": 37.5662, "lng": 127.0095, "country": "KR", "en": "Dongdaemun"},
    "dongdaemun": {"lat": 37.5662, "lng": 127.0095, "country": "KR", "en": "Dongdaemun"},
    "江南": {"lat": 37.4979, "lng": 127.0276, "country": "KR", "en": "Gangnam"},
    "gangnam": {"lat": 37.4979, "lng": 127.0276, "country": "KR", "en": "Gangnam"},
    "西門町": {"lat": 25.0424, "lng": 121.5081, "country": "TW", "en": "Ximending"},
    "ximending": {"lat": 25.0424, "lng": 121.5081, "country": "TW", "en": "Ximending"},
    "信義區": {"lat": 25.0330, "lng": 121.5654, "country": "TW", "en": "Xinyi"},
    "萬華": {"lat": 25.0352, "lng": 121.4998, "country": "TW", "en": "Wanhua"},
    "士林": {"lat": 25.0928, "lng": 121.5246, "country": "TW", "en": "Shilin"},
    "大安": {"lat": 25.0267, "lng": 121.5435, "country": "TW", "en": "Daan"},
    "鳳山": {"lat": 22.6273, "lng": 120.3581, "country": "TW", "en": "Fengshan"},
    "鹿港": {"lat": 24.0560, "lng": 120.4350, "country": "TW", "en": "Lukang"},
}

# 🌐 國別首都錨點（Search Fusion 最後一階合法國別錨點，絕不跨國盲灌東京）
_COUNTRY_CAPITAL_ANCHORS: Dict[str, tuple[float, float]] = {
    "TW": (25.0330, 121.5654),
    "JP": (35.6895, 139.6917),
    "KR": (37.5665, 126.9780),
    "TH": (13.7563, 100.5018),
    "VN": (21.0285, 105.8542),
    "SG": (1.3521, 103.8198),
    "HK": (22.3193, 114.1694),
    "MO": (22.1987, 113.5439),
    "MY": (3.1390, 101.6869),
    "ID": (-6.2088, 106.8456),
    "PH": (14.5995, 120.9842),
    "CN": (39.9042, 116.4074),
    "US": (40.7128, -74.0060),
    "CA": (43.6532, -79.3832),
    "GB": (51.5074, -0.1278),
    "FR": (48.8566, 2.3522),
    "DE": (52.5200, 13.4050),
    "IT": (41.9028, 12.4964),
    "ES": (40.4168, -3.7038),
    "PT": (38.7223, -9.1393),
    "NL": (52.3676, 4.9041),
    "BE": (50.8503, 4.3517),
    "CH": (47.3769, 8.5417),
    "AT": (48.2082, 16.3738),
    "CZ": (50.0755, 14.4378),
    "HU": (47.4979, 19.0402),
    "PL": (52.2297, 21.0122),
    "FI": (60.1699, 24.9384),
    "SE": (59.3293, 18.0686),
    "NO": (59.9139, 10.7522),
    "DK": (55.6761, 12.5683),
    "IS": (64.1466, -21.9426),
    "GR": (37.9838, 23.7275),
    "IE": (53.3498, -6.2603),
    "AU": (-33.8688, 151.2093),
    "NZ": (-36.8509, 174.7645),
    "TR": (41.0082, 28.9784),
    "AE": (25.2048, 55.2708),
    "PE": (-12.0464, -77.0428),
    "MX": (19.4326, -99.1332),
    "BR": (-23.5505, -46.6333),
}

# 🌐 ISO 國碼 -> 中文國名 / 英文權威國名 / 主要母語代碼（涵蓋 GLOBAL_COUNTRY_TO_ISO 全部 122+ 國）
_ISO_TO_ZH_NAME: Dict[str, str] = {}
_ISO_TO_EN_NAME: Dict[str, str] = {}
for _cname, _iso in GLOBAL_COUNTRY_TO_ISO.items():
    _cc_u = _iso.upper()
    if _HAS_CJK_RE.search(_cname):
        if _cc_u not in _ISO_TO_ZH_NAME:
            _ISO_TO_ZH_NAME[_cc_u] = _cname
    elif _cname.isascii() and len(_cname) >= 3:
        # 優先保留無逗號、最常見的標準英文國名（例如 Taiwan, South Korea, United States）
        if _cc_u not in _ISO_TO_EN_NAME or ("," in _ISO_TO_EN_NAME[_cc_u] and "," not in _cname):
            _ISO_TO_EN_NAME[_cc_u] = _cname


def get_country_display_name(country_code: Optional[str]) -> str:
    """回傳目標國家之中文名稱（涵蓋 122+ 國，解除舊版 20 國限制）"""
    if not country_code:
        return ""
    cc = country_code.strip().upper()
    if cc in COUNTRY_BOUNDS and COUNTRY_BOUNDS[cc].get("name"):
        return COUNTRY_BOUNDS[cc]["name"]
    return _ISO_TO_ZH_NAME.get(cc) or _ISO_TO_EN_NAME.get(cc) or cc


def get_country_english_name(country_code: Optional[str]) -> Optional[str]:
    """回傳目標國家之標準英文名稱（供 Photon place:country 精準定位）"""
    if not country_code:
        return None
    cc = country_code.strip().upper()
    explicit_en = {
        "GB": "United Kingdom",
        "US": "United States",
        "KR": "South Korea",
        "TW": "Taiwan",
        "CN": "China",
        "AE": "United Arab Emirates",
        "CZ": "Czech Republic",
    }
    return explicit_en.get(cc) or _ISO_TO_EN_NAME.get(cc)


def get_country_primary_lang(country_code: Optional[str]) -> str:
    """回傳目標國家在 Wikipedia / OSM 中最常用之當地母語代碼"""
    if not country_code:
        return "en"
    cc = country_code.strip().upper()
    if cc in COUNTRY_BOUNDS and COUNTRY_BOUNDS[cc].get("lang"):
        return COUNTRY_BOUNDS[cc]["lang"].split("-")[0]
    extra_langs = {
        "LU": "fr", "SK": "sk", "RO": "ro", "BG": "bg", "RS": "sr", "SI": "sl",
        "UA": "uk", "RU": "ru", "EE": "et", "LV": "lv", "LT": "lt", "IL": "he",
        "EG": "ar", "MA": "fr", "AR": "es", "CL": "es", "CO": "es", "KH": "km",
        "LA": "lo", "MM": "my", "IN": "en", "ZA": "en", "AU": "en", "CA": "en",
    }
    return extra_langs.get(cc, "en")


def infer_country_from_coords(lat: Optional[float], lng: Optional[float]) -> Optional[str]:
    """座標優先反推所在國別：先比對最近城市錨點 (<=150km)，再取包含該座標之最小面積國家矩形。"""
    if lat is None or lng is None:
        return None
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat_f) and math.isfinite(lng_f)):
        return None
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lng_f <= 180.0):
        return None
    if abs(lat_f) < 1e-5 and abs(lng_f) < 1e-5:
        return None

    # Tier 1: 最近城市錨點 (解決歐洲/亞洲鄰國矩形重疊問題，例如慕尼黑/蘇黎世/薩爾茨堡/新加坡/香港)
    nearest_cc: Optional[str] = None
    nearest_dist = 150.0
    anchors = globals().get("GLOBAL_CITY_ANCHORS") or {}
    for info in anchors.values():
        c_lat = info.get("lat")
        c_lng = info.get("lng")
        c_cc = info.get("country")
        if c_lat is None or c_lng is None or not c_cc:
            continue
        d = haversine_km(lat_f, lng_f, c_lat, c_lng)
        if d <= nearest_dist:
            nearest_dist = d
            nearest_cc = str(c_cc).upper()
    if nearest_cc:
        return nearest_cc

    # Tier 2: 包含該座標之最小面積邊界框 (避免大型鄰國吞噬小型國家)
    best_cc: Optional[str] = None
    best_area = float("inf")
    for cc, b in COUNTRY_BOUNDS.items():
        if b["lat_min"] <= lat_f <= b["lat_max"] and b["lng_min"] <= lng_f <= b["lng_max"]:
            area = (b["lat_max"] - b["lat_min"]) * (b["lng_max"] - b["lng_min"])
            if area < best_area:
                best_area = area
                best_cc = cc
    return best_cc


# 🌐 零成本通用旅遊設施多語微字典（純通用設施詞，不含單一城市專屬地標，避免跨城漂移）
GENERIC_FACILITY_TRANSLATIONS: Dict[str, Dict[str, List[str]]] = {
    "市政廳": {"en": ["City Hall", "Town Hall"], "de": ["Rathaus"], "fi": ["Kaupungintalo"], "fr": ["Hôtel de Ville"], "it": ["Municipio", "Palazzo Comunale"], "es": ["Ayuntamiento"], "nl": ["Stadhuis"], "sv": ["Stadshus"], "no": ["Rådhus"], "da": ["Rådhus"], "cs": ["Radnice"], "pl": ["Ratusz"], "pt": ["Câmara Municipal"], "ja": ["市役所"], "ko": ["시청"]},
    "市政府": {"en": ["City Hall"], "de": ["Rathaus"], "fi": ["Kaupungintalo"], "fr": ["Hôtel de Ville"], "nl": ["Stadhuis"], "sv": ["Stadshus"], "ja": ["市役所"], "ko": ["시청"]},
    "中央車站": {"en": ["Central Station"], "de": ["Hauptbahnhof"], "fi": ["Päärautatieasema"], "fr": ["Gare Centrale"], "it": ["Stazione Centrale"], "es": ["Estación Central"], "nl": ["Centraal Station"], "sv": ["Centralstation"], "no": ["Sentralstasjon"], "da": ["Hovedbanegård"], "cs": ["Hlavní nádraží"], "pl": ["Dworzec Centralny"], "hu": ["Pályaudvar"], "pt": ["Estação Central"], "ja": ["中央駅"], "ko": ["중앙역"]},
    "中央火車站": {"en": ["Central Station"], "de": ["Hauptbahnhof"], "fi": ["Päärautatieasema"], "fr": ["Gare Centrale"], "it": ["Stazione Centrale"], "nl": ["Centraal Station"], "sv": ["Centralstation"], "cs": ["Hlavní nádraží"], "ja": ["中央駅"]},
    "火車站": {"en": ["Train Station", "Railway Station"], "de": ["Bahnhof"], "fi": ["Rautatieasema"], "fr": ["Gare"], "it": ["Stazione"], "es": ["Estación de tren"], "nl": ["Station"], "sv": ["Järnvägsstation"], "cs": ["Nádraží"], "ja": ["駅"], "ko": ["역"]},
    "車站": {"en": ["Station"], "de": ["Bahnhof"], "fi": ["Asema"], "fr": ["Gare"], "it": ["Stazione"], "es": ["Estación"], "nl": ["Station"], "ja": ["駅"], "ko": ["역"]},
    "國際機場": {"en": ["International Airport"], "de": ["Flughafen"], "fi": ["Lentoasema"], "fr": ["Aéroport"], "it": ["Aeroporto"], "es": ["Aeropuerto"], "nl": ["Luchthaven"], "ja": ["国際空港"], "ko": ["국제공항"]},
    "機場": {"en": ["Airport"], "de": ["Flughafen"], "fi": ["Lentoasema"], "fr": ["Aéroport"], "it": ["Aeroporto"], "es": ["Aeropuerto"], "nl": ["Luchthaven"], "sv": ["Flygplats"], "ja": ["空港"], "ko": ["공항"]},
    "大教堂": {"en": ["Cathedral"], "de": ["Dom", "Kathedrale"], "fi": ["Tuomiokirkko"], "fr": ["Cathédrale"], "it": ["Duomo", "Cattedrale"], "es": ["Catedral"], "nl": ["Kathedraal"], "sv": ["Domkyrka"], "cs": ["Katedrála"], "pt": ["Sé", "Catedral"]},
    "教堂": {"en": ["Church"], "de": ["Kirche"], "fi": ["Kirkko"], "fr": ["Église"], "it": ["Chiesa"], "es": ["Iglesia"], "nl": ["Kerk"]},
    "國家博物館": {"en": ["National Museum"], "de": ["Nationalmuseum"], "fi": ["Kansallismuseo"], "fr": ["Musée National"], "it": ["Museo Nazionale"], "es": ["Museo Nacional"], "nl": ["Rijksmuseum"], "sv": ["Nationalmuseum"], "cs": ["Národní muzeum"], "ja": ["国立博物館"], "ko": ["국립박물관"]},
    "博物館": {"en": ["Museum"], "de": ["Museum"], "fi": ["Museo"], "fr": ["Musée"], "it": ["Museo"], "es": ["Museo"], "nl": ["Museum"], "ja": ["博物館"], "ko": ["박물관"]},
    "美術館": {"en": ["Art Museum", "Art Gallery"], "de": ["Kunstmuseum"], "fi": ["Taidemuseo"], "fr": ["Musée d'Art"], "it": ["Galleria d'Arte"], "es": ["Museo de Arte"], "ja": ["美術館"], "ko": ["미술관"]},
    "皇宮": {"en": ["Royal Palace", "Imperial Palace"], "de": ["Schloss", "Residenz"], "fi": ["Presidentinlinna"], "fr": ["Palais"], "it": ["Palazzo Reale"], "es": ["Palacio Real"], "sv": ["Kungliga slottet"], "ja": ["皇居"]},
    "王宮": {"en": ["Royal Palace"], "de": ["Schloss", "Residenz"], "fr": ["Palais Royal"], "it": ["Palazzo Reale"], "es": ["Palacio Real"], "sv": ["Kungliga slottet"], "no": ["Det kongelige slott"]},
    "城堡": {"en": ["Castle"], "de": ["Schloss", "Burg"], "fi": ["Linna"], "fr": ["Château"], "it": ["Castello"], "es": ["Castillo"], "nl": ["Kasteel"], "cs": ["Hrad"], "ja": ["城"]},
    "老城區": {"en": ["Old Town"], "de": ["Altstadt"], "fi": ["Vanha kaupunki"], "fr": ["Vieille Ville"], "it": ["Centro Storico"], "es": ["Casco Antiguo"], "sv": ["Gamla Stan"], "cs": ["Staré Město"]},
    "舊城區": {"en": ["Old Town"], "de": ["Altstadt"], "fr": ["Vieille Ville"], "it": ["Centro Storico"], "cs": ["Staré Město"]},
    "廣場": {"en": ["Square", "Plaza"], "de": ["Platz"], "fi": ["Tori"], "fr": ["Place"], "it": ["Piazza"], "es": ["Plaza"], "nl": ["Plein"], "cs": ["Náměstí"]},
    "市場": {"en": ["Market", "Market Hall"], "de": ["Markt", "Markthalle"], "fi": ["Kauppatori", "Kauppahalli"], "fr": ["Marché"], "it": ["Mercato"], "es": ["Mercado"], "nl": ["Markt"], "ja": ["市場"], "ko": ["시장"]},
    "歌劇院": {"en": ["Opera House"], "de": ["Staatsoper", "Oper"], "fi": ["Oopperatalo"], "fr": ["Opéra"], "it": ["Teatro dell'Opera"], "es": ["Ópera"]},
    "動物園": {"en": ["Zoo"], "de": ["Zoo", "Tierpark"], "fi": ["Eläintarha"], "fr": ["Zoo"], "ja": ["動物園"], "ko": ["동물원"]},
    "植物園": {"en": ["Botanical Garden"], "de": ["Botanischer Garten"], "fi": ["Kasvitieteellinen puutarha"], "fr": ["Jardin Botanique"], "ja": ["植物園"]},
    "水族館": {"en": ["Aquarium"], "de": ["Aquarium"], "fi": ["Akvaario"], "ja": ["水族館"], "ko": ["아쿠아리움"]},
    "圖書館": {"en": ["Library"], "de": ["Bibliothek"], "fi": ["Kirjasto"], "fr": ["Bibliothèque"], "ja": ["図書館"], "ko": ["도서관"]},
    "大學": {"en": ["University"], "de": ["Universität"], "fi": ["Yliopisto"], "fr": ["Université"], "it": ["Università"], "es": ["Universidad"], "ja": ["大学"], "ko": ["대학교"]},
    "公園": {"en": ["Park"], "de": ["Park"], "fi": ["Puisto"], "fr": ["Parc"], "it": ["Parco"], "es": ["Parque"], "ja": ["公園"], "ko": ["공원"]},
    "港口": {"en": ["Harbour", "Port"], "de": ["Hafen"], "fi": ["Satama"], "fr": ["Port"], "it": ["Porto"], "es": ["Puerto"], "ja": ["港"]},
    "碼頭": {"en": ["Pier", "Harbour"], "de": ["Hafen"], "fi": ["Satama"], "fr": ["Quai"], "it": ["Porto"], "ja": ["埠頭"]},
    "醫院": {"en": ["Hospital"], "de": ["Krankenhaus"], "fi": ["Sairaala"], "fr": ["Hôpital"], "it": ["Ospedale"], "es": ["Hospital"], "ja": ["病院"], "ko": ["병원"]},
    "藥局": {"en": ["Pharmacy"], "de": ["Apotheke"], "fi": ["Apteekki"], "fr": ["Pharmacie"], "it": ["Farmacia"], "es": ["Farmacia"], "ja": ["薬局"], "ko": ["약국"]},
    "超市": {"en": ["Supermarket"], "de": ["Supermarkt"], "fi": ["Supermarket"], "fr": ["Supermarché"], "it": ["Supermercato"], "es": ["Supermercado"], "ja": ["スーパー"], "ko": ["마트"]},
    "咖啡廳": {"en": ["Cafe", "Coffee"], "de": ["Café"], "fi": ["Kahvila"], "fr": ["Café"], "it": ["Caffè"], "es": ["Cafetería"], "ja": ["カフェ"], "ko": ["카페"]},
    "飯店": {"en": ["Hotel"], "de": ["Hotel"], "fi": ["Hotelli"], "fr": ["Hôtel"], "it": ["Hotel"], "es": ["Hotel"], "ja": ["ホテル"], "ko": ["호텔"]},
    "酒店": {"en": ["Hotel"], "de": ["Hotel"], "fi": ["Hotelli"], "fr": ["Hôtel"], "it": ["Hotel"], "es": ["Hotel"], "ja": ["ホテル"], "ko": ["호텔"]},
    "環球影城": {"en": ["Universal Studios"], "ja": ["Universal Studios Japan", "ユニバーサル・スタジオ・ジャパン"]},
    "迪士尼": {"en": ["Disneyland", "Disney"], "ja": ["Tokyo Disneyland", "東京ディズニーランド"], "fr": ["Disneyland Paris", "Disneyland"]},
    "迪士尼樂園": {"en": ["Disneyland"], "ja": ["Tokyo Disneyland", "東京ディズニーランド"], "fr": ["Disneyland Paris", "Disneyland"]},
}


def _get_city_anchor_english_name(city_info: Optional[Dict[str, Any]]) -> Optional[str]:
    """從 GLOBAL_CITY_ANCHORS 0ms 反查同座標城市之標準英文名稱（例如『巴塞隆納』-> 'Barcelona'、『慕尼黑』-> 'Munich'）。"""
    if not isinstance(city_info, dict):
        return None
    if city_info.get("en"):
        return str(city_info["en"]).strip()
    c_lat = city_info.get("lat")
    c_lng = city_info.get("lng")
    if c_lat is None or c_lng is None:
        return None
    anchors = globals().get("GLOBAL_CITY_ANCHORS") or {}
    for k, v in anchors.items():
        if k.isascii() and v.get("lat") == c_lat and v.get("lng") == c_lng:
            return k.title()
    return None


def _find_nearest_city_anchor_en(
    lat: Optional[float],
    lng: Optional[float],
    country_code: Optional[str] = None,
    max_km: float = 25.0,
) -> Optional[str]:
    """若當前地圖座標位於已知城市錨點 25km 內，回傳該城市英文名稱（用於組合 'Munich Rathaus' 等精準查詢）。"""
    if lat is None or lng is None:
        return None
    try:
        lat_f, lng_f = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat_f) and math.isfinite(lng_f)):
        return None
    target_cc = (country_code or "").strip().upper()
    anchors = globals().get("GLOBAL_CITY_ANCHORS") or {}
    best_en: Optional[str] = None
    best_dist = max_km
    for k, info in anchors.items():
        if not k.isascii() or info.get("is_admin_region"):
            continue
        c_lat, c_lng = info.get("lat"), info.get("lng")
        c_cc = str(info.get("country") or "").upper()
        if c_lat is None or c_lng is None:
            continue
        if target_cc and c_cc and c_cc != target_cc:
            continue
        d = haversine_km(lat_f, lng_f, c_lat, c_lng)
        if d <= best_dist:
            best_dist = d
            best_en = k.title()
    return best_en


def _detect_country_from_city_prefix(query: str) -> Optional[str]:
    """從查詢詞中偵測已知全球城市名稱（補齊 LOCATION_KEYWORDS 以外的歐美/日韓/台灣城市，如『慕尼黑市政廳』-> DE）。"""
    clean_q = (query or "").strip()
    if not clean_q:
        return None
    q_low = clean_q.lower()
    norm_q = normalize_cjk_chars(clean_q)
    anchors = globals().get("GLOBAL_CITY_ANCHORS") or {}
    for k in sorted(anchors.keys(), key=len, reverse=True):
        cc = str(anchors[k].get("country") or "").upper()
        if not cc:
            continue
        if k.isascii():
            if len(k) >= 4 and re.search(rf"\b{re.escape(k.lower())}\b", q_low):
                return cc
        else:
            if len(k) >= 2 and (k in clean_q or normalize_cjk_chars(k) in norm_q):
                return cc
    return None


_CULINARY_DISH_SUFFIXES = (
    "燒", "麵", "面", "飯", "饭", "牛肉麵", "担仔麵", "擔仔麵", "小籠包", "湯包",
    "鍋", "火鍋", "烤鴨", "料理", "便當", "滷肉飯", "肉燥飯", "蚵仔煎", "炒飯", "炒麵",
    "拉麵", "烏龍麵", "蕎麥麵", "章魚燒", "文字燒", "廣島燒", "大阪燒", "壽司", "燒肉", "咖哩",
)


def _is_city_dish_query(prefix: str, suffix: str) -> bool:
    """區分『大阪燒』『廣島燒』『台南擔仔麵』等料理品名（不應把台北搜尋切換到大阪座標）
    與『新宿一蘭拉麵』『慕尼黑市政廳』『台南龍山寺』等跨區/跨城實地查詢。
    """
    if not suffix:
        return False
    # 只要次區錨點（如新宿/澀谷/明洞）或具體品牌/地標詞存在，即屬實地查詢而非通用料理名
    if prefix in _SUBDISTRICT_ANCHORS or prefix.lower() in _SUBDISTRICT_ANCHORS:
        return False
    # 若後綴本身就是純料理尾詞（例如「大阪」+「燒」、「台南」+「擔仔麵」）
    s_clean = suffix.strip()
    if s_clean in _CULINARY_DISH_SUFFIXES:
        return True
    if len(s_clean) <= 3 and any(s_clean.endswith(ds) for ds in ("燒", "麵", "面", "飯", "饭", "鍋", "粥", "羹")):
        return True
    return False


def _match_landmark_facility_prefix(
    query: str,
    country_code: Optional[str] = None,
) -> Optional[tuple[str, Dict[str, Any], str]]:
    """從『已知地標 + 通用設施詞』（如『東京迪士尼飯店』『環球影城飯店』『淺草寺飯店』）
    萃取地標前綴與設施尾詞，供 0ms 微字典轉譯與空間錨點精準對齊（排除連鎖品牌與撞名地標）。
    """
    clean_q = (query or "").strip()
    if not clean_q:
        return None
    target_cc = (country_code or "").strip().upper()
    # 僅在必要時讀取已載入之內建與外部地標，確保單點地標如「東京迪士尼」「環球影城」皆可命中
    for fac_key in sorted(GENERIC_FACILITY_TRANSLATIONS.keys(), key=len, reverse=True):
        if clean_q.endswith(fac_key) and len(clean_q) > len(fac_key):
            prefix = clean_q[:-len(fac_key)].strip()
            if len(prefix) < 2:
                continue
            norm_prefix = normalize_cjk_chars(prefix)
            if not norm_prefix or norm_prefix in _HOMONYM_GUARD_NORM:
                continue
            for lm_key, lm_val in LANDMARKS_DB.items():
                if not isinstance(lm_val, dict):
                    continue
                lm_cc = str(lm_val.get("country") or "").strip().upper()
                if target_cc and lm_cc and lm_cc != target_cc:
                    continue
                matched = normalize_cjk_chars(lm_key) == norm_prefix or normalize_cjk_chars(str(lm_val.get("display") or "")) == norm_prefix
                if not matched:
                    for alias in (lm_val.get("aliases") or []):
                        if normalize_cjk_chars(str(alias)) == norm_prefix:
                            matched = True
                            break
                if matched:
                    if _is_chain_brand_entry(prefix, lm_val, lm_val.get("display"), landmark_key=lm_key):
                        continue
                    return prefix, lm_val, fac_key
    return None


def _detect_city_prefix_anchor(query: str) -> Optional[tuple[str, Dict[str, Any], str]]:
    """從『城市/次區/地標前綴 + 設施/地標/分店』查詢中提取目標空間錨點與剩餘後綴。

    例：
    - '慕尼黑市政廳'   -> ('慕尼黑', {lat:48.1351, lng:11.5820, country:'DE'}, '市政廳')
    - '台南龍山寺'     -> ('台南', {lat:22.9997, lng:120.2270, country:'TW'}, '龍山寺')
    - '新宿一蘭拉麵'   -> ('新宿', {lat:35.6938, lng:139.7034, country:'JP'}, '一蘭拉麵')
    - '東京迪士尼飯店' -> ('東京迪士尼', {lat:35.6329, lng:139.8804, country:'JP', ...}, '飯店')
    - '大阪燒'         -> None（料理名詞，不切離在地座標）
    """
    clean_q = (query or "").strip()
    if not clean_q:
        return None
    norm_q = normalize_cjk_chars(clean_q)
    q_low = clean_q.lower()

    # 優先識別更精細之『著名地標 + 設施詞』（如『東京迪士尼飯店』-> 浦安迪士尼座標而非新宿中心）
    lm_fac_hit = _match_landmark_facility_prefix(clean_q)
    if lm_fac_hit:
        lm_prefix, lm_val, fac_suffix = lm_fac_hit
        if lm_val.get("lat") is not None and lm_val.get("lng") is not None:
            return lm_prefix, {
                "lat": float(lm_val["lat"]),
                "lng": float(lm_val["lng"]),
                "country": lm_val.get("country"),
                "is_subdistrict": True,
            }, fac_suffix

    merged_anchors: Dict[str, Dict[str, Any]] = {}
    merged_anchors.update(globals().get("GLOBAL_CITY_ANCHORS") or {})
    merged_anchors.update(_SUBDISTRICT_ANCHORS)

    for k in sorted(merged_anchors.keys(), key=len, reverse=True):
        info = merged_anchors[k]
        if info.get("lat") is None or info.get("lng") is None:
            continue
        if k.isascii():
            if len(k) < 4:
                continue
            m = re.match(rf"^{re.escape(k.lower())}\s+(.+)$", q_low)
            if m:
                suffix = clean_q[len(k):].strip()
                if suffix and not _is_city_dish_query(k, suffix):
                    return k, info, suffix
        else:
            if len(k) < 2:
                continue
            norm_k = normalize_cjk_chars(k)
            if (clean_q.startswith(k) and len(clean_q) > len(k)) or (norm_q.startswith(norm_k) and len(norm_q) > len(norm_k)):
                suffix = clean_q[len(k):].strip()
                if suffix and not _is_city_dish_query(k, suffix):
                    return k, info, suffix
    return None


def _get_facility_standalone_terms(suffix: str, country_code: Optional[str]) -> List[str]:
    """為『城市前綴 + 設施詞』取出僅供 rerank_top_k 評分使用的當地母語/英文設施單詞
    （不改動 _translate_via_micro_dict 回傳值，守住既有哨兵契約）。
    """
    clean_s = (suffix or "").strip()
    if not clean_s or not country_code:
        return []
    cc = country_code.strip().upper()
    if cc in ("TW", "CN", "HK", "MO"):
        return []
    entry = GENERIC_FACILITY_TRANSLATIONS.get(clean_s)
    if not entry:
        return []
    lang = get_country_primary_lang(cc)
    terms: List[str] = []
    for t in entry.get(lang, []):
        if t and t not in terms:
            terms.append(t)
    for t in entry.get("en", []):
        if t and t not in terms:
            terms.append(t)
    return terms


_PAREN_REMARK_RE = re.compile(r"[\(（\[【][^()（）\[\]【】]{1,80}[\)）\]】]")
_LEADING_ACTIVITY_PREFIX_RE = re.compile(
    r"^(?:"
    r"(?:day\s*\d+|d\d+|第\s*\d+\s*天)\s*[:：\-—–]?\s*"
    r"|\d{1,2}:\d{2}(?:\s*[-~～]\s*\d{1,2}:\d{2})?\s+"
    r"|(?:上午|下午|晚上|早上|中午|傍晚|早餐|午餐|晚餐|宵夜|前往|參觀|拜訪|逛逛|逛|吃)\s*[:：]\s*"
    r"|(?:前往|參觀|拜訪|抵達|入住)\s+"
    r")",
    re.IGNORECASE,
)


def _extract_clean_place_query(raw: str) -> str:
    """從帶括號備註或行程前綴的長活動標題提取純淨地名（ReDoS-Free，供後端單次降級使用）。
    例：'淺草寺 (雷門拍照)' -> '淺草寺'、'10:00 築地市場（海鮮早餐）' -> '築地市場'。
    """
    text = (raw or "").strip()
    if not text:
        return ""
    cleaned = _PAREN_REMARK_RE.sub(" ", text)
    cleaned = _LEADING_ACTIVITY_PREFIX_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t\r\n-—–|:：,，")
    if len(cleaned) < 2:
        return text
    return cleaned


def resolve_fusion_anchor_coords(
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    query: Optional[str] = None,
    region: Optional[str] = None,
    trip_title: Optional[str] = None,
    country: Optional[str] = None,
) -> tuple[Optional[float], Optional[float]]:
    """依序解析 Search Fusion 空間錨點：
    1. 顯式 body.lat/lng
    2. 查詢詞／區域／行程標題內之城市或次區錨點（含 shinjuku/新宿）
    3. 顯式或關鍵字推斷之國別首都錨點
    全空則回傳 (None, None) 跳過 Fusion，絕不盲灌東京座標。
    """
    if lat is not None and lng is not None:
        try:
            lat_f, lng_f = float(lat), float(lng)
            if math.isfinite(lat_f) and math.isfinite(lng_f) and -90.0 <= lat_f <= 90.0 and -180.0 <= lng_f <= 180.0:
                if abs(lat_f) > 1e-5 or abs(lng_f) > 1e-5:
                    return lat_f, lng_f
        except (TypeError, ValueError):
            pass

    merged_anchors: Dict[str, Dict[str, Any]] = {}
    merged_anchors.update(globals().get("GLOBAL_CITY_ANCHORS") or {})
    merged_anchors.update(_SUBDISTRICT_ANCHORS)
    sorted_keys = sorted(merged_anchors.keys(), key=len, reverse=True)

    for source_text in (query, region, trip_title):
        s = (source_text or "").strip()
        if not s:
            continue
        s_low = s.lower()
        s_norm = normalize_cjk_chars(s)
        for k in sorted_keys:
            info = merged_anchors[k]
            if info.get("lat") is None or info.get("lng") is None:
                continue
            if k.isascii():
                if len(k) >= 3 and re.search(rf"\b{re.escape(k.lower())}\b", s_low):
                    return float(info["lat"]), float(info["lng"])
            else:
                norm_k = normalize_cjk_chars(k)
                if len(k) >= 2 and (k in s or norm_k in s_norm):
                    # 排除料理名詞（如『大阪燒』『廣島燒』『台南擔仔麵』）誤將 Fusion 座標切往外地城市
                    if source_text is query:
                        idx_pos = s.find(k) if k in s else s_norm.find(norm_k)
                        if idx_pos >= 0:
                            after_txt = s[idx_pos + len(k):].strip()
                            if after_txt and _is_city_dish_query(k, after_txt):
                                continue
                    return float(info["lat"]), float(info["lng"])

    resolved_cc: Optional[str] = None
    if country:
        c_up = str(country).strip().upper()
        if c_up in _COUNTRY_CAPITAL_ANCHORS:
            resolved_cc = c_up
        else:
            iso = country_to_iso(str(country))
            if iso:
                resolved_cc = iso.upper()
    if not resolved_cc:
        # 優先尊重 region / trip_title 避免料理詞（如『大阪燒』）在無座標時把台北行程拉往東京
        for source_text in (region, trip_title, query):
            if not source_text:
                continue
            if source_text is query:
                s_q = query.strip()
                if any(
                    (s_q.startswith(ck) or normalize_cjk_chars(s_q).startswith(normalize_cjk_chars(ck)))
                    and len(s_q) > len(ck)
                    and _is_city_dish_query(ck, s_q[len(ck):].strip())
                    for ck in (globals().get("GLOBAL_CITY_ANCHORS") or {})
                    if not ck.isascii() and len(ck) >= 2
                ):
                    continue
            cc_hit = detect_country_from_keywords(source_text) or _detect_country_from_city_prefix(source_text)
            if cc_hit:
                resolved_cc = cc_hit.upper()
                break

    if resolved_cc and resolved_cc in _COUNTRY_CAPITAL_ANCHORS:
        return _COUNTRY_CAPITAL_ANCHORS[resolved_cc]

    return None, None


def _strip_wiki_parenthetical(title: str) -> str:
    """剝除 Wikipedia 消歧義尾端括號，例如 'Central Station (Helsinki)' -> 'Central Station'。"""
    if not title:
        return ""
    cleaned = re.sub(r"\s*[\(（][^()（）]{1,40}[\)）]\s*$", "", title.strip()).strip()
    return cleaned or title.strip()


_TW_CITY_GOV_MAP: Dict[str, str] = {
    "taipei": "臺北市政府",
    "new taipei": "新北市政府",
    "taoyuan": "桃園市政府",
    "taichung": "臺中市政府",
    "tainan": "臺南市政府",
    "kaohsiung": "高雄市政府",
}


def _translate_via_micro_dict(
    query: str,
    country_code: Optional[str],
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> List[str]:
    """零成本 0ms 通用旅遊設施微字典轉譯（支援單詞、座標鄰近城市結合、與『已知城市+設施』組合）。"""
    clean_q = (query or "").strip()
    if not clean_q or not country_code:
        return []
    cc = country_code.strip().upper()
    if cc in ("TW", "CN", "HK", "MO"):
        if cc == "TW" and clean_q == "市政廳":
            nearest_tw = (_find_nearest_city_anchor_en(lat, lng, country_code="TW", max_km=35.0) or "").lower()
            gov_name = _TW_CITY_GOV_MAP.get(nearest_tw)
            return list(dict.fromkeys([t for t in (gov_name, "市政府") if t]))
        if cc == "HK" and clean_q in ("迪士尼", "迪士尼樂園"):
            return ["Hong Kong Disneyland", "香港迪士尼樂園"]
        if cc == "CN" and clean_q in ("迪士尼", "迪士尼樂園"):
            return ["Shanghai Disneyland", "上海迪士尼乐园"]
        if cc == "CN" and clean_q == "環球影城":
            return ["Universal Beijing Resort", "北京环球影城"]
        return []
    lang = get_country_primary_lang(cc)

    def _collect_terms(entry: Dict[str, List[str]]) -> List[str]:
        terms: List[str] = []
        for t in entry.get(lang, []):
            if t not in terms:
                terms.append(t)
        for t in entry.get("en", []):
            if t not in terms:
                terms.append(t)
        return terms

    # 1. 完全命中通用設施詞（若座標位於已知城市 25km 內，優先前置 '<City> <LocalTerm>' 精準命中主地標如 Neues Rathaus）
    if clean_q in GENERIC_FACILITY_TRANSLATIONS:
        base_terms = _collect_terms(GENERIC_FACILITY_TRANSLATIONS[clean_q])
        nearest_city_en = _find_nearest_city_anchor_en(lat, lng, country_code=cc, max_km=25.0)
        if clean_q == "環球影城" and nearest_city_en and nearest_city_en.lower() == "los angeles":
            return ["Universal Studios Hollywood", "Universal Studios"]
        if nearest_city_en and base_terms:
            b0_low = base_terms[0].lower()
            if nearest_city_en.lower() not in b0_low and not any(
                qual in b0_low for qual in ("japan", "tokyo", "paris", "singapore", "hong kong")
            ):
                city_qualified = f"{nearest_city_en} {base_terms[0]}"
                return list(dict.fromkeys([city_qualified, *base_terms]))
        return base_terms

    # 2. 城市前綴 + 設施後綴組合（例如『慕尼黑市政廳』-> 'Munich Rathaus', 'Munich City Hall'）
    anchors = globals().get("GLOBAL_CITY_ANCHORS") or {}
    for fac_key in sorted(GENERIC_FACILITY_TRANSLATIONS.keys(), key=len, reverse=True):
        if clean_q.endswith(fac_key) and len(clean_q) > len(fac_key):
            prefix = clean_q[:-len(fac_key)].strip()
            city_info = anchors.get(prefix) or anchors.get(normalize_cjk_chars(prefix))
            if city_info:
                city_en = _get_city_anchor_english_name(city_info)
                if city_en:
                    return list(dict.fromkeys([
                        t if city_en.lower() in t.lower() else f"{city_en} {t}"
                        for t in _collect_terms(GENERIC_FACILITY_TRANSLATIONS[fac_key])[:2]
                    ]))
            # 2b. 次級商圈前綴 + 設施後綴（例如『新宿飯店』-> '新宿 ホテル', 'Shinjuku Hotel'）
            sub_info = _SUBDISTRICT_ANCHORS.get(prefix) or _SUBDISTRICT_ANCHORS.get(normalize_cjk_chars(prefix))
            if sub_info:
                sub_cc = str(sub_info.get("country") or "").upper()
                if not sub_cc or sub_cc == cc:
                    fac_entry = GENERIC_FACILITY_TRANSLATIONS[fac_key]
                    native_terms = fac_entry.get(lang, [])
                    en_terms = fac_entry.get("en", [])
                    out_sub: List[str] = []
                    if lang == "ja" and native_terms and not prefix.isascii():
                        out_sub.append(f"{prefix} {native_terms[0]}")
                    sub_en = sub_info.get("en")
                    if sub_en and en_terms:
                        out_sub.append(f"{sub_en} {en_terms[0]}")
                    elif sub_en and native_terms:
                        out_sub.append(f"{sub_en} {native_terms[0]}")
                    if out_sub:
                        return list(dict.fromkeys(out_sub))[:2]

    # 2c. 著名地標前綴 + 設施後綴（例如『東京迪士尼飯店』-> 'Tokyo Disneyland Hotel', '東京ディズニーランドホテル'）
    lm_fac_hit = _match_landmark_facility_prefix(clean_q, country_code=cc)
    if lm_fac_hit:
        _, lm_val, fac_key = lm_fac_hit
        fac_entry = GENERIC_FACILITY_TRANSLATIONS[fac_key]
        native_terms = fac_entry.get(lang, [])
        en_terms = fac_entry.get("en", [])
        out_lm: List[str] = []
        lm_search = str(lm_val.get("search") or "").strip()
        if lm_search and en_terms:
            out_lm.append(f"{lm_search} {en_terms[0]}")
        if lang == "ja" and native_terms:
            ja_alias = next(
                (str(a).strip() for a in (lm_val.get("aliases") or []) if re.search(r"[\u3040-\u30ff]", str(a))),
                None,
            )
            if ja_alias:
                # 日文片假名複合詞直接相接（如 '東京ディズニーランドホテル'）較空白拼接大幅提升 OSM 命中率
                out_lm.append(f"{ja_alias}{native_terms[0]}")
        if out_lm:
            return list(dict.fromkeys(out_lm))[:2]
    return []


async def _translate_via_wikipedia_langlinks(query: str, country_code: Optional[str]) -> List[str]:
    """無 API Key 時免費 Wikipedia zh->(當地母語/en) 跨語言標題橋接（1.2s 硬超時 + 括號消歧義剝除）。"""
    clean_q = (query or "").strip()
    if not clean_q or not country_code:
        return []
    cc = country_code.strip().upper()
    if cc in ("TW", "CN", "HK", "MO") or not _HAS_CJK_RE.search(clean_q):
        return []
    target_lang = get_country_primary_lang(cc)
    wanted_langs = [target_lang, "en"] if target_lang != "en" else ["en"]
    headers = {"User-Agent": os.getenv("APP_USER_AGENT", "TabijiTravelPWA/1.0 (https://www.tabijiapp.com; contact@tabijiapp.com)")}

    async def _fetch_langlinks() -> List[str]:
        async with httpx.AsyncClient(timeout=1.1, headers=headers) as client:
            res = await client.get(
                "https://zh.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "prop": "langlinks",
                    "titles": clean_q,
                    "redirects": 1,
                    "lllimit": 50,
                    "format": "json",
                },
            )
            wiki_status = getattr(res, "status_code", 200)
            if isinstance(wiki_status, int) and wiki_status != 200:
                return []
            payload = res.json()
            pages = (payload.get("query") or {}).get("pages") or {}
            extracted: Dict[str, str] = {}
            for page_id, page_data in pages.items():
                if str(page_id) == "-1":
                    continue
                for ll in (page_data.get("langlinks") or []):
                    lang_code = ll.get("lang")
                    title = ll.get("*")
                    if lang_code in wanted_langs and title:
                        extracted[lang_code] = _strip_wiki_parenthetical(str(title))

            # 若直接標題未命中，改走 OpenSearch 取第一筆相近條目再查 langlinks
            if not extracted:
                os_res = await client.get(
                    "https://zh.wikipedia.org/w/api.php",
                    params={
                        "action": "opensearch",
                        "search": clean_q,
                        "limit": 1,
                        "namespace": 0,
                        "format": "json",
                    },
                )
                os_status = getattr(os_res, "status_code", 200)
                if not isinstance(os_status, int) or os_status == 200:
                    os_data = os_res.json()
                    if isinstance(os_data, list) and len(os_data) >= 2 and isinstance(os_data[1], list) and os_data[1]:
                        matched_title = str(os_data[1][0]).strip()
                        if matched_title and matched_title != clean_q:
                            res2 = await client.get(
                                "https://zh.wikipedia.org/w/api.php",
                                params={
                                    "action": "query",
                                    "prop": "langlinks",
                                    "titles": matched_title,
                                    "redirects": 1,
                                    "lllimit": 50,
                                    "format": "json",
                                },
                            )
                            res2_status = getattr(res2, "status_code", 200)
                            if not isinstance(res2_status, int) or res2_status == 200:
                                pages2 = ((res2.json()).get("query") or {}).get("pages") or {}
                                for pid2, pdata2 in pages2.items():
                                    if str(pid2) == "-1":
                                        continue
                                    for ll in (pdata2.get("langlinks") or []):
                                        lang_code = ll.get("lang")
                                        title = ll.get("*")
                                        if lang_code in wanted_langs and title:
                                            extracted[lang_code] = _strip_wiki_parenthetical(str(title))

            ordered: List[str] = []
            for wl in wanted_langs:
                val = extracted.get(wl)
                if val and val not in ordered:
                    ordered.append(val)
            return ordered

    try:
        return await asyncio.wait_for(_fetch_langlinks(), timeout=1.2)
    except Exception as e:
        log_debug(f"🌐 [WikiLanglinks] skipped/timeout for '{clean_q}': {type(e).__name__}")
        return []

# 🆕 關鍵字 → 國家代碼 映射 (確定性規則，無需 AI)
LOCATION_KEYWORDS = {
    "JP": [
        # 城市與主要觀光大區
        "東京", "tokyo", "大阪", "osaka", "京都", "kyoto", "北海道", "hokkaido",
        "沖繩", "okinawa", "札幌", "sapporo", "名古屋", "nagoya", "福岡", "fukuoka",
        "奈良", "nara", "神戶", "kobe", "橫濱", "yokohama", "廣島", "hiroshima",
        "函館", "hakodate", "小樽", "otaru", "旭川", "asahikawa", "富良野", "furano",
        "二世谷", "新雪谷", "niseko", "金澤", "kanazawa", "仙台", "sendai", "青森", "aomori",
        "輕井澤", "karuizawa", "日光", "nikko", "河口湖", "kawaguchiko", "那霸", "naha",
        "石垣島", "ishigaki", "宮古島", "miyako",
        # 著名景點（排除跨國連鎖主題樂園如「迪士尼」「環球影城」，避免「巴黎迪士尼」「新加坡環球影城」誤判 JP）
        "淺草", "asakusa", "箱根", "hakone", "富士", "fuji",
        "新宿", "shinjuku", "澀谷", "shibuya", "涩谷", "銀座", "ginza",
        "成田", "narita", "羽田", "haneda", "秋葉原", "akihabara", "原宿", "harajuku",
        "上野", "ueno", "池袋", "ikebukuro", "品川", "shinagawa",
        "清水寺", "金閣寺", "伏見稻荷", "嵐山", "arashiyama",
        "心齋橋", "道頓堀", "通天閣",
        "日本", "japan", "関西", "関東", "九州", "四國", "東北",
    ],
    "KR": [
        "首爾", "seoul", "釜山", "busan", "濟州", "jeju", "仁川", "incheon",
        "明洞", "myeongdong", "弘大", "hongdae", "東大門", "dongdaemun",
        "景福宮", "南山塔", "n seoul tower", "梨泰院", "itaewon",
        "韓國", "korea", "樂天", "lotte",
    ],
    "TW": [
        "台北", "taipei", "台中", "taichung", "台南", "tainan", "高雄", "kaohsiung",
        "九份", "jiufen", "淡水", "tamsui", "墾丁", "kenting", "花蓮", "hualien",
        "101", "西門町", "ximending", "士林", "shilin", "故宮", "北投", "beitou",
        "台灣", "taiwan", "饒河", "逢甲", "日月潭", "sun moon lake", "阿里山",
    ],
    "TH": [
        "曼谷", "bangkok", "普吉", "phuket", "清邁", "chiang mai", "芭達雅", "pattaya",
        "華欣", "hua hin", "蘇梅", "samui", "大城", "ayutthaya",
        "考山路", "khao san", "恰圖恰", "chatuchak", "水門", "pratunam",
        "泰國", "thailand",
    ],
    "VN": [
        "河內", "hanoi", "胡志明", "ho chi minh", "峴港", "da nang", "會安", "hoi an",
        "下龍灣", "ha long", "芽莊", "nha trang", "大叻", "dalat",
        "越南", "vietnam",
    ],
    "SG": [
        "新加坡", "singapore", "聖淘沙", "sentosa", "烏節路", "orchard", "克拉碼頭", "clarke quay",
        "濱海灣", "marina bay", "樟宜", "changi",
    ],
    "HK": [
        "香港", "hong kong", "旺角", "mong kok", "尖沙咀", "tsim sha tsui",
        "銅鑼灣", "causeway bay", "中環", "central", "太平山", "victoria peak",
        "海洋公園", "ocean park", "大嶼山", "lantau",
    ],
    "FR": [
        "巴黎", "paris", "法國", "france", "尼斯", "nice", "里昂", "lyon",
        "馬賽", "marseille", "波爾多", "bordeaux", "羅浮宮", "louvre",
        "艾菲爾", "eiffel", "凡爾賽", "versailles", "聖母院", "notre dame",
        "奧賽", "orsay", "蒙馬特", "montmartre",
    ],
    "US": [
        "紐約", "new york", "nyc", "美國", "usa", "洛杉磯", "los angeles",
        "舊金山", "san francisco", "西雅圖", "seattle", "芝加哥", "chicago",
        "曼哈頓", "manhattan", "布魯克林", "brooklyn", "時代廣場", "times square",
        "中央公園", "central park", "大都會", "metropolitan", "自由女神", "statue of liberty",
    ],
}

def detect_country_from_keywords(query: Optional[str]) -> Optional[str]:
    """🔑 從搜尋關鍵字確定性判斷國家（無需 AI，零延遲）
    
    這是 Google Maps 風格的語意解析：
    - "東京迪士尼" → JP (命中 "東京")
    - "首爾塔" → KR (命中 "首爾")
    
    Returns: 國家代碼 或 None
    """
    if not query or not isinstance(query, str):
        return None
    query_lower = query.lower()
    
    for country_code, keywords in LOCATION_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in query_lower:
                log_debug(f"🔑 Keyword Match: '{kw}' → {country_code}")
                return country_code
    return None


# ═══════════════════════════════════════════════════════════════
# 幣別映射與確定性推斷引擎 (ISO 4217 Currency Engine)
# ═══════════════════════════════════════════════════════════════
COUNTRY_TO_CURRENCY = {
    "TW": "TWD",
    "JP": "JPY",
    "KR": "KRW",
    "US": "USD",
    "UK": "GBP",
    "GB": "GBP",
    "FR": "EUR",
    "DE": "EUR",
    "IT": "EUR",
    "ES": "EUR",
    "EU": "EUR",
    "TH": "THB",
    "SG": "SGD",
    "HK": "HKD",
    "MO": "MOP",
    "CN": "CNY",
    "AU": "AUD",
    "NZ": "NZD",
    "CA": "CAD",
    "VN": "VND",
    "MY": "MYR",
    "PH": "PHP",
    "ID": "IDR",
}

def detect_currency_from_country(country_code: Optional[str], fallback: str = "TWD") -> str:
    """根據國家代碼 (ISO 3166-1 alpha-2) 返回對應 ISO 4217 法幣代碼"""
    if not country_code:
        return fallback
    return COUNTRY_TO_CURRENCY.get(country_code.upper(), fallback)

def infer_currency_from_destination(dest: str, declared_currency: Optional[str] = None) -> str:
    """雙層防禦推斷法定幣別 (Destination ➔ Country ➔ Currency)"""
    # 1. 若外部/LLM 已提供有效三位大寫字母幣別代碼
    if declared_currency and isinstance(declared_currency, str):
        cleaned = declared_currency.strip().upper()
        if len(cleaned) == 3 and cleaned.isalpha():
            country = detect_country_from_keywords(dest)
            if country:
                expected = detect_currency_from_country(country)
                # 若外部/LLM 隨機輸出 JPY 但目的地明確為台灣(TW)或韓國(KR)，以確定性規則糾偏
                if cleaned == "JPY" and expected != "JPY":
                    return expected
                return cleaned
            return cleaned

    # 2. 確定性關鍵字對照
    if dest:
        country = detect_country_from_keywords(dest)
        if country:
            return detect_currency_from_country(country)

    return "TWD"


# 🆕 擴展版地標資料庫（支援別名、中文顯示、國家識別、座標直接回傳）
LANDMARKS_DB = {
    # ═══════════════════════════════════════════════════════════════
    # 日本 - 主題公園 (含座標，可秒回)
    # ═══════════════════════════════════════════════════════════════
    "東京迪士尼": {"aliases": ["东京迪士尼", "tokyo disneyland", "tdl", "東京ディズニーランド"], "search": "Tokyo Disneyland", "display": "東京迪士尼樂園", "country": "JP", "lat": 35.6329, "lng": 139.8804},
    "東京迪士尼海洋": {"aliases": ["东京迪士尼海洋", "tokyo disneysea", "tds", "東京ディズニーシー"], "search": "Tokyo DisneySea", "display": "東京迪士尼海洋", "country": "JP", "lat": 35.6267, "lng": 139.8850},
    "大阪環球影城": {"aliases": ["日本環球影城", "usj", "universal studios japan", "ユニバーサル"], "search": "Universal Studios Japan", "display": "日本環球影城", "country": "JP", "lat": 34.6654, "lng": 135.4323},
    "富士急樂園": {"aliases": ["富士急ハイランド", "fuji-q", "fujiq"], "search": "Fuji-Q Highland", "display": "富士急樂園", "country": "JP", "lat": 35.4833, "lng": 138.7778},
    
    # ═══════════════════════════════════════════════════════════════
    # 日本 - 東京景點 (含座標，可秒回)
    # ═══════════════════════════════════════════════════════════════
    "淺草寺": {"aliases": ["浅草寺", "senso-ji", "sensoji", "雷門"], "search": "Senso-ji Temple", "display": "淺草寺", "country": "JP", "lat": 35.7148, "lng": 139.7967},
    "東京鐵塔": {"aliases": ["东京塔", "tokyo tower", "東京タワー"], "search": "Tokyo Tower", "display": "東京鐵塔", "country": "JP", "lat": 35.6586, "lng": 139.7454},
    "晴空塔": {"aliases": ["天空樹", "skytree", "tokyo skytree", "スカイツリー", "东京晴空塔"], "search": "Tokyo Skytree", "display": "東京晴空塔", "country": "JP", "lat": 35.7101, "lng": 139.8107},
    "明治神宮": {"aliases": ["meiji shrine", "meiji jingu", "明治神宫"], "search": "Meiji Shrine", "display": "明治神宮", "country": "JP", "lat": 35.6764, "lng": 139.6993},
    "皇居": {"aliases": ["imperial palace", "皇居東御苑", "东京皇居"], "search": "Imperial Palace Tokyo", "display": "皇居", "country": "JP", "lat": 35.6852, "lng": 139.7528},
    "上野公園": {"aliases": ["ueno park", "上野恩賜公園"], "search": "Ueno Park", "display": "上野公園", "country": "JP", "lat": 35.7146, "lng": 139.7732},
    "新宿御苑": {"aliases": ["shinjuku gyoen", "新宿御苑"], "search": "Shinjuku Gyoen", "display": "新宿御苑", "country": "JP", "lat": 35.6852, "lng": 139.7100},
    "東京車站": {"aliases": ["东京站", "tokyo station", "東京駅"], "search": "Tokyo Station", "display": "東京車站", "country": "JP", "lat": 35.6812, "lng": 139.7671},
    "澀谷十字路口": {"aliases": ["涩谷", "shibuya crossing", "shibuya scramble", "スクランブル交差点", "渋谷"], "search": "Shibuya Crossing", "display": "澀谷十字路口", "country": "JP", "lat": 35.6595, "lng": 139.7004},
    "秋葉原": {"aliases": ["akihabara", "アキバ", "秋叶原"], "search": "Akihabara", "display": "秋葉原電器街", "country": "JP", "lat": 35.7023, "lng": 139.7745},
    "銀座": {"aliases": ["ginza", "銀座"], "search": "Ginza Tokyo", "display": "銀座", "country": "JP", "lat": 35.6717, "lng": 139.7649},
    "原宿": {"aliases": ["harajuku", "竹下通", "原宿竹下通"], "search": "Harajuku", "display": "原宿", "country": "JP", "lat": 35.6702, "lng": 139.7027},
    "池袋": {"aliases": ["ikebukuro", "池袋サンシャイン"], "search": "Ikebukuro", "display": "池袋", "country": "JP", "lat": 35.7295, "lng": 139.7109},
    "六本木": {"aliases": ["roppongi", "roppongi hills", "六本木ヒルズ"], "search": "Roppongi", "display": "六本木", "country": "JP", "lat": 35.6628, "lng": 139.7313},
    "台場": {"aliases": ["odaiba", "お台場", "彩虹大橋"], "search": "Odaiba", "display": "台場", "country": "JP", "lat": 35.6295, "lng": 139.7753},
    "自由女神像": {"aliases": ["odaiba statue of liberty", "お台場の自由の女神像", "自由の女神像"], "search": "Statue of Liberty Odaiba", "display": "台場自由女神像", "country": "JP", "lat": 35.6278727, "lng": 139.7718346},
    "築地市場": {"aliases": ["tsukiji", "tsukiji market", "築地"], "search": "Tsukiji Market", "display": "築地市場", "country": "JP", "lat": 35.6654, "lng": 139.7707},
    "豐洲市場": {"aliases": ["toyosu", "toyosu market", "豊洲市場"], "search": "Toyosu Market", "display": "豐洲市場", "country": "JP", "lat": 35.6455, "lng": 139.7853},
    # 購物/娛樂
    "teamLab Borderless": {"aliases": ["teamlab", "チームラボ", "teamlab planets", "數位藝術美術館"], "search": "teamLab Borderless", "display": "teamLab 數位藝術美術館", "country": "JP", "lat": 35.6265, "lng": 139.7837},  # 台場/豐洲
    "池袋陽光城": {"aliases": ["sunshine city", "サンシャインシティ", "sunshine 60"], "search": "Ikebukuro Sunshine City", "display": "池袋陽光城", "country": "JP", "lat": 35.7283, "lng": 139.7193},
    "東京巨蛋": {"aliases": ["tokyo dome", "東京ドーム", "tokyodome"], "search": "Tokyo Dome", "display": "東京巨蛋", "country": "JP", "lat": 35.7056, "lng": 139.7519},
    "表參道": {"aliases": ["omotesando", "表参道", "表參道hills"], "search": "Omotesando", "display": "表參道", "country": "JP", "lat": 35.6652, "lng": 139.7123},
    "代官山": {"aliases": ["daikanyama", "代官山蔦屋"], "search": "Daikanyama", "display": "代官山", "country": "JP", "lat": 35.6486, "lng": 139.7033},
    "自由之丘": {"aliases": ["jiyugaoka", "自由が丘"], "search": "Jiyugaoka", "display": "自由之丘", "country": "JP", "lat": 35.6073, "lng": 139.6689},
    "吉祥寺": {"aliases": ["kichijoji", "井之頭公園"], "search": "Kichijoji", "display": "吉祥寺", "country": "JP", "lat": 35.7031, "lng": 139.5796},
    "惠比壽": {"aliases": ["ebisu", "恵比寿", "惠比壽花園廣場"], "search": "Ebisu", "display": "惠比壽", "country": "JP", "lat": 35.6467, "lng": 139.7101},
    "中野百老匯": {"aliases": ["nakano broadway", "中野ブロードウェイ"], "search": "Nakano Broadway", "display": "中野百老匯", "country": "JP", "lat": 35.7078, "lng": 139.6657},
    "下北澤": {"aliases": ["shimokitazawa", "下北沢"], "search": "Shimokitazawa", "display": "下北澤", "country": "JP", "lat": 35.6618, "lng": 139.6682},
    # ═══════════════════════════════════════════════════════════════
    # 日本 - 京都景點 (含座標，可秒回)
    # ═══════════════════════════════════════════════════════════════
    "清水寺": {"aliases": ["kiyomizu-dera", "kiyomizudera", "清水の舞台"], "search": "Kiyomizu-dera", "display": "清水寺", "country": "JP", "lat": 34.9949, "lng": 135.7850},
    "金閣寺": {"aliases": ["kinkaku-ji", "kinkakuji", "金閣", "鹿苑寺"], "search": "Kinkaku-ji", "display": "金閣寺", "country": "JP", "lat": 35.0394, "lng": 135.7292},
    "銀閣寺": {"aliases": ["ginkaku-ji", "ginkakuji", "銀閣", "慈照寺"], "search": "Ginkaku-ji", "display": "銀閣寺", "country": "JP", "lat": 35.0270, "lng": 135.7982},
    "伏見稻荷大社": {"aliases": ["伏見稻荷", "fushimi inari", "千本鳥居", "伏見稲荷大社"], "search": "Fushimi Inari Taisha", "display": "伏見稻荷大社", "country": "JP", "lat": 34.9671, "lng": 135.7727},
    "嵐山": {"aliases": ["arashiyama", "嵐山竹林", "竹林小徑", "嵯峨野"], "search": "Arashiyama", "display": "嵐山", "country": "JP", "lat": 35.0094, "lng": 135.6667},
    "二條城": {"aliases": ["nijo castle", "二条城"], "search": "Nijo Castle", "display": "二條城", "country": "JP", "lat": 35.0142, "lng": 135.7479},
    "祇園": {"aliases": ["gion", "花見小路", "祇園花見小路"], "search": "Gion Kyoto", "display": "祇園", "country": "JP", "lat": 35.0037, "lng": 135.7751},
    "八坂神社": {"aliases": ["yasaka shrine", "八坂神社"], "search": "Yasaka Shrine", "display": "八坂神社", "country": "JP", "lat": 35.0036, "lng": 135.7785},
    "京都車站": {"aliases": ["kyoto station", "京都駅"], "search": "Kyoto Station", "display": "京都車站", "country": "JP", "lat": 34.9858, "lng": 135.7588},
    "錦市場": {"aliases": ["nishiki market", "錦市場"], "search": "Nishiki Market", "display": "錦市場", "country": "JP", "lat": 35.0050, "lng": 135.7649},
    "平安神宮": {"aliases": ["heian shrine", "平安神宮"], "search": "Heian Shrine", "display": "平安神宮", "country": "JP", "lat": 35.0160, "lng": 135.7820},
    "哲學之道": {"aliases": ["philosopher's path", "哲学の道"], "search": "Philosopher's Path", "display": "哲學之道", "country": "JP", "lat": 35.0233, "lng": 135.7942},
    
    # ═══════════════════════════════════════════════════════════════
    # 日本 - 大阪景點 (含座標，可秒回)
    # ═══════════════════════════════════════════════════════════════
    "道頓堀": {"aliases": ["dotonbori", "道頓崛", "固力果看板", "glico"], "search": "Dotonbori", "display": "道頓堀", "country": "JP", "lat": 34.6687, "lng": 135.5013},
    "心齋橋": {"aliases": ["shinsaibashi", "心斋桥"], "search": "Shinsaibashi", "display": "心齋橋", "country": "JP", "lat": 34.6748, "lng": 135.5009},
    "通天閣": {"aliases": ["tsutenkaku", "新世界"], "search": "Tsutenkaku", "display": "通天閣", "country": "JP", "lat": 34.6525, "lng": 135.5063},
    "大阪城": {"aliases": ["osaka castle", "大阪城公園", "大坂城"], "search": "Osaka Castle", "display": "大阪城", "country": "JP", "lat": 34.6873, "lng": 135.5262},
    "黑門市場": {"aliases": ["kuromon market", "黒門市場"], "search": "Kuromon Market", "display": "黑門市場", "country": "JP", "lat": 34.6679, "lng": 135.5065},
    "難波": {"aliases": ["namba", "なんば"], "search": "Namba Osaka", "display": "難波", "country": "JP", "lat": 34.6659, "lng": 135.5013},
    "梅田": {"aliases": ["umeda", "大阪梅田", "梅田スカイビル"], "search": "Umeda Osaka", "display": "梅田", "country": "JP", "lat": 34.7055, "lng": 135.4983},
    "天王寺": {"aliases": ["tennoji", "阿倍野harukas", "あべのハルカス"], "search": "Tennoji", "display": "天王寺", "country": "JP", "lat": 34.6473, "lng": 135.5135},
    "海遊館": {"aliases": ["kaiyukan", "osaka aquarium"], "search": "Osaka Aquarium Kaiyukan", "display": "海遊館", "country": "JP", "lat": 34.6545, "lng": 135.4290},
    "天保山": {"aliases": ["tempozan", "tempozan ferris wheel", "天保山大摩天輪"], "search": "Tempozan", "display": "天保山", "country": "JP", "lat": 34.6539, "lng": 135.4285},
    
    # ═══════════════════════════════════════════════════════════════
    # 日本 - 其他地區 (含座標，可秒回)
    # ═══════════════════════════════════════════════════════════════
    "富士山": {"aliases": ["mount fuji", "mt fuji", "fujisan", "富士山五合目"], "search": "Mount Fuji", "display": "富士山", "country": "JP", "lat": 35.3606, "lng": 138.7274},
    "箱根": {"aliases": ["hakone", "箱根温泉", "蘆之湖", "芦ノ湖"], "search": "Hakone", "display": "箱根", "country": "JP", "lat": 35.2324, "lng": 139.1069},
    "河口湖": {"aliases": ["kawaguchiko", "河口湖"], "search": "Lake Kawaguchi", "display": "河口湖", "country": "JP", "lat": 35.5163, "lng": 138.7519},
    "奈良公園": {"aliases": ["nara park", "奈良鹿", "東大寺", "奈良"], "search": "Nara Park", "display": "奈良公園", "country": "JP", "lat": 34.6851, "lng": 135.8430},
    "姬路城": {"aliases": ["himeji castle", "姫路城", "白鷺城"], "search": "Himeji Castle", "display": "姬路城", "country": "JP", "lat": 34.8394, "lng": 134.6939},
    "廣島和平公園": {"aliases": ["hiroshima peace park", "原爆ドーム", "原爆圓頂", "広島"], "search": "Hiroshima Peace Memorial", "display": "廣島和平紀念公園", "country": "JP", "lat": 34.3955, "lng": 132.4536},
    "宮島": {"aliases": ["miyajima", "厳島神社", "嚴島神社", "海上鳥居"], "search": "Itsukushima Shrine", "display": "宮島", "country": "JP", "lat": 34.2959, "lng": 132.3198},
    "金澤兼六園": {"aliases": ["kenrokuen", "兼六園", "金沢", "金澤"], "search": "Kenrokuen Garden", "display": "兼六園", "country": "JP", "lat": 36.5625, "lng": 136.6625},
    "白川鄉": {"aliases": ["shirakawa-go", "合掌村", "白川郷"], "search": "Shirakawa-go", "display": "白川鄉合掌村", "country": "JP", "lat": 36.2576, "lng": 136.9064},
    "沖繩美麗海水族館": {"aliases": ["churaumi", "美ら海水族館", "沖繩水族館", "美麗海"], "search": "Okinawa Churaumi Aquarium", "display": "沖繩美麗海水族館", "country": "JP", "lat": 26.6944, "lng": 127.8778},
    "札幌": {"aliases": ["sapporo", "時計台", "大通公園"], "search": "Sapporo", "display": "札幌", "country": "JP", "lat": 43.0618, "lng": 141.3545},
    "小樽運河": {"aliases": ["otaru canal", "小樽"], "search": "Otaru Canal", "display": "小樽運河", "country": "JP", "lat": 43.1970, "lng": 140.9940},
    "函館山": {"aliases": ["hakodate", "函館夜景", "函館山ロープウェイ"], "search": "Mount Hakodate", "display": "函館山", "country": "JP", "lat": 41.7587, "lng": 140.7031},
    
    # ═══════════════════════════════════════════════════════════════
    # 日本 - 人氣餐廳 (旗艦店座標，用於品牌搜索)
    # ═══════════════════════════════════════════════════════════════
    # 拉麵
    "一蘭拉麵": {"aliases": ["ichiran", "一蘭", "いちらん", "一蘭ラーメン"], "search": "Ichiran Ramen", "display": "一蘭拉麵", "country": "JP", "lat": 35.6617, "lng": 139.7037},  # 澀谷本店
    "一風堂": {"aliases": ["ippudo", "一風堂ラーメン", "博多一風堂"], "search": "Ippudo Ramen", "display": "一風堂", "country": "JP", "lat": 35.6938, "lng": 139.7034},  # 新宿本店
    "蒙古タンメン中本": {"aliases": ["nakamoto", "蒙古湯麵中本", "中本"], "search": "Mouko Tanmen Nakamoto", "display": "蒙古湯麵中本", "country": "JP", "lat": 35.7051, "lng": 139.7729},  # 池袋本店
    "麵屋武藏": {"aliases": ["menya musashi", "つけ麺"], "search": "Menya Musashi", "display": "麵屋武藏", "country": "JP", "lat": 35.6891, "lng": 139.6995},  # 新宿
    
    # 壽司
    "藏壽司": {"aliases": ["くら寿司", "kura sushi", "無添くら寿司"], "search": "Kura Sushi", "display": "藏壽司", "country": "JP", "lat": 35.6580, "lng": 139.7016},  # 澀谷店
    "壽司郎": {"aliases": ["スシロー", "sushiro", "スシロー回転寿司"], "search": "Sushiro", "display": "壽司郎", "country": "JP", "lat": 35.6896, "lng": 139.7006},  # 新宿店
    "築地壽司": {"aliases": ["tsukiji sushi", "築地すし", "すし大"], "search": "Tsukiji Sushi", "display": "築地壽司", "country": "JP", "lat": 35.6655, "lng": 139.7707},  # 築地
    
    # 燒肉/螃蟹
    "敘敘苑": {"aliases": ["叙々苑", "jojoen", "叙叙苑"], "search": "Jojoen Yakiniku", "display": "敘敘苑", "country": "JP", "lat": 35.6620, "lng": 139.7310},  # 六本木本店
    "牛角": {"aliases": ["gyukaku", "ぎゅうかく"], "search": "Gyukaku", "display": "牛角", "country": "JP", "lat": 35.6591, "lng": 139.7034},  # 澀谷店
    "蟹道樂": {"aliases": ["kani doraku", "かに道楽", "カニ道楽"], "search": "Kani Doraku", "display": "蟹道樂", "country": "JP", "lat": 34.6688, "lng": 135.5015},  # 道頓堀本店
    
    # 丼飯/定食
    "松屋": {"aliases": ["matsuya", "まつや", "松屋牛丼"], "search": "Matsuya", "display": "松屋", "country": "JP", "lat": 35.6896, "lng": 139.7006},  # 新宿
    "吉野家": {"aliases": ["yoshinoya", "よしのや"], "search": "Yoshinoya", "display": "吉野家", "country": "JP", "lat": 35.6580, "lng": 139.7016},  # 澀谷
    "すき家": {"aliases": ["sukiya", "すきや", "sukiya牛丼"], "search": "Sukiya", "display": "すき家", "country": "JP", "lat": 35.7296, "lng": 139.7109},  # 池袋
    "CoCo壱番屋": {"aliases": ["coco ichibanya", "ココイチ", "咖哩屋"], "search": "CoCo Ichibanya", "display": "CoCo壱番屋", "country": "JP", "lat": 35.6896, "lng": 139.7006},  # 新宿
    
    # 咖啡/甜點
    "Blue Bottle Coffee": {"aliases": ["藍瓶咖啡", "blue bottle", "ブルーボトル"], "search": "Blue Bottle Coffee", "display": "Blue Bottle Coffee", "country": "JP", "lat": 35.6617, "lng": 139.7037},  # 青山店
    "猿田彥咖啡": {"aliases": ["sarutahiko", "猿田彦珈琲"], "search": "Sarutahiko Coffee", "display": "猿田彥咖啡", "country": "JP", "lat": 35.6617, "lng": 139.7037},  # 惠比壽本店
    # ═══════════════════════════════════════════════════════════════
    # 日本 - 機場與車站 (含座標，可秒回)
    # ═══════════════════════════════════════════════════════════════
    "成田機場": {"aliases": ["narita airport", "narita", "nrt", "成田空港"], "search": "Narita Airport", "display": "成田國際機場", "country": "JP", "lat": 35.7720, "lng": 140.3929},
    "羽田機場": {"aliases": ["haneda airport", "haneda", "hnd", "羽田空港"], "search": "Haneda Airport", "display": "羽田國際機場", "country": "JP", "lat": 35.5494, "lng": 139.7798},
    "關西機場": {"aliases": ["kansai airport", "kix", "関西空港", "關西國際機場"], "search": "Kansai International Airport", "display": "關西國際機場", "country": "JP", "lat": 34.4347, "lng": 135.2441},
    "新大阪站": {"aliases": ["shin-osaka", "新大阪駅"], "search": "Shin-Osaka Station", "display": "新大阪站", "country": "JP", "lat": 34.7336, "lng": 135.5003},
    "品川站": {"aliases": ["shinagawa", "品川駅"], "search": "Shinagawa Station", "display": "品川站", "country": "JP", "lat": 35.6284, "lng": 139.7387},
    "新宿站": {"aliases": ["shinjuku station", "新宿駅"], "search": "Shinjuku Station", "display": "新宿站", "country": "JP", "lat": 35.6896, "lng": 139.7006},
    "澀谷站": {"aliases": ["shibuya station", "渋谷駅"], "search": "Shibuya Station", "display": "澀谷站", "country": "JP", "lat": 35.6580, "lng": 139.7016},
    "難波站": {"aliases": ["namba station", "難波駅", "なんば"], "search": "Namba Station", "display": "難波站", "country": "JP", "lat": 34.6659, "lng": 135.5013},
    "博多站": {"aliases": ["hakata station", "博多駅"], "search": "Hakata Station", "display": "博多站", "country": "JP", "lat": 33.5897, "lng": 130.4207},
    "名古屋站": {"aliases": ["nagoya station", "名古屋駅"], "search": "Nagoya Station", "display": "名古屋站", "country": "JP", "lat": 35.1709, "lng": 136.8815},
    "穴守稻荷車站": {"aliases": ["anamori inari", "anamoriinari", "穴守稻荷", "穴守稲荷", "穴守稲荷駅"], "search": "Anamori Inari Station", "display": "穴守稻荷車站", "country": "JP", "lat": 35.5502, "lng": 139.7470},
    
    # ═══════════════════════════════════════════════════════════════
    # 韓國 (含座標，可秒回)
    # ═══════════════════════════════════════════════════════════════
    "首爾塔": {"aliases": ["南山塔", "n seoul tower", "남산타워", "namsan tower"], "search": "N Seoul Tower", "display": "首爾塔", "country": "KR", "lat": 37.5512, "lng": 126.9882},
    "景福宮": {"aliases": ["gyeongbokgung", "경복궁", "光化門"], "search": "Gyeongbokgung Palace", "display": "景福宮", "country": "KR", "lat": 37.5796, "lng": 126.9770},
    "明洞": {"aliases": ["myeongdong", "명동", "明洞購物"], "search": "Myeongdong", "display": "明洞", "country": "KR", "lat": 37.5636, "lng": 126.9850},
    "弘大": {"aliases": ["hongdae", "홍대", "弘益大學"], "search": "Hongdae", "display": "弘大", "country": "KR", "lat": 37.5563, "lng": 126.9237},
    "東大門": {"aliases": ["dongdaemun", "동대문", "ddp"], "search": "Dongdaemun", "display": "東大門", "country": "KR", "lat": 37.5662, "lng": 127.0095},
    "梨泰院": {"aliases": ["itaewon", "이태원"], "search": "Itaewon", "display": "梨泰院", "country": "KR", "lat": 37.5344, "lng": 126.9947},
    "樂天世界": {"aliases": ["lotte world", "롯데월드", "樂天遊樂園"], "search": "Lotte World", "display": "樂天世界", "country": "KR", "lat": 37.5111, "lng": 127.0980},
    "樂天塔": {"aliases": ["lotte tower", "롯데타워", "樂天世界塔"], "search": "Lotte World Tower", "display": "樂天世界塔", "country": "KR", "lat": 37.5126, "lng": 127.1026},
    "北村韓屋村": {"aliases": ["bukchon", "북촌한옥마을", "韓屋村"], "search": "Bukchon Hanok Village", "display": "北村韓屋村", "country": "KR", "lat": 37.5827, "lng": 126.9850},
    "仁寺洞": {"aliases": ["insadong", "인사동"], "search": "Insadong", "display": "仁寺洞", "country": "KR", "lat": 37.5742, "lng": 126.9856},
    "江南": {"aliases": ["gangnam", "강남"], "search": "Gangnam Seoul", "display": "江南", "country": "KR", "lat": 37.4979, "lng": 127.0276},
    "仁川機場": {"aliases": ["incheon airport", "icn", "인천공항"], "search": "Incheon Airport", "display": "仁川國際機場", "country": "KR", "lat": 37.4602, "lng": 126.4407},
    "濟州島": {"aliases": ["jeju", "제주도", "濟州"], "search": "Jeju Island", "display": "濟州島", "country": "KR", "lat": 33.4996, "lng": 126.5312},
    "釜山海雲台": {"aliases": ["haeundae", "해운대", "海雲台"], "search": "Haeundae Beach", "display": "海雲台海灘", "country": "KR", "lat": 35.1587, "lng": 129.1604},
    
    # ═══════════════════════════════════════════════════════════════
    # 台灣 (含座標，可秒回)
    # ═══════════════════════════════════════════════════════════════
    "台北101": {"aliases": ["taipei 101", "101大樓", "一零一"], "search": "Taipei 101", "display": "台北101", "country": "TW", "lat": 25.0339, "lng": 121.5645},
    "九份": {"aliases": ["jiufen", "九份老街", "九分"], "search": "Jiufen Old Street", "display": "九份老街", "country": "TW", "lat": 25.1097, "lng": 121.8454},
    "西門町": {"aliases": ["ximending", "西門"], "search": "Ximending", "display": "西門町", "country": "TW", "lat": 25.0424, "lng": 121.5081},
    "士林夜市": {"aliases": ["shilin night market", "士林"], "search": "Shilin Night Market", "display": "士林夜市", "country": "TW", "lat": 25.0880, "lng": 121.5241},
    "饒河夜市": {"aliases": ["raohe night market", "饒河街"], "search": "Raohe Night Market", "display": "饒河夜市", "country": "TW", "lat": 25.0513, "lng": 121.5779},
    "故宮博物院": {"aliases": ["national palace museum", "台北故宮", "故宮"], "search": "National Palace Museum Taiwan", "display": "國立故宮博物院", "country": "TW", "lat": 25.1024, "lng": 121.5485},
    "日月潭": {"aliases": ["sun moon lake", "日月潭"], "search": "Sun Moon Lake", "display": "日月潭", "country": "TW", "lat": 23.8588, "lng": 120.9163},
    "阿里山": {"aliases": ["alishan", "阿里山森林"], "search": "Alishan", "display": "阿里山", "country": "TW", "lat": 23.5106, "lng": 120.8066},
    "台北車站": {"aliases": ["taipei station", "台北火車站", "北車"], "search": "Taipei Main Station", "display": "台北車站", "country": "TW", "lat": 25.0478, "lng": 121.5170},
    "中正紀念堂": {"aliases": ["chiang kai-shek memorial", "中正廟"], "search": "Chiang Kai-shek Memorial Hall", "display": "中正紀念堂", "country": "TW", "lat": 25.0350, "lng": 121.5219},
    "淡水老街": {"aliases": ["tamsui", "淡水", "漁人碼頭"], "search": "Tamsui Old Street", "display": "淡水老街", "country": "TW", "lat": 25.1697, "lng": 121.4383},
    "北投溫泉": {"aliases": ["beitou", "北投", "地熱谷"], "search": "Beitou Hot Spring", "display": "北投溫泉", "country": "TW", "lat": 25.1375, "lng": 121.5077},
    "桃園機場": {"aliases": ["taoyuan airport", "tpe", "桃機"], "search": "Taoyuan Airport", "display": "桃園國際機場", "country": "TW", "lat": 25.0777, "lng": 121.2327},
    "鹿港龍山寺": {"aliases": ["lukang longshan temple", "lukang lungshan temple"], "search": "Lukang Longshan Temple", "display": "鹿港龍山寺", "country": "TW", "lat": 24.0499, "lng": 120.4357},
    "龍山寺": {"aliases": ["艋舺龍山寺", "萬華龍山寺", "台北龍山寺", "lungshan temple", "longshan temple"], "search": "Lungshan Temple Taipei", "display": "艋舺龍山寺", "country": "TW", "lat": 25.0372, "lng": 121.4999},
    "大稻埕迪化街": {"aliases": ["迪化街", "大稻埕", "dihua street", "dadaocheng"], "search": "Dihua Street Taipei", "display": "大稻埕迪化街", "country": "TW", "lat": 25.0551, "lng": 121.5084},
    "剝皮寮歷史街區": {"aliases": ["剝皮寮", "bopiliao", "bopiliao historic block"], "search": "Bopiliao Historic Block", "display": "剝皮寮歷史街區", "country": "TW", "lat": 25.0368, "lng": 121.5022},
    "象山步道": {"aliases": ["象山", "象山親山步道", "elephant mountain"], "search": "Xiangshan Trail Taipei", "display": "象山親山步道", "country": "TW", "lat": 25.0275, "lng": 121.5712},
    
    # ═══════════════════════════════════════════════════════════════
    # 泰國
    # ═══════════════════════════════════════════════════════════════
    "大皇宮": {"aliases": ["grand palace", "大王宮", "พระบรมมหาราชวัง"], "search": "Grand Palace Bangkok", "display": "大皇宮", "country": "TH"},
    "臥佛寺": {"aliases": ["wat pho", "วัดโพธิ์", "涅槃寺"], "search": "Wat Pho", "display": "臥佛寺", "country": "TH"},
    "鄭王廟": {"aliases": ["wat arun", "วัดอรุณ", "黎明寺"], "search": "Wat Arun", "display": "鄭王廟", "country": "TH"},
    "考山路": {"aliases": ["khao san road", "ถนนข้าวสาร", "背包客街"], "search": "Khao San Road", "display": "考山路", "country": "TH"},
    "恰圖恰市場": {"aliases": ["chatuchak", "jj market", "週末市場"], "search": "Chatuchak Market", "display": "恰圖恰週末市場", "country": "TH"},
    "水門市場": {"aliases": ["pratunam", "水門"], "search": "Pratunam Market", "display": "水門市場", "country": "TH"},
    "四面佛": {"aliases": ["erawan shrine", "พระพรหม"], "search": "Erawan Shrine", "display": "四面佛", "country": "TH"},
    "暹羅廣場": {"aliases": ["siam square", "siam paragon", "สยาม"], "search": "Siam Square", "display": "暹羅廣場", "country": "TH"},
    "素萬那普機場": {"aliases": ["suvarnabhumi", "bkk", "曼谷機場"], "search": "Suvarnabhumi Airport", "display": "素萬那普國際機場", "country": "TH"},
    
    # ═══════════════════════════════════════════════════════════════
    # 新加坡
    # ═══════════════════════════════════════════════════════════════
    "魚尾獅": {"aliases": ["merlion", "merlion park", "鱼尾狮"], "search": "Merlion", "display": "魚尾獅公園", "country": "SG"},
    "濱海灣金沙": {"aliases": ["marina bay sands", "mbs", "金沙酒店"], "search": "Marina Bay Sands", "display": "濱海灣金沙酒店", "country": "SG"},
    "聖淘沙": {"aliases": ["sentosa", "環球影城新加坡"], "search": "Sentosa", "display": "聖淘沙島", "country": "SG"},
    "新加坡環球影城": {"aliases": ["universal studios singapore", "uss"], "search": "Universal Studios Singapore", "display": "新加坡環球影城", "country": "SG"},
    "烏節路": {"aliases": ["orchard road", "orchard"], "search": "Orchard Road", "display": "烏節路", "country": "SG"},
    "牛車水": {"aliases": ["chinatown singapore"], "search": "Chinatown Singapore", "display": "牛車水", "country": "SG"},
    "濱海灣花園": {"aliases": ["gardens by the bay", "超級樹"], "search": "Gardens by the Bay", "display": "濱海灣花園", "country": "SG"},
    "樟宜機場": {"aliases": ["changi airport", "sin", "星耀樟宜"], "search": "Changi Airport", "display": "樟宜國際機場", "country": "SG"},
    
    # ═══════════════════════════════════════════════════════════════
    # 香港
    # ═══════════════════════════════════════════════════════════════
    "太平山頂": {"aliases": ["victoria peak", "the peak", "山頂纜車"], "search": "Victoria Peak", "display": "太平山頂", "country": "HK"},
    "維多利亞港": {"aliases": ["victoria harbour", "維港", "幻彩詠香江"], "search": "Victoria Harbour", "display": "維多利亞港", "country": "HK"},
    "香港迪士尼": {"aliases": ["hong kong disneyland", "hkdl", "香港迪士尼樂園"], "search": "Hong Kong Disneyland", "display": "香港迪士尼樂園", "country": "HK"},
    "尖沙咀": {"aliases": ["tsim sha tsui", "tst", "尖沙嘴"], "search": "Tsim Sha Tsui", "display": "尖沙咀", "country": "HK"},
    "旺角": {"aliases": ["mong kok", "女人街", "波鞋街"], "search": "Mong Kok", "display": "旺角", "country": "HK"},
    "銅鑼灣": {"aliases": ["causeway bay", "时代广场"], "search": "Causeway Bay", "display": "銅鑼灣", "country": "HK"},
    "中環": {"aliases": ["central", "中環碼頭", "蘭桂坊"], "search": "Central Hong Kong", "display": "中環", "country": "HK"},
    "大嶼山": {"aliases": ["lantau", "昂坪360", "天壇大佛"], "search": "Lantau Island", "display": "大嶼山", "country": "HK"},
    "海洋公園": {"aliases": ["ocean park", "海洋公園"], "search": "Ocean Park Hong Kong", "display": "海洋公園", "country": "HK"},
    "香港機場": {"aliases": ["hong kong airport", "hkg", "赤鱲角"], "search": "Hong Kong International Airport", "display": "香港國際機場", "country": "HK"},
}

_INLINE_CHAIN_BRAND_KEYS = {
    "一蘭拉麵", "一風堂", "蒙古タンメン中本", "麵屋武藏",
    "藏壽司", "壽司郎", "築地壽司",
    "敘敘苑", "牛角", "蟹道樂",
    "松屋", "吉野家", "すき家", "CoCo壱番屋",
    "Blue Bottle Coffee", "猿田彥咖啡",
}
_RESTAURANT_LANDMARK_KEYS: set[str] = set()
_CHAIN_BRAND_TOKENS_CACHE: Optional[set[str]] = None
_HOMONYM_GUARD_NORM: set[str] = {normalize_cjk_chars(k) for k in HOMONYM_GUARD_KEYS}


def _get_chain_brand_tokens() -> set[str]:
    """彙整 BRANDS_DB 與內建連鎖餐飲品牌之正規化詞集（涵蓋與 LANDMARKS_DB 重疊之 46+ 筆連鎖項目）。"""
    global _CHAIN_BRAND_TOKENS_CACHE
    if _CHAIN_BRAND_TOKENS_CACHE is not None:
        return _CHAIN_BRAND_TOKENS_CACHE
    tokens: set[str] = {normalize_cjk_chars(k) for k in _INLINE_CHAIN_BRAND_KEYS if k}
    brands_db = get_brands_db()
    for category, brands in brands_db.items():
        if category.startswith("_") or not isinstance(brands, dict):
            continue
        for brand_name, brand_data in brands.items():
            if not isinstance(brand_data, dict):
                continue
            nb = normalize_cjk_chars(brand_name)
            if nb and len(nb) >= 2:
                tokens.add(nb)
            for alias in brand_data.get("aliases", []):
                na = normalize_cjk_chars(alias)
                if na and len(na) >= 2:
                    tokens.add(na)
    _CHAIN_BRAND_TOKENS_CACHE = tokens
    return tokens


def _is_chain_brand_entry(
    query: Optional[str] = None,
    landmark_data: Optional[dict] = None,
    display_name: Optional[str] = None,
    landmark_key: Optional[str] = None,
) -> bool:
    """判定地標項目或查詢是否屬多門市連鎖品牌（禁止單點秒回與覆寫分店名）。"""
    if landmark_key and (landmark_key in _INLINE_CHAIN_BRAND_KEYS or landmark_key in _RESTAURANT_LANDMARK_KEYS):
        return True
    if landmark_data is not None:
        for k, v in LANDMARKS_DB.items():
            if v is landmark_data:
                if k in _INLINE_CHAIN_BRAND_KEYS or k in _RESTAURANT_LANDMARK_KEYS:
                    return True
                landmark_key = landmark_key or k
                break
    brand_tokens = _get_chain_brand_tokens()
    fields = [landmark_key, display_name]
    if isinstance(landmark_data, dict):
        fields.append(landmark_data.get("display"))
        fields.extend(landmark_data.get("aliases") or [])
    if query:
        fields.append(query)
    for raw_f in fields:
        if not raw_f:
            continue
        nf = normalize_cjk_chars(str(raw_f))
        if not nf:
            continue
        if nf in brand_tokens:
            return True
        # 檢查是否為某連鎖品牌之分店條目（例如「一蘭 新宿中央東口店」、「一蘭拉麵(總店)」、「Blue Bottle (青山)」）
        if raw_f in (landmark_key, display_name, landmark_data.get("display") if isinstance(landmark_data, dict) else None):
            for bt in brand_tokens:
                if len(bt) < 2:
                    continue
                if bt.isascii():
                    if len(bt) >= 4 and re.search(rf"(?<![a-z0-9]){re.escape(bt)}(?![a-z0-9])", nf):
                        return True
                elif bt in nf:
                    return True
    return False


def get_fuzzy_index():
    global _FUZZY_INDEX, _LANDMARKS_KEYS_SORTED
    if _FUZZY_INDEX is not None:
        return _FUZZY_INDEX, _LANDMARKS_KEYS_SORTED
    
    print("🧠 [Lazy] Building fuzzy search index and loading external data...")
    _RESTAURANT_LANDMARK_KEYS.clear()
    _RESTAURANT_LANDMARK_KEYS.update(_INLINE_CHAIN_BRAND_KEYS)
    
    # 🆕 Load External JSON for Massive Expansion
    try:
        data_path = Path(__file__).parent.parent / "data" / "landmarks.json"
        if data_path.exists():
            external_data = orjson.loads(data_path.read_bytes())
            valid_entries = {k: v for k, v in external_data.items() if isinstance(v, dict) and not k.startswith("_")}
            LANDMARKS_DB.update(valid_entries)
            print(f"📦 Loaded {len(valid_entries)} external landmarks")
    except Exception as e:
        print(f"⚠️ Failed to load external landmarks: {e}")

    # 🆕 Load Country-Separated Data
    try:
        countries_dir = Path(__file__).parent.parent / "data" / "countries"
        if countries_dir.exists():
            for country_path in countries_dir.iterdir():
                if country_path.is_dir():
                    for json_file in country_path.glob("*.json"):
                        try:
                            country_data = orjson.loads(json_file.read_bytes())
                            valid_entries = {k: v for k, v in country_data.items() if isinstance(v, dict) and not k.startswith("_")}
                            LANDMARKS_DB.update(valid_entries)
                            if "restaurant" in json_file.stem.lower():
                                _RESTAURANT_LANDMARK_KEYS.update(valid_entries.keys())
                        except Exception: pass
            print("📦 Loaded country-specific databases")
    except Exception as e:
        print(f"⚠️ Failed to load country data: {e}")

    # Build Index
    _FUZZY_INDEX = {}
    for k, v in LANDMARKS_DB.items():
        norm = normalize_for_fuzzy(k)
        if norm: _FUZZY_INDEX[norm] = (k, v)
        for alias in v.get("aliases", []):
            norm_alias = normalize_for_fuzzy(alias)
            if norm_alias: _FUZZY_INDEX[norm_alias] = (k, v)
    
    _LANDMARKS_KEYS_SORTED = sorted(LANDMARKS_DB.keys(), key=len, reverse=True)
    print(f"[OK] [Lazy] Index built: {len(_FUZZY_INDEX)} entries")
    return _FUZZY_INDEX, _LANDMARKS_KEYS_SORTED


_EXACT_JP_DISNEY_QUERIES = {
    normalize_cjk_chars(k)
    for k in (
        "東京迪士尼", "東京迪士尼樂園",
        "tokyo disney", "tokyo disneyland",
        "東京ディズニーランド",
    )
}
_EXACT_HK_DISNEY_QUERIES = {
    normalize_cjk_chars(k)
    for k in (
        "香港迪士尼", "香港迪士尼樂園", "hong kong disney", "hong kong disneyland",
    )
}


def translate_famous_landmark(query: str, country_code: str = None, *, strict_country: bool = True) -> tuple:
    """🏰 確定性翻譯著名景點（全詞精確匹配閘門 + 主鍵優先於別名 + 連鎖品牌去劫持 + 目標國別隔離防呆）"""
    query_clean = (query or "").strip()
    query_lower = query_clean.lower()
    norm_query_chars = normalize_cjk_chars(query_clean)
    target_cc = (country_code or "").strip().upper()
    query_explicit_cc = (detect_country_from_keywords(query_clean) or "").upper()
    is_query_homonym = norm_query_chars in _HOMONYM_GUARD_NORM
    
    # 🆕 Lazy load indices
    FUZZY_INDEX, LANDMARKS_KEYS_SORTED = get_fuzzy_index()
    BRANDS_DB = get_brands_db()

    def _is_country_compatible(lm: dict) -> bool:
        lm_cc = (lm.get("country") or "").strip().upper()
        if not lm_cc or not target_cc:
            return True
        if query_explicit_cc and query_explicit_cc == lm_cc:
            return True
        return lm_cc == target_cc
    
    def _matches_phrase(needle: str, haystack: str) -> bool:
        n = (needle or "").strip().lower()
        if not n:
            return False
        # 純 ASCII 別名採單詞邊界比對（防止機場代碼 'sin' 誤中 'singapore'）
        if n.isascii():
            return bool(re.search(rf"(?<![a-z0-9]){re.escape(n)}(?![a-z0-9])", haystack))
        return n in haystack

    def _is_exact_token(candidate: str) -> bool:
        c = normalize_cjk_chars(candidate)
        return bool(c and norm_query_chars and c == norm_query_chars)

    # === 1. 全詞精確匹配（最快；Pass 1a 優先主鍵/顯示名，Pass 1b 才掃別名，杜絕『嵐山』被『星野虹夕諾雅』別名劫持） ===
    # 當 strict_country=False（僅地圖座標軟推斷，無明確鎖國）且非跨國同名地標時，允許無歧義精確地標跨國命中（如台北搜『晴空塔』『關西機場』『白川鄉』）。
    chain_fallback_terms: Optional[list] = None
    allow_cross_country_exact = (not strict_country) and (not is_query_homonym)

    def _scan_exact_landmarks(check_aliases: bool, enforce_cc: bool):
        nonlocal chain_fallback_terms
        for landmark_key in LANDMARKS_KEYS_SORTED:
            landmark = LANDMARKS_DB[landmark_key]
            if enforce_cc and not _is_country_compatible(landmark):
                continue
            if not check_aliases:
                matched_exact = _is_exact_token(landmark_key) or _is_exact_token(landmark.get("display", ""))
            else:
                matched_exact = any(_is_exact_token(alias) for alias in landmark.get("aliases", []))
            if matched_exact:
                if _is_chain_brand_entry(query_clean, landmark, landmark.get("display"), landmark_key=landmark_key):
                    if chain_fallback_terms is None and landmark.get("search"):
                        chain_fallback_terms = [landmark["search"], query_clean]
                    continue
                print(f"🏰 Landmark Exact Match: '{query_clean}' → '{landmark['display']}'")
                return ([landmark["search"], query_clean], landmark["display"], landmark)
        return None

    for check_aliases in (False, True):
        hit = _scan_exact_landmarks(check_aliases=check_aliases, enforce_cc=True)
        if hit is not None:
            return hit
        if allow_cross_country_exact:
            hit = _scan_exact_landmarks(check_aliases=check_aliases, enforce_cc=False)
            if hit is not None:
                return hit
    
    # === 2. 🆕 連鎖店品牌匹配（brands.json 為日本品牌庫，僅在日本或無目標國時啟用） ===
    # - 全詞精確命中（如 '一蘭'、'松本清'）剝除 OSM tag 泛用尾詞（ラーメン/ドラッグストア）置首以精準命中附近門市，同時保留原 search_term 守住契約；
    # - 子字串命中（如 '新宿一蘭拉麵'）保留地名前綴組合搜尋詞並令 display_name=None，絕不遺失區域前綴！
    _BRAND_GENERIC_TAIL_TOKENS = {
        "ラーメン", "牛丼", "カレー", "うどん", "焼き鳥", "回転寿司",
        "定食", "ファミレス", "コーヒー", "100均", "ドラッグストア", "コンビニ",
    }
    if not target_cc or target_cc == "JP" or query_explicit_cc == "JP":
        # 2a. 優先檢查全詞精確匹配
        for category, brands in BRANDS_DB.items():
            if category.startswith("_") or not isinstance(brands, dict):
                continue
            for brand_name, brand_data in brands.items():
                if not isinstance(brand_data, dict):
                    continue
                search_term = brand_data.get("search_term", brand_name)
                if _is_exact_token(brand_name) or any(_is_exact_token(a) for a in brand_data.get("aliases", [])):
                    st_parts = str(search_term).split()
                    effective_brand_term = (
                        " ".join(st_parts[:-1]).strip()
                        if len(st_parts) >= 2 and st_parts[-1] in _BRAND_GENERIC_TAIL_TOKENS and len(" ".join(st_parts[:-1]).strip()) >= 2
                        else search_term
                    )
                    terms = list(dict.fromkeys([effective_brand_term, search_term, query_clean]))
                    print(f"🏪 Brand Exact Match: '{query_clean}' → {terms}")
                    return (terms, brand_name, None)

        # 2b. 子字串匹配（保留區域前綴/後綴，例如 '新宿一蘭拉麵' -> '新宿 一蘭'，剝除 OSM tag 泛用尾詞如 ラーメン/牛丼 避免偏遠誤配，display_name=None）
        brand_candidates: List[tuple[str, str, str]] = []
        for category, brands in BRANDS_DB.items():
            if category.startswith("_") or not isinstance(brands, dict):
                continue
            for brand_name, brand_data in brands.items():
                if not isinstance(brand_data, dict):
                    continue
                search_term = brand_data.get("search_term", brand_name)
                brand_candidates.append((brand_name, search_term, brand_name))
                for alias in brand_data.get("aliases", []):
                    brand_candidates.append((alias, search_term, brand_name))
        brand_candidates.sort(key=lambda x: len(x[0]), reverse=True)
        for token, search_term, brand_name in brand_candidates:
            if _matches_phrase(token, query_lower):
                pattern = (
                    rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])"
                    if token.isascii()
                    else re.escape(token)
                )
                st_parts = str(search_term).split()
                effective_brand_term = (
                    " ".join(st_parts[:-1]).strip()
                    if len(st_parts) >= 2 and st_parts[-1] in _BRAND_GENERIC_TAIL_TOKENS and len(" ".join(st_parts[:-1]).strip()) >= 2
                    else search_term
                )
                combined = re.sub(pattern, f" {effective_brand_term} ", query_clean, count=1, flags=re.IGNORECASE)
                combined = re.sub(r"\s+", " ", combined).strip()
                terms = list(dict.fromkeys([combined, query_clean]))
                print(f"🏪 Brand Substring Match (Prefix Preserved): '{query_clean}' → {terms}")
                return (terms, None, None)

    if chain_fallback_terms:
        return (chain_fallback_terms, None, None)
    
    # === 3. 🆕 模糊搜尋（僅供純地標拼寫容錯；排除含設施/餐飲尾詞查詢與連鎖品牌，防止 '龍山寺站'/'台北101美食'/'東京迪士尼飯店' 誤命中） ===
    normalized_query = normalize_for_fuzzy(query_clean)
    if len(normalized_query) >= 2 and not _has_poi_or_food_intent(query_clean):
        match_result = process.extractOne(
            normalized_query,
            FUZZY_INDEX.keys(),
            scorer=fuzz.ratio,
            score_cutoff=88
        )
        
        if match_result:
            matched_key, score, _ = match_result
            landmark_key, landmark = FUZZY_INDEX[matched_key]
            if _is_country_compatible(landmark) and not _is_chain_brand_entry(query_clean, landmark, landmark.get("display"), landmark_key=landmark_key):
                print(f"[FUZZY] '{query_clean}' -> '{landmark['display']}' (score: {score})")
                return ([landmark["search"], query_clean], landmark["display"], landmark)

    # === 4. 特殊處理：迪士尼（僅限全詞精確指向樂園本體，杜絕劫持『東京迪士尼飯店』『迪士尼餐廳』） ===
    if norm_query_chars in _EXACT_JP_DISNEY_QUERIES and (
        target_cc == "JP" or any(jp in query_lower for jp in ("東京", "tokyo", "日本", "japan"))
    ):
        disney = LANDMARKS_DB.get("東京迪士尼樂園") or LANDMARKS_DB.get("東京迪士尼")
        return (["Tokyo Disneyland", "東京ディズニーランド", query_clean], "東京迪士尼樂園", disney)
    if norm_query_chars in _EXACT_HK_DISNEY_QUERIES and (target_cc == "HK" or "香港" in query_clean):
        return (["Hong Kong Disneyland", query_clean], "香港迪士尼樂園", None)
    
    return ([query_clean], None, None)


async def detect_country_from_trip_title(trip_title: str, api_key: str = None) -> str:
    """🧠 使用 Gemini 從行程標題判斷目的地國家
    
    Returns: 國家代碼 (JP, KR, TW...) 或 None
    """
    if not trip_title or not api_key:
        return None
    
    try:
        prompt = f"""你是一個旅遊地理專家。請判斷這個旅遊行程標題所隱含的目的地國家。

行程標題：「{trip_title}」

規則：
1. 請只回覆國家代碼（如 JP, KR, TW, TH, VN, SG, HK, US, GB, FR, IT, CA...）。
2. 如果標題是【人名】（例如：Ryan Su, John Doe）、【日期】（例如：2026 夏天）、【無意義編號】或【無法判斷目的地】時，必須回覆 NONE。
3. 如果是多國行程，回覆 NONE。
4. 只輸出代碼，不要任何其他文字或解釋。"""

        raw = await call_extraction_server(prompt, intent_type="GEOCODE", api_key=api_key)
        if not raw or not str(raw).strip():
            return None
        
        result = str(raw).strip().strip("`'\". ").upper()
        if result in COUNTRY_BOUNDS or result in _ISO_TO_ZH_NAME or result in _ISO_TO_EN_NAME:
            print(f"🧠 Trip title '{trip_title}' → Country: {result}")
            return result
        return None
    except Exception as e:
        print(f"ℹ️ [SmartGeo] TripTitle 國家推斷跳過 ({e})，轉入關鍵字檢索")
        return None


# 🆕 翻譯結果緩存（減少重複 AI / Wiki 調用，具上限防止記憶體無界成長）
TRANSLATION_CACHE: "OrderedDict[tuple, list]" = OrderedDict()
_MAX_TRANSLATION_CACHE_SIZE = 1024


def _set_translation_cache(key: tuple, val: list) -> None:
    TRANSLATION_CACHE[key] = val
    TRANSLATION_CACHE.move_to_end(key)
    while len(TRANSLATION_CACHE) > _MAX_TRANSLATION_CACHE_SIZE:
        TRANSLATION_CACHE.popitem(last=False)

# ==========================================
# 🗺️ 全球語系搜尋分級策略 (Global Language Geocoding Strategies)
# ==========================================

# 定義不同語系的搜尋指令模板
GEOCODE_STRATEGIES = {
    "CJK_V1": {
        "name": "CJK (日本/東亞) 專家模式",
        "instruction": "請翻譯成四種格式：1.日文漢字 2.平假名 3.片假名 4.羅馬拼音 (Romaji/English)。且各語系字串之間以換行分隔。"
    },
    "LATIN_V1": {
        "name": "Latin (歐美/澳) 標準模式",
        "instruction": "請將輸入詞強效對齊為「標準英文名稱」。不論輸入語系，務必回傳該地最權威的英文原名。"
    },
    "NATIVE_V1": {
        "name": "Native/Dual (韓/泰/越) 雙軌模式",
        "instruction": "請提供 1.母語寫法 (如 Hangul/Thai) 2.全球通用英文名。"
    },
    "GLOBAL_V1": {
        "name": "全域標準模式",
        "instruction": "請提供 1.當地母語寫法 2.通用英文名稱。"
    }
}

def get_country_search_strategy(country_code: str) -> str:
    """根據國碼回傳最適當的搜尋策略"""
    cc = country_code.upper() if country_code else ""
    if cc == "JP": return "CJK_V1"
    if cc in ["AU", "US", "GB", "CA", "NZ", "IE"]: return "LATIN_V1"
    if cc in ["KR", "TH", "VN", "RU", "UA", "KZ"]: return "NATIVE_V1"
    if cc in ["FR", "DE", "ES", "IT", "PT", "BE", "CH"]: return "GLOBAL_V1" # 拉丁變體暫歸全域
    return "GLOBAL_V1"

async def translate_place_name(
    query: str,
    country_code: str,
    api_key: str = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> list:
    """🔤 三層極速地名翻譯（0ms 通用設施微字典 ➔ 1.8s Flash-Lite [解鎖全球 122+ 國] ➔ 1.2s 免 Key Wikipedia langlinks）
    
    Returns: 搜尋變體列表 [翻譯後, 英文, 原文]
    """
    clean_q = (query or "").strip()
    if not clean_q or not country_code:
        return [clean_q or query]

    # 未完成注音符號直接原詞返回，不消耗翻譯配額
    if _INCOMPLETE_ZHUYIN_RE.search(clean_q):
        return [clean_q]

    cc = country_code.strip().upper()
    # 純英文/數字查詢於英語系國家無需翻譯
    if clean_q.isascii() and cc in ("US", "GB", "AU", "CA", "NZ", "IE", "SG"):
        return [clean_q]
    # 華語地區的中文查詢先檢查 0ms 區域慣用語/主題樂園微字典（如 TW 市政廳->市政府、HK 迪士尼->Hong Kong Disneyland），其餘走異體字展開
    if cc in ("TW", "CN", "HK", "MO") and _HAS_CJK_RE.search(clean_q):
        local_micro = _translate_via_micro_dict(clean_q, cc, lat=lat, lng=lng)
        if local_micro:
            return list(dict.fromkeys([*local_micro, clean_q]))[:5]
        return [clean_q]

    mode_tag = "ai" if api_key else "free"
    nearest_city_tag = (
        _find_nearest_city_anchor_en(lat, lng, country_code=cc, max_km=25.0) or ""
        if clean_q in GENERIC_FACILITY_TRANSLATIONS
        else ""
    )
    cache_key = (clean_q.lower(), cc, mode_tag, nearest_city_tag.lower())
    if cache_key in TRANSLATION_CACHE:
        TRANSLATION_CACHE.move_to_end(cache_key)
        print(f"🔤 CACHE HIT: '{clean_q}' ({cc}/{mode_tag}) → {TRANSLATION_CACHE[cache_key]}")
        return list(TRANSLATION_CACHE[cache_key])

    # Layer 1: 0ms 通用旅遊設施多語微字典（免 Key、跨歐美日韓，含座標鄰近城市精準組合）
    micro_terms = _translate_via_micro_dict(clean_q, cc, lat=lat, lng=lng)
    if micro_terms and not api_key:
        result = list(dict.fromkeys([*micro_terms, clean_q]))[:5]
        _set_translation_cache(cache_key, result)
        print(f"🔤 MicroDict '{clean_q}' ({cc}) → {result}")
        return result

    # Layer 2: 有 API Key 時呼叫 Flash-Lite（1.8s 硬上限，解鎖全球 122+ 國）
    ai_timed_out = False
    if api_key:
        try:
            strat_key = get_country_search_strategy(cc)
            strat_info = GEOCODE_STRATEGIES.get(strat_key, GEOCODE_STRATEGIES["GLOBAL_V1"])
            instruction = strat_info["instruction"]
            country_name = get_country_display_name(cc)

            prompt = f"""你是地理資訊與搜尋地標專家。用戶正在前往 {country_name} ({cc}) 進行旅行。
用戶目前的搜尋地名：「{clean_q}」

【核心指令】：{instruction}
【額外要求】：
1. 輸出格式為每行一個，不要有編號 (1. 2. 3.) 或註釋說明。
2. 最多回傳 3-4 行。
3. 如果輸入詞已是當地母語，請額外提供英文名。

只輸出翻譯後的關鍵字列表，每行一個："""

            raw = await asyncio.wait_for(
                call_extraction_server(prompt, intent_type="GEOCODE", api_key=api_key),
                timeout=1.8,
            )
            if raw and str(raw).strip():
                lines = [line.strip() for line in str(raw).strip().split("\n") if line.strip()]
                if lines:
                    merged = list(dict.fromkeys([*lines, *micro_terms, clean_q]))[:5]
                    _set_translation_cache(cache_key, merged)
                    print(f"🔤 Translated '{clean_q}' via {strat_key} ({cc}) → {merged} (cached)")
                    return merged
        except asyncio.TimeoutError:
            ai_timed_out = True
            print(f"🔤 AI Translation timed out (1.8s) for '{clean_q}' ({cc}); degrading to free bridge")
        except Exception as e:
            print(f"🔤 AI Translation fallback ({type(e).__name__}): {e}")

    # Layer 3: 免 Key（或 AI 超時）降級（先取微字典，未命中則 1.2s Wikipedia langlinks 跨語言橋接）
    if micro_terms:
        result = list(dict.fromkeys([*micro_terms, clean_q]))[:5]
        _set_translation_cache(cache_key, result)
        return result

    if (not api_key or ai_timed_out) and _HAS_CJK_RE.search(clean_q) and cc not in ("TW", "CN", "HK", "MO"):
        wiki_terms = await _translate_via_wikipedia_langlinks(clean_q, cc)
        if wiki_terms:
            result = list(dict.fromkeys([*wiki_terms, clean_q]))[:5]
            _set_translation_cache(cache_key, result)
            print(f"🔤 WikiLanglinks '{clean_q}' ({cc}) → {result}")
            return result

    return [clean_q]


def filter_results_by_country(results: list, country_code: str, strict: bool = True) -> list:
    """🗺️ 根據經緯度過濾結果：
    - strict=False（軟提示）時絕不硬刪跨國結果，全部保留交由 rerank_top_k 智慧排序；
    - strict=True（使用者明確鎖國或搜純國名）時過濾至目標國邊界，若無結果則優雅降級保留原列表。
    """
    if not strict or not country_code:
        return results
    cc = country_code.strip().upper()
    if cc not in COUNTRY_BOUNDS:
        return results
    
    bounds = COUNTRY_BOUNDS[cc]
    filtered = []
    
    for r in results:
        lat = r.get("lat", 0)
        lng = r.get("lng", 0)
        
        # 寬鬆邊界檢查 (+/- 0.1 度緩衝)
        if (bounds["lat_min"] - 0.1 <= lat <= bounds["lat_max"] + 0.1 and 
            bounds["lng_min"] - 0.1 <= lng <= bounds["lng_max"] + 0.1):
            filtered.append(r)
    
    if filtered:
        log_debug(f"Filtered: {len(results)} -> {len(filtered)} (Target: {cc}, strict=True)")
        return filtered
    
    # 關鍵優雅降級：若目標國過濾後無結果（如規劃日本行程搜尋「桃園機場」等跨國樞紐），
    # 絕不回傳空陣列，降級保留原候選結果，交由後續 Top-K 重排
    log_debug(f"Filtered: {len(results)} -> 0 (Fallback: retaining original results)")
    return results


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """計算兩點間的大圓距離 (km)"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2.0)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _fold_latin(text: str) -> str:
    """移除拉丁變音符號（例如 Zürich -> zurich、München -> munchen、Café -> cafe）。"""
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )


def _detect_script_family(text: str) -> str:
    """辨識地名主要文字系統，用於精準判定真正跨文字系統端名（例如 Athens vs Αθήνα、Bangkok vs กรุงเทพมหานคร）。"""
    if not text:
        return "latin"
    if re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", text):
        return "cjk"
    if re.search(r"[\uac00-\ud7af]", text):
        return "hangul"
    if re.search(r"[\u0e00-\u0e7f]", text):
        return "thai"
    if re.search(r"[\u0370-\u03ff]", text):
        return "greek"
    if re.search(r"[\u0400-\u04ff]", text):
        return "cyrillic"
    if re.search(r"[\u0600-\u06ff]", text):
        return "arabic"
    return "latin"


def _is_ordered_subsequence(needle: str, haystack: str) -> bool:
    """判定 needle 是否為 haystack 之保序子序列（如 '桃园机场' ∈ '台湾桃园国际机场'，但 '台中' ∉ '中台禅寺'）。"""
    it = iter(haystack)
    return all(ch in it for ch in needle)


def cjk_text_similarity(query: str, target: str) -> float:
    """多語／CJK 字義相似度（保序子序列 + 短子集折減 + 多 Bigram 召回保護）
    
    - 含 CJK 時：
      1) 完全相同 -> 1.0；去空白相同 -> 0.98；q 包含於 t -> 0.85..1.0；
      2) 短子集 (t 包含於 q，如 '大阪燒'->'大阪' 或 '一蘭總店'->'一蘭') 採冪次折減 (<0.75 / <0.50)；
      3) len(q)>=3 保序子序列且命中至少 1 個雙字 Bigram (如 '桃園機場'->'臺灣桃園國際機場') -> >=0.85；
      4) 其餘採 min(0.84, max(0.60*ratio + 0.40*token_sort, 多 Bigram 覆蓋保護))，
         壓制顛倒字 ('台中' vs '中台禪寺' <0.60) 同時保護跨序複合查詢 ('新宿一蘭拉麵' vs '一蘭 新宿中央東口店')。
    - 純非 CJK（拉丁/歐語等）採去變音符詞級與序列比對。
    """
    q = normalize_cjk_chars(query)
    t = normalize_cjk_chars(target)
    if not q or not t:
        return 0.0
    if q == t:
        return 1.0
    if q in t:
        return 0.85 + 0.15 * (len(q) / max(len(q), len(t)))
    if not _HAS_CJK_RE.search(q) and not _HAS_CJK_RE.search(t):
        qf = _fold_latin(q)
        tf = _fold_latin(t)
        if qf == tf:
            return 1.0
        if qf in tf:
            return 0.85 + 0.15 * (len(qf) / max(len(qf), len(tf)))
        seq_ratio = fuzz.ratio(qf, tf) / 100.0
        tok_sort = fuzz.token_sort_ratio(qf, tf) / 100.0
        tok_set = fuzz.token_set_ratio(qf, tf) / 100.0
        if len(tf) < len(qf) and " " in qf:
            tok_set *= (len(tf) / len(qf)) ** 0.5
        return max(seq_ratio, tok_sort, tok_set)

    qc = re.sub(r"\s+", "", q)
    tc = re.sub(r"\s+", "", t)
    if not qc or not tc:
        return 0.0
    if qc == tc:
        return 0.98
    if qc in tc:
        return 0.85 + 0.15 * (len(qc) / max(len(qc), len(tc)))
    if tc in qc:
        return min(0.75, 0.78 * ((len(tc) / len(qc)) ** 1.2))

    q_bigrams = [qc[i:i + 2] for i in range(len(qc) - 1)]
    matched_bigrams = [bg for bg in q_bigrams if bg in tc]
    if len(qc) >= 3 and _is_ordered_subsequence(qc, tc) and len(matched_bigrams) >= 1:
        return 0.85 + 0.10 * (len(qc) / max(len(qc), len(tc)))

    seq_ratio = fuzz.ratio(qc, tc) / 100.0
    tok_sort = fuzz.token_sort_ratio(" ".join(list(qc)), " ".join(list(tc))) / 100.0
    base = 0.60 * seq_ratio + 0.40 * tok_sort
    if len(matched_bigrams) >= 2:
        covered = set()
        for i in range(len(qc) - 1):
            if qc[i:i + 2] in tc:
                covered.add(i)
                covered.add(i + 1)
        bigram_cov = len(covered) / len(qc)
        bigram_score = 0.86 * bigram_cov * (0.85 + 0.15 * min(1.0, len(qc) / max(len(tc), 1)))
        base = max(base, bigram_score)
    return min(0.84, base)


def proximity_decay(dist_km: float, half_life_km: float = 150.0) -> float:
    """平滑有理衰減函數
    
    預設半衰期 150km（兼顧同城與跨區樞紐）；街景縮放 zoom>=14 可收斂至 15km 強化同城連鎖店排序。
    """
    return 1.0 / (1.0 + (dist_km / half_life_km))


_CJK_POI_OR_FOOD_MARKERS = (
    "燒", "麵", "面", "飯", "饭", "餐廳", "食堂", "咖啡", "火鍋", "牛排", "拉麵", "壽司",
    "燒肉", "居酒屋", "蛋糕", "麵包", "雪花冰", "剉冰", "刨冰", "冰店", "冰淇淋", "冰果室",
    "分店", "本店", "總店", "咖啡店", "書店", "藥妝店", "麵包店", "拉麵店", "便利商店",
    "車站", "站", "駅", "飯店", "酒店", "旅館", "民宿", "寺", "廟", "神社", "教堂",
    "公園", "市場", "夜市", "機場", "空港", "大學", "中學", "高中", "國小",
    "醫院", "藥局", "畫廊", "博物館", "美術館", "水族館", "圖書館", "展覽館", "體育館", "紀念館",
    "購物", "百貨", "大樓", "市政廳", "市政府", "歌劇院", "動物園", "植物園", "廣場", "城堡", "皇宮", "王宮",
)
_ASCII_POI_OR_FOOD_RE = re.compile(
    r"\b(?:tower|station|hotel|restaurant|cafe|coffee|bar|shop|market|temple|shrine|museum|gallery|mall|bakery|ramen|sushi|izakaya|palace|castle|cathedral|church|airport|hospital|pharmacy|hall|opera|zoo|park)\b",
    re.IGNORECASE,
)
_NON_LATIN_SCRIPT_RE = re.compile(
    r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\u0e00-\u0e7f\u0600-\u06ff\u0400-\u04ff\u0370-\u03ff]"
)
_STATION_QUERY_MARKERS = ("車站", "火車站", "地鐵站", "捷運站", "站", "駅", "station")
_CIVIC_QUERY_MARKERS = ("市政廳", "市政府", "city hall", "town hall", "rathaus", "市役所", "시청")
_THEME_PARK_QUERY_MARKERS = ("迪士尼", "環球影城", "disney", "disneyland", "universal studios", "樂園", "遊樂園")
_LANDMARK_QUERY_MARKERS = (
    "城堡", "皇宮", "王宮", "大教堂", "博物館", "美術館", "歌劇院", "鐵塔", "塔", "堡",
    "寺", "廟", "神社", "宮", "castle", "palace", "cathedral", "museum", "opera", "temple", "shrine",
)
_STATION_STRIP_RE = re.compile(
    r"(?:中央火車站|中央車站|火車站|地鐵站|捷運站|轉運站|車站|站|駅"
    r"| (?:central station|train station|railway station|station|hauptbahnhof|bahnhof|päärautatieasema|rautatieasema|gare centrale|stazione centrale|estación central|centraal station|centralstation))$",
    re.IGNORECASE,
)
_MACRO_GEO_TYPES = {"country", "state", "province", "city", "county", "municipality", "region", "administrative"}
_MINOR_UTILITY_TYPES = {"bus_stop", "parking", "bicycle_parking", "waste_basket", "atm", "post_box", "bench", "board", "ticket", "greenfield", "bureau_de_change", "residential", "pedestrian"}


def _has_poi_or_food_intent(query: str) -> bool:
    """精準偵測查詢是否為餐飲/店家/設施 POI（使用英文單詞邊界與精確中文詞尾，杜絕『Barcelona』被 bar、『冰島』被 冰 誤殺）。"""
    q_low = (query or "").strip().lower()
    if not q_low:
        return False
    if any(k in q_low for k in _CJK_POI_OR_FOOD_MARKERS):
        return True
    return bool(_ASCII_POI_OR_FOOD_RE.search(q_low))


def _normalize_osm_type(raw_type: Any) -> str:
    """統一 Photon ('N'/'W'/'R') 與 Nominatim/Overpass ('node'/'way'/'relation') 的 OSM 型別，確保跨源去重精準一致。"""
    t = str(raw_type or "").strip().lower()
    if t in ("n", "node"):
        return "node"
    if t in ("w", "way"):
        return "way"
    if t in ("r", "relation"):
        return "relation"
    return t


def rerank_top_k(
    candidates: list,
    query: str,
    bias_lat: Optional[float] = None,
    bias_lng: Optional[float] = None,
    target_country: Optional[str] = None,
    limit: Optional[int] = 5,
    zoom: Optional[float] = None,
    query_variants: Optional[List[str]] = None,
    is_explicit_country: bool = False,
    is_explicit_city: bool = False,
    explicit_city_coords: Optional[tuple[float, float]] = None,
    is_admin_region_anchor: bool = False,
    is_subdistrict_anchor: bool = False,
    prefix_label: Optional[str] = None,
) -> list:
    """多元加權智慧重排演算法（limit=None 或 <=0 時回傳全量排序結果，不截斷）
    
    FinalScore = 0.50 * 多變體字義相似度 + 0.30 * 動態空間衰減 + 0.10 * 權威重要度
               + 0.10 * 目標國軟加分 + 宏觀高相似度閘門(>=0.85) + 交通/市政/住宿軟加分
    """
    if not candidates:
        return []
        
    scored = []
    target_cc_up = target_country.upper() if target_country else ""
    target_bounds = COUNTRY_BOUNDS.get(target_cc_up) if target_cc_up else None

    # 彙整多語/異體字比對變體（使歐美/日文翻譯結果取得正確高分）
    variants: List[str] = []
    for raw_v in [query, *(query_variants or [])]:
        v = (raw_v or "").strip()
        if v and v not in variants:
            variants.append(v)
    variant_scripts = {_detect_script_family(v) for v in variants if v}

    q_lower = (query or "").strip().lower()
    wants_station = any(m in q_lower for m in _STATION_QUERY_MARKERS)
    wants_hotel = any(m in q_lower for m in ("飯店", "酒店", "旅館", "民宿", "ホテル", "hotel"))
    wants_civic = any(m in q_lower for m in _CIVIC_QUERY_MARKERS)
    wants_theme_park = (not wants_hotel) and any(m in q_lower for m in _THEME_PARK_QUERY_MARKERS)
    wants_landmark = any(m in q_lower for m in _LANDMARK_QUERY_MARKERS)
    wants_state_or_province = (
        is_admin_region_anchor
        or (len(q_lower) >= 3 and q_lower[-1] in ("省", "州", "府", "道", "縣", "県", "都"))
        or bool(re.search(r"\b(?:state|province|prefecture|county|region)\b", q_lower))
    )
    has_poi_or_food_tail = False if (is_explicit_country or is_explicit_city) else _has_poi_or_food_intent(query)
    stripped_station_variants: List[str] = []
    if wants_station:
        for v in variants:
            norm_v = re.sub(r"\s+", " ", v).strip()
            sv = _STATION_STRIP_RE.sub("", norm_v).strip()
            if sv and len(sv) >= 2 and sv not in stripped_station_variants:
                stripped_station_variants.append(sv)
    q_has_non_latin = bool(_NON_LATIN_SCRIPT_RE.search(q_lower))

    if is_subdistrict_anchor and (zoom is None or float(zoom) > 10.0):
        half_life = 5.0
    elif zoom is not None and float(zoom) >= 14.0:
        half_life = 15.0
    else:
        half_life = 150.0
    norm_prefix_label = normalize_cjk_chars(prefix_label) if prefix_label else ""

    for idx, item in enumerate(candidates):
        name = item.get("name", "") or ""
        lat = item.get("lat")
        lng = item.get("lng")
        item_type = str(item.get("type") or "").lower()
        osm_key = str(item.get("osm_key") or "").lower()
        admin_level = item.get("admin_level")
        item_source = str(item.get("source") or "").lower()
        
        # 1. 多變體字義相似度 (權重 50%)
        fuzz_score = max((cjk_text_similarity(v, name) for v in variants), default=0.0)

        # 明確國名／特別行政區查詢之當地母語權威實體對齊（支援 COUNTRY_BOUNDS 與國名雙軌判定）
        in_target_bounds = bool(
            target_bounds
            and lat is not None
            and lng is not None
            and target_bounds["lat_min"] - 0.1 <= lat <= target_bounds["lat_max"] + 0.1
            and target_bounds["lng_min"] - 0.1 <= lng <= target_bounds["lng_max"] + 0.1
        )
        if not in_target_bounds and target_cc_up and not target_bounds:
            item_country_raw = str(item.get("country") or "").strip()
            if item_country_raw:
                item_cc = country_to_iso(item_country_raw).upper()
                if item_cc and item_cc == target_cc_up:
                    in_target_bounds = True

        # 提前計算與空間基準點之距離（供跨語系保底與空間衰減共用）
        dist_km = None
        if bias_lat is not None and bias_lng is not None and lat is not None and lng is not None:
            dist_km = haversine_km(bias_lat, bias_lng, lat, lng)

        # 次區/城市前綴 + 店名（如『新宿一蘭拉麵』對應 OSM 門店 name='一蘭', address='東京都新宿区...'）：
        # 門店位於目標商圈 <=3km 或地址含前綴時給予前綴補強（上限 0.76，仍低於顯式完整分店名 '一蘭 新宿中央東口店' ~0.79）
        if (
            prefix_label
            and norm_prefix_label
            and name
            and norm_prefix_label not in normalize_cjk_chars(name)
        ):
            addr_blob = normalize_cjk_chars(
                " ".join(str(item.get(f) or "") for f in ("address", "display_name", "city", "state"))
            )
            in_prefixed_area = (
                (norm_prefix_label in addr_blob)
                or (is_subdistrict_anchor and dist_km is not None and dist_km <= 3.0)
            )
            if in_prefixed_area:
                prefixed_sim = max(
                    (cjk_text_similarity(v, f"{prefix_label} {name}") for v in variants),
                    default=0.0,
                )
                fuzz_score = max(fuzz_score, min(0.76, prefixed_sim * 0.90))

        is_sar_macro_entity = bool(
            is_explicit_country
            and target_cc_up in _OSM_SAR_CODES
            and in_target_bounds
            and (
                item_type in ("country", "state", "province", "city", "administrative")
                or (isinstance(admin_level, int) and admin_level in (2, 3, 4))
            )
            and fuzz_score >= 0.70
        )
        if (
            is_explicit_country
            and (
                ((item_type == "country" or admin_level == 2) and (item_source == "photon_global" or in_target_bounds))
                or is_sar_macro_entity
            )
        ):
            fuzz_score = max(fuzz_score, 0.95)

        # 明確城市／觀光小鎮／大區查詢之當地母語權威對齊：
        # 僅在「詞級相似度 >= 0.50」或「候選為所有查詢變體皆未覆蓋之非拉丁母語文字（如希臘文 Αθήνα、泰文 กรุงเทพมหานคร、韓文 서울특별시、英文查 Tokyo 對齊 東京都）」時放行，
        # 徹底杜絕鄰近同文字城市（如 Hoboken 劫持紐約、Ixelles 劫持布魯塞爾、Naha 劫持沖繩）之誤加權！
        anchor_dist_km: Optional[float] = None
        if is_explicit_city and explicit_city_coords is not None and lat is not None and lng is not None:
            anchor_dist_km = haversine_km(lat, lng, explicit_city_coords[0], explicit_city_coords[1])
            name_script = _detect_script_family(name)
            is_unrepresented_non_latin = (name_script != "latin" and name_script not in variant_scripts)
            if fuzz_score >= 0.50 or is_unrepresented_non_latin:
                if not wants_state_or_province and item_type in ("city", "municipality", "town") and anchor_dist_km <= 8.0:
                    fuzz_score = max(fuzz_score, 0.96)
                elif item_type in ("state", "province") and (
                    anchor_dist_km <= 15.0 or (wants_state_or_province and in_target_bounds and fuzz_score >= 0.75)
                ):
                    fuzz_score = max(fuzz_score, 0.95)

        # 跨語系索引命中保底（單調平滑：僅當候選文字系統未被任何查詢變體覆蓋、且位於目標國或錨點 30km 內時保底 0.65，消除 <0.45->0.72 非單調斷崖）
        if (
            item_source.startswith("photon")
            and not is_explicit_country
            and not is_explicit_city
            and name
            and len(q_lower) >= 3
            and (_detect_script_family(name) not in variant_scripts)
            and (in_target_bounds or (dist_km is not None and dist_km <= 30.0))
        ):
            fuzz_score = max(fuzz_score, 0.65)

        # 日本/歐洲 OSM 主車站常僅以城市名命名（例如 name="東京" 或 name="Helsinki", osm_key="railway", type="station"）
        is_major_station = (
            (osm_key == "railway" and item_type in ("station", "train_station"))
            or item_type in ("station", "train_station", "bus_station", "ferry_terminal")
        )
        is_minor_transit = (
            not is_major_station
            and (osm_key in ("railway", "public_transport") or item_type in ("halt", "tram_stop", "subway_entrance", "bus_stop"))
        )
        is_transit_candidate = is_major_station or is_minor_transit
        if wants_station and is_transit_candidate and stripped_station_variants:
            stripped_sim = max((cjk_text_similarity(sv, name) for sv in stripped_station_variants), default=0.0)
            if stripped_sim > fuzz_score:
                fuzz_score = stripped_sim
        
        # 2. 動態空間距離衰減 (權重 30%)
        proximity_score = 0.5
        if dist_km is not None:
            proximity_score = proximity_decay(dist_km, half_life_km=half_life)
            
        # 3. 權威度評分 (權重 10%)
        raw_imp = item.get("importance")
        if raw_imp is not None:
            try:
                imp_score = max(0.0, min(1.0, float(raw_imp)))
            except (ValueError, TypeError):
                imp_score = 0.1
        else:
            # 分源批次名次補償（對齊 Nominatim 0.15..0.45 尺度，避免 Photon 無 importance 項目壓過 Nominatim 大寺廟實測權威度）
            raw_batch_rank = item.get("_batch_rank")
            rank_idx = int(raw_batch_rank) if isinstance(raw_batch_rank, int) and raw_batch_rank >= 0 else idx
            imp_score = max(0.15, 0.45 - rank_idx * 0.03)
                
        # 4. 目標國軟性加分 (加分 10%)
        country_bonus = 0.10 if in_target_bounds else 0.0

        # 5. 交通/市政/地標/住宿類別軟性加分（取代舊版硬性 osm_tag 過濾，不誤殺轉運站與地下街，同時壓低公車站牌與藥局雜訊）
        category_bonus = 0.0
        if wants_station:
            if is_major_station:
                category_bonus = 0.08
            elif is_minor_transit:
                category_bonus = 0.02
            elif item_type in _MINOR_UTILITY_TYPES:
                category_bonus = -0.05
        elif wants_civic:
            if item_type in ("townhall", "city_hall", "public_building"):
                category_bonus = 0.12
            elif osm_key in ("tourism", "historic"):
                category_bonus = 0.04
            elif item_type in _MINOR_UTILITY_TYPES or item_type in ("pharmacy", "restaurant", "cafe", "fast_food", "tram_stop", "stop", "platform", "station"):
                category_bonus = -0.08
        elif wants_theme_park:
            if item_type in ("theme_park", "attraction", "resort", "amusement_park"):
                category_bonus = 0.14
            elif item_type in _MINOR_UTILITY_TYPES or item_type in ("pet", "bank", "bicycle_rental", "stop", "platform", "convenience", "clothes", "yes", "hotel"):
                category_bonus = -0.10
        elif wants_landmark:
            if (
                osm_key in ("tourism", "historic")
                or item_type in ("attraction", "castle", "palace", "museum", "cathedral", "theatre", "monument", "place_of_worship", "temple", "shrine")
            ):
                category_bonus = 0.08
            elif is_minor_transit or is_major_station or item_type in _MINOR_UTILITY_TYPES:
                category_bonus = -0.08
        elif wants_hotel:
            if osm_key == "tourism" or item_type in ("hotel", "hostel", "guest_house", "motel"):
                category_bonus = 0.06
            elif is_minor_transit or item_type in _MINOR_UTILITY_TYPES:
                category_bonus = -0.08

        # 6. 宏觀行政區高相似度保護閘門（僅 fuzz_score >= 0.85 且非餐飲/POI 查詢才加分，防止「大阪燒」被「大阪府」劫持；
        #    同名城市與省州共存時，除明確指定國名或省/州/府/道/縣/都查詢外，優先讓精準匹配的 city/municipality (fuzz>=0.95) 排在包覆它的 province/state 之前）
        macro_bonus = 0.0
        is_anchored_resort_town = bool(
            is_explicit_city
            and not wants_state_or_province
            and item_type == "town"
            and anchor_dist_km is not None
            and anchor_dist_km <= 8.0
        )
        is_macro_candidate = (
            item_type in _MACRO_GEO_TYPES
            or (isinstance(admin_level, int) and 1 <= admin_level <= 6)
            or is_anchored_resort_town
        )
        if is_macro_candidate and fuzz_score >= 0.85 and not has_poi_or_food_tail:
            if item_type == "country" or admin_level == 2 or is_sar_macro_entity:
                macro_bonus = 0.30
            elif (
                not is_explicit_country
                and not wants_state_or_province
                and (item_type in ("city", "municipality") or is_anchored_resort_town)
                and fuzz_score >= 0.95
            ):
                macro_bonus = 0.26
            elif item_type in ("state", "province") or (isinstance(admin_level, int) and admin_level <= 4):
                macro_bonus = 0.23
            else:
                macro_bonus = 0.20

        final_score = (
            0.50 * fuzz_score +
            0.30 * proximity_score +
            0.10 * imp_score +
            country_bonus +
            category_bonus +
            macro_bonus
        )
        
        item_copy = dict(item)
        item_copy.pop("_batch_rank", None)
        item_copy["_score"] = round(final_score, 4)
        if dist_km is not None:
            item_copy["_dist_km"] = round(dist_km, 2)
        scored.append((final_score, item_copy))
        
    scored.sort(key=lambda x: x[0], reverse=True)
    if limit is not None and limit > 0:
        return [item for _, item in scored[:limit]]
    return [item for _, item in scored]


# 🌍 地理編碼 API 端點（供前端使用）
# GeocodeSearchRequest, GeocodeReverseRequest 已移至 models/base.py

async def detect_country_from_query(query: str, api_key: str = None) -> str:
    """🧠 從搜尋關鍵字推斷國家（當標題失效時的 Fallback）"""
    if not query or not api_key:
        return None
        
    try:
        prompt = f"""用戶正在搜尋旅遊地點，請推測目標國家。
搜尋關鍵字：「{query}」

請只回覆國家代碼（如 JP, KR, TW, TH...）。
範例：
"東京迪士尼" -> JP
"首爾塔" -> KR
"士林夜市" -> TW
"101" -> TW

如果無法確定，回覆 NONE。
只輸出代碼，不要其他文字。"""

        from services.model_manager import call_extraction_server
        raw = await call_extraction_server(prompt, intent_type="GEOCODE", api_key=api_key)
        if not raw or not str(raw).strip():
            return None
        result = str(raw).strip().strip("`'\". ").upper()
        if result in COUNTRY_BOUNDS or result in _ISO_TO_ZH_NAME or result in _ISO_TO_EN_NAME:
            print(f"🧠 Query '{query}' → Country: {result}")
            return result
        return None
    except Exception as e:
        print(f"ℹ️ [SmartGeo] Query 國家推斷跳過 ({e})，轉入 Photon / Nominatim 檢索")
        return None

# 🆕 國家名稱 → 代碼映射 (全小寫，大小寫不敏感)
COUNTRY_NAME_TO_CODE = {
    # 2位 ISO 碼自我映射 (支援大小寫無縫直通)
    "jp": "JP", "tw": "TW", "kr": "KR", "th": "TH", "vn": "VN", "sg": "SG", "hk": "HK",
    "us": "US", "gb": "GB", "fr": "FR", "it": "IT", "de": "DE", "es": "ES", "is": "IS",
    "ch": "CH", "ca": "CA", "au": "AU", "nz": "NZ", "my": "MY", "id": "ID", "ph": "PH",
    # 日本
    "japan": "JP", "日本": "JP",
    # 台灣 (兩種寫法)
    "taiwan": "TW", "台灣": "TW", "臺灣": "TW",
    # 韓國
    "south korea": "KR", "korea": "KR", "韓國": "KR", "한국": "KR",
    # 泰國
    "thailand": "TH", "泰國": "TH", "ประเทศไทย": "TH",
    # 越南
    "vietnam": "VN", "越南": "VN",
    # 新加坡
    "singapore": "SG", "新加坡": "SG",
    # 香港
    "hong kong": "HK", "香港": "HK",
    # 🆕 美國
    "usa": "US", "united states": "US", "美國": "US", "美国": "US",
    # 🆕 英國
    "uk": "GB", "united kingdom": "GB", "england": "GB", "britain": "GB", "英國": "GB", "英国": "GB",
    # 🆕 法國
    "france": "FR", "法國": "FR", "法国": "FR",
    # 🆕 義大利
    "italy": "IT", "義大利": "IT", "意大利": "IT",
    # 🆕 澳洲
    "australia": "AU", "澳洲": "AU", "澳大利亞": "AU",
    # 🆕 德國
    "germany": "DE", "德國": "DE", "德国": "DE",
    # 🆕 西班牙
    "spain": "ES", "西班牙": "ES",
    # 🆕 加拿大
    "canada": "CA", "加拿大": "CA",
    # 🆕 中國
    "china": "CN", "中國": "CN", "中国": "CN",
    # 🆕 馬來西亞
    "malaysia": "MY", "馬來西亞": "MY", "马来西亚": "MY",
    # 🆕 印尼
    "indonesia": "ID", "印尼": "ID", "印度尼西亞": "ID",
    # 🆕 菲律賓
    "philippines": "PH", "菲律賓": "PH", "菲律宾": "PH",
}

# 🆕 別名兼容：將額外中文/英文別名安全融入，保護全域 190+ 國資料庫
for _k, _v in COUNTRY_NAME_TO_CODE.items():
    if _k not in GLOBAL_COUNTRY_TO_ISO:
        GLOBAL_COUNTRY_TO_ISO[_k] = _v.lower()

# 🌍 全球主要旅遊城市快速座標錨點表 (0ms 零網路延遲 Tier 4 兜底)
GLOBAL_CITY_ANCHORS: Dict[str, Dict[str, Any]] = {
    "台北": {"lat": 25.0330, "lng": 121.5654, "country": "TW"},
    "taipei": {"lat": 25.0330, "lng": 121.5654, "country": "TW"},
    "新北": {"lat": 25.0169, "lng": 121.4628, "country": "TW", "en": "New Taipei"},
    "new taipei": {"lat": 25.0169, "lng": 121.4628, "country": "TW", "en": "New Taipei"},
    "台中": {"lat": 24.1477, "lng": 120.6736, "country": "TW"},
    "taichung": {"lat": 24.1477, "lng": 120.6736, "country": "TW"},
    "台南": {"lat": 22.9999, "lng": 120.2269, "country": "TW"},
    "tainan": {"lat": 22.9999, "lng": 120.2269, "country": "TW"},
    "高雄": {"lat": 22.6273, "lng": 120.3014, "country": "TW"},
    "kaohsiung": {"lat": 22.6273, "lng": 120.3014, "country": "TW"},
    "花蓮": {"lat": 23.9872, "lng": 121.6016, "country": "TW"},
    "hualien": {"lat": 23.9872, "lng": 121.6016, "country": "TW"},
    "台東": {"lat": 22.7583, "lng": 121.1444, "country": "TW"},
    "taitung": {"lat": 22.7583, "lng": 121.1444, "country": "TW"},
    "宜蘭": {"lat": 24.7570, "lng": 121.7530, "country": "TW"},
    "yilan": {"lat": 24.7570, "lng": 121.7530, "country": "TW"},
    "澎湖": {"lat": 23.5711, "lng": 119.5793, "country": "TW"},
    "penghu": {"lat": 23.5711, "lng": 119.5793, "country": "TW"},
    "馬公": {"lat": 23.5654, "lng": 119.5663, "country": "TW"},
    "magong": {"lat": 23.5654, "lng": 119.5663, "country": "TW"},
    "金門": {"lat": 24.4321, "lng": 118.3171, "country": "TW"},
    "kinmen": {"lat": 24.4321, "lng": 118.3171, "country": "TW"},
    "墾丁": {"lat": 21.9483, "lng": 120.7798, "country": "TW"},
    "kenting": {"lat": 21.9483, "lng": 120.7798, "country": "TW"},
    "嘉義": {"lat": 23.4801, "lng": 120.4491, "country": "TW"},
    "chiayi": {"lat": 23.4801, "lng": 120.4491, "country": "TW"},
    "東京": {"lat": 35.6895, "lng": 139.6917, "country": "JP"},
    "tokyo": {"lat": 35.6895, "lng": 139.6917, "country": "JP"},
    "大阪": {"lat": 34.6937, "lng": 135.5023, "country": "JP"},
    "osaka": {"lat": 34.6937, "lng": 135.5023, "country": "JP"},
    "京都": {"lat": 35.0116, "lng": 135.7681, "country": "JP"},
    "kyoto": {"lat": 35.0116, "lng": 135.7681, "country": "JP"},
    "北海道": {"lat": 43.0618, "lng": 141.3545, "country": "JP", "en": "Hokkaido", "is_admin_region": True},
    "hokkaido": {"lat": 43.0618, "lng": 141.3545, "country": "JP", "en": "Hokkaido", "is_admin_region": True},
    "札幌": {"lat": 43.0618, "lng": 141.3545, "country": "JP", "en": "Sapporo"},
    "sapporo": {"lat": 43.0618, "lng": 141.3545, "country": "JP", "en": "Sapporo"},
    "沖繩": {"lat": 26.2124, "lng": 127.6809, "country": "JP", "en": "Okinawa", "is_admin_region": True},
    "okinawa": {"lat": 26.2124, "lng": 127.6809, "country": "JP", "en": "Okinawa", "is_admin_region": True},
    "那霸": {"lat": 26.2124, "lng": 127.6809, "country": "JP", "en": "Naha"},
    "naha": {"lat": 26.2124, "lng": 127.6809, "country": "JP", "en": "Naha"},
    "石垣島": {"lat": 24.3407, "lng": 124.1556, "country": "JP"},
    "ishigaki": {"lat": 24.3407, "lng": 124.1556, "country": "JP"},
    "福岡": {"lat": 33.5904, "lng": 130.4017, "country": "JP"},
    "fukuoka": {"lat": 33.5904, "lng": 130.4017, "country": "JP"},
    "名古屋": {"lat": 35.1815, "lng": 136.9066, "country": "JP"},
    "nagoya": {"lat": 35.1815, "lng": 136.9066, "country": "JP"},
    "箱根": {"lat": 35.2324, "lng": 139.1069, "country": "JP"},
    "hakone": {"lat": 35.2324, "lng": 139.1069, "country": "JP"},
    "河口湖": {"lat": 35.4982, "lng": 138.7686, "country": "JP"},
    "kawaguchiko": {"lat": 35.4982, "lng": 138.7686, "country": "JP"},
    "金澤": {"lat": 36.5613, "lng": 136.6562, "country": "JP"},
    "kanazawa": {"lat": 36.5613, "lng": 136.6562, "country": "JP"},
    "廣島": {"lat": 34.3853, "lng": 132.4553, "country": "JP"},
    "hiroshima": {"lat": 34.3853, "lng": 132.4553, "country": "JP"},
    "神戶": {"lat": 34.6901, "lng": 135.1955, "country": "JP"},
    "kobe": {"lat": 34.6901, "lng": 135.1955, "country": "JP"},
    "奈良": {"lat": 34.6851, "lng": 135.8048, "country": "JP"},
    "nara": {"lat": 34.6851, "lng": 135.8048, "country": "JP"},
    "仙台": {"lat": 38.2682, "lng": 140.8694, "country": "JP"},
    "sendai": {"lat": 38.2682, "lng": 140.8694, "country": "JP"},
    "函館": {"lat": 41.7687, "lng": 140.7288, "country": "JP"},
    "hakodate": {"lat": 41.7687, "lng": 140.7288, "country": "JP"},
    "小樽": {"lat": 43.1907, "lng": 140.9947, "country": "JP"},
    "otaru": {"lat": 43.1907, "lng": 140.9947, "country": "JP"},
    "橫濱": {"lat": 35.4437, "lng": 139.6380, "country": "JP"},
    "yokohama": {"lat": 35.4437, "lng": 139.6380, "country": "JP"},
    "輕井澤": {"lat": 36.3489, "lng": 138.5970, "country": "JP"},
    "karuizawa": {"lat": 36.3489, "lng": 138.5970, "country": "JP"},
    "首爾": {"lat": 37.5665, "lng": 126.9780, "country": "KR"},
    "seoul": {"lat": 37.5665, "lng": 126.9780, "country": "KR"},
    "釜山": {"lat": 35.1796, "lng": 129.0756, "country": "KR"},
    "busan": {"lat": 35.1796, "lng": 129.0756, "country": "KR"},
    "濟州": {"lat": 33.4996, "lng": 126.5312, "country": "KR"},
    "jeju": {"lat": 33.4996, "lng": 126.5312, "country": "KR"},
    "曼谷": {"lat": 13.7563, "lng": 100.5018, "country": "TH"},
    "bangkok": {"lat": 13.7563, "lng": 100.5018, "country": "TH"},
    "清邁": {"lat": 18.7883, "lng": 98.9853, "country": "TH", "en": "Chiang Mai"},
    "chiang mai": {"lat": 18.7883, "lng": 98.9853, "country": "TH", "en": "Chiang Mai"},
    "新加坡": {"lat": 1.3521, "lng": 103.8198, "country": "SG"},
    "singapore": {"lat": 1.3521, "lng": 103.8198, "country": "SG"},
    "香港": {"lat": 22.3193, "lng": 114.1694, "country": "HK"},
    "hong kong": {"lat": 22.3193, "lng": 114.1694, "country": "HK"},
    "巴黎": {"lat": 48.8566, "lng": 2.3522, "country": "FR"},
    "paris": {"lat": 48.8566, "lng": 2.3522, "country": "FR"},
    "倫敦": {"lat": 51.5074, "lng": -0.1278, "country": "GB"},
    "london": {"lat": 51.5074, "lng": -0.1278, "country": "GB"},
    "羅馬": {"lat": 41.9028, "lng": 12.4964, "country": "IT"},
    "rome": {"lat": 41.9028, "lng": 12.4964, "country": "IT"},
    "米蘭": {"lat": 45.4642, "lng": 9.1900, "country": "IT"},
    "milan": {"lat": 45.4642, "lng": 9.1900, "country": "IT"},
    "紐約": {"lat": 40.7128, "lng": -74.0060, "country": "US"},
    "new york": {"lat": 40.7128, "lng": -74.0060, "country": "US"},
    "雪梨": {"lat": -33.8688, "lng": 151.2093, "country": "AU"},
    "sydney": {"lat": -33.8688, "lng": 151.2093, "country": "AU"},
    "墨爾本": {"lat": -37.8136, "lng": 144.9631, "country": "AU"},
    "melbourne": {"lat": -37.8136, "lng": 144.9631, "country": "AU"},
    # 台灣補充縣市（『臺』異體字由 normalize_cjk_chars 統一對齊，不重複插入避免覆蓋『台北』主標籤）
    "桃園": {"lat": 24.9936, "lng": 121.3010, "country": "TW"},
    "taoyuan": {"lat": 24.9936, "lng": 121.3010, "country": "TW"},
    "新竹": {"lat": 24.8138, "lng": 120.9675, "country": "TW"},
    "hsinchu": {"lat": 24.8138, "lng": 120.9675, "country": "TW"},
    "基隆": {"lat": 25.1276, "lng": 121.7392, "country": "TW"},
    "keelung": {"lat": 25.1276, "lng": 121.7392, "country": "TW"},
    "彰化": {"lat": 24.0518, "lng": 120.5161, "country": "TW"},
    "changhua": {"lat": 24.0518, "lng": 120.5161, "country": "TW"},
    "屏東": {"lat": 22.6762, "lng": 120.4929, "country": "TW"},
    "pingtung": {"lat": 22.6762, "lng": 120.4929, "country": "TW"},
    "南投": {"lat": 23.9610, "lng": 120.9719, "country": "TW"},
    "nantou": {"lat": 23.9610, "lng": 120.9719, "country": "TW"},
    # 歐洲主要旅遊城市
    "慕尼黑": {"lat": 48.1351, "lng": 11.5820, "country": "DE"},
    "munich": {"lat": 48.1351, "lng": 11.5820, "country": "DE"},
    "柏林": {"lat": 52.5200, "lng": 13.4050, "country": "DE"},
    "berlin": {"lat": 52.5200, "lng": 13.4050, "country": "DE"},
    "法蘭克福": {"lat": 50.1109, "lng": 8.6821, "country": "DE"},
    "frankfurt": {"lat": 50.1109, "lng": 8.6821, "country": "DE"},
    "漢堡": {"lat": 53.5511, "lng": 9.9937, "country": "DE"},
    "hamburg": {"lat": 53.5511, "lng": 9.9937, "country": "DE"},
    "科隆": {"lat": 50.9375, "lng": 6.9603, "country": "DE"},
    "cologne": {"lat": 50.9375, "lng": 6.9603, "country": "DE"},
    "赫爾辛基": {"lat": 60.1699, "lng": 24.9384, "country": "FI"},
    "helsinki": {"lat": 60.1699, "lng": 24.9384, "country": "FI"},
    "羅瓦涅米": {"lat": 66.5039, "lng": 25.7294, "country": "FI"},
    "rovaniemi": {"lat": 66.5039, "lng": 25.7294, "country": "FI"},
    "斯德哥爾摩": {"lat": 59.3293, "lng": 18.0686, "country": "SE"},
    "stockholm": {"lat": 59.3293, "lng": 18.0686, "country": "SE"},
    "奧斯陸": {"lat": 59.9139, "lng": 10.7522, "country": "NO"},
    "oslo": {"lat": 59.9139, "lng": 10.7522, "country": "NO"},
    "哥本哈根": {"lat": 55.6761, "lng": 12.5683, "country": "DK"},
    "copenhagen": {"lat": 55.6761, "lng": 12.5683, "country": "DK"},
    "雷克雅維克": {"lat": 64.1466, "lng": -21.9426, "country": "IS"},
    "reykjavik": {"lat": 64.1466, "lng": -21.9426, "country": "IS"},
    "阿姆斯特丹": {"lat": 52.3676, "lng": 4.9041, "country": "NL"},
    "amsterdam": {"lat": 52.3676, "lng": 4.9041, "country": "NL"},
    "鹿特丹": {"lat": 51.9244, "lng": 4.4777, "country": "NL"},
    "rotterdam": {"lat": 51.9244, "lng": 4.4777, "country": "NL"},
    "布魯塞爾": {"lat": 50.8503, "lng": 4.3517, "country": "BE"},
    "brussels": {"lat": 50.8503, "lng": 4.3517, "country": "BE"},
    "維也納": {"lat": 48.2082, "lng": 16.3738, "country": "AT"},
    "vienna": {"lat": 48.2082, "lng": 16.3738, "country": "AT"},
    "薩爾茨堡": {"lat": 47.8095, "lng": 13.0550, "country": "AT"},
    "salzburg": {"lat": 47.8095, "lng": 13.0550, "country": "AT"},
    "蘇黎世": {"lat": 47.3769, "lng": 8.5417, "country": "CH"},
    "zurich": {"lat": 47.3769, "lng": 8.5417, "country": "CH"},
    "日內瓦": {"lat": 46.2044, "lng": 6.1432, "country": "CH"},
    "geneva": {"lat": 46.2044, "lng": 6.1432, "country": "CH"},
    "布拉格": {"lat": 50.0755, "lng": 14.4378, "country": "CZ"},
    "prague": {"lat": 50.0755, "lng": 14.4378, "country": "CZ"},
    "布達佩斯": {"lat": 47.4979, "lng": 19.0402, "country": "HU"},
    "budapest": {"lat": 47.4979, "lng": 19.0402, "country": "HU"},
    "華沙": {"lat": 52.2297, "lng": 21.0122, "country": "PL"},
    "warsaw": {"lat": 52.2297, "lng": 21.0122, "country": "PL"},
    "馬德里": {"lat": 40.4168, "lng": -3.7038, "country": "ES"},
    "madrid": {"lat": 40.4168, "lng": -3.7038, "country": "ES"},
    "巴塞隆納": {"lat": 41.3874, "lng": 2.1686, "country": "ES"},
    "barcelona": {"lat": 41.3874, "lng": 2.1686, "country": "ES"},
    "里斯本": {"lat": 38.7223, "lng": -9.1393, "country": "PT"},
    "lisbon": {"lat": 38.7223, "lng": -9.1393, "country": "PT"},
    "威尼斯": {"lat": 45.4408, "lng": 12.3155, "country": "IT"},
    "venice": {"lat": 45.4408, "lng": 12.3155, "country": "IT"},
    "佛羅倫斯": {"lat": 43.7696, "lng": 11.2558, "country": "IT"},
    "florence": {"lat": 43.7696, "lng": 11.2558, "country": "IT"},
    "雅典": {"lat": 37.9838, "lng": 23.7275, "country": "GR"},
    "athens": {"lat": 37.9838, "lng": 23.7275, "country": "GR"},
    "都柏林": {"lat": 53.3498, "lng": -6.2603, "country": "IE"},
    "dublin": {"lat": 53.3498, "lng": -6.2603, "country": "IE"},
    "愛丁堡": {"lat": 55.9533, "lng": -3.1883, "country": "GB"},
    "edinburgh": {"lat": 55.9533, "lng": -3.1883, "country": "GB"},
    # 美洲 / 大洋洲 / 中東主要旅遊城市
    "洛杉磯": {"lat": 34.0522, "lng": -118.2437, "country": "US"},
    "los angeles": {"lat": 34.0522, "lng": -118.2437, "country": "US"},
    "舊金山": {"lat": 37.7749, "lng": -122.4194, "country": "US"},
    "san francisco": {"lat": 37.7749, "lng": -122.4194, "country": "US"},
    "西雅圖": {"lat": 47.6062, "lng": -122.3321, "country": "US"},
    "seattle": {"lat": 47.6062, "lng": -122.3321, "country": "US"},
    "芝加哥": {"lat": 41.8781, "lng": -87.6298, "country": "US"},
    "chicago": {"lat": 41.8781, "lng": -87.6298, "country": "US"},
    "波士頓": {"lat": 42.3601, "lng": -71.0589, "country": "US"},
    "boston": {"lat": 42.3601, "lng": -71.0589, "country": "US"},
    "溫哥華": {"lat": 49.2827, "lng": -123.1207, "country": "CA"},
    "vancouver": {"lat": 49.2827, "lng": -123.1207, "country": "CA"},
    "多倫多": {"lat": 43.6532, "lng": -79.3832, "country": "CA"},
    "toronto": {"lat": 43.6532, "lng": -79.3832, "country": "CA"},
    "奧克蘭": {"lat": -36.8509, "lng": 174.7645, "country": "NZ"},
    "auckland": {"lat": -36.8509, "lng": 174.7645, "country": "NZ"},
    "杜拜": {"lat": 25.2048, "lng": 55.2708, "country": "AE"},
    "dubai": {"lat": 25.2048, "lng": 55.2708, "country": "AE"},
    "伊斯坦堡": {"lat": 41.0082, "lng": 28.9784, "country": "TR"},
    "istanbul": {"lat": 41.0082, "lng": 28.9784, "country": "TR"},
}


def extract_region_for_search(region: str) -> str:
    """
    從中英文行程標題提取純淨的目的地詞組：
    - '3 Day Taipei Explorer ✨' -> 'Taipei'
    - '2026 東京自由行' -> '東京'
    - 'Alice 東京行程' -> '東京'
    - '7 Days in Cusco' -> 'Cusco'
    """
    if not region:
        return ""
    raw = str(region).strip()
    raw_lower = raw.lower()

    city_state_keys = {"新加坡", "singapore", "香港", "hong kong"}
    country_only_names = (
        {k.lower() for k in COUNTRY_NAME_TO_CODE.keys()}
        | {k.lower() for k in GLOBAL_COUNTRY_TO_ISO.keys()}
    ) - city_state_keys

    # Stage 1: 優先精準匹配已知城市與次級區域關鍵字 (排除純國名，避免 '台灣台中一日遊' 或 'Peru Cusco' 被國名攔截)
    city_candidates = list(GLOBAL_CITY_ANCHORS.keys())
    for kws in LOCATION_KEYWORDS.values():
        city_candidates.extend(k for k in kws if k.lower() not in country_only_names)
    for kw in sorted(set(city_candidates), key=len, reverse=True):
        kw_low = kw.lower()
        if kw_low.isascii():
            if len(kw_low) < 3:
                continue
            m = re.search(r'\b' + re.escape(kw_low) + r'\b', raw_lower)
            if m:
                return raw[m.start():m.end()]
        else:
            if len(kw_low) >= 2 and kw_low in raw_lower:
                idx = raw_lower.find(kw_low)
                return raw[idx:idx + len(kw)]

    # Stage 2: 啟發式剝離天數、年份、人名所有格、旅遊後綴與 Emoji (適用全球未知冷門城市)
    raw_truncated = raw[:800]
    clean = re.sub(r'[^\w\s\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af-]', ' ', raw_truncated)
    clean = re.sub(r'(?:19|20)\d{2}\s*年?', ' ', clean)
    clean = re.sub(
        r'((?:\d{1,3}|[一二三四五六七八九十百兩]{1,5})\s*(?:日遊|天(?:[0-9一二三四五六七八九十百兩]{1,4}夜)?|日)|自由行|之旅|極致之旅|深度遊|行程|冬日遊|夏日遊|攻略|漫遊|快閃|旅遊|旅行)',
        ' ',
        clean,
    )
    clean = re.sub(
        r'\b(\d+\s*days?|\d+\s*nights?|\d+d\d*n|day\s*\d+|in|to|at|for|of|the|my|our|trip|travel|itinerary|explorer|adventure|vacation|tour|guide)\b',
        ' ',
        clean,
        flags=re.IGNORECASE,
    )
    tokens = [t.strip() for t in clean.split() if t.strip() and not t.strip().isdigit()]
    non_country_tokens = [t for t in tokens if t.lower() not in country_only_names]

    # 若標題僅含純國名 (如 '2026 日本自由行'、'Alice 日本行程')，提取已知國名
    country_candidates = [
        k for k in country_only_names
        if (not k.isascii() and len(k) >= 2) or (k.isascii() and len(k) >= 4)
    ]
    matched_country = ""
    for kw_low in sorted(set(country_candidates), key=len, reverse=True):
        if kw_low.isascii():
            m = re.search(r'\b' + re.escape(kw_low) + r'\b', raw_lower)
            if m:
                matched_country = raw[m.start():m.end()]
                break
        else:
            if kw_low in raw_lower:
                idx = raw_lower.find(kw_low)
                matched_country = raw[idx:idx + len(kw_low)]
                break

    if matched_country and (not non_country_tokens or (not matched_country.isascii() and all(t.isascii() for t in non_country_tokens))):
        return matched_country

    if non_country_tokens:
        return non_country_tokens[-1]
    return tokens[-1] if tokens else matched_country


async def resolve_trip_spatial_anchor(
    trip: Optional[Dict[str, Any]],
    day_number: int = 1,
    existing_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    🌍 全球通用 4 層由近而遠動態空間錨點解析器 (4-Tier Dynamic Spatial Anchor)
    優先級：
      Tier 1: 當日明確設定之 daily_locations[day]
      Tier 2: 當日既有景點座標中位數 (Same-Day Items Centroid)
      Tier 3: 鄰近天數軌跡座標 (Sequential Trajectory: Day d-1, d+1...)
      Tier 4: 行程標題動態目的地解析 (GLOBAL_CITY_ANCHORS 0ms ➔ smart_geocode_logic)
    """
    anchor_lat: Optional[float] = None
    anchor_lng: Optional[float] = None
    region_name: str = ""
    inferred_country: Optional[str] = None

    trip_dict = trip if isinstance(trip, dict) else {}
    content = trip_dict.get("content") if isinstance(trip_dict.get("content"), dict) else {}
    daily_locs = content.get("daily_locations") if isinstance(content.get("daily_locations"), dict) else {}

    # Tier 1: 當日明確設定之 daily_locations[day]
    day_loc = daily_locs.get(str(day_number)) or daily_locs.get(day_number)
    day_segments: List[Dict[str, Any]] = []
    if isinstance(day_loc, dict):
        region_name = str(day_loc.get("name") or "").strip()
        try:
            if day_loc.get("lat") is not None and day_loc.get("lng") is not None:
                lat_f, lng_f = float(day_loc["lat"]), float(day_loc["lng"])
                if lat_f != 0.0 and lng_f != 0.0:
                    anchor_lat, anchor_lng = lat_f, lng_f
        except (ValueError, TypeError):
            pass
        raw_segs = day_loc.get("segments")
        if isinstance(raw_segs, list):
            for seg in raw_segs:
                if isinstance(seg, dict):
                    try:
                        if seg.get("lat") is not None and seg.get("lng") is not None:
                            slat, slng = float(seg["lat"]), float(seg["lng"])
                            if -90.0 <= slat <= 90.0 and -180.0 <= slng <= 180.0 and (slat != 0.0 or slng != 0.0):
                                day_segments.append({
                                    "name": str(seg.get("name") or "").strip(),
                                    "lat": slat,
                                    "lng": slng,
                                })
                    except (ValueError, TypeError):
                        pass

    # Tier 2 & 3: 當日既有景點座標中位數 -> 鄰近天數軌跡座標
    items = existing_items if isinstance(existing_items, list) else []
    if anchor_lat is None or anchor_lng is None:
        same_day_coords = []
        other_day_coords = []
        for it in items:
            if not isinstance(it, dict):
                continue
            raw_lat = it.get("location_lat") if it.get("location_lat") is not None else it.get("lat")
            raw_lng = it.get("location_lng") if it.get("location_lng") is not None else it.get("lng")
            try:
                if raw_lat is not None and raw_lng is not None:
                    lat_f, lng_f = float(raw_lat), float(raw_lng)
                    if -90.0 <= lat_f <= 90.0 and -180.0 <= lng_f <= 180.0 and (lat_f != 0.0 or lng_f != 0.0):
                        it_day = int(it.get("day_number") or 1)
                        if it_day == day_number:
                            same_day_coords.append((lat_f, lng_f))
                        else:
                            other_day_coords.append((abs(it_day - day_number), lat_f, lng_f))
            except (ValueError, TypeError):
                continue

        if same_day_coords:
            s_lats = sorted(c[0] for c in same_day_coords)
            s_lngs = sorted(c[1] for c in same_day_coords)
            anchor_lat = s_lats[len(s_lats) // 2]
            anchor_lng = s_lngs[len(s_lngs) // 2]
        elif other_day_coords:
            other_day_coords.sort(key=lambda x: x[0])
            anchor_lat = other_day_coords[0][1]
            anchor_lng = other_day_coords[0][2]

    # Tier 4: 行程標題/目的地提取與 0ms 城市錨點查表
    raw_dest_hint = str(trip_dict.get("destination") or "").strip()
    trip_title = str(trip_dict.get("title") or "").strip()
    if not region_name:
        region_name = (
            extract_region_for_search(raw_dest_hint)
            or raw_dest_hint
            or extract_region_for_search(trip_title)
            or trip_title
        )

    if region_name:
        city_hit = GLOBAL_CITY_ANCHORS.get(region_name) or GLOBAL_CITY_ANCHORS.get(region_name.lower())
        if city_hit:
            if anchor_lat is None or anchor_lng is None:
                anchor_lat = city_hit["lat"]
                anchor_lng = city_hit["lng"]
            inferred_country = city_hit.get("country")

    if not inferred_country:
        inferred_country = (
            detect_country_from_keywords(region_name)
            or detect_country_from_keywords(raw_dest_hint)
            or detect_country_from_keywords(trip_title)
        )

    # 若為全球未知城市且無既有座標，承接原 ai.py Step 1/Step 2 透過 smart_geocode_logic (含快取、Photon、Nominatim 備援與國碼推斷) 動態解析中心點
    if (anchor_lat is None or anchor_lng is None) and region_name:
        try:
            dest_geo = await smart_geocode_logic(query=region_name, limit=1, country=inferred_country)
            if dest_geo and dest_geo.get("results"):
                first_dest = dest_geo["results"][0]
                anchor_lat = first_dest.get("lat")
                anchor_lng = first_dest.get("lng")
                inferred_country = first_dest.get("country") or inferred_country
        except Exception:
            try:
                photon_anchor = await geocode_with_photon(region_name, limit=1, country_code=inferred_country)
                if photon_anchor and len(photon_anchor) > 0:
                    anchor_lat = photon_anchor[0].get("lat")
                    anchor_lng = photon_anchor[0].get("lng")
            except Exception:
                pass

    # 若座標已知但尚未確定國家，優先以最近城市錨點與最小面積國界反推所在國別
    if anchor_lat is not None and anchor_lng is not None and not inferred_country:
        inferred_country = infer_country_from_coords(anchor_lat, anchor_lng)

    bbox = None
    if anchor_lat is not None and anchor_lng is not None:
        min_lng = max(-180.0, anchor_lng - 0.8)
        min_lat = max(-90.0, anchor_lat - 0.8)
        max_lng = min(180.0, anchor_lng + 0.8)
        max_lat = min(90.0, anchor_lat + 0.8)
        bbox = f"{min_lng:.5f},{min_lat:.5f},{max_lng:.5f},{max_lat:.5f}"

    return {
        "lat": anchor_lat,
        "lng": anchor_lng,
        "region": region_name,
        "country": inferred_country,
        "bbox": bbox,
        "trip_title": trip_title,
        "segments": day_segments,
    }


def extract_all_regions_from_text(text: str) -> List[str]:
    """
    從自由文本、Markdown 標題或 Wizard XML (<destination>...</destination>) 中提取所有提及的目的地城市與區域。
    支援單一城市（如 '台北 3 日遊' -> ['台北']）與跨城市行程（如 '東京、京都、大阪 6 日遊' -> ['東京', '京都', '大阪']）。
    """
    if not text:
        return []
    raw = str(text).strip()
    raw_truncated = raw[:1000]
    m_xml = re.search(r"<destination>([^<]{1,200})</destination>", raw_truncated, flags=re.IGNORECASE | re.DOTALL)
    target_segment = m_xml.group(1).strip() if m_xml else raw_truncated[:500]
    seg_lower = target_segment.lower()

    city_state_keys = {"新加坡", "singapore", "香港", "hong kong"}
    country_only_names = (
        {k.lower() for k in COUNTRY_NAME_TO_CODE.keys()}
        | {k.lower() for k in GLOBAL_COUNTRY_TO_ISO.keys()}
    ) - city_state_keys

    city_candidates = list(GLOBAL_CITY_ANCHORS.keys())
    for kws in LOCATION_KEYWORDS.values():
        city_candidates.extend(k for k in kws if k.lower() not in country_only_names)

    found_with_pos = []
    seen_coords = set()
    for kw in sorted(set(city_candidates), key=len, reverse=True):
        kw_low = kw.lower()
        pos = -1
        matched_str = ""
        if kw_low.isascii():
            if len(kw_low) < 3:
                continue
            m = re.search(r"\b" + re.escape(kw_low) + r"\b", seg_lower)
            if m:
                pos = m.start()
                matched_str = target_segment[m.start():m.end()]
        else:
            if len(kw_low) >= 2 and kw_low in seg_lower:
                pos = seg_lower.find(kw_low)
                matched_str = target_segment[pos:pos + len(kw)]
        if pos >= 0 and matched_str:
            anchor_info = GLOBAL_CITY_ANCHORS.get(matched_str) or GLOBAL_CITY_ANCHORS.get(matched_str.lower())
            dedup_key = (round(anchor_info["lat"], 2), round(anchor_info["lng"], 2)) if anchor_info else matched_str.lower()
            if dedup_key not in seen_coords:
                seen_coords.add(dedup_key)
                found_with_pos.append((pos, matched_str))

    found_with_pos.sort(key=lambda x: x[0])
    regions = [r for _, r in found_with_pos]
    if not regions:
        single = extract_region_for_search(target_segment)
        if single:
            regions = [single]
    return regions


async def resolve_prompt_spatial_anchor(
    text: str = "",
    trip: Optional[Dict[str, Any]] = None,
    existing_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    🌍 事前空間錨點解析器 (Pre-Generation Spatial Anchor Resolver)：
    支援現有行程物件、Wizard XML <destination>、自由輸入 Prompt 與 Markdown 文本。
    """
    if isinstance(trip, dict) and (trip.get("id") or trip.get("title") or trip.get("content")):
        base = await resolve_trip_spatial_anchor(trip, day_number=1, existing_items=existing_items)
        regions = [base["region"]] if base.get("region") else []
        combined_title_text = f"{trip.get('title') or ''} {trip.get('destination') or ''} {text or ''}".strip()
        for extracted_r in extract_all_regions_from_text(combined_title_text):
            if extracted_r and extracted_r not in regions:
                regions.append(extracted_r)
        content = trip.get("content") if isinstance(trip.get("content"), dict) else {}
        daily_locs = content.get("daily_locations") if isinstance(content.get("daily_locations"), dict) else {}
        for dl in daily_locs.values():
            if isinstance(dl, dict):
                if dl.get("name") and dl["name"] not in regions:
                    regions.append(str(dl["name"]))
                for seg in (dl.get("segments") or []):
                    if isinstance(seg, dict) and seg.get("name") and seg["name"] not in regions:
                        regions.append(str(seg["name"]))
        city_anchors = []
        seen_ca_names = set()
        for r in regions:
            hit = GLOBAL_CITY_ANCHORS.get(r) or GLOBAL_CITY_ANCHORS.get(r.lower())
            if hit and r not in seen_ca_names:
                seen_ca_names.add(r)
                city_anchors.append({"name": r, "lat": hit["lat"], "lng": hit["lng"], "country": hit.get("country")})
        for dl in daily_locs.values():
            if isinstance(dl, dict):
                for seg in (dl.get("segments") or []):
                    if isinstance(seg, dict) and seg.get("name") and seg.get("lat") is not None and seg.get("lng") is not None:
                        sname = str(seg["name"]).strip()
                        if sname and sname not in seen_ca_names:
                            try:
                                slat, slng = float(seg["lat"]), float(seg["lng"])
                                seen_ca_names.add(sname)
                                city_anchors.append({"name": sname, "lat": slat, "lng": slng, "country": base.get("country")})
                            except (ValueError, TypeError):
                                pass
        if not city_anchors and base.get("lat") is not None and base.get("lng") is not None:
            city_anchors.append({"name": base.get("region") or "", "lat": base["lat"], "lng": base["lng"], "country": base.get("country")})
        return {**base, "regions": regions, "city_anchors": city_anchors}

    regions = extract_all_regions_from_text(text)
    primary_region = regions[0] if regions else ""
    city_anchors = []
    for r in regions:
        hit = GLOBAL_CITY_ANCHORS.get(r) or GLOBAL_CITY_ANCHORS.get(r.lower())
        if hit:
            city_anchors.append({"name": r, "lat": hit["lat"], "lng": hit["lng"], "country": hit.get("country")})

    if primary_region:
        try:
            base = await asyncio.wait_for(
                resolve_trip_spatial_anchor({"title": primary_region}, day_number=1, existing_items=existing_items),
                timeout=1.5,
            )
        except Exception:
            base = {"lat": None, "lng": None, "region": primary_region, "country": detect_country_from_keywords(primary_region), "bbox": None, "trip_title": primary_region}
    else:
        inferred_cc = detect_country_from_keywords(text[:300]) if text else None
        base = {"lat": None, "lng": None, "region": "", "country": inferred_cc, "bbox": None, "trip_title": ""}

    if not base.get("country") and text:
        base["country"] = detect_country_from_keywords(text[:300])
    if not city_anchors and base.get("lat") is not None and base.get("lng") is not None:
        city_anchors.append({"name": base.get("region") or primary_region, "lat": base["lat"], "lng": base["lng"], "country": base.get("country")})

    return {**base, "regions": regions, "city_anchors": city_anchors}


def build_spatial_constraint_prompt(anchor: Optional[Dict[str, Any]]) -> str:
    """
    將事前解析出的空間錨點轉換為注入 Gemini System Instruction 的 <spatial_anchor_constraint> 強制規範區塊。
    """
    anc = anchor or {}
    regions = anc.get("regions") or ([anc["region"]] if anc.get("region") else [])
    country = anc.get("country")
    lat = anc.get("lat")
    lng = anc.get("lng")
    c_bounds = COUNTRY_BOUNDS.get(country) if country else None

    if len(regions) <= 1 and lat is not None and lng is not None:
        min_lat, max_lat = max(-90.0, lat - 0.8), min(90.0, lat + 0.8)
        min_lng, max_lng = max(-180.0, lng - 0.8), min(180.0, lng + 0.8)
        bounds_desc = (
            f"目標城市中心錨點為 ({lat:.4f}, {lng:.4f})，所有景點之 (lat, lng) 必須嚴格落於緯度 [{min_lat:.4f}, {max_lat:.4f}]、經度 [{min_lng:.4f}, {max_lng:.4f}] 範圍內"
        )
    elif c_bounds:
        city_Hints = ", ".join(
            f"{ca['name']}({ca['lat']:.4f},{ca['lng']:.4f})"
            for ca in (anc.get("city_anchors") or [])
            if ca.get("lat") is not None and ca.get("lng") is not None
        )
        bounds_desc = (
            f"國界經緯度範圍為緯度 [{c_bounds['lat_min']:.4f}, {c_bounds['lat_max']:.4f}]、經度 [{c_bounds['lng_min']:.4f}, {c_bounds['lng_max']:.4f}]"
            + (f"；各城市中心參考錨點：{city_Hints}" if city_Hints else "")
        )
    else:
        bounds_desc = (
            "請先由輸入內容識別目標國家與城市並填入頂層 `destination` 欄位，並在內部鎖定該城市的實際地理邊界後再輸出各景點座標"
        )

    region_label = "、".join(regions) if regions else "依輸入內容自動識別並鎖定之目標城市"
    return (
        f"\n### 📍 事前空間錨定強制約束 (<spatial_anchor_constraint>):\n"
        f"1. **目標區域與國別**: {region_label} (Country ISO: {country or 'AUTO'})。\n"
        f"2. **空間座標邊界約束**: {bounds_desc}。\n"
        f"3. **同名地標強制消歧義**: 凡遇全球或跨城撞名地標（如「龍山寺」、「東照宮」、「中國城」、「故宮」），`place_name` 必須自動冠上所在城市或行政區前綴（例如在台北行程輸出「台北 艋舺龍山寺」），且其 (`lat`, `lng`) 必須嚴格位於該日所在城市邊界內，絕對禁止套用其他國家或城市的同名座標！\n"
        f"4. **跨城與跨海轉場走廊規範 (Transit Corridor Rule)**: 若單日內包含跨城市高鐵/新幹線、長途火車、國內線航班或跨海渡輪移動，該交通項目必須標記 `category: \"transit\"`，且轉場前後之景點必須分別採用「出發城市」與「抵達城市」之真實座標，嚴禁將不同城市的景點壓縮至同一座標中心！\n"
    )


GLOBAL_TRANSIT_SPLIT_KEYWORDS = (
    "新幹線", "高鐵", "高速鐵路", "飛往", "搭機", "航班", "國內線", "國際線",
    "渡輪", "搭船", "快艇", "特急", "成田特快", "はるか", "haruka", "nex",
    "shinkansen", "bullet train", "high-speed rail", "eurostar", "tgv",
    "thalys", "ice train", "frecciarossa", "ave train", "ktx",
    "flight to", "fly to", "ferry to", "airport", "機場", "空港",
)
TRANSIT_SPLIT_CATEGORIES = {
    "transit", "transport", "transportation", "flight", "train", "ferry", "high_speed_rail",
}


def _is_transit_splitter_item(item: Dict[str, Any]) -> bool:
    """判斷行程項目是否為跨城/跨海轉場交通橋接節點 (ReDoS-Free 常數時間檢測)。"""
    if not isinstance(item, dict):
        return False
    cat = str(item.get("category") or "").strip().lower()
    if cat in TRANSIT_SPLIT_CATEGORIES:
        return True
    combined = (
        f"{item.get('place_name') or ''} "
        f"{item.get('original_name') or ''} "
        f"{item.get('notes') or ''} "
        f"{item.get('desc') or ''}"
    ).lower()
    return any(kw in combined for kw in GLOBAL_TRANSIT_SPLIT_KEYWORDS)


def _resolve_segment_region_name(
    seg_lat: float,
    seg_lng: float,
    rep_names: List[str],
    known_city_anchors: List[Dict[str, Any]],
    default_region: str,
    default_country: Optional[str],
) -> tuple[str, Optional[str]]:
    """
    🌍 全球無字典動態走廊子群命名器 (Invariant 3 - Zero-Dictionary Dynamic Segment Naming)
    優先級：
      1. known_city_anchors (行程標題/Prompt/既有走廊已知城市 <= 60km)
      2. GLOBAL_CITY_ANCHORS (優先非 ASCII 中文名，次選英文名 <= 60km)
      3. LANDMARKS_DB (30km 內知名地標所屬城市或地標名稱)
      4. 子群代表性景點詞元共現分析與 extract_region_for_search 動態提取 (支援秘魯 Lima -> Cusco 等冷門城市)
    """
    for ca in known_city_anchors:
        if ca.get("lat") is not None and ca.get("lng") is not None:
            if haversine_km(ca["lat"], ca["lng"], seg_lat, seg_lng) <= 60.0 and ca.get("name"):
                return str(ca["name"]), ca.get("country") or default_country

    best_city_name = ""
    best_city_country = default_country
    best_dist = 60.0
    for cname, cinfo in GLOBAL_CITY_ANCHORS.items():
        if cname.isascii():
            continue
        dist = haversine_km(cinfo["lat"], cinfo["lng"], seg_lat, seg_lng)
        if dist <= best_dist:
            best_dist = dist
            best_city_name = cname
            best_city_country = cinfo.get("country") or default_country
    if best_city_name:
        return best_city_name, best_city_country

    for cname, cinfo in GLOBAL_CITY_ANCHORS.items():
        dist = haversine_km(cinfo["lat"], cinfo["lng"], seg_lat, seg_lng)
        if dist <= best_dist:
            best_dist = dist
            best_city_name = cname.title()
            best_city_country = cinfo.get("country") or default_country
    if best_city_name:
        return best_city_name, best_city_country

    # 3. LANDMARKS_DB (30km 內知名地標所屬城市或地標名稱)
    best_lm_name = ""
    best_lm_country = default_country
    best_lm_dist = 30.0
    for lm_key, lm_info in LANDMARKS_DB.items():
        if not isinstance(lm_info, dict) or lm_info.get("lat") is None or lm_info.get("lng") is None:
            continue
        lm_country = lm_info.get("country")
        if default_country and lm_country and lm_country.upper() != default_country.upper():
            continue
        dist = haversine_km(lm_info["lat"], lm_info["lng"], seg_lat, seg_lng)
        if dist <= best_lm_dist:
            best_lm_dist = dist
            best_lm_name = extract_region_for_search(lm_info.get("display") or lm_key) or lm_info.get("display") or lm_key
            best_lm_country = lm_country or default_country
    if best_lm_name:
        return best_lm_name, best_lm_country

    # 從子群代表性景點名稱中提取共同城市詞元 (例如 ['Lima Plaza Mayor', 'Lima Miraflores'] -> 'Lima')
    clean_reps = [str(r).strip() for r in rep_names if str(r).strip()]
    if clean_reps:
        token_counts: Dict[str, int] = {}
        stop_words = {
            "plaza", "park", "hotel", "station", "airport", "temple", "shrine",
            "museum", "market", "tower", "castle", "bridge", "beach", "old", "street",
            "the", "of", "de", "la", "el", "in", "at", "to", "and",
        }
        for rname in clean_reps:
            extracted = extract_region_for_search(rname)
            if extracted and extracted in GLOBAL_CITY_ANCHORS:
                return extracted, default_country
            words = re.findall(r"[A-Za-z\u4e00-\u9fff]{2,}", rname)
            seen_in_item = set()
            for w in words:
                wl = w.lower()
                if wl not in stop_words and wl not in seen_in_item:
                    seen_in_item.add(wl)
                    token_counts[w] = token_counts.get(w, 0) + 1
        if token_counts:
            best_token = max(token_counts.items(), key=lambda kv: (kv[1], len(kv[0])))[0]
            if token_counts[best_token] >= 2 or len(clean_reps) == 1:
                return best_token, default_country
        first_extracted = extract_region_for_search(clean_reps[0])
        if first_extracted:
            return first_extracted, default_country
        return clean_reps[0][:12], default_country

    return default_region, default_country


_JP_KANA_NON_NO_RE = re.compile(r"[\u3040-\u306D\u306F-\u309F\u30A0-\u30FF]")
_KR_HANGUL_RE = re.compile(r"[\uAC00-\uD7AF]")
_TH_SCRIPT_RE = re.compile(r"[\u0E00-\u0E7F]")
_AMBIGUOUS_FOREIGN_CLUE_KEYWORDS = frozenset({
    "101", "nice", "central", "東北", "樂天", "lotte", "故宮", "海洋公園", "自由女神",
})
_DISH_FOLLOW_CHARS = frozenset({"燒", "烧", "麵", "面"})
_NAME_CLEAN_SEP_RE = re.compile(r"[\s\-—–_・·/(),（）【】\[\]]+")
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_LATIN_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")


def _has_non_dish_cjk(combined_norm: str, term: str) -> bool:
    term_norm = normalize_cjk_chars(term)
    if not term_norm:
        return False
    idx = combined_norm.find(term_norm)
    while idx != -1:
        after_idx = idx + len(term_norm)
        if after_idx >= len(combined_norm) or combined_norm[after_idx] not in _DISH_FOLLOW_CHARS:
            return True
        idx = combined_norm.find(term_norm, after_idx)
    return False


def _infer_countries_from_text(combined: str) -> set[str]:
    if not combined:
        return set()
    inferred: set[str] = set()
    # 排除華語店家常見之單獨裝飾字「の」（如「茶の魔手」），僅其他日文假名直接推論為 JP
    if _JP_KANA_NON_NO_RE.search(combined):
        inferred.add("JP")
    if _KR_HANGUL_RE.search(combined):
        inferred.add("KR")
    if _TH_SCRIPT_RE.search(combined):
        inferred.add("TH")

    combined_low = combined.lower()
    combined_norm = normalize_cjk_chars(combined)

    for k, info in GLOBAL_CITY_ANCHORS.items():
        cc = str(info.get("country") or "").upper()
        if not cc or cc in inferred:
            continue
        if k.isascii():
            if len(k) >= 4 and re.search(rf"\b{re.escape(k.lower())}\b", combined_low):
                inferred.add(cc)
        elif len(k) >= 2 and _has_non_dish_cjk(combined_norm, k):
            inferred.add(cc)

    for cc, kws in LOCATION_KEYWORDS.items():
        if cc in inferred:
            continue
        for kw in kws:
            kw_low = kw.lower()
            if kw_low in _AMBIGUOUS_FOREIGN_CLUE_KEYWORDS:
                continue
            if kw.isascii():
                if len(kw_low) >= 4 and re.search(rf"\b{re.escape(kw_low)}\b", combined_low):
                    inferred.add(cc)
                    break
            elif len(kw) >= 2 and _has_non_dish_cjk(combined_norm, kw):
                inferred.add(cc)
                break

    for cc, b in COUNTRY_BOUNDS.items():
        if cc in inferred:
            continue
        cname = str(b.get("name") or "").strip()
        if len(cname) >= 2 and _has_non_dish_cjk(combined_norm, cname):
            inferred.add(cc)

    return inferred


def _infer_city_anchors_from_text(combined: str) -> List[Dict[str, Any]]:
    if not combined:
        return []
    combined_low = combined.lower()
    combined_norm = normalize_cjk_chars(combined)
    matched: List[Dict[str, Any]] = []
    seen_coords: set[tuple[float, float]] = set()
    for k, info in GLOBAL_CITY_ANCHORS.items():
        if info.get("lat") is None or info.get("lng") is None:
            continue
        hit = False
        if k.isascii():
            if len(k) >= 4 and re.search(rf"\b{re.escape(k.lower())}\b", combined_low):
                hit = True
        elif len(k) >= 2 and _has_non_dish_cjk(combined_norm, k):
            hit = True
        if hit:
            key = (round(float(info["lat"]), 3), round(float(info["lng"]), 3))
            if key not in seen_coords:
                seen_coords.add(key)
                matched.append(info)
    return matched


def _item_text_by_fields(item: Dict[str, Any], fields: tuple[str, ...]) -> str:
    if not isinstance(item, dict):
        return ""
    parts = [str(item.get(field) or "").strip() for field in fields]
    return " ".join(p for p in parts if p)


def infer_explicit_countries_from_item(item: Dict[str, Any]) -> set[str]:
    """從單筆項目的名稱、原文名、地址與備註推論明確提及的國家代碼（含語系線索與非料理城市關鍵字）。"""
    combined = _item_text_by_fields(item, ("place_name", "original_name", "address", "notes", "desc"))
    return _infer_countries_from_text(combined)


def is_self_consistent_foreign_place(
    item: Dict[str, Any],
    lat: float,
    lng: float,
    allowed_countries: Optional[set[str]] = None,
) -> bool:
    """驗證項目文字中明確推論之國家與傳入座標是否自洽（同時攔截文字與當地國家/主地址矛盾之幻覺）。"""
    all_countries = infer_explicit_countries_from_item(item)
    if not all_countries:
        return False

    def _in_bounds(cc: str) -> bool:
        bounds = COUNTRY_BOUNDS.get(cc)
        return bool(
            bounds
            and (bounds["lat_min"] <= lat <= bounds["lat_max"])
            and (bounds["lng_min"] <= lng <= bounds["lng_max"])
        )

    # 1. 若項目文字本身已明確提及母體行程所在國家（如台北分店/地址），但座標落在該國境外 -> 視為幻覺矛盾，拒絕放行
    if allowed_countries and (all_countries & allowed_countries):
        if not any(_in_bounds(cc) for cc in allowed_countries):
            return False

    # 2. 若主要定位欄位（店名/原文名/地址）已明確指向特定國家，座標必須落於其中（避免『台北龍山寺』備註提首爾卻放行首爾座標）
    primary_text = _item_text_by_fields(item, ("place_name", "original_name", "address"))
    primary_countries = _infer_countries_from_text(primary_text)
    if primary_countries and not any(_in_bounds(cc) for cc in primary_countries):
        return False

    return any(_in_bounds(cc) for cc in all_countries)


def is_self_consistent_explicit_city_place(
    item: Dict[str, Any],
    lat: float,
    lng: float,
    anchor_lat: Optional[float] = None,
    anchor_lng: Optional[float] = None,
) -> bool:
    """同國跨城自洽驗證（如東京行程加入備註明寫『大阪』且座標落於大阪 80km 內之餐廳），同時攔截與當日城市矛盾之幻覺。"""
    all_text = _item_text_by_fields(item, ("place_name", "original_name", "address", "notes", "desc"))
    all_cities = _infer_city_anchors_from_text(all_text)
    if not all_cities:
        return False

    # 若文字同時明確提及當日錨點城市（如東京分店備註提大阪風味），座標遠離當日錨點屬矛盾幻覺
    if anchor_lat is not None and anchor_lng is not None:
        if any(haversine_km(anchor_lat, anchor_lng, c["lat"], c["lng"]) <= 80.0 for c in all_cities):
            return False

    primary_text = _item_text_by_fields(item, ("place_name", "original_name", "address"))
    primary_cities = _infer_city_anchors_from_text(primary_text)
    if primary_cities and not any(haversine_km(c["lat"], c["lng"], lat, lng) <= 80.0 for c in primary_cities):
        return False

    return any(haversine_km(c["lat"], c["lng"], lat, lng) <= 80.0 for c in all_cities)


def _is_weak_out_of_country_match(place_name: str, match_name: str) -> bool:
    """防止跨國自癒時因極短子字串誤撞（如『北海』vs『北海 -HOKKAI- お初天神店』）而覆蓋有效原座標。"""
    q_norm = normalize_cjk_chars(place_name or "")
    m_norm = normalize_cjk_chars(match_name or "")
    q_clean = _NAME_CLEAN_SEP_RE.sub("", q_norm)
    m_clean = _NAME_CLEAN_SEP_RE.sub("", m_norm)
    if not q_clean or not m_clean:
        return False
    if q_clean in m_clean:
        return False

    q_cjk = set(_CJK_CHAR_RE.findall(q_clean))
    m_cjk = set(_CJK_CHAR_RE.findall(m_clean))
    # 必須在剝除空白與分隔符號前切分拉丁詞彙，避免多詞英文地名被黏合成單一 token 誤殺有效匹配
    q_lat = set(_LATIN_TOKEN_RE.findall(q_norm))
    m_lat = set(_LATIN_TOKEN_RE.findall(m_norm))

    if q_cjk and m_cjk:
        q_units = len(q_cjk) + len(q_lat)
        shared_units = len(q_cjk & m_cjk) + len(q_lat & m_lat)
        return (shared_units / max(1, q_units)) < 0.45

    if not q_cjk and not m_cjk and q_lat and m_lat:
        return (len(q_lat & m_lat) / max(1, len(q_lat))) < 0.45

    return False


async def verify_and_heal_itinerary_coords(
    items: List[Dict[str, Any]],
    trip_meta: Optional[Dict[str, Any]] = None,
    pre_anchor: Optional[Dict[str, Any]] = None,
    existing_items: Optional[List[Dict[str, Any]]] = None,
) -> tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """
    🛡️ 事後逐日空間錨點校驗與非破壞性自癒引擎 (Post-Generation Spatial Guard & Non-Destructive Healer)
    - 支援單一城市與跨城市/跨國多日行程（自動推算並回傳 daily_locations）
    - 保留真實 Google Maps URL 直解座標 (_url_verified) 與合法範圍內的 AI 座標（0 額外請求）
    - 自動攔截跨國越界、撞名地標漂移 (> 50km) 與跨區離群 (> 180km) 幻覺座標
    - 非破壞性兜底：若 OSM 查無結果或超時，跨國/撞名幻覺座標自動退回當日城市中心錨點，絕不留錯誤座標或 None
    """
    meta = trip_meta if isinstance(trip_meta, dict) else {}
    raw_dest = str(meta.get("destination") or meta.get("title") or "").strip()
    post_anchor = await resolve_prompt_spatial_anchor(
        raw_dest,
        trip=meta if (meta.get("id") or meta.get("content")) else None,
        existing_items=existing_items,
    )

    base_anchor = post_anchor if (post_anchor.get("lat") is not None or post_anchor.get("country")) else (pre_anchor or post_anchor)
    if pre_anchor and pre_anchor.get("lat") is not None and post_anchor.get("lat") is None:
        base_anchor = pre_anchor

    target_country = base_anchor.get("country") or (pre_anchor or {}).get("country")

    known_city_anchors: List[Dict[str, Any]] = []
    seen_names = set()
    for src in (pre_anchor or {}, post_anchor or {}):
        for ca in (src.get("city_anchors") or []):
            if ca.get("name") and ca["name"] not in seen_names and ca.get("lat") is not None:
                seen_names.add(ca["name"])
                known_city_anchors.append(ca)

    allowed_countries = {
        cc
        for cc in ([target_country, (pre_anchor or {}).get("country"), (post_anchor or {}).get("country")] + [ca.get("country") for ca in known_city_anchors])
        if cc
    }
    allowed_bounds = [COUNTRY_BOUNDS[cc] for cc in allowed_countries if cc in COUNTRY_BOUNDS]

    def _extract_coord(obj: Dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
        rlat = obj.get("lat") if obj.get("lat") is not None else obj.get("location_lat")
        rlng = obj.get("lng") if obj.get("lng") is not None else obj.get("location_lng")
        try:
            if rlat is not None and rlng is not None and str(rlat).strip().lower() not in ("none", "null", "n/a", ""):
                f_lat, f_lng = float(rlat), float(rlng)
                if -90.0 <= f_lat <= 90.0 and -180.0 <= f_lng <= 180.0 and (f_lat != 0.0 or f_lng != 0.0) and not math.isnan(f_lat) and not math.isnan(f_lng):
                    return f_lat, f_lng
        except (ValueError, TypeError):
            pass
        return None, None

    def _in_country(lat_v: float, lng_v: float) -> bool:
        if not allowed_bounds:
            return True
        return any(
            (b["lat_min"] <= lat_v <= b["lat_max"]) and (b["lng_min"] <= lng_v <= b["lng_max"])
            for b in allowed_bounds
        )

    HOMONYM_GUARD_KEYS = (
    "龍山寺", "東照宮", "中國城", "中華街", "故宮", "天后宮", "媽祖廟", "文武廟",
    "迪士尼", "迪士尼樂園", "disney", "disneyland",
    "環球影城", "universal studios",
    "自由女神像", "自由女神", "海洋公園",
)

    def _in_country_or_border(lat_v: float, lng_v: float, is_homonym: bool = False) -> bool:
        if _in_country(lat_v, lng_v):
            return True
        if (
            not is_homonym
            and base_anchor.get("lat") is not None
            and base_anchor.get("lng") is not None
            and haversine_km(base_anchor["lat"], base_anchor["lng"], lat_v, lng_v) <= 80.0
        ):
            return True
        return False

    content = meta.get("content") if isinstance(meta.get("content"), dict) else {}
    raw_daily_locs = meta.get("daily_locations") or content.get("daily_locations") or {}
    daily_locations: Dict[str, Dict[str, Any]] = {}
    if isinstance(raw_daily_locs, dict):
        for k, v in raw_daily_locs.items():
            if isinstance(v, dict):
                dl_lat, dl_lng = _extract_coord(v)
                dl_name = str(v.get("name") or "")
                is_dl_homonym = any(hk in dl_name for hk in HOMONYM_GUARD_KEYS)
                if dl_lat is not None and dl_lng is not None and _in_country_or_border(dl_lat, dl_lng, is_homonym=is_dl_homonym):
                    daily_locations[str(k)] = dict(v)

    # Step A: 建立每一天的動態空間錨點 day_anchors 與時序走廊子群 item_segment_map
    ACTION_NOISE_KEYWORDS = ("集合", "搭乘", "休息", "抵達", "出發", "退稅", "check-in", "check-out")
    all_days = sorted({int(it.get("day_number") or it.get("day") or 1) for it in items if isinstance(it, dict)} or {1})
    day_anchors: Dict[int, Dict[str, Any]] = {}
    item_segment_map: Dict[int, Dict[str, Any]] = {}

    def _make_bbox(lat_v: float, lng_v: float) -> str:
        min_lng, min_lat = max(-180.0, lng_v - 0.8), max(-90.0, lat_v - 0.8)
        max_lng, max_lat = min(180.0, lng_v + 0.8), min(90.0, lat_v + 0.8)
        return f"{min_lng:.5f},{min_lat:.5f},{max_lng:.5f},{max_lat:.5f}"

    for d_num in all_days:
        d_key = str(d_num)
        explicit_dl = daily_locations.get(d_key)
        if isinstance(explicit_dl, dict):
            dl_lat, dl_lng = _extract_coord(explicit_dl)
            dl_name = str(explicit_dl.get("name") or "")
            is_dl_homonym = any(hk in dl_name for hk in HOMONYM_GUARD_KEYS)
            if dl_lat is not None and dl_lng is not None and _in_country_or_border(dl_lat, dl_lng, is_homonym=is_dl_homonym):
                parsed_segs: List[Dict[str, Any]] = []
                raw_segs = explicit_dl.get("segments")
                if isinstance(raw_segs, list):
                    for seg in raw_segs:
                        if isinstance(seg, dict):
                            slat, slng = _extract_coord(seg)
                            sname = str(seg.get("name") or "").strip()
                            is_s_homonym = any(hk in sname for hk in HOMONYM_GUARD_KEYS)
                            if slat is not None and slng is not None and _in_country_or_border(slat, slng, is_homonym=is_s_homonym):
                                parsed_segs.append({
                                    "lat": slat,
                                    "lng": slng,
                                    "region": sname or str(explicit_dl.get("name") or base_anchor.get("region") or ""),
                                    "country": target_country,
                                    "bbox": _make_bbox(slat, slng),
                                })
                day_anchors[d_num] = {
                    "lat": dl_lat,
                    "lng": dl_lng,
                    "region": str(explicit_dl.get("name") or base_anchor.get("region") or ""),
                    "country": target_country,
                    "bbox": _make_bbox(dl_lat, dl_lng),
                    "segments": parsed_segs,
                }
                continue
            else:
                daily_locations.pop(d_key, None)

        # 收集當日既有項目與新項目中位於目標國境內的座標
        existing_day_coords = []
        for ex in (existing_items or []):
            if isinstance(ex, dict) and int(ex.get("day_number") or 1) == d_num:
                elat, elng = _extract_coord(ex)
                if elat is not None and elng is not None and _in_country(elat, elng):
                    existing_day_coords.append((elat, elng))

        day_items = [
            it for it in items
            if isinstance(it, dict) and int(it.get("day_number") or it.get("day") or 1) == d_num
        ]
        has_day_transit = any(_is_transit_splitter_item(it) for it in day_items)

        # Step A.1: 預掃描當日所有國境內合法點，計算局部群聚密度支撐 (Invariant 1: MinPts >= 2)
        in_country_records = []
        for idx_i, it in enumerate(day_items):
            ilat, ilng = _extract_coord(it)
            pname = str(it.get("place_name") or it.get("original_name") or "").strip()
            is_transit = _is_transit_splitter_item(it)
            is_noise = (not is_transit) and any(noise in pname.lower() for noise in ACTION_NOISE_KEYWORDS)
            is_homonym = any(hk in pname for hk in HOMONYM_GUARD_KEYS)
            if ilat is not None and ilng is not None and not is_noise and _in_country(ilat, ilng):
                in_country_records.append((idx_i, ilat, ilng, is_homonym, is_transit, pname))

        trusted_item_coords: Dict[int, tuple[float, float, str]] = {}
        for idx_i, ilat, ilng, is_homonym, is_transit, pname in in_country_records:
            peers = [
                (olat, olng, ohom)
                for _, olat, olng, ohom, _, _ in in_country_records
                if haversine_km(ilat, ilng, olat, olng) <= 60.0
            ]
            non_homonym_peers = sum(1 for _, _, ohom in peers if not ohom)
            has_local_density = len(peers) >= 2 and non_homonym_peers >= 1
            matches_known_city = any(
                haversine_km(ca["lat"], ca["lng"], ilat, ilng) <= 60.0
                for ca in known_city_anchors
                if ca.get("lat") is not None and ca.get("lng") is not None
            )

            # Invariant 1 防幻覺分裂與離群過濾：
            # 若單一城市錨點已明確存在，僅當具備局部多點密度 (MinPts>=2) 或顯式轉場走廊時，才豁免 >50km/180km 單點過濾
            if len(known_city_anchors) == 1 and base_anchor.get("lat") is not None:
                dist_base = haversine_km(base_anchor["lat"], base_anchor["lng"], ilat, ilng)
                if is_homonym and dist_base > 50.0 and not has_local_density:
                    continue
                if dist_base > 180.0 and not (has_local_density or has_day_transit):
                    continue
            trusted_item_coords[idx_i] = (ilat, ilng, pname)

        # Step A.2: 時序多段分割 ($K$-Partitioning)
        raw_segments: List[Dict[str, Any]] = [{"item_objs": [], "coords": [], "rep_names": []}]
        for idx_i, it in enumerate(day_items):
            is_transit = _is_transit_splitter_item(it)
            t_coord = trusted_item_coords.get(idx_i)
            curr_seg = raw_segments[-1]

            if t_coord is not None and curr_seg["coords"]:
                ilat, ilng, pname = t_coord
                s_lats = sorted(c[0] for c in curr_seg["coords"])
                s_lngs = sorted(c[1] for c in curr_seg["coords"])
                seg_med_lat = s_lats[len(s_lats) // 2]
                seg_med_lng = s_lngs[len(s_lngs) // 2]
                jump_km = haversine_km(seg_med_lat, seg_med_lng, ilat, ilng)

                # Invariant 1: 距離跳躍 > 80km 且該新位置已通過 trusted_item_coords 支撐檢驗 -> 觸發子群切分
                if jump_km > 80.0:
                    curr_seg = {"item_objs": [], "coords": [], "rep_names": []}
                    raw_segments.append(curr_seg)

            curr_seg["item_objs"].append(it)
            if t_coord is not None:
                curr_seg["coords"].append((t_coord[0], t_coord[1]))
                if not is_transit:
                    curr_seg["rep_names"].append(t_coord[2])

        # Step A.3: 計算各子群獨立中位數錨點與無字典動態命名 (Invariant 3)
        built_segments: List[Dict[str, Any]] = []
        for seg in raw_segments:
            seg_pool = seg["coords"] if seg["coords"] else existing_day_coords
            if not seg_pool:
                continue
            s_lats = sorted(c[0] for c in seg_pool)
            s_lngs = sorted(c[1] for c in seg_pool)
            med_lat = s_lats[len(s_lats) // 2]
            med_lng = s_lngs[len(s_lngs) // 2]
            seg_region, seg_country = _resolve_segment_region_name(
                med_lat,
                med_lng,
                seg["rep_names"],
                known_city_anchors,
                base_anchor.get("region") or raw_dest or "",
                target_country,
            )
            seg_anchor_dict = {
                "lat": med_lat,
                "lng": med_lng,
                "region": seg_region,
                "country": seg_country or target_country,
                "bbox": _make_bbox(med_lat, med_lng),
                "item_objs": seg["item_objs"],
            }
            built_segments.append(seg_anchor_dict)

        if len(built_segments) >= 2:
            for seg_anc in built_segments:
                for it_obj in seg_anc["item_objs"]:
                    item_segment_map[id(it_obj)] = seg_anc

            # 預設主錨點取當日最終抵達城市 (向後相容舊前端地圖居中)
            primary_seg = built_segments[-1]
            d_lat, d_lng = primary_seg["lat"], primary_seg["lng"]
            d_country = primary_seg["country"]
            dedup_names: List[str] = []
            for s in built_segments:
                sname = s["region"] or raw_dest or "中心區域"
                if not dedup_names or dedup_names[-1] != sname:
                    dedup_names.append(sname)
            corridor_label = " → ".join(dedup_names) if len(dedup_names) >= 2 else (dedup_names[0] if dedup_names else "中心區域")
            d_region = corridor_label
            bbox_str = _make_bbox(d_lat, d_lng)

            if d_key not in daily_locations:
                daily_locations[d_key] = {
                    "name": corridor_label,
                    "lat": round(d_lat, 4),
                    "lng": round(d_lng, 4),
                    "type": "transit_corridor",
                    "segments": [
                        {
                            "name": s["region"] or raw_dest or "中心區域",
                            "lat": round(s["lat"], 4),
                            "lng": round(s["lng"], 4),
                        }
                        for s in built_segments
                    ],
                }
            day_anchors[d_num] = {
                "lat": d_lat,
                "lng": d_lng,
                "region": d_region,
                "country": d_country,
                "bbox": bbox_str,
                "segments": built_segments,
            }
        else:
            candidate_day_coords = [(c[0], c[1]) for c in trusted_item_coords.values()]
            pool = existing_day_coords if existing_day_coords else candidate_day_coords
            d_lat, d_lng = base_anchor.get("lat"), base_anchor.get("lng")
            d_region = base_anchor.get("region") or ""
            d_country = target_country

            if pool:
                s_lats = sorted(c[0] for c in pool)
                s_lngs = sorted(c[1] for c in pool)
                med_lat = s_lats[len(s_lats) // 2]
                med_lng = s_lngs[len(s_lngs) // 2]
                matched_city = None
                for ca in known_city_anchors:
                    if haversine_km(ca["lat"], ca["lng"], med_lat, med_lng) <= 80.0:
                        matched_city = ca
                        break
                if matched_city:
                    d_lat, d_lng = med_lat, med_lng
                    d_region = matched_city["name"]
                    if matched_city.get("country"):
                        d_country = matched_city["country"]
                elif len(pool) >= 2 or d_lat is None:
                    d_lat, d_lng = med_lat, med_lng
                    for cname, cinfo in GLOBAL_CITY_ANCHORS.items():
                        if cname.isascii():
                            continue
                        if haversine_km(cinfo["lat"], cinfo["lng"], d_lat, d_lng) <= 60.0:
                            d_region = cname
                            if cinfo.get("country"):
                                d_country = cinfo["country"]
                            break

            bbox_str = _make_bbox(d_lat, d_lng) if (d_lat is not None and d_lng is not None) else None
            if d_lat is not None and d_lng is not None and d_key not in daily_locations:
                daily_locations[d_key] = {
                    "name": d_region or raw_dest or "中心區域",
                    "lat": round(d_lat, 4),
                    "lng": round(d_lng, 4),
                    "type": "stay",
                }

            day_anchors[d_num] = {
                "lat": d_lat,
                "lng": d_lng,
                "region": d_region,
                "country": d_country,
                "bbox": bbox_str,
                "segments": built_segments,
            }

    # Step B & C: 逐項座標驗證與非破壞性自癒（節流至 Semaphore(3) 並關閉全國 Overpass 掃描以保護公用圖資）
    sem = asyncio.Semaphore(3)

    async def _verify_and_heal_single(item: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(item, dict):
            return item
        if item.pop("_url_verified", False):
            return item

        d_num = int(item.get("day_number") or item.get("day") or 1)
        day_anc_root = day_anchors.get(d_num) or base_anchor
        d_segs = day_anc_root.get("segments") or []
        ilat, ilng = _extract_coord(item)

        # Invariant 4: 優先取時序子群錨點；若為二次讀取之走廊日，依現有座標匹配最近之合法 segment 錨點
        d_anc = item_segment_map.get(id(item))
        if d_anc is None:
            if len(d_segs) >= 2 and ilat is not None and ilng is not None:
                d_anc = min(
                    d_segs,
                    key=lambda s: haversine_km(s["lat"], s["lng"], ilat, ilng)
                    if (s.get("lat") is not None and s.get("lng") is not None)
                    else float("inf"),
                )
            elif len(d_segs) == 1:
                d_anc = d_segs[0]
            else:
                d_anc = day_anc_root

        has_location_keys = ("location_lat" in item or "location_lng" in item) and ("lat" not in item)

        def _set_coords(new_lat: Optional[float], new_lng: Optional[float]) -> None:
            if has_location_keys:
                item["location_lat"] = new_lat
                item["location_lng"] = new_lng
            else:
                item["lat"] = new_lat
                item["lng"] = new_lng
                if "location_lat" in item:
                    item["location_lat"] = new_lat
                if "location_lng" in item:
                    item["location_lng"] = new_lng

        place_name = str(item.get("place_name") or item.get("original_name") or "").strip()
        is_transit_item = _is_transit_splitter_item(item)

        # Invariant 2: 交通橋接節點 vs 純動作雜訊精準分流
        if not place_name or (not is_transit_item and any(noise in place_name.lower() for noise in ACTION_NOISE_KEYWORDS)):
            if ilat is None or ilng is None or not _in_country(ilat, ilng):
                _set_coords(None, None)
            elif d_anc.get("lat") is not None and d_anc.get("lng") is not None and haversine_km(d_anc["lat"], d_anc["lng"], ilat, ilng) > 180.0:
                _set_coords(None, None)
            return item

        place_name_low = place_name.lower()
        is_homonym_place = any(hk.lower() in place_name_low for hk in HOMONYM_GUARD_KEYS)
        reason = None
        if ilat is None or ilng is None:
            reason = "missing"
        elif not _in_country(ilat, ilng):
            # 允許邊境城市當日跨境順遊 (如日內瓦->霞慕尼 64km、新加坡->新山 18km)，
            # 以及文字與外國座標自洽的非撞名跨區景點（如大阪日文店名 + 日本邊界座標），
            # 同時嚴格攔截跨國幻覺與撞名地標（如台北行程中的首爾龍山寺、或文字提及台北但帶日本座標之矛盾點）
            if not is_homonym_place and (
                (
                    d_anc.get("lat") is not None
                    and d_anc.get("lng") is not None
                    and haversine_km(d_anc["lat"], d_anc["lng"], ilat, ilng) <= 80.0
                )
                or is_self_consistent_foreign_place(
                    item,
                    ilat,
                    ilng,
                    allowed_countries=allowed_countries,
                )
            ):
                reason = None
            else:
                reason = "out_of_country"
        elif d_anc.get("lat") is not None and d_anc.get("lng") is not None:
            dist_day = haversine_km(d_anc["lat"], d_anc["lng"], ilat, ilng)
            min_dist_city = min(
                [dist_day]
                + [
                    haversine_km(ca["lat"], ca["lng"], ilat, ilng)
                    for ca in known_city_anchors
                    if ca.get("lat") is not None and ca.get("lng") is not None
                ]
                + [
                    haversine_km(s["lat"], s["lng"], ilat, ilng)
                    for s in d_segs
                    if s.get("lat") is not None and s.get("lng") is not None
                ]
            )
            if is_homonym_place and dist_day > 50.0:
                reason = "homonym_drift"
            elif min_dist_city > 180.0 and not (
                not is_homonym_place
                and is_self_consistent_explicit_city_place(
                    item,
                    ilat,
                    ilng,
                    anchor_lat=d_anc.get("lat"),
                    anchor_lng=d_anc.get("lng"),
                )
            ):
                reason = "spatial_outlier"

        if reason is None:
            _set_coords(ilat, ilng)
            return item

        healed_lat, healed_lng = None, None
        rejected_weak_match = False
        async with sem:
            try:
                geo_res = await asyncio.wait_for(
                    smart_geocode_logic(
                        query=place_name,
                        limit=1,
                        trip_title=str(meta.get("title") or raw_dest or ""),
                        region=d_anc.get("region"),
                        lat=d_anc.get("lat"),
                        lng=d_anc.get("lng"),
                        country=d_anc.get("country"),
                        bbox=d_anc.get("bbox"),
                        allow_overpass=False,
                    ),
                    timeout=2.5,
                )
                if geo_res and geo_res.get("results"):
                    first_match = geo_res["results"][0]
                    match_name = str(first_match.get("name") or first_match.get("display_name") or "").strip()
                    if (
                        reason == "out_of_country"
                        and not is_homonym_place
                        and ilat is not None
                        and ilng is not None
                        and match_name
                        and _is_weak_out_of_country_match(place_name, match_name)
                    ):
                        rejected_weak_match = True
                    else:
                        healed_lat = first_match.get("lat")
                        healed_lng = first_match.get("lng")
            except Exception as e:
                print(f"⚠️ [Spatial Healer] Geocode fallback for '{place_name}' ({reason}): {e}")

        if healed_lat is not None and healed_lng is not None:
            _set_coords(healed_lat, healed_lng)
        elif rejected_weak_match and ilat is not None and ilng is not None:
            # 防止模糊子字串誤撞（如「北海」誤撞大阪店名）覆寫原有效座標
            _set_coords(ilat, ilng)
        elif (
            reason in ("out_of_country", "homonym_drift", "spatial_outlier")
            or (reason == "missing" and is_transit_item)
        ) and d_anc.get("lat") is not None and d_anc.get("lng") is not None:
            # 非破壞性兜底：當確認原座標為跨國/撞名幻覺，或為無座標之跨城交通橋接節點 (Invariant 2)，退回所屬子群中心錨點
            _set_coords(d_anc["lat"], d_anc["lng"])
        else:
            _set_coords(ilat, ilng)

        return item

    healed_items = await asyncio.gather(*[_verify_and_heal_single(it) for it in items])
    return list(healed_items), daily_locations


_EXPLICIT_ADMIN_SUFFIX_RE = re.compile(r"^[\u4e00-\u9fff]{2,5}[市縣省州都道府]$")


def _detect_explicit_city_anchor(query: str) -> Optional[tuple[str, Dict[str, Any]]]:
    """識別查詢是否為純城市／行政區（例如『台中』、『台中市』、『台南』、『慕尼黑』、『Barcelona』），排除餐飲/POI 詞彙。"""
    clean_q = (query or "").strip()
    if not clean_q:
        return None
    q_low = clean_q.lower()
    # 先直接比對 GLOBAL_CITY_ANCHORS（含剝除「市/縣/都/府」後比對），確保『Barcelona』『函館』不被誤判為 POI
    norm_q = normalize_cjk_chars(clean_q)
    candidates_to_check = [clean_q, q_low, norm_q]
    if len(clean_q) >= 3 and clean_q[-1] in ("市", "縣", "都", "府", "省", "州"):
        base = clean_q[:-1]
        candidates_to_check.extend([base, base.lower(), normalize_cjk_chars(base)])
    for cand in candidates_to_check:
        hit = GLOBAL_CITY_ANCHORS.get(cand)
        if hit:
            return cand, hit
    if _has_poi_or_food_intent(clean_q):
        return None
    if _EXPLICIT_ADMIN_SUFFIX_RE.match(clean_q):
        return clean_q, {"country": None}
    return None


def _is_exact_landmark_match(query: str, landmark_data: Optional[dict], display_name: Optional[str]) -> bool:
    """檢查查詢是否與地標主鍵、顯示名、搜尋名或任一別名達『純字元正規化全詞精確匹配』（防止 >80km 子字串誤觸秒回）。"""
    if not query or not landmark_data:
        return False
    norm_q = normalize_cjk_chars(query)
    if not norm_q:
        return False
    exact_pool = set()
    for field in (display_name, landmark_data.get("display"), landmark_data.get("search")):
        if field:
            exact_pool.add(normalize_cjk_chars(str(field)))
    for alias in (landmark_data.get("aliases") or []):
        if alias:
            exact_pool.add(normalize_cjk_chars(str(alias)))
    for lm_key, lm_val in LANDMARKS_DB.items():
        if lm_val is landmark_data:
            exact_pool.add(normalize_cjk_chars(lm_key))
            break
    return norm_q in exact_pool


def _extract_nominatim_result(item: dict) -> dict:
    """將 Nominatim 回傳單筆資料標準化（補齊 addresstype 層級、admin_level、RFC 7946 extent 與 osm_id）。"""
    addr = item.get("address") if isinstance(item.get("address"), dict) else {}
    extratags = item.get("extratags") if isinstance(item.get("extratags"), dict) else {}
    raw_addresstype = str(item.get("addresstype") or "").strip().lower()
    raw_type = str(item.get("type") or "place").strip().lower()
    raw_class = str(item.get("class") or "").strip().lower()

    if raw_addresstype in ("country", "state", "province", "city", "county", "municipality", "town", "district", "suburb"):
        mapped_type = raw_addresstype
    elif raw_class == "boundary" and raw_type == "administrative":
        mapped_type = raw_addresstype or "administrative"
    else:
        mapped_type = raw_type or "place"

    admin_lvl_raw = extratags.get("admin_level")
    admin_level: Optional[int] = int(admin_lvl_raw) if str(admin_lvl_raw).isdigit() else None
    if admin_level is None:
        place_rank = item.get("place_rank")
        if mapped_type == "country" or place_rank == 4:
            admin_level = 2
        elif mapped_type in ("state", "province") or place_rank == 8:
            admin_level = 4
        elif mapped_type in ("city", "county", "municipality") or place_rank in (12, 16):
            admin_level = 6

    imp = item.get("importance")
    norm_extent = normalize_extent(item.get("boundingbox"), source_format="nominatim")
    city_val = addr.get("city") or addr.get("town") or addr.get("municipality") or addr.get("county")

    return {
        "lat": float(item["lat"]),
        "lng": float(item["lon"]),
        "name": item.get("name") or item.get("display_name", "").split(",")[0],
        "display_name": item.get("display_name", ""),
        "address": item.get("display_name", ""),
        "type": mapped_type,
        "osm_key": raw_class or None,
        "osm_id": item.get("osm_id"),
        "osm_type": item.get("osm_type"),
        "city": city_val,
        "state": addr.get("state"),
        "country": addr.get("country"),
        "admin_level": admin_level,
        "extent": norm_extent,
        "importance": float(imp) if imp is not None else None,
        "source": "nominatim",
    }


async def smart_geocode_logic(
    query: str,
    limit: Optional[int] = None,
    trip_title: Optional[str] = None,
    api_key: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    country: Optional[str] = None,    # 🆕 前端傳入的國家過濾
    region: Optional[str] = None,     # 🆕 前端傳入的區域過濾
    zoom: Optional[float] = None,     # 🆕 P1: 地圖縮放層級 (用於動態 bias)
    bbox: Optional[str] = None,       # 🆕 P2: 地圖視窗邊界 (minLon,minLat,maxLon,maxLat)
    allow_overpass: bool = True,      # 🆕 批次行程自癒時關閉全國 Overpass 掃描
    _allow_paren_fallback: bool = True,  # 🛡️ 括號/前綴長標題單次降級守衛（保護舊版 SW 用戶且防無窮遞迴）
) -> dict:
    clean_query = (query or "").strip()[:500]
    if not clean_query:
        return {"results": [], "source": "none"}

    # limit=None 或 <=0：上游單次安全抓取上限 25，去重與智慧排序後「有多少筆顯示多少筆」；
    # limit=1 等小量查詢至少抓 15 筆候選池供 rerank_top_k 擇優，再依 return_limit 切片遵守向下相容契約。
    return_limit: Optional[int] = min(int(limit), 50) if (limit is not None and int(limit) > 0) else None
    upstream_limit: int = min(max(return_limit * 5, 15), 50) if return_limit is not None else 25

    log_debug(f"🌍 [SmartGeo] 啟動多層檢索: '{clean_query}' (Trip: {trip_title or '無'}, limit={return_limit or 'ALL'}, 偏置: {lat},{lng})")
    log_debug(f"🔍 [SmartGeo] Start search: '{clean_query}' (Trip: {trip_title}, Country: {country}, Region: {region}, Zoom: {zoom}, Bias: {lat},{lng})")
    
    # 🧠 Step 0: 智能國家判斷和翻譯（優先序：前端顯式 country > 查詢純國名 > 查詢地名關鍵字 > 地圖中心座標 > tripTitle/region）
    country_code = None
    api_country_lock = None # 🆕 只有明確指定時才物理鎖死 API
    search_queries = [clean_query]
    chinese_display = None  # 🆕 中文顯示名稱
    
    # 🆕 第零優先級：前端明確指定的國家 (最高優先，大小寫不敏感，支援 2 位 ISO 與全名)
    if country:
        c_upper = country.strip().upper()
        if c_upper in COUNTRY_BOUNDS or c_upper in _ISO_TO_ZH_NAME or c_upper in _ISO_TO_EN_NAME:
            country_code = c_upper
        else:
            normalized_country = country.strip().lower()
            country_code = next((v.upper() for k, v in COUNTRY_TO_ISO.items() if k.lower() == normalized_country), None)
        if country_code:
            api_country_lock = country_code
            log_debug(f"   🎯 Frontend Country Filter (Lock) → {country_code}")
    
    # 🆕 0.1 優先級：偵測搜尋詞本身是否就是國家名（明確導向）
    user_explicit_country = False
    norm_query = clean_query.lower()
    found_explicit_code = next((v.upper() for k, v in COUNTRY_TO_ISO.items() if k.lower() == norm_query), None)
    if found_explicit_code:
        country_code = found_explicit_code
        user_explicit_country = True
        api_country_lock = country_code
        log_debug(f"   🌍 Explicit Country Query Detected (Lock) → {country_code}")

    # 🆕 0.2 優先級：識別純城市／行政區查詢（例如「台中」、「台南」、「慕尼黑」、「巴塞隆納」）
    explicit_city_hit = None if user_explicit_country else _detect_explicit_city_anchor(clean_query)
    is_explicit_city = explicit_city_hit is not None
    explicit_city_cc = (explicit_city_hit[1].get("country") or "").upper() if explicit_city_hit else ""
    explicit_city_is_admin_region = bool(explicit_city_hit and explicit_city_hit[1].get("is_admin_region"))
    explicit_city_en = (
        _get_city_anchor_english_name(explicit_city_hit[1])
        if (explicit_city_hit and explicit_city_cc not in ("TW", "CN", "HK", "MO"))
        else None
    )
    explicit_city_coords: Optional[tuple[float, float]] = (
        (float(explicit_city_hit[1]["lat"]), float(explicit_city_hit[1]["lng"]))
        if (explicit_city_hit and explicit_city_hit[1].get("lat") is not None and explicit_city_hit[1].get("lng") is not None)
        else None
    )

    # 座標所在國（用於餐飲消歧義如「大阪燒」與歐美鏡頭跨語系翻譯）
    coord_country = infer_country_from_coords(lat, lng)
    has_poi_or_food_tail = False if (user_explicit_country or is_explicit_city) else _has_poi_or_food_intent(clean_query)

    # 第一優先級：查詢關鍵字 / 已知全球城市前綴 ➔ 地圖中心座標 (lat, lng) ➔ 行程標題 / 目標區域
    if not country_code:
        if explicit_city_cc:
            country_code = explicit_city_cc
        else:
            kw_country = detect_country_from_keywords(clean_query) or _detect_country_from_city_prefix(clean_query)
            # 若查詢為在地美食料理詞（例如台北搜「大阪燒」、「廣島燒」、「台南担仔麵」）且地圖座標已定位，優先以當前地圖所在國為軟提示
            if kw_country and has_poi_or_food_tail and coord_country and kw_country != coord_country:
                # 排除明確跨國交通/市政/地標詞（如「東京車站」、「東京鐵塔」、「慕尼黑市政廳」、「赫爾辛基中央車站」、「巴塞隆納聖家堂」）
                is_specific_landmark_or_transit = any(
                    m in norm_query
                    for m in (
                        "車站", "駅", "機場", "空港", "鐵塔", "塔", "寺", "神社", "教堂", "聖家堂",
                        "市政廳", "市政府", "歌劇院", "博物館", "美術館", "皇宮", "王宮", "城堡",
                        "老城區", "舊城區", "廣場", "競技場", "羅浮宮", "迪士尼", "環球影城",
                        "castle", "tower", "station", "airport", "city hall", "rathaus", "opera", "cathedral", "museum", "palace",
                    )
                )
                country_code = kw_country if is_specific_landmark_or_transit else coord_country
            elif kw_country:
                country_code = kw_country
            elif coord_country:
                country_code = coord_country
                log_debug(f"   📍 Coordinate Country Inference → {country_code}")
            elif trip_title:
                country_code = detect_country_from_keywords(trip_title)
            if not country_code and region:
                country_code = detect_country_from_keywords(region)
        if country_code:
            log_debug(f"   🔑 Resolved Country Hint → {country_code}")

    # 第二優先級：AI 判斷（僅當座標與關鍵字皆無法推斷且有 API Key 時，嚴格受 1.2s 超時保護）
    if not country_code and api_key and not _INCOMPLETE_ZHUYIN_RE.search(clean_query):
        log_debug("   🚀 Parallelizing AI country detection...")
        ai_tasks = []
        if trip_title:
            ai_tasks.append(detect_country_from_trip_title(trip_title, api_key))
        ai_tasks.append(detect_country_from_query(clean_query, api_key))
        try:
            ai_results = await asyncio.wait_for(
                asyncio.gather(*ai_tasks, return_exceptions=True),
                timeout=1.2,
            )
            res_list = [r for r in ai_results if isinstance(r, str) and r]
            if res_list:
                country_code = res_list[0]
                log_debug(f"   🧠 Detected Country (Parallel): {country_code}")
        except asyncio.TimeoutError:
            log_debug("   ⏱️ AI country detection timed out (1.2s), proceeding without lock")

    # 🆕 Step 1.1: 快速路徑 - 如果查詢是坐標，直接跳過所有 AI 邏輯
    if "," in clean_query:
        parts = clean_query.split(",")
        if len(parts) == 2:
            try:
                lat_val, lng_val = float(parts[0]), float(parts[1])
                if math.isfinite(lat_val) and math.isfinite(lng_val) and -90.0 <= lat_val <= 90.0 and -180.0 <= lng_val <= 180.0:
                    log_debug(f"   ⚡ FAST PATH: Coordinates detected ({lat_val}, {lng_val})")
                    return {"results": [{
                        "lat": lat_val, "lng": lng_val, "name": clean_query, "display_name": clean_query, "address": clean_query, "type": "coordinate", "source": "direct"
                    }], "source": "direct"}
            except Exception:
                pass

    # 🆕 Step 1.2: 城市/次區/地標前綴空間錨點切換（例如台北搜『慕尼黑市政廳』『台南龍山寺』『新宿一蘭拉麵』『東京迪士尼飯店』）
    # 同時萃取僅供 rerank_top_k 使用的母語設施單詞（如 Rathaus / City Hall），維持 _translate_via_micro_dict 契約不變
    effective_bias_lat: Optional[float] = lat
    effective_bias_lng: Optional[float] = lng
    city_prefix_switched = False
    city_prefix_key: Optional[str] = None
    is_subdistrict_anchor = False
    rerank_extra_variants: List[str] = []
    if not user_explicit_country and not is_explicit_city:
        city_prefix_hit = _detect_city_prefix_anchor(clean_query)
        if city_prefix_hit:
            city_prefix_key, prefix_info, prefix_suffix = city_prefix_hit
            effective_bias_lat = float(prefix_info["lat"])
            effective_bias_lng = float(prefix_info["lng"])
            city_prefix_switched = True
            is_subdistrict_anchor = bool(
                prefix_info.get("is_subdistrict")
                or city_prefix_key in _SUBDISTRICT_ANCHORS
                or city_prefix_key.lower() in _SUBDISTRICT_ANCHORS
            )
            target_for_fac = country_code or prefix_info.get("country")
            rerank_extra_variants = _get_facility_standalone_terms(prefix_suffix, target_for_fac)
            log_debug(
                f"   🧭 City-Prefix Anchor Switch → ({effective_bias_lat:.4f}, {effective_bias_lng:.4f}), "
                f"subdistrict={is_subdistrict_anchor}, rerank_extra={rerank_extra_variants}"
            )

    cleaned_paren_query = _extract_clean_place_query(clean_query) if _allow_paren_fallback else clean_query
    has_paren_or_prefix_noise = bool(
        _allow_paren_fallback
        and cleaned_paren_query
        and cleaned_paren_query != clean_query
        and len(cleaned_paren_query) >= 2
    )

    # 🆕 Step 1.3: 確定性著名景點翻譯（全詞精確匹配閘門 + 主鍵優先於別名 + 連鎖品牌零覆寫 + 撞名地標安全網）
    if user_explicit_country or is_explicit_city:
        search_terms, display_name, landmark_data = ([clean_query], None, None)
    else:
        landmark_result = translate_famous_landmark(clean_query, country_code, strict_country=bool(api_country_lock))
        search_terms, display_name, landmark_data = landmark_result
    
    # 🚀 INSTANT RETURN: 全距離強制 _is_exact_landmark_match 且排除連鎖品牌；
    # 僅在明確鎖國 (api_country_lock) 或跨國撞名地標 (HOMONYM_GUARD_KEYS) 時比對目標國別，
    # 避免台北地圖座標軟推斷 (coord_country='TW') 誤封『晴空塔』『關西機場』『明治神宮』『白川鄉』等 290+ 無歧義精確地標。
    norm_clean_q = normalize_cjk_chars(clean_query)
    is_exact_lm = _is_exact_landmark_match(clean_query, landmark_data, display_name)
    is_chain_brand = _is_chain_brand_entry(clean_query, landmark_data, display_name)
    is_bare_homonym = norm_clean_q in _HOMONYM_GUARD_NORM
    landmark_country = (landmark_data.get("country") or "").upper() if landmark_data else ""
    country_matches = True
    if api_country_lock and landmark_country:
        country_matches = (landmark_country == api_country_lock.upper())
    elif is_bare_homonym and country_code and landmark_country:
        country_matches = (landmark_country == country_code.upper())
    lm_dist_km: Optional[float] = (
        haversine_km(lat, lng, landmark_data["lat"], landmark_data["lng"])
        if (landmark_data and landmark_data.get("lat") is not None and landmark_data.get("lng") is not None and lat is not None and lng is not None)
        else None
    )

    can_instant_return = bool(
        landmark_data
        and landmark_data.get("lat") is not None
        and landmark_data.get("lng") is not None
        and country_matches
        and is_exact_lm
        and not is_chain_brand
    )
    landmark_blocked_by_homonym = False
    if can_instant_return and is_bare_homonym:
        if lat is None or lng is None or (lm_dist_km is not None and lm_dist_km > 80.0):
            can_instant_return = False
            landmark_blocked_by_homonym = True
            display_name = None
            landmark_data = None
            search_terms = [clean_query]
    elif landmark_data and not can_instant_return:
        if is_bare_homonym and (lat is None or lng is None or (lm_dist_km is not None and lm_dist_km > 80.0)):
            landmark_blocked_by_homonym = True
            display_name = None
            landmark_data = None
            search_terms = [clean_query]
        elif not is_exact_lm or is_chain_brand or not country_matches:
            display_name = None
            landmark_data = None
            search_terms = [clean_query]

    if can_instant_return and landmark_data:
        lm_addr = f"{landmark_data.get('display', display_name)}, {landmark_data.get('country', '')}"
        instant_result = {
            "lat": landmark_data["lat"],
            "lng": landmark_data["lng"],
            "name": landmark_data.get("display", display_name),
            "display_name": lm_addr,
            "address": lm_addr,
            "type": "landmark",
            "source": "landmarks_db",
            "original_name": clean_query
        }
        log_debug(f"   ⚡ INSTANT RETURN: {display_name} ({landmark_data['lat']}, {landmark_data['lng']})")
        return {"results": [instant_result], "source": "landmarks_db"}

    # ⚡ 括號備註／時間前綴精確地標直達（如『淺草寺 (雷門拍照)』『晴空塔（夜景拍照）』『10:00 築地市場（海鮮早餐）』）：
    # 若清洗後純地名命中無歧義非連鎖 LANDMARKS_DB，立即 0ms 秒回，杜絕 5s 尾延遲與 Nominatim 誤配『晴空之阁』。
    if has_paren_or_prefix_noise and not user_explicit_country and not is_explicit_city:
        p_norm = normalize_cjk_chars(cleaned_paren_query)
        if p_norm and p_norm not in _HOMONYM_GUARD_NORM:
            _, p_disp, p_lm = translate_famous_landmark(
                cleaned_paren_query, country_code, strict_country=bool(api_country_lock)
            )
            p_lm_cc = (p_lm.get("country") or "").upper() if p_lm else ""
            p_cc_ok = (not api_country_lock) or (not p_lm_cc) or (p_lm_cc == api_country_lock.upper())
            if (
                p_lm
                and p_lm.get("lat") is not None
                and p_lm.get("lng") is not None
                and p_cc_ok
                and _is_exact_landmark_match(cleaned_paren_query, p_lm, p_disp)
                and not _is_chain_brand_entry(cleaned_paren_query, p_lm, p_disp)
            ):
                lm_addr = f"{p_lm.get('display', p_disp)}, {p_lm.get('country', '')}"
                instant_result = {
                    "lat": p_lm["lat"],
                    "lng": p_lm["lng"],
                    "name": p_lm.get("display", p_disp),
                    "display_name": lm_addr,
                    "address": lm_addr,
                    "type": "landmark",
                    "source": "landmarks_db",
                    "original_name": clean_query,
                }
                log_debug(f"   ⚡ PAREN-CLEAN INSTANT RETURN: '{clean_query}' -> {p_disp} ({p_lm['lat']}, {p_lm['lng']})")
                return {"results": [instant_result], "source": "landmarks_db"}
    
    # 🆕 Step 2: 投機性並行搜尋 (Speculative Parallelism)
    region_term = extract_region_for_search(region or trip_title) if (region or trip_title) else ""

    # 判斷是否為跨城／跨國／離題行程標題，決定是否抑制 region_term 前綴與硬 bbox
    region_conflicts_with_target = False
    if user_explicit_country or is_explicit_city:
        if not region_term or normalize_cjk_chars(region_term) != normalize_cjk_chars(clean_query):
            region_conflicts_with_target = True
    if city_prefix_switched and effective_bias_lat is not None and effective_bias_lng is not None:
        if lat is None or lng is None or haversine_km(lat, lng, effective_bias_lat, effective_bias_lng) > 30.0:
            region_conflicts_with_target = True
    reg_anchor = None
    if region_term and not region_conflicts_with_target:
        reg_anchor = (
            GLOBAL_CITY_ANCHORS.get(region_term)
            or GLOBAL_CITY_ANCHORS.get(region_term.lower())
            or _SUBDISTRICT_ANCHORS.get(region_term)
            or _SUBDISTRICT_ANCHORS.get(region_term.lower())
        )
        reg_cc = (reg_anchor.get("country") if reg_anchor else detect_country_from_keywords(region_term)) or ""
        if reg_cc and country_code and reg_cc.upper() != country_code.upper():
            region_conflicts_with_target = True
        elif reg_anchor and effective_bias_lat is not None and effective_bias_lng is not None:
            if haversine_km(effective_bias_lat, effective_bias_lng, reg_anchor["lat"], reg_anchor["lng"]) > 150.0:
                region_conflicts_with_target = True
        elif reg_anchor and effective_bias_lat is None and effective_bias_lng is None and not user_explicit_country and not is_explicit_city:
            # 無顯式座標但行程標題／區域具已知城市錨點（如 tripTitle='大阪五日遊' 搜 '大阪燒' 或 InfoView 搜首間飯店）➔ 注入城市座標偏置
            effective_bias_lat = float(reg_anchor["lat"])
            effective_bias_lng = float(reg_anchor["lng"])
            log_debug(f"   🧭 Trip/Region Anchor Bias → '{region_term}' ({effective_bias_lat:.4f}, {effective_bias_lng:.4f})")

    search_queries = []
    chinese_display = None
    
    tasks = []
    # 任務 A: 三層極速翻譯（有 Key 走 Flash-Lite 1.8s，無 Key 走 0ms 微字典 + 1.2s Wikipedia langlinks；
    # 已知城市錨點已有 0ms 英文名或含括號備註雜訊之初次原詞不浪費外部 Wiki 逾時）
    translation_task = None
    has_cjk_local_micro = bool(
        not display_name
        and country_code
        and country_code.upper() in ("TW", "CN", "HK", "MO")
        and _HAS_CJK_RE.search(clean_query)
        and clean_query in ("市政廳", "迪士尼", "迪士尼樂園", "環球影城")
    )
    needs_free_translation = bool(
        not display_name
        and country_code
        and not user_explicit_country
        and not explicit_city_en
        and not has_paren_or_prefix_noise
        and _HAS_CJK_RE.search(clean_query)
        and (country_code.upper() not in ("TW", "CN", "HK", "MO") or has_cjk_local_micro)
    )
    if (not display_name and country_code and not user_explicit_country and api_key and not has_paren_or_prefix_noise) or needs_free_translation:
        translation_task = asyncio.create_task(
            translate_place_name(clean_query, country_code, api_key, lat=effective_bias_lat, lng=effective_bias_lng)
        )
        tasks.append(translation_task)
    
    # 任務 B: 原始名稱初步搜尋 (Speculative Photon)
    effective_bbox = None if (user_explicit_country or is_explicit_city or region_conflicts_with_target) else bbox
    use_region_prefix = bool(region_term and not region_conflicts_with_target and region_term.lower() not in norm_query)
    speculative_query = f"{region_term} {clean_query}".strip() if use_region_prefix else clean_query
    speculative_lat = None if (user_explicit_country or is_explicit_city) else effective_bias_lat
    speculative_lng = None if (user_explicit_country or is_explicit_city) else effective_bias_lng
    if user_explicit_country or is_explicit_city:
        speculative_zoom = None
    elif is_subdistrict_anchor and (zoom is None or float(zoom) > 10.0):
        speculative_zoom = 15.0
    elif city_prefix_switched and region_conflicts_with_target:
        speculative_zoom = 12.0
    else:
        speculative_zoom = zoom

    speculative_task = asyncio.create_task(
        geocode_with_photon(
            speculative_query,
            upstream_limit,
            speculative_lat,
            speculative_lng,
            speculative_zoom,
            country_code=api_country_lock,
            bbox=effective_bbox,
        )
    )
    tasks.append(speculative_task)
    
    # 🆕 任務 C: 全域觀察者任務 (Global Observer — 明確國名或跨城純城市查詢不帶 bbox/偏置，防止在地店家排擠宏觀實體)
    global_task = None
    global_q_sent: Optional[str] = None
    if user_explicit_country:
        global_q = get_country_english_name(country_code) or clean_query
        global_osm_tag = None if (country_code and country_code.upper() in _OSM_SAR_CODES) else "place:country"
        if global_osm_tag is not None or global_q.lower() != speculative_query.lower():
            global_q_sent = global_q
            global_task = asyncio.create_task(
                geocode_with_photon(
                    global_q,
                    upstream_limit,
                    None,
                    None,
                    None,
                    location_bias_scale=None,
                    osm_tag=global_osm_tag,
                    country_code=api_country_lock,
                    bbox=None,
                )
            )
            tasks.append(global_task)
    elif is_explicit_city:
        # 跨城宏觀召回：日本城市若具日文新字體變體（如 沖繩->沖縄、那霸->那覇、橫濱->横浜、輕井澤->軽井沢）優先採日文漢字精準召回；
        # 否則以 0ms 城市錨點英文名（如 巴塞隆納->Barcelona、慕尼黑->Munich）或 CJK 異體字並行取回完整邊界與 extent；
        # 若無差異且 speculative_task 已採無偏置/無 bbox 查詢，避免對 Photon 發出重複雙打請求引發 503
        city_variants = expand_cjk_variants(clean_query)
        jp_city_var = _jp_kanji_variant(clean_query) if (country_code and country_code.upper() == "JP") else None
        if jp_city_var and jp_city_var.lower() != speculative_query.lower():
            macro_q = jp_city_var
        elif explicit_city_en and explicit_city_en.lower() != speculative_query.lower():
            macro_q = explicit_city_en
        else:
            macro_q = next((v for v in city_variants if v != clean_query), clean_query)
        if macro_q.lower() != speculative_query.lower():
            global_q_sent = macro_q
            global_task = asyncio.create_task(
                geocode_with_photon(
                    macro_q,
                    upstream_limit,
                    None,
                    None,
                    None,
                    location_bias_scale=None,
                    country_code=api_country_lock,
                    bbox=None,
                )
            )
            tasks.append(global_task)

    log_debug(f"   🚀 Starting Speculative Searches for '{clean_query}'...")
    await asyncio.gather(*tasks, return_exceptions=True)

    # 彙整搜尋關鍵字
    if display_name:
        search_queries = list(search_terms)
        chinese_display = display_name
    elif translation_task and not translation_task.cancelled() and not translation_task.exception():
        search_queries = list(translation_task.result() or [])
        log_debug(f"   🔤 Translated variants: {search_queries}")

    # 連鎖品牌子字串前綴保留搜尋詞（例如「新宿一蘭拉麵」->「新宿 一蘭 ラーメン」，display_name=None）仍應納入查詢變體
    if search_terms and not landmark_blocked_by_homonym:
        for st in search_terms:
            if st and st not in search_queries:
                if st != clean_query:
                    search_queries.insert(0, st)
                else:
                    search_queries.append(st)

    # 明確國名／已知城市查詢補充 0ms 英文權威名供 rerank 多變體評分（免依賴外部 Wikipedia 逾時）
    if user_explicit_country:
        en_country = get_country_english_name(country_code)
        if en_country and en_country not in search_queries:
            search_queries.insert(0, en_country)
    elif is_explicit_city and explicit_city_en and explicit_city_en not in search_queries:
        search_queries.insert(0, explicit_city_en)

    # 日本單語系乾淨漢字變體（如「東京車站」->「東京駅」獨立變體，不空白拼接）
    if country_code and country_code.upper() == "JP":
        jp_var = _jp_kanji_variant(clean_query)
        if jp_var and jp_var not in search_queries:
            search_queries.insert(0, jp_var)

    # 🆕 P1-B: 展開 CJK 異體字變體（如「台中一中」→「臺中一中」）加入搜尋
    for variant in expand_cjk_variants(clean_query):
        if variant not in search_queries:
            search_queries.append(variant)

    if not country_code:
        log_debug("   ⚠️ No country detected, using broad search")

    all_results = []
    found_source = "none"
    
    # 🆕 整合投機性搜尋結果（各批次獨立標記 _batch_rank 供 rerank_top_k 分源權威校正）
    # A. 全域觀察者結果 (優先級最高，因為這是明確的國土/城市座標)
    if global_task and not global_task.cancelled() and not global_task.exception():
        global_results = global_task.result()
        if global_results:
            for b_idx, r in enumerate(global_results):
                r["source"] = "photon_global"
                r["_batch_rank"] = b_idx
            all_results.extend(global_results)
            found_source = "photon"
            log_debug(f"   🌍 Found {len(global_results)} global entities")

    # B. 在地觀察者結果 (次之，包含附近同名店家)
    if speculative_task and not speculative_task.cancelled() and not speculative_task.exception():
        photon_spec = speculative_task.result()
        if photon_spec:
            for b_idx, r in enumerate(photon_spec):
                r["source"] = "photon_speculative"
                r["_batch_rank"] = b_idx
            all_results.extend(photon_spec)
            if found_source == "none":
                found_source = "photon"
            log_debug(f"   ⚡ Using {len(photon_spec)} speculative results")
    
    # 嚴格遵循 strict：僅於明確鎖國 (api_country_lock) 時才預先過濾境外結果；非鎖國一律保留跨國結果供智慧排序
    is_strict = bool(api_country_lock)
    if country_code and all_results and is_strict:
        pre_filtered = filter_results_by_country(all_results, country_code, strict=True)
        if len(pre_filtered) < len(all_results):
            log_debug(f"   🧹 Pre-filter: {len(all_results)} → {len(pre_filtered)} (strict=True)")
            all_results = pre_filtered

    # ⚡ 快速括號/前綴單次降級：含括號備註或時間前綴（如『淺草寺 (雷門拍照)』）且原詞快速 Photon 0 命中時，
    # 立即轉入清洗後純地名檢索，杜絕在雜訊原詞上空耗 Nominatim + Overpass (10s+) 撞穿前端 3.5s 存檔逾時！
    if has_paren_or_prefix_noise and not all_results:
        log_debug(f"   ⚡ Fast Parenthetical Fallback (single-pass): '{clean_query}' -> '{cleaned_paren_query}'")
        return await smart_geocode_logic(
            cleaned_paren_query,
            limit=limit,
            trip_title=trip_title,
            api_key=api_key,
            lat=lat,
            lng=lng,
            country=country,
            region=region,
            zoom=zoom,
            bbox=bbox,
            allow_overpass=allow_overpass,
            _allow_paren_fallback=False,
        )

    # 空間感知 Nominatim 短路評估：
    # - 明確國名：photon_global 或位於目標國邊界內之 country/admin_level=2 實體即為權威命中（支援母語名 Deutschland/Ísland/Österreich）
    # - 一般查詢：若已帶空間錨點 (lat, lng)，僅當已有「距離 <= 80km 且相似度 >= 0.85」之強在地命中，
    #   或「經跨語系翻譯且已於目標國內命中 >= 2 筆高相似度結果（如慕尼黑搜 89km 外新天鵝堡）」時才省去額外 Nominatim 請求；
    # - 嚴格確保 [PoC 4] 秘魯庫斯科搜 Plaza Mayor（無翻譯且馬德里誘餌不在秘魯境內）絕不被短路！
    had_cross_lang_translation = bool(
        any(q.strip().lower() != norm_query and q.isascii() != clean_query.isascii() for q in search_queries)
    )
    target_cc_bounds = COUNTRY_BOUNDS.get(country_code.upper()) if country_code else None
    q_has_non_latin = bool(_NON_LATIN_SCRIPT_RE.search(norm_query))

    def _in_target_cc(r: dict) -> bool:
        if not target_cc_bounds:
            return False
        r_lat, r_lng = r.get("lat"), r.get("lng")
        if r_lat is None or r_lng is None:
            return False
        return (
            target_cc_bounds["lat_min"] - 0.1 <= r_lat <= target_cc_bounds["lat_max"] + 0.1
            and target_cc_bounds["lng_min"] - 0.1 <= r_lng <= target_cc_bounds["lng_max"] + 0.1
        )

    def _has_strong_spatial_coverage(results_list: list) -> bool:
        if not results_list:
            return False
        if user_explicit_country:
            is_sar_cc = bool(country_code and country_code.upper() in _OSM_SAR_CODES)
            return any(
                (
                    (str(r.get("type") or "").lower() == "country" or r.get("admin_level") == 2)
                    or (is_sar_cc and (str(r.get("type") or "").lower() in ("state", "province", "city", "administrative") or r.get("admin_level") in (3, 4)) and _in_target_cc(r))
                )
                and (
                    str(r.get("source") or "").lower() == "photon_global"
                    or _in_target_cc(r)
                    or max((cjk_text_similarity(v, r.get("name", "")) for v in search_queries), default=0.0) >= 0.85
                )
                for r in results_list
            )
        if is_explicit_city:
            target_types = ("state", "province") if explicit_city_is_admin_region else ("city", "county", "municipality", "administrative", "town")
            return any(
                (str(r.get("type") or "").lower() in target_types or (not explicit_city_is_admin_region and isinstance(r.get("admin_level"), int) and r["admin_level"] <= 6))
                and (
                    max((cjk_text_similarity(v, r.get("name", "")) for v in search_queries), default=0.0) >= 0.85
                    or (
                        not explicit_city_is_admin_region
                        and explicit_city_coords is not None
                        and r.get("lat") is not None
                        and r.get("lng") is not None
                        and str(r.get("type") or "").lower() in ("city", "municipality", "town", "province")
                        and haversine_km(r["lat"], r["lng"], explicit_city_coords[0], explicit_city_coords[1]) <= 8.0
                    )
                )
                for r in results_list
            )
        if effective_bias_lat is not None and effective_bias_lng is not None:
            strong_local = 0
            strong_in_country_translated = 0
            coverage_variants = list(dict.fromkeys([*search_queries, *rerank_extra_variants]))
            for r in results_list:
                r_lat, r_lng = r.get("lat"), r.get("lng")
                if r_lat is None or r_lng is None:
                    continue
                r_name = r.get("name", "") or ""
                sim = max((cjk_text_similarity(v, r_name) for v in coverage_variants), default=0.0)
                dist = haversine_km(effective_bias_lat, effective_bias_lng, r_lat, r_lng)
                if dist <= 80.0:
                    is_photon_cross_script = (
                        str(r.get("source") or "").startswith("photon")
                        and dist <= 30.0
                        and bool(r_name)
                        and len(norm_query) >= 3
                        and (q_has_non_latin != bool(_NON_LATIN_SCRIPT_RE.search(r_name)))
                    )
                    if sim >= 0.85 or is_photon_cross_script:
                        strong_local += 1
                if had_cross_lang_translation and sim >= 0.85 and _in_target_cc(r):
                    strong_in_country_translated += 1
            needed = 3 if return_limit is None else max(return_limit, 2)
            if strong_local >= needed:
                return True
            if had_cross_lang_translation and strong_in_country_translated >= 2:
                return True
            return False
        return len(results_list) >= (return_limit or 5)

    # 先執行翻譯/日文/異體字變體之 Photon 查詢（非已查過之 speculative_query；最多並行 2 個高優先變體大幅降低尾延遲）
    searched_photon = {speculative_query.lower()}
    if global_q_sent:
        searched_photon.add(global_q_sent.lower())

    pending_photon_queries: List[str] = []
    for q in search_queries:
        if q.lower() in searched_photon:
            continue
        searched_photon.add(q.lower())
        pending_photon_queries.append(q)
        if len(pending_photon_queries) >= 2:
            break

    if pending_photon_queries and (had_cross_lang_translation or not (_has_strong_spatial_coverage(all_results) and len(all_results) >= (return_limit or 10))):
        # 若已切換城市前綴空間錨點（如台北搜『慕尼黑市政廳』-> 慕尼黑座標），直接使用該目標城市偏置精準命中德國主地標；
        # 否則若為無錨點跨國查詢則不帶原始城市偏置避免跨半球干擾。
        if city_prefix_switched and effective_bias_lat is not None and effective_bias_lng is not None:
            use_variant_lat = effective_bias_lat
            use_variant_lng = effective_bias_lng
            use_variant_zoom = speculative_zoom
        else:
            use_variant_lat = None if (region_conflicts_with_target and not is_explicit_city and not user_explicit_country and coord_country and country_code and coord_country != country_code.upper()) else speculative_lat
            use_variant_lng = None if use_variant_lat is None else speculative_lng
            use_variant_zoom = None if use_variant_lat is None else speculative_zoom
        photon_batch = await asyncio.gather(
            *[
                geocode_with_photon(
                    q,
                    max(upstream_limit, 5),
                    use_variant_lat,
                    use_variant_lng,
                    use_variant_zoom,
                    country_code=api_country_lock,
                    bbox=effective_bbox,
                )
                for q in pending_photon_queries
            ],
            return_exceptions=True,
        )
        for photon in photon_batch:
            if isinstance(photon, list) and photon:
                for b_idx, r in enumerate(photon):
                    r["source"] = "photon"
                    r["_batch_rank"] = b_idx
                all_results.extend(photon)
                found_source = "photon"

    # Nominatim 補全（空間感知短路 + Event-Loop 分桶鎖保護 1 req/s + extratags/extent 豐富化）
    nominatim_calls = 0
    if not _has_strong_spatial_coverage(all_results):
        nom_queries = search_queries[:2]
        for q in nom_queries:
            if nominatim_calls >= 2:
                break
            if nominatim_calls > 0 and _has_strong_spatial_coverage(all_results):
                break
            try:
                async with _get_nominatim_lock():
                    await _nominatim_rate_limit_wait()
                    async with httpx.AsyncClient(timeout=3.0) as client:
                        params: Dict[str, Any] = {
                            "q": q,
                            "format": "json",
                            "limit": max(upstream_limit, 5),
                            "addressdetails": 1,
                            "extratags": 1,
                        }
                        nom_country_lock = api_country_lock or (explicit_city_cc if (is_explicit_city and explicit_city_cc) else None)
                        if nom_country_lock:
                            lock_up = nom_country_lock.upper()
                            if lock_up in _OSM_SAR_CODES:
                                params["countrycodes"] = f"cn,{lock_up.lower()}"
                                if not effective_bbox and lock_up in COUNTRY_BOUNDS:
                                    b = COUNTRY_BOUNDS[lock_up]
                                    sar_vb = sanitize_bbox(
                                        f"{b['lng_min'] - 0.05},{b['lat_min'] - 0.05},{b['lng_max'] + 0.05},{b['lat_max'] + 0.05}"
                                    )
                                    if sar_vb:
                                        params["viewbox"] = sar_vb
                            else:
                                params["countrycodes"] = lock_up.lower()
                        if effective_bbox:
                            clean_vb = sanitize_bbox(effective_bbox)
                            if clean_vb:
                                params["viewbox"] = clean_vb
                        res = await client.get(
                            "https://nominatim.openstreetmap.org/search",
                            params=params,
                            headers={
                                "User-Agent": os.getenv("APP_USER_AGENT", "TabijiTravelPWA/1.0 (https://www.tabijiapp.com; contact@tabijiapp.com)"),
                                "Accept-Language": "zh-TW,zh,en",
                            },
                        )
                        nom_status = getattr(res, "status_code", 200)
                        nom_added = 0
                        if not isinstance(nom_status, int) or nom_status == 200:
                            data = res.json()
                            if isinstance(data, list) and data:
                                for b_idx, item in enumerate(data):
                                    if isinstance(item, dict) and "lat" in item and "lon" in item:
                                        extracted_nom = _extract_nominatim_result(item)
                                        extracted_nom["_batch_rank"] = b_idx
                                        all_results.append(extracted_nom)
                                        nom_added += 1
                                found_source = "nominatim"
                        nominatim_calls += 1
                        if nom_added > 0 and (not is_explicit_city or _has_strong_spatial_coverage(all_results)):
                            break
            except Exception as e:
                print(f"   ⚠️ Nominatim error: {type(e).__name__}: {e!r}")

    # 🆕 P3: Overpass 名稱搜尋（僅在 Photon + Nominatim 皆 0 筆、非純國名且允許 Overpass 時才觸發，杜絕 11s 拖尾）
    if allow_overpass and not user_explicit_country and len(all_results) < 1 and country_code:
        overpass_results = await search_overpass_by_name(clean_query, country_code, min(upstream_limit, 10))
        if overpass_results:
            for b_idx, r in enumerate(overpass_results):
                r["_batch_rank"] = b_idx
            all_results.extend(overpass_results)
            found_source = "overpass"
            log_debug(f"   🗺️ Overpass fallback: {len(overpass_results)} results")

    # ArcGIS Fallback
    if not all_results and ARCGIS_API_KEY:
        try:
            params = {"SingleLine": clean_query, "f": "json", "outFields": "PlaceName,Place_addr,Type", "maxLocations": upstream_limit, "token": ARCGIS_API_KEY}
            if effective_bias_lat is not None and effective_bias_lng is not None:
                params["location"] = f"{effective_bias_lng},{effective_bias_lat}" # ArcGIS uses x,y
                params["distance"] = 50000 # 50km radius bias
            
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(
                    "https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates",
                    params=params
                )
                data = res.json()
                if data.get("candidates"):
                    for b_idx, c in enumerate(data["candidates"]):
                        place_addr = c.get("attributes", {}).get("Place_addr", "")
                        all_results.append({
                            "lat": c["location"]["y"], "lng": c["location"]["x"],
                            "name": c.get("attributes", {}).get("PlaceName", clean_query),
                            "display_name": place_addr,
                            "address": place_addr,
                            "type": c.get("attributes", {}).get("Type", "place"),
                            "source": "arcgis",
                            "_batch_rank": b_idx,
                        })
                    found_source = "arcgis"
        except Exception:
            pass

    # 🗺️ 搜尋過濾策略：strict=False 不硬刪跨國結果，全部交由智慧排序；僅 strict=True 時鎖定目標國
    if country_code and all_results:
        all_results = filter_results_by_country(all_results, country_code, strict=is_strict)

    # 跨源正規化去重（統一 Photon N/W/R 與 Nominatim node/way/relation，並於撞鍵時回填缺失之 extent/display_name/admin_level）
    seen_coords: Dict[tuple, dict] = {}
    seen_osm_ids: Dict[tuple, dict] = {}
    unique = []
    for r in all_results:
        r_osm_id = r.get("osm_id")
        osm_key_id = (_normalize_osm_type(r.get("osm_type")), str(r_osm_id)) if r_osm_id is not None else None
        coord_key = (round(r["lat"], 5), round(r["lng"], 5))
        existing = (seen_osm_ids.get(osm_key_id) if osm_key_id else None) or seen_coords.get(coord_key)
        if existing is not None:
            for meta_key in ("extent", "display_name", "admin_level", "city", "state", "country", "importance"):
                if not existing.get(meta_key) and r.get(meta_key):
                    existing[meta_key] = r[meta_key]
            continue
        if osm_key_id:
            seen_osm_ids[osm_key_id] = r
        seen_coords[coord_key] = r
        unique.append(r)

    # 🧬 多元加權智能重排（return_limit=None 時回傳全部去重排序結果；母語設施單詞僅追加至 query_variants）
    rerank_variants = list(dict.fromkeys([*search_queries, *rerank_extra_variants]))
    ranked = rerank_top_k(
        unique,
        clean_query,
        bias_lat=effective_bias_lat,
        bias_lng=effective_bias_lng,
        target_country=country_code,
        limit=return_limit,
        zoom=zoom,
        query_variants=rerank_variants,
        is_explicit_country=user_explicit_country,
        is_explicit_city=is_explicit_city,
        explicit_city_coords=explicit_city_coords,
        is_admin_region_anchor=explicit_city_is_admin_region,
        is_subdistrict_anchor=is_subdistrict_anchor,
        prefix_label=city_prefix_key,
    )

    # 🆕 注入中文顯示名稱（僅限單一權威地標之全詞精確匹配且非連鎖品牌，絕不覆寫分店名！）
    if (
        chinese_display
        and ranked
        and landmark_data is not None
        and _is_exact_landmark_match(clean_query, landmark_data, chinese_display)
        and not is_chain_brand
    ):
        ranked[0]["original_name"] = ranked[0].get("name", clean_query)  # 先保留原始名稱再覆寫
        ranked[0]["name"] = chinese_display
        log_debug(f"   ✨ Injected Chinese Name: {chinese_display}")

    # 🛡️ 括號/前綴長標題單次降級（原詞 0 筆或僅回傳低相似度雜訊時退回純淨地名；嚴格單次禁止遞迴）
    should_paren_fallback = False
    if has_paren_or_prefix_noise:
        if not ranked:
            should_paren_fallback = True
        else:
            top_name = str(ranked[0].get("name") or "")
            same_script = bool(_NON_LATIN_SCRIPT_RE.search(cleaned_paren_query)) == bool(_NON_LATIN_SCRIPT_RE.search(top_name))
            best_paren_sim = max(
                cjk_text_similarity(clean_query, top_name),
                cjk_text_similarity(cleaned_paren_query, top_name),
            )
            if same_script and best_paren_sim < 0.55:
                should_paren_fallback = True
    if should_paren_fallback:
        log_debug(f"   🧹 Parenthetical Fallback (single-pass): '{clean_query}' -> '{cleaned_paren_query}'")
        return await smart_geocode_logic(
            cleaned_paren_query,
            limit=limit,
            trip_title=trip_title,
            api_key=api_key,
            lat=lat,
            lng=lng,
            country=country,
            region=region,
            zoom=zoom,
            bbox=bbox,
            allow_overpass=allow_overpass,
            _allow_paren_fallback=False,
        )

    return {"results": ranked, "source": found_source}


def log_debug(msg):
    # Use print instead of file write (HF Spaces has read-only filesystem)
    try:
        print(f"[DEBUG] {msg}")
    except (UnicodeEncodeError, Exception):
        try:
            encoding = getattr(sys.stdout, 'encoding', 'utf-8') or 'utf-8'
            clean_msg = str(msg).encode(encoding, errors="replace").decode(encoding)
            print(f"[DEBUG] {clean_msg}")
        except Exception:
            pass
