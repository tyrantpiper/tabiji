# -*- coding: utf-8 -*-
"""
Shared Flight Pricing & IATA Resolution Service (Wave 2.3)
----------------------------------------------------------
- Single shared httpx.AsyncClient connection pool (closed cleanly on app shutdown)
- In-memory LRU TTL caches for both IATA resolution (24h) and live flight prices (1h)
- Zero-key Travelpayouts `places2` dynamic IATA translation + fast local city map
- Explicit `__reset_flight_pricing_for_testing()` for deterministic pytest isolation
"""

import asyncio
from collections import OrderedDict
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger("ryan-travel-api")

TP_BASE = "https://api.travelpayouts.com"
TP_PLACES2_URL = "https://autocomplete.travelpayouts.com/places2"
TABIJI_USER_AGENT = "TabijiTravelPWA/1.0 (https://www.tabijiapp.com; contact@tabijiapp.com)"

_IATA_CODE_RE = re.compile(r"^[A-Z]{3}$")
_IATA_IN_TEXT_RE = re.compile(r"\(([A-Z]{3})\)")
_TITLE_NOISE_RE = re.compile(
    r"(?:20\d{2}|年|家族|之旅|自由行|行程|旅遊|旅行|攻略|獨旅|蜜月|跨年|賞櫻|賞楓|\d+\s*天\s*\d*\s*夜?|"
    r"\b(?:trip|travel|itinerary|guide|vacation|holiday|family|days?|nights?)\b)",
    re.IGNORECASE,
)

# Fast zero-latency city/region -> IATA map for common trip titles
_CITY_TO_IATA: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (("東京", "tokyo", "成田", "羽田", "新宿", "澀谷", "渋谷", "淺草"), "TYO"),
    (("大阪", "osaka", "關西", "関西", "難波", "梅田", "京都", "kyoto", "奈良", "神戶"), "OSA"),
    (("北海道", "hokkaido", "札幌", "sapporo", "小樽", "富良野", "函館", "旭川", "新千歲"), "CTS"),
    (("福岡", "fukuoka", "九州", "博多", "由布院", "熊本"), "FUK"),
    (("沖繩", "沖縄", "那霸", "okinawa", "naha", "石垣"), "OKA"),
    (("名古屋", "nagoya", "中部", "高山", "白川鄉"), "NGO"),
    (("仙台", "sendai", "東北"), "SDJ"),
    (("廣島", "広島", "hiroshima"), "HIJ"),
    (("首爾", "seoul", "仁川", "金浦", "明洞", "弘大"), "SEL"),
    (("釜山", "busan"), "PUS"),
    (("濟州", "jeju"), "CJU"),
    (("台北", "臺北", "taipei", "桃園"), "TPE"),
    (("高雄", "kaohsiung"), "KHH"),
    (("台中", "臺中", "taichung"), "RMQ"),
    (("香港", "hong kong"), "HKG"),
    (("澳門", "macau", "macao"), "MFM"),
    (("新加坡", "singapore"), "SIN"),
    (("曼谷", "bangkok"), "BKK"),
    (("清邁", "chiang mai"), "CNX"),
    (("普吉", "phuket"), "HKT"),
    (("吉隆坡", "kuala lumpur"), "KUL"),
    (("峇里島", "bali", "登巴薩"), "DPS"),
    (("河內", "hanoi"), "HAN"),
    (("胡志明", "ho chi minh"), "SGN"),
    (("峴港", "da nang"), "DAD"),
    (("馬尼拉", "manila"), "MNL"),
    (("倫敦", "london"), "LON"),
    (("巴黎", "paris"), "PAR"),
    (("羅馬", "rome"), "ROM"),
    (("米蘭", "milan"), "MIL"),
    (("威尼斯", "venice"), "VCE"),
    (("蘇黎世", "zurich", "瑞士"), "ZRH"),
    (("慕尼黑", "munich"), "MUC"),
    (("法蘭克福", "frankfurt"), "FRA"),
    (("柏林", "berlin"), "BER"),
    (("巴塞隆納", "barcelona"), "BCN"),
    (("馬德里", "madrid"), "MAD"),
    (("阿姆斯特丹", "amsterdam"), "AMS"),
    (("維也納", "vienna"), "VIE"),
    (("布拉格", "prague"), "PRG"),
    (("赫爾辛基", "helsinki", "芬蘭"), "HEL"),
    (("冰島", "雷克雅維克", "reykjavik", "iceland"), "REK"),
    (("紐約", "new york"), "NYC"),
    (("洛杉磯", "los angeles"), "LAX"),
    (("舊金山", "san francisco"), "SFO"),
    (("西雅圖", "seattle"), "SEA"),
    (("溫哥華", "vancouver"), "YVR"),
    (("多倫多", "toronto"), "YTO"),
    (("雪梨", "sydney"), "SYD"),
    (("墨爾本", "melbourne"), "MEL"),
    (("奧克蘭", "auckland"), "AKL"),
    (("杜拜", "dubai"), "DXB"),
)

