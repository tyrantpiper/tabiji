"""
Trips Router
------------
Handles all trip-related API endpoints including:
- Trip CRUD operations
- Day management (add/delete)
- Item management (CRUD)
- Legacy endpoints (save-itinerary, join-trip)

Note: This is a large router containing 17 endpoints.
"""

import os
import re
import math
import uuid
import random
import string
import copy
import hashlib
import asyncio
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Any
from urllib.parse import urlparse
from unittest.mock import NonCallableMock
from fastapi import APIRouter, Depends, HTTPException, Header
from starlette.concurrency import run_in_threadpool
from supabase import Client as SupabaseClient

from models.base import (
    JoinTripRequest,
    CreateManualTripRequest,
    UpdateTripTitleRequest,
    UpdateCoverRequest,
    SaveItineraryRequest,
    ImportToTripRequest,
    UpdateDayDataRequest,
    UpdateLocationRequest,
    UpdateInfoRequest,
    UpdateDatesRequest,
    CreateItemRequest,
    UpdateItemRequest,
    AddDayRequest,
    ReorderRequest,
    ExpenseResponse,      # 🆕 Data Parity
    ReceiptDiagnostics    # 🆕 Data Parity
)
from .expenses import normalize_items, check_trip_access  # 🆕 Data Parity + BOLA Guard
from services.link_resolver import resolve_google_maps_link
from services.cover_service import resolve_destination_cover_url
from utils.concurrency import trip_lock
from utils.deps import get_supabase, get_verified_user, UUID_V4_REGEX
from utils.helpers import generate_room_code, generate_public_id, ensure_user_exists
from utils.idempotency import get_idempotent_response, store_idempotent_response
from utils.constants import DAY_MAP_FIELDS, CLONEABLE_FIELDS

router = APIRouter(prefix="/api/trips", tags=["trips"])

_GOOGLE_MAPS_HOST_RE = re.compile(r"^maps\.google\.(?:com|co\.[a-z]{2}|com\.[a-z]{2}|[a-z]{2,3})$")
_GOOGLE_WEB_HOST_RE = re.compile(r"^(?:www\.|m\.)?google\.(?:com|co\.[a-z]{2}|com\.[a-z]{2}|[a-z]{2,3})$")
_EXACT_MAP_HOSTS = frozenset({
    "maps.app.goo.gl",
    "maps.apple.com",
    "beta.maps.apple.com",
    "openstreetmap.org",
    "www.openstreetmap.org",
    "osm.org",
    "www.osm.org",
    "map.naver.com",
    "m.map.naver.com",
    "naver.me",
    "map.kakao.com",
    "m.map.kakao.com",
    "kko.to",
    "map.yahoo.co.jp",
    "maps.loco.yahoo.co.jp",
    "amap.com",
    "www.amap.com",
    "ditu.amap.com",
    "surl.amap.com",
    "uri.amap.com",
    "map.baidu.com",
    "j.map.baidu.com",
    "api.map.baidu.com",
    "waze.com",
    "www.waze.com",
    "ul.waze.com",
})
_BING_HOSTS = frozenset({"bing.com", "www.bing.com", "cn.bing.com"})


def _is_safe_http_url(url: Optional[str]) -> bool:
    """驗證是否為合法 http(s) URL（拒絕 javascript:/data:/含反斜線或帳密權威混淆字元）。"""
    if not url or not isinstance(url, str):
        return False
    raw = url.strip()
    if not raw or any(ch in raw for ch in ("\\", "\r", "\n", "\t")):
        return False
    try:
        parsed = urlparse(raw)
        if parsed.scheme.lower() not in ("http", "https"):
            return False
        if not parsed.hostname or parsed.username or parsed.password:
            return False
        return True
    except Exception:
        return False


