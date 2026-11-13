"""
App Router
----------
Handles global app-level settings and meta-information.
"""

import math
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from utils.deps import get_supabase

router = APIRouter(prefix="/api/app", tags=["app"])

DEFAULT_DONATION_GOAL = 2000.0
MAX_DONATION_PERCENTAGE = 120.0


@router.get("/donation-progress")
async def get_donation_progress(supabase=Depends(get_supabase)):
    """
    💰 獲取捐贈進度（隱私最小揭露 + Fail-Closed）

    僅於伺服端計算百分比回傳 `{available, percentage, month}`，絕不在 HTTP 封包傳輸原始台幣金額 (`current` / `goal`)；
    查無設定列回傳 `{available: false}`；資料庫或網路異常則回傳 HTTP 503 觸發前端整張隱藏。
    """
    headers = {"Cache-Control": "no-store"}
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        res = (
            supabase.table("app_settings")
            .select("value")
            .eq("key", "donation_progress")
            .limit(1)
            .execute()
        )
        rows = res.data if isinstance(res.data, list) else ([res.data] if res.data else [])
        if not rows or not isinstance(rows[0], dict) or not isinstance(rows[0].get("value"), dict):
            return JSONResponse(content={"available": False}, headers=headers)

        val = rows[0]["value"]
        stored_month = str(val.get("month") or current_month)

        try:
            raw_goal = float(val.get("goal") or DEFAULT_DONATION_GOAL)
        except (TypeError, ValueError):
            raw_goal = DEFAULT_DONATION_GOAL
        safe_goal = raw_goal if (math.isfinite(raw_goal) and raw_goal > 0) else DEFAULT_DONATION_GOAL

        try:
            raw_current = float(val.get("current") or 0.0)
        except (TypeError, ValueError):
            raw_current = 0.0
        safe_current = raw_current if (math.isfinite(raw_current) and raw_current > 0) else 0.0

        # UTC 跨月自動歸零顯示
        if stored_month != current_month:
            safe_current = 0.0

        raw_pct = (safe_current / safe_goal) * 100.0
        percentage = round(min(max(raw_pct, 0.0), MAX_DONATION_PERCENTAGE), 1)
        return JSONResponse(
            content={
                "available": True,
                "percentage": percentage,
                "month": current_month,
            },
            headers=headers,
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"🔥 Get Donation Progress Error: {e}")
        raise HTTPException(
            status_code=503,
            detail="Donation progress unavailable",
            headers=headers,
        )