# IATA / 3-letter country code -> (zh_display_city, en_ascii_display_city)
# All English values MUST remain strictly ASCII (e.g. CTS -> "Hokkaido", OKA -> "Okinawa", TPE -> "Taipei").
_IATA_TO_DISPLAY_CITY: Dict[str, Tuple[str, str]] = {
    "TYO": ("東京", "Tokyo"),
    "NRT": ("東京", "Tokyo"),
    "HND": ("東京", "Tokyo"),
    "OSA": ("大阪", "Osaka"),
    "KIX": ("大阪", "Osaka"),
    "ITM": ("大阪", "Osaka"),
    "UKB": ("神戶", "Kobe"),
    "CTS": ("北海道", "Hokkaido"),
    "SPK": ("札幌", "Sapporo"),
    "HKD": ("函館", "Hakodate"),
    "AKJ": ("旭川", "Asahikawa"),
    "FUK": ("福岡", "Fukuoka"),
    "KMJ": ("熊本", "Kumamoto"),
    "KOJ": ("鹿兒島", "Kagoshima"),
    "OKA": ("沖繩", "Okinawa"),
    "ISG": ("石垣島", "Ishigaki"),
    "NGO": ("名古屋", "Nagoya"),
    "SDJ": ("仙台", "Sendai"),
    "HIJ": ("廣島", "Hiroshima"),
    "SEL": ("首爾", "Seoul"),
    "ICN": ("首爾", "Seoul"),
    "GMP": ("首爾", "Seoul"),
    "PUS": ("釜山", "Busan"),
    "CJU": ("濟州島", "Jeju"),
    "TPE": ("台北", "Taipei"),
    "TSA": ("台北", "Taipei"),
    "KHH": ("高雄", "Kaohsiung"),
    "RMQ": ("台中", "Taichung"),
    "HKG": ("香港", "Hong Kong"),
    "MFM": ("澳門", "Macau"),
    "SIN": ("新加坡", "Singapore"),
    "BKK": ("曼谷", "Bangkok"),
    "DMK": ("曼谷", "Bangkok"),
    "CNX": ("清邁", "Chiang Mai"),
    "HKT": ("普吉島", "Phuket"),
    "KUL": ("吉隆坡", "Kuala Lumpur"),
    "DPS": ("峇里島", "Bali"),
    "HAN": ("河內", "Hanoi"),
    "SGN": ("胡志明市", "Ho Chi Minh City"),
    "DAD": ("峴港", "Da Nang"),
    "MNL": ("馬尼拉", "Manila"),
    "LON": ("倫敦", "London"),
    "LHR": ("倫敦", "London"),
    "LGW": ("倫敦", "London"),
    "STN": ("倫敦", "London"),
    "PAR": ("巴黎", "Paris"),
    "CDG": ("巴黎", "Paris"),
    "ORY": ("巴黎", "Paris"),
    "ROM": ("羅馬", "Rome"),
    "FCO": ("羅馬", "Rome"),
    "MIL": ("米蘭", "Milan"),
    "MXP": ("米蘭", "Milan"),
    "VCE": ("威尼斯", "Venice"),
    "ZRH": ("蘇黎世", "Zurich"),
    "MUC": ("慕尼黑", "Munich"),
    "FRA": ("法蘭克福", "Frankfurt"),
    "BER": ("柏林", "Berlin"),
    "BCN": ("巴塞隆納", "Barcelona"),
    "MAD": ("馬德里", "Madrid"),
    "AMS": ("阿姆斯特丹", "Amsterdam"),
    "VIE": ("維也納", "Vienna"),
    "PRG": ("布拉格", "Prague"),
    "HEL": ("赫爾辛基", "Helsinki"),
    "REK": ("冰島", "Iceland"),
    "KEF": ("冰島", "Iceland"),
    "NYC": ("紐約", "New York"),
    "JFK": ("紐約", "New York"),
    "EWR": ("紐約", "New York"),
    "LGA": ("紐約", "New York"),
    "LAX": ("洛杉磯", "Los Angeles"),
    "SFO": ("舊金山", "San Francisco"),
    "SEA": ("西雅圖", "Seattle"),
    "YVR": ("溫哥華", "Vancouver"),
    "YTO": ("多倫多", "Toronto"),
    "YYZ": ("多倫多", "Toronto"),
    "SYD": ("雪梨", "Sydney"),
    "MEL": ("墨爾本", "Melbourne"),
    "AKL": ("奧克蘭", "Auckland"),
    "DXB": ("杜拜", "Dubai"),
    # 3-letter country code exception
    "USA": ("美國", "USA"),
}

