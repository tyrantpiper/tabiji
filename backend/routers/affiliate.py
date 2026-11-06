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

@router.get("/{partner}/{target_id:path}")
async def redirect_to_partner(partner: str, target_id: str, request: Request):
    """
    分潤跳轉遮罩端點：
    防範 Open Redirect 漏洞，限制僅能跳轉至合作夥伴已授權之網址前綴。
    支援 Unicode 地區路徑與 Query String 安全轉發。
    """
    if partner not in ALLOWED_AFFILIATE_PARTNERS:
        raise HTTPException(status_code=400, detail="Disallowed affiliate partner")

    # 嚴格禁止偽造 scheme、換行符號、雙斜線或反斜線跳轉
    if (
        not PARAM_REGEX.match(target_id)
        or "://" in target_id
        or target_id.startswith("//")
        or "//" in target_id
        or "\\" in target_id
    ):
        raise HTTPException(status_code=400, detail="Invalid target parameter detected")

    # 若請求包含 Query String (例如 ?item=晴空塔)，嚴格驗證並安全轉發
    query = request.url.query
    if query:
        if (
            not PARAM_REGEX.match(query)
            or "://" in query
            or "//" in query
            or "\\" in query
        ):
            raise HTTPException(status_code=400, detail="Invalid query parameter detected")
        separator = "&" if "?" in target_id else "?"
        target_id = f"{target_id}{separator}{query}"

    base_jump = ALLOWED_AFFILIATE_PARTNERS[partner]
    final_destination = f"{base_jump}{target_id}"
    return RedirectResponse(url=final_destination, status_code=302)

