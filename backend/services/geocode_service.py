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
from google import genai
from google.genai import types
from pathlib import Path
import time
import random
import math
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
    "燈": "灯",  # 燈→灯 (與日式標準化一致)
    "縣": "県",  # 縣→県 (與日式標準化一致)
}


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
    for char, equiv in CHAR_EQUIVALENTS.items():
        text = text.replace(char, equiv)
    return text


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
            headers={"User-Agent": "RyanTravelApp/1.0"}
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
_NOMINATIM_LOCK = asyncio.Lock()
_NOMINATIM_CACHE = {}

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
        def run_sync_genai():
            client = genai.Client(api_key=api_key)
            return client.models.generate_content(
                model=WORKHORSE_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.0)
            )
        # Prevent event loop blocking
        res = await asyncio.to_thread(run_sync_genai)
        text = res.text.strip()
        if text.startswith("```json"):
            text = text[7:-3].strip()
        data = json.loads(text)
        return {k: v for k, v in data.items() if v and isinstance(v, str)}
    except Exception as e:
        print(f"⚠️ Gemma Address Parse Error: {e}")
        return {}


_DEAD_URL_CACHE = {}

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
                print(f"⚠️ [Tier 0] GAS URL Quota Exceeded. Banning URL for 12 hours.")
                _DEAD_URL_CACHE[url] = now
            elif data and "error_message" in data:
                print(f"⚠️ [Tier 0] GAS Maps API Error: {data['error_message']}")
                if "quota" in data['error_message'].lower() or "over_query_limit" in data.get("status", "").lower():
                    _DEAD_URL_CACHE[url] = now
        except Exception as e:
            print(f"⚠️ [Tier 0] GAS Request Failed: {e}")
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

    # Throttle 1 request per second (For Nominatim)
    async with _NOMINATIM_LOCK:
        # Check cache again inside lock just in case it was fetched while waiting
        now = time.time()
        if clean_addr in _NOMINATIM_CACHE and (now - _NOMINATIM_CACHE[clean_addr]["time"] < 3600):
            return _NOMINATIM_CACHE[clean_addr]["data"]

        base_url = os.getenv("NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org/search").strip()
        user_agent = os.getenv("APP_USER_AGENT", "RyanTravelApp/2.0 (contact@ryantravel.app)")
        
        # 🧠 Gemma 3 降維解構
        structured_data = await _gemma_parse_address(clean_addr, user_key=user_gemini_key)
        
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
            # Enforce 1 req/s delay if recent fetch
            last_f = getattr(resolve_address_pipeline, "_last_fetch", 0)
            elapsed = time.time() - last_f
            if elapsed < 1.0: await asyncio.sleep(1.0 - elapsed)
            
            res = await HTTPX_CLIENT.get(base_url, params=params, headers=headers, timeout=8.0)
            resolve_address_pipeline._last_fetch = time.time()
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
                        
                    last_f2 = getattr(resolve_address_pipeline, "_last_fetch", 0)
                    elapsed2 = time.time() - last_f2
                    if elapsed2 < 1.0: await asyncio.sleep(1.0 - elapsed2)
                    
                    res_deg = await HTTPX_CLIENT.get(base_url, params=params, headers=headers, timeout=8.0)
                    resolve_address_pipeline._last_fetch = time.time()
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
    limit: int = 5, 
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
        zoom: 縮放層級，用於 P2 動態 bias scale
        location_bias_scale: 0.0 ~ 1.0，手動控制偏移強度 (🆕 2026 擴充)
        osm_tag: OSM 標籤過濾，例如 'place:country' (🆕 2026 擴充)
        bbox: minLon,minLat,maxLon,maxLat 地圖視窗邊界過濾 (🆕 2026 視圖並行)
    """
    try:
        user_agent = os.getenv("APP_USER_AGENT", "RyanTravelApp/3.0 (contact@ryantravel.app)")
        async with httpx.AsyncClient(timeout=5.0, headers={"User-Agent": user_agent}) as client:
            # 🆕 P0: 雙變體查詢 (原字串 + 簡體變體)
            simplified = normalize_for_fuzzy(place_name)
            if simplified != place_name.lower().strip():
                query_text = f"{place_name} {simplified}"
            else:
                query_text = place_name
                
            # 🆕 P7: 意圖偵測 (自動 osm_tag，僅在未指定時啟動)
            if osm_tag is None:
                if any(k in place_name for k in ["站", "駅", "線", "鐵"]):
                    osm_tag = "railway:station"
                elif any(k in place_name for k in ["飯店", "酒店", "旅館", "ホテル"]):
                    osm_tag = "tourism:hotel"
                elif any(k in place_name for k in ["餐廳", "餐", "食堂", "レストラン"]):
                    osm_tag = "amenity:restaurant"
            
            params = {
                "q": query_text,
                "limit": limit
            }
            
            # 🆕 Country Bias
            if country_code:
                params["countrycode"] = country_code.lower()
            
            # 🆕 P7: 添加 osm_tag 過濾
            if osm_tag:
                params["osm_tag"] = osm_tag
                
            # 🆕 BBOX Viewport Bias
            if bbox:
                clean_bbox = sanitize_bbox(bbox)
                if clean_bbox:
                    params["bbox"] = clean_bbox
                
            # 🆕 Location Bias
            if lat is not None and lng is not None:
                params["lat"] = lat
                params["lon"] = lng
                
            # 🆕 P2: 動態 bias scale (根據 zoom)
            if location_bias_scale is not None:
                params["location_bias_scale"] = location_bias_scale
            elif zoom is not None:
                if zoom > 14:
                    params["location_bias_scale"] = 0.9
                elif zoom > 10:
                    params["location_bias_scale"] = 0.5
                else:
                    params["location_bias_scale"] = 0.2

            res = await client.get(
                "https://photon.komoot.io/api/",
                params=params
            )
            data = orjson.loads(res.content)
            if data.get("features") and len(data["features"]) > 0:
                results = []
                for feature in data["features"]:
                    props = feature.get("properties", {})
                    coords = feature.get("geometry", {}).get("coordinates", [0, 0])
                    
                    # 組合地址
                    address_parts = []
                    for key in ["country", "state", "city", "district", "street", "housenumber"]:
                        if props.get(key):
                            address_parts.append(props[key])
                    
                    extra = props.get("extra") or {}
                    admin_lvl = extra.get("admin_level") if isinstance(extra, dict) else None
                    if not admin_lvl and "admin_level" in props:
                        admin_lvl = props.get("admin_level")

                    extent = props.get("extent") or feature.get("bbox")

                    results.append({
                        "lat": coords[1],
                        "lng": coords[0],
                        "name": props.get("name", place_name),
                        "address": ", ".join(address_parts) if address_parts else props.get("name", ""),
                        "type": props.get("osm_value", "place"),
                        "osm_key": props.get("osm_key"),
                        "admin_level": int(admin_lvl) if str(admin_lvl).isdigit() else None,
                        "extent": extent if isinstance(extent, list) and len(extent) == 4 else None,
                        "importance": props.get("importance")
                    })
                
                if results:
                    print(f"[Photon] {place_name} -> {len(results)} results")
                    return results
    except Exception as e:
        print(f"[Photon] Error for '{place_name}': {e}")
    return None


# 🆕 P3: Overpass API 名稱搜尋（CJK 友好的最後防線）
async def search_overpass_by_name(
    name: str,
    country_code: str = None,
    limit: int = 3
) -> list | None:
    """透過 OSM 原始資料的 name/name:zh tag 進行 regex 匹配，
    繞過 Photon/Nominatim 的分詞限制。
    
    只在 Photon+Nominatim 結果不足時觸發，作為 fallback。
    """
    import re
    
    # 生成搜尋 regex（包含異體字變體）
    variants = expand_cjk_variants(name)
    name_regex = "|".join(re.escape(v) for v in variants)
    
    # 建構 area 限制（如果有國碼）
    area_filter = ""
    scope = ""
    if country_code:
        area_filter = f'area["ISO3166-1"="{country_code.upper()}"]->.searchArea;'
        scope = "(area.searchArea)"
    
    query = f"""
    [out:json][timeout:10];
    {area_filter}
    (
      nwr["name"~"{name_regex}",i]{scope};
      nwr["name:zh"~"{name_regex}",i]{scope};
      nwr["alt_name"~"{name_regex}",i]{scope};
    );
    out center {limit};
    """
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                "https://overpass-api.de/api/interpreter",
                data={"data": query},
                headers={"User-Agent": "RyanTravelApp/3.0"}
            )
            data = orjson.loads(res.content)
            elements = data.get("elements", [])
            if not elements:
                return None
            
            results = []
            for el in elements[:limit]:
                tags = el.get("tags", {})
                el_lat = el.get("lat") or el.get("center", {}).get("lat")
                el_lng = el.get("lon") or el.get("center", {}).get("lon")
                if not el_lat or not el_lng:
                    continue
                
                display_name = (
                    tags.get("name:zh") or
                    tags.get("name") or
                    tags.get("name:en") or
                    name
                )
                results.append({
                    "lat": el_lat, "lng": el_lng,
                    "name": display_name,
                    "address": tags.get("addr:full", ""),
                    "type": tags.get("amenity") or tags.get("tourism") or "place",
                    "source": "overpass"
                })
            
            if results:
                print(f"[Overpass] {name} -> {len(results)} results")
            return results or None
    except Exception as e:
        print(f"[Overpass] Error for '{name}': {e}")
        return None


async def reverse_geocode_with_photon(lat: float, lng: float):
    """Photon 反向地理編碼（座標 → 地名）"""
    try:
        user_agent = os.getenv("APP_USER_AGENT", "RyanTravelApp/3.0 (contact@ryantravel.app)")
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
        text = raw.strip()
        # 處理可能的 markdown 包裝
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        
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
}

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
        # 著名景點
        "迪士尼", "disney", "淺草", "asakusa", "箱根", "hakone", "富士", "fuji",
        "新宿", "shinjuku", "澀谷", "shibuya", "涩谷", "銀座", "ginza",
        "成田", "narita", "羽田", "haneda", "秋葉原", "akihabara", "原宿", "harajuku",
        "上野", "ueno", "池袋", "ikebukuro", "品川", "shinagawa",
        "清水寺", "金閣寺", "伏見稻荷", "嵐山", "arashiyama",
        "環球影城", "universal", "心齋橋", "道頓堀", "通天閣",
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
        "濱海灣", "marina bay", "樟宜", "changi", "環球影城",
    ],
    "HK": [
        "香港", "hong kong", "旺角", "mong kok", "尖沙咀", "tsim sha tsui",
        "銅鑼灣", "causeway bay", "中環", "central", "太平山", "victoria peak",
        "迪士尼", "disney", "海洋公園", "ocean park", "大嶼山", "lantau",
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

def get_fuzzy_index():
    global _FUZZY_INDEX, _LANDMARKS_KEYS_SORTED
    if _FUZZY_INDEX is not None:
        return _FUZZY_INDEX, _LANDMARKS_KEYS_SORTED
    
    print("🧠 [Lazy] Building fuzzy search index and loading external data...")
    
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


def translate_famous_landmark(query: str, country_code: str = None) -> tuple:
    """🏰 確定性翻譯著名景點（無需 AI，具備目標國別隔離防呆）"""
    query_lower = query.lower().strip()
    target_cc = (country_code or "").strip().upper()
    query_explicit_cc = (detect_country_from_keywords(query) or "").upper()
    
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
    
    # === 1. 精確匹配（最快） ===
    for landmark_key in LANDMARKS_KEYS_SORTED:
        landmark = LANDMARKS_DB[landmark_key]
        if not _is_country_compatible(landmark):
            continue
        
        if landmark_key.lower() in query_lower:
            print(f"🏰 Landmark Match: '{query}' → '{landmark['display']}'")
            return ([landmark["search"], query], landmark["display"], landmark)
        
        for alias in landmark.get("aliases", []):
            if alias.lower() in query_lower:
                print(f"🏰 Alias Match: '{alias}' → '{landmark['display']}'")
                return ([landmark["search"], query], landmark["display"], landmark)
    
    # === 2. 🆕 連鎖店品牌匹配 ===
    for category, brands in BRANDS_DB.items():
        if category.startswith("_"):  # 跳過 __comment
            continue
        if not isinstance(brands, dict):
            continue
        for brand_name, brand_data in brands.items():
            if not isinstance(brand_data, dict):
                continue
            # 檢查品牌名稱
            if brand_name.lower() in query_lower:
                search_term = brand_data.get("search_term", brand_name)
                print(f"🏪 Brand Match: '{query}' → '{search_term}'")
                return ([search_term, query], brand_name, None)
            # 檢查別名
            for alias in brand_data.get("aliases", []):
                if alias.lower() in query_lower:
                    search_term = brand_data.get("search_term", brand_name)
                    print(f"🏪 Brand Alias Match: '{alias}' → '{search_term}'")
                    return ([search_term, query], brand_name, None)
    
    # === 3. 🆕 模糊搜尋（容錯：typo、繁簡差異） ===
    normalized_query = normalize_for_fuzzy(query)
    if len(normalized_query) >= 2:  # 至少 2 字才進行模糊匹配
        # 🆕 使用預先建立的索引（效能優化）
        match_result = process.extractOne(
            normalized_query, 
            FUZZY_INDEX.keys(),
            scorer=fuzz.ratio,
            score_cutoff=88  # 🆕 提高閾值至 88% 減少誤匹配
        )
        
        if match_result:
            matched_key, score, _ = match_result
            landmark_key, landmark = FUZZY_INDEX[matched_key]
            if _is_country_compatible(landmark):
                print(f"[FUZZY] '{query}' -> '{landmark['display']}' (score: {score})")
                return ([landmark["search"], query], landmark["display"], landmark)

    
    # === 4. 特殊處理：迪士尼 ===
    if "迪士尼" in query or "disney" in query_lower:
        if country_code == "JP" or any(jp in query.lower() for jp in ["東京", "tokyo", "日本", "japan"]):
            disney = LANDMARKS_DB.get("東京迪士尼樂園")
            return (["Tokyo Disneyland", "東京ディズニーランド", query], "東京迪士尼樂園", disney)
        elif country_code == "HK" or "香港" in query:
            return (["Hong Kong Disneyland", query], "香港迪士尼樂園", None)
    
    return ([query], None, None)


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

        from services.model_manager import call_extraction_server
        raw = await call_extraction_server(prompt, intent_type="GEOCODE", api_key=api_key)
        
        result = raw.strip().upper()
        if result in COUNTRY_BOUNDS:
            print(f"🧠 Trip title '{trip_title}' → Country: {result}")
            return result
        return None
    except Exception as e:
        print(f"ℹ️ [SmartGeo] TripTitle 國家推斷跳過 ({e})，轉入關鍵字檢索")
        return None


# 🆕 翻譯結果緩存（減少重複 AI 調用）
TRANSLATION_CACHE = {}  # {(query, country_code): [translations]}

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

async def translate_place_name(query: str, country_code: str, api_key: str = None) -> list:
    """🔤 使用 Gemini 將地名翻譯成目標國家語言
    
    🆕 v2.1: 針對日本輸出多語言變體（漢字、假名、羅馬拼音）
    
    Returns: 搜尋變體列表 [翻譯後, 英文, 原文]
    """
    if not country_code or not api_key:
        return [query]
    
    # 🆕 緩存檢查
    # Cache key based on input
    cache_key = (query.lower(), country_code) # Corrected cache_key to match function parameters
    if cache_key in TRANSLATION_CACHE:
        print(f"🔤 CACHE HIT: '{query}' → {TRANSLATION_CACHE[cache_key]}")
        return TRANSLATION_CACHE[cache_key]
    
    country_info = COUNTRY_BOUNDS.get(country_code)
    if not country_info:
        return [query]
    
    try:
        # Step 1: AI Analysis
        # 🆕 識別語系策略
        strat_key = get_country_search_strategy(country_code)
        strat_info = GEOCODE_STRATEGIES.get(strat_key, GEOCODE_STRATEGIES["GLOBAL_V1"])
        instruction = strat_info["instruction"]
        
        country_name = country_info["name"]
        
        # 🆕 動態 Prompt 生成：根據各國語系策略進行專家級轉換
        prompt = f"""你是地理資訊與搜尋地標專家。用戶正在前往 {country_name} ({country_code}) 進行旅行。