# Specific sub-cities sharing a metropolitan IATA hub (e.g. Kyoto/Nara/Kobe under OSA)
_SPECIFIC_CITY_DISPLAY: Tuple[Tuple[Tuple[str, ...], Tuple[str, str]], ...] = (
    (("京都", "kyoto"), ("京都", "Kyoto")),
    (("奈良", "nara"), ("奈良", "Nara")),
    (("神戶", "神户", "kobe"), ("神戶", "Kobe")),
    (("函館", "hakodate"), ("函館", "Hakodate")),
    (("旭川", "asahikawa"), ("旭川", "Asahikawa")),
    (("小樽", "otaru"), ("小樽", "Otaru")),
    (("富良野", "furano"), ("富良野", "Furano")),
)

_DISPLAY_EXTRA_NOISE_RE = re.compile(r"(?:親子|情侶|閨蜜|畢旅|必去|必吃|懶人包|冬季|夏季|春季|秋季)")


def resolve_iata_to_display_city(destination: Optional[str], locale: str = "zh") -> str:
    """
    Pure in-memory reverse mapping from IATA code (e.g. 'CTS', 'NRT', 'KIX') or trip title
    (e.g. '2026 北海道 5天4夜親子自由行') to a clean localized display city name.
    - English outputs are strictly ASCII city names (never CJK aliases like '沖縄'/'臺北').
    - Unknown 3-letter uppercase IATA codes return '' so bare airport codes never pollute RSS queries.
    """
    clean = (destination or "").strip()
    if not clean:
        return ""

    is_en = bool(locale and str(locale).strip().lower().startswith("en"))
    upper = clean.upper()

    # 1. Exact 3-letter code (IATA airport/city or 3-letter country exception such as USA)
    if _IATA_CODE_RE.fullmatch(upper):
        mapped = _IATA_TO_DISPLAY_CITY.get(upper)
        if mapped:
            return mapped[1] if is_en else mapped[0]
        if clean.isupper():
            return ""
        return clean

    low = clean.lower()

    # 2. Specific sub-cities sharing an IATA hub (e.g. Kyoto/Nara/Kobe inside trip titles)
    for keywords, display_pair in _SPECIFIC_CITY_DISPLAY:
        if any(kw in low for kw in keywords):
            return display_pair[1] if is_en else display_pair[0]

    # 3. Known local city/region keywords in trip titles (e.g. "2026 北海道 5天4夜親子自由行" -> "北海道")
    for keywords, code in _CITY_TO_IATA:
        if any(kw in low for kw in keywords):
            mapped = _IATA_TO_DISPLAY_CITY.get(code)
            if mapped:
                return mapped[1] if is_en else mapped[0]

    # 4. Parenthesized IATA code inside title (e.g. "行程 (CTS)")
    paren = _IATA_IN_TEXT_RE.search(upper)
    if paren:
        mapped = _IATA_TO_DISPLAY_CITY.get(paren.group(1))
        if mapped:
            return mapped[1] if is_en else mapped[0]

    # 5. Non-IATA trip title / city outside local map -> clean title noise
    cleaned = _TITLE_NOISE_RE.sub(" ", clean)
    cleaned = _DISPLAY_EXTRA_NOISE_RE.sub(" ", cleaned)
    cleaned = re.sub(r"[\s\-_/·・,，。!?()（）【】]+", " ", cleaned).strip()
    if _IATA_CODE_RE.fullmatch(cleaned.upper()) and cleaned.isupper():
        mapped = _IATA_TO_DISPLAY_CITY.get(cleaned.upper())
        return (mapped[1] if is_en else mapped[0]) if mapped else ""
    return cleaned[:40]

_IATA_CACHE_MAX = 256
_IATA_CACHE_TTL_SEC = 24 * 3600.0
_PRICE_CACHE_MAX = 256
_PRICE_CACHE_TTL_SEC = 3600.0

