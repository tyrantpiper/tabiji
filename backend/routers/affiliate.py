# -*- coding: utf-8 -*-
"""
🛡️ Tabiji Affiliate Gateway Router
Provides cloaked 302 redirection for travel booking partners (Klook, KKday, Booking).
Defends against Open Redirect and SSRF attacks with strict partner domain whitelisting.
"""

import re
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/go", tags=["affiliate"])

ALLOWED_AFFILIATE_PARTNERS = {
    "klook": "https://affiliate.klook.com/jump?aff_id=TABIJI_AFF_888&target=",
    "kkday": "https://www.kkday.com/zh-tw/affiliate/jump?cid=TABIJI_AFF_999&url=",
    "booking": "https://www.booking.com/index.html?aid=TABIJI_BOOKING_111&label="
}

PARAM_REGEX = re.compile(r'^[\w\-\./\?=&%~+]+$', re.UNICODE)

UUID_REGEX = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

@router.get("/{partner}")
@router.get("/{partner}/{target_id:path}")
async def redirect_to_partner(partner: str, request: Request, target_id: str = ""):
    """
    分潤跳轉遮罩端點：
    防範 Open Redirect 漏洞，限制僅能跳轉至合作夥伴已授權之網址前綴。
    支援 Unicode 地區路徑與 Query String 安全轉發，並在缺乏目標或傳入內部 UUID 時優雅回退至夥伴首頁。
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

    # 合作夥伴官方基底網址回退表
    fallback_map = {
        "klook": "https://www.klook.com/zh-TW/",
        "kkday": "https://www.kkday.com/zh-tw",
        "booking": "https://www.booking.com/"
    }

    # 若目標為內部 UUID (如 Tabiji 行程 UUID) 或為空，優雅回退至合作夥伴官方首頁
    if not clean_target or UUID_REGEX.match(clean_target):
        clean_target = fallback_map.get(partner, "")

    # 若請求包含 Query String (例如 ?item=晴空塔)，嚴格驗證並安全轉發
    query = request.url.query if request else ""
    if query:
        if (
            not PARAM_REGEX.match(query)
            or "://" in query
            or "//" in query
            or "\\" in query
        ):
            raise HTTPException(status_code=400, detail="Invalid query parameter detected")
        separator = "&" if "?" in clean_target else "?"
        clean_target = f"{clean_target}{separator}{query}"

    base_jump = ALLOWED_AFFILIATE_PARTNERS[partner]
    final_destination = f"{base_jump}{clean_target}"
    return RedirectResponse(url=final_destination, status_code=302)