用戶目前的搜尋地名：「{query}」

【核心指令】：{instruction}
【額外要求】：
1. 輸出格式為每行一個，不要有編號 (1. 2. 3.) 或註釋說明。
2. 最多回傳 3-4 行。
3. 如果輸入詞已是當地母語，請額外提供英文名。

只輸出翻譯後的關鍵字列表，每行一個："""

        # 🆕 傳入 api_key 確保地圖搜尋翻譯功能正常 (BYOK 模式)
        raw = await call_extraction_server(prompt, intent_type="GEOCODE", api_key=api_key)
        
        lines = [line.strip() for line in raw.strip().split("\n") if line.strip()]
        if lines:
            # 確保原始查詢也在列表中
            if query not in lines:
                lines.append(query)
            result = lines[:5]  # 🆕 最多5個變體（增加語系容錯）
            # 🆕 存入緩存
            TRANSLATION_CACHE[cache_key] = result
            print(f"🔤 Translated '{query}' via {strat_key} → {result} (cached)")
            return result
        return [query]
    except Exception as e:
        print(f"🔤 Translation error: {e}")
        return [query]



def filter_results_by_country(results: list, country_code: str, strict: bool = True) -> list:
    """🗺️ 根據經緯度過濾結果，只保留目標國家內的地點（具備優雅降級防禦）"""
    if not country_code or country_code not in COUNTRY_BOUNDS:
        return results
    
    bounds = COUNTRY_BOUNDS[country_code]
    filtered = []
    
    for r in results:
        lat = r.get("lat", 0)
        lng = r.get("lng", 0)
        
        # 寬鬆邊界檢查 (+/- 0.1 度緩衝)
        if (bounds["lat_min"] - 0.1 <= lat <= bounds["lat_max"] + 0.1 and 
            bounds["lng_min"] - 0.1 <= lng <= bounds["lng_max"] + 0.1):
            filtered.append(r)
    
    if filtered:
        log_debug(f"Filtered: {len(results)} -> {len(filtered)} (Target: {country_code})")
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


def cjk_text_similarity(query: str, target: str) -> float:
    """CJK 字符級雙向字義相似度
    
    解決 rapidfuzz 在無空格中文下 token_set_ratio 崩潰為 66% 的問題。
    結合精確匹配、子字串包含加分與字元級集合匹配。
    """
    q = query.strip().lower()
    t = target.strip().lower()
    if not q or not t:
        return 0.0
    if q == t:
        return 1.0
    if q in t:
        return 0.85 + 0.15 * (len(q) / max(len(q), len(t)))
    q_chars = " ".join(list(q))
    t_chars = " ".join(list(t))
    return fuzz.token_set_ratio(q_chars, t_chars) / 100.0


def proximity_decay(dist_km: float) -> float:
    """平滑有理衰減函數
    
    取代高斯 50km 斷崖 (exp(-800)=0)，兼顧同城優先 (10km=0.94, 50km=0.75) 
    與跨國交通樞紐保留 (2000km=0.07)。
    """
    return 1.0 / (1.0 + (dist_km / 150.0))


def rerank_top_k(
    candidates: list,
    query: str,
    bias_lat: Optional[float] = None,
    bias_lng: Optional[float] = None,
    target_country: Optional[str] = None,
    limit: int = 5
) -> list:
    """多元加權 Top-K 重排演算法
    
    FinalScore = 0.50 * 文字相似度 + 0.30 * 空間距離衰減 + 0.10 * 權威重要度 + 0.10 * 目標國加分
    相容 Photon 缺省 importance 的順位遞減啟發補償。
    """
    if not candidates:
        return []
        
    scored = []
    target_bounds = COUNTRY_BOUNDS.get(target_country.upper()) if target_country else None

    for idx, item in enumerate(candidates):
        name = item.get("name", "")
        lat = item.get("lat")
        lng = item.get("lng")
        
        # 1. 字義相似度 (權重 50%)
        fuzz_score = cjk_text_similarity(query, name)
        
        # 2. 空間距離衰減 (權重 30%)
        proximity_score = 0.5
        dist_km = None
        if bias_lat is not None and bias_lng is not None and lat is not None and lng is not None:
            dist_km = haversine_km(bias_lat, bias_lng, lat, lng)
            proximity_score = proximity_decay(dist_km)
            
        # 3. 權威度評分 (權重 10%)
        raw_imp = item.get("importance")
        if raw_imp is not None:
            try:
                imp_score = max(0.0, min(1.0, float(raw_imp)))
            except (ValueError, TypeError):
                imp_score = 0.1
        else:
            # 順位遞減啟發補償（Photon 內部已按分數排序，前序給予較高權重）
            imp_score = max(0.1, 0.7 - idx * 0.1)
                
        # 4. 目標國軟性加分 (加分 10%)
        country_bonus = 0.0
        if target_bounds and lat is not None and lng is not None:
            if (target_bounds["lat_min"] - 0.1 <= lat <= target_bounds["lat_max"] + 0.1 and
                target_bounds["lng_min"] - 0.1 <= lng <= target_bounds["lng_max"] + 0.1):
                country_bonus = 0.10

        final_score = (
            0.50 * fuzz_score +
            0.30 * proximity_score +
            0.10 * imp_score +
            country_bonus
        )
        
        item_copy = dict(item)
        item_copy["_score"] = round(final_score, 4)
        if dist_km is not None:
            item_copy["_dist_km"] = round(dist_km, 2)
        scored.append((final_score, item_copy))
        
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]


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
        result = raw.strip().upper()
        if result in COUNTRY_BOUNDS:
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
    "新北": {"lat": 25.0169, "lng": 121.4628, "country": "TW"},
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
    "北海道": {"lat": 43.0618, "lng": 141.3545, "country": "JP"},
    "hokkaido": {"lat": 43.0618, "lng": 141.3545, "country": "JP"},
    "札幌": {"lat": 43.0618, "lng": 141.3545, "country": "JP"},
    "sapporo": {"lat": 43.0618, "lng": 141.3545, "country": "JP"},
    "沖繩": {"lat": 26.2124, "lng": 127.6809, "country": "JP"},
    "okinawa": {"lat": 26.2124, "lng": 127.6809, "country": "JP"},
    "那霸": {"lat": 26.2124, "lng": 127.6809, "country": "JP"},
    "naha": {"lat": 26.2124, "lng": 127.6809, "country": "JP"},
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
    "首爾": {"lat": 37.5665, "lng": 126.9780, "country": "KR"},
    "seoul": {"lat": 37.5665, "lng": 126.9780, "country": "KR"},
    "釜山": {"lat": 35.1796, "lng": 129.0756, "country": "KR"},
    "busan": {"lat": 35.1796, "lng": 129.0756, "country": "KR"},
    "濟州": {"lat": 33.4996, "lng": 126.5312, "country": "KR"},
    "jeju": {"lat": 33.4996, "lng": 126.5312, "country": "KR"},
    "曼谷": {"lat": 13.7563, "lng": 100.5018, "country": "TH"},
    "bangkok": {"lat": 13.7563, "lng": 100.5018, "country": "TH"},
    "清邁": {"lat": 18.7883, "lng": 98.9853, "country": "TH"},
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
    clean = re.sub(r'[^\w\s\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af-]', ' ', raw)
    clean = re.sub(r'(?:19|20)\d{2}\s*年?', ' ', clean)
    clean = re.sub(
        r'((?:\d+|[一二三四五六七八九十百兩]+)\s*日遊|(?:\d+|[一二三四五六七八九十百兩]+)\s*天\d*[一二三四五六七八九十百兩]*\s*夜|(?:\d+|[一二三四五六七八九十百兩]+)\s*天|(?:\d+|[一二三四五六七八九十百兩]+)\s*日|自由行|之旅|極致之旅|深度遊|行程|冬日遊|夏日遊|攻略|漫遊|快閃|旅遊|旅行)',
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

    # 若座標已知但尚未確定國家，從 COUNTRY_BOUNDS 反推所在國別
    if anchor_lat is not None and anchor_lng is not None and not inferred_country:
        for cc, b in COUNTRY_BOUNDS.items():
            if b["lat_min"] <= anchor_lat <= b["lat_max"] and b["lng_min"] <= anchor_lng <= b["lng_max"]:
                inferred_country = cc
                break

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
    m_xml = re.search(r"<destination>(.*?)</destination>", raw, flags=re.IGNORECASE | re.DOTALL)
    target_segment = m_xml.group(1).strip() if m_xml else raw[:500]
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

    HOMONYM_GUARD_KEYS = ("龍山寺", "東照宮", "中國城", "中華街", "故宮", "天后宮", "媽祖廟", "文武廟")

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

    # Step B & C: 逐項座標驗證與非破壞性自癒
    sem = asyncio.Semaphore(10)

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

        is_homonym_place = any(hk in place_name for hk in HOMONYM_GUARD_KEYS)
        reason = None
        if ilat is None or ilng is None:
            reason = "missing"
        elif not _in_country(ilat, ilng):
            # 允許邊境城市當日跨境順遊 (如日內瓦->霞慕尼 64km、新加坡->新山 18km)，但嚴格攔截 >80km 跨國幻覺與撞名地標
            if (
                not is_homonym_place
                and d_anc.get("lat") is not None
                and d_anc.get("lng") is not None
                and haversine_km(d_anc["lat"], d_anc["lng"], ilat, ilng) <= 80.0
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
            elif min_dist_city > 180.0:
                reason = "spatial_outlier"

        if reason is None:
            _set_coords(ilat, ilng)
            return item

        healed_lat, healed_lng = None, None
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
                    ),
                    timeout=2.5,
                )
                if geo_res and geo_res.get("results"):
                    first_match = geo_res["results"][0]
                    healed_lat = first_match.get("lat")
                    healed_lng = first_match.get("lng")
            except Exception as e:
                print(f"⚠️ [Spatial Healer] Geocode fallback for '{place_name}' ({reason}): {e}")

        if healed_lat is not None and healed_lng is not None:
            _set_coords(healed_lat, healed_lng)
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


async def smart_geocode_logic(
    query: str, 
    limit: int, 
    trip_title: Optional[str] = None, 
    api_key: Optional[str] = None, 
    lat: Optional[float] = None, 
    lng: Optional[float] = None,
    country: Optional[str] = None,    # 🆕 前端傳入的國家過濾
    region: Optional[str] = None,     # 🆕 前端傳入的區域過濾
    zoom: Optional[float] = None,     # 🆕 P1: 地圖縮放層級 (用於動態 bias)
    bbox: Optional[str] = None        # 🆕 P2: 地圖視窗邊界 (minLon,minLat,maxLon,maxLat)
) -> dict:
    log_debug(f"🌍 [SmartGeo] 啟動多層檢索: '{query}' (Trip: {trip_title or '無'}, 偏置: {lat},{lng})")
    log_debug(f"🔍 [SmartGeo] Start search: '{query}' (Trip: {trip_title}, Country: {country}, Region: {region}, Zoom: {zoom}, Bias: {lat},{lng})")
    
    # 🧠 Step 0: 智能國家判斷和翻譯
    country_code = None
    api_country_lock = None # 🆕 只有明確指定時才物理鎖死 API
    search_queries = [query]
    chinese_display = None  # 🆕 中文顯示名稱
    
    # 🆕 第零優先級：前端明確指定的國家 (最高優先，大小寫不敏感，支援 2 位 ISO 與全名)
    if country:
        c_upper = country.strip().upper()
        if c_upper in COUNTRY_BOUNDS:
            country_code = c_upper
        else:
            normalized_country = country.strip().lower()
            country_code = next((v.upper() for k, v in COUNTRY_TO_ISO.items() if k.lower() == normalized_country), None)
        if country_code:
            api_country_lock = country_code
            log_debug(f"   🎯 Frontend Country Filter (Lock) → {country_code}")
    
    # 🆕 0.1 優先級：偵測搜尋詞本身是否就是國家名（明確導向）
    user_explicit_country = False
    norm_query = query.strip().lower()
    # 修正：使用正確的變數名稱 COUNTRY_TO_ISO，並支援大小寫不敏感查詢
    found_explicit_code = next((v.upper() for k, v in COUNTRY_TO_ISO.items() if k.lower() == norm_query), None)
    if found_explicit_code:
        country_code = found_explicit_code
        user_explicit_country = True
        api_country_lock = country_code
        log_debug(f"   🌍 Explicit Country Query Detected (Lock) → {country_code}")
    
    # 第一優先級：關鍵字規則（確定性，零延遲，依序校驗：景點名稱 ➔ 母體行程標題 ➔ 目標區域）
    if not country_code:
        country_code = detect_country_from_keywords(query)
        if not country_code and trip_title:
            country_code = detect_country_from_keywords(trip_title)
        if not country_code and region:
            country_code = detect_country_from_keywords(region)
        if country_code:
            log_debug(f"   🔑 Keyword Match → {country_code}")

    
    # 第二優先級：AI 判斷（需要 API Key）- 🆕 並行運算優化
    if not country_code and api_key:
        log_debug("   🚀 Parallelizing AI country detection...")
        tasks = []
        if trip_title:
            tasks.append(detect_country_from_trip_title(trip_title, api_key))
        tasks.append(detect_country_from_query(query, api_key))
        
        # 使用 asyncio.gather 同時啟動多個 AI 任務，將延遲從相加轉為取最大值
        ai_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 解析結果（優先級：標題 > 查詢）
        res_list = [r for r in ai_results if isinstance(r, str) and r]
        if res_list:
            country_code = res_list[0]
            log_debug(f"   🧠 Detected Country (Parallel): {country_code}")


    # 🆕 Step 1.1: 快速路徑 - 如果查詢是坐標，直接跳過所有 AI 邏輯
    if "," in query:
        parts = query.split(",")
        if len(parts) == 2:
            try:
                lat_val, lng_val = float(parts[0]), float(parts[1])
                log_debug(f"   ⚡ FAST PATH: Coordinates detected ({lat_val}, {lng_val})")
                return {"results": [{
                    "lat": lat_val, "lng": lng_val, "name": query, "address": query, "type": "coordinate", "source": "direct"
                }], "source": "direct"}
            except: pass

    # 🆕 Step 1.2: 先嘗試確定性著名景點翻譯（無需 API Key）
    landmark_result = translate_famous_landmark(query, country_code)
    search_terms, display_name, landmark_data = landmark_result
    
    # 🚀 INSTANT RETURN: 如果景點有座標且國家與空間錨點相符，直接回傳，完全跳過 API 調用
    landmark_country = (landmark_data.get("country") or "").upper() if landmark_data else ""
    effective_target_cc = (api_country_lock or country_code or "").upper()
    country_matches = True
    if effective_target_cc and landmark_country:
        country_matches = (landmark_country == effective_target_cc)

    # 🛡️ 空間錨點距離守衛：若已提供行程錨點 (lat, lng)，且地標距離當前行程錨點超過 80km，嚴禁秒回跨國/跨城同名地標
    if landmark_data and landmark_data.get("lat") and landmark_data.get("lng") and lat is not None and lng is not None:
        if haversine_km(lat, lng, landmark_data["lat"], landmark_data["lng"]) > 80.0:
            country_matches = False
            display_name = None

    if landmark_data and landmark_data.get("lat") and landmark_data.get("lng") and country_matches:
        instant_result = {
            "lat": landmark_data["lat"],
            "lng": landmark_data["lng"],
            "name": landmark_data.get("display", display_name),
            "address": f"{landmark_data.get('display', display_name)}, {landmark_data.get('country', '')}",
            "type": "landmark",
            "source": "landmarks_db",
            "original_name": query
        }
        log_debug(f"   ⚡ INSTANT RETURN: {display_name} ({landmark_data['lat']}, {landmark_data['lng']})")
        return {"results": [instant_result], "source": "landmarks_db"}
    
    # 🆕 Step 2: 投機性並行搜尋 (Speculative Parallelism)
    # 我們開啟三個任務：AI 翻譯、原始名稱搜尋、以及（如果有）景點搜尋
    search_queries = []
    chinese_display = None
    
    tasks = []
    # 任務 A: AI 翻譯 (如果需要)
    translation_task = None
    if not display_name and country_code and api_key:
        translation_task = asyncio.create_task(translate_place_name(query, country_code, api_key))
        tasks.append(translation_task)
    
    # 任務 B: 原始名稱初步搜尋 (Speculative Photon)
    region_term = extract_region_for_search(region or trip_title) if (region or trip_title) else ""
    # 🛡️ 區域前綴消歧義：若地名本身不含區域前綴，優先以前綴組裝搜尋 (例如 "北海道 朝市")
    if region_term and region_term not in query:
        speculative_query = f"{region_term} {query}".strip()
    else:
        speculative_query = query
    speculative_task = asyncio.create_task(geocode_with_photon(speculative_query, limit, lat, lng, zoom, country_code=api_country_lock, bbox=bbox))
    tasks.append(speculative_task)
    
    # 🆕 任務 C: 全域觀察者任務 (Global Observer)
    # 如果偵測到「明確國名」，開啟全域不偏向搜尋，防止在地店家排擠國家座標
    global_task = None
    if user_explicit_country:
        # 使用低強度 Bias (0.1) 確保全球範圍的權威結果能排到最前面
        # 🆕 橋階關鍵字：利用純國碼 (如 AU) 進行強攻，直接定位主權實體，不帶地緣偏見
        global_q = country_code.upper() if country_code else query
        global_task = asyncio.create_task(geocode_with_photon(global_q, limit, None, None, None, location_bias_scale=None, osm_tag="place:country", country_code=api_country_lock, bbox=bbox))
        tasks.append(global_task)

    log_debug(f"   🚀 Starting Speculative Searches for '{query}'...")
    
    # 等待初步結果或翻譯完成（設置一個小的超時或併行等待）
    # 為了保持簡單，我們等待所有任務完成，但此時已是「並行」而非「順位」
    await asyncio.gather(*tasks, return_exceptions=True)

    # 彙整搜尋關鍵字
    if display_name:
        search_queries = search_terms
        chinese_display = display_name
    elif translation_task and not translation_task.exception():
        search_queries = translation_task.result()
        log_debug(f"   🔤 AI Translated: {search_queries}")
    
    # 🆕 P1-B: 展開 CJK 異體字變體（如「台中一中」→「臺中一中」）加入搜尋
    for variant in expand_cjk_variants(query):
        if variant not in search_queries:
            search_queries.append(variant)

    if not country_code:
        log_debug("   ⚠️ No country detected, using broad search")

    

    
    all_results = []
    found_source = "none"
    
    # 🆕 整合投機性搜尋結果
    # A. 全域觀察者結果 (優先級最高，因為這是明確的國土座標)
    if global_task and not global_task.exception():
        global_results = global_task.result()
        if global_results:
            for r in global_results: r["source"] = "photon_global"
            all_results.extend(global_results)
            log_debug(f"   🌍 Found {len(global_results)} global entities")

    # B. 在地觀察者結果 (次之，包含附近同名店家)
    if speculative_task and not speculative_task.exception():
        photon_spec = speculative_task.result()
        if photon_spec:
            for r in photon_spec: r["source"] = "photon_speculative"
            all_results.extend(photon_spec)
            found_source = "photon"
            log_debug(f"   ⚡ Using {len(photon_spec)} speculative results")
    
    # 🆕 P0 Pre-filter: 提前清除境外 Speculative 垃圾結果
    # 防止中國「台州」等結果佔滿 effective_limit，導致後續 Nominatim 搜尋被 break 跳過
    is_strict = bool(api_country_lock) # 只有硬性鎖定時才進行嚴格過濾
    if country_code and all_results:
        pre_filtered = filter_results_by_country(all_results, country_code, strict=is_strict)
        if len(pre_filtered) < len(all_results):
            log_debug(f"   🧹 Pre-filter: {len(all_results)} → {len(pre_filtered)} (strict={is_strict})")
            all_results = pre_filtered

    # 限定候選池數量 (當 limit=1 時，仍收集至少 5 筆候選讓 Photon + Nominatim 共同進入 rerank_top_k 距離重排)
    effective_limit = max(limit * 3, 5) if (lat is not None and lng is not None) else (limit * 2 if user_explicit_country else limit)
    
    nominatim_calls = 0  # 🆕 P0: Nominatim 呼叫計數器（遵守 1req/s 政策，最多 2 次）
    
    for q in search_queries:
        if len(all_results) >= effective_limit:
            break
        
        # 🆕 P0 修復：Photon 只對「非原始查詢」執行（原始已 Speculative 搜過）
        # 但 Nominatim 對「所有查詢」執行，因為 Nominatim 的 CJK 能力遠優於 Photon
        if q != query:
            # Photon (🆕 P1: 傳遞 zoom 用於動態 bias scale, 傳遞 bbox)
            photon = await geocode_with_photon(q, max(limit, 3), lat, lng, zoom, country_code=api_country_lock, bbox=bbox)
            if photon:
                for r in photon: r["source"] = "photon"
                all_results.extend(photon)
                found_source = "photon"

        # Nominatim（所有查詢都執行，包括原始中文查詢，並帶入空間錨點 viewbox）
        if nominatim_calls < 2:
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    params = {"q": q, "format": "json", "limit": max(limit, 3), "addressdetails": 1}
                    if api_country_lock:
                        params["countrycodes"] = api_country_lock.lower()
                    if bbox:
                        clean_vb = sanitize_bbox(bbox)
                        if clean_vb:
                            params["viewbox"] = clean_vb
                    res = await client.get("https://nominatim.openstreetmap.org/search", params=params, headers={
                        "User-Agent": "RyanTravelApp/3.0 (contact@ryantravel.app)",
                        "Accept-Language": "zh-TW,zh,en"  # 🆕 P0: 確保中文結果優先回傳
                    })
                    data = res.json()
                    if data:
                        for item in data:
                            imp = item.get("importance")
                            all_results.append({
                                "lat": float(item["lat"]), "lng": float(item["lon"]),
                                "name": item.get("name") or item.get("display_name", "").split(",")[0],
                                "address": item.get("display_name", ""), "type": item.get("type", "place"),
                                "importance": float(imp) if imp is not None else None,
                                "source": "nominatim"
                            })
                        found_source = "nominatim"
                    nominatim_calls += 1
            except Exception as e:
                print(f"   ⚠️ Nominatim error: {e}")

    # 🆕 P3: Overpass 名稱搜尋（當 Photon + Nominatim 結果不足時啟動）
    if len(all_results) < 2 and country_code:
        overpass_results = await search_overpass_by_name(query, country_code, limit)
        if overpass_results:
            all_results.extend(overpass_results)
            found_source = "overpass"
            log_debug(f"   🗺️ Overpass fallback: {len(overpass_results)} results")

    # ArcGIS Fallback
    if not all_results and ARCGIS_API_KEY:
        try:
            params = {"SingleLine": query, "f": "json", "outFields": "PlaceName,Place_addr,Type", "maxLocations": effective_limit, "token": ARCGIS_API_KEY}
            if lat is not None and lng is not None:
                params["location"] = f"{lng},{lat}" # ArcGIS uses x,y
                params["distance"] = 50000 # 50km radius bias
            
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(
                    "https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates",
                    params=params
                )
                data = res.json()
                if data.get("candidates"):
                    for c in data["candidates"]:
                        all_results.append({
                            "lat": c["location"]["y"], "lng": c["location"]["x"],
                            "name": c.get("attributes", {}).get("PlaceName", query),
                            "address": c.get("attributes", {}).get("Place_addr", ""),
                            "type": c.get("attributes", {}).get("Type", "place"),
                            "source": "arcgis"
                        })
                    found_source = "arcgis"
        except Exception:
            pass

    # 🗺️ 搜尋過濾策略 (寬容化優雅降級)
    if country_code and all_results:
        is_strict = bool(api_country_lock)
        all_results = filter_results_by_country(all_results, country_code, strict=is_strict)

    # 去重
    seen = set()
    unique = []
    for r in all_results:
        key = (round(r["lat"], 5), round(r["lng"], 5))
        if key not in seen:
            seen.add(key)
            unique.append(r)

    # 🧬 多元加權智能重排 (Top-K Reranking)
    ranked = rerank_top_k(
        unique, 
        query, 
        bias_lat=lat, 
        bias_lng=lng, 
        target_country=country_code, 
        limit=limit
    )

    # 🆕 注入中文顯示名稱
    if chinese_display and ranked:
        ranked[0]["name"] = chinese_display
        ranked[0]["original_name"] = ranked[0].get("name", query)  # 保留原始名稱
        log_debug(f"   ✨ Injected Chinese Name: {chinese_display}")

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