_IATA_CACHE: "OrderedDict[str, Tuple[float, str]]" = OrderedDict()
_PRICE_CACHE: "OrderedDict[str, Tuple[float, List[Dict[str, Any]]]]" = OrderedDict()
_FLIGHT_CLIENT: Optional[httpx.AsyncClient] = None


def get_flight_pricing_client() -> httpx.AsyncClient:
    """Return shared AsyncClient pool for Travelpayouts pricing & places2."""
    global _FLIGHT_CLIENT
    if _FLIGHT_CLIENT is None or _FLIGHT_CLIENT.is_closed:
        _FLIGHT_CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(4.0, connect=2.0),
            limits=httpx.Limits(max_connections=30, max_keepalive_connections=10),
            headers={"User-Agent": TABIJI_USER_AGENT, "Accept": "application/json"},
        )
    return _FLIGHT_CLIENT


async def close_flight_pricing_client() -> None:
    """Close shared AsyncClient pool on FastAPI lifespan shutdown."""
    global _FLIGHT_CLIENT
    if _FLIGHT_CLIENT is not None and not _FLIGHT_CLIENT.is_closed:
        await _FLIGHT_CLIENT.aclose()
    _FLIGHT_CLIENT = None


def __reset_flight_pricing_for_testing() -> None:
    """Reset module-level IATA and flight price caches between unit tests."""
    _IATA_CACHE.clear()
    _PRICE_CACHE.clear()


def _lru_get(cache: OrderedDict, key: str) -> Any:
    entry = cache.get(key)
    if entry is None:
        return None
    expires_at, val = entry
    if time.monotonic() >= expires_at:
        cache.pop(key, None)
        return None
    cache.move_to_end(key)
    return val


def _lru_set(cache: OrderedDict, key: str, value: Any, ttl: float, max_size: int) -> None:
    cache[key] = (time.monotonic() + ttl, value)
    cache.move_to_end(key)
    while len(cache) > max_size:
        cache.popitem(last=False)


def _match_local_iata(raw: str) -> str:
    clean = (raw or "").strip()
    if not clean:
        return ""
    upper = clean.upper()
    if _IATA_CODE_RE.fullmatch(upper):
        return upper
    paren = _IATA_IN_TEXT_RE.search(upper)
    if paren:
        return paren.group(1)

    low = clean.lower()
    for keywords, code in _CITY_TO_IATA:
        if any(kw in low for kw in keywords):
            return code
    return ""


async def resolve_iata_code(raw_value: Optional[str], locale: str = "zh", timeout: float = 1.2) -> str:
    """
    Resolve an IATA code (e.g. 'NRT', 'TYO') from a raw IATA string, city name, or trip title
    such as '2026 東京家族之旅'. Uses fast local map -> cached places2 zero-key lookup.
    """
    clean = (raw_value or "").strip()
    if not clean:
        return ""

    fast_hit = _match_local_iata(clean)
    if fast_hit:
        return fast_hit

    # Clean noisy trip titles before querying places2
    term = _TITLE_NOISE_RE.sub(" ", clean)
    term = re.sub(r"[\s\-_/·・,，。!?()（）【】]+", " ", term).strip()
    if not term or len(term) < 2:
        return ""

    norm_locale = "en" if str(locale or "").strip().lower().startswith("en") else "zh"
    cache_key = f"{term.lower()}|{norm_locale}"
    cached = _lru_get(_IATA_CACHE, cache_key)
    if cached is not None:
        return cached

    try:
        client = get_flight_pricing_client()
        resp = await asyncio.wait_for(
            client.get(
                TP_PLACES2_URL,
                params={
                    "term": term[:50],
                    "locale": norm_locale,
                    "types[]": ["city", "airport"],
                },
            ),
            timeout=timeout,
        )
        if resp.status_code == 200:
            items = resp.json()
            if isinstance(items, list):
                for item in items[:5]:
                    if isinstance(item, dict):
                        code = str(item.get("code") or "").strip().upper()
                        if _IATA_CODE_RE.fullmatch(code):
                            _lru_set(_IATA_CACHE, cache_key, code, _IATA_CACHE_TTL_SEC, _IATA_CACHE_MAX)
                            return code
    except Exception as e:
        logger.debug(f"[FlightPricing] places2 IATA lookup skipped for '{term}': {e}")

    return ""


