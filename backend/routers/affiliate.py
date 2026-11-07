# -*- coding: utf-8 -*-
"""
🛡️ Tabiji Affiliate Gateway Router
Provides cloaked 302 redirection & direct Travelpayouts attribution URL builder
for travel booking partners (Klook, KKday, Booking, Trip.com).
Defends against Open Redirect and SSRF attacks with strict partner domain whitelisting.
"""

import os
import re
import urllib.parse
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/go", tags=["affiliate"])

TP_MARKER = os.getenv("NEXT_PUBLIC_TP_MARKER", os.getenv("TP_MARKER", "602410")).strip() or "602410"
BOOKING_AID = os.getenv("NEXT_PUBLIC_BOOKING_AID", "").strip()
TRIP_ALLIANCE_ID = os.getenv("NEXT_PUBLIC_TRIP_ALLIANCEID", "").strip()
TRIP_SID = os.getenv("NEXT_PUBLIC_TRIP_SID", "").strip()

ALLOWED_AFFILIATE_PARTNERS = {
    "klook": "https://www.klook.com/zh-TW/",
    "kkday": "https://www.kkday.com/zh-tw",
    "booking": "https://www.booking.com/",
    "tripcom": "https://www.trip.com/",
}

PARAM_REGEX = re.compile(r'^[\w\-\./\?=&%~+\s]+$', re.UNICODE)
UUID_REGEX = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)


def sanitize_activity_query(destination: Optional[str] = None, activity_name: Optional[str] = None) -> str:
    """🛡️ 智慧複合查詢消毒器 (與前端 affiliate-config.ts sanitizeActivityQuery 對齊，防止重複疊詞)"""
    clean_dest = (destination or "").strip()
    clean_act = (activity_name or "").strip()
    if not clean_act:
        return clean_dest
    if not clean_dest or UUID_REGEX.match(clean_dest):
        return clean_act
    if clean_dest.lower() in clean_act.lower() or clean_act.lower() in clean_dest.lower():
        return clean_act
    return f"{clean_dest} {clean_act}"


def build_tp_media_url(marker: str, program_id: int, target_url: str) -> str:
    """建構官方 Travelpayouts tp.media 追蹤跳轉網址"""
    if not marker:
        return target_url
    encoded_marker = urllib.parse.quote(marker, safe="")
    encoded_target = urllib.parse.quote(target_url, safe="")
    return f"https://tp.media/r?marker={encoded_marker}&p={program_id}&u={encoded_target}"


def build_legacy_tp_url(marker: str, server_id: str, promo_id: int, target_url: str) -> str:
    """建構 Travelpayouts cXXX 傳統追蹤跳轉網址 (Booking / Trip.com 備援)"""
    encoded_marker = urllib.parse.quote(marker, safe="")
    encoded_target = urllib.parse.quote(target_url, safe="")
    return (
        f"https://{server_id}.travelpayouts.com/click?"
        f"shmarker={encoded_marker}&promo_id={promo_id}&source_type=customlink&type=click&custom_url={encoded_target}"
    )