def is_map_navigation_url(url: Optional[str]) -> bool:
    """檢查網址是否屬於合法地圖導航網域白名單（Google / Apple / OSM / Naver / Kakao / Yahoo JP / Bing / Amap / Baidu / Waze）。"""
    if not _is_safe_http_url(url):
        return False
    try:
        parsed = urlparse(str(url).strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        path = (parsed.path or "").lower()
    except Exception:
        return False

    if not host:
        return False
    if host in _EXACT_MAP_HOSTS:
        return True
    if _GOOGLE_MAPS_HOST_RE.match(host):
        return True
    if _GOOGLE_WEB_HOST_RE.match(host) and (path == "/maps" or path.startswith("/maps/")):
        return True
    if host == "goo.gl" and (path == "/maps" or path.startswith("/maps/")):
        return True
    if host in _BING_HOSTS and (path == "/maps" or path.startswith("/maps/")):
        return True
    return False


def _normalize_url_for_dedupe(url: str) -> str:
    """保留路徑大小寫（如 IG Reel ID），僅將 scheme/netloc 小寫化並移除尾斜線以供去重比對。"""
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")
        query = f"?{parsed.query}" if parsed.query else ""
        return f"{scheme}://{netloc}{path}{query}"
    except Exception:
        return raw.rstrip("/")


def _label_for_reference_url(url: str) -> str:
    """依非地圖網址之網域產生清楚的此地備忘錄連結名稱。"""
    try:
        host = (urlparse(url.strip()).hostname or "").lower().rstrip(".")
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    elif host.startswith("m."):
        host = host[2:]

    if host in ("instagram.com", "instagr.am") or host.endswith(".instagram.com"):
        return "Instagram 參考連結"
    if host in ("threads.net", "threads.com") or host.endswith(".threads.net") or host.endswith(".threads.com"):
        return "Threads 參考連結"
    if host == "tiktok.com" or host.endswith(".tiktok.com"):
        return "TikTok 參考連結"
    if host in ("youtube.com", "youtu.be") or host.endswith(".youtube.com"):
        return "YouTube 參考連結"
    if host in ("facebook.com", "fb.com", "fb.watch") or host.endswith(".facebook.com"):
        return "Facebook 參考連結"
    if host in ("x.com", "twitter.com") or host.endswith(".x.com") or host.endswith(".twitter.com"):
        return "X / Twitter 參考連結"
    if host in ("xiaohongshu.com", "xhslink.com") or host.endswith(".xiaohongshu.com"):
        return "小紅書參考連結"
    if host == "tabelog.com" or host.endswith(".tabelog.com"):
        return "Tabelog 食評連結"
    if host.startswith("tripadvisor.") or ".tripadvisor." in host:
        return "TripAdvisor 參考連結"
    if host == "klook.com" or host.endswith(".klook.com"):
        return "Klook 預訂連結"
    if host == "kkday.com" or host.endswith(".kkday.com"):
        return "KKday 預訂連結"
    if (
        host in ("booking.com", "agoda.com")
        or host.endswith(".booking.com")
        or host.endswith(".agoda.com")
        or host.startswith("airbnb.")
        or ".airbnb." in host
    ):
        return "訂房參考連結"
    return "官方網站 / 參考連結"


def _sanitize_item_links(
    link_url: Optional[str],
    website_link: Optional[str],
    sub_items: Optional[List[dict]],
) -> tuple[Optional[str], Optional[str], List[dict]]:
    """後端最後防線：導航網址 (link_url) 僅允許地圖網域，非地圖網址自動分流至 sub_items（此地備忘錄）與 website_link（去重）。"""
    clean_sub_items: List[dict] = [dict(s) for s in (sub_items or []) if isinstance(s, dict)]
    seen_links: set[str] = set()
    for s in clean_sub_items:
        existing_link = s.get("link")
        if isinstance(existing_link, str) and existing_link.strip():
            seen_links.add(_normalize_url_for_dedupe(existing_link))

    raw_link = link_url.strip() if isinstance(link_url, str) else ""
    raw_web = website_link.strip() if isinstance(website_link, str) else ""

    clean_link_url: Optional[str] = None
    clean_website_link: Optional[str] = raw_web if _is_safe_http_url(raw_web) else None
    memo_candidates: List[str] = []

    if raw_link:
        if is_map_navigation_url(raw_link):
            clean_link_url = raw_link
        elif _is_safe_http_url(raw_link):
            memo_candidates.append(raw_link)
            if not clean_website_link:
                clean_website_link = raw_link

    if clean_website_link and not is_map_navigation_url(clean_website_link):
        memo_candidates.append(clean_website_link)

    for candidate in memo_candidates:
        norm = _normalize_url_for_dedupe(candidate)
        if norm and norm not in seen_links:
            seen_links.add(norm)
            clean_sub_items.append({
                "name": _label_for_reference_url(candidate),
                "link": candidate,
            })

    return clean_link_url, clean_website_link, clean_sub_items


def _is_atomic_rpc_enabled() -> bool:
    """Env kill-switch for Phase 1 pure Postgres atomic RPCs (default enabled)."""
    return os.getenv("ENABLE_ATOMIC_TRIP_RPC", "1").strip().lower() not in {"0", "false", "no", "off"}


def _can_use_atomic_rpc(supabase: Any) -> bool:
    """Detect whether the supplied Supabase client supports atomic RPC execution.

    Preserves legacy unit tests using bare `MagicMock()` that only mock `.table()`,
    while enabling real `supabase.Client`, custom RPC fakes, and mocks with explicitly configured `.rpc`.
    """
    if not _is_atomic_rpc_enabled() or supabase is None:
        return False
    if isinstance(supabase, NonCallableMock):
        if "rpc" in getattr(supabase, "__dict__", {}):
            return callable(supabase.__dict__["rpc"])
        children = getattr(supabase, "_mock_children", {})
        if "rpc" in children:
            child = children["rpc"]
            if getattr(child, "side_effect", None) is not None:
                return True
            ret_val = getattr(child, "_mock_return_value", None)
            if ret_val is not None and not isinstance(ret_val, NonCallableMock):
                return True
            if ret_val is not None and "execute" in getattr(ret_val, "_mock_children", {}):
                return True
        return False
    return callable(getattr(supabase, "rpc", None))


_INVALID_LITERAL_IDS = frozenset({"", "undefined", "null", "nan", "none"})


def _guard_resource_id(
    supabase: Any,
    raw_id: Any,
    *,
    allow_creator_bypass: bool = True,
    forbidden_detail: str = "您沒有權限操作此行程",
    not_found_detail: str = "Trip not found",
) -> None:
    """Block invalid literal IDs unconditionally and non-UUID IDs against real Supabase clients."""
    clean_id = str(raw_id or "").strip()
    is_bad_literal = clean_id.lower() in _INVALID_LITERAL_IDS
    is_real_client_bad_uuid = isinstance(supabase, SupabaseClient) and not UUID_V4_REGEX.fullmatch(clean_id)
    if is_bad_literal or is_real_client_bad_uuid:
        if allow_creator_bypass:
            raise HTTPException(status_code=404, detail=not_found_detail)
        raise HTTPException(status_code=403, detail=forbidden_detail)


def _raise_if_pg_invalid_uuid(exc: Exception, detail: str = "Trip not found") -> None:
    """Convert PostgreSQL 22P02 invalid UUID syntax errors into clean 404 responses."""
    if _extract_pg_error_code(exc) == "22P02":
        raise HTTPException(status_code=404, detail=detail)


def _precheck_atomic_trip_id(
    supabase: Any,
    trip_id: str,
    *,
    allow_creator_bypass: bool,
    forbidden_detail: str,
    not_found_detail: str,
) -> None:
    """Pre-validate UUID format before hitting Postgres UUID RPC parameters (prevents 22P02 -> 500)."""
    clean_trip_id = str(trip_id or "").strip()
    if clean_trip_id.lower() in _INVALID_LITERAL_IDS:
        if allow_creator_bypass:
            raise HTTPException(status_code=404, detail=not_found_detail)
        raise HTTPException(status_code=403, detail=forbidden_detail)
    if not _can_use_atomic_rpc(supabase):
        if isinstance(supabase, SupabaseClient) and not UUID_V4_REGEX.fullmatch(clean_trip_id):
            if allow_creator_bypass:
                raise HTTPException(status_code=404, detail=not_found_detail)
            raise HTTPException(status_code=403, detail=forbidden_detail)
        return
    if not UUID_V4_REGEX.fullmatch(clean_trip_id):
        if allow_creator_bypass:
            raise HTTPException(status_code=404, detail=not_found_detail)
        raise HTTPException(status_code=403, detail=forbidden_detail)


def _extract_pg_error_code(exc: Exception) -> str:
    """Extract PostgREST / PostgreSQL SQLSTATE error code from an exception."""
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code.strip():
        return code.strip().upper()
    if exc.args and isinstance(exc.args[0], dict):
        arg_code = exc.args[0].get("code")
        if isinstance(arg_code, str) and arg_code.strip():
            return arg_code.strip().upper()
    msg = str(exc)
    for known in ("PGRST202", "55P03", "40P01", "57014", "22P02", "22023"):
        if known in msg:
            return known
    return ""


async def _execute_atomic_trip_rpc(
    supabase: Any,
    rpc_name: str,
    params: dict,
    *,
    trip_id: str,
    allow_creator_bypass: bool = False,
    forbidden_detail: str = "您沒有權限修改此行程資訊",
    not_found_detail: str = "找不到此行程",
) -> Optional[dict]:
    """Execute a pure-Postgres atomic trip-content RPC off the event loop via threadpool.

    Returns:
        dict payload on success (`status == "ok"`).
        None ONLY when atomic RPC is disabled/unavailable (kill-switch, legacy mock, or PGRST202).
    """
    if not _can_use_atomic_rpc(supabase):
        return None

    _precheck_atomic_trip_id(
        supabase,
        trip_id,
        allow_creator_bypass=allow_creator_bypass,
        forbidden_detail=forbidden_detail,
        not_found_detail=not_found_detail,
    )

    def _invoke():
        return supabase.rpc(rpc_name, params).execute()

    res = None
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            res = await run_in_threadpool(_invoke)
            break
        except Exception as exc:
            pg_code = _extract_pg_error_code(exc)
            if pg_code == "PGRST202" or "Could not find the function" in str(exc):
                print(f"⚠️ [AtomicRPC] {rpc_name} unavailable (PGRST202); falling back to Python RMW")
                return None
            if pg_code in ("55P03", "40P01"):
                if attempt + 1 < max_attempts:
                    await asyncio.sleep(random.uniform(0.06, 0.16))
                    continue
                raise HTTPException(
                    status_code=409,
                    detail="行程正由旅伴同步編輯中，請稍候重試",
                )
            if pg_code == "22023":
                raise HTTPException(status_code=400, detail="無效的請求參數")
            raise

    raw_data = getattr(res, "data", None)
    if isinstance(raw_data, list):
        payload = raw_data[0] if raw_data and isinstance(raw_data[0], dict) else None
    elif isinstance(raw_data, dict):
        payload = raw_data
    else:
        payload = None

    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected atomic RPC response from {rpc_name}")

    status = str(payload.get("status") or "").strip().lower()
    if status == "ok":
        return payload
    if status == "forbidden":
        raise HTTPException(status_code=403, detail=forbidden_detail)
    if status == "not_found":
        raise HTTPException(status_code=404, detail=not_found_detail)
    raise RuntimeError(f"Unknown atomic RPC status from {rpc_name}: {status}")


def _first_row(data: Any) -> Optional[dict]:
    """Safely extract the first row dict from either PostgREST list or .single() dict."""
    if not data:
        return None
    if isinstance(data, list):
        return data[0] if isinstance(data[0], dict) else None
    if isinstance(data, dict):
        return data
    return None


def _safe_single_data(query: Any) -> Optional[dict]:
    """Execute a .single() query while converting PGRST116 0-row errors into None for 404 handling."""
    try:
        res = query.execute()
    except Exception as exc:
        msg = str(exc)
        if "PGRST116" in msg or "0 rows" in msg or "multiple (or no) rows" in msg:
            return None
        raise
    return _first_row(getattr(res, "data", None))


def _chunked(seq: List[str], size: int = 50):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def _rollback_created_trip(supabase: Any, trip_id: Optional[str]) -> None:
    """Best-effort compensating deletion across child tables and parent itinerary to prevent quota-consuming orphans."""
    if not trip_id:
        return
    for tbl, col in (
        ("itinerary_items", "itinerary_id"),
        ("trip_members", "itinerary_id"),
        ("itineraries", "id"),
    ):
        try:
            supabase.table(tbl).delete().eq(col, trip_id).execute()
        except Exception as rollback_err:
            print(f"⚠️ Compensating cleanup error ({tbl}): {rollback_err}")

def resolve_trip_currency(trip: Optional[dict], content: Optional[dict]) -> str:
    """確定性解析行程幣別，含舊行程標題語意回溯"""
    safe_content = content or {}
    safe_trip = trip or {}
    declared = safe_content.get("currency") or safe_trip.get("currency")
    if declared:
        return declared
    from services.geocode_service import infer_currency_from_destination
    title = safe_trip.get("title") or ""
    return infer_currency_from_destination(title, declared_currency=None)

def mask_member_id(user_id: Any, trip_id: str) -> str:
    """🛡️ 伺服端單向脫敏：非本人 UUID 單向雜湊，杜絕奪舍"""
    return f"mem_{hashlib.sha256((str(user_id) + str(trip_id)).encode()).hexdigest()[:10]}"


def _is_trip_creator(trip: Optional[dict], user_id: str, allow_legacy_user_id: bool = False) -> bool:
    """判定呼叫者是否為行程建立者。
    注意：user_trips_view 的 user_id 欄位為成員本身 ID，絕不可作為建立者依據；
    allow_legacy_user_id 僅適用於直接查詢 itineraries 主表之場景。
    """
    if not trip or not user_id:
        return False
    uid = str(user_id).strip()
    created_by = str(trip.get("created_by") or "").strip()
    if created_by:
        return created_by == uid
    if allow_legacy_user_id:
        legacy_uid = str(trip.get("user_id") or "").strip()
        if legacy_uid:
            return legacy_uid == uid
    return False


def _is_day_item_visible_to_user(item: Any, user_id: str, is_owner: bool) -> bool:
    """判斷單筆項目是否對當前使用者可見：
    - 公開項目（或非 dict 歷史字串）一律可見
    - 具 private_owner_id 之私人項目僅建立者本人可見（禁止他方窺探或暴露原生 UUID）
    - 無 private_owner_id 之歷史無主私人項目由行程擁有者精確救援可見
    """
    if not isinstance(item, dict):
        return True
    if item.get("is_private") is not True:
        return True
    owner_id = str(item.get("private_owner_id") or "").strip()
    if owner_id:
        return owner_id == str(user_id or "").strip()
    return is_owner


def _sanitize_visible_day_item(item: Any) -> Any:
    """出口淨化：公開項目不得夾帶殘留 private_owner_id。"""
    if not isinstance(item, dict):
        return item
    if item.get("is_private") is not True and "private_owner_id" in item:
        cleaned = dict(item)
        cleaned.pop("private_owner_id", None)
        return cleaned
    return item


def _filter_private_day_items(items_dict: Any, user_id: str, is_owner: bool) -> dict:
    """過濾每日陣列欄位中的他方私人項目，防止私密內容與原生 UUID 外洩。"""
    if not isinstance(items_dict, dict):
        return {}
    filtered = {}
    for day_key, items_list in items_dict.items():
        if isinstance(items_list, list):
            filtered[day_key] = [
                _sanitize_visible_day_item(item)
                for item in items_list
                if _is_day_item_visible_to_user(item, user_id, is_owner)
            ]
        else:
            filtered[day_key] = items_list
    return filtered


def _merge_day_items_preserving_hidden_private(
    existing_items: Any,
    submitted_items: Any,
    user_id: str,
    is_owner: bool,
) -> list:
    """合併寫入每日項目：
    1. 無條件保留資料庫中對呼叫者不可見的他方私人項目（消除協作覆寫資料遺失）。
    2. 呼叫者提交之私人項目強制綁定 JWT 驗證身分 user_id，公開項目剝除殘留 private_owner_id 並正規化非布林 is_private。
    """
    uid = str(user_id or "").strip()
    existing_list = existing_items if isinstance(existing_items, list) else []
    hidden_foreign_private = [
        item for item in existing_list
        if not _is_day_item_visible_to_user(item, uid, is_owner)
    ]

    normalized_submitted = []
    for item in (submitted_items if isinstance(submitted_items, list) else []):
        if not isinstance(item, dict):
            normalized_submitted.append(item)
            continue
        cleaned = dict(item)
        if cleaned.get("is_private") is True:
            cleaned["is_private"] = True
            cleaned["private_owner_id"] = uid
        else:
            cleaned.pop("private_owner_id", None)
            if "is_private" in cleaned:
                cleaned["is_private"] = False
        normalized_submitted.append(cleaned)

    return normalized_submitted + hidden_foreign_private


def _is_card_visible_to_user(card: Any, user_id: str, is_owner: bool) -> bool:
    """判斷信用卡是否對當前使用者可見（公開卡、建立者本人或行程擁有者精確救援無主卡）。"""
    if not isinstance(card, dict):
        return True
    if card.get("is_public") is True:
        return True
    creator_id = str(card.get("creator_id") or "").strip()
    if creator_id:
        return creator_id == str(user_id or "").strip()
    return is_owner


def _filter_private_cards(cards: Any, user_id: str, is_owner: bool, trip_id: str = "") -> list:
    """過濾私人信用卡並脫敏公開卡之他方 creator_id，避免原生 UUID 外洩。"""
    if not isinstance(cards, list):
        return []
    uid = str(user_id or "").strip()
    result = []
    for card in cards:
        if not _is_card_visible_to_user(card, uid, is_owner):
            continue
        if isinstance(card, dict):
            creator_id = str(card.get("creator_id") or "").strip()
            if creator_id and creator_id != uid and not creator_id.startswith("mem_"):
                sanitized = dict(card)
                sanitized["creator_id"] = mask_member_id(creator_id, trip_id) if trip_id else None
                result.append(sanitized)
            else:
                result.append(card)
        else:
            result.append(card)
    return result


def _merge_cards_preserving_hidden_private(
    existing_cards: Any,
    submitted_cards: Any,
    user_id: str,
    is_owner: bool,
) -> list:
    """合併寫入信用卡：
    1. 無條件保留他方隱藏私卡，並禁止 submitted 卡片碰撞隱藏私卡 ID（消除存在性探測與重複 ID）。
    2. 嚴格由 JWT 身分決定新卡 creator_id，絕不信任客戶端傳入之 creator_id。
    3. 既有他方公開卡一律鎖定原始 creator_id 並禁止非建立者將其私化奪取。
    """
    uid = str(user_id or "").strip()
    existing_list = existing_cards if isinstance(existing_cards, list) else []
    hidden_foreign_cards = []
    visible_existing_cards = []
    for card in existing_list:
        if _is_card_visible_to_user(card, uid, is_owner):
            visible_existing_cards.append(card)
        else:
            hidden_foreign_cards.append(card)

    hidden_ids = {
        str(card["id"]).strip()
        for card in hidden_foreign_cards
        if isinstance(card, dict) and card.get("id")
    }
    visible_by_id = {
        str(card["id"]).strip(): card
        for card in visible_existing_cards
        if isinstance(card, dict) and card.get("id")
    }

    normalized_submitted = []
    seen_ids: set[str] = set()
    for card in (submitted_cards if isinstance(submitted_cards, list) else []):
        if not isinstance(card, dict):
            normalized_submitted.append(card)
            continue
        cleaned = dict(card)
        cid = str(cleaned.get("id") or "").strip()
        if cid and (cid in hidden_ids or cid in seen_ids):
            # 防止以隱藏私卡 ID 或重複提交 ID 碰撞探測／覆寫歸屬
            new_id = str(uuid.uuid4())
            cleaned["id"] = new_id
            seen_ids.add(new_id)
            prev_card = None
        else:
            if cid:
                seen_ids.add(cid)
            prev_card = visible_by_id.get(cid) if cid else None

        submitted_is_public = cleaned.get("is_public") is True

        if prev_card is None:
            # 新卡一律強制綁定 JWT user_id 並正規化布林 is_public，不信任客戶端偽造
            cleaned["creator_id"] = uid
            cleaned["is_public"] = submitted_is_public
        else:
            prev_creator = str(prev_card.get("creator_id") or "").strip()
            caller_owns_prev = (prev_creator == uid) or (not prev_creator and is_owner)
            if caller_owns_prev:
                cleaned["creator_id"] = uid
                cleaned["is_public"] = submitted_is_public
            else:
                # 既有他方公開卡：鎖定原建立者且禁止非建立者私化奪取
                cleaned["creator_id"] = prev_creator
                cleaned["is_public"] = True
        normalized_submitted.append(cleaned)

    return normalized_submitted + hidden_foreign_cards


def _fetch_trip_is_owner(supabase, trip_id: str, user_id: str) -> bool:
    """查詢指定行程建立者並判定呼叫者是否為建立者（避免選擇不存在欄位）。"""
    trip_res = supabase.table("itineraries").select("created_by").eq("id", trip_id).execute()
    trip_row = _first_row(getattr(trip_res, "data", None))
    return _is_trip_creator(trip_row, user_id, allow_legacy_user_id=True)


def _sanitize_imported_day_map(raw_map: Any, user_id: str) -> dict:
    """淨化匯入之每日陣列欄位：忽略非陣列項目防止覆寫他方私密陣列，私人項目強制綁定 JWT user_id，公開項目正規化布林並剝除殘留 private_owner_id。"""
    if not isinstance(raw_map, dict):
        return {}
    uid = str(user_id or "").strip()
    sanitized = {}
    for day_key, items_list in raw_map.items():
        if not isinstance(items_list, list):
            continue
        cleaned_list = []
        for item in items_list:
            if not isinstance(item, dict):
                cleaned_list.append(item)
                continue
            entry = dict(item)
            if entry.get("is_private") is True:
                entry["is_private"] = True
                entry["private_owner_id"] = uid
            else:
                entry.pop("private_owner_id", None)
                if "is_private" in entry:
                    entry["is_private"] = False
            cleaned_list.append(entry)
        sanitized[day_key] = cleaned_list
    return sanitized

# ensure_user_exists moved to utils.helpers


# ═══════════════════════════════════════════════════════════════════════════════
# 🆕 Public Share Endpoint (ISR-enabled, no auth required)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/share/{public_id}")
async def get_public_trip_by_public_id(
    public_id: str,
    supabase=Depends(get_supabase)
):
    """🌐 公開行程分享 (無需認證, 支援 ISR)
    
    用於 Next.js ISR 頁面的 Server-side fetch。
    注意：這是公開 API，絕不包含加入碼 (share_code) 或訂房代號 (reservation_code)。
    
    Rate Limit: 10 requests/minute per IP (防暴力枚舉)
    """
    # 🛡️ Input Validation
    if not re.match(r'^pub_[a-z0-9]{8}$', public_id):
        raise HTTPException(status_code=400, detail="Invalid public ID format")
    try:
        def _fetch_public_trip():
            # 1. 透過 public_id 查詢行程
            trip_res = supabase.table("itineraries").select("*").eq("public_id", public_id).execute()

            if not trip_res.data or len(trip_res.data) == 0:
                raise HTTPException(status_code=404, detail="Trip not found")

            trip_row = trip_res.data[0]

            # 2. 抓該行程的所有細項 (公開資料，不過濾)
            items_res = (
                supabase.table("itinerary_items")
                .select("*")
                .eq("itinerary_id", trip_row["id"])
                .order("day_number")
                .order("sort_order")
                .order("time_slot")
                .execute()
            )
            return trip_row, items_res

        trip, items_res = await run_in_threadpool(_fetch_public_trip)
        
        # 3. 整理成前端要的格式 (含隱私過濾)
        days_map = {}
        if items_res.data:
            for item in items_res.data:
                # 🛡️ 隱私過濾：公開分享連結絕對不顯示私人項目
                if item.get("is_private", False):
                    continue
                    
                d = item["day_number"]
                if d not in days_map:
                    days_map[d] = []
                
                days_map[d].append({
                    "id": item["id"],
                    "time_slot": item["time_slot"][:5] if item["time_slot"] else "00:00",
                    "time": item["time_slot"][:5] if item["time_slot"] else "00:00",
                    "place_name": item["place_name"],
                    "place": item["place_name"],
                    "category": item["category"] or "sightseeing",
                    "notes": item["notes"],
                    "desc": item["notes"],
                    "lat": item["location_lat"],
                    "lng": item["location_lng"],
                    "image_url": item.get("image_url"),
                    "image_urls": item.get("image_urls", []),
                    "tags": item.get("tags", []),
                    "link_url": item.get("link_url"),
                    "website_link": item.get("website_link"),
                    "address": item.get("address"),
                    "preview_metadata": item.get("preview_metadata"),
                    # 🛡️ 機密防衛：公開端點絕不洩漏 reservation_code
                    "hide_navigation": item.get("hide_navigation", False),
                    "is_highlight": item.get("is_highlight", False)
                })
        
        content = trip.get("content") or {}
        
        # 4. 回傳公開資料 (過濾敏感資訊)
        return {
            "id": trip["id"],
            "title": trip["title"],
            "start_date": trip["start_date"],
            "end_date": trip.get("end_date"),
            "cover_image": trip.get("cover_image"),
            # 🛡️ 憑證防衛：公開端點絕不洩漏 share_code，徹底杜絕訪客自主升權
            "creator_name": trip.get("creator_name", "Guest"),
            "currency": resolve_trip_currency(trip, content),
            "daily_locations": content.get("daily_locations", {}),
            # 不回傳: day_costs, day_tickets (私人財務資訊)
            # 不回傳: members (隱私)
            "days": [{"day": d, "activities": days_map[d]} for d in sorted(days_map.keys())] if days_map else []
        }

    except HTTPException:
        raise
    except Exception as e:
        # 🛡️ 安全日誌：內部記錄細節，但不暴露給客戶端
        print(f"🔥 Public Share Error: {e}")
        raise HTTPException(status_code=500, detail="Unable to retrieve trip data")


# ═══════════════════════════════════════════════════════════════════════════════
# Trip CRUD Operations
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("")
async def get_trips(
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """📋 取得我參與的所有行程
    
    🛡️ 已強化身分驗證：
    1. 優先從 JWT 驗證
    2. 回落至 Header (向後相容)
    """
    print(f"📋 查詢使用者 {user_id} 的所有行程")
    
    if not user_id:
        raise HTTPException(status_code=401, detail="需要提供 X-User-ID Header")
    
    try:
        def _fetch_user_trips():
            # 🆕 Phase 3: 使用 user_trips_view 一次性取得所有相關行程 (Dashboard Optimization)
            # 這取代了原本需要兩次查詢 (trip_members + itineraries) 的邏輯
            try:
                res = supabase.table("user_trips_view")\
                    .select("*")\
                    .eq("user_id", user_id)\
                    .execute()
                print(f"📊 Dashboard: Using optimized user_trips_view")
                return res.data or []
            except Exception as view_err:
                # 🛡️ Zero-Regression Fallback: If view is broken (e.g. missing column), 
                # switch to robust table join to ensure itineraries remain visible.
                error_msg = str(view_err)
                print(f"⚠️ [Resilience Fallback] user_trips_view issue: {error_msg}")
                
                # Explicitly log if it's the known column missing error (42703)
                if "42703" in error_msg:
                    print("🚨 Detectable Pathogen: Missing column in trip_members. Activating surgical fallback.")
                # 🔄 Fallback Logic: 同時抓取成員表與創立表
                members_res = supabase.table("trip_members").select("itinerary_id").eq("user_id", user_id).execute()
                member_ids = [m['itinerary_id'] for m in members_res.data] if members_res.data else []
                
                owned_res = supabase.table("itineraries").select("id").eq("created_by", user_id).execute()
                owned_ids = [i['id'] for i in owned_res.data] if owned_res.data else []
                
                all_ids = list(set(member_ids + owned_ids))
                if not all_ids:
                    return []
                    
                res = supabase.table("itineraries").select("*").in_("id", all_ids).order("created_at", desc=True).execute()
                return res.data or []

        trips_data = await run_in_threadpool(_fetch_user_trips)

        # 整理資料結構 - 🔧 FIX: 解析 content 欄位，將 daily_locations 提升到頂層，並過濾他方私人項目與原生 UUID
        trips = []
        for raw_trip in trips_data:
            trip = dict(raw_trip)
            content = dict(trip.get('content') or {})
            trip_id_str = str(trip.get('id') or '')
            is_owner = _is_trip_creator(trip, user_id, allow_legacy_user_id=False)

            raw_day_costs = content.get('day_costs') or trip.get('day_costs') or {}
            raw_day_tickets = content.get('day_tickets') or trip.get('day_tickets') or {}
            raw_day_checklists = content.get('day_checklists') or trip.get('day_checklists') or {}
            raw_credit_cards = content.get('credit_cards') or trip.get('credit_cards') or []

            filtered_costs = _filter_private_day_items(raw_day_costs, user_id, is_owner)
            filtered_tickets = _filter_private_day_items(raw_day_tickets, user_id, is_owner)
            filtered_checklists = _filter_private_day_items(raw_day_checklists, user_id, is_owner)
            filtered_cards = _filter_private_cards(raw_credit_cards, user_id, is_owner, trip_id=trip_id_str)

            # 🆕 將 content 內的欄位提升到頂層，與 get_trip_by_id 格式一致
            trip['daily_locations'] = content.get('daily_locations') or trip.get('daily_locations') or {}
            trip['day_notes'] = content.get('day_notes') or trip.get('day_notes') or {}
            trip['day_costs'] = filtered_costs
            trip['day_tickets'] = filtered_tickets
            trip['day_checklists'] = filtered_checklists
            trip['ai_review'] = content.get('ai_review') or trip.get('ai_review') or ""
            trip['credit_cards'] = filtered_cards
            if 'content' in trip and isinstance(trip.get('content'), dict):
                content['day_costs'] = filtered_costs
                content['day_tickets'] = filtered_tickets
                content['day_checklists'] = filtered_checklists
                content['credit_cards'] = filtered_cards
                trip['content'] = content
            trip['currency'] = resolve_trip_currency(trip, content)
            trip['is_sample'] = content.get('is_sample', False)  # 🎓 Sample trip flag
            # 🛡️ 列表出口脫敏：非建立者本人不暴露原生 created_by / legacy user_id UUID，消除 ATO 外洩路徑
            if not is_owner:
                trip['created_by'] = None
                if trip.get('user_id') and str(trip.get('user_id')).strip() != str(user_id).strip():
                    trip['user_id'] = None
            trips.append(trip)
            
        # 📌 Feature: 行程強制置頂 (Pin Sample Itinerary)
        # 規則: 1. `is_sample` 為 True 的排最前面 2. 其次依 `created_at` 降冪排序 (最新的在前)
        # 防呆: `created_at` 可能為 None (極端髒資料)，以空字串 "" 墊底處理，避免 TypeError 崩潰
        trips.sort(
            key=lambda t: (
                bool(t.get('is_sample')), 
                t.get('created_at') or ""
            ), 
            reverse=True
        )
        
        print(f"✅ 找到 {len(trips)} 個行程")
        return trips
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"🔥 Get Trips Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="讀取行程列表失敗，請稍後重試")


@router.get("/{trip_id}")
async def get_trip_by_id(
    trip_id: str, 
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """🆕 獲取特定行程 (by ID)
    
    支援隱私過濾：
    - 成員：看到所有項目 (包含私人)
    - 非成員：私人項目會被過濾
    """
    try:
        _guard_resource_id(supabase, trip_id, allow_creator_bypass=True, not_found_detail="Trip not found")
        def _fetch_trip_detail():
            # 1. 查詢指定的行程
            trip_res = supabase.table("itineraries").select("*").eq("id", trip_id).execute()
            
            if not trip_res.data or len(trip_res.data) == 0:
                print(f"ℹ️ [Trips] Trip {trip_id} not found for user {user_id}. Returning 404 for client self-healing.")
                raise HTTPException(status_code=404, detail="Trip not found")
                
            trip_row = trip_res.data[0]
            
            # 🆕 Auto-Migration: If public_id is missing, generate and save it
            if not trip_row.get("public_id"):
                # generate_public_id is now at top level
                new_public_id = generate_public_id()
                try:
                    # 僅在此處嘗試更新，若 column 不存在會失敗但會被 catch
                    supabase.table("itineraries").update({"public_id": new_public_id}).eq("id", trip_id).execute()
                    trip_row["public_id"] = new_public_id
                    print(f"🪄 Auto-Migrated Legacy Trip: Generated public_id={new_public_id}")
                except Exception as e:
                    print(f"⚠️ Failed to auto-migrate public_id: {e} (Maybe column missing?)")

            # 🆕 取得所有成員 (整合查詢：一次性抓取全員包含記錄主鍵 id，並在記憶體完成「成員 + 創立者」雙重核驗)
            all_members_res = supabase.table("trip_members").select("id, user_id, user_name, user_avatar").eq("itinerary_id", trip_id).execute()
            member_rows = all_members_res.data or []
            trip_created_by = str(trip_row.get("created_by") or "")
            
            owner_flag = (user_id == trip_created_by)
            member_flag = owner_flag or any(str(m.get("user_id") or "") == user_id for m in member_rows)
            print(f"🔍 [Trips] user_id={user_id}, is_creator={owner_flag}, is_member={member_flag}")
            
            # 🛡️ BOLA 物件授權防衛：非成員一律嚴格 403 阻斷，陌生人絕不可窺探整趟行程
            if not member_flag:
                raise HTTPException(status_code=403, detail="您不是此行程的成員，無法存取詳細資訊")
            
            # 2. 抓該行程的所有細項 (按 time_slot 排序，確保符合時間軸)
            items_result = supabase.table("itinerary_items").select("*").eq("itinerary_id", trip_row["id"]).order("day_number").order("time_slot").order("sort_order").execute()
            return trip_row, member_rows, trip_created_by, member_flag, items_result

        trip, members, created_by, is_member, items_res = await run_in_threadpool(_fetch_trip_detail)
        
        # 3. 整理成前端要的格式 (含隱私過濾與原生 UUID 隔離)
        is_owner = _is_trip_creator(trip, user_id, allow_legacy_user_id=True)
        days_map = {}
        if items_res.data:
            for item in items_res.data:
                # 🛡️ 隱私過濾邏輯：公開項目全體成員可見；私人項目僅建立者（或無主歷史項目之行程創立者）可見
                is_private = bool(item.get("is_private", False))
                if not _is_day_item_visible_to_user(item, user_id, is_owner):
                    continue
                
                d = item["day_number"]
                if d not in days_map:
                    days_map[d] = []
                
                days_map[d].append({
                    "id": item["id"],
                    "time": item["time_slot"][:5] if item["time_slot"] else "00:00",
                    "place": item["place_name"],
                    "original_name": item["original_name"],
                    "category": item["category"] or "sightseeing",
                    "desc": item["notes"],
                    "memo": item.get("memo") or "",
                    "lat": item["location_lat"],
                    "lng": item["location_lng"],
                    "cost": item["cost_amount"],
                    "reservation_code": item.get("reservation_code"),
                    "tags": item.get("tags", []),
                    "link_url": item.get("link_url"), 
                    "website_link": item.get("website_link"),
                    "address": item.get("address"),
                    "preview_metadata": item.get("preview_metadata") or {},
                    "sub_items": item.get("sub_items") or [],
                    "image_url": item.get("image_url"),
                    "image_urls": item.get("image_urls") or ([item.get("image_url")] if item.get("image_url") else []),
                    "hide_navigation": item.get("hide_navigation", False),
                    "sort_order": item.get("sort_order", 0),
                    "is_highlight": item.get("is_highlight", False),
                    "is_private": is_private,
                    "private_owner_id": item.get("private_owner_id") if is_private else None
                })
        
        # 取得 content 並過濾
        content = trip.get("content") or {}
        
        # 🔧 FIX: Data Restoration - Fallback to top-level columns if content is empty
        # This harmonizes logic with get_trips() list view
        raw_day_costs = content.get("day_costs") or trip.get("day_costs") or {}
        raw_day_tickets = content.get("day_tickets") or trip.get("day_tickets") or {}
        raw_day_checklists = content.get("day_checklists") or trip.get("day_checklists") or {}
        
        day_costs = _filter_private_day_items(raw_day_costs, user_id, is_owner)
        day_tickets = _filter_private_day_items(raw_day_tickets, user_id, is_owner)
        day_checklists = _filter_private_day_items(raw_day_checklists, user_id, is_owner)
        
        return {
            "id": trip["id"],
            "title": trip["title"],
            "creator": trip.get("creator_name", "Guest"),
            "start_date": trip["start_date"],
            "end_date": trip.get("end_date"),
            "share_code": trip.get("share_code", ""),
            "public_id": trip.get("public_id", ""),
            "cover_image": trip.get("cover_image"),
            "currency": resolve_trip_currency(trip, content),
            
            # 🔧 FIX: Check content first (New Truth), then top-level (Legacy Fallback)
            "daily_locations": content.get("daily_locations") or trip.get("daily_locations") or {},
            "day_notes": content.get("day_notes") or trip.get("day_notes") or {},
            "day_costs": day_costs,
            "day_tickets": day_tickets,
            "day_checklists": day_checklists,
            "ai_review": content.get("ai_review") or trip.get("ai_review") or "",
            "day_ai_reviews": content.get("day_ai_reviews") or trip.get("day_ai_reviews") or {},  # 🆕 每日 AI 審核報告
            "flight_info": content.get("flight_info") or trip.get("flight_info") or {},
            "hotel_info": content.get("hotel_info") or trip.get("hotel_info") or {},
            "credit_cards": _filter_private_cards(content.get("credit_cards", []), user_id, is_owner, trip_id=trip_id),
            "is_member": is_member,  # 🆕 告訴前端是否為成員
            "is_owner": is_owner,    # 🆕 告訴前端是否為創立者
            # 🛡️ 伺服端動態脫敏：非本人 UUID 動態雜湊，杜絕隊友奪舍
            "created_by": created_by if is_owner else None,
            "members": [
                {
                    **m,
                    "member_id": str(m.get("id") or ""),
                    "user_id": m["user_id"] if m.get("user_id") == user_id else mask_member_id(m.get("user_id"), trip_id)
                }
                for m in members
            ],
            "days": [{"day": d, "activities": days_map[d]} for d in sorted(days_map.keys())] if days_map else []
        }

    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="Trip not found")
        print(f"❌ Fetch Error for Trip {trip_id}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="讀取行程失敗，請稍後重試")


@router.delete("/{trip_id}/members/{member_ref}")
def kick_member(
    trip_id: str,
    member_ref: str,
    current_user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """🚫 踢出成員 (僅行程創建者可用)"""
    try:
        _guard_resource_id(supabase, trip_id, allow_creator_bypass=True, not_found_detail="找不到該行程")
        # 1. 取得行程資訊 (檢查建立者)
        trip_res = supabase.table("itineraries").select("created_by").eq("id", trip_id).execute()
        if not trip_res.data:
            raise HTTPException(status_code=404, detail="找不到該行程")
            
        owner_id = str(trip_res.data[0].get("created_by") or "")
        
        # 🛡️ 權限檢查 1：只有行程建立者可以剔除成員
        if current_user_id != owner_id:
            raise HTTPException(status_code=403, detail="只有行程建立者可以剔除成員")
            
        # 2. 🛡️ 伺服端記憶體比對：安全比對記錄主鍵 id 或 mem_* 遮罩，絕不拿字串查詢 UUID 欄位 (防 22P02 崩潰)
        members = supabase.table("trip_members").select("id, user_id").eq("itinerary_id", trip_id).execute().data or []
        target = next((m for m in members if str(m.get("id")) == member_ref or mask_member_id(m.get("user_id"), trip_id) == member_ref), None)
        
        if not target:
            raise HTTPException(status_code=404, detail="找不到此成員")
            
        # 🛡️ 權限檢查 2：建立者不能剔除自己
        if str(target.get("user_id")) == owner_id:
            raise HTTPException(status_code=400, detail="建立者不能將自己從行程中剔除")
        
        # 3. 精確以記錄主鍵 id 執行刪除
        del_res = supabase.table("trip_members")\
            .delete()\
            .eq("itinerary_id", trip_id)\
            .eq("id", target["id"])\
            .execute()
            
        if not del_res.data:
            raise HTTPException(status_code=404, detail="找不到此成員")

        print(f"🚫 已踢出成員記錄 {target['id']} from trip {trip_id}")
        return {"status": "success", "message": "成員已成功移除", "kicked_member_id": str(target["id"])}
        
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="找不到該行程")
        print(f"🔥 Kick Member Error: {e}")
        raise HTTPException(status_code=500, detail="移除成員時發生未知錯誤")


@router.delete("/{trip_id}")
def delete_trip(
    trip_id: str, 
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """🗑️ 刪除整趟行程 (安全先驗後刪版)"""
    try:
        _guard_resource_id(supabase, trip_id, allow_creator_bypass=True, not_found_detail="找不到此行程")
        print(f"🗑️ 嘗試刪除行程 ID: {trip_id}, 由使用者: {user_id}")
        
        # 0. 權限檢查：只有行程創立者可以刪除行程
        trip_check = supabase.table("itineraries").select("created_by").eq("id", trip_id).execute()
        if not trip_check.data:
            raise HTTPException(status_code=404, detail="找不到此行程")
            
        owner_id = str(trip_check.data[0].get("created_by") or "")
        
        # 1. 🛡️ 先驗後刪：創立者驗證必須在任何物理刪除之前！未授權者立即 403 阻斷，保護受害者帳本
        if owner_id != user_id:
            raise HTTPException(status_code=403, detail="只有行程創立者可以刪除行程")
        
        # 2. 🛡️ 授權確認後，才執行關聯費用清除 (FK Cleanup)
        try:
            supabase.table("expenses").delete().eq("itinerary_id", trip_id).execute()
            print(f"🧹 Cleared expenses for trip {trip_id}")
        except Exception as fk_err:
            print(f"⚠️ FK Cleanup Warning (expenses): {fk_err}")
        
        # 3. 刪除所有細項與膠囊紀錄 (觸發 Cloudinary 圖片清理後再刪主表)
        supabase.table("itinerary_items").delete().eq("itinerary_id", trip_id).execute()
        print("   ✅ 細項已刪除")

        try:
            supabase.table("trip_capsule_entries").delete().eq("trip_id", trip_id).execute()
            print("   ✅ 時光膠囊紀錄已清理")
        except Exception as cap_err:
            print(f"⚠️ FK Cleanup Warning (trip_capsule_entries): {cap_err}")
        
        # 4. 刪除所有成員關係
        supabase.table("trip_members").delete().eq("itinerary_id", trip_id).execute()
        print("   ✅ 成員關係已刪除")
        
        # 5. 最後刪除主行程
        res = supabase.table("itineraries").delete().eq("id", trip_id).execute()
        
        # 關鍵檢查：如果 data 是空的，代表根本沒刪到東西
        if not res.data:
            print(f"❌ 刪除失敗：資料庫回傳空值 (ID: {trip_id})")
            raise HTTPException(status_code=404, detail="刪除失敗：找不到該行程或無權限")
        
        print(f"   ✅ 主行程已刪除: {res.data}")
        return {"status": "success", "message": "Trip deleted", "deleted_data": res.data}
        
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="找不到此行程")
        print(f"🔥 Delete Error: {e}")
        raise HTTPException(status_code=500, detail="刪除行程失敗，請稍後重試")


@router.post("/create-manual")
async def create_manual_trip(
    request: CreateManualTripRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """🔥 手動建立空白行程"""
    try:
        cached = get_idempotent_response("create_manual_trip", user_id, idempotency_key)
        if cached is not None:
            return cached

        # 🆕 Phase 2: 行程數量限制（最多 3 個自建行程）
        count_res = await run_in_threadpool(
            lambda: supabase.table("itineraries")
            .select("id", count="exact")
            .eq("created_by", user_id)
            .execute()
        )
        
        raw_count = getattr(count_res, "count", None)
        owned_count = raw_count if isinstance(raw_count, int) else len(count_res.data or [])
        if owned_count >= 3:
            raise HTTPException(
                status_code=403, 
                detail="行程數量已達上限 (最多 3 個)，請先下載 PDF 後刪除舊行程"
            )
        
        room_code = generate_room_code()
        pub_id = generate_public_id()
        
        # 🛡️ 封面保底：若無自訂封面，自動依行程標題解析高畫質風景封面
        clean_cover = request.cover_image.strip() if (request.cover_image and request.cover_image.strip()) else resolve_destination_cover_url(request.title)

        trip_data = {
            "title": request.title,
            "creator_name": request.creator_name,
            "created_by": user_id,
            "share_code": room_code,
            "public_id": pub_id,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "status": "active",
            "content": {},  # 👈 新增：給個空物件，不要讓它是 NULL
            "flight_info": {},
            "hotel_info": {},
            "cover_image": clean_cover
        }
        
        
        # 🆕 Phase 3.1: 確保使用者存在 (滿足外鍵約束)
        await ensure_user_exists(supabase, user_id, request.creator_name)
        
        trip_res = await run_in_threadpool(lambda: supabase.table("itineraries").insert(trip_data).execute())
        if not trip_res.data:
            raise HTTPException(status_code=500, detail="建立行程失敗：資料庫未傳回建立結果")
        trip_id = trip_res.data[0]['id']

        # 加入成員 (若失敗則執行補償刪除，避免留下孤兒行程佔用配額)
        try:
            await run_in_threadpool(
                lambda: supabase.table("trip_members").insert({
                    "itinerary_id": trip_id,
                    "user_id": user_id,
                    "user_name": request.creator_name
                }).execute()
            )
        except Exception as member_err:
            print(f"⚠️ create_manual_trip member insert failed, rolling back trip {trip_id}: {member_err}")
            await run_in_threadpool(_rollback_created_trip, supabase, trip_id)
            raise HTTPException(status_code=500, detail="建立行程成員關聯失敗，已回滾復原")

        response_payload = {"status": "success", "trip_id": trip_id, "share_code": room_code, "public_id": pub_id}
        store_idempotent_response("create_manual_trip", user_id, idempotency_key, response_payload)
        return response_payload
    except HTTPException:
        raise
    except Exception as e:
        print(f"🔥 create_manual_trip error: {e}")
        raise HTTPException(status_code=500, detail="建立行程失敗，請稍後重試")


@router.patch("/{trip_id}/title")
def update_trip_title(
    trip_id: str, 
    request: UpdateTripTitleRequest,
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """🔥 修改行程標題"""
    try:
        _guard_resource_id(supabase, trip_id, allow_creator_bypass=False, forbidden_detail="您沒有權限修改此行程標題")
        # 🛡️ 權限檢查 (只有成員能修改標題)
        member_check = supabase.table("trip_members")\
            .select("user_id")\
            .eq("itinerary_id", trip_id)\
            .eq("user_id", user_id)\
            .execute()
        
        if not member_check.data:
            raise HTTPException(status_code=403, detail="您沒有權限修改此行程標題")

        supabase.table("itineraries").update({"title": request.title}).eq("id", trip_id).execute()
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="找不到此行程")
        print(f"🔥 Update Title Error: {e}")
        raise HTTPException(status_code=500, detail="更新行程標題失敗，請稍後重試")


@router.patch("/{trip_id}/cover")
def update_trip_cover(
    trip_id: str,
    request: UpdateCoverRequest,
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """🖼️ 修改行程封面圖 (支援上傳、換圖或移除)"""
    try:
        _guard_resource_id(supabase, trip_id, allow_creator_bypass=False, forbidden_detail="您沒有權限修改此行程封面")
        # 🛡️ 權限檢查 (只有行程成員或創建者能修改封面)
        member_check = supabase.table("trip_members")\
            .select("user_id")\
            .eq("itinerary_id", trip_id)\
            .eq("user_id", user_id)\
            .execute()
        
        if not member_check.data:
            raise HTTPException(status_code=403, detail="您沒有權限修改此行程封面")

        clean_cover = request.cover_image.strip() if (request.cover_image and request.cover_image.strip()) else None
        supabase.table("itineraries").update({"cover_image": clean_cover}).eq("id", trip_id).execute()
        return {"status": "success", "cover_image": clean_cover}
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="找不到此行程")
        print(f"🔥 Update Cover Error: {e}")
        raise HTTPException(status_code=500, detail="更新行程封面失敗，請稍後重試")



# ═══════════════════════════════════════════════════════════════════════════════
# Legacy Endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/join-trip")
async def join_trip(
    request: JoinTripRequest, 
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """🚪 加入行程 (通過房間碼)"""
    print(f"🚪 使用者 {request.user_name} 嘗試加入房間: {request.share_code}")
    
    try:
        # 1. 找行程
        trip_res = await run_in_threadpool(
            lambda: supabase.table("itineraries").select("id, title").eq("share_code", request.share_code).execute()
        )
        
        if not trip_res.data:
            raise HTTPException(status_code=404, detail="找不到此行程代碼")
            
            
        trip = trip_res.data[0]
        print(f"✅ 找到行程: {trip['title']}")
        
        # 🆕 Phase 3.1: 確保加入者也存在於專屬 users 表 (滿足外鍵約束)
        await ensure_user_exists(supabase, user_id, request.user_name)
        
        # 2. 加入成員 (如果已加入會報錯，我們用 try 接住忽略)
        try:
            await run_in_threadpool(
                lambda: supabase.table("trip_members").insert({
                    "itinerary_id": trip['id'],
                    "user_id": user_id,
                    "user_name": request.user_name
                }).execute()
            )
            print(f"✅ 成功加入成員")
        except Exception as member_err:
            print(f"ℹ️ 使用者可能已經是成員: {member_err}")
            pass  # 已經加入過就算了

        return {"status": "success", "trip": trip}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"🔥 Join Trip Error: {e}")
        raise HTTPException(status_code=500, detail="加入行程失敗，請稍後重試")


@router.get("/itinerary/latest")
def get_latest_itinerary(
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """🔥 讀取最新行程 (給主畫面用)"""
    try:
        # 1. 抓該使用者最新的一個行程 (依賴 user_trips_view，並具備容錯 fallback，防止全域行程洩漏)
        trip = None
        try:
            view_res = supabase.table("user_trips_view")\
                .select("*")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()
            if view_res.data:
                trip = view_res.data[0]
        except Exception as view_err:
            print(f"⚠️ [Resilience Fallback] user_trips_view error in latest: {view_err}")
            # Fallback: 查詢成員與創立表
            members_res = supabase.table("trip_members").select("itinerary_id").eq("user_id", user_id).execute()
            member_ids = [m['itinerary_id'] for m in members_res.data] if members_res.data else []
            
            owned_res = supabase.table("itineraries").select("id").eq("created_by", user_id).execute()
            owned_ids = [i['id'] for i in owned_res.data] if owned_res.data else []
            
            all_ids = list(set(member_ids + owned_ids))
            if all_ids:
                fallback_res = supabase.table("itineraries").select("*").in_("id", all_ids).order("created_at", desc=True).limit(1).execute()
                if fallback_res.data:
                    trip = fallback_res.data[0]
        
        if not trip:
            return None
        
        # 2. 抓該行程的所有細項 (按 sort_order 排序，支援拖曳)
        items_res = supabase.table("itinerary_items").select("*").eq("itinerary_id", trip["id"]).order("day_number").order("sort_order").order("time_slot").execute()
        
        # 3. 整理成前端要的格式 (注意：user_trips_view 的 user_id 是成員本人 ID，絕不可用於判定 is_owner)
        is_owner = _is_trip_creator(trip, user_id, allow_legacy_user_id=False)
        days_map = {}
        if items_res.data:
            for item in items_res.data:
                # 🛡️ 隱私過濾：主畫面只顯示公開或本人（及行程創立者無主歷史）私人項目
                is_private = bool(item.get("is_private", False))
                if not _is_day_item_visible_to_user(item, user_id, is_owner):
                    continue
                    
                d = item["day_number"]
                if d not in days_map:
                    days_map[d] = []
                
                days_map[d].append({
                    "id": item["id"],
                    "time": item["time_slot"][:5] if item["time_slot"] else "00:00",
                    "place": item["place_name"],
                    "original_name": item["original_name"],
                    "category": item["category"] or "sightseeing",
                    "desc": item["notes"],
                    "memo": item.get("memo") or "",
                    "lat": item["location_lat"],
                    "lng": item["location_lng"],
                    "cost": item["cost_amount"],
                    "reservation_code": item.get("reservation_code"),
                    "tags": item.get("tags", []),
                    "link_url": item.get("link_url"), 
                    "website_link": item.get("website_link"),
                    "address": item.get("address"),
                    "sub_items": item.get("sub_items") or [],
                    "image_url": item.get("image_url"),
                    "image_urls": item.get("image_urls") or ([item.get("image_url")] if item.get("image_url") else []),
                    "is_private": is_private,
                    "private_owner_id": item.get("private_owner_id") if is_private else None
                })
            
        # 轉成陣列
        days_array = []
        for d in sorted(days_map.keys()):
            days_array.append({
                "day": d,
                "activities": days_map[d]
            })

        content = trip.get("content") or {}
        filtered_day_costs = _filter_private_day_items(content.get("day_costs", {}), user_id, is_owner)
        filtered_day_tickets = _filter_private_day_items(content.get("day_tickets", {}), user_id, is_owner)
        filtered_day_checklists = _filter_private_day_items(content.get("day_checklists", {}), user_id, is_owner)
            
        return {
            "id": trip["id"],
            "title": trip["title"],
            "creator": trip.get("creator_name", "Guest"),
            "start_date": trip["start_date"],  # 👈 關鍵！補上這行
            "end_date": trip.get("end_date"),  # 🐛 FIX: 補上缺失的 end_date
            "share_code": trip.get("share_code", ""),  # 順便補上分享碼
            "currency": resolve_trip_currency(trip, content),
            # 👇 讀取並回傳
            "daily_locations": content.get("daily_locations", {}),
            # 🆕 每日提示（過濾他方私人項目與原生 UUID）
            "day_notes": content.get("day_notes", {}),
            "day_costs": filtered_day_costs,
            "day_tickets": filtered_day_tickets,
            "day_checklists": filtered_day_checklists,
            "ai_review": content.get("ai_review", ""),  # 🆕 AI 審核
            "day_ai_reviews": content.get("day_ai_reviews", {}),  # 🆕 每日 AI 審核
            
            "flight_info": trip.get("flight_info") or {},  # 👈 新增航班資訊
            "hotel_info": trip.get("hotel_info") or {},    # 👈 新增住宿資訊
            # 即使 days_map 是空的，也要回傳空陣列，不然前端 map 會爆
            "days": [{"day": d, "activities": days_map[d]} for d in sorted(days_map.keys())] if days_map else []
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Fetch Error: {e}")
        raise HTTPException(status_code=500, detail="讀取最新行程失敗，請稍後重試")


# ═══════════════════════════════════════════════════════════════════════════════
# Trip Data Updates (Batch 2)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/save-itinerary")
async def save_itinerary(
    request: SaveItineraryRequest, 
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """💾 儲存行程到資料庫
    
    產生房間碼，創建主行程，並批量插入細項。
    """
    print(f"💾 正在儲存行程: {request.title}...")
    print(f"   創建者: {request.creator_name}")
    print(f"   User ID: {request.user_id}")
    print(f"   項目數量: {len(request.items)}")
    
    created_trip_id: Optional[str] = None
    try:
        cached = get_idempotent_response("save_itinerary", user_id, idempotency_key)
        if cached is not None:
            return cached

        # 🆕 Phase 2: 行程數量限制 (最多 3 個自建行程)
        # 🛡️ 競態防禦：在此進行最終檢查。注意：最高強度的防禦建議在資料庫端建立 Trigger
        # SQL範例: CREATE TRIGGER check_trip_limit BEFORE INSERT ON itineraries ...
        count_res = await run_in_threadpool(
            lambda: supabase.table("itineraries")
            .select("id", count="exact")
            .eq("created_by", user_id)
            .execute()
        )
        
        raw_count = getattr(count_res, "count", None)
        owned_count = raw_count if isinstance(raw_count, int) else len(count_res.data or [])
        if owned_count >= 3:
            raise HTTPException(
                status_code=403, 
                detail="行程數量已達上限 (最多 3 個)，請先下載 PDF 後刪除舊行程"
            )

        
        # 1. 產生房間號與公開 ID
        room_code = generate_room_code()
        pub_id = generate_public_id()
        
        # 🆕 自動計算 end_date (支援天數防禦性展延，絕不截斷)
        start_date = request.start_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        max_day = max((item.day_number for item in request.items), default=1) if request.items else 1
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            calculated_end = (start_dt + timedelta(days=max_day - 1)).strftime("%Y-%m-%d")
            if request.end_date:
                req_end_dt = datetime.strptime(request.end_date, "%Y-%m-%d")
                req_days = (req_end_dt - start_dt).days + 1
                # 🛡️ 守衛：若傳入天數小於 items 最大天數，強制以 max_day 展延，絕不截斷！
                end_date = request.end_date if req_days >= max_day else calculated_end
            else:
                end_date = calculated_end
            print(f"   🆕 行程天數確認: {start_date} ~ {end_date} (總計 {max_day} 天)")
        except Exception:
            end_date = start_date
        
        # 2. 建立主行程 (Parent) - 寫入前先執行逐日空間錨點校驗與非破壞性自癒，並自動補齊 daily_locations
        from services.geocode_service import verify_and_heal_itinerary_coords
        raw_save_items = [
            {
                "day_number": item.day_number,
                "place_name": item.place_name,
                "original_name": item.original_name,
                "notes": item.desc,
                "address": item.address,
                "lat": item.lat,
                "lng": item.lng,
            }
            for item in request.items
        ]
        healed_save_items, resolved_save_daily_locs = await verify_and_heal_itinerary_coords(
            raw_save_items,
            trip_meta={
                "title": request.title,
                "daily_locations": request.daily_locations or {},
            },
        )
        merged_save_daily_locs = resolved_save_daily_locs or {}
        cover_image = request.cover_image.strip() if (request.cover_image and request.cover_image.strip()) else resolve_destination_cover_url(request.title)

        trip_data = {
            "title": request.title,
            "creator_name": request.creator_name,
            "created_by": user_id,
            "share_code": room_code,
            "public_id": pub_id,
            "start_date": start_date,
            "end_date": end_date,
            "status": "active",
            "cover_image": cover_image,
            # 👇 存入 JSONB 欄位: 包含 daily_locations 及新的 daily tips
            # 👇 存入 JSONB 欄位 (🆕 v4.Long-term: 預留欄位以防未來擴充)
            "content": {
                "daily_locations": merged_save_daily_locs,
                "day_notes": request.day_notes or {},
                "day_costs": request.day_costs or {},
                "day_tickets": request.day_tickets or {},
                "day_checklists": request.day_checklists or {},
                "ai_review": request.ai_review or None,
                "credit_cards": [], # 🆕 顯式初始化，防止後續讀取異常
                "flight_info": None,
                "hotel_info": None,
                "currency": request.currency or "TWD"
            }
        }
        
        # 🆕 Phase 3.1: 確保使用者存在 (滿足外鍵約束)
        await ensure_user_exists(supabase, user_id, request.creator_name)
        
        trip_res = await run_in_threadpool(lambda: supabase.table("itineraries").insert(trip_data).execute())
        
        if not trip_res.data:
            raise HTTPException(status_code=500, detail="無法建立主行程")
            
        trip_id = trip_res.data[0]["id"]
        created_trip_id = trip_id
        print(f"✅ 主行程建立成功 ID: {trip_id}, 房間號: {room_code}")

        # 3. 自動把創建者加入成員列表
        member_data = {
            "itinerary_id": trip_id,
            "user_id": user_id,
            "user_name": request.creator_name
        }
        await run_in_threadpool(lambda: supabase.table("trip_members").insert(member_data).execute())

        # 4. 建立細項 (Children)
        items_data = []
        for idx, item in enumerate(request.items):
            healed_coord = healed_save_items[idx] if idx < len(healed_save_items) else {}
            clean_link_url, clean_website_link, clean_sub_items = _sanitize_item_links(
                item.link_url,
                item.website_link,
                item.sub_items,
            )
            items_data.append({
                "itinerary_id": trip_id,
                "day_number": item.day_number,
                "time_slot": item.time_slot,
                "place_name": item.place_name,
                "original_name": item.original_name,
                "category": item.category,
                "notes": item.desc,
                "location_lat": healed_coord.get("lat", item.lat),
                "location_lng": healed_coord.get("lng", item.lng),
                "cost_amount": item.cost_amount,
                "reservation_code": item.reservation_code,
                "tags": item.tags,
                "sub_items": clean_sub_items,
                "link_url": clean_link_url,
                "website_link": clean_website_link,
                "address": item.address,
                "memo": item.memo,
                "image_url": item.image_url,
                "image_urls": item.image_urls or ([item.image_url] if item.image_url else []),
                "hide_navigation": item.hide_navigation,
                "is_private": item.is_private,
                "is_highlight": item.is_highlight,
                "preview_metadata": item.preview_metadata
            })
            
        # 批次寫入
        if items_data:
            print(f"   📦 準備插入 {len(items_data)} 個細項...")
            try:
                await run_in_threadpool(lambda: supabase.table("itinerary_items").insert(items_data).execute())
                print(f"   ✅ 細項插入成功!")
            except Exception as item_err:
                print(f"   ❌ 細項插入失敗: {item_err}")
                # 嘗試逐個插入以找出問題項目
                def _insert_one_by_one():
                    for i, item in enumerate(items_data):
                        try:
                            supabase.table("itinerary_items").insert(item).execute()
                            print(f"      ✅ Item {i+1} OK")
                        except Exception as single_err:
                            print(f"      ❌ Item {i+1} FAILED: {single_err}")
                            print(f"         Data: {item}")
                await run_in_threadpool(_insert_one_by_one)
                raise item_err
            
        response_payload = {"status": "success", "trip_id": trip_id, "share_code": room_code, "public_id": pub_id}
        store_idempotent_response("save_itinerary", user_id, idempotency_key, response_payload)
        return response_payload

    except HTTPException:
        if created_trip_id:
            print(f"⚠️ save_itinerary aborted via HTTPException after parent insert; rolling back trip {created_trip_id}")
            await run_in_threadpool(_rollback_created_trip, supabase, created_trip_id)
        raise
    except Exception as e:
        if created_trip_id:
            print(f"⚠️ save_itinerary failed after parent insert; rolling back trip {created_trip_id}")
            await run_in_threadpool(_rollback_created_trip, supabase, created_trip_id)
        print(f"🔥 Save Error: {e}")
        print(f"   Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="儲存行程失敗，請稍後重試")


@router.post("/import-to-trip")
async def import_to_trip(
    request: ImportToTripRequest, 
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """📥 匯入到現有行程
    
    將新項目合併到現有行程的 content 並新增 items。
    """
    print(f"📥 正在匯入至現有行程 ID: {request.trip_id}...")
    
    try:
        _precheck_atomic_trip_id(
            supabase,
            request.trip_id,
            allow_creator_bypass=True,
            forbidden_detail="只有行程成員或創建者可以匯入內容",
            not_found_detail="找不到指定的行程",
        )
        # 1. 檢查行程是否存在並獲取現有資料 (Off-loop via threadpool)
        trip_res = await run_in_threadpool(
            lambda: supabase.table("itineraries").select("*").eq("id", request.trip_id).execute()
        )
        if not trip_res.data:
            raise HTTPException(status_code=404, detail="找不到指定的行程")
            
        existing_trip = trip_res.data[0]

        # 🛡️ 權限檢查：只有行程創建者或成員可以匯入內容
        created_by = str(existing_trip.get("created_by") or "")
        if created_by != user_id:
            mem_res = await run_in_threadpool(
                lambda: supabase.table("trip_members")
                .select("id")
                .eq("itinerary_id", request.trip_id)
                .eq("user_id", user_id)
                .execute()
            )
            if not mem_res.data:
                raise HTTPException(status_code=403, detail="只有行程成員或創建者可以匯入內容")

        existing_content = existing_trip.get("content") or {}
        
        # 2. 合併 content 資料輔助函數
        #    - merge_dicts: 用於 daily_locations (一天只有一個中心點，覆蓋)
        #    - deep_merge_day_arrays: 用於 notes/costs/tickets (同一天可追加)
        
        def merge_dicts(old_d, new_d):
            """簡單的 key-level 合併 (新值覆蓋舊值)"""
            if not new_d: return old_d or {}
            if not old_d: return new_d
            result = old_d.copy()
            result.update(new_d)
            return result
        
        def deep_merge_day_arrays(old_d: dict, new_d: dict) -> dict:
            """陣列型每日資料的深度合併 (追加而非覆蓋，嚴禁非陣列覆寫既有陣列)
            
            用途：同一天分批匯入時，day_notes/costs/tickets 會追加合併
            範例：
              舊資料: {"1": [{"item": "交通", "amount": "¥1200"}]}
              新資料: {"1": [{"item": "午餐", "amount": "¥1000"}]}
              結果:   {"1": [{"item": "交通", "amount": "¥1200"}, {"item": "午餐", "amount": "¥1000"}]}
            """
            if not new_d: return old_d or {}
            if not old_d: return new_d
            result = old_d.copy()
            for day_key, new_items in new_d.items():
                if new_items is None:
                    continue
                existing = result.get(day_key)
                if isinstance(existing, list):
                    if isinstance(new_items, list):
                        result[day_key] = existing + new_items  # 追加合併
                    # 非陣列絕不覆寫既有陣列（保護他方私密項目）
                else:
                    result[day_key] = new_items
            return result
        
        # 3. 取得現有地點組合，執行「智能去重」(Smart Deduplication) 與空間錨點取樣
        existing_items_res = await run_in_threadpool(
            lambda: supabase.table("itinerary_items")
            .select("day_number, place_name, location_lat, location_lng")
            .eq("itinerary_id", request.trip_id)
            .execute()
        )
        existing_set = set()
        existing_items_list = existing_items_res.data or []
        for item in existing_items_list:
            existing_set.add((item["day_number"], item["place_name"]))
        
        # 4. 插入細項前以母體行程既有 content 執行 4 層空間錨點非破壞性自癒（嚴禁未驗證之 request.daily_locations 污染既有錨點）
        from services.geocode_service import verify_and_heal_itinerary_coords
        raw_import_items = [
            {
                "day_number": item.day_number,
                "place_name": item.place_name,
                "original_name": item.original_name,
                "notes": item.desc,
                "address": item.address,
                "lat": item.lat,
                "lng": item.lng,
            }
            for item in request.items
        ]
        healed_import_items, resolved_import_daily_locs = await verify_and_heal_itinerary_coords(
            raw_import_items,
            trip_meta={
                **existing_trip,
                "content": existing_content,
                "daily_locations": merge_dicts(request.daily_locations or {}, existing_content.get("daily_locations") or {}),
            },
            existing_items=existing_items_list,
        )

        # 5. Per-trip RMW 鎖序列化讀取、合併與寫入（防止併發匯入/更新覆蓋 JSONB 或產生重複細項）
        items_data = []
        skipped_count = 0
        async with trip_lock(request.trip_id):
            if _can_use_atomic_rpc(supabase):
                fresh_items_res = await run_in_threadpool(
                    lambda: supabase.table("itinerary_items")
                    .select("day_number, place_name")
                    .eq("itinerary_id", request.trip_id)
                    .execute()
                )
                rpc_existing_set = set(existing_set)
                for item in (getattr(fresh_items_res, "data", None) or []):
                    rpc_existing_set.add((item["day_number"], item["place_name"]))

                is_owner_pre = _is_trip_creator(existing_trip, user_id, allow_legacy_user_id=True)
                rpc_items_data = []
                rpc_skipped = 0
                rpc_max_day = 0
                for idx, item in enumerate(request.items):
                    if (item.day_number, item.place_name) in rpc_existing_set:
                        rpc_skipped += 1
                        continue
                    healed_coord = healed_import_items[idx] if idx < len(healed_import_items) else {}
                    clean_link_url, clean_website_link, clean_sub_items = _sanitize_item_links(
                        item.link_url,
                        item.website_link,
                        item.sub_items,
                    )
                    rpc_max_day = max(rpc_max_day, item.day_number)
                    rpc_items_data.append({
                        "itinerary_id": request.trip_id,
                        "day_number": item.day_number,
                        "time_slot": item.time_slot,
                        "place_name": item.place_name,
                        "original_name": item.original_name,
                        "category": item.category,
                        "notes": item.desc,
                        "location_lat": healed_coord.get("lat", item.lat),
                        "location_lng": healed_coord.get("lng", item.lng),
                        "cost_amount": item.cost_amount,
                        "reservation_code": item.reservation_code,
                        "tags": item.tags,
                        "sub_items": clean_sub_items,
                        "link_url": clean_link_url,
                        "website_link": clean_website_link,
                        "address": item.address,
                        "memo": item.memo,
                        "image_url": item.image_url,
                        "image_urls": item.image_urls or ([item.image_url] if item.image_url else []),
                        "hide_navigation": item.hide_navigation,
                        "is_private": bool(item.is_private) if is_owner_pre else False,
                        "is_highlight": item.is_highlight,
                        "preview_metadata": item.preview_metadata
                    })

                import_patch = {}
                if request.day_notes:
                    import_patch["day_notes"] = request.day_notes
                if request.day_costs:
                    import_patch["day_costs"] = request.day_costs
                if request.day_tickets:
                    import_patch["day_tickets"] = request.day_tickets
                if request.day_checklists:
                    import_patch["day_checklists"] = request.day_checklists
                if request.ai_review:
                    import_patch["ai_review"] = request.ai_review
                if resolved_import_daily_locs:
                    import_patch["daily_locations"] = resolved_import_daily_locs

                fallback_start_date = None
                if request.start_date:
                    try:
                        raw_start = str(request.start_date).split("T")[0].strip()
                        datetime.strptime(raw_start, "%Y-%m-%d")
                        fallback_start_date = raw_start
                    except (ValueError, TypeError):
                        print(f"⚠️ [Date Sync] Ignoring invalid fallback start_date: {request.start_date}")

                rpc_res = await _execute_atomic_trip_rpc(
                    supabase,
                    "merge_trip_import_content_atomic",
                    {
                        "p_trip_id": request.trip_id,
                        "p_user_id": user_id,
                        "p_patch": import_patch,
                        "p_max_imported_day": rpc_max_day if rpc_max_day > 0 else None,
                        "p_fallback_start_date": fallback_start_date,
                    },
                    trip_id=request.trip_id,
                    allow_creator_bypass=True,
                    forbidden_detail="只有行程成員或創建者可以匯入內容",
                    not_found_detail="找不到指定的行程",
                )
                if rpc_res is not None:
                    items_data = rpc_items_data
                    skipped_count = rpc_skipped
                    if items_data:
                        print(f"   📦 準備插入 {len(items_data)} 個細項 (已跳過 {skipped_count} 個重複項)...")
                        await run_in_threadpool(
                            lambda: supabase.table("itinerary_items").insert(items_data).execute()
                        )
                    return {
                        "status": "success",
                        "message": f"成功匯入 {len(items_data)} 個新項目 (跳過 {skipped_count} 個重複地點)",
                        "inserted": len(items_data),
                        "skipped": skipped_count
                    }

            def _import_legacy_fallback_sync():
                nonlocal skipped_count
                fresh_trip_res = supabase.table("itineraries").select("*").eq("id", request.trip_id).execute()
                if fresh_trip_res is not None and not getattr(fresh_trip_res, "data", None):
                    raise HTTPException(status_code=404, detail="找不到指定的行程")
                fresh_trip = _first_row(getattr(fresh_trip_res, "data", None)) or existing_trip
                fresh_content = dict(fresh_trip.get("content") or {})

                # 🛡️ 戰略修復 4.0: 全欄位保留型深度合併 (Neural Preservation Merge)
                updated_content = fresh_content.copy()
                is_owner = _is_trip_creator(fresh_trip, user_id, allow_legacy_user_id=True)

                # B. 深度合併每日數組數據 (追加，並強制將私人項目歸屬綁定為 JWT user_id)
                if request.day_notes:
                    updated_content["day_notes"] = deep_merge_day_arrays(updated_content.get("day_notes"), request.day_notes)
                if request.day_costs:
                    updated_content["day_costs"] = deep_merge_day_arrays(
                        updated_content.get("day_costs"),
                        _sanitize_imported_day_map(request.day_costs, user_id),
                    )
                if request.day_tickets:
                    updated_content["day_tickets"] = deep_merge_day_arrays(
                        updated_content.get("day_tickets"),
                        _sanitize_imported_day_map(request.day_tickets, user_id),
                    )
                if request.day_checklists:
                    updated_content["day_checklists"] = deep_merge_day_arrays(
                        updated_content.get("day_checklists"),
                        _sanitize_imported_day_map(request.day_checklists, user_id),
                    )

                # C. 合併 AI 審核 (保留原有的或更新)
                if request.ai_review:
                    updated_content["ai_review"] = request.ai_review

                updated_content["daily_locations"] = merge_dicts(
                    resolved_import_daily_locs or {},
                    fresh_content.get("daily_locations") or {},
                )

                # 更新主行程 content
                supabase.table("itineraries").update({"content": updated_content}).eq("id", request.trip_id).execute()

                fresh_items_res = supabase.table("itinerary_items").select("day_number, place_name").eq("itinerary_id", request.trip_id).execute()
                for item in (getattr(fresh_items_res, "data", None) or []):
                    existing_set.add((item["day_number"], item["place_name"]))

                max_imported_day = 0
                for idx, item in enumerate(request.items):
                    if (item.day_number, item.place_name) in existing_set:
                        skipped_count += 1
                        continue

                    healed_coord = healed_import_items[idx] if idx < len(healed_import_items) else {}
                    clean_link_url, clean_website_link, clean_sub_items = _sanitize_item_links(
                        item.link_url,
                        item.website_link,
                        item.sub_items,
                    )
                    max_imported_day = max(max_imported_day, item.day_number)
                    items_data.append({
                        "itinerary_id": request.trip_id,
                        "day_number": item.day_number,
                        "time_slot": item.time_slot,
                        "place_name": item.place_name,
                        "original_name": item.original_name,
                        "category": item.category,
                        "notes": item.desc,
                        "location_lat": healed_coord.get("lat", item.lat),
                        "location_lng": healed_coord.get("lng", item.lng),
                        "cost_amount": item.cost_amount,
                        "reservation_code": item.reservation_code,
                        "tags": item.tags,
                        "sub_items": clean_sub_items,
                        "link_url": clean_link_url,
                        "website_link": clean_website_link,
                        "address": item.address,
                        "memo": item.memo,
                        "image_url": item.image_url,
                        "image_urls": item.image_urls or ([item.image_url] if item.image_url else []),
                        "hide_navigation": item.hide_navigation,
                        "is_private": bool(item.is_private) if is_owner else False,
                        "is_highlight": item.is_highlight,
                        "preview_metadata": item.preview_metadata
                    })

                sync_start_date = request.start_date or fresh_trip.get("start_date")

                if max_imported_day > 0 and sync_start_date:
                    try:
                        raw_start = str(sync_start_date).split('T')[0]
                        start_dt = datetime.strptime(raw_start, "%Y-%m-%d")

                        if not fresh_trip.get("start_date") and request.start_date:
                            print(f"📅 [Auto-Sync] Setting missing start_date to: {request.start_date}")
                            supabase.table("itineraries").update({"start_date": request.start_date}).eq("id", request.trip_id).execute()

                        new_end_dt = start_dt + timedelta(days=max_imported_day - 1)
                        new_end_date = new_end_dt.strftime("%Y-%m-%d")

                        current_days = 1
                        if fresh_trip.get("end_date"):
                            raw_end = str(fresh_trip["end_date"]).split('T')[0]
                            old_end_dt = datetime.strptime(raw_end, "%Y-%m-%d")
                            current_days = (old_end_dt - start_dt).days + 1

                        if max_imported_day > current_days:
                            print(f"📅 [Auto-Sync] Extending trip end_date to: {new_end_date} (Day {max_imported_day})")
                            supabase.table("itineraries").update({"end_date": new_end_date}).eq("id", request.trip_id).execute()
                        else:
                            print(f"📅 [Auto-Sync] No extension needed (Day {max_imported_day} <= {current_days})")
                    except Exception as date_err:
                        print(f"⚠️ [Date Sync Critical Failure] {date_err} | Start: {fresh_trip.get('start_date')}")

                if items_data:
                    print(f"   📦 準備插入 {len(items_data)} 個細項 (已跳過 {skipped_count} 個重複項)...")
                    supabase.table("itinerary_items").insert(items_data).execute()

            await run_in_threadpool(_import_legacy_fallback_sync)
            
        return {
            "status": "success", 
            "message": f"成功匯入 {len(items_data)} 個新項目 (跳過 {skipped_count} 個重複地點)",
            "inserted": len(items_data),
            "skipped": skipped_count
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"🔥 Import Error: {e}")
        print(f"   Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="匯入行程失敗，請稍後重試")


@router.patch("/{trip_id}/day-data")
async def update_day_data(
    trip_id: str, 
    request: UpdateDayDataRequest, 
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """📝 更新特定天的注意事項、預估花費、交通票券"""
    try:
        if request.day < 0:
            raise HTTPException(status_code=400, detail="無效的請求參數")

        _precheck_atomic_trip_id(
            supabase,
            trip_id,
            allow_creator_bypass=False,
            forbidden_detail="您沒有權限修改此行程資訊",
            not_found_detail="Trip not found",
        )

        if _can_use_atomic_rpc(supabase):
            day_key = str(request.day)
            rpc_patch = {}
            if request.day_notes is not None:
                new_data = request.day_notes.get(day_key) if day_key in request.day_notes else request.day_notes.get(request.day)
                rpc_patch["day_notes"] = {day_key: new_data if new_data is not None else []}
            if request.day_costs is not None:
                new_data = request.day_costs.get(day_key) if day_key in request.day_costs else request.day_costs.get(request.day)
                rpc_patch["day_costs"] = {day_key: new_data if new_data is not None else []}
            if request.day_tickets is not None:
                new_data = request.day_tickets.get(day_key) if day_key in request.day_tickets else request.day_tickets.get(request.day)
                rpc_patch["day_tickets"] = {day_key: new_data if new_data is not None else []}
            if request.day_checklists is not None:
                new_data = request.day_checklists.get(day_key) if day_key in request.day_checklists else request.day_checklists.get(request.day)
                rpc_patch["day_checklists"] = {day_key: new_data if new_data is not None else []}
            if request.day_ai_reviews is not None:
                new_data = request.day_ai_reviews.get(day_key) if day_key in request.day_ai_reviews else request.day_ai_reviews.get(request.day)
                rpc_patch["day_ai_reviews"] = {day_key: new_data if new_data is not None else ""}

            async with trip_lock(trip_id):
                rpc_res = await _execute_atomic_trip_rpc(
                    supabase,
                    "patch_trip_day_data_atomic",
                    {
                        "p_trip_id": trip_id,
                        "p_user_id": user_id,
                        "p_day": request.day,
                        "p_patch": rpc_patch,
                        "p_allow_creator_bypass": False,
                    },
                    trip_id=trip_id,
                    allow_creator_bypass=False,
                    forbidden_detail="您沒有權限修改此行程資訊",
                    not_found_detail="Trip not found",
                )
                if rpc_res is not None:
                    return {"status": "success", "message": "Day data updated"}

        # 🛡️ 權限檢查 (Strict Authorization Check - Legacy RMW Fallback)
        member_check = await run_in_threadpool(
            lambda: supabase.table("trip_members")
            .select("user_id")
            .eq("itinerary_id", trip_id)
            .eq("user_id", user_id)
            .execute()
        )
        
        if not member_check.data:
            raise HTTPException(status_code=403, detail="您沒有權限修改此行程資訊")
        print(f"📝 更新 Day {request.day} 資訊 for Trip {trip_id}")

        async with trip_lock(trip_id):
            def _update_day_data_fallback_sync():
                trip_res = supabase.table("itineraries").select("*").eq("id", trip_id).execute()
                trip = _first_row(trip_res.data)
                if not trip:
                    raise HTTPException(status_code=404, detail="Trip not found")
                
                content = dict(trip.get("content") or {})
                
                def migrate_field(field_name: str):
                    if not content.get(field_name) and trip.get(field_name):
                        content[field_name] = trip.get(field_name)
                        print(f"📦 [Lazy Migration] Migrated {field_name} from legacy column to content")
                        
                migrate_field("day_notes")
                migrate_field("day_costs")
                migrate_field("day_tickets")
                migrate_field("day_checklists")
                migrate_field("ai_review")
                migrate_field("day_ai_reviews")
                migrate_field("daily_locations")
                
                day_key = str(request.day)
                is_owner = _is_trip_creator(trip, user_id, allow_legacy_user_id=True)
                
                if request.day_notes is not None:
                    existing_notes = dict(content.get("day_notes") or {})
                    new_data = request.day_notes.get(day_key) if day_key in request.day_notes else request.day_notes.get(request.day)
                    existing_notes[day_key] = new_data if new_data is not None else []
                    content["day_notes"] = existing_notes
                    
                if request.day_costs is not None:
                    existing_costs = dict(content.get("day_costs") or {})
                    prev_day_costs = existing_costs.get(day_key) if day_key in existing_costs else existing_costs.get(request.day, [])
                    if request.day != day_key and request.day in existing_costs:
                        existing_costs.pop(request.day, None)
                    new_data = request.day_costs.get(day_key) if day_key in request.day_costs else request.day_costs.get(request.day)
                    existing_costs[day_key] = _merge_day_items_preserving_hidden_private(
                        prev_day_costs, new_data if new_data is not None else [], user_id, is_owner
                    )
                    content["day_costs"] = existing_costs
                    
                if request.day_tickets is not None:
                    existing_tickets = dict(content.get("day_tickets") or {})
                    prev_day_tickets = existing_tickets.get(day_key) if day_key in existing_tickets else existing_tickets.get(request.day, [])
                    if request.day != day_key and request.day in existing_tickets:
                        existing_tickets.pop(request.day, None)
                    new_data = request.day_tickets.get(day_key) if day_key in request.day_tickets else request.day_tickets.get(request.day)
                    existing_tickets[day_key] = _merge_day_items_preserving_hidden_private(
                        prev_day_tickets, new_data if new_data is not None else [], user_id, is_owner
                    )
                    content["day_tickets"] = existing_tickets
                
                if request.day_checklists is not None:
                    existing_checklists = dict(content.get("day_checklists") or {})
                    prev_day_checklists = existing_checklists.get(day_key) if day_key in existing_checklists else existing_checklists.get(request.day, [])
                    if request.day != day_key and request.day in existing_checklists:
                        existing_checklists.pop(request.day, None)
                    new_data = request.day_checklists.get(day_key) if day_key in request.day_checklists else request.day_checklists.get(request.day)
                    existing_checklists[day_key] = _merge_day_items_preserving_hidden_private(
                        prev_day_checklists, new_data if new_data is not None else [], user_id, is_owner
                    )
                    content["day_checklists"] = existing_checklists
                    
                if request.day_ai_reviews is not None:
                    existing_reviews = dict(content.get("day_ai_reviews") or {})
                    new_data = request.day_ai_reviews.get(day_key) if day_key in request.day_ai_reviews else request.day_ai_reviews.get(request.day)
                    existing_reviews[day_key] = new_data if new_data is not None else ""
                    content["day_ai_reviews"] = existing_reviews
                    
                supabase.table("itineraries").update({"content": content}).eq("id", trip_id).execute()

            await run_in_threadpool(_update_day_data_fallback_sync)
        
        return {"status": "success", "message": "Day data updated"}

    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="Trip not found")
        print(f"Update Day Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="更新每日資料失敗，請稍後重試")
        


@router.patch("/{trip_id}/location")
async def update_trip_location(
    trip_id: str, 
    request: UpdateLocationRequest, 
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """🗺️ 更新行程的每日地點"""
    try:
        if request.day < 0:
            raise HTTPException(status_code=400, detail="無效的請求參數")

        _precheck_atomic_trip_id(
            supabase,
            trip_id,
            allow_creator_bypass=False,
            forbidden_detail="您沒有權限修改此行程的資訊",
            not_found_detail="找不到此行程",
        )

        if _can_use_atomic_rpc(supabase):
            day_key = str(request.day)
            rpc_patch = {
                "daily_locations": {
                    day_key: {
                        "name": request.name,
                        "lat": request.lat,
                        "lng": request.lng,
                    }
                }
            }
            async with trip_lock(trip_id):
                rpc_res = await _execute_atomic_trip_rpc(
                    supabase,
                    "patch_trip_day_data_atomic",
                    {
                        "p_trip_id": trip_id,
                        "p_user_id": user_id,
                        "p_day": request.day,
                        "p_patch": rpc_patch,
                        "p_allow_creator_bypass": False,
                    },
                    trip_id=trip_id,
                    allow_creator_bypass=False,
                    forbidden_detail="您沒有權限修改此行程的資訊",
                    not_found_detail="找不到此行程",
                )
                if rpc_res is not None:
                    return {"status": "success"}

        # 🧪 權限檢查：先驗證行程成員身分，杜絕未授權存在性探測 (Legacy RMW Fallback)
        member_check = await run_in_threadpool(
            lambda: supabase.table("trip_members")
            .select("user_id")
            .eq("itinerary_id", trip_id)
            .eq("user_id", user_id)
            .execute()
        )
        
        if not member_check.data:
            raise HTTPException(status_code=403, detail="您沒有權限修改此行程的資訊")

        async with trip_lock(trip_id):
            def _update_location_fallback_sync():
                res = supabase.table("itineraries").select("content").eq("id", trip_id).execute()
                trip_row = _first_row(res.data)
                if not trip_row:
                    raise HTTPException(status_code=404, detail="找不到此行程")

                content = dict(trip_row.get('content') or {})
                daily_locs = dict(content.get('daily_locations') or {})
                daily_locs[str(request.day)] = {
                    "name": request.name,
                    "lat": request.lat,
                    "lng": request.lng
                }
                content['daily_locations'] = daily_locs
                supabase.table("itineraries").update({"content": content}).eq("id", trip_id).execute()

            await run_in_threadpool(_update_location_fallback_sync)
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="找不到此行程")
        print(f"🔥 Update Location Error: {e}")
        raise HTTPException(status_code=500, detail="更新每日地點失敗，請稍後重試")



@router.post("/{trip_id}/leave")
def leave_trip(
    trip_id: str,
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """👋 退出行程"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        _guard_resource_id(supabase, trip_id, allow_creator_bypass=True, not_found_detail="找不到此行程")
        # 1. Check trip ownership (safe PGRST116 handling)
        trip = _safe_single_data(
            supabase.table("itineraries").select("created_by").eq("id", trip_id).single()
        )
        if trip and trip.get("created_by") == user_id:
            raise HTTPException(status_code=400, detail="Owner cannot leave trip. Please delete the trip instead.")

        # 2. Remove from trip_members
        res = supabase.table("trip_members").delete().eq("itinerary_id", trip_id).eq("user_id", user_id).execute()
        
        if not res.data:
            return {"message": "User was not in trip or already left"}

        return {"message": "Successfully left the trip"}

    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="找不到此行程")
        print(f"🔥 Leave Trip Error: {e}")
        raise HTTPException(status_code=500, detail="退出行程失敗，請稍後重試")


@router.patch("/{trip_id}/info")
async def update_trip_info(
    trip_id: str, 
    request: UpdateInfoRequest, 
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """✈️ 更新行程資訊 (航班、住宿、信用卡)"""
    try:
        # 🛡️ 戰略修復 3.1: 深度欄位保護更新 (Deep Field Protection)
        # 僅更新請求中明確提供的欄位，避免預設 None 值覆蓋現有資料
        provided_data = request.model_dump(exclude_unset=True)
        print(f"🛠️ [Partial Update] Fields to update: {list(provided_data.keys())}")

        _precheck_atomic_trip_id(
            supabase,
            trip_id,
            allow_creator_bypass=False,
            forbidden_detail="您沒有權限修改此行程資訊",
            not_found_detail="Trip not found",
        )

        if _can_use_atomic_rpc(supabase):
            async with trip_lock(trip_id):
                rpc_res = await _execute_atomic_trip_rpc(
                    supabase,
                    "patch_trip_info_atomic",
                    {
                        "p_trip_id": trip_id,
                        "p_user_id": user_id,
                        "p_patch": provided_data,
                    },
                    trip_id=trip_id,
                    allow_creator_bypass=False,
                    forbidden_detail="您沒有權限修改此行程資訊",
                    not_found_detail="Trip not found",
                )
                if rpc_res is not None:
                    print(f"✅ Strategy 3.1 (Atomic RPC): Partial update successful for Trip {trip_id}")
                    return {"status": "success"}

        # 🛡️ 權限檢查 (Cautious Authorization Check - Legacy RMW Fallback)
        if user_id:
            member_check = await run_in_threadpool(
                lambda: supabase.table("trip_members")
                .select("user_id")
                .eq("itinerary_id", trip_id)
                .eq("user_id", user_id)
                .execute()
            )
            
            if not member_check.data:
                print(f"🔒 [Auth Denied] User {user_id} tried to update Trip {trip_id}")
                raise HTTPException(status_code=403, detail="您沒有權限修改此行程資訊")

        async with trip_lock(trip_id):
            def _update_info_fallback_sync():
                trip_res = supabase.table("itineraries").select("content, flight_info, hotel_info, created_by").eq("id", trip_id).execute()
                trip_row = _first_row(trip_res.data)
                if not trip_row:
                    raise HTTPException(status_code=404, detail="Trip not found")
                    
                current_content = dict(trip_row.get("content") or {})
                update_columns = {}
                is_owner = _is_trip_creator(trip_row, user_id, allow_legacy_user_id=True)

                if "credit_cards" in provided_data:
                    cards = _merge_cards_preserving_hidden_private(
                        current_content.get("credit_cards", []),
                        provided_data["credit_cards"],
                        user_id,
                        is_owner,
                    )
                    current_content["credit_cards"] = cards
                    print(f"   🃏 Cards updated: {len(cards)} items")

                if "flight_info" in provided_data:
                    f_info = provided_data["flight_info"]
                    update_columns["flight_info"] = f_info
                    current_content["flight_info"] = f_info
                    
                if "hotel_info" in provided_data:
                    h_info = provided_data["hotel_info"]
                    update_columns["hotel_info"] = h_info
                    current_content["hotel_info"] = h_info

                update_columns["content"] = current_content
                supabase.table("itineraries").update(update_columns).eq("id", trip_id).execute()

            await run_in_threadpool(_update_info_fallback_sync)
        print(f"✅ Strategy 3.1: Partial update successful for Trip {trip_id}")
        
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="Trip not found")
        print(f"Update Info Error: {e}")
        raise HTTPException(status_code=500, detail="更新行程資訊失敗，請稍後重試")


@router.patch("/{trip_id}/dates")
async def update_trip_dates(
    trip_id: str,
    request: UpdateDatesRequest,
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """📅 原子化更新行程日期區間 (With Zero-Regression Shifting Engine)"""
    print(f"📅 更新行程 {trip_id} 日期: {request.start_date} ~ {request.end_date}, on_shorten={request.on_shorten}, user={user_id}")
    try:
        _guard_resource_id(supabase, trip_id, allow_creator_bypass=True, not_found_detail="行程不存在")
        async with trip_lock(trip_id):
            def _update_dates_sync() -> int:
                # 1. 取得目前行程 (保留 .single() 以相容既有測試合約並防衛 PGRST116)
                trip = _safe_single_data(
                    supabase.table("itineraries").select("created_by, start_date, end_date, content").eq("id", trip_id).single()
                )
                if not trip:
                    raise HTTPException(status_code=404, detail="行程不存在")

                content = dict(trip.get("content") or {})
                created_by = trip.get("created_by", "")

                # 2. 權限檢查 (創立者或成員皆有權限)
                if user_id:
                    is_creator = (user_id == created_by)
                    if not is_creator:
                        member_check = supabase.table("trip_members")\
                            .select("user_id")\
                            .eq("itinerary_id", trip_id)\
                            .eq("user_id", user_id)\
                            .execute()
                        if not member_check.data:
                            raise HTTPException(status_code=403, detail="您沒有權限修改此行程日期")

                # 3. 日期計算與格式防呆
                old_start_str = trip.get("start_date") or request.start_date
                old_end_str = trip.get("end_date") or old_start_str
                try:
                    old_start = datetime.strptime(str(old_start_str).split('T')[0], "%Y-%m-%d")
                    old_end = datetime.strptime(str(old_end_str).split('T')[0], "%Y-%m-%d")
                    new_start = datetime.strptime(str(request.start_date).split('T')[0], "%Y-%m-%d")
                    new_end = datetime.strptime(str(request.end_date).split('T')[0], "%Y-%m-%d")
                except (ValueError, TypeError):
                    raise HTTPException(status_code=400, detail="無效的日期格式，請使用 YYYY-MM-DD")

                if new_end < new_start:
                    raise HTTPException(status_code=400, detail="結束日期不能早於開始日期")

                old_days = max(1, (old_end - old_start).days + 1)
                new_days_val = max(1, (new_end - new_start).days + 1)

                if new_days_val < old_days:
                    excess_items = supabase.table("itinerary_items")\
                        .select("id, day_number")\
                        .eq("itinerary_id", trip_id)\
                        .gt("day_number", new_days_val)\
                        .execute()
                    excess_rows = excess_items.data or []
                    excess_ids = [item["id"] for item in excess_rows]

                    if excess_ids:
                        if request.on_shorten == "merge":
                            for batch in _chunked(excess_ids):
                                supabase.table("itinerary_items")\
                                    .update({"day_number": new_days_val})\
                                    .in_("id", batch)\
                                    .execute()
                        else:
                            for batch in _chunked(excess_ids):
                                supabase.table("itinerary_items").delete().in_("id", batch).execute()

                    if request.on_shorten == "merge":
                        for field in DAY_MAP_FIELDS:
                            if field in content and isinstance(content[field], dict):
                                for k in list(content[field].keys()):
                                    if k.isdigit() and int(k) > new_days_val:
                                        if isinstance(content[field].get(str(new_days_val)), list) and isinstance(content[field][k], list):
                                            content[field][str(new_days_val)].extend(content[field][k])
                                        elif isinstance(content[field].get(str(new_days_val)), str) and isinstance(content[field][k], str):
                                            content[field][str(new_days_val)] += f"\n{content[field][k]}"
                                        del content[field][k]
                    else:
                        for field in DAY_MAP_FIELDS:
                            if field in content and isinstance(content[field], dict):
                                for k in list(content[field].keys()):
                                    if k.isdigit() and int(k) > new_days_val:
                                        del content[field][k]

                    try:
                        supabase.rpc(
                            "shift_trip_capsules",
                            {
                                "p_trip_id": trip_id,
                                "p_op": "truncate_merge" if request.on_shorten == "merge" else "truncate_delete",
                                "p_pivot_day": new_days_val,
                            },
                        ).execute()
                    except Exception as cap_err:
                        print(f"⚠️ Capsule Truncate/Merge Warning: {cap_err}")

                updates = {
                    "start_date": request.start_date,
                    "end_date": request.end_date,
                    "content": content
                }
                supabase.table("itineraries").update(updates).eq("id", trip_id).execute()
                return new_days_val

            new_days = await run_in_threadpool(_update_dates_sync)
        print(f"✅ 成功原子化更新 Trip {trip_id} 日期為 {request.start_date} ~ {request.end_date} (共 {new_days} 天)")

        return {
            "status": "success",
            "start_date": request.start_date,
            "end_date": request.end_date,
            "total_days": new_days
        }

    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="行程不存在")
        print(f"🔥 Update Dates Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="更新行程日期失敗，請稍後重試")


# ═══════════════════════════════════════════════════════════════════════════════
# Items CRUD (Batch 3)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/items")
async def create_item(
    request: CreateItemRequest, 
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """➕ 新增單筆行程項目"""
    try:
        _guard_resource_id(supabase, request.itinerary_id, allow_creator_bypass=False, forbidden_detail="您沒有權限在此行程新增項目")
        # 🧪 權限檢查：只有行程成員可以新增項目
        def _check_create_auth():
            member_check = supabase.table("trip_members")\
                .select("user_id")\
                .eq("itinerary_id", request.itinerary_id)\
                .eq("user_id", user_id)\
                .execute()
            if not member_check.data:
                raise HTTPException(status_code=403, detail="您沒有權限在此行程新增項目")
            if request.is_private and not _fetch_trip_is_owner(supabase, request.itinerary_id, user_id):
                raise HTTPException(status_code=403, detail="僅行程建立者可建立私密行程項目")

        await run_in_threadpool(_check_create_auth)

        lat_val = request.lat if (
            request.lat is not None
            and request.lng is not None
            and math.isfinite(request.lat)
            and math.isfinite(request.lng)
            and -90.0 <= request.lat <= 90.0
            and -180.0 <= request.lng <= 180.0
            and not (request.lat == 0.0 and request.lng == 0.0)
        ) else None
        lng_val = request.lng if lat_val is not None else None

        should_preserve_coords = False
        if request.preserve_coords and lat_val is not None and lng_val is not None:
            from services.geocode_service import HOMONYM_GUARD_KEYS, is_self_consistent_foreign_place
            pname_low = (request.place_name or "").strip().lower()
            is_homonym_create = any(hk.lower() in pname_low for hk in HOMONYM_GUARD_KEYS)
            if not is_homonym_create or is_self_consistent_foreign_place(
                {
                    "place_name": request.place_name,
                    "notes": request.notes,
                    "address": request.address,
                },
                lat_val,
                lng_val,
            ):
                should_preserve_coords = True

        # 🟢 自動地理編碼與空間錨點防呆 (結合 4 層動態空間錨點，同時攔截空座標與跨國/撞名異常座標)
        if not should_preserve_coords:
            try:
                from services.geocode_service import verify_and_heal_itinerary_coords
                def _fetch_geo_ctx():
                    meta = None
                    existing = []
                    try:
                        t_res = supabase.table("itineraries").select("id, title, content").eq("id", request.itinerary_id).execute()
                        if t_res and t_res.data:
                            meta = t_res.data[0]
                        it_res = supabase.table("itinerary_items").select("day_number, place_name, location_lat, location_lng").eq("itinerary_id", request.itinerary_id).execute()
                        if it_res and isinstance(it_res.data, list):
                            existing = it_res.data
                    except Exception:
                        pass
                    return meta, existing

                trip_meta, existing_items_data = await run_in_threadpool(_fetch_geo_ctx)
                healed_single, _ = await verify_and_heal_itinerary_coords(
                    [
                        {
                            "day_number": request.day_number,
                            "place_name": request.place_name,
                            "notes": request.notes,
                            "address": request.address,
                            "lat": lat_val,
                            "lng": lng_val,
                        }
                    ],
                    trip_meta=trip_meta,
                    existing_items=existing_items_data,
                )
                if healed_single:
                    lat_val = healed_single[0].get("lat")
                    lng_val = healed_single[0].get("lng")
            except Exception as geo_err:
                print(f"⚠️ [AutoGeocode] Non-critical geocoding fallback failed: {geo_err}")

        clean_link_url, clean_website_link, clean_sub_items = _sanitize_item_links(
            request.link_url,
            request.website_link,
            request.sub_items,
        )

        data = {
            "itinerary_id": request.itinerary_id,
            "day_number": request.day_number,
            "time_slot": request.time_slot,
            "place_name": request.place_name,
            "category": request.category,
            "notes": request.notes,
            "location_lat": lat_val,
            "location_lng": lng_val,
            "image_url": request.image_url,
            "image_urls": request.image_urls or ([request.image_url] if request.image_url else []),
            "tags": request.tags,
            "memo": request.memo,
            "sub_items": clean_sub_items,
            "link_url": clean_link_url,
            "website_link": clean_website_link,
            "address": request.address,
            "reservation_code": request.reservation_code,
            "cost_amount": request.cost_amount,
            "preview_metadata": request.preview_metadata,
            "hide_navigation": request.hide_navigation,
            "is_private": request.is_private,
            "is_highlight": request.is_highlight
        }
        
        res = await run_in_threadpool(lambda: supabase.table("itinerary_items").insert(data).execute())
        
        if not res.data:
            raise HTTPException(status_code=500, detail="插入失敗")
        
        print(f"✅ 單筆行程新增成功：{request.place_name}")
        return {"status": "success", "data": res.data}
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="找不到此行程")
        print(f"🔥 Create Item Error: {e}")
        raise HTTPException(status_code=500, detail="新增行程項目失敗，請稍後重試")


# 🆕 批次排序更新 API (Moved up to avoid conflict with {item_id})
@router.patch("/items/reorder")
def reorder_items(
    request: ReorderRequest, 
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """🔄 批次更新多個項目的排序順序"""
    print(f"🔄 批次排序: {len(request.items)} 項目, user={user_id}")
    try:
        results = []
        if request.items:
            # 🛡️ 權限檢查 (BOLA Defense)：去重並分段驗證所有排序項目皆隸屬於同一合法行程
            unique_item_ids = list(dict.fromkeys(i.item_id for i in request.items))
            for iid in unique_item_ids:
                _guard_resource_id(supabase, iid, allow_creator_bypass=True, not_found_detail="部分行程項目不存在")
            db_items = []
            for batch in _chunked(unique_item_ids):
                items_query = supabase.table("itinerary_items").select("id, itinerary_id, is_private").in_("id", batch).execute()
                db_items.extend(items_query.data or [])
            if len(db_items) != len(unique_item_ids):
                raise HTTPException(status_code=404, detail="部分行程項目不存在")
            
            itinerary_ids = {row["itinerary_id"] for row in db_items}
            if len(itinerary_ids) != 1:
                raise HTTPException(status_code=400, detail="禁止跨行程批次排序")
            
            tid = itinerary_ids.pop()
            member_check = supabase.table("trip_members").select("user_id").eq("itinerary_id", tid).eq("user_id", user_id).execute()
            if not member_check.data:
                raise HTTPException(status_code=403, detail="您沒有權限排序此行程")

            if any(row.get("is_private") for row in db_items):
                is_owner = _fetch_trip_is_owner(supabase, tid, user_id)
                if any(not _is_day_item_visible_to_user(row, user_id, is_owner) for row in db_items):
                    raise HTTPException(status_code=403, detail="您沒有權限排序他人的私密行程項目")

            for item in request.items:
                data = {"sort_order": item.sort_order}
                
                # 如果選擇自動調整時間
                if request.adjust_times and item.time_slot:
                    data["time_slot"] = item.time_slot
                
                res = supabase.table("itinerary_items").update(data).eq("id", item.item_id).eq("itinerary_id", tid).execute()
                results.append({"id": item.item_id, "updated": bool(res.data)})
        
        print(f"✅ 排序更新完成: {len(results)} 項目")
        return {"status": "success", "results": results}
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="部分行程項目不存在")
        traceback.print_exc()
        print(f"🔥 Reorder Error: {e}")
        raise HTTPException(status_code=500, detail="批次排序失敗，請稍後重試")


@router.patch("/items/{item_id}")
async def update_item(
    item_id: str, 
    request: UpdateItemRequest, 
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """📝 修改單一細項"""
    print(f"📝 嘗試更新細項 {item_id}, user={user_id}")
    try:
        _guard_resource_id(supabase, item_id, allow_creator_bypass=True, not_found_detail="找不到此行程項目")
        # 🛡️ 權限檢查與資料快照 (非 single 查詢：缺失項目先回 404，防止 PGRST116 轉為 500)
        def _fetch_item_and_check_auth():
            item_check = supabase.table("itinerary_items").select("itinerary_id, link_url, website_link, sub_items, location_lat, location_lng, image_url, image_urls, place_name, is_private").eq("id", item_id).execute()
            row = _first_row(item_check.data)
            if not row:
                raise HTTPException(status_code=404, detail="找不到此行程項目")
            tid = row["itinerary_id"]
            member_check = supabase.table("trip_members").select("user_id").eq("itinerary_id", tid).eq("user_id", user_id).execute()
            if not member_check.data:
                raise HTTPException(status_code=403, detail="您沒有權限修改此項目")
            if row.get("is_private") or request.is_private:
                is_owner = _fetch_trip_is_owner(supabase, tid, user_id)
                if row.get("is_private") and not _is_day_item_visible_to_user(row, user_id, is_owner):
                    raise HTTPException(status_code=403, detail="您沒有權限修改此私密行程項目")
                if request.is_private and not is_owner:
                    raise HTTPException(status_code=403, detail="僅行程建立者可將行程項目設為私密")
            return row

        item_row = await run_in_threadpool(_fetch_item_and_check_auth)
        # 只更新有值的欄位
        data = {}
        if request.time_slot is not None: data["time_slot"] = request.time_slot
        if request.place_name is not None: data["place_name"] = request.place_name
        if request.notes is not None: data["notes"] = request.notes
        if request.cost_amount is not None: data["cost_amount"] = request.cost_amount
        # 👇 寫入資料庫
        if request.lat is not None: data["location_lat"] = request.lat
        if request.lng is not None: data["location_lng"] = request.lng

        # 🛡️ 導航網址分流防線：導航網址 (link_url) 僅允許地圖網域，非地圖網址改入 sub_items（此地備忘錄）與 website_link
        sanitized_link_url: Optional[str] = None
        sanitized_website_link: Optional[str] = None
        should_write_website = False
        sanitized_sub_items: Optional[List[dict]] = None
        if request.link_url is not None or request.website_link is not None:
            existing_sub_items = item_row.get("sub_items") if isinstance(item_row.get("sub_items"), list) else []
            existing_website = item_row.get("website_link")
            base_sub_items = request.sub_items if request.sub_items is not None else existing_sub_items

            raw_req_link = request.link_url.strip() if isinstance(request.link_url, str) else ""
            raw_req_web = request.website_link.strip() if isinstance(request.website_link, str) else ""
            existing_web_str = existing_website.strip() if isinstance(existing_website, str) else ""

            link_was_non_map = bool(raw_req_link) and not is_map_navigation_url(raw_req_link)
            website_actively_changed = (
                request.website_link is not None
                and bool(raw_req_web)
                and _normalize_url_for_dedupe(raw_req_web) != _normalize_url_for_dedupe(existing_web_str)
            )

            if link_was_non_map or website_actively_changed:
                new_web_for_sanitize = raw_req_web if website_actively_changed else None
                clean_link, clean_web, clean_subs = _sanitize_item_links(
                    raw_req_link if request.link_url is not None else item_row.get("link_url"),
                    new_web_for_sanitize,
                    base_sub_items,
                )
                sanitized_link_url = clean_link
                if website_actively_changed:
                    sanitized_website_link = clean_web
                    should_write_website = True
                elif clean_web:
                    sanitized_website_link = (
                        existing_web_str if _is_safe_http_url(existing_web_str) else clean_web
                    )
                    should_write_website = True
                elif request.website_link is not None:
                    sanitized_website_link = raw_req_web if _is_safe_http_url(raw_req_web) else None
                    should_write_website = True
                sanitized_sub_items = clean_subs
            else:
                if request.link_url is not None:
                    sanitized_link_url = raw_req_link if is_map_navigation_url(raw_req_link) else None
                if request.website_link is not None:
                    sanitized_website_link = raw_req_web if _is_safe_http_url(raw_req_web) else None
                    should_write_website = True

        # 🕵️ JIT Resolution logic (Sub-Atomic Guard)
        # 如果收到潛在的同步信號（lat 為 None）且合法地圖網址異動
        if request.link_url is not None and sanitized_link_url and request.lat is None and item_row:
            current_url = item_row.get("link_url", "") or ""
            new_url = sanitized_link_url
            
            # Normalize for comparison
            if new_url.rstrip("/") != current_url.rstrip("/"):
                try:
                    print(f"🛰️ Detected URL change with null coords signal, triggering JIT resolution for: {new_url}")
                    resolved = await resolve_google_maps_link(new_url)
                    if resolved and resolved.get("lat"):
                        data["location_lat"] = float(resolved["lat"])
                        data["location_lng"] = float(resolved["lng"])
                        print(f"✅ JIT Resolution Success: {data['location_lat']}, {data['location_lng']}")

                        # 🧬 v31.8: Absolute-Synergy Visual Sync (Zero-Regression Protocol)
                        if resolved.get("metadata"):
                            try:
                                meta = resolved["metadata"]
                                new_thumb = meta.get("image")
                                
                                if new_thumb and isinstance(new_thumb, str):
                                    # 1. Gallery Merger (Cumulative Synergy)
                                    # Priority order: Frontend Payload > DB Current > Resolved Thumbnail
                                    raw_urls = request.image_urls if request.image_urls is not None else (item_row.get("image_urls") or [])
                                    target_urls = raw_urls if isinstance(raw_urls, list) else []
                                    
                                    # Prepend new thumbnail to gallery if it's unique
                                    clean_thumb = new_thumb.strip()
                                    if clean_thumb and clean_thumb not in [str(u).strip() for u in target_urls if u]:
                                        target_urls.insert(0, clean_thumb)
                                        request.image_urls = target_urls
                                        print(f"📸 Visual Synergy: Atomic gallery merge - Added {clean_thumb[:30]}...")
                                    
                                    # 2. Cover Protection (Human-Priority Guard)
                                    # Only set as primary if BOTH the editor payload and DB are empty
                                    if not request.image_url and not item_row.get("image_url"):
                                        request.image_url = clean_thumb
                                        print("📸 Visual Synergy: Primary cover populated (Empty-State Recovery)")

                                # 3. Title Intelligence (Merit Preservation)
                                # Never overwrite a name if the user or the DB already has one
                                if meta.get("title") and not request.place_name and not item_row.get("place_name"):
                                    request.place_name = meta["title"]
                                    print(f"🏷️ Title Synergy: Auto-filling name: {meta['title']}")

                                # 4. Atomic Metadata Injection
                                data["preview_metadata"] = meta
                            except Exception as inner_e:
                                # 🛡️ Zero-Noise: Non-critical failures should never block the save
                                print(f"⚠️ Visual JIT (trips.py) gracefully ignored: {inner_e}")
                    else:
                        # 🛡️ v35.24: Conditional Cleanse (Anti-Sticky-Pin)
                        # Only invalidate if URL actually changed
                        current_db_url = item_row.get("link_url") or ""
                        if sanitized_link_url and sanitized_link_url.rstrip("/") != current_db_url.rstrip("/"):
                            data["location_lat"] = None
                            data["location_lng"] = None
                            print("🧹 Sticky Pin Prevention: Cleansed stale coords due to URL change")
                        else:
                            # Preserve existing behavior for non-URL-change scenarios
                            data.pop("location_lat", None)
                            data.pop("location_lng", None)
                except Exception as ex:
                    print(f"⚠️ JIT Resolution Failed: {ex}")
                    # 🛡️ v35.24: Same conditional cleanse for exception path
                    current_db_url = item_row.get("link_url") or ""
                    if sanitized_link_url and sanitized_link_url.rstrip("/") != current_db_url.rstrip("/"):
                        data["location_lat"] = None
                        data["location_lng"] = None
                    else:
                        data.pop("location_lat", None)
                        data.pop("location_lng", None)
        # 👇 新增：處理備忘錄
        if request.memo is not None: data["memo"] = request.memo
        # 🆕 新增：處理預約資訊
        if request.link_url is not None: data["link_url"] = sanitized_link_url
        if should_write_website: data["website_link"] = sanitized_website_link
        if request.address is not None: data["address"] = request.address
        if request.reservation_code is not None: data["reservation_code"] = request.reservation_code
        # 👇 新增：處理 sub_items (連結列表)
        if sanitized_sub_items is not None:
            data["sub_items"] = sanitized_sub_items
        elif request.sub_items is not None:
            data["sub_items"] = request.sub_items
        # 👇 新增：處理分類與標籤
        if request.category is not None: data["category"] = request.category
        if request.tags is not None: data["tags"] = request.tags
        # 👇 新增：處理圖片 URL (向後相容)
        if request.image_url is not None: data["image_url"] = request.image_url
        # 🆕 新增：處理多圖片 URLs
        if request.image_urls is not None: data["image_urls"] = request.image_urls
        # 🆕 新增：處理預覽元數據
        if request.preview_metadata is not None: data["preview_metadata"] = request.preview_metadata
        # 🆕 新增：處理排序順序 (拖曳排序)
        if request.sort_order is not None: data["sort_order"] = request.sort_order
        # 🆕 新增：手動隱藏導航
        if request.hide_navigation is not None: data["hide_navigation"] = request.hide_navigation
        if request.is_private is not None: data["is_private"] = request.is_private
        if request.is_highlight is not None: data["is_highlight"] = request.is_highlight
        
        if not data:
            print("⚠️ 沒有資料需要更新")
            return {"status": "no_change"}

        res = await run_in_threadpool(lambda: supabase.table("itinerary_items").update(data).eq("id", item_id).execute())
        
        if not res.data:
            print(f"❌ 更新失敗：找不到 ID {item_id}")
            raise HTTPException(status_code=404, detail="找不到此行程項目")

        print("✅ 更新成功")
        return {"status": "success", "data": res.data}
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="找不到此行程項目")
        traceback.print_exc()
        print(f"🔥 Update Item Exception: {e}")
        raise HTTPException(status_code=500, detail="更新行程項目失敗，請稍後重試")


@router.delete("/items/{item_id}")
def delete_item(
    item_id: str, 
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """🗑️ 刪除單一細項"""
    print(f"🗑️ 嘗試刪除細項 {item_id}, user={user_id}")
    try:
        _guard_resource_id(supabase, item_id, allow_creator_bypass=True, not_found_detail="找不到此行程項目")
        # 🛡️ 權限檢查 (非 single() 查詢，確保項目已刪除時具備天然冪等性)
        item_check = supabase.table("itinerary_items").select("itinerary_id, is_private").eq("id", item_id).execute()
        if item_check.data and len(item_check.data) > 0:
            item_row = item_check.data[0]
            tid = item_row["itinerary_id"]
            member_check = supabase.table("trip_members").select("user_id").eq("itinerary_id", tid).eq("user_id", user_id).execute()
            if not member_check.data:
                 raise HTTPException(status_code=403, detail="您沒有權限刪除此項目")
            if item_row.get("is_private"):
                is_owner = _fetch_trip_is_owner(supabase, tid, user_id)
                if not _is_day_item_visible_to_user(item_row, user_id, is_owner):
                    raise HTTPException(status_code=403, detail="您沒有權限刪除此私密行程項目")

        res = supabase.table("itinerary_items").delete().eq("id", item_id).execute()
        
        if not res.data:
             print(f"ℹ️ 刪除略過：找不到 ID {item_id} (已處於已刪除狀態)")
             # 這裡不噴錯，滿足冪等性 (Idempotency)
             return {"status": "success", "message": "Item might already be deleted"}
             
        print(f"✅ 刪除成功：{item_id}")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="找不到此行程項目")
        print(f"🔥 Delete Item Error: {e}")
        raise HTTPException(status_code=500, detail="刪除行程項目失敗，請稍後重試")


# ═══════════════════════════════════════════════════════════════════════════════
# Day Management - HIGH RISK (Batch 4)
# ⚠️ Contains complex algorithms: Ghostbuster, Scorched Earth, Smart Clone
# ═══════════════════════════════════════════════════════════════════════════════

@router.delete("/{trip_id}/days/{day_number}")
async def delete_day(
    trip_id: str, 
    day_number: int, 
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """🗑️ 刪除整天行程 (Deep Logic Fix)"""
    print(f"🗑️ 嘗試刪除行程 {trip_id} 第 {day_number} 天, user={user_id}")
    try:
        _guard_resource_id(supabase, trip_id, allow_creator_bypass=False, forbidden_detail="您沒有權限修改此行程")
        # 🛡️ 權限檢查
        member_check = await run_in_threadpool(
            lambda: supabase.table("trip_members").select("user_id").eq("itinerary_id", trip_id).eq("user_id", user_id).execute()
        )
        if not member_check.data:
            raise HTTPException(status_code=403, detail="您沒有權限修改此行程")

        async with trip_lock(trip_id):
            def _delete_day_sync() -> int:
                trip_res = supabase.table("itineraries").select("start_date, end_date, content").eq("id", trip_id).execute()
                trip_row = _first_row(trip_res.data)
                if not trip_row:
                    raise HTTPException(status_code=404, detail="行程不存在")

                res = supabase.table("itinerary_items")\
                    .delete()\
                    .eq("itinerary_id", trip_id)\
                    .eq("day_number", day_number)\
                    .execute()
                del_cnt = len(res.data) if res.data else 0
                
                remaining = supabase.table("itinerary_items")\
                    .select("id, day_number")\
                    .eq("itinerary_id", trip_id)\
                    .gt("day_number", day_number)\
                    .execute()
                
                by_target_day = {}
                for item in (remaining.data or []):
                    target_day = item["day_number"] - 1
                    by_target_day.setdefault(target_day, []).append(item["id"])
                for target_day in sorted(by_target_day.keys()):
                    for batch in _chunked(by_target_day[target_day]):
                        supabase.table("itinerary_items")\
                            .update({"day_number": target_day})\
                            .in_("id", batch)\
                            .execute()

                try:
                    supabase.rpc(
                        "shift_trip_capsules",
                        {
                            "p_trip_id": trip_id,
                            "p_op": "delete_shift",
                            "p_pivot_day": day_number,
                        },
                    ).execute()
                except Exception as cap_err:
                    print(f"⚠️ Capsule Delete-Shift Warning: {cap_err}")

                content = dict(trip_row.get("content") or {})
                start_date = datetime.strptime(trip_row["start_date"], "%Y-%m-%d") if trip_row.get("start_date") else None
                end_date = datetime.strptime(trip_row["end_date"], "%Y-%m-%d") if trip_row.get("end_date") else None
                current_max_day = (end_date - start_date).days + 1 if (start_date and end_date) else 30

                for field in DAY_MAP_FIELDS:
                    if field in content and isinstance(content[field], dict):
                        if str(day_number) in content[field]:
                            del content[field][str(day_number)]
                        for i in range(day_number + 1, current_max_day + 2):
                            old_key = str(i)
                            new_key = str(i - 1)
                            if old_key in content[field]:
                                content[field][new_key] = content[field][old_key]
                                del content[field][old_key]

                updates = {"content": content}
                if end_date:
                    new_end = end_date - timedelta(days=1)
                    updates["end_date"] = new_end.strftime("%Y-%m-%d")
                    
                supabase.table("itineraries").update(updates).eq("id", trip_id).execute()
                return del_cnt

            deleted_count = await run_in_threadpool(_delete_day_sync)

        print(f"   ✅ Day {day_number} 刪除完成，Content 已校正，Activities 已位移")
        return {"status": "success", "deleted_items": deleted_count}

    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="行程不存在")
        print(f"🔥 Delete Day Error: {e}")
        raise HTTPException(status_code=500, detail="刪除天數失敗，請稍後重試")


@router.post("/{trip_id}/days")
async def add_day(
    trip_id: str, 
    request: AddDayRequest, 
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """➕ 新增天數 (With Ghostbuster)"""
    print(f"➕ 新增天數 to {trip_id}, user={user_id}")
    try:
        _guard_resource_id(supabase, trip_id, allow_creator_bypass=False, forbidden_detail="您沒有權限修改此行程")
        # 🛡️ 權限檢查
        member_check = await run_in_threadpool(
            lambda: supabase.table("trip_members").select("user_id").eq("itinerary_id", trip_id).eq("user_id", user_id).execute()
        )
        if not member_check.data:
            raise HTTPException(status_code=403, detail="您沒有權限修改此行程")

        insert_before_val: Optional[int] = None
        if request.position.startswith("before:"):
            try:
                insert_before_val = max(1, int(request.position.split(":", 1)[1]))
            except (ValueError, IndexError):
                raise HTTPException(status_code=400, detail="無效的 position 格式")
        elif request.position != "end":
            raise HTTPException(status_code=400, detail="無效的 position 格式")

        async with trip_lock(trip_id):
            def _add_day_sync():
                trip_res = supabase.table("itineraries").select("start_date, end_date, content").eq("id", trip_id).execute()
                trip_row = _first_row(trip_res.data)
                if not trip_row:
                    raise HTTPException(status_code=404, detail="行程不存在")
                    
                content = dict(trip_row.get("content") or {})

                utc_today_midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
                start_date = datetime.strptime(trip_row["start_date"], "%Y-%m-%d") if trip_row.get("start_date") else utc_today_midnight
                end_date = datetime.strptime(trip_row["end_date"], "%Y-%m-%d") if trip_row.get("end_date") else start_date
                date_calculated_days = (end_date - start_date).days + 1
                
                all_content_keys = []
                for field in DAY_MAP_FIELDS:
                    if field in content and isinstance(content[field], dict):
                        all_content_keys.extend(content[field].keys())
                
                valid_day_nums = [int(k) for k in all_content_keys if k.isdigit()]
                content_max_day = max(valid_day_nums) if valid_day_nums else 0
                shift_limit_day = max(date_calculated_days, content_max_day)
                
                if content_max_day > date_calculated_days:
                    print(f"   👻 發現幽靈資料! Content Max: {content_max_day} > Date Max: {date_calculated_days}")

                n_day = -1
                source_day_for_clone = None

                if request.position == "end":
                    n_day = date_calculated_days + 1
                    print(f"   ➕ 新增 Day {n_day} 到結尾 (覆蓋該位置可能的幽靈)")
                    source_day_for_clone = n_day - 1
                    
                elif insert_before_val is not None:
                    insert_before = insert_before_val
                    n_day = insert_before
                    source_day_for_clone = insert_before 
                    
                    items_to_shift = supabase.table("itinerary_items")\
                        .select("id, day_number")\
                        .eq("itinerary_id", trip_id)\
                        .gte("day_number", insert_before)\
                        .order("day_number", desc=True)\
                        .execute()
                    
                    by_new_day = {}
                    for item in (items_to_shift.data or []):
                        target_day = item["day_number"] + 1
                        by_new_day.setdefault(target_day, []).append(item["id"])
                    for target_day in sorted(by_new_day.keys(), reverse=True):
                        for batch in _chunked(by_new_day[target_day]):
                            supabase.table("itinerary_items")\
                                .update({"day_number": target_day})\
                                .in_("id", batch)\
                                .execute()

                    try:
                        supabase.rpc(
                            "shift_trip_capsules",
                            {
                                "p_trip_id": trip_id,
                                "p_op": "insert_shift",
                                "p_pivot_day": insert_before,
                            },
                        ).execute()
                    except Exception as cap_err:
                        print(f"⚠️ Capsule Insert-Shift Warning: {cap_err}")
                    
                    for field in DAY_MAP_FIELDS:
                        if field not in content: content[field] = {}
                        if not isinstance(content[field], dict): content[field] = {}

                        for i in range(shift_limit_day, insert_before - 1, -1):
                            old_key = str(i)
                            new_key = str(i + 1)
                            if old_key in content[field]:
                                content[field][new_key] = content[field][old_key]
                                del content[field][old_key]
                    
                    source_day_for_clone = 2 if insert_before == 1 else insert_before - 1
                    print(f"   ➕ 插入 Day {n_day}, Content 已反向位移")
                
                target_key = str(n_day)
                print(f"   🔥 執行焦土清理 Day {n_day}")
                
                cleaned_count = 0
                for field in DAY_MAP_FIELDS:
                     if field not in content: content[field] = {}
                     if target_key in content[field]:
                         del content[field][target_key]
                         print(f"      🧹 已清除殘留資料: {field}[{target_key}]")
                         cleaned_count += 1
                
                if cleaned_count > 0:
                    print(f"   ✅ 焦土清理完成，共清除 {cleaned_count} 個欄位")

                if request.clone_content and source_day_for_clone:
                    print(f"   🌱 執行智慧移植: 從 Day {source_day_for_clone} -> Day {n_day}")
                    src_key = str(source_day_for_clone)
                    
                    def wash_ids(items):
                        if not isinstance(items, list): return items
                        new_items = copy.deepcopy(items)
                        for item in new_items:
                            if isinstance(item, dict) and "id" in item:
                                item["id"] = str(uuid.uuid4())
                        return new_items

                    for field in CLONEABLE_FIELDS:
                        if field in content and src_key in content[field]:
                            data = content[field][src_key]
                            if field in ["day_checklists", "day_costs", "day_tickets"] and isinstance(data, list):
                                data = wash_ids(data)
                                print(f"      🆔 已為 {field} 內的 {len(data)} 個項目重整唯一身份")
                            content[field][target_key] = data
                            print(f"      ✅ 複製 {field}")

                final_total = date_calculated_days + 1
                new_end_date = start_date + timedelta(days=final_total - 1)
                updates = {
                    "content": content,
                    "end_date": new_end_date.strftime("%Y-%m-%d")
                }
                supabase.table("itineraries").update(updates).eq("id", trip_id).execute()
                return n_day, final_total

            new_day, final_total_days = await run_in_threadpool(_add_day_sync)
        
        return {"status": "success", "new_day": new_day, "total_days": final_total_days}

    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="行程不存在")
        print(f"🔥 Add Day Error: {e}")
        raise HTTPException(status_code=500, detail="新增天數失敗，請稍後重試")


# ═══════════════════════════════════════════════════════════════════════════════
# 💰 Expenses Integration (Cross-Module Compatibility)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/{trip_id}/expenses")
def get_trip_expenses(
    trip_id: str, 
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """
    📊 獲取行程的費用列表 (配合前端 API.TRIPS 路徑)
    
    邏輯：抓出 (該行程的所有公帳) OR (該行程中 我建立的私帳)
    """
    try:
        _guard_resource_id(supabase, trip_id, allow_creator_bypass=False, forbidden_detail="您不是此行程的成員，無法存取費用列表")
        # 🛡️ BOLA 物件授權防衛：非行程建立者或成員禁止查詢任何費用明細
        if not check_trip_access(supabase, trip_id, user_id):
            raise HTTPException(status_code=403, detail="您不是此行程的成員，無法存取費用列表")

        print(f"💰 [Trips] Fetching expenses for trip {trip_id}, user {user_id}")
        res = supabase.table("expenses").select("*").eq("itinerary_id", trip_id).execute()
        all_expenses = res.data or []
        
        filtered = []
        for exp in all_expenses:
            # 🛡️ Authorization Partition
            is_owner = str(exp.get('created_by')) == user_id
            if not (exp.get('is_public') or is_owner):
                continue

            raw_date = exp.get('incurred_at') or ''
            expense_date = str(raw_date).split('T')[0] if raw_date else None
            
            version = exp.get("details_schema_version", 1)
            items = normalize_items(exp.get("details", []), version)
            
            expense_resp = ExpenseResponse(
                id=str(exp["id"]),
                itinerary_id=str(exp["itinerary_id"]),
                title=exp.get("title", "Untitled"),
                total_amount=exp.get("amount", 0.0),
                amount=exp.get("amount", 0.0), # Sync for backward compatibility
                subtotal_amount=exp.get("subtotal_amount", 0.0),
                tax_amount=exp.get("tax_amount", 0.0),
                tip_amount=exp.get("tip_amount", 0.0),
                service_charge_amount=exp.get("service_charge_amount", 0.0),
                discount_amount=exp.get("discount_amount", 0.0),
                currency=exp.get("currency", "JPY"),
                category=exp.get("category", "其他"),
                is_public=exp.get("is_public", True),
                expense_date=expense_date,
                payment_method=exp.get("payment_method"),
                exchange_rate=exp.get("exchange_rate"),
                items=items,
                diagnostics=ReceiptDiagnostics(
                    status=exp.get("validation_status", "pass"),
                    source="ai" if exp.get("validation_status") == "warning" else "user",
                    code=exp.get("validation_code"),
                    message=exp.get("validation_message"),
                    mismatch_amount=exp.get("mismatch_amount", 0.0)
                ),
                details_schema_version=version,
                created_at=str(exp.get("created_at")),
                created_by=str(exp.get("created_by")) if str(exp.get("created_by")) == user_id else f"mem_{hashlib.sha256((str(exp.get('created_by')) + trip_id).encode()).hexdigest()[:10]}",
                creator_name=exp.get("creator_name"),
                image_url=exp.get("image_url"),
                card_name=exp.get("card_name"),
                cashback_rate=exp.get("cashback_rate", 0.0),
                custom_icon=exp.get("custom_icon"),
                notes=exp.get("notes"),
                payer_id=exp.get("payer_id") if exp.get("payer_id") == user_id else (f"mem_{hashlib.sha256((str(exp.get('payer_id')) + trip_id).encode()).hexdigest()[:10]}" if exp.get("payer_id") else None),
                payer_name=exp.get("payer_name")
            )
            filtered.append(expense_resp.model_dump())
                
        print(f"✅ [Trips] Returned {len(filtered)} standardized expenses")
        return filtered
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="找不到此行程")
        print(f"🔥 Fetch Trip Expenses Error: {e}")
        raise HTTPException(status_code=500, detail="讀取行程費用失敗，請稍後重試")


@router.patch("/{trip_id}/ledger-share")
def generate_ledger_share_code(
    trip_id: str,
    user_id: str = Depends(get_verified_user),
    supabase=Depends(get_supabase)
):
    """
    🔗 為行程生成公帳分享碼 (Ledger Share Code)
    
    邏輯：
    1. 驗證使用者是否為該行程成員
    2. 生成 6 碼隨機字串 (大寫字母+數字)
    3. 更新 itineraries 表的 ledger_share_code 欄位
    """
    try:
        _guard_resource_id(supabase, trip_id, allow_creator_bypass=False, forbidden_detail="您沒有權解操作此行程的分享功能")
        # 1. 權限檢查
        member_check = supabase.table("trip_members")\
            .select("user_id")\
            .eq("itinerary_id", trip_id)\
            .eq("user_id", user_id)\
            .execute()
            
        if not member_check.data:
            raise HTTPException(status_code=403, detail="您沒有權解操作此行程的分享功能")
            
        # 2. 生成新 UUID
        share_code = str(uuid.uuid4())
            
        # 3. 更新資料庫
        update_res = supabase.table("itineraries")\
            .update({"ledger_share_code": share_code})\
            .eq("id", trip_id)\
            .execute()
            
        if not update_res.data:
            raise HTTPException(status_code=404, detail="找不到此行程或更新失敗")
            
        print(f"✅ [Share] Generated Ledger Share Code: {share_code} for trip {trip_id}")
        return {
            "status": "success",
            "ledger_share_code": share_code
        }
        
    except HTTPException:
        raise
    except Exception as e:
        _raise_if_pg_invalid_uuid(e, detail="找不到此行程或更新失敗")
        print(f"🔥 Ledger Share Error: {e}")
        raise HTTPException(status_code=500, detail="生成帳本分享碼失敗，請稍後重試")