def extract_route_from_itinerary(itinerary: Optional[Dict[str, Any]]) -> Tuple[str, str, Optional[str]]:
    """
    Extract (origin_hint, destination_hint, departure_date) from itinerary metadata.
    Prioritizes explicit flight_info.outbound[0] IATA codes, falling back to destination/title.
    """
    if not isinstance(itinerary, dict):
        return "", "", None

    origin = ""
    destination = ""
    dep_date: Optional[str] = None

    flight_info = itinerary.get("flight_info")
    if isinstance(flight_info, dict):
        outbound = flight_info.get("outbound")
        first_leg: Dict[str, Any] = {}
        if isinstance(outbound, list) and outbound and isinstance(outbound[0], dict):
            first_leg = outbound[0]
        elif isinstance(outbound, dict):
            first_leg = outbound
        origin = str(first_leg.get("dep_airport") or first_leg.get("origin") or "").strip()
        destination = str(first_leg.get("arr_airport") or first_leg.get("destination") or "").strip()
        raw_dep = first_leg.get("dep_date") or first_leg.get("departure_at") or first_leg.get("date")
        if isinstance(raw_dep, str) and raw_dep.strip():
            dep_date = raw_dep.strip().split("T")[0].replace("/", "-")

    if not dep_date:
        start_date = itinerary.get("start_date")
        if isinstance(start_date, str) and start_date.strip():
            dep_date = start_date.strip().split("T")[0].replace("/", "-")

    if not destination:
        destination = str(itinerary.get("destination") or itinerary.get("title") or "").strip()

    if not origin and destination:
        origin = "TPE"

    return origin, destination, dep_date


async def fetch_flight_prices(
    origin_iata: str,
    dest_iata: str,
    *,
    departure_at: Optional[str] = None,
    currency: str = "TWD",
    limit: int = 3,
    token: Optional[str] = None,
    timeout: float = 1.5,
) -> List[Dict[str, Any]]:
    """Fetch cached live flight prices from Travelpayouts within a bounded timeout."""
    api_token = (token if token is not None else os.getenv("TP_API_TOKEN", "")).strip()
    if not api_token:
        return []

    orig = (origin_iata or "").strip().upper()
    dest = (dest_iata or "").strip().upper()
    if not _IATA_CODE_RE.fullmatch(orig) or not _IATA_CODE_RE.fullmatch(dest) or orig == dest:
        return []

    clean_date = (departure_at or "").strip().split("T")[0].replace("/", "-") or None
    cur = (currency or "TWD").strip().upper()
    cache_key = f"{orig}|{dest}|{clean_date or ''}|{cur}|{limit}"
    cached = _lru_get(_PRICE_CACHE, cache_key)
    if cached is not None:
        return [dict(item) for item in cached]

    params: Dict[str, Any] = {
        "origin": orig,
        "destination": dest,
        "currency": cur,
        "sorting": "price",
        "limit": limit,
        "unique": "false",
    }
    if clean_date:
        params["departure_at"] = clean_date

    client = get_flight_pricing_client()
    try:
        resp = await asyncio.wait_for(
            client.get(
                f"{TP_BASE}/aviasales/v3/prices_for_dates",
                params=params,
                headers={"X-Access-Token": api_token},
            ),
            timeout=timeout,
        )
        prices: List[Dict[str, Any]] = []
        if resp.status_code == 200:
            raw_data = resp.json().get("data", [])
            if isinstance(raw_data, list):
                prices = [p for p in raw_data if isinstance(p, dict)]

        # General route fallback if specific date returned empty and budget permits
        if not prices and clean_date:
            fb_params = {k: v for k, v in params.items() if k != "departure_at"}
            fb_resp = await asyncio.wait_for(
                client.get(
                    f"{TP_BASE}/aviasales/v3/prices_for_dates",
                    params=fb_params,
                    headers={"X-Access-Token": api_token},
                ),
                timeout=max(0.5, timeout * 0.6),
            )
            if fb_resp.status_code == 200:
                raw_fb = fb_resp.json().get("data", [])
                if isinstance(raw_fb, list):
                    prices = [p for p in raw_fb if isinstance(p, dict)]

        if prices:
            trimmed = prices[:limit]
            _lru_set(_PRICE_CACHE, cache_key, trimmed, _PRICE_CACHE_TTL_SEC, _PRICE_CACHE_MAX)
            return [dict(item) for item in trimmed]
    except Exception as e:
        logger.debug(f"[FlightPricing] Live price fetch skipped ({orig}->{dest}): {e}")

    return []