def build_affiliate_url(
    partner: str,
    target_id: str = "",
    item: Optional[str] = None,
    destination: Optional[str] = None,
    raw_query: str = "",
) -> str:
    """
    統一產生與前端 UI 訂購中心 (frontend/lib/affiliate-config.ts) 100% 一致的真實分潤連結。
    """
    p_key = (partner or "klook").strip().lower()
    clean_target = (target_id or "").strip()
    is_uuid_or_empty = (not clean_target) or bool(UUID_REGEX.match(clean_target))

    # 解析搜尋關鍵字
    item_val = (item or "").strip()
    dest_val = (destination or "").strip()
    if not dest_val and not is_uuid_or_empty and "/" not in clean_target:
        dest_val = clean_target

    combined_query = sanitize_activity_query(dest_val, item_val)

    if p_key == "klook":
        if "/" in clean_target and not is_uuid_or_empty:
            target_url = f"https://www.klook.com/zh-TW/{clean_target.lstrip('/')}"
            if raw_query:
                sep = "&" if "?" in target_url else "?"
                target_url = f"{target_url}{sep}{raw_query}"
        elif combined_query:
            target_url = f"https://www.klook.com/zh-TW/search/result/?query={urllib.parse.quote(combined_query)}"
        else:
            target_url = "https://www.klook.com/zh-TW/"
            if raw_query:
                target_url = f"{target_url}?{raw_query}"
        return build_tp_media_url(TP_MARKER, 4110, target_url)

    if p_key == "kkday":
        if "/" in clean_target and not is_uuid_or_empty:
            target_url = f"https://www.kkday.com/zh-tw/{clean_target.lstrip('/')}"
            if raw_query:
                sep = "&" if "?" in target_url else "?"
                target_url = f"{target_url}{sep}{raw_query}"
        elif combined_query:
            target_url = f"https://www.kkday.com/zh-tw/product/productlist?keyword={urllib.parse.quote(combined_query)}"
        else:
            target_url = "https://www.kkday.com/zh-tw"
            if raw_query:
                target_url = f"{target_url}?{raw_query}"
        return build_tp_media_url(TP_MARKER, 9074, target_url)

    if p_key == "booking":
        if combined_query:
            target_url = f"https://www.booking.com/searchresults.html?ss={urllib.parse.quote(combined_query)}"
        elif not is_uuid_or_empty:
            target_url = f"https://www.booking.com/{clean_target.lstrip('/')}"
        else:
            target_url = "https://www.booking.com/"
        if BOOKING_AID:
            sep = "&" if "?" in target_url else "?"
            return f"{target_url}{sep}aid={urllib.parse.quote(BOOKING_AID)}&label=tabidachi_mcp"
        return build_legacy_tp_url(TP_MARKER, "c84", 3650, target_url)

    if p_key == "tripcom":
        if combined_query:
            target_url = f"https://www.trip.com/hotels/list?city={urllib.parse.quote(combined_query)}"
        else:
            target_url = "https://www.trip.com/"
        if TRIP_ALLIANCE_ID and TRIP_SID:
            sep = "&" if "?" in target_url else "?"
            return f"{target_url}{sep}Allianceid={urllib.parse.quote(TRIP_ALLIANCE_ID)}&SID={urllib.parse.quote(TRIP_SID)}"
        return build_legacy_tp_url(TP_MARKER, "c121", 3778, target_url)

    raise HTTPException(status_code=400, detail="Disallowed affiliate partner")


@router.get("/{partner}")
@router.get("/{partner}/{target_id:path}")
async def redirect_to_partner(partner: str, request: Request, target_id: str = ""):
    """
    分潤跳轉遮罩端點：
    防範 Open Redirect 漏洞，限制僅能跳轉至合作夥伴已授權之 Travelpayouts / 官方分潤網址。
    支援 Unicode 地區路徑與 Query String 安全轉發，並在缺乏目標或傳入內部 UUID 時優雅回退。
    """
    if partner not in ALLOWED_AFFILIATE_PARTNERS:
        raise HTTPException(status_code=400, detail="Disallowed affiliate partner")

    clean_target = (target_id or "").strip()

    # 嚴格禁止偽造 scheme、換行符號、雙斜線或反斜線跳轉
    if clean_target:
        if (
            not PARAM_REGEX.match(clean_target)
            or "://" in clean_target
            or clean_target.startswith("//")
            or "//" in clean_target
            or "\\" in clean_target
        ):
            raise HTTPException(status_code=400, detail="Invalid target parameter detected")

    query = request.url.query if request else ""
    if query:
        if (
            not PARAM_REGEX.match(query)
            or "://" in query
            or "//" in query
            or "\\" in query
        ):
            raise HTTPException(status_code=400, detail="Invalid query parameter detected")

    item_param = request.query_params.get("item") or request.query_params.get("query") if request else None
    dest_param = request.query_params.get("destination") if request else None

    final_destination = build_affiliate_url(
        partner=partner,
        target_id=clean_target,
        item=item_param,
        destination=dest_param,
        raw_query=query,
    )
    return RedirectResponse(url=final_destination, status_code=302)