async def build_flight_price_context(
    *,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    itinerary: Optional[Dict[str, Any]] = None,
    departure_at: Optional[str] = None,
    locale: str = "zh",
    token: Optional[str] = None,
    marker: Optional[str] = None,
    include_marker: bool = False,
    timeout: float = 1.5,
) -> str:
    """
    Unified live flight price context builder for both Deep Research and Streaming Chat.
    Resolves city/title strings to IATA via local map or places2, then queries cached fares.
    """
    api_token = (token if token is not None else os.getenv("TP_API_TOKEN", "")).strip()
    if not api_token:
        return ""

    orig_hint = (origin or "").strip()
    dest_hint = (destination or "").strip()
    dep_hint = departure_at

    if itinerary is not None:
        it_orig, it_dest, it_dep = extract_route_from_itinerary(itinerary)
        if not orig_hint:
            orig_hint = it_orig
        if not dest_hint:
            dest_hint = it_dest
        if not dep_hint:
            dep_hint = it_dep

    if not dest_hint:
        return ""
    if not orig_hint:
        orig_hint = "TPE"

    deadline = time.monotonic() + max(0.4, timeout)
    orig_iata = await resolve_iata_code(orig_hint, locale=locale, timeout=min(0.6, max(0.2, deadline - time.monotonic())))
    dest_iata = await resolve_iata_code(dest_hint, locale=locale, timeout=min(0.6, max(0.2, deadline - time.monotonic())))
    if not orig_iata or not dest_iata or orig_iata == dest_iata:
        return ""

    remaining = deadline - time.monotonic()
    if remaining <= 0.15:
        return ""

    prices = await fetch_flight_prices(
        orig_iata,
        dest_iata,
        departure_at=dep_hint,
        currency="TWD",
        limit=3,
        token=api_token,
        timeout=remaining,
    )
    if not prices:
        return ""

    is_en = bool(locale and str(locale).strip().lower().startswith("en"))
    tp_marker = (marker if marker is not None else os.getenv("NEXT_PUBLIC_TP_MARKER", os.getenv("TP_MARKER", "602410"))).strip()

    if include_marker:
        if is_en:
            lines = [f"[Travelpayouts Live Flight Fare Reference ({orig_iata} -> {dest_iata})]:"]
            for p in prices[:3]:
                price = p.get("price")
                airline = p.get("airline", "Airline")
                dep = p.get("departure_at", "")
                price_str = f"NT${price:,}" if isinstance(price, (int, float)) else f"NT${price}"
                lines.append(f"- {airline} Departure: {dep} Lowest est. price ~ {price_str}")
            lines.append(f"(Affiliate tracking marker: {tp_marker})")
            return "\n".join(lines)

        lines = [f"【Travelpayouts 即時票價參考 ({orig_iata} ➔ {dest_iata})】:"]
        for p in prices[:3]:
            price = p.get("price")
            airline = p.get("airline", "航空")
            dep = p.get("departure_at", "")
            price_str = f"NT${price:,}" if isinstance(price, (int, float)) else f"NT${price}"
            lines.append(f"- {airline} 出發日:{dep} 最低票價約 {price_str}")
        lines.append(f"（分潤標記追蹤碼: {tp_marker}）")
        return "\n".join(lines)

    if is_en:
        lines = [f"\n\n💰 **Live Flight Fare Reference ({orig_iata}->{dest_iata}, TWD):**"]
        for p in prices[:3]:
            transfers = p.get("transfers", 0)
            transfer_str = "Direct" if transfers == 0 else f"{transfers} stop(s)"
            price = p.get("price", "?")
            price_str = f"{price:,}" if isinstance(price, (int, float)) else str(price)
            lines.append(
                f"- {str(p.get('departure_at', '?'))[:10]} | "
                f"{p.get('airline', '?')} | "
                f"TWD {price_str} | {transfer_str}"
            )
        lines.append("(Live data via Travelpayouts, for reference only)")
        return "\n".join(lines)

    lines = [f"\n\n💰 **即時機票參考價格 ({orig_iata}→{dest_iata}, TWD):**"]
    for p in prices[:3]:
        transfers = p.get("transfers", 0)
        transfer_str = "直飛" if transfers == 0 else f"{transfers}轉"
        price = p.get("price", "?")
        price_str = f"{price:,}" if isinstance(price, (int, float)) else str(price)
        lines.append(
            f"- {str(p.get('departure_at', '?'))[:10]} | "
            f"{p.get('airline', '?')} | "
            f"TWD {price_str} | {transfer_str}"
        )
    lines.append("（以上為 Travelpayouts 即時數據，僅供參考）")
    return "\n".join(lines)
